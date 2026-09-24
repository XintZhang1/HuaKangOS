"""Create the XC trial staff accounts in a RUNNING local preview.

Talks to the ordinary HTTP API of the local preview (same endpoints the 员工账号 page uses),
so every account goes through the normal admin check, audit trail and "first login must
change password" rule. It never writes to the database directly and never stores, echoes or
logs a password: the administrator password and the shared initial staff password are typed
on the terminal (or passed through the environment for an automated synthetic run) and are
only used for the HTTP requests.

Refuses anything that is not a loopback address reporting itself as a local preview.
Staff rows come from docs/trial-source/world.json, so the tool and the trial scripts cannot
drift apart. Safe to re-run: existing logins are reported and skipped.
"""
import argparse
import getpass
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / 'docs/trial-source/world.json'
LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1'}
DEFAULT_BASE = 'http://127.0.0.1:8000'
MIN_PASSWORD = 12


class PreviewError(RuntimeError):
    """A refusal or a plain Chinese message coming back from the preview."""


def load_staff(path=WORLD):
    """Non-administrator accounts of the trial world, in file order."""
    world = json.loads(Path(path).read_text('utf-8-sig'))
    staff = [{'username': account['username'], 'display_name': account['display_name'],
              'role': account['role'], 'store': account['store'], 'purpose': account['purpose']}
             for account in world['accounts'] if account['role'] != 'admin']
    if not staff:
        raise PreviewError('试用世界设定里没有员工账号')
    return staff


def check_base(base):
    """Return the normalised base URL, or refuse anything that is not loopback HTTP."""
    parts = urllib.parse.urlsplit(base)
    if parts.scheme != 'http':
        raise PreviewError('只允许连接本机 http 预览（当前：%s）' % base)
    host = (parts.hostname or '').lower()
    if host not in LOOPBACK_HOSTS:
        raise PreviewError('为避免写错库，只允许连接本机地址（127.0.0.1 / localhost / ::1），当前：%s' % host)
    if parts.port is None:
        raise PreviewError('请在地址里带上端口，例如 %s' % DEFAULT_BASE)
    host = parts.hostname if ':' not in parts.hostname else '[%s]' % parts.hostname
    return '%s://%s:%d' % (parts.scheme, host, parts.port)


class PreviewClient:
    """Minimal HTTP client: cookies, CSRF header and Chinese error messages."""

    def __init__(self, base, opener=None):
        self.base = check_base(base)
        self.jar = http.cookiejar.CookieJar()
        self.opener = opener or urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def csrf(self):
        for cookie in self.jar:
            if cookie.name == 'dealer_csrf':
                return cookie.value
        return ''

    def request(self, method, path, payload=None, headers=None):
        body = None if payload is None else json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(self.base + path, data=body, method=method)
        request.add_header('X-App-Request', '1')
        if body is not None:
            request.add_header('Content-Type', 'application/json')
            if self.csrf():
                request.add_header('X-CSRF-Token', self.csrf())
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with self.opener.open(request, timeout=20) as response:
                text = response.read().decode('utf-8')
                return json.loads(text) if text.strip() else {}
        except urllib.error.HTTPError as error:
            raw = error.read().decode('utf-8', 'replace')
            try:
                detail = json.loads(raw).get('detail')
            except (ValueError, AttributeError):
                detail = raw[:200]
            raise PreviewError('%s %s' % (error.code, detail or error.reason)) from None
        except urllib.error.URLError as error:
            raise PreviewError('连不上预览（%s）。请先双击 start-preview.cmd 打开预览。' % error.reason) from None

    def status(self):
        state = self.request('GET', '/api/local-preview/status')
        if not state.get('local_preview'):
            raise PreviewError('这个地址不是本机独立预览库，脚本已停止；不会向其它环境写入账号')
        if state.get('bootstrap_required'):
            raise PreviewError('预览还没有设置管理员：请先按首次设置页面创建管理员，再运行本脚本')
        return state

    def login(self, username, password):
        return self.request('POST', '/api/auth/login', {'username': username, 'password': password})

    def stores(self):
        return self.request('GET', '/api/stores').get('items', [])

    def users(self):
        return self.request('GET', '/api/users').get('items', [])

    def create_user(self, store_id, row, password, store_role):
        payload = {'username': row['username'], 'display_name': row['display_name'],
                   'role': row['role'], 'password': password, 'can_group_summary': False,
                   'store_ids': [store_id], 'store_roles': [{'store_id': store_id, 'role': store_role}]}
        return self.request('POST', '/api/users', payload, {'X-Store-ID': str(store_id)})


def resolve_store(stores, wanted_code, interactive=True, ask=input):
    """Prefer the trial store code, then the only active store, then ask."""
    active = [store for store in stores if store.get('active', True)]
    if not active:
        raise PreviewError('预览里还没有可用门店：请先在 系统管理 → 门店设置 建一家门店')
    for store in active:
        if str(store.get('code', '')).strip().lower() == wanted_code.strip().lower():
            return store, '按试用世界设定的门店编码匹配'
    if len(active) == 1:
        return active[0], '预览里只有一家门店，按它分配'
    listing = '\n'.join('  %d) %s（%s）' % (index, store['name'], store.get('code', ''))
                        for index, store in enumerate(active, start=1))
    if not interactive:
        raise PreviewError('没有找到编码 %s 的门店，且有多家门店，无法自动选择：\n%s' % (wanted_code, listing))
    print('没有找到编码 %s 的门店，请选择本次分配的门店：\n%s' % (wanted_code, listing))
    while True:
        answer = ask('输入序号：').strip()
        if answer.isdigit() and 1 <= int(answer) <= len(active):
            return active[int(answer) - 1], '按你的选择分配'


def run(client, store, staff, password, dry_run=False, reporter=print):
    """Create missing accounts; return rows describing what happened."""
    existing = {user['username'].lower() for user in client.users()}
    store_id = store['id']
    results = []
    for row in staff:
        if row['username'].lower() in existing:
            results.append({**row, 'result': 'skipped', 'note': '已存在，未改动'})
            reporter('  已存在 %-14s %s' % (row['username'], row['display_name']))
            continue
        if dry_run:
            results.append({**row, 'result': 'planned', 'note': '试运行未写入'})
            reporter('  将新建 %-14s %-6s %s' % (row['username'], row['role'], row['display_name']))
            continue
        try:
            client.create_user(store_id, row, password, row['role'])
        except PreviewError as error:
            results.append({**row, 'result': 'failed', 'note': str(error)})
            reporter('  失败   %-14s %s' % (row['username'], error))
            continue
        results.append({**row, 'result': 'created', 'note': '已创建，首次登录必须改密'})
        reporter('  已创建 %-14s %-6s %s' % (row['username'], row['role'], row['display_name']))
    return results


def read_secret(env_name, prompt, confirm=False):
    value = os.environ.get(env_name, '')
    if value:
        return value
    value = getpass.getpass(prompt)
    if confirm:
        again = getpass.getpass('再输入一次：')
        if value != again:
            raise PreviewError('两次输入的密码不一致，请重新运行')
    return value


def build_parser():
    """No --password option on purpose: passwords are never passed on the command line."""
    parser = argparse.ArgumentParser(description='为 XC 试用世界批量创建员工账号（只允许本机独立预览）')
    parser.add_argument('--base', default=os.environ.get('XC_BASE', DEFAULT_BASE),
                        help='本机预览地址，默认 %s' % DEFAULT_BASE)
    parser.add_argument('--store-code', default=None, help='分配门店编码，默认取试用世界设定（XC-CD）')
    parser.add_argument('--admin', default=os.environ.get('XC_ADMIN_USER', 'admin'), help='管理员登录账号')
    parser.add_argument('--dry-run', action='store_true', help='只显示将要创建哪些账号，不写入')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    staff = load_staff()
    wanted_code = args.store_code or staff[0]['store']
    client = PreviewClient(args.base)
    state = client.status()
    print('已连接本机预览（%s，实例 %s）' % (client.base, str(state.get('instance_id'))[:8]))
    client.login(args.admin, read_secret('XC_ADMIN_PASSWORD', '管理员密码（%s）：' % args.admin))
    store, why = resolve_store(client.stores(), wanted_code)
    print('本次分配门店：%s（%s）—— %s' % (store['name'], store.get('code', ''), why))
    password = '' if args.dry_run else read_secret('XC_STAFF_PASSWORD',
                                                   '员工初始密码（%d 位以上，首次登录必须改）：' % MIN_PASSWORD,
                                                   confirm=True)
    if not args.dry_run and len(password) < MIN_PASSWORD:
        raise PreviewError('员工初始密码至少 %d 位' % MIN_PASSWORD)
    print('开始建立 %d 个员工账号%s：' % (len(staff), '（试运行）' if args.dry_run else ''))
    results = run(client, store, staff, password, dry_run=args.dry_run)
    created = [row for row in results if row['result'] == 'created']
    skipped = [row for row in results if row['result'] == 'skipped']
    failed = [row for row in results if row['result'] == 'failed']
    planned = [row for row in results if row['result'] == 'planned']
    print('结果：新建 %d，已存在 %d，失败 %d%s' % (len(created), len(skipped), len(failed),
                                              '，试运行 %d' % len(planned) if planned else ''))
    if created:
        print('下一步：用 xc-sales 等账号首次登录，按提示设置个人密码；初始密码不会保存到任何文件。')
    if failed:
        print('失败的行请看上面的中文提示；修正后可以重复运行本脚本，已存在的账号会被跳过。')
        return 3
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except PreviewError as error:
        print('未执行：' + str(error))
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print('已取消，没有写入。')
        raise SystemExit(1) from None
