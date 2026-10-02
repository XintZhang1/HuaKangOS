"""Eleven original reports, backed by this run's native business checkpoints.

No app imports, business setup, direct HTTP requests or injected browser state.
The shared Evidence owns the real page and SELECT-only external database. CSV
downloads may append exactly their original export audit; all old rows remain.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import SCENARIO as PRESALES_SCENARIO, login_as, require
from vehicle_purchase_business import SCENARIO as PURCHASE_SCENARIO, nav


SCENARIO = "reports-hk134-135-137-138-142-143-144-145-160-167-136"
# The known quote-conversion diagnostic runs last. Earlier evidence never turns
# an incomplete eleven-check scene into a successful scene.
CONTRACTS = (
    ("HK-134", "展厅接待分析", "table/leads", ("leads",)),
    ("HK-135", "意向客户分析", "table/leads", ("leads",)),
    ("HK-137", "销售订单统计", "table/orders", ("orders",)),
    ("HK-138", "销售单统计", "table/deliveries", ("deliveries",)),
    ("HK-142", "整车销售毛利统计", "table/deliveries", ("deliveries",)),
    ("HK-143", "整车入库历史统计", "vehicle-period", ("vehicle_period_movements",)),
    ("HK-144", "整车出库历史统计", "vehicle-period", ("vehicle_period_movements",)),
    ("HK-145", "整车仓库入出存统计", "vehicle-period", ("vehicle_period_balances", "vehicle_period_transit")),
    ("HK-160", "收款统计", "table/cash", ("cash",)),
    ("HK-167", "客户价值分析统计", "table/customer_value", ("customer_value", "customer_value_details")),
    ("HK-136", "售前跟进分析", "visit-activity", ("presales_activity", "presales_transitions",
        "presales_stage_durations", "presales_open_stages", "presales_stage_summary")),
)
ZONE = ZoneInfo("Asia/Shanghai")  # The isolated fixture does not inherit APP_TIMEZONE.


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def yuan(value):
    return "—" if value is None else format(Decimal(value) / 100, ".2f")


def text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def local_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(ZONE)


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        source = Path(__file__).with_name("business_acceptance_catalog.json")
        catalog = json.loads(source.read_text(encoding="utf-8"))
        bindings = {row["id"]: row for row in catalog["requirements"]}
        for key, title, route, _ in CONTRACTS:
            row = bindings[key]
            require(row["title"] == title and route in row["target_routes"]
                and row["source_review_status"] == "source_reviewed", key + " 原源合同不匹配")
            require(any(c["check_id"] == key + "-business" for c in row["acceptance_checks"]), key + " 原 check_id 缺失")
        self.report = {
            "schema": 1, "scenario": SCENARIO, "scope": [c[0] for c in CONTRACTS],
            "complete": False, "passed": False, "business_accepted": False,
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "source_contract_sha256": sha(source), "execution": "native_browser_original_reports",
            "manual_review": {"simple_flow": "pending", "concise_copy": "pending"},
            "conditions": {"production_money_or_handover_acceptance": False,
                "all_36_reports": "not_tested", "group_scope": "not_tested",
                "other_historical_periods": "not_tested", "nonempty_transit": "not_tested"},
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"check_id": key + "-business", "status": "not_tested", "evidence": {}}]}
                for key, title, _, _ in CONTRACTS],
        }
        self.save()

    def save(self):
        write_json(self.path, self.report)

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active["status"] = "running"
        self.active["acceptance_checks"][0]["status"] = "running"
        self.active["evidence_action_start"] = len(self.e.actions)
        self.save()

    def record(self, evidence):
        self.active["acceptance_checks"][0]["evidence"].update(evidence)
        self.save()

    async def passed(self, evidence):
        self.record(evidence)
        await self.e.snapshot(self.active["id"].lower() + "-report", business_ready=True)
        self.active["status"] = "passed"
        self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.save()

    def failed(self, error):
        if self.active is not None:
            self.active["status"] = "failed"
            self.active["acceptance_checks"][0].update(status="failed", error=self.e.scrub(error))
        self.report["error"] = self.e.scrub(error)
        self.report["executed_requirements"] = sum(r["status"] != "not_tested" for r in self.report["requirements"])
        self.report["passed_requirements"] = sum(r["status"] == "passed" for r in self.report["requirements"])
        self.save()

    def finish(self):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "11项报表未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=11, passed_requirements=11)
        self.save()
        self.e.observe("report_business_checkpoint", {"path": str(self.path), "requirements": 11, "passed": 11})


def passed_checkpoint(e, name):
    require(name and Path(name).name == name, "前序场景名必须明确且不可跨目录")
    root = Path(e.manifest["evidence_root"]).resolve()
    path = root / name / "business-checkpoint.json"
    require(path.resolve().is_relative_to(root) and path.is_file(), "缺少本轮前序业务 checkpoint：" + name)
    report = json.loads(path.read_text(encoding="utf-8"))
    require(report.get("scenario") == name and report.get("complete") is True and report.get("passed") is True,
        "本轮前序业务不完整：" + name)
    require(report.get("requirements") and all(r["status"] == "passed" and r.get("acceptance_checks")
        and all(c["status"] == "passed" for c in r["acceptance_checks"]) for r in report["requirements"]),
        "前序缺少逐项实际通过：" + name)
    return report, {"path": str(path), "sha256": sha(path), "scenario": name}


def check_evidence(report, key):
    selected = [r for r in report["requirements"] if r["id"] == key]
    require(len(selected) == 1 and len(selected[0]["acceptance_checks"]) == 1, "前序业务证据不唯一：" + key)
    return selected[0]["acceptance_checks"][0]["evidence"]


def one(e, table, key):
    require(table in {"flow_cases", "flow_customers", "vehicles", "cash_entries"}, "原来源表超出本场景")
    rows = e.db.rows(f"SELECT * FROM {table} WHERE id=?", (key,))
    require(len(rows) == 1, "本轮明确原来源缺失：" + table)
    return rows[0]


def source_facts(e, checkpoint):
    # A lazily imported sibling only declares native scenario code, never app.
    from sales_order_business import SCENARIO as SALES_SCENARIO, CANCELLATION_SCENARIO

    require(e.manifest.get("synthetic_data_only") is True, "只允许本轮外置合成实例")
    evidence_root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(evidence_root.parent / "runtime"),
        "报表数据库不是本轮外置 runtime")
    provenance_path = evidence_root / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    require(provenance.get("snapshot_stable") is True, "来源镜像未完整冻结")
    for name in ("report_business.py", "business_acceptance_catalog.json", "sales_business.py",
                 "vehicle_purchase_business.py", "sales_order_business.py"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name)), "同次脚本指纹变化：" + name)
    presales, presales_ref = passed_checkpoint(e, PRESALES_SCENARIO)
    purchase, purchase_ref = passed_checkpoint(e, PURCHASE_SCENARIO)
    sale, sale_ref = passed_checkpoint(e, SALES_SCENARIO)
    cancellation, cancellation_ref = passed_checkpoint(e, CANCELLATION_SCENARIO)
    delivery_refs = sale.get("report_sources", {})
    cancellation_refs = cancellation.get("report_sources", {})
    common_keys = {"lead_id", "customer_id", "delivered_order_id", "delivered_vehicle_id"}
    require(common_keys <= delivery_refs.keys() and common_keys <= cancellation_refs.keys()
        and all(delivery_refs[k] == cancellation_refs[k] for k in common_keys), "销售与退订没有承接同轮同一交付来源")
    refs = {**delivery_refs, **cancellation_refs}
    expected_keys = {"lead_id", "customer_id", "delivered_order_id", "cancelled_order_id", "delivered_vehicle_id"}
    require(expected_keys <= refs.keys() and all(type(refs[k]) is int and refs[k] > 0 for k in expected_keys),
        "销售原 checkpoint 缺少明确报表来源ID，不从旧成交或全库猜选")
    before_lead = check_evidence(presales, "HK-007")["db"]
    require(refs["lead_id"] == before_lead["case"]["id"] and refs["customer_id"] == before_lead["customer"]["id"],
        "销售没有承接本轮售前客户与原单")
    lead = one(e, "flow_cases", refs["lead_id"])
    customer = one(e, "flow_customers", refs["customer_id"])
    delivered = one(e, "flow_cases", refs["delivered_order_id"])
    cancelled = one(e, "flow_cases", refs["cancelled_order_id"])
    require(delivered["id"] != cancelled["id"] and lead["kind"] == "lead" and lead["state"] == "converted"
        and delivered["kind"] == cancelled["kind"] == "order" and delivered["state"] == "delivered"
        and delivered["completed_date"] and cancelled["state"] == "cancelled", "本轮真实接待/交付/退订事实不齐")
    require(delivered["parent_id"] == lead["id"] and delivered["vehicle_id"] == refs["delivered_vehicle_id"]
        and lead["customer_id"] == delivered["customer_id"] == cancelled["customer_id"] == customer["id"], "报表原业务链串单")
    require(all(r["store_id"] == 1 for r in (lead, customer, delivered, cancelled))
        and delivered["created_by"] == cancelled["created_by"] == e.manifest["users"]["sales_peer"]["id"],
        "报表原店或原业务创建身份不匹配")
    origin = check_evidence(purchase, "HK-021")
    purchase_case = one(e, "flow_cases", origin["case_id"])
    receipts = e.db.rows("SELECT * FROM vehicle_purchase_receipts WHERE case_id=? ORDER BY id", (purchase_case["id"],))
    movements = e.db.rows("SELECT * FROM vehicle_purchase_movements WHERE case_id=? ORDER BY id", (purchase_case["id"],))
    vehicle_ids = [r["vehicle"]["id"] for r in origin["vehicles"]]
    require(purchase_case["store_id"] == 1 and purchase_case["state"] == "completed" and len(vehicle_ids) == 2
        and len(set(vehicle_ids)) == 2 and {r["vehicle_id"] for r in receipts} == set(vehicle_ids)
        and len(receipts) == len(movements) == 2 and delivered["vehicle_id"] in vehicle_ids, "本轮两台原采购来源不完整")
    cars = [one(e, "vehicles", key) for key in vehicle_ids]
    require(len({r["vin"] for r in cars}) == 2 and all(r["store_id"] == 1 and r["inventory_generation"] > 0 for r in cars),
        "本轮VIN与代次来源不唯一")
    links = e.db.rows("SELECT * FROM flow_payment_links WHERE case_id IN (?,?) ORDER BY id", (delivered["id"], cancelled["id"]))
    require(links and len({r["cash_id"] for r in links}) == len(links), "销售现金来源缺失或重复")
    signed = lambda case_id: sum(r["amount_cents"] * (1 if r["direction"] == "in" else -1) for r in links if r["case_id"] == case_id)
    require(signed(delivered["id"]) == delivered["amount_cents"] and signed(cancelled["id"]) == 0
        and any(r["case_id"] == cancelled["id"] and r["direction"] == "out" and r["original_id"] for r in links),
        "本轮实收/原款退款未完整留事实")
    cash_ids = [r["cash_id"] for r in links] + [origin["cash"]["id"]]
    cash = [one(e, "cash_entries", key) for key in cash_ids]
    require(len(set(cash_ids)) == len(cash_ids) and all(r["store_id"] == 1 and r["approval_state"] == "approved" for r in cash),
        "本轮独立采购及销售款混源或未生效")
    events = e.db.rows("SELECT * FROM flow_events WHERE case_id IN (?,?) ORDER BY occurred_at,id", (lead["id"], delivered["id"]))
    for event in events:
        event["detail"] = json.loads(event["detail"])
    dates = [r["business_date"] for r in (lead, delivered, cancelled, purchase_case)] + [delivered["completed_date"]]
    dates += [r["business_date"] for r in receipts + cash] + [local_time(r["occurred_at"]).date().isoformat() for r in events]
    period = {"date_from": min(dates), "date_to": max(dates)}
    require(period["date_to"] <= datetime.now(ZONE).date().isoformat(), "同次原来源包含未来发生事实")
    result = {"lead": lead, "customer": customer, "delivered": delivered, "cancelled": cancelled,
        "purchase_case": purchase_case, "receipts": receipts, "movements": movements, "cars": cars,
        "payment_links": links, "cash": cash, "events": events, "period": period}
    write_json(e.directory / "same-run-source-facts.json", result)
    checkpoint.report["prerequisite_checkpoints"] = [presales_ref, purchase_ref, sale_ref, cancellation_ref]
    checkpoint.report["provenance"] = {"path": str(provenance_path), "sha256": sha(provenance_path),
        "source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"]}
    checkpoint.report["source_ids"] = refs
    checkpoint.save()
    return result


async def click(e, locator, label):
    await expect(locator).to_have_count(1)
    await expect(locator).to_be_visible()
    await expect(locator).to_be_enabled()
    e.action("click", label)
    await locator.click()


async def native_response(e, response, parameters):
    require(response.request.method == "GET" and response.status == 200, "原报表读取或导出失败")
    headers = await response.request.all_headers()
    require(bool(headers.get("cookie")) and headers.get("x-store-id") == "1", "报表缺原生Cookie或实际本店身份")
    parsed = urlsplit(response.url)
    query = parse_qs(parsed.query)
    require(query == {key: [str(value)] for key, value in parameters.items()}, "原UI报表范围与实际请求不一致")
    metadata = {"path": parsed.path, "query": query, "method": "GET", "status": 200,
        "native_ui": True, "cookie_present": True, "store_id": 1}
    e.observe("original_report_http", metadata)
    return metadata


async def refresh_report(e, path, period, extra=None):
    before = e.business_snapshot("before_original_report_filter")
    await e.fill('#datefilters [name="date_from"]', period["date_from"], "实际来源开始日期")
    await e.fill('#datefilters [name="date_to"]', period["date_to"], "实际来源结束日期")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        await click(e, e.page.locator('#datefilters button[type="submit"]'), "更新原报表期间")
    response = await pending.value
    data = await response.json()
    await native_response(e, response, {**period, **(extra or {})})
    require(data["date_from"] == period["date_from"] and data["date_to"] == period["date_to"], "服务器报表期间错配")
    await expect(e.page.locator("#main .loading")).to_have_count(0)
    e.business_unchanged(before, "after_original_report_filter")
    return data


async def open_report(e, key, route, period):
    before = e.business_snapshot("before_original_report_navigation")
    await nav(e, "module/analytics", "统计分析", None)
    await e.fill("#mux-query", key, "检索明确原报表需求")
    button = e.page.locator('[data-mux-open="wf-report-' + key.split("-")[1] + '"]')
    await click(e, button, "打开" + key + "原报表入口")
    await expect(e.page).to_have_url(re.compile(r"#" + re.escape(route) + r"$"))
    await expect(e.page.locator("#datefilters")).to_be_visible()
    path = "/api/visit-activity-reports" if route == "visit-activity" else "/api/inventory-reports/vehicles" if route == "vehicle-period" else "/api/flow/analytics"
    data = await refresh_report(e, path, period)
    title = "跟进与进出厂统计" if route == "visit-activity" else "整车期间入出存" if route == "vehicle-period" else data["tables"][route.split("/")[1]]["title"]
    await expect(e.page.locator("#main h1")).to_have_text(title)
    await expect(e.page.locator("#store")).to_have_value("1")
    e.business_unchanged(before, "after_original_report_navigation")
    return data


def original_rows(data, key, case_id):
    return [r for r in data["tables"][key]["rows"] if r.get("route") == {"type": "case", "id": case_id}]


def unique_original(data, key, case_id):
    rows = original_rows(data, key, case_id)
    require(len(rows) == 1, key + "未呈现唯一的本轮原单")
    return rows[0]


def panel(e, data, key, family):
    if family == "flow":
        return e.page.locator("#main > section.panel")
    return e.page.locator("#main > section.panel").filter(has=e.page.get_by_role("heading", name=data["tables"][key]["title"], exact=True)).filter(has=e.page.locator(".work-table"))


async def first_page(e, target):
    previous = target.locator('[data-act="page"]').get_by_text("上一页", exact=True)
    while await previous.count() and await previous.is_enabled():
        caption = await target.locator(".pagination span").inner_text()
        current = int(re.search(r"第 (\d+) 页", caption).group(1))
        await click(e, previous, "原明细回到上一页")
        await expect(target.locator(".pagination span")).to_contain_text("第 " + str(current - 1) + " 页")


async def verify_table(e, data, key, family):
    before = e.business_snapshot("before_original_report_table_pages")
    source = data["tables"][key]
    target = panel(e, data, key, family)
    await expect(target).to_have_count(1)
    await expect(target).to_be_visible()
    table = target.locator(".work-table table" if family != "flow" else "table")
    if not source["rows"]:
        await expect(target).to_contain_text("暂无")
        await expect(table).to_have_count(0)
        e.business_unchanged(before, "after_original_empty_report_table")
        return {"table": key, "headers": source["headers"], "rows": 0, "empty_original_table": True}
    await expect(table.locator("thead th")).to_have_text(source["headers"] + ["原单"])
    size = 50 if family == "flow" else 25
    # All three original pages use a shared page number. Move via visible
    # controls; do not set state.page or assume API rows were all displayed.
    await first_page(e, target)
    for page_no, start in enumerate(range(0, max(1, len(source["rows"])), size), 1):
        expected_rows = source["rows"][start:start + size]
        if expected_rows:
            rows = table.locator("tbody tr")
            await expect(rows).to_have_count(len(expected_rows))
            for index, expected_row in enumerate(expected_rows):
                await expect(rows.nth(index).locator("td").nth(0)).to_have_text(text(expected_row["values"][0]))
                actual = [v.strip() for v in await rows.nth(index).locator("td").all_text_contents()]
                require(actual[:-1] == [text(v).strip() for v in expected_row["values"]], key + "原明细与API行不一致")
        if start + size < len(source["rows"]):
            await click(e, target.locator('[data-act="page"][data-page="' + str(page_no + 1) + '"]'), "查看原报表下一页")
            await expect(target.locator(".pagination span")).to_contain_text("第 " + str(page_no + 1) + " 页")
    e.business_unchanged(before, "after_original_report_table_pages")
    return {"table": key, "headers": source["headers"], "rows": len(source["rows"]), "all_pages_clicked": True}


def safe_csv(value, family):
    if family == "flow":
        value_text = text(value)
        return "'" + value_text if not isinstance(value, (int, float)) and value_text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value_text
    value_text = str(value)
    numeric = value_text.replace("-", "", 1).replace(".", "", 1).isdigit()
    return "'" + value_text if value_text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) and not numeric else value_text


def assert_export_delta(e, before, old_audit, actor, entity_type, reason):
    after = e.business_snapshot("after_native_csv_export")
    old_tables = {k: v for k, v in before["tables"].items() if k != "audit_logs"}
    new_tables = {k: v for k, v in after["tables"].items() if k != "audit_logs"}
    require(old_tables == new_tables, "报表导出改写了原业务行")
    current = e.db.rows("SELECT * FROM audit_logs ORDER BY id")
    old_by_id = {row["id"]: row for row in old_audit}
    require({row["id"]: row for row in current if row["id"] in old_by_id} == old_by_id, "报表导出覆盖或删除了旧审计")
    added = [row for row in current if row["id"] not in old_by_id]
    require(len(added) == 1, "一次原CSV下载没有唯一新增导出审计")
    audit = added[0]
    require(audit["actor_id"] == actor["id"] and audit["store_id"] == 1 and audit["action"] == "export"
        and audit["entity_type"] == entity_type and audit["entity_id"] is None and audit["reason"] == reason
        and (json.loads(audit["before_data"]) if isinstance(audit["before_data"], str) else audit["before_data"]) is None
        and (json.loads(audit["after_data"]) if isinstance(audit["after_data"], str) else audit["after_data"]) is None,
        "CSV新增审计不是本次原员工原范围")
    return audit


async def export_csv(e, actor, data, key, family, period, *, locator=None, customer_key=None):
    if family == "flow":
        path = "/api/flow/analytics/export"
        parameters = {"dataset": key, **period}
        if customer_key is not None:
            parameters["customer_key"] = customer_key
        locator = locator if locator is not None else e.page.locator('[data-act="exporttable"][data-table="' + key + '"]')
        entity_type, reason = "flow_analytics", "本客户期间已记录业务明细" if customer_key else data["tables"][key]["title"]
    elif family == "vehicles":
        path = "/api/inventory-reports/vehicles/export/" + key
        parameters = period
        locator = locator if locator is not None else panel(e, data, key, family).locator('[data-act="inventory-report-export"][data-key="' + key + '"]')
        entity_type, reason = "vehicles_inventory_report", period["date_from"] + "至" + period["date_to"] + " " + key
    else:
        path = "/api/visit-activity-reports/export/" + key
        parameters = {**period, "case_id": data["filters"]["case_id"]}
        locator = locator if locator is not None else panel(e, data, key, family).locator('[data-act="va-export"][data-key="' + key + '"]')
        entity_type, reason = "visit_activity_report", period["date_from"] + "至" + period["date_to"] + " " + key
    before = e.business_snapshot("before_native_csv_export")
    old_audit = e.db.rows("SELECT * FROM audit_logs ORDER BY id")
    async with e.page.expect_download() as downloaded:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
            await click(e, locator, "下载" + key + "原CSV")
        response = await pending.value
        metadata = await native_response(e, response, parameters)
    download = await downloaded.value
    require(await download.failure() is None, "原生CSV下载失败")
    directory = e.directory / "exports"
    directory.mkdir(exist_ok=True)
    destination = directory / (str(len(list(directory.iterdir())) + 1).zfill(2) + "-" + key + ".csv")
    await download.save_as(destination)
    actual = list(csv.reader(io.StringIO(destination.read_text(encoding="utf-8-sig"), newline="")))
    rows = data["tables"][key]["rows"]
    if customer_key is not None:
        rows = [r for r in rows if r.get("customer_key") == customer_key]
    expected = [data["tables"][key]["headers"]] + [[safe_csv(value, family) for value in row["values"]] for row in rows]
    require(actual == expected, "原CSV不是相同期间/门店/原表全部行")
    audit = assert_export_delta(e, before, old_audit, actor, entity_type, reason)
    result = {"path": str(destination), "sha256": sha(destination), "rows": len(rows),
        "native_http": metadata, "audit": audit, "other_business_rows_unchanged": True, "old_audit_rows_unchanged": True}
    e.observe("original_csv_download", result)
    return result


async def graph(e, data, chart_id):
    charts = [c for c in data["charts"] if c["id"] == chart_id]
    require(len(charts) == 1, "原图表缺失或重复：" + chart_id)
    chart = charts[0]
    target = e.page.locator("#main > section.panel, #main .chartpanel").filter(has=e.page.get_by_role("heading", name=chart["title"], exact=True))
    await expect(target).to_have_count(1)
    await expect(target).to_be_visible()
    nonempty = bool(chart["labels"]) and any(value != 0 for series in chart["series"] for value in series["values"])
    if nonempty:
        svg = target.locator('svg[role="img"]')
        await expect(svg).to_have_count(1)
        require(await svg.get_attribute("aria-label") == chart["title"], "原图可读名称不匹配")
        titles = await svg.locator("rect > title, circle > title").all_text_contents()
        expected_titles = []
        for series in chart["series"]:
            for label, value in zip(chart["labels"], series["values"]):
                shown = format(Decimal(value) / 100, ",.2f") + "元" if chart["unit"] == "cents" else format(Decimal(str(value)), ",.3f").rstrip("0").rstrip(".")
                expected_titles.append(str(label) + "：" + series["name"] + " " + shown)
        require(titles == expected_titles, "原SVG数值与实际图表数据不一致")
    else:
        await expect(target).to_contain_text("当前范围暂无可绘制数据")
    return {"chart": chart_id, "labels": chart["labels"], "series": chart["series"], "table": chart["table"], "svg_rendered": nonempty}


async def flow_chart(e, section, chart_id, data, period):
    before = e.business_snapshot("before_original_report_chart_navigation")
    await click(e, e.page.locator('[data-act="open"][data-route="analytics/overview"]'), "返回原可视化")
    await expect(e.page.locator("#main h1")).to_have_text("数据可视化")
    await click(e, e.page.locator('.tabs a[href="#analytics/' + section + '"]'), "查看原统计图表分类")
    await expect(e.page).to_have_url(re.compile(r"#analytics/" + section + r"$"))
    await expect(e.page.locator('#datefilters [name="date_from"]')).to_have_value(period["date_from"])
    result = await graph(e, data, chart_id)
    e.business_unchanged(before, "after_original_report_chart_navigation")
    return result


async def finance_chart_groups(e, data):
    """Native disclosure keeps empty finance sources available without a long page."""
    charts = [c for c in data["charts"] if c["section"] == "finance"]
    empty_charts = [c for c in charts if not data["tables"][c["table"]]["rows"]
                    and not c["labels"] and all(not s["values"] for s in c["series"])]
    folded = e.page.locator("details.analytics-empty-charts")
    await expect(e.page.locator(".chartpanel")).to_have_count(len(charts))
    await expect(folded).to_have_count(1 if empty_charts else 0)
    rows = []
    for width in (390, 768, 1440):
        e.action("viewport", "财务专项原展示", width=width, height=1000)
        await e.page.set_viewport_size({"width": width, "height": 1000})
        layout = await e.page.evaluate("() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight})")
        require(layout["scrollWidth"] == width, "财务专项撑宽页面")
        visible = await e.page.locator(".chartpanel:visible h2").all_text_contents()
        require(visible == [c["title"] for c in charts if c not in empty_charts], "非空财务来源被折叠或空图仍铺满页面")
        await e.snapshot("finance-nonempty-" + str(width))
        if empty_charts:
            summary = folded.locator(":scope > summary")
            await summary.focus()
            await e.key("details.analytics-empty-charts > summary", "Enter")
            await expect(folded.locator(".chartpanel:visible")).to_have_count(len(empty_charts))
            await expect(folded.locator(".chartpanel h2")).to_have_text([c["title"] for c in empty_charts])
            await e.key("details.analytics-empty-charts > summary", "Space")
            require(await folded.get_attribute("open") is None and await summary.evaluate("x=>x===document.activeElement"), "原生专项收起未保留键盘焦点")
        rows.append(layout)
    result = {"charts": len(charts), "empty_sources": len(empty_charts), "widths": rows,
              "all_original_titles_preserved": True, "native_keyboard_disclosure": bool(empty_charts)}
    e.observe("finance_empty_source_disclosure", result)
    return result


async def drill_original(e, data, key, row, family, case):
    index = data["tables"][key]["rows"].index(row)
    size = 50 if family == "flow" else 25
    target = panel(e, data, key, family)
    desired = index // size + 1
    # The table helper finished at its last page. Navigate back as needed.
    await first_page(e, target)
    for page_no in range(2, desired + 1):
        await click(e, target.locator('[data-act="page"][data-page="' + str(page_no) + '"]'), "翻页定位明确原单")
        await expect(target.locator(".pagination span")).to_contain_text("第 " + str(page_no) + " 页")
    row_ui = target.locator("tbody tr").nth(index % size)
    button = row_ui.locator('[data-act="drill"]' if family == "flow" else '[data-act="open"]')
    before = e.business_snapshot("before_report_original_drill")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/cases/" + str(case["id"])) as pending:
        await click(e, button, "从报表查看明确原单")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["id"] == case["id"] and body["number"] == case["number"], "报表跳转错误原单")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(case["number"])
    e.business_unchanged(before, "after_report_original_drill")
    return {"case_id": case["id"], "case_number": case["number"], "native_get_status": response.status}


async def experience(e):
    buttons = e.page.locator("#main button:visible")
    labels = [(s or "").strip() for s in await buttons.all_text_contents()]
    require(all(label and len(label) <= 30 for label in labels), "报表可见操作按钮为空或过长")
    dimensions = await e.page.evaluate("() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth})")
    require(dimensions["scrollWidth"] <= dimensions["width"] + 1, "报表页面横向溢出")
    return {"heading": await e.page.locator("#main h1").inner_text(), "button_labels": labels,
        "viewport": dimensions, "simple_flow": "manual_pending", "concise_copy": "manual_pending"}


def lead_facts(e, data, facts):
    lead = facts["lead"]
    row = unique_original(data, "leads", lead["id"])
    require(row["values"][:4] == [lead["number"], next(s["name"] for s in e.manifest["stores"] if s["id"] == 1),
        facts["customer"]["name"], lead["business_date"]] and row["values"][5:] == ["是", "是"],
        "本轮原接待、原意向与明确订单后继未正确显示")
    require(any(r["action"] == "intent" and r["case_id"] == lead["id"] for r in facts["events"])
        and facts["delivered"]["parent_id"] == lead["id"], "同批转化没有原事件与原订单父单")
    # The full local population remains part of chart math, but earns no new
    # business credit. Compute cohort membership independently with SELECT.
    cohort = e.db.rows("SELECT id,state FROM flow_cases WHERE store_id=1 AND kind='lead' AND business_date>=? AND business_date<=? ORDER BY id",
        (facts["period"]["date_from"], facts["period"]["date_to"]))
    intended = set()
    converted = set()
    for original in cohort:
        if e.db.rows("SELECT id FROM flow_events WHERE case_id=? AND action IN ('intent','reserve')", (original["id"],)) or original["state"] == "intent":
            intended.add(original["id"])
        if e.db.rows("SELECT id FROM flow_cases WHERE store_id=1 AND kind='order' AND parent_id=?", (original["id"],)):
            converted.add(original["id"])
    intended |= converted
    require(data["metrics"]["cohort_receptions"] == len(cohort) and data["metrics"]["cohort_orders"] == len(converted)
        and data["metrics"]["cohort_rate"] == round(len(converted) / len(cohort) * 100, 2), "接待批次指标与同店原来源不一致")
    chart = next(c for c in data["charts"] if c["id"] == "cohort")
    require(chart["series"][0]["values"] == [len(cohort), len(intended), len(converted)], "同批原接待转化图基数不一致")
    return row, {"same_run_row": row, "source_lead_id": lead["id"], "current_state": lead["state"],
        "ever_intent": True, "order_parent_id": facts["delivered"]["parent_id"],
        "full_scope_cohort_counts": [len(cohort), len(intended), len(converted)]}


def order_facts(e, data, facts):
    rows = []
    for case in (facts["delivered"], facts["cancelled"]):
        row = unique_original(data, "orders", case["id"])
        paid = sum(r["amount_cents"] * (1 if r["direction"] == "in" else -1) for r in facts["payment_links"] if r["case_id"] == case["id"])
        require(row["values"][0] == case["number"] and row["values"][2:4] == [facts["customer"]["name"], case["business_date"]]
            and row["values"][5:] == [yuan(case["amount_cents"]), yuan(paid), yuan(case["cost_cents"])], "本轮订单金额/累计原款/成本错配")
        rows.append(row)
    period = facts["period"]
    scoped = e.db.rows("SELECT id,business_date FROM flow_cases WHERE store_id=1 AND kind='order' AND business_date>=? AND business_date<=? ORDER BY id",
        (period["date_from"], period["date_to"]))
    legacy = e.db.rows("SELECT id,business_date FROM sales WHERE store_id=1 AND approval_state='approved' AND business_date>=? AND business_date<=? ORDER BY id",
        (period["date_from"], period["date_to"]))
    require(data["metrics"]["new_orders"] == len(scoped) + len(legacy) == len(data["tables"]["orders"]["rows"]), "原新增订单数量不一致")
    chart = next(c for c in data["charts"] if c["id"] == "orders_trend")
    require(sum(chart["series"][0]["values"]) == len(scoped) + len(legacy), "新增订单图表遗漏或重复原单")
    return rows[0], {"same_run_rows": rows, "independent_scope_counts": {"current": len(scoped), "legacy": len(legacy)}}


def delivery_facts(e, data, facts):
    case = facts["delivered"]
    row = unique_original(data, "deliveries", case["id"])
    car = next(r for r in facts["cars"] if r["id"] == case["vehicle_id"])
    receipt = next(r for r in facts["receipts"] if r["vehicle_id"] == car["id"])
    require(type(case["cost_cents"]) is int and case["cost_cents"] == car["purchase_cost_cents"] == receipt["value_cents"],
        "本轮实际交付没有明确原采购成本快照")
    require(row["values"][0] == case["number"] and row["values"][2:] == [facts["customer"]["name"], case["completed_date"],
        yuan(case["amount_cents"]), yuan(case["cost_cents"]), yuan(case["amount_cents"] - case["cost_cents"])],
        "交付日、金额及直接毛差没有真实原来源")
    require(not original_rows(data, "deliveries", facts["cancelled"]["id"]), "未履约退订被误计成交")
    period = facts["period"]
    current = e.db.rows("SELECT amount_cents,cost_cents FROM flow_cases WHERE store_id=1 AND kind='order' AND state='delivered' AND completed_date>=? AND completed_date<=?",
        (period["date_from"], period["date_to"]))
    legacy = e.db.rows("SELECT contract_amount_cents,purchase_cost_snapshot_cents FROM sales WHERE store_id=1 AND approval_state='approved' AND sale_stage='delivered' AND delivery_date>=? AND delivery_date<=?",
        (period["date_from"], period["date_to"]))
    amounts = [(r["amount_cents"], r["cost_cents"]) for r in current] + [(r["contract_amount_cents"], r["purchase_cost_snapshot_cents"]) for r in legacy]
    total = sum(a for a, _ in amounts)
    missing = sum(c is None for _, c in amounts)
    margin = None if missing else total - sum(c for _, c in amounts)
    require(data["metrics"]["delivery_count"] == len(amounts) and data["metrics"]["delivery_cents"] == total
        and data["metrics"]["delivery_missing_cost"] == missing and data["metrics"]["delivery_margin_cents"] == margin,
        "全范围交付/原成本/未知毛差指标不一致")
    require(sum(next(c for c in data["charts"] if c["id"] == "delivery")["series"][0]["values"]) == total, "实际交付图表金额错配")
    return row, {"same_run_row": row, "vehicle_id": car["id"], "receipt_id": receipt["id"],
        "direct_margin_cents": case["amount_cents"] - case["cost_cents"], "scope_cost_unknown_count": missing}


def vehicle_facts(e, data, facts, key, requirement_id):
    cars, case = facts["cars"], facts["delivered"]
    vins = {r["vin"] for r in cars}
    sources = [r for r in data["details"] if r["vehicle_id"] in {v["id"] for v in cars}]
    require(len(sources) == 3 and all(r["vin"] in vins and r["store_id"] == 1 for r in sources), "本轮原VIN入出库来源被遗漏或重复")
    ins = [r for r in sources if r["quantity"] == 1]
    outs = [r for r in sources if r["quantity"] == -1]
    require(len(ins) == 2 and len(outs) == 1 and outs[0]["vehicle_id"] == case["vehicle_id"], "本轮实际入2/出1事实不一致")
    for entry in ins:
        movement = next((r for r in facts["movements"] if r["id"] == entry["source_id"]), None)
        require(entry["source"] == "vehicle_purchase_movements" and entry["kind"] == "purchase_receive" and movement
            and movement["kind"] == "receive" and movement["quantity"] == entry["quantity"] == 1
            and movement["vehicle_id"] == entry["vehicle_id"] and movement["value_cents"] == entry["value_cents"]
            and movement["business_date"] == entry["date"], "原采购入库来源、日期或成本不一致")
    out = outs[0]
    positions = e.db.rows("SELECT * FROM vehicle_position_entries WHERE case_id=? AND kind='sale_dispatch' ORDER BY id", (case["id"],))
    dispatches = [r for r in facts["events"] if r["case_id"] == case["id"] and r["action"] == "dispatch"]
    allocations = [r for r in facts["events"] if r["case_id"] == case["id"] and r["action"] == "allocate"]
    require(len(positions) == len(dispatches) == len(allocations) == 1 and allocations[0]["detail"]["vehicle_id"] == case["vehicle_id"]
        and out["source"] == "vehicle_position_entries" and out["source_id"] == positions[0]["id"]
        and positions[0]["vehicle_id"] == out["vehicle_id"] and positions[0]["value_cents"] == out["value_cents"] == -case["cost_cents"]
        and out["date"] == positions[0]["business_date"] == local_time(dispatches[0]["occurred_at"]).date().isoformat(),
        "本轮原销售出库与事件/原位置流水不一致或二计")
    balances = [r for r in data["rows"] if r["vehicle_id"] in {v["id"] for v in cars}]
    require(len(balances) == 2 and all(r["reconciled"] and not r["issues"] for r in balances), "本轮新VIN存在来源缺口，不能用历史背景提示通过")
    for balance in balances:
        car = next(r for r in cars if r["id"] == balance["vehicle_id"])
        leaving = car["id"] == case["vehicle_id"]
        require(balance["vin"] == car["vin"] and balance["generation"] == car["inventory_generation"]
            and [balance[s]["quantity"] for s in ("opening", "in", "out", "closing")] == [0, 1, int(leaving), int(not leaving)]
            and [balance[s]["value_cents"] for s in ("opening", "in", "out", "closing")] == [0, car["purchase_cost_cents"], car["purchase_cost_cents"] if leaving else 0, 0 if leaving else car["purchase_cost_cents"]],
            "本轮VIN代次期初+入-出=期末不守恒")
    require(sum(r["closing"]["quantity"] for r in balances) == 1, "本轮新VIN期末库存不为1")
    background = [r for r in data["rows"] if r not in balances and not r["reconciled"]]
    require(data["complete"] == (len(background) == 0), "整店完整标记与实际来源缺口不一致")
    if background:
        require(data["metrics"]["vehicle_period_closing_count"] is None and data["charts"] == [], "历史缺源被伪造为完整期末合计/图")
    if key == "vehicle_period_movements":
        rows = data["tables"][key]["rows"]
        selected = [r for r in rows if r["values"][2] in vins]
        require(len(selected) == 3, "原入出库明细未逐来源呈现本轮3行")
        chosen = next(r for r in selected if r["quantity"] == -1) if requirement_id == "HK-144" else next(r for r in selected if r["quantity"] == 1)
    else:
        chosen = next(r for r in data["tables"][key]["rows"] if r["vehicle_id"] == case["vehicle_id"])
    return chosen, {"same_run_sources": sources, "same_run_balances": balances, "complete": data["complete"],
        "transit_complete": data["transit_complete"], "historical_unverified_vehicle_ids": [r["vehicle_id"] for r in background],
        "full_store_source_acceptance": "pending" if background else "observed_this_period_only",
        "nonempty_transit_acceptance": "not_tested"}


def cash_facts(data, facts):
    result = []
    for cash in facts["cash"]:
        matching = [r for r in data["tables"]["cash"]["rows"] if r["values"][0] == cash["doc_no"]]
        require(len(matching) == 1, "原收款统计遗漏或重复本轮独立现金源")
        row = matching[0]
        labels = {"workflow_order": "车辆订单收款", "workflow_refund": "流程退款",
                  "vehicle_procurement_payment": "整车采购实际付款"}
        require(row["values"][2] == cash["business_date"] and row["values"][3] == ("收入" if cash["direction"] == "in" else "支出")
            and row["values"][4] == labels.get(cash["category"])
            and row["values"][5:] == [yuan(cash["amount_cents"]), cash["account"], cash["voucher_no"]], "原现金日期/方向/分类/金额/凭据不一致")
        link = next((r for r in facts["payment_links"] if r["cash_id"] == cash["id"]), None)
        if link:
            require(link["amount_cents"] == cash["amount_cents"] and link["direction"] == cash["direction"]
                and link["business_date"] == cash["business_date"] and link["reference"] == cash["voucher_no"], "原PaymentLink和唯一实际现金不一致")
        original_case = link["case_id"] if link else facts["purchase_case"]["id"]
        require(row.get("route") == {"type": "case", "id": original_case}, "原收款明细不能追溯正确原单")
        result.append({"cash_id": cash["id"], "payment_id": link["id"] if link else None, "row": row})
    rows = data["tables"]["cash"]["rows"]
    income = sum(int(Decimal(r["values"][5]) * 100) for r in rows if r["values"][3] == "收入")
    expense = sum(int(Decimal(r["values"][5]) * 100) for r in rows if r["values"][3] == "支出")
    require(data["metrics"]["cash_in_cents"] == income and data["metrics"]["cash_out_cents"] == expense
        and data["metrics"]["cash_net_cents"] == income - expense, "原现金图表/明细范围不一致")
    require(sum(next(c for c in data["charts"] if c["id"] == "cash_category")["series"][0]["values"]) == income - expense,
        "原现金分类图遗漏或重复现金")
    return result, {"original_cash_rows": result, "cash_definition": 7, "scope_in_cents": income, "scope_out_cents": expense}


def customer_facts(e, data, facts):
    customer, case = facts["customer"], facts["delivered"]
    links = e.db.rows("SELECT identity_id FROM group_identity_links WHERE store_id=1 AND local_kind='customer' AND local_id=?", (customer["id"],))
    require(len(links) <= 1, "本轮客户共享身份不唯一")
    token = "g" + str(links[0]["identity_id"]) if links else "s1c" + str(customer["id"])
    matching = [r for r in data["tables"]["customer_value"]["rows"] if r["customer_key"] == token]
    require(len(matching) == 1, "本轮客户价值没有明确原身份归集")
    summary = matching[0]
    details = [r for r in data["tables"]["customer_value_details"]["rows"] if r["customer_key"] == token]
    require(len(details) == 1 and details[0]["route"] == {"type": "case", "id": case["id"]}
        and details[0]["values"][1] == customer["name"] and details[0]["values"][3:5] == [case["number"], case["completed_date"]]
        and details[0]["amount_cents"] == case["amount_cents"] and summary["amount_cents"] == case["amount_cents"]
        and summary["values"][3:] == [1, yuan(case["amount_cents"]), "0.00", "0.00", "0.00", yuan(case["amount_cents"])],
        "客户价值把预收/未履约退款算成交或归错身份")
    return summary, details[0], {"customer_id": customer["id"], "customer_key": token,
        "summary": summary, "details": details, "excluded_cancelled_order_id": facts["cancelled"]["id"]}


def presales_facts(data, facts):
    lead = facts["lead"]
    events = [r for r in facts["events"] if r["case_id"] == lead["id"]]
    contacts = [r for r in events if r["action"] in {"remind", "intent", "follow"}]
    require(contacts and all(facts["period"]["date_from"] <= local_time(r["occurred_at"]).date().isoformat() <= facts["period"]["date_to"] for r in contacts),
        "本轮售前沟通原发生日不在真实期间")
    actual = original_rows(data, "presales_activity", lead["id"])
    require({r["source_id"] for r in actual} == {r["id"] for r in contacts} and len(actual) == len(contacts)
        and data["metrics"]["presales_contact_events"] == len(contacts), "售前实际沟通漏记、重复或把未来计划当沟通")
    for row in actual:
        event = next(r for r in contacts if r["id"] == row["source_id"])
        content = event["detail"]["need" if event["action"] == "intent" else "result"]
        require(row["values"][1] == lead["number"] and row["values"][2] == local_time(event["occurred_at"]).strftime("%Y-%m-%d %H:%M:%S")
            and row["values"][4] == content, "售前沟通原内容、原事件及真实时间错配")
    # A new same-run converted lead must have the actual final transition.
    conversions = [r for r in events if r["before_state"] == "intent" and r["after_state"] == "converted"]
    require(len(conversions) == 1 and conversions[0]["detail"].get("order_id") == facts["delivered"]["id"],
        "本轮报价转订单缺少真实intent→converted原迁移来源")
    conversion = conversions[0]
    transitioned = original_rows(data, "presales_transitions", lead["id"])
    require(any(r["source_id"] == conversion["id"] for r in transitioned), "售前报表遗漏本轮已转订单原迁移")
    issues = original_rows(data, "visit_source_issues", lead["id"])
    require(not issues and data["complete"] is True, "本轮新售前来源不足不能作为报表成功")
    closed = original_rows(data, "presales_stage_durations", lead["id"])
    open_stages = original_rows(data, "presales_open_stages", lead["id"])
    require(not open_stages and len(closed) == 4 and {r["stage"] for r in closed} == {"unassigned", "contacting", "reminder", "intent"},
        "本轮已转订单仍挂意向阶段或阶段历史被遗漏")
    by_id = {r["id"]: r for r in events}
    for row in closed:
        start = by_id[row["start_event_id"]]
        end = by_id[row["end_event_id"]]
        require(start["after_state"] == row["stage"] == end["before_state"], "报表阶段没有连续原进入/结束事件")
        interval = local_time(end["occurred_at"]) - local_time(start["occurred_at"])
        microseconds = interval.days * 86_400_000_000 + interval.seconds * 1_000_000 + interval.microseconds
        minutes = format((Decimal(microseconds) / 60_000_000).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
        require(microseconds >= 0 and row["elapsed_microseconds"] == microseconds and row["values"][5] == minutes,
            "售前自然阶段时长与真实原时间不一致")
        summary = next(r for r in data["tables"]["presales_stage_summary"]["rows"] if r["stage"] == row["stage"])
        require(summary["completed_count"] == 1 and summary["open_count"] == 0 and summary["total_microseconds"] == microseconds
            and summary["mean_minutes"] == minutes, "同原阶段明细/已结束均值不一致")
    require(any(r["end_event_id"] == conversion["id"] and r["stage"] == "intent" for r in closed), "售前意向阶段未结束于本轮转订单")
    return {"same_run_contact_event_ids": [r["id"] for r in contacts], "current_state": lead["state"],
        "conversion_event": conversion, "closed_stages": closed, "planned_contact_not_counted": True}


async def report_business(e, context, credentials):
    checkpoint = Checkpoint(e)
    try:
        facts = source_facts(e, checkpoint)
        actor = await login_as(e, context, credentials, "manager", "work", 1)
        await e.page.set_viewport_size({"width": 1440, "height": 1000})
        require(actor["role"] == "manager", "本轮报表没有以真实本店店长阅读")
        for key, _, route, table_keys in CONTRACTS:
            checkpoint.start(key)
            data = await open_report(e, key, route, facts["period"])
            payload_path = e.directory / (key.lower() + "-native-report.json")
            write_json(payload_path, data)
            checkpoint.record({"native_report": {"path": str(payload_path), "sha256": sha(payload_path)}, "period": facts["period"]})
            evidence = {"tables": [], "csv": [], "charts": [], "source_ids": checkpoint.report["source_ids"]}
            if route.startswith("table/"):
                table_key = table_keys[0]
                evidence["tables"].append(await verify_table(e, data, table_key, "flow"))
                evidence["csv"].append(await export_csv(e, actor, data, table_key, "flow", facts["period"]))
                if key in {"HK-134", "HK-135"}:
                    row, evidence["db"] = lead_facts(e, data, facts)
                    if key == "HK-134":
                        evidence["drill"] = await drill_original(e, data, table_key, row, "flow", facts["lead"])
                        data = await open_report(e, key, route, facts["period"])
                    evidence["charts"].append(await flow_chart(e, "sales", "cohort", data, facts["period"]))
                elif key == "HK-137":
                    row, evidence["db"] = order_facts(e, data, facts)
                    evidence["drill"] = await drill_original(e, data, table_key, row, "flow", facts["delivered"])
                    data = await open_report(e, key, route, facts["period"])
                    evidence["charts"].append(await flow_chart(e, "sales", "orders_trend", data, facts["period"]))
                elif key in {"HK-138", "HK-142"}:
                    row, evidence["db"] = delivery_facts(e, data, facts)
                    if key == "HK-138":
                        evidence["drill"] = await drill_original(e, data, table_key, row, "flow", facts["delivered"])
                        data = await open_report(e, key, route, facts["period"])
                    evidence["charts"].append(await flow_chart(e, "overview", "delivery", data, facts["period"]))
                    if key == "HK-142":
                        await click(e, e.page.locator('.tabs a[href="#analytics/sales"]'), "查看原直接毛差指标")
                        expected_margin = data["metrics"]["delivery_margin_cents"]
                        card = e.page.locator(".kpi").filter(has=e.page.get_by_text("车辆直接毛差", exact=True))
                        shown = "—" if expected_margin is None else format(Decimal(expected_margin) / 100, ",.2f")
                        await expect(card.locator(".value")).to_have_text(shown + "元")
                        evidence["direct_margin_metric_cents"] = expected_margin
                elif key == "HK-160":
                    _, evidence["db"] = cash_facts(data, facts)
                    evidence["charts"].append(await flow_chart(e, "finance", "cash_category", data, facts["period"]))
                    evidence["finance_disclosure"] = await finance_chart_groups(e, data)
                else:
                    summary, detail, evidence["db"] = customer_facts(e, data, facts)
                    await first_page(e, panel(e, data, table_key, "flow"))
                    index = data["tables"][table_key]["rows"].index(summary)
                    require(index < 50, "本轮客户价值超过首屏，需登记真实分页适配")
                    before = e.business_snapshot("before_original_customer_value_drill")
                    token = summary["customer_key"]
                    await click(e, e.page.locator('[data-act="drill"][data-table="customer_value"][data-index="' + str(index) + '"]'), "进入本轮明确客户业务明细")
                    await expect(e.page.locator("#main h1")).to_have_text("客户业务 · " + facts["customer"]["name"])
                    await expect(e.page.locator(".customer-fact")).to_have_count(1)
                    await expect(e.page.locator(".customer-fact")).to_contain_text(facts["delivered"]["number"])
                    e.business_unchanged(before, "after_original_customer_value_drill")
                    evidence["csv"].append(await export_csv(e, actor, data, "customer_value_details", "flow", facts["period"],
                        locator=e.page.locator('[data-act="customer-value-export"][data-key="' + token + '"]'), customer_key=token))
                    before = e.business_snapshot("before_customer_value_original_case")
                    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/cases/" + str(facts["delivered"]["id"])) as pending:
                        await click(e, e.page.locator('.customer-fact [data-act="open"]'), "查看本轮客户实际交付原单")
                    response = await pending.value
                    body = await response.json()
                    require(response.status == 200 and body["id"] == facts["delivered"]["id"], "客户业务跳到错误原单")
                    await expect(e.page.locator("#main .pagehead")).to_contain_text(facts["delivered"]["number"])
                    e.business_unchanged(before, "after_customer_value_original_case")
                    data = await open_report(e, key, route, facts["period"])
                    evidence["charts"].append(await flow_chart(e, "customers", "customer_value", data, facts["period"]))
            elif route == "vehicle-period":
                _, evidence["db"] = vehicle_facts(e, data, facts, table_keys[0], key)
                for table_key in table_keys:
                    evidence["tables"].append(await verify_table(e, data, table_key, "vehicles"))
                    evidence["csv"].append(await export_csv(e, actor, data, table_key, "vehicles", facts["period"]))
                if data["complete"]:
                    evidence["charts"].append(await graph(e, data, "vehicle_period_balances"))
                else:
                    await expect(e.page.locator("#main .notice.error")).to_contain_text("不展示完整期末合计")
                    await expect(e.page.locator('#main svg[role="img"]')).to_have_count(0)
                    evidence["historical_missing_source_graph_suppressed"] = True
                if key in {"HK-143", "HK-144"}:
                    row, _ = vehicle_facts(e, data, facts, table_keys[0], key)
                    original_case = facts["delivered"] if key == "HK-144" else facts["purchase_case"]
                    evidence["drill"] = await drill_original(e, data, table_keys[0], row, "vehicles", original_case)
                    data = await open_report(e, key, route, facts["period"])
            else:
                before = e.business_snapshot("before_actual_presales_source_filter")
                selected = e.page.locator('#visit-activity-filters [name="case_id"]')
                e.action("select", "选择本轮真实售前原单", case_id=facts["lead"]["id"])
                await selected.select_option(str(facts["lead"]["id"]))
                async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/visit-activity-reports") as pending:
                    await click(e, e.page.locator('#visit-activity-filters button[type="submit"]'), "筛选本轮真实售前记录")
                response = await pending.value
                data = await response.json()
                await native_response(e, response, {**facts["period"], "case_id": facts["lead"]["id"]})
                await expect(e.page.locator("#main .loading")).to_have_count(0)
                e.business_unchanged(before, "after_actual_presales_source_filter")
                write_json(payload_path, data)
                checkpoint.record({"native_report": {"path": str(payload_path), "sha256": sha(payload_path)},
                    "selected_source_id": facts["lead"]["id"], "server_complete": data["complete"],
                    "server_source_issues": data["tables"]["visit_source_issues"]["rows"]})
                await e.snapshot("hk136-actual-source-before-strict-check")
                # Strictly fail the present producer/report mismatch. A source
                # warning protects old data, but cannot validate our new chain.
                evidence["db"] = presales_facts(data, facts)
                for table_key in table_keys:
                    evidence["tables"].append(await verify_table(e, data, table_key, "visit"))
                    evidence["csv"].append(await export_csv(e, actor, data, table_key, "visit", facts["period"]))
                evidence["charts"].append(await graph(e, data, "presales_activity"))
                evidence["charts"].append(await graph(e, data, "presales_stage_summary"))
            evidence["experience"] = await experience(e)
            await checkpoint.passed(evidence)
        checkpoint.finish()
    except Exception as error:
        checkpoint.failed(error)
        raise


REPORT_SCENARIOS = ((SCENARIO, report_business, 360),)
