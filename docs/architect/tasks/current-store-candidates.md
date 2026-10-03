# 任务：代表表单的当前门店候选

负责人：Codex 子代理 day_boundary。范围为 M8.1 的 PATCH-M8-1-CURRENT-STORE-CANDIDATES-01；不推进 M8.2，不维护共享进度或实施计划。

2026-10-03 主代理在正式 80 场与 26 场重复自然退出后，授权登记补丁并仅修改 `tests/browser_click/requirements_click.py` 的 `representative_forms`。另一个活跃候选使用仓库外冻结 scripts 副本，本次仓库测试文件不属于其动态输入。生产 app/web/迁移和依赖继续冻结。

只读诊断确认：原新增员工表单的管理员身份、默认 sales、全部门店未选符合合同；原场景已创建启用门店 3、4，初始化 manifest 仍只有 1、2，造成固定数量误报。旧原失败及后续门店创建时刻分别保留。

实施要求：捕获本次原页面使用的同源 GET `/api/users` 响应，以当前启用 ID 全集严格比较 UI 候选，拒绝重复、缺失、多余及默认预选；候选、checkbox、默认岗位先写仓库外证据再断言。保留九表单、193/111、原权限与取消零写入合同，不发额外请求。

当前状态：补丁已登记，实现已落盘，作者静态审阅通过，主代理复审及原生动态验证待做；没有启动验证、修改隔离数据或改写原失败报告。

实现只改 `representative_forms`。原指引按钮点击前监听同源且精确 URL 的 GET `/api/users`，读取该响应 JSON，不发额外 HTTP；证据只摘取门店 ID/启用状态及安全响应元数据，不保存账号列表。候选 JSON/结构不合法仍拒绝；UI 候选按 ID 全集严格比较且禁止重复，默认 sales 和所有 checkbox 未选分别保持严格断言。

原门店合同断言前，`employee-current-store-candidates.json` 立即写入当前场仓库外 evidence，原 checkpoint 同时记录候选来源、岗位及 checkbox。后续任何候选/默认授权断言失败均保留这些已取得证据。原 HTTP 或表单尚未可见时的失败仍沿原网络/失败截图证据，不伪造不存在的表单字段。

静态检查：仅 stdlib AST/UTF-8，退出 0，无 U+FFFD；`git diff --check` 退出 0。差异为测试文件 43 行新增、3 行删除；文件 SHA256=`fc28f3384053d588b85c6f8ed4c4a76a0b7eb2086ba1512afdab714443513d4b`。生产及共享执行器未修改，193/111、九表单、原岗位、原关闭按钮、取消零写请求与原业务摘要门禁全部保留。静态检查不等于验收通过。

建议由主代理安排最小动态顺序：`runtime-original-admin-access-revoke-inflight-prepare` → `runtime-original-source-map-seven-producer-transaction-rollbacks` → `requirements-representative-forms`。沿现有 SCENARIOS 顺序在全新隔离实例选择这三场，真实产生门店 3、4 后检查九原表单；本任务没有启动或注册这次回归，不增加凑数场景。通过后仍由主代理重建冻结指纹和安排正式全量。
