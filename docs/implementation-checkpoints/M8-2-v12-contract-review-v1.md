# M8.2 v12 终局与两处测试适配审阅

新 v14 输入已上传原未发布 draft release，asset `608994736`；官方 digest 与本地 ZIP `240cc7913a4d1b90a2d10dec08eb6376891b06dd9fd293f51a73f0568ed36a2f` 一致。独立审阅已完成，新双平台执行结果另登记。

2026-10-04，main `ef4f62dc8363ec3e377e3261fd33aaaa6b2b00c0` 的 CI `37170796831` 两平台自然终局 failure，未取消。两平台均只执行原 101 命令中的 4 条；后 97 条及原 203 个独立 unittest 均未执行，M8.2 保持 in_progress。

| 实际证据 | Linux | Windows |
|---|---|---|
| strict | 22/22 | 18/18 |
| 原有序收集 | 3407 pytest / 245 文件 | 3407 pytest / 245 文件 |
| 矩阵 / A | 1 / 25 通过 | 1 / 25 通过 |
| B 的 33 节点 | 32 call 通过，1 call 失败 | 13 call 通过，19 setup 错误，1 call 失败 |
| artifact | 11291317614 | 11291313035 |
| 官方与实际 ZIP SHA256 | `55ef9d6d8f5881aa4e443aa474c6630bd56c4b152818487f917d83cf6f578c54` | `81aab93cdc7316bcf663d5aa2a788d1fa41c07d7ebc767131ce008e67494a730` |

原件位于 V/closeout-20261003 的 `m82-v12-linux-20261004T023311Z-3177c51e0f` 和 `m82-v12-windows-20261004T023749Z-5f9aae398e`；V 是已授权的仓库外验证根。各自 strict/full 同五输入匹配、前后无输入变化、没有命令超时，真实模型调用为 0。Linux 独立审阅 SHA `84041f1459deef43fd081cc5d34aed0750cf1bd5d0791852f52106c9b454a46f`；Windows 独立审阅另追加。

两个平台最后节点都在真实员工确认成功、原卡 succeeded、从回执取 case ID 后，读取原 GET 的错误字段 `values`；当前原接口返回 `data`。按 PATCH-M8-2-CASE-DETAIL-CONTRACT-01 仅修正该字段，后续原目标版本和授权全字段保持断言不变。v13 原件及独立静审保留，但本地包未运行或上传。

Windows 的 19 个 setup 错误是在保留旧合成库时遇到 WinError 32。共享只读快照采用 sqlite3 的事务上下文，未负责关闭其连接；按 PATCH-M8-2-SNAPSHOT-CONNECTION-01 仅加 contextlib.closing。保持 conftest 的闲置连接断言、原库字节留存、路径标记及真实 FK 守卫，不加 GC、重试或吞错。

v14 静态候选：801 输入相对 v12 仅两测试源及 manifest/restoration 的对应 SHA 四处改变，其余 797 相同；74 个有序数组、101 命令、101 合成配置授权及 10 个 Linux 平台不适用登记保持。B 文件新 SHA `f2276375d15f052618b6b6d2949927fd011a5ba1ccf2d45461a54ad0c0155719`，共享 helper 新 SHA `6a992c9d77bd1ca49b82083c85f7aac9fe2446065b9cf61ac1c8302ec20f05cb`；主 manifest `91972e9e5b42187539d3ef91485440610e3eb524eaadf72796cb66b2bf362266`，restoration `e0d38b6c301a778efafab6d0b37b466ef03b27614d6b7d1317054ec9c503abf4`。

完整 draft SHA `a59976c843a329a87a4c3b9f8e1e315b12240bb93bd166d1105f136f1399c735`，source-only ZIP SHA `240cc7913a4d1b90a2d10dec08eb6376891b06dd9fd293f51a73f0568ed36a2f`。关联进程终局后才修改，旧输入与差异外置保留。下一行动为独立静审后同候选双平台 strict/full，不能将局部通过或静态修复记为全项完成。

v14 独立静态审阅完成，无阻断，报告 SHA `067b0859507081c84773297a348d19e4492950945e1ec8fff8711ca8ab78c30e`。801 实际文件逐 SHA 一致；两测试源分别反向恢复等原字节，helper 的其它 AST/SQL/返回内容保持，登记差异仅对应 SHA 叶值。连接关闭覆盖返回和异常路径；尚未执行新完整回归。

Windows 独立终局报告已追加，SHA `b0fac7f1bcd2a904c897c68c9a46d2a9b6415a48a3cdeb1c80abbe7ccea1b819`。ZIP 与解包字节一致、5 主进程原生命周期记录均 drained；五输入严格匹配及终局未变。与 Linux 的完整 3407 节点收集顺序一致，平台 harness/依赖安装指纹分别保留。文件占用错误只证明句柄未释放，未声称已定位持有者 PID；helper 的显式关闭修复仍待同入口实跑验证。
