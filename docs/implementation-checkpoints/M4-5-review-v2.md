# M4.5 中间编码审阅 v2：待授权队列补丁草案

日期：2026-09-28。延续 v1，前三个已授权生产文件及其指纹不变。此报告不放行 CP-09，里程碑及门禁状态仍只在 implementation_plan.md 维护。

## 本次新增的可审阅产物

精确代码 diff：`docs/implementation-patches/PATCH-M4-5-02.patch`。只为 queue._safe_retry 补本 Run 建立新 Plan 前真实已完成成果的来源判定；新增两个只读辅助函数，不签发 principal、不要求过期 worker 仍持有租约，不执行网络/模型/业务提交，不修改历史归属。

审阅修正三项：

1. 最新读取依据同一个 Run、同一稳定 item_key 的最大 attempt_no 和完整真实关联组，不依据 created_at 或随机 ID 排序。
2. 保留原错误分类拒绝；删除跳过旧非瞬时失败的特殊分支。后来查询成功不自动覆盖原队列的拒绝规则。
3. 同时核对持久 GET 意图和原工具 arguments.body 为空，不能因内部规范化 helper 忽略 body 就放行不可能成功的原输入。

完整模型调用、父/子项、批量原行、WorkItem/卡关联逐一核对后，只生成历史 manifest/WorkItem ID 集合；这些项仍继续经过原卡片状态、过期、supersedes 和未决确认守卫。历史例外不新增旧 carry/重准备兼容。源码审阅未发现须扩大本补丁范围的问题。

## 静态证据

| 对象 | SHA-256 |
| --- | --- |
| 生产 queue，修改前且本轮保持不变 | c1d5265d74ea63287b38ab8e88eb35bbedfa2e2338bb9b73804fabb9d6ea6c3d |
| 待授权代码补丁 | 7ce0e46660b9443ae1ea55c1e146066ae674726956d74cba4aee10da293d2af2 |
| 内存候选 queue | b0fa3b811d12bdb434541cc958033b71522624bcab8b91f24f4776af797ee60c |

- `git apply --check docs/implementation-patches/PATCH-M4-5-02.patch`：退出 0，只检查，未应用。
- 外部 Python `-I -B` 使用标准库在内存重建候选并解析 AST：退出 0；仅 `_safe_retry` 的已有函数 AST 改变，新增 `_retry_model_frame`、`_completed_unbound_history`，其他已有函数保持。
- 同时断言无 U+FFFD、无 covered_reads 特殊跳过，原错误分类判断保留，原工具 body 核对存在，并再次核对生产文件字节未变。

这不是测试通过。未导入 app、执行候选、访问数据库、运行测试或模型。没有本批后台验证进程。测试仍 deferred_to_deepseek，v1 和原计划的全部验收保留。

## 当前依赖

PATCH-M4-5-02 的单文件扩围授权问题已经发出，尚未收到答复。生产 queue 未改；M4.5 仍 in_progress，M4.6 未开始。用户授权后先核对源/补丁指纹，再应用、复核接线并登记实际产物；不以补丁草案存在代替授权或里程碑完成。
