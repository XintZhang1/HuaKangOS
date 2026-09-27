"""Server-derived labels for business-tool cards; immutable payload stays authoritative.

Only native form/chooser data enters this snapshot. It is not a model-supplied
summary, a business state, an authorization token, or a replacement for the digest.
"""
from copy import deepcopy


def snapshot(form,references):
    return {'label':form['label'],'labels':{f['key']:f['label'] for f in form['fields']},
            'references':references,'case_id':form.get('case_id'),'case_text':form.get('case_text','')}


def with_answers(presentation,questions,execution):
    if not presentation:return None
    result=deepcopy(presentation);values=(execution.get('body') or {}).get('values',{})
    result['filled_values']={q['key'].split('.',1)[1]:values[q['key'].split('.',1)[1]]
        for q in questions if q.get('key','').startswith('values.') and q['key'].split('.',1)[1] in values}
    for question in questions:
        key=question.get('key','').removeprefix('values.');value=values.get(key)
        for option in question.get('options',[]):
            if isinstance(option,dict) and value is not None and str(option.get('value'))==str(value):
                result['references'][key]={'value':value,'label':option['label']};break
    return result


def fields_for(row):
    from . import business_assistant_gateway as gateway
    p=(row.result or {}).get('business_presentation')
    if not isinstance(p,dict):return None
    payload=deepcopy(row.payload);body=payload.get('body',{});values=body.get('values',{})
    # On settled cards only, the recorded employee answers show the actual submission.
    if row.status!='pending':values.update(p.get('filled_values',{}))
    path=payload.get('path_args',{});result=[]
    if path.get('case_id')==p.get('case_id') and p.get('case_text'):
        result.append({'label':'关联原单','value':p['case_text']});path.pop('case_id',None)
    path.pop('action',None)
    if 'kind' in path:path.pop('kind');result.append({'label':'业务类型','value':p['label']})
    old_labels=gateway._field_labels(payload,row.operation_id)
    for key,value in values.items():
        native_label=p.get('labels',{}).get(key,key)
        ref=p.get('references',{}).get(key)
        if ref and ref.get('value')==value:
            values[key]=ref['label']
        old_labels[key]=native_label
    # Render each original value through the original unit/line renderer. Relabel
    # by keys before flattening, not by globally replacing repeated text.
    # Do not patch global render functions across concurrent requests. The renderer
    # accepts an explicit local labels projection instead.
    result.extend(gateway.display_fields(payload,row.operation_id,field_labels=old_labels))
    return result
