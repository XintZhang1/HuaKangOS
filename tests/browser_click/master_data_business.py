"""Unregistered original UI master-data acceptance candidate.

The runner supplies Evidence and existing isolated identities. Every positive
write uses a visible original form. Database access is SELECT-only; this module
does not create stock, cash, an approved business result, or application state.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import uuid

from playwright.async_api import expect

from sales_business import login_as, require
from vehicle_purchase_business import (
    checkbox, live_choice, master_form, master_page, nav, rejected_submit,
    select_value,
)

SCENARIO = "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187"
DICTIONARIES = (
    ("HK-170", "public", "公共字典"), ("HK-173", "repair", "维修字典"),
    ("HK-176", "vehicle", "整车字典"), ("HK-180", "materials", "物资字典"),
    ("HK-185", "finance", "财务字典"), ("HK-186", "customer", "客户字典"),
    ("HK-187", "member", "会员字典"),
)
REQUIREMENTS = (
    ("HK-170", "公共字典"), ("HK-172", "保险公司"), ("HK-173", "维修字典"),
    ("HK-174", "车间班组"), ("HK-175", "作业项目"), ("HK-176", "整车字典"),
    ("HK-179", "代办项目"), ("HK-180", "物资字典"), ("HK-181", "物资品牌"),
    ("HK-182", "物资分类"), ("HK-183", "物资目录"), ("HK-184", "物资仓库"),
    ("HK-185", "财务字典"), ("HK-186", "客户字典"), ("HK-187", "会员字典"),
)
TABLES = {
    "insurers": "master_insurers", "teams": "master_teams",
    "work_items": "master_work_items", "agency_projects": "master_agency_projects",
    "material_brands": "master_material_brands",
    "material_categories": "master_material_categories",
    "warehouses": "master_warehouses", "locations": "master_locations",
    "item_profiles": "master_item_profiles",
}
LABELS = {
    "insurers": "保险公司", "teams": "车间班组", "work_items": "作业项目",
    "agency_projects": "代办项目", "material_brands": "物资品牌",
    "material_categories": "物资分类", "warehouses": "仓库", "locations": "库位",
    "item_profiles": "物资归类与库位",
}
SELECT_FIELDS = {"warehouse_type", "billing_unit"}
MONEY_FIELDS = {"standard_fee_cents", "service_fee_cents"}
REFERENCE_TABLES = {
    "leader_user_id": ("users", "display_name"),
    "parent_id": ("master_material_categories", "name"),
    "warehouse_id": ("master_warehouses", "name"),
    "item_id": ("flow_items", "name"),
    "category_id": ("master_material_categories", "name"),
    "location_id": ("master_locations", "name"),
    "brand_id": ("master_material_brands", "name"),
    "supplier_id": ("master_suppliers", "name"),
}


class Checkpoint:
    """Same per-check evidence contract as the existing business candidates."""

    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        source = Path(__file__).with_name("business_acceptance_catalog.json")
        require(source.is_file(), "本轮逐项源目录未随候选镜像")
        contents = source.read_bytes()
        bindings = {row["id"]: row for row in json.loads(contents)["requirements"]}
        rows = []
        for key, title in REQUIREMENTS:
            contract = bindings.get(key)
            require(contract and contract["source_review_status"] == "source_reviewed",
                    key + " 尚未核准原源合同")
            check_id = key + "-business"
            check = next((row for row in contract["acceptance_checks"]
                          if row["check_id"] == check_id), None)
            require(check is not None, key + " 源目录 check_id 不匹配")
            rows.append({
                "id": key, "title": title, "status": "not_tested",
                "business_accepted": False,
                "acceptance_checks": [{
                    "id": check_id, "check_id": check_id, "status": "not_tested",
                    "criteria": ["原页面真实新增及编辑", "原API/ID/版本/岗位与只读DB一致",
                                 "启停及有效引用按本项原守卫", "主档不制造库存或现金"],
                    "evidence": {},
                }],
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "conditional_checks": [],
            })
        self.report = {
            "schema": 1, "scenario": SCENARIO, "scope": [row[0] for row in REQUIREMENTS],
            "complete": False, "passed": False, "full_193_business_acceptance": False,
            "full_registered_suite_complete": False,
            "execution": "native_browser_original_forms",
            "source_contract_sha256": hashlib.sha256(contents).hexdigest(),
            "requirements": rows, "source_preconditions": [],
            "conditions": {"synthetic_master_inputs": True,
                           "stock_cash_or_fulfillment_created": False,
                           "production_business_acceptance": False},
        }
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")

    def start(self, key):
        self.active = next(row for row in self.report["requirements"] if row["id"] == key)
        self.active.setdefault("evidence_action_start", len(self.e.actions))
        self.active["status"] = "running"
        self.active["acceptance_checks"][0]["status"] = "running"
        self.save()

    def defer(self, evidence):
        self.active["acceptance_checks"][0]["evidence"] = evidence
        self.active["incomplete_reason"] = "主档已维护；本场景实际物资引用及原守卫尚待完成。"
        self.save()

    async def passed(self, evidence, *, conditional=()):
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active["status"] = "passed"
        self.active["acceptance_checks"][0].update(status="passed", evidence=evidence)
        self.active["conditional_checks"] = list(conditional)
        self.active.pop("incomplete_reason", None)
        self.active["evidence_action_end"] = len(self.e.actions)
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = "failed"
            self.active["acceptance_checks"][0].update(status="failed", error=self.e.scrub(error))
            self.active["evidence_action_end"] = len(self.e.actions)
            self.report["failed_requirement"] = self.active["id"]
        for row in self.report["requirements"]:
            if row["status"] == "running":
                row["status"] = "partial"
                row["acceptance_checks"][0].update(
                    status="partial", incomplete_reason="部分原UI事实已发生；后续依赖未完成。")
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self):
        require(all(row["status"] == "passed" for row in self.report["requirements"]),
                "15项主档原合同未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=15,
                           passed_requirements=15, human_acceptance="pending")
        self.save()
        self.e.observe("master_data_business_checkpoint",
                       {"path": str(self.path), "requirements": 15, "passed": 15,
                        "business_accepted": False})


def one_row(e, table, record_id):
    rows = e.db.rows(f"SELECT * FROM {table} WHERE id=?", (record_id,))
    require(len(rows) == 1, "原主档ID不存在或不唯一")
    return rows[0]


def zero_item(e, record_id):
    row = one_row(e, "flow_items", record_id)
    require(all(row[key] == 0 for key in (
        "quantity_milli", "unit_cost_cents", "inventory_value_cents")),
        "主档配置制造了库存数量或成本")
    require(not e.db.rows("SELECT id FROM flow_stock_moves WHERE item_id=?", (record_id,)),
            "主档操作制造库存流水")
    return row


def audit_fact(e, actor, store_id, entity_type, record_id, action, reason):
    rows = e.db.rows(
        "SELECT id,actor_id,store_id,action,entity_type,entity_id,reason,before_data,after_data "
        "FROM audit_logs WHERE actor_id=? AND store_id=? AND entity_type=? "
        "AND entity_id=? AND action=? AND reason=? ORDER BY id DESC LIMIT 1",
        (actor["id"], store_id, entity_type, record_id, action, reason))
    require(len(rows) == 1, "原维护动作未留下正确员工/门店审计")
    row = rows[0]
    return {key: row[key] for key in
            ("id", "actor_id", "store_id", "action", "entity_type", "entity_id", "reason")}


async def submit_original(e, path, render_path, store_id, *, record_id=None):
    method = "PUT" if record_id is not None else "POST"
    stock_before = e.db.rows("SELECT * FROM flow_stock_moves ORDER BY id")
    cash_before = e.db.rows("SELECT * FROM cash_entries ORDER BY id")
    async with e.page.expect_response(
        lambda r: r.request.method == "GET" and urlsplit(r.url).path == render_path
    ) as rendered:
        async with e.page.expect_response(
            lambda r: r.request.method == method and urlsplit(r.url).path == path
        ) as pending:
            await e.click('#modal form button[type="submit"]', "明确保存原主档表单")
        response = await pending.value
        body = await response.json()
        require(response.status == (200 if record_id is not None else 201),
                f"原主档返回HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    read = await rendered.value
    listing = await read.json()
    require(read.status == 200, "保存后原页面读取失败")
    headers = await response.request.all_headers()
    require(bool(headers.get("cookie")) and bool(headers.get("x-csrf-token")),
            "原主档表单缺Cookie或CSRF")
    require(headers.get("x-store-id") == str(store_id), "原主档提交串店")
    request = response.request.post_data_json
    require(isinstance(request, dict) and isinstance(request.get("values"), dict),
            "原主档JSON合同不完整")
    meta = {"path": path, "method": method, "status": response.status,
            "native_ui": True, "cookie_present": True, "csrf_present": True,
            "store_id": store_id, "submitted_version": request.get("version"),
            "response_id": body.get("id"), "response_version": body.get("version"),
            "render_get_path": render_path, "render_get_status": read.status,
            "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest()
            if request.get("request_id") else None}
    require(stock_before == e.db.rows("SELECT * FROM flow_stock_moves ORDER BY id")
            and cash_before == e.db.rows("SELECT * FROM cash_entries ORDER BY id"),
            "主档保存制造或覆盖了原库存/现金流水")
    meta["stock_and_cash_rows_unchanged"] = True
    e.observe("original_master_form_response", meta)
    await expect(e.page.locator("#modal")).not_to_be_visible()
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    return body, listing, request, meta


async def fill_values(e, values):
    for key, value in values.items():
        selector = f'#modal [name="{key}"]'
        if isinstance(value, bool):
            await checkbox(e, selector, value, "明确原主档启用状态")
        elif key in SELECT_FIELDS:
            await select_value(e, selector, value, "明确原主档" + key)
        else:
            await e.fill(selector, str(value), "填写原主档" + key)


async def search_current(e, path, name):
    before = e.business_snapshot("before_master_search")
    async with e.page.expect_response(
        lambda r: r.request.method == "GET" and urlsplit(r.url).path == path
        and parse_qs(urlsplit(r.url).query).get("q") == [name]
    ) as pending:
        await e.fill('#filters [name="q"]', name, "先查本轮明确资料")
    response = await pending.value
    body = await response.json()
    require(response.status == 200, "原资料搜索失败")
    e.business_unchanged(before, "after_master_search")
    return body


async def reset_search(e, path):
    before = e.business_snapshot("before_master_search_reset")
    async with e.page.expect_response(
        lambda r: r.request.method == "GET" and urlsplit(r.url).path == path
        and not parse_qs(urlsplit(r.url).query).get("q")
    ) as pending:
        await e.click('#main [data-act="clearfilter"]', "清除搜索后维护实际资料")
    response = await pending.value
    require(response.status == 200, "原资料重置搜索失败")
    await response.body()
    await expect(e.page.locator('#filters [name="q"]')).to_have_value("")
    e.business_unchanged(before, "after_master_search_reset")


async def dictionary_page(e, group, title):
    if urlsplit(e.page.url).fragment != "dictionaries":
        await nav(e, "dictionaries", "分类设置", "/api/dictionaries/catalog")
    else:
        await expect(e.page.locator("#main h1")).to_have_text("分类设置")
    if group == "public":
        await expect(e.page.locator('.sidebar a[href="#master/references"]')).to_have_text("原有基础资料")
        await expect(e.page.locator('.sidebar a[href="#masters"]')).to_have_text("基础资料")
        await expect(e.page.locator("#main .pagehead p, #main .chartgrid p")).to_have_count(0)
    async with e.page.expect_response(
        lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/dictionaries/" + group
    ) as pending:
        await e.click(f'#main [data-act="open"][data-route="dictionaries/{group}"]',
                      "进入原" + title)
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["label"] == title, "原字典类别不匹配")
    await expect(e.page.locator("#main h1")).to_have_text(title)
    return body


async def save_dictionary(e, actor, store_id, group, title, values, *, row=None):
    selector = (f'#main [data-act="dictionary-edit"][data-group="{group}"][data-id="{row["id"]}"]'
                if row else f'#main [data-act="dictionary-new"][data-group="{group}"]')
    await e.click(selector, ("编辑" if row else "新增") + title)
    await expect(e.page.locator("#modal-title")).to_have_text(("编辑" if row else "新增") + title)
    protected = e.db.rows("SELECT * FROM flow_references WHERE id<>? ORDER BY id",
                          (row["id"] if row else 0,))
    await fill_values(e, values)
    path = "/api/dictionaries/" + group
    body, listing, request, meta = await submit_original(
        e, path + ("/" + str(row["id"]) if row else ""), path, store_id,
        record_id=row["id"] if row else None)
    saved = one_row(e, "flow_references", body["id"])
    require(saved["store_id"] == store_id and saved["category"] == title, "原字典ID串店或串类")
    for field, value in request["values"].items():
        require(saved[field] == value == body[field], "原字典UI/API/DB不一致：" + field)
    if row:
        require(request["version"] == row["version"] and saved["id"] == row["id"]
                and saved["version"] > row["version"], "原字典编辑缺真实CAS或覆盖ID")
    require(protected == e.db.rows("SELECT * FROM flow_references WHERE id<>? ORDER BY id",
                                  (saved["id"],)), "字典维护覆盖了旧条目、另一类别或另一店")
    visible = next((item for item in listing["items"] if item["id"] == saved["id"]), None)
    require(visible and all(visible[key] == saved[key] for key in
                           ("id", "store_id", "category", "name", "detail", "active", "version")),
            "原字典列表与DB不匹配")
    await expect(e.page.locator("#main tbody tr").filter(
        has=e.page.locator(f'[data-act="dictionary-edit"][data-id="{saved["id"]}"]')
    )).to_contain_text(saved["detail"])
    meta["audit"] = audit_fact(e, actor, store_id, "flow_master", saved["id"],
                              "dictionary_update" if row else "dictionary_create", title)
    meta["other_category_and_store_unchanged"] = True
    return saved, meta


async def save_typed(e, actor, store_id, kind, values, *, row=None):
    table, title = TABLES[kind], LABELS[kind]
    protected = e.db.rows(f"SELECT * FROM {table} WHERE id<>? ORDER BY id", (row["id"] if row else 0,))
    await fill_values(e, values)
    path = "/api/masters/" + kind
    body, listing, request, meta = await submit_original(
        e, path + ("/" + str(row["id"]) if row else ""), path, store_id,
        record_id=row["id"] if row else None)
    saved = one_row(e, table, body["id"])
    require(saved["store_id"] == store_id, "typed主档串店")
    require(protected == e.db.rows(f"SELECT * FROM {table} WHERE id<>? ORDER BY id", (saved["id"],)),
            "主档维护覆盖了旧资料或另一店")
    for field, value in request["values"].items():
        require(saved[field] == value == body[field], "主档UI/API/DB不一致：" + field)
    for field in MONEY_FIELDS & values.keys():
        require(request["values"][field] == int(Decimal(str(values[field])) * 100),
                "原UI金额没有精确换算整数分")
    if row:
        require(request["version"] == row["version"] and saved["id"] == row["id"]
                and saved["version"] > row["version"], "typed编辑缺真实CAS或覆盖ID")
    require(bool(request.get("request_id")), "typed原表单缺幂等请求编号")
    receipts = e.db.rows(
        "SELECT actor_id,result FROM master_receipts WHERE store_id=? AND request_key=?",
        (store_id, request["request_id"]))
    require(len(receipts) == 1 and receipts[0]["actor_id"] == actor["id"]
            and json.loads(receipts[0]["result"])["id"] == saved["id"],
            "typed原请求回执非本次员工/原ID")
    visible = next((item for item in listing["items"] if item["id"] == saved["id"]), None)
    require(visible and all(visible[key] == saved[key] for key in request["values"]),
            "typed原列表与DB不匹配")
    target = e.page.locator("#main tbody tr").filter(
        has=e.page.locator(f'[data-act="typed-edit"][data-id="{saved["id"]}"]'))
    await expect(target).to_be_visible()
    if "name" in saved:
        await expect(target).to_contain_text(saved["name"])
    for field, (reference_table, name_field) in REFERENCE_TABLES.items():
        if not saved.get(field):
            continue
        references = e.db.rows(f"SELECT id,{name_field} FROM {reference_table} WHERE id=?",
                               (saved[field],))
        require(len(references) == 1 and
                visible["reference_labels"][field] == references[0][name_field],
                "原列表引用标签与真实来源不一致：" + field)
        await expect(target).to_contain_text(references[0][name_field])
    meta["audit"] = audit_fact(e, actor, store_id, "typed_master", saved["id"],
                              "master_update" if row else "master_create", title)
    meta["old_and_other_store_rows_unchanged"] = True
    return saved, meta


async def typed_lifecycle(e, actor, store_id, kind, values, edits, *, reference=None):
    title = LABELS[kind]
    await master_page(e, kind, title)
    require((await search_current(e, "/api/masters/" + kind, values["name"]))["total"] == 0,
            "本轮新资料已存在，不能冒充新增")
    await reset_search(e, "/api/masters/" + kind)
    await master_form(e, kind, title)
    if reference:
        for key, record in reference.items():
            label = record["display_name"] if "display_name" in record else record["code"] + " · " + record["name"]
            await live_choice(e, key, record.get("name", record.get("display_name")),
                              label, expected_value=record["id"])
    row, created = await save_typed(e, actor, store_id, kind, values)
    await master_form(e, kind, title, row["id"])
    row, edited = await save_typed(e, actor, store_id, kind, edits, row=row)
    await master_form(e, kind, title, row["id"])
    row, stopped = await save_typed(e, actor, store_id, kind, {"active": False}, row=row)
    await expect(e.page.locator("#main tbody tr").filter(
        has=e.page.locator(f'[data-act="typed-edit"][data-id="{row["id"]}"]')
    )).to_contain_text("停用")
    await master_form(e, kind, title, row["id"])
    row, enabled = await save_typed(e, actor, store_id, kind, {"active": True}, row=row)
    return row, {"native_create": created, "native_edit": edited,
                 "native_stop": stopped, "native_enable": enabled, "row": row}


async def original_rejected_stop(e, kind, row):
    await master_page(e, kind, LABELS[kind])
    await master_form(e, kind, LABELS[kind], row["id"])
    await checkbox(e, '#modal [name="active"]', False, "核对有效引用不可停用")
    return await rejected_submit(e, f'/api/masters/{kind}/{row["id"]}', 409,
                                 "仍有启用的下游资料引用", method="PUT")


async def switch_store(e, store_id, user):
    before = e.business_snapshot("before_master_store_switch")
    async with e.page.expect_response(
        lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/auth/me"
        and r.request.headers.get("x-store-id") == str(store_id)
    ) as pending:
        await select_value(e, "#store", store_id, "明确切换另一真实合成门店")
    response = await pending.value
    require(response.status == 200, "原切店身份重验失败")
    await response.body()
    await expect(e.page.locator(".identity .who")).to_contain_text(user["display_name"])
    await expect(e.page.locator("#store")).to_have_value(str(store_id))
    e.business_unchanged(before, "after_master_store_switch")


async def save_item(e, actor, store_id, values, *, row=None):
    selector = (f'#main [data-act="editmaster"][data-kind="items"][data-id="{row["id"]}"]'
                if row else '#main [data-act="newmaster"][data-kind="items"]')
    await e.click(selector, "编辑原物资" if row else "新增原零库存物资")
    await expect(e.page.locator("#modal-title")).to_have_text(("编辑" if row else "新增") + "物资目录")
    await expect(e.page.locator('#modal [name="quantity"], #modal [name="quantity_milli"], '
                                '#modal [name="unit_cost_cents"], #modal [name="inventory_value_cents"]')).to_have_count(0)
    protected = e.db.rows("SELECT * FROM flow_items WHERE id<>? ORDER BY id", (row["id"] if row else 0,))
    await fill_values(e, values)
    path = "/api/flow/master/items"
    body, listing, request, meta = await submit_original(
        e, path + ("/" + str(row["id"]) if row else ""), path, store_id,
        record_id=row["id"] if row else None)
    saved = zero_item(e, body["id"])
    require(saved["store_id"] == store_id, "原物资串店")
    for key in ("sku", "name", "unit", "active"):
        require(saved[key] == body[key] == request["values"][key], "原物资字段不一致：" + key)
    require(saved["reorder_milli"] == int(Decimal(request["values"]["reorder"]) * 1000),
            "原补货数量没有精确换算千分位")
    if row:
        require(request["version"] == row["version"] and saved["version"] > row["version"],
                "原物资编辑缺版本守卫")
    require(protected == e.db.rows("SELECT * FROM flow_items WHERE id<>? ORDER BY id", (saved["id"],)),
            "物资目录覆盖了旧物资或另一店")
    visible = next((item for item in listing["items"] if item["id"] == saved["id"]), None)
    require(visible and visible["quantity"] == visible["available_quantity"] == visible["reserved_quantity"] == "0",
            "零库存物资原查询数量不正确")
    await expect(e.page.locator("#main tbody tr").filter(
        has=e.page.locator(f'[data-act="editmaster"][data-id="{saved["id"]}"]')
    )).to_contain_text(saved["name"])
    meta["audit"] = audit_fact(e, actor, store_id, "flow_master", saved["id"],
                              "master_update" if row else "master_create", "物资目录")
    return saved, meta


async def master_data_business(e, context, credentials):
    checkpoint = Checkpoint(e)
    try:
        fixture = e.manifest["business_fixtures"]["vehicle_purchase"]
        store_id = fixture["store_id"]
        other = next((row for row in e.manifest["stores"] if row["id"] != store_id), None)
        require(other is not None, "领域字典隔离需要另一真实合成门店")
        token = uuid.uuid4().hex[:10].upper()
        dictionary_name = "合成主档同名字典" + token
        # Cross-store counterparts are themselves produced by original admin UI.
        # This is permitted master maintenance, not independent business approval.
        checkpoint.start("HK-170")
        admin = await login_as(e, context, credentials, "admin", "dictionaries", store_id)
        await expect(e.page.locator("#main h1")).to_have_text("分类设置")
        await switch_store(e, other["id"], admin)
        counterparts = {}
        for _, group, title in DICTIONARIES:
            await dictionary_page(e, group, title)
            row, meta = await save_dictionary(
                e, admin, other["id"], group, title,
                {"name": dictionary_name, "detail": "另一店原" + title, "active": True})
            counterparts[group] = row
            checkpoint.report["source_preconditions"].append({
                "kind": "original_ui_other_store_dictionary", "group": group,
                "id": row["id"], "store_id": other["id"], "native": meta})
            checkpoint.save()
        await switch_store(e, store_id, admin)
        manager = await login_as(e, context, credentials, fixture["manager_key"],
                                 "dictionaries", store_id)
        for key, group, title in DICTIONARIES:
            checkpoint.start(key)
            await dictionary_page(e, group, title)
            require((await search_current(e, "/api/dictionaries/" + group, dictionary_name))["total"] == 0,
                    "当前店泄露另一店同名字典")
            row, created = await save_dictionary(
                e, manager, store_id, group, title,
                {"name": dictionary_name, "detail": "本店已核对" + title, "active": True})
            row, edited = await save_dictionary(
                e, manager, store_id, group, title, {"detail": "本店简短说明：" + title}, row=row)
            row, stopped = await save_dictionary(e, manager, store_id, group, title, {"active": False}, row=row)
            row, enabled = await save_dictionary(e, manager, store_id, group, title, {"active": True}, row=row)
            require(one_row(e, "flow_references", counterparts[group]["id"]) == counterparts[group],
                    "本店维护覆盖另一店同名条目")
            await checkpoint.passed({"row": row, "native": [created, edited, stopped, enabled],
                                     "other_store_same_name": counterparts[group],
                                     "other_category_and_store_unchanged": True})

        for key, kind, values, edits, references in (
            ("HK-172", "insurers",
             {"code": "MDI" + token, "name": "合成保险公司" + token, "active": True,
              "license_number": "SYNTHETIC" + token, "claims_phone": "13800000172", "settlement_days": 7},
             {"claims_phone": "13800000173", "settlement_days": 14}, None),
            ("HK-174", "teams",
             {"code": "MDT" + token, "name": "合成车间班组" + token, "active": True},
             {"name": "合成车间班组已核对" + token}, {"leader_user_id": manager}),
            ("HK-175", "work_items",
             {"code": "MDW" + token, "name": "合成按项检查" + token, "active": True,
              "billing_unit": "job", "standard_minutes": 30, "standard_fee_cents": "120.35", "warranty_days": 30},
             {"standard_fee_cents": "123.45", "standard_minutes": 45}, None),
            ("HK-179", "agency_projects",
             {"code": "MDA" + token, "name": "合成代办项目" + token, "active": True,
              "service_fee_cents": "80.25", "expected_days": 3},
             {"service_fee_cents": "85.40", "expected_days": 5}, None),
        ):
            checkpoint.start(key)
            row, evidence = await typed_lifecycle(
                e, manager, store_id, kind, values, edits, reference=references)
            if kind == "teams":
                require(row["leader_user_id"] == manager["id"], "班组未引用真实本店主管")
            await checkpoint.passed(evidence, conditional=[{
                "check_id": key + "-open-business-reference",
                "classification": "conditional_when_source_present", "status": "not_tested",
                "reason": "本轮只维护新主档，尚无该主档的未结交易引用；不宣称交易引用拒绝已验证",
            }])

        inventory = await login_as(e, context, credentials, fixture["inventory_key"],
                                   "masters/material_brands", store_id)
        checkpoint.start("HK-181")
        brand, brand_evidence = await typed_lifecycle(
            e, inventory, store_id, "material_brands",
            {"code": "MDB" + token, "name": "合成物资品牌" + token, "active": True},
            {"name": "合成物资品牌已核对" + token})
        checkpoint.defer(brand_evidence)
        checkpoint.start("HK-182")
        parent, parent_evidence = await typed_lifecycle(
            e, inventory, store_id, "material_categories",
            {"code": "MDCP" + token, "name": "合成物资父类" + token, "active": True},
            {"name": "合成物资父类已核对" + token})
        category, category_evidence = await typed_lifecycle(
            e, inventory, store_id, "material_categories",
            {"code": "MDCC" + token, "name": "合成物资子类" + token, "active": True},
            {"name": "合成物资子类已核对" + token}, reference={"parent_id": parent})
        require(category["parent_id"] == parent["id"], "分类树未使用本轮实际父类")
        cycle_evidence = []
        for target in (category, parent):
            await master_page(e, "material_categories", "物资分类")
            await master_form(e, "material_categories", "物资分类", target["id"])
            await live_choice(e, "parent_id", category["name"],
                              category["code"] + " · " + category["name"], expected_value=category["id"])
            cycle_evidence.append(await rejected_submit(
                e, f'/api/masters/material_categories/{target["id"]}', 422,
                "物资分类不能引用自身或形成循环", method="PUT"))
        parent_stop = await original_rejected_stop(e, "material_categories", parent)
        checkpoint.defer({"parent": parent_evidence, "child": category_evidence,
                          "self_and_cycle_refusals": cycle_evidence, "active_child_stop_refusal": parent_stop})

        checkpoint.start("HK-184")
        warehouse, warehouse_evidence = await typed_lifecycle(
            e, inventory, store_id, "warehouses",
            {"code": "MDWM" + token, "name": "合成材料专用仓" + token, "active": True,
             "warehouse_type": "materials", "address": "合成材料库区一"},
            {"address": "合成材料库区已核对"})
        location, location_evidence = await typed_lifecycle(
            e, inventory, store_id, "locations",
            {"code": "MDL" + token, "name": "合成材料库位" + token, "active": True},
            {"name": "合成材料库位已核对" + token}, reference={"warehouse_id": warehouse})
        require(location["warehouse_id"] == warehouse["id"] and warehouse["warehouse_type"] == "materials",
                "材料仓与库位真实关系错误")
        warehouse_stop = await original_rejected_stop(e, "warehouses", warehouse)
        checkpoint.defer({"warehouse": warehouse_evidence, "location": location_evidence,
                          "active_location_stop_refusal": warehouse_stop})

        checkpoint.start("HK-183")
        await nav(e, "master/items", "物资目录", "/api/flow/master/items")
        require((await search_current(e, "/api/flow/master/items", "合成零库存物资" + token))["total"] == 0,
                "本轮物资已存在")
        item, item_created = await save_item(
            e, inventory, store_id, {"sku": "MDITEM" + token, "name": "合成零库存物资" + token,
                                    "unit": "升", "reorder": "1.125", "active": True})
        item, item_edited = await save_item(e, inventory, store_id, {"reorder": "2.375"}, row=item)
        require(item["reorder_milli"] == 2375, "原补货阈值千分位错误")
        await master_page(e, "item_profiles", "物资归类与库位")
        await master_form(e, "item_profiles", "物资归类与库位")
        for key, record in (("item_id", item), ("category_id", category),
                            ("location_id", location), ("brand_id", brand)):
            label = record.get("code", record.get("sku")) + " · " + record["name"]
            await live_choice(e, key, record["name"], label, expected_value=record["id"])
        profile, profile_created = await save_typed(e, inventory, store_id, "item_profiles", {"active": True})
        require(profile["item_id"] == item["id"] and profile["category_id"] == category["id"]
                and profile["location_id"] == location["id"] and profile["brand_id"] == brand["id"]
                and profile["supplier_id"] is None, "物资实际归类/库位/品牌不匹配")
        original_profile = dict(profile)
        await master_form(e, "item_profiles", "物资归类与库位", profile["id"])
        profile, profile_edited = await save_typed(e, inventory, store_id, "item_profiles", {"active": False}, row=profile)
        await master_form(e, "item_profiles", "物资归类与库位", profile["id"])
        profile, profile_enabled = await save_typed(e, inventory, store_id, "item_profiles", {"active": True}, row=profile)
        for key in ("item_id", "category_id", "location_id", "brand_id", "supplier_id"):
            require(profile[key] == original_profile[key],
                "编辑物资归类覆盖了原引用")
        brand_guard = await original_rejected_stop(e, "material_brands", brand)
        category_guard = await original_rejected_stop(e, "material_categories", category)
        location_guard = await original_rejected_stop(e, "locations", location)
        zero_item(e, item["id"])
        # Finance reads the actual joined brand and integer stock/value fields;
        # its original catalog must not expose maintenance buttons.
        async with e.page.expect_response(
            lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/master/items"
        ) as pending:
            finance = await login_as(e, context, credentials, fixture["finance_key"], "master/items", store_id)
        response = await pending.value
        listing = await response.json()
        require(response.status == 200, "财务原目录读取失败")
        found = next((row for row in listing["items"] if row["id"] == item["id"]), None)
        require(found and found["brand_id"] == brand["id"] and found["brand_name"] == brand["name"]
                and found["brand_code"] == brand["code"], "原物资列表没有显示实际品牌关联")
        require(found["quantity"] == found["available_quantity"] == found["reserved_quantity"] == "0"
                and found["inventory_value_cents"] == 0, "原列表零库存/成本不一致")
        await expect(e.page.locator("#main")).to_contain_text(brand["name"])
        await expect(e.page.locator('#main [data-act="newmaster"], #main [data-act="editmaster"]')).to_have_count(0)
        shared = {"item": zero_item(e, item["id"]), "profile": profile,
                  "finance_read": {"user_id": finance["id"], "status": response.status,
                                   "path": "/api/flow/master/items", "row": found,
                                   "write_controls": 0},
                  "new_item_stock_moves": 0}
        checkpoint.start("HK-181")
        await checkpoint.passed({**brand_evidence, **shared, "active_profile_stop_refusal": brand_guard})
        checkpoint.start("HK-182")
        await checkpoint.passed({"parent": parent_evidence, "child": category_evidence, **shared,
                                 "self_and_cycle_refusals": cycle_evidence,
                                 "active_child_stop_refusal": parent_stop,
                                 "active_profile_stop_refusal": category_guard})
        checkpoint.start("HK-184")
        await checkpoint.passed({"warehouse": warehouse_evidence, "location": location_evidence, **shared,
                                 "active_location_stop_refusal": warehouse_stop,
                                 "active_profile_location_stop_refusal": location_guard}, conditional=[{
            "check_id": "HK-184-physical-stock-history", "status": "not_tested",
            "classification": "conditional_when_source_present",
            "reason": "本轮新仓仅主档与零库存引用；实物启用/收发和有历史改型拒绝留后续仓储原链",
        }])
        checkpoint.start("HK-183")
        await checkpoint.passed({**shared, "native_create": item_created, "native_edit": item_edited,
                                 "native_profile": [profile_created, profile_edited, profile_enabled]})
        checkpoint.finish()
    except Exception as error:
        checkpoint.failed(error)
        raise


MASTER_DATA_SCENARIOS = ((SCENARIO, master_data_business, 480),)

