# M8.2 v21 全量失败与定向修订

2026-10-04，main `c269f5e962657d468747c932ab4331d1164da203`，[CI 37188128764](https://github.com/XintZhang1/HuaKangOS/actions/runs/37188128764) 两平台自然 failure，未取消或重触发。使用同一 source-only asset609410676 / SHA `54fe594476256e59abe59f4864f8402b73283f01b9e5b6a86fcbd40eb558acd1`，801源输入。此次两平台均实际执行101/101命令，不能以已跑完代替验收通过。

| 本轮原件 | Linux | Windows |
| --- | --- | --- |
| strict | 22通过 | 18通过 |
| 全量最终节点 | 4151通过、87失败、10原平台不适用 | 3473通过、89失败、686准备阶段错误 |
| pytest | 3333通过、64失败、10原平台不适用 | 2655通过、66失败、686准备阶段错误 |
| 原203 unittest实际执行 | 198通过、5失败 | 198通过、5失败 |
| 命令执行时间累计 | 8058.308秒 | 11882.934秒 |
| 自然job终局 | 10:27:31 UTC | 11:31:49 UTC |

两平台均完整收集3407有序pytest节点/245文件和原203有序unittest节点；4248个结果均有终态，未执行、重复、缺漏均0。各自五输入、源码/harness/外部输入映射和43项依赖前后不变，命令leader正常排空，未触发命令超时或强制清理；Windows九项测试内部20秒子进程超时另计真实失败，不能与外层命令超时混淆。Windows1308源码逐项与该Git HEAD一致。无独立远端CIM全树普查证据，不补造证明。真实模型0。

Linux先前核心matrix/A/B/C/D/E/F本轮126项、b01验证合同657项均通过，真实600秒等待及后置计数已实际覆盖。Linux87项分为旧业务夹具/合同14、Runtime领域及UI旧合同50、Node旧VM/界面合同18、原unittest旧登录重试与registry5。修订保留原节点、真实业务事实与权限/完整性/无重放负例，不回退已批准的产品行为。具体范围见 `PATCH-M8-2-FULL-FAILURE-ALIGNMENT-01`。

Windows另有686个setup WinError32，首次发生于赠品完整原链通过后更换本次合成库时。旧测试的raw SQLite context只结束事务而未close，不属于SQLAlchemy池；先核直接前序及同类文件清单，修正测试资源生命周期。原PowerShell九个call都在20秒超时，原因尚未确认，只补确定性非交互调用及有限原输出，不提高上限或把诊断写成修复成功。范围见 `PATCH-M8-2-WINDOWS-FIXTURE-LIFETIME-01`。

独立原件均位于 `V/closeout-20261003/`（V为正式NTFS验证根）：

- Linux `m82-v21-linux-unique`：artifact11301430002，3718695字节/2051成员，ZIP SHA `02be2ad624897bad24446bb0e098b0e3b1bb418d91f2fd7a85c3eb9320113280`；独审SHA `e34f87c67c4bb346d15bd50583eb06539499766e0989589ccbfaaff979dbbdfc`。真实strict `20261004T081240Z-d034e6ca07`、full `20261004T081249Z-175aad7eaa`。
- Windows `m82-v21-windows-20261004T113728Z-a331285487`：artifact11301688391，3905314字节/2045成员，ZIP SHA `8cd27997a9af7b4723778dc69e656e7ca24144d73bea985771b05d10394b0f7a`；独审SHA `9de7c82720dcfccaf8b5e5b8f2442a2f6de4b79cb2d5eef20550843f15c55f5e`。真实strict `20261004T081247Z-57b5e34351`、full `20261004T081303Z-928e81df35`。

修订首先在全新外部 `m82-v21-repair-candidates-20261004T111905Z-c9fe9a268b` 的before/candidate完成，未改本轮CI冻结输入；静审和独审后才合入注册来源。下一步原统一M0.1 strict、M0.2.B diagnostic与已注册M6/M7定向入口，再新同候选双平台101完整回归。进度输出只增加stderr命令序号、名称、结果和耗时，stdout JSON/超时/授权/终局守卫保留。M8.2仍唯一in_progress；PG、真实模型、独立Windows/Linux环境等后续技术门槛仍待原顺序执行，员工试用及人工验收不预记完成。

2026-10-04 v22候选已实际合入外部注册来源：129个已交叉静审的测试/夹具/执行器源文件，加两份来源登记，共131输入变化、670/801保持原字节；原319归档、全部命令/节点清单保留，9条Linux preview不适用规则仅重绑overlay SHA。合入前实际检查无本地验证进程，v21两平台已自然终局。新draft SHA `8be5fe1a17554916fa34d62c5ae4ff48209ad12b86fd280914d17b65b6b61f23`；下一步统一strict和原定向入口，尚未执行新候选动态检查，不记通过。 合入记录 `closeout-20261003/m82-v21-repair-candidates-20261004T111905Z-c9fe9a268b/merged-registration/merge-result.json`，SHA `080410b348bbd5c8274ba9332ab34fefaf9489da8ab26957e2259258506019a8`。Windows 80文件/193处另经独审 `2194080ff212703cd7a1831a74373eec3d0ec1b1221aa912c9abff5924dd95ad`；所有动态修复结论仍待实跑。

2026-10-04 v22定向实跑：strict `20261004T120855Z-001d54f089` 18通过；M0.2.B diagnostic `20261004T121130Z-b2b9a85767` 原657合同+27节点=684全过，阶段/里程碑仍false；25个既有M7入口202节点全过，同五输入、正常排空。M6.8 `20261004T120953Z-12bffdc9cc` 执行15/21，149 Node及25 Python通过，1个Python新正则漏转义失败，后6命令未执行。原失败保留；仅补1个反斜杠并双人静审，注册输入仅该源和来源记录变更，799保持。r1 draft SHA `3cb9419482aac8c597167f64b56921f566f38a5e0f8e65279e5343c880a39817`，新strict及M6.8全入口复验待执行；双平台101全量仍待，不混用为整项通过。 M02独审SHA `639f6e45aabfdea6b28bf187f65042f1b06e068599a0c59bce11161826a20578`；M6.8独审SHA `340746c5705660c68fefce864d07003baaa71db63daeb596e503918d4350ab6d`；一字符修订root独审SHA `dea4a9af5d4750f5bb5815f533b2d66212571a7f826f00b0f7ed8c221a8d48ff`。原26 Python中25过1错，Node149而非口头中间误计159，以原报告为准。

2026-10-04 v22-r1定向修订完成：新strict `20261004T123410Z-9314a28915` 18通过，M6.8 `20261004T123445Z-da2b05ff37` 完整21/21通过（149 Node、61 Python，另10语法及1生成物检查）；与该strict同五输入且均正常排空。一字符修复已真实复验，前次失败原件保留。此前同v22的M02定向684及M7领域202结果分别留档，不拼成一次全量通过。冻结source-only asset609828442，SHA `129115b39864e387a02b3158151b0fb7f82d38cdff7c3141c681a7076c75c382`（801源输入、3367654字节ZIP，GitHub官方digest相符）；原319归档、101命令及全部原节点保持。下一步新main该同候选双平台strict/full；M8.2仍唯一in_progress，后续真实技术门槛及员工试用/人工验收边界保留。 M6.8-r1独审SHA `ba75beeb22d21212cac9c93dfaa818430145820d93f0cbcdc3be4f05b01938a4`；25个M7明确run独立终审SHA `212c70590d071a20630cde61bdaca446c129240a04339f2159bc87aeab347e17`。源码包只含测试定义/执行器/来源登记与归档源码，不含凭据、数据库、日志或运行证据；下载后仍由原统一入口新建隔离环境执行。
