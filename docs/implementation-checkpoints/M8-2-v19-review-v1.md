# M8.2 v19 真实预算与取消计数审阅

2026-10-04，main `c426ae7254039bcfb93cef38bae3567a5f9148a1`，CI [37181959680](https://github.com/XintZhang1/HuaKangOS/actions/runs/37181959680) 两平台自然failure：Windows06:33:09 UTC，Linux06:34:09 UTC。v19输入asset609251384，源码胶囊SHA `1e39b364be36face7ebd3b0af3ca5a8995736ebd4361ae2d782d71d519e3f33a`。

两平台各自strict通过（Windows18/Linux22），完整collector3407节点/245文件；实际执行8/101命令，125通过、1失败、3281未执行。matrix1/A25/B33/C35/D14/E7均通过，F10通过/1失败。后续93命令及原18独立收集/203执行尚未运行，不能记完整回归通过。

本轮E已实际通过完整25次有序读取观察及后续24轮、恢复和业务快照断言。Windows原严格PID问题已通过：E实际Popen/worker均1632，F均5116，Run/helper/mode及存活匹配；诊断parent_matches=false符合直接持有实际解释器句柄，不作为放宽原严格PID守卫的理由。

唯一失败为 `test_real_six_hundred_second_budget_survives_owned_process_restart` 第135行。两平台实际执行604.8536/604.646秒，原600秒time_budget/needs_input、原started_at、实际1次请求、心跳推进、两round及旧强杀轮次未知均已越过；第二轮finished为true但usage为None，索引http_requests时TypeError。其后的summary及业务零写快照断言未执行，不继承为通过。

原因经独立源码复核：provider在子任务取消异常上保留安全usage，但heartbeat排空子任务后，runner收到外层取消父任务的另一异常，导致该已知请求计数遗失。按PATCH-M8-2-MODEL-CANCEL-USAGE-01，仅修当轮模型调用局部计数接线，保留原取消/总预算、未知token、权限/fence和全部测试断言；新候选待同输入完整双平台复验。

原件及审阅：

- Windows：`V/closeout-20261003/m82-v19-windows-20261004T063500Z-08cd5cb1e6`，full `20261004T061007Z-ce422a3e33`；artifact11295503628，ZIP SHA `bc2cdcda465f1cf9e4bb0526d3a5221fd0dd73f971bf0d0ed4130230f866e0d3`，1404558字节/60成员；独审SHA `74d53ce8f82996273f1d914ea0d79a5244c9b4cb08e98c002545a822d09977ca`。1304源码映射另与当前Git blobs逐项核同；原件未提供远端全进程树普查或宿主CLI单列退出记录，不补造此类证明。
- Linux：`V/closeout-20261003/m82-v19-linux-unique`；artifact11296385370，ZIP SHA `8997a9b3b7e987890b2aa6c68fcc608dca9b996ada7aae590d8e8667c76821cf`，1401561字节/64成员；独审SHA `9d2a9096ad6d97408065cd27b8945fc58db9bd6c385d030bdae93bdabf20f99a`。

两平台各自strict/full五指纹及三份文件映射一致，输入和依赖未变；实际命令自然排空、无执行器超时或清理终止，真实模型生成0。M8.2仍为唯一in_progress；后续PostgreSQL、真实浏览器/模型、部署恢复及员工条件仍按原计划分别执行。

实现与静审完成：单文件候选位于 `V/closeout-20261003/m82-model-cancel-usage-candidate-20261004T064144Z-c78e0c8be1`，生产SHA `e106fdea33461e963a8f327028eeaf895f6a8fe21aa8a760c2068a91f1963d30`；作者静审 `da6e3630f574f0aa86bc7aa61fa4fea7f4a0ed7a0bfa43cd8cad0585d32aa098`，独审 `42122fedf33bfc46a165e5c56a282da0723a0716c6c1f2005297057bc666fcc4`，root合并核对 `0daf9ba280610f0d133e8656a2975f0aeb04435f05bad2a276625d47d6d52f8d`。逆向原文件字节/整AST及原调用参数均核同；只有当轮局部wrapper与异常usage选择变化。完整801登记输入保持原v19 SHA，使用同asset609251384，不改F或任何断言。静审无app导入/测试/模型；新源码实际双平台复验待执行。
