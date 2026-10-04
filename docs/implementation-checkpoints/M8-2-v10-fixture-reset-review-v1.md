# M8.2 v10 真实失败与隔离夹具修复审阅

2026-10-04；M8.2 继续 in_progress。CI [37165122951](https://github.com/XintZhang1/HuaKangOS/actions/runs/37165122951) 使用 HEAD `74c3697431d9fb10a35ac431cd13c5cf438d8ef2`、v10 源码输入胶囊。Windows/Linux 均已终局且整体失败，未通过全量验收。

两平台各自本轮 strict18/22 实际通过；完整 collector3407、当前193/111来源矩阵唯一节点、A25及B首个合法图节点实际通过。随后B其余32节点均在旧恢复 conftest 的 setup `DROP TABLE business_assistant_work_items` 触发 SQLite 外键拒绝；C35和后续97命令尚未执行。这是原夹具删除当前真实循环引用图的适配缺口，不能写成32条业务断言失败。两个 full 都仅执行4/101，五输入同本轮strict参照、前后不变、无超时且自然排空，真实模型0。

官方与实际ZIP SHA：Windows `368719905c171fb1d47cdc7e45f16e492c316103728ae598e020d1d71eb9b0ad`；Linux `e0b97cf441c52f9e1110bff5a61ebea4da1106334b1c580f7416fc1eef1a297a`。原件留在 V/closeout-20261003/m82-{windows,linux}-v10-full-37165122951-*。root两份审计SHA `cdc1386825042624dca8b1403c5a8644bdde1b91b7f5a40678e7e33d27067053`、`818fec6d0300d930fb89cbc50cd2ab34c759f69ae38329971dbf1725d9d4b238`；Linux独立审计 `2019d3892c905a1181efa2d73baa37c7e1ac9d14ef2ebb739765531202891dc4`。旧失败保留。

PATCH-M8-2-CURRENT-REGRESSION-01 已事前登记，仅原外部 `tests/baseline/overlay/tests/conftest.py` 修复：确认标记路径、池中在用连接为0，再 dispose；已存在的本次合成库/WAL/SHM逐件留存于同run/fixtures的新独占目录，每个源/目标使用原路径守卫、字节SHA核对。沿原固定engine及路径新建空Base schema，原Store/User/UserStore种子、yield和全部业务断言不变。WAL设置的raw连接显式 closing。任何路径、连接、移动或哈希错误正常失败；没有强制GC、重试、删旧证据、改生产、关闭或延迟外键。留存不承诺多文件原子移动。

原 conftest SHA `522e75e1681453559e8936ac04ebf8afe3d93bf6fd0837b00f6874795eaf63b2`；新 `3ba99b841e51d45873d2b90a5938752c78fee9a3443d3a6e2ab8f94eda95d57c`；精确diff `c558a50760fd5e9f00207aafad5d4185d0056da10e0d2ef68a15e7e5191d5b44`。原四函数及seed/yield AST相同；独立静审 `cfc7a4a47df29b8f839201acf9adbb37bf56475b04d64ecb7c58e36b47cca2c3` 无确定阻断。首次作者静审误把分号两个Expr当一个索引而失败，原说明保留，修正审计未改候选字节。

v11 的801源码输入仅 conftest 与既有 restoration adaptation 来源版本改变；归档原件、74节点数组、101命令、101合成授权、10个Linux明确NA及其它milestone不变。manifest SHA仍 `a85e20a31f380ab045950e5f6dc4f4c053efff1950e901917a9e21797f895779`；restoration `c9c23b8abf028ef9df95faa03473dd2701ab040d2b4c11d394d89350c54e1def`；草稿 `fb2007879e6bb5633afdbe2bae6defefe5ef6e9b8e900c59fee5a19b49f56be3`。全部801实际文件SHA已核对。新两平台必须各自重新 strict 和101完整执行；静审和定义齐全不计 passed/done/released。main尚未上传；员工试用以外技术门槛继续完成。
