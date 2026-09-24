"""Real configured model + assistant HTTP workflow in a fresh synthetic database.

This API trial does not mock model replies. Its server-only HTTPX audit hook
observes actual provider usage without storing headers/prompts/replies and stops
after the configured 1-40 provider calls. Login and manager assignment are declared prerequisites.
"""
from datetime import datetime, timedelta
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def server_entry(port, audit, provider_budget):
    """Observe real transport only; original response objects stay unchanged."""
    from scripts.assistant_simulation import load_provider
    provider = load_provider(Path(os.environ['BUSINESS_ASSISTANT_CONFIG']))
    endpoint = urlparse(provider.endpoint)
    original_init = httpx.AsyncClient.__init__
    counter = {'calls': 0}
    async def on_request(request):
        if request.url.host == endpoint.hostname and request.url.path == endpoint.path:
            if counter['calls'] >= provider_budget:
                with audit.open('a', encoding='utf-8') as output:
                    output.write(json.dumps({'test_guard': 'provider_budget', 'budget': provider_budget, 'request_sent': False}) + '\n')
                raise httpx.RequestError('Synthetic trial provider budget reached', request=request)
            counter['calls'] += 1
    async def on_response(response):
        if response.request.url.host != endpoint.hostname or response.request.url.path != endpoint.path:
            return
        await response.aread()
        row = {'call': counter['calls'], 'status': response.status_code, 'provider': provider.provider}
        if response.status_code == 200:
            body = response.json()
            row.update(model=body.get('model'), usage=body.get('usage'))
            choices = body.get('choices') or []
            first = choices[0] if choices else {}
            calls = (first.get('message') or {}).get('tool_calls')
            row.update(finish_reason=first.get('finish_reason'), tool_calls_type=type(calls).__name__,
                       tool_call_count=len(calls) if isinstance(calls, list) else None,
                       function_names=[str((call.get('function') or {}).get('name', ''))[:100]
                                       for call in calls[:40] if isinstance(call, dict)] if isinstance(calls, list) else [])
        with audit.open('a', encoding='utf-8') as output:
            output.write(json.dumps(row, ensure_ascii=False) + '\n')
    def audited_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.event_hooks['request'].append(on_request)
        self.event_hooks['response'].append(on_response)
    httpx.AsyncClient.__init__ = audited_init
    import uvicorn
    uvicorn.run('app.main:app', host='127.0.0.1', port=port, log_level='warning')


class EmployeeHTTP:
    def __init__(self, base):
        self.client = httpx.Client(base_url=base, timeout=130, trust_env=False)
    def request(self, path, method='GET', body=None, expected=200):
        headers = {'X-App-Request': '1', 'X-Store-ID': '1'}
        token = self.client.cookies.get('dealer_csrf')
        if token:
            headers['X-CSRF-Token'] = token
        response = self.client.request(method, path, headers=headers, json=body) if body is not None else self.client.request(method, path, headers=headers)
        data = response.json()
        if response.status_code != expected:
            raise AssertionError({'path': path, 'status': response.status_code, 'error': data.get('detail')})
        return data
    def login(self, username, password):
        self.request('/api/auth/login', 'POST', {'username': username, 'password': password})


def exercise(base, password, output, user_message_budget=5):
    admin, employee = EmployeeHTTP(base), EmployeeHTTP(base)
    transcript, checks = [], []
    result = {'mode': 'real remote model + native assistant HTTP', 'synthetic_only': True, 'success': False,
              'transcript': transcript, 'checks': checks, 'user_messages': 0, 'user_message_budget': user_message_budget,
              'preconditions': ['新临时SQLite、附件隔离、随机端口，无原试用数据。',
                  '脚本登录并创建销售账号；随机密码不进入模型或证据。',
                  '助手确认创建接待后，主管通过原生接口将该接待分派给此销售；该步骤明确为准备，不计为模型操作。']}
    try:
        admin.login('admin', password)
        initial, changed = secrets.token_urlsafe(28), secrets.token_urlsafe(28)
        user = admin.request('/api/users', 'POST', {'username': 'remote-assistant-sales', 'display_name': '合成对话销售',
            'role': 'sales', 'password': initial, 'store_roles': [{'store_id': 1, 'role': 'sales'}]}, 201)
        employee.login('remote-assistant-sales', initial)
        employee.request('/api/auth/password', 'POST', {'current_password': initial, 'new_password': changed})
        employee.login('remote-assistant-sales', changed)
        status = employee.request('/api/business-assistant/status')
        if not status.get('ready') or not status.get('synthetic'):
            raise AssertionError('未启用明确的合成测试助手配置。')
        result['assistant_status'] = status
        thread = employee.request('/api/business-assistant/sessions', 'POST', {}, 201)
        sid = thread['id']
        def message(content):
            if result['user_messages'] >= user_message_budget:
                raise AssertionError('已达到本次员工消息上限。')
            result['user_messages'] += 1
            print(json.dumps({'stage': 'send', 'message': result['user_messages']}, ensure_ascii=False), flush=True)
            view = employee.request('/api/business-assistant/sessions/' + sid + '/messages', 'POST',
                                    {'request_id': secrets.token_hex(16), 'content': content})
            transcript.append({'step': result['user_messages'], 'user': content, 'session': view})
            (output / 'conversation.json').write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding='utf-8')
            return view
        def cases():
            return employee.request('/api/flow/cases?kind=lead')['items']
        def confirm(view, operation):
            candidates = [p for p in view['proposals'] if p['status'] == 'pending' and p['operation_id'] == operation]
            if len(candidates) != 1:
                raise AssertionError({'reason': '未出现唯一预期待确认操作', 'operation': operation,
                                      'pending': [{'operation': p['operation_id'], 'summary': p['summary']} for p in view['proposals'] if p['status'] == 'pending']})
            proposal = candidates[0]
            path = '/api/business-assistant/sessions/' + sid + '/proposals/' + proposal['id'] + '/confirm'
            confirmed = employee.request(path, 'POST', {'digest': proposal['digest']})
            done = next(p for p in confirmed['proposals'] if p['id'] == proposal['id'])
            transcript.append({'explicit_employee_confirmation': proposal['summary'], 'result': done})
            if done['status'] != 'succeeded':
                raise AssertionError({'reason': '原生办理没有成功', 'proposal': done})
            again = employee.request(path, 'POST', {'digest': proposal['digest']})
            same = next(p for p in again['proposals'] if p['id'] == proposal['id'])
            assert same['result'] == done['result']
            checks.append('相同待确认操作重复确认返回原结果')
            return done
        first = message('帮我登记一条新客户的售前接待，还没填写资料。')
        assert not cases(), '补充资料和本人确认之前不应创建接待。'
        assert not [p for p in first['proposals'] if p['status'] == 'pending'], '缺姓名来源时不应准备猜测的接待。'
        reply = next((m['content'] for m in reversed(first['messages']) if m['role'] == 'assistant'), '')
        assert '姓名' in reply and '来源' in reply, '首条没有实际追问必要姓名和来源；错误提示不算追问通过。'
        checks.append('缺少姓名和来源时保留问答，未创建接待')
        second = message('这是新客户，按新档案登记。客户叫合成对话客户，今天从展厅到店咨询，关注合成纯电车，暂时没有联系电话。请登记接待。')
        assert not cases(), '确认前不应创建接待。'
        if not [p for p in second['proposals'] if p['status'] == 'pending' and p['operation_id'] == 'POST /api/flow/cases']:
            second = message('确认新建独立客户档案；如果没有匹配记录就按刚才给出的资料建立接待，电话留空。请整理待我确认的操作。')
        created = confirm(second, 'POST /api/flow/cases')
        rows = cases()
        assert len(rows) == 1 and rows[0]['kind'] == 'lead'
        cid = rows[0]['id']
        row = employee.request('/api/flow/cases/' + str(cid))
        assert row['customer']['name'] == '合成对话客户' and not row['customer']['phone']
        checks.append('本人确认后通过原生入口创建唯一无电话接待')
        admin.request('/api/flow/cases/' + str(cid) + '/actions/assign', 'POST',
                      {'request_id': secrets.token_hex(16), 'version': row['version'], 'values': {'assignee_id': user['id']}})
        third = message('主管已把刚才这条接待分派给我。请帮我安排接待回访。')
        row = employee.request('/api/flow/cases/' + str(cid))
        assert row['state'] == 'contacting' and not row['customer']['phone']
        phone_field = next(f for action in row['actions'] if action['key'] == 'remind' for f in action['fields'] if f['key'] == 'customer_phone')
        result['callback_phone_metadata'] = {'required': phone_field['required'], 'label': phone_field['label']}
        assert phone_field['required'] is True
        checks.append('缺电话时尚未登记回访，保留员工补充入口')
        due = str(datetime.now(ZoneInfo('Asia/Shanghai')).date() + timedelta(days=3))
        fourth = message('补充联系电话13900007771，下次处理日期' + due + '，本次沟通结果：已确认意向，三日后回访。请准备安排回访。')
        pending = [p for p in fourth['proposals'] if p['status'] == 'pending' and '/actions/' in p['operation_id']]
        if not pending and result['user_messages'] < user_message_budget:
            fourth = message('上面的电话、日期和沟通结果就是本次资料。请按原接待当前可用的安排接待回访操作，生成待我确认的内容。')
        confirmed = confirm(fourth, 'POST /api/flow/cases/{case_id}/actions/{action}')
        row = employee.request('/api/flow/cases/' + str(cid))
        assert row['state'] == 'reminder' and row['customer']['phone'] == '13900007771'
        assert str(row['due_date']) == due and len(cases()) == 1
        checks.append('本人确认后电话、回访状态、日期通过原生记录核对；仍只有一条接待')
        result['success'] = True
    except Exception as error:
        result['failure'] = str(error)[:9000]
    finally:
        try:
            result['issues'] = employee.request('/api/business-assistant/issues')
        except Exception:
            result['issues'] = {'unavailable': True}
        admin.client.close()
        employee.client.close()
        (output / 'conversation.json').write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-entry', action='store_true')
    parser.add_argument('--port', type=int)
    parser.add_argument('--audit', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--provider-budget', type=int, default=25)
    parser.add_argument('--user-message-budget', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.provider_budget <= 40:
        parser.error('provider-budget必须为1至40。')
    if not 1 <= args.user_message_budget <= 6:
        parser.error('user-message-budget必须为1至6。')
    if args.server_entry:
        server_entry(args.port, args.audit, args.provider_budget)
        return
    if not args.config or not args.output:
        parser.error('需要源码外的--config及--output。')
    from scripts.assistant_simulation import load_provider
    load_provider(args.config)  # Validate destination and private config without printing it.
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error('输出必须在源码之外。')
    output.mkdir(parents=True, exist_ok=True)
    audit = output / 'provider-audit.jsonl'
    if audit.exists():
        parser.error('请使用新的证据目录，保留原有试验。')
    password = secrets.token_urlsafe(28)
    with tempfile.TemporaryDirectory(prefix='huakangos-deepseek-dialogue-') as temp:
        work = Path(temp)
        env = {**os.environ, 'APP_ENV': 'test', 'DATABASE_URL': 'sqlite:///' + (work / 'synthetic.sqlite').as_posix(),
            'ALLOWED_HOSTS': '127.0.0.1,localhost', 'COOKIE_SECURE': 'false', 'SCHEDULER_ENABLED': 'false',
            'SCHEDULER_MODE': 'off', 'FILE_STORAGE_MODE': 'blob', 'PRIVATE_FILE_ROOT': '', 'FILE_SCAN_MODE': 'structure_only',
            'ALLOW_AI_EXTERNAL': 'false', 'DEEPSEEK_API_KEY': '', 'LEGACY_BUSINESS_WRITE': 'false',
            'HUAKANGOS_INITIAL_PASSWORD': password, 'DEALER_INITIAL_PASSWORD': password, 'PYTHONUTF8': '1',
            'BUSINESS_ASSISTANT_CONFIG': str(args.config.resolve())}
        initialized = subprocess.run([sys.executable, '-m', 'app.cli', 'init'], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8')
        if initialized.returncode:
            raise RuntimeError('合成测试库初始化失败：' + initialized.stderr)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        with (work / 'server.log').open('w', encoding='utf-8') as log:
            server = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--server-entry', '--port', str(port), '--audit', str(audit), '--provider-budget', str(args.provider_budget)],
                cwd=ROOT, env=env, stdout=log, stderr=log, creationflags=flags)
            try:
                base = 'http://127.0.0.1:' + str(port)
                with httpx.Client(base_url=base, timeout=2, trust_env=False) as probe:
                    for _ in range(120):
                        if server.poll() is not None:
                            raise RuntimeError('本次隔离服务启动失败。')
                        try:
                            if probe.get('/api/health').status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(.1)
                    else:
                        raise RuntimeError('本次隔离服务启动超时。')
                result = exercise(base, password, output, args.user_message_budget)
                records = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines()] if audit.exists() else []
                result['provider_calls'] = sum(1 for row in records if 'call' in row)
                result['provider_budget'] = args.provider_budget
                result['test_budget_blocked_requests'] = sum(1 for row in records if row.get('test_guard') == 'provider_budget')
                result['models'] = sorted({r.get('model') for r in records if r.get('model')})
                result['usage'] = {key: sum(int((r.get('usage') or {}).get(key, 0)) for r in records) for key in ['prompt_tokens', 'completion_tokens', 'total_tokens']}
                (output / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps({k: v for k, v in result.items() if k != 'transcript'}, ensure_ascii=False, indent=2))
            finally:
                if os.name == 'nt' and server.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(server.pid), '/T', '/F'], capture_output=True, creationflags=flags)
                elif server.poll() is None:
                    server.terminate()
                server.wait(timeout=10)
        if os.name == 'nt':
            for _ in range(50):
                try:
                    os.replace(work / 'server.log', work / 'server.log')
                    break
                except PermissionError:
                    time.sleep(.1)


if __name__ == '__main__':
    main()
