# PATCH-M4-9-01：未知结果恢复与跟进核查接线

2026-09-28，M4.9。根据用户持续授权登记。原范围receipts、runner恢复入口和service结果映射保持；增加outbox中在条件求值前调用固定恢复入口，解决未知卡阻止入队后无法由Run自己恢复的问题。

- `app/assistant_runtime_receipts.py`保留lookup_receipt完全只读；新增独立协调函数。读取真实冻结confirmation及原receipt，由原actor/store/digest与当前GET可见性证明结果；全部外部读取结束后才进入短事务。不能接受客户端传入成功结果或自由request_id/表名/actor。
- 领取Run的协调写入必须先通过原queue.lock_for_write/fence。无Run后台协调只能用真实active Grant probe，限定当前goal下完整当前manifest/合法carry_forward或明确单卡关联，独立一次性完整来源证明及Session→Plan→控制/卡/WorkItem顺序锁；仅修复已有确认记录，不创建卡、模型Run或原业务记录。
- confirmed_success才把原Proposal、冻结confirmation结果与对应WorkItem记录为确证结果，在同事务追加typed回执证据及原proposal结果WakeEvent。冻结snapshot/digest不覆盖；Step保留真实证据后由原有限条件重读决定完成，不能把“原命令成功”当整个业务完成。
- not_found/unsupported/mismatch不重发、不制造失败重试许可；仍未确定的状态与原证据保留。inaccessible不返回旧内容。读接口继续只展示ReceiptLookup，后台协调函数才有上述固定助手恢复副作用。
- `app/assistant_runtime_outbox.py`只补在所有本轮FollowupCheck签发之前调用当前授权Plan的固定确认核对服务；恢复有自己的短事务，再重新读新版本签发核查凭据，避免本轮凭据自冲突。一个Plan只处理真实当前关联卡，不查别人的私聊。Run恢复入口同样先核对再重新读取工具/卡结果，不使用协调前的旧内存观察。
- `app/business_assistant_service.py`只增加共用的有限结果映射，保留业务确认POST、事务、唯一request_id和未知结果反馈。`app/assistant_runtime_runner.py`仅改恢复接线，原provider/预算/权限/人工确认合同不变。

原生领域目前只有已登记的通用Flow回执；其他领域在对应M7适配项扩展，不猜支持。通知交M5.4，当前保留真实信号供后续分发；不伪造已通知本人。测试统一后移，原成功原API只调用一次及任意轮询不POST等条件保留。

## 源码核对后的必要补齐

原`conditions.proposal_succeeded`仅接受助手保存的原HTTP 2xx；响应丢失时只有真实receipt，不能伪造HTTP200来满足旧判断。允许`app/assistant_runtime_conditions.py`仅补此有限条件：原2xx路径保留；已协调成功卡必须有匹配冻结确认的固定回执证据，并通过共享只读resolver重新核对真实receipt与当前原对象可见性，才算原命令成功。无回执、不匹配或当前不可见仍阻止依赖。不能把任意result JSON自称成功作为证据，不放宽实体业务的独立完成条件。

`app/assistant_runtime_principal.py`仅澄清probe docstring：通用Plan保存与Run写入仍需真实Run；M4.8/M4.9固定条件/回执凭据另行控制有限助手记账，probe本身不提供通用写能力。此处不改执行逻辑。
