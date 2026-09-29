# PATCH-M8-1-SUITE-SELECTION-01

2026-09-29；M8.1 保持 in_progress。

原隔离入口复制所有 test_*.py，但执行器硬编码 10 个文件；新增业务族测试可能被复制却静默不运行。允许修改 `tests/assistant_offline/run_isolated.py`、`run_validation.py`、`README.md`，新增 `tests/test_validation_selection.py`：默认发现全部后端套件，浏览器仍由显式模式控制；可重复提供 --suite 定向后端测试，未知/重复/路径形式拒绝，不遗漏所选项。前端与语法检查保持运行，定向结果标 scope=targeted、selected_complete=true、complete=false，不冒充完整回归。入口自身纳入套件指纹；CI 不使用选择参数，仍运行全部。

所有执行继续由 run_isolated 复制到新的外部目录后进行，禁止读取生产配置、复用运行库、泄露密码或调用真实模型。先验证选择器、定向红/绿，再执行默认完整回归与原生页面；日志追加而非覆盖。
