# PATCH-M8-1-PREPARATION-PROCESS-CRASH-01

2026-10-02，业主授权以达到原交付标准为目标持续继续。当前仅M8.1在办；GitHub36976885886/9a6505b已经terminal success，原件下载审计另留证，不把53点击全绿代替M8.1原故障合同。

当前最早强证据缺口是准备真实提交后、Run结束前的worker进程崩溃。精确测试范围：新增`tests/browser_click/runtime_faults.py`，包含固定隔离worker子进程控制及一个原生浏览器场景；`fixture_server.py`仅在明确process模式替换嵌入worker为实际`app.assistant_worker.main`子进程，沿当前白名单镜像/随机合成身份/config/阻外provider；`run.py`仅增加该文件白名单及模式登记，完整或选择新故障场景时用process模式，其他定向场景保持原模式；`scenarios.py`注册新故障场景并延续原全部53。README、当前M8.1、原任务及递增检查点允许维护。生产代码不改。

故障点只在隔离子进程包装原`_save_preparations`：先执行原函数及真实`_finish_write`提交，写外部阶段标记，再阻塞当前worker；父夹具仅终止自己持有、登记的该PID。通过原UI提交新建合成客户请求，确认已有唯一真实pending卡和WorkItem、Run仍running、原业务全表hash不变；随后启动另一原worker。等待原90秒租约自然过期并由原队列重领，不改时钟/租约/业务/Run/事件。核同一Run的真实fence/attempt变化、原卡与准备WorkItem唯一且仍需人工确认、事件连续和原业务零写入。超时/失败保持失败，不能伪造回执或重发聊天求绿。

仅该故障模式的合成配置将原turn_timeout_seconds从60设为180，合法资源边界内覆盖真实90秒租约恢复；不改生产默认/队列租约和既有定向配置。父及每个子进程分别保留provider账本，即使被kill也记录已处理的合成请求，最终汇总真实调用0/外部尝试0。固定外部控制文件不是业务/模型工具，只接受对自己已登记子进程的kill/restart/正常stop。数据库及凭据不进入Git，原失败不删除；每次新镜像全部关联验证收尾后才修改候选。

先独立审阅并执行一场，再在相同生产/脚本/依赖指纹的另一全新实例重复同一故障。这只补一处准备提交后崩溃，不替双活worker旧租约晚写、在途撤权、整批各行/首成次败后停、通知/发件箱故障、HK099真实Date及其它原门槛。M8.1/M8.4/CP36及四生产开关默认关闭保持；当前新增场景使注册54，原53成绩作为旧候选真实原件保留。

实施前源码补充：原租约90秒后还由队列设首次30秒退避，保持原自然恢复，不缩短它。精确测试范围追加`provider.py`仅本新故障合成提示（浏览器客户crash_前缀）的新模型链：原恢复不重放已存role=tool链，故不能按calls=0盲重造意图；只依据本次RuntimeContext的同session真实pending卡/原输入来源返回待员工确认收尾，不改其他合成响应、数据库或原runner。该判断为已保存事实的合成模型应答，不伪造卡或业务成功；完整唯一卡/WorkItem断言仍保留。

独立接线审阅发现实际失败传播缺口：Uvicorn可能仅记录lifespan shutdown异常并返回，fixture原main无条件0；原自动runner也未核正常stop后的server退出或是否强杀。仍在上述两文件精确范围补齐：fixture仅在lifespan完整清理/provider记录/命令任务无异常后返回0，异常非零；runner自动正常收尾需服务0且未forced terminate，否则整体失败。finally清理保持原先失败，不将半完成控制器/孤儿进程当passed。控制器start/stop必须回收其自己Popen，任何初始化失败也不能遗漏；不扩大业务或修改生产worker。

2026-10-02 首场preparation-crash29在应用启动前真实失败：Windows CPython3.11 venv redirector的Popen.pid与被转发解释器os.getpid不同，5秒身份登记超时；fixture退出3/runner宿主退出1，场景未执行，全部关联进程收尾。原目录保留，不记业务故障验证通过。外部stdlib probe明确venv启动26380/实际33116，直接base启动28784/实际28784但依赖变为全局，不能使用后者代替原venv。

故障执行器精确修复仍仅runtime_faults.py的_launch：Windows且当前为venv时，直接Popen当前sys._base_executable，并以当前sys.executable设置CPython原__PYVENV_LAUNCHER__启动变量，保留原venv识别与依赖。官方CPython v3.11.4 Modules/getpath.py对应变量用于launcher选择原executable/venv；外部direct-venv-probe实测Popen25508=os.getpid25508、sys.executable/prefix与原venv完全相等、SQLAlchemy仍原venv路径。不是任意PID终止或移除PID校验；原控制器持有的Popen必须就是实测worker，Linux及非venv保持原启动方式。原正常/故障收尾与严格父子账本身份断言全部保留，生产代码不变。新目录重测，不复用29。

启动器依据：[CPython v3.11.4 getpath.py](https://github.com/python/cpython/blob/v3.11.4/Modules/getpath.py#L264-L280)；本机probe原件位于外部`V/browser-click/worker-launch-probe-20261002-88ab6670`。这里只登记执行器原因，不把stdlib probe计入业务验收。
