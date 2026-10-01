# PATCH-M8-4-CUSTOMER-HISTORY-STATUS-01

2026-10-01，M8.1。本次 customer-followon02 已实际完成其它收入6000分收款及两回访，随后原车辆服务摘要关联 POST /api/customer-service/vehicles/2/history-links 成功201并原GET显示，候选submit默认200而停。原API customer_service_api.py明确status_code=201，不能以成功创建当产品失败。52完整/55局部check及failed原件保留。

所有关联进程已退出后，仅 customer_followon_business.py 的 history_links 原调用显式 status=201。不改变submit通用200、API/schema/审计/回执/关系/旧行守卫，不加2xx宽松匹配或重放。两summary仍分别原UI创建，目标ID/内容/确认本人/原CareReceipt与exact摘要/现有原行保护保持。AST及独立短审后新8场景复验，不把已局部100/102/104记成七项通过。
