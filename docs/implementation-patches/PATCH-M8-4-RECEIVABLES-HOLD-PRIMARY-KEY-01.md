# PATCH-M8-4-RECEIVABLES-HOLD-PRIMARY-KEY-01

2026-10-01，M8.1 同一实施项，当前三组完整终局及相关进程/监听已收尾后先登记精确候选修正。

receivables07为11执行10父通过1失败。最后不是VIN身份或保管错误：HK158实际选VIN后、原allocate POST前，在Guard(ar_sales_allocate)查询flow_vehicle_holds ORDER BY id抛no such column。该表真实唯一主键vehicle_id，无id；候选TABLES合并把原真实键覆盖为通用id。最后动作334、before_ar_sales_allocate观察、确定源码调用链和本轮外部合成库mode=ro/query_only PRAGMA共同定位，日志未保留完整Traceback，不冒称有原stack。没有该allocate POST或占车业务结果。

仅tests/browser_click/receivables_business.py的有限TABLES最终映射显式flow_vehicle_holds='vehicle_id'。Guard/原VIN选择/Identity和Custody唯一派生/原hold字段/状态/旧行保护和所有业务输入不改，生产、schema、服务、其它映射、目录和runner/CI不改。有限182映射180现存合法，file_security使用真实unique键；另sales_pdi_records仅无调用的旧声明，不是本次触发且不猜造表或扩守卫。

精确AST与独立增量审阅后新鲜11项闭包复验；不把原已通过父或上一零退款结果拼成当前完整业务。最后同指纹全53、193体验逐项证据、真实Date及原环境/员工/模型/生产门槛保持。
