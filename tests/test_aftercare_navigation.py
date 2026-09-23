"""Original work pages use the same stop guard and scoped aftercare relation."""
from tests.conftest import login
from tests.test_workflow import order,action,detail
from tests.test_aftercare import create,cmd


def test_original_actions_pause_and_resume_without_exposing_unassigned_aftercare(client):
    login(client,'sales');source=order(client,'100.00')
    login(client);source=action(client,source,'approve')
    assert next(a for a in detail(client,source)['actions'] if a['key']=='allocate')['enabled']
    after=create(client,source,'sale_termination')
    original=detail(client,source)
    assert [(r['id'],r['number'],r['state']) for r in original['aftercare_links']]==[(after['id'],after['number'],'pending')]
    assert original['actions'] and not any(a['enabled'] for a in original['actions'])
    assert '售后' in next(a for a in original['actions'] if a['key']=='allocate')['reason']
    login(client,'sales')
    assert detail(client,source)['aftercare_links']==[]
    assert client.get('/api/aftercare/orders/'+str(after['id'])).status_code==404
    login(client);cmd(client,after,'cancel',{'reason':'客户撤销尚未执行的售后申请'})
    original=detail(client,source)
    assert next(a for a in original['actions'] if a['key']=='allocate')['enabled']
    assert original['aftercare_links'][0]['state']=='cancelled'
