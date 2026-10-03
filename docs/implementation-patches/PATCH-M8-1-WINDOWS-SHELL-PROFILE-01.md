# PATCH-M8-1-WINDOWS-SHELL-PROFILE-01

2026-10-03；M8.1 正式外部入口的真实启动失败修复。

正式 run `20261003T063440Z-a81cad3a6a` 两个后端合同11/19节点实际通过，完整浏览器入口在Chrome启动前失败，80场执行0。Chrome明确拒绝DevTools目录，宿主CLI1、原服务0且未强杀；原日志、报告和指纹保留，不把注册81报告节点当作已执行80场。

全新子进程配对探针 `V/closeout-20261003/windows-profile-probe-20261003T064214Z-70f26e9a/probe-results.json` 证明：独占fake USERPROFILE顶层存在仍使SHGetFolderPathW的Local/Roaming查询返回80070003；只补该profile下AppData/Local和AppData/Roaming后两者成功。未修改原用户目录、OS、失败run或启动浏览器。该证据只定位执行器原因，不计业务验收。

精确范围：只修改V的 `tests/baseline/overlay/tests/m81_browser_entry.py`，在当前正式run/命令/结果目录验证后，Windows分支确认四个原profile环境变量仍严格指向该run/profile，用原inside/clean_path拒绝链接和越界，创建上述两个目录。只更新 `archive/baseline-restoration.json` 中该唯一adapter的指纹及修复追溯；修改前在V独占history保存原字节及SHA。不改环境变量、Chrome版本/参数/安全策略、manifest、isolation、被测app或60脚本，不降级浏览器。

独立26故障复跑使用当前app/60脚本，不依赖这个正式adapter或归档登记，其生产/脚本继续冻结。失败正式进程已退出，修复后重新冻结全部正式输入并执行完整M8.1，不继承失败run的部分成绩。
