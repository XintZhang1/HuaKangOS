"""Static business adapters, registered explicitly by the Runtime object layer.

No discovery, plugin imports, background work or database access occurs here.
"""

from .flow_case import FLOW_ACTION, FLOW_CREATE, FLOW_READ, FlowCaseAdapter

__all__ = ['FLOW_ACTION', 'FLOW_CREATE', 'FLOW_READ', 'FlowCaseAdapter']


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
