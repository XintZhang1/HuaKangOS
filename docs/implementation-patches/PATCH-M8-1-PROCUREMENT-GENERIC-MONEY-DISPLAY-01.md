# PATCH-M8-1-PROCUREMENT-GENERIC-MONEY-DISPLAY-01

2026-10-01，M8.1 同一浏览器交付，先登记。当前 fresh3 仍运行，生产/tests/runner冻结，全部关联收尾后才实施。

本次实际查看 reports-complete-source08 的311-hk-153-functional-source.png：原通用采购Case页显示约定20.00与“累计已收或已结0.00”，同时采购本人原资金事实已付2000/退回500、净付1500。Case.paid_cents不是专用采购payments/totals的付款投影，通用字段容易误读为未付款；不可为展示而改原Case或服务、复制计算或猜填金额。

仅允许 web/app.js casePage 原“业务资料”金额区域：kind===procurement时保留服务器原约定金额，隐藏该不适用的累计已收或已结；保留原采购办理按钮，实际收付款沿原有采购详情API与UI核对。其他kind、金额权限、原业务导航/submit/schema、未保存草稿与状态不改，不新增介绍或后台查询。

必要展示范围补齐 web/procurement.js procurementPage：仅在原row.totals存在的资金卡组增加“已付净额（元）”，直接使用原totals.paid_net_cents，不从表格重算；原API金额权限仍决定totals是否返回，其他验收/退货/应付/应退卡及所有原提交不改。员工可直接核对原20元付款减5元退款的15元净付。

源码精确差异与Node语法检查后进入唯一当前版本full53，核实际采购原通用页不再显示0汇总、原采购明细净付1500仍准确；这项只处理当前已观察采购显示，不宣称其他专用页或193体验全部通过。原自动/人工证据类型、真实Date、PG/Linux/员工/模型及生产门槛保持。
