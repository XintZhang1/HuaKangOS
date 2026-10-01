# PATCH-M8-1-LEGACY-STOCK-DISPLAY-01：原库存状态与零库龄显示

日期：2026-10-01。人工 IAB 在隔离 `business-manual-vehicle-purchase-20261001-01` 实际登录、按本轮 VIN 查询库存、展开车型及采购原单，核对独立财务已付/实际验收 210,000.00 元。原库存页面另见两个显示缺口：当天入库的 `stock_age_days=0` 显示 `—`；背景真实占用的 `stock_state=reserved` 显示工作流“订单待确认”，而原库存词义是“已预订”。后台事实与当前采购状态未改变。

根因：`legacyCell` 普通值用 `v||'—'` 把零当空；库存/原销售交付/原维修完工字段调用通用 `pill` 时优先读取工作流同名状态。已核对 `app/services.py` 的实际库存派生与库龄计算，以及 `app/schemas.py` 原销售 `ordered/delivered`、维修 `open/completed` 合同；`web/app.js` 原 `labels` 已包含相应词义。

精确范围：仅 `web/app.js` 的 `legacyCell`。原 `approval_state`、`stock_state`、`*_stage` 显式使用已有原标签，未知值显示原值；普通值保留数值零及布尔假，仅 null/undefined/空字符串显示 `—`。通用工作流 `pill`、原提交/API/权限/金额/库存状态计算及四个生产开关均不变。采购点击脚本 HK-029 在实际当日验收后精确检查 API 零库龄及“库龄（天）”对应单元格为 `0`，保留严格“已审核”断言；后续真实订单占用检查原库存“已预订”。维护对应任务、计划及审阅记录。

实施前：本次隔离服务及关联验证进程已收尾，原失败与截图仍外置可恢复。实施后以全新目录执行受影响实际采购路径，再人工查看库龄列；不把背景占用或静态源检查计为订单业务验收。193 完整业务、真实银行/实物、ClamAV、PG/Linux、员工试用和发布仍按原条件。

实施审阅：一行修复已落盘，Node语法通过。test_inventory独立只读核对services39–48、schemas65/81和原labels，未发现静态合同问题；通用pill未动，0/false保留。实际重验尚待执行，不记通过。
