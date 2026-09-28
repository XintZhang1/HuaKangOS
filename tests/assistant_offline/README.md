# 业务助手离线回归

测试源码随 Git 版本化，执行时先复制到仓库外**全新目录**。不要在此目录直接运行 unittest，也不要把生产/预览配置、数据或 `.env` 放进被测源码。入口在导入 app 之前验证路径、生成显式合成环境；不清理或重用旧证据。

## 运行

在独立虚拟环境安装根 `requirements.txt` 的固定版本；前端行为测试另需 Node.js。原生浏览器测试另需 `playwright==1.57.0` 及其 Chromium（`python -m playwright install --with-deps chromium`）。

```bash
# 后端、协议、前端行为；不宣称浏览器已测试。
python tests/assistant_offline/run_isolated.py --browser-mode off

# 原生 Chromium：真实导航、Cookie、fetch 和网络 SSE。
python tests/assistant_offline/run_isolated.py --browser-mode native

# 仅在浏览器网络受限的环境中，显式使用桥接夹具。
python tests/assistant_offline/run_isolated.py --browser-mode fixture
```

可用 `--source /absolute/source` 指定被测源码，`--output /absolute/new/external/path` 指定不存在的外部验证目录。默认创建唯一临时目录并保留结果。`HUAKANGOS_CHROMIUM` 可明确指定浏览器可执行文件。已有 8765 端口服务会导致浏览器测试拒绝启动，不复用不明实例。

`evidence/run-summary.json` 记录实际命令、退出码、非零测试数、浏览器模式；`source-and-suite.json` 记录逐文件与汇总指纹。任何失败都保留日志，不以删测试、调整业务规则或降级浏览器模式求绿。`runtime/` 含测试随机密码和合成库，禁止提交或上传；CI 只上传 evidence。

## 覆盖内容

定向覆盖：真实登录及门店权限、工具协议拒绝、持久 Run、租约与取消、人工确认及未知结果不重放；两步计划依赖、显式跟进授权、退出/暂停/撤权、原接待事实；重复唤醒、发件箱事务恢复和私有通知；原批量接口首项失败即停；完整前端模块与页面实操、移动端布局和上下文竞态。

模型响应是确定性合成内容，不使用真实 DeepSeek；原业务 API、状态、数据库与事务不是桩。原生浏览器测试与 fixture 测试分别记录，后者不证明原生 Cookie/CSP/网络 SSE。全套定向通过仍不代表原 101/283 模型场景、193 项需求、全部业务族、PostgreSQL、Windows、指定 MCP 客户端及员工试用已经验收。
