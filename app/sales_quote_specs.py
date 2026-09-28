"""V3 shares physical execution actions with v2; commercial authorization is explicit."""
from copy import deepcopy

def order_spec(base):
    from .flow_specs import a, f, REASON, PAY_FIELDS
    spec=deepcopy(base)
    spec.update(label='车辆报价与交付',create_roles=[],fields=[])
    spec['actions']=[x for x in spec['actions'] if x.key not in {'approve','revise'}]
    spec['actions'][:0]=[
        a('quote_approve','批准本版报价','manager','reserved,executing',[REASON],task='quote_approve'),
        a('quote_reject','退回本版报价','manager','reserved,executing',[REASON],task='quote_approve'),
        a('quote_withdraw','撤回未生效报价','sales','reserved,executing',[REASON]),
        a('release_vehicle','确认释放原配车','inventory','executing',[REASON,f('evidence_id','未出库实车核对凭据','file',file_category='evidence')]),
        a('refund_excess','登记变更后原款退差额','finance','executing',[f('original_id','原收款','payment')]+PAY_FIELDS,task='refund_excess'),
    ]
    return spec
