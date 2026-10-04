# PATCH-M2-6-RECEIPT-READ-IDENTITY-01

2026-10-04，在当前 M8.2 真实回归中修复原 M2.6 接线，仍只保持 M8.2 一个 in_progress。CI37172219196 已自然终局。Linux C 的 questionnaire_version 和 reminder_empty 参数在原确认已提交且回复丢失后，首次 execution-result GET 因 `_LoginRead.active` 不存在而返回异常；这是生产身份接线缺陷，不修改测试以忽略。

精确生产范围：`app/assistant_runtime_receipts.py` 原 ownership/read identity 接线。复用已经加载并检查 active、must_change_password、access_version、当前门店岗位的真实 User，为原领域只读权限上下文提供 RequestPrincipal；同时固定原 actor、role、access_version、session/store。before、原回执读取和 after 独立 reader 各自沿原当前账户检查，HTTP _LoginRead 与后台 Grant/RuntimePrincipal 共用此路径。

禁止给冻结身份补常量 active=True、借管理员身份、取消原 group/care 权限或把旧 ORM 刷新值当原授权版本。所有原 owner/session/store、冻结 submission/digest、原可靠回执和查询前后来源一致性检查保持；GET 不执行业务提交或自动 settle。保持 `_owned_lookup_proposal` 原调用合同，必要的小型内部 helper 只服务现有重复边界，不建设通用身份框架。

测试只补强/修正原 C 参数化回执节点，范围已在 PATCH-M8-2-V14-OBSERVATION-01 登记；复用该节点及原回执拒绝、撤销/失效与来源变化回归，不移除失败。生产和测试独立审阅后沿完整隔离入口实跑，不以静态审阅宣称恢复成功。
