# M7.10.4 编码审阅与实测记录（调拨货物找回适配器）

2026-09-28，集中测试阶段。M7.10 组第四项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/transfer_goods_recovery.py`：`TransferGoodsRecoveryAdapter(FlowCaseAdapter)`，`object_types=('goods_recovery',)`；快照只读 `GET /api/transfer-goods-recoveries/{key}`（**key 即原 GoodsRecovery.id**）；`read_receipt` 走 `GoodsReceipt` 族 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='transfer_goods_recovery', object_types=(GR_OBJECT_TYPE,), operation_ids=(GET /api/transfer-goods-recoveries/{key}, POST /api/transfer-goods-recoveries, POST /api/transfer-goods-recoveries/{key}/actions/{action}), fact_keys=GR_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_transfer_goods_recovery.py`（8 项） |
| 未改动 | 原 `transfer_goods_recovery_api.py`/`_service.py`/`_models.py`/`transfer_goods_search_service.py`、迁移、权限表、数量与负担公式、状态机；未新增 signal hook |

## 2. 确定映射表（从 reviewed catalog 与原 schema 核对）

| 用途 | operation_id | path_args | 原响应 / 回执族 |
|---|---|---|---|
| snapshot / 事实 | `GET /api/transfer-goods-recoveries/{key}` | `{'key': <GoodsRecovery.id>}` | 原找回案详情（`status`、`transfer_id`、`facts[]`（`GoodsFact`）/`postings[]`（`GoodsPosting`）按原详情提供） |
| 只读来源 | `GET /api/transfer-goods-recoveries/origins/{transfer_id}` | `{'transfer_id'}` | 原来源读取（登记为只读来源，不作为结果 operation） |
| result | `POST /api/transfer-goods-recoveries` | — | 原创建响应 |
| result / receipt | `POST /api/transfer-goods-recoveries/{key}/actions/{action}` | `{'key','action'}` | 原动作响应（match/inspect/ship/receive/plan/approve/reject/dispose/restore/finish_bad）；回执族 `GoodsReceipt` |

事实键与满足条件：
- `goods_recovery.match_recorded`：原 match 成功结果及 `GoodsFact` 的**明确原损失匹配**；
- `goods_recovery.receipt_recorded`：原 receive 结果及**实物接收 `GoodsFact`**；
- `goods_recovery.restore_posted`：原 restore 结果及 `GoodsPosting`；
- 三条都带边界声明：**unlocated（未找回）不等于已找回**；**找到或收到实物不能替代损失恢复过账或赔付退回**；明细未提供一律未知。

## 3. 实测结论

运行 `20260928T142154Z-7c6541d030`：`status=passed`，`phase_complete=true`（源码指纹 `38d3b91418f455d0e9e4dbe0c1d14d3a8778ab281968a8e668692da343bc57fd`）。

- `tests/runtime_domains/test_transfer_goods_recovery.py`：**8 项通过**。覆盖四条 operation 在 reviewed catalog、四个原 service 函数、四个原模型、不动态导入/不写库/不抢回退；**注册到达运行时注册表**（Spy 捕获 spec）；快照 key 即找回案 id、ID 不一致 502、**缺原调拨单引用 502**、无门店身份 403、动作可用性 `unknown`；三条事实的满足/未满足/未知分支（含"未找回不等于已找回""只有实物接收不算过账""明细未提供必须未知"三条显式断言）；未登记事实不猜；`extract_result` 边界；回执保持冻结 `request_id`、未绑定 `unsupported`、只读详情 422。
- 本轮**一次如实拦截 + 一处产品修复**：首轮"详情未提供事实明细"返回 False 而合同要求未知——因为"容器键存在但值为 null"被判成已提供；已改为**只有 list/dict 才算提供**（这是真实的产品缺陷，非套件问题）。

## 4. 未完成/未验收（如实登记）

- 本项只完成 `transfer_goods_recovery` 一个适配器；M7.10.5 起 19 个小项仍为 `todo`，按编号串行。
- 事实明细的判定沿用原详情实际提供的字段；未提供时按合同未知。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
