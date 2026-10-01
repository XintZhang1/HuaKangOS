# PDI 与精品加装出库的下一批范围

2026-10-01，只读源码设计；HEAD `8993ca8c755194a42a48e7323fe355e80c6bf9ae`。本页按根最新授权记录 HK037/065/075 三完整候选的最短原 UI 闭包及 HK076/078 的有限后续建议，没有改生产、候选、fixture、runner、目录或计划，没有导入 app、启动实例、浏览器或测试。HK038 已冻结文件保持原字节；本页不进入验证镜像。全部执行状态仍为 `not_tested`，下一精确补丁前不编候选、不登记新的通过或全 193 验收。

| 原编号、原标题与稳定检查 | 原真实行为 | 原入口 |
| --- | --- | --- |
| HK037 新车检测(PDI)，`HK-037-business` | 新订单的当前已配 VIN 检查不合格，原发车受阻；原技师整改，同 VIN 复检合格，缺陷、轮次、凭据、任务分别存在。 | `#sales-quotes/{id}`；原 `#case/{id}` 显示检查摘要。 |
| HK065 精品加装出库，`HK-065-business` | 原销售加装的同 VIN、授权商品、实际出库、安装、独立质检、接收及收费逐项对应。出库不表示已安装或收入确认。 | `#addon-orders/{id}`；准确原标题不是“销售加装交车”。 |
| HK075 车辆销售收款，`HK-075-business` | 同一新 PDI 订单财务两笔原实际收款，累计/剩余和两个原款/账户/流水/凭据正确；真实 UI 连续点击保护、每请求唯一原回执及现金。 | `#sales-quotes/{id}` 的原 receive，不做 raw 正向 HTTP 重放。 |

## HK037：新原车辆订单上的不合格、整改、复检

固定同次来源为 `vehicle-purchase-hk171-177-178-026-021-018-029`、`sales-order-hk008-009-011-022`、`sales-cancellation-hk010` 及其已完整通过的必要前序。只读当前 `e.manifest.evidence_root/browser-click-report.json` 的明确父状态，再读取对应固定 `business-checkpoint.json`，核同一 origin/source/scripts/catalog 指纹与父 `complete/passed`；没有父或单选缺依赖立即失败，不能从旧 run 或全库扫描替代车辆。

取取消父 `report_sources.cancelled_order_id`，只读该原 Case 的 `vehicle_id`，与同轮采购第二车的 Receipt→Shipment→Line→Model 有限身份对应；必须不同于 `delivered_vehicle_id`。即时重读该 VIN 的 Vehicle、VehiclePosition、VehicleCustody、IdentityLink、Hold、现库存状态及代次：取消原 Hold 已释放，当前车仍在店、已审核、可配，没有后来来源占用或出店。车辆操作父另建的新采购车辆不替代此来源，其已作废的车也不能用于 PDI。若有限车辆当前不可用，报告前置缺失，等待另一个获准真实采购输入到结果链，不能静默换 demo 车。

原售前 lead 已 `converted`，因此新报价不再承接它：从原 `#sales-quotes` 新建，真实选已知本店客户、该车原车型，`lead_id/lead_version` 均为空，沿 `create_quote(..., from_lead=False)` 的已知表单能力。不可直接调用旧 `dependencies(cancellation=False)`，它要求 lead 仍为 intent；只复用有限依赖/当前身份核对及原 UI 小型 helper，不更改共享 helper。报价显式无加装、保险、代办条件，不同 manager 原审核冻结本版，inventory 本人实际配该 VIN，sales_peer 下载本版生成合同字节、上传对应签回并确认当前 Quote/VIN/模板快照。demo 模板只证明合成字节和签回流程，不证明公司合同批准、生产主体策略或病毒扫描。

先按下述 HK075 原 finance 两笔本人收款使当前报价款已齐，避免把资金不足误当 PDI 阻断；金额以本次实际输入报价为准，整数分和原 Account/PaymentLink/Cash 独立留证。然后按以下原动作办理：

1. service 对原 open `inspect` 任务上传本次不同内容的 inspection 凭据，原按钮“登记交车检查”选择原生值 `不合格`、填写明确缺陷和真实文件候选。当前 Case.data.inspection 绑定该 VIN，round=1、outcome 不合格、inspection_status=failed；inspect done、rectify open，原事件保留全部输入。
2. inventory 在原页面核 dispatch disabled、真实阻断理由和未出库的 Position/Custody/Hold。禁用按钮不能强点或绕 UI POST；按钮拒办与零业务变化足以证明原 UI 阻断，后台直接拒绝分支另标未测。可用同源只读 GET 核 action.enabled/reason，不能用它取代可见按钮。此时无 dispatch 事件、PositionEntry(sale_dispatch)、实际交接或 deliver。
3. technician 本人原任务“登记缺陷处理”，结果和 inspection 文件明确对应第一轮缺陷；rectify done、reinspect open，inspection_status=awaiting_reinspection。整改不是合格检查，发车仍受阻，原 round=1 和失败事件不变。
4. service 本人原任务“登记交车复检”，选择原生值 `合格`，新文件/结果属于同 VIN；round=2、inspection_status=passed、reinspect done，原失败和整改 FlowEvent、三个文件、任务历史完整保留。原检查结果只更新当前 Case.data，不能要求旧 data 快照仍是当前值。
5. 本批闭包必须实际发车与交付：inventory 本人原 dispatch 留凭据，唯一原 PositionEntry(sale_dispatch) 与当前代次、实际成本对应；sales_peer 本版生成/签回 handover 后原 deliver，交接、实际收款、PDI、签回各自核验，当前代次只交出一次。只到复检合格不满足此登记闭包。
6. 最后原 UI 打开客户/当前销售单及其回访来源，核本店本人客户、同实际新 VIN、交车日期/金额、callback 父单和实际待办；只读指定有限原件、全库零业务写。`flow_engine.make_callback:622–627,750` 在 `contact_allowed=true` 时追加原 kind=callback、parent=该新订单、同 customer、due=业务今天+3；不自动新增 care_customer_vehicles 或新 CustomerCareCase。原客户已有 care/CV/observations 保持，不把原自动 callback 当已完成员工回访或自动新 CV。若另需为新 VIN 原 UI 建立 CV/新式 care，则需另登记具体路径，本批不虚构关联行。

原合同：`app/flow_specs.py:182–191` 的 inspect/reinspect 字段为 `evidence_id/outcome/result`，outcome 的原生枚举是中文 `合格/不合格`；rectify 为 `result/evidence_id`。`web/salesquotes.js` 原按钮 `[data-act=sales-quote-action][data-key=inspect|rectify|reinspect|dispatch|deliver]`，真实 POST `/api/flow/cases/{id}/actions/{key}` 封包 `{request_id,version,values}`。`flow_api.ActionInput`、`flow_engine.py:649–671` 核原 actor/store/digest/Case CAS/岗位/state/blocker；`856–870` 冻结 VIN/轮次并追加后继任务，`421–443,464–480` 与 `sales_quote_service.py:182–207` 保持当前签回、付款、PDI 及服务条件。

现账号已具 sales_peer、manager、inventory、finance、service；technician 从原 `business_fixtures.repair.technician_key` 取实际账号。每次真实登录核当前用户/当前一店原岗位，不借 admin 代检查。原负载分派若落 demo 员工，仅 manager 原 Task 转交，`POST /api/flow/tasks/{id}/assign` 精确 `{version,assignee_id,reason}`，无 request_id；先等原 Case GET 和任务按钮真实渲染，再原点击。inspect 初始 service、rectify technician、reinspect service 为此例责任顺序，实际原任务 ID/岗位/负责人/版本均逐次核，不能只按 action 允许角色推断本人任务。

静态可见显示缺口：`web/app.js:264–276` 的原 `inspectionBanner` 已显示“检查不合格，禁止出库”“缺陷已处理，等待复检”、结果/轮次，现仅接 generic Case。`web/salesquotes.js` 专用销售详情没有该摘要，只展示原 action/tasks 的阻断文案。本批可真实导航 `#case/{id}` 核原检查摘要，再回专用销售动作页；这是已有原入口。若要同页简化，可另登记仅复用该真实摘要的展示接线，不能改原检查规则或凭据判定。本页没有运行证据，不把这一静态缺口写成已复现故障。

## HK065：复用同轮真实 Addon 闭包，不重复消耗物资

同轮固定父 `sales-followon-hk012-015-016-017` 的 `report_sources.addon_case_id/delivered_order_id/customer_id/vehicle_id/material_item_id/material_warehouse_id/material_location_id/work_item_id` 已有完整可执行源合同；必须当次父整场景完整通过后才能读取。HK012 逐段 evidence 已记录创建/本版 Quote 独立批准/Authorization、dispatch/StockMove/WarehouseEntry、installation、quality 两次 `[False,True]`、rectification、Acceptance、PaymentLink/AddonPayment/Cash 和各 native response/任务负责人。这里只说明代码已有证据输出，不继承任何历史 run 成绩。

推荐下一登记把 `HK-065-business` 的独立判据接入这条**本次重新执行的同一原点击路径**，每段核自己的 source/check/action range/响应/DB；也可新增只读闭包逐项打开本次 Addon 原详情，消费父原点击证据并核当前事实。它必须同时证明原业务点击和当次原可见页面，不把映射、一个完成状态、只读 GET 或数组字段相同当成完整业务通过。禁止对 completed Case 重办 dispatch/install/quality/accept/receive，禁止重复采购、领料或收款补分。

原源 `app/addon_service.py:271,407,466,486–490`：dispatch 绑定目标 VIN/本版授权商品和实际 WarehouseAllocation→StockMove；install 引用原 dispatch 的实际数量；quality 绑定原 installation，失败不能 accept；rectify 引用失败 Inspection；重新 quality 合格后 sales 接收当前 Quote 才生成 AddonAcceptance，finance receive 才新增真实 AddonPayment/PaymentLink/Cash。父例为数量 1000 milli、商品 3000 分+安装 500 分，实收 3500 分，原成本只从真实出库源核，不从售价推定。预留不是出库，出库不是安装或履约收入，验收不是现金。

实际原 UI `#addon-orders/{id}` 与 POST `/api/addon-orders/{id}/actions/{dispatch,install,quality,rectify,accept,receive}` 的 `{request_id,version,values}` 保留。dispatch 值为 `checked_vin/lines[{line_key,quantity_milli}]/evidence_id`；install 为 `dispatch_id/quantity_milli/result/evidence_id`；quality 为 `installation_id/passed` 严格布尔、result/evidence；rectify 为 `inspection_id/result/evidence`；accept 为 `quote_id/evidence`；receive 为 `amount_cents/account_id/reference/evidence`。员工顺序 inventory→technician→service→technician→service→sales→finance，各原 Task 本人办理，manager 仅本版独立审核和原任务交接。

父例是已交付同 VIN 的 `delivery_blocking=False` 后加装，可以满足原 HK065 出库/安装闭包；它不证明交车前加装阻断。`guard_order_delivery` 只对 delivery_blocking=true 生效；交车前父阻断、零价赠送、拆回/取消/随车移交和原款退款均保留条件未测，不为本项强建这些来源。

## 旧原件、源版本和统一标准

新 PDI 每次登录审计完成后取全原业务行基线。正向动作只允许当前新订单/Task 的必要列、有限当前 VIN/Hold/Position/Custody/付款账户、原 quote/签回/文件/回执/事件追加；manager 转交的原 Task 与合法审计单独放行。旧采购、原交付/取消、旧报价/Resolution/Consent、库存/会员/资金/附件/他店全行保留。Case data 当前检查更新采用有限列/字段许可，旧 FlowEvent/file 字节永远不覆盖。文件 BLOB 仅内存守卫，输出 length/SHA256/原字段，禁止把内容或 bytes 存入 checkpoint。未知结果立即停止，不自动换 request_id、不重放、不放宽 CAS。

HK065 闭包只读检查须在各原登录后基线：除真实读取/下载本身规定的有限 Audit 追加外，全原业务摘要及每张旧行不变，零业务写；父已消耗 Item/Balance/Allocation 的当前版本即时重读，不能与初建零库存整行强等。原费用、金额用分，数量用 milli；数据来源日期取业务 Asia/Shanghai，不依 host UTC 猜今天。全部截图、日志、凭据、checkpoint 外置，仅固定有限 source ID，不导出原客户全行或文件正文。

前端预期、流程简单、文案简洁、后端匹配、硬性 bug、来源完整六类标准仍各自记录：原按钮/摘要/轮次/缺陷可见、动态 lookup 必须真实选择、原中间状态及 DB 准确、阻断不写原业务、刷新不重办。三宽像素与员工实际体验没有本轮证据时为 pending；自动事实通过不自动 business_accepted/full193。

## HK075：同一新 PDI 单两笔原到账与事前误记来源

原交付父只收一笔 12100000 分，退订父是另一单定金/退款，不能拼成同单分笔。第三完整候选直接沿上述新报价、独立主管价审、inventory 配同 VIN、本版生成/签回合同办理。建议员工事先声明新报价 13000000 分，原 finance 第一笔 5000000 分、第二笔 8000000 分；实际金额输入及请求精确为分，核第二笔前尚欠 8000000、receive Task 仍 open，第二笔后总额 13000000、尚欠 0、原 receive Task done，现金不依 PDI 或出库状态推断。若原报价金额另有明确输入，事前两笔需恰和该版金额而不是后台猜差额。

两笔均明确选择同一个真实本店启用 Account 的有限 ID，使用本次各自唯一 reference 和不同 receipt 原件。每次真实原 receive 表单值→POST/Cookie/CSRF/actor/store/version→RequestReceipt digest→PaymentLink→CashEntry/账户余额→原当前版累计一一核对；旧款/旧签回/原车/其他店全行保护。通过原 UI 本人原生连续点击验证提交中 `aria-busy`、原 submit disabled/`dataset.submitting` 保护，观察全部真实请求，不注入 JS state/fetch、不卡住网络伪造成功、不 force 点击、不 raw 正向重放。以原实际请求 request_id 核仅一条对应 Receipt、PaymentLink 和 Cash；第二次 native 点击若被原 UI 截止或表单已关闭，不期待第二个 POST，也不为获得第二响应循环点击。两笔必须各为独立原 request_id/回执，刷新保持两个原款。

`web/app.js:132` 原 modal 同步设置 submitting/disabled，并在原回调 finally 恢复；`flow_api.py:173–185` 原请求按 store/request_key 查回执，actor/digest/原 Case 再核。UI 连点后唯一请求/回执能证明本次不二记；若 UI 从未发出同 request_id 第二请求，后台重复请求返回旧回执分支仍条件未测，不能用一个 Receipt 伪称执行了后台重放。

第一笔可为后继 HK078 留**事前明确**合成误记事实：在仓库外新输入说明中先冻结正确合成银行凭据编号 `PDI-{run}-BANK-01` 与本次员工故意误录编号 `PDI-{run}-ENTRY-01`，两值必须不同，原上传 receipt 字节包含正确编号、原 UI reference 填故意误录编号；金额、账户、事实到账和其它条件仍正确。checkpoint 只报告两编号、输入/凭据 hash/长度、原 PaymentLink/Cash/Receipt ID 及实际 reference，不打印原附件内容。本批不修原记录、不创建 correction；后继更正另走原追加纠正且保留此正确依据。若事前说明/正确凭据不成立，不给既有正确收款事后编错款理由。

## 仅建议的 HK076 有限收款复用

HK076 代办服务收款，`HK-076-business`：同轮 sales-followon 的 `agency_case_id` 可给出第二版 fee=2500/pass=1000、receive=3500 分真实 Cash，原 ServiceTender 两桶精确分开；pass 对同 payee 原 disburse=1000 与独立 outgoing Cash/ServicePassEntry 留事实。只在同次父重新完整通过并逐项原 UI/原件核对后复用，不把 fulfill、补件完成或最终状态当到账。若缺完整父，另建原代办闭包而不是查询历史替代；本批不实施 HK076。

## 本次只读指纹

目录 `business_acceptance_catalog.json`：`eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`。关键源：flow_specs `014f2ff72953dcfdf331ae00211942994800e758faab28a2b941c87a6574a64f`；flow_engine `f654ffa77e82f517f77cfc69f6937e2e2c2527c23874d87f937f7ab18e0bbaca`；flow_api `a4343d6b2cbaedc32bdec1a1b411cb274ff20040ce05fa15ba23c2393f425652`；sales_quote_service `5627575b09624dc68e88a4c929d6c4415cb0bce87ad92f170d47514392f8d083`；addon_service `5eb53bef6ab4eeafebd5fbdc5c9d4d4794e4d36bb3112f1f48ebb7c2e7366846`。

原 UI：app.js `642525adde83676ed157d6ee96e667bb38feb1d57b331e37e027bbba3bad6453`；salesquotes.js `07147f988baca26278e11d010f2fd4892e6ebc44b06324041cf7047838314367`；addonorders.js `705d24ea3cd91f508fd0a4d547b92d9b6cf8c0fd6dd0bf43a05aed4dab9a490c`。既有 helper：sales_order `4cd5e5b2468e1cd9f40884033f614342a9633bd0afab46393a20ce01fdf0cb92`；sales_followon `7b93e9b07ad454a7bc33129e9cc85979900fa33994ffc1132f1c683ef8e62e7f`。本页是范围与前置记录，不是执行结果或上线放行。
