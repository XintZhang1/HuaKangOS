"""Seven insurance/renewal contracts through this run's original native forms.

This candidate has no app imports, business HTTP writes, prewritten outcomes or
POST retries. Synthetic external facts remain distinct from real acceptance.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import require, login_as, employee_choice
from sales_order_business import fixed_dependency, checkpoint_evidence, fen_text
from vehicle_purchase_business import select_value, live_choice
from sales_followon_business import one, rows, case, original_submit, upload, proof_choice, account_choice, digest


SCENARIO = "insurance-renewal-hk013-014-077-113-114-115-116"
CUSTOMER = "customer-service-hk098-107-108-109"
MASTER = "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187"
PURCHASE = "vehicle-purchase-hk171-177-178-026-021-018-029"
API = "/api/insurance-orders"
CARE = "/api/customer-service"
CONTRACTS = {
    "HK-013": ("车辆保险单", ["补件、拒绝与真实合成出保各绑定本次原提交", "明确客户/VIN/保期、本版授权与终点任务事实一致"]),
    "HK-014": ("保险核价单", ["两版本分别独立复核与客户同版授权", "旧报价、同意与撤回不可覆盖，新版不能借旧授权"]),
    "HK-077": ("保险服务收款", ["保费代收、原款代缴与实际佣金分别记账", "客户直付证明不生成店内现金，实际金额区别于预计佣金"]),
    "HK-113": ("续保信息提取", ["原有效保期在真实提前量边界生成非空续保任务", "同CV/观察/规则版本冻结，原续保列表显示同单"]),
    "HK-114": ("续保信息分派", ["原care_handle分派到明确本店员工，同事务改负责人/日期", "旧日期/负责人留原记录，新员工本人可见与可办"]),
    "HK-115": ("续保分派回访", ["两次真实回访留独立历史，旧保期不能标完成", "真实新保险原来源期限延长后才原close renewed"]),
    "HK-116": ("保险到期提醒", ["未到边界/到边界/同周期去重和本人工作提醒独立核对", "完成后不重复，原实际撤保失效旧基准且新保期仍有效"]),
}
CASE_COLUMNS = {"version", "updated_at", "state", "data", "amount_cents", "cost_cents", "revenue_cents", "completed_date", "due_date"}
TASK_COLUMNS = {"version", "updated_at", "status", "done_by", "done_at", "assignee_id", "due_date", "title", "role"}
VERSION_COLUMNS = {"version", "updated_at"}
COMMON = {"flow_tasks", "flow_events", "audit_logs"}
TABLES = {t: "id" for t in (
    "flow_cases", "flow_tasks", "flow_events", "audit_logs", "flow_accounts", "cash_entries", "flow_payment_links",
    "care_customer_vehicles", "care_vehicle_observations", "care_records", "care_receipts", "care_reminder_rules",
    "observation_correction_receipts", "observation_insurance_invalidations", "observation_reminder_invalidations",
    "insurance_orders", "insurance_quotes", "insurance_reviews", "insurance_consents", "insurance_quote_cancellations",
    "insurance_submissions", "insurance_results", "insurance_renewal_links", "insurance_tenders", "insurance_pass_entries",
    "insurance_direct_entries", "insurance_terminations", "insurance_termination_reviews", "insurance_termination_consents",
    "insurance_termination_applications", "insurance_customer_refunds", "insurance_commissions", "insurance_commission_reviews",
    "insurance_commission_payments", "insurance_requests")}
TABLES.update(care_cases="case_id", observation_reminder_bases="case_id", business_entity_case_contexts="case_id", business_entity_cash_contexts="cash_id")
PARENTS = {
    **{t: ("insurance_quotes", "quote_id") for t in ("insurance_reviews", "insurance_consents", "insurance_quote_cancellations", "insurance_submissions")},
    **{t: ("insurance_terminations", "plan_id") for t in ("insurance_termination_reviews", "insurance_termination_consents", "insurance_termination_applications", "insurance_customer_refunds")},
    "insurance_commission_reviews": ("insurance_commissions", "confirmation_id"),
}
ACTION_TABLES = {
    "quote": {"insurance_quotes", "insurance_quote_cancellations"}, "review": {"insurance_reviews"},
    "authorize": {"insurance_consents"}, "submit": {"insurance_submissions"},
    "result": {"insurance_results", "care_vehicle_observations"},
    "receive": {"cash_entries", "flow_payment_links", "insurance_tenders", "business_entity_cash_contexts"},
    "disburse": {"cash_entries", "insurance_pass_entries", "business_entity_cash_contexts"},
    "insurer_return": {"cash_entries", "insurance_pass_entries", "business_entity_cash_contexts"},
    "direct_paid": {"insurance_direct_entries"}, "commission": {"insurance_commissions"},
    "commission_review": {"insurance_commission_reviews"},
    "commission_receive": {"cash_entries", "insurance_commission_payments", "business_entity_cash_contexts"},
    "commission_return": {"cash_entries", "insurance_commission_payments", "business_entity_cash_contexts"},
    "termination": {"insurance_terminations"}, "termination_review": {"insurance_termination_reviews"},
    "termination_consent": {"insurance_termination_consents"},
    "termination_apply": {"insurance_termination_applications", "observation_insurance_invalidations", "observation_reminder_invalidations", "care_records"},
    "refund": {"cash_entries", "flow_payment_links", "insurance_tenders", "insurance_customer_refunds", "business_entity_cash_contexts"},
}
FINANCIAL = {"receive", "disburse", "insurer_return", "direct_paid", "termination_apply", "refund", "commission", "commission_review", "commission_receive", "commission_return"}


def today():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def decoded(row):
    return {k: json.loads(v) if k in {"lines", "insurer_snapshot", "returns", "snapshot", "details"} and isinstance(v, str) else v for k, v in row.items()}


def owner_case(e, table, row):
    if "case_id" in row:
        return row["case_id"]
    if table == "insurance_orders":
        return row["id"]
    if table in PARENTS:
        parent, field = PARENTS[table]
        return one(e, parent, row[field])["case_id"]
    if table == "observation_insurance_invalidations":
        return row["source_case_id"]
    if table == "business_entity_cash_contexts":
        return row.get("case_id")
    return None


class Guard:
    """All tables/old bytes protected; only finite original IDs/columns may change."""
    def __init__(self, e, label, actor, store, *, append=(), update=None, cases=(), vehicle=None, new_kind=None):
        self.e, self.label, self.actor, self.store = e, label, actor, store
        self.append, self.update, self.cases = set(append), update or {}, set(cases)
        self.vehicle, self.kind = vehicle, new_kind
        require((self.append | self.update.keys()) <= TABLES.keys(), "保险原表守卫未核准")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: e.db.rows(f"SELECT * FROM {t} ORDER BY {TABLES[t]}") for t in self.append | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys() if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.append | self.update.keys(), "保险动作改动无关原表：" + str(sorted(changed)))
        owned, added, updated = set(self.cases), {}, {}
        if self.kind:
            old = {r["id"] for r in self.old["flow_cases"]}
            new = [r for r in self.e.db.rows("SELECT * FROM flow_cases ORDER BY id") if r["id"] not in old]
            require(len(new) == 1 and new[0]["kind"] == self.kind and new[0]["created_by"] == self.actor["id"], "原动作没有唯一正确新单")
            owned.add(new[0]["id"])
        for table, old_rows in self.old.items():
            pk = TABLES[table]
            current = {r[pk]: r for r in self.e.db.rows(f"SELECT * FROM {table} ORDER BY {pk}")}
            old_ids, updated[table] = {r[pk] for r in old_rows}, []
            for old in old_rows:
                require(old[pk] in current, "保险动作删除原事实：" + table)
                columns = {k for k in old if old[k] != current[old[pk]][k]}
                require(columns <= self.update.get(table, {}).get(old[pk], set()), "保险动作覆盖无权旧行/列：" + table + "/" + str(old[pk]) + "/" + str(sorted(columns)))
                if columns:
                    updated[table].append({"id": old[pk], "columns": sorted(columns)})
            new = [r for key, r in current.items() if key not in old_ids]
            require(not new or table in self.append, "只读旧表出现新增：" + table)
            if table in {"insurance_requests", "care_receipts", "observation_correction_receipts"}:
                require(len(new) == 1, "一次原提交必须恰好新增一条原回执：" + table)
            for row in new:
                if "store_id" in row:
                    require(row["store_id"] == self.store, "保险新增串店：" + table)
                for field in ("actor_id", "created_by"):
                    if field in row:
                        require(row[field] == self.actor["id"], "保险新增串本人：" + table)
                owner = owner_case(self.e, table, row)
                if table == "insurance_requests":
                    owner = json.loads(row["result"])["id"]
                elif table == "care_receipts" and json.loads(row["result"]).get("case"):
                    owner = json.loads(row["result"])["case"]["id"]
                if owner is not None:
                    require(owner in owned, "保险新增串原单：" + table)
                if "vehicle_id" in row and row["vehicle_id"] is not None:
                    require(row["vehicle_id"] == self.vehicle, "保险新增串客户车辆：" + table)
                if table == "cash_entries":
                    links = self.e.db.rows("SELECT case_id FROM flow_payment_links WHERE cash_id=? UNION ALL SELECT case_id FROM insurance_pass_entries WHERE cash_id=? UNION ALL SELECT case_id FROM insurance_commission_payments WHERE cash_id=?", (row["id"], row["id"], row["id"]))
                    require(len(links) == 1 and links[0]["case_id"] in owned, "保险现金没有唯一同原单资金来源")
            added[table] = [r[pk] for r in new]
        result = {"changed_tables": sorted(changed), "appended_ids": added, "updated_columns": updated,
                  "protected_old_rows_and_other_stores": True, "unrelated_tables_and_stock_unchanged": True}
        self.e.observe("insurance_source_guard", {"label": self.label, **result})
        return result


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        bindings = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, (title, _) in CONTRACTS.items():
            require(bindings[key]["title"] == title and bindings[key]["source_review_status"] == "source_reviewed" and any(c["check_id"] == key + "-business" for c in bindings[key]["acceptance_checks"]), "保险目录源合同不匹配：" + key)
        self.path = e.directory / "business-checkpoint.json"
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": list(CONTRACTS), "complete": False, "passed": False,
            "source_contract_sha256": self.digest, "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "execution": "native_browser_original_forms", "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "human_acceptance": "pending",
            "conditions": {"synthetic_short_period_insurance": True, "production_bank_or_insurer_results": False, "real_customer_signature": False, "clamav_acceptance": False},
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested", "criteria": criteria, "evidence": {}}],
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"}} for key, (title, criteria) in CONTRACTS.items()]}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active.setdefault("evidence_action_start", len(self.e.actions))
        self.save()

    def note(self, **evidence):
        self.active["acceptance_checks"][0]["evidence"].update(evidence)
        self.save()

    async def passed(self, **evidence):
        self.note(**evidence)
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.active["acceptance_checks"][0]["error"] = self.e.scrub(error)
            self.report["failed_requirement"] = self.active["id"]
        for r in self.report["requirements"]:
            if r["status"] == "running":
                r["status"] = r["acceptance_checks"][0]["status"] = "partial"
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "保险七项未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=7, passed_requirements=7, report_sources=sources)
        self.save()
        self.e.observe("insurance_business_checkpoint", {"path": str(self.path), "report_sources": sources, "business_accepted": False})


def source_facts(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "保险候选只允许本轮合成实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "保险库不是本次外置runtime")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance["snapshot_stable"] is True, "保险来源镜像未冻结")
    for name in ("insurance_business.py", "sales_followon_business.py", "sales_order_business.py", "sales_business.py", "vehicle_purchase_business.py", "customer_service_business.py", "master_data_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(), "保险来源脚本指纹变化：" + name)
    cp.report["mirror"] = {"provenance_sha256": hashlib.sha256(raw).hexdigest(), "source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"]}
    care, master, purchase = [fixed_dependency(e, cp, name) for name in (CUSTOMER, MASTER, PURCHASE)]
    fixture = dict(e.manifest["business_fixtures"]["repair"])
    for role in ("service", "manager", "finance"):
        require(e.manifest["users"][fixture[role + "_key"]]["role"] == role, "保险缺真实本店岗位：" + role)
    local = next(r for r in care["partial_requirements"] if r["id"] == "HK-099")
    require(local["local_scope_status"] == "local_scope_passed" and local["business_accepted"] is False and local["acceptance_check_submitted"] is False, "不可借保险提升099原部分来源")
    given = local["evidence"]
    cv = one(e, "care_customer_vehicles", given["vehicle"]["id"])
    customer = one(e, "flow_customers", cv["customer_id"])
    require(cv["active"] and cv["store_id"] == customer["store_id"] == fixture["store_id"] and customer["contact_allowed"] and customer["phone"], "保险原客户车辆或允许联系来源无效")
    for field in ("id", "customer_id", "customer_identity_id", "vehicle_identity_id", "vin", "store_id", "identity_source", "created_by"):
        require(cv[field] == given["vehicle"][field], "099明确客户车辆身份变化：" + field)
    require(len(given["observations"]) == 2, "本轮CV缺两条原实测观察")
    for item in given["observations"]:
        require(one(e, "care_vehicle_observations", item["observation"]["id"]) == item["observation"], "原099观察被覆写")
    link = given["original_consultation_history"]["original_link"]
    require(one(e, "care_history_links", link["id"]) == link and link["vehicle_id"] == cv["id"] and case(e, link["case_id"])["state"] == "completed", "本轮CV缺真实原咨询摘要")
    insurer = one(e, "master_insurers", checkpoint_evidence(master, "HK-172")["row"]["id"])
    account = one(e, "flow_accounts", checkpoint_evidence(purchase, "HK-021")["payment"]["account_id"])
    require(insurer["active"] and account["active"] and insurer["store_id"] == account["store_id"] == fixture["store_id"], "保险公司/原账户停用或串店")
    require(not e.db.rows("SELECT id FROM care_reminder_rules WHERE store_id=? AND active=1", (fixture["store_id"],)), "本次已有其它启用提醒规则，须先明确其合法生成范围，不覆盖或隐藏")
    require(not e.db.rows("SELECT id FROM care_reminder_rules WHERE store_id=? AND kind='renewal'", (fixture["store_id"],)), "本次已存在续保规则，须明确原来源再独立登记适配，不覆盖未知旧规则")
    cp.report["source_preconditions"] = {"customer": customer, "customer_vehicle": cv, "insurer": insurer, "original_account": account,
        "hk099_source_status": "partial/local_scope_passed", "original_observation_ids": [r["observation"]["id"] for r in given["observations"]],
        "business_timezone": "Asia/Shanghai", "planned_synthetic_inputs": {"first_premium_v1_cents": 20000, "first_premium_v2_cents": 22000,
            "expected_commission_cents": 1500, "actual_commission_cents": 1200, "first_policy_days": 10, "renewal_policy_days": 365}}
    cp.save()
    return fixture, customer, cv, insurer, account


def updates(e, key, cv, *, renewal=None, account=None, care=False, close=False):
    result = {"flow_cases": {key: CASE_COLUMNS | ({"owner_id"} if care else set())},
              "flow_tasks": {r["id"]: TASK_COLUMNS for r in rows(e, "flow_tasks", key)},
              "care_customer_vehicles": {cv["id"]: VERSION_COLUMNS}}
    if renewal is not None:
        result["flow_cases"][renewal] = VERSION_COLUMNS
    if account is not None:
        result["flow_accounts"] = {account["id"]: VERSION_COLUMNS}
    if close:
        result["care_cases"] = {key: {"result"}}
    return result


async def read_as(e, context, credentials, fixture, role, key, *, care=False):
    path = (CARE + "/cases/" if care else API + "/") + str(key)
    route = ("customer-service/" if care else "insurance-orders/") + str(key)
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], route, fixture["store_id"])
    response = await pending.value
    view = await response.json()
    require(response.status == 200 and view["id"] == key and view["version"] == case(e, key)["version"], "原岗位未读取同单当前CAS")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(view["number"])
    return actor, view


async def responsible(e, context, credentials, fixture, role, key, action, cv):
    task_key = "insurance_" + ({"submit": "handle", "result": "handle"}.get(action, action))
    tasks = [r for r in rows(e, "flow_tasks", key) if r["key"] == task_key and r["status"] == "open"]
    selected = e.manifest["users"][fixture[role + "_key"]]
    # quote/commission/insurer_return originate from UI while their task may be
    # absent in the original domain. Other staged actions require one task.
    optional = action in {"quote", "commission", "insurer_return", "termination"}
    require(len(tasks) == 1 or optional and not tasks, "保险原待办缺失或不唯一：" + task_key)
    transfer = {"task_key": task_key, "task_id": tasks[0]["id"] if tasks else None, "assignee_id": selected["id"], "handoff_needed": False}
    if tasks and tasks[0]["assignee_id"] != selected["id"]:
        old = tasks[0]
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/flow/cases/{key}") as loaded:
            manager = await login_as(e, context, credentials, fixture["manager_key"], "case/" + str(key), fixture["store_id"])
        response = await loaded.value
        original_view = await response.json()
        require(response.status == 200 and original_view["id"] == key and original_view["version"] == case(e, key)["version"], "交接前未读取同原单当前版本")
        await expect(e.page.locator("#main .pagehead")).to_contain_text(original_view["number"])
        await expect(e.page.locator(f'#main [data-act="assign"][data-id="{old["id"]}"]')).to_have_count(1)
        await expect(e.page.locator(f'#main [data-act="assign"][data-id="{old["id"]}"]')).to_be_visible()
        await e.click(f'#main [data-act="assign"][data-id="{old["id"]}"]', "主管明确交接本次保险原待办")
        await employee_choice(e, selected)
        reason = "本次保险对应原岗位员工本人接手，逐张交接"
        await e.fill('#modal [name="reason"]', reason, "记录原待办交接原因")
        guard = Guard(e, "insurance_task_handoff", manager, fixture["store_id"], append={"flow_events", "audit_logs"},
            update={"flow_tasks": {old["id"]: TASK_COLUMNS}, "flow_cases": {key: VERSION_COLUMNS}}, cases={key}, vehicle=cv["id"])
        _, _, meta, request = await original_submit(e, f'/api/flow/tasks/{old["id"]}/assign', lambda p: p == f"/api/flow/cases/{key}", guard, fixture["store_id"], request_id_required=False)
        require(request == {"version": old["version"], "assignee_id": selected["id"], "reason": reason}, "原任务交接三字段不匹配")
        transfer.update(handoff_needed=True, native=meta)
    actor, view = await read_as(e, context, credentials, fixture, role, key)
    if tasks:
        current = one(e, "flow_tasks", tasks[0]["id"])
        require(current["assignee_id"] == actor["id"] and current["status"] == "open", "原保险待办未交给本人")
    return actor, view, transfer


async def original_form(e, action, *, extra=""):
    selector = f'#main [data-act="insurance-action"][data-key="{action}"]' + extra
    await expect(e.page.locator(selector)).to_have_count(1)
    await expect(e.page.locator(selector)).to_be_visible()
    await e.click(selector, "本人办理原保险步骤 " + action)
    await expect(e.page.locator("#modal form")).to_be_visible()


async def command(e, fixture, actor, key, action, cv, *, expected=None, account=None, renewal=None, invalidated=()):
    before, events = case(e, key), rows(e, "flow_events", key)
    changes = updates(e, key, cv, renewal=renewal, account=account)
    owned = {key} | set(invalidated)
    if renewal is not None:
        owned.add(renewal)
    # Completed affected care retains its original entire Case and done Task.
    for care_id in invalidated:
        old = case(e, care_id)
        if old["state"] in {"pending", "working"} and any(t["status"] == "open" and t["key"] == "care_handle" for t in rows(e, "flow_tasks", care_id)):
            changes["flow_cases"][care_id] = {"state", "completed_date", "version", "updated_at"}
            changes["flow_tasks"].update({t["id"]: {"status", "done_by", "done_at", "version", "updated_at"} for t in rows(e, "flow_tasks", care_id)})
    guard = Guard(e, "insurance_" + action, actor, fixture["store_id"], append=COMMON | {"insurance_requests"} | ACTION_TABLES[action], update=changes, cases=owned, vehicle=cv["id"])
    body, view, meta, request = await original_submit(e, API + f"/{key}/actions/{action}", lambda p: p == API + "/" + str(key), guard, fixture["store_id"])
    require(request["version"] == before["version"] and body["id"] == view["id"] == key and body["version"] == case(e, key)["version"] > before["version"], "保险原提交CAS/身份不符")
    for field in ("id", "kind", "flow_version", "number", "store_id", "parent_id", "customer_id", "created_by", "owner_id"):
        require(case(e, key)[field] == before[field], "保险原提交改写身份：" + field)
    for field, value in (expected or {}).items():
        require(request["values"][field] == value, "保险原输入不符：" + field)
    receipt = e.db.rows("SELECT * FROM insurance_requests WHERE request_key=?", (request["request_id"],))
    require(len(receipt) == 1 and receipt[0]["actor_id"] == actor["id"] and json.loads(receipt[0]["result"])["id"] == key, "保险缺唯一同单本人回执")
    current_events = rows(e, "flow_events", key)
    require(current_events[:len(events)] == events and len(current_events) == len(events) + 1 and current_events[-1]["action"] == "insurance_" + action and current_events[-1]["actor_id"] == actor["id"], "保险步骤未唯一追加本人事件")
    return view, {"native": meta, "request_values": request["values"], "event": current_events[-1], "receipt_id": receipt[0]["id"]}


async def create_order(e, context, credentials, fixture, customer, cv, *, previous=None, renewal=None):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == API) as pending:
        service = await login_as(e, context, credentials, fixture["service_key"], "insurance-orders", fixture["store_id"])
    require((await pending.value).status == 200, "保险原列表读取失败")
    await expect(e.page.locator("#main h1")).to_have_text("保险核价与结算")
    await e.click('#main [data-act="insurance-new"]', "为本轮明确客户车辆建立原保险单")
    label = customer["name"] + (" · " + customer["phone"] if customer["phone"] else "")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == API + "/catalog" and "customer_id=" + str(customer["id"]) in r.url) as loading:
        await live_choice(e, "customer", customer["name"], label, expected_value=customer["id"])
    catalogue = await (await loading.value).json()
    require(any(r["id"] == cv["id"] and r["customer_id"] == customer["id"] and r["vin"] == cv["vin"] for r in catalogue["vehicles"]), "原保险候选没有同客户VIN")
    await live_choice(e, "vehicle", cv["vin"], (cv["plate"] + " · " if cv["plate"] else "") + cv["vin"], expected_value=cv["id"])
    current_renewal = case(e, renewal) if renewal is not None else None
    if previous is not None:
        await e.click('#modal details > summary', "明确关联真实原保单和在办续保任务")
        await live_choice(e, "previous", previous["policy_number"], previous["policy_number"] + " · " + cv["vin"], expected_value=previous["id"])
        await live_choice(e, "renewal", current_renewal["title"], current_renewal["title"], expected_value=renewal)
        listed = next(r for r in catalogue["renewals"] if r["id"] == renewal)
        require(listed["version"] == current_renewal["version"], "续保候选未读当前原版本")
    await e.fill('#modal [name="due_date"]', today().isoformat(), "记录本人保险办理日")
    await e.fill('#modal [name="reason"]', "合成短期保险实际原流程；续保必须新的明确保单来源" if previous is None else "明确本客户VIN原保单及本次续保任务，登记新的有效保期", "填写本人保险需求")
    changes = {"care_customer_vehicles": {cv["id"]: VERSION_COLUMNS}}
    if renewal is not None:
        changes["flow_cases"] = {renewal: VERSION_COLUMNS}
    guard = Guard(e, "insurance_create", service, fixture["store_id"], append=COMMON | {"flow_cases", "insurance_orders", "insurance_requests", "insurance_renewal_links", "business_entity_case_contexts"},
        update=changes, cases={renewal} if renewal else set(), vehicle=cv["id"], new_kind="insurance")
    body, view, meta, request = await original_submit(e, API, lambda p: bool(re.fullmatch(API + r"/\d+", p)), guard, fixture["store_id"], status=201)
    key = body["id"]
    require(body["flow_version"] == 3 and case(e, key)["parent_id"] is None and request["customer_id"] == customer["id"] and request["customer_vehicle_id"] == cv["id"]
            and request["source_order_id"] is None and request["source_version"] is None and request["delivery_blocking"] is False, "保险建立没有明确独立同客户CV来源")
    require(body["order"]["vin"] == cv["vin"] and body["order"]["renewal_task_id"] == renewal and request["previous_policy_id"] == (previous["id"] if previous else None)
            and request["renewal_version"] == (current_renewal["version"] if current_renewal else None), "保险续保关联ID/版本错配")
    return key, {"native": meta, "request": request, "order": one(e, "insurance_orders", key), "case": case(e, key)}


async def quote(e, context, credentials, fixture, key, cv, insurer, token, *, revision, premium, expected_commission, days, mode, renewal=None):
    actor, before, transfer = await responsible(e, context, credentials, fixture, "service", key, "quote", cv)
    await original_form(e, "quote")
    current_insurer = one(e, "master_insurers", insurer["id"])
    await live_choice(e, "insurer", insurer["name"], insurer["name"] + " · " + insurer["license_number"], expected_value=insurer["id"])
    await select_value(e, '#modal [name="mode"]', mode, "明确保费实际资金模式")
    lines = [{"name": "合成交强险-" + token, "premium_cents": 10000}, {"name": "合成短期商业险-" + token, "premium_cents": premium - 10000}]
    sections = e.page.locator('#modal [data-insurance-line]')
    await expect(sections).to_have_count(2)
    for i, row in enumerate(lines):
        e.action("fill", "填写原险种与保费", line=i, amount_cents=row["premium_cents"])
        await sections.nth(i).locator('[name="line_name"]').fill(row["name"])
        await sections.nth(i).locator('[name="line_amount"]').fill(fen_text(row["premium_cents"]))
    values = {"expected": fen_text(expected_commission), "payee": "合成保险公司实际户名-" + token if mode == "store_collect" else "",
              "payee_reference": "SYN-INSURER-" + token if mode == "store_collect" else "", "start": today().isoformat(),
              "end": (today() + timedelta(days=days)).isoformat(), "expiry": (today() + timedelta(days=3)).isoformat(),
              "terms": "合成保险约定；此原报价仅用于隔离验证，不代表真实承保或签字-" + token,
              "reason": "本次独立核价第" + str(revision) + "版，保费和预计佣金分别明确"}
    for field, value in values.items():
        await e.fill(f'#modal [name="{field}"]', value, "填写本版明确保险 " + field)
    view, meta = await command(e, fixture, actor, key, "quote", cv, renewal=renewal,
        expected={"insurer_id": insurer["id"], "insurer_version": current_insurer["version"], "lines": lines, "collection_mode": mode,
                  "expected_commission_cents": expected_commission, "start_date": values["start"], "end_date": values["end"], "valid_until": values["expiry"]})
    q = decoded(one(e, "insurance_quotes", view["quote"]["id"]))
    require(q["revision"] == revision and q["premium_cents"] == premium and q["collection_mode"] == mode and q["actor_id"] == actor["id"], "保险报价原金额/版本/本人不符")
    facts = {k: q[k] for k in ("lines", "expected_commission_cents", "collection_mode", "start_date", "end_date", "valid_until", "terms", "reason", "insurer_snapshot", "premium_cents", "revision")}
    facts["vin"] = cv["vin"]
    require(q["digest"] == view["quote"]["digest"] == digest("insurance_quote", facts) and q["insurer_snapshot"]["id"] == insurer["id"] and q["insurer_snapshot"]["version"] == current_insurer["version"], "报价摘要与冻结公司资料不符")
    current_history = next(h for h in view["quote_history"] if h["quote"]["id"] == q["id"])
    require(current_history["review"] is None and current_history["authorized"] is False, "新版借用了旧版核价或授权")
    await expect(e.page.locator("#main")).to_contain_text("当前报价第 " + str(revision) + " 版")
    await expect(e.page.locator("#main")).to_contain_text("尚无客户本版授权")
    return q, {"quote": q, "native": meta, "original_task": transfer, "fresh_approval_and_consent_required": True}


async def fact_action(e, context, credentials, fixture, key, cv, action, *, role, token, expected=None, fields=None, extra="", account=None, renewal=None, invalidated=()):
    actor, current, transfer = await responsible(e, context, credentials, fixture, role, key, action, cv)
    category = "receipt" if action in FINANCIAL else "authorization"
    proof = await upload(e, fixture, key, actor, category, "insurance-" + action + "-" + token,
                         "合成保险本人明确事实：" + action + "；每个办理事实独立文件，不冒真实保险、银行或签字")
    await original_form(e, action, extra=extra)
    for field, value in (fields or {}).items():
        selector = f'#modal [name="{field}"]'
        if field in {"decision", "outcome"}:
            await select_value(e, selector, value, "选择本人核对的原保险结果")
        else:
            await e.fill(selector, value, "填写本人实际原保险 " + field)
    if account is not None:
        await account_choice(e, account)
    await proof_choice(e, proof)
    expected = {"evidence_id": proof["file"]["id"], **(expected or {})}
    if account is not None:
        expected["account_id"] = account["id"]
    view, meta = await command(e, fixture, actor, key, action, cv, expected=expected, account=account, renewal=renewal, invalidated=invalidated)
    return view, {"native": meta, "proof": proof, "original_task": transfer, "current_quote_id": current["quote"]["id"]}


async def approved_authorized(e, context, credentials, fixture, key, cv, q, token, *, renewal=None):
    approved, review = await fact_action(e, context, credentials, fixture, key, cv, "review", role="manager", token=token,
        fields={"decision": "批准", "reason": "本人独立核对本版保险公司、险种与保期后批准"}, expected={"decision": "approved"})
    raw_review = e.db.rows("SELECT * FROM insurance_reviews WHERE quote_id=?", (q["id"],))
    require(len(raw_review) == 1 and raw_review[0]["actor_id"] != q["actor_id"] and raw_review[0]["decision"] == "approved", "保险核价没有原独立批准")
    authorized, consent = await fact_action(e, context, credentials, fixture, key, cv, "authorize", role="service", token=token,
        expected={"quote_id": q["id"], "digest": q["digest"]}, renewal=renewal)
    raw_consent = e.db.rows("SELECT * FROM insurance_consents WHERE quote_id=?", (q["id"],))
    require(len(raw_consent) == 1 and raw_consent[0]["digest"] == q["digest"] and raw_consent[0]["evidence_id"] == consent["proof"]["file"]["id"], "保险授权未绑定同版原摘要及独立原件")
    history = next(h for h in authorized["quote_history"] if h["quote"]["id"] == q["id"])
    require(history["authorized"] and history["review"]["decision"] == "approved", "原页面/API核价授权未一致")
    await expect(e.page.locator("#main")).to_contain_text("客户已授权本版")
    return {"review": review, "review_fact": raw_review[0], "consent": consent, "consent_fact": raw_consent[0]}


async def external_results(e, context, credentials, fixture, key, cv, q, token, *, renewal=None, all_outcomes=True):
    outcomes = [("need_documents", "需要补件"), ("rejected", "拒绝投保"), ("issued", "实际出保")] if all_outcomes else [("issued", "实际出保")]
    evidence, issued = [], None
    for i, (outcome, label) in enumerate(outcomes, 1):
        reference = f"SYN-INS-SUB-{token}-{i}"
        submitted, native_submit = await fact_action(e, context, credentials, fixture, key, cv, "submit", role="service", token=token + str(i),
            fields={"external_reference": reference, "business_date": today().isoformat()}, expected={"external_reference": reference, "business_date": today().isoformat()}, renewal=renewal)
        submission = submitted["submissions"][-1]
        require(submission["quote_id"] == q["id"] and submission["external_reference"] == reference and not any(r["submission_id"] == submission["id"] for r in submitted["results"]), "提交未绑定本版或结果被提前预置")
        old_observations = e.db.rows("SELECT * FROM care_vehicle_observations WHERE vehicle_id=? ORDER BY id", (cv["id"],))
        number = "SYN-POLICY-" + token if outcome == "issued" else ""
        result_text = "合成保险公司实际结果：" + label + "；本次原提交 " + reference
        result_view, native_result = await fact_action(e, context, credentials, fixture, key, cv, "result", role="service", token=token + str(i),
            fields={"outcome": label, "policy_number": number, "result": result_text, "business_date": today().isoformat()},
            expected={"submission_id": submission["id"], "outcome": outcome, "policy_number": number, "result": result_text, "business_date": today().isoformat()})
        result = next(r for r in rows(e, "insurance_results", key) if r["submission_id"] == submission["id"])
        require(result["outcome"] == outcome and result["policy_number"] == (number or None) and result["evidence_id"] == native_result["proof"]["file"]["id"], "保险实际结果/原号/原件不一致")
        observations = e.db.rows("SELECT * FROM care_vehicle_observations WHERE vehicle_id=? ORDER BY id", (cv["id"],))
        if outcome == "issued":
            issued = result
            observation = one(e, "care_vehicle_observations", result["observation_id"])
            require(observations[:-1] == old_observations and len(observations) == len(old_observations) + 1 and observations[-1] == observation
                    and observation["kind"] == "insurance" and observation["vehicle_id"] == cv["id"] and observation["valid_until"] == q["end_date"]
                    and observation["observed_date"] == result["business_date"] and observation["actor_id"] == result["actor_id"] and observation["evidence_id"] == result["evidence_id"], "出保未唯一追加同CV有效保险原来源")
            await expect(e.page.locator("#main")).to_contain_text(number)
        else:
            require(result["observation_id"] is None and observations == old_observations and result_view["summary"]["issued"] is False, "补件/拒绝冒作出保或新增保期")
        await expect(e.page.locator("#main")).to_contain_text({"need_documents": "保险公司要求补件", "rejected": "保险公司拒绝", "issued": "已实际出保"}[outcome])
        evidence.append({"submission": submission, "submission_native": native_submit, "result": result, "result_native": native_result})
    return issued, evidence


async def money_action(e, context, credentials, fixture, key, cv, account, action, cents, token, *, extra="", expected=None):
    fields = {"amount": fen_text(cents), "business_date": today().isoformat()}
    reference = "SYN-INS-" + action.upper() + "-" + token
    direct = action == "direct_paid"
    fields["external_reference" if direct else "reference"] = reference
    expected = {"amount_cents": cents, "business_date": today().isoformat(), "external_reference" if direct else "reference": reference, **(expected or {})}
    view, native = await fact_action(e, context, credentials, fixture, key, cv, action, role="finance", token=token, fields=fields,
        extra=extra, account=None if direct else account, expected=expected)
    if direct:
        entries = rows(e, "insurance_direct_entries", key)
        require(len(entries) == 1 and entries[0]["purpose"] == "paid" and entries[0]["amount_cents"] == cents and entries[0]["original_id"] is None
                and not rows(e, "insurance_tenders", key) and not rows(e, "flow_payment_links", key) and not rows(e, "insurance_pass_entries", key), "客户直付产生门店保费资金或缺原证明")
        native["direct_entry"] = entries[0]
        return view, native
    links = native["native"]["native"]["source_guard"]["appended_ids"]["cash_entries"]
    require(len(links) == 1, "单笔原保险资金未唯一产生现金")
    cash = one(e, "cash_entries", links[0])
    direction, category = {
        "receive": ("in", "workflow_ins_premium"), "disburse": ("out", "workflow_ins_disburse"),
        "insurer_return": ("in", "workflow_ins_insurer_return"), "refund": ("out", "workflow_ins_premium_refund"),
        "commission_receive": ("in", "workflow_ins_commission_in"), "commission_return": ("out", "workflow_ins_commission_out"),
    }[action]
    require(cash["amount_cents"] == cents and cash["direction"] == direction and cash["category"] == category and cash["account"] == account["name"]
            and cash["voucher_no"] == reference and cash["approval_state"] == "approved" and cash["created_by"] == e.manifest["users"][fixture["finance_key"]]["id"], "保险现金原金额/分类/账号/本人不匹配")
    native["cash"] = cash
    return view, native


async def commission(e, context, credentials, fixture, key, cv, target, token):
    proposed, native = await fact_action(e, context, credentials, fixture, key, cv, "commission", role="finance", token=token,
        fields={"target": fen_text(target), "reason": "保险公司合成实际结算累计应得" + fen_text(target) + "元，区别于预计佣金"}, expected={"target_cents": target})
    fact = rows(e, "insurance_commissions", key)[-1]
    require(fact["target_cents"] == target and proposed["commissions"][-1]["id"] == fact["id"] and proposed["commissions"][-1]["review"] is None, "实际佣金未经批准被提前生效")
    view, review = await fact_action(e, context, credentials, fixture, key, cv, "commission_review", role="manager", token=token,
        fields={"decision": "批准", "reason": "本人独立核对保险公司实际佣金结算和原凭据", "business_date": today().isoformat()},
        extra=f'[data-confirmation="{fact["id"]}"]', expected={"confirmation_id": fact["id"], "decision": "approved", "business_date": today().isoformat()})
    reviewed = e.db.rows("SELECT * FROM insurance_commission_reviews WHERE confirmation_id=?", (fact["id"],))
    require(len(reviewed) == 1 and reviewed[0]["actor_id"] != fact["actor_id"] and reviewed[0]["decision"] == "approved" and view["summary"]["confirmed_commission_cents"] == target, "实际佣金未独立确认同版累计数")
    return fact, view, {"confirmation": fact, "proposed": native, "review": review, "review_fact": reviewed[0]}


async def native_write(e, fixture, path, method, rendered, guard, *, status=200, selector='#modal form button[type="submit"]'):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == rendered) as ready:
        async with e.page.expect_response(lambda r: r.request.method == method and urlsplit(r.url).path == path) as pending:
            await e.click(selector, "本人确认原提醒或客户服务步骤")
        response = await pending.value
        body = await response.json()
        require(response.status == status, f"原提醒提交HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    read = await ready.value
    view = await read.json()
    require(read.status == 200, "原提醒提交后读取失败")
    request, headers = response.request.post_data_json, await response.request.all_headers()
    require(isinstance(request["request_id"], str) and len(request["request_id"]) >= 16 and headers.get("cookie") and headers.get("x-csrf-token")
            and headers.get("x-store-id") == str(fixture["store_id"]) and urlsplit(response.url).netloc == urlsplit(e.manifest["origin"]).netloc, "原提醒请求没有同源本人Cookie/CSRF/当前店/原请求号")
    meta = {"path": path, "method": method, "status": response.status, "render_get_path": rendered, "render_get_status": read.status,
            "native_ui": True, "cookie_present": True, "csrf_present": True, "submitted_version": request.get("version"),
            "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest(), "source_guard": guard.finish()}
    await expect(e.page.locator("#modal")).not_to_be_visible()
    if rendered == CARE + "/reminders/rules":
        await expect(e.page.locator("#main h1")).to_have_text("车辆提醒与续保提取")
    elif rendered.startswith(CARE + "/cases/"):
        await expect(e.page.locator("#main .pagehead")).to_contain_text(view["number"])
    e.observe("insurance_care_original_response", meta)
    return body, view, request, meta


async def reminder_page(e, context, credentials, fixture, role):
    path = CARE + "/reminders/rules"
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], "customer-reminders", fixture["store_id"])
    response = await pending.value
    data = await response.json()
    require(response.status == 200, "原提醒规则读取失败")
    await expect(e.page.locator("#main h1")).to_have_text("车辆提醒与续保提取")
    return actor, data


async def reminder_rule(e, context, credentials, fixture, cv, token, *, lead, rule=None):
    manager, data = await reminder_page(e, context, credentials, fixture, "manager")
    if rule is None:
        require(not any(r["kind"] == "renewal" for r in data["items"]), "已有未知续保规则，不能覆盖")
        await select_value(e, '#main [name="care_rule_kind"]', "renewal", "选择原续保规则类型")
        await e.click('#main [data-act="care-rule-new"]', "主管建立明确本次续保规则")
    else:
        require(next(r for r in data["items"] if r["id"] == rule["id"])["version"] == rule["version"], "提醒规则当前CAS未读取")
        await e.click(f'#main [data-act="care-rule-edit"][data-id="{rule["id"]}"]', "主管按原版本修改本次提前量")
    name = "合成短期保险到期提醒-" + token
    await e.fill('#modal [name="name"]', name, "明确本次原提醒名称")
    await e.fill('#modal [name="lead_days"]', str(lead), "设置真实提前天数边界")
    service = e.manifest["users"][fixture["service_key"]]
    await select_value(e, '#modal [name="assignee_id"]', service["id"], "明确本店原服务接手员工")
    e.action("check", "启用本次明确原规则")
    await e.page.locator('#modal [name="active"]').check()
    update = {"care_reminder_rules": {rule["id"]: {"name", "lead_days", "assignee_id", "active", "approved_by", "version", "updated_at"}}} if rule else {}
    guard = Guard(e, "renewal_rule_save", manager, fixture["store_id"], append={"care_receipts", "audit_logs"} | (set() if rule else {"care_reminder_rules"}), update=update, vehicle=cv["id"])
    path = CARE + "/reminders/rules" + ("/" + str(rule["id"]) if rule else "")
    body, view, request, meta = await native_write(e, fixture, path, "PUT" if rule else "POST", CARE + "/reminders/rules", guard, status=200 if rule else 201)
    current = one(e, "care_reminder_rules", body["rule"]["id"])
    expected = {"name": name, "kind": "renewal", "interval_days": 0, "interval_km": 0, "lead_days": lead, "lead_km": 0, "assignee_id": service["id"], "active": True}
    require(request["values"] == expected and all(current[k] == v for k, v in expected.items()) and current["approved_by"] == manager["id"], "续保原规则字段/零周期/本店经办不符")
    if rule:
        require(request["version"] == rule["version"] and current["version"] > rule["version"], "原规则CAS未推进")
    visible = next(r for r in view["items"] if r["id"] == current["id"])
    require(visible["version"] == current["version"] and visible["lead_days"] == lead, "原规则UI/API/DB边界不一致")
    receipt = e.db.rows("SELECT * FROM care_receipts WHERE request_key=?", (request["request_id"],))
    require(len(receipt) == 1 and receipt[0]["actor_id"] == manager["id"], "原规则没有唯一主管回执")
    return current, {"native": meta, "rule": current, "receipt_id": receipt[0]["id"]}


async def generate(e, context, credentials, fixture, cv, *, expected_created):
    service, _ = await reminder_page(e, context, credentials, fixture, "service")
    active = e.db.rows("SELECT id FROM care_customer_vehicles WHERE store_id=? AND active=1 ORDER BY id", (fixture["store_id"],))
    require(len(active) <= 500, "原提醒车辆范围超过明确500上限")
    old_cases = e.db.rows("SELECT * FROM care_cases WHERE vehicle_id=? AND subtype='renewal' ORDER BY case_id", (cv["id"],))
    append = {"observation_correction_receipts"}
    if expected_created:
        append |= COMMON | {"flow_cases", "care_cases", "care_records", "observation_reminder_bases", "business_entity_case_contexts"}
    guard = Guard(e, "renewal_generate", service, fixture["store_id"], append=append,
        update={"care_customer_vehicles": {r["id"]: VERSION_COLUMNS for r in active}}, vehicle=cv["id"], new_kind="customer_care" if expected_created else None)
    body, _, request, meta = await native_write(e, fixture, CARE + "/reminders/generate", "POST", CARE + "/reminders/rules", guard,
        selector='#main [data-act="care-generate"]')
    require(set(request) == {"request_id"} and body["as_of"] == today().isoformat() and body["automatic"] is False and not body["skipped"]
            and len(body["created"]) == expected_created, "原生成数/时间/自动与岗位跳过不符，不能隐藏其它实际来源")
    receipt = e.db.rows("SELECT * FROM observation_correction_receipts WHERE request_key=?", (request["request_id"],))
    require(len(receipt) == 1 and receipt[0]["actor_id"] == service["id"] and json.loads(receipt[0]["result"]) == body, "原生成缺唯一本人有效周期回执")
    current = e.db.rows("SELECT * FROM care_cases WHERE vehicle_id=? AND subtype='renewal' ORDER BY case_id", (cv["id"],))
    require(len(current) == len(old_cases) + expected_created and all(r in current for r in old_cases), "原周期重复或覆盖旧续保事实")
    return body, {"native": meta, "body": body, "current_renewal_case_ids": [r["case_id"] for r in current], "receipt_id": receipt[0]["id"], "limited_active_vehicle_ids": [r["id"] for r in active]}


async def care_action(e, context, credentials, fixture, key, cv, action, fields=None):
    manager, current = await read_as(e, context, credentials, fixture, "manager", key, care=True)
    require(action in current["actions"], "当前原续保单没有可办动作：" + action)
    await e.click(f'#main [data-act="care-action"][data-action="{action}"]', "本人办理原续保 " + action)
    for name, value in (fields or {}).items():
        selector = f'#modal [name="{name}"]'
        if name in {"assignee_id", "channel", "contact_result", "result"}:
            await select_value(e, selector, value, "选择明确原续保 " + name)
        else:
            await e.fill(selector, value, "记录本人实际续保 " + name)
    before, records, events = case(e, key), rows(e, "care_records", key), rows(e, "flow_events", key)
    case_fields = VERSION_COLUMNS | {"start": {"state"}, "followup": {"due_date"}, "handoff": {"owner_id", "due_date"}, "close": {"state", "completed_date"}}[action]
    task_fields = VERSION_COLUMNS | {"start": set(), "followup": {"due_date"}, "handoff": {"assignee_id", "due_date"}, "close": {"status", "done_by", "done_at"}}[action]
    changes = {"flow_cases": {key: case_fields}, "flow_tasks": {r["id"]: task_fields for r in rows(e, "flow_tasks", key)}, "care_customer_vehicles": {cv["id"]: VERSION_COLUMNS}}
    if action == "close":
        changes["care_cases"] = {key: {"result"}}
    guard = Guard(e, "renewal_care_" + action, manager, fixture["store_id"], append={"care_records", "care_receipts", "flow_events", "audit_logs"},
        update=changes, cases={key}, vehicle=cv["id"])
    body, view, request, meta = await native_write(e, fixture, CARE + f"/cases/{key}/actions/{action}", "POST", CARE + "/cases/" + str(key), guard)
    require(request["version"] == before["version"] and body["case"]["id"] == view["id"] == key and body["case"]["version"] == case(e, key)["version"] > before["version"], "原续保提交CAS或身份不符")
    for field, value in (fields or {}).items():
        require(request["values"][field] == value, "原续保提交字段不符：" + field)
    current_records, current_events = rows(e, "care_records", key), rows(e, "flow_events", key)
    require(current_records[:len(records)] == records and len(current_records) == len(records) + 1 and current_records[-1]["action"] == action and current_records[-1]["actor_id"] == manager["id"], "原续保记录未唯一追加本人实际动作")
    require(current_events[:len(events)] == events and len(current_events) == len(events) + 1 and current_events[-1]["action"] == "care_" + action and current_events[-1]["actor_id"] == manager["id"], "原续保事件未唯一追加")
    receipt = e.db.rows("SELECT * FROM care_receipts WHERE request_key=?", (request["request_id"],))
    require(len(receipt) == 1 and receipt[0]["actor_id"] == manager["id"], "原续保缺同单本人回执")
    return view, {"native": meta, "request_values": request["values"], "record": decoded(current_records[-1]), "event": current_events[-1], "receipt_id": receipt[0]["id"]}


async def old_source_refusal(e, context, credentials, fixture, key):
    actor, view = await read_as(e, context, credentials, fixture, "manager", key, care=True)
    require(view["state"] == "working" and view["reminder_basis"]["status"] == "effective" and "close" in view["actions"], "负向准入不是有效且在办原续保")
    await e.click('#main [data-act="care-action"][data-action="close"]', "实际尝试仅凭旧保单标记续保完成")
    await select_value(e, '#modal [name="result"]', "renewed", "明确选择原续保已完成")
    await e.fill('#modal [name="note"]', "已电话核对，但尚无真正新保单，须由原来源守卫拒绝", "记录此次原负向结案依据")
    before = e.business_snapshot("before_renewed_old_source_refusal")
    path = CARE + f"/cases/{key}/actions/close"
    async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
        await e.click('#modal form button[type="submit"]', "提交原表单并核对旧源拒绝")
    response = await pending.value
    body = await response.json()
    message = "没有新的有效保险来源，不能用失效或被纠正的旧保期标记续保完成"
    require(response.status == 409 and body.get("detail") == message, "原旧保险来源未按真实renewed守卫拒绝")
    request, headers = response.request.post_data_json, await response.request.all_headers()
    require(request["version"] == view["version"] and request["values"]["result"] == "renewed" and headers.get("cookie") and headers.get("x-csrf-token") and headers.get("x-store-id") == str(fixture["store_id"]), "原旧源拒绝没有本人/CAS/店域")
    e.business_unchanged(before, "after_renewed_old_source_refusal")
    await expect(e.page.locator("#modal .formerror")).to_contain_text(message)
    await e.snapshot("renewal-old-source-409")
    await expect(e.page.locator("#modal form")).not_to_have_attribute("aria-busy", "true")
    await e.click('#modal .modalhead [data-act="close"]', "关闭被拒绝的原结案表单")
    await expect(e.page.locator("#modal .wfx-discard")).to_be_visible()
    await e.click('#modal [data-wfx-discard]', "明确放弃已拒绝的旧源结案填写")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    e.business_unchanged(before, "after_renewal_refusal_discard")
    return {"path": path, "status": 409, "detail": message, "native_ui": True, "actor_id": actor["id"], "business_unchanged": True,
            "submitted_version": request["version"], "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest(), "no_replay": True}


async def vehicle_sources(e, context, credentials, fixture, cv, *, effective_ids, inactive_ids=()):
    path = CARE + "/vehicles/" + str(cv["id"])
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        await login_as(e, context, credentials, fixture["service_key"], "customer-vehicles/" + str(cv["id"]), fixture["store_id"])
    response = await pending.value
    data = await response.json()
    require(response.status == 200 and data["vehicle"]["id"] == cv["id"] and data["vehicle"]["vin"] == cv["vin"], "原客户车辆来源读取错配")
    await expect(e.page.locator("#main h1")).to_contain_text(cv["plate"] or cv["vin"])
    before = e.business_snapshot("before_insurance_effective_source_view")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as refreshed:
        await e.page.reload()
    refreshed_response = await refreshed.value
    data = await refreshed_response.json()
    require(refreshed_response.status == 200 and data["vehicle"]["id"] == cv["id"] and data["vehicle"]["version"] == one(e, "care_customer_vehicles", cv["id"])["version"], "原客户车辆刷新没有同ID当前版本")
    await expect(e.page.locator("#main h1")).to_contain_text(cv["plate"] or cv["vin"])
    source = {r["id"]: r for r in data["effective_observations"]}
    for key in effective_ids:
        require(source[key]["active"] and source[key]["kind"] == "insurance" and source[key]["odometer_measured"] is False and source[key]["odometer_km"] is None, "有效保险被误当实测里程或有效性错误")
        original = one(e, "care_vehicle_observations", key)
        require(source[key]["valid_until"] == original["valid_until"] and source[key]["observed_date"] == original["observed_date"], "原保期有效投影不一致")
        await expect(e.page.locator("#main")).to_contain_text(original["source_reference"])
    for key in inactive_ids:
        require(source[key]["active"] is False and one(e, "care_vehicle_observations", key)["kind"] == "insurance", "实际撤保旧来源没有明确失效")
    if inactive_ids:
        await expect(e.page.locator("#main")).to_contain_text("原观察已失效，不再驱动提醒；历史记录保留。")
    await expect(e.page.locator("#main")).to_contain_text("本条没有独立实测里程")
    e.business_unchanged(before, "after_insurance_effective_source_view")
    return {"path": path, "status": 200, "effective_insurance": [source[k] for k in effective_ids], "inactive_insurance": [source[k] for k in inactive_ids], "native_ui": True, "no_observation_overwrite": True}


async def reminder_work(e, context, credentials, fixture, key):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/tasks") as initial:
        service = await login_as(e, context, credentials, fixture["service_key"], "work", fixture["store_id"])
    require((await initial.value).status == 200, "原我的工作读取失败")
    await expect(e.page.locator("#main h1")).to_have_text("我的工作")
    before = e.business_snapshot("before_original_insurance_due_work")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/tasks" and parse_qs(urlsplit(r.url).query).get("due") == ["today"]) as filtered:
        await e.click('[data-mux-due="today"]', "筛选原今日到期提醒")
    require((await filtered.value).status == 200, "原今日提醒筛选失败")
    current = case(e, key)
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/tasks" and parse_qs(urlsplit(r.url).query).get("q") == [current["number"]]) as pending:
        await e.fill('#filters [name="q"]', current["number"], "查找明确本轮续保提醒")
    response = await pending.value
    data = await response.json()
    task = rows(e, "flow_tasks", key)
    require(response.status == 200 and len(data["items"]) == len(task) == 1, "今日续保提醒不是非空唯一同Task")
    item, task = data["items"][0], task[0]
    for field in ("id", "case_id", "key", "title", "assignee_id", "due_date", "status", "version"):
        require(item[field] == task[field], "原续保提醒API/DB不一致：" + field)
    require(task["assignee_id"] == service["id"] and task["due_date"] == today().isoformat() and task["key"] == "care_handle" and item["entry_route"] == "customer-service/" + str(key), "原提醒串本人/日期/办理入口")
    row = e.page.locator("#main .work-table tbody tr")
    await expect(row).to_have_count(1)
    for text in (current["number"], task["title"], item["assignee_name"], task["due_date"]):
        await expect(row).to_contain_text(text)
    await e.snapshot("insurance-renewal-today-reminder")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == CARE + "/cases/" + str(key)) as opened:
        await e.click(f'#main .work-table [data-act="open"][data-route="customer-service/{key}"]', "从今日提醒打开同原续保任务")
    loaded = await opened.value
    view = await loaded.json()
    require(loaded.status == 200 and view["id"] == key and view["assignee_id"] == service["id"] and "start" in view["actions"], "原提醒不能到本人同单办理")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(current["number"])
    e.business_unchanged(before, "after_original_insurance_due_work")
    return {"task": task, "original_get": {"path": "/api/flow/tasks", "status": 200, "item": item}, "opened_get": {"path": CARE + "/cases/" + str(key), "status": 200}, "native_ui": True, "business_unchanged": True}


async def termination_and_refunds(e, context, credentials, fixture, key, cv, account, tender, pass_entry, comm_payment, issued, renewal, token):
    actor, _, transfer = await responsible(e, context, credentials, fixture, "service", key, "termination", cv)
    proof = await upload(e, fixture, key, actor, "authorization", "insurance-termination-" + token, "合成保险公司已经实际退保且保留保费零；原客户220元全部可退")
    await original_form(e, "termination")
    await e.fill('#modal [name="retained"]', "0.00", "填写原保险公司实际零保留额")
    await e.fill(f'#modal [data-insurance-return="{tender["id"]}"] [name="amount"]', "220.00", "明确退回本笔原客户款")
    await select_value(e, '#modal [name="result"]', "terminated", "选择原保单实际退保结果")
    await e.fill('#modal [name="reason"]', "合成保险公司退保结果已核对，原220元和佣金分别结清，不撤销新续保", "填写原保险退保原因")
    await select_value(e, '#modal [name="evidence_id"]', proof["file"]["id"], "选择本次原退保事实文件")
    view, proposed = await command(e, fixture, actor, key, "termination", cv,
        expected={"retained_cents": 0, "external_result": "terminated", "returns": [{"tender_id": tender["id"], "amount_cents": 22000}], "evidence_id": proof["file"]["id"]})
    plan = decoded(rows(e, "insurance_terminations", key)[-1])
    require(plan["digest"] == digest("insurance_termination", {"quote_id": plan["quote_id"], **proposed["request_values"]}) and view["summary"]["terminated"] is False, "退保申请冒作实际生效或方案摘要错误")
    _, review = await fact_action(e, context, credentials, fixture, key, cv, "termination_review", role="manager", token=token,
        fields={"decision": "批准", "reason": "本人独立核对保险公司实际退保与原款分配"}, extra=f'[data-plan="{plan["id"]}"]', expected={"plan_id": plan["id"], "decision": "approved"})
    _, consent = await fact_action(e, context, credentials, fixture, key, cv, "termination_consent", role="service", token=token,
        extra=f'[data-plan="{plan["id"]}"]', expected={"plan_id": plan["id"], "digest": plan["digest"]})
    affected = e.db.rows("SELECT c.case_id FROM care_cases c LEFT JOIN observation_reminder_bases b ON b.case_id=c.case_id WHERE c.vehicle_id=? AND c.subtype='renewal' AND c.rule_id IS NOT NULL AND (b.case_id IS NULL OR b.baseline_id=? OR b.current_id=?) ORDER BY c.case_id", (cv["id"], issued["observation_id"], issued["observation_id"]))
    require([r["case_id"] for r in affected] == [renewal], "原撤保涉及其它未知提醒来源，须明确其合法原事实")
    old_case, old_tasks, old_records = case(e, renewal), rows(e, "flow_tasks", renewal), rows(e, "care_records", renewal)
    old_basis = one(e, "observation_reminder_bases", renewal, "case_id")
    require(old_case["state"] == "completed" and all(t["status"] == "done" for t in old_tasks), "须先真正续保完成再验证旧基准失效")
    applied, application = await fact_action(e, context, credentials, fixture, key, cv, "termination_apply", role="finance", token=token,
        extra=f'[data-plan="{plan["id"]}"]', expected={"plan_id": plan["id"]}, invalidated={renewal})
    invalid = e.db.rows("SELECT * FROM observation_insurance_invalidations WHERE source_case_id=?", (key,))
    reminder_invalid = rows(e, "observation_reminder_invalidations", renewal)
    require(applied["summary"]["terminated"] and len(invalid) == len(reminder_invalid) == 1 and invalid[0]["observation_id"] == issued["observation_id"]
            and invalid[0]["plan_id"] == plan["id"] and reminder_invalid[0]["insurance_invalidation_id"] == invalid[0]["id"] and reminder_invalid[0]["closed_open_task"] == 0,
            "实际撤保没有唯一同源保险/提醒失效记录")
    require(case(e, renewal) == old_case and rows(e, "flow_tasks", renewal) == old_tasks and one(e, "observation_reminder_bases", renewal, "case_id") == old_basis
            and rows(e, "care_records", renewal)[:-1] == old_records and len(rows(e, "care_records", renewal)) == len(old_records) + 1, "旧已完成续保或原基准被撤保改写")
    invalid_note = decoded(rows(e, "care_records", renewal)[-1])
    require(invalid_note["action"] == "followup" and invalid_note["details"]["closed_open_task"] is False and invalid_note["details"]["basis_invalidation"] == "insurance:" + str(invalid[0]["id"]), "已结案提醒失效未追加保留历史说明")
    _, recovered = await money_action(e, context, credentials, fixture, key, cv, account, "insurer_return", 22000, token,
        extra=f'[data-original="{pass_entry["id"]}"]', expected={"original_id": pass_entry["id"]})
    returned_pass = rows(e, "insurance_pass_entries", key)[-1]
    require(returned_pass["purpose"] == "insurer_return" and returned_pass["original_id"] == pass_entry["id"] and returned_pass["tender_id"] == tender["id"] and returned_pass["account_id"] == account["id"], "保险公司追回未沿本笔原代缴和账户")
    _, refund = await money_action(e, context, credentials, fixture, key, cv, account, "refund", 22000, token,
        extra=f'[data-plan="{plan["id"]}"][data-tender="{tender["id"]}"]', expected={"plan_id": plan["id"], "tender_id": tender["id"]})
    reversed_tender = rows(e, "insurance_tenders", key)[-1]
    reversed_link = one(e, "flow_payment_links", reversed_tender["payment_link_id"])
    require(reversed_tender["original_id"] == tender["id"] and reversed_tender["amount_cents"] == -22000 and reversed_link["original_id"] == tender["payment_link_id"]
            and reversed_link["account_id"] == account["id"] and reversed_link["direction"] == "out", "客户退款没有负原Tender及原客户付款账户关联")
    target, _, target_native = await commission(e, context, credentials, fixture, key, cv, 0, token + "RETURN")
    final, comm_return = await money_action(e, context, credentials, fixture, key, cv, account, "commission_return", 1200, token,
        extra=f'[data-confirmation="{target["id"]}"][data-original="{comm_payment["id"]}"]', expected={"confirmation_id": target["id"], "original_id": comm_payment["id"]})
    reverse_comm = rows(e, "insurance_commission_payments", key)[-1]
    require(reverse_comm["direction"] == "out" and reverse_comm["original_id"] == comm_payment["id"] and reverse_comm["amount_cents"] == 1200 and reverse_comm["account_id"] == account["id"], "佣金返还没有独立原佣金/账户来源")
    for field in ("premium_cents", "customer_paid_cents", "customer_due_cents", "customer_refund_cents", "insurer_paid_cents", "insurer_due_cents", "insurer_return_due_cents", "held_principal_cents", "confirmed_commission_cents", "actual_commission_cents", "commission_due_cents", "commission_return_due_cents"):
        require(final["summary"][field] == 0, "原保险返还终点未结清：" + field)
    require(case(e, key)["state"] == "completed" and all(t["status"] != "open" for t in rows(e, "flow_tasks", key)) and final["summary"]["issued"], "旧保险原出保历史丢失或返还任务未完结")
    return {"plan": plan, "proposal": {"native": proposed, "proof": proof, "original_task": transfer}, "review": review, "consent": consent, "application": application,
            "insurance_basis_invalidation": invalid[0], "reminder_invalidation": reminder_invalid[0], "completed_care_unchanged": True, "appended_invalidation_note": invalid_note,
            "insurer_return": {"native": recovered, "pass_entry": returned_pass}, "customer_refund": {"native": refund, "tender": reversed_tender, "link": reversed_link},
            "commission_target_zero": target_native, "commission_return": {"native": comm_return, "payment": reverse_comm}, "final_summary": final["summary"], "case": case(e, key)}


async def insurance_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        cp.start("HK-013")
        fixture, customer, cv, insurer, account = source_facts(e, cp)
        token = uuid.uuid4().hex[:12].upper()
        first, created = await create_order(e, context, credentials, fixture, customer, cv)
        cp.note(original_create=created)

        cp.start("HK-014")
        q1, price1 = await quote(e, context, credentials, fixture, first, cv, insurer, token, revision=1, premium=20000, expected_commission=1000, days=10, mode="store_collect")
        auth1 = await approved_authorized(e, context, credentials, fixture, first, cv, q1, token + "V1")
        q2, price2 = await quote(e, context, credentials, fixture, first, cv, insurer, token, revision=2, premium=22000, expected_commission=1500, days=10, mode="store_collect")
        cancel = e.db.rows("SELECT * FROM insurance_quote_cancellations WHERE quote_id=?", (q1["id"],))
        require(len(cancel) == 1 and decoded(one(e, "insurance_quotes", q1["id"])) == q1 and q2["id"] != q1["id"], "报价更改没有保留旧版本和唯一原撤回")
        auth2 = await approved_authorized(e, context, credentials, fixture, first, cv, q2, token + "V2")
        service, current = await read_as(e, context, credentials, fixture, "service", first)
        require(len(current["quote_history"]) == 2 and current["quote_history"][0]["cancelled"] and all(h["authorized"] and h["review"]["decision"] == "approved" for h in current["quote_history"]), "两版独立核价/授权历史不完整")
        history = e.page.locator('#main .panel').filter(has=e.page.get_by_role("heading", name="历史报价", exact=True))
        await expect(history).to_have_count(1)
        e.action("click", "展开保险两版原报价历史")
        await history.locator("details > summary").click()
        await expect(history).to_contain_text("第 1 版")
        await expect(history).to_contain_text("第 2 版")
        await expect(history).to_contain_text("已撤回")
        await cp.passed(first_version={"price": price1, "independent_approval_and_consent": auth1}, second_version={"price": price2, "independent_approval_and_consent": auth2},
                        cancellation=cancel[0], original_history=current["quote_history"], old_quote_unchanged=True)

        cp.start("HK-013")
        issued, external = await external_results(e, context, credentials, fixture, first, cv, q2, token)
        cp.note(actual_external_outcomes=external, issued_result=issued)
        source_read = await vehicle_sources(e, context, credentials, fixture, cv, effective_ids={issued["observation_id"]})

        cp.start("HK-077")
        _, received = await money_action(e, context, credentials, fixture, first, cv, account, "receive", 22000, token)
        tenders = rows(e, "insurance_tenders", first)
        require(len(tenders) == 1 and tenders[0]["amount_cents"] == 22000 and tenders[0]["original_id"] is None and tenders[0]["credit_link_id"] is None, "原保费没有唯一真实正向现金Tender")
        tender = tenders[0]
        payment = one(e, "flow_payment_links", tender["payment_link_id"])
        require(payment["cash_id"] == received["cash"]["id"] and payment["amount_cents"] == 22000 and payment["account_id"] == account["id"] and payment["direction"] == "in", "保费原款PaymentLink/现金/账户错配")
        _, disbursed = await money_action(e, context, credentials, fixture, first, cv, account, "disburse", 22000, token,
            extra=f'[data-tender="{tender["id"]}"]', expected={"tender_id": tender["id"]})
        pass_rows = rows(e, "insurance_pass_entries", first)
        require(len(pass_rows) == 1 and pass_rows[0]["purpose"] == "disburse" and pass_rows[0]["tender_id"] == tender["id"] and pass_rows[0]["original_id"] is None
                and pass_rows[0]["cash_id"] == disbursed["cash"]["id"] and pass_rows[0]["account_id"] == account["id"] and pass_rows[0]["amount_cents"] == 22000, "实际代缴没有本笔原款/账户/现金来源")
        pass_entry = pass_rows[0]
        conf, _, commission_confirmed = await commission(e, context, credentials, fixture, first, cv, 1200, token)
        completed, comm_received = await money_action(e, context, credentials, fixture, first, cv, account, "commission_receive", 1200, token,
            extra=f'[data-confirmation="{conf["id"]}"]', expected={"confirmation_id": conf["id"]})
        comm_rows = rows(e, "insurance_commission_payments", first)
        require(len(comm_rows) == 1 and comm_rows[0]["direction"] == "in" and comm_rows[0]["amount_cents"] == 1200 and comm_rows[0]["confirmation_id"] == conf["id"]
                and comm_rows[0]["cash_id"] == comm_received["cash"]["id"] and comm_rows[0]["original_id"] is None and comm_rows[0]["account_id"] == account["id"], "实际佣金没有独立原确认/现金来源")
        comm_payment = comm_rows[0]
        s = completed["summary"]
        require(s["customer_paid_cents"] == s["insurer_paid_cents"] == s["premium_cents"] == 22000 and s["held_principal_cents"] == 0
                and s["expected_commission_cents"] == 1500 and s["confirmed_commission_cents"] == s["actual_commission_cents"] == 1200
                and not any(s[f] for f in ("customer_due_cents", "insurer_due_cents", "commission_due_cents", "commission_return_due_cents")), "保险保费与实际佣金未分别结清")
        require(case(e, first)["state"] == "completed" and all(t["status"] != "open" for t in rows(e, "flow_tasks", first)), "首保险原任务未完整结束")
        money = {"receive": received, "positive_tender": tender, "payment_link": payment, "disburse": disbursed, "pass_entry": pass_entry,
                 "actual_commission_confirmation": commission_confirmed, "commission_receive": comm_received, "commission_payment": comm_payment,
                 "first_complete_summary": s, "principal_net_zero": True, "expected_is_not_actual_income": True}
        cp.note(store_collect_and_commission=money)
        cp.start("HK-013")
        await cp.passed(original_create=created, actual_external_outcomes=external, issued_result=issued, effective_source=source_read,
                        second_quote_id=q2["id"], complete_case=case(e, first), completed_tasks=rows(e, "flow_tasks", first))

        cp.start("HK-113")
        rule9, initial_rule = await reminder_rule(e, context, credentials, fixture, cv, token, lead=9)
        _, before_boundary = await generate(e, context, credentials, fixture, cv, expected_created=0)
        rule10, edited_rule = await reminder_rule(e, context, credentials, fixture, cv, token, lead=10, rule=rule9)
        boundary, at_boundary = await generate(e, context, credentials, fixture, cv, expected_created=1)
        renewal = boundary["created"][0]["case_id"]
        care_row = one(e, "care_cases", renewal, "case_id")
        basis = decoded(one(e, "observation_reminder_bases", renewal, "case_id"))
        require(care_row["subtype"] == "renewal" and care_row["vehicle_id"] == cv["id"] and care_row["baseline_observation_id"] == issued["observation_id"]
                and care_row["rule_id"] == rule10["id"] and care_row["rule_version"] == rule10["version"] and care_row["generation_mode"] == "rule_requested"
                and basis["baseline_id"] == issued["observation_id"] and basis["snapshot"]["rule_version"] == rule10["version"]
                and basis["cycle_key"] == f'{fixture["store_id"]}:{cv["id"]}:renewal:observation:{issued["observation_id"]}', "提取续保任务原CV/保期/版本/周期冻结不完整")
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == CARE + "/cases" and parse_qs(urlsplit(r.url).query).get("subtype") == ["renewal"]) as listing:
            await e.click('#main [data-act="care-renewals"]', "查看本次实际提取的原续保跟进")
        response = await listing.value
        listed = await response.json()
        require(response.status == 200 and any(r["id"] == renewal and r["vehicle_id"] == cv["id"] for r in listed["items"]), "原续保查询没有非空同来源任务")
        await expect(e.page.locator(f'#main [data-route="customer-service/{renewal}"]')).to_have_count(1)
        await cp.passed(initial_rule=initial_rule, edited_rule=edited_rule, before_boundary=before_boundary, at_boundary=at_boundary,
                        generated_care=care_row, frozen_basis=basis, original_list_get={"path": CARE + "/cases", "status": 200, "items": listed["items"]})

        cp.start("HK-116")
        _, duplicate = await generate(e, context, credentials, fixture, cv, expected_created=0)
        work = await reminder_work(e, context, credentials, fixture, renewal)
        cp.note(before_boundary=before_boundary, at_boundary=at_boundary, same_cycle_duplicate_check=duplicate, original_today_work=work)

        cp.start("HK-114")
        original_task = rows(e, "flow_tasks", renewal)[0]
        old_due = case(e, renewal)["due_date"]
        manager = e.manifest["users"][fixture["manager_key"]]
        new_due = (today() + timedelta(days=1)).isoformat()
        handed, handoff = await care_action(e, context, credentials, fixture, renewal, cv, "handoff", {"assignee_id": manager["id"], "due_date": new_due, "reason": "主管接手本次续保回访，保留原期限与责任人"})
        current_task = rows(e, "flow_tasks", renewal)[0]
        require(current_task["id"] == original_task["id"] and current_task["assignee_id"] == case(e, renewal)["owner_id"] == handed["assignee_id"] == manager["id"]
                and current_task["due_date"] == case(e, renewal)["due_date"] == new_due, "续保分派没有同Task/Case负责人日期")
        details = handoff["record"]["details"]
        require(details["from_assignee_id"] == original_task["assignee_id"] and details["previous_due_date"] == old_due and details["was_overdue"] is False, "续保交接丢失原责任人/日期/逾期史")
        _, own_view = await read_as(e, context, credentials, fixture, "manager", renewal, care=True)
        require(own_view["assignee_id"] == manager["id"] and "start" in own_view["actions"], "接手人真实登录后没有同单办理权")
        await cp.passed(original_task=original_task, handoff=handoff, current_task=current_task, new_owner_original_get=own_view)

        cp.start("HK-115")
        _, started = await care_action(e, context, credentials, fixture, renewal, cv, "start")
        require(case(e, renewal)["state"] == "working", "续保接手未进入实际在办")
        followups = []
        for i, note in enumerate(("已电话核对客户原保期，客户要求提供新期险种和报价", "再次电话确认客户本次续保需求，等待保险公司真实新保单"), 1):
            _, followup = await care_action(e, context, credentials, fixture, renewal, cv, "followup", {"channel": "phone", "contact_result": "contacted", "note": note, "next_due_date": (today() + timedelta(days=i)).isoformat()})
            require(followup["record"]["note"] == note and followup["record"]["details"]["channel"] == "phone", "原续保实际沟通未独立留痕")
            await expect(e.page.locator("#main")).to_contain_text(note)
            followups.append(followup)
        refusal = await old_source_refusal(e, context, credentials, fixture, renewal)
        cp.note(start=started, two_actual_followups=followups, old_source_refusal=refusal)
        second, created_second = await create_order(e, context, credentials, fixture, customer, cv, previous=issued, renewal=renewal)
        new_quote, new_price = await quote(e, context, credentials, fixture, second, cv, insurer, token + "NEW", revision=1, premium=30000, expected_commission=0,
                                         days=365, mode="customer_direct", renewal=renewal)
        new_auth = await approved_authorized(e, context, credentials, fixture, second, cv, new_quote, token + "NEW", renewal=renewal)
        new_issued, new_external = await external_results(e, context, credentials, fixture, second, cv, new_quote, token + "NEW", renewal=renewal, all_outcomes=False)
        direct, direct_paid = await money_action(e, context, credentials, fixture, second, cv, account, "direct_paid", 30000, token + "NEW")
        require(direct["summary"]["direct_net_cents"] == 30000 and direct["summary"]["direct_due_cents"] == 0 and direct["summary"]["customer_paid_cents"] == 0, "续保直付原资金定义错配")
        _, new_complete, new_zero_commission = await commission(e, context, credentials, fixture, second, cv, 0, token + "NEW")
        require(case(e, second)["state"] == "completed" and all(t["status"] != "open" for t in rows(e, "flow_tasks", second)), "真正续保保险任务未完整结束")
        new_observation = one(e, "care_vehicle_observations", new_issued["observation_id"])
        require(new_observation["id"] != issued["observation_id"] and new_observation["valid_until"] > q2["end_date"] and new_observation["valid_until"] > today().isoformat(), "新原保期没有延长并有效未来")
        closed, close = await care_action(e, context, credentials, fixture, renewal, cv, "close", {"result": "renewed", "note": "本人已核对同客户VIN真正新的保险原单和未来延长保期，完成续保回访"})
        require(closed["state"] == "completed" and closed["result"] == "renewed" and one(e, "care_cases", renewal, "case_id")["result"] == "renewed"
                and rows(e, "flow_tasks", renewal)[0]["status"] == "done" and rows(e, "flow_tasks", renewal)[0]["done_by"] == manager["id"], "续保真实新源后原结案/Task不一致")
        await cp.passed(start=started, two_actual_followups=followups, old_source_refusal=refusal, new_insurance_create=created_second, new_price=new_price,
                        new_approval_and_consent=new_auth, new_external_result=new_external, direct_payment=direct_paid, zero_actual_commission=new_zero_commission,
                        new_insurance_complete_summary=new_complete["summary"], new_effective_observation=new_observation, original_close=close, completed_care=closed)

        cp.start("HK-077")
        read_before = e.business_snapshot("before_hk077_original_finance_read")
        old_audits = e.db.rows("SELECT * FROM audit_logs ORDER BY id")
        finance, direct_view = await read_as(e, context, credentials, fixture, "finance", second)
        require(finance["id"] == e.manifest["users"][fixture["finance_key"]]["id"] and finance["role"] == "finance"
                and direct_view["state"] == "completed" and direct_view["summary"] == new_complete["summary"],
                "保险收款原页面须由本店财务读取同一完成原单及当前真实资金摘要")
        read_after = e.business_snapshot("after_hk077_original_finance_read")
        changed = {t for t in read_before["tables"].keys() | read_after["tables"].keys()
                   if read_before["tables"].get(t) != read_after["tables"].get(t)}
        require(changed == {"audit_logs"}, "保险原页读取仅允许本人实际登录审计，其他原业务全表不变")
        current_audits = {r["id"]: r for r in e.db.rows("SELECT * FROM audit_logs ORDER BY id")}
        require(all(current_audits.get(r["id"]) == r for r in old_audits), "保险原页读取不可覆盖或删除旧审计")
        old_ids = {r["id"] for r in old_audits}
        login_audits = [r for key, r in current_audits.items() if key not in old_ids]
        require(len(login_audits) == 1 and login_audits[0]["action"] == "login"
                and login_audits[0]["entity_type"] == "users" and login_audits[0]["store_id"] == 0
                and login_audits[0]["actor_id"] == login_audits[0]["entity_id"] == finance["id"],
                "保险原页补充读取须唯一追加同财务本人登录审计")
        await cp.passed(store_collect_and_commission=money, new_customer_direct=direct_paid, direct_original_summary=direct["summary"],
                        direct_creates_no_store_cash=True, direct_source_guard=direct_paid["native"]["native"]["source_guard"],
                        original_finance_read={"actor_id": finance["id"], "store_id": fixture["store_id"], "path": API + "/" + str(second),
                            "case_id": direct_view["id"], "version": direct_view["version"], "summary": direct_view["summary"],
                            "login_audit_id": login_audits[0]["id"], "all_old_audits_unchanged": True, "all_other_business_tables_unchanged": True})
        cp.start("HK-116")
        _, after_renewed = await generate(e, context, credentials, fixture, cv, expected_created=0)
        returned = await termination_and_refunds(e, context, credentials, fixture, first, cv, account, tender, pass_entry, comm_payment, issued, renewal, token)
        effective = await vehicle_sources(e, context, credentials, fixture, cv, effective_ids={new_issued["observation_id"]}, inactive_ids={issued["observation_id"]})
        _, after_invalidation = await generate(e, context, credentials, fixture, cv, expected_created=0)
        _, final_care = await read_as(e, context, credentials, fixture, "manager", renewal, care=True)
        require(final_care["state"] == "completed" and final_care["result"] == "renewed" and final_care["reminder_basis"]["status"] == "invalidated"
                and not final_care["actions"] and case(e, second)["state"] == "completed", "失效投影覆盖了旧结案或新续保事实")
        await cp.passed(before_boundary=before_boundary, at_boundary=at_boundary, same_cycle_duplicate_check=duplicate, original_today_work=work,
                        completed_no_repeat=after_renewed, original_termination_and_three_returns=returned, effective_vehicle_sources=effective,
                        invalidated_no_repeat=after_invalidation, original_completed_care=final_care, no_external_customer_message_claim=True)
        cp.finish({"customer_id": customer["id"], "customer_vehicle_id": cv["id"], "insurer_id": insurer["id"], "account_id": account["id"], "first_insurance_case_id": first,
                   "first_issued_result_id": issued["id"], "first_observation_id": issued["observation_id"], "renewal_care_case_id": renewal,
                   "renewal_rule_id": rule10["id"], "new_insurance_case_id": second, "new_issued_result_id": new_issued["id"], "new_observation_id": new_issued["observation_id"]})
    except Exception as error:
        cp.failed(error)
        raise


INSURANCE_SCENARIOS = ((SCENARIO, insurance_business, 900),)
