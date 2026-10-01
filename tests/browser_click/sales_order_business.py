"""Original vehicle quote, independent approval, delivery and cancellation UI.

Only this run's passed fixed checkpoints supply customer and physical vehicle
sources. Original writes use visible forms; Evidence opens SQLite read-only.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
import uuid
import zipfile
from xml.etree import ElementTree

from playwright.async_api import expect

from sales_business import employee_choice, login_as, native_submit, new_event, require
from vehicle_purchase_business import live_choice, nav, select_value


SCENARIO = "sales-order-hk008-009-011-022"
CANCELLATION_SCENARIO = "sales-cancellation-hk010"
PRESALES = "sales-presales-hk001-007"
PURCHASE = "vehicle-purchase-hk171-177-178-026-021-018-029"
CONTRACTS = {
    "HK-008": ("车辆预订单", ["从本次原意向建立同客户报价，另一主管批准", "提交新版并保留旧报价、批准和客户确认，新版须本版签回"]),
    "HK-009": ("车辆销售单", ["同本版报价及VIN签回、原实收、合格检查、出库及提车分别产生事实", "原单任务、事件、现金、占车及库存代次一致，刷新不重复办理"]),
    "HK-011": ("客户提车单", ["生成本版提车字节、上传明确对应签回", "独立客户接车事件及任务结束，出库不冒充接车"]),
    "HK-022": ("车辆销售出库", ["库管本人在签回、车款及检查齐全后确认实物出库", "唯一出库位置流水、占车及在途交接状态与尚未提车事实一致"]),
    "HK-010": ("销售订单退订单", ["另一未履约原单申请退订，由不同主管批准", "财务从原收款及同账户实退，原款不删，净额零及解占正确"]),
}


class Checkpoint:
    def __init__(self, e, scenario, ids):
        self.e, self.active = e, None
        self.path = e.directory / "business-checkpoint.json"
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.catalogue = json.loads(raw)
        self.digest = hashlib.sha256(raw).hexdigest()
        bindings = {r["id"]: r for r in self.catalogue["requirements"]}
        for key in ids:
            require(bindings[key]["source_review_status"] == "source_reviewed", key + " 未核准源合同")
            require(any(c["check_id"] == key + "-business" for c in bindings[key]["acceptance_checks"]), key + " check_id错误")
        self.report = {
            "schema": 1, "scenario": scenario, "scope": list(ids), "complete": False, "passed": False,
            "source_contract_sha256": self.digest,
            "candidate_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "execution": "native_browser_original_forms", "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "human_acceptance": "pending",
            "conditions": {"synthetic_money_and_physical_inputs": True,
                "production_bank_or_physical_handover_acceptance": False,
                "file_scan": "original_structure_only_not_clamav",
                "company_contract_template_approval_acceptance": False,
                "business_entity_policy_acceptance": False},
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "requirements": [{"id": key, "title": CONTRACTS[key][0], "status": "not_tested", "business_accepted": False,
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested",
                    "criteria": CONTRACTS[key][1], "evidence": {}}],
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"}, "conditional_checks": []} for key in ids],
        }
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active["status"] = "running"
        self.active["acceptance_checks"][0]["status"] = "running"
        self.active.setdefault("evidence_action_start", len(self.e.actions))
        self.save()

    def note(self, evidence):
        self.active["acceptance_checks"][0]["evidence"].update(evidence)
        self.save()

    async def passed(self, evidence, conditional=()):
        self.note(evidence)
        await self.e.snapshot(self.active["id"].lower() + "-business")
        self.active["status"] = "passed"
        self.active["acceptance_checks"][0]["status"] = "passed"
        self.active["evidence_action_end"] = len(self.e.actions)
        self.active["conditional_checks"] = list(conditional)
        self.save()

    def failed(self, error):
        if self.active:
            self.active["status"] = "failed"
            self.active["acceptance_checks"][0].update(status="failed", error=self.e.scrub(error))
            self.report["failed_requirement"] = self.active["id"]
        for row in self.report["requirements"]:
            if row["status"] == "running":
                row["status"] = "partial"
                row["acceptance_checks"][0].update(status="partial", incomplete_reason="后续原依赖未完成，场景失败后终止")
        self.report["error"] = self.e.scrub(error)
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "声明销售业务范围未完整执行")
        self.report.update(complete=True, passed=True, executed_requirements=len(self.report["requirements"]),
                           passed_requirements=len(self.report["requirements"]), report_sources=sources)
        self.save()
        self.e.observe("sales_original_business_checkpoint", {"path": str(self.path), "report_sources": sources,
                                                               "business_accepted": False})


def checkpoint_evidence(report, key):
    row = next((r for r in report["requirements"] if r["id"] == key), None)
    require(row is not None and row["status"] == "passed", "前场景需求未实际通过：" + key)
    check = row["acceptance_checks"][0]
    require(check["status"] == "passed" and check["evidence"], "前场景缺原事实证据：" + key)
    return check["evidence"]


def fixed_dependency(e, checkpoint, name):
    root = Path(e.manifest["evidence_root"]).resolve()
    summary = json.loads((root / "browser-click-report.json").read_text(encoding="utf-8"))
    require(name in summary["expected_scenarios"], "当前运行未注册所需前场景：" + name)
    result = [r for r in summary["scenarios"] if r["id"] == name]
    require(len(result) == 1 and result[0]["status"] == "passed", "当前运行前场景尚未通过：" + name)
    path = root / name / "business-checkpoint.json"
    raw = path.read_bytes()
    report = json.loads(raw)
    require(report["scenario"] == name and report["complete"] is True and report["passed"] is True,
            "当前前场景检查点不完整：" + name)
    require(all(r["status"] == "passed" for r in report["requirements"]), "前场景有失败或未执行项：" + name)
    if "source_contract_sha256" in report:
        require(report["source_contract_sha256"] == checkpoint.digest, "本次原业务目录指纹与前场景不一致")
    if "provenance" in report:
        require(report["provenance"] == checkpoint.report["provenance"], "前场景来自其他运行或源码目录")
    checkpoint.report.setdefault("dependencies", []).append({"scenario": name, "runner_status": "passed",
        "checkpoint_sha256": hashlib.sha256(raw).hexdigest(), "fixed_path": str(path),
        "source_contract_sha256": report.get("source_contract_sha256"), "current_run_only": True})
    checkpoint.save()
    return report


def dependencies(e, checkpoint, *, cancellation=False):
    fixture = dict(e.manifest["business_fixtures"]["sales_order"])
    for role in ("sales", "manager", "inventory", "finance", "service"):
        key = fixture[role + "_key"]
        require(key in e.manifest["users"] and e.manifest["users"][key]["role"] == role, "缺真正本店岗位：" + role)
    presales = fixed_dependency(e, checkpoint, PRESALES)
    purchase = fixed_dependency(e, checkpoint, PURCHASE)
    original = checkpoint_evidence(presales, "HK-007")["db"]
    lead_id, customer_id = original["case"]["id"], original["customer"]["id"]
    lead = e.db.rows("SELECT id,store_id,kind,state,version,customer_id,owner_id,number FROM flow_cases WHERE id=?", (lead_id,))[0]
    customer = e.db.rows("SELECT id,store_id,name,phone,contact_allowed,owner_id FROM flow_customers WHERE id=?", (customer_id,))[0]
    salesperson = e.manifest["users"][fixture["sales_key"]]
    require(lead["kind"] == "lead" and lead["store_id"] == customer["store_id"] == fixture["store_id"]
            and lead["customer_id"] == customer_id and lead["owner_id"] == customer["owner_id"] == salesperson["id"], "本次原意向/客户归属不匹配")
    if not cancellation:
        require(lead["state"] == "intent" and lead["version"] == original["case"]["version"], "本次前置原意向已变化")
    purchase_evidence = checkpoint_evidence(purchase, "HK-021")
    fixture["account_id"] = purchase_evidence["payment"]["account_id"]
    cars = purchase_evidence["vehicles"]
    require(len(cars) == 2, "本次原采购没有两辆实际验收车辆")
    models = checkpoint_evidence(purchase, "HK-018")["positive"]
    sources = []
    for supplied in cars:
        car_id = supplied["vehicle"]["id"]
        car = e.db.rows("SELECT id,vin,store_id,model,inventory_generation,purchase_cost_cents,approval_state,color,location FROM vehicles WHERE id=?", (car_id,))[0]
        receipt = e.db.rows("SELECT r.id,r.vehicle_id,r.case_id,r.shipment_id,l.model_id FROM vehicle_purchase_receipts r "
                            "JOIN vehicle_purchase_shipments s ON s.id=r.shipment_id JOIN vehicle_purchase_lines l ON l.id=s.line_id "
                            "WHERE r.case_id=? AND r.vehicle_id=?", (purchase_evidence["case_id"], car_id))
        require(len(receipt) == 1 and car["vin"] == supplied["vehicle"]["vin"] and car["store_id"] == fixture["store_id"]
                and car["inventory_generation"] == supplied["vehicle"]["inventory_generation"]
                and car["purchase_cost_cents"] == supplied["vehicle"]["purchase_cost_cents"] and car["approval_state"] == "approved", "原采购实车/收车来源或代次不匹配")
        model = next((m["model"] for m in models if m["model"]["id"] == receipt[0]["model_id"]), None)
        require(model is not None and model["name"] == car["model"], "前采购实车缺真实车型来源")
        current_model = e.db.rows("SELECT id,version,name FROM master_vehicle_models WHERE id=?", (model["id"],))[0]
        require(current_model["version"] == model["version"] and current_model["name"] == model["name"], "本次车型版本已变化")
        sources.append({"vehicle": car, "model": model, "receipt": receipt[0], "original_position": supplied["position"]})
    prior_delivery = None
    if cancellation:
        prior_delivery = fixed_dependency(e, checkpoint, SCENARIO)
        require(prior_delivery["report_sources"]["lead_id"] == lead_id
                and prior_delivery["report_sources"]["customer_id"] == customer_id and lead["state"] == "converted", "退订前同次销售/客户原来源错误")
    checkpoint.report["dependency_status"] = "passed_current_run_sources_rechecked"
    checkpoint.save()
    return fixture, lead, customer, sources, prior_delivery


def facts(e, case_id):
    rows = e.db.rows("SELECT * FROM flow_cases WHERE id=?", (case_id,))
    require(len(rows) == 1, "原销售单不存在或不唯一")
    case = rows[0]
    case["data"] = json.loads(case["data"])
    result = {"case": case}
    for key, table in (("quotes", "sales_quotes"), ("tasks", "flow_tasks"), ("events", "flow_events"), ("payments", "flow_payment_links")):
        result[key] = e.db.rows(f"SELECT * FROM {table} WHERE case_id=? ORDER BY id", (case_id,))
    for q in result["quotes"]:
        q["model_snapshot"], q["services"] = json.loads(q["model_snapshot"]), json.loads(q["services"])
    for event in result["events"]:
        event["detail"] = json.loads(event["detail"])
    for key, table in (("reviews", "sales_quote_reviews"), ("resolutions", "sales_quote_resolutions"), ("consents", "sales_quote_consents")):
        result[key] = e.db.rows(f"SELECT t.* FROM {table} t JOIN sales_quotes q ON q.id=t.quote_id WHERE q.case_id=? ORDER BY t.id", (case_id,))
    result["holds"] = e.db.rows("SELECT * FROM flow_vehicle_holds WHERE case_id=?", (case_id,))
    result["cash"] = [e.db.rows("SELECT id,store_id,direction,category,amount_cents,account,payment_method,voucher_no,created_by,approval_state "
                                "FROM cash_entries WHERE id=?", (p["cash_id"],))[0] for p in result["payments"]]
    return result


def task(f, key):
    rows = [t for t in f["tasks"] if t["key"] == key and t["status"] == "open"]
    require(len(rows) == 1, "当前原销售待办不唯一：" + key)
    return rows[0]


def appended(before, after):
    for field in ("id", "number", "store_id", "kind", "flow_version", "created_by", "owner_id", "customer_id", "parent_id"):
        require(before["case"][field] == after["case"][field], "原销售身份事实被替换：" + field)
    require(after["case"]["version"] > before["case"]["version"], "原单版本未前进")
    for key in ("quotes", "reviews", "resolutions", "consents", "payments", "cash"):
        require(after[key][:len(before[key])] == before[key], "原不可覆盖事实被改写：" + key)


async def original_write(e, path, expected, *, case_id=None, click='#modal form button[type="submit"]', multipart=False):
    def rendered(r):
        p = urlsplit(r.url).path
        return r.request.method == "GET" and (p == f"/api/sales-quotes/orders/{case_id}" if case_id is not None else
            p.startswith("/api/sales-quotes/orders/") and p.rsplit("/", 1)[-1].isdigit())
    async with e.page.expect_response(rendered) as ready:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == path) as pending:
            await e.click(click, "员工提交原销售表单" if click.startswith("#modal") else "员工生成原本版文档")
        response = await pending.value
        body = await response.json()
        require(response.status == expected, f"原销售提交 HTTP {response.status}：{e.scrub(body.get('detail', ''))}")
    read = await ready.value
    view = await read.json()
    require(read.status == 200 and view["id"] == (case_id if case_id is not None else body["id"]), "提交后未真实读取同销售原单")
    headers = await response.request.all_headers()
    require(bool(headers.get("cookie")) and bool(headers.get("x-csrf-token"))
            and headers.get("x-store-id") == str(e.manifest["business_fixtures"]["sales_order"]["store_id"]), "原销售写缺本店Cookie/CSRF")
    request = None if multipart else response.request.post_data_json
    metadata = {"path": path, "method": "POST", "status": response.status, "native_ui": True,
                "cookie_present": True, "csrf_present": True, "submitted_version": request.get("version") if request else None,
                "request_id_sha256": hashlib.sha256(request["request_id"].encode()).hexdigest() if request and request.get("request_id") else None,
                "render_get_path": urlsplit(read.url).path, "render_get_status": 200}
    e.observe("original_sales_response", metadata)
    await expect(e.page.locator("#modal")).not_to_be_visible()
    await expect(e.page.locator("#main h1")).to_have_text("预订合同 · " + view["number"])
    await expect(e.page.locator("#main .notice.error")).to_have_count(0)
    return body, view, metadata, request


async def detail_as(e, context, credentials, key, case_id, store_id):
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/sales-quotes/orders/{case_id}") as pending:
        user = await login_as(e, context, credentials, key, f"sales-quotes/{case_id}", store_id)
    response = await pending.value
    view = await response.json()
    require(response.status == 200 and view["id"] == case_id, "原岗位未读取本销售单")
    await expect(e.page.locator("#main h1")).to_have_text("预订合同 · " + view["number"])
    if user["role"] == "inventory":
        require("amount_cents" not in view and "paid_cents" not in view, "库管读取了不应显示的原销售款项")
        await expect(e.page.locator('#main [data-key="receive"]')).to_have_count(0)
    return user, view


async def responsible(e, context, credentials, fixture, case_id, key, role):
    before = task(facts(e, case_id), key)
    target = e.manifest["users"][fixture[role + "_key"]]
    evidence = {"task_id": before["id"], "key": key, "original_assignee_id": before["assignee_id"], "actual_employee_id": target["id"]}
    if before["assignee_id"] != target["id"]:
        await login_as(e, context, credentials, fixture["manager_key"], f"case/{case_id}", fixture["store_id"])
        await expect(e.page.locator("#main h1")).to_have_text(facts(e, case_id)["case"]["title"])
        await e.click(f'#main [data-act="assign"][data-id="{before["id"]}"]', "主管在原任务表转交真实员工")
        await expect(e.page.locator("#modal-title")).to_have_text("转交任务")
        await employee_choice(e, target)
        await e.fill('#modal [name="reason"]', "本次合成销售由明确选择的本店岗位员工本人办理", "填写真实任务转交原因")
        _, metadata, _ = await native_submit(e, f'/api/flow/tasks/{before["id"]}/assign', 200, case_id=case_id)
        after = task(facts(e, case_id), key)
        require(after["id"] == before["id"] and after["assignee_id"] == target["id"] and after["version"] > before["version"], "原销售任务转交失败")
        evidence["native_handoff"] = metadata
    user, view = await detail_as(e, context, credentials, fixture[role + "_key"], case_id, fixture["store_id"])
    require(task(facts(e, case_id), key)["assignee_id"] == user["id"], "原销售员工不是当前待办负责人")
    return user, view, evidence


async def action_form(e, key):
    selector = f'#main [data-act="sales-quote-action"][data-key="{key}"]'
    button = e.page.locator(selector)
    await expect(button).to_have_count(1)
    if not await button.is_visible():
        details = button.locator("xpath=ancestor::details[1]")
        await expect(details).to_have_count(1)
        e.action("click", "展开原更正、退回或撤销操作", action=key)
        await details.locator(":scope > summary").click()
    await expect(button).to_be_visible()
    await expect(button).to_be_enabled()
    await e.click(selector, "办理原销售步骤 " + key)
    await expect(e.page.locator("#modal form")).to_be_visible()


async def command(e, case_id, key, actor, fills=None, selects=(), lookups=()):
    before = facts(e, case_id)
    await action_form(e, key)
    for field, value in (fills or {}).items():
        await e.fill(f'#modal [name="{field}"]', str(value), "填写明确的原销售事实 " + field)
    for field, value in selects:
        await select_value(e, f'#modal [name="{field}"]', value, "明确选择本单原来源 " + field)
    for field, label, value in lookups:
        await live_choice(e, field, label, label, expected_value=value)
    _, view, metadata, request = await original_write(e, f"/api/flow/cases/{case_id}/actions/{key}", 200, case_id=case_id)
    after = facts(e, case_id)
    appended(before, after)
    event = new_event(before, after, key, actor["id"])
    require(request["version"] == before["case"]["version"] and request["request_id"], "销售动作未携带真实原单版本和请求号")
    metadata.update(event_id=event["id"], actor_id=actor["id"])
    return after, view, metadata


async def upload(e, case_id, actor, category, name, text, *, source_file=None):
    directory = e.directory / "synthetic-inputs"
    directory.mkdir(exist_ok=True)
    content = ("合成浏览器验收资料，不表示真实公司签约、银行或现场交接。\n" + text + "\n").encode()
    path = directory / name
    path.write_bytes(content)
    await e.click('#main [data-panel-role="files"] [data-act="upload"]' if await e.page.locator('#main [data-panel-role="files"] [data-act="upload"]').count()
                  else '#main .panel:has(h2:text-is("本版文档与实际凭据")) [data-act="upload"]', "原文件选择并上传合成实际凭据")
    await expect(e.page.locator("#modal-title")).to_have_text("上传业务文件")
    await select_value(e, '#modal [name="category"]', category, "明确原签回或业务附件类别")
    if source_file is not None:
        await select_value(e, '#modal [name="source_file_id"]', source_file["id"], "明确选择本版原生成文档")
    e.action("select_file", "员工从外部目录选择合成凭据", filename=name, sha256=hashlib.sha256(content).hexdigest())
    await e.page.locator('#modal input[name="file"]').set_input_files(str(path))
    body, view, metadata, _ = await original_write(e, f"/api/flow/cases/{case_id}/files", 200, case_id=case_id, multipart=True)
    row = e.db.rows("SELECT id,case_id,store_id,category,name,sha256,size,created_by,generated,source_file_id FROM flow_files WHERE id=?", (body["id"],))[0]
    require(row["case_id"] == case_id and row["created_by"] == actor["id"] and row["category"] == category and row["name"] == name
            and row["sha256"] == hashlib.sha256(content).hexdigest() and row["size"] == len(content) and not row["generated"]
            and row["source_file_id"] == (source_file["id"] if source_file else None), "原上传字节、身份或签回来源错误")
    scan = e.db.rows("SELECT file_id,actor_id,action,state,sha256,size FROM file_scan_events WHERE file_id=? ORDER BY id", (row["id"],))
    require(len(scan) == 1 and scan[0]["actor_id"] == actor["id"] and scan[0]["action"] == "initial" and scan[0]["state"] == "structure_only"
            and scan[0]["sha256"] == row["sha256"] and scan[0]["size"] == row["size"], "原结构扫描来源不匹配")
    visible = next((f for f in view["files"] if f["id"] == row["id"]), None)
    require(visible is not None and visible["security"]["can_use"] is True, "原合成附件未达到当前隔离可用状态")
    await expect(e.page.locator("#main .filerecord").filter(has_text=name)).to_contain_text(visible["security"]["label"])
    return row, {"native": metadata, "file": row, "scan": scan[0], "clamav_acceptance": False}


async def generate(e, case_id, actor, kind):
    body, view, metadata, _ = await original_write(e, f"/api/flow/cases/{case_id}/documents", 200, case_id=case_id,
        click=f'#main [data-act="generatedoc"][data-kind="{kind}"]')
    row = e.db.rows("SELECT id,case_id,store_id,category,name,sha256,size,created_by,generated,template_version,template_approved,"
                    "source_fingerprint,snapshot FROM flow_files WHERE id=?", (body["id"],))[0]
    row["snapshot"] = json.loads(row["snapshot"])
    require(row["case_id"] == case_id and row["created_by"] == actor["id"] and row["category"] == kind and row["generated"] and row["template_approved"], "生成文档没有可用的原模板/本人及本单来源")
    require(row["source_fingerprint"] == hashlib.sha256(json.dumps(row["snapshot"], ensure_ascii=False, sort_keys=True).encode()).hexdigest(), "原文档快照指纹错误")
    current = facts(e, case_id)
    quote_id = current["case"]["data"].get("active_quote_id") if kind == "handover" else current["case"]["data"].get("pending_quote_id") or current["case"]["data"].get("active_quote_id")
    quote = next(q for q in current["quotes"] if q["id"] == quote_id)
    car = e.db.rows("SELECT vin FROM vehicles WHERE id=?", (current["case"]["vehicle_id"],))[0]
    require(row["snapshot"]["报价版本"] == quote["revision"] and row["snapshot"]["报价校验摘要"] == quote["digest"]
            and row["snapshot"]["车架号"] == car["vin"] and row["snapshot"]["车辆约定金额（元）"] == fen_text(quote["amount_cents"]), "生成合同/提车快照非当前报价及VIN")
    before = e.business_snapshot("original_before_generated_document_download")
    old_audit = {r["id"]: r for r in e.db.rows("SELECT * FROM audit_logs ORDER BY id")}
    async with e.page.expect_download() as pending:
        await e.click(f'#main .filerecord [data-act="downloadfile"][data-id="{row["id"]}"]', "下载原生成字节核对本版报价与VIN")
    directory = e.directory / "generated-documents"
    directory.mkdir(exist_ok=True)
    path = directory / (str(row["id"]) + ".docx")
    await (await pending.value).save_as(str(path))
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == row["sha256"] and len(data) == row["size"], "真实下载字节与FileAsset不一致")
    with zipfile.ZipFile(path) as doc:
        text = "".join(ElementTree.fromstring(doc.read("word/document.xml")).itertext())
    require(car["vin"] in text and row["snapshot"]["单据编号"] in text and row["snapshot"]["车辆约定金额（元）"] in text, "真实生成字节缺本原单/车型金额")
    after = e.business_snapshot("original_after_generated_document_download")
    require({k: v for k, v in before["tables"].items() if k != "audit_logs"}
            == {k: v for k, v in after["tables"].items() if k != "audit_logs"}, "原文档下载改动了业务行")
    current_audit = e.db.rows("SELECT * FROM audit_logs ORDER BY id")
    require({r["id"]: r for r in current_audit if r["id"] in old_audit} == old_audit,
            "原文档下载覆盖或删除了旧审计")
    added = [r for r in current_audit if r["id"] not in old_audit]
    require(len(added) == 1, "一次文档下载没有唯一原审计")
    audit = added[0]
    require(audit["actor_id"] == actor["id"] and audit["store_id"] == row["store_id"]
            and audit["action"] == "download" and audit["entity_type"] == "flow" and audit["entity_id"] == case_id
            and audit["reason"] == "下载文件 " + str(row["id"])
            and json.loads(audit["before_data"]) is None and json.loads(audit["after_data"]) is None,
            "下载审计没有对应当前本人、本店、原单及原文档")
    return row, {"native": metadata, "generated": row, "download_sha256": hashlib.sha256(data).hexdigest(), "download_business_unchanged": True,
                 "exact_download_audit": audit, "old_audit_rows_unchanged": True,
                 "demo_template_only": True, "company_template_approval_acceptance": False}


async def sign_current(e, context, credentials, fixture, case_id, revision):
    sales, _, owner = await responsible(e, context, credentials, fixture, case_id, "sign", "sales")
    document, doc_evidence = await generate(e, case_id, sales, "contract")
    file, file_evidence = await upload(e, case_id, sales, "signed_contract", f"signed-contract-{case_id}-{revision}.txt",
        f"本合成客户核对并签回报价第{revision}版、VIN {document['snapshot']['车架号']}、金额{document['snapshot']['车辆约定金额（元）']}元。", source_file=document)
    f, view, action = await command(e, case_id, "sign", sales, lookups=[("evidence_id", file["name"] + " · 合同签回件", file["id"])])
    consent = f["consents"][-1]
    quote = next(q for q in f["quotes"] if q["revision"] == revision)
    require(f["case"]["data"].get("active_quote_id") == consent["quote_id"] == quote["id"] and f["case"]["data"].get("pending_quote_id") is None
            and consent["vehicle_id"] == f["case"]["vehicle_id"] and consent["source_file_id"] == document["id"]
            and consent["evidence_id"] == file["id"] and consent["fingerprint"] == document["source_fingerprint"] and consent["actor_id"] == sales["id"], "客户原确认非本Quote/VIN/源字节")
    require(view["business_facts"]["facts"]["sales.active_quote_approved"] is True
            and view["business_facts"]["facts"]["sales.active_quote_consented"] is True, "原事实GET不认可当前批准及签回")
    return f, {"task_owner": owner, "document": doc_evidence, "signature": file_evidence, "native_sign": action, "consent": consent}


async def stock_ui(e, source, state, label):
    before = e.business_snapshot("original_before_sales_stock_query")
    await nav(e, "legacy/vehicles", "整车库存", "/api/records/vehicles")
    vin = source["vehicle"]["vin"]
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/records/vehicles"
        and parse_qs(urlsplit(r.url).query).get("q") == [vin]) as pending:
        await e.fill('#filters [name="q"]', vin, "查实际本次VIN的占用与库龄")
    response = await pending.value
    body = await response.json()
    require(response.status == 200 and body["total"] == len(body["items"]) == 1, "原占车库存查询未返回同VIN")
    row = body["items"][0]
    require(row["id"] == source["vehicle"]["id"] and row["stock_state"] == state and row["stock_age_days"] == 0, "真实占用或零库龄API错误")
    ui = e.page.locator("#main tbody tr")
    await expect(ui).to_have_count(1)
    headings = await e.page.locator("#main thead th").all_text_contents()
    for heading, expected in (("库龄（天）", "0"), ("审核状态", "已审核"), ("库存状态", label)):
        indices = [i for i, text in enumerate(headings) if text.strip() == heading]
        require(len(indices) == 1, "原库存缺精确列：" + heading)
        await expect(ui.locator("td").nth(indices[0])).to_have_text(expected)
    await expect(ui).to_contain_text(label)
    await expect(ui).to_contain_text(vin)
    e.business_unchanged(before, "original_after_sales_stock_query")
    return {"native_get": {"path": "/api/records/vehicles", "status": 200, "vin": vin}, "stock_state": state,
            "stock_age_days": 0, "stock_age_exact_column": "0", "business_unchanged": True}


def fen_text(cents):
    return str(cents // 100) + "." + str(cents % 100).zfill(2)


def displayed_money(cents):
    return format(cents // 100, ",") + "." + str(cents % 100).zfill(2)


def selected_source(sources, fuel):
    matched = [s for s in sources if s["model"]["fuel_type"] == fuel]
    require(len(matched) == 1, "本次采购不存在唯一明确车型：" + fuel)
    return matched[0]


def physical(e, source, *, state, case_id=None, delivered=False):
    car = source["vehicle"]
    actual = e.db.rows("SELECT id,store_id,vin,model,inventory_generation,purchase_cost_cents,approval_state FROM vehicles WHERE id=?", (car["id"],))[0]
    for field in actual:
        require(actual[field] == car[field], "销售原实车身份或代次被改变：" + field)
    positions = e.db.rows("SELECT * FROM vehicle_positions WHERE vehicle_id=?", (car["id"],))
    require(len(positions) == 1 and positions[0]["status"] == state, "销售原位置状态不匹配")
    if state == "stored":
        require(positions[0]["location_id"] == source["original_position"]["location_id"], "原实车库位被替换")
    else:
        require(positions[0]["location_id"] is None, "出库实车仍保留在库位置")
    custody = e.db.rows("SELECT * FROM vehicle_custodies WHERE current_vehicle_id=?", (car["id"],))
    require(len(custody) == 1 and custody[0]["current_store_id"] == car["store_id"] and custody[0]["generation"] == car["inventory_generation"]
            and custody[0]["pending_transfer_id"] is None, "原库存权属或代次不匹配")
    holds = e.db.rows("SELECT * FROM flow_vehicle_holds WHERE vehicle_id=?", (car["id"],))
    if case_id is None:
        require(not holds, "本次待选实车已有非本次原销售占用")
    else:
        require(len(holds) == 1 and holds[0]["case_id"] == case_id and bool(holds[0]["delivered"]) is delivered, "原配车占用/提车事实错误")
    return {"vehicle": actual, "position": positions[0], "custody": custody[0], "holds": holds}


async def fill_quote(e, model, cents, terms, *, reason=None):
    await expect(e.page.locator("#sales-quote-form")).to_be_visible()
    label = model["brand_name"] + " · " + model["series_name"] + " · " + model["name"] + " · " + str(model["model_year"]) + "款"
    await live_choice(e, "model", model["name"], label, expected_value=model["id"])
    await e.fill('#modal [name="amount"]', fen_text(cents), "明确本次合成车辆约定金额（元）")
    await e.fill('#modal [name="terms"]', terms, "明确本版客户合成约定")
    for name in ("due", "expires"):
        target = e.page.locator(f'#modal [name="{name}"]')
        value, minimum = await target.input_value(), await target.get_attribute("min")
        require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", minimum or ""))
                and date.fromisoformat(value) >= date.fromisoformat(minimum), "原报价默认日期不符合页面实际业务日限制")
    for name in ("addon", "insurance", "agency"):
        await expect(e.page.locator(f'#modal [name="{name}"]')).not_to_be_checked()
    if reason is not None:
        await e.fill('#modal [name="reason"]', reason, "明确本次新版报价的实际合成原因")


async def create_quote(e, context, credentials, fixture, lead, customer, source, *, from_lead):
    physical(e, source, state="stored")
    customer_count = e.db.rows("SELECT COUNT(*) AS n FROM flow_customers")[0]["n"]
    if from_lead:
        sales = await login_as(e, context, credentials, fixture["sales_key"], f'case/{lead["id"]}', fixture["store_id"])
        await expect(e.page.locator("#main h1")).to_contain_text(customer["name"])
        await expect(e.page.locator('#main [data-act="caseaction"][data-key="reserve"]')).to_be_enabled()
        await e.click('#main [data-act="caseaction"][data-key="reserve"]', "本人从当次真实意向转原预订")
        await expect(e.page.locator('#modal [name="customer_name"]')).to_have_value(customer["name"])
        await expect(e.page.locator('#modal [name="customer_name"]')).to_have_attribute("readonly", "")
        await expect(e.page.locator('#modal [name="customer_phone"]')).to_have_value(customer["phone"])
    else:
        sales = await login_as(e, context, credentials, fixture["sales_key"], "sales-quotes", fixture["store_id"])
        await expect(e.page.locator("#main h1")).to_have_text("车辆报价与预订")
        await e.click('#main [data-act="sales-quote-new"]', "为同次现有本人客户建立第二原预订")
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/customer-choice/matches"
            and parse_qs(urlsplit(r.url).query).get("q") == [customer["name"]]) as pending:
            await e.fill('#modal [name="customer_name"]', customer["name"], "从原客户候选查找同次已有客户")
        response = await pending.value
        body = await response.json()
        require(response.status == 200 and any(c["id"] == customer["id"] for c in body["items"]), "原本人客户不在真实候选中")
        await e.click(f'#modal [data-quote-customers] [data-customer-id="{customer["id"]}"]', "明确选择当次已有客户，不另建档案")
        await expect(e.page.locator('#modal [name="customer_phone"]')).to_have_attribute("readonly", "")
    amount = 12000000 if from_lead else 13000000
    await fill_quote(e, source["model"], amount, "本次合成整车预订；仅车辆价款，未约定另单加装、保险或代办。")
    body, view, metadata, request = await original_write(e, "/api/sales-quotes/orders", 201)
    f = facts(e, body["id"])
    require(f["case"]["kind"] == "order" and f["case"]["flow_version"] == 4 and f["case"]["state"] == "reserved"
            and f["case"]["customer_id"] == customer["id"] and f["case"]["created_by"] == f["case"]["owner_id"] == sales["id"]
            and f["case"]["store_id"] == fixture["store_id"] and len(f["quotes"]) == 1 and not f["reviews"] and not f["consents"]
            and not f["payments"] and not f["holds"], "原预订头、客户、报价或初始实际事实错误")
    quote = f["quotes"][0]
    require(quote["amount_cents"] == amount and quote["revision"] == 1 and quote["actor_id"] == sales["id"]
            and quote["model_id"] == source["model"]["id"] and quote["model_snapshot"]["version"] == request["quote"]["model_version"] == source["model"]["version"]
            and all(v is False for v in quote["services"].values()), "原报价当前车型版本、金额或另服务不匹配")
    require(e.db.rows("SELECT COUNT(*) AS n FROM flow_customers")[0]["n"] == customer_count, "原现有客户预订另造了客户")
    if from_lead:
        require(f["case"]["parent_id"] == lead["id"] and request["lead_id"] == lead["id"] and request["lead_version"] == lead["version"], "预订未携真实前意向ID/版本")
        converted = e.db.rows("SELECT state,customer_id,version FROM flow_cases WHERE id=?", (lead["id"],))[0]
        events = e.db.rows("SELECT id,actor_id,action,detail FROM flow_events WHERE case_id=? AND action='sales_quote_convert'", (lead["id"],))
        require(converted["state"] == "converted" and converted["customer_id"] == customer["id"] and converted["version"] > lead["version"]
                and len(events) == 1 and events[0]["actor_id"] == sales["id"] and json.loads(events[0]["detail"])["order_id"] == f["case"]["id"], "意向转预订缺真实原事件或同客户")
        require(not e.db.rows("SELECT id FROM flow_tasks WHERE case_id=? AND status='open'", (lead["id"],)), "原意向任务未结束")
        metadata["lead_conversion"] = {"case": converted, "event": events[0]}
    else:
        require(f["case"]["parent_id"] is None and request["customer_id"] == customer["id"], "第二预订没有明确复用原客户")
    return f, {"native_create": metadata, "initial_quote": quote, "customer_id": customer["id"]}


async def approve(e, context, credentials, fixture, case_id):
    manager, _, owner = await responsible(e, context, credentials, fixture, case_id, "quote_approve", "manager")
    before = facts(e, case_id)
    quote = next(q for q in before["quotes"] if q["id"] == before["case"]["data"]["pending_quote_id"])
    require(quote["actor_id"] != manager["id"], "批准人不得是本版报价提交人")
    f, view, metadata = await command(e, case_id, "quote_approve", manager, {"reason": "独立核对本次合成客户、车型、价格、期限及无另单服务约定"})
    review = next(r for r in f["reviews"] if r["quote_id"] == quote["id"])
    require(review["actor_id"] == manager["id"] and review["decision"] == "approved" and f["case"]["state"] == "executing"
            and f["case"]["data"]["pending_quote_id"] == quote["id"] and len(f["payments"]) == len(before["payments"]), "独立报价批准冒充客户签回或实收")
    return f, {"task_owner": owner, "native_approval": metadata, "review": review}


async def allocate(e, context, credentials, fixture, case_id, source):
    inventory, _, owner = await responsible(e, context, credentials, fixture, case_id, "allocate", "inventory")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/sales-quotes/orders/{case_id}/vehicles") as pending:
        await action_form(e, "allocate")
    response = await pending.value
    body = await response.json()
    rows = [r for r in body["items"] if r["id"] == source["vehicle"]["id"]]
    require(response.status == 200 and len(rows) == 1 and source["vehicle"]["vin"] in rows[0]["label"], "当前本版可用车候选没有原采购VIN")
    before = facts(e, case_id)
    await select_value(e, '#modal [name="vehicle"]', rows[0]["label"], "明确选择真实采购VIN，不按同名车型猜车")
    _, _, metadata, request = await original_write(e, f"/api/flow/cases/{case_id}/actions/allocate", 200, case_id=case_id)
    f = facts(e, case_id)
    appended(before, f)
    event = new_event(before, f, "allocate", inventory["id"])
    require(request["values"]["vehicle_id"] == f["case"]["vehicle_id"] == source["vehicle"]["id"]
            and request["version"] == before["case"]["version"] and f["case"]["cost_cents"] == source["vehicle"]["purchase_cost_cents"], "原配车VIN、成本或版本不匹配")
    physical_facts = physical(e, source, state="stored", case_id=case_id)
    stock = await stock_ui(e, source, "reserved", "已预订")
    return f, {"task_owner": owner, "native_allocate": metadata, "event": event, "physical": physical_facts,
               "supplemental_HK029_occupied_source": stock}


async def payment(e, context, credentials, fixture, case_id, cents, suffix, *, original=None):
    key = "refund" if original else "receive"
    finance, _, owner = await responsible(e, context, credentials, fixture, case_id, key, "finance")
    file, file_evidence = await upload(e, case_id, finance, "receipt", f"{key}-{case_id}-{suffix}.txt",
        f"本次合成{key}实际金额{fen_text(cents)}元；独立凭证{suffix}，不代表真实银行到账。")
    account_id = original["account_id"] if original else fixture["account_id"]
    account = e.db.rows("SELECT id,store_id,name,active,account_type FROM flow_accounts WHERE id=?", (account_id,))[0]
    require(account["active"] and account["store_id"] == fixture["store_id"], "原付款来源账户已停用或非本店")
    choices = [("account_id", account["name"], account["id"]), ("evidence_id", file["name"] + " · 收退款凭据", file["id"])]
    if original:
        choices.append(("original_id", original["reference"] + " · 可退 " + fen_text(original["amount_cents"]) + " 元", original["id"]))
    before = facts(e, case_id)
    reference = "BCS-" + uuid.uuid4().hex[:18].upper()
    f, view, metadata = await command(e, case_id, key, finance, {"amount": fen_text(cents), "reference": reference}, lookups=choices)
    require(len(f["payments"]) == len(before["payments"]) + 1 and len(f["cash"]) == len(before["cash"]) + 1, "原收退款没有恰好追加独立一笔")
    link, cash = f["payments"][-1], f["cash"][-1]
    direction = "out" if original else "in"
    require(link["direction"] == cash["direction"] == direction and link["amount_cents"] == cash["amount_cents"] == cents
            and link["account_id"] == account_id and cash["account"] == account["name"] and cash["created_by"] == finance["id"]
            and link["reference"] == cash["voucher_no"] == reference and link["cash_id"] == cash["id"]
            and link["original_id"] == (original["id"] if original else None) and cash["category"] == ("workflow_refund" if original else "workflow_order"), "原实际资金方向/金额/账户/原款不一致")
    total_ui = e.page.locator("#main .card").filter(has_text="已收及已抵用")
    await expect(total_ui).to_have_count(1)
    await expect(total_ui.locator("strong")).to_have_text(displayed_money(view["paid_cents"]))
    return f, view, {"task_owner": owner, "native_payment": metadata, "evidence": file_evidence, "payment": link, "cash": cash}


async def refresh(e, case_id):
    before = e.business_snapshot("original_before_sales_final_refresh")
    current = facts(e, case_id)
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == f"/api/sales-quotes/orders/{case_id}") as pending:
        e.action("refresh", "刷新原单核对款、出库及提车不重复")
        await e.page.reload(wait_until="domcontentloaded")
    response = await pending.value
    view = await response.json()
    require(response.status == 200 and view["id"] == case_id, "原销售刷新未读取同原单")
    await expect(e.page.locator("#main h1")).to_have_text("预订合同 · " + current["case"]["number"])
    e.business_unchanged(before, "original_after_sales_final_refresh")
    require(facts(e, case_id) == current, "刷新重复追加或改变原资金/业务事实")
    return view


async def sales_order(e, context, credentials):
    checkpoint = Checkpoint(e, SCENARIO, ("HK-008", "HK-009", "HK-011", "HK-022"))
    checkpoint.start("HK-008")
    try:
        fixture, lead, customer, sources, _ = dependencies(e, checkpoint)
        source = selected_source(sources, "petrol")
        f, created = await create_quote(e, context, credentials, fixture, lead, customer, source, from_lead=True)
        case_id = f["case"]["id"]
        checkpoint.note({"case_id": case_id, "customer_id": customer["id"], "lead_id": lead["id"], "create": created})
        _, approval1 = await approve(e, context, credentials, fixture, case_id)
        _, allocated = await allocate(e, context, credentials, fixture, case_id, source)
        first, signature1 = await sign_current(e, context, credentials, fixture, case_id, 1)
        await e.click('#main [data-act="sales-quote-revise"]', "本人在同原单提交新报价版本")
        await expect(e.page.locator("#modal-title")).to_have_text("修改报价")
        await fill_quote(e, source["model"], 12100000, "本次合成客户明确改价121000元，仍为原VIN且无另单服务。", reason="客户重新核对本次车辆价款，旧已签报价保留")
        _, view, revised_api, request = await original_write(e, f"/api/sales-quotes/orders/{case_id}/quotes", 201, case_id=case_id)
        changed = facts(e, case_id)
        appended(first, changed)
        require(request["version"] == first["case"]["version"] and len(changed["quotes"]) == 2
                and changed["quotes"][1]["prior_id"] == first["quotes"][0]["id"] and changed["quotes"][1]["amount_cents"] == 12100000
                and changed["case"]["data"]["active_quote_id"] == first["quotes"][0]["id"] and changed["case"]["data"]["pending_quote_id"] == changed["quotes"][1]["id"]
                and changed["case"]["amount_cents"] == 12000000 and changed["consents"] == first["consents"], "新版未确认前覆盖旧有效报价或确认")
        require(view["business_facts"]["facts"]["sales.active_quote_consented"] is None, "原事实错误用旧签回满足新版")
        await expect(e.page.locator("#main")).to_contain_text("当前待确认报价")
        await expect(e.page.locator("#main")).to_contain_text("此版本尚未生效")
        finance, pending_view = await detail_as(e, context, credentials, fixture["finance_key"], case_id, fixture["store_id"])
        receive = next(a for a in pending_view["actions"] if a["key"] == "receive")
        require(receive["enabled"] is False and "报价" in receive["reason"], "新版待确认没有暂停原收款")
        await expect(e.page.locator('#main [data-key="receive"]')).to_be_disabled()
        _, approval2 = await approve(e, context, credentials, fixture, case_id)
        confirmed, signature2 = await sign_current(e, context, credentials, fixture, case_id, 2)
        require(confirmed["quotes"][:1] == first["quotes"] and confirmed["consents"][:1] == first["consents"]
                and len(confirmed["consents"]) == 2 and confirmed["case"]["amount_cents"] == 12100000, "新版生效改写旧报价或签回")
        active_ui = e.page.locator("#main .panel").filter(has=e.page.get_by_role("heading", name="当前有效报价", exact=True))
        await expect(active_ui).to_contain_text("第 2 版")
        await expect(active_ui).to_contain_text("121,000.00")
        before_history = e.business_snapshot("original_before_quote_history_clicks")
        wrapper = e.page.locator("#main details.ux-history")
        if await wrapper.count() and await wrapper.get_attribute("open") is None:
            await e.click('#main details.ux-history > summary', "展开原报价历史核对两个原版本")
        for revision, amount in ((1, "120,000.00"), (2, "121,000.00")):
            title = f'第 {revision} 版 · {source["model"]["name"]}'
            summary = e.page.locator('#main [data-panel-role="history"] details > summary').filter(has_text=re.compile("^" + re.escape(title) + "$"))
            await expect(summary).to_have_count(1)
            e.action("click", "实际展开原报价第" + str(revision) + "版")
            await summary.click()
            await expect(summary.locator("..")).to_contain_text(amount)
            await expect(summary.locator("..")).to_contain_text("客户已确认并生效")
        e.business_unchanged(before_history, "original_after_quote_history_clicks")
        await checkpoint.passed({"case_id": case_id, "create": created, "approval1": approval1, "allocated": allocated,
            "signature1": signature1, "native_revise": revised_api, "old_active_preserved_while_pending": True,
            "pending_cash_disabled": True, "old_and_new_history_visible": True, "approval2": approval2, "signature2": signature2, "db": confirmed}, conditional=[
            {"check_id": "HK-008-business-edge-1", "status": "partial", "tested": ["原本人客户和同意向选择", "待确认新报价不替代旧确认并暂停收款"],
             "not_tested": ["申请人自批拒绝", "过期或车型版本冲突"]}])

        checkpoint.start("HK-009")
        funded, funded_view, cash_evidence = await payment(e, context, credentials, fixture, case_id, 12100000, "full")
        require(funded_view["paid_cents"] == funded_view["amount_cents"] == 12100000, "原车款未收足或金额不匹配")
        checkpoint.note({"case_id": case_id, "payment": cash_evidence, "db": funded})
        service, _, inspection_owner = await responsible(e, context, credentials, fixture, case_id, "inspect", "service")
        file, inspection_file = await upload(e, case_id, service, "inspection", f"inspection-{case_id}.txt", "本次合成原VIN交车检查合格，未检出须整改项。")
        inspected, _, inspection_api = await command(e, case_id, "inspect", service, {"result": "合成现场已核对原VIN及交车条件，结果合格"},
            selects=[("outcome", "合格")], lookups=[("evidence_id", file["name"] + " · 检测记录", file["id"])])
        require(inspected["case"]["data"]["inspection_status"] == "passed" and inspected["case"]["data"]["inspection"]["outcome"] == "合格"
                and inspected["case"]["data"]["inspection"]["vehicle_id"] == source["vehicle"]["id"]
                and inspected["case"]["data"]["inspection"]["round"] == 1, "原检查不属于本VIN或未合格")
        inventory, _, dispatch_owner = await responsible(e, context, credentials, fixture, case_id, "dispatch", "inventory")
        file, dispatch_file = await upload(e, case_id, inventory, "evidence", f"dispatch-{case_id}.txt", "本次合成库管核对原VIN实际出库进入客户接车交接，尚未记录客户提车。")
        dispatched, _, dispatch_api = await command(e, case_id, "dispatch", inventory,
            lookups=[("evidence_id", file["name"] + " · 业务凭据", file["id"])])
        checkpoint.note({"inspection": {"task_owner": inspection_owner, "file": inspection_file, "native": inspection_api},
                         "dispatch": {"task_owner": dispatch_owner, "file": dispatch_file, "native": dispatch_api}, "db": dispatched})
        checkpoint.start("HK-022")
        dispatched_physical = physical(e, source, state="handover", case_id=case_id)
        entries = e.db.rows("SELECT * FROM vehicle_position_entries WHERE case_id=? AND vehicle_id=? ORDER BY id", (case_id, source["vehicle"]["id"]))
        require(len(entries) == 1 and entries[0]["kind"] == "sale_dispatch" and entries[0]["quantity"] == -1
                and entries[0]["inventory_delta"] == 0 and entries[0]["value_cents"] == -source["vehicle"]["purchase_cost_cents"]
                and entries[0]["evidence_id"] == file["id"] and entries[0]["actor_id"] == inventory["id"]
                and dispatched["case"]["state"] == "executing" and dispatched["case"]["completed_date"] is None
                and not [ev for ev in dispatched["events"] if ev["action"] == "deliver"], "原出库缺独立位置事实或冒充客户接车")
        await checkpoint.passed({"case_id": case_id, "dispatch": dispatch_api, "dispatch_file": dispatch_file,
            "physical": dispatched_physical, "position_entries": entries, "not_yet_delivered": True, "db": dispatched})

        checkpoint.start("HK-011")
        sales, _, deliver_owner = await responsible(e, context, credentials, fixture, case_id, "deliver", "sales")
        handover, handover_evidence = await generate(e, case_id, sales, "handover")
        signed, signed_evidence = await upload(e, case_id, sales, "signed_handover", f"signed-handover-{case_id}.txt",
            "本次合成客户已核对本VIN及当前报价原提车单并实际接车签回。", source_file=handover)
        delivered, delivered_view, deliver_api = await command(e, case_id, "deliver", sales,
            lookups=[("evidence_id", signed["name"] + " · 提车签回件", signed["id"])])
        final_physical = physical(e, source, state="exited", case_id=case_id, delivered=True)
        require(delivered["case"]["state"] == "delivered" and delivered["case"]["completed_date"] is not None
                and delivered["case"]["data"]["handover_file"] == signed["id"]
                and len([ev for ev in delivered["events"] if ev["action"] == "deliver"]) == 1
                and len([ev for ev in delivered["events"] if ev["action"] == "dispatch"]) == 1
                and len(e.db.rows("SELECT id FROM vehicle_position_entries WHERE case_id=?", (case_id,))) == 1
                and not [t for t in delivered["tasks"] if t["status"] == "open"], "客户接车或唯一出库/任务结果错误")
        await expect(e.page.locator("#main .taskstate.open")).to_have_count(0)
        require(delivered_view["business_facts"]["facts"]["sales.delivery_recorded"] is True, "原事实GET未认可本版客户提车")
        await refresh(e, case_id)
        callbacks = e.db.rows("SELECT id,kind,parent_id,customer_id,state,due_date FROM flow_cases WHERE parent_id=? AND kind='callback'", (case_id,))
        if customer["contact_allowed"]:
            require(len(callbacks) == 1 and callbacks[0]["customer_id"] == customer["id"], "原交付回访不唯一或串客户")
        await checkpoint.passed({"case_id": case_id, "handover_document": handover_evidence, "signed_handover": signed_evidence,
            "task_owner": deliver_owner, "native_deliver": deliver_api, "physical": final_physical, "refresh_business_unchanged": True,
            "callback_sources": callbacks, "db": delivered}, conditional=[
            {"check_id": "HK-011-business-edge-1", "status": "partial", "tested": ["原生成字节/快照/本版/VIN签回", "出库尚未接车", "刷新不重复"],
             "not_tested": ["错源或旧VIN签回提交拒绝"]}])
        checkpoint.start("HK-009")
        await checkpoint.passed({"case_id": case_id, "lead_id": lead["id"], "customer_id": customer["id"],
            "vehicle": source, "payment": cash_evidence, "inspection": {"owner": inspection_owner, "file": inspection_file, "native": inspection_api},
            "dispatch": dispatch_api, "handover": handover_evidence, "signed_handover": signed_evidence, "deliver": deliver_api,
            "physical": final_physical, "callback_sources": callbacks, "db": delivered}, conditional=[
            {"check_id": "HK-009-business-edge-1", "status": "partial", "tested": ["待确认报价冻结实收", "同版签回及原足额到账/合格PDI分别留事实", "刷新不重复办理"],
             "not_tested": ["不合格检查/技师整改/复检", "已约定另单服务未完成守卫"]}])
        checkpoint.finish({"lead_id": lead["id"], "customer_id": customer["id"], "delivered_order_id": case_id,
                           "delivered_vehicle_id": source["vehicle"]["id"]})
    except Exception as error:
        checkpoint.failed(error)
        raise


async def sales_cancellation(e, context, credentials):
    checkpoint = Checkpoint(e, CANCELLATION_SCENARIO, ("HK-010",))
    checkpoint.start("HK-010")
    try:
        fixture, lead, customer, sources, delivery = dependencies(e, checkpoint, cancellation=True)
        source = selected_source(sources, "hybrid")
        require(source["vehicle"]["id"] != delivery["report_sources"]["delivered_vehicle_id"], "退订不得复用已交付实车")
        f, created = await create_quote(e, context, credentials, fixture, lead, customer, source, from_lead=False)
        case_id = f["case"]["id"]
        checkpoint.note({"case_id": case_id, "create": created})
        _, approval = await approve(e, context, credentials, fixture, case_id)
        _, allocation = await allocate(e, context, credentials, fixture, case_id, source)
        _, signature = await sign_current(e, context, credentials, fixture, case_id, 1)
        deposited, deposit_view, deposit = await payment(e, context, credentials, fixture, case_id, 300000, "deposit")
        require(deposit_view["paid_cents"] == 300000 and not [ev for ev in deposited["events"] if ev["action"] in {"inspect", "dispatch", "deliver"}]
                and not e.db.rows("SELECT id FROM flow_cases WHERE parent_id=? AND kind IN ('addon','insurance','agency')", (case_id,)), "快捷取消原单已有实物或另单履约")
        sales, _ = await detail_as(e, context, credentials, fixture["sales_key"], case_id, fixture["store_id"])
        requested, _, cancellation_api = await command(e, case_id, "cancel_request", sales, {"reason": "本次合成客户在未履约和未出库前退订，原实收按原账户退回"})
        require(requested["case"]["state"] == "cancel_review" and requested["holds"] == deposited["holds"], "申请退订提前退款或释放占车")
        manager, _, owner = await responsible(e, context, credentials, fixture, case_id, "cancel_approve", "manager")
        require(manager["id"] != sales["id"], "退订批准不得同申请人")
        approved, _, approval_api = await command(e, case_id, "cancel_approve", manager)
        require(approved["case"]["state"] == "refund_pending" and approved["holds"] == deposited["holds"]
                and approved["payments"] == deposited["payments"], "退订批准冒充退款或提前解占")
        checkpoint.note({"approval": approval, "allocation": allocation, "signature": signature, "deposit": deposit,
                         "native_cancel_request": cancellation_api, "cancel_approval": {"owner": owner, "native": approval_api}, "db": approved})
        refunded, refund_view, refund = await payment(e, context, credentials, fixture, case_id, 300000, "return", original=deposit["payment"])
        require(refunded["case"]["state"] == "cancelled" and refunded["case"]["completed_date"] is not None
                and not refunded["holds"] and len(refunded["payments"]) == len(refunded["cash"]) == 2
                and refund_view["paid_cents"] == 0 and not [t for t in refunded["tasks"] if t["status"] == "open"], "原退款未清零/解占或原单未结束")
        final_physical = physical(e, source, state="stored")
        require(not e.db.rows("SELECT id FROM vehicle_position_entries WHERE case_id=?", (case_id,)), "未履约退订制造实车出库流水")
        await refresh(e, case_id)
        await stock_ui(e, source, "available", "可售")
        await checkpoint.passed({"case_id": case_id, "lead_id": lead["id"], "customer_id": customer["id"], "create": created,
            "approval": approval, "allocation": allocation, "signature": signature, "deposit": deposit,
            "cancel_request": cancellation_api, "cancel_approval": approval_api, "refund": refund,
            "physical": final_physical, "refresh_business_unchanged": True, "db": refunded}, conditional=[
            {"check_id": "HK-010-business-edge-1", "status": "partial", "tested": ["原有实收按原账户与original_id退回", "原款追加不覆盖", "退款清零后解占"],
             "not_tested": ["无原实收拒绝虚构退款", "已加装/代缴/承保终止及保留费用"]},
            {"check_id": "HK-010-aftercare-fulfilled", "status": "not_tested", "reason": "本轮第二单没有另服务履约或出库；已履约退订、提车后退车须另一个真实售后增量"}])
        checkpoint.finish({**delivery["report_sources"], "cancelled_order_id": case_id,
                           "cancelled_vehicle_id": source["vehicle"]["id"]})
    except Exception as error:
        checkpoint.failed(error)
        raise


SALES_ORDER_SCENARIOS = ((SCENARIO, sales_order, 300), (CANCELLATION_SCENARIO, sales_cancellation, 180))
