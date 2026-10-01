# PATCH-M8-4-REWORK-CONVERT-VIN-01

2026-10-01，M8.1。全部关联验证已收尾，精确仅 repair_rework_business.py 原convert守卫。

rework03在原convert成功后Guard发现未声明care_customer_vehicles；原service_intake_service.rework_action convert调用gate_attendance.arrive_guard→lock_vin。先独立核当前店同VIN最早且唯一CV为明确本次父CV，再仅此ID version/updated_at列允许touch，沿已有mutable(...vehicle_id=...)合同。原字段/身份/观察/原维修/Cash不改，原convert事件和VehicleBinding照实，不编造intake_arrivals或GateFact。后续release原有限同CV版本守卫已具备，保持原回执/旧行保护；新实例完成全部HK038后再计通过。
