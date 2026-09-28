# PATCH-M4-5-02：新计划绑定前历史成果的队列恢复接线

日期：2026-09-28。适用计划：R4-20260928，M4.5。授权：用户已明确“批准，后续授权不用再问我，都默认允许”；按已审阅精确补丁实施，完成静态复核后登记结果。PATCH-M4-5-01 的 service/plans 授权仍有效，本补丁只增加一个生产文件。下文草案审阅事实保留为应用前历史，不再构成等待授权门禁。

## 已核实的触发与影响

同一个未绑定事项的 Run 先完成原授权 GET 或准备卡片，随后在另一个完整工具片段创建并绑定新 Plan。旧 WorkItem/manifest 的 plan_id 必须保留 null，不能为匹配新 Plan 改写历史归属。

runner 已实现对本 Run 已完成历史成果的只读恢复，但队列 assistant_runtime_queue._safe_retry 仍要求全部 manifest 的 plan_id/goal_version 和全部 WorkItem.plan_id 等于当前 Run。此 Run 租约过期后，reclaim_expired 会先将其判为 failed，无法到达 runner 的恢复接口。可直接从当前队列第 712–714、739–741、954–955 行核实；属于恢复判定接线缺口，不是业务权限变化，也不是测试失败推断。

不能通过禁止正常的“先查询或准备、再建立计划”、修改旧 WorkItem 归属、放宽所有空 plan_id，或把该缺口写成已验收来解决。

## 申请的唯一额外生产范围

只允许修改 app/assistant_runtime_queue.py 的 _safe_retry 及其必要的本文件私有只读判定 helper。不改 claim、租约时长、fence、重试次数/退避、reclaim_expired 的授权与状态转换、release 的权限守卫、数据库模型/迁移或任何业务 API。

在原 _safe_retry 的严格相等路径之外，仅接纳满足以下全部条件的历史例外：

1. 当前 Run 已真实绑定其本人、原门店、原会话的新 Plan；Plan.request_id 等于 runtime_busy_token(run.id)，engine_version=2，Plan 当前 goal_version 与 Run 一致。此关系由实际数据库行证明，不能接受模型提供的标志或运行时伪 principal。
2. 历史 manifest 必须属于这个实际 Run，scope 的 owner/store/session/role/access_version 与真实 Run/会话一致，plan_id/step_id/goal_version 均为 null。manifest 必须已完整准备成功；不可只因状态字符串成功而跳过全行校验。
3. 由这个 Run 的完整 runtime_model_tools/runtime_tool 记录及稳定 item_key、call_id、model_item_id、manifest_id、input_item_id 核对父工具/批量子行；每一有效最新项均已成功，完整行集合和输入摘要一致。只有这些确证的原 WorkItem ID 才能进入“历史已完成”集合。
4. 历史准备 WorkItem 必须仍属于原本人/门店/会话、plan_id/step_id 均为空，原 input_item_id/intent 与完整 manifest 对应，真实原卡仍由 source_work_item_id 指向它。不得为它创建新卡、重准备、改属或把成功准备当作业务完成。
5. 历史 read WorkItem 必须由本 Run 的实际已成功最新 read attempt 引用，item_kind=read、status=settled，plan_id/step_id 均为空；工具为真实已验证 read_data，operation_id/path_args/query/body 与持久的固定 GET 意图一致。未完成读取不能借此例外恢复成新计划步骤。
6. 原 _safe_retry 对角色/来源、已 supersede 意图、缺卡、卡过期、失败/取消/未知、executing/uncertain 确认以及当前合法待准备项的拒绝全部保留。历史卡仍必须满足原允许的 pending/succeeded 和未过期规则；不能在此查询回执或发送任何网络请求。
7. 该 helper 只读且失败关闭：任一来源缺失、JSON/关联不一致或无法证明历史已完成都返回不允许自动重试。不能签发 RuntimePrincipal、移除身份条件、修改记录来“修好”历史，也不能调用需活租约的 runner 执行函数；恢复器此时可能正在处理过期租约。

## 状态及异常路径

- 上述历史例外通过，并且原权限/目标/重试额度等条件全部通过：沿用原 running → queued → 重新领取流程，原已成功工具只回显真实引用。
- 存在尚未完成的原无计划准备/读取、未知确认、过期卡或证据缺失：沿用原 failed/人工核对路径，不重放业务。
- 目标改变、撤权、暂停/撤销或用户停止：沿用原取消规则，历史例外不得将其改成可继续。
- 旧 worker 晚回：原 fence、租约与提交守卫不变。本补丁不授权自动确认、跨店查询或修改原业务状态。

## 审阅与验证边界

授权后由作者和独立审阅者检查实际队列 → reclaim → runner 恢复调用链，核对严格来源及拒绝路径；执行 AST/UTF-8/静态符号检查，记录最终源码指纹，补入 M4.5 执行记录。仍只有 M4.5 一项在实施，不把前三个文件落盘写成整项完成。

按用户 R4 决定，本轮不新增、修改或运行测试，不导入 app，不访问数据库或调用模型。集中验证待办增加：先成功纯读/准备后建计划的过期租约恢复；完整批量不重复成卡；未完成旧读取、未知/过期/失败原卡仍拒绝；伪造别的 Run/Plan/门店、缺行和混杂 intent 均拒绝；原队列权限/fence/退避/事务回归。

本补丁不授权其他生产文件、测试执行器、功能开关启用、生产部署或外部服务调用。未授权前 queue 保持原状。

## 可审阅的代码草案（尚未应用）

对应 unified diff 已保存为 `docs/implementation-patches/PATCH-M4-5-02.patch`。2026-09-28 经作者、root 和独立审阅，草案仅调整 `_safe_retry` 并新增 `_retry_model_frame`、`_completed_unbound_history` 两个只读辅助函数。按完整同 Run/同 item_key 的最大 attempt_no 核对最新读取，原 GET 参数 body 必须为空；没有跳过旧错误分类的例外。

历史例外限当前 Runtime 确实能产生的 intent_version=1、无 carry/previous manifest/supersedes 的完整成功来源。不能完整证明的旧 M2 重准备记录失败关闭；当前 Plan 严格相等的既有路径及其全部原守卫保持。数据库读取故障继续抛出回滚，不误记为永久不可重试。

| 对象 | SHA-256 |
| --- | --- |
| 原 queue 文件（尚未修改） | c1d5265d74ea63287b38ab8e88eb35bbedfa2e2338bb9b73804fabb9d6ea6c3d |
| 代码补丁 | 7ce0e46660b9443ae1ea55c1e146066ae674726956d74cba4aee10da293d2af2 |
| 内存中应用后的候选 | b0fa3b811d12bdb434541cc958033b71522624bcab8b91f24f4776af797ee60c |

静态核对：`git apply --check docs/implementation-patches/PATCH-M4-5-02.patch` 退出 0；外部 Python `-I -B` 仅在内存重建候选、解析 AST 和比较改动范围，退出 0。所有其他已有函数 AST 不变，生产 queue 原始字节不变。未执行候选代码、导入 app、运行测试、访问数据库或联网模型。这些证据只证明草案可应用且静态范围符合约定，不表示授权、运行验收或 M4.5 完成。

## 授权后应用记录

用户2026-09-28明确批准后，root执行原精确补丁；应用后queue SHA-256为`b0fa3b811d12bdb434541cc958033b71522624bcab8b91f24f4776af797ee60c`，与上述候选一致，AST/UTF-8/无U+FFFD静态复核退出0。M4.5代码审阅收尾见`docs/implementation-checkpoints/M4-5-review-v3.md`，状态只在正式计划中维护。后续M4.6另有补丁范围，不能用本指纹代表后续改动后的文件。
