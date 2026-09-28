# PATCH-M4-8-01：跟进核查的固定持久合同

2026-09-28，M4.8。依据用户后续必要范围默认授权登记。原允许outbox、queue与plans；本补丁细化无Run核查及增加runner最小机器可读收尾原因，未改变业务或确认权限。

- plans复用原完整条件纯读流程，新增独立FollowupCheck一次性凭据：绑定同Session/Engine、真实Grant probe版本、Plan/goal与完整Step/WorkItem/卡/RunItem来源快照，60秒有效。原Run条件消费、准备、close_followup_control的Run/fence门槛保持。
- 固定批量持久入口先按所有Session→所有Plan→Grant锁并验证所有快照，再统一写Step状态/typed last_evidence/next_check_at；同Session版本由本事务统一维护。不得在写事务里调用GET/模型。全部必要步骤由本轮完整证据确证且无未处理卡/行才能完成Plan、撤当前Grant和写原WakeEvent。空必要集合不完成。
- queue固定followup resolve/persist/validate接口仅接受真实FollowupCheck，跟进成果与Run同事务，源授权提交前重新复验。signal和定时核查共享plan+goal+稳定事实fingerprint触发键，原终态不重开，不新增字段或迁移，不往EvidenceRef塞杂项。
- outbox保持逐事件CAS原子性，在原只读阶段加入有限条件核查；补漏只扫描明确active Grant，next_check_at优先显式到期，普通补漏5分钟。暴露单次异步调度函数和5秒检查间隔供M5.6 worker调用，本项不启动常驻进程。
- `app/assistant_runtime_runner.py`只在原最终回复同事务保存固定字段的执行收尾摘要（完成状态、有限原因码、是否需要员工输入），便于调度识别预算失败/缺资料而非解析回复文字。禁止存推理/异常原文/业务明细；不改变模型循环或员工确认流程。该摘要存在Run.usage独立固定命名空间，沿用原计数，不改迁移。
- 若需要在计划模块共享只读求值，允许抽取原函数内部纯读代码；不新增通用callback写权限、不创建伪Run、不使Grant probe获得模型/业务写权限。

异常路径：来源变化/过期凭据/并发事务整体拒绝；无变化/前置不足0 Run和0模型；旧失败或缺资料必须等待明确本人输入/继续，不因时钟或无关事件反复调用；原卡expired/cancelled/uncertain不自动复制。失效授权走原独立控制收尾，仅助手状态改变，业务记录不撤销。测试与故障注入全部后移，静态审查不代替验收。
