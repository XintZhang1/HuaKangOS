# PATCH-M8-1-VEHICLE-ASSIGNEE-LOOKUP-01

2026-10-01，M8.1。vehicle02 原采购/主档passed，CSV资金/发运/接收均原点击已办理；到新local_move主管“转交当前待办”时，原GET /api/flow/lookup/user 返回404“查询类别不存在”，modal未建立，整场failed。原源码 web/vehicleoperations.js:47 写 user，而 app/flow_api.py 原支持 employee，按当前店eligible_users查询；这是产品接线缺陷，不降低断言或借admin/后台assign绕过。

允许仅 web/vehicleoperations.js 中该 reassign GET 从 /api/flow/lookup/user 改为已存在 /api/flow/lookup/employee。原候选值/标签、员工本人Task、原VO reassign POST、Case版本、门店/岗位服务守卫和全部其他动作不改。注册源仍有关联验证在运行，本页先登记；必须所有关联实例收尾后才执行生产修正，Node/差异及独立只读短审后全新vehicle三场景复验。记录真实404与原失败，不把局部CSV三项拼成完整六项通过。
