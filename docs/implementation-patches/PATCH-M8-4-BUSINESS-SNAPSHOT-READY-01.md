# PATCH-M8-4-BUSINESS-SNAPSHOT-READY-01

2026-10-02，M8.1 修改前登记。full13 的 HK073 盘点截图实际只有“正在读取…”；HK077 保险收款截图仍在续保跟进页面，不能作为原保险显示证据。原图和失败轮保留，关联进程已全部退出。

允许 `tests/browser_click/scenarios.py` 的 Evidence.snapshot 增加默认关闭的 `business_ready` 显式参数：仅被业务检查点 passed 方法启用，截图前等待原 #main 直接 loading 消失、原业务 h1 可见、直接 errorpage 为零。32 个业务检查点 passed 方法仅在原 snapshot 调用传该参数；覆盖文件清单在外部修改记录精确列出，全部其他方法与助手有意忙状态截图不变。无固定sleep、重试、fetch桥接或错误忽略；原页面不就绪就真实失败。

另仅允许 `tests/browser_click/insurance_business.py insurance_business` 的 HK077 检查点：用既有 read_as 以原财务本人从原保险详情 GET 读取第二保险原单，核对当前 ID/版本、原 customer_direct 资金摘要以及数据库原资金事实，记入此检查点后再截图。不再次提交任何保险/收款事实，不把续保跟进页当保险页，不变更任一已有业务断言或原规则。

该补充读取前后比较全部原业务表摘要，仅允许实际换员工登录追加一条原 login/users/当前财务审计，旧审计逐行不变；原 logout 仅撤销 login_session、不追加审计。登录尝试/会话仍沿用现有摘要排除，不把合法登录写成全库零写。原资金和其他全部原业务摘要必须不变，不放宽为任意审计写。

独立源码复审并冻结全部精确指纹后，新完整53运行和逐项阅图。只读原页显示证据与原API/数据库结果分别记录；已有错误图不覆写、不继承为新轮通过。
