# M8.2 v18 Windows进程身份实证

2026-10-04，main `9f36e564bb4412481e5e201153350206d1c4f77e`，Windows定向CI [37180332868](https://github.com/XintZhang1/HuaKangOS/actions/runs/37180332868) 在05:46:15 UTC自然终局failure。本轮未调度Linux，不视为双平台验收。输入asset609203214 / `2837369d3f2d7d57dfac59c10b4eb8dff1fde9084fd9f28bf3b3c089551ed0ec`。

官方artifact11294233402及实际ZIP SHA为 `db0f5b65cb22745e18e61ee7e1f5fc1af06e1258ce23aa0f61237d6dc0d33a85`，原件在 `V/closeout-20261003/m82-v18-windows-20261004T055039Z-a6e0b08d0b`，full运行 `20261004T053627Z-3c9ca5baa2`。有限诊断文件为该运行command-results/m82-runtime-boundaries-02下的 `checkpoint-identity-e3185ef111754f1cbe3b657e586a13ab.json`。

独立审阅 `independent-review.json` SHA为 `e3537760446ff9800b23b5b3667cf72203febe89eb699e3687c8c51c1e3aef9e`：官方ZIP摘要、55个成员CRC及解压字节一致；strict18通过，collector完整收集3407个唯一节点/245文件，full实际仅7/101命令，114通过、1失败、3292未执行。matrix1/A25/B33/C35/D14通过，E6通过/1失败；其余94命令、F及原203独立执行尚未运行。strict/full五指纹和1302源码/33执行器/768外部输入映射一致，输入和依赖前后未变，8个实际命令自然排空、无超时或清理终止，真实模型请求0。冻结的M8.2 legacy_compatibility=true和strict=false按原清单保留，未调整门槛。

实际记录：expected_pid4272，proof_pid6344，parent_pid4272；run_matches、helper_matches、mode_matches、parent_matches、process_alive均true，只有pid_matches=false。失败已精确定位到support294的原严格PID断言；同节点尚未进入故障kill、自然回收、后续24轮及原业务快照断言。此前Linux的25次读取问题在本轮Windows没有执行到，不能混同结果。

这份证据确认Popen句柄持有Windows venv启动器，而执行helper的实际解释器是其子进程。按PATCH-M8-2-WINDOWS-DIRECT-WORKER-01保留严格PID等式，将Windows测试子进程启动改为已绑定base解释器直接启动，并按CPython原机制保留venv身份；父/子实际路径、prefix/base及文件SHA在app导入前严格核对。非Windows、生产和原业务/模型/预算/终止合同保持，候选独审和新双平台完整实跑待完成。

v19冻结输入已登记于 `V/closeout-20261003/m82-v19-merged-20261004T060554Z-1a4cbee373`。相较v18只改两个helper及两份SHA登记，共4/801文件，其他797文件保持，包括E完整25次有序读取断言。manifest SHA `e584290406542634d68e135273361244ce1780e5faccb3c94949372662c9f963`，restoration SHA `6932ce14367a88b8dc2fb7528071991d4cc3caebd88422389357d41b70764905`，draft SHA `16c5dd37cd5dc430056a02196ca73423b875531b924911607e7360cfbafd5999`。两helper候选独审通过；合并清单另行独审，随后同HEAD执行双平台完整strict/full。

合并注册独审 SHA `1bbe5f2c2a5ef2ed9b78285c3134b3631b64d78b2f277c8fed883af9f4d549e5`：801当前输入全部逐文件核实，74份有序数组、101命令/101授权、10项Linux适用排除及原runner均保持。v19源码胶囊 SHA `1e39b364be36face7ebd3b0af3ca5a8995736ebd4361ae2d782d71d519e3f33a`，只含801登记源文件，无运行证据、数据库或密钥。
