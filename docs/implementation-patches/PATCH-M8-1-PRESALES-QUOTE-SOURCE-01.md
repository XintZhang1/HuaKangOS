# PATCH-M8-1-PRESALES-QUOTE-SOURCE-01：版本报价的真实售前迁移来源

日期：2026-10-01。sales-reports04原UI完成本轮接待、采购、销售交付及独立退订，前四场景passed；报告前十项真实图表/明细/CSV核对通过，HK136严格失败。本轮报价create确把同一lead由intent转converted，却用sales_quote_convert记录空before_state，售前活动/阶段回放又未识别此动作。新原单被当作历史缺源，无法正确结束意向阶段。外部原报告、事件及原页面截图保留。

精确生产范围：`app/sales_quote_service.py`的原convert事件记录、`app/visit_activity_analytics.py`的原转换动作识别、`app/presales_stage_analytics.py`的原状态迁移回放。报价原事务捕捉真实lead前状态，事件记录真实order_id和本次已校验车型名称；两个消费者识别该原动作，严格intent→converted。原权限、客户/lead/model/CAS/request_id、报价/订单/任务与原事务不变；其余报价动作不改变事件before合同。

历史旧事件、流水和定义不回填、不重写；旧空before仍保留待核对，不能猜当前订单补造阶段。无需迁移，生产四开关仍关闭。M8.1由implemented重新in_progress，待当前新链与受影响全注册检查和人工复核后再登记实现；193正式业务、原模型/PG/Linux/员工及发布门槛仍未验收。

根在所有相关验证进程正常收尾后实施；三源码AST及独立短审，随后全新外置镜像执行相同五场景和HK136严格原源/四阶段断言。失败不删，十项诊断结果不拼成整报告passed。
