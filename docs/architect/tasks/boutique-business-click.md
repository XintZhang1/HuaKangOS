# 精品采购、安装与混合收款六项候选

2026-10-01，当前 M8.1 顺序内候选。授权为 `PATCH-M8-4-BUSINESS-193-22.md`，源范围 `boutique-remaining-scope.md` SHA256 `9172d3110d81f0d94c2c88e02de714b65472036f353359337bfa3a105b69d3e0`。作者只新增本文和 `tests/browser_click/boutique_business.py`，没有修改生产、共享 helper、fixture、目录、runner、注册或实施计划；没有导入 app、启动服务/浏览器或验证进程。以下是源码合同及静态候选，不是执行成绩。

## 原范围与导出

固定场景 `boutique-purchase-retail-hk074-052-058-062-064-082`，导出 `BOUTIQUE_SCENARIOS = ((SCENARIO, boutique_business, 1500),)`；1500秒为有限整场上限，原网络/DOM等待超时后停止，没有动作重试或未知结果重放。运行顺序 074→052→058→062→064→082；062从原建单到安装、接收及资金闭合才通过。

| 原需求 | 原 check ID | 本批独立必需原事实 |
| --- | --- | --- |
| HK074 精品采购订货 | `HK-074-business` | 两件新精品、真实子类/Profile/零库存启用；两行原采购申请、不同主管批准，冻结量价和 Task/回执一致，尚无实物或现金。 |
| HK052 精品采购入库 | `HK-052-business` | 两批分别真实库位准备、两行原 receive，每批真实原款40元；Receipt/StockMove/库位量值及应付对平。 |
| HK058 精品采购入库退货 | `HK-058-business` | 第一批A原Receipt部分退1件，独立批准、实际发出、原付款账户退款10元；原冲款/库存均价成本/差额分列。 |
| HK062 精品销售单 | `HK-062-business` | 本轮两商品原Retail报价、不同主管批准、本版客户授权、库管出库、技师原install、客户accept及资金完全闭合。 |
| HK064 精品销售出库 | `HK-064-business` | 两商品原实际库位准备/dispatch，各唯一实物流水、成本/预占释放/位置量值一致。 |
| HK082 精品销售收款 | `HK-082-business` | 新券规则及独立商品资格、新membership发行宿主实购；原券/本金各reserve→capture；原Retail两笔现金实收、余应收准确。不能以纯现金缩成完整合同。 |

每项只在实际运行后逐 check 写 passed；目录源码审阅不继承成绩。Checkpoint 整场 complete/passed 只在六项全部通过后设置；失败保留已执行原步骤、当前failed、依赖中running为partial、后续not_tested。始终 `business_accepted=false`、`human_acceptance=pending`、`full_193_business_acceptance=false`。自动断言只能证明对应 UI/API/DB 事实，六类标准中的人工显示、流程简单和文案简洁仍须独立审阅，未测条件不默认为通过。

## 同轮有限依赖

`fixed_dependency` 检查当前 `browser-click-report.json` 原注册名且整个前场景passed，固定外部路径 `evidence_root/<scenario>/business-checkpoint.json` complete、全部原requirement passed、目录hash及provenance相同。没有扫历史运行/全表最新记录或预制状态。依赖如下：

- `vehicle-purchase-hk171-177-178-026-021-018-029`：HK171实际供应商ID与HK021原付款账户ID。
- `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187`（实际常量 `MD.SCENARIO`）：HK181真实品牌、HK182父分类、HK184 materials仓与实际库位、HK175 WorkItem id/code。
- `materials-hk069-045-054-083-070-072-073-051-061`：完整物资前序来源保留，只借同轮前置身份/仓位，不消费其原主物资或冒用旧采购。
- `membership-hk117-128-118-089-094`：同轮本店客户、原GroupMember/身份关联与原账户，没有会员期会。
- `member-followon-hk123-124-125-129-130-132`：其 `member_followon_sources.customer_id/member_id/account_id/member_balance_cents/wallet_ids`。现场重读本金9700分/占额0、真实本店customer身份链接、旧卡及无period条件；旧券/赠品不复用。新运行没有这份完整来源即停，父场景其他运行的passed不能成为本候选成绩。

从现有 manifest 的 sales_order/repair 身份中取 inventory、manager、service、technician、finance，admin只在不同申请人的独立商品资格批准使用。当前店均1；主档按本店和active重验，中央GroupMember按本店已确认IdentityLink核验，不能虚构其store_id。使用现有原账户；无本店经营主体策略是当前有限前置，出现新策略时重新核来源，不改既有配置。

源/脚本镜像必须 stable；候选、member_followon、membership、material、master、vehicle_purchase、finance、sales、sales_order及catalog原字节hash与同轮provenance一致。数据库必须位于同轮外部runtime，所有SQL只读。

## 实际输入与量值合同

1. inventory 在原 typed-master 页面新建本轮精品子类（原父分类）、A/B两零库存Item并各建Profile，明确本轮子类、原品牌、供应商与实际库位。原仓储activate数量0，另一manager approve后各一个真实零库位Enrollment，零StockMove、零库存价值；原件字节仅内存核size/SHA。该段是采购商品前置，不另冒主档check。
2. 原采购A4×10元、B2×20元，合计80元。不同manager approve后两批，每批A2/B1及40元实际付款。每次采购原receive表内先为两行点击库位保存，各POST当前case version递进；原prepare不改Item/Balance，随后一次receive产生2Receipt/Move。第一次实际付款40元与第二次实际付款40元独立原Cash/PurchasePayment；未开预付款Facility、不生成抵用分配。
3. 第一批A的Receipt退1件，原ReturnRequest→不同manager approve→inventory prepare -1000/实发。Receipt原supplier credit1000分、当前库存成本1000分、Valuation差额0分别核。finance从第一笔原40元付款/同账户实际退10元，原original_id严格关联，采购net paid7000分、实收到8000分/实退1000分、应付和供应商应退均0；A3/3000分、B2/4000分。
4. manager 发布只本店新券：C500/P400/S500分，group承担100分，30天、原未用到期前退款政策、无兑换率/服务code。用 `MF.retail_eligibility` 原UI提出只允许新A商品goods范围，原退 `accumulate_original_unit`、原有效期 `original_expiry`、pending `none`；不同获权admin原Task批准并冻结Decision/Scope。不能后补旧钱包权限。
5. service 新建 membership benefit_issue 宿主（action purchase、上述新rule、units1）；finance 本人原membership_execute实际收到4元后产生唯一Wallet/Entry/Cash及发行时Eligibility绑定。发行往来按实际发行款400分，消费核销往来才按冻结S500分；这张券发行现金不计为Retail再收4元。旧卡、旧本金Entry和旧权益全保护。
6. service 原Retail两行：A1×25元+真实WorkItem安装5元、B1×30元无安装，共6000分，revision1、无手工discount/会员价格/related_repair_id。另一manager最低成交60元批准，创建服务顾问本人客户authorization revision1。原retail_authorize/retail_accept Task.role保留sales而assignee按row.owner为创建service；候选仅核这种明确本人归属，不尝试把sales Task越岗交给另service。其它岗位原Task需转交时沿已有MF.responsible的原GET/TaskID/版本/员工/原因三字段AssignInput，无request_id；其余业务提交均有request_id及精确原回执。
7. inventory 两件各准备retail_dispatch -1000，再一次整单实发，原平均库存成本A1000/B2000分，RetailDispatch/StockMove/负Reservation及WarehouseEntry逐项守恒。technician本人原retail_install上传evidence并明确安装结果；service本人原retail_accept实际接收。安装来源为原FlowEvent retail_install+Line WorkItem/code+Dispatch；没有原独立quality动作，不编造repair_installation或维修/加装质检。
8. 接收后service冻结新券1张/本金500分方案，自动剩现金5000分。3Tender/3Unit/7Allocation冻结三原组成（A商品2500、A安装500、B商品3000），券只A goods，原C/P/S总6000/5900/6000；计划不提前占额或扣钱。finance本金与新券分别reserve→capture；当前case/plan/member/wallet/reservation CAS每次从原成功刷新与DB核。非现金核销净C1000/P900/S1000分，无新Cash；member9200分/占额0，券可用0/占额0。
9. finance 原Retail receive2000、3000分两次，独立receipt、唯一凭证和Cash/PaymentLink/RetailPayment，各只落原现金Unit的有限Allocation，剩现金/应收3000→0。终态Case completed、无open Task；charge/net_paid6000分、现金5000分、net_price/revenue5900分、库存成本3000分、group recognized900分/内部往来1000分/group discount100分/service discount0、退款0。无期会rule的PointsClaim rule_id=null且无消费奖积分。最终A2/2000分、B1/2000分在原库存页面再读。

以上全部正向由真实原页面操作。API仅观察本次原网络/原响应，DB仅SELECT；库位准备、实际收发、安装、接收、集团扣账、实际现金各自留事实。主分支任何未知/失败立即停止，没有更换request_id、后台写或重放。

## 原函数接线及旧行保护

采购沿 `procurement_api.py` Create/Receive/ReturnRef/Pay/Refund 与 `procurement_service.create/command/_sync`，v3双原退CAS；库位沿 `warehouse_api.allocate` 原post与 `warehouse_stock.after_stock_move`。精品沿 `retail_api.py` 原schema、`retail_service.create/command/describe`；混合付款沿 `retail_group_api.py` Selection/Authorize/TenderAct/Capture、`retail_group_service.prepare_plan/reserve/capture/attach_cash/totals_adjustment`。发行沿 `membership_service` execute委托 `group_benefits_service._issue`，不从Retail非法发行。

每次合法登录完成后才建立业务baseline，保留全部原login audit。新代码内两批inline prepare/receive分开守卫，避免外围baseline包含共享helper内部合法重登录；共享helper原件/Task/typed-master等直接复用不修改。每步全业务表hash、原行逐列及BLOB内存比较；只准当前Case/Task、两新Item/真实Balance、当前prepared Allocation、新Return/Member/Wallet/Plan/Reservation及原Account的具体有限列。

新append数量按动作明确：两行准备/receive、两实际出库及WarehouseEntry、每笔现金唯一Cash/原关联、每次Group/Benefit往来精确双边。所有其他旧行/其他门店/旧现金库存/卡/规则/原始Entry/权限配置保护；没有粗排除audit、Cash、StockMove或原附件表。采购仅原第二批receive可将receiving_closed从false改true，原data其它既有键不可覆盖；单据类型、代次、商品关联和冻结价格行不改。现金Guard核实际分类、本人、账户、凭证/approved/payment_method，非现金Guard禁止Cash追加。

附件经原UI选择上传，核actual DB bytes/length/SHA/security结构记录；Checkpoint只FileAsset元信息与stored_blob长度/hash。没有bytes/default=str/base64持久化。结构扫描不当真实ClamAV或真实外部签字。

只有六完整check后输出有限 `boutique_sources`/`report_sources`：本店/customer/member/account；supplier/category/brand/两Item/Profile/warehouses/location/Enrollment；两activate case/采购Case/Lines/4Receipt/原pay和Cash/Return及Line/Post/Valuation/原款Refund；实际WorkItem/code/Retail两Line/Dispatch/Move/Reservation/install和accept Event；新CouponRule/版、Eligibility Case/Scope/Decision、Membership发行Case/新Wallet/Origin/Cash/Binding；Plan/Tender/Unit/Allocation/Reservation/Capture、原Group/Benefit Entry/PaymentLink/Settlement、两RetailPayment/Link/Cash/现金Allocation以及原库存/位置账IDs。ID来自原本次响应/有限sameCase SELECT，无已执行时不会输出假来源。

## 静态状态与待实测

作者人工核原UI/API字段、双CAS、任务和原账；AST及helper调用参数、六标题/check绑定、有限SQL表/字段与SELECT-only、三元组有限timeout、无app import/导入时业务动作、UTF8与空白检查通过。首次冻结源码1084行，SHA256 `455b55d919b7f92c57a2532be0516cc19eaa0e642504c54de39c4862e5f899ae`；后续窄修冻结见下节。本页hash在最终交接单独报告，避免自引用。

独立只读短审、root注册/镜像及首次原生实际运行仍待做；动态lookup/折叠/每岗实际Task默认经办、multipart可观测、两个连续inline准备及Linux/业务时区、时间预算仍需真跑。原材料/会员六后继其他run通过不成为本候选通过。六类人工标准仍pending，不写business_accepted。

未覆盖分支保持not_tested：采购预付款/过期/终止余量/取消及获批未发退货撤销；不同成本混批非零差额、缺货/超额/重复/并发CAS；券原退恢复/到期/跨店/积分兑换/消费积分；精品客户退货/整改/复检/保留费/现金退款及真实销售套餐。HK063/066关联维修、HK065加装、HK067客户退货、HK068精品套餐及HK156安装报表不算本批通过。真实PG/Linux、ClamAV、员工人工试用、真实模型和生产门槛全部保留。

## 原集团回执静态修正

2026-10-01，独立只读短审首次冻结候选发现一处确定的回执家族误配，根登记 `PATCH-M8-4-BOUTIQUE-GROUP-RECEIPT-CONTRACT-01` 后授权窄修。本发现来自源码合同核对，候选尚未实际运行，不登记实测失败。

仅 `paid_coupon` 的原 `membership_create`、`mixed_plan` 的原 `retail_group_authorize`、`mixed_capture` 的原 `retail_group_reserve/capture` 三组Guard不再要求追加 `flow_request_receipts`。它们实际沿 `group_service._execute` 只追加一条本人/本店/原request_id/动作及payload摘要匹配的 `GroupReceipt`，原 `group_receipt` 验证保持。三组原事件和审计数量也保持，所有旧回执及全业务表/旧行继续严格保护；对应动作若新增或改动 `FlowRequestReceipt`，全表变化守卫仍会拒绝。其余采购、库位和普通Retail的 `FLOW` 常量及各自 `FlowRequestReceipt` 要求完全保留。

窄修后的源码仍1084行，SHA256 `42ffb6dcbbf8726c7bc073e55c2f5e2b130c61b443c55fc35392c095713ee3b2`。重新核对AST、helper参数、仅三处回执差异、三元组、SELECT-only及空白；独立增量复读及首次真实运行仍待做，没有业务通过成绩。注册顺序须在会员等级/消费积分候选之前：本候选沿原有限依赖明确无会员会期，不借后者的会期后券来源改变本合同。
