"""Read-only SQLite proof and resource reconstruction for explicit reception v4."""
import json

def validate(connection):
    names={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'intake_appointments' not in names:return {'verified_service_intakes':0,'verified_rework_requests':0,'verified_resource_uses':0}
    def rows(name):
        cursor=connection.execute('SELECT * FROM '+name);columns=[r[0] for r in cursor.description]
        return [dict(zip(columns,r)) for r in cursor]
    def by(name,key='id'):return {r[key]:r for r in rows(name)}
    def fail(message):raise ValueError('维修接待恢复检查：'+message)
    cases=by('flow_cases');vehicles=by('care_customer_vehicles');resources=by('intake_resources');files=by('flow_files')
    quotes=by('repair_quotes');lines=by('repair_lines');settlements=by('repair_settlements','case_id');appointments=by('intake_appointments')
    arrivals=by('intake_arrivals','appointment_id');bindings=by('intake_vehicle_bindings','case_id');contexts=by('intake_repair_contexts','case_id')
    reworks=by('intake_rework_requests');liabilities=by('intake_rework_liabilities','request_id');events=rows('flow_events')
    from .rework_extension_integrity import validate as validate_extensions
    extension_counts=validate_extensions(connection)
    extensions=by('rework_extensions','request_id') if 'rework_extensions' in names else {}
    def same(a,b):return a and b and a['store_id']==b['store_id']
    def case(key,record,kind=None,version=None):
        row=cases.get(key)
        if not same(row,record) or (kind and row['kind']!=kind) or (version and row['flow_version']!=version):fail('原业务、门店或流程版本不一致')
        return row
    def data(row):return json.loads(row['data'])
    def proof(file_id,row):
        f=files.get(file_id)
        if not same(f,row) or f['case_id']!=row['id'] or f['generated']:fail('核验凭据没有关联正确原业务')
        return f
    def vehicle_binding(binding,row):
        v=vehicles.get(binding['customer_vehicle_id'])
        if not same(binding,row) or not same(v,row) or v['customer_id']!=row['customer_id'] or any(binding[k]!=v[k] for k in ('vin','customer_identity_id','vehicle_identity_id')):fail('不可变客户、VIN或共享身份绑定不一致')
    for a in appointments.values():
        row=case(a['case_id'],a,'service_intake',2);v=vehicles.get(a['customer_vehicle_id']);resource=resources.get(a['resource_id'])
        if not same(v,a) or row['customer_id']!=v['customer_id'] or not same(resource,a) or a['starts_at']>=a['ends_at']:fail('预约客户车辆、工位或时段不一致')
        arrival=arrivals.get(a['id'])
        if arrival:
            if not same(arrival,a) or arrival['customer_vehicle_id']!=v['id'] or arrival['checked_vin']!=v['vin']:fail('实际到店的客户车辆或VIN不一致')
            proof(arrival['evidence_id'],row)
        if (a['status'] in {'arrived','converted'} and not arrival) or (a['status'] in {'scheduled','no_show'} and arrival):fail('预约状态缺少或伪造实际到店')
        if a['repair_case_id']:
            ctx=contexts.get(a['repair_case_id'])
            if a['status']!='converted' or not ctx or ctx['appointment_id']!=a['id']:fail('预约与唯一转单上下文不一致')
        elif a['status']=='converted':fail('已转单预约缺少实际维修')
        if a['status']=='cancelled' and arrival:
            departures=[e for e in events if e['case_id']==row['id'] and e['action']=='intake_leave']
            if len(departures)!=1:fail('已到店取消缺少明确离场记录')
            proof(json.loads(departures[0]['detail'])['evidence_id'],row)
    for key,binding in bindings.items():
        row=case(key,binding,'repair');vehicle_binding(binding,row)
        if row['flow_version']==3:proof(binding['evidence_id'],row)
        elif row['flow_version']!=4:fail('旧流程绑定不得自动推断为新维修')
    for row in cases.values():
        if row['kind']=='repair' and row['flow_version']==4 and row['id'] not in contexts:fail('新维修缺少冻结接待来源')
    for key,ctx in contexts.items():
        row=case(key,ctx,'repair',4);binding=bindings.get(key);resource=resources.get(ctx['resource_id'])
        if not binding or not same(resource,ctx):fail('维修缺少冻结车辆或本店工位')
        vehicle_binding(binding,row)
        if ctx['appointment_id']:
            a=appointments.get(ctx['appointment_id']);arrival=arrivals.get(ctx['appointment_id'])
            if not same(a,ctx) or a['repair_case_id']!=key or not arrival or ctx['rework_id'] or ctx['profile']=='rework' or binding['evidence_id']!=arrival['evidence_id'] or ctx['resource_id']!=a['resource_id'] or ctx['preset_id']!=a['preset_id']:fail('到店转单与原凭据或资源不一致')
            proof(binding['evidence_id'],cases[a['case_id']])
        else:
            r=reworks.get(ctx['rework_id'])
            if not same(r,ctx) or r['repair_case_id']!=key or ctx['profile']!='rework' or ctx['resource_id']!=r['resource_id']:fail('责任返修转单与来源不一致')
            proof(binding['evidence_id'],cases[r['case_id']])
    for authorization in rows('repair_authorizations'):
        q=quotes.get(authorization['quote_id'])
        if not q:fail('客户授权缺少报价版本')
        if q['case_id'] not in contexts:continue
        row=cases[q['case_id']];f=proof(authorization['evidence_id'],row)
        if not same(authorization,row) or f['category']!='authorization' or authorization['quote_digest']!=q['digest']:fail('客户授权类别或绑定版本摘要不一致')
    source_lines=rows('intake_rework_source_lines');allocations=rows('repair_allocations');payments=rows('flow_payment_links')
    for r in reworks.values():
        extension=extensions.get(r['id'])
        row=case(r['case_id'],r,'service_intake',2);source=cases.get(r['source_case_id']) if extension else case(r['source_case_id'],r,'repair');settlement=settlements.get(source['id']);binding=bindings.get(source['id']);v=vehicles.get(r['customer_vehicle_id'])
        if source['flow_version'] not in (3,4) or not data(source).get('released_date') or not settlement or settlement['quote_id']!=r['source_quote_id'] or not binding or not same(v,r):fail('责任原单缺少已交车结算及车辆核验事实')
        if row['customer_id']!=v['customer_id'] or (not extension and source['customer_id']!=v['customer_id']) or any(binding[k]!=v[k] for k in ('vin','customer_identity_id','vehicle_identity_id')):fail('返修原单客户或VIN不一致')
        selected=[l for l in source_lines if l['request_id']==r['id']]
        if not selected or any(not same(l,r) or l['source_line_id'] not in lines or lines[l['source_line_id']]['quote_id']!=r['source_quote_id'] for l in selected):fail('责任项目并非原单冻结结算行')
        if r['active_source_id']!=(r['source_case_id'] if r['status'] in ('requested','approved','converted') else None):fail('原单未结返修占用与状态不一致')
        liability=liabilities.get(r['id'])
        if r['status'] in ('approved','converted','completed') and not liability:fail('内部责任缺少批准')
        if liability:
            if not same(liability,r) or r['approved_by']!=liability['approved_by']:fail('责任批准人与冻结记录不一致')
            proof(liability['evidence_id'],row)
            approved=[e for e in events if e['case_id']==row['id'] and e['action']=='intake_rework_approve']
            if len(approved)!=1 or json.loads(approved[0]['detail']).get('internal_name')!=liability['internal_name']:fail('内部承担主体与批准事实不一致')
        if r['repair_case_id']:
            repair=case(r['repair_case_id'],r,'repair',4);ctx=contexts.get(repair['id'])
            if not liability or not ctx or ctx['rework_id']!=r['id']:fail('责任返修缺少唯一已批来源')
            if r['status']=='completed' and not data(repair).get('released_date'):fail('返修尚未实际交车却已结束')
            if r['status']=='cancelled' and repair['state']!='cancelled':fail('实际返修与申请取消不一致')
            if repair['id'] in settlements and not extension:
                own=[a for a in allocations if a['case_id']==repair['id']]
                if sum(a['amount_cents'] for a in own)!=repair['amount_cents'] or any(a['payer_type']!='internal' or a['payer_name']!=liability['internal_name'] or not same(a,repair) for a in own):fail('责任返修未全额计入已批准内部承担')
            if not extension and any(p['case_id']==repair['id'] for p in payments):fail('内部责任返修不得复制原款或增加客户现金')
            for table in ('group_payment_links','benefit_payment_links'):
                if not extension and table in names and connection.execute('SELECT 1 FROM '+table+' WHERE case_id=? LIMIT 1',(repair['id'],)).fetchone():fail('内部责任返修不得消费客户集团款项或权益')
    uses=sorted(rows('intake_resource_uses'),key=lambda u:u['id']);occupied={};vin_occupied={}
    for use in uses:
        row=case(use['case_id'],use,'repair',4);ctx=contexts.get(row['id']);resource=resources.get(use['resource_id']);binding=bindings.get(row['id'])
        if not ctx or not binding or not same(resource,use) or ctx['resource_id']!=resource['id']:fail('实际工位记录与冻结维修不一致')
        if use['evidence_id']:proof(use['evidence_id'],row)
        vin=(row['store_id'],binding['vin'])
        if use['action']=='acquire':
            if occupied.get(resource['id']) or vin in vin_occupied:fail('实际工位或同VIN重复占用')
            occupied[resource['id']]=row['id'];vin_occupied[vin]=row['id']
        elif use['action']=='release':
            if occupied.get(resource['id'])!=row['id'] or vin_occupied.get(vin)!=row['id']:fail('实际释放没有对应本车进位')
            occupied.pop(resource['id']);vin_occupied.pop(vin)
        else:fail('未知实际工位动作')
    for resource in resources.values():
        if resource['active_case_id']!=occupied.get(resource['id']):fail('工位当前占用与不可变进出位记录不一致')
    return {'verified_service_intakes':len(appointments),'verified_rework_requests':len(reworks),'verified_resource_uses':len(uses),**extension_counts}
