# PATCH-M8-1-VEHICLE-HIDDEN-FIELDS-01

2026-10-01，M8.1。vehicle03 已真实local_move与other_out completed；切原other_return后本店vehicle_id和recipient仍可见，196原失败截图、select动作及DOM断言留外部。原native change已按类型设置四label.hidden；实际index加载web/styles.css的label display:grid覆盖UA隐藏，属于真实显示缺陷。不是未加载的style.css，不弱化候选或force隐藏。

所有关联四实例退出后，允许只在web/styles.css追加 #modal 下四VO data属性的[hidden] display:none：data-vo-vehicle/original/location/recipient。不全局重写hidden，不影响帮助print或其它模块；原JS/真实选项/POST/CAS/任务/门店/岗位/原车代次与数据均不改。CSS/差异及独立短审，新vehicle最小3场景复验，原严格hidden断言保持，失败与局部四项不继承六项passed。
