"""Local and remote setup checks. --send-test sends one non-actionable bot card.

This never calls DeepSeek and never publishes anything. It answers one question:
"if an opinion arrived right now, could the pipeline actually run?"
"""
import argparse
import importlib.util
import json
from pathlib import Path
from .config import MaintenanceConfig, GateError, preflight
from .gitops import Repository, tree_matches
from .feishu import FeishuBot
from .transport import BuilderClient, NotNow
from .window import quant_state, window_state
from app.config import ROOT


def _local_window(cfg):
    state=window_state(cfg)
    print('本机维护窗口：%s %s' % ('开放' if state.open else '关闭', state.reason or ('剩余 %d 分钟' % state.minutes_left)))
    if not state.open and state.wait_hint(): print('            '+state.wait_hint())
    quant=quant_state(cfg.quant_units)
    print('本机量化让行：%s %s' % ('空闲' if quant.ok else '让行中', quant.reason()))


def _split_checks(cfg):
    remote=BuilderClient(cfg)
    status=remote.status()
    print('构建机：%s（docker %s，磁盘余量 %sGB，请求来源 %s）'
          % (status.get('host') or '?', status.get('docker') or '未知',
             status.get('disk_free_gb'), status.get('request_from') or '?'))
    window=status.get('window') or {}
    print('构建窗口：%s %s' % ('开放' if window.get('open') else '关闭', window.get('reason') or ''))
    quant=status.get('quant') or {}
    busy=list(quant.get('busy') or [])
    print('量化让行：%s %s' % ('空闲' if not busy and not quant.get('unknown') else '让行中（'+', '.join(busy)+'）',
                              quant.get('reason') or ''))
    image=status.get('test_image') or {}
    if not image.get('usable'):
        raise GateError('构建机隔离测试镜像不可用：'+str(image.get('detail') or '未知原因'))
    print('隔离测试镜像：%s 就绪（基线标签 %s）' % (image.get('tag'), image.get('trusted_label') or '未标注'))
    main_sha=status.get('main_sha') or ''
    if not main_sha:
        raise GateError('无法从构建机确认远程主分支；请先完成仓库克隆与 deploy key')
    pointer=cfg.runtime/'active.json'
    active=json.loads(pointer.read_text(encoding='utf-8')) if pointer.exists() else {}
    recorded=active.get('sha')
    if recorded in (None,'local'):
        print('运行版本指针：尚未绑定（首次发布时会绑定到 %s）' % main_sha[:12])
    elif recorded!=main_sha:
        raise GateError('本机记录的运行版本 %s 与远程主分支 %s 不一致；请人工核对后再启用'
                        % (str(recorded)[:12], main_sha[:12]))
    else:
        print('Git 主分支与运行版本：一致（%s）' % main_sha[:12])
    return status


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--send-test',action='store_true')
    args=parser.parse_args();cfg=MaintenanceConfig()
    try:
        cfg.validate();print('配置字段：通过（不显示密钥）')
        preflight(cfg)
        print('本机依赖：就绪（%s）' % ('docker 可用，应用以容器运行' if cfg.split else '飞书 SDK 与隔离测试镜像就绪'))
        _local_window(cfg)
        if cfg.split:
            _split_checks(cfg)
        else:
            repo=Repository(cfg);base=repo.sync()
            pointer=cfg.runtime/'active.json'
            active=json.loads(pointer.read_text(encoding='utf-8')) if pointer.exists() else {'sha':base,'path':str(ROOT)}
            if active['sha']=='local':active['sha']=base
            if base!=active['sha'] or not tree_matches(repo,base,Path(active['path'])):
                raise GateError('当前运行代码与远程主分支不同；自动维护不会越过这个检查')
            print('Git 读取与运行基线：一致（这不能代替远端写权限验收）')
        if args.send_test:
            FeishuBot(cfg).send({'header':{'title':{'tag':'plain_text','content':'DealerDesk · 接线测试'}},
                'elements':[{'tag':'div','text':{'tag':'plain_text','content':'飞书应用机器人发送成功。这条消息没有审批按钮，不会修改代码或数据库。请继续完成真实反馈的测试、审批与回滚验收。'}}]},'dealerdesk-setup-test')
            print('飞书测试消息：已发送；长连接审批回调仍需实际点击卡片验收')
        print('DeepSeek 未调用；代码生成、容器实际测试和真实审批尚须完整验收。')
        return 0
    except NotNow as exc:
        print('检查未通过：构建机当前让行（'+str(exc)+'）；这不是故障，请在维护时段内重试');return 1
    except (GateError,OSError,ValueError,KeyError) as exc:
        print('检查未通过：'+(str(exc) if isinstance(exc,GateError) else '本地状态文件无效，请核对配置'))
        return 1


if __name__=='__main__':raise SystemExit(main())