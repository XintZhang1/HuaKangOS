"""全流程试用：把车型清单整表交给业务助手，按批准备确认卡并逐张确认，最后核对车型目录。

python tests/assistant_catalog_import_run.py --output OUTSIDE_THE_REPOSITORY \
    [--xlsx docs/试用记录/比亚迪车型清单_导入用_20260925.xlsx] [--batch 6] [--contact-sheet 20]

一次性实例（自建临时库与端口、本机私有助手配置），不碰预览库与账号。流程与员工在页面上的操作一致：
上传表格 → 助手预览 → 把这一批行发给助手 → 助手逐行准备确认卡 → 脚本逐张点确认 → 回读车型目录核对。
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
from assistant_probe_instance import ADMIN_PASSWORD, FINAL_PASSWORD, create_accounts, login, start  # noqa: E402
from assistant_prompt_probe import confirm_cards                                                      # noqa: E402


def upload(client, path):
    with path.open('rb') as handle:
        return client.post('/api/business-assistant/file-preview',
                           files={'files': (path.name, handle.read(),
                                            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},
                           timeout=180)


def rows_of(preview):
    body = preview.json() if preview.status_code == 200 else {}
    for entry in body.get('files') or []:
        for table in entry.get('tables') or []:
            if '车型' in (table.get('name') or ''):
                return table['columns'], table['rows']
    return [], []


def instruction(columns, rows, index, total):
    lines = ['这是比亚迪车型清单的第 %d 批（共 %d 批）。请**为下面每一行各准备一张车型目录确认卡**，'
             '不要再问确认，直接准备，我逐张点确认。' % (index, total),
             '接口：车型目录新增（POST /api/vehicle-catalog/entry）。字段一一对应，缺一个都会反工：',
             '  brand_name=比亚迪（固定）',
             '  series_name=表里的「车系」列（**必填，车型必须挂到这个车系下**）',
             '  name=表里的「车型」列；model_year=「年款」列',
             '  fuel_type=「动力代码」列（electric / plugin_hybrid）',
             '  seats=「座位数」列；displacement_ml=「排量(ml)」列',
             '  battery_wh=「电池容量(Wh)」列（表里已是 Wh，纯电必须有值）',
             '  guide_price_cents=「指导价(元)」列 × 100（表里是元，接口要分）',
             '不要传编码字段（接口严格模式会拒绝多余字段）；不要传 request_id。',
             '',
             ' | '.join(columns)]
    for row in rows:
        lines.append(' | '.join(value or '' for value in row['values']))
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xlsx', default='docs/试用记录/比亚迪车型清单_导入用_20260925.xlsx')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--batch', type=int, default=6)
    parser.add_argument('--whole', action='store_true',
                        help='整表一次性发（不分批、不换会话），用来看助手能不能一把做完')
    parser.add_argument('--limit', type=int, default=0, help='只处理前 N 行（0=全部）')
    parser.add_argument('--confirm-all', action='store_true',
                        help='用一次“全部确认”（批量接口）办完整组卡，模拟员工在页面上点一次按钮')
    parser.add_argument('--keep-server', action='store_true')
    args = parser.parse_args()
    if args.output.resolve() == ROOT or ROOT in args.output.resolve().parents:
        parser.error('把结果写到仓库之外')
    args.output.mkdir(parents=True, exist_ok=True)
    book = (ROOT / args.xlsx).resolve()
    work = Path(tempfile.mkdtemp(prefix='huakangos-catalog-run-'))
    server, base, log = start(work)
    print('temporary instance:', base, 'work', work, flush=True)
    report = {'xlsx': str(book), 'batches': []}
    try:
        with httpx.Client(base_url=base, timeout=300, trust_env=False) as admin:
            login(admin, 'admin', ADMIN_PASSWORD)
            admin.headers['X-Store-ID'] = '1'
            create_accounts(admin)
        with httpx.Client(base_url=base, timeout=300, trust_env=False) as client:
            login(client, 'probe-stock', FINAL_PASSWORD)      # inventory 岗位可写车型目录
            client.headers['X-Store-ID'] = '1'
            columns, rows = rows_of(upload(client, book))
            if args.limit:
                rows = rows[:args.limit]
            total = (len(rows) + args.batch - 1) // args.batch
            report['rows'] = len(rows)
            print('表格列:', len(columns), '｜待导入行:', len(rows), '｜分批:', total, flush=True)
            if args.whole:
                total = 1

            def catalog_total():
                body = client.get('/api/vehicle-catalog', timeout=120).json()
                return body.get('total') or 0

            for index in range(1, total + 1):
                chunk = rows if args.whole else rows[(index - 1) * args.batch:index * args.batch]
                content = instruction(columns, chunk, index, total)
                batch = {'index': index, 'rows': [row['values'][0] for row in chunk],
                         'status': None, 'cards': [], 'confirmed': [], 'retries': 0}
                report['batches'].append(batch)
                before = catalog_total()
                # 只重试一种情况：模型**一张卡都没准备**却声称准备好了（试用实测过的"只说不做"）。
                # 卡准备好了但被系统按业务规则拒绝（例如纯电缺电池容量 422）不算失败，不去逼模型重来，
                # 报告里原样列出即可——那正是我们要它如实汇报的行为。
                for attempt in (1, 2):
                    # 每一批开一个新会话：长会话里模型会把前面批次的行再准备一遍（试用实测），
                    # 新会话没有这段历史，只按本批内容办。
                    session = client.post('/api/business-assistant/sessions',
                                          json={'title': '车型清单第 %d 批' % index}).json()
                    text = content if attempt == 1 else (
                        content + '\n\n注意：上一轮你说准备好了，但系统里没有任何待确认卡、车型目录条数也没有增加。'
                                  '请**逐行真的调用准备操作**；被系统拒绝的行，把原因原样告诉我。')
                    reply = client.post('/api/business-assistant/sessions/%s/messages' % session['id'],
                                        json={'request_id': 'catalog-run-20260925-%03d-%d' % (index, attempt),
                                              'content': text, 'thinking': False}, timeout=600)
                    batch['status'] = reply.status_code
                    if reply.status_code != 200:
                        batch['error'] = reply.text[:300]
                        break
                    answer = reply.json()
                    messages = answer.get('messages') or []
                    replies = [row.get('content') or '' for row in messages if row.get('role') == 'assistant']
                    batch['reply'] = replies[-1] if replies else ''
                    view = client.get('/api/business-assistant/sessions/%s' % session['id'],
                                      timeout=120).json()
                    pending = [card for card in (view.get('proposals') or [])
                               if card.get('status') == 'pending']
                    if len(pending) > len(batch['cards']):
                        batch['cards'] = [{'summary': p.get('summary'), 'operation': p.get('operation')}
                                          for p in pending]
                    # --confirm-all：像员工在页面上点一次“全部确认”那样，一条请求办完整组卡
                    # （服务端仍逐张校验、逐张调原接口）。默认仍逐张点，保留两种证据。
                    if args.confirm_all and pending:
                        payload = {'action': 'confirm',
                                   'items': [{'id': card['id'], 'digest': card['digest']} for card in pending]}
                        posted = client.post('/api/business-assistant/sessions/%s/proposals/batch' % session['id'],
                                             json=payload, timeout=600)
                        batch['batch_status'] = posted.status_code
                        if posted.status_code == 200:
                            answer = posted.json()
                            batch['batch'] = answer.get('batch')
                            confirmed = [{'summary': item.get('summary'), 'status': 200,
                                          'proposal_status': item.get('status'),
                                          'result': str(item.get('message'))[:200]}
                                         for item in (answer.get('batch') or {}).get('items', [])]
                        else:
                            batch['batch_error'] = posted.text[:300]
                            confirmed = []
                    else:
                        confirmed = confirm_cards(client, session['id'], pending, limit=len(pending) or 1)
                    batch['confirmed'].extend(confirmed)
                    created = catalog_total() - before
                    batch['created'] = created
                    if pending or attempt == 2:
                        break
                    batch['retries'] = attempt
                    print('    批 %d 第 %d 次一张卡都没准备，换新会话重试一次' % (index, attempt), flush=True)
                # 同一张卡可能被确认两次（重试那一轮重发了同样的行），统计按车型名称去重，
                # 避免"确认成功 165 张"这种看着比表格行数还多的假数字。
                unique = {}
                for item in batch['confirmed']:
                    unique.setdefault(item.get('summary'), item)
                ok = sum(1 for item in unique.values() if item.get('proposal_status') == 'succeeded')
                print('批 %d：卡 %d 张，确认成功 %d 张，未成功 %d 张，目录新增 %s 条%s'
                      % (index, len(batch['cards']), ok, len(unique) - ok, batch.get('created'),
                         '（重试 %d 次）' % batch['retries'] if batch['retries'] else ''), flush=True)
                if batch.get('batch'):
                    summary = batch['batch']
                    print('   一次“全部确认”：%s/%s 张办成（一条请求）'
                          % (summary.get('done'), summary.get('total')), flush=True)
                for item in unique.values():
                    if item.get('proposal_status') != 'succeeded':
                        print('   未成功:', item.get('summary'), str(item.get('result'))[:140], flush=True)
            catalog = client.get('/api/vehicle-catalog', timeout=120)
            if catalog.status_code == 200:
                body = catalog.json()
                report['catalog'] = {'brands': [b.get('name') for b in (body.get('brands') or [])],
                                     'series': [s.get('name') for s in (body.get('series') or [])],
                                     'total': body.get('total'), 'unclassified_total': body.get('unclassified_total'),
                                     'items': [{'name': i.get('name'), 'series': i.get('series_name'),
                                                'year': i.get('model_year'), 'fuel': i.get('fuel_type'),
                                                'battery_wh': i.get('battery_wh'),
                                                'price_cents': i.get('guide_price_cents')}
                                               for i in (body.get('items') or [])]}
                print('目录：品牌 %s ｜车系 %s ｜车型合计 %s ｜待确认归属 %s'
                      % (report['catalog']['brands'], len(report['catalog']['series']),
                         report['catalog']['total'], report['catalog']['unclassified_total']), flush=True)
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
    (args.output / 'catalog-run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('written to', args.output, flush=True)


if __name__ == '__main__':
    main()
