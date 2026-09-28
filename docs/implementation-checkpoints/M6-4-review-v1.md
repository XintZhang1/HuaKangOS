# M6.4 编码审阅与实测记录（默认进入助手，同时保持原人工导航与深链接）

2026-09-28，集中测试阶段。

## 1. 交付物

| 类型 | 位置 |
|---|---|
| 路由 | `web/app.js`：新增唯一判定 `assistantDefaultRoute({store,features})`、`assistantFeatures()`、`loadAssistantFeatures()`、`bootDefaultRoute()`；`boot()` 的空 hash 默认页、门店切换与失败恢复、`hashchange` 空 hash 分支全部改用该判定；不再出现 `location.hash.slice(1)||'work'` 的分散兜底 |
| 导航 | 侧栏顺序改为业务助手、我的工作、快捷操作；评审申请/统计分析/操作指引/十模块入口与角色条件原样保留 |
| 欢迎示例 | `web/businessassistant.js`：新增 `businessAssistantWelcomeExamples()`（+ `businessAssistantReadonlyRole()` / `businessAssistantWelcomeFallback()`），欢迎页改为渲染 ≤4 个岗位相关示例；删除原来固定给所有岗位的 5 个写操作示例 |
| 外部套件 | `V/tests/frontend/test_m6_4.cjs`（6 项，函数体从真实源码提取后执行）、`V/tests/runtime/test_m6_4.py`（6 项接线检查） |
| 未改动 | 原路由与菜单项、需求映射、首次改密流程、集团只读汇总、`#business-assistant` 之外的 hash 语法 |

## 2. 关键实现点（对应计划 M6.4 具体改法 1—6）

1. `assistantDefaultRoute`：`store==='all'` → `analytics/overview`；`features.home===true` → `business-assistant`；否则 `work`。四个开关初始 false，前端只读服务器投影，绝不自改成 true。
2. `boot()` 保持鉴权与首次改密门禁最优先，随后才在**没有有效 hash** 时读取 `/workspace` 并决定默认页；有效深链接（原单、任务、流程、模块）完全优先，不做语法改写。
3. 模型未配置或 `/workspace` 读取失败：`state.assistantFeatures=null` → 默认回原 `work`（可降级），登录不因模型或开关失败而失败；只有服务器明确 `home:false` 才回旧首页。
4. 导航顺序按要求调整，其余条目与 `legacy(...)`/模块入口未删。
5. 欢迎示例取自发布 `workflow-guides.json` 与 `UX_COMMON_WORKFLOWS[role]`（含 `default`）的交集，按 `WorkflowGuides.canEnter(item, role, store)` 过滤，按岗位排序取前 4；`auditor/readonly/statistics/finance_view/group_view` 与集团汇总只保留 `intent==='query_status'` 的查询示例；目录不可用时退回 4 条只读查询示例，不再出现统一的写操作示例。示例只预填草稿，不创建会话、不发模型。
6. 未新增助手 hash 语法；侧栏选事项仍通过已校验引用，原单深链接沿用原路由。

## 3. 实测结论

运行 `20260928T111826Z-e49f524fa7`：`status=passed`（源码指纹 `52bfeaf425f59001580c3a5f8a35822b23794598ab…`）。

- `m64-node-workspace-contract`：6 passed。覆盖 home 开/关/集团汇总三种默认页、读取失败与缺开关时降级不抛错、`features` 显式覆盖；欢迎示例 ≤4 且按岗位顺序、只读岗位与集团汇总只给查询示例、目录不可用退回只读示例且不含统一写示例、示例函数内不含发送/会话/Run 调用。
- `m64-wiring-regression`：6 passed。覆盖唯一判定函数、`location.hash.slice(1)||'work'` 兜底已消除、门店切换与恢复各一处调用、首次改密门禁在默认页判定之前、`/workspace` 读取不含任何写请求、导航顺序与原入口保留、无新 hash 语法、欢迎示例的目录/权限/上限/预填边界。
- 同指纹回归：M6.1（`20260928T111857Z-7f9c93fb12`）、M6.2（`20260928T111925Z-2907d1cb61`）、M6.3（`20260928T111954Z-69f004ae37`）与前端 6 项检查（`20260928T111324Z-518a2326d4`）全部 passed。

## 4. 人工审查要点

- 默认页只在服务器 `home` 投影为真时选择助手；读取失败不等价于开启。
- 深链接优先：任何非空 hash 直接沿用，不被默认页抢占；合法但不可读的原单仍由原页面返回原拒绝。
- 登录路径没有新增会话、Run、Grant 或模型调用；欢迎示例点击只写未发送草稿。
- 集团汇总继续只读首页，不提供写示例。

## 5. 尚未由运行证据覆盖

- 真实浏览器的默认落地、深链接刷新、首次改密跳转与无门店/撤权拒绝：属 M8.4 浏览器验收。
- 十模块 193 项需求名与 111 条发布工作流的完整可检索性：属 M8.2 回归。
- 本项不启动原预览、不调用真实模型、不写公司库。
