# PATCH-M7-1-PROPOSAL-TIME-PRECISION-01

2026-10-02，业主要求虚拟数据尽可能优化后交付，仍只 M8.1 在办。批量脚本静态独立审查发现：session_view 按数据库完整 created_at/id 排序，proposal_view 却用秒精度 stamp 输出 created_at，前端 CardGroups 再按该时间和随机 UUID 排序。同秒生成的批量卡可能偏离真实创建顺序；不按随机 UI 顺序重排原合成输入求绿。

精确生产范围仅 app/business_assistant_service.py 的 proposal_view.created_at 字段：输出原数据库时间的固定六位微秒 ISO Z。原数据库时间、ID、请求、步骤和业务事实不修改；stamp 其他使用、expires_at、前端排序与单卡/批量确认接口保持。该格式保留原 UTC 合同并对齐完整创建时间的先后；原精确同刻仍保留前端原 ID 回退，不声称 Python 字典序与前端 numeric localeCompare 相同或本补丁修复该独立边界。不生成新的排序字段或重写历史卡。

异常路径包括同秒不同微秒、原精确同刻、已成功/失败卡重读、旧卡及过期卡。由新的三卡批量原浏览器路径核卡片 A/B/C 显示和逐张提交次序；静态解析和独立源码审查先完成，旧候选通过不能继承为本生产变更后的实测。原人工确认、版本与权限守卫、默认关闭功能和正式验收边界不变。
