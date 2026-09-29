# PATCH-M8-1-SALES-BROWSER-01：销售原生页面闭环

2026-09-29。仅改测试：`tests/assistant_offline/browser_server.py`、`tests/assistant_offline/tests/test_browser_ui.py`、`tests/assistant_offline/browser_harness.py`。不改生产 UI、CSP、Cookie、确认协议或工作流。

测试通过原接口建立真实合成 v4 订单，独立主管批准，配车并生成、上传合同签回；助手保存两步计划。浏览器实际点击开启跟进、通知及每张确认卡；第一步确认前没有生效签回，收款/检查/出库仍由原接口记录，交车签回上传不等于交车；第二步人工确认后才能满足交付事实和完成计划。未发草稿必须保留，只发生一次跟进授权和两次业务确认。

上游模型响应完全合成；测试模型仅引用请求中明确给出的合成订单及其唯一签回。业务 API/数据库/worker/页面不替换。native 模式不替换 fetch/SSE/Cookie，fixture 模式必须单列，不能当原生验收。完整回归通过才登记结果。

若浏览器原生导航受环境策略拒绝，fixture 清理浏览器和 HTTP 资源后保留原失败，不自动降级。
