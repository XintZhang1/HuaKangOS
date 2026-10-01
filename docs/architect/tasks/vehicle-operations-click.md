# 车辆导入与单店实物流转六项点击候选

2026-10-01，按 `PATCH-M8-4-BUSINESS-193-20.md` 及冻结范围 `inventory-next-scope.md`（SHA256 `35bc5eaa05359f0c3cf54344a0e6a7802e63e78ac9de388afe4dcaf341496c8e`）编写。仅新增本页和 `tests/browser_click/vehicle_operations_business.py`，未改生产、共享 runner/scenarios、fixture、目录或实施计划。候选未注册、未启动应用或浏览器、未导入 app；作者静态检查不记执行通过。

候选入口 `vehicle-import-operations-hk019-027-028-030-025-023`，导出 `VEHICLE_OPERATIONS_SCENARIOS`，720秒资源上限。六个完整自动检查分别为 `HK-019-business`、`HK-027-business`、`HK-028-business`、`HK-030-business`、`HK-025-business`、`HK-023-business`。输入与款项、实物均为外部隔离实例的明确合成资料，不代表公司实际业务。自动 UI/API/DB 核对通过仍须单独人工评价流程及文案；所有 `business_accepted`、`full_193_business_acceptance` 保持 false，人工 pending。

## 同轮依赖及精确 schema

仅读取本次 evidence_root 的 `browser-click-report.json` 与以下固定 `business-checkpoint.json`，核对 expected_scenarios、场景 passed、完整 requirements、源合同 SHA 和可用 provenance；不扫描历史目录，不挑 latest，不从已履约旧采购再发请款。

| 固定前序 | 必需字段 |
| --- | --- |
| `vehicle-purchase-hk171-177-178-026-021-018-029` | `requirements[HK-171].acceptance_checks[0].evidence.supplier`（typed Supplier 的 id/store/code/name/active）；HK177 evidence 的 `new_hierarchy.model` 与 `existing_hierarchy_new_model.model`（两个确切车型）；HK178 的 `warehouse` 与 `location`（vehicles 仓及真实 warehouse_id）；HK021 的 `payment.account_id`（本店启用 bank Account）。原账户版本须当前重读，不拿旧版本当当前余额。 |
| `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187` | 本次整场 complete/passed、十五项通过及原合同指纹，作为本轮主档前序；不重复计 supplier/model/车辆仓检查。 |
| `manifest.business_fixtures.vehicle_purchase` | store_id、manager_key、inventory_key、finance_key；admin 使用现有 `manifest.users.admin`，仅作为资金清单的独立主管复核，不替代库管或财务。各岗位实际登录、Cookie/CSRF/store 独立核对。 |

库管通过原主档页新增同仓第二库位，使用实际可见 warehouse lookup；这是移库前置，零实车配置，不追加 HK178 成绩。两辆新 VIN 为合法17位随机合成输入，已有 VIN 时停止。原 UI 新建两行采购各1台，独立 manager 冻结成本1000/2000分、建议价1200/2200分；本金支付为 finance 原两笔10/20元。同原批准来源输入，不手工造资金或库存状态。业务日显式按 fixture Asia/Shanghai 计算，不依赖主机 UTC。

## 原业务输入至结果

| 检查及原题名 | UI/API/原事实 |
| --- | --- |
| HK019 车辆请款导入 | 新采购 `#vehicle-procurement/{case_id}`，原 approve 冻结两行；manager 到 `#vehicle-imports/{case_id}` 选择 funds CSV，原 multipart `POST /api/vehicle-imports/orders/{case_id}/batches`。预检 prepared，trial → 不同 admin review → 原 manager confirm，分别原 `/batches/{id}/actions/{action}`；每行真实 FundsRequest/ImportResult，未造 Cash、Shipment 或实车。另新已知重复 VIN 清单预检 invalid，错误逐行可见、Claims/Results 均0，没有第二请款；其自身来源/日志保留。 |
| HK027 请款导入车辆发货 | 两筆 finance 原 pay、receipt、账户和流水先实际产生。库管原页面读取本次 confirmed funds manifest，金额/文件不给库管；ship CSV 使用实际 manifest 行 ID/VIN/今天发运和预计日。trial 回滚 → manager 独立 review → 原 inventory confirm；真实 Shipment 在途、Custody gen0/无当前库存，原预付3000分、验收0。 |
| HK028 请款导入车辆到货 | receive CSV 使用本次已发运同VIN的 manifest 行、今天实际收车和本店源库位。三步核验后2个 Receipt/Movement；两唯一库存 Vehicle gen1、Custody 当前店及 Vehicle ID、GroupIdentityLink、Position、purchase_receive 位置分录和冻结成本均匹配。库位分录 inventory_delta=0，采购 Movement 另记门店实车；收齐净款/实车结清。 |
| HK030 车辆店内移库 | A 原 Vehicle ID/gen1，原 `#vehicle-operations` 建 local_move，经另一 manager approve，inventory dispatch 实际同店在途，目的位 accept。`POST /api/vehicle-operations/orders` 及 `/orders/{case_id}/actions/{approve,dispatch,accept}`；local_dispatch -1 与 local_accept +1 原关联，数量/价值/门店 inventory_delta 和为0，同车、同代次、原成本不变。 |
| HK025 车辆其他出库 | A 从新位置建 other_out，明确接收/处置去向、独立批准、库管 dispatch；旧 Vehicle void、Position exited、Custody 当前车/店为空，other_out qty/inventory_delta=-1。原 completed 出库单建 other_return，独立批准、现场同VIN receive；新 Vehicle ID/gen2，成本/品牌/车型/颜色/供方/建议价完整继承，other_return +1 引原 out Entry，旧车/旧Position 全行不变。 |
| HK023 车辆采购退回 | B 始终保留原采购收车来源：inventory return_request → manager return_approve → inventory return_dispatch；原 Return/Shipment/Movement/Position/Custody。实物退回时原已付仍3000、供方应退2000；finance 原 refund 从原B付款、同账户真实合成退20元。原付款不改，退款独立 CashEntry/Payment original_id，最终净款及有效约定1000分、应付/应退0。 |

原 VP 任务本人分别通过原 FlowCase GET、当前页面及唯一可见 assign 按钮交接。唯一 generic AssignInput 仍 `{version,assignee_id,reason}`，不补 request_id；其它 JSON 业务命令严格原 request_id 和 current version。导入 review 任务沿该批原 reassign，admin 是合法独立 review 角色。VO review/physical 任务沿原 VO reassign，确认人仍为实际岗位本人。每次登录和 GET 渲染稳定后才取写入保护基线；不把合法登录 audit 排除。

CSV 精确 UTF-8 原头：funds=`source_row,line_id,vin,amount_cents`，ship=`source_row,manifest_row_id,vin,shipped_date,expected_date`，receive=`source_row,manifest_row_id,vin,received_date,location_id`。三批各2行，金额整数分；源文件只写外部 runtime 的 synthetic-inputs。原上传 multipart 标量 CAS/request_id 与员工所选文件长度/SHA 对照实际网络、DB ImportRequest、冻结源字节；文件/原件报告只记元信息和 stored_blob length/SHA，不 JSON 序列化 BLOB、不用 default=str/base64。

## 保护与未测边界

全部 DB 查询 SELECT-only。每次正向确认前全业务表哈希，变动只允许本动作有限表；允许表所有旧主键逐行比较，旧 BLOB 也在内存原样比较。Case/Task 限本单；Custody 限两VIN；位置/车型/原价/原款和其它店全保护。导入 Claim 的字符串 key 与 file_security.file_id 使用真实 PK，Result/Claim → Row → Batch → Case、身份 Link → 本次 VIN 逐项绑定。新 audit/event/receipt 的实际员工和门店核对，不粗排除审计表。

trial 合法追加 Batch 状态/Task/Event/Audit/ImportRequest；原 Case、资金、请款、发运、实车、集团身份/监管均必须回滚。正式 confirm 才允许本域对应结果，资金CSV仍不能直接 Cash。`_returnable`（vehicle_procurement_service）在 return_request/approve 会真实触碰 B 的 updated_at/version 与 Custody.version，明确仅放此B；出退库新代次不会重写旧 Vehicle/Position。最终原页面刷新全业务哈希不变，核对B退回没有破坏A新代次。

后继有限 `report_sources`：purchase_case_id；funds/ship/receive import_batch_ids；invalid_duplicate_batch_id；每VIN manifest 行 ID；original_vehicle_ids 两原库存ID；current_vehicle_id 为A新代次；local_move/other_out/other_return 的 case IDs；B purchase_return_id/原return_movement_id；两原 payment_ids、退款 payment_id、三 cash_ids、account_id、源/目的 location IDs；final_A/final_B 原行与 Position/Custody/Entries。只在整场六项自动检查全部通过后输出 complete；失败保留当前 failed 与后续 not_tested，不继承其它场景成绩。

未执行：全部真实点击、三CSV原 multipart 内容可观测性、原 UI 动态选项/任务渲染、完整状态/角色/行保护、平台及并发条件。条件分支未测：移库目的拒收/原位接回、批次 replacement/cancel/资源上限、采购在途退回/撤销/部分退款。HK020/024跨店、客户退车隔离、运输索赔和其它193项不属本批。生产银行/实物、ClamAV、经营主体与公司合同模板、PostgreSQL/员工试用及人工六类仍未验收。

## 作者静态记录

- 已逐函数核对 vehicle_imports_api/service/csv/models、vehicle_procurement_service/models、vehicle_operations_api/service/models、原三前端 UI，以及复用的原点击 helper。
- 自审修正：原 `_apply` 同时校验 vp_ship/vp_receive 任务本人，预先原 UI 交接；trial/review 有真实 audit 追加；return_request/approve 有原B监管锁触碰；实际 totals 键为 in_transit_cents。静态修正不称实测失败/通过。
- 新 Python AST、10个直接数据库调用全部 SELECT 起始、有限表/无 app/scenarios 导入、catalog 六原标题/checkID、UTF-8/空白、引用 helper 名称静态检查通过。guard 逐旧行保护包含旧 bytes，JSON 产物只用去除 content 的附件元信息；未启动验证进程。
- 作者冻结源码992行，SHA256 `811c59e075ca513a9e29a6c397f482eaaa0a342199b68138aba7a66a8fc249d7`。已请求 click_scenarios 只读短审；冻结不代表独立审阅或动态执行通过。根接手注册及新鲜镜像，作者不再写已冻结候选，若审阅发现明确问题再按授权增量修复并重记指纹。
