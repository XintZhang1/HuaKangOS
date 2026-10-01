# 原整车采购至库存浏览器点击

日期：2026-10-01。依据 `PATCH-M8-4-BUSINESS-193-02`。根代理已注册并完成首轮实际执行，当前修订候选等待统一复验。本代理仅维护此脚本和本页，没有改生产、共享 runner、夹具、目录或既有接待脚本。

## 范围与入口

`tests/browser_click/vehicle_purchase_business.py` 导出 `VEHICLE_PURCHASE_SCENARIOS=(("vehicle-purchase-hk171-177-178-026-021-018-029", vehicle_purchase, 300),)`。函数为 `async (e, context, credentials)`，复用原 `Evidence` 和已验证的 `sales_business.login_as/employee_choice/new_event/require`，没有顶层导入 scenarios，不建立另一套运行框架。

原业务源目录的稳定检查编号分别为 `HK-171-business`、`HK-177-business`、`HK-178-business`、`HK-026-business`、`HK-021-business`、`HK-018-business`、`HK-029-business`。启动时核对镜像目录的七项 source_reviewed 和 check_id，并在外部报告记录该目录 SHA-256；原源目录由审计代理维护，不能从旧导航或空表单成绩继承本次业务通过。

夹具只提供本店 manager/inventory/finance 真实启用身份及外部随机凭据，`business_fixtures.vehicle_purchase` 含 `store_id/manager_key/inventory_key/finance_key`。本轮新供应商、品牌、车系、车型、仓库、库位、计划、附件、请款、付款、VIN、实车及任务结果全部由原 UI 产生，不预置这些结果。原负载分派若选到 demo 员工，主管在原任务转交表单明确选择本次经办人；不 SQL 改负责人，不借管理员身份自批。

## 可复验原链

1. 主管先搜索唯一供应商名，原表新增代码、名称、账期及已知合成联系方式；再实际修改联系人与电话，核对原列表、响应和数据库。
2. 原“新增车型”表明确新增品牌与车系，创建五座汽油车型；第二次明确选已有品牌、车系及其版本，创建七座混动车型。分别核对排量、电池、指导价的整数换算及 ModelClassification 关系。
3. 原管理页创建 `warehouse_type=vehicles` 的整车仓与真实库位，员工从可见查找候选明确选择所属仓库。主档配置不增加实车；后续原验收实际使用本店库位。
4. 库管原采购表填两车型各一台、不同颜色、当日计划日期及合成合同抬头。独立主管通过原上传表选择外部合成采购合同，逐行冻结单车成本 100000/110000 元与建议售价，再请款 210000 元。此时没有付款或实车。
5. 财务原上传付款凭据，明确选择本店唯一启用银行账户，原表登记 210000 元和本轮唯一凭证号。独立 CashEntry/Payment、请款关闭及预付 210000 元准确；此时实车为零，不宣称银行真实付款。
6. 库管上传中性发运/验收凭据，逐 VIN 发运两个原车型行；在途不增加 Vehicle。现场填写与原发运不同的有效 17 位 VIN，实际收到 422 及原 refusal，完整原业务摘要不变；取消后重新打开原表，逐车重填正确 VIN 和库位实际验收。
7. 核对 Receipt、Movement、Vehicle 原成本/库存代次、Custody、GroupIdentityLink、Position 和 purchase_receive 位置流水。付款净额、已验收均为 210000 元；预付、应付、供应商应退、在途及未发运均为零，原任务结束。刷新后款、车、流水与任务不重复。
8. 原车型页实际组合品牌、车系、动力、座位、指导价及名称筛选，展开真实入库 VIN；五座车型在六座条件下被排除。原库存页按两个 VIN 分别检索，显示原位置、可用及审核状态，与只读数据库一致。所有查询完整原业务摘要不变。

## 证据与条件边界

每项在外部 `business-checkpoint.json` 记录稳定 check_id、具体判据、实际动作区间、原 Cookie/CSRF/门店/版本/请求编号摘要、原响应及 SELECT-only 数据库事实。失败项保留 failed，其余未执行项不补 passed；空场景或缺源合同失败。外部合成 TXT 仅是明确输入，原 UI 选择文件并原服务生成不可覆盖 FileAsset、哈希及原 structure_only 扫描记录，不伪造扫描状态，不当 ClamAV 验收。

按原工作流复核，供应商停用、在用仓库编辑/停用/类型守卫，以及有真实占用来源时的库存占用分支属于条件或后续检查。本轮继续使用这些新主档，不为查询额外造销售配车。脚本在 conditional_checks 留 not_tested 和原因；空 Hold 仅证明本轮新车当前没有占用，不证明占用分支通过。目录代理已准确区分主合同与条件分支，七项 check_id 保持稳定。

当前夹具没有已启用经营主体策略：原非生产服务允许明确填写合成采购公司，账户使用既有合成本店银行账户。若原 API 提供批准抬头，脚本保留 readonly 值。该路径不表示生产主体冻结、账户归属、真实银行或真实实物交接通过。

自动检查通过与人工业务验收分开：simple_flow、concise_copy 保留 pending，business_accepted 和 full_193_business_acceptance 始终 false；不声称效率提高 20%、全部 193、生产环境或部署已验收。实际执行结果及候选修订分别记录，历史失败不覆盖。

首轮候选脚本 SHA-256：`63df2398b9165347fa25d2a4f988766211b73d461852d27a8a00e97b399659dd`。注册前 AST 解析、定向差异空白检查通过，当时实际执行次数为 0。运行时另外记录镜像逐项目录的真实指纹。

## 首轮实际失败与取消流程修订

外部 `business-vehicle-purchase-20261001-01` 已完整结束，退出 1，服务已收尾。原 `business-checkpoint.json` 保留 HK-171、HK-177、HK-026 passed，HK-178 running、HK-021 failed、HK-018/HK-029 not_tested；HK-178 只完成仓库与库位配置，原实车验收引用尚未发生，不能算完整通过。首轮没有七项通过。

本次真实原 UI 已产生两行采购、独立主管审批、请款、财务付款及两个在途 VIN。错误现场 VIN 原提交收到 HTTP 422 和服务器“现场VIN与发运VIN不一致，不能验收”；原业务摘要为 469 表、1891 行，拒绝前后相同，未新增验收、实车或入库流水。截图 `44-protected-original-vehicle-refusal.png` 保留原拒绝；`45-failure.png` 显示点击关闭后原 dirty guard 的“还有未保存的填写内容 / 继续填写 / 放弃填写”。原保护与 `web/workforms.js` 的 `workFormCloseRequest` 合同一致；测试错误在于把关闭按钮当作立即放弃。

修订候选只补真实取消流程：等待原表单提交结束，点击原关闭按钮，核对准确的未保存提示，再实际点击“放弃填写”，要求对话框隐藏且完整原业务摘要仍不变。原 422、真实 refusal、Cookie/CSRF、错误 VIN 和零业务修改断言全部保留；没有重试提交、固定等待、强制点击、原状态注入或生产改动。明确放弃后，后续正确验收须重新打开原表、员工实际填写与确认。

同时修正本候选的失败收尾：当前项 HK-021 保留 failed 并明确 failed_requirement；先前等待后续依赖的 running 项转为 partial，保留已完成配置证据及未完成原因。尚未执行项仍为 not_tested，不能留下运行中状态或把当前采购拒绝后的 UI 失败归到仓库设置。首轮外部历史报告保持原件，此收尾规则只用于下一次执行。

当前修订脚本 SHA-256：`d23ae355d992c5255b52e8494e1763eb9d92de1366d74ecbedc2f2ece5bd614a`。AST 解析、定向空白检查及第二代理原合同只读审阅通过；尚未启动新实例或实际复验。人工体验、生产支付/实物、ClamAV、经营主体策略、条件分支及完整 193 项业务验收仍未通过。
