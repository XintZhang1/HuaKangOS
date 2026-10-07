# PATCH-M8-5-GUIDE-BRANCH-13

2026-10-07；当前 M8.5。依据本轮真实全量发现的具体事实、岗位及分支误述，按既有持续授权做有限修复。M8.5 `in_progress`、M8.6 `todo`、CP-37 `not_ready`、M8.10 `done`。

## 本轮依据

冻结 `80f332d0ff8b10600abf8306e684a977336eca57`、source `8a6a02ee6f107f9a2fbacdba9e1777778390aaefcc41bbaff110e264b3c9857d`，九代表 `rep051252` 结构及独立语义9/9后，同候选从零运行原283：`20261007T052312Z-25326e65c5` 自然CLI0、5068.265秒、进程已排空。283例逐例467业务表等值、84卡pending、零业务确认。最终独审246可接受、36普通失败、1关键失败，同批101为98/2/1；全部37失败ID、修正记录与汇总来源见 [M8-5-full052312-review-v1](../implementation-checkpoints/M8-5-full052312-review-v1.md)。结构与业务不变性不能抵消回答中的错误，本轮候选不通过。

A06把只返回原单号的两条售前记录补配成错误客户名，属于关键对象归属错误。其它已核问题包括静态目录被说成实际岗位预检、未确认的新员工工作门店被当必选、原入口与动作岗位混用、身份开通与识别卡办理混成必经链、保修与实际保养混用、精品收款附加客户确认前置，以及通用图表不存在的逐图导出入口。只修这些明确错误及同源说明，不因合理条件表达或非穷尽概述扩大失败范围。

## 精确允许范围

外部四源候选位于 `V/closeout-20261007/patch13-preparation/candidate`；登记清单为同目录 `manifest.json`。最终差异 SHA `b8d72390dc97fb6d0955e9a045c4a0d0831c3ee0e91f123cfa7fb19e2c761f26`：在初稿 `cceb64b7` 基础上，收窄当前快照的导出范围措辞，并补本轮HELP192参数发布分支。ROOT实施下列范围，保留其它内容：

- `app/business_assistant_gateway.py`：仅澄清静态目录岗位提示没有执行 `read_data` 预检或原GET；仅对成功、未截断的 `GET /api/visit-activity-reports` 已返回两张表、且原headers精确匹配时，追加 `visit_report_subject_context` 字段语义。区分原单号、原Case ID、原事件ID，明确未返回客户姓名。原data、行与route保持，不补客户查询或数据库关联，不扩大原授权。
- `app/business_assistant_prompt.py`：仅补消费上述字段语义、新员工实际工作门店须由管理员核实勾选，以及静态目录、实际工具预检、原接口拒绝的来源区别。未读同一原单客户事实不能补姓名；当前会话门店或其它员工配置不是新员工的授权事实。
- `docs/workflow-source/business.json`：`wf-insurance-order`仅在 `roles`、`entry.roles` 补原 `auditor` 读取岗，并追加其只读、不取得业务动作权限的说明；销售v3/v4报价签回及子单分支保持。`wf-vehicle-batch-import.prerequisites`明确请款、发运、到货各自原经办岗位，财务只读/付款不取得三类导入权限；`wf-repair-intake.manual[2].expected`明确开单后的主管批准、技师施工、财务实收和服务顾问本人步骤；`wf-retail-sale.prerequisites`明确原主管已批准报价后的真实收款条件，客户报价确认属于履约，不能增加为收款前置。
- `docs/workflow-source/services.json`：`wf-vehicle-reminders.manual[2].action`区分保修联系/维修与实际保养完成；`wf-member-card`只修身份开通和明确另办发行/挂失/换补识别卡的分支，只有真实卡申请才有该独立单确认步骤；`wf-member-renew-tier.prerequisites`明确等级调整仍需原申请单真实凭据和办理原因，不能保证其它事实自动带出。
- 同文件26条通用统计指引的 `manual[2].action`：`wf-report-134/135/137/138/139/140/141/142/146/147/148/150/151/154/155/156/157/158/159/160/162/164/165/167/168/169`，改为原图“明细”进入同源表后“导出明细”。专用库存、领退料、物资价值等页面确有原图导出，保持其现有路径。
- 同文件 `wf-parameters-password-brand.manual[1].expected` 仅明确业务参数按原发布或独立复核条件生效；问卷须由不同人复核批准后用于新问卷，不能统一说参数无需再审批。
- 同文件 `wf-report-143/144/145/152/153` 仅在 `roles` 和 `entry.roles` 补原 `inventory` 读取岗位；原数量读取与金额岗位范围分别保留，不增加动作权限。
- 通过原 `scripts/build_workflow_guides.py` 同步 `web/workflow-guides.json`、`web/workflow-handbook.html`、`docs/全量工作流手册.html`；193项映射、111条指引、入口、截图及原手册结构保持。
- 仓库外新增一个gateway原API测试节点 `test_visit_report_subjects_keep_native_case_facts_and_authorization`，核原已授权结果及上述字段元数据；`m85_runtime_live.py` 仅向有限 `REPRESENTATIVES` tuple 追加缺失的原失败ID，再登记selectors和相应来源、manifest/archive元数据。原场景文本、283/101、其它适配行为及评分、权限和业务状态机保持。门禁来源重绑与账本ACK另经独立候选审阅，不能由本补丁自动激活。
- 本补丁、`M8-5-full052312-review-v1`、`implementation_plan.md`当前M8.5/CP-37，以及两份architect进度文档。

## 异常路径与边界

售前报表缺表、headers不符、错误或截断时不制造字段事实；未返回姓名就按原单号说明。同一原单获权详情另有真实姓名时才可关联，route缺失不等于能读详情。保持原报表权限、定义、CSV和查询，禁止按行序、编号或其它候选补对象。

目录可见或静态不匹配不等于实际接口成功/403，也不生成评审refusal。员工门店未明确就等待管理员核实；管理员账号级权限仍不同逐店StoreRole。原保险、导入及维修页面可读不等于本人能执行各动作，各步骤仍按原岗位、原版本、真实事实和确认守卫办理。

只开通会员身份不默认发卡；另办识别卡及等级申请继续依原任务、凭据、原因和独立复核。保修或联系记录不制造实际保养完成事实。精品真实实收和客户履约确认分别记录，不重算可办状态或放宽原守卫。库存报表库管可读数量不代表可读财务金额或写库存；通用表导出仍按原同范围数据。26条说明不统一附加“同一期间”尾句，各原expected保持；当前待收、预收和客户车辆快照分别按原当前范围，不改称期间发生或历史期末。参数和问卷原发布、不同人批准与历史版本守卫保持。

## 审阅与后续

ROOT已按最终差异应用四源，收据为 `V/closeout-20261007/patch13-preparation/applied.json`；三生成物同步、原生成器build/check193/111、AST2/2及diff检查通过，发布指南源SHA `ddf297678e5d6d35e1dbfffc5c232c3d56748934eb22b58bbb9f9d5343689aae`。A4末次有限静审通过，`patch13-preparation/review-A4.md` SHA `98aa7bea0a0440bf9a7a3d4f1a4f9671063465db774089c0941df3cdbbc7a2da`；A3当前快照措辞阻塞已消除，各版审阅原件保留。

实现已落盘、有限静审通过；外部节点与selector登记尚未安装，隔离动态节点、新strict及真实模型复验待做。之后冻结新来源、同输入strict和经审来源重绑；只有明确ACK后才按原有限案例真实复验，问题消失后从零完整283并单列同批101逐例语义审阅。九代表、旧全量和本轮结构通过都不继承为新候选通过。400元/12000次、reserve5.242880元及全部旧费用/七未知保留；`total_plan.md`不改写。
