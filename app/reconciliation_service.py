"""Financial statements freeze observations; cash is confirmed separately by each store."""
from contextlib import contextmanager
from datetime import date,datetime
from decimal import Decimal
import hashlib,json,uuid
from fastapi import HTTPException
from sqlalchemy import select,func,or_
from sqlalchemy.exc import IntegrityError,OperationalError
from sqlalchemy.orm.exc import StaleDataError
from .db import Base,today,utcnow
from .models import Store,CashEntry
from .flow_models import Case,Task,Account,FileAsset
from .tenancy import single_store,role_for_store,set_scope
from . import flow_engine as eng,group_service as group
from . import business_entity_service as entities
from .reconciliation_models import (ReconciliationBatch,ReconciliationIssue,ClearingBucket,ClearingOrder,
    ClearingCash,ClearingOffset,ReconciliationEvent,ReconciliationReceipt)

CURRENT_DEFINITION_VERSION=21

READ={'admin','manager','finance','auditor'};FINANCE={'admin','finance'};MANAGERS={'admin','manager'}
LABELS={'draft':'财务对账中','review':'待独立店长封存','sealed':'已封存','superseded':'已有重算版本',
    'requested':'待付款店实际支付','paid':'付款已记，收款店待确认','settled':'双方已确认结清','cancelled':'已撤销'}

def can_read(user,row):return user.role in READ


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()
def clean(row):return {c.name:(getattr(row,c.name).isoformat() if isinstance(getattr(row,c.name),(date,datetime)) else getattr(row,c.name)) for c in row.__table__.columns}


@contextmanager
def authority(db,user,roles=READ):
    sid=single_store(db)
    if role_for_store(db,user,sid) not in roles or not db.scalar(select(Store.id).where(Store.id==sid,Store.active.is_(True))):
        raise HTTPException(403,'当前门店岗位不能办理业务对账或内部清算')
    old=db.info.get('_reconciliation_authority');db.info['_reconciliation_authority']=(user.id,sid)
    try:yield sid
    finally:
        if old is None:db.info.pop('_reconciliation_authority',None)
        else:db.info['_reconciliation_authority']=old


@contextmanager
def coordination(db,sid,parties):
    if not db.info.get('_reconciliation_authority') or sid not in parties:raise HTTPException(403,'清算双方范围无效')
    db.flush();old={k:db.info.get(k) for k in ('store_scope','write_store')};set_scope(db,[sid],sid)
    try:yield;db.flush()
    finally:
        for k,v in old.items():
            if v is None:db.info.pop(k,None)
            else:db.info[k]=v


def execute(db,user,key,action,values,roles,operation):
    try:
        with authority(db,user,roles):
            hashed=digest({'action':action,'values':values})
            receipt=db.scalar(select(ReconciliationReceipt).where(ReconciliationReceipt.request_key==key))
            if receipt:
                if receipt.actor_id!=user.id or receipt.digest!=hashed:raise HTTPException(409,'请求编号已用于不同动作或内容')
                return receipt.result
            result=operation()
            db.add(ReconciliationReceipt(request_key=key,actor_id=user.id,digest=hashed,result=result));db.commit()
            return result
    except (StaleDataError,IntegrityError,OperationalError):
        db.rollback();raise HTTPException(409,'记录已变化或正在由其他员工办理，请刷新核对原请求结果')
    except Exception:db.rollback();raise


def evidence(db,user,case,key):
    eng.file_exists(db,case,key)
    return key


def event(db,user,case,action,reason,evidence_id=None,detail=None):
    db.add(ReconciliationEvent(case_id=case.id,actor_id=user.id,action=action,reason=reason,evidence_id=evidence_id,detail=detail or {}))
    eng.log_event(db,user,case,action,'业务对账与内部清算',detail=detail or {})


def case_row(db,user,key,version=None):
    row=eng.get_case(db,user,key)
    if row.kind not in {'reconciliation','interstore_clearing'} or row.flow_version!=2:raise HTTPException(409,'对账流程版本不受支持')
    if version is not None:group._version(row,version)
    row.updated_at=utcnow();db.flush();return row


def new_case(db,user,kind,title,due):
    row=Case(kind=kind,flow_version=2,number='HK-RC-'+uuid.uuid4().hex[:16].upper(),title=title,
        state='pending',created_by=user.id,owner_id=user.id,business_date=today(),due_date=due,amount_cents=0,data={})
    db.add(row)
    if kind=='interstore_clearing':entities.note_coordinated_case(db,user,row)
    db.flush()
    if kind!='interstore_clearing':entities.freeze_case_entity(db,user,row)
    return row


def snapshot(db,user,start,end,definition_version=CURRENT_DEFINITION_VERSION):
    """Period immutable facts plus explicitly current receivables/internal positions."""
    from .flow_analytics import build_analytics
    from .group_models import GroupEntry
    from .group_benefits_models import BenefitEntry
    sid=single_store(db);manifest=[];summary={}
    models={m.local_table.name:m.class_ for m in Base.registry.mappers}
    period_names={'cash_entries','flow_payment_links','flow_stock_moves','flow_member_entries','group_entries','benefit_entries',
        'procurement_payments','procurement_receipts','procurement_return_postings','interstore_clearing_cash','interstore_clearing_offsets',
        'vehicle_purchase_payments','vehicle_purchase_receipts','vehicle_purchase_movements','retail_payments','retail_dispatches','retail_return_postings'}
    current_names={'group_settlement_entries','benefit_settlements','material_transfer_settlements','vehicle_transfer_settlements',
        'group_reservations','group_refund_requests','benefit_reservations','benefit_refunds'}
    if definition_version not in {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21}:raise HTTPException(409,'对账来源定义版本不受支持，不能按现行规则猜测旧批次')
    if definition_version>=2:
        summary['definition_version']=definition_version
        period_names|={'invoice_results','warehouse_entries','membership_fees','membership_points_changes','membership_points_debt_payments'}
        current_names|={'warehouse_balances','membership_points_claims'}
    if definition_version>=3:
        period_names|={'aftercare_applications','aftercare_adjustments','vehicle_position_entries','business_finance_advance_entries'}
        current_names|={'business_finance_advances','business_finance_applications','business_finance_credit_links','business_finance_cash_batches',
            'business_finance_cash_allocations','business_finance_corrections','business_finance_return_receivables','business_finance_advance_returns',
            'group_aftercare_holds','group_aftercare_postings','vehicle_positions'}
        from .cash_basis import excluded_cash_ids
        summary['excluded_cash_ids']=sorted(excluded_cash_ids(db,7 if definition_version>=21 else 6 if definition_version>=20 else 5 if definition_version>=17 else 4 if definition_version>=13 else 3))
    if definition_version>=4:
        period_names|={'opening_account_entries','opening_vehicle_entries'}
        current_names|={'opening_imports','opening_attestations','private_file_objects','recharge_bundle_orders','recharge_bundle_purchases',
            'recharge_bundle_components','recharge_bundle_refunds','recharge_bundle_refund_components','recharge_bundle_refund_postings'}
    if definition_version>=5:
        period_names|={'claims_applications','claims_responsibility_entries','claims_cash','claims_customer_payments'}
        current_names|={'claims_orders','claims_assessments','claims_approvals','claims_transmissions','claims_results','claims_bindings',
            'claims_resolutions','claims_resolution_approvals','claims_reimbursement_approvals','claims_return_plans',
            'claims_return_approvals','claims_return_cancellations','claims_closures',
            'vehicle_import_batches','vehicle_import_rows','vehicle_import_results',
            'retail_bundle_rules','retail_bundle_components','retail_bundle_sales','retail_bundle_allocations'}
    if definition_version>=6:
        current_names|={'service_orders', 'service_fulfillments', 'service_authorizations', 'service_termination_consents', 'service_price_approvals', 'service_pass_entries', 'sales_quote_reviews', 'service_external_results', 'sales_quote_adjustments', 'service_quotes', 'service_refunds', 'sales_quotes', 'service_terminations', 'service_termination_approvals', 'service_lines', 'service_submissions', 'service_quote_cancellations', 'service_termination_cancellations', 'sales_vehicle_releases', 'service_tender_slices', 'service_charge_adjustments', 'sales_quote_resolutions', 'service_termination_applications', 'sales_quote_consents'}
    if definition_version>=7:
        from .reconciliation_v7 import CURRENT_NAMES
        current_names|=CURRENT_NAMES
    if definition_version>=8:
        from .reconciliation_v8 import PERIOD_NAMES as V8_PERIOD,CURRENT_NAMES as V8_CURRENT
        period_names|=V8_PERIOD;current_names|=V8_CURRENT
    if definition_version>=9:
        from .reconciliation_v9 import PERIOD_NAMES as V9_PERIOD,CURRENT_NAMES as V9_CURRENT
        period_names|=V9_PERIOD;current_names|=V9_CURRENT
    if definition_version>=10:
        from .reconciliation_v10 import CURRENT_NAMES as V10_CURRENT
        current_names|=V10_CURRENT
    if definition_version>=11:
        from .reconciliation_v11 import CURRENT_NAMES as V11_CURRENT
        current_names|=V11_CURRENT
    if definition_version>=12:
        from .reconciliation_v12 import CURRENT_NAMES as V12_CURRENT,PERIOD_NAMES as V12_PERIOD,SOURCE_FIELDS as V12_FIELDS
        current_names|=V12_CURRENT;period_names|=V12_PERIOD
    if definition_version>=13:
        from .reconciliation_v13 import CURRENT_NAMES as V13_CURRENT,SOURCE_FIELDS as V13_FIELDS
        current_names|=V13_CURRENT
    if definition_version>=14:
        from .reconciliation_v14 import CURRENT_NAMES as V14_CURRENT,SOURCE_FIELDS as V14_FIELDS
        current_names|=V14_CURRENT
    if definition_version>=15:
        from .reconciliation_v15 import CURRENT_NAMES as V15_CURRENT,PERIOD_NAMES as V15_PERIOD,SOURCE_FIELDS as V15_FIELDS
        current_names|=V15_CURRENT;period_names|=V15_PERIOD
    source_keys={}
    if definition_version>=16:
        from .rework_extension_sources import CURRENT_NAMES as V16_CURRENT,SOURCE_FIELDS as V16_FIELDS,SOURCE_KEYS
        current_names|=V16_CURRENT;source_keys.update(SOURCE_KEYS)
    if definition_version>=17:
        from .reconciliation_v17 import CURRENT_NAMES as V17_CURRENT,SOURCE_FIELDS as V17_FIELDS
        current_names|=V17_CURRENT
    if definition_version>=18:
        from .reconciliation_v18 import CURRENT_NAMES as V18_CURRENT,SOURCE_FIELDS as V18_FIELDS
        current_names|=V18_CURRENT
    if definition_version>=19:
        from .reconciliation_v19 import CURRENT_NAMES as V19_CURRENT,SOURCE_FIELDS as V19_FIELDS
        current_names|=V19_CURRENT
    if definition_version>=20:
        from .reconciliation_v20 import CURRENT_NAMES as V20_CURRENT,SOURCE_FIELDS as V20_FIELDS
        current_names|=V20_CURRENT
    if definition_version>=21:
        from .reconciliation_v21 import CURRENT_NAMES as V21_CURRENT,SOURCE_FIELDS as V21_FIELDS
        current_names|=V21_CURRENT
    from .business_finance_bundle_corrections import bundle_correction_case_ids
    old_excluded_corrections=bundle_correction_case_ids(db) if definition_version<17 else set()
    from .business_finance_partial_corrections import partial_correction_case_ids
    old_partial_cases=partial_correction_case_ids(db) if definition_version<20 else set()
    batch_model=models['business_finance_cash_batches']
    old_partial_batches=set(db.scalars(select(batch_model.id).where(batch_model.case_id.in_(old_partial_cases)))) if old_partial_cases else set()
    claim_dates={r.id:r.business_date for r in db.scalars(select(models['claims_applications']))} if definition_version>=5 else {}
    adjustment_dates={r.id:r.business_date for r in db.scalars(select(models['aftercare_applications']))} if definition_version>=3 else {}
    cash_dates={r.id:r.business_date for r in db.scalars(select(CashEntry).where(CashEntry.approval_state=='approved'))}
    stock_model=models['flow_stock_moves'];stock_rows={r.id:r for r in db.scalars(select(stock_model))}
    payment_dates={r.id:r.business_date for r in db.scalars(select(models['flow_payment_links']))}
    with group.authority(db,user,READ):
        invoice_directions={r.id:r.direction for r in db.scalars(select(models['invoice_applications']))} if definition_version>=2 else {}
        benefit_dates={r.id:r.occurred_at for r in db.scalars(select(BenefitEntry).where(BenefitEntry.store_id==sid))} if definition_version>=2 else {}
        wallet_ids=set(db.scalars(select(BenefitEntry.wallet_id).where(BenefitEntry.store_id==sid)))
        for model_name in ['benefit_reservations','benefit_refunds']:
            model=models[model_name];wallet_ids.update(db.scalars(select(model.wallet_id).where(model.store_id==sid)))
        benefit_wallets={r.id:r.rule_id for r in db.scalars(select(models['benefit_wallets']).where(models['benefit_wallets'].id.in_(wallet_ids)))}
        benefit_rules={r.id:r for r in db.scalars(select(models['benefit_rules']).where(models['benefit_rules'].id.in_(set(benefit_wallets.values()))))}
        for name in sorted(period_names|current_names):
            model=models.get(name)
            if model is None:continue
            key_name=source_keys.get(name,'id')
            query=select(model).where(model.store_id==sid).order_by(getattr(model,key_name)).limit(10001)
            if name in {'business_finance_stored_correction_requests','business_finance_stored_corrections'} and old_excluded_corrections:
                query=query.where(model.case_id.notin_(old_excluded_corrections))
            if name in {'business_finance_corrections','business_finance_cash_batches'} and old_partial_cases:
                query=query.where(model.case_id.notin_(old_partial_cases))
            if name=='business_finance_cash_allocations' and old_partial_batches:
                query=query.where(model.batch_id.notin_(old_partial_batches))
            if (definition_version>=9 and name in V9_PERIOD|V9_CURRENT) or (definition_version>=11 and name in V11_CURRENT) or (definition_version>=12 and name in V12_FIELDS):
                # Central physical/review tables require explicit domain read authority.
                # The statement is still restricted to its single local store.
                from .transfer_goods_recovery_analytics import report_authority
                with report_authority(db,user):rows=list(db.scalars(query))
            else:rows=list(db.scalars(query))
            if len(rows)>10000:raise HTTPException(409,'来源超过单批上限，请拆分期间或联系管理员导出核对')
            totals={'count':0,'amount_cents':0,'value_cents':0,'quantity_milli_by_item':{},'units_by_kind':{}}
            for row in rows:
                if hasattr(row,'store_id') and row.store_id!=sid:continue
                if name in {'group_reservations','benefit_reservations'} and row.status!='reserved':continue
                if name in {'group_refund_requests','benefit_refunds'} and row.status not in {'requested','approved'}:continue
                data=clean(row);basis='current'
                if definition_version>=12 and name in V12_FIELDS:data={k:data[k] for k in V12_FIELDS[name]}
                if definition_version>=13 and name in V13_FIELDS:data={k:data[k] for k in V13_FIELDS[name]}
                if definition_version>=14 and name in V14_FIELDS:data={k:data[k] for k in V14_FIELDS[name]}
                if definition_version>=15 and name in V15_FIELDS:data={k:data[k] for k in V15_FIELDS[name]}
                if definition_version>=16 and name in V16_FIELDS:data={k:data[k] for k in V16_FIELDS[name]}
                if definition_version>=17 and name in V17_FIELDS:data={k:data[k] for k in V17_FIELDS[name]}
                if definition_version>=18 and name in V18_FIELDS:data={k:data[k] for k in V18_FIELDS[name]}
                if definition_version>=19 and name in V19_FIELDS:data={k:data[k] for k in V19_FIELDS[name]}
                if definition_version>=20 and name in V20_FIELDS:data={k:data[k] for k in V20_FIELDS[name]}
                if definition_version>=21 and name in V21_FIELDS:data={k:data[k] for k in V21_FIELDS[name]}
                if definition_version<13 and name=='business_finance_advances':data.pop('correction_cents',None)
                if definition_version<13 and name=='addon_quotes':
                    data.pop('pricing_version',None);data.pop('gift_terms',None)
                if definition_version<13 and name=='addon_approvals':data.pop('gift_confirmed',None)
                if name in period_names:
                    when=getattr(row,'business_date',None) or getattr(row,'occurred_at',None)
                    if name=='invoice_results':when=row.issued_on
                    if name=='membership_fees':when=cash_dates.get(row.cash_id)
                    if name=='membership_points_debt_payments':when=benefit_dates.get(row.benefit_entry_id)
                    if name=='aftercare_adjustments':when=adjustment_dates.get(row.application_id)
                    if name=='claims_responsibility_entries':when=claim_dates.get(row.application_id)
                    if when is None and getattr(row,'cash_id',None):when=cash_dates.get(row.cash_id)
                    if when is None and getattr(row,'stock_move_id',None):when=getattr(stock_rows.get(row.stock_move_id),'business_date',None)
                    if when is None and getattr(row,'payment_link_id',None):when=payment_dates.get(row.payment_link_id)
                    if isinstance(when,datetime):
                        from zoneinfo import ZoneInfo
                        from datetime import timezone
                        from .config import settings
                        when=when.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(settings.timezone)).date()
                    if when is None or not start<=when<=end:continue
                    if name=='cash_entries' and row.approval_state!='approved':continue
                    basis='period'
                source_id=getattr(row,key_name)
                manifest.append({'key':name+':'+str(source_id),'source':name,'source_id':source_id,'case_id':getattr(row,'case_id',None),'basis':basis,'data':data})
                totals['count']+=1
                for k in ['amount_cents','value_cents']:
                    if k in data:
                        sign=-1 if k=='amount_cents' and data.get('direction')=='out' else 1
                        if name=='invoice_results' and invoice_directions.get(row.case_id)=='red':sign=-1
                        totals[k]+=sign*data[k]
                if 'quantity_milli' in data:
                    item=getattr(row,'item_id',None) or getattr(stock_rows.get(getattr(row,'stock_move_id',None)),'item_id',None)
                    label=str(item) if item else name+':'+str(row.id)
                    totals['quantity_milli_by_item'][label]=totals['quantity_milli_by_item'].get(label,0)+data['quantity_milli']
                if name in {'benefit_entries','benefit_reservations','benefit_refunds'}:
                    rule=benefit_rules[benefit_wallets[row.wallet_id]]
                    unit=rule.kind+(':'+rule.service_code if rule.kind=='package' else '')
                    totals['units_by_kind'][unit]=totals['units_by_kind'].get(unit,0)+row.units
                if name in {'membership_points_changes','membership_points_debt_payments'}:
                    totals['units_by_kind']['points']=totals['units_by_kind'].get('points',0)+row.units
            if definition_version>=10 and name in V10_CURRENT:
                from .reconciliation_v10 import source_summary
                totals=source_summary([e for e in manifest if e['source']==name])
            if definition_version>=11 and name in V11_CURRENT:
                from .reconciliation_v11 import source_summary as search_summary
                totals=search_summary([e for e in manifest if e['source']==name])
            if definition_version>=12 and name in V12_FIELDS:
                from .reconciliation_v12 import source_summary as vehicle_summary
                totals=vehicle_summary([e for e in manifest if e['source']==name],start.isoformat(),end.isoformat())
            if definition_version>=13 and name in V13_FIELDS:
                from .reconciliation_v13 import source_summary as finance_summary
                totals=finance_summary([e for e in manifest if e['source']==name])
            if definition_version>=14 and name in V14_FIELDS:
                from .reconciliation_v14 import source_summary as supplier_summary
                totals=supplier_summary([e for e in manifest if e['source']==name])
            if definition_version>=15 and name in V15_FIELDS:
                from .reconciliation_v15 import source_summary as income_summary
                totals=income_summary([e for e in manifest if e['source']==name],start.isoformat(),end.isoformat())
            if definition_version>=16 and name in V16_FIELDS:
                from .rework_extension_sources import source_summary as rework_summary
                totals=rework_summary([e for e in manifest if e['source']==name])
            if definition_version>=17 and name in V17_FIELDS:
                from .reconciliation_v17 import source_summary as bundle_summary
                totals=bundle_summary([e for e in manifest if e['source']==name])
            if definition_version>=18 and name in V18_FIELDS:
                from .reconciliation_v18 import source_summary as member_price_summary
                totals=member_price_summary([e for e in manifest if e['source']==name])
            if definition_version>=19 and name in V19_FIELDS:
                from .reconciliation_v19 import source_summary as package_summary
                totals=package_summary([e for e in manifest if e['source']==name])
            if definition_version>=20 and name in V20_FIELDS:
                from .reconciliation_v20 import source_summary as partial_summary
                totals=partial_summary([e for e in manifest if e['source']==name])
            if definition_version>=21 and name in V21_FIELDS:
                from .reconciliation_v21 import source_summary as fee_correction_summary
                totals=fee_correction_summary([e for e in manifest if e['source']==name])
            summary[name]=totals
    if definition_version>=10:
        from .reconciliation_v10 import pending_from_manifest
        summary['retail_group_pending_original_units']=pending_from_manifest(manifest)
    report=build_analytics(db,user,start,end,cash_definition_version=7 if definition_version>=21 else 6 if definition_version>=20 else 5 if definition_version>=17 else 4 if definition_version>=13 else min(definition_version,3),include_vehicle_income=definition_version>=15)
    if definition_version>=2:
        for dataset in ('invoice_corrections','membership_points_debts'):
            rows=report['tables'][dataset]['rows']
            if definition_version<15 and dataset=='invoice_corrections':
                income_ids=set(db.scalars(select(Case.id).where(Case.kind=='vehicle_income')))
                rows=[r for r in rows if (r.get('route') or {}).get('id') not in income_ids]
            if definition_version<13 and dataset=='invoice_corrections':
                insurance_ids=set(db.scalars(select(Case.id).where(Case.kind=='insurance')))
                rows=[r for r in rows if (r.get('route') or {}).get('id') not in insurance_ids]
            for index,value in enumerate(sorted(rows,key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False))):
                manifest.append({'key':dataset+':'+str(index),'source':dataset,'source_id':index,
                    'case_id':(value.get('route') or {}).get('id'),'basis':'current','data':value})
    for index,row in enumerate(sorted(report['tables']['receivables']['rows'],key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False))):
        manifest.append({'key':'receivable:'+str(index),'source':'receivable','source_id':index,
            'case_id':row.get('route',{}).get('id') if row.get('route',{}).get('type')=='case' else None,'basis':'current','data':row})
    summary['current_receivable_cents']=report['metrics']['receivable_cents']
    summary['period_cash_in_cents']=report['metrics']['cash_in_cents'];summary['period_cash_out_cents']=report['metrics']['cash_out_cents']
    manifest.sort(key=lambda x:x['key'])
    return manifest,summary,digest({'manifest':manifest,'summary':summary})


def batch_info(db,user,row,live=True):
    value=clean(row);value['status_label']=LABELS[row.status]
    case=db.scalar(select(Case).where(Case.id==row.case_id));value['case_version']=case.version
    value['issues']=[clean(x) for x in db.scalars(select(ReconciliationIssue).where(ReconciliationIssue.batch_id==row.id).order_by(ReconciliationIssue.id))]
    successor=db.scalar(select(ReconciliationBatch.id).where(ReconciliationBatch.previous_id==row.id));value['successor_id']=successor
    value['definition_version']=row.summary.get('definition_version',1)
    value['source_changed']=snapshot(db,user,row.start,row.end,value['definition_version'])[2]!=row.digest if live else False
    return value


def list_batches(db,user):
    with authority(db,user):return {'items':[{k:v for k,v in clean(x).items() if k not in {'manifest'}} for x in db.scalars(select(ReconciliationBatch).order_by(ReconciliationBatch.id.desc()).limit(200))]}
def get_batch(db,user,key):
    with authority(db,user):
        row=db.scalar(select(ReconciliationBatch).where(ReconciliationBatch.id==key))
        if not row:raise HTTPException(404,'本店对账批次不存在')
        return batch_info(db,user,row)


def create_batch(db,user,key,start,end,reason,previous=None):
    def operation():
        if start>end or end>today() or (end-start).days>365:raise HTTPException(422,'对账期间须为过去或今天，且跨度不超过365天')
        old=db.scalar(select(ReconciliationBatch).where(ReconciliationBatch.start==start,ReconciliationBatch.end==end).order_by(ReconciliationBatch.revision.desc()))
        if old:raise HTTPException(409,'该期间已有对账版本，请从原批次明确重算或复开')
        return _new_batch(db,user,start,end,reason)
    return execute(db,user,key,'batch_create',{'start':start,'end':end,'reason':reason},FINANCE,operation)


def _new_batch(db,user,start,end,reason,previous=None):
    manifest,summary,hashed=snapshot(db,user,start,end)
    case=new_case(db,user,'reconciliation',f'业务对账 {start} 至 {end}',today())
    row=ReconciliationBatch(case_id=case.id,start=start,end=end,revision=previous.revision+1 if previous else 1,
        previous_id=previous.id if previous else None,prepared_by=user.id,reason=reason,digest=hashed,manifest=manifest,summary=summary)
    db.add(row);db.flush();case.data={'reconciliation_id':row.id};eng.ensure_task(db,case,'reconcile','核对来源与处理差异','finance')
    event(db,user,case,'reconcile_create',reason,detail={'batch_id':row.id,'digest':hashed})
    db.flush();return batch_info(db,user,row,False)


def batch_command(db,user,key,request,version,case_version,action,values):
    roles=MANAGERS if action in {'seal','reopen'} else FINANCE
    def operation():
        row=db.scalar(select(ReconciliationBatch).where(ReconciliationBatch.id==key).with_for_update())
        if not row:raise HTTPException(404,'本店对账批次不存在')
        group._version(row,version);case=case_row(db,user,row.case_id,case_version)
        if db.scalar(select(ReconciliationBatch.id).where(ReconciliationBatch.previous_id==row.id)):raise HTTPException(409,'已有后继版本，请办理最新对账')
        if action in {'reopen','recalculate'}:
            if action=='reopen' and row.status!='sealed':raise HTTPException(409,'只有封存版本才需复开')
            if action=='recalculate' and row.status not in {'draft','review'}:raise HTTPException(409,'封存版本须由店长明确复开')
            if row.status!='sealed':row.status='superseded'
            eng.close_tasks(db,case,user);case.state='completed'
            event(db,user,case,'reconcile_'+action,values['reason'])
            return _new_batch(db,user,row.start,row.end,values['reason'],row)
        if row.status not in {'draft','review'}:raise HTTPException(409,'此对账版本已结束')
        if action=='issue':
            if row.status!='draft':raise HTTPException(409,'请先重算退回财务对账')
            if values['line_key'] not in {x['key'] for x in row.manifest}:raise HTTPException(422,'差异必须指向本版本真实来源条目')
            evidence(db,user,case,values['evidence_id'])
            db.add(ReconciliationIssue(batch_id=row.id,line_key=values['line_key'],difference_cents=values['difference_cents'],
                reason=values['reason'],opened_by=user.id,evidence_id=values['evidence_id']))
        elif action=='resolve':
            issue=db.scalar(select(ReconciliationIssue).where(ReconciliationIssue.id==values['issue_id'],ReconciliationIssue.batch_id==row.id))
            if not issue:raise HTTPException(404,'本版本差异不存在')
            group._version(issue,values['issue_version'])
            if issue.status!='open':raise HTTPException(409,'差异已记录处理结果')
            evidence(db,user,case,values['evidence_id']);issue.status='resolved';issue.resolved_by=user.id
            issue.resolution=values['reason'];issue.resolution_evidence_id=values['evidence_id']
        elif action in {'submit','seal'}:
            if snapshot(db,user,row.start,row.end,row.summary.get('definition_version',1))[2]!=row.digest:raise HTTPException(409,'来源有晚到、冲正或余额变化，请重算产生新版本')
            if db.scalar(select(ReconciliationIssue.id).where(ReconciliationIssue.batch_id==row.id,ReconciliationIssue.status=='open')):raise HTTPException(409,'仍有未处理差异，不能提交或封存')
            if action=='submit':
                if row.status!='draft':raise HTTPException(409,'对账已提交')
                row.status='review';row.submitted_by=user.id;eng.finish_task(db,case,'reconcile',user)
                eng.ensure_task(db,case,'reconcile_seal','独立复核并封存业务对账','manager')
            else:
                if row.status!='review':raise HTTPException(409,'须先由财务完成对账并提交')
                if user.id in {row.prepared_by,row.submitted_by}:raise HTTPException(403,'封存必须由另一位店长或管理员独立复核')
                evidence(db,user,case,values['evidence_id']);row.status='sealed';row.sealed_by=user.id;row.sealed_at=utcnow()
                eng.finish_task(db,case,'reconcile_seal',user);case.state='completed';case.completed_date=today()
        else:raise HTTPException(404,'对账动作不存在')
        row.updated_at=utcnow();event(db,user,case,'reconcile_'+action,values['reason'],values.get('evidence_id'),{'batch_id':row.id})
        db.flush();return batch_info(db,user,row,False)
    return execute(db,user,request,'batch:'+str(key)+':'+action,{'version':version,'case_version':case_version,'values':values},roles,operation)


def _clearing_origins():
    from .transfer_models import TransferSettlement
    from .transfer_exception_models import TransferLossSettlement
    from .vehicle_transfer_models import VehicleTransferSettlement
    from .transfer_goods_recovery_models import GoodsSettlement
    from .vehicle_transport_models import VehicleTransportLossSettlement,VehicleTransportFoundSettlement
    return {'material':TransferSettlement,'material_loss':TransferLossSettlement,'material_found':GoodsSettlement,'vehicle':VehicleTransferSettlement,
        'vehicle_loss':VehicleTransportLossSettlement,'vehicle_found':VehicleTransportFoundSettlement}


def _lock_clearing_original(db,user,kind,origin_id,action,debtor=True):
    """Read immutable identity, lock shared transfer before any clearing locks."""
    from .transfer_goods_recovery_service import settlement_read_authority,lock_clearing_parent
    model=_clearing_origins().get(kind)
    if model is None:raise HTTPException(422,'仅支持有明确原条目的物资或整车店间往来')
    with settlement_read_authority(db):
        stmt=select(model).where(model.id==origin_id)
        stmt=stmt.where(model.amount_cents<0 if debtor else model.amount_cents>0)
        origin=db.scalar(stmt)
    if not origin:raise HTTPException(404,'本店原清算条目不存在')
    if kind.startswith('material'):lock_clearing_parent(db,user,origin.transfer_id,action)
    elif kind in {'vehicle_loss','vehicle_found'}:
        from .vehicle_transport_service import lock_clearing_parent as lock_vehicle
        lock_vehicle(db,user,origin.transfer_id,action)
    return origin


def origins(db,user):
    from .transfer_goods_recovery_service import settlement_read_authority,clearing_pause_info
    with authority(db,user):
        result=[];names={s.id:s.name for s in db.scalars(select(Store))};pause={}
        with settlement_read_authority(db):
          for kind,model in _clearing_origins().items():
            rows=list(db.scalars(select(model).where(model.amount_cents<0).order_by(model.id).limit(25001)))
            if len(rows)>25000:raise HTTPException(413,'清算原条目超过25000条，请分批核对，不能显示截断结果')
            for row in rows:
                bucket=db.scalar(select(ClearingBucket).where(ClearingBucket.origin_kind==kind,ClearingBucket.debtor_origin_id==row.id))
                if kind.startswith('material') and row.transfer_id not in pause:pause[row.transfer_id]=clearing_pause_info(db,user,row.transfer_id)
                vehicle_pause=None
                if kind in {'vehicle_loss','vehicle_found'}:
                    from .vehicle_transport_service import clearing_pause_info as vehicle_pause_info
                    vehicle_pause=vehicle_pause_info(db,user,row.transfer_id)
                result.append({'origin_kind':kind,'origin_id':row.id,'transfer_id':row.transfer_id,'counterparty_store_id':row.counterparty_store_id,
                    'counterparty_store_name':names.get(row.counterparty_store_id,''),'active_goods_recovery_id':pause.get(row.transfer_id) if kind.startswith('material') else None,'active_vehicle_exception_id':vehicle_pause,
                    'total_cents':-row.amount_cents,'reserved_cents':bucket.reserved_cents if bucket else 0,
                    'settled_cents':bucket.settled_cents if bucket else 0,'available_cents':-row.amount_cents-(bucket.reserved_cents+bucket.settled_cents if bucket else 0)})
        return {'items':result}


def _bucket(db,user,kind,origin_id):
    from .transfer_goods_recovery_service import settlement_read_authority
    origin=_lock_clearing_original(db,user,kind,origin_id,'clearing_create');model=_clearing_origins()[kind]
    bucket=db.scalar(select(ClearingBucket).where(ClearingBucket.origin_kind==kind,ClearingBucket.debtor_origin_id==origin.id).with_for_update().execution_options(populate_existing=True))
    sid=single_store(db);other=origin.counterparty_store_id
    if not db.scalar(select(Store.id).where(Store.id==other,Store.active.is_(True))):raise HTTPException(409,'收款门店已停用')
    if bucket:return bucket
    with settlement_read_authority(db),coordination(db,other,(sid,other)):
        stmt=select(model).where(model.transfer_id==origin.transfer_id,model.counterparty_store_id==sid,model.amount_cents==-origin.amount_cents)
        if kind=='material':stmt=stmt.where(model.movement_id==origin.movement_id)
        if kind=='material_loss':stmt=stmt.where(model.posting_id==origin.posting_id,model.exception_id==origin.exception_id)
        if kind=='material_found':stmt=stmt.where(model.posting_id==origin.posting_id,model.recovery_id==origin.recovery_id)
        if kind=='vehicle_loss':stmt=stmt.where(model.loss_id==origin.loss_id,model.exception_id==origin.exception_id)
        if kind=='vehicle_found':stmt=stmt.where(model.receipt_id==origin.receipt_id,model.loss_id==origin.loss_id)
        matches=list(db.scalars(stmt.limit(2)))
        if len(matches)!=1:raise HTTPException(409,'原调拨双方往来不唯一配对，不能清算')
        paired=matches[0]
        if kind=='material_found':
            from .transfer_exception_models import TransferLossSettlement
            # Validate each reversal's link to its own immutable loss side,
            # even if another finding happened to have the same amount.
            old=db.scalar(select(TransferLossSettlement).where(TransferLossSettlement.id==paired.original_id))
            with coordination(db,sid,(sid,other)):
                debit_old=db.scalar(select(TransferLossSettlement).where(TransferLossSettlement.id==origin.original_id))
            if not old or not debit_old or old.posting_id!=debit_old.posting_id or old.transfer_id!=origin.transfer_id or old.amount_cents!=-debit_old.amount_cents:
                raise HTTPException(409,'找回反向往来未追同一原损失双方条目')
        paired_id=paired.id
    bucket=ClearingBucket(origin_kind=kind,debtor_origin_id=origin.id,creditor_origin_id=paired_id,
        payer_store_id=sid,receiver_store_id=other,total_cents=-origin.amount_cents,reserved_cents=0,settled_cents=0)
    db.add(bucket);db.flush();return bucket


def clearing_info(db,user,row,sid):
    own=row.payer_case_id if sid==row.payer_store_id else row.receiver_case_id
    case=db.scalar(select(Case).where(Case.id==own))
    value={k:v for k,v in clean(row).items() if k not in {'payer_case_id','receiver_case_id'}}
    value.update(case_id=own,case_version=case.version,status_label=LABELS[row.status],side='payer' if sid==row.payer_store_id else 'receiver')
    bucket=db.scalar(select(ClearingBucket).where(ClearingBucket.id==row.bucket_id))
    value.update(origin_kind=bucket.origin_kind,origin_id=bucket.debtor_origin_id if sid==row.payer_store_id else bucket.creditor_origin_id)
    from .transfer_goods_recovery_service import settlement_read_authority,clearing_pause_info
    with settlement_read_authority(db):
        origin=db.scalar(select(_clearing_origins()[bucket.origin_kind]).where(_clearing_origins()[bucket.origin_kind].id==value['origin_id']))
    value.update(transfer_id=origin.transfer_id,active_goods_recovery_id=clearing_pause_info(db,user,origin.transfer_id) if bucket.origin_kind.startswith('material') else None,
        payer_store_name=db.scalar(select(Store.name).where(Store.id==row.payer_store_id)),receiver_store_name=db.scalar(select(Store.name).where(Store.id==row.receiver_store_id)))
    if bucket.origin_kind=='material_found':value['goods_recovery_id']=origin.recovery_id
    if bucket.origin_kind in {'vehicle_loss','vehicle_found'}:
        from .vehicle_transport_service import clearing_pause_info as vehicle_pause_info
        value['active_vehicle_exception_id']=vehicle_pause_info(db,user,origin.transfer_id)
        value['vehicle_loss_id']=origin.loss_id
    value['cash']=[clean(x) for x in db.scalars(select(ClearingCash).where(ClearingCash.order_id==row.id))]
    value['events']=[clean(x) for x in db.scalars(select(ReconciliationEvent).where(ReconciliationEvent.case_id==own).order_by(ReconciliationEvent.id))]
    return value


def list_clearing(db,user,key=None):
    with authority(db,user) as sid:
        stmt=select(ClearingOrder).where(or_(ClearingOrder.payer_store_id==sid,ClearingOrder.receiver_store_id==sid)).order_by(ClearingOrder.id.desc())
        if key:
            row=db.scalar(stmt.where(ClearingOrder.id==key))
            if not row:raise HTTPException(404,'本店内部清算不存在')
            return clearing_info(db,user,row,sid)
        return {'items':[clearing_info(db,user,r,sid) for r in db.scalars(stmt.limit(200))]}


def create_clearing(db,user,request,values):
    def operation():
        sid=single_store(db);bucket=_bucket(db,user,values['origin_kind'],values['origin_id'])
        if values['amount_cents']>bucket.total_cents-bucket.reserved_cents-bucket.settled_cents:raise HTTPException(409,'金额超过原条目未清算且未占用额度')
        parties=(sid,bucket.receiver_store_id);cases={}
        for party in parties:
            with coordination(db,party,parties):
                case=new_case(db,user,'interstore_clearing','店间调拨往来实际结算',date.fromisoformat(values['due_date']))
                cases[party]=case.id
                eng.ensure_task(db,case,'clearing_pay' if party==sid else 'clearing_receive',
                    '登记本店实际支付' if party==sid else '核对本店实际到账','finance',due=case.due_date)
        row=ClearingOrder(bucket_id=bucket.id,payer_store_id=sid,receiver_store_id=bucket.receiver_store_id,
            payer_case_id=cases[sid],receiver_case_id=cases[bucket.receiver_store_id],amount_cents=values['amount_cents'],
            requested_by=user.id,due_date=date.fromisoformat(values['due_date']),reason=values['reason'])
        bucket.reserved_cents+=row.amount_cents;db.add(row);db.flush()
        for party in parties:
            with coordination(db,party,parties):
                case=db.scalar(select(Case).where(Case.id==cases[party]));case.data={'clearing_id':row.id}
                entities.freeze_coordinated_case(db,user,case,row)
        case=db.scalar(select(Case).where(Case.id==cases[sid]));event(db,user,case,'clearing_create',values['reason'],detail={'clearing_id':row.id})
        db.flush();return clearing_info(db,user,row,sid)
    return execute(db,user,request,'clearing_create',values,FINANCE,operation)


def _cash(db,user,row,case,values,direction):
    evidence(db,user,case,values['evidence_id'])
    account=db.scalar(select(Account).where(Account.id==values['account_id']).with_for_update())
    if not account or not account.active:raise HTTPException(422,'本店有效收付款账户不存在')
    entities.require_account_entity(db,user,case,account.id,today())
    if db.scalar(select(CashEntry.id).where(CashEntry.account==account.name,CashEntry.voucher_no==values['reference'])):raise HTTPException(409,'本店账户流水号已入账，不能重复确认')
    with group.authority(db,user,FINANCE):
        for mapper in Base.registry.mappers:
            model=mapper.class_
            if {'id','store_id','account_id','reference'}<=set(mapper.local_table.c.keys()):
                if db.scalar(select(model.id).where(model.account_id==account.id,model.reference==values['reference'])):
                    raise HTTPException(409,'此账户流水号已用于其他业务，不能重复入账')
    account.updated_at=utcnow();other=row.receiver_store_id if direction=='out' else row.payer_store_id
    cash=CashEntry(doc_no='HK-IC-'+uuid.uuid4().hex[:16],business_date=today(),approval_state='approved',created_by=user.id,
        direction=direction,category='interstore_clearing',amount_cents=row.amount_cents,account=account.name,
        counterparty='集团门店 '+str(other),payment_method='cash' if account.account_type=='cash' else 'bank',
        voucher_no=values['reference'],note='调拨往来实际清算，原清算单 '+str(row.id))
    db.add(cash);db.flush();entities.record_cash_entity(db,user,case,cash,account.id)
    db.add(ClearingCash(order_id=row.id,cash_id=cash.id,account_id=account.id,direction=direction,
        amount_cents=row.amount_cents,reference=values['reference'],evidence_id=values['evidence_id'],actor_id=user.id,business_date=today()))


def clearing_command(db,user,key,request,version,case_version,action,values):
    def operation():
        sid=single_store(db)
        query=select(ClearingOrder).where(ClearingOrder.id==key,or_(ClearingOrder.payer_store_id==sid,ClearingOrder.receiver_store_id==sid))
        row=db.scalar(query)
        if not row:raise HTTPException(404,'本店清算单不存在')
        original_bucket=db.scalar(select(ClearingBucket).where(ClearingBucket.id==row.bucket_id))
        debtor=sid==row.payer_store_id
        _lock_clearing_original(db,user,original_bucket.origin_kind,original_bucket.debtor_origin_id if debtor else original_bucket.creditor_origin_id,'clearing_'+action,debtor)
        row=db.scalar(query.with_for_update().execution_options(populate_existing=True))
        group._version(row,version);payer=sid==row.payer_store_id
        case=case_row(db,user,row.payer_case_id if payer else row.receiver_case_id,case_version)
        bucket=db.scalar(select(ClearingBucket).where(ClearingBucket.id==row.bucket_id).with_for_update().execution_options(populate_existing=True))
        if row.status in {'settled','cancelled'}:raise HTTPException(409,'清算已结束，原现金和往来不可改写')
        if action in {'pay','receive'}:
            expected='clearing_pay' if action=='pay' else 'clearing_receive'
            task=db.scalar(select(Task).where(Task.case_id==case.id,Task.key==expected,Task.status=='open'))
            if not task or (user.role!='admin' and task.assignee_id!=user.id):raise HTTPException(403,'请由本店当前实际收付款待办财务确认')
            if action=='pay' and (not payer or row.status!='requested'):raise HTTPException(409,'只能付款门店确认尚未记账的实际付款')
            if action=='receive' and (payer or row.status!='paid'):raise HTTPException(409,'须先由付款店记实际支付，再由收款店核对实际到账')
            _cash(db,user,row,case,values,'out' if payer else 'in');eng.finish_task(db,case,expected,user)
            row.status='paid' if payer else 'settled'
            if not payer:
                bucket.reserved_cents-=row.amount_cents;bucket.settled_cents+=row.amount_cents
                for party,original,amount,case_id in [(row.payer_store_id,bucket.debtor_origin_id,row.amount_cents,row.payer_case_id),
                    (row.receiver_store_id,bucket.creditor_origin_id,-row.amount_cents,row.receiver_case_id)]:
                    with coordination(db,party,(row.payer_store_id,row.receiver_store_id)):
                        db.add(ClearingOffset(order_id=row.id,origin_kind=bucket.origin_kind,origin_id=original,amount_cents=amount,business_date=today()))
                        own=db.scalar(select(Case).where(Case.id==case_id));own.state='completed';own.completed_date=today()
        elif action in {'cancel','reject'}:
            if row.status!='requested':raise HTTPException(409,'已实际支付不能撤销现金；请记录差异并核对银行及对方到账')
            if (action=='cancel' and not payer) or (action=='reject' and payer):raise HTTPException(403,'付款方可撤销，收款方可拒绝尚未付款申请')
            row.status='cancelled';bucket.reserved_cents-=row.amount_cents
            for party,case_id in [(row.payer_store_id,row.payer_case_id),(row.receiver_store_id,row.receiver_case_id)]:
                with coordination(db,party,(row.payer_store_id,row.receiver_store_id)):
                    own=db.scalar(select(Case).where(Case.id==case_id));eng.close_tasks(db,own,user);own.state='cancelled'
        elif action=='difference':evidence(db,user,case,values['evidence_id'])
        else:raise HTTPException(404,'内部清算动作不存在')
        row.updated_at=utcnow();bucket.updated_at=utcnow();event(db,user,case,'clearing_'+action,values['reason'],values.get('evidence_id'),{'clearing_id':row.id})
        db.flush();return clearing_info(db,user,row,sid)
    return execute(db,user,request,'clearing:'+str(key)+':'+action,{'version':version,'case_version':case_version,'values':values},FINANCE,operation)


def internal_cash_ids(db):return set(db.scalars(select(ClearingCash.cash_id)))


def settlement_rows(db,user):
    """Read-only scoped reporting, including paid but not yet received in transit."""
    if user.role not in READ:raise HTTPException(403,'没有清算汇总权限')
    ids=tuple(x for x in db.info.get('store_scope',()) if x)
    old=db.info.get('_reconciliation_authority');db.info['_reconciliation_authority']=('report',ids)
    try:
        cash=[clean(r) for r in db.scalars(select(ClearingCash).order_by(ClearingCash.id))]
        linked_orders={r.id:r for r in db.scalars(select(ClearingOrder).where(ClearingOrder.id.in_({p['order_id'] for p in cash}),
            or_(ClearingOrder.payer_store_id.in_(ids),ClearingOrder.receiver_store_id.in_(ids))))}
        for posting in cash:
            order=linked_orders.get(posting['order_id'])
            if not order or posting['store_id'] not in {order.payer_store_id,order.receiver_store_id}:raise HTTPException(409,'内部现金与本店清算来源不一致')
            posting['case_id']=order.payer_case_id if posting['store_id']==order.payer_store_id else order.receiver_case_id
        offsets=[clean(r) for r in db.scalars(select(ClearingOffset).order_by(ClearingOffset.id))]
        transit=[]
        for r in db.scalars(select(ClearingOrder).where(ClearingOrder.status=='paid',or_(ClearingOrder.payer_store_id.in_(ids),ClearingOrder.receiver_store_id.in_(ids)))):
            transit.append({'id':r.id,'payer_store_id':r.payer_store_id,'receiver_store_id':r.receiver_store_id,
                'amount_cents':r.amount_cents,'due_date':r.due_date.isoformat(),
                'case_id':r.payer_case_id if r.payer_store_id in ids else r.receiver_case_id})
        return {'cash':cash,'in_transit':transit,'settlements':offsets}
    finally:
        if old is None:db.info.pop('_reconciliation_authority',None)
        else:db.info['_reconciliation_authority']=old
