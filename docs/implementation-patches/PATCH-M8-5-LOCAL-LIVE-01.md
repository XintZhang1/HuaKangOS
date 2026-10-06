# 本地真实模型复验入口

## 08be534二十六代表后的两条指南澄清（2026-10-06，事前范围登记）

已实施并独审：仅两guide的5个既有字符串，原API/UI条件核对无阻挡；报告SHA `a745a4cdf43276d69b292008af95b34f23f7334adceee6b8ab691ac5a1bbdac6`。原生成器build/check通过，193需求/111流程/70截图保持，无app改动。26语义汇总v2 SHA `b85d7125e0483b52596394f4b540ef1449bb1b2d50a93fa0d0269761067ed78f`仅更新已封存分片原件路径，24/2结论及所有case SHA不变；原聚合保留。新strict、两代表及完整复验待执行。

新strict `20261006T100114Z-ee7f81d5c2` 18通过；同五输入代表 `20261006T100207Z-5c63532980` 自然CLI0/366.313秒，26结构全部通过，语义24可接受/2失败。HELP082把客户报价确认列为精品实际收款必备；原`retail_service.py`的收款任务及receive守卫要求原报价已批准、可收金额、真实到账、凭据和原任务，不要求客户报价确认。HELP092将混合岗位分别绑定到“提交费用与原路方案”和“核实事实并应用纠正”；原`aftercare_service.ROLES`的plan/customer_confirm由销售、服务顾问或管理员办理，独立approve由主管岗位办理，apply/refund/collect由财务或管理员办理。

本次生产范围仅`docs/workflow-source/business.json`的`wf-retail-sale`及`wf-sale-aftercare`：在原步骤及必要对应assistant/exceptions字符串内分清客户报价确认与现金收款条件、方案提交/独立批准/客户同意录入/财务应用及逐原款收退款岗位。保留原API权限、任务、版本、证据及资金守卫，保留guide结构、步骤数、入口、193/111及其余109条。使用原生成器更新三发布文件并check；不改任何app或测试节点。root维护本补丁、当前计划/CP与审阅记录，不改`total_plan.md`。

68新POST结算0.915166元，累计6438次已结192.004796元，旧七未知66.322432元，占258.327228元。root已在进程排空后持原锁显式halt，停后SHA `d730b9595071fe1c8766a9f2c46b2eab49e8dd4570e16266cd27e5d4078eaf92`；其余行与metadata保持，原件在V/closeout-20261006/representative100207-explicit-stop。累计350元/9000次不变。

外部只将原manifest代表参数选为原失败HELP-HK-082/092，两个ID已在allowlist，adapter/restoration/原283及101/评分全部不动。源码独审并冻结后重绑source及必要manifest/gate，新同五输入strict通过，root才可显式一次ack固定6438停止，再复验两原场景并从零完整283。只改说明，无新业务节点或长collector。M8.5保持in_progress、CP-37 not_ready，M8.6未开始。

## ecf73b7完整轮后的说明合同集中修复（2026-10-06，事前登记后已实施，待真实复验）

有限修订已落盘：两份app文件仅原提示词和两个路由summary说明变化，去除对应文字后AST与ecf73b7一致；12指南共42字符串字段变化，结构、步骤数、入口/角色、截图及其余99条保持。原生成器build与`--check`通过，193需求/111流程、70截图及coverage保持。独立app审阅SHA `5f5eea31d3111ddb19f59b7258a948ca07c0aef33f52a9672d8a222c3f72481a`；指南原API/UI交叉审阅SHA `f1f588f82d0bf3ba0752ac574e048727f8a9a634d8fca716883e72c47b3f9e43`，证据均在V/closeout-20261006。完整轮最终聚合为257可接受/26失败（d9753fc7），下段保留事前登记时的汇总阶段。下一步冻结源码，绑定有限26代表输入，新strict通过后显式确认6370停止，再执行代表与从零完整复验；未预记通过。

HELP126新代表`20261006T081940Z-8e4184158b`真实语义通过后，同源码完整轮`20261006T082328Z-58f97d40f2`已从零执行283例，自然CLI0/4712.219秒；原结构282/283、同批101子集100/101，保留B03原检查并按已审R4十条件另列当前结构283/283、101/101。结构通过不等于语义通过，逐例审阅尚在汇总，已确认具体岗位、分支前置、版本适用、审计小计、入口及当前快照口径错误。此轮源码和所有注册输入运行期间保持冻结，旧报告不改。

937新POST全部HTTP200并结算10.629723元；累计6370条，已结191.089630元加旧七未知66.322432元，占257.412062元，无新未知或预留。root在进程自然排空后按原锁、固定run及账本SHA显式停止；仅两halt字段变化，停后SHA`b784268027e59d3c8a35f842ba09e6f008a0818d48fcc926fa5954be48af38f7`，证据`V/closeout-20261006/full082328-explicit-stop/`。350元/9000次保持。

本次仍只实施M8.5，先登记以下有限范围再修改；任何新增失败若超出此表先补登记。原业务权限、状态机、字段含义、现金/实物/确认守卫、API处理逻辑及四个生产默认开关均不改：

| 文件 | 当前证据支持的最小修订 |
|---|---|
| `app/business_assistant_prompt.py` | 原单段接既有`workflow_definition`固定版本与原入口；帮助段按当前具体动作的actor、事实来源及分支条件说明，不将入口岗位或相邻动作条件合并。接口简介和空关键词结果不作为能力穷举。系统段接原audit的`page_counts`范围，不额外编造分类小计；先给明确账号入口，凭据说明独立成段，原脱敏保持。 |
| `app/inventory_reports_api.py` | 仅为原查询/导出装饰器补充准确说明：原kind与报表范围、VIN仅vehicles、item_id/warehouse_id仅warehouses；不修改参数校验或build守卫。 |
| `docs/workflow-source/business.json` | 仅`wf-sale-addon`分清客户接收与财务收款分支；`wf-repair-complete`分清原v3直接建立/v4来源及内部承担不形成待收；`wf-customer-reimbursement`分别说明申请/独审/实际返还岗位；`wf-member-topup-refund`说明原退款申请及撤销身份。 |
| `docs/workflow-source/services.json` | 仅`wf-member-principal`同步原退款申请/撤销身份；`wf-insurance-renewal`消除assistant.prompt对全部结案结果合问新保单的歧义；`wf-report-152`明确库位/在途期间账与全店物资账、有效期初不要求期间有发生；`wf-report-157/158/159/162`将当前快照与另表期间流水区分；`wf-suppliers-and-insurers`按供应商/保险公司分别说明原业务引用，不混用对象ID。 |

使用原生成器更新三份发布文件并`--check`；193项/111流程、截图、coverage、步骤数与合法入口保持。其余已准确的指南不因单例回答错误重写。root维护本补丁、实施计划当前段和审阅/任务记录；协作只在同一M8.5范围实施与交叉审阅，不并行M8.6，不重启取消项，不改`total_plan.md`。

外部仅在原M8.5适配的代表允许集及原manifest参数选入本轮最终确认的失败ID，同步必要restoration来源SHA；原283/101场景、评分、B03十条件和完整执行逻辑保持。先原生成器、静态差异与独立审阅，冻结提交后重绑source/external及原gate/manifest并执行同五输入strict，root才可显式一次ack固定6370条停止。原已通过且本次未改的业务节点不重复长collector；新真实代表逐例通过后，再从零完整283/101，普通语义失败收完整批、安全/隔离/费用异常停止。不得以代表片段拼成完整通过。

## d4b24f4二十代表后的套餐岗位说明修正（2026-10-06，实现已落盘，待真实验证）

新strict `20261006T074545Z-da97e3e202`及三原节点 `20261006T074617Z-2070c869d5`通过；20代表 `20261006T075631Z-e599d7eb0b`自然CLI0/383.375秒，结构20/20、同批101子集7/7，逐例语义19可接受/1失败。新失败HELP-HK-126把财务列为购买申请/客户授权经办人；`repair_package_service.create_purchase`只允许FRONT，授权为FRONT|MANAGE，到账发行才为FINANCE。旧本店组件映射被前置到购买的问题本轮已消除；不能用零卡、零确认或467表不变豁免岗位说明错误。

允许仅修改`docs/workflow-source/business.json::wf-repair-package`及`services.json::wf-customer-repair-package`原购买步骤的actor/action文字，明确申请、授权、实际到账发行各自岗位；保留原步骤数、当前购买与工单使用分支及其条件，不改原API/权限或全局prompt，不增加帮助步骤上限。用原生成器同步三份发布文件并做--check，193/111、coverage、入口岗位和原业务守卫保持。

实际采用v2候选（`help126-purchase-roles-v2-candidate-20261006T081558Z-60fdd43e/guide-replacements.json` SHA `f3b23b517badd6fe3e4c6fbe8638d3036e7676973695edc504ed2201abfb18bd`）：说明销售/服务顾问/管理员申请并在页面记录授权，财务/管理员按真实到账发行。独审发现原API允许店长授权，但当前页面按钮限FRONT，故manual只描述现有可见路径，不用“仅”否定店长的合法原API能力；原UI/API不改。两完整候选已按原字节SHA安装，原5/6步骤及退款完整；生成器build和--check均通过，193项/111流程/70截图保持，未声称业务验收。

74新POST全部200/settled共0.827486元；累计5431条已结180.430233元加旧七未知66.322432元，占246.752665元，无新未知/预留。排空后显式halt SHA `c956bd88bf5a8e7aa0ba0322db0bb09b14ed4053c835a753714a16f3e08019f7`，全部旧行及metadata保持。原三节点已通过，此次只有说明文字变化，不重复长collector或改测试。外部仅将manifest代表参数改选原HELP-HK-126并重绑gate/source和manifest gateSHA；20代表adapter允许集、原283/101、场景/评分/测试/restoration及350元/9000次保持。独立静审、原生成器及新同五输入strict通过后，root显式一次ack上述精确停止；HELP126新真实代表通过后，从零完整283/101集中审阅。新结果留V，不改正在验证的冻结源码。M8.5仍in_progress，M8.6未开始。

## 5f63427二十代表后的有限修复登记（2026-10-06，实现已落盘，待验证）

本节取代下面旧轮的待执行描述，不改变历史成绩。`5f63427` / source `d0b55812f0c1d2523027c57ac6e46a1044317dd96b790dccb3f086566eae1b5c` 的strict `20261006T065927Z-ba14311333` 和原五节点定向 `20261006T065959Z-6e97bdee42`均通过。新20代表 `20261006T071113Z-5aa1384574`自然CLI0/388.063秒，20/20结构通过，同批101子集7/7；语义11可接受/9失败，不能据CLI0记业务通过。失败为Y07、X02、X03、HELP-HK-051/061/073/126/164/178。全部20例0卡、0确认、467张业务表前后等值。

70个新POST全部200并结算0.834455元；累计5357条已结179.602747元，旧七未知66.322432元保留，占245.925179元，无新未知或预留。当前已绑定同一累计350元、9000次，固定`deepseek-flash`及thinking/high。root自然排空后显式halt，停后账本SHA `19004b998fd15fb74c07907b2db9a5c24ac0119fb37a5bf343fb4a174cec8787`，原5357行和其它metadata不变。停机证据在`V/closeout-20261006/representative20-explicit-stop-20261006/`。

审阅纠正：安全`tool_trace`只含成功返回的工具。新代表与旧052500完整轮的Y07都在Runtime记录中发起了users/audit读取，随后被读取器岗位预检查403挡下；不能写成“未调用”。未产生相应原API拒绝记录，旧完整轮还读到了空refusals。失败依据是没有真实可评审记录仍承诺能够申请评审。旧报告原件保留，另附勘误，失败分母及结论不变。

本次只在同一M8.5内实施以下范围，已先登记后落盘并完成独立静审；不改原API、数据库、权限、状态机、实际提交或四个默认关闭开关：

| 文件 | 本次限定修复 |
|---|---|
| `app/business_assistant_case_tools.py` | 在既有`project_case_read`和必要的`_guidance`接线中，将终态任务的实际完成/终止事实与原办理责任结构分清；保留授权历史信息和原事件，未知仍未知，不从责任人或当前owner推断操作者/接手对象，native结果保持。 |
| `app/business_assistant_guides.py` | 仅对现有精确名称检索结果标明实际匹配种类、原需求范围与覆盖范围，区分精确命中和模糊相关；保留原多匹配、排序、上限、岗位与未命中路径，不因具体案例加特判。 |
| `app/business_assistant_prompt.py` | 修正原旧盘点段：旧Flow盘点仍为物资汇总口径，但已启用库位账的差额按原Allocation/count规则落实到库位；不能声称绝不影响库位。原评审段区分失败响应的can_escalate标志与原refusals列表的真实类别/提交条件；必须有对应原记录，403或静态提示本身不构成可申请承诺。 |
| `docs/workflow-source/business.json` | 仅`wf-sale-delivery`将按各自条件办理的收款/检查分支表达清楚，不能由序号虚构普遍依赖；`wf-repair-package`分清套餐独立批准、销售/发放及维修使用时的本店匹配。 |
| `docs/workflow-source/services.json` | 仅`wf-customer-repair-package`同步实际购买与使用分支；`wf-report-164`按当前有效客户车辆关系快照说明查询，不虚构期间过滤；`wf-warehouse-location-masters`分清仓库/库位配置与后续业务引用，不要求配置提供VIN、交接日期/凭据。 |

三份发布生成物已沿原生成器build及--check更新并通过，193需求/111工作流、截图/coverage及迁移保持。维护交接仅同步上述事实投影含义，不扩大业务范围；`total_plan.md`不动。

外部只在原case_tools任务事实节点和原guides分类/精确检索节点内同步投影断言，原断言及节点数保持；同次额外执行原`tests/test_warehouse.py::test_location_preparation_does_not_invalidate_legacy_count_item_snapshot`，该节点源码不改，核真实旧盘点与库位差额。复用原M8.2诊断，02组两节点、20组一节点；不新增测试框架、不重复前轮其余未变节点。

仅按实际两文件变化维护`V/archive/baseline-restoration.json`来源及`prior_registration`，并在源码冻结后更新原gate和manifest绑定；20代表选择、适配器、原283/101、冻结输入/评分、费用上限及四harness代码均不改。候选独立静审、新同五输入strict及上述三节点通过后，root才可显式一次ack上述固定停止，只改halted/halt_reason，全部费用历史保持；不自动启动付费或解除后续停止。随后20原代表真实复验并集中审阅，满足后从零完整283/101。一般语义失败完整采集后修复，安全/隔离/费用异常仍立即停。M8.5仍in_progress、CP-37 not_ready，M8.6未开始。

## fd30372完整283后的集中修复登记（2026-10-06，实现已落盘，待验证）

本节是本次精确允许范围；下方各轮记录保留当时结果与预算条件。集中实现已落盘并经root静审，生成器发布build及check通过；外部输入待绑定，新strict、五原节点、20代表及完整283均待验证，不预记修复成功。源码冻结后，外部动态绑定与后续执行结果在仓库外留证，不为补记绑定再次改动冻结源码。

`fd30372065a132852529c324e8e116f4899cc5d5` / source `10a66e023ed2f678649e74dd8ecde35a4b38696275286effe05223c0ad9100ae` 的完整Flash运行 `20261006T052500Z-e070771e64` 自然CLI1/4416.875秒、无超时、进程drained，原283全部在同一轮新执行、0继承，101只是同批子集。原结构281/283、99/101；R4当前合同另列282/283、100/101。原失败B03/X03保留；B03十项原登记条件本轮成立仅影响另列R4判断，X03仍失败。逐例语义263可接受/20失败，0未运行；汇总 `V/closeout-20261006/flash-full-20261006T052500Z-e070771e64-review/aggregate-review.json` SHA `d72ecee11b6bea37b1b6ba58c63312e0088c5b50e1a235a82a41b9229e0e5621`。全部283例467业务表图不变、零确认请求，并不豁免回答及不当备卡错误。

本批20个原失败ID：S07、M01、Y04、Y07、X02、X03、X08、HELP-HK-038、HELP-HK-048、HELP-HK-051、HELP-HK-061、HELP-HK-073、HELP-HK-101、HELP-HK-121、HELP-HK-122、HELP-HK-126、HELP-HK-131、HELP-HK-164、HELP-HK-178、HELP-HK-188。原提示词/expected_outcome、283及101定义、原结构评分和既有B03十条件保持；观察不扩成新增验收要求，不能为提高分数多备卡。

| 允许生产文件 | 本次限定修复 |
|---|---|
| `app/warehouse_service.py` | 原stock_view保留enabled，复用已读取值补item_active、location_ledger_enabled及字段含义，区分物资档案与库位账；无新SQL，原列表/成本权限/UI旧字段行为不变（M01）。 |
| `app/business_assistant_gateway.py` | 目录岗位说明附static_catalog/request_executed=false，不冒充已发查询或refusal；仅对已授权200且未截断的原audit页附本页分类计数、原customers页附客户ID/owner_id/当前员工ID含义，不追加读取、不改原data、权限或拒绝（Y04/Y07/X08）。同步两处过时职责注释。 |
| `app/business_assistant_case_tools.py` | 仅澄清既有终态original_assignment.meaning：待办办理责任不是动作输入的业务接手对象，后者核原事件detail；实际完成者仍用done_by，原字段、深复制与native结果保持（X02）。 |
| `app/business_assistant_prompt.py` | 原委托边界段说明拒绝绕过后不能擅自改办收款等其它业务；唯一可办动作不是员工委托，不加关键词拦截或业务特判，不改确认守卫（X03）。 |
| `app/business_assistant_business_tools.py` | 完整筛选后的表单封装entries为空时附原操作目录尚未核对及list_operations/inspect_operation下一步；不把空封装当能力上限，不增renew快捷表单、API或卡（HELP122）。 |
| `app/business_assistant_guides.py` | 仅模型帮助检索：规范化发布标题/原需求标题精确命中时保留全部精确命中，再沿原排序、投影、3项上限；未精确命中路径保持，不改变UI搜索、目录或权限（HELP164/178/188）。 |
| `docs/workflow-source/business.json`、`docs/workflow-source/services.json` | 仅11条原guide：wf-sale-addon、wf-repair-rework、wf-material-other-in、wf-consumable-issue-return、wf-material-other-out、wf-material-local-move、wf-material-stock-count、wf-questionnaire-design-and-answer、wf-member-renew-tier、wf-coupons-and-benefits、wf-customer-repair-package。纠正创建加装与实际VIN条件、返修批准相对申请人、仓储当前待办权限及盘点初始approve、实际单选题型、会员身份与识别卡、当前岗位客户范围，以及套餐购买与本店实际使用映射条件。保留原业务守卫，不凭指引顺序加依赖。 |
| `app/assistant_runtime_domains/system_readonly.py`、`app/business_assistant_capabilities.json`、`docs/维护交接.md` | 仅维护说明及本适配器unsupported事实原因的准确表达；说明共用project_case_read、原版本定义、终态真实办理者、金额展示和当前Flash。capabilities操作列表、路由/注册、事实键和权限不动。 |

生成范围仅 `web/workflow-guides.json`、`web/workflow-handbook.html`、`docs/全量工作流手册.html`，用原 `scripts/build_workflow_guides.py` 发布构建及--check；111工作流、193需求映射、原截图和coverage原件保持。本批已使用原生成器完成发布build及check；此结果只证明生成物一致，不替代业务或模型验证。

外部只扩以下五个原节点，保留原断言、节点数与原套件；不新增框架：

- `V/tests/baseline/overlay/tests/test_business_assistant_case_tools.py::test_get_case_returns_native_actions_and_missing_phone_prevents_any_draft`：同步终态原责任含义，原真实两读取通道、版本定义、金额、未知成本等断言保持。
- `V/tests/baseline/overlay/tests/test_business_assistant_gateway.py::test_catalog_subset_and_sanitizing_are_explicit`：原真实HTTP读取不变及授权返回页元数据、截断/拒绝不注释。
- `V/tests/baseline/overlay/tests/test_business_assistant_scope.py::test_the_operation_list_hands_the_role_through_the_normal_tool_path`：目录岗位元数据无实际请求/refusal。
- `V/tests/baseline/overlay/tests/test_business_assistant_guides.py::test_category_narrows_the_same_catalogue`：真实已发布标题/需求标题精确命中、多个原映射及各自岗位保持。
- `V/tests/baseline/overlay/tests/test_warehouse.py::test_existing_ledger_activation_no_stock_duplication_and_stale_activation_refused`：物资启用与库位账启用独立、列表/详情一致及旧库存不变。

外部适配与来源允许范围：同overlay的 `m85_runtime_live.py` 仅把上述既有20个失败ID补入REPRESENTATIVES允许选择集，不改夹具或评分；`V/archive/baseline-restoration.json` 仅按实际改动重绑来源并保留prior_registration；`V/validation-manifest.json` 仅设置20代表参数及gate SHA；`V/harness/live_gate.py` 仅MAX_ATTEMPTS由6000增至9000；`V/live-evaluation/gates/deepseek-current.json` 仅同步次数cap、固定四harness文件及source/external指纹绑定。既有runner、isolation、runtime_guard不改，不读取或将私有凭据写入报告。

费用实录：本轮939次新POST全部HTTP200并结算11.017271元；累计5287条，已结算178.768292元，加七条旧未知66.322432元，保守占245.090724元，零新未知、零预留。原4348行和metadata保持，未知不释放、不重价、不重放。业主已授权次数6000→9000，金额仍为同一累计350元，不另开预算；此次外部上限与指纹变更待绑定，动态绑定证据留在仓库外。root已在自然排空后显式halt，5287条停后SHA `8246a889bb8d2d3f9685abdef770ee4437d14f595722345186d45ad61c840115`。仅在当前集中候选独立静审、新同五输入strict和上述精确五节点通过后，允许root显式一次ack解除该次固定停止；只能改halted/halt_reason，全部历史行/费用/metadata保持，不自动解除后续停止，不自动启动付费。

执行顺序：本登记及上述精确生产/生成物已安装并核静态差异；冻结源码后，在仓库外绑定外部输入与新五指纹；新M0.1 strict及M8.2原五节点定向（3+1+1原节点组）通过后，核固定停止并显式ack，再新执行上述20原代表逐例语义审阅；随后从零单次新执行完整283并单列101子集。代表、旧R04和旧全量均不拼入新成绩。安全/未确认写入/隔离或费用异常立即停；一般语义问题完整采集后集中修复。当前M8.5 in_progress、CP-37 not_ready、M8.6 todo；M8.10 done，取消的OS/部署独立门槛不重启，total_plan.md不改。

## 原单金额的精确展示单位（2026-10-06）

12d8602/source2fe16742 的strict `20261006T044929Z-607dc5ba47`和原节点定向 `20261006T045010Z-5180298be0`通过（清单收集495.843秒、目标25.64秒）。R04真实代表 `20261006T045959Z-2a7299aba3`自然CLI0/56.203秒，原版本workflow_definition已实际读到，回答不再新增新版独立费用承担步骤；但把原amount_cents=50000写成“应收50000元”，正确值是500元。结构1/1不能掩盖这次明确金额错误。

4个POST均200/settled共0.034912元；累计4343次已结167.706145元加七条旧未知66.322432元，占234.028577元。代表已排空，root显式停止后SHA `6aff0272fe1861c0b6ec1bd129776512bbb584597a5d6baf9057121cde7f95f7`；全部原行、未知和metadata保留，未开新full。

范围仍限既有 `project_case_read`：为已授权结果中实际存在且为整数的amount_cents、paid_cents、cost_cents附money_fields，逐项明确storage_unit=分、scale=100、精确元display字符串和unit=元。用整数商余处理正负与零，不用浮点或假填null成本，不新增查询或改原数值/业务含义。workflow_definition原notice澄清fields.label是动作输入表单文案，不能拿它当原data的存储单位；不改原动作定义或全局prompt。外部仅在相同原case_tools节点补授权存在字段、缺失/null保持和精确单位断言，原定义/事实测试保留；原R04选择、冻结283/101、评分不变。独立静审、新strict和该原节点通过后再真实R04；root只可显式解除本次精确停止，预算与后续完整采集规则保持。

## 原单版本的只读动作定义（2026-10-06）

b4a672c/source ddffdd6c 的strict `20261006T043344Z-472a1ba8a3`通过。V03/R04真实代表 `20261006T043513Z-ed59d2981d`自然CLI0/137.828秒，结构2/2但语义仅V03可接受、R04失败；R04实际读到了完整新旧版本说明，仍把新版“确认费用承担”步骤当作旧版工单必经项。说明提示并未补齐模型可读的旧单动作定义：当前get_case只给当前岗位/当前状态动作，通用帮助给的是当前明细流程，不能继续只堆文案求通过。V03空结果归因的过度解释单列观察，原件保持。

14个新POST全部200/settled共0.174299元，累计4339次已结167.671233元、七条旧未知66.322432元，保守占233.993665元。代表已排空，root显式停止后SHA `77bcb4f8616b954a3039863b66f80a54a91ec1b09d64a83a55cb5584868637d8`；全部原行/metadata保持，未启动新完整轮。

允许仅扩展 `app/business_assistant_case_tools.py::project_case_read` 既有助手只读投影：对已授权成功读取的原单，按原kind/flow_version从既有flow_spec取得非空动作定义，附workflow_definition（原版本/名称、动作key/label、声明roles/states及字段key/label）。不写另一套状态机或推导依赖，目录不是当前员工可办清单；原actions、任务、原data事实及现有终态责任投影保持。专门业务没有通用动作定义时不伪造或用其它版本补齐；原HTTP、native reader、权限、身份和提交守卫不动。两条read_data和get_case已共用该投影，无新接口或全局prompt分支。

外部复用原case_tools任务事实节点验证当前版本来源与读取接线、原native结果/动作/事实不变、旧repair定义包含原报价结算方且无新版独立冻结承担动作、专门repair版本不借用旧定义。候选在仓库外审阅登记，保留原断言、冻结283/101和评分；原有限代表改选R04。新strict、原节点定向和真实R04通过后，从零完整采集并集中审阅。root只有核对上述精确停后账本和新验证后才可显式解除该次停止，350元/6000次及全部未知占用保持。

## 发运与到货导入共用原请款行来源（2026-10-06）

acec51e/source01ae774 的strict `20261006T041205Z-9c054ef5cd`和S06/V04真实代表 `20261006T041247Z-f2cb98f09f`通过；代表结构/语义2/2，12POST结算0.122735元。新完整轮 `20261006T041711Z-5c7769ca07` 的V03在读到原CSV目录后，仍明确将到货清单的来源写成“已确认发运清单行”。实际 `vehicle_imports_service.prepare` 的ship/receive均要求manifest_row_id引用同采购单已确认funds批次的同VIN行；到货另核已确认发运事实，两者不能混为同一来源编号。当前无卡、无实际入库，但对象来源说明错误不能记通过。

root在场景边界持原预算锁停止，CLI1/461.36秒自然排空。4325条停后账本SHA `7c27aacd486ed13cda9bcf2e0eab7ce448220249d5d393686f691f0b3f99968a`；旧行及七条未知原样保留。本次生产仅改 `app/vehicle_imports_api.py` 已有 `csv_field_notes.manifest_row_id` 的说明：ship/receive共用原请款行，到货所需发运事实与引用ID分开说明。原查询、CSV列、权限、校验和业务动作不动，不叠加全局prompt或增加接口。独立静审、新strict后通过原有限代表选择V03真实复验；外部仅改manifest代表参数和来源绑定，adapter、冻结283/101及评分不变，不因单字段说明重复长collector。root可显式解除上述已审固定停止，预算350元/6000次与未知占用不变；后续完整轮仍从零独立执行。

同轮R04另经交叉审阅确认失败：原repair flow_version=2在报价data.payer和quote事件已登记客户承担，模型却套用当前维修明细指引的独立“确认费用承担”步骤，并导向repair-orders。追加范围仅 `docs/workflow-source/business.json` 原 `wf-repair-complete` 的prerequisites，标清明细工单与旧版原单差异，旧版已登记承担方不算缺项；沿原生成器同步三份发布生成物。原flow_specs、flow_engine、flow_navigation及API不改，193/111与原指引其它步骤保持。外部有限代表改为V03/R04，允许只将R04加入原选择集并按原addition更新来源；冻结场景/评分不改。

下一完整轮在冻结输入上收集全部场景和语义失败后统一审阅修复，避免一般回答错误导致反复重跑前段；越权或未确认写入、隔离/费用异常仍立即停止。完整执行不等于通过，有实际业务错误时仍保持M8.5 in_progress，不降低关键错误为0的完成条件。

## 查询证据与未核实依赖的对称表述（2026-10-06）

fb42f53/source00ec2090 的strict `20261006T033850Z-f567eea18c`、原任务事实定向 `20261006T033949Z-328ae5021f`及S06真实代表 `20261006T034946Z-52868592ea`通过。代表5POST结算0.067085元，终态责任投影真实接入Runtime；代表通过不覆盖后续full。新full `20261006T035410Z-5c6da75ed5`实际18/283，原结构18/18、独立语义16可接受/2失败，265未运行。S06完成者已正确，但把未核实依赖解释成车款/PDI不是提车必需步骤；V04正确查空并读到调拨指引后，仍编造记录出现条件和另一店代验收规则。两者均为无来源解释，不是原业务守卫问题。

root持原预算锁在场景边界明确停止，CLI1/402.75秒自然排空，18×467业务图未变、零确认。95新增POST全部结算0.919959元；累计4208次已结166.324019元，加七条旧未知66.322432元，保守占232.646451元。停后账本SHA `b2cdc42828311ba7d52ab5b7703f1ac4c9b41f248739e740b6dda7e86c2f72e5`，全部原件及未知占用保留。

本次生产范围仅为 `app/business_assistant_prompt.py` 原查询/读单两段及 `app/business_assistant_case_tools.py::_guidance` 原待办说明：未知依赖既不能确认为必需，也不能排除为非必需；空查询不推断原因、可见时点或他岗/他店代办要求。继续沿适用已发布指引及原单事实核对，不新增API、岗位权限、状态机、输出修正规则或业务特判。外部只登记S06/V04有限代表（必要时将V04加入原有限允许集），原冻结283/101、夹具和评分保持。文字调整经独立静审与新strict后真实复验两例；此前任务投影原节点不因本次纯文字改动再重复长collector。root审阅本次停止后仅可显式解除上述精确停后状态，350元/6000次、七条未知和异常停机规则保持；随后从零完整283/101，代表不拼入全量。

## 已办任务责任与实际办理者投影（2026-10-06）

eeb88da/source712983e 的 strict `20261006T031032Z-e587b717fc`、84项定向 `20261006T031100Z-3f6b96a142`及真实三代表 `20261006T032120Z-dc120670f1`均通过；代表语义3/3，但S06完成者括注和跨岗顺序表述另记歧义观察。随后同五输入full `20261006T032447Z-75cd367cfe`在S06再次明确把分派负责人写成实际完成者。原完成记录正确，重复文字提醒不足以消除并列人名的混淆。root持原预算锁在场景边界停止，8/283已运行、275未运行，原结构8/8、语义7可接受/1失败；CLI1/199.031秒自然排空。33个新POST均结算0.435782元，累计4108次已结165.336975元加七条旧未知66.322432元，占231.659407元。原停止后账本SHA `32a4c7ddc334bf6be20ccc1d254cf16650d588f8cd2af1a221e20978fedd9ee8`，费用与旧行不变，不自动解除。

本次精确生产范围为 `app/business_assistant_case_tools.py` 的纯只读模型结果投影，以及 `app/business_assistant_service.py` / `app/assistant_runtime_runner.py` 两条既有read_data返回接线。只处理已授权成功读取的原 `GET /api/flow/cases/{case_id}`：深复制结果，将done/cancelled任务的role、role_label、assignee_id、assignee_name收进明确标注含义的original_assignment；保留原done_by/done_by_name/done_at及缺失值，不把取消解释为完成，不改其它任务字段、顺序或open任务。原HTTP API、数据库、状态机、权限和原始历史不变，Runtime原生业务适配器读取合同不变。get_case、typed内部查询和直接read_data复用同一个投影；不靠新增提示词禁令或模型输出正则修正事实。

外部仅扩展原 `test_get_case_returns_native_actions_and_missing_phone_prevents_any_draft` 节点，验证原API与open任务保持、实际完成/取消人和原分派责任分开、未知实际办理者不回填，及get_case/read_data一致；原准备/缺电话/取消断言保留。有限代表改选S06，不改冻结283/101或评分；重新绑定来源并通过strict、该原节点和S06真实复验后，再执行独立完整队列。root仅可在明确审阅此次停止、保留4108条原行与全部未知占用后解除这个停止状态；350元累计上限、6000次和异常停机规则不变，未来停止不自动恢复。

## Flash首次完整队列：真实任务效果与员工选择器（2026-10-06）

bc81a7a/source6776ccc 的新strict `20261006T021613Z-33eb4e44d3` 通过，原F[complete]定向 `20261006T021701Z-da89ee7a63` 通过。Flash八代表 `20261006T022631Z-879bd0f790` 自然CLI0/216.672秒，原及当前结构8/8、101同批7/7，独立语义8/8；30次真实POST全部结算0.446153元。S08查询范围措辞、V03两次参数纠正和冗余追问另留观察，不删原件。

随后同五输入完整队列 `20261006T023936Z-c619bffc05` 暴露S03确认后把续开的跟进任务误称完成、S05候选员工含原分派接口拒绝的岗位、S06把分派负责人当实际完成者（含“你本人”）。root持原预算锁在场景边界明确停止，实际10/283已运行、273未运行，101同批10/101，CLI1/270.75秒自然排空；原结构10/10、独立语义7可接受/3失败。48POST全部结算0.576235元，无新增未知或预留；累计4062条，已结算164.737646元加七条旧未知66.322432元，保守占231.060078元。停止前后只变halted/halt_reason，原行和费用保持；旧报告不被新代表覆盖。

允许本次最小生产范围：`app/business_assistant_case_tools.py` 的既有原单指导明确登记本次意向沟通后仍保留下次跟进，并从原done_by_name/done_at单列已完成任务事实，缺失保持未知、cancelled不作完成；原数据、状态机和确认行为不变。`app/flow_api.py` 的employee选择器增加明确原action上下文，并与 `app/flow_engine.py` 原lead.assign共享接手岗位合同，逐候选复用原assignable的启用、本店岗位和权限检查；先鉴权原单并核当前实际动作，不能用动作执行人岗位冒充接手岗位。无动作的一般员工查询保持。原动作employee字段附lookup_action，`web/app.js` 与 `web/livechoices.js` 在初始加载、手动搜索和防抖搜索都传同一上下文，保留换店与过期请求保护。`app/business_assistant_business_tools.py` 的对象查询可传该动作，原单工具按各动作分别取候选；原prompt员工查询说明同步，不增加任意写入能力。

外部仅复用原 `tests/baseline/overlay/tests/test_store_roles.py::test_assignment_uses_store_specific_role_without_mutation` 及原 `scripts/check_assistant_r3t3.py::NativeRepairs.test_reception_candidates_from_business_picker_not_accounts`、`scripts/check_assistant_business.py::NativeTests.test_action_by_name_with_live_version` 核合法/拒绝岗位、当前店投影、停用/跨店及原单读取拒绝；保留原断言，不新建框架或改冻结283/101。必要manifest/来源SHA按原位置更新。停止的完整原件、逐例SHA和终态审计留在V/closeout-20261006/flash-full-023936-review；本次是已知语义主动停止，修复后可显式核固定停后账本SHA `13cd772c24f0b319802f8a61c7b8ad74b3195e83ec90d009cdb6b4a63181d289` 保存前后原件后仅解除该次停止，七条未知及350元/6000次不变，不自动恢复以后停止。完整原候选已取得时，模型自带选项逐项核对原ID并恢复原label，保留合法子集和原字符串ID兼容，不静默过滤未知人。外部m85适配器仅补有限代表S03/S05原ID，登记S03/S05/S06三例，原评分与冻结输入不改。先定向复验受影响例，再从零完整283/101；M8.5仍in_progress、CP-37 not_ready。

## 350元累计授权与当前V4.1 Flash切换（2026-10-06）

业主已明确将本地真实模型复验切到当前官方ID`deepseek-flash`，并授权350元累计上限；不是另开350元预算或清空旧消耗。此前280元门禁和Pro运行记录按当时条件保留。`20261006T010901Z-4881d6c544`四例已自然排空，累计3984次、已结算163.715258元，七条未知仍全额占66.322432元，保守总占230.037690元；全部旧行、metadata、金额、未知占用和报告保持，不重价、不释放、不自动重放。

2026-10-06查阅[官方更新日志](https://api-docs.deepseek.com/updates/)与[官方人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：`deepseek-flash`当前映射DeepSeek-V4.1-Flash，峰时缓存命中0.04、未命中2、输出8元每百万token。上下文1048576、最大输出393216，仍用独立上界预留`(1048576×2+393216×8)/1000000=5.242880`元，不依赖缓存命中或峰谷判断才准许POST。完整合法cache分项才按本次政策结算，缺失或矛盾沿用全miss上界。请求ID与官方版本映射分别记录；旧前1402条亦使用Flash名称，不能据此次切换自行断定旧后台为另一版本或回写旧报告。[官方思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)继续支持`thinking.enabled`及`reasoning_effort=high`。

本次外部范围仅为既有helper及私有门禁的模型/费用政策和来源重绑：1—1402条按原旧Flash政策，1403—3984条按原旧Pro政策，3985起新Flash使用本次政策；历史核价按原行所属政策，不随当前MODEL重算。350元是同一累计账本新上限，6000次及七条未知停止边界保留；更新gate、manifest引用及必要来源登记，重新绑定源码/输入/依赖和新strict，不改变原冻结283/101、评分或业务夹具。生产`AssistantConfig`默认已为`deepseek-flash`，provider逐字发送配置模型且无fallback，现thinking/high和Runtime适配器导入gate.MODEL的接线可直接复用，不改生产默认或适配器。

同批仅同步外部原F文件`tests/m82-closeout/runtime-boundaries/test_runtime_provider_budget.py`的三处夹具接口：合成新尝试改为`LEGACY_PRO_ATTEMPTS+1`，`_usage_price`调用显式传政策，六个Mock场景同时将两个历史分界局部patch为0并在退出时恢复。原节点及断言数量、生产、冻结场景不变；其manifest确切SHA与来源登记沿原路径更新，不创建新测试入口。

拟先执行新strict及原F[complete]定向验证，再通过既有representative入口执行S01/S08/V03/X03/F02/B03/HELP021/HELP041八例，检查新模型的真实请求、卡片及语义，随后从零执行完整283并单列重叠101。当前仅登记后续步骤，尚未执行新Flash，M8.5保持in_progress、CP-37 not_ready、M8.6未开始；代表和旧Pro结果均不拼成新完整通过。

## db53920定向30后的三项继续修正（2026-10-06）

`20261006T004756Z-4508d4ab9a` 已自然完成，CLI0/528.938秒，原结构及当前结构30/30，同批101子集7/7；逐条语义27可接受、3失败（V03、X03、HELP041）。姓名完整性及其余本轮受影响说明已纠正。HELP021仅表格编号且没有强制先后措辞，按与其它案例一致的口径通过并留观察，不覆盖旧全283明确错误。B03本轮选择等待会员、零卡，原raw本来通过；未动态触发单卡十条件专判。72POST全部结算3.996324元，累计3970次，已计162.998876元加旧未知66.322432元，保守占229.321308元。旧3898条及metadata精确保留，五指纹/三映射相同，进程排空。终态审计SHA `d877ce68570a5681645a5d1646bc0c96541a59a668236b8e5f877a6902724e44`。

允许仅继续修三处已定位说明：采购指引原财务/库管步骤分别写明各自条件，并将“在验收前计预付”改为“验收前登记的款计预付”，保留四步骤及原付款与实物不互替例外；理赔指引原混合“服务顾问或店长”改为原职责，主管确认维修费用承担时原事务关联核赔，若原单仍需绑定则由服务岗位核已有冻结承担办理，不能教成先绑定后冻结；原prompt读单段仅替换两句，把未知依赖按岗位分别说明，只有有原单或适用指引依据的依赖才能串联，拒绝绕过时也不能编造额外条件。原API/岗位/状态机、此前姓名修复及其它指引不动，不新增场景特判或自动纠正执行路径。

源码限`docs/workflow-source/business.json`两条既有指引和`app/business_assistant_prompt.py`，照原发布构建重发三生成物；外部仅将同phase有限选择设为V03/X03/HELP021/HELP041，适配器及原场景不变。静审、新同输入strict后复验四例；结果仍不拼入全量。280元门禁未改变，完整复验所需预算与未知占用分别保留。

## e01e83b完整283后的指引与目录修正（2026-10-06）

完整运行 `20261005T224028Z-7db0218cc8` 已自然终局，原283全部新执行，原结构282/283、同批101子集100/101，CLI1；B03的旧“不得准备卡”断言与当前缺字段待确认卡合同不同，不能改写原分数。逐条语义审阅仍有真实岗位、依赖、姓名保真和主档字段错误。五输入、三文件映射、全部业务快照和进程排空已独审，允许结束本轮冻结并修复。终态审计 SHA `918a94d532b157247ac5f3c18e01f143785e95f438a100104e37c6e2d27690eb`。858次新调用全部结算40.043135元；累计3898次，按返回用量计159.002552元，七条旧未知66.322432元仍保留，保守占225.324984元。未获新的明确额度答复前保持280元/6000次。

精确生产范围为五处既有说明入口：`vehicle_procurement_api.py` 的catalog按原ROLES附本人岗位元数据；`business_assistant_prompt.py` 强化已给姓名按完整原文保留；`business_assistant_case_tools.py` 澄清任务显示顺序不构成依赖；`business_assistant_guides.py` 区分通用Flow动作与专门领域原详情；`flow_api.py` 仅给现analytics GET增加中文summary，使既有消费券/权益统计可由原操作目录检索。均位于app目录，原查询、业务权限、状态机、数值计算及提交守卫保持；不增加查询或自动提交路径。

指引只改 `docs/workflow-source/business.json` 与 `services.json` 已审条目：采购、意向分派、销售交付、保险单、维修领退料/理赔、客户赔偿、零售、销售加装、代办、其它客户收入、预收、客服事项、续保、消费券、供应商/保险公司、物资品牌/分类。依原API和实际页面区分经理批准与员工办理、现金与实物独立条件、可选主档字段及原业务结果。保留角色入口、原193/111映射、coverage与截图审核；经原非draft生成器统一重发三份既有生成物，不复制各候选的旧生成物。HELP129明确页面路径实际要求已有会员，原前提保留，不按仅看API的初判修改。

外部当前Runtime适配器仅追加B03单独的current-R4结构判定：固定原提示词/检查，单张member_topup待确认卡、精确500元、原金额与会员字段、真实会员待选问题、同本人Run/Work/卡及服务器request_id、业务未变等十项全部成立方可接受。原raw检查、成绩、原件及继承规则不变；不恢复已撤回B04豁免。有限代表选择补入本轮实际失败案例和B03，原283/101/冻结提示词及夹具字节不改。先静审并按同输入strict运行，再验证受影响真实路径；代表不拼入全量，未消除真实错误前不记done。

## 分类与可配性、导入阅读与办理岗位（2026-10-06）

ecf7810/source09e101cc 的四代表 `20261005T222102Z-9845ecf2c3` 自然结束，CLI0/195.234秒，24POST全部结算0.836130元。V05销售占用与V08分岗位说明已纠正；V01却把车型归属确认扩成配车的普遍前提，V07对当前库管说请款清单最后由“你”确认，原catalog的prepare_kinds实际不含funds。原件和失败说明保留，不能由结构4/4放行。累计3019次保守占184.522081元，七条未知及原预算保持。

允许窄改两处原查询输出：`app/vehicle_catalog_service.py` 的现有notice澄清车型分类与available提示是不同事实，实际配车按原单版本与动作守卫；`app/vehicle_imports_api.py` 的catalog按原PREP派生每kind的本人岗位是否允许及原岗位集合，注明读取格式不等于本人可编制/确认。新字段只表达岗位层面的条件，不表示来源、版本或原编制人已验证。原读取门禁、prepare_kinds、CSV字段、候选集合、金额、原业务权限及提交代码保持。不改全局prompt、增加词表或新测试平台；静审这两个原返回点，再复验同四例。

## 原帮助的岗位与移库前置说明（2026-10-06）

6e08d44/source109332a7 的四代表 `20261005T215904Z-071f7523fc` 自然结束，CLI0/218.750秒；V01库存与V07导入固定字段回答正确，V05候选名称已纠正但遗漏销售占用阻断，V08误将请款清单编制岗位说成“通常财务”。结构通过不能覆盖这些语义问题，暂不启动新全量。

允许只修改 `docs/workflow-source/business.json` 中原车辆店内移库及 `wf-vehicle-batch-import` 两条指引：按 `vehicle_operations_service._free/create` 明确销售占用不能通过补库位解除、选定原车须先核可办性；按 `vehicle_imports_service.PREP` 明确请款编制/试执行/本人确认与发运、到货的岗位区别，保持另一主管独立复核。修正原“无明确位置先登记”和“原经办人”的条件及岗位歧义，不改原业务权限或步骤。用原生成器同步三个既有发布生成物；111工作流、193映射、原coverage字节、截图和入口保持。四例复验仍用同一原选择，不新增测试框架或放宽判据。

## 原查询目录说明收紧（2026-10-06）

26c7b41 的新全量 `20261005T212053Z-9f4d3d32d9` 已在 F08 后安全停止：40/283 已运行，243 未运行，198 次请求全部结算；进程自然排空，无强制取消。V05 将12条车辆作业候选称为当前库存，V07 未读取导入 catalog 就错误说明模板按采购单变列。原件保留，两项记失败；车辆回答实际收到完整 scope/notice/逐行销售阻断，不能归因于数据被裁剪。

本次只允许 `app/vehicle_operations_api.py` 的 GET `/vehicles` 与 `app/vehicle_imports_api.py` 的 GET `/catalog` 两个路由 `summary`：把工具目录中的笼统 `vehicles/catalog` 改成精确查询范围及返回字段说明。车辆候选不等于当前库存或可办性；导入列按 kind 固定，字段/单位读原 csv_headers/csv_field_notes，行内容才绑定具体采购原单。共享 gateway 原本已读取 route.summary，无需添加新提示词分支。保持原候选集合、返回内容、权限、参数及业务守卫；不修改全局 prompt、历史场景或评分。说明调整的效果须由新真实输入验证，不预记为已解决模型误读。

外部只调整既有有限代表选择为 V01/V05/V07/V08，保留原283和101定义；同源完整结果不能继承前述失败。原280元累计上限和七条未知占用继续保留。

## 20代表后的原字段接线与语义纠正

2026-10-06当前：62a739e5/source920104e0的新20代表 `20261005T202422Z-98724cc4ff` 已自然排空，CLI0/450.172秒、原结构20/20及focus4/4，但语义仍有C03实际办理人、B04正向积分、HELP125审批岗位、HELP158统计范围错误；010开头与正文矛盾、059额外不同人限制也须纠正，不能放行。59次POST全部结算2.848083元；累计2753次，已结算107.438133元加七条旧未知66.322432元，保守占用173.760565元，280元/6000次上限不变。**撤回此前B04“符合当前合同”结论及兼容判据**：原Points不接受values.points，adjust实际为扣减；旧完整283语义应为263可接受、20失败。全部旧报告与评分保留并追加纠正。仅M8.5 in_progress，M8.6未开始。

本次允许范围限定为观察到的原因：

- `app/membership_api.py` 把原9种purpose的schema和原exchange/target_rule_id交叉校验提取为同文件纯共享入口，原HTTP创建调用它，保持原验证结果及业务提交行为；`app/business_assistant_gateway.py` 在原inspect中暴露该固定purpose schema及原正向grant/负向adjust事实说明，并在原纯验证阶段复用原校验；`app/business_assistant_forms.py` 仅按body.purpose使用同一schema描述values。缺客户/原因的临时probe仍须通过内部原schema，points未知字段不得绕过，缺字段不能猜填；不扩大其它领域、不改变权限/确认/积分正负规则。
- `app/flow_api.py::task_info` 从原已授权Task返回真实done_by、done_by_name及done_at；`app/business_assistant_case_tools.py` 的既有事实说明引用这些原记录。已取消任务不说成业务完成，缺真实办理人时保留未知，不能从assignee推断或猜事件关系；原授权查询、状态、排序与字段保留。
- 仅在 `docs/workflow-source/business.json`、`services.json` 及实际包含HK158的既有源文件中，按原API拆清此前混合岗位的对应动作，澄清实际履约条件、礼品批准人与申请人/确认人边界及当前待收款原定义；不增新业务或改111/193范围、不叠加通用prompt。先核原工具真实收到的字段与裁剪，只有存在实际缺口才修。三份生成物沿原发布生成器同步。
- 外部V撤回B04兼容shim，恢复原checks和评分，仅保留有限代表selector修复；冻结283/101提示、夹具及评分定义不动。复用原已登记定向节点验证原会员schema/缺资料probe与Task投影，不建新测试框架。登记指纹后先真实复验受影响原例，通过才从零全量；不把旧20或旧283拼成新指纹成绩。

root登记/集成；day_boundary负责会员原schema接线；mobile_closeout负责Task真实办理人投影和已观察帮助源歧义；regression_harness负责旧shim撤回候选、原节点定向与输入登记。全部正式验证执行期间冻结源码和V输入；旧费用不改、不释放未知。

## 完整283实测后的卡片与帮助说明修复

2026-10-06，`20261005T180742Z-a5f76d8a36` 在15135b2d/source3353d120上从零完成原283，101是其中重叠子集，未继承旧例；CLI1/6089.625秒，输入与依赖不变、自然排空。877次本轮尝试均结算40.255395元，无新增未知；累计2694次保守占用170.912482元，七条旧未知66.322432元原样保留。结构失败B04/D05与逐案语义失败分别记录，不能因无业务写入就把错误岗位说明记为正确。完整原件、旧失败与原评分保留；终局独立语义审计写入现有检查点报告。

本次只修已经观察到的原因，允许范围如下：

- `app/business_assistant_service.py::resolve_preparation`：缺必需关系时probe分支复制了模型request_id，而普通分支才清理；原Runtime随后按generate_request_id合同拒绝，D05没有生成卡。把已有清理移到两分支共同出口，仍不将临时品牌probe写入原草稿；服务器生成真实UUID、原权限/版本/幂等和人工确认不变。原完整工具输入与确定代码路径支持此定位，原报告没有捕到409最初异常帧，不伪造动态栈证据。
- `app/business_assistant_guides.py::find_workflows`：在原成功notice澄清入口岗位不代表每步办理/审批岗，按steps.actor/action/expected与exceptions解释分工；整体prerequisites不自动成为某一步前提；同指南的其它事项不变成本次必办分支。包括项不改成唯一范围。保留现有原单、版本、父单和原API权限合同，不硬编码案例ID、角色规则，不对回答加正则或后处理。
- `app/business_assistant_case_tools.py::_guidance`：C03把任务assignee当实际历史办理人。只补事实含义：任务被分派人与真实事件办理人分开，实际历史动作引用对应事件，不猜关联或补造执行人；原DTO、查询与业务状态不变。
- `docs/workflow-source/business.json`、`docs/workflow-source/services.json`：只在本轮V08及HELP004/010/037/058/059/077/082/087/089/092/098/120/121/123/125/158对应既有指引存在歧义处，依据原API澄清单批种类、试算回滚再复核、办理步骤/角色/资料与范围。已有清楚的分支不重复扩写；不改变111工作流、193需求映射、入口、业务守卫或岗位。仅用原发布生成器同步 `web/workflow-guides.json`、`web/workflow-handbook.html`、`docs/全量工作流手册.html`，保留原覆盖映射。
- 外部V原 `tests/m82-closeout/runtime-boundaries/test_runtime_provider_budget.py`（镜像节点 `tests/m82_runtime_boundaries/test_runtime_provider_budget.py::test_actual_provider_usage_is_durable_and_unknown_attempt_is_not_free[complete]`）：复用原节点追加一次D05原HTTP建Run→真实Worker.tick→准备待补品牌卡，核probe不落库、服务端UUID、同Work幂等同卡及467业务图不变；不增加测试平台或节点。保留该节点原费用、畸形输入及SQLite配对断言。
- 外部V原M8.5适配与原登记文件：B04原提示明确要求“帮我准备”，实际卡保留缺会员/原因并提供真实候选，符合R4既有缺资料卡合同。冻结283/101定义、原no_proposals观察与原结构分数保持；仅追加B04当前合同独立判据（0卡或至多1张pending积分调整卡，100为严格整数且来自原提示，会员/原因未猜填、真实授权候选、必答问题、无确认及业务图不变），其它原检查全部保持，不把旧失败抹成原分数通过。原representative有限选择表补入此次已观察失败ID和B04，argparse从同一固定表派生避免双表遗漏；本轮按原顺序只执行这些受影响案例。

先完成代码与适配审阅、原F定向，再登记新源码/输入指纹与live gate，执行受影响原例的真实定向；这些通过后重新从零执行原283并单列101。不得混拼旧结果、修改历史费用、自动重试未知请求或因本轮结束降低语义门槛。M8.5保持in_progress。

前置修复的证据亦保留：原F `173741Z-bcf87278aa` 的DELETE/WAL实际GET配对分别阻塞心跳33.25秒/正常0.032秒，证明锁条件差异，未复现旧自然timer取消，不能追认其唯一根因。原四代表 `175949Z-2693969fb6` 完整22POST/CLI0，S07/V07/V08/R02当次通过；本次全量V08的新说明错误仍有效。`175415Z-38fb5bdf3c` 是argparse选择遗漏导致的0模型调用启动失败，已有限修复并保留原件。

## 原生目录读取取消与导入说明

本轮R02还在工位真实为空时建议改为现场来访绕过，并承诺只补车牌/时间即可成卡。原 `AppointmentSave(Slot)` 及 `appointment_create` 对预约、现场来访都要求真实resource_id，这是一项流程说明错误，未发生错误卡或业务写入。允许 `app/service_intake_service.py::catalog` 仅附原必需条件说明：两种模式均需真实客户车辆、启用工位和完整时段；没有工位时等待有维护权限岗位配置，不通过切模式绕过。原/resources数组结构、查询、角色、Slot及动作守卫保持。有限代表再补原R02（22变23），本轮定向四项按原顺序S07/V07/V08/R02，不改原场景或评分。

2026-10-06，3d0f34d5/source59d2a474的新全量165227Z-80ca31882e在R05边界停止，21/283完整、262未运行，95 POST全结算，CLI1/640.313秒自然排空。S04这次真实列两候选、请员工选择、0卡，消歧通过。S07第三次表单发现里的原生目录读取被取消，最终failed/precondition_conflict、0卡却提示补原卡资料；不是正常等待。原安全观察只捕到被取消子任务，未捕到心跳的最初失败，不能凭CancelledError断言根因。它在53.185秒停止，非原600秒预算耗尽。累计1795次保守占用129.730620元，原七条未知66.322432元保留，无新增未知。

只读核对发现本轮外置合成test.sqlite及baseline.sqlite均为DELETE日志模式，原fixture仅调用migrate；产品 `app.cli.initialize` 和本地预览初始化使用WAL。这是实际环境差异，尚非已证取消原因。允许复用原外部预算/读取节点，使用真实原生GET与原heartbeat的有限并发配对定位DELETE/WAL差异，保留原20/30/90/600秒、租约及身份守卫；必要时仅在现安全观察器记录heartbeat最初异常类别/状态/已登记源码帧，不记录正文或locals。若配对证实为fixture初始化偏差，仅在当前M8.5薄适配中对新外部合成库按产品初始化设置并核实WAL，不改冻结283/101定义、历史夹具、业务数据或生产数据库设置；每例恢复后核实真实模式，记录配置变量。禁止凭时间形状修改生产取消规则、扩大超时或自动重试。另允许 `app/assistant_runtime_runner.py::_outcome_text` 仅把通用needs_input说明中的“原卡所列资料”改为“本次办理所需资料”，使零卡时不指向不存在的卡片；原因分类、真实计数、状态和重试规则不变。

V07以“必需字段”回答导入列却遗漏发运/预计/到货日期；实际已查询的vehicle-imports/catalog没有固定CSV列。允许 `app/vehicle_imports_api.py::catalog` 复用已有真实 `HEADERS` 返回固定列与存储金额/日期单位说明，不改解析、字段、角色或确认。V08虽已收到采购指引的验收入库说明，仍称到货“不增加库存”；原批量导入指引末步仅说生成对应动作。允许仅在 `docs/workflow-source/business.json` 的既有批量导入末步说明三种确认的真实效果：请款不等于付款、发运不等于入库、到货按VIN/库位实际验收入库且不自动付款；按原生成器同步三份生成物。全局prompt和111/193业务范围不扩展，真实模型效果须新定向复验，不能把错误全归为工具漏说明。允许原representative选择目录补入已观察失败的V07（原21变22），本次只选择S07/V07/V08三项原case；原定义/提示/顺序/评分与283和101集合均不变，不重跑其余无关代表。

## 候选选择与原单动作条件

2026-10-06，13ac2bae/source ba4c965d 的90秒私有配置full163025Z-b2317976ba在S07边界安全停止，7/283完整、276未执行，31 POST全HTTP200且结算，CLI1/324.297秒自然排空。S04面对两个同名客户，在员工未选定也未要求全部办理时给两张原单分别准备了分派卡，是实际对象/意图错误；业务467表未变、无确认。其余六例语义可接受。累计1700次保守占用125.830690元，原七条未知66.322432元保留，无新增未知。

现有全局prompt已经明确禁止给每个同名候选制卡，Runtime每轮仍完整携带，不能归因为丢提示或缺规则。实际find_cases的局部next只强调不要选第一条；后续两个get_case均给出“现在就能办”的动作提示，可能促使模型混淆动作条件与本次对象选择。这是工具轨迹支持的局部诱因推断，模型内部原因未知。允许仅修改 `app/business_assistant_case_tools.py` 两处已有说明：多候选须依据员工明确选择/明确全部办理范围；可办动作只说明原单条件，不证明员工选定或要求办理。原筛选、列表、字段、动作启用判断、批量范围、权限和确认逻辑全部保留，不增加语义正则、候选状态机或猜测员工选择。

root及独立审阅完成后以新源码从零执行原283，S04在同一全量中优先复核，不继承163025结果。仅解除这次已知semantic_review_stop，保留1700条费用与全部旧停止记录；原总限280元/6000次、未知费用停止、24轮/600秒不改。该说明修正不等于服务端已能判定自然语言指代，结果以新真实工具链和逐案语义为准。

## 网络中断的可观察性与同指纹显式续跑

2026-10-05，697dce01/source9fb9c72c 的语法纠正经原provider及Runtime预算两节点通过（150627Z-67dea718df），strict151742后真实full151830Z-c7cc268e31执行13/283、62 POST、557.359秒、CLI1。S01—S08及V01—V04语义可接受；V05未取得完整结果，余270项未运行。第1669次实际发送未取得HTTP状态，原内部重试在再次发送前被费用守卫拒绝；现有证据不能把首次异常断言为某个具体网络异常或JSON错误。旧六条未知46.268416元保留，新1669保留20.054016元，累计保守占用123.748635元；总限280元/6000次不变。

允许仅在V的`harness/live_gate.py`实际HTTP send边界记录首次异常的安全类型/已登记源码位置，原异常继续抛出，保留既有终局诊断；禁止正文、locals、请求内容、推理或凭据。将本地Pro high验证私有配置的单请求超时45秒改为产品已经支持的90秒，并显式记录这一配置变化；生产默认、24轮/600秒、原重试规则及未知费用停止保持。它是对照条件变化，旧45秒局部成绩不拼入新90秒完整结果。

允许在原`V/run_validation.py`与`m85_runtime_live.py`中增加显式的全量续跑参数，绑定指定旧run及报告SHA，只用于当前M8.5 full。必须核旧进程自然排空、输入未改、同五指纹、同原283/101完整清单与模型配置，逐案校验原件并保留出处。失败与未完成case用全新合成夹具/新Run重做，不重放不明业务，不自动解除费用停止；已通过片段保留原run/时间/配置，合并报告明确为分段复验而非单次全量。源码、工具、提示词、场景、测试或执行器不同指纹即拒绝继承，语义审阅仍逐案执行，关键错误门槛不降低。新入口首次完整运行从零开始，不继承151830旧执行器结果。

root核对固定失败run/账本SHA与停机事实后，可一次明确把1669完整预留保留为未知占用，再恢复后续新Run；不释放费用、不重算历史、不自动恢复下一次未知。不新建测试平台或通用重试系统。M8.5仍为唯一in_progress。

## 完整回复的参数语法拒绝与一次纠正

2026-10-05，2a76e245/source a069c644 的4项离线定向与strict通过；真实V05/M03定向142008Z-e7e5267213完整33 POST、350.719秒，语义均通过（M03止于22轮，不冒称触发真实强制收尾）。同源全量142833Z-935eedbad6仅完成S01—S05、20 POST、165.39秒、CLI1，278项未运行。第1607次HTTP200完整回复在工具arguments的JSON解析处失败，原保护正确保留0卡、业务表不变；本轮不能记全量通过。1607预留20.054016元与旧五次未知全部保留，累计保守占用100.939422元，总限280元不变。

允许 `app/assistant_runtime_provider.py` 将一种完整非流式拒绝单独分类：HTTP200、显式tool_calls结束、assistant消息、所有工具信封/索引/唯一ID/名称/长度/Unicode均完整，所有可解析参数仍通过原重复键、有限值及对象检查，仅剩JSON语法错误，并有一次请求的完整一致usage。专用异常只含固定说明和安全计数，不携带回复、参数、推理或凭据；不修改、补全或执行坏参数。缺失结束标志、截断、SSE、重复ID、非法名称、重复键、非有限值及未知费用仍按原协议失败处理。

允许 `app/assistant_runtime_runner.py` 在原Run中只追加固定系统纠正说明，不加入坏assistant/tool帧或推理，不checkpoint、不执行被拒片段；下一轮仍重验身份、时间与原24轮预算。与原输出截断共享一次重新表达额度，沿 `app/assistant_runtime_queue.py` 既有持久 `truncation_replanned` 标志，不新增预算状态或迁移；第二次语法错误、已用额度或收尾阶段均停止。原403/409/确认边界不变。外部 `V/harness/live_gate.py` 仅对这一精确异常且完整单请求usage结算后重新抛出，不自动重发、不结算一般异常，也不追溯释放旧未知费用。复用原provider和Runtime预算节点核对成功纠正、第二次停止、截断共用额度及混合非法片段硬拒绝，再回到真实全量。

官方普通工具协议明确参数可能不是合法JSON；严格模式须Beta端点及受限schema，当前动态业务工具不为此换端点或改架构：[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)。M8.5仍为唯一in_progress；原283/101及M8.6门槛保持。

## Pro代表结果与收尾、候选事实修复

2026-10-05，c93b7ee/source e604280f 的 Pro high 代表 `20261005T124118Z-875bdaf3ad` 自然排空：21条原件、152次真实POST、1201.766秒、CLI1；20条结构完成，M03达到24轮上限，V05另有语义失败。所有业务467表保持、无确认请求。152次均结算，无新增未知，累计1554次保守占用78.912116元；此前五条未知26.214400元保持，280元上限不变。较早Flash的数量/日期/报表问题本轮未复现，不据此宣称完整283或默认Flash通过。

V05把12条车辆作业候选称为均可作业，并建议选择包含已交付/销售占用车辆的范围；全局scope虽已明确未核验可作业性，单行缺少对应真实阻断事实。允许仅在 `app/vehicle_operations_service.py` 抽取原 `_free` 已有销售占用/交付查询，在 `app/vehicle_operations_api.py::vehicles` 复用为只读逐行事实，并明确原库位条件；保留原候选集合、门店权限、未知状态及原确认守卫。不得调用 `_free`/`register_custody` 制造读中写，不返回销售金额或跨店标识，不宣称部分检查已覆盖所有可办条件。

M03的父原单404和客户查询403均已进入当前完整工具链，模型仍换入口查询。没有证据表明本地截断丢失拒绝事实。现有 `assistant_runtime_runner.py` 最后两轮已明确要求收尾，但 `assistant_runtime_provider.py` 仍发送 `tool_choice=auto`；允许将这个既有收尾阶段接到服务端工具开关，发送 `tool_choice=none`，按已有事实生成等待说明。普通轮及旧调用默认保持，24轮/600秒不增。流式与非流式均须先完成原完整性校验；若供应商仍返回工具则以协议错误拒绝，保留实际usage，绝不执行或把拒绝变成功。真实收尾表述仍须独立审阅，不能仅因Run结束记业务成功。官方协议依据：[DeepSeek Chat Completions](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)。

仅复用V已登记provider/Runtime预算和车辆读取相关节点，保存原件及精确断言变化；不新建测试平台、不扩大收尾重试、不降低权限。新来源绑定和strict完成后，定向真实复验V05/M03；其他19条本轮证据保留为该旧指纹结果，不拼接成新全量。原283/101及M8.6门槛保持，M8.5仍为唯一in_progress。

## Flash高强度终局与Pro有限对照

2026-10-05，9cb6868/source d6d0b51b的21代表112644Z-4e1e1431f7实际815.593秒、145POST、CLI1，21条原件均留存但未通过。M02仍混淆80升原到货与68升当前库存；V08把原请款清单错误作为请款导入自身前置；A07未读取已有消费积分目标表。V03在第9轮原单检索时中断，先前错误实体URL的422已经反馈且又继续四轮，不能据此误改正常的422处理。D04第1402次再次因完整响应内工具参数JSON无法解析而被正确拒绝，非超时。只读、无卡与结构完成都不消除这些失败。

同一Flash在普通、thinking-low及thinking-high中仍有关键事实错误，继续堆叠提示词不构成充分修复。下一步允许沿用户本地API/余额授权，在相同官方端点、原21场景/283/101定义和工具下，明确选择现有配置可用的`deepseek-v4-pro`、thinking-high做有限对照；不静默fallback，不把其结果当Flash通过。此轮不修改生产默认模型、UI默认或历史消息。若选择最终交付模式，须依据实测另记默认入口与兼容边界。

外部最小范围为`V/harness/live_gate.py`、现M8.5适配器的模型断言，以及必要gate/manifest/restoration指纹登记。当前授权模型固定Pro，历史费率仅识别Flash与Pro两个明确值。官方高峰上界为Pro输入9元/百万token、输出27元/百万token；1,048,576输入和393,216输出的每请求保守预留为20.054016元，缓存命中仍先按未命中计。旧Flash1402行逐行保留，旧未知与第1402次5.242880元预留不能按Pro重算、释放或重置；新请求显式登记模型及对应预留，总额仍280元、总次数仍6000。逐行费用取该行明确模型的固定费率和预留，禁止任意模型、任意费率或任意URL。来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/ 。

原V03异常先在既有外部Runtime读取测试中用合成响应复现，走原员工/Run/GET及结果持久化，必要时只记录整数状态、异常类和已登记源码位置；禁止为猜测原因改守卫。模型的原始推理和凭据仍只在当前内存。原1402次累计占用73.044270元、剩余上界206.955730元，失败和保留记录全部保留。待离线复现、费用边界和输入审阅后，由root一次明确确认第1402次保留未知并恢复；后续不确定请求仍自动停止。

**Pro开始前的费用口径细化**：上述全未命中计价在同轨144次已知usage上约为27.501354元，不能视作Pro实测费用。现有provider实际返回缓存分项，例如原M02的118141输入=103424命中+14717未命中；官方峰值Pro缓存命中价为0.30元/百万。仅未来Pro请求允许在两个分项均为非bool非负整数且合计严格等于prompt_tokens时，按0.30×命中+9×未命中+27×输出计费并向上取六位小数；缺失或矛盾一律按全部输入未命中。新记录保存明确计费规则与已核分项，不能猜缓存、扣减未知费用或重算任何旧行。每次最坏预留仍20.054016元，280元/6000次、未知停止及高峰上界不变；此精确化不改变生产provider或业务测试路径。

## 21代表模式对照与DeepSeek推理强度

2026-10-05，3a28f35/sourcef6331e8d同一代码、原21场景及合成夹具分别执行普通模式104141Z-b7f74b72e4与thinking-low模式105531Z-8a7f7e8080。普通模式106次POST已结算，结构CLI0但A03/A06/M02/M04仍有实际口径或来源错误；思考模式纠正了这些路径，仍出现V03采购来源外推及V05把12个作业候选当在库。两次结果独立审阅，不拼成通过。后者134次POST、CLI1/528.562秒，D04最后一次HTTP200包含无法解析的工具参数JSON，原provider按完整性合同拒绝；安全异常链为ModelProtocolError/JSONDecodeError，不是请求超时。无业务确认写入，原始推理不保存。

下一步仅允许在 `app/assistant_runtime_provider.py::provider_request` 将DeepSeek的既有thinking推理强度由low改high，MiMo、非思考模式、工具与业务合同保持；沿原外部provider节点核对请求体及畸形JSON仍拒绝，再以原21代表独立复验。暂不改变UI、HTTP输入或后台的thinking默认值，不把显式开启的评测误称默认模式已通过。此处依官方思考模式合同选择high，不新增重试、截断修补、自由端点或另一套推理配置。

累计1257次、保守占用61.557766元，包含原三次未知及第1257次完整5.242880元预留；280元、6000次上限保持。root核对失败run、账本SHA和离线检查后，允许仅对这次已结束且未执行工具的失败追加明确恢复记录，将1257的完整预留保留为永久未知占用，再解除本次停止用于全新Run；仅更改1257的保留状态，不结算、不释放金额、不改前1256条历史行，不自动恢复未来失败或重放旧Run。所有正式输入仍须重绑和新strict后运行。

## 094910 全量失败后的事实边界修复

2026-10-05，1b9b735/source6b03e5d4 的原283全量 `20261005T094910Z-a940bd86a3` 在75例后因已核实错误由root持原费用锁于场景边界停止，CLI1、721.078秒，208例未运行。287次实际POST已结算，累计1017次记录全部保留；本轮不是完整通过，不能继承此前14代表成绩。独立审阅确认S07无来源车型选项与猜填版本、M03物资计量单位错误、F02/A03金额计算错误、A06把售前活动当已完成回访；root另核B01漏查仍有效的旧会员账。全部原始结果、失败和三次未知费用保留在V。

后续仍只有M8.5执行。允许在原 `business_assistant_forms.py` 完善内部版本缺项守卫，在原准备边界复核与原schema/原查询对应的候选；未知对象应等待，不猜ID或版本、不默选第一项。允许在 `flow_api.py` 的原授权物资详情投影补实际物资单位，在原会员lookup/master查询按已展示的本店客户姓名查找会员；保留原岗位、门店、分页、版本及确认边界，不改现金/库存/会员流水。不以名称猜物资单位，不把新集团会员为空外推成旧会员账不存在。必要定向验证继续复用V的现有登记节点。

模型收到正确数值后仍出现计算及流程理解错误，应与产品缺口分别处理。允许在现有Runtime适配上按明确模式新增有限对照：同一DeepSeek Flash及原场景、合成夹具、原工具、24轮/600秒，启用产品已经支持的thinking布尔参数；单独记录模式和结果，不混为旧非思考成绩，不静默替换模型或放宽验收。先审阅代表结果再决定本次交付使用模式；累计280元、6000次、每请求预留、未知停止及端点隔离保持。原始推理仅在工具链内存，不入报告、日志或数据库。

**2026-10-05当前预算授权**：代表092736Z-6ab857a52a已结构/语义14项全通过。业主明确“余额你放心使用，一共还有280多”，本轮据此采用累计280元上限，包含此前占用38.342414元，不另加280。允许仅把外部 `harness/live_gate.py` 的LIMIT及固定gate预算校验两处50改280，更新public gate预算/当前已审文档绑定/执行器SHA和manifest gateSHA。730条原账本整字节保留，三次未知15.728640不释放；6000次、每POST预留5.242880、实际结算、到期、未知停止、网络与隔离守卫均保持。旧50元记录保留为历史，不再等待增额答复。预算及文档变化做新strict后进入原283完整复验，不因它们重复无变化的14代表或日期节点。详M8-5-local-live-review-v1。

2026-10-05业主明确要求使用本地环境及已提供API复验。现有V统一入口尚未实现live gate，原283脚本也仍调用历史run_tools，因此不能直接把旧脚本成绩算作当前Runtime结果。

仅允许在V原run_validation.py、harness/isolation.py、runtime_guard.py、必要的有限live_gate.py与当前Runtime薄适配中增加M8.5/M8.6专用授权入口；普通离线命令、原网络禁用、数据库隔离和来源校验保持。真实联网固定DeepSeek官方HTTPS端点/api.deepseek.com:443、deepseek-flash；DNS与连接只放行该明确目标，禁止任意URL、代理、redirect或模型控制网络目标。新脚本和原283/101定义通过来源登记，数据全为当前源码的外部新合成库。

沿既有共享上限CNY50、6000次实际HTTP尝试，两项共用耐久账本；每个POST及重试前预留预算并落盘，成功且usage完整后按锁定高峰费率保守结算，不确定结果保留预留并停止，不盲目重发。官方2026-10-05价格核对：deepseek-flash输入缓存未命中2元/百万token，输出8元/百万token；按文档1M上下文、384K输出的保守二进制上界每请求预留5.24288元。缓存命中仍按未命中计，报告为保守费用上界。来源：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/ 。不通过缩减生产轮数/超时/输出能力偷换被测行为。

密钥只从业主提供本地文件读入受控内存/私有本次配置，不在命令行、日志、报告、Git或源码包出现；原始推理不展示、不持久化。普通测试不得通过fake_config注册真实key绕过gate。先冻结维护后的源码/工具/场景指纹并运行有限代表路径，观察真实问题再修；283只跑一次并单列其101子集，历史成绩不覆盖。多轮及独立保留集按实施计划分别留真实事实，不将API可达当业务通过。

## 首次真实失败后的有限诊断

2026-10-05：strict `20261005T035234Z-25952b01d5` 18项通过，代表run `20261005T035315Z-95d79a755f` 同五输入实际失败。S01只有1次真实POST，原provider记录11029输入/113输出/11142总token，工具数0；没有卡片或业务表变化。worker实际使用非流式请求，不能归因为SSE。S04及其余场景未调用；原费用账本已停止，保留5.242880元预留，不把这次调用记为成功或零成本。

允许仅给外部live_gate添加有限故障证据：HTTP整数状态、实际stream布尔值、original_call/settlement阶段、异常类及最多三层context的已登记源码相对位置。禁止异常正文、局部变量、HTTP正文、原始推理或密钥；原异常仍抛出，下一未知结果仍停止。先取到实际失败位置再判断生产修复，不凭猜测放宽响应完整性。

本次整体真实复验及原50元/6000尝试授权保持。root复核首轮失败后，可用显式一次性外部脚本核旧账本SHA/run/attempt、保存原件与恢复记录，将该不确定请求的完整5.242880元永久保留为预算占用，再解除本次停止用于全新合成Run诊断。它不是账单结算，不填settled费用、不释放预留、不重置累计次数，保守剩余额度44.757120元。禁止自动解除以后未知结果或重放原Run；新诊断须重新绑定当前输入和同五指纹strict。此项修正以继续用户已授权复验且不超过费用上限为目的，不增加费用额度或降低业务验收标准。

## 实测非流式工具索引兼容修复

新 strict `20261005T041644Z-f08b4308be` 通过，代表 Run `20261005T041711Z-cfb01c6aca` 再次失败。实际 HTTP 200、stream=false；两项工具均有 id/type/function/index，index 分别为 0、1，无其他额外字段。安全异常链定位到 `app/assistant_runtime_provider.py::_complete_tools` 的精确键集合判断。该结果确认供应商非流式响应携带工具位置索引，与 SSE 无关。

允许仅修改该 provider 的非流式规范化和必要注释，复用原外部 provider 定向测试补充这个已观察到的边界。索引可省略；出现时必须为非 bool 的整数、在现有工具上限内并等于实际数组位置。完成原 ID 去重、函数结构、参数 JSON 和容量校验后，返回内部 id/type/function 三字段结构。未知键、无效索引、重复 ID、不完整参数等继续拒绝；不改业务守卫、工具 schema、提示词或 SSE 行为。按原 V 入口先离线定向检查，再同输入 strict 和真实代表路径。

第二次实际 POST 也保留原失败及完整 5.242880 元预留；两次共 10.485760 元永久预算占用，不代表实际账单。root 根据已查明的生产原因，在修复及定向检查后可显式核第二次失败的固定账本 SHA/run/attempt，保存恢复证据，仅解除这次 halt；剩余保守预算 39.514240 元、累计尝试 2 次不变。仍不允许自动恢复后续未知结果、重放旧 Run 或重置额度。

## 完整队列首次实测后的修复范围

provider修复855a1b9经6个原离线节点通过后，代表Run `20261005T044022Z-d2f5367fc7` 完成5例、20次真实POST、78.515秒，结构和独立业务语义核对均通过。完整Run `20261005T044407Z-aab598b6e1` 随后暴露不同问题，不能继承代表成功：S08第三轮回复后未产生任何确认卡，部分客户原GET返回数据库身份来源不一致，S07将车系/未分类车型归属作了无依据推断。root在case间持原账本锁明确停止，28例已完成、255未运行、153次真实POST全部结算、进程正常排空；未修改已有case原件，未确认写入业务。

客户GET的已证原因是原 `get_write_db` 为SQLite创建写事务 OptionEngine，同一个基础Engine被原身份对象等号误判为不同数据库。允许精确修复 `app/assistant_runtime_principal.py` 与必要的 `app/db.py` 接线及原外部身份边界定向测试：仅识别原服务端写事务包装并回到同一个基础Engine对象作身份读取；独立授权读取不能继承BEGIN IMMEDIATE。继续拒绝Connection、同URL但不同Engine、未知选项或不同绑定，不删守卫或以URL比较代替身份。原业务端点审计/模板初始化事务不改变。

S08原件不能区分首个registry校验与checkpoint内部拒绝，禁止据最终precondition_conflict猜测具体原因后泛化重试。允许仅给现外部Runtime适配器增加透明故障观察：分别包原registry.validate_calls与checkpoint，失败时记录阶段/异常类/HTTP整数状态/已登记源码相对位置和有限工具结构。工具名只记已注册名，参数只记已声明键的存在/类型与列表长度；禁止异常正文、参数值、未知键原文、回复、原始推理、密钥或locals。原函数照常委托、原异常继续抛，结束恢复；单列本例diagnostics，不改变原评分与业务。后续根据实证另记最小修复；车系归属语义问题另据原查询结果审阅。

S07进一步核对：原vehicle-catalog的items为空，brands与series是独立目录，unclassified仅有model_text和待人工确认来源；模型却将目录中的车系称为品牌并把未分类文字归入其中。允许仅补清 `app/vehicle_catalog_service.py::catalogue` 已有notice：区分品牌/车系目录与已确认车型关联，说明未分类车辆没有已确认品牌/车系/车型归属。原数据、筛选、权限、数量与配车状态不改，不用名称正则猜归属；按原S07/V02语义复验，不因说明变更预记修复有效。

修复后的代表入口沿原同一phase/命令扩为原序7例：S01、S04、S07、S08、V02、F08、D04，保留原5例并补此次分类事实问题；原283/101定义不改，旧5例报告不覆盖。新增两例仅用于已观察失败的定向复验，不能代替完整283。

28例语义审阅还确认M02仅查procurement/独立采购仓储接口为空，就断言本店无物资采购；同基线V03真实查询证明purchase类别仍有4条当前岗位可见原单。两类均为真实有效类别，不改查询合并或业务状态。允许 `app/business_assistant_case_tools.py` 给现find_cases结果补准确的类别/筛选范围说明及采购双类别读取提示，原items/计数/权限/分页保持；原M02加入上述代表队列（共8例）核实际完整查询和最终表述，不能只因提示存在记通过。

身份边界测试复用原M8.2的D文件及合成支持文件，保持来源唯一。现统一入口仅允许M0.2/B定向，而D文件只在M8.2镜像；为避免复制测试来源或重跑数小时完整套件，允许外部 `run_validation.py` 与 `harness/diagnostic.py` 的现有模式检查增加精确 `(M8.2, None)` 定向支持，沿原collector、registered command/node选择、同输入strict和diagnostic不通过里程碑判定。原M8.2完整路径、清单、普通离线网络禁用及其它模式保持。仅同步确实受此合法模式新增影响的原selftest断言，不改其它拒绝条件。D文件只在原两个测试函数内追加已观察身份边界，原节点/参数数量保持。

## 八代表复验后的业务目录说明修正

2026-10-05：当前402b664的strict052644Z-5899ec0070及原M8.2定向052721Z-7e77533df3实际通过14项身份边界和1项诊断合同；客户原GET为200，异库/异常reader仍拒绝。原本地平台锁仅缺schema/node，沿现打包器同字段补记实际Python/Node版本和哈希，43依赖与原锁一致，没有安装或替换运行时。新strict053759Z-32d2323b64及八代表053829Z-05dbff7d80同五输入，完整8例/43真实POST/119.172秒、结构通过；S01/S04/S08语义通过且真实三行批量完整、无确认业务写入。但S07仍把series称具体车型；M02只调用独立采购/仓储GET，未调用find_cases，故新增该工具notice未进入上下文，仍错误外推全店无采购。

允许仅修正 `app/business_assistant_prompt.py` 的既有业务目录说明：物资管理段遗漏仍有效的Flow purchase/procurement采购来源，整体采购入库查询须按当前身份核对适用来源及原单关系，未查全只能报告已查询范围；基础数据段明确vehicle-catalog的items/total是具体车型结果，brands/series为筛选目录，不以目录项或未分类文字虚构已确认车型或归属。保留所有原接口/数据/权限/分页/状态，不硬编码场景名称，不为模型答案补造业务，不加入自动重试。文案静审后直接按原八代表真实复验；这次提示词改变如实另记变量，不继承前轮语义结论或原283成绩。

## 已定位的批量参数拒绝反馈缺口

223a890的新strict054955Z-5ced37bc9e通过；八代表055027Z-ccedf77b29完整执行但CLI1，33次真实POST。S07正确区分车型目录层级，M02已真实查到原Flow四条采购并保留各来源；仍记录范围措辞及额外追问的体验观察。S08安全诊断首次明确为registry_validate_calls的422：business_tools.validate原model_validate拒绝prepare_business_batch一个额外顶层键，三行values/summary类型正常；整段没有checkpoint、没有卡、业务未变。未记录额外键名或原参数，不追认更早缺诊断那次失败。

允许仅在 `app/assistant_runtime_runner.py::run_once` 首次完整registry校验位置反馈这一类明确422格式拒绝：原严格schema继续拒绝，整个被拒片段不进入工具执行或持久化；用固定服务器格式说明及现工具schema让模型在原循环重新表达原请求。非法参数、回复、推理不入当前chain或数据库；反馈区分本片段未执行和之前已接受成果，不重做旧卡。固定纠正说明不重复累积；原持久轮数/时间/调用费用、每轮身份和暂停边界仍生效，不增重启后重置的纠错预算。仅捕获该位置的422，不泛捕checkpoint、权限401/403、版本409、租约、截断、未知结果或数据库错误。复用原外部runner节点验证拒绝后正确三行、无确认写入、其它错误仍停止及原预算计数，再按同八代表实测；不为此新增通用恢复框架或修改迁移。

同次S07只以available_only=true查询车型，却将空结果称作全店车型目录空。进一步仅在原prompt“读原单”段补明所有查询结论应保留实际筛选范围；可配车为空不证明全店车型为空。属于已观察范围外推的说明修正，不改服务端查询或新增模型答案字符串替换。

## 实际拒绝反馈与原单数值单位

8f9c1a2的原F定向062034Z-d6be4bf788通过；strict062957Z-dd43719ba0及八代表063029Z-b17f37c1b3同五指纹，实际53次POST、151.843秒、CLI1。S08在首次两个有效查询后连续22次registry422，均多一个顶层键，最终24轮预算停止、卡0；非法片段零执行成立，但固定反馈未能纠正真实模型。S07另把未委托的接待卡称为订车必需前置；M02四个采购来源虽已查齐，却把原quantity千分之一存储值直接展示，数量放大1000倍。八例业务467表前后均相同。累计304次尝试、保守占用19.698166元，余30.301834元；历史报告与未知占用保留。

允许修正上节仅固定说明且丢弃当前拒绝片段的实现选择：沿现legacy工具协议，把provider已完整验证的assistant/tool拒绝对仅放本次内存chain；各工具明确422、整段未执行，并携带原safe_text/scrub后的校验位置。原参数及推理不写检查点、消息、快照、事件、日志或报告，不调用handler；当前链不是业务成果。原循环身份、费用、轮数和checkpoint拒绝边界保持。复用原F节点，把错误的“内存中也不应存在拒绝对”断言改成真实协议及零持久化核对，保留三行纠正、连续拒绝预算、403/409/checkpoint422原断言。

允许在原助手业务提示词澄清直接办理目标与可选上游流程的区别：已有目标原表单可建客户关系时按该表单办理，不能把接待/意向虚构为必需前置或制造未发生接待。允许仅在 `app/flow_api.py::describe_case` 依据原Flow kind/flow_version的字段类型给原单读取补充金额/数量的准确单位说明，供原列表/详情及助手共同读取；仅对授权结果中真实存在的已声明字段给出展示值，原数据/API单位、权限、状态机和业务事实不改，不按任意字段名猜换算。修复后继续原代表及全量，不以说明存在或离线通过代替真实语义结果。

## 当前库存与期间查询范围

faa2d54的strict065142Z-debdbfff67及F定向065221Z-4f37ebd356通过；重新绑定后strict070319Z-6be9607fc7和八代表070402Z-c7d6b4bb06同五输入，完整8例/37POST/151.375秒、结构及关键语义通过。S08实际经历一次registry422后纠正为三张准确待确认卡；M02数量80/24/4/10准确，S07无额外前置卡。S07英文开场和重复询问已知选项仍记体验观察，不借关键检查通过抹去。

同源全量070940Z-c904408cfc在34/283后由root持原账本锁于case边界停止，249未运行、169真实POST均已结算、374.813秒自然排空，全部34例467业务表前后相同。V01将期间报表12条历史核对行误作当前在库12台/可配10台，原目录实际11台/9台；F02将默认近30天（9/6–10/5）称为本月，未按自然月查询。结构通过不覆盖这些错误。累计510次尝试，保守占用25.940190元，余24.059810元；原50元上限保持，扩大额度须业主答复。

允许仅在 `app/vehicle_catalog_service.py::catalogue` 给既有完整未分类车辆集合补可配台数及精确筛选/独立分页说明，在 `app/vehicle_period_analytics.py::build_vehicle_period` 附加范围元数据，明确历史代次行不是当前库存、原期末指标及未知值不能由行数替代。原车辆集合、权限、分类、指标定义、表格/图表/导出和算法保持。原prompt仓库目录同步当前库存与期间库存读取合同，列实际已有报表kind与参数范围，避免猜路径类别。按实际代码核对看板end/days范围后，仅补原日期查询说明，不改看板默认30天或把旧报表重新定义成自然月。原V01/F02加入同phase代表复验，保留原八例和原283/101定义，先核已观察问题再全量。

本次root明确停止属于已知语义失败，并非未知付费结果。修复及必要检查完成后，可核对固定run/账本SHA和510条费用行，保留这次停止原件，仅解除该次intentional halt并重新绑定当前输入。不得释放最初两次未知占用、重置费用/次数、自动解除后续未知结果或重放旧Run。

日期来源核实：旧service显式提供服务器today，Runtime `assistant_runtime_context.py::build_context` 尚无对应字段。允许在该函数复用原本用于摘要的一次可信clock取样，经原UTC规范化和实际settings.timezone换算，向本轮context补business_date/timezone。每轮重算并计入原上下文预算，不从用户输入推定今天、不写入历史摘要、不新增数据库读取或更改权限/时间预算。日期查询说明与实际dashboard的end/days及返回start_date/end_date同步；按F02真实输入核对自然月范围。

34例的继续语义核对确认：S06把本人岗位actions及按ID展示的任务误作跨岗位流程顺序；M03当前inventory不能读取该v2父维修/客户，等待补充原单线索合理，不改权限。M04只查warehouse耗材退回来源便扩大为系统没有维修领料来源，且无来源猜测流水ID；V05把整车作业辅助列表的12行称当前在库且可补齐移库，实际包含销售占用/已交付车且全部unlocated；F01未查Flow当前待收款表，误称全店无客户应收。已记录Case5按原收款/净应收定义仍有128800元待收、尚未到期，不能另称逾期。

允许仅补原prompt的工单/物资/财务目录说明，指导按真实原单族和已发布工作流核对；任务列表不表示依赖顺序，原权限拒绝和查询空结果不扩大为全店无业务。财务用既有flow/analytics的receivables及原来源，保留当前快照与期间统计的区别，不新增计算规则。允许 `app/vehicle_operations_api.py::vehicles` 只附原列表范围/位置要求说明，不改车辆集合、守卫、计数、分页或调用有写副作用的_free。未选对象、原单不足或真实位置不满足时等待，不能猜ID或承诺补齐即可办理。

代表入口同phase扩为原顺序14项：S01/S04/S06/S07/S08/V01/V02/V05/M02/M04/F01/F02/F08/D04；这是原8项及6个已观察失败的定向复验，原283/101及评分保持。复用原F的trusted_context节点核业务日期来自实际服务器时区、纳入完整上下文且不进入历史摘要；不重复无改动的格式纠正节点、不新增测试框架。全部修复后重新冻结输入，必要检查与真实语义复验分开记录。

## 混合应收承担方与旧原单的帮助适用范围

17a1565/source178edad8经strict075103Z-dfc6a91186及原trusted_context定向075146Z-c2bb1b4202通过（collector458.109秒/目标25.032秒）。本次主动暂停显式核原件后解除，50元/6000次及510条账本保留；新strict080221Z-bada609f26通过。代表080317Z-847a1c99fa执行12/14后CLI1、215.203秒：V01真实11台/9可配、V05正确等待位置、S06不再编排出库先于检查、S08准确三张独立卡；F01已查原8笔总待收298000元，却把其中原保险公司承担500元误归客户。M04查原领料并等待正确，但仍按当前发布指引向旧v2原单承诺本人可办理退料及接收库位，未核该版本/本人权限。

F02没有原业务GET结果，不能判日期修复有效或失败；实际预算attempt558首次发送未留下HTTP状态/usage，原重试被live gate拒绝，最后安全异常链只保留该拒绝，不能区分第一次timeout/transport。48次尝试中47已结算、1保留完整5.242880元，F08/D04未运行。累计558条，保守占用32.719784元、余17.280216元，原件不改。不是新增格式错误或放宽预算的依据，不自动重发旧Run。

允许 `app/flow_analytics.py::build_analytics` 仅在原receivables行metadata增加真实承担方：详细维修复用原receivable_rows的payer_type/payer_name；原非详细Flow维修使用原payer声明枚举，缺失/未知明确unknown，其它同分支客户结算族仅依原business_finance_sources合同标识。原表头、行values、金额、合计、期间/快照定义、SQL与权限均不改变；其它无承担方metadata的来源不能推定为客户。prompt财务说明混合总待收与客户承担的区别，未知先核原授权详情，不能把原总额当筛后客户合计。本轮不扩建新的报表或答案字符串改写器。

M04的具体原因还有帮助结果的适用范围未明：`business_assistant_guides.py::find_workflows` 返回当前发布指引及按岗位计算的entry.can_enter，并未读取原单或评估旧flow_version。允许仅在该成功响应加固定notice，说明入口岗位匹配不证明旧单可办，办理须回原get_case动作/字段/拒绝原因，父单须按本人权限读取，拒绝等待有权岗位。原指引、检索、入口权限和原API守卫均不改变，不自动读父单或新增业务状态机。

558的首次未知费用仍保留完整预留，不释放或冒充结算；本轮网络异常不能用修改业务守卫解决。root审阅其固定run/attempt/账本及停机事实后，可显式留存原件，将该唯一reserved标记为uncertain_occupied并记一次人工审阅恢复，以新Run继续既有本地复验。原累计558次和50元上限保持，旧两次未知占用及历史停止记录均保留；下一未知仍停止，不自动循环恢复。新查询范围/帮助元数据只作静态差异审阅及原14真实路径复验，不因这些变化重复已通过且源码未变的日期定向节点。

## 实际检索投影与Flow报表期间

51ffd82/sourcef5c06ad2的新strict082615Z-03f3cb1343通过，14代表082653Z-47037c4c27完整14/64次尝试/171.109秒、CLI0，新增未知0，所有业务表不变；结构通过仍非语义通过。F01已准确区分7笔客户承担297500元和1笔保险公司承担500元。F02真实GET转用了flow/analytics，tables=cash未带日期仍返回默认9/6–10/5，答案错误称本月；先前dashboard参数说明不能代替该报表合同。M04本次未调用find_workflows/get_case，帮助notice未进入上下文，仅find_cases就保证拿到单号后本人立即准备退料，原候选投影又丢弃原API已给的flow_version/version/parent_id；前轮帮助范围修复不能算本例已有效。

允许 `app/business_assistant_case_tools.py` 的find_cases投影仅保留原API已有的flow_version/version/parent_id，并在原notice说明候选只证明可检索，未核可办动作及父单权限；选定后用本人原get_case核对，不能凭编号保证准备。不新增父单读取、权限、状态机或按案例号分支。允许 `app/flow_analytics.py::build_analytics` 仅附加scope元数据，说明实参起止日期是否省略、实际期间、默认起点取结束日前29日，以及期间cash与当前快照不同；原默认值、计算、冻结报表与权限保持。原prompt同步此接口的date_from/date_to及自然月参数，不能自动猜用户目标或改业务日期。仍按原14真实路径验证，不重复无变化的日期单元或扩执行框架。

## 原生日期查询的持久意图

e401338/sourcecfe83f99经strict084950Z-cce46bc60b通过，14代表085020Z-493f3c1983完整执行53次POST、165.281秒、CLI1，全部HTTP200并结算，新增未知0。独立语义13例通过；M04当前正确消歧等待，不把未选原单前没有get_case判失败，也未验证旧单后续权限。F02本次已生成cash及2026-10-01至2026-10-05准确参数，但model checkpoint成功后read仍running、Work为0、原GET为0，最后runtime_unavailable。原日志为空，不能把推断异常类写成实测证据。全部14例467业务表不变；累计675次、保守占用36.573856元（含三次未知15.728640）、余13.426144元，50元上限仍保持。

源码核对显示原gateway._parameters把日期按原API类型校验为date，runner._read_intent直接深复制该值给WorkItem.validated_intent JSON列，尚未转回可持久JSON。允许仅修改 `app/assistant_runtime_runner.py::_read_intent` 的原生日期序列化及说明，保留原gateway类型验证、GET限定、原查询和同事务关联。只将原已验证date转ISO日期，其他有限JSON值保留；禁止default=str、全局JSON serializer、浮点金额转换、绕过原校验或更改确认路径。复用现M8.2真实read检查；若现节点包含独立崩溃/24轮合同而不宜混入，允许仅在原 `test_runtime_checkpoint_recovery.py` 加一条小的真实Run→日期GET→Work落盘→原结果及零业务变化检查，同步原manifest/restoration，不建新执行框架。按V原入口定向通过后再真实复验；旧日期context节点未变，不重复它。此项是已观察执行失败的修复，不据正确模型参数就宣称F02通过。
