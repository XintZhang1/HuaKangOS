# 跨店原调拨与双方实际清算点击候选

2026-10-01，M8.1，按 `PATCH-M8-4-BUSINESS-193-26.md` 和已冻结 `interstore-remaining-scope.md`（SHA256 `79d5c985eae4c57d3f007685a79c6bec9ab773087a7502ccb084a34cec69bfea`）编写。作者仅新增 `tests/browser_click/interstore_business.py` 与本页；没有修改生产、fixture、helpers、目录、runner、注册表或计划，也没有导入app、启动服务/浏览器或执行验证。本文不登记实测通过。

## 精确五项与入口

候选导出 `INTERSTORE_SCENARIOS=(("interstore-original-hk020-024-047-055-084", interstore_business, 1500),)`，有限超时1500秒。五项各有独立原check，异常时当前项failed、其后not_tested，未完成整场不产出passed来源。

| 原ID / 标题 | 固定check | 输入到结果边界 |
| --- | --- | --- |
| HK020 车辆调拨入库 | `HK-020-business` | 原当前代次A、双方本店主管批准、源本人实车发运、二店本人实际验收；新代次、Custody/Position、原成本及双方往来一致。 |
| HK024 车辆调拨出库 | `HK-024-business` | 主单实车发运外，第二独立可用VIN原单批准/发运/拒收/退运/原店新代次验收；拒收单无验收往来或现金。 |
| HK047 物资调拨入库 | `HK-047-business` | 同原1000milli发运批，两次实际合格入500/250、第二批拒250、原拒收退运、源质量合格入250；净750与原批成本守恒。 |
| HK055 物资调拨出库 | `HK-055-business` | 原Item/实际源位当前可用至少1000，双方主管批准、本地库位准备、本人实际dispatch与唯一StockMove/Entry。 |
| HK084 调拨出库收款 | `HK-084-business` | 一个整车及两个物资accept的三个负向Settlement逐笔申请清算，二店本人pay、一店本人receive；六笔唯一Cash、六offset、原占额归零。 |

## 同轮有限前序与schema

直接父报告固定五条：采购 `vehicle-purchase-hk171-177-178-026-021-018-029`、主档 `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187`、物资 `materials-hk069-045-054-083-070-072-073-051-061`、车辆作业 `vehicle-import-operations-hk019-027-028-030-025-023`、退订 `sales-cancellation-hk010`。每条须本次runner场景passed、business-checkpoint完整及全checks passed，并核同catalog、provenance和冻结脚本字节；禁止扫旧run、取latest或继承未通过父候选。

最短实际执行闭包另含 `sales-presales-hk001-007` 与 `sales-order-hk008-009-011-022`，共七前序加本场景；次序依原父依赖。候选只消费采购HK021真实账户、作业 `report_sources.current_vehicle_id/final_A/source_location_id`、退订 `report_sources.cancelled_vehicle_id`、物资 `material_sources.primary` 的item_id/sku/name/unit/store_id/source_location_id。B须现场无hold、未退供应商、无active操作或销售占额；A必须原作业返入的新当前代次。源库存报告快照不是当前可用量，每次实际源GET与DB重读；两接收份额原累计整数分配均须正值以形成三笔正清算，不猜填成本。

身份前置全部原UI：原admin只新建三名随机二店manager/inventory/finance，账号默认sales、初始空勾店、明确只store2并选本店岗位；三个独立context本人首改密码再登录。全部动态初始/新密码先加入整份 `Evidence.secrets` 脱敏，只写本次外置runtime私密文件，不进入checkpoint/观察、源码或证据正文。业务实际由对应本店人员办理，管理员不代批、收发或付款。

二店库管原typed页面新vehicles/materials两仓两位、原物资目录同SKU/name/unit零Item；二店主管新增bank账户，并独立批准原零activate。零启用只Enrollment/零Balance，严禁StockMove/Entry/现金或预制接收。每次合法登录完成后才baseline，不排除login审计来掩盖变化。

成功后的 `report_sources` 仅保存有限ID：source/destination_store_id，destination_users三岗位ID，source/destination_account_id、目的vehicle/material_location_id，source/destination_item_id；accepted/rejected_vehicle_transfer_id、received/returned_vehicle_id，material_transfer_id及本单movement/accept IDs，按vehicle/material分类的原Settlement IDs，三个clearing_order_ids、六cash_ids、六offset_ids、destination_zero_activation_case_id。`manual_review="pending"`、`full_193_business_acceptance=false`；不输出User hash、Cookie/session、文件BLOB或密码。

## 原提交与保护合同

整车 `/api/vehicle-transfers`、物资 `/api/transfers` 的create/actions各沿原UI与当次本店GET，使用真实request_id、transfer.version和本地Case.version；Task若非本人，仅本店主管原 `/api/flow/tasks/{id}/assign` 三字段version/assignee_id/reason，没有request_id。库位原 `/api/warehouse/allocations/{case_id}` prepare只位置计划，实际dispatch/receive/return_receive才StockMove与Entry。三版物资成本严格累计floor：第一500、累计750差额、余250，原返库存original_id指原dispatch StockMove。

调拨原回执为 `material_transfer_receipts`（整车同家族）；清算为 `reconciliation_receipts`，库位为 `flow_request_receipts`，typed主档为 `master_receipts`。分别核精确本人/店/request/digest/result；不额外要求不存在的FlowReceipt。清算原负Settlement.id是origin_id，物资按同movement_id配对，整车按同transfer_id配对；pay只本店现金在途、receive才双offset/settled。原现金category为interstore_clearing，独立账户、流水号、凭据和当日，不能用后台结束Task冒实收款。

每一步全business哈希和全部旧行逐列保护。仅当前双方Case/Task、明确Transfer/Custody/Vehicle/Position、选中Item/同Item有限Balance/本单Allocation、当笔Bucket/Order/Account的原合法列可改；追加数量和case/item/VIN/transfer/order/actor/store有限核对。物资完成时原服务 `close_tasks` 将剩余Task标cancelled并记done_by，本Case仍completed，候选精确保留原语义。旧Cash、StockMove、Entry、Settlement、Origin、Receipt及文件原字节不可覆盖删除。上传分别只本店本单、原非generated TXT，报告仅metadata/size/SHA，结构检查可用不等于ClamAV通过。未知提交结果立即停止，不自动刷新换request_id重放。

## 静态审阅与待实测

作者逐读原transfer/vehicle_transfer/reconciliation/warehouse的API schema、service、models、原web控件及复用helper。仅stdlib静态解析：候选AST通过；21个复用helper符号、207处调用签名核对；16处直接SQL均SELECT；单一三元入口1500秒、无app导入/执行、UTF-8无BOM/尾空白核对通过。候选1307行SHA256 `b389cc6f1ca44588abb8cd7f5620d3e0955fe48b032862769816c633dab35632`，本页最终指纹另报避免自引用。自审已纠正库位回执无result、零启用批准原plain-select、物资完成Task关闭语义、原Receipt.shipment_id查采购退回占额、本次evidence_root/provenance路径、原导航折叠与独立context恢复，未降低原守卫；独立短审待根安排，静态通过不作为动态成绩。

动态控件展开/lookup/CAS/双店角色、multipart响应及同轮真实库存成本仍未执行。原车辆流水仍渲染对店ordinary download入口而后台本店scope，是否出现无授权可点/拒绝需根实际观察另登记，候选不下载对店文件或借admin。调拨和清算普通POST仍原get_db，任何真实并发冲突保留原请求与日志另诊断，不在此候选改事务、重试或虚构错误码。

其余未测条件：错误VIN/超量/角色变化/CAS，审批拒绝与未发撤销，运输短缺损坏/退回不合格/损失找回，清算部分金额/差异/已付撤销，跨店有名文件授权及失效、真实银行、PostgreSQL/Linux、ClamAV、员工试用和生产。全部人工流程简洁/文案标准pending；自动断言即使未来通过也不自动business_accepted，更不代表193全量完成。
