# HuaKangOS 专用业务 Runtime：实施架构合同

版本：runtime-v1 / 2026-09-27。本文描述待实施结构；不得将接口、表或测试写成已经存在。产品规则见`PROJECT_SPEC.md`，实施次序与写入边界见`implementation_plan.md`。

实施计划及其审阅补丁控制检查点和限定基线纠偏，不修改本架构。2026-09-28 用户改为两阶段：本轮 Codex 按依赖优先完成实现，后续由 DeepSeek 集中执行原全部验收并修复。编码产物和人工代码审查完成后记 `implemented`，全部验收满足才记 `done`；编码 CP 可记 `implementation_released` 继续后项，不代表测试通过或允许启用。实施 CP 与下文运行时恢复检查点不同。

当前不新增/运行测试、不扩 runner、不调用真实模型，也不做浏览器、PostgreSQL 或故障演练；必要轻量静态检查不代替验收。原接口、权限、业务确认、状态机、事务和默认关闭开关不变。历史 M0.2.A 纠偏与 CP-00B-v5 报告保留，未测的符号链接条件后移，不借此修改产品合同或 OS。执行与测试分别见 `CODEX_EXECUTION_PROMPT.md`、`DEEPSEEK_TESTING_HANDOFF.md`。

## A. 系统边界和数据流

```text
员工登录页面 ── 原人工模块 ────────────────── 原业务API
      │                                          │
      └─ 助手工作台 ─ 消息/Run API ─ DB队列         ├─ 原状态机/权限/回执
                              │                  └─ 原业务数据与附件
                         单槽worker
                              │
                  上下文 → 模型 → 完整工具意图
                              │
                  原授权GET查询 / 准备确认卡
                              │
                   员工点击原confirm接口 ──────────┘
                              │
                    结果/事件 → 条件核对 → 下一步准备
```

- 一个逻辑业务Agent；模型循环、权限、工具、计划、队列分别组织为Python模块。
- 不替换ERP域模型，不建立第二套销售／维修／财务状态机。
- PostgreSQL与SQLite共享逻辑；不改变`app/db.py`现有隔离级别和租户过滤来解决并发。
- 后台仅查询、计划、准备。银行、到账、库存交接、签回等事实仍由原业务接口和人员确认。
- 新增源文件位于`app/`；领域适配器位于`app/assistant_runtime_domains/`。前端仍为原生JS。

## B. 模块职责和接口

下列是规定的新模块。未轮到对应里程碑前，不提前实现其业务逻辑。

| 模块 | 负责 | 禁止 |
|---|---|---|
| `assistant_runtime_schemas.py` | DTO、状态枚举、条件联合类型、严格入参 | 导入并启动app/数据库、执行业务 |
| `assistant_runtime_models.py` | Runtime ORM与索引 | 领域状态、原业务流水schema |
| `assistant_runtime_registry.py` | 工具分类、适配器注册、按原reviewed目录解析操作 | 新动作名白名单、插件市场 |
| `assistant_runtime_objects.py` | 原单引用与适配器分派、授权快照 | 任意表名/SQL/URL |
| `assistant_runtime_domains/*.py` | 单一业务族只读快照、结果映射、原生回执核对 | 直接业务写入、重写原状态机 |
| `assistant_runtime_principal.py` | 即时会话/Grant重验、内部ASGI调用身份 | 持久化Cookie/CSRF、管理员代跑 |
| `assistant_runtime_plans.py` | DAG、目标版本、旧计划升级、Grant启停 | 改原Case/Task状态 |
| `assistant_runtime_conditions.py` | 有限类型条件的真实事实判断 | 执行表达式、把自由文本当条件 |
| `assistant_runtime_context.py` | 有来源快照、上下文预算、恢复组装 | 原始推理持久化、跨会话自动混资料 |
| `assistant_runtime_provider.py` | 现有模型请求/SSE/usage适配 | 更换供应商、任意endpoint、降低截断保护 |
| `assistant_runtime_queue.py` | Run入队、CAS领取、租约、互斥、重试 | 持长事务等待网络 |
| `assistant_runtime_events.py` | RunEvent序号、可展示快照、事件补读 | 原始推理/凭据事件 |
| `assistant_runtime_runner.py` | 单次Run，完整工具意图落库、读取与准备检查点 | 业务确认、后台调用原业务POST |
| `assistant_runtime_receipts.py` | 冻结提交读取、受评审回执核对、恢复分类 | 找不到回执就重放 |
| `assistant_runtime_outbox.py` | 原事务signal、分发、去重、定时补漏 | 在原业务事务中调用模型/网络队列 |
| `assistant_runtime_workspace.py` | 授权侧栏投影、通知读取与计数 | 放宽原任务查询、混算总量 |
| `assistant_runtime_api.py` | HTTP DTO、授权、返回语义 | 第二个业务确认入口 |
| `assistant_worker.py` | 相同worker核心的CLI/单次运行/关闭 | 初始化现有库、隐式连接公司库 |

原`business_assistant_service.py`保留兼容入口、确认主流程和原消息/卡展示；只拆出上述职责，不整文件重写。

### B1. 适配器最小协议

```python
class DomainAdapter:
    async def read_snapshot(self, principal, ref) -> BusinessObjectSnapshot: ...
    def extract_result(self, operation_id, response) -> list[BusinessObjectRef]: ...
    async def read_receipt(self, principal, submission) -> ReceiptLookup: ...
    async def fact_snapshot(self, principal, ref, fact_key) -> FactSnapshot: ...
```

适配器由registry构建并注入受控`native_reader`和需要的原生回执读取器。`principal`是服务端构造的RuntimePrincipal；不是HTTP请求里的自报用户字典。方法不commit、不执行领域写，不自行开管理员DB范围。

通用Case的引用type固定为`case`，`flow_case.py`只是通用适配器文件名，不新增flow_case对象类型。多个专用适配器共用case/group_member等原引用时，注册表先从授权原读取证明kind/flow_version，再按固定operation_id或领域fact_key分派；相同键只能有一个provider。M7每项的“注册合同”给出有限对象类型/原主键/事实键，不能由模型选择Python模块。

原API具有明确结果结构才可提取ID。`native_version`不存在就返回null，不造版本号。原API动作不可用则返回原原因，不制造可用动作。只读报表没有实体ID时使用`ref={type:'report_query',id:WorkItem.id}`；冻结查询来自该本人WorkItem的`validated_intent`，只允许原注册GET参数。报表快照不能作为到账、库存交接等完成事实。

### B2. 基础类型

```text
BusinessObjectRef = {type: 注册类型, id: 原整数ID或规定UUID}
EvidenceRef = {source_type: message|object|proposal|task|receipt,
               source_id, native_version: int|null, observed_at: UTC时间}
BusinessObjectSnapshot = {ref, native_version, display_number, state,
                          tasks[], available_actions[], evidence_refs[],
                          manual_route, observed_at}
FactSnapshot = {fact_key, satisfied: bool|null, evidence_refs[], reason}
ReceiptLookup = {status: confirmed_success|not_found|unsupported|inaccessible|mismatch,
                 checked_at, object_refs[], evidence_refs[], reason_code}
```

null的事实满足值表示无法确定，不能等同false并自动补办。`manual_route`必须来自原路由映射/发布目录；未知版本回原通用页。工具结果超限沿用现有缩减/分页提示，不静默截断成“完整结果”。

`available_actions`每项固定为`{action_key,availability:enabled|disabled|unknown,reason?,evidence_refs[]}`。仅岗位过滤后的动作字符串只证明入口可见，映射为unknown；只有原API明确的enabled或已存在纯只读原守卫的通过结果才可满足`native_action_available`。禁止试调写接口探测可用性。未知项仍可在员工明确要求后准备待补信息的卡，但不能据此自动推进；若所承诺自动续办依赖无法由原接口证实，记录能力缺口并阻塞相关验收。

### B3. 准备的只读解析与事务保存分离

现有`business_assistant_business_tools.prepare`和`business_assistant_case_tools.handle_case_tool`也调用会commit的旧准备包装，前者还单独commit展示快照。Runtime不能仅绕过底层prepare_proposal就声称原子保存。

内部固定分成`resolve_preparation`和`persist_preparation`：前者复用原候选、表单、版本和严格字段校验，完成所有授权原GET，返回`ResolvedPreparation`（operation_id/path_args/query/body/questions/question_fields/presentation/references/label/step_order/step_label）或needs_source；无卡/WorkItem/事件写入。后者在无网络的短事务重新验权/fence/目标版本/稳定意图，保存WorkItem、Proposal、展示快照、Step和事件。原兼容包装默认仍resolve后提交，原返回形状保持；Runtime使用无内部commit的persist路径。不得在未提交卡片的事务里调用会commit的旧native/read helper。

ResolvedPreparation是服务器内部类型，不是模型输入/HTTP权限凭据；写入前重新验证所有归属。幂等意图摘要仅排除服务器本次将生成的request_id，不能排除原版本、金额、对象、员工明确指定字段；先比既有WorkItem，再决定是否首次生成请求号。

## C. 数据模型与约束

新增迁移头：`h53k_assistant_runtime`，父版本`h52j_assistant_work_plans`。迁移前先完成ORM和schema，确认冻结持久化在迁移之后实施。若编号已被其他工作使用，停止报告冲突，不改旧迁移或猜新父版本。

### C1. 公共规则

- UUID使用项目现有`String(36)`；枚举String+CheckConstraint；JSON用可移植SQLAlchemy JSON。
- 时间沿用`utcnow()`的UTC-naive数据库值，API序列化加Z；本地日期使用现有`settings.timezone`。
- 员工数据记录有`owner_id/store_id/session_id`所需归属；所有外键和引用先验权再返回。
- Runtime可变记录使用整数`version`乐观锁；事件/快照为追加记录。
- 不给引用短期登录会话的字段建阻止logout删除会话的FK；只存服务器已有的session hash标识，内部使用，不在API/日志中暴露。
- 不使用跨数据库不兼容的隐含触发器。唯一索引、外键和服务层检查共同保证归属；备份检查也验证归属和DAG。

### C2. 既有表扩展

`AssistantWorkPlan`新增：`engine_version`(1/2,旧默认1)、`goal_version`(>=1)、`status`、`context_snapshot_id`(可空)、`next_check_at`(可空)。保留原`session_id/owner_id/store_id/goal/steps/version`。

- `version`：所有计划修改的乐观锁。
- `goal_version`：只有目标范围、必要步骤或等待条件的结构性变化才增加。Grant与Run绑定它。填入真实前序ID、更新状态和时间不增加goal_version。
- `steps`：旧版历史快照；v2唯一可写图在PlanStep，旧接口响应从PlanStep生成，不维护两份可编辑DAG。

`AssistantProposal`新增可空`source_work_item_id`唯一外键。WorkItem不再加反向proposal外键，避免循环FK；通过该唯一关联查卡。旧卡为null。旧payload/digest/状态/权限快照全部保留。

### C3. 新表字段合同

所有表名用`business_assistant_`前缀；每表都包含必要的主键及创建时间。

| 类/表后缀 | 必须字段和约束 |
|---|---|
| PlanStep / `plan_steps` | plan_id, key, position, title(160), wait_for(500，仅解释), depends_on(JSON稳定key数组), proposal_id?(当前关联卡FK), object_ref, workflow_id, form_ref, conditions(JSON), completion_conditions(JSON), required(bool), status, wait_reason, last_evidence, intent_version, version；唯一(plan_id,key)、(plan_id,proposal_id) |
| WorkItem / `work_items` | owner_id,store_id,session_id,plan_id?,step_id?,origin_request_id,input_item_id,intent_version,item_kind(read/prepare),intent_key,operation_id,validated_intent,source_refs,status,supersedes_id?,version；唯一(owner_id,store_id,intent_key) |
| Run / `runs` | owner_id,store_id,session_id,plan_id?,trigger_kind(user/signal/manual),trigger_key,request_id?,request_digest,entry_context(JSON可空，已验证引用),auth_kind(login/grant),login_session_ref?,grant_id?,goal_version?,status,next_run_at,lease_owner?,lease_until?,fence(default0),attempt,stop_requested,priority,display_text,display_revision,event_seq,usage(JSON),error_code?,started_at?,finished_at?,version；唯一(owner_id,store_id,trigger_key) |
| RunItem / `run_items` | run_id?,work_item_id?,proposal_id?,kind(model/tool/batch_row/confirmation),item_key,attempt_no,tool_name?,validated_arguments?,result_refs?,status,error_code?,started_at?,finished_at?,submission_snapshot?,submission_digest?；工具尝试唯一(run_id,item_key,attempt_no)；confirmation对proposal_id唯一 |
| ContextSnapshot / `context_snapshots` | owner_id,store_id,session_id,plan_id?,goal_version?,through_message_id,goal,constraints,confirmed_selections,open_questions,evidence_refs,unverified_notes；不可覆盖 |
| RunEvent / `run_events` | run_id,seq,type,payload(脱敏最小内容),created_at；唯一(run_id,seq) |
| FollowupGrant / `followup_grants` | plan_id,owner_id,store_id,session_id,owner_role,access_version,goal_version,status,granted_at,expires_at?,revoked_at?,stop_reason?,version；每plan最多一个active，SQLite/PostgreSQL部分唯一索引 |
| WakeEvent / `wake_events` | signal_key,topic,store_id,object_ref?,proposal_id?,task_id?,plan_id?,source_ref?,state(pending/dispatched),attempt,next_attempt_at,created_at,dispatched_at?；signal_key唯一 |
| Notification / `notifications` | owner_id,store_id,session_id?,plan_id?,proposal_id?,task_id?,source_key,kind,safe_summary,status(unread/read/resolved),created_at,read_at?；唯一(owner_id,store_id,source_key,kind) |

索引至少覆盖Run的(status,next_run_at)、lease_until、session_id、plan_id；Plan/Grant的owner+store；WakeEvent的(state,next_attempt_at)；Notification的owner+store+status。`RunItem`的confirmation可以没有run_id：旧会话的人工确认也必须冻结提交，但不得为了留痕偷偷创建模型Run；其他kind必须有run_id。该例外由数据库CHECK及schema同时约束。

`submission_snapshot`只存最终operation_id/path_args/query/body/真实request_id/actor_id/store_id/role/access_version/confirmed_at；不含Cookie、CSRF、原始推理。正常GET响应不直接返回这个内部快照。

冻结快照摘要在M1.1即实现于纯schema模块：对校验后的完整snapshot使用`json.dumps(sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)`的UTF-8字节做SHA-256；时间先统一为UTC字符串。完整性检查与确认共用此函数，不能各自选算法。此摘要只检查助手冻结内容，原领域request_digest仍沿原算法。

用户Run与原AssistantMessage(user,request_id,content,thinking)同事务首次保存；Run.request_digest覆盖content/thinking/plan_id/已验证entry_context，Run.entry_context保存该引用。恢复时由session+request_id读取用户输入，不从最新消息猜。后台signal Run不伪造user消息；其最终回复键固定`run:<run_id>:reply`，用户Run仍为原`<request_id>:reply`，所有恢复路径复用同一键。

WorkPlan.context_snapshot_id若需跨后建表FK，迁移分两步建表再加引用；禁止为方便省略整体验证。所有旧记录默认不跟进、不排队、不补造快照。

PlanStep.proposal_id只保存旧计划或明确引用既有单卡的兼容关系，不替代Proposal.source_work_item_id，也不代表批量的全部卡。新准备项通过WorkItem.step_id+当前intent_version取得完整行集合并关联Proposal；Step/WorkItem/Proposal同事务保存。历史superseded项保留，仅检查归属和替代链，不要求等于当前卡。兼容单卡与新当前行不能重复计数；同一Step若已有兼容单卡且未明确重新准备，不另创建当前行集合。

PlanStepView的proposal_ids是当前意图所有行的真实卡ID数组；兼容单卡包含在该数组，proposal_id仅保留旧字段兼容。批量步骤按完整行集合核对：任一uncertain阻塞依赖；缺输入行保持needs_input；仍有待确认行显示awaiting_confirmation并保留各行错误；必要行失败/取消不可被其他成功行掩盖；所有必要行确证成功且完成条件满足才completed。prepared/settled数不等于成功数，必须读取对应卡的确定结果。新一版意图的行集合仍沿服务端原input_item_id核对完整性。

### C4. 图、身份和幂等不变量

1. PlanStep依赖必须同plan、无环、无重复key、无悬空引用；有依赖时按拓扑序，不信任模型数组顺序。
2. proposal引用必须同owner/store/session；WorkItem、Run、Grant必须与对应会话/计划一致。
3. 有完整模型回复且校验成功后才落可执行RunItem；半截JSON不可产生任何项。
4. 长期准备键=plan+step key+input item ID+intent_version；即时准备键=消息request_id+input item ID+intent_version。
5. input item ID由服务端在完整输入意图首次接受时固定，批量保留原行顺序；跨Run沿用。相同键但参数指纹不同返回409，不能覆盖。
6. 相同意图的两worker并发以WorkItem唯一键与Proposal唯一关联兜底。过期/失败后的重新准备必须员工明确触发新intent_version，保留supersedes关系。
7. 模型重新规划只可引用真实对象；不能把已经成功的必要步骤又变回待执行。

## D. 状态机和事务

### D1. Runtime状态（不是原业务状态）

| 对象 | 合法转换与触发 |
|---|---|
| Plan | active→paused（员工暂停/授权失效）；paused→active（本人有效恢复）；active→completed（全部必要步骤及真实完成条件满足）；active/paused→cancelled（员工结束）。终态不自动重开 |
| Step | waiting→needs_input/awaiting_confirmation/completed/failed；needs_input→waiting/awaiting_confirmation；awaiting_confirmation→completed/failed/uncertain/cancelled；动作成功但真实完成条件尚未满足→waiting(wait_reason=external_fact)，关联WorkItem保持settled；卡过期→waiting(wait_reason=expired)；uncertain仅在可靠回执核对后→completed或waiting(external_fact)，否则保持需人工核对 |
| Run | queued→running→succeeded/failed/cancelled；queued→cancelled用于领取前停止/撤权；running→queued只用于丢失租约/可安全重试的查询准备；不得重放confirmation |
| RunItem | pending→running→succeeded/failed/uncertain；未执行的项可skipped；纯读失败允许新增attempt，原记录不删 |
| WorkItem | prepare项planned→prepared（有真实卡）→settled（卡已确定处理）；read项读取成功planned→settled，无卡；安全读失败保持planned并增加RunItem尝试记录；未知业务执行→uncertain；员工重新准备创建新意图版本，不把旧项改回planned |
| Grant | active→paused（员工暂停/目标结构变化）；paused→active（重新校验本人确认）；active/paused→revoked（撤销、完成、权限失效）；revoked不可原地复活 |
| Notification | unread→read；真实事项已无需处理才resolved。read不触发原任务完成 |

缺前序、取消前序、未知结果、不满足原状态守卫都禁止推进相关依赖。前序API调用成功仅说明该动作成功；有真实完成条件的步骤要继续核对，不能只看HTTP 200。

员工明确重新准备可让failed/cancelled/expired原因的Step增加intent_version后回waiting/needs_input，再进入awaiting_confirmation；保留旧WorkItem/卡并建立supersedes。未结束Plan才允许重开，completed步骤不能无证据退回，uncertain不能用新意图绕过回执核对。取消卡片不等于取消整个事项。

### D2. 原子性边界

- 保存Plan及全部Step、结构版本变化和旧Grant暂停：一次事务。
- 开启/暂停Grant、相应Run入队/停止标志和WakeEvent：一次事务。
- 准备卡、WorkItem关联、Step状态、RunItem结果和事件：一次事务；内部构建函数只flush。
- WakeEvent分发标记与Run去重入队：一次事务。
- Run事件seq通过更新同一Run.event_seq并插入事件在同一短事务完成；并发冲突仅重试落库，不重复外部调用。
- 业务确认固定三段：冻结submission并置executing提交 → 原API自己的事务 → 助手结果/事件提交。不能合并宣称为一次事务。
- 确认后通知/投影失败不能把原业务成功改写为失败。恢复读取精确回执；找不到仍未知。

### D3. 请求号和确认冻结

`validate_operation`成为纯校验，不生成/替换request_id。服务端准备函数只对原本幂等的操作生成一次request_id，模型不能提供或改写；无幂等号的原操作不得伪造支持。

缺项探测使用独立临时副本；探测字段/请求号不得污染原草稿。员工补填后规范化一次，保留原号；确认前创建唯一confirmation RunItem，冻结实际将发送的全部payload，与Proposal.executing一起提交。原API只收到该冻结副本。

原生摘要必须按该原API的算法计算，不能用助手card digest替代。GET核对只返回ReceiptLookup；reconciliation才更新助手状态，旧未知卡没有快照返回unsupported(reason=missing_submission_snapshot)。原生无可靠回执的动作保留人工核对。

### D4. 拒绝分类

在原异常处理路径中让`note_refusal()`返回已成功保存的最小refusal引用，原JSON `detail`保持不变，可增加`refusal:{id,category,can_escalate}`。保存失败不影响原响应且不输出伪refusal。

gateway仅依据这一真实记录显示评审引导；category=rule、认证/CSRF失败、无记录一律不提示可评审。禁止只凭403推断权限不足，禁止由模型创建/reforge refusal。原评审收件岗位、不能自批、不能通过评审执行业务全部保留。

## E. 身份、调度、恢复

### E1. 内部principal

RuntimePrincipal包括actor/store/role/access_version及login或grant来源，由服务端查询生成。内部transport构造带私有Python标记对象的ASGI scope；`get_user`只有看到受信标记且验证当前Run/Grant后才接受。网络请求不能序列化该对象，不接受任何`X-Run-ID`式身份旁路。

内部调用仍走原路由、`attach_scope`及业务授权。GET之外方法拒绝；GET也必须是registry已登记的具体operation，不能借只读身份访问任意管理接口。为receipt lookup登记专门只读入口，不扩大原数据目录。

每个完整工具前、模型外发前和结果暴露前重验员工/门店启用、当前门店岗位、access_version、首次改密及来源授权。即时Run检查原LoginSession存在且有效；Grant默认expires_at=null，退出不撤销，权限变化即时失效。

权限变化后的旧session/proposal权限快照不可更新。重新授权建立新有效会话/事项，仅重新读取当前可见对象；旧私聊与旧payload不得因新Grant重新暴露。

普通暂停恢复且goal_version未变，可原Grant paused→active；目标结构改变后点击resume表示员工重新审阅新范围：在同事务将旧Grant revoked并创建绑定新goal_version的active Grant。不得覆盖旧授权范围以抹去审计；角色/access_version已变仍按上段新会话规则办理。

### E2. 队列默认值

| 项 | 固定默认 |
|---|---|
| worker执行槽 | 1 |
| 队列/发件箱检查 | 5秒 |
| 等待计划补漏 | 5分钟；明确到期条件用next_check_at |
| lease / heartbeat | 90秒 / 20秒 |
| 瞬时安全重试 | 30秒、120秒、600秒，随后failed并需处理 |
| 模型单请求/片段 | 沿用现有默认45秒、24轮/600秒及原硬保护 |
| 草稿有效期 | 原30分钟 |
| 无新事实 | 0模型调用 |

Run通过条件UPDATE+受影响行数CAS领取；原会话version/busy_token同时防止前台/MCP与worker交错准备。领取按固定顺序锁session→plan→run，短事务失败退回队列。同session/plan最多一个活动执行。MCP的原busy租约也必须被尊重。

所有worker写回要求fence仍匹配、租约有效、stop_requested=false、goal_version仍有效、授权仍有效；包括最终保存卡片，不仅保存Run状态。过期worker只丢弃自己的未提交结果，不覆盖新状态。

上条限制针对新增成果/准备/进度推进。控制收尾是明确例外：当前持有有效fence与租约的worker可在stop_requested=true或授权/目标失效后，把自身Run标cancelled、未执行项skipped、释放自己busy_token并写最小取消事件；不得新增卡、暴露失权业务内容或恢复running。已失租worker连控制收尾也不得覆盖新持有者，由CAS恢复器处理。

用户新输入优先；当前完整工具完成后后台让出。输入改变目标结构则旧Run取消并暂停Grant，等待明确新授权。未改变目标的补充资料沿用同一事项，创建新Run，不偷偷修改已冻结确认内容。

### E3. 事件与监测

事务发件箱只存对象/任务/卡片引用，不存私聊和客户明细。原领域服务内只调用轻量signal helper，不调用模型或网络。先接flow事件、任务转交、卡结果、Grant变更与权限变更；专用领域在各适配里程碑添加精确hook。

按每条未分发事件处理，不能只保存最大ID。分发按原引用找等待事项，重新验权和读事实后判断；同一goal_version+来源键唯一Run。条件快照指纹不变不再调用模型，周期补漏也复用指纹。业务版本变化不等于必须准备下一步，先判有限条件。

### E4. 等待条件联合类型

```text
proposal_succeeded {proposal_id}
native_action_available {object_ref, action_key}
native_task_state {task_id, expected_status: 原任务合法状态, expected_assignee_id?}
fact_exists {object_ref, fact_key: 适配器注册的有限键}
due_at {at: UTC时间, source_message_id}
```

conditions是AND数组；无任意表达式/JSONPath/SQL。`wait_for`只解释。事实不足返回waiting或needs_input，不靠模型猜。完成条件独立于准备前置条件，例如“动作可办”不能被当成“动作完成”。

空conditions只表示没有额外准备前置；空completion_conditions不能证明业务完成。必要步骤没有可靠完成条件时保持waiting/needs_input，首次开启跟进明确列出该缺口。不能用all([])或无Task/无卡让Plan自动completed。明确只读步骤可用当前read WorkItem已成功且其原授权查询结果仍有效作为运行完成依据，此项仅表示查询完成，不能代替实体业务完成。

### E5. 崩溃恢复顺序

1. 重验授权和目标版本。
2. 若有executing/uncertain确认，先核对冻结快照对应回执；禁止发POST。
3. 已落完整工具意图而未完成：纯读可重查；准备先查WorkItem→Proposal关联再继续。
4. 模型链中断：保留已完成工具和卡，丢弃不完整回复；用真实快照开始新链。原始推理不恢复/落盘。
5. 实际业务成功、助手结果未存：可靠回执核对后追加恢复证据，不能再执行该业务。

## F. API、SSE和前端合同

所有新HTTP API前缀`/api/business-assistant`，沿用真实登录、CSRF、当前门店。模型/MCP无Grant控制工具。API错误：入参422；不可见404（不泄露对象存在）；已知权限403；版本/重复内容/前置冲突409；配置或运行不可用503。

| 路由 | 请求/响应关键约定 |
|---|---|
| POST sessions/{id}/runs | `{request_id,content,thinking,plan_id?,entry_context?}`；身份来自会话；同request_id同内容返回原run，不同内容409；202返回RunView |
| GET runs/{id} | 本人同门店RunView，重新验权 |
| GET runs/{id}/events?after_seq=N | 返回N后的事件；SSE带id=seq；心跳不改业务；鉴权失效终止且不继续吐旧缓存 |
| POST runs/{id}/cancel | `{expected_version}`；幂等停止查询/准备，已有卡/原业务不回滚 |
| GET plans/{id} | PlanView；步骤/卡/原单分别显示实际状态 |
| POST plans/{id}/followup | `{action:enable|pause|resume|revoke,expected_version}`；仅本人点击；revoke对应结束事项；GET从不授权 |
| GET workspace | `{group?,cursor?,limit?}`；分组attention/following/finished，默认limit30上限100；权限过滤在计数/分页前 |
| GET notifications | 本人同店分页；只返回仍可见的引用与安全摘要 |
| POST notifications/{id}/read | 幂等标记已读，不改业务 |
| GET sessions/{sid}/proposals/{pid}/execution-result | 无自由request_id/table/actor参数，返回ReceiptLookup；只读不改Proposal |

```text
RunView = {id,session_id,plan_id,status,version,last_seq,
           display:{phase,text,revision},result_refs[],error?,allowed_actions[]}
PlanView = {id,session_id,version,goal_version,goal,status,
            steps[],grant:{status,enabled,stop_reason},allowed_actions[]}
WorkspaceView = {features:{home,runtime,followup,notifications},
                 counts:{native_tasks,pending_proposals,attention,following,finished},
                 groups:[{key,items[],next_cursor}],checked_at}
WorkspaceItem = {key,kind:native_task|proposal|plan,session_id?,plan_id?,
                 task_id?,proposal_id?,object_ref?,title,status,status_label,
                 waiting_reason?,due_at?,manual_route?,allowed_actions[],updated_at}
```

Workspace key必须稳定（如task:42、proposal:UUID、plan:UUID），不可数组下标。合并只用确定task_id；不从中文摘要去重。counts没有混合total，group计数在授权过滤后计算。游标稳定使用排序键+唯一ID，不暴露跨店查询。

补充wire合同：

```text
SessionView.last_request.run_id = string|null  # 原字段保留，刷新定位已有Run
entry_context = {source_type:task|object|workflow,
                 intent:query_status|explain_prerequisites|prepare_action,
                 task_id?|object_ref?|workflow_id?}
PlanStepView = {key,position,title,wait_for,status,wait_reason,proposal_id?,proposal_ids[],object_ref?,manual_route?}
NotificationList = {items:NotificationView[],next_cursor,unread_count}
NotificationView = {id,kind,safe_summary,status,created_at,read_at,
                    session_id?,plan_id?,proposal_id?,task_id?,manual_route?}
RunEventView = {run_id,seq,type,payload,created_at}
```

entry_context按source_type恰好接受对应的一种引用，服务器重新验权/验证发布目录，不接受任意URL、脚本或module名称作为可执行指令。PlanStep保留原工具title/wait_for作为脱敏说明，不作为完成事实；缺标题时从原工作流/表单取得或显示第N步。Notification的manual_route仅从当前授权引用投影，GET支持cursor/limit（默认30、上限100），read返回更新后NotificationView。SSE data使用RunEventView；run.progress的payload为`{display:RunView.display}`。其他事件payload只含已提交对象的安全引用，UI需详情时重读对应GET。模型就绪状态复用原`GET /status`的ready/message，不在workspace增加第二份模型配置。

原`save_work_plan`工具保持名称，WorkPlan增加可选`schema_version:1|2`（旧请求缺省1）；WorkStep保留原字段，并兼容新增object_ref/form_ref/conditions/completion_conditions/required。schema_version=2使用严格联合条件，required默认true；case_id与object_ref同时出现必须指向相同原Case。legacy请求不推断自由文本条件；Runtime提示词明确要求新版计划schema_version=2，MCP旧请求仍可读/存旧计划但不自动跟进。首次明确开启旧计划跟进时先重验并升级；缺少可验证条件则返回需要补齐的步骤，不能把wait_for解析为可执行条件。

事件类型最少：run.queued/run.started/run.progress/tool.finished/proposal.prepared/plan.updated/run.completed/run.failed/run.cancelled。只有数据库实际状态产生事件。完整最终回复仍存原AssistantMessage并按原request_id去重。展示用display_text先脱敏，最多每秒合并更新一次；原始推理和认证数据不得进入事件。

旧`/messages`保持返回SessionView，内部入队并等待同一Run；正常完成返回旧形状。运行超过旧等待窗口返回明确503/504及同一run_id，重发同request_id只查原Run。旧`/messages/stream`转换同一Run事件为原前端形状，断开只停止订阅。旧confirmation/cancel/batch路由及已知HTTP语义保留；旧批量接口原继续执行语义不在本轮悄悄修改。

以上入队/断流解耦行为以runtime开关开启为条件。关闭时旧消息/流入口继续走原会话执行路径，新Run创建返回503；旧人工确认仍可处理有效卡。关闭runtime同时停止领取新Run与后台准备，已存在记录保留，恢复开启后按授权、租约及原幂等规则恢复。不能把开关关闭实现成旧助手不可用。

新前端模块：`web/assistantruntime.js`负责新接口、Run订阅和上下文代际；`web/assistantworkspace.js`负责侧栏、页面入口和守卫；`web/assistantworkspace.css`负责布局。旧`businessassistant.js`保留卡片补填/确认逻辑，通过适配调用新模块。不得两套状态store相互覆盖；临时草稿/答案仍归原会话内存，以session+proposal稳定ID索引。

## G. 上下文与资源

ContextBuilder固定装配：当前principal → 目标约束 → 计划/卡/任务 → 新读取事实 → 有来源快照 → 最近消息/当前输入。沿用原字段/结果长度边界；摘要只用于控制旧历史长度，不截掉当前员工输入或完整工具JSON。

快照区分confirmed facts和unverified notes。结构化事实从原API与明确员工选择提取；模型叙述不能直接转成付款/库存/签回字段。超过原30条或24000字符历史窗口前保存快照；保留来源引用与覆盖位置，不改写原消息。旧业务状态使用前重读，跨会话选择旧事项回其原会话，不自动混合资料。

provider仅抽取原实现并保持行为；usage缺失显示unknown，不能当0；记录请求次数、耗时、工具数、重试、是否来自后台。预算触顶明确结束该Run并保留已准备成果，不无限同指纹唤醒。真实模型评测与离线合成provider分别标记。

## H. 开关、启动、迁移与回退

四个新开关固定为`ASSISTANT_HOME_ENABLED`、`ASSISTANT_RUNTIME_ENABLED`、`ASSISTANT_FOLLOWUP_ENABLED`、`ASSISTANT_NOTIFICATIONS_ENABLED`，代码默认false；测试可显式开启。开启followup要求runtime已开启，否则配置报错而非悄悄降级。

worker CLI：`python -m app.assistant_worker`；`--once`完成一次领取/分发循环后退出。导入模块不启动worker。SQLite与Postgres初期均一个执行槽，运行健康只报告实例身份、心跳、队列数、错误分类，不报告个人业务内容。

健康信息复用现有AppMetadata，不加领域表：键前缀`assistant_runtime_worker:`加本worker的32字符UUID hex，总长57字符、不超过原String(60)；值仅保存心跳时间、源码指纹、实例安全标识和错误分类，每20秒短事务更新。`--health`只读聚合60秒内有效心跳、队列数及Run最近完成时间，输出不得含DB URL或个人资料；只清理该预留前缀7日前过期项。健康写入失败不能改原业务结果。Web不公开无鉴权个人队列信息。

Windows预览在`local_preview.configure()`后用相同worker核心，复用同实例路径与数据库；不改变原日报关闭状态，不从仓库.env偷换配置。Linux独立服务与Web共享经过确认的部署配置。关机休眠不承诺运行，重启按数据库记录恢复。

迁移只在合成库/获授权升级副本执行。先检验h52j含历史会话/卡/计划的副本升级、外键与原业务行指纹，再做备份恢复。本文不授权触碰现有公司/预览库。回退只关新功能，不降级删除表、不撤销已成功业务。

## I. 测试位置和实施顺序规则

测试环境根按本轮用户批准固定为 NTFS 上的 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1`，原 E: 根保留历史证据；迁移按 PATCH-CP-00B-03，不改变产品存储合同。M0建立runner。runner每次把当前源码白名单镜像到外部source、设置测试数据库与附件根、再导入应用。不能直接import工作树app做“只读检查”，因为`app/db.py`导入会创建data目录。

全部新增测试、恢复的历史测试、日志、截图和合成数据库放在外部根，仓库仅保留实现代码、必要文档和迁移。没有`package.json`，不新增npm工程来凑`npm build`验收。

实施顺序由 implementation_plan 的索引决定；本轮编码依赖接受 `implemented` 或 `done`，但前项实际接口、schema 和迁移文件必须已实现。schema/迁移文件先于冻结提交实现，后台接口先于 UI，具体领域适配先于该链真实模型验收；迁移执行与其它纯验证任务后移。每项只允许列出的生产文件及本项记录修改，外部测试和 runner 工作留待集中测试阶段。纯测试项不因交接而记为 implemented/done，其验收清单完整保留。

架构冲突必须停下报告，不靠兼容“兜底”放宽原权限、状态和事实守卫。原实体新需求或原API缺少必要能力须明确报告，而不是在adapter里直接写表。
