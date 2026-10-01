"""Seven native report checks from this run's five original business sources.

No application imports, setup writes, direct HTTP calls or browser state injection.
HK152 and HK153 are partial source observations, never complete business checks.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from playwright.async_api import expect
from sales_business import login_as, require
from sales_order_business import fixed_dependency
from vehicle_purchase_business import nav
from material_business import choose
from report_business import (click, write_json, sha, yuan, local_time, native_response,
    refresh_report, open_report, panel, verify_table, safe_csv, assert_export_delta,
    export_csv, graph, flow_chart, drill_original, experience)


SCENARIO = "report-followon-hk146-147-148-149-150-151-153-155"
PURCHASE = "vehicle-purchase-hk171-177-178-026-021-018-029"
MASTER = "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187"
CUSTOMER = "customer-service-hk098-107-108-109"
MATERIAL = "materials-hk069-045-054-083-070-072-073-051-061"
REPAIR = "repair-selfpay-hk031-034-044-049-053-079"
CONTRACTS = (
    ("HK-146", "维修预约分析", "table/service_appointments"),
    ("HK-147", "维修工单分析", "table/repairs"),
    ("HK-148", "维修项目分析", "table/repair_projects"),
    ("HK-149", "维修领料分析", "repair-materials"),
    ("HK-150", "物资入库历史统计", "table/movements"),
    ("HK-151", "物资出库历史统计", "table/movements"),
    ("HK-155", "物资移库明细统计", "table/warehouse_local_moves"),
)
PARTIAL_CONTRACTS = (("HK-153", "物资采购订货统计", "procurement-cohort"),
    ("HK-152", "物资仓库入出存统计", "warehouse-period"))
TABLES = {"flow_cases", "flow_items", "flow_stock_moves", "flow_events", "flow_payment_links",
    "cash_entries", "intake_appointments", "intake_arrivals", "intake_vehicle_bindings",
    "repair_quotes", "repair_lines", "repair_authorizations", "repair_stock", "repair_settlements",
    "repair_allocations", "repair_payments", "procurement_orders", "procurement_lines",
    "procurement_receipts", "procurement_return_postings", "warehouse_documents", "warehouse_entries",
    "warehouse_balances", "warehouse_enrollments", "master_locations", "master_warehouses", "repairs",
    "group_aftercare_holds", "repair_package_payment_links"}
PRIMARY_KEYS = {"intake_vehicle_bindings": "case_id"}
STATE = {"completed": "已完成", "assessment": "待检查报价", "authorization": "待客户授权",
    "working": "处理中", "quality": "待质检", "settling": "待结算交接", "credit_open": "已交车待月结",
    "pending": "待办理", "approval": "待复核", "cancelled": "已取消", "rejected": "已退回"}
MOVEMENT_LABELS = {"purchase": "采购入库", "procurement_receipt": "采购分批入库",
    "procurement_receive": "采购分批入库", "procurement_return": "采购退货出库", "transfer_out": "店间调拨发出",
    "transfer_in": "店间调拨验收", "transfer_return": "拒收退回入库", "issue": "维修领料", "return": "维修退料",
    "count": "盘点差异", "repair_issue_v3": "维修明细领料", "repair_return_v3": "维修明细退料",
    "retail_dispatch": "精品实际出库", "retail_return": "精品原单退货", "wh_other_in": "其他实际入库",
    "wh_other_return": "其他入库原单退回", "wh_consumable": "耗材领用", "wh_consume_return": "耗材原单退回",
    "wh_gift": "礼品领用", "wh_gift_return": "礼品原单退回", "wh_disposal": "其他实际出库", "wh_count": "实盘批准差异"}
QUANTITIES = ("ordered", "received", "open", "closed", "pending", "returned", "retained")
LEGACY_PROCUREMENT_REASON = "历史简表采购：仅按原登记日期列出，缺少不可变逐行订货来源，不混入新订货履约合计"
ZONE = ZoneInfo("Asia/Shanghai")


class Checkpoint:
    def __init__(self, e):
        self.e, self.active, self.partial = e, None, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = hashlib.sha256(raw).hexdigest()
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        requirements = []
        for key, title, route in CONTRACTS:
            bound = catalog[key]
            require(bound["title"] == title and route in bound["target_routes"] and bound["source_review_status"] == "source_reviewed", key + " 原合同错配")
            require(any(c["check_id"] == key + "-business" for c in bound["acceptance_checks"]), key + " 原check缺失")
            requirements.append({"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested",
                    "criteria": ["原UI实际期间、非空明细与同范围图", "原API及DB来源和整数金额数量一致",
                        "原单钻取、全部分页与实际CSV", "只读及唯一导出审计保护",
                        "流程简易：待独立人工评价", "文案简洁：待独立人工评价"], "evidence": {}}],
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"}})
        partials = []
        for key, title, route in PARTIAL_CONTRACTS:
            bound = catalog[key]
            require(bound["title"] == title and route in bound["target_routes"] and bound["source_review_status"] == "source_reviewed", key + " 局部原合同错配")
            partials.append({"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_check_submitted": False})
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [c[0] for c in CONTRACTS],
            "partial_scope": [c[0] for c in PARTIAL_CONTRACTS], "requirements": requirements, "partial_requirements": partials,
            "complete": False, "passed": False, "business_accepted": False,
            "source_contract_sha256": self.digest, "candidate_sha256": sha(Path(__file__)),
            "execution": "native_browser_original_reports", "human_acceptance": "pending",
            "acceptance_rule": "自动UI/API/DB检查通过不代表六类标准全部通过；人工待评期间business_accepted保持false",
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "conditions": {"group_scope": "not_tested", "historical_complete_warehouse_period": "not_tested",
                "complete_procurement_cohort_summary_charts_and_dynamic_csv": "not_tested",
                "production_money_or_handover_acceptance": False, "postgresql_linux_employee_acceptance": False}}
        self.save()

    def save(self):
        write_json(self.path, self.report)

    def start(self, key):
        self.partial = None
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        require(self.active["status"] == "not_tested", "不覆盖已执行check")
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active["evidence_action_start"] = len(self.e.actions)
        self.save()

    def start_partial(self, key):
        self.active = None
        self.partial = next(r for r in self.report["partial_requirements"] if r["id"] == key)
        require(self.partial["status"] == "not_tested", "不覆盖已执行局部观察")
        self.partial.update(status="running", evidence_action_start=len(self.e.actions))
        self.save()

    def note(self, **evidence):
        self.active["acceptance_checks"][0]["evidence"].update(evidence)
        self.save()

    async def passed(self, **evidence):
        self.note(**evidence)
        await self.e.snapshot(self.active["id"].lower() + "-report", business_ready=True)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.active["acceptance_checks"][0]["error"] = self.e.scrub(error)
        elif self.partial and self.partial["status"] == "running":
            self.partial.update(status="failed", error=self.e.scrub(error))
        self.report.update(error=self.e.scrub(error), executed_requirements=sum(r["status"] != "not_tested" for r in self.report["requirements"]),
            passed_requirements=sum(r["status"] == "passed" for r in self.report["requirements"]))
        self.save()

    def finish(self):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "七报表未完整执行")
        require(all(r["status"] == "partial" for r in self.report["partial_requirements"]), "两项局部来源观察尚未完成")
        self.report.update(complete=True, passed=True, executed_requirements=7, passed_requirements=7)
        self.save()
        self.e.observe("report_followon_business_checkpoint", {"path": str(self.path), "complete_checks": 7,
            "partial_only": ["HK-152", "HK-153"], "human_acceptance": "pending", "business_accepted": False})


def rows(e, table, store_id):
    require(table in TABLES, "报表来源表未核准")
    found = e.db.rows(f"SELECT * FROM {table} WHERE store_id=? ORDER BY {PRIMARY_KEYS.get(table, 'id')} LIMIT 25001", (store_id,))
    require(len(found) <= 25000, "原来源超限，不能截断")
    return found


def one(e, table, key, store_id):
    require(table in TABLES and type(key) is int and key > 0, "明确原来源ID无效")
    found = e.db.rows(f"SELECT * FROM {table} WHERE {PRIMARY_KEYS.get(table, 'id')}=? AND store_id=?", (key, store_id))
    require(len(found) == 1, "本店原来源不存在：" + table)
    return found[0]


def qty(value):
    return format(Decimal(value) / 1000, "f")


def compare_rows(actual, expected, label):
    encode = lambda r: json.dumps(r, ensure_ascii=False, sort_keys=True)
    require(Counter(map(encode, actual)) == Counter(map(encode, expected)), label + " 原全部行与DB不一致")


def inside(day, period):
    return bool(day and period["date_from"] <= day <= period["date_to"])


def chart_record(data, key):
    found = [c for c in data["charts"] if c["id"] == key]
    require(len(found) == 1, "图表源不唯一：" + key)
    return found[0]


def source_facts(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "只允许同轮外置合成实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "报表库不是本次外置runtime")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance.get("snapshot_stable") is True, "报表镜像未稳定")
    for name in ("report_followon_business.py", "report_business.py", "sales_order_business.py", "sales_business.py",
        "vehicle_purchase_business.py", "master_data_business.py", "customer_service_business.py", "material_business.py", "repair_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name)), "本次脚本指纹变化：" + name)
    cp.report["mirror"] = {"provenance_sha256": sha(root / "provenance.json"), "source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"]}
    prior = {name: fixed_dependency(e, cp, name) for name in (PURCHASE, MASTER, CUSTOMER, MATERIAL, REPAIR)}
    cv_partial = [p for p in prior[CUSTOMER]["partial_requirements"] if p["id"] == "HK-099"]
    require(len(cv_partial) == 1 and cv_partial[0]["status"] == "partial"
        and cv_partial[0]["local_scope_status"] == "local_scope_passed"
        and cv_partial[0]["business_accepted"] is False and cv_partial[0]["acceptance_check_submitted"] is False,
        "客户车辆前序必须保留本店局部来源边界")
    fixture = dict(e.manifest["business_fixtures"]["repair"])
    sid = fixture["store_id"]
    require(sid == 1 and e.manifest["users"][fixture["manager_key"]]["role"] == "manager", "原报表helper须同本店主管")
    refs = prior[REPAIR]["report_sources"]
    require(set(refs) == {"customer_id", "customer_vehicle_id", "vin", "appointment_id", "intake_case_id", "repair_case_id", "quote_id", "allocation_id", "payment_link_id", "cash_id", "material_item_id"}, "首维修有限源键不完整")
    repair = one(e, "flow_cases", refs["repair_case_id"], sid)
    repair["data"] = json.loads(repair["data"])
    appointment = one(e, "intake_appointments", refs["appointment_id"], sid)
    quote = one(e, "repair_quotes", refs["quote_id"], sid)
    require(repair["kind"] == "repair" and repair["flow_version"] == 4 and repair["state"] == "completed"
        and repair["customer_id"] == refs["customer_id"] and repair["data"]["released_date"]
        and appointment["case_id"] == refs["intake_case_id"] and appointment["repair_case_id"] == repair["id"]
        and appointment["customer_vehicle_id"] == refs["customer_vehicle_id"] and appointment["status"] == "converted", "原接待维修未真实完成或串来源")
    require(quote["case_id"] == repair["id"] and quote["purpose"] == "service", "原最终报价来源错误")
    stock = [s for s in rows(e, "repair_stock", sid) if s["case_id"] == repair["id"]]
    moves = [one(e, "flow_stock_moves", s["stock_move_id"], sid) for s in stock]
    require(len(stock) == len(moves) == 3 and [s["quantity_milli"] for s in stock] == [1250, -250, 250]
        and sum(s["quantity_milli"] for s in stock) == 1250, "原三笔领退补领源不齐")
    for s, move in zip(stock, moves):
        require(s["quote_id"] == quote["id"] and move["item_id"] == refs["material_item_id"]
            and move["case_id"] == repair["id"] and (move["quantity_milli"], move["value_cents"]) == (-s["quantity_milli"], -s["value_cents"]), "原库存与维修明细数量成本串源")
    require(stock[1]["original_id"] == stock[0]["id"] and moves[1]["original_id"] == moves[0]["id"], "原退非原领")
    material = prior[MATERIAL]["material_sources"]
    require(set(material) == {"primary", "secondary"} and material["primary"]["item_id"] == refs["material_item_id"], "原物资两来源错配")
    pinned = {}
    for given in material.values():
        for name, table in (("receipt_ids", "procurement_receipts"), ("stock_move_ids", "flow_stock_moves"), ("entry_ids", "warehouse_entries")):
            require(given[name], "原物资有限来源为空")
            pinned.setdefault(table, []).extend(one(e, table, key, sid) for key in given[name])
    dates = [repair["business_date"], repair["data"]["released_date"], local_time(appointment["starts_at"]).date().isoformat()]
    dates += [m["business_date"] for m in moves + pinned["flow_stock_moves"]]
    events = [r for r in rows(e, "flow_events", sid) if r["case_id"] == material["primary"]["purchase_order_id"] and r["action"] == "procurement_create"]
    require(len(events) == 1, "物资缺唯一原申请日")
    dates.append(local_time(events[0]["occurred_at"]).date().isoformat())
    period = {"date_from": min(dates), "date_to": max(dates)}
    require(period["date_to"] <= datetime.now(ZONE).date().isoformat(), "原预约来源还在未来，不能造当前期间")
    result = {"store_id": sid, "store_name": next(s["name"] for s in e.manifest["stores"] if s["id"] == sid),
        "refs": refs, "repair": repair, "appointment": appointment, "quote": quote, "stock": stock, "moves": moves,
        "material": material, "period": period, "pinned_original_rows": pinned}
    cp.report["source_preconditions"] = result
    cp.report["source_preconditions"]["hk099_status"] = "local_source_only_not_business_accepted"
    cp.save()
    return fixture, result


async def dedicated_report(e, key, route, period, path, title):
    before = e.business_snapshot("before_followon_original_entry")
    await nav(e, "module/analytics", "统计分析", None)
    await e.fill("#mux-query", key, "检索明确报表原需求")
    await click(e, e.page.locator('[data-mux-open="wf-report-' + key.split("-")[1] + '"]'), "打开原报表入口")
    await expect(e.page).to_have_url(re.compile("#" + re.escape(route) + "$"))
    await expect(e.page.locator("#datefilters")).to_be_visible()
    data = await refresh_report(e, path, period)
    await expect(e.page.locator("#main h1")).to_have_text(title)
    await expect(e.page.locator("#store")).to_have_value("1")
    e.business_unchanged(before, "after_followon_original_entry")
    return data


async def dedicated_export(e, actor, data, key, family, period, extra=None, locator=None):
    require(family in {"repair_material", "procurement", "warehouses"}, "专用原导出域无效")
    filters = {k: v for k, v in (extra or {}).items() if v is not None and v != ""}
    if family == "repair_material":
        path, entity_type, action = "/api/repair-material-reports/export/" + key, "repair_material_report", "rm-export"
    else:
        path = "/api/inventory-reports/" + family + "/export/" + key
        entity_type, action = family + "_inventory_report", "inventory-report-export"
    parameters = {**period, **filters}
    locator = locator if locator is not None else panel(e, data, key, family).locator('[data-act="' + action + '"][data-key="' + key + '"]')
    before = e.business_snapshot("before_followon_original_csv")
    old_audit = e.db.rows("SELECT * FROM audit_logs ORDER BY id")
    async with e.page.expect_download() as downloaded:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
            await click(e, locator, "下载原" + key + "全部CSV")
        response = await pending.value
        metadata = await native_response(e, response, parameters)
    download = await downloaded.value
    require(await download.failure() is None, "原CSV下载失败，不重放")
    directory = e.directory / "exports"
    directory.mkdir(exist_ok=True)
    destination = directory / (str(len(list(directory.iterdir())) + 1).zfill(2) + "-" + key + ".csv")
    await download.save_as(destination)
    actual = list(csv.reader(io.StringIO(destination.read_text(encoding="utf-8-sig"), newline="")))
    source = data["tables"][key]
    expected = [source["headers"]] + [[safe_csv(v, "inventory") for v in row["values"]] for row in source["rows"]]
    require(actual == expected, "专用CSV不是同原筛选全表／顺序")
    audit = assert_export_delta(e, before, old_audit, actor, entity_type, period["date_from"] + "至" + period["date_to"] + " " + key)
    result = {"path": str(destination), "sha256": sha(destination), "rows": len(source["rows"]), "native_http": metadata,
        "audit": audit, "all_old_audit_and_business_rows_protected": True, "download_body_only_from_file": True}
    e.observe("followon_original_csv", result)
    return result


def appointments_facts(e, data, src):
    sid, period = src["store_id"], src["period"]
    cases = {c["id"]: c for c in rows(e, "flow_cases", sid)}
    arrivals = {a["appointment_id"]: a for a in rows(e, "intake_arrivals", sid)}
    labels = {"scheduled": "预约待到店", "arrived": "已到店待开单", "converted": "已转维修工单", "cancelled": "已取消或离场", "no_show": "未到店结案"}
    expected, counts = [], Counter()
    for a in rows(e, "intake_appointments", sid):
        stamp = local_time(a["starts_at"])
        if not inside(stamp.date().isoformat(), period):
            continue
        counts[labels[a["status"]]] += 1
        expected.append([cases[a["case_id"]]["number"], src["store_name"], stamp.strftime("%Y-%m-%d %H:%M"),
            "预约" if a["mode"] == "appointment" else "直接到店", labels[a["status"]], "是" if a["id"] in arrivals else "否",
            cases[a["repair_case_id"]]["number"] if a["repair_case_id"] else ""])
    compare_rows([r["values"] for r in data["tables"]["service_appointments"]["rows"]], expected, "预约批次")
    c = chart_record(data, "service_appointments")
    require(dict(zip(c["labels"], c["series"][0]["values"])) == dict(counts), "预约全批次图计数错误")
    target = [r for r in data["tables"]["service_appointments"]["rows"] if r["route"]["id"] == src["refs"]["intake_case_id"]]
    require(len(target) == 1 and target[0]["values"][4:6] == ["已转维修工单", "是"], "本次非空预约／实际到店未显示")
    return target[0], {"whole_cohort_count": len(expected), "current_state_counts": dict(counts), "appointment": src["appointment"]}


def released_repair_facts(e, data, src):
    sid = src["store_id"]
    discount = defaultdict(int)
    benefits = e.db.rows("SELECT e.*,w.source_kind,r.sale_cents_per_unit FROM benefit_entries e "
        "LEFT JOIN benefit_wallets w ON w.id=e.wallet_id LEFT JOIN benefit_rules r ON r.id=w.rule_id "
        "WHERE e.store_id=? ORDER BY e.id LIMIT 25001", (sid,))
    require(len(benefits) <= 25000, "原权益优惠来源超限，不能截断")
    for entry in benefits:
        require(entry["source_kind"] in {"purchase", "grant", "exchange"}
            and type(entry["sale_cents_per_unit"]) is int, "原权益冻结价来源缺失")
        consumed = -entry["units"] if entry["purpose"] in {"capture", "reverse"} else 0
        recognized = consumed * entry["sale_cents_per_unit"] if entry["source_kind"] == "purchase" else 0
        discount[entry["case_id"]] += entry["credit_cents"] - recognized
    for hold in rows(e, "group_aftercare_holds", sid):
        if hold["status"] == "applied":
            discount[hold["source_case_id"]] += hold["discount_cents"]
    for link in rows(e, "repair_package_payment_links", sid):
        if link["purpose"] == "capture":
            discount[link["case_id"]] += link["amount_cents"] - link["recognized_cents"]
    allocations = rows(e, "repair_allocations", sid)
    expected, totals = [], defaultdict(int)
    for case in rows(e, "flow_cases", sid):
        detail = json.loads(case["data"])
        day = detail.get("released_date")
        if case["kind"] != "repair" or not inside(day, src["period"]) or detail.get("payer") == "内部":
            continue
        detailed = case["flow_version"] in {3, 4}
        gross = sum(a["amount_cents"] for a in allocations if a["case_id"] == case["id"]
            and a["payer_type"] != "internal") if detailed else case["amount_cents"]
        net = gross - discount[case["id"]]
        require(net >= 0, "原承担与权益优惠不守恒")
        expected.append([case["number"], src["store_name"], case["title"].split(" · ")[0], day,
            yuan(net), "多方承担" if detailed else detail.get("payer", "待确认")])
        totals[day] += net
    for repair in rows(e, "repairs", sid):
        if repair["approval_state"] != "approved" or repair["repair_stage"] != "completed" or not inside(repair["completion_date"], src["period"]):
            continue
        amount = repair["labor_amount_cents"] + repair["parts_amount_cents"] - repair["discount_cents"]
        expected.append([repair["doc_no"], src["store_name"], repair["customer_name"], repair["completion_date"], yuan(amount), "既有记录"])
        totals[repair["completion_date"]] += amount
    compare_rows([r["values"] for r in data["tables"]["repair_settlements"]["rows"]], expected, "实际接车日维修结算")
    daily = data["tables"]["daily"]["rows"]
    c = chart_record(data, "repair_value")
    require(c["labels"] == [r["values"][0][5:] for r in daily]
        and c["series"][0]["values"] == [totals[r["values"][0]] for r in daily]
        and data["metrics"]["repair_cents"] == sum(totals.values()), "实际接车日全范围金额图与原账不符")
    return {"whole_scope_release_daily_cents": dict(totals), "whole_scope_external_settled_cents": sum(totals.values()),
        "target_actual_released_date": src["repair"]["data"]["released_date"]}


def repair_facts(e, data, src):
    sid, target = src["store_id"], src["repair"]
    found = [r for r in data["tables"]["repairs"]["rows"] if r.get("route") == {"type": "case", "id": target["id"]}]
    require(len(found) == 1, "原非空维修不唯一")
    paid = sum(p["amount_cents"] * (1 if p["direction"] == "in" else -1) for p in rows(e, "flow_payment_links", sid) if p["case_id"] == target["id"])
    expected = [target["number"], src["store_name"], target["title"].split(" · ")[0], target["business_date"], STATE[target["state"]],
        yuan(target["amount_cents"]), yuan(paid), target["data"]["payer"]]
    require(found[0]["values"] == expected and paid == target["amount_cents"], "原结算与实收未一致")
    allocation = one(e, "repair_allocations", src["refs"]["allocation_id"], sid)
    link = one(e, "flow_payment_links", src["refs"]["payment_link_id"], sid)
    cash = one(e, "cash_entries", src["refs"]["cash_id"], sid)
    association = [r for r in rows(e, "repair_payments", sid) if r["allocation_id"] == allocation["id"]]
    require(allocation["case_id"] == target["id"] and allocation["payer_type"] == "customer" and allocation["amount_cents"] == paid
        and len(association) == 1 and association[0]["payment_link_id"] == link["id"] and link["cash_id"] == cash["id"]
        and cash["approval_state"] == "approved" and link["amount_cents"] == cash["amount_cents"] == paid, "原承担／独立实款关联错误")
    counts = Counter(STATE[r["state"]] for r in rows(e, "flow_cases", sid) if r["kind"] == "repair" and inside(r["business_date"], src["period"]))
    for r in rows(e, "repairs", sid):
        if r["approval_state"] == "approved" and inside(r["business_date"], src["period"]):
            counts["已完工" if r["repair_stage"] == "completed" else "维修中"] += 1
    c = chart_record(data, "repair_state")
    require(dict(zip(c["labels"], c["series"][0]["values"])) == dict(counts) and data["metrics"]["new_repairs"] == sum(counts.values()), "全范围工单图／计数错误")
    return found[0], {"allocation": allocation, "payment_link": link, "cash": cash,
        "whole_scope_state_counts": dict(counts), **released_repair_facts(e, data, src)}


def projects_facts(e, data, src):
    sid, period = src["store_id"], src["period"]
    cases = {c["id"]: c for c in rows(e, "flow_cases", sid)}
    quotes = {q["id"]: q for q in rows(e, "repair_quotes", sid)}
    authorized = {a["quote_id"] for a in rows(e, "repair_authorizations", sid)}
    lines = rows(e, "repair_lines", sid)
    expected, totals = [], defaultdict(int)
    for settlement in rows(e, "repair_settlements", sid):
        case = cases[settlement["case_id"]]
        day = json.loads(case["data"]).get("released_date")
        q = quotes[settlement["quote_id"]]
        if not inside(day, period) or q["purpose"] != "service":
            continue
        own = [l for l in lines if l["quote_id"] == q["id"]]
        require(q["id"] in authorized and sum(l["amount_cents"] for l in own) == q["amount_cents"], "最终报价缺授权／不守恒")
        for line in own:
            if line["kind"] != "work":
                continue
            expected.append([case["number"], src["store_name"], day, q["revision"], line["code"], line["name"], qty(line["quantity_milli"]), line["unit"], yuan(line["amount_cents"])])
            totals[line["code"] + " · " + line["name"]] += line["amount_cents"]
    compare_rows([r["values"] for r in data["tables"]["repair_projects"]["rows"]], expected, "最终作业")
    c = chart_record(data, "repair_projects")
    require(dict(zip(c["labels"], c["series"][0]["values"])) == dict(totals)
        and data["metrics"]["repair_project_basis_cents"] == sum(totals.values()), "作业全范围金额图错误")
    target = [r for r in data["tables"]["repair_projects"]["rows"] if r.get("route") == {"type": "case", "id": src["repair"]["id"]}]
    require(len(target) == 1, "本轮最终作业不唯一")
    return target[0], {"final_quote": src["quote"], "whole_scope_project_basis_cents": sum(totals.values())}


def movement_facts(e, data, src, *, inbound):
    sid, period = src["store_id"], src["period"]
    items = {r["id"]: r for r in rows(e, "flow_items", sid)}
    cases = {r["id"]: r for r in rows(e, "flow_cases", sid)}
    movements = [m for m in rows(e, "flow_stock_moves", sid) if inside(m["business_date"], period)]
    expected = [[cases[m["case_id"]]["number"] if m["case_id"] in cases else "", src["store_name"], m["business_date"],
        items[m["item_id"]]["name"], MOVEMENT_LABELS.get(m["purpose"], m["purpose"]), qty(m["quantity_milli"]), items[m["item_id"]]["unit"], yuan(m["value_cents"])] for m in movements]
    compare_rows([r["values"] for r in data["tables"]["movements"]["rows"]], expected, "物资全期间库存")
    c = chart_record(data, "material_value")
    totals = defaultdict(lambda: [0, 0])
    for m in movements:
        totals[m["business_date"]][0 if m["value_cents"] >= 0 else 1] += abs(m["value_cents"])
    days = list(data["tables"]["daily"]["rows"])
    require(c["labels"] == [r["values"][0][5:] for r in days] and len(c["series"]) == 2, "物资原图日期范围错配")
    for index in range(2):
        require(c["series"][index]["values"] == [totals[r["values"][0]][index] for r in days], "原全范围入出成本图错误")
    finite_ids = {m["id"] for m in src["moves"]}
    finite_ids.update(key for given in src["material"].values() for key in given["stock_move_ids"])
    chosen = [m for m in movements if m["id"] in finite_ids and (m["quantity_milli"] > 0 if inbound else m["quantity_milli"] < 0)]
    require(chosen, "本次原方向没有非空实际事实")
    purposes = {m["purpose"] for m in chosen}
    require(({"procurement_receipt", "repair_return_v3", "wh_count"} if inbound else {"procurement_return", "repair_issue_v3", "wh_count"}) <= purposes, "本方向少了明确原入出／盘差／维修")
    selected_case = src["repair"]
    selected = [r for r in data["tables"]["movements"]["rows"] if r.get("route") == {"type": "case", "id": selected_case["id"]}
        and (Decimal(r["values"][5]) > 0 if inbound else Decimal(r["values"][5]) < 0)]
    require(selected, "本次维修入出原单不在明细")
    return selected[0], {"direction": "in" if inbound else "out", "finite_original_moves": chosen,
        "whole_scope_move_count": len(movements), "whole_scope_value_cents": sum(m["value_cents"] for m in movements)}


async def flow_check(e, cp, src, key, table_key, section, chart_key, oracle, *, inbound=None):
    cp.start(key)
    data = await open_report(e, key, "table/" + table_key, src["period"])
    selected, facts = oracle(e, data, src, **({"inbound": inbound} if inbound is not None else {}))
    cp.note(original_api=data, db_facts=facts)
    shown = await verify_table(e, data, table_key, "flow")
    csv_file = await export_csv(e, src["actor"], data, table_key, "flow", src["period"])
    case_id = selected["route"]["id"]
    origin = one(e, "flow_cases", case_id, src["store_id"])
    drill = await drill_original(e, data, table_key, selected, "flow", origin)
    # Reopen through the actual catalog before using the original table's back button.
    data = await open_report(e, key, "table/" + table_key, src["period"])
    graphic = await flow_chart(e, section, chart_key, data, src["period"])
    secondary = None
    if key == "HK-147":
        graphic_value = await graph(e, data, "repair_value")
        before = e.business_snapshot("before_original_repair_value_details")
        target = e.page.locator("#main .chartpanel").filter(has=e.page.get_by_role("heading", name=chart_record(data, "repair_value")["title"], exact=True))
        await click(e, target.locator('[data-act="charttable"][data-table="repair_settlements"]'), "查看实际接车日维修结算原明细")
        await expect(e.page.locator("#main h1")).to_have_text(data["tables"]["repair_settlements"]["title"])
        e.business_unchanged(before, "after_original_repair_value_details")
        secondary = {"chart": graphic_value, "all_pages": await verify_table(e, data, "repair_settlements", "flow"),
            "actual_csv": await export_csv(e, src["actor"], data, "repair_settlements", "flow", src["period"])}
    # Full-range chart re-read must still agree with the independently captured facts.
    oracle(e, data, src, **({"inbound": inbound} if inbound is not None else {}))
    await cp.passed(db_facts=facts, all_pages=shown, actual_csv=csv_file, original_drill=drill, chart=graphic,
        actual_release_settlement=secondary, experience=await experience(e), human_acceptance="pending")


async def repair_filter(e, src, values):
    before = e.business_snapshot("before_original_repair_material_filters")
    for name, value in values.items():
        await e.page.locator('#repair-material-filters [name="' + name + '"]').select_option(str(value))
        e.action("select", "明确原领退料筛选", field=name, value=str(value))
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/repair-material-reports") as pending:
        await click(e, e.page.locator('#repair-material-filters button[type="submit"]'), "筛选实际原领退料")
    response = await pending.value
    data = await response.json()
    await native_response(e, response, {**src["period"], **values})
    await expect(e.page.locator("#main h1")).to_have_text("维修实际领退料分析")
    await expect(e.page.locator("#main .loading")).to_have_count(0)
    e.business_unchanged(before, "after_original_repair_material_filters")
    return data


def repair_material_facts(e, data, src):
    sid, repair = src["store_id"], src["repair"]
    binding = [b for b in rows(e, "intake_vehicle_bindings", sid) if b["case_id"] == repair["id"]]
    event = [v for v in rows(e, "flow_events", sid) if v["case_id"] == repair["id"] and v["action"] == "repair_vehicle_model_snapshot"]
    require(len(binding) == len(event) == 1, "原冻结车型来源不唯一")
    snapshot = json.loads(event[0]["detail"])
    require(snapshot["customer_vehicle_id"] == binding[0]["customer_vehicle_id"] == src["refs"]["customer_vehicle_id"]
        and snapshot["vin"] == binding[0]["vin"] == src["refs"]["vin"] and snapshot["model_name"]
        and snapshot["schema_version"] == 1 and type(snapshot["customer_vehicle_version"]) is int
        and snapshot["customer_vehicle_version"] > 0, "历史车型不匹配原绑定")
    facts = data["details"]
    require(data["complete"] is True and data["model_complete"] is True and data["issues"] == []
        and {r["source_id"] for r in facts} == {m["id"] for m in src["moves"]} and len(facts) == 3, "原四维筛选少行／重复／来源不完整")
    auth = [a for a in rows(e, "repair_authorizations", sid) if a["quote_id"] == src["quote"]["id"]]
    require(len(auth) == 1 and auth[0]["quote_digest"] == src["quote"]["digest"], "原领料缺冻结授权")
    by_source = {r["source_id"]: r for r in facts}
    for stock, move in zip(src["stock"], src["moves"]):
        row = by_source[move["id"]]
        require(row["repair_stock_id"] == stock["id"] and row["case_id"] == repair["id"] and row["quote_id"] == src["quote"]["id"]
            and row["model_name"] == snapshot["model_name"] and row["quantity_milli"] == stock["quantity_milli"]
            and row["value_cents"] == stock["value_cents"] and row["original_source_id"] == move["original_id"], "原三笔维修领退来源方向／成本错配")
    require(len(data["rows"]) == 1, "同物资车型汇总不唯一")
    total = data["rows"][0]
    require((total["issued_milli"], total["returned_milli"], total["net_milli"]) == (1500, 250, 1250)
        and total["net_cents"] == sum(s["value_cents"] for s in src["stock"])
        and data["metrics"]["repair_material_actual_net_cents"] == total["net_cents"], "实际领退净量／成本错误")
    c = chart_record(data, "repair_material_cost")
    require(c["labels"] == [snapshot["model_name"]] and c["series"][0]["values"] == [total["net_cents"]], "原历史车型图错配")
    return snapshot


async def repair_material_check(e, cp, src):
    cp.start("HK-149")
    data = await dedicated_report(e, "HK-149", "repair-materials", src["period"], "/api/repair-material-reports", "维修实际领退料分析")
    # Scope the original case first so unrelated historical gaps remain outside this explicit source.
    filters = {"case_id": src["repair"]["id"]}
    data = await repair_filter(e, src, filters)
    model = repair_material_facts(e, data, src)
    work = [l for l in rows(e, "repair_lines", src["store_id"]) if l["quote_id"] == src["quote"]["id"] and l["kind"] == "work"]
    require(len(work) == 1, "本次原作业来源不唯一")
    steps = [dict(filters)]
    for key, value in (("item_id", src["refs"]["material_item_id"]), ("model_name", model["model_name"]), ("work_item_id", work[0]["work_item_id"])):
        filters[key] = value
        data = await repair_filter(e, src, filters)
        repair_material_facts(e, data, src)
        steps.append(dict(filters))
    cp.note(original_api=data, original_filters=steps, model_snapshot=model)
    shown, csv_files = [], []
    for key in ("repair_material_totals", "repair_material_movements", "repair_material_issues"):
        shown.append(await verify_table(e, data, key, "repair_material"))
        csv_files.append(await dedicated_export(e, src["actor"], data, key, "repair_material", src["period"], filters))
    graphic = await graph(e, data, "repair_material_cost")
    row = data["tables"]["repair_material_movements"]["rows"][0]
    drill = await drill_original(e, data, "repair_material_movements", row, "repair_material", src["repair"])
    await cp.passed(original_filters=steps, model_snapshot=model, all_pages=shown, actual_csv=csv_files,
        original_drill=drill, chart=graphic, actual_original_stock_ids=[m["id"] for m in src["moves"]], experience=await experience(e))


def procurement_facts(e, data, src):
    sid = src["store_id"]
    require(data["can_money"] is True, "本店主管原采购金额范围缺失")
    ids = {g["purchase_order_id"] for g in src["material"].values()}
    require(len(ids) == 1, "本次两物资不在原同采购")
    key = next(iter(ids))
    lines = [l for l in rows(e, "procurement_lines", sid) if l["case_id"] == key]
    require(len(lines) == 2, "原两行采购不完整")
    receipts = [r for r in rows(e, "procurement_receipts", sid) if r["case_id"] == key]
    returns = [r for r in rows(e, "procurement_return_postings", sid) if r["case_id"] == key]
    own = [r for r in data["rows"] if r["case_id"] == key]
    require(len(own) == len(data["rows"]) == 2 and all(r["reconciled"] and r["issues"] == [] for r in own), "本次采购原两行未显示或混入未知新批次")
    header = one(e, "procurement_orders", key, sid)
    origin = one(e, "flow_cases", key, sid)
    moves = {m["id"]: m for m in rows(e, "flow_stock_moves", sid)}
    expected_details = []
    for line in lines:
        received = [r for r in receipts if r["line_id"] == line["id"]]
        returned = [r for r in returns if r["receipt_id"] in {v["id"] for v in received}]
        expected = {"ordered": (line["quantity_milli"], line["amount_cents"]),
            "received": (sum(r["quantity_milli"] for r in received), sum(r["value_cents"] for r in received)),
            "returned": (sum(r["quantity_milli"] for r in returned), sum(r["value_cents"] for r in returned))}
        expected.update(open=(0, 0), closed=(0, 0), pending=(0, 0))
        expected["retained"] = tuple(expected["received"][i] - expected["returned"][i] for i in range(2))
        require(expected["ordered"] == expected["received"] and len(received) == 2, "原订货不是两次完整验收")
        row = next(r for r in own if r["line_id"] == line["id"])
        require(row["supplier"] == header["supplier_name"] and row["sku"] == line["sku"] and row["unit"] == line["unit"], "原供应方／物资／单位错配")
        for state, (quantity, value) in expected.items():
            require(row[state] == {"quantity_milli": quantity, "value_cents": value}, "原累计订货维度不守恒：" + state)
        for posting in received + returned:
            m = moves[posting["stock_move_id"]]
            sign = 1 if posting in received else -1
            require(m["case_id"] == key and m["item_id"] == line["item_id"]
                and m["purpose"] == ("procurement_receipt" if sign == 1 else "procurement_return")
                and (m["quantity_milli"], m["value_cents"]) == (sign * posting["quantity_milli"], sign * posting["value_cents"]), "采购库存原账方向／成本不符")
            if sign == -1:
                original = next(r for r in received if r["id"] == posting["receipt_id"])
                require(m["original_id"] == original["stock_move_id"], "采购退回未引用原收货库存")
            expected_details.append({"case_id": key, "store_id": sid, "number": origin["number"], "line_id": line["id"],
                "sku": line["sku"], "date": m["business_date"], "kind": "receive" if sign == 1 else "return",
                "label": "实际到货" if sign == 1 else "实际退货", "source_id": posting["id"], "stock_move_id": m["id"],
                "quantity_milli": m["quantity_milli"], "value_cents": m["value_cents"], "unit": line["unit"]})
    details = [d for d in data["details"] if d["case_id"] == key]
    require(len(details) == len(data["details"]) == len(receipts) + len(returns) == 5
        and {d["stock_move_id"] for d in details} == {r["stock_move_id"] for r in receipts + returns}, "累计收退原账缺行／重复")
    compare_rows(details, expected_details, "本次五笔累计到退货原账")
    legacy = [r for r in rows(e, "flow_cases", sid) if r["kind"] == "purchase" and inside(r["business_date"], src["period"])]
    require(len(legacy) == 4 and all(r["state"] == "completed" and r["flow_version"] == 2
        and r["business_date"] == datetime.now(ZONE).date().isoformat()
        and local_time(r["created_at"]).date().isoformat() == r["business_date"] for r in legacy),
        "局部观察需要确切本店当日四条原历史采购，不能接收任意来源缺口")
    expected_issues = [{"case_id": r["id"], "number": r["number"], "store_id": sid, "issue": LEGACY_PROCUREMENT_REASON} for r in legacy]
    compare_rows(data["issues"], expected_issues, "原历史四条来源差异")
    expected_table = [[src["store_name"], r["number"], LEGACY_PROCUREMENT_REASON] for r in legacy]
    compare_rows([r["values"] for r in data["tables"]["procurement_cohort_issues"]["rows"]], expected_table, "原历史差异明细")
    require({r["route"]["id"] for r in data["tables"]["procurement_cohort_issues"]["rows"]} == {r["id"] for r in legacy}, "历史差异原单路由错配")
    metrics = data["metrics"]
    require(data["complete"] is False and metrics["procurement_cohort_complete"] is False
        and metrics["procurement_cohort_order_count"] == 1 and metrics["procurement_cohort_line_count"] == 2
        and metrics["procurement_cohort_issue_count"] == 4, "全期间未知来源／新批数量不符合原实际来源")
    for state in QUANTITIES:
        require(metrics["procurement_cohort_" + state + "_cents"] is None, "历史缺源被冒充完整批次金额")
    require(data["charts"] == [] and set(data["tables"]) == {"procurement_cohort_lines", "procurement_cohort_postings", "procurement_cohort_issues"},
        "历史缺源时仍生成完整单位图或动态图明细")
    return {"purchase_order_id": key, "original_lines": lines, "receipts": receipts, "returns": returns,
        "whole_cohort_line_count": len(data["rows"]), "cumulative_as_of": data["as_of"], "legacy_source_cases": legacy,
        "exact_original_issues": expected_issues, "whole_metrics": metrics, "no_complete_business_check": True}


async def procurement_partial(e, cp, src):
    cp.start_partial("HK-153")
    before = e.business_snapshot("before_partial_procurement_source")
    data = await dedicated_report(e, "HK-153", "procurement-cohort", src["period"], "/api/inventory-reports/procurement", "物资采购订货统计")
    facts = procurement_facts(e, data, src)
    notice = e.page.locator("#main .notice.error").filter(has_text="存在来源差异或历史简表；不展示完整履约合计")
    await expect(notice).to_have_count(1)
    await expect(notice).to_be_visible()
    await expect(e.page.locator('#main svg[role="img"]')).to_have_count(0)
    await expect(e.page.locator('[data-act="inventory-report-export"][data-key^="procurement_cohort_unit_"]')).to_have_count(0)
    e.business_unchanged(before, "after_partial_procurement_source")
    shown, csv_files = [], []
    for key in ("procurement_cohort_lines", "procurement_cohort_postings", "procurement_cohort_issues"):
        shown.append(await verify_table(e, data, key, "procurement"))
        csv_files.append(await dedicated_export(e, src["actor"], data, key, "procurement", src["period"]))
    origin = one(e, "flow_cases", facts["purchase_order_id"], src["store_id"])
    row = next(r for r in data["tables"]["procurement_cohort_postings"]["rows"] if r["route"]["id"] == origin["id"])
    drill = await drill_original(e, data, "procurement_cohort_postings", row, "procurement", origin)
    await e.snapshot("hk-153-partial-not-business-check")
    cp.partial.update(status="partial", local_scope_status="observed_current_lines_postings_and_exact_legacy_gaps",
        evidence_action_end=len(e.actions), evidence={"original_api": data, "db_facts": facts, "all_pages": shown,
            "actual_csv": csv_files, "original_drill": drill, "incomplete_notice_visible": True, "complete_chart_visible": False,
            "experience": await experience(e), "no_complete_business_check": True},
        remaining_conditions=["全期间完整采购履约来源未闭合，四条历史简表保留未知",
            "完整全期间金额、各单位图、动态图原始行CSV均not_tested"])
    cp.save()
    cp.partial = None


def local_move_facts(e, data, src):
    sid = src["store_id"]
    docs = {d["id"]: d for d in rows(e, "warehouse_documents", sid) if d["operation"] == "local_move"}
    entries = [r for r in rows(e, "warehouse_entries", sid) if r["case_id"] in docs and inside(r["business_date"], src["period"])]
    balances = {b["id"]: b for b in rows(e, "warehouse_balances", sid)}
    items = {i["id"]: i for i in rows(e, "flow_items", sid)}
    locations = {l["id"]: l for l in rows(e, "master_locations", sid)}
    cases = {c["id"]: c for c in rows(e, "flow_cases", sid)}
    labels = {"local_dispatch": "实际发出", "local_accept": "实际接收", "local_return": "原库位实际退回", "average_revaluation": "移动平均价值分摊"}
    expected, daily = [], defaultdict(int)
    for r in entries:
        b = balances[r["balance_id"]]
        item = items[b["item_id"]]
        location = locations[b["location_id"]]["name"] if b["location_id"] else "在途 " + cases[b["transit_case_id"]]["number"]
        expected.append([cases[r["case_id"]]["number"], src["store_name"], r["business_date"], item["sku"], item["name"], location,
            labels.get(r["reason"], r["reason"]), qty(r["quantity_milli"]), item["unit"], yuan(r["value_cents"])])
        daily[r["business_date"]] += r["value_cents"]
    compare_rows([r["values"] for r in data["tables"]["warehouse_local_moves"]["rows"]], expected, "全期间店内移库")
    finite = set(src["material"]["primary"]["entry_ids"])
    own = [r for r in entries if r["id"] in finite]
    case_ids = {r["case_id"] for r in own}
    require(len(case_ids) == 1 and len(own) == 6, "本次移库配对原六行不齐")
    for key in case_ids:
        pair = [r for r in own if r["case_id"] == key]
        require(sum(r["quantity_milli"] for r in pair) == sum(r["value_cents"] for r in pair) == 0
            and docs[key]["quantity_milli"] == 2000
            and sorted(r["quantity_milli"] for r in pair if r["reason"] == "local_accept" and r["quantity_milli"] > 0) == [750, 1250]
            and all(r["stock_move_id"] is None for r in pair), "原库位／在途／目的配对不守恒或误造库存收发")
    c = chart_record(data, "warehouse_local_moves")
    require(dict(zip(c["labels"], c["series"][0]["values"])) == dict(daily), "移库全期间净图错误")
    row = next(r for r in data["tables"]["warehouse_local_moves"]["rows"] if r["route"]["id"] in case_ids)
    return row, {"finite_local_move_case_ids": sorted(case_ids), "original_paired_entries": own,
        "whole_scope_entries": len(entries), "whole_scope_daily_net_cents": dict(daily)}


async def warehouse_partial(e, cp, src):
    cp.start_partial("HK-152")
    before = e.business_snapshot("before_partial_warehouse_source")
    data = await dedicated_report(e, "HK-152", "warehouse-period", src["period"], "/api/inventory-reports/warehouses", "库位期间入出存")
    sid, given = src["store_id"], src["material"]["primary"]
    item = one(e, "flow_items", given["item_id"], sid)
    warehouse = one(e, "master_warehouses", given["warehouse_id"], sid)
    filters = {}
    for key, row, code in (("item_id", item, "sku"), ("warehouse_id", warehouse, "code")):
        filters[key] = row["id"]
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/inventory-reports/warehouses") as pending:
            await choose(e, e.page.locator("#warehouse-report-filters"), 'select[name="' + key + '"]', row[code], row[code] + " · " + row["name"], row["id"])
        response = await pending.value
        data = await response.json()
        await native_response(e, response, {**src["period"], **filters})
        await expect(e.page.locator("#main .loading")).to_have_count(0)
    selected = data["rows"]
    require(selected and all(r["item_id"] == item["id"] and r["warehouse_id"] == warehouse["id"] for r in selected), "局部仓库筛选串来源")
    require(data["complete"] is False and data["closing_complete"] is True
        and all(r["opening"] is None and r["in"] is None and r["out"] is None and r["closing"] is not None for r in selected), "当日桥接未知期初被冒充完整")
    balances = [b for b in rows(e, "warehouse_balances", sid) if b["item_id"] == item["id"]]
    require(sum(r["closing"]["quantity_milli"] for r in selected) == sum(b["quantity_milli"] for b in balances)
        and sum(r["closing"]["value_cents"] for r in selected) == sum(b["value_cents"] for b in balances) == item["inventory_value_cents"], "有据期末不能核对当前原库存")
    e.business_unchanged(before, "after_partial_warehouse_source")
    shown, csv_files = [], []
    for key in ("warehouse_period_balances", "warehouse_period_baselines", "warehouse_period_entries"):
        shown.append(await verify_table(e, data, key, "warehouses"))
        csv_files.append(await dedicated_export(e, src["actor"], data, key, "warehouses", src["period"], filters))
    graphic = await graph(e, data, "warehouse_period_closing")
    partial = cp.partial
    await e.snapshot("hk-152-partial-not-business-check")
    partial.update(status="partial", local_scope_status="observed_closing_and_unknown_opening", evidence={"original_api": data,
        "original_filters": filters, "current_item": item, "current_balances": balances, "all_pages": shown, "actual_csv": csv_files,
        "chart": graphic, "no_complete_business_check": True},
        remaining_conditions=["查询开始日严格晚于真实启用本地日的历史窗口尚未产生", "未改时钟或回填午夜期初"])
    cp.save()
    cp.partial = None


async def report_followon_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        fixture, src = source_facts(e, cp)
        # Authentication legitimately appends its original audit; baseline starts afterwards.
        actor = await login_as(e, context, credentials, fixture["manager_key"], "module/analytics", src["store_id"])
        src["actor"] = actor
        await flow_check(e, cp, src, "HK-146", "service_appointments", "repair", "service_appointments", appointments_facts)
        await flow_check(e, cp, src, "HK-147", "repairs", "repair", "repair_state", repair_facts)
        await flow_check(e, cp, src, "HK-148", "repair_projects", "repair", "repair_projects", projects_facts)
        await repair_material_check(e, cp, src)
        await flow_check(e, cp, src, "HK-150", "movements", "materials", "material_value", movement_facts, inbound=True)
        await flow_check(e, cp, src, "HK-151", "movements", "materials", "material_value", movement_facts, inbound=False)
        await procurement_partial(e, cp, src)
        await flow_check(e, cp, src, "HK-155", "warehouse_local_moves", "materials", "warehouse_local_moves", local_move_facts)
        cp.active = None
        await warehouse_partial(e, cp, src)
        cp.finish()
    except Exception as error:
        cp.failed(error)
        raise


REPORT_FOLLOWON_SCENARIOS = ((SCENARIO, report_followon_business, 720),)
