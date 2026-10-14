"""Current-role personal data projection after delivery; originals remain intact."""
from copy import deepcopy
import re
from fastapi import HTTPException
from sqlalchemy import select, or_

MASKED_ROLES = frozenset({'sales', 'manager', 'finance'})
PHONE_KEYS = frozenset({'phone', 'customer_phone', 'buyer_phone', '客户电话', '联系电话'})
ID_KEYS = frozenset({'buyer_id_number', 'buyer_agent_id_number', 'buyer_tax_id', '身份证号', '证件号码'})


def completed_contract_clause(model):
    from .business_record_delivery_models import RecordDelivery
    from .business_records_models import ContractReceipt
    delivered = select(RecordDelivery.id).where(RecordDelivery.contract_id == model.id,
        RecordDelivery.store_id == model.store_id).exists()
    received = select(ContractReceipt.id).where(ContractReceipt.contract_id == model.id,
        ContractReceipt.store_id == model.store_id).exists()
    return or_(delivered, (model.workflow_version != 'trial-v210') & received)


def customer_completed_clause(model):
    from .business_records_models import SalesContract
    return select(SalesContract.id).where(SalesContract.customer_id == model.id,
        SalesContract.store_id == model.store_id, completed_contract_clause(SalesContract)).exists()


def contract_privacy(db, user, contract):
    from .business_records_models import SalesContract
    completed = bool(db.scalar(select(SalesContract.id).where(SalesContract.id == contract.id,
        completed_contract_clause(SalesContract))))
    masked = completed and user.role in MASKED_ROLES
    return {'completed': completed, 'masked': masked, 'vin_visible': True,
        'can_export_personal': not masked,
        'notice': '销售已终结，电话中间四位及证件末四位隐藏，完整原件不可导出；VIN保留。' if masked else ''}


def mask_phone(value):
    value = str(value or '')
    if not value or '*' in value:
        return value
    return value[:3] + '****' + value[7:] if len(value) >= 7 else '*' * len(value)


def mask_id(value):
    value = str(value or '')
    return value[:-4] + '****' if len(value) >= 4 else '*' * len(value)


def redact_personal_values(data, source=None):
    """Redact typed values and their exact duplicates inside notes/recognition text."""
    replacements = {}
    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in PHONE_KEYS | ID_KEYS and isinstance(item, str) and item:
                    replacements[item] = mask_phone(item) if key in PHONE_KEYS else mask_id(item)
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect(data)
    if source is not None:
        collect(source)
    def clean(value, key=''):
        if isinstance(value, dict):
            return {name: clean(item, name) for name, item in value.items()}
        if isinstance(value, list):
            return [clean(item, key) for item in value]
        if isinstance(value, str):
            if key in PHONE_KEYS:
                return mask_phone(value)
            if key in ID_KEYS:
                return mask_id(value)
            if key in {'vin', '车辆识别号', '车架号'}:
                return value
            for original, masked in replacements.items():
                if len(original) >= 7:
                    value = value.replace(original, masked)
        return value
    return clean(data)


def redact_contract_data(db, user, contract, data):
    privacy = contract_privacy(db, user, contract)
    source = {'customer_phone': contract.customer_phone, 'form_data': contract.form_data,
        'approved_snapshot': contract.approved_snapshot}
    result = redact_personal_values(data, source) if privacy['masked'] else deepcopy(data)
    result['privacy'] = privacy
    if privacy['masked']:
        result['actions'] = [action for action in result.get('actions', []) if action != 'print']
        for item in (result.get('terms') or {}).get('attachments', []):
            item['available'] = False
        gift = (result.get('delivery_state') or {}).get('gift_document')
        if gift:
            gift['available'] = False
    return result


def redact_customer_data(db, user, customer, data):
    from .business_records_models import RecordCustomer, SalesContract, RecordContractCorrection
    closed = user.role in MASKED_ROLES and bool(db.scalar(select(RecordCustomer.id).where(
        RecordCustomer.id == customer.id, customer_completed_clause(RecordCustomer))))
    if not closed:
        return data
    contracts = list(db.scalars(select(SalesContract).where(SalesContract.customer_id == customer.id,
        SalesContract.store_id == customer.store_id, completed_contract_clause(SalesContract))))
    sources = [{'customer_phone': item.customer_phone, 'form_data': item.form_data,
        'approved_snapshot': item.approved_snapshot} for item in contracts]
    if contracts:
        sources += [item.approved_snapshot for item in db.scalars(select(RecordContractCorrection).where(
            RecordContractCorrection.contract_id.in_([contract.id for contract in contracts]),
            RecordContractCorrection.status == 'approved'))]
    return redact_personal_values(data, sources)


def require_personal_export(db, user, contract):
    if contract_privacy(db, user, contract)['masked']:
        raise HTTPException(403, '销售已终结，当前岗位不可导出或打印包含完整客户信息的合同及原件；请由内勤或总经理按原权限复查')


def sanitize_command_result(db, user, result, action='', payload=None):
    """Old idempotent replies obey today's privacy state, never their saved role view."""
    if user.role not in MASKED_ROLES:
        return result
    from .business_records_models import SalesContract, RecordCustomer
    payload = payload or {}
    match = re.match(r'contract:(\d+):', action)
    contract_id = payload.get('contract_id') or (int(match[1]) if match else None)
    if not contract_id and isinstance(result, dict):
        contract_id = result.get('contract_id')
        if not contract_id and str(result.get('number', '')).startswith('XS-'):
            contract_id = result.get('id')
        if not contract_id:
            for key in ('invoice', 'delivery'):
                contract_id = (result.get(key) or {}).get('contract_id')
                if contract_id:
                    break
    if contract_id:
        contract = db.get(SalesContract, contract_id)
        if contract and contract_privacy(db, user, contract)['masked']:
            result = redact_personal_values(result, {'customer_phone': contract.customer_phone,
                'form_data': contract.form_data, 'approved_snapshot': contract.approved_snapshot})
            def close_files(value):
                if isinstance(value, dict):
                    if 'available' in value:
                        value['available'] = False
                    if 'actions' in value:
                        value['actions'] = [item for item in value['actions'] if item != 'print']
                    for item in value.values():
                        close_files(item)
                elif isinstance(value, list):
                    for item in value:
                        close_files(item)
            close_files(result)
            return result
    if action.startswith('customer:') and isinstance(result, dict) and result.get('id'):
        customer = db.get(RecordCustomer, result['id'])
        if customer:
            return redact_customer_data(db, user, customer, result)
    return result
