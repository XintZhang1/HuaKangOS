# M8.1 代办事实、并发会话与页面错误态检查点 v4

2026-09-29。接续原 feature `47d9dc25bc2846d84ae920291a0aee2f244e4ec8`，不是重新实施 R4-B1。该基点已包含 main `5d3802931aae6ce246fb549e5837e35d8c01781b`，无需合并。M8.1 保持 `in_progress`；本记录不是生产发布或整个业务助手验收。

## 已实现的修复

1. 原采购/维修 API 测试在每次事实读取后释放自身 Run，保留真实 worker 单槽、权限和租约守卫。原 CI `36522387531` 的失败不是删测或放宽生产检查来消除。
2. 代办外部批准事实使用原接口顶层 `results[].submission_id` 关联 `submissions`，逐当前 `line_key` 取最新提交；不猜嵌套字段或从结果说明文字推断。缺失、重复、串单或非法关联返回未知。另一个项目较新的提交不能抹掉已有项目批准，旧的同项目结果不能证明补件后已批准；单项批准不等于全部履约。
3. 侧栏未成功读取时不显示假零待办；刷新失败保留已有内容，提供“重试”，不覆盖草稿或增加解释性段落。
4. 原页面新对话 409 已用两个真实 SQLite 事务确定性复现为 `SQLITE_BUSY_SNAPSHOT`（517）。新对话入口结束旧认证快照，在 SQLite 短事务中预留写入后重新执行原 Cookie、CSRF、账号、门店和岗位检查，再调用原创建服务一次。没有业务命令重试，没有绕过撤权，没有改变默认数据库配置。
5. 离线套件默认发现全部后台测试，定向 `--suite` 单独标记，定向通过不再被描述为完整回归。新增的测试也进入 Git 及来源指纹。

精确改动范围分别见 PATCH-M8-1-NATIVE-FIXTURE-01、SERVICE-FACTS-01、SIDEBAR-ERROR-01、SESSION-CREATE-01、SUITE-SELECTION-01；不改原业务状态机、付款流程、业务确认接口或功能开关默认值。

## 本地验证证据（候选提交时记录）

本地不可变快照 v4c 的生产指纹：`489d8bc5b889730abaf0296bac107e532d15940d88fde4a7e21abfe6d694e31d`。
测试指纹：`827ff6bd6444abe68b6edaf948da5fc89f8af5b3e925088c8fd3353f110960a3`。

新库迁移与合成初始化、Python/JavaScript 语法检查、150 项后台/编排/验证工具测试、47 项前端模块测试均已执行并通过。150 项包含直接事实投影和 worker 隔离测试，不全部称为原 HTTP 集成测试。新增代办授权跟进用例真实运行 worker：等待原提交结果，收到原批准事实后完成只读计划，不创建业务卡片或擅自履约。

本地完整回归已结束，退出码 0：150 项后台/编排/验证工具、47 项前端模块、14 项 Chromium 桥接页面全部通过（共 211 项，不与后续复跑累计）。`run-summary.json` 为 `complete=true`、`scope=full`、`browser_transport=fixture`、`release_accepted=false`。本地 `fixture` 使用显式受控传输桥接，不能冒充原生 Cookie/fetch/SSE 验收。收尾日志仍保留 Playwright 绑定关闭时的 `TargetClosedError` 警告；没有把这些日志删掉或宣称整个运行零告警。候选提交时原生 CI 尚未完成，其随后实际结果追加于下一节。

原生本地运行曾被浏览器环境以 `ERR_BLOCKED_BY_ADMINISTRATOR` 拒绝导航，没有修改浏览器安全策略或降级后冒称原生。中途桥接页面 test_07 的 409 保留为故障证据；随后独立确定性红灯、原 API 12 项修复回归、完整回归分别记录。首次代办测试导入顺序的夹具故障单独记录，不冒称产品缺陷。

## 原生验证与 Git 交付追记

2026-09-29 11:24 UTC 后核对：Actions run `36560475158` 的原生测试 job `109379860008` 与已验证检查点发布 job `109383066695` 均为 `success`。这不是继承旧提交的成绩。

- 精确被测代码提交：`ee9385428a38fdda3e10e0d813fb9c6cdbf83c6c`。
- 精确被测 Git 树：`6db24c5decfdc0cde2717bb6160267d4ddc8fab2`；唯一父提交为本记录开头的 `47d9dc2`。
- 流水线头 `548246693a1d9e07ca0a9281b4533bb3c1d389e0` 仅负责导入候选；先核验 bundle SHA-256、提交、父提交和树，再在独立 worktree 中运行候选代码。不能把流水线头误写成被测业务代码提交。
- Ubuntu / Python 3.13 / Node.js 22 / Playwright 1.57.0 / Chromium；全新隔离合成库；原始入口 `python tests/assistant_offline/run_isolated.py --source <candidate> --output <external-directory> --browser-mode native`。

| 层次 | 执行数量 | 结果 |
| --- | ---: | --- |
| 后台、编排、事实投影及验证工具 | 150 | 全部通过 |
| 前端模块行为 | 47 | 全部通过 |
| 原生 Chromium 页面操作 | 14 | 全部通过 |
| 合计 | 211 | 与本地复跑不重复计数 |

新库迁移、合成初始化和 Python/JavaScript 语法检查也退出 0。原生 `run-summary.json` 为 `complete=true`、`scope=full`、`browser_transport=native`、`real_model_calls=0`、`release_accepted=false`。生产与测试指纹分别与上述本地 v4c 完全一致。14 份页面证据的 `page_errors` 均为空；保留 Python 异步调度慢回调提示，不宣称整个日志零告警。

浏览器使用原登录页面、Cookie、原生 fetch 与网络 SSE；没有桥接替换、bypass_csp 或 unsafe-eval。实测覆盖发送、取消、离页返回、切店、移动端、显式开启跟进、通知、逐张人工确认、原 v4 销售合同签回与交车分别确认，以及侧栏 503 后保留旧数据和未发草稿、点击重试恢复。模型响应仍为合成内容，不属于真实 DeepSeek 能力验证。

原始 artifact：`assistant-native-evidence-ee93854`，ID `11030191285`，ZIP SHA-256 `38bc6d5c88f7531ed2b4b1ba85a803fc061bf6448ea081f69d3be5ed1360ab2e`。已下载并核对计数、指纹、候选 SHA 和页面日志；副本 `/mnt/data/assistant-native-evidence-v4` 仅为临时工作目录，不能依赖永久存在，随本次交付保留 ZIP，测试源码均已进 Git。Actions artifact 保留 7 天，不含运行数据库、密码或真实客户信息。

先成功保存 `checkpoint/assistant-verified-ee93854`，再次读取 main/feature 后，使用授权连接器 `force=false` 将 `feature/assistant-agent-runtime` 从 `47d9dc2` 快进至 `ee93854`。没有 force push、覆盖其他提交、修改 main，临时导出 workflow 和 bundle 分片未进入 feature。当前文档追记是其后的纯文档提交，不改变上述被测生产和测试文件。feature 自身工作流若再次运行，属于独立复跑，不能在未读回结论时预填成功。

## 下一执行点与未完成边界

M8.1 继续保持 `in_progress`。先按原业务族补齐维修、仓库与跨店授权的实际页面长链和失败恢复；继续核对所有事实适配器，不把接口、类型或注册数量等同可用功能。原生截图还显示既有等待原因 `employee_continue` 直接透出到侧栏，属于后续简洁中文文案清理的具体入口；本轮没有宣称全部旧文案已清理，也没有在通过后的代码里追加未经复验的 UI 修改。

真实模型调用为 0。四个新功能开关默认关闭；不接真实客户库、不部署。真实 DeepSeek 的 101/283 模型场景、193 项需求整体业务验收、跨业务族完整故障矩阵、PostgreSQL、Windows、指定 MCP 客户端、生产 HTTPS/代理与真实员工试用仍按主计划分别待验。不可将本轮回归通过等同这些工作全部完成。
