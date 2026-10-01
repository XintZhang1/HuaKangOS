"""Seven original customer flows, with same-run finite sources and UI writes.

The delivered VIN relation is a local HK099 partial. Cross-store permissions,
reminder generation and external customer contact acceptance are separate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import (login_as, employee_choice, require, facts as lead_facts,
                            task as lead_task, action_form, rendered_case, due_work, native_submit)
from sales_order_business import fixed_dependency, checkpoint_evidence
from vehicle_purchase_business import select_value, nav, live_choice
from customer_service_business import (fields, care_facts, care_rendered, vehicle_facts,
                                      vehicle_rendered)
from finance_business import (create_income_item, create_service_source, service_facts,
                             original_form, upload_original, choose_file,
                             submit as finance_submit, mutable, receipt as finance_receipt,
                             cash_fact, SERVICE_COMMON)

SCENARIO = "customer-followon-hk100-101-102-103-104-110-111"
CARE = "/api/customer-service"
QUESTIONS = CARE + "/questionnaires"
REQUIREMENTS = (("HK-100", "其它收入单"), ("HK-101", "问卷设置"),
                ("HK-102", "车辆销售回访"), ("HK-103", "意向客户回访"),
                ("HK-104", "维修工单回访"), ("HK-110", "客户回访查询"),
                ("HK-111", "跟进记录查询"))
PARENTS = (
    ("sales-presales-hk001-007", "sales_business.py"),
    ("vehicle-purchase-hk171-177-178-026-021-018-029", "vehicle_purchase_business.py"),
    ("master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187", "master_data_business.py"),
    ("customer-service-hk098-107-108-109", "customer_service_business.py"),
    ("sales-order-hk008-009-011-022", "sales_order_business.py"),
    ("materials-hk069-045-054-083-070-072-073-051-061", "material_business.py"),
    ("repair-selfpay-hk031-034-044-049-053-079", "repair_business.py"),
)
PK = {name: "id" for name in (
    "flow_cases", "flow_tasks", "flow_events", "flow_customers", "audit_logs",
    "care_customer_vehicles", "care_vehicle_observations", "care_records", "care_receipts",
    "care_history_links", "group_identities", "group_identity_links", "group_events",
    "care_questionnaire_policies", "care_questionnaire_versions", "care_questionnaire_reviews",
    "care_questionnaire_bindings", "care_questionnaire_responses")}
PK["care_cases"] = "case_id"
PK.update({t: "id" for t in ("flow_request_receipts", "flow_accounts", "service_orders", "service_requests",
                           "service_tender_slices", "flow_payment_links", "cash_entries")})
VERSION = {"version", "updated_at"}
CASE_FIELDS = VERSION | {"state", "due_date", "completed_date", "owner_id", "data"}
TASK_FIELDS = VERSION | {"status", "done_by", "done_at", "due_date", "assignee_id"}
COMMON = {"care_receipts": 1, "care_records": 1, "flow_events": 1, "audit_logs": 1}
LABELS = {"sales_callback": "销售回访", "repair_callback": "维修回访", "questionnaire": "客户问卷"}


def today():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def rows(e, table):
    require(table in PK, "客户后继未核准保护表：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {PK[table]}")


def one(e, table, key):
    require(table in PK, "客户后继未核准原来源表：" + table)
    found = e.db.rows(f"SELECT * FROM {table} WHERE {PK[table]}=?", (key,))
    require(len(found) == 1, "客户后继原记录缺失或重复：" + table)
    return found[0]


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        requirements = []
        for key, title in REQUIREMENTS:
            original = catalog[key]
            require(original["title"] == title and original["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in original["acceptance_checks"]),
                    "客户后继原题名或check合同不一致：" + key)
            requirements.append({"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business",
                                       "status": "not_tested", "evidence": {}}],
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"}})
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [k for k, _ in REQUIREMENTS],
            "complete": False, "passed": False, "business_accepted": False,
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "source_contract_sha256": self.digest, "execution": "native_browser_original_forms",
            "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "requirements": requirements, "partial_requirements": [{"id": "HK-099", "title": "车辆档案",
                "status": "not_tested", "local_scope_status": "not_tested", "business_accepted": False,
                "acceptance_check_submitted": False, "evidence": {}, "unexecuted_scope": [
                    "明确跨店身份及服务摘要授权", "原单快照与逐件文件独立复核授权", "过期及撤销读取",
                    "有据原观察纠正及独立复核"]}],
            "unexecuted_requirements": ["HK-105", "HK-106", "HK-112"],
            "conditions": {"synthetic_inputs_only": True, "human_review": "pending",
                "external_contact_payment_or_service_acceptance": False, "production_acceptance": False}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        require(self.active is None, "上项客户后继尚未完成")
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

    def partial_vehicle(self, evidence):
        json.dumps(evidence, ensure_ascii=False)
        self.report["partial_requirements"][0].update(status="partial", local_scope_status="local_scope_passed", evidence=evidence)
        self.save()

    def failed(self, error):
        if self.active:
            self.active.update(status="failed", evidence_action_end=len(self.e.actions))
            self.active["acceptance_checks"][0].update(status="failed", error=self.e.scrub(error))
            self.report["failed_requirement"] = self.active["id"]
        else:
            self.report["failed_subrange"] = self.report.get("current_subrange", "same_run_preconditions")
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "客户七项未完整执行")
        require(self.report["partial_requirements"][0]["local_scope_status"] == "local_scope_passed", "交付VIN本店档案子范围未完成")
        self.report.update(complete=True, passed=True, executed_requirements=7, passed_requirements=7,
                           report_sources=sources, human_acceptance="pending")
        self.save()
        self.e.observe("customer_followon_checkpoint", {"path": str(self.path), "passed_checks": 7,
            "hk099": "partial/local_scope_passed", "full_193_business_acceptance": False})


class Guard:
    """Only finite IDs/columns and exact append counts; no table-wide exclusions."""
    def __init__(self, e, label, actor, *, appends, updates=None, cases=(), customer=None):
        self.e, self.label, self.actor = e, label, actor
        self.appends, self.updates = dict(appends), updates or {}
        self.cases, self.customer = set(cases), customer
        require(self.appends.keys() | self.updates.keys() <= PK.keys(), "客户后继保护超出原源表")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.appends.keys() | self.updates.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.old.keys(), "客户后继改变无关原表：" + str(sorted(changed)))
        additions, mutations = {}, {}
        for table, old in self.old.items():
            current = {r[PK[table]]: r for r in rows(self.e, table)}
            additions[table] = [r for key, r in current.items() if key not in {x[PK[table]] for x in old}]
            require(len(additions[table]) == self.appends.get(table, 0), "客户后继新增数不匹配：" + table)
            mutations[table] = []
            for original in old:
                key = original[PK[table]]
                require(key in current, "客户后继删除旧事实：" + table)
                columns = {k for k in original if original[k] != current[key][k]}
                require(columns <= self.updates.get(table, {}).get(key, set()),
                        "客户后继覆盖旧行/列：" + table + "/" + str(key) + "/" + str(sorted(columns)))
                if columns:
                    mutations[table].append({"id": key, "columns": sorted(columns)})
        owned = self.cases | {r["id"] for r in additions.get("flow_cases", [])}
        for table, added in additions.items():
            for r in added:
                if "store_id" in r:
                    require(r["store_id"] == 1, "客户新增原事实串门店：" + table)
                if "case_id" in r:
                    require(r["case_id"] in owned, "客户新增原事实串原单：" + table)
                if self.customer is not None and "customer_id" in r:
                    require(r["customer_id"] == self.customer, "客户新增原事实串客户")
                for key in ("actor_id", "created_by", "proposed_by", "confirmed_by"):
                    if key in r:
                        require(r[key] == self.actor["id"], "客户新增原事实借用身份：" + table)
        self.additions = additions
        result = {"label": self.label, "changed_tables": sorted(changed),
                  "appended_ids": {t: [r[PK[t]] for r in v] for t, v in additions.items() if v},
                  "updated_columns": {t: v for t, v in mutations.items() if v},
                  "all_other_tables_unchanged": True, "all_other_old_rows_and_columns_unchanged": True}
        self.e.observe("customer_followon_guard", result)
        return result


def match(response, path, method="GET"):
    actual = urlsplit(response.url).path
    return response.request.method == method and (actual.startswith(path) and actual[len(path):].isdigit()
                                                  if path.endswith("/") else actual == path)


async def login(e, context, credentials, key, route, title, path):
    async with e.page.expect_response(lambda r: match(r, path)) as pending:
        actor = await login_as(e, context, credentials, key, route, 1)
    response = await pending.value
    data = await response.json()
    require(response.status == 200, "本人原页面读取失败：" + path)
    await expect(e.page.locator("#main h1")).to_have_text(title)
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    return actor, data


async def click_locator(e, locator, label):
    await expect(locator).to_have_count(1)
    await expect(locator).to_be_visible()
    await expect(locator).to_be_enabled()
    e.action("click", label)
    await locator.click()


async def form(e, selector, title):
    await expect(e.page.locator(selector)).to_be_visible()
    await e.click(selector, "本人打开原表单：" + title)
    await expect(e.page.locator("#modal")).to_be_visible()
    await expect(e.page.locator("#modal-title")).to_have_text(title)


async def submit(e, actor, path, render_path, guard, *, status=200, method="POST", action=None, payload=None):
    async with e.page.expect_response(lambda r: match(r, render_path)) as rendered:
        async with e.page.expect_response(lambda r: match(r, path, method)) as pending:
            await e.click('#modal form button[type="submit"]', "本人明确提交原客户后继表单")
        response = await pending.value
        body = await response.json()
        require(response.status == status, "原客户后继 HTTP " + str(response.status) + "：" + e.scrub(body.get("detail", "")))
    read = await rendered.value
    shown = await read.json()
    require(read.status == 200, "原客户后继成功后的读取失败")
    headers, request = await response.request.all_headers(), response.request.post_data_json
    require(headers.get("cookie") and headers.get("x-csrf-token") and headers.get("x-store-id") == "1"
            and headers.get("x-app-request") == "1", "客户后继同源Cookie/CSRF/当前店不完整")
    require(isinstance(request, dict) and len(request.get("request_id", "")) >= 16, "客户后继原请求号缺失")
    if action is not None:
        actual_payload = payload(request) if callable(payload) else payload
        found = e.db.rows("SELECT * FROM care_receipts WHERE request_key=?", (request["request_id"],))
        require(len(found) == 1 and found[0]["actor_id"] == actor["id"] and found[0]["store_id"] == 1
                and found[0]["digest"] == digest([action, actual_payload]) and decoded(found[0]["result"]) == body,
                "客户原回执未绑定本人/当前店/精确原参数")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    protection = guard.finish()
    metadata = {"path": path, "method": method, "status": status, "native_ui": True,
        "cookie_present": True, "csrf_present": True, "actor_id": actor["id"], "store_id": 1,
        "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest(),
        "submitted_version": request.get("version"), "render_get_path": urlsplit(read.url).path,
        "guard": protection}
    e.observe("customer_followon_native_submit", metadata)
    return body, request, shown, metadata


def care_updates(e, case_id, vehicle_id, *, closing=False):
    # Original control_vehicle locks and increments this finite CV on handling.
    result = {"care_customer_vehicles": {vehicle_id: VERSION},
              "flow_cases": {case_id: CASE_FIELDS},
              "flow_tasks": {r["id"]: TASK_FIELDS for r in e.db.rows("SELECT id FROM flow_tasks WHERE case_id=?", (case_id,))}}
    if closing:
        result["care_cases"] = {case_id: {"result"}}
    return result


def dependencies(e, cp):
    root = Path(e.manifest["evidence_root"]).resolve()
    require(e.manifest.get("synthetic_data_only") is True
            and Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "客户后继仅允许同轮外部合成库")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance["snapshot_stable"] is True, "客户后继同轮镜像未稳定")
    for name in ("customer_followon_business.py", "business_acceptance_catalog.json", "finance_business.py",
                 *(p[1] for p in PARENTS)):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(),
                "客户后继当前镜像脚本变化：" + name)
    cp.report["provenance"] = {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")}
    cp.report["mirror"] = {k: provenance[k] for k in ("source_sha256", "script_sha256")}
    parents = {name: fixed_dependency(e, cp, name) for name, _ in PARENTS}
    sale = parents[PARENTS[4][0]]["report_sources"]
    repair = parents[PARENTS[6][0]]["report_sources"]
    customer = one(e, "flow_customers", sale["customer_id"])
    order = one(e, "flow_cases", sale["delivered_order_id"])
    inventory = e.db.rows("SELECT * FROM vehicles WHERE id=?", (sale["delivered_vehicle_id"],))
    require(len(inventory) == 1, "销售有限交付实车来源不唯一")
    vehicle = inventory[0]
    old_cv = one(e, "care_customer_vehicles", repair["customer_vehicle_id"])
    repair_case = one(e, "flow_cases", repair["repair_case_id"])
    require(order["kind"] == "order" and order["state"] == "delivered" and order["customer_id"] == customer["id"]
            and order["vehicle_id"] == vehicle["id"] and order["completed_date"] is not None,
            "本次交付客户/VIN/订单事实不完整")
    require(repair_case["kind"] == "repair" and repair_case["state"] == "completed"
            and repair_case["customer_id"] == old_cv["customer_id"] == repair["customer_id"]
            and old_cv["vin"] == repair["vin"] and old_cv["vin"] != vehicle["vin"], "原维修与本次销售两VIN来源混淆")
    local = next(r for r in parents[PARENTS[3][0]]["partial_requirements"] if r["id"] == "HK-099")
    require(local["local_scope_status"] == "local_scope_passed" and local["evidence"]["vehicle"]["id"] == old_cv["id"], "维修CV缺本次原客服来源")
    purchase = checkpoint_evidence(parents[PARENTS[1][0]], "HK-021")
    account_rows = e.db.rows("SELECT * FROM flow_accounts WHERE id=?", (purchase["payment"]["account_id"],))
    require(len(account_rows) == 1 and account_rows[0]["active"] and account_rows[0]["account_type"] == "bank", "原采购有限到账账户失效")
    account = account_rows[0]
    fixture = dict(e.manifest["business_fixtures"]["sales_order"])
    fixture["reception_key"] = e.manifest["business_fixtures"]["presales"]["reception_key"]
    require(fixture["store_id"] == customer["store_id"] == old_cv["store_id"] == order["store_id"]
            == repair_case["store_id"] == account["store_id"] == 1, "客户后继有限来源串门店")
    for role in ("service", "manager", "finance", "sales", "reception"):
        actor = e.manifest["users"][fixture[role + "_key"]]
        require(actor["role"] == role and len(e.db.rows("SELECT user_id FROM user_stores WHERE user_id=? AND store_id=1 AND role=?",
                (actor["id"], role))) == 1, "客户后继缺本店真实原岗位：" + role)
    require(e.manifest["users"]["admin"]["id"] != e.manifest["users"][fixture["manager_key"]]["id"], "问卷提出/批准身份必须不同")
    require(customer["owner_id"] == e.manifest["users"][fixture["sales_key"]]["id"]
            and customer["contact_allowed"] and customer["phone"], "销售回访客户缺实际允许联系或本人来源")
    old_customer = one(e, "flow_customers", old_cv["customer_id"])
    require(old_customer["contact_allowed"] and old_customer["phone"], "维修回访原客户缺明确联系电话及许可")
    require(not e.db.rows("SELECT id FROM business_entity_policies WHERE store_id=1"), "客户候选不代替经营主体策略验收")
    cp.report["source_preconditions"] = {"customer_id": customer["id"], "delivered_order_id": order["id"],
        "delivered_vehicle_id": vehicle["id"], "delivered_vin": vehicle["vin"], "repair_case_id": repair_case["id"],
        "repair_customer_vehicle_id": old_cv["id"], "repair_vin": old_cv["vin"], "account_id": account["id"],
        "current_cv_version": old_cv["version"], "old_checkpoint_cv_version_not_assumed_current": True}
    cp.save()
    return fixture, customer, order, vehicle, old_cv, repair_case, account


async def delivered_vehicle(e, context, credentials, fixture, customer, order, inventory, token):
    actor, _ = await login(e, context, credentials, fixture["service_key"], "customer-vehicles",
                           "客户车辆档案", CARE + "/vehicles")
    before = e.business_snapshot("before_new_delivered_cv_form")
    await form(e, '#main [data-act="care-vehicle-new"]', "登记客户车辆")
    source = "本次原订单" + order["number"] + "已交付签回，VIN与本店实车核对 " + token
    await fields(e, {"customer_id": customer["id"], "vin": inventory["vin"], "plate": "",
                     "model_name": inventory["model"], "source_reference": source, "confirmed": True})
    e.business_unchanged(before, "after_new_delivered_cv_inputs")
    links = e.db.rows("SELECT * FROM group_identity_links WHERE local_kind='customer' AND local_id=?", (customer["id"],))
    identities = e.db.rows("SELECT id FROM group_identities WHERE kind='vehicle' AND canonical_key=?", (inventory["vin"],))
    require(len(links) <= 1 and len(identities) <= 1, "有限集团身份来源重复")
    guard = Guard(e, "create_delivered_customer_vehicle", actor, appends={"care_customer_vehicles": 1,
        "group_identities": int(not links) + int(not identities), "group_identity_links": int(not links),
        "group_events": int(not links), "audit_logs": 1, "care_receipts": 1}, customer=customer["id"])
    body, request, shown, native = await submit(e, actor, CARE + "/vehicles", CARE + "/vehicles/", guard,
        status=201, action="vehicle_create", payload=lambda r: r["values"])
    key = body["vehicle"]["id"]
    cv = one(e, "care_customer_vehicles", key)
    require(cv["vin"] == inventory["vin"] and cv["customer_id"] == customer["id"]
            and cv["model_name"] == inventory["model"] and cv["identity_source"] == source,
            "原交付VIN客户档案不匹配")
    await vehicle_rendered(e, vehicle_facts(e, key), shown)
    await form(e, '#main [data-act="care-vehicle-edit"]', "维护客户车辆关系")
    reason = "按本次已交付原单核对车辆关系，保留已知车型和空车牌 " + token
    await fields(e, {"model_name": cv["model_name"], "plate": "", "active": True, "reason": reason})
    guard = Guard(e, "edit_delivered_customer_vehicle", actor, appends={"care_receipts": 1, "audit_logs": 1},
                  updates={"care_customer_vehicles": {key: VERSION | {"model_name", "plate", "active"}}})
    _, request_edit, shown, edit = await submit(e, actor, CARE + "/vehicles/" + str(key), CARE + "/vehicles/" + str(key),
        guard, method="PUT", action="vehicle_update", payload=lambda r: {"id": key, "version": r["version"], **r["values"]})
    require(request_edit["version"] == cv["version"], "原车辆关系维护缺当前CAS")
    updated = one(e, "care_customer_vehicles", key)
    await vehicle_rendered(e, vehicle_facts(e, key), shown)
    # The mileage is a declared synthetic handover reading, never inferred from
    # price, vehicle status, insurance, or another VIN's service observations.
    observation_source = "原订单" + order["number"] + "本次合成交接里程表实际读数0公里 " + token
    await form(e, '#main [data-act="care-observe"]', "登记日期与里程来源")
    await fields(e, {"kind": "delivery", "observed_date": order["completed_date"], "odometer_km": 0,
                     "source_reference": observation_source, "confirmed": True})
    guard = Guard(e, "observe_delivered_customer_vehicle", actor,
        appends={"care_vehicle_observations": 1, "care_receipts": 1, "audit_logs": 1},
        updates={"care_customer_vehicles": {key: VERSION}})
    observed, request_observation, shown, observation_native = await submit(e, actor, CARE + "/vehicles/" + str(key) + "/observations",
        CARE + "/vehicles/" + str(key), guard, action="observe",
        payload=lambda r: {"id": key, "version": r["version"], **r["values"]})
    require(request_observation["version"] == updated["version"], "交付观察缺原当前CV版本")
    f = vehicle_facts(e, key)
    observation = f["observations"][0]
    require(len(f["observations"]) == 1 and observation["kind"] == "delivery"
            and observation["observed_date"] == order["completed_date"] and observation["odometer_km"] == 0
            and observation["source_reference"] == observation_source and observed["observation"]["id"] == observation["id"],
            "实际交付观察日期/里程/原来源错误")
    await vehicle_rendered(e, f, shown)
    return f["vehicle"], {"vehicle": f["vehicle"], "observation": observation, "creation": native,
        "edit": edit, "observation_native": observation_native, "original_order_id": order["id"],
        "original_inventory_vehicle_id": inventory["id"], "declared_synthetic_handover_odometer_km": 0,
        "unexecuted_cross_store_scope": True}


async def new_care(e, actor, customer, vehicle, subtype, topic, *, source=None):
    if urlsplit(e.page.url).fragment != "customer-service":
        await nav(e, "customer-service", "客户服务工作台", CARE + "/cases")
    await select_value(e, '#main [name="care_create_type"]', subtype, "选择本次原客户服务类型")
    await form(e, '#main [data-act="care-new"]', "登记" + LABELS[subtype])
    async with e.page.expect_response(lambda r: match(r, CARE + "/lookup/vehicles")
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as vehicles:
        if source is not None:
            async with e.page.expect_response(lambda r: match(r, CARE + "/lookup/source_cases")
                    and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]
                    and parse_qs(urlsplit(r.url).query).get("subtype") == [subtype]) as sources:
                await select_value(e, '#modal [name="customer_id"]', customer["id"], "明确本轮原客户")
            source_response = await sources.value
            source_options = await source_response.json()
            require(source_response.status == 200 and any(r["id"] == source["id"] for r in source_options["items"]),
                    "本轮实际完成来源不在原客户候选")
        else:
            await select_value(e, '#modal [name="customer_id"]', customer["id"], "明确本轮原客户")
    response = await vehicles.value
    options = await response.json()
    require(response.status == 200 and any(r["id"] == vehicle["id"] for r in options["items"]), "原客户车辆候选缺有限来源")
    await fields(e, {"vehicle_id": vehicle["id"], "topic": topic,
        "description": "本次合成客户要求核对原交付或服务体验；联系及原回答单独登记。 " + topic,
        "priority": "normal", "assignee_id": actor["id"], "due_date": today()})
    if source is not None:
        await fields(e, {"source_case_id": source["id"]})
    appends = {**COMMON, "flow_cases": 1, "flow_tasks": 1, "care_cases": 1}
    if subtype == "questionnaire":
        appends["care_questionnaire_bindings"] = 1
    guard = Guard(e, "create_" + subtype, actor, appends=appends,
                  updates={"care_customer_vehicles": {vehicle["id"]: VERSION}}, customer=customer["id"])
    body, request, shown, native = await submit(e, actor, CARE + "/cases", CARE + "/cases/", guard,
        status=201, action="care_create", payload=lambda r: r["values"])
    key = body["case"]["id"]
    f = care_facts(e, key)
    require(f["case"]["created_by"] == f["case"]["owner_id"] == actor["id"]
            and f["case"]["kind"] == "customer_care" and f["case"]["flow_version"] == 2
            and f["case"]["state"] == "pending" and f["case"]["customer_id"] == customer["id"]
            and f["care"]["vehicle_id"] == vehicle["id"] and f["care"]["subtype"] == subtype
            and f["care"]["source_case_id"] == (source["id"] if source else None)
            and request["values"]["assignee_id"] == actor["id"], "客户新回访/问卷来源或实际身份不符")
    require(len(f["records"]) == len(f["events"]) == 1 and f["records"][0]["action"] == "create"
            and f["tasks"][0]["role"] == "customer_service" and f["tasks"][0]["assignee_id"] == actor["id"],
            "原care创建/责任任务不完整")
    await care_rendered(e, f, shown, actor)
    return f, {"native": native, "created_case_id": key, "actual_values": request["values"], "db": f}


async def care_action(e, actor, case_id, action, values):
    before = care_facts(e, case_id)
    titles = {"start": "接手办理", "followup": "登记跟进", "close": "登记结案"}
    await form(e, f'#main [data-act="care-action"][data-action="{action}"]', titles[action])
    await fields(e, {k: v for k, v in values.items() if k not in {"answers", "satisfaction", "recommend"}})
    if action == "close" and "answers" in values:
        for key, value in values["answers"].items():
            await fields(e, {"answer__" + key: ("yes" if value else "no") if isinstance(value, bool) else value})
    appends = dict(COMMON)
    if action == "close" and before["care"]["subtype"] == "questionnaire":
        appends["care_questionnaire_responses"] = 1
    guard = Guard(e, "care_" + action, actor, appends=appends,
        updates=care_updates(e, case_id, before["care"]["vehicle_id"], closing=action == "close"), cases={case_id})
    body, request, shown, native = await submit(e, actor, CARE + f"/cases/{case_id}/actions/{action}",
        CARE + f"/cases/{case_id}", guard, action="care_" + action,
        payload=lambda r: {"case_id": case_id, "version": r["version"], **r["values"]})
    expected_values = dict(values)
    if action == "close":
        expected_values.update(satisfaction=None, recommend=None)
    require(request["version"] == before["case"]["version"] and request["values"] == expected_values,
            "原care提交本版/结果/原题回答不符")
    after = care_facts(e, case_id)
    for family in ("records", "events"):
        require(after[family][:-1] == before[family], "客户原历史非单条追加：" + family)
    record, event = after["records"][-1], after["events"][-1]
    require(record["actor_id"] == event["actor_id"] == actor["id"] and record["action"] == action
            and event["action"] == "care_" + action and after["case"]["version"] > before["case"]["version"],
            "客户动作/事件/本人或原CAS不符")
    await care_rendered(e, after, shown, actor)
    return after, {"native": native, "record": record, "event": event}


async def callback(e, context, credentials, fixture, customer, vehicle, subtype, source, token):
    actor, _ = await login(e, context, credentials, fixture["service_key"], "customer-service",
                           "客户服务工作台", CARE + "/cases")
    f, created = await new_care(e, actor, customer, vehicle, subtype, LABELS[subtype] + "-" + token, source=source)
    key = f["case"]["id"]
    f, started = await care_action(e, actor, key, "start", {})
    updates = []
    for index, channel in enumerate(("phone", "in_person"), 1):
        note = "本次合成" + LABELS[subtype] + "第" + str(index) + "次实际联系：客户核对原单及交接事项 " + token
        f, native = await care_action(e, actor, key, "followup", {
            "channel": channel, "contact_result": "contacted", "note": note, "next_due_date": today()})
        require(f["records"][-1]["details"] == {"channel": channel, "contact_result": "contacted", "next_due_date": today()}
                and f["records"][-1]["note"] == note, "两次回访原沟通结果未保留")
        updates.append(native)
    note = "客户已核对本次合成原交付或接车事项，反馈已答复；本次回访结案 " + token
    f, closed = await care_action(e, actor, key, "close", {"result": "resolved", "note": note})
    require(f["case"]["state"] == "completed" and f["care"]["result"] == "resolved"
            and len(f["records"]) == 5 and len([r for r in f["records"] if r["action"] == "followup"]) == 2
            and f["tasks"][0]["status"] == "done" and f["tasks"][0]["done_by"] == actor["id"], "原回访未完整联系及结案")
    return f, {"create": created, "start": started, "two_followups": updates, "close": closed,
        "source_case_id": source["id"], "customer_vehicle_id": vehicle["id"], "db": f,
        "external_customer_contact_acceptance": False}


async def income(e, context, credentials, fixture, customer, account, token):
    item, item_proof = await create_income_item(e, context, credentials, fixture, token)
    f, preparation = await create_service_source(e, context, credentials, fixture, customer, item, token, "客户其它收入")
    key = f["case"]["id"]
    actor = e.manifest["users"][fixture["finance_key"]]
    proof = await upload_original(e, key, actor, "receipt", "customer-income-actual-receipt", token)
    await original_form(e, "serviceorder-action", "receive", "客户实际到账")
    await e.fill('#modal [name="amount"]', "60.00", "明确本次新服务实际到账60元")
    await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
    reference = "CARE-IN-" + token
    await e.fill('#modal [name="reference"]', reference, "本次独立实际收款凭证号")
    await choose_file(e, proof, "receipt")
    guard = Guard(e, "other_income_receive", actor, appends={**SERVICE_COMMON, "audit_logs": 2,
        "cash_entries": 1, "flow_payment_links": 1, "service_tender_slices": 1},
        updates=mutable(e, (key,), account=account["id"], service=True), cases={key}, customer=customer["id"])
    body, request, view, meta = await finance_submit(e, f"/api/service-orders/{key}/actions/receive", f"/api/service-orders/{key}")
    values = {"amount_cents": 6000, "account_id": account["id"], "reference": reference,
              "evidence_id": proof["file"]["id"]}
    require(request["version"] == f["case"]["version"] and request["values"] == values, "其它收入本版收款参数不符")
    protection = guard.finish()
    result_receipt = finance_receipt(e, request, actor, body, service_action="receive")
    after = service_facts(e, key)
    require(after["case"]["state"] == "completed" and view["summary"]["customer_due_cents"] == 0
            and len(after["payments"]) == len(after["tenders"]) == 1 and len(after["fulfillments"]) == 1,
            "其它收入独立履约及实收未完成")
    payment, tender = after["payments"][0], after["tenders"][0]
    cash = cash_fact(e, payment["cash_id"], 6000, "in", "workflow_other_income", account, actor["id"],
                     reference=reference, day=today())
    require(payment["amount_cents"] == tender["amount_cents"] == 6000 and payment["direction"] == "in"
            and payment["original_id"] is None and payment["account_id"] == account["id"]
            and tender["payment_link_id"] == payment["id"] and tender["credit_link_id"] is None
            and tender["evidence_id"] == proof["file"]["id"] and tender["bucket"] == "fee",
            "其它收入实际原Cash/Payment/Tender关系不符")
    require(after["quotes"] == f["quotes"] and after["authorizations"] == f["authorizations"]
            and after["fulfillments"] == f["fulfillments"] and after["approvals"] == f["approvals"],
            "收款改写原报价/独立批准/客户授权/实际履约")
    audits = guard.additions["audit_logs"]
    require({(r["action"], r["entity_type"], r["entity_id"]) for r in audits} == {
        ("create", "cash", cash["id"]), ("flow_serviceorder_receive", "flow", key)}, "其它收入原现金与业务审计不符")
    await expect(e.page.locator("#main h1")).to_have_text(after["case"]["title"])
    await expect(e.page.locator("#main")).to_contain_text("60.00")
    return after, {"item": item, "item_original_ui": item_proof, "quote_approval_authorization_fulfillment": preparation,
        "actual_receive": {"native": meta, "guard": protection, "receipt": result_receipt,
                           "file": proof, "cash": cash, "payment": payment, "tender": tender}, "db": after}


async def history_links(e, context, credentials, fixture, vehicle, sources, token):
    actor, _ = await login(e, context, credentials, fixture["service_key"], "customer-vehicles/" + str(vehicle["id"]),
                           "客户车辆 · " + (vehicle["plate"] or vehicle["vin"]), CARE + f'/vehicles/{vehicle["id"]}')
    trail = []
    for source, summary in sources:
        await form(e, '#main [data-act="care-history-link"]', "关联本店服务摘要")
        values = {"case_id": source["id"], "summary": summary,
                  "source_reference": "本轮原单" + source["number"] + "与客户/VIN一致 " + token, "confirmed": True}
        await fields(e, values)
        guard = Guard(e, "local_history_link", actor, appends={"care_history_links": 1, "audit_logs": 1,
            "care_receipts": 1}, cases={source["id"]})
        body, request, view, meta = await submit(e, actor, CARE + f'/vehicles/{vehicle["id"]}/history-links',
            CARE + f'/vehicles/{vehicle["id"]}', guard, status=201, action="history_link",
            payload=lambda r: {"vehicle_id": vehicle["id"], **r["values"]})
        require(request["values"] == values and len(guard.additions["care_history_links"]) == 1, "最小服务摘要原参数不符")
        link = guard.additions["care_history_links"][0]
        require(link["vehicle_id"] == vehicle["id"] and link["case_id"] == source["id"]
                and link["summary"] == summary and link["confirmed_by"] == actor["id"] and body["link_id"] == link["id"],
                "本店有限原单摘要绑定不符")
        await expect(e.page.locator("#main h1")).to_have_text("客户车辆 · " + (vehicle["plate"] or vehicle["vin"]))
        await expect(e.page.locator("#main")).to_contain_text(summary)
        await expect(e.page.locator(f'#main [data-route="{("customer-service" if source["kind"] == "customer_care" else "case")}/{source["id"]}"]')).to_be_visible()
        trail.append({"native": meta, "link": link})
    return trail


async def new_intent_followup(e, context, credentials, fixture, token):
    actor, _ = await login(e, context, credentials, fixture["reception_key"], "cases/lead", "售前接待", "/api/flow/cases")
    name, phone = "合成意向回访" + token, "138" + str(int(token, 16) % 100000000).zfill(8)
    await form(e, '#main [data-act="newcase"][data-kind="lead"]', "新建售前接待")
    await fields(e, {"customer_name": name, "customer_phone": phone, "source": "展厅到店"})
    guard = Guard(e, "new_intent_lead", actor, appends={"flow_cases": 1, "flow_customers": 1,
        "flow_tasks": 1, "flow_events": 1, "audit_logs": 1, "flow_request_receipts": 1})
    body, meta, _, request = await lead_submit(e, actor, "/api/flow/cases", 201)
    protection = guard.finish()
    key = body["id"]
    f = lead_facts(e, key)
    require(f["case"]["state"] == "unassigned" and f["case"]["kind"] == "lead" and f["case"]["flow_version"] == 2
            and f["case"]["owner_id"] == f["case"]["created_by"] == actor["id"]
            and f["customer"]["name"] == name and f["customer"]["phone"] == phone and f["customer"]["contact_allowed"] == 1,
            "新意向回访未由原输入建立独立客户接待")
    require(request["kind"] == "lead" and request["values"]["customer_name"] == name
            and request["values"]["customer_phone"] == phone and request["values"]["source"] == "展厅到店", "原新意向输入封包不符")
    trail = [{"native": meta, "guard": protection, "event": f["events"][0]}]
    manager, _ = await login(e, context, credentials, fixture["manager_key"], "case/" + str(key),
                              f["case"]["title"], f"/api/flow/cases/{key}")
    await rendered_case(e, f)
    seller = e.manifest["users"][fixture["sales_key"]]
    await action_form(e, "assign", "分派接待")
    await employee_choice(e, seller)
    update = {"flow_cases": {key: CASE_FIELDS}, "flow_customers": {f["customer"]["id"]: VERSION | {"owner_id"}},
              "flow_tasks": {r["id"]: TASK_FIELDS for r in f["tasks"]}}
    guard = Guard(e, "new_intent_assign", manager, appends={"flow_events": 1, "audit_logs": 1,
        "flow_tasks": 1, "flow_request_receipts": 1}, updates=update, cases={key}, customer=f["customer"]["id"])
    _, meta, _, request = await lead_submit(e, manager, f"/api/flow/cases/{key}/actions/assign", 200, case_id=key)
    require(request["version"] == f["case"]["version"] and request["values"] == {"assignee_id": seller["id"]}, "原新意向分派当前CAS或员工不符")
    protection = guard.finish()
    assigned = lead_facts(e, key)
    require(assigned["customer"]["owner_id"] == assigned["case"]["owner_id"] == seller["id"]
            and lead_task(assigned, "contact")["assignee_id"] == seller["id"]
            and lead_task(assigned, "assign", "done")["done_by"] == manager["id"], "新意向原分派任务/负责人错误")
    trail.append({"native": meta, "guard": protection, "event": assigned["events"][-1]})
    seller, _ = await login(e, context, credentials, fixture["sales_key"], "case/" + str(key),
                             assigned["case"]["title"], f"/api/flow/cases/{key}")
    f = assigned
    for action, title, values in (("intent", "转意向客户", {"need": "核对家庭购车配置及预算，当前仅意向回访 " + token, "due_date": today()}),
                                  ("follow", "记录意向跟进", {"result": "第一次实际合成意向联系：客户已核对车型，继续比较 " + token, "due_date": today()}),
                                  ("follow", "记录意向跟进", {"result": "第二次实际合成意向联系：已答复配置差异，今日继续回访 " + token, "due_date": today()})):
        await rendered_case(e, f)
        await action_form(e, action, title)
        await fields(e, values)
        guard = Guard(e, "new_intent_" + action, seller,
            appends={"flow_events": 1, "audit_logs": 1, "flow_request_receipts": 1, **({"flow_tasks": 1} if action == "intent" else {})},
            updates={"flow_cases": {key: CASE_FIELDS}, "flow_tasks": {r["id"]: TASK_FIELDS for r in f["tasks"]}},
            cases={key}, customer=f["customer"]["id"])
        _, meta, _, request = await lead_submit(e, seller, f"/api/flow/cases/{key}/actions/{action}", 200, case_id=key)
        require(request["version"] == f["case"]["version"] and request["values"] == values, "意向本人原CAS/实际沟通输入不符")
        protection = guard.finish()
        after = lead_facts(e, key)
        require(after["events"][:-1] == f["events"] and after["customer"] == f["customer"]
                and after["events"][-1]["actor_id"] == seller["id"] and after["events"][-1]["action"] == action
                and all(after["events"][-1]["detail"].get(k) == v for k, v in values.items())
                and after["case"]["state"] == "intent" and after["case"]["due_date"] == today()
                and lead_task(after, "follow")["assignee_id"] == seller["id"], "意向原本人联系/追加历史/唯一待办期限不符")
        trail.append({"native": meta, "guard": protection, "event": after["events"][-1]})
        f = after
    await rendered_case(e, f)
    pending = await due_work(e, f, "follow")
    return f, {"native": trail, "actual_today_work": pending, "db": f,
               "converted_parent_not_rewound": True, "external_customer_contact_acceptance": False}


async def lead_submit(e, actor, path, status, *, case_id=None):
    async with e.page.expect_response(lambda r: match(r, path, "POST")) as pending:
        body, meta, view = await native_submit(e, path, status, case_id=case_id)
    response = await pending.value
    request = response.request.post_data_json
    payload = {k: v for k, v in request.items() if k != "request_id"}
    operation = "create" if case_id is None else str(case_id) + ":" + path.rsplit("/", 1)[1]
    receipt = e.db.rows("SELECT * FROM flow_request_receipts WHERE request_key=?", (request["request_id"],))
    require(len(receipt) == 1 and receipt[0]["actor_id"] == actor["id"] and receipt[0]["store_id"] == 1
            and receipt[0]["case_id"] == body["id"] and receipt[0]["digest"] == digest({"operation": operation, "payload": payload}),
            "意向原回执未绑定本人/本店/原单和实际参数")
    meta["original_receipt_id"] = receipt[0]["id"]
    return body, meta, view, request


def normalized_questions(raw):
    return [{"min_value": None, "max_value": None, "max_length": None, "choices": [], **q} for q in raw]


async def publish_questions(e, context, credentials, fixture, token, generation):
    actor, catalog = await login(e, context, credentials, fixture["manager_key"], "customer-questionnaires",
                                 "问卷题目版本", QUESTIONS + "/versions")
    await form(e, '#main [data-act="care-q-propose"]', "提出新的问卷版本")
    name = "合成客户体验原题" + token + "第" + str(generation) + "版"
    reason = "明确本次合成发放使用新版原题；旧发放与原回答保持原版本 " + token
    await fields(e, {"name": name, "reason": reason})
    remove = e.page.locator('#modal .care-question-editor [data-act="care-q-remove"]')
    for _ in range(await remove.count()):
        e.action("click", "移除本次待提交编辑器的一道题")
        await remove.first.click()
    await expect(e.page.locator('#modal .care-question-editor')).to_have_count(0)
    raw = [
        {"key": "visits", "label": f"第{generation}版：本次已确认到店次数", "kind": "integer",
         "required": True, "min_value": 0, "max_value": 5},
        {"key": "resolved_feedback", "label": f"第{generation}版：客户确认答复已清楚", "kind": "boolean", "required": True},
        {"key": "next_step", "label": f"第{generation}版：客户明确后续计划", "kind": "choice", "required": True,
         "choices": [{"key": "confirmed", "label": "已明确后续安排"}, {"key": "none", "label": "暂无后续安排"}]},
    ]
    for index, question in enumerate(raw):
        await e.click('#modal [data-act="care-q-add"]', "真实增加本次原题")
        editors = e.page.locator('#modal .care-question-editor')
        await expect(editors).to_have_count(index + 1)
        editor = editors.nth(index)
        for key, value in (("q_key", question["key"]), ("q_label", question["label"])):
            e.action("fill", "明确待提交原题 " + key, value=value)
            await editor.locator('[name="' + key + '"]').fill(value)
        e.action("select", "明确原题类型", value=question["kind"])
        await editor.locator('[name="q_kind"]').select_option(question["kind"])
        e.action("check", "明确原题必答")
        await editor.locator('[name="q_required"]').check()
        if question["kind"] == "integer":
            for key, value in (("q_min", "0"), ("q_max", "5")):
                e.action("fill", "明确整数题范围", value=value)
                await editor.locator('[name="' + key + '"]').fill(value)
        if question["kind"] == "choice":
            e.action("fill", "明确原题两个可见选项")
            await editor.locator('[name="q_choices"]').fill("confirmed|已明确后续安排\nnone|暂无后续安排")
    old_policy = e.db.rows("SELECT * FROM care_questionnaire_policies WHERE store_id=1")
    require(len(old_policy) <= 1 and catalog["policy_version"] == (old_policy[0]["version"] if old_policy else 0), "问卷目录本版CAS不符")
    guard = Guard(e, "propose_questionnaire", actor, appends={"care_questionnaire_versions": 1,
        "care_receipts": 1, "audit_logs": 1, **({"care_questionnaire_policies": 1} if not old_policy else {})},
        updates={"care_questionnaire_policies": {r["id"]: VERSION | {"next_number"} for r in old_policy}})
    body, request, shown, native = await submit(e, actor, QUESTIONS + "/versions", QUESTIONS + "/versions", guard,
        status=201, action="questionnaire_propose", payload=lambda r: r["values"])
    require(request["values"] == {"policy_version": catalog["policy_version"], "name": name, "reason": reason, "questions": raw},
            "问卷提案未提交本次逐题原值")
    version = guard.additions["care_questionnaire_versions"][0]
    schema = normalized_questions(raw)
    require(version["proposed_by"] == actor["id"] and decoded(version["questions"]) == schema
            and version["digest"] == digest(schema) and version["number"] >= 2
            and body["questionnaire_version"]["id"] == version["id"], "问卷原题版本及规范化冻结摘要错误")
    require(version["number"] == (old_policy[0]["next_number"] if old_policy else 2)
            and e.db.rows("SELECT next_number FROM care_questionnaire_policies WHERE store_id=1")[0]["next_number"] == version["number"] + 1,
            "原题版本未按当前目录单次递增")
    proposer_id = actor["id"]
    review_actor, review_catalog = await login(e, context, credentials, "admin", "customer-questionnaires", "问卷题目版本", QUESTIONS + "/versions")
    require(review_actor["id"] != proposer_id and review_actor["role"] == "admin", "新原题没有独立复核身份")
    policy = e.db.rows("SELECT * FROM care_questionnaire_policies WHERE store_id=1")[0]
    previous = policy["active_version_id"]
    section = e.page.locator('#main section.panel').filter(has=e.page.get_by_role("heading", name=f'v{version["number"]} · {name}', exact=True))
    await expect(section).to_have_count(1)
    await click_locator(e, section.locator("details > summary"), "另一位主管展开本版完整原题")
    await expect(section).to_contain_text("0 至 5")
    for question in raw:
        await expect(section).to_contain_text(question["label"])
    await form(e, f'#main [data-act="care-q-review"][data-id="{version["id"]}"][data-decision="approve"]', "批准后仅用于后续发放")
    review_reason = "独立逐题核对本版0至5整数、明确是非、两选择及三题必答；不覆盖旧发放 " + token
    await fields(e, {"reason": review_reason, "confirmed": True})
    guard = Guard(e, "review_questionnaire", review_actor, appends={"care_questionnaire_reviews": 1, "care_receipts": 1, "audit_logs": 1},
                  updates={"care_questionnaire_policies": {policy["id"]: VERSION | {"active_version_id"}}})
    body, request, shown, review = await submit(e, review_actor, QUESTIONS + f'/versions/{version["id"]}/review', QUESTIONS + "/versions", guard,
        action="questionnaire_review", payload=lambda r: {"version_id": version["id"], **r["values"]})
    fact = guard.additions["care_questionnaire_reviews"][0]
    require(request["values"] == {"policy_version": review_catalog["policy_version"], "decision": "approve", "reason": review_reason, "confirmed": True}
            and fact["version_id"] == version["id"] and fact["schema_digest"] == version["digest"]
            and fact["actor_id"] == review_actor["id"] != proposer_id and fact["actor_role"] == "admin"
            and fact["previous_version_id"] == previous and shown["active_version_id"] == version["id"], "原题独立批准/本版CAS/旧发布依据不符")
    require(one(e, "care_questionnaire_versions", version["id"]) == version, "独立复核覆盖不可变原题版本")
    return version, {"native_proposal": native, "native_independent_review": review, "version": version,
                     "normalized_questions": schema, "review": fact}


async def answer_questionnaire(e, actor, f, answers, *, missing_check=False):
    key = f["case"]["id"]
    binding = e.db.rows("SELECT * FROM care_questionnaire_bindings WHERE case_id=?", (key,))
    require(len(binding) == 1, "原问卷缺唯一发放绑定")
    binding = binding[0]
    await form(e, '#main [data-act="care-action"][data-action="close"]', "登记结案")
    note = "本次合成客户按实际发放原题明确逐项回答；0与否保留本义 " + f["case"]["number"]
    await fields(e, {"result": "resolved", "note": note})
    negative = None
    if missing_check:
        before = e.business_snapshot("before_questionnaire_missing_answer")
        async with e.page.expect_response(lambda r: match(r, CARE + f"/cases/{key}/actions/close", "POST")) as pending:
            await e.click('#modal form button[type="submit"]', "缺少必答时真实尝试原结案")
        response = await pending.value
        refusal = await response.json()
        request = response.request.post_data_json
        require(response.status == 422 and "缺少必答题" in str(refusal.get("detail")) and request["version"] == f["case"]["version"]
                and request["values"]["answers"] == {}, "缺答原拒绝/本版/空回答合同不符")
        await expect(e.page.locator('#modal form')).not_to_have_attribute("aria-busy", "true")
        await expect(e.page.locator('#modal .formerror')).to_contain_text("缺少必答题")
        await expect(e.page.locator('#modal')).to_be_visible()
        e.business_unchanged(before, "after_questionnaire_missing_answer")
        require(care_facts(e, key) == f and not e.db.rows("SELECT id FROM care_questionnaire_responses WHERE binding_id=?", (binding["id"],)),
                "缺答拒绝仍留下答卷/结案修改")
        negative = {"status": 422, "detail": e.scrub(refusal["detail"]), "business_unchanged": True,
                    "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest()}
        await e.snapshot("questionnaire-missing-answer-refused")
    for question, value in answers.items():
        await fields(e, {"answer__" + question: ("yes" if value else "no") if type(value) is bool else value})
    guard = Guard(e, "questionnaire_actual_answer", actor, appends={**COMMON, "care_questionnaire_responses": 1},
                  updates=care_updates(e, key, f["care"]["vehicle_id"], closing=True), cases={key})
    body, request, view, native = await submit(e, actor, CARE + f"/cases/{key}/actions/close", CARE + f"/cases/{key}", guard,
        action="care_close", payload=lambda r: {"case_id": key, "version": r["version"], **r["values"]})
    require(request["values"] == {"result": "resolved", "note": note, "satisfaction": None, "recommend": None, "answers": answers},
            "实际答卷丢失0/否/单选原值")
    after = care_facts(e, key)
    original = guard.additions["care_questionnaire_responses"][0]
    record = after["records"][-1]
    require(original["binding_id"] == binding["id"] and original["record_id"] == record["id"] and decoded(original["answers"]) == answers
            and original["digest"] == digest({"binding_id": binding["id"], "record_id": record["id"],
                "schema_digest": binding["schema_digest"], "answers": answers}) and original["actor_id"] == actor["id"]
            and after["case"]["state"] == "completed" and after["tasks"][0]["status"] == "done"
            and after["records"][:-1] == f["records"] and after["events"][:-1] == f["events"]
            and record["details"]["answers"] == answers and record["details"]["questionnaire_schema_digest"] == binding["schema_digest"],
            "原答卷/结案/不可变绑定/追加原记录不符")
    require(one(e, "care_questionnaire_bindings", binding["id"]) == binding, "原回答更改发放题目")
    await care_rendered(e, after, view, actor)
    return after, {"native": native, "missing_answer_refusal": negative, "binding": binding, "response": original, "record": record}


async def query_and_open(e, actor, f):
    key = f["case"]["id"]
    before = e.business_snapshot("before_callback_query")
    if urlsplit(e.page.url).fragment == "customer-service":
        await expect(e.page.locator("#main h1")).to_have_text("客户服务工作台")
        await expect(e.page.locator("#care-filters")).to_be_visible()
    else:
        await nav(e, "customer-service", "客户服务工作台", CARE + "/cases")
    await e.fill('#care-filters [name="q"]', f["case"]["number"], "按本次真实回访单号查找")
    await select_value(e, '#care-filters [name="subtype"]', f["care"]["subtype"], "明确原回访类型")
    await select_value(e, '#care-filters [name="status"]', "completed", "明确实际已结案状态")
    async with e.page.expect_response(lambda r: match(r, CARE + "/cases")
            and parse_qs(urlsplit(r.url).query).get("q") == [f["case"]["number"]]) as pending:
        await e.click('#care-filters button[type="submit"]', "提交原回访查询")
    response = await pending.value
    data = await response.json()
    params = parse_qs(urlsplit(response.url).query)
    require(response.status == 200 and data["total"] == 1 and len(data["items"]) == 1
            and data["items"][0]["id"] == key and params["subtype"] == [f["care"]["subtype"]]
            and params["status"] == ["completed"] and params["page"] == ["1"], "回访非空筛选范围/原单不符")
    shown = data["items"][0]
    require(shown["customer_id"] == f["case"]["customer_id"] and shown["source_case_id"] == f["care"]["source_case_id"]
            and shown["vehicle_id"] == f["care"]["vehicle_id"] and shown["assignee_id"] == actor["id"]
            and shown["state"] == "completed" and shown["due_date"] == f["case"]["due_date"], "回访列表原来源/本人/期限不符")
    target = e.page.locator(f'#main tr:has([data-route="customer-service/{key}"])')
    await expect(target).to_have_count(1)
    values = [shown[k] for k in ("customer_name", "subtype_label", "topic", "state_label", "assignee_name", "due_date")]
    await expect(target.locator("td")).to_have_count(7)
    for index, value in enumerate(values):
        await expect(target.locator("td").nth(index)).to_have_text(str(value))
    async with e.page.expect_response(lambda r: match(r, CARE + f"/cases/{key}")) as original:
        await e.click(f'#main [data-route="customer-service/{key}"]', "真实打开筛选所得原回访")
    read = await original.value
    view = await read.json()
    require(read.status == 200, "回访原详情读取失败")
    await care_rendered(e, f, view, actor)
    e.business_unchanged(before, "after_callback_query_and_original")
    return {"parameters": params, "matched_id": key, "total": 1, "native_list_and_original": True,
            "list_response": shown, "business_unchanged": True}


async def care_history_query(e, actor, f):
    query = await query_and_open(e, actor, f)
    before = e.business_snapshot("before_care_records_refresh")
    panel = e.page.locator('#main section.panel').filter(has=e.page.get_by_role("heading", name="办理记录", exact=True))
    articles = panel.locator("article")
    await expect(articles).to_have_count(len(f["records"]))
    expected = []
    for index, record in enumerate(f["records"]):
        action_labels = {"create": "建立服务", "start": "接手办理", "followup": "登记跟进", "close": "登记结案"}
        stamp = local_stamp(record["created_at"])
        display_time = f"{stamp.year}/{stamp.month}/{stamp.day} {stamp.hour:02}:{stamp.minute:02}:{stamp.second:02}"
        await expect(articles.nth(index).locator("strong")).to_have_text(action_labels[record["action"]] + " · " + display_time)
        await expect(articles.nth(index)).to_contain_text(record["note"])
        if record["action"] == "followup":
            await expect(articles.nth(index)).to_contain_text("电话跟进" if record["details"]["channel"] == "phone" else "当面反馈")
            await expect(articles.nth(index)).to_contain_text("已联系确认")
        require(record["actor_id"] == actor["id"] and record["store_id"] == 1 and record["case_id"] == f["case"]["id"],
                "办理记录身份/原单/门店不符")
        expected.append({k: record[k] for k in ("id", "actor_id", "created_at", "action", "note", "details")})
    async with e.page.expect_response(lambda r: match(r, CARE + f'/cases/{f["case"]["id"]}')) as refreshed:
        e.action("reload", "原生刷新并核对追加记录不会重复")
        await e.page.reload()
    response = await refreshed.value
    view = await response.json()
    require(response.status == 200 and care_facts(e, f["case"]["id"]) == f, "刷新重复/覆盖原办理记录")
    await care_rendered(e, f, view, actor)
    e.business_unchanged(before, "after_care_records_refresh")
    return {"query": query, "records": expected, "refresh_native_get": True, "refresh_business_unchanged": True}


async def intent_history_query(e, context, credentials, fixture, f):
    actor, view = await login(e, context, credentials, fixture["sales_key"], "case/" + str(f["case"]["id"]),
                             f["case"]["title"], f'/api/flow/cases/{f["case"]["id"]}')
    before = e.business_snapshot("before_intent_original_history")
    await rendered_case(e, f)
    outer = e.page.locator('#main details.ux-history:has([data-panel-role="history"])')
    await click_locator(e, outer.locator(":scope > summary"), "真实展开意向操作留痕")
    history = [r for r in f["events"] if r["action"] == "follow"]
    require(len(history) == 2, "意向原跟进历史不是两次实际联系")
    for event in history:
        require(event["actor_id"] == actor["id"] and event["detail"]["due_date"] == today(), "意向记录本人/下次日期不符")
        item = outer.locator('.timelineitem').filter(has_text=event["detail"]["result"])
        original = one(e, "flow_events", event["id"])
        stamp = local_stamp(original["occurred_at"])
        display_time = f"{stamp.year}/{stamp.month}/{stamp.day} {stamp.hour:02}:{stamp.minute:02}:{stamp.second:02}"
        await expect(item.locator(".time")).to_have_text(actor["display_name"] + " · " + display_time)
        await click_locator(e, item.locator("summary"), "展开独立原意向沟通结果")
        await expect(item.get_by_text(event["detail"]["result"], exact=True)).to_be_visible()
    async with e.page.expect_response(lambda r: match(r, f'/api/flow/cases/{f["case"]["id"]}')) as pending:
        e.action("reload", "原生刷新意向原记录")
        await e.page.reload()
    response = await pending.value
    require(response.status == 200 and (await response.json())["id"] == f["case"]["id"]
            and lead_facts(e, f["case"]["id"]) == f, "意向刷新覆盖/重复原记录")
    await rendered_case(e, f)
    e.business_unchanged(before, "after_intent_original_history")
    return {"case_id": f["case"]["id"], "events": history, "native_expansion_and_refresh": True, "business_unchanged": True}


def local_stamp(raw):
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(ZoneInfo("Asia/Shanghai"))


def expected_questionnaire_report(e, day):
    bindings = e.db.rows("SELECT b.*,c.number AS case_number FROM care_questionnaire_bindings b JOIN flow_cases c ON c.id=b.case_id "
        "WHERE b.store_id=1 AND c.store_id=1 AND c.kind='customer_care' ORDER BY b.id")
    response_rows = {r["binding_id"]: r for r in e.db.rows("SELECT * FROM care_questionnaire_responses WHERE store_id=1 ORDER BY id")}
    records = {r["id"]: r for r in e.db.rows("SELECT * FROM care_records WHERE store_id=1 ORDER BY id")}
    issued, answers, distributions, totals = [], [], [], defaultdict(Counter)
    closed = 0
    for binding in bindings:
        if local_stamp(binding["issued_at"]).date().isoformat() == day:
            issued.append({"values": [binding["case_number"], binding["number"], binding["name"],
                local_stamp(binding["issued_at"]).strftime("%Y-%m-%d %H:%M:%S"), "原版本迁移" if binding["origin"] == "migration" else "实际发放"],
                "route": {"type": "case", "id": binding["case_id"]}})
        response = response_rows.get(binding["id"])
        record = records.get(response["record_id"]) if response else None
        if record is None or local_stamp(record["created_at"]).date().isoformat() != day:
            continue
        require(record["case_id"] == binding["case_id"], "统计原回答串发放原单")
        closed += 1
        data, actual = decoded(record["details"]), decoded(response["answers"])
        result_labels = {"resolved": "已解决", "appointment": "已约定后续办理", "declined": "客户不需要", "no_response": "多次联系未回应", "renewed": "续保已完成"}
        for question in decoded(binding["questions"]):
            key, kind = question["key"], question["kind"]
            present, value = key in actual, actual.get(key)
            if not present:
                text = "未回答"
            elif kind == "boolean":
                require(type(value) is bool, "布尔原答案被改型")
                text = "是" if value else "否"
            elif kind == "choice":
                text = next(x["label"] for x in question["choices"] if x["key"] == value)
            else:
                text = str(value)
            filters = {"version_number": binding["number"], "schema_digest": binding["schema_digest"], "question_key": key}
            answers.append({"values": [binding["case_number"], binding["number"], day, result_labels.get(data.get("result"), data.get("result") or "来源待核对"),
                key, question["label"], "已回答" if present else "未回答", text], "route": {"type": "case", "id": binding["case_id"]},
                "binding_id": binding["id"], "record_id": record["id"], **filters, "answered": present, "answer": value})
            token = (binding["number"], binding["schema_digest"], key, question["label"], kind)
            if not present:
                totals[token]["missing"] += 1
            elif kind == "text":
                totals[token]["有文字回答"] += 1
            else:
                totals[token][text] += 1
            # Preserve the zero missing bucket independently of actual False/0.
            totals[token].setdefault("missing", 0)
    charts = []
    for token, counts in sorted(totals.items()):
        number, hash_, key, label, kind = token
        values = {k: v for k, v in counts.items() if k != "missing"}
        if kind == "text":
            values = {"有文字回答": counts["有文字回答"]}
        values["未回答"] = counts["missing"]
        filters = {"version_number": number, "schema_digest": hash_, "question_key": key}
        for answer, count in values.items():
            distributions.append({"values": [number, hash_, key, label, answer, count], "route": None, "count": count, **filters})
        charts.append({"id": "questionnaire_" + str(number) + "_" + key, "title": "v" + str(number) + " · " + label,
            "type": "bar", "unit": "count", "labels": list(values), "series": [{"name": "实际结案回答数", "values": list(values.values())}],
            "table": "questionnaire_distribution", "table_filters": filters,
            "caption": "按发放时原题及期间结案记录统计；未回答单列，不当作否或0。不同题目版本不混算。"})
    return {"date_from": day, "date_to": day, "tables": {
        "questionnaire_issued": {"title": "期间实际发放的原题版本", "headers": ["原单", "版本", "名称", "发放时间", "来源"], "rows": issued},
        "questionnaire_answers": {"title": "期间实际结案的原题答案", "headers": ["原单", "版本", "结案日期", "实际结果", "题目编号", "原题", "回答状态", "原回答"], "rows": answers},
        "questionnaire_distribution": {"title": "按原题版本分开的回答分布", "headers": ["版本", "原题摘要", "题目编号", "原题", "回答", "记录数"], "rows": distributions}},
        "charts": charts, "metrics": {"questionnaires_issued": len(issued), "questionnaires_closed": closed}}


def safe_csv(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) and not text.replace("-", "", 1).replace(".", "", 1).isdigit() else text


async def questionnaire_csv(e, actor, data, key, locator, filters=None):
    filters = filters or {}
    table = data["tables"][key]
    selected = [r for r in table["rows"] if all(r.get(k) == v for k, v in filters.items())]
    guard = Guard(e, "questionnaire_export", actor, appends={"audit_logs": 1})
    async with e.page.expect_download() as pending_download:
        async with e.page.expect_response(lambda r: match(r, QUESTIONS + "/export/" + key)
                and all(parse_qs(urlsplit(r.url).query).get(k) == [str(v)] for k, v in filters.items())) as pending_response:
            await click_locator(e, locator, "真实下载当前原问卷同源CSV")
        response = await pending_response.value
        headers = await response.request.all_headers()
        content_type = await response.header_value("content-type") or ""
        e.observe("questionnaire_csv_native_response", {"table_key": key, "status": response.status,
            "content_type": content_type, "cookie_present": bool(headers.get("cookie")),
            "store_id": headers.get("x-store-id")})
        require(response.status == 200 and content_type.startswith("text/csv"),
                "问卷原CSV下载失败，HTTP " + str(response.status))
    download = await pending_download.value
    require(headers.get("cookie") and headers.get("x-store-id") == "1" and headers.get("x-app-request") == "1", "问卷原CSV未使用本人同源当前店")
    path = e.directory / ("questionnaire-" + key + "-" + str(len(e.actions)) + ".csv")
    require(await download.failure() is None, "问卷原生下载失败")
    await download.save_as(str(path))
    body = path.read_bytes()
    require(body.startswith(b"\xef\xbb\xbf"), "问卷原生下载BOM不符")
    actual = list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))
    expected = [table["headers"]] + [[safe_csv(v) for v in r["values"]] for r in selected]
    require(actual == expected, "问卷CSV遗漏/改写同范围完整原答案或分布")
    params = parse_qs(urlsplit(response.url).query)
    require(params.get("date_from") == [data["date_from"]] and params.get("date_to") == [data["date_to"]]
            and set(params) == {"date_from", "date_to"} | filters.keys(), "问卷CSV与图表日期/筛选不一致")
    protection = guard.finish()
    audit = guard.additions["audit_logs"][0]
    suffix = "" if not filters else f' v{filters["version_number"]} {filters["schema_digest"]} {filters["question_key"]}'
    require(audit["actor_id"] == actor["id"] and audit["store_id"] == 1 and audit["action"] == "export"
            and audit["entity_type"] == "questionnaire_report" and audit["entity_id"] is None
            and audit["reason"] == data["date_from"] + "至" + data["date_to"] + " " + key + suffix,
            "问卷导出不是精确一次原范围审计")
    return {"path": str(path), "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "rows": len(selected),
            "parameters": params, "audit_id": audit["id"], "guard": protection}


def report_panel(e, title):
    return e.page.locator('#main > section.panel').filter(has=e.page.get_by_role("heading", name=title, exact=True))


async def report_page_one(e, panel):
    previous = panel.locator('[data-act="page"]').get_by_text("上一页", exact=True)
    if await previous.count() and await previous.is_enabled():
        # Follow only the finite visible pagination sequence, never retry writes.
        caption = await panel.locator(".pagination span").inner_text()
        import re
        number = int(re.search(r"第 (\d+) 页", caption).group(1))
        for destination in range(number - 1, 0, -1):
            enclosing = previous.locator("xpath=ancestor::details[1]")
            if await enclosing.count() and await enclosing.get_attribute("open") is None:
                await click_locator(e, enclosing.locator(":scope > summary"), "展开当前分页的原问卷明细")
            await click_locator(e, previous, "原问卷明细返回上一页")
            await expect(panel.locator(".pagination span")).to_contain_text(f"第 {destination} 页")


async def questionnaire_table(e, data, key):
    before = e.business_snapshot("before_questionnaire_table_pages")
    table = data["tables"][key]
    target = report_panel(e, table["title"])
    await expect(target).to_have_count(1)
    await expect(target.locator("thead th")).to_have_text(table["headers"] + ["原单"])
    await report_page_one(e, target)
    for page_no, offset in enumerate(range(0, max(1, len(table["rows"])), 25), 1):
        expected = table["rows"][offset:offset + 25]
        visible = target.locator("tbody tr")
        await expect(visible).to_have_count(len(expected))
        for index, row in enumerate(expected):
            cells = visible.nth(index).locator("td")
            await expect(cells).to_have_count(len(table["headers"]) + 1)
            require([x.strip() for x in await cells.all_text_contents()][:-1] == [str(v).strip() for v in row["values"]],
                    "问卷完整原表显示与同范围DB/API不符：" + key)
            if row["route"]:
                await expect(visible.nth(index).locator(f'[data-route="customer-service/{row["route"]["id"]}"]')).to_have_count(1)
        if offset + 25 < len(table["rows"]):
            await click_locator(e, target.locator(f'[data-act="page"][data-page="{page_no + 1}"]'), "真实翻页核全量问卷原表")
            await expect(target.locator(".pagination span")).to_contain_text(f"第 {page_no + 1} 页")
    await report_page_one(e, target)
    e.business_unchanged(before, "after_questionnaire_table_pages")
    return {"key": key, "row_count": len(table["rows"]), "all_native_pages_checked": True}


async def questionnaire_report(e, context, credentials, fixture, actual_cases):
    actor, _ = await login(e, context, credentials, fixture["service_key"], "customer-questionnaire-report", "原题问卷统计", QUESTIONS + "/report")
    before = e.business_snapshot("before_questionnaire_report")
    day = today()
    await e.fill('#datefilters [name="date_from"]', day, "明确原发放及回答统计起日")
    await e.fill('#datefilters [name="date_to"]', day, "明确原发放及回答统计止日")
    async with e.page.expect_response(lambda r: match(r, QUESTIONS + "/report")
            and parse_qs(urlsplit(r.url).query).get("date_from") == [day]
            and parse_qs(urlsplit(r.url).query).get("date_to") == [day]) as pending:
        await e.click('#datefilters button[type="submit"]', "读取同原日期范围问卷统计")
    response = await pending.value
    data = await response.json()
    expected = expected_questionnaire_report(e, day)
    require(response.status == 200 and all(data[k] == expected[k] for k in ("date_from", "date_to", "tables", "charts", "metrics")),
            "问卷图表/完整明细/统计不是原发放和结案DB同范围")
    own_ids = {f["case"]["id"] for f in actual_cases}
    require(own_ids <= {r["route"]["id"] for r in data["tables"]["questionnaire_issued"]["rows"]}
            and own_ids <= {r["route"]["id"] for r in data["tables"]["questionnaire_answers"]["rows"]}
            and data["metrics"]["questionnaires_issued"] >= 2 and data["metrics"]["questionnaires_closed"] >= 2,
            "本轮两版真正发放及原回答未进入统计")
    await expect(e.page.locator("#main h1")).to_have_text("原题问卷统计")
    e.business_unchanged(before, "after_questionnaire_report_read")
    tables, exports, chart_proofs = [], [], []
    for key, table in data["tables"].items():
        tables.append(await questionnaire_table(e, data, key))
        exports.append(await questionnaire_csv(e, actor, data, key,
            report_panel(e, table["title"]).locator('[data-act="care-q-export"]')))
    before_charts = e.business_snapshot("before_questionnaire_charts")
    for chart in data["charts"]:
        target = report_panel(e, chart["title"])
        await expect(target).to_have_count(1)
        svg = target.locator('svg[role="img"]')
        await expect(svg).to_be_visible()
        require(await svg.get_attribute("aria-label") == chart["title"]
                and await svg.locator("rect > title").all_text_contents() == [str(label) + "：实际结案回答数 " + str(count)
                    for label, count in zip(chart["labels"], chart["series"][0]["values"])], "问卷原SVG逐值不符")
        await click_locator(e, target.locator("details > summary"), "真实展开本题同源分布及原回答")
        details = target.locator("details")
        distribution = [r for r in data["tables"]["questionnaire_distribution"]["rows"]
                        if all(r[k] == v for k, v in chart["table_filters"].items())]
        originals = [r for r in data["tables"]["questionnaire_answers"]["rows"]
                     if all(r[k] == v for k, v in chart["table_filters"].items())]
        await expect(details.locator("table")).to_have_count(2)
        actual_rows = details.locator("table").nth(0).locator("tbody tr")
        await expect(actual_rows).to_have_count(len(distribution))
        for index, row in enumerate(distribution):
            require([x.strip() for x in await actual_rows.nth(index).locator("td").all_text_contents()]
                    == [str(row["values"][4]), str(row["count"])], "本题分布与DB不符")
        await report_page_one(e, target)
        for page_no, offset in enumerate(range(0, max(1, len(originals)), 25), 1):
            expected_rows = [[r["values"][i] for i in (7, 6, 2, 3)] for r in originals[offset:offset + 25]]
            actual_rows = details.locator("table").nth(1).locator("tbody tr")
            await expect(actual_rows).to_have_count(len(expected_rows))
            for index, row in enumerate(expected_rows):
                actual = [x.strip() for x in await actual_rows.nth(index).locator("td").all_text_contents()]
                require(actual[:-1] == [str(v).strip() for v in row], "本题原回答完整分页与DB不符")
            if offset + 25 < len(originals):
                await click_locator(e, details.locator(f'[data-act="page"][data-page="{page_no + 1}"]'), "真实翻页核本题所有原回答")
                await expect(details.locator(".pagination span")).to_contain_text(f"第 {page_no + 1} 页")
                # The page is re-rendered; expand the original visible summary.
                if await target.locator("details").get_attribute("open") is None:
                    await click_locator(e, target.locator("details > summary"), "展开本题下一页原明细")
        await report_page_one(e, target)
        if await target.locator("details").get_attribute("open") is None:
            await click_locator(e, target.locator("details > summary"), "保留本题原明细供核对")
        chart_proofs.append({"id": chart["id"], "filters": chart["table_filters"], "svg_native_values_checked": True,
                             "distribution_rows": len(distribution), "original_answer_rows": len(originals), "all_native_answer_pages_checked": True})
    e.business_unchanged(before_charts, "after_questionnaire_charts")
    for chart in data["charts"]:
        if chart["table_filters"]["question_key"] not in {"visits", "resolved_feedback"}:
            continue
        target = report_panel(e, chart["title"])
        if await target.locator("details").get_attribute("open") is None:
            await click_locator(e, target.locator("details > summary"), "展开待导出的本题原回答")
        for key in ("questionnaire_distribution", "questionnaire_answers"):
            locator = target.locator(f'[data-act="care-q-export"][data-key="{key}"]')
            exports.append(await questionnaire_csv(e, actor, data, key, locator, chart["table_filters"]))
    original = actual_cases[0]
    target = report_panel(e, data["tables"]["questionnaire_answers"]["title"])
    before = e.business_snapshot("before_questionnaire_drill_original")
    button = target.locator(f'[data-route="customer-service/{original["case"]["id"]}"]').first
    async with e.page.expect_response(lambda r: match(r, CARE + f'/cases/{original["case"]["id"]}')) as pending:
        e.action("click", "从原回答表钻取本次真实问卷")
        await button.click()
    response = await pending.value
    view = await response.json()
    require(response.status == 200, "问卷统计原单钻取失败")
    await care_rendered(e, care_facts(e, original["case"]["id"]), view, actor)
    e.business_unchanged(before, "after_questionnaire_drill_original")
    return {"period": {"date_from": day, "date_to": day}, "metrics": data["metrics"], "tables": tables,
        "charts": chart_proofs, "native_csv": exports, "independent_db_full_range_checked": True,
        "native_original_drill_case_id": original["case"]["id"], "response_rate_not_inferred": True}


async def questionnaires(e, context, credentials, fixture, customer, vehicle, token):
    first, first_version = await publish_questions(e, context, credentials, fixture, token, 1)
    actor, _ = await login(e, context, credentials, fixture["service_key"], "customer-service", "客户服务工作台", CARE + "/cases")
    a, create_a = await new_care(e, actor, customer, vehicle, "questionnaire", "合成原题A-" + token)
    a, start_a = await care_action(e, actor, a["case"]["id"], "start", {})
    binding_a = e.db.rows("SELECT * FROM care_questionnaire_bindings WHERE case_id=?", (a["case"]["id"],))[0]
    require(binding_a["version_id"] == first["id"] and binding_a["schema_digest"] == first["digest"]
            and decoded(binding_a["questions"]) == decoded(first["questions"]), "第一版原发放没有冻结已批准题目")
    second, second_version = await publish_questions(e, context, credentials, fixture, token, 2)
    require(second["number"] == first["number"] + 1 and second["id"] != first["id"]
            and second["digest"] != first["digest"] and one(e, "care_questionnaire_bindings", binding_a["id"]) == binding_a
            and one(e, "care_questionnaire_versions", first["id"]) == first and care_facts(e, a["case"]["id"]) == a,
            "新版发布改写旧发放/原题/旧单")
    actor, _ = await login(e, context, credentials, fixture["service_key"], "customer-service", "客户服务工作台", CARE + "/cases")
    b, create_b = await new_care(e, actor, customer, vehicle, "questionnaire", "合成原题B-" + token)
    b, start_b = await care_action(e, actor, b["case"]["id"], "start", {})
    binding_b = e.db.rows("SELECT * FROM care_questionnaire_bindings WHERE case_id=?", (b["case"]["id"],))[0]
    require(binding_b["version_id"] == second["id"] and binding_b["schema_digest"] == second["digest"], "新版发放未使用新版原题")
    actor, view = await login(e, context, credentials, fixture["service_key"], "customer-service/" + str(a["case"]["id"]),
        a["case"]["title"] + " · " + a["case"]["number"], CARE + f'/cases/{a["case"]["id"]}')
    await care_rendered(e, a, view, actor)
    a, answers_a = await answer_questionnaire(e, actor, a, {"visits": 0, "resolved_feedback": False, "next_step": "none"}, missing_check=True)
    actor, view = await login(e, context, credentials, fixture["service_key"], "customer-service/" + str(b["case"]["id"]),
        b["case"]["title"] + " · " + b["case"]["number"], CARE + f'/cases/{b["case"]["id"]}')
    await care_rendered(e, b, view, actor)
    b, answers_b = await answer_questionnaire(e, actor, b, {"visits": 1, "resolved_feedback": True, "next_step": "confirmed"})
    report = await questionnaire_report(e, context, credentials, fixture, (a, b))
    return (a, b), {"first_version": first_version, "second_version": second_version,
        "first_issue": create_a, "second_issue": create_b, "first_start": start_a, "second_start": start_b,
        "first_original_answers": answers_a, "second_original_answers": answers_b,
        "old_binding_preserved_after_publication": True, "native_statistics": report}


async def customer_followon_business(e, context, credentials):
    checkpoint = Checkpoint(e)
    try:
        fixture, customer, delivered_order, inventory, repair_cv, repair_case, account = dependencies(e, checkpoint)
        token = uuid.uuid4().hex[:12]
        checkpoint.report["current_subrange"] = "HK099_delivered_local_vehicle"
        cv, local = await delivered_vehicle(e, context, credentials, fixture, customer, delivered_order, inventory, token)
        checkpoint.partial_vehicle(local)
        checkpoint.start("HK-100")
        income_case, income_proof = await income(e, context, credentials, fixture, customer, account, token)
        await checkpoint.passed(income_proof)
        checkpoint.start("HK-102")
        sales_callback, sales_proof = await callback(e, context, credentials, fixture, customer, cv, "sales_callback", delivered_order, token)
        await checkpoint.passed(sales_proof)
        checkpoint.start("HK-104")
        repair_customer = one(e, "flow_customers", repair_cv["customer_id"])
        repair_callback, repair_proof = await callback(e, context, credentials, fixture, repair_customer, repair_cv,
                                                      "repair_callback", repair_case, token)
        await checkpoint.passed(repair_proof)
        checkpoint.report["current_subrange"] = "HK099_finite_local_history_links"
        local["actual_local_service_history"] = await history_links(e, context, credentials, fixture, cv, (
            (delivered_order, "本次原销售已实际交付，本店仅共享最小交付摘要 " + token),
            (one(e, "flow_cases", sales_callback["case"]["id"]), "本次实际销售回访已联系并答复，原回访留痕独立保留 " + token)), token)
        checkpoint.partial_vehicle(local)
        checkpoint.start("HK-103")
        intent, intent_proof = await new_intent_followup(e, context, credentials, fixture, token)
        await checkpoint.passed(intent_proof)
        checkpoint.start("HK-101")
        issued, questionnaire_proof = await questionnaires(e, context, credentials, fixture, customer, cv, token)
        await checkpoint.passed(questionnaire_proof)
        checkpoint.start("HK-110")
        actor, _ = await login(e, context, credentials, fixture["service_key"], "customer-service", "客户服务工作台", CARE + "/cases")
        queries = [await query_and_open(e, actor, f) for f in (sales_callback, repair_callback)]
        await checkpoint.passed({"two_real_callback_types": queries, "q_matches_number_or_topic_only": True,
                                 "cross_store_unexecuted": True})
        checkpoint.start("HK-111")
        records = [await care_history_query(e, actor, f) for f in (sales_callback, repair_callback)]
        intent_records = await intent_history_query(e, context, credentials, fixture, intent)
        await checkpoint.passed({"two_distinct_callback_record_sources": records, "separate_original_intent_history": intent_records})
        checkpoint.finish({"customer_id": customer["id"], "delivered_order_id": delivered_order["id"],
            "customer_vehicle_id": cv["id"], "delivered_vehicle_id": inventory["id"], "income_case_id": income_case["case"]["id"],
            "income_cash_id": income_case["payments"][0]["cash_id"], "sales_callback_id": sales_callback["case"]["id"],
            "repair_callback_id": repair_callback["case"]["id"], "repair_customer_id": repair_cv["customer_id"],
            "repair_customer_vehicle_id": repair_cv["id"], "new_intent_lead_id": intent["case"]["id"],
            "questionnaire_case_ids": [f["case"]["id"] for f in issued]})
    except BaseException as error:
        checkpoint.failed(str(error))
        raise


CUSTOMER_FOLLOWON_SCENARIOS = ((SCENARIO, customer_followon_business, 1200),)
