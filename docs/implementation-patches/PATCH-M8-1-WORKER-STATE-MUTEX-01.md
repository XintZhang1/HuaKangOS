# PATCH-M8-1-WORKER-STATE-MUTEX-01

2026-10-03，M8.1 验证器窄修。正式 `20261003T091007Z-d9d0e4c819` 关闭日志证实 `runtime_faults._atomic_json` 替换 worker-state.json 时 WinError 5；命令监督任务退出，restart ACK 和后续 queue arm 未完成。原 80 场 75 通过 / 5 失败，服务关闭失败，整体不得通过。

允许范围仅 `tests/browser_click/runtime_faults.py` 与 `runtime_followup_closeout.py`。将已验证的观察文件 Windows 同路径本地命名 mutex 复用到 worker-state.json 的完整读写；followup 原严格 PID 文件名 wrapper 共用同一 helper。非 Windows 在 ctypes 导入前原样无操作，其他文件原路径不锁。10 秒超时、abandoned、未知/失败 wait 均严格报错，无循环重试、ACK 默认成功或协议降级。

外部纯文件协议 9/9、实际 CLI 0，含多进程完整读写与逐次 ACK、持锁、真实超时和 abandoned。组合取消候选的五场原生复验 5/5，服务自然退出 0；仅证明所选场景，不替代完整 suite。最终整套需原正式合同及独立故障重复。

指纹更正保留原件：旧候选记录 72a9da99 是默认 JSON 空格序列化所得，登记入口 `run.py` 使用紧凑 `separators=(',', ':')`，相同 60 文件映射的实际规范指纹为 `6a3815995f666f0a03441778c8cbfb7c794f5f0128c9cc5af956018546cf0d13`。没有源字节差异，不覆盖旧记录；后续按入口规范计算。
