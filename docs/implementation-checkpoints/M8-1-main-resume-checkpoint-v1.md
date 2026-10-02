# M8.1 main 接续补测检查点 v1

2026-10-02，沿 main `6d2368e844fe20e12e43d737c706d0513bc26710` 接续业主“进一步完成之前未完成的测试，然后提交到github”。初始工作树干净，`git pull --ff-only` 确认已同步。本记录仅维护当前 M8.1 的有限复验，不重开其它里程碑、不继承旧通过数。

## 已观察问题与修复

- 原 SSE 离线命令没有关闭已打开流。Chrome原生 Page.stopLoading 产生实际 Network.loadingFailed/net::ERR_ABORTED；同页面保留Run与真实游标，离线游标不再前进，服务器独立结束，恢复后请求精确非零after_seq并补读至真实event_seq。没有伪造事件/响应、替换fetch或重发原查询。独立两次Chrome进程原登录/历史读取证明重启后恢复原Run、不重发、卡0。
- 原安全探测故意 `/api/users` 403按服务器追加真实refusal，旧后继全库比较误含该前置记录。现在严格核唯一新增refusal、原本人店/path/消息与响应id、rule/can_escalate=false、旧行及其它全表不变；后继只读流和浏览器恢复保护拒绝后完整快照，不忽略整张表。
- 新 `pending_ui.py` 接入现有followup与完整来源报表。M16使用本轮第二真实卡ID核历史关闭后的三宽主卡、抽屉Escape/遮罩返回焦点、Tab及草稿；前后原业务与当前会话相关14类助手表全部字段hash相同。M05/M06使用同轮UI建立的原采购/库位来源，不复制旧parent数据库；原CSV/全表/整数原账/期间不完整说明及明确原单守卫保留。原导航在768先点真实菜单，滚轮落点交集考虑sticky topbar；保留单次trusted wheel、实际右端、末列、整页宽及原业务不变。
- 原GitHub CI [36952582341](https://github.com/XintZhang1/HuaKangOS/actions/runs/36952582341) 在6d完整53执行49过4失败：SSE装置、HK028 CSV准备409、两个父失败后0动作后继。原server在对应HK028 INSERT时记录SQLite OperationalError code5，生产prepare遗漏鉴权前get_write_db。同文件其它写入口已有该合同。仅改 `app/vehicle_imports_api.py:prepare` 的依赖为先get_write_db再get_user；原body/schema/守卫/服务/事务回执不改，无重试、worker仍运行。原CI125条锁错误不能全部归因此单入口。

精确范围及原失败边界见 PATCH-M8-1-MAIN-RESUME-TESTS-01 与 PATCH-M8-1-VEHICLE-IMPORT-PREPARE-WRITER-01。独立只读审查与根差异审阅核对实际代码；必要AST与diff检查不等于业务通过。

## 本轮原件

所有实例通过原 `tests/browser_click/run.py` 在仓库外全新 NTFS 目录白名单镜像后才初始化/导入app。证据根 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/`。原预览/公司库、真实.env/密钥/数据未访问，合成provider阻外。

| 实例 | 真正结果 | 边界 |
| --- | --- | --- |
| main-resume23 | selected1失败，CLI1，合成4/真实0/外部0 | 旧装置仅after_seq0，游标1到6，不能证明重连 |
| main-resume24 | selected1失败，CLI1，合成4/真实0/外部0 | 真断流与after_seq1补读通过，后继错误包含前置refusal |
| main-resume25 | selected1失败，CLI1 | 测试误猜封闭管理拒绝为authority；服务器实际rule，原记录保留 |
| main-resume26 | selected1完整通过，CLI0，合成6/真实0/外部0 | 原拒绝、真断流补读及两次独立Chrome登录/历史恢复 |
| main-resume27 | selected9完整执行8过1，CLI1，合成16/真实0/外部0 | M16/恢复/前置/M05通过；M06原wheel可见中点被topbar遮挡，装置失败，不拼整体通过 |

main-resume28 是修正落点及生产依赖后的全新10项联合运行。当前源码摘要 `cf34fb8d05080dd1d3efd89a3e76d156e5045df31540024f7b318c197f8d16da`，脚本摘要 `2e5eb6e6e2b74b099dc68f8698a8b2eb66a66de77db4ea97e3cadba9e0e093e6`，镜像stable=true；正在执行时不预称完整通过。终局另追加。

### main-resume28 实际终局

原进程正常收尾，CLI0；`run-summary.json` 与 `browser-click-report.json` 均 complete=true/passed=true，selected10执行10通过、失败0，2467动作/1056点击、各场景耗时合计378.39秒、页面异常0。实际Chrome154.0.8037.93、Playwright1.56.0/Python3.11.4，原生HTTP传输。provider合成17/真实0/阻外尝试0。原来源及脚本摘要与上述冻结字节相同。

十项是followup/退出迟到响应/协议错误/security、原采购/主档/物资/系统/车辆导入和完整来源报表。M16三宽主卡、抽屉关闭返回焦点、原生Tab及草稿，M05两张/M06三张原表768单次trusted wheel和末列，SSE实际中断后的精确非零seq补读、独立Chrome关闭及重新登录读取均实际通过；HK028 prepare及同轮HK019/027/030/025/023也通过。当前41项自动业务检查不等于193业务接受，full_registered_suite_complete=false/full193_business_acceptance=false。

server.log仍有20条后台SQLite code5/517记录，原件保留；不宣称worker并发完全修复。生产依赖独立只读审阅确认FastAPI0.128.2/Starlette0.50.0先完整接收暂存multipart再解依赖，锁不覆盖客户端上传等待；仍可能等待/BUSY。正式Linux53项结果由推送后的同原CI另记，不继承Windows定向通过。

## 原未满足条件

53注册场景仍保留，脚本白名单由45增为46。定向10项不是完整53或193正式业务接受；人工阅图不是员工试用。HK099旧授权截止2026-10-02且已主动撤销，不可拿它证明到期；真正次日到期须独立active授权并跨真实日期（最早10/3），不能改钟/回填日期/恢复旧grant。原OS输入法、HTTPS、PG、Linux独立进程恢复、101/283真实模型、员工效率及生产门槛仍各自待真实条件。四生产开关默认关闭；M8.1仍唯一in_progress，M8.4 todo/CP-36 not_ready，不上线。
