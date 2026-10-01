# PATCH-M8-1-CLAIM-PROOF-FIELD-01：理赔原件类别接线

2026-10-01，按维修后继HK042候选发现的原UI/API静态不一致修复。精确生产范围只有`web/claims.js`的claimAction原件字段。原通用表单显示/就地上传统一evidence，而原_proof非资金只收authorization，实际资金和resolution_apply收receipt；原file lookup未按普通类别过滤，因此不声称此处已发生实际422。

沿现有moneyKeys及resolution_apply将原件类别对应receipt，其余普通核价/发送/独立评审用authorization；assess/result、resolution/return_plan独立表单沿其原合同。后端、文件安全、重复SHA、角色/任务、客户直接到账不产门店现金、版本与原金额守卫不改。修复后语法及静态逐动作审阅，实际HK042还须同轮首维修后继真实点击。源码接线不是该需求通过，未覆盖支路保持待测。
