# 任务：PATCH16 卡片填写范围与员工原名投影

**任务 id 与负责人**：`patch16-card-and-employee-read-scope`；语义审阅 C，向 ROOT 交接。

**目标与交付结果**：修复本轮 D07 空问题卡被说成可补任意资料、Y01 原员工显示名被改写的实际缺陷。卡片投影只列真实待确认问题键；已授权成功且未截断的原账号查询提供紧凑原显示名。

**架构依据与决定**：沿用 `PATCH-M8-5-GUIDE-READ-SCOPE-16` 与原卡片 `questions`、确认答案合并、原 GET 权限。只新增展示元数据，不新增字段编辑能力、查询或默认选择；原 payload、digest、data、权限及确认守卫保持。

**代码快照与影响范围**：起始 HEAD `a90a1c54dce2a337ffea1aff9892e481f934c638`。本任务独占 `app/business_assistant_service.py::proposal_view` 和 `app/business_assistant_gateway.py` 已成功读取后的元数据分支；ROOT 并行负责指南。外部仅沿已登记 gateway/service 卡片测试补有限断言，不改架构总览或 ROOT 进度。

**已完成与当前位置**：已核实际 D07 两卡 `questions=[]`、原 UI 只显示 pending 问题及原确认只合并声明键；已核 Y01 原 GET 200 返回员工原显示名。两个生产投影已落盘；已登记 gateway 文件追加一个原账号 GET 节点，原 service 卡片测试补空问题、真实键及已办理不可编辑断言。原测试字节与差异保留于 V 外部报告，登记由 ROOT 统一处理。

**下一步**：交 ROOT 独立静审及统一登记，冻结后由原 runner 执行必要节点与 D07/Y01 真实复验；本任务不提交 Git 或启动 runner。

**验证与实际阻塞**：四文件 AST 解析通过，未改函数的顶层 AST 逐项等值，`git diff --check` 通过。未运行测试、app 导入或真实模型。当前无实现阻塞；后续独立静审、同输入定向无网及原例真实复验待完成，不宣称整个 PATCH16 通过。
