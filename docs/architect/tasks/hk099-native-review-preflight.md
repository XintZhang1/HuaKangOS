# HK099 同实例真实午夜：原生点击预检与代码草案

2026-10-01，只读准备。依据 `hk099-date-followup.md`；没有启动浏览器/app、执行 SQL、读取私有凭据或写入测试/共享文件。本页代码没有执行，不新增 passed。根决定是否将草案保存为当前外部实例的补充工具；执行性质应记为 `native_playwright_post_automatic_supplement`，与 IAB 人工点击/视觉评价分开。

## 启动条件及精确来源

保留一次完整默认 full53 的 `--review-after-tests` 原服务。原自动脚本在结束时已关闭其浏览器，不能复用不存在的自动 Page；后续可另建原生 Chrome context，连接同一 manifest.origin，不能新建业务服务、换库或用请求桥接代替页面。`run-summary.post_test_review.phase=awaiting_external_stop` 时 provider 最终记录尚未生成，须待正常停止再验。

启动前逐项核验：`browser-click-report.json` 的 complete/passed/full_registered_suite_complete=true、scope=full_registered、registered/executed/passed_count=53、failed=0；expected_scenarios 与 all_registered_scenarios 及实际唯一 id 集合完全一致，全部 status=passed。requirements_coverage.complete/passed=true 且 actual_counts 精确为 requirements_searched193/guides_displayed111/page_targets_opened70/forms_opened_cancelled9；business_acceptance=false 原边界保留。禁止使用 selected 结果或不同 run 拼来源。

所有固定 checkpoint 完整且 passed，当前 provenance.snapshot_stable=true；其 source_contract_sha256、provenance/mirror 与当前 manifest/provenance 对照。原工具从本轮 `evidence_root.parent/scripts` 加载，其逐文件 SHA 与 provenance.script_files 相同；涉及原服务/页面的镜像文件 SHA 与 provenance.source_files 对照，不能从正在变化的工作区直接 import 草案所需 helper。manifest.synthetic_data_only=true；database_path 在同 runtime 内，runtime/evidence/source 为同一个外部 run。人工文件仅写 `evidence/manual-review/hk099-date-expiry`，原自动报告/checkpoint/汇总不覆盖。

| 固定原路径 | 必需字段 |
|---|---|
| `customer-followon-hk100-101-102-103-104-110-111/business-checkpoint.json` | `report_sources.customer_id/customer_vehicle_id/delivered_order_id/delivered_vehicle_id` |
| `customer-reminders-hk105-106-112/business-checkpoint.json` | `next(r for r in partial_requirements if r.id=='HK-099').evidence.source_cv_id/receiver_customer_id/receiver_cv_id/grant/revoke/original_local`；source_cv_id 必须等于上一行 customer_vehicle_id。**不用此报告 report_sources.customer_vehicle_id，那个是另一提醒 VIN。** |
| `system-management-hk189-191/business-checkpoint.json` | HK-191 第一个 acceptance_checks 的 evidence.staff_actions[0].user_id；原店授权关系由即时只读事实复核 |
| `system-management-hk189-191/observations.json` | 唯一 label=synthetic_system_private_credentials 的 value.path，且 credentials_in_evidence=false |
| `system-followon-hk192-193/business-checkpoint.json` | `temporary_auditor_restored=true` |
| `roles-dossier-hk190/business-checkpoint.json` | `report_sources.current_employees.receiver.id/store_roles/access_version/private_source_scenario/private_account_key/current_password_stage`；private_account_key=receiver，private_source_scenario=system-management-hk189-191 |
| `inventory-store-scope-hk071/business-checkpoint.json` | 完整 passed；其员工乙不能代替接收甲 |
| manifest | 授权方 `users[business_fixtures.sales_order.manager_key]`，当前一店 manager；接收方是上行 SYS 员工甲，账号级 sales、当前二店 service |

源码版本不能代替即时原事实。未来实际执行前仅 SELECT 这些有限 id，重核两 CV active、store1/store2、VIN及 customer_identity_id/vehicle_identity_id 同一明确身份；原交付/HistoryLink 非空；source customer 为上一行原客户。旧 revoke 的原 Grant 必须仍 revoked/active_pair=null，没有另一个同对 active Grant。Users active/must_change_password=false、两 Stores active、receiver 当前 UserStore 二店 service 和原授权关系准确；不读取或输出 password_hash/session token/hash。任一来源不符停报，不能扫描全库补找另一辆车、给员工加权或补造身份。

`sales_order_business.fixed_dependency(e, checkpoint, name)` 可复用，参数 checkpoint 必须含当前 catalog digest、当前 provenance 和只写独立人工目录的 save()；它只比较父 requirements，不会错误要求 HK099 partial 升为 passed。`checkpoint_evidence(report,'HK-191')` 取上述员工来源。

## 现成 helper 和原控件

`customer_reminders_business`（下文记 `CR`）已具备 `form/fields/Guard/submit/audit_exact/history/read_page/receiver_login/one/day/digest/decoded`；`fields` 实际定义在 `customer_service_business`，已被 CR 导入。`receiver_login` 经 `system_management_business.fresh_identity → native_login → switch_store`，创建独立 Cookie context、验证原登录审计/会话与二店 service；它读取 src.receiver/src.password，返回 `(context,page,login_metadata)`。已有 Guard 对全原业务表摘要、准许表全部旧行逐列核对，不能用 counts 代替。

`CR.login(e,context,credentials,manager_key,'customer-history-grants','跨店服务历史授权','/api/customer-service/history/grants')` 先真实 manager 登录一店，再等待当前原 GET/body/h1。新授权入口 `#main [data-act="care-grant-new"]`，modal title 精确“登记跨店服务历史授权”。原表单实际控件：`#modal [name="from_vehicle_id"]` 和 `[name="to_store_id"]` 为 select；`[name="to_vehicle_id"]` 为整数输入；`[name="valid_until"]` 为日期；`[name="source_reference"]` 为来源说明；`[name="confirmed"]` 为 checkbox。`CR.fields` 对 select、日期、整数和 bool 分别使用原生控件，并会真实展开必要 details。

POST `/api/customer-service/history/grants` 应为201，真实请求严格是 `{request_id:<原新表单生成>, values:{from_vehicle_id,to_store_id,to_vehicle_id,valid_until:<D ISO>,source_reference,confirmed:true}}`，没有 Grant/version 字段。响应新编号为 `body.grant.id`；渲染 GET `/api/customer-service/history/grants` 的列表字段为 `items`。`CR.submit` 返回 `(body,request,shown,native_metadata)`，不是只有 body；它会核 Cookie/CSRF/X-App-Request/当前店、请求 digest/回执和精确旧行 Guard。不得复用旧 request_id、retry 或重放201。

历史实际路径 `/api/customer-service/vehicles/{id}/history`，响应 `items/notice`。原源 local item 有 case_id，external 条目仅 `{number,kind,business_date,completed_date,state,summary,store_name,external}` 八键；日期过期后是 HTTP200 外部条目消失，本地条目保留。页面 h1 为 `客户车辆 · {plate or vin}`。历史区域精确 `#main .panel` 中 h2“获准服务历史”；external 标识在 `article > strong` 内“已授权跨店摘要”。授权列表七列，原 `[data-act="care-grant-revoke"][data-id="新GrantID"]` 可只用于唯一行定位，**不点击**；该行 td[4] 截止日 D、td[5] 午夜前“有效”、午夜后“已过期”，实际 raw status 始终 active。

## 私有账号的最短读取草案

只读取上表 observations 提供的唯一有限路径，不 glob、不找旧实例。不输出 private 对象、口令或 Login/HTTP 原头。SYS 原私有文件 schema1/synthetic_data_only=true，accounts.receiver 至少含 id/username/current_password_stage 和各阶段口令；SYS 初始化最后阶段 final，后继通常 system_followon，**真实执行只按字段取，不能硬编码名称**。下段是待根决定使用的草案，不是已运行代码：

```python
def receiver_password(e, pointer, receiver):
    runtime = Path(e.manifest['runtime_root']).resolve()
    path = Path(pointer['path']).resolve()
    require(pointer['credentials_in_evidence'] is False,
            '私有口令不能来自证据正文')
    require(path.parent == runtime and path.name.startswith('system-management-accounts-')
            and path.is_file(), '私有指针不在本轮runtime')
    private = json.loads(path.read_text(encoding='utf-8'))
    require(private['schema'] == 1 and private['synthetic_data_only'] is True,
            '不是本轮合成员工私有记录')
    for account in private['accounts'].values():
        e.secrets.extend(v for k, v in account.items() if isinstance(v, str)
                         and k not in {'username', 'current_password_stage'})
    secret = private['accounts']['receiver']
    stage = secret['current_password_stage']
    require(secret['id'] == receiver['id'] and secret['username'] == receiver['username']
            and stage in secret and isinstance(secret[stage], str) and secret[stage],
            '接收甲的当前口令阶段/身份不符')
    return secret[stage]  # 只传给原登录，不能 observe/json.dump/print 返回值
```

## 两阶段最短原生点击草案

输入 src 由上表的同轮完整来源和即时有限只读核对产生，含 `fixture/receiver/pointer/source_cv/receiver_cv/old_revoked`；source_cv/receiver_cv 都是当前完整原行，不沿用历史整行版本。e 是同 manifest 的新 Evidence，directory 指向独立人工目录；所有截图/动作/观察/失败另存，不调用原场景 run/finalizer，也不改自动报告。下面依赖 `json/Path/date/datetime/timezone/timedelta/ZoneInfo/uuid/expect/require`，本轮镜像中的 CR 及 `system_management_business`（记 SYS）。context 是同浏览器仍有效的原父 context；两方均另建 fresh_identity，避免 e.page 已转至接收 context 时把登录检查误交给原父 Cookie jar。credentials 只取 manifest.credentials_path 的本轮私有 fixture 口令，先全部加入 e.secrets，不保存其值到 retained。

```python
def stamp():
    now = datetime.now(timezone.utc)
    return {'utc': now.isoformat(), 'shanghai': now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat()}

def history_panel(e):
    return e.page.locator('#main .panel').filter(
        has=e.page.locator('h2:text-is("获准服务历史")'))

async def receiver_page(e, context, contexts, src):
    # 每次重新读真实当前 stage，不把旧密码或过期会话当授权过期。
    secret = receiver_password(e, src['pointer'], src['receiver'])
    return await CR.receiver_login(e, context, contexts,
                                   {'receiver': src['receiver'], 'password': secret})

async def manager_page(e, context, contexts, credentials, src):
    key = src['fixture']['manager_key']
    actor = e.manifest['users'][key]
    require(credentials['users'][key]['username'] == actor['username'], '本轮授权方凭据串员工')
    password = credentials['users'][key]['password']
    e.secrets.append(password)
    await SYS.fresh_identity(e, context, contexts)
    login = await SYS.native_login(e, actor, password)
    if login['active_store_id'] != 1:
        login = await SYS.switch_store(e, 1, actor, 'manager')
    require(login['current_role'] == 'manager' and login['active_store_id'] == 1,
            '授权方不是本人一店manager')
    return actor

async def before_midnight(e, context, credentials, contexts, src):
    d = CR.day()
    source_id, target_id = src['source_cv']['id'], src['receiver_cv']['id']
    manager = await manager_page(e, context, contexts, credentials, src)
    source_page = e.page
    source_local = await CR.history(e, source_id)
    require(source_local['items'] and all(not r['external'] for r in source_local['items']),
            '本车本店原摘要缺失')
    await receiver_page(e, context, contexts, src)
    recipient_page = e.page
    before_shared = await CR.history(e, target_id)
    require(all(not r['external'] for r in before_shared['items']), '同对已有其他授权')
    e.page = source_page
    await CR.read_page(e, 'customer-history-grants', '跨店服务历史授权',
                       CR.CARE + '/history/grants')
    await CR.form(e, '#main [data-act="care-grant-new"]', '登记跨店服务历史授权')
    values = {'from_vehicle_id': source_id, 'to_store_id': 2, 'to_vehicle_id': target_id,
              'valid_until': d.isoformat(), 'source_reference':
              '本次合成客户明确同意同车服务摘要至今日截止 ' + uuid.uuid4().hex[:12],
              'confirmed': True}
    await CR.fields(e, values)
    require(CR.day() == d, '已经跨日，停止提交昨日截止日')
    guard = CR.Guard(e, 'hk099_new_day_grant', manager, 1,
        appends={'care_history_grants': 1, 'care_receipts': 1, 'audit_logs': 1})
    requested_at = stamp()
    body, request, listing, native = await CR.submit(e, manager, 1,
        CR.CARE + '/history/grants', guard, status=201, render=CR.CARE + '/history/grants',
        action='grant_history', payload=lambda r: r['values'])
    grant = CR.one(e, 'care_history_grants', body['grant']['id'])
    audit_id = CR.audit_exact(guard, 'care_history_grant', 'care_grant', grant['id'])
    require(CR.day() == d and request['values'] == values and grant['status'] == 'active'
            and grant['valid_until'] == d.isoformat() and grant['granted_by'] == manager['id']
            and grant['active_pair'] == f'{source_id}:{target_id}'
            and any(r['id'] == grant['id'] for r in listing['items']), '新授权日期/原身份不符')
    require(CR.one(e, 'care_history_grants', src['old_revoked']['id']) == src['old_revoked'],
            '不得改写本轮原撤销记录')
    e.page = recipient_page
    shared = await CR.history(e, target_id)
    external = [r for r in shared['items'] if r['external']]
    expected = [{k: v for k, v in r.items() if k != 'case_id'} | {'external': True}
                for r in source_local['items']]
    require(external == expected and [r for r in shared['items'] if not r['external']]
            == before_shared['items'], '截止日当天原摘要/本地摘要不符')
    keys = {'number','kind','business_date','completed_date','state','summary','store_name','external'}
    require(all(set(r) == keys for r in external), '跨店摘要字段越界')
    await expect(history_panel(e).locator('article > strong').filter(
        has_text='已授权跨店摘要')).to_have_count(len(expected))
    await e.snapshot('hk099-D-authorized-history')
    # root另核新Grant/Receipt/Audit全字段及页面无外部原单/金额/电话/附件。
    baseline = e.business_snapshot('hk099_before_real_midnight_wait')
    retained = {'D': d.isoformat(), 'grant': grant, 'source_local': source_local,
                'receiver_local': before_shared['items'], 'after_day_read_business': baseline,
                'audit_id': audit_id, 'native': native,
                'requested_at': requested_at, 'completed_at': stamp()}
    e.observe('hk099_D_native_completed_waiting_real_midnight', retained)
    return retained  # 独立文件先保存；此时 complete/passed=False，不能预记过期。

async def after_midnight(e, context, credentials, contexts, src, retained):
    d = date.fromisoformat(retained['D'])
    require(CR.day() == d + timedelta(days=1), '还未到真实D+1或已错过所声明次日')
    # 等待本身不写业务；未知后台原业务变化不能按整表豁免。
    e.business_unchanged(retained['after_day_read_business'], 'hk099_real_wait_business_unchanged')
    await receiver_page(e, context, contexts, src)  # 原登录审计/Session独立Guard；再取GET基线。
    expired = await CR.history(e, src['receiver_cv']['id'])
    require(expired['items'] == retained['receiver_local'], '过期后外部摘要未消失或本店摘要改变')
    await expect(history_panel(e).locator('article > strong').filter(
        has_text='已授权跨店摘要')).to_have_count(0)
    await e.snapshot('hk099-Dplus1-no-external-history')
    manager = await manager_page(e, context, contexts, credentials, src)
    listing = await CR.read_page(e, 'customer-history-grants', '跨店服务历史授权',
                                 CR.CARE + '/history/grants')
    grant_id = retained['grant']['id']
    require(CR.one(e, 'care_history_grants', grant_id) == retained['grant'],
            '过期不能改状态、版本、active_pair或任何原列')
    require(next(r for r in listing['items'] if r['id'] == grant_id)['status'] == 'active',
            '接口不应自动写expired')
    row = e.page.locator('#main tr').filter(has=e.page.locator(
        f'[data-act="care-grant-revoke"][data-id="{grant_id}"]'))
    await expect(row).to_have_count(1)
    await expect(row.locator('td').nth(4)).to_have_text(retained['D'])
    await expect(row.locator('td').nth(5)).to_have_text('已过期')
    await e.snapshot('hk099-Dplus1-original-grant-expired-label')
    require(await CR.history(e, src['source_cv']['id']) == retained['source_local'],
            '原本店历史必须保留')
    require(CR.one(e, 'care_history_grants', src['old_revoked']['id']) == src['old_revoked'],
            '原撤销事实必须保留')
    return {'real_date_expiry_observed': True, 'same_instance': True,
            'observed_at': stamp(), 'D': retained['D'], 'grant_id': grant_id,
            'recipient_history_http': 200, 'external_after': 0,
            'grant_old_row_unchanged': True, 'original_local_history_unchanged': True}
```

源构建的有限 SELECT、全53/provenance 预检和独立证据 finish/failure 由根确定执行入口，不能略掉再声称上述片段独立完成全验收。新 Grant 的 from/to store/CV、双方 identity、valid_until/source_reference/active_pair/granted_by 逐字段核；请求键必须与新 receipt 对应。Receipt 需 actor/store/digest=`CR.digest(['grant_history', request.values])`、decoded(result)=body；Audit 唯一 action=care_history_grant/entity_type=care_grant/entity_id=新 id/actor=manager/store1/reason=来源说明，decoded(before_data/after_data) 均为 None。不是 SQL raw `'null' is None`。创建不追加 FlowEvent/Case/Task/CV/HistoryLink/观察/身份/附件/款/库存/会员。

每个重新登录的 login Audit/本人 Session 由 SYS.native_login 原 before_write/after_write 独立核对，完成后才取 GET 基线；跨日等待前后不能把 audit_logs 整表忽略。草案中的 e.business_snapshot 按现成合同只排助手自有记录、两实际登录记账表及 app_metadata 精确 worker 前缀，所有其他原业务旧行保持；BLOB 内存核对仅报告长度/SHA，不持久化正文。若等待期间出现未知原业务变化、500/403/401、相同授权409或结果不明，保存失败且停止；不更换请求求绿。

根分段等真实日期，每次等待不超过60秒；不调系统时间、不改时区/业务日期/Date字段。靠近午夜仍须留足真实登录和页面动作时间；若已经跨日，不提交昨日日期，应停止本次未执行阶段并另登记当前新D的计划，不能沿旧request重放。截图/DOM/响应/UTC及Shanghai时间四者一致，最终人工记录不能覆盖原 HK099 partial。根统一审核后才能决定业务条件闭合；正常 stop-requested 后再等 runner 的 provider=0/外网0与最终退出码，不凭等待中的 summary 推定网络通过。

## 本次核对的原文件指纹

CR `b16cb44633043585d1f9693041bc7cf956891334ee333b0d66894821ba31093a`；SYS management `7a0425a770c8db492f7489a0190364deac062626be3d4af29be56a3a8ed3bdce`；SYS followon `08603ff77f3c7d4eaf8e6da76c688a5aced595bd4228e77231bcb07133e762b0`；CF `a550e24088bff8facb9c8d60ae044f301f89e8ebc5fedc33203c27998352ea18`；CS fields `66fc51404096abea0c773d5c41e13293f6408e4ba51d2e28f3fa9e3dd61fa6cb`；web/customerservice.js `aa669dba86043529f346be8b95e25e0526e80a4bca6dfc910ded7d53e723f4d7`；app/customer_service.py `924f5f5217d667d719c572a6599e76d674908cc06a28c437535f68de77d5e54b`；app/customer_service_api.py 当前 writer 接线后 `280164918803c8eb3421d4c60f4c4165115fe2dc96600e20f2918359a2278d8b`。这些是研究指纹，真实执行必须以所保留实例的 provenance 为准。
