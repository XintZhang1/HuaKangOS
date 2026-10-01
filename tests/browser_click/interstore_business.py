"""Native two-store transfers and actual clearing; synthetic, same-run facts only.

No application imports, HTTP write setup, SQL writes, or unknown-result replay.
The five checks keep manual experience/copy review and all external gates pending.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import employee_choice, require
from sales_order_business import checkpoint_evidence, fixed_dependency
from vehicle_purchase_business import checkbox, live_choice, master_form, select_value
from master_data_business import save_item, save_typed
from material_business import qty, visible_original_button
from system_management_business import (after_write, audit_one, before_write, field,
    fresh_identity, native_login, original_submit as system_submit, personal_password,
    save_private)

SCENARIO = "interstore-original-hk020-024-047-055-084"
CONTRACTS = (
    ("HK-020", "车辆调拨入库", "双方独立批准、实车发运及目的实际验收，新代次/身份/成本/位置守恒"),
    ("HK-024", "车辆调拨出库", "另一可用VIN独立调拨并实际拒收、退运、原店新代次验收"),
    ("HK-047", "物资调拨入库", "1000原批分两次实收500/250及拒收250原返，库位与成本守恒"),
    ("HK-055", "物资调拨出库", "本店原可用物资、双方批准、源位1000实际发运及原流水"),
    ("HK-084", "调拨出库收款", "三条真实验收往来分别付款店pay与收款店receive，六现金/六offset闭合"),
)
PARENTS = (
    "vehicle-purchase-hk171-177-178-026-021-018-029",
    "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187",
    "materials-hk069-045-054-083-070-072-073-051-061",
    "vehicle-import-operations-hk019-027-028-030-025-023",
    "sales-cancellation-hk010",
)
TABLES = {
    "flow_cases", "flow_tasks", "flow_events", "audit_logs", "flow_request_receipts",
    "flow_files", "file_security", "file_scan_events", "flow_items", "flow_stock_moves",
    "flow_accounts", "master_warehouses", "master_locations", "master_receipts",
    "warehouse_documents", "warehouse_approvals", "warehouse_enrollments", "warehouse_balances",
    "warehouse_entries", "warehouse_allocations", "warehouse_allocation_lines",
    "material_transfers", "material_transfer_lines", "material_transfer_movements",
    "material_transfer_settlements", "material_transfer_receipts", "vehicles", "vehicle_custodies",
    "vehicle_transfers", "vehicle_movements", "vehicle_transfer_settlements", "vehicle_positions",
    "vehicle_position_entries", "group_identities", "group_identity_links",
    "interstore_clearing_buckets", "interstore_clearing_orders", "interstore_clearing_cash",
    "interstore_clearing_offsets", "reconciliation_events", "reconciliation_receipts", "cash_entries",
}
PK = {"file_security": "file_id"}
VERSION = {"version", "updated_at"}
CASE_FIELDS = VERSION | {"state", "completed_date"}
TASK_FIELDS = VERSION | {"status", "done_by", "done_at"}
ITEM_FIELDS = VERSION | {"quantity_milli", "inventory_value_cents", "unit_cost_cents"}
LABELS = {"vehicle": {"approve": "批准本店安排", "dispatch": "核对实车并发出",
    "accept": "验收车辆入库", "reject": "拒收车辆", "return_ship": "确认退回发运",
    "return_receive": "确认退回入库"}, "material": {"approve": "批准本店安排",
    "dispatch": "确认实物发出", "receive": "分批验收", "return_ship": "拒收物资发运退回",
    "return_receive": "确认退回入库"}}


def today():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest()


def rows(e, table):
    require(table in TABLES, "未审来源表：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {PK.get(table, 'id')}")


def one(e, table, key):
    require(table in TABLES, "未审来源表：" + table)
    found = e.db.rows(f"SELECT * FROM {table} WHERE {PK.get(table, 'id')}=?", (key,))
    require(len(found) == 1, "原记录非唯一：" + table + "/" + str(key))
    return found[0]


def related(e, table, field_name, key):
    require(table in TABLES and field_name in {"case_id", "item_id", "transfer_id", "order_id", "vehicle_id", "allocation_id"},
            "关联读取无有限合同")
    return e.db.rows(f"SELECT * FROM {table} WHERE {field_name}=? ORDER BY {PK.get(table, 'id')}", (key,))


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        source = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title, _ in CONTRACTS:
            require(source[key]["title"] == title and source[key]["source_review_status"] == "source_reviewed",
                    key + " 源标题/合同未核准")
            require(any(c["check_id"] == key + "-business" for c in source[key]["acceptance_checks"]), "check_id误配")
        self.report = {"schema": 1, "scenario": SCENARIO, "source_contract_sha256": self.digest,
            "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "complete": False, "passed": False, "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "human_acceptance": "pending",
            "execution": "native_browser_original_forms", "scope": [r[0] for r in CONTRACTS],
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested",
                    "contract": contract, "evidence": {}, "criteria": [{"category": k, "status":
                    "manual_review_pending" if k in {"simple_flow", "concise_copy"} else "not_tested"}
                    for k in ("frontend_expected", "simple_flow", "concise_copy", "backend_matches", "hard_bugs", "scope_source_integrity")]}]}
                for key, title, contract in CONTRACTS],
            "conditional_not_tested": ["错VIN/超量/CAS/角色撤销", "审批拒绝/未发撤销", "运输损坏短缺/质量不合格/损失找回",
                "部分金额/付款差异/撤销", "跨店指定附件授权及失效", "真实银行/PG/Linux/ClamAV/员工/生产"],
            "conditions": {"synthetic_only": True, "manual_review": "pending", "production_acceptance": False}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active.update(status="running", evidence_action_start=len(self.e.actions))
        self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    async def passed(self, evidence):
        require(self.active is not None, "没有当前逐项check")
        self.active.update(status="passed", evidence_action_end=len(self.e.actions))
        check = self.active["acceptance_checks"][0]
        check.update(status="passed", evidence=evidence)
        for criterion in check["criteria"]:
            if criterion["status"] != "manual_review_pending":
                criterion["status"] = "passed"
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active = None
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = "failed"
            self.active["acceptance_checks"][0].update(status="failed", error=self.e.scrub(error))
            self.report["failed_requirement"] = self.active["id"]
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "五项原业务未执行完整")
        self.report.update(complete=True, passed=True, executed_requirements=5, passed_requirements=5, report_sources=sources)
        self.save()


class Guard:
    """Coherent full hashes; exact prior primary keys/columns and bounded appends."""
    def __init__(self, e, label, actor, store, *, add=None, update=None, cases=(), items=(), vins=(),
                 parties=None, new_kind=None, transfers=(), orders=()):
        self.e, self.label, self.actor, self.store = e, label, actor, store
        self.add, self.update = add or {}, update or {}
        require(self.add.keys() | self.update.keys() <= TABLES, "动作表超过审阅范围")
        self.cases, self.items, self.vins = set(cases), set(items), set(vins)
        self.parties, self.new_kind = set(parties or (store,)), new_kind
        self.transfers, self.orders = set(transfers), set(orders)
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.add.keys() | self.update.keys()}
        self.new = {}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.add.keys() | self.update.keys(), "原动作改动无关表：" + str(sorted(changed)))
        updated = {}
        for table, old_rows in self.old.items():
            key = PK.get(table, "id")
            now = {r[key]: r for r in rows(self.e, table)}
            old_ids = {r[key] for r in old_rows}
            updated[table] = []
            for old in old_rows:
                require(old[key] in now, "原行被删除：" + table)
                columns = {k for k in old if old[k] != now[old[key]][k]}
                require(columns <= self.update.get(table, {}).get(old[key], set()),
                        "旧原行越界：" + table + "/" + str(old[key]) + "/" + str(sorted(columns)))
                if columns:
                    updated[table].append({"id": old[key], "columns": sorted(columns)})
            fresh = [r for key_id, r in now.items() if key_id not in old_ids]
            count = self.add.get(table, 0)
            lo, hi = count if isinstance(count, tuple) else (count, count)
            require(lo <= len(fresh) <= hi, "新增数与原动作不符：" + table + "/" + str(len(fresh)))
            self.new[table] = fresh
        owned = self.cases | {r["id"] for r in self.new.get("flow_cases", [])}
        transfer_ids = self.transfers | {r["id"] for t in ("material_transfers", "vehicle_transfers") for r in self.new.get(t, [])}
        order_ids = self.orders | {r["id"] for r in self.new.get("interstore_clearing_orders", [])}
        for table, fresh in self.new.items():
            for row in fresh:
                if "store_id" in row:
                    require(row["store_id"] in self.parties, "新增串店：" + table)
                if "case_id" in row:
                    require(row["case_id"] in owned, "新增串原单：" + table)
                if "item_id" in row:
                    require(row["item_id"] in self.items, "新增串物资：" + table)
                if "transfer_id" in row:
                    require(row["transfer_id"] in transfer_ids, "新增串调拨：" + table)
                if "order_id" in row:
                    require(row["order_id"] in order_ids, "新增串清算：" + table)
                if table == "flow_cases":
                    require(row["kind"] == self.new_kind and row["flow_version"] == (3 if self.new_kind == "material_transfer" else 2),
                            "新协调原单类型/版本错误")
                for actor_key in ("actor_id", "created_by", "requested_by", "confirmed_by"):
                    if row.get(actor_key) is not None and table != "flow_tasks":
                        require(row[actor_key] == self.actor["id"], "新增非本人事实：" + table)
                if row.get("vehicle_id") is not None:
                    require(one(self.e, "vehicles", row["vehicle_id"])["vin"] in self.vins, "新增车辆无有限VIN来源")
                if table in {"vehicles", "vehicle_custodies", "vehicle_transfers"}:
                    require(row["vin"] in self.vins, "新增VIN无来源")
                if table == "group_identities":
                    require(row["kind"] == "vehicle" and row["canonical_key"] in self.vins, "新增共享身份无原VIN")
                if table == "group_identity_links":
                    require(row["local_kind"] == "vehicle" and one(self.e, "vehicles", row["local_id"])["vin"] in self.vins,
                            "新增共享关联无原代次")
                if table in {"file_security", "file_scan_events"}:
                    require(one(self.e, "flow_files", row["file_id"])["case_id"] in owned, "扫描串附件")
                if table == "warehouse_allocation_lines":
                    allocation = one(self.e, "warehouse_allocations", row["allocation_id"])
                    require(allocation["case_id"] in owned and allocation["item_id"] in self.items, "库位准备串源")
                if table == "warehouse_entries":
                    require(one(self.e, "warehouse_balances", row["balance_id"])["item_id"] in self.items, "库位流水串物资")
        result = {"label": self.label, "changed_tables": sorted(changed),
            "appended_ids": {t: [r[PK.get(t, 'id')] for r in values] for t, values in self.new.items()},
            "updated_columns": updated, "all_old_rows_preserved": True, "all_other_tables_preserved": True}
        self.e.observe("interstore_original_guard", result)
        return result


def mutable_cases(e, case_ids):
    return {"flow_cases": {key: set(CASE_FIELDS) for key in case_ids},
        "flow_tasks": {r["id"]: set(TASK_FIELDS) for key in case_ids for r in related(e, "flow_tasks", "case_id", key)}}


def item_mutable(e, item_id, case_id):
    return {"flow_items": {item_id: set(ITEM_FIELDS)}, "warehouse_balances": {
        r["id"]: VERSION | {"quantity_milli", "value_cents"} for r in related(e, "warehouse_balances", "item_id", item_id)},
        "warehouse_allocations": {r["id"]: VERSION | {"status", "stock_move_id"}
            for r in related(e, "warehouse_allocations", "case_id", case_id) if r["item_id"] == item_id}}


async def read_page(e, route, path, title):
    before = e.business_snapshot("before_interstore_read")
    if urlsplit(e.page.url).fragment == route:
        await expect(e.page.locator("#modal")).not_to_be_visible()
        await expect(e.page.locator("#main .loading")).to_have_count(0)
        await expect(e.page.locator("#main h1")).to_have_text(title)
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        if urlsplit(e.page.url).fragment == route:
            e.action("navigate", "重读当前原页面", route=route)
            await e.page.reload(wait_until="domcontentloaded")
        else:
            selector = f'[data-act="open"][data-route="{route}"]'
            anchor = f'a[href="#{route}"]'
            if await e.page.locator(anchor).count() == 1:
                ancestors = e.page.locator(anchor).locator("xpath=ancestor::details")
                for index in range(await ancestors.count()):
                    detail = ancestors.nth(index)
                    if await detail.get_attribute("open") is None:
                        e.action("click", "展开原导航分组", route=route)
                        await detail.locator(":scope > summary").click()
                await e.click(anchor, "打开原页面：" + title)
            elif await e.page.locator(selector).count() == 1 and await e.page.locator(selector).is_visible():
                await e.click(selector, "继续本次原单：" + title)
            else:
                e.action("navigate", "原深链接查看本次已知编号", route=route)
                await e.page.goto(e.origin + "/#" + route, wait_until="domcontentloaded")
    response = await pending.value
    body = await response.json()
    require(response.status == 200, "原页面读取失败：" + path)
    await expect(e.page.locator("#main h1")).to_have_text(title)
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    e.business_unchanged(before, "after_interstore_read")
    return body


async def submit(e, path, actor, store, guard, *, status=200, multipart=False, assign=False, keyed=True):
    async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
        await e.click('#modal form button[type="submit"]', "本人只提交一次原确认")
    response = await pending.value
    body = await response.json()
    require(response.status == status, f"原确认HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    headers = await response.request.all_headers()
    require(bool(headers.get("cookie")) and bool(headers.get("x-csrf-token"))
            and headers.get("x-store-id") == str(store) and headers.get("x-app-request") == "1", "原同源身份/CSRF/门店错误")
    request = None if multipart else response.request.post_data_json
    if not multipart:
        require(isinstance(request, dict), "原JSON请求缺失")
        if assign:
            require(set(request) == {"version", "assignee_id", "reason"}, "原Task交接不是三字段合同")
        elif keyed:
            require(re.fullmatch(r"[A-Za-z0-9_-]{16,80}", request.get("request_id", "")), "原确认缺幂等编号")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    # Callers explicitly reread the native page for its current ID/version/DOM;
    # no callback latency is interpreted as a failed write or a retry instruction.
    native = {"path": path, "method": "POST", "status": response.status, "actor_id": actor["id"], "store_id": store,
        "original_ui": True, "cookie_present": True, "csrf_present": True,
        "submitted_version": request.get("version") if request else None,
        "submitted_case_version": request.get("case_version") if request else None,
        "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest() if request and request.get("request_id") else None,
        "response_id": body.get("id"), "guard": guard.finish()}
    e.observe("interstore_original_submit", native)
    return body, request, native


def original_receipt(e, family, actor, store, request, result, action, *, case_id=None):
    payload = {k: v for k, v in request.items() if k != "request_id"}
    if family == "transfer":
        table, digest = "material_transfer_receipts", sha([action, payload])
    elif family == "clearing":
        table, digest = "reconciliation_receipts", sha({"action": action, "values": payload})
    else:
        table = "flow_request_receipts"
        if action == "warehouse_create":
            payload = {"source_location_id": None, "destination_location_id": None, "original_move_id": None,
                       "recipient": "", "locations": [], **payload}
        elif action == "warehouse_approve":
            payload = {"id": case_id, "version": payload["version"], "value_cents": None, **payload["values"]}
        else:
            payload = {"id": case_id, "version": payload["version"], **payload["values"]}
        digest = sha({"operation": action, "payload": payload})
    found = e.db.rows(f"SELECT * FROM {table} WHERE request_key=?", (request["request_id"],))
    require(len(found) == 1 and found[0]["actor_id"] == actor["id"] and found[0]["store_id"] == store
            and found[0]["digest"] == digest, "原回执家族/本人/店/完整封包不符")
    if family in {"transfer", "clearing"}:
        stored = json.loads(found[0]["result"])
        require(stored["id"] == result["id"] and stored["version"] == result["version"]
                and stored["case_id"] == result["case_id"] and stored["case_version"] == result["case_version"], "原回执结果串单/CAS")
    else:
        require(found[0]["case_id"] == case_id, "原库位回执串单")
    return {"id": found[0]["id"], "family": table, "digest": digest, "actor_id": actor["id"], "store_id": store}


async def create_staff(e, admin, secret, role, token):
    await read_page(e, "users", "/api/users", "员工账号")
    await e.click('[data-act="newuser"]', "新建本批二店独立" + role)
    await expect(e.page.locator('#modal [name="role"]')).to_have_value("sales")
    boxes = e.page.locator('#modal [name="store_ids"]')
    require(await boxes.count() >= 2 and not any([await boxes.nth(i).is_checked() for i in range(await boxes.count())]),
            "原员工默认门店不是空选择")
    await expect(e.page.locator('#modal [name="can_group_summary"]')).not_to_be_checked()
    await field(e, "username", secret["username"])
    await field(e, "password", secret["initial"], private=True)
    display = "合成二店调拨" + {"manager": "主管", "inventory": "库管", "finance": "财务"}[role] + token
    await field(e, "display_name", display)
    await checkbox(e, '#modal [name="store_ids"][value="2"]', True, "仅明确授予二店")
    await select_value(e, '#modal [name="store_role_2"]', role, "明确本店实际岗位")
    protection = before_write(e, appends=("users", "user_stores", "audit_logs"))
    body, request, meta = await system_submit(e, "/api/users", 201, store_id=1)
    require(request["role"] == "sales" and request["store_ids"] == [2]
            and request["store_roles"] == [{"store_id": 2, "role": role}]
            and request["can_group_summary"] is False, "账号默认岗位与原二店授权不符")
    accounts = e.db.rows("SELECT * FROM users WHERE id=?", (body["id"],))
    require(len(accounts) == 1, "新员工原ID非唯一")
    account = accounts[0]
    require(account["username"] == secret["username"] and account["display_name"] == display
            and account["role"] == "sales" and account["active"] == account["must_change_password"] == 1,
            "新员工原资料不符")
    members = e.db.rows("SELECT * FROM user_stores WHERE user_id=? ORDER BY store_id", (account["id"],))
    require(len(members) == 1 and members[0]["store_id"] == 2 and members[0]["role"] == role, "新员工授予其他门店")
    require(len(e.db.rows("SELECT id FROM users ORDER BY id")) == len(protection[1]["users"]) + 1,
            "一次新员工表单产生其他账号")
    require(len(e.db.rows("SELECT user_id FROM user_stores ORDER BY user_id,store_id"))
            == len(protection[1]["user_stores"]) + 1, "一次授予产生其他关系")
    audit = audit_one(e, protection, admin["id"], "create_user", "users", account["id"])
    safety = after_write(e, protection)
    await expect(e.page.locator(f'#main tr:has([data-act="edituser"][data-id="{account["id"]}"])')).to_contain_text(display)
    require("password" not in body and "password_hash" not in body, "新员工响应暴露凭据")
    # Return the safe identity only; hash never enters JSON/checkpoint.
    return {"id": account["id"], "username": account["username"], "display_name": display, "role": "sales"}, {
        **meta, **safety, "audit_id": audit["id"], "user_id": account["id"], "store_id": 2,
        "account_role": "sales", "current_store_role": role, "default_stores_empty": True}


class Roster:
    def __init__(self, e, initial_context, credentials):
        self.e, self.initial, self.credentials = e, initial_context, credentials
        self.initial_page = e.page
        self.contexts, self.identities = [], {}

    async def existing(self, role):
        if role not in self.identities:
            context, page = await fresh_identity(self.e, self.initial, self.contexts)
            actor = await self.e.login(context, self.credentials, role=role, route="parameters")
            await expect(page.locator('#main h1')).to_have_text("参数与个人密码")
            await expect(page.locator('#store')).to_have_value("1")
            self.identities[role] = (context, page, actor, 1, role)
        await self.use(role)
        return self.identities[role][2]

    async def use(self, key):
        context, page, actor, store, role = self.identities[key]
        await self.e.attach(context, page)
        await expect(page.locator('.identity .who')).to_contain_text(actor["display_name"])
        await expect(page.locator('#store')).to_have_value(str(store))
        return actor, store, role

    async def create_destination(self, token):
        admin = await self.existing("admin")
        private = {role: {"username": "it_" + token + "_" + role,
                    "initial": "A!" + secrets.token_urlsafe(24), "current": "B!" + secrets.token_urlsafe(24)}
                   for role in ("manager", "inventory", "finance")}
        self.e.secrets.extend(value for record in private.values() for key, value in record.items() if key != "username")
        directory = Path(self.e.manifest["runtime_root"]) / ("interstore-private-" + token)
        directory.mkdir(exist_ok=True)
        save_private(directory / "interstore-accounts.json", private)
        created = {}
        for role, secret in private.items():
            await self.use("admin")
            account, meta = await create_staff(self.e, admin, secret, role, token)
            context, page = await fresh_identity(self.e, self.initial, self.contexts)
            login = await native_login(self.e, account, secret["initial"], first=True)
            require(login["active_store_id"] == 2 and login["current_role"] == role and login["store_ids"] == [2],
                    "新员工当前二店岗位没有真实重验")
            password = await personal_password(self.e, account, secret["initial"], secret["current"], 2, opened=True)
            login = await native_login(self.e, account, secret["current"])
            require(login["must_change_password"] is False and login["current_role"] == role
                    and login["active_store_id"] == 2 and login["store_ids"] == [2], "首改密后实际登录未重验二店岗位")
            self.identities[role + "2"] = (context, page, {**account, "account_role": "sales", "role": role}, 2, role)
            created[role] = {"user": {"id": account["id"], "display_name": account["display_name"], "account_role": "sales",
                "store_role": role, "store_ids": [2]}, "create": meta, "first_password": password, "native_login": login}
        return created

    async def close(self):
        await self.e.attach(self.initial, self.initial_page)
        for context in self.contexts:
            await context.close()


def dependencies(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "只允许同次外置合成实例")
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(Path(e.manifest["runtime_root"]).resolve()),
            "数据库没有位于本次外置runtime")
    provenance_path = Path(e.manifest["evidence_root"]) / "provenance.json"
    raw_provenance = provenance_path.read_bytes()
    provenance = json.loads(raw_provenance)
    require(provenance.get("snapshot_stable") is True, "本次镜像没有冻结")
    for name in ("interstore_business.py", "business_acceptance_catalog.json", "sales_order_business.py",
            "vehicle_operations_business.py", "material_business.py", "master_data_business.py",
            "vehicle_purchase_business.py", "system_management_business.py", "sales_business.py"):
        require(provenance["script_files"].get(name) == hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest(),
                "本轮依赖脚本指纹变化：" + name)
    source_root = Path(e.manifest["source_root"]).resolve()
    for name in ("database_path", "evidence_root", "runtime_root"):
        require(not Path(e.manifest[name]).resolve().is_relative_to(source_root), "运行资料进入被测源码目录")
    cp.report["mirror"] = {"sha256": hashlib.sha256(raw_provenance).hexdigest(),
        "source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"]}
    parents = {key: fixed_dependency(e, cp, key) for key in PARENTS}
    operation = parents[PARENTS[3]]["report_sources"]
    cancellation = parents[PARENTS[4]]["report_sources"]
    primary = parents[PARENTS[2]]["material_sources"]["primary"]
    account_id = checkpoint_evidence(parents[PARENTS[0]], "HK-021")["payment"]["account_id"]
    a = one(e, "vehicles", operation["current_vehicle_id"])
    b = one(e, "vehicles", cancellation["cancelled_vehicle_id"])
    require(a["id"] != b["id"] and a["vin"] != b["vin"], "两独立调拨前序不是两辆不同实车")
    require(operation["final_A"]["vehicle"]["id"] == a["id"], "车辆作业当前代次来源不一致")
    require(primary["store_id"] == 1, "原物资源不是一店")
    account = one(e, "flow_accounts", account_id)
    location = one(e, "master_locations", operation["source_location_id"])
    require(account["store_id"] == location["store_id"] == 1 and account["active"] == location["active"] == 1,
            "原账户/退回库位不在本店启用范围")
    return a, b, primary, account, location


def vehicle_fact(e, vehicle_id, *, available=False):
    vehicle = one(e, "vehicles", vehicle_id)
    custody_rows = e.db.rows("SELECT * FROM vehicle_custodies WHERE vin=?", (vehicle["vin"],))
    positions = related(e, "vehicle_positions", "vehicle_id", vehicle_id)
    require(len(positions) == 1, "本次实车缺唯一真实位置")
    if available:
        require(vehicle["store_id"] == 1 and vehicle["approval_state"] == "approved" and positions[0]["status"] == "stored",
                "前序车辆不是一店实际可用库存")
        require(not e.db.rows("SELECT id FROM sales WHERE active_vehicle_id=?", (vehicle_id,))
                and not e.db.rows("SELECT vehicle_id FROM flow_vehicle_holds WHERE vehicle_id=?", (vehicle_id,))
                and not e.db.rows("SELECT id FROM vehicle_operation_claims WHERE active_vin=?", (vehicle["vin"],))
                and not e.db.rows("SELECT id FROM vehicle_purchase_returns WHERE active_shipment_id IN "
                    "(SELECT shipment_id FROM vehicle_purchase_receipts WHERE vehicle_id=?)", (vehicle_id,)), "前序车辆仍有原业务占额")
        if custody_rows:
            require(len(custody_rows) == 1 and custody_rows[0]["current_vehicle_id"] == vehicle_id
                    and custody_rows[0]["current_store_id"] == 1 and custody_rows[0]["pending_transfer_id"] is None,
                    "共享车辆归属/调拨占用未释放")
        require(vehicle["purchase_cost_cents"] > 0, "实际清算必须具备真实正原成本")
    return {"vehicle": vehicle, "custody": custody_rows[0] if custody_rows else None,
            "position": positions[0], "entries": related(e, "vehicle_position_entries", "vehicle_id", vehicle_id)}


async def case_page(e, case_id):
    source = one(e, "flow_cases", case_id)
    view = await read_page(e, "case/" + str(case_id), "/api/flow/cases/" + str(case_id), source["title"])
    require(view["id"] == source["id"] and view["store_id"] == source["store_id"]
            and view["version"] == one(e, "flow_cases", case_id)["version"], "本地原Case GET错单/CAS")
    return view


async def responsible(e, roster, key, case_id, task_key):
    actor, store, role = await roster.use(key)
    view = await case_page(e, case_id)
    found = [r for r in related(e, "flow_tasks", "case_id", case_id) if r["key"] == task_key and r["status"] == "open"]
    require(len(found) == 1 and found[0]["store_id"] == store, "当前本人原Task不存在/非本店")
    task = found[0]
    handoff = None
    if task["assignee_id"] != actor["id"]:
        manager_key = "manager2" if store == 2 else "manager"
        if store == 1:
            await roster.existing("manager")
        manager, _, _ = await roster.use(manager_key)
        view = await case_page(e, case_id)
        target = next(r for r in view["tasks"] if r["id"] == task["id"])
        button = f'#main [data-act="assignTask"][data-id="{task["id"]}"]'
        await expect(e.page.locator(button)).to_have_count(1)
        await expect(e.page.locator(button)).to_be_visible()
        await e.click(button, "主管从原单明确转交当前待办")
        await expect(e.page.locator("#modal-title")).to_have_text("转交任务")
        await employee_choice(e, actor)
        reason = "本轮调拨由本店明确员工接手原任务"
        await field(e, "reason", reason)
        guard = Guard(e, "transfer_task_assign", manager, store, add={"flow_events": 1, "audit_logs": 1},
            update={"flow_tasks": {task["id"]: VERSION | {"assignee_id"}}}, cases={case_id})
        _, request, handoff = await submit(e, f'/api/flow/tasks/{task["id"]}/assign', manager, store, guard, assign=True)
        require(request == {"version": target["version"], "assignee_id": actor["id"], "reason": reason}, "原交接三字段输入不符")
        changed = one(e, "flow_tasks", task["id"])
        require(changed["assignee_id"] == actor["id"] and changed["version"] > target["version"], "交接未落原待办")
        await roster.use(key)
        view = await case_page(e, case_id)
    task = one(e, "flow_tasks", task["id"])
    require(task["assignee_id"] == actor["id"] and task["status"] == "open" and role != "admin", "本人待办/岗位未重验")
    return actor, store, task, handoff


async def upload(e, case_id, actor, store, category, purpose):
    await case_page(e, case_id)
    directory = e.directory / "synthetic-inputs"
    directory.mkdir(exist_ok=True)
    path = directory / (purpose + "-" + uuid.uuid4().hex[:8] + ".txt")
    content = ("本轮外部隔离合成输入；非真实银行或交接证据。\n原本店单=" + str(case_id)
               + "；用途=" + purpose + "；随机输入=" + uuid.uuid4().hex + "\n").encode()
    path.write_bytes(content)
    await e.click('#main [data-act="upload"]', "本人上传本店原单独立凭据")
    await expect(e.page.locator("#modal-title")).to_have_text("上传业务文件")
    await select_value(e, '#modal [name="category"]', category, "选择原凭据类别")
    e.action("select_file", "选择外部合成文件", name=path.name, length=len(content), sha256=hashlib.sha256(content).hexdigest())
    await e.page.locator('#modal [name="file"]').set_input_files(str(path))
    guard = Guard(e, "interstore_file_upload", actor, store, add={"flow_files": 1, "file_security": 1,
        "file_scan_events": 1, "flow_events": 1, "audit_logs": 1}, cases={case_id})
    async with e.page.expect_response(lambda r: r.request.method == "GET"
            and urlsplit(r.url).path == f'/api/flow/cases/{case_id}') as rendered:
        body, _, native = await submit(e, f'/api/flow/cases/{case_id}/files', actor, store, guard, multipart=True)
        after_upload = e.business_snapshot("after_interstore_upload_before_render")
    response = await rendered.value
    view = await response.json()
    source = one(e, "flow_cases", case_id)
    require(response.status == 200 and view["id"] == case_id and view["store_id"] == store
            and view["version"] == source["version"], "上传后的原UI渲染错原单/门店/CAS")
    await expect(e.page.locator("#main h1")).to_have_text(source["title"])
    asset = one(e, "flow_files", body["id"])
    blob = asset.pop("content")
    require(isinstance(blob, bytes) and blob == content and asset["size"] == len(content)
            and asset["sha256"] == hashlib.sha256(content).hexdigest() and asset["case_id"] == case_id
            and asset["store_id"] == store and asset["created_by"] == actor["id"]
            and asset["category"] == category and not asset["generated"], "原上传字节/店/本人/原单不符")
    security = one(e, "file_security", asset["id"])
    require(security["state"] == "structure_only" and body["security"]["can_use"], "合成原件应仅结构检查可用")
    require([(f["id"], f["name"]) for f in view["files"] if f["id"] == asset["id"]]
            == [(asset["id"], asset["name"])], "上传后原Case未返回本次原文件")
    await expect(e.page.locator('#main .filerecord').filter(has_text=asset["name"])).to_have_count(1)
    e.business_unchanged(after_upload, "after_interstore_upload_render")
    return {"file": asset, "native": native, "security": security,
            "stored_blob": {"length": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}, "clamav_acceptance": False}


async def choose_proof(e, proof, category):
    asset = proof["file"]
    require(asset["category"] == category, "凭据类别误配")
    await live_choice(e, "evidence_id", asset["name"], asset["name"] + " · " +
        {"evidence": "业务凭据", "receipt": "收退款凭据"}[category], expected_value=asset["id"])


async def typed_new(e, roster, kind, values, *, warehouse=None):
    actor, store, _ = await roster.use("inventory2")
    title = "仓库" if kind == "warehouses" else "库位"
    await read_page(e, "masters/" + kind, "/api/masters/" + kind, title)
    await master_form(e, kind, title)
    if warehouse:
        await live_choice(e, "warehouse_id", warehouse["name"], warehouse["code"] + " · " + warehouse["name"], expected_value=warehouse["id"])
    guard = Guard(e, "destination_master_" + kind, actor, store,
        add={"master_" + kind: 1, "master_receipts": 1, "audit_logs": 1})
    row, native = await save_typed(e, actor, store, kind, values)
    native["guard"] = guard.finish()
    require(row["store_id"] == 2 and row["active"] == 1, "本店新仓位未实际启用")
    if warehouse:
        require(row["warehouse_id"] == warehouse["id"], "目的库位错挂外店仓")
    return row, native


async def destination_masters(e, roster, primary, token):
    warehouses, locations, evidence = {}, {}, {}
    for kind in ("vehicles", "materials"):
        warehouse, created = await typed_new(e, roster, "warehouses", {"code": "ITW-" + token + kind[:1],
            "name": "合成二店调拨" + ("整车仓" if kind == "vehicles" else "物资仓") + token,
            "warehouse_type": kind, "address": "本轮合成二店实际接收仓", "active": True})
        location, located = await typed_new(e, roster, "locations", {"code": "ITL-" + token + kind[:1],
            "name": "二店原接收位" + kind[:1] + token, "active": True}, warehouse=warehouse)
        warehouses[kind], locations[kind] = warehouse, location
        evidence[kind] = {"warehouse": warehouse, "location": location, "create_warehouse": created, "create_location": located}
    actor, store, _ = await roster.use("inventory2")
    await read_page(e, "master/items", "/api/flow/master/items", "物资目录")
    guard = Guard(e, "destination_zero_item", actor, store, add={"flow_items": 1, "audit_logs": 1})
    item, item_meta = await save_item(e, actor, store, {"sku": primary["sku"], "name": primary["name"],
        "unit": primary["unit"], "reorder": "0", "active": True})
    item_meta["guard"] = guard.finish()
    require(item["quantity_milli"] == item["inventory_value_cents"] == item["unit_cost_cents"] == 0,
            "新接收Item须零量值，不能预制收货结果")
    actor, store, _ = await roster.use("manager2")
    await read_page(e, "master/accounts", "/api/flow/master/accounts", "收付款账户")
    await e.click('[data-act="newmaster"][data-kind="accounts"]', "主管新增本店实际账户")
    await expect(e.page.locator("#modal-title")).to_have_text("新增收付款账户")
    name = "合成二店调拨银行" + token
    await field(e, "name", name)
    await select_value(e, '#modal [name="account_type"]', "bank", "明确银行账户类型")
    await checkbox(e, '#modal [name="active"]', True, "明确本店账户启用")
    guard = Guard(e, "destination_bank_account", actor, store, add={"flow_accounts": 1, "audit_logs": 1})
    body, request, native = await submit(e, "/api/flow/master/accounts", actor, store, guard, status=201, keyed=False)
    account = one(e, "flow_accounts", body["id"])
    require(request["values"] == {"name": name, "account_type": "bank", "active": True}
            and account["store_id"] == 2 and account["name"] == name and account["account_type"] == "bank"
            and account["active"] == 1, "新本店账户UI/API/DB不符")
    evidence.update(item=item, create_item=item_meta, account=account, create_account=native)
    return item, account, locations, evidence


async def activate_zero(e, roster, item, location):
    actor, store, _ = await roster.use("inventory2")
    await read_page(e, "warehouse", "/api/warehouse/cases", "库位与仓储作业")
    button = '#main [data-act="wh-new"][data-operation="activate"]'
    await visible_original_button(e, button, "真实库位启用")
    await e.click(button, "申请原零实物库位启用")
    await expect(e.page.locator("#modal-title")).to_have_text("真实库位启用")
    await select_value(e, '#modal [name="item_id"]', item["id"], "明确本店新零Item")
    await select_value(e, '#modal [name="location"]', location["id"], "明确本店实际库位")
    await field(e, "location_qty", "0")
    await field(e, "quantity", "0")
    reason = "新二店零实物定位，原调拨验收后才增加实物"
    await field(e, "reason", reason)
    due = await e.page.locator('#modal [name="due_date"]').input_value()
    guard = Guard(e, "destination_zero_activate_create", actor, store, add={"flow_cases": 1, "flow_tasks": 1,
        "warehouse_documents": 1, "warehouse_allocations": 1, "warehouse_allocation_lines": 1,
        "flow_events": 1, "audit_logs": 1, "flow_request_receipts": 1}, items={item["id"]}, new_kind="warehouse")
    body, request, created = await submit(e, "/api/warehouse/cases", actor, store, guard, status=201)
    case_id = body["id"]
    require(request == {"request_id": request["request_id"], "operation": "activate", "item_id": item["id"],
        "quantity_milli": 0, "locations": [{"location_id": location["id"], "quantity_milli": 0}], "reason": reason,
        "due_date": due}, "零启用原封包误配")
    created["receipt"] = original_receipt(e, "warehouse", actor, store, request, body, "warehouse_create", case_id=case_id)
    manager, store, task, handoff = await responsible(e, roster, "manager2", case_id, "wh_approve")
    proof = await upload(e, case_id, manager, store, "evidence", "零定位独立主管依据")
    view = await read_page(e, "warehouse/" + str(case_id), "/api/warehouse/cases/" + str(case_id), "真实库位启用")
    await e.click('[data-act="wh-action"][data-key="approve"]', "另一主管批准零实物启用")
    await expect(e.page.locator("#modal-title")).to_have_text("批准作业")
    await select_value(e, '#modal [name="evidence_id"]', proof["file"]["id"], "明确选择本单主管原凭据")
    updates = mutable_cases(e, (case_id,))
    updates.update(item_mutable(e, item["id"], case_id))
    guard = Guard(e, "destination_zero_activate_approve", manager, store, add={"warehouse_approvals": 1,
        "warehouse_enrollments": 1, "warehouse_balances": 1, "flow_events": 1, "audit_logs": 1,
        "flow_request_receipts": 1}, update=updates, cases={case_id}, items={item["id"]})
    body, request, approved = await submit(e, f'/api/warehouse/cases/{case_id}/commands/approve', manager, store, guard)
    require(request == {"request_id": request["request_id"], "version": view["version"], "values": {"evidence_id": proof["file"]["id"]}},
            "原零启用批准CAS/依据错误")
    approved["receipt"] = original_receipt(e, "warehouse", manager, store, request, body, "warehouse_approve", case_id=case_id)
    current = one(e, "flow_items", item["id"])
    enrollment = related(e, "warehouse_enrollments", "item_id", item["id"])
    balances = related(e, "warehouse_balances", "item_id", item["id"])
    require(body["state"] == "completed" and len(enrollment) == len(balances) == 1
            and enrollment[0]["case_id"] == case_id and enrollment[0]["actor_id"] == manager["id"]
            and enrollment[0]["baseline_quantity_milli"] == enrollment[0]["baseline_value_cents"] == 0
            and balances[0]["location_id"] == location["id"] and balances[0]["quantity_milli"] == balances[0]["value_cents"] == 0
            and current["quantity_milli"] == current["inventory_value_cents"] == 0
            and not related(e, "warehouse_entries", "case_id", case_id)
            and not related(e, "flow_stock_moves", "case_id", case_id), "零启用制造了库存/量值流水")
    require(one(e, "flow_tasks", task["id"])["done_by"] == manager["id"] and manager["id"] != actor["id"], "零定位未独立本人批准")
    return {"case_id": case_id, "create": created, "approve": approved, "handoff": handoff,
        "proof": proof, "enrollment": enrollment[0], "balances": balances, "physical_quantity": 0}


async def transfer_view(e, kind, transfer_id):
    route, api, title, table = ("vehicle-transfers", "/api/vehicle-transfers", "整车调拨", "vehicle_transfers") if kind == "vehicle" else (
        "transfers", "/api/transfers", "物资调拨", "material_transfers")
    view = await read_page(e, f'{route}/{transfer_id}', f'{api}/{transfer_id}', title)
    raw = one(e, table, transfer_id)
    store = int(await e.page.locator('#store').input_value())
    expected_case = raw["from_case_id"] if store == raw["from_store_id"] else raw["to_case_id"]
    require(view["id"] == raw["id"] and view["case_id"] == expected_case and view["version"] == raw["version"]
            and view["case_version"] == one(e, "flow_cases", expected_case)["version"] and view["status"] == raw["status"],
            "本店调拨原GET/DB状态/CAS不一致")
    await expect(e.page.locator('#main')).to_contain_text(raw["number"])
    return view, raw


async def transfer_new(e, roster, kind, source):
    actor = await roster.existing("inventory")
    route, api, title = ("vehicle-transfers", "/api/vehicle-transfers", "整车跨店调拨") if kind == "vehicle" else (
        "transfers", "/api/transfers", "跨店物资调拨")
    await read_page(e, route, api, title)
    act = "vehicle-transfer-new" if kind == "vehicle" else "transfer-new"
    await e.click(f'[data-act="{act}"]', "申请独立原" + title)
    await expect(e.page.locator("#modal-title")).to_have_text("申请整车跨店调拨" if kind == "vehicle" else "申请跨店物资调拨")
    await select_value(e, '#modal [name="vehicle_id"]' if kind == "vehicle" else '#modal [name="item_id"]', source["id"], "选择原有限实物来源")
    await select_value(e, '#modal [name="destination_store_id"]' if kind == "vehicle" else '#modal [name="destination"]', 2, "明确调入二店")
    if kind == "material":
        await field(e, "quantity", "1.000")
    reason = "本轮二店真实调拨" + (source["vin"] if kind == "vehicle" else source["sku"])
    await field(e, "reason", reason)
    await field(e, "due_date", today())
    add = {"flow_cases": 2, "flow_tasks": 2, "flow_events": 2, "audit_logs": 2, "material_transfer_receipts": 1}
    update, vins, items = {}, set(), set()
    if kind == "vehicle":
        before = vehicle_fact(e, source["id"], available=True)
        add["vehicle_transfers"] = 1
        update["vehicles"] = {source["id"]: set(VERSION)}
        custody = before["custody"]
        if custody:
            update["vehicle_custodies"] = {custody["id"]: {"version", "pending_transfer_id"}}
        else:
            add.update(vehicle_custodies=1, group_identities=(0, 1), group_identity_links=(0, 1))
        vins.add(source["vin"])
    else:
        add.update(material_transfers=1, material_transfer_lines=1)
        items.add(source["id"])
    guard = Guard(e, "transfer_create_" + kind, actor, 1, add=add, update=update,
        items=items, vins=vins, parties={1, 2}, new_kind="vehicle_transfer" if kind == "vehicle" else "material_transfer")
    body, request, native = await submit(e, api, actor, 1, guard, status=201)
    expected = {"request_id": request["request_id"], "destination_store_id": 2, "due_date": today(), "reason": reason}
    expected.update(vehicle_id=source["id"]) if kind == "vehicle" else expected.update(lines=[{"item_id": source["id"], "quantity_milli": 1000}])
    require(request == expected, "调拨申请原输入/封包错误")
    native["receipt"] = original_receipt(e, "transfer", actor, 1, request, body, "vehicle:create" if kind == "vehicle" else "create")
    view, raw = await transfer_view(e, kind, body["id"])
    require(raw["from_store_id"] == 1 and raw["to_store_id"] == 2 and raw["requested_by"] == actor["id"]
            and raw["status"] == "requested" and raw["source_approved_by"] is None and raw["destination_approved_by"] is None,
            "申请冒充批准/运输事实")
    cases = [one(e, "flow_cases", raw[k]) for k in ("from_case_id", "to_case_id")]
    require({c["store_id"] for c in cases} == {1, 2} and all(c["created_by"] == actor["id"] for c in cases), "协调原单两店/申请人不符")
    if kind == "vehicle":
        require(vehicle_fact(e, source["id"])["custody"]["pending_transfer_id"] == raw["id"], "申请未形成明确VIN占用")
    else:
        line = related(e, "material_transfer_lines", "transfer_id", raw["id"])
        require(len(line) == 1 and line[0]["source_item_id"] == source["id"] and line[0]["quantity_milli"] == 1000
                and all(line[0][k] == source[k] for k in ("sku", "name", "unit")), "原物资调拨行冻结来源错误")
    return raw, {"create": native, "initial_api": view, "case_ids": [c["id"] for c in cases]}


def task_key(kind, action):
    if kind == "vehicle":
        return {"approve": "vehicle_approve", "dispatch": "vehicle_dispatch", "accept": "vehicle_receive",
            "reject": "vehicle_receive", "return_ship": "vehicle_return_ship", "return_receive": "vehicle_return_receive"}[action]
    return {"approve": "transfer_approve", "dispatch": "transfer_dispatch", "receive": "transfer_receive",
            "return_ship": "transfer_receive", "return_receive": "transfer_return"}[action]


def transfer_updates(e, kind, raw, action, store, *, item_id=None):
    cases = (raw["from_case_id"], raw["to_case_id"])
    update = mutable_cases(e, cases)
    table = "vehicle_transfers" if kind == "vehicle" else "material_transfers"
    fields = VERSION | {"status"}
    if action == "approve":
        fields = fields | {"source_approved_by" if store == 1 else "destination_approved_by"}
    if kind == "vehicle":
        custody = e.db.rows("SELECT * FROM vehicle_custodies WHERE vin=?", (raw["vin"],))
        require(len(custody) == 1, "在办调拨缺共享Custody")
        cols = {"version"}
        if action in {"dispatch", "accept", "return_receive"}:
            cols |= {"current_vehicle_id", "current_store_id"}
        if action in {"accept", "return_receive"}:
            cols |= {"generation", "pending_transfer_id"}
            fields |= {"received_vehicle_id"}
            update["flow_cases"][raw["from_case_id"] if store == 1 else raw["to_case_id"]] |= {"vehicle_id"}
        update["vehicle_custodies"] = {custody[0]["id"]: cols}
        if action == "dispatch":
            vehicle_id = raw["source_vehicle_id"]
            update["vehicles"] = {vehicle_id: VERSION | {"approval_state"}}
            positions = related(e, "vehicle_positions", "vehicle_id", vehicle_id)
            update["vehicle_positions"] = {r["id"]: VERSION | {"status", "location_id"} for r in positions}
    elif item_id is not None:
        update.update(item_mutable(e, item_id, raw["from_case_id"] if store == 1 else raw["to_case_id"]))
    update[table] = {raw["id"]: fields}
    return update


def sync_events(e, guard, raw, actor, action, kind):
    expected = {raw["from_case_id"]: 1, raw["to_case_id"]: 2}
    events = guard.new["flow_events"]
    require(len(events) == 2 and {r["case_id"] for r in events} == set(expected)
            and all(r["actor_id"] == actor["id"] and r["store_id"] == expected[r["case_id"]]
                and r["action"] == ("vehicle_" if kind == "vehicle" else "transfer_") + action for r in events),
            "协调事件缺双方本地Case/本次员工/动作")
    audits = guard.new["audit_logs"]
    require(len(audits) == 2 and {r["entity_id"] for r in audits} == set(expected)
            and all(r["actor_id"] == actor["id"] and r["store_id"] == expected[r["entity_id"]]
                and r["entity_type"] == "flow" and r["action"] == "flow_" + events[0]["action"] for r in audits),
            "协调审计没有准确双店原单")
    return {"event_ids": [r["id"] for r in events], "audit_ids": [r["id"] for r in audits]}


async def prepare(e, roster, actor_key, case_id, item_id, location_id, quantity, purpose):
    actor, store, _ = await roster.use(actor_key)
    await case_page(e, case_id)
    route, path = "warehouse-allocation/" + str(case_id), "/api/warehouse/allocations/" + str(case_id)
    view = await read_page(e, route, path, "准备物资库位")
    require(purpose in view["purposes"] and any(r["id"] == item_id and r["enabled"] for r in view["items"]),
            "原库位准备不提供本次物资/原动作")
    button = f'[data-act="wh-allocate"][data-id="{item_id}"]'
    await expect(e.page.locator(button)).to_be_visible()
    await e.click(button, "按本次原业务精确数量准备位置")
    await expect(e.page.locator("#modal-title")).to_have_text("准备库位（尚未实际收发）")
    await select_value(e, '#modal [name="purpose"]', purpose, "明确原收发动作")
    await field(e, "quantity", qty(abs(quantity)))
    await select_value(e, '#modal [name="location"]', location_id, "明确本店原实际库位")
    await field(e, "location_qty", qty(abs(quantity)))
    update = {"flow_cases": {case_id: set(VERSION)}, "warehouse_allocations": {
        r["id"]: VERSION | {"status"} for r in related(e, "warehouse_allocations", "case_id", case_id)
        if r["item_id"] == item_id and r["purpose"] == purpose and r["status"] == "prepared"}}
    guard = Guard(e, "transfer_prepare_" + purpose, actor, store, add={"warehouse_allocations": 1,
        "warehouse_allocation_lines": 1, "flow_events": 1, "audit_logs": 1, "flow_request_receipts": 1},
        update=update, cases={case_id}, items={item_id})
    body, request, native = await submit(e, path, actor, store, guard)
    require(request == {"request_id": request["request_id"], "version": view["version"], "values": {
        "item_id": item_id, "quantity_milli": quantity, "purpose": purpose,
        "locations": [{"location_id": location_id, "quantity_milli": abs(quantity)}]}}, "本次库位准备封包/原CAS不符")
    native["receipt"] = original_receipt(e, "warehouse", actor, store, request, body, "warehouse_allocation", case_id=case_id)
    allocation = guard.new["warehouse_allocations"][0]
    require(allocation["quantity_milli"] == quantity and allocation["purpose"] == purpose
            and allocation["status"] == "prepared" and allocation["stock_move_id"] is None,
            "位置准备被误记实际实物")
    return {"allocation": allocation, "lines": guard.new["warehouse_allocation_lines"], "native": native,
            "stock_and_cash_preserved": True}


async def transfer_action(e, roster, kind, raw, action, actor_key, *, values=None, item_id=None, location=None):
    actor, store, _ = await roster.use(actor_key)
    case_id = raw["from_case_id"] if store == 1 else raw["to_case_id"]
    actor, store, task, handoff = await responsible(e, roster, actor_key, case_id, task_key(kind, action))
    proof = None
    if action != "approve":
        proof = await upload(e, case_id, actor, store, "evidence", kind + "-" + action)
    view, raw = await transfer_view(e, kind, raw["id"])
    require(action in view["actions"], "当前原调拨GET没有该动作")
    act = "vehicle-transfer-action" if kind == "vehicle" else "transfer-action"
    await e.click(f'[data-act="{act}"][data-key="{action}"]', "本人办理" + LABELS[kind][action])
    await expect(e.page.locator("#modal-title")).to_have_text(LABELS[kind][action])
    submitted = {"reason": "本轮原" + LABELS[kind][action] + "，按本次原来源实际核对"}
    await field(e, "reason", submitted["reason"])
    if proof:
        await choose_proof(e, proof, "evidence")
        submitted["evidence_id"] = proof["file"]["id"]
    if kind == "vehicle" and action != "approve":
        await field(e, "vin", raw["vin"])
        submitted["vin"] = raw["vin"]
        if location is not None:
            await select_value(e, '#modal [name="location_id"]', location, "核对本店实际接车库位")
            submitted["location_id"] = location
    if kind == "material":
        if action == "receive":
            receive = values["lines"][0]
            for prefix in ("accept", "reject"):
                await field(e, prefix + "_" + str(receive["line_id"]), qty(receive[prefix + "_milli"]))
            await select_value(e, '#modal [name="item_' + str(receive["line_id"]) + '"]', receive["item_id"], "选本店同SKU/名称/单位接收Item")
        elif action in {"return_ship", "return_receive"}:
            await select_value(e, '#modal [name="target"]', values["rejection_id" if action == "return_ship" else "shipment_id"], "核对本次原拒收/退运批次")
            if action == "return_receive":
                await field(e, "returned_qty", qty(values["quantity_milli"]))
                await checkbox(e, '#modal [name="passed"]', True, "本人明确核对退回质量合格")
        submitted.update(values or {})
    add = {"flow_events": 2, "audit_logs": 2, "flow_tasks": (0, 2), "material_transfer_receipts": 1}
    if kind == "vehicle" and action != "approve":
        add["vehicle_movements"] = 1
        if action == "dispatch":
            add["vehicle_position_entries"] = 1
        elif action in {"accept", "return_receive"}:
            add.update(vehicles=1, vehicle_positions=1, vehicle_position_entries=1, group_identity_links=1)
            if action == "accept":
                add["vehicle_transfer_settlements"] = 2
    elif kind == "material" and action != "approve":
        add["material_transfer_movements"] = 2 if action == "receive" and values["lines"][0]["reject_milli"] else 1
        if action in {"dispatch", "receive", "return_receive"}:
            add["flow_stock_moves"] = 1
            balances = related(e, "warehouse_balances", "item_id", item_id)
            require(len(balances) <= 500, "真实位置有限边界超限")
            add["warehouse_entries"] = (1, max(1, len(balances)))
        if action == "receive":
            add["material_transfer_settlements"] = 2
    update = transfer_updates(e, kind, raw, action, store, item_id=item_id)
    guard = Guard(e, "transfer_" + kind + "_" + action, actor, store, add=add, update=update,
        cases={raw["from_case_id"], raw["to_case_id"]}, items={item_id} if item_id else (),
        vins={raw["vin"]} if kind == "vehicle" else (), parties={1, 2}, transfers={raw["id"]})
    api = "/api/vehicle-transfers" if kind == "vehicle" else "/api/transfers"
    body, request, native = await submit(e, f'{api}/{raw["id"]}/actions/{action}', actor, store, guard)
    require(request == {"request_id": request["request_id"], "version": view["version"],
        "case_version": view["case_version"], "values": submitted}, "原调拨当前双CAS/输入封包误配")
    receipt_action = ("vehicle:" if kind == "vehicle" else "") + str(raw["id"]) + ":" + action
    native.update(receipt=original_receipt(e, "transfer", actor, store, request, body, receipt_action),
        sync=sync_events(e, guard, raw, actor, action, kind), handoff=handoff)
    current_view, current = await transfer_view(e, kind, raw["id"])
    require(body["version"] == current["version"] and body["case_version"] == current_view["case_version"], "提交后原GET/CAS错位")
    if action == "approve":
        require(current["source_approved_by" if store == 1 else "destination_approved_by"] == actor["id"]
                and actor["id"] != current["requested_by"], "审批非本店独立主管")
    elif kind == "vehicle":
        move = guard.new["vehicle_movements"][0]
        require(move["kind"] == action and move["case_id"] == case_id and move["evidence_id"] == proof["file"]["id"], "整车原实物流水误配")
    else:
        for move in guard.new["material_transfer_movements"]:
            require(move["evidence_id"] == proof["file"]["id"] and move["line_id"] == related(e, "material_transfer_lines", "transfer_id", raw["id"])[0]["id"],
                    "物资原批交接引用不符")
    if kind == "vehicle" or action in {"approve", "dispatch"} or current["status"] == "completed":
        done = one(e, "flow_tasks", task["id"])
        # Material synchronize closes its remaining tasks using original
        # close_tasks(status=cancelled); this does not cancel the completed case.
        expected_status = "cancelled" if kind == "material" and current["status"] == "completed" else "done"
        require(done["status"] == expected_status and done["done_by"] == actor["id"], "本次原Task未按原服务由本人结束")
    return current, {"native": native, "proof": proof, "after_api": current_view,
        "new_movements": guard.new.get("vehicle_movements" if kind == "vehicle" else "material_transfer_movements", []),
        "new_stock_moves": guard.new.get("flow_stock_moves", []), "new_entries": guard.new.get("warehouse_entries", [])}


async def approved_transfer(e, roster, kind, raw):
    first, approved1 = await transfer_action(e, roster, kind, raw, "approve", "manager")
    require(first["source_approved_by"] is not None and first["destination_approved_by"] is None and first["status"] == "requested",
            "首方批准不能冒另一方批准")
    both, approved2 = await transfer_action(e, roster, kind, first, "approve", "manager2")
    require(both["status"] == "approved" and both["source_approved_by"] != both["destination_approved_by"], "双店独立批准未闭合")
    return both, [approved1, approved2]


def vehicle_received(e, raw, before, store, location, status):
    require(raw["status"] == status and raw["received_vehicle_id"] != before["vehicle"]["id"], "实际接收未建立新代次")
    result = vehicle_fact(e, raw["received_vehicle_id"])
    old = one(e, "vehicles", before["vehicle"]["id"])
    vehicle, custody, position = result["vehicle"], result["custody"], result["position"]
    frozen = json.loads(raw["snapshot"])
    require(all(vehicle[k] == v for k, v in frozen.items()) and vehicle["store_id"] == store
            and vehicle["inventory_generation"] == before["vehicle"]["inventory_generation"] + 1
            and vehicle["approval_state"] == "approved" and old["approval_state"] == "void"
            and old["store_id"] == 1 and old["inventory_generation"] == before["vehicle"]["inventory_generation"],
            "原实车冻结事实/成本/店/新旧代次被覆盖")
    require(custody["current_vehicle_id"] == vehicle["id"] and custody["current_store_id"] == store
            and custody["pending_transfer_id"] is None and custody["generation"] == vehicle["inventory_generation"]
            and (before["custody"] is None or custody["identity_id"] == before["custody"]["identity_id"])
            and position["status"] == "stored" and position["location_id"] == location,
            "共享身份/当前Custody/实际库位不符")
    link = e.db.rows("SELECT * FROM group_identity_links WHERE local_kind='vehicle' AND local_id=?", (vehicle["id"],))
    require(len(link) == 1 and link[0]["identity_id"] == custody["identity_id"], "新代次没有同原VIN共享身份")
    entries = result["entries"]
    require(len(entries) == 1 and entries[0]["quantity"] == 1 and entries[0]["inventory_delta"] == 0
            and entries[0]["value_cents"] == old["purchase_cost_cents"], "位置接收重复计入库存/改变原成本")
    for case_id in (raw["from_case_id"], raw["to_case_id"]):
        require(one(e, "flow_cases", case_id)["state"] == "completed"
                and not any(t["status"] == "open" for t in related(e, "flow_tasks", "case_id", case_id)), "双店原单/任务尚未结束")
    return result


async def vehicle_chain(e, roster, source, destination_location, source_location, *, reject=False):
    before = vehicle_fact(e, source["id"], available=True)
    raw, evidence = await transfer_new(e, roster, "vehicle", source)
    raw, approvals = await approved_transfer(e, roster, "vehicle", raw)
    raw, dispatch = await transfer_action(e, roster, "vehicle", raw, "dispatch", "inventory")
    sent = dispatch["new_movements"][0]
    pending = vehicle_fact(e, source["id"])
    require(raw["status"] == "transit" and sent["quantity"] == -1 and sent["value_cents"] == -source["purchase_cost_cents"]
            and pending["vehicle"]["approval_state"] == "void" and pending["position"]["status"] == "exited"
            and pending["custody"]["current_vehicle_id"] is None and pending["custody"]["current_store_id"] is None
            and pending["custody"]["pending_transfer_id"] == raw["id"], "实际发车/在途/原成本不符")
    evidence.update(before=before, approvals=approvals, dispatch=dispatch)
    if not reject:
        raw, accepted = await transfer_action(e, roster, "vehicle", raw, "accept", "inventory2", location=destination_location)
        result = vehicle_received(e, raw, before, 2, destination_location, "accepted")
        settlement = related(e, "vehicle_transfer_settlements", "transfer_id", raw["id"])
        require(len(settlement) == 2 and {(r["store_id"], r["counterparty_store_id"], r["amount_cents"]) for r in settlement}
                == {(1, 2, source["purchase_cost_cents"]), (2, 1, -source["purchase_cost_cents"])}, "实际整车验收双方往来不等额")
        evidence.update(accept=accepted, received=result, settlements=settlement)
    else:
        raw, rejected = await transfer_action(e, roster, "vehicle", raw, "reject", "inventory2")
        require(raw["status"] == "rejected", "实际拒收状态错误")
        raw, returned = await transfer_action(e, roster, "vehicle", raw, "return_ship", "inventory2")
        require(raw["status"] == "return_transit", "实际退运状态错误")
        raw, received = await transfer_action(e, roster, "vehicle", raw, "return_receive", "inventory", location=source_location)
        result = vehicle_received(e, raw, before, 1, source_location, "returned")
        for step in (rejected, returned):
            move = step["new_movements"][0]
            require(move["quantity"] == move["value_cents"] == 0 and move["vehicle_id"] is None, "拒收/退运造目的库存")
        require(not related(e, "vehicle_transfer_settlements", "transfer_id", raw["id"]), "拒收原返制造验收往来")
        evidence.update(reject=rejected, return_ship=returned, return_receive=received, received=result, settlements=[])
    evidence["transfer"] = raw
    return raw, evidence


async def stock_view(e, roster, actor_key, item_id):
    await roster.use(actor_key)
    view = await read_page(e, "warehouse-item/" + str(item_id), f'/api/warehouse/items/{item_id}/stock', "物资真实库位")
    item = one(e, "flow_items", item_id)
    balances = related(e, "warehouse_balances", "item_id", item_id)
    require(view["quantity_milli"] == item["quantity_milli"] and view["name"] == item["name"]
            and view["sku"] == item["sku"] and view["enabled"] is True
            and sum(r["quantity_milli"] for r in balances) == item["quantity_milli"]
            and sum(r["value_cents"] for r in balances) == item["inventory_value_cents"], "原Item/API/库位总量值不符")
    for balance in view["balances"]:
        source = one(e, "warehouse_balances", balance["id"])
        require(balance["quantity_milli"] == source["quantity_milli"]
                and ("value_cents" not in balance or balance["value_cents"] == source["value_cents"]), "原库位UI/API/DB不一致")
    await expect(e.page.locator('#main')).to_contain_text(item["name"])
    return {"api": view, "item": item, "balances": balances}


def stock_post(e, result, *, item_id, case_id, quantity, value, purpose, original=None):
    moves = result["new_stock_moves"]
    require(len(moves) == 1, "每次实际物资过账须唯一原StockMove")
    move = moves[0]
    require(move["item_id"] == item_id and move["case_id"] == case_id and move["quantity_milli"] == quantity
            and move["value_cents"] == value and move["purpose"] == purpose and move["original_id"] == original
            and move["unit_cost_cents"] == abs(value) * 1000 // abs(quantity), "原StockMove数量/成本/原批来源错误")
    entries = result["new_entries"]
    require(entries and all(r["stock_move_id"] == move["id"] for r in entries)
            and sum(r["quantity_milli"] for r in entries) == quantity and sum(r["value_cents"] for r in entries) == value,
            "库位实际/均价分录未对上唯一库存过账")
    return move


async def material_dispatch(e, roster, primary):
    actor = await roster.existing("inventory")
    stock = await stock_view(e, roster, "inventory", primary["item_id"])
    source = stock["item"]
    require(all(source[k] == primary[k] for k in ("sku", "name", "unit")) and source["store_id"] == 1
            and source["active"] == 1 and stock["api"]["available_milli"] >= 1000, "原物资源现场可用量/身份不满足")
    bin_rows = [b for b in stock["balances"] if b["location_id"] == primary["source_location_id"]]
    held = e.db.rows("SELECT coalesce(sum(quantity_milli),0) AS quantity FROM warehouse_holds WHERE item_id=? AND location_id=?",
                    (primary["item_id"], primary["source_location_id"]))[0]["quantity"]
    require(len(bin_rows) == 1 and bin_rows[0]["quantity_milli"] - held >= 1000, "原源实际库位可用量不足1000")
    raw, evidence = await transfer_new(e, roster, "material", source)
    raw, approvals = await approved_transfer(e, roster, "material", raw)
    prepared = await prepare(e, roster, "inventory", raw["from_case_id"], source["id"], primary["source_location_id"], -1000, "transfer_out")
    current = one(e, "flow_items", source["id"])
    value = current["inventory_value_cents"] * 1000 // current["quantity_milli"]
    require(value > 0 and value * 500 // 1000 > 0 and value * 750 // 1000 - value * 500 // 1000 > 0,
            "两实收批须各有真实正成本才能形成三笔正清算")
    raw, dispatch = await transfer_action(e, roster, "material", raw, "dispatch", "inventory", item_id=source["id"])
    stock_move = stock_post(e, dispatch, item_id=source["id"], case_id=raw["from_case_id"], quantity=-1000,
        value=-value, purpose="transfer_out")
    movement = dispatch["new_movements"][0]
    require(movement["kind"] == "dispatch" and movement["quantity_milli"] == 1000 and movement["value_cents"] == value
            and movement["stock_move_id"] == stock_move["id"] and movement["original_id"] is None
            and raw["status"] == "transit", "原物资发运批次/在途错误")
    after = one(e, "flow_items", source["id"])
    require(after["quantity_milli"] == current["quantity_milli"] - 1000
            and after["inventory_value_cents"] == current["inventory_value_cents"] - value, "源Item实际发出未减原数量/成本")
    evidence.update(source_before=current, source_stock=stock, approvals=approvals, prepare=prepared,
        dispatch=dispatch, dispatch_movement=movement, transfer=raw)
    return raw, evidence


async def material_receive_return(e, roster, raw, evidence, destination, location, primary):
    dispatch = evidence["dispatch_movement"]
    line = related(e, "material_transfer_lines", "transfer_id", raw["id"])[0]
    parts, accepted = [], []
    for quantity, rejected, value in ((500, 0, dispatch["value_cents"] * 500 // 1000),
            (250, 250, dispatch["value_cents"] * 750 // 1000 - dispatch["value_cents"] * 500 // 1000)):
        prepared = await prepare(e, roster, "inventory2", raw["to_case_id"], destination["id"], location["id"], quantity, "transfer_in")
        raw, received = await transfer_action(e, roster, "material", raw, "receive", "inventory2", item_id=destination["id"], values={
            "lines": [{"line_id": line["id"], "item_id": destination["id"], "accept_milli": quantity, "reject_milli": rejected}]})
        stock_move = stock_post(e, received, item_id=destination["id"], case_id=raw["to_case_id"], quantity=quantity,
            value=value, purpose="transfer_in")
        accept = next(r for r in received["new_movements"] if r["kind"] == "accept")
        require(accept["quantity_milli"] == quantity and accept["value_cents"] == value
                and accept["original_id"] == dispatch["id"] and accept["stock_move_id"] == stock_move["id"], "分批真实验收成本或原批引用错误")
        accepted.append(accept)
        parts.append({"prepare": prepared, "receive": received})
    rejects = [r for r in related(e, "material_transfer_movements", "transfer_id", raw["id"]) if r["kind"] == "reject"]
    require(len(rejects) == 1 and rejects[0]["quantity_milli"] == 250
            and rejects[0]["value_cents"] == dispatch["value_cents"] - sum(r["value_cents"] for r in accepted)
            and rejects[0]["stock_move_id"] is None and rejects[0]["original_id"] == dispatch["id"], "拒收250不能成为目的库存")
    raw, returned = await transfer_action(e, roster, "material", raw, "return_ship", "inventory2", values={"rejection_id": rejects[0]["id"]})
    shipment = returned["new_movements"][0]
    require(shipment["kind"] == "return_ship" and shipment["original_id"] == rejects[0]["id"]
            and shipment["quantity_milli"] == 250 and shipment["value_cents"] == rejects[0]["value_cents"]
            and shipment["stock_move_id"] is None, "原拒收退运串批/制造库存")
    prepared = await prepare(e, roster, "inventory", raw["from_case_id"], primary["item_id"], primary["source_location_id"], 250, "transfer_return")
    raw, received = await transfer_action(e, roster, "material", raw, "return_receive", "inventory", item_id=primary["item_id"], values={
        "shipment_id": shipment["id"], "quantity_milli": 250, "passed": True})
    back = received["new_movements"][0]
    stock_post(e, received, item_id=primary["item_id"], case_id=raw["from_case_id"], quantity=250,
        value=rejects[0]["value_cents"], purpose="transfer_return", original=dispatch["stock_move_id"])
    require(back["kind"] == "return_receive" and back["original_id"] == shipment["id"]
            and back["quantity_milli"] == 250 and back["value_cents"] == shipment["value_cents"] and raw["status"] == "completed",
            "原返实际入库引用/成本/结束错误")
    source_stock = await stock_view(e, roster, "inventory", primary["item_id"])
    dest_stock = await stock_view(e, roster, "inventory2", destination["id"])
    before = evidence["source_before"]
    accepted_value = sum(r["value_cents"] for r in accepted)
    require(source_stock["item"]["quantity_milli"] == before["quantity_milli"] - 750
            and source_stock["item"]["inventory_value_cents"] == before["inventory_value_cents"] - accepted_value
            and dest_stock["item"]["quantity_milli"] == 750 and dest_stock["item"]["inventory_value_cents"] == accepted_value,
            "双店原调拨净量/成本不守恒")
    require(sum(r["quantity_milli"] for r in accepted) + back["quantity_milli"] == dispatch["quantity_milli"]
            and accepted_value + back["value_cents"] == dispatch["value_cents"], "原批发出不等于实收加原返")
    settlement = related(e, "material_transfer_settlements", "transfer_id", raw["id"])
    require(len(settlement) == 4, "两实收批次应独立四条往来")
    for accept in accepted:
        pair = [r for r in settlement if r["movement_id"] == accept["id"]]
        require(len(pair) == 2 and {(r["store_id"], r["counterparty_store_id"], r["amount_cents"]) for r in pair}
                == {(1, 2, accept["value_cents"]), (2, 1, -accept["value_cents"])}, "原验收批次双方往来未唯一配对")
    for case_id in (raw["from_case_id"], raw["to_case_id"]):
        require(one(e, "flow_cases", case_id)["state"] == "completed"
                and not any(t["status"] == "open" for t in related(e, "flow_tasks", "case_id", case_id)), "物资双方原单/Task未闭合")
    await roster.use("manager2")
    api, raw = await transfer_view(e, "material", raw["id"])
    line_view = api["lines"][0]
    require(line_view["accepted_milli"] == 750 and line_view["returned_milli"] == 250
            and line_view["uninspected_milli"] == line_view["return_in_transit_milli"] == line_view["return_pending_milli"] == 0
            and line_view["accepted_value_cents"] == accepted_value and line_view["in_transit_value_cents"] == 0,
            "原调拨最终非空UI/API明细与DB不匹配")
    return raw, {**evidence, "transfer": raw, "batches": parts, "rejection": rejects[0], "return_ship": returned,
        "return_prepare": prepared, "return_receive": received, "accepted_movements": accepted,
        "settlements": settlement, "source_final_stock": source_stock, "destination_final_stock": dest_stock, "final_api": api}


async def clearing_view(e, order_id):
    view = await read_page(e, "clearing/" + str(order_id), "/api/reconciliation/clearing/" + str(order_id), "店间实际清算")
    order = one(e, "interstore_clearing_orders", order_id)
    store = int(await e.page.locator('#store').input_value())
    case_id = order["payer_case_id"] if store == order["payer_store_id"] else order["receiver_case_id"]
    require(view["id"] == order_id and view["version"] == order["version"] and view["case_id"] == case_id
            and view["case_version"] == one(e, "flow_cases", case_id)["version"] and view["status"] == order["status"]
            and view["amount_cents"] == order["amount_cents"], "清算原GET/本店Case/CAS/金额错误")
    return view, order


def clearing_parent_update(kind, transfer_id):
    return {"material_transfers": {transfer_id: set(VERSION)}} if kind == "material" else {}


async def clearing_create(e, roster, kind, origin):
    actor, store, _ = await roster.use("finance2")
    require(origin["store_id"] == 2 and origin["counterparty_store_id"] == 1 and origin["amount_cents"] < 0, "本店原清算应付来源错误")
    listing = await read_page(e, "clearing", "/api/reconciliation/origins", "店间实际清算")
    current = [r for r in listing["items"] if r["origin_kind"] == kind and r["origin_id"] == origin["id"]]
    amount = -origin["amount_cents"]
    require(len(current) == 1 and current[0]["available_cents"] == current[0]["total_cents"] == amount
            and current[0]["reserved_cents"] == current[0]["settled_cents"] == 0
            and current[0]["transfer_id"] == origin["transfer_id"], "当前原往来可清额度/源ID错误")
    await e.click(f'[data-act="clearing-new"][data-kind="{kind}"][data-id="{origin["id"]}"]', "财务从本条实际验收应付申请清算")
    await expect(e.page.locator("#modal-title")).to_have_text("申请部分或全部调拨清算")
    await field(e, "amount", f'{amount // 100}.{amount % 100:02d}')
    await field(e, "due_date", today())
    reason = "本次原" + kind + "验收条目" + str(origin["id"]) + "逐笔全额清算"
    await field(e, "reason", reason)
    guard = Guard(e, "clearing_create_" + kind, actor, store, add={"interstore_clearing_buckets": 1,
        "interstore_clearing_orders": 1, "flow_cases": 2, "flow_tasks": 2, "reconciliation_events": 1,
        "flow_events": 1, "audit_logs": 1, "reconciliation_receipts": 1},
        update=clearing_parent_update(kind, origin["transfer_id"]), parties={1, 2}, new_kind="interstore_clearing")
    body, request, native = await submit(e, "/api/reconciliation/clearing", actor, store, guard, status=201)
    require(request == {"request_id": request["request_id"], "origin_kind": kind, "origin_id": origin["id"],
        "amount_cents": amount, "due_date": today(), "reason": reason}, "原清算申请封包/源SettlementID误配")
    native["receipt"] = original_receipt(e, "clearing", actor, store, request, body, "clearing_create")
    view, order = await clearing_view(e, body["id"])
    bucket = one(e, "interstore_clearing_buckets", order["bucket_id"])
    table = "vehicle_transfer_settlements" if kind == "vehicle" else "material_transfer_settlements"
    creditor = one(e, table, bucket["creditor_origin_id"])
    require(bucket["debtor_origin_id"] == origin["id"] and bucket["origin_kind"] == kind
            and creditor["store_id"] == 1 and creditor["counterparty_store_id"] == 2 and creditor["amount_cents"] == amount
            and creditor["transfer_id"] == origin["transfer_id"] and (kind == "vehicle" or creditor["movement_id"] == origin["movement_id"])
            and bucket["reserved_cents"] == bucket["total_cents"] == amount and bucket["settled_cents"] == 0
            and order["payer_store_id"] == 2 and order["receiver_store_id"] == 1 and order["status"] == "requested"
            and not related(e, "interstore_clearing_cash", "order_id", order["id"])
            and not related(e, "interstore_clearing_offsets", "order_id", order["id"]), "原申请占额不能冒现金/对账核销")
    return order, {"origin": origin, "paired_origin": creditor, "native": native, "initial_bucket": bucket, "initial_api": view}


async def clearing_money(e, roster, order, action, key, account, kind, transfer_id):
    actor, store, _ = await roster.use(key)
    case_id = order["payer_case_id"] if action == "pay" else order["receiver_case_id"]
    actor, store, task, handoff = await responsible(e, roster, key, case_id, "clearing_" + action)
    proof = await upload(e, case_id, actor, store, "receipt", "清算实际" + action)
    view, order = await clearing_view(e, order["id"])
    await e.click(f'[data-act="clearing-action"][data-key="{action}"]', "本店财务确认自己的实际款项")
    await expect(e.page.locator("#modal-title")).to_have_text("确认本店实际付款" if action == "pay" else "确认本店实际到账")
    await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
    await choose_proof(e, proof, "receipt")
    reference = "IT-" + action + "-" + uuid.uuid4().hex[:16]
    reason = "本店本次原清算实际" + ("支出" if action == "pay" else "到账") + "，与对店资金记录分开"
    await field(e, "reference", reference)
    await field(e, "reason", reason)
    update = mutable_cases(e, (order["payer_case_id"], order["receiver_case_id"]))
    update.update(clearing_parent_update(kind, transfer_id))
    update.update(interstore_clearing_orders={order["id"]: VERSION | {"status"}},
        interstore_clearing_buckets={order["bucket_id"]: VERSION | {"reserved_cents", "settled_cents"}},
        flow_accounts={account["id"]: set(VERSION)})
    add = {"cash_entries": 1, "interstore_clearing_cash": 1, "reconciliation_events": 1,
        "reconciliation_receipts": 1, "flow_events": 1, "audit_logs": 1}
    if action == "receive":
        add["interstore_clearing_offsets"] = 2
    guard = Guard(e, "clearing_actual_" + action, actor, store, add=add, update=update,
        cases={order["payer_case_id"], order["receiver_case_id"]}, parties={1, 2}, orders={order["id"]})
    body, request, native = await submit(e, f'/api/reconciliation/clearing/{order["id"]}/actions/{action}', actor, store, guard)
    require(request == {"request_id": request["request_id"], "version": view["version"], "case_version": view["case_version"],
        "values": {"account_id": account["id"], "reference": reference, "evidence_id": proof["file"]["id"], "reason": reason}},
            "实际原清算当前双CAS/金额来源/凭据封包错误")
    native["receipt"] = original_receipt(e, "clearing", actor, store, request, body, f'clearing:{order["id"]}:{action}')
    direction = "out" if action == "pay" else "in"
    cash, link = guard.new["cash_entries"][0], guard.new["interstore_clearing_cash"][0]
    require(cash["store_id"] == link["store_id"] == store and cash["created_by"] == link["actor_id"] == actor["id"]
            and cash["approval_state"] == "approved" and cash["category"] == "interstore_clearing"
            and cash["direction"] == link["direction"] == direction and cash["amount_cents"] == link["amount_cents"] == order["amount_cents"]
            and cash["account"] == account["name"] and cash["voucher_no"] == link["reference"] == reference
            and link["account_id"] == account["id"] and link["evidence_id"] == proof["file"]["id"]
            and link["cash_id"] == cash["id"] and link["order_id"] == order["id"]
            and cash["business_date"] == link["business_date"] == today(), "本店真实Cash/原关联/账户/来源错误")
    require(one(e, "flow_tasks", task["id"])["status"] == "done"
            and one(e, "flow_tasks", task["id"])["done_by"] == actor["id"], "本店财务Task未由本人实际办理")
    view, order = await clearing_view(e, order["id"])
    bucket = one(e, "interstore_clearing_buckets", order["bucket_id"])
    offsets = related(e, "interstore_clearing_offsets", "order_id", order["id"])
    if action == "pay":
        require(order["status"] == "paid" and bucket["reserved_cents"] == order["amount_cents"]
                and bucket["settled_cents"] == 0 and not offsets, "付款在途被提前当对店到账/核销")
    else:
        require(order["status"] == "settled" and bucket["reserved_cents"] == 0 and bucket["settled_cents"] == order["amount_cents"]
                and len(offsets) == 2 and {(r["store_id"], r["origin_id"], r["amount_cents"]) for r in offsets} == {
                    (2, bucket["debtor_origin_id"], order["amount_cents"]), (1, bucket["creditor_origin_id"], -order["amount_cents"])},
                "双方实际到账后原offset/占额/余额错误")
        require(all(one(e, "flow_cases", key_id)["state"] == "completed" for key_id in (order["payer_case_id"], order["receiver_case_id"])),
                "实际到账双店Case未完成")
    await expect(e.page.locator('#main')).to_contain_text(reference)
    return order, {"native": native, "handoff": handoff, "proof": proof, "cash": cash, "clearing_cash": link,
        "after_bucket": bucket, "offsets": offsets, "after_api": view}


async def clear_origin(e, roster, kind, origin, account2, account1):
    order, evidence = await clearing_create(e, roster, kind, origin)
    order, pay = await clearing_money(e, roster, order, "pay", "finance2", account2, kind, origin["transfer_id"])
    await roster.existing("finance")
    order, receive = await clearing_money(e, roster, order, "receive", "finance", account1, kind, origin["transfer_id"])
    require(pay["cash"]["id"] != receive["cash"]["id"] and pay["cash"]["store_id"] == 2 and receive["cash"]["store_id"] == 1,
            "双方实际现金不能替代或重复同一来源")
    await roster.use("finance2")
    current = await read_page(e, "clearing", "/api/reconciliation/origins", "店间实际清算")
    row = next(r for r in current["items"] if r["origin_kind"] == kind and r["origin_id"] == origin["id"])
    require(row["available_cents"] == row["reserved_cents"] == 0 and row["settled_cents"] == -origin["amount_cents"], "原应付条目尚未真正清算")
    return {**evidence, "order": order, "pay": pay, "receive": receive, "final_origin": row}


async def interstore_business(e, context, credentials):
    cp, roster = Checkpoint(e), Roster(e, context, credentials)
    token = uuid.uuid4().hex[:9]
    try:
        cp.start("HK-020")
        vehicle_a, vehicle_b, primary, account1, source_location = dependencies(e, cp)
        # These identities log in before all protected business snapshots.
        for role in ("manager", "inventory", "finance"):
            await roster.existing(role)
        staff = await roster.create_destination(token)
        destination, account2, locations, masters = await destination_masters(e, roster, primary, token)
        activated = await activate_zero(e, roster, destination, locations["materials"])
        vehicle, accepted = await vehicle_chain(e, roster, vehicle_a, locations["vehicles"]["id"], source_location["id"])
        await cp.passed({"same_run_parent_ids": list(PARENTS), "destination_staff": staff,
            "destination_masters": masters, "zero_activation": activated, "accepted_vehicle_transfer": accepted})

        cp.start("HK-024")
        rejected, rejection = await vehicle_chain(e, roster, vehicle_b, locations["vehicles"]["id"], source_location["id"], reject=True)
        await cp.passed({"actual_accept_dispatch": accepted["dispatch"], "separate_rejected_transfer": rejection,
            "different_vin": vehicle["vin"] != rejected["vin"], "rejected_transfer_cash_or_settlement": False})

        cp.start("HK-055")
        material, sent = await material_dispatch(e, roster, primary)
        await cp.passed(sent)

        cp.start("HK-047")
        material, material_evidence = await material_receive_return(e, roster, material, sent, destination, locations["materials"], primary)
        await cp.passed(material_evidence)

        cp.start("HK-084")
        origins = [("vehicle", row) for row in accepted["settlements"] if row["store_id"] == 2]
        origins += [("material", row) for row in material_evidence["settlements"] if row["store_id"] == 2]
        require(len(origins) == 3 and all(row["amount_cents"] < 0 for _, row in origins), "三笔正实际验收原来源不足")
        settlements = [await clear_origin(e, roster, kind, row, account2, account1) for kind, row in origins]
        cash_ids = [part[action]["cash"]["id"] for part in settlements for action in ("pay", "receive")]
        require(len(set(cash_ids)) == 6, "三笔双店实际现金不是六个唯一来源")
        await cp.passed({"three_original_origins": [{"kind": kind, "settlement_id": row["id"], "transfer_id": row["transfer_id"]}
                for kind, row in origins], "independent_clearings": settlements, "cash_ids": cash_ids,
                "bank_execution": "isolated_synthetic_input_only", "rejected_vehicle_has_no_origin": True})

        sources = {"source_store_id": 1, "destination_store_id": 2,
            "destination_users": {role: staff[role]["user"]["id"] for role in staff},
            "source_account_id": account1["id"], "destination_account_id": account2["id"],
            "destination_vehicle_location_id": locations["vehicles"]["id"],
            "destination_material_location_id": locations["materials"]["id"],
            "source_item_id": primary["item_id"], "destination_item_id": destination["id"],
            "accepted_vehicle_transfer_id": vehicle["id"], "received_vehicle_id": vehicle["received_vehicle_id"],
            "rejected_vehicle_transfer_id": rejected["id"], "returned_vehicle_id": rejected["received_vehicle_id"],
            "material_transfer_id": material["id"], "material_accept_movement_ids": [r["id"] for r in material_evidence["accepted_movements"]],
            "material_movement_ids": [r["id"] for r in related(e, "material_transfer_movements", "transfer_id", material["id"])],
            "original_settlement_ids": {"vehicle": [r["id"] for r in accepted["settlements"]],
                "material": [r["id"] for r in material_evidence["settlements"]]},
            "clearing_order_ids": [r["order"]["id"] for r in settlements], "cash_ids": cash_ids,
            "offset_ids": [r["id"] for part in settlements for r in part["receive"]["offsets"]],
            "destination_zero_activation_case_id": activated["case_id"], "full_193_business_acceptance": False,
            "manual_review": "pending"}
        cp.finish(sources)
    except Exception as error:
        cp.failed(error)
        raise
    finally:
        await roster.close()


INTERSTORE_SCENARIOS = ((SCENARIO, interstore_business, 1500),)
