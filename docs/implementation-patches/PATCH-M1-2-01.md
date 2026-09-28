# PATCH-M1-2-01：AssistantWorkPlan 的 stores 外键与已发布 h52j 对齐

2026-09-28，集中测试阶段发现并修复；不动已发布迁移，不改业务规则。

## 现象与证据

新增的 M1.4 外部套件 `tests/runtime/test_schema_parity.py` 在候选源码上首次运行即失败
（run `20260928T055323Z-0751c9cdb5`，`m14-schema-parity` 4 passed / 1 failed）：

```
business_assistant_work_plans.foreign_keys
  migration: [(('context_snapshot_id',), 'business_assistant_context_snapshots', ('id',)),
              (('owner_id',), 'users', ('id',)),
              (('session_id',), 'business_assistant_sessions', ('id',)),
              (('store_id',), 'stores', ('id',))]        ← h52j 建了 stores 外键
  orm:       [ ...同上前三条...,                       ← ORM 的 StoreScoped.store_id 没有外键
              ]
```

其余 13 张助手表的列、外键、索引、唯一约束、CHECK 名称两侧完全一致；差异只有这一处。

## 归属

- `migrations/versions/h52j_assistant_work_plans.py:12` 明确写了
  `sa.Column('store_id', sa.Integer(), sa.ForeignKey('stores.id'), nullable=False)`；
  `app/models.py:23-25` 的 `StoreScoped.store_id` 只有 `Integer, nullable=False, default=1, index=True`，
  没有外键；`AssistantWorkPlan` 直接继承该 mixin，于是 ORM 与已发布实例不一致。
- 已发布迁移只追加、不重写（AGENTS §10），因此只能让 ORM 描述真实的物理约束。
- 影响面：`Base.metadata.create_all` 建的夹具库缺少一条已发布实例上真实存在的引用约束，
  schema 漂移探测（M1.4 验收）失效；业务行为本身不变（计划总是引用真实门店）。

## 精确改动

`app/business_assistant_models.py`（AssistantWorkPlan）新增一列声明，覆盖 mixin：

```python
    store_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('stores.id'), nullable=False, default=1, index=True)
```

保留 `nullable/default/index` 原语义，外键不命名（与 h52j 的匿名物理约束一致），
其余列、约束、索引一律未动。

## 复验

| 运行 | 内容 | 结果 |
|---|---|---|
| `20260928T055323Z-0751c9cdb5` | M1.4 未修复 | failed：1 项（本补丁） |
| `20260928T055616Z-2dfd3d3e71` | M1.4 修复后 | passed：5 + 1 |
| `20260928T060914Z-5e452d642a` | M1.4 与后续改动同指纹复跑 | passed |

源码指纹 `fce9783476ef263f4e55782afccc2e104f5ab0053db34d341621a7885492444b`。
补丁同时覆盖 `tests/test_business_assistant_migration.py`（历史 e13r→f24s 升级与独立恢复）
与新增的 ORM/迁移全链一致性断言。
