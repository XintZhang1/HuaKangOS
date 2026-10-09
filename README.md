# HuaKangOS · 华慷集团

HuaKangOS 当前面向客户第二版需求，是独立的业务记录与经营可视化系统。销售预填合同，经销售经理、总经理依次批准后可以打印；内勤随后核价和补充原表信息，再交总经理审核。附带信息允许留空提交，已批准合同锁档，变更新建合同。收银核对发票和实际到账，两者独立留存。六类售后和客户建档只记录业务，不依赖库存、会员或 ERP。

侧栏**可视化看板**下设**每日报表、自定义范围数据、月报统计**，默认打开内勤已确认的每日报表；日报修订追加版本，月报随内勤日常维护实时更新。支持过去2–90日、2–36月的自选趋势，单图切换柱状图、折线图及同范围数据表；缺报/未知保持空白。业务菜单为**销售业务、售后业务、财务流水、客户信息**，AI助手保留侧栏入口。旧模块菜单及旧页面入口已移除。

提交销售合同或售后记录会自动保存并关联客户档案，无需先建档。客户信息可查看权限内的关联合同和售后记录；历史已填单据通过追加迁移补关联，仅同名或没有电话的客户不自动合并。

V2.7 保持四项业务框架，提供 **30 类报表，其中 25 类原截图/Excel 统计表共 451 个字段**。已核价合同可预填车辆明细，内勤补充缺少的事实；看板生成权限内的统计表、图表和同范围 CSV，并可切换组合、自动或人工来源。快手、保费溢出、车辆类别、毛利合计名称及单产精度已补齐。累计快照、库存期末值、共享门店指标和比例各按明确规则处理；售后排名使用实际经办人。更正追加新记录，旧版人工记录单独保留，不混入新成绩。

V2.9 规格及岗位、统计口径见[客户第二版业务记录设计](docs/客户第二版业务记录设计.md)，实施与交付状态见[实施计划](implementation_plan.md)。成本、毛利、返佣利润仅内勤和董事长可见，维护管理员保留维护能力。内勤可导入统一标准价格和原表CSV，人工最终值按指标替代而不重复累计。发票支持图片/PDF上传和DeepSeek识别建议，由收银确认，原件替换留档。AI助手只开放当前记录域17个已审阅接口，旧库存/会员等域关闭；核价、审批、发票、到账和日报确认在页面由员工操作。历史业务数据与迁移保留，以下旧验收说明不代表第二版验收。

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
