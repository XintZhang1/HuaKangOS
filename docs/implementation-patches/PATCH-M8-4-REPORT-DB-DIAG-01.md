# PATCH-M8-4-REPORT-DB-DIAG-01：隔离导出数据库错误的最小诊断

日期：2026-10-01。IAB独立合成report-diagnostic01实际一次导出后显示原503数据库忙提示、export审计零新增；第二次明确点击也未成功，已正常退出并收尾服务。原报告04去掉装置多余response.body后每CSV精确一条原审计通过，不能把IAB真实503归为同一装置问题。

精确测试范围仅`tests/browser_click/fixture_server.py`：隔离serve实例SQLAlchemy handle_error观察器只输出SQLite错误类型与整数sqlite_errorcode，不输出原SQL、参数、异常message、Cookie、密码、推理或客户数据，不处理/重试/吞异常。原服务、数据库、网络阻断和记录规则不变，生产代码无此日志。根正常收尾后写入并镜像至全新外部实例，IAB再次原点击核对根因；诊断不是正式业务验收。
