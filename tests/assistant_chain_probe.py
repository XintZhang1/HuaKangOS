"""真实模型试："章先生看完车要直接订车，把流程补上再打印订单合同"。

业主 2026-09-25 明确要的"连续批量确认"：员工说的是中间/最后一步，助手要在**同一轮**里
把整条前序链按步骤准备好（分组卡片），而不是一步一轮地中断对话。这个脚本用一次性实例
（自建库与端口，不碰预览库）跑真实模型，打印它准备了几步、每步几张，以及确认后下一轮的结果。

python tests/assistant_chain_probe.py --output OUTSIDE_THE_REPOSITORY [--confirm] [--rounds 2]
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
from assistant_probe_instance import (ADMIN_PASSWORD, FINAL_PASSWORD, create_accounts, login,  # noqa: E402
                                      start)

DEFAULT_PROMPT = '章先生今天看完车，想直接订车。你帮我把流程补上，最后打印订单合同。'
# 一次性实例的车型目录默认是空的，没有车型就没法报价、下单。这里按员工真实入口建一条
# 合成车型（值取自公开参数页的宋PLUS DM-i），让"整条链一次准备"这件事能被真实验证。
SEED_MODEL = {'brand_name': '比亚迪', 'series_name': '宋PLUS', 'name': '宋PLUS DM-i 110km 旗舰型',
              'model_year': 2026, 'fuel_type': 'plugin_hybrid', 'seats': 5,
              'displacement_ml': 1498, 'battery_wh': 18300, 'guide_price_cents': 1680000}


def seed_vehicle(client):
    response = client.post('/api/vehicle-catalog/entry', json={'request_id': 'chain-seed-20260925-0001', **SEED_MODEL},
                           headers={'X-App-Request': '1', 'X-Store-ID': '1',
                                    'X-CSRF-Token': client.cookies.get('dealer_csrf', '')}, timeout=120)
    print('seed vehicle:', response.status_code, str(response.text)[:160], flush=True)
    return response.status_code in {200, 201}


def describe(session):
    steps, last = [], None
    for card in session.get('proposals') or []:
        key = (int(card.get('step_order') or 0), card.get('step') or '未标步骤')
        if key != last:
            steps.append((key, []))
            last = key
        steps[-1][1].append(card)
    return steps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prompt', default=DEFAULT_PROMPT)
    parser.add_argument('--rounds', type=int, default=1, help='确认之后自动"继续"追几轮')
    parser.add_argument('--confirm', action='store_true', help='真的点确认（测试期由业主授权）')
    parser.add_argument('--no-seed-vehicle', action='store_true', help='不预置车型，观察它对缺资料的如实说明')
    args = parser.parse_args()
    if args.output.resolve() == ROOT or ROOT in args.output.resolve().parents:
        parser.error('把结果写到仓库之外')
    args.output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='huakangos-chain-run-'))
    server, base, log = start(work)
    print('temporary instance:', base, 'work', work, flush=True)
    report = {'prompt': args.prompt, 'rounds': []}
    try:
        with httpx.Client(base_url=base, timeout=300, trust_env=False) as admin:
            login(admin, 'admin', ADMIN_PASSWORD)
            admin.headers['X-Store-ID'] = '1'
            create_accounts(admin)
    except Exception as exc:                                    # 账号已存在等不影响本轮
        print('准备账号时提示：', exc, flush=True)
    if not args.no_seed_vehicle:
        try:
            with httpx.Client(base_url=base, timeout=300, trust_env=False) as stock:
                login(stock, 'probe-stock', FINAL_PASSWORD)
                stock.headers['X-Store-ID'] = '1'
                report['seed_vehicle'] = seed_vehicle(stock)
        except Exception as exc:
            print('预置车型失败：', exc, flush=True)
    try:
        with httpx.Client(base_url=base, timeout=600, trust_env=False) as client:
            login(client, 'admin', ADMIN_PASSWORD)
            client.headers['X-Store-ID'] = '1'
            session = client.post('/api/business-assistant/sessions', json={'title': '连带办理试跑'}).json()
            content = args.prompt
            for index in range(1, args.rounds + 2):
                reply = client.post('/api/business-assistant/sessions/%s/messages' % session['id'],
                                    json={'request_id': 'chain-20260925-%02d-%d' % (index, len(content)),
                                          'content': content, 'thinking': False}, timeout=900)
                assert reply.status_code == 200, reply.text
                view = client.get('/api/business-assistant/sessions/%s' % session['id'], timeout=120).json()
                answers = [row.get('content') or '' for row in (view.get('messages') or []) if row.get('role') == 'assistant']
                steps = describe(view)
                entry = {'round': index, 'sent': content[:160], 'answer': answers[-1] if answers else '',
                         'steps': [{'order': key[0], 'step': key[1], 'cards': len(cards),
                                    'labels': [card.get('label') for card in cards]} for key, cards in steps]}
                report['rounds'].append(entry)
                print('\n== 第 %d 轮 ==' % index, flush=True)
                print('我：', content[:200], flush=True)
                print('助手：', entry['answer'][:700], flush=True)
                for key, cards in steps:
                    print('   第 %s 步 %s：%d 张 -> %s' % (key[0] or '-', key[1], len(cards),
                                                          '；'.join(card.get('label') or '' for card in cards)), flush=True)
                if args.confirm:
                    pending = [card for card in (view.get('proposals') or []) if card.get('status') == 'pending']
                    if pending:
                        posted = client.post('/api/business-assistant/sessions/%s/proposals/batch' % session['id'],
                                             json={'action': 'confirm',
                                                   'items': [{'id': card['id'], 'digest': card['digest']} for card in pending]},
                                             timeout=600)
                        assert posted.status_code == 200, posted.text
                        batch = posted.json().get('batch') or {}
                        failed = [item for item in batch.get('items', []) if item.get('status') not in {'succeeded', 'cancelled'}]
                        entry['confirmed'] = {'total': batch.get('total'), 'done': batch.get('done'), 'failed': failed}
                        print('   一次“按顺序全部确认”：%s/%s 张办成%s'
                              % (batch.get('done'), batch.get('total'),
                                 '' if not failed else '；未办成：' + json.dumps(failed, ensure_ascii=False)[:400]), flush=True)
                if index > args.rounds:
                    break
                content = '继续处理下一步'
            report['catalog'] = client.get('/api/vehicle-catalog', timeout=60).json().get('total')
    finally:
        (args.output / 'chain-run.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('\nwritten to', args.output, flush=True)
        server.terminate()


if __name__ == '__main__':
    main()
