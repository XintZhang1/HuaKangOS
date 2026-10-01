# PATCH-M8-4-INTERSTORE-READ-SETTLE-01

2026-10-01，M8.1。全部关联验证进程已收尾。精确仅 tests/browser_click/interstore_business.py 的 read_page同hash分支。

interstore02已经过上传及零启用批准，整车调拨创建201后原location.hash触发详情GET200；紧接原同hash reload 的只按path观察又捕获即将被销毁的旧文档响应体。源码与实际顺序支持此原因，尚无本次调拨审批/出库，不记后端拒绝。

同目标hash时，在设新的GET观察和reload之前，等待原提交modal关闭、原main loading消失、当前已知详情标题确实呈现。原render在开始同步清除旧main，成功完成才还原标题；创建详情与列表标题不同。因此先完成本次原自动渲染再独立重读，避免两文档读竞争。保留原GET200/完整返回/DB-CAS/本店岗位/全库读取不变；不忽略JSON、增加重复POST、固定睡眠、fetch或Cookie桥接，也不改原生产导航。上传的专用原render等待仍保留，后续新实例复验整链。
