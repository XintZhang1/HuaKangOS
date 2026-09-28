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

__all__ = ['FLOW_ACTION', 'FLOW_CREATE', 'FLOW_READ', 'FlowCaseAdapter',
           'LEAD_ACTIONS', 'LEAD_FACTS', 'LEAD_KIND', 'LeadAdapter',
           'SALES_CREATE', 'SALES_FACTS', 'SALES_KIND', 'SALES_PROPOSE', 'SALES_READ',
           'SALES_VEHICLES', 'SalesOrderAdapter',
           'AFTERCARE_ACTION', 'AFTERCARE_CREATE', 'AFTERCARE_FACTS', 'AFTERCARE_FLOW_VERSION',
           'AFTERCARE_KIND', 'AFTERCARE_READ', 'AFTERCARE_SCENARIOS', 'AftercareAdapter',
           'PURCHASE_ACTION', 'PURCHASE_ACTIONS', 'PURCHASE_CREATE', 'PURCHASE_FACTS',
           'PURCHASE_FLOW_VERSION', 'PURCHASE_KIND', 'PURCHASE_READ', 'VehiclePurchaseAdapter']


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
