"""Native care adapters; original request receipt owns commits and idempotency."""
from contextlib import contextmanager
from copy import deepcopy
from fastapi import HTTPException
from sqlalchemy import select
from .db import utcnow
from .services import plain,audit
from .questionnaire_models import (QuestionnairePolicy as Policy,QuestionnaireVersion as Version,
    QuestionnaireReview as Review,QuestionnaireBinding as Binding,QuestionnaireResponse as Response)
from .questionnaire_schema import questions,answers,digest,LEGACY_QUESTIONS,LEGACY_NAME


@contextmanager
def writing(db):
    if not db.info.get('_care_authority'):raise HTTPException(403,'缺少原客户服务权限')
    previous=db.info.get('_questionnaire_write');db.info['_questionnaire_write']=True
    try:
        yield
        db.flush()
    finally:
        if previous is None:db.info.pop('_questionnaire_write',None)
        else:db.info['_questionnaire_write']=previous


def policy(db,*,create=False,lock=False):
    query=select(Policy)
    if lock:query=query.with_for_update()
    row=db.scalar(query)
    if not row and create:
        row=Policy();db.add(row);db.flush()
    return row


def catalog(db,user):
    from .customer_service import authority,MANAGE
    with authority(db,user):
        head=policy(db);active=db.scalar(select(Version).where(Version.id==head.active_version_id)) if head and head.active_version_id else None
        reviews={r.version_id:r for r in db.scalars(select(Review))}
        rows=[]
        for row in db.scalars(select(Version).order_by(Version.number.desc()).limit(200)):
            review=reviews.get(row.id);value=plain(row)
            value.update(review=plain(review) if review else None,active=head.active_version_id==row.id if head else False,
                can_review=user.role in MANAGE and row.proposed_by!=user.id and not review,
                state='active' if head and head.active_version_id==row.id else 'superseded' if review and review.decision=='approve' else 'rejected' if review else 'pending')
            rows.append(value)
        return {'policy_version':head.version if head else 0,'active_version_id':head.active_version_id if head else None,
            'active_number':active.number if active else 1,
            'active_questions':deepcopy(active.questions if active else LEGACY_QUESTIONS),'active_name':active.name if active else LEGACY_NAME,
            'legacy':{'number':1,'name':LEGACY_NAME,'questions':deepcopy(LEGACY_QUESTIONS)},
            'items':rows,'can_manage':user.role in MANAGE,
            'notice':'新问卷须独立复核；仅后续发放采用新题，已经发出的问卷和旧答案不改写。最多显示最近200份版本。'}


def propose(db,user,key,v):
    from .customer_service import _execute,MANAGE
    try:schema=questions(v['questions'])
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    def op(sid):
        with writing(db):
            head=policy(db,lock=True)
            if v['policy_version']!=(head.version if head else 0):raise HTTPException(409,'问卷版本目录已变化，请刷新后登记')
            head=head or policy(db,create=True)
            row=Version(number=head.next_number,name=v['name'],questions=schema,digest=digest(schema),reason=v['reason'],proposed_by=user.id)
            head.next_number+=1;head.updated_at=utcnow();db.add(row);db.flush()
            audit(db,user.id,'questionnaire_propose','questionnaire_version',row.id,after={'number':row.number,'digest':row.digest},reason=v['reason'])
        return {'questionnaire_version':plain(row),'policy_version':head.version}
    return _execute(db,user,key,'questionnaire_propose',v,op,MANAGE)


def review(db,user,key,version_id,v):
    from .customer_service import _execute,MANAGE
    def op(sid):
        with writing(db):
            head=policy(db,lock=True)
            if not head or head.version!=v['policy_version']:raise HTTPException(409,'问卷发布状态已变化，请刷新独立核对')
            row=db.scalar(select(Version).where(Version.id==version_id))
            if not row:raise HTTPException(404,'本店问卷版本不存在')
            if row.proposed_by==user.id:raise HTTPException(403,'题目提出人不能复核自己的问卷版本')
            if db.scalar(select(Review.id).where(Review.version_id==row.id)):raise HTTPException(409,'该问卷版本已有独立处理记录')
            active=db.scalar(select(Version).where(Version.id==head.active_version_id)) if head.active_version_id else None
            if v['decision']=='approve' and active and row.number<=active.number:
                raise HTTPException(409,'不能重新发布早于当前版本的题目；请另提新版本')
            fact=Review(version_id=row.id,actor_id=user.id,actor_role=user.role,decision=v['decision'],
                previous_version_id=head.active_version_id,reason=v['reason'],schema_digest=row.digest)
            db.add(fact)
            if v['decision']=='approve':head.active_version_id=row.id
            head.updated_at=utcnow();db.flush()
            audit(db,user.id,'questionnaire_'+v['decision'],'questionnaire_version',row.id,
                after={'number':row.number,'digest':row.digest,'review_id':fact.id},reason=v['reason'])
        return {'questionnaire_version':plain(row),'review':plain(fact),'policy_version':head.version}
    return _execute(db,user,key,'questionnaire_review',{'version_id':version_id,**v},op,MANAGE)


def bind(db,user,row,care):
    if care.subtype!='questionnaire':return None
    with writing(db):
        # Serialize issuance against publication using the same original registry.
        head=policy(db,create=True,lock=True)
        current=db.scalar(select(Version).where(Version.id==head.active_version_id)) if head.active_version_id else None
        if head.active_version_id and (not current or not db.scalar(select(Review.id).where(Review.version_id==current.id,Review.decision=='approve'))):
            raise HTTPException(409,'当前问卷发布来源不完整，不能猜测题目发放')
        schema=deepcopy(current.questions if current else LEGACY_QUESTIONS)
        fact=Binding(case_id=row.id,version_id=current.id if current else None,
            number=current.number if current else 1,name=current.name if current else LEGACY_NAME,
            questions=schema,schema_digest=digest(schema),issued_at=utcnow(),origin='runtime')
        db.add(fact);db.flush()
        row.data={**row.data,'questionnaire_version':fact.number,'questionnaire_binding_id':fact.id,'questionnaire_schema_digest':fact.schema_digest}
        db.flush()
    return fact


def binding(db,row):
    result=db.scalar(select(Binding).where(Binding.case_id==row.id))
    if not result:raise HTTPException(409,'原发放题目绑定缺失，请先核对完整升级与来源，不能套用当前新题')
    return result


def info(db,row):
    fact=binding(db,row);response=db.scalar(select(Response).where(Response.binding_id==fact.id))
    return {'binding_id':fact.id,'version_id':fact.version_id,'number':fact.number,'name':fact.name,
        'questions':deepcopy(fact.questions),'issued_at':fact.issued_at.isoformat(),'schema_digest':fact.schema_digest,
        'response':plain(response) if response else None}


def normalize_close(db,row,care,v):
    if care.subtype!='questionnaire':
        if v.get('answers') is not None or v.get('satisfaction') is not None or v.get('recommend') is not None:
            raise HTTPException(422,'问卷回答只适用于客户问卷')
        return v,None
    fact=binding(db,row)
    legacy={key:v[key] for key in ('satisfaction','recommend') if v.get(key) is not None}
    if v.get('answers') is not None and legacy:raise HTTPException(422,'不要同时提交旧字段和按题编号的答案')
    if legacy and fact.version_id is not None:raise HTTPException(422,'新问卷请按本次发放版本逐题填写，不使用旧版快捷字段')
    value=v.get('answers') if v.get('answers') is not None else legacy
    try:normalized=answers(fact.questions,value,completed=v['result']=='resolved')
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    details={**v,'answers':normalized,'questionnaire_binding_id':fact.id,
        'questionnaire_version':fact.number,'questionnaire_schema_digest':fact.schema_digest}
    return details,fact


def record_response(db,user,fact,record,v):
    if fact is None:return
    with writing(db):
        db.flush()  # The native close CareRecord is the immutable source.
        value=v['answers']
        frozen={'binding_id':fact.id,'record_id':record.id,'schema_digest':fact.schema_digest,'answers':value}
        db.add(Response(binding_id=fact.id,record_id=record.id,answers=deepcopy(value),digest=digest(frozen),
            actor_id=user.id,origin='runtime'))
