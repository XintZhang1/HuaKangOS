# PATCH-M8-4-RECEIVABLES-OBSERVATION-FOREIGN-KEY-01

2026-10-01，M8.1 当前浏览器候选精确修正，实施前登记；finance10仍运行，全部关联验证收尾前不修改源/tests/runner。

receivables09完整11场景10父通过，最后候选在 repair_source 建立原现场预约、接手后，读取既有里程时抛SQL no such column: customer_vehicle_id。原care_vehicle_observations的真实外键名是vehicle_id，引用care_customer_vehicles.id；intake_appointments/intake_arrivals/intake_vehicle_bindings字段才叫customer_vehicle_id。失败位于实际到店凭据/arrive POST之前，不称到店或维修已完成，原已建立预约保留。

仅允许 tests/browser_click/receivables_business.py repair_source 单条SELECT的care_vehicle_observations WHERE字段改为vehicle_id。保留当前确切本店原CV ID、里程读取/max+100、本人原生现场VIN核对、原到店/绑定/纯作业/独立报价及质检/多方客户与内部承担、部分实收/正应收/原回执与全旧行守卫。不得改生产schema/DB、换车、造里程事实或放宽SQL guard。

静态核原模型和镜像真实列、独立精确源审后新外置原11闭包再跑；局部不拼full53，之后完整同版本full53、193逐项体验和Date等原门槛保留。
