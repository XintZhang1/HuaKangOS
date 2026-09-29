# PATCH-M8-1-WAIT-TEXT-01

2026-09-29；M8.1 保持 `in_progress`。业主本轮授权继续实现并执行离线/页面验证。

## 已复现缺陷

原生截图与本轮原控件复现都显示事项侧栏把等待原因的内部状态机标识直接显示给员工：
侧栏事项行渲染 `等待：employee_continue`，当前事项面板同理，计划步骤列表渲染
`wait_reason`。同一个等待原因还会在计划投影里出现 `native_prerequisite`、
`external_fact`、`completion_conditions_missing`、`source_inaccessible` 等标识。
这些是助手状态，不是业务话术，员工无法据以判断下一步。

## 精确改动范围

1. 新增 `app/assistant_runtime_labels.py`：等待原因到固定中文文案的唯一来源。
   只做标识到文案的映射，不判断业务含义；无法识别的标识返回 `None`，由各处回退文案负责。
2. `app/assistant_runtime_schemas.py`：`WorkspaceItem` 与 `PlanStepView` 各新增可选字段
   `waiting_label`，保留原 `waiting_reason` / `wait_reason` 不变（前端守卫、排序与测试仍按原标识）。
3. `app/assistant_runtime_workspace.py`：事项投影在构造条目时按 `waiting_reason` 填
   `waiting_label`，只补显示字段，不改变分组、排序、版本或授权判定。
4. `app/assistant_runtime_plans.py`、`app/assistant_runtime_api.py`：计划视图与旧计划兼容视图
   在生成步骤时同样填 `waiting_label`，覆盖运行时投影与 legacy 投影两条路径。
5. `web/assistantworkspace.js`：侧栏事项行、当前事项面板和计划步骤等待列表改为只显示
   服务器给出的 `waiting_label`；没有文案时整条等待信息不显示，不再显示内部标识。

## 保留的边界

- 不改等待原因本身的取值、产生条件、条件判定或跟进授权；`employee_continue` 等标识仍留在
  接口契约中，只是不再出现在员工可见文案里。
- 不为未知标识编造文案；`waiting_label` 为 `None` 时不显示等待行。
- 不修改原业务状态机、卡片、确认接口、通知或功能开关默认值。

## 异常路径

- 服务器返回未知等待原因：`waiting_label` 为 `null`，界面不显示等待行，不显示原始标识。
- 服务器返回非字符串标签：前端 `waitingText` 视为没有文案。
- 计划步骤缺少 `wait_reason`：`waiting_label` 为 `null`，不参与步骤等待列表。

## 测试精确范围

`tests/assistant_offline/tests/test_repair_warehouse_grant_facts.py`（`WaitLabelText`）覆盖文案映射、
未知标识不猜、`WorkspaceItem`/`PlanStepView` 的字段契约；
`tests/assistant_offline/tests/assistant_plan_ui.test.cjs` 覆盖六个真实内部标识不出现在侧栏 HTML、
无文案时不显示等待行、`waitingText` 的类型守卫。原生浏览器页面记录另记于本轮检查点。
