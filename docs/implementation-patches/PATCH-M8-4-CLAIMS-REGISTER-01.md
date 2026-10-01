# PATCH-M8-4-CLAIMS-REGISTER-01

2026-10-01，M8.1。依照 PATCH-M8-4-BUSINESS-193-27 静态冻结候选 repair_claims_business.py SHA256 82f66f195cb313df6bab71184ffb3c5e2bdbd14eacbe5668213778231d10baa7，及独立原回执/版本/岗位/输入到结果复核，允许将其加入 tests/browser_click/run.py SCRIPT_FILES、tests/browser_click/scenarios.py 的 import 与末尾三元注册。所有既有验证已收尾。此注册不改变候选、夹具、目录、原生产合同或任何结果。

42场景、35受指纹脚本；新增 repair-claims-hk035-036-039-040-041 单场景720秒，仍用新外部白名单镜像与原七项同轮完整passed依赖，不从历史报告继承原单/成绩。原结果部分完成即失败、后续不继续，模型仍外网阻断。首次仅最小八场景闭包；完整联合回归在各新增增量收尾后进行。runner整体1800秒和CI40分钟暂保留，若本轮实际完整工作量需要再按证据登记预算，不放宽动作/版本/事实检查。业务、人工作用评价、PG/Linux/员工和生产状态仍未发布。
