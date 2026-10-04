# PATCH-M8-2-V14-OBSERVATION-01

2026-10-04，CI37172219196（main de6a166）两平台自然终局 failure 后登记。Windows B33 的 setup 全部通过、原占用错误不再出现，但 cross-owner 损坏夹具未必真正改变有归属链接的通知；Linux B33 全过，C35 的新实测暴露下列测试假设错误。原失败字节保留，不覆盖或拼接成绩。

允许仅修改 V 原 B/C 测试中的这些函数，原节点、原 API、业务守卫和完整登记不删减：

- B `test_integrity_rejects_damaged_copy_without_repair` 的 cross-owner 分支：按真实 graph card 定位 proposal 通知，先验证原 owner，再更改为另一真实员工并读回；保留原 scope_mismatch 和只读不修复断言，不再选随机排序的第一条通知。
- C `test_validate_operation_repeatedly_preserves_request_id_and_draft`：保留原客户主档卡的重复纯校验、草稿和全图不变，按其原 schema 验证 request_id 缺席；另用原 Case 创建 DTO 的固定 request_id 在同一个禁止生成 UUID 的范围中重复校验并核输入不变。
- C `test_original_refusal_survives_refusal_audit_commit_failure`：用销售对原账户主档的真实 GET 权限拒绝，覆盖 authority 正向提示和审计写失败后的原拒绝保留；门店管理的原 rule 分类不修改。
- C `test_native_specialized_receipts_recover_only_frozen_employee_commands`：业务零写比较按真实 business_assistant_ 表边界排除助手恢复状态，同时保持所有真正业务表全量逐行比较。仅 service_order 参数改由原规则允许的 sales 本人贯穿建客户、卡、授权、确认、查询和恢复，另一真实员工仍 404；其它参数保持 manager，原冻结证据/同 ID/单次 POST/无重放断言保留。

多个协作者只在各自新建仓库外候选目录修改其负责函数；root 按原 v14 字节与 AST 范围顺序整合，不并发覆盖同一个 C 文件。原件、候选、差异及最终 SHA 留存并独立审阅。相关登记、完整 collector 和双平台原入口随后统一复验；静态判断不记实际通过。
