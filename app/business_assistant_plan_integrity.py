"""Backup relationship checks for assistant plans; no business state modifications."""
import json


def validate(connection):
    names={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'business_assistant_work_plans' not in names:return {'assistant_work_plans':0}
    mismatch=connection.execute('''SELECT p.id FROM business_assistant_work_plans p
        LEFT JOIN business_assistant_sessions s ON s.id=p.session_id
        WHERE s.id IS NULL OR p.store_id!=s.store_id OR p.owner_id!=s.owner_id LIMIT 1''').fetchone()
    if mismatch:raise ValueError('助手计划与所属员工、门店或对话不一致')
    count=0
    from .business_assistant_business_tools import WorkStep
    from .business_assistant_workboard import validate_graph
    for session_id,store_id,owner_id,raw in connection.execute('SELECT session_id,store_id,owner_id,steps FROM business_assistant_work_plans'):
        try:
            steps=json.loads(raw)
            if not isinstance(steps,list) or not 1<=len(steps)<=200:raise ValueError()
            steps=[WorkStep.model_validate(x).model_dump() for x in steps];validate_graph(steps)
        except Exception:raise ValueError('助手计划的结构或依赖关系不完整') from None
        for step in steps:
            ident=step.get('proposal_id')
            if ident:
                row=connection.execute('SELECT session_id,store_id,owner_id FROM business_assistant_proposals WHERE id=?',(ident,)).fetchone()
                if not row or tuple(row)!=(session_id,store_id,owner_id):raise ValueError('助手计划草稿引用跨越对话、员工或门店')
        count+=1
    return {'assistant_work_plans':count}
