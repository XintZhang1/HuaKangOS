# 业务截图等待与原页面对应诊断

2026-10-02，manual_review_draft 只读审阅。未执行 app/browser/SQL、草案或测试；没有修改生产、tests、runner、catalog 或自动原件。实际使用 view_image 查看第13轮两个问题原PNG；第13轮已失败，仅为诊断，不登记 display 或业务 accepted。

## 实际原图

- HK073：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/automatic-business13/evidence/materials-hk069-045-054-083-070-072-073-051-061/404-hk-073-business.png`，SHA256 `d6627ae141bf6c958b4750983cd8177c213520a927eae72c240a345c44647208`。1440×1000，主区域只有“正在读取…”及“文件已留档”toast，没有盘点详情或结果。此图不能证明盘点显示通过。原check仍有正/负/零三个原单的业务事实，图与事实分别审阅。
- HK077：`C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/automatic-business13/evidence/insurance-renewal-hk013-014-077-113-114-115-116/317-hk-077-business.png`，SHA256 `328659f269658ae43978de43f7a94f6acd2afeec2f38d5a52f1f43cfd9681cbc`。1440×1865，页面标题“续保跟进”，客户服务结案、来源及跟进记录可见，没有保险资金摘要。不能按HK077文件标签推断保险收款页面已显示。

## 原因与最小方案

第13轮 `scripts/scenarios.py:333–338` 的 Evidence.snapshot 直接截取 full_page 和 body 文本，没有等待真实业务渲染。`web/app.js:229` 在 render 入口把 `#main` 设为直接子 `.loading`；各原页面异步返回且 renderId 仍为当前时才提交html。失败也会移除 loading 并展示直接子 `.errorpage`，所以只等 loading=0 不足以排除页面失败。

建议只给业务 passed 方法显式启用 `snapshot(label, *, business_ready=False)`：启用时按原DOM等待 `#main > .loading` 数量0、`#main h1` 可见、`#main > .errorpage` 数量0，随后保持原截屏和正文采集。使用 Playwright 状态断言，不加 sleep、写请求、重试或请求桥。不要把助手故意忙态、错误、换店或登录隔离截图自动等成完成态。AST遍历13脚本实际找到32个 passed 方法；注册场景可复用方法，不能把40场景误写成40独立方法。显式调用参数比按场景全局flag稳定，调用语义可逐项复核。

此等待只确认已渲染，不确认正确业务对象。HK077在原续保care close之后直接 start HK077/passed，即使等完仍是care页。应先复用原 `read_as(e, context, credentials, fixture, "finance", second)` 读取第二个同轮保险原单，沿原登录/同源Cookie/当前门店、GET200、真实原ID/CAS和pagehead编号，核已完成状态与当前真实 summary；无新资金提交。来源不足、页面不同或跨需求同页截图仍需单项判定，不能靠标签或任意h1接受。

## Root最终候选独立复核

备份 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/launches/business-render-and-appointment-before-20261002/tests/browser_click/` 与登记 edit JSON 的33项before实SHA全部一致。当前32个passed方法逐个精确去掉新增 `, business_ready=True` 后，其原方法文本与备份完全相等；没有改动作、断言、通过条件或错误恢复。当前 Evidence.snapshot 精确去掉新增keyword/default及三条条件等待后，文件与备份逐字节相等。默认False，助手原调用未变。33文件AST全部可解析，未导入或执行。

保险最终 `tests/browser_click/insurance_business.py` SHA256 `ab2ec461c72cf57a17dcd65e1f02418d49f547f0ddf80308e434dc3d4cef5293`。在原HK077末块新增原finance本人读取second、finance id/role及state=completed/summary==new_complete.summary，保存原actor/store/path/case/version/summary。原read_as核GET200/id/current数据库version/pagehead原number，login_as核本人identity和当前店。原直接支付及其source_guard、直付不产生店内现金等资金断言保留。

该读取包含原退出和登录，所以新增读取前后摘要仅允许audit_logs变化，再逐行核全部旧audit不变、唯一新增同finance的login审计（entity_type=users、entity_id=actor_id=finance.id、store_id=0）；记录login_audit_id。Database.business_snapshot本来包含audit_logs，排除的是login_sessions/login_attempts等原声明范围，不能直接称全库零写。`app/main.py` 原logout只撤销登录会话，无logout审计；原login追加登录审计。此精确允许域没有放宽任意审计或业务写。

repair_business文件另有root已登记预约时段适配；此处仅核其passed方法参数增量，预约实现由root/独立负责者审阅。其他snapshot修改范围没有扩展。静态复核允许候选进入真实验证，不表示新PNG已正确或全53通过。

Root已启动并冻结第14轮，scripts总SHA `36396c4743d430dec8f0f76d2ea94db62760e9e8a627a0eb23a90def90368ecd`。只使用14新原件继续视觉审，不继承13失败图或评分。所有未实际观察项及人工accepted继续pending/false。
