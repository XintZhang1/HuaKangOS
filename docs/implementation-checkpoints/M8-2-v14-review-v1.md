# M8.2 v14 实际结果及修复范围

2026-10-04，main `de6a166135ddb84b145c9a7d6abf2a8f0b6955e8`、source-only capsule `240cc7913a4d1b90a2d10dec08eb6376891b06dd9fd293f51a73f0568ed36a2f`，CI `37172219196` 两平台自然终局 failure，未取消。原件保存在 V/closeout-20261003，目录如下。

| 平台 | 结果 | 外部目录 / 官方及实际 ZIP SHA |
|---|---|---|
| Windows | 矩阵 1、A25 通过；B33 为 32 通过/1 失败，全部 setup/teardown 通过 | m82-v14-windows-20261004T030117Z-bb5b6ad4c2 / `6b4d200803ffd8a52906003eee22a72aeea0d8faaf64cb3ff2a0af7de9a2ce0f` |
| Linux | 矩阵 1、A25、B33 通过；C35 为 27 通过/8 失败，全部 setup/teardown 通过 | m82-v14-linux-20261004T030117Z-d5d1e4f69b / `05fba2fef18247866264910601ba5ce90e03b04c43e21fe346a11128951cd4c3` |

Windows 原共享快照文件占用错误在本轮消失；B 的原单详情字段修正及原 goal/grant 保持节点实际通过。不能将 Linux B33 成绩补给 Windows；C 之后的命令仍未运行，不计全量成功。

本轮归因及事前补丁：

- Windows cross-owner 损坏夹具随机选第一条通知，可能没有真正更改具有 proposal 归属关系的 owner；固定到实际 graph card 并核实损坏。C 主档不存在 request_id、门店管理拒绝的原分类为 rule，也是测试假设错误。范围见 PATCH-M8-2-V14-OBSERVATION-01。
- 问卷原 200 项列表经已有 gateway 脱敏变为前 100 项加固定尾标记；测试必须观察真实传输合同，适配器须将正常截断造成的缺失表示为未知，同时继续拒绝非法行。配车前置使用原权限允许代办并生成合同的 manager，保留 inventory 原任务事实及原权限。范围见 PATCH-M7-6-QUESTIONNAIRE-BOUNDED-READ-01。
- questionnaire_version/reminder_empty 的 execution-result GET 真实触发 `_LoginRead.active` 缺失。中央回执路径应给原领域权限检查提供已验证的真实账号投影，并固定原身份、查询前后重验；不能添加伪造启用标志。范围见 PATCH-M2-6-RECEIPT-READ-IDENTITY-01。
- supplier_raw 的真实回执与恢复已到成功，测试错将 business_assistant_* 助手状态计入业务零写；service_order 测试错用原规则无创建权限的 manager。仅改真实表边界及该参数的 sales 本人完整链，保留业务表全量比较、单次确认、原冻结证据与另一员工 404。

协作者在不同生产文件和各自外部测试候选中实施；C 的多个函数由 root 顺序合并，不并发覆盖。旧输入、真实失败和源码原件均保留。当前 M8.2 仍唯一 in_progress，修复和独立审阅不等于新一轮测试通过。

双平台独立实件审阅完成：Windows 报告 SHA `66c1e5f6793f90051d36785eb63e9ec179956823ec4ced47a7a5a52b24098f47`，Linux `7caec67fc902182d1439aca99aae0642e3cbbaf6e0a17feeafbd4e03ea2c1491`。strict 分别 18/18、22/22；完整有序 collector 均 3407 节点/245 文件。Windows 实际只 4/101 命令，总 58 通过/1 失败/3348 未执行；Linux 5/101，总 86 通过/8 失败/3313 未执行。两平台各自 strict/full 五输入、三个文件映射及前后依赖一致，输入无变化，全部已执行进程自然排空，无超时，真实模型 0。后 97/96 命令和原 203 独立 unittest 尚未执行。

## 修复静审与 v15 输入

两处生产修复保持原业务权限：回执上下文先固定原身份，再加载和校验真实账号，给原领域只读接口提供 `RequestPrincipal`；查询前后及原 Grant 校验均保留。问卷仅识别 gateway 原有的 100 项加唯一固定尾标记，缺失目标仍为未知，非法行仍拒绝。当前文件 SHA 分别为 `b7a1fa5036ac83fb284790cd2ccdbf6149d7a16dd8b61dc64bcdabfc4e2a8e00`、`6694611d67698bb9b939dfa8af9a4663ee9d48eab4bd23a6e9dd46d6e84ca26f`。

回执独立审阅 `11d56f50518c4de3c9b6f9cf655fb07551bbe372581903fa95114ebaabc01a51` 发现测试末尾仍停用 manager，已改为本参数实际 actor；增量审阅 `87f46e25d6b434980e8ce96d7703031e0dc3bf93136ffd00372fd502aaa22dd3` 确认仅这一调用参数改变，原撤权和零写断言保持。问卷/配车独立审阅 `adbf4cfe57ee536d923f9be13cfa79796fcf1187fc1383382aec1f0f2df6c1fb` 无确定静态阻断；这些均不是测试成绩。

root 按函数合并 B1/C5 共六函数；反向替换可逐字节恢复原文件，全部原函数、装饰器、参数及函数外字节保持。外部目录 `V/closeout-20261003/m82-v15-merged-20261004T032801Z-a7b3357fe2` 留存前后输入、差异与登记。B SHA `5b50a2d37201cfe7b7515fcdeeff644875d4d7c231953828eb3446c6f4505813`，C SHA `754f9f641c4d93924a00687fb50851865098c2f969df95ba5fb1b1b70181b998`。manifest `db7fbcf5ed020fbac0f3ac184fcfd664f939324b6bf15e6be86f7111723d7c1b` 与 restoration `3ed5797e3fd101001fa348b53c243474498174ec38d5821566bb9d368a702c10` 仅同步对应 SHA。

v15 draft `f326669bd8bfbac942a57c3b029cd7674de3c107dca576119c65b567948e5dbb` 的 801 输入中仅上述四项改变，其余 797 实际哈希保持。原 74 数组、101 命令/合成授权及 Linux 适用范围保留；新指纹双平台完整实测待执行，M8.2 仍唯一 in_progress。

最终输入独审 `7a2d873ae59e9851179fab99f939e0fccb2fee8c093bde6fe049ef17f222eaaf` 逐字节核实六函数来源及全部 801 实际 SHA，无确定静态阻断。source-only ZIP `84f241c07ee1ab449eef5602c2baca27ba08cdc7f45052db0645cdb1bd763891`（801 文件、3,332,766 字节）上传到原 draft release `402597955` 的全新 asset `609046788`，官方 digest 与本地一致；没有覆盖旧包。首次封包因输出误位于 V 内，被原安全守卫在写入前拒绝；改用 V 外 capsules 目录后成功，记录留在外部 pack-result.json，不改守卫。
