# PATCH-M5-5-01：MCP 的真实工具检查点与兼容事务

2026-09-28，配套 M5.5。依据用户持续范围授权登记后实施，不再重复申请。现有 MCP 只有 busy token，没有请求摘要或持久工具成果；不能把工具请求伪造为模型回复，也不能让旧 handler 提前提交后再补检查点。

## 精确补充范围

- 新增 `app/assistant_runtime_mcp.py`：固定 business_v1 工具请求的无模型执行入口。真实 MCP 来源封套、完整请求摘要、准备 manifest、原返回结构投影；复用 runner 的 WorkItem/卡原语和 queue 的 lease/fence，不建另一套业务状态机。
- `app/assistant_runtime_runner.py`：在任何上下文或 provider 工作前识别真实 MCP Run，分派同一无模型入口；仅必要的准备兼容原语扩展。不得伪造 model RunItem、用户消息或 ContextSnapshot。
- `app/business_assistant_workboard.py`：拆分既有 schema 1 计划的只读解析与 flush-only 保存，保留原校验、版本和返回合同；原 save_plan 仍拥有旧事务。
- `app/assistant_runtime_plans.py`：仅允许已验证、未绑定事项的真实 MCP Run 保存员工明确指定的 v2 计划，仍按原 Plan/version/引用守卫；不把 MCP Run 绑定为跟进继续来源，不放宽普通 Runtime 的计划绑定约束。
- 原允许的 `business_assistant_api.py`、`assistant_runtime_queue.py`、`assistant_runtime_registry.py`：真实登录工具入口、完整规范参数摘要、固定 `mcp:<session>:<request>` 来源、定向领取及安全恢复判定。MCP Run 保持未绑定 Plan，不能解除既有跟进阻断。

## 固定合同

Runtime 关闭时保留新请求的原 MCP 兼容路径，不依赖新表或放开 Runtime 身份守卫。为防止关闭开关后重放已接纳请求，旧路径前增加只读保护：先核真实登录和当前会话，检查 Run 表是否存在；存在同 owner/store/session/固定请求键的旧 Run 则返回 503、accepted=true 和原 run_id，提示读取原记录，不能再进入 legacy 写入。无表或无该请求才沿原路径；检测/查询失败不当作无记录，不发行 RuntimePrincipal/Grant、不写表。开启后，同请求号不同完整参数返回 409；相同请求只恢复真实成果，纯查询按当前权限重读，不持久保存原始查询结果。请求身份与每次 lease/fence 分开；旧请求不能晚写或释放新租约。

新请求在持会话锁时发现 live busy 或同会话未收尾 running Run，必须在写入新 Run 前返回 409。已接纳后的领取竞争保留原 Run；处理中响应明确 `accepted:true` 和 `run_id`，不能让员工误认为未接纳而更换编号。MCP 定向领取先遵守原全局候选优先级，首候选不是本请求则等待，不能跳过更高优先级用户请求或领取邻项。

卡、计划、问题记录与各自完成检查点同一受 fence 保护的事务。完整批量输入先保存；只恢复未完成准备，不重新创建已有、终态或结果不明卡。旧单卡和两种批量返回字段按真实结果投影，不返回内部摘要冒充旧工具结果。原内容去重和 M2 行意图的差异必须显式解决并源码审阅，不能悄悄多造卡。

去重兼容的固定实现：MCP 工具封套先持久保存完整原输入、全部行的稳定 UUID 和顺序。每行在 fence 事务内沿原 builder 判定已有活跃卡；真实复用只记兼容卡引用，不转绑旧 WorkItem 或制造假 WorkItem。确需新卡才为该真实行建立单行 M2 manifest，复用既有 WorkItem/卡原语，再在完整 MCP 封套中记录映射。恢复逐行验证真实来源；普通模型/M2 恢复路径不接受该封套，普通等值独立行语义不变。

worker 只能沿固定 MCP 分支恢复该来源，模型调用为零；不得创建 Grant、确认业务或执行任意代码/SQL/URL。超时保留可查询的真实成果并说明未完成。原工具目录和 ToolCall 字段不变，无新迁移或新功能开关。

旧 v1 Plan 的新建/更新在同一保存事务调用现有 Plan 信号 helper；复用不发新信号，门禁仍由原 Runtime/通知开关决定，不另启用后台行为。

当前只做编码、源码审阅、AST/UTF-8/指纹核对，运行验收移交 DeepSeek，不启动进程、访问数据库或联网。
