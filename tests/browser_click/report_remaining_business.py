"""Nine original reports; native controls and this run's finite business sources.

No app imports, setup writes, direct HTTP calls, state injection or write replay.
CSV is the sole permitted new audit; every old business row remains protected.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from playwright.async_api import expect
from sales_business import login_as, require
from sales_order_business import fixed_dependency
from vehicle_purchase_business import nav
from report_business import (click, write_json, sha, yuan, local_time, native_response,
    refresh_report, open_report, panel, first_page, verify_table, export_csv, graph,
    flow_chart, drill_original, experience)


A = "reports-sales-customer-hk139-140-164-165-166"
B = "reports-boutique-points-hk154-156-168-169"
CONTRACTS = {
    A: (("HK-139", "加装单分析", "table/addon_actual_facts"),
        ("HK-140", "代办单分析", "table/service_fee_facts"),
        ("HK-164", "客户车辆统计", "table/customer_vehicle_stats"),
        ("HK-165", "客户回访统计", "table/callbacks"),
        ("HK-166", "进出厂统计", "visit-activity")),
    B: (("HK-154", "精品销售统计", "table/retail_settlements"),
        ("HK-156", "精品销售施工统计", "table/retail_installation"),
        ("HK-168", "会员积分统计", "analytics/members"),
        ("HK-169", "消费券统计", "table/benefit_coupon")),
}
PRE = "sales-presales-hk001-007"
PUR = "vehicle-purchase-hk171-177-178-026-021-018-029"
MD = "master-data-hk170-172-173-174-175-176-179-180-181-182-183-184-185-186-187"
MAT = "materials-hk069-045-054-083-070-072-073-051-061"
CS = "customer-service-hk098-107-108-109"
REP = "repair-selfpay-hk031-034-044-049-053-079"
SALE = "sales-order-hk008-009-011-022"
FOLLOW = "sales-followon-hk012-015-016-017"
CF = "customer-followon-hk100-101-102-103-104-110-111"
MEM = "membership-hk117-128-118-089-094"
MF = "member-followon-hk123-124-125-129-130-132"
BT = "boutique-purchase-retail-hk074-052-058-062-064-082"
PTS = "member-points-tier-hk121-122-188-120-119-131"
PARENTS = {A: (PRE, PUR, MD, MAT, CS, REP, SALE, FOLLOW, CF),
           B: (PRE, PUR, MD, MAT, SALE, MEM, MF, BT, PTS)}
FILES = {PRE: "sales_business.py", PUR: "vehicle_purchase_business.py", MD: "master_data_business.py",
    MAT: "material_business.py", CS: "customer_service_business.py", REP: "repair_business.py",
    SALE: "sales_order_business.py", FOLLOW: "sales_followon_business.py", CF: "customer_followon_business.py",
    MEM: "membership_business.py", MF: "member_followon_business.py", BT: "boutique_business.py",
    PTS: "member_points_tier_business.py"}
TABLES = {"flow_cases", "flow_events", "flow_customers", "addon_acceptances", "addon_return_postings",
    "service_lines", "service_fulfillments", "service_charge_adjustments", "service_terminations",
    "service_authorizations", "service_tender_slices",
    "service_termination_applications", "care_customer_vehicles", "care_cases", "care_records",
    "intake_appointments", "intake_arrivals", "intake_vehicle_bindings", "flow_files",
    "retail_lines", "retail_dispatches", "retail_return_postings", "retail_return_lines", "flow_stock_moves",
    "retail_group_plans", "retail_group_tenders", "retail_group_units", "retail_group_allocations",
    "retail_group_captures", "retail_group_returns", "retail_group_return_parts", "group_entries",
    "benefit_entries", "benefit_wallets", "benefit_rules", "membership_points_changes",
    "membership_points_claims", "membership_points_debts", "membership_points_debt_payments"}
PK = {"care_cases": "case_id", "intake_vehicle_bindings": "case_id"}
ZONE = ZoneInfo("Asia/Shanghai")
STATES = {"draft": "待提交", "unassigned": "待分派", "contacting": "待接待反馈", "reminder": "接待回访中",
    "intent": "意向跟进中", "converted": "已转订单", "closed": "已结束", "reserved": "订单待确认",
    "executing": "交付准备中", "delivered": "已提车", "cancel_review": "退订待审批", "refund_pending": "待退款",
    "cancelled": "已取消", "assessment": "待检查报价", "authorization": "待客户授权", "working": "处理中",
    "quality": "待质检", "settling": "待结算交接", "credit_open": "已交车待月结", "completed": "已完成",
    "pending": "待办理", "approval": "待复核", "receiving": "待到货", "rejected": "已退回", "resolving": "处理中"}
CARE_STATUS = {"pending": "待接手", "working": "跟进中", "completed": "已结案", "cancelled": "已取消"}
CARE_RESULT = {"resolved": "已解决", "appointment": "已约定后续办理", "declined": "客户不需要",
               "no_response": "多次联系未回应", "renewed": "续保已完成"}
PURPOSES = {"purchase": "购买发行", "grant": "赠送发行", "capture": "核销", "reverse": "撤销核销",
    "refund": "原款退款", "adjust": "积分调整", "exchange_in": "兑换获得", "exchange_out": "兑换扣减"}


class Checkpoint:
    def __init__(self, e, scenario):
        self.e, self.active, self.scenario = e, None, scenario
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(Path(__file__).with_name("business_acceptance_catalog.json"))
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        requirements = []
        for key, title, route in CONTRACTS[scenario]:
            source = catalog[key]
            require(source["title"] == title and route in source["target_routes"]
                and source["source_review_status"] == "source_reviewed"
                and any(c["check_id"] == key + "-business" for c in source["acceptance_checks"]), "原报表合同不匹配：" + key)
            requirements.append({"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business",
                    "criteria": ["原UI非空来源、实际期间、全分页及同范围图", "原API与DB整数金额数量和来源一致",
                        "原单钻取与实际CSV全部字段", "全旧行保护、唯一原导出审计与当前身份",
                        "流程简易：待独立人工评价", "文案简洁：待独立人工评价"],
                    "status": "not_tested", "evidence": {}}],
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"}})
        self.report = {"schema": 1, "scenario": scenario, "scope": [r["id"] for r in requirements],
            "complete": False, "passed": False, "business_accepted": False, "human_acceptance": "pending",
            "full_193_business_acceptance": False, "full_registered_suite_complete": False,
            "execution": "native_browser_original_reports", "requirements": requirements,
            "source_contract_sha256": sha(Path(__file__).with_name("business_acceptance_catalog.json")),
            "candidate_sha256": sha(Path(__file__)), "prerequisite_checkpoints": [],
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "conditions": {"real_external_or_production_acceptance": False, "group_scope": "not_tested",
                "nonempty_points_debt": "not_tested", "gate_corrections": "not_tested",
                "historical_full_coverage": "not_tested", "HK152_HK153": "partial_not_promoted",
                "HK157_HK158_HK159": "not_tested_new_positive_balance_sources_required"}}
        self.save()

    def save(self):
        write_json(self.path, self.report)

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        require(self.active["status"] == "not_tested", "不能覆盖原执行记录")
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active["evidence_action_start"] = len(self.e.actions)
        self.save()

    def note(self, **evidence):
        json.dumps(evidence, ensure_ascii=False)
        self.active["acceptance_checks"][0]["evidence"].update(evidence)
        self.save()

    async def passed(self, **evidence):
        self.note(**evidence)
        await self.e.snapshot(self.active["id"].lower() + "-original-report", business_ready=True)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.active = None
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.active["acceptance_checks"][0]["error"] = self.e.scrub(str(error))
        self.report.update(error=self.e.scrub(str(error)),
            executed_requirements=sum(r["status"] != "not_tested" for r in self.report["requirements"]),
            passed_requirements=sum(r["status"] == "passed" for r in self.report["requirements"]))
        self.save()

    def finish(self):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "本组报表未完整执行")
        total = len(self.report["requirements"])
        self.report.update(complete=True, passed=True, executed_requirements=total, passed_requirements=total)
        self.save()
        self.e.observe("remaining_reports_checkpoint", {"scenario": self.scenario, "checks": total,
            "business_accepted": False, "human_acceptance": "pending", "full_193_business_acceptance": False})


def rows(e, table):
    require(table in TABLES, "原只读来源表未核准：" + table)
    found = e.db.rows(f"SELECT * FROM {table} ORDER BY {PK.get(table, 'id')} LIMIT 25001")
    require(len(found) <= 25000, "原报表来源超限，不能截断")
    # Debt payments are scoped through their original PointsChange, rather
    # than the paying store. Match that existing report relationship exactly.
    return [r for r in found if table == "membership_points_debt_payments" or "store_id" not in r or r["store_id"] == 1]


def one(e, table, key):
    require(type(key) is int and key > 0, "原有限来源ID无效")
    found = [r for r in rows(e, table) if r[PK.get(table, "id")] == key]
    require(len(found) == 1, "本店明确原来源不存在：" + table)
    return found[0]


def cases(e):
    result = {r["id"]: r for r in rows(e, "flow_cases")}
    for row in result.values():
        row["data"] = json.loads(row["data"])
    return result


def inside(day, period):
    return bool(day and period["date_from"] <= day <= period["date_to"])


def quantity(value):
    return format(Decimal(value) / 1000, "f")


def compare(actual, expected, label):
    encode = lambda r: json.dumps(r, ensure_ascii=False, sort_keys=True)
    require(Counter(map(encode, actual)) == Counter(map(encode, expected)), label + " 全范围原行与DB不匹配")


def compare_table(data, key, expected, fields):
    compare([{k: r[k] for k in fields} for r in data["tables"][key]["rows"]], expected, key)


def record(values, case_id, **extra):
    return {"values": values, "route": {"type": "case", "id": case_id}, **extra}


def chart_db(data, key, totals, name, unit="cents"):
    found = [c for c in data["charts"] if c["id"] == key]
    require(len(found) == 1, "原图来源缺失/重复：" + key)
    c = found[0]
    require(c["table"] == key and c["unit"] == unit and len(c["series"]) == 1
        and c["series"][0]["name"] == name and len(c["labels"]) == len(set(c["labels"]))
        and dict(zip(c["labels"], c["series"][0]["values"])) == dict(totals), "原图不是同范围DB归集：" + key)


def source_facts(e, cp):
    require(e.manifest.get("synthetic_data_only") is True, "只允许同轮外置合成运行")
    root = Path(e.manifest["evidence_root"]).resolve()
    require(Path(e.manifest["database_path"]).resolve().is_relative_to(root.parent / "runtime"), "原报表库不在本轮runtime")
    require(not root.is_relative_to(Path(e.manifest["source_root"]).resolve()), "证据不得写入被测源码")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance.get("snapshot_stable") is True, "原镜像未冻结")
    for name in {"report_remaining_business.py", "report_business.py", "business_acceptance_catalog.json",
                 "sales_order_business.py", "sales_business.py", "vehicle_purchase_business.py",
                 *(FILES[k] for k in PARENTS[cp.scenario])}:
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name)), "同次脚本指纹变化：" + name)
    prior = {name: fixed_dependency(e, cp, name) for name in PARENTS[cp.scenario]}
    all_cases = cases(e)
    refs = {k: prior[k].get("report_sources", {}) for k in prior}
    fixed, check_ids = {}, set()
    if cp.scenario == A:
        require({"addon_case_id", "agency_case_id", "customer_other_case_id"} <= refs[FOLLOW].keys(), "销售后继缺有限原单")
        require({"sales_callback_id", "repair_callback_id", "customer_vehicle_id"} <= refs[CF].keys(), "客服后继缺两类回访/原客车")
        require({"repair_case_id", "appointment_id", "intake_case_id", "customer_vehicle_id", "vin"} <= refs[REP].keys(), "首维修缺实际到离场来源")
        fixed = {"addon": refs[FOLLOW]["addon_case_id"], "agency": refs[FOLLOW]["agency_case_id"],
            "other_income": refs[FOLLOW]["customer_other_case_id"], "sales_callback": refs[CF]["sales_callback_id"],
            "repair_callback": refs[CF]["repair_callback_id"], "repair": refs[REP]["repair_case_id"]}
        for kind, key in fixed.items():
            c = all_cases[key]
            expected = "customer_care" if kind.endswith("callback") else kind
            require(c["kind"] == expected and c["state"] == "completed", "本轮有限来源未真实完成：" + kind)
        require(one(e, "care_cases", fixed["sales_callback"])["subtype"] == "sales_callback"
            and one(e, "care_cases", fixed["repair_callback"])["subtype"] == "repair_callback", "两种原回访混源")
        fixed["customer_vehicle"] = refs[CF]["customer_vehicle_id"]
        cv = one(e, "care_customer_vehicles", fixed["customer_vehicle"])
        require(cv["active"] and cv["customer_id"] == refs[CF]["customer_id"], "本店原车辆身份未有效关联")
        check_ids = {fixed[k] for k in fixed if k != "customer_vehicle"} | {refs[REP]["intake_case_id"]}
    else:
        require({"retail_case_id", "installation_event_id", "accept_event_id", "coupon_purchase_entry_id", "benefit_capture_entry_ids"}
            <= refs[BT].keys(), "精品来源不完整")
        require({"retail_case_id", "points_claim_id", "points_change_id", "earned_points_entry_id", "direct_coupon_grant_entry_id",
                 "points_adjust_entry_id", "independent_points_grant_entry_id", "points_exchange_out_entry_id", "points_exchange_in_entry_id",
                 "direct_coupon_grant_case_id"} <= refs[PTS].keys()
            and refs[PTS]["points_consumption_or_points_change"] is True, "原消费积分来源不完整")
        require({"bundle_grant_entry_ids", "bundle_recovery_entry_ids", "paid_coupon_purchase_entry_id", "paid_coupon_refund_entry_id",
                 "benefit_capture_entry_ids", "retail_case_id", "points_grant_entry_id", "points_recovery_entry_id"} <= refs[MF].keys(),
                "会员六项缺本轮券实购、赠送、核销和原退款有限Entry")
        require(refs[MF]["benefit_capture_entry_ids"] and refs[BT]["benefit_capture_entry_ids"], "本轮核销Entry不足")
        fixed = {"retail": refs[BT]["retail_case_id"], "points_retail": refs[PTS]["retail_case_id"]}
        for key in fixed.values():
            c = all_cases[key]
            require(c["kind"] == "retail" and c["flow_version"] == 2 and c["data"].get("accepted_date"), "原精品未真实客户验收")
        change = one(e, "membership_points_changes", refs[PTS]["points_change_id"])
        claim = one(e, "membership_points_claims", refs[PTS]["points_claim_id"])
        require(change["case_id"] == claim["case_id"] == fixed["points_retail"] and change["claim_id"] == claim["id"]
            and change["units"] == 9 and claim["rule_id"] is not None, "本轮消费积分借用赠分或无冻结规则")
        require(all_cases[fixed["retail"]]["id"] < all_cases[fixed["points_retail"]]["id"], "精品必须在本轮积分会期及积分零售前真实发生")
        check_ids = set(fixed.values())
    dates = [all_cases[k]["business_date"] for k in check_ids]
    dates += [local_time(r["occurred_at"]).date().isoformat() for r in rows(e, "flow_events") if r["case_id"] in check_ids]
    period = {"date_from": min(dates), "date_to": datetime.now(ZONE).date().isoformat()}
    require(max(dates) <= period["date_to"], "实际来源包含未来事实")
    names = e.db.rows("SELECT id,name FROM stores WHERE id=1")
    require(len(names) == 1, "当前原门店缺失")
    cp.report.update(mirror={"provenance_sha256": sha(root / "provenance.json"),
        "source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"]},
        source_ids=fixed, period=period)
    cp.save()
    return {"parents": prior, "refs": refs, "fixed": fixed, "period": period, "store": names[0]["name"]}


def addon_facts(e, data, src):
    cs, expected = cases(e), []
    for table, kind in (("addon_acceptances", "acceptance"), ("addon_return_postings", "return")):
        for f in rows(e, table):
            if f["case_id"] not in cs or not inside(f["business_date"], src["period"]) or kind == "return" and not f["acceptance_id"]:
                continue
            c = cs[f["case_id"]]
            amount = f["amount_cents"] if kind == "acceptance" else -(f["goods_cents"] + f["installation_cents"] - f["retained_cents"])
            cost = f["value_cents"] * (1 if kind == "acceptance" else -1)
            require(type(cost) is int, "原加装商品成本未知时不能猜填")
            expected.append(record([c["number"], src["store"], f["business_date"], "客户实际验收" if kind == "acceptance" else "原验收明细实际退回",
                yuan(amount), yuan(cost)], c["id"], amount_cents=amount, value_cents=cost, source_kind="addon", fact_kind=kind, fact_id=f["id"]))
    compare_table(data, "addon_actual_facts", expected, ("values", "route", "amount_cents", "value_cents", "source_kind", "fact_kind", "fact_id"))
    require(any(r["route"]["id"] == src["fixed"]["addon"] and r["fact_kind"] == "acceptance" for r in expected), "本轮加装实际验收未呈现")
    totals = {src["store"]: sum(r["amount_cents"] for r in expected)} if expected else {}
    chart_db(data, "addon_actual_facts", totals, "金额")
    require(data["metrics"]["addon_actual_net_cents"] == sum(r["amount_cents"] for r in expected)
        and data["metrics"]["addon_actual_goods_cost_cents"] == sum(r["value_cents"] for r in expected), "加装全范围净额/成本KPI错误")
    return expected, {"actual_acceptance_not_dispatch_or_cash": True}


def service_facts(e, data, src):
    cs = {k: c for k, c in cases(e).items() if c["kind"] == "agency" and c["flow_version"] == 3 or c["kind"] == "other_income" and c["flow_version"] == 2}
    lines = {r["id"]: r for r in rows(e, "service_lines")}
    fulfilled = rows(e, "service_fulfillments")
    applications = {r["id"]: r for r in rows(e, "service_termination_applications")}
    facts = []
    for f in fulfilled:
        if f["case_id"] in cs and lines[f["line_id"]]["bucket"] == "fee":
            facts.append((f["case_id"], f["line_id"], f["business_date"], f["amount_cents"], "fulfillment", f["id"], None))
    for a in rows(e, "service_charge_adjustments"):
        old = next((f for f in fulfilled if f["case_id"] == a["case_id"] and f["line_key"] == a["line_key"]), None)
        if a["case_id"] in cs and a["bucket"] == "fee" and old:
            facts.append((a["case_id"], a["line_id"], applications[a["application_id"]]["business_date"], a["amount_cents"], "fee_reduction", a["id"], old["id"]))
    previous = defaultdict(dict)
    for plan in rows(e, "service_terminations"):
        app = next((r for r in applications.values() if r["plan_id"] == plan["id"]), None)
        if plan["case_id"] not in cs or app is None:
            continue
        for line in json.loads(plan["lines"]):
            if line["bucket"] != "fee" or line["fulfilled"]:
                continue
            old = previous[plan["case_id"]]
            amount = line["retained_cents"] - old.get(line["line_key"], 0)
            if amount:
                facts.append((plan["case_id"], line["line_id"], app["business_date"], amount, "retained_fee" if amount > 0 else "fee_reduction", app["id"], None))
            old[line["line_key"]] = line["retained_cents"]
    captions = {"fulfillment": "原项目实际履约", "fee_reduction": "原项目已生效减免", "retained_fee": "客户确认保留的实际办理费"}
    expected, totals = [], defaultdict(int)
    for cid, lid, day, amount, kind, fid, original in facts:
        if not inside(day, src["period"]):
            continue
        c = cs[cid]
        label = "代办服务" if c["kind"] == "agency" else "其它客户服务"
        totals[label] += amount
        expected.append(record([c["number"], src["store"], day, label, lines[lid]["name"], captions[kind], yuan(amount)], cid,
            amount_cents=amount, source_kind=c["kind"], fact_kind=kind, fact_id=fid, original_fact_id=original))
    compare_table(data, "service_fee_facts", expected, ("values", "route", "amount_cents", "source_kind", "fact_kind", "fact_id", "original_fact_id"))
    require({src["fixed"]["agency"], src["fixed"]["other_income"]} <= {r["route"]["id"] for r in expected}, "原代办和其它实际服务费用来源未呈现")
    chart_db(data, "service_fee_facts", totals, "服务费")
    authorizations = {r["quote_id"] for r in rows(e, "service_authorizations")}
    tenders = rows(e, "service_tender_slices")
    adjustments = rows(e, "service_charge_adjustments")
    balances = {"fee": 0, "pass": 0}
    for c in cs.values():
        qid = c["data"].get("service_quote_id")
        if c["state"] == "cancelled" or qid not in authorizations:
            continue
        for bucket in balances:
            selected = [line for line in lines.values() if line["quote_id"] == qid and line["bucket"] == bucket]
            keys = {line["line_key"] for line in selected}
            charge = sum(line["amount_cents"] for line in selected) + sum(a["amount_cents"] for a in adjustments if a["case_id"] == c["id"] and a["line_key"] in keys)
            paid = sum(t["amount_cents"] for t in tenders if t["case_id"] == c["id"] and t["line_key"] in keys)
            balances[bucket] += max(0, charge - paid)
    require(data["metrics"]["service_fee_net_cents"] == sum(totals.values())
        and data["metrics"]["service_fee_receivable_cents"] == balances["fee"]
        and data["metrics"]["service_pass_receivable_cents"] == balances["pass"], "服务实际收入或独立服务费/代缴余额KPI错误")
    return expected, {"pass_through_principal_excluded": True, "full_fee_facts": len(expected), "current_bucket_due_cents": balances}


def vehicle_facts(e, data, src):
    groups = defaultdict(list)
    for r in rows(e, "care_customer_vehicles"):
        if r["active"]:
            groups[r["vehicle_identity_id"]].append(r)
    expected, totals = [], defaultdict(int)
    for identity, relations in sorted(groups.items()):
        models = {r["model_name"] for r in relations}
        model = next(iter(models)) if len(models) == 1 else "车型资料待核对"
        totals[model] += 1
        expected.append({"values": ["GV-" + str(identity), model, src["store"], len(relations),
            "一致" if len(models) == 1 else "各门店登记车型不一致"], "route": {"type": "customer_vehicle", "id": relations[0]["id"]}, "vehicle_count": 1})
    compare_table(data, "customer_vehicle_stats", expected, ("values", "route", "vehicle_count"))
    target = one(e, "care_customer_vehicles", src["fixed"]["customer_vehicle"])
    require(any(r["values"][0] == "GV-" + str(target["vehicle_identity_id"]) for r in expected), "本轮原客户车辆身份未统计")
    chart_db(data, "customer_vehicle_stats", totals, "车辆", "count")
    require(data["metrics"]["customer_vehicle_identity_count"] == len(groups)
        and data["metrics"]["customer_vehicle_relation_count"] == sum(len(rs) for rs in groups.values()), "共享身份去重/关系KPI错误")
    return expected, {"identity_groups": len(groups), "current_relationships_not_stock_or_ownership": True}


def callback_facts(e, data, src):
    cs, expected, totals = cases(e), [], Counter()
    care = {r["case_id"]: r for r in rows(e, "care_cases")}
    for c in cs.values():
        if not inside(c["business_date"], src["period"]):
            continue
        if c["kind"] == "callback":
            state, topic, result = STATES.get(c["state"], c["state"]), c["data"].get("topic", "客户回访"), "原结果见原单"
        elif c["kind"] == "customer_care" and care[c["id"]]["subtype"] in {"sales_callback", "repair_callback"}:
            f = care[c["id"]]
            state = CARE_STATUS.get(c["state"], c["state"])
            topic = ("销售回访" if f["subtype"] == "sales_callback" else "维修回访") + " · " + f["topic"]
            result = "已取消" if c["state"] == "cancelled" else CARE_RESULT.get(f["result"], "尚未结案")
        else:
            continue
        totals[state] += 1
        expected.append(record([c["number"], src["store"], topic, c["due_date"] or "", state, result, 1], c["id"], count=1, state=state, result=result))
    compare_table(data, "callbacks", expected, ("values", "route", "count", "state", "result"))
    require({src["fixed"]["sales_callback"], src["fixed"]["repair_callback"]} <= {r["route"]["id"] for r in expected}, "两种真实新回访未独立计数")
    c = next(r for r in data["charts"] if r["id"] == "callback_state")
    require(c["table"] == "callbacks" and c["unit"] == "count" and c["series"][0]["name"] == "回访任务"
        and dict(zip(c["labels"], c["series"][0]["values"])) == dict(totals), "回访重复跟进被重复计任务")
    require(data["metrics"]["callback_task_count"] == sum(totals.values())
        and data["metrics"]["callback_completed_count"] == totals["已完成"] + totals["已结案"]
        and data["metrics"]["callback_cancelled_count"] == totals["已取消"], "回访全范围KPI错误")
    for cid in (src["fixed"]["sales_callback"], src["fixed"]["repair_callback"]):
        require(len([r for r in rows(e, "care_records") if r["case_id"] == cid]) > 2, "新回访缺真实多次办理原记录")
    return expected, {"two_distinct_care_callback_sources": True, "multiple_records_count_one_task": True}


def retail_facts(e, data, src):
    cs = {k: c for k, c in cases(e).items() if c["kind"] == "retail" and c["flow_version"] == 2}
    moves = {r["id"]: r for r in rows(e, "flow_stock_moves")}
    returns, dispatches = rows(e, "retail_return_postings"), rows(e, "retail_dispatches")
    facts = defaultdict(list)
    for c in cs.values():
        accepted = c["data"].get("accepted_date")
        if not accepted:
            continue
        own = [r for r in returns if r["case_id"] == c["id"]]
        prior = [r for r in own if moves[r["stock_move_id"]]["business_date"] <= accepted]
        facts[c["id"]].append((accepted, "客户接收", c["amount_cents"] - sum(r["goods_cents"] + r["installation_cents"] - r["retained_cents"] for r in prior),
            sum(r["value_cents"] for r in dispatches if r["case_id"] == c["id"]) - sum(r["value_cents"] for r in prior)))
        for r in own:
            if r not in prior:
                facts[c["id"]].append((moves[r["stock_move_id"]]["business_date"], "原单退货冲减", -(r["goods_cents"] + r["installation_cents"] - r["retained_cents"]), -r["value_cents"]))
    plans = {r["id"]: r for r in rows(e, "retail_group_plans") if r["case_id"] in cs}
    tenders = {r["id"]: r for r in rows(e, "retail_group_tenders") if r["plan_id"] in plans}
    units = {r["id"]: r for r in rows(e, "retail_group_units") if r["tender_id"] in tenders}
    allocations = {r["id"]: r for r in rows(e, "retail_group_allocations") if r["unit_id"] in units}
    captures = {r["tender_id"]: r for r in rows(e, "retail_group_captures") if r["tender_id"] in tenders}
    for allocation in allocations.values():
        t = tenders[units[allocation["unit_id"]]["tender_id"]]
        capture = captures.get(t["id"])
        amount = allocation["consideration_cents"] - allocation["credit_cents"]
        if capture and amount:
            original = one(e, "group_entries" if capture["principal_id"] else "benefit_entries", capture["principal_id"] or capture["benefit_id"])
            cid = plans[t["plan_id"]]["case_id"]
            require(original["case_id"] == cid, "原C/P/S核销串单")
            facts[cid].append((local_time(original["occurred_at"]).date().isoformat(), "原集团核销履约优惠", amount, 0))
    group_returns = {r["id"]: r for r in rows(e, "retail_group_returns") if r["plan_id"] in plans}
    byreturn = {r["id"]: r for r in returns}
    for part in rows(e, "retail_group_return_parts"):
        if part["return_id"] not in group_returns or not part["capture_id"] or part["credit_cents"] == part["consideration_cents"]:
            continue
        allocation = allocations[part["allocation_id"]]
        tender = tenders[units[allocation["unit_id"]]["tender_id"]]
        require(captures[tender["id"]]["id"] == part["capture_id"], "实退不是原核销批次")
        posting = byreturn[group_returns[part["return_id"]]["posting_id"]]
        facts[posting["case_id"]].append((moves[posting["stock_move_id"]]["business_date"], "原实退对应优惠冲回", part["credit_cents"] - part["consideration_cents"], 0))
    expected, totals, cost = [], defaultdict(int), 0
    for cid, events in facts.items():
        c = cs[cid]
        if not c["data"].get("accepted_date"):
            continue
        for day, kind, amount, value in events:
            if not inside(day, src["period"]):
                continue
            require(type(value) is int, "原商品成本未知，不能补零")
            totals[src["store"]] += amount
            cost += value
            expected.append(record([c["number"], src["store"], c["title"].split(" · ")[0], day, kind, yuan(amount), yuan(value)], cid, amount_cents=amount))
    compare_table(data, "retail_settlements", expected, ("values", "route", "amount_cents"))
    require({src["fixed"]["retail"], src["fixed"]["points_retail"]} <= {r["route"]["id"] for r in expected}, "两本轮实际精品验收未呈现")
    chart_db(data, "retail_settlements", totals, "金额")
    require(data["metrics"]["retail_revenue_cents"] == sum(totals.values()) and data["metrics"]["retail_goods_cost_cents"] == cost, "精品全范围对外净额/成本错误")
    return expected, {"physical_cost_not_cash": True, "group_C_minus_P_once_no_restore_double_discount": True}


def installation_facts(e, data, src):
    cs = cases(e)
    events = rows(e, "flow_events")
    lines = rows(e, "retail_lines")
    dispatch = {r["id"]: r for r in rows(e, "retail_dispatches")}
    return_lines = {r["id"]: r for r in rows(e, "retail_return_lines")}
    returns = rows(e, "retail_return_postings")
    return_events = {json.loads(r["detail"]).get("return_id"): r["id"] for r in events if r["action"] == "retail_return_receive"}
    expected, totals, seen = [], defaultdict(int), set()
    for event in events:
        if event["action"] != "retail_install":
            continue
        require(event["case_id"] not in seen, "原精品安装重复事实")
        seen.add(event["case_id"])
        day = local_time(event["occurred_at"]).date().isoformat()
        if event["case_id"] not in cs or not inside(day, src["period"]):
            continue
        c = cs[event["case_id"]]
        for line in lines:
            if line["case_id"] != c["id"] or not line["work_item_id"]:
                continue
            own = [r for r in returns if dispatch[r["dispatch_id"]]["line_id"] == line["id"]]
            require(all(return_lines[r["return_line_id"]]["return_id"] in return_events for r in own), "退回缺真实事件顺序")
            before = [r for r in own if return_events[return_lines[r["return_line_id"]]["return_id"]] < event["id"]]
            qty = line["quantity_milli"] - sum(r["quantity_milli"] for r in before)
            amount = line["installation_cents"] - sum(r["installation_cents"] for r in before)
            require(qty >= 0 and amount >= 0, "安装原冻结量价不守恒")
            if not qty:
                continue
            totals[line["work_code"] + " · " + line["work_name"]] += amount
            expected.append(record([c["number"], src["store"], day, line["name"], line["work_name"], quantity(qty), line["unit"], yuan(amount)], c["id"], amount_cents=amount, quantity_milli=qty))
    compare_table(data, "retail_installation", expected, ("values", "route", "amount_cents", "quantity_milli"))
    own = [r for r in expected if r["route"]["id"] == src["fixed"]["retail"]]
    own_work = [r for r in lines if r["case_id"] == src["fixed"]["retail"] and r["work_item_id"]]
    own_events = [r for r in events if r["case_id"] == src["fixed"]["retail"] and r["action"] == "retail_install"]
    technician = e.manifest["users"][e.manifest["business_fixtures"]["repair"]["technician_key"]]["id"]
    require(len(own_work) == len(own) == 1 and own_work[0]["quantity_milli"] == own[0]["quantity_milli"] == 1000
            and own_work[0]["installation_cents"] == own[0]["amount_cents"] == 500
            and len(own_events) == 1 and own_events[0]["id"] == src["refs"][BT]["installation_event_id"]
            and own_events[0]["actor_id"] == technician, "本轮有安装作业的原商品与真实技师事件不符")
    chart_db(data, "retail_installation", totals, "冻结金额")
    require(data["metrics"]["retail_installation_basis_cents"] == sum(totals.values()), "安装收费依据KPI错误")
    return expected, {"actual_technician_event_not_customer_income": True}


def benefit_facts(e, data, src, kind):
    cs = cases(e)
    entries = rows(e, "benefit_entries")
    wallets = {r["id"]: r for r in rows(e, "benefit_wallets")}
    rules = {r["id"]: r for r in rows(e, "benefit_rules")}
    expected, totals, used = [], Counter(), []
    for entry in entries:
        rule = rules[wallets[entry["wallet_id"]]["rule_id"]]
        day = local_time(entry["occurred_at"]).date().isoformat()
        if rule["kind"] != kind or not inside(day, src["period"]):
            continue
        action = PURPOSES.get(entry["purpose"], entry["purpose"])
        totals[action] += entry["units"]
        number = cs[entry["case_id"]]["number"] if entry["case_id"] in cs else ""
        expected.append(record([day, src["store"], number, rule["name"] + " / " + str(rule["rule_version"]), action, entry["units"]], entry["case_id"], units=entry["units"]))
        used.append(entry["id"])
    key = "benefit_" + kind
    compare_table(data, key, expected, ("values", "route", "units"))
    chart_db(data, key, totals, "变动数量（" + ("积分" if kind == "points" else "张") + "）", "count")
    require(expected, "本次原权益单位账不能以空表通过")
    selected = src["refs"][PTS]
    member = src["refs"][MF]
    if kind == "points":
        require({selected[k] for k in ("earned_points_entry_id", "points_adjust_entry_id", "independent_points_grant_entry_id", "points_exchange_out_entry_id")}
            | {member["points_grant_entry_id"], member["points_recovery_entry_id"]} <= set(used), "消费/扣减/独立赠分/兑换及组合原Entry缺失")
    else:
        required = {src["refs"][BT]["coupon_purchase_entry_id"], selected["points_exchange_in_entry_id"], selected["direct_coupon_grant_entry_id"],
                    member["paid_coupon_purchase_entry_id"], member["paid_coupon_refund_entry_id"]}
        finite = {*member["bundle_grant_entry_ids"], *member["bundle_recovery_entry_ids"], *member["benefit_capture_entry_ids"],
                  *src["refs"][BT]["benefit_capture_entry_ids"]}
        coupon_entries = {r["id"] for r in entries if r["id"] in finite and rules[wallets[r["wallet_id"]]["rule_id"]]["kind"] == "coupon"}
        required |= coupon_entries
        require(required <= set(used), "原实购/兑换/独立赠券及本轮赠券核销退款来源不足")
        purchase = one(e, "benefit_entries", member["paid_coupon_purchase_entry_id"])
        refund = one(e, "benefit_entries", member["paid_coupon_refund_entry_id"])
        require(purchase["purpose"] == "purchase" and refund["purpose"] == "refund" and purchase["wallet_id"] == refund["wallet_id"]
            and refund["original_id"] == purchase["id"] and refund["cash_id"] is not None, "原付费券实退未引用同批实际购买/现金")
        for report in (member, src["refs"][BT]):
            captured = [one(e, "benefit_entries", key) for key in report["benefit_capture_entry_ids"]]
            require(any(r["purpose"] == "capture" and r["case_id"] == report["retail_case_id"] and r["id"] in used for r in captured),
                    "本轮独立精品券核销来源未呈现")
    return expected, {"finite_entry_ids": used, "reservations_not_units_or_cash": True,
        "uncreated_reverse_or_restore_branch": "not_tested"}


def consumption_facts(e, data, src):
    cs, changes = cases(e), rows(e, "membership_points_changes")
    expected, totals = [], defaultdict(int)
    for c in changes:
        day = local_time(c["occurred_at"]).date().isoformat()
        if inside(day, src["period"]):
            totals[src["store"]] += c["units"]
            expected.append(record([cs[c["case_id"]]["number"], src["store"], day, c["units"], yuan(c["basis_cents"])], c["case_id"], units=c["units"]))
    compare_table(data, "membership_points", expected, ("values", "route", "units"))
    target = one(e, "membership_points_changes", src["refs"][PTS]["points_change_id"])
    require(target["units"] == 9 and any(r["route"]["id"] == target["case_id"] and r["units"] == 9 for r in expected), "消费积分原增量被赠分替代")
    chart_db(data, "membership_points", totals, "积分", "count")
    bychange = {r["id"]: r for r in changes}
    payments = rows(e, "membership_points_debt_payments")
    debts, debt_totals = [], defaultdict(int)
    for d in rows(e, "membership_points_debts"):
        if d["change_id"] not in bychange:
            continue
        outstanding = d["units"] - sum(p["units"] for p in payments if p["debt_id"] == d["id"])
        if not outstanding:
            continue
        c = cs[bychange[d["change_id"]]["case_id"]]
        debt_totals[src["store"]] += outstanding
        debts.append(record([c["number"], src["store"], d["units"], outstanding], c["id"], units=outstanding, debt_id=d["id"]))
    compare_table(data, "membership_points_debts", debts, ("values", "route", "units", "debt_id"))
    chart_db(data, "membership_points_debts", debt_totals, "积分", "count")
    require(data["metrics"]["membership_points_change_units"] == sum(totals.values())
        and data["metrics"]["membership_points_debt_units"] == sum(debt_totals.values()), "消费积分或当前欠额KPI错误")
    return expected, {"point_change_id": target["id"], "full_current_debt_rows": len(debts), "nonempty_debt_branch": "not_tested"}


async def cached_table(e, data, key):
    before = e.business_snapshot("before_remaining_chart_detail")
    chart = next(c for c in data["charts"] if c["table"] == key)
    target = e.page.locator("#main .chartpanel").filter(has=e.page.get_by_role("heading", name=chart["title"], exact=True))
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/flow/analytics") as pending:
        await click(e, target.locator('[data-act="charttable"][data-table="' + key + '"]'), "从原图查看全部明细")
    response = await pending.value
    refreshed = await response.json()
    await native_response(e, response, {"date_from": data["date_from"], "date_to": data["date_to"]})
    require(refreshed["tables"][key] == data["tables"][key] and refreshed["metrics"] == data["metrics"], "原图明细与同范围原表/KPI不同")
    await expect(e.page).to_have_url(re.compile("#table/" + key + "$"))
    await expect(e.page.locator("#main h1")).to_have_text(data["tables"][key]["title"])
    e.business_unchanged(before, "after_remaining_chart_detail")


async def visible_kpis(e, data, section):
    # Only metrics actually present on the original page are UI KPIs. Report
    # fact-specific totals above are independently compared with the database.
    groups = {
        "sales": (("new_orders", "新增车辆订单", "单"), ("delivery_cents", "车辆交付金额", "元"),
                  ("delivery_margin_cents", "车辆直接毛差", "元"), ("cohort_rate", "同批接待转订单率", "%")),
        "materials": (("material_cost_cents", "当前物资库存成本", "元"), ("task_count", "当前未完成任务", "项")),
        "customers": (("cohort_receptions", "本期接待记录", "次"), ("cohort_orders", "同批转订单", "次"),
                      ("cohort_rate", "同批接待转订单率", "%")),
        "members": (("member_count", "会员档案", "人"), ("member_balance_cents", "当前储值余额", "元")),
    }
    shown = {}
    before = e.business_snapshot("before_original_visible_report_kpis")
    for key, label, unit in groups[section]:
        value = data["metrics"][key]
        number = "—" if value is None else format(Decimal(value) / 100, ",.2f") if key.endswith("_cents") else format(Decimal(str(value)), ",.3f").rstrip("0").rstrip(".")
        card = e.page.locator("#main .kpi").filter(has=e.page.get_by_text(label, exact=True))
        await expect(card.locator(".value")).to_have_text(number + unit)
        shown[key] = {"value": value, "label": label, "unit": unit}
    e.business_unchanged(before, "after_original_visible_report_kpis")
    return shown


async def vehicle_drill(e, data, row):
    key = "customer_vehicle_stats"
    target = panel(e, data, key, "flow")
    index = data["tables"][key]["rows"].index(row)
    await first_page(e, target)
    for page_no in range(2, index // 50 + 2):
        await click(e, target.locator('[data-act="page"][data-page="' + str(page_no) + '"]'), "翻页定位本次客户车辆")
        await expect(target.locator(".pagination span")).to_contain_text("第 " + str(page_no) + " 页")
    cv = one(e, "care_customer_vehicles", row["route"]["id"])
    before = e.business_snapshot("before_current_customer_vehicle_drill")
    path = "/api/customer-service/vehicles/" + str(cv["id"])
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
        await click(e, target.locator("tbody tr").nth(index % 50).locator('[data-act="drill"]'), "查看本轮客户车辆原关系")
    response = await pending.value
    body = await response.json()
    await native_response(e, response, {})
    require(body["vehicle"]["id"] == cv["id"] and body["vehicle"]["vin"] == cv["vin"]
        and body["vehicle"]["vehicle_identity_id"] == cv["vehicle_identity_id"], "身份报表钻取错车/关系")
    await expect(e.page.locator("#main")).to_contain_text(cv["vin"])
    e.business_unchanged(before, "after_current_customer_vehicle_drill")
    return {"customer_vehicle_id": cv["id"], "vehicle_identity_id": cv["vehicle_identity_id"], "vin": cv["vin"], "native_get_status": 200}


async def flow_check(e, cp, src, key, table_key, section, chart_key, oracle, target_id):
    cp.start(key)
    data = await open_report(e, key, "table/" + table_key, src["period"])
    expected, db = oracle(e, data, src)
    require(expected, "本项原主表无真实来源")
    if key == "HK-164":
        target = one(e, "care_customer_vehicles", target_id)
        row = next(r for r in data["tables"][table_key]["rows"] if r["values"][0] == "GV-" + str(target["vehicle_identity_id"]))
    else:
        row = next(r for r in data["tables"][table_key]["rows"] if r["route"]["id"] == target_id)
    shown = [await verify_table(e, data, table_key, "flow")]
    downloads = [await export_csv(e, src["actor"], data, table_key, "flow", src["period"])]
    drill = await vehicle_drill(e, data, row) if key == "HK-164" else await drill_original(e, data, table_key, row, "flow", cases(e)[target_id])
    data = await open_report(e, key, "table/" + table_key, src["period"])
    second_expected, _ = oracle(e, data, src)
    compare(second_expected, expected, "原单钻取后同范围来源")
    graphic = await flow_chart(e, section, chart_key, data, src["period"])
    kpis = await visible_kpis(e, data, section)
    await cached_table(e, data, table_key)
    shown.append(await verify_table(e, data, table_key, "flow"))
    downloads.append(await export_csv(e, src["actor"], data, table_key, "flow", src["period"]))
    cp.note(original_tables=shown, original_csv=downloads, chart=graphic, visible_kpis=kpis, db=db, original_drill=drill,
        whole_authorized_period_oracle=True, period=src["period"], source_ids=src["fixed"])
    await cp.passed(experience=await experience(e))


async def visit_check(e, cp, src):
    cp.start("HK-166")
    data = await open_report(e, "HK-166", "visit-activity", src["period"])
    require(data["complete"] == (not data["tables"]["visit_source_issues"]["rows"]), "全范围缺源与完整标志不匹配")
    whole = {"complete": data["complete"], "issues": data["tables"]["visit_source_issues"]["rows"], "metrics": data["metrics"]}
    before = e.business_snapshot("before_actual_repair_visit_filter")
    cid = src["fixed"]["repair"]
    e.action("select", "仅筛本轮已知实际维修原单", case_id=cid)
    await e.page.locator('#visit-activity-filters [name="case_id"]').select_option(str(cid))
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/visit-activity-reports") as pending:
        await click(e, e.page.locator('#visit-activity-filters button[type="submit"]'), "筛选本轮实际到店与接车")
    response = await pending.value
    data = await response.json()
    await native_response(e, response, {**src["period"], "case_id": cid})
    await expect(e.page.locator("#main .loading")).to_have_count(0)
    e.business_unchanged(before, "after_actual_repair_visit_filter")
    refs = src["refs"][REP]
    repair, intake = cases(e)[cid], cases(e)[refs["intake_case_id"]]
    ap = one(e, "intake_appointments", refs["appointment_id"])
    arrivals = [r for r in rows(e, "intake_arrivals") if r["appointment_id"] == ap["id"]]
    releases = [r for r in rows(e, "flow_events") if r["case_id"] == cid and r["action"] == "repair_v4_release"]
    require(len(arrivals) == len(releases) == 1 and ap["repair_case_id"] == cid and ap["case_id"] == intake["id"], "实际进出来源不是本轮同一维修")
    arrival, release = arrivals[0], releases[0]
    binding = one(e, "intake_vehicle_bindings", cid)
    for case_id, evidence_id in ((intake["id"], arrival["evidence_id"]), (cid, repair["data"]["release_evidence_id"])):
        asset = one(e, "flow_files", evidence_id)
        require(asset["case_id"] == case_id and asset["store_id"] == 1, "到店/接车原件串店串单")
    require(arrival["checked_vin"] == binding["vin"] == refs["vin"] and binding["customer_vehicle_id"] == refs["customer_vehicle_id"], "实际核验VIN或车辆关系错误")
    at, left = local_time(arrival["occurred_at"]), local_time(release["occurred_at"])
    require(left >= at and inside(at.date().isoformat(), src["period"]) and inside(left.date().isoformat(), src["period"])
        and repair["data"]["released_date"] == left.date().isoformat(), "实际进出时间/期间/接车日错误")
    expected = [record([src["store"], intake["number"], repair["number"], at.strftime("%Y-%m-%d %H:%M:%S"), "进厂", "普通维修", refs["vin"], "实际到店记录", arrival["id"]], cid,
        count=1, direction="进厂", source_id=arrival["id"], source_table="intake_arrivals"),
        record([src["store"], intake["number"], repair["number"], left.strftime("%Y-%m-%d %H:%M:%S"), "出厂", "维修客户接车", refs["vin"], "原业务事件", release["id"]], cid,
        count=1, direction="出厂", source_id=release["id"], source_table="flow_events")]
    compare_table(data, "service_gate_movements", expected, ("values", "route", "count", "direction", "source_id", "source_table"))
    cohort = [record([src["store"], intake["number"], repair["number"], at.strftime("%Y-%m-%d %H:%M:%S"), left.strftime("%Y-%m-%d %H:%M:%S"), "已有实际离场记录", int((left - at).total_seconds() // 60)], cid, count=1, closed=True)]
    compare_table(data, "service_visit_cohort", cohort, ("values", "route", "count", "closed"))
    require(data["filters"]["case_id"] == cid and data["complete"] is True
        and data["metrics"]["service_actual_arrivals"] == data["metrics"]["service_actual_departures"] == 1
        and data["metrics"]["service_arrival_cohort_without_departure"] == 0
        and not data["tables"]["gate_corrections"]["rows"] and not data["tables"]["visit_source_issues"]["rows"], "限定原维修范围未闭合或伪造Gate纠正")
    chart_db(data, "service_gate_movements", {at.date().isoformat() + " 进厂": 1, left.date().isoformat() + " 出厂": 1}, "实际记录次数", "count")
    for label, value in (("实际到店次数", 1), ("实际离场次数", 1), ("到店批次尚无离场记录", 0)):
        card = e.page.locator(".kpi").filter(has=e.page.get_by_text(label, exact=True))
        await expect(card.locator(".value")).to_have_text(str(value) + "次")
    shown, downloads = [], []
    for key in ("service_gate_movements", "service_visit_cohort", "gate_corrections", "visit_source_issues"):
        shown.append(await verify_table(e, data, key, "visit"))
        downloads.append(await export_csv(e, src["actor"], data, key, "visit", src["period"]))
    graphic = await graph(e, data, "service_gate_movements")
    chart = next(c for c in data["charts"] if c["id"] == "service_gate_movements")
    chart_panel = e.page.locator("#main > section.panel").filter(has=e.page.get_by_role("heading", name=chart["title"], exact=True))
    downloads.append(await export_csv(e, src["actor"], data, "service_gate_movements", "visit", src["period"],
        locator=chart_panel.locator('[data-act="va-export"][data-key="service_gate_movements"]')))
    appearance = await experience(e)
    drill = await drill_original(e, data, "service_gate_movements", data["tables"]["service_gate_movements"]["rows"][0], "visit", repair)
    await cp.passed(whole_scope_coverage=whole, original_tables=shown, original_csv=downloads, chart=graphic,
        original_drill=drill, actual_arrival_id=arrival["id"], actual_release_event_id=release["id"],
        source_ids=src["fixed"], limited_scope_does_not_claim_full_history=True, experience=appearance)


async def points_check(e, cp, src):
    cp.start("HK-168")
    before = e.business_snapshot("before_original_points_report_entry")
    await nav(e, "module/analytics", "统计分析", None)
    await e.fill("#mux-query", "HK-168", "查找原会员积分统计")
    await click(e, e.page.locator('[data-mux-open="wf-report-168"]'), "打开原会员积分统计")
    await expect(e.page).to_have_url(re.compile("#analytics/members$"))
    await expect(e.page.locator("#datefilters")).to_be_visible()
    data = await refresh_report(e, "/api/flow/analytics", src["period"])
    await expect(e.page.locator("#main h1")).to_have_text("数据可视化")
    e.business_unchanged(before, "after_original_points_report_entry")
    _, units_db = benefit_facts(e, data, src, "points")
    _, change_db = consumption_facts(e, data, src)
    kpis = await visible_kpis(e, data, "members")
    shown, downloads, graphics, drills = [], [], [], []
    for index, key in enumerate(("benefit_points", "membership_points", "membership_points_debts")):
        if index:
            await flow_chart(e, "members", key, data, src["period"])
        graphics.append(await graph(e, data, key))
        await cached_table(e, data, key)
        shown.append(await verify_table(e, data, key, "flow"))
        downloads.append(await export_csv(e, src["actor"], data, key, "flow", src["period"]))
        if key != "membership_points_debts":
            target = src["fixed"]["points_retail"]
            row = next(r for r in data["tables"][key]["rows"] if r["route"]["id"] == target)
            drills.append(await drill_original(e, data, key, row, "flow", cases(e)[target]))
            data = await open_report(e, "HK-169", "table/benefit_coupon", src["period"])
    await cp.passed(original_tables=shown, original_csv=downloads, charts=graphics, original_drills=drills,
        benefit_points_db=units_db, actual_consumption_db=change_db, visible_kpis=kpis, source_ids=src["fixed"],
        independent_units_and_current_debt=True, experience=await experience(e))


async def report_sales_customer(e, context, credentials):
    cp = Checkpoint(e, A)
    try:
        src = source_facts(e, cp)
        src["actor"] = await login_as(e, context, credentials, "manager", "work", 1)
        await e.page.set_viewport_size({"width": 1440, "height": 1000})
        await flow_check(e, cp, src, "HK-139", "addon_actual_facts", "sales", "addon_actual_facts", addon_facts, src["fixed"]["addon"])
        await flow_check(e, cp, src, "HK-140", "service_fee_facts", "sales", "service_fee_facts", service_facts, src["fixed"]["agency"])
        await flow_check(e, cp, src, "HK-164", "customer_vehicle_stats", "customers", "customer_vehicle_stats", vehicle_facts, src["fixed"]["customer_vehicle"])
        await flow_check(e, cp, src, "HK-165", "callbacks", "customers", "callback_state", callback_facts, src["fixed"]["sales_callback"])
        await visit_check(e, cp, src)
        cp.finish()
    except BaseException as error:
        cp.failed(error)
        raise


async def report_boutique_points(e, context, credentials):
    cp = Checkpoint(e, B)
    try:
        src = source_facts(e, cp)
        src["actor"] = await login_as(e, context, credentials, "manager", "work", 1)
        await e.page.set_viewport_size({"width": 1440, "height": 1000})
        await flow_check(e, cp, src, "HK-154", "retail_settlements", "materials", "retail_settlements", retail_facts, src["fixed"]["retail"])
        await flow_check(e, cp, src, "HK-156", "retail_installation", "materials", "retail_installation", installation_facts, src["fixed"]["retail"])
        await points_check(e, cp, src)
        await flow_check(e, cp, src, "HK-169", "benefit_coupon", "members", "benefit_coupon",
            lambda e, d, s: benefit_facts(e, d, s, "coupon"), src["refs"][PTS]["direct_coupon_grant_case_id"])
        cp.finish()
    except BaseException as error:
        cp.failed(error)
        raise


REPORT_REMAINING_SCENARIOS = ((A, report_sales_customer, 720), (B, report_boutique_points, 720))
