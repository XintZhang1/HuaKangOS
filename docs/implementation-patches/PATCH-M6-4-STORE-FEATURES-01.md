# PATCH-M6-4-STORE-FEATURES-01：切店时按目标门店读取首页开关

2026-09-30 原生点击 automatic-20260930-01 证实：助手内切店后回到“我的工作”。switchStore 在 pending 阶段调用普通 loadAssistantFeatures，被原 api 的切店保护在请求前拒绝；catch 把 features 清空，从而选择旧默认页。

当前 M8.1 集成精确范围：仅 web/app.js 的 switchStore/loadAssistantFeatures。按目标门店显式调用 GET workspace，沿既有 storeRequest 控制面；身份和目录仍由原 readStoreContext 获取，版本守卫保持。失效的迟到读取不能覆盖当前 features，真实读取失败仍明确保存读取错误。生产开关默认值不改。

新点击脚本保持 running 状态下切店、当前门店/助手入口/空上下文及迟到响应隔离断言；首轮失败完整保留，使用全新隔离目录复跑九组。
