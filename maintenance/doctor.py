"""Local setup checks. --send-test explicitly sends one non-actionable bot card."""
import argparse
import importlib.util
import json
from .config import MaintenanceConfig, GateError, preflight
from .gitops import Repository, tree_matches
from .feishu import FeishuBot
from app.config import ROOT


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--send-test',action='store_true')
    args=parser.parse_args();cfg=MaintenanceConfig()
    try:
        cfg.validate();print('配置字段：通过（不显示密钥）')
        preflight(cfg);print('飞书SDK与隔离测试镜像：就绪')
        repo=Repository(cfg);base=repo.sync()
        pointer=cfg.runtime/'active.json'
        active=json.loads(pointer.read_text(encoding='utf-8')) if pointer.exists() else {'sha':base,'path':str(ROOT)}
        if active['sha']=='local':active['sha']=base
        from pathlib import Path
        if base!=active['sha'] or not tree_matches(repo,base,Path(active['path'])):
            raise GateError('当前运行代码与远程主分支不同；自动维护不会越过这个检查')
        print('Git 读取与运行基线：一致（这不能代替远端写权限验收）')
        if args.send_test:
            FeishuBot(cfg).send({'header':{'title':{'tag':'plain_text','content':'DealerDesk · 接线测试'}},
                'elements':[{'tag':'div','text':{'tag':'plain_text','content':'飞书应用机器人发送成功。这条消息没有审批按钮，不会修改代码或数据库。请继续完成真实反馈的测试、审批与回滚验收。'}}]},'dealerdesk-setup-test')
            print('飞书测试消息：已发送；长连接审批回调仍需实际点击卡片验收')
        print('DeepSeek 未调用；代码生成、容器实际测试和真实审批尚须完整验收。')
        return 0
    except (GateError,OSError,ValueError,KeyError) as exc:
        print('检查未通过：'+(str(exc) if isinstance(exc,GateError) else '本地状态文件无效，请核对配置'))
        return 1

if __name__=='__main__':raise SystemExit(main())
