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
           'GateVisitAdapter']


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
