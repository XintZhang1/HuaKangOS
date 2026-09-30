# 2026-09-30 浏览器点击交付审阅 v2

本报告审阅本轮代码与浏览器点击交付。业主已明确以该范围收口，并要求尽量覆盖桌面功能需求表；原 M8 全面验收、员工试用和生产条件仍按实施计划记录，不由本报告替代。M8.1 恢复 `implemented`，M8.4 保留 `todo`，CP-35 保留 `implementation_released`、CP-36 保留 `not_ready`。

## 当前代码与改动

开工分支 `feature/assistant-agent-runtime`，本地和 GitHub 头均为 `71276037dc920069d6d5fa77311b0a7fdbbc3773`，工作树干净；`git pull --ff-only` 返回 Already up to date。按当前源码、实施计划和未提交补丁重载，没有重置旧基线。`total_plan.md`、原业务状态机、人工确认接口与默认关闭开关保留。

生产修复范围为 11 个 Python 文件、3 个 JS 文件和能力目录：

- `app/group_benefits_api.py`、`app/group_benefits_service.py`、`app/assistant_runtime_domains/group_benefit.py`：按真实 member ID 读取权益详情，沿用原门店、岗位和客户责任授权；分页/超限如实保留，不猜权益余额。
- `app/repair_package_api.py`、`app/repair_package_service.py`、`app/assistant_runtime_domains/repair_package.py`：按真实 purchase ID 读取购买及可见核销事实；未发行、零价取消、退款现金事实分别解释，不用缺失现金行推定已付款。
- `app/assistant_runtime_domains/__init__.py`、`app/assistant_runtime_domains/group_principal.py`、`app/business_assistant_capabilities.json`：有限注册对象分派、原导入 GET、集团原 purpose 与两个新只读路由接线，不扩展模型写权限。
- `web/app.js`：登录默认入口及切店后读取该门店真实功能开关，保留有效深链接和迟到响应保护。
- `web/assistantworkspace.js`：员工最终确认跟进前刷新同一计划，范围变化要求重新核对，CAS 拒绝保持可见，没有自动重放。
- `web/businessassistant.js`：欢迎建议只预填短目标，最多四条；不覆盖草稿或发送。
- `app/db.py`、`app/security.py`、`app/main.py`：仅 SQLite 退出短事务使用服务器 Connection 选项选择 `BEGIN IMMEDIATE`，重新执行原认证/CSRF/岗位核对后只删除本次会话一次，提交成功才清 Cookie；其它事务和 PostgreSQL 不改。

精确原因、文件和异常路径见本轮九份 `PATCH-M*-01` 补丁。生产代码已经独立人工复核；原对象维度、权限、确认和资金/库存事实边界保留。旧测试与套件 CI 共 42 个跟踪文件移除，连同旧本地运行物共 3605 文件、1,121,846,836 字节先移至外部可恢复归档并逐文件 SHA256 核对；不删除历史失败证据。

新入口 `tests/browser_click/run.py`、五个 Python 脚本、需求清单、评分规则、使用说明及 `.github/workflows/browser-click-checks.yml` 已落盘。先白名单镜像当前源码与脚本到全新外部目录，复制前/内容/复制后三份指纹一致才导入 app。浏览器直接访问原生 HTTP 服务，原 Cookie/CSRF/CSP/SSE、原业务 API、worker 与 SQLite 运行；仅模型响应使用阻止外网的合成 provider。没有 fetch/Cookie 桥接或静默降级。

## 同一次自动点击证据

权威运行目录为 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/automatic-20260930-07/evidence/`。

实际命令入口：外部 venv Python 执行 `tests/browser_click/run.py --source E:/HuaKangOS --output C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/automatic-20260930-07 --browser "C:/Program Files/Google/Chrome/Application/chrome.exe"`。退出码 **0**；`run-summary.json` 与 `browser-click-report.json` 均为 **complete=true、passed=true，注册/执行/通过 13/13**。真实 Chrome **154.0.8037.59**、Playwright **1.56.0**、Python **3.11.4**，模型请求 **17 次合成、0 次真实**。同轮记录 **1128 动作、659 真实点击、4 原生键盘动作**，3 项补充 Cookie GET 单独计数，未当成业务点击；页面异常和外网尝试为空。

九组核心路径覆盖欢迎建议/三宽度/草稿/焦点、原人工深链接、真实查询零卡、准备零业务写入与员工确认后唯一客户、依赖计划开启/暂停/恢复/结束与后继卡、慢查询切店/退出、协议失败零卡、Cookie/CSRF/CSP/SSE。实际观测一次结束授权 CAS 409，真实拒绝可见、原业务/授权不变，员工重新核对并再次两次确认后 200 与数据库 revoked；不是重试隐藏冲突。HTTP 合成实例 Cookie secure=false，不冒称 HTTPS 验收。

新增四组需求覆盖来自 `C:/Users/tiefu/Desktop/全新搭建：功能需求表.docx`，与仓库原表字节一致，SHA256 `ddf297678e5d6d35e1dbfffc5c232c3d56748934eb22b58bbb9f9d5343689aae`。10 模块、193 项和 111 工作流双向核对无遗漏；本轮逐项真实检索编号及原名称，逐条打开 **111 指引**，点击 **70 共用原人工页面**，打开/聚焦/取消 **9 类原表单**，各组原业务摘要不变。逐项结果见 `requirements-coverage.json`，每项分开记搜索、指引、页面、表单和业务子动作。

实际业务子动作只有 HK-098 客户新增/历史唯一、HK-002 第一接待分派确认；第二依赖卡仅准备。HK-117/HK-126 详情 GET 为只读补充，夹具创建不计员工业务操作。**完整业务流程实测为 0，193 项完整业务验收为 false**。四个原报表的来源不完整警示原样保留，仅在真实 GET200、字段和界面文案相符时通过页面显示层；不造来源或完整合计，不记来源验收通过。

## 实际浏览器人工审阅

使用同一生产/脚本指纹的全新实例 `manual-20260930-02`，IAB 实际销售登录，768/390/1440 宽度审阅；短建议预填后，新对话发送 `新建客户 浏览器客户Manual0930`，打开待确认卡并单次点击确认，刷新结果、点击查看单据到原客户档案，最后退出到登录页。输入目标后主要办理点击为发送/查看待确认/确认共三次。数据库从客户零条/卡 pending 变为客户恰一条/卡 succeeded，刷新与原单核对后仍恰一条，员工/门店/原单一致。

人工评分按 `rubric.json` 最低每项 3 分：显示 **3**、流程简易 **3**、文案简洁 **3**、事实清楚 **4**、失败恢复 **3**、可操作性 **3**。桌面双栏和历史状态仍有重复信息；评分不代表真实员工效率或试用。首次手工输入未符合合成 provider 登记格式，应用如实显示未完成且零卡/零客户，该失败保留并不计成功；随后使用已登记格式走通。未修改模型协议来使这次输入变成功。

人工证据目录 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/manual-20260930-02/evidence/`：`manual-review.json`、准备/确认/最终 DB JSON、`01-welcome-768.png` 至 `06-logged-out.png`。自动报告中的人工 pending 保留为当时事实，人工结果在独立报告中登记。临时尺寸已恢复、代理创建的 tab 已关闭。工具中断后服务原句柄已消失，CIM 验证 Python 进程和 52510 监听均为空；无正常 serve 停止 summary，不补造 exit0/stopped=true，独立保存 `service-cleanup.json`。

## 失败归因与复验

每次运行均在新目录，原失败不覆盖、不拼接：automatic01 **6/9**；02 端口启动拒绝，未执行；03/04/05 各 **8/9**；06 **11/13**；07 **13/13**。实际产品修复包括登录入口、切店开关、跟进旧版本提交和 SQLite 慢查询退出 503；测试装置修正包括混合快照门禁、端口真实 listen 检查、陈旧 h1 等待及多余滚动导致 DOM 分离、将报表来源警示准确归入页面层。原 CAS 守卫和来源警示没有为求绿删除。

退出问题的 Fresh06 服务只记录 OperationalError，未捕获原错误码。外部 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/auth-logout-probe-20260930/report.json` 用两连接全新合成库独立复现原 BEGIN 读后升写的 **517 SQLITE_BUSY_SNAPSHOT**；新 Connection 选项在 begin 事件前生效，短写事务顺序正确，连接回池后选项不传播。该探针证明机制，不能把它写成 Fresh06 已捕获 517。Fresh07 慢查询期间真实退出已通过。

## 指纹、静态审查与剩余条件

- 受检生产镜像 SHA256：`0ade3e7a781de93a963bc341242488abf386ee7d68bed55178838cc815e22f7a`。
- 执行脚本集合 SHA256：`e4265ebdc23ce75c2d1767e272da5bc37167221f380d0c14d4857735eacff921`。
- 193 需求静态清单 SHA256：`19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f`。
- 前十二生产文件复核集合 SHA256：`f227b8734265af823a18659369e2cc037d9f006f60061e16baf48d552bb3f87f`；退出三文件复核集合：`aaed12b3f35d8fe32eacb61409ebdb696ce3aeb0c1219e707836ba5bd31a4346`。
- 最终静态审查：16 Python AST、3 JSON、3 JS `node --check`、`git diff --check` 均通过；不导入仓库 app。当前生产和脚本指纹与 automatic07/manual02 一致，逐文件清单及依赖见 provenance，最终汇总 `browser-click/final-delivery-evidence.json`。

新 CI 使用 Ubuntu/Python3.13/固定 Playwright1.56.0/自带 Chromium，调用同一入口，只上传 evidence，不上传随机密码、数据库或配置；**配置已经交付，尚未推送，未声称新远端 CI 已运行**。历史 Linux CI 成绩不继承。

本轮交付完成后不再扩展验证。原 M8 待验收条件包括完整业务批量/193 实际交易链路、SSE 断网按 seq 恢复、OS IME 候选/浏览器重启/HTTPS、独立 PostgreSQL 与 Linux、附件/恢复故障、101/283 真实模型、员工试用及生产发布条件。四开关默认关闭，未部署、未推送、未真实调用模型。
