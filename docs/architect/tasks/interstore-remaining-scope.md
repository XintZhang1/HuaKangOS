# 跨店整车、物资与实际清算五项的只读后继范围

2026-10-01，当前M8.1。仅研究原193目录、发布工作流与当前原业务源码，不修改测试、生产、fixture、注册表、runner或计划，不导入app、启动实例或浏览器。本页没有执行成绩；所有建议check、六类人工标准和全部193仍待真实同轮验收。

## 精确范围与最小边界

| 原ID / 中文标题 | 固定完整check | 当前原合同所需事实 |
| --- | --- | --- |
| HK020 车辆调拨入库 | `HK-020-business` | 双方批准、源店实际dispatch、目的店accept，新Vehicle代次/原成本、Custody与双方Position/Movement历史一致。 |
| HK024 车辆调拨出库 | `HK-024-business` | 原目录除双方批准/实际发运/目的验收，还明确列reject→return_ship→return_receive；不能只验收一车即把此分支计为通过。 |
| HK047 物资调拨入库 | `HK-047-business` | 双方批准、源位实际发出、目的分批accept/reject、拒收原返；TransferMovement/StockMove/库位/在途/原成本逐批守恒。 |
| HK055 物资调拨出库 | `HK-055-business` | 原源店可用物资、双方批准、真实源位分配及dispatch，不能用目的接收替代源出。 |
| HK084 调拨出库收款 | `HK-084-business` | 明确原验收往来条目→付款店create/pay→收款店receive；双方实际Cash及原offset/占额/未清余额闭合。 |

两个主调拨原单的最小连贯路径是一车实际验收、一物资单分批接收并原返，再将两类实际验收来源逐条清算。这样可拟定完整020/047/055/084，024须保留partial：已经accepted的整车原单不能回退成拒收单。若登记五项完整候选，最小补齐是**第三张独立调拨单、第二个可用VIN**，走拒收/退运/原店新代次接收；这不是把未测条件自动改成建议覆盖。拟定场景 `interstore-original-hk020-024-047-055-084` 应在范围登记时明确选择上述两主单+第三单合同；本页不新增或改变catalog。

运输损坏/短缺、原损失、后来找回、赔付和清算撤销/差异等另列条件未测，不把这些附加分支硬扩进当前主链。原工作流 `wf-vehicle-transfer`、`wf-material-transfer`、`wf-transfer-clearing` 保留；读导航、空表及后台状态不算业务结果。

## 两店身份与原UI前置

`fixture_server.py:85–117` 有合成一店1、二店2。sales获两店销售岗位，其余manager/inventory/finance/service/technician只创建一店UserStore。已注册系统主链新增receiver仅二店service/第三店auditor，另一manager仍仅一店；这些员工不能替二店库管或财务。管理员全店访问也不能代办本批物理收发或资金事实。

最小前置建议：原admin在 `#users` 明确新增三位随机二店合成员工，账号默认sales保持，逐店只勾二店并分别选择manager/inventory/finance；POST `/api/users`，不修改现有账户及权限。三人各在独立原生context首次登录、本人原改密、再登录，GET `/api/auth/me` 核账号岗位sales与当前店岗位的区别、仅二店可选且当前store2。随机初始/新密码仅写runtime私密文件，动态加入整份Evidence.scrub秘密集合；日志、checkpoint不含密码/hash/session。

二店前置全部原UI生成，不借跨店FK：

- inventory2在 `#masters/warehouses` 与 `#masters/locations` 建本店vehicles仓/库位、materials仓/库位，POST `/api/masters/warehouses`、`/locations`。明确不同类型和本店warehouse_id；不以mixed模糊两个用途。
- manager2在 `#master/accounts` 新增本店启用bank账户，POST `/api/flow/master/accounts`；该主档原写岗位是admin/manager，不能让finance2猜有新增权限。finance2随后只读确认本店账户、名称、id与当前版本。
- inventory2在 `#master/items` 创建明确接收物资。为已启用仓位完整链，SKU、name、unit与选定源Item**均相同**，id/store_id不同、quantity/value起始0。原receive只验证名称/单位；原warehouse allocation_options目的项按SKU筛选，所以只匹配名称还不足以完成真实库位准备。
- 该二店Item沿 `#warehouse` 原activate数量0/明确本店materials库位→manager2独立approve，产生Enrollment与零Balance，不造StockMove/库存价值；配置没有实物入库成绩。无需复制一店brand/category/supplier等FK，也不静默配置经营主体策略。

三位二店新员工仅是待原UI创建前置，不是已存在来源；不用SQL、fixture或管理员权力制造业务完成。原user创建、首次改密合法audit须发生在每次业务baseline之前，所有旧员工/UserStore、权限配置及其他店原行保持。

## 同轮有限父来源与现场准入

必须用 `fixed_dependency` 和固定 `evidence_root/<scenario>/business-checkpoint.json`：同一次镜像/provenance、catalog hash与源码/脚本指纹，父场景整体passed、checkpoint complete且其各check通过；禁止扫旧run/取latest行。建议固定父来源：

1. `vehicle-purchase-hk171-177-178-026-021-018-029`：原账户id、店1整车仓/源库位和采购事实。仅借真实主档来源，不把已有采购结果重新发运或接收。
2. `vehicle-import-operations-hk019-027-028-030-025-023`：`report_sources.current_vehicle_id`、`final_A`（原other_return后的**新代次**）、source/destination_location_id、account_id。B已退供应商，`original_vehicle_ids[1]`不能拿来调拨；A旧代次也不能继续使用。当前父候选曾遇上传观察限制，未来仅新鲜整体passed后可成为本链依赖，本页不继承其局部动作。
3. 五项完整时再依赖 `sales-cancellation-hk010` 的 `report_sources.cancelled_vehicle_id`，现场重读无Sale.active_vehicle_id/VehicleHold、无采购退回/VehicleOperationClaim、Custody当前归属一店、approved及stored。它仅是第二VIN候选，拒绝使用已交付车辆；若已被后继占用，停止并登记缺前置，不能换旧表最新车或重置原单。亦可另登记原UI新采购第二可用VIN前序，但不可自行扩写fixture。
4. `materials-hk069-045-054-083-070-072-073-051-061` 的 `material_sources.primary`（同时为report_sources）：item_id/sku/name/unit、source_location_id、enrollment_id、purchase_order_id/receipt_ids、StockMove/Entry/Balance有限IDs。其checkpoint数量是历史快照；先用原GET `/api/flow/master/items`、`/api/warehouse/items/{item_id}/stock` 重读当前可用量、库位、成本与版本，至少可用1000 milli且该源位可发1000；不足立即停，不把赠金/物资占额或纯账面数量当可用。
5. `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187` 的一店materials仓/位等原主档来源只作读回核对；二店主档不得复用其id。`system-management-hk189-191` 不提供二店所需三岗位，可复用其中少量原create_staff/native_login/personal_password观察方法，不能因此依赖其receiver的service权限。

原GroupIdentity/Custody是明确共享车辆身份，不能改Vehicle.store_id造跨店；物资接收为独立二店Item，不能将源Item移到二店。现场所有读先登录完成并核当前store/role，再建原行baseline。

## 整车实际验收主单

原UI `#vehicle-transfers`，`data-act=vehicle-transfer-new` → 本店原可用vehicle_id、destination_store_id=2、due_date/原因 → POST `/api/vehicle-transfers`。生成一个VehicleTransfer、两个本店Case(kind=vehicle_transfer,flow_version=2)、两本地vehicle_approve Task；Case/Task owner由原eligible_users创建，候选不得默认人员或借admin跳过本人Task。Custody.pending_transfer_id明确占用，旧Vehicle身份与成本snapshot冻结，申请没有现金或目的库存。

一店manager、二店manager各从本人当前店 GET `/api/vehicle-transfers/{id}` 取transfer.version与本地case_version，实际点击“批准本店安排”；申请为inventory1，与两批准者不同。原API `/{id}/actions/approve` 的values仅reason。批准一方不提前产生另一方批准事实，双方完成才approved；Task不属本人时由本地主管原 `POST /api/flow/tasks/{task_id}/assign` 按version/assignee_id/reason交接（该AssignInput没有request_id）。

inventory1在本店from_case_id上传实际合成evidence，回原调拨“核对实车并发出”，填原VIN、evidence_id/reason。`dispatch`：原Vehicle仅approval_state void/updated/version、源Position exited及负PositionEntry、Custody current_vehicle_id/current_store_id置空、pending保留、generation不变；VehicleMovement为quantity=-1/value=-C，status=transit。实物在途两店不可配售；旧VIN/采购/售价/成本/代次不得覆盖，不能累加Position与Movement把同一发车计两次。

inventory2只用自己to_case_id上传的新evidence，点击“验收车辆入库”并填同VIN/本店车辆库location_id。`accept`：新二店Vehicle id、generation=g+1、成本C、原snapshot字段及明确location；GroupIdentityLink接同identity；Custody指新Vehicle/store2并清pending；新Position/Entry及Movement +1/C，status accepted。两个VehicleTransferSettlement分别一店+C、二店−C，只有实际accept产生。双方Case终结并结束任务，原source Vehicle/Position/分录保留；不是修改源Vehicle.store_id，亦没有现金到账。

每次action都是原POST `/api/vehicle-transfers/{id}/actions/{action}`，封包 `{request_id,version,case_version,values}`。所有值取本次原GET及原UI，不固化上一员工版本。物理动作values为 `{vin,evidence_id,reason}`；accept/return_receive另location_id。当前在办transport exception会停普通动作，不另造allowed_actions绕过。

## 第二VIN拒收原返：完整HK024准入

若登记五项完整，以第二可用VIN建**另一原VehicleTransfer**并各店独立approve→源dispatch。二店本人evidence与同VIN“拒收车辆”→“确认退回发运”，一店本人evidence/原VIN/库位“确认退回入库”。状态依次transit/rejected/return_transit/returned；reject/return_ship各Movement quantity/value为0且vehicle_id null，不产生目的Vehicle或settlement；return_receive新建一店Vehicle新代次g+1、原成本/identity/原返来源，Custody归回一店并清pending。旧source代次仍void，旧Position/分录不覆盖。没有实际accepted往来，所以该拒收单不新建清算或现金。

此分支当前not_tested且完整024不可跳过；只有两主单候选时明确记录HK024 partial和所缺原返，不提交完整 `HK-024-business`。VIN不符拒绝、审批撤销/拒绝、重复提交、损失/找回另列未测，不把拒收原返当损失补车。

## 物资分批接收与原返单

原UI `#transfers`、`data-act=transfer-new` → 源原Item，quantity=1.000（1000 milli）、destination=2、日期/原因。POST `/api/transfers` 原封包 `{request_id,destination_store_id,due_date,reason,lines:[{item_id,quantity_milli}]}`；新MaterialTransfer、冻结TransferLine、双方Case(kind=material_transfer,flow_version=3)、原transfer_approve任务。一店inventory申请，manager1/manager2各从本店GET当前双版本批准；不能把另一店批准当本店批准。

源inventory在from_case_id通用页“准备物资库位”原POST `/api/warehouse/allocations/{case_id}`，purpose=transfer_out、quantity_milli=-1000、locations实际源位数量1000。prepare只位置计划/Case版本/原事件与FlowRequestReceipt，不改Item/库存/StockMove；再当前transfer GET核本地case_version后，原“确认实物发出” dispatch。源真实StockMove quantity=-1000/value=-D，D=发运前Item.inventory_value_cents×1000//Item.quantity_milli；源Item/各Balance量值及原WarehouseEntry守恒。TransferMovement dispatch quantity=1000/value=D，原库存在途，不先写目的库存。

二店原Item已同SKU/name/unit且零启用。第一批在目的to_case_id通过原库位表单准备transfer_in +500，再回本店原调拨刷新双版本，“分批验收” accept_milli=500/reject_milli=0/item_id=目的Item。第二批另prepare transfer_in +250，再原receive accept250/reject250；UI实际输入0.500/0.250，原网络精确整数milli。每批Receipt事实是原TransferMovement accept及StockMove transfer_in，不编造不存在的独立收货状态；两个accept各为对应原dispatch.id的original_id，目的各原库位实际入500/250。

三版portion采用原批累计整数分配：first=floor(500D/1000)，second=floor(750D/1000)−first，reject=D−floor(750D/1000)。不得套零售平均成本四舍五入或按后来的Item.unit_cost重新定旧批成本。每个accept分别生成双方TransferSettlement（一店正、二店负），reject没有目的StockMove/settlement。目的stock已750，拒收250仍在途，不变为二店可用库存。

inventory2原“拒收物资发运退回”选择本次rejectMovement.id（rejection_id），生成return_ship引用该reject；没有实际入库或现金。一店prepare transfer_return +250对应源Item/实际位→原GET当前版本→“确认退回入库”，values={shipment_id:本次return_ship.id,quantity_milli:250,passed:true,evidence_id,reason}；三版必须员工明确质量合格。StockMove transfer_return.original_id引用原dispatch.stock_move_id，TransferMovement.return_receive.original_id引用return_ship.id；原250/剩余原成本回一店，不能拿目的accept作退回来源。最终本单completed：源净减750、目的实入750、在途0、无loss，dispatch量值=accept合计+return_receive，双店Task结束。

原actions接口 `/api/transfers/{id}/actions/{action}` 同样 `{request_id,version,case_version,values}`；approve只reason，dispatch evidence_id/reason，receive逐line_id/item_id/accept_milli/reject_milli，return_ship rejection_id，return_receive上述三版schema。UI没有inline准备控件，沿本地通用Case的原库位入口先保存再回调拨；不要调用后台allocate来省点击。

## 两财务各店实际清算

独立批准指前述两店调拨批准；当前清算没有approve动作，不虚构第三个资金审批状态。原READ=admin/manager/finance/auditor，create/pay/receive为本店finance/admin；本候选由finance2付款、finance1收款，管理员不代办。

二店 `#clearing` 原GET `/api/reconciliation/origins` 只选择当前三个**负向原往来条目**：整车accepted的二店VehicleTransferSettlement，以及物资两次accept的二店TransferSettlement。origin_id是具体Settlement.id，**不是transfer_id、Movement.id或Case.id**；两批物资不能汇成一个伪造origin。每一原条目分别点击“申请本次清算”，POST `/api/reconciliation/clearing` `{request_id,origin_kind:'vehicle'|'material',origin_id,amount_cents:该原未清全额,due_date,reason}`。

每份ClearingBucket唯一冻结双方原正负条目；ClearingOrder及双方Case(kind=interstore_clearing,flow_version=2)/finance Task，reserved增加、settled0，现金0。现场核payer_store_id=2/receiver_store_id=1与正确配对；材料按同movement_id配对，整车按同transfer/原金额配对。若某合法验收份额价值为0，原清算只允许正金额；该份不造0元Cash/清算，应保留实际原库存数量和零价值事实并由正值来源完成084。

finance2本地payer_case_id上传receipt，当前Clearing.version+本地case_version，点“实际付款”pay，values={account_id:二店账户,reference:本次独立流水,evidence_id,reason}。原单固定全额，不另填伪amount；产生二店CashEntry direction out/category interstore_clearing/approved及一ClearingCash，status paid；bucket仍reserved、settled0、无offset，付款在途不是对店已到账。

finance1换独立context当前一店，GET同clearing.id取新双版本，在receiver_case_id上传本店receipt，用一店原账户/另一实际流水点“实际到账确认”receive。新增一店CashEntry in与ClearingCash；bucket reserved归0/settled增本原金额，ClearingOrder settled，双方ClearingOffset（一店负向offset对应原正应收、二店正offset对应原负应付），双方Case completed/本任务done。旧两边Settlement及旧Cash不覆盖；每份正金额清算恰两笔实际Cash、两Offset，没有GroupMember/集团中心付款或经营收入。原收到前无offset，收到后未清0，可在原页/同范围经营报表核内部现金另列，不能将两店款净额0冒成未付款。

API `/api/reconciliation/clearing/{id}/actions/{pay,receive}` 封包 `{request_id,version,case_version,values}`，ReconciliationReceipt.family独立；没有额外FlowRequestReceipt或GroupReceipt。物资/整车原调拨共用transfer_service.execute的 `material_transfer_receipts`，不能按名称误造VehicleReceipt。库位prepare和普通任务交接仍保留各自原合同。

## 附件、有限Guard与未测缺口

所有正向附件分别由当前店员工上传到本店对应from/to或payer/receiver Case，再从原字段选择。`transfer_service.evidence`/`flow_engine.file_exists` 要求实际非generated可用FileAsset、同本地case_id；共用调拨id或看见对方Movement不授予对方文件读取/写入权限。跨店DossierGrant只读授权亦不能把外国Case的file_id当本店写动作证据。

若后续验收必须读对方原交接附件，另登记原 `#dossier-grants` 有名收件人、明确file_ids/用途/有效期、source_case_version→独立原店主管批准→本人接收后的 `/api/dossier-grants/{grant_id}/files/{file_id}`。默认不包含原financial/contact/record；相应权限和到期/换岗即时重验。原 `interstore_clearing` 在dossier EXCLUDED中，不使用通用共享绕过；两清算店必须保管自己的实际款凭据。本主链不需要读对店文件，不把未执行授权记HK190或跨店附件通过。

静态显示待复现：`vehicle_transfer_service.py:97–101` 当前给双方Movement都带evidence_id，`web/vehicletransfers.js:14` 对每条都渲染普通downloadfile按钮；普通 `/api/flow/files/{id}` 先本店scope并get_case/can_file，二店无grant不能下载一店原文件。物资serialize已只给本店Movement.evidence_id，UI对方显示“由对方保管”。车辆这一入口不一致应在实际跨店IAB观察，未证实产品运行结果；不能用admin下载或放宽后台守卫求通过。

每步全business snapshot保护所有表和旧行，合法登录/audit后才baseline。只有当前双方Case/Task的实际同步列、当前Transfer.status/审批者/version/updated、明确源及目的Item/Balance/Allocation列、选中Vehicle/Position/Custody版本/实际归属列，以及当前Bucket/Order/Account列可改；不能只允许单一店Case而误拒合法服务同步，也不能粗放全部店全部Task。源item和两个明确接收批的成本按原算法逐项核对，Warehouse average_revaluation分录按同Item有限Balance允许；旧StockMove/Entry/Settlement/Cash/File/Origin/Receipt历史不可删改。

每个新append核真实store/actor、双方协调新增Case/事件的原source actor、case_id/transfer_id/line_id/original_id/stock_move_id/source Vehicle与新的目的代次、资金original配对。全库旧行/BLOB只在内存比较，报告仅附件metadata/size/SHA；不输出bytes/base64/default=str、用户password_hash或私密凭据。request_id/digest/result按正确回执家族验证；一次原提交，结果未知停止并保留请求编号，不切新id重放。

尚未执行条件分别保留：第二VIN/024原返前置；3名二店人员及首次改密；二店仓位/零启用/账户；当前原源可用量/成本；错误VIN/名称单位或SKU不匹配/超量/禁用/重复/CAS/角色变化；审批拒绝与未发撤销；短缺损坏、return质量不合格、loss/recovery；清算部分金额/未付款reject/cancel/已付款差异及真实银行；跨店指定文件授权/到期/撤销、PG/Linux/ClamAV/员工试用/真实模型。以上没有自动或人工通过成绩。

## 源定位与静态冻结

- `app/vehicle_transfer_api.py:11–37` / `vehicle_transfer_service.py:88/131/196`、`vehicle_transfer_models.py`；`web/vehicletransfers.js:6/16/21`。
- `app/transfer_api.py:13–62` / `transfer_service.py:32/166/192/229/281`、`transfer_models.py`；`web/transfers.js:8/19/28`。物资portion另核 `transfer_exception_service.py:116/121`、`transfer_exception_math.py:4/26`，不导入服务运算。
- `app/warehouse_service.py:328/350`、`warehouse_stock.py:96/113` 与原 `web/warehouse.js`；`flow_api.py:294/214`、`flow_engine.py:410`、`flow_documents.py:49`。
- `app/reconciliation_api.py:29/68/75`、`reconciliation_service.py:428/455/477/541/565/587`、`reconciliation_models.py:57`；`web/reconciliation.js:77/84/89`。
- `tests/browser_click/fixture_server.py:85–117`、现父候选report_sources与 `business_acceptance_catalog.json`；`docs/workflow-source/business.json` / `services.json`。原 `system_management_business.py` helpers和权限结果只读。

静态HEAD为 `8993ca8c755194a42a48e7323fe355e80c6bf9ae`，工作树含根与各作者未提交改动；不以HEAD代表同镜像指纹。关键28路径内容摘要在交接报告，用排序path:bytesSHA256加LF再SHA256计算；本页最终hash另报，避免自引用。未来作者须登记精确文件范围并复核当时来源，根统一接线/新鲜真跑后才有实际check结果。
