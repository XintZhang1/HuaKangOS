"""Static business adapters, registered explicitly by the Runtime object layer.

No discovery, plugin imports, background work or database access occurs here.
"""

from .flow_case import FLOW_ACTION, FLOW_CREATE, FLOW_READ, FlowCaseAdapter
from .lead import LEAD_ACTIONS, LEAD_FACTS, LEAD_KIND, LeadAdapter
from .sales_order import (SALES_CREATE, SALES_FACTS, SALES_KIND, SALES_PROPOSE,
                          SALES_READ, SALES_VEHICLES, SalesOrderAdapter)
from .aftercare import (AFTERCARE_ACTION, AFTERCARE_CREATE, AFTERCARE_FACTS,
                        AFTERCARE_FLOW_VERSION, AFTERCARE_KIND, AFTERCARE_READ,
                        AFTERCARE_SCENARIOS, AftercareAdapter)
from .vehicle_purchase import (PURCHASE_ACTION, PURCHASE_ACTIONS, PURCHASE_CREATE,
                              PURCHASE_FACTS, PURCHASE_FLOW_VERSION, PURCHASE_KIND,
                              PURCHASE_READ, VehiclePurchaseAdapter)
from .vehicle_operation import (OPERATION_ACTION, OPERATION_ACTIONS, OPERATION_CREATE,
                               OPERATION_FACTS, OPERATION_FLOW_VERSION, OPERATION_KIND,
                               OPERATION_KINDS, OPERATION_READ, VehicleOperationAdapter)
from .vehicle_import_batch import (IMPORT_ACTION, IMPORT_ACTIONS, IMPORT_FACTS,
                                  IMPORT_OBJECT_TYPE, VehicleImportBatchAdapter)
from .service_intake import (APPOINTMENT_OBJECT_TYPE, INTAKE_ACTION, INTAKE_ACTIONS,
                            INTAKE_CREATE, INTAKE_FACTS, INTAKE_READ, ServiceIntakeAdapter)
from .repair_order import (REPAIR_ACTION, REPAIR_ACTIONS, REPAIR_CREATE, REPAIR_FACTS,
                          REPAIR_READ, RepairOrderAdapter)
from .rework_grant import (GRANT_ACTION, GRANT_ACTIONS, GRANT_CREATE, GRANT_FACTS,
                          GRANT_OBJECT_TYPE, GRANT_QUOTE, GRANT_READ, GRANT_REQUEST,
                          ReworkGrantAdapter)
from .claim_order import (CLAIM_ACTION, CLAIM_ACTIONS, CLAIM_CREATE, CLAIM_FACTS,
                         CLAIM_OPTIONS, CLAIM_READ, ClaimOrderAdapter)
from .gate_visit import (GATE_ACTION, GATE_ACTIONS, GATE_CORRECTION,
                        GATE_CORRECTION_ACTION, GATE_CREATE, GATE_DEPARTURE, GATE_FACTS,
                        GATE_OBJECT_TYPE, GATE_READ, GateVisitAdapter)
from .retail_order import (RETAIL_ACTION, RETAIL_ACTIONS, RETAIL_CREATE, RETAIL_FACTS,
                          RETAIL_READ, RetailOrderAdapter)
from .retail_bundle import (BUNDLE_FACTS, BUNDLE_PREVIEW, BUNDLE_RULE_CREATE,
                           BUNDLE_RULES, BUNDLE_SALE_CREATE, RULE_OBJECT_TYPE,
                           SALE_OBJECT_TYPE, RetailBundleAdapter)
from .retail_group_payment import (GROUP_ACTION, GROUP_ACTIONS, GROUP_CATALOG,
                                  GROUP_FACTS, GROUP_READ, RetailGroupPaymentAdapter)
from .material_procurement import (PROC_ACTION, PROC_ACTIONS, PROC_CREATE,
                                  PROC_FACTS, PROC_READ, MaterialProcurementAdapter)
from .procurement_prepayment import (PREPAY_ACTION, PREPAY_ACTIONS, PREPAY_FACTS,
                                    PREPAY_READ, ProcurementPrepaymentAdapter)
from .warehouse_document import (WH_COMMAND, WH_CREATE, WH_FACTS, WH_OPERATIONS,
                                WH_READ, WarehouseDocumentAdapter)
from .customer_vehicle import (VEHICLE_CREATE, VEHICLE_FACTS, VEHICLE_HISTORY,
                               VEHICLE_HISTORY_LINK, VEHICLE_OBJECT_TYPE, VEHICLE_OBSERVATION,
                               VEHICLE_READ, CustomerVehicleAdapter)
from .customer_care import (CARE_ACTION, CARE_ACTIONS, CARE_CREATE, CARE_FACTS,
                            CARE_OBJECT_TYPE, CARE_READ, CARE_SUBTYPES, CustomerCareAdapter)
from .care_reminder import (REMINDER_FACTS, REMINDER_GENERATE, REMINDER_KINDS,
                            REMINDER_OBJECT_TYPE, REMINDER_RULE_SAVE, REMINDER_RULES,
                            CareReminderAdapter)
from .membership_order import (MEMBERSHIP_ACTION, MEMBERSHIP_ACTIONS, MEMBERSHIP_CREATE,
                               MEMBERSHIP_FACTS, MEMBERSHIP_PURPOSES, MEMBERSHIP_READ,
                               MembershipOrderAdapter)
from .group_principal import (MEMBER_ACTION, MEMBER_COMMANDS, MEMBER_FACTS,
                              MEMBER_OBJECT_TYPE, MEMBER_READ, GroupPrincipalAdapter)
from .group_benefit import (BENEFIT_ACTION, BENEFIT_FACTS, BENEFIT_KINDS,
                            BENEFIT_MEMBERS, BENEFIT_OBJECT_TYPE, BENEFIT_RULES,
                            GroupBenefitAdapter)
from .recharge_bundle import (RECHARGE_ACTION, RECHARGE_ACTIONS, RECHARGE_CREATE,
                              RECHARGE_FACTS, RECHARGE_PURCHASES, RECHARGE_PURPOSES,
                              RECHARGE_READ, RechargeBundleAdapter)
from .repair_package import (PACKAGE_ACTION, PACKAGE_ACTIONS, PACKAGE_CREATE,
                             PACKAGE_FACTS, PACKAGE_MEMBER_PURCHASES, PACKAGE_OBJECT_TYPE,
                             PACKAGE_ORDER_CAPTURE, PACKAGE_ORDER_QUOTE,
                             PACKAGE_REFUND_ACTION, PACKAGE_RULES, RepairPackageAdapter)
from .member_price import (PRICE_ACTION, PRICE_ACTIONS, PRICE_CANDIDATES, PRICE_CREATE,
                           PRICE_FACTS, PRICE_OBJECT_TYPE, PRICE_READ, MemberPriceAdapter)
from .business_finance_order import (FINANCE_ACTION, FINANCE_ADVANCES, FINANCE_CREATE,
                                    FINANCE_FACTS, FINANCE_READ, FINANCE_RECEIPTS,
                                    FINANCE_SOURCES, BusinessFinanceOrderAdapter)

__all__ = ['FLOW_ACTION', 'FLOW_CREATE', 'FLOW_READ', 'FlowCaseAdapter',
           'LEAD_ACTIONS', 'LEAD_FACTS', 'LEAD_KIND', 'LeadAdapter',
           'SALES_CREATE', 'SALES_FACTS', 'SALES_KIND', 'SALES_PROPOSE', 'SALES_READ',
           'SALES_VEHICLES', 'SalesOrderAdapter',
           'AFTERCARE_ACTION', 'AFTERCARE_CREATE', 'AFTERCARE_FACTS', 'AFTERCARE_FLOW_VERSION',
           'AFTERCARE_KIND', 'AFTERCARE_READ', 'AFTERCARE_SCENARIOS', 'AftercareAdapter',
           'PURCHASE_ACTION', 'PURCHASE_ACTIONS', 'PURCHASE_CREATE', 'PURCHASE_FACTS',
           'PURCHASE_FLOW_VERSION', 'PURCHASE_KIND', 'PURCHASE_READ', 'VehiclePurchaseAdapter',
           'OPERATION_ACTION', 'OPERATION_ACTIONS', 'OPERATION_CREATE', 'OPERATION_FACTS',
           'OPERATION_FLOW_VERSION', 'OPERATION_KIND', 'OPERATION_KINDS', 'OPERATION_READ',
           'VehicleOperationAdapter',
           'IMPORT_ACTION', 'IMPORT_ACTIONS', 'IMPORT_FACTS', 'IMPORT_OBJECT_TYPE',
           'VehicleImportBatchAdapter',
           'APPOINTMENT_OBJECT_TYPE', 'INTAKE_ACTION', 'INTAKE_ACTIONS', 'INTAKE_CREATE',
           'INTAKE_FACTS', 'INTAKE_READ', 'ServiceIntakeAdapter',
           'REPAIR_ACTION', 'REPAIR_ACTIONS', 'REPAIR_CREATE', 'REPAIR_FACTS', 'REPAIR_READ',
           'RepairOrderAdapter',
           'GRANT_ACTION', 'GRANT_ACTIONS', 'GRANT_CREATE', 'GRANT_FACTS', 'GRANT_OBJECT_TYPE',
           'GRANT_QUOTE', 'GRANT_READ', 'GRANT_REQUEST', 'ReworkGrantAdapter',
           'CLAIM_ACTION', 'CLAIM_ACTIONS', 'CLAIM_CREATE', 'CLAIM_FACTS', 'CLAIM_OPTIONS',
           'CLAIM_READ', 'ClaimOrderAdapter',
           'GATE_ACTION', 'GATE_ACTIONS', 'GATE_CORRECTION', 'GATE_CORRECTION_ACTION',
           'GATE_CREATE', 'GATE_DEPARTURE', 'GATE_FACTS', 'GATE_OBJECT_TYPE', 'GATE_READ',
           'GateVisitAdapter',
           'RETAIL_ACTION', 'RETAIL_ACTIONS', 'RETAIL_CREATE', 'RETAIL_FACTS', 'RETAIL_READ',
           'RetailOrderAdapter',
           'BUNDLE_FACTS', 'BUNDLE_PREVIEW', 'BUNDLE_RULE_CREATE', 'BUNDLE_RULES',
           'BUNDLE_SALE_CREATE', 'RULE_OBJECT_TYPE', 'SALE_OBJECT_TYPE', 'RetailBundleAdapter',
           'GROUP_ACTION', 'GROUP_ACTIONS', 'GROUP_CATALOG', 'GROUP_FACTS', 'GROUP_READ',
           'RetailGroupPaymentAdapter',
           'PROC_ACTION', 'PROC_ACTIONS', 'PROC_CREATE', 'PROC_FACTS', 'PROC_READ',
           'MaterialProcurementAdapter',
           'PREPAY_ACTION', 'PREPAY_ACTIONS', 'PREPAY_FACTS', 'PREPAY_READ',
           'ProcurementPrepaymentAdapter',
           'WH_COMMAND', 'WH_CREATE', 'WH_FACTS', 'WH_OPERATIONS', 'WH_READ',
           'WarehouseDocumentAdapter',
           'VEHICLE_CREATE', 'VEHICLE_FACTS', 'VEHICLE_HISTORY', 'VEHICLE_HISTORY_LINK',
           'VEHICLE_OBJECT_TYPE', 'VEHICLE_OBSERVATION', 'VEHICLE_READ',
           'CustomerVehicleAdapter',
           'CARE_ACTION', 'CARE_ACTIONS', 'CARE_CREATE', 'CARE_FACTS', 'CARE_OBJECT_TYPE',
           'CARE_READ', 'CARE_SUBTYPES', 'CustomerCareAdapter',
           'REMINDER_FACTS', 'REMINDER_GENERATE', 'REMINDER_KINDS', 'REMINDER_OBJECT_TYPE',
           'REMINDER_RULE_SAVE', 'REMINDER_RULES', 'CareReminderAdapter',
           'MEMBERSHIP_ACTION', 'MEMBERSHIP_ACTIONS', 'MEMBERSHIP_CREATE', 'MEMBERSHIP_FACTS',
           'MEMBERSHIP_PURPOSES', 'MEMBERSHIP_READ', 'MembershipOrderAdapter',
           'MEMBER_ACTION', 'MEMBER_COMMANDS', 'MEMBER_FACTS', 'MEMBER_OBJECT_TYPE',
           'MEMBER_READ', 'GroupPrincipalAdapter',
           'BENEFIT_ACTION', 'BENEFIT_FACTS', 'BENEFIT_KINDS', 'BENEFIT_MEMBERS',
           'BENEFIT_OBJECT_TYPE', 'BENEFIT_RULES', 'GroupBenefitAdapter',
           'RECHARGE_ACTION', 'RECHARGE_ACTIONS', 'RECHARGE_CREATE', 'RECHARGE_FACTS',
           'RECHARGE_PURCHASES', 'RECHARGE_PURPOSES', 'RECHARGE_READ', 'RechargeBundleAdapter',
           'PACKAGE_ACTION', 'PACKAGE_ACTIONS', 'PACKAGE_CREATE', 'PACKAGE_FACTS',
           'PACKAGE_MEMBER_PURCHASES', 'PACKAGE_OBJECT_TYPE', 'PACKAGE_ORDER_CAPTURE',
           'PACKAGE_ORDER_QUOTE', 'PACKAGE_REFUND_ACTION', 'PACKAGE_RULES', 'RepairPackageAdapter',
           'PRICE_ACTION', 'PRICE_ACTIONS', 'PRICE_CANDIDATES', 'PRICE_CREATE', 'PRICE_FACTS',
           'PRICE_OBJECT_TYPE', 'PRICE_READ', 'MemberPriceAdapter',
           'FINANCE_ACTION', 'FINANCE_ADVANCES', 'FINANCE_CREATE', 'FINANCE_FACTS',
           'FINANCE_READ', 'FINANCE_RECEIPTS', 'FINANCE_SOURCES', 'BusinessFinanceOrderAdapter']


def register_adapters(registry):
    """One static registration point for the reviewed domain milestones.

    There is no discovery/import path supplied by an employee or a model.
    Each later adapter adds its explicit provider here before the registry seals.
    """
    from ..assistant_runtime_registry import DomainAdapterSpec
    registry.register(DomainAdapterSpec(
        name='flow_case', factory=FlowCaseAdapter, object_types=('case',),
        operation_ids=(FLOW_READ, FLOW_CREATE, FLOW_ACTION),
        fallback_object_types=('case',),
    ))
    # M7.8.1：预收与结算（business_finance_order）静态注册；key 一律取原 Case.id。
    registry.register(DomainAdapterSpec(
        name='business_finance_order', factory=BusinessFinanceOrderAdapter, object_types=('case',),
        operation_ids=(FINANCE_READ, FINANCE_CREATE, FINANCE_ACTION),
        fact_keys=FINANCE_FACTS,
        fallback_object_types=(),
    ))
    # M7.7.6：会员价格规则（member_price）静态注册；key 即原 MemberPricingRule.id。
    registry.register(DomainAdapterSpec(
        name='member_price', factory=MemberPriceAdapter,
        object_types=(PRICE_OBJECT_TYPE,),
        operation_ids=(PRICE_READ, PRICE_CANDIDATES, PRICE_CREATE, PRICE_ACTION),
        fact_keys=PRICE_FACTS,
        fallback_object_types=(),
    ))
    # M7.7.5：维修套餐（repair_package）静态注册。
    # 已评审读取按会员维度（members/{key}/purchases），与 package_purchase 维度不一致：
    # 适配器只登记已评审 operation，不编造 purchase→member 映射，事实按合同返回未知。
    registry.register(DomainAdapterSpec(
        name='repair_package', factory=RepairPackageAdapter,
        object_types=(PACKAGE_OBJECT_TYPE,),
        operation_ids=(PACKAGE_MEMBER_PURCHASES, PACKAGE_RULES, PACKAGE_CREATE, PACKAGE_ORDER_CAPTURE,
                       PACKAGE_ORDER_QUOTE, PACKAGE_ACTION, PACKAGE_REFUND_ACTION),
        fact_keys=PACKAGE_FACTS,
        fallback_object_types=(),
    ))
    # M7.7.4：组合退回与履约（recharge_bundle）静态注册；key 一律取原 Case.id。
    registry.register(DomainAdapterSpec(
        name='recharge_bundle', factory=RechargeBundleAdapter, object_types=('case',),
        operation_ids=(RECHARGE_READ, RECHARGE_CREATE, RECHARGE_ACTION),
        fact_keys=RECHARGE_FACTS,
        fallback_object_types=(),
    ))
    # M7.7.3：集团权益（group_benefit）静态注册。
    # 权益读取按客户维度（必填 customer_id），与登记的 member 维度不一致：
    # 适配器只登记已评审 operation，不编造 member→customer 映射，事实按合同返回未知。
    registry.register(DomainAdapterSpec(
        name='group_benefit', factory=GroupBenefitAdapter,
        object_types=(BENEFIT_OBJECT_TYPE,),
        operation_ids=(BENEFIT_MEMBERS, BENEFIT_RULES, BENEFIT_ACTION),
        fact_keys=BENEFIT_FACTS,
        fallback_object_types=(),
    ))
    # M7.7.2：集团本金与权益（group_principal）静态注册。
    registry.register(DomainAdapterSpec(
        name='group_principal', factory=GroupPrincipalAdapter,
        object_types=(MEMBER_OBJECT_TYPE,),
        operation_ids=(MEMBER_READ, MEMBER_ACTION),
        fact_keys=MEMBER_FACTS,
        fallback_object_types=(),
    ))
    # M7.7.1：会员业务单（membership_order）静态注册；key 一律取原 Case.id。
    registry.register(DomainAdapterSpec(
        name='membership_order', factory=MembershipOrderAdapter, object_types=('case',),
        operation_ids=(MEMBERSHIP_READ, MEMBERSHIP_CREATE, MEMBERSHIP_ACTION),
        fact_keys=MEMBERSHIP_FACTS,
        fallback_object_types=(),
    ))
    # M7.6.3：客户提醒来源（care_reminder）静态注册。
    registry.register(DomainAdapterSpec(
        name='care_reminder', factory=CareReminderAdapter,
        object_types=(REMINDER_OBJECT_TYPE,),
        operation_ids=(REMINDER_RULES, REMINDER_RULE_SAVE, REMINDER_GENERATE),
        fact_keys=REMINDER_FACTS,
        fallback_object_types=(),
    ))
    # M7.6.2：客户关怀服务单（customer_care）静态注册。
    registry.register(DomainAdapterSpec(
        name='customer_care', factory=CustomerCareAdapter,
        object_types=(CARE_OBJECT_TYPE,),
        operation_ids=(CARE_READ, CARE_CREATE, CARE_ACTION),
        fact_keys=CARE_FACTS,
        fallback_object_types=(),
    ))
    # M7.6.1：客户档案与服务单（customer_vehicle）静态注册。
    registry.register(DomainAdapterSpec(
        name='customer_vehicle', factory=CustomerVehicleAdapter,
        object_types=(VEHICLE_OBJECT_TYPE,),
        operation_ids=(VEHICLE_READ, VEHICLE_HISTORY, VEHICLE_CREATE, VEHICLE_OBSERVATION,
                       VEHICLE_HISTORY_LINK),
        fact_keys=VEHICLE_FACTS,
        fallback_object_types=(),
    ))
    # M7.5.3：仓储单据（warehouse_document）静态注册。
    registry.register(DomainAdapterSpec(
        name='warehouse_document', factory=WarehouseDocumentAdapter, object_types=('case',),
        operation_ids=(WH_READ, WH_CREATE, WH_COMMAND),
        fact_keys=WH_FACTS,
        fallback_object_types=(),
    ))
    # M7.5.2：物资采购预付（procurement_prepayment）静态注册。
    registry.register(DomainAdapterSpec(
        name='procurement_prepayment', factory=ProcurementPrepaymentAdapter, object_types=('case',),
        operation_ids=(PREPAY_READ, PREPAY_ACTION),
        fact_keys=PREPAY_FACTS,
        fallback_object_types=(),
    ))
    # M7.5.1：物资采购、预付与仓储（material_procurement）静态注册。
    registry.register(DomainAdapterSpec(
        name='material_procurement', factory=MaterialProcurementAdapter, object_types=('case',),
        operation_ids=(PROC_READ, PROC_CREATE, PROC_ACTION),
        fact_keys=PROC_FACTS,
        fallback_object_types=(),
    ))
    # M7.4.3：零售集团与门店规则（retail_group_payment）静态注册。
    registry.register(DomainAdapterSpec(
        name='retail_group_payment', factory=RetailGroupPaymentAdapter, object_types=('case',),
        operation_ids=(GROUP_READ, GROUP_CATALOG, GROUP_ACTION),
        fact_keys=GROUP_FACTS,
        fallback_object_types=(),
    ))
    # M7.4.2：精品套餐核销与安装（retail_bundle）静态注册。
    # 规则对象走预览 GET；销售对象只经 POST 结果绑定（无已评审/已发现的详情读取路径）。
    registry.register(DomainAdapterSpec(
        name='retail_bundle', factory=RetailBundleAdapter,
        object_types=(RULE_OBJECT_TYPE, SALE_OBJECT_TYPE),
        operation_ids=(BUNDLE_RULES, BUNDLE_PREVIEW, BUNDLE_RULE_CREATE, BUNDLE_SALE_CREATE),
        fact_keys=BUNDLE_FACTS,
        fallback_object_types=(),
    ))
    # M7.4.1：精品销售与套餐（retail_order）静态注册。
    registry.register(DomainAdapterSpec(
        name='retail_order', factory=RetailOrderAdapter, object_types=('case',),
        operation_ids=(RETAIL_READ, RETAIL_CREATE, RETAIL_ACTION),
        fact_keys=RETAIL_FACTS,
        fallback_object_types=(),
    ))
    # M7.3.5：维修出厂与真实进出厂时间（gate_visit）静态注册。
    registry.register(DomainAdapterSpec(
        name='gate_visit', factory=GateVisitAdapter,
        object_types=(GATE_OBJECT_TYPE,),
        operation_ids=(GATE_READ, GATE_CREATE, GATE_ACTION, GATE_CORRECTION,
                       GATE_CORRECTION_ACTION, GATE_DEPARTURE),
        fact_keys=GATE_FACTS,
        fallback_object_types=(),
    ))
    # M7.3.4：理赔核赔受理（claim_order）静态注册。
    registry.register(DomainAdapterSpec(
        name='claim_order', factory=ClaimOrderAdapter, object_types=('case',),
        operation_ids=(CLAIM_READ, CLAIM_OPTIONS, CLAIM_CREATE, CLAIM_ACTION),
        fact_keys=CLAIM_FACTS,
        fallback_object_types=(),
    ))
    # M7.3.3：维修领退料与返修（rework_grant）静态注册。
    registry.register(DomainAdapterSpec(
        name='rework_grant', factory=ReworkGrantAdapter,
        object_types=(GRANT_OBJECT_TYPE,),
        operation_ids=(GRANT_READ, GRANT_CREATE, GRANT_ACTION, GRANT_REQUEST, GRANT_QUOTE),
        fact_keys=GRANT_FACTS,
        fallback_object_types=(),
    ))
    # M7.3.2：维修工单接车与施工进度（repair_order）静态注册。
    registry.register(DomainAdapterSpec(
        name='repair_order', factory=RepairOrderAdapter, object_types=('case',),
        operation_ids=(REPAIR_READ, REPAIR_CREATE, REPAIR_ACTION),
        fact_keys=REPAIR_FACTS,
        fallback_object_types=(),
    ))
    # M7.3.1：维修预约与实际到店接待（service_intake）静态注册。
    registry.register(DomainAdapterSpec(
        name='service_intake', factory=ServiceIntakeAdapter,
        object_types=(APPOINTMENT_OBJECT_TYPE,),
        operation_ids=(INTAKE_READ, INTAKE_CREATE, INTAKE_ACTION),
        fact_keys=INTAKE_FACTS,
        fallback_object_types=(),
    ))
    # M7.2.3：整车批量导入批次（vehicle_import_batch）静态注册。
    # 只登记已评审的批次动作；原详情 GET 未在目录内，适配器按能力缺口明确拒绝。
    registry.register(DomainAdapterSpec(
        name='vehicle_import_batch', factory=VehicleImportBatchAdapter,
        object_types=(IMPORT_OBJECT_TYPE,),
        operation_ids=(IMPORT_ACTION,),
        fact_keys=IMPORT_FACTS,
        fallback_object_types=(),
    ))
    # M7.2.2：整车库位及出退库作业（vehicle_operation）静态注册。
    registry.register(DomainAdapterSpec(
        name='vehicle_operation', factory=VehicleOperationAdapter, object_types=('case',),
        operation_ids=(OPERATION_READ, OPERATION_CREATE, OPERATION_ACTION),
        kind_versions=(('case', OPERATION_KIND, OPERATION_FLOW_VERSION),),
        fact_kind_versions=(('case', OPERATION_KIND, OPERATION_FLOW_VERSION),),
        fallback_object_types=(),
    ))
    # M7.2.1：整车采购逐 VIN 进度（vehicle_purchase）静态注册。
    registry.register(DomainAdapterSpec(
        name='vehicle_purchase', factory=VehiclePurchaseAdapter, object_types=('case',),
        operation_ids=(PURCHASE_READ, PURCHASE_CREATE, PURCHASE_ACTION),
        kind_versions=(('case', PURCHASE_KIND, PURCHASE_FLOW_VERSION),),
        fact_kind_versions=(('case', PURCHASE_KIND, PURCHASE_FLOW_VERSION),),
        fallback_object_types=(),
    ))
    # M7.1.3：退订退车及维修退款纠正（aftercare）静态注册。
    registry.register(DomainAdapterSpec(
        name='aftercare', factory=AftercareAdapter, object_types=('case',),
        operation_ids=(AFTERCARE_READ, AFTERCARE_CREATE, AFTERCARE_ACTION),
        kind_versions=(('case', AFTERCARE_KIND, AFTERCARE_FLOW_VERSION),),
        fact_kind_versions=(('case', AFTERCARE_KIND, AFTERCARE_FLOW_VERSION),),
        fallback_object_types=(),
    ))
    # M7.1.2：版本报价与车辆交付（sales_order）静态注册。
    registry.register(DomainAdapterSpec(
        name='sales_order', factory=SalesOrderAdapter, object_types=('case',),
        operation_ids=(SALES_READ, SALES_VEHICLES, SALES_CREATE, SALES_PROPOSE),
        kind_versions=(('case', SALES_KIND, 3),),
        fact_kind_versions=(('case', SALES_KIND, 3),),
        fallback_object_types=(),
    ))
    # M7.1.1：售前接待（lead）静态注册；映射固定，不做发现或动态导入。
    registry.register(DomainAdapterSpec(
        name='lead', factory=LeadAdapter, object_types=('case',),
        operation_ids=(FLOW_READ, FLOW_CREATE, FLOW_ACTION),
        # 原 flow_version 1 的 lead；对象选择与事实适用性分开声明。
        kind_versions=(('case', LEAD_KIND, 1),),
        fact_kind_versions=(('case', LEAD_KIND, 1),),
        fallback_object_types=(),
    ))
