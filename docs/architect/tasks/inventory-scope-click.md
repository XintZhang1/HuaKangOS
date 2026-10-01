# 任务：HK071 机构库存查询的本人授权和实际在途

2026-10-01，按 PATCH-M8-4-BUSINESS-193-37 编写独立未注册候选。只新增 `tests/browser_click/inventory_scope_business.py` 和本文；所有生产、fixture、已注册脚本/helper、目录、计划及HK190只读。未导入app、启动实例或运行浏览器/测试，不登记业务通过。当前同一M8.1项，计划和共享进度仍由根维护。

原题“机构库存查询”，仅 `HK-071-business` 一完整候选；`inventory-store-scope-hk071` / `INVENTORY_SCOPE_SCENARIOS` 三元900秒。全193、人工体验/文案及生产验收保持 pending。原其他物资/整车库存和并发、资源上限、真实员工、PG/Linux条件不由本项代替。

## 同轮有限来源

必须当前 runner passed、完整 checkpoint、原目录/五项 provenance相同且本次镜像稳定：system-management新员工乙、master-data、材料九项、仓储八项和跨店五项。父闭包逐项重验；可选 `system-followon-hk192-193` 必须完整且原临时授权已恢复，可选 `roles-dossier-hk190` 必须完整且 sender 的当前id/store_roles/access_version/私有账号key与密码代次一致。不继承历史run、静态成绩或demo库存作为有限正向来源。

- 乙固定HK191 `staff_actions[1].user_id`，账号默认sales、一店实际manager、完成本人改密且active。只读原系统observations唯一外部凭据指针，限定本次runtime文件与账号当前阶段，密码加入共用scrubber，不输出密码/hash。
- 本店有限Item为 `material_sources.primary.item_id/enrollment_id/warehouse_id/source_location_id/location_ids`；第一bin来自主档HK184 `location.row.id`，第二来自**材料HK069** `second_location.row.id`。材料九项没有HK052，不能引用不存在的check；scope的这一来源拼写已由根更正。源位不足固定500千分单位或现场盘点围栏时真实失败，不换量/SQL造余额。
- 二店Item/bin为跨店完整 `report_sources.destination_item_id/destination_material_location_id`，其source_item_id须等于本店primary。另核仓储完整 `warehouse_sources.consumable` 在一店当前非空且来源bin相同；用于真实汇总来源，不代替采购材料移库。

## 实际输入至结果

| 原员工原UI | 原结果及守卫 |
| --- | --- |
| 乙本人原生登录一店；二店不在店下拉；真实未授权warehouse-item深链接 | 唯一原GET404、只原通用不存在提示，没有foreign name/sku/库位/成本，业务摘要不变。随后原warehouse输入有限编码并打开本店实际库位。 |
| 原admin在#users保留乙一店manager，明确加二店auditor及汇总=true | 完整原UserUpdate/CAS、access_version+1、一UserAccessReceipt/精确update_user Audit，所有乙旧session撤销、其他人原session不变。按原/新岗位及有限本人Run/Grant核每店WakeEvent来源；不改密码/其他员工/原Dossier。 |
| 旧乙窗口真实me401；本人重新登录，实际店下拉切二店auditor并搜索唯一有限编码 | 原items/stock与当前SELECT及UI逐行一致，账面/成本、可用、所有占额来源、库位/Entries完整且只本店；auditor没有仓储写控件。再本人切一店。 |
| 原库管新local_move明确500、源bin/目标bin、原因/日期，并原UI上传合成凭据；另一manager批准 | 原创建/批准CAS/本人Task、唯一事件/审计/FlowReceipt完整输入摘要；准确Approval与500 Hold。本店Item/启用/原收发不变，批准不作实物。借用已冻结材料原helper，不修改helper或使用admin代办实物。 |
| 本库管实际dispatch；乙本人读取本店非零在途 | 同原case真实transit Balance=500，源/在途原Entry净数量和价值均零；完整原最大余数均价算法核所有相关bin价值及必要零数量重估。总库存/成本及所有原StockMove保持，真实在途计入reserved、从available扣除。独立保存非零读取证据。 |
| 乙原店下拉选all；原warehouse目录拒绝；原#master/items逐页读取授权两店目录 | 原aggregate_scope/auditor/group_store_ids仅1/2；原all默认落点严格为analytics/overview/数据可视化，不能硬期待助手。warehouse can_read/create/money三false。拒绝页为原empty strong，不假设存在h1；展开真实折叠导航再点击。目录每页完整原本地ID/门店/量值/占额与UI一致，无新增/编辑/领用，明示汇总不能作为本店可领量。 |
| 原库管本单accept实收500；乙原一店再读 | 源/目标/在途量值守恒，原本地Entry按实际算法逐笔核，0新StockMove；原Task完成、预占释放、在途清零，原总量/成本不变。最终清零不覆盖先前非零证据。 |
| 原管理页恢复乙原店集合/岗位/汇总开关；旧扩权窗口me401；本人再登录 | access_version继续+1不回写，总+2；二店再次不在下拉且真实404。既有Grant/File/Decision/Access及全部无关原行保持，不让旧授权复活。失败只允许原UI恢复这一个员工的明确岗位/开关，不回滚业务、抹失败或重放。 |

库存读取沿原 `warehouse_service.stock_view`，每条balance/entry的实际来源店/原case、数量整数千分位、成本整数分与原UI精确单元格核对。可用量只读核 retail/addon reservation、warehouse signed hold/真实transit/现场观察、approved v3 procurement return，沿原 `inventory_availability` 同口径；不拿父终值猜当前余额。原五万明细超限413保留，不截断求绿。

权限写入复用已注册HK190 `change_access` 的原逐列/全表/全部本人session与其他session守卫及精确访问回执、摘要和信号；本候选另写显式一店manager+二店auditor表单，没有使用HK190专用表单限制。材料创建/办理复用原native helper及有限旧行Guard，再加强每动作唯一Audit/Event/FlowReceipt完整digest、Task/Approval/Hold和位置量值核对。附件正文仅内存，checkpoint只id/category/name/size/SHA；所有User/password/session hash不进证据。

## 静态自审与边界

AST、8个原helper模块导入符号及实际函数实参、18处SQL调用均SELECT-only、0app导入/0直接HTTP业务写、原三元900秒入口、原题/check以及旧行/敏感字段边界已自审；空白和最终指纹随冻结交接。尚未运行，不记1passed。原异步render/分页/真实店切换、多窗口旧session、原Task/附件、SQLite事务并发与整体900秒预算须根的全新外部实例实际验证。

原HK190首次run的只读定位作为本候选落点合同核对：先旧me401及原登录、G1暂停详情，再action73明确选all，实际me(all)200及analytics(all)200；web/app.js的assistantDefaultRoute对all无条件返回analytics/overview。该外部失败属于已注册HK190的落点断言误配，根处理其修正，本候选只同步正确原all断言；未修改HK190或将其首次失败/局部读取计入HK071成绩。

读取相关32路径组合SHA `4e6e16c72c0e6c17915d6b06d8b93fbee8f40af50e5aa8f9a307351f7650f11a`：排序拼 `path+NUL+sha256(bytes)+LF` 后SHA。包括 app/{main,schemas,security,tenancy,user_access_service,user_access_models,assistant_runtime_access_signals,flow_api,flow_engine,services,warehouse_api,warehouse_service,warehouse_stock,warehouse_models,inventory_availability,retail_service,retail_models,addon_service,addon_models,procurement_service,procurement_models}.py、web/{app,warehouse}.js、tests/browser_click/{sales_business,sales_order_business,system_management_business,vehicle_purchase_business,material_business,warehouse_operations_business,interstore_business,roles_dossier_business}.py及business_acceptance_catalog.json。组合不含本候选，最终源码/本文SHA交接记录，不自嵌循环hash。

成功才输出有限 `report_sources`：乙当前store_roles/access_version/私有来源key和密码阶段、两店Item、local_move case/两bin/transit balance/dispatch及accept Entry IDs和500→0真实量；所有成绩只来自当前执行。未知权限/来源、超时或409/503需保留原失败和原件，禁止重放、不豁免Audit或库存全表。其他当前候选与根运行均未修改。
