# PATCH-M8-1-WIRING-01 · 接线、异常终止与并发登录

本次业主明确授权继续实现、隔离测试、模拟模型响应和页面实操。基点为 feature 的 `8c9641d24ba207ee2d49fe4efea69d652c23ae0d`，另含语法 CI 提交 `a293a92ae76073a97dc75511d48683be9c0fe34d`。不修改总计划、业务规则、迁移、默认开关或原用户数据。

## 精确范围与已复现缺陷

- `web/businessassistant.js`：同步 HTML 渲染不得返回 Promise；欢迎目录异步加载与同步呈现分离，保留当前岗位和门店过滤；终态消息/卡片必须读回后再结束订阅；确认后的原会话不得被旧 Run 卡片缓存覆盖；离页、重新进入、换会话与迟到响应保持上下文隔离；无法读取功能合同不能擅自改走 legacy 再执行。
- `web/assistantruntime.js`：补齐终态聚合回读和会话身份核对，详情见 CLIENT-01。
- `web/assistantworkspace.js` / `.css`：输入区和卡片栏的高度、移动端原标签按钮与实际 DOM 对齐，确认按钮不得裁切；删除两段空白区重复解释，不增加操作流程说明、自动发送或业务持久化。
- `app/assistant_runtime_provider.py` / `app/assistant_runtime_runner.py`：给畸形/不完整模型协议单独错误类型，Runtime 终止本次准备而非当网络故障再次排队。原传输重试、完整批次校验和人工确认边界保留；已有有效卡片不补造、不回滚。
- `app/security.py`：真实浏览器回归遇到 worker 并发期间登录偶发 503。用两个独立 SQLite 连接在真实密码校验期间提交，稳定复现 `SQLITE_BUSY_SNAPSHOT`（517），而非猜测超时。仅对该精确错误，在发放会话前回滚并重新核对密码、账号和失败次数一次；第二次冲突原样失败。一般连接异常、PostgreSQL、原业务提交和未知写入结果不重试。
- 当前 M8.1 执行记录与独立检查点；测试及完整证据仍放仓库外。

## 异常路径与验收边界

模型重复 tool ID、半截 JSON、同回复一好一坏调用：整段不准备；退出或取消后的回复不得泄露。登录重试必须重新看到账号停用，错误密码只计一次失败，持续冲突不设 Cookie、不追加会话或登录成功日志。页面功能合同读取失败保留草稿，不切换协议发第二次请求。

上述行为已纳入完整模块行为测试、真实 HTTP / SQLite / worker 集成，以及 Chromium 控件测试。浏览器导航被当前环境阻止，Chromium 使用显式 HTTP/Cookie 桥接夹具；不得将其计作 M8.4 原生浏览器同源验收。完整结果和未验收范围见 `docs/implementation-checkpoints/M8-1-offline-runtime-checkpoint-v1.md`。
