# M4.7 真实生产者与原事务映射

日期：2026-09-28。实施前源码定位记录；不是测试或整项完成证明。Runtime关闭时新生产者不访问Runtime表；开启后信号与原修改同事务，不另commit。

| 生产者 | 原事务owner | 唤醒键 / topic | 真实来源与引用 |
| --- | --- | --- | --- |
| flow_engine.log_event | 原调用service/API；通用create_case/act由flow_api提交 | flow:<FlowEvent.id> / flow | 追加FlowEvent真实ID，source_ref.type=flow_event、version=null；object_ref=实际Case |
| flow_api.assign_task | assign_task原db.commit | task:<Task.id>:<Task.version> / task | 接手人实际变化，flush后的真实Task版本；task_id、实际Case与source_ref.type=task |
| business_assistant_service.decide_proposal取消/过期/实际确认结果保存 | 各分支原commit；原业务API提交仍独立且不重放 | proposal:<id>:<version>:<status> / proposal | flush后的实际Proposal版本；proposal_id与source_ref.type=proposal；信号失败随该助手事务回滚，业务已成功仍保留原“结果未保存”返回合同 |
| assistant_runtime_plans._emit_grants及无Grant的Plan关闭 | followup_transition / invalidate_followup_grant / close_followup_control / 原计划保存事务 | 原grant:<id>:<version>:<status>或plan:<id>:<version>:<status> / grant | 复用M3.5已存在hooks，原Grant/Plan真实版本与plan_id，不另造授权 |
| user_access_service.change_access | change_access原db.commit | user_access_receipt:<id>:store:<store_id> / access.changed | 新真实UserAccessReceipt，previous_version+1与result.access_version；source_ref.type=user_access_receipt，版本=实际新access_version，关联update_user AuditLog |
| main.reset_password | 原reset_password提交 | audit_log:<id>:access:store:<store_id> / access.changed | 新reset_password/users AuditLog与真实must_change_password=true；source_ref.type=audit_log，version=null |
| main.edit_store | 原edit_store提交 | audit_log:<id>:store:<store_id> / store.access_changed | 仅active真实改变；新update_store AuditLog、原before/after与实际Store.active；Store无version，不虚构版本 |

权限生产者通过PATCH-M4-7-01指定的专用helper推导真实门店，只写固定WakeEvent，不更改当前业务写入门店。新用户/门店没有旧私人事项，不扩大创建信号；正常退出登录不撤销已授权Grant，自行改密也不能借信号自动撤后台授权。

通用create/act幂等早返回不补造FlowEvent。经log_event的专用业务保留同一源事务；绕过log_event直接写FlowEvent/Task的专用领域仅按后续M7适配实施，不把本映射宣称为全领域覆盖。分发器必须根据真实source_ref核对来源，不能只相信topic文字或自由描述。
