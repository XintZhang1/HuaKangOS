# M7.11.3 编码审阅与实测记录（系统只读面适配器）

2026-09-28，集中测试阶段。M7.11 组第三项。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 新适配器 | `app/assistant_runtime_domains/system_readonly.py`：`SystemReadonlyAdapter(FlowCaseAdapter)`，`object_types=('report_query',)`；受控只读原语 `read_stores` / `read_parameter_catalog`；**`fact_keys=()`** |
| 显式注册 | `app/assistant_runtime_domains/__init__.py`：`DomainAdapterSpec(name='system_readonly', object_types=(SYS_OBJECT_TYPE,), operation_ids=(GET /api/stores, GET /api/parameters/catalog), fact_keys=(), fallback_object_types=())` |
| 外部套件 | `V/tests/runtime_domains/test_system_readonly.py`（5 项） |
| 未改动 | 原 `main.py`/`parameter_api.py`/`user_access_service.py`/网关、迁移、权限表；未新增 signal hook；**未注册任何写 operation** |

## 2. 结论摘要（先读，经核对）

1. reviewed catalog 内本域**只有两条只读**：`GET /api/stores`、`GET /api/parameters/catalog` → 均实现为受控原语；
2. 计划点名的 **`GET /api/users`、`GET /api/audit` 不在已评审 catalog 内**（原封闭面）→ **没有已评审读取可用**，
   适配器只在文档里说明该边界、**绝不调用**（套件断言不存在该调用，且只有唯一受控读取入口）；
3. **`MANAGEMENT_READERS` 与原 `CLOSED_DOMAINS` 仍是权威**：适配器调用原接口，不代替岗位判断、不借用管理员身份；
4. **`fact_keys=()`**：查询权限配置**不产生授权生效、密码变更或员工创建完成事实**（四条副作用型事实键逐一验证为未知）。

## 3. 实测结论

运行 `20260928T143357Z-28c6ff6399`：`status=passed`，`phase_complete=true`（源码指纹 `3b69b217f278aa112cd769f521ba3773be5a7c39004358be6a02fa6259ab3798`）。

- `tests/runtime_domains/test_system_readonly.py`：**5 项通过**。覆盖两条只读在 reviewed catalog、`users`/`audit` 不在目录内、本域无写 operation、网关仍含 `MANAGEMENT_READERS`/`CLOSED_DOMAINS`、不动态导入/不写库/不抢回退、**封闭面读取只作说明绝不被调用**；注册 spec 只含两条只读且 `fact_keys=()`；两条只读各只发一次调用、状态码映射（403/404→404、422→422、503→503）、无门店身份 403；四条副作用事实键全部未知且**事实层零读取**、快照的核心提供查询边界（503 + 零读取 + 类型 422）；结果恒空、GET 快照式提交按契约 422、只读回执理由仍在源码中声明。
- 本轮经历 **2 次如实拦截**（见下节），最终通过。

## 4. 实测发现并修复的问题（全部如实保留）

1. 套件用"源码不含该字符串"断言未使用封闭面读取，而适配器**文档字符串**正当地说明了这两条路由 → 改为断言**不存在该调用**且**只有唯一受控读取入口**（产品代码未改）。
2. 套件把 GET 形状的提交期望为 `unsupported`，实际按契约在**快照校验阶段即 422**（GET 不属写回执族）→ 与其它只读领域统一口径（产品代码未改）。

## 5. 未完成/未验收（如实登记）

- 本项只完成 `system_readonly` 一个适配器；M7.11.4 起 14 个小项仍为 `todo`，按编号串行。
- 若评审希望放开用户/审计读取，须显式扩目录（本项不擅自扩域）；真实原库与真实模型属 M8.x。
