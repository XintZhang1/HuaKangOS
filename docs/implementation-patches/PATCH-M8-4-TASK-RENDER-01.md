# PATCH-M8-4-TASK-RENDER-01：销售后继原任务交接等待实际渲染

2026-10-01。完整 `automatic-business-20261001-08` 27/27执行、26通过，销售后继HK017在主管打开原Case113之后立刻查Task310交接按钮，瞬时count为0；原截图仅“正在读取…”，本次原Case GET为200且尚未发生交接POST。75项完整自动check与3项失败场景局部诊断分别留证，整轮退出1，不拼接为通过。

精确源码范围只有 `tests/browser_click/sales_followon_business.py` 的responsible主管交接分支。包本次原FlowCase GET，核id、当前Case CAS、本次开放Task id/key/assignee/version；待原h1标题及精确唯一按钮真正可见，再由员工原点击。共享login/Evidence、原AssignInput三字段/版本/原因、Task/CAS/权限及旧行Guard不改，无固定sleep、直接API提交、业务重试或请求号重放。

结束关联人工02实例后修改，语法及独立增量短审，再全新外部镜像验证原有限前序和销售后继。原失败库不重用，人工02定向显示六项通过另留同指纹报告，不换算193全部接受。根维护本补丁、计划/进度和当前登记文件。
