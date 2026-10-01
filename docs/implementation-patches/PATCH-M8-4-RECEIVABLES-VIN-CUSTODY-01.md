# PATCH-M8-4-RECEIVABLES-VIN-CUSTODY-01

2026-10-01，M8.1 本轮浏览器验证补充。receivables05 的原整车发运POST/读取200，Case120 receiving/v6、Shipment3及VIN LTESTC9D0716F97FD；原后端 `_custody` 在发运首次追加该VIN唯一车辆身份与空当前位置的保管行。候选只允许Shipment新增而错误拒绝合法派生；后续验收还会仅更新本保管行四列。旧失败原件不改、不重放。

只允许 `tests/browser_click/receivables_business.py` 的 `vehicle_precondition` 发运/验收守卫与精确事实核对。发运前确认本VIN的实车/身份/保管不存在；只允许本次Shipment、GroupIdentity和Custody新增，逐行核唯一VIN、真实actor、model、generation0、version及空当前位置/转移。验收前保留原身份/保管整行，只许可同Custody ID的version/generation/current_vehicle_id/current_store_id；其余列及所有旧身份整行不变，不再允许追加身份/保管。原新实车、身份关联、位置、验收和Movement仍逐项核本VIN/本人/当前店/原单、准确数量成本与原CAS/回执。通用Guard、helper与生产后端不改。

全部关联进程停止后才实施，独立精确增量源审与AST；新隔离原正向全链确认前仍pending，不将合法追加许可变成整表豁免，不扩大VIN/门店/员工，不合并历史成绩或降低旧行保护。
