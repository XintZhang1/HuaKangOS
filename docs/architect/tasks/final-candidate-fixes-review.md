# 当前三候选精确修正的独立源码审阅

2026-10-01；只读审阅，未导入应用、运行业务/浏览器/测试、执行 SQL 或读取数据库、真实配置及密码。审阅者只新增本文件；生产源码、测试与执行器均未由审阅者修改。主任务报告关联旧实例已收尾，本审阅不另把进程状态作为业务通过证据。

## 结论

与仓库外原字节逐文件比较，四个文件的差异均落在已登记的三个 PATCH 范围：采购通用页仅隐藏不适用的累计字段，采购专页仅接线原净付款字段，应收候选仅修一处真实车辆外键，财务候选仅对齐原父 Cash 固定十列投影。未发现额外生产行为或测试合同放宽。允许进入原范围的新隔离复验；本结论只代表静态审阅，不代表新 17/11 闭包、full53 或业务验收通过。

原件目录：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/launches/final-candidate-fixes-before-20261001/`。前三项 SHA 与同目录 `edit-record.json` 一致；采购专页原件也在该目录，本审阅独立计算第四项。

| 文件 | 原件 SHA256 | 当前 SHA256 | 精确差异 |
| --- | --- | --- | --- |
| web/app.js | 642525adde83676ed157d6ee96e667bb38feb1d57b331e37e027bbba3bad6453 | f06b590bbd23b4ab4e87798f8084738a729185610d8edc4970557ef7a630cdba | 第279行一行替换 |
| web/procurement.js | a7be6ed05ab9e2ec8d7370c33405a797714070df850fc9edd3dd343e3b47a668 | 3877ffe6b41bc3f4f457564788d53a7489d930368c700056cc26066f88e289fa | 第23行一行替换 |
| tests/browser_click/receivables_business.py | d8b6b360fa6920c72f6bbc7ebcf5cfc807d9a87e9659e361cf8ad7e2f2c41d11 | e9f7149de607303ac5ceea00c83d89f9a9f414c2244bae9fc37d50141abf701f | 第763行一处 SQL 标识符替换 |
| tests/browser_click/finance_remaining_business.py | 5da17e4578813debe1f013dfd0526d0614b0636148e7fc9bc6b3e82a4aca9556 | e558d6e01467c7ecc638a27fdf0eba878392a294ecc2474e04ba47a22c936c41 | cancellation_closure 内三处局部差异 |

## 采购金额显示

对应 `PATCH-M8-1-PROCUREMENT-GENERIC-MONEY-DISPLAY-01.md` 及其已登记专页补齐范围。

`web/app.js:279 casePage` 仍由原 `'amount_cents' in r` 控制金额区，原约定金额 `money(r.amount_cents)` 保留。唯一新增条件 `r.kind==='procurement'?'':...` 包住原 `money(r.paid_cents)` 累计卡；其他 kind 的原累计卡文本与值原字节保留。第278行原 `procurement/{r.id}` 采购办理入口和全部权限、原单/专页导航、表单及 submit 不在差异中。服务器 `app/flow_api.py:50` 的 `eng.money_visible` 返回字段边界不改，也没有把采购 payments 的值复制回 Case。

`web/procurement.js:23 procurementPage` 只在原 `if(row.totals)` 内新增“已付净额（元）”卡，直接 `money(t.paid_net_cents)`。原实际验收、实际退货、当前应付、供应商应退四卡及其他页面字节全部相同；没有前端加减、默认零、额外查询或提交变化。当前服务 `app/procurement_service.py:50–62 totals` 已从原 PurchasePayment 方向计算 paid_net_cents；`describe:66,88–102` 仅向原 MONEY_ROLES 返回金额与 totals。因此这次接线沿用原服务器金额权限及原总额。

实际新页面是否显示当前原净付、隐藏原通用采购 0 汇总，以及小屏五卡布局，仍需唯一当前版本 full53 与原生页面实测核对；不继承旧截图结果。

## 应收维修来源外键

对应 `PATCH-M8-4-RECEIVABLES-OBSERVATION-FOREIGN-KEY-01.md`。

`tests/browser_click/receivables_business.py:763 repair_source` 原字节重建确认：整文件只将 `FROM care_vehicle_observations WHERE customer_vehicle_id=? ORDER BY id` 换为 `... WHERE vehicle_id=? ORDER BY id`，参数仍为本次同一个 `vehicle['id']`，没有新增 SQL、扩大查找范围或改业务守卫。`app/customer_service_models.py:25–28 VehicleObservation` 的真实字段为 vehicle_id，外键指向 care_customer_vehicles.id；原预约/到店参数 customer_vehicle_id 的名字不应套到 observation 表。

原预约 scheduled、同原 CV/VIN、max(原读数)+100、本人上传/逐位核 VIN、原 arrive/convert 提交与回执、版本/原店/原车及追加/旧行 guard 均在未变字节中。此修正解决测试候选的列名错误；不证明原到店、维修或应收闭包已经实测完成。

## 退订现金父投影

对应 `PATCH-M8-4-CANCELLATION-CASH-PROJECTION-01.md`。

原 `tests/browser_click/sales_order_business.py:203–204 facts` 对 cash_entries 明确只取十列，顺序为 `id, store_id, direction, category, amount_cents, account, payment_method, voucher_no, created_by, approval_state`。当前 `finance_remaining_business.py:471 cash_fields` 的字段和顺序逐项一致；472 要求 deposit/refund 两父 cash 的 keys **恰等** 此集合，既不补缺字段，也不忽略多余父字段。474–475 从当前两个完整 Cash 行逐列取值，与对应原父投影严格相等；缺列会失败，没有 `.get` 或默认零。

原两 Payment 仍以 SELECT * 的完整行分别等于原父 payment。原 cancelled 单、本人读取的当前原单版本/店、Payment case_id、Cash id、两方向、四金额全部300000分、退款 original_id、同原 account_id、唯一两 Payment、无本单车辆位置流水及无开放任务，原条件均保留。完整 Payment 相等也保留原 store_id 与原款/账户等其他列。原 `read_original:369–395` 的 Cookie、x-store-id=1、同原版本/编号及刷新前后全业务摘要相同守卫未变。

当前 `original_cash` 和 `refund_cash` 仍返回两个完整 Cash 行；只额外返回 `parent_original_cash_projection` 与 `parent_refund_cash_projection` 说明父来源。**父记录并非完整 Cash 行，因此此处不宣称未被原父保存的日期、备注、版本等额外 Cash 列已跨父比较相等。** 当前完整行仍可审阅，原父/原生支付回执不改。本函数以外所有字节相等，移除此函数后的整模块 AST 也相等；没有修改其他域比较、父 checkpoint、生产模型/服务或执行器。

## 检查与待测

检查只使用原字节比较、有限源码读取和标准库 AST 解析。两个 Python 文件解析成功；没有导入候选模块或运行其中的读取/提交。JavaScript 一行差异已人工核模板嵌套，主任务报告其语法检查通过，本子审阅未重跑该检查。上述通过项仅是静态检查。

新外置17与11原闭包必须分别保留真实退出码、完整注册与 provider 终局，片段不拼成 full53；随后同一当前源码/脚本指纹完整 full53 核低影响显示。原失败、193逐项体验、真实 Date、101/283、PostgreSQL/Linux/员工及生产门槛保留。本文件不修改里程碑或发布状态。
