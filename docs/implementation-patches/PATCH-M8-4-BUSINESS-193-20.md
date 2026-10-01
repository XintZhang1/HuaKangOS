# PATCH-M8-4-BUSINESS-193-20：车辆导入与单店实物流转六项候选

2026-10-01，当前M8.1，冻结 `inventory-next-scope.md` SHA256 `35bc5eaa05359f0c3cf54344a0e6a7802e63e78ac9de388afe4dcaf341496c8e` 的优先车辆六项019/027/028/030/025/023。作者仅新增 `tests/browser_click/vehicle_operations_business.py`、`docs/architect/tasks/vehicle-operations-click.md`；生产、fixture、目录、共享入口/注册与实施计划只读，不导入app或启动应用/浏览器。

消费本轮采购/主档完整passed的明确车型、供应方、原仓/库位与账户，经原UI新建并独立批准新两VIN采购，不拿已付收齐旧单重复请款。原funds/ship/receive三CSV批次逐原trial、独立review、本人confirm，原来源与当前CAS精确绑定；trial业务回滚与该批原记录/日志分开核，不能粗判所有表零变化。CSV只放外部runtime、整数分/真实VIN/有限manifest行，无脚本造业务成果。

A车原同店移库→其他出库→原单退回的新库存代次，B车保持原采购来源→采购退回及原付款账户实际合成退款。实物/批准/请款/真实合成款各自留原事实；新代次/current_vehicle_id必须重读，旧车/成本/现金/占用/Position与Custody逐行保护。全正写仅原UI，SQL SELECT-only、已知结果不明停止、不重放。原跨店020/024等及后批库存/维修本批不实施、不计数量。六类人工/原外部与生产门槛保留；冻结和独立短审后根才注册新镜像，未执行无成绩。

根接线范围追加：所有关联实例已退出；候选811c59e075ca513a9e29a6c397f482eaaa0a342199b68138aba7a66a8fc249d7经根及独立只读审阅，没有确定静态合同缺口。仅tests/browser_click/run.py的SCRIPT_FILES与scenarios.py的import/BUSINESS_SCENARIOS追加，三元场景720秒，不改父场景/fixture/生产。先新鲜同轮采购、主档及本候选三个原UI场景实际验证；未执行不计六项通过。
