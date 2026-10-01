# PATCH-M8-4-MEMBER-PRICE-REFUSAL-OBSERVATION-01：会员价自批拒绝的真实记录

2026-10-01，仅未注册member_points_tier_business.py的本人自批403观察，原候选108b77ef静态独立短审发现，尚未实际执行，不登记为实测失败。原rejected_submit helper整库不变要求与原main.record_refusal不符：真实403即使业务规则category=rule也追加escalation_refusals，can_escalate=false。不能为了绿测试删记录或把业务拒绝译成权限不足。

仅此403分支改为精确允许一条本人/本店/原POST价格approve路径/403/服务器原exactmessage/category rule/source page/consumed_at null的原refusal；其余每一旧行、所有业务/原价/资格/钱包/现金/Task及其他表不变。拒绝只点击一次、读真实响应，无另造拒绝或重放。422非整倍、409超过可用积分仍保持原零业务写检查；不改原helper/生产/目录。作者owned两文件在原PATCH23范围内更新并重冻结，根及独立短审后才能注册。当前其他运行不镜像该候选；193人工及原门槛不变。
