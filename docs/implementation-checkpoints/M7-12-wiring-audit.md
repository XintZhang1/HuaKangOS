# 领域适配器接线审计（仓库完整度核对）

2026-09-28，集中测试阶段。目的：按目标要求核对"代码可导入、无语法/接线缺口"。
方法：仓库外只读脚本 `$ValidationRoot/staging/audit_domain_wiring.py`，对
`app/assistant_runtime_domains/` 做 AST 级核对，**不修改任何仓库文件**。

## 核对项与结果

| 核对项 | 结果 |
|---|---|
| 适配器文件数（不含 `__init__.py`） | **49** |
| 其中的适配器类数（`*Adapter`） | **49** |
| `__init__.py` 中 `factory=<类>` 的注册数 | **49** |
| 语法错误（`ast.parse`） | **0** |
| 未接线的适配器文件（类名未出现在 `__init__.py`） | **0** |
| 已声明但未注册的适配器类 | **0** |
| `__init__.py` 导入行引用的、在对应模块中不存在的模块或符号 | **0** |

**结论：49 个适配器全部「有文件 / 有类 / 被导入 / 被注册」，无语法或接线缺口。**

## 与计划的对应

- `implementation_plan.md` 中 `**状态**：implemented` 计数为 **93**（M6.1—M6.8 与 M7.1.1—M7.12.3；
  M8.1 为 `in_progress`），与本次审计的适配器面一致（M8.x 为验收类，不新增适配器）。
- 本审计**只证明静态接线完整**，不等于业务验收：原库真实数据、真实模型、浏览器、PostgreSQL、
  Linux、员工试用等仍属各 M8.x 的环境条件（见 `M8-1-partial-review-v1.md`）。

## 复现命令

```
& "$ValidationRoot/.venv/Scripts/python.exe" -X utf8 "$ValidationRoot/staging/audit_domain_wiring.py"
# 期望输出：适配器文件 49 个，适配器类 49 个，注册 49 个 / 问题: 0 / OK
```
