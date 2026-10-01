# 原整车销售及未履约退订浏览器点击

日期：2026-10-01。精确范围为 `PATCH-M8-4-BUSINESS-193-04`。本增量只维护未注册候选 `tests/browser_click/sales_order_business.py` 和本页；既有生产、采购/接待脚本、Evidence、runner、夹具及逐项目录由根代理或原负责人维护。没有启动应用、浏览器或共同测试。

## 入口与当次依赖

导出 `SALES_ORDER_SCENARIOS` 两组三元组：`sales-order-hk008-009-011-022`，原 `async sales_order(e, context, credentials)`，300 秒；`sales-cancellation-hk010`，原 `async sales_cancellation(e, context, credentials)`，180 秒。复用已验证的登录、员工候选、原任务提交及可见查找选择小型 helper，不建立共享状态或新的运行框架。

根注册顺序必须为售前 → 采购 → 销售 → 退订。候选仅从本次 manifest 的 `evidence_root/browser-click-report.json` 核对前场景 runner status=passed，再读取此 root 固定售前/采购/销售目录的 `business-checkpoint.json`。缺前序或前序不完整明确失败并在活动需求检查点留失败，不扫描数据库挑旧单，不读取其他运行目录。记录前检查点字节指纹、本次原目录指纹和 manifest 原 origin/source/runtime/evidence/database 路径；再次只读核对实际原 ID、关系、本人客户、意向状态、采购来源、车型版本、VIN 和库存代次。

`business_fixtures.sales_order` 精确六键为 `store_id/sales_key/manager_key/inventory_key/finance_key/service_key`。角色分别为原本店销售乙、主管、库管、财务、服务；凭据只从已有外部参数读取。夹具仅提供真实启用身份，客户和两辆实车必须由同次前场景原 UI 产生，不新增或预置业务结果。原任务若分到 demo 员工，由主管在原转交表真实选择本次经办员工及原因，再由该员工本人办理。

每组启动核对 source_reviewed 和稳定 `HK-008/009/011/022/010-business`。每项独立 acceptance_checks、动作区间、响应及 SELECT-only 原事实；自动 passed 与 business_accepted 分开，人工简洁文案与操作方便判断保留 pending，完整 193 和完整注册套件均为 false。

## 原销售交付链

1. 从本次本人意向原单实际点击转车辆预订，复用同客户及 lead_id/version，明确选择本次汽油车型。填写合成 120000 元、期限及无另单服务约定，保存原 Quote1/Case；原意向 converted 事件及任务结束可追溯，不另建客户。
2. 不同主管批准 Quote1；库管从该报价真实可用车候选明确选原采购 VIN，原成本与占车/位置/代次相符。原库存查询必须精确显示“已预订”“已审核”，库龄（天）对应单元格为 0，与真实 API stock_age_days=0 一致；查询零业务写入。
3. 销售生成绑定原 VIN 的合同，实际点击下载生成字节，与 FileAsset SHA/size/快照/报价指纹核对，再通过原文件选择器上传对应 source_file_id 的合成签回并确认。录入与上传不替代原 sign、Consent 和 Resolution。
4. 同原单提交合成 121000 元的新报价；旧 Quote/Review/Resolution/Consent 保留，旧有效报价仍为 120000 元，新版处于待确认，财务收款按钮禁用。不同主管再次批准，销售生成当前合同并关联本版签回，原 sign 后 Quote2 生效。
5. 财务上传收款凭据，从原真实账户候选选择本次采购已用的账户，填本轮唯一凭证号，原 UI 实收 121000 元。PaymentLink 与 CashEntry 原方向、金额、账户、身份及引用一致。
6. 服务岗位上传检查记录并实际登记原 VIN 合格 PDI；只覆盖本次直接合格检查，不继承 HK-037 缺陷处理或技师整改验收。
7. 库管上传原出库依据并确认 dispatch。单独保留 HK-022 的原事件、唯一 `sale_dispatch` 位置流水（quantity=-1、inventory_delta=0、原成本负值）、Position=handover、Hold.delivered=false。此时 Case 仍 executing、没有 deliver，出库不冒充接车。
8. 销售生成本版 handover、实际下载核字节/快照/VIN、上传对应签回，再明确确认客户提车。独立 deliver、Task 完成、Case delivered、Position exited 和 Hold.delivered=true 一致；不会再次扣库位。刷新完整原业务摘要及原资金/任务/事件不变。原服务自动生成的 callback 若存在，记录其真实关联，不宣称该回访已办理。

## 未履约第二单退订

复用同次本人已有客户及第二混动车型/VIN，另建 130000 元原预订，独立批准、配车和本版签回。财务原 UI 实收 3000 元；确认没有 PDI/出库/提车或加装、保险、代办履约。销售申请退订，另一主管批准后状态 refund_pending、原款和占车仍存；财务从原退款候选选同 original_id、同账户，实际登记 3000 元退款。新增 out Payment/Cash 引用原款，原 in 不删，原单 cancelled、净收零、Hold 解占、Position 仍 stored、没有本单出库流水。刷新不重复；原库存显示可售、零库龄和已审核。

已履约服务终止、保留费用和提车后退车必须另走原售后流程，当前条件分支为 not_tested；不在本链造售后、占额、调拨或无原款退款。HK-012–017 的加装、保险、代办及客户/厂家其他收入各有独立状态机，未在本组执行或冒充通过。

## 证据与交接

外部 `business-checkpoint.json` 记录每项 actual 原 case/Quote/Review/Consent/Resolution/Event/Task、Payment/Cash、VIN/Position/Custody、原附件及字节指纹。实际正写全部通过原可见表单，Cookie/CSRF/门店/版本/请求号摘要来自原浏览器响应；无业务 API 直写、前端状态注入、数据库造事实、强制点击或循环重放。

销售组顶层 `report_sources` 固定为 `{lead_id, customer_id, delivered_order_id, delivered_vehicle_id}`。退订组只在本组完整后追加 `{cancelled_order_id, cancelled_vehicle_id}` 并带同四个销售源键。后续报表只在本次两组 runner 与检查点都通过后引用这些真实 ID；原日期金额、成本、车款及退款从对应原 db 事实核对，不把零待收或订单定金当预收账。

文件仅为明确合成输入，经原上传生成 structure_only 扫描记录；原 demo 已批准合同/提车模板仅用于虚构数据字节和签回守卫，不表示本轮公司正式条款批准、真实签字、银行支付、现场交车或 ClamAV 验收。当前未注册、未执行，所有实际成绩等待根代理统一运行。

根已短审接原镜像/注册/汇总；销售2场景与报告1场景接入后当前注册20。Fresh sales-reports01真实报价及配车完成，原文档下载正确新增download审计，装置整库不变断言误失败；根仅允许本员工/店/原单/该文档reason的唯一下载审计、before/after=null，旧audit和所有其他业务表仍完整保护。Fresh02销售四项同次passed，独立第二单实收3000元后申请退订按钮位于原“更正、退回或撤销”折叠，脚本未展开而失败。根按实际唯一按钮的原details/summary点击展开，不强制点击或改产品；两失败及依赖报表未执行均保留。Fresh03正在全新镜像沿前序再验两组，未执行/不完整报告不计passed。

静态候选已完整落盘，两个入口及导出结构、AST 与定向空白检查通过。第二代理对 `ebfefdceb384e0b83e7773bc67384fb94a6bc12e2655035e8aa11823a8aceb81` 字节进行了只读短审，没有发现所列原 selector/API/DB 合同明显误配。随后仅把报价期限检查从 host `date.today()` 改为读取原页面日期控件实际 `min`（原 UI 的上海业务日），避免把机器 UTC 日期当业务日；不导入应用，不因此宣称 Linux 跨日验收。

最终冻结脚本 SHA-256：`b07094f33a5355182e7f5c9628128b2f1faacadc67cefe1073eced778d9e026a`。最终 AST、空白及两组导出结构检查通过。尚未实际运行，动态页面时序、下载、原任务交接和完整正链等待根代理注册镜像后实测；没有产生本批自动通过或业务验收成绩。

根后续记录：上述冻结为候选历史。销售/报表Fresh05所选5/5退出0，本销售4check与退订1check同次完整通过，来源5394dedb…/脚本7fbb2c7b…；原报价/两版实际合同字节与签回、121000元实收、检查、唯一出库/提车、第二车3000元实收/独立取消批准/原款实退分别核对。两本场景report_sources在同次runner passed及checkpoint完整后才供报表使用。未继承历史，人工体验/文案及全部193仍pending。automatic-business05当前新生产6be81a7b…/脚本1f2bbfb4…两场景通过，但整体21尚在执行，不提前登记联合完成。
