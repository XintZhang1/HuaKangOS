# tests/historical —— 历史遗留，不参与测试集

这个目录里的文件**不是测试**，不会被 pytest 或 `scripts/verify_candidate.py` 收集（两者都按
`test_*.py` / `*_test.py` 匹配文件名）。放在这里是为了保留仓库历史的可追溯性，不构成任何通过证据。

| 文件 | 来源 | 为什么不能跑 | 如何恢复 |
|---|---|---|---|
| `batch_entry_dealerdesk_p4.py` | DealerDesk P4 批次录入线（提交 967db54、2d69414、6c14f19，位于本仓库历史中） | 导入 `app.schemas.EntryDraftInput`、`app.main.DEFAULT_BODY_LIMIT`、`ENTRY_DRAFT_BODY_LIMIT`，这些名称在 huakangos 线中不存在；它此前以 `tests/test_batch_entry.py` 存在，导致本目录的全量回归在**收集阶段**就中断 | 需要先把 P4 线的 schema 与批录入接口引入本线（当前没有该模块），并补齐迁移、权限/岗位/门店边界测试；之后可改回 `test_` 名称并纳入测试集 |
| `login_lockout_dealerdesk_lineage.py` | DealerDesk 线的登录限流身份改进（同仓库历史中的 commit「Stop using a shared address as a login-lockout identity」） | 导入本线不存在的 `LOGIN_FAILURE_LIMIT`、`LOGIN_FAILURE_WINDOW`、`identifies_a_client`。**注意：本文件描述的“共享出口地址被当作登录身份、任意陌生人可锁死全店”问题，在本线当前 `app/security.authenticate` 中依然存在**（同一用户名或同一 IP 失败 10 次即锁 15 分钟） | 作为一次**有安全影响的行为变更**单独确认后再移植（只让全球可达单播地址参与身份计数，并抽出可配置上限/窗口），同时补齐“成功登录不清零历史失败”“运营商大内网 100.64/10 不算身份”等用例 |
| `visualization_dealerdesk_lineage.py` | DealerDesk 数据可视化线 | 请求 `GET /api/visualization`，本线没有挂载该路由；`app/visualization.py` 的 `visualization()` 在本线没有任何 router 或前端调用者（本线的数据可视化是 `#analytics/overview` + `/api/flow/analytics`）。它此前造成 27 项失败 | 先决定“数据可视化”保留哪一套；若要恢复逐日聚合接口，需重新挂载 router、接回页面并补岗位/门店范围校验 |
| `feedback_maintenance_dealerdesk_lineage.py` | DealerDesk 反馈与维护线 | 请求 `/api/feedback`、`/api/maintenance/status`，这两个接口在本线不存在（`maintenance/` 目录是开发维护工具，不是这里的路由）。它此前造成 11 项失败 | 若确实要做员工反馈/维护开关，需单独设计接口、岗位、状态机、审计，以及与“业务助手 → 问题清单”的关系 |

## 约定

- 放进本目录的文件必须去掉 `test_` 前缀，并在文件头写清来源、不能运行的原因和恢复条件。
- 不要为了“让全量回归变绿”而把这里的历史文件改成能通过的样子；要恢复就按上面的条件正式引入。
- 本目录不进 `MANIFEST` 的通过统计，也不要引用为验收证据。
