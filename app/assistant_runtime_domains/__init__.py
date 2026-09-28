"""Static business adapters, registered explicitly by the Runtime object layer.

No discovery, plugin imports, background work or database access occurs here.
"""

from .flow_case import FLOW_ACTION, FLOW_CREATE, FLOW_READ, FlowCaseAdapter
from .lead import LEAD_ACTIONS, LEAD_FACTS, LEAD_KIND, LeadAdapter
from .sales_order import (SALES_CREATE, SALES_FACTS, SALES_KIND, SALES_PROPOSE,
                          SALES_READ, SALES_VEHICLES, SalesOrderAdapter)

__all__ = ['FLOW_ACTION', 'FLOW_CREATE', 'FLOW_READ', 'FlowCaseAdapter',
           'LEAD_ACTIONS', 'LEAD_FACTS', 'LEAD_KIND', 'LeadAdapter',
           'SALES_CREATE', 'SALES_FACTS', 'SALES_KIND', 'SALES_PROPOSE', 'SALES_READ',
           'SALES_VEHICLES', 'SalesOrderAdapter']


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
