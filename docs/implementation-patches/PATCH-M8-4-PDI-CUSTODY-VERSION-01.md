# PATCH-M8-4-PDI-CUSTODY-VERSION-01

2026-10-01，M8.1，四关联运行已退出。PDI01 原新单allocate已200且后GET正确，守卫拒绝额外vehicle_custodies变更；vehicle_procurement_service.require_available_vehicle原函数在同事务锁当前已审核vehicle并增加唯一Custody.version，原payload/physical未改变，属于候选漏声明。

仅 tests/browser_click/sales_pdi_business.py 的 mutable 在任何已明确car的原动作，有限SELECT该车唯一current_vehicle_id Custody，核恰1，并仅允许其version变化；所有归属/代次/VIN/identity/pendingTransfer及其他旧行不变，position分支不再扩许updated_at（该表无此列）。不改生产、原权限、锁、数量或原接口，不把POST200当完整PDI通过。修复后新镜像重验。
