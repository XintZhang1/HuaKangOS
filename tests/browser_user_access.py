"""Two administrators' real browser forms compete on a synthetic employee."""
import secrets,subprocess,sys
from playwright.sync_api import expect
import browser_huakangos as harness
from browser_masters import employee_login,take_screenshot


def initialize_database(env,work):
    """UI fixture only; migration-chain validation is deliberately separate."""
    script='''
import os
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import User,UserStore,Store
from app.security import hash_password
Base.metadata.create_all(engine)
with SessionLocal() as db:
    db.add(Store(id=1,code='ACCESS-A',name='合成授权甲店'));db.flush()
    user=User(username='admin',display_name='合成管理员',role='admin',must_change_password=False,
        password_hash=hash_password(os.environ['HUAKANGOS_INITIAL_PASSWORD']))
    db.add(user);db.flush();db.add(UserStore(user_id=user.id,store_id=1));db.commit()
'''
    return subprocess.run([sys.executable,'-X','utf8','-c',script],cwd=harness.ROOT,env=env,
                          capture_output=True,text=True,encoding='utf-8')


def exercise(browser,base,password,output):
    contexts=[];errors=[];steps=[];images=[];req=harness.checked_request
    def page():
        context=browser.new_context(viewport={'width':390,'height':844},locale='zh-CN')
        contexts.append(context);p=context.new_page();p.on('pageerror',lambda e:errors.append(str(e)));return p
    first,second,employee=page(),page(),page()
    try:
        harness.login_page(first,base,'admin',password)
        two=req(first,'/api/stores','POST',{'code':'ACCESS-B','name':'合成授权乙店','active':True},status=201)['id']
        initial=secrets.token_urlsafe(28)
        req(first,'/api/users','POST',{'username':'access-admin-two','display_name':'合成第二管理员','role':'admin','password':initial},status=201)
        employee_login(second,base,'access-admin-two',initial)
        initial=secrets.token_urlsafe(28)
        staff=req(first,'/api/users','POST',{'username':'access-staff','display_name':'合成两店员工','role':'sales',
            'password':initial,'can_group_summary':True,'store_roles':[{'store_id':1,'role':'manager'},{'store_id':two,'role':'finance'}]},status=201)
        employee_password=employee_login(employee,base,'access-staff',initial)
        assert req(employee,'/api/auth/me')['can_group_summary']
        for admin in (first,second):
            harness.navigate(admin,'users','员工账号')
            admin.locator('[data-act=edituser][data-id="'+str(staff['id'])+'"]').click()
        expect(second.locator('#modal [name=can_group_summary]')).to_be_checked()
        expect(second.locator('#modal [name=store_ids][value="'+str(two)+'"]')).to_be_checked()
        sent=[]
        first.on('request',lambda r:sent.append(r.post_data_json) if r.method=='PUT' and r.url.endswith('/api/users/'+str(staff['id'])) else None)
        first.locator('#modal [name=store_ids][value="'+str(two)+'"]').uncheck()
        first.locator('#modal [name=store_role_1]').select_option('sales')
        first.locator('#modal [name=can_group_summary]').uncheck()
        harness.save_modal(first)
        assert len(sent)==1 and sent[0]['access_version']==staff['access_version'] and sent[0]['request_id']
        assert harness.request(employee,'/api/auth/me')['status']==401
        second.locator('#modal [name=display_name]').fill('旧页面不应覆盖')
        second.locator('#modal button[type=submit]').click()
        expect(second.locator('#modal .formerror')).to_contain_text('刷新员工列表')
        second.locator('#modal .formerror').scroll_into_view_if_needed()
        harness.assert_fits_mobile(second);images.append(take_screenshot(second,output,'01_access_stale_refused.png'))
        current=next(u for u in req(first,'/api/users')['items'] if u['id']==staff['id'])
        assert current['store_ids']==[1] and not current['can_group_summary'] and current['display_name']=='合成两店员工'
        steps.append('两位管理员同时打开员工表单；第一位撤销乙店和汇总权限，第二位旧页保存遭中文拒绝')
        second.locator('#modal .modalhead [data-act=close]').click()
        second.locator('[data-act=open][data-route=users]').click()
        expect(second.locator('tr').filter(has=second.locator('[data-act=edituser][data-id="'+str(staff['id'])+'"]'))).not_to_contain_text('合成授权乙店')
        second.locator('[data-act=edituser][data-id="'+str(staff['id'])+'"]').click()
        expect(second.locator('#modal [name=can_group_summary]')).not_to_be_checked()
        expect(second.locator('#modal [name=store_ids][value="'+str(two)+'"]')).not_to_be_checked()
        second.locator('#modal [name=display_name]').fill('合成已核对员工');harness.save_modal(second)
        harness.assert_fits_mobile(second);images.append(take_screenshot(second,output,'02_access_latest_review.png'))
        steps.append('管理员关闭旧窗口，使用刷新员工列表重新核对最新授权，只修改姓名后成功保存')
        harness.login_page(employee,base,'access-staff',employee_password)
        me=req(employee,'/api/auth/me');assert me['role']=='sales' and not me['can_group_summary']
        expect(employee.locator('#store option')).to_have_count(1)
        assert harness.request(employee,'/api/users')['status']==403
        assert harness.request(employee,'/api/auth/me',store=two)['status']==403
        replay=req(first,'/api/users/'+str(staff['id']),'PUT',sent[0])
        assert replay['access_version']==staff['access_version']+1
        assert req(employee,'/api/auth/me')['display_name']=='合成已核对员工'
        harness.assert_fits_mobile(employee);images.append(take_screenshot(employee,output,'03_access_employee_relogin.png'))
        steps.append('员工原会话失效，重新登录只见仍获权门店；重复原请求不再次改权或撤销新会话')
        assert not errors,errors
        return {'passed':True,'mode':'real Chrome HTTP','database_setup':'independent synthetic metadata; this run does not validate the full migration chain',
            'roles':['admin','admin','sales'],'steps':steps,'screenshots':images,'javascript_errors':errors}
    finally:
        for context in contexts:context.close()


if __name__=='__main__':
    harness.initialize_database=initialize_database;harness.exercise=exercise;harness.main()
