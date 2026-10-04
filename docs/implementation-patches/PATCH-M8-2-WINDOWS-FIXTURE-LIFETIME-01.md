# PATCH-M8-2-WINDOWS-FIXTURE-LIFETIME-01

2026-10-04，M8.2 唯一进行项。v21 Windows CI 37188128764 / job111394399180 于11:31:49 UTC自然failure。原件artifact11301688391、ZIP/官方SHA `8cd27997a9af7b4723778dc69e656e7ca24144d73bea985771b05d10394b0f7a` 保留，未取消/重触发。以下为原件实际失败后的必要测试生命周期适配，不修改生产逻辑。

## 已有证据

Windows全部101命令执行，18个旧业务命令中有686个setup因WinError32不能rename自己的 `fixtures/test.sqlite`。第一项是business01的赠品零价完整原链通过后的下一节点change0；前一节点末尾 `tests/test_addon_gifts.py:84` 使用 `with sqlite3.connect(TEST_DIR/'test.sqlite') as restored`，该context只结束事务，没有close连接。Windows文件不可重命名；`engine.dispose()`只管理SQLAlchemy池，不能关闭这些独立raw连接。其它受影响命令必须逐项核对直接前序及同类源码，不将所有686行当686独立业务缺陷。

精确允许范围：外部baseline overlay中，由本轮18个实际受影响business命令及其调用的共同测试helper定位到的raw SQLite context连接；先附精确文件/行清单及原SHA，再在独立候选改为 `closing(sqlite3.connect(...)) as connection, connection`，或等价的外层closing/内层原事务。原SQL、参数、匿名`:memory:`、commit/rollback、异常断言和节点保留。已显式try/finally close的连接不重复修改；不使用GC/retry/强制关活连接，不改conftest rename/FK/标记守卫，不让Windows跳过。

另原 `tests/test_preview_runtime.py` 的9个Windows PowerShell call均在同helper的 `subprocess.run(...timeout=20)` 超时，stdout读取线程未结束。没有足够证据认定是执行策略、stdin等待、启动器业务或进程残留。允许该原helper的最小确定性CI调用与有限诊断：同一真实 `powershell.exe`、同一当前 `scripts/preview_launcher.ps1`，添加 `-NonInteractive`、stdin为DEVNULL；stdout/stderr定向自己的tmp_path文件，避免管道读线程掩盖有限输出；20秒原上限、原返回码及所有JSON/业务断言不变。只输出固定启动/载入阶段标记；超时正常终止并wait本次子进程后，将有限原输出纳入失败消息，不猜通过、不增加超时/重试/备用shell。该helper只dot-source无副作用函数，原测试的安装命令仍由原有限fake函数接管。

root负责preview helper及该文件两个raw SQLite context，reg负责其余有限raw连接清单和候选；day可独审事务语义。所有文件仍在全新仓库外before/candidate中；最终合入前检查原字节、节点、独立审阅及无验证进程。先现有统一M0.2.B定向原节点复现，最后当前同候选双平台101完整复验。非零、超时和新失败继续保留，不能凭此补丁声称已经修复9个PowerShell超时。

精确清单已在实施前补齐：`V/closeout-20261003/m82-v21-repair-candidates-20261004T111905Z-c9fe9a268b/windows-lifetime/main-sqlite-lifetime-audit.json`，SHA `8f7e4590a200b62187cfd8d100ef529df51160ff04ccb17b49c165033abc21dc`。仅上述18个实际命令及原selection范围内，194处主库raw context/81文件；每处有原SHA、行号、函数、原参数、同文件调用者和18个首次失败的真实前序。reg独占193处/80文件；另 `test_user_access.py` 原203行由root在已有候选追加关闭。`test_preview_runtime.py` 的另两处独立文件连接属前述独立范围，不算这194处。未触及其它临时/匿名内存连接，已显式关闭的context排除；16类后续同名引用均重新绑定，四处return在退出前已物化/校验完成，未发现连接或游标逃逸。全部原事务context必须保留到外层closing之前执行退出。

80文件/193处独立审阅通过，报告SHA `2194080ff212703cd7a1831a74373eec3d0ec1b1221aa912c9abff5924dd95ad`，整文件AST及字节逆向精确。root另管user_access1处及preview2处。候选已按原SHA核对合入外部注册来源，原测试/SQL/事务语义及清单保持；定向和全量动态结果仍待。

本地Windows原入口定向 `20261004T121130Z-b2b9a85767` 中，赠品连续原2节点、preview原13节点（含9个真实PowerShell调用）、storage原2节点及账号并发原2节点全部通过，CLI0、无超时、正常排空。此为当前机器证据，不能据此推定GitHub九项旧超时原因已确认或全部686准备错误已消除；新同候选GitHub双平台完整结果仍待。
