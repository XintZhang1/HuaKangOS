# 193 项业务验收合同目录（源码审阅，不是执行报告）

日期：2026-10-01。源码基准：`5069b2b`；按当前工作树的原工作流、API、服务、模型和原生前端核对。仅维护本任务文件与 `tests/browser_click/business_acceptance_catalog.json`，未启动应用、浏览器或业务数据库，未修改生产、原需求清单、计划或执行脚本。

原 193 项需求、10 模块、111 条发布工作流身份与映射保留。目录按每项记录稳定 check_id、实际 UI 操作、已注册原 API 来源、原后端事实、角色/任务、前置与待验证条件。193 项源码合同已审阅；执行状态全部 `not_tested`、`business_accepted=false`。实际浏览器证据和逐 criteria 结果由外部 checkpoint 记录，目录不继承导航、空表单、旧成绩或单个共享动作。

自动场景 passed 只证明本次自动 UI/API/DB 断言。六类标准为显示正确、流程简单、文案简洁、后端匹配、硬 bug、原来源完整；人工体验/文案审阅仍须独立记录，manual_review pending 不可汇总业务已验收。建议检查和条件分支分别标为未测试，不把建议写成已执行。

原路由目录是有限来源绑定，不要求一个需求调用整个业务域全部路由。共享工作流的完整岗位步骤是来源参考；各需求只按自己的 ui_action 和 check_id 独立判断。动态 action/kind/group/dataset 明确使用本项合同，不能猜另一个接口。

只读需求和报表需非空原来源且 UI/API/只读 DB 一致；明细、图、CSV 使用同范围。查询不办理业务，导出追加审计记录仍沿原合同。报表保留实际业务日、批次/当前值、complete、未知成本 null 及原来源关系。写流程必须员工原页面显式点击，原单/Task/Event/资金/库存/会员/文件分别核对，不手造已付、已发、已退或终态夹具。

本轮代码与合成真实点击交付保持 PostgreSQL、真实模型、指定客户端、附件环境、员工试用和生产门槛独立；缺对应条件不写 done/released。

优先路径与最小前置：

- HK001–007各自独立：创建、分派、意向、转交、两次历史跟进、接待提醒、意向提醒。未选员工候选文本不成为有效 employee ID；同名消歧未执行不得继承主路径 passed。
- HK008–017分别核报价版本/独立批准、实际合同签回与 VIN/款/PDI/出库/提车、原路退款、加装、保险、代办和其他收入；当前基础动作存在不表示完整链通过。
- 下一整车路径 HK171/177/178/026/021/018/029：供应商实际维护、品牌车系车型分类、vehicles仓+库位、真实计划核价/请款、逐VIN发运/实际接收入库、目录组合筛选与库存查询。29已有占用来源才核占用条件；没有来源不为查询强建销售交易，也不称该分支通过。26按实际原采购需要逐行，不为形式凑行。
- 维修前置为原有效客户车辆/VIN/里程、作业/配件/工位/预设、可用材料与库位；预约、到店、施工、质量、承担、资金、接车是独立事实。理赔核准不是到账；mixed套餐 proposed 详情只读样例不是购买发行。
- 物资新建零库存 Item、materials仓/库位后先 Warehouse activate 对平源量/位置，由主管批准 Enrollment，再 other_in 来源凭据核价/实际 execute 可建立可靠原成本库存。旧 demo 必须原期初+收发账对平；不能直接改 Item 余额。
- 报表先由真实前序业务形成原事实，查询和导出不能替代发行/退款/履约。HK168是 benefit_points、membership_points、membership_points_debts，储值 member_entries不代替积分；当前月结定义22，历史1..21冻结，现金定义7保持。
- 字典/typed masters共页但各组独立；178整车仓与184物资仓、181品牌与182分类、188会员价格规则与实际会员等级不同。系统用户必须真实店岗位、密码/会话/审计和跨店逐件授权，不能新建一个账户概括全部系统需求。

已发现的源码条件与边界：

- 基本原路由/工作流已绑定，静态审阅不能排除运行硬 bug，也不能把字段/模型文件存在当业务完成。
- 当前 typed VehicleModel 标签并不自动形成品牌/车系 ModelClassification；按177原入口补明确分类，作为18参数筛选前置。
- 仓储非 activate 作业强制已 Enrollment；原单收发须本次精确库位分配。盘盈/亏不能在缺可靠原成本或预占不足时猜写。
- 旧 R4 group 本金退款、采购/调拨/repair/retail保留部分 admin 自批例外，新 Claims/套餐/组合则明确独立。该差别登记待核，不因目录审计擅改原业务规则；正常验收使用不同经办/主管身份。
- 参数页只读部署配置导航，个人密码实际变更另原 auth/password；没有原写合同不声称能改部署阈值或头像。

| 模块 | 原需求数 |
| --- | ---: |
| 整车销售模块 | 17 |
| 整车仓库模块 | 13 |
| 维修管理模块 | 14 |
| 物资管理模块 | 30 |
| 财务管理模块 | 23 |
| 客户管理模块 | 19 |
| 会员服务模块 | 17 |
| 统计分析模块 | 36 |
| 基础数据模块 | 19 |
| 系统管理模块 | 5 |

逐项执行入口索引（具体动作/API/原事实与条件见 JSON；以下不记录通过）：

| 需求 | 名称 | 合同类型 | 稳定 check_id |
| --- | --- | --- | --- |
| HK-001 | 展厅接待 | write | HK-001-create |
| HK-002 | 展厅接待分派 | write | HK-002-assign |
| HK-003 | 意向客户管理 | write | HK-003-intent |
| HK-004 | 意向单分派 | write | HK-004-reassign |
| HK-005 | 意向单跟进记录 | write | HK-005-history |
| HK-006 | 展厅接待提醒 | write | HK-006-reminder |
| HK-007 | 意向客户提醒 | write | HK-007-reminder |
| HK-008 | 车辆预订单 | write | HK-008-business |
| HK-009 | 车辆销售单 | workflow | HK-009-business |
| HK-010 | 销售订单退订单 | workflow | HK-010-business |
| HK-011 | 客户提车单 | workflow | HK-011-business |
| HK-012 | 精品加装单 | workflow | HK-012-business |
| HK-013 | 车辆保险单 | workflow | HK-013-business |
| HK-014 | 保险核价单 | write | HK-014-business |
| HK-015 | 代办服务单 | workflow | HK-015-business |
| HK-016 | 代办核价单 | write | HK-016-business |
| HK-017 | 整车其它收入单 | workflow | HK-017-business |
| HK-018 | 所有车辆品牌型号筛参数选展示专题页 | read | HK-018-business |
| HK-019 | 车辆请款导入 | workflow | HK-019-business |
| HK-020 | 车辆调拨入库 | write | HK-020-business |
| HK-021 | 车辆采购入库 | write | HK-021-business |
| HK-022 | 车辆销售出库 | write | HK-022-business |
| HK-023 | 车辆采购退回 | write | HK-023-business |
| HK-024 | 车辆调拨出库 | write | HK-024-business |
| HK-025 | 车辆其他出库 | write | HK-025-business |
| HK-026 | 采购计划管理 | write | HK-026-business |
| HK-027 | 请款导入车辆发货 | workflow | HK-027-business |
| HK-028 | 请款导入车辆到货 | workflow | HK-028-business |
| HK-029 | 车辆库存查询 | read | HK-029-business |
| HK-030 | 车辆店内移库 | write | HK-030-business |
| HK-031 | 维修预约 | workflow | HK-031-business |
| HK-032 | 洗车开单 | workflow | HK-032-business |
| HK-033 | 快捷开单 | workflow | HK-033-business |
| HK-034 | 一般维修 | write | HK-034-business |
| HK-035 | 保险理赔维修 | write | HK-035-business |
| HK-036 | 厂家索赔维修 | write | HK-036-business |
| HK-037 | 新车检测(PDI) | write | HK-037-business |
| HK-038 | 返修单 | workflow | HK-038-business |
| HK-039 | 保险账核价单 | write | HK-039-business |
| HK-040 | 索赔账核价单 | write | HK-040-business |
| HK-041 | 内部账核价单 | write | HK-041-business |
| HK-042 | 客户报销结算 | write | HK-042-business |
| HK-043 | 维修套餐设置 | workflow | HK-043-business |
| HK-044 | 维修工单提醒 | read | HK-044-business |
| HK-045 | 物资采购入库 | write | HK-045-business |
| HK-046 | 物资其它入库 | write | HK-046-business |
| HK-047 | 物资调拨入库 | write | HK-047-business |
| HK-048 | 耗材领用退回 | write | HK-048-business |
| HK-049 | 维修退料入库 | write | HK-049-business |
| HK-050 | 礼品退货入库 | write | HK-050-business |
| HK-051 | 物资盘盈入库查询 | read | HK-051-business |
| HK-052 | 精品采购入库 | write | HK-052-business |
| HK-053 | 维修领料出库 | write | HK-053-business |
| HK-054 | 物资采购入库退货 | write | HK-054-business |
| HK-055 | 物资调拨出库 | write | HK-055-business |
| HK-056 | 耗材领用出库 | write | HK-056-business |
| HK-057 | 其它入库退货 | write | HK-057-business |
| HK-058 | 精品采购入库退货 | write | HK-058-business |
| HK-059 | 礼品出库 | write | HK-059-business |
| HK-060 | 物资其他出库 | write | HK-060-business |
| HK-061 | 盘亏出库查询 | read | HK-061-business |
| HK-062 | 精品销售单 | write | HK-062-business |
| HK-063 | 维修精品销售单 | write | HK-063-business |
| HK-064 | 精品销售出库 | write | HK-064-business |
| HK-065 | 精品加装出库 | write | HK-065-business |
| HK-066 | 维修精品销售出库 | write | HK-066-business |
| HK-067 | 精品销售退货 | write | HK-067-business |
| HK-068 | 精品销售套餐设置 | workflow | HK-068-business |
| HK-069 | 物资采购订货 | write | HK-069-business |
| HK-070 | 物资库存查询 | read | HK-070-business |
| HK-071 | 机构库存查询 | read | HK-071-business |
| HK-072 | 物资店内移库 | write | HK-072-business |
| HK-073 | 物资库存盘点 | workflow | HK-073-business |
| HK-074 | 精品采购订货 | write | HK-074-business |
| HK-075 | 车辆销售收款 | write | HK-075-business |
| HK-076 | 代办服务收款 | write | HK-076-business |
| HK-077 | 保险服务收款 | write | HK-077-business |
| HK-078 | 整车收款单调整 | write | HK-078-business |
| HK-079 | 维修收款 | write | HK-079-business |
| HK-080 | 洗车收款 | write | HK-080-business |
| HK-081 | 维修收款单调整 | write | HK-081-business |
| HK-082 | 精品销售收款 | write | HK-082-business |
| HK-083 | 采购入库退货收款 | write | HK-083-business |
| HK-084 | 调拨出库收款 | write | HK-084-business |
| HK-085 | 其他入库退货收款 | write | HK-085-business |
| HK-086 | 物资收款单调整 | write | HK-086-business |
| HK-087 | 财务预收款 | write | HK-087-business |
| HK-088 | 其它收入单收款 | write | HK-088-business |
| HK-089 | 会员储值卡充值收款 | write | HK-089-business |
| HK-090 | 其他收款单调整 | write | HK-090-business |
| HK-091 | 客户应收款查询 | read | HK-091-business |
| HK-092 | 收款单退款申请 | write | HK-092-business |
| HK-093 | 预收款退款 | write | HK-093-business |
| HK-094 | 会员储值卡退款 | write | HK-094-business |
| HK-095 | 月结查询 | workflow | HK-095-business |
| HK-096 | 客户月结处理 | workflow | HK-096-business |
| HK-097 | 开发票 | workflow | HK-097-business |
| HK-098 | 客户档案 | write | HK-098-business |
| HK-099 | 车辆档案 | write | HK-099-business |
| HK-100 | 其它收入单 | write | HK-100-business |
| HK-101 | 问卷设置 | workflow | HK-101-business |
| HK-102 | 车辆销售回访 | write | HK-102-business |
| HK-103 | 意向客户回访 | write | HK-103-business |
| HK-104 | 维修工单回访 | write | HK-104-business |
| HK-105 | 保养提醒 | workflow | HK-105-business |
| HK-106 | 保修提醒 | workflow | HK-106-business |
| HK-107 | 客户咨询 | write | HK-107-business |
| HK-108 | 客户投诉 | write | HK-108-business |
| HK-109 | 客户救援 | write | HK-109-business |
| HK-110 | 客户回访查询 | read | HK-110-business |
| HK-111 | 跟进记录查询 | read | HK-111-business |
| HK-112 | 首保提醒回访 | workflow | HK-112-business |
| HK-113 | 续保信息提取 | workflow | HK-113-business |
| HK-114 | 续保信息分派 | workflow | HK-114-business |
| HK-115 | 续保分派回访 | workflow | HK-115-business |
| HK-116 | 保险到期提醒 | workflow | HK-116-business |
| HK-117 | 会员信息管理 | workflow | HK-117-business |
| HK-118 | 会员换补卡 | workflow | HK-118-business |
| HK-119 | 会员积分兑换 | write | HK-119-business |
| HK-120 | 会员积分调整 | write | HK-120-business |
| HK-121 | 会员级别调整 | workflow | HK-121-business |
| HK-122 | 会员续会 | workflow | HK-122-business |
| HK-123 | 会员卡充值套餐设置 | workflow | HK-123-business |
| HK-124 | 会员储值卡充值 | workflow | HK-124-business |
| HK-125 | 会员储值卡退款请求 | workflow | HK-125-business |
| HK-126 | 会员套餐购买 | workflow | HK-126-business |
| HK-127 | 会员套餐退款 | workflow | HK-127-business |
| HK-128 | 会员卡生成 | workflow | HK-128-business |
| HK-129 | 消费券类型 | write | HK-129-business |
| HK-130 | 消费券生成 | write | HK-130-business |
| HK-131 | 消费券赠送 | write | HK-131-business |
| HK-132 | 消费券信息查询 | read | HK-132-business |
| HK-133 | 套餐卡类型 | workflow | HK-133-business |
| HK-134 | 展厅接待分析 | report | HK-134-business |
| HK-135 | 意向客户分析 | report | HK-135-business |
| HK-136 | 售前跟进分析 | report | HK-136-business |
| HK-137 | 销售订单统计 | report | HK-137-business |
| HK-138 | 销售单统计 | report | HK-138-business |
| HK-139 | 加装单分析 | report | HK-139-business |
| HK-140 | 代办单分析 | report | HK-140-business |
| HK-141 | 保险单分析 | report | HK-141-business |
| HK-142 | 整车销售毛利统计 | report | HK-142-business |
| HK-143 | 整车入库历史统计 | report | HK-143-business |
| HK-144 | 整车出库历史统计 | report | HK-144-business |
| HK-145 | 整车仓库入出存统计 | report | HK-145-business |
| HK-146 | 维修预约分析 | report | HK-146-business |
| HK-147 | 维修工单分析 | report | HK-147-business |
| HK-148 | 维修项目分析 | report | HK-148-business |
| HK-149 | 维修领料分析 | report | HK-149-business |
| HK-150 | 物资入库历史统计 | report | HK-150-business |
| HK-151 | 物资出库历史统计 | report | HK-151-business |
| HK-152 | 物资仓库入出存统计 | report | HK-152-business |
| HK-153 | 物资采购订货统计 | report | HK-153-business |
| HK-154 | 精品销售统计 | report | HK-154-business |
| HK-155 | 物资移库明细统计 | report | HK-155-business |
| HK-156 | 精品销售施工统计 | report | HK-156-business |
| HK-157 | 物资应收账统计 | report | HK-157-business |
| HK-158 | 整车相关应收账统计 | report | HK-158-business |
| HK-159 | 维修应收账统计 | report | HK-159-business |
| HK-160 | 收款统计 | report | HK-160-business |
| HK-161 | 物资收入成本对照表 | report | HK-161-business |
| HK-162 | 预收款统计 | report | HK-162-business |
| HK-163 | 财务结算统计 | report | HK-163-business |
| HK-164 | 客户车辆统计 | report | HK-164-business |
| HK-165 | 客户回访统计 | report | HK-165-business |
| HK-166 | 进出厂统计 | report | HK-166-business |
| HK-167 | 客户价值分析统计 | report | HK-167-business |
| HK-168 | 会员积分统计 | report | HK-168-business |
| HK-169 | 消费券统计 | report | HK-169-business |
| HK-170 | 公共字典 | write | HK-170-business |
| HK-171 | 供应商设置 | write | HK-171-business |
| HK-172 | 保险公司 | write | HK-172-business |
| HK-173 | 维修字典 | write | HK-173-business |
| HK-174 | 车间班组 | write | HK-174-business |
| HK-175 | 作业项目 | write | HK-175-business |
| HK-176 | 整车字典 | write | HK-176-business |
| HK-177 | 品牌车系车型 | write | HK-177-business |
| HK-178 | 整车仓库 | write | HK-178-business |
| HK-179 | 代办项目 | write | HK-179-business |
| HK-180 | 物资字典 | write | HK-180-business |
| HK-181 | 物资品牌 | write | HK-181-business |
| HK-182 | 物资分类 | write | HK-182-business |
| HK-183 | 物资目录 | write | HK-183-business |
| HK-184 | 物资仓库 | write | HK-184-business |
| HK-185 | 财务字典 | write | HK-185-business |
| HK-186 | 客户字典 | write | HK-186-business |
| HK-187 | 会员字典 | write | HK-187-business |
| HK-188 | 会员级别 | workflow | HK-188-business |
| HK-189 | 机构管理 | write | HK-189-business |
| HK-190 | 角色管理 | workflow | HK-190-business |
| HK-191 | 员工管理 | workflow | HK-191-business |
| HK-192 | 参数设置密码修改 | workflow | HK-192-business |
| HK-193 | 系统日志 | read | HK-193-business |

静态核对需在最后写入边界验证：193唯一身份与原 manifest一致、111工作流来源、193唯一check、全部not_tested/false、所有源路径存在、实际API绑定、当前文件SHA256。该检查不导入app，不等于业务验收。
