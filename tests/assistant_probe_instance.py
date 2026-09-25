"""Boot a throwaway instance with the owner's private assistant config and run the prompt library.

python tests/assistant_probe_instance.py --output OUTSIDE_THE_REPOSITORY [--only P01,P07] [--confirm]

The instance uses its own temporary SQLite database and port; the owner's preview data, accounts
and passwords are never touched. The assistant configuration is the private file the running
preview already uses (never read, copied or printed here). Accounts are created with passwords
this script generates. Without --confirm only chat messages are sent; with --confirm the prepared
cards are clicked as well, which is fine here because the whole instance is a throwaway trial.
"""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from assistant_prompt_probe import PROMPTS, ask, login          # noqa: E402

ADMIN_PASSWORD = 'Probe-Admin-' + secrets.token_urlsafe(12)
STAFF_PASSWORD = 'Probe-Staff-' + secrets.token_urlsafe(12)
FINAL_PASSWORD = 'Probe-Final-' + secrets.token_urlsafe(12)
ACCOUNTS = [('probe-sales', '试用销售', 'sales'), ('probe-service', '试用服务', 'service'),
            ('probe-stock', '试用库管', 'inventory'), ('probe-finance', '试用财务', 'finance'),
            ('probe-manager', '试用店长', 'manager')]
ROLE_PROMPTS = {'probe-sales': ('P01', 'P02', 'P03', 'P04', 'P05', 'P06', 'P07', 'P08', 'P09',
                                'P14', 'P24', 'P26', 'P27', 'C01'),
                'probe-service': ('P10', 'P11', 'P12', 'P13', 'P27', 'C03'),
                'probe-stock': ('P15', 'P16', 'P17', 'P18'),
                'probe-finance': ('P19', 'P20', 'P21', 'P22'),
                'probe-manager': ('P23', 'P24', 'P25', 'P27', 'C02')}


def environment(work):
    return {**os.environ, 'DATABASE_URL': 'sqlite:///' + (work / 'probe.sqlite').as_posix(),
            'APP_ENV': 'local', 'ALLOWED_HOSTS': '127.0.0.1,localhost', 'COOKIE_SECURE': 'false',
            'SCHEDULER_ENABLED': 'false', 'SCHEDULER_MODE': 'off', 'FILE_SCAN_MODE': 'structure_only',
            'FILE_STORAGE_MODE': 'blob', 'PRIVATE_FILE_ROOT': '', 'ALLOW_AI_EXTERNAL': 'true',
            'LEGACY_BUSINESS_WRITE': 'false', 'HUAKANGOS_INITIAL_PASSWORD': ADMIN_PASSWORD,
            'DEALER_INITIAL_PASSWORD': ADMIN_PASSWORD, 'PYTHONUTF8': '1'}


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def start(work):
    env = environment(work)
    init = subprocess.run([sys.executable, '-m', 'app.cli', 'init'], cwd=ROOT, env=env,
                          capture_output=True, text=True, encoding='utf-8')
    if init.returncode:
        raise RuntimeError('临时库初始化失败：' + init.stderr)
    port = free_port()
    log = (work / 'server.log').open('w', encoding='utf-8')
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                               '--port', str(port)], cwd=ROOT, env=env, stdout=log, stderr=log,
                              creationflags=flags)
    base = 'http://127.0.0.1:%d' % port
    with httpx.Client(base_url=base, timeout=3, trust_env=False) as client:
        for _ in range(200):
            if server.poll() is not None:
                raise RuntimeError('临时实例启动失败：' + (work / 'server.log').read_text('utf-8')[-800:])
            try:
                if client.get('/api/health').status_code == 200:
                    return server, base, log
            except httpx.HTTPError:
                pass
            time.sleep(.1)
    raise RuntimeError('临时实例未就绪')


def create_accounts(client):
    for username, display, role in ACCOUNTS:
        response = client.post('/api/users', json={'username': username, 'display_name': display,
                                                   'role': role, 'password': STAFF_PASSWORD,
                                                   'store_ids': [1],
                                                   'store_roles': [{'store_id': 1, 'role': role}]},
                               headers={'X-App-Request': '1'})
        assert response.status_code == 201, (username, response.text)
    # A fresh account must change its password before anything else works; do it through the
    # ordinary endpoint, exactly like the employee would on first login.
    for username, _, _ in ACCOUNTS:
        with httpx.Client(base_url=client.base_url, timeout=30, trust_env=False) as employee:
            login(employee, username, STAFF_PASSWORD)
            changed = employee.post('/api/auth/password', json={'current_password': STAFF_PASSWORD,
                                                               'new_password': FINAL_PASSWORD})
            assert changed.status_code == 200, (username, changed.text)


def spec_values(kind, **extra):
    """Fill every required field of that business with a value the page would accept."""
    from app.flow_specs import SPECS
    values = {}
    for field in SPECS[kind]['fields']:
        if not field.get('required'):
            continue
        field_type = field.get('type')
        options = field.get('options') or []
        if field_type == 'select' and options:
            values[field['key']] = options[0]
        elif field_type == 'money':
            values[field['key']] = '100.00'
        elif field_type == 'quantity':
            values[field['key']] = '1'
        elif field_type == 'int':
            values[field['key']] = 1
        elif field_type in {'date', 'future_date'}:
            values[field['key']] = '2026-12-31'
        elif field_type == 'bool':
            values[field['key']] = True
        else:
            values[field['key']] = '试用'
    values.update(extra)
    return values


def seed(base, report):
    """Give the prompts something real to work on, through the ordinary APIs only."""
    with httpx.Client(base_url=base, timeout=60, trust_env=False) as employee:
        login(employee, 'probe-sales', FINAL_PASSWORD)
        employee.headers['X-Store-ID'] = '1'
        lead = employee.post('/api/flow/cases', json={'request_id': secrets.token_hex(16), 'kind': 'lead',
                                                      'values': spec_values('lead', customer_name='张试用',
                                                                             customer_phone='13900001111')})
        report.append(('seeded lead', lead.status_code, lead.text[:160]))
        if lead.status_code == 201:
            case_id = lead.json()['id']
            detail = employee.get('/api/flow/cases/%d' % case_id).json()
            for action in detail.get('actions') or []:
                report.append(('lead action', action.get('key'), action.get('enabled'), action.get('reason')))
    with httpx.Client(base_url=base, timeout=60, trust_env=False) as service:
        login(service, 'probe-service', FINAL_PASSWORD)
        service.headers['X-Store-ID'] = '1'
        repair = service.post('/api/flow/cases', json={'request_id': secrets.token_hex(16), 'kind': 'repair',
                                                       'values': spec_values('repair', customer_name='张试用',
                                                                             customer_phone='13900001111',
                                                                             plate='试用A1001',
                                                                             problem='刹车异响（试用）')})
        report.append(('seeded repair', repair.status_code, repair.text[:160]))


def run_prompts(base, output, only, confirm=False):
    wanted = {item.strip().upper() for item in only.split(',') if item.strip()}
    results = []
    for username, _, _ in ACCOUNTS:
        mine = [item for item in PROMPTS if item[0] in ROLE_PROMPTS[username]]
        if wanted:
            mine = [item for item in mine if item[0] in wanted]
        if not mine:
            continue
        with httpx.Client(base_url=base, timeout=60, trust_env=False) as client:
            login(client, username, FINAL_PASSWORD)
            client.headers['X-Store-ID'] = '1'
            for index, group, prompt in mine:
                record = ask(client, index, prompt, confirm=confirm)
                record.update({'group': group, 'account': username})
                results.append(record)
                print('%s %s %s -> %s' % (username, index, prompt,
                                          (record.get('reply') or record.get('error') or '')[:80].replace('\n', ' ')))
                time.sleep(.5)
    (output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 助手口语化探针（一次性实例 + 真实模型）', '']
    for record in results:
        lines += ['## %s %s（%s）%s' % (record['account'], record['index'], record.get('group', ''), record['prompt']), '',
                  '- 状态 %s · 用时 %ss' % (record.get('status'), record.get('seconds')), '']
        if record.get('error'):
            lines += ['```', record['error'], '```', '']
            continue
        lines += ['**助手回复**', '', record.get('reply') or '（空）', '']
        if record.get('proposals'):
            lines += ['**确认卡**', ''] + ['- %s（%s）' % (card.get('summary'), card.get('operation'))
                                          for card in record['proposals']] + ['']
        for card in record.get('confirmed') or []:
            lines += ['**已点确认**：%s → %s（%s）%s' % (card.get('summary'), card.get('proposal_status'),
                      card.get('status'), (' · ' + card.get('result', '')) if card.get('result') else ''), '']
    (output / 'results.md').write_text('\n'.join(lines), encoding='utf-8')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', default='')
    parser.add_argument('--confirm', action='store_true', help='点确认卡（只用于一次性测试库）')
    parser.add_argument('--keep-server', action='store_true')
    args = parser.parse_args()
    if args.output.resolve() == ROOT or ROOT in args.output.resolve().parents:
        parser.error('把结果写到仓库之外')
    args.output.mkdir(parents=True, exist_ok=True)
    import tempfile
    work = Path(tempfile.mkdtemp(prefix='huakangos-assistant-probe-'))
    server, base, log = start(work)
    print('temporary instance:', base, 'work', work, flush=True)
    try:
        with httpx.Client(base_url=base, timeout=60, trust_env=False) as admin:
            login(admin, 'admin', ADMIN_PASSWORD)
            admin.headers['X-Store-ID'] = '1'
            create_accounts(admin)
            status = admin.get('/api/business-assistant/status').json()
            print('assistant status:', json.dumps(status, ensure_ascii=False)[:200], flush=True)
        report = []
        seed(base, report)
        for row in report:
            print('seed:', row, flush=True)
        results = run_prompts(base, args.output, args.only, confirm=args.confirm)
        (args.output / 'seed.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('prompts run:', len(results), '->', args.output, flush=True)
    finally:
        if args.keep_server:
            print('server kept at', base, 'log', work / 'server.log', flush=True)
        else:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
            log.close()


if __name__ == '__main__':
    main()
