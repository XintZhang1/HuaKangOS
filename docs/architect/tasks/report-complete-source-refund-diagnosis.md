# Reports06 原付款退款选项只读诊断

日期：2026-10-01；负责人：remaining_audit。仅审阅失败原件、当前候选及同轮镜像源码；数据库由 manifest 明确标记的外置 `runtime/synthetic.sqlite` 以 `mode=ro`、`PRAGMA query_only=ON` 读取。未导入 app、启动应用/测试/浏览器，未改生产、候选或 runner。

## 结论

确定是候选 `report_complete_source_business.py:681` 的硬编码误解：正常到货付款尚未退回的原款余额为 2000 分，而实际退货形成的全单应退为 500 分。两者是不同上限。当前页面正确显示原付款可选；候选要求选项文字包含“本笔剩余 5.00 元”，在原付款选择前失败，尚未发送退款 POST。

无需改生产标签、退款上限、预付款来源或业务数量。真实退货与付款已经发生；本报告不将其局部成功写成 HK152/HK153 整项通过。

## 同轮原件与最后动作

运行根：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/business-reports-complete-source-20261001-06`。

- `evidence/browser-click-report.json` 为完整 selected 报告：6 执行、5 passed、1 failed。五父为售前、采购、主档、物资、系统管理；不是 full53。目标场景 `reports-complete-source-hk152-153` 失败。
- 目标 `business-checkpoint.json`：complete=false、passed=false；HK153 failed，HK152 not_tested，原错误“原退款选项不是本笔释放余款”。
- `actions.json` 最后357–361：原 refund 按钮、输入5.00、明确选择本店账户、输入原退款凭证编号；没有选择原付款，没有点击提交。
- `network.json`：本 Case94 的 pay/return_request/return_approve/return_dispatch 均真实200；最后原详情 GET 与账户/文件 lookup 均200。`/api/procurement/orders/94/actions/refund` request/response 均未出现。
- failure 观察与 `275-failure.png` 保留原页面：实际验收20.00、实际退货5.00、当前应付0.00、供应商应退5.00；退款弹窗仍有两项必填，原退款待办未结束。

## 有限原事实与生产合同

只读本轮合成库查得：Case94/store3，kind=procurement，state=receiving，version=19；原 Payment5 direction=out、amount_cents=2000、account_id=3、cash_id=116、original_id=null，尚无引用它的退款行。两 Receipt5/6 各1000；Return2 dispatched/v3，Posting2 引 Receipt5，quantity_milli=value_cents=500。退款 Task231 open，assignee_id=15（本轮财务），version=1。

`procurement_prepayment_facilities WHERE id=94` 为0行；本 Case `procurement_payment_allocations` 为0行。不是“释放预付款抵用500”的合同，原付款是正常到货实付。

- `app/procurement_service.py:87–102`：财务详情返回原付款、当前 totals，以及 `prepayments.describe`。
- `app/procurement_prepayment_service.py:198–199`：未启用 Facility 返回 `None`；启用情况下才提供 `original_cash` 与 allocations。
- `web/procurement.js:7–11`：`prepayments=None` 分支的“本笔剩余”由该原付款 amount 减同 original_id 已退计算；本轮为2000−0=2000分。
- `app/procurement_service.py:349–354`：退款同时受全单 supplier_refund_due 与原付款未退额度限制，启用预付时另受 payment_available 守卫。本轮合法最大实退为 `min(500,2000)=500` 分。

原 network 只保存 HTTP 元信息，没有保存完整最后 GET 响应正文。因此本文不冒称已捕获 `prepayments:null` 或完整 option 文本；`None` 与20.00结论由同轮未变的真实 describe/UI 源码及只读 Facility/Payment/Allocation 事实核定。后继候选应直接保存并核对财务本人当次原 GET 投影。

## 最窄后继修改建议（未实施）

仅在 `procurement_action` 保留 `responsible` 返回的当前财务详情，refund 分支核其本人/本店/Case94当前版本，`prepayments is None`、全单应退500、唯一原付款与DB的 id/账户/方向/2000金额/reference，以及引用该付款的已退款合计0。由这份当前 GET 与有限DB事实计算原款剩余2000，严格核选项“本笔剩余 20.00 元”及原 reference/id，再沿原可见候选选择。不是删掉选项余额断言。

保持本次提交 amount_cents=500、原 Payment5/账户3、receipt凭据、当前 Task本人、CAS/request/唯一回执、原款关联和所有旧行 Guard。提交后仍严格核原到账500、方向in、original_id=5、原账户及净付1500/实物1500/应退0。其余 pay 和已有预付 Facility 合同不变；不补造预付申请，不重放本轮未知结果。

## 原件指纹

| 原件 | SHA-256 |
| --- | --- |
| browser-click-report.json | `b5b15da5d052eaeb21ec43bb926feb9471027a00ce89fd1b179051221586d188` |
| business-checkpoint.json | `66b6ddd740cc88bfe0d18e368f8f9b736df9073920389c76df6233c7eef087cb` |
| observations.json | `8eb20d95657dcbc158c57da9b046f83767611f5b786f98ec962d16438d363635` |
| actions.json | `5cd0059813de6b5b59040fc3d8f68a503c60c2d3f0904931ce6cc9168d74be1b` |
| network.json | `c8de97bf4f51b1f164bffec09101314f8e3c8b11dbc2a0ea7e2b0bb2432e29b4` |
| report_complete_source_business.py 当前与同轮 scripts 一致 | `c6b02dfbdcee821ec46e9804b440526e480160008d29217a3d242b0cf740440d` |
| web/procurement.js 当前与同轮 source 一致 | `a7be6ed05ab9e2ec8d7370c33405a797714070df850fc9edd3dd343e3b47a668` |
| app/procurement_service.py 当前与同轮 source 一致 | `13d7f017d6772af541fc0022dac277de82f88f525385e8711c5cfd5789caa359` |
| app/procurement_prepayment_service.py 当前与同轮 source 一致 | `ab82b1124950fe32a3266e68d8e7f50d122bbccf9dfaa366d79b8a8f256c6372` |

历史失败保留。新原点击、真实退款和两个报表完整验收仍待根登记窄修并在当前关联实例收尾后的新鲜隔离运行中完成。

## REPORT-REFUND-ORIGINAL-BALANCE-01 落盘增量独立复审

2026-10-01，根确认相应实例与监听全部收尾后实施。按该补丁，只读对比外置 `launches/current-three-fixes-before-20261001/tests/browser_click/report_complete_source_business.py` 与当前文件；本次未读数据库、导入 app、运行应用/测试或修改候选。

原 SHA-256：`c6b02dfbdcee821ec46e9804b440526e480160008d29217a3d242b0cf740440d`；后 SHA-256：`f5a001fb75240afa993a7d3e9720e4963f2639994f6cd36cb9d3ab06c3bd1b00`。

未发现确定的静态接线缺陷。逐字 diff 只修改 `procurement_action`：保留 `responsible` 的当前详情、新增原 GET/DB 来源与双上限核对、记录观察、由整数分原款余额严格核对原选项；其签名不变。还原这一个函数后，整模块 AST 与原字节 AST 等价；其他函数、Guard、实物/现金/旧行/文件、下载、权限恢复与净1500检查均未改变。

- `responsible → detail` 沿原本人登录/当前店岗位和同 Case GET，核详情 id/version、真实门店和当前 Task本人；没有改用不同角色的详情。金融 refund 才带 original，正常 pay 路径保持原合同。
- 新八字段 `id/direction/amount_cents/account_id/original_id/reference/cash_id/evidence_id` 与真实 `procurement_service.describe` 公开付款投影逐项、顺序完全一致。GET全部本单付款与同一 Case SELECT 投影相等，且唯一 DB付款整行等于事前保存原件，保留原 Case/门店/金额/账户/凭证和原款身份，不把公开投影冒充整行。
- `prepayments is None` 明确本来源未启用 Facility；原款未退2000与当前全单应退/实际退款500分别严格核对。唯一未改 original 限定下，同原款退款总额仍为0，不把2000余额当作可无条件退2000。
- UI仍核唯一 original_payment_id option、原 reference和由原 remaining 计算的20.00文字，再真实选择；500金额/账户/凭据仍从原可见表单提交。`source_refund_original_caps` 仅追加有限业务来源与两个上限元信息，没有文件正文或凭据秘密。
- 新增直接 SQL 文本只有一条 `SELECT * FROM procurement_payments WHERE case_id=? ORDER BY id`；本次只分析文本，未执行 SQL。原 Refund schema 的整数金额/原付款/账户/evidence、当前 Task/CAS/request/回执、旧行 Guard、原500退款与原账户/净1500/库存1500后置核对完整保留。

静态检查：AST解析、单函数还原模块等价、八公开字段对真实 schema、SELECT-only、逐字 diff与 `git diff --check`。这是静态复审通过，不是实际退款或HK152/HK153重新通过；原reports06失败和全部原件不变，动态结果等待新鲜隔离复验。
