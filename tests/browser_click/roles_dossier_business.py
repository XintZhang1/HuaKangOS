"""Unregistered native HK190: original roles and named per-record/file grants.

Only original forms submit. Parent facts belong to this run; all SQL is SELECT.
Credentials and attachment bytes stay private; expiry uses the actual UTC clock.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

from playwright.async_api import expect

from sales_business import login_as, require
from sales_order_business import fixed_dependency, checkpoint_evidence
from system_management_business import field, fresh_identity, native_login, revoked_page, switch_store
from vehicle_purchase_business import checkbox, select_value

SCENARIO = "roles-dossier-hk190"
SYSTEM = "system-management-hk189-191"
SALE = "sales-order-hk008-009-011-022"
SYSTEM_FOLLOWON = "system-followon-hk192-193"
API = "/api/dossier-grants"
PK = {t: ("id",) for t in ("users", "stores", "flow_cases", "flow_customers", "vehicles", "flow_events", "flow_files",
    "audit_logs", "user_access_receipts", "dossier_grants", "dossier_grant_files", "dossier_decisions", "dossier_accesses", "dossier_receipts")}
PK["user_stores"] = ("user_id", "store_id")
FILE_KEYS = ("id", "store_id", "case_id", "category", "name", "media_type", "size", "sha256", "created_by",
             "generated", "template_version", "template_approved", "source_fingerprint", "source_file_id")
GRANT_MUTABLE = {"status", "version", "updated_at"}
SOURCE_EXCLUDED = {"business_entity", "opening_import", "reconciliation", "interstore_clearing", "retail_group_rule", "business_finance"}
STATES = {"pending": "待原店复核", "approved": "已批准", "revoked": "已撤销", "expired": "已到期", "suspended": "权限变化，已暂停"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return sha(canonical(value).encode())


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value):
    return utc(value).replace(tzinfo=None).isoformat() + "Z"


def rows(e, table):
    require(table in PK, "角色档案读取表未核准：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {','.join(PK[table])}")


def one(e, table, key):
    require(table in PK and PK[table] == ("id",), "角色档案单行键未核准")
    found = e.db.rows(f"SELECT * FROM {table} WHERE id=?", (key,))
    require(len(found) == 1, "角色档案原记录缺失或非唯一：" + table)
    return found[0]


def identity(table, row):
    return tuple(row[k] for k in PK[table])


def memberships(e, user_id):
    return {r["store_id"]: r["role"] for r in e.db.rows("SELECT store_id,role FROM user_stores WHERE user_id=? ORDER BY store_id", (user_id,))}


def file_metadata(asset):
    value = {k: asset[k] for k in FILE_KEYS}
    value["generated"], value["template_approved"] = bool(value["generated"]), bool(value["template_approved"])
    value["created_at"] = iso(asset["created_at"])
    return value


def public_file(asset):
    value = file_metadata(asset)
    return {k: value[k] for k in ("id", "name", "category", "media_type", "size", "sha256", "created_at")}


def source_snapshot(e, source, *, include_record):
    if not include_record:
        return {}
    header_keys = ("id", "store_id", "number", "kind", "flow_version", "version", "state", "title")
    result = {"definition_version": 1, "case": {k: source[k] for k in header_keys}}
    header = result["case"]
    # Labels are compared with the actual server allowlisted projection separately.
    header.update(business_date=source["business_date"], due_date=source["due_date"], completed_date=source["completed_date"], updated_at=iso(source["updated_at"]))
    if source["customer_id"]:
        customer = one(e, "flow_customers", source["customer_id"])
        require(customer["store_id"] == source["store_id"], "原单客户串店")
        result["customer"] = {"name": customer["name"]}
    if source["vehicle_id"]:
        vehicle = one(e, "vehicles", source["vehicle_id"])
        require(vehicle["store_id"] == source["store_id"], "原单车辆串店")
        result["vehicle"] = {k: vehicle[k] for k in ("vin", "model", "color")}
    events = e.db.rows("SELECT id,label,before_state,after_state,occurred_at FROM flow_events WHERE case_id=? AND store_id=? ORDER BY id", (source["id"], source["store_id"]))
    result.update(events=[{"id": r["id"], "label": r["label"], "from_state": r["before_state"], "to_state": r["after_state"], "occurred_at": iso(r["occurred_at"])} for r in events[-200:]],
                  event_total=len(events), events_omitted=max(0, len(events) - 200))
    return result


def check_snapshot(e, grant):
    actual = decoded(grant["record_snapshot"])
    source = one(e, "flow_cases", grant["source_case_id"])
    expected = source_snapshot(e, source, include_record=bool(grant["include_record"]))
    if grant["include_record"]:
        original_label = {3: "车辆报价与交付", 4: "车辆报价与明细服务交付"}[source["flow_version"]]
        require(set(actual["case"]) == set(expected["case"]) | {"kind_label", "state_label"}
                and actual["case"]["kind_label"] == original_label and actual["case"]["state_label"] == "已提车", "原单快照头字段/原业务名称错误")
        stripped = {**actual, "case": {k: v for k, v in actual["case"].items() if k not in {"kind_label", "state_label"}}}
        require(stripped == expected, "批准原快照与本张真实原单/事件窗口/姓名/VIN不一致")
    else:
        require(actual == expected == {}, "仅文件授权附带了原单快照")
    require(grant["include_contact"] == grant["include_financials"] == 0, "最小原授权意外分享电话/资金")
    return actual


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(raw)
        source = next(r for r in json.loads(raw)["requirements"] if r["id"] == "HK-190")
        require(source["title"] == "角色管理" and source["source_review_status"] == "source_reviewed"
                and any(c["check_id"] == "HK-190-business" for c in source["acceptance_checks"]), "HK190原题/check/合同未核准")
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": ["HK-190"], "source_contract_sha256": self.digest,
            "candidate_sha256": sha(Path(__file__).read_bytes()), "complete": False, "passed": False,
            "execution": "native_browser_original_forms", "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "human_acceptance": "pending",
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "requirements": [{"id": "HK-190", "title": "角色管理", "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": "HK-190-business", "check_id": "HK-190-business", "status": "not_tested",
                    "criteria": ["原UI改权/CAS/会话与访问代次", "指定员工逐原单和文件独立批准/原读取", "换岗恢复仍失效/撤销/真实时钟到期", "全部旧业务/附件/授权/其他员工保护"], "evidence": {}}]}],
            "conditional_not_tested": ["原自批按钮缺失不代表403提交已验", "最后另一位管理员/真实并发互撤", "停用账号或门店/原源转交", "超366天/100文件/后续新增原件", "任意越权HTTP/跨日到期/PG/Linux/ClamAV/员工与生产"],
            "conditions": {"synthetic_data_only": True, "fixture_results_created": False, "clock_changed": False, "production_acceptance": False}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self):
        self.active = self.report["requirements"][0]
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active["evidence_action_start"] = len(self.e.actions)
        self.save()

    def note(self, **value):
        canonical(value)
        self.active["acceptance_checks"][0]["evidence"].update(value)
        self.save()

    def failed(self, error):
        self.report.update(error=self.e.scrub(error), failed_requirement="HK-190")
        if self.active is not None:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
        self.save()

    async def finish(self, sources):
        await self.e.snapshot("hk190-business")
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.report.update(complete=True, passed=True, executed_requirements=1, passed_requirements=1, report_sources=sources)
        self.save()
        self.e.observe("roles_dossier_checkpoint", {"path": str(self.path), "passed_checks": 1, "business_accepted": False})


def dependencies(e, cp):
    root, runtime = Path(e.manifest["evidence_root"]).resolve(), Path(e.manifest["runtime_root"]).resolve()
    require(e.manifest.get("synthetic_data_only") is True and Path(e.manifest["database_path"]).resolve().is_relative_to(runtime), "角色授权只允许本次外部合成实例")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance["snapshot_stable"] is True, "角色来源镜像不稳定")
    for name in ("roles_dossier_business.py", "system_management_business.py", "system_followon_business.py", "sales_business.py", "sales_order_business.py", "vehicle_purchase_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name).read_bytes()), "角色来源脚本并非同轮字节：" + name)
    cp.report["mirror"] = {"source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"], "provenance_sha256": sha(raw)}
    system, sale = fixed_dependency(e, cp, SYSTEM), fixed_dependency(e, cp, SALE)
    seen = {SYSTEM, SALE}
    pending = list(system.get("dependencies", [])) + list(sale.get("dependencies", []))
    while pending:
        name = pending.pop()["scenario"]
        if name not in seen:
            seen.add(name)
            parent = fixed_dependency(e, cp, name)
            pending.extend(parent.get("dependencies", []))
    summary = json.loads((root / "browser-click-report.json").read_text(encoding="utf-8"))
    if any(r["id"] == SYSTEM_FOLLOWON for r in summary["scenarios"]):
        followon = fixed_dependency(e, cp, SYSTEM_FOLLOWON)
        require(followon.get("temporary_auditor_restored") is True, "系统临时来源店审计授权尚未恢复")
    staff = checkpoint_evidence(system, "HK-191")["staff_actions"]
    require(len(staff) >= 2 and staff[0]["default_sales"] is True and staff[1]["default_sales"] is True, "原系统缺两个UI新增员工")
    receiver, sender = one(e, "users", staff[0]["user_id"]), one(e, "users", staff[1]["user_id"])
    require(receiver["id"] != sender["id"] and all(r["role"] == "sales" and r["active"] == 1 and r["must_change_password"] == 0 for r in (receiver, sender)), "本轮两员工当前身份不可用")
    first, second = e.manifest["stores"][0]["id"], e.manifest["stores"][1]["id"]
    original_roles = memberships(e, receiver["id"])
    require(original_roles == {int(k): v for k, v in staff[0]["store_roles"].items()} and first not in original_roles
            and original_roles.get(second) == "service" and len(original_roles) == 2
            and all(r == "auditor" for s, r in original_roles.items() if s != second)
            and memberships(e, sender["id"]) == {first: "manager"}, "本轮员工原授权不同或甲已有来源店权限")
    for sid in {first, *original_roles}:
        require(one(e, "stores", sid)["active"] == 1, "本轮授权相关门店未启用")
    observations = json.loads((root / SYSTEM / "observations.json").read_text(encoding="utf-8"))
    pointers = [r["value"] for r in observations if r["label"] == "synthetic_system_private_credentials"]
    require(len(pointers) == 1 and pointers[0]["credentials_in_evidence"] is False, "原系统缺唯一外部私有凭据指针")
    private_path = Path(pointers[0]["path"]).resolve()
    require(private_path.parent == runtime and private_path.name.startswith("system-management-accounts-"), "密码来源不是本次runtime")
    private = json.loads(private_path.read_text(encoding="utf-8"))
    require(private["synthetic_data_only"] is True, "原系统凭据非合成来源")
    for name, actor in (("receiver", receiver), ("manager", sender)):
        account = private["accounts"][name]
        require(account["id"] == actor["id"] and account["username"] == actor["username"]
                and account["current_password_stage"] in account, "原系统私有账号或密码阶段不符")
        e.secrets.extend(v for k, v in account.items() if isinstance(v, str) and k not in {"username", "current_password_stage"})
    source_id = sale["report_sources"]["delivered_order_id"]
    evidence = checkpoint_evidence(sale, "HK-009")
    require(evidence["case_id"] == source_id, "销售原文件不是本轮交付原单")
    selected = [evidence["handover"]["generated"], evidence["signed_handover"]["file"]]
    require(selected[0]["id"] != selected[1]["id"], "逐件来源须为两件不同实际文件")
    source = one(e, "flow_cases", source_id)
    require(source["store_id"] == first and source["kind"] == "order" and source["flow_version"] in {3, 4}
            and source["state"] == "delivered" and source["kind"] not in SOURCE_EXCLUDED, "源订单当前状态或类型不可分享")
    files = [one(e, "flow_files", r["id"]) for r in selected]
    for previous, current, category in zip(selected, files, ("handover", "signed_handover")):
        require(current["case_id"] == source_id and current["store_id"] == first and current["category"] == category
                and all(current[k] == previous[k] for k in ("id", "case_id", "store_id", "category", "sha256", "size")), "父原件来源或原摘要已改变")
    require(files[1]["source_file_id"] == files[0]["id"], "父签回未引用同次生成件")
    cp.note(source_preconditions={"receiver_id": receiver["id"], "sender_id": sender["id"], "original_store_roles": original_roles,
        "source_case_id": source_id, "current_source_version": source["version"], "files": [public_file(f) for f in files],
        "private_passwords_in_report": False, "same_run_parent_closure": sorted(seen)})
    return {"receiver": receiver, "sender": sender, "private": private, "first": first, "second": second,
            "original_roles": original_roles, "original_summary": bool(receiver["can_group_summary"]), "source_id": source_id, "files": files}


class AccessLedger:
    """Observe actual successful audited reads, including native focus rechecks."""
    def __init__(self):
        self.events, self.pages, self.grants = [], [], set()

    def attach(self, page):
        page.on("response", self.observe)
        self.pages.append(page)

    def observe(self, response):
        match = re.fullmatch(API + r"/(\d+)/(record|files)(?:/(\d+))?", urlsplit(response.url).path)
        if match and response.request.method == "GET" and response.status == 200:
            self.events.append({"response": response, "grant_id": int(match[1]), "action": "record" if match[2] == "record" else "file" if match[3] else "directory",
                                "file_id": int(match[3]) if match[3] else None})

    def close(self):
        for page in self.pages:
            page.remove_listener("response", self.observe)


class Guard:
    def __init__(self, e, label, *, append=None, grant=None, employee=None, ledger=None):
        self.e, self.label, self.grant, self.employee, self.ledger = e, label, grant, employee, ledger
        self.append = append or {}
        self.allowed = set(self.append) | ({"dossier_grants"} if grant is not None else set()) | ({"users", "user_stores"} if employee is not None else set())
        require(self.allowed <= set(PK), "角色档案Guard未核准表")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.allowed}
        self.old_sessions = e.db.rows("SELECT * FROM login_sessions ORDER BY id")
        self.begin = len(ledger.events) if ledger is not None else None
        self.new = {}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys() if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.allowed, "角色档案改变无关原表：" + str(sorted(changed - self.allowed)))
        updated = {}
        for table in self.allowed:
            current = {identity(table, r): r for r in rows(self.e, table)}
            old = {identity(table, r): r for r in self.old[table]}
            for key, original in old.items():
                if table == "user_stores" and original["user_id"] == self.employee:
                    continue
                require(key in current, "角色档案删除原旧行：" + table)
                delta = {k for k in original if current[key][k] != original[k]}
                permitted = GRANT_MUTABLE if table == "dossier_grants" and original["id"] == self.grant else {"access_version", "can_group_summary"} if table == "users" and original["id"] == self.employee else set()
                require(delta <= permitted, "角色档案覆盖非法旧列：" + table + "/" + str(sorted(delta)))
                if delta:
                    updated[str(original.get("id", key))] = {"table": table, "columns": sorted(delta)}
            added = [v for k, v in current.items() if k not in old]
            if table == "user_stores":
                require(all(r["user_id"] == self.employee for r in added), "改权新增其他员工关系")
            elif table not in self.append:
                require(not added, "角色档案意外新增：" + table)
            else:
                count = self.append[table]
                require(count is None or len(added) == count, "角色档案新增数量不同：" + table)
            self.new[table] = added
        current_sessions = self.e.db.rows("SELECT * FROM login_sessions ORDER BY id")
        require([r for r in self.old_sessions if r["user_id"] != self.employee] == [r for r in current_sessions if r["user_id"] != self.employee], "改变了其他员工原会话")
        self.result = {"label": self.label, "changed_tables": sorted(changed), "updated_columns": updated,
            "appended_ids": {t: [r["id"] for r in rs] for t, rs in self.new.items() if t not in {"users", "user_stores"}},
            "all_other_old_rows_business_files_and_sessions_protected": True}
        self.e.observe("roles_dossier_row_guard", self.result)
        return self.result


def audited(e, guard, actor, store, action, key, *, after, reason, before=None):
    found = guard.new["audit_logs"]
    require(len(found) == 1, "原操作必须唯一审计")
    row = found[0]
    require(row["actor_id"] == actor["id"] and row["store_id"] == store and row["action"] == action
            and row["entity_type"] == ("users" if action == "update_user" else "flow" if action == "download" else "dossier_grant")
            and row["entity_id"] == key and row["reason"] == reason
            and decoded(row["before_data"]) == before and decoded(row["after_data"]) == after, "原审计actor/store/动作/对象/范围错误")
    require(0 <= (datetime.now(timezone.utc) - utc(row["occurred_at"])).total_seconds() < 120, "审计不在本次办理窗口")
    return row


async def meta(e, response, *, store, method="POST"):
    headers = await response.request.all_headers()
    require(response.request.method == method and headers.get("cookie") and headers.get("x-csrf-token")
            and headers.get("x-app-request") == "1" and headers.get("x-store-id") == str(store), "原表单同源Cookie/CSRF/当前店不匹配")
    request = response.request.post_data_json
    require(isinstance(request, dict) and isinstance(request.get("request_id"), str), "原请求缺员工此次请求编号")
    info = {"path": urlsplit(response.url).path, "method": method, "status": response.status, "native_ui": True,
        "cookie_present": True, "csrf_present": True, "store_id": store, "request_id_sha256": sha(request["request_id"].encode())}
    return request, info


async def form(e, selector, title):
    await expect(e.page.locator(selector)).to_be_visible()
    await expect(e.page.locator(selector)).to_be_enabled()
    await e.click(selector, "打开原表单：" + title)
    await expect(e.page.locator("#modal")).to_be_visible()
    await expect(e.page.locator("#modal-title")).to_have_text(title)


async def submit(e, path, *, store, status=200, method="POST", render=None):
    future, observed, target = asyncio.get_running_loop().create_future(), [], None
    def observe(response):
        if response.request.method == "GET":
            observed.append(response)
            if target is not None and urlsplit(response.url).path == target and not future.done():
                future.set_result(response)
    e.page.on("response", observe)
    try:
        await expect(e.page.locator('#modal form button[type="submit"]')).to_be_visible()
        await expect(e.page.locator('#modal form button[type="submit"]')).to_be_enabled()
        async with e.page.expect_response(lambda r: r.request.method == method and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "本人一次确认原表单")
        response = await pending.value
        body = await response.json()
        require(response.status == status, "原角色档案HTTP " + str(response.status) + "：" + e.scrub(body.get("detail", "")))
        request, info = await meta(e, response, store=store, method=method)
        if render is not None:
            target = render(body) if callable(render) else render
            for read in observed:
                if urlsplit(read.url).path == target and not future.done():
                    future.set_result(read)
            read = await asyncio.wait_for(future, 30)
            shown = await read.json()
            require(read.status == 200, "原表单保存后实体GET失败")
            info.update(render_get_path=target, render_get_status=read.status)
        else:
            shown = None
        await expect(e.page.locator("#modal")).not_to_be_visible()
        e.observe("original_roles_dossier_submit", info)
        return body, request, info, shown
    finally:
        e.page.remove_listener("response", observe)
        if not future.done():
            future.cancel()


async def staff_login(e, context, contexts, ledger, src, key, store, role):
    _, page = await fresh_identity(e, context, contexts)
    ledger.attach(page)
    actor = one(e, "users", src[key]["id"])
    secret = src["private"]["accounts"]["receiver" if key == "receiver" else "manager"]
    login = await native_login(e, actor, secret[secret["current_password_stage"]])
    if login["active_store_id"] != store:
        login = await switch_store(e, store, actor, role)
    require(login["current_role"] == role and login["active_store_id"] == store, "原员工登录/当前门店岗位不符")
    return page, actor, login


async def navigation(e, box, *, audited_navigation=False):
    before = e.business_snapshot("before_dossier_listing")
    route = "dossier-grants/" + box
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == API
            and parse_qs(urlsplit(r.url).query).get("box") == [box]) as pending:
        if box == "received" and urlsplit(e.page.url).fragment != route:
            selector = '.sidebar a[href="#' + route + '"]'
            link = e.page.locator(selector)
            await expect(link).to_have_count(1)
            ancestor = link.locator("xpath=ancestor::details[1]")
            if await ancestor.count() and await ancestor.get_attribute("open") is None:
                e.action("click", "展开原客户管理导航")
                await ancestor.locator(":scope > summary").click()
            await e.click(selector, "打开本人收到的授权")
        elif urlsplit(e.page.url).fragment == route:
            e.action("navigate", "刷新原档案列表", box=box)
            await e.page.reload(wait_until="domcontentloaded")
        else:
            await e.click(f'#main a[href="#{route}"]', "切换原档案列表：" + box)
    response = await pending.value
    body = await response.json()
    require(response.status == 200, "原授权列表读取失败")
    await expect(e.page.locator("#main h1")).to_have_text("档案授权")
    if not audited_navigation:
        e.business_unchanged(before, "after_dossier_listing")
    return body


async def pick_source(e, src):
    if not urlsplit(e.page.url).fragment.startswith("dossier-grants/"):
        await navigation(e, "received")
    before = e.business_snapshot("before_dossier_pick_source")
    await form(e, '#main [data-act="dossier-pick"]', "选择本店原业务")
    current = one(e, "flow_cases", src["source_id"])
    await e.fill('#modal [name="q"]', current["number"], "按明确原单号查本店真实业务")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/cases"
            and parse_qs(urlsplit(r.url).query).get("q") == [current["number"]]) as query:
        await e.click('#modal #dossier-search button[type="submit"]', "实际查找明确原单")
    response = await query.value
    body = await response.json()
    require(response.status == 200 and any(r["id"] == current["id"] for r in body["items"]), "原查找没有本张有限原单")
    path = f'{API}/source/{current["id"]}'
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path and not urlsplit(r.url).query) as pending:
        await e.click(f'#modal [data-act="dossier-new"][data-case="{current["id"]}"]', "选择本张真实原单申请跨店协同")
    options = await (await pending.value).json()
    await expect(e.page.locator("#modal")).to_be_visible()
    await expect(e.page.locator("#modal-title")).to_have_text("跨店协同")
    require(options["case"] == {"id": current["id"], "number": current["number"], "version": current["version"]}
            and options["max_validity_days"] == 366, "原源版本或资源期限合同不符")
    e.business_unchanged(before, "after_dossier_pick_source")
    return current, options


async def proposal(e, src, actor, ledger, *, selected_file, include_record, expiry_short=False):
    current, options = await pick_source(e, src)
    first, second = src["first"], src["second"]
    require(any(s["id"] == second for s in options["stores"]), "原接收店候选不存在")
    path = f'{API}/source/{current["id"]}'
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path
            and parse_qs(urlsplit(r.url).query) == {"to_store_id": [str(second)]}) as pending:
        await select_value(e, '#modal [name="to_store_id"]', second, "原表单明确接收门店")
    response = await pending.value
    recipients = await response.json()
    receiver = one(e, "users", src["receiver"]["id"])
    role = memberships(e, receiver["id"])[second]
    require(response.status == 200 and {"id": receiver["id"], "label": receiver["display_name"], "role": role} in recipients["recipients"], "原接收员工/当前岗位候选不符")
    await expect(e.page.locator('#modal [name="recipient_id"]')).to_be_enabled()
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path
            and parse_qs(urlsplit(r.url).query) == {"to_store_id": [str(second)], "recipient_id": [str(receiver["id"])]}) as pending:
        await select_value(e, '#modal [name="recipient_id"]', receiver["id"], "明确本人甲接收，不默选员工")
    response = await pending.value
    choice = await response.json()
    require(response.status == 200, "逐件可读原文件核对失败")
    purpose = "本轮合成指定员工核对" + ("短时到期原记录" if expiry_short else "原单快照及明确单件" if include_record else "原签回单件")
    await field(e, "purpose", purpose)
    await checkbox(e, '#modal [name="include_record"]', include_record, "明确是否包含原单快照")
    await expect(e.page.locator('#modal [name="include_contact"]')).not_to_be_checked()
    await expect(e.page.locator('#modal [name="include_financials"]')).not_to_be_checked()
    if not include_record:
        await expect(e.page.locator('#modal [name="include_contact"]')).to_be_disabled()
        await expect(e.page.locator('#modal [name="include_financials"]')).to_be_disabled()
    elif role == "service":
        await expect(e.page.locator('#modal [name="include_financials"]')).to_be_disabled()
    controls = e.page.locator('#modal [name="dossier_file"]')
    await expect(controls).to_have_count(len(choice["files"]))
    require(not any([await controls.nth(i).is_checked() for i in range(await controls.count())]), "原逐件文件被默认勾选")
    file_ids = []
    if selected_file is not None:
        require(public_file(selected_file) in choice["files"], "指定原件不在双方当前可读/检查通过候选")
        await checkbox(e, f'#modal [name="dossier_file"][value="{selected_file["id"]}"]', True, "只勾本次明确原文件")
        file_ids = [selected_file["id"]]
    if expiry_short:
        browser_now = datetime.fromtimestamp(await e.page.evaluate("Date.now()" ) / 1000, timezone.utc)
        # Round upward, leaving a full minute of submission/independent review
        # margin while preserving the original minute-precision native control.
        expires = (browser_now + timedelta(minutes=3)).replace(second=0, microsecond=0) + timedelta(minutes=1)
        require((expires - browser_now).total_seconds() >= 120, "真实短时授权须至少两分钟")
        offset = await e.page.evaluate("new Date().getTimezoneOffset()")
        await field(e, "expires_at", (expires - timedelta(minutes=offset)).replace(tzinfo=None).isoformat(timespec="minutes"))
    else:
        expires = None
    await checkbox(e, '#modal [name="confirmed"]', True, "员工核对指定员工/原单/逐件内容并确认")
    guard = Guard(e, "dossier_propose", append={"dossier_grants": 1, "dossier_grant_files": len(file_ids), "dossier_receipts": 1, "audit_logs": 1})
    body, request, native, shown = await submit(e, API, store=first, status=201, render=lambda b: f'{API}/{b["grant"]["id"]}')
    grant_id = body["grant"]["id"]
    ledger.grants.add(grant_id)
    protection = guard.finish()
    grant = one(e, "dossier_grants", grant_id)
    require(guard.new["dossier_grants"][0]["id"] == grant_id, "申请响应未绑定唯一新增原授权")
    expected = {"source_case_id": current["id"], "source_case_version": current["version"], "to_store_id": second, "recipient_id": receiver["id"],
        "purpose": purpose, "expires_at": request["values"]["expires_at"], "include_record": include_record, "include_contact": False, "include_financials": False,
        "file_ids": file_ids, "confirmed": True}
    require(request == {"request_id": request["request_id"], "values": expected} and body["replayed"] is False and shown["id"] == grant_id
            and grant["from_store_id"] == first and grant["to_store_id"] == second and grant["source_case_id"] == current["id"]
            and grant["source_case_version"] == current["version"] and grant["requested_by"] == actor["id"]
            and grant["requester_role"] == "manager" and grant["requester_access_version"] == one(e, "users", actor["id"])["access_version"]
            and grant["recipient_id"] == receiver["id"] and grant["recipient_role"] == role and grant["recipient_access_version"] == receiver["access_version"]
            and grant["version"] == 1 and grant["status"] == "pending" and iso(grant["expires_at"]) == iso(expected["expires_at"]), "原申请参数/冻结身份或版本不符")
    if expires is not None:
        require(utc(grant["expires_at"]) == expires and utc(grant["expires_at"]) - utc(grant["created_at"]) >= timedelta(minutes=2), "实际保存的短授权不足两分钟")
    file_rows = guard.new["dossier_grant_files"]
    require([r["file_id"] for r in file_rows] == file_ids and all(r["grant_id"] == grant_id for r in file_rows), "新增逐件范围串授权")
    if selected_file is not None:
        require(decoded(file_rows[0]["metadata_snapshot"]) == file_metadata(selected_file), "冻结逐件metadata不等于实际原件")
    record = check_snapshot(e, grant)
    scope = {k: grant[k] for k in ("from_store_id", "to_store_id", "source_case_id", "source_case_version", "recipient_id", "recipient_role", "recipient_access_version", "requested_by", "requester_role", "requester_access_version", "purpose")}
    scope.update(include_record=include_record, include_financials=False, include_contact=False, record_snapshot=record,
                 expires_at=iso(grant["expires_at"]), created_at=iso(grant["created_at"]), files=sorted([decoded(r["metadata_snapshot"]) for r in file_rows], key=lambda r: r["id"]))
    require(grant["scope_digest"] == digest(scope), "原授权冻结scope摘要不符")
    receipt = guard.new["dossier_receipts"][0]
    payload = {**expected, "expires_at": iso(expected["expires_at"])}
    check_receipt(receipt, actor, first, grant, request, "propose", payload)
    audit = audited(e, guard, actor, first, "dossier_propose", grant_id, after={"source_case_id": current["id"], "scope_digest": grant["scope_digest"]}, reason="提交指定员工的只读档案范围")
    await expect(e.page.locator('#main [data-act="dossier-decision"][data-key="approve"]')).to_have_count(0)
    await expect(e.page.locator("#main")).to_contain_text(STATES["pending"])
    return grant, {"native": native, "grant": grant, "scope_files": [decoded(r["metadata_snapshot"]) for r in file_rows], "receipt": receipt,
                   "audit": audit, "source_snapshot": record, "row_guard": protection, "self_review_button_absent": True, "self_review_post_tested": False}


def check_receipt(row, actor, store, grant, request, action, payload):
    require(row["actor_id"] == actor["id"] and row["store_id"] == store and row["grant_id"] == grant["id"]
            and row["scope_digest"] == grant["scope_digest"] and row["request_key"] == request["request_id"] and row["action"] == action
            and decoded(row["request_data"]) == payload and row["digest"] == digest({"action": action, "payload": payload}), "原DossierReceipt本人/门店/原请求/冻结scope不符")


async def plain_detail(e, grant_id, *, box, expected):
    before = e.business_snapshot("before_source_dossier_detail")
    route = f"dossier-grants/{box}/{grant_id}"
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"{API}/{grant_id}") as pending:
        e.action("navigate", "打开明确原授权记录", route=route)
        if urlsplit(e.page.url).fragment == route:
            await e.page.reload(wait_until="domcontentloaded")
        else:
            await e.page.goto(e.origin + "/#" + route, wait_until="domcontentloaded")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["id"] == grant_id and body["effective_status"] == expected, "原授权详情对象/状态不符")
    await expect(e.page.locator("#main h1")).to_have_text("档案授权")
    await expect(e.page.locator("#main")).to_contain_text(STATES[expected])
    e.business_unchanged(before, "after_source_dossier_detail")
    return body


async def decision(e, src, actor, grant, action):
    detail = await plain_detail(e, grant["id"], box="review" if action == "approve" else "sent", expected=grant["status"])
    require(detail["source_side"] is True and detail["scope_digest"] == grant["scope_digest"]
            and detail["preview"] == decoded(grant["record_snapshot"]), "原店决定页冻结范围不同")
    await form(e, f'#main [data-act="dossier-decision"][data-key="{action}"]', "独立批准" if action == "approve" else "撤销授权")
    reason = "原店不同管理员核对指定员工和准确范围" if action == "approve" else "原店明确终止本次单件后续读取，原业务与历史保留"
    await field(e, "reason", reason)
    await checkbox(e, '#modal [name="confirmed"]', True, "明确本次独立决定")
    guard = Guard(e, "dossier_" + action, grant=grant["id"], append={"dossier_decisions": 1, "dossier_receipts": 1, "audit_logs": 1})
    body, request, native, shown = await submit(e, f'{API}/{grant["id"]}/actions/{action}', store=src["first"], render=f'{API}/{grant["id"]}')
    protection = guard.finish()
    current = one(e, "dossier_grants", grant["id"])
    target = "approved" if action == "approve" else "revoked"
    require(request == {"request_id": request["request_id"], "version": grant["version"], "values": {"reason": reason, "confirmed": True}}
            and body["replayed"] is False and body["grant"]["id"] == shown["id"] == current["id"]
            and current["status"] == target and current["version"] == grant["version"] + 1, "原决定参数或授权代次错误")
    event = guard.new["dossier_decisions"][0]
    require(event["grant_id"] == current["id"] and event["previous_version"] == grant["version"] and event["action"] == action
            and event["actor_id"] == actor["id"] and event["actor_role"] == "admin" and event["actor_access_version"] == one(e, "users", actor["id"])["access_version"]
            and event["store_id"] == src["first"] and event["scope_digest"] == grant["scope_digest"] and event["reason"] == reason
            and (action != "approve" or actor["id"] != grant["requested_by"]), "原独立Decision人员/版本/摘要错误")
    receipt = guard.new["dossier_receipts"][0]
    check_receipt(receipt, actor, src["first"], current, request, action, {"grant_id": grant["id"], "version": grant["version"], "reason": reason, "confirmed": True})
    audit = audited(e, guard, actor, src["first"], "dossier_" + action, current["id"], after={"scope_digest": current["scope_digest"]}, reason=reason)
    return current, {"native": native, "decision": event, "receipt": receipt, "audit": audit, "row_guard": protection}


async def access_finish(e, guard, actor, store, ledger):
    protection = guard.finish()
    events = ledger.events[guard.begin:]
    accesses, audits = guard.new["dossier_accesses"], guard.new["audit_logs"]
    require(events and len(events) == len(accesses) == len(audits), "每次真实成功GET必须各有唯一Access和Audit")
    unmatched_accesses, unmatched_audits, matched = list(accesses), list(audits), []
    for event in events:
        require(event["grant_id"] in ledger.grants, "成功读取未知授权")
        response = event["response"]
        headers = await response.request.all_headers()
        require(headers.get("cookie") and headers.get("x-store-id") == str(store) and headers.get("x-app-request") == "1", "原GET没有本人Cookie/正确接收店")
        grant = one(e, "dossier_grants", event["grant_id"])
        candidates = [r for r in unmatched_accesses if r["grant_id"] == grant["id"] and r["action"] == event["action"] and r["file_id"] == event["file_id"]]
        require(candidates, "本次GET缺精确动作Access")
        access = candidates[0]
        unmatched_accesses.remove(access)
        require(access["actor_id"] == actor["id"] and access["store_id"] == store and access["actor_role"] == memberships(e, actor["id"])[store]
                and access["actor_access_version"] == one(e, "users", actor["id"])["access_version"]
                and access["grant_version"] == grant["version"] and access["scope_digest"] == grant["scope_digest"], "原Access本人/当前店岗位/访问代次/授权版本错误")
        found = [r for r in unmatched_audits if r["actor_id"] == actor["id"] and r["store_id"] == store
                 and r["action"] == "dossier_read_" + event["action"] and r["entity_type"] == "dossier_grant" and r["entity_id"] == grant["id"]
                 and r["reason"] == "按独立批准范围只读" and decoded(r["before_data"]) is None
                 and decoded(r["after_data"]) == {"scope_digest": grant["scope_digest"], "file_id": event["file_id"]}]
        require(found, "本次GET缺精确读取Audit")
        audit = found[0]
        unmatched_audits.remove(audit)
        require(0 <= (utc(audit["occurred_at"]) - utc(access["occurred_at"])).total_seconds() < 10, "原Access和Audit不是同次实际读取")
        matched.append({"path": urlsplit(response.url).path, "status": 200, "access": access, "audit": audit})
    require(not unmatched_accesses and not unmatched_audits, "多余读取或审计没有真实GET来源")
    return {"native_gets": matched, "row_guard": protection, "exact_successful_get_count": len(matched)}


async def receiver_detail(e, src, actor, ledger, grant):
    before = Guard(e, "receiver_original_read", append={"dossier_accesses": None, "audit_logs": None}, ledger=ledger)
    endpoint = f'{API}/{grant["id"]}/' + ("record" if grant["include_record"] else "files")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == endpoint) as pending:
        await navigation(e, "received", audited_navigation=True)
        selector = f'#main [data-act="open"][data-route="dossier-grants/received/{grant["id"]}"]'
        await expect(e.page.locator(selector)).to_be_visible()
        await e.click(selector, "甲本人打开独立批准的指定授权")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["grant_id"] == grant["id"] and iso(body["expires_at"]) == iso(grant["expires_at"]), "原接收页读了错误授权")
    expected_files = [public_file(one(e, "flow_files", r["file_id"])) for r in rows(e, "dossier_grant_files") if r["grant_id"] == grant["id"]]
    require(body["files"] == expected_files, "原接收范围开放了未选文件或省略原件")
    if grant["include_record"]:
        require(body == {"grant_id": grant["id"], "scope_digest": grant["scope_digest"], "frozen_at": iso(grant["created_at"]), "expires_at": iso(grant["expires_at"]),
            "record": decoded(grant["record_snapshot"]), "files": expected_files, "read_only": True}, "原接收JSON不是批准时白名单快照")
        record = body["record"]
        await expect(e.page.locator("#main")).to_contain_text(record["case"]["number"])
        await expect(e.page.locator("#main")).to_contain_text(record["customer"]["name"])
        await expect(e.page.locator("#main")).to_contain_text(record["vehicle"]["vin"])
        await expect(e.page.locator('#main h2:text-is("明确批准的金额快照")')).to_have_count(0)
        require(set(record["customer"]) == {"name"} and "financials" not in record, "未授权快照泄露电话或金额")
    else:
        require(body == {"grant_id": grant["id"], "files": expected_files, "include_record": False, "expires_at": iso(grant["expires_at"])}, "仅文件原目录附带源业务/客户/金额")
        await expect(e.page.locator('#main h2:text-is("已冻结的原单快照")')).to_have_count(0)
    await expect(e.page.locator('#main [data-act="dossier-download"]')).to_have_count(len(expected_files))
    await expect(e.page.locator('#main [data-act="dossier-decision"]')).to_have_count(0)
    for action in ("caseaction", "generatedoc", "upload", "downloadfile"):
        await expect(e.page.locator(f'#main [data-act="{action}"]')).to_have_count(0)
    await expect(e.page.locator(f'#main [data-route="case/order/{src["source_id"]}"]')).to_have_count(0)
    for file in expected_files:
        await expect(e.page.locator(f'#main [data-act="dossier-download"][data-file="{file["id"]}"]').locator("xpath=ancestor::tr[1]")).to_contain_text(file["name"])
    audit = await access_finish(e, before, actor, src["second"], ledger)
    require(any(r["access"]["action"] == ("record" if grant["include_record"] else "directory") for r in audit["native_gets"]), "真实页面未读取本次记录/目录")
    return {"response": body, **audit}


async def native_download(e, src, actor, ledger, grant, asset, *, original=False):
    if original:
        guard = Guard(e, "original_file_content_review", append={"audit_logs": 1})
        path = f'/api/flow/files/{asset["id"]}'
        selector = f'#main [data-act="downloadfile"][data-id="{asset["id"]}"]'
    else:
        guard = Guard(e, "dossier_single_file_download", append={"dossier_accesses": None, "audit_logs": None}, ledger=ledger)
        path = f'{API}/{grant["id"]}/files/{asset["id"]}'
        selector = f'#main [data-act="dossier-download"][data-grant="{grant["id"]}"][data-file="{asset["id"]}"]'
    await expect(e.page.locator(selector)).to_be_visible()
    async with e.page.expect_download() as pending_download:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
            await e.click(selector, "实际核验并下载本件原文件")
    response, download = await pending.value, await pending_download.value
    require(response.status == 200, "原逐件下载失败")
    headers = await response.all_headers()
    require(headers.get("x-content-type-options") == "nosniff" and headers.get("cache-control") == "no-store"
            and headers.get("content-security-policy") == "sandbox; default-src 'none'"
            and headers.get("content-type") == asset["media_type"], "原下载安全头/媒体类型缺失")
    match = re.search(r"filename\*=UTF-8''([^;]+)", headers.get("content-disposition", ""), re.I)
    require(match is not None and unquote(match[1]) == asset["name"] and download.suggested_filename == asset["name"], "原文件名与下载件不一致")
    directory = e.directory / "downloaded-original-files"
    directory.mkdir(exist_ok=True)
    destination = directory / (("source-review" if original else "grant-" + str(grant["id"])) + "-" + str(asset["id"]) + Path(asset["name"]).suffix)
    await download.save_as(str(destination))
    require(await download.failure() is None, "原下载失败")
    content = destination.read_bytes()
    require(sha(content) == asset["sha256"] and len(content) == asset["size"], "真实下载字节与父原件不匹配")
    stored = e.db.rows("SELECT content FROM flow_files WHERE id=?", (asset["id"],))[0]["content"]
    require(isinstance(stored, bytes) and stored == content, "原BLOB与实际下载字节不匹配")
    if original:
        protection = guard.finish()
        audit = audited(e, guard, actor, src["first"], "download", src["source_id"], after=None, reason="下载文件 " + str(asset["id"]))
        if asset["category"] == "handover":
            with zipfile.ZipFile(destination) as archive:
                document = ET.fromstring(archive.read("word/document.xml"))
            text = "".join(n.text or "" for n in document.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
            source = one(e, "flow_cases", src["source_id"])
            require(one(e, "flow_customers", source["customer_id"])["name"] in text
                    and one(e, "vehicles", source["vehicle_id"])["vin"] in text, "原生成件没有本客户/本VIN实际可读内容")
        else:
            text = content.decode("utf-8")
            require("合成浏览器验收资料，不表示真实公司签约、银行或现场交接。" in text
                    and "本VIN及当前报价原提车单" in text, "原合成签回内容没有明确本版提车事实")
        observed = {"row_guard": protection, "audit": audit, "actual_content_checked": True, "automatic_document_redaction_claimed": False}
    else:
        observed = await access_finish(e, guard, actor, src["second"], ledger)
        require(any(r["access"]["file_id"] == asset["id"] for r in observed["native_gets"]), "真实下载缺本件Access")
    return {"file": public_file(asset), "download_path": str(destination), "download_sha256": sha(content), "download_size": len(content),
            "native_status": 200, "stored_blob_sha256": sha(stored), "stored_blob_size": len(stored), **observed}


async def ended(e, grant, state):
    body = await plain_detail(e, grant["id"], box="received", expected=state)
    allowed = {"id", "version", "status", "effective_status", "status_label", "from_store_id", "to_store_id", "recipient_id", "expires_at", "created_at",
        "source_side", "can_read", "can_review", "can_cancel", "can_revoke", "from_store_name", "to_store_name"}
    require(set(body) == allowed and body["source_side"] is False and body["can_read"] is False
            and body["can_review"] is False and body["can_cancel"] is False and body["can_revoke"] is False,
            "已终止接收详情泄露了原单/用途/姓名/逐件metadata或操作")
    await expect(e.page.locator('#main [data-act="dossier-download"]')).to_have_count(0)
    await expect(e.page.locator('#main h2:text-is("已冻结的原单快照")')).to_have_count(0)
    require(one(e, "dossier_grants", grant["id"]) == grant, "结束状态读取改写了物理原授权")
    return {"response": body, "old_grant_unchanged": True, "original_payload_and_file_controls_absent": True}


async def users_page(e):
    before = e.business_snapshot("before_original_users")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/users") as pending:
        e.action("navigate", "原员工账号管理", route="users")
        if urlsplit(e.page.url).fragment == "users":
            await e.page.reload(wait_until="domcontentloaded")
        else:
            await e.page.goto(e.origin + "/#users", wait_until="domcontentloaded")
    response = await pending.value
    body = await response.json()
    require(response.status == 200, "原员工管理读取失败")
    await expect(e.page.locator("#main h1")).to_have_text("员工账号")
    e.business_unchanged(before, "after_original_users")
    return body


async def access_form(e, src, *, roles, summary):
    body = await users_page(e)
    user_id = src["receiver"]["id"]
    target = one(e, "users", user_id)
    row = next(r for r in body["items"] if r["id"] == user_id)
    require(row["access_version"] == target["access_version"], "原列表编辑版与当前员工不同")
    await form(e, f'#main [data-act="edituser"][data-id="{user_id}"]', "编辑员工")
    await field(e, "display_name", target["display_name"])
    await select_value(e, '#modal [name="role"]', "sales", "保留员工账号默认销售岗位")
    await checkbox(e, '#modal [name="active"]', True, "保留本人启用状态")
    await checkbox(e, '#modal [name="can_group_summary"]', summary, "明确当前集团汇总授权")
    controls = e.page.locator('#modal [name="store_ids"]')
    choices = [int(await controls.nth(i).get_attribute("value")) for i in range(await controls.count())]
    require(set(roles) <= set(choices) and src["first"] not in roles, "原员工编辑缺明确门店或拟扩大来源店访问")
    for store in choices:
        await checkbox(e, f'#modal [name="store_ids"][value="{store}"]', store in roles, "逐店明确原本人授权")
        if store in roles:
            await select_value(e, f'#modal [name="store_role_{store}"]', roles[store], "核对该店实际岗位")
    return target, row


def account_projection(e, target):
    # Use the immutable original audit projection for full parity, with independent
    # assertions below covering the actual User and UserStore columns.
    return {k: target[k] for k in ("id", "username", "display_name", "role", "active", "must_change_password", "can_group_summary", "access_version")}


def wake_sources(e, user_id, before_roles, after_roles):
    stores = set(before_roles) | set(after_roles)
    for table in ("business_assistant_followup_grants", "business_assistant_runs"):
        stores.update(r["store_id"] for r in e.db.rows(f"SELECT store_id FROM {table} WHERE owner_id=?", (user_id,)))
    return stores


async def change_access(e, src, actor, target, listed, roles, summary, label):
    user_id = target["id"]
    before_roles = memberships(e, user_id)
    signal_stores = wake_sources(e, user_id, before_roles, roles)
    guard = Guard(e, label, employee=user_id, append={"audit_logs": 1, "user_access_receipts": 1})
    require(any(r["user_id"] == user_id for r in guard.old_sessions), "本次改权缺甲待撤销的真实会话")
    body, request, native, shown = await submit(e, f"/api/users/{user_id}", method="PUT", store=src["first"], render="/api/users")
    protection = guard.finish()
    current = one(e, "users", user_id)
    values = {k: v for k, v in request.items() if k != "request_id"}
    require(set(request) == {"request_id", "access_version", "store_ids", "store_roles", "can_group_summary", "role", "display_name", "active"}
            and request["access_version"] == target["access_version"] and request["display_name"] == target["display_name"]
            and request["role"] == "sales" and request["active"] is True and request["can_group_summary"] is summary
            and set(request["store_ids"]) == set(roles) and {r["store_id"]: r["role"] for r in request["store_roles"]} == roles
            and memberships(e, user_id) == roles and bool(current["can_group_summary"]) is summary
            and current["access_version"] == target["access_version"] + 1, "原改权明确输入/逐店岗位或版本错误")
    require(not e.db.rows("SELECT user_id FROM login_sessions WHERE user_id=?", (user_id,)), "原改权没有撤销全部本人会话")
    displayed = next(r for r in shown["items"] if r["id"] == user_id)
    require(displayed == body and body["access_version"] == current["access_version"]
            and body["store_roles"] == [{"store_id": s, "role": roles[s], "legacy_fallback": False} for s in sorted(roles)], "原更新响应/刷新列表不同")
    audit = audited(e, guard, actor, 0, "update_user", user_id, before=listed, after=body, reason="核对账号授权版本后修改；原登录会话全部失效")
    receipt = guard.new["user_access_receipts"][0]
    access_digest = sha(json.dumps({"target_id": user_id, "values": values}, sort_keys=True, ensure_ascii=False).encode())
    require(receipt["actor_id"] == actor["id"] and receipt["target_id"] == user_id and receipt["request_key"] == request["request_id"]
            and receipt["previous_version"] == target["access_version"] and receipt["digest"] == access_digest
            and decoded(receipt["request_data"]) == values and decoded(receipt["result"]) == body and receipt["audit_id"] == audit["id"], "原UserAccessReceipt真实输入/版本/审计错误")
    require(not any(k in canonical(body) for k in ("password_hash", "csrf_hash", "session_id")), "原账号响应泄露凭据")
    wakes = e.db.rows("SELECT id,signal_key,topic,store_id,object_ref,proposal_id,task_id,plan_id,source_ref FROM business_assistant_wake_events WHERE signal_key LIKE ? ORDER BY store_id", (f'user_access_receipt:{receipt["id"]}:store:%',))
    require({r["store_id"] for r in wakes} == signal_stores and len(wakes) == len(signal_stores), "原访问回执派生门店信号不完整或重复")
    for wake in wakes:
        require(wake["signal_key"] == f'user_access_receipt:{receipt["id"]}:store:{wake["store_id"]}' and wake["topic"] == "access.changed"
                and all(wake[k] is None for k in ("object_ref", "proposal_id", "task_id", "plan_id"))
                and decoded(wake["source_ref"]) == {"type": "user_access_receipt", "id": receipt["id"], "version": current["access_version"]}, "原信号携带了错误来源/额外业务上下文")
    await expect(e.page.locator(f'#main tr:has([data-act="edituser"][data-id="{user_id}"])')).to_contain_text(current["display_name"])
    return {"native": native, "old_access_version": target["access_version"], "current_access_version": current["access_version"], "actual_store_roles": roles,
            "account": account_projection(e, current), "access_receipt": receipt, "audit": audit, "wake_sources": wakes, "row_guard": protection,
            "old_target_session_count": sum(r["user_id"] == user_id for r in guard.old_sessions), "remaining_target_session_count": 0}


async def stale_access(e, src, target):
    before = e.business_snapshot("before_original_stale_access")
    sessions = e.db.rows("SELECT * FROM login_sessions ORDER BY id")
    async with e.page.expect_response(lambda r: r.request.method == "PUT" and urlsplit(r.url).path == f'/api/users/{target["id"]}') as pending:
        await e.click('#modal form button[type="submit"]', "独立旧窗口原提交一次，核对真实CAS拒绝")
    response = await pending.value
    body = await response.json()
    request, native = await meta(e, response, store=src["first"], method="PUT")
    expected = "账号授权已被其他管理员修改，请关闭编辑窗口、刷新员工列表并核对最新岗位后重新办理"
    require(response.status == 409 and body.get("detail") == expected and request["access_version"] == target["access_version"], "原旧访问代次没有准确409")
    await expect(e.page.locator("#modal .formerror")).to_contain_text(expected)
    await expect(e.page.locator('#modal form button[type="submit"]')).to_be_enabled()
    e.business_unchanged(before, "after_original_stale_access")
    require(e.db.rows("SELECT * FROM login_sessions ORDER BY id") == sessions, "CAS拒绝改变会话")
    await e.snapshot("hk190-stale-access-409")
    await e.click('#modal .modalhead [data-act="close"]', "关闭旧授权编辑，不重放原提交")
    discard = e.page.locator('#modal .wfx-discard [data-wfx-discard]')
    if await discard.count():
        await expect(discard).to_be_visible()
        e.action("click", "实际放弃旧窗口内容")
        await discard.click()
    await expect(e.page.locator("#modal")).not_to_be_visible()
    await users_page(e)
    e.business_unchanged(before, "after_original_stale_access_closed")
    return {"native": native, "detail": expected, "same_request_preserved_no_replay": True, "business_and_sessions_unchanged": True}


async def aggregate_readonly(e, src):
    before = e.business_snapshot("before_original_group_readonly")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/auth/me") as pending:
        await select_value(e, "#store", "all", "员工明确选择已授权集团只读范围")
    response = await pending.value
    me = await response.json()
    require(response.status == 200 and me["aggregate_scope"] is True and me["role"] == "auditor" and me["active_store_id"] is None
            and set(me["group_store_ids"]) == set(src["original_roles"]) and src["first"] not in me["group_store_ids"], "原集团汇总扩大了来源店")
    await expect(e.page.locator("#store")).to_have_value("all")
    await expect(e.page).to_have_url(e.origin + "/#analytics/overview")
    await expect(e.page.locator("#main h1")).to_have_text("数据可视化")
    await expect(e.page.locator('.sidebar a[href="#dossier-grants/received"]')).to_have_count(0)
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == API + "/catalog") as pending:
        e.action("navigate", "核对汇总模式原档案目录只读保护")
        await e.page.goto(e.origin + "/#dossier-grants/received", wait_until="domcontentloaded")
    catalog = await (await pending.value).json()
    require(catalog["can_read"] is False and catalog["can_propose"] is False and catalog["can_review"] is False, "汇总仍可原档案办理")
    await expect(e.page.locator("#main")).to_contain_text("请先选择本人有权限的具体门店")
    await expect(e.page.locator('#main [data-act="dossier-pick"]')).to_have_count(0)
    e.business_unchanged(before, "after_original_group_readonly")
    switched = await switch_store(e, src["second"], one(e, "users", src["receiver"]["id"]), "auditor")
    return {"native_me": {k: me[k] for k in ("id", "role", "account_role", "active_store_id", "group_store_ids", "aggregate_scope")}, "catalog": catalog, "switched_back": switched}


async def expire_actual(e, src, actor, ledger, grant):
    expiry = utc(grant["expires_at"])
    now = datetime.now(timezone.utc)
    require(now < expiry, "原短期授权在首次真实读取前已到期")
    segments = []
    while datetime.now(timezone.utc) <= expiry + timedelta(seconds=1):
        remaining = (expiry + timedelta(seconds=1) - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            break
        seconds = min(50, remaining)
        e.action("wait_actual_expiry", "等待原UTC期限真实到期，无修改时钟", seconds=round(seconds, 3), expires_at=iso(expiry))
        await asyncio.sleep(seconds)
        segments.append(round(seconds, 3))
    require(datetime.now(timezone.utc) >= expiry and all(0 < s <= 60 for s in segments), "原时钟未真正跨过授权期限")
    baseline = len(ledger.events)
    result = await ended(e, grant, "expired")
    require(len(ledger.events) == baseline, "真实到期后仍有成功payload/文件读取")
    return {"expires_at": iso(expiry), "observed_at": iso(datetime.now(timezone.utc)), "wait_segments_seconds": segments,
            "real_clock_only": True, "physical_status_preserved": "approved", **result}


async def roles_dossier_business(e, context, credentials):
    cp, ledger = Checkpoint(e), AccessLedger()
    main_page, contexts, src = e.page, [], None
    cp.start()
    ledger.attach(main_page)
    try:
        src = dependencies(e, cp)
        sender_page, sender, sender_login = await staff_login(e, context, contexts, ledger, src, "sender", src["first"], "manager")
        g1, propose1 = await proposal(e, src, sender, ledger, selected_file=src["files"][0], include_record=True)
        content_review = await native_download(e, src, sender, ledger, g1, src["files"][0], original=True)
        cp.note(g1_proposed=propose1, selected_source_document_review=content_review, sender_native_login=sender_login)
        e.page = main_page
        admin = await login_as(e, context, credentials, "admin", "parameters", src["first"])
        g1, approve1 = await decision(e, src, admin, g1, "approve")
        receiver_page, receiver, receiver_login = await staff_login(e, context, contexts, ledger, src, "receiver", src["second"], "service")
        read1 = await receiver_detail(e, src, receiver, ledger, g1)
        download1 = await native_download(e, src, receiver, ledger, g1, src["files"][0])
        cp.note(g1_approved=approve1, g1_original_record=read1, g1_exact_file_download=download1, receiver_native_login=receiver_login)
        # A second admin context keeps an actual old form open, with no mutation
        # injection. Native metadata/CAS are inspected only after its real submit.
        _, stale_page = await fresh_identity(e, context, contexts)
        ledger.attach(stale_page)
        await native_login(e, one(e, "users", admin["id"]), credentials["users"]["admin"]["password"])
        stale_target, _ = await access_form(e, src, roles=src["original_roles"], summary=src["original_summary"])
        e.page = main_page
        changed_roles = {**src["original_roles"], src["second"]: "auditor"}
        target, listed = await access_form(e, src, roles=changed_roles, summary=True)
        changed = await change_access(e, src, admin, target, listed, changed_roles, True, "role_change")
        cp.note(access_changed=changed)
        e.page = stale_page
        stale = await stale_access(e, src, stale_target)
        revoked = await revoked_page(e, receiver_page, receiver["id"])
        receiver_page, receiver, relogin = await staff_login(e, context, contexts, ledger, src, "receiver", src["second"], "auditor")
        suspended = await ended(e, g1, "suspended")
        group = await aggregate_readonly(e, src)
        e.page = main_page
        target, listed = await access_form(e, src, roles=src["original_roles"], summary=src["original_summary"])
        restored = await change_access(e, src, admin, target, listed, src["original_roles"], src["original_summary"], "role_restore")
        restored_revoke = await revoked_page(e, receiver_page, receiver["id"])
        receiver_page, receiver, restored_login = await staff_login(e, context, contexts, ledger, src, "receiver", src["second"], "service")
        still_suspended = await ended(e, g1, "suspended")
        require(g1["recipient_access_version"] < one(e, "users", receiver["id"])["access_version"], "恢复岗位竟复活旧访问代次")
        cp.note(original_stale_CAS=stale, original_session_revoke=revoked, current_auditor_login=relogin, g1_suspended=suspended,
            actual_aggregate_readonly=group, roles_restored=restored, restored_session_revoke=restored_revoke,
            restored_service_login=restored_login, g1_did_not_revive=still_suspended)
        e.page = sender_page
        g2, propose2 = await proposal(e, src, sender, ledger, selected_file=src["files"][1], include_record=False)
        content_review2 = await native_download(e, src, sender, ledger, g2, src["files"][1], original=True)
        e.page = main_page
        g2, approve2 = await decision(e, src, admin, g2, "approve")
        e.page = receiver_page
        read2 = await receiver_detail(e, src, receiver, ledger, g2)
        download2 = await native_download(e, src, receiver, ledger, g2, src["files"][1])
        e.page = main_page
        g2, revoke2 = await decision(e, src, admin, g2, "revoke")
        e.page = receiver_page
        revoked2 = await ended(e, g2, "revoked")
        cp.note(g2_file_only_proposed=propose2, second_source_content_review=content_review2, g2_independent_approval=approve2,
                g2_directory_read=read2, g2_exact_file_download=download2, g2_actual_revocation=revoke2, g2_receiver_revoked=revoked2)
        e.page = sender_page
        g3, propose3 = await proposal(e, src, sender, ledger, selected_file=None, include_record=True, expiry_short=True)
        e.page = main_page
        g3, approve3 = await decision(e, src, admin, g3, "approve")
        e.page = receiver_page
        read3 = await receiver_detail(e, src, receiver, ledger, g3)
        expired3 = await expire_actual(e, src, receiver, ledger, g3)
        cp.note(g3_short_record_proposed=propose3, g3_independent_approval=approve3, g3_actual_record_read=read3, g3_actual_expiry=expired3)
        require(memberships(e, receiver["id"]) == src["original_roles"] and bool(one(e, "users", receiver["id"])["can_group_summary"]) is src["original_summary"], "原员工授权未完整恢复")
        await cp.finish({"receiver_id": receiver["id"], "sender_id": sender["id"], "source_case_id": src["source_id"],
            "selected_file_ids": [f["id"] for f in src["files"]], "grant_ids": [g1["id"], g2["id"], g3["id"]],
            "final_original_store_roles": src["original_roles"], "final_access_version": one(e, "users", receiver["id"])["access_version"],
            "current_employees": {key: {"id": src[key]["id"], "store_roles": memberships(e, src[key]["id"]),
                "access_version": one(e, "users", src[key]["id"])["access_version"], "private_source_scenario": SYSTEM,
                "private_account_key": "receiver" if key == "receiver" else "manager",
                "current_password_stage": src["private"]["accounts"]["receiver" if key == "receiver" else "manager"]["current_password_stage"]}
                for key in ("receiver", "sender")},
            "g1_suspended": True, "g2_revoked": True, "g3_real_expired": True})
    except BaseException as error:
        cp.failed(str(error))
        # Only the authorized finite role/summary restoration is eligible on a
        # failed run. The failure remains; original dossiers/results are retained.
        if src is not None:
            current = one(e, "users", src["receiver"]["id"])
            if memberships(e, current["id"]) != src["original_roles"] or bool(current["can_group_summary"]) != src["original_summary"]:
                try:
                    e.page = main_page
                    target, listed = await access_form(e, src, roles=src["original_roles"], summary=src["original_summary"])
                    # A successful role change revoked sessions. Login is a
                    # real original operation and occurs before this guard.
                    if not e.db.rows("SELECT user_id FROM login_sessions WHERE user_id=?", (target["id"],)):
                        await staff_login(e, context, contexts, ledger, src, "receiver", src["second"], memberships(e, target["id"])[src["second"]])
                        e.page = main_page
                    cleanup = await change_access(e, src, admin, target, listed, src["original_roles"], src["original_summary"], "failed_role_restore")
                    cp.note(failed_run_explicit_role_restoration=cleanup)
                except BaseException as cleanup_error:
                    cp.note(role_restore_error=e.scrub(cleanup_error))
        raise
    finally:
        ledger.close()
        if e.response_jobs:
            await asyncio.gather(*list(e.response_jobs))
        e.page = main_page
        for separate in reversed(contexts):
            await separate.close()


ROLES_DOSSIER_SCENARIOS = ((SCENARIO, roles_dossier_business, 900),)
