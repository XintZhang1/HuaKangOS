"""Native current-store source closures for HK152 and HK153.

The third store, staff and prerequisites are finite same-run original UI facts.
No application imports, SQL writes, positive HTTP calls or clock changes.
"""
from __future__ import annotations

from collections import Counter
import asyncio
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import login_as, require, employee_choice
from sales_order_business import fixed_dependency, checkpoint_evidence
from vehicle_purchase_business import checkbox, live_choice, master_form, master_page, select_value, nav
from master_data_business import save_typed, save_item, submit_original
import material_business as M
import system_management_business as SYS
import roles_dossier_business as ACCESS
from report_business import click, panel, verify_table, graph, drill_original, safe_csv
from repair_business import upload

SCENARIO = "reports-complete-source-hk152-153"
CONTRACTS = (("HK-152", "物资仓库入出存统计"), ("HK-153", "物资采购订货统计"))
ZONE = ZoneInfo("Asia/Shanghai")
QUANTITIES = ("ordered", "received", "open", "closed", "pending", "returned", "retained")
PK = {t: "id" for t in M.TABLES | {"master_material_brands", "master_material_categories"}}
PK["file_security"] = "file_id"
CASE_FIELDS = M.CASE_FIELDS
TASK_FIELDS = M.TASK_FIELDS
COMMON = M.COMMON
STOCK_APPEND = M.STOCK_APPEND
WAREHOUSE_APPEND = M.WAREHOUSE_APPEND


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def rows(e, table):
    require(table in PK, "来源报表读取表未核准：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {PK[table]}")


def one(e, table, key):
    require(table in PK and type(key) is int and key > 0, "有限原来源ID无效")
    found = e.db.rows(f"SELECT * FROM {table} WHERE {PK[table]}=?", (key,))
    require(len(found) == 1, "有限原来源缺失或不唯一：" + table)
    return found[0]


def local_day(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp).astimezone(ZONE).date().isoformat()


def same_rows(actual, expected, message):
    require(Counter(digest(r) for r in actual) == Counter(digest(r) for r in expected), message)


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        source = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title in CONTRACTS:
            require(source[key]["title"] == title and source[key]["source_review_status"] == "source_reviewed"
                and any(c["check_id"] == key + "-business" for c in source[key]["acceptance_checks"]), "原需求合同不一致：" + key)
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [k for k, _ in CONTRACTS],
            "complete": False, "passed": False, "execution": "native_browser_original_forms",
            "source_contract_sha256": self.digest, "candidate_sha256": sha(__file__),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "business_accepted": False, "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "human_acceptance": "pending",
            "planned_pending": [{"id": "HK-152-full-historical-period", "status": "not_tested",
                "reason": "当日真实启用不能生成午夜期初；原功能未知期初与有据期末分别核对"}],
            "conditions": {"synthetic_data_only": True, "clock_changed": False,
                "fixture_business_results_created": False, "production_acceptance": False,
                "business_entity_policy_acceptance": False, "clamav_acceptance": False},
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested",
                    "criteria": ["非空本店原来源及完整整数oracle", "原UI/API/图表/明细/CSV/原单同范围", "旧原件保护与来源未知提示"],
                    "evidence": {}}]} for key, title in CONTRACTS]}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    def note(self, **evidence):
        json.dumps(evidence, ensure_ascii=False, allow_nan=False)
        self.active["acceptance_checks"][0]["evidence"].update(evidence)
        self.save()

    async def passed(self, **evidence):
        self.note(**evidence)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        await self.e.snapshot(self.active["id"].lower() + "-functional-source", business_ready=True)
        self.save()

    def failed(self, error):
        self.report.update(error=self.e.scrub(str(error)), complete=False, passed=False)
        if self.active is not None:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.report["failed_requirement"] = self.active["id"]
        self.save()

    def finish(self, sources, restoration):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "两个完整功能检查未全部执行")
        self.report.update(complete=True, passed=True, executed_requirements=2, passed_requirements=2,
            report_sources=sources, original_access_restored=restoration)
        self.save()


class Guard:
    """Current finite store IDs/columns, with all other old rows protected."""
    def __init__(self, e, sid, label, *, append=(), update=None, cases=(), items=(), kind=None):
        self.e, self.sid, self.label = e, sid, label
        self.append, self.update = set(append), update or {}
        self.cases, self.items, self.kind = set(cases), set(items), kind
        require(self.append | self.update.keys() <= PK.keys(), "新店Guard表未核准")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.append | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
            if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.append | self.update.keys(), "原确认影响无关原表：" + str(sorted(changed)))
        new_cases = set()
        if "flow_cases" in self.append:
            previous = {r["id"] for r in self.old["flow_cases"]}
            found = [r for r in rows(self.e, "flow_cases") if r["id"] not in previous]
            require(len(found) == 1 and found[0]["store_id"] == self.sid and found[0]["kind"] == self.kind
                and found[0]["created_by"] == found[0]["owner_id"], "新增本店原单类型/身份非唯一")
            new_cases = {found[0]["id"]}
        added, updated = {}, {}
        for table, previous in self.old.items():
            current = {r[PK[table]]: r for r in rows(self.e, table)}
            old_ids = {r[PK[table]] for r in previous}
            updated[table] = []
            for old in previous:
                key = old[PK[table]]
                require(key in current, "删除了原旧事实：" + table)
                delta = {k for k in old if current[key][k] != old[k]}
                require(delta <= self.update.get(table, {}).get(key, set()), "覆盖了无关旧行/旧列：" + table + "/" + str(key) + "/" + str(sorted(delta)))
                if delta:
                    updated[table].append({"id": key, "columns": sorted(delta)})
            new = [r for key, r in current.items() if key not in old_ids]
            require(not new or table in self.append, "仅更新表新增原行：" + table)
            for row in new:
                if "store_id" in row:
                    require(row["store_id"] == self.sid, "新增原事实串店：" + table)
                if "case_id" in row:
                    require(row["case_id"] in self.cases | new_cases, "新增原事实串单：" + table)
                if "item_id" in row:
                    require(row["item_id"] in self.items, "新增原事实串物资：" + table)
                if table == "warehouse_entries":
                    require(one(self.e, "warehouse_balances", row["balance_id"])["item_id"] in self.items, "库位流水串物资")
                if table == "warehouse_allocation_lines":
                    source = one(self.e, "warehouse_allocations", row["allocation_id"])
                    require(source["case_id"] in self.cases | new_cases and source["item_id"] in self.items, "库位准备行串源")
            added[table] = [r[PK[table]] for r in new]
        result = {"changed_tables": sorted(changed), "appended_ids": added, "updated_columns": updated,
            "all_other_old_rows_and_stores_protected": True}
        self.e.observe("complete_report_source_guard", result)
        return result


def dependencies(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "只允许同轮外置合成环境")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime")
        and not root.is_relative_to(Path(e.manifest["source_root"]).resolve()), "证据/数据库边界错误")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance["snapshot_stable"] is True, "本轮镜像尚未稳定")
    for name in ("report_complete_source_business.py", "system_management_business.py", "roles_dossier_business.py",
        "sales_business.py", "sales_order_business.py", "vehicle_purchase_business.py", "master_data_business.py",
        "material_business.py", "repair_business.py", "report_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name)), "本轮脚本指纹不同：" + name)
    parents = {n: fixed_dependency(e, cp, n) for n in (SYS.SCENARIO, M.MASTER, M.PURCHASE, M.SCENARIO)}
    evidence = checkpoint_evidence(parents[SYS.SCENARIO], "HK-189")
    actions = evidence["store_actions"]
    ids = {r["store_id"] for r in actions}
    require(len(ids) == 1, "同轮系统未创建唯一第三店")
    sid = ids.pop()
    store = e.db.rows("SELECT * FROM stores WHERE id=?", (sid,))
    require(len(store) == 1 and store[0]["active"] == 1 and sid not in {s["id"] for s in e.manifest["stores"]}, "第三店不是本轮新建启用门店")
    audit_ids = [r["audit_id"] for r in actions]
    created = e.db.rows("SELECT id,action,entity_type,entity_id FROM audit_logs WHERE entity_id=? AND action='create_store' AND entity_type='stores'", (sid,))
    require(len(created) == 1 and created[0]["id"] in audit_ids, "第三店缺本轮原UI唯一新增审计")
    require(not e.db.rows("SELECT id FROM flow_cases WHERE store_id=?", (sid,))
        and not e.db.rows("SELECT id FROM flow_items WHERE store_id=?", (sid,))
        and not e.db.rows("SELECT id FROM cash_entries WHERE store_id=?", (sid,)), "本店不是明确无旧业务来源的新店")
    fixture = dict(e.manifest["business_fixtures"]["vehicle_purchase"])
    keys = {r: fixture[r + "_key"] for r in ("inventory", "manager", "finance")}
    actors = {r: ACCESS.one(e, "users", e.manifest["users"][k]["id"]) for r, k in keys.items()}
    require(len({a["id"] for a in actors.values()}) == 3 and all(a["active"] and not a["must_change_password"] for a in actors.values()), "三原本人身份不独立或待改密")
    before_roles = {r: ACCESS.memberships(e, a["id"]) for r, a in actors.items()}
    require(all(sid not in scopes and scopes for scopes in before_roles.values()), "新店已有本人授权或原授权缺失")
    cp.report["mirror"] = {"provenance_sha256": sha(root / "provenance.json"),
        "source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"]}
    cp.report["source_preconditions"] = {"third_store": store[0], "original_user_ids": {r: a["id"] for r, a in actors.items()},
        "original_store_roles": before_roles, "same_run_system_store_actions": actions}
    cp.save()
    fixture["store_id"] = sid
    return fixture, actors, before_roles, store[0]


async def authorize(e, src, admin, actor, roles, label):
    listing = await ACCESS.users_page(e)
    target = ACCESS.one(e, "users", actor["id"])
    shown = next(r for r in listing["items"] if r["id"] == target["id"])
    old_roles = ACCESS.memberships(e, target["id"])
    await ACCESS.form(e, f'#main [data-act="edituser"][data-id="{target["id"]}"]', "编辑员工")
    await SYS.field(e, "display_name", target["display_name"])
    await select_value(e, '#modal [name="role"]', target["role"], "保留原账号默认岗位")
    await checkbox(e, '#modal [name="active"]', bool(target["active"]), "保留原启用状态")
    await checkbox(e, '#modal [name="can_group_summary"]', bool(target["can_group_summary"]), "保留原汇总授权")
    controls = e.page.locator('#modal [name="store_ids"]')
    choices = [int(await controls.nth(i).get_attribute("value")) for i in range(await controls.count())]
    require(set(roles) <= set(choices), "原门店岗位表单缺本次新店")
    for sid in choices:
        await checkbox(e, f'#modal [name="store_ids"][value="{sid}"]', sid in roles, "逐店保留原授权并明确本次范围")
        if sid in roles:
            await select_value(e, f'#modal [name="store_role_{sid}"]', roles[sid], "确认本店本人岗位")
    guard = ACCESS.Guard(e, label, employee=target["id"], append={"audit_logs": 1, "user_access_receipts": 1})
    require(any(r["user_id"] == target["id"] for r in guard.old_sessions), "原改权前没有待撤销的本人会话")
    old_wakes = e.db.rows("SELECT * FROM business_assistant_wake_events ORDER BY id")
    signal_stores = ACCESS.wake_sources(e, target["id"], old_roles, roles)
    body, request, native, listing = await ACCESS.submit(e, f'/api/users/{target["id"]}', method="PUT",
        store=src["admin_store"], render="/api/users")
    protection = guard.finish()
    current = ACCESS.one(e, "users", target["id"])
    expected = {"access_version": target["access_version"], "store_ids": sorted(roles),
        "store_roles": [{"store_id": s, "role": roles[s]} for s in sorted(roles)],
        "role": target["role"], "display_name": target["display_name"], "active": bool(target["active"]),
        "can_group_summary": bool(target["can_group_summary"])}
    require({k: v for k, v in request.items() if k != "request_id"} == expected
        and current["access_version"] == target["access_version"] + 1
        and ACCESS.memberships(e, current["id"]) == roles, "原访问CAS/逐店岗位不符合实际明确输入")
    require(not e.db.rows("SELECT user_id FROM login_sessions WHERE user_id=?", (target["id"],)), "原改权未撤销本人所有旧session")
    require(next(r for r in listing["items"] if r["id"] == target["id"]) == body, "原更新响应/原刷新员工列表不同")
    require(not any(k in json.dumps(body, ensure_ascii=False) for k in ("password_hash", "csrf_hash", "session_id")), "原账号响应含凭据")
    audit = ACCESS.audited(e, guard, admin, 0, "update_user", target["id"], before=shown, after=body,
        reason="核对账号授权版本后修改；原登录会话全部失效")
    receipt = guard.new["user_access_receipts"][0]
    access_digest = hashlib.sha256(json.dumps({"target_id": target["id"], "values": expected}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    require(receipt["actor_id"] == admin["id"] and receipt["target_id"] == target["id"]
        and receipt["request_key"] == request["request_id"] and receipt["previous_version"] == target["access_version"]
        and receipt["digest"] == access_digest and receipt["audit_id"] == audit["id"]
        and decoded(receipt["request_data"]) == expected and decoded(receipt["result"]) == body, "原访问回执未绑定本人/原版本/完整输入")
    wakes = e.db.rows("SELECT id,signal_key,topic,store_id,object_ref,proposal_id,task_id,plan_id,source_ref FROM business_assistant_wake_events WHERE signal_key LIKE ? ORDER BY store_id",
        (f'user_access_receipt:{receipt["id"]}:store:%',))
    require({r["store_id"] for r in wakes} == signal_stores and len(wakes) == len(signal_stores), "原访问信号门店集合缺失/重复")
    for wake in wakes:
        require(wake["signal_key"] == f'user_access_receipt:{receipt["id"]}:store:{wake["store_id"]}'
            and wake["topic"] == "access.changed" and all(wake[k] is None for k in ("object_ref", "proposal_id", "task_id", "plan_id"))
            and decoded(wake["source_ref"]) == {"type": "user_access_receipt", "id": receipt["id"], "version": current["access_version"]}, "原访问信号内容不符合回执")
    current_wakes = {r["id"]: r for r in e.db.rows("SELECT * FROM business_assistant_wake_events ORDER BY id")}
    require(all(current_wakes.get(r["id"]) == r for r in old_wakes)
        and {k for k in current_wakes if k not in {r["id"] for r in old_wakes}} == {r["id"] for r in wakes}, "原授权覆盖旧信号或追加了无关门店信号")
    return {"native": native, "original_access_version": target["access_version"], "current_access_version": current["access_version"],
        "roles": roles, "receipt_id": receipt["id"], "audit_id": audit["id"], "wakes": wakes, "guard": protection,
        "all_old_sessions_revoked": True, "password_or_hash_reported": False}


async def read_page(e, route, title, path, sid):
    before = e.business_snapshot("before_source_page_" + route.replace("/", "_"))
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        e.action("navigate", "查看本人本店原页面", route=route)
        if urlsplit(e.page.url).fragment == route:
            await e.page.reload(wait_until="domcontentloaded")
        else:
            await e.page.goto(e.origin + "/#" + route, wait_until="domcontentloaded")
    response = await pending.value
    body = await response.json()
    headers = await response.request.all_headers()
    require(response.status == 200 and headers.get("cookie") and headers.get("x-store-id") == str(sid), "原页Cookie/本人当前店/HTTP错误")
    await expect(e.page.locator("#main h1")).to_have_text(title)
    await expect(e.page.locator("#store")).to_have_value(str(sid))
    e.business_unchanged(before, "after_source_page_" + route.replace("/", "_"))
    return body


async def login_current(e, context, credentials, key, sid):
    user = e.manifest["users"][key]
    scopes = ACCESS.memberships(e, user["id"])
    require(sid in scopes, "本人尚未通过原UI获得本次门店岗位")
    actor = await login_as(e, context, credentials, key, "parameters", min(scopes))
    await expect(e.page.locator("#main h1")).to_have_text("参数与个人密码")
    if await e.page.locator("#store").input_value() != str(sid):
        e.observe("complete_source_original_store_projection", await SYS.switch_store(e, sid, actor, scopes[sid]))
    return actor


def receipt(e, request, sid, case_id, actor, operation, payload):
    found = e.db.rows("SELECT * FROM flow_request_receipts WHERE request_key=?", (request["request_id"],))
    expected = digest({"operation": operation, "payload": payload})
    require(len(found) == 1 and found[0]["actor_id"] == actor["id"] and found[0]["case_id"] == case_id
        and found[0]["store_id"] == sid and found[0]["digest"] == expected, "原回执未绑定本店本人/版本/规范封包")
    return {k: v for k, v in found[0].items() if k != "request_key"}


async def created(e, sid, actor, domain, guard, expected):
    path = "/api/procurement/orders" if domain == "procurement" else "/api/warehouse/cases"
    body, request, native, shown = await ACCESS.submit(e, path, store=sid, status=201,
        render=lambda b: path + "/" + str(b["id"]))
    values = {k: v for k, v in request.items() if k != "request_id"}
    require(values == expected and body["id"] == shown["id"] and body["version"] == shown["version"], "原创建输入或加载后版本不一致")
    facts = M.facts(e, body["id"])
    require(facts["case"]["store_id"] == sid and facts["case"]["created_by"] == actor["id"]
        and len(facts["events"]) == 1 and facts["events"][0]["actor_id"] == actor["id"]
        and facts["events"][0]["action"] == domain + "_create", "原创建未唯一留本人/当前店事件")
    title = shown["supplier_name"] + " · 采购办理" if domain == "procurement" else shown["operation_label"]
    await expect(e.page.locator("#main h1")).to_have_text(title)
    payload = dict(values)
    if domain == "warehouse":
        for k, v in {"source_location_id": None, "destination_location_id": None, "original_move_id": None,
            "recipient": "", "locations": []}.items():
            payload.setdefault(k, v)
    return body["id"], {"native": native, "submitted": values,
        "receipt": receipt(e, request, sid, body["id"], actor, domain + "_create", payload), "guard": guard.finish(), "db": facts}


async def detail(e, context, credentials, fixture, role, case_id, domain):
    sid = fixture["store_id"]
    actor = await login_current(e, context, credentials, fixture[role + "_key"], sid)
    path = ("/api/procurement/orders/" if domain == "procurement" else "/api/warehouse/cases/") + str(case_id)
    title = one(e, "procurement_orders", case_id)["supplier_name"] + " · 采购办理" if domain == "procurement" else "真实库位启用"
    body = await read_page(e, ("procurement/" if domain == "procurement" else "warehouse/") + str(case_id), title, path, sid)
    current = M.facts(e, case_id)
    require(body["id"] == case_id and body["version"] == current["case"]["version"] and current["case"]["store_id"] == sid, "原详情/CAS串店或迟到")
    require(ACCESS.memberships(e, actor["id"])[sid] == role, "本人的当前原岗位不符")
    if domain == "procurement" and role == "inventory":
        require("totals" not in body and body["payments"] == [] and all("unit_cost_cents" not in r for r in body["lines"]), "库管原页面泄露财务成本")
    return actor, body


async def responsible(e, context, credentials, fixture, role, case_id, key, domain):
    target = e.manifest["users"][fixture[role + "_key"]]
    original = M.open_task(e, case_id, key)
    evidence = {"task_id": original["id"], "key": key, "actor_id": target["id"], "handoff_needed": original["assignee_id"] != target["id"]}
    if evidence["handoff_needed"]:
        manager = await login_current(e, context, credentials, fixture["manager_key"], fixture["store_id"])
        await read_page(e, "case/" + str(case_id), M.facts(e, case_id)["case"]["title"], "/api/flow/cases/" + str(case_id), fixture["store_id"])
        selector = f'#main [data-act="assign"][data-id="{original["id"]}"]'
        await expect(e.page.locator(selector)).to_have_count(1)
        await expect(e.page.locator(selector)).to_be_visible()
        await e.click(selector, "主管原UI交接本项本人待办")
        await expect(e.page.locator("#modal-title")).to_have_text("转交任务")
        await employee_choice(e, target)
        reason = "本次新门店原来源由所选同店岗位本人实际经办"
        await e.fill('#modal [name="reason"]', reason, "明确原待办交接原因")
        guard = Guard(e, fixture["store_id"], "source_task_handoff", append={"flow_events", "audit_logs"},
            update={"flow_tasks": {original["id"]: {"assignee_id", "updated_at", "version"}}}, cases={case_id})
        path = f'/api/flow/tasks/{original["id"]}/assign'
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/cases/" + str(case_id)) as rendered:
            async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
                await e.click('#modal form button[type="submit"]', "主管确认一次原任务交接")
            response = await pending.value
            require(response.status == 200, "原待办交接失败")
            body = await response.json()
        await (await rendered.value).json()
        headers = await response.request.all_headers()
        require(headers.get("cookie") and headers.get("x-csrf-token") and headers.get("x-store-id") == str(fixture["store_id"])
            and response.request.post_data_json == {"version": original["version"], "assignee_id": target["id"], "reason": reason}, "原AssignInput三字段/本人门店错误")
        await expect(e.page.locator("#modal")).not_to_be_visible()
        evidence.update(guard=guard.finish(), assigned_by=manager["id"], native_http=200, response_id=body.get("id"))
    actor, body = await detail(e, context, credentials, fixture, role, case_id, domain)
    require(M.open_task(e, case_id, key)["assignee_id"] == actor["id"], "本原任务不是本人接手")
    e.observe("source_original_task", evidence)
    return actor, body


async def command(e, fixture, actor, domain, case_id, key, guard, values):
    before = M.facts(e, case_id)
    path = (f"/api/procurement/orders/{case_id}/actions/" if domain == "procurement" else f"/api/warehouse/cases/{case_id}/commands/") + key
    render = ("/api/procurement/orders/" if domain == "procurement" else "/api/warehouse/cases/") + str(case_id)
    body, request, native, shown = await ACCESS.submit(e, path, store=fixture["store_id"], render=render)
    require(request["version"] == before["case"]["version"] and request["values"] == values, "原动作CAS/整数输入变化：" + key)
    after = M.facts(e, case_id)
    require(after["case"]["version"] > before["case"]["version"] and body["version"] == shown["version"] == after["case"]["version"], "原动作/加载后版本未推进")
    old_events = {r["id"] for r in before["events"]}
    events = [r for r in after["events"] if r["id"] not in old_events]
    require(len(events) == 1 and events[0]["action"] == domain + "_" + key and events[0]["actor_id"] == actor["id"]
        and events[0]["before_state"] == before["case"]["state"] and events[0]["after_state"] == after["case"]["state"], "原动作事件没有唯一绑定本人/前后状态")
    parsed = dict(values)
    if domain == "warehouse" and key == "approve":
        parsed.setdefault("value_cents", None)
    payload = {"case_id": case_id, "version": request["version"], "values": parsed} if domain == "procurement" else {"id": case_id, "version": request["version"], **parsed}
    return shown, {"native": native, "submitted": values, "event": events[0], "db": after,
        "receipt": receipt(e, request, fixture["store_id"], case_id, actor, domain + "_" + key, payload), "guard": guard.finish()}


async def typed(e, fixture, actor, kind, values, refs=None):
    await master_page(e, kind, {"suppliers": "供应商", "material_brands": "物资品牌", "material_categories": "物资分类",
        "warehouses": "仓库", "locations": "库位", "item_profiles": "物资归类与库位"}[kind])
    await master_form(e, kind, {"suppliers": "供应商", "material_brands": "物资品牌", "material_categories": "物资分类",
        "warehouses": "仓库", "locations": "库位", "item_profiles": "物资归类与库位"}[kind])
    for field, source in (refs or {}).items():
        label = source["code"] + " · " + source["name"] if "code" in source else source["sku"] + " · " + source["name"]
        await live_choice(e, field, source["name"], label, expected_value=source["id"])
    tables = {"suppliers": "master_suppliers", "material_brands": "master_material_brands", "material_categories": "master_material_categories",
        "warehouses": "master_warehouses", "locations": "master_locations", "item_profiles": "master_item_profiles"}
    guard = Guard(e, fixture["store_id"], "source_master_" + kind, append={tables[kind], "master_receipts", "audit_logs"},
        items={refs["item_id"]["id"]} if refs and "item_id" in refs else ())
    if kind == "suppliers":
        # The existing fifteen-master helper does not own suppliers. Preserve
        # the same original form and explicit current-store contract here.
        for field, value in values.items():
            if isinstance(value, bool):
                await checkbox(e, '#modal [name="' + field + '"]', value, "明确原供应商启用状态")
            else:
                await e.fill('#modal [name="' + field + '"]', str(value), "填写原供应商字段")
        body, request, native, listing = await ACCESS.submit(e, "/api/masters/suppliers", store=fixture["store_id"], status=201, render="/api/masters/suppliers")
        row = one(e, "master_suppliers", body["id"])
        require(request["values"] == values and row["store_id"] == fixture["store_id"]
            and all(row[k] == body[k] == v for k, v in values.items()), "原供应商UI/API/DB字段不同")
        visible = next(r for r in listing["items"] if r["id"] == row["id"])
        require(all(visible[k] == row[k] for k in values), "原供应商刷新列表字段不同")
        await expect(e.page.locator(f'#main tr:has([data-act="typed-edit"][data-id="{row["id"]}"])')).to_contain_text(row["name"])
        receipts = e.db.rows("SELECT * FROM master_receipts WHERE store_id=? AND request_key=?", (fixture["store_id"], request["request_id"]))
        expected_digest = digest(["master:suppliers", {"id": None, "version": request.get("version"), "values": values}])
        require(len(receipts) == 1 and receipts[0]["actor_id"] == actor["id"] and receipts[0]["digest"] == expected_digest
            and decoded(receipts[0]["result"]) == body, "原供应商规范回执不同")
        previous = {r["id"] for r in guard.old["audit_logs"]}
        audits = [r for r in rows(e, "audit_logs") if r["id"] not in previous]
        require(len(audits) == 1 and audits[0]["actor_id"] == actor["id"] and audits[0]["store_id"] == fixture["store_id"]
            and audits[0]["action"] == "master_create" and audits[0]["entity_type"] == "typed_master" and audits[0]["entity_id"] == row["id"]
            and audits[0]["reason"] == "供应商" and decoded(audits[0]["before_data"]) is None and decoded(audits[0]["after_data"]) == body, "原供应商审计不同")
        native.update(master_receipt={k: v for k, v in receipts[0].items() if k != "request_key"}, audit=audits[0])
    else:
        row, native = await save_typed(e, actor, fixture["store_id"], kind, values)
    native["guard"] = guard.finish()
    return row, native


async def masters(e, context, credentials, fixture, token):
    actor = await login_current(e, context, credentials, fixture["manager_key"], fixture["store_id"])
    supplier, supplier_native = await typed(e, fixture, actor, "suppliers", {"code": "PS" + token,
        "name": "合成完整来源供应商" + token, "contact_name": "合成来源联系人", "phone": "13800000153",
        "payment_terms_days": 0, "tax_identifier": "SYNTHETIC" + token, "active": True})
    brand, brand_native = await typed(e, fixture, actor, "material_brands", {"code": "PB" + token, "name": "合成来源品牌" + token, "active": True})
    category, category_native = await typed(e, fixture, actor, "material_categories", {"code": "PC" + token,
        "name": "合成来源类别" + token, "active": True})
    warehouse, warehouse_native = await typed(e, fixture, actor, "warehouses", {"code": "PW" + token,
        "name": "合成来源物资仓" + token, "warehouse_type": "materials", "address": "合成演练库房", "active": True})
    locations, location_native = [], []
    for letter in ("A", "B"):
        row, native = await typed(e, fixture, actor, "locations", {"code": "PL" + letter + token,
            "name": "合成来源库位" + letter + token, "active": True}, {"warehouse_id": warehouse})
        require(row["warehouse_id"] == warehouse["id"], "两新库位不属于本次材料仓")
        locations.append(row)
        location_native.append(native)
    await read_page(e, "master/accounts", "收付款账户", "/api/flow/master/accounts", fixture["store_id"])
    await e.click('#main [data-act="newmaster"][data-kind="accounts"]', "原UI新建本店实际合成银行账户")
    await expect(e.page.locator("#modal-title")).to_have_text("新增收付款账户")
    await e.fill('#modal [name="name"]', "合成来源银行账户" + token, "填写独立本店账户名称")
    await select_value(e, '#modal [name="account_type"]', "bank", "明确原银行账户类型")
    await checkbox(e, '#modal [name="active"]', True, "明确启用原新账户")
    guard = Guard(e, fixture["store_id"], "source_bank_account", append={"flow_accounts", "audit_logs"})
    async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == "/api/flow/master/accounts") as account_submit:
        body, listing, request, account_native = await submit_original(e, "/api/flow/master/accounts", "/api/flow/master/accounts", fixture["store_id"])
    account_response = await account_submit.value
    account_headers = await account_response.request.all_headers()
    require(account_headers.get("x-app-request") == "1" and set(request) == {"values"}
        and account_native["request_id_sha256"] is None, "原新账户须保持无request_id的MasterInput合同")
    account = one(e, "flow_accounts", body["id"])
    require(request["values"] == {"name": account["name"], "account_type": "bank", "active": True}
        and account["store_id"] == body["store_id"] == fixture["store_id"] and account["active"] == 1
        and all(body[k] == account[k] for k in ("name", "account_type", "active", "version")), "本店账户UI/API/DB不匹配")
    visible_accounts = [r for r in listing["items"] if r["id"] == account["id"]]
    require(len(visible_accounts) == 1 and all(visible_accounts[0][k] == body[k] for k in ("name", "account_type", "active", "version")),
        "原新账户列表与提交结果不同")
    await expect(e.page.locator(f'#main tr:has([data-act="editmaster"][data-kind="accounts"][data-id="{account["id"]}"])')).to_contain_text(account["name"])
    old_audit_ids = {r["id"] for r in guard.old["audit_logs"]}
    account_audits = [r for r in rows(e, "audit_logs") if r["id"] not in old_audit_ids]
    require(len(account_audits) == 1 and account_audits[0]["actor_id"] == actor["id"]
        and account_audits[0]["store_id"] == fixture["store_id"] and account_audits[0]["action"] == "master_create"
        and account_audits[0]["entity_type"] == "flow_master" and account_audits[0]["entity_id"] == account["id"]
        and account_audits[0]["reason"] == "收付款账户" and decoded(account_audits[0]["before_data"]) is None
        and decoded(account_audits[0]["after_data"]) is None, "原新账户缺唯一本人本店维护审计")
    account_native.update(app_request_present=True, audit=account_audits[0])
    account_native["guard"] = guard.finish()
    inventory = await login_current(e, context, credentials, fixture["inventory_key"], fixture["store_id"])
    await read_page(e, "master/items", "物资目录", "/api/flow/master/items", fixture["store_id"])
    await expect(e.page.locator("#main h1")).to_have_text("物资目录")
    guard = Guard(e, fixture["store_id"], "source_zero_item", append={"flow_items", "audit_logs"})
    item, item_native = await save_item(e, inventory, fixture["store_id"], {"sku": "PI" + token,
        "name": "合成完整来源材料" + token, "unit": "升", "reorder": "0", "active": True})
    item_native["guard"] = guard.finish()
    profile, profile_native = await typed(e, fixture, inventory, "item_profiles", {"active": True},
        {"item_id": item, "category_id": category, "brand_id": brand, "supplier_id": supplier, "location_id": locations[0]})
    require(profile["item_id"] == item["id"] and profile["category_id"] == category["id"] and profile["brand_id"] == brand["id"]
        and profile["supplier_id"] == supplier["id"] and profile["location_id"] == locations[0]["id"], "原物资归类/供应商/库位不符")
    return {"supplier": supplier, "brand": brand, "category": category, "warehouse": warehouse, "locations": locations,
        "account": account, "item": item, "profile": profile, "native": {"supplier": supplier_native, "brand": brand_native,
            "category": category_native, "warehouse": warehouse_native, "locations": location_native,
            "account": account_native, "item": item_native, "profile": profile_native}}


def zero_activation_basis(e, sid, case_id, item_id, location_id):
    case, document = one(e, "flow_cases", case_id), one(e, "warehouse_documents", case_id)
    enrollments = e.db.rows("SELECT * FROM warehouse_enrollments WHERE case_id=? AND item_id=?", (case_id, item_id))
    approvals = e.db.rows("SELECT * FROM warehouse_approvals WHERE case_id=?", (case_id,))
    allocations = e.db.rows("SELECT * FROM warehouse_allocations WHERE case_id=? AND item_id=? AND purpose='activation'", (case_id, item_id))
    require(len(enrollments) == len(approvals) == len(allocations) == 1, "零启用缺唯一原批准/Enrollment/分配来源")
    enrollment, approval, allocation = enrollments[0], approvals[0], allocations[0]
    lines = e.db.rows("SELECT * FROM warehouse_allocation_lines WHERE allocation_id=?", (allocation["id"],))
    require(len(lines) == 1 and lines[0]["location_id"] == location_id and lines[0]["quantity_milli"] == 0,
        "零启用缺唯一实际选定位置的零分配行")
    require(case["store_id"] == document["store_id"] == enrollment["store_id"] == approval["store_id"] == allocation["store_id"] == lines[0]["store_id"] == sid
        and case["kind"] == "warehouse" and case["state"] == "completed"
        and document["operation"] == "activate" and document["item_id"] == item_id
        and document["quantity_milli"] == document["baseline_quantity_milli"] == document["baseline_value_cents"] == 0
        and enrollment["baseline_quantity_milli"] == enrollment["baseline_value_cents"] == enrollment["stock_move_cursor"] == 0
        and approval["value_cents"] == allocation["quantity_milli"] == 0
        and allocation["status"] == "consumed" and allocation["stock_move_id"] is None
        and allocation["actor_id"] == case["created_by"] and approval["actor_id"] == enrollment["actor_id"] != case["created_by"],
        "零启用分配/批准/基准或本店独立身份不一致")
    return {"document": document, "enrollment": enrollment, "approval": approval,
        "allocation": allocation, "allocation_line": lines[0]}


async def activate(e, context, credentials, fixture, source, token):
    sid, item, location = fixture["store_id"], source["item"], source["locations"][0]
    actor = await login_current(e, context, credentials, fixture["inventory_key"], sid)
    await read_page(e, "warehouse", "库位与仓储作业", "/api/warehouse/cases", sid)
    await M.visible_original_button(e, '#main [data-act="wh-new"][data-operation="activate"]', "打开原零库存库位启用")
    await e.click('#main [data-act="wh-new"][data-operation="activate"]', "打开原零库存启用表单")
    await expect(e.page.locator("#modal-title")).to_have_text("真实库位启用")
    await select_value(e, '#modal [name="item_id"]', item["id"], "明确本次新物资")
    await e.fill('#modal [name="quantity"]', "0", "零库存启用不造进货")
    await select_value(e, '#modal [name="location"]', location["id"], "明确原真实零基准库位")
    await e.fill('#modal [name="location_qty"]', "0", "零基准实际分配")
    reason = "本次新店零库存，按现场零数量启用真实物资库位"
    await e.fill('#modal [name="reason"]', reason, "明确零基准来源")
    day = await e.page.locator('#modal [name="due_date"]').input_value()
    expected = {"operation": "activate", "item_id": item["id"], "quantity_milli": 0, "reason": reason,
        "due_date": day, "locations": [{"location_id": location["id"], "quantity_milli": 0}]}
    guard = Guard(e, sid, "source_zero_activation", append=COMMON | {"flow_cases", "flow_tasks", "warehouse_documents"} | WAREHOUSE_APPEND,
        items={item["id"]}, kind="warehouse")
    case_id, creation = await created(e, sid, actor, "warehouse", guard, expected)
    proof = await upload(e, case_id, actor, "evidence", "source-zero-" + token + ".txt", reason, store_id=sid)
    actor, _ = await responsible(e, context, credentials, fixture, "manager", case_id, "wh_approve", "warehouse")
    await M.action_form(e, "warehouse", "approve")
    await select_value(e, '#modal [name="evidence_id"]', proof["file"]["id"], "独立主管核零基准原凭据")
    guard = Guard(e, sid, "source_activation_approve", append=COMMON | {"flow_tasks", "warehouse_approvals", "warehouse_enrollments", "warehouse_balances"},
        update=M.mutable(e, case_id, {item["id"]}, balances=True, allocations=True), cases={case_id}, items={item["id"]})
    _, approval = await command(e, fixture, actor, "warehouse", case_id, "approve", guard, {"evidence_id": proof["file"]["id"]})
    stock = M.item_stock(e, item["id"])
    basis = zero_activation_basis(e, sid, case_id, item["id"], location["id"])
    require(stock["item"]["quantity_milli"] == stock["item"]["inventory_value_cents"] == 0
        and len(stock["balances"]) == 1 and stock["balances"][0]["location_id"] == location["id"]
        and stock["balances"][0]["quantity_milli"] == stock["balances"][0]["value_cents"] == 0
        and not stock["entries"] and stock["enrollment"] == basis["enrollment"]
        and basis["approval"]["actor_id"] == actor["id"] and basis["approval"]["evidence_id"] == proof["file"]["id"]
        and not stock["stock_moves"] and M.facts(e, case_id)["case"]["state"] == "completed", "零基准误产生库存或缺原位置来源")
    return {"case_id": case_id, "creation": creation, "file": proof, "approval": approval, "basis": basis, "db": stock}


async def allocation(e, fixture, actor, case_id, item, location, warehouse, quantity, *, inline=False):
    sid = fixture["store_id"]
    purpose = "procurement_receipt" if inline else "procurement_return"
    version = M.facts(e, case_id)["case"]["version"]
    old = {r["id"] for r in rows(e, "warehouse_allocations")}
    values = {"item_id": item["id"], "quantity_milli": quantity if inline else -quantity, "purpose": purpose,
        "locations": [{"location_id": location["id"], "quantity_milli": quantity}]}
    guard = Guard(e, sid, "source_allocation_" + purpose, append=COMMON | WAREHOUSE_APPEND,
        update=M.mutable(e, case_id, allocations=True), cases={case_id}, items={item["id"]})
    if inline:
        await e.click('#modal [data-prep-open]', "实际分配本批接收位置")
        root = e.page.locator(f'#modal [data-prep-item="{item["id"]}"]')
        await expect(root).to_be_visible()
        await M.choose(e, root, "select[data-prep-bin]", location["name"], warehouse["name"] + " · " + location["name"], location["id"])
        e.action("fill", "明确本批原位置数量", quantity_milli=quantity)
        await root.locator("[data-prep-quantity]").fill(M.qty(quantity))
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == f"/api/warehouse/allocations/{case_id}") as pending:
            await e.click('#modal [data-prep-save]', "实际保存本批库位准备")
        response = await pending.value
        body = await response.json()
        request = response.request.post_data_json
        observed_request, native = await ACCESS.meta(e, response, store=sid)
        require(observed_request == request, "准备动作观察封包不一致")
        require(response.status == 200 and body["case_id"] == case_id and body["prepared"] is True, "原库位准备未成功")
        await expect(e.page.locator('#modal [data-prep-status]')).to_have_text("库位已保存。核对本表后，再确认实际收发。")
    else:
        await read_page(e, "case/" + str(case_id), M.facts(e, case_id)["case"]["title"], "/api/flow/cases/" + str(case_id), sid)
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/warehouse/allocations/{case_id}") as pending:
            await M.visible_original_button(e, f'#main [data-act="open"][data-route="warehouse-allocation/{case_id}"]', "原单打开退货实际库位准备")
            await e.click(f'#main [data-act="open"][data-route="warehouse-allocation/{case_id}"]', "打开原单实际退货位置页")
        require((await pending.value).status == 200, "原准备页面读取失败")
        await (await pending.value).json()
        await expect(e.page.locator("#main h1")).to_have_text("准备物资库位")
        await e.click(f'#main [data-act="wh-allocate"][data-id="{item["id"]}"]', "原UI准备本批实际退回库位")
        await select_value(e, '#modal [name="purpose"]', purpose, "明确原采购退回用途")
        await e.fill('#modal [name="quantity"]', M.qty(quantity), "填写本批实际退回数量")
        await select_value(e, '#modal [name="location"]', location["id"], "明确本原批次接收位置")
        await e.fill('#modal [name="location_qty"]', M.qty(quantity), "填写原位置退回数量")
        body, request, native, _ = await ACCESS.submit(e, f"/api/warehouse/allocations/{case_id}", store=sid,
            render=f"/api/warehouse/allocations/{case_id}")
    require(request["version"] == version and request["values"] == values and M.facts(e, case_id)["case"]["version"] == version + 1, "原库位准备CAS或整数输入不一致")
    added = [r for r in rows(e, "warehouse_allocations") if r["id"] not in old]
    require(len(added) == 1 and added[0]["case_id"] == case_id and added[0]["item_id"] == item["id"]
        and added[0]["actor_id"] == actor["id"] and added[0]["quantity_milli"] == values["quantity_milli"]
        and added[0]["status"] == "prepared" and added[0]["purpose"] == purpose, "原库位准备未唯一留本人/源/用途")
    lines = e.db.rows("SELECT * FROM warehouse_allocation_lines WHERE allocation_id=?", (added[0]["id"],))
    require(len(lines) == 1 and lines[0]["location_id"] == location["id"] and lines[0]["quantity_milli"] == quantity, "原位置准备行没有明确量")
    return {"native": native, "allocation": added[0], "lines": lines,
        "receipt": receipt(e, request, sid, case_id, actor, "warehouse_allocation", {"id": case_id, "version": version, **values}), "guard": guard.finish()}


async def receive(e, context, credentials, fixture, source, case_id, line_id, location, proof):
    actor, _ = await responsible(e, context, credentials, fixture, "inventory", case_id, "procurement_receive", "procurement")
    await M.action_form(e, "procurement", "receive")
    await e.fill(f'#modal [name="quantity_{line_id}"]', "1.000", "本批实际接收一升")
    await M.file_choice(e, "evidence", proof["file"])
    prepare = await allocation(e, fixture, actor, case_id, source["item"], location, source["warehouse"], 1000, inline=True)
    before_ids = {r["id"] for r in rows(e, "procurement_receipts")}
    guard = Guard(e, fixture["store_id"], "source_actual_receive", append=COMMON | {"flow_tasks", "procurement_receipts", "procurement_payment_allocations"} | STOCK_APPEND,
        update=M.mutable(e, case_id, {source["item"]["id"]}, balances=True, allocations=True), cases={case_id}, items={source["item"]["id"]})
    _, native = await command(e, fixture, actor, "procurement", case_id, "receive", guard,
        {"lines": [{"line_id": line_id, "quantity_milli": 1000}], "evidence_id": proof["file"]["id"]})
    found = [r for r in rows(e, "procurement_receipts") if r["id"] not in before_ids]
    require(len(found) == 1 and found[0]["line_id"] == line_id and found[0]["quantity_milli"] == found[0]["value_cents"] == 1000
        and found[0]["evidence_id"] == proof["file"]["id"], "本批原收货不是明确数量/成本/凭据")
    move = one(e, "flow_stock_moves", found[0]["stock_move_id"])
    require(move["purpose"] == "procurement_receipt" and move["quantity_milli"] == move["value_cents"] == 1000
        and move["original_id"] is None and move["actor_id"] == actor["id"]
        and one(e, "warehouse_allocations", prepare["allocation"]["id"])["status"] == "consumed", "本批收货未消费本原准备/实际库存源")
    return {"preparation": prepare, "native": native, "receipt": found[0], "stock_move": move}


async def procurement_action(e, context, credentials, fixture, source, case_id, key, role, task, *, proof=None, returned=None, original=None, token=""):
    actor, current = await responsible(e, context, credentials, fixture, role, case_id, task, "procurement")
    await M.action_form(e, "procurement", key, returned["id"] if returned else None)
    values = {}
    if returned:
        values.update(return_id=returned["id"], return_version=returned["version"])
    if key == "return_approve":
        values["reason"] = "独立主管核对本原批次实物退回及释放款项"
        await e.fill('#modal [name="reason"]', values["reason"], "独立批准原批次退回")
    if key in {"pay", "refund"}:
        amount = 2000 if key == "pay" else 500
        await e.fill('#modal [name="amount"]', M.money(amount), "财务本人登记本次实际合成款")
        await live_choice(e, "account_id", source["account"]["name"], source["account"]["name"], expected_value=source["account"]["id"])
        reference = "SOURCE-" + key.upper() + "-" + token
        await e.fill('#modal [name="reference"]', reference, "明确本次唯一原凭证编号")
        values.update(amount_cents=amount, account_id=source["account"]["id"], reference=reference)
    if original:
        require(key == "refund" and current["prepayments"] is None, "本来源未启用预付款，不能推断抵用释放")
        payment_rows = e.db.rows("SELECT * FROM procurement_payments WHERE case_id=? ORDER BY id", (case_id,))
        payment_fields = ("id", "direction", "amount_cents", "account_id", "original_id", "reference", "cash_id", "evidence_id")
        shown_payments = sorted(current["payments"], key=lambda p: p["id"])
        require([{k: p[k] for k in payment_fields} for p in shown_payments]
                == [{k: p[k] for k in payment_fields} for p in payment_rows]
                and len(payment_rows) == 1 and payment_rows[0] == original,
                "财务本人原GET付款来源与DB不一致或原款被改写")
        refunded = sum(p["amount_cents"] for p in payment_rows if p["direction"] == "in" and p["original_id"] == original["id"])
        remaining = original["amount_cents"] - refunded
        require(remaining == 2000 and current["totals"]["supplier_refund_due_cents"] == values["amount_cents"] == 500,
                "原付款未退额和全单应退额必须分别核对")
        e.observe("source_refund_original_caps", {"case_id": case_id, "original_payment_id": original["id"],
            "account_id": original["account_id"], "original_unreturned_cents": remaining,
            "supplier_refund_due_cents": current["totals"]["supplier_refund_due_cents"], "actual_refund_cents": values["amount_cents"],
            "prepayments": current["prepayments"], "native_get_payments_match_db": True})
        option = e.page.locator(f'#modal select[name="original_payment_id"] option[value="{original["id"]}"]')
        await expect(option).to_have_count(1)
        label = await option.text_content()
        require(original["reference"] in label and "本笔剩余 " + M.money(remaining) + " 元" in label,
                "原退款选项必须显示本原付款未退额")
        await live_choice(e, "original_payment_id", original["reference"], label, expected_value=original["id"])
        values["original_payment_id"] = original["id"]
    if proof:
        await M.file_choice(e, "evidence_id", proof["file"])
        values["evidence_id"] = proof["file"]["id"]
    append = COMMON | {"flow_tasks", "procurement_payment_allocations"}
    if key in {"pay", "refund"}:
        append |= {"procurement_payments", "cash_entries"}
    if key == "return_dispatch":
        append |= STOCK_APPEND | {"procurement_return_postings", "procurement_return_valuations"}
    item_ids = {source["item"]["id"]} if key in {"return_approve", "return_dispatch"} else set()
    guard = Guard(e, fixture["store_id"], "source_procurement_" + key, append=append,
        update=M.mutable(e, case_id, item_ids, balances=key == "return_dispatch", allocations=key == "return_dispatch",
            returns=bool(returned), account_id=source["account"]["id"] if key in {"pay", "refund"} else None), cases={case_id}, items={source["item"]["id"]})
    return await command(e, fixture, actor, "procurement", case_id, key, guard, values)


async def procure(e, context, credentials, fixture, source, token):
    sid, item = fixture["store_id"], source["item"]
    actor = await login_current(e, context, credentials, fixture["inventory_key"], sid)
    await read_page(e, "procurement", "采购与供应商结算", "/api/procurement/orders", sid)
    await e.click('#main [data-act="procurement-new"]', "本人申请本次新店原采购")
    await expect(e.page.locator("#modal-title")).to_have_text("申请多行采购")
    await M.choose(e, e.page.locator("#modal"), 'select[name="supplier"]', source["supplier"]["name"], source["supplier"]["code"] + " · " + source["supplier"]["name"], source["supplier"]["id"])
    line = e.page.locator('#modal [data-purchase-line]')
    await M.choose(e, line, 'select[name="item"]', item["name"], item["sku"] + " · " + item["name"] + "（升）", item["id"])
    e.action("fill", "明确新采购两升及十元单价", quantity_milli=2000, unit_cost_cents=1000)
    await line.locator('[name="quantity"]').fill("2.000")
    await line.locator('[name="cost"]').fill("10.00")
    reason = "本轮新店真实采购两升，分两原库位接收一升后原退半升"
    await e.fill('#modal [name="reason"]', reason, "填写本次合成输入来源")
    guard = Guard(e, sid, "source_new_procurement", append=COMMON | {"flow_cases", "flow_tasks", "procurement_orders", "procurement_lines"},
        cases=(), items={item["id"]}, kind="procurement")
    case_id, creation = await created(e, sid, actor, "procurement", guard,
        {"supplier_id": source["supplier"]["id"], "reason": reason, "lines": [{"item_id": item["id"], "quantity_milli": 2000, "unit_cost_cents": 1000}]})
    lines = e.db.rows("SELECT * FROM procurement_lines WHERE case_id=?", (case_id,))
    require(len(lines) == 1 and lines[0]["quantity_milli"] == lines[0]["amount_cents"] == 2000 and lines[0]["unit_cost_cents"] == 1000, "原采购行金额不守恒")
    _, approval = await procurement_action(e, context, credentials, fixture, source, case_id, "approve", "manager", "procurement_approve")
    require(M.facts(e, case_id)["case"]["state"] == "receiving", "独立批准没有进入原接收状态")
    receipts = []
    for index, location in enumerate(source["locations"]):
        actor, _ = await detail(e, context, credentials, fixture, "inventory", case_id, "procurement")
        proof = await upload(e, case_id, actor, "evidence", f"source-receive-{index}-{token}.txt", "本次现场接收一升，位置" + location["name"], store_id=sid)
        receipts.append(await receive(e, context, credentials, fixture, source, case_id, lines[0]["id"], location, proof))
    actor, _ = await detail(e, context, credentials, fixture, "finance", case_id, "procurement")
    pay_file = await upload(e, case_id, actor, "receipt", "source-pay-" + token + ".txt", "合成银行实际付款二十元，原账户原单独立登记", store_id=sid)
    _, paid = await procurement_action(e, context, credentials, fixture, source, case_id, "pay", "finance", "procurement_pay", proof=pay_file, token=token)
    payments = e.db.rows("SELECT * FROM procurement_payments WHERE case_id=?", (case_id,))
    require(len(payments) == 1 and payments[0]["amount_cents"] == 2000 and payments[0]["direction"] == "out"
        and payments[0]["account_id"] == source["account"]["id"] and payments[0]["original_id"] is None, "原采购实际付款不是本次原账户二十元")
    payment = payments[0]
    actor, _ = await detail(e, context, credentials, fixture, "inventory", case_id, "procurement")
    return_file = await upload(e, case_id, actor, "evidence", "source-return-" + token + ".txt", "第一原批次实物半升退回同供应商，禁止借第二批库存", store_id=sid)
    await M.action_form(e, "procurement", "return_request")
    await e.fill(f'#modal [name="quantity_{receipts[0]["receipt"]["id"]}"]', "0.500", "明确退本次第一实际批次半升")
    await M.file_choice(e, "evidence", return_file["file"])
    return_reason = "原第一批次半升现场退回供应商，来源和款项独立核对"
    await e.fill('#modal [name="reason"]', return_reason, "填写本次实际原批次退回原因")
    guard = Guard(e, sid, "source_return_request", append=COMMON | {"flow_tasks", "procurement_returns", "procurement_return_lines"},
        update=M.mutable(e, case_id), cases={case_id}, items={item["id"]})
    _, requested = await command(e, fixture, actor, "procurement", case_id, "return_request", guard,
        {"lines": [{"receipt_id": receipts[0]["receipt"]["id"], "quantity_milli": 500}], "evidence_id": return_file["file"]["id"], "reason": return_reason})
    found = e.db.rows("SELECT * FROM procurement_returns WHERE case_id=?", (case_id,))
    require(len(found) == 1 and found[0]["requested_by"] == actor["id"], "本原退回申请非唯一本人")
    returned = found[0]
    _, return_approved = await procurement_action(e, context, credentials, fixture, source, case_id, "return_approve", "manager",
        "procurement_return_review_" + str(returned["id"]), returned=returned)
    returned = one(e, "procurement_returns", returned["id"])
    require(returned["approved_by"] != returned["requested_by"], "原退回发生自批")
    actor, _ = await responsible(e, context, credentials, fixture, "inventory", case_id, "procurement_return_dispatch_" + str(returned["id"]), "procurement")
    preparation = await allocation(e, fixture, actor, case_id, item, source["locations"][0], source["warehouse"], 500)
    _, dispatched = await procurement_action(e, context, credentials, fixture, source, case_id, "return_dispatch", "inventory",
        "procurement_return_dispatch_" + str(returned["id"]), returned=returned, proof=return_file)
    posting = e.db.rows("SELECT * FROM procurement_return_postings WHERE case_id=?", (case_id,))
    require(len(posting) == 1 and posting[0]["receipt_id"] == receipts[0]["receipt"]["id"] and posting[0]["quantity_milli"] == posting[0]["value_cents"] == 500, "实物退回未引用本第一原批次及成本")
    return_move = one(e, "flow_stock_moves", posting[0]["stock_move_id"])
    require(return_move["quantity_milli"] == return_move["value_cents"] == -500 and return_move["original_id"] == receipts[0]["stock_move"]["id"], "原实物负向源不是本次实际收货")
    actor, _ = await detail(e, context, credentials, fixture, "finance", case_id, "procurement")
    refund_file = await upload(e, case_id, actor, "receipt", "source-refund-" + token + ".txt", "供应商原银行账户退回五元，严格引用本原付款", store_id=sid)
    body, refunded = await procurement_action(e, context, credentials, fixture, source, case_id, "refund", "finance", "procurement_refund",
        proof=refund_file, original=payment, token=token)
    stock = M.item_stock(e, item["id"])
    payments = e.db.rows("SELECT * FROM procurement_payments WHERE case_id=? ORDER BY id", (case_id,))
    cash = [one(e, "cash_entries", p["cash_id"]) for p in payments]
    require(len(payments) == 2 and payments[1]["direction"] == "in" and payments[1]["original_id"] == payment["id"]
        and payments[1]["account_id"] == payment["account_id"] and payments[1]["amount_cents"] == 500, "供应商退款未实际引用同原账户原款")
    require([r["amount_cents"] for r in cash] == [2000, 500] and [r["direction"] for r in cash] == ["out", "in"]
        and all(r["approval_state"] == "approved" and r["store_id"] == sid and r["created_by"] == actor["id"] for r in cash), "本笔原资金事实不独立于实物")
    require(stock["item"]["quantity_milli"] == stock["item"]["inventory_value_cents"] == 1500
        and sorted(b["quantity_milli"] for b in stock["balances"]) == [500, 1000]
        and M.facts(e, case_id)["case"]["state"] == "completed"
        and body["totals"]["paid_net_cents"] == 1500
        and all(body["totals"][k] == 0 for k in ("payable_cents", "supplier_refund_due_cents"))
        and body["prepayments"] is None and "prepaid_cents" not in body["totals"], "本次完成后量值/原净款或普通采购合同未守恒")
    return {"case_id": case_id, "line": lines[0], "creation": creation, "approval": approval, "receipts": receipts,
        "paid": paid, "return_request": requested, "return_approval": return_approved, "return_preparation": preparation,
        "return_dispatch": dispatched, "return_posting": posting[0], "return_move": return_move,
        "refund": refunded, "payments": payments, "cash": cash, "stock": stock}


def q(value):
    return format(Decimal(value) / 1000, "f")


def yuan(value):
    return "—" if value is None else format(Decimal(value) / 100, ".2f")


async def read_metadata(e, response, sid, parameters):
    headers = await response.request.all_headers()
    actual = {k: v for k, v in parse_qs(urlsplit(response.url).query).items() if v != [""]}
    require(response.request.method == "GET" and response.status == 200 and urlsplit(response.url).netloc == urlsplit(e.origin).netloc
        and headers.get("cookie") and headers.get("x-store-id") == str(sid)
        and actual == {k: [str(v)] for k, v in parameters.items()}, "原报表同源Cookie/本人店/精确筛选不同")
    return {"path": urlsplit(response.url).path, "status": response.status, "store_id": sid,
        "query": parameters, "cookie_present": True, "native_browser_request": True}


async def open_report(e, sid, key, family, period):
    before = e.business_snapshot("before_complete_source_report_entry")
    await nav(e, "module/analytics", "统计分析", None)
    await e.fill("#mux-query", key, "检索本项原需求报表")
    await click(e, e.page.locator('[data-mux-open="wf-report-' + key.split("-")[1] + '"]'), "打开本人本店原报表")
    await expect(e.page).to_have_url(e.origin + "/#" + ("procurement-cohort" if family == "procurement" else "warehouse-period"))
    await expect(e.page.locator("#datefilters")).to_be_visible()
    for name, value in period.items():
        await e.fill('#datefilters [name="' + name + '"]', value, "按本次原来源日期查询")
    path = "/api/inventory-reports/" + family
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        await click(e, e.page.locator('#datefilters button[type="submit"]'), "本人确认原期间报表")
    response = await pending.value
    data = await response.json()
    metadata = await read_metadata(e, response, sid, period)
    await expect(e.page.locator("#main h1")).to_have_text("物资采购订货统计" if family == "procurement" else "库位期间入出存")
    await expect(e.page.locator("#main .loading")).to_have_count(0)
    await expect(e.page.locator("#store")).to_have_value(str(sid))
    require(data["date_from"] == period["date_from"] and data["date_to"] == period["date_to"] and data["can_money"] is True, "原报表日期/本人财务可读字段错误")
    e.business_unchanged(before, "after_complete_source_report_entry")
    e.observe("complete_source_original_report_read", metadata)
    return data


async def export(e, sid, actor, data, family, key, period, *, filters=None, locator=None):
    before = e.business_snapshot("before_complete_source_csv")
    old = rows(e, "audit_logs")
    path, parameters = "/api/inventory-reports/" + family + "/export/" + key, {**period, **(filters or {})}
    locator = locator if locator is not None else panel(e, data, key, family).locator('[data-act="inventory-report-export"][data-key="' + key + '"]')
    async with e.page.expect_download() as downloaded:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
            await click(e, locator, "下载本店本期间原CSV全部行")
        response = await pending.value
        native = await read_metadata(e, response, sid, parameters)
    download = await downloaded.value
    require(await download.failure() is None, "原CSV下载失败，不重放")
    folder = e.directory / "exports"
    folder.mkdir(exist_ok=True)
    destination = folder / (str(len(list(folder.iterdir())) + 1).zfill(2) + "-" + key + ".csv")
    await download.save_as(destination)
    table = data["tables"][key]
    actual = list(csv.reader(io.StringIO(destination.read_text(encoding="utf-8-sig"), newline="")))
    require(actual == [table["headers"]] + [[safe_csv(v, "inventory") for v in r["values"]] for r in table["rows"]], "原CSV不是同范围全部行/顺序/整数换算")
    after = e.business_snapshot("after_complete_source_csv")
    require({k: v for k, v in before["tables"].items() if k != "audit_logs"} == {k: v for k, v in after["tables"].items() if k != "audit_logs"}, "导出修改原业务/他店事实")
    current = {r["id"]: r for r in rows(e, "audit_logs")}
    require(all(current.get(r["id"]) == r for r in old), "原CSV覆盖旧审计")
    added = [r for k, r in current.items() if k not in {o["id"] for o in old}]
    reason = period["date_from"] + "至" + period["date_to"] + " " + key
    require(len(added) == 1 and added[0]["actor_id"] == actor["id"] and added[0]["store_id"] == sid
        and added[0]["action"] == "export" and added[0]["entity_type"] == family + "_inventory_report"
        and added[0]["entity_id"] is None and added[0]["reason"] == reason
        and decoded(added[0]["before_data"]) is None and decoded(added[0]["after_data"]) is None, "原CSV没有唯一真实本人本店审计")
    result = {"path": str(destination), "sha256": sha(destination), "rows": len(table["rows"]), "native": native,
        "audit": added[0], "all_old_audit_and_business_rows_protected": True, "bytes_only_read_from_actual_download": True}
    e.observe("complete_source_original_csv", result)
    return result


def procurement_oracle(e, data, sid, store, source, purchase, period):
    case = M.facts(e, purchase["case_id"])["case"]
    whole = e.db.rows("SELECT * FROM flow_cases WHERE store_id=? AND kind IN ('procurement','purchase') ORDER BY id", (sid,))
    require(len(whole) == 1 and whole[0]["id"] == case["id"] and whole[0]["kind"] == "procurement", "第三店有未列出的旧简表/额外采购源")
    events = [r for r in M.facts(e, case["id"])["events"] if r["action"] in {"procurement_create", "procurement_approve"}]
    require(len(events) == 2 and local_day(events[0]["occurred_at"]) == case["business_date"] == period["date_from"], "订货真实本地申请日/独立批准缺失")
    line, header = one(e, "procurement_lines", purchase["line"]["id"]), one(e, "procurement_orders", case["id"])
    require(line["unit"] == "升" and line["item_id"] == source["item"]["id"] and line["unit_cost_cents"] == 1000
        and line["quantity_milli"] == line["amount_cents"] == 2000 and header["supplier_id"] == source["supplier"]["id"], "原冻结采购数量/价格/供应商不符合输入")
    quantities = dict(zip(QUANTITIES, (2000, 2000, 0, 0, 0, 500, 1500)))
    expected = {"case_id": case["id"], "store_id": sid, "number": case["number"], "line_id": line["id"], "date": case["business_date"],
        "supplier": header["supplier_name"], "sku": line["sku"], "name": line["item_name"], "unit": line["unit"],
        "status": "已关闭", "reconciled": True, "issues": [],
        **{k: {"quantity_milli": quantities[k], "value_cents": quantities[k]} for k in QUANTITIES}}
    same_rows(data["rows"], [expected], "整个第三店订货履约行不同于原账")
    details = []
    for receipt_row in e.db.rows("SELECT * FROM procurement_receipts WHERE case_id=? ORDER BY id", (case["id"],)):
        move = one(e, "flow_stock_moves", receipt_row["stock_move_id"])
        require(move["case_id"] == case["id"] and move["item_id"] == line["item_id"] and move["purpose"] == "procurement_receipt"
            and move["quantity_milli"] == move["value_cents"] == receipt_row["quantity_milli"] == receipt_row["value_cents"] == 1000, "整范围实际收货原账未对平")
        details.append({"case_id": case["id"], "store_id": sid, "number": case["number"], "line_id": line["id"], "sku": line["sku"],
            "date": move["business_date"], "kind": "receive", "label": "实际到货", "source_id": receipt_row["id"], "stock_move_id": move["id"],
            "quantity_milli": 1000, "value_cents": 1000, "unit": line["unit"]})
    returned, move = one(e, "procurement_return_postings", purchase["return_posting"]["id"]), one(e, "flow_stock_moves", purchase["return_move"]["id"])
    require(returned["receipt_id"] == purchase["receipts"][0]["receipt"]["id"] and move["original_id"] == purchase["receipts"][0]["stock_move"]["id"], "整范围实退不是本第一批次原源")
    details.append({"case_id": case["id"], "store_id": sid, "number": case["number"], "line_id": line["id"], "sku": line["sku"],
        "date": move["business_date"], "kind": "return", "label": "实际退货", "source_id": returned["id"], "stock_move_id": move["id"],
        "quantity_milli": -500, "value_cents": -500, "unit": line["unit"]})
    require(len(details) == 3 and {d["stock_move_id"] for d in details} == {m["id"] for m in e.db.rows("SELECT * FROM flow_stock_moves WHERE store_id=?", (sid,))}, "报表遗漏本店实际收发")
    same_rows(data["details"], details, "整范围到退货明细不同于不可变原账")
    expected_metrics = {"procurement_cohort_order_count": 1, "procurement_cohort_line_count": 1,
        "procurement_cohort_complete": True, "procurement_cohort_issue_count": 0,
        **{"procurement_cohort_" + k + "_cents": quantities[k] for k in QUANTITIES}}
    require(data["complete"] is True and data["issues"] == [] and data["metrics"] == expected_metrics, "无旧简表整店批次KPI未完整/守恒")
    labels = ["原订货", "累计到货", "仍待到货", "已关闭未到", "待批准", "实际退货", "净留存"]
    base = data["tables"]["procurement_cohort_lines"]
    headers = ["门店", "采购单", "申请日期", "供应商", "物资编码", "物资名称", "单位", "当前进度"] + [x + "数量" for x in labels] + [x + "金额（元）" for x in labels] + ["来源核对"]
    values = [store["name"], case["number"], case["business_date"], header["supplier_name"], line["sku"], line["item_name"], line["unit"], expected["status"]] + [q(quantities[k]) for k in QUANTITIES] + [yuan(quantities[k]) for k in QUANTITIES] + ["已核对"]
    require(base["headers"] == headers and [r["values"] for r in base["rows"]] == [values]
        and base["rows"][0]["route"] == {"type": "case", "id": case["id"]}, "原批次整表/原单路由错误")
    require(all(base["rows"][0][k + "_milli"] == base["rows"][0][k + "_cents"] == quantities[k] for k in QUANTITIES), "原订货整表整数元数据不同于原账")
    details.sort(key=lambda r: (r["date"], r["stock_move_id"]))
    expected_values = [[store["name"], case["number"], d["date"], line["sku"], d["label"], d["source_id"], d["stock_move_id"], q(d["quantity_milli"]), line["unit"], yuan(d["value_cents"])] for d in details]
    detail_table = data["tables"]["procurement_cohort_postings"]
    require(detail_table["headers"] == ["门店", "采购单", "实际日期", "物资编码", "实际业务", "原确认记录", "库存流水", "数量", "单位", "库存价值变化（元）"]
        and [r["values"] for r in detail_table["rows"]] == expected_values
        and all(r["route"] == {"type": "case", "id": case["id"]} for r in detail_table["rows"]), "整范围到退货原表/原单路由错误")
    require(data["tables"]["procurement_cohort_issues"]["rows"] == [] and len(data["charts"]) == 1, "无旧简表来源却有差异/不完整图")
    chart = data["charts"][0]
    require(chart["id"] == "procurement_cohort_0" and chart["labels"] == labels and chart["unit"] == "quantity"
        and chart["series"] == [{"name": "升", "values": [float(Decimal(quantities[k]) / 1000) for k in QUANTITIES]}]
        and chart["table"] == "procurement_cohort_unit_0", "真实非空订货单位图不同于原账")
    dynamic = data["tables"][chart["table"]]
    require(dynamic["chart_only"] is True and dynamic["headers"] == headers and dynamic["rows"] == base["rows"]
        and set(data["tables"]) == {"procurement_cohort_lines", "procurement_cohort_postings", "procurement_cohort_issues", chart["table"]}, "动态单位原始行/整个表集合不完整")
    return {"case": case, "line": line, "header": header, "whole_scope_details": details, "whole_scope_metrics": expected_metrics}


def warehouse_oracle(e, data, sid, store, source, activation, purchase, period):
    stock, warehouse = M.item_stock(e, source["item"]["id"]), source["warehouse"]
    item, enrollment = stock["item"], stock["enrollment"]
    require({r["id"] for r in e.db.rows("SELECT id FROM flow_items WHERE store_id=?", (sid,))} == {item["id"]}
        and len(stock["balances"]) == 2 and item["quantity_milli"] == item["inventory_value_cents"] == 1500, "整范围新物资/期末两原位置不完整")
    original = M.facts(e, activation["case_id"])
    basis = zero_activation_basis(e, sid, activation["case_id"], item["id"], source["locations"][0]["id"])
    require(basis == activation["basis"] and enrollment == basis["enrollment"], "原批准/零分配/启用基准被修改")
    approved = [r for r in original["events"] if r["action"] == "warehouse_approve"]
    require(len(approved) == 1 and enrollment["case_id"] == original["case"]["id"] and local_day(approved[0]["occurred_at"]) == period["date_from"], "启用桥接不是当日唯一真实批准")
    stamp = datetime.fromisoformat(approved[0]["occurred_at"]).isoformat() + "Z"
    require(enrollment["baseline_quantity_milli"] == enrollment["baseline_value_cents"] == 0, "零期初原基准发生改变")
    issue = "请求期初不晚于启用日，午夜期初及启用前收发未知"
    locations = {r["id"]: r for r in source["locations"]}
    reasons = {"activation": "库位启用基准", "procurement_receipt": "采购实际验收", "procurement_return": "采购实际退回", "average_revaluation": "均价分摊调整"}
    expected, details, baselines = [], [], []
    for balance in stock["balances"]:
        require(balance["store_id"] == sid and balance["location_id"] in locations and balance["transit_case_id"] is None, "期末库位不是本店本次位置")
        location = locations[balance["location_id"]]
        entries = [r for r in stock["entries"] if r["balance_id"] == balance["id"]]
        base = [r for r in entries if r["case_id"] == enrollment["case_id"] and r["stock_move_id"] is None]
        require(not base, "零数量零价值启用被追加虚构库位流水")
        nonbase = [r for r in entries if r not in base]
        require(all(r["business_date"] == period["date_from"] and r["case_id"] in {activation["case_id"], purchase["case_id"]} and r["reason"] in reasons for r in entries), "实际来源跨日期/串单或出现未经声明原动作")
        expected.append({"item_id": item["id"], "store_id": sid, "sku": item["sku"], "name": item["name"], "unit": item["unit"],
            "balance_id": balance["id"], "warehouse_id": warehouse["id"], "warehouse": warehouse["name"], "location": location["name"],
            "transit_case_id": None, "period_complete": False, "closing_complete": True, "coverage_start": stamp, "issues": [issue],
            "opening": None, "in": None, "out": None, "closing": {"quantity_milli": balance["quantity_milli"], "value_cents": balance["value_cents"]},
            "revaluation_cents": None, "known_in_milli": sum(max(0, r["quantity_milli"]) for r in nonbase),
            "known_out_milli": sum(max(0, -r["quantity_milli"]) for r in nonbase), "known_value_delta_cents": sum(r["value_cents"] for r in nonbase)})
        if location["id"] == source["locations"][0]["id"]:
            require(location["id"] == basis["allocation_line"]["location_id"] and basis["allocation_line"]["quantity_milli"] == 0,
                "原启用零分配基准缺失/被当进货")
            baselines.append({"item_id": item["id"], "store_id": sid, "balance_id": balance["id"], "sku": item["sku"], "unit": item["unit"],
                "warehouse": warehouse["name"], "location": location["name"], "quantity_milli": 0, "value_cents": 0, "coverage_start": stamp, "case_id": enrollment["case_id"]})
        else:
            require(not base, "后续接收位置被冒充原启用基准")
        for r in entries:
            details.append({"item_id": item["id"], "store_id": sid, "balance_id": balance["id"], "sku": item["sku"], "name": item["name"], "unit": item["unit"],
                "warehouse": warehouse["name"], "location": location["name"], "source_id": r["id"], "case_id": r["case_id"], "stock_move_id": r["stock_move_id"],
                "date": r["business_date"], "quantity_milli": r["quantity_milli"], "value_cents": r["value_cents"], "label": reasons[r["reason"]], "is_baseline": r in base})
    same_rows(data["rows"], expected, "整店/双库位期初未知、期末整数原账不一致")
    same_rows(data["baselines"], baselines, "真实启用基准被替换/漏列")
    same_rows(data["details"], details, "全期间真实库位原流水遗漏/猜填")
    require(data["complete"] is False and data["closing_complete"] is True and data["metrics"] == {
        "warehouse_period_complete": False, "warehouse_period_closing_complete": True, "warehouse_period_gap_count": 2}, "未知期初被伪造完整/有据期末丢失")
    tables = data["tables"]
    total = tables["warehouse_period_balances"]
    headers = ["门店", "物资编码", "物资", "单位", "仓库", "库位或店内在途", "期初数量", "完整期间入库数量", "完整期间出库数量", "已知期末数量",
        "期初价值（元）", "入库有符号价值变动（元）", "出库有符号价值变动（元）", "均价分摊调整（元）", "已知期末价值（元）", "期间是否完整", "期末是否完整", "来源说明"]
    values = [[store["name"], item["sku"], item["name"], item["unit"], warehouse["name"], r["location"], "—", "—", "—", q(r["closing"]["quantity_milli"]),
        "—", "—", "—", "—", yuan(r["closing"]["value_cents"]), "有覆盖缺口", "完整", issue] for r in expected]
    require(total["headers"] == headers, "仓库期间原表字段不完整")
    same_rows([r["values"] for r in total["rows"]], values, "仓库期间未知值/说明被零或空替代")
    for r in total["rows"]:
        original_row = next(x for x in expected if x["location"] == r["values"][5])
        require(r["item_id"] == item["id"] and r["closing_quantity_milli"] == original_row["closing"]["quantity_milli"]
            and r["closing_value_cents"] == original_row["closing"]["value_cents"], "期末整表整数元数据不对应实际位置")
    require(tables["warehouse_period_baselines"]["headers"] == ["门店", "物资编码", "单位", "仓库", "库位或在途", "实际启用时刻（UTC）", "分配基准数量", "分配基准价值（元）"]
        and all(r["route"] == {"type": "case", "id": activation["case_id"]} for r in tables["warehouse_period_baselines"]["rows"]), "原基准完整字段/原批准单错误")
    same_rows([r["values"] for r in tables["warehouse_period_baselines"]["rows"]], [[store["name"], item["sku"], item["unit"], warehouse["name"], r["location"], stamp, "0", "0.00"] for r in baselines], "原基准整表不同源")
    details.sort(key=lambda r: (r["date"], r["source_id"]))
    wanted = [[store["name"], r["date"], item["sku"], item["unit"], warehouse["name"], r["location"], r["label"], r["source_id"], r["stock_move_id"] or "不新增门店收发", q(r["quantity_milli"]), yuan(r["value_cents"])] for r in details]
    require([r["values"] for r in tables["warehouse_period_entries"]["rows"]] == wanted
        and tables["warehouse_period_entries"]["headers"] == ["门店", "实际日期", "物资编码", "单位", "仓库", "库位或在途", "实际业务", "原库位流水", "原物资流水", "数量变化", "有符号价值变化（元）"]
        and all(r["route"] == {"type": "case", "id": d["case_id"]} and r["quantity_milli"] == d["quantity_milli"] and r["amount_cents"] == d["value_cents"] for r, d in zip(tables["warehouse_period_entries"]["rows"], details)), "库位原流水整表/原单关联错误")
    require(set(tables) == {"warehouse_period_balances", "warehouse_period_baselines", "warehouse_period_entries"} and len(data["charts"]) == 1, "期末图/三原表集合不完整")
    chart = data["charts"][0]
    require(chart["id"] == "warehouse_period_closing" and chart["unit"] == "cents" and chart["labels"] == [store["name"] + " · " + warehouse["name"]]
        and chart["series"] == [{"name": "账面价值", "values": [1500]}] and chart["table"] == "warehouse_period_balances", "已知期末图被冒充完整期间图/量值不符")
    return {"current_item": item, "enrollment": enrollment, "activation_basis": basis, "balances": stock["balances"], "entries": stock["entries"],
        "whole_scope_rows": expected, "whole_scope_baselines": baselines, "period_complete": False, "closing_complete": True,
        "historical_complete_window": "not_tested", "unknown_opening_not_zero": True}


async def procurement_check(e, cp, context, credentials, fixture, store, source, purchase, period):
    actor = await login_current(e, context, credentials, fixture["manager_key"], fixture["store_id"])
    data = await open_report(e, fixture["store_id"], "HK-153", "procurement", period)
    before = e.business_snapshot("before_complete_procurement_oracle")
    facts = procurement_oracle(e, data, fixture["store_id"], store, source, purchase, period)
    await expect(e.page.locator("#main .notice").filter(has_text="原订货与到退货来源可核对")).to_be_visible()
    await expect(e.page.locator("#main .notice.error, #main [role=alert]")).to_have_count(0)
    e.business_unchanged(before, "after_complete_procurement_oracle")
    shown, files = [], []
    for key in ("procurement_cohort_lines", "procurement_cohort_postings", "procurement_cohort_issues"):
        shown.append(await verify_table(e, data, key, "procurement"))
        files.append(await export(e, fixture["store_id"], actor, data, "procurement", key, period))
    graphic = await graph(e, data, "procurement_cohort_0")
    chart_panel = e.page.locator("#main > section.panel").filter(has=e.page.get_by_role("heading", name="订货履约数量（升）", exact=True))
    files.append(await export(e, fixture["store_id"], actor, data, "procurement", "procurement_cohort_unit_0", period,
        locator=chart_panel.locator('[data-act="inventory-report-export"][data-key="procurement_cohort_unit_0"]')))
    drill = await drill_original(e, data, "procurement_cohort_postings", data["tables"]["procurement_cohort_postings"]["rows"][0], "procurement", facts["case"])
    await cp.passed(actual_api=data, independent_db_oracle=facts, visible_whole_tables=shown, chart=graphic,
        actual_csv=files, original_drill=drill, whole_store_complete=True, legacy_purchase_removed=False,
        artificial_date_or_scope_changes=False, human_acceptance="pending")


async def warehouse_check(e, cp, context, credentials, fixture, store, source, activation, purchase, period):
    cp.start("HK-152")
    actor = await login_current(e, context, credentials, fixture["manager_key"], fixture["store_id"])
    data = await open_report(e, fixture["store_id"], "HK-152", "warehouses", period)
    unfiltered = warehouse_oracle(e, data, fixture["store_id"], store, source, activation, purchase, period)
    before = e.business_snapshot("before_complete_warehouse_filters")
    filters, reads = {}, []
    for name, row, code in (("item_id", source["item"], "sku"), ("warehouse_id", source["warehouse"], "code")):
        filters[name] = row["id"]
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/inventory-reports/warehouses") as pending:
            await M.choose(e, e.page.locator("#warehouse-report-filters"), 'select[name="' + name + '"]', row[code], row[code] + " · " + row["name"], row["id"])
        response = await pending.value
        data = await response.json()
        reads.append(await read_metadata(e, response, fixture["store_id"], {**period, **filters}))
        await expect(e.page.locator("#main .loading")).to_have_count(0)
        require(data["filters"][name] == row["id"], "原UI显式筛选没有取得当前真实来源")
        warehouse_oracle(e, data, fixture["store_id"], store, source, activation, purchase, period)
    facts = warehouse_oracle(e, data, fixture["store_id"], store, source, activation, purchase, period)
    warning = e.page.locator("#main .notice.error")
    await expect(warning).to_have_count(1)
    await expect(warning).to_have_text("全期间来源：有未知期初或覆盖缺口。期末来源：已知并可核对；这不代表全期间完整。", use_inner_text=False)
    await expect(e.page.locator("#main [role=alert]")).to_have_count(0)
    e.business_unchanged(before, "after_complete_warehouse_filters")
    shown, files = [], []
    for key in ("warehouse_period_balances", "warehouse_period_baselines", "warehouse_period_entries"):
        shown.append(await verify_table(e, data, key, "warehouses"))
        files.append(await export(e, fixture["store_id"], actor, data, "warehouses", key, period, filters=filters))
    graphic = await graph(e, data, "warehouse_period_closing")
    current_case = M.facts(e, activation["case_id"])["case"]
    drill = await drill_original(e, data, "warehouse_period_baselines", data["tables"]["warehouse_period_baselines"]["rows"][0], "warehouses", current_case)
    await cp.passed(actual_api=data, independent_db_oracle=facts, unfiltered_whole_store_oracle=unfiltered,
        native_filters=reads, visible_whole_tables=shown, actual_csv=files, original_drill=drill, closing_chart=graphic,
        unknown_period_notice_visible=True, original_period_complete=False, closing_complete=True,
        complete_functional_branches=True, complete_historical_period="not_tested", human_acceptance="pending")


async def session_pages(e, context, credentials, fixture, actors, contexts, *, third=False):
    saved, native = {}, {}
    for role, actor in actors.items():
        _, page = await SYS.fresh_identity(e, context, contexts)
        secret = credentials["users"][fixture[role + "_key"]]["password"]
        result = await SYS.native_login(e, actor, secret)
        if third:
            result = await SYS.switch_store(e, fixture["store_id"], actor, role)
        saved[role], native[role] = page, result
    return saved, native


async def admin_users_login(e, context, credentials, store):
    async with e.page.expect_response(lambda r: r.request.method == "GET"
            and urlsplit(r.url).path == "/api/users" and r.request.headers.get("x-store-id") == str(store)) as pending:
        actor = await login_as(e, context, credentials, "admin", "users", store)
    response = await pending.value
    body = await response.json()
    headers = await response.request.all_headers()
    require(response.status == 200 and headers.get("cookie") and headers.get("x-store-id") == str(store)
            and isinstance(body["items"], list), "原管理员当前店员工列表未完整就绪")
    await expect(e.page.locator("#main h1")).to_have_text("员工账号")
    e.observe("admin_users_ready", {"path": "/api/users", "method": "GET", "status": 200,
        "store_id": store, "cookie_present": True, "items": len(body["items"]), "native_ui": True})
    return actor


async def report_complete_source_business(e, context, credentials):
    cp, contexts, original_page = Checkpoint(e), [], e.page
    cp.start("HK-153")
    try:
        fixture, actors, original_roles, store = dependencies(e, cp)
        token = uuid.uuid4().hex[:10].upper()
        src = {"admin_store": e.manifest["stores"][0]["id"]}
        old_pages, before_logins = await session_pages(e, context, credentials, fixture, actors, contexts)
        e.page = original_page
        admin = await admin_users_login(e, context, credentials, src["admin_store"])
        access, refused = {}, {}
        for role, actor in actors.items():
            access[role] = await authorize(e, src, admin, actor, {**original_roles[role], fixture["store_id"]: role}, "source_append_" + role)
            refused[role] = await SYS.revoked_page(e, old_pages[role], actor["id"])
            e.page = original_page
        cp.note(original_access_append=access, original_old_logins=before_logins, native_old_session_refusals=refused)
        source = await masters(e, context, credentials, fixture, token)
        cp.note(native_new_store_masters=source)
        activation = await activate(e, context, credentials, fixture, source, token)
        cp.note(native_zero_activation=activation)
        purchase = await procure(e, context, credentials, fixture, source, token)
        cp.note(native_purchase_to_original_refund=purchase)
        day = local_day(M.facts(e, purchase["case_id"])["events"][0]["occurred_at"])
        require(day == datetime.now(timezone.utc).astimezone(ZONE).date().isoformat(), "本闭包跨过真实日期，停止而不改钟/回填来源")
        period = {"date_from": day, "date_to": day}
        await procurement_check(e, cp, context, credentials, fixture, store, source, purchase, period)
        await warehouse_check(e, cp, context, credentials, fixture, store, source, activation, purchase, period)
        authorized_pages, authorized_logins = await session_pages(e, context, credentials, fixture, actors, contexts, third=True)
        e.page = original_page
        admin = await admin_users_login(e, context, credentials, src["admin_store"])
        restored, final_read = {}, {}
        for role, actor in actors.items():
            restored[role] = await authorize(e, src, admin, actor, original_roles[role], "source_restore_" + role)
            require(restored[role]["current_access_version"] == access[role]["original_access_version"] + 2, "恢复授权版本没有严格递增两次")
            invalid = await SYS.revoked_page(e, authorized_pages[role], actor["id"])
            result = await SYS.native_login(e, actor, credentials["users"][fixture[role + "_key"]]["password"])
            require(set(result["store_ids"]) == set(original_roles[role]) and fixture["store_id"] not in result["store_ids"]
                and result["current_role"] == original_roles[role][result["active_store_id"]]
                and ACCESS.memberships(e, actor["id"]) == original_roles[role], "恢复原授权后本人仍有第三店权限或原岗位丢失")
            await expect(e.page.locator(f'#store option[value="{fixture["store_id"]}"]')).to_have_count(0)
            final_read[role] = {"old_authorized_session_refused": invalid, "native_relogin": result,
                "original_store_roles_restored": True, "revoked_old_sessions_revived": False}
            e.page = original_page
        restoration = {"before_restoration_native_third_store_logins": authorized_logins, "native_access_restore": restored,
            "final_original_scope_relogin": final_read, "all_three_original_roles_and_account_fields_restored": True,
            "all_other_original_business_users_grants_receipts_and_sessions_protected": True}
        sources = {"store_id": fixture["store_id"], "supplier_id": source["supplier"]["id"], "account_id": source["account"]["id"],
            "item_id": source["item"]["id"], "warehouse_id": source["warehouse"]["id"], "location_ids": [r["id"] for r in source["locations"]],
            "enrollment_id": activation["db"]["enrollment"]["id"], "activation_case_id": activation["case_id"], "purchase_case_id": purchase["case_id"],
            "receipt_ids": [r["receipt"]["id"] for r in purchase["receipts"]], "payment_ids": [r["id"] for r in purchase["payments"]],
            "cash_ids": [r["id"] for r in purchase["cash"]], "stock_move_ids": [r["id"] for r in purchase["stock"]["stock_moves"]],
            "warehouse_entry_ids": [r["id"] for r in purchase["stock"]["entries"]], "period": period,
            "stock_quantity_milli": 1500, "stock_value_cents": 1500, "paid_net_cents": 1500,
            "full_historical_warehouse_period_tested": False, "all_old_source_rows_and_other_stores_protected": True}
        cp.finish(sources, restoration)
        e.observe("complete_source_original_report_checkpoint", {"path": str(cp.path), "report_sources": sources,
            "business_accepted": False, "human_acceptance": "pending", "full_193_business_acceptance": False})
    except Exception as error:
        cp.failed(error)
        raise
    finally:
        e.page = original_page
        if e.response_jobs:
            await asyncio.gather(*list(e.response_jobs))
        for separate in contexts:
            await separate.close()


REPORT_COMPLETE_SOURCE_SCENARIOS = ((SCENARIO, report_complete_source_business, 1500),)
