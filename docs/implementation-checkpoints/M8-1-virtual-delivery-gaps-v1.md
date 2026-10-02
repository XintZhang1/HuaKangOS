# M8.1 虚拟数据交付缺口审计 v1

2026-10-02，负责人 root；按业主“以达到交付标准为目标持续继续”和“真实测试暂时不考虑，先用虚拟数据尽可能优化后交付”接续。当前唯一在办仍为 M8.1。main 代码候选 bc19e56944536caa0be12738c60b7f60fc41e1a5 已推送；完整57场 CI 37000183906 正在运行，本审计不预判终局。当前生产/测试保持冻结。

本次只读核对实施计划 M8.1 的目标、故障步骤及五项完成检查，结合实际源码和57个注册场景。真实模型、公司数据、真人试用、PostgreSQL、独立部署环境及生产继续暂缓；以下是仍可用合成数据回答的原合同问题。注册入口通过不能关闭没有执行的故障窗口，开发源码包也不能替代这些证据。本表不新增业务、不修改原验收标准或状态。

| 顺序 | 原问题与仍缺证据 | 最小验证边界 |
|---|---|---|
| 1 | 重复 request_id 和真实唤醒 | 原 queue 的同请求去重及不同内容拒绝、原 emitter 的同 source/key 重复与一次分发。现 UI 丢失202后刷新恢复原Run没有第二POST。API/队列合同证据单列，不能写成页面点击。 |
| 2 | 双 worker 竞争及旧租约晚写 | 两个原 CLI 进程竞争同原Run；旧进程在写事务开始前暂停、停止心跳但仍存活，另一进程自然90秒租约及30秒退避恢复，新fence生效后释放旧进程，核原新状态、事件和busy不能被旧进程写入或释放。现先kill后重启不覆盖此窗口。 |
| 3 | 准备前、批量行边界及整组提交后中断 | 三行 _prepare_rows 共用一次 _save_preparations/_finish_write 事务；A/B/C处理或flush前后kill时本次整组回滚，先前已耐久manifest/children完整。另在三卡整组commit后kill，恢复时三原卡、Work及映射全部保持、无重复。不得虚构每行单独准备commit或拆事务。 |
| 4 | 确认冻结后、原调用前中断 | 原freeze已提交、尚未调用业务；固定边界传输失败须native调用0、卡uncertain、业务全表不变，原核对not_found。此注入不等于Web物理崩溃；Web确认进程中断另记实际执行面，准备worker kill不能代替。 |
| 5 | 原业务成功后助手结果保存失败 | 原invoke真实201已被服务观察，助手第二次结果commit失败；原业务与receipt已提交，冻结记录仍在，business_status/result_persisted及页面反馈准确，原业务不重放。现201后丢返回不是同一窗口。 |
| 6 | 可靠Flow回执及依赖恢复 | 普通员工原UI准备/确认真实flow:lead，原事务产生FlowReceipt后只丢返回。原核对confirmed_success须引用实际case/receipt并保持只读；另由原后台协调恢复原卡、confirmation及Work，再依真实事实准备后继，后继仍不自动确认。现客户Master的unsupported不覆盖它。 |
| 7 | 原回执not_found/mismatch | not_found沿第4项；mismatch可在两原页面中门控receipt内部原GET，使原确认先真实推进source版本，再放行GET，得到confirmation_source_changed。不能写SQL改receipt或伪造UUID/digest。 |
| 8 | 后端batch停止及skipped | 原UI逐张confirm不调用/proposals/batch。另以原身份、店、Cookie/CSRF运行该HTTP合同，首失败或未知后C为本次skipped、原卡不变；独立API证据不伪称原UI调用，不改前端制造覆盖。 |
| 9 | 在途撤权及原权限信号 | 原本人跟进UI revoke，或原管理员页面修改员工授权，产生实际access_version/receipt/audit/signal后释放迟到prepare响应。核无新准备、泄露及权限错误退避重放。授权修改本身的合法差异单列，零变从该commit后计算。 |
| 10 | outbox重复、乱序、分发中断与通知失败 | 原业务201后，针对实际source在原Run/notice/CAS同事务中注入固定分发失败或中断；原业务保持成功、Runtime事务回滚、event pending，原自然退避恢复唯一后继/通知，不重放业务。重复及后到event无遗漏，已读不复活、不完成任务。原各hook回滚须按source-map逐项留证，不能从一个Flow推全生产者。 |
| 11 | Grant登出继续及无变化等待 | 本人明确active Grant后登出仍能查询/准备；未开启、暂停和撤销不准备。原20次无变化tick及一次实际事实核查、一次真实变化最多一次分别记录；空poll不是已重读事实，不能只有sleep/provider计数。 |
| 12 | pending卡取消及自然过期 | 原卡取消后业务零变；按原30分钟期限自然过期，核不可确认、无自动补卡及依赖阻塞。Run stop、Runtime授权UTC过期及HK099上海Date次日各自独立，不互相替代。 |
| 13 | 旧摘要、求值凭据与目标版本 | 真正形成原30消息/24000字符摘要后，原业务UI改变事实，核新上下文使用当前版本；原60秒凭据过期拒绝。员工改变计划结构后旧goal授权/在途Run停止，本人重读及resume绑定新goal，旧历史与原业务保持。 |
| 14 | 重复tool ID和真实截断stream | 现protocol只验证完整终结流中的半截参数JSON。另送重复tool ID及实际截断合成SSE、不给完整DONE，必须无完整可执行意图/新卡/业务写入，并可由原页面恢复。 |

依据为 implementation_plan.md 的 M8.1 原故障步骤及完成检查，以及原 M4.4 流协议、M4.7 source-map/事务hook、跟进20tick、摘要事实与goal版本合同。实际边界已核 assistant_runtime_queue、principal、runner、receipts、outbox、plans、context、business_assistant_service 与原前端。批量准备在 runner 的 _prepare_row 仅flush，_save_preparations 末尾 _finish_write 统一commit；确认仍每张独立原业务事务。

已有效回答的原路径仍保留：单卡准备提交后原进程kill/自然恢复、员工stop后迟到模型响应、即时登录退出/换店、UI批量首成次败或未知后暂停C、Master unsupported只读核对、迟到核对上下文保护及侧栏自动刷新。40/41自动业务绿色但SDK观察器异常的独立audit false原件保留；42新脚本受影响两场独立audit true，不把它当成全部新缺口通过。

下一增量优先复用 runtime_batch 的原Flow准备、真实提交丢返回和原receipt入口，源码只按必要精确补丁调整。新增故障先定实际注入点/恢复动作/完整行与原业务hash，在同最终源码、脚本及依赖的独立新实例重复原断言，再运行当时完整注册入口及CI。仅有意图、局部日志或绿计数不足以关闭表项；M8.1及原五完成检查保持原状态，后续实现与动态证据另追加。
