# n46a-fix1 本轮验证证据

`summary.json` 记录范围、命令和边界。四组 `.txt` 与 JUnit `.xml` 是本轮最终通过的运行结果；测试模块互不重复。开发期间逐项修正后按影响域复跑，不是历史全套用例的一次冻结整轮运行。

测试使用 `tests/conftest.py` 建立的独立合成 SQLite 数据库。真实 PostgreSQL 没有运行。浏览器尝试在页面打开前被受管 Chromium 策略阻止，不能计为通过；未修改或绕过策略。

旧文档里的 Windows Chrome、PostgreSQL 和 1024 项整轮记录仅作为原项目历史保留。公司真实岗位、真实附件、正式月结周期和部署均未验收。
