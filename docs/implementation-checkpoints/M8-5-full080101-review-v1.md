# M8.5 full080101 部分真实模型回归审阅 v1

2026-10-07。M8.5 `in_progress`、M8.6 `todo`、CP-37 `not_ready`、M8.10 `done`。本次从零全量在技术故障处中断，不能把前47例或37代表拼成原283完成。

## 冻结来源和已完成的前置验证

受测 HEAD `662b085`、source `897bf4b9e723eb6a51d43197eb8ed8599c489281e173caa9afa7b681f3e54261`，external `aa58ae5e...`、harness `71a82dca...`。同输入 post-rebind strict `20261007T073232Z-611683be12` 自然 passed 18/18、零模型调用，run SHA `e1a3d2962e86e8cb1579c22db4d40163e90fd8e88d1960cb9b68c8acef891372`。新 gateway 原 API 节点 `20261007T073312Z-8442ec293f` diagnostic passed 1/1、零模型调用，run SHA `a72f60741d27fd2a637687c304fdfc6924af3626eaa2b469f364e39ddf72f7eb`。这些不替代本次付费场景审阅。

原失败代表37例 `20261007T074423Z-b32a03ad7d` 自然 passed，原结构37/37、独立语义37可接受／0普通／0关键，run SHA `f377c7e4da2976abd8bd1b1b8220698fc195edae046963b8b3553b0d8e79f1d1`；仓库外聚合 `rep074423-terminal/semantic-aggregate.json` SHA `57d789e497f27307c7a24d75559055fc88bf73044b41e9dd5d848101f8ee0fd0`。该选择最初按旧全量失败清单冻结，不是所有37例在最终纠错后仍失败；Y07纠错见下节。

## full080101 的实际终态

从零运行 `20261007T080101Z-7eb0d1f095`，`--all --thinking`；run.json SHA `900e16b395a6456f4df99a311e5dfc9c5b10d2e440fb833879d96bf1da632b6a`。自然 CLI1、未超时、进程排空：47个原case文件落盘，其中46例原/R4结构通过，C07为技术失败；236例未运行。模型请求221次，八项源码/镜像/overlay/依赖/harness/外部输入/manifest/全部输入不变性为真，`commands_ok=false`、`phase_complete=false`、`milestone_complete=false`。终态审计 `full080101-terminal/audit.json` SHA `3c6ec93745a6b09d8ee92c0b6702831971e693598743680a764f22035d5faf00` 证明47例各467业务表前后等值、零确认；此项不将C07计为结构或语义通过。

C07 已成功读取两条静态续保工作流说明，但随后 DeepSeek 请求在取得 HTTP 状态前发生 `RemoteProtocolError`；原live gate阻断内部重试，无法取得完整用量。Runtime只留下失败兜底答复与零卡，属于 `provider_call_failed` 技术中断，不是业务拒绝、正常回答或普通语义错误；下一C08未产出。本轮不能续接47/283，也不能借用上次全量的余236例。

三份独立终稿按实际完整答复、卡、成功 `tool_trace` 和 `runtime_records` 中失败调用逐例审阅47个已落原case，聚合 `full080101-terminal/semantic-aggregate.json` SHA `203f8063654d6fb601f69e77ae62198442b18747560cf1d0b03811f9760ad2d3`：

| 分片 | 已审 / 分配 | 可接受 | 普通错误 | 关键错误 | 技术失败 | 未运行 |
|---|---:|---:|---:|---:|---:|---:|
| A | 16 / 73 | 15 | 1 | 0 | 0 | 57 |
| B | 16 / 73 | 15 | 0 | 0 | 1 | 57 |
| C | 15 / 73 | 13 | 2 | 0 | 0 | 58 |
| ROOT | 0 / 64 | 0 | 0 | 0 | 0 | 64 |
| 全批 | 47 / 283 | 43 | 3 | 0 | 1 | 236 |
| 同批原101重叠集 | 47 / 101 | 43 | 3 | 0 | 1 | 54 |

三份 `review.json` SHA 分别为 A `5b292b7b5eaed7fefc8dcdc8129e8d898b295d44d2b471e0abd95cb2b423b911`、B `dcc77fe9bb23f3e7f0c75a564672719fccae8a544c8422c12c90737e305130b3`、C `02ae8fced6199c9722f67b84cf424e7240a1d40cda001410cdec3e2f78068042`。普通错误仅以下实际三例，旧成绩不继承：

- F05：来源未选且只查询了开票来源列表，回答却保证选定后可从经营主体快照核对销售方抬头和税号、员工“不让你手抄”。原详情 `issuer` 可能为 `null`，申请仍要求真实销售方两字段；该保证越过已读事实，卡数0、金额列表本身正确。
- S06：纠正零卡数量后的最终可见答复仅说卡数与“其它结论不变”；上一答并未交付员工，因此未回答员工所问原订单进度、本人下一步和同事待办。原事实已读且无写入，属于答复完整性错误。
- M06：拒绝直接改库存正确，但末段把现场实盘设成创建库位盘点申请的前提；原申请先填物资、实际库位和安排，批准后才形成现场清点待办，再记录实际观察、复核差异。未生成卡、无库存写入。

旧全量 `20261007T052312Z-25326e65c5` 的 Y07 初判只看简化 `tool_trace`，漏了 `runtime_records` 中两次实际只读工具岗位预检失败。原审计和各分片保留，单独附录 `full052312-terminal/semantic-aggregate-v2.json` SHA `0d2b546710fbffba96d2a801bb4de4a1199b83c14db2211e6338ef75b51be92d` 将该例纠正为可接受；现行旧全量聚合为247可接受／35普通／1关键，同批101为99／1／1。PATCH13最初选37例按登记时清单保留，不倒写成37个最终失败。

## 费用、补丁与待验证

终态审计记 10985 次累计尝试：10977笔已结、原7笔未知、C07一笔 `reserved`；本轮新221次中220笔结算2.319612元，1笔无完整用量。累计已结245.450981元，原七未知保守占66.322432元，加本次预留保守占5.242880元，共317.016293元；400元／12000次门禁、固定预留额与旧费用保持。原终态1笔reserved经B独立审阅后锁内仅转为uncertain_occupied，0预留、8未知、halted=true/reason=unsettled_reservation；`full080101-terminal/ledger-conversion-installed.json` SHA `4be8b5ca47f8164b8e2fa1250105ded5bd015ddc7bc8bedcfd184ee1aa94f8a2` 证明原账本SHA `f1e066b9af1041a8aa6bbf1eafad9ae8a97ff2fcc792acc463ce68552ecfd2ab` → 安装后SHA `441b611af06905804504ac68e6b927a9a7289db0de6cbca3284b198aa5c3f3e6`，仅该行状态变化，旧费用/全历史保持。

[PATCH-M8-5-ANSWER-COMPLETENESS-14](../implementation-patches/PATCH-M8-5-ANSWER-COMPLETENESS-14.md)已事前登记：仅收窄 Runtime 纠正轮完整答复指令、原开票列表既有 notice 和原盘点指南的申请／实盘前置，三生成物同步。原业务 API、权限、确认和评分不变。生产差异有限静审已完成且无静态阻塞；后续冻结同输入 strict、受影响原四例真实复验、从零283／同批101逐例审阅均须新证据；不得由47例部分成绩或37代表放行 M8.5/CP-37。M8.6仍未启动，员工试用与人工验收不代签，`total_plan.md`不改写。
