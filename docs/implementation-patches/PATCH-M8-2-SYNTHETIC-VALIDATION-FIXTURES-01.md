# PATCH-M8-2-SYNTHETIC-VALIDATION-FIXTURES-01

2026-10-04，CI37183964600两平台均已自然终局failure（Linux07:22:31、Windows07:39:58 UTC）。Linux原件已独审：strict22、matrix/A/B/C/D/E/F全部通过，原18独立收集得到203节点但未执行；full27/101命令，750通过、33失败、2624未执行。33项调用失败来自两个旧合成验证夹具；Windows完整原件另行核对，不推定其失败相同。

`tests/test_m02_binding_contract.py` 的临时validation树遗漏当前已绑定的 `harness/runtime-platform.json`，32节点均在计算输入指纹时失败。`tests/test_m02_diagnostic_contract.py` 的 `test_main_routes_full_and_diagnostic_without_reusing_outputs[full]` 临时任务缺少 `baseline_inventory`，被当前完整清单守卫正确拒绝。真实runner、严格绑定和完整清单检查不因此放宽。

允许仅修V原overlay中上述两文件的合成夹具：补显式合成平台文件；给main接线测试补完整的两个合成测试文件清单、镜像字节及对应overlay来源哈希，使真实 `registered_inventory`、聚合和结束时输入核对继续执行。必要IO替身仅作用于该测试的合成文件，保留原main、清单守卫、诊断选择、聚合、调用次序和全部断言。不得改原测试函数/参数化节点、放宽断言、删除失败、修改生产源码、统一入口或依赖。

day在外部独立候选目录保留before/candidate/diff及静态审阅；mobile独立审阅，root合并SHA和来源登记。允许同步原restoration及M0.2/M8.2对应overlay条目与源胶囊inventory，不改变全部801输入范围、74精确节点数组、101命令、原授权或Linux适用项。其余输入逐项保持；旧run、源与失败证据原样保留。

静审后先通过原V统一入口执行全新同指纹M0.1 strict，再用现有M0.2.B `--diagnostic-command b01-validation-contracts` 做本地定向复验。该诊断仍先完整收集，不新增M8.2诊断接口，不替代业务或全量验收，phase/milestone保持false。随后冻结新输入，执行新同候选双平台M8.2完整101命令。M8.2仍唯一in_progress；未执行范围和后续技术、员工边界保持。

候选和独立静审已完成：`V/closeout-20261003/m82-synthetic-validation-fixtures-candidate-20261004T075349Z-2ecf2a6e5e`，binding SHA `3d845d073cb96a559d22230f22ea147a1e57ce954c993ee47113a4662efd5039`、diagnostic SHA `636b6496c49c2b35793ecc27a0d8c2ee04bad35468d3d8559ba83943ac15e88a`；作者静审 `3bda5f4876b7d003b4d11adf90550d6f078ec657868ea31ff0d68f98414f48eb`、独审 `b500e73e9d4f9c605dab8de61671196013c39b7f112b822b6b5aee98b8189265`。全部原Assert及函数/参数化保留，逆向整字节与AST一致；未运行测试或导入app。

root合并登记在 `V/closeout-20261003/m82-v21-merged-20261004T075841Z-36adb0b3b1`：实际仅两测试与restoration共3个输入变化，其余798逐SHA保持；manifest原overlay条目仅为路径列表，故无需改动。restoration SHA `acf3f44b3093573971e079db7a67b0ca0cc8e5610b379fd55bd6fdb144cd13c7`，v21 draft SHA `34a9b8474847673b5705d32c6c54f36f6d35bbcedfa5856ae87792bebf1b481a`。真实overlay、清单、聚合和全部终局守卫保持；新实际复验待执行。
