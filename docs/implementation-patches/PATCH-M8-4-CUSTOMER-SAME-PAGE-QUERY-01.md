# PATCH-M8-4-CUSTOMER-SAME-PAGE-QUERY-01

2026-10-01，M8.1。精确修改 tests/browser_click/customer_followon_business.py 的 query_and_open；所有关联验证已收尾。保留 business-customer-followon-20261001-03 原失败。

客服登录已通过原 GET /api/customer-service/cases 展示 customer-service 列表；再次点击同 hash 原导航不触发 hashchange，脚本等待另一 GET 超时。当前 hash 已为该列表时核对真实标题与筛选表单后直接提交原查询；其他 hash 仍按原导航及严格 GET 等待。保持当前用户、门店、完整查询参数、唯一非空原行七列、原详情和全库只读不变校验，不增加请求重试、fetch 或 Cookie 桥接。全新隔离实例复验七项。
