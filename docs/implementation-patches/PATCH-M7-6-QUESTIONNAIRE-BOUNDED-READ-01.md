# PATCH-M7-6-QUESTIONNAIRE-BOUNDED-READ-01

2026-10-04，M8.2 的 v14 CI37172219196 自然终局后登记。问卷原 HTTP 目录返回最近 200 项；现有 gateway.sanitize 合同将列表投影为前 100 项及唯一固定 more 尾标记。新增 C 测试误要求 native reader 仍收到 200 项；适配器也未识别这个正常尾标记，会将其当缺 id 的损坏行拒绝，不能给出原要求的“缺少完整性依据，事实未知”。本次实际停于 101/200 断言，后一个生产分支是已核源码缺口，尚不冒认动态失败。

精确生产范围只为 `app/assistant_runtime_domains/questionnaire_version.py::_version`：识别 gateway 原有唯一、固定形状和位置的截断尾标记，严格校验其余原记录。所求版本已在完整可读记录内时沿原摘要/独立复核/门店校验读取；不在可读记录内则返回 503 未知，不能据此认定不存在。任意错误行、额外/伪形状标记、重复 ID、跨店或错误发布来源仍拒绝。不改 gateway 的大小限制、原 API、200 项目录或权限，不生成完整性事实。

V 的原 C `test_registered_questionnaire_publication_frozen_answers_original_http` 同步核原 HTTP 200 项与 native 前 100 项加固定尾标记，保留未知 fact.satisfied=None、空 evidence 和完整图无写；所求版本仍可读的路径及非法行拒绝保留。只在该协作者外部候选目录改 C，root 顺序整合。

另允许同 C 的 `test_registered_vehicle_income_original_http_keeps_approved_target_and_original_refunds` 仅调整销售单配车前置的实际员工：原 manager 可代办原配车任务及生成合同，inventory 原合同权限拒绝保持。原归属门店、真实 Vehicle/Hold/事件、目标审批、收益及退款全链断言不改，不能以此扩大 inventory 文档权限。

原文件、差异、SHA 与两平台失败证据外置保留。静态独立审阅后按 M8.2 原完整入口执行，当前唯一 in_progress 不变。
