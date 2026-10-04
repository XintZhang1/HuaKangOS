# M8.2 v20 核心恢复通过与合成验证夹具修订

2026-10-04，main `78356b0f6ad28fb565f9f0104120a4c18605760d`，CI [37183964600](https://github.com/XintZhang1/HuaKangOS/actions/runs/37183964600) 两平台自然failure：Linux07:22:31 UTC、Windows07:39:58 UTC。沿用v19源输入asset609251384，胶囊SHA `1e39b364be36face7ebd3b0af3ca5a8995736ebd4361ae2d782d71d519e3f33a`；本轮生产runner SHA `e106fdea33461e963a8f327028eeaf895f6a8fe21aa8a760c2068a91f1963d30`。

两平台各自strict通过（Windows18/Linux22），3407唯一pytest节点/245文件完整有序收集。matrix1/A25/B33/C35/D14/E7/F11全部通过；真实600秒预算节点的后续usage、summary和业务快照断言本轮均已执行通过，原强杀轮次的未知计数仍保持未知。此次结果覆盖上轮模型取消计数修复，不继承上轮未执行断言。

两平台随后18个原unittest collector实际收集203有序节点，均为collect-only、测试执行0。第27/101命令b01验证合同组为624通过/33调用失败；全轮pytest共750通过、33失败、2624未执行。后续74命令和原203项执行尚未发生，phase/milestone均false。

33项失败根因一致：32项绑定合同的合成validation目录缺少当前已绑定的 `harness/runtime-platform.json`；诊断接线测试的full参数缺少 `baseline_inventory`，原完整清单守卫抛 `full_inventory_files_missing`。这是旧夹具未补齐当前输入合同；按PATCH-M8-2-SYNTHETIC-VALIDATION-FIXTURES-01，仅补合成文件、清单和来源记录。原runner/业务、全部断言和节点不变。

原件：

- Linux：`V/closeout-20261003/m82-v20-linux-unique`，strict `20261004T065049Z-d66bb4c4df`、full `20261004T065058Z-e8864cb8fd`；artifact11297067000，ZIP SHA `4de6ac67c9d17f139adcca2c1293c188449c36431a1233d35733cfcc7aca5dfe`，2679126字节/1656成员。独审SHA `8637cc838acda5e76395d8356983befe461c3993cdfdc84662b80aa753ce0e3a`。
- Windows：`V/closeout-20261003/m82-v20-windows-20261004T074212Z-a142beb78d`；artifact11297133264，ZIP SHA `f3e9b3ad3d97f808d50d5d095c3ce700938ebf69ab40a4ae987546f55f1b67af`，2679962字节/1652成员；独审SHA `af97145842ba4e75c180fbd1b1f3a7889bb506e4b3e4957fd0d799088702c45f`。

两平台各自五输入、1306源码/33harness/768外部文件映射和依赖前后不变，28实际命令报告均为自然排空、无超时或清理终止。Linux严格前置含4项真实POSIX进程组验证；Windows1306源码SHA另逐项与Git78356b0 blobs匹配，600秒节点实际610.02955秒，原件无独立远端全进程树普查，不补造该证明。Windows审计首次误用旧1304硬计数而失败的过程亦保留，不影响原CI结果。真实模型生成0。修订后先原M0.2.B诊断，再新同输入双平台完整复验；M8.2继续唯一in_progress。

夹具修订的本地定向复验已实际通过：strict `20261004T075929Z-4944389608` 18/18；随后同指纹M0.2.B diagnostic `20261004T080035Z-2fb45474b0`，原collector收集2781节点，b01完整657/657通过，CLI均0、输入稳定、命令自然排空。source指纹 `ee358fa841af756d9c2ea2cd9566ddaa7b03f399008747a252e1446042594ecb`，诊断phase/milestone均false，仅证明本组修订，不替代新main双平台3407节点及原203执行。后续文档更新后的CI将重新执行自己的strict/full。

v21源胶囊已上传同draft release：asset609410676，SHA `54fe594476256e59abe59f4864f8402b73283f01b9e5b6a86fcbd40eb558acd1`，3337419字节/801源输入，GitHub官方digest核同；仅3个输入变化，其余798保持。全量复验尚未取得结果。
