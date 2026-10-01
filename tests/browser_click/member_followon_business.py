"""Unregistered same-run recharge bundle, coupon and actual retail consumption.

Only original native employee forms write. Database access is SELECT; credentials,
files and evidence stay in the external mirror. No centre payment is invented.
"""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import uuid

from playwright.async_api import expect

from sales_business import employee_choice, login_as, require
from sales_order_business import checkpoint_evidence, fixed_dependency, fen_text
from vehicle_purchase_business import checkbox, live_choice, select_value, rejected_submit
from finance_business import get_match, submit, original_form
from membership_business import group_receipt

SCENARIO = "member-followon-hk123-124-125-129-130-132"
MEMBERSHIP = "membership-hk117-128-118-089-094"
MATERIAL = "materials-hk069-045-054-083-070-072-073-051-061"
MASTERS = "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187"
BENEFIT = "/api/group/benefits"
BUNDLE = "/api/recharge-bundles"
RG = "/api/retail-group"
RETAIL = "/api/retail"
REQUIREMENTS = (("HK-123", "会员卡充值套餐设置"), ("HK-124", "会员储值卡充值"),
                ("HK-125", "会员储值卡退款请求"), ("HK-129", "消费券类型"),
                ("HK-130", "消费券生成"), ("HK-132", "消费券信息查询"))
VERSION = {"version", "updated_at"}
CASE = VERSION | {"data", "state", "cost_cents", "completed_date"}
TASK = VERSION | {"status", "done_by", "done_at"}
MEMBER = VERSION | {"balance_cents", "reserved_cents"}
WALLET = VERSION | {"balance_units", "reserved_units"}
FLOW = {"flow_events": 1, "audit_logs": 1}
BUNDLE_EVENT = {**FLOW, "group_events": 1, "group_receipts": 1}
TABLES = {
    "flow_cases", "flow_tasks", "flow_events", "audit_logs", "flow_files", "file_security", "file_scan_events",
    "flow_accounts", "cash_entries", "flow_request_receipts", "flow_items", "flow_stock_moves",
    "group_members", "group_entries", "group_reservations", "group_payment_links", "group_settlement_entries",
    "group_events", "group_receipts", "benefit_rules", "benefit_wallets", "benefit_entries",
    "benefit_reservations", "benefit_payment_links", "benefit_settlements", "benefit_refunds",
    "membership_orders", "membership_events", "membership_points_claims",
    "recharge_bundle_rules", "recharge_bundle_rule_components", "recharge_bundle_orders",
    "recharge_bundle_purchases", "recharge_bundle_components", "recharge_bundle_refunds",
    "recharge_bundle_refund_components", "recharge_bundle_refund_postings", "retail_orders", "retail_lines",
    "retail_reservations", "retail_dispatches", "retail_group_eligibility", "retail_group_scopes",
    "retail_group_decisions", "retail_group_wallets", "retail_group_plans", "retail_group_tenders",
    "retail_group_units", "retail_group_allocations", "retail_group_reservations", "retail_group_captures",
    "warehouse_allocations", "warehouse_allocation_lines", "warehouse_balances", "warehouse_entries",
}
READ_TABLES = TABLES | {"flow_customers", "membership_cards", "membership_periods", "group_identities",
                       "group_identity_links", "group_refund_requests", "master_work_items", "master_locations",
                       "master_warehouses", "warehouse_enrollments", "master_item_profiles", "retail_payments", "flow_payment_links"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pk(table):
    return "file_id" if table == "file_security" else "id"


def rows(e, table):
    require(table in READ_TABLES, "未审原表：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {pk(table)}")


def one(e, table, key):
    require(table in READ_TABLES and type(key) is int and key > 0, "未审原来源或无精确ID")
    found = e.db.rows(f"SELECT * FROM {table} WHERE {pk(table)}=?", (key,))
    require(len(found) == 1, "本轮原记录缺失/重复：" + table + "/" + str(key))
    return found[0]


def subset(e, table, field, value):
    require(table in READ_TABLES and field in {"case_id", "member_id", "wallet_id", "rule_id", "bundle_rule_id",
        "purchase_id", "refund_id", "plan_id", "tender_id", "unit_id", "entry_id", "eligibility_id", "item_id", "allocation_id"}, "未审关联")
    return e.db.rows(f"SELECT * FROM {table} WHERE {field}=? ORDER BY {pk(table)}", (value,))


def json_row(row, *fields):
    value = dict(row)
    for field in fields:
        value[field] = json.loads(value[field])
    require(not any(isinstance(v, bytes) for v in value.values()), "原件正文不可进入JSON证据")
    return value


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(raw)
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title in REQUIREMENTS:
            require(catalog[key]["title"] == title and catalog[key]["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in catalog[key]["acceptance_checks"]), key + " 原合同不匹配")
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [r[0] for r in REQUIREMENTS],
            "complete": False, "passed": False, "execution": "native_browser_original_forms",
            "source_contract_sha256": self.digest, "candidate_sha256": sha(Path(__file__).read_bytes()),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "full_193_business_acceptance": False, "full_registered_suite_complete": False, "business_accepted": False,
            "human_acceptance": "pending", "requirements": [{"id": key, "title": title, "status": "not_tested",
                "business_accepted": False, "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested", "evidence": {}}]}
                for key, title in REQUIREMENTS],
            "partial_requirements": [{"id": "HK-131", "status": "not_tested", "acceptance_check_submitted": False,
                                      "unexecuted_scope": ["原独立赠送订单；组合自动赠品不能代替"]}],
            "conditional_checks": [{"status": "not_tested", "scope": scope} for scope in
                ("消费积分、欠分、会员等级会期及会员价", "mixed套餐购买核销退款", "精品部分退回与restore、到期及跨店",
                 "现金混合、安装、并发库存不足、全部权益异常", "真实模型、PostgreSQL、员工验收及生产门槛")],
            "conditions": {"synthetic_inputs_only": True, "bank_acceptance": False, "centre_payment": False,
                           "file_scan": "structure_only_not_clamav", "new_fixture_results": False, "new_roles": 0}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active.update(status="running", evidence_action_start=len(self.e.actions))
        self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    def note(self, value):
        json.dumps(value, ensure_ascii=False)
        self.active["acceptance_checks"][0].setdefault("steps", []).append(value)
        self.save()

    async def passed(self, value):
        json.dumps(value, ensure_ascii=False)
        self.active["acceptance_checks"][0].update(status="passed", evidence=value)
        self.active.update(status="passed", evidence_action_end=len(self.e.actions))
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active = None
        self.save()

    def failed(self, error):
        for row in self.report["requirements"]:
            if row["status"] == "running":
                status = "failed" if row is self.active else "partial"
                row["status"] = status
                row["acceptance_checks"][0].update(status=status, error=self.e.scrub(error))
        self.report.update(error=self.e.scrub(error), failed_requirement=self.active["id"] if self.active else "same_run_source_or_final_guard")
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "会员六项未完整实际执行")
        self.report.update(complete=True, passed=True, executed_requirements=6, passed_requirements=6,
                           member_followon_sources=sources, report_sources=sources)
        self.save()
        self.e.observe("member_followon_original_checkpoint", {"path": str(self.path), "passed_checks": 6,
                       "full_193_business_acceptance": False, "human_acceptance": "pending"})


class Guard:
    """Protect all tables/old rows; append counts and source IDs belong to one action."""
    def __init__(self, e, label, actor, *, append, update=None, cases=(), member=None, customer=None,
                 new_kind=None, wallets=(), item=None):
        self.e, self.label, self.actor = e, label, actor
        self.append, self.update = dict(append), update or {}
        self.cases, self.wallets = set(cases), set(wallets)
        self.member, self.customer, self.new_kind, self.item = member, customer, new_kind, item
        require(self.append.keys() | self.update.keys() <= TABLES, "会员后继守卫超出审阅表")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.append.keys() | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.old.keys(), "办理改变无关原表：" + str(sorted(changed)))
        added = {t: [r for r in rows(self.e, t) if r[pk(t)] not in {x[pk(t)] for x in old}] for t, old in self.old.items()}
        for table, new in added.items():
            count = self.append.get(table, 0)
            low, high = count if isinstance(count, tuple) else (count, count)
            require(low <= len(new) <= high, "本次新增数错误：" + table + "/" + str(len(new)))
        new_cases = added.get("flow_cases", [])
        require(not new_cases or len(new_cases) == 1 and new_cases[0]["kind"] == self.new_kind
                and new_cases[0]["flow_version"] == 2 and new_cases[0]["customer_id"] == self.customer
                and new_cases[0]["created_by"] == new_cases[0]["owner_id"] == self.actor["id"], "新增原单岗位/客户/类型不匹配")
        cases = self.cases | {r["id"] for r in new_cases}
        wallets = self.wallets | {r["id"] for r in added.get("benefit_wallets", [])}
        modified = {}
        for table, old in self.old.items():
            current = {r[pk(table)]: r for r in rows(self.e, table)}
            modified[table] = []
            for prior in old:
                key = prior[pk(table)]
                require(key in current, "删除旧原行：" + table)
                columns = {k for k in prior if prior[k] != current[key][k]}
                require(columns <= self.update.get(table, {}).get(key, set()),
                        "覆盖非授权原列：" + table + "/" + str(key) + "/" + str(sorted(columns)))
                if table == "flow_cases" and "data" in columns:
                    prior_data, current_data = json.loads(prior["data"]), json.loads(current[key]["data"])
                    require(all(current_data.get(k) == v for k, v in prior_data.items()), "本批正向步骤覆盖原单既有data事实")
                if columns:
                    modified[table].append({"id": key, "columns": sorted(columns)})
            for row in added[table]:
                for field in ("store_id", "issuer_store_id"):
                    if field in row:
                        require(row[field] == 1, "新增事实串门店：" + table)
                if "case_id" in row:
                    require(row["case_id"] in cases, "新增事实串原单：" + table)
                if "source_case_id" in row:
                    require(row["source_case_id"] in cases, "新增钱包串来源单")
                if "member_id" in row and row["member_id"] is not None:
                    require(row["member_id"] == self.member, "新增事实串会员：" + table)
                if "wallet_id" in row and row["wallet_id"] is not None:
                    require(row["wallet_id"] in wallets, "新增事实串批次：" + table)
                if "item_id" in row:
                    require(row["item_id"] == self.item, "新增事实串物资：" + table)
                for field in ("actor_id", "created_by", "requested_by"):
                    if field in row:
                        require(row[field] == self.actor["id"], "新增事实借身份：" + table)
                if table == "audit_logs":
                    require(row["entity_type"] == "flow" and row["entity_id"] in cases, "原审计串实体")
                if table == "group_events":
                    rule_event = self.label.startswith("benefit_rule_")
                    require(row["member_id"] == (None if rule_event else self.member)
                            and (rule_event and row["action"] == "benefit_rule" or row["action"] in {r["action"] for r in added.get("flow_events", [])}),
                            "原集团事件动作/会员不匹配")
                if table == "membership_points_claims":
                    require(row["rule_id"] is None and row["member_id"] == self.member, "无会期不得编造消费积分规则")
        self.added = added
        value = {"label": self.label, "changed_tables": sorted(changed),
                 "appended_ids": {t: [r[pk(t)] for r in v] for t, v in added.items()},
                 "updated_columns": modified, "expected_counts": self.append,
                 "all_other_tables_unchanged": True, "all_other_old_rows_unchanged": True}
        self.e.observe("member_followon_original_guard", value)
        return value


def updates(e, case_ids=(), *, member=None, wallets=(), account=None):
    result = {"flow_cases": {key: CASE for key in case_ids},
              "flow_tasks": {r["id"]: TASK for key in case_ids for r in subset(e, "flow_tasks", "case_id", key)}}
    if member:
        result["group_members"] = {member: MEMBER}
    if wallets:
        result["benefit_wallets"] = {key: WALLET for key in wallets}
    if account:
        result["flow_accounts"] = {account: VERSION}
    return {k: v for k, v in result.items() if v}


def task(e, case_id, key):
    found = [r for r in subset(e, "flow_tasks", "case_id", case_id) if r["key"] == key and r["status"] == "open"]
    require(len(found) == 1, "当前原待办不唯一：" + key)
    return found[0]


def event(e, guard, case_id, action):
    native, audit = guard.added["flow_events"], guard.added["audit_logs"]
    require(len(native) == len(audit) == 1 and native[0]["case_id"] == audit[0]["entity_id"] == case_id
            and native[0]["actor_id"] == audit[0]["actor_id"] == guard.actor["id"]
            and native[0]["action"] == action and audit[0]["action"] == "flow_" + action, "原事件与审计不对应本人动作")
    return {"event_id": native[0]["id"], "audit_id": audit[0]["id"], "action": action, "detail": json.loads(native[0]["detail"])}


async def submit_created(e, path, prefix, *, status, body_key):
    """Bind actual new entity GET to the unique POST ID, including render races."""
    responses, expected_path = [], None
    matching = asyncio.get_running_loop().create_future()

    def observe(response):
        if get_match(response, prefix):
            responses.append(response)
            if urlsplit(response.url).path == expected_path and not matching.done():
                matching.set_result(response)

    e.page.on("response", observe)
    try:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click('#modal form button[type="submit"]', "本人核对后提交原新单表单")
        response = await pending.value
        body = await response.json()
        identifier = body
        for key in body_key:
            identifier = identifier.get(key) if isinstance(identifier, dict) else None
        require(response.status == status and type(identifier) is int and identifier > 0,
                "原新单失败：" + str(response.status) + "/" + e.scrub(body.get("detail", "")))
        expected_path = prefix + str(identifier)
        for read in responses:
            if urlsplit(read.url).path == expected_path and not matching.done():
                matching.set_result(read)
        read = await asyncio.wait_for(matching, 30)
        displayed = await read.json()
        displayed_id = displayed.get("case", displayed).get("id")
        require(read.status == 200 and displayed_id == identifier, "实际原新单GET与提交ID不一致")
        request = response.request.post_data_json
        headers = await response.request.all_headers()
        require(isinstance(request, dict) and len(request.get("request_id", "")) >= 16
                and headers.get("x-store-id") == "1" and headers.get("x-app-request") == "1"
                and headers.get("cookie") and headers.get("x-csrf-token"), "原新单Cookie/CSRF/当前店不完整")
        await expect(e.page.locator("#modal")).not_to_be_visible()
        await expect(e.page.locator("#main .notice.error")).to_have_count(0)
        meta = {"path": path, "status": status, "native_ui": True, "cookie_present": True, "csrf_present": True,
                "store_id": 1, "request_id_sha256": sha(request["request_id"].encode()),
                "created_entity_id": identifier, "render_get_path": expected_path, "render_get_status": read.status}
        e.observe("member_followon_native_new_entity", meta)
        return body, request, displayed, meta
    finally:
        e.page.remove_listener("response", observe)
        if not matching.done():
            matching.cancel()


async def read_as(e, context, credentials, fixture, role, route, path, heading):
    async with e.page.expect_response(lambda r: get_match(r, path)) as pending:
        actor = await login_as(e, context, credentials, fixture[role + "_key"], route, 1)
    response = await pending.value
    value = await response.json()
    require(response.status == 200, "本人原业务读取失败：" + path)
    await expect(e.page.locator("#main h1")).to_have_text(heading)
    return actor, value


async def responsible(e, context, credentials, fixture, case_id, key, role, member):
    target, current = e.manifest["users"][fixture[role + "_key"]], task(e, case_id, key)
    result = {"task_id": current["id"], "key": key, "target_id": target["id"], "handoff_needed": current["assignee_id"] != target["id"]}
    if result["handoff_needed"]:
        manager, view = await read_as(e, context, credentials, fixture, "manager", "case/" + str(case_id),
            "/api/flow/cases/" + str(case_id), one(e, "flow_cases", case_id)["title"])
        require(view["id"] == case_id, "待办交接读取串原单")
        button = f'#main [data-act="assign"][data-id="{current["id"]}"]'
        await expect(e.page.locator(button)).to_be_visible()
        await expect(e.page.locator(button)).to_be_enabled()
        await e.click(button, "主管明确将本次原待办交给已知本人")
        await employee_choice(e, target)
        reason = "本店已知员工本人核对这份会员原单及独立事实"
        await e.fill('#modal [name="reason"]', reason, "填写原交接依据")
        guard = Guard(e, "task_handoff_" + str(current["id"]), manager, append=FLOW,
            update={"flow_tasks": {current["id"]: VERSION | {"assignee_id"}}}, cases={case_id}, member=member)
        _, request, _, native = await submit(e, f'/api/flow/tasks/{current["id"]}/assign', f"/api/flow/cases/{case_id}")
        require(request == {"version": current["version"], "assignee_id": target["id"], "reason": reason}, "AssignInput不能猜填字段")
        result.update(native=native, guard=guard.finish(), event=event(e, guard, case_id, "reassign"))
    require(task(e, case_id, key)["assignee_id"] == target["id"]
            and (current["role"] == role or role == "admin"), "本人未接手原岗位待办")
    return result


async def upload(e, actor, case_id, member, path, category, label, token):
    directory = e.directory / "synthetic-inputs"
    directory.mkdir(exist_ok=True)
    file = directory / (label + "-" + token + ".txt")
    content = ("合成浏览器原输入，不表示真实公司款项。\n用途=" + label + "；原单=" + str(case_id) + "\n" + uuid.uuid4().hex).encode("utf-8")
    file.write_bytes(content)
    await e.click('#main [data-act="upload"]', "员工上传本单本次独立合成原件")
    await expect(e.page.locator("#modal-title")).to_have_text("上传业务文件")
    await select_value(e, '#modal [name="category"]', category, "选择原凭据类别")
    e.action("select_file", "实际选择仓库外合成文件", name=file.name, sha256=sha(content))
    await e.page.locator('#modal [name="file"]').set_input_files(str(file))
    guard = Guard(e, "upload_" + label, actor, append={**FLOW, "flow_files": 1, "file_security": 1, "file_scan_events": 1},
                  cases={case_id}, member=member)
    body, _, _, native = await submit(e, f"/api/flow/cases/{case_id}/files", path, multipart=True)
    asset = one(e, "flow_files", body["id"])
    blob = asset.pop("content")
    require(isinstance(blob, bytes) and blob == content and len(blob) == asset["size"] and sha(blob) == asset["sha256"]
            and asset["created_by"] == actor["id"] and asset["case_id"] == case_id and asset["category"] == category
            and not asset["generated"] and body["security"]["can_use"], "所选原件字节/来源不匹配")
    security = one(e, "file_security", asset["id"])
    scans = e.db.rows("SELECT * FROM file_scan_events WHERE file_id=? ORDER BY id", (asset["id"],))
    require(len(scans) == 1 and scans[0]["state"] == security["state"] == "structure_only"
            and scans[0]["sha256"] == asset["sha256"] and scans[0]["size"] == asset["size"], "原结构扫描事实不完整")
    await expect(e.page.locator("#main .filerecord").filter(has_text=file.name)).to_have_count(1)
    return {"file": asset, "stored_blob": {"length": len(blob), "sha256": sha(blob)}, "native": native,
            "guard": guard.finish(), "event": event(e, guard, case_id, "upload"), "clamav_acceptance": False}


async def choose_file(e, proof, category="evidence"):
    labels = {"evidence": "业务凭据", "authorization": "客户授权", "receipt": "收退款凭据"}
    require(proof["file"]["category"] == category, "原件类别不匹配")
    await live_choice(e, "evidence_id", proof["file"]["name"], proof["file"]["name"] + " · " + labels[category], expected_value=proof["file"]["id"])


def dependencies(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "仅允许外部新合成实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "DB不是同轮外部runtime")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance.get("snapshot_stable") is True, "源快照不稳定")
    for name in ("member_followon_business.py", "membership_business.py", "material_business.py", "master_data_business.py",
                 "finance_business.py", "sales_business.py", "sales_order_business.py", "vehicle_purchase_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name).read_bytes()), "脚本并非同轮指纹：" + name)
    prior, materials, masters = [fixed_dependency(e, cp, name) for name in (MEMBERSHIP, MATERIAL, MASTERS)]
    source = prior["membership_sources"]
    for key in ("customer_id", "member_id", "active_card_id", "topup_entry_id", "refund_entry_id", "account_id"):
        require(type(source.get(key)) is int and source[key] > 0, "缺有限会员前序：" + key)
    partial = {r["id"]: r for r in prior["partial_requirements"]}
    require(partial["HK-124"]["status"] == partial["HK-125"]["status"] == "partial"
            and partial["HK-124"]["evidence"]["topup_entry_id"] == source["topup_entry_id"]
            and partial["HK-125"]["evidence"]["refund_entry_id"] == source["refund_entry_id"], "普通本金原partial原件缺失")
    customer, member, account = [one(e, t, source[k]) for t, k in
        (("flow_customers", "customer_id"), ("group_members", "member_id"), ("flow_accounts", "account_id"))]
    original, returned = one(e, "group_entries", source["topup_entry_id"]), one(e, "group_entries", source["refund_entry_id"])
    require(member["balance_cents"] == 6000 and member["reserved_cents"] == 0 and member["active"] == 1
            and original["amount_cents"] == 10000 and returned["amount_cents"] == -4000
            and returned["original_id"] == original["id"] and original["cash_id"] == source["topup_cash_id"]
            and returned["cash_id"] == source["refund_cash_id"] and returned["account_id"] == original["account_id"] == account["id"], "普通原款与当前本金不是同轮事实")
    for entry, direction, amount in ((original, "in", 10000), (returned, "out", 4000)):
        cash = one(e, "cash_entries", entry["cash_id"])
        require(cash["direction"] == direction and cash["amount_cents"] == amount and cash["account"] == account["name"], "原partial实际现金不符")
    require(one(e, "membership_cards", source["active_card_id"])["status"] == "active"
            and not subset(e, "membership_periods", "member_id", member["id"])
            and not subset(e, "benefit_wallets", "member_id", member["id"]), "会期/权益不是本批明确初始来源")
    primary = materials["material_sources"]["primary"]
    item, enrollment, location = one(e, "flow_items", primary["item_id"]), one(e, "warehouse_enrollments", primary["enrollment_id"]), one(e, "master_locations", primary["source_location_id"])
    warehouse = one(e, "master_warehouses", primary["warehouse_id"])
    balances = subset(e, "warehouse_balances", "item_id", item["id"])
    source_balances = [b for b in balances if b["location_id"] == location["id"] and b["transit_case_id"] is None]
    require(item["active"] == 1 and item["quantity_milli"] >= 1000 and enrollment["item_id"] == item["id"]
            and warehouse["warehouse_type"] == "materials" and warehouse["active"] == location["active"] == 1
            and location["warehouse_id"] == warehouse["id"] and location["id"] in primary["location_ids"]
            and len(source_balances) == 1 and source_balances[0]["quantity_milli"] >= 1000, "当前真实领料位不足，不能借旧快照")
    work = checkpoint_evidence(masters, "HK-175")["row"]
    require(one(e, "master_work_items", work["id"])["code"] == work["code"] and one(e, "master_work_items", work["id"])["active"] == 1, "同轮作业原代码失效")
    fixture = dict(e.manifest["business_fixtures"]["sales_order"])
    fixture["admin_key"] = "admin"
    for role in ("sales", "service", "finance", "inventory", "manager"):
        actor = e.manifest["users"][fixture[role + "_key"]]
        require(actor["role"] == role and len(e.db.rows("SELECT user_id FROM user_stores WHERE user_id=? AND store_id=1 AND role=?", (actor["id"], role))) == 1, "缺当前店真实岗位：" + role)
    require(e.manifest["users"]["admin"]["role"] == "admin" and fixture["store_id"] == customer["store_id"] == account["store_id"] == item["store_id"] == location["store_id"] == warehouse["store_id"] == 1
            and customer["owner_id"] == e.manifest["users"][fixture["sales_key"]]["id"] and account["active"] == 1, "前序串店/本人归属失效")
    require(not e.db.rows("SELECT id FROM business_entity_policies WHERE store_id=1"), "本批没有完整主体前序，不能绕过新策略")
    cp.report["source_preconditions"] = {"ordinary_membership": source, "ordinary_partial_evidence": {k: partial[k]["evidence"] for k in ("HK-124", "HK-125")},
        "primary": primary, "current_item": item, "source_balance": source_balances[0], "work": work,
        "customer": customer, "account": account, "provenance_sha256": sha((root / "provenance.json").read_bytes())}
    cp.save()
    return fixture, customer, member["id"], account, primary, work, source


async def benefit_read(e, context, credentials, fixture, customer, member, *, role="finance", wallet_ids=(), stage):
    path = BENEFIT + "/members"
    actor, _ = await read_as(e, context, credentials, fixture, role, "benefits/" + str(customer["id"]), path, "集团权益")
    before = e.business_snapshot("before_benefit_read_" + stage)
    async with e.page.expect_response(lambda r: get_match(r, path)
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as pending:
        e.action("navigate", "实际刷新原集团权益资料：" + stage)
        await e.page.reload(wait_until="domcontentloaded")
    response = await pending.value
    view = await response.json()
    db_member = one(e, "group_members", member)
    require(response.status == 200 and view["customer"]["id"] == customer["id"] and view["member"]["id"] == member
            and all(view["member"][k] == db_member[k] for k in ("balance_cents", "reserved_cents", "version")), "集团权益原会员事实不符")
    await expect(e.page.locator("#main h1")).to_have_text("集团权益")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(customer["name"])
    by_id = {r["id"]: r for r in view["wallets"]}
    facts = []
    for key in wallet_ids:
        wallet, shown = one(e, "benefit_wallets", key), by_id.get(key)
        require(shown and all(shown[k] == wallet[k] for k in ("id", "version", "member_id", "rule_id", "initial_units",
            "balance_units", "reserved_units", "source_kind", "expires_on")), "原权益批次余额/占用/期限不匹配")
        rule = json_row(one(e, "benefit_rules", wallet["rule_id"]), "allowed_store_ids")
        require(all(shown["rule"].get(k) == v for k, v in rule.items() if k not in {"created_at", "created_by"}), "原冻结券规则与DB不匹配")
        ui_row = e.page.locator("#main tr").filter(has_text=rule["name"]).filter(has_text=wallet["expires_on"])
        await expect(ui_row).to_have_count(1)
        await expect(ui_row).to_contain_text(f'{wallet["balance_units"] - wallet["reserved_units"]} / {wallet["reserved_units"]}')
        facts.append({"wallet": wallet, "rule": rule})
    for family, table in (("entries", "benefit_entries"), ("reservations", "benefit_reservations"), ("refunds", "benefit_refunds")):
        actual = [r for r in rows(e, table) if r["wallet_id"] in wallet_ids]
        displayed = {r["id"]: r for r in view[family]}
        for row in actual:
            require(row["id"] in displayed and all(row[k] == v for k, v in displayed[row["id"]].items()), "原权益明细API/DB不一致：" + family)
    e.business_unchanged(before, "after_benefit_read_" + stage)
    value = {"stage": stage, "customer_id": customer["id"], "member": db_member, "wallet_facts": facts,
             "displayed_source_ids": {k: [r["id"] for r in view[k]] for k in ("entries", "reservations", "refunds")},
             "native_refresh": True, "business_unchanged": True}
    await e.snapshot("benefits-" + stage)
    return actor, value


async def publish_benefit(e, context, credentials, fixture, customer, member, token, key, *, version=1):
    actor, _ = await read_as(e, context, credentials, fixture, "manager", "benefits/" + str(customer["id"]), BENEFIT + "/members", "集团权益")
    await e.click('#main [data-act="benefit-rule"]', "主管发布本次明确冻结权益版本")
    await expect(e.page.locator("#modal-title")).to_have_text("发布权益规则新版本")
    kind = "coupon" if key == "paid" else key
    credit = (600 if version == 2 else 500) if key == "paid" else 500 if key in {"coupon", "package"} else 1
    sale = (450 if version == 2 else 400) if key == "paid" else 0
    code, name = "MF-" + key + "-" + token, "本轮" + key + "权益" + token + "版本" + str(version)
    values = {"code": code, "name": name, "kind": kind, "allowed_store_ids": [1], "credit_cents_per_unit": credit,
        "settlement_cents_per_unit": sale, "sale_cents_per_unit": sale, "exchange_points_per_unit": 0,
        "refund_policy": "unused_before_expiry" if key == "paid" else "none", "discount_bearer": "service_store",
        "validity_days": 30, "service_code": fixture["work_code"] if key == "package" else ""}
    for field, value in (("code", code), ("name", name), ("stores", "1"), ("credit", fen_text(credit)),
                         ("settlement", fen_text(sale) if sale else "0"), ("sale", fen_text(sale) if sale else "0"),
                         ("exchange_points_per_unit", "0"), ("validity_days", "30"), ("service_code", values["service_code"])):
        await e.fill(f'#modal [name="{field}"]', value, "填写冻结权益字段：" + field)
    for field in ("kind", "refund_policy", "discount_bearer"):
        await select_value(e, f'#modal [name="{field}"]', values[field], "明确权益原枚举：" + field)
    guard = Guard(e, "benefit_rule_" + key + "_" + str(version), actor,
                  append={"benefit_rules": 1, "group_events": 1, "group_receipts": 1}, member=member)
    body, request, _, native = await submit(e, BENEFIT + "/rules", BENEFIT + "/rules", status=201)
    row = json_row(one(e, "benefit_rules", body["id"]), "allowed_store_ids")
    require(request == {"request_id": request["request_id"], "values": values}
            and all(row[k] == v for k, v in values.items()) and row["rule_version"] == version
            and row["created_by"] == actor["id"] and row["issuer_store_id"] == 1, "本次冻结权益规则值不符")
    protection = guard.finish()
    ge = guard.added["group_events"][0]
    require(ge["action"] == "benefit_rule" and ge["member_id"] is None and json.loads(ge["detail"]) == {"rule_id": row["id"]}, "规则原事件不符")
    native.update(guard=protection, receipt=group_receipt(e, request, actor, "benefit_rule", values, body), group_event_id=ge["id"], rule=row)
    await expect(e.page.locator("#main")).to_contain_text(name)
    return row, native


async def bundle_page(e, context, credentials, fixture, customer, role="service"):
    return await read_as(e, context, credentials, fixture, role, "recharge-bundles/" + str(customer["id"]), BUNDLE + "/purchases", "会员充值组合套餐")


async def bundle_create(e, context, credentials, fixture, customer, member, token, *, rule=None, purchase=None, rejected=False):
    actor, listing = await bundle_page(e, context, credentials, fixture, customer)
    purpose = "refund" if purchase else "purchase"
    selector = '#main [data-act="bundle-create"][data-key="' + purpose + '"]' + (f'[data-id="{purchase["id"]}"]' if purchase else "")
    await e.click(selector, "本人申请原组合" + purpose)
    await expect(e.page.locator("#modal-title")).to_have_text("申请原组合整份退款" if purchase else "申请购买充值组合")
    if rule:
        await select_value(e, '#modal [name="rule"]', f'{rule["name"]} · {rule["code"]} · 版本{rule["rule_version"]}', "明确本次当前已启用组合版本")
    await e.fill('#modal [name="shares"]', "2" if not purchase or rejected else "1", "填写实际完整份数")
    await checkbox(e, '#modal [name="terms_accepted"]', True, "已向客户说明并确认原完整份额退款条款")
    reason = "本次明确接受原完整份額与赠品回收条款" + token
    await e.fill('#modal [name="reason"]', reason, "填写本人明确的组合申请")
    values = {"shares": 2 if not purchase or rejected else 1, "terms_accepted": True,
              "purchase_id" if purchase else "rule_id": (purchase or rule)["id"]}
    if rejected:
        before = e.business_snapshot("before_insufficient_original_bundle_refund")
        native = await rejected_submit(e, BUNDLE + "/orders", 409, "可退整份不足")
        e.business_unchanged(before, "after_insufficient_original_bundle_refund")
        return None, {"native": native, "status": 409, "shares": 2, "business_unchanged": True, "dirty_form_explicitly_discarded": True}
    append = {**BUNDLE_EVENT, "flow_cases": 1, "flow_tasks": 1, "recharge_bundle_orders": 1}
    if purchase:
        append.update(recharge_bundle_refunds=1, recharge_bundle_refund_components=4)
    guard = Guard(e, "bundle_create_" + purpose, actor, append=append,
                  update={"group_members": {member: VERSION}}, member=member, customer=customer["id"], new_kind="recharge_bundle")
    body, request, shown, native = await submit_created(e, BUNDLE + "/orders", BUNDLE + "/orders/", status=201, body_key=("case", "id"))
    key = body["case"]["id"]
    order = subset(e, "recharge_bundle_orders", "case_id", key)
    require(request == {"request_id": request["request_id"], "customer_id": customer["id"], "purpose": purpose, "values": values, "reason": reason}
            and len(order) == 1 and json.loads(order[0]["values"]) == values and order[0]["status"] == "draft"
            and order[0]["member_id"] == member and shown["case"]["id"] == key and body["case"]["amount_cents"] == (5000 if purchase else 10000), "原组合新申请冻结份额/金额不符")
    native.update(guard=guard.finish(), event=event(e, guard, key, "bundle_create"),
                  receipt=group_receipt(e, request, actor, "bundle_create", {k: v for k, v in request.items() if k != "request_id"}, body),
                  order=json_row(order[0], "values"))
    return key, native


async def bundle_action(e, context, credentials, fixture, member, key, action, token, account, eligibility, wallet_ids=()):
    role = "manager" if action == "approve" else "finance" if action == "execute" else "service"
    handoff = await responsible(e, context, credentials, fixture, key, "bundle_review" if action == "approve" else "bundle_execute", role, member) if action != "cancel" else None
    actor, view = await read_as(e, context, credentials, fixture, role, "recharge-bundle-order/" + str(key), BUNDLE + f"/orders/{key}", "充值组合办理")
    proof = None
    if action != "cancel":
        proof = await upload(e, actor, key, member, BUNDLE + f"/orders/{key}", "receipt" if action == "execute" else "evidence", "bundle-" + str(key) + "-" + action, token)
    # Original upload refreshes the order; re-read current CAS facts, never the old view.
    case = one(e, "flow_cases", key)
    order = subset(e, "recharge_bundle_orders", "case_id", key)[0]
    db_member = one(e, "group_members", member)
    purpose = order["purpose"]
    title = "独立复核完整份额" if action == "approve" else "撤销并释放原占额" if action == "cancel" else "确认真实到账" if purpose == "purchase" else "确认原账户实际退款"
    await original_form(e, "bundle-action", action, title)
    reason = "本人核对本次原组合" + purpose + "和" + action + "的真实合成事实"
    await e.fill('#modal [name="reason"]', reason, "填写实际办理依据")
    values = {"reason": reason}
    if proof:
        await choose_file(e, proof, "receipt" if action == "execute" else "evidence")
        values["evidence_id"] = proof["file"]["id"]
    if action == "execute":
        await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
        reference = "MF-BUNDLE-" + str(key) + "-" + token
        await e.fill('#modal [name="reference"]', reference, "填写独立实际收退款凭证号")
        values.update(account_id=account["id"], reference=reference)
    permitted = updates(e, [key], member=member, wallets=wallet_ids, account=account["id"] if action == "execute" else None)
    permitted["recharge_bundle_orders"] = {order["id"]: VERSION | {"status", "approved_by"}}
    refund_rows = subset(e, "recharge_bundle_refunds", "case_id", key)
    if refund_rows:
        permitted["recharge_bundle_refunds"] = {refund_rows[0]["id"]: VERSION | {"status", "executed_entry_id"}}
    append = dict(BUNDLE_EVENT)
    if action == "approve":
        append["flow_tasks"] = 1
    if action == "execute":
        append.update(group_entries=1, group_settlement_entries=2, cash_entries=1)
        if purpose == "purchase":
            append.update(recharge_bundle_purchases=1, recharge_bundle_components=4, benefit_wallets=4, benefit_entries=4, retail_group_wallets=2)
            for ann in eligibility.values():
                if ann["eligibility"]["rule_id"] in {fixture["gift_bonus_rule"], fixture["gift_coupon_rule"]}:
                    permitted["flow_cases"][ann["case_id"]] = VERSION
        else:
            append.update(benefit_entries=4, recharge_bundle_refund_postings=4)
    guard = Guard(e, "bundle_" + action + "_" + str(key), actor, append=append, update=permitted,
                  cases={key} | set(permitted.get("flow_cases", {})), member=member, wallets=wallet_ids)
    body, request, shown, native = await submit(e, BUNDLE + f"/orders/{key}/actions/{action}", BUNDLE + f"/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": order["version"], "case_version": case["version"],
                       "member_version": db_member["version"], "values": values}, "原组合动作CAS/实际凭据不符")
    final = subset(e, "recharge_bundle_orders", "case_id", key)[0]
    expected_status = "approved" if action == "approve" else "cancelled" if action == "cancel" else "completed"
    require(final["status"] == expected_status and shown["order"]["status"] == expected_status and shown["case"]["version"] == one(e, "flow_cases", key)["version"], "组合办理状态与原GET不符")
    native.update(guard=guard.finish(), event=event(e, guard, key, "bundle_" + action), handoff=handoff, proof=proof,
        receipt=group_receipt(e, request, actor, "bundle:" + str(key) + ":" + action,
            {k: v for k, v in request.items() if k != "request_id"}, body))
    return body, native


def cash_fact(e, entry, direction, amount, category, account, actor):
    cash = one(e, "cash_entries", entry["cash_id"])
    require(cash["direction"] == direction and cash["amount_cents"] == amount and cash["category"] == category
            and cash["created_by"] == actor["id"] and cash["store_id"] == 1 and cash["account"] == account["name"]
            and cash["voucher_no"] == entry["reference"] and entry["account_id"] == account["id"]
            and cash["approval_state"] == "approved" and cash["payment_method"] == ("cash" if account["account_type"] == "cash" else "bank"), "原真实款项与账本、本人账户不一致")
    return cash


def paired(e, table, entry_id, amount):
    found = subset(e, table, "entry_id", entry_id)
    require({r["side"]: r["amount_cents"] for r in found} == ({"center": amount, "store": -amount} if amount else {}), "原非零内部双边往来不守恒")
    return found


def bundle_purchase_facts(e, key, rules, member, account, actor, eligibility):
    purchases = subset(e, "recharge_bundle_purchases", "case_id", key)
    require(len(purchases) == 1, "组合缺唯一原Purchase")
    purchase = purchases[0]
    principal = one(e, "group_entries", purchase["principal_entry_id"])
    require(purchase["shares"] == 2 and purchase["member_id"] == member and principal["purpose"] == "topup"
            and principal["amount_cents"] == 10000 and principal["case_id"] == key, "原全部实收未记通用本金")
    cash = cash_fact(e, principal, "in", 10000, "group_member_topup", account, actor)
    wallets, components, entries, bindings = {}, subset(e, "recharge_bundle_components", "purchase_id", purchase["id"]), [], []
    require(len(components) == 4, "组合未产生四独立赠品来源")
    for component in components:
        wallet = one(e, "benefit_wallets", component["wallet_id"])
        grant = one(e, "benefit_entries", component["grant_entry_id"])
        kind = next(k for k, r in rules.items() if r["id"] == wallet["rule_id"])
        amount = {"bonus": 400, "points": 200, "coupon": 2, "package": 2}[kind]
        require(wallet["source_kind"] == grant["purpose"] == "grant" and wallet["initial_units"] == wallet["balance_units"] == grant["units"] == amount
                and wallet["reserved_units"] == 0 and wallet["cash_id"] is None and grant["cash_id"] is None
                and wallet["source_case_id"] == grant["case_id"] == key and wallet["member_id"] == member, "赠品原批次/原grant不一致")
        wallets[kind] = wallet
        entries.append(grant)
        current = subset(e, "retail_group_wallets", "wallet_id", wallet["id"])
        if kind in {"bonus", "coupon"}:
            require(len(current) == 1 and current[0]["origin_id"] == grant["id"]
                    and current[0]["eligibility_id"] == eligibility[kind]["eligibility"]["id"]
                    and current[0]["decision_id"] == eligibility[kind]["decision"]["id"], "发行时未绑定原独立商品用途")
            bindings.extend(current)
        else:
            require(not current, "积分/旧次数赠品未授权本次精品用途")
    return {"purchase": purchase, "principal_entry": principal, "cash": cash, "settlements": paired(e, "group_settlement_entries", principal["id"], 10000),
            "components": components, "wallets": wallets, "grant_entries": entries, "retail_bindings": bindings}


async def paid_coupon(e, context, credentials, fixture, customer, member, rule, account, token, eligibility):
    service, _ = await read_as(e, context, credentials, fixture, "service", "membership/" + str(customer["id"]), "/api/membership/members", "会员卡与续会")
    await original_form(e, "membership-create", "purchase", "权益发行")
    await select_value(e, '#modal [name="rule"]', f'{rule["id"]} · {rule["name"]} · 版本{rule["rule_version"]}', "明确原付费券版本")
    await e.fill('#modal [name="units"]', "2", "客户明确购买两张原付费券")
    reason = "本次明确购买两张付费消费券，不替代零价赠品"
    await e.fill('#modal [name="reason"]', reason, "输入客户本次购买依据")
    values = {"action": "purchase", "rule_id": rule["id"], "units": 2}
    guard = Guard(e, "paid_coupon_create", service, append={**FLOW, "flow_cases": 1, "flow_tasks": 1,
        "membership_orders": 1, "membership_events": 1, "group_receipts": 1}, update={"group_members": {member: VERSION}},
        new_kind="membership", customer=customer["id"], member=member)
    body, request, shown, native = await submit_created(e, "/api/membership/orders", "/api/membership/orders/", status=201, body_key=("case", "id"))
    key = body["case"]["id"]
    require(request == {"request_id": request["request_id"], "customer_id": customer["id"], "purpose": "benefit_issue", "values": values, "reason": reason}
            and shown["case"]["amount_cents"] == 800, "付费券原申请不是本次两张800分")
    created = {"native": native, "guard": guard.finish(), "event": event(e, guard, key, "membership_create"),
        "receipt": group_receipt(e, request, service, "membership_create", {k: v for k, v in request.items() if k != "request_id"}, body)}
    handoff = await responsible(e, context, credentials, fixture, key, "membership_execute", "finance", member)
    actor, _ = await read_as(e, context, credentials, fixture, "finance", "membership-order/" + str(key), "/api/membership/orders/" + str(key), "会员业务办理")
    proof = await upload(e, actor, key, member, "/api/membership/orders/" + str(key), "evidence", "paid-coupon-actual-purchase", token)
    current_case = one(e, "flow_cases", key)
    order = subset(e, "membership_orders", "case_id", key)[0]
    prior_member = one(e, "group_members", member)
    await original_form(e, "membership-action", "execute", "确认实际办理")
    await choose_file(e, proof)
    await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
    reference = "MF-COUPON-IN-" + token
    reason = "本人实际收到两张原付费券款8元"
    await e.fill('#modal [name="reference"]', reference, "填写实际购买流水")
    await e.fill('#modal [name="reason"]', reason, "填写财务实际到账事实")
    execution = {"evidence_id": proof["file"]["id"], "reason": reason, "account_id": account["id"], "reference": reference}
    permitted = updates(e, [key], member=member, account=account["id"])
    permitted["flow_cases"][eligibility["case_id"]] = VERSION
    permitted["membership_orders"] = {order["id"]: VERSION | {"status"}}
    guard = Guard(e, "paid_coupon_execute", actor, append={"flow_events": 2, "audit_logs": 2, "group_receipts": 1, "group_events": 1,
        "membership_events": 1, "cash_entries": 1, "benefit_wallets": 1, "benefit_entries": 1, "benefit_settlements": 2, "retail_group_wallets": 1},
        update=permitted, cases={key, eligibility["case_id"]}, member=member)
    body, request, shown, meta = await submit(e, f"/api/membership/orders/{key}/actions/execute", f"/api/membership/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": order["version"], "case_version": current_case["version"],
        "member_version": prior_member["version"], "values": execution} and shown["order"]["status"] == "completed", "原付费券实际办理CAS不符")
    protection = guard.finish()
    wallets = [w for w in subset(e, "benefit_wallets", "member_id", member) if w["source_case_id"] == key]
    require(len(wallets) == 1, "购买未产生唯一付费券钱包")
    wallet = wallets[0]
    entries = subset(e, "benefit_entries", "wallet_id", wallet["id"])
    require(len(entries) == 1 and wallet["source_kind"] == entries[0]["purpose"] == "purchase"
            and wallet["initial_units"] == wallet["balance_units"] == entries[0]["units"] == 2 and wallet["reserved_units"] == 0
            and wallet["rule_id"] == rule["id"] and wallet["cash_id"] == entries[0]["cash_id"], "付费券批次/购买原账不符")
    entry = entries[0]
    cash = cash_fact(e, entry, "in", 800, "benefit_purchase", account, actor)
    binding = subset(e, "retail_group_wallets", "wallet_id", wallet["id"])
    require(len(binding) == 1 and binding[0]["origin_id"] == entry["id"] and binding[0]["decision_id"] == eligibility["decision"]["id"], "付费券发行未绑定原商品授权")
    payload = {"rule_id": rule["id"], "units": 2, **execution, "case_id": key, "case_version": current_case["version"]}
    receipt = group_receipt(e, request, actor, "benefit:" + str(member) + ":purchase",
                            {"version": prior_member["version"], "values": payload}, body["result"])
    events = guard.added["flow_events"]
    require([r["action"] for r in events] == ["membership_purchase", "benefit_purchase"]
            and all(r["case_id"] == key and r["actor_id"] == actor["id"] for r in events), "原宿主与权益两事件不完整")
    return {"case_id": key, "wallet": wallet, "purchase_entry": entry, "cash": cash, "settlements": paired(e, "benefit_settlements", entry["id"], 800),
            "binding": binding[0], "create": created, "handoff": handoff, "proof": proof, "execute": {"native": meta, "guard": protection, "receipt": receipt}}


def flow_receipt(e, request, actor, case_id, operation, payload):
    found = e.db.rows("SELECT * FROM flow_request_receipts WHERE request_key=?", (request["request_id"],))
    digest = sha(json.dumps({"operation": operation, "payload": payload}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
    require(len(found) == 1 and found[0]["actor_id"] == actor["id"] and found[0]["store_id"] == 1
            and found[0]["case_id"] == case_id and found[0]["digest"] == digest, "原业务回执与本人精确输入不符")
    return {"id": found[0]["id"], "digest": digest, "case_id": case_id, "actor_id": actor["id"]}


async def retail_read(e, context, credentials, fixture, role, key):
    number = one(e, "flow_cases", key)["number"]
    actor, view = await read_as(e, context, credentials, fixture, role, "retail/" + str(key), RETAIL + "/orders/" + str(key), "精品销售 · " + number)
    case = one(e, "flow_cases", key)
    require(view["id"] == key and view["version"] == case["version"] and view["state"] == case["state"], "精品原详情CAS/状态不符")
    return actor, view


async def create_retail(e, context, credentials, fixture, customer, member, primary):
    actor, _ = await read_as(e, context, credentials, fixture, "sales", "retail", RETAIL + "/orders", "精品销售与退货")
    await e.click('#main [data-act="retail-new"]', "本人客户真实购买本轮已入库商品")
    await expect(e.page.locator("#modal-title")).to_have_text("新建精品订单")
    customer_label = await e.page.locator(f'#modal [name="customer"] option[value="{customer["id"]}"]').text_content()
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/cases"
            and parse_qs(urlsplit(r.url).query).get("kind") == ["repair"]
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as related_pending:
        await live_choice(e, "customer", customer["name"], customer_label, expected_value=customer["id"])
    related_response = await related_pending.value
    require(related_response.status == 200, "原客户关联维修范围未核对完成")
    await expect(e.page.locator('#modal [data-member-price-field]')).not_to_have_attribute("data-loading", "true")
    item = one(e, "flow_items", primary["item_id"])
    item_label = await e.page.locator(f'#modal [name="item"] option[value="{item["id"]}"]').text_content()
    await live_choice(e, "item", item["sku"], item_label, expected_value=item["id"])
    await e.fill('#modal [data-retail-line] [name="quantity"]', "1.000", "实际商品数量1.000")
    await e.fill('#modal [data-retail-line] [name="price"]', "25.00", "实际冻结商品单价25.00元")
    await expect(e.page.locator('#modal [data-retail-line] [name="work"]')).to_have_value("")
    await e.fill('#modal [data-retail-line] [name="install_price"]', "0.00", "不收未发生安装费用")
    await expect(e.page.locator('#modal [name="related"]')).to_have_value("")
    await e.fill('#modal [name="discount"]', "0.00", "本次不作手工整单优惠")
    await select_value(e, '#modal [name="member_pricing_rule"]', "", "本次没有会期会员价，不猜填规则")
    guard = Guard(e, "retail_original_create", actor, append={**FLOW, "flow_cases": 1, "flow_tasks": 1, "retail_orders": 1,
        "retail_lines": 1, "retail_reservations": 1, "flow_request_receipts": 1}, update={"flow_items": {item["id"]: VERSION}},
        customer=customer["id"], member=member, new_kind="retail", item=item["id"])
    body, request, shown, native = await submit_created(e, RETAIL + "/orders", RETAIL + "/orders/", status=201, body_key=("id",))
    key = body["id"]
    expected = {"customer_id": customer["id"], "related_repair_id": None, "discount_cents": 0,
        "lines": [{"item_id": item["id"], "quantity_milli": 1000, "unit_price_cents": 2500, "work_item_id": None, "installation_unit_price_cents": 0}]}
    require(request == {"request_id": request["request_id"], **expected} and shown["amount_cents"] == 2500 and shown["revision"] == 1
            and shown["state"] == "approval", "原精品冻结输入/单价/数量不符")
    line = subset(e, "retail_lines", "case_id", key)
    require(len(line) == 1 and line[0]["goods_cents"] == 2500 and line[0]["quantity_milli"] == 1000
            and line[0]["installation_cents"] == 0 and line[0]["item_id"] == item["id"], "原商品行未按整数milli/分冻结")
    native.update(guard=guard.finish(), event=event(e, guard, key, "retail_create"),
                  receipt=flow_receipt(e, request, actor, key, "retail_create", expected), line=line[0], item_before=item)
    return key, native


async def retail_action(e, context, credentials, fixture, member, primary, key, action, token):
    role, task_key, title, category = {
        "approve": ("manager", "retail_approve", "主管价格授权", None),
        "authorize": ("sales", "retail_authorize", "记录客户报价确认", "authorization"),
        "dispatch": ("inventory", "retail_dispatch", "确认整单实际出库", "evidence"),
        "accept": ("sales", "retail_accept", "确认客户接收", "evidence"),
    }[action]
    handoff = await responsible(e, context, credentials, fixture, key, task_key, role, member)
    actor, _ = await retail_read(e, context, credentials, fixture, role, key)
    proof = await upload(e, actor, key, member, RETAIL + f"/orders/{key}", category, "retail-" + action, token) if category else None
    case = one(e, "flow_cases", key)
    item = one(e, "flow_items", primary["item_id"])
    balances = subset(e, "warehouse_balances", "item_id", item["id"])
    await original_form(e, "retail-action", action, title)
    values = {}
    if proof:
        await choose_file(e, proof, category)
        values["evidence_id"] = proof["file"]["id"]
    if action == "approve":
        await e.fill('#modal [name="minimum"]', "25.00", "主管明确冻结最低成交额")
        await checkbox(e, '#modal [name="allow_below_minimum"]', False, "本单无需低价例外")
        reason = "独立核对本轮商品数量与25元实际报价"
        await e.fill('#modal [name="reason"]', reason, "原主管价格授权依据")
        values = {"minimum_total_cents": 2500, "allow_below_minimum": False, "reason": reason}
    if action == "authorize":
        values["revision"] = 1
    append = {**FLOW, "flow_request_receipts": 1, "flow_tasks": (0, 2)}
    permitted = updates(e, [key])
    if action == "authorize":
        append["membership_points_claims"] = 1
        permitted["group_members"] = {member: VERSION}
    allocation = None
    if action == "dispatch":
        allocations = [a for a in subset(e, "warehouse_allocations", "case_id", key) if a["item_id"] == item["id"] and a["status"] == "prepared" and a["purpose"] == "retail_dispatch"]
        require(len(allocations) == 1, "没有本次真实库位准备，不能确认出库")
        allocation = allocations[0]
        permitted.update(flow_items={item["id"]: VERSION | {"quantity_milli", "inventory_value_cents", "unit_cost_cents"}},
            warehouse_balances={b["id"]: VERSION | {"quantity_milli", "value_cents"} for b in balances},
            warehouse_allocations={allocation["id"]: VERSION | {"status", "stock_move_id"}})
        append.update(retail_reservations=1, flow_stock_moves=1, retail_dispatches=1, warehouse_entries=(1, len(balances)))
    guard = Guard(e, "retail_" + action, actor, append=append, update=permitted, cases={key}, member=member, item=item["id"])
    body, request, shown, native = await submit(e, RETAIL + f"/orders/{key}/actions/{action}", RETAIL + f"/orders/{key}")
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values}
            and shown["id"] == key and shown["version"] == one(e, "flow_cases", key)["version"], "原精品动作版本或内容不符")
    native.update(guard=guard.finish(), event=event(e, guard, key, "retail_" + action), handoff=handoff, proof=proof,
        receipt=flow_receipt(e, request, actor, key, "retail_" + action, {"case_id": key, "version": case["version"], "values": values}))
    data = json.loads(one(e, "flow_cases", key)["data"])
    if action == "dispatch":
        move = guard.added["flow_stock_moves"][0]
        cost = item["inventory_value_cents"] if item["quantity_milli"] == 1000 else (2 * item["inventory_value_cents"] * 1000 + item["quantity_milli"]) // (2 * item["quantity_milli"])
        require(move["quantity_milli"] == -1000 and move["value_cents"] == -cost and move["purpose"] == "retail_dispatch"
                and data["dispatched"] is True and one(e, "flow_items", item["id"])["quantity_milli"] == item["quantity_milli"] - 1000
                and one(e, "warehouse_allocations", allocation["id"])["stock_move_id"] == move["id"], "原平均成本或真实出库来源不匹配")
        bins = subset(e, "warehouse_balances", "item_id", item["id"])
        require(sum(b["quantity_milli"] for b in bins) == one(e, "flow_items", item["id"])["quantity_milli"]
                and sum(b["value_cents"] for b in bins) == one(e, "flow_items", item["id"])["inventory_value_cents"]
                and sum(r["quantity_milli"] for r in guard.added["warehouse_entries"]) == -1000
                and sum(r["value_cents"] for r in guard.added["warehouse_entries"]) == -cost, "原庫位数量价值与门店库存不守恒")
        native.update(stock_move=move, dispatch=guard.added["retail_dispatches"][0], warehouse_entries=guard.added["warehouse_entries"], balance_ids=[b["id"] for b in bins])
    else:
        expected_flag = {"approve": "approved", "authorize": "authorized", "accept": "accepted_date"}[action]
        require(bool(data.get(expected_flag)), "原精品未产生明确事实：" + expected_flag)
    return native


async def prepare_retail(e, context, credentials, fixture, member, primary, key):
    actor, _ = await read_as(e, context, credentials, fixture, "inventory", "warehouse-allocation/" + str(key),
                            "/api/warehouse/allocations/" + str(key), "准备物资库位")
    await e.click(f'#main [data-act="wh-allocate"][data-id="{primary["item_id"]}"]', "库管按本单实际数量准备原库位")
    await expect(e.page.locator("#modal-title")).to_have_text("准备库位（尚未实际收发）")
    await select_value(e, '#modal [name="purpose"]', "retail_dispatch", "明确本次原精品出库动作")
    await e.fill('#modal [name="quantity"]', "1.000", "明确本次精确实物数量")
    await select_value(e, '#modal [data-wh-location] [name="location"]', primary["source_location_id"], "选择同轮真实有库存的原位")
    await e.fill('#modal [data-wh-location] [name="location_qty"]', "1.000", "原库位分配必须等于本次数量")
    case = one(e, "flow_cases", key)
    values = {"item_id": primary["item_id"], "quantity_milli": -1000, "purpose": "retail_dispatch",
              "locations": [{"location_id": primary["source_location_id"], "quantity_milli": 1000}]}
    guard = Guard(e, "retail_prepare_locations", actor, append={**FLOW, "flow_request_receipts": 1,
        "warehouse_allocations": 1, "warehouse_allocation_lines": 1}, update={"flow_cases": {key: VERSION}}, cases={key}, member=member, item=primary["item_id"])
    body, request, _, native = await submit(e, "/api/warehouse/allocations/" + str(key), "/api/warehouse/allocations/" + str(key))
    require(request == {"request_id": request["request_id"], "version": case["version"], "values": values} and body["prepared"] is True, "原库位准备payload不符")
    native.update(guard=guard.finish(), event=event(e, guard, key, "warehouse_allocation"),
                  receipt=flow_receipt(e, request, actor, key, "warehouse_allocation", {"id": key, "version": case["version"], **values}))
    native["allocation"] = guard.added["warehouse_allocations"][0]
    require(native["allocation"]["quantity_milli"] == -1000 and native["allocation"]["status"] == "prepared", "位置准备不能记实物完成")
    return native


async def retail_plan(e, context, credentials, fixture, member, wallets, key, token):
    actor, catalog = await read_as(e, context, credentials, fixture, "sales", "retail-group/" + str(key), RG + f"/orders/{key}/catalog", "精品集团混合付款")
    require(catalog["can_authorize"] and not catalog["has_plan"], "本次原单尚不具备真实集团付款条件")
    # Upload belongs to the same original retail case; generic raw GET is native.
    proof = await upload(e, actor, key, member, RG + f"/orders/{key}/catalog", "authorization", "retail-funding-customer-confirmation", token)
    case, db_member = one(e, "flow_cases", key), one(e, "group_members", member)
    await e.click('#main [data-act="rg-authorize"]', "客户明确本次四种原批次付款约定")
    await expect(e.page.locator("#modal-title")).to_have_text("冻结精品原付款方案")
    await e.fill('#modal [name="principal"]', "13.00", "明确使用通用本金13元")
    for kind, amount in (("bonus", 200), ("coupon", 1), ("paid", 1)):
        await e.fill(f'#modal [name="wallet_{wallets[kind]["id"]}"]', str(amount), "明确原权益整数单位：" + kind)
    await select_value(e, '#modal [name="evidence"]', proof["file"]["id"], "选择本次实际客户付款授权")
    await checkbox(e, '#modal [name="confirmed"]', True, "客户确认原批次并知悉原退及期限")
    permitted = updates(e, [key])
    guard = Guard(e, "retail_original_funding_plan", actor, append={**FLOW, "group_receipts": 1, "flow_tasks": 1,
        "retail_group_plans": 1, "retail_group_tenders": 4, "retail_group_units": 4, "retail_group_allocations": 4},
        update=permitted, cases={key}, member=member, wallets=[w["id"] for w in wallets.values()])
    body, request, shown, native = await submit(e, RG + f"/orders/{key}/actions/authorize", RG + f"/orders/{key}")
    selections = request["values"]["selections"]
    require(request["version"] == case["version"] and request["values"]["member_id"] == member and request["values"]["member_version"] == db_member["version"]
            and request["values"]["evidence_id"] == proof["file"]["id"] and len(selections) == 4
            and selections[0] == {"kind": "principal", "amount_cents": 1300}
            and {s["wallet_id"]: (s["kind"], s["units"], s["wallet_version"]) for s in selections[1:]} ==
            {wallets[k]["id"]: ("bonus" if k == "bonus" else "coupon", n, one(e, "benefit_wallets", wallets[k]["id"])["version"])
             for k, n in (("bonus", 200), ("coupon", 1), ("paid", 1))}, "集团方案与本次客户四原批次不符")
    payload = dict(request["values"])
    payload["selections"] = [{"amount_cents": None, "wallet_id": None, "wallet_version": None, "units": None, **s} for s in selections]
    native.update(guard=guard.finish(), event=event(e, guard, key, "retail_group_authorize"), proof=proof,
        receipt=group_receipt(e, request, actor, "retail_group_authorize", {"case_id": key, "version": request["version"], "values": payload}, body))
    plan = subset(e, "retail_group_plans", "case_id", key)[0]
    tenders = subset(e, "retail_group_tenders", "plan_id", plan["id"])
    expected_tenders = {None: ("principal", 1300, 1300, 1300, 1300), wallets["bonus"]["id"]: ("bonus", 200, 200, 0, 0),
                        wallets["coupon"]["id"]: ("coupon", 1, 500, 0, 0), wallets["paid"]["id"]: ("coupon", 1, 500, 400, 400)}
    require(len(tenders) == 4 and {t["wallet_id"] for t in tenders} == set(expected_tenders), "原方案批次不是本次四源")
    line_ids = {r["id"] for r in subset(e, "retail_lines", "case_id", key)}
    frozen_parts = []
    for tender in tenders:
        require(tuple(tender[k] for k in ("kind", "units", "credit_cents", "consideration_cents", "settlement_cents")) == expected_tenders[tender["wallet_id"]],
                "原Tender面值/实款/结算或单位未按客户本次来源冻结")
        unit = subset(e, "retail_group_units", "tender_id", tender["id"])
        require(len(unit) == 1, "本次每个Tender须有一份原单位")
        allocation = subset(e, "retail_group_allocations", "unit_id", unit[0]["id"])
        require(len(allocation) == 1 and allocation[0]["line_id"] in line_ids and allocation[0]["component"] == "goods"
                and all(unit[0][k] == allocation[0][k] == tender[k] for k in ("credit_cents", "consideration_cents", "settlement_cents")),
                "原单位/商品行份额与Tender C/P/S不符")
        frozen_parts.append({"tender": tender, "unit": unit[0], "allocation": allocation[0]})
    require(sum(t["credit_cents"] for t in tenders) == 2500 and sum(t["consideration_cents"] for t in tenders) == 1700
            and sum(t["settlement_cents"] for t in tenders) == 1700 and all(t["kind"] != "cash" for t in tenders)
            and one(e, "group_members", member) == db_member and all(t["status"] == "authorized" for t in shown["tenders"]), "方案冻结不得扣款/占额或制造零额现金")
    expected_digest = sha(json.dumps(["retail_group_plan", {"selections": payload["selections"], "evidence_id": proof["file"]["id"], "case_id": key}], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
    require(plan["digest"] == expected_digest, "原集团付款方案冻结摘要不匹配")
    return {"plan": plan, "tenders": tenders, "frozen_parts": frozen_parts, "native": native}


async def capture_tenders(e, context, credentials, fixture, member, key, token, plan):
    handoff = await responsible(e, context, credentials, fixture, key, "retail_group_payment", "finance", member)
    actor, _ = await read_as(e, context, credentials, fixture, "finance", "retail-group/" + str(key), RG + f"/orders/{key}", "精品集团混合付款")
    proof = await upload(e, actor, key, member, RG + f"/orders/{key}", "evidence", "retail-actual-funding-confirmation", token)
    operations = []
    for tender in plan["tenders"]:
        wid = tender["wallet_id"]
        for action in ("reserve", "capture"):
            current_case = one(e, "flow_cases", key)
            current_plan = one(e, "retail_group_plans", plan["plan"]["id"])
            db_member = one(e, "group_members", member)
            wallet = one(e, "benefit_wallets", wid) if wid else None
            original_reservations = subset(e, "retail_group_reservations", "tender_id", tender["id"])
            underlying = None
            if action == "capture":
                require(len(original_reservations) == 1, "实际核销缺本次原占额")
                link = original_reservations[0]
                underlying = one(e, "benefit_reservations" if wid else "group_reservations", link["benefit_id"] if wid else link["principal_id"])
            await original_form(e, "rg-action", action, "占用原批次" if action == "reserve" else "确认实际核销", identifier=tender["id"])
            await choose_file(e, proof)
            values = {"evidence_id": proof["file"]["id"], "plan_version": current_plan["version"], "member_version": db_member["version"], "tender_id": tender["id"]}
            if wid:
                values["wallet_version"] = wallet["version"]
            if underlying:
                values["reservation_version"] = underlying["version"]
            permitted = updates(e, [key], member=member, wallets=[wid] if wid else ())
            permitted["retail_group_plans"] = {current_plan["id"]: VERSION}
            append = {**FLOW, "group_receipts": 1}
            if action == "reserve":
                append.update(retail_group_reservations=1)
                append["benefit_reservations" if wid else "group_reservations"] = 1
            else:
                append["retail_group_captures"] = 1
                append["benefit_entries" if wid else "group_entries"] = 1
                append["benefit_payment_links" if wid else "group_payment_links"] = 1
                if tender["settlement_cents"]:
                    append["benefit_settlements" if wid else "group_settlement_entries"] = 2
                permitted["benefit_reservations" if wid else "group_reservations"] = {underlying["id"]: VERSION | {"status"}}
            guard = Guard(e, "retail_" + action + "_tender_" + str(tender["id"]), actor, append=append, update=permitted,
                          cases={key}, member=member, wallets=[wid] if wid else ())
            body, request, shown, native = await submit(e, RG + f"/orders/{key}/actions/{action}", RG + f"/orders/{key}")
            require(request == {"request_id": request["request_id"], "version": current_case["version"], "values": values}, "原四笔占用/核销CAS不符")
            payload = {"wallet_version": None, **values}
            native.update(guard=guard.finish(), event=event(e, guard, key, "retail_group_" + action),
                receipt=group_receipt(e, request, actor, "retail_group_" + action, {"case_id": key, "version": current_case["version"], "values": payload}, body))
            rendered = next(t for t in shown["tenders"] if t["id"] == tender["id"])
            require(rendered["status"] == ("reserved" if action == "reserve" else "captured"), "前端原批次状态未匹配实际动作")
            current_member = one(e, "group_members", member)
            if wid:
                current_wallet = one(e, "benefit_wallets", wid)
                require(current_wallet["balance_units"] == wallet["balance_units"] - (tender["units"] if action == "capture" else 0)
                        and current_wallet["reserved_units"] == wallet["reserved_units"] + (tender["units"] if action == "reserve" else -tender["units"])
                        and current_member["balance_cents"] == db_member["balance_cents"] and current_member["reserved_cents"] == db_member["reserved_cents"], "券/赠金占用核销错扣通用本金")
            else:
                require(current_member["balance_cents"] == db_member["balance_cents"] - (1300 if action == "capture" else 0)
                        and current_member["reserved_cents"] == db_member["reserved_cents"] + (1300 if action == "reserve" else -1300), "原本金占用与扣款未分离")
            if action == "capture":
                entry = guard.added["benefit_entries" if wid else "group_entries"][0]
                require(entry["purpose"] == "capture" and entry["case_id"] == key and entry["cash_id"] is None
                        and (entry["units"] == -tender["units"] and entry["credit_cents"] == tender["credit_cents"] if wid else entry["amount_cents"] == -1300), "实际核销未留独立原非现金账")
                native.update(entry=entry, settlements=paired(e, "benefit_settlements" if wid else "group_settlement_entries", entry["id"], -tender["settlement_cents"]))
            operations.append({"tender_id": tender["id"], "action": action, "native": native})
            # Same original group view now carries the refreshed versions for next click.
            await expect(e.page.locator("#main")).to_contain_text("已占额，未核销" if action == "reserve" else "已实际核销")
    final = one(e, "flow_cases", key)
    require(final["state"] == "completed" and not [t for t in subset(e, "flow_tasks", "case_id", key) if t["status"] == "open"]
            and one(e, "group_members", member)["balance_cents"] == 14700, "原消费履约/四笔核销未完整结束")
    before = e.business_snapshot("before_final_group_funding_read")
    async with e.page.expect_response(lambda r: get_match(r, RG + f"/orders/{key}")) as pending:
        e.action("navigate", "刷新四笔原实际核销及C/P/S结果")
        await e.page.reload(wait_until="domcontentloaded")
    view = await (await pending.value).json()
    totals = view["totals"]
    require(totals["group_paid_cents"] == 2500 and totals["group_recognized_cents"] == 1700 and totals["group_internal_settlement_cents"] == 1700
            and totals["service_discount_borne_cents"] == 800 and totals["group_discount_borne_cents"] == totals["cash_collectable_cents"] == 0
            and all(t["status"] == "captured" for t in view["tenders"]), "C/P/S、优惠承担或现金份额混账")
    require(not subset(e, "retail_payments", "case_id", key) and not subset(e, "flow_payment_links", "case_id", key), "纯集团付款制造店内收款")
    e.business_unchanged(before, "after_final_group_funding_read")
    return {"handoff": handoff, "proof": proof, "operations": operations, "totals": totals, "current_case": json_row(final, "data"), "native_refresh": True}


async def coupon_refund_action(e, context, credentials, fixture, customer, member, paid, account, token, action, *, refund_id=None):
    role = "service" if action == "refund_request" else "manager" if action == "refund_approve" else "finance"
    key, wid = paid["case_id"], paid["wallet"]["id"]
    handoff, proof = None, None
    if action != "refund_request":
        handoff = await responsible(e, context, credentials, fixture, key,
            "benefit_refund_review_" + str(refund_id) if action == "refund_approve" else "benefit_refund_pay_" + str(refund_id), role, member)
    if action != "refund_approve":
        actor, _ = await read_as(e, context, credentials, fixture, role, "membership-order/" + str(key), "/api/membership/orders/" + str(key), "会员业务办理")
        proof = await upload(e, actor, key, member, "/api/membership/orders/" + str(key), "evidence", "paid-coupon-" + action, token)
    actor, _ = await read_as(e, context, credentials, fixture, role, "benefits/" + str(customer["id"]), BENEFIT + "/members", "集团权益")
    current_case, current_member, wallet = one(e, "flow_cases", key), one(e, "group_members", member), one(e, "benefit_wallets", wid)
    original_refund = one(e, "benefit_refunds", refund_id) if refund_id else None
    title = {"refund_request": "申请原款退款", "refund_approve": "批准并占额", "refund": "登记实际退款"}[action]
    await original_form(e, "benefit-action", action, title, identifier=refund_id or wid)
    reason = "本人确认原付费券尚未使用的一张，按原购买单价退原账户"
    await e.fill('#modal [name="reason"]', reason, "说明原未用份退款事实")
    values = {"case_version": current_case["version"], "reason": reason, "wallet_id": wid, "wallet_version": wallet["version"]}
    if action == "refund_request":
        await e.fill('#modal [name="units"]', "1", "只申请原未使用的一张")
        values["units"] = 1
    if proof:
        await choose_file(e, proof)
        values["evidence_id"] = proof["file"]["id"]
    if original_refund:
        values.update(refund_id=refund_id, refund_version=original_refund["version"])
    if action == "refund":
        await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
        reference = "MF-COUPON-OUT-" + token
        await e.fill('#modal [name="reference"]', reference, "填写本次真实原款退款凭证")
        values.update(account_id=account["id"], reference=reference)
    permitted = updates(e, [key], member=member, wallets=[wid], account=account["id"] if action == "refund" else None)
    if original_refund:
        permitted["benefit_refunds"] = {refund_id: VERSION | {"status", "approved_by", "executed_entry_id"}}
    append = {**FLOW, "group_events": 1, "group_receipts": 1}
    if action in {"refund_request", "refund_approve"}:
        append["flow_tasks"] = 1
    if action == "refund_request":
        append["benefit_refunds"] = 1
    if action == "refund":
        append.update(benefit_entries=1, benefit_settlements=2, cash_entries=1)
    guard = Guard(e, "paid_coupon_" + action, actor, append=append, update=permitted, cases={key}, member=member, wallets=[wid])
    body, request, shown, native = await submit(e, BENEFIT + f"/members/{member}/actions/{action}", BENEFIT + "/members")
    require(request == {"request_id": request["request_id"], "version": current_member["version"], "values": values}, "原付费券退款钱包/会员/原单CAS不符")
    rid = body["refund"]["id"]
    refund = one(e, "benefit_refunds", rid)
    expected = {"refund_request": "requested", "refund_approve": "approved", "refund": "executed"}[action]
    require(refund["status"] == expected and refund["wallet_id"] == wid and refund["case_id"] == key and refund["units"] == 1
            and any(r["id"] == rid and r["status"] == expected for r in shown["refunds"]), "原退款请求与真实GET不一致")
    if action == "refund_approve":
        require(refund["approved_by"] == actor["id"] != refund["requested_by"] and one(e, "benefit_wallets", wid)["reserved_units"] == 1, "批准未独立占用原未用份")
    native.update(guard=guard.finish(), event=event(e, guard, key, "benefit_" + action), handoff=handoff, proof=proof,
        receipt=group_receipt(e, request, actor, "benefit:" + str(member) + ":" + action,
            {"version": current_member["version"], "values": values}, body), refund=refund)
    if action == "refund":
        entry = one(e, "benefit_entries", refund["executed_entry_id"])
        require(entry["original_id"] == paid["purchase_entry"]["id"] and entry["units"] == -1 and entry["purpose"] == "refund"
                and one(e, "benefit_wallets", wid)["balance_units"] == one(e, "benefit_wallets", wid)["reserved_units"] == 0
                and one(e, "benefit_wallets", wid)["expires_on"] == paid["wallet"]["expires_on"], "退款未引用原购买或改变期限/已用份")
        native.update(entry=entry, cash=cash_fact(e, entry, "out", 400, "benefit_refund", account, actor),
                      settlements=paired(e, "benefit_settlements", entry["id"], -400))
    return rid, native


async def bundle_read(e, context, credentials, fixture, customer, member, purchase, *, refundable, reserved, refunded, stage):
    actor, _ = await bundle_page(e, context, credentials, fixture, customer, "finance")
    before = e.business_snapshot("before_bundle_read_" + stage)
    async with e.page.expect_response(lambda r: get_match(r, BUNDLE + "/purchases")) as pending:
        e.action("navigate", "刷新原组合本金、原赠品和完整份额：" + stage)
        await e.page.reload(wait_until="domcontentloaded")
    response = await pending.value
    value = await response.json()
    item = next((r for r in value["items"] if r["id"] == purchase["id"]), None)
    require(response.status == 200 and item and item["rule"]["id"] == purchase["rule_id"]
            and item["refundable_shares"] == refundable and item["reserved_refund_shares"] == reserved and item["refunded_shares"] == refunded
            and value["member"]["balance_cents"] == one(e, "group_members", member)["balance_cents"]
            and value["member"]["reserved_cents"] == one(e, "group_members", member)["reserved_cents"], "原组合完整可退份数与原本金事实不符")
    await expect(e.page.locator("#main h1")).to_have_text("会员充值组合套餐")
    await expect(e.page.locator("#main")).to_contain_text(f"当前最多可退 {refundable} 个完整份额")
    for c in item["components"]:
        wallet = one(e, "benefit_wallets", c["wallet_id"])
        require(c["wallet_version"] == wallet["version"], "组合原批次版本不符")
        require(all(c[k] == wallet[k] for k in ("balance_units", "reserved_units", "expires_on")), "组合原批次余额/占额/期限不符")
    e.business_unchanged(before, "after_bundle_read_" + stage)
    await e.snapshot("bundle-" + stage)
    return {"stage": stage, "original_purchase": item, "member": value["member"], "native_refresh": True, "business_unchanged": True}


async def no_available_bundle(e, context, credentials, fixture, customer):
    actor, _ = await bundle_page(e, context, credentials, fixture, customer)
    before = e.business_snapshot("before_disabled_bundle_catalog")
    posts = []

    def observed(request):
        if request.method == "POST" and urlsplit(request.url).path == BUNDLE + "/orders":
            posts.append(request)

    e.page.on("request", observed)
    try:
        async with e.page.expect_response(lambda r: get_match(r, BUNDLE + "/rules")) as pending:
            await e.click('#main [data-act="bundle-create"][data-key="purchase"]', "核对未启用组合不可直接成交")
        catalog = await (await pending.value).json()
        require(not any(r["enabled"] for r in catalog["items"]), "当前首版组合竟默认启用")
        await expect(e.page.locator("#toast")).to_contain_text("本店尚无当前启用的组合")
        await expect(e.page.locator("#modal")).not_to_be_visible()
        require(not posts, "未启用组合产生业务提交")
        e.business_unchanged(before, "after_disabled_bundle_catalog")
        return {"native_click": True, "catalog_rule_ids": [r["id"] for r in catalog["items"]], "business_post_count": 0, "business_unchanged": True}
    finally:
        e.page.remove_listener("request", observed)


async def latest_bundle_only(e, context, credentials, fixture, customer, rule):
    actor, _ = await bundle_page(e, context, credentials, fixture, customer)
    before = e.business_snapshot("before_bundle_latest_choice")
    async with e.page.expect_response(lambda r: get_match(r, BUNDLE + "/rules")) as pending:
        await e.click('#main [data-act="bundle-create"][data-key="purchase"]', "核对新申请只选择当前启用组合")
    catalog = await (await pending.value).json()
    await expect(e.page.locator("#modal-title")).to_have_text("申请购买充值组合")
    current_label = f'{rule["name"]} · {rule["code"]} · 版本{rule["rule_version"]}'
    choices = await e.page.locator('#modal [name="rule"] option').all_text_contents()
    require(current_label in choices and all(not (r["code"] == rule["code"] and r["id"] != rule["id"] and f'{r["name"]} · {r["code"]} · 版本{r["rule_version"]}' in choices) for r in catalog["items"]), "旧版组合仍可作新购买选择")
    await select_value(e, '#modal [name="rule"]', current_label, "明确当前版本但不伪造额外成交")
    await e.click('#modal .modalhead [data-act="close"]', "核对后关闭未成交申请")
    discard = e.page.locator("#modal .wfx-discard")
    if await discard.is_visible():
        await e.click('#modal [data-wfx-discard]', "明确放弃未提交申请")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    e.business_unchanged(before, "after_bundle_latest_choice")
    return {"current_rule_id": rule["id"], "choice_labels": choices, "submitted": False, "business_unchanged": True}


def final_sources(e, customer, member, ordinary, primary, rules, eligibility, bundle, refund_key, paid, coupon_refund, retail_key, plan):
    refund = subset(e, "recharge_bundle_refunds", "case_id", refund_key)[0]
    principal_refund = one(e, "group_entries", refund["executed_entry_id"])
    coupon_refund_entry = one(e, "benefit_entries", one(e, "benefit_refunds", coupon_refund)["executed_entry_id"])
    components = bundle["components"]
    wallets = {k: one(e, "benefit_wallets", v["id"]) for k, v in bundle["wallets"].items()}
    wallets["paid"] = one(e, "benefit_wallets", paid["wallet"]["id"])
    captures = [r for t in plan["tenders"] for r in subset(e, "retail_group_captures", "tender_id", t["id"])]
    reservation_links = [r for t in plan["tenders"] for r in subset(e, "retail_group_reservations", "tender_id", t["id"])]
    units = [r for t in plan["tenders"] for r in subset(e, "retail_group_units", "tender_id", t["id"])]
    allocations = [r for u in units for r in subset(e, "retail_group_allocations", "unit_id", u["id"])]
    refund_parts = subset(e, "recharge_bundle_refund_components", "refund_id", refund["id"])
    postings = [r for r in rows(e, "recharge_bundle_refund_postings") if r["refund_component_id"] in {p["id"] for p in refund_parts}]
    entries = [r for r in subset(e, "benefit_entries", "case_id", refund_key)]
    require(refund["status"] == "applied" and len(entries) == len(postings) == 4, "完整原组合退款缺四份实际回收")
    for part in refund_parts:
        component = next(c for c in components if c["id"] == part["component_id"])
        posting = next(p for p in postings if p["refund_component_id"] == part["id"])
        entry = one(e, "benefit_entries", posting["benefit_entry_id"])
        require(entry["original_id"] == component["grant_entry_id"] and entry["wallet_id"] == component["wallet_id"]
                and entry["purpose"] == "adjust" and entry["units"] == -part["units"] and entry["cash_id"] is None, "回收赠品未引用各原grant且误记现金")
    cash_ids = [bundle["cash"]["id"], paid["cash"]["id"], principal_refund["cash_id"], coupon_refund_entry["cash_id"]]
    cash = [one(e, "cash_entries", key) for key in cash_ids]
    require(len(set(cash_ids)) == 4 and sum(r["amount_cents"] * (1 if r["direction"] == "in" else -1) for r in cash) == 5400
            and one(e, "group_members", member)["balance_cents"] == 9700 and one(e, "group_members", member)["reserved_cents"] == 0
            and {k: w["balance_units"] for k, w in wallets.items()} == {"bonus": 0, "points": 100, "coupon": 0, "package": 1, "paid": 0}
            and all(w["reserved_units"] == 0 for w in wallets.values()), "有限原款净现金、本金或五批权益混账")
    require(one(e, "recharge_bundle_purchases", bundle["purchase"]["id"]) == bundle["purchase"]
            and one(e, "benefit_entries", paid["purchase_entry"]["id"]) == paid["purchase_entry"]
            and one(e, "benefit_rules", paid["wallet"]["rule_id"])["credit_cents_per_unit"] == 500, "后续退款/新版本覆盖旧原事实")
    retail_dispatches = subset(e, "retail_dispatches", "case_id", retail_key)
    group_entries = [r for r in subset(e, "group_entries", "case_id", retail_key)]
    benefit_entries = [r for r in subset(e, "benefit_entries", "case_id", retail_key)]
    require(len(captures) == len(reservation_links) == len(units) == len(allocations) == 4
            and len(group_entries) == 1 and len(benefit_entries) == 3, "四集团核销缺原本金或权益账")
    principal_reservations = [one(e, "group_reservations", r["principal_id"]) for r in reservation_links if r["principal_id"]]
    benefit_reservations = [one(e, "benefit_reservations", r["benefit_id"]) for r in reservation_links if r["benefit_id"]]
    require(len(principal_reservations) == 1 and len(benefit_reservations) == 3
            and all(r["case_id"] == retail_key and r["status"] == "captured" for r in principal_reservations + benefit_reservations),
            "消费有限原占额未实际核销")
    return {"customer_id": customer["id"], "member_id": member, "account_id": ordinary["account_id"], "ordinary_membership_sources": ordinary,
        "primary_item_id": primary["item_id"], "source_location_id": primary["source_location_id"],
        "benefit_rule_ids": {k: r["id"] for k, r in rules.items()}, "eligibility_case_ids": {k: a["case_id"] for k, a in eligibility.items()},
        "eligibility_ids": {k: a["eligibility"]["id"] for k, a in eligibility.items()}, "decision_ids": {k: a["decision"]["id"] for k, a in eligibility.items()},
        "wallet_ids": {k: w["id"] for k, w in wallets.items()}, "bundle_purchase_id": bundle["purchase"]["id"], "bundle_case_id": bundle["purchase"]["case_id"],
        "bundle_refund_case_id": refund_key, "bundle_refund_id": refund["id"], "bundle_component_ids": [c["id"] for c in components],
        "bundle_grant_entry_ids": [c["grant_entry_id"] for c in components], "bundle_refund_component_ids": [r["id"] for r in refund_parts],
        "bundle_refund_posting_ids": [r["id"] for r in postings], "bundle_recovery_entry_ids": [r["id"] for r in entries],
        "bundle_topup_entry_id": bundle["principal_entry"]["id"], "bundle_refund_entry_id": principal_refund["id"],
        "paid_coupon_case_id": paid["case_id"], "paid_coupon_purchase_entry_id": paid["purchase_entry"]["id"], "paid_coupon_refund_id": coupon_refund,
        "paid_coupon_refund_entry_id": coupon_refund_entry["id"], "cash_ids": cash_ids, "cash_net_cents": 5400, "member_balance_cents": 9700,
        "points_grant_entry_id": next(r["id"] for r in bundle["grant_entries"] if r["wallet_id"] == wallets["points"]["id"]),
        "points_recovery_entry_id": next(r["id"] for r in entries if r["wallet_id"] == wallets["points"]["id"]),
        "points_consumption_or_points_change": False, "retail_case_id": retail_key,
        "retail_line_ids": [r["id"] for r in subset(e, "retail_lines", "case_id", retail_key)],
        "retail_dispatch_ids": [r["id"] for r in retail_dispatches], "stock_move_ids": [r["stock_move_id"] for r in retail_dispatches],
        "warehouse_entry_ids": [r["id"] for r in subset(e, "warehouse_entries", "case_id", retail_key)],
        "retail_plan_id": plan["plan"]["id"], "tender_ids": [r["id"] for r in plan["tenders"]], "reservation_link_ids": [r["id"] for r in reservation_links],
        "retail_unit_ids": [r["id"] for r in units], "retail_allocation_ids": [r["id"] for r in allocations],
        "principal_reservation_ids": [r["id"] for r in principal_reservations], "benefit_reservation_ids": [r["id"] for r in benefit_reservations],
        "capture_ids": [r["id"] for r in captures], "group_capture_entry_ids": [r["id"] for r in group_entries], "benefit_capture_entry_ids": [r["id"] for r in benefit_entries],
        "group_payment_link_ids": [r["id"] for r in subset(e, "group_payment_links", "case_id", retail_key)],
        "benefit_payment_link_ids": [r["id"] for r in subset(e, "benefit_payment_links", "case_id", retail_key)],
        "retail_binding_ids": [r["id"] for r in rows(e, "retail_group_wallets") if r["wallet_id"] in {w["id"] for w in wallets.values()}],
        "group_settlement_ids": [r["id"] for r in rows(e, "group_settlement_entries") if r["entry_id"] in {bundle["principal_entry"]["id"], principal_refund["id"], *[x["id"] for x in group_entries]}],
        "benefit_settlement_ids": [r["id"] for r in rows(e, "benefit_settlements") if r["entry_id"] in {paid["purchase_entry"]["id"], coupon_refund_entry["id"], *[x["id"] for x in benefit_entries]}],
        "centre_payment_performed": False, "full_193_business_acceptance": False}


async def member_followon_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        fixture, customer, member, account, primary, work, ordinary = dependencies(e, cp)
        token = uuid.uuid4().hex[:10]
        fixture["work_code"] = work["code"]
        old_cards = subset(e, "membership_cards", "member_id", member)
        old_principal = [one(e, "group_entries", ordinary[k]) for k in ("topup_entry_id", "refund_entry_id")]
        reads, rules, rules_meta, eligibility = [], {}, {}, {}

        cp.start("HK-129")
        for kind in ("bonus", "points", "coupon", "package", "paid"):
            rules[kind], rules_meta[kind] = await publish_benefit(e, context, credentials, fixture, customer, member, token, kind)
            cp.note({"kind": kind, "rule": rules[kind], "native": rules_meta[kind]})
        for kind in ("bonus", "coupon", "paid"):
            eligibility[kind] = await retail_eligibility(e, context, credentials, fixture, member, primary, rules[kind], token)
            cp.note({"independent_retail_eligibility": eligibility[kind]})
        fixture.update(gift_bonus_rule=rules["bonus"]["id"], gift_coupon_rule=rules["coupon"]["id"])

        cp.start("HK-123")
        first_rule, first_meta = await publish_bundle(e, context, credentials, fixture, member, rules, token, 1)
        disabled = await no_available_bundle(e, context, credentials, fixture, customer)
        bundle_rule, second_meta = await publish_bundle(e, context, credentials, fixture, member, rules, token, 2, previous=first_rule)
        cp.note({"disabled_first_version": first_meta, "unavailable_native_purchase": disabled, "explicit_enabled_next_version": second_meta})

        cp.start("HK-124")
        purchase_key, purchase_create = await bundle_create(e, context, credentials, fixture, customer, member, token, rule=bundle_rule)
        _, purchase_execute = await bundle_action(e, context, credentials, fixture, member, purchase_key, "execute", token, account, eligibility)
        finance = e.manifest["users"][fixture["finance_key"]]
        bundle = bundle_purchase_facts(e, purchase_key, {k: rules[k] for k in ("bonus", "points", "coupon", "package")}, member, account, finance, eligibility)
        require(bundle["purchase"]["rule_id"] == bundle_rule["id"] and one(e, "group_members", member)["balance_cents"] == 16000, "两份组合未实际发行本金16000")
        _, read = await benefit_read(e, context, credentials, fixture, customer, member, wallet_ids=[w["id"] for w in bundle["wallets"].values()], stage="bundle-issued")
        reads.append(read)
        await cp.passed({"ordinary_same_run_partial": cp.report["source_preconditions"]["ordinary_partial_evidence"]["HK-124"],
                         "bundle_create": purchase_create, "bundle_execute": purchase_execute, "db": bundle, "actual_nonempty_read": read})

        cp.start("HK-130")
        paid = await paid_coupon(e, context, credentials, fixture, customer, member, rules["paid"], account, token, eligibility["paid"])
        wallet_ids = [w["id"] for w in bundle["wallets"].values()] + [paid["wallet"]["id"]]
        _, read = await benefit_read(e, context, credentials, fixture, customer, member, wallet_ids=wallet_ids, stage="paid-coupon-issued")
        reads.append(read)
        await cp.passed({"original_paid_purchase": paid, "actual_nonempty_read": read, "gift_is_not_paid_coupon_generation": True})

        cp.start("HK-129")
        paid_v2, paid_v2_meta = await publish_benefit(e, context, credentials, fixture, customer, member, token, "paid", version=2)
        require(one(e, "benefit_wallets", paid["wallet"]["id"])["rule_id"] == rules["paid"]["id"] and one(e, "benefit_rules", rules["paid"]["id"])["sale_cents_per_unit"] == 400, "新版本改写旧付费规则")
        await cp.passed({"gift_rule": rules["coupon"], "paid_rule": rules["paid"], "paid_next_rule": paid_v2,
            "original_rule_publications": {k: rules_meta[k] for k in ("coupon", "paid")}, "independent_retail_scopes": eligibility,
            "paid_next_version": paid_v2_meta, "old_wallet_immutable_rule_id": paid["wallet"]["rule_id"]})

        cp.start("HK-132")
        retail_key, created = await create_retail(e, context, credentials, fixture, customer, member, primary)
        approved = await retail_action(e, context, credentials, fixture, member, primary, retail_key, "approve", token)
        authorized = await retail_action(e, context, credentials, fixture, member, primary, retail_key, "authorize", token)
        prepared = await prepare_retail(e, context, credentials, fixture, member, primary, retail_key)
        dispatched = await retail_action(e, context, credentials, fixture, member, primary, retail_key, "dispatch", token)
        accepted = await retail_action(e, context, credentials, fixture, member, primary, retail_key, "accept", token)
        use_wallets = {"bonus": bundle["wallets"]["bonus"], "coupon": bundle["wallets"]["coupon"], "paid": paid["wallet"]}
        plan = await retail_plan(e, context, credentials, fixture, member, use_wallets, retail_key, token)
        captured = await capture_tenders(e, context, credentials, fixture, member, retail_key, token, plan)
        _, read = await benefit_read(e, context, credentials, fixture, customer, member, wallet_ids=wallet_ids, stage="retail-captured")
        reads.append(read)
        cp.note({"real_stock_and_customer_acceptance": {"create": created, "approve": approved, "authorize": authorized, "prepare": prepared,
            "dispatch": dispatched, "accept": accepted}, "actual_four_tender_funding": {"plan": plan, "capture": captured}, "actual_nonempty_read": read})

        cp.start("HK-125")
        available = await bundle_read(e, context, credentials, fixture, customer, member, bundle["purchase"], refundable=1, reserved=0, refunded=0, stage="one-whole-share-remains")
        _, refused = await bundle_create(e, context, credentials, fixture, customer, member, token, purchase=bundle["purchase"], rejected=True)
        cancel_key, cancel_create = await bundle_create(e, context, credentials, fixture, customer, member, token, purchase=bundle["purchase"])
        _, cancel_approve = await bundle_action(e, context, credentials, fixture, member, cancel_key, "approve", token, account, eligibility, wallet_ids=[w["id"] for w in bundle["wallets"].values()])
        occupied = await bundle_read(e, context, credentials, fixture, customer, member, bundle["purchase"], refundable=0, reserved=1, refunded=0, stage="approved-occupied")
        require(one(e, "group_members", member)["reserved_cents"] == 5000 and all(one(e, "benefit_wallets", w["id"])["reserved_units"] == n
            for w, n in ((bundle["wallets"]["bonus"], 200), (bundle["wallets"]["points"], 100), (bundle["wallets"]["coupon"], 1), (bundle["wallets"]["package"], 1))), "独立批准未完整占原本金与四赠品")
        _, cancelled = await bundle_action(e, context, credentials, fixture, member, cancel_key, "cancel", token, account, eligibility, wallet_ids=[w["id"] for w in bundle["wallets"].values()])
        released = await bundle_read(e, context, credentials, fixture, customer, member, bundle["purchase"], refundable=1, reserved=0, refunded=0, stage="cancel-released")
        require(one(e, "group_members", member)["balance_cents"] == 14700 and one(e, "group_members", member)["reserved_cents"] == 0
            and all(one(e, "benefit_wallets", w["id"])["reserved_units"] == 0 for w in bundle["wallets"].values()), "撤销未释放原占額或制造实际退款")
        refund_key, refund_create = await bundle_create(e, context, credentials, fixture, customer, member, token, purchase=bundle["purchase"])
        _, refund_approve = await bundle_action(e, context, credentials, fixture, member, refund_key, "approve", token, account, eligibility, wallet_ids=[w["id"] for w in bundle["wallets"].values()])
        _, refund_execute = await bundle_action(e, context, credentials, fixture, member, refund_key, "execute", token, account, eligibility, wallet_ids=[w["id"] for w in bundle["wallets"].values()])
        refund = subset(e, "recharge_bundle_refunds", "case_id", refund_key)[0]
        entry = one(e, "group_entries", refund["executed_entry_id"])
        require(entry["amount_cents"] == -5000 and entry["original_id"] == bundle["principal_entry"]["id"] and entry["purpose"] == "refund", "组合实际退款未引用原通用本金来源")
        refunded_cash = cash_fact(e, entry, "out", 5000, "group_member_refund", account, finance)
        final_bundle = await bundle_read(e, context, credentials, fixture, customer, member, bundle["purchase"], refundable=0, reserved=0, refunded=1, stage="whole-share-refunded")
        await cp.passed({"ordinary_same_run_partial": cp.report["source_preconditions"]["ordinary_partial_evidence"]["HK-125"],
            "original_purchase_id": bundle["purchase"]["id"], "available_after_real_consumption": available, "two_share_refusal": refused,
            "cancel_branch": {"case_id": cancel_key, "create": cancel_create, "approve": cancel_approve, "occupied": occupied, "cancel": cancelled, "released": released},
            "actual_refund": {"case_id": refund_key, "create": refund_create, "approve": refund_approve, "execute": refund_execute, "refund": refund,
                "principal_entry": entry, "cash": refunded_cash, "settlements": paired(e, "group_settlement_entries", entry["id"], -5000)}, "final_original_bundle_read": final_bundle})

        cp.start("HK-123")
        newest_rule, newest_meta = await publish_bundle(e, context, credentials, fixture, member, rules, token, 3, previous=bundle_rule)
        latest = await latest_bundle_only(e, context, credentials, fixture, customer, newest_rule)
        require(one(e, "recharge_bundle_purchases", bundle["purchase"]["id"]) == bundle["purchase"]
            and one(e, "recharge_bundle_rules", bundle_rule["id"])["principal_cents_per_share"] == 5000, "后续组合版本改写原购买条款")
        await cp.passed({"first_disabled_version": first_meta, "disabled_native_catalog": disabled, "explicit_enabled_v2": second_meta,
            "actual_purchase_id": bundle["purchase"]["id"], "four_actual_component_ids": [c["id"] for c in bundle["components"]],
            "append_v3": newest_meta, "latest_native_application_choices": latest, "old_purchase_still_uses_v2": True})

        cp.start("HK-132")
        rid, coupon_request = await coupon_refund_action(e, context, credentials, fixture, customer, member, paid, account, token, "refund_request")
        rid, coupon_approve = await coupon_refund_action(e, context, credentials, fixture, customer, member, paid, account, token, "refund_approve", refund_id=rid)
        _, read = await benefit_read(e, context, credentials, fixture, customer, member, wallet_ids=wallet_ids, stage="paid-coupon-refund-reserved")
        reads.append(read)
        rid, coupon_execute = await coupon_refund_action(e, context, credentials, fixture, customer, member, paid, account, token, "refund", refund_id=rid)
        _, read = await benefit_read(e, context, credentials, fixture, customer, member, wallet_ids=wallet_ids, stage="all-original-results")
        reads.append(read)
        require(subset(e, "membership_cards", "member_id", member) == old_cards and all(one(e, "group_entries", r["id"]) == r for r in old_principal), "后继覆盖原卡/原普通本金事实")
        sources = final_sources(e, customer, member, ordinary, primary, rules, eligibility, bundle, refund_key, paid, rid, retail_key, plan)
        sources.update(bundle_rule_ids=[first_rule["id"], bundle_rule["id"], newest_rule["id"]], paid_next_rule_id=paid_v2["id"],
                       cancelled_bundle_refund_case_id=cancel_key)
        await cp.passed({"actual_nonempty_reads": reads, "original_retail_facts": {"create": created, "approve": approved, "authorize": authorized,
            "prepare": prepared, "dispatch": dispatched, "accept": accepted}, "four_actual_original_tenders": {"plan": plan, "captured": captured},
            "original_paid_coupon_refund": {"request": coupon_request, "approve": coupon_approve, "execute": coupon_execute},
            "finite_source_contract": sources, "cash_principal_consideration_separate": {"cash_net_cents": 5400, "member_balance_cents": 9700, "retail_consideration_cents": 1700}})
        cp.finish(sources)
    except Exception as error:
        cp.failed(str(error))
        raise


async def retail_eligibility(e, context, credentials, fixture, member, primary, rule, token):
    actor, _ = await read_as(e, context, credentials, fixture, "manager", "retail-group-rules", RG + "/rules", "精品权益商品规则")
    await e.click('#main [data-act="rg-rule-new"]', "主管申请本次权益明确商品用途")
    await expect(e.page.locator("#modal-title")).to_have_text("建立新商品规则申请")
    label = f'{rule["id"]} · {rule["name"]} · 版本 {rule["rule_version"]}'
    await select_value(e, '#modal [name="rule"]', label, "选择本轮尚未发行规则")
    guard = Guard(e, "retail_rule_create_" + str(rule["id"]), actor, append={**FLOW, "group_receipts": 1, "flow_cases": 1, "flow_tasks": 1},
                  member=member, new_kind="retail_group_rule")
    body, request, shown, native = await submit_created(e, RG + "/rules", RG + "/rules/", status=201, body_key=("case_id",))
    key = body["case_id"]
    require(request == {"request_id": request["request_id"], "rule_id": rule["id"]} and shown["rule"]["id"] == rule["id"] and shown["state"] == "draft", "商品规则原新申请不符")
    create = {"native": native, "guard": guard.finish(), "event": event(e, guard, key, "retail_rule_create"),
              "receipt": group_receipt(e, request, actor, "retail_rule_create", {"rule_id": rule["id"]}, body)}
    proof = await upload(e, actor, key, member, RG + "/rules/" + str(key), "evidence", "retail-rule-source-" + str(rule["id"]), token)
    await original_form(e, "rg-rule-action", "submit", "明确商品范围与原退约定")
    for field, value in (("partial_return_mode", "accumulate_original_unit"), ("expiry_mode", "original_expiry"), ("pending_claim_expiry", "none")):
        await select_value(e, f'#modal [name="{field}"]', value, "明确原退与有效期边界：" + field)
    item = one(e, "flow_items", primary["item_id"])
    option = e.page.locator('#modal label.checklabel').filter(has_text=item["sku"] + " · " + item["name"] + " · 商品")
    await expect(option).to_have_count(1)
    e.action("check", "明确本轮原物资的商品用途", item_id=item["id"])
    await option.locator('input[type="checkbox"]').set_checked(True)
    await select_value(e, '#modal [name="evidence"]', proof["file"]["id"], "选择这份原公司规则凭据")
    before = one(e, "flow_cases", key)
    values = {"scopes": [{"store_id": 1, "item_id": item["id"], "component": "goods", "work_item_id": None}],
              "evidence_id": proof["file"]["id"], "partial_return_mode": "accumulate_original_unit", "expiry_mode": "original_expiry", "pending_claim_expiry": "none"}
    guard = Guard(e, "retail_rule_submit_" + str(key), actor, append={**FLOW, "group_receipts": 1, "flow_tasks": 1,
                  "retail_group_eligibility": 1, "retail_group_scopes": 1}, update=updates(e, [key]), cases={key}, member=member, item=item["id"])
    body, request, shown, native = await submit(e, RG + f"/rules/{key}/actions/submit", RG + f"/rules/{key}")
    require(request == {"request_id": request["request_id"], "version": before["version"], "values": values}
            and shown["state"] == "approval" and len(shown["scopes"]) == 1, "原商品用途提交不是明确本轮物资")
    submitted = {"native": native, "guard": guard.finish(), "event": event(e, guard, key, "retail_rule_submit"),
        "receipt": group_receipt(e, request, actor, "retail_rule_submit", {"case_id": key, "version": request["version"], "values": values}, body)}
    eligibility = subset(e, "retail_group_eligibility", "case_id", key)
    require(len(eligibility) == 1 and eligibility[0]["rule_id"] == rule["id"] and eligibility[0]["requested_by"] == actor["id"], "商品规则来源不唯一")
    handoff = await responsible(e, context, credentials, fixture, key, "retail_rule_approve", "admin", member)
    admin, _ = await read_as(e, context, credentials, fixture, "admin", "retail-group-rule/" + str(key), RG + f"/rules/{key}", "精品权益商品规则")
    require(admin["id"] != actor["id"], "商品规则必须不同获权人批准")
    checked = await upload(e, admin, key, member, RG + f"/rules/{key}", "evidence", "retail-rule-review-" + str(key), token)
    await original_form(e, "rg-rule-action", "approve", "独立批准公司商品规则")
    await choose_file(e, checked)
    reason = "独立核对本轮实际商品、原完整单位退回与期限规则"
    await e.fill('#modal [name="reason"]', reason, "填写独立公司规则复核")
    before = one(e, "flow_cases", key)
    values = {"evidence_id": checked["file"]["id"], "reason": reason}
    guard = Guard(e, "retail_rule_approve_" + str(key), admin, append={**FLOW, "group_receipts": 1, "retail_group_decisions": 1},
                  update=updates(e, [key]), cases={key}, member=member)
    body, request, shown, native = await submit(e, RG + f"/rules/{key}/actions/approve", RG + f"/rules/{key}")
    require(request == {"request_id": request["request_id"], "version": before["version"], "values": values} and shown["state"] == "completed", "原商品用途批准字段不符")
    approved = {"native": native, "guard": guard.finish(), "event": event(e, guard, key, "retail_rule_approve"),
        "receipt": group_receipt(e, request, admin, "retail_rule_approve", {"case_id": key, "version": request["version"], "values": values}, body)}
    decisions = subset(e, "retail_group_decisions", "eligibility_id", eligibility[0]["id"])
    scopes = subset(e, "retail_group_scopes", "eligibility_id", eligibility[0]["id"])
    require(len(decisions) == len(scopes) == 1 and decisions[0]["approved"] == 1 and decisions[0]["actor_id"] == admin["id"]
            and scopes[0]["item_id"] == item["id"] and scopes[0]["unit"] == item["unit"] and scopes[0]["sku"] == item["sku"], "冻结用途/单位/独立决定不匹配")
    return {"case_id": key, "eligibility": eligibility[0], "scope": scopes[0], "decision": decisions[0],
            "create": create, "source_file": proof, "submit": submitted, "handoff": handoff, "review_file": checked, "approve": approved}


async def publish_bundle(e, context, credentials, fixture, member, rules, token, version, *, previous=None):
    actor, _ = await read_as(e, context, credentials, fixture, "admin", "recharge-bundle-rules", BUNDLE + "/rules", "充值组合规则")
    selector = '#main [data-act="bundle-rule"]' + (f'[data-id="{previous["id"]}"]' if previous else ':not([data-id])')
    await e.click(selector, "管理员明确追加冻结充值组合版本")
    await expect(e.page.locator("#modal-title")).to_have_text("发布充值组合规则")
    require(await e.page.locator('#modal [name="enabled"]').is_checked() is False, "组合发布原默认必须关闭")
    day = await e.page.locator('#modal [name="sale_starts_on"]').input_value()
    end = (date.fromisoformat(day) + timedelta(days=30)).isoformat()
    principal = 6000 if version == 3 else 5000
    values = {"code": "BUNDLE-" + token, "name": "本轮完整组合" + token + "版本" + str(version),
        "principal_cents_per_share": principal, "allowed_store_ids": [1], "sale_starts_on": day, "sale_ends_on": end,
        "refund_policy": "whole_unused_before_expiry", "refund_terms": "仅退本批尚完整未用份额，赠品与本金一起原账户退回", "enabled": version > 1,
        "components": [{"benefit_rule_id": rules[k]["id"], "units_per_share": n} for k, n in (("bonus", 200), ("points", 100), ("coupon", 1), ("package", 1))]}
    for field, value in (("code", values["code"]), ("name", values["name"]), ("principal", fen_text(principal)), ("sale_starts_on", day),
                         ("sale_ends_on", end), ("refund_terms", values["refund_terms"])):
        await e.fill(f'#modal [name="{field}"]', value, "填写充值组合冻结字段：" + field)
    for element in await e.page.locator('#modal input[name^="store_"]').all():
        name = await element.get_attribute("name")
        await checkbox(e, '#modal [name="' + name + '"]', name == "store_1", "明确仅本店发行和使用")
    for kind, amount in (("bonus", 200), ("points", 100), ("coupon", 1), ("package", 1)):
        rule = rules[kind]
        await select_value(e, f'#modal [name="gift_{kind}"]', f'{rule["name"]} · {rule["code"]} · 版本{rule["rule_version"]}', "选择明确独立零价赠品规则")
        await e.fill(f'#modal [name="units_{kind}"]', fen_text(amount) if kind == "bonus" else str(amount), "填写每份赠品原单位")
    await select_value(e, '#modal [name="refund_policy"]', "原批次赠品到期前退回完整份额", "明确原完整份额期限")
    await checkbox(e, '#modal [name="enabled"]', values["enabled"], "本人明确组合新申请启用状态")
    guard = Guard(e, "bundle_rule_v" + str(version), actor, append={"recharge_bundle_rules": 1, "recharge_bundle_rule_components": 4, "group_receipts": 1}, member=member)
    body, request, shown, native = await submit(e, BUNDLE + "/rules", BUNDLE + "/rules", status=201)
    row = json_row(one(e, "recharge_bundle_rules", body["id"]), "allowed_store_ids")
    require(request == {"request_id": request["request_id"], "values": values} and row["rule_version"] == version
            and all(row[k] == v for k, v in values.items() if k not in {"components", "refund_terms"})
            and row["refund_terms"].startswith(values["refund_terms"]) and "积分" in row["refund_terms"], "充值组合冻结规则/补充欠分条款不符")
    components = subset(e, "recharge_bundle_rule_components", "bundle_rule_id", row["id"])
    require([{k: r[k] for k in ("benefit_rule_id", "units_per_share")} for r in components] == values["components"]
            and body["mandatory_terms"] and len([r for r in shown["items"] if r["id"] == row["id"]]) == 1, "组合四赠品/原强制条款/页面不符")
    native.update(guard=guard.finish(), receipt=group_receipt(e, request, actor, "recharge_bundle_rule", values, body),
                  rule=row, components=components, mandatory_terms=body["mandatory_terms"])
    await expect(e.page.locator("#main")).to_contain_text(values["name"])
    return row, native


MEMBER_FOLLOWON_SCENARIOS = ((SCENARIO, member_followon_business, 1200),)
