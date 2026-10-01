"""Unregistered native reminder candidate: three checks and HK099 partial.

Only original visible forms write. The database helper is SELECT-only; all
business data and credentials belong to the current external synthetic run.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import login_as, require
from sales_order_business import fixed_dependency, checkpoint_evidence
from vehicle_purchase_business import select_value, checkbox
from customer_service_business import fields, care_facts, care_rendered
from system_management_business import fresh_identity, native_login, switch_store

SCENARIO = "customer-reminders-hk105-106-112"
CUSTOMER = "customer-followon-hk100-101-102-103-104-110-111"
SYSTEM = "system-management-hk189-191"
SYSTEM_FOLLOWON = "system-followon-hk192-193"
CARE = "/api/customer-service"
OC = "/api/observation-corrections"
REQUIREMENTS = (("HK-105", "保养提醒"), ("HK-106", "保修提醒"), ("HK-112", "首保提醒回访"))
VERSION = {"version", "updated_at"}
PK = {t: "id" for t in (
    "flow_cases", "flow_tasks", "flow_events", "audit_logs", "flow_customers",
    "care_customer_vehicles", "care_vehicle_observations", "care_records", "care_receipts",
    "care_history_links", "care_history_grants", "care_reminder_rules", "group_identities",
    "group_identity_links", "group_events", "observation_correction_events",
    "observation_correction_effects", "observation_insurance_invalidations",
    "observation_reminder_invalidations", "observation_reminder_replacements",
    "observation_correction_receipts", "flow_files", "file_security", "file_scan_events",
    "insurance_quotes", "insurance_submissions", "insurance_results", "insurance_terminations",
    "insurance_termination_reviews", "insurance_termination_consents",
    "insurance_termination_applications", "insurance_termination_cancellations", "stores")}
PK.update({t: "case_id" for t in ("care_cases", "observation_corrections", "observation_reminder_bases")})
PK["insurance_orders"] = "id"
AFFECTED = {"delivery": {"first_service", "maintenance"}, "odometer": {"first_service", "maintenance"},
            "maintenance": {"maintenance"}, "first_service": {"first_service", "maintenance"},
            "warranty": {"warranty"}, "insurance": {"renewal"}}
LABELS = {"maintenance": "保养提醒", "first_service": "首保提醒", "warranty": "保修到期提醒"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def day():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def rows(e, table):
    require(table in PK, "提醒未核准原表：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {PK[table]}")


def one(e, table, key):
    require(table in PK, "提醒未核准原记录：" + table)
    found = e.db.rows(f"SELECT * FROM {table} WHERE {PK[table]}=?", (key,))
    require(len(found) == 1, "提醒原记录缺失或不唯一：" + table)
    return found[0]


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        checks = []
        for key, title in REQUIREMENTS:
            source = catalog[key]
            require(source["title"] == title and source["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in source["acceptance_checks"]),
                    "提醒原题名/check未核准：" + key)
            checks.append({"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business",
                                       "status": "not_tested", "evidence": {}}],
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"}})
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [k for k, _ in REQUIREMENTS],
            "source_contract_sha256": self.digest, "requirements": checks,
            "complete": False, "passed": False, "business_accepted": False,
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "execution": "native_browser_original_forms", "human_acceptance": "pending",
            "partial_requirements": [{"id": "HK-099", "title": "车辆档案", "status": "not_tested",
                "business_accepted": False, "acceptance_check_submitted": False, "evidence": {},
                "planned_pending": ["真正跨授权截止日后的读取", "原单快照及逐件文件独立授权"]}],
            "conditions": {"synthetic_data_only": True, "messages_sent": False,
                           "real_service_or_external_contact_acceptance": False, "production_acceptance": False}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        require(self.active is None, "前项提醒仍在办理")
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active.update(status="running", evidence_action_start=len(self.e.actions))
        self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    async def passed(self, evidence):
        json.dumps(evidence, ensure_ascii=False)
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active.update(status="passed", evidence_action_end=len(self.e.actions))
        self.active["acceptance_checks"][0].update(status="passed", evidence=evidence)
        self.active = None
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.active["acceptance_checks"][0]["error"] = self.e.scrub(error)
        self.report.update(error=self.e.scrub(error), failed_requirement=self.active["id"] if self.active else "source_or_hk099_partial")
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "三项提醒未完整执行")
        require(self.report["partial_requirements"][0]["status"] == "partial", "本批车辆摘要子范围未执行")
        self.report.update(complete=True, passed=True, executed_requirements=3, passed_requirements=3, report_sources=sources)
        self.save()
        self.e.observe("customer_reminders_checkpoint", {"passed_checks": 3, "hk099": "partial",
            "true_history_grant_expiry": "planned_pending", "full_193_business_acceptance": False})


class Guard:
    """Whole old rows remain; only finite columns and exact append counts vary."""
    def __init__(self, e, label, actor, store, *, appends, updates=None):
        self.e, self.label, self.actor, self.store = e, label, actor, store
        self.appends, self.updates = dict(appends), updates or {}
        allowed = self.appends.keys() | self.updates.keys()
        require(allowed <= PK.keys(), "提醒保护表未经核准")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in allowed}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.old.keys(), "提醒改变无关原表：" + str(sorted(changed)))
        self.additions, updated = {}, {}
        for table, old in self.old.items():
            current = {r[PK[table]]: r for r in rows(self.e, table)}
            oldkeys = {r[PK[table]] for r in old}
            added = [r for key, r in current.items() if key not in oldkeys]
            require(len(added) == self.appends.get(table, 0), "提醒新增数不匹配：" + table)
            self.additions[table] = added
            updated[table] = []
            for original in old:
                key = original[PK[table]]
                require(key in current, "提醒删除原事实：" + table)
                columns = {k for k in original if original[k] != current[key][k]}
                require(columns <= self.updates.get(table, {}).get(key, set()),
                        "提醒覆盖未授权旧行/列：" + table + "/" + str(key) + "/" + str(sorted(columns)))
                if columns:
                    updated[table].append({"id": key, "columns": sorted(columns)})
            for row in added:
                if "store_id" in row:
                    require(row["store_id"] == self.store, "提醒新事实串店：" + table)
                for key in ("actor_id", "created_by", "confirmed_by", "granted_by"):
                    if key in row:
                        require(row[key] == self.actor["id"], "提醒新事实借用身份：" + table)
        result = {"label": self.label, "changed_tables": sorted(changed),
            "appended_ids": {t: [r[PK[t]] for r in v] for t, v in self.additions.items() if v},
            "updated_columns": {t: v for t, v in updated.items() if v},
            "all_other_tables_unchanged": True, "all_other_old_rows_and_columns_unchanged": True}
        self.e.observe("customer_reminders_guard", result)
        return result


def match(response, path, method="GET"):
    return response.request.method == method and urlsplit(response.url).path == path


async def read_page(e, route, title, path):
    before = e.business_snapshot("before_reminder_read")
    async with e.page.expect_response(lambda r: match(r, path)) as pending:
        e.action("navigate", "读取原车辆/提醒页面", route=route)
        if urlsplit(e.page.url).fragment == route:
            await e.page.reload(wait_until="domcontentloaded")
        else:
            await e.page.goto(e.origin + "/#" + route, wait_until="domcontentloaded")
    response = await pending.value
    require(response.status == 200, "原车辆/提醒读取失败：" + path)
    body = await response.json()
    await expect(e.page.locator("#main h1")).to_have_text(title)
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    e.business_unchanged(before, "after_reminder_read")
    return body


async def login(e, context, credentials, key, route, title, path):
    actor = await login_as(e, context, credentials, key, "parameters", 1)
    body = await read_page(e, route, title, path)
    return actor, body


async def form(e, selector, title):
    control = e.page.locator(selector)
    await expect(control).to_have_count(1)
    await expect(control).to_be_visible()
    await expect(control).to_be_enabled()
    await e.click(selector, "打开原表单：" + title)
    await expect(e.page.locator("#modal-title")).to_have_text(title)


async def submit(e, actor, store, path, guard, *, render, status=200, method="POST",
                 action=None, payload=None, receipt_table="care_receipts", click='#modal form button[type="submit"]'):
    # Capture actual UI rendering; creations bind the GET to the new POST ID.
    target, seen = None, []
    future = asyncio.get_running_loop().create_future()

    def observe(response):
        nonlocal target
        if response.request.method == "GET":
            seen.append(response)
            if target is not None and match(response, target) and not future.done():
                future.set_result(response)

    e.page.on("response", observe)
    try:
        await expect(e.page.locator(click)).to_be_visible()
        await expect(e.page.locator(click)).to_be_enabled()
        async with e.page.expect_response(lambda r: match(r, path, method)) as pending:
            await e.click(click, "本人单次确认原办理")
        response = await pending.value
        body = await response.json()
        require(response.status == status, "原提醒 HTTP " + str(response.status) + "：" + e.scrub(body.get("detail", "")))
        target = render(body) if callable(render) else render
        for read in seen:
            if match(read, target) and not future.done():
                future.set_result(read)
        read = await asyncio.wait_for(future, 30)
        shown = await read.json()
        require(read.status == 200, "原提交后的明确原实体读取失败：" + target)
        headers, request = await response.request.all_headers(), response.request.post_data_json
        require(headers.get("cookie") and headers.get("x-csrf-token") and headers.get("x-app-request") == "1"
                and headers.get("x-store-id") == str(store), "原提醒同源Cookie/CSRF/当前店不完整")
        if action is not None:
            require(isinstance(request, dict) and len(request.get("request_id", "")) >= 16, "原提醒请求号缺失")
            actual = payload(request) if callable(payload) else payload
            require(receipt_table in {"care_receipts", "observation_correction_receipts"}, "原回执表未核准")
            found = e.db.rows(f"SELECT * FROM {receipt_table} WHERE request_key=?", (request["request_id"],))
            require(len(found) == 1
                    and found[0]["store_id"] == store and found[0]["actor_id"] == actor["id"]
                    and found[0]["digest"] == digest([action, actual]) and decoded(found[0]["result"]) == body,
                    "原回执未绑定精确员工/门店/参数/结果")
        await expect(e.page.locator("#modal")).not_to_be_visible()
        protected = guard.finish()
        metadata = {"method": method, "path": path, "status": status, "actor_id": actor["id"], "store_id": store,
                    "native_ui": True, "render_path": target, "submitted_version": request.get("version") if isinstance(request, dict) else None,
                    "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest() if isinstance(request, dict) and request.get("request_id") else None,
                    "guard": protected}
        e.observe("customer_reminders_original_submit", metadata)
        return body, request, shown, metadata
    finally:
        e.page.remove_listener("response", observe)
        if not future.done():
            future.cancel()


def dependencies(e, cp):
    root, runtime = Path(e.manifest["evidence_root"]).resolve(), Path(e.manifest["runtime_root"]).resolve()
    require(e.manifest.get("synthetic_data_only") is True and Path(e.manifest["database_path"]).resolve().is_relative_to(runtime),
            "提醒仅允许本轮仓库外合成库")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance["snapshot_stable"] is True, "提醒当前镜像未冻结")
    for name in (Path(__file__).name, "business_acceptance_catalog.json", "customer_followon_business.py",
                 "system_management_business.py", "system_followon_business.py", "sales_order_business.py",
                 "sales_business.py", "vehicle_purchase_business.py", "customer_service_business.py"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(),
                "提醒脚本不是同轮固定镜像：" + name)
    cp.report["provenance"] = {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")}
    cp.report["mirror"] = {k: provenance[k] for k in ("source_sha256", "script_sha256")}
    customer_report, system = fixed_dependency(e, cp, CUSTOMER), fixed_dependency(e, cp, SYSTEM)
    summary = json.loads((root / "browser-click-report.json").read_text(encoding="utf-8"))
    if any(r["id"] == SYSTEM_FOLLOWON for r in summary["scenarios"]):
        optional = fixed_dependency(e, cp, SYSTEM_FOLLOWON)
        require(optional.get("temporary_auditor_restored") is True, "系统后继临时岗位未恢复")
    source = customer_report["report_sources"]
    customer = one(e, "flow_customers", source["customer_id"])
    vehicle = one(e, "care_customer_vehicles", source["customer_vehicle_id"])
    order = one(e, "flow_cases", source["delivered_order_id"])
    require(customer["store_id"] == vehicle["store_id"] == order["store_id"] == 1
            and vehicle["customer_id"] == order["customer_id"] == customer["id"] and vehicle["active"]
            and order["state"] == "delivered" and order["vehicle_id"] == source["delivered_vehicle_id"]
            and customer["contact_allowed"] and customer["phone"], "原客户/交付CV/联系许可来源不一致")
    history = [r for r in rows(e, "care_history_links") if r["vehicle_id"] == vehicle["id"]]
    require(history and any(r["case_id"] == order["id"] for r in history), "父交付车辆缺真实非空服务摘要")
    identity = one(e, "group_identities", vehicle["customer_identity_id"])
    require(identity["kind"] == "customer" and identity["name"] == customer["name"], "父明确集团客户身份缺失")
    staff = checkpoint_evidence(system, "HK-191")["staff_actions"]
    require(len(staff) >= 2 and staff[0]["default_sales"] is True, "父新员工非真实原UI来源")
    found = e.db.rows("SELECT id,username,display_name,role,active,must_change_password FROM users WHERE id=?", (staff[0]["user_id"],))
    require(len(found) == 1, "父接收员工不唯一")
    receiver = found[0]
    require(receiver["role"] == "sales" and receiver["active"] and not receiver["must_change_password"], "父员工未实际改初始密码或已停用")
    role_rows = e.db.rows("SELECT store_id,role FROM user_stores WHERE user_id=? ORDER BY store_id", (receiver["id"],))
    require({r["store_id"]: r["role"] for r in role_rows} == {int(k): v for k, v in staff[0]["store_roles"].items()}
            and any(r["store_id"] == 2 and r["role"] == "service" for r in role_rows), "接收员工当前明确二店岗位已变化")
    pointers = [r["value"] for r in json.loads((root / SYSTEM / "observations.json").read_text(encoding="utf-8"))
                if r["label"] == "synthetic_system_private_credentials"]
    require(len(pointers) == 1 and pointers[0]["credentials_in_evidence"] is False, "新员工私有凭据指针不唯一")
    path = Path(pointers[0]["path"]).resolve()
    require(path.parent == runtime and path.name.startswith("system-management-accounts-") and path.is_file(), "凭据不在本轮runtime")
    private = json.loads(path.read_text(encoding="utf-8"))
    require(private["synthetic_data_only"] is True, "员工凭据不是本轮合成来源")
    for account in private["accounts"].values():
        e.secrets.extend(v for k, v in account.items() if isinstance(v, str) and k not in {"username", "current_password_stage"})
    secret = private["accounts"]["receiver"]
    require(secret["id"] == receiver["id"] and secret["username"] == receiver["username"]
            and secret.get("current_password_stage") in secret, "当前凭据阶段串员工")
    fixture = e.manifest["business_fixtures"]["sales_order"]
    for role in ("sales", "service", "manager"):
        actor = e.manifest["users"][fixture[role + "_key"]]
        active = e.db.rows("SELECT id,active FROM users WHERE id=?", (actor["id"],))
        require(len(active) == 1 and active[0]["active"] and e.db.rows("SELECT role FROM user_stores WHERE user_id=? AND store_id=1", (actor["id"],)) == [{"role": role}], "提醒缺实际本店岗位：" + role)
    require(customer["owner_id"] == e.manifest["users"][fixture["sales_key"]]["id"], "本批销售非父客户本人")
    require(not e.db.rows("SELECT id FROM business_entity_policies WHERE store_id IN (1,2)"), "经营主体策略需另行有限前置，不能未知放宽")
    cp.report["source_preconditions"] = {"customer_id": customer["id"], "delivered_vehicle_relation_id": vehicle["id"],
        "delivered_order_id": order["id"], "local_history_link_ids": [r["id"] for r in history],
        "receiver_id": receiver["id"], "receiver_current_store_roles": role_rows, "private_credentials_in_evidence": False}
    cp.save()
    return {"fixture": fixture, "customer": customer, "delivered_cv": vehicle, "history": history,
            "receiver": receiver, "password": secret[secret["current_password_stage"]]}


def effective(e, vehicle_id, *, inactive=False):
    result = []
    for original in rows(e, "care_vehicle_observations"):
        if original["vehicle_id"] != vehicle_id:
            continue
        values = {k: original[k] for k in ("id", "vehicle_id", "kind", "observed_date", "odometer_km", "valid_until", "source_reference", "evidence_id")}
        effects = [r for r in rows(e, "observation_correction_effects") if r["observation_id"] == original["id"]]
        effect = effects[-1] if effects else None
        correction = one(e, "observation_corrections", effect["case_id"]) if effect else None
        if correction and correction["operation"] == "replace":
            values.update(decoded(correction["proposed"]))
        ended = [r for r in rows(e, "observation_insurance_invalidations") if r["observation_id"] == original["id"]]
        business = [r for r in rows(e, "insurance_results") if r["observation_id"] == original["id"]]
        require(len(ended) <= 1 and len(business) <= 1, "观察保险来源不唯一")
        values.update(effect_id=effect["id"] if effect else None,
            active=not bool(ended) and not bool(correction and correction["operation"] == "retract"),
            source_type="insurance_result" if business else "manual_observation",
            source_case_id=business[0]["case_id"] if business else None, odometer_measured=not bool(business),
            insurance_invalidation_id=ended[0]["id"] if ended else None)
        if business:
            values["odometer_km"] = None
        values["digest"] = digest(values)
        if values["active"] or inactive:
            result.append(values)
    return result


def insurance_sources(e, vehicles):
    """Pre-integration unknown sync is a stop, never a table-wide exemption."""
    checked = []
    for order in rows(e, "insurance_orders"):
        if order["customer_vehicle_id"] not in {r["id"] for r in vehicles}:
            continue
        plans = [p for p in rows(e, "insurance_terminations") if p["case_id"] == order["id"] and p["external_result"] == "terminated"
                 and any(a["plan_id"] == p["id"] for a in rows(e, "insurance_termination_applications"))]
        for plan in plans:
            source, quote = one(e, "flow_cases", order["id"]), one(e, "insurance_quotes", plan["quote_id"])
            def unique(table):
                found = [r for r in rows(e, table) if r["plan_id"] == plan["id"]]
                require(len(found) == 1, "终止保险原链缺失：" + table)
                return found[0]
            application = unique("insurance_termination_applications")
            review, consent = unique("insurance_termination_reviews"), unique("insurance_termination_consents")
            issued = [r for r in rows(e, "insurance_results") if r["case_id"] == source["id"] and r["outcome"] == "issued"
                      and one(e, "insurance_submissions", r["submission_id"])["quote_id"] == quote["id"]]
            require(len(issued) == 1 and issued[0]["observation_id"] is not None, "终止保险缺同报价实际出保观察")
            issued = issued[0]
            original = one(e, "care_vehicle_observations", issued["observation_id"])
            vehicle = one(e, "care_customer_vehicles", original["vehicle_id"])
            require(source["kind"] == "insurance" and source["flow_version"] == 3
                    and quote["case_id"] == source["id"] == plan["case_id"]
                    and review["decision"] == "approved" and review["actor_id"] != plan["actor_id"]
                    and consent["digest"] == plan["digest"]
                    and not any(r["plan_id"] == plan["id"] for r in rows(e, "insurance_termination_cancellations")), "终止保险原独立审批/客户同意/执行来源不完整")
            payload = {k: plan[k] for k in ("quote_id", "evidence_id", "reason", "retained_cents", "external_result")}
            payload["returns"] = decoded(plan["returns"])
            require(plan["digest"] == digest({"operation": "insurance_termination", "payload": payload}), "终止保险方案摘要不完整")
            require(order["customer_vehicle_id"] == vehicle["id"] and source["customer_id"] == vehicle["customer_id"]
                    and order["vin"] == vehicle["vin"] and original["kind"] == "insurance"
                    and original["valid_until"] == quote["end_date"] and original["observed_date"] == issued["business_date"]
                    and original["evidence_id"] == issued["evidence_id"] and original["actor_id"] == issued["actor_id"], "保险原观察与同客户/VIN/日期/原件不一致")
            for fact in (issued, plan, review, consent, application):
                file = one(e, "flow_files", fact["evidence_id"])
                security = [r for r in rows(e, "file_security") if r["file_id"] == file["id"]]
                require(file["case_id"] == source["id"] and file["store_id"] == 1 and not file["generated"]
                        and len(security) == 1 and security[0]["state"] == "structure_only", "保险同步原件不是本轮可用原件")
            prior = [r for r in rows(e, "observation_insurance_invalidations") if r["observation_id"] == original["id"]]
            require(len(prior) == 1, "尚有待同步保险失效来源，需精确增量授权，停止本候选：" + str(source["id"]))
            invalidation = prior[0]
            require(all(invalidation[k] == value for k, value in {
                "source_case_id": source["id"], "vehicle_id": vehicle["id"], "result_id": issued["id"],
                "plan_id": plan["id"], "application_id": application["id"], "evidence_id": application["evidence_id"], "store_id": 1}.items()),
                "既有保险失效原链字段不一致")
            checked.append({"case_id": source["id"], "observation_id": original["id"], "plan_id": plan["id"], "invalidation_id": invalidation["id"]})
    return checked


def role(e, user_id, store):
    active = e.db.rows("SELECT active,role FROM users WHERE id=?", (user_id,))
    stores = e.db.rows("SELECT role FROM user_stores WHERE user_id=? AND store_id=?", (user_id, store))
    if len(active) != 1 or not active[0]["active"]:
        return None
    if active[0]["role"] == "admin":
        return "admin"
    return (stores[0]["role"] or active[0]["role"]) if len(stores) == 1 else None


def generation_plan(e):
    as_of = day()
    vehicles = [r for r in rows(e, "care_customer_vehicles") if r["store_id"] == 1 and r["active"]]
    require(len(vehicles) <= 500, "本店有效车辆超过原一次检查上限，停止本候选")
    insurance = insurance_sources(e, vehicles)
    rules = [r for r in rows(e, "care_reminder_rules") if r["store_id"] == 1 and r["active"]]
    expected, skipped = [], []
    for vehicle in vehicles:
        observations = effective(e, vehicle["id"])
        pending = [r for r in rows(e, "observation_corrections") if r["vehicle_id"] == vehicle["id"] and one(e, "flow_cases", r["case_id"])["state"] == "approval"]
        for rule in rules:
            kind = rule["kind"]
            if any(kind in AFFECTED[one(e, "care_vehicle_observations", r["observation_id"])["kind"]] for r in pending):
                continue
            if kind == "first_service" and any(o["kind"] == "first_service" for o in observations):
                continue
            kinds = {"first_service": {"delivery"}, "maintenance": {"delivery", "maintenance", "first_service"}, "warranty": {"warranty"}, "renewal": {"insurance"}}[kind]
            baselines = [o for o in observations if o["kind"] in kinds]
            if not baselines:
                continue
            baseline = baselines[-1]
            measured = [o for o in observations if o["odometer_measured"] and o["odometer_km"] is not None]
            current = measured[-1] if measured else None
            if kind in {"warranty", "renewal"}:
                target = date.fromisoformat(baseline["valid_until"]) if baseline["valid_until"] else None
                trigger = target is not None and as_of >= target - timedelta(days=rule["lead_days"])
            else:
                target = date.fromisoformat(baseline["observed_date"]) + timedelta(days=rule["interval_days"]) if rule["interval_days"] else None
                trigger = bool(target and as_of >= target - timedelta(days=rule["lead_days"])) or bool(rule["interval_km"] and current and baseline["odometer_km"] is not None
                    and current["odometer_km"] >= baseline["odometer_km"] + rule["interval_km"] - rule["lead_km"])
            if not trigger:
                continue
            old = [c for c in rows(e, "care_cases") if c["vehicle_id"] == vehicle["id"] and c["subtype"] == kind and c["rule_id"] is not None
                   and (c["baseline_observation_id"] == baseline["id"] or kind in {"renewal", "warranty"} and c["baseline_observation_id"]
                        and next(o for o in effective(e, vehicle["id"], inactive=True) if o["id"] == c["baseline_observation_id"])["valid_until"] == baseline["valid_until"])]
            eligible, stop = [], False
            for care in old:
                state = one(e, "flow_cases", care["case_id"])["state"]
                invalid = [r for r in rows(e, "observation_reminder_invalidations") if r["case_id"] == care["case_id"]]
                if state in {"pending", "working", "completed"} or not any(r["closed_open_task"] for r in invalid):
                    stop = True
                    break
                eligible.append(care["case_id"])
            if stop:
                continue
            ops = {"admin", "manager", "service", "customer_service"}
            if role(e, rule["assignee_id"], 1) not in ops or role(e, rule["approved_by"], 1) not in {"admin", "manager"}:
                skipped.append({"rule_id": rule["id"], "reason": "本店规则经办或批准岗位已变化，请主管复核规则"})
                continue
            token = digest([baseline["id"], baseline["effect_id"], current["id"] if current else None, current["effect_id"] if current else None, eligible])[:30]
            reminder_key = f'oc:1:{vehicle["id"]}:{kind}:{token}'
            if any(c["reminder_key"] == reminder_key for c in rows(e, "care_cases")):
                continue
            snapshot = {"baseline": baseline, "current": current, "rule_id": rule["id"], "rule_version": rule["version"],
                "triggered_on": as_of.isoformat(), "rule": {k: rule[k] for k in ("kind", "name", "interval_days", "interval_km", "lead_days", "lead_km", "assignee_id", "approved_by")}}
            expected.append({"vehicle_id": vehicle["id"], "customer_id": vehicle["customer_id"], "rule": rule,
                "baseline": baseline, "current": current, "target": target.isoformat() if target else None,
                "eligible": eligible, "key": reminder_key, "cycle": f'1:{vehicle["id"]}:{kind}:observation:{baseline["id"]}', "snapshot": snapshot})
    return {"day": as_of.isoformat(), "vehicles": vehicles, "rules": rules, "expected": expected, "skipped": skipped, "insurance_sources": insurance}


async def generate(e, actor, label):
    await read_page(e, "customer-reminders", "车辆提醒与续保提取", CARE + "/reminders/rules")
    plan = generation_plan(e)
    n = len(plan["expected"])
    replacements = sum(len(p["eligible"]) for p in plan["expected"])
    guard = Guard(e, label, actor, 1, appends={"flow_cases": n, "care_cases": n, "flow_tasks": n,
        "care_records": n, "flow_events": 2*n, "audit_logs": 2*n, "observation_reminder_bases": n,
        "observation_reminder_replacements": replacements, "observation_correction_receipts": 1},
        updates={"care_customer_vehicles": {v["id"]: VERSION for v in plan["vehicles"]}})
    body, request, _, metadata = await submit(e, actor, 1, CARE + "/reminders/generate", guard,
        render=CARE + "/reminders/rules", action="generate", payload={"day": plan["day"], "automatic": False},
        receipt_table="observation_correction_receipts", click='#main [data-act="care-generate"]')
    require(body["as_of"] == plan["day"] and body["automatic"] is False and body["skipped"] == plan["skipped"]
            and len(body["created"]) == n, "本店完整应生成/跳过集合不一致")
    bykey = {r["reminder_key"]: r for r in guard.additions["care_cases"]}
    require(set(bykey) == {p["key"] for p in plan["expected"]}, "本店生成包含名单外或遗漏准确基准")
    actual = []
    for p in plan["expected"]:
        c = bykey[p["key"]]
        case = one(e, "flow_cases", c["case_id"])
        basis = one(e, "observation_reminder_bases", case["id"])
        tasks = [r for r in guard.additions["flow_tasks"] if r["case_id"] == case["id"]]
        records = [r for r in guard.additions["care_records"] if r["case_id"] == case["id"]]
        events = [r for r in guard.additions["flow_events"] if r["case_id"] == case["id"]]
        audits = [r for r in guard.additions["audit_logs"] if r["entity_id"] == case["id"] and r["entity_type"] == "flow"]
        require(case["kind"] == "customer_care" and case["flow_version"] == 2 and case["state"] == "pending"
                and case["customer_id"] == p["customer_id"] and case["owner_id"] == p["rule"]["assignee_id"]
                and case["created_by"] == actor["id"] and case["business_date"] == case["due_date"] == plan["day"], "规则生成原Case归属/类型/真实日期不一致")
        require(c["vehicle_id"] == p["vehicle_id"] and c["rule_id"] == p["rule"]["id"] and c["rule_version"] == p["rule"]["version"]
                and c["subtype"] == p["rule"]["kind"] and c["baseline_observation_id"] == p["baseline"]["id"]
                and c["generation_mode"] == "rule_requested" and c["rule_approved_by"] == p["rule"]["approved_by"], "新提醒原来源/模式不一致")
        require(basis["vehicle_id"] == p["vehicle_id"] and basis["baseline_id"] == p["baseline"]["id"]
                and basis["current_id"] == (p["current"]["id"] if p["current"] else None)
                and basis["baseline_effect_id"] == p["baseline"]["effect_id"]
                and basis["current_effect_id"] == (p["current"]["effect_id"] if p["current"] else None)
                and basis["cycle_key"] == p["cycle"] and decoded(basis["snapshot"]) == p["snapshot"], "新提醒冻结日期/公里/规则版本不一致")
        require(len(tasks) == len(records) == 1 and tasks[0]["key"] == "care_handle" and tasks[0]["status"] == "open"
                and tasks[0]["assignee_id"] == case["owner_id"] and tasks[0]["due_date"] == plan["day"]
                and records[0]["action"] == "create" and records[0]["actor_id"] == actor["id"], "新提醒本人任务/创建记录不一致")
        require([r["action"] for r in events] == ["care_create", "observation_reminder_basis"]
                and [r["action"] for r in audits] == ["flow_care_create", "flow_observation_reminder_basis"]
                and all(r["actor_id"] == actor["id"] for r in events + audits), "规则生成两事件/两审计不一致")
        replacement = [r for r in guard.additions["observation_reminder_replacements"] if r["replacement_case_id"] == case["id"]]
        require([r["previous_case_id"] for r in replacement] == p["eligible"], "新提醒替代谱系不一致")
        require({"case_id": case["id"], "number": case["number"], "subtype": c["subtype"]} in body["created"], "原生成响应缺真实新单")
        actual.append({"case_id": case["id"], "vehicle_id": p["vehicle_id"], "subtype": c["subtype"],
                       "rule_id": p["rule"]["id"], "basis": {**basis, "snapshot": decoded(basis["snapshot"])}, "replacement_ids": [r["id"] for r in replacement]})
    for v in plan["vehicles"]:
        current = one(e, "care_customer_vehicles", v["id"])
        require(current["version"] > v["version"] and all(current[k] == value for k, value in v.items() if k not in VERSION), "生成未精确touch本店全部有效CV或改变关系")
    await expect(e.page.locator("#main")).to_contain_text(f"新建 {n} 条内部任务")
    result = {"label": label, "all_active_vehicle_ids": [v["id"] for v in plan["vehicles"]],
              "active_rule_ids": [r["id"] for r in plan["rules"]], "created": actual, "skipped": body["skipped"],
              "insurance_sources_already_synchronized": plan["insurance_sources"], "native": metadata,
              "zero_created_still_touches_finite_vehicles": True}
    e.observe("customer_reminders_full_store_generation", result)
    return result


async def vehicle_view(e, vehicle_id):
    row = one(e, "care_customer_vehicles", vehicle_id)
    value = await read_page(e, "customer-vehicles/" + str(vehicle_id), "客户车辆 · " + (row["plate"] or row["vin"]), CARE + "/vehicles/" + str(vehicle_id))
    require(all(value["vehicle"][k] == row[k] for k in ("id", "store_id", "version", "customer_id", "customer_identity_id", "vehicle_identity_id", "vin", "plate", "model_name", "active", "identity_source", "created_by")), "CV原API/DB事实不一致")
    original = [r for r in rows(e, "care_vehicle_observations") if r["vehicle_id"] == vehicle_id]
    require([r["id"] for r in value["observations"]] == [r["id"] for r in reversed(original)], "CV原观察清单不完整")
    for shown in value["observations"]:
        source = one(e, "care_vehicle_observations", shown["id"])
        require(all(shown[k] == source[k] for k in ("id", "vehicle_id", "kind", "observed_date", "odometer_km", "valid_until", "source_reference", "evidence_id", "actor_id")), "CV原观察被有效纠正覆盖")
        await expect(e.page.locator("#main")).to_contain_text(source["source_reference"])
    require(value["effective_observations"] == effective(e, vehicle_id, inactive=True), "CV有效观察含义与有限原来源不一致")
    for text in (row["vin"], row["model_name"], row["identity_source"]):
        await expect(e.page.locator("#main")).to_contain_text(text)
    return value


def audit_exact(guard, action, entity, key):
    audits = guard.additions["audit_logs"]
    require(len(audits) == 1 and audits[0]["action"] == action and audits[0]["entity_type"] == entity
            and audits[0]["entity_id"] == key and audits[0]["actor_id"] == guard.actor["id"], "原审计动作/对象/本人不一致")
    return audits[0]["id"]


async def create_vehicle(e, actor, store, customer, vin, identity, token):
    await read_page(e, "customer-vehicles", "客户车辆档案", CARE + "/vehicles")
    await form(e, '#main [data-act="care-vehicle-new"]', "登记客户车辆")
    values = {"customer_id": customer["id"], "vin": vin, "customer_identity_id": identity,
              "plate": "合成" + token[-6:], "model_name": "合成提醒车辆" + token,
              "source_reference": "本次合成客户本人及VIN资料逐项确认 " + token, "confirmed": True}
    await fields(e, values)
    link = [r for r in rows(e, "group_identity_links") if r["store_id"] == store and r["local_kind"] == "customer" and r["local_id"] == customer["id"]]
    existing = [r for r in rows(e, "group_identities") if r["kind"] == "vehicle" and r["canonical_key"] == vin]
    require(len(link) <= 1 and len(existing) <= 1 and identity is not None, "明确集团身份或VIN候选不一致")
    guard = Guard(e, "new_vehicle_store" + str(store), actor, store, appends={"care_customer_vehicles": 1,
        "group_identities": int(not existing), "group_identity_links": int(not link), "group_events": int(not link),
        "audit_logs": 1, "care_receipts": 1})
    body, request, _, native = await submit(e, actor, store, CARE + "/vehicles", guard,
        status=201, render=lambda b: CARE + "/vehicles/" + str(b["vehicle"]["id"]), action="vehicle_create", payload=lambda r: r["values"])
    row = one(e, "care_customer_vehicles", body["vehicle"]["id"])
    audit_exact(guard, "care_vehicle_create", "customer_vehicle", row["id"])
    require(request["values"] == values and row["customer_id"] == customer["id"] and row["customer_identity_id"] == identity
            and row["vin"] == vin and row["created_by"] == actor["id"] and row["identity_source"] == values["source_reference"], "新CV明确客户/集团身份/VIN/本人关系不一致")
    links = [r for r in rows(e, "group_identity_links") if r["store_id"] == store and r["local_kind"] == "customer" and r["local_id"] == customer["id"]]
    vi = one(e, "group_identities", row["vehicle_identity_id"])
    require(len(links) == 1 and links[0]["identity_id"] == identity and vi["canonical_key"] == vin and vi["kind"] == "vehicle", "原集团客户及车辆身份分别未对齐")
    await vehicle_view(e, row["id"])
    return row, native


async def edit_vehicle(e, actor, row, token):
    await form(e, '#main [data-act="care-vehicle-edit"]', "维护客户车辆关系")
    values = {"plate": "合成复核" + token[-4:], "model_name": "合成车型资料已复核" + token, "active": True,
              "reason": "本次本人复核车牌车型，仅维护关系资料 " + token}
    await fields(e, values)
    guard = Guard(e, "edit_reminder_vehicle", actor, 1, appends={"care_receipts": 1, "audit_logs": 1},
                  updates={"care_customer_vehicles": {row["id"]: VERSION | {"plate", "model_name", "active"}}})
    _, request, _, native = await submit(e, actor, 1, CARE + "/vehicles/" + str(row["id"]), guard, method="PUT",
        render=CARE + "/vehicles/" + str(row["id"]), action="vehicle_update", payload=lambda r: {"id": row["id"], "version": r["version"], **r["values"]})
    now = one(e, "care_customer_vehicles", row["id"])
    audit_exact(guard, "care_vehicle_update", "customer_vehicle", row["id"])
    require(request["version"] == row["version"] and request["values"] == values and now["version"] > row["version"]
            and all(now[k] == values[k] for k in ("plate", "model_name", "active")), "关系编辑未绑定原当前CAS和输入")
    await vehicle_view(e, row["id"])
    return now, native


async def history(e, vehicle_id):
    row = one(e, "care_customer_vehicles", vehicle_id)
    target = e.origin + "/#customer-vehicles/" + str(vehicle_id)
    same_page = e.page.url == target
    if same_page:
        await expect(e.page.locator("#main h1")).to_have_text("客户车辆 · " + (row["plate"] or row["vin"]))
    before = e.business_snapshot("before_native_history")
    async with e.page.expect_response(lambda r: match(r, CARE + f"/vehicles/{vehicle_id}/history")) as pending:
        e.action("navigate", "原CV读取本地与获准服务摘要", vehicle_id=vehicle_id)
        if same_page:
            await e.page.reload(wait_until="domcontentloaded")
        else:
            await e.page.goto(target, wait_until="domcontentloaded")
    response = await pending.value
    body = await response.json()
    require(response.status == 200, "原CV服务摘要读取失败")
    await expect(e.page.locator("#main h1")).to_have_text("客户车辆 · " + (row["plate"] or row["vin"]))
    e.business_unchanged(before, "after_native_history")
    return body


async def receiver_login(e, context, contexts, src):
    separate, page = await fresh_identity(e, context, contexts)
    result = await native_login(e, src["receiver"], src["password"])
    if result["active_store_id"] != 2:
        result = await switch_store(e, 2, src["receiver"], "service")
    require(result["current_role"] == "service" and result["active_store_id"] == 2, "接收员工未按当前二店service本人办理")
    return separate, page, result


async def second_store_customer(e, src, token):
    actor, original = src["receiver"], src["customer"]
    await read_page(e, "master/customers", "客户档案", "/api/flow/master/customers")
    await form(e, '#main [data-act="newmaster"][data-kind="customers"]', "新增客户档案")
    values = {"name": original["name"], "phone": original["phone"], "contact_allowed": True,
              "note": "本次明确核对同一合成客户，二店独立档案不覆盖一店 " + token}
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/customer-choice/matches" and "phone=" in urlsplit(r.url).query) as pending:
        await fields(e, values)
    response = await pending.value
    matches = await response.json()
    require(response.status == 200, "二店原同号候选读取失败")
    if matches["items"]:
        await expect(e.page.locator('#modal [name="choice_confirm"]')).to_be_visible()
        await checkbox(e, '#modal [name="choice_confirm"]', True, "核对同号资料后明确另建二店客户")
    guard = Guard(e, "second_store_customer", actor, 2, appends={"flow_customers": 1, "audit_logs": 1})
    body, request, listing, native = await submit(e, actor, 2, "/api/flow/master/customers", guard,
        status=201, render="/api/flow/master/customers")
    row = one(e, "flow_customers", body["id"])
    audit_exact(guard, "master_create", "flow_master", row["id"])
    require(row["store_id"] == 2 and row["owner_id"] == actor["id"] and all(row[k] == values[k] for k in values)
            and row["id"] != original["id"] and any(r["id"] == row["id"] for r in listing["items"]), "二店原客户并非本人明确新增")
    require(request["values"] == {**values, **({"confirm_new_customer": True} if matches["items"] else {})}, "二店原客户输入或明确另建合同不一致")
    await expect(e.page.locator('#main tr').filter(has=e.page.locator(f'[data-act="editmaster"][data-id="{row["id"]}"]'))).to_contain_text(row["name"])
    return row, native


async def share_partial(e, context, credentials, contexts, src, token, cp):
    fixture, delivered = src["fixture"], src["delivered_cv"]
    sales, _ = await login(e, context, credentials, fixture["sales_key"], "customer-vehicles/" + str(delivered["id"]),
                          "客户车辆 · " + (delivered["plate"] or delivered["vin"]), CARE + "/vehicles/" + str(delivered["id"]))
    local = await history(e, delivered["id"])
    require(len(local["items"]) == len(src["history"]) and all(not r["external"] for r in local["items"]), "父交付CV本地历史不完整或混入跨店来源")
    for link in src["history"]:
        item = next((r for r in local["items"] if r.get("case_id") == link["case_id"]), None)
        require(item is not None and item["summary"] == link["summary"], "本地原摘要与实际HistoryLink不一致")
        await expect(e.page.locator("#main")).to_contain_text(link["summary"])
    # The identity number is actually visible on the source CV page.
    identity_panel = e.page.locator('#main .panel').filter(has=e.page.locator('h2:text-is("身份与本店关系")'))
    await expect(identity_panel).to_contain_text("集团客户身份编号")
    await expect(identity_panel).to_contain_text(str(delivered["customer_identity_id"]))
    main_page = e.page
    _, _, login_info = await receiver_login(e, context, contexts, src)
    customer2, customer_native = await second_store_customer(e, src, token)
    vehicle2, second_native = await create_vehicle(e, src["receiver"], 2, customer2, delivered["vin"], delivered["customer_identity_id"], token)
    require(vehicle2["vehicle_identity_id"] == delivered["vehicle_identity_id"], "跨店相同VIN未关联原明确车辆身份")
    no_grant = await history(e, vehicle2["id"])
    require(no_grant["items"] == [], "尚无授权时二店收到外部摘要")
    receiver_page = e.page
    e.page = main_page
    manager, _ = await login(e, context, credentials, fixture["manager_key"], "customer-history-grants", "跨店服务历史授权", CARE + "/history/grants")
    await form(e, '#main [data-act="care-grant-new"]', "登记跨店服务历史授权")
    values = {"from_vehicle_id": delivered["id"], "to_store_id": 2, "to_vehicle_id": vehicle2["id"],
              "valid_until": day().isoformat(), "source_reference": "本次合成客户明确同意仅两店同车服务摘要 " + token, "confirmed": True}
    await fields(e, values)
    guard = Guard(e, "grant_actual_history", manager, 1, appends={"care_history_grants": 1, "care_receipts": 1, "audit_logs": 1})
    body, request, _, grant_native = await submit(e, manager, 1, CARE + "/history/grants", guard,
        status=201, render=CARE + "/history/grants", action="grant_history", payload=lambda r: r["values"])
    grant = one(e, "care_history_grants", body["grant"]["id"])
    audit_exact(guard, "care_history_grant", "care_grant", grant["id"])
    require(request["values"] == values and all(grant[k] == v for k, v in values.items() if k != "confirmed")
            and grant["from_store_id"] == 1 and grant["status"] == "active" and grant["active_pair"] == f'{delivered["id"]}:{vehicle2["id"]}'
            and grant["customer_identity_id"] == delivered["customer_identity_id"] and grant["vehicle_identity_id"] == delivered["vehicle_identity_id"], "原服务摘要授权范围不一致")
    e.page = receiver_page
    shared = await history(e, vehicle2["id"])
    expected = [{k: v for k, v in r.items() if k != "case_id"} | {"external": True} for r in local["items"]]
    require(shared["items"] == expected and all(set(r) == {"number", "kind", "business_date", "completed_date", "state", "summary", "store_name", "external"} for r in shared["items"]), "跨店摘要含金额/电话/原case_id/附件或遗漏真实摘要")
    await expect(e.page.locator('#main [data-route^="case/"]')).to_have_count(0)
    await expect(e.page.locator("#main")).to_contain_text("已授权跨店摘要")
    e.page = main_page
    await read_page(e, "customer-history-grants", "跨店服务历史授权", CARE + "/history/grants")
    await form(e, f'#main [data-act="care-grant-revoke"][data-id="{grant["id"]}"]', "撤销服务历史授权")
    reason = "本次客户明确撤销两店摘要授权，原服务和附件权限保留 " + token
    await fields(e, {"reason": reason})
    guard = Guard(e, "revoke_actual_history", manager, 1, appends={"care_receipts": 1, "audit_logs": 1},
        updates={"care_history_grants": {grant["id"]: {"version", "status", "active_pair", "revoked_by", "revoke_reason"}}})
    _, request, _, revoke_native = await submit(e, manager, 1, CARE + f'/history/grants/{grant["id"]}/revoke', guard,
        render=CARE + "/history/grants", action="revoke_history", payload=lambda r: {"id": grant["id"], "version": r["version"], "reason": r["values"]["reason"]})
    revoked = one(e, "care_history_grants", grant["id"])
    audit_exact(guard, "care_history_revoke", "care_grant", grant["id"])
    require(request["version"] == grant["version"] and revoked["version"] > grant["version"] and revoked["status"] == "revoked"
            and revoked["active_pair"] is None and revoked["revoked_by"] == manager["id"] and revoked["revoke_reason"] == reason, "原授权撤销未绑定最新版本/本人/原因")
    e.page = receiver_page
    after = await history(e, vehicle2["id"])
    require(after["items"] == [], "真实撤销后仍泄露外部摘要")
    e.page = main_page
    original_history = await history(e, delivered["id"])
    require(original_history == local, "撤销跨店摘要覆盖本地历史")
    result = {"source_cv_id": delivered["id"], "receiver_customer_id": customer2["id"], "receiver_cv_id": vehicle2["id"],
              "receiver_login": login_info, "receiver_native_customer": customer_native, "receiver_native_vehicle": second_native,
              "grant": grant, "revoke": revoked, "original_local": local, "shared_minimal": shared,
              "after_revoke": after, "grant_native": grant_native, "revoke_native": revoke_native,
              "true_expiry": "planned_pending", "grant_valid_on_today": True, "acceptance_check_submitted": False}
    cp.report["partial_requirements"][0].update(status="partial", evidence=result)
    cp.save()
    await e.snapshot("hk099-shared-and-revoked-partial")
    return result


async def observe_vehicle(e, actor, vehicle_id, values):
    await vehicle_view(e, vehicle_id)
    old = one(e, "care_customer_vehicles", vehicle_id)
    await form(e, '#main [data-act="care-observe"]', "登记日期与里程来源")
    # Read the actual UI business date rather than assuming a machine UTC day.
    require(await e.page.locator('#modal [name="observed_date"]').input_value() == day().isoformat(), "页面与候选业务日不同，停止跨日输入")
    await fields(e, {k: (v if v is not None else "") for k, v in values.items()})
    guard = Guard(e, "observe_" + values["kind"], actor, 1,
        appends={"care_vehicle_observations": 1, "care_receipts": 1, "audit_logs": 1}, updates={"care_customer_vehicles": {vehicle_id: VERSION}})
    body, request, _, native = await submit(e, actor, 1, CARE + f"/vehicles/{vehicle_id}/observations", guard,
        render=CARE + "/vehicles/" + str(vehicle_id), action="observe", payload=lambda r: {"id": vehicle_id, "version": r["version"], **r["values"]})
    row = one(e, "care_vehicle_observations", body["observation"]["id"])
    audit_exact(guard, "care_observe", "customer_vehicle", vehicle_id)
    require(request["version"] == old["version"] and request["values"] == values
            and row["vehicle_id"] == vehicle_id and row["actor_id"] == actor["id"]
            and all(row[k] == v for k, v in values.items() if k != "confirmed"), "独立日期/公里/种类/来源与原观察不一致")
    await vehicle_view(e, vehicle_id)
    return row, native


async def rule_save(e, context, credentials, fixture, kind, values):
    actor, _ = await login(e, context, credentials, fixture["manager_key"], "customer-reminders", "车辆提醒与续保提取", CARE + "/reminders/rules")
    existing = [r for r in rows(e, "care_reminder_rules") if r["store_id"] == 1 and r["kind"] == kind]
    require(len(existing) <= 1, "原每店每种提醒规则不唯一")
    old = existing[0] if existing else None
    if old is None:
        await select_value(e, '#main [name="care_rule_kind"]', kind, "明确原提醒规则种类")
    await form(e, f'#main [data-act="care-rule-edit"][data-id="{old["id"]}"]' if old else '#main [data-act="care-rule-new"]', "维护" + LABELS[kind] + "规则")
    allowed = {"name", "lead_days", "assignee_id", "active"} | ({"interval_days", "interval_km", "lead_km"} if kind in {"maintenance", "first_service"} else set())
    await fields(e, {k: v for k, v in values.items() if k in allowed})
    guard = Guard(e, "rule_" + kind, actor, 1, appends={"care_reminder_rules": int(old is None), "care_receipts": 1, "audit_logs": 1},
        updates={"care_reminder_rules": {old["id"]: VERSION | allowed | {"approved_by"}}} if old else {})
    body, request, listing, native = await submit(e, actor, 1, CARE + "/reminders/rules" + ("/" + str(old["id"]) if old else ""), guard,
        render=CARE + "/reminders/rules", method="PUT" if old else "POST", status=200 if old else 201,
        action="rule_save", payload=lambda r: {"id": old["id"] if old else None, "version": r.get("version"), **r["values"]})
    row = one(e, "care_reminder_rules", body["rule"]["id"])
    audit_exact(guard, "care_rule_save", "care_rule", row["id"])
    require(request["values"] == values and all(row[k] == v for k, v in values.items()) and row["approved_by"] == actor["id"]
            and (request["version"] == old["version"] and row["version"] > old["version"] if old else row["created_by"] == actor["id"]), "本店原规则/经办/独立配置责任/CAS不一致")
    shown = next((r for r in listing["items"] if r["id"] == row["id"]), None)
    require(shown is not None and all(shown[k] == row[k] for k in ("id", "version", *values)), "原规则列表遗漏或输入/API/DB不匹配")
    table_row = e.page.locator('#main tr').filter(has=e.page.locator(f'[data-act="care-rule-edit"][data-id="{row["id"]}"]'))
    await expect(table_row).to_have_count(1)
    await expect(table_row).to_contain_text(values["name"])
    for index, field in enumerate(("interval_days", "interval_km", "lead_days", "lead_km"), 1):
        await expect(table_row.locator("td").nth(index)).to_have_text(str(values[field]))
    await expect(table_row.locator("td").nth(5)).to_have_text("启用" if values["active"] else "停用")
    return row, native


async def care_read(e, case_id, actor):
    f = care_facts(e, case_id)
    api = await read_page(e, "customer-service/" + str(case_id), f["case"]["title"] + " · " + f["case"]["number"], CARE + "/cases/" + str(case_id))
    await care_rendered(e, f, api, actor)
    require(f["case"]["store_id"] == 1 and f["case"]["owner_id"] == actor["id"]
            and f["tasks"][0]["assignee_id"] == actor["id"], "提醒原Task非当前本人本店")
    return f, api


async def care_action(e, actor, case_id, action, values):
    f, api = await care_read(e, case_id, actor)
    require(action in api["actions"], "提醒原本人动作不可办理：" + action)
    titles = {"start": "接手办理", "followup": "登记跟进", "close": "登记结案"}
    await form(e, f'#main [data-act="care-action"][data-action="{action}"]', titles[action])
    await fields(e, {k: (v if v is not None else "") for k, v in values.items() if k not in {"satisfaction", "recommend"}})
    updates = {"care_customer_vehicles": {f["care"]["vehicle_id"]: VERSION},
               "flow_cases": {case_id: VERSION | ({"state", "completed_date"} if action == "close" else {"state"} if action == "start" else {"due_date"})}}
    if action == "close":
        updates["care_cases"] = {case_id: {"result"}}
        updates["flow_tasks"] = {f["tasks"][0]["id"]: VERSION | {"status", "done_at", "done_by"}}
    elif action == "followup" and values.get("next_due_date"):
        updates["flow_tasks"] = {f["tasks"][0]["id"]: VERSION | {"due_date"}}
    guard = Guard(e, "care_" + action + "_" + str(case_id), actor, 1,
        appends={"care_receipts": 1, "care_records": 1, "flow_events": 1, "audit_logs": 1}, updates=updates)
    _, request, _, native = await submit(e, actor, 1, CARE + f"/cases/{case_id}/actions/{action}", guard,
        render=CARE + "/cases/" + str(case_id), action="care_" + action,
        payload=lambda r: {"case_id": case_id, "version": r["version"], **r["values"]})
    require(request["version"] == f["case"]["version"] and request["values"] == values, "原提醒办理缺完整当前CAS/输入")
    after, api = await care_read(e, case_id, actor)
    record = guard.additions["care_records"][0]
    require(record["case_id"] == case_id and record["action"] == action and record["actor_id"] == actor["id"]
            and record["note"] == ("经办人已接手" if action == "start" else values["note"])
            and decoded(record["details"]) == {k: v for k, v in values.items() if k != "note"}, "原提醒逐次跟进记录不一致")
    require(guard.additions["flow_events"][0]["action"] == "care_" + action
            and guard.additions["flow_events"][0]["after_state"] == after["case"]["state"]
            and guard.additions["audit_logs"][0]["action"] == "flow_care_" + action, "原提醒事件/审计不一致")
    audit_exact(guard, "flow_care_" + action, "flow", case_id)
    if action == "close":
        require(after["case"]["state"] == "completed" and after["case"]["completed_date"] == day().isoformat()
                and after["care"]["result"] == values["result"] and after["tasks"][0]["done_by"] == actor["id"], "结案原Case/Task/实际结果不一致")
    return {"native": native, "case": after["case"], "care": after["care"], "records": after["records"], "task": after["tasks"][0]}


async def finish_care(e, actor, case_id, token):
    actions = [await care_action(e, actor, case_id, "start", {})]
    for index, channel in enumerate(("internal", "in_person"), 1):
        actions.append(await care_action(e, actor, case_id, "followup", {"channel": channel, "contact_result": "progress" if index == 1 else "contacted",
            "note": f"本次合成第{index}次实际回访核对，约定后续办理而非已完成保养 {token}", "next_due_date": None}))
    actions.append(await care_action(e, actor, case_id, "close", {"result": "appointment", "note": "合成客户已明确约定后续办理；没有发送消息或确认实际保养完成 " + token,
        "satisfaction": None, "recommend": None}))
    return actions


def selected_generation(result, vehicle_id, kind, *, present=True):
    matches = [r for r in result["created"] if r["vehicle_id"] == vehicle_id and r["subtype"] == kind]
    require(len(matches) == (1 if present else 0), "目标车原边界提醒数不符：" + kind)
    return matches[0] if present else None


def affected(e, vehicle_id, observation):
    matches = []
    for c in rows(e, "care_cases"):
        if c["vehicle_id"] != vehicle_id or c["subtype"] not in AFFECTED[observation["kind"]] or c["rule_id"] is None:
            continue
        basis = [b for b in rows(e, "observation_reminder_bases") if b["case_id"] == c["case_id"]]
        if not basis or observation["id"] in {basis[0]["baseline_id"], basis[0]["current_id"]} or observation["kind"] == "first_service" and c["subtype"] == "first_service":
            case = one(e, "flow_cases", c["case_id"])
            tasks = [t for t in rows(e, "flow_tasks") if t["case_id"] == case["id"] and t["key"] == "care_handle" and t["status"] == "open"]
            require(len(tasks) <= 1, "原提醒开放任务不唯一")
            matches.append({"case": case, "care": c, "open_task": tasks[0] if tasks else None,
                            "closed": case["state"] in {"pending", "working"} and bool(tasks)})
    return matches


async def correction_view(e, case_id):
    value = await read_page(e, "observation-corrections/cases/" + str(case_id), "日期里程原观察纠正", OC + "/cases/" + str(case_id))
    case = one(e, "flow_cases", case_id)
    request = one(e, "observation_corrections", case_id)
    require(all(value[k] == case[k] for k in ("id", "number", "version", "state"))
            and value["vehicle_id"] == request["vehicle_id"] and value["observation_id"] == request["observation_id"]
            and value["operation"] == request["operation"] and value["original"] == decoded(request["original_snapshot"])
            and value["proposed"] == decoded(request["proposed"]), "原纠正页面/API/DB来源或CAS不一致")
    return value


async def correction_create(e, actor, vehicle_id, observation, operation, proposed, token):
    value = await read_page(e, "observation-corrections/vehicles/" + str(vehicle_id), "日期里程原观察纠正", OC + "/vehicles/" + str(vehicle_id))
    original = next(r for r in value["observations"] if r["id"] == observation["id"])
    expected = next(r for r in effective(e, vehicle_id, inactive=True) if r["id"] == observation["id"])
    vehicle = one(e, "care_customer_vehicles", vehicle_id)
    require(original == expected and original["source_type"] == "manual_observation" and original["active"], "原纠正非有限人工观察当前有效版本")
    await form(e, f'#main [data-act="oc-new"][data-id="{observation["id"]}"]', "有据纠正原观察")
    reason = "核对本次合成原资料确认误登记，保留原观察并请求独立复核 " + token
    await fields(e, {"operation": operation, **({k: (v if v is not None else "") for k, v in proposed.items()
        if k != "valid_until" or observation["kind"] in {"warranty", "insurance"}} if proposed else {}), "reason": reason})
    guard = Guard(e, "create_correction_" + operation, actor, 1, appends={"flow_cases": 1, "flow_tasks": 1,
        "observation_corrections": 1, "observation_correction_events": 1, "observation_correction_receipts": 1,
        "flow_events": 1, "audit_logs": 1}, updates={"care_customer_vehicles": {vehicle_id: VERSION}})
    body, request, _, native = await submit(e, actor, 1, OC + "/cases", guard, status=201,
        render=lambda b: OC + "/cases/" + str(b["case"]["id"]), action="create", receipt_table="observation_correction_receipts",
        payload=lambda r: {k: (r[k] or {} if k == "proposed" else r[k]) for k in ("vehicle_id", "vehicle_version", "observation_id", "base_digest", "operation", "proposed", "reason")})
    case_id = body["case"]["id"]
    audit_exact(guard, "flow_observation_create", "flow", case_id)
    event = guard.additions["observation_correction_events"][0]
    require(event["case_id"] == case_id and event["action"] == "create" and event["reason"] == reason
            and event["evidence_id"] is None and guard.additions["flow_events"][0]["case_id"] == case_id
            and guard.additions["flow_events"][0]["action"] == "observation_create", "原纠正创建事件未对应申请")
    expected_request = {"vehicle_id": vehicle_id, "vehicle_version": vehicle["version"], "observation_id": observation["id"],
                        "base_digest": original["digest"], "operation": operation, "proposed": proposed, "reason": reason}
    require({k: v for k, v in request.items() if k != "request_id"} == expected_request, "原纠正未绑定本CV/原观察/有效摘要/替代事实")
    corr = one(e, "observation_corrections", case_id)
    require(corr["base_digest"] == original["digest"] and decoded(corr["original_snapshot"]) == original
            and decoded(corr["proposed"]) == (proposed or {}) and corr["operation"] == operation, "原观察纠正快照未冻结")
    task = guard.additions["flow_tasks"][0]
    require(task["case_id"] == case_id and task["key"] == "observation_submit" and task["assignee_id"] == actor["id"] and task["status"] == "open", "纠正申请原本人任务不一致")
    await correction_view(e, case_id)
    return case_id, native


async def correction_upload(e, actor, case_id, token):
    await correction_view(e, case_id)
    await form(e, '#main [data-act="oc-upload"]', "上传本次核对原件")
    directory = e.directory / "synthetic-inputs"
    directory.mkdir(exist_ok=True)
    name = "observation-correction-" + str(case_id) + ".txt"
    content = ("合成验收原资料，不表示公司实际客户或现场服务。\n本次误录独立复核依据 " + token + "\n").encode()
    path = directory / name
    path.write_bytes(content)
    e.action("select_file", "本人选择本次纠正原件", filename=name, sha256=hashlib.sha256(content).hexdigest())
    await e.page.locator('#modal [name="file"]').set_input_files(str(path))
    guard = Guard(e, "upload_correction_" + str(case_id), actor, 1,
        appends={"flow_files": 1, "file_security": 1, "file_scan_events": 1, "flow_events": 1, "audit_logs": 1})
    async with e.page.expect_response(lambda r: match(r, OC + "/cases/" + str(case_id))) as rendered:
        async with e.page.expect_response(lambda r: match(r, f"/api/flow/cases/{case_id}/files", "POST")) as pending:
            await e.click('#modal form button[type="submit"]', "原UI单次上传本申请原件")
        response = await pending.value
        body = await response.json()
        require(response.status == 200, "原纠正附件上传失败")
    shown = await (await rendered.value).json()
    headers = await response.request.all_headers()
    require(headers.get("cookie") and headers.get("x-csrf-token") and headers.get("x-store-id") == "1" and headers.get("x-app-request") == "1", "原上传缺同源身份/CSRF")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    protected = guard.finish()
    file = one(e, "flow_files", body["id"])
    audit_exact(guard, "flow_upload", "flow", case_id)
    blob = file["content"]
    require(isinstance(blob, bytes) and blob == content and file["sha256"] == hashlib.sha256(content).hexdigest()
            and file["size"] == len(content) and file["case_id"] == case_id and file["category"] == "evidence"
            and file["name"] == name and file["created_by"] == actor["id"] and not file["generated"] and file["source_file_id"] is None, "原上传字节/本人/原单/用途不一致")
    metadata = {k: file[k] for k in ("id", "case_id", "store_id", "name", "category", "sha256", "size", "created_by", "generated", "source_file_id")}
    visible = next(f for f in shown["files"] if f["id"] == file["id"])
    scan = guard.additions["file_scan_events"][0]
    require(scan["file_id"] == file["id"] and scan["actor_id"] == actor["id"] and scan["action"] == "initial"
            and scan["state"] == "structure_only" and scan["sha256"] == file["sha256"] and scan["size"] == file["size"]
            and visible["security"]["can_use"] is True and visible["security"]["state"] == "structure_only", "原纠正附件结构检查来源不一致")
    await expect(e.page.locator('#main .filerecord').filter(has_text=name)).to_contain_text(visible["security"]["label"])
    return metadata, {"file": metadata, "stored_blob": {"length": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}, "scan": scan,
                      "guard": protected, "clamav_acceptance": False, "native_ui": True}


async def correction_action(e, actor, case_id, action, evidence):
    api = await correction_view(e, case_id)
    case = one(e, "flow_cases", case_id)
    corr = one(e, "observation_corrections", case_id)
    observation = one(e, "care_vehicle_observations", corr["observation_id"])
    require(action in api["actions"] and (action != "approve" or case["created_by"] != actor["id"]), "原纠正非独立可办理动作")
    old_tasks = [t for t in rows(e, "flow_tasks") if t["case_id"] == case_id and t["status"] == "open"]
    require(len(old_tasks) == 1 and old_tasks[0]["key"] == ("observation_submit" if action == "submit" else "observation_review"), "原纠正审批/提交任务不唯一")
    if action == "submit":
        require(old_tasks[0]["assignee_id"] == actor["id"] == case["created_by"], "原纠正提交非申请本人任务")
    targets = affected(e, corr["vehicle_id"], observation) if action == "approve" else []
    values = {"evidence_id": evidence["id"], **({"reason": "独立核对本申请原件和当前有效版本，确认合成误录更正"} if action == "approve" else {})}
    await form(e, f'#main [data-act="oc-action"][data-key="{action}"]', "提交原件复核" if action == "submit" else "独立批准本次纠正")
    await fields(e, values)
    updates = {"care_customer_vehicles": {corr["vehicle_id"]: VERSION}, "flow_cases": {case_id: VERSION | {"state", "completed_date"}},
               "flow_tasks": {t["id"]: VERSION | {"status", "done_at", "done_by"} for t in old_tasks}}
    for target in targets:
        if target["closed"]:
            updates["flow_cases"][target["case"]["id"]] = VERSION | {"state", "completed_date"}
            updates["flow_tasks"][target["open_task"]["id"]] = VERSION | {"status", "done_at", "done_by"}
    n = len(targets)
    guard = Guard(e, "correction_" + action + "_" + str(case_id), actor, 1,
        appends={"observation_correction_receipts": 1, "observation_correction_events": 1,
                 "observation_correction_effects": int(action == "approve"), "observation_reminder_invalidations": n,
                 "care_records": n, "flow_events": 1+n, "audit_logs": 1+n, "flow_tasks": int(action == "submit")}, updates=updates)
    _, request, _, native = await submit(e, actor, 1, OC + f"/cases/{case_id}/actions/{action}", guard,
        render=OC + "/cases/" + str(case_id), action=action, receipt_table="observation_correction_receipts",
        payload=lambda r: {"case_id": case_id, "version": r["version"], "values": r["values"]})
    require(request["version"] == case["version"] and request["values"] == values, "纠正提交/审批缺本次CAS/原件/核对说明")
    current = one(e, "flow_cases", case_id)
    event = guard.additions["observation_correction_events"][0]
    require(event["case_id"] == case_id and event["action"] == action and event["evidence_id"] == evidence["id"]
            and current["version"] > case["version"] and current["state"] == ("approval" if action == "submit" else "completed"), "纠正原Case/Event未正确前进")
    expected_events = [(case_id, "observation_" + action)] + [(t["case"]["id"], "care_cancel" if t["closed"] else "care_followup") for t in targets]
    require([(r["case_id"], r["action"]) for r in guard.additions["flow_events"]] == expected_events
            and [(r["entity_id"], r["action"]) for r in guard.additions["audit_logs"]] == [(cid, "flow_" + act) for cid, act in expected_events]
            and all(r["entity_type"] == "flow" for r in guard.additions["audit_logs"]), "纠正或有限失效提醒事件/审计不匹配")
    if action == "submit":
        manager = guard.additions["flow_tasks"][0]
        require(manager["case_id"] == case_id and manager["key"] == "observation_review" and manager["status"] == "open"
                and manager["assignee_id"] != actor["id"] and role(e, manager["assignee_id"], 1) in {"admin", "manager"}, "原纠正没有独立主管复核任务")
        require(one(e, "flow_tasks", old_tasks[0]["id"])["status"] == "done", "原提交Task未关闭")
    else:
        effect = guard.additions["observation_correction_effects"][0]
        base = decoded(corr["original_snapshot"])
        require(effect["case_id"] == case_id and effect["observation_id"] == observation["id"]
                and effect["parent_effect_id"] == base["effect_id"] and effect["parent_token"] == str(base["effect_id"] or 0)
                and effect["review_event_id"] == event["id"], "有效纠正未引用原代次和独立review事件")
        require(current["completed_date"] == day().isoformat() and one(e, "flow_tasks", old_tasks[0]["id"])["status"] == "cancelled", "批准原复核任务/结案日期不一致")
        for target in targets:
            cid = target["case"]["id"]
            invalid = [r for r in guard.additions["observation_reminder_invalidations"] if r["case_id"] == cid]
            record = [r for r in guard.additions["care_records"] if r["case_id"] == cid]
            require(len(invalid) == len(record) == 1 and invalid[0]["correction_case_id"] == case_id
                    and invalid[0]["insurance_invalidation_id"] is None and invalid[0]["observation_id"] == observation["id"]
                    and invalid[0]["previous_state"] == target["case"]["state"] and bool(invalid[0]["closed_open_task"]) == target["closed"]
                    and invalid[0]["source_key"] == "correction:" + str(case_id), "原有限提醒失效谱系不一致")
            details = {"basis_invalidation": "correction:" + str(case_id), "previous_state": target["case"]["state"], "closed_open_task": target["closed"]}
            require(record[0]["action"] == ("cancel" if target["closed"] else "followup") and decoded(record[0]["details"]) == details, "原提醒失效追加记录不一致")
            if target["closed"]:
                require(one(e, "flow_cases", cid)["state"] == "cancelled"
                        and one(e, "flow_tasks", target["open_task"]["id"])["status"] == "cancelled", "开放提醒未明确取消及关闭Task")
            else:
                require(one(e, "flow_cases", cid) == target["case"], "已结案提醒因纠正回退或改状态")
        expected = next(r for r in effective(e, corr["vehicle_id"], inactive=True) if r["id"] == observation["id"])
        require(expected["effect_id"] == effect["id"] and expected["active"] is (corr["operation"] == "replace"), "纠正/撤销有效基准不一致")
    view = await correction_view(e, case_id)
    require(set(view["invalidated_reminder_ids"]) == {t["case"]["id"] for t in targets}, "原纠正显示失效提醒集合遗漏")
    return {"native": native, "case": current, "event": event,
            "effect": guard.additions["observation_correction_effects"], "invalidations": guard.additions["observation_reminder_invalidations"],
            "review_task_before": {k: old_tasks[0][k] for k in ("id", "case_id", "key", "assignee_id", "version", "status")},
            "independent_manager_actual_ui_authorized": action == "approve"}


async def pending_reminder(e, actor, case_id, correction_id):
    f, api = await care_read(e, case_id, actor)
    require(api["reminder_basis"]["status"] == "pending_review"
            and api["reminder_basis"]["pending_correction_ids"] == [correction_id]
            and "close" not in api["actions"] and api["followup_channels"] == ["internal"], "待复核旧提醒仍可按失效基准外联/结案")
    await expect(e.page.locator('#main [data-act="care-action"][data-action="close"]')).to_have_count(0)
    await form(e, '#main [data-act="care-action"][data-action="followup"]', "登记跟进")
    options = await e.page.locator('#modal [name="channel"] option').all_text_contents()
    values = await e.page.locator('#modal [name="channel"] option').evaluate_all("nodes=>nodes.map(n=>n.value)")
    require(values == ["", "internal"], "待复核原UI仍提供外联选项")
    before = e.business_snapshot("before_pending_internal_form_discard")
    await e.click('#modal .modalhead [data-act="close"]', "关闭未填写的内部核对表单")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    e.business_unchanged(before, "after_pending_internal_form_discard")
    note = "原观察复核中，仅保留内部核对，不外联不按旧基准结案"
    action = await care_action(e, actor, case_id, "followup", {"channel": "internal", "contact_result": "progress", "note": note, "next_due_date": None})
    return {"pending_basis": api["reminder_basis"], "visible_channels": options, "original_ui_blocks_external_channel": True,
            "server_phone_409_not_submitted_because_ui_does_not_offer_it": True, "internal_followup": action}


async def service_login(e, context, credentials, fixture):
    actor, _ = await login(e, context, credentials, fixture["service_key"], "customer-reminders", "车辆提醒与续保提取", CARE + "/reminders/rules")
    return actor


async def customer_reminders_business(e, context, credentials):
    cp, contexts, main_page = Checkpoint(e), [], e.page
    try:
        src = dependencies(e, cp)
        fixture, customer = src["fixture"], src["customer"]
        token = uuid.uuid4().hex[:10]
        partial = await share_partial(e, context, credentials, contexts, src, token, cp)
        sales, _ = await login(e, context, credentials, fixture["sales_key"], "customer-vehicles", "客户车辆档案", CARE + "/vehicles")
        vin = "LREMD" + uuid.uuid4().hex[:12].upper()
        require(len(vin) == 17 and not e.db.rows("SELECT id FROM care_customer_vehicles WHERE vin=?", (vin,)), "本批新VIN非明确独立资料")
        # Hex can contain I/O/Q only in the fixed prefix; this prefix contains none.
        vehicle, created = await create_vehicle(e, sales, 1, customer, vin, src["delivered_cv"]["customer_identity_id"], token)
        vehicle, edited = await edit_vehicle(e, sales, vehicle, token)
        actor = await service_login(e, context, credentials, fixture)
        date_at_start = day()
        delivery_values = {"kind": "delivery", "observed_date": (date_at_start - timedelta(days=30)).isoformat(), "odometer_km": 1000,
            "valid_until": None, "source_reference": "本次合成原交付资料，日期暂录D-30、仪表实际1000公里 " + token, "evidence_id": None, "confirmed": True}
        delivery, delivery_native = await observe_vehicle(e, actor, vehicle["id"], delivery_values)
        odometer, odometer_native = await observe_vehicle(e, actor, vehicle["id"], {"kind": "odometer", "observed_date": (date_at_start - timedelta(days=1)).isoformat(),
            "odometer_km": 4900, "valid_until": None, "source_reference": "本次独立合成仪表照片D-1、实际4900公里 " + token, "evidence_id": None, "confirmed": True})
        partial["reminder_local_vehicle"] = {"vehicle_id": vehicle["id"], "create": created, "edit": edited,
                                             "delivery_observation": delivery, "delivery_native": delivery_native, "odometer": odometer, "odometer_native": odometer_native}
        cp.report["partial_requirements"][0]["evidence"] = partial
        cp.save()

        cp.start("HK-105")
        values = {"kind": "maintenance", "name": "本次保养日期规则" + token, "interval_days": 30, "interval_km": 0,
                  "lead_days": 0, "lead_km": 0, "assignee_id": actor["id"], "active": True}
        original_rule, rule_native = await rule_save(e, context, credentials, fixture, "maintenance", values)
        actor = await service_login(e, context, credentials, fixture)
        first_generation = await generate(e, actor, "maintenance_date_at_boundary")
        first = selected_generation(first_generation, vehicle["id"], "maintenance")
        await care_action(e, actor, first["case_id"], "start", {})
        await care_action(e, actor, first["case_id"], "followup", {"channel": "internal", "contact_result": "progress", "note": "核对合成交付原件发现日期可能误录，提请独立核对", "next_due_date": None})
        proposed = {"observed_date": (date_at_start - timedelta(days=29)).isoformat(), "odometer_km": 1000, "valid_until": None,
                    "source_reference": "本次合成实际交付原资料复核正确D-29、1000公里 " + token}
        correction_id, correction_create_native = await correction_create(e, actor, vehicle["id"], delivery, "replace", proposed, token)
        proof, proof_native = await correction_upload(e, actor, correction_id, token)
        submitted = await correction_action(e, actor, correction_id, "submit", proof)
        pending = await pending_reminder(e, actor, first["case_id"], correction_id)
        pending_generation = await generate(e, actor, "maintenance_pending_review_no_new")
        selected_generation(pending_generation, vehicle["id"], "maintenance", present=False)
        manager, _ = await login(e, context, credentials, fixture["manager_key"], "observation-corrections/cases/" + str(correction_id), "日期里程原观察纠正", OC + "/cases/" + str(correction_id))
        approved = await correction_action(e, manager, correction_id, "approve", proof)
        require(approved["invalidations"] and {r["case_id"] for r in approved["invalidations"]} == {first["case_id"]}, "本批交付纠正影响名单不是有限已核旧提醒")
        corrected_rule, update_native = await rule_save(e, context, credentials, fixture, "maintenance", {**values, "lead_days": 1})
        actor = await service_login(e, context, credentials, fixture)
        replacement_generation = await generate(e, actor, "maintenance_corrected_date_boundary")
        replacement = selected_generation(replacement_generation, vehicle["id"], "maintenance")
        require(len(replacement["replacement_ids"]) == 1 and replacement["basis"]["baseline_effect_id"] == approved["effect"][0]["id"]
                and decoded(replacement["basis"]["snapshot"])["baseline"]["observed_date"] == proposed["observed_date"], "新提醒未按有据替代日期及谱系生成")
        handled = await finish_care(e, actor, replacement["case_id"], token)
        repeat = await generate(e, actor, "maintenance_completed_cycle_no_duplicate")
        selected_generation(repeat, vehicle["id"], "maintenance", present=False)
        await cp.passed({"vehicle_id": vehicle["id"], "date_and_mileage_sources": [delivery, odometer], "initial_rule": original_rule, "rule_native": rule_native,
            "initial_generation": first_generation, "correction": {"case_id": correction_id, "create": correction_create_native, "file": proof_native,
                "submit": submitted, "pending_ui": pending, "pending_generation": pending_generation, "approve": approved},
            "corrected_rule": corrected_rule, "rule_update_native": update_native, "replacement_generation": replacement_generation,
            "actual_handling": handled, "completed_cycle_repeat": repeat, "external_contact_or_actual_maintenance_not_claimed": True})

        cp.start("HK-112")
        first_values = {"kind": "first_service", "name": "本次首保整数公里规则" + token, "interval_days": 0, "interval_km": 4000,
                        "lead_days": 0, "lead_km": 99, "assignee_id": actor["id"], "active": True}
        first_rule, first_rule_native = await rule_save(e, context, credentials, fixture, "first_service", first_values)
        actor = await service_login(e, context, credentials, fixture)
        below = await generate(e, actor, "first_service_below_4901")
        selected_generation(below, vehicle["id"], "first_service", present=False)
        boundary_rule, boundary_native = await rule_save(e, context, credentials, fixture, "first_service", {**first_values, "lead_km": 100})
        actor = await service_login(e, context, credentials, fixture)
        boundary = await generate(e, actor, "first_service_at_4900")
        first_service = selected_generation(boundary, vehicle["id"], "first_service")
        first_handled = await finish_care(e, actor, first_service["case_id"], token)
        completion, completion_native = await observe_vehicle(e, actor, vehicle["id"], {"kind": "first_service", "observed_date": date_at_start.isoformat(),
            "odometer_km": 5000, "valid_until": None, "source_reference": "另行核对本车合成首保现场完工原资料，实际D日5000公里，非回访结案推算 " + token,
            "evidence_id": None, "confirmed": True})
        suppressed = await generate(e, actor, "effective_first_service_suppresses_outreach")
        selected_generation(suppressed, vehicle["id"], "first_service", present=False)
        await cp.passed({"vehicle_id": vehicle["id"], "original_delivery": delivery["id"], "independent_odometer": odometer["id"],
            "below_rule": first_rule, "below_rule_native": first_rule_native, "below_threshold": below,
            "boundary_rule": boundary_rule, "boundary_rule_native": boundary_native, "at_threshold": boundary,
            "actual_two_followups_and_closure": first_handled, "separate_actual_completion_observation": completion,
            "completion_native": completion_native, "suppressed_generation": suppressed})

        cp.start("HK-106")
        warranty, warranty_native = await observe_vehicle(e, actor, vehicle["id"], {"kind": "warranty", "observed_date": date_at_start.isoformat(),
            "odometer_km": 5000, "valid_until": (date_at_start + timedelta(days=9)).isoformat(),
            "source_reference": "本次独立合成保修期限原件，明确截止D+9，非根据公里推算 " + token, "evidence_id": None, "confirmed": True})
        warranty_values = {"kind": "warranty", "name": "本次原保修截止规则" + token, "interval_days": 0, "interval_km": 0,
                           "lead_days": 8, "lead_km": 0, "assignee_id": actor["id"], "active": True}
        warranty_rule, warranty_rule_native = await rule_save(e, context, credentials, fixture, "warranty", warranty_values)
        actor = await service_login(e, context, credentials, fixture)
        not_due = await generate(e, actor, "warranty_before_9_day_boundary")
        selected_generation(not_due, vehicle["id"], "warranty", present=False)
        warranty_boundary_rule, warranty_boundary_native = await rule_save(e, context, credentials, fixture, "warranty", {**warranty_values, "lead_days": 9})
        actor = await service_login(e, context, credentials, fixture)
        due = await generate(e, actor, "warranty_exact_9_day_boundary")
        warranty_case = selected_generation(due, vehicle["id"], "warranty")
        warranty_handled = await finish_care(e, actor, warranty_case["case_id"], token)
        duplicate = await generate(e, actor, "warranty_completed_same_period_no_duplicate")
        selected_generation(duplicate, vehicle["id"], "warranty", present=False)
        retract_id, retract_create = await correction_create(e, actor, vehicle["id"], warranty, "retract", None, token)
        retract_file, retract_file_native = await correction_upload(e, actor, retract_id, token)
        retract_submit = await correction_action(e, actor, retract_id, "submit", retract_file)
        manager, _ = await login(e, context, credentials, fixture["manager_key"], "observation-corrections/cases/" + str(retract_id), "日期里程原观察纠正", OC + "/cases/" + str(retract_id))
        retract_approve = await correction_action(e, manager, retract_id, "approve", retract_file)
        require({r["case_id"] for r in retract_approve["invalidations"]} == {warranty_case["case_id"]}
                and all(not r["closed_open_task"] and r["previous_state"] == "completed" for r in retract_approve["invalidations"]), "已结案保修提醒被误撤回或失效集合不准确")
        actor = await service_login(e, context, credentials, fixture)
        after_retract = await generate(e, actor, "warranty_retracted_source_no_new")
        selected_generation(after_retract, vehicle["id"], "warranty", present=False)
        await vehicle_view(e, vehicle["id"])
        await cp.passed({"vehicle_id": vehicle["id"], "independent_warranty_observation": warranty, "observation_native": warranty_native,
            "not_due_rule": warranty_rule, "not_due_rule_native": warranty_rule_native, "not_due": not_due,
            "at_boundary_rule": warranty_boundary_rule, "at_boundary_rule_native": warranty_boundary_native,
            "generated": due, "actual_two_followups_and_closure": warranty_handled, "same_period_repeat": duplicate,
            "original_manual_retraction": {"case_id": retract_id, "create": retract_create, "file": retract_file_native, "submit": retract_submit, "approve": retract_approve},
            "after_retract": after_retract, "completed_original_reminder_retained": one(e, "flow_cases", warranty_case["case_id"])})
        require(day() == date_at_start, "实际执行跨业务日，不能拼接临界值成绩")
        cp.finish({"customer_id": customer["id"], "customer_vehicle_id": vehicle["id"], "source_delivery_observation_id": delivery["id"],
            "delivery_correction_case_id": correction_id, "maintenance_case_id": replacement["case_id"], "first_service_case_id": first_service["case_id"],
            "first_service_observation_id": completion["id"], "warranty_case_id": warranty_case["case_id"], "warranty_retraction_case_id": retract_id,
            "history_grant_id": partial["grant"]["id"], "receiver_customer_vehicle_id": partial["receiver_cv_id"]})
    except BaseException as error:
        cp.failed(error)
        raise
    finally:
        e.page = main_page
        for separate in contexts:
            await separate.close()


CUSTOMER_REMINDERS_SCENARIOS = ((SCENARIO, customer_reminders_business, 1500),)
