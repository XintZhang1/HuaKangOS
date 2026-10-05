"""Backup relationship checks for assistant plans; no business state modifications."""
import json


def validate(connection):
    # Validate the Runtime schema before legacy parsing, so an incomplete h53k
    # backup cannot be mistaken for a database without the new feature.
    from .assistant_runtime_integrity import validate as validate_runtime, _names, _columns, _execute
    runtime = validate_runtime(connection)
    names=_names(connection)
    if 'business_assistant_work_plans' not in names:return {**runtime,'assistant_work_plans':0}
    mismatch=_execute(connection,'''SELECT p.id FROM business_assistant_work_plans p
        LEFT JOIN business_assistant_sessions s ON s.id=p.session_id
        WHERE s.id IS NULL OR p.store_id!=s.store_id OR p.owner_id!=s.owner_id LIMIT 1''').fetchone()
    if mismatch:raise ValueError('助手计划与所属员工、门店或对话不一致')
    count=0
    columns=_columns(connection,'business_assistant_work_plans')
    engine_column='engine_version' if 'engine_version' in columns else '1'
    steps_column=('CAST(steps AS TEXT)' if getattr(getattr(connection,'dialect',None),'name',None)=='postgresql' else 'steps')
    for session_id,store_id,owner_id,raw,engine_version in _execute(connection,
            'SELECT session_id,store_id,owner_id,'+steps_column+','+engine_column+' FROM business_assistant_work_plans'):
        if engine_version == 2:
            # Only normalized PlanStep rows are the v2 graph. Its retained JSON
            # is a historical snapshot, already superseded by that graph.
            count+=1
            continue
        if engine_version != 1:
            raise ValueError('助手计划引擎版本无效')
        from .business_assistant_business_tools import WorkStep
        from .business_assistant_workboard import validate_graph
        try:
            steps=json.loads(raw)
            if not isinstance(steps,list) or not 1<=len(steps)<=200:raise ValueError()
            steps=[WorkStep.model_validate(x).model_dump() for x in steps];validate_graph(steps)
        except Exception:raise ValueError('助手计划的结构或依赖关系不完整') from None
        for step in steps:
            ident=step.get('proposal_id')
            if ident:
                row=_execute(connection,'SELECT session_id,store_id,owner_id FROM business_assistant_proposals WHERE id=:proposal_id',{'proposal_id':ident}).fetchone()
                if not row or tuple(row)!=(session_id,store_id,owner_id):raise ValueError('助手计划草稿引用跨越对话、员工或门店')
        count+=1
    return {**runtime,'assistant_work_plans':count}
