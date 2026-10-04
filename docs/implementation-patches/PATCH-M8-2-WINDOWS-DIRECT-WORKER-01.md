# PATCH-M8-2-WINDOWS-DIRECT-WORKER-01

2026-10-04，Windows定向CI37180332868已05:46:15 UTC自然终局failure。实际固定诊断：Popen PID4272，worker PID6344，其父PID4272；run/helper/mode匹配、父关系及存活均true，仅pid_matches=false。原严格PID断言失败，尚未执行该节点的kill/恢复/24轮后置断言。诊断证实了启动器和实际解释器两层进程，原业务及生产代码不因此改动。

允许仅改V原两helper的Windows启动与前置身份核验。父进程从当前已隔离run.json的dependencies_before.python_runtime读取绑定，核对当前sys.executable/prefix/base_prefix、sys._base_executable及两份解释器文件SHA，所有路径须为现绑定的绝对路径。Windows以该sys._base_executable直接Popen，保留原参数/cwd/pipe，只在复制的子环境设置 `__PYVENV_LAUNCHER__` 为原venv sys.executable；不改父环境、PATH、PYTHONHOME、原隔离守卫或解释器安装。

子进程在任何app导入前，同当前run绑定严格核对实际sys.executable、prefix、base与两文件SHA，失败即停止；不得以设置环境变量就推定身份正确。必要有限诊断只添加核验成功布尔，不记录环境/凭据/源业务内容。其余checkpoint、原PID相等、Run/helper/mode、35秒等待、exact Popen handle kill和communicate排空、故障恢复、24/600预算全部保持。非Windows保留原启动方式及测试行为。

本方式遵循CPython3.11.9原launcher设置虚拟环境身份的机制（Modules/getpath.py264–319、getpath.c866、Lib/site.py463–507），使原PID相等守卫直接约束实际Python进程；不增加PID例外、进程枚举、任意PID终止、Job平台或重试。不触生产、测试节点、provider及任何业务断言。

day只在外部独立两helper候选实施，mobile独立审阅；root合并对应SHA登记、复核完整801输入并重新冻结。当前Windows诊断不是全量通过；修复候选仍通过原统一入口执行新同指纹双平台strict/full，原101命令/全部节点/授权/适用范围不减。M8.2唯一in_progress，原诊断及源文件保留。

候选已完成两人静态审阅：`V/closeout-20261003/m82-windows-direct-worker-candidate-20261004T055605Z-a1676fb3e9`。worker SHA `5c514786c3bde89038eab977a90cb55316783721176405d10823f071b18a3477`，support SHA `d89c88f3fd9fbda84896bb9e372dea9c72805ff6ebc78a9f53b342bdc3d60f25`；作者静审 `0c1410cd9d72746503c81043d01725a3d5a14b78cd9854f22bf5a3aaa2ab2cba`，独审 `34ca3624dc200ca085124909ca644bd5eee66bc3ff6d5e5da679cf4a56c98f55`。逆向文本/整模块AST一致，父核验位于Popen前、子核验位于原隔离守卫后且首个app导入前；父测试夹具既有app导入未移动。真实运行身份及恢复未由静态审阅证明。
