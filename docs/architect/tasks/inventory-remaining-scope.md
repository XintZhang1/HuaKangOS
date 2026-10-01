# 任务：机构库存查询的实际授权和在途范围

2026-10-01，root 只读研究，无运行/注册/生产修改。HK071 原题“机构库存查询”，原入口 warehouse，唯一完整 check 要求实际切另一授权店、非空库存/位置/在途只本店、未授权不可读、集团汇总只读且不当本店可用量。原期末库存的零在途和页面检索不替代这一正向链；没有新完整结果。

## 有限来源与最小候选

建议同轮完整父为 system-management 的新员工乙、master-data HK184的第一个物资库位、material HK069 evidence.second_location.row.id及material_sources.primary.location_ids的第二原库位、warehouse-original 与 interstore-original 的非空两店真实库存。主档父并未创建两个库位，不把后继材料创建计入主档。全部父 executed/passed、complete/passed、checks完整且当前镜像指纹一致；仅有限metadata和当前ID读取，不 SELECT latest、拼旧run或造库存。已有跨店五项结束后的 destination_item_id 在二店实际有库存，source_item_id 在一店须即时核可用量/库位；移库选新500千分单位前须当前真实原可用足额，不从旧父快照猜。

库存这里只要求物资，不为统一模板增加整车采购或调拨。真实在途来自仓储原 local_move 的 transit_case_id/warehouse_balances；跨店发送和店内移库是不同事实，不相互替代。用同轮一店已有启用原物资和两个明确 active 库位，原库管新建500千分单位店内移库，独立主管批准，原库管实际 dispatch，产生一明确店内在途 balance、原两条 Entry，门店 total 不变而本店 available 与 transit 按原 inventory_availability 核。源库位当前不足则明确实际条件失败，不能改数量或虚构源余额。读取验证后从原单原库管 accept 完整500，原 source/destination/transit 和成本守恒、original rows保护；读阶段非零在途证据独立保留，不以最后清零替代。

新员工乙限定 system-management HK191 staff_actions[1]（原一店manager），私有密码仅从本轮唯一外部凭据指针读当前阶段并加入 scrubber，证据无密码/hash。首次本人一店登录，原下拉没有二店，原导航 warehouse-item/{二店原item} GET404不泄漏本地ID/库位/成本；仅原本可读源，不注入store/角色。

管理者原 #users 显式保留乙原一店manager并增加二店auditor，can_group_summary=true，账号默认role/name/active不变；真实 UserUpdate/access_version/AccessReceipt/精确受影响店 WakeEvent、本人所有旧会话撤销。重新本人原登录后通过原店选择切二店，再实际 warehouse 搜唯一原名称/编码和打开 warehouse-item/{二店item}，只比二店当前非空库存、真正位置和原entries；再切一店核同轮非零移库在途。不同店的 local item_id、名字/单位/可用/已占和库位不混作同一行或集团可用量。

集团选项仅走原库存汇总可读入口。warehouse catalog 当前明确 _aggregate_scope 时 can_read/can_create/can_money 均false，不能强迫仓储全店详情返回集团操作或把这正常限制记bug。沿原主库存/analytics只读汇总核实际授权店集合、全部非空库存范围及没有新增/提交/物资领用入口；汇总数字不能说成本店可领量，服务端仓储原单保留 single_store 约束。现金/库存/任务/原业务在全部查询阶段不变，真实导出额外审计按原接口单独记录。

完成原实际接收后，原管理页恢复乙最初角色、店集合与原汇总开关，access_version只递增不能回写原值，旧会话依然无效；本人重新登录确认二店选项消失、原二店item GET404。原职责/临时测试账号管理均保留当前凭据代次，不能借admin读库存作为乙的成功。若同轮HK190已执行，其所有旧Grant/File/Decision/Access保护；乙改权不使已suspended/revoked/expired授权复活，其他员工/密码/Cash/StockMove/原历史不变。

## 原实际合同与后继登记边界

app/warehouse_api.py 原catalog允许READ且非aggregate；items与stock在warehouse_service.authority中沿StoreScoped筛选。stock_view返回quantity_milli/available_milli/reserved_milli、原各balance.location_id/location_name/transit_case_id/quantity和当岗位允许时value，entries最多五万完整来源超限413，不静默截断。原local_move dispatch保留店总量并移动源与transit价值，accept只实际尚在途数量且到原目标库位。原 #warehouse-item/{id} 表必须沿这些真实来源，不增加group_summary可写接口。

建议后续仅新增 inventory_scope_business.py 与 inventory-scope-click.md，单有限场景/一完整HK071；待根登记精确范围和独立原接口/父metadata核对后实现，不修改原角色/仓储规则、已有fixture/helper、源目录或计划。当前没有测试候选和实际结果。真实跨店员工授权、资源上限、并发占量/改权竞争、PG/Linux和全193人工及生产条件独立待测。

2026-10-01 来源文字纠正：第二库位由同轮 material HK069 原创建，不是 HK052；只纠正文档定位，不改变数量、业务来源、权限或验收合同。
