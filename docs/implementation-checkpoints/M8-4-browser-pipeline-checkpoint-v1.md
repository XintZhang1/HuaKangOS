# M8.4 真实浏览器流水线检查点 v1

2026-09-30；开发候选。**不部署、不默认开启四个功能开关、不调用真实模型。** M8.1 保持 `in_progress`，
M8.4 保持 `todo`（本记录只交付流水线本身与一次真实浏览器证据，不宣称 M8.4 整体验收成立）。

## 1. 为什么先做这一步

计划把「真实 HTTP 浏览器」验收放在 M8.4，命令是 `$V/run_validation.py --milestone M8.4`；
而仓库里已有的 `tests/assistant_offline/run_isolated.py --browser-mode native` 虽然能跑原生浏览器，
却缺少三件东西：

1. **没有单一入口**：调用者要自己拼 `--source/--output/--browser-mode`，还要自己判断结果算不算通过；
2. **没有机器可读的浏览器证据**：逐页 `page_errors`、`/api/` 流量、浏览器版本、CSP 事实散落在 14 个
   JSON 与日志里，审阅者只能人工读；
3. **没有「拒绝伪装」的守卫**：原生失败可以被人为改跑 `fixture`，或把 `fixture` 结果写成原生验收，
   而两种传输在计划里**必须分开记录**（PATCH-M8-1-VALIDATION-01）。

本检查点交付 `tests/assistant_offline/run_browser_pipeline.py`：一次调用完成预检 → 全新外部目录 →
原生执行 → 证据核对，并把上面三件缺口全部收口。

## 2. 本批实际改动文件

生产代码：**无**。本批只改测试与执行器，未触碰 `app/**`、`web/**`、`migrations/**`、
功能开关默认值、业务确认接口或权限规则。

| 文件 | 作用 |
|---|---|
| `tests/assistant_offline/run_browser_pipeline.py` | 新增（M8.4 单一入口）：预检、执行、核对、退出码 |
| `tests/assistant_offline/browser_evidence.py` | 新增：只从既有证据文件汇总，不启动浏览器、不联网 |
| `tests/assistant_offline/browser_harness.py` | 记录**真实网络请求**、浏览器版本与可执行文件、CSP 事实 |
| `tests/assistant_offline/run_validation.py` | 浏览器步骤后写出 `browser-evidence.json`，页数与执行数不符即失败 |
| `tests/assistant_offline/run_isolated.py` | 新增两个执行器文件进入外部副本与套件指纹 |
| `tests/assistant_offline/tests/test_browser_ui.py` | 逐用例归属环境记录；登录失败也留证 |
| `tests/assistant_offline/tests/test_browser_pipeline.py` | 新增 13 项流水线合同套件 |
| `tests/assistant_offline/README.md` | 记录入口、退出码、产物与核对规则 |
| `.github/workflows/assistant-offline-checks.yml` | CI 原生步骤改用同一入口（原生结论不再绕过核对） |

## 3. 核对规则（为什么它不能假装通过）

`run_browser_pipeline.py` 在写结论前逐项校验，任一不满足即 `verified=false`、退出码 4：

| 规则 | 它拦住的反例 |
|---|---|
| `run-summary.browser_transport == 请求的模式` | 用 fixture 结果冒充原生验收 |
| 原生模式下 `complete=true` 且 `scope=full` | 用定向子集冒充完整回归 |
| `browser-evidence.page_count == 实际执行用例数` | 少跑用例却仍报绿 |
| 原生模式下**逐页 `/api/` 流量 > 0** | 页面其实没走到隔离服务（桥接伪装成原生） |
| 原生模式下 `page_errors_total == 0` | 页面脚本异常被当成通过 |
| 必须记录真实浏览器版本与可执行文件 | 不知道究竟哪个浏览器产出了证据 |
| 必须观测到 `script-src 'self'` 的 CSP | 关掉 CSP 求绿 |
| `real_model_calls == 0` | 合成夹具偷偷变成真实模型调用 |

预检同样拒绝：源码带 `.env`、输出目录在源码树内、输出目录已存在（证据永不覆盖）、
无可用浏览器。**原生失败即失败，不自动降级。**

## 4. 本批实测：Windows 本机真实 Chrome

命令（唯一入口，证据目录在仓库外）：

```powershell
python tests/assistant_offline/run_browser_pipeline.py --browser-mode native `
  --browser "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

最终一次运行（含本批新增的两个套件）的结果：

| 层次 | 用例数 | 结果 |
|---|---:|---|
| 后端领域与集成（17 个已版本化套件） | 211 | 全部通过 |
| 前端模块行为（Node） | 55 | 全部通过 |
| **原生浏览器页面操作** | 14 | 全部通过 |
| 合计 | **280** | 全部命令退出码 0 |

`browser-pipeline.json`：`verified=true`、`problems=[]`、`browser_mode=native`、`native_transport=true`。
`run-summary.json`：`complete=true`、`scope=full`、`browser_transport=native`、`real_model_calls=0`、
`release_accepted=false`。

**真实浏览器事实**（不是桥接）：

- 浏览器：`C:\Program Files\Google\Chrome\Application\chrome.exe`，版本 `154.0.8037.59`，来源
  `browser_source=system-candidate`（本机没有 Playwright 自带浏览器，见 4.2）；
- 观测到的 CSP：`default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src …`
  （`script-src 'self'` 存在、无 `unsafe-eval`）；
- 逐页 `/api/` 真实流量：14 页全部非零（最少 14 条、最多 46 条），状态码覆盖 `200/201/202/401/422/503`
  ——包括真实登录 `POST /api/auth/login` → 200、真实 SSE 补读 `GET /runs/<id>/events?after_seq=0` → 200、
  真实人工确认 `POST …/proposals/<id>/confirm` → 200、以及刻意的 503 侧栏失败重试用例；
- `page_errors_total = 0`；真实模型调用 0。

证据目录（仓库外，逐页 PNG + JSON + 逐命令日志）：
`C:\Users\tiefu\.codex\HuaKangOS-agent-validation\runtime-v1\browser\browser-native-20260930T001744Z\evidence`

生产源码指纹 `a7c0cd8fe38d8eb5101ffcf92fba07e1780f59b29e6bf368acf522fbf38ae8e4`；
测试套件指纹 `36370e655814085e86b5ba7ad402b38ceb3461225fd7e1153d574d837e8f49a4`。

> 本批保留更早的两次原生运行（`…164304Z` 时 **272** 项、`…170405Z` 时 **277** 项、`…001744Z` 时
> **280** 项），它们是同一批次里不同源码集合的**完整运行**，**不相加**、不比较为「不同用例」；上面以
> 最终一次为准。上表是该次原生运行实际执行的完整清单（`counts` 逐套件计数之和），其中
> `test_browser_pipeline.py`（16 项合同套件）与 `test_revocation_session.py`（5 项撤权套件）都与本批
> 同时落盘。

### 4.1 Linux CI 独立复跑（本轮已读到运行结论与日志，v5 当时读不到的部分已补齐）

交付推送后，GitHub Actions 按仓库工作流在 Ubuntu 上用同一个入口真实执行。**连续四次运行的结果都保留**，
因为它们是本轮修正的真实依据：

| # | 提交 | run | 结论 | 真实原因（不是猜测） |
|---:|---|---|---|---|
| 1 | `9b79fd3` | `36644421471` | success | 通过，但**跑的是主机自带 chromium**（见下） |
| 2 | `cc6d5fe` | `36645406272` | **failure** | 修正优先级后改用固定版本自带 Chromium 143，`test_07` 在 `asyncSetUp` 点击导航项超时 |
| 3 | `a87c2c8` | `36647479427` | **failure** | 改为显式等待导航项后仍失败（30s 也未出现），说明不是渲染快慢 |
| 4 | `71a4b51` | `36650238893` | **success** | 修好真实根因后全绿（本行即最终结论） |

**最终一次（run `36650238893`，被测提交 `71a4b51`）的核对结论**：

- 步骤打印 **`verified=true`、`problems=[]`、`native_transport=true`、`page_count=14`、
  `page_errors_total=0`、`real_model_calls=0`**，以 `PIPELINE VERIFIED: …` 结束；`browser-final`
  日志为 `Ran 14 tests` / `OK`；
- **`browser_source=playwright-bundled`**、
  `browser_executable=/home/runner/.cache/ms-playwright/chromium-1200/chrome-linux64/chrome`、
  `browser_version=143.0.7499.4`：CI 现在确实跑在该步骤安装的**固定版本**浏览器上；
- 逐套件计数：后端 **211**（含 `test_browser_pipeline` 16、`test_revocation_session` 5）＋前端 **55**
  ＋`browser-final` **14** ＝ **280**。

**第 1 次暴露的真实缺陷（已修复）**：CI 步骤确实安装了 Playwright 自带 Chromium，但解析顺序把主机自带的
`/usr/bin/chromium` 排在**固定版本自带浏览器之前**——CI 用的其实是镜像里的系统浏览器，而不是该步骤刚装的
那个。已改为「显式参数 → `HUAKANGOS_CHROMIUM` → **Playwright 固定版本自带浏览器** → 主机常见候选」，并把
来源记入 `browser_source` 与 `browser-pipeline.json`；合同用例
`test_pinned_playwright_browser_wins_over_a_host_system_browser` 固定该优先级。本机没有自带浏览器，
因此本机仍解析为系统候选，与第 4.2 节一致。

**第 2、3 次暴露的真实根因（已修复）**：`test_07` 每次都在 `asyncSetUp` 的登录步骤失败，而**不是页面
渲染慢**——30 秒等待也没等到导航项。为此给装置补了只读诊断 `LOGIN-STATE`，第 3 次运行本机复现时它直接
给出答案：

```
LOGIN-STATE {"nav_entries": 0, "user": false, "login_form": true,
  "body": "…登录\n账号\n密码\n数据库暂时忙或连接异常，请刷新核对后重试，避免重复录单。…",
  "requests": [ … {"method": "POST", "path": "/api/auth/login", "status": 503}]}
```

即 `POST /api/auth/login` 返回 **503**。该状态是应用对 `OperationalError` 的既有处理
（`app/main.py:200-203`），文案本身就说「可以重试、且不会重复录单」；隔离 worker 与登录共用同一个
SQLite 库，于是**一次瞬时写竞争**被单发登录放大成 14 个页面错误，而它们与页面本身毫无关系。装置现改为
**仅对该瞬时状态**做最多 3 次有界重试（其它失败照原样报告），并新增两条证据补强：① 在 `asyncSetUp`
失败的页面也会在关闭浏览器**之前**留下截图与请求清单，并标记 `setup_failed`（此前这类页面恰恰是审阅最
需要、却唯一缺失的那一页）；② 导航未出现时打印 URL、导航项数量、登录表单是否仍在、可见文本与最近请求，
使只有 CI 日志的审阅者也能定位。

本机的 Windows + 真实 Chrome 运行与 Linux CI 运行是**不同浏览器、不同宿主**的两次独立复跑，各自留证，
不互相替代。上面的计数一致性只说明两端的用例清单相同，不代表两端浏览器相同；本机原生运行的
`verified=true`、`page_count=14`、`page_errors_total=0` 来自同源码指纹的独立运行。

### 4.2 本机浏览器环境的一个真实约束（如实保留）

Playwright 自带的 Chromium **未能安装**：`playwright install chromium` 在派生下载子进程时以
`spawn EPERM` 失败，指定仓库内 `PLAYWRIGHT_BROWSERS_PATH` 后又被 `__dirlock` 陈旧锁拒绝。
最终按**使用者明确授权安装插件**的范围改用本机已安装的 Chrome（`HUAKANGOS_CHROMIUM` /
`--browser`），未修改任何浏览器安全策略、未关闭 CSP、未降级传输。CI 侧 Playwright 自带 Chromium 已安装
成功，并在第 4.1 节所述的顺序修复后成为 CI 的首选浏览器。

## 5. 本批明确未覆盖的边界

- **不宣称 M8.4 验收成立**：M8.4 的四条完成检查还要求 390/768/1440 三种宽度、中文与组合输入、
  焦点/光标与未发草稿、换店迟到结果、断网重连按 `seq` 补读、伪造内部身份 header 无效、缺 CSRF 写被拒、
  以及 HTTPS 会话证据。本批的 14 项页面用例覆盖其中一部分（响应式抽屉、移动端卡片确认、切店丢弃旧
  Run、侧栏失败重试、CSP、真实 Cookie/CSRF），**其余仍待**；HTTPS 与浏览器重启未执行。
- 未执行 M8.3（独立 PostgreSQL、h52j 合成旧库升级、联合备份恢复），M8.4 的全局顺序前置仍未满足。
- 真实模型调用 0；模型响应仍是确定性合成内容。
- 未执行员工试用、未开启四个功能开关、未部署。
- 本记录不把 `fixture` 传输结果写成原生；第 4 节的用例全部来自 `native` 那一次运行。

## 6. 下一执行点

1. 在 M8.4 名下继续补齐其余完成检查（三种宽度与 IME、断网重连按 `seq` 补读、伪造身份 header、
   缺 CSRF 写、HTTPS 会话），复用同一入口与同一核对规则；
2. M8.1 剩余清单继续推进：旧租约不得覆盖新状态的 DB 跃迁演练、确认前原业务写入计数、
   批量部分失败即暂停、延迟注入（会话级撤权见 `M8-1-revocation-checkpoint-v1.md`）；
3. M8.3 的外部条件（独立 PostgreSQL 测试服务）具备后按计划执行；缺少该条件时按计划记 `blocked`，
   不以 SQLite 恢复替代。