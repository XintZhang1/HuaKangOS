# PATCH-M8-1-OBSERVATION-MUTEX-01

2026-10-03；M8.1 Windows 外部观察文件协议修复。允许范围仅 `tests/browser_click/runtime_followup_closeout.py`：对本模块4处 PID observation 原子写入和1处全文件读取加同路径本地 mutex；不修改通用 `_load`、`_atomic_json`、控制/阶段/放行文件、生产源码或 OS 设置。

正式80场的原取消200之后，读取 `followup-observations-<PID>.json` 出现 PermissionError13。原报告未记录 WinError，不能赋予具体 WinError。纯文件探测复现读取与 os.replace 的竞争；shared-delete 单独不能消除写入失败。

同进程/session 的 Windows mutex 名由规范绝对路径 normcase/SHA256 生成，只接受准确 PID 文件名。锁覆盖完整同步读取或原子写入，不包 await、业务 API 或 worker tick。等待10秒；timeout/abandoned/失败/未知结果严格失败；abandoned 已获所有权仍在 finally release，所有分支 close handle。非 Windows 保留原路径，不加载 WinDLL。无重试、默认值或错误压制。

外部 `windows-observation-probe-20261003T074046Z-155ec46a44/mutex-candidate-20261003T074818Z-4f51c607b0` 六项纯协议检查退出0，包括线程/真实三进程竞争、持有读锁、真实timeout和abandoned释放；独立静态审阅通过。外部7场候选已通过登出20 tick、撤销迟到准备和取消依赖整场，期限场仍运行。上述范围不表示整个M8.1通过；正式与独立重复失败原件均保留。
