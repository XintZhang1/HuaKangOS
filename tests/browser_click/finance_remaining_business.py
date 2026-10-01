"""Six original finance closures, consuming only this run's passed facts.

Three declared reference errors use visible correction forms and independent
review. Completed agency, income and cancellation sources are read, never paid
again. SQL is SELECT-only; credentials, file bodies and hashes of passwords are
not reported. No application imports or positive request replay.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import uuid

from playwright.async_api import expect

from sales_business import login_as, require
from sales_order_business import checkpoint_evidence, fixed_dependency, fen_text
from vehicle_purchase_business import live_choice, select_value
import finance_business as FB
import sales_order_business as SALE
import sales_followon_business as FOLLOW
import customer_followon_business as CARE
import repair_claims_business as CLAIMS
import retail_remaining_business as RETAIL
import sales_pdi_business as PDI


SCENARIO = "finance-remaining-hk076-078-081-086-088-092"
REQUIREMENTS = (("HK-076", "代办服务收款"), ("HK-078", "整车收款单调整"),
                ("HK-081", "维修收款单调整"), ("HK-086", "物资收款单调整"),
                ("HK-088", "其它收入单收款"), ("HK-092", "收款单退款申请"))
CRITERIA = {
    "HK-076": ["原代办独立本版核价、授权和实际外部办结", "服务费2500/代缴1000分原到账分桶及实际代缴1000分、原款保护"],
    "HK-078": ["首次原款前BANK/ENTRY说明及同轮交付VIN/第一笔5000000分来源", "财务原申请、不同主管批准、本人同额重记；第二笔和交车不变"],
    "HK-081": ["新核赔客户承担1000分原款与事前BANK/ENTRY说明，其他承担分开", "独立批准和财务真实更正，原施工/接车及保险厂家原款不变"],
    "HK-086": ["原Retail总款2500/原实退1000/剩余1500分与事前凭据一致", "冲正/重记Cash各2500、分配各1500；唯一冻结原退款切片，不再次退款或出库"],
    "HK-088": ["客户其它收入独立原履约与真实6000分到账", "厂家10000分真实收款、两版独立批准目标7000、原账户实退3000分，各自原源留存"],
    "HK-092": ["另一原未交付销售申请退订和不同主管批准", "原定金300000分按原account/original_id实退300000分，净额0且本单无出库"],
}
TABLES = FB.TABLES | {"business_finance_corrections", "business_finance_correction_bases",
    "business_finance_correction_refund_slices", "repair_payments", "retail_payments"}
READ_TABLES = TABLES | {"flow_customers", "users", "stores", "repair_allocations", "repair_settlements",
    "vehicle_income_orders", "vehicle_income_cash", "vehicle_income_revisions", "vehicle_income_decisions",
    "service_pass_entries", "sales_quotes", "retail_orders", "retail_returns", "retail_return_postings"}
VERSION = {"version", "updated_at"}
SOURCE_COLUMNS = VERSION | {"state", "completed_date", "cost_cents"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def one(e, table, key):
    require(table in READ_TABLES, "财务有限来源表未核准：" + table)
    found = e.db.rows(f"SELECT * FROM {table} WHERE {FB.pk(table)}=?", (key,))
    require(len(found) == 1, "财务有限原ID缺失或重复：" + table)
    return found[0]


def rows(e, table, field=None, key=None):
    require(table in READ_TABLES and (field is None or field in {"case_id", "basis_id", "cash_id", "allocation_id"}),
            "财务只读查询范围未核准")
    suffix, params = (f" WHERE {field}=?", (key,)) if field else ("", ())
    return e.db.rows(f"SELECT * FROM {table}{suffix} ORDER BY {FB.pk(table)}", params)


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(raw)
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, title in REQUIREMENTS:
            require(catalog[key]["title"] == title and catalog[key]["source_review_status"] == "source_reviewed"
                and any(c["check_id"] == key + "-business" for c in catalog[key]["acceptance_checks"]),
                "原财务需求目录未核准：" + key)
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": [k for k, _ in REQUIREMENTS],
            "complete": False, "passed": False, "source_contract_sha256": self.digest,
            "candidate_sha256": sha(Path(__file__).read_bytes()), "execution": "native_browser_original_forms",
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "full_193_business_acceptance": False, "full_registered_suite_complete": False, "business_accepted": False,
            "human_acceptance": "pending", "requirements": [{"id": k, "title": title, "status": "not_tested",
                "business_accepted": False, "human_criteria": {"simple_flow": "pending", "concise_copy": "pending", "visual_pixels": "pending"},
                "acceptance_checks": [{"id": k + "-business", "check_id": k + "-business", "status": "not_tested",
                    "criteria": CRITERIA[k], "evidence": {}}]} for k, title in REQUIREMENTS],
            "conditional_checks": [{"status": "not_tested", "scope": s} for s in (
                "零元撤错、跨原单重新分配、改期和原账户停用", "在办退款/更正并发、占额及后继再更正",
                "集团/预收/充值更正、真实银行、经营主体策略", "员工体验、PostgreSQL、Linux、真实模型及生产启用")],
            "conditions": {"synthetic_money": True, "real_bank_acceptance": False, "production_acceptance": False,
                "file_scan": "original_structure_only_not_clamav", "positive_http_replay": False}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "running"
        self.active["evidence_action_start"] = len(self.e.actions)
        self.save()

    def note(self, **evidence):
        json.dumps(evidence, ensure_ascii=False)
        self.active["acceptance_checks"][0]["evidence"].update(evidence)
        self.save()

    async def passed(self, **evidence):
        self.note(**evidence)
        await self.e.snapshot(self.active["id"].lower() + "-business", business_ready=True)
        self.active["status"] = self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.active = None
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = self.active["acceptance_checks"][0]["status"] = "failed"
            self.active["acceptance_checks"][0]["error"] = self.e.scrub(error)
        self.report.update(error=self.e.scrub(error), failed_requirement=self.active["id"] if self.active else "same_run_sources")
        self.save()

    def finish(self, sources):
        require(all(r["status"] == r["acceptance_checks"][0]["status"] == "passed" for r in self.report["requirements"]),
                "财务六项原闭包未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=6, passed_requirements=6, report_sources=sources)
        self.save()
        self.e.observe("finance_remaining_original_checkpoint", {"path": str(self.path), "passed_checks": 6,
            "report_sources": sources, "full_193_business_acceptance": False})


class Guard:
    """Protect every old row; permit only this action's finite source columns."""
    def __init__(self, e, label, actor, *, expected, update=None, cases=(), customer=None, new_kind=None):
        self.e, self.label, self.actor = e, label, actor
        self.expected, self.update = dict(expected), update or {}
        self.cases, self.customer, self.kind = set(cases), customer, new_kind
        require(self.expected.keys() | self.update.keys() <= TABLES, "财务动作守卫表范围错误")
        self.before = e.business_snapshot("before_finance_remaining_" + label)
        self.old = {t: rows(e, t) for t in self.expected.keys() | self.update.keys()}

    def finish(self):
        after = self.e.business_snapshot("after_finance_remaining_" + self.label)
        changed = {t for t in self.before["tables"].keys() | after["tables"].keys()
            if self.before["tables"].get(t) != after["tables"].get(t)}
        require(changed <= self.expected.keys() | self.update.keys(), "财务更正改变无关原表：" + str(sorted(changed)))
        added, updated = {}, {}
        for table, old in self.old.items():
            current = {r[FB.pk(table)]: r for r in rows(self.e, table)}
            old_ids = {r[FB.pk(table)] for r in old}
            added[table] = [r for key, r in current.items() if key not in old_ids]
            updated[table] = []
            for original in old:
                key = original[FB.pk(table)]
                require(key in current, "财务更正删除旧原行：" + table)
                columns = {k for k in original if original[k] != current[key][k]}
                require(columns <= self.update.get(table, {}).get(key, set()),
                    "财务更正覆盖无关旧行/列：" + table + "/" + str(key) + "/" + str(sorted(columns)))
                if columns:
                    updated[table].append({"id": key, "columns": sorted(columns)})
        require({t: len(v) for t, v in added.items() if v} == {t: n for t, n in self.expected.items() if n},
                "财务原事实新增数不符：" + str({t: len(v) for t, v in added.items() if v}))
        new_cases = added.get("flow_cases", [])
        if new_cases:
            require(len(new_cases) == 1 and new_cases[0]["kind"] == self.kind == "business_finance"
                and new_cases[0]["flow_version"] == 2 and new_cases[0]["customer_id"] == self.customer
                and new_cases[0]["created_by"] == new_cases[0]["owner_id"] == self.actor["id"], "财务新原单身份或客户不符")
        owned = self.cases | {r["id"] for r in new_cases}
        for table, additions in added.items():
            for row in additions:
                if "store_id" in row:
                    require(row["store_id"] == 1, "财务新增事实串店：" + table)
                if "case_id" in row:
                    require(row["case_id"] in owned, "财务新增事实串原单：" + table)
                if "source_case_id" in row:
                    require(row["source_case_id"] in owned, "原退款切片串来源")
                if "customer_id" in row:
                    require(row["customer_id"] == self.customer, "财务新增事实串客户")
                for field in ("actor_id", "created_by", "requested_by"):
                    if field in row:
                        require(row[field] == self.actor["id"], "财务新增事实借用身份：" + table)
                if table == "audit_logs":
                    require(row["entity_type"] == "flow" and row["entity_id"] in owned, "财务新增审计串原单")
                if table == "repair_payments":
                    require(one(self.e, "repair_allocations", row["allocation_id"])["case_id"] in owned
                        and one(self.e, "flow_payment_links", row["payment_link_id"])["case_id"] in owned, "维修更正付款串承担来源")
                if "batch_id" in row:
                    require(one(self.e, "business_finance_cash_batches", row["batch_id"])["case_id"] in owned, "财务分配串批次")
                if "basis_id" in row:
                    require(one(self.e, "business_finance_correction_bases", row["basis_id"])["case_id"] in owned, "财务退款切片串冻结依据")
        self.added = added
        result = {"label": self.label, "changed_tables": sorted(changed), "expected_append_counts": self.expected,
            "appended_ids": {t: [r[FB.pk(t)] for r in v] for t, v in added.items() if v}, "updated_columns": updated,
            "all_other_tables_unchanged": True, "all_other_old_rows_unchanged": True}
        self.e.observe("finance_remaining_finite_guard", result)
        return result


async def native_identity(e, fixture, role, operation):
    responses = []
    def observe(response):
        if response.request.method == "POST" and urlsplit(response.url).path == "/api/auth/login":
            responses.append(response)
    e.page.on("response", observe)
    try:
        result = await operation()
    finally:
        e.page.remove_listener("response", observe)
    require(responses, "财务缺本人真实登录响应")
    last = None
    for response in responses:
        identity = await response.json()
        known = [r for r in ("manager", "finance") if e.manifest["users"][fixture[r + "_key"]]["id"] == identity["id"]]
        require(response.status == 200 and len(known) == 1 and identity["account_role"] == identity["role"] == known[0]
            and identity["active_store_id"] == 1 and identity["aggregate_scope"] is False and 1 in identity["store_ids"],
            "财务原登录未投影本店本人岗位")
        last = identity
    require(last["id"] == e.manifest["users"][fixture[role + "_key"]]["id"] and last["role"] == role,
            "财务最终登录不是本次办理本人")
    e.observe("finance_remaining_native_actor", {"actor_id": last["id"], "current_role": role, "store_id": 1,
        "native_login_count": len(responses), "aggregate_scope": False})
    return result


def exact_check(parent, key):
    row = next(r for r in parent["requirements"] if r["id"] == key)
    check = row["acceptance_checks"][0]
    require(row["status"] == check["status"] == "passed" and check["check_id"] == key + "-business",
            "前序不是原完整需求check：" + key)
    return checkpoint_evidence(parent, key)


def dependencies(e, cp):
    root, runtime = Path(e.manifest["evidence_root"]).resolve(), Path(e.manifest["runtime_root"]).resolve()
    require(e.manifest.get("synthetic_data_only") is True and root.parent == runtime.parent
        and Path(e.manifest["database_path"]).resolve().is_relative_to(runtime)
        and not root.is_relative_to(Path(e.manifest["source_root"]).resolve()), "财务来源不是本轮外部合成实例")
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    require(provenance["snapshot_stable"] is True, "本轮镜像未冻结")
    for filename in (Path(__file__).name, "business_acceptance_catalog.json", "finance_business.py", "sales_business.py",
        "sales_order_business.py", "sales_followon_business.py", "customer_followon_business.py",
        "repair_claims_business.py", "retail_remaining_business.py", "sales_pdi_business.py", "vehicle_purchase_business.py"):
        require(provenance["script_files"].get(filename) == sha(Path(__file__).with_name(filename).read_bytes()),
            "本轮候选/helper指纹改变：" + filename)
    names = (PDI.SCENARIO, CLAIMS.SCENARIO, RETAIL.SCENARIO, FOLLOW.SCENARIO, CARE.SCENARIO, SALE.CANCELLATION_SCENARIO)
    parents = {name: fixed_dependency(e, cp, name) for name in names}
    for name, parent in parents.items():
        require(parent.get("provenance") == cp.report["provenance"] and parent["candidate_sha256"] == provenance["script_files"][{
            PDI.SCENARIO: "sales_pdi_business.py", CLAIMS.SCENARIO: "repair_claims_business.py", RETAIL.SCENARIO: "retail_remaining_business.py",
            FOLLOW.SCENARIO: "sales_followon_business.py", CARE.SCENARIO: "customer_followon_business.py", SALE.CANCELLATION_SCENARIO: "sales_order_business.py"}[name]],
            "完整父候选字节或有限运行来源改变：" + name)
    for name, keys in ((PDI.SCENARIO, ("HK-037", "HK-075")), (CLAIMS.SCENARIO, ("HK-035", "HK-036", "HK-039", "HK-040", "HK-041")),
        (RETAIL.SCENARIO, ("HK-063", "HK-067")), (FOLLOW.SCENARIO, ("HK-015", "HK-017")),
        (CARE.SCENARIO, ("HK-100",)), (SALE.CANCELLATION_SCENARIO, ("HK-010",))):
        for key in keys:
            exact_check(parents[name], key)
    fixture = dict(e.manifest["business_fixtures"]["sales_order"])
    require(fixture["store_id"] == 1, "财务来源店不是本轮一店")
    for role in ("manager", "finance"):
        actor = e.manifest["users"][fixture[role + "_key"]]
        require(actor["role"] == role and len(e.db.rows("SELECT user_id FROM user_stores WHERE user_id=? AND store_id=1 AND role=?",
            (actor["id"], role))) == 1 and one(e, "users", actor["id"])["active"] and one(e, "stores", 1)["active"], "缺本店真实本人岗位")
    require(e.manifest["users"][fixture["manager_key"]]["id"] != e.manifest["users"][fixture["finance_key"]]["id"], "不能财务自批")
    require(not e.db.rows("SELECT id FROM business_entity_policies WHERE store_id=1"), "本批不绕经营主体策略")
    cp.report["mirror"] = {k: provenance[k] for k in ("source_sha256", "script_sha256")}
    cp.save()
    return fixture, parents


def declaration(e, parent_name, path_text, digest):
    path = Path(path_text).resolve()
    expected = Path(e.manifest["evidence_root"]).resolve() / parent_name / "synthetic-inputs"
    require(path.parent == expected and path.is_file() and not path.is_relative_to(Path(e.manifest["source_root"]).resolve()),
            "事前合成说明不是同轮父固定外部输入")
    raw = path.read_bytes()
    require(sha(raw) == digest, "事前合成说明字节被改变")
    value = json.loads(raw)
    require(value["schema"] == 1, "误录说明版本不符")
    return value, {"path": str(path), "sha256": digest, "length": len(raw), "same_run_parent": parent_name}


def correction_sources(e, parents):
    pdi_cash_fields = ("id", "store_id", "direction", "category", "amount_cents", "account", "payment_method", "voucher_no", "created_by", "approval_state")

    def matches_parent_cash(current, recorded, domain):
        if domain == "sale":
            require(set(recorded) == set(pdi_cash_fields), "PDI父现金固定十列投影形状不同")
            return {key: current[key] for key in pdi_cash_fields} == recorded
        return current == recorded

    ps = parents[PDI.SCENARIO]["report_sources"]
    cs = parents[CLAIMS.SCENARIO]["report_sources"]
    rs = parents[RETAIL.SCENARIO]["report_sources"]["cash_correction_source"]
    pd, pmeta = declaration(e, PDI.SCENARIO, ps["declaration_path"], ps["declaration_sha256"])
    cd, cmeta = declaration(e, CLAIMS.SCENARIO, cs["declaration_path"], cs["declaration_sha256"])
    rd, rmeta = declaration(e, RETAIL.SCENARIO, rs["before_cash_declaration_path"], rs["before_cash_declaration_sha256"])
    pdi_payments = exact_check(parents[PDI.SCENARIO], "HK-075")
    claims_completion = exact_check(parents[CLAIMS.SCENARIO], "HK-035")["completion"]
    claims_payment = next(p for p in claims_completion["actual_receipts"] if p["party_type"] == "customer")
    retail_payment = exact_check(parents[RETAIL.SCENARIO], "HK-063")["actual_cash"]
    require(pd["scenario"] == PDI.SCENARIO and pd["synthetic_only"] is True and pd["declared_before_new_order_ui"] is True
        and pd["correction_in_this_candidate"] is False and ps["correction_executed"] is False
        and pd["customer_id"] == ps["customer_id"] and pd["vehicle_id"] == ps["vehicle_id"] and pd["account_id"] == ps["account_id"]
        and pd["first"]["amount_cents"] == 5000000 and pd["first"]["correct_bank_reference"] == ps["first_correct_bank_reference"]
        and pd["first"]["deliberate_entry_reference"] == ps["first_misrecorded_reference"], "PDI事前误录和实际有限来源不一致")
    require(cd["synthetic"] is True and cd["correction_executed"] is cs["correction_executed"] is False
        and cd["store_id"] == 1 and cd["repair_case_id"] == cs["repair_case_id"] and cd["customer_id"] == cs["customer_id"]
        and cd["account_id"] == cs["account_id"] and cd["amount_cents"] == 1000
        and cd["correct_bank_reference"] == cs["customer_correct_bank_reference"] and cd["misrecorded_reference"] == cs["customer_misrecorded_reference"],
        "核赔事前客户误录说明或原承担来源不一致")
    require(rd["sample"] == "synthetic_known_reference_misrecord_before_original_cash" and rd["actual_synthetic_receipt_confirmed"] is True
        and rd["intentional_reference_error"] is rs["intentional_reference_error"] is True and rd["correction_executed"] is rs["correction_executed"] is False
        and rd["case_id"] == rs["case_id"] and rd["customer_id"] == rs["customer_id"] and rd["account_id"] == rs["original_account_id"]
        and rd["amount_cents"] == rs["gross_cents"] == 2500 and rs["refunded_cents"] == 1000 and rs["remaining_cents"] == 1500
        and rd["correct_reference"] == rs["correct_reference"] and rd["entered_reference"] == rs["entered_reference"], "Retail事前误录/原退来源不一致")
    specs = [dict(requirement="HK-078", domain="sale", case_id=ps["pdi_order_id"], customer_id=ps["customer_id"],
            cash_id=ps["first_cash_id"], payment_id=ps["first_payment_link_id"], evidence_id=ps["first_evidence_id"], account_id=ps["account_id"],
            gross=5000000, refunded=0, remaining=5000000, correct=ps["first_correct_bank_reference"], entered=ps["first_misrecorded_reference"],
            declared=pmeta, parent_payment=pdi_payments["first_payment"]["payment_link"], parent_cash=pdi_payments["first_payment"]["cash"],
            parent_native=pdi_payments["first_payment"]["native"],
            extra_originals=[{"payment": pdi_payments["second_payment"]["payment_link"], "cash": pdi_payments["second_payment"]["cash"]}]),
        dict(requirement="HK-081", domain="repair", case_id=cs["repair_case_id"], customer_id=cs["customer_id"],
            cash_id=cs["customer_cash_id"], payment_id=cs["customer_payment_link_id"], evidence_id=cs["customer_payment_evidence_id"], account_id=cs["account_id"],
            gross=1000, refunded=0, remaining=1000, correct=cs["customer_correct_bank_reference"], entered=cs["customer_misrecorded_reference"], declared=cmeta,
            parent_payment=claims_payment["payment_link"], parent_cash=claims_payment["cash"], parent_native=claims_payment["native"],
            extra_originals=[{"payment": p["payment_link"], "cash": p["cash"]} for p in claims_completion["actual_receipts"] if p["party_type"] != "customer"]),
        dict(requirement="HK-086", domain="retail", case_id=rs["case_id"], customer_id=rs["customer_id"], cash_id=rs["original_cash_id"],
            payment_id=rs["original_payment_id"], evidence_id=rs["original_receipt_file"]["id"], account_id=rs["original_account_id"],
            gross=2500, refunded=1000, remaining=1500, correct=rs["correct_reference"], entered=rs["entered_reference"], declared=rmeta,
            parent_payment=retail_payment["payment"], parent_cash=retail_payment["cash"], parent_native=retail_payment["native"], extra_originals=[],
            refund_payment_id=rs["refund_payment_id"], refund_cash_id=rs["refund_cash_id"])]
    for s in specs:
        original, payment = one(e, "cash_entries", s["cash_id"]), one(e, "flow_payment_links", s["payment_id"])
        source, account = one(e, "flow_cases", s["case_id"]), one(e, "flow_accounts", s["account_id"])
        require(matches_parent_cash(original, s["parent_cash"], s["domain"]) and payment == s["parent_payment"]
            and s["correct"] != s["entered"] and source["customer_id"] == s["customer_id"] and source["store_id"] == payment["store_id"] == account["store_id"] == 1
            and source["state"] == ("delivered" if s["domain"] == "sale" else "completed")
            and account["active"] and account["account_type"] == "bank"
            and original["direction"] == payment["direction"] == "in" and original["amount_cents"] == payment["amount_cents"] == s["gross"]
            and original["voucher_no"] == payment["reference"] == s["entered"] and payment["cash_id"] == original["id"]
            and payment["account_id"] == account["id"] and payment["case_id"] == source["id"] and payment["original_id"] is None,
            "当前明确原误记现金/付款/账户/客户不符")
        for extra in s["extra_originals"]:
            extra_cash = one(e, "cash_entries", extra["cash"]["id"])
            require(one(e, "flow_payment_links", extra["payment"]["id"]) == extra["payment"]
                and matches_parent_cash(extra_cash, extra["cash"], s["domain"]), "其他独立原款不匹配完整父事实")
            if s["domain"] == "sale":
                extra["parent_cash_projection"] = extra["cash"]
                extra["cash"] = extra_cash
        asset = one(e, "flow_files", s["evidence_id"])
        content = asset.pop("content")
        require(isinstance(content, bytes) and s["correct"].encode() in content and asset["case_id"] == source["id"]
            and asset["category"] == ("evidence" if s["domain"] == "repair" else "receipt")
            and asset["size"] == len(content) and asset["sha256"] == sha(content), "原合成凭据没有事前明确的实际BANK字节")
        if s["refunded"]:
            refund, cash = one(e, "flow_payment_links", s["refund_payment_id"]), one(e, "cash_entries", s["refund_cash_id"])
            require(refund["original_id"] == payment["id"] and refund["cash_id"] == cash["id"]
                and refund["account_id"] == payment["account_id"] and refund["amount_cents"] == cash["amount_cents"] == 1000
                and cash["direction"] == refund["direction"] == "out" and refund["case_id"] == s["case_id"], "原实退1000关联或账户不符")
            s.update(original_refund=refund, original_refund_cash=cash)
        s.update(original_cash=original, original_payment=payment, original_file=asset, original_blob={"length": len(content), "sha256": sha(content)},
                 original_case=source, account=account)
    require(len({s["cash_id"] for s in specs}) == len({s["case_id"] for s in specs}) == 3, "三更正误用同原款/原单")
    return specs


async def read_original(e, context, credentials, fixture, case_id, *, domain="case"):
    route, path = ("case/", "/api/flow/cases/")
    if domain in {"service", "income"}:
        route, path = FOLLOW.ROUTE[domain] + "/", FOLLOW.DOMAIN[domain] + "/"
    path += str(case_id)
    async with e.page.expect_response(lambda r: FB.get_match(r, path)) as pending:
        actor = await native_identity(e, fixture, "finance", lambda: login_as(e, context, credentials, fixture["finance_key"], route + str(case_id), 1))
    response = await pending.value
    shown = await response.json()
    source = one(e, "flow_cases", case_id)
    require(response.status == 200 and shown["id"] == case_id and shown["version"] == source["version"], "原页未读取当前有限原单版本")
    title = "厂家及供应商整车其他收入" if domain == "income" else source["title"]
    await expect(e.page.locator("#main h1")).to_have_text(title)
    await expect(e.page.locator("#main .pagehead")).to_contain_text(source["number"])
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    before = e.business_snapshot("before_finance_remaining_read_refresh")
    async with e.page.expect_response(lambda r: FB.get_match(r, path)) as pending:
        e.action("refresh", "本人刷新原财务来源，不再收付")
        await e.page.reload()
    response = await pending.value
    repeat = await response.json()
    headers = await response.request.all_headers()
    require(response.status == 200 and repeat == shown and headers.get("cookie") and headers.get("x-store-id") == "1", "原页刷新身份/数据范围改变")
    await expect(e.page.locator("#main h1")).to_have_text(title)
    e.business_unchanged(before, "after_finance_remaining_read_refresh")
    return shown, {"path": path, "status": 200, "native_ui": True, "cookie_present": True, "store_id": 1,
        "actor_id": actor["id"], "source_id": case_id, "source_version": source["version"], "refresh_business_unchanged": True}


def original_native(meta):
    require(meta["native_ui"] is True and meta["method"] == "POST" and meta["status"] == 200
        and meta["cookie_present"] is True and meta["csrf_present"] is True and meta.get("request_id_sha256"),
        "父来源没有原本人UI成功/幂等回执证据")
    return {k: meta[k] for k in ("path", "method", "status", "native_ui", "cookie_present", "csrf_present", "request_id_sha256")}


async def agency_closure(e, context, credentials, fixture, parent):
    evidence, sources = exact_check(parent, "HK-015"), parent["report_sources"]
    key = sources["agency_case_id"]
    require(key == evidence["case_id"], "代办不是完整父原单")
    view, native = await read_original(e, context, credentials, fixture, key, domain="service")
    f = FB.service_facts(e, key)
    paid = evidence["collection"]
    payment, cash = one(e, "flow_payment_links", paid["payment_link"]["id"]), one(e, "cash_entries", paid["cash"]["id"])
    third, out = one(e, "service_pass_entries", evidence["thirdparty"]["id"]), one(e, "cash_entries", evidence["thirdparty_cash"]["id"])
    require(payment == paid["payment_link"] and cash == paid["cash"] and third == evidence["thirdparty"] and out == evidence["thirdparty_cash"]
        and payment["case_id"] == third["case_id"] == key and payment["cash_id"] == cash["id"]
        and cash["amount_cents"] == payment["amount_cents"] == 3500 and cash["direction"] == payment["direction"] == "in"
        and third["amount_cents"] == out["amount_cents"] == 1000 and out["direction"] == "out"
        and third["cash_id"] == out["id"] and f["case"]["state"] == "completed"
        and not [t for t in f["tasks"] if t["status"] == "open"], "代办原到账/实付/结束事实不符")
    tenders = [t for t in f["tenders"] if t["payment_link_id"] == payment["id"]]
    require(len(tenders) == 2 and {(t["bucket"], t["amount_cents"]) for t in tenders} == {("fee", 2500), ("pass", 1000)}
        and view["summary"]["customer_paid_cents"] == 3500 and view["summary"]["customer_due_cents"] == 0
        and view["summary"]["thirdparty_paid_cents"] == 1000 and view["summary"]["pass_cash_balance_cents"] == 0,
        "代办服务费与代缴本金分桶或余款不符")
    return {"case_id": key, "current_original_api": view, "original_page": native, "payment": payment, "cash": cash,
        "tenders": tenders, "actual_disbursement": third, "thirdparty_cash": out,
        "parent_collection": original_native(paid["native"]["native"]), "parent_disbursement": original_native(evidence["native_disburse"]["native"]),
        "original_price_and_external_fulfillment_preserved": True, "no_duplicate_money": True}


async def other_income_closure(e, context, credentials, fixture, parents):
    customer = exact_check(parents[CARE.SCENARIO], "HK-100")
    key = parents[CARE.SCENARIO]["report_sources"]["income_case_id"]
    view, native = await read_original(e, context, credentials, fixture, key, domain="service")
    received = customer["actual_receive"]
    f = FB.service_facts(e, key)
    payment, cash = one(e, "flow_payment_links", received["payment"]["id"]), one(e, "cash_entries", received["cash"]["id"])
    require(customer["db"]["case"]["id"] == key and f["case"]["kind"] == "other_income" and f["case"]["state"] == "completed"
        and payment == received["payment"] and cash == received["cash"] and payment["case_id"] == key and payment["cash_id"] == cash["id"]
        and payment["direction"] == cash["direction"] == "in" and payment["amount_cents"] == cash["amount_cents"] == 6000
        and view["summary"]["customer_due_cents"] == 0 and len(f["payments"]) == 1 and len(f["tenders"]) == 1
        and f["tenders"][0]["amount_cents"] == 6000 and f["tenders"][0]["bucket"] == "fee", "客户其它收入履约与真实到账不符")
    factory = exact_check(parents[FOLLOW.SCENARIO], "HK-017")["manufacturer"]
    mid = parents[FOLLOW.SCENARIO]["report_sources"]["manufacturer_income_case_id"]
    require(factory["case_id"] == mid, "厂家收入不是同轮独立原来源")
    mview, mnative = await read_original(e, context, credentials, fixture, mid, domain="income")
    incoming, returning = factory["collection"], factory["refund"]
    p, r = one(e, "vehicle_income_cash", incoming["payment"]["id"]), one(e, "vehicle_income_cash", returning["payment"]["id"])
    c, rc = one(e, "cash_entries", incoming["cash"]["id"]), one(e, "cash_entries", returning["cash"]["id"])
    require(p == incoming["payment"] and r == returning["payment"] and c == incoming["cash"] and rc == returning["cash"]
        and p["case_id"] == r["case_id"] == mid and p["cash_id"] == c["id"] and r["cash_id"] == rc["id"]
        and r["original_id"] == p["id"] and p["account_id"] == r["account_id"] and p["direction"] == c["direction"] == "in"
        and r["direction"] == rc["direction"] == "out" and p["amount_cents"] == c["amount_cents"] == 10000
        and r["amount_cents"] == rc["amount_cents"] == 3000 and len(rows(e, "vehicle_income_cash", "case_id", mid)) == 2
        and factory["final_totals"]["target_cents"] == 7000 and mview["totals"] == factory["final_totals"], "厂家独立目标及原账户收退不符")
    return {"customer_income": {"case_id": key, "api": view, "original_page": native, "payment": payment, "cash": cash,
            "parent_native": original_native(received["native"]), "original_fulfillment": customer["quote_approval_authorization_fulfillment"]},
        "manufacturer_income": {"case_id": mid, "api": mview, "original_page": mnative, "original_payment": p, "original_cash": c,
            "refund_payment": r, "refund_cash": rc, "independent_revisions": [factory["first_approval"], factory["second_approval"]],
            "parent_collection": original_native(incoming["native"]["native"]), "parent_refund": original_native(returning["native"]["native"])},
        "two_distinct_original_income_sources": True, "no_duplicate_money": True}


async def cancellation_closure(e, context, credentials, fixture, parent):
    evidence = exact_check(parent, "HK-010")
    key = parent["report_sources"]["cancelled_order_id"]
    view, native = await read_original(e, context, credentials, fixture, key)
    deposit, refund = evidence["deposit"], evidence["refund"]
    p, r = one(e, "flow_payment_links", deposit["payment"]["id"]), one(e, "flow_payment_links", refund["payment"]["id"])
    c, rc = one(e, "cash_entries", deposit["cash"]["id"]), one(e, "cash_entries", refund["cash"]["id"])
    cash_fields = ("id", "store_id", "direction", "category", "amount_cents", "account", "payment_method", "voucher_no", "created_by", "approval_state")
    require(set(deposit["cash"]) == set(refund["cash"]) == set(cash_fields), "退订父现金固定十列投影形状不同")
    require(evidence["case_id"] == key and view["state"] == "cancelled" and p == deposit["payment"] and r == refund["payment"]
        and {field: c[field] for field in cash_fields} == deposit["cash"]
        and {field: rc[field] for field in cash_fields} == refund["cash"] and p["case_id"] == r["case_id"] == key
        and p["cash_id"] == c["id"] and r["cash_id"] == rc["id"] and p["direction"] == c["direction"] == "in"
        and r["direction"] == rc["direction"] == "out" and p["amount_cents"] == r["amount_cents"] == c["amount_cents"] == rc["amount_cents"] == 300000
        and r["original_id"] == p["id"] and p["account_id"] == r["account_id"] and len(rows(e, "flow_payment_links", "case_id", key)) == 2
        and not e.db.rows("SELECT id FROM vehicle_position_entries WHERE case_id=?", (key,))
        and not [t for t in rows(e, "flow_tasks", "case_id", key) if t["status"] == "open"], "退订原申请、批准、原账户实退及净额闭包不符")
    return {"case_id": key, "original_page": native, "original_deposit": p, "original_cash": c, "original_refund": r,
        "refund_cash": rc, "parent_original_cash_projection": deposit["cash"], "parent_refund_cash_projection": refund["cash"],
        "original_cancel_request": evidence["cancel_request"], "independent_cancel_approval": evidence["cancel_approval"],
        "parent_deposit": original_native(deposit["native_payment"]), "parent_refund": original_native(refund["native_payment"]),
        "no_this_cancellation_physical_dispatch": True, "current_vin_may_have_later_independent_order": True, "net_cents": 0}


async def proof(e, case_id, actor, category, spec, phase):
    directory = e.directory / "synthetic-inputs"
    directory.mkdir(exist_ok=True)
    path = directory / (spec["requirement"] + "-" + phase + "-" + uuid.uuid4().hex[:12] + ".txt")
    content = ("仅外部合成银行输入，非真实款项。\n本轮原财务更正单=" + str(case_id)
        + "；原收款单=" + str(spec["case_id"]) + "；原Cash=" + str(spec["cash_id"])
        + "；事前正确BANK=" + spec["correct"] + "；原UI误录ENTRY=" + spec["entered"]
        + "；原总额分=" + str(spec["gross"]) + "；原已退分=" + str(spec["refunded"])
        + "；正确剩余分配分=" + str(spec["remaining"]) + "；本次=" + phase + "\n").encode("utf-8")
    path.write_bytes(content)
    await e.click('#main [data-act="upload"]', "本人选择本次独立原银行核对凭据")
    await expect(e.page.locator("#modal-title")).to_have_text("上传业务文件")
    await select_value(e, '#modal [name="category"]', category, "选择原财务凭据类别")
    e.action("select_file", "选择外部合成原件", name=path.name, sha256=sha(content))
    await e.page.locator('#modal [name="file"]').set_input_files(str(path))
    guard = Guard(e, phase + "_upload", actor, expected={**FB.COMMON, "flow_files": 1, "file_security": 1, "file_scan_events": 1}, cases={case_id})
    body, _, shown, native = await FB.submit(e, f"/api/flow/cases/{case_id}/files", f"{FB.FINANCE}/orders/{case_id}", multipart=True)
    asset = one(e, "flow_files", body["id"])
    stored = asset.pop("content")
    security = one(e, "file_security", asset["id"])
    scans = e.db.rows("SELECT * FROM file_scan_events WHERE file_id=? ORDER BY id", (asset["id"],))
    require(stored == content and asset["sha256"] == sha(content) and asset["size"] == len(content)
        and asset["case_id"] == case_id and asset["category"] == category and asset["created_by"] == actor["id"] and not asset["generated"]
        and body["security"]["can_use"] is True and security["state"] == "structure_only" and len(scans) == 1
        and scans[0]["state"] == "structure_only" and scans[0]["sha256"] == asset["sha256"] and scans[0]["action"] == "initial"
        and scans[0]["actor_id"] == actor["id"], "本次更正凭据字节/类别/真实扫描状态不符")
    FB.finance_view(e, shown, FB.finance_facts(e, case_id))
    await expect(e.page.locator("#main .filerecord").filter(has_text=path.name)).to_have_count(1)
    return {"file": asset, "stored_blob": {"length": len(stored), "sha256": sha(stored)}, "native": native,
        "guard": guard.finish(), "event": FB.events(e, guard, case_id, actor, "upload"), "clamav_acceptance": False}


def update_rows(e, finance_id, spec, action):
    update = FB.mutable(e, {finance_id}, order=FB.finance_facts(e, finance_id)["order"]["id"],
        account=spec["account_id"] if action == "execute" else None)
    if action == "execute" or spec["refunded"] and action == "approve":
        update["flow_cases"][spec["case_id"]] = SOURCE_COLUMNS if action == "execute" else VERSION
    if action == "execute":
        update.setdefault("flow_tasks", {}).update({r["id"]: FB.TASK_COLUMNS for r in rows(e, "flow_tasks", "case_id", spec["case_id"])})
    return update


async def correction_create(e, context, credentials, fixture, spec):
    customer_id = spec["customer_id"]
    async with e.page.expect_response(lambda r: FB.get_match(r, FB.FINANCE + "/sources")
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer_id)]) as pending:
        actor = await native_identity(e, fixture, "finance", lambda: login_as(e, context, credentials, fixture["finance_key"], "business-finance/" + str(customer_id), 1))
    read = await pending.value
    require(read.status == 200, "更正前原客户应收读取失败")
    await read.body()
    await expect(e.page.locator("#main h1")).to_have_text("业务财务结算")
    before_form = e.business_snapshot("before_original_correction_inputs")
    async with e.page.expect_response(lambda r: FB.get_match(r, FB.FINANCE + "/receipts")
            and parse_qs(urlsplit(r.url).query).get("customer_id") == [str(customer_id)]) as pending:
        await FB.original_form(e, "business-finance-create", "correction", "原收款误记更正")
    read = await pending.value
    receipts = await read.json()
    selected = [r for r in receipts["items"] if r.get("cash_id") == spec["cash_id"] and not r.get("source_kind")]
    require(read.status == 200 and len(selected) == 1, "原可见收款候选不含唯一事前误记款")
    r = selected[0]
    require(r["amount_cents"] == spec["gross"] and r["refunded_cents"] == spec["refunded"] and r["net_amount_cents"] == spec["remaining"]
        and r["reference"] == spec["entered"] and r["business_date"] == spec["original_cash"]["business_date"]
        and {x["case_id"] for x in r["sources"]} == {spec["case_id"]}, "原可见候选金额/退款/日期/来源不符")
    label = f'{r["business_date"]} · {r["account"]} · {r["reference"]} · {SALE.displayed_money(r["amount_cents"])}元'
    if spec["refunded"]:
        label += f' · 已实退{SALE.displayed_money(spec["refunded"])}元，剩余{SALE.displayed_money(spec["remaining"])}元'
    await select_value(e, '#modal [name="original"]', label, "员工明确选本轮已查明误录的原收款")
    await expect(e.page.locator('#modal [name="actual_business_date"]')).to_have_value("")
    await live_choice(e, "account_id", spec["account"]["name"], spec["account"]["name"], expected_value=spec["account_id"])
    await e.fill('#modal [name="reference"]', spec["correct"], "填写原合成银行凭据的正确编号")
    await e.fill(f'#modal [name="allocation_{spec["case_id"]}"]', fen_text(spec["remaining"]), "只分配原单扣除已退款后的正确余额")
    controls = e.page.locator('#modal [name^="allocation_"]')
    for index in range(await controls.count()):
        control = controls.nth(index)
        if await control.get_attribute("name") != "allocation_" + str(spec["case_id"]):
            require(await control.input_value() == "0", "更正误分配其他客户原单")
    reason = "事前合成原银行凭据" + spec["correct"] + "与原误录" + spec["entered"] + "不同，仅同额更正编号，保留旧退款与原履约。"
    await e.fill('#modal [name="reason"]', reason, "本人明确误记原因和原银行依据")
    e.business_unchanged(before_form, "after_original_correction_inputs")
    values = {"original_cash_id": spec["cash_id"], "amount_cents": spec["gross"],
        "allocations": [{"source_case_id": spec["case_id"], "amount_cents": spec["remaining"]}],
        "allocation_basis": "remaining_after_refunds", "account_id": spec["account_id"], "reference": spec["correct"]}
    expected = {**FB.FINANCE_COMMON, "flow_cases": 1, "flow_tasks": 1, "business_finance_orders": 1}
    if spec["refunded"]:
        expected.update(business_finance_correction_bases=1, business_finance_correction_refund_slices=1)
    guard = Guard(e, "correction_create", actor, expected=expected, cases={spec["case_id"]}, customer=customer_id, new_kind="business_finance")
    body, request, shown, native = await FB.submit(e, FB.FINANCE + "/orders", FB.FINANCE + "/orders/", status=201)
    require(request == {"request_id": request["request_id"], "customer_id": customer_id, "purpose": "correction", "values": values, "reason": reason},
            "更正创建原封包与明确输入不符")
    key = body["case"]["id"]
    f = FB.finance_facts(e, key)
    require(f["order"]["purpose"] == "correction" and f["order"]["status"] == "draft" and f["order"]["requested_by"] == actor["id"]
        and not f["batches"] and not f["allocations"] and f["order"]["values"]["actual_business_date"] == spec["original_cash"]["business_date"],
        "申请误生成现金或未保留原到账日期")
    FB.finance_view(e, body, f)
    FB.finance_view(e, shown, f)
    await expect(e.page.locator("#main h1")).to_have_text("财务业务办理")
    return key, {"native": native, "guard": guard.finish(), "event": FB.events(e, guard, key, actor, "business_finance_create", finance=True),
        "receipt": FB.receipt(e, request, actor, body, finance_action="create"), "values": values, "db": f}


async def correction_action(e, context, credentials, fixture, finance_id, spec, action):
    role, key = ("manager", "business_finance_review") if action == "approve" else ("finance", "business_finance_execute")
    actor, _, owner = await native_identity(e, fixture, role,
        lambda: FB.responsible(e, context, credentials, fixture, finance_id, key, role, financial=True))
    f = FB.finance_facts(e, finance_id)
    require(action != "approve" or actor["id"] != f["order"]["requested_by"], "原申请人不得自批")
    category = "evidence" if action == "approve" else "receipt"
    uploaded = await proof(e, finance_id, actor, category, spec, action)
    source = one(e, "flow_cases", spec["case_id"])
    title = "独立复核批准" if action == "approve" else "确认批准内容及实际办理"
    async with e.page.expect_response(lambda r: FB.get_match(r, "/api/flow/cases/" + str(spec["case_id"]))) as pending:
        await FB.original_form(e, "business-finance-action", action, title)
    source_response = await pending.value
    actual_source = await source_response.json()
    require(source_response.status == 200 and actual_source["id"] == source["id"] and actual_source["version"] == source["version"], "更正未使用实际原来源GET/current CAS")
    await FB.choose_file(e, uploaded, category)
    reason = "本人核对事前合成BANK/ENTRY差异；保持原总款、原退款和履约，按正确凭据同额重记。"
    await e.fill('#modal [name="reason"]', reason, "本人明确独立复核或实际办理依据")
    values = {"reason": reason, "evidence_id": uploaded["file"]["id"], "source_versions": {str(spec["case_id"]): source["version"]}}
    expected = {**FB.FINANCE_COMMON}
    if action == "approve":
        expected["flow_tasks"] = 1
    else:
        expected.update(cash_entries=2, flow_payment_links=2, business_finance_cash_batches=2,
            business_finance_cash_allocations=2, business_finance_corrections=1)
        if spec["domain"] == "repair":
            expected["repair_payments"] = 2
        elif spec["domain"] == "retail":
            expected["retail_payments"] = 2
    guard = Guard(e, "correction_" + action, actor, expected=expected, update=update_rows(e, finance_id, spec, action),
        cases={finance_id, spec["case_id"]}, customer=spec["customer_id"])
    body, request, shown, native = await FB.submit(e, f"{FB.FINANCE}/orders/{finance_id}/actions/{action}", f"{FB.FINANCE}/orders/{finance_id}")
    require(request == {"request_id": request["request_id"], "version": f["order"]["version"], "case_version": f["case"]["version"], "values": values},
            "更正动作缺完整Order/Case/来源CAS或原输入")
    after = FB.finance_facts(e, finance_id)
    require(after["case"]["version"] > f["case"]["version"] and after["order"]["version"] > f["order"]["version"]
        and after["order"]["values"] == f["order"]["values"] and after["events"][:len(f["events"])] == f["events"]
        and after["finance_events"][:len(f["finance_events"])] == f["finance_events"], "更正覆盖原申请或事件/未追加版本")
    FB.finance_view(e, body, after)
    FB.finance_view(e, shown, after)
    if action == "approve":
        require(after["order"]["status"] == "approved" and after["order"]["approved_by"] == actor["id"] and not after["batches"], "独立批准错误生成资金")
    else:
        require(after["case"]["state"] == "completed" and after["order"]["status"] == "completed"
            and not [t for t in after["tasks"] if t["status"] == "open"], "原更正执行未完整结束")
    await expect(e.page.locator("#main h1")).to_have_text("财务业务办理")
    return after, shown, {"native": native, "guard": guard.finish(), "event": FB.events(e, guard, finance_id, actor, "business_finance_" + action, finance=True),
        "receipt": FB.receipt(e, request, actor, body, finance_action=str(finance_id) + ":" + action), "values": values,
        "file": uploaded, "task_owner": owner, "actor_id": actor["id"]}


def validate_correction(e, finance_id, spec, f, view, executed):
    corrections = rows(e, "business_finance_corrections", "case_id", finance_id)
    require(len(corrections) == 1 and corrections[0]["original_cash_id"] == spec["cash_id"] and len(f["batches"]) == len(f["allocations"]) == 2,
            "更正唯一事实/批次/剩余分配数不符")
    correction = corrections[0]
    reverse = one(e, "business_finance_cash_batches", correction["reversing_batch_id"])
    recorded = one(e, "business_finance_cash_batches", correction["corrected_batch_id"])
    payments = []
    for batch, direction, category, kind in ((reverse, "out", "business_finance_correction_reverse", "correction_reverse"),
            (recorded, "in", "business_finance_corrected", "correction_record")):
        cash = one(e, "cash_entries", batch["cash_id"])
        allocations = [a for a in f["allocations"] if a["batch_id"] == batch["id"]]
        require(len(allocations) == 1, "更正批次缺唯一原单剩余分配")
        allocation = allocations[0]
        payment = one(e, "flow_payment_links", allocation["payment_link_id"])
        require(batch["case_id"] == finance_id and batch["kind"] == kind and batch["amount_cents"] == cash["amount_cents"] == spec["gross"]
            and batch["actor_id"] == cash["created_by"] == executed["actor_id"] and batch["evidence_id"] == executed["file"]["file"]["id"]
            and cash["approval_state"] == "approved" and cash["category"] == category and cash["direction"] == payment["direction"] == direction
            and cash["account"] == spec["account"]["name"] and payment["account_id"] == spec["account_id"]
            and allocation["case_id"] == payment["case_id"] == spec["case_id"] and allocation["amount_cents"] == payment["amount_cents"] == spec["remaining"]
            and allocation["statement_line_id"] is None and payment["cash_id"] == cash["id"] and payment["reference"] == cash["voucher_no"],
            "更正gross现金与net分配、原账户或独立本人不符")
        require(payment["original_id"] == (spec["payment_id"] if direction == "out" else None), "冲正未引用原客户款或重记误冒退款")
        if direction == "in":
            require(cash["voucher_no"] == spec["correct"] and cash["business_date"] == spec["original_cash"]["business_date"], "正确重记凭证或原到账日期不符")
        payments.append({"batch": batch, "allocation": allocation, "payment": payment, "cash": cash})
    require(one(e, "cash_entries", spec["cash_id"]) == spec["original_cash"] and one(e, "flow_payment_links", spec["payment_id"]) == spec["original_payment"],
            "更正覆盖原Cash/PaymentLink")
    for extra in spec["extra_originals"]:
        require(one(e, "flow_payment_links", extra["payment"]["id"]) == extra["payment"]
            and one(e, "cash_entries", extra["cash"]["id"]) == extra["cash"], "更正覆盖其他独立原款")
    source = one(e, "flow_cases", spec["case_id"])
    source_links = rows(e, "flow_payment_links", "case_id", source["id"])
    net = sum(r["amount_cents"] * (1 if r["direction"] == "in" else -1) for r in source_links)
    require(source["state"] == spec["original_case"]["state"]
        and source["state"] == ("delivered" if spec["domain"] == "sale" else "completed")
        and source["completed_date"] == spec["original_case"]["completed_date"],
            "同额更正重开原交付或接车")
    expected_net = 13000000 if spec["domain"] == "sale" else 7000 if spec["domain"] == "repair" else 1500
    require(net == expected_net, "正确重记后原净实收改变")
    basis = rows(e, "business_finance_correction_bases", "case_id", finance_id)
    slices = rows(e, "business_finance_correction_refund_slices", "basis_id", basis[0]["id"]) if basis else []
    if spec["refunded"]:
        require(len(basis) == len(slices) == 1 and basis[0]["original_cash_id"] == spec["cash_id"] and basis[0]["previous_id"] is None
            and basis[0]["original_amount_cents"] == basis[0]["corrected_amount_cents"] == 2500 and basis[0]["refunded_cents"] == 1000
            and slices[0]["refund_payment_id"] == spec["refund_payment_id"] and slices[0]["original_payment_id"] == spec["payment_id"]
            and slices[0]["source_case_id"] == spec["case_id"] and slices[0]["amount_cents"] == 1000
            and one(e, "flow_payment_links", spec["refund_payment_id"]) == spec["original_refund"]
            and one(e, "cash_entries", spec["refund_cash_id"]) == spec["original_refund_cash"], "HK086旧退款切片/gross净额层级不符")
        partial = view["partial_correction"]
        require({k: partial[k] for k in ("basis_version", "original_amount_cents", "corrected_amount_cents", "refunded_cents", "original_net_cents", "corrected_net_cents")}
            == {"basis_version": 2, "original_amount_cents": 2500, "corrected_amount_cents": 2500, "refunded_cents": 1000,
                "original_net_cents": 1500, "corrected_net_cents": 1500} and len(partial["refunds"]) == 1
            and partial["refunds"][0]["payment_id"] == spec["refund_payment_id"], "原页面退款冻结层与DB不符")
    else:
        require(not basis and not slices, "没有旧退款的更正误造退款冻结事实")
    return {"finance_case_id": finance_id, "original_source_id": spec["case_id"], "original_cash": spec["original_cash"],
        "original_payment": spec["original_payment"], "declaration": spec["declared"], "original_file": spec["original_file"],
        "original_blob": spec["original_blob"], "correction": correction, "two_money_facts": payments, "basis": basis, "refund_slices": slices,
        "parent_original_native": original_native(spec["parent_native"]), "other_original_receipts_unchanged": spec["extra_originals"],
        "current_source_case": source, "original_net_cents": net, "original_refund_immutable": True,
        "no_new_physical_or_membership_facts": True, "parent_completion_and_historical_bytes_protected": True}


async def correction_rendered(e, spec):
    frozen = e.page.locator("#main .panel").filter(has=e.page.get_by_role("heading", name="冻结申请与原款", exact=True))
    await expect(frozen).to_have_count(1)
    await expect(frozen).to_contain_text(spec["entered"])
    await expect(frozen).to_contain_text(spec["correct"])
    await expect(frozen).to_contain_text(spec["original_cash"]["business_date"])
    funds = e.page.locator("#main .panel").filter(has=e.page.get_by_role("heading", name="资金记录与原单分配", exact=True))
    await expect(funds).to_have_count(1)
    for label in ("原误记反向调整", "正确重记"):
        row = funds.locator("tbody tr").filter(has_text=label)
        await expect(row).to_have_count(1)
        await expect(row.locator("td").nth(0)).to_have_text(label)
        await expect(row.locator("td").nth(1)).to_have_text(SALE.displayed_money(spec["gross"]))
        await expect(row.locator("td").nth(2)).to_contain_text(SALE.displayed_money(spec["remaining"]) + " 元")
        original = row.locator(f'[data-act="open"][data-route="case/{spec["case_id"]}"]')
        await expect(original).to_have_count(1)
        await expect(original).to_be_visible()
        await expect(original).to_be_enabled()
    if spec["refunded"]:
        await expect(frozen).to_contain_text("已经真实退款 10.00 元保留原记录")
        await expect(frozen).to_contain_text("剩余业务款由 15.00 元更正为 15.00 元")
        await expect(frozen).to_contain_text(spec["original_refund"]["reference"])
    return {"gross_cash_columns": [spec["gross"], spec["gross"]], "net_allocation_columns": [spec["remaining"], spec["remaining"]],
        "original_source_buttons_visible_enabled": True, "original_date_and_both_references_visible": True,
        "retained_refund_visible": bool(spec["refunded"])}


async def finance_remaining_business(e, context, credentials):
    cp = Checkpoint(e)
    try:
        fixture, parents = dependencies(e, cp)
        specs = correction_sources(e, parents)
        cp.report["source_preconditions"] = [{k: s[k] for k in ("requirement", "domain", "case_id", "customer_id", "cash_id", "payment_id",
            "account_id", "gross", "refunded", "remaining", "declared")} for s in specs]
        cp.save()
        cp.start("HK-076")
        agency = await agency_closure(e, context, credentials, fixture, parents[FOLLOW.SCENARIO])
        await cp.passed(**agency)
        corrections = []
        for spec in specs:
            cp.start(spec["requirement"])
            finance_id, created = await correction_create(e, context, credentials, fixture, spec)
            cp.note(finance_case_id=finance_id, original_declaration=spec["declared"], actual_create=created)
            _, _, approved = await correction_action(e, context, credentials, fixture, finance_id, spec, "approve")
            cp.note(independent_approve=approved)
            f, view, executed = await correction_action(e, context, credentials, fixture, finance_id, spec, "execute")
            result = validate_correction(e, finance_id, spec, f, view, executed)
            ui = await correction_rendered(e, spec)
            before = e.business_snapshot("before_completed_correction_refresh")
            async with e.page.expect_response(lambda r: FB.get_match(r, f"{FB.FINANCE}/orders/{finance_id}")) as pending:
                e.action("refresh", "刷新已完成更正，核原回执及资金不重复")
                await e.page.reload()
            response = await pending.value
            reread = await response.json()
            require(response.status == 200 and reread == view, "完成更正刷新改变原结果")
            await expect(e.page.locator("#main h1")).to_have_text("财务业务办理")
            e.business_unchanged(before, "after_completed_correction_refresh")
            await cp.passed(**result, actual_create=created, independent_approve=approved, actual_execute=executed,
                original_ui=ui, refresh_same_result=True, no_duplicate_money=True)
            corrections.append({"requirement": spec["requirement"], "source_case_id": spec["case_id"], "finance_case_id": finance_id,
                "correction_id": result["correction"]["id"], "original_cash_id": spec["cash_id"], "original_payment_id": spec["payment_id"],
                "new_cash_ids": [r["cash"]["id"] for r in result["two_money_facts"]], "new_payment_ids": [r["payment"]["id"] for r in result["two_money_facts"]]})
        cp.start("HK-088")
        income = await other_income_closure(e, context, credentials, fixture, parents)
        await cp.passed(**income)
        cp.start("HK-092")
        cancellation = await cancellation_closure(e, context, credentials, fixture, parents[SALE.CANCELLATION_SCENARIO])
        await cp.passed(**cancellation)
        cp.finish({"store_id": 1, "corrections": corrections, "agency_case_id": agency["case_id"],
            "customer_income_case_id": income["customer_income"]["case_id"], "manufacturer_income_case_id": income["manufacturer_income"]["case_id"],
            "cancelled_order_id": cancellation["case_id"], "original_inputs_only_same_run": True})
    except BaseException as error:
        cp.failed(str(error))
        raise


FINANCE_REMAINING_SCENARIOS = ((SCENARIO, finance_remaining_business, 1500),)
