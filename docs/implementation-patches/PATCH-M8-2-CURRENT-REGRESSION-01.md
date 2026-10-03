# PATCH-M8-2-CURRENT-REGRESSION-01

2026-10-03；M8.1原五条故障门禁已收口。当前唯一M8.2 in_progress。补齐当前候选的原适用基线、新Runtime/domain合同及已implemented早期原检查，保留历史证据与每项原标准，不恢复旧app或退休浏览器桥接。

精确范围：V/run_validation.py；V/harness/isolation.py、baseline.py、baseline_results.py、baseline_aggregate.py、verdict.py、fixture_profiles.py（实际collector与groups逻辑在run_validation.py，不新建同名假模块）；V/validation-manifest.json、archive/baseline-restoration.json及本轮独占依赖锁/平台绑定；原18 unittest及fixture_env/fake_provider/build_base最少辅助源码仅恢复在V的独立执行域；新增共享原合同测试、当前capability-matrix生成/审阅脚本仅在V本轮目录。CI必要接线限新增 `.github/workflows/full-regression-checks.yml` 与源码-only外部验收输入胶囊包装脚本，具体文件名在写入前补记。根正式实施计划、当前architect任务/索引及本检查点允许维护；total_plan不改。生产代码未授权宽改，真实缺陷先登记必要精确补丁。

执行先有最小真实collect/守卫验证，再按精确完整清单运行。原B参照严格绑定与聚合必须应用M8.2，baseline缺/多/重复/空/非终态/未知skip均失败；原五个废止项的来源/理由保持。实际收集文件前缀等于登记目标及原件清单；18 unittest保留原独立进程和合法继承节点，不静默去重。补原早期32项六个共享边界组，并逐项映射实际结果，不用AST数量、声明路由或历史成绩代替。

各平台独占短目录、实际版本/依赖/Node指纹和own process lifecycle。Windows通过已有管理权限的GitHub专用VM执行原symlink和launcher合同，不改业主OS设置；Linux原junction1及PowerShell launcher9节点按实际collector精确列平台不适用，其他skip仍失败，通用symlink两平台必须实际执行。GitHub仅代码/测试/冻结定义输入，禁止环境、密钥、库、附件、截图、日志、证据、venv或公司数据；不恢复旧CI/退休浏览器。

D/D+1原native库、凭据、源/script镜像、V原venv与Chrome继续封存；M8.2使用新的独占环境/venv和镜像，不写日期实例、不动原物理依赖。当前原五条done不表示追加Date、PG/live/OS浏览器/独立部署/员工/生产通过；所有原门槛留相应记录。任何失败保留原件并分类，只修实际原因，不加自动业务重放或降低断言。

2026-10-03 精确分工：harness负责人只维护上述已存在V脚本的M8.2注册/完整清单/聚合/平台及owned进程接线；18 unittest与共享A/B/C负责人只写V/tests/m82-closeout/original-unittest、shared-contracts及该独占辅助目录，原archive/overlay原件先留SHA与拷贝来源，不修改归档。D/E/F共享边界独占V/tests/m82-closeout/runtime-boundaries。新增注册入口/报告器如需新文件，先向root报精确路径，由root补记再写。测试执行仍统一经V/run_validation.py，真实app import前镜像/隔离/网络守卫；shared输入未齐前不跑正式全量，各负责域只静态/审阅准备。

2026-10-03 23:14 精确入口补充：原18独立域入口为 `V/tests/m82-closeout/original-unittest/entry.py`，镜像目标 `tests/m82_original_unittest/entry.py`，只处理登记的 `--suite` 原文件名及实际 `--collect-only`，保留继承节点与重复检测，每命令独占合成运行域。D/E/F文件为 `V/tests/m82-closeout/runtime-boundaries/test_runtime_principal_stream.py`、`test_runtime_checkpoint_recovery.py`、`test_runtime_provider_budget.py`、`_runtime_support.py`、`_runtime_read_worker.py`；辅助源码仅服务已登记合同和owned子进程，不引入新runner或直接业务提交。root当前矩阵生成与合同的精确文件为 `V/tests/m82-closeout/capability-matrix/generate_current_matrix.py`、`test_current_capability_matrix.py`；只在统一隔离镜像内生成当前路由/schema/来源矩阵，不执行业务写入或模型调用，旧矩阵和原生成器只读保留。

2026-10-03 23:28 CI胶囊包装/独占启动精确接线为 `scripts/package_validation_inputs.py`。只读取manifest显式登记的harness、归档原测试、overlay、supplemental、依赖声明与来源JSON，逐SHA封装，排除环境/数据/日志/备份/凭据/运行证据；验证ZIP路径、大小、完整清单与SHA后解压至全新外置目录，独立安装venv并记录实际依赖/平台指纹。禁止写原V/日期实例或修改原断言/历史证据。对应双平台工作流仅使用此代码输入胶囊与当前Git候选，运行当前strict和M8.2；云依赖安装与测试执行分阶段，实际app仍只由统一runner的合成镜像导入。

CI调度接线补充 `.github/workflows/browser-click-checks.yml` 的可选手动胶囊输入及同commit reusable job，原无胶囊80场路径保持。原因是GitHub新dispatch工作流首次触发须存在于默认分支，而本轮明确全部技术完成后才一起上传main；从已有默认分支入口在候选ref调用新 `full-regression-checks.yml`，不提前改main。依据：[GitHub dispatch合同](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch)、[同commit reusable合同](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)。完整注册/原件审核仍按上述条件，工作流绿灯不代替实际报告。

2026-10-04 精确守卫补充：仅已有 `V/harness/selftest.py` 的 Linux strict 合同追加四条 owned POSIX 进程组实证，覆盖正常结束、非零退出、超时以及 leader 早退而后代持有 pipe；调用既有 `isolation.execute` 并记录实际节点、进程组与排空结果。Windows 原 strict 清单保持，未实际排空不得通过。M8.2 full 继续要求同五指纹的本次 strict 参照，不增加独立测试入口或未知 harness 文件。父 CI 对胶囊回归使用独立 concurrency group 且不自动取消，避免普通 browser push 终止正在执行的长回归。

2026-10-04 实际准备失败及窄修：v3/v4 first collector分别3305节点/2与5导入错误，均自然退出2、owned lifecycle drained=true、无超时；18原套件尚未启动，不能记passed。只按实际镜像包名补共享helper、B/C和D/E/F的 `tests.` 导入前缀，去除不再需要的child顶层路径插入，不改断言/业务合同/网络守卫，旧copy和失败日志外置保留。CI37137950279在启动阶段失败：Windows无3.11.14包、Linux草稿asset访问被拒，未执行回归；固定改为官方清单两平台均有的3.11.9，不浮动版本。草稿输入仅具push访问身份可见，current-regression手动job及对应reusable job单独使用contents:write，原browser仍read；该短期token只给固定资产读取步骤，不传测试环境，不发布release或推送源码。asset错误只补实际HTTP数字诊断，凭据、签名URL和响应正文不输出。依据：[官方Python包清单](https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json)、[草稿可见性合同](https://docs.github.com/en/rest/releases/releases#list-releases)。修后须新独占copy和实际collector/CI报告，不继承旧失败节点为通过。
