# M8.5 同源21代表模式对照

日期：2026-10-05。结论：**M8.5仍in_progress；本报告不放行完整283或M8.6。**

## Pro high代表终局

受检HEAD `c93b7eede7e2d301827fababe73acfb7cd3d12d7`，source `e604280f6bf37817da87e3c082e4bfb06644ebdb755ff2d9001a495b8b1897be`。新strict `124039Z-09bf864f89` 18项通过（报告SHA `b4aae1697b793579479b8a93372bd46adf8206eee692830de925dbb53b072c2e`）；实际Pro high代表 `124118Z-875bdaf3ad` 21条、152 POST、1201.766秒、CLI1，报告SHA `3408b23e31bf587f71ef987c932e97e9babe36978a982197ce8cb2100e7be5e3`。进程自然排空、无超时，没有默认模型或默认思考模式通过的含义。

20条结构完成；M03在原父单404、客户查询403之后继续换入口检索，达到24轮上限。V05虽无卡，却把12个作业候选称为均可作业，忽略销售占用/交付及缺少原库位，不合格。其余核心事实本轮可接受；S01电话不存在尚未被姓名查询证明，S07保险入口概括偏窄，保留范围措辞观察。V03本轮正常等待真实采购/到货来源，D04两次真实查重后只准备一张1234分、30分钟、job计费的待确认工时卡；旧Flash的异常不因此擦除或宣布修复。

21例均无确认请求、各467业务表前后相等。152个新请求全部settled，保守核算5.867846元；累计1554次、78.912116元、剩余201.087884元，历史五个未知26.214400元原额保持，未新增未知或halt。这里是验证账本的保守占用，不是供应商实际账单。

独立原件仍在 `V/closeout-20261005/`：六例 `mode-semantic-review/day_boundary/20261005T124118Z-875bdaf3ad-pro-high-124327Z-68669952/terminal-six-case-semantic-review.json`（SHA `e10a2e387242cb6b429932cf6dbac9826f436ce0d2848906318214ecf6638e27`）；十一例 `representative21-pro-semantic-mobile-20261005T125938Z-193875db43/independent-review.json`（SHA `f2eb54e08ce59412e48ad0afef76cc1b88823f8a806395487a3969257684861c`，当时四例仍在运行，仅证明该十一例）。后续按PATCH-M8-5-LOCAL-LIVE-01补候选逐行事实与现有收尾阶段的工具开关，再做受影响代表和独立完整283；不拼接不同指纹的通过项。

其余四例及终局费用/五输入独审：`m85-pro21-regression-review-20261005T125854Z-f1f20913f2/independent-terminal-review.json`，SHA `46de80d085bf3d258727248a387ec7d85e1c1c2bd7f581033cb38fa9605f58fd`。M03完整链及重复检索位置：`representative21-pro-semantic-mobile-20261005T125938Z-193875db43/m03-context-and-budget-review.json`，SHA `c25cfbfe2fbec5c8e2cd2b395a90799a5d6981b3a4745be61adad6979df24bc7`；仅凭该证据不推断模型内部原因。

## 后续high终局（覆盖本报告下方的当前时序）

9cb6868/source `d6d0b51b76be7b3ab10d4023880cac11586f0a597b5cee8f418e23d2a3918fb6`仅改变DeepSeek thinking强度及对应记录；原请求体节点111506Z-a11a730655实际1 passed/0 skipped，collector22.656秒、目标20.125秒，model0。新strict112559Z-96f2ac9125后，high代表112644Z-4e1e1431f7执行21条、145 POST、815.593秒、CLI1；五输入/三文件映射与本轮strict相等，正常排空且无超时。19条结构通过，V03/D04失败；不拼入下列不同模式结果。

核心语义仍有M02原到货80升与当前68升库存混同、V08请款清单自身前置错误，A07遗漏已有消费积分目标表。A03/A06金额及回访口径正确，六条销售/会员案例核心正确并保留措辞观察。V03错误实体URL的422已有正常反馈；之后第9轮find_cases仍running/下一项pending，终局precondition_conflict，需要离线定位，不能归因为缺少422反馈。D04第1402次HTTP200的工具参数JSON解析失败被原守卫拒绝。所有21例467业务表全等，无确认写入。

费用：新增144次结算6.243624元，1402次完整预留5.242880元；累计73.044270元，剩余上界206.955730元，原四次永久未知保持，当前因新预留停止。后续按PATCH-M8-5-LOCAL-LIVE-01核当前API的Pro模型能力，不把Flash评为通过。外部报告在`V/closeout-20261005/`：

- `mode-semantic-review/day_boundary/20261005T112644Z-4e1e1431f7-high-114438Z-16d6cf4d/six-case-semantic-review.json`，SHA256 `cda90746e4fdc5ceab4aee30dd0c756afa81385889b9add2a021fbd9c1fbce98`。
- `representative21-high-semantic-mobile-20261005T114345Z-36b71dad1e/independent-review.json`，SHA256 `dbc554966ea3ae65a3379810e6e58996b11c9883f27a3c8b9defa2e416558ba1`。
- `m85-attempt1257-ack-candidate-20261005T112136Z-c8c2cfa2d1/independent-high-review.json`，SHA256 `b7e90e7c713063a20121fb28df26b5a2c87cb6d42a984a05d31c36e6a255aa83`。

## V03合成复现与Pro入口审阅

在`1fa5b5b`/source `90991484d0869aacf687c0992aa4740eb9297d4fe33193d08f812197d0408ab2`，strict `121122Z-fac723948f`通过；`121153Z-710253bbe8`经原M8.2完整collector（3410节点、464.594秒）执行唯一新增读取复现节点（34.234秒），diagnostic_passed、真实模型0、进程正常排空、五输入未变。九轮原已接受工具意图加一轮固定终局回复共10次合成响应；错误实体URL的422已反馈，后续两个find_cases均succeeded，零卡、业务快照不变。此结果**未复现**真实high中的中断，不据此改生产守卫或宣布真实V03已修复。安全诊断SHA `7c9f99b7db9bdac982eae241aa9dbaa0686c68968d300bed11eb9986223d8164`；run SHA `8cab20cdfaf980758eeeee32548ccce23fbb5efedc9ef22767a67dbd51ab9b75`。

Pro入口与费用两源已独立静审并在诊断排空后应用：外部live_gate SHA `8fdf41ec1226b7a485c9c991527b022452ec005ce68849e52c24efa968bbfc92`，适配器模型入口SHA `28218d1a904e63282fa1d16f920042538b35928a60f3c5f610f87b5a3e5d6c4c`。固定Pro及其高峰费率，完整缓存分项按登记规则计费，旧1402行/73.044270元原额保留；应用回执SHA `e105daf39977dd7703e7f6104f1e29568b095bd05217ca217812dd3315b8435d`。真实Pro尚未调用，仍待有限工具异常诊断、明确1402保留恢复和新strict。离线诊断与后续费用入口的指纹不同，不拼成同一全量成绩；原E节点不因独立费用代码变更重复运行。

## 此前同源普通/low对照

受检HEAD为`3a28f3562c0fc33f430ed82efa7671cd06b21573`，源码指纹为`f6331e8d5815b492e7bdbc096394a452eeb49dc8e8b9df838448ce4587d2206f`。同一DeepSeek Flash、21条原代表、原283/101定义、合成夹具和工具；通过真实员工Run接口、worker及provider执行。每例独立恢复合成基线，没有模型确认工具。模式参数显式记录，未修改产品默认。

| 模式 | 同输入strict | 真实run | 实际结果 |
|---|---|---|---|
| thinking=false | 104048Z-ccfb977eeb，18 passed | 104141Z-b7f74b72e4 | 21条原件，106 POST全部已结算；263.297秒、CLI0。结构完成但A03/A06/M02/M04有语义错误，M03未定位请求对象。 |
| thinking=true、effort=low | 105450Z-9e899bec80，18 passed | 105531Z-8a7f7e8080 | 21条原件，134 POST；528.562秒、CLI1。18条可接受，V03/V05来源范围错误，D04工具JSON不完整而失败。 |

两轮原件位于`V/runs/20261005T<上述run>/`；所有已记录案例的467张业务表前后哈希一致，没有确认写入。这里的可接受包含有事实依据的等待与权限拒绝，不把无卡自动判失败，也不把卡准备当业务完成。

## 语义审阅

普通模式A03把维修结算指标称实际收款，A06把售前沟通当完成回访；M02把80升历史入库与68升当前库存称为一致，M04把机油原领料推荐为滤芯退回来源。思考模式这四例均已区分真实来源；M03查明四个可见子单及父单不可查看，明确不能据此绑定客户姓名，正确等待有权人员核对。不能扩大父单读取权限来提高检索成绩。

思考模式V03已读取原Flow四条采购，却把采购接口空结果外推；V05把12个车辆作业候选称为在库，而同例当前车辆目录仅11台。原API已有范围提示，这属于模型收到真实事实后的错误表述，不能以结构通过消除。S01/S08仍有姓名查询与电话查询能力措辞观察；S06的子单负责人来源真实，但不是逐待办接手人的完整查询。

D04第1257次请求HTTP200，非流式`finish=tool_calls`，一个工具参数字符串不能由JSON解析器完整解析。安全诊断为`ModelProtocolError → JSONDecodeError`，原完整性守卫正确拒绝，零卡、Run失败；不是45秒超时。未保存响应正文、推理或凭据，不修补不完整JSON、不重放该Run。

外部独审原件（均在`V/closeout-20261005/`，完整路径与各case哈希在报告内）：

- 普通六例：`mode-semantic-review/day_boundary/20261005T104141Z-b7f74b72e4-false-104946Z-89352b7d/six-case-semantic-review.json`，SHA256 `a378a936ca996d49ed4981fddd959c3acaecb7ba497c30df400c317988b19768`。
- 普通十一例：`representative21-normal-semantic-mobile-20261005T104357Z-d29aa2c90b/independent-review.json`，SHA256 `39993f1ea50719b65896b7a9f0b401da00617613a1f87567c1b40c158f2e0d92`。
- 普通四例及费用：`m85-thinking-true-switch-candidate-20261005T105128Z-dc87f1c07a/independent-false-review.json`，SHA256 `e5c8f17657c59ebb948a6756af7da5a0a5f6519749d03dc0328d11685d2e8829`。
- 思考十一例：`representative21-thinking-semantic-mobile-20261005T110557Z-a2436029d6/independent-review.json`，SHA256 `9df43fd2e334ba77451d9a53c64172a841d6dcf41e1abe09951057bc50fd7a2a`。
- 思考六例：`mode-semantic-review/day_boundary/20261005T105531Z-8a7f7e8080-true-110905Z-9b61018f/six-case-semantic-review.json`，SHA256 `2b27f17a4d1860e2e270692577fbbf51b50ad2f1b9d0e8dcda810a073e2e950a`。

## 后续范围

累计1257次、保守占用61.557766元；其中1、2、558三次永久未知和1257完整预留合计20.971520元，均不释放或当作已结算账单。280元总额、6000次、每次预留、端点与隔离守卫不变。依PATCH-M8-5-LOCAL-LIVE-01，仅将DeepSeek已开启thinking的强度改high；先核原provider请求体与拒绝节点，再同21条有限复验。原普通模式默认未因此通过，完整283/101和M8.6不得继承本报告结果。
