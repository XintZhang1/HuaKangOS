#!/usr/bin/env python3
"""Explicit local login for one native user/store; no model API key, no admin shortcut."""
from __future__ import annotations
import getpass
import json
import os
from pathlib import Path
import sys
import httpx
from huakangos_mcp import validate_url,ROOT


def main():
    print('HuaKangOS MCP 本地登录配置（普通账号权限，登录密码不会保存）')
    print('请先启动独立测试系统；不要把测试工具连接到公司正式库。')
    base=validate_url(input('系统地址（例如 http://127.0.0.1:8000）：').strip())
    username=input('员工登录名：').strip();password=getpass.getpass('登录密码（隐藏输入）：')
    with httpx.Client(base_url=base,timeout=30,follow_redirects=False,trust_env=False) as client:
        login=client.post('/api/auth/login',headers={'X-App-Request':'1'},json={'username':username,'password':password})
        password=''
        if login.status_code!=200:raise RuntimeError('登录失败，请到原系统核对账号或修改初始密码。')
        data=login.json()
        if data.get('must_change_password') or data.get('user',{}).get('must_change_password'):
            raise RuntimeError('请先在原系统修改初始密码，再配置MCP。')
        # Native authorization will validate the selected store, do not assume membership.
        store=int(input('当前测试门店编号（与页面所选一致）：').strip())
        csrf=client.cookies.get('dealer_csrf');cookie=client.cookies.get('dealer_session')
        if not csrf or not cookie:raise RuntimeError('未取得有效登录会话。')
        client.headers.update({'X-CSRF-Token':csrf,'X-Store-ID':str(store),'X-App-Request':'1'})
        created=client.post('/api/business-assistant/sessions',json={'title':'MCP业务工具独立对话'})
        if created.status_code!=201:raise RuntimeError('当前账号不能在所选门店创建对话；配置未写入。')
        sid=created.json()['id']
        config={'base_url':base,'session_cookie':cookie,'csrf_token':csrf,'store_id':store,'assistant_session_id':sid}
        folder=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.config')))/'huakangos-mcp'
        folder.mkdir(mode=0o700,parents=True,exist_ok=True)
        path=(folder/'session.json').resolve()
        if path.is_relative_to(ROOT):raise RuntimeError('私密配置不能位于项目内。')
        temporary=folder/'session.json.new'
        # Private mode before writing, not chmod after exposing the token.
        descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            with os.fdopen(descriptor,'w',encoding='utf-8') as out:json.dump(config,out,ensure_ascii=False)
            os.replace(temporary,path)
        finally:
            if temporary.exists():temporary.unlink()
        print('配置已写入本机私密目录。请勿上传、截图或提交该文件。')
        print('会话过期后重新运行本脚本；不会保存密码或自动重新登录。')
        print('MCP客户端配置（这里只含路径，不含凭据）：')
        print(json.dumps({'mcpServers':{'huakangos':{'command':sys.executable,
            'args':[str(ROOT/'scripts'/'huakangos_mcp.py')],
            'env':{'HUAKANGOS_MCP_CONFIG':str(path)}}}},ensure_ascii=False,indent=2))
        print('同一员工在HuaKangOS业务助手历史中打开“MCP业务工具独立对话”核对草稿。')
        print('登录凭据具备该员工原有权限，请只在可信本机客户端启用，不向其他人共享。')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,RuntimeError,httpx.HTTPError) as exc:
        print('配置未完成：请检查系统地址、登录权限和本机目录；不会打印凭据。',file=sys.stderr)
        raise SystemExit(1)
