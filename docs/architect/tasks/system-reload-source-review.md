# 系统同页面重载源码复审

2026-10-01，只读独立源码审阅。范围为已事前登记的 [PATCH-M8-4-SYSTEM-RELOAD-REQUEST-01](../../implementation-patches/PATCH-M8-4-SYSTEM-RELOAD-REQUEST-01.md)；本审未执行应用、浏览器、测试或 SQL，未读取密码、数据库或环境配置。静态结论不能写成业务通过。

## 精确差异

- 原件：外部 `launches/system-reload-before-20261001.py`，SHA256 `7a0425a770c8db492f7489a0190364deac062626be3d4af29be56a3a8ed3bdce`。
- 当前 `tests/browser_click/system_management_business.py`，SHA256 `ea41ce1c11915f31cd039405736566005d13bd56cd052560975fcb9c870837a0`。
- 两份均可由标准库 AST 解析。唯一变更为 `open_page`（当前第 200–214 行）；移除该函数后整文件原字节完全相等，其他顶层 AST 完全相等。

同 route 分支先等待原 `#main h1` 与传入标题相等，再保存原业务全行快照。在 `expect_request` 的 GET／精确路径谓词已安装时调用原 `reload(wait_until="domcontentloaded")`；从 `pending.value` 取得 Request，随后 `await request.response()`，并要求响应非空且 HTTP 200，再读取该响应 JSON。结束仍检查原标题和原 `business_unchanged`。该顺序把 body 读取绑定至捕获的请求，并把登录后原页面标题就绪作为重载前条件。

原非同 route 的 `nav`、业务提交、Cookie／CSRF、门店／员工身份、审计、全行保护均未改；没有重试、固定等待、额外 HTTP、降级请求或异常忽略。响应缺失、非 200、JSON 读取失败、标题不符或业务变化继续失败。

## 结论与边界

静态审通过，差异符合补丁的单函数范围与原断言保留要求。此前 CDP `No resource with given identifier` 与跨页面旧响应有关属于执行诊断，源码审不能证明全部浏览器时序已消除。父任务随后报告独立 fresh 核心单场 CLI 0；本审未亲自执行，实际运行结论以其原新轮证据为准。

第 12 轮是失败中断的诊断轮，其视觉记录保持 partial、accepted=false，不能继承为第 13 轮或完整 53／193 成绩。后续图像审阅必须重新引用第 13 轮自身完成的 parent、PNG、检查点与指纹。
