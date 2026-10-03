"""Two phases on one sealed synthetic instance, across a real Shanghai date.

Original visible forms create all facts. SELECT-only evidence and the existing
browser Evidence/helpers are reused. Stage is preparation, never an expiry or
historical-period pass; verify cannot run until the following calendar date.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo

from playwright.async_api import expect

import customer_reminders_business as C
import material_business as M
import report_complete_source_business as R
import warehouse_operations_business as W
from customer_service_business import fields
from report_business import click, drill_original, graph, verify_table
from sales_business import require
from sales_order_business import fixed_dependency
from vehicle_purchase_business import nav

STAGE = "day-boundary-original-ui-stage"
VERIFY = "day-boundary-hk099-expiry-hk152-complete-period"
STAGE_FILE = "day-boundary-stage.json"
ZONE = ZoneInfo("Asia/Shanghai")
BINDING = ("origin", "source_root", "runtime_root", "evidence_root", "database_path", "credentials_path")
TABLE_KEYS = ("warehouse_period_balances", "warehouse_period_baselines", "warehouse_period_entries")
REASONS = {"wh_other_in": "其他实际入库", "wh_consumable": "耗材实际领用", "wh_consume_return": "耗材原单退回"}
TABLE_HEADERS = {
    "warehouse_period_balances": ["门店", "物资编码", "物资", "单位", "仓库", "库位或店内在途", "期初数量", "完整期间入库数量", "完整期间出库数量", "已知期末数量",
        "期初价值（元）", "入库有符号价值变动（元）", "出库有符号价值变动（元）", "均价分摊调整（元）", "已知期末价值（元）", "期间是否完整", "期末是否完整", "来源说明"],
    "warehouse_period_baselines": ["门店", "物资编码", "单位", "仓库", "库位或在途", "实际启用时刻（UTC）", "分配基准数量", "分配基准价值（元）"],
    "warehouse_period_entries": ["门店", "实际日期", "物资编码", "单位", "仓库", "库位或在途", "实际业务", "原库位流水", "原物资流水", "数量变化", "有符号价值变化（元）"],
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def day():
    return datetime.now(ZONE).date()


def stamp_day(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp).astimezone(ZONE).date()


def utc_z(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(stamp.tzinfo is None or stamp.utcoffset() == timedelta(0), "批准来源时间必须是原 UTC 时间")
    return stamp.replace(tzinfo=None).isoformat() + "Z"


def qty(value):
    return format(Decimal(value) / 1000, "f")


def yuan(value):
    return format(Decimal(value) / 100, ".2f")


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def fixed_mirror(manifest):
    require(manifest.get("schema") == 1 and manifest.get("synthetic_data_only") is True, "只允许已有外置合成实例")
    root = Path(manifest["runtime_root"]).resolve().parent
    for key, folder in (("source_root", "source"), ("runtime_root", "runtime"), ("evidence_root", "evidence")):
        require(Path(manifest[key]).resolve() == root / folder, "跨日实例目录结构不符：" + key)
    require(Path(manifest["database_path"]).resolve().is_relative_to(root / "runtime")
        and Path(manifest["credentials_path"]).resolve().is_relative_to(root / "runtime")
        and Path(__file__).resolve().parent == root / "scripts", "跨日只能运行 stage 固定外部镜像脚本")
    origin = urlsplit(manifest["origin"])
    require(origin.scheme in {"http", "https"} and origin.hostname in {"127.0.0.1", "localhost"}
        and not origin.username and not origin.password and origin.path in {"", "/"}, "跨日只允许本机原生隔离 origin")
    path = root / "evidence" / "provenance.json"
    provenance = json.loads(path.read_text(encoding="utf-8"))
    require(provenance.get("snapshot_stable") is True, "stage 来源镜像未冻结")
    for kind, folder in (("source_files", root / "source"), ("script_files", root / "scripts")):
        inventory = provenance[kind]
        require(isinstance(inventory, dict) and inventory, "跨日缺少完整固定清单：" + kind)
        for name, expected in inventory.items():
            parts = PurePosixPath(name.replace("\\", "/"))
            require(not parts.is_absolute() and ".." not in parts.parts, "固定清单路径逃逸")
            target = (folder / Path(*parts.parts)).resolve()
            require(target.is_relative_to(folder) and target.is_file() and sha(target) == expected,
                "跨日固定源码或脚本已改变：" + name)
    require(provenance["script_files"].get(Path(__file__).name) == sha(__file__), "跨日脚本未纳入正式镜像清单")
    return {"provenance_sha256": sha(path), "source_sha256": provenance["source_sha256"],
        "script_sha256": provenance["script_sha256"], "candidate_sha256": sha(__file__)}


def resume_checkpoint(manifest):
    """Preflight before restarting; does not initialize, import app or write DB."""
    mirror = fixed_mirror(manifest)
    path = Path(manifest["evidence_root"]).resolve() / STAGE / STAGE_FILE
    stage = json.loads(path.read_text(encoding="utf-8"))
    require(stage.get("schema") == 1 and stage.get("stage_complete") is True
        and stage.get("natural_boundary_verified") is False and stage.get("phase") == "stage",
        "跨日 stage 尚未完整封存")
    require(stage["binding"] == {k: manifest[k] for k in BINDING} and stage["mirror"] == mirror,
        "verify 不属于同一个 stage 实例和固定源码镜像")
    original_suite = stage["original_suite_report"]
    original_path = Path(original_suite["path"]).resolve()
    require(original_path == Path(manifest["evidence_root"]).resolve() / "browser-click-report.json"
        and sha(original_path) == original_suite["sha256"], "跨日覆写或替换了原合成套件证据")
    first = date.fromisoformat(stage["stage_date"])
    require(day() == first + timedelta(days=1), "只能在实际上海 D+1 验证，禁止改钟、提前或拼接另一个日期")
    require(stage["grant"]["valid_until"] == first.isoformat() and stage["grant"]["status"] == "active"
        and stamp_day(stage["warehouse"]["activation_event"]["occurred_at"]) == first,
        "两项独立门槛没有同一 D 日原来源")
    return stage, {"path": str(path), "sha256": sha(path), "stage_date": first.isoformat(),
        "verify_date": day().isoformat(), "same_instance": True, "same_frozen_mirror": True}


class Checkpoint:
    def __init__(self, e, phase):
        self.e, self.phase = e, phase
        require(phase in {"stage", "verify"} and e.directory.resolve() == Path(e.manifest["evidence_root"]).resolve() / (STAGE if phase == "stage" else VERIFY),
            "跨日证据只能写当前 phase 的外部独立目录")
        self.path = e.directory / "business-checkpoint.json"
        self.digest = sha(Path(__file__).with_name("business_acceptance_catalog.json"))
        self.report = {"schema": 1, "scenario": STAGE if phase == "stage" else VERIFY, "phase": phase,
            "source_contract_sha256": self.digest, "complete": False, "passed": False,
            "business_accepted": False, "full_193_business_acceptance": False,
            "human_acceptance": "pending", "requirements": [],
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "conditions": {"synthetic_data_only": True, "clock_changed": False,
                "sql_business_writes": False, "real_model_calls": 0, "production_acceptance": False}}
        self.save()

    def save(self):
        write_json(self.path, self.report)

    def note(self, **value):
        self.report.update(value)
        self.save()

    def failed(self, error):
        self.note(error=self.e.scrub(str(error)), complete=False, passed=False)


async def native_history(e, vehicle_id, sid):
    path = C.CARE + f"/vehicles/{vehicle_id}/history"
    async with e.page.expect_response(lambda r: C.match(r, path)) as pending:
        result = await C.history(e, vehicle_id)
    response = await pending.value
    headers = await response.request.all_headers()
    require(response.status == 200 and urlsplit(response.url).netloc == urlsplit(e.origin).netloc
        and headers.get("cookie") and headers.get("x-store-id") == str(sid), "原摘要读取缺本人当前店或原生 Cookie")
    return result, {"path": path, "status": 200, "store_id": sid, "native_browser_request": True, "cookie_present": True}


def receiver_credentials(e, private_path, expected=None):
    path = Path(private_path).resolve()
    require(path.parent == Path(e.manifest["runtime_root"]).resolve()
        and path.name.startswith("system-management-accounts-") and path.is_file(), "接收员工私有合成凭据范围不符")
    if expected:
        require(sha(path) == expected, "接收员工私有合成凭据不是 stage 固定来源")
    private = json.loads(path.read_text(encoding="utf-8"))
    require(private.get("synthetic_data_only") is True, "接收员工凭据不是合成来源")
    account = private["accounts"]["receiver"]
    require(account.get("current_password_stage") in account, "接收员工当前改密阶段缺失")
    for entry in private["accounts"].values():
        e.secrets.extend(v for k, v in entry.items() if isinstance(v, str) and k not in {"username", "current_password_stage"})
    return account, account[account["current_password_stage"]], {"path": str(path), "sha256": sha(path), "credentials_in_evidence": False}


def warehouse_sources(e, item_id):
    stock = M.item_stock(e, item_id)
    enrollment = stock["enrollment"]
    activation = M.facts(e, enrollment["case_id"])
    events = [r for r in activation["events"] if r["action"] == "warehouse_approve"]
    require(len(events) == 1 and activation["case"]["state"] == "completed", "缺唯一真实启用批准原事实")
    document = W.one(e, "warehouse_documents", enrollment["case_id"])
    allocations = e.db.rows("SELECT * FROM warehouse_allocations WHERE case_id=? AND item_id=? AND purpose='activation'",
        (enrollment["case_id"], item_id))
    require(document["operation"] == "activate" and len(allocations) == 1 and allocations[0]["status"] == "consumed",
        "启用原单或实际消耗分配缺失")
    lines = e.db.rows("SELECT * FROM warehouse_allocation_lines WHERE allocation_id=? ORDER BY id", (allocations[0]["id"],))
    opening = e.db.rows("SELECT * FROM opening_stock_entries WHERE item_id=? ORDER BY id", (item_id,))
    before = [m for m in stock["stock_moves"] if m["id"] <= enrollment["stock_move_cursor"]]
    baseline = [r for r in stock["entries"] if r["case_id"] == enrollment["case_id"] and r["stock_move_id"] is None]
    require(not opening and not before and not baseline and len(lines) == 1 and lines[0]["quantity_milli"] == 0
        and enrollment["baseline_quantity_milli"] == enrollment["baseline_value_cents"] == 0,
        "零启用基准不得猜造原期初/收发，须与原 OpeningStock/StockMove 守恒")
    return {**stock, "activation_case": activation["case"], "activation_event": events[0],
        "activation_document": document, "activation_allocation": allocations[0], "activation_lines": lines,
        "opening_stock_entries": opening, "stock_moves_before_cursor": before}


def warehouse_oracle(e, data, sources, warehouse, location, store, period, expected_moves):
    """Primitive original-row integer sums, never a copied app calculation call."""
    stock = warehouse_sources(e, sources["item"]["id"])
    item, enrollment = stock["item"], stock["enrollment"]
    require(stock["activation_event"] == sources["activation_event"] and enrollment == sources["enrollment"]
        and stock["activation_case"] == sources["activation_case"]
        and stock["activation_document"] == sources["activation_document"]
        and stock["activation_allocation"] == sources["activation_allocation"]
        and stock["activation_lines"] == sources["activation_lines"], "跨日改变了真实批准桥接原件")
    require(len(stock["balances"]) == 1 and stock["balances"][0]["location_id"] == location["id"]
        and location["warehouse_id"] == warehouse["id"] and all(r["store_id"] == store["id"] for r in (item, enrollment, location, warehouse)),
        "跨日原来源不是唯一同店同物资真实库位")
    require(stock["stock_moves"] == expected_moves and len(stock["entries"]) == len(expected_moves), "原收发被漏列、重复或换成未登记来源")
    by_move = {r["id"]: r for r in expected_moves}
    for entry in stock["entries"]:
        move = by_move.get(entry["stock_move_id"])
        require(move is not None and entry["reason"] == move["purpose"] and entry["reason"] in REASONS
            and all(entry[k] == move[k] for k in ("store_id", "case_id", "quantity_milli", "value_cents", "business_date", "actor_id")),
            "库位流水没有逐条对应原物资/员工/日期/数量/有符号成本")
        require(W.one(e, "flow_cases", move["case_id"])["state"] == "completed", "原实物作业尚未完成")
    entries = stock["entries"]
    first, last = period["date_from"], period["date_to"]
    selected = sorted([r for r in entries if first <= r["business_date"] <= last], key=lambda r: (r["business_date"], r["id"]))
    opening = {"quantity_milli": sum(r["quantity_milli"] for r in entries if r["business_date"] < first),
        "value_cents": sum(r["value_cents"] for r in entries if r["business_date"] < first)}
    incoming = {"quantity_milli": sum(r["quantity_milli"] for r in selected if r["quantity_milli"] > 0),
        "value_cents": sum(r["value_cents"] for r in selected if r["quantity_milli"] > 0)}
    outgoing = {"quantity_milli": sum(-r["quantity_milli"] for r in selected if r["quantity_milli"] < 0),
        "value_cents": sum(r["value_cents"] for r in selected if r["quantity_milli"] < 0)}
    closing = {"quantity_milli": sum(r["quantity_milli"] for r in entries if r["business_date"] <= last),
        "value_cents": sum(r["value_cents"] for r in entries if r["business_date"] <= last)}
    revalue = sum(r["value_cents"] for r in selected if r["quantity_milli"] == 0)
    require(closing == {"quantity_milli": stock["balances"][0]["quantity_milli"], "value_cents": stock["balances"][0]["value_cents"]}
        == {"quantity_milli": item["quantity_milli"], "value_cents": item["inventory_value_cents"]}
        and closing["quantity_milli"] == opening["quantity_milli"] + incoming["quantity_milli"] - outgoing["quantity_milli"]
        and closing["value_cents"] == opening["value_cents"] + incoming["value_cents"] + outgoing["value_cents"] + revalue,
        "原期初/期间收发/期末或门店与库位整数账不守恒")
    complete = date.fromisoformat(first) > stamp_day(sources["activation_event"]["occurred_at"])
    issue = [] if complete else ["请求期初不晚于启用日，午夜期初及启用前收发未知"]
    bridge = utc_z(sources["activation_event"]["occurred_at"])
    balance = stock["balances"][0]
    row = {"item_id": item["id"], "store_id": store["id"], "sku": item["sku"], "name": item["name"], "unit": item["unit"],
        "balance_id": balance["id"], "warehouse_id": warehouse["id"], "warehouse": warehouse["name"], "location": location["name"],
        "transit_case_id": None, "period_complete": complete, "closing_complete": True, "coverage_start": bridge, "issues": issue,
        "opening": opening if complete else None, "in": incoming if complete else None, "out": outgoing if complete else None,
        "closing": closing, "revaluation_cents": revalue if complete else None,
        "known_in_milli": incoming["quantity_milli"], "known_out_milli": outgoing["quantity_milli"],
        "known_value_delta_cents": sum(r["value_cents"] for r in selected)}
    baseline = {"item_id": item["id"], "store_id": store["id"], "balance_id": balance["id"], "sku": item["sku"], "unit": item["unit"],
        "warehouse": warehouse["name"], "location": location["name"], "quantity_milli": 0, "value_cents": 0, "coverage_start": bridge, "case_id": enrollment["case_id"]}
    details = [{"item_id": item["id"], "store_id": store["id"], "balance_id": balance["id"], "sku": item["sku"], "name": item["name"],
        "unit": item["unit"], "warehouse": warehouse["name"], "location": location["name"], "source_id": r["id"], "case_id": r["case_id"],
        "stock_move_id": r["stock_move_id"], "date": r["business_date"], "quantity_milli": r["quantity_milli"], "value_cents": r["value_cents"],
        "label": REASONS[r["reason"]], "is_baseline": False} for r in selected]
    require(data["rows"] == [row] and data["baselines"] == [baseline] and data["details"] == details
        and data["complete"] is complete and data["closing_complete"] is True and data["can_money"] is True
        and data["metrics"] == {"warehouse_period_complete": complete, "warehouse_period_closing_complete": True,
            "warehouse_period_gap_count": 0 if complete else 1}, "原 API 全期间/来源覆盖/逐条流水不是独立整数 oracle")
    totals = [store["name"], item["sku"], item["name"], item["unit"], warehouse["name"], location["name"]]
    totals += [qty(r["quantity_milli"]) if r is not None else "—" for r in (row["opening"], row["in"], row["out"], closing)]
    totals += [yuan(r["value_cents"]) if r is not None else "—" for r in (row["opening"], row["in"], row["out"])]
    totals += [yuan(revalue) if complete else "—", yuan(closing["value_cents"]), "完整" if complete else "有覆盖缺口", "完整", "；".join(issue)]
    tables = data["tables"]
    require(set(tables) == set(TABLE_KEYS), "原三张完整表集合错误")
    require(all(tables[key]["headers"] == TABLE_HEADERS[key] for key in TABLE_KEYS), "原三张表字段合同被删减或改写")
    require(tables[TABLE_KEYS[0]]["rows"] == [{"values": totals, "item_id": item["id"],
        "closing_quantity_milli": closing["quantity_milli"], "closing_value_cents": closing["value_cents"]}], "原期间表整数和空值口径错误")
    require(tables[TABLE_KEYS[1]]["rows"] == [{"values": [store["name"], item["sku"], item["unit"], warehouse["name"], location["name"], bridge, "0", "0.00"],
        "route": {"type": "case", "id": enrollment["case_id"]}}], "原零启用基准不是原批准单或冒充进货")
    wanted = [{"values": [store["name"], r["date"], item["sku"], item["unit"], warehouse["name"], location["name"], r["label"],
        r["source_id"], r["stock_move_id"], qty(r["quantity_milli"]), yuan(r["value_cents"])], "route": {"type": "case", "id": r["case_id"]},
        "quantity_milli": r["quantity_milli"], "amount_cents": r["value_cents"]} for r in details]
    require(tables[TABLE_KEYS[2]]["rows"] == wanted and len(data["charts"]) == 1, "原流水明细/原单/期间图遗漏或重复")
    chart = data["charts"][0]
    require(chart["id"] == "warehouse_period_closing" and chart["unit"] == "cents" and chart["table"] == TABLE_KEYS[0]
        and chart["labels"] == [store["name"] + " · " + warehouse["name"]]
        and chart["series"] == [{"name": "账面价值", "values": [closing["value_cents"]]}], "原期末图与本范围整数账不同源")
    return {"period": period, "period_complete": complete, "opening": opening, "in": incoming, "out": outgoing,
        "closing": closing, "revaluation_cents": revalue, "source_entry_ids": [r["id"] for r in selected],
        "original_stock_move_ids": [r["stock_move_id"] for r in selected], "coverage_start": bridge,
        "opening_stock_entries": stock["opening_stock_entries"], "enrollment": enrollment,
        "all_original_rows_traced": True}


async def filtered_warehouse(e, warehouse, item, period):
    before = e.business_snapshot("before_day_boundary_report_navigation")
    await nav(e, "module/analytics", "统计分析", None)
    await e.fill("#mux-query", "HK-152", "检索本项原需求报表")
    await click(e, e.page.locator('[data-mux-open="wf-report-152"]'), "打开本店原仓库期间报表")
    await expect(e.page).to_have_url(e.origin + "/#warehouse-period")
    await expect(e.page.locator("#datefilters")).to_be_visible()
    await expect(e.page.locator("#main .loading")).to_have_count(0)
    # Original navigation retains its last report filters. Clear them with the
    # visible original control before binding a new exact native request scope.
    selected = [await e.page.locator('#warehouse-report-filters [name="' + name + '"]').input_value()
        for name in ("item_id", "warehouse_id")]
    if any(selected):
        async with e.page.expect_response(lambda r: r.request.method == "GET"
            and urlsplit(r.url).path == "/api/inventory-reports/warehouses") as cleared:
            await click(e, e.page.locator('[data-act="warehouse-report-clear"]'), "原 UI 明确清除前次报表筛选")
        response = await cleared.value
        require(response.status == 200, "原清除筛选 GET 失败")
        await expect(e.page.locator("#main .loading")).to_have_count(0)
        await expect(e.page.locator('#warehouse-report-filters [name="item_id"]')).to_have_value("")
        await expect(e.page.locator('#warehouse-report-filters [name="warehouse_id"]')).to_have_value("")
    for name, value in period.items():
        await e.fill('#datefilters [name="' + name + '"]', value, "明确原来源实际期间")
    async with e.page.expect_response(lambda r: r.request.method == "GET"
        and urlsplit(r.url).path == "/api/inventory-reports/warehouses") as queried:
        await click(e, e.page.locator('#datefilters button[type="submit"]'), "本人查询本次真实期间")
    response = await queried.value
    data = await response.json()
    entry = await R.read_metadata(e, response, 1, period)
    require(data["date_from"] == period["date_from"] and data["date_to"] == period["date_to"] and data["can_money"] is True,
        "原报表当前期间或岗位金额口径不符")
    await expect(e.page.locator("#main h1")).to_have_text("库位期间入出存")
    await expect(e.page.locator("#main .loading")).to_have_count(0)
    e.business_unchanged(before, "after_day_boundary_report_navigation")
    filters, reads = {}, []
    for name, source, code in (("item_id", item, "sku"), ("warehouse_id", warehouse, "code")):
        filters[name] = source["id"]
        async with e.page.expect_response(lambda r: r.request.method == "GET"
            and urlsplit(r.url).path == "/api/inventory-reports/warehouses") as pending:
            await M.choose(e, e.page.locator("#warehouse-report-filters"), 'select[name="' + name + '"]',
                source[code], source[code] + " · " + source["name"], source["id"])
        response = await pending.value
        data = await response.json()
        reads.append(await R.read_metadata(e, response, 1, {**period, **filters}))
        await expect(e.page.locator("#main .loading")).to_have_count(0)
    require(data["filters"]["item_id"] == item["id"] and data["filters"]["warehouse_id"] == warehouse["id"], "原报表不是显式所选有限来源")
    return data, filters, [entry, *reads]


async def day_boundary_stage(e, context, credentials):
    mirror = fixed_mirror(e.manifest)
    cp, contexts, main_page = Checkpoint(e, "stage"), [], e.page
    first = day()
    try:
        src = C.dependencies(e, cp)
        parent = fixed_dependency(e, cp, C.SCENARIO)
        partial = parent["partial_requirements"][0]["evidence"]
        old = C.one(e, "care_history_grants", parent["report_sources"]["history_grant_id"])
        require(old == partial["revoke"] and old["status"] == "revoked" and old["active_pair"] is None,
            "旧 share_partial 授权没有真实撤销，不能伪称它会自然过期")
        receiver_vehicle = C.one(e, "care_customer_vehicles", parent["report_sources"]["receiver_customer_vehicle_id"])
        require(receiver_vehicle["id"] == old["to_vehicle_id"] and receiver_vehicle["store_id"] == 2
            and receiver_vehicle["vehicle_identity_id"] == src["delivered_cv"]["vehicle_identity_id"], "两店明确同车关系变更")
        _, _ = await C.login(e, context, credentials, src["fixture"]["sales_key"], "customer-vehicles/" + str(src["delivered_cv"]["id"]),
            "客户车辆 · " + (src["delivered_cv"]["plate"] or src["delivered_cv"]["vin"]), C.CARE + "/vehicles/" + str(src["delivered_cv"]["id"]))
        original, source_read = await native_history(e, src["delivered_cv"]["id"], 1)
        require(original["items"] and all(not r["external"] for r in original["items"]), "D 日原店非空本地服务摘要缺失")
        _, receiver_page, receiver_login = await C.receiver_login(e, context, contexts, src)
        without, without_read = await native_history(e, receiver_vehicle["id"], 2)
        require(not any(r["external"] for r in without["items"]), "新授权前二店已有未核准外部摘要")
        e.page = main_page
        manager, _ = await C.login(e, context, credentials, src["fixture"]["manager_key"],
            "customer-history-grants", "跨店服务历史授权", C.CARE + "/history/grants")
        await C.form(e, '#main [data-act="care-grant-new"]', "登记跨店服务历史授权")
        values = {"from_vehicle_id": src["delivered_cv"]["id"], "to_store_id": 2, "to_vehicle_id": receiver_vehicle["id"],
            "valid_until": first.isoformat(), "source_reference": "本次隔离合成客户明确同意仅到实际上海今日的两店同车服务摘要 " + uuid.uuid4().hex[:10],
            "confirmed": True}
        await fields(e, values)
        guard = C.Guard(e, "natural_boundary_new_active_grant", manager, 1,
            appends={"care_history_grants": 1, "care_receipts": 1, "audit_logs": 1})
        body, request, _, grant_native = await C.submit(e, manager, 1, C.CARE + "/history/grants", guard, status=201,
            render=C.CARE + "/history/grants", action="grant_history", payload=lambda r: r["values"])
        grant = C.one(e, "care_history_grants", body["grant"]["id"])
        require(request["values"] == values and grant["id"] != old["id"] and grant["status"] == "active"
            and grant["valid_until"] == first.isoformat() and grant["active_pair"] == f'{values["from_vehicle_id"]}:{values["to_vehicle_id"]}',
            "D 日新 active 授权未绑定原范围/真实日期")
        e.page = receiver_page
        shared, shared_read = await native_history(e, receiver_vehicle["id"], 2)
        external = [{k: v for k, v in r.items() if k != "case_id"} | {"external": True} for r in original["items"]]
        require(shared["items"] == without["items"] + external and all(set(r) == {"number", "kind", "business_date", "completed_date", "state", "summary", "store_name", "external"} for r in external),
            "D 日服务摘要未真实共享或泄漏原单/金额/附件")
        await expect(e.page.locator("#main")).to_contain_text("已授权跨店摘要")
        e.page = main_page
        fixture, warehouse, location, _, _ = W.source_dependencies(e, cp)
        token = uuid.uuid4().hex[:10].upper()
        item, item_native = await W.new_item(e, context, credentials, fixture, token, "consumable", "包")
        case_id, created = await W.create_warehouse(e, context, credentials, fixture, item["id"], location,
            "activate", 0, warehouse=warehouse, token=token)
        approved = await W.warehouse_command(e, context, credentials, fixture, case_id, item["id"], "approve", token)
        zero = await W.stock_read(e, context, credentials, fixture, item["id"], 0, 0)
        incoming = await W.operate(e, context, credentials, fixture, item["id"], location, warehouse, "other_in", 5000, 2000, token)
        sources = warehouse_sources(e, item["id"])
        require(stamp_day(sources["activation_event"]["occurred_at"]) == first
            and sources["stock_moves"] == [incoming["db"]["stock_move"]]
            and incoming["db"]["stock_move"]["business_date"] == first.isoformat(), "stage 没有 D 日真实启用与非零原流水")
        actor = await R.login_current(e, context, credentials, fixture["manager_key"], 1)
        store = C.one(e, "stores", 1)
        period = {"date_from": first.isoformat(), "date_to": first.isoformat()}
        data, _, native_filters = await filtered_warehouse(e, warehouse, item, period)
        same_day = warehouse_oracle(e, data, sources, warehouse, location, store, period, sources["stock_moves"])
        require(same_day["period_complete"] is False, "D 当日真实启用被写成完整午夜历史")
        pointers = [r["value"] for r in json.loads((Path(e.manifest["evidence_root"]) / C.SYSTEM / "observations.json").read_text(encoding="utf-8"))
            if r["label"] == "synthetic_system_private_credentials"]
        require(len(pointers) == 1, "同轮接收员工私有凭据引用不唯一")
        _, _, private_ref = receiver_credentials(e, pointers[0]["path"])
        require(day() == first and C.one(e, "care_history_grants", grant["id"]) == grant, "stage 跨过真实 D 日或新授权被改动，停止封存")
        suite_path = Path(e.manifest["evidence_root"]) / "browser-click-report.json"
        envelope = {"schema": 1, "phase": "stage", "stage_complete": True, "natural_boundary_verified": False,
            "stage_date": first.isoformat(), "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "binding": {k: e.manifest[k] for k in BINDING}, "mirror": mirror,
            "original_suite_report": {"path": str(suite_path), "sha256": sha(suite_path)},
            "original_prerequisite_checkpoints": cp.report["dependencies"],
            "grant": grant, "old_revoked_grant": old, "source_vehicle": src["delivered_cv"], "receiver_vehicle": receiver_vehicle,
            "source_original_history": original, "receiver_local_history": without, "d_actual_shared_history": shared,
            "receiver": src["receiver"], "receiver_private_credentials": private_ref, "receiver_current_store_roles": e.db.rows("SELECT store_id,role FROM user_stores WHERE user_id=? ORDER BY store_id", (src["receiver"]["id"],)),
            "sales_fixture": src["fixture"], "warehouse_fixture": fixture, "warehouse": sources,
            "warehouse_master": warehouse, "location_master": location, "store": store,
            "stage_business_snapshot": e.business_snapshot("sealed_day_boundary_original_rows"),
            "checks": {"hk099_date_d_valid": True, "hk099_date_d_plus_one": "waiting_real_date",
                "hk152_same_day_unknown_opening": same_day, "hk152_historical_complete": "waiting_real_date"},
            "native_stage": {"source_history": source_read, "receiver_before": without_read, "receiver_login": receiver_login,
                "grant": grant_native, "shared_history": shared_read, "new_item": item_native,
                "activation": {"created": created, "approved": approved, "zero": zero}, "incoming": incoming, "report_filters": native_filters},
            "conditions": {"clock_changed": False, "sql_business_writes": False, "midnight_job_required": False,
                "real_model_calls": 0, "production_acceptance": False, "human_acceptance": "pending"}}
        await e.snapshot("day-boundary-stage-original-period-unknown", business_ready=True)
        write_json(e.directory / STAGE_FILE, envelope)
        cp.note(stage_complete=True, natural_boundary_verified=False, complete=False, passed=False,
            status="waiting_real_shanghai_d_plus_one", stage_checkpoint={"path": str(e.directory / STAGE_FILE), "sha256": sha(e.directory / STAGE_FILE)},
            stage_date=first.isoformat(), next_actual_date=(first + timedelta(days=1)).isoformat())
        e.observe("day_boundary_stage_ready", {"path": str(e.directory / STAGE_FILE), "sha256": sha(e.directory / STAGE_FILE),
            "stage_date": first.isoformat(), "same_day_checks_complete": True, "natural_boundary_verified": False})
    except BaseException as error:
        cp.failed(error)
        raise
    finally:
        e.page = main_page
        if e.response_jobs:
            await asyncio.gather(*list(e.response_jobs))
        for separate in contexts:
            await separate.close()


async def day_boundary_verify(e, context, credentials):
    stage, reference = resume_checkpoint(e.manifest)
    cp, contexts, main_page = Checkpoint(e, "verify"), [], e.page
    try:
        cp.note(stage_checkpoint=reference, mirror=stage["mirror"])
        require(e.db.business_snapshot() == stage["stage_business_snapshot"], "跨日停服务/重启期间原业务事实变化，不能继承 stage 原件")
        require(C.one(e, "care_history_grants", stage["grant"]["id"]) == stage["grant"]
            and C.one(e, "care_history_grants", stage["old_revoked_grant"]["id"]) == stage["old_revoked_grant"], "跨日授权物理行被改写或旧撤销原件恢复")
        require(warehouse_sources(e, stage["warehouse"]["item"]["id"]) == stage["warehouse"], "跨日仓库原来源被改写")
        private, password, _ = receiver_credentials(e, stage["receiver_private_credentials"]["path"], stage["receiver_private_credentials"]["sha256"])
        require(private["id"] == stage["receiver"]["id"] and private["username"] == stage["receiver"]["username"]
            and e.db.rows("SELECT store_id,role FROM user_stores WHERE user_id=? ORDER BY store_id", (private["id"],)) == stage["receiver_current_store_roles"],
            "接收员工身份/当前店岗位不是 stage 同一授权")
        receiver_src = {"receiver": stage["receiver"], "password": password}
        _, receiver_page, receiver_login = await C.receiver_login(e, context, contexts, receiver_src)
        expired, expired_read = await native_history(e, stage["receiver_vehicle"]["id"], 2)
        require(expired == stage["receiver_local_history"] and all(not r["external"] for r in expired["items"]),
            "上海 D+1 原 GET 仍暴露截止 D 日外部摘要或删掉本地摘要")
        await expect(e.page.locator("#main")).not_to_contain_text("已授权跨店摘要")
        await e.snapshot("hk099-original-get-actual-date-expired", business_ready=True)
        e.page = main_page
        manager, listing = await C.login(e, context, credentials, stage["sales_fixture"]["manager_key"],
            "customer-history-grants", "跨店服务历史授权", C.CARE + "/history/grants")
        shown = next((r for r in listing["items"] if r["id"] == stage["grant"]["id"]), None)
        require(shown is not None and shown["status"] == "active" and shown["valid_until"] == stage["stage_date"], "原授权列表物理状态/截止日失真")
        await expect(e.page.locator('#main tr').filter(has=e.page.locator(f'[data-act="care-grant-revoke"][data-id="{stage["grant"]["id"]}"]'))).to_contain_text("已过期")
        await e.snapshot("hk099-ui-expired-db-active-retained", business_ready=True)
        source_after, source_read = await native_history(e, stage["source_vehicle"]["id"], 1)
        require(source_after == stage["source_original_history"] and C.one(e, "care_history_grants", stage["grant"]["id"]) == stage["grant"],
            "自然截止修改了原店摘要或授权物理整行")
        cp.note(hk099={"status": "passed", "actual_verify_date": day().isoformat(), "native_expired_read": expired_read,
            "receiver_native_login": receiver_login, "expired_history": expired, "source_read": source_read,
            "grant_physical_whole_row_unchanged": True, "grant_status_still_active": True,
            "original_local_history_unchanged": True, "new_date_native_get_excludes_external": True})
        fixture, warehouse, location = stage["warehouse_fixture"], stage["warehouse_master"], stage["location_master"]
        actor = await R.login_current(e, context, credentials, fixture["manager_key"], 1)
        current = day().isoformat()
        period = {"date_from": current, "date_to": current}
        data, _, before_filters = await filtered_warehouse(e, warehouse, stage["warehouse"]["item"], period)
        historical_opening = warehouse_oracle(e, data, stage["warehouse"], warehouse, location, stage["store"], period, stage["warehouse"]["stock_moves"])
        require(historical_opening["period_complete"] is True and historical_opening["opening"] == {"quantity_milli": 5000, "value_cents": 2000}
            and historical_opening["in"] == historical_opening["out"] == {"quantity_milli": 0, "value_cents": 0},
            "D+1 真实历史流水未重建非零午夜期初，不能以当日空报表求通过")
        token = uuid.uuid4().hex[:10].upper()
        item_id = stage["warehouse"]["item"]["id"]
        new_in = await W.operate(e, context, credentials, fixture, item_id, location, warehouse, "other_in", 1000, 400, token)
        consumed = await W.operate(e, context, credentials, fixture, item_id, location, warehouse, "consumable", 500, -200, token)
        returned = await W.operate(e, context, credentials, fixture, item_id, location, warehouse,
            "consumable_return", 125, 50, token, original=consumed["db"]["stock_move"])
        later = [r["db"]["stock_move"] for r in (new_in, consumed, returned)]
        require(all(r["business_date"] == current for r in later) and day().isoformat() == current
            and returned["db"]["stock_move"]["original_id"] == consumed["db"]["stock_move"]["id"], "D+1 原收发日期或原领用退回关联失真")
        actor = await R.login_current(e, context, credentials, fixture["manager_key"], 1)
        data, filters, native_filters = await filtered_warehouse(e, warehouse, stage["warehouse"]["item"], period)
        expected_moves = stage["warehouse"]["stock_moves"] + later
        result = warehouse_oracle(e, data, stage["warehouse"], warehouse, location, stage["store"], period, expected_moves)
        require(result["period_complete"] is True and result["in"] == {"quantity_milli": 1125, "value_cents": 450}
            and result["out"] == {"quantity_milli": 500, "value_cents": -200}
            and result["closing"] == {"quantity_milli": 5625, "value_cents": 2250}, "完整期间整数 oracle 未含非零原入出及原单退回")
        await expect(e.page.locator("#main .notice.error")).to_have_count(0)
        await expect(e.page.locator("#main")).to_contain_text("全期间来源：完整")
        tables, exports = [], []
        for key in TABLE_KEYS:
            tables.append(await verify_table(e, data, key, "warehouses"))
            exports.append(await R.export(e, 1, actor, data, "warehouses", key, period, filters=filters))
        graphic = await graph(e, data, "warehouse_period_closing")
        await e.snapshot("hk152-actual-historical-complete-period", business_ready=True)
        drills = []
        for key in (TABLE_KEYS[1], TABLE_KEYS[2]):
            originals = list(data["tables"][key]["rows"])
            for row in originals:
                case = W.one(e, "flow_cases", row["route"]["id"])
                drills.append(await drill_original(e, data, key, row, "warehouses", case))
                data, _, _ = await filtered_warehouse(e, warehouse, stage["warehouse"]["item"], period)
                warehouse_oracle(e, data, stage["warehouse"], warehouse, location, stage["store"], period, expected_moves)
        original_window = {"date_from": stage["stage_date"], "date_to": current}
        combined, _, original_filters = await filtered_warehouse(e, warehouse, stage["warehouse"]["item"], original_window)
        old_period = warehouse_oracle(e, combined, stage["warehouse"], warehouse, location, stage["store"], original_window, expected_moves)
        require(old_period["period_complete"] is False and combined["rows"][0]["opening"] is None, "后日完整不能篡改启用当日原未知历史")
        require(C.one(e, "care_history_grants", stage["grant"]["id"]) == stage["grant"] and day().isoformat() == current,
            "verify 跨日或办理仓储改变摘要授权原件")
        cp.note(hk152={"status": "passed", "actual_historical_opening_before_new_flows": historical_opening,
            "native_before_filters": before_filters, "native_original_d_plus_one_flows": {"in": new_in, "out": consumed, "original_return": returned},
            "independent_integer_oracle": result, "native_same_scope_filters": native_filters,
            "visible_all_tables": tables, "actual_csv_whole_rows": exports, "closing_chart": graphic,
            "original_case_drills": drills, "original_incomplete_window_retained": old_period, "native_original_window_filters": original_filters,
            "all_old_immutable_stock_moves_entries_and_bridge_protected": True,
            "midnight_async_job_required": False, "real_natural_date_crossed": True})
        cp.note(complete=True, passed=True, natural_boundary_verified=True, stage_unchanged_sha256=reference["sha256"],
            requirements=[{"id": "HK-099", "title": "车辆档案", "status": "technical_subrange_passed",
                "business_accepted": False, "subrange": "actual_date_expired_service_summary"},
                {"id": "HK-152", "title": "物资仓库入出存统计", "status": "technical_subrange_passed",
                    "business_accepted": False, "subrange": "actual_historical_complete_period"}])
        require(sha(Path(reference["path"])) == reference["sha256"], "verify 覆盖了 stage 原证据")
        e.observe("day_boundary_two_independent_contracts_verified", {"stage": reference,
            "hk099_actual_date_expiry": True, "hk152_complete_historical_period": True,
            "human_acceptance": "pending", "full193_business_acceptance": False})
    except BaseException as error:
        cp.failed(error)
        raise
    finally:
        e.page = main_page
        if e.response_jobs:
            await asyncio.gather(*list(e.response_jobs))
        for separate in contexts:
            await separate.close()


# The lead registers only the selected phase; registering both in an ordinary
# same-day suite would be an invalid assertion that natural time has elapsed.
DAY_BOUNDARY_STAGE_SCENARIOS = ((STAGE, day_boundary_stage, 1200),)
DAY_BOUNDARY_VERIFY_SCENARIOS = ((VERIFY, day_boundary_verify, 1200),)
