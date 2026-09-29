# PATCH-M8-1-LEAD-REGISTRY-01：接待事实接入真实条件目录

2026-09-29。范围：`app/assistant_runtime_domains/__init__.py`、`app/assistant_runtime_domains/lead.py`、`tests/assistant_offline/tests/test_lead_facts.py`、实施计划 M8.1 当前记录。

已实现的 LeadAdapter 三条事实没有填入 DomainAdapterSpec.fact_keys；直接调用适配器可过，而计划条件始终查不到。先增加目录及公开条件核验的回归，再登记精确事实键；核对原 `CURRENT_FLOW_VERSION=2` 与冻结 v1 目录，支持 `case/lead/1` 和 `case/lead/2`，不扩大到其它未登记版本、不增加原业务操作或自动确认。原关联客户、负责人和子单证据规则不改；本补丁不宣称其他缺少事实注册的业务族已完成。

验证：新接待只有创建人不满足分派；原 assign 后公开条件成立；真实关联订单由公开条件返回其证据；不兼容版本/其他 kind 不可借用这些键。

原生复测进一步确认：不只是漏填 fact_keys，原接待创建接口与合成种子均返回 flow_version=2，旧适配器只声明1；因此增加现行2的精确适用性，并在历史1副本上走原 assign 动作验证，不把文档的版本声明当原 API 事实。
