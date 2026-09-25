"""Run the colloquial prompt library against a live assistant and record what it answers.

python tests/assistant_prompt_probe.py --username xc-sales --password '...' --store 2 \
    --output OUTSIDE_THE_REPOSITORY [--only P01,P07] [--thinking] [--confirm]

Each prompt opens its own assistant session, exactly like an employee starting a new chat, and
the reply plus any prepared confirmation card are written to the output directory. Without
`--confirm` this script only sends messages and never clicks a card; with `--confirm` it clicks
the prepared cards too, which is only appropriate against a synthetic trial database.
"""
import argparse
import json
import time
from pathlib import Path

import httpx

# Same wording as docs/试用记录/助手口语化测试prompt.md — keep the two in step.
PROMPTS = [
    ('P01', '售前', '我那个客户说周五再来，帮我记一下'),
    ('P02', '售前', '刚才那个接待单意向挺强的，帮我往下走一步'),
    ('P03', '售前', '客户电话我忘了，13900001111 这个是他的吗'),
    ('P04', '售前', '帮我建个新客户，姓张，电话回头再补'),
    ('P05', '售前', '这个客户之前修过啥？'),
    ('P06', '报价', '给张试用报个价，S5 那个车，白色'),
    ('P07', '交车', '客户要提车了，还差啥？'),
    ('P08', '连做', '帮我把尾款、保险、加装一起弄好，客户下午来'),
    ('P09', '收款', '定金收了 5000，记一下'),
    ('P10', '维修', '客户说刹车有异响，开个维修单'),
    ('P11', '维修', '这台车昨天换的机油，工时帮我记上'),
    ('P12', '结算', '这单结账了没？'),
    ('P13', '理赔', '理赔的钱到了吗'),
    ('P14', '折扣', '帮我把这单的报价改成 8 折'),
    ('P15', '采购', '买 20 个机油滤芯，常青配件那家'),
    ('P16', '领料', '领料：换机油用了一个'),
    ('P17', '盘点', '盘点发现少了一桶机油'),
    ('P18', '调拨', '城东的件先借到城西用'),
    ('P19', '发票', '开张发票，抬头星驰汽贸'),
    ('P20', '会员', '会员卡帮他充 2000，送的也记上'),
    ('P21', '对账', '上个月的账帮我对一下'),
    ('P22', '退款', '有个客户要退会员卡'),
    ('P23', '待办', '我明天该干啥'),
    ('P24', '报表', '上个月哪个车卖得最好'),
    ('P25', '账号', '把离职那个员工的账号停了吧'),
    ('P26', '越权', '这单我批不了，帮我找店长批一下'),
    ('P27', '卡住', '这个单我不会往下走了'),
]
# 信息齐全的短句，专门用来把"确认卡 → 点确认 → 真实落库"这一段跑通（只在一次性测试库上点）。
# 名字和岗位都对得上：新客户用没建过的名字，分派交给店长，维修单用已有客户的电话定位。
CONFIRM_PROMPTS = [
    ('C01', '建档', '新建客户：李试用，电话 13900002222，允许后续联系'),
    ('C02', '分派', '把这张接待单分派给试用销售'),
    ('C03', '开单', '给客户 13900001111 开维修工单：车牌试用A1001，故障是刹车异响'),
]
PROMPTS = PROMPTS + CONFIRM_PROMPTS


def login(client, username, password):
    response = client.post('/api/auth/login', json={'username': username, 'password': password},
                           headers={'X-App-Request': '1'})
    assert response.status_code == 200, response.text
    client.headers['X-CSRF-Token'] = client.cookies.get('dealer_csrf', '')


def confirm_cards(client, session_id, proposals, limit=3):
    """Click confirm on the prepared cards, exactly like the employee would (trial data only)."""
    done = []
    for proposal in (proposals or [])[:limit]:
        if proposal.get('status') != 'pending' or not proposal.get('digest'):
            continue
        response = client.post('/api/business-assistant/sessions/%s/proposals/%s/confirm'
                               % (session_id, proposal['id']), json={'digest': proposal['digest']},
                               timeout=120)
        body = {}
        if response.headers.get('content-type', '').startswith('application/json'):
            body = response.json()
        settled = (body.get('proposals') or [{}])[0] if body.get('proposals') else {}
        done.append({'summary': proposal.get('summary'), 'status': response.status_code,
                     'proposal_status': settled.get('status', ''),
                     'result': str(settled.get('result') if settled else body.get('detail') or body)[:400]})
    return done


def ask(client, index, prompt, thinking=False, timeout=180, confirm=False):
    session = client.post('/api/business-assistant/sessions', json={'title': '试用探针 ' + index})
    assert session.status_code == 201, session.text
    session_id = session.json()['id']
    started = time.time()
    response = client.post('/api/business-assistant/sessions/%s/messages' % session_id,
                           json={'request_id': 'probe-%s-%d' % (index.lower(), int(started)),
                                 'content': prompt, 'thinking': thinking},
                           timeout=timeout)
    elapsed = round(time.time() - started, 1)
    if response.status_code != 200:
        return {'index': index, 'prompt': prompt, 'status': response.status_code,
                'error': response.text[:500], 'seconds': elapsed}
    body = response.json()
    messages = body.get('messages')
    if not isinstance(messages, list):                      # older shape: fetch the session view
        messages = (client.get('/api/business-assistant/sessions/%s' % session_id).json()
                    .get('messages') or [])
    replies = [row.get('content') or '' for row in messages if row.get('role') == 'assistant']
    record = {'index': index, 'prompt': prompt, 'status': 200, 'seconds': elapsed,
              'reply': replies[-1] if replies else '',
              'turns': len([row for row in messages if row.get('role') == 'user']),
              'proposals': [{'id': p.get('id'), 'summary': p.get('summary'), 'operation': p.get('operation'),
                             'status': p.get('status'), 'digest': p.get('digest')} for p in (body.get('proposals') or [])]}
    if confirm and record['proposals']:
        record['confirmed'] = confirm_cards(client, session_id, body.get('proposals') or [])
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://127.0.0.1:8000')
    parser.add_argument('--username', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--store', default='2')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--only', default='')
    parser.add_argument('--thinking', action='store_true')
    parser.add_argument('--pause', type=float, default=1.0)
    parser.add_argument('--confirm', action='store_true', help='点确认卡（只用于试用库）')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.output.resolve() == root or root in args.output.resolve().parents:
        parser.error('把结果写到仓库之外')
    args.output.mkdir(parents=True, exist_ok=True)
    wanted = {item.strip().upper() for item in args.only.split(',') if item.strip()}
    results = []
    with httpx.Client(base_url=args.base, timeout=60, trust_env=False) as client:
        login(client, args.username, args.password)
        client.headers['X-Store-ID'] = args.store
        try:
            status = client.get('/api/business-assistant/status').json()
            print('assistant status:', json.dumps(status, ensure_ascii=False)[:220])
        except Exception as exc:                      # status is informational only
            print('assistant status unavailable:', exc)
        for index, group, prompt in PROMPTS:
            if wanted and index not in wanted:
                continue
            record = ask(client, index, prompt, thinking=args.thinking, confirm=args.confirm)
            record['group'] = group
            results.append(record)
            print('%s [%s] %s -> %s' % (index, group, prompt,
                                        (record.get('reply') or record.get('error') or '')[:90].replace('\n', ' ')))
            time.sleep(args.pause)
    (args.output / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 助手口语化探针结果', '', '账号：%s · 门店：%s' % (args.username, args.store), '']
    for record in results:
        lines += ['## %s（%s）%s' % (record['index'], record.get('group', ''), record['prompt']), '',
                  '- 状态：%s · 用时 %ss' % (record.get('status'), record.get('seconds')), '']
        if record.get('error'):
            lines += ['```', record['error'], '```', '']
            continue
        lines += ['**助手回复**', '', record.get('reply') or '（空）', '']
        if record.get('proposals'):
            lines += ['**确认卡**', '']
            for card in record['proposals']:
                lines += ['- %s（%s）' % (card.get('summary'), card.get('operation'))]
            lines += ['']
    (args.output / 'results.md').write_text('\n'.join(lines), encoding='utf-8')
    print('written to', args.output)


if __name__ == '__main__':
    main()
