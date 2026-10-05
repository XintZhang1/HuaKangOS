# M8.5 同源21代表模式对照

日期：2026-10-05。结论：**M8.5仍in_progress；本报告不放行完整283或M8.6。**

## 后续high终局（覆盖本报告下方的当前时序）

9cb6868/source `d6d0b51b76be7b3ab10d4023880cac11586f0a597b5cee8f418e23d2a3918fb6`仅改变DeepSeek thinking强度及对应记录；原请求体节点111506Z-a11a730655实际1 passed/0 skipped，collector22.656秒、目标20.125秒，model0。新strict112559Z-96f2ac9125后，high代表112644Z-4e1e1431f7执行21条、145 POST、815.593秒、CLI1；五输入/三文件映射与本轮strict相等，正常排空且无超时。19条结构通过，V03/D04失败；不拼入下列不同模式结果。

核心语义仍有M02原到货80升与当前68升库存混同、V08请款清单自身前置错误，A07遗漏已有消费积分目标表。A03/A06金额及回访口径正确，六条销售/会员案例核心正确并保留措辞观察。V03错误实体URL的422已有正常反馈；之后第9轮find_cases仍running/下一项pending，终局precondition_conflict，需要离线定位，不能归因为缺少422反馈。D04第1402次HTTP200的工具参数JSON解析失败被原守卫拒绝。所有21例467业务表全等，无确认写入。

费用：新增144次结算6.243624元，1402次完整预留5.242880元；累计73.044270元，剩余上界206.955730元，原四次永久未知保持，当前因新预留停止。后续按PATCH-M8-5-LOCAL-LIVE-01核当前API的Pro模型能力，不把Flash评为通过。外部报告在`V/closeout-20261005/`：

- `mode-semantic-review/day_boundary/20261005T112644Z-4e1e1431f7-high-114438Z-16d6cf4d/six-case-semantic-review.json`，SHA256 `cda90746e4fdc5ceab4aee30dd0c756afa81385889b9add2a021fbd9c1fbce98`。
- `representative21-high-semantic-mobile-20261005T114345Z-36b71dad1e/independent-review.json`，SHA256 `dbc554966ea3ae65a3379810e6e58996b11c9883f27a3c8b9defa2e416558ba1`。
- `m85-attempt1257-ack-candidate-20261005T112136Z-c8c2cfa2d1/independent-high-review.json`，SHA256 `b7e90e7c713063a20121fb28df26b5a2c87cb6d42a984a05d31c36e6a255aa83`。

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
