"""试用：把"比亚迪车型清单.xlsx"交给业务助手，看它能不能按表建车型目录。

python tests/assistant_model_import_probe.py --xlsx docs/试用记录/比亚迪车型清单_导入用_20260925.xlsx \
    --output OUTSIDE_THE_REPOSITORY [--rows 12] [--confirm]

在一次性实例上跑：自建临时库与端口，用本机私有助手配置（不碰预览库与账号）。
流程与员工在页面上的操作一致：上传表格 → 助手预览 → 把选中的行发给助手 → 看它准备什么。
--confirm 才会点确认卡；默认只看它准备什么。
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from assistant_probe_instance import (ADMIN_PASSWORD, FINAL_PASSWORD, create_accounts, environment,  # noqa: E402
                                      free_port, login, start)
from assistant_prompt_probe import confirm_cards                                                  # noqa: E402


def upload(client, path):
    # The endpoint parses multipart itself and only accepts the field name `files`
    # with a filename (it never accepts a server path).
    with path.open('rb') as handle:
        response = client.post('/api/business-assistant/file-preview',
                               files={'files': (path.name, handle.read(),
                                                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
                               timeout=180)
    return response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xlsx', default='docs/试用记录/比亚迪车型清单_导入用_20260925.xlsx')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rows', type=int, default=12)
    parser.add_argument('--confirm', action='store_true')
    parser.add_argument('--follow-up', default='', help='第二句话：回答助手提出的问题并让它开始建')
    parser.add_argument('--keep-server', action='store_true')
    args = parser.parse_args()
    if args.output.resolve() == ROOT or ROOT in args.output.resolve().parents:
        parser.error('把结果写到仓库之外')
    args.output.mkdir(parents=True, exist_ok=True)
    book = (ROOT / args.xlsx).resolve()
    assert book.is_file(), book
    work = Path(tempfile.mkdtemp(prefix='huakangos-model-import-'))
    server, base, log = start(work)
    print('temporary instance:', base, 'work', work, flush=True)
    record = {'xlsx': str(book), 'size': book.stat().st_size}
    try:
        with httpx.Client(base_url=base, timeout=180, trust_env=False) as admin:
            login(admin, 'admin', ADMIN_PASSWORD)
            admin.headers['X-Store-ID'] = '1'
            create_accounts(admin)
        with httpx.Client(base_url=base, timeout=180, trust_env=False) as client:
            login(client, 'probe-stock', FINAL_PASSWORD)      # inventory 岗位可写车型目录
            client.headers['X-Store-ID'] = '1'
            preview = upload(client, book)
            record['file_preview_status'] = preview.status_code
            body = preview.json() if preview.status_code == 200 else {}
            files = body.get('files') or []
            tables = [table for entry in files for table in (entry.get('tables') or [])]
            record['files'] = [{'name': entry.get('name'), 'kind': entry.get('kind'),
                                'error': entry.get('error'), 'tables': len(entry.get('tables') or []),
                                'warnings': (entry.get('warnings') or [])[:3]} for entry in files]
            record['tables'] = [{'name': t.get('name'), 'columns': t.get('columns'),
                                 'rows': len(t.get('rows') or [])} for t in tables]
            print('file-preview:', preview.status_code, record['tables'], flush=True)
            main_table = next((t for t in tables if (t.get('rows') or [])), None)
            if main_table is None:
                record['error'] = '助手没有解析出表格'
            else:
                header = main_table['columns']
                picked = [row['values'] for row in main_table['rows'][:args.rows]]
                lines = [' | '.join(header)]
                lines += [' | '.join(value or '' for value in row) for row in picked]
                prompt = ('这是比亚迪车型清单（共 %d 行，先发前 %d 行）。请按"品牌→车系→车型"建立车型目录：'
                          '先告诉我你打算怎么建（会建哪些车系、要不要分批、缺哪些字段），先不要一条条准备确认卡。\n\n'
                          % (len(main_table['rows']), len(picked))) + '\n'.join(lines)
                session = client.post('/api/business-assistant/sessions',
                                      json={'title': '车型清单导入试用'}).json()
                started = client.post('/api/business-assistant/sessions/%s/messages' % session['id'],
                                      json={'request_id': 'model-import-probe-0001', 'content': prompt,
                                            'thinking': False}, timeout=300)
                record['message_status'] = started.status_code
                if started.status_code == 200:
                    answer = started.json()
                    messages = answer.get('messages') or []
                    replies = [row.get('content') or '' for row in messages if row.get('role') == 'assistant']
                    record['reply'] = replies[-1] if replies else ''
                    record['proposals'] = [{'id': p.get('id'), 'summary': p.get('summary'),
                                            'status': p.get('status'), 'digest': p.get('digest')}
                                           for p in (answer.get('proposals') or [])]
                    if args.follow_up:
                        second = client.post('/api/business-assistant/sessions/%s/messages' % session['id'],
                                             json={'request_id': 'model-import-probe-0002',
                                                   'content': args.follow_up, 'thinking': False}, timeout=300)
                        record['follow_up_status'] = second.status_code
                        if second.status_code == 200:
                            answer = second.json()
                            messages = answer.get('messages') or []
                            replies = [row.get('content') or '' for row in messages
                                       if row.get('role') == 'assistant']
                            record['reply_after_follow_up'] = replies[-1] if replies else ''
                            record['proposals'] = [{'id': p.get('id'), 'summary': p.get('summary'),
                                                    'status': p.get('status'), 'digest': p.get('digest')}
                                                   for p in (answer.get('proposals') or [])]
                        else:
                            record['follow_up_error'] = second.text[:400]
                    if args.confirm and record['proposals']:
                        record['confirmed'] = confirm_cards(client, session['id'],
                                                            answer.get('proposals') or [], limit=12)
                    catalog = client.get('/api/vehicle-catalog')
                    if catalog.status_code == 200:
                        body = catalog.json()
                        record['catalog_after'] = {
                            'brands': body.get('brands') or body.get('items') or [],
                            'series': body.get('series') or [],
                            'models': len(body.get('models') or []) if isinstance(body.get('models'), list) else None,
                            'keys': sorted(body)[:12]}
                else:
                    record['error'] = started.text[:400]
                print('reply:', (record.get('reply') or record.get('error') or '')[:400].replace('\n', ' '), flush=True)
    finally:
        if args.keep_server:
            print('server kept at', base, flush=True)
        else:
            server.terminate()
            try:
                server.wait(timeout=15)
            except Exception:
                server.kill()
            log.close()
    (args.output / 'model-import.json').write_text(json.dumps(record, ensure_ascii=False, indent=2),
                                                   encoding='utf-8')
    print('written to', args.output, flush=True)


if __name__ == '__main__':
    main()
