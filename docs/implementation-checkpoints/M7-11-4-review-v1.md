# M7.11.4 编码审阅与实测记录（评审升级申请适配器）

2026-09-28，集中测试阶段。M7.11 组第四项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/escalation_request.py`：`EscalationRequestAdapter(FlowCaseAdapter)`，`object_types=('escalation','refusal')`；受控只读 `read_scope(scope)`（`scope ∈ mine/to_review`）与 `read_refusals()`；写入只准备 `POST /api/escalations` |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='escalation_request', object_types=(ESC_TYPE, REFUSAL_TYPE), operation_ids=(GET /api/escalations, GET /api/escalations/refusals, POST /api/escalations), fact_keys=ESC_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_escalation_request.py`（7 项） |
| 未改动 | 原 `escalation_api.py`/`_service.py`/`_models.py`/网关、迁移、权限表与评审流程；未新增 signal hook |

## 2. 结论摘要（先读，经核对）

1. reviewed catalog 内本域**只有三条**：`GET /api/escalations`（`scope` 默认 `mine`）、`GET /api/escalations/refusals`、`POST /api/escalations`（**只准备**）；
2. 原 `POST /api/escalations/{escalation_id}/actions/{action}`（`claim/done/reject/cancel`）**存在但不在目录内**：
   **助手不得代办人工处理动作**（套件断言该调用不存在，且注册的 operation 恰为三条）；
3. 事实按类型适用，**不适用类型返回未知**：前两键仅 `escalation`，末键仅 `refusal`；
   `escalation.done` 要求**原人工 done 动作**与**当前状态**同时吻合，理由始终含
   **"评审 done 不满足业务成功或权限已授予"**；`escalation.request_recorded` 要求原记录回带**服务器 `refusal_id`**。

## 3. 实测结论

运行 `20260928T143521Z-1b83c9e6e0`：`status=passed`，`phase_complete=true`（源码指纹 `d7ca098e9da7e970e026100c8c235818cf0db875658e7459e9aa88a8b48ced6b`）。

- `tests/runtime_domains/test_escalation_request.py`：**7 项通过**。覆盖三条 operation 在目录内且人工动作**不在**目录内（原动作确实存在于源码）、不动态导入/不写库/不抢回退、**人工动作调用不存在**；注册 spec 恰为三条 operation 与两个对象类型；`request_recorded` 需 `refusal_id`（缺失未知）、未命中**明确未满足**（理由点名 mine/to_review 两范围）、**命中即停不多读**；`done` 四态（动作+状态吻合→真、只有状态→未知、事件无 done→未知、状态不符→假）；`refusal_recorded` 需 `classification`、两向类型适用性未知；快照状态/引用/门店门禁与 `scope` 校验、命中即停；结果只绑定准备写入、读操作不绑定；回执保持冻结 `request_id`、未绑定 `unsupported`、只读 operation 422。
- 本轮**一次通过，无返工**。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `escalation_request` 一个适配器；M7.11.5 起 13 个小项仍为 `todo`，按编号串行。
- 评审队列/收件人取值仍由原接口与本人在岗决定；助手只准备、不办理；真实原库与真实模型属 M8.x。
