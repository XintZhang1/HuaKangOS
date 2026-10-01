# PATCH-M8-4-PDI-INDEPENDENT-VEHICLE-01

2026-10-02，M8.1，automatic-business15 已 CLI 3 正常收尾，48 个场景执行、47 通过、PDI 1 失败；原报告和图保留。PDI 尚未进行正向业务点击，前置旧车来源核对失败。仓库外合成库只读核对：退订车 74 相比本轮采购原件只有 approval_state 从 approved 变为 void，VIN、门店、车型、原成本、库存代次未变。前序场景共用该车，退订释放并不保证后续仍是本店可配库存；不降低当前实车/身份/保管守卫，不通过重排场景或回写状态规避。

独立追溯确认 HK-024 原调拨2/cases183、184：dispatch 从74真实出库，position_entry13 成本 -11000000；拒收后的 return_receive 按原代次合同生成新本店 vehicle79、position_entry14 成本 +11000000，同VIN custody identity3/current_vehicle_id79/store1/generation2/version15，原 transfer.status returned。旧74保留 void/exited、原位置为空是正确历史；本修复针对脚本误用旧代次，不把它记成产品成本或调拨缺陷。

仅允许修改 tests/browser_click/sales_pdi_business.py：从同轮实际采购点击证据取得供应商、已发布车型、整车仓库/库位和银行账户，按原 ID、版本、启用和本店关系核对；保留原退订订单及净退款、客户归属、原采购收车来源核对，但不将旧车冒充当前可配库存。复用已存在且实际执行过的 receivables_business.vehicle_precondition，经原页面独立采购一个新 VIN、经理批准、财务实际付款、库管发运/验收，完整保留其来源守卫和证据；新增实车只能由原界面产生。新车重新核实审批状态、原成本、库存代次、集团 VIN 身份和当前保管/位置，再进入原 PDI、两笔收款、失败整改复检和交车路径。将独立采购事实和成本来源记录在本场景外部报告。

不修改生产、基线两辆采购、场景顺序、业务规则、旧失败证据、catalog、53 场景注册或 45 文件白名单；不导入 app，不使用 SQL/API 正向造车，不增加外网模型。复用模块纳入原镜像指纹核对。异常必须保留失败，包括独立采购权限/版本/付款/发运/验收以及任何后续整备守卫；人工源码审阅及轻量静态检查后在全新隔离镜像重验。新脚本指纹的结果不得继承 full15 或旧分组成绩。
