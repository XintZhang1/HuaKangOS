# PATCH-M8-2-MODEL-CANCEL-USAGE-01

2026-10-04，v19 CI37181959680双平台自然failure，已执行的E全部7项通过，包括Windows原严格PID及24轮读取恢复。F各10通过/1失败；实际等待600秒及time_budget终止通过，唯一失败位于第二模型round的已知HTTP计数丢失，`usage=None` 被原135行断言索引。首轮强杀未知与第二轮自然取消必须分别保留，不能改测试把两轮都归为未观察。

原provider `call_model` 已在子调用异常上附加有限 `runtime_usage`；`_RunHeartbeat.wait` 等待独立子任务，外层总预算取消的是等待父任务，其finally取消并排空子任务。`run_once` 取得父任务的取消异常，没有子调用的计数，因此在第二轮错误保存None。原600秒停止、心跳、排空和未知token保护有效，丢失的是子任务已观察的安全计数。

允许仅在 `app/assistant_runtime_runner.py::run_once` 的当轮模型调用局部保留子调用安全usage：局部包装协程在异常退出前记录provider已附加的 `runtime_usage`，仍原样抛出异常；原heartbeat.wait排空之后，原异常处理经即时权限/fence重验及queue严格usage校验保存该本轮计数。没有报告时仍为None。局部状态每轮重置，不包含响应、消息、凭据、推理或异常文本，不扩展异常链解析。

不改变通用heartbeat、取消/总预算、模型请求/重试、默认24轮/600秒、原权限与事务、provider/queue结构或模型usage含义。不把未知token记零，不将已强杀的上一轮补造为已知，不执行迟到回答或业务写入。原F及全部输入/断言保持，未执行的后续93命令仍留待新同候选完整回归。

原生产文件SHA `396eb22eaa4a4778ff8e04692374658b1313529a7798021cd2cff6bd16ec381d`。day只在外部独立候选实施，root合并前审阅，mobile独立复核；静态审阅不代替原真实600秒故障路径。M8.2保持唯一in_progress，修复后同一v19输入胶囊、当前新HEAD完整执行两平台strict/full，不继承旧片段为全量通过。

实现与静审完成：单文件候选位于 `V/closeout-20261003/m82-model-cancel-usage-candidate-20261004T064144Z-c78e0c8be1`，生产SHA `e106fdea33461e963a8f327028eeaf895f6a8fe21aa8a760c2068a91f1963d30`；作者静审 `da6e3630f574f0aa86bc7aa61fa4fea7f4a0ed7a0bfa43cd8cad0585d32aa098`，独审 `42122fedf33bfc46a165e5c56a282da0723a0716c6c1f2005297057bc666fcc4`，root合并核对 `0daf9ba280610f0d133e8656a2975f0aeb04435f05bad2a276625d47d6d52f8d`。逆向原文件字节/整AST及原调用参数均核同；只有当轮局部wrapper与异常usage选择变化。完整801登记输入保持原v19 SHA，使用同asset609251384，不改F或任何断言。静审无app导入/测试/模型；新源码实际双平台复验待执行。
