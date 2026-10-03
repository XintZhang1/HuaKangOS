# 任务：跟进与待确认卡合成收口

**任务id与负责人**：`runtime-followup-closeout`；Codex子代理，向root交接，不改共享进度或里程碑状态。

**目标与交付结果**：表9/11/12优先完成可执行独立脚本：本人撤销后迟到准备拒绝；显式Grant登出仍查询/准备和真实20tick/实际GET区分；原pending取消及原30分钟自然到期。

**架构依据与决定**：原M8.1故障步骤、14表精确边界和原plans/outbox/principal/worker、原UI确认；PATCH-M8-1-FOLLOWUP-CLOSEOUT-01。复用原helpers，仅原UI创建独立接待，不重用已消费fixture，不造业务事实或改时间。

**代码快照与影响范围**：HEAD `7a4f8722bc66029d69cdf2b35b872c85f35f0d59`，现有root/其它作者改动保留。仅新增本任务、精确补丁和 `runtime_followup_closeout.py`；root集成provider/观察器/注册/白名单及动态复验。

**已完成与当前位置**：表9本人撤销、表11退出后跟进/20个原worker tick与实际GET分开、表12原UI取消/原30min自然过期脚本已交root。每PID观察账本独立合并，只计原首卡Run所属仍运行worker的20tick。`closeout-contracts-02`实际三短场均在enable出现前点击失败；已保留失败，并用原UI新对话、真实当前goal及唯一可用enable等待修正装置，不降低业务断言。表13追加 `runtime_context_closeout.py` 两场：真实31轮跨30/24000窗口后原单UI变化核当前事实，真实61s自然核查凭据拒绝后新核查唯一卡；追加 `runtime_goal_closeout.py`，原UI修改同一Plan目标、当前旧goal在途修改Run停止、原历史保留、本人原UIresume新增新goal Grant。

**下一步**：root集成所有独立provider/观察器/场景与白名单，从新镜像动态验证；goal场要求root已登记的生产sendRuntime安全plan_id接线。继续评估表10全source-map真实hook、管理员原撤权及固定事务失败路径，逐项保留未覆盖边界。

**验证与实际阻塞**：本子代理没有启动/运行验证。原短场装置失败事实如上，业务路径尚未由此次结果验收；AST静态解析与diff whitespace检查通过。自然过期必须真实等待30分钟并最终完整入口执行；无修改业务deadline的捷径。source-map各hook及管理员撤权仍未覆盖，真正摘要/旧goal也须动态证据后才可记通过。第一文件在等待修复后冻结SHA256 `c337f2fa4572629203a612b98b7538f95242aefb9741bf6a339f88d2bd7d13fa`；摘要/TTL文件冻结 `97856f546b3a1ecec91052f2677ca169e34eb7757adc9520f4e3939507b32c25`。

**2026-10-03 core03 实际记录及本次冻结**：root 完整定向15场实际8pass/7fail、CLI1，服务已全退出且未强杀；原报告位于仓库外 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/closeout-contracts-03`，未覆盖或改写。本人撤销迟到准备和真实61秒凭据场该轮通过。logout在第二卡commit到Run终态约650ms窗口即时仅计成功Run而误判重复；实际两原Run/两原卡，故障截图约早230ms。cancel和goal是首卡Run终态前refresh导致原控件busy；摘要在31轮前读不存在case_id装置KeyError，其24000字符分支也未被旧等长资料实际覆盖。notice场首条原Grant source故障出现就过早断言Flow未注入；CAS/原回执共享场则在共享helper独立后继员工归属断言失败，由root修共享helper。这些失败不能转写通过。

独立代码已修真实卡↔Run映射/成功终态与原worker tick后refresh；logout保持严格全场仅两Grant Run/两卡；摘要每31轮实际Run/当前schema完整步骤语义、新卡/新Plan零新增及两窗口实际被排除消息边界；goal保持同Plan原请求和工具结果核查；outbox等待全部真实Flow/Run/notice故障证据并核后继Run终态，原全Runtime回滚、单source自然退避与恢复终点disarm不降标准。已完成AST静态解析及diff whitespace检查，未启动新验证，动态结果待root新镜像。

本次四文件SHA256：followup `97ac8e8066cd49722ec21dbe2952b8f75848d0b750d95ffe4a27de813c8b43bc`；context `8583dbbe3547b9e207ea39322bfda118b133d287437a4f025746d4a876fbfcbd`；goal `f97501ed363aa01c446d4823b7804661cbba907b44a0491b2e08665fd1bf0d39`；outbox `38019f06e6b8fa268021ab17ce7bc8462bfd2af6d5486b5b60981ddf635ec763`。后续source-map/admin撤权新增独立模块不修改这四个冻结文件或共享入口。
