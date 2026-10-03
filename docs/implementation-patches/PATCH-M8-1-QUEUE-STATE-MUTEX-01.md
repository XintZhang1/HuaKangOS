# PATCH-M8-1-QUEUE-STATE-MUTEX-01

2026-10-03，M8.1 验证器窄修。正式 `20261003T113528Z-3fd7aeef2f` 关闭日志确证 `runtime_faults._atomic_json` 替换 queue-closeout-state.json 时 WinError 5；监督协程退出，真实 compete 命令未获 ACK。原11/11、19/19后端合同通过，80场停止时15执行、14通过、1失败，完整80未完成；服务自然退出3。根核对原场景进程树后停止该树，CLI1，保留原报告。独立26重复中断收尾（4通过、22失败、只5/9终止），Linux CI37120178085取消；均不继承为通过。

允许修改仅 `tests/browser_click/runtime_faults.py`：已有同路径 Windows mutex 精确增加 queue-closeout-state.json，覆盖其完整读取和原子写入。worker-state、严格PID报告、其他JSON、非Windows路径和10秒失败关闭合同不变。无重试、默认ACK或业务代码修改。

新外部候选纯文件原九项协议9/9、CLI0，22.047秒；含真实多进程完整读写、逐generation ACK、持锁、超时和abandoned。WAIT_FAILED/未知状态仅静态审阅。候选SHA `8648f4567bb7c1d7e2b324c5a1def2c336cf2f258d3c15c0e5314ca5c0d27d99`，规范60脚本指纹 `b1ef43a5aacd516f568601ac17037349707e0a7e86373bfae647e1f6025df382`；生产635指纹仍bbe95959。纯文件结果不替代正式80、独立26及Linux完整复验。
