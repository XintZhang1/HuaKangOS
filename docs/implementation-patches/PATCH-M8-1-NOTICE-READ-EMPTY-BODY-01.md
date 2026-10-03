# PATCH-M8-1-NOTICE-READ-EMPTY-BODY-01

2026-10-03；M8.1 late-source 原通知点击实际 HTTP422。允许范围为 `web/assistantworkspace.js` 的 `openNotification` 已读 POST 参数及 `web/businessassistant.js` 共享请求层保留未提供 body 的空体语义。

服务器原 `assistant_runtime_api.py` 明确拒绝该固定已读入口的任何 body；前端却发送 `{}`。去掉 body 参数，沿原本人 Cookie/CSRF/当前门店发一次空 body POST；不放宽后端、权限、来源可见性、通知状态或错误处理，不重放失败提交。原读通知不办理任务，原 source 和业务事实保持。

原失败与422网络证据保留；Node 语法、源码独立审阅及新真实点击结果分别登记，本记录不代表通过。

独立审阅发现只删除调用参数仍会由共享请求层的 `JSON.stringify(body||{})` 补回 `{}`。共享层在 body 为 undefined 时不附加 body；所有非 GET 仍带原 CSRF/current store 与原 JSON Content-Type，所有已显式提供对象的提交保持原 JSON 编码、multipart 文件入口守卫、上下文失效与错误处理。当前其它写入调用均显式传 payload，不用空体替代原表单。

08 实测真实空体已经成立，但同时去掉类型头触发原 `app/main.py` 全局安全入口 415；这次失败保留。恢复原类型头，仅保留未提供 body 的空体语义，不放宽全局安全中间件或后端已读入口。08 本轮4执行2过2败，CLI1/service0且未强杀；通知仍待新候选复验。
