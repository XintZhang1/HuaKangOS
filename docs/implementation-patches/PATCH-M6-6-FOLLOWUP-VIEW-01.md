# PATCH-M6-6-FOLLOWUP-VIEW-01：点击跟进动作前读取当前进度

2026-09-30 原生点击 automatic-20260930-01：开启 200，后台真实准备第一张卡后暂停 409；中间没有 GET plans。后台条件/准备会递增 plan.version，UI 仍提交开启响应中的缓存版本。原 API/CAS 拒绝是正确行为，不删除或放宽版本守卫。

M8.1 集成补丁精确范围仅 web/assistantworkspace.js 的 setFollowup：每次员工明确点击最终动作时先 GET 同一 PlanView，只有 goal_version、授权状态/原因及当前允许动作仍与已展示范围一致时，提交服务器新读的 version 一次。目标或授权发生变化则更新显示、收起二次结束确认，并请员工重新核对；不自动开启新目标，不重放 409 或未知 POST，不执行业务提交。读/写都保持当前身份、门店、事项和迟到响应守卫。

验证保持九组中的 enable → worker 准备 → pause → 员工确认前序 → worker 周期无后继 → resume → 后继准备 → revoke 的真实点击和数据库断言；失败证据不覆盖。并发发生在前置 GET 与 POST 之间仍由原 CAS 拒绝，界面读回提示，不承诺消除所有版本冲突。
