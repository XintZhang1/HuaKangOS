# PATCH-M6-8-RECEIPT-CARD-WIRING-01

2026-10-02，业主虚拟数据优化后交付授权，仍只 M8.1 在办。batch-unknown35 原生通过后，按原 M6.7 第5步复核员工未知结果核对路径，发现 assistantworkspace.js 已有 receiptButtonHTML/checkReceipt/onClick 及原 execution-result GET，但实际卡模板没有调用输出，员工无法点原核对入口。不以已有函数或旧替身通过声称实际可用。

初始精确生产范围仅 web/businessassistant.js 的 businessAssistantProposal：原 executing/uncertain 卡的 links 区复用现有 AssistantWorkspace.receiptButtonHTML，传当前真实 session.id 和原 proposal.id；模块或ID缺失沿原 helper 不输出。原 pending 不显示核对按钮，原确认栏/链接/卡状态保持。原 workspace controller 的必要守卫补齐见末段追加范围，五种固定文案和 GET API 不修改。按钮只读，不切换 request_id、不调用模型、不自动恢复/修改卡、不重发业务，不拼回执自由文本URL。生产四开关默认值不变，原已存记录仍按原权限读取。

精确测试范围仅 tests/browser_click/runtime_batch.py 的 unknown B 显示阶段：增加原按钮点击与实际 GET 响应 Cookie/当前店、status=unsupported、reason_code=receipt_family_not_registered 验证；核前后全部原卡/WorkItem/确认快照和原业务全行摘要保持、仍只有A/B两次confirm、C未提交，并核原固定提示及结果不明标签。按钮自身带data-proposal，卡选取收窄为原 .ba-proposal，不能让重复匹配掩盖页面事实。只给B此次真实核对观测记unsupported，不声称Flow reliable receipt恢复/not_found/mismatch通过。

修改前 virtual-critical36 宿主直接CLI0、关联Python与监听均0；34/35/36原件保留。静态/独立审阅后新全新镜像核unknown原路径，再同最终指纹重复关键故障及完整57 CI；旧通过不继承当前新增接线。M8.1原其他合成可测故障与正式环境门槛仍待测，不标done/released。

独立接线审查发现原 checkReceipt 的 requestGuard 仅核员工/门店及 workspace owner；同店切换新对话/历史会话不会重置该owner，旧核对 GET 迟到仍能在新对话toast。精确必要生产范围追加 web/assistantworkspace.js 的 checkReceipt 及 receipt 点击分支：捕当前businessAssistantState对象、generation及原session.id，成功/失败返回、缓存和toast之前均核仍原会话；不扩展其他requestGuard、不改变原读取/五文案/错误/确认接口。对应原生验证在同unknown B首次核对后增加一次有界原浏览器GET派发暂停：只暂停并随后continue原请求，不fetch/fulfill或改headers/body/响应；员工原UI切新对话后放行，由原服务器实际响应，核旧会话提示不出现、原冻结/业务不变，最后历史重读原组。该固定边界不是模拟原服务器内容或业务回执。

2026-10-02 观察器修复追加：virtual-critical40/41 报告中的业务断言通过，但两份 scenarios.log 均有 Playwright 1.56 Response.finished() 遗留 target-close task 的 Target closed 异常；独立原件审计因此 passes=false，不能记日志无异常。已定位 runtime_batch.py 的迟到 GET 等待：SDK 在响应完成后未收尾竞争的关闭任务，后续 context.close 触发未取回异常。精确修改仅该处，沿 scenarios.py 已有做法以实际原响应 json/body 完整读取等待完成，保留原 GET、drained、全部断言和原始日志。禁止修改安装的 SDK、忽略异常或过滤日志。生产指纹不变；新脚本指纹下新镜像复核原核对/迟到响应，再完成同候选关键故障与完整 CI。修改前关联验证 Python/监听均已结束；40/41 原件和 independent-critical-audit-v1.json 保留。
