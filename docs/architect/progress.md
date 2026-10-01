# 当前交付任务

最新完整结果：automatic-business09已退出0，同次28/28、84完整自动业务check，5208动作/2560点击，生产1597eb7b/脚本7cc1267d、镜像稳定。销售后续四项及财务五项首次整场景通过；页面异常/外部尝试0、16合成/0真实模型。193完整及全部业务人工接受仍false/0，保险七项和开票/核账两项未注册。详细当前事实见v5；下文各阶段保留为历史。

后续更新：automatic-business08完整27执行26通过/销售HK017原任务渲染装置失败（GET200、点击尚未发生），75完整自动check/3销售局部另列，整体failed。人工domain02同指纹定向维修/接待六项3/3/3/4/3/3，469表原业务不变，已结束实例。根TASK-RENDER-01只补真实页面等待，经独立短审；财务五项已审阅注册，当前28场景automatic-business09运行中，不预写通过。保险七项独立候选冻结短审、开票/核账两项独立编写，均未注册。详细追加见v4，下文皆保留历史阶段。

最新完整结果为v4：automatic-business07同次24/24、71自动业务check、3608动作/1853点击，生产68ef5e1b/脚本60a0bef1。人工同指纹domain01在已接车维修和已转换接待发现错误等待文案、长规则常驻，失败保留并结束实例。根按REPAIR-DISPLAY-01窄修、独立短审，现27场景automatic-business08和同指纹manual-domain02运行中，不预写新成绩。销售四项/维修后继四项已审阅注册，财务五项/保险七项仍候选；193完整及人工接受false。下文阶段记录属于历史。

最新运行追加：automatic-business06完整23执行22通过/维修BLOB证据装置失败，只有60项完整自动业务check（维修两局部诊断不计）；failure保留。根修附件metadata/原子记录后，repair01物资前序库位SQLAlchemy通用409失败，维修未启动；按WAREHOUSE-PREP-TRANSACTION-01复用写事务在认证读取前开始，独立短审与AST通过，仍不自动重试。会员5项已冻结窄审注册；最新24场景automatic-business07及同指纹manual-domain01体验实例运行中，暂无联合/人工结果。下文“当前23/待出”保留该阶段历史。

2026-10-01 按需求表继续193项实际业务。最新完整通过仍为v3的16/16、29项自动检查；之后automatic-business05完整21项执行20通过/物资装置失败，不能继承成全套通过。客服4、销售交付/退订5及报表11已在同次选定sales-reports05完成，物资九项在material-system01完整本场景通过（同次系统装置失败），系统两项在system04定向通过。三类装置问题按原UI/审计/路径修正，失败原件保留。当前注册23场景，新增维修六项独立短审后首次联合运行automatic-business06；尚无本轮联合结果。会员五项及交车后四项为未注册候选，未计成绩。193完整业务与人工体验、原环境/员工门槛仍未验收。下列旧成绩只属于当时指纹。

2026-09-30 本轮代码与实际浏览器点击交付已完成：自动13/13、193检索/111指引/70原页面/9表单，人工同指纹六项评分达到最低标准。最终审阅见 `docs/implementation-checkpoints/M8-4-browser-click-checkpoint-v2.md`；原里程碑/门禁仍只以实施计划为准，193完整业务及原环境/员工条件尚未验收。

| 任务 id | 目标 | 负责人 | 任务记录 |
|---|---|---|---|
| browser-click | 当前实现收口、旧测试/CI 清理与真实浏览器点击验证 | Codex | [browser-click](tasks/browser-click.md) |
| browser-fixture | 新隔离 HTTP 服务、合成模型、运行入口与 CI | test_inventory | [browser-fixture](tasks/browser-fixture.md) |
| browser-scenarios | 真实点击场景、数据库对照及统一评价 | click_scenarios | [browser-scenarios](tasks/browser-scenarios.md) |
| requirements-coverage | 原需求表核验、193 项到真实页面的分层覆盖清单 | test_inventory | [requirements-coverage](tasks/requirements-coverage.md) |
| domain-read-details | 本轮原对象详情与生产修复的代码复核 | remaining_audit | [domain-read-details](tasks/domain-read-details.md) |
| business-193 | 按最新要求继续全部193项实际业务点击与文案验收 | Codex | [business-193](tasks/business-193.md) |
| business-acceptance-inventory | 193项实际动作/API/后端事实验收合同 | remaining_audit | [business-acceptance-inventory](tasks/business-acceptance-inventory.md) |
| sales-business-click | 售前接待至跟进提醒的原UI业务路径 | click_scenarios | [sales-business-click](tasks/sales-business-click.md) |
| business-fixtures | 当前业务增量所需最小合成前置 | test_inventory | [business-fixtures](tasks/business-fixtures.md) |
| vehicle-purchase-click | 主档、两车型采购、独立付款、两VIN验收及非空库存查询 | click_scenarios | [vehicle-purchase-click](tasks/vehicle-purchase-click.md) |
| master-data-click | 七类字典、原主档启停及零库存物资真实关联 | remaining_audit | [master-data-click](tasks/master-data-click.md) |
| customer-service-click | 客户档案及咨询、投诉、救援原单的实际办理 | remaining_audit | [customer-service-click](tasks/customer-service-click.md) |
| sales-order-click | 原销售交付与独立取消退款 | click_scenarios | [sales-order-click](tasks/sales-order-click.md) |
| report-business-click | 同轮真实业务来源的非空报表与导出 | test_inventory | [report-business-click](tasks/report-business-click.md) |
| material-business-click | 原物资预付/采购/到货/退货/盘点/移库首链 | test_inventory | [material-business-click](tasks/material-business-click.md) |
| repair-business-click | 同轮客户车辆及物料到原维修接车首链 | click_scenarios | [repair-business-click](tasks/repair-business-click.md) |
| system-management-click | 新合成机构、员工与当前岗位会话及审计子范围 | remaining_audit | [system-management-click](tasks/system-management-click.md) |
| membership-business-click | 原会员本金、原款退款和卡状态首链候选 | test_inventory | [membership-business-click](tasks/membership-business-click.md) |
| sales-followon-click | 原交车后加装、代办及两源其它收入候选 | remaining_audit | [sales-followon-click](tasks/sales-followon-click.md) |
| repair-followon-click | 原洗车、快捷维修与客户直接报销候选 | click_scenarios | [repair-followon-click](tasks/repair-followon-click.md) |
| finance-business-click | 客户预收及更正、非空应收、原款退款与分笔月结候选 | test_inventory | [finance-business-click](tasks/finance-business-click.md) |
