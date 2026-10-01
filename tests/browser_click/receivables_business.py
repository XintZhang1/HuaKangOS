"""Original employee forms create four positive balances, then read full scope.

Registered click scenario. No app imports, direct HTTP business writes, SQL writes,
clock manipulation or replay. All passwords and source bytes remain external.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
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
from vehicle_purchase_business import live_choice, select_value, checkbox, nav
from finance_business import original_form, submit
import sales_order_business as S
import sales_followon_business as SF
import vehicle_operations_business as VO
import vehicle_purchase_business as VP
import repair_business as R
import boutique_business as BT
import retail_remaining_business as RT
import material_business as MAT
import member_followon_business as MF
import report_business as REPORT

SCENARIO = "receivables-hk157-158-159"
REQUIREMENTS = (("HK-157", "物资应收账统计"), ("HK-158", "整车相关应收账统计"), ("HK-159", "维修应收账统计"))
PURCHASE, MASTER, REPAIR, BOUTIQUE = BT.PURCHASE, BT.MASTER, R.SCENARIO, BT.SCENARIO
SALES, RETAIL = S.SCENARIO, RT.SCENARIO
TABLES = {**SF.TABLES, **R.PRIMARY_KEYS, **{t: VO.PK.get(t, "id") for t in VO.TABLES},
          **{t: BT.pk(t) for t in RT.TABLES}, **{t: "id" for t in (
              "sales_quotes", "sales_quote_reviews", "sales_quote_consents", "sales_quote_resolutions",
              "flow_vehicle_holds", "sales_pdi_records", "master_item_profiles", "stores", "flow_customers",
              "master_vehicle_models", "master_agency_projects", "master_suppliers", "master_warehouses", "master_locations")},
          "flow_vehicle_holds": "vehicle_id"}
CASE = R.CASE_FIELDS
TASK = R.TASK_FIELDS
VERSION = {"version", "updated_at"}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def day():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def rows(e, table):
    require(table in TABLES, "未审阅原表：" + table)
    return e.db.rows(f"SELECT * FROM {table} ORDER BY {TABLES[table]}")


def one(e, table, key):
    require(table in TABLES and type(key) is int and key > 0, "来源须是明确原ID")
    result = e.db.rows(f"SELECT * FROM {table} WHERE {TABLES[table]}=?", (key,))
    require(len(result) == 1, "原来源缺失或重复：" + table + "/" + str(key))
    return result[0]


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(raw)
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title in REQUIREMENTS:
            require(catalog[key]["title"] == title and catalog[key]["source_review_status"] == "source_reviewed"
                    and any(c["check_id"] == key + "-business" for c in catalog[key]["acceptance_checks"]), "应收原合同错配")
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [k for k, _ in REQUIREMENTS],
            "source_contract_sha256": self.digest, "candidate_sha256": sha(Path(__file__).read_bytes()),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "complete": False, "passed": False, "execution": "native_browser_original_forms",
            "business_accepted": False, "human_acceptance": "pending", "full_193_business_acceptance": False,
            "full_registered_suite_complete": False,
            "contract_rules": {"automatic_pass_is_not_business_acceptance": True, "unknown_result_replay": False,
                "human_six_criteria_review": "pending", "untested_conditions_are_not_passed": True,
                "no_dedicated_receivable_chart_in_original_contract": True},
            "requirements": [{"id": k, "title": title, "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": k + "-business", "check_id": k + "-business", "status": "not_tested",
                    "criteria": ["实际原表单建立非空正欠额", "原Task/版本/回执/现金库存各自关联",
                        "当前全授权范围KPI/全部分页表/CSV/原单钻取与DB一致", "保护全部无关旧行/文件原字节"], "evidence": {}}]}
                for k, title in REQUIREMENTS],
            "conditional_checks": [{"status": "not_tested", "scope": x} for x in (
                "欠额再收/逾期/权益占额/并发/拒绝", "跨店或集团/新增超过处理上限/历史期末余额",
                "维修保险厂家其他承担及实际客户接车", "人工六类标准/真实银行实物/PG/Linux/ClamAV/生产")],
            "conditions": {"synthetic_inputs_only": True, "prebuilt_business_results": False,
                "actual_bank_or_company_handover": False, "file_scan": "structure_only_not_clamav"}}
        self.save()

    def save(self):
        content = json.dumps(self.report, ensure_ascii=False, indent=2, allow_nan=False)
        for secret in self.e.secrets:
            if secret:
                content = content.replace(json.dumps(secret, ensure_ascii=False)[1:-1], "[redacted]")
        self.path.write_text(content + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        require(self.active["status"] == "not_tested", "不重复领取已执行check")
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active["evidence_action_start"] = len(self.e.actions)
        self.save()

    def note(self, value):
        json.dumps(value, ensure_ascii=False)
        self.active["acceptance_checks"][0].setdefault("steps", []).append(value)
        self.save()

    async def passed(self, value):
        json.dumps(value, ensure_ascii=False)
        self.active.update(status="passed", evidence_action_end=len(self.e.actions))
        self.active["acceptance_checks"][0].update(status="passed", evidence=value)
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active = None
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.active["acceptance_checks"][0]["error"] = self.e.scrub(error)
        self.report.update(error=self.e.scrub(error), failed_requirement=self.active["id"] if self.active else "sources")
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "三项原合同未全部执行")
        self.report.update(complete=True, passed=True, executed_requirements=3, passed_requirements=3, report_sources=sources)
        self.save()
        self.e.observe("receivables_checkpoint", {"path": str(self.path), "passed_checks": 3,
            "business_accepted": False, "human_acceptance": "pending", "full_193_business_acceptance": False})


class Guard:
    """All business hashes and every old row, including immutable BLOB bytes."""
    def __init__(self, e, label, actor, *, append=(), update=None, cases=(), new_kind=None, new_version=None, customer=None):
        self.e, self.label, self.actor = e, label, actor
        self.append, self.update, self.cases = set(append), update or {}, set(cases)
        self.new_kind, self.new_version, self.customer = new_kind, new_version, customer
        require(self.append | self.update.keys() <= TABLES.keys(), "守卫超出已核原表")
        self.before = e.business_snapshot("before_" + label)
        self.old = {t: rows(e, t) for t in self.append | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
                   if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.old.keys(), "修改了无关原表：" + str(sorted(changed)))
        self.added = {}
        updates = {}
        for table, old in self.old.items():
            pk = TABLES[table]
            current = {r[pk]: r for r in rows(self.e, table)}
            self.added[table] = [r for k, r in current.items() if k not in {x[pk] for x in old}]
            require(not self.added[table] or table in self.append, "仅更新表新增事实")
            require(len(self.added[table]) <= 12, "本次有限单张动作出现超量新增：" + table)
            updates[table] = []
            for prior in old:
                require(prior[pk] in current, "删除了旧原事实：" + table)
                columns = {k for k in prior if prior[k] != current[prior[pk]][k]}
                require(columns <= self.update.get(table, {}).get(prior[pk], set()),
                        "覆写了未允许旧行/列：" + table + "/" + str(prior[pk]) + "/" + str(sorted(columns)))
                if columns:
                    updates[table].append({"id": prior[pk], "columns": sorted(columns)})
        created = self.added.get("flow_cases", [])
        require(not created or len(created) == 1 and created[0]["kind"] == self.new_kind
            and created[0]["flow_version"] == self.new_version and created[0]["created_by"] == self.actor["id"]
            and (self.customer is None or created[0]["customer_id"] == self.customer), "新原单身份/版本/客户错配")
        owned = self.cases | {r["id"] for r in created}
        for table, added in self.added.items():
            for r in added:
                if "store_id" in r:
                    require(r["store_id"] == 1, "新增原事实串店")
                if "case_id" in r:
                    require(r["case_id"] in owned, "新增原事实串单：" + table)
                for field in ("actor_id", "created_by"):
                    if field in r and r[field] is not None:
                        require(r[field] == self.actor["id"], "新增原事实借办理身份：" + table)
                if table in {"file_security", "file_scan_events"}:
                    require(one(self.e, "flow_files", r["file_id"])["case_id"] in owned, "扫描串原文件")
                if table == "cash_entries":
                    links = self.e.db.rows("SELECT * FROM flow_payment_links WHERE cash_id=?", (r["id"],))
                    require(len(links) == 1 and links[0]["case_id"] in owned, "新现金缺本单唯一来源")
        proof = {"label": self.label, "changed_tables": sorted(changed),
            "appended_ids": {t: [r[TABLES[t]] for r in v] for t, v in self.added.items()},
            "updated_columns": updates, "all_unrelated_tables_unchanged": True, "all_other_old_rows_unchanged": True}
        self.e.observe("receivables_original_row_guard", proof)
        return proof


def updates(e, key, *, vehicle=None, account=None):
    result = {"flow_cases": {key: CASE}, "flow_tasks": {r["id"]: TASK for r in rows(e, "flow_tasks") if r["case_id"] == key}}
    if vehicle:
        result["vehicles"] = {vehicle: VERSION}
    if account:
        result["flow_accounts"] = {account: VERSION}
    return result


def sources(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "只接受外置合成实例")
    provenance = json.loads((Path(e.manifest["evidence_root"]) / "provenance.json").read_text(encoding="utf-8"))
    require(provenance["snapshot_stable"] is True, "来源快照不稳定")
    for name in ("receivables_business.py", "retail_remaining_business.py", "boutique_business.py", "repair_business.py",
                 "vehicle_operations_business.py", "vehicle_purchase_business.py", "finance_business.py",
                 "sales_business.py", "sales_order_business.py", "sales_followon_business.py", "material_business.py",
                 "member_followon_business.py", "report_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name).read_bytes()), "脚本来源指纹变化：" + name)
    purchase, master, repair, boutique, sale = [fixed_dependency(e, cp, name) for name in (PURCHASE, MASTER, REPAIR, BOUTIQUE, SALES)]
    current_report = json.loads((Path(e.manifest["evidence_root"]) / "browser-click-report.json").read_text(encoding="utf-8"))
    if any(s["id"] == RETAIL for s in current_report["scenarios"]):
        fixed_dependency(e, cp, RETAIL)
    b, r = boutique["report_sources"], repair["report_sources"]
    fixture = {**e.manifest["business_fixtures"]["sales_order"], **e.manifest["business_fixtures"]["repair"],
               **e.manifest["business_fixtures"]["vehicle_purchase"], "admin_key": "admin"}
    fixture["sales_key"] = e.manifest["business_fixtures"]["sales_order"]["sales_key"]
    item, profile = one(e, "flow_items", b["item_ids"][0]), one(e, "master_item_profiles", b["profile_ids"][0])
    supplier = one(e, "master_suppliers", b["supplier_id"])
    warehouse, location = one(e, "master_warehouses", b["warehouse_id"]), one(e, "master_locations", b["location_id"])
    account = one(e, "flow_accounts", b["account_id"])
    enrollment = one(e, "warehouse_enrollments", b["enrollment_ids"][0])
    customer, cv = one(e, "flow_customers", r["customer_id"]), one(e, "care_customer_vehicles", r["customer_vehicle_id"])
    sales_customer = one(e, "flow_customers", sale["report_sources"]["customer_id"])
    work = one(e, "master_work_items", checkpoint_evidence(master, "HK-175")["row"]["id"])
    project = one(e, "master_agency_projects", checkpoint_evidence(master, "HK-179")["row"]["id"])
    hierarchy = checkpoint_evidence(purchase, "HK-177")["new_hierarchy"]
    model = dict(hierarchy["model"], brand_name=hierarchy["brand"]["name"], series_name=hierarchy["series"]["name"])
    current_model = one(e, "master_vehicle_models", model["id"])
    require(current_model["active"] == 1 and current_model["version"] == model["version"]
        and current_model["name"] == model["name"], "原已发布车型身份或版本变化")
    vstore = checkpoint_evidence(purchase, "HK-178")
    vwarehouse, vlocation = one(e, "master_warehouses", vstore["warehouse"]["id"]), one(e, "master_locations", vstore["location"]["id"])
    for t, row in (("flow_items", item), ("master_item_profiles", profile), ("master_suppliers", supplier),
                   ("master_warehouses", warehouse), ("master_locations", location), ("flow_accounts", account),
                   ("master_work_items", work), ("master_agency_projects", project), ("master_warehouses", vwarehouse), ("master_locations", vlocation)):
        require(row["store_id"] == fixture["store_id"] == 1 and row["active"] == 1, "有限父原源失效：" + t)
    activation = one(e, "flow_cases", enrollment["case_id"])
    activation_document = one(e, "warehouse_documents", activation["id"])
    approval_events = e.db.rows("SELECT * FROM flow_events WHERE case_id=? AND action='warehouse_approve'", (activation["id"],))
    require(profile["item_id"] == enrollment["item_id"] == item["id"] and enrollment["store_id"] == 1
            and profile["location_id"] == location["id"] and location["warehouse_id"] == warehouse["id"], "原精品库存关联失效")
    require(activation["store_id"] == activation_document["store_id"] == 1
            and activation["kind"] == "warehouse" and activation["flow_version"] == 2 and activation["state"] == "completed"
            and activation_document["operation"] == "activate" and activation_document["item_id"] == item["id"]
            and activation_document["baseline_quantity_milli"] == enrollment["baseline_quantity_milli"]
            and activation_document["baseline_value_cents"] == enrollment["baseline_value_cents"]
            and len(approval_events) == 1 and approval_events[0]["after_state"] == "completed"
            and approval_events[0]["actor_id"] == e.manifest["users"][fixture["manager_key"]]["id"], "原物资启用及真实独立批准来源不符")
    require(cv["active"] == 1 and cv["customer_id"] == customer["id"] and cv["store_id"] == 1
            and sales_customer["owner_id"] == e.manifest["users"][fixture["sales_key"]]["id"], "原客户或真实销售所有权不符")
    for role in ("manager", "inventory", "finance", "service", "technician", "sales"):
        require(e.manifest["users"][fixture[role + "_key"]]["role"] == role, "缺真实本店岗位")
    cp.report["source_preconditions"] = {"fixed_scenarios": [PURCHASE, MASTER, REPAIR, BOUTIQUE, SALES],
        "item_id": item["id"], "profile_id": profile["id"], "enrollment_id": enrollment["id"],
        "warehouse_id": warehouse["id"], "location_id": location["id"], "account_id": account["id"],
        "customer_id": customer["id"], "customer_vehicle_id": cv["id"], "sales_customer_id": sales_customer["id"],
        "supplier_id": supplier["id"], "work_item_id": work["id"], "agency_project_id": project["id"], "model_id": model["id"],
        "activation_case_id": activation["id"], "activation_approval_event_id": approval_events[0]["id"]}
    cp.save()
    return fixture, item, supplier, warehouse, location, account, customer, cv, sales_customer, work, project, model, vwarehouse, vlocation


async def material_precondition(e, context, credentials, fixture, item, supplier, warehouse, location, account, token):
    actor, _ = await BT.read_as(e, context, credentials, fixture, "inventory", "procurement", "/api/procurement/orders", "采购与供应商结算")
    await e.click('#main [data-act="procurement-new"]', "另采1.000" + item["unit"] + "本轮物资，实际付款及收货")
    await expect(e.page.locator("#modal-title")).to_have_text("申请多行采购")
    await live_choice(e, "supplier", supplier["name"], supplier["code"] + " · " + supplier["name"], expected_value=supplier["id"])
    reason = "本次合成明确采购1.000" + item["unit"] + "，单价10元；实际预付、现场收货与原库位分别留证"
    await e.fill('#modal [name="reason"]', reason, "明确本笔独立采购依据")
    line = e.page.locator('#modal [data-purchase-line]')
    await expect(line).to_have_count(1)
    await MAT.choose(e, line, 'select[name="item"]', item["sku"], item["sku"] + " · " + item["name"] + "（" + item["unit"] + "）", item["id"])
    await line.locator('[name="quantity"]').fill("1.000")
    await line.locator('[name="cost"]').fill("10.00")
    guard = BT.Guard(e, "receivables_material_purchase", actor, append={**BT.FLOW, "flow_cases": 1,
        "flow_tasks": 1, "procurement_orders": 1, "procurement_lines": 1}, new_kind="procurement", items={item["id"]})
    body, request, shown, native = await MF.submit_created(e, "/api/procurement/orders", "/api/procurement/orders/", status=201, body_key=("id",))
    key = body["id"]
    expected = {"supplier_id": supplier["id"], "reason": reason,
        "lines": [{"item_id": item["id"], "quantity_milli": 1000, "unit_cost_cents": 1000}]}
    require(request == {"request_id": request["request_id"], **expected} and shown["flow_version"] == 3, "原单件采购完整输入不符")
    native.update(guard=guard.finish(), receipt=MF.flow_receipt(e, request, actor, key, "procurement_create", expected))
    _, approved = await BT.purchase_action(e, context, credentials, fixture, key, "approve", {item["id"]}, role="manager", task_key="procurement_approve")
    finance, _ = await MAT.detail(e, context, credentials, fixture, "finance", key, "procurement")
    contract = await MF.upload(e, finance, key, None, f"/api/procurement/orders/{key}", "procurement_contract", "receivable-material-contract", token)
    requested, request_native = await MAT.procurement_command(e, context, credentials, fixture, key, "prepay_request", {item["id"]},
        role="finance", file=contract["file"], amount=1000)
    funds = requested["prepayments"]["requests"]
    require(len(funds) == 1 and funds[0]["requested_by"] == finance["id"], "原请款来源不唯一")
    approved_funds, approve_native = await MAT.procurement_command(e, context, credentials, fixture, key, "prepay_approve", {item["id"]},
        role="manager", file=contract["file"], funds=funds[0], task_key="procurement_prepay_review_" + str(funds[0]["id"]))
    funds = approved_funds["prepayments"]["requests"][0]
    require(funds["status"] == "approved" and len(funds["decisions"]) == 1
        and funds["decisions"][0]["actor_id"] == e.manifest["users"][fixture["manager_key"]]["id"] != finance["id"], "原请款须已由另一主管独立批准")
    finance, _ = await MAT.detail(e, context, credentials, fixture, "finance", key, "procurement")
    proof = await MF.upload(e, finance, key, None, f"/api/procurement/orders/{key}", "receipt", "receivable-material-actual-pay", token)
    reference = "AR-MATERIAL-OUT-" + token
    _, paid_native = await MAT.procurement_command(e, context, credentials, fixture, key, "prepay_pay", {item["id"]}, role="finance",
        file=proof["file"], funds=funds, amount=1000, account=account, reference=reference,
        task_key="procurement_prepay_pay_" + str(funds["id"]))
    actual_cash = MAT.cash_fact(e, key, 1000, "out", reference, account, finance)
    inventory, _ = await MAT.detail(e, context, credentials, fixture, "inventory", key, "procurement")
    receiving = await MF.upload(e, inventory, key, None, f"/api/procurement/orders/{key}", "evidence", "receivable-material-actual-receive", token)
    stock_before = MAT.item_stock(e, item["id"])
    batch = await MAT.inline_receive(e, context, credentials, fixture, key, (item,), (1000,), location, warehouse, receiving["file"])
    stock = MAT.item_stock(e, item["id"])
    require("totals" not in batch["api"] and batch["api"]["id"] == key and batch["api"]["state"] == "completed",
            "原库管收货投影不得泄漏财务金额或串单")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/procurement/orders/{key}"
            and r.request.headers.get("x-store-id") == str(fixture["store_id"])) as finance_read:
        finance_actor, finance_api = await MAT.detail(e, context, credentials, fixture, "finance", key, "procurement")
    finance_response = await finance_read.value
    finance_headers = await finance_response.request.all_headers()
    require(finance_response.status == 200 and finance_headers.get("cookie")
            and finance_headers.get("x-store-id") == str(fixture["store_id"])
            and finance_actor["id"] == finance["id"] and finance_api["state"] == "completed",
            "须财务本人原页核同店同单实付而非借库管投影")
    finance_meta = {"path": f"/api/procurement/orders/{key}", "method": "GET", "status": 200,
            "native_ui": True, "cookie_present": True, "store_id": fixture["store_id"], "actor_id": finance_actor["id"],
            "case_id": key, "version": finance_api["version"], "state": finance_api["state"], "totals": finance_api["totals"]}
    e.observe("receivables_original_finance_totals_read", finance_meta)
    require(stock["item"]["quantity_milli"] == stock_before["item"]["quantity_milli"] + 1000
            and stock["item"]["inventory_value_cents"] == stock_before["item"]["inventory_value_cents"] + 1000
            and finance_api["totals"]["payable_cents"] == 0 and finance_api["totals"]["paid_net_cents"] == 1000
            and len(batch["receipts"]) == 1 and batch["receipts"][0]["value_cents"] == 1000, "新原采实款/到货/均价未闭合")
    usable = [r for r in stock["balances"] if r["location_id"] == location["id"]]
    require(len(usable) == 1 and usable[0]["quantity_milli"] >= 1000, "新实际收货仍无原位置足额")
    return {"case_id": key, "create": native, "independent_purchase_approval": approved, "contract": contract,
        "funds_request": request_native, "independent_funds_approval": approve_native, "actual_payment": actual_cash,
        "native_payment": paid_native, "receive": batch, "finance_totals_read": finance_meta, "before_stock": stock_before, "current_stock": stock}


async def retail_source(e, context, credentials, fixture, customer, item, location, account, token):
    actor, _ = await BT.read_as(e, context, credentials, fixture, "service", "retail", BT.RETAIL + "/orders", "精品销售与退货")
    await e.click('#main [data-act="retail-new"]', "建立一件纯商品真实正欠额")
    await expect(e.page.locator("#modal-title")).to_have_text("新建精品订单")
    label = await e.page.locator(f'#modal [name="customer"] option[value="{customer["id"]}"]').text_content()
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/cases"
        and parse_qs(urlsplit(r.url).query).get("kind") == ["repair"] and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer["id"])]) as ready:
        await live_choice(e, "customer", customer["name"], label, expected_value=customer["id"])
    require((await ready.value).status == 200, "原客户候选读取失败")
    await expect(e.page.locator('#modal [data-member-price-field]')).not_to_have_attribute("data-loading", "true")
    await expect(e.page.locator('#modal [name="related"]')).to_have_value("")
    line = e.page.locator('#modal [data-retail-line]')
    label = await line.locator(f'[name="item"] option[value="{item["id"]}"]').text_content()
    await MAT.choose(e, line, '[name="item"]', item["sku"], label, item["id"])
    await line.locator('[name="quantity"]').fill("1.000")
    await line.locator('[name="price"]').fill("20.00")
    await expect(line.locator('[name="work"]')).to_have_value("")
    await line.locator('[name="install_price"]').fill("0.00")
    await e.fill('#modal [name="discount"]', "0.00", "本次不猜优惠")
    await select_value(e, '#modal [name="member_pricing_rule"]', "", "纯现金无会员价格规则")
    expected = {"customer_id": customer["id"], "related_repair_id": None, "discount_cents": 0,
        "lines": [{"item_id": item["id"], "quantity_milli": 1000, "unit_price_cents": 2000,
                   "work_item_id": None, "installation_unit_price_cents": 0}]}
    guard = RT.Guard(e, "receivable_retail_create", actor, append={**BT.FLOW, "flow_cases": 1, "flow_tasks": 1,
        "retail_orders": 1, "retail_lines": 1, "retail_reservations": 1}, update={"flow_items": {item["id"]: VERSION}},
        items={item["id"]}, new_customer=customer["id"])
    body, request, view, native = await MF.submit_created(e, BT.RETAIL + "/orders", BT.RETAIL + "/orders/", status=201, body_key=("id",))
    key = body["id"]
    require(request == {"request_id": request["request_id"], **expected} and view["amount_cents"] == 2000, "新纯商品原输入不符")
    native.update(guard=guard.finish(), receipt=MF.flow_receipt(e, request, actor, key, "retail_create", expected))
    approval = await RT.retail_action(e, context, credentials, fixture, key, "approve", (item,), 2000, token)
    authorization = await RT.retail_action(e, context, credentials, fixture, key, "authorize", (item,), 2000, token)
    preparation = await BT.prepare(e, context, credentials, fixture, key, (item,), location, "retail_dispatch", (-1000,))
    dispatch = await RT.retail_action(e, context, credentials, fixture, key, "dispatch", (item,), 2000, token)
    acceptance = await RT.retail_action(e, context, credentials, fixture, key, "accept", (item,), 2000, token)
    await BT.responsible(e, context, credentials, fixture, key, "retail_receive", "finance")
    finance, before = await RT.retail_read(e, context, credentials, fixture, "finance", key)
    require(before["totals"]["receivable_cents"] == 2000
            and before["totals"].get("cash_collectable_cents", before["totals"]["receivable_cents"]) == 2000, "原商品尚待收额不符")
    proof = await MF.upload(e, finance, key, None, BT.RETAIL + f"/orders/{key}", "receipt", "receivable-retail-in", token)
    await original_form(e, "retail-action", "receive", "登记实际收款")
    await e.fill('#modal [name="amount"]', "5.00", "只收到本次5元，留下15元待收")
    await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
    reference = "AR-RETAIL-IN-" + token
    await e.fill('#modal [name="reference"]', reference, "明确独立原款编号")
    await MF.choose_file(e, proof, "receipt")
    c = one(e, "flow_cases", key)
    guard = RT.Guard(e, "receivable_retail_partial_cash", finance,
        append={"flow_events": 1, "audit_logs": 2, "flow_request_receipts": 1, "cash_entries": 1,
                "flow_payment_links": 1, "retail_payments": 1}, update=BT.updates(e, key, account=account["id"]), cases={key})
    body, request, view, cash_native = await submit(e, BT.RETAIL + f"/orders/{key}/actions/receive", BT.RETAIL + f"/orders/{key}")
    values = {"amount_cents": 500, "account_id": account["id"], "reference": reference, "evidence_id": proof["file"]["id"]}
    require(request == {"request_id": request["request_id"], "version": c["version"], "values": values}, "原部分收款完整CAS输入不符")
    cash_native.update(guard=guard.finish(), receipt=MF.flow_receipt(e, request, finance, key, "retail_receive", {"case_id": key, "version": c["version"], "values": values}))
    cash, link, bound = guard.added["cash_entries"][0], guard.added["flow_payment_links"][0], guard.added["retail_payments"][0]
    require(len(guard.added["cash_entries"]) == len(guard.added["flow_payment_links"]) == len(guard.added["retail_payments"]) == 1
        and cash["direction"] == link["direction"] == "in" and cash["amount_cents"] == link["amount_cents"] == 500
        and cash["category"] == "workflow_retail" and cash["account"] == account["name"] and cash["voucher_no"] == link["reference"] == reference
        and link["account_id"] == account["id"] and link["cash_id"] == cash["id"] and link["original_id"] is None
        and bound["payment_link_id"] == link["id"] and bound["evidence_id"] == proof["file"]["id"]
        and view["totals"]["charge_cents"] == 2000 and view["totals"]["net_paid_cents"] == 500
        and view["totals"]["receivable_cents"] == 1500 and view["state"] == "settling", "实收5元不应结清20元约定")
    return key, {"case_id": key, "charge_cents": 2000, "paid_cents": 500, "due_cents": 1500,
        "create": native, "independent_approval": approval, "customer_authorization": authorization,
        "position_preparation": preparation, "actual_dispatch": dispatch, "actual_customer_acceptance": acceptance,
        "partial_cash": cash_native, "proof": proof, "cash": cash, "payment_link": link, "retail_payment": bound, "api": view}


async def vehicle_precondition(e, context, credentials, fixture, supplier, model, warehouse, location, account, token):
    vin = "LTEST" + uuid.uuid4().hex[:12].upper()
    require(re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin) and not e.db.rows("SELECT id FROM vehicles WHERE vin=?", (vin,)), "新VIN已被使用")
    fixture = dict(fixture, vins=[vin])
    inventory, _ = await VO.read_as(e, context, credentials, fixture, "inventory", "vehicle-procurement", VO.VP, "整车采购与付款")
    await e.click('#main [data-act="vp-new"]', "独立采购本次应收订单的一台新车")
    await expect(e.page.locator("#modal-title")).to_have_text("整车采购计划")
    await select_value(e, '#modal [name="supplier_id"]', supplier["id"], "明确本轮原供应商")
    party = e.page.locator('#modal [name="contracting_party"]')
    if await party.get_attribute("readonly") is None:
        await e.fill('#modal [name="contracting_party"]', "合成应收采购主体" + token, "明确本次原合同抬头")
    await e.fill('#modal [name="due_date"]', day(), "明确实际收车业务日")
    await e.fill('#modal [name="reason"]', "独立新VIN实际付款及入库后给新客户合同配车，保留当前正欠额", "本次独立采购用途")
    await select_value(e, '#modal [data-vp-line] [name="model"]', model["id"], "明确本轮已发布车型")
    await e.fill('#modal [data-vp-line] [name="color"]', "合成应收白", "本车明确颜色")
    await e.fill('#modal [data-vp-line] [name="quantity"]', "1", "一台真实新车")
    guard = VO.Guard(e, "receivable_vehicle_purchase", inventory, 1,
        append=VO.COMMON | {"flow_cases", "flow_tasks", "vehicle_purchase_orders", "vehicle_purchase_lines"}, new_kind="vehicle_procurement")
    body, _, native, request = await VO.submit(e, VO.VP, inventory, 1, guard, status=201)
    key = body["id"]
    f = VP.purchase_facts(e, key)
    require(len(f["lines"]) == 1 and request["lines"] == [{"model_id": model["id"], "quantity": 1, "color": "合成应收白"}], "新一台采购输入不符")
    manager, _, _ = await VO.purchase_owner(e, context, credentials, fixture, key, "vp_approve", "manager")
    contract = await VO.proof_upload(e, key, manager, fixture, "procurement_contract", "ar-vehicle-contract-" + token + ".txt", "本次新车成本80元/建议售价100元，按本台合成原合同实际付款及收车。")
    _, f, approved = await VO.purchase_action(e, fixture, key, "approve", manager,
        {"cost_" + str(f["lines"][0]["id"]): "80.00", "price_" + str(f["lines"][0]["id"]): "100.00"},
        [("evidence_id", contract["file"]["id"])], append={"vehicle_purchase_prices"}, update=VO.mutable(e, key, prices=True))
    _, f, funds = await VO.purchase_action(e, fixture, key, "request_funds", manager,
        {"amount": "80.00", "reason": "独立新VIN原合同全额请款80元"}, [("evidence_id", contract["file"]["id"])], append={"vehicle_purchase_funds_requests"})
    fund = f["funds"][0]
    finance, _, _ = await VO.purchase_owner(e, context, credentials, fixture, key, "vp_pay", "finance")
    receipt = await VO.proof_upload(e, key, finance, fixture, "receipt", "ar-vehicle-paid-" + token + ".txt", "合成现场已按原账户实际支付本台原款80元。")
    _, f, paid = await VO.purchase_action(e, fixture, key, "pay", finance, {"amount": "80.00", "reference": "AR-VP-OUT-" + token},
        [("funds_request_id", fund["id"]), ("account_id", account["id"]), ("evidence_id", receipt["file"]["id"])],
        append={"vehicle_purchase_payments", "cash_entries"}, update=VO.mutable(e, key, funds={fund["id"]}, account=account["id"]))
    payment = VO.payment_fact(e, key, f["payments"][0]["id"], finance, account, 8000, "out")
    inventory, _, _ = await VO.purchase_owner(e, context, credentials, fixture, key, "vp_ship", "inventory")
    shipping = await VO.proof_upload(e, key, inventory, fixture, "evidence", "ar-vehicle-shipped-" + token + ".txt", "供方本台新VIN " + vin + " 已实际发运。")
    require(not e.db.rows("SELECT id FROM vehicles WHERE vin=?", (vin,))
        and not e.db.rows("SELECT id FROM vehicle_custodies WHERE vin=?", (vin,))
        and not e.db.rows("SELECT id FROM group_identities WHERE kind='vehicle' AND canonical_key=?", (vin,)),
        "本次新VIN发运前已有实车、身份或保管来源")
    _, f, shipped = await VO.purchase_action(e, fixture, key, "ship", inventory,
        {"vin": vin, "shipped_date": day(), "expected_date": day()}, [("line_id", f["lines"][0]["id"]), ("evidence_id", shipping["file"]["id"])],
        append={"vehicle_purchase_shipments", "group_identities", "vehicle_custodies"})
    ship_added = shipped["native"]["source_guard"]["appended_ids"]
    require(all(len(ship_added[name]) == 1 for name in ("vehicle_purchase_shipments", "group_identities", "vehicle_custodies"))
        and len(f["shipments"]) == 1, "本次发运未唯一追加原Shipment、VIN身份及保管记录")
    shipment = f["shipments"][0]
    identity = one(e, "group_identities", ship_added["group_identities"][0])
    custody = one(e, "vehicle_custodies", ship_added["vehicle_custodies"][0])
    require(identity["kind"] == "vehicle" and identity["canonical_key"] == identity["search_key"] == vin
        and identity["name"] == f["lines"][0]["model_name"] and identity["created_by"] == inventory["id"]
        and identity["version"] == 1, "发运新增VIN身份的车型、本人或版本不符")
    require(custody["vin"] == vin and custody["identity_id"] == identity["id"] and custody["generation"] == 0
        and custody["current_vehicle_id"] is None and custody["current_store_id"] is None
        and custody["pending_transfer_id"] is None and custody["version"] == 2,
        "发运保管记录不是本VIN首次空位置、零代次及真实版本")
    require(shipment["id"] == ship_added["vehicle_purchase_shipments"][0] and shipment["case_id"] == key
        and shipment["store_id"] == fixture["store_id"] and shipment["line_id"] == f["lines"][0]["id"]
        and shipment["vin"] == shipment["active_vin"] == vin and shipment["status"] == "transit"
        and shipment["actor_id"] == inventory["id"] and shipment["version"] == 1
        and shipment["evidence_id"] == shipping["file"]["id"]
        and shipment["shipped_date"] == shipped["submitted_values"]["shipped_date"]
        and shipment["expected_date"] == shipped["submitted_values"]["expected_date"],
        "原发运VIN、同店同单、本人或实际日期不符")
    inventory, _, _ = await VO.purchase_owner(e, context, credentials, fixture, key, "vp_receive", "inventory")
    receiving = await VO.proof_upload(e, key, inventory, fixture, "evidence", "ar-vehicle-received-" + token + ".txt", "现场逐位核本VIN " + vin + " 实物入原车辆库位，非发运代验收。")
    require(one(e, "group_identities", identity["id"]) == identity
        and one(e, "vehicle_custodies", custody["id"]) == custody, "验收前本VIN身份或保管原件已变化")
    receive_update = VO.mutable(e, key, shipments={shipment["id"]})
    custody_fields = {"version", "generation", "current_vehicle_id", "current_store_id"}
    receive_update["vehicle_custodies"] = {custody["id"]: custody_fields}
    _, f, received = await VO.purchase_action(e, fixture, key, "receive", inventory,
        {"vin": vin}, [("shipment_id", shipment["id"]), ("location_id", location["id"]), ("evidence_id", receiving["file"]["id"])],
        append={"vehicles", "group_identity_links", "vehicle_positions", "vehicle_position_entries",
                "vehicle_purchase_receipts", "vehicle_purchase_movements"}, update=receive_update)
    require(len(f["receipts"]) == 1 and f["case"]["state"] == "completed", "一台新采购未真实完成")
    physical = VP.vehicle_fact(e, f["receipts"][0], f["shipments"][0], f["lines"][0], f["prices"][0], warehouse, location, inventory)
    receive_added = received["native"]["source_guard"]["appended_ids"]
    require(all(len(receive_added[name]) == 1 for name in ("vehicles", "group_identity_links", "vehicle_positions",
        "vehicle_position_entries", "vehicle_purchase_receipts", "vehicle_purchase_movements")), "本次实际验收来源未各自唯一追加")
    current_custody = one(e, "vehicle_custodies", custody["id"])
    link = one(e, "group_identity_links", receive_added["group_identity_links"][0])
    require(one(e, "group_identities", identity["id"]) == identity
        and all(current_custody[name] == value for name, value in custody.items() if name not in custody_fields)
        and current_custody["generation"] == custody["generation"] + 1 == physical["vehicle"]["inventory_generation"]
        and current_custody["current_vehicle_id"] == physical["vehicle"]["id"] == receive_added["vehicles"][0]
        and current_custody["current_store_id"] == fixture["store_id"] and current_custody["version"] > custody["version"],
        "验收改写VIN身份、保管其它列或缺少本实车代次及版本推进")
    require(link["identity_id"] == identity["id"] and link["local_kind"] == "vehicle"
        and link["local_id"] == physical["vehicle"]["id"] and link["store_id"] == fixture["store_id"]
        and link["confirmed_by"] == inventory["id"], "实际验收集团身份关联不属于本VIN、当前店及本人")
    require(len(f["movements"]) == 1 and f["receipts"][0]["id"] == receive_added["vehicle_purchase_receipts"][0]
        and f["movements"][0]["id"] == receive_added["vehicle_purchase_movements"][0]
        and f["receipts"][0]["actor_id"] == f["movements"][0]["actor_id"] == inventory["id"]
        and f["receipts"][0]["store_id"] == f["movements"][0]["store_id"] == fixture["store_id"]
        and f["receipts"][0]["shipment_id"] == f["movements"][0]["shipment_id"] == shipment["id"]
        and f["movements"][0]["vehicle_id"] == physical["vehicle"]["id"] and f["movements"][0]["kind"] == "receive"
        and f["movements"][0]["quantity"] == 1 and f["movements"][0]["value_cents"] == f["prices"][0]["unit_cost_cents"]
        and f["receipts"][0]["evidence_id"] == f["movements"][0]["evidence_id"] == receiving["file"]["id"],
        "实际验收及库存原账的数量成本、发运来源、本人或凭据不符")
    source = dict(physical, model=model)
    return source, {"case_id": key, "vin": vin, "create": native, "contract": contract, "approve": approved,
        "funds": funds, "actual_payment": payment, "native_payment": paid, "shipping": shipped,
        "actual_receipt": received, "physical": physical, "proofs": [receipt, shipping, receiving],
        "vin_identity_custody": {"ship_identity": identity, "ship_custody": custody, "shipment_id": shipment["id"],
            "received_custody": current_custody, "identity_link": link, "identity_unchanged": True,
            "only_original_custody_columns_mutable": sorted(custody_fields)}}


async def sales_owner(e, context, credentials, fixture, key, task_key, role):
    original = S.task(S.facts(e, key), task_key)
    target = e.manifest["users"][fixture[role + "_key"]]
    handoff = {"task_id": original["id"], "key": task_key, "original_assignee_id": original["assignee_id"],
               "actual_employee_id": target["id"]}
    if original["assignee_id"] != target["id"]:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/flow/cases/{key}") as pending:
            manager = await login_as(e, context, credentials, fixture["manager_key"], f"case/{key}", 1)
        response = await pending.value
        current = await response.json()
        require(response.status == 200 and current["id"] == key, "原转交未读取同单")
        await expect(e.page.locator("#main h1")).to_have_text(current["title"])
        button = e.page.locator(f'#main [data-act="assign"][data-id="{original["id"]}"]')
        await expect(button).to_have_count(1)
        await expect(button).to_be_visible()
        await e.click(f'#main [data-act="assign"][data-id="{original["id"]}"]', "主管交接本次原销售待办")
        await employee_choice(e, target)
        reason = "本次应收原岗位员工本人办理，明确交接当前原任务"
        await e.fill('#modal [name="reason"]', reason, "明确原待办交接原因")
        guard = Guard(e, "ar_sales_original_handoff", manager, append={"flow_events", "audit_logs"},
            update={"flow_tasks": {original["id"]: TASK}, "flow_cases": {key: VERSION}}, cases={key})
        _, _, native, request = await SF.original_submit(e, f'/api/flow/tasks/{original["id"]}/assign',
            lambda p: p == f"/api/flow/cases/{key}", guard, 1, request_id_required=False)
        require(set(request) == {"version", "assignee_id", "reason"} and request["version"] == original["version"]
            and request["assignee_id"] == target["id"] and request["reason"] == reason
            and native["request_id_sha256"] is None, "原任务三字段/CAS不符")
        handoff["native"] = native
    actor, view = await S.detail_as(e, context, credentials, fixture[role + "_key"], key, 1)
    require(S.task(S.facts(e, key), task_key)["assignee_id"] == actor["id"], "当前销售待办不是本人")
    return actor, view, handoff


async def sales_command(e, key, action, actor, *, append=(), extra=None, fills=None, lookups=()):
    before = S.facts(e, key)
    guard = Guard(e, "ar_sales_" + action, actor,
        append={"flow_events", "flow_tasks", "audit_logs", "flow_request_receipts"} | set(append),
        update={**updates(e, key), **(extra or {})}, cases={key})
    async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == f"/api/flow/cases/{key}/actions/{action}") as pending:
        after, view, native = await S.command(e, key, action, actor, fills=fills, lookups=lookups)
    request = (await pending.value).request.post_data_json
    native["source_guard"] = guard.finish()
    # The generic original action uses the ID in its operation name, not in its payload.
    receipt = guard.added["flow_request_receipts"]
    require(len(receipt) == 1 and receipt[0]["actor_id"] == actor["id"], "销售动作原回执不唯一")
    exact = MF.flow_receipt(e, request, actor, key, f"{key}:{action}", {"version": request["version"], "values": request["values"]})
    return after, view, {"native": native, "receipt": exact, "submitted_values": request["values"], "before_version": before["case"]["version"]}


async def sales_source(e, context, credentials, fixture, customer, physical, account, token):
    physical = dict(physical, original_position=physical["position"])
    S.physical(e, physical, state="stored")
    sales = await login_as(e, context, credentials, fixture["sales_key"], "sales-quotes", 1)
    await expect(e.page.locator("#main h1")).to_have_text("车辆报价与预订")
    await e.click('#main [data-act="sales-quote-new"]', "为本人客户建立本次新VIN的原报价")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/customer-choice/matches"
        and parse_qs(urlsplit(r.url).query).get("q") == [customer["name"]]) as pending:
        await e.fill('#modal [name="customer_name"]', customer["name"], "明确检索本人原客户")
    response = await pending.value
    choices = await response.json()
    require(response.status == 200 and any(c["id"] == customer["id"] for c in choices["items"]), "新销售原客户不可选")
    await e.click(f'#modal [data-quote-customers] [data-customer-id="{customer["id"]}"]', "明确选择原客户不另建档案")
    await S.fill_quote(e, physical["model"], 10000, "本次合成新车100元；本次实收30元，剩70元原客户欠款另行核对。")
    guard = Guard(e, "ar_sales_create", sales, append={"flow_cases", "sales_quotes", "flow_tasks", "flow_events", "audit_logs",
        "flow_request_receipts", "flow_files", "file_security", "file_scan_events", "business_entity_case_contexts"},
        new_kind="order", new_version=4, customer=customer["id"])
    body, view, native, request = await S.original_write(e, "/api/sales-quotes/orders", 201)
    native["source_guard"] = guard.finish()
    key, initial = body["id"], S.facts(e, body["id"])
    create_payload = {"customer_id": customer["id"], "lead_id": None, "lead_version": None, "quote": request["quote"]}
    native["receipt"] = MF.flow_receipt(e, request, sales, key, "sales_quote_create", create_payload)
    require(initial["case"]["customer_id"] == customer["id"] and request["customer_id"] == customer["id"]
        and initial["case"]["parent_id"] is None and initial["case"]["state"] == "reserved"
        and len(initial["quotes"]) == 1 and initial["quotes"][0]["amount_cents"] == 10000
        and initial["quotes"][0]["model_id"] == physical["model"]["id"], "新销售原报价/客户/金额不符")
    manager, _, approve_owner = await sales_owner(e, context, credentials, fixture, key, "quote_approve", "manager")
    f, _, approved = await sales_command(e, key, "quote_approve", manager, append={"sales_quote_reviews"},
        fills={"reason": "独立核对本次新VIN100元原报价、客户及期限"})
    require(f["reviews"][0]["actor_id"] == manager["id"] != sales["id"] and f["reviews"][0]["decision"] == "approved", "新销售报价未独立复核")
    inventory, _, allocate_owner = await sales_owner(e, context, credentials, fixture, key, "allocate", "inventory")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/sales-quotes/orders/{key}/vehicles") as pending:
        await S.action_form(e, "allocate")
    response = await pending.value
    choices = await response.json()
    chosen = [c for c in choices["items"] if c["id"] == physical["vehicle"]["id"]]
    require(response.status == 200 and len(chosen) == 1 and physical["vehicle"]["vin"] in chosen[0]["label"], "配车候选未含本次新VIN")
    await select_value(e, '#modal [name="vehicle"]', chosen[0]["label"], "明确当前代次新VIN")
    before = S.facts(e, key)
    guard = Guard(e, "ar_sales_allocate", inventory, append={"flow_vehicle_holds", "flow_events", "audit_logs", "flow_request_receipts"},
        update={**updates(e, key), "flow_cases": {key: CASE | {"vehicle_id"}},
            "vehicles": {physical["vehicle"]["id"]: VERSION}, "vehicle_custodies": {physical["custody"]["id"]: {"version"}}}, cases={key})
    _, _, allocated, request = await S.original_write(e, f"/api/flow/cases/{key}/actions/allocate", 200, case_id=key)
    allocated["source_guard"] = guard.finish()
    allocated["receipt"] = MF.flow_receipt(e, request, inventory, key, f"{key}:allocate", {"version": request["version"], "values": request["values"]})
    f = S.facts(e, key)
    require(request["version"] == before["case"]["version"] and f["case"]["vehicle_id"] == request["values"]["vehicle_id"] == physical["vehicle"]["id"]
        and f["case"]["cost_cents"] == 8000, "配车原VIN/CAS/成本不符")
    S.physical(e, physical, state="stored", case_id=key)
    sales, _, sign_owner = await sales_owner(e, context, credentials, fixture, key, "sign", "sales")
    guard = Guard(e, "ar_sales_generated_current_contract", sales,
        append={"flow_files", "file_security", "file_scan_events", "flow_events", "audit_logs"}, cases={key})
    document, generated = await S.generate(e, key, sales, "contract")
    generated["all_old_rows_guard"] = guard.finish()
    guard = Guard(e, "ar_sales_actual_signature_upload", sales,
        append={"flow_files", "file_security", "file_scan_events", "flow_events", "audit_logs"}, cases={key})
    file, signed = await S.upload(e, key, sales, "signed_contract", "ar-sale-signed-" + token + ".txt",
        "合成客户逐位核对本次VIN与原生成100元合同后签回；不以上传代替原签回确认。", source_file=document)
    signed["all_old_rows_guard"] = guard.finish()
    f, view, confirmed = await sales_command(e, key, "sign", sales, append={"sales_quote_consents", "sales_quote_resolutions"},
        extra={"flow_cases": {key: CASE | {"due_date"}}}, lookups=[("evidence_id", file["name"] + " · 合同签回件", file["id"])])
    quote, consent = f["quotes"][0], f["consents"][0]
    require(f["case"]["data"]["active_quote_id"] == consent["quote_id"] == quote["id"]
        and consent["vehicle_id"] == physical["vehicle"]["id"] and consent["source_file_id"] == document["id"]
        and consent["evidence_id"] == file["id"] and consent["fingerprint"] == document["source_fingerprint"]
        and view["business_facts"]["facts"]["sales.active_quote_consented"] is True, "签回未绑定本Quote/VIN/源字节")
    finance, _, pay_owner = await sales_owner(e, context, credentials, fixture, key, "receive", "finance")
    guard = Guard(e, "ar_sales_actual_cash_upload", finance,
        append={"flow_files", "file_security", "file_scan_events", "flow_events", "audit_logs"}, cases={key})
    file, paid_proof = await S.upload(e, key, finance, "receipt", "ar-sale-paid-" + token + ".txt", "合成原客户本次实际到账30元；70元未到账。")
    paid_proof["all_old_rows_guard"] = guard.finish()
    reference = "AR-SALE-IN-" + token
    f, view, received = await sales_command(e, key, "receive", finance, append={"cash_entries", "flow_payment_links", "business_entity_cash_contexts"},
        extra={"flow_accounts": {account["id"]: VERSION}}, fills={"amount": "30.00", "reference": reference},
        lookups=[("account_id", account["name"], account["id"]), ("evidence_id", file["name"] + " · 收退款凭据", file["id"])])
    require(len(f["payments"]) == 1 and f["payments"][0]["amount_cents"] == f["cash"][0]["amount_cents"] == 3000
        and f["payments"][0]["direction"] == f["cash"][0]["direction"] == "in" and f["payments"][0]["account_id"] == account["id"]
        and f["cash"][0]["voucher_no"] == reference and f["cash"][0]["created_by"] == finance["id"]
        and f["case"]["amount_cents"] == 10000 and view["paid_cents"] == 3000 and not f["case"]["data"].get("delivered_at"), "新销售实际30元与70元未收混同")
    return key, {"case_id": key, "quote": quote, "consent": consent, "vehicle": physical["vehicle"], "payment_link": f["payments"][0], "cash": f["cash"][0],
        "charge_cents": 10000, "paid_cents": 3000, "due_cents": 7000, "create": native, "approve": approved, "allocate": allocated,
        "generated_contract": generated, "actual_signature": signed, "sign": confirmed, "proof": paid_proof, "receive": received,
        "task_owners": [approve_owner, allocate_owner, sign_owner, pay_owner]}


async def service_source(e, context, credentials, fixture, source_id, customer, project, account, token):
    actor, current = await S.detail_as(e, context, credentials, fixture["sales_key"], source_id, 1)
    require(current["business_facts"]["facts"]["sales.active_quote_consented"] is True, "关联服务须本版签回原销售")
    await nav(e, "service-orders", "代办与其它客户服务", SF.DOMAIN["service"])
    await e.click('#main [data-act="serviceorder-new"]', "为本次原销售建立独立10元服务费")
    for field, value in (("subtype", "代办服务"), ("customer", f'{customer["id"]} · {customer["name"]}'),
        ("source", f'{source_id} · {current["number"]}'), ("vehicle", "不关联车辆"), ("blocking", "允许后续办理")):
        await select_value(e, f'#modal [name="{field}"]', value, "明确原服务来源 " + field)
    await e.fill('#modal [name="due_date"]', day(), "明确本次服务期限")
    await e.fill('#modal [name="reason"]', "本次有效原销售关联独立服务费10元；不冒充外部办结或代缴本金", "明确原服务申请")
    guard = SF.Guard(e, "ar_service_create", actor, 1,
        append=SF.COMMON | {"flow_cases", "service_orders", "service_requests", "business_entity_case_contexts"},
        update={"flow_cases": {source_id: VERSION}}, new_kind="agency")
    body, view, native, request = await SF.original_submit(e, SF.DOMAIN["service"],
        lambda p: bool(re.fullmatch(r"/api/service-orders/\d+", p)), guard, 1, status=201)
    key = body["id"]
    require(request["source_order_id"] == source_id and request["source_version"] == current["version"]
        and request["customer_id"] == customer["id"] and request["subtype"] == "agency" and not request["delivery_blocking"]
        and view["order"]["source_order_id"] == source_id and SF.case(e, key)["parent_id"] == source_id, "关联服务未绑定当前原销售/CAS")
    quote, lines, quoted = await SF.service_quote(e, context, credentials, fixture, key, source_id, "sales", project, 1000, day())
    _, consent = await SF.service_approve_authorize(e, context, credentials, fixture, key, source_id, "sales", quote)
    finance, _, owner = await SF.responsible(e, context, credentials, fixture, "service", key, "serviceorder_receive", "finance")
    proof = await SF.upload(e, fixture, key, finance, "receipt", "ar-service-paid-" + token, "合成原客户服务费本次实际到账3元；7元未到账。")
    await SF.form(e, "service", "receive")
    await e.fill('#modal [name="amount"]', "3.00", "只登记实际到账服务费3元")
    await SF.account_choice(e, account)
    reference = "AR-SERVICE-IN-" + token
    await e.fill('#modal [name="reference"]', reference, "独立服务费实际流水")
    await SF.proof_choice(e, proof)
    view, received = await SF.command(e, fixture, "service", key, finance, "receive", parent=source_id, account=account["id"],
        append={"cash_entries", "flow_payment_links", "service_tender_slices", "business_entity_cash_contexts"},
        expected={"amount_cents": 300, "account_id": account["id"], "reference": reference})
    links, tenders = SF.rows(e, "flow_payment_links", key), SF.rows(e, "service_tender_slices", key)
    require(len(links) == len(tenders) == 1 and links[0]["amount_cents"] == tenders[0]["amount_cents"] == 300
        and tenders[0]["payment_link_id"] == links[0]["id"] and tenders[0]["bucket"] == "fee"
        and view["summary"]["fee_charge_cents"] == 1000 and view["summary"]["fee_paid_cents"] == 300
        and view["summary"]["fee_due_cents"] == view["summary"]["customer_due_cents"] == 700
        and view["summary"]["pass_charge_cents"] == 0 and not SF.rows(e, "service_fulfillments", key), "服务费正欠700或未办结事实不符")
    cash = one(e, "cash_entries", links[0]["cash_id"])
    require(cash["amount_cents"] == 300 and cash["created_by"] == finance["id"] and cash["account"] == account["name"]
        and cash["direction"] == "in" and cash["voucher_no"] == reference, "服务现金与本店原账户不符")
    return key, {"case_id": key, "source_case_id": source_id, "quote": quote, "lines": lines, "charge_cents": 1000,
        "paid_cents": 300, "due_cents": 700, "cash": cash, "payment_link": links[0], "tenders": tenders,
        "create": native, "quote_native": quoted, "independent_authorization": consent, "receipt_proof": proof,
        "receive": received, "task_owner": owner, "external_fulfillment": "not_performed"}


async def repair_command(e, fixture, key, action, actor):
    async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == f"{R.REPAIR}/{key}/actions/{action}") as pending:
        f, view, native = await R.command(e, fixture, key, action, actor)
    request = (await pending.value).request.post_data_json
    values = dict(request["values"])
    if action == "quote":
        values = {"purpose": "service", "discount_cents": 0, "retained_amount_cents": None, **values}
        if values.get("member_pricing") is None:
            values.pop("member_pricing", None)
        values["lines"] = [{"line_key": None, **r} for r in values["lines"]]
    elif action == "allocate":
        values["allocations"] = [{"payer_id": None, "payer_name": "", **r} for r in values["allocations"]]
    native["receipt"] = MF.flow_receipt(e, request, actor, key, "repair_v3_" + action,
        {"id": key, "version": request["version"], "values": values})
    return f, view, native


def intake_receipt(e, request, actor, operation, payload, body):
    digest = sha(json.dumps({"operation": "intake_" + operation, "payload": payload},
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())
    receipts = [r for r in rows(e, "intake_command_receipts") if r["request_key"] == request["request_id"]]
    require(len(receipts) == 1 and receipts[0]["store_id"] == 1 and receipts[0]["actor_id"] == actor["id"]
        and receipts[0]["digest"] == digest and json.loads(receipts[0]["result"]) == body,
        "原接待回执本人/本店/请求摘要/实际结果不符")
    return {"id": receipts[0]["id"], "digest": digest, "actor_id": actor["id"], "store_id": 1,
        "request_id_sha256": sha(request["request_id"].encode()), "result_matches_native_response": True}


async def repair_source(e, context, credentials, fixture, customer, vehicle, work, account, token):
    manager = await login_as(e, context, credentials, fixture["manager_key"], "service-intake/resources", 1)
    await expect(e.page.locator("#main h1")).to_have_text("工位与快捷项目")
    await e.click('#main [data-act="intake-resource-new"]', "主管建立本次纯作业实际工位")
    name = "合成应收工位" + token
    await e.fill('#modal [name="code"]', "AR" + token, "本次唯一工位编码")
    await e.fill('#modal [name="name"]', name, "本次明确维修工位")
    await select_value(e, '#modal [name="type"]', "维修", "明确真实维修用途")
    guard = R.Guard(e, "ar_resource_create", manager, 1, append={"intake_resources", "intake_command_receipts"})
    body, _, resource_native, resource_request = await R.submit(e, R.INTAKE + "/resources", R.INTAKE + "/catalog", 1, 201, protection=guard)
    resource_native["receipt"] = intake_receipt(e, resource_request, manager, "resource_create",
        {k: v for k, v in resource_request.items() if k != "request_id"}, body)
    resource = R.one(e, "intake_resources", body["id"])
    require(resource["active"] and resource["active_case_id"] is None and resource["resource_type"] == "repair", "新工位非真实可用")
    service = await login_as(e, context, credentials, fixture["service_key"], "service-intake/appointments", 1)
    await expect(e.page.locator("#main h1")).to_have_text("维修预约与到店")
    await e.click('#main [data-act="intake-new"][data-mode="walk_in"]', "现场原车辆来访，不预制到店结果")
    vehicle_label = " · ".join(str(v) for v in (customer["name"], customer["phone"], vehicle["plate"], vehicle["vin"]) if v)
    await live_choice(e, "customer_vehicle_id", vehicle["vin"], vehicle_label, expected_value=vehicle["id"])
    await live_choice(e, "resource_id", name, name, expected_value=resource["id"])
    for field in ("starts_at", "ends_at"):
        value = await e.page.locator(f'#modal [name="{field}"]').input_value()
        await e.fill(f'#modal [name="{field}"]', value, "明确页面本次现场时段")
    await e.fill('#modal [name="reason"]', "合成现场纯作业30元，客户承担20元、内部承担10元，真实客户仅先付5元", "明确本次维修诉求")
    guard = R.Guard(e, "ar_walkin_create", service, 1,
        append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "intake_appointments", "intake_command_receipts", "business_entity_case_contexts"},
        update={"intake_resources": {resource["id"]: VERSION}}, vehicle_id=vehicle["id"], resource_id=resource["id"], new_kind="service_intake")
    body, _, booked, request = await R.submit(e, R.INTAKE + "/appointments", R.INTAKE + "/appointments/*", 1, 201, protection=guard)
    payload = {k: v for k, v in request.items() if k != "request_id"}
    for field in ("starts_at", "ends_at"):
        payload[field] = datetime.fromisoformat(payload[field].replace("Z", "+00:00")).isoformat().replace("+00:00", "Z")
    booked["receipt"] = intake_receipt(e, request, service, "appointment_create", payload, body)
    appointment_id, intake_id = body["id"], body["case_id"]
    require(request["mode"] == "walk_in" and request["preset_id"] is None and request["customer_vehicle_id"] == vehicle["id"]
        and R.one(e, "intake_appointments", appointment_id)["status"] == "scheduled", "现场单必须仍等待真实到店确认")
    service, _, arrive_owner = await R.responsible(e, context, credentials, fixture, intake_id, "intake_arrive", "service", appointment_id=appointment_id)
    observations = e.db.rows("SELECT odometer_km FROM care_vehicle_observations WHERE vehicle_id=? ORDER BY id", (vehicle["id"],))
    mileage = max([0] + [r["odometer_km"] or 0 for r in observations]) + 100
    proof = await R.upload(e, intake_id, service, "evidence", "ar-arrive-" + token + ".txt",
        f"本次合成现场逐位核VIN {vehicle['vin']}，独立读数{mileage}公里。", 1)
    await R.form(e, "arrive", intake=True)
    await e.fill('#modal [name="checked_vin"]', vehicle["vin"], "现场逐位核对原VIN")
    await e.fill('#modal [name="odometer_km"]', str(mileage), "记录本次实际合成读数")
    await R.file_choice(e, "evidence_id", proof)
    guard = R.Guard(e, "ar_walkin_arrival", service, 1, append={"flow_tasks", "flow_events", "audit_logs", "intake_arrivals", "intake_command_receipts"},
        update={**R.mutable(e, intake_id, vehicle_id=vehicle["id"]), "intake_appointments": {appointment_id: {"status", "updated_at", "version"}}},
        cases={intake_id}, vehicle_id=vehicle["id"])
    body, _, arrived, request = await R.submit(e, f"{R.INTAKE}/appointments/{appointment_id}/actions/arrive", f"{R.INTAKE}/appointments/{appointment_id}", 1, protection=guard)
    arrived["receipt"] = intake_receipt(e, request, service, "appointment_arrive",
        {"id": appointment_id, "version": request["version"], **request["values"]}, body)
    arrival = e.db.rows("SELECT * FROM intake_arrivals WHERE appointment_id=?", (appointment_id,))
    require(len(arrival) == 1 and arrival[0]["checked_vin"] == vehicle["vin"] and arrival[0]["odometer_km"] == mileage
        and arrival[0]["evidence_id"] == proof["file"]["id"] and arrival[0]["actor_id"] == service["id"], "真实到店/VIN/读数来源不符")
    service, _, convert_owner = await R.responsible(e, context, credentials, fixture, intake_id, "intake_convert", "service", appointment_id=appointment_id)
    await R.form(e, "convert", intake=True)
    await e.fill('#modal [name="due_date"]', day(), "本次维修原期限")
    guard = R.Guard(e, "ar_walkin_convert", service, 1,
        append={"flow_cases", "flow_tasks", "flow_events", "audit_logs", "intake_command_receipts", "intake_repair_contexts", "intake_vehicle_bindings", "business_entity_case_contexts"},
        update={**R.mutable(e, intake_id), "intake_appointments": {appointment_id: {"status", "repair_case_id", "updated_at", "version"}}},
        cases={intake_id}, vehicle_id=vehicle["id"], resource_id=resource["id"], new_kind="repair")
    body, _, converted, request = await R.submit(e, f"{R.INTAKE}/appointments/{appointment_id}/actions/convert", f"{R.INTAKE}/appointments/{appointment_id}", 1, protection=guard)
    converted["receipt"] = intake_receipt(e, request, service, "appointment_convert",
        {"id": appointment_id, "version": request["version"], **request["values"]}, body)
    key = body["repair_case_id"]
    f = R.facts(e, key)
    require(f["case"]["flow_version"] == 4 and f["case"]["customer_id"] == customer["id"]
        and f["context"][0]["resource_id"] == resource["id"] and f["binding"][0]["vin"] == vehicle["vin"]
        and f["binding"][0]["customer_vehicle_id"] == vehicle["id"], "新维修未绑定本次到店/原CV")
    service, _, quote_owner = await R.responsible(e, context, credentials, fixture, key, "repair_quote", "service")
    await R.form(e, "quote")
    line = e.page.locator('#modal [data-repair-line]').nth(0)
    e.action("fill", "检索本轮真实作业主档", work_item_id=work["id"])
    await line.locator('[role="combobox"]').fill(work["name"])
    option = line.get_by_role("option", name="项目 · " + work["code"] + " " + work["name"], exact=True)
    await expect(option).to_be_visible()
    e.action("click", "明确选择真实纯作业项目", work_item_id=work["id"])
    await option.click()
    await expect(line.locator('[name="source"]')).to_have_value("work:" + str(work["id"]))
    for field, value in (("quantity", "1.000"), ("price", "30.00")):
        e.action("fill", "明确本次纯作业数量和价款", field=field, value=value)
        await line.locator(f'[name="{field}"]').fill(value)
    await e.fill('#modal [name="discount"]', "0.00", "本次没有额外折扣")
    await e.fill('#modal [name="reason"]', "本次合成真实纯作业报价30元，不领用物资", "本版原报价依据")
    f, _, quoted = await repair_command(e, fixture, key, "quote", service)
    quote = f["quotes"][0]
    require(len(f["lines"]) == 1 and f["lines"][0]["kind"] == "work" and f["lines"][0]["work_item_id"] == work["id"]
        and f["lines"][0]["item_id"] is None and f["lines"][0]["quantity_milli"] == 1000
        and quote["amount_cents"] == f["lines"][0]["amount_cents"] == 3000, "纯作业原报价不符")
    manager, _, price_owner = await R.responsible(e, context, credentials, fixture, key, "repair_price_" + str(quote["id"]), "manager")
    await R.form(e, "price_approve")
    await e.fill('#modal [name="minimum"]', "30.00", "主管独立核本版最低价")
    await checkbox(e, '#modal [name="allow_below_minimum"]', False, "不默认批准低价")
    await e.fill('#modal [name="reason"]', "独立核对本版合成纯作业30元", "主管原核价依据")
    f, _, approved = await repair_command(e, fixture, key, "price_approve", manager)
    require(f["approvals"][0]["actor_id"] == manager["id"] != service["id"], "维修未独立核价")
    service, _, auth_owner = await R.responsible(e, context, credentials, fixture, key, "repair_authorize_" + str(quote["id"]), "service")
    auth = await R.upload(e, key, service, "authorization", "ar-repair-auth-" + token + ".txt", f"合成客户本版{quote['id']}摘要{quote['digest']}30元明确授权。", 1)
    await R.form(e, "authorize")
    await R.file_choice(e, "evidence_id", auth)
    f, _, authorized = await repair_command(e, fixture, key, "authorize", service)
    technician, _, work_owner = await R.responsible(e, context, credentials, fixture, key, "repair_work", "technician")
    await R.form(e, "start")
    await e.fill('#modal [name="result"]', "合成现场已进本次工位实际开工", "技师记录真实开工")
    f, _, started = await repair_command(e, fixture, key, "start", technician)
    require(R.one(e, "intake_resources", resource["id"])["active_case_id"] == key, "实际工位未占用")
    technician, _, _ = await R.responsible(e, context, credentials, fixture, key, "repair_work", "technician")
    await R.form(e, "finish")
    await e.fill('#modal [name="result"]', "合成纯作业已实际完成，提交独立质检", "技师记录真实完工")
    f, _, finished = await repair_command(e, fixture, key, "finish", technician)
    service, _, quality_owner = await R.responsible(e, context, credentials, fixture, key, "repair_quality", "service")
    quality_proof = await R.upload(e, key, service, "inspection", "ar-quality-" + token + ".txt", "本次合成纯作业逐项安全核对合格。", 1)
    await R.form(e, "quality")
    await e.fill('#modal [name="result"]', "独立逐项核本次实际作业合格", "服务顾问原质检结论")
    await select_value(e, '#modal [name="outcome"]', "合格", "明确本次实际质检结果")
    await R.file_choice(e, "evidence_id", quality_proof)
    f, _, quality = await repair_command(e, fixture, key, "quality", service)
    manager, _, allocation_owner = await R.responsible(e, context, credentials, fixture, key, "repair_allocate", "manager")
    allocation_proof = await R.upload(e, key, manager, "evidence", "ar-allocation-" + token + ".txt", "合成客户承担20元、内部责任10元；本次明确实际合成工时成本6元，非收款。", 1)
    await R.form(e, "allocate")
    await e.fill('#modal [name="amount_customer"]', "20.00", "明确客户承担20元")
    await e.click('#modal [data-repair-add-payer="internal"]', "另列内部责任10元")
    await e.fill('#modal [name="amount_internal"]', "10.00", "明确内部承担不记客户现金")
    await e.fill('#modal [name="internal_name"]', "合成本店内部责任", "明确内部承担主体")
    for field in ("due_customer", "due_internal"):
        await e.fill(f'#modal [name="{field}"]', day(), "本次承担原期限")
    await e.fill('#modal [name="labor_cost"]', "6.00", "明确合成实际工时成本")
    await R.file_choice(e, "evidence", allocation_proof)
    f, _, allocated = await repair_command(e, fixture, key, "allocate", manager)
    allocations = {r["payer_type"]: r for r in f["allocations"]}
    require(set(allocations) == {"customer", "internal"} and allocations["customer"]["amount_cents"] == 2000
        and allocations["internal"]["amount_cents"] == 1000 and f["case"]["cost_cents"] == 600 and not f["stock"]
        and not f["payments"], "维修客户/内部承担或成本与原事实不符")
    finance, _, pay_owner = await R.responsible(e, context, credentials, fixture, key, "repair_receive_" + str(allocations["customer"]["id"]), "finance")
    cash_proof = await R.upload(e, key, finance, "evidence", "ar-repair-paid-" + token + ".txt", "合成原客户实际只到账5元；其余客户15元未付，内部10元不作现金。", 1)
    await R.form(e, "receive")
    await e.fill('#modal [name="amount"]', "5.00", "只登记本次真实到账5元")
    await live_choice(e, "account_id", account["name"], account["name"], expected_value=account["id"])
    reference = "AR-REPAIR-IN-" + token
    await e.fill('#modal [name="reference"]', reference, "原客户本次独立实际流水")
    await R.file_choice(e, "evidence_id", cash_proof)
    f, view, received = await repair_command(e, fixture, key, "receive", finance)
    require(len(f["payments"]) == len(f["repair_payments"]) == 1 and f["repair_payments"][0]["allocation_id"] == allocations["customer"]["id"]
        and f["payments"][0]["amount_cents"] == 500 and view["receivable_cents"] == 1500
        and f["case"]["state"] == "settling" and not f["case"]["data"].get("released_date"), "维修必须保留真实正欠额，不先冒交车")
    cash = one(e, "cash_entries", f["payments"][0]["cash_id"])
    require(cash["amount_cents"] == 500 and cash["direction"] == "in" and cash["voucher_no"] == reference
        and cash["created_by"] == finance["id"] and f["payments"][0]["account_id"] == account["id"], "维修现金原账户事实不符")
    technician, _ = await R.read_as(e, context, credentials, fixture, "technician", f"repair-orders/{key}", f"{R.REPAIR}/{key}")
    release_proof = await R.upload(e, key, technician, "evidence", "ar-workplace-release-" + token + ".txt", "本次施工已完成，技师现场将车实际移出工位；客户欠款仍15元且没有接车离场。", 1)
    await e.click('#main [data-act="intake-resource"][data-key="release"]', "技师确认真实移出工位，不代客户接车")
    await e.fill('#modal [name="reason"]', "本次实际完工车辆移出工位等待原欠款核对，未客户接车", "明确实际工位释放事实")
    await R.file_choice(e, "evidence_id", release_proof)
    guard = R.Guard(e, "ar_actual_resource_release", technician, 1, append={"intake_resource_uses", "flow_events", "audit_logs", "intake_command_receipts"},
        update=R.mutable(e, key, resource_id=resource["id"], vehicle_id=vehicle["id"]), cases={key}, vehicle_id=vehicle["id"], resource_id=resource["id"])
    body, _, resource_release, request = await R.submit(e, f"{R.INTAKE}/orders/{key}/resource/release", f"{R.REPAIR}/{key}", 1, protection=guard)
    resource_release["receipt"] = intake_receipt(e, request, technician, "resource_release",
        {"case_id": key, "version": request["version"], **request["values"]}, body)
    require(R.one(e, "intake_resources", resource["id"])["active_case_id"] is None and R.facts(e, key)["case"]["state"] == "settling"
        and not R.facts(e, key)["case"]["data"].get("released_date"), "实际工位释放误作客户交车或清掉欠款")
    return key, {"case_id": key, "customer_id": customer["id"], "customer_vehicle_id": vehicle["id"], "appointment_id": appointment_id,
        "resource": resource, "arrival": arrival[0], "quote": quote, "lines": f["lines"], "allocations": list(allocations.values()),
        "charge_cents": 2000, "paid_cents": 500, "due_cents": 1500, "internal_cents": 1000, "cash": cash,
        "payment_link": f["payments"][0], "resource_create": resource_native, "book": booked, "arrive": arrived, "convert": converted,
        "quote_native": quoted, "independent_price": approved, "authorize": authorized, "start": started, "finish": finished,
        "independent_quality": quality, "allocate": allocated, "receive": received, "actual_resource_release": resource_release,
        "task_owners": [arrive_owner, convert_owner, quote_owner, price_owner, auth_owner, work_owner, quality_owner, allocation_owner, pay_owner],
        "customer_departure": "not_performed_while_positive_due"}


ORACLE_TABLES = frozenset({"flow_cases", "stores", "flow_payment_links", "business_finance_credit_links", "flow_member_entries",
    "group_payment_links", "benefit_payment_links", "repair_package_payment_links", "aftercare_adjustments", "repair_allocations",
    "repair_payments", "claims_responsibility_entries", "retail_return_postings", "retail_group_plans", "retail_group_tenders",
    "retail_group_captures", "retail_group_units", "retail_group_allocations", "retail_group_return_parts", "service_lines",
    "service_authorizations", "service_charge_adjustments", "service_tender_slices", "insurance_quotes", "insurance_consents",
    "insurance_terminations", "insurance_termination_applications", "insurance_tenders", "insurance_commissions",
    "insurance_commission_reviews", "insurance_commission_payments", "addon_authorizations", "addon_return_postings",
    "vehicle_income_orders", "vehicle_income_revisions", "vehicle_income_decisions", "vehicle_income_cash",
    "business_finance_return_receivables", "business_finance_return_target_revisions", "sales", "repairs", "cash_entries",
    "business_finance_corrections", "business_finance_cash_batches", "business_finance_stored_corrections", "membership_fee_corrections"})


def current_oracle(e):
    """Independent SELECT projection of every current store-one receivable.

    Dates are presentation filters for this current balance, never an invented
    historical balance. Source-specific cash, face credit and fee/pass slices
    remain separate. No app import or HTTP result is used to compute totals.
    """
    db = {}
    for table in sorted(ORACLE_TABLES):
        require(re.fullmatch(r"[a-z_]+", table), "非有限原表")
        db[table] = e.db.rows(f"SELECT * FROM {table}")
        require(len(db[table]) <= 25000, "原表超限未完整读取：" + table)
    cases = [c for c in db["flow_cases"] if c["store_id"] == 1 and c["kind"] != "customer_care"]
    require(len(cases) <= 25000, "当前授权原单超限")
    store = next(s["name"] for s in db["stores"] if s["id"] == 1)
    signed = lambda r: r["amount_cents"] * (1 if r["direction"] == "in" else -1)
    cash_paid, credit, paid = defaultdict(int), defaultdict(int), defaultdict(int)
    for link in db["flow_payment_links"]:
        cash_paid[link["case_id"]] += signed(link)
        paid[link["case_id"]] += signed(link)
    for link in db["business_finance_credit_links"]:
        credit[link["case_id"]] += link["amount_cents"]
        paid[link["case_id"]] += link["amount_cents"]
    for entry in db["flow_member_entries"]:
        if entry["purpose"] == "consume":
            paid[entry["case_id"]] -= entry["amount_cents"]
    external_credit = defaultdict(int)
    for table in ("group_payment_links", "benefit_payment_links", "repair_package_payment_links"):
        for link in db[table]:
            paid[link["case_id"]] += link["amount_cents"]
            external_credit[link["case_id"]] += link["amount_cents"]
    result, total, overdue = [], 0, 0

    def add(c, customer, label, charge, settled, gap, state, late=False, route=None):
        nonlocal total, overdue
        if gap <= 0:
            return
        total += gap
        overdue += gap if late else 0
        result.append({"values": [c.get("number", c.get("doc_no")), store, customer, label,
            fen_text(charge), fen_text(settled), fen_text(gap), state],
            "route": route or {"type": "case", "id": c["id"]}, "amount_cents": gap})

    links_by_id = {r["id"]: r for r in db["flow_payment_links"]}
    for c in cases:
        key, kind, version = c["id"], c["kind"], c["flow_version"]
        data = json.loads(c["data"])
        customer = c["title"].split(" · ")[0]
        late = bool(c["due_date"] and c["due_date"] < day())
        income = [o for o in db["vehicle_income_orders"] if o["id"] == key]
        if income and c["state"] != "cancelled":
            approved = {r["revision_id"] for r in db["vehicle_income_decisions"] if r["decision"] == "approved"}
            revisions = [r for r in db["vehicle_income_revisions"] if r["case_id"] == key and r["id"] in approved]
            target = max(revisions, key=lambda r: r["id"])["target_cents"] if revisions else 0
            received = sum(signed(r) for r in db["vehicle_income_cash"] if r["case_id"] == key)
            add(c, json.loads(income[0]["supplier_snapshot"])["name"], "厂家及供应商整车其他收入", target, received,
                max(0, target - received), "已超约定日期" if late else "尚待收取", late)
        for original in db["business_finance_return_receivables"]:
            if original["case_id"] != key:
                continue
            revisions = [r for r in db["business_finance_return_target_revisions"] if r["receivable_id"] == original["id"]]
            target = max(revisions, key=lambda r: r["revision"])["amount_cents"] if revisions else original["amount_cents"]
            add(c, "原退货供应方", "其他入库原单退货", target, paid[key], max(0, target - paid[key]), "尚待收取")
        if kind == "repair" and version in (3, 4):
            for a in db["repair_allocations"]:
                if a["case_id"] != key or a["payer_type"] == "internal":
                    continue
                adjustment = sum(r["credit_cents"] for r in db["aftercare_adjustments"]
                    if r["source_case_id"] == key and r["allocation_id"] == a["id"])
                charge = max(0, a["amount_cents"] - adjustment) + sum(r["amount_cents"] for r in db["claims_responsibility_entries"] if r["allocation_id"] == a["id"])
                settled = sum(signed(links_by_id[r["payment_link_id"]]) for r in db["repair_payments"] if r["allocation_id"] == a["id"])
                if a["payer_type"] == "customer":
                    settled += credit[key] + external_credit[key]
                gap = max(0, charge - settled)
                a_late = bool(a["due_date"] and a["due_date"] < day())
                add(c, a["payer_name"], "维修多方承担", charge, charge - gap, gap,
                    "已超约定日期" if a_late else "尚待收取", a_late)
        elif kind == "retail" and version == 2:
            reduction = sum(r["goods_cents"] + r["installation_cents"] - r["retained_cents"] for r in db["retail_return_postings"] if r["case_id"] == key)
            charge, settled = (0 if data.get("cancelled") else c["amount_cents"] - reduction), cash_paid[key] + credit[key]
            plans = [r for r in db["retail_group_plans"] if r["case_id"] == key]
            require(len(plans) <= 1, "原混合付款方案不唯一")
            if plans:
                for tender in db["retail_group_tenders"]:
                    if tender["plan_id"] != plans[0]["id"]:
                        continue
                    captures = [r for r in db["retail_group_captures"] if r["tender_id"] == tender["id"]]
                    require(len(captures) <= 1, "原支付核销不唯一")
                    if not captures:
                        continue
                    units = {r["id"] for r in db["retail_group_units"] if r["tender_id"] == tender["id"]}
                    allocations = {r["id"] for r in db["retail_group_allocations"] if r["unit_id"] in units}
                    returned = sum(r["credit_cents"] for r in db["retail_group_return_parts"]
                        if r["allocation_id"] in allocations and r["capture_id"] == captures[0]["id"])
                    settled += tender["credit_cents"] - returned
            add(c, customer, "精品销售", charge, settled, max(0, charge - settled), "尚待收取")
        elif (kind, version) in {("agency", 3), ("other_income", 2)}:
            quote_id = data.get("service_quote_id")
            if c["state"] != "cancelled" and quote_id and any(r["quote_id"] == quote_id for r in db["service_authorizations"]):
                for bucket, label in (("fee", "本店服务费"), ("pass", "客户代缴本金")):
                    charge = settled = 0
                    for line in db["service_lines"]:
                        if line["quote_id"] != quote_id or line["bucket"] != bucket:
                            continue
                        charge += line["amount_cents"] + sum(r["amount_cents"] for r in db["service_charge_adjustments"] if r["case_id"] == key and r["line_key"] == line["line_key"])
                        settled += sum(r["amount_cents"] for r in db["service_tender_slices"] if r["case_id"] == key and r["line_key"] == line["line_key"])
                    add(c, customer, label, charge, settled, max(0, charge - settled), "已超约定日期" if late else "尚待收取", late)
        elif kind == "insurance" and version == 3:
            qid = data.get("insurance_quote_id")
            if c["state"] not in {"cancelled", "rejected"} and qid and any(r["quote_id"] == qid for r in db["insurance_consents"]):
                quote = next(r for r in db["insurance_quotes"] if r["id"] == qid)
                applied = {r["plan_id"] for r in db["insurance_termination_applications"]}
                plans = [r for r in db["insurance_terminations"] if r["case_id"] == key and r["id"] in applied]
                premium = max(plans, key=lambda r: r["id"])["retained_cents"] if plans else quote["premium_cents"]
                charge = premium if quote["collection_mode"] == "store_collect" else 0
                settled = sum(r["amount_cents"] for r in db["insurance_tenders"] if r["case_id"] == key)
                add(c, customer, "客户原保费", charge, settled, max(0, charge - settled), "按原保单核对")
                approved = {r["confirmation_id"] for r in db["insurance_commission_reviews"] if r["decision"] == "approved"}
                commissions = [r for r in db["insurance_commissions"] if r["case_id"] == key and r["id"] in approved]
                charge = max(commissions, key=lambda r: r["id"])["target_cents"] if commissions else 0
                settled = sum(signed(r) for r in db["insurance_commission_payments"] if r["case_id"] == key)
                add(c, customer, "保险公司已确认佣金", charge, settled, max(0, charge - settled), "按原保单核对")
        elif kind == "addon" and version == 3:
            if c["state"] not in {"cancelled", "rejected"} and any(r["quote_id"] == data.get("addon_quote_id") for r in db["addon_authorizations"]):
                reduction = sum(r["goods_cents"] + r["installation_cents"] - r["retained_cents"] for r in db["addon_return_postings"] if r["case_id"] == key)
                charge, settled = c["amount_cents"] - reduction, cash_paid[key] + credit[key]
                add(c, customer, "加装商品及安装费", charge, settled, max(0, charge - settled), "按原授权明细核对")
        elif kind in {"order", "repair", "addon", "agency", "insurance"} and c["state"] not in {"cancelled", "rejected", "cancel_review", "refund_pending"}:
            if data.get("internal_settled") or kind == "repair" and data.get("payer") == "内部":
                continue
            charge = max(0, c["amount_cents"] - sum(r["credit_cents"] for r in db["aftercare_adjustments"] if r["source_case_id"] == key))
            generic_late = late and c["state"] in {"delivered", "credit_open", "completed"}
            label = {"order": "车辆订单", "repair": "维修工单", "addon": "精品加装", "agency": "代办服务", "insurance": "车辆保险"}[kind]
            add(c, customer, label, charge, paid[key], max(0, charge - paid[key]), "已超约定日期" if generic_late else "尚待收取", generic_late)
    # Actual-cash definition 7 excludes replacement bookkeeping and its reverse,
    # including independently corrected membership fees. It never erases refunds.
    excluded = {r["original_cash_id"] for r in db["business_finance_corrections"]}
    excluded |= {r["cash_id"] for r in db["business_finance_cash_batches"] if r["kind"] == "correction_reverse"}
    for table in ("business_finance_stored_corrections", "membership_fee_corrections"):
        for r in db[table]:
            excluded.update((r["original_cash_id"], r["reversing_cash_id"]))
    effective = [r for r in db["cash_entries"] if r["store_id"] == 1 and r["approval_state"] == "approved" and r["id"] not in excluded]
    for table, module, label in (("sales", "sales", "既有销售单"), ("repairs", "repairs", "既有维修单")):
        for c in db[table]:
            if c["store_id"] != 1 or c["approval_state"] != "approved":
                continue
            field = "sale_id" if module == "sales" else "repair_id"
            settled = sum(signed(r) for r in effective if r[field] == c["id"] and r["category"] in {"sale_collection", "repair_collection", "refund"})
            charge = c["contract_amount_cents"] if module == "sales" else c["labor_amount_cents"] + c["parts_amount_cents"] - c["discount_cents"]
            late = bool(module == "sales" and c["sale_stage"] == "delivered" and c["delivery_date"] and (datetime.fromisoformat(day()).date() - datetime.fromisoformat(c["delivery_date"]).date()).days > 3)
            add(c, c["customer_name"], label, charge, settled, max(0, charge - settled), "已交付待核对" if late else "尚待收取", late,
                route={"type": "legacy", "module": module, "id": c["id"]})
    return {"rows": result, "receivable_cents": total, "overdue_receivable_cents": overdue,
        "store_id": 1, "cash_definition_version": 7, "current_balance": True,
        "all_scope_cases": len(cases), "oracle_tables": sorted(ORACLE_TABLES)}


def report_match(data, oracle):
    actual = data["tables"]["receivables"]
    require(actual["headers"] == ["业务单号", "门店", "客户", "业务", "约定金额（元）", "累计已收（元）", "尚待收取（元）", "应收状态"], "原待收表真实列合同变化")
    canonical = lambda r: json.dumps({"values": r["values"], "route": r["route"], "amount_cents": r["amount_cents"]}, ensure_ascii=False, sort_keys=True)
    require(Counter(canonical(r) for r in actual["rows"]) == Counter(canonical(r) for r in oracle["rows"]), "整店待收明细与全部原源账不符，不能只核本次三单")
    require(data["metrics"]["receivable_cents"] == oracle["receivable_cents"]
        and data["metrics"]["overdue_receivable_cents"] == oracle["overdue_receivable_cents"]
        and sum(r["amount_cents"] for r in actual["rows"]) == oracle["receivable_cents"], "原财务整店待收总额/逾期额与全表不守恒")
    return {"full_current_store_rows": len(actual["rows"]), "all_scope_cases": oracle["all_scope_cases"],
        "receivable_cents": oracle["receivable_cents"], "overdue_receivable_cents": oracle["overdue_receivable_cents"],
        "oracle_row_sha256": sha(json.dumps(sorted(canonical(r) for r in oracle["rows"]), ensure_ascii=False).encode()),
        "all_scope_rows_equal": True, "cash_definition_version": 7, "historical_period_balance_claimed": False}


async def financial_kpi(e, data, oracle, period):
    before = e.business_snapshot("ar_before_actual_financial_kpi")
    await REPORT.click(e, e.page.locator('[data-act="open"][data-route="analytics/overview"]'), "返回原统计可视化")
    await expect(e.page.locator("#main h1")).to_have_text("数据可视化")
    await REPORT.click(e, e.page.locator('.tabs a[href="#analytics/finance"]'), "点击原财务统计标签")
    await expect(e.page).to_have_url(re.compile(r"#analytics/finance$"))
    await expect(e.page.locator('#datefilters [name="date_from"]')).to_have_value(period["date_from"])
    await expect(e.page.locator('#datefilters [name="date_to"]')).to_have_value(period["date_to"])
    kpi = e.page.locator("#main .kpi").filter(has=e.page.get_by_text("当前尚待收取", exact=True))
    await expect(kpi).to_have_count(1)
    await expect(kpi.locator(".value")).to_have_text(S.displayed_money(oracle["receivable_cents"]) + "元")
    await REPORT.click(e, kpi.locator('[data-act="charttable"][data-table="receivables"]'), "从真实财务待收总额查看完整明细")
    await expect(e.page).to_have_url(re.compile(r"#table/receivables$"))
    await expect(e.page.locator("#main h1")).to_have_text(data["tables"]["receivables"]["title"])
    e.business_unchanged(before, "ar_after_actual_financial_kpi")
    return {"label": "当前尚待收取", "value_cents": oracle["receivable_cents"], "route": "analytics/finance",
        "actual_original_kpi_clicked": True, "detail_route": "table/receivables", "dedicated_receivables_chart": "not_defined_in_original_contract"}


async def domain_drill(e, data, key, case_id, domain, expected):
    original = one(e, "flow_cases", case_id)
    row = REPORT.unique_original(data, "receivables", case_id)
    require([row["values"][i] for i in (4, 5, 6)] == [fen_text(expected[k]) for k in ("charge_cents", "paid_cents", "due_cents")]
        and row["amount_cents"] == expected["due_cents"] > 0, "新原单正欠额未真实进入原表")
    generic = await REPORT.drill_original(e, data, "receivables", row, "flow", original)
    before = e.business_snapshot("ar_before_domain_original_drill")
    route, path = {"retail": (f"retail/{case_id}", f"/api/retail/orders/{case_id}"),
        "sales": (f"sales-quotes/{case_id}", f"/api/sales-quotes/orders/{case_id}"),
        "service": (f"service-orders/{case_id}", f"/api/service-orders/{case_id}"),
        "repair": (f"repair-orders/{case_id}", f"/api/repair-orders/{case_id}")}[domain]
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        await REPORT.click(e, e.page.locator(f'#main [data-act="open"][data-route="{route}"]'), "继续核对本行原领域明细与实际原款")
    response = await pending.value
    view = await response.json()
    require(response.status == 200 and view["id"] == case_id and view["number"] == original["number"], "原领域钻取串单")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(original["number"])
    if domain == "retail":
        require(view["totals"]["charge_cents"] == 2000 and view["totals"]["cash_paid_cents"] == 500 and view["totals"]["receivable_cents"] == 1500, "原商品应收与现金不符")
        await expect(e.page.locator("#main .card").filter(has_text="尚欠")).to_contain_text("15.00")
    elif domain == "sales":
        require(view["amount_cents"] == 10000 and view["paid_cents"] == 3000 and view["vehicle_id"] == expected["vehicle"]["id"], "原销售款和新VIN不符")
    elif domain == "service":
        require(view["order"]["source_order_id"] == expected["source_case_id"] and view["summary"]["fee_charge_cents"] == 1000
            and view["summary"]["fee_paid_cents"] == 300 and view["summary"]["fee_due_cents"] == 700, "关联服务原收费/实收/正欠额不符")
    else:
        require(view["receivable_cents"] == view["customer_due_cents"] == 1500 and view["state"] == "settling"
            and not view["data"].get("released_date"), "原维修客户欠额被内部责任/接车错误清除")
        await expect(e.page.locator("#main .kpi").filter(has_text="客户尚欠")).to_contain_text("15.00")
    e.business_unchanged(before, "ar_after_domain_original_drill")
    return {"generic_original": generic, "native_domain_get": {"path": path, "status": 200}, "row": row,
        "same_case_cas": view["version"], "source_cash_id": expected["cash"]["id"], "positive_due_cents": expected["due_cents"], "business_unchanged": True}


async def report_check(e, context, credentials, fixture, check_id, targets):
    actor = await login_as(e, context, credentials, fixture["finance_key"], "module/analytics", 1)
    await expect(e.page.locator("#main h1")).to_have_text("统计分析")
    period = {"date_from": day(), "date_to": day()}
    oracle = current_oracle(e)
    data = await REPORT.open_report(e, check_id, "table/receivables", period)
    full = report_match(data, oracle)
    kpi = await financial_kpi(e, data, oracle, period)
    table = await REPORT.verify_table(e, data, "receivables", "flow")
    csv = await REPORT.export_csv(e, actor, data, "receivables", "flow", period)
    experience = await REPORT.experience(e)
    drills = []
    for index, (case_id, domain, facts) in enumerate(targets):
        if index:
            data = await REPORT.open_report(e, check_id, "table/receivables", period)
            report_match(data, oracle)
        drills.append(await domain_drill(e, data, check_id, case_id, domain, facts))
    return {"period": period, "full_store_oracle": full, "financial_kpi": kpi, "whole_table": table,
        "same_scope_csv": csv, "original_drills": drills, "experience": experience,
        "manual_review": "pending", "dedicated_graph": "no_original_receivables_graph_required"}


async def receivables(e, context, credentials):
    cp = Checkpoint(e)
    try:
        fixture, item, supplier, warehouse, location, account, customer, cv, sales_customer, work, project, model, vwarehouse, vlocation = sources(e, cp)
        token = uuid.uuid4().hex[:10].upper()
        cp.start("HK-157")
        material = await material_precondition(e, context, credentials, fixture, item, supplier, warehouse, location, account, token)
        cp.note({"necessary_original_ui_material_purchase": material})
        retail_id, retail = await retail_source(e, context, credentials, fixture, customer, item, location, account, token)
        cp.note({"original_positive_retail": retail})
        retail_report = await report_check(e, context, credentials, fixture, "HK-157", [(retail_id, "retail", retail)])
        await cp.passed({"input_to_actual_positive_due": retail, "stock_precondition": material, "report": retail_report})
        cp.start("HK-158")
        physical, purchase = await vehicle_precondition(e, context, credentials, fixture, supplier, model, vwarehouse, vlocation, account, token)
        cp.note({"necessary_original_ui_new_vehicle_purchase": purchase})
        sale_id, sale = await sales_source(e, context, credentials, fixture, sales_customer, physical, account, token)
        cp.note({"original_positive_sale": sale})
        service_id, service = await service_source(e, context, credentials, fixture, sale_id, sales_customer, project, account, token)
        cp.note({"original_positive_associated_service": service})
        sales_report = await report_check(e, context, credentials, fixture, "HK-158", [(sale_id, "sales", sale), (service_id, "service", service)])
        await cp.passed({"input_to_actual_positive_due": sale, "independent_associated_service_due": service,
            "new_vehicle_purchase": purchase, "report": sales_report})
        cp.start("HK-159")
        repair_id, repair = await repair_source(e, context, credentials, fixture, customer, cv, work, account, token)
        cp.note({"original_positive_repair": repair})
        repair_report = await report_check(e, context, credentials, fixture, "HK-159", [(repair_id, "repair", repair)])
        await cp.passed({"input_to_actual_positive_due": repair, "internal_not_customer_receivable": True, "report": repair_report})
        final = current_oracle(e)
        cp.finish({"retail_case_id": retail_id, "sales_case_id": sale_id, "associated_service_case_id": service_id,
            "repair_case_id": repair_id, "vehicle_procurement_case_id": purchase["case_id"], "new_vehicle_id": physical["vehicle"]["id"],
            "vin": purchase["vin"], "material_procurement_case_id": material["case_id"], "item_id": item["id"], "customer_id": customer["id"],
            "customer_vehicle_id": cv["id"], "sales_customer_id": sales_customer["id"], "account_id": account["id"],
            "positive_due_cents": {"retail": 1500, "sales": 7000, "associated_service": 700, "repair_customer": 1500},
            "actual_cash_ids": [retail["cash"]["id"], sale["cash"]["id"], service["cash"]["id"], repair["cash"]["id"]],
            "payment_link_ids": [retail["payment_link"]["id"], sale["payment_link"]["id"], service["payment_link"]["id"], repair["payment_link"]["id"]],
            "current_whole_store_receivable_cents": final["receivable_cents"], "cash_definition_version": 7, "historical_balance_claimed": False})
    except Exception as error:
        cp.failed(str(error))
        raise


RECEIVABLES_SCENARIOS = ((SCENARIO, receivables, 1500),)


