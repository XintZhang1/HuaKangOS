# HK099 同实例 D / D+1 原生授权补充草案

2026-10-01；子代理 manual_review_draft 准备，root 负责决定实际执行/日期等待/审阅。允许改动仅本文与仓库外 `C:/Users/tiefu/.codex/HuaKangOS-agent-validation/runtime-v1/browser-click/launches/hk099-date-review-draft.py`。本次没有执行草案、启动浏览器/app、读取私有凭据或执行 SQL，没有修改生产、测试、runner、CI、目录、共享索引或自动报告。

依据 `hk099-native-review-preflight.md`、`hk099-date-followup.md` 的已登记原 helper/字段。从同目录 `native-review-draft.py` 只复用 full53 preflight；父53场、覆盖193/111/70/9、逐文件镜像/脚本哈希、完整父 checkpoint、仍 retained 服务都须成立，**不要求193 business accepted**。预检代码与 Date 自身 SHA 随 before 记录，after 必须相同；源镜像/数据库/服务/自动证据也必须同轮。仅 helper 来自该轮 scripts，未导入 app。

`--phase before`：CF 的 `report_sources.customer_vehicle_id` 必须等于 REM 的 `partial_requirements[HK099].evidence.source_cv_id`；REM 顶层另一提醒 CV 不用作源车。接收 CV/customer/旧 Grant/Revoke 精确取该 partial；SYS 员工甲与 HK190 current_employees.receiver 交叉核对当前 roles/access_version，非 HK071 员工乙。有限 SELECT 核实际交付、两CV/同VIN/明确GroupIdentity/本地HistoryLink、原撤销完整旧行、同对无其他active grant；原用户与两店启用。接收口令按唯一同轮 SYS 私有指针的 receiver.current_password_stage 取值，不硬编码阶段或保存秘密。

原 manager 一店及 receiver 二店 service 独立同源会话登录，由 SYS 原 before_write/after_write 守卫登录审计/Session；完成后才取原 GET/业务基线。源本地历史和接收本地历史保存全条目，原 UI 仅新增一次 D 截止授权：原 form/fields/submit，Guard 仅允许 **1 HistoryGrant＋1 Receipt＋1 Audit**，旧行及其他原业务全部保护。不换 request、不重试、不 revoke；网络守卫只开放本次原登录及一次原 POST，其余业务/模型写拒绝。新 Grant 全字段、原 request values、Receipt digest/result、Audit actor/store/action/entity/reason 和 JSON null 逐项核。已知201先留独立事实，即使后继读取失败也不隐去成功原件。

D 日原 manager 列表显示“有效”；receiver 原 history 外部摘要逐条等于源本地项去 case_id 后的八键对象，原本地整行不变；外部 article 没有原单/文件/动作链接。三宽截图、原 GET、UTC/Shanghai 时间另存。D 日操作真正完整后写独立 `retained-before-midnight.json`，date_expiry 仍 planned_pending，不能预记跨日。

原 external strong 实际包括店名与日期，按已登记原控件用 has_text 核“已授权跨店摘要”；不误用整段等于短标识。接收 current_password_stage 还须精确等于同轮 HK190 receiver 的公开代次。关闭全部 context/browser、finish 收齐网络后再核错误/外网/被拒写/5xx/pending 与原自动字节，全部满足才保存成功 retained 和 observed preview。after 同时要求 before preview 的成功终局，未完成/晚到异常/不同代码均不能拼接。

root 分段等待真实日期，每次不超过60秒；脚本自身不等待、不改时钟/时区/SQL日期，也不重起服务。必须先串行结束站点只读审阅，再 before；等待期间不得并发办理。`--phase after --retained <上述独立文件>` 只在真实 Shanghai D+1 进入，先核 waiting 全原业务摘要不变，再以原独立登录 Guard 完成新审计后取读取基线。接收 history 外部项为0而本地全条目保留；manager 原列表“已过期”且数据库新 Grant 全行仍原 active，source 本地历史和旧 revoked Grant 全行保留。after 除两次原登录外只有 GET，没有新授权/撤销/业务写。

所有额外动作、网络、三宽PNG、失败、retained/preview只追加本轮 `evidence/manual-review/hk099-date-expiry/<phase>-<UTC>/`；不覆盖自动成绩或 HK099 partial。实际执行标签 `native_chrome_review_click`；自动PNG审阅、六项评分、HK099完整条件、193 accepted 和 provider终局均独立 pending。root 正常 stop 原 retained 服务后仍须核原 runner exit0、provider0/外网0，并逐合同审阅，不能用 Date 单一事实宣布 HK099 或项目全验收。

**检查与交接**：本次仅 AST 检查，不导入或执行草案；root 当前源/runner冻结，脚本不硬写旧候选指纹或搬旧run编号。真正调用前须核自有草案及依赖当前 SHA；before成功的 retained 冻结其精确代码/同轮来源，after拒绝不同版本拼接。暂无新增业务或人工通过结果。

当前外部 Date 草案 366 行，AST 通过，SHA256 `eb2f78f25ac6e626843eac3c2fdf21fa290bcff70ba1489a25a3752cd75ad858`；依赖 native preflight SHA 为 `4ccf21b0e0729319606c3019e29f0fa6b14a8521a58a3a515ce813d5acad4198`。Date 代码独立复审仍待 root 协调；本任务未执行任一 phase。
