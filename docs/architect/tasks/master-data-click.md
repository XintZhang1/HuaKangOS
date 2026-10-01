# 主档 15 项原页面点击候选

2026-10-01。仅新增 `tests/browser_click/master_data_business.py` 与本任务页；候选未注册、未运行，不修改生产、fixture、run/scenarios、原需求清单、目录或计划。根在稳定镜像窗口接线并执行。

候选导出 `MASTER_DATA_SCENARIOS`，场景 `master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187`，最大执行窗口 480 秒。复用原采购候选的导航、原主档对话框、明确候选选择、复选框、select 和原拒绝留证 helper；沿既有 Evidence 与 external business-checkpoint.json，不新增执行平台。数据库接口只调用 SELECT，正向保存全部经原表单和同源 Cookie/CSRF。

| 原需求 | check_id | 输入到结果 |
| --- | --- | --- |
| HK170/173/176/180/185/186/187 | 各 HK-xxx-business | 七个原领域字典分别新增、改说明、停用、恢复；原类别/版本/审计与本店列表一致。另一实际合成店先由 admin 原页面分别建立同名条目，本店 manager 办理后对店及其他类别全行保持不变。 |
| HK172 | HK-172-business | manager 新增保险公司、修改理赔电话和结算天数、停启用，许可证号/原版本/回执/审计核对。 |
| HK174 | HK-174-business | manager 新增并改车间班组；负责人由实际员工候选明确选择现有本店 manager，原 ID 与标签核对；无业务引用时停启用。 |
| HK175 | HK-175-business | manager 新增按项作业、编辑参考收费和分钟、停启用；120.35/123.45 元由原 UI 精确转换 12035/12345 分。 |
| HK179 | HK-179-business | manager 新增代办项目、编辑费用与天数、停启用；80.25/85.40 元精确为 8025/8540 分。 |
| HK181 | HK-181-business | inventory 新增/编辑/停启用物资品牌，再与本场景零库存物资真实关联；原物资列表显示品牌 ID/name/code；有效 ItemProfile 引用后停用返回原 409 且业务全行不变。 |
| HK182 | HK-182-business | inventory 建父子分类、编辑/停启用并明确选父类；实际自指和循环各返回原 422，启用子类及有效物资引用下的停用返回原 409；分类树和 ItemProfile FK 保持。 |
| HK183 | HK-183-business | inventory 原物资目录新增零库存物资、将补货数量 1.125 改为 2.375；原整数阈值 1125/2375。原表单无库存/成本填写入口；另原 ItemProfile 明确选本场景物资、分类、库位与品牌，停启用不改绑定；原 GET/只读 DB 保持零库存/零价值、无 StockMove。 |
| HK184 | HK-184-business | inventory 新建 materials 专用仓和所属库位，编辑/无引用时停启用，再由真实 ItemProfile 使用；有启用库位/物资引用时原停用拒绝；不拿整车仓算本项。 |

采用原 `/api/dictionaries/{group}` POST/PUT/GET、`/api/masters/{kind}` POST/PUT/GET/lookup、`/api/flow/master/items` POST/PUT/GET。typed 与字典由原 request_id/CAS/version 办理；旧 flow Item 原合同只有 version，不为测试补另一幂等接口。每次保存核对原请求员工/店、响应/列表/数据库、原审计、typed 请求回执；原引用标签直接对真实关联表，未选择的自由文字不成为外键。只有已有 admin/manager/inventory/finance 登录，未新建账号，未办理需要独立批准的交易。

四个关联需求 181/182/183/184 共用本次实际物资来源，但各 check 留独立证据；品牌/分类/仓未完成实际引用前保持 running，场景失败时记 partial。首次出错当前需求 failed、已经完成项目保留其自动结果、依赖未结束记 partial、尚未进入者 not_tested；总场景不完整不 passed。外部源目录 hash 绑定，193 个合同不继承这 15 个动作。

人工 `simple_flow/concise_copy` 始终 pending，`business_accepted=false`、`full_193_business_acceptance=false`；自动完成只证明本次 UI/API/DB 断言。未结交易主档引用、有实际库存历史时改库型/停仓等分支明确 conditional/not_tested，不拿新零库存主档假称完整业务履约或库存验收。供应商、车型、整车仓、采购/维修/资金/会员交易不在本候选通过范围。

静态核对使用 AST 与当前原 API/模型/JS 对照，不导入 workspace app、不启动应用或浏览器。候选实际行为与耗时等待根的新镜像运行；源码审阅不记执行通过。

独立短审阅已完成（test_inventory，只读）：原字典类别/CAS/审计、typed 实际员工与引用标签、金额与千分位、分类自指/循环原拒绝、有效引用停用原拒绝、四个物资 FK 和财务只读核对均无实质静态合同缺口。复核全部 direct rows 调用为 SELECT-only，15 个源 ID/title/check_id、9 个 typed 表及 helper 符号已绑定。候选代码 SHA256 为 `42ec6e2e8e07e525fe59cd66d3d2106ba4a53aad405132c0cf9269f98136c4ba`。本次仅静态审阅，未运行或登记业务 passed；两文件至此冻结，由根接线后实际点击。

根集成登记：已加入原 `run.py` 白名单和 `scenarios.py` 的实际业务注册/汇总，注册共16组；独立短审结论及3文件AST通过。首次全新隔离执行待启动，未继承历史结果。生产新增库存零库龄显示修复已另登记精确补丁，原采购同列断言复验在其所属场景执行。

首次实际 `business-master-data-20261001-01`：采购7项（含真实零库龄列）通过；主档已由另一店原UI建七项同名对照，主管新登录停在字典目录。脚本再点同一原anchor却等待新GET而超时，HK170 failed、整场未通过。截图和网络保留，属装置导航误等待，原用户页面正常显示目录；未写本店条目，不假记完成。服务进程退出1并已收尾。根只在本候选dictionary_page识别已在目录时等待实际标题，直接点击目标字典；从其他原页仍观察原目录GET。无浏览器/API桥接、重试或断言放宽；全新镜像重验待执行。

第二次 `business-master-data-20261001-02` 主档15项全部通过，455动作/270点击、页面异常0、退出0，仅selected范围。人工master-stock01同指纹当次采购/主档两场景22项自动检查通过，实测零库龄/原预订标签及手机原主档表单；发现两个同名资料入口及分类重复介绍，人工partial。按REFERENCE-COPY-01修复展示后，IAB reference-copy01在390/768/1440实际点击两个保留入口并查看精简目录，定向人工评分每项≥3；不记15项完整人工接受。完整16自动03通过前15，但根把新文案检查放在换店后、导航前，误期待分类页而实际正确返回助手首页；整轮failed，历史保留。根已把检查移到原公共字典目录导航完成后，两店分别核对，不改产品换店清理规则或放宽断言，新的完整16复验待执行。

复验结果：automatic-business-20261001-04同次完整16/16通过、退出0，主档15项严格完成并与售前/采购共29项自动检查。复制前/镜像/复制后生产e25325fb…及脚本3b52615d…稳定，页面异常0。定向人工资料导航/文案结果仅绑定其同生产指纹和原脚本6935828c…；逐项完整人工仍pending，193正式业务不记通过。当前主档代码冻结e599184f…，后续物资交易必须从同轮原UI产生的主档ID继续，不能以零库存主档结果代替库存履约。

