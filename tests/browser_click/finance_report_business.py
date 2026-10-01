"""Four native finance reports from passed business sources in this run.

Only original UI requests and downloads; SQL is read-only and no app is imported.
HK168/169 and empty receivable types earn no complete check in this candidate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime
from decimal import Decimal
import io
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from playwright.async_api import expect
from sales_business import login_as, require
from sales_order_business import fixed_dependency
from vehicle_purchase_business import nav, select_value
from finance_followon_business import batch_view, comparable, digest
from report_business import (click, write_json, sha, yuan, text, local_time,
    native_response, refresh_report, verify_table, safe_csv, assert_export_delta,
    export_csv, graph, drill_original, experience, first_page)


SCENARIO = "finance-reports-hk141-161-162-163"
INSURANCE = "insurance-renewal-hk013-014-077-113-114-115-116"
SALE = "sales-followon-hk012-015-016-017"
REPAIR = "repair-selfpay-hk031-034-044-049-053-079"
MATERIAL = "materials-hk069-045-054-083-070-072-073-051-061"
FINANCE = "finance-hk087-090-091-093-096"
SETTLEMENT = "finance-followon-hk095-097"
CONTRACTS = (("HK-141", "保险单分析", "analytics/sales"),
    ("HK-161", "物资收入成本对照表", "material-value"),
    ("HK-162", "预收款统计", "table/finance_advances"),
    ("HK-163", "财务结算统计", "reconciliation"))
ZONE = ZoneInfo("Asia/Shanghai")
MATERIAL_KEYS = ("material_goods", "material_services", "material_unallocated", "material_sources",
    "material_actual_stock", "material_other_stock", "material_unfulfilled")
SOURCE_NAMES = {"retail": "精品销售", "addon": "销售加装", "repair": "维修", "stock": "非履约库存变化"}
STOCK_NAMES = {"activation": "库位启用基准", "local_dispatch": "店内实际移出", "local_accept": "店内实际接收",
    "local_return": "店内拒收原退", "average_revaluation": "均价分摊调整", "wh_other_in": "其他实际入库",
    "wh_other_in_return": "其他入库原退", "wh_consumable": "耗材实际领用", "wh_consumable_return": "耗材原单退回",
    "wh_gift": "礼品实际发出", "wh_gift_return": "礼品原单退回", "wh_disposal": "物资实际处置",
    "wh_count": "盘点差异实际过账", "procurement_receipt": "采购实际验收", "procurement_return": "采购实际退回",
    "transfer_out": "跨店实际发出", "transfer_in": "跨店实际接收", "transfer_return": "跨店原退接收",
    "repair_issue_v3": "维修实际领料", "repair_return_v3": "维修原料退回", "retail_dispatch": "精品实际出库",
    "retail_return": "精品原单退货", "purchase": "原采购实际收货", "issue": "原物资实际领用",
    "return": "原物资退回", "count": "原盘点实际过账"}
TABLES = {"flow_cases", "flow_customers", "flow_items", "flow_stock_moves", "flow_accounts", "cash_entries",
    "flow_payment_links", "insurance_orders", "insurance_quotes", "insurance_submissions", "insurance_results",
    "insurance_commissions", "insurance_commission_reviews", "insurance_commission_payments", "insurance_tenders",
    "insurance_pass_entries", "insurance_direct_entries", "business_finance_advances", "business_finance_advance_entries",
    "business_finance_applications", "business_finance_stored_corrections", "business_finance_credit_links",
    "reconciliation_batches", "reconciliation_issues", "reconciliation_events", "reconciliation_receipts",
    "addon_quotes", "addon_lines", "addon_dispatches", "addon_acceptances", "addon_return_postings",
    "repair_quotes", "repair_lines", "repair_stock", "repair_settlements", "repair_allocations",
    "retail_lines", "retail_dispatches", "retail_return_postings", "aftercare_applications", "aftercare_adjustments",
    "claims_applications", "claims_responsibility_entries", "group_aftercare_holds", "benefit_entries",
    "benefit_wallets", "benefit_rules", "repair_package_payment_links", "repair_package_stock_returns",
    "repair_package_quote_snapshots", "retail_group_plans", "retail_group_tenders", "retail_group_units",
    "retail_group_allocations", "retail_group_captures", "retail_group_returns", "retail_group_return_parts", "group_entries"}
UNSCOPED_REFERENCES = {"benefit_wallets", "benefit_rules"}


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        catalog_file = Path(__file__).with_name("business_acceptance_catalog.json")
        self.digest = sha(catalog_file)
        bound = {r["id"]: r for r in json.loads(catalog_file.read_text(encoding="utf-8"))["requirements"]}
        for key, title, route in CONTRACTS:
            require(bound[key]["title"] == title and route in bound[key]["target_routes"]
                and bound[key]["source_review_status"] == "source_reviewed"
                and any(c["check_id"] == key + "-business" for c in bound[key]["acceptance_checks"]), key + " 原源合同错配")
        self.report = {"schema": 1, "scenario": SCENARIO, "complete": False, "passed": False,
            "scope": [r[0] for r in CONTRACTS], "business_accepted": False, "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "execution": "native_browser_original_reports",
            "source_contract_sha256": self.digest, "candidate_sha256": sha(Path(__file__)),
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "manual_review": {"simple_flow": "pending", "concise_copy": "pending"},
            "conditions": {"HK-168": "not_tested", "HK-169": "not_tested", "nonempty_receivables": "not_tested",
                "group_scope": "not_tested", "other_periods": "not_tested", "production_money_acceptance": False},
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"check_id": key + "-business", "status": "not_tested", "evidence": {}}]}
                for key, title, _ in CONTRACTS]}
        self.save()

    def save(self):
        write_json(self.path, self.report)

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        require(self.active["status"] == "not_tested", "不能覆盖已执行报表")
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active["evidence_action_start"] = len(self.e.actions)
        self.save()

    def note(self, **evidence):
        json.dumps(evidence, ensure_ascii=False)
        self.active["acceptance_checks"][0]["evidence"].update(evidence)
        self.save()

    async def passed(self, **evidence):
        self.note(**evidence)
        await self.e.snapshot(self.active["id"].lower() + "-report", business_ready=True)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.active = None
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.active["acceptance_checks"][0]["error"] = self.e.scrub(error)
        self.report.update(error=self.e.scrub(error),
            executed_requirements=sum(r["status"] != "not_tested" for r in self.report["requirements"]),
            passed_requirements=sum(r["status"] == "passed" for r in self.report["requirements"]))
        self.save()

    def finish(self):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "四报表未完整实际执行")
        self.report.update(complete=True, passed=True, executed_requirements=4, passed_requirements=4)
        self.save()
        self.e.observe("finance_report_original_checkpoint", {"path": str(self.path), "complete_checks": 4,
            "business_accepted": False, "human_acceptance": "pending", "full_193_business_acceptance": False})


def rows(e, table):
    require(table in TABLES - UNSCOPED_REFERENCES, "读取表不在本轮原来源白名单")
    found = e.db.rows(f"SELECT * FROM {table} WHERE store_id=1 ORDER BY id LIMIT 25001")
    require(len(found) <= 25000, "报表来源超限，不能截断")
    return found


def one(e, table, key):
    require(table in TABLES and type(key) is int and key > 0, "原来源表或明确ID非法")
    scope = "" if table in UNSCOPED_REFERENCES else " AND store_id=1"
    found = e.db.rows(f"SELECT * FROM {table} WHERE id=?" + scope, (key,))
    require(len(found) == 1, "本店明确原来源不存在：" + table)
    return found[0]


def case(e, key):
    found = one(e, "flow_cases", key)
    found["data"] = json.loads(found["data"])
    return found


def compare(actual, expected, label):
    encode = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True)
    require(Counter(map(encode, actual)) == Counter(map(encode, expected)), label + " 全部原行与DB不一致")


def inside(day, period):
    return period["date_from"] <= day <= period["date_to"]


def quantity(value):
    return format(Decimal(value) / 1000, "f")


def source_facts(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "只允许本轮外置合成实例")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "数据库不是本轮外置runtime")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance.get("snapshot_stable") is True, "源码镜像未冻结")
    for name in ("finance_report_business.py", "report_business.py", "sales_business.py", "sales_order_business.py",
        "vehicle_purchase_business.py", "sales_followon_business.py", "material_business.py", "repair_business.py",
        "finance_business.py", "finance_followon_business.py", "insurance_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name)), "同次脚本指纹变化：" + name)
    prior = {name: fixed_dependency(e, cp, name) for name in (INSURANCE, SALE, REPAIR, MATERIAL, FINANCE, SETTLEMENT)}
    fixture = e.manifest["business_fixtures"]["repair"]
    require(fixture["store_id"] == 1, "原报表只验证本次明确店")
    actor = e.manifest["users"][fixture["manager_key"]]
    require(actor["role"] == "manager" and e.db.rows("SELECT role FROM user_stores WHERE user_id=? AND store_id=1", (actor["id"],)) == [{"role": "manager"}], "原查询员工不是本店主管")
    insurance = prior[INSURANCE]["report_sources"]
    insured = [case(e, insurance[k]) for k in ("first_insurance_case_id", "new_insurance_case_id")]
    results = [one(e, "insurance_results", insurance[k]) for k in ("first_issued_result_id", "new_issued_result_id")]
    require(insured[0]["id"] != insured[1]["id"] and all(c["kind"] == "insurance" and c["flow_version"] == 3
        and c["customer_id"] == insurance["customer_id"] for c in insured)
        and all(r["outcome"] == "issued" and r["case_id"] == c["id"] for r, c in zip(results, insured)), "本次两保单来源不真实或串单")
    sale = prior[SALE]["report_sources"]
    addon = case(e, sale["addon_case_id"])
    repair_refs = prior[REPAIR]["report_sources"]
    repair = case(e, repair_refs["repair_case_id"])
    require(addon["kind"] == "addon" and addon["flow_version"] == 3 and addon["state"] == "completed"
        and repair["kind"] == "repair" and repair["flow_version"] == 4 and repair["state"] == "completed"
        and repair["data"].get("released_date"), "本次加装/维修未实际履约")
    material = prior[MATERIAL]["material_sources"]
    require(set(material) == {"primary", "secondary"} and material["primary"]["item_id"] == repair_refs["material_item_id"], "原维修与物资有限源错配")
    moves = []
    for given in material.values():
        require(given["stock_move_ids"] and given["receipt_ids"], "原物资有限采购来源缺失")
        moves.extend(one(e, "flow_stock_moves", key) for key in given["stock_move_ids"])
    finance = prior[FINANCE]["finance_sources"]
    advance = one(e, "business_finance_advances", finance["advance_id"])
    entries = [r for r in rows(e, "business_finance_advance_entries") if r["advance_id"] == advance["id"]]
    require(advance["initial_cents"] == 10000 and advance["correction_cents"] == -1000
        and advance["balance_cents"] == advance["reserved_cents"] == 0
        and [(r["purpose"], r["amount_cents"]) for r in entries] == [("receive", 10000), ("correction", -1000), ("apply", -4000), ("refund", -5000)], "原预收更正/抵用/退款四事实缺失")
    correction = one(e, "business_finance_stored_corrections", finance["stored_correction_id"])
    credit = one(e, "business_finance_credit_links", finance["credit_link_id"])
    require(correction["original_cash_id"] == finance["original_advance_cash_id"] and correction["corrected_cash_id"] == finance["corrected_cash_id"]
        and credit["amount_cents"] == 4000 and credit["entry_id"] == entries[2]["id"] and entries[-1]["cash_id"] == finance["refund_cash_id"], "原预收款/非现金抵用/实退关联错误")
    settlement = prior[SETTLEMENT]["finance_followon_sources"]
    batches = [one(e, "reconciliation_batches", key) for key in settlement["reconciliation_batch_ids"]]
    require(len(batches) == 3 and [b["revision"] for b in batches] == [1, 2, 3]
        and [b["status"] for b in batches] == ["superseded", "sealed", "sealed"]
        and batches[1]["previous_id"] == batches[0]["id"] and batches[2]["previous_id"] == batches[1]["id"]
        and settlement["definition_version"] == 22 and settlement["cash_definition_version"] == 7, "原三版核账尚未独立完成")
    issue = one(e, "reconciliation_issues", settlement["issue_id"])
    require(issue["batch_id"] == batches[1]["id"] and issue["status"] == "resolved"
        and issue["evidence_id"] and issue["resolution_evidence_id"], "原逐项差异未留真实处理")
    dates = [r["business_date"] for r in results + moves] + [repair["data"]["released_date"], addon["completed_date"]]
    dates += [one(e, "cash_entries", r["cash_id"])["business_date"] if r["cash_id"] else local_time(r["occurred_at"]).date().isoformat() for r in entries]
    dates += [r["business_date"] for r in rows(e, "insurance_commission_reviews") + rows(e, "insurance_commission_payments")]
    period = {"date_from": min(dates), "date_to": max(dates)}
    require(period["date_to"] <= datetime.now(ZONE).date().isoformat(), "真实来源还在未来，不能造查询期间")
    result = {"store_id": 1, "store_name": next(s["name"] for s in e.manifest["stores"] if s["id"] == 1),
        "manager_key": fixture["manager_key"], "actor": actor, "insurance": insurance, "insured_cases": insured,
        "issued_results": results, "sale": sale, "addon": addon, "repair_refs": repair_refs, "repair": repair,
        "material": material, "finance": finance, "advance": advance, "advance_entries": entries,
        "settlement": settlement, "batch_ids": [b["id"] for b in batches], "issue": issue, "period": period}
    cp.report["mirror"] = {"provenance_sha256": sha(root / "provenance.json"), "source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"]}
    cp.report["source_preconditions"] = result
    cp.save()
    return result


async def entry(e, key, route, title, path, period=None):
    before = e.business_snapshot("finance_report_before_original_entry")
    await nav(e, "module/analytics", "统计分析", None)
    await e.fill("#mux-query", key, "检索本项原财务统计需求")
    button = e.page.locator('[data-mux-open="wf-report-' + key.split("-")[1] + '"]')
    if period is None:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
            await click(e, button, "进入" + key + "原统计入口")
        response = await pending.value
        data = await response.json()
        await native_response(e, response, {})
    else:
        await click(e, button, "进入" + key + "原统计入口")
        await expect(e.page.locator("#datefilters")).to_be_visible()
        data = await refresh_report(e, path, period)
    await expect(e.page).to_have_url(re.compile("#" + re.escape(route) + "$"))
    await expect(e.page.locator("#main h1")).to_have_text(title)
    await expect(e.page.locator("#main .notice.error, #main [role=alert]")).to_have_count(0)
    await expect(e.page.locator("#store")).to_have_value("1")
    e.business_unchanged(before, "finance_report_after_original_entry")
    return data


async def flow_table(e, data, key):
    before = e.business_snapshot("finance_report_before_cached_table")
    chart = next((c for c in data["charts"] if c["table"] == key), None)
    parent = e.page.locator("#main .chartpanel").filter(has=e.page.get_by_role("heading", name=chart["title"], exact=True)) if chart else e.page.locator("#main > section.panel").filter(has=e.page.get_by_role("heading", name=data["tables"][key]["title"], exact=True))
    await click(e, parent.locator('.panelhead [data-act="charttable"][data-table="' + key + '"]'), "进入原" + data["tables"][key]["title"] + "完整明细")
    await expect(e.page).to_have_url(re.compile("#table/" + re.escape(key) + "$"))
    await expect(e.page.locator("#main h1")).to_have_text(data["tables"][key]["title"])
    e.business_unchanged(before, "finance_report_after_cached_table")


async def finance_chart_page(e, section, period):
    before = e.business_snapshot("finance_report_before_chart_return")
    await click(e, e.page.locator('[data-act="open"][data-route="analytics/overview"]'), "返回原可视化范围")
    await expect(e.page.locator("#main h1")).to_have_text("数据可视化")
    await click(e, e.page.locator('.tabs a[href="#analytics/' + section + '"]'), "切换原统计分类")
    await expect(e.page).to_have_url(re.compile("#analytics/" + section + "$"))
    await expect(e.page.locator('#datefilters [name="date_from"]')).to_have_value(period["date_from"])
    await expect(e.page.locator('#datefilters [name="date_to"]')).to_have_value(period["date_to"])
    e.business_unchanged(before, "finance_report_after_chart_return")


def table_chart(data, key, index, *, costs=False):
    chart = [c for c in data["charts"] if c["id"] == key]
    require(len(chart) == 1, "原图缺失或重复")
    totals, cost = defaultdict(int), defaultdict(int)
    for row in data["tables"][key]["rows"]:
        label = row["values"][index]
        totals[label] += row["amount_cents"]
        cost[label] += row.get("cost_cents", 0)
    labels = sorted(totals)
    series = [{"name": "金额", "values": [totals[label] for label in labels]}]
    if costs:
        series.append({"name": "直接材料成本", "values": [cost[label] for label in labels]})
    require(chart[0]["labels"] == labels and chart[0]["series"] == series and chart[0]["table"] == key
        and chart[0]["unit"] == "cents", "原图完整范围与原明细整数分不一致")


def insurance_facts(e, data, src):
    cases = {r["id"]: case(e, r["id"]) for r in rows(e, "flow_cases")}
    quotes = {r["id"]: r for r in rows(e, "insurance_quotes")}
    submits = {r["id"]: r for r in rows(e, "insurance_submissions")}
    confirmations = {r["id"]: r for r in rows(e, "insurance_commissions")}
    expected = {k: [] for k in ("insurance_policy_facts", "insurance_commission_facts", "insurance_commission_cash")}
    for result in rows(e, "insurance_results"):
        if result["outcome"] != "issued" or not inside(result["business_date"], src["period"]):
            continue
        c = cases[result["case_id"]]
        quote = quotes[submits[result["submission_id"]]["quote_id"]]
        require(quote["case_id"] == c["id"] and result["insurer_id"] == quote["insurer_id"], "出保引用了另一原报价")
        expected["insurance_policy_facts"].append({"values": [c["number"], src["store_name"], result["business_date"], json.loads(quote["insurer_snapshot"])["name"], result["policy_number"], yuan(quote["premium_cents"]), "门店代收代缴" if quote["collection_mode"] == "store_collect" else "客户直付保险公司"],
            "route": {"type": "case", "id": c["id"]}, "premium_cents": quote["premium_cents"], "policy_count": 1, "fact_id": result["id"]})
    for review in rows(e, "insurance_commission_reviews"):
        if review["decision"] != "approved" or not inside(review["business_date"], src["period"]):
            continue
        fact = confirmations[review["confirmation_id"]]
        c = cases[fact["case_id"]]
        quote = quotes[c["data"]["insurance_quote_id"]]
        require(review["actor_id"] != fact["actor_id"], "佣金确认不是独立原批准")
        amount = fact["target_cents"] - fact["previous_cents"]
        expected["insurance_commission_facts"].append({"values": [c["number"], src["store_name"], review["business_date"], json.loads(quote["insurer_snapshot"])["name"], fact["revision"], yuan(fact["target_cents"]), yuan(amount)],
            "route": {"type": "case", "id": c["id"]}, "amount_cents": amount, "source_kind": "insurance", "fact_kind": "commission_review", "fact_id": review["id"]})
    payments = rows(e, "insurance_commission_payments")
    for paid in payments:
        if not inside(paid["business_date"], src["period"]):
            continue
        c = cases[paid["case_id"]]
        quote = quotes[c["data"]["insurance_quote_id"]]
        cash = one(e, "cash_entries", paid["cash_id"])
        require(cash["approval_state"] == "approved" and cash["amount_cents"] == paid["amount_cents"]
            and cash["direction"] == paid["direction"] and cash["business_date"] == paid["business_date"], "佣金实际账不是唯一原Cash")
        amount = paid["amount_cents"] * (1 if paid["direction"] == "in" else -1)
        expected["insurance_commission_cash"].append({"values": [c["number"], src["store_name"], paid["business_date"], json.loads(quote["insurer_snapshot"])["name"], "到账" if paid["direction"] == "in" else "原佣金退回", yuan(amount)],
            "route": {"type": "case", "id": c["id"]}, "amount_cents": amount, "cash_id": paid["cash_id"], "fact_id": paid["id"]})
    for key, wanted in expected.items():
        require(wanted, "保险三种原来源不得为空：" + key)
        compare(data["tables"][key]["rows"], wanted, key)
    for key in ("insurance_commission_facts", "insurance_commission_cash"):
        table_chart(data, key, 3)
    require(data["metrics"]["insurance_issued_count"] == len(expected["insurance_policy_facts"])
        and data["metrics"]["insurance_issued_premium_cents"] == sum(r["premium_cents"] for r in expected["insurance_policy_facts"])
        and data["metrics"]["insurance_confirmed_commission_delta_cents"] == sum(r["amount_cents"] for r in expected["insurance_commission_facts"])
        and data["metrics"]["insurance_commission_actual_net_cents"] == sum(r["amount_cents"] for r in expected["insurance_commission_cash"]), "保险整范围统计误计预计佣金或保费现金")
    own = [p for p in payments if p["case_id"] == src["insurance"]["first_insurance_case_id"]]
    require(len(own) == 2 and [(p["direction"], p["amount_cents"]) for p in own] == [("in", 1200), ("out", 1200)]
        and own[1]["original_id"] == own[0]["id"] and own[0]["account_id"] == own[1]["account_id"] == src["insurance"]["account_id"], "本轮真实佣金收退来源不完整")
    require({r["id"] for r in src["issued_results"]} <= {r["fact_id"] for r in expected["insurance_policy_facts"]}, "两本轮出保事实未纳入期间")
    return {"db_row_counts": {k: len(v) for k, v in expected.items()}, "original_commission_payment_ids": [p["id"] for p in own],
        "same_run_commission_net_cents": 0, "policy_table_has_no_invented_chart": True}


def advance_facts(e, data, src):
    advances = {r["id"]: r for r in rows(e, "business_finance_advances")}
    expected_current, expected_entries = [], []
    labels = {"receive": "原登记收到预收款", "apply": "批准抵用原业务", "refund": "未用原款实际退款",
        "return": "原抵用回退余额", "correction": "误记更正本金差额（非实际收退款）"}
    ledger = rows(e, "business_finance_advance_entries")
    for a in advances.values():
        original, customer = case(e, a["case_id"]), one(e, "flow_customers", a["customer_id"])
        require(sum(r["amount_cents"] for r in ledger if r["advance_id"] == a["id"]) == a["balance_cents"], "原预收余额与逐事实流水不守恒")
        holds = [r for r in rows(e, "business_finance_applications") if r["advance_id"] == a["id"] and r["status"] == "reserved"]
        require(sum(r["amount_cents"] for r in holds) == a["reserved_cents"], "预收批准占額不符")
        expected_current.append({"values": [original["number"], src["store_name"], customer["name"], yuan(a["initial_cents"]), yuan(a["balance_cents"]), yuan(a["reserved_cents"]), yuan(a["balance_cents"] - a["reserved_cents"]), yuan(a["correction_cents"]), yuan(a["initial_cents"] + a["correction_cents"])], "route": {"type": "case", "id": a["case_id"]}, "amount_cents": a["balance_cents"]})
    for r in ledger:
        stamp = one(e, "cash_entries", r["cash_id"])["business_date"] if r["cash_id"] else local_time(r["occurred_at"]).date().isoformat()
        if not inside(stamp, src["period"]):
            continue
        a, original = advances[r["advance_id"]], case(e, r["case_id"])
        customer = one(e, "flow_customers", a["customer_id"])
        expected_entries.append({"values": [original["number"], src["store_name"], stamp, customer["name"], labels[r["purpose"]], yuan(r["amount_cents"])], "route": {"type": "case", "id": r["case_id"]}, "amount_cents": r["amount_cents"]})
    require(expected_current and expected_entries, "原预收和期间事实不能为空")
    compare(data["tables"]["finance_advances"]["rows"], expected_current, "预收当前原账")
    compare(data["tables"]["finance_advance_movements"]["rows"], expected_entries, "预收期间原流水")
    for key in ("finance_advances", "finance_advance_movements"):
        table_chart(data, key, 1)
    require(data["metrics"]["business_finance_advance_balance_cents"] == sum(r["amount_cents"] for r in expected_current), "预收指标不是当前实际余额")
    return {"db_advances": len(expected_current), "period_entries": len(expected_entries), "same_run_advance_id": src["advance"]["id"],
        "same_run_ledger": [(r["purpose"], r["amount_cents"]) for r in src["advance_entries"]], "zero_balance_has_nonempty_sources": True,
        "nonzero_hold_branch": "not_tested", "current_balance_is_not_historical_period_balance": True}


def material_facts(e, data, src, filters):
    """Read frozen prices/acceptance and actual stock independently of the UI JSON."""
    require(data["complete"] is True and data["definition_version"] == 1 and set(data["tables"]) == set(MATERIAL_KEYS)
        and data["filters"] == {k: filters.get(k) for k in ("source", "item_id", "case_id")}, "实际成本范围或完整性不符")
    allcases = {r["id"]: case(e, r["id"]) for r in rows(e, "flow_cases")}
    items = {r["id"]: r for r in rows(e, "flow_items")}
    moves = {r["id"]: r for r in rows(e, "flow_stock_moves")}
    selected = {key: c for key, c in allcases.items() if ((c["kind"] == "retail" and c["flow_version"] == 2)
        or (c["kind"] == "addon" and c["flow_version"] == 3) or (c["kind"] == "repair" and c["flow_version"] in (3, 4)))
        and (not filters.get("source") or c["kind"] == filters["source"])
        and (not filters.get("case_id") or key == filters["case_id"])}
    facts, physical, source_items = [], {}, defaultdict(set)
    expected_net = defaultdict(int)

    def emit(c, day, category, label, table, source_id, amount, cost=0, line=None, qty=0):
        require(day and type(amount) is int and type(cost) is int, "物资履约日期/原价/成本未知，不能造0")
        item = line.get("item_id") if line and category == "goods" else None
        if item:
            source_items[c["id"]].add(item)
        facts.append({"case_id": c["id"], "store_id": 1, "source": c["kind"], "business_date": day,
            "category": category, "kind": label, "source_table": table, "source_id": source_id,
            "line_id": line["id"] if line else None, "item_id": item,
            "code": (line.get("sku", line.get("code", "")) if category == "goods" else line.get("work_code", line.get("code", ""))) if line else "",
            "name": (line.get("name", "") if category == "goods" else line.get("work_name", line.get("name", ""))) if line else "",
            "unit": line.get("unit", "") if line and category == "goods" else "", "quantity_milli": qty,
            "amount_cents": amount, "cost_cents": cost})

    def stock(move_id, c, item, qty, cost):
        move = moves[move_id]
        require(move["case_id"] == c["id"] and move["item_id"] == item and move["store_id"] == 1
            and type(move["value_cents"]) is int and (move["quantity_milli"], move["value_cents"]) == (-qty, -cost)
            and move_id not in physical, "原库存数量成本/原单不一致或重复归属")
        physical[move_id] = c["id"]
        source_items[c["id"]].add(item)

    retail_lines = {r["id"]: r for r in rows(e, "retail_lines") if r["case_id"] in selected}
    retail_dispatch = {r["id"]: r for r in rows(e, "retail_dispatches") if r["case_id"] in selected}
    retail_returns = [r for r in rows(e, "retail_return_postings") if r["case_id"] in selected]
    for d in retail_dispatch.values():
        stock(d["stock_move_id"], selected[d["case_id"]], retail_lines[d["line_id"]]["item_id"], d["quantity_milli"], d["value_cents"])
    for r in retail_returns:
        stock(r["stock_move_id"], selected[r["case_id"]], retail_lines[retail_dispatch[r["dispatch_id"]]["line_id"]]["item_id"], -r["quantity_milli"], -r["value_cents"])
    for line in retail_lines.values():
        c = selected[line["case_id"]]
        source_items[c["id"]].add(line["item_id"])
        day = c["data"].get("accepted_date")
        if not day:
            continue
        dispatched = [d for d in retail_dispatch.values() if d["line_id"] == line["id"]]
        require(len(dispatched) == 1, "已接收原精品缺唯一逐行实际出库")
        d = dispatched[0]
        returns = [r for r in retail_returns if r["dispatch_id"] == d["id"]]
        prior = [r for r in returns if moves[r["stock_move_id"]]["business_date"] <= day]
        emit(c, day, "goods", "客户接收", "retail_lines", line["id"], line["goods_cents"] - sum(r["goods_cents"] for r in prior),
            d["value_cents"] - sum(r["value_cents"] for r in prior), line, line["quantity_milli"] - sum(r["quantity_milli"] for r in prior))
        if line["installation_cents"]:
            emit(c, day, "service", "安装履约及保留费", "retail_lines", line["id"], line["installation_cents"] - sum(r["installation_cents"] - r["retained_cents"] for r in prior), line=line)
        for r in returns:
            if r in prior:
                continue
            stamp = moves[r["stock_move_id"]]["business_date"]
            emit(c, stamp, "goods", "原单退货", "retail_return_postings", r["id"], -r["goods_cents"], -r["value_cents"], line, -r["quantity_milli"])
            if r["installation_cents"]:
                emit(c, stamp, "service", "原安装退款（扣除保留费）", "retail_return_postings", r["id"], -r["installation_cents"] + r["retained_cents"], line=line)
    for c in selected.values():
        if c["kind"] == "retail" and c["data"].get("accepted_date"):
            expected_net[c["id"]] = c["amount_cents"] - sum(r["goods_cents"] + r["installation_cents"] - r["retained_cents"] for r in retail_returns if r["case_id"] == c["id"])
    # Existing same-store background C/P is read, never a member acceptance.
    plans = {r["id"]: r for r in rows(e, "retail_group_plans") if r["case_id"] in selected}
    tenders = {r["id"]: r for r in rows(e, "retail_group_tenders") if r["plan_id"] in plans}
    units = {r["id"]: r for r in rows(e, "retail_group_units") if r["tender_id"] in tenders}
    allocations = {r["id"]: r for r in rows(e, "retail_group_allocations") if r["unit_id"] in units}
    captures = {r["tender_id"]: r for r in rows(e, "retail_group_captures") if r["tender_id"] in tenders}
    for a in allocations.values():
        tender = tenders[units[a["unit_id"]]["tender_id"]]
        captured = captures.get(tender["id"])
        if not captured or a["credit_cents"] == a["consideration_cents"]:
            continue
        original = one(e, "group_entries" if captured["principal_id"] else "benefit_entries", captured["principal_id"] or captured["benefit_id"])
        c = selected[plans[tender["plan_id"]]["case_id"]]
        require(original["case_id"] == c["id"], "原集团履约流水串单")
        amount = a["consideration_cents"] - a["credit_cents"]
        emit(c, local_time(original["occurred_at"]).date().isoformat(), "goods" if a["component"] == "goods" else "service", "原集团核销履约优惠", "retail_group_allocations", a["id"], amount, line=retail_lines[a["line_id"]])
        expected_net[c["id"]] += amount
    returned_group = {r["id"]: r for r in rows(e, "retail_group_returns") if r["plan_id"] in plans}
    retail_returns_byid = {r["id"]: r for r in retail_returns}
    for part in rows(e, "retail_group_return_parts"):
        if part["return_id"] not in returned_group or not part["capture_id"] or part["credit_cents"] == part["consideration_cents"]:
            continue
        a = allocations[part["allocation_id"]]
        posting = retail_returns_byid[returned_group[part["return_id"]]["posting_id"]]
        c = selected[posting["case_id"]]
        amount = part["credit_cents"] - part["consideration_cents"]
        emit(c, moves[posting["stock_move_id"]]["business_date"], "goods" if a["component"] == "goods" else "service", "原实退对应优惠冲回", "retail_group_return_parts", part["id"], amount, line=retail_lines[a["line_id"]])
        expected_net[c["id"]] += amount

    addon_quotes = {r["id"]: r for r in rows(e, "addon_quotes") if r["case_id"] in selected}
    addon_lines = {r["id"]: r for r in rows(e, "addon_lines") if r["quote_id"] in addon_quotes}
    addon_dispatch = [r for r in rows(e, "addon_dispatches") if r["case_id"] in selected]
    addon_returns = [r for r in rows(e, "addon_return_postings") if r["case_id"] in selected]
    for d in addon_dispatch:
        stock(d["stock_move_id"], selected[d["case_id"]], addon_lines[d["line_id"]]["item_id"], d["quantity_milli"], d["value_cents"])
    for r in addon_returns:
        if r["stock_move_id"]:
            stock(r["stock_move_id"], selected[r["case_id"]], addon_lines[r["line_id"]]["item_id"], -r["quantity_milli"], -r["value_cents"])
    seen = defaultdict(set)
    for accepted in rows(e, "addon_acceptances"):
        if accepted["case_id"] not in selected:
            continue
        c = selected[accepted["case_id"]]
        lines = [l for l in addon_lines.values() if l["quote_id"] == accepted["quote_id"]]
        before_count = len(facts)
        for line in lines:
            source_items[c["id"]].add(line["item_id"])
            if line["line_key"] in seen[c["id"]]:
                continue
            seen[c["id"]].add(line["line_key"])
            prior = [r for r in addon_returns if r["case_id"] == c["id"] and r["line_key"] == line["line_key"] and r["acceptance_id"] is None]
            cost = sum(d["value_cents"] for d in addon_dispatch if d["case_id"] == c["id"] and d["line_key"] == line["line_key"]) - sum(r["value_cents"] for r in prior)
            emit(c, accepted["business_date"], "goods", "本版实际验收", "addon_acceptances", accepted["id"], line["goods_cents"] - sum(r["goods_cents"] for r in prior), cost, line, line["quantity_milli"] - sum(r["quantity_milli"] for r in prior))
            emit(c, accepted["business_date"], "service", "本版安装履约及保留费", "addon_acceptances", accepted["id"], line["installation_cents"] - sum(r["installation_cents"] - r["retained_cents"] for r in prior), line=line)
        require(sum(f["amount_cents"] for f in facts[before_count:]) == accepted["amount_cents"] and sum(f["cost_cents"] for f in facts[before_count:]) == accepted["value_cents"], "加装实际验收与原冻结商品/作业不守恒")
        expected_net[c["id"]] += accepted["amount_cents"]
    for r in addon_returns:
        if not r["acceptance_id"]:
            continue
        c, line = selected[r["case_id"]], addon_lines[r["line_id"]]
        emit(c, r["business_date"], "goods", "已验收原商品退回", "addon_return_postings", r["id"], -r["goods_cents"], -r["value_cents"], line, -r["quantity_milli"])
        emit(c, r["business_date"], "service", "原安装退款（扣除保留费）", "addon_return_postings", r["id"], -r["installation_cents"] + r["retained_cents"], line=line)
        expected_net[c["id"]] -= r["goods_cents"] + r["installation_cents"] - r["retained_cents"]

    repair_quotes = {r["id"]: r for r in rows(e, "repair_quotes") if r["case_id"] in selected}
    repair_lines = [r for r in rows(e, "repair_lines") if r["quote_id"] in repair_quotes]
    repair_stock = [r for r in rows(e, "repair_stock") if r["case_id"] in selected]
    require(not [r for r in rows(e, "repair_package_stock_returns") if r["stock_fact_id"] in {s["id"] for s in repair_stock}]
        and not [r for r in rows(e, "repair_package_quote_snapshots") if r["quote_id"] in repair_quotes and repair_quotes[r["quote_id"]]["purpose"] == "stop"], "本批原来源出现未覆盖的套餐停工/原退成本分支，不能假验")
    repair_cost = defaultdict(int)
    for s in repair_stock:
        line = [l for l in repair_lines if l["quote_id"] == s["quote_id"] and l["line_key"] == s["line_key"]]
        require(len(line) == 1, "原领料找不到唯一冻结行")
        stock(s["stock_move_id"], selected[s["case_id"]], line[0]["item_id"], s["quantity_milli"], s["value_cents"])
        repair_cost[(s["case_id"], s["line_key"])] += s["value_cents"]
    discounts = defaultdict(int)
    for b in rows(e, "benefit_entries"):
        if b["case_id"] not in selected:
            continue
        wallet = one(e, "benefit_wallets", b["wallet_id"])
        rule = one(e, "benefit_rules", wallet["rule_id"])
        signed_units = -b["units"] if b["purpose"] in ("capture", "reverse") else 0
        recognized = signed_units * rule["sale_cents_per_unit"] if wallet["source_kind"] == "purchase" else 0
        discounts[b["case_id"]] += b["credit_cents"] - recognized
    for h in rows(e, "group_aftercare_holds"):
        if h["status"] == "applied" and h["source_case_id"] in selected:
            discounts[h["source_case_id"]] += h["discount_cents"]
    package_discount = defaultdict(int)
    for p in rows(e, "repair_package_payment_links"):
        if p["purpose"] == "capture" and p["case_id"] in selected:
            package_discount[p["case_id"]] += p["amount_cents"] - p["recognized_cents"]
    allocations = rows(e, "repair_allocations")
    for settlement in rows(e, "repair_settlements"):
        c = selected.get(settlement["case_id"])
        if not c or not c["data"].get("released_date"):
            continue
        q, day = repair_quotes[settlement["quote_id"]], c["data"]["released_date"]
        if q["purpose"] == "stop":
            require(not any(value for (cid, _), value in repair_cost.items() if cid == c["id"]), "停工原料未全退")
            emit(c, day, "service", "客户授权停工保留费", "repair_quotes", q["id"], q["amount_cents"])
        else:
            consumed_keys = set()
            for line in (l for l in repair_lines if l["quote_id"] == q["id"]):
                if line["kind"] == "part":
                    consumed_keys.add(line["line_key"])
                    emit(c, day, "goods", "维修实际交车", "repair_lines", line["id"], line["amount_cents"], repair_cost[(c["id"], line["line_key"])], line, line["quantity_milli"])
                else:
                    emit(c, day, "service", "维修作业履约", "repair_lines", line["id"], line["amount_cents"], line=line)
            require(not any(v and key not in consumed_keys for (cid, key), v in repair_cost.items() if cid == c["id"]), "实际消耗缺最终原行")
        internal = sum(a["amount_cents"] for a in allocations if a["case_id"] == c["id"] and a["payer_type"] == "internal")
        for label, amount in (("原整单内部承担（未分配商品）", internal), ("会员对外优惠（未分配商品）", discounts[c["id"]]), ("套餐原面值与实付对价差额（未分配商品）", package_discount[c["id"]])):
            if amount:
                emit(c, day, "unallocated", label, "repair_settlements", settlement["id"], -amount)
        expected_net[c["id"]] = sum(a["amount_cents"] for a in allocations if a["case_id"] == c["id"] and a["payer_type"] != "internal") - discounts[c["id"]] - package_discount[c["id"]]
    for a in rows(e, "aftercare_adjustments"):
        c = selected.get(a["source_case_id"])
        if c and c["kind"] == "repair" and c["data"].get("released_date"):
            emit(c, one(e, "aftercare_applications", a["application_id"])["business_date"], "unallocated", "原单售后减免（未分配商品）", "aftercare_adjustments", a["id"], -a["revenue_credit_cents"])
            expected_net[c["id"]] -= a["revenue_credit_cents"]
    for a in rows(e, "claims_responsibility_entries"):
        c = selected.get(a["source_case_id"])
        if c and c["kind"] == "repair" and c["data"].get("released_date") and a["payer_type"] != "internal":
            day = max(one(e, "claims_applications", a["application_id"])["business_date"], c["data"]["released_date"])
            emit(c, day, "unallocated", "原维修核赔责任调整（未分配商品）", "claims_responsibility_entries", a["id"], a["amount_cents"])
            expected_net[c["id"]] += a["amount_cents"]

    wanted = {key: [] for key in MATERIAL_KEYS}
    related = {key for key in selected if not filters.get("item_id") or filters["item_id"] in source_items[key]}
    all_amount, recognized, summary = defaultdict(int), defaultdict(int), defaultdict(lambda: defaultdict(int))
    for f in facts:
        all_amount[f["case_id"]] += f["amount_cents"]
        if f["category"] == "goods":
            recognized[(f["case_id"], f["item_id"])] += f["cost_cents"]
        if f["case_id"] not in related or not inside(f["business_date"], src["period"]):
            continue
        s = summary[f["case_id"]]
        s[f["category"]] += f["amount_cents"]
        s["cost"] += f["cost_cents"]
        if f["category"] == "goods" and filters.get("item_id") and f["item_id"] != filters["item_id"]:
            continue
        c = selected[f["case_id"]]
        values = [c["number"], src["store_name"], SOURCE_NAMES[c["kind"]], f["business_date"], f["kind"]]
        if f["category"] == "goods":
            values += [f["code"], f["name"], f["unit"], quantity(f["quantity_milli"]), yuan(f["amount_cents"]), yuan(f["cost_cents"])]
        elif f["category"] == "service":
            values += [f["code"], f["name"], yuan(f["amount_cents"])]
        else:
            values += [yuan(f["amount_cents"])]
        wanted[{"goods": "material_goods", "service": "material_services", "unallocated": "material_unallocated"}[f["category"]]].append({**f, "values": values, "route": {"type": "case", "id": c["id"]}})
    require(all(all_amount[key] == expected_net[key] for key in selected), "原商品/服务/承担调整不等于独立原对外金额")
    for key, s in sorted(summary.items()):
        c = selected[key]
        amount = s["goods"] + s["service"] + s["unallocated"]
        wanted["material_sources"].append({"values": [c["number"], src["store_name"], SOURCE_NAMES[c["kind"]], yuan(s["goods"]), yuan(s["service"]), yuan(s["unallocated"]), yuan(amount), yuan(s["cost"])], "case_id": key, "amount_cents": amount, "goods_cents": s["goods"], "service_cents": s["service"], "unallocated_cents": s["unallocated"], "cost_cents": s["cost"], "route": {"type": "case", "id": key}})
    commercial = {r["stock_move_id"] for table in ("retail_dispatches", "retail_return_postings", "addon_dispatches", "addon_return_postings", "repair_stock") for r in rows(e, table) if r["stock_move_id"]}
    netstock = defaultdict(int)
    for m in moves.values():
        owner = physical.get(m["id"])
        if owner:
            netstock[(owner, m["item_id"])] -= m["value_cents"]
        cid = owner or m["case_id"]
        if not inside(m["business_date"], src["period"]) or filters.get("item_id") and m["item_id"] != filters["item_id"] or filters.get("case_id") and cid != filters["case_id"]:
            continue
        c, item = allcases[cid], items[m["item_id"]]
        if owner:
            if owner not in related:
                continue
            table, amount, qty = "material_actual_stock", -m["value_cents"], -m["quantity_milli"]
            values = [c["number"], src["store_name"], SOURCE_NAMES[c["kind"]], m["business_date"], item["sku"], item["name"], item["unit"], quantity(qty), yuan(amount), m["id"]]
        else:
            detailed = c["kind"] == "retail" and c["flow_version"] == 2 or c["kind"] == "addon" and c["flow_version"] == 3 or c["kind"] == "repair" and c["flow_version"] in (3, 4)
            if filters.get("source") and filters["source"] != "stock" or m["id"] in commercial or detailed:
                continue
            table, amount, qty = "material_other_stock", m["value_cents"], m["quantity_milli"]
            values = [c["number"], src["store_name"], m["business_date"], STOCK_NAMES.get(m["purpose"], m["purpose"]), item["sku"], item["name"], item["unit"], quantity(qty), yuan(amount), m["id"]]
        wanted[table].append({"values": values, "amount_cents": amount, "case_id": cid, "item_id": item["id"], "stock_move_id": m["id"], "quantity_milli": qty, "business_date": m["business_date"], "purpose": m["purpose"], "route": {"type": "case", "id": cid}})
    for cid, iid in sorted(set(netstock) | set(recognized)):
        if cid not in related or filters.get("item_id") and iid != filters["item_id"]:
            continue
        c, item = selected[cid], items[iid]
        actual, cost = netstock[(cid, iid)], recognized[(cid, iid)]
        require(actual - cost >= 0, "原未履约成本为负")
        wanted["material_unfulfilled"].append({"values": [c["number"], src["store_name"], SOURCE_NAMES[c["kind"]], item["sku"], item["name"], yuan(actual), yuan(cost), yuan(actual - cost)], "case_id": cid, "item_id": iid, "actual_cost_cents": actual, "recognized_cost_cents": cost, "amount_cents": actual - cost, "route": {"type": "case", "id": cid}})
    for key in MATERIAL_KEYS:
        compare(data["tables"][key]["rows"], wanted[key], key)
    for key, index in (("material_goods", 2), ("material_sources", 2), ("material_unallocated", 4), ("material_other_stock", 3), ("material_unfulfilled", 2)):
        table_chart(data, key, index, costs=key == "material_goods")
    metrics = {"material_selected_goods_cents": sum(r["amount_cents"] for r in wanted["material_goods"]),
        "material_selected_goods_cost_cents": sum(r["cost_cents"] for r in wanted["material_goods"]),
        "material_source_net_cents": sum(r["amount_cents"] for r in wanted["material_sources"]),
        "material_unfulfilled_cost_cents": sum(r["amount_cents"] for r in wanted["material_unfulfilled"])}
    require(data["metrics"] == metrics, "原商品/成本/净额/未履约指标与DB不一致")
    return {"db_row_counts": {key: len(values) for key, values in wanted.items()}, "filters": filters,
        "metrics": metrics, "original_stock_ids": sorted(physical), "all_source_amounts_conserved": True,
        "background_group_retail_is_not_new_member_acceptance": True}


def material_panel(e, data, key):
    return e.page.locator("#main > section.panel").filter(has=e.page.get_by_role("heading", name=data["tables"][key]["title"], exact=True)).filter(has=e.page.locator(".work-table"))


async def material_table(e, data, key):
    before = e.business_snapshot("before_material_value_table")
    target, source = material_panel(e, data, key), data["tables"][key]
    await expect(target).to_have_count(1)
    await expect(target).to_be_visible()
    table = target.locator(".work-table table")
    if not source["rows"]:
        await expect(table).to_have_count(0)
        await expect(target).to_contain_text("当前范围没有实际记录")
    else:
        await expect(table.locator("thead th")).to_have_text(source["headers"] + ["原单"])
        await first_page(e, target)
        for page_no, start in enumerate(range(0, len(source["rows"]), 20), 1):
            actual = table.locator("tbody tr")
            expected = source["rows"][start:start + 20]
            await expect(actual).to_have_count(len(expected))
            for i, row in enumerate(expected):
                await expect(actual.nth(i).locator("td").nth(0)).to_have_text(text(row["values"][0]))
                require([v.strip() for v in await actual.nth(i).locator("td").all_text_contents()][:-1] == [text(v).strip() for v in row["values"]], "物资实际20行分页与原JSON不一致")
            if start + 20 < len(source["rows"]):
                await click(e, target.locator('[data-act="page"][data-page="' + str(page_no + 1) + '"]'), "查看实际收入成本下一页")
                await expect(target.locator(".pagination span")).to_contain_text("第 " + str(page_no + 1) + " 页")
    e.business_unchanged(before, "after_material_value_table")
    return {"key": key, "rows": len(source["rows"]), "page_size": 20, "all_visible_pages_verified": True}


async def material_filter(e, src, filters):
    before = e.business_snapshot("before_material_value_filters")
    for name in ("source", "item_id", "case_id"):
        value = str(filters[name]) if filters.get(name) is not None else ""
        await select_value(e, '#material-value-filters [name="' + name + '"]', value, "选择真实" + name + "原筛选项")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/material-value") as pending:
        await click(e, e.page.locator('#material-value-filters button[type="submit"]'), "按明确来源物资原单查询实际收入成本")
    response = await pending.value
    result = await response.json()
    await native_response(e, response, {**src["period"], **filters})
    await expect(e.page.locator("#main .loading")).to_have_count(0)
    await expect(e.page.locator("#main .notice.error, #main [role=alert]")).to_have_count(0)
    e.business_unchanged(before, "after_material_value_filters")
    return result


async def save_download(e, download, key, expected):
    require(await download.failure() is None, "原CSV下载失败")
    directory = e.directory / "exports"
    directory.mkdir(exist_ok=True)
    destination = directory / (str(len(list(directory.iterdir())) + 1).zfill(2) + "-" + key + ".csv")
    await download.save_as(destination)
    actual = list(csv.reader(io.StringIO(destination.read_text(encoding="utf-8-sig"), newline="")))
    require(actual == expected, "原CSV与该范围全部原行不一致：" + key)
    return {"path": str(destination), "sha256": sha(destination), "data_rows": len(expected) - 1}


async def material_export(e, src, data, key, filters):
    before = e.business_snapshot("before_material_value_csv")
    audit = e.db.rows("SELECT * FROM audit_logs ORDER BY id")
    path = "/api/material-value/export/" + key
    async with e.page.expect_download() as downloaded:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
            await click(e, material_panel(e, data, key).locator('[data-act="mv-export"][data-key="' + key + '"]'), "下载物资收入成本本表原CSV")
        metadata = await native_response(e, await pending.value, {**src["period"], **filters})
    t = data["tables"][key]
    result = await save_download(e, await downloaded.value, key, [t["headers"]] + [[safe_csv(v, "material") for v in r["values"]] for r in t["rows"]])
    result.update(native_http=metadata, audit=assert_export_delta(e, before, audit, src["actor"], "material_value_report", src["period"]["date_from"] + "至" + src["period"]["date_to"] + " " + key), all_other_business_and_old_audit_preserved=True)
    e.observe("original_material_value_csv", result)
    return result


async def material_drill(e, data, key, original):
    candidates = [r for r in data["tables"][key]["rows"] if r.get("route") == {"type": "case", "id": original["id"]}]
    require(candidates, "本次明确维修/加装原单未出现在收入成本表")
    row = candidates[0]
    index = data["tables"][key]["rows"].index(row)
    target = material_panel(e, data, key)
    await first_page(e, target)
    for page_no in range(2, index // 20 + 2):
        await click(e, target.locator('[data-act="page"][data-page="' + str(page_no) + '"]'), "按原20行分页定位真实原单")
        await expect(target.locator(".pagination span")).to_contain_text("第 " + str(page_no) + " 页")
    return await case_drill(e, target.locator(".work-table tbody tr").nth(index % 20).locator('[data-act="open"][data-route="case/' + str(original["id"]) + '"]'), original)


async def case_drill(e, button, original):
    before = e.business_snapshot("before_finance_report_original_drill")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/cases/" + str(original["id"])) as pending:
        await click(e, button, "从报表点击查看明确原业务单")
    response = await pending.value
    body = await response.json()
    await native_response(e, response, {})
    require(body["id"] == original["id"] and body["number"] == original["number"] and body["version"] == original["version"], "报表原单钻取对象/当前CAS错误")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(original["number"])
    e.business_unchanged(before, "after_finance_report_original_drill")
    return {"case_id": original["id"], "number": original["number"], "version": original["version"], "native_get_status": response.status}


async def insurance_report(e, cp, src):
    data = await entry(e, "HK-141", "analytics/sales", "数据可视化", "/api/flow/analytics", src["period"])
    facts = insurance_facts(e, data, src)
    charts = [await graph(e, data, key) for key in ("insurance_commission_facts", "insurance_commission_cash")]
    ui = await experience(e)
    proofs = []
    for key in ("insurance_policy_facts", "insurance_commission_facts", "insurance_commission_cash"):
        if proofs:
            data = await entry(e, "HK-141", "analytics/sales", "数据可视化", "/api/flow/analytics", src["period"])
            insurance_facts(e, data, src)
        await flow_table(e, data, key)
        viewed = await verify_table(e, data, key, "flow")
        downloaded = await export_csv(e, src["actor"], data, key, "flow", src["period"])
        original = src["insured_cases"][1 if key == "insurance_policy_facts" else 0]
        matches = [r for r in data["tables"][key]["rows"] if r.get("route") == {"type": "case", "id": original["id"]}]
        require(matches, "本轮原保险来源没有原单入口")
        drill = await drill_original(e, data, key, matches[0], "flow", case(e, original["id"]))
        proofs.append({"key": key, "table": viewed, "csv": downloaded, "original": drill})
        cp.note(tables=proofs)
    await cp.passed(db_facts=facts, charts=charts, tables=proofs, period=src["period"], experience=ui)


async def material_report(e, cp, src):
    data = await entry(e, "HK-161", "material-value", "物资收入成本对照", "/api/material-value", src["period"])
    facts = material_facts(e, data, src, {})
    require(any(r["case_id"] == src["repair"]["id"] for r in data["tables"]["material_goods"]["rows"])
        and any(r["case_id"] == src["addon"]["id"] for r in data["tables"]["material_goods"]["rows"]), "同次实际维修领退与加装履约非空源缺失")
    charts = [await graph(e, data, key) for key in ("material_goods", "material_sources", "material_unallocated", "material_other_stock", "material_unfulfilled")]
    tables = []
    for key in MATERIAL_KEYS:
        tables.append({"ui": await material_table(e, data, key), "csv": await material_export(e, src, data, key, {})})
        cp.note(tables=tables)
    ui = await experience(e)
    filters = {"source": "repair", "item_id": src["material"]["primary"]["item_id"], "case_id": src["repair"]["id"]}
    filtered = await material_filter(e, src, filters)
    filtered_facts = material_facts(e, filtered, src, filters)
    require(filtered["tables"]["material_goods"]["rows"] and all(r["case_id"] == filters["case_id"] and r["item_id"] == filters["item_id"] for r in filtered["tables"]["material_goods"]["rows"]), "实际三筛选未限定本维修原物资")
    filtered_table = await material_table(e, filtered, "material_goods")
    filtered_csv = await material_export(e, src, filtered, "material_goods", filters)
    drill = await material_drill(e, filtered, "material_goods", case(e, src["repair"]["id"]))
    await cp.passed(db_facts=facts, tables=tables, charts=charts, filters=filters, filtered_db=filtered_facts,
        filtered_table=filtered_table, filtered_csv=filtered_csv, original=drill, experience=ui, cash_not_used_as_material_revenue=True)


async def advance_report(e, cp, src):
    data = await entry(e, "HK-162", "table/finance_advances", "当前本店客户预收余额", "/api/flow/analytics", src["period"])
    facts = advance_facts(e, data, src)
    viewed = await verify_table(e, data, "finance_advances", "flow")
    exported = await export_csv(e, src["actor"], data, "finance_advances", "flow", src["period"])
    await finance_chart_page(e, "finance", src["period"])
    charts = [await graph(e, data, key) for key in ("finance_advances", "finance_advance_movements")]
    await flow_table(e, data, "finance_advance_movements")
    ledger_ui = await verify_table(e, data, "finance_advance_movements", "flow")
    ledger_csv = await export_csv(e, src["actor"], data, "finance_advance_movements", "flow", src["period"])
    ui = await experience(e)
    original = case(e, src["finance"]["apply_case_id"])
    matches = [r for r in data["tables"]["finance_advance_movements"]["rows"] if r.get("route") == {"type": "case", "id": original["id"]}]
    require(len(matches) == 1, "4000非现金原抵用没有唯一期间来源")
    drill = await drill_original(e, data, "finance_advance_movements", matches[0], "flow", original)
    await cp.passed(db_facts=facts, current_balance_table=viewed, current_balance_csv=exported, ledger_table=ledger_ui,
        ledger_csv=ledger_csv, charts=charts, original_non_cash_apply=drill, experience=ui, balance_not_cash_or_member_principal=True)


def settlement_facts(e, src, view):
    manifest = view["manifest"]
    require(manifest and len({r["key"] for r in manifest}) == len(manifest)
        and [r["key"] for r in manifest] == sorted(r["key"] for r in manifest), "冻结来源缺失、重复或无原稳定排序")
    require(view["definition_version"] == view["summary"]["definition_version"] == 22, "读取了非本次现行原定义")
    correction = one(e, "business_finance_stored_corrections", src["finance"]["stored_correction_id"])
    samples = (("cash_entries", [src["finance"]["original_advance_cash_id"], correction["reversing_cash_id"], src["finance"]["corrected_cash_id"], src["finance"]["refund_cash_id"]]),
        ("business_finance_stored_corrections", [correction["id"]]), ("business_finance_credit_links", [src["finance"]["credit_link_id"]]))
    matched = []
    for table, ids in samples:
        for key in ids:
            found = [r for r in manifest if r["source"] == table and r["source_id"] == key]
            require(len(found) == 1, "本版冻结来源缺少本轮原事实：" + table)
            original = comparable(one(e, table, key))
            for field, value in found[0]["data"].items():
                require(field in original, "冻结来源出现原模型无字段")
                expected = original[field]
                if isinstance(value, (dict, list)) and isinstance(expected, str):
                    expected = json.loads(expected)
                require(expected == value, "不可变原款/更正/抵用冻结值与原DB不符")
            matched.append({"key": found[0]["key"], "basis": found[0]["basis"], "data_sha256": digest(found[0]["data"])})
    excluded = set(view["summary"]["excluded_cash_ids"])
    require({correction["original_cash_id"], correction["reversing_cash_id"]} <= excluded
        and not ({correction["corrected_cash_id"], src["finance"]["refund_cash_id"]} & excluded), "现金定义7原误记/冲正和正确收退款排除规则不符")
    cash_totals = {"in": 0, "out": 0}
    for entry in manifest:
        if entry["source"] == "cash_entries" and entry["source_id"] not in excluded and entry["data"]["category"] != "transfer":
            value = entry["data"]
            require(entry["basis"] == "period" and type(value["amount_cents"]) is int and value["direction"] in cash_totals, "现金冻结期间/方向/整数分不符")
            cash_totals[value["direction"]] += value["amount_cents"]
    receivable = sum(r["data"]["amount_cents"] for r in manifest if r["source"] == "receivable")
    require(cash_totals["in"] == view["summary"]["period_cash_in_cents"]
        and cash_totals["out"] == view["summary"]["period_cash_out_cents"]
        and receivable == view["summary"]["current_receivable_cents"], "冻结整范围摘要不等于同版本完整现金/应收来源")
    require(type(view["source_changed"]) is bool, "原晚到来源比较不是明确布尔值")
    return {"matched_finite_immutable_sources": matched, "all_frozen_rows": len(manifest), "cash_totals": cash_totals,
        "frozen_current_receivable_cents": receivable, "definition_version": 22, "cash_definition_version": 7,
        "frozen_digest": view["digest"], "source_changed": view["source_changed"], "late_business_not_recomputed_or_overwritten": True}


async def settlement_open(e, src, key):
    listing = await entry(e, "HK-163", "reconciliation", "业务对账与月结", "/api/reconciliation/batches")
    require(any(r["id"] == key for r in listing["items"]), "本次原对账不在本人原列表，不扫描旧单替代")
    before = e.business_snapshot("before_original_frozen_batch")
    path = "/api/reconciliation/batches/" + str(key)
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        await click(e, e.page.locator('#main [data-act="open"][data-route="reconciliation/' + str(key) + '"]'), "查看同次明确对账版本来源与差异")
    response = await pending.value
    view = await response.json()
    await native_response(e, response, {})
    batch_view(e, view, key)
    await expect(e.page.locator("#main h1")).to_have_text("业务对账与月结")
    await expect(e.page.locator("#main .pagehead")).to_contain_text(view["start"] + " 至 " + view["end"] + " · 版本" + str(view["revision"]))
    await expect(e.page.locator("#main .notice.error, #main [role=alert]")).to_have_count(0)
    warning = e.page.locator("#main .notice").filter(has_text="账目已变化，请重新计算后提交。已封存的请联系店长重开。")
    if view["source_changed"]:
        await expect(warning).to_have_count(1)
        await expect(warning).to_be_visible()
    else:
        await expect(warning).to_have_count(0)
    e.business_unchanged(before, "after_original_frozen_batch")
    return view


def frozen_yuan(value):
    return "—" if value is None else format(Decimal(value) / 100, ",.2f")


def frozen_cell(source, data):
    if isinstance(data.get("values"), list):
        return " · ".join(text(v) for v in data["values"])
    amount = data.get("amount_cents", data.get("value_cents"))
    result = frozen_yuan(amount) + " 元" if amount is not None else ""
    if "quantity_milli" in data:
        result += " · 数量 " + format((Decimal(data["quantity_milli"]) / 1000).normalize(), "f")
    if "units" in data:
        result += " · 原单位 " + str(data["units"])
    if "credit_cents" in data:
        result += " · C " + frozen_yuan(data["credit_cents"]) + " / P " + frozen_yuan(data["consideration_cents"]) + " / S " + frozen_yuan(data["settlement_cents"]) + " 元"
    purpose_labels = {
        "business_finance_advance_entries": {"receive": "预收款实际到账", "correction": "账务更正", "apply": "预收抵用", "refund": "原款退款"},
        "flow_member_entries": {"topup": "充值"},
        "flow_stock_moves": {"purchase": "采购入库", "issue": "物资出库"},
    }
    status_labels = {
        "business_finance_applications": {"applied": "已办理"},
        "business_finance_stored_correction_requests": {"applied": "已办理"},
        "vehicle_positions": {"stored": "在库", "exited": "已出库"},
    }
    purpose = data.get("purpose")
    status = data.get("status")
    trailing = data.get("reference") or data.get("voucher_no")
    if not trailing:
        trailing = (purpose_labels.get(source, {}).get(purpose)
            or {"transfer_in": "跨店调入", "transfer_out": "跨店调出", "purchase_in": "采购入库"}.get(purpose)
            or purpose or data.get("side") or status_labels.get(source, {}).get(status) or status or "")
    return (result + "\n" + str(trailing)).strip()


async def settlement_table(e, view):
    before = e.business_snapshot("before_original_frozen_sources_ui")
    target = e.page.locator("#main > section.panel").filter(has=e.page.get_by_role("heading", name="冻结来源条目", exact=True))
    await expect(target).to_have_count(1)
    await expect(target.locator("thead th")).to_have_text(["来源／原条目", "金额与事实", "核对"])
    visible = view["manifest"][:200]
    await expect(target.locator("tbody tr")).to_have_count(len(visible))
    for index, row in enumerate(visible):
        ui = target.locator("tbody tr").nth(index)
        await expect(ui.locator("td").nth(0).locator(".muted")).to_have_text("#" + str(row["source_id"]) + " · " + ("所选期间" if row["basis"] == "period" else "生成时点"))
        # The original display labels retain their own names; amounts and
        # source references below are checked against frozen raw model facts.
        expected = frozen_cell(row["source"], row["data"])
        actual = (await ui.locator("td").nth(1).inner_text()).strip()
        require(actual == expected, "原冻结来源金额/数量/原引用显示不符：" + row["key"])
        if row["case_id"]:
            await expect(ui.locator('[data-act="open"][data-route="case/' + str(row["case_id"]) + '"]')).to_be_visible()
    if len(view["manifest"]) > 200:
        await expect(e.page.get_by_text("页面显示前200条，完整冻结条目请下载CSV。", exact=True)).to_be_visible()
    issue_panel = e.page.locator("#main > section.panel").filter(has=e.page.get_by_role("heading", name="逐项差异", exact=True))
    if view["issues"]:
        await expect(issue_panel.locator("tbody tr")).to_have_count(len(view["issues"]))
        for index, issue in enumerate(view["issues"]):
            row = issue_panel.locator("tbody tr").nth(index)
            await expect(row).to_contain_text("#" + issue["line_key"].split(":")[1])
            await expect(row).to_contain_text(frozen_yuan(issue["difference_cents"]) + " 元")
            await expect(row).to_contain_text(issue["reason"])
            await expect(row).to_contain_text(issue["resolution"] if issue["status"] == "resolved" else "待核对处理")
    e.business_unchanged(before, "after_original_frozen_sources_ui")
    return {"visible_frozen_rows": len(visible), "complete_frozen_rows": len(view["manifest"]), "source_limit_explicit": len(view["manifest"]) > 200,
        "issues_shown": len(view["issues"]), "frozen_source_values_checked": True}


async def settlement_csv(e, view):
    before = e.business_snapshot("before_original_frozen_csv")
    path = "/api/reconciliation/batches/" + str(view["id"]) + "/export"
    async with e.page.expect_download() as downloaded:
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
            await click(e, e.page.locator('[data-act="reconcile-action"][data-key="export"]'), "下载本版本全部冻结原来源CSV")
        metadata = await native_response(e, await pending.value, {})
    expected = [["对账版本", "源条目", "来源", "期间或时点", "原单", "金额分", "数量千分位", "权益单位", "冻结来源内容"]]
    for entry in view["manifest"]:
        d = entry["data"]
        values = [view["revision"], entry["key"], entry["source"], entry["basis"], entry["case_id"] or "", d.get("amount_cents", d.get("value_cents", "")), d.get("quantity_milli", ""), d.get("units", ""), json.dumps(d, ensure_ascii=False, sort_keys=True)]
        expected.append(["'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r")) else str(v) for v in values])
    result = await save_download(e, await downloaded.value, "reconciliation-" + str(view["id"]), expected)
    e.business_unchanged(before, "after_original_frozen_csv")
    result.update(native_http=metadata, revision=view["revision"], frozen_digest=view["digest"], no_export_audit_in_original_contract=True,
        all_old_business_and_audit_rows_unchanged=True)
    e.observe("original_frozen_statement_csv", result)
    return result


async def settlement_report(e, cp, src):
    proofs = []
    pinned = {key: one(e, "reconciliation_batches", key) for key in src["batch_ids"]}
    for key in src["batch_ids"]:
        view = await settlement_open(e, src, key)
        facts = settlement_facts(e, src, view)
        table = await settlement_table(e, view)
        exported = await settlement_csv(e, view)
        ui = await experience(e)
        own = [r for r in view["manifest"][:200] if r["source"] == "business_finance_credit_links" and r["source_id"] == src["finance"]["credit_link_id"]]
        require(len(own) == 1 and own[0]["case_id"] == src["finance"]["service_case_ids"][0], "本版有限4000原抵用不在可见冻结来源或串原服务单，不能猜另一原单")
        index = view["manifest"].index(own[0])
        panel_ui = e.page.locator("#main > section.panel").filter(has=e.page.get_by_role("heading", name="冻结来源条目", exact=True))
        drill = await case_drill(e, panel_ui.locator("tbody tr").nth(index).locator('[data-act="open"][data-route="case/' + str(own[0]["case_id"]) + '"]'), case(e, own[0]["case_id"]))
        proofs.append({"batch_id": key, "revision": view["revision"], "status": view["status"], "facts": facts, "table": table, "csv": exported, "original": drill, "experience": ui})
        cp.note(versions=proofs)
    require(all(one(e, "reconciliation_batches", key) == value for key, value in pinned.items()), "原查询改写了三版冻结账目")
    await cp.passed(versions=proofs, sealed_old_versions_preserved=True, source_changed_observed_without_recalculation=True,
        charts_supported=False, original_module_uses_frozen_source_table_and_csv=True)


async def finance_report_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        cp.start("HK-141")
        src = source_facts(e, cp)
        # Session audits are allowed by the original login; each subsequent
        # read/download takes a new complete old-business baseline.
        actor = await login_as(e, context, credentials, src["manager_key"], "module/analytics", 1)
        require(actor["id"] == src["actor"]["id"], "报表借用了另一员工")
        await expect(e.page.locator("#main h1")).to_have_text("统计分析")
        await insurance_report(e, cp, src)
        cp.start("HK-161")
        await material_report(e, cp, src)
        cp.start("HK-162")
        await advance_report(e, cp, src)
        cp.start("HK-163")
        await settlement_report(e, cp, src)
        cp.finish()
    except Exception as error:
        cp.failed(error)
        raise


FINANCE_REPORT_SCENARIOS = ((SCENARIO, finance_report_business, 600),)
