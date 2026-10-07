# M8.5 full020839 失败与后续候选审阅

2026-10-07，当前 M8.5 仍 `in_progress`，M8.6 `todo`，CP-37 `not_ready`。这里保存实际运行结果，代表和不完整全量均不替代新候选的完整 283/同批 101 验收。

## 同输入冻结及代表更正

冻结 main `b65288d1628fce002d64a7bdf6bf53f1ac9758a9`；源码指纹 `1cf154180d9f89b7b0b5ad5b7a4dd69b64e6a56a0bf94f7f539096506983e044`。外部输入 `c345a207945efd296bcd5436bcbc7c8fe912e44dedf7c51117f7473fa1cea1e9`、锁 `3910945cf6063ebe984b40cc22667657bd83476dcca1024ef4884b10f01dc930`、已装依赖 `e537a94af533e550a48e512063354bc101cc12ab2a9e696bbe0aa7ea207b618a`。

门禁重绑后的 strict `20261007T020034Z-19b0b954d0` 为 18/18、0 模型调用，run SHA `25fc21604ac907d182ea7a382b3df6a597ad06c1095ed461c3872001e4538147`；当时 harness `8852ae6266e66adfb44e1172b4ab0ff38b4ff00658ba9a61a566d53a384813a1`、manifest `f2020c9e123a64c76292a77a15b6bd7bff4ff28bfb30e6d5bea813e56a9bf0bc`、gate `2ad422d873e48d9f6b2bcb8f48a5a994b5028807d789678a03c5308fb1f4f29e`。独立 ACK 后两代表 `20261007T020317Z-bcdf70bc49` 自然退出、结构 2/2，run SHA `e1caa173a9932f6ca3a5dc11c081631f0225ce0e21f395d32411d1b118b82158`。

F05 的来源计数和 Y07 组合岗位初审正确；初审 2 可接受意见保留。随后对照申请 Create 与原页面，F05 只写“开票日期”，没有区分 `due_date` 计划办理与后续 `issued_on` 实际开票日期，独立审阅追加普通失败更正。现行代表语义为 **1 可接受 / 1 普通失败 / 0 关键错误**。更正不继承为下面全量意见，不覆盖初审报告。原更正 `V/closeout-20261007/m85-rep020317-semantic-C/adjudication-F05-date-20261007.json` SHA `1d97b0d5054d30641bf6c84fd8174fe5f97017523a9231a40a1496a498cc1a3b`。

## 全量实际执行与语义

`20261007T020839Z-9f9f238ff7` 通过当前员工登录、原 Run 入队、Worker 和真实 `deepseek-flash` 从零执行。CLI **1**，1672.39 秒，未超时，进程已排空；在 D03 发出新模型请求前预算上下文抛 `PermissionError`。原件实际落盘 66/283，217 未运行，未继承任何历史案例。

原/R4 结构均 66/66；已执行 66 例均属同批 101 重叠子集，其余 35 项子集未完成。独立 A 逐例最终意见：58 可接受、8 普通失败、0 关键错误。B/C 所负责 HELP 全部没有本轮原件，不计通过。原 283、101 及评分字节没有修改。

| 原例 | 观察到的实际问题 |
| --- | --- |
| S03 | 卡中回访结果与日期正确，但先说已记录原单、后说点击才写入。 |
| V03 | 集中补问整车采购资料时遗漏原创建必填经营主体。 |
| V05 | 车辆/真实库位未选，未获明确委托却多准备库位主档卡，末句与实际卡数矛盾。 |
| V08 | 岗位与请款行引用正确，末句超出原能力，承诺自动生成/带出完整 CSV 行。 |
| M03 | 已读子领料可见、父维修404，却承诺再给单号/车牌就能本人核实父单。 |
| M04 | 来源未明时等待正确，却将新版库管退料方式套到旧来源，并承诺本人能读父单。 |
| F05 | 来源和计划日期列得正确，但把两个零额来源列为当前可选，并笼统承诺选定即可备正额蓝票。 |
| F08 | 正确拒绝虚构车辆余额到账，却补充未经原车辆单证明的维修月结/内部承担分支。 |

V02/D01 的无效读工具 422 已恢复，审阅保留技术异常，不因此伪称全程无错误。66 例各 467 张业务表前后完全等值；11 张实际 proposal 均 pending，0 业务确认/执行。卡片准备成绩不当作办理闭环。

全量 run SHA `b1820958492fa941a85e51311ad334850acc797cf7077feffad640e4b811052e`，summary SHA `631a3a75f443486d9bbe917817e62a7bdd2c9c7267813cf4b0a052ec4292bf38`；五输入及八项不漂移标记一致，命令完整性仍失败。A 逐例 `V/closeout-20261007/full020839-semantic-A/review.json` SHA `b77722a06fed40bef347e1332dc9ce465e4e36bcede14745684477b928d19d94`；C 技术终审 `full020839-semantic-C/terminal-review.json` SHA `b101f28ad8e6e4943f3b47d6ae5c6b6b04559a3c44b0e0ffb90be799d8db27e8`；root 停后审计 `full020839-terminal/audit.json` SHA `00f082448f849fc5b6166fa831dcfdb2fa81d32511fc102ffb7e7ba6af3ad297`。

## 费用与执行器原因

本轮 345 次请求全结算 3.647656 元；累计 9535 次，9528 settled，七个旧未知仍按 66.322432 元保守占用，0 reserved。累计已结算 228.716453 元，保守合计 295.038885 元。400 元/12000 次门禁不变。独立审阅后 root 只将 ledger 的 `halted/halt_reason` 改为安全停止；旧行与全部费用保持。停前 SHA `3f3bba75f40f69438dfb17d419aff09c5f22a5548377e74c8bb28c8ace7031cd`，停后 `d4cea2e0dfa467b5b8357cbb4052384a2151549a21ed2350559180bedf47f1bb`。

`V/closeout-20261007/ledger-fileshare-diagnostic-A/review.json` SHA `2564d6c8b2cfd2c0e0825c9956b7a7cfdc7dd012b287eecb7d6b54be5e1b3381` 以独立 marker 复现并发 `Get-Content` 阻挡 `os.replace` 的 WinError 5。与 root 同期读取真实账本、异常调用点、D03 无新请求高度吻合；未捕获原内层栈，不将具体出错行写成已证实事实。恢复时付费进程运行中完全不读取可变共享账本，观察已落盘案例预算快照，终态排空后才核账。无需给写入器增加重试或修改预算合同。

## PATCH08 候选及尚待工作

按 `PATCH-M8-5-NATIVE-FIELD-SEMANTICS-08` 两生产文件实施精确字段说明和边界表述；gateway SHA `0addad65ec4264b076fd2ec24880701dd00b739e69ac21d5ff58a2100dd266cf`，prompt SHA `335b6f4fccf57585be63061e7027f2611b46711395911b02db80d265c149dbde`。root 人工审阅认为原 schema、单位、默认值、权限、确认和业务写守卫保持；AST 2/2、`git diff --check` 通过。独审指出采购经营主体一致性只在原接口取得冻结 context 时检查，文案已按该实际条件收窄，空目录不声称已冻结。独立 C 静审已通过，外部 patch08-static-review-C/review.json SHA 47599eff9f1fa949bdcd3aa20f62f9c239310cf27ca791e583d5d6e28e05f9c2；新输入冻结尚待，不能沿用 b65288d 的 strict 或实际成绩。

下一步完成独立审阅与原九代表选择登记；冻结新源码和输入，取得同输入 strict、受审门禁重绑和 post-strict，再独立 ACK 才付费。受影响八例及 Y07 保护通过后，从零完整 283/同批 101 并逐例语义终审。M8.6 不并行实施；独立保留集仅准备不调参草稿，正式封存等待最终候选冻结。员工验收由业主安排，生产部署不自动执行。
