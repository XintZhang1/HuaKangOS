# PATCH-M4-5-01：Runtime 工具接入的最小接口补齐

日期：2026-09-28。适用计划：R4-20260928，M4.5。用户已明确答复“允许按该补丁扩展两处并继续实施（推荐）”，仅按下述范围执行。授权不等于实现或验收完成；里程碑状态仍只在 implementation_plan.md 维护。

## 已核实的问题

M4.5 只允许修改 app/assistant_runtime_runner.py，但依赖的旧工具并非全部是无提交的 helper：

1. business_assistant_service._run_registered_tool 的 inspect_operation 更新 Session.recent_operation_ids 并提交。read_data 在原 GET 前提交，查询失败时又调用会提交的 record_issue。business/case 复合查询及 resolve_only 准备函数内部仍会经过这条 read_data 路径。
2. assistant_runtime_plans.save_plan 完成原 GET 后自行更新并提交 Plan/Step；没有接受 Runtime 的 Run/fence 检查点事务。提前锁 Run 再调用它会跨网络持写事务；等它提交后再检查 fence 又无法阻止过期 worker 先写计划。
3. 新计划还需与创建它的实际 Run 建立关联，更新 principal 后继续。当前独立 save_plan 与 bind_run_plan 分两次提交，必须明确中间恢复路径，不能让事件或后续步骤借用未绑定身份。

registry 的 read 分类及 resolve_only 参数都不等于“任意旧 handler 无助手写入”。不能靠全局 monkeypatch、Session 提交拦截或复制整套业务表单规则掩盖这个缺口。

## 已授权扩展的文件与边界

在 M4.5 原 app/assistant_runtime_runner.py 范围之外，仅增加以下两处：

- app/business_assistant_service.py：为服务器签发、重新校验的 RuntimePrincipal 增加明确的内部工具分派接线，使复合工具内部 read_data 走受原授权保护的固定 GET，读取期间不自动记录/提交助手 issue。需要的助手元数据统一在 runner 的短事务检查点保存。普通员工旧对话、MCP 和原确认入口保持原路径、签名及行为。不能只用普通 HTTP 标头或任意字典决定走 Runtime 分支。
- app/assistant_runtime_plans.py：把现有计划保存的读取校验与写入阶段拆成可复用的服务器内部接口，沿用原 schema、DAG、来源核验、保护已执行步骤、版本守卫及目标变化处理。原 save_plan 仍可按原合同调用并提交；Runtime 调用方在全部原 GET 完成后取得 Run/fence，原子保存 Plan/Step、必要 Run 关联、工具结果和最小事件，提交前再次核对权限。仅为 Runtime 提供必要的事务接入点，不另建计划规则。

同一 plans 接口还须补齐已接受批量的续办证明：当前整步 awaiting_confirmation 会阻止同一完整 manifest 中因预算或容量未处理的原行。只为真实 batch 中仍无卡的 pending 原行判定 resume_batch；兼容单卡及已有卡不在其内。原业务完成判断、原 blocking_rows、依赖和实际 preparation 条件全部保留，不因“已有部分待确认卡”把整步视为完成。一次性条件凭据在锁后核对完整来源快照，再返回当前 manifest/intent 下真实尚无卡的固定 input_item_id 集合；不重复生成行、不升级意图、不重准备失败或过期卡。

新内部接口由服务器代码调用，不能进入模型工具 JSON、HTTP 请求体或 MCP 工具清单。若确需第三个生产文件或改变原模型/schema/业务规则，另行报告，不扩大本补丁。

## 状态与失败路径

- 完整工具先验证并持久化；读取和准备解析阶段不持有写事务，不把任何新卡或计划写入交给旧 handler 自行提交。
- 读取失败保留服务器真实拒绝及逐项结果，不能解释成没有记录；待持久的安全 issue/元数据由实际有效 Run 在检查点保存。
- 新计划只绑定创建它的同本人、同门店、同会话 Run；不修改原用户请求摘要，不允许重绑别的事项。绑定后重新签发身份，不能复用旧 principal。
- 结构变化保留原 goal_version 增量、Grant 暂停与旧 Run 停止语义；不能为登记本次工具结果放宽旧目标授权。该写入所需的控制收尾必须最小化，不为旧 worker 开放额外准备权限。
- 写回前后任一版本、权限、lease、fence 或停止守卫失败：回滚本次助手事务，不回滚或重放原业务。完成卡/WorkItem 的业务语义与原人工确认入口不变。
- 重启按实际已保存 Plan/Step/RunItem/WorkItem/Proposal 恢复；不能为同一完整意图生成新行 ID，也不能因结果未知发业务 POST。

## 审阅与集中验证

授权后仍只有 M4.5 一项 in_progress。作者、root 与独立审阅者核对旧/新接口调用链、事务边界、新计划绑定与改目标停止路径；保存源码指纹和实施记录，测试按用户 R4 决定后移。

后续集中验证增加：旧对话/MCP/确认路径兼容，复合查询成功和拒绝不发生无 fence 助手写入，读取阶段无写锁，过期 worker 保存计划被拒，计划保存/Run 关联/工具事件同事务故障回滚，新计划恢复不重复，改目标停止自己后的最小收尾，全部原 Plan/DAG/权限/版本守卫回归。原 M4.5 全部验收条件保留。

本补丁不授权修改测试执行器、模型联网、数据库迁移、业务状态机、权限结构、生产开关或部署。
