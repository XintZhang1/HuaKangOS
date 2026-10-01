# PATCH-M8-4-INTERSTORE-UPLOAD-RENDER-01

2026-10-01，M8.1。精确修改 tests/browser_click/interstore_business.py 的 upload；所有关联验证已收尾，保留 business-interstore-20261001-01 原失败。

原文件 POST 成功后 formDialog 自动重新 render 原Case，脚本立即重载同页时可能先捕获上一文档的原GET，导航销毁响应体后出现 Network.getResponseBody No resource。原文件事实及守卫已成功，尚未发审批，不能据此标原业务失败。

在点击唯一原上传提交前订阅原 GET /api/flow/cases/{本次原ID}，等待该次原 UI 自发 render 的原响应和新文件DOM；取消上传后立即强制重载。核对真实200、Case ID、门店、当前版本及新文件ID/名称，并保留原上传字节/SHA/结构检查/当前本人/店/有限表守卫与读取零写。初始进入原页仍用既有真实导航；不增加重试、忽略错误、全局sleep、fetch/Cookie桥接或改生产上传合同。全新隔离实例复验五项原申请、双方独立审批、实物出入、退回和原结算。
