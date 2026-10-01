# 下一批原业务点击范围：会员本金与识别卡

2026-10-01 只读设计。主代理授权本文件记录；未新增候选脚本，未修改生产、夹具、注册入口或共享进度，未导入或运行 app。当前材料链及联合执行的结果由主代理收集，本记录不继承它们为成绩。

建议下一批先办本店会员身份、首卡、挂失换补、本金实收及原款退款。可复用当次销售客户、采购付款账户和现有随机员工，不增加岗位或造余额。按当前逐项目录，完整范围是 **HK117、HK128、HK118、HK089、HK094 五项**；普通本金链对 HK124、HK125 仅形成支路证据，不能把它们的组合购买／整份退款合同略去后记七项通过。

## 源与前序合同

- 原 193 项来源：`tests/browser_click/requirements_manifest.json` 的 `source_sha256=ddf297678e5d6d35e1dbfffc5c232c3d56748934eb22b58bbb9f9d5343689aae`；本次读取其文件 SHA256 为 `19840f4fc5fd816d94ea35a4602a31bde4674105e44621eeb4cfe42bdad27a1f`。逐 check 合同读 `business_acceptance_catalog.json`，本次 SHA256 为 `eeea5ea2088ac932fe9f725ef1d4bd68073507bd23f695df360ef0036ba8a3ff`。实施前仍须核对实际复制指纹，不能以本记录静态值代替下一轮来源绑定。
- 固定同轮 `sales-order-hk008-009-011-022/business-checkpoint.json`：要求根报告该场景 passed、checkpoint `complete=true/passed=true`、HK008/009/011/022 的实际 check 均 passed，读取顶层 `report_sources.customer_id`。只读核对本店 Customer 的实际 owner 为 `manifest.users.sales_peer.id`，其电话来自该轮客户操作；不从 demo、`domain_samples.customer_id`、最新数据库行或其他 run 找替代客户。
- 固定同轮 `vehicle-purchase-hk171-177-178-026-021-018-029/business-checkpoint.json`：相同通过／同镜像要求，从 HK021 的 `acceptance_checks[].evidence.payment.account_id` 获取真实前序账户，重新读取本店 Account 的 active/name/type/version。账户是付款账户主档来源，不能把采购现金当成会员充值现金；下一笔充值必须原 UI 新办理。当前经营主体规则仍由原 `freeze_case_entity`／`require_account_entity` 执行，不放宽。
- 两前序及下一批必须同一 evidence root、稳定 `provenance.json` 和源码／脚本镜像指纹；具体 Customer/Account/Case ID 有界读取。若前序未通过、源客户已被撤销联系／换店、账户失效或前序指纹不匹配，明确失败前置，不跳到旧资料。
- 现有一店身份：`sales_peer` 的实际 role=sales，用来核对本人客户；`service` 的 role=service，发卡／挂失换补、提出退款；`finance` 实际收退款；不同 `manager` 独立批准退款。全部已有真实 User/UserStore，凭据只在外部 runtime。业务不用 admin 代员工办理。
- 首卡完整路径要求所选同轮客户无任何原 MembershipCard 历史、无 GroupMember 本金成绩；在原会员页／只读 DB 检查。有 GroupIdentityLink 时核实是否由本轮前序真实生成；有已发卡／资金历史则不能假走“首卡”或重开身份。本轮销售候选未包含会员开通；客服另一个客户的原车辆关联会生成身份，不能混用。

## 原 UI → API → 结果

| 完整 check | 员工输入与真实点击 | 原接口及结果 |
| --- | --- | --- |
| HK117 会员信息管理 | sales_peer 在 `#membership` 搜索本轮客户并点“查看会员”；从“核对并开通会员”进入 `#group/<customer>`，明确选择独立身份并勾本人确认，随后“开通集团会员”。再核卡、本金、权益记录的分账及当前客户。 | GET `/api/flow/master/customers`、`/api/membership/members?customer_id`；GET `/api/group/identities?kind=customer&q=<完整电话>`；POST `/api/group/identities/link` `{request_id,kind:'customer',local_id,identity_id:null}`；POST `/api/group/members` `{request_id,identity_id}`。新增 GroupIdentity/GroupIdentityLink/GroupMember 和对应 GroupEvent/GroupReceipt，初始本金／占额 0；不发卡、不充值，不拼接旧 flow Member 余额。选择已有同电话身份不能自动合并。 |
| HK128 会员卡生成 | service 打开同一会员，点 `[data-act=membership-create][data-key=card_issue]`“发行第一张会员卡”，填写明确原因。新独立单上传本单合成确认凭据，选该凭据并点“确认本次实际办理”。回列表实际按新卡号识别客户。 | POST `/api/membership/orders` `{request_id,customer_id,purpose:'card_issue',values:{},reason}`，响应以 `case.id` 导航 `#membership-order/<case.id>`。POST `/api/membership/orders/<case.id>/actions/execute` 带 order/case/member 三个当前版本和 `{evidence_id,reason}`。MembershipOrder completed、Case completed、本人 `membership_execute` Task done；唯一 MembershipCard generation=1/status=active/previous_id=null；GET `/api/membership/cards/lookup?number` 返回精确本店客户。金额、权益、期间不变。 |
| HK118 会员换补卡 | service 先点同一原卡“挂失原卡”，独立申请、原上传及实际 execute；原卡号识别须 404 且显示原错误。再从已挂失原卡点“换补新卡”，另一独立单、凭据、execute；实际识别新卡，原号仍拒绝。 | 同 POST orders，purpose=`card_loss`／`card_replace`，values `{card_id:<该轮首卡ID>}`；同三版本 execute。原卡 active→lost→replaced；唯一新卡 generation=2、previous_id=原卡ID、新 number，原身份和所有本金／权益／期间均不变，旧卡不删除。每个申请／执行有独立 Order/Task/FlowEvent/MembershipEvent/GroupReceipt。不能重新 card_issue 覆盖历史。 |
| HK089 会员储值卡充值收款 | service 在原会员页点“本金充值”，输入 **100.00 元**和原因，创建独立 topup 单。上传本单到账凭据；finance 本人接手原任务后实际“确认本次实际办理”，选择前序实际账户并输入本轮唯一流水号、凭据和原因。 | POST orders purpose=`topup`、values `{amount_cents:10000}`；同三版本 execute 的 values `{account_id,reference,evidence_id,reason}`。原 membership service 委托 Group topup，在同事务追加 GroupEntry topup +10000、对应 CashEntry in/category=`group_member_topup`/amount=10000、原账户／原 Case／actor；GroupMember balance=10000/reserved=0；MembershipOrder/Case/Task 完成。唯一 GroupReceipt；本金不再追加 flow MemberEntry/PaymentLink 或赠品 Wallet。每条 GroupEntry 的两条 GroupSettlementEntry 合计 0，是内部往来。 |
| HK094 会员储值卡退款 | service 在 `#group/<customer>` 精确选新 topup 行 `[data-key=refund_request][data-id=<GroupEntryID>]`，输入 **40.00 元**、该来源单凭据与原因。manager 以本人原岗位点本申请“批准并占额”；finance 接手本申请原退款任务，点“登记实际退款”，选择原账户、独立退款流水号和实际凭据。 | POST `/api/group/members/<member.id>/actions/refund_request` 带 member 当前 version 和 `{case_version,original_id,amount_cents:4000,evidence_id,reason}`；`refund_approve` values `{case_version,refund_request_id,refund_request_version,reason}`；`refund` values `{case_version,refund_request_id,refund_request_version,account_id,reference,evidence_id}`。GroupRefundRequest requested→approved→executed、requested_by!=approved_by，占额 0→4000→0、本金 10000→10000→6000；追加 GroupEntry refund -4000，original_id 精确指 topup、原账户、CashEntry out/category=`group_member_refund`/4000；executed_entry_id／closed_by 为本次真实结果，原 topup/Cash 不改写。 |

创建／换补 UI 的原字段：`#modal [name=reason]`，充值新增 `[name=amount]`；执行表单 `[name=evidence_id]`、收退款 `[name=account_id]`／`[name=reference]`。发卡后不能按识别号视觉 `<wbr>` 切片猜值，以真实响应和本单 MembershipCard 的完整 number 核对，原按卡号识别表单输入完整值。

所有执行订单当前版本来自 GET `/api/membership/orders/<case.id>` 及原 GET `/api/flow/cases/<case.id>`，不能假定整数固定。退款的来源单是该次已完成的 Membership topup Case，原 `_case` 允许从此已结束来源提出退款；前端每次 groupAction 都重新读取该源 Case version，不新造销售／维修宿主。退款请求／批准还会更新该来源 FlowEvent/Task/Case version，下一步重核。

`membership_execute` 默认可能分配到原 demo 员工。若非本次 service/finance，manager 必须从原任务页面明确转交，沿原 `AssignInput(version,assignee_id,reason)`；不得改库、抄固定任务 ID 或用 admin execute。退款审核任务键为 `group_refund_review_<request.id>`，付款为 `group_refund_pay_<request.id>`。退款 approve 当前 service→manager 已满足申请人与批准人分开；旧 Group 路径仍有 account-admin 自批例外，此链不使用该例外，也不声称已验它。

原附件必须分别在其 host Case 通过“上传本次凭据”选择外部合成文件；不复用销售／采购单的文件 ID 冒本单证据。原 `security.can_use`、非 generated、category=evidence／receipt、Store/Case/read permission 守卫保留。结构检查件只证明隔离业务结构链，不能声称真实银行、ClamAV、客户签字或生产附件完成。

## 结果保护与后继有限来源

每步核真实前端、原请求 request_id/store/Cookie-CSRF 及原 response、SELECT-only DB，绑定同一 actor/store/source/version。资金顺序严格为 **0→10000→6000 分**，占额 **0→4000→0 分**，可用 **0→10000→6000→6000 分**；现金只能一条新入 10000 和一条新出 4000，不能把审批占额或清算内部行当现金。每步刷新／查看原卡或旧流水不得再追加业务。

有限变更表包括本批指定 GroupIdentity/Link/Member、MembershipOrder/Card/Event、GroupEntry/RefundRequest/Settlement/Event/Receipt、本批 Case/Task/FlowEvent/RequestReceipt/FileAsset，以及两条真实 CashEntry 和原账户允许的 version/updated_at 推进；实体冻结等原额外行须按实际源合同逐条允许。旧 Cash/GroupEntry/Card 的不可变资料、所有其他客户／会员／原单、StockMove、InventoryBalance、旧 flow Member/MemberEntry、全部原权益 Wallet/Entry、Period/Fee、报价和前序销售／采购现金逐行保护。不得以整表排除 Audit/Receipt/Event/Account 规避副作用核对；只允许本次真实请求精确关联的新行／指定版本列。密码／哈希／Cookie 值不得进入证据。

候选若获授权，建议固定一个场景，checkpoint 仅这五个 `HK-xxx-business` check；先形成全路径再核角色／金钱／旧卡拒绝。途中失败时保留已经执行及未执行项，不换 request_id 盲重放。后继可输出 `membership_sources={customer_id,identity_id,identity_link_id,member_id,card_issue_case_id,original_card_id,card_loss_case_id,card_replace_case_id,active_card_id,topup_case_id,topup_entry_id,topup_cash_id,account_id,refund_request_id,refund_entry_id,refund_cash_id}`，各 ID 从当次原响应＋DB核对获得，不输出预想 ID／余额。下游读其 passed checkpoint 和当前真实版本，不拿输出版本冻结后续合法推进。

HK124“会员储值卡充值”和 HK125“会员储值卡退款请求”完整合同含第二条 `wf-recharge-bundle`。本链只能各标 `partial`／普通本金支路，不提交这两项 business check。组合充值必须以后实际发布适用门店和期限、本金／赠品／整份退款条款、客户 terms_accepted、独立实际付款和完整未用份额退款，不能拿本次 100.00 本金代替套餐 Purchase/Component/Wallet 成果。消费占额／核销、积分、等级、续会及混合维修包均仍未测；人工简单流程／简洁文案 pending，`business_accepted=false` 和 193 整体验收保持。

## 后续备选与系统遗漏

**跨店材料四项 HK055/047/071/084** 可在会员后做，原来源是同轮材料已通过 checkpoint 的 `material_sources.primary`，尤其精确 `item_id/enrollment_id/warehouse_id/location_ids/source_location_id/receipt_ids/stock_move_ids`。需重新读取可用 Balance，不能继承候选计划 7250 或在维修之后仍认旧余额。当前一店 manager/inventory/finance 均无二店 UserStore；要先通过原管理 UI 明确二店岗位并重新登录（或原 UI 新建对应员工），二店原 UI 新建同规格零库存 Item、materials 仓／库位及实际账户，完成独立启用；不能夹具直接铺调拨／余额／现金。工作量及新来源明显多于会员五项，因此不选作首批。

该备选的已核最小合同：`#transfers`“申请调拨”→POST `/api/transfers` `{destination_store_id,due_date,reason,lines:[{item_id,quantity_milli}]}`；双方分别 `actions/approve`，source库存原库位 allocation→`dispatch`，destination 原物资／实际库位 allocation→分批 `receive`（accept_milli/reject_milli），拒收另 `return_ship`→source `return_receive`（v3实际 passed）。每个动作带 request_id/transfer.version/当前店 case_version；各自原任务、证据、Source/Destination 守卫保留。精确 TransferReceipt/Movement/Entry/Balance/StockMove、在途与成本守恒；HK071 实际切店读原非空库存，不能拿集团合并量冒本店可用量。

HK084 从该次真正 accept 的 `material_transfer_settlements` debtor/creditor 原条目产生原 ClearingBucket，不靠 dispatch 在途凑清算。付款店 `#clearing` 点指定 `origin_kind='material'/origin_id`“申请本次清算”→POST `/api/reconciliation/clearing` amount_cents/due_date/reason；双方原单分别上传本店 receipt；付款方 `actions/pay`，收款方 `actions/receive`，values=account_id/reference/evidence_id/reason，带 clearing.version/本店 case_version。依次 requested→paid→settled；付款时另一店 Cash 为 0、原额度仍占用，到账才追加对店 Cash 和两边 ClearingOffset、释放 reserved/增加 settled、完成各 Case。两条 Cash 和两条 offset 各引用本次实际 ClearingOrder／原 settlement，不自动替对店到账。权限／二店原账户／原实体前序未完成，四项均不得执行或算 passed。

**整车退回 HK023** 是另一条单项优先补充，可沿同轮销售取消 checkpoint 的 `report_sources.cancelled_vehicle_id/cancelled_order_id` 和原采购 HK021 的明确车辆/shipment/receipt/payment；必须实时确认该车已经原退订释放、库存有效、无 SaleHold，不能使用已交付 `delivered_vehicle_id`。原 `#vehicle-procurement/<case>` 的 `return_request`→不同 manager `return_approve`→inventory `return_dispatch`→finance 原 `refund`，带 return_id/return_version、逐步当前 case/version 和精确 original_payment_id。实物退回与供应商原账户实际退款分别留 VehiclePurchaseReturn/Movement/Custody/Payment/Cash；不把供应商应退数或完成任务当到账。单项不能包装为 4–8 项；HK024/HK030 跨店整车仍需真正双店前序，后续独立登记。

系统遗漏只按当前候选声明区分，不重复另一代理详细设计：`system_management_business.py` 当前未注册候选范围为 HK189“机构管理”、HK191“员工管理”两个完整 check，HK192 密码／安全参数和 HK193 日志仅 partial。HK188“会员级别”不属于字典 MemberTier CRUD 验收，需实际 member-pricing 规则 submit→不同主管 approve→有效会员真实报价应用／履约来源；HK190 完整原单／逐件文件跨店授权须已交付原单、接收员工、不同来源主管、版本／期限／逐次访问及撤销失效，普通新增员工不能代替。HK192 登录图片实际更换／恢复、HK193 非空真实范围／分页／类型-ID筛选及详情仍须按独立当前精确范围记录；未注册候选、部分密码动作和当前页面存在均不代表整项通过。对应研究由 `system-management-click.md` 和其作者维护，不扩大本次会员范围。

## 本次只读来源指纹

| 文件 | SHA256 |
| --- | --- |
| app/membership_api.py | 3ec9054048827a4685f5fd13d6c23191c15d7184044674d1868a643e36645a8a |
| app/membership_service.py | 39824e265a9044207c60b231521862e942c774fa9425cd1e13ffc1f03e9f8173 |
| app/group_api.py | 4e3edd8c5d9ac493c77b9d9fbd9ceaabbf05fc826fe34ef0fc8b8cfe1c0c1794 |
| app/group_service.py | 72a4908740648a0774e228d4809447163deb29a4095fc5baa68d5b49309840dc |
| web/membership.js | 5dde1c2063e522815bf198890c2e46f38fe1e7941cad34b461185f97cf2b8f61 |
| web/group.js | fefeffbe61910c68669997e94c257076086c80877e8b242a2d80e475c5f9e1a7 |

读取而未执行：上述 API/service/UI、membership_models/group_models、fixture 的现有随机角色与独立只读样例、销售／采购／客服 checkpoint 写出源码、原 transfer/reconciliation API/service/UI/models 以及逐项目录和系统研究。未读真实库、环境或凭据；未把静态研究登记成运行通过。下一写入范围及注册、联合镜像与实际点击仍由主代理按精确补丁登记后实施。
