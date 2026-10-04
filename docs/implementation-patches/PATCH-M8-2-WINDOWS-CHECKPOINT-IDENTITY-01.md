# PATCH-M8-2-WINDOWS-CHECKPOINT-IDENTITY-01

2026-10-04，v17两平台已自然终局，Windows原件独审确认同一E节点在 `_runtime_support.py:268` 的PID/Run身份组合断言失败，尚未到Linux的读取次数断言。原件没有marker、proof PID或Popen子PID，不能确定哪个条件失败。CPython3.11.9 Windows venv redirector源代码支持二级进程可能，不能以此替代本次实际身份证据或直接放宽守卫。

允许 V 原 `_runtime_read_worker.py` 的既有checkpoint新增 `parent_pid=os.getppid()`；原 `_runtime_support.py` 读marker后仅记录固定整数/布尔诊断：Popen PID、proof PID及父PID，pid/run/helper/mode匹配和进程存活状态。文件只写当前已登记命令的证据目录，独占创建、flush/fsync；不写原始marker、异常/流内容、参数、身份资料或凭据。拆开原组合身份断言但保持全部严格要求、原helper哈希/mode、35秒等待及exact Popen handle kill/cleanup不变。既有诊断schema和原provider/24轮600秒/真实GET/业务断言不变。

为先取得Windows这条明确缺失证据，允许 `.github/workflows/full-regression-checks.yml` 与其现有手动caller增加默认false的有限 `windows_only` 选项；与既有linux_only同时为true时在启动验证前拒绝。默认仍跑两平台，运行统一原strict/full入口；不删任何命令或断言，不恢复浏览器job。此轮Windows定向执行不构成双平台验收，最终必须同一冻结候选两平台完整通过。

day仅在独立外部候选修改两helper，mobile独审；root负责工作流、三源码候选及SHA登记合并和统一调度。与PATCH-M8-2-READ-OBSERVATION-01共同形成下一输入包，原v17失败和全部源文件保存。M8.2仍唯一in_progress，未执行或后置断言不记通过。
