# PATCH-M8-1-OFFLINE-HARNESS-01

2026-09-29；M8.1 保持 `in_progress`。业主授权执行离线与页面验证。本补丁只修**测试执行器**，
不修改任何生产业务源码、断言强度、浏览器安全策略或功能开关。

## 已复现缺陷

1. `run_browser.py` 的端口占用探测只捕获 `httpx.ConnectError`。本机回环探测返回
   `httpx.ConnectTimeout`（`ConnectTimeout` 不是 `ConnectError` 的子类），异常直接抛出，
   fixture/native 浏览器套件在启动夹具服务器之前就失败。此前把这一现象当成
   “本地浏览器不可用”，实际是执行器自身的异常处理缺口。
2. `browser_harness.py` 用 `Path.read_text()` 读取 `web/index.html`、`web/*.js`、`web/*.css`，
   未指定编码，于是使用本机 locale 编码（本机为 GBK）。这些资产是 UTF-8，读取直接抛
   `UnicodeDecodeError`，fixture 模式的“原页面 + 显式传输桥接”整条路径在本机不可执行。
3. `run_validation.py` 读取各步骤 UTF-8 日志时同样未指定编码，非 ASCII 的失败输出会以
   locale 编码解码失败，掩盖真实失败原因。

以上三项都不影响 Ubuntu CI（默认 UTF-8、连接被拒），因此此前只在 Linux CI 上跑通；
它们使本地 Windows 复验得出“浏览器不可用”的错误结论。

## 精确改动范围

- `tests/assistant_offline/run_browser.py`：端口探测与就绪轮询同时接受
  `ConnectError`、`ConnectTimeout`（就绪轮询保留 `ReadTimeout`）。语义不变：任何 HTTP 应答
  仍表示端口被占用并拒绝启动，连接被拒或超时仍表示“没有我们自己的服务在监听”。
- `tests/assistant_offline/browser_harness.py`：`asset_text` 与 `frontend_html` 显式按 UTF-8
  读取资产。
- `tests/assistant_offline/run_validation.py`：步骤日志按 UTF-8 读取。

## 保留的边界

- 不修改 `native` / `fixture` 的传输语义、不新增桥接、不设置 `bypass_csp`、不加 `unsafe-eval`，
  不改变原登录、Cookie、CSRF、CSP 或 SSE 的使用方式。
- 不降低任何断言；不把本地 `fixture` 结果写成原生验收。
- 不改测试选择逻辑：默认仍发现并执行全部已版本化 `test_*.py`；定向 `--suite` 仍标记
  `scope=targeted`、`complete=false`。

## 异常路径

- 夹具服务器真的启动失败：`server.poll()` 非空即抛 `RuntimeError`，保留其日志。
- 端口被无关进程占用：首个请求返回任意 HTTP 应答即拒绝启动，不复用不明实例。
- 资产不是合法 UTF-8：显式 `UnicodeDecodeError` 直接失败，不再被 locale 编码掩盖。
