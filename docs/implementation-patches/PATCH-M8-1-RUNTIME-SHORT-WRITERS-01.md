# PATCH-M8-1-RUNTIME-SHORT-WRITERS-01

2026-10-02，M8.1，实施前登记。full14 的原退出 Run 在已配置预算、零模型轮时持续占唯一运行槽约90秒，随后由租约恢复取消；两个后继原Run排队超时。原server.log七次SQLite code5但无具体调用信息，不能认定其中某函数为原首次错误。九核心诊断未复现；外置五退出观察因helper执行时草稿变动，仅保留定位事实，不记正式冻结验证。

独立源码审阅明确六个同步短事务存在主Session SELECT后升写窗口。允许修改 `app/assistant_runtime_queue.py`：新增仅SQLite的短写预约helper，在任何rollback前保留原_clean，结束干净旧读后复用原_slot_lock的零行UPDATE，占写锁后才读；仅接入heartbeat、lock_for_write、release、reclaim_expired。SQLite保持原Engine，不能传OptionEngine给RuntimePrincipal或独立reader；PostgreSQL直接跳过，不改变事务、表锁与守卫。claim已首SQL占写锁，保持原样。原权限即时重验、scope、CAS、版本、fence、90秒租约、最后fresh guard、提交和错误分类不变；不持锁等待模型/native网络，不加重试，不重放写入。

允许修改 `app/assistant_worker.py` 的beat、beat_cleanup：这两项每次独立fresh Session且无RuntimePrincipal，首metadata读取前复用已有get_write_db；不扩大heartbeats/queue_counts等只读查询，不改worker循环、调度、来源/身份或功能开关。

允许修改 `tests/browser_click/scenarios.py slow_logout`：保留全部原UI/Cookie/迟到内容/原业务全表断言，再用原25秒wait只读核原Run cancelled、租约清空、有结束时刻、最后同seq的run.cancelled事件、此原会话0卡及全业务无变化。注册53/白名单45不变，不调用API取消、不等待90秒求绿、不增加业务写。该修复消除已证实的升级窗口，具体full14因果仍待动态证据；SQLite正常写竞争仍可能BUSY，不能承诺无等待。

生产与测试原字节、精确差异及指纹保存仓库外。实施后独立源码复审、轻量静态检查，再按当前原九助手/安全点击闭包复验；受影响路径通过后只进行一次同版本完整53与实际阅图，旧失败和不同运行不拼成绩。193逐项、真实Date及原PG/Linux/员工/真实模型/生产门槛仍分开记录，四生产开关保持关闭。
