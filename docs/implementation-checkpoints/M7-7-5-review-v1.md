# M7.7.5 编码审阅与实测记录（维修套餐适配器；含一处读取维度不匹配）

2026-09-28，集中测试阶段。M7.7 组第五项。

## 1. 结论摘要（先读）

本项发现并如实登记一处**读取维度不匹配**：登记对象类型是 `package_purchase`（原 `PackagePurchase.id`），
而本领域已评审的读取只有 `GET /api/repair-packages/members/{key}/purchases`（**按会员**维度），
**不存在按购买 id 的已评审详情读取**（套件断言目录中 `GET /api/repair-packages/purchases*` 为空）。
按共同合同"缺必要 ID 返回无法建立依赖证据、不让模型猜 ID"，适配器**明确报告该不匹配并零读取**，
三条购买事实一律未知；可判定部分（写结果绑定、回执合同）照常实现并实测。

## 2. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/repair_package.py`：`RepairPackageAdapter(FlowCaseAdapter)`，`object_types=('package_purchase',)`；`read_snapshot` 报告不匹配（503 + 原页面入口，零读取）；事实按合同未知；`extract_result` 绑定原写接口返回的购买；`read_receipt` 由已评审 resolver 绑定 |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='repair_package', object_types=(PACKAGE_OBJECT_TYPE,), operation_ids=(members/{key}/purchases, rules, POST purchases, orders/{key}/capture, orders/{key}/quote, purchases/{key}/actions/{action}, refunds/{key}/actions/{action}), fact_keys=PACKAGE_FACTS, fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_repair_package.py`（6 项） |
| 未改动 | 原 `repair_package_api.py`/`_service.py`/`_models.py`/`repair_package_aftercare.py`、迁移、权限表、组件与金额公式、状态机；未新增 signal hook；未扩大 reviewed catalog |

## 3. 实测结论

运行 `20260928T135316Z-d145c0ac9b` 之前的失败与修正，见第 4 节。最终运行 `20260928T135316Z-d145c0ac9b`：`status=passed`，`phase_complete=true`（源码指纹 `3b49bf9a12cedde422882b0e4ac99924e950198f3884ee2901be8e942946d60f`）。

- `tests/runtime_domains/test_repair_package.py`：**6 项通过**。覆盖：目录中只有按会员的读取且无按购买 id 的读取、原 `purchase_info`/`PackageLot` 读法与四个原模型；注册经 **Spy 捕获 `DomainAdapterSpec`** 校验对象类型/含本项 operation 的字面值/不抢回退、不动态导入/不写库；**不匹配时 503 且零读取**（`captured == []`）、无门店身份 403；引用类型四类非法输入 422；三条事实未知且理由含 `members/{key}/purchases`；未登记事实不猜；`extract_result` 对三种写响应绑定购买、对只读面不绑定、失败响应不绑定；回执保持冻结 `request_id`、未绑定 `unsupported`、只读面 422。
- 本轮**一次返工**（如实登记，见下）。

## 4. 实测发现并修复的问题

- 首轮套件把"注册含本项 operation"写成在 `__init__.py` 源码里找**字面 operation 字符串**；而实现使用常量（`PACKAGE_MEMBER_PURCHASES` 等），断言因此失败。已改为**用 Spy 校验注册到达运行时注册表并检查 spec 内的字面 operation**——这比字符串扫描更强，且不因常量抽取而失效；产品代码未改动。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `repair_package` 一个适配器；M7.7.6 起 26 个小项仍为 `todo`，按编号串行。
- **待评审**：补一条"purchase→member"的已评审只读映射，或提供按购买 id 的详情读取；在此之前不声称套餐事实已可用。
- 真实原库、真实模型、浏览器与员工试用属 M8.x。
