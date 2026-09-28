# M4.5 中间编码审阅 v1

日期：2026-09-28。计划 R4-20260928。此报告仅保存本项审阅事实，不替代 implementation_plan.md 的状态或 CP-09 门禁；M4.5 尚未完成，M4.6 未开始。

## 已实现与审阅

- 完整工具列表、原批量行、稳定 manifest、父/子 RunItem 在首项执行前同事务保存。不持久化模型推理或半截 JSON。
- Runtime 读取使用真实签发身份及原授权 GET；旧工具里的 metadata/issue 自行提交不会进入 Runtime 读取链。查询、卡片准备、计划保存分别走固定事务路径，没有业务确认 POST。
- 每项 running 先落检查点，再查询；原授权、当前 goal、租约和 fence 在助手写回前重验。结果只保存必要引用；批量保留原行，缺项/失败/未知不自动重准备。
- 计划保存拆为读取和无提交持久化接口；旧 save_plan 仍保持原提交行为。Runtime 原子保存 Plan/Step、Run 绑定、工具结果和事件。结构变化保留旧 Run 停止及 Grant 暂停；不能将旧执行升级到新目标继续。
- 恢复成功项只回显原记录。纯读中断的旧 attempt 明确收尾，再创建新 attempt；真实 User 承接原回执读取守卫，查询通道仍绑定原 principal，未知确认不重放。
- 已修源码审阅发现的批量 shared 参数遗漏、复用前错误检查 readiness、metadata 敏感标识、缺当前单店范围、原业务批量 action 禁令遗漏及成功项竞争重执行问题。
- 同 Run 先准备后创建计划时，历史成果保持原空 plan_id；只允许完整成功、真实来源一致的原记录只读恢复。首次绑定仍拒未完成旧准备/读取和当前 executing/uncertain 卡。
- 查询 WorkItem 不凭“同 Case、无 form_ref”猜测业务步骤类型；当前查询成功只表示 read WorkItem settled，不会把空 completion_conditions 的付款/交付等待步骤标完成。明确只读步骤的能力不能以对象相同代替真实契约。

## 未完成的集成问题

队列 _safe_retry 仍要求历史 manifest/WorkItem 的 plan_id 与后来绑定的 Run 一致。因此合法的先完成查询/准备、再建计划序列在租约过期后会先被队列终止，无法进入 runner 的恢复逻辑。

补丁 PATCH-M4-5-02 已列明一个文件、只读判定及完整来源核验范围，并请求用户授权。未得到授权前不改 queue，不把本项标 implemented，不进入 M4.6。不能用延期测试掩盖已知源码集成缺口。

## 指纹及证据边界

| 文件 | SHA-256 |
| --- | --- |
| app/assistant_runtime_runner.py | e7d85d5e7b46f29ef808b8d0354f6c32aa2f89dc70128e64f6a4797a3f867b9e |
| app/assistant_runtime_plans.py | 66d4ca0026cc16639f2d211c3f92f281a53fcb95b81d66114954eae35dba2123 |
| app/business_assistant_service.py | defeea409b8671a7137551dc26e401555720d6ac603a296f41ec7c0c7c79bd42 |

作者、root 与独立代理完成源码复核。外部 Python 的 -I -B 标准库脚本仅做 AST、UTF-8、U+FFFD 和本地相对导入符号检查，退出 0；不导入 app。未运行测试、访问数据库、迁移或联网模型。无本批服务/验证后台句柄，四个功能开关保持默认关闭。

集中验证保留原 M4.5 全部验收，并补旧对话/MCP/计划兼容、跨事务权限与 lease/fence 变化、所有提交前后中断、批量半完成和容量恢复、新 Plan 绑定前成果、旧 read attempt 收尾、未知回执、同对象业务等待不得误完成等路径。静态审阅不等于运行或业务验收。
