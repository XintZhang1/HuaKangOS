"""Publish immutable question versions and bind issued legacy v1 without rewriting it."""
from datetime import datetime,timezone
import hashlib,json
from alembic import op
import sqlalchemy as sa

revision='p68c_questionnaire_versions'
down_revision='o57b_found_transit_searches'
branch_labels=None
depends_on=None

# Frozen migration contract. Never import a future application question template.
LEGACY=[{'key':'satisfaction','label':'本次服务满意度','kind':'integer','required':True,'min_value':1,'max_value':5,'max_length':None,'choices':[]},
        {'key':'recommend','label':'是否愿意推荐','kind':'boolean','required':True,'min_value':None,'max_value':None,'max_length':None,'choices':[]}]
def _digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def _fact():return [sa.Column('id',sa.Integer(),primary_key=True,nullable=False),sa.Column('store_id',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False)]


def upgrade():
    op.create_table('care_questionnaire_versions',*_fact(),sa.Column('number',sa.Integer(),nullable=False),
        sa.Column('name',sa.String(120),nullable=False),sa.Column('questions',sa.JSON(),nullable=False),sa.Column('digest',sa.String(64),nullable=False),
        sa.Column('reason',sa.String(1000),nullable=False),sa.Column('proposed_by',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.UniqueConstraint('store_id','number',name='uq_questionnaire_store_number'),sa.CheckConstraint('number>=2',name='ck_questionnaire_number'))
    op.create_table('care_questionnaire_policies',*_fact(),sa.Column('version',sa.Integer(),nullable=False),
        sa.Column('updated_at',sa.DateTime(),nullable=False),sa.Column('next_number',sa.Integer(),nullable=False),
        sa.Column('active_version_id',sa.Integer(),sa.ForeignKey('care_questionnaire_versions.id'),nullable=True),
        sa.UniqueConstraint('store_id',name='uq_questionnaire_policy_store'),sa.CheckConstraint('next_number>=2',name='ck_questionnaire_next_number'))
    op.create_table('care_questionnaire_reviews',*_fact(),sa.Column('version_id',sa.Integer(),sa.ForeignKey('care_questionnaire_versions.id'),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('actor_role',sa.String(20),nullable=False),
        sa.Column('decision',sa.String(12),nullable=False),sa.Column('previous_version_id',sa.Integer(),sa.ForeignKey('care_questionnaire_versions.id'),nullable=True),
        sa.Column('reason',sa.String(1000),nullable=False),sa.Column('schema_digest',sa.String(64),nullable=False),
        sa.UniqueConstraint('version_id'),sa.CheckConstraint("decision IN ('approve','reject') AND actor_role IN ('admin','manager')",name='ck_questionnaire_review'))
    op.create_table('care_questionnaire_bindings',*_fact(),sa.Column('case_id',sa.Integer(),sa.ForeignKey('care_cases.case_id'),nullable=False),
        sa.Column('version_id',sa.Integer(),sa.ForeignKey('care_questionnaire_versions.id'),nullable=True),sa.Column('number',sa.Integer(),nullable=False),
        sa.Column('name',sa.String(120),nullable=False),sa.Column('questions',sa.JSON(),nullable=False),sa.Column('schema_digest',sa.String(64),nullable=False),
        sa.Column('issued_at',sa.DateTime(),nullable=False),sa.Column('origin',sa.String(12),nullable=False),
        sa.UniqueConstraint('case_id',name='uq_questionnaire_binding_case'),sa.CheckConstraint("origin IN ('runtime','migration') AND ((version_id IS NULL AND number=1) OR (version_id IS NOT NULL AND number>=2))",name='ck_questionnaire_binding'))
    op.create_table('care_questionnaire_responses',*_fact(),sa.Column('binding_id',sa.Integer(),sa.ForeignKey('care_questionnaire_bindings.id'),nullable=False),
        sa.Column('record_id',sa.Integer(),sa.ForeignKey('care_records.id'),nullable=False),sa.Column('answers',sa.JSON(),nullable=False),sa.Column('digest',sa.String(64),nullable=False),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),sa.Column('origin',sa.String(12),nullable=False),
        sa.UniqueConstraint('binding_id'),sa.UniqueConstraint('record_id'),sa.CheckConstraint("origin IN ('runtime','migration')",name='ck_questionnaire_response_origin'))
    for table in ('care_questionnaire_policies','care_questionnaire_versions','care_questionnaire_reviews','care_questionnaire_bindings','care_questionnaire_responses'):
        op.create_index('ix_'+table+'_store_id',table,['store_id'])
    op.create_index('ix_care_questionnaire_bindings_case_id','care_questionnaire_bindings',['case_id'])
    connection=op.get_bind();metadata=sa.MetaData()
    cases=sa.Table('flow_cases',metadata,autoload_with=connection)
    cares=sa.Table('care_cases',metadata,autoload_with=connection)
    records=sa.Table('care_records',metadata,autoload_with=connection)
    bindings=sa.Table('care_questionnaire_bindings',metadata,autoload_with=connection)
    responses=sa.Table('care_questionnaire_responses',metadata,autoload_with=connection)
    policies=sa.Table('care_questionnaire_policies',metadata,autoload_with=connection)
    now=datetime.now(timezone.utc).replace(tzinfo=None);schema_hash=_digest(LEGACY);stores=set()
    query=sa.select(cases.c.id,cases.c.store_id,cases.c.kind,cases.c.data,cases.c.created_at,cases.c.state,
        cares.c.result,cares.c.store_id.label('care_store_id')).join(cares,cares.c.case_id==cases.c.id).where(cares.c.subtype=='questionnaire').order_by(cases.c.id)
    for index,row in enumerate(connection.execute(query).mappings(),1):
        if row['kind']!='customer_care' or row['store_id']!=row['care_store_id'] or (row['data'] or {}).get('questionnaire_version',1)!=1:
            raise RuntimeError('历史问卷类型、门店或版本不一致，请核对原库；不能猜测原题')
        stores.add(row['store_id'])
        binding_id=connection.execute(bindings.insert().values(store_id=row['store_id'],case_id=row['id'],version_id=None,
            number=1,name='客户服务问卷',questions=LEGACY,schema_digest=schema_hash,issued_at=row['created_at'],origin='migration',created_at=now)).inserted_primary_key[0]
        closed=list(connection.execute(sa.select(records).where(records.c.case_id==row['id'],records.c.action=='close')).mappings())
        if len(closed)!=(1 if row['state']=='completed' else 0):raise RuntimeError('历史问卷结案与原记录不一致，禁止空白回填')
        if closed:
            record=closed[0];details=record['details'] or {};answers={k:details[k] for k in ('satisfaction','recommend') if details.get(k) is not None}
            if record['store_id']!=row['store_id'] or details.get('result')!=row['result']:
                raise RuntimeError('历史问卷原回答门店或结果不一致')
            if 'satisfaction' in answers and (type(answers['satisfaction']) is not int or not 1<=answers['satisfaction']<=5):raise RuntimeError('历史满意度非有效整数')
            if 'recommend' in answers and type(answers['recommend']) is not bool:raise RuntimeError('历史推荐回答不是明确是非值')
            if row['result']=='resolved' and set(answers)!={'satisfaction','recommend'}:raise RuntimeError('历史已完成问卷缺少原回答，禁止捏造')
            frozen={'binding_id':binding_id,'record_id':record['id'],'schema_digest':schema_hash,'answers':answers}
            connection.execute(responses.insert().values(binding_id=binding_id,record_id=record['id'],store_id=row['store_id'],answers=answers,digest=_digest(frozen),actor_id=record['actor_id'],origin='migration',created_at=record['created_at']))
    for sid in sorted(stores):connection.execute(policies.insert().values(store_id=sid,version=1,next_number=2,active_version_id=None,created_at=now,updated_at=now))


def downgrade():
    raise RuntimeError('Issued questions and original responses require a reviewed consistent backup restore, not a destructive downgrade')
