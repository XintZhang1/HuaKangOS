# PATCH-M8-4-UPLOAD-WRITER-01

2026-10-01，M8.1。所有本轮四组验证已退出。member-boutique-reports07 原 POST /api/flow/cases/106/files 返回503，原日志为 SQLite OperationalError code5/517；实际首次附件提交保留失败，后继三场不继承局部父。源码原 upload 在共享 get_db 的 auth/read snapshot 后追加文件，存在与已观测文档/报表相同的延后事务升级窗口。

仅 app/flow_api.py 原 upload 的 db 依赖改为既有 get_write_db，并位于 get_user 前；SQLite 在认证/读取前取得原写事务，PG 沿用原实现。原大小、类别、扫描、私有文件、岗位/门店/原单权限、同事务文件与审计、响应均保留。无重试、延时调整、接口扩大或其他路由改动。AST/代码审阅不等于实际通过；后继全新完整父及附带精品/积分/报表待重验。
