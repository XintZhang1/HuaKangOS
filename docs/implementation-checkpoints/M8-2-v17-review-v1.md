# M8.2 v17 实际结果与读取观察修正

2026-10-04，main `bcff75be94685cbdd47376239f51b6f04a3cdf9c`，CI [37178121548](https://github.com/XintZhang1/HuaKangOS/actions/runs/37178121548) 两平台自然终局 failure，未取消。Linux 05:03:45 UTC、Windows 05:10:38 UTC 完成。仍使用原v16的801输入和capsule asset609102816 / `519e60ee37dfa5df99063db69a43605cd2b0fe9383c56a99b6208f97ededbe79`，生产变化仅为前轮登记的新读取WorkItem先flush。

| 平台 | 官方及下载 ZIP SHA | 外部原件目录 |
|---|---|---|
| Linux | `9662133ec1a52c59a0a3aedfae2a3e61a5446d992746f4addfd1f0c85ad7523e` | V/closeout-20261003/m82-v17-linux-20261004T050709Z-b966c83b77 |
| Windows | `3f7758b769a96bce0cbd1dd56b686af8f60d3ec3a1c88f0a72cc573fd7f7ad5e` | V/closeout-20261003/m82-v17-windows-20261004T051249Z-28cacc7eb0 |

Linux 独立审阅 `ee479a1408950c4ce0b6e2a9686783251432cdc1aa72e2ef6f5062a85671dab5`：strict22/22；full7/101，collector3407唯一节点/245文件，各已执行有序数组精确等于登记，聚合无缺失/多余/重复。matrix1/A25/B33/C35/D14通过，E6通过/1 call失败；114 passed /1 failed /3292 not_run。后94命令、F和原203独立节点未执行。strict/full五指纹和三个来源映射相等，全部输入/依赖前后不变；实际8命令自然排空、无超时或强制清理，无setup/teardown错误或skip，真实模型0。

唯一失败仍在原读取恢复节点，但已越过前轮的写入次序错误：真实原GET checkpoint、原24/600配置、第一张待确认卡、原manifest、自然租约回收与新fence均执行到达；23次后续provider请求及 `model_round_budget` 断言通过。本次在原238行发现spy读数25而总数断言24。239行之后的持久预算、同WorkItem两attempt、首卡逐列不变、两卡、完整manifest及业务全图断言仍未执行，不能记整体恢复通过。

按 PATCH-M8-2-READ-OBSERVATION-01，仅精确修正该测试函数的观察合同。源码固定路径还包含恢复第二张crm:customers卡所需的一次目录GET；原spy无条件记录了所有读取。完整25条参数没有在原失败报告展开，组成是源码支持的判断；新断言将严格核对有序完整参数，任何额外/错序/错对象均失败。生产、provider、helper和所有后置业务断言保持，新完整实跑待执行，M8.2仍唯一in_progress。

Windows独立审阅 `01d6e8d6443c3a860a4b67acc8151e41023a24808c0b71daa64d6c694a96c8ca`：strict18/18，full7/101、114 passed /1 failed /3292 not_run，全部已执行节点/有序清单、五指纹和三个来源映射精确一致，输入依赖不变、自然排空、无超时或setup/teardown错误、模型0。该平台的唯一失败更早：原support268的PID/Run组合身份校验，尚未进入Linux后续读取计数阶段。原件没有marker、proof PID、Popen子PID或proof RunID，外层命令leader PID不能替代子进程；不能确定失败operand，也不直接归因Windows redirector。

按PATCH-M8-2-WINDOWS-CHECKPOINT-IDENTITY-01增加有限进程身份诊断并保留全部严格校验，先通过Windows原strict/full入口取证。默认双平台仍保留，平台选择互斥，未恢复浏览器job。该轮定向执行不等于双平台验收；最终完整候选仍需两平台同指纹通过。

下一v18候选：E单函数源 `81fabcec0af29ef5e4b06ca7328888362580ea35ffe66a79704c2fbd7c26eda3`，作者静审 `a912efc01fe72c8894f65b98262c4dd667a68dc76ac233f1a37fee9be6e505a5`、独立静审 `e0e71fc544bc7ab7df4c0713a6f5821212de25c81b37f3ed0eb96a973aef9984`。两helper源为worker `031a612a65537ad659604e2c7095f2904b19dbfdc8afb1538def2a9e7a92411c`、support `a186e6991286d68e572b544b19f223faab8989fee73f4d3a11aa44fcf6a39aea`，作者静审 `8fc9b1227f3f995e9478f9e5fc7a6fd003d29736a060df138570533d0ab589b0`、独立静审 `03013860259e429b205bac16e774a6e491d5c500dcaa689ca36ce6361b59a78c`。三者逆向字节/全模块AST审阅确认原无关代码、全部后置断言和原PID守卫保持；尚未执行新测试。

统一登记在 `V/closeout-20261003/m82-v18-merged-20261004T052709Z-0deed4ead9` 保存前后源及清单；manifest `75afb05b63af51c19c34446261d1c5ff1a263652dfd2c75bce22d25822f25c7b`、restoration `7090ad551d403fe6f8724964f4349bd19940ae1bd1ee8a922cda5de536075ef0` 仅更新对应三SHA。v18 draft `dc44d32dd010e9e7f0cf8d30d7939381075de5894f7a1449a31b5a3fdc15611f`，801输入仅五项变化，其余796实际SHA保持。source-only包 `2837369d3f2d7d57dfac59c10b4eb8dff1fde9084fd9f28bf3b3c089551ed0ec`；不含运行库、凭据或日志，真实模型0。

最终登记独审 `02699d4935e3b75ca52803d65608cb8957bd9283ea41f7cb2f230a0104bb9502` 核实801实际SHA、恰五变更、两metadata各仅25/26/27三SHA叶子变化；74有序数组、101命令/授权、10 Linux适用项与原runner均保持。两workflow静审 `bb68a2adabe3821a0180ba81fac6d2adb3d84a5f90097200662ecaef4e5b3012` 确认默认双平台、单平台互斥及原strict/full调用不变，未运行Actions；未引入浏览器任务。source-only包已追加至原draft release402597955的asset609203214（3,335,882字节），官方digest与本地2837369d完整SHA一致，旧包未覆盖。下一步Windows定向完整入口取证。
