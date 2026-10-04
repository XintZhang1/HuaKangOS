# M8.2 v15 实际结果与故障观察

2026-10-04，main `12371312f2820428ae01888d11c3e1e0b0b1153a`，source-only capsule `84f241c07ee1ab449eef5602c2baca27ba08cdc7f45052db0645cdb1bd763891`，CI `37174392421` 两平台均自然终局 failure，未取消。Linux 03:45:16 UTC、Windows 03:53:29 UTC 完成。

| 平台 | 官方及下载 ZIP SHA | 外部原件目录 |
|---|---|---|
| Linux | `711a88f9288fc153bd2b887b909605d69614f415612f1a5b9aa6ffc08f162aa3` | V/closeout-20261003/m82-v15-linux-20261004T034628Z-7b29212f80 |
| Windows | `a7eeba74dcf60766cce873b4c608406fd27af634056e62a2efd4be231ff4e92a` | V/closeout-20261003/m82-v15-windows-20261004T035511Z-045a2d6869 |

两平台 matrix1、A25、B33、C35、D14 实际通过，E7 为 5 通过/2 call 失败，全部这些节点的 setup/teardown 通过。上轮跨 owner 损坏夹具、C 的八个失败点及两处生产修复已在本轮实际覆盖；这些成绩不能代替剩余原基线、独立环境和业务验收。

Linux 独立实件审阅 SHA `a7644ac10014cccf40f4c014c0371b012a8bf6d35ecb3b047403a02c0dcaaf17`：strict22/22；full 只执行 7/101 命令，113 passed / 2 failed / 3292 not_run，剩余94命令及原203独立节点未执行。collector3407唯一节点/245文件、已执行数组与登记一致；strict/full五输入及三个来源映射一致，全部输入和依赖前后不变，实际进程自然退出并排空、无超时，真实模型0。Windows 原件已验证官方 digest、ZIP CRC及安全提取，完整独立审阅另补，不拼接平台成绩。

Windows 独立实件审阅追加 SHA `1e5d76e9d0702e38a5ceb3dfe47e6c0245a92db9e09ce3e0fc270f6929d1080d`：strict18/18；full 同样只7/101命令，113 passed /2 failed /3292 not_run。collector3407唯一节点/245文件、全部已执行数组及逐节点聚合与登记一致，无遗漏、多余或重复；后94命令及原203节点未执行。该平台独立核实strict/full五输入、三个来源映射、前后依赖与输入一致；全部8条实际命令自然排空、无超时、无setup/teardown错误或skip、真实模型0。以上为该平台原件自身结果。

两处失败及精确范围见 PATCH-M8-2-V15-CHECKPOINT-OBSERVATION-01：

- 准备回滚测试的 after_commit 误将原 WakeEvent 两次 SAVEPOINT 释放算作外层提交；仅改实例监听的分类，外层仍要求零提交，原第三行故障及完整回滚断言保留。原失败在最终回滚断言前终止，不预称回滚通过。
- 真实 GET 故障子进程在 checkpoint 前退出3。固定 stderr 哈希只能识别 helper 输出的 RuntimeError，实际原原因未知；钩子签名已核一致。补有限结构化阶段诊断后再复现，不猜测修改生产或放宽原断言。

当前 M8.2 仍唯一 in_progress。新候选、指纹及执行结果尚待统一登记与实跑；四默认关闭开关和全部剩余技术门槛不变。

## v16 观察候选

原 E 单函数的提交监听已分类：两个纯读取断言同时要求外层及嵌套提交为零；准备写入阶段记录合法 SAVEPOINT，外层仍零提交。原第三行故障和完整回滚断言保留，实例监听在 finally 移除。最终源 `aeef0b8b0aae2499182be5af2fb7a5ed9bd11aea9a8deae99b129ea5c7193239`；独立增量审阅 `1c7a3f426aac8705d4e2801120c8ac441e5923e9c6706a9ba41eae83ed5fee53`，前候选和两处 read 断言补强均留存。

原 child/helper 仅增加固定 schema 诊断与当前命令证据保存，原 GET、provider 响应、35 秒等待、断点、24/600 预算及 owned kill 保持。`_finish_run` 观察当前 handled exception 时只取固定类型及静态位置，原函数和异常原样委托；不读取正文、参数、locals 或模型内容。worker `f6d8521f1cf5f25c2a3ba328451cb3e2fa5f9c4fcc1aa2b8e3431490863d9d6b`、support `237b2d7704e10c482cc1aec1f2594977dad578fad2564f2aa47788f0dfa526d3`，独立审阅 `851e823732be9cbda3d4e443b0bf61b612624fba10e1e3369c73d51728542b9e`。诊断不表示原故障已修复。

统一合并目录 `V/closeout-20261003/m82-v16-merged-20261004T040820Z-516d97af39` 留存前后源与登记。manifest `4614ad2f0c89a43d1b2a6459f20c7b3fc669c5f7317e02b2093336beb935e39b`、restoration `b27cf37a56d1f42fc55bd71330e64111fe7b3324e674144d8f0230259c0a5970` 仅改三个对应来源 SHA。v16 draft `a80ab9a50929a833c03c23d220cd21d33a705ac2da01fcb6070252c19d682dd1`，801 输入精确5项变化，其余796保持；74数组、101命令/授权及原平台适用规则保持。新指纹完整执行待实测。

最终登记独审 `1c643882f37483be8425d2bf3f418e18cac2699dfc8ac8d790ab782ca3b56821` 核实801实际SHA、五项登记及全部原有序数组/命令/授权保持，无确定静态阻断。source-only ZIP `519e60ee37dfa5df99063db69a43605cd2b0fe9383c56a99b6208f97ededbe79`（3,335,740字节）已追加上传原draft release402597955的asset609102816，官方digest一致；旧包未覆盖，生产代码本轮未改。
