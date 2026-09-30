# PATCH-M8-1-LOGOUT-TRANSACTION-01：退出时避免陈旧 SQLite 读快照升写

日期：2026-09-30。依据：本轮真实浏览器 Fresh06 慢查询期间退出，原 Cookie/CSRF 的 `POST /api/auth/logout` 返回 503，页面保持登录；原服务日志记录 `OperationalError`。该轮未记录原错误码，不能将候选原因写成已捕获的 517 原文。

原 SQLite WAL 引擎显式 `BEGIN`，`get_user` 读取真实会话、账号和门店后，worker 可提交写入；logout 再从读事务执行删除会话存在陈旧快照升写冲突。先以全新仓库外两连接合成库定向核对这一模式，证据外置；不读取真实账号、库或凭据。

精确允许修改 `app/db.py`、`app/security.py`、`app/main.py` 及当前计划/审阅记录。在原 begin 钩子中增加仅由服务器代码设置的 Connection execution option `huakangos_sqlite_write_transaction=True`，该连接用 `BEGIN IMMEDIATE`；其余连接继续原 `BEGIN`，PostgreSQL 不改。

退出 helper 仅在 SQLite 回滚已完成的认证读事务，以上述短写事务重新执行原 `get_user`，再次核对 Cookie、会话有效期、账号启用、CSRF、门店及岗位，然后只删除本次真实会话并提交一次。原退出路由调用该 helper，只有 commit 成功才清 Cookie。没有重试循环、删除重放、新的业务权限或事务全局改动；连接选项不来自请求、模型或配置。不恢复未知提交，任何读取、写入或提交异常仍由原处理器报告。

待核对异常路径：worker 写入时真实退出成功；重新核验拒绝或提交失败不清 Cookie；其它连接仍使用原事务模式；连接回池后选项不传播；不重放业务/助手 POST。复验保留同一套13组点击、完整原需求覆盖与真实业务摘要门槛。此修复不启用生产或替代其它原 M8 验收条件。

实测与审阅：外部 `runtime-v1/auth-logout-probe-20260930/report.json` 在全新两连接SQLite库复现原BEGIN读快照升写517，核对Session连接选项在begin事件前生效、新短事务顺序及回池选项不泄露；未导入仓库app，不读取真实数据。三生产文件独立审阅完成，集合SHA256 `aaed12b3f35d8fe32eacb61409ebdb696ce3aeb0c1219e707836ba5bd31a4346`。automatic07同次13/13、exit0，慢查询时原生Cookie/CSRF真实退出200、登录页保持且迟到回复不污染；与其它场景同一生产/脚本指纹。Fresh06未捕获的原错误码不补写为517，探针机制证据独立保留。重新核验/提交失败不清Cookie由调用顺序源码审阅支持，本轮未注入这些故障，不冒称异常注入通过。详见v2浏览器检查点。
