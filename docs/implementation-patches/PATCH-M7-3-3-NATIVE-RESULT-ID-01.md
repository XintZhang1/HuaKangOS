# PATCH-M7-3-3-NATIVE-RESULT-ID-01

2026-10-04；M2.6最终原生回执静审结束后，唯一回开M7.3.3。真实POST /api/rework-extensions/requests返回id=ReworkRequest.id、case_id=本店Case.id、rework_extension.grant_id=责任授权id；QUOTE返回RepairCase/state/flow_version而无status。原结果将请求ID绑定为Grant并丢失报价Case，是实际绑定缺陷。

范围仅app/assistant_runtime_domains/rework_grant.py的extract_result及必要原常量；__init__.py原rework_grant spec保留READ/CREATE/ACTION、Grant对象/事实/原Grant fallback，另加同factory的rework_derivative_results，object_types=('case',)，operation_ids仅REQUEST/QUOTE，fact_keys=()、fallback_object_types=()。不增加Case selector/fallback，不改原快照/事实/回执、业务API/模型/历史迁移/权限/状态机。

REQUEST严格核真实正整数request/case/grant ID和definition_version=1原关联形状；QUOTE只接受原RepairCase v3/v4真实id/state/store/version，错误/未知/混族不绑定。原Grant分支保留。外部V/tests/baseline/overlay/tests/runtime_domains/test_rework_grant.py只原registration/results两节点窄修，保留10节点名称/有序清单/旧Grant断言，补真实派生shape和实际registry分派。保留旧源/差异，不手造Receipt或降守卫。

编码和独立审阅后implemented；实际验收仍通过随后M8.2统一隔离入口，不新建runner。允许本补丁、原计划项/CP19及小型编码审阅/architect进度维护。员工试用之外全部原技术门槛保留，本项不调用模型或访问公司/原预览数据。
