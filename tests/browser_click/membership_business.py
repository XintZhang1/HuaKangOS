"""Unregistered native membership candidate: five checks, two source partials.

Only this run's passed sale customer and purchase account supply IDs. Every
business write is an employee's original visible form; SQLite is SELECT-only.
No fixture balance, demo member, direct API write, or unknown-result replay.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
import uuid

from playwright.async_api import expect

from sales_business import employee_choice, login_as, require
from sales_order_business import checkpoint_evidence, fixed_dependency
from vehicle_purchase_business import checkbox, live_choice, select_value, upload

SCENARIO = "membership-hk117-128-118-089-094"
SALES = "sales-order-hk008-009-011-022"
PURCHASE = "vehicle-purchase-hk171-177-178-026-021-018-029"
REQUIREMENTS = (
    ("HK-117", "会员信息管理"), ("HK-128", "会员卡生成"),
    ("HK-118", "会员换补卡"), ("HK-089", "会员储值卡充值收款"),
    ("HK-094", "会员储值卡退款"),
)
TABLES = {
    "group_identities", "group_identity_links", "group_members", "group_entries",
    "group_refund_requests", "group_settlement_entries", "group_events", "group_receipts",
    "membership_orders", "membership_cards", "membership_events", "flow_cases",
    "flow_tasks", "flow_events", "flow_request_receipts", "flow_files",
    "file_security", "file_scan_events", "audit_logs", "cash_entries", "flow_accounts",
}
CASE_COLUMNS = {"version", "updated_at", "state", "completed_date"}
TASK_COLUMNS = {"version", "updated_at", "status", "done_by", "done_at"}
MEMBER_COLUMNS = {"version", "updated_at", "balance_cents", "reserved_cents"}


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        source = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(source).hexdigest()
        catalog = {r["id"]: r for r in json.loads(source)["requirements"]}
        for key, title in REQUIREMENTS:
            require(catalog[key]["title"] == title and catalog[key]["source_review_status"] == "source_reviewed",
                    key + " 原源合同不匹配")
            require(any(c["check_id"] == key + "-business" for c in catalog[key]["acceptance_checks"]), key + " check缺失")
        self.report = {
            "schema": 1, "scenario": SCENARIO, "scope": [r[0] for r in REQUIREMENTS],
            "complete": False, "passed": False, "execution": "native_browser_original_forms",
            "source_contract_sha256": self.digest,
            "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "human_acceptance": "pending", "requirements": [
                {"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                 "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                 "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business",
                                        "status": "not_tested", "evidence": {}}]} for key, title in REQUIREMENTS],
            "partial_requirements": [
                {"id": "HK-124", "title": "会员储值卡充值", "status": "not_tested", "business_accepted": False,
                 "acceptance_check_submitted": False, "unexecuted_scope": ["原组合套餐规则、条款接受及独立购买履约"]},
                {"id": "HK-125", "title": "会员储值卡退款请求", "status": "not_tested", "business_accepted": False,
                 "acceptance_check_submitted": False, "unexecuted_scope": ["组合完整未用份额退款、赠品批次及取消释放"]}],
            "conditions": {"synthetic_money_inputs_only": True, "bank_payment_acceptance": False,
                           "production_acceptance": False, "file_scan": "structure_only_not_clamav",
                           "points_tier_period_benefit_consumption_acceptance": False,
                           "business_entity_policy_acceptance": False, "legacy_admin_self_review_exercised": False},
        }
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active.update(status="running", evidence_action_start=len(self.e.actions))
        self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    async def passed(self, evidence):
        self.active["acceptance_checks"][0]["evidence"] = evidence
        await self.e.snapshot(self.active["id"].lower() + "-business")
        self.active.update(status="passed", evidence_action_end=len(self.e.actions))
        self.active["acceptance_checks"][0]["status"] = "passed"
        self.active = None
        self.save()

    def partial(self, key, evidence):
        r = next(r for r in self.report["partial_requirements"] if r["id"] == key)
        r.update(status="partial", local_scope_status="ordinary_principal_scope_passed", evidence=evidence)
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = "failed"
            self.active["acceptance_checks"][0].update(status="failed", error=self.e.scrub(error))
            self.report["failed_requirement"] = self.active["id"]
        else:
            self.report["failed_source_precondition"] = "same_run_membership_source"
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "会员五项未完整执行")
        require(all(r["status"] == "partial" for r in self.report["partial_requirements"]), "两个本金支路未完整记录")
        self.report.update(complete=True, passed=True, executed_requirements=5, passed_requirements=5,
                           membership_sources=sources)
        self.save()
        self.e.observe("membership_original_checkpoint", {"path": str(self.path), "passed_checks": 5,
                       "partial": ["HK-124", "HK-125"], "business_accepted": False})


def rows(e, table):
    require(table in TABLES, "会员守卫表未审阅：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {'file_id' if table == 'file_security' else 'id'}")


def one(e, table, key):
    require(table in TABLES | {"flow_customers"}, "原来源表未审阅：" + table)
    found = e.db.rows(f"SELECT * FROM {table} WHERE id=?", (key,))
    require(len(found) == 1, "本轮原记录缺失或不唯一：" + table)
    return found[0]


class Guard:
    """Protect all other tables and every old row; updates use finite IDs/columns."""
    def __init__(self, e, label, *, actor, append=(), update=None, cases=(), customer=None, member=None):
        self.e, self.label, self.actor = e, label, actor
        self.append, self.update = set(append), update or {}
        self.cases, self.customer, self.member = set(cases), customer, member
        require(self.append | self.update.keys() <= TABLES, "会员守卫表超范围")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.append | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.append | self.update.keys(), "会员办理改动无关原表：" + str(sorted(changed)))
        added, modified = {}, {}
        added_cases, added_members = set(), set()
        if "flow_cases" in self.append:
            old_ids = {r["id"] for r in self.old["flow_cases"]}
            fresh = [r for r in rows(self.e, "flow_cases") if r["id"] not in old_ids]
            require(len(fresh) == 1 and fresh[0]["kind"] == "membership"
                    and fresh[0]["created_by"] == fresh[0]["owner_id"] == self.actor
                    and fresh[0]["customer_id"] == self.customer, "创建未产生唯一本人同客户会员原单")
            added_cases = {fresh[0]["id"]}
        if "group_members" in self.append:
            added_members = {r["id"] for r in rows(self.e, "group_members")} - {r["id"] for r in self.old["group_members"]}
            require(len(added_members) == 1, "开通未产生唯一会员")
        for table, old in self.old.items():
            pk = "file_id" if table == "file_security" else "id"
            current = {r[pk]: r for r in rows(self.e, table)}
            old_ids = {r[pk] for r in old}
            modified[table] = []
            for original in old:
                key = original[pk]
                require(key in current, "会员办理删除原事实：" + table)
                diff = {c for c in original if original[c] != current[key][c]}
                require(diff <= self.update.get(table, {}).get(key, set()), "会员办理覆盖原事实：" + table + "/" + str(key) + "/" + str(sorted(diff)))
                if diff:
                    modified[table].append({"id": key, "columns": sorted(diff)})
            new = [r for key, r in current.items() if key not in old_ids]
            require(not new or table in self.append, "仅更新表出现新增：" + table)
            for r in new:
                if "store_id" in r:
                    require(r["store_id"] == self.e.manifest["business_fixtures"]["sales_order"]["store_id"], "会员新增事实串店")
                if "case_id" in r:
                    require(r["case_id"] in self.cases | added_cases, "会员新增事实串原单：" + table)
                if "member_id" in r and r["member_id"] is not None:
                    require(r["member_id"] in added_members | ({self.member} if self.member else set()), "会员新增事实串会员")
                if "actor_id" in r:
                    require(r["actor_id"] == self.actor, "会员新增事实借用他人身份：" + table)
                if table == "audit_logs":
                    require(r["entity_type"] == "flow" and r["entity_id"] in self.cases | added_cases,
                            "会员新增审计不是本次原单")
            added[table] = [r[pk] for r in new]
        evidence = {"label": self.label, "changed_tables": sorted(changed), "appended_ids": added,
                    "updated_columns": modified, "all_other_tables_unchanged": True, "all_other_old_rows_unchanged": True}
        self.e.observe("membership_original_guard", evidence)
        return evidence


def updates(e, *, case_id=None, member_id=None, order_id=None, card_id=None, refund_id=None, account_id=None):
    result = {}
    if case_id:
        result["flow_cases"] = {case_id: CASE_COLUMNS}
        result["flow_tasks"] = {r["id"]: TASK_COLUMNS for r in rows(e, "flow_tasks") if r["case_id"] == case_id}
    if member_id:
        result["group_members"] = {member_id: MEMBER_COLUMNS}
    if order_id:
        result["membership_orders"] = {order_id: {"status", "version", "updated_at"}}
    if card_id:
        result["membership_cards"] = {card_id: {"status", "version", "updated_at"}}
    if refund_id:
        result["group_refund_requests"] = {refund_id: {"version", "updated_at", "status", "approved_by", "approved_at", "closed_by", "executed_entry_id"}}
    if account_id:
        result["flow_accounts"] = {account_id: {"version", "updated_at"}}
    return result


def member_facts(e, member_id):
    member = one(e, "group_members", member_id)
    result = {"member": member}
    for key, table in (("cards", "membership_cards"), ("entries", "group_entries"), ("refunds", "group_refund_requests")):
        result[key] = [r for r in rows(e, table) if r["member_id"] == member_id]
    return result


def order_facts(e, case_id):
    found = [r for r in rows(e, "membership_orders") if r["case_id"] == case_id]
    require(len(found) == 1, "会员单缺唯一原 Order")
    case, order = one(e, "flow_cases", case_id), found[0]
    result = {"case": case, "order": order, "member": one(e, "group_members", order["member_id"])}
    for key, table in (("tasks", "flow_tasks"), ("events", "flow_events"), ("membership_events", "membership_events")):
        result[key] = [r for r in rows(e, table) if r["case_id"] == case_id]
    return result


def open_task(e, case_id, key):
    found = [r for r in rows(e, "flow_tasks") if r["case_id"] == case_id and r["key"] == key and r["status"] == "open"]
    require(len(found) == 1, "会员本人原待办不唯一：" + key)
    return found[0]


def group_receipt(e, request, actor, action, payload, result):
    found = e.db.rows("SELECT * FROM group_receipts WHERE request_key=?", (request["request_id"],))
    digest = hashlib.sha256(json.dumps([action, payload], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    require(len(found) == 1 and found[0]["actor_id"] == actor["id"] and found[0]["store_id"] == 1
            and found[0]["digest"] == digest, "集团原收据未绑定本人精确本次请求")
    saved = json.loads(found[0]["result"])
    require(saved == result, "集团原收据与本次原响应结果不一致")
    return {"id": found[0]["id"], "digest": digest, "actor_id": actor["id"], "store_id": found[0]["store_id"],
            "result_sha256": hashlib.sha256(json.dumps(saved, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}


def exact_appends(protection, expected):
    result = protection.finish()
    actual = {table: len(ids) for table, ids in result["appended_ids"].items() if ids}
    require(actual == expected, "本次原会员办理新增记录数不一致：" + str(actual))
    result["expected_append_counts"] = expected
    return result


def group_event(e, protection, action, *, member_id=None, detail=None):
    old = {r["id"] for r in protection.old["group_events"]}
    fresh = [r for r in rows(e, "group_events") if r["id"] not in old]
    require(len(fresh) == 1 and fresh[0]["action"] == action and fresh[0]["member_id"] == member_id,
            "集团原事件动作或会员来源不一致")
    value = json.loads(fresh[0]["detail"])
    require(all(value.get(k) == v for k, v in (detail or {}).items()), "集团原事件未关联本次来源")
    return {"id": fresh[0]["id"], "action": action, "member_id": member_id, "detail": value}


def new_events(e, protection, case_id, actor, actions):
    old = {r["id"] for r in protection.old.get("flow_events", [])}
    found = [r for r in rows(e, "flow_events") if r["id"] not in old]
    require([r["action"] for r in found] == list(actions)
            and all(r["case_id"] == case_id and r["actor_id"] == actor["id"] for r in found), "会员原事件动作或来源不一致")
    audits = [r for r in rows(e, "audit_logs") if r["id"] not in {r["id"] for r in protection.old.get("audit_logs", [])}]
    require(len(audits) == len(found) and [r["action"] for r in audits] == ["flow_" + a for a in actions]
            and all(r["entity_type"] == "flow" and r["entity_id"] == case_id and r["actor_id"] == actor["id"] for r in audits),
            "原事件未精确对应本次审计")
    return {"event_ids": [r["id"] for r in found], "audit_ids": [r["id"] for r in audits], "actions": list(actions)}


def dependencies(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "只允许新外部合成实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "会员数据库不是同轮runtime")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance.get("snapshot_stable") is True, "同轮镜像不是稳定快照")
    for name in ("membership_business.py", "business_acceptance_catalog.json", "sales_business.py",
                 "vehicle_purchase_business.py", "sales_order_business.py"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(), "同轮脚本已变化：" + name)
    sale, purchase = fixed_dependency(e, cp, SALES), fixed_dependency(e, cp, PURCHASE)
    source_id = sale["report_sources"]["customer_id"]
    require(type(source_id) is int and source_id > 0, "销售缺精确同轮客户ID")
    customer = one(e, "flow_customers", source_id)
    origin = checkpoint_evidence(purchase, "HK-021")
    account = one(e, "flow_accounts", origin["payment"]["account_id"])
    fixture = dict(e.manifest["business_fixtures"]["sales_order"])
    for role in ("sales", "service", "manager", "finance"):
        actor = e.manifest["users"][fixture[role + "_key"]]
        require(actor["role"] == role and len(e.db.rows("SELECT user_id FROM user_stores WHERE user_id=? AND store_id=? AND role=?",
                (actor["id"], fixture["store_id"], role))) == 1, "缺本人当前店实际岗位：" + role)
    require(customer["store_id"] == account["store_id"] == fixture["store_id"] == 1
            and customer["owner_id"] == e.manifest["users"][fixture["sales_key"]]["id"]
            and customer["contact_allowed"] == 1 and account["active"] == 1, "同轮客户归属、联系或本店账户失效")
    require(re.fullmatch(r"\d{7,20}", re.sub(r"[\s()+-]", "", customer["phone"])), "同轮客户没有原集团身份所需完整电话")
    require(not e.db.rows("SELECT id FROM group_identity_links WHERE store_id=? AND local_kind='customer' AND local_id=?", (1, customer["id"])),
            "同轮客户已有身份，不跳过本批明确关联或借旧开通结果")
    require(not e.db.rows("SELECT id FROM business_entity_policies WHERE store_id=?", (1,)),
            "当前合成实例已有经营主体策略；本批未授权增加完整主体前序，不能绕过原规则")
    cp.report["source_preconditions"] = {"customer": customer, "account": account,
        "customer_source": {"scenario": SALES, "key": "report_sources.customer_id"},
        "account_source": {"scenario": PURCHASE, "requirement": "HK-021", "key": "payment.account_id"},
        "stable_provenance_sha256": hashlib.sha256((root / "provenance.json").read_bytes()).hexdigest(),
        "new_fixture_results": False, "new_roles": 0}
    cp.save()
    return fixture, customer, account


def get_matches(response, path):
    actual = urlsplit(response.url).path
    return response.request.method == "GET" and (actual.startswith(path) and actual[len(path):].isdigit() if path.endswith("/") else actual == path)


async def submit(e, path, render_path, *, status=200):
    async with e.page.expect_response(lambda r: get_matches(r, render_path)) as rendered:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "本人核对后提交原会员表单")
        response = await pending.value
        body = await response.json()
        require(response.status == status, f"原会员表单HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    read = await rendered.value
    displayed = await read.json()
    require(read.status == 200, "原会员提交后的实际读取失败")
    headers = await response.request.all_headers()
    request = response.request.post_data_json
    original_assign = path.startswith("/api/flow/tasks/") and path.endswith("/assign")
    require(isinstance(request, dict) and (original_assign or request.get("request_id")) and headers.get("x-app-request") == "1"
            and headers.get("x-store-id") == "1" and headers.get("cookie") and headers.get("x-csrf-token"), "原会员同源身份/CSRF/请求号合同缺失")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    meta = {"path": path, "method": "POST", "status": status, "native_ui": True, "cookie_present": True,
            "csrf_present": True, "store_id": 1,
            "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest() if request.get("request_id") else None,
            "submitted_version": request.get("version"), "submitted_case_version": request.get("case_version"),
            "submitted_member_version": request.get("member_version"), "render_get_path": urlsplit(read.url).path,
            "render_get_status": read.status}
    e.observe("native_membership_submit", meta)
    return body, request, displayed, meta


async def ready_member(e, context, credentials, fixture, role, customer, *, group=False):
    route = ("group/" if group else "membership/") + str(customer["id"])
    path = "/api/group/members" if group else "/api/membership/members"
    async with e.page.expect_response(lambda r: get_matches(r, path)
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], route, fixture["store_id"])
    read = await pending.value
    body = await read.json()
    require(read.status == 200 and body["customer"]["id"] == customer["id"], "会员原查询串客户")
    await expect(e.page.locator("#main h1")).to_have_text("集团会员" if group else "会员卡与续会")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(customer["name"])
    return actor, body


async def ready_order(e, context, credentials, fixture, role, case_id):
    async with e.page.expect_response(lambda r: get_matches(r, "/api/membership/orders/" + str(case_id))) as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], "membership-order/" + str(case_id), fixture["store_id"])
    response = await pending.value
    body = await response.json()
    f = order_facts(e, case_id)
    require(response.status == 200 and body["case"]["id"] == case_id
            and all(body["case"][k] == f["case"][k] for k in ("id", "number", "version", "state", "customer_id", "amount_cents"))
            and all(body["order"][k] == f["order"][k] for k in ("id", "case_id", "member_id", "purpose", "status", "version"))
            and body["member"]["version"] == f["member"]["version"], "会员原订单API/DB不一致")
    await expect(e.page.locator("#main h1")).to_have_text("会员业务办理")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(f["case"]["title"])
    return actor, body


async def original_action(e, act, key, title, *, sub_id=None):
    selector = f'#main [data-act="{act}"][data-key="{key}"]' + (f'[data-id="{sub_id}"]' if sub_id else "")
    await expect(e.page.locator(selector)).to_have_count(1)
    await expect(e.page.locator(selector)).to_be_visible()
    await expect(e.page.locator(selector)).to_be_enabled()
    await e.click(selector, "打开原会员办理：" + title)
    await expect(e.page.locator("#modal-title")).to_have_text(title)


async def choose_file(e, file_id):
    asset = one(e, "flow_files", file_id)
    require(asset["category"] == "evidence", "本次会员凭据类别未核实")
    await live_choice(e, "evidence_id", asset["name"], asset["name"] + " · 业务凭据", expected_value=file_id)


async def responsible(e, context, credentials, fixture, case_id, task_key, role):
    actor = e.manifest["users"][fixture[role + "_key"]]
    task = open_task(e, case_id, task_key)
    meta = {"task_id": task["id"], "key": task_key, "actor_id": actor["id"], "handoff_needed": task["assignee_id"] != actor["id"]}
    if meta["handoff_needed"]:
        manager = await login_as(e, context, credentials, fixture["manager_key"], "case/" + str(case_id), fixture["store_id"])
        await expect(e.page.locator("#main h1")).to_have_text(one(e, "flow_cases", case_id)["title"])
        await e.click(f'#main [data-act="assign"][data-id="{task["id"]}"]', "主管明确转交原会员待办")
        await expect(e.page.locator("#modal-title")).to_have_text("转交任务")
        await employee_choice(e, actor)
        reason = "本店已选岗位员工本人办理本次会员原事实"
        await e.fill('#modal [name="reason"]', reason, "填写原待办转交依据")
        protection = Guard(e, "membership_task_handoff", actor=manager["id"], append={"flow_events", "audit_logs"},
                           update={"flow_tasks": {task["id"]: {"assignee_id", "version", "updated_at"}}}, cases={case_id})
        _, request, _, native = await submit(e, f'/api/flow/tasks/{task["id"]}/assign', f"/api/flow/cases/{case_id}")
        require(request == {"version": task["version"], "assignee_id": actor["id"], "reason": reason}, "原AssignInput错误")
        meta.update(native=native, protection=exact_appends(protection, {"flow_events": 1, "audit_logs": 1}),
                    events=new_events(e, protection, case_id, manager, ("reassign",)))
        now = open_task(e, case_id, task_key)
        require(now["assignee_id"] == actor["id"] and now["role"] == role and now["version"] > task["version"], "原任务未转给真实同岗本人")
    return meta


async def upload_original(e, case_id, actor, member_id, purpose, token):
    protection = Guard(e, "membership_upload_" + purpose, actor=actor["id"],
                       append={"flow_files", "file_security", "file_scan_events", "flow_events", "audit_logs"}, cases={case_id}, member=member_id)
    file_id = await upload(e, case_id, actor, "evidence", purpose + "-" + token + ".txt",
                           "本次合成会员申请和本人确认；用途=" + purpose + "；原业务=" + str(case_id))
    asset = one(e, "flow_files", file_id)
    stored = asset.pop("content")
    selected = (e.directory / "synthetic-inputs" / asset["name"]).read_bytes()
    require(isinstance(stored, bytes) and stored == selected and len(stored) == asset["size"]
            and hashlib.sha256(stored).hexdigest() == asset["sha256"], "原会员附件实际字节与员工所选内容不匹配")
    safety = exact_appends(protection, {"flow_files": 1, "file_security": 1, "file_scan_events": 1,
                                       "flow_events": 1, "audit_logs": 1})
    new_events(e, protection, case_id, actor, ("upload",))
    require(safety["appended_ids"]["flow_files"] == [file_id] and len(safety["appended_ids"]["file_scan_events"]) == 1,
            "原上传产生额外文件或扫描")
    safety.update(file=asset, stored_blob={"length": len(stored), "sha256": hashlib.sha256(stored).hexdigest()})
    return file_id, safety


async def create_order(e, context, credentials, fixture, customer, member_id, purpose, reason, *, card_id=None):
    actor, _ = await ready_member(e, context, credentials, fixture, "service", customer)
    title = {"card_issue": "发行会员卡", "card_loss": "会员卡挂失", "card_replace": "会员卡换补", "topup": "集团本金充值"}[purpose]
    await original_action(e, "membership-create", purpose, title, sub_id=card_id)
    values = {"card_id": card_id} if card_id else {"amount_cents": 10000} if purpose == "topup" else {}
    if purpose == "topup":
        await e.fill('#modal [name="amount"]', "100.00", "输入本次独立本金充值100.00元")
    await e.fill('#modal [name="reason"]', reason, "填写本人核对的会员申请原因")
    protection = Guard(e, "membership_create_" + purpose, actor=actor["id"], customer=customer["id"], member=member_id,
        append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "membership_orders", "membership_events", "group_receipts"},
        update={"group_members": {member_id: {"version", "updated_at"}}})
    body, request, displayed, meta = await submit(e, "/api/membership/orders", "/api/membership/orders/", status=201)
    case_id = body["case"]["id"]
    f = order_facts(e, case_id)
    require(request == {"request_id": request["request_id"], "customer_id": customer["id"], "purpose": purpose, "values": values, "reason": reason},
            "原会员申请不绑定本次明确输入")
    require(displayed["case"]["id"] == case_id and f["case"]["flow_version"] == 2
            and f["case"]["state"] == "pending" and f["case"]["amount_cents"] == (10000 if purpose == "topup" else 0)
            and f["order"]["purpose"] == purpose and f["order"]["requested_by"] == actor["id"]
            and f["order"]["status"] == "draft" and json.loads(f["order"]["values"]) == values, "原会员单、原申请人或冻结金额不匹配")
    task = open_task(e, case_id, "membership_execute")
    require(task["role"] == ("finance" if purpose == "topup" else "service"), "原会员待办岗位不符")
    receipt = group_receipt(e, request, actor, "membership_create",
                            {k: v for k, v in request.items() if k != "request_id"}, body)
    meta.update(receipt=receipt, protection=exact_appends(protection, {
        "flow_cases": 1, "flow_tasks": 1, "flow_events": 1, "audit_logs": 1,
        "membership_orders": 1, "membership_events": 1, "group_receipts": 1}),
        events=new_events(e, protection, case_id, actor, ("membership_create",)))
    await expect(e.page.locator("#main h1")).to_have_text("会员业务办理")
    await expect(e.page.locator("#main")).to_contain_text(title)
    return case_id, meta


async def execute_order(e, context, credentials, fixture, case_id, purpose, token, *, account=None, original_card=None):
    role = "finance" if purpose == "topup" else "service"
    task_meta = await responsible(e, context, credentials, fixture, case_id, "membership_execute", role)
    actor, _ = await ready_order(e, context, credentials, fixture, role, case_id)
    before = order_facts(e, case_id)
    member_id = before["member"]["id"]
    file_id, upload_meta = await upload_original(e, case_id, actor, member_id, purpose, token)
    # Upload re-renders the original order; use actual post-upload versions.
    before = order_facts(e, case_id)
    await original_action(e, "membership-action", "execute", "确认实际办理")
    await choose_file(e, file_id)
    reason = "本人已核对本单客户确认和本次独立办理事实"
    await e.fill('#modal [name="reason"]', reason, "填写实际办理依据")
    value = {"evidence_id": file_id, "reason": reason}
    if account:
        await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
        reference = "MEM-IN-" + token
        await e.fill('#modal [name="reference"]', reference, "输入本次独立合成到账流水号")
        value.update(account_id=account["id"], reference=reference)
    append = {"membership_events", "group_receipts", "flow_events", "audit_logs"}
    if purpose in {"card_issue", "card_replace"}:
        append.add("membership_cards")
    if purpose == "topup":
        append |= {"group_entries", "group_settlement_entries", "cash_entries", "group_events"}
    permitted = updates(e, case_id=case_id, member_id=member_id, order_id=before["order"]["id"],
                        card_id=original_card["id"] if original_card else None, account_id=account["id"] if account else None)
    if purpose.startswith("card_"):
        permitted["group_members"][member_id] = {"version", "updated_at"}
    protection = Guard(e, "membership_execute_" + purpose, actor=actor["id"], append=append, cases={case_id},
                       member=member_id, update=permitted)
    body, request, shown, meta = await submit(e, f"/api/membership/orders/{case_id}/actions/execute", f"/api/membership/orders/{case_id}")
    require(request == {"request_id": request["request_id"], "version": before["order"]["version"], "case_version": before["case"]["version"],
                       "member_version": before["member"]["version"], "values": value}, "原会员执行金额、来源或三版本合同不符")
    after = order_facts(e, case_id)
    require(after["order"]["status"] == after["case"]["state"] == "completed" and after["case"]["completed_date"]
            and all(t["status"] == "done" and t["done_by"] == actor["id"] for t in after["tasks"]), "实际办理未完成本单本人任务")
    require(all(after[key]["version"] > before[key]["version"] for key in ("case", "order", "member")),
            "实际办理未推进原单、会员业务及会员真实版本")
    require(shown["order"]["status"] == "completed" and shown["case"]["version"] == after["case"]["version"]
            and shown["member"]["version"] == after["member"]["version"], "办理结果API/DB版本不一致")
    await expect(e.page.locator("#main")).to_contain_text("已完成")
    await expect(e.page.locator('#main [data-act="membership-action"][data-key="execute"]')).to_have_count(0)
    if purpose == "topup":
        payload = {"member_id": member_id, "version": before["member"]["version"],
                   "values": {"amount_cents": 10000, **value, "case_id": case_id, "case_version": before["case"]["version"]}}
        receipt = group_receipt(e, request, actor, "member_topup", payload, body["result"])
        actions = ("membership_topup", "group_topup")
        expected = {"membership_events": 1, "group_receipts": 1, "flow_events": 2, "audit_logs": 2,
                    "group_entries": 1, "group_settlement_entries": 2, "cash_entries": 1, "group_events": 1}
    else:
        receipt = group_receipt(e, request, actor, f"membership:{case_id}:execute",
                                {k: v for k, v in request.items() if k != "request_id"}, body)
        actions = ("membership_execute",)
        expected = {"membership_events": 1, "group_receipts": 1, "flow_events": 1, "audit_logs": 1}
        if purpose in {"card_issue", "card_replace"}:
            expected["membership_cards"] = 1
    meta.update(task=task_meta, file_id=file_id, upload=upload_meta, receipt=receipt,
                protection=exact_appends(protection, expected), events=new_events(e, protection, case_id, actor, actions))
    if purpose == "topup":
        meta["group_event"] = group_event(e, protection, "topup", member_id=member_id, detail={"case_id": case_id})
    return after, meta


async def separate_benefits(e, customer, member_id):
    before = e.business_snapshot("before_original_member_separate_benefits")
    async with e.page.expect_response(lambda r: get_matches(r, "/api/group/benefits/members")
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as pending:
        await e.click(f'#main [data-act="open"][data-route="benefits/{customer["id"]}"]', "实际查看独立集团权益账")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["member"]["id"] == member_id and body["customer"]["id"] == customer["id"]
            and body["wallets"] == [] and body["entries"] == [], "识别卡开通误生成赠品或混入旧权益")
    await expect(e.page.locator("#main h1")).to_have_text("集团权益")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(customer["name"])
    e.business_unchanged(before, "after_original_member_separate_benefits")
    return {"original_ui": True, "member_id": member_id, "wallets": [], "entries": [], "business_unchanged": True}


async def lookup_card(e, card, customer, *, valid):
    await e.click('#main [data-act="open"][data-route="membership"]', "返回原会员客户列表")
    await expect(e.page.locator("#main h1")).to_have_text("会员卡与续会")
    await expect(e.page.locator('[data-act="membership-card-lookup"]')).to_be_visible()
    await e.click('[data-act="membership-card-lookup"]', "实际按完整会员卡号识别客户")
    await expect(e.page.locator("#modal-title")).to_have_text("按卡号识别本店客户")
    await e.fill('#modal [name="number"]', card["number"], "填写该轮实际生成的完整卡号")
    before = e.business_snapshot("before_native_membership_card_lookup")
    async with e.page.expect_response(lambda r: get_matches(r, "/api/membership/cards/lookup")
            and parse_qs(urlsplit(r.url).query).get("number") == [card["number"]]) as pending:
        await e.click('#modal form button[type="submit"]', "提交原只读卡号识别")
    response = await pending.value
    body = await response.json()
    require(response.status == (200 if valid else 404), "新旧卡号识别状态不正确")
    if valid:
        require(body["customer"]["id"] == customer["id"] and any(c["id"] == card["id"] and c["status"] == "active" for c in body["cards"]),
                "有效卡识别了其他客户或失效卡")
        await expect(e.page.locator("#modal")).not_to_be_visible()
        await expect(e.page.locator("#main .pagehead")).to_contain_text(customer["name"])
    else:
        message = "有效会员卡不存在，请核对客户；旧卡与挂失卡不能识别"
        require(body.get("detail") == message, "原旧卡识别拒绝文案不符")
        await expect(e.page.locator("#modal .formerror")).to_contain_text(message)
        await e.snapshot("original-card-lookup-rejected")
        await expect(e.page.locator("#modal form")).not_to_have_attribute("aria-busy", "true")
        await e.click('#modal .modalhead [data-act="close"]', "关闭失效卡识别填写")
        await expect(e.page.locator("#modal .wfx-discard")).to_be_visible()
        await e.click('#modal [data-wfx-discard]', "明确放弃失效卡查询填写")
        await expect(e.page.locator("#modal")).not_to_be_visible()
        async with e.page.expect_response(lambda r: get_matches(r, "/api/flow/master/customers")
                and parse_qs(urlsplit(r.url).query).get("q") == [customer["name"]]) as searched:
            await e.fill('#filters [name="q"]', customer["name"], "按明确本轮客户重新检索，不借列表首项")
        search_result = await searched.value
        require(search_result.status == 200 and any(r["id"] == customer["id"] for r in (await search_result.json())["items"]),
                "失效卡查询后原客户检索缺该轮来源")
        await e.click(f'#main [data-act="open"][data-route="membership/{customer["id"]}"]', "返回本次明确客户会员资料")
        await expect(e.page.locator("#main .pagehead")).to_contain_text(customer["name"])
    e.business_unchanged(before, "after_native_membership_card_lookup")
    return {"card_id": card["id"], "number": card["number"], "status": response.status, "customer_id": customer["id"] if valid else None,
            "original_ui": True, "business_unchanged": True}


async def group_action(e, context, credentials, fixture, customer, member_id, key, target, topup_case_id, token, account):
    role = "service" if key == "refund_request" else "manager" if key == "refund_approve" else "finance"
    task_meta = None
    if key != "refund_request":
        task_meta = await responsible(e, context, credentials, fixture, topup_case_id,
            ("group_refund_review_" if key == "refund_approve" else "group_refund_pay_") + str(target["id"]), role)
    actor, _ = await ready_member(e, context, credentials, fixture, role, customer, group=True)
    # Finance uploads an independent refund fact to the exact original topup host.
    file_id = target["evidence_id"]
    upload_meta = None
    if key == "refund":
        actor, _ = await ready_order(e, context, credentials, fixture, role, topup_case_id)
        file_id, upload_meta = await upload_original(e, topup_case_id, actor, member_id, "refund", token)
        actor, _ = await ready_member(e, context, credentials, fixture, role, customer, group=True)
    title = {"refund_request": "申请本金退款", "refund_approve": "批准并占用退款本金", "refund": "本金退款"}[key]
    await original_action(e, "group-action", key, title, sub_id=target["id"])
    before_member = one(e, "group_members", member_id)
    source_case = one(e, "flow_cases", topup_case_id)
    values = {"case_version": source_case["version"]}
    reason = "核对本次原充值和客户退款申请，保留原收退款事实"
    if key == "refund_request":
        await e.fill('#modal [name="amount"]', "40.00", "输入原本金部分退款40.00元")
        await choose_file(e, file_id)
        await e.fill('#modal [name="reason"]', reason, "填写原款退款申请依据")
        values.update(original_id=target["id"], amount_cents=4000, evidence_id=file_id, reason=reason)
    else:
        values.update(refund_request_id=target["id"], refund_request_version=target["version"])
        if key == "refund_approve":
            await e.fill('#modal [name="reason"]', reason, "另一主管填写独立原款核对依据")
            values["reason"] = reason
        else:
            await choose_file(e, file_id)
            await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
            reference = "MEM-OUT-" + token
            await e.fill('#modal [name="reference"]', reference, "输入本次实际合成退款流水号")
            values.update(account_id=account["id"], reference=reference, evidence_id=file_id)
    append = {"group_receipts", "group_events", "flow_events", "audit_logs"}
    if key in {"refund_request", "refund_approve"}:
        append.add("flow_tasks")
    if key == "refund_request":
        append.add("group_refund_requests")
    if key == "refund":
        append |= {"group_entries", "group_settlement_entries", "cash_entries"}
    protection = Guard(e, "membership_" + key, actor=actor["id"], append=append, cases={topup_case_id}, member=member_id,
        update=updates(e, case_id=topup_case_id, member_id=member_id, refund_id=target["id"] if key != "refund_request" else None,
                       account_id=account["id"] if key == "refund" else None))
    body, request, displayed, meta = await submit(e, f"/api/group/members/{member_id}/actions/{key}", "/api/group/members")
    require(request == {"request_id": request["request_id"], "version": before_member["version"], "values": values}, "集团退款请求版本/金额/原账户不匹配")
    member = one(e, "group_members", member_id)
    require(body["member"]["id"] == member_id and body["member"]["version"] == member["version"]
            and displayed["member"]["id"] == member_id and displayed["customer"]["id"] == customer["id"], "退款响应或页面串会员/客户")
    refund_id = body["refund_request"]["id"]
    refund = one(e, "group_refund_requests", refund_id)
    require(refund["member_id"] == member_id and refund["case_id"] == topup_case_id and refund["amount_cents"] == 4000
            and refund["requested_by"] == e.manifest["users"][fixture["service_key"]]["id"], "原退款申请身份/金额/来源不符")
    expected = {"refund_request": (10000, 0, "requested"), "refund_approve": (10000, 4000, "approved"), "refund": (6000, 0, "executed")}[key]
    require((member["balance_cents"], member["reserved_cents"], refund["status"]) == expected, "原退款余额/占额/状态不一致")
    if key != "refund_request":
        require(refund["approved_by"] == e.manifest["users"][fixture["manager_key"]]["id"] != refund["requested_by"], "原退款没有不同主管批准")
    receipt = group_receipt(e, request, actor, "member_" + key,
                            {"member_id": member_id, "version": before_member["version"], "values": values}, body)
    events = new_events(e, protection, topup_case_id, actor, ("group_" + key,))
    expected = {"group_receipts": 1, "group_events": 1, "flow_events": 1, "audit_logs": 1}
    if key in {"refund_request", "refund_approve"}:
        expected["flow_tasks"] = 1
    if key == "refund_request":
        expected["group_refund_requests"] = 1
    if key == "refund":
        expected.update(group_entries=1, group_settlement_entries=2, cash_entries=1)
    safety = exact_appends(protection, expected)
    await expect(e.page.locator("#main h1")).to_have_text("集团会员")
    await expect(e.page.locator("#main")).to_contain_text({"refund_request": "待审批", "refund_approve": "已占额待退款", "refund": "已退款"}[key])
    meta.update(receipt=receipt, events=events, protection=safety, task=task_meta, upload=upload_meta, file_id=file_id,
                member_balance_cents=member["balance_cents"], member_reserved_cents=member["reserved_cents"], refund_request_id=refund_id,
                group_event=group_event(e, protection, key, member_id=member_id, detail={"case_id": topup_case_id}))
    return refund, meta


async def membership_business(e, context, credentials):
    cp = Checkpoint(e)
    token = uuid.uuid4().hex[:12]
    try:
        fixture, customer, account = dependencies(e, cp)
        cp.start("HK-117")
        sales = await login_as(e, context, credentials, fixture["sales_key"], "membership", 1)
        await expect(e.page.locator("#main h1")).to_have_text("会员卡与续会")
        before = e.business_snapshot("before_membership_own_customer_search")
        async with e.page.expect_response(lambda r: get_matches(r, "/api/flow/master/customers")
                and parse_qs(urlsplit(r.url).query).get("q") == [customer["name"]]) as pending:
            await e.fill('#filters [name="q"]', customer["name"], "查本人同次销售真实客户")
        response = await pending.value
        data = await response.json()
        require(response.status == 200 and any(r["id"] == customer["id"] for r in data["items"]), "原会员客户查询缺本轮本人来源")
        await e.click(f'#main [data-act="open"][data-route="membership/{customer["id"]}"]', "明确打开本人客户会员资料")
        await expect(e.page.locator('#main [data-act="open"][data-route="group/' + str(customer["id"]) + '"]')).to_have_count(2)
        await expect(e.page.locator("#main")).to_contain_text("先核对集团身份")
        e.business_unchanged(before, "after_membership_own_customer_search")
        service, local = await ready_member(e, context, credentials, fixture, "service", customer, group=True)
        require(local["identity_id"] is None and local["member"] is None, "首关联读取已继承旧开通")
        async with e.page.expect_response(lambda r: get_matches(r, "/api/group/identities")) as matches:
            await e.click('#main [data-act="group-link"]', "本人明确核对独立客户身份")
        require((await matches.value).status == 200, "原完整电话身份核对失败")
        await expect(e.page.locator("#modal-title")).to_have_text("核对客户身份")
        await select_value(e, '#modal [name="identity"]', "new", "明确新建独立身份，不凭同电话合并")
        await checkbox(e, '#modal [name="confirmed"]', True, "本人已核对客户身份与确认结果")
        protection = Guard(e, "membership_identity_link", actor=service["id"], customer=customer["id"],
                           append={"group_identities", "group_identity_links", "group_events", "group_receipts"})
        body, request, _, linked = await submit(e, "/api/group/identities/link", "/api/group/members", status=201)
        identity = one(e, "group_identities", body["identity_id"])
        link = one(e, "group_identity_links", body["link_id"])
        require(request == {"request_id": request["request_id"], "kind": "customer", "local_id": customer["id"], "identity_id": None}
                and identity["kind"] == "customer" and identity["name"] == customer["name"] and identity["created_by"] == service["id"]
                and identity["search_key"] == re.sub(r"[\s()+-]", "", customer["phone"])
                and link["local_kind"] == "customer" and link["local_id"] == customer["id"]
                and link["identity_id"] == identity["id"] and link["confirmed_by"] == service["id"],
                "身份明确关联UI/API/DB不符")
        linked.update(receipt=group_receipt(e, request, service, "identity_link",
            {"kind": "customer", "local_id": customer["id"], "identity_id": None, "identifier": ""}, body),
            protection=exact_appends(protection, {"group_identities": 1, "group_identity_links": 1,
                                                "group_events": 1, "group_receipts": 1}),
            group_event=group_event(e, protection, "identity_link", detail={"identity_id": identity["id"],
                                                                        "kind": "customer", "local_id": customer["id"]}))
        await expect(e.page.locator('#main [data-act="group-issue"]')).to_be_visible()
        await e.click('#main [data-act="group-issue"]', "开通本客户原集团会员")
        await expect(e.page.locator("#modal-title")).to_have_text("开通集团会员")
        protection = Guard(e, "membership_issue", actor=service["id"], append={"group_members", "group_events", "group_receipts"})
        body, request, _, issued = await submit(e, "/api/group/members", "/api/group/members", status=201)
        member_id = body["member"]["id"]
        member = one(e, "group_members", member_id)
        require(request == {"request_id": request["request_id"], "identity_id": identity["id"]}
                and member["identity_id"] == identity["id"] and member["balance_cents"] == member["reserved_cents"] == 0
                and member["active"] == 1 and not member_facts(e, member_id)["cards"], "开通误产生发卡或资金")
        issued.update(receipt=group_receipt(e, request, service, "issue", {"identity_id": identity["id"]}, body),
                      protection=exact_appends(protection, {"group_members": 1, "group_events": 1, "group_receipts": 1}),
                      group_event=group_event(e, protection, "issue", member_id=member_id, detail={"identity_id": identity["id"]}))
        _, own = await ready_member(e, context, credentials, fixture, "sales", customer)
        require(own["member"]["id"] == member_id and own["cards"] == [] and own["periods"] == [], "本人原会员资料与开通结果不一致")
        benefit_read = await separate_benefits(e, customer, member_id)
        await cp.passed({"customer_id": customer["id"], "owner_id": sales["id"], "identity": identity, "link": link,
                         "member": member, "native_link": linked, "native_issue": issued,
                         "separate_benefits": benefit_read, "opening_has_no_card_money_or_period": True})

        cp.start("HK-128")
        issue_case, issue_create = await create_order(e, context, credentials, fixture, customer, member_id, "card_issue", "本次客户明确申请首次会员识别卡")
        _, issue_execute = await execute_order(e, context, credentials, fixture, issue_case, "card_issue", token)
        cards = member_facts(e, member_id)["cards"]
        require(len(cards) == 1 and cards[0]["generation"] == 1 and cards[0]["status"] == "active" and cards[0]["previous_id"] is None
                and cards[0]["case_id"] == issue_case and cards[0]["issuer_store_id"] == 1, "首卡代次/原单不正确")
        original_card = cards[0]
        await ready_member(e, context, credentials, fixture, "service", customer)
        first_lookup = await lookup_card(e, original_card, customer, valid=True)
        await cp.passed({"case_id": issue_case, "native_create": issue_create, "native_execute": issue_execute,
                         "original_card": original_card, "lookup": first_lookup, "principal_unchanged": True})

        cp.start("HK-118")
        loss_case, loss_create = await create_order(e, context, credentials, fixture, customer, member_id, "card_loss", "客户本人确认该原识别卡遗失", card_id=original_card["id"])
        _, loss_execute = await execute_order(e, context, credentials, fixture, loss_case, "card_loss", token, original_card=original_card)
        lost = one(e, "membership_cards", original_card["id"])
        require(lost["status"] == "lost" and lost["number"] == original_card["number"], "挂失改写原卡号或未生效")
        await ready_member(e, context, credentials, fixture, "service", customer)
        lost_lookup = await lookup_card(e, lost, customer, valid=False)
        replacement_case, replacement_create = await create_order(e, context, credentials, fixture, customer, member_id, "card_replace", "本人核对原挂失卡后申请独立换补", card_id=lost["id"])
        _, replacement_execute = await execute_order(e, context, credentials, fixture, replacement_case, "card_replace", token, original_card=lost)
        cards = member_facts(e, member_id)["cards"]
        new = [r for r in cards if r["id"] != original_card["id"]]
        require(len(cards) == 2 and len(new) == 1 and new[0]["generation"] == 2 and new[0]["status"] == "active"
                and new[0]["previous_id"] == original_card["id"] and new[0]["number"] != original_card["number"]
                and new[0]["case_id"] == replacement_case and one(e, "membership_cards", original_card["id"])["status"] == "replaced",
                "换补未保留旧卡或生成正确新代次")
        active_card = new[0]
        await ready_member(e, context, credentials, fixture, "service", customer)
        replacement_lookup = await lookup_card(e, active_card, customer, valid=True)
        obsolete_lookup = await lookup_card(e, original_card, customer, valid=False)
        require(member_facts(e, member_id)["member"]["balance_cents"] == 0, "识别卡办理制造本金")
        await cp.passed({"loss_case_id": loss_case, "replacement_case_id": replacement_case, "original_card_id": original_card["id"],
                         "active_card": active_card, "native_loss": {"create": loss_create, "execute": loss_execute},
                         "native_replacement": {"create": replacement_create, "execute": replacement_execute},
                         "actual_lookups": [lost_lookup, replacement_lookup, obsolete_lookup], "principal_period_benefits_unchanged": True})

        cp.start("HK-089")
        topup_case, topup_create = await create_order(e, context, credentials, fixture, customer, member_id, "topup", "本次独立本金充值100.00元，不附赠品")
        _, topup_execute = await execute_order(e, context, credentials, fixture, topup_case, "topup", token, account=account)
        f = member_facts(e, member_id)
        require(len(f["entries"]) == 1 and f["entries"][0]["purpose"] == "topup" and f["entries"][0]["amount_cents"] == 10000
                and f["entries"][0]["account_id"] == account["id"] and f["entries"][0]["case_id"] == topup_case
                and f["member"]["balance_cents"] == 10000 and f["member"]["reserved_cents"] == 0, "原实收本金/唯一来源不一致")
        topup = f["entries"][0]
        cash = one(e, "cash_entries", topup["cash_id"])
        require(cash["direction"] == "in" and cash["category"] == "group_member_topup" and cash["amount_cents"] == 10000
                and cash["account"] == account["name"] and cash["voucher_no"] == topup["reference"]
                and cash["counterparty"] == customer["name"] and cash["approval_state"] == "approved"
                and cash["payment_method"] == ("cash" if account["account_type"] == "cash" else "bank")
                and cash["created_by"] == e.manifest["users"][fixture["finance_key"]]["id"], "原本金现金不对应实际本店财务")
        settlement = [r for r in rows(e, "group_settlement_entries") if r["entry_id"] == topup["id"]]
        require({r["side"]: r["amount_cents"] for r in settlement} == {"center": 10000, "store": -10000}, "原本金内部往来非等额双边")
        await ready_member(e, context, credentials, fixture, "finance", customer, group=True)
        await expect(e.page.locator("#main .kpis")).to_contain_text("100.00")
        cp.partial("HK-124", {"ordinary_principal_case_id": topup_case, "topup_entry_id": topup["id"], "cash_id": cash["id"], "amount_cents": 10000})
        await cp.passed({"case_id": topup_case, "native_create": topup_create, "native_execute": topup_execute,
                         "entry": topup, "cash": cash, "settlements": settlement, "principal_balance_cents": 10000})

        cp.start("HK-094")
        refund, requested = await group_action(e, context, credentials, fixture, customer, member_id, "refund_request", topup, topup_case, token, account)
        require(refund["original_id"] == topup["id"] and refund["approved_by"] is None, "原申请不绑定唯一充值或提前批准")
        refund, approved = await group_action(e, context, credentials, fixture, customer, member_id, "refund_approve", refund, topup_case, token, account)
        refund, executed = await group_action(e, context, credentials, fixture, customer, member_id, "refund", refund, topup_case, token, account)
        refund_entry = one(e, "group_entries", refund["executed_entry_id"])
        refund_cash = one(e, "cash_entries", refund_entry["cash_id"])
        require(refund_entry["purpose"] == "refund" and refund_entry["amount_cents"] == -4000
                and refund_entry["original_id"] == topup["id"] and refund_entry["case_id"] == topup_case
                and refund_entry["account_id"] == account["id"] and refund_cash["direction"] == "out"
                and refund_cash["category"] == "group_member_refund" and refund_cash["amount_cents"] == 4000
                and refund_cash["account"] == cash["account"] and refund_cash["voucher_no"] == refund_entry["reference"]
                and refund_cash["counterparty"] == customer["name"] and refund_cash["approval_state"] == "approved"
                and refund_cash["payment_method"] == cash["payment_method"]
                and refund_entry["actor_id"] == refund_cash["created_by"] == refund["closed_by"] == e.manifest["users"][fixture["finance_key"]]["id"],
                "实际退款不是原款、原账户、本次财务或正确负账")
        require(one(e, "group_entries", topup["id"]) == topup and one(e, "cash_entries", cash["id"]) == cash,
                "实际退款覆盖原充值或原现金")
        require(member_facts(e, member_id)["cards"] == cards, "充值退款修改识别卡历史")
        settlement_refund = [r for r in rows(e, "group_settlement_entries") if r["entry_id"] == refund_entry["id"]]
        require({r["side"]: r["amount_cents"] for r in settlement_refund} == {"center": -4000, "store": 4000}, "原退款内部往来不守恒")
        f = member_facts(e, member_id)
        require(len(f["entries"]) == 2 and len(f["refunds"]) == 1 and f["member"]["balance_cents"] == 6000
                and f["member"]["reserved_cents"] == 0, "原款完成后本金净额、占额或记录数错误")
        source_tasks = [r for r in rows(e, "flow_tasks") if r["case_id"] == topup_case]
        require(all(r["status"] == "done" for r in source_tasks), "原本金及退款任务未完成")
        await expect(e.page.locator("#main .kpis")).to_contain_text("60.00")
        before = e.business_snapshot("before_final_membership_readonly_refresh")
        async with e.page.expect_response(lambda r: get_matches(r, f"/api/group/members/{member_id}")) as pending:
            e.action("navigate", "原本金结果真实刷新")
            await e.page.reload(wait_until="domcontentloaded")
        detail = await (await pending.value).json()
        require(detail["member"]["balance_cents"] == 6000 and detail["member"]["reserved_cents"] == 0
                and {r["id"] for r in detail["entries"]} == {topup["id"], refund_entry["id"]}, "刷新原账本金和来源错误")
        await expect(e.page.locator("#main .kpis")).to_contain_text("60.00")
        e.business_unchanged(before, "after_final_membership_readonly_refresh")
        cp.partial("HK-125", {"ordinary_refund_request_id": refund["id"], "original_topup_entry_id": topup["id"],
                   "refund_entry_id": refund_entry["id"], "refund_cash_id": refund_cash["id"], "amount_cents": 4000})
        await cp.passed({"case_id": topup_case, "request": refund, "native_request": requested, "native_approve": approved,
                         "native_refund": executed, "refund_entry": refund_entry, "refund_cash": refund_cash,
                         "refund_settlements": settlement_refund, "final_member": f["member"], "refresh_business_unchanged": True})
        cp.finish({"customer_id": customer["id"], "identity_id": identity["id"], "identity_link_id": link["id"], "member_id": member_id,
                   "card_issue_case_id": issue_case, "original_card_id": original_card["id"], "card_loss_case_id": loss_case,
                   "card_replace_case_id": replacement_case, "active_card_id": active_card["id"], "topup_case_id": topup_case,
                   "topup_entry_id": topup["id"], "topup_cash_id": cash["id"], "account_id": account["id"],
                   "refund_request_id": refund["id"], "refund_entry_id": refund_entry["id"], "refund_cash_id": refund_cash["id"]})
    except Exception as error:
        cp.failed(error)
        raise


MEMBERSHIP_SCENARIOS = ((SCENARIO, membership_business, 420),)
