# PATCH-M8-4-SYSTEM-RELOAD-REQUEST-01

2026-10-01，M8.1 精确浏览器候选修复，修改前登记。receivables11 原11/11通过、CLI0；full12 的 system-management-hk189-191 在登录后第5动作重新载入stores时 Response.json 报CDP No resource with given identifier。响应按URL匹配可能拾取重新载入前已发出的同路径旧页面响应，页面切换后其body失效；无业务表单提交。原错误、动作、网络和已生成PNG保留。

full12 的场景进程在确认本轮准确PID/命令后停止，原runner自行正常关闭服务并以CLI3收尾，scenario_exit_code=4294967295，provider合成15/真实0/阻外0；不记完整53。全部关联Python已退出后才修改。

仅允许 tests/browser_click/system_management_business.py open_page 同route reload分支：先等原stores业务标题真实显示（登录仅等待门店控件，并不保证原页面读取完成），再将仅按响应URL捕获改为reload时捕获新发出的原GET request，再取得该精确Request的response/body。原方法/路径、HTTP200、可见业务标题、全旧业务行不变保护不变。不给旧响应重试、不加固定sleep、不降级fetch或额外HTTP请求、不忽略错误。非reload分支与全部业务提交/员工身份/门店/密码/审计断言不变。

精确字节和AST审阅、独立源码复审后，新外部SYS单场核心路径及同版本完整53分别运行。旧full12为失败且中断的诊断轮，不拼入新全量；193逐项图像与真实Date门槛保留。
