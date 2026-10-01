# Runtime Worker 短事务与占位回收只读诊断

## 追加：PDI 独立原车源静态复审

2026-10-02，full15 原失败保留。冻结 full15 脚本 `sales_pdi_business.py` SHA256 `a211396508efed492c58947934c14395c4cf1c8901a9f5004f38bd410d6ff748`，当前候选 `f5b0caebaec7266c9b6145d6fcaaa5603a6dd904af72da8d018554c0a896d21b`；标准库 AST 与逐行差异审，无 app/browser/SQL 执行。旧 car74 的 approval_state 已由 approved 变 void 是根任务同轮只读事实，不能再当可用库存；历史采购成本、代次、退订原单、净款零与旧原件仍核对。

候选仅在原 PDI 脚本复用 `receivables_business.vehicle_precondition`（410–518），不复制流程或变更注册顺序／生产／runner。参数取同轮 HK171 供应商、HK177 已发布车型、HK178 整车仓与库位及原实款账户；当前 active/version/本店/仓型关联有显式校验。helper 使用同店真实库管、主管与财务原 UI，独立采购一台、核价／请款、实际付款 8000 分、发运与验收；唯一原 Receipt/Movement、VIN 身份／Custody／代次／成本 guard 保留。该 helper 不消费 cp_adapter。`VP.vehicle_fact` 返回 vehicle、position、custody、position_entry、identity_link；候选补 original_position=position，PDI 后续 physical／配车／检查／发车／签回消费键满足，无 source['receipt'] 消费。原销售报价 13000000 分保持，出库成本来自新采购 purchase_cost_cents，原件及新采购 case/native 全部入报告。新车仍须 approved，S.physical 对当前 approval/cost/generation/位置／权属／占用守卫保持。独立静态未见启动硬阻断；full16 已启动不等于通过，本段没有动态验收结论。

2026-10-02。独立读取当前源码与 `automatic-business14/source` 冻结副本、原有限日志；不执行应用、浏览器、测试或 SQL，不读取凭据／配置，不修改生产／测试。本文与根任务、A 的源码报告分工，不改计划或实施记录。

## 第 14 轮事实和归因边界

根任务及并行只读审提供的同轮合成库时序：slowlogout 原 Run `f7dac58b…` 在 UTC 16:44:29.333682 开始，16:45:59.491383 取消，error=`permission_denied`，间隔 90.1577 秒；其 limits 已配置、rounds 和 items 为空，事件仅 queued／started／cancelled。protocol 排队后至 16:45:59.504 才开始，native 至 16:45:59.696 才开始，符合单槽占位直到旧 lease 回收。该 cancelled/error 与 `reclaim_expired` 授权失效维护分支吻合，不是 runner 正常控制收尾的固定 precondition_conflict 结果。本审不自行查询数据库，也不把别的轮次拼入该事实。

运行中先观察三条 SQL code 5；终局 `server.log` 为七条，缺少时间、线程、表及调用栈。不能把七行逐项归因业务请求，也不能把 90 秒定性为三次 30 秒等待。根任务记录终局 CLI 3、18 执行／16 通过／2 失败，原失败保留。

## 实际维护／占位调用链

以下四个生产文件与第 14 轮冻结副本原字节相等后审阅：worker SHA `59e6d51d389c03137e8073667ff7feaa1130938cb501b9b7b8074d71304bdc26`；queue `7953ca68f54cea9e76e45b92eb37bd1ee6f2b3a01c55c26541f34ea9aa013e7c`；runner `2269ec8fb0957d8f3f45b296470f7b21904c31b449097010418fedb1599a099c`；principal `797cb91f13436e6aa84796fe75cd521070adb37335095b727704c3d9d9ac0eef`。

- `assistant_worker.beat`（原 206–219）及 `beat_cleanup`（222–245）每次独立 fresh factory Session。原首读 AppMetadata 后更新／删除、commit，存在 SQLite 读升写窗口；仅改自己保留前缀的元数据。
- `_recover`（467–471）、`_claim`（473–477）、`_execute`（479–482）各用独立 fresh Session，不共享 Web Session。recover／claim 关闭后才进入 runner 自己的工作 Session。
- 原 queue `_claim_queued_run`（565–625）通过 `_slot_lock`（541–550）在首 SQL 预占 SQLite writer（固定 false UPDATE），然后查询单槽／候选，commit 后发 principal。claim 已有该保护，不能归为其首读升写。
- 原 `reclaim_expired`（1988–2040）先关闭独立只读候选／授权 reader，再在 main Session `_lock_rows` 读取，CAS 修改 Run／Session、释放 busy、追加事件并提交；原 main 首读升写窗口可静态确认。单次只恢复一项，授权／版本／lease 和退避守卫保留。
- 原 `heartbeat`（628–644）在独立 Session 查询 `_lock_rows` 后续 lease CAS；runner `_RunHeartbeat._loop`（1890–1902）持同原 Engine 创建独立 Session，每 20 秒调用它。worker `_beat_loop`（453–464）也在本 Worker loop 同步执行元数据 beat。
- `tick`（493–544）在 runner 异常时记录 error、关闭 execution Session，并尝试元数据 beat；不会在 worker 外层擅自释放 Run。runner 正常终局或原到期 reclaim 负责占位释放。`_serve` 的进度循环未新增业务提交。

上述同步 SQL 与 Worker runner／取消协程在同一 Worker asyncio loop 调度；SQLite 30 秒 busy 等待若实际发生，可能阻止该 loop 的取消／heartbeat 协程及时调度。仅“干净只读事务跨 await”不足以证明占 writer，更不能证明本次七条 code 5 来自其中某函数；新有限标签观察才能进一步定位。

## 有限诊断日志源码复审

`launches/runtime-lock-observation-before-20261002.py` SHA `9f56a87feed40e4c81aff5c3b5b95f88e007201aea3af747cb0835ff1f3eb9d1` 与第 14 轮 `scripts/fixture_server.py` 原字节相等。当前 fixture SHA `526f9faf6b0ecd793517b8982a148ad180f6c47894633a45392acfd19e393175`，AST 解析通过；唯一差异是原 error listener 输出段追加 UTC／线程整数和有限 SQL 标签。

statement 只在内存中取有限 verb（SELECT／INSERT／UPDATE／DELETE／BEGIN／COMMIT，其余 other）及六个固定表标签（runs／run_events／run_items／sessions／app_metadata／login_sessions，其余 other）。不输出 statement、参数、异常 message、业务正文或密码；原执行、断言、25 秒期限和失败语义不变。本审未运行该观察候选。根任务报告五轮旧退出诊断未复现，但启动后 helper 字节变更，因此只保留诊断事实，不计正式冻结通过，不以重复运行求绿。

## 六个短 writer 实际补丁边界

对 [PATCH-M8-1-RUNTIME-SHORT-WRITERS-01](../../implementation-patches/PATCH-M8-1-RUNTIME-SHORT-WRITERS-01.md) 已落生产差异做独立语义复审（精确全文件逆字节／测试差异由 A 单独负责）：

`assistant_worker.py` 当前 SHA `94c5b0d814bc3ae3112959e58fdd4fb74dede6307a8206b48673d0e55c491fdc`。仅必要导入，以及 beat／beat_cleanup 自己 fresh Session 首个 AppMetadata read 前调用 `get_write_db(db)`。两者无 RuntimePrincipal、独立 reader 或 await；OptionEngine 只属于该 own Session，退出即关闭，不传入 runner，PostgreSQL沿用原事务。

`assistant_runtime_queue.py` 当前 SHA `49f8195d3d5847812e962028df02b653d5caf6c59112785296c458a1523530f6`。新增私有 `_sqlite_writer`，仅 SQLite `_clean` → 回滚干净原读事务 → 复用原 `_slot_lock` 固定 false UPDATE；在 heartbeat／lock_for_write／release／reclaim_expired 原授权 guard 后、main `_lock_rows` 前调用。`_clean` 沿原合同拒绝 new／dirty／deleted 或活跃 preparation transaction，不默默丢弃半成卡／事件。该 helper 不替换 Engine；principal 的 `_bind` 恒等守卫、独立 `_reader` 同原 Engine 及其 fresh／no-dirty 要求保持，避免 reader 继承写选项争自己的锁。

四个 queue 短写本身无模型／原业务 GET／await，原授权再验、单槽、CAS、fence、lease、回收、重试档位、提交和异常回滚均保持。不是对 Runtime 所有读取事务或普通 helper 的泛化，也不加失败重放、加长超时、启用默认开关或改 PG。

独立静态审未见此范围的硬问题。已明确的 SQLite 读升写窗口可以作为独立并发缺陷精确修复；五轮未复现不证明窗口不存在。该判断不声称已定位第 14 轮具体锁因，也不把源码审或诊断记作业务通过。后续必须由同指纹 fresh 原点击验证实际终态、lease／busy 清理、旧业务保持及未泄漏日志。

main refusal 的独立两行字节／AST复审与原业务 rollback 先释放结论见 [HK188 拒绝证据诊断](member-points-current-diagnosis.md)。

## 第 16 轮 HK071 原源位不足与精确采购接线复审

2026-10-02，仅本轮 `automatic-business16/evidence/inventory-store-scope-hk071/business-checkpoint.json` 原件与当前两脚本静态核对；未执行 SQL／app／浏览器或 helper。终局 53 执行／52 通过／1 失败，原 `sufficient` 拒绝保留。

原 `initial_local_nonempty` 的 item9 总量／可用为 2250、reserved0；source location2/balance1 仅 250/value250，destination location3 为 2000，在途 balance3 为零。`availability_components` 的 retail/addon/holds/transit/approved_return/count 均零。主档原源位不足 500 已由真实原单消费确证，不需猜生产错误，也不把失败提示中的“盘点围栏”自动定性为实际围栏。

balance1 不可变流水按原证据合计正好 250：采购94入3000+5000；盘点95增500；采购94退1000；移库96出2000（在途后完整收到location3）；盘点97减250；维修100净领1250；组合零售135出1000；会员价格零售164出1000；维修179出1000；跨店185出1000、退250。这些都是本轮原自动证据，不是本审独立数据库读取。不能移动场景、改源位／500数量、删当前守卫或回写余额规避。

根任务先登记 PATCH-M8-4-INVENTORY-ACTUAL-PURCHASE-01，后仅修改 `inventory_scope_business.py` 及 AR helper 两句单位文案。本审逐 diff／AST 核：库存脚本原 full16 SHA `2b5458d2cd5ae6790a377faeda3cc5dd43e330bb8408c48b6b1325a451820a2f` → 当前 `2fbf63ef0c0d59b2b641967c5333317062e650ef60208d6b204eefe8aab654fe`，仅 sources／inventory_scope_business 两个函数 AST 改动、必要 import／文档字串／同轮 helper 指纹；AR 原 `7386ada44c8e9ceb6765d4ba614cda21813a80f73dc18e43eba59d68ca25cbac` → 当前 `c08beefbfb92492448042feed9794e3fcf77678031ce0f4ebfb01e3ecee9e76e`，仅 material_precondition 两句单位文案，其他函数／类 AST 原样。

当前 sources 从原 Material source_preconditions 取得 supplier2/version2、account1、warehouse2/location2，读当前原行核同店active／供应商version／银行type／仓位关系；原账户来源投影没有 version，不能宣称它与父旧账户version完全相等。原 private src.account 只供员工凭据，purchase_account 另为真实银行行。调用 AR.material_precondition 的 signature 为 `(e, context, credentials, fixture, item, supplier, warehouse, location, account, token)`；传本店 vehicle_purchase 原 fixture 的 manager12／finance15／inventory14，直接沿原 Item9/warehouse2/location2，未调用 AR.sources 换为精品 Item13。

主流程始终实际采购1000、独立管理批准、财务实付1000、仓管原位入库1000，保存完整 necessary_original_ui_material_purchase 后取实际 current_stock.item；随后仍调用原 sufficient，再原员工登录／改权／查询／移库500及后续数量成本保护。不是库存不足时静默 fallback。AR 原完整输入摘要、同单回执、独立批准、现金／账户／原位增量、唯一receipt、财务本人原 GET 金额及库管不泄财务投影守卫保持；输入 reason 与 expected 同变量，单位文案适用于原“升”。原 AMOUNT500、两位关系、成本、holds/count/transit 与权限恢复均未改。

该范围静态未见可执行硬阻断，可进入同指纹 fresh 原点击验证；不是业务 passed。第 17 轮实际成绩独立记录，不能继承第 16 轮其他父场景或代表图。
