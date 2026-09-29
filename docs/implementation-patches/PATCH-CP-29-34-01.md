# PATCH-CP-29-34-01 执行器重绑与外部合同夹具对齐

2026-09-29。本补丁只涉及**仓库外统一验证执行器**与**外部合同测试夹具**，不修改仓库内生产源码。

## 1. 执行器重绑到当前仓库

- 现象：`V/runtime-v1/binding.json` 与 `validation-manifest.json` 的 `repository` 均为
  `E:\HuakangOSFeature`，该路径在本机不存在，导致统一 runner 无法验证当前 `E:\HuaKangOS` 源码。
- 处置：重绑前备份 `binding.json.bak-20260929-edb5`、
  `validation-manifest.json.bak-20260929-edb5`、`archive/baseline-restoration.json.bak-20260929-contract`；
  两个文件均改为 `E:\HuaKangOS`（用 `json.dumps` 生成合法转义，反斜杠不手写）。
- 异常路径：首次替换手写反斜杠使 manifest 成为非法 JSON（`Invalid \escape`），已从备份回滚后重做，
  并以 `json.load` 复核；不再手工拼接路径字符串。
- 登记：`m02-progress.json`、`latest-run.json` 等历史记录不改写；旧备份与旧 run 全部保留。

## 2. 外部合同夹具对齐真实原接口

两处夹具写了原业务不可能出现的形状，导致里程碑失败。原件保留为
`<name>.bak-20260929-pre-fact-linkage`，差异可逐条追溯：

- `tests/runtime_domains/test_dossier_grant.py`：发起店夹具补 `'source_side': True`。
- `tests/runtime_domains/test_service_order.py`：提交补 `case_id/quote_id/line_key`；顶层补
  `results`；`outcome` 的非法取值 `pending` 改为 `rejected`；“旧提交不能当当前结果”改为同一
  `line_key` 存在更新提交；结果指向他单提交的断言改为“提交关联不完整”；空 `results` 改为
  断言“尚无批准结果”。

`archive/baseline-restoration.json` 中两条 `overlay_additions` 同步了新 sha256 与字节数，执行器
哈希校验通过；未删除任何断言，未降低断言强度。

## 3. 隔离边界

- 未读取、迁移或触碰公司数据库、用户预览库、真实 `.env`、密钥或客户附件。
- 未调用真实模型；`real_model_calls` 全程为 0。
- 未新增数据库、日志或缓存到仓库；测试产物全部位于仓库外验证根。
