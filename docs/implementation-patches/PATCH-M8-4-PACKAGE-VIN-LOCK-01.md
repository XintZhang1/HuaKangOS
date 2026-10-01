# PATCH-M8-4-PACKAGE-VIN-LOCK-01

2026-10-01，M8.1。精确修改 tests/browser_click/repair_packages_business.py 的新会员CV关系、原 arrive 及 release 守卫；所有关联验证已收尾，保留 business-repair-packages-20261001-01 原失败。

原 gate_attendance lock_vin 对当前店同 VIN 最早 CV 仅 touch version/updated_at；本次新CV唯一，实际 arrive 合法变化被脚本漏列。先独立 SELECT 核对本次新 VIN 在当前店唯一且最早就是该CV，再在 arrive 和 release 各仅允许此有限CV的 VERSION字段变化。start既有同CV版本守卫保留，convert及其他动作不豁免CV，不扩大其他车辆/身份/观察/历史旧行的允许更新。守卫仍枚举真实新增记录及保护全库旧行，不把 GateFacts 或提醒推算为已完成。全新隔离实例复验原同会员套餐输入到接车路径，无积分规则与同轮真实已生效积分规则分支分别保留证据。
