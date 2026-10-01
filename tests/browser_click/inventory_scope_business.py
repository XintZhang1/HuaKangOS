"""HK071: real employee stores, independent receipt and local physical transit.

Only original visible UI writes. Same-run passed checkpoints supply finite IDs;
SQLite is SELECT-only, and private credentials never enter the evidence report.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import uuid
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import expect

from sales_business import login_as, require
from sales_order_business import checkpoint_evidence, fixed_dependency
from system_management_business import field, fresh_identity, native_login, revoked_page, switch_store
from vehicle_purchase_business import checkbox, nav, select_value
from material_business import (MASTER, SCENARIO as MATERIAL, facts, item_stock, money,
    one as material_one, qty, warehouse_command, warehouse_create)
from warehouse_operations_business import SCENARIO as WAREHOUSE
from interstore_business import SCENARIO as INTERSTORE
from roles_dossier_business import (SCENARIO as ROLES_DOSSIER, SYSTEM, SYSTEM_FOLLOWON,
    change_access, memberships, one as role_one, users_page)
import receivables_business as AR

SCENARIO = "inventory-store-scope-hk071"
AMOUNT = 500


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Checkpoint:
    def __init__(self, e):
        self.e = e
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(raw)
        source = next(r for r in json.loads(raw)["requirements"] if r["id"] == "HK-071")
        require(source["title"] == "机构库存查询" and source["source_review_status"] == "source_reviewed"
                and any(c["check_id"] == "HK-071-business" for c in source["acceptance_checks"]), "HK071原题/check未核准")
        self.active = {"id": "HK-071", "title": source["title"], "status": "running", "business_accepted": False,
            "evidence_action_start": len(e.actions), "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
            "acceptance_checks": [{"id": "HK-071-business", "check_id": "HK-071-business", "status": "running",
                "criteria": ["本人明确改权及两店非空库存", "原本店500实际在途/接收与数量成本守恒", "未授权404/汇总只读/恢复会话失效", "全旧行与原流水保护"], "evidence": {}}]}
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": ["HK-071"], "complete": False, "passed": False,
            "candidate_sha256": sha(Path(__file__).read_bytes()), "source_contract_sha256": self.digest,
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "execution": "native_browser_original_forms", "requirements": [self.active], "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "human_acceptance": "pending",
            "conditions": {"synthetic_physical_inputs": True, "fixture_results_created": False, "production_acceptance": False},
            "conditional_not_tested": ["并发占量/改权竞争", "资源上限/任意越权HTTP", "真实员工/PG/Linux/生产条件", "其他店/整车库存"]}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def note(self, **values):
        # Fail on accidental bytes or another non-JSON fact, rather than stringify.
        json.dumps(values, ensure_ascii=False)
        self.active["acceptance_checks"][0]["evidence"].update(values)
        self.save()

    def failed(self, error):
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
        self.report.update(error=self.e.scrub(error), failed_requirement="HK-071", executed_requirements=1, passed_requirements=0)
        self.save()

    async def finish(self, sources):
        await self.e.snapshot("hk071-business")
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.report.update(complete=True, passed=True, executed_requirements=1, passed_requirements=1, report_sources=sources)
        self.save()
        self.e.observe("inventory_store_scope_checkpoint", {"path": str(self.path), "business_accepted": False})


def sources(e, cp):
    root, runtime = Path(e.manifest["evidence_root"]).resolve(), Path(e.manifest["runtime_root"]).resolve()
    require(e.manifest.get("synthetic_data_only") is True and Path(e.manifest["database_path"]).resolve().is_relative_to(runtime), "库存候选只允许本次外部合成实例")
    raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(raw)
    require(provenance["snapshot_stable"] is True, "库存来源镜像不稳定")
    for name in ("inventory_scope_business.py", "roles_dossier_business.py", "sales_business.py", "sales_order_business.py",
                 "system_management_business.py", "system_followon_business.py", "vehicle_purchase_business.py",
                 "material_business.py", "master_data_business.py", "warehouse_operations_business.py",
                 "interstore_business.py", "receivables_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name).read_bytes()), "库存来源脚本不是同轮字节：" + name)
    cp.report["mirror"] = {"source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"], "provenance_sha256": sha(raw)}
    parents = {name: fixed_dependency(e, cp, name) for name in (SYSTEM, MASTER, MATERIAL, WAREHOUSE, INTERSTORE)}
    seen, pending = set(parents), [d for p in parents.values() for d in p.get("dependencies", [])]
    while pending:
        name = pending.pop()["scenario"]
        if name not in seen:
            seen.add(name)
            parent = fixed_dependency(e, cp, name)
            pending.extend(parent.get("dependencies", []))
    summary = json.loads((root / "browser-click-report.json").read_text(encoding="utf-8"))
    optional = {}
    for name in (SYSTEM_FOLLOWON, ROLES_DOSSIER):
        if any(r["id"] == name for r in summary["scenarios"]):
            optional[name] = fixed_dependency(e, cp, name)
    if SYSTEM_FOLLOWON in optional:
        require(optional[SYSTEM_FOLLOWON].get("temporary_auditor_restored") is True, "系统后继临时授权未恢复")
    staff = checkpoint_evidence(parents[SYSTEM], "HK-191")["staff_actions"]
    require(len(staff) >= 2 and staff[1]["default_sales"] is True, "原系统缺UI新员工乙")
    employee = role_one(e, "users", staff[1]["user_id"])
    first, second = e.manifest["stores"][0]["id"], e.manifest["stores"][1]["id"]
    original_roles = memberships(e, employee["id"])
    require(first == 1 and second == 2 and original_roles == {first: "manager"}
            and original_roles == {int(k): v for k, v in staff[1]["store_roles"].items()}
            and employee["role"] == "sales" and employee["active"] == 1 and employee["must_change_password"] == 0,
            "乙本人当前原岗位/门店或密码阶段不符")
    observations = json.loads((root / SYSTEM / "observations.json").read_text(encoding="utf-8"))
    pointers = [r["value"] for r in observations if r["label"] == "synthetic_system_private_credentials"]
    require(len(pointers) == 1 and pointers[0]["credentials_in_evidence"] is False, "原系统缺唯一私有指针")
    private_path = Path(pointers[0]["path"]).resolve()
    require(private_path.parent == runtime and private_path.name.startswith("system-management-accounts-"), "私有来源不属于本次runtime")
    private = json.loads(private_path.read_text(encoding="utf-8"))
    require(private["synthetic_data_only"] is True, "私有账号不是合成来源")
    account = private["accounts"]["manager"]
    require(account["id"] == employee["id"] and account["username"] == employee["username"]
            and account["current_password_stage"] in account, "乙原账号/当前私有代次不符")
    e.secrets.extend(v for k, v in account.items() if isinstance(v, str) and k not in {"username", "current_password_stage"})
    if ROLES_DOSSIER in optional:
        previous = optional[ROLES_DOSSIER]["report_sources"]["current_employees"]["sender"]
        require(previous["id"] == employee["id"] and previous["access_version"] == employee["access_version"]
                and {int(k): v for k, v in previous["store_roles"].items()} == original_roles
                and previous["private_source_scenario"] == SYSTEM and previous["private_account_key"] == "manager"
                and previous["current_password_stage"] == account["current_password_stage"], "HK190乙代次/真实恢复事实不符")
    primary = parents[MATERIAL]["material_sources"]["primary"]
    master_bin = checkpoint_evidence(parents[MASTER], "HK-184")["location"]["row"]["id"]
    material_bin = checkpoint_evidence(parents[MATERIAL], "HK-069")["second_location"]["row"]["id"]
    require(master_bin != material_bin and {master_bin, material_bin} <= set(primary["location_ids"])
            and primary["source_location_id"] == master_bin, "两实际原bin不是主档+材料来源")
    item = material_one(e, "flow_items", primary["item_id"])
    locations = [material_one(e, "master_locations", key) for key in (master_bin, material_bin)]
    warehouse = material_one(e, "master_warehouses", primary["warehouse_id"])
    require(warehouse["active"] == 1 and warehouse["warehouse_type"] == "materials"
            and all(r["active"] == 1 and r["warehouse_id"] == warehouse["id"] and r["store_id"] == first for r in locations)
            and item["store_id"] == first and item["active"] == 1, "实际原物资/库位已不可用")
    stock = item_stock(e, item["id"])
    require(stock["enrollment"]["id"] == primary["enrollment_id"], "实际启用来源不同")
    purchase_original = parents[MATERIAL]["source_preconditions"]
    supplier = material_one(e, "master_suppliers", purchase_original["supplier"]["id"])
    bank_account = material_one(e, "flow_accounts", purchase_original["account"]["id"])
    require(supplier["store_id"] == bank_account["store_id"] == first and supplier["active"] and bank_account["active"]
        and supplier["version"] == purchase_original["supplier"]["version"] and bank_account["account_type"] == "bank"
        and warehouse["id"] == purchase_original["warehouse"]["id"]
        and locations[0]["id"] == purchase_original["location"]["id"], "新实际采购的原供应商/账户/源库位关系错误")
    foreign = parents[INTERSTORE]["report_sources"]
    destination = material_one(e, "flow_items", foreign["destination_item_id"])
    foreign_bin = material_one(e, "master_locations", foreign["destination_material_location_id"])
    require(foreign["source_item_id"] == item["id"] and destination["id"] != item["id"]
            and destination["store_id"] == foreign_bin["store_id"] == second and destination["active"] == foreign_bin["active"] == 1
            and destination["quantity_milli"] > 0, "二店非空有限原Item/库位不足或串来源")
    local_other = parents[WAREHOUSE]["warehouse_sources"]["consumable"]
    wh_item = material_one(e, "flow_items", local_other["item_id"])
    require(wh_item["store_id"] == first and wh_item["quantity_milli"] > 0
            and local_other["source_location_id"] == master_bin, "同轮仓储八项非空原来源不符")
    cp.note(source_preconditions={"employee_id": employee["id"], "original_store_roles": original_roles,
        "current_access_version": employee["access_version"], "private_password_stage": account["current_password_stage"],
        "private_credentials_in_evidence": False, "primary_item_id": item["id"], "source_location_id": master_bin,
        "destination_location_id": material_bin, "second_store_item_id": destination["id"],
        "second_store_location_id": foreign_bin["id"], "warehouse_other_item_id": wh_item["id"], "parent_closure": sorted(seen)})
    return {"receiver": employee, "employee": employee, "account": account, "first": first, "second": second,
        "original_roles": original_roles, "original_summary": bool(employee["can_group_summary"]),
        "item": item, "locations": locations, "foreign_item": destination, "foreign_bin": foreign_bin,
        "other_item": wh_item, "fixture": e.manifest["business_fixtures"]["vehicle_purchase"],
        "purchase_supplier": supplier, "purchase_warehouse": warehouse, "purchase_account": bank_account}


def availability(e, item_id):
    """Read the original reservation components, with no application imports."""
    retail = e.db.rows("SELECT COALESCE(SUM(quantity_milli),0) AS q FROM retail_reservations WHERE item_id=?", (item_id,))[0]["q"]
    addon = e.db.rows("SELECT COALESCE(SUM(quantity_milli),0) AS q FROM addon_reservations WHERE item_id=?", (item_id,))[0]["q"]
    holds = e.db.rows("SELECT COALESCE(SUM(quantity_milli),0) AS q FROM warehouse_holds WHERE item_id=?", (item_id,))[0]["q"]
    transit = e.db.rows("SELECT COALESCE(SUM(quantity_milli),0) AS q FROM warehouse_balances WHERE item_id=? AND transit_case_id IS NOT NULL", (item_id,))[0]["q"]
    returns = e.db.rows("SELECT COALESCE(SUM(l.quantity_milli),0) AS q FROM procurement_return_lines l JOIN procurement_returns r ON r.id=l.return_id JOIN procurement_receipts p ON p.id=l.receipt_id JOIN procurement_lines i ON i.id=p.line_id JOIN flow_cases c ON c.id=r.case_id WHERE r.status='approved' AND c.flow_version=3 AND i.item_id=?", (item_id,))[0]["q"]
    counts = e.db.rows("SELECT c.id,d.source_location_id,o.baseline_quantity_milli,o.counted_quantity_milli FROM warehouse_documents d JOIN flow_cases c ON c.id=d.id LEFT JOIN warehouse_count_observations o ON o.case_id=c.id WHERE d.item_id=? AND d.operation='count' AND c.state IN ('counting','review')", (item_id,))
    count = 0
    for row in counts:
        if row["baseline_quantity_milli"] is not None:
            count += max(0, row["baseline_quantity_milli"] - row["counted_quantity_milli"])
        else:
            found = e.db.rows("SELECT quantity_milli FROM warehouse_balances WHERE item_id=? AND location_id=?", (item_id, row["source_location_id"]))
            count += found[0]["quantity_milli"] if found else 0
    reserved = retail + addon + holds + transit + returns + count
    item = material_one(e, "flow_items", item_id)
    require(all(type(v) is int for v in (retail, addon, holds, transit, returns, count, reserved)), "原占额不是整数千分位")
    return {"reserved_milli": reserved, "available_milli": max(0, item["quantity_milli"] - reserved),
            "retail": retail, "addon": addon, "holds": holds, "transit": transit, "approved_return": returns, "count": count}


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


async def read_meta(response, store):
    headers = await response.request.all_headers()
    require(headers.get("cookie") and headers.get("x-app-request") == "1" and headers.get("x-store-id") == str(store), "本人原读取缺正确Cookie/门店")
    return {"path": urlsplit(response.url).path, "method": "GET", "status": response.status,
            "current_store": store, "native_ui": True, "cookie_present": True}


async def access_form(e, src, roles, summary):
    listed = await users_page(e)
    target = role_one(e, "users", src["employee"]["id"])
    row = next(r for r in listed["items"] if r["id"] == target["id"])
    require(row["access_version"] == target["access_version"], "原员工列表编辑版已不同")
    await e.click(f'#main [data-act="edituser"][data-id="{target["id"]}"]', "原管理者编辑本轮乙授权")
    await expect(e.page.locator("#modal")).to_be_visible()
    await expect(e.page.locator("#modal-title")).to_have_text("编辑员工")
    await field(e, "display_name", target["display_name"])
    await select_value(e, '#modal [name="role"]', "sales", "保留账号默认销售岗位")
    await checkbox(e, '#modal [name="active"]', True, "保留账号启用")
    await checkbox(e, '#modal [name="can_group_summary"]', summary, "明确授权店汇总开关")
    boxes = e.page.locator('#modal [name="store_ids"]')
    choices = [int(await boxes.nth(i).get_attribute("value")) for i in range(await boxes.count())]
    require(set(roles) <= set(choices), "原编辑缺所需真实门店")
    for sid in choices:
        await checkbox(e, f'#modal [name="store_ids"][value="{sid}"]', sid in roles, "逐店明确本员工访问")
        if sid in roles:
            await select_value(e, f'#modal [name="store_role_{sid}"]', roles[sid], "保留一店管理并明确二店审计")
    return target, row


async def employee_login(e, context, contexts, src, store, role):
    _, page = await fresh_identity(e, context, contexts)
    e.page = page
    account = src["account"]
    observed = await native_login(e, src["employee"], account[account["current_password_stage"]])
    require(set(observed["store_ids"]) == set(memberships(e, src["employee"]["id"])), "本人登录门店投影不同")
    if await page.locator("#store").input_value() != str(store):
        observed = await switch_store(e, store, src["employee"], role)
    else:
        require(observed["current_role"] == role, "本人当前门店岗位不同")
    return page, observed


async def unauthorized(e, item, foreign_store):
    require(await e.page.locator(f'#store option[value="{foreign_store}"]').count() == 0, "未授权二店仍是本人选择项")
    before = e.business_snapshot("before_original_unauthorized_stock")
    path = f'/api/warehouse/items/{item["id"]}/stock'
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        e.action("navigate", "本人原未授权物资深链接只读拒绝", item_id=item["id"])
        await e.page.goto(e.origin + f'/#warehouse-item/{item["id"]}', wait_until="domcontentloaded")
    response = await pending.value
    body = await response.json()
    require(response.status == 404 and body == {"detail": "当前门店物资不存在"}, "原未授权404投影泄露或状态不同")
    await expect(e.page.locator("#main .errorpage h2")).to_have_text("暂时无法显示")
    await expect(e.page.locator("#main .notice.error")).to_have_text(body["detail"])
    await expect(e.page.locator("#main")).not_to_contain_text(item["name"])
    await expect(e.page.locator("#main")).not_to_contain_text(item["sku"])
    await expect(e.page.locator("#main tbody")).to_have_count(0)
    e.business_unchanged(before, "after_original_unauthorized_stock")
    return {"native": await read_meta(response, 1), "body": body, "foreign_store_option_absent": True, "business_unchanged": True}


async def stock_read(e, item_id, store, role, *, search=True):
    before = e.business_snapshot("before_original_inventory_store_read")
    original = item_stock(e, item_id)
    item, available = original["item"], availability(e, item_id)
    require(item["store_id"] == store and item["quantity_milli"] > 0, "本店非空实际Item前序不足")
    listing = None
    if search:
        await nav(e, "warehouse", "库位与仓储作业", "/api/warehouse/catalog")
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/warehouse/items"
                and parse_qs(urlsplit(r.url).query).get("q") == [item["sku"]]) as pending:
            await e.fill('#filters [name="q"]', item["sku"], "输入有限本店原物资编码检索")
        response = await pending.value
        listing = await response.json()
        require(response.status == 200 and len(listing["items"]) == listing["total"] == 1
                and listing["items"][0]["id"] == item_id, "本店原编码没有唯一可见原Item")
        button = e.page.locator(f'#main [data-act="open"][data-route="warehouse-item/{item_id}"]')
        await expect(button).to_be_visible()
        await expect(button).to_be_enabled()
    path = f"/api/warehouse/items/{item_id}/stock"
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        if search:
            await e.click(f'#main [data-act="open"][data-route="warehouse-item/{item_id}"]', "本人打开实际库位与原流水")
        elif urlsplit(e.page.url).fragment == f"warehouse-item/{item_id}":
            e.action("navigate", "本人重新读取当前在途原库存", item_id=item_id)
            await e.page.reload(wait_until="domcontentloaded")
        else:
            e.action("navigate", "本人读取有限当前原库存", item_id=item_id)
            await e.page.goto(e.origin + f"/#warehouse-item/{item_id}", wait_until="domcontentloaded")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["id"] == item_id and body["name"] == item["name"] and body["sku"] == item["sku"]
            and body["unit"] == item["unit"] and body["version"] == item["version"] and body["enabled"] is True
            and body["quantity_milli"] == item["quantity_milli"] and body["value_cents"] == item["inventory_value_cents"]
            and body["available_milli"] == available["available_milli"] and body["reserved_milli"] == available["reserved_milli"],
            "本人本店原库存/成本/当前占额与SELECT不符")
    for kind in ("balances", "entries"):
        require({r["id"] for r in body[kind]} == {r["id"] for r in original[kind]}, "本店原位置/流水不完整")
        for shown in body[kind]:
            row = next(r for r in original[kind] if r["id"] == shown["id"])
            for key in shown.keys() & row.keys():
                require(shown[key] == row[key], "本店原库存列与DB不同：" + key)
            if kind == "balances":
                if row["location_id"] is not None:
                    location = material_one(e, "master_locations", row["location_id"])
                    require(location["store_id"] == store and shown["location_name"] == location["name"], "位置串店或原名称不同")
                else:
                    require(row["transit_case_id"] is not None and shown["location_name"] == "店内移库在途", "在途缺原单或名称错误")
                    case = material_one(e, "flow_cases", row["transit_case_id"])
                    doc = material_one(e, "warehouse_documents", row["transit_case_id"])
                    require(case["store_id"] == store and case["kind"] == "warehouse"
                            and doc["operation"] == "local_move" and doc["item_id"] == item_id, "在途原单串店或物资")
            else:
                require(row["store_id"] == store and material_one(e, "flow_cases", row["case_id"])["store_id"] == store,
                        "原库位流水串门店")
    await expect(e.page.locator("#main h1")).to_have_text("物资真实库位")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(item["name"] + " · " + item["sku"])
    await expect(e.page.locator("#main")).to_contain_text(f'账面 {qty(item["quantity_milli"])}，当前可用 {qty(available["available_milli"])}')
    await expect(e.page.locator("#main")).to_contain_text(f'预占／在途／盘点保留 {qty(available["reserved_milli"])} {item["unit"]}')
    await expect(e.page.locator("#main")).to_contain_text(f'门店库存价值 {money(item["inventory_value_cents"])} 元')
    panels = e.page.locator("#main .panel")
    bins = panels.filter(has=e.page.get_by_text("库位及店内在途", exact=True))
    entries = panels.filter(has=e.page.get_by_text("不可变库位流水", exact=True))
    require(await bins.locator("tbody tr").count() == len(body["balances"])
            and await entries.locator("tbody tr").count() == len(body["entries"]), "原UI位置/流水行数不完整")
    for index, shown in enumerate(body["balances"]):
        # Several completed local moves legitimately retain separate zero
        # transit buckets with the same visible name. Preserve original order.
        cells = bins.locator("tbody tr").nth(index)
        await expect(cells.locator("td").nth(0)).to_have_text(shown["location_name"])
        await expect(cells.locator("td").nth(1)).to_have_text(qty(shown["quantity_milli"]))
        await expect(cells.locator("td").nth(2)).to_have_text(money(shown["value_cents"]))
    for index, shown in enumerate(body["entries"]):
        cells = entries.locator("tbody tr").nth(index)
        await expect(cells.locator("td").nth(1)).to_have_text(qty(shown["quantity_milli"]))
        await expect(cells.locator("td").nth(2)).to_have_text(money(shown["value_cents"]))
        await expect(cells.locator(f'[data-route="case/{shown["case_id"]}"]')).to_have_count(1)
    if role == "auditor":
        await expect(e.page.locator('#main [data-act="wh-new"], #main [data-act="wh-action"], #main [data-act="upload"]')).to_have_count(0)
    e.business_unchanged(before, "after_original_inventory_store_read")
    return {"native": await read_meta(response, store), "current_role": role, "api": body,
            "db": original, "availability_components": available, "search_result": listing, "read_only": True}


def sufficient(e, src):
    item_id, bin_id = src["item"]["id"], src["locations"][0]["id"]
    state, available = item_stock(e, item_id), availability(e, item_id)
    source = [b for b in state["balances"] if b["location_id"] == bin_id]
    held = e.db.rows("SELECT COALESCE(SUM(quantity_milli),0) AS q FROM warehouse_holds WHERE item_id=? AND location_id=?", (item_id, bin_id))[0]["q"]
    fences = e.db.rows("SELECT c.id FROM flow_cases c JOIN warehouse_documents d ON d.id=c.id WHERE d.item_id=? AND d.source_location_id=? AND d.operation='count' AND c.state='counting'", (item_id, bin_id))
    require(len(source) == 1 and available["available_milli"] >= AMOUNT and source[0]["quantity_milli"] - held >= AMOUNT
            and not fences, "原明确源位当前不足500或现场盘点围栏；不换数量/造余额")
    require(all(b["quantity_milli"] == 0 for b in state["balances"] if b["transit_case_id"] is not None), "父原店内在途尚未收尾")
    return state


def protected_totals(e, baseline):
    state = item_stock(e, baseline["item"]["id"])
    require({k: v for k, v in state["item"].items() if k not in {"version", "updated_at"}}
            == {k: v for k, v in baseline["item"].items() if k not in {"version", "updated_at"}}
            and state["stock_moves"] == baseline["stock_moves"] and state["enrollment"] == baseline["enrollment"],
            "店内移库覆盖物资总量/成本/原收发/启用历史")
    return state


def physical_entries(e, baseline, after, case_id, changes, reason, actor_id):
    before = {b["id"]: b for b in baseline["balances"]}
    current = {b["id"]: b for b in after["balances"]}
    require(set(before) <= set(current), "原库位被删除")
    total, value = after["item"]["quantity_milli"], after["item"]["inventory_value_cents"]
    expected_qty = {key: before.get(key, {"quantity_milli": 0})["quantity_milli"] + changes.get(key, 0) for key in current}
    require(sum(expected_qty.values()) == total, "店内真实位置/在途总量不守恒")
    target = {key: value * amount // total for key, amount in expected_qty.items()}
    remaining = value - sum(target.values())
    ranked = sorted(current, key=lambda key: (-(value * expected_qty[key] % total), key))
    for key in ranked[:remaining]:
        target[key] += 1
    for key, row in current.items():
        require(row["quantity_milli"] == expected_qty[key] and row["value_cents"] == target[key], "原均价最大余数法分配不符")
    old_ids = {r["id"] for r in baseline["entries"]}
    new = [r for r in after["entries"] if r["id"] not in old_ids]
    expected = {key: (changes.get(key, 0), target[key] - before.get(key, {"value_cents": 0})["value_cents"])
                for key in current if changes.get(key, 0) or target[key] != before.get(key, {"value_cents": 0})["value_cents"]}
    require(len(new) == len(expected) and {r["balance_id"] for r in new} == set(expected), "真实位置流水数量/来源不完整或重复")
    for row in new:
        delta, cents = expected[row["balance_id"]]
        require(row["case_id"] == case_id and row["quantity_milli"] == delta and row["value_cents"] == cents
                and row["stock_move_id"] is None and row["actor_id"] == actor_id
                and row["reason"] == (reason if delta else "average_revaluation"), "原本地流水来源/数量/成本或经办不符")
    require(sum(r["quantity_milli"] for r in new) == sum(r["value_cents"] for r in new) == 0, "本地两位/在途流水量值净额不为零")
    require(not e.db.rows("SELECT id FROM flow_stock_moves WHERE case_id=?", (case_id,)), "原店内移库制造门店收发流水")
    return new


def original_action(e, case_id, metadata, action, label, actor_id):
    """Strengthen the reused original helper with this finite action receipt."""
    added = metadata["guard"]["appended_ids"]
    require(len(added["audit_logs"]) == len(added["flow_events"]) == len(added["flow_request_receipts"]) == 1,
            "一次本地原动作必须唯一事件/审计/回执")
    current = facts(e, case_id)["case"]
    audit = e.db.rows("SELECT * FROM audit_logs WHERE id=?", (added["audit_logs"][0],))[0]
    event = e.db.rows("SELECT * FROM flow_events WHERE id=?", (added["flow_events"][0],))[0]
    receipt = e.db.rows("SELECT * FROM flow_request_receipts WHERE id=?", (added["flow_request_receipts"][0],))[0]
    require(audit["actor_id"] == event["actor_id"] == receipt["actor_id"] == actor_id
            and audit["store_id"] == current["store_id"] == 1 and audit["entity_type"] == "flow"
            and audit["entity_id"] == event["case_id"] == receipt["case_id"] == case_id
            and audit["action"] == "flow_warehouse_" + action and event["action"] == "warehouse_" + action
            and audit["reason"] == event["label"] == label and json.loads(audit["before_data"]) is None
            and json.loads(audit["after_data"]) == {"store_id": 1, "state": current["state"], "number": current["number"]},
            "本地原动作审计/事件/回执来源错误")
    if action == "create":
        request = metadata["request"]
        payload = {"source_location_id": None, "destination_location_id": None, "original_move_id": None,
                   "recipient": "", "locations": [], **{k: v for k, v in request.items() if k != "request_id"}}
        require(receipt["request_key"] == request["request_id"] and event["before_state"] == "", "原创建回执请求号/事件基准不符")
    else:
        payload = {"id": case_id, "version": metadata["native"]["submitted_version"], **metadata["submitted_values"]}
        if action == "approve":
            # The original strict Approve schema adds its nullable default
            # before hashing, although the visible local-move form omits it.
            payload["value_cents"] = None
        require(sha(receipt["request_key"].encode()) == metadata["native"]["request_id_sha256"], "原命令回执请求号不同")
    expected = sha(json.dumps({"operation": "warehouse_" + action, "payload": payload},
                             sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
    require(receipt["digest"] == expected, "原本地动作完整输入摘要不符")
    return {"audit": audit, "event_id": event["id"], "receipt_id": receipt["id"], "digest": receipt["digest"]}


async def aggregate(e, src):
    before = e.business_snapshot("before_native_inventory_aggregate")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/auth/me") as pending:
        await select_value(e, "#store", "all", "本人选择已授权两店只读汇总")
    response = await pending.value
    me = await response.json()
    require(response.status == 200 and me["id"] == src["employee"]["id"] and me["aggregate_scope"] is True
            and me["role"] == "auditor" and me["active_store_id"] is None
            and set(me["group_store_ids"]) == {src["first"], src["second"]}, "原库存汇总扩大授权范围")
    # The original default route gives every aggregate scope its read-only
    # analytics page, independently of the assistant home feature switch.
    await expect(e.page).to_have_url(e.origin + "/#analytics/overview")
    await expect(e.page.locator("#main h1")).to_have_text("数据可视化")
    link = e.page.locator('.sidebar a[href="#warehouse"]')
    await expect(link).to_have_count(1)
    parent = link.locator("xpath=ancestor::details[1]")
    if await parent.count() and await parent.get_attribute("open") is None:
        e.action("click", "展开原物资导航后核对汇总限制")
        await parent.locator(":scope > summary").click()
    await expect(link).to_be_visible()
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/warehouse/catalog") as pending:
        await e.click('.sidebar a[href="#warehouse"]', "本人核对汇总不能办理原仓储作业")
    response = await pending.value
    require(response.status == 200, "汇总仓储原目录读取失败")
    catalog = await response.json()
    await expect(e.page.locator("#main .empty strong")).to_have_text("请切换到获权门店")
    require(all(catalog[key] is False for key in ("can_read", "can_create", "can_money")), "汇总模式仓储原作业权限错误")
    await expect(e.page.locator('#main [data-act="wh-new"], #main [data-act="wh-action"]')).to_have_count(0)
    body = await nav(e, "master/items", "物资目录", "/api/flow/master/items")
    expected = e.db.rows("SELECT * FROM flow_items WHERE store_id IN (?,?) ORDER BY id DESC", (src["first"], src["second"]))
    require(body["total"] == len(expected), "原集团目录范围不同于实际授权两店")
    seen, pages = [], []
    while True:
        require(body["page_size"] == 30 and body["page"] == len(pages) + 1, "原目录分页合同不同")
        offset = len(pages) * body["page_size"]
        originals = expected[offset:offset + body["page_size"]]
        require([r["id"] for r in body["items"]] == [r["id"] for r in originals], "原汇总行漏项/串未授权店/顺序错误")
        await expect(e.page.locator("#main tbody tr")).to_have_count(len(originals))
        for index, (shown, row) in enumerate(zip(body["items"], originals)):
            current = availability(e, row["id"])
            require(shown["store_id"] == row["store_id"] and shown["sku"] == row["sku"] and shown["name"] == row["name"]
                    and Decimal(shown["quantity"]) == Decimal(row["quantity_milli"]) / 1000
                    and Decimal(shown["available_quantity"]) == Decimal(current["available_milli"]) / 1000
                    and Decimal(shown["reserved_quantity"]) == Decimal(current["reserved_milli"]) / 1000
                    and shown["inventory_value_cents"] == row["inventory_value_cents"], "原汇总本地ID/账面/可用/占额或成本错误")
            # Codes can legitimately repeat across stores; the original API
            # and native table share their explicit per-page row order.
            ui = e.page.locator("#main tbody tr").nth(index)
            for col, value in ((0, row["sku"]), (1, row["name"]), (3, shown["quantity"]),
                    (4, shown["reserved_quantity"]), (5, shown["available_quantity"]), (6, row["unit"])):
                await expect(ui.locator("td").nth(col)).to_have_text(value)
            seen.append(shown["id"])
        await expect(e.page.locator('#main [data-act="newmaster"], #main [data-act="editmaster"], #main [data-act="wh-new"], #main [data-act="wh-action"]')).to_have_count(0)
        pages.append(body)
        if len(seen) == body["total"]:
            break
        require(body["items"], "汇总目录空页不能算完整")
        next_page = len(pages) + 1
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/master/items"
                and parse_qs(urlsplit(r.url).query).get("page") == [str(next_page)]) as pending:
            await e.click(f'#main [data-act="page"][data-page="{next_page}"]', "本人逐页核完整已授权物资目录")
        response = await pending.value
        require(response.status == 200, "原汇总下一页读取失败")
        body = await response.json()
        await expect(e.page.locator("#main h1")).to_have_text("物资目录")
    require(len(seen) == len(set(seen)) == len(expected)
            and {src["item"]["id"], src["foreign_item"]["id"], src["other_item"]["id"]} <= set(seen), "汇总缺本轮两店非空原来源")
    await expect(e.page.locator("#main")).to_contain_text("当前为多门店汇总。办理业务时请先选择具体门店。")
    e.business_unchanged(before, "after_native_inventory_aggregate")
    return {"actual_group_store_ids": me["group_store_ids"], "warehouse_catalog": catalog,
            "master_pages": pages, "read_only": True, "group_totals_are_not_local_available_quantity": True}


async def inventory_scope_business(e, context, credentials):
    cp, src, contexts = Checkpoint(e), None, []
    main_page, employee_page, admin = e.page, None, None
    try:
        src = sources(e, cp)
        purchased = await AR.material_precondition(e, context, credentials, src["fixture"], src["item"],
            src["purchase_supplier"], src["purchase_warehouse"], src["locations"][0], src["purchase_account"], "HK071-" + uuid.uuid4().hex[:12])
        cp.note(necessary_original_ui_material_purchase=purchased)
        src["item"] = purchased["current_stock"]["item"]
        sufficient(e, src)
        employee_page, original_login = await employee_login(e, context, contexts, src, src["first"], "manager")
        denied_before = await unauthorized(e, src["foreign_item"], src["second"])
        first = await stock_read(e, src["item"]["id"], src["first"], "manager")
        cp.note(initial_personal_login=original_login, unauthorized_before=denied_before, initial_local_nonempty=first)
        e.page = main_page
        admin = await admin_users_login(e, context, credentials, src["first"])
        roles = {src["first"]: "manager", src["second"]: "auditor"}
        target, listed = await access_form(e, src, roles, True)
        added = await change_access(e, src, admin, target, listed, roles, True, "inventory_explicit_add_store")
        revoked_initial = await revoked_page(e, employee_page, src["employee"]["id"])
        employee_page, new_login = await employee_login(e, context, contexts, src, src["first"], "manager")
        await expect(e.page.locator(f'#store option[value="{src["second"]}"]')).to_have_count(1)
        second_switch = await switch_store(e, src["second"], src["employee"], "auditor")
        second = await stock_read(e, src["foreign_item"]["id"], src["second"], "auditor")
        require(any(b["location_id"] == src["foreign_bin"]["id"] and b["quantity_milli"] > 0 for b in second["db"]["balances"]), "二店有限实际验收原位没有实物")
        cp.note(explicit_access_added=added, old_session_revoked=revoked_initial, reauthenticated=new_login,
                actual_second_store_switch=second_switch, second_store_nonempty=second)
        await switch_store(e, src["first"], src["employee"], "manager")
        baseline = sufficient(e, src)
        e.page = main_page
        case_id, proof, created = await warehouse_create(e, context, credentials, src["fixture"], baseline["item"],
            "local_move", AMOUNT, source=src["locations"][0], destination=src["locations"][1])
        inventory_actor = e.manifest["users"][src["fixture"]["inventory_key"]]["id"]
        require(facts(e, case_id)["case"]["created_by"] == inventory_actor, "移库不是本库管原申请")
        created["exact_original_action"] = original_action(e, case_id, created, "create", "申请店内移库", inventory_actor)
        _, approved = await warehouse_command(e, context, credentials, src["fixture"], case_id, src["item"]["id"], "approve", proof)
        approval_actor = approved["event"]["actor_id"]
        require(approval_actor != facts(e, case_id)["case"]["created_by"] and approved["api"]["state"] == "ready", "本移库未独立批准")
        approved["exact_original_action"] = original_action(e, case_id, approved, "approve", "批准作业", approval_actor)
        approvals = e.db.rows("SELECT * FROM warehouse_approvals WHERE case_id=?", (case_id,))
        reserves = e.db.rows("SELECT * FROM warehouse_holds WHERE case_id=?", (case_id,))
        require(len(approvals) == len(reserves) == 1 and approvals[0]["actor_id"] == reserves[0]["actor_id"] == approval_actor
                and approvals[0]["evidence_id"] == proof["id"] and approvals[0]["value_cents"] == 0
                and reserves[0]["item_id"] == src["item"]["id"] and reserves[0]["location_id"] == src["locations"][0]["id"]
                and reserves[0]["quantity_milli"] == AMOUNT and reserves[0]["reason"] == "reserve", "原独立批准及500精确预占来源不符")
        approved_stock = protected_totals(e, baseline)
        require(approved_stock["balances"] == baseline["balances"] and approved_stock["entries"] == baseline["entries"], "原批准提前变更实物库位")
        _, dispatched = await warehouse_command(e, context, credentials, src["fixture"], case_id, src["item"]["id"], "dispatch", proof)
        dispatched["exact_original_action"] = original_action(e, case_id, dispatched, "dispatch", "确认实际移出", inventory_actor)
        transit_stock = protected_totals(e, baseline)
        transit = [b for b in transit_stock["balances"] if b["transit_case_id"] == case_id]
        source_bin = next(b for b in baseline["balances"] if b["location_id"] == src["locations"][0]["id"])
        require(len(transit) == 1 and transit[0]["quantity_milli"] == AMOUNT and facts(e, case_id)["case"]["state"] == "transit", "本原单500未进入明确店内在途")
        dispatch_entries = physical_entries(e, baseline, transit_stock, case_id,
            {source_bin["id"]: -AMOUNT, transit[0]["id"]: AMOUNT}, "local_dispatch", dispatched["event"]["actor_id"])
        e.page = employee_page
        in_transit = await stock_read(e, src["item"]["id"], src["first"], "manager", search=False)
        require(in_transit["availability_components"]["transit"] == AMOUNT
                and any(b["transit_case_id"] == case_id and b["quantity_milli"] == AMOUNT for b in in_transit["api"]["balances"]), "本人查询缺非零当前在途")
        cp.note(local_move_created=created, proof={k: proof[k] for k in ("id", "case_id", "store_id", "name", "category", "size", "sha256")},
                independently_approved=approved, actually_dispatched=dispatched, dispatch_entries=dispatch_entries,
                nonzero_transit_read=in_transit)
        group = await aggregate(e, src)
        await switch_store(e, src["first"], src["employee"], "manager")
        e.page = main_page
        _, accepted = await warehouse_command(e, context, credentials, src["fixture"], case_id, src["item"]["id"], "accept", proof, quantity=AMOUNT)
        accepted["exact_original_action"] = original_action(e, case_id, accepted, "accept", "确认实际接收", inventory_actor)
        final = protected_totals(e, baseline)
        destination = next(b for b in final["balances"] if b["location_id"] == src["locations"][1]["id"])
        accept_entries = physical_entries(e, transit_stock, final, case_id,
            {transit[0]["id"]: -AMOUNT, destination["id"]: AMOUNT}, "local_accept", accepted["event"]["actor_id"])
        original = facts(e, case_id)
        require(original["case"]["state"] == "completed" and original["case"]["completed_date"]
                and all(t["status"] != "open" for t in original["tasks"])
                and all(b["quantity_milli"] == 0 for b in final["balances"] if b["transit_case_id"] is not None)
                and e.db.rows("SELECT COALESCE(SUM(quantity_milli),0) AS q FROM warehouse_holds WHERE case_id=?", (case_id,))[0]["q"] == 0,
                "实际接收没有完成/清零在途/释放本原预占")
        e.page = employee_page
        received = await stock_read(e, src["item"]["id"], src["first"], "manager", search=False)
        require(received["availability_components"]["transit"] == 0, "本人接收后仍将旧在途当现存")
        cp.note(authorized_group_readonly=group, actual_accept=accepted, accept_entries=accept_entries, final_local_nonempty=received)
        e.page = main_page
        admin = await admin_users_login(e, context, credentials, src["first"])
        target, listed = await access_form(e, src, src["original_roles"], src["original_summary"])
        restored = await change_access(e, src, admin, target, listed, src["original_roles"], src["original_summary"], "inventory_explicit_restore")
        revoked_expanded = await revoked_page(e, employee_page, src["employee"]["id"])
        employee_page, restored_login = await employee_login(e, context, contexts, src, src["first"], "manager")
        denied_after = await unauthorized(e, src["foreign_item"], src["second"])
        require(memberships(e, src["employee"]["id"]) == src["original_roles"]
                and role_one(e, "users", src["employee"]["id"])["access_version"] == src["employee"]["access_version"] + 2,
                "本人原岗位未恢复或访问代次被回写")
        cp.note(original_roles_restored=restored, expanded_session_revoked=revoked_expanded,
                restored_personal_login=restored_login, unauthorized_after=denied_after)
        await cp.finish({"employee_id": src["employee"]["id"], "current_store_roles": memberships(e, src["employee"]["id"]),
            "current_access_version": role_one(e, "users", src["employee"]["id"])["access_version"], "private_source_scenario": SYSTEM,
            "private_account_key": "manager", "current_password_stage": src["account"]["current_password_stage"],
            "first_store_item_id": src["item"]["id"], "second_store_item_id": src["foreign_item"]["id"],
            "local_move_case_id": case_id, "source_location_id": src["locations"][0]["id"],
            "destination_location_id": src["locations"][1]["id"], "transit_balance_id": transit[0]["id"],
            "dispatch_entry_ids": [r["id"] for r in dispatch_entries], "accept_entry_ids": [r["id"] for r in accept_entries],
            "actual_transit_quantity_milli": AMOUNT, "final_transit_quantity_milli": 0, "original_roles_restored": True})
    except BaseException as error:
        cp.failed(str(error))
        if src is not None and (memberships(e, src["employee"]["id"]) != src["original_roles"]
                or bool(role_one(e, "users", src["employee"]["id"])["can_group_summary"]) != src["original_summary"]):
            try:
                if not e.db.rows("SELECT user_id FROM login_sessions WHERE user_id=?", (src["employee"]["id"],)):
                    await employee_login(e, context, contexts, src, src["first"], memberships(e, src["employee"]["id"])[src["first"]])
                e.page = main_page
                admin = await admin_users_login(e, context, credentials, src["first"])
                target, listed = await access_form(e, src, src["original_roles"], src["original_summary"])
                restored = await change_access(e, src, admin, target, listed, src["original_roles"], src["original_summary"], "failed_inventory_role_restore")
                cp.note(failed_run_explicit_role_restoration=restored)
            except BaseException as cleanup_error:
                cp.note(role_restoration_error=e.scrub(str(cleanup_error)))
        raise
    finally:
        if e.response_jobs:
            await asyncio.gather(*list(e.response_jobs))
        e.page = main_page
        for separate in reversed(contexts):
            await separate.close()


INVENTORY_SCOPE_SCENARIOS = ((SCENARIO, inventory_scope_business, 900),)
