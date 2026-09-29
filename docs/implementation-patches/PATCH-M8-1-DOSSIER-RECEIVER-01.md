# PATCH-M8-1-DOSSIER-RECEIVER-01

2026-09-29；M8.1 保持 `in_progress`。业主本轮授权继续实现并执行离线验证。

## 已复现缺陷

`dossier_grant` 的两条决定事实（`dossier.approval_recorded`、`dossier.revocation_recorded`）
只读取原详情顶层 `decisions`。原 `dossier_grant_service._detail` 按合同只在 `source_side`
（发起店）下发 `decisions`；接收店只得到 `status`、`effective_status`、`can_read` 等字段。
因此在接收店侧，这两条事实恒为“未知”，跨店授权事项无法按原批准推进。

## 精确改动范围

仅 `app/assistant_runtime_domains/dossier_grant.py`：

1. 模块顶部按原名导入 `dossier_grant_rules.STATES`（别名 `RECEIVER_STATES`），不另造状态名。
2. `fact_snapshot` 在拿到原详情后，先按 `source_side` 分流：发起店仍走原 `decisions`；接收店走
   新增的 `_receiver_fact`。
3. `_receiver_fact` 只使用原详情给出的 `effective_status`：
   - `approved` → 原批准已登记且当前仍有效（原店独立复核 + 接收侧可读性实测），批准键成立、
     撤销键不成立；
   - `revoked` / `cancelled` → 撤销键成立，批准键不成立；
   - 其他已登记状态（`pending`、`rejected`、`expired`、`suspended`）→ 两个键都不成立，并给出
     对应原状态中文说明；
   - 未登记或非字符串状态 → 未知，不推断。

## 保留的边界

- 不改原授权状态机、独立复核、到期、撤权或接收人绑定；只读原详情，不调用任何业务 command。
- `dossier.record_readable` 仍必须由本次原 `/record` 成功读取证明，不由有效状态推断。
- 403/404 仍按原合同返回未知，不区分“不存在”与“不可见”。
- 请求的快照读取仍按发起店口径；接收店不因此获得原决定明细或原单内容。

## 异常路径

- 接收店详情缺少 `effective_status`：返回未知并要求到原页面核对，不猜。
- 授权批准后又被撤销：批准历史仍在（批准键成立），撤销键成立，接收店 `/record` 由原接口拒绝。
- 到期或权限变化导致原接口把有效状态降级为 `expired`/`suspended`：不满足批准键。

## 测试精确范围

`tests/assistant_offline/tests/test_repair_warehouse_grant_facts.py` 的 `GrantDecisionActions`
（含大写变体、非字符串动作、缺失/空决定列表）与 `GrantReceiverSide`（六种有效状态、撤销判定、
未知状态、`record_readable` 仍独立探测、403/404 保持未知），以及 `DossierNativeGrant`
三项真实 `/api/dossier-grants` 用例：待复核为未批准、批准后发起店与接收店分别得到一致的
等价事实、撤销后接收店 `/record` 被原接口拒绝且有效状态为 `revoked`。
