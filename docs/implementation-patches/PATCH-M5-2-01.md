# PATCH-M5-2-01：旧会话的持久执行状态投影

2026-09-28，M5.2，依据用户持续授权。原允许API消息分派、Runtime SSE及旧stream包装保持。补充business_assistant_service.py仅session_view内已添加的last_request Run查询：读取同一真实Run的status，将queued/running映射原processing，终态沿真实最终回复/中断显示。未领取Run尚无busy_token时不能误报原消息已中断；busy字段仅为本会话真实排队/执行提示，不新增租约或更改legacy互斥。

不更改confirmation、Plan、权限、队列及原业务。运行开关关闭后旧执行器保持；存在旧Run时状态仍来源于持久记录，不能按网页连接判结束。SSE和兼容等待不领取Run、不调用模型、不改业务，超时返回原run_id。测试全部后移，补入集中验证清单。
