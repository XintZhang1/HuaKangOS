# PATCH-M8-4-VEHICLE-ASSIGNEE-EXPLICIT-01

2026-10-01，当前连续浏览器点击交付授权内，独立生产diff源审发现接手员工默认第一候选风险，先登记。当前53四实例仍执行，生产/注册冻结；全部退出前不实施。

仅web/vehicleoperations.js的reassign assignee_id下拉增加空value“请选择接手员工”首项及required；保留实际lookup/employee、原真实岗位候选和后端权限/状态/版本，不改全局voOptions，不默认管理员或其他员工。实际API可返回admin并按原业务允许明确选择，UI加载候选不能默选它。

仅tests/browser_click/vehicle_operations_business.py在原移交表单分支核初始value为空/required、未选的原生validity为false，原填其他项后未选提交不发业务POST且全部原业务行不变；明确选择真实员工后按原成功路径继续，原事件/任务/版本/回执/人员ID守卫不降。异常时留原失败，不能补造或重放旧移交。AST/JS及独立短审后新镜像最小VO闭包与必要新全注册联合复验；不改四开关/门禁/193人工或生产授权。
