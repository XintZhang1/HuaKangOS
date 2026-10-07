# PATCH-M8-5-COUNT-ENROLLMENT-15

2026-10-07，属于当前 M8.5 同一增量。M8.5 保持 `in_progress`，M8.6 保持 `todo`，CP-37 保持 `not_ready`，M8.10 保持 `done`。

## 实际问题与原合同

代表复验 rep084731 的四例结构通过，独立语义审阅为 3 可接受、1 普通失败、0 关键失败、0 技术失败。M06 实际读取物资 2 的库位库存，返回 `location_ledger_enabled=false`、`balances=[]`。回答已知道库位账未启用，末句却承诺仅补库位、原因和日期就能准备库位盘点卡，遗漏真实启用前置；没有卡片、业务确认或业务表变化。

`app/warehouse_service.py:171` 对非 `activate` 操作先检查所选物资已启用真实库位，未启用返回 409“请先逐项核对并启用真实库位”。库位 `count` 申请仍须指定一个实际库位、申请数量为零，实盘结果由后续现场待办提交；不将实盘数量提前移至申请阶段。`app/flow_specs.py:146-148` 的 `stock_count` 是原“物资盘点（全店，非库位）”，另按实际全店实盘数量、原因及原复核凭据办理，不能与库位盘点申请混用。

## 精确允许范围

- 仅在 `docs/workflow-source/business.json` 的 `wf-material-stock-count.prerequisites` 补充：所选物资已启用真实库位账并核对；未启用先按原流程核对启用，不能直接准备库位 `count`；选择原全店 `stock_count` 时另按其真实实盘前置办理。
- 使用原生成器同步 `web/workflow-guides.json`、`web/workflow-handbook.html`、`docs/全量工作流手册.html`，保留 193 项需求及 111 条发布工作流。
- 登记本补丁、实际复验检查点、实施计划当前 M8.5／CP-37 记录和架构进度。原业务 API、服务守卫、岗位、动作、申请数量及实盘阶段合同保持。

本补丁不修改 runner、gateway、prompt、测试、manifest、adapter 或评分。已注册 S06、M06、F05、C07 四例及原完整 283／重叠 101 输入保持。

## 异常路径与复验

未启用时停在原核对启用流程；不能猜填库位或历史分配，也不能把全店总量实盘结果当库位账已经启用。已启用时仍依原库位、重复未处理盘点、权限、批准、现场观察和差异复核守卫办理。业务规则 409 不改称权限 403；查询或准备不表示启用、盘点或差异流水已经完成。

事前范围已登记，ROOT 已实施该一项前置及三生成物；原生成器 build/check（193/111）与差异检查通过，A 独立有限静审无静态阻塞。新候选冻结、新 strict、同四原例和从零完整 283 尚待执行，结构通过不替代语义审阅。本次原证据位于外部 `rep084731-terminal/audit.json`、`semantic-aggregate.json` 及 A／C 独立报告，历史失败保留。

聚合证据：`semantic-aggregate.json` SHA256 `2c22faa6c29f9d672565bb0e0f8901f5541a85d97956628c17c46b73a71d9826`。M06 原审阅：`rep084731-semantic-C/review.json` SHA256 `e431d1ea5e8dd4b380a1afe6a3f356e15eca9788ad0db159eadd0c3222019c68`。
