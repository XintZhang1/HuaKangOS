"""历史遗留：登录限流身份识别的测试，**不参与本目录测试集**。

来源：仓库历史里的 DealerDesk 线分支（同一个仓库历史中存在对应实现 commit
「Stop using a shared address as a login-lockout identity」）。

为什么不能跑：它导入 `app.security` 的 `LOGIN_FAILURE_LIMIT`、`LOGIN_FAILURE_WINDOW`
与 `identifies_a_client`——这三个名称在 huakangos 线中都不存在。**重要**：本线当前实现是
「同一用户名 **或** 同一 IP 失败 10 次即锁 15 分钟」（`app/security.py` 的 `authenticate`），
也就是说本文件描述的那个「共享出口地址被当成身份 → 任一陌生人可锁死全店」的问题，
**在当前代码里依然存在**，只是没有对应测试。

处置（业主选择“标注历史遗留并移出测试集”，2026-09-24）：改名去掉 `test_` 前缀并移入
`tests/historical/`，作为资料与需求线索保留，不作为测试证据。

**业主决定（2026-09-24）：暂不移植。** 本文件仅作资料与需求线索保留；除非业主另行提出，不要再把它当作待办。

恢复条件（如需重启该提案）：把该改进正式移植进本线（只让全球可达的单播地址参与身份计数，并抽出可配置的
失败上限与窗口），同时补齐“成功登录不清零历史失败”“运营商大内网 100.64/10 不算身份”等
用例；这是一次有安全影响的行为变更，需要业主单独确认后再做，不能靠“让测试变绿”悄悄改。
"""
from datetime import timedelta
import pytest
from fastapi import HTTPException
from app.db import SessionLocal, utcnow
from app.models import LoginAttempt
from app.security import (LOGIN_FAILURE_LIMIT, LOGIN_FAILURE_WINDOW, authenticate,
                          identifies_a_client)

PASSWORD='TestingOnly!LongPassword2026'


@pytest.mark.parametrize('ip,expected',[
    # 全球可达的单播地址：可以代表某一个客户端
    ('8.133.192.159',True),('1.2.3.4',True),('8.8.8.8',True),('2001:4860:4860::8888',True),
    # 回环 / 内网 / 链路本地 / 未指定：容器与穿透场景下都会退化成同一个地址
    ('127.0.0.1',False),('::1',False),('172.17.0.1',False),('10.1.2.3',False),
    ('192.168.1.20',False),('169.254.1.1',False),('0.0.0.0',False),
    # 运营商大内网：成百上千人共用一个出口，同样不能当身份
    ('100.64.0.1',False),('100.127.255.254',False),
    # 文档段与保留段
    ('203.0.113.9',False),('192.0.2.5',False),('198.18.0.1',False),
    # 根本不是地址的字符串（TestClient 用的就是 'testclient'）
    ('testclient',False),('',False),('not-an-ip',False),('999.1.1.1',False),('8.133.192.159:8080',False),
])
def test_only_globally_reachable_addresses_identify_a_client(ip,expected):
    assert identifies_a_client(ip) is expected


def failures(count,username='admin',ip='172.17.0.1'):
    with SessionLocal() as db:
        for _ in range(count):
            db.add(LoginAttempt(username=username,ip=ip))
        db.commit()


def attempt(username='admin',password='wrong',ip='172.17.0.1'):
    with SessionLocal() as db:
        return authenticate(db,username,password,ip)


def test_shared_private_address_cannot_lock_out_other_accounts():
    """回归：这是穿透/反代场景下最危险的一条。

    别人失败 10 次，不能让一个毫无关系的账号（甚至用正确密码）登不进来。
    """
    failures(LOGIN_FAILURE_LIMIT,username='someone-else',ip='172.17.0.1')
    assert attempt('admin',PASSWORD,'172.17.0.1').username=='admin'


def test_public_address_lockout_still_works():
    """同一个公网地址上的暴力尝试仍然要被挡住。"""
    failures(LOGIN_FAILURE_LIMIT,username='someone-else',ip='1.2.3.4')
    with pytest.raises(HTTPException) as exc:
        attempt('admin',PASSWORD,'1.2.3.4')
    assert exc.value.status_code==429 and '当前网络' in exc.value.detail


def test_carrier_nat_address_does_not_lock_a_whole_subscriber_group():
    """100.64/10 是国内移动网络常见的运营商大内网出口，成百上千人共用。

    把它当身份，等于用一个陌生人的失败锁住一整片用户；当它不是身份，则退回到按账号计数。
    """
    failures(LOGIN_FAILURE_LIMIT,username='someone-else',ip='100.64.7.7')
    assert attempt('admin',PASSWORD,'100.64.7.7').username=='admin'


def test_per_account_lockout_works_from_a_shared_address():
    """按账号计数必须保留：否则穿透之后就完全没有暴力破解防护了。"""
    failures(LOGIN_FAILURE_LIMIT,username='admin',ip='172.17.0.1')
    with pytest.raises(HTTPException) as exc:
        attempt('admin',PASSWORD,'172.17.0.1')
    assert exc.value.status_code==429 and '该账号' in exc.value.detail


def test_other_accounts_are_unaffected_by_one_accounts_lockout():
    failures(LOGIN_FAILURE_LIMIT,username='admin',ip='172.17.0.1')
    assert attempt('manager',PASSWORD,'172.17.0.1').username=='manager'


def test_a_shared_address_never_accrues_a_network_wide_lock():
    """分散到 20 个不同用户名各失败 1 次，仍然不应该触发任何网络级锁定。"""
    with SessionLocal() as db:
        for index in range(20):
            db.add(LoginAttempt(username=f'user{index}',ip='172.17.0.1'))
        db.commit()
    assert attempt('admin',PASSWORD,'172.17.0.1').username=='admin'


def test_failures_older_than_the_window_do_not_count():
    with SessionLocal() as db:
        for _ in range(LOGIN_FAILURE_LIMIT):
            db.add(LoginAttempt(username='admin',ip='172.17.0.1',
                                occurred_at=utcnow()-LOGIN_FAILURE_WINDOW-timedelta(minutes=1)))
        db.commit()
    assert attempt('admin',PASSWORD,'172.17.0.1').username=='admin'


def test_a_failed_login_is_still_recorded_for_audit():
    with pytest.raises(HTTPException) as exc:
        attempt('nobody','wrong','172.17.0.1')
    assert exc.value.status_code==401
    with SessionLocal() as db:
        rows=list(db.query(LoginAttempt).filter(LoginAttempt.username=='nobody'))
    assert len(rows)==1 and rows[0].ip=='172.17.0.1'
