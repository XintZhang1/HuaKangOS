# 原同步写入口独立审阅 C

2026-10-01，PATCH-M8-1-REVIEWED-SHORT-WRITERS-01 的第三组独立静态审阅；只新增本页。未导入 app、未启动应用/浏览器、未跑测试、未读数据库、未修改任何生产或已注册测试文件。静态结论不代表业务通过。

## 集合与结论

以外部 `V/browser-click/launches/reviewed-short-writers-127.json` 的 `file` 去重排序，审阅第 29–41 文件，共 **13 个 API 文件、37 个精确同步入口**。原字节为 `V/browser-click/launches/short-writers-before-20261001/app/`，不是 Git HEAD；JSON SHA256 为 `f368df1018df2a4eb2f662ceba3a859f1a78badc75e1f1b10ad36d847f2cc521`。

未发现本组确定静态阻断。35 个原 `Depends(get_db)` 只替换为 `Depends(get_write_db)`；2 个原写依赖保持（vehicle_procurement.command、warehouse.allocate）。只有 vehicle_imports.command 同时把 db 移到 user 前。37 个入口现在均先取写 Session、再 get_user，全部同步；原路由方法/路径/decorator/status、函数体、请求模型、动作解析、权限/CAS/任务/原件/回执/返回没有变化。原 GET、纯读 POST、其它闭面及异步上传函数保持原 AST。

逐字 unified diff 只有 .db 导入、上述签名及 db helper 三行变化。对每个原模块 AST 做精确定点转换（.db 导入增加名称、清单函数 db 默认值、唯一 import command 参数顺序）后与新模块全部 AST 相等；不是只核修改行或用函数名猜所有 POST。已独立核对当前全 app 显式 get_write_db/get_audited_read_db 参数，没有 auth-first 的函数。原 router/decorator/include_router 无提前依赖的基础结论保持，本文未重做全部另外两组作者范围的审阅。

## 当前逐文件集合与字节指纹

表中的替换/已有均指本 127 清单选出的函数，hash 为原字节/当前字节完整 SHA256。

| 第几项 / 文件 | 本组函数 | 数量 / 替换 / 已有 | 原 SHA256 | 当前 SHA256 |
|---|---|---|---|---|
| 29 `app/service_intake_api.py` | `appointment_action, appointment_create, binding, preset_active, preset_create, resource_action, resource_active, resource_create, rework_action, rework_create` | 10 / 10 / 0 | `4001e55a5c4dc7341298130edda6cca26e24ced56d696a1405b4d6085ce50323` | `db6aae030cd83c6ec051e2e291c1f7ca50d865befa927f0c48a90667d99b7b84` |
| 30 `app/service_orders_api.py` | `command, create, income, payee` | 4 / 4 / 0 | `8f1145db0749807cb2a233ff55704442e789b6e10607bf9c88d622ab93e2fbd4` | `87bea688027a617864dabf8cbe4b0c2cbbc20534ca0d41d9868f54df61491b97` |
| 31 `app/transfer_api.py` | `command, create` | 2 / 2 / 0 | `b4c50ddc752eb756049c0604de298dea5be63c349df6ee451dafbb1abaab395b` | `60ad1e81df279e3b81a28d964211d44c9faaaf532b509d2ebd864d8693d223a1` |
| 32 `app/transfer_exception_api.py` | `command, create` | 2 / 2 / 0 | `4298d93caeefdc282b31c6fcd702759b3d064817942405fbb0092eb1600f1681` | `51f14f76f5252b7bd6f6697b951c2d6cfff7a6cbcb38144194829dff04498747` |
| 33 `app/transfer_goods_recovery_api.py` | `command, create` | 2 / 2 / 0 | `3215909b3ced83456406dfd32cc8408c02c479ae3fe97037e70946c6eaca2721` | `58556cdbaa2ce8f3a9f93c1cb1f3af5cc9bb21e8c764f7095d0b5fbc6cae2294` |
| 34 `app/vehicle_catalog_api.py` | `entry, model_assignment, vehicle_assignment` | 3 / 3 / 0 | `2de2db892362745fda6774275798e8cedff93cca95e438e1e12cad34d48c7a0e` | `679bea9845bff3e7321d9ddaecc8fa1d177ae53997df4e26dce151ef38bb8b50` |
| 35 `app/vehicle_imports_api.py` | `command` | 1 / 1 / 0 | `470515d9d9107a25a1e91332e3b23ac26ca900aef94d30520f2bceeef8674f87` | `76a35add0e5ac11e00b030735d7174a3ddb2d911f307890b098cc579519e799c` |
| 36 `app/vehicle_income_api.py` | `command, create` | 2 / 2 / 0 | `459441ba42cbd039e9205d5982bf739d65171a8db101586162cec3e10584deb8` | `be53276ef84eaf4321fb3e639f70e1cdfeac8bf0043fbddce755ca3d6701c4e4` |
| 37 `app/vehicle_operations_api.py` | `command, create` | 2 / 2 / 0 | `10b15091daf01006f15b0656fa8cd646c9a81dbf9efcc37922018111a6c10acf` | `bd98fe297af2032422b423255d86933cb18b525337bb77123671e7b37c9d5854` |
| 38 `app/vehicle_procurement_api.py` | `command, create` | 2 / 1 / 1 | `6ffc844dcfbb8d432ff955b45d49e4e1fa8ec0934cad9f859abed1ddfbb11e3f` | `3853d7e1c212321cfbf23777b30c92c35b751fa1bd9661250520122d566d68b2` |
| 39 `app/vehicle_transfer_api.py` | `command, create` | 2 / 2 / 0 | `d9b29c641823df2c342cc4c015b95f22c63906e964f8c2d091afbfaa77deffed` | `c9d9ecfc1f75bac0f8984879f806a0ed9ca41a6499a50012e2a28f200575df7e` |
| 40 `app/vehicle_transport_api.py` | `command, create` | 2 / 2 / 0 | `110af09b64f1996898d365effb42f8d4dfe75c3bd5a884296be5f5126706d8b4` | `558a8b49944dfa45419516c20a74729db4987793cab4ce6d0fa5be8e9485bf86` |
| 41 `app/warehouse_api.py` | `allocate, command, create` | 3 / 2 / 1 | `b4e0f9970bcf8e0a6104c58067bba6d2497e3141cd275679e27646c60a6c13ad` | `fdfc1ccc78ba84a8bd8536c2879522723df54119056be3b736b535edf0023f44` |

`app/db.py` 原 SHA256 `bf6df8b8db8812073ba1e15130a6c2c5537aa054481bc216aa062628d4b45d45`，当前 `d7d9143dcfec6eb663dc1fe9f3aad77aa79462b4bd06e685fcd517803399ed89`。全 14 份当前源字节在本页落盘前再次复核一致。

## app/db.py 请求级 OptionEngine

真实 delta 仅 get_write_db 的 SQLite 分支：原 Connection execution_options 改为 `db.bind = db.get_bind().execution_options(huakangos_sqlite_write_transaction=True)`，随后 `db.connection()`；增加一行说明注释。模块其它 AST 完全不变，包括 make_engine、SQLite begin/connect 事件、默认 Engine、SessionLocal、get_db finally rollback、PG 的 REPEATABLE READ 和 get_audited_read_db alias。

本机 SQLAlchemy 2.0.50 源码静态依据：

- `orm/session.py:2784–2787`：原 SessionLocal 单 Engine、无 per-mapper/table binds，后续 ORM SQL/flush/get_bind 使用同一 Session.bind。改 bind 不换 Session、identity map 或 db.info 当前门店。
- `engine/base.py:3060–3077/3333–3360/3369`：execution_options 返回请求持有的新 OptionEngine，共原 pool、继承父事件；它的 options 不写到原 Engine。
- `engine/base.py:165–170`：新 Connection 从其 Engine 取得 options/事件。`orm/session.py:1191/1244` 从 bind.connect 后 begin，故原 `app/db.py:34–40` begin hook 可以在认证第一条读 SQL 前看到 True 并选择 IMMEDIATE。
- `orm/session.py:1312–1330/1407–1423`：commit 关闭此次 Connection；没有重置 Session.bind。rollback 后后续取连接同理继续从此代理获得标志。默认 get_db 和 Worker 的独立 Session仍原 Engine，池复用不把代理 Engine options 赋给其它新 Connection。PG 不进入该分支。
- `FastAPI dependencies/utils.py:280–313/603/639–659`：签名顺序解析、默认缓存相同 get_db callable，db 与 user 共同持有本请求 Session。get_db 构造无 SQL，get_bind/dialect 读取也不开始事务；明确先 db.connection 再认证。vehicle_imports.command 重排同时携带对应默认值，无错配。

方案前提仍是首次 Connection 前接线；不能在已有读事务后换 bind求修复。本组实际签名符合此前提。没有全局 Session hook、HTTP method 猜测、重试、回放、改变原 request_id 或降低 CAS。提交后的 describe 短读也会使用本请求写绑定，需新隔离点击验证实际锁等待/耗时，不能由静态结论宣称无 busy/517。

## 待实测与审阅边界

本组只核第 29–41 文件与 db helper，不替代另两组完整集合核对、原三失败场景复验、同指纹全 53 联合或 193 业务/人工验收。普通读/Worker、PG、写入后下一事务、真实原权限/CSRF/CAS/幂等/全旧行/任务/回执及负路数据保护均保留实际复验门槛。另开 Session 的 refusal、管理闭面、同步 I/O 和异步上传的原事务阶段没有被本补丁自动证明或扩大。
