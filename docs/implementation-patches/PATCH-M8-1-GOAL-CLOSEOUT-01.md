# PATCH-M8-1-GOAL-CLOSEOUT-01

2026-10-03，仍为当前 M8.1 表13。仅新增 `tests/browser_click/runtime_goal_closeout.py` 和独立任务记录；生产 UI 的当前计划绑定由 root 单独登记与修改。本脚本要求真正原 UI 发送已有计划的 goal 修改，实际 Run 必须绑定本人同会话原 Plan/旧 goal_version；没有接线时明确失败，不能以另建 Plan 或直接 API 修改代替。

原 UI 创建两原接待并保存依赖事项，明确开启 Grant、准备唯一首卡；在首卡尚未办理且原事项 active 时，用原输入框修改目标。合成 provider 仅返回 `save_work_plan`，保存时的真实 RuntimeContext 与原 PlanStep 只读记录提供精确 expected_version 和不变完整步骤。要求同一个 Plan 的 goal_version 增一、当前修改 Run 保留旧 goal_version 并实际停止，旧 Grant 被暂停为 goal_changed，原卡、WorkItem、历史消息和 ContextSnapshot 保留。原 UI 刷新核对新目标后，本人显式 resume；要求旧 Grant 真实 revoked、新增唯一新 goal_version Grant，后台实际原 GET 核查仍无替代首卡或自动办理原单。此场景覆盖旧目标在途修改 Run 停止，不把历史完成 Run 改写为取消，也不主张多 worker 并发迟到准备已由此验证。

场景在 root 全新镜像集成并动态运行前仅为待验证；所有模型响应仍为阻止外网的合成内容，不读真实凭据，不改钟、原授权期限或业务事实。

2026-10-03 `closeout-contracts-03` 原失败保留后的装置修正：场景发送disabled为共用首卡装置在原准备Run终态前refresh，现由followup helper先核真实卡↔Run映射、Run成功及原worker tick再刷新。goal provider的完整步骤重送同时移除实际规范化PlanStep schema中不存在的case_id，使用真实object_ref/form_ref；保留原tool succeeded/nullerror、plan.updated、真实POST plan_id、旧goal停和本人resume新Grant断言。尚待新镜像复验。
