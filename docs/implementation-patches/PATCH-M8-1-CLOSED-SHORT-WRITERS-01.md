# PATCH-M8-1-CLOSED-SHORT-WRITERS-01

2026-10-01，当前 M8.1 同一实施项必要事务接线，实施前登记；关联验证已收尾。独立静态追踪已确认 app/main.py add_user、add_users_batch、edit_user、reset_password、add_store、edit_store 六个原管理闭面为同步def，无await；原db依赖在认证前，成功路径真实修改User/UserStore/Store/登录会话/审计/原权限回执并commit。此前127业务清单不包含它们，不能继承旧补丁授权范围或称它们已经修复。

精确允许这六函数db=Depends(get_db)改为get_write_db，保持原全部body/decorator/schema/鉴权/门店/版本/员工普通岗位默认/密码及会话撤销/唯一回执；只修已评审本请求SQLite先读后升写缺口，PG原隔离不改，不重试、不开放管理给模型或助手。

另允许 app/flow_api.py master_list 的db改为get_write_db：原kind=templates且write_store有效时ensure_templates新增approved=False的缺失模板并flush，路由原commit；它是既有条件初始化writer，单独登记，不叫审计或纯读取。保持所有kind分支、聚合店不写、未批准模板、原角色/模板审核与一次初始化合同，不新建API、不删除初始化、不自动批准。入口为有限同步本地函数，无await；其他纯读GET保持get_db。

逆向AST证明仅以上7依赖名称变化，原字节外部留档；独立源审后由新外置原浏览器同一版本闭包/full53核SYS员工、原权限/密码/模板生成与负例。无真实账号/配置/公司库修改；没有动态证据不记passed，原193/111及独立环境/生产门槛保留。
