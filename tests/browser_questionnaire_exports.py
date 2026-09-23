"""Real employee Chrome downloads for original-question charts; synthetic data only.

Run: python tests/browser_questionnaire_exports.py --screenshots OUTSIDE_REPOSITORY
The shared harness owns a temporary database/server and never uses a HTTP bridge.
"""
import csv
import hashlib
import io
import secrets

from playwright.sync_api import expect

import browser_huakangos as harness
from browser_masters import employee_login

API='/api/customer-service'
QUESTIONS=[
    {'key':'wait_minutes','label':'实际等候分钟数','kind':'integer','required':True,'min_value':0,'max_value':600},
    {'key':'first_visit','label':'是否首次到店','kind':'boolean','required':True},
    {'key':'suggestion','label':'其他建议','kind':'text','required':False,'max_length':200},
]


def post(page,path,values,status=200,version=None):
    body={'request_id':secrets.token_hex(16),'values':values}
    if version is not None:body['version']=version
    return harness.checked_request(page,API+path,'POST',body,status=status)


def publish(admin,reviewer,name):
    catalog=harness.checked_request(admin,API+'/questionnaires/versions')
    proposed=post(admin,'/questionnaires/versions',{'policy_version':catalog['policy_version'],
        'name':name,'questions':QUESTIONS,'reason':'合成验收：本次明确的原题版本'},201)['questionnaire_version']
    catalog=harness.checked_request(reviewer,API+'/questionnaires/versions')
    post(reviewer,f'/questionnaires/versions/{proposed["id"]}/review',{'policy_version':catalog['policy_version'],
        'decision':'approve','reason':'合成验收：另一主管独立逐题核对','confirmed':True})


def completed(admin,employee,customer,assignee,answers,legacy=False,partial=False):
    due=admin.evaluate('()=>day()')
    row=post(admin,'/cases',{'customer_id':customer,'subtype':'questionnaire','topic':'虚构本次到店反馈',
        'description':'仅为真实浏览器验收创建的合成问卷','due_date':due,'assignee_id':assignee},201)['case']
    row=post(employee,f'/cases/{row["id"]}/actions/start',{},version=row['version'])['case']
    values={'result':'declined' if partial else 'resolved','note':'合成客服按本次发放原题记录实际回答'}
    values.update(answers if legacy else {'answers':answers})
    return post(employee,f'/cases/{row["id"]}/actions/close',values,version=row['version'])['case']


def download_and_check(page,button,path,table,rows):
    with page.expect_download() as waiting:button.click()
    download=waiting.value
    assert download.failure() is None
    download.save_as(str(path));content=path.read_bytes()
    expected=io.StringIO(newline='');writer=csv.writer(expected)
    writer.writerow(table['headers']);writer.writerows(row['values'] for row in rows)
    assert content==('\ufeff'+expected.getvalue()).encode('utf-8')
    return {'path':str(path),'sha256':hashlib.sha256(content).hexdigest(),'data_rows':len(rows),
        'parsed_rows':list(csv.reader(io.StringIO(content.decode('utf-8-sig'))))}


def exercise(browser,base,password,output):
    sources=['app/questionnaire_analytics.py','app/customer_service_api.py','web/customerservice.js',
        'web/app.js','web/index.html','tests/browser_questionnaire_exports.py','tests/browser_huakangos.py']
    fingerprint=lambda:{name:hashlib.sha256((harness.ROOT/name).read_bytes()).hexdigest() for name in sources}
    before=fingerprint()
    contexts=[browser.new_context(viewport={'width':1440,'height':1000},locale='zh-CN',accept_downloads=True) for _ in range(3)]
    errors=[];screens=[];steps=[];downloads=[]
    for context in contexts:context.on('page',lambda page:page.on('pageerror',lambda error:errors.append(str(error))))
    admin,reviewer,employee=[context.new_page() for context in contexts]
    try:
        harness.login_page(admin,base,'admin',password)
        staff={}
        for page,username,role in [(reviewer,'question-reviewer','manager'),(employee,'question-clerk','customer_service')]:
            initial=secrets.token_urlsafe(28)
            staff[role]=harness.checked_request(admin,'/api/users','POST',{'username':username,
                'display_name':'合成问卷'+role,'role':role,'password':initial,'store_roles':[{'store_id':1,'role':role}]},status=201)['id']
            employee_login(page,base,username,initial)
        customer=harness.checked_request(admin,'/api/flow/master/customers','POST',
            {'values':{'name':'虚构问卷客户','phone':'','contact_allowed':False}},status=201)['id']
        completed(admin,employee,customer,staff['customer_service'],{'satisfaction':4,'recommend':False},legacy=True)
        publish(admin,reviewer,'合成到店调查第二版')
        completed(admin,employee,customer,staff['customer_service'],{'wait_minutes':0,'first_visit':False})
        completed(admin,employee,customer,staff['customer_service'],{},partial=True)
        publish(admin,reviewer,'合成到店调查第三版')
        completed(admin,employee,customer,staff['customer_service'],{'wait_minutes':7,'first_visit':True})
        steps.append('独立主管批准两个后续版本，客服记录原v1与v2/v3答案，包含0、否和未回答')

        data=harness.checked_request(employee,API+'/questionnaires/report')
        assert data['metrics']['questionnaires_closed']==4
        harness.navigate(employee,'customer-questionnaire-report','原题问卷统计')
        expect(employee.locator('.identity .role')).to_have_text('客户服务')
        employee.set_viewport_size({'width':390,'height':844})
        for key in ['first_visit','wait_minutes']:
            chart=next(c for c in data['charts'] if c['id']=='questionnaire_2_'+key)
            filters=chart['table_filters']
            matches=lambda row:all(row.get(k)==v for k,v in filters.items())
            distribution=data['tables'][chart['table']];answers=data['tables']['questionnaire_answers']
            rows=[row for row in distribution['rows'] if matches(row)]
            originals=[row for row in answers['rows'] if matches(row)]
            assert sum(chart['series'][0]['values'])==len(originals)==2
            button=employee.locator(f'[data-act="care-q-export"][data-key="questionnaire_distribution"][data-version-number="2"][data-question-key="{key}"]')
            panel=button.locator('xpath=ancestor::section[contains(@class,"panel")][1]')
            expect(panel.locator('svg')).to_be_visible()
            panel.locator('summary').click()
            details=panel.locator('details');expect(details).to_be_visible()
            visible=details.locator('table tbody tr').all_inner_texts()
            assert len(visible)==len(rows)+len(originals)
            expect(details).to_contain_text('未回答')
            if key=='first_visit':expect(details).to_contain_text('否')
            else:expect(details).to_contain_text('0')
            harness.assert_fits_mobile(employee)
            downloads.append(download_and_check(employee,button,output/f'{key}_distribution.csv',distribution,rows))
            downloads.append(download_and_check(employee,details.locator('[data-act="care-q-export"]'),
                output/f'{key}_answers.csv',answers,originals))
            panel.scroll_into_view_if_needed();path=output/f'question_{key}_390px.png'
            employee.screenshot(path=str(path));screens.append(str(path))
        steps.append('390px客服页面实际展开单题明细并下载：同题的图、明细、CSV逐字节一致，其他版本和题目不混入')

        table=data['tables']['questionnaire_distribution']
        whole=employee.locator('[data-act="care-q-export"][data-key="questionnaire_distribution"]:not([data-version-number])')
        downloads.append(download_and_check(employee,whole,output/'whole_distribution.csv',table,table['rows']))
        assert downloads[-1]['data_rows']>downloads[0]['data_rows']
        steps.append('整表下载仍包含全部获权题目，与单题按钮的范围明确不同')

        button=employee.locator('[data-act="care-q-export"][data-key="questionnaire_distribution"][data-version-number="2"][data-question-key="first_visit"]')
        original=button.get_attribute('data-schema-digest')
        # Simulate an incomplete link in the actual page; no fallback download is allowed.
        button.evaluate("el=>el.removeAttribute('data-schema-digest')")
        button.click();expect(employee.locator('#toast')).to_contain_text('单题筛选须同时填写问卷版本、原题摘要和题目编号')
        path=output/'incomplete_selector_chinese_390px.png';employee.screenshot(path=str(path));screens.append(str(path))
        button.evaluate('(el,value)=>el.setAttribute("data-schema-digest",value)',original)
        steps.append('真实页面缺少原题摘要的下载请求得到中文拒绝，不退回全表')
        assert not errors,errors
        return {'mode':'real Chrome HTTP, 390px customer_service account, no bridge','passed':len(steps),
            'steps':steps,'downloads':downloads,'screenshots':screens,'javascript_errors':errors,
            'source_hashes':before,'source_unchanged':fingerprint()==before,
            'limitations':['全部为隔离库合成记录，未触碰公司业务库或附件','本地HTTP不代替生产HTTPS及公司业务验收']}
    except Exception:
        path=output/'failure_questionnaire.png';employee.screenshot(path=str(path),full_page=True)
        raise
    finally:
        for context in contexts:context.close()


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
