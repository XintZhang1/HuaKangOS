# HuaKangOS · 华慷集团

2026-10-11 V2.11 已整合客户最新需求，并同步昨晚 main `76e73cf`，保留总经理完整核价、门店管理员、月度目标及版本更新功能。本轮实现、必要隔离检查及原生浏览器检查已完成，已交付[草稿PR #18](https://github.com/XintZhang1/HuaKangOS/pull/18)，尚未部署；阿里云已只读提取4项赠品名称并整理待补价临时表，原记录没有单价，仍待门店确认，DeepSeek真实识别尚未实调。准确状态与证据见[实施计划](implementation_plan.md)。

新合同由销售顾问从本店车型和赠品目录预填，冻结提交时价格。普通审批依次到销售经理、总经理；车价低于销售管控价，或销售经理人工填写赠品超价金额时，使用特殊申请表并加集团副总经理终审。两类批准合同均可打印。赠品无预设额度，销售顾问和客户不见赠品金额；相关审批、财务、内勤按岗位可见。批准合同锁档，变更新建。

销售经理/总经理可上传本店限价表，经 DeepSeek Flash max 识别建议、逐行补齐和确认后整批替换有效版本；新表不会改变未批准合同已冻结版本。赠品目录另允许系统管理员上传。财务核实上传发票、主动确认交车并抄送总经理，盖章赠品单齐备后交内勤补充延伸信息，再由总经理审核。新合同不再要求先登记到账；历史到账事实保留。

内勤按原车辆明细表的公式显示单车利润明细和结果，仅汇总各已填写净额；缺项显示待补齐，赠品金额来自冻结目录。交车以发票业务上传日核算，退车在总经理批准月追加冲减，退款另录。每日报表、自定义范围、月报默认展示多图；已确认日报保留历史，修订需说明。月度目标、同口径明细及导出继续保留。销售顾问与财务不开放经营看板。

系统保持独立记录方式，不接 ERP，不依赖库存或会员。合同/售后填单会自动关联客户档案。助手只开放当前记录域20个审阅接口（16查询、4填单），审批、价格上传、交车、退车退款仍在人工页面办理。成本、毛利、返佣利润仅授权内勤、总经理、董事长和管理员读取；集团副总经理的赠品审批及非敏感汇总权不扩大为整车毛利权限。历史业务数据、报表定义和迁移均保留。详见[业务设计](docs/客户第二版业务记录设计.md)。

2026-10-05 当前交付范围是代码/架构维护交接及本地真实模型复验。业主已取消尚未执行的 HTTPS/OS 输入法与独立 Windows/Linux 验收计划；取消不计通过，已完成的回归和 SQLite/PostgreSQL 证据保留，员工及生产验收不代签。当前状态只查[实施计划](implementation_plan.md)，范围见[本次调整](docs/implementation-patches/PATCH-SCOPE-MAINTENANCE-20261005-01.md)。

## 从源码开始

建议从 Git 克隆维护，以获得迁移、源内检查和提交历史。Python 支持 3.11–3.13；前端是原生 JavaScript，没有 `package.json` 或构建步骤。

```text
git clone <仓库地址> HuaKangOS
cd HuaKangOS
python -m venv .venv
```

Windows 激活 `.venv\Scripts\Activate.ps1`，Linux/macOS 激活 `.venv/bin/activate`，然后安装：

```text
python -m pip install -r requirements.txt
```

从 [.env.example](.env.example) 建立自己的私有配置，先确认 `DATABASE_URL` 指向全新开发库，附件和备份目录在源码外。仅对新实例运行：

```text
python -m app.cli init
python -m app.run
```

默认页面为 `http://127.0.0.1:8000`，初始化会交互创建第一个管理员。普通开发不需要模型密钥；四个 Runtime 功能开关默认关闭。使用 PostgreSQL 时安装 [requirements-postgres.txt](requirements-postgres.txt)，数据库服务及其工具另行提供。

## 启动入口的区别

| 入口 | 实际行为 |
|---|---|
| [start-preview.cmd](start-preview.cmd) / [start-preview.ps1](start-preview.ps1) | Windows 持久本地预览；按仓库身份绑定 `LOCALAPPDATA/huakangos` 下的外部实例，保留该实例账号和数据 |
| [start.ps1](start.ps1) / [start.sh](start.sh) | 普通启动快捷脚本，安装依赖并调用 `app.cli init`、`app.run`；使用自己的 `.env`/环境配置 |
| `python -m app.run` | Web；普通部署不会自动启动业务 Runtime worker |
| `python -m app.assistant_worker` | 使用已迁移的同一业务实例领取 Run；`--once` 单周期，`--health` 只读健康检查 |

只有经过本地预览配置与实例标记验证的 Web，才会嵌入同一 Runtime worker 核心。Web 与独立 worker 必须使用同一业务库、附件根及业务助手配置。意见反馈、运维模型和邮件另有进程、存储和凭据，见[维护交接](docs/维护交接.md)。

已有库升级前先一致性备份、在副本迁移并验证恢复，再使用 `python -m app.cli migrate`。当前迁移链包含历史 `h52j_assistant_work_plans` 和 Runtime `h53k_assistant_runtime`；文件存在不表示实例已经升级。不要用演示初始化代替升级，也不要只替换前端。

V2.7 新增 `h56n_record_report_sources`，仅为统计记录追加 7 个来源、更正及备注字段，不改写原始统计内容。已完成 9 组隔离 HTTP 与 5 项原生浏览器验证，49373 演示保留数据更新并追加 25 表合成示例，GitHub main 与阿里云完成 h56 保留数据发布。详[本轮检查点](docs/implementation-checkpoints/V2.7-report-generation-20261009.md)。

## 维护与验证

先读[维护交接](docs/维护交接.md)的模块图、五条读码路径和配置表，再查[架构合同](ARCHITECTURE.md)、[开发约束](AGENTS.md)及[执行入口](CODEX_EXECUTION_PROMPT.md)。真实模型复验另见[验证交接](DEEPSEEK_TESTING_HANDOFF.md)。

Git 中保留的[运维隔离检查](tests/ops_review/run_isolated.py)和[浏览器点击入口](tests/browser_click/run.py)可在新环境使用仓库外合成实例。完整归档回归及原 101/283 模型定义依赖另行交付的验证材料；不要求开发者拥有本机历史 V 路径，也不能把源内检查冒称完整归档验收。当前普通 CI 没有浏览器任务。

原需求仍为 193 项、111 条发布工作流；目录可检索、页面覆盖和具体业务验收分别记录。历史实现边界见 [R4 说明](docs/R4-B1-实现与验收说明.md)，整合来源见[整合补丁](docs/implementation-patches/PATCH-INTEGRATION-20261004-01.md)。

工作流源为 `docs/workflow-source/`，生成与检查分别使用 `python scripts/build_workflow_guides.py`、`python scripts/build_workflow_guides.py --check`。原人工模块、深链接与待办保持可用。

`python scripts/package_source.py --output <仓库外的新ZIP路径>` 打包当前工作树。源码 ZIP 不含 Git 历史、测试目录、CI、外部验证胶囊、依赖环境、数据、附件、日志或密钥；测试维护优先使用 Git 克隆，验证材料单独按指纹交接。源码交付不等于上线；生产的 HTTPS、安全 Cookie、Host、ClamAV、联合备份恢复及人工验收合同保持。
