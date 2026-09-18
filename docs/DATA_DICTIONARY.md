# 数据字段与录入口径

## 共同字段

所有业务表含门店store_id、内部 ID、系统单号、业务日期、审核状态、录入人、创建/修改时间、版本号和备注。业务日期是实际发生日期，不是自动创建时间；系统时间按 UTC 保存，界面按门店时区显示。业务日期不得在未来。

金额输入元，数据库字段后缀 `_cents` 的值是分整数。界面用十进制字符串传金额，后端用 Decimal 校验；不要用 Excel/JavaScript 浮点结果直接拼出超过两位的小数。

## 五类业务

| 表 | 主要字段 | 关键关系与校验 |
|---|---|---|
| vehicles | VIN、brand、model、color、supplier、location、purchase_cost、list_price | VIN 为17位并排除 I/O/Q；唯一。不是完整厂家 VIN 校验/车型识别服务 |
| sales | vehicle_id、customer_name、customer_phone、salesperson、contract_amount、sale_stage、delivery_date | 车辆须为可用的已审核库存；已审核唯一占用；审核时成本快照用于毛差 |
| repairs | plate_number、customer_name、customer_phone、service_advisor、repair_type、repair_stage、due_date、completion_date、policy_id、labor_amount、parts_amount、discount、cost_amount | 类型含 maintenance/repair/insurance；可关联保单；结算=工时+配件−优惠 |
| policies | policy_number、insurer、plate_number、customer_name、customer_phone、policy_type、start_date、end_date、premium、commission | 保单号唯一；起止日期有序；预计佣金不等于已收到佣金 |
| cash_entries | direction、category、amount、account、counter_account、counterparty、payment_method、voucher_no、sale_id/repair_id/policy_id/vehicle_id | 最多关联一个业务；类别约束方向和关联对象；账户是自由录入代号，不是银行接口 |

完整字段名、长度、必填、枚举以 `app/schemas.py` 和 `app/models.py` 为准，中文表单由 `web/app.js` 定义。销售、维修和保单可选录入客户电话；姓名、电话均为本地敏感资料，不外发 AI。备注不外发 AI，但会保存在本地单据与审计历史中，不应粘贴不必要的身份证/银行卡等资料。

## 财务分类

| 类别 | 方向 | 必须关联 |
|---|---|---|
| sale_collection / 销售收款 | 收 | 销售 |
| repair_collection / 维修收款 | 收 | 维修 |
| premium_collection / 保费代收 | 收 | 保单 |
| commission / 佣金收款 | 收 | 保单 |
| vehicle_purchase / 车辆采购 | 支 | 库存车辆 |
| operating_expense / 经营支出 | 支 | 不关联上述业务 |
| refund / 客户退款 | 支 | 销售、维修或保单之一 |
| capital / 出资撤资 | 收或支 | 不关联上述业务 |
| loan / 借款还款 | 收或支 | 不关联上述业务 |
| transfer / 内部转账 | 单条支出形式 | 不关联业务；填写不同转入账户 |

内部转账使用单条记录是本版的门店总现金流口径，并不建立会计复式分录或两个银行账户的完整对账账本。账户、对方、供应商等目前不是独立主数据表，人工输入需统一命名；这会影响按账户/对方匹配的重复规则。

## 审核与复核是两件事

`approval_state` 管单据是否生效：draft/submitted/approved/rejected/void。

`findings.review_status` 管一条“需要核对的线索”如何处理：open/reviewing/confirmed/dismissed/resolved。确认问题不会自动修改业务，仍须按单据流程进行有理由的纠正。

AI 建议没有自动转成最终财务结论；报告显示模型观点、内部记录引用、原因和核对建议，用户应返回原单查证。


## 0.2 门店、账号与自动维护表

| 表 | 用途 | 边界 |
|---|---|---|
| stores | 门店代码、名称、启用状态 | 不删除有历史业务的店；停用后不参与当前授权汇总 |
| user_stores | 员工与店的多对多授权 | 非管理员至少一个启用店；管理员自动拥有所有启用店 |
| feedback | 文字意见、门店、作者、候选SHA、摘要、测试结果、审批状态 | 不向浏览器暴露审批令牌哈希或测试stdout |
| maintenance_events | 每个改码/审批/发布步骤 | 只对意见作者或管理员可读，仍受门店隔离 |
| bot_receipts | 飞书事件去重ID | 不能用任意外部HTTP提交代替SDK回调 |
| deployments | 前后代码SHA/路径、备份路径、部署结果 | 当前版本回滚不回退财务/业务数据 |

单据号改为同店唯一；多店可重复，主键ID仍全库唯一。每份日报和每条复核项均有所属门店。store_id在应用层强制写入/验证，非所有业务表都增加了数据库外键；不得绕过应用执行任意直接SQL写入。新增的store/user_store授权关系有外键。
