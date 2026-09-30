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

## 真实浏览器流水线（M8.4 单一入口）

`run_browser_pipeline.py` 是同一条真实浏览器验收的一键入口：预检 → 全新外部目录 → 原生运行 → 核对证据。它**不会**把原生失败改跑 `fixture` 求绿，也不会改写已有证据目录。

```bash
python tests/assistant_offline/run_browser_pipeline.py --browser-mode native
# 显式指定浏览器（未指定时按 HUAKANGOS_CHROMIUM → 常见 Chrome/Chromium 路径 → Playwright 自带）
python tests/assistant_offline/run_browser_pipeline.py --browser-mode native \
  --browser "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

浏览器解析顺序为「`--browser` 显式参数 → `HUAKANGOS_CHROMIUM` → **Playwright 固定版本自带浏览器** →
主机常见候选」，并把来源记入 `browser_source`（`explicit`/`environment`/`playwright-bundled`/
`system-candidate`）。固定版本的自带浏览器优先于主机自带候选，避免 CI 镜像里的系统 Chromium 悄悄
替换掉该步骤刚安装的那个。

退出码：`0` 已核对；`2` 预检拒绝（源码带 `.env`、输出在源码树内、目录已存在、无可用浏览器）；`3` 执行失败；`4` 证据不完整或自相矛盾。

产物（每次运行独立目录，默认仓库旁的 `HuaKangOS-validation/browser-<模式>-<UTC时间戳>/`，可用
`--output` 或 `HUAKANGOS_EVIDENCE_ROOT` 指定）：

| 文件 | 内容 |
|---|---|
| `evidence/run-summary.json` | 逐命令退出码、用例计数、`browser_transport`、真实模型调用数 |
| `evidence/browser-evidence.json` | 逐页 `page_errors`、`/api/` 请求数与状态码、截图名、浏览器版本与可执行文件、CSP 事实 |
| `evidence/browser-environment.json` | 本次运行的浏览器与传输事实（由浏览器夹具写出） |
| `evidence/<用例>.png` / `.json` | 逐页截图与请求记录 |
| `browser-pipeline.json` | 顶层核对结论 `verified` 与 `problems` |

核对规则：`browser_transport` 必须等于请求的模式；原生模式下 `complete` 必须为真、逐页 API 流量必须非零、`page_errors_total` 必须为 0、必须记录真实浏览器版本并观测到应用 CSP；任何一项不满足即 `verified=false` 并以退出码 4 结束。`evidence/browser-evidence.json` 只由已有证据文件汇总，不执行浏览器、不联网。

## 里程碑验收判定（`run_acceptance.py`）

`run_acceptance.py` 是本目录的**验收判定**入口：它不跑测试、不联网，只按 `acceptance_milestones.json` 里登记的断言复核一次已完成运行的证据，然后写出结论。

```bash
# 1) 先产出证据（同一条完整命令）
python tests/assistant_offline/run_browser_pipeline.py --browser-mode fixture
# 2) 再按里程碑复核
python tests/assistant_offline/run_acceptance.py --milestone M8.1 \
  --evidence ../HuaKangOS-validation/browser-fixture-<时间戳>/evidence
```

退出码：`0` 通过；`1` 未通过（逐条列出矛盾）；`2` 拒绝（里程碑未登记、证据目录不存在或缺少 `run-summary.json`）。
结论写入 `<证据目录>/acceptance-<里程碑>.json`，其中 `problems` 为空才算通过。

判定规则全部来自 `acceptance_milestones.json`（只写断言、不含证据）：运行必须 `complete=true`、`scope` 与登记一致、传输模式与登记一致、总用例数不低于登记下限、每个登记套件的用例数不低于登记值、真实模型调用为 0、页面错误为 0、必须有浏览器证据。任何一项不符即 `accepted=false`，**不会**因为「看起来差不多」放过。

改动测试或新增套件后必须同步更新 `acceptance_milestones.json`，否则旧下限会让判定失去意义。

## 工作流与需求总账检查（M8.2，`check_m82_contracts.py`）

```bash
python tests/assistant_offline/check_m82_contracts.py --report <外部目录>/m82-contracts.json
```

它做三件事：以 `--check` 模式运行 `scripts/build_workflow_guides.py`（从不使用 `--draft`，因此手工改过的生成物会被判失败而不是被静默重写）；核对 193 项需求与 10 个模块的完整性、唯一性与引用；核对 111 条工作流与需求**双向**映射一致，并要求生成物携带与源相同的指纹。`--skip-generator` 只做对账，便于快速复核。

## 覆盖内容

定向覆盖：真实登录及门店权限、工具协议拒绝、持久 Run、租约与取消、人工确认及未知结果不重放；两步计划依赖、显式跟进授权、退出/暂停/撤权、原接待事实；重复唤醒、发件箱事务恢复和私有通知；原批量接口首项失败即停；完整前端模块与页面实操、移动端布局和上下文竞态。

模型响应是确定性合成内容，不使用真实 DeepSeek；原业务 API、状态、数据库与事务不是桩。原生浏览器测试与 fixture 测试分别记录，后者不证明原生 Cookie/CSP/网络 SSE。全套定向通过仍不代表原 101/283 模型场景、193 项需求、全部业务族、PostgreSQL、Windows、指定 MCP 客户端及员工试用已经验收。

## 定向复验与套件发现

默认运行所有已版本化 `test_*.py` 后端套件（`test_browser_ui.py` 仅由显式浏览器模式运行），不会因执行器白名单遗漏新文件。排查单项时可追加 `--suite test_service_facts.py`，可重复参数选择多个不同套件。未知文件、路径和重复项拒绝。定向执行保留语法与全部前端行为检查，但报告为 `scope=targeted`、`selected_complete=true`、`complete=false`；不能用它替代默认完整回归。CI 默认不筛选套件。入口脚本也包含在套件指纹中。
