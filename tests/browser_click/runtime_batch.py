"""Two finite native customer batches; original confirmation remains real.

Importing this module starts nothing and imports no application module. The
single unknown-result fixture drops only an armed second card's already-returned
201, after reading its committed customer and audit through SELECT-only evidence.
"""
from contextlib import contextmanager
import asyncio
import json
from pathlib import Path
import re
import uuid
from urllib.parse import urlsplit

from runtime_faults import _atomic_json, _digest, _load, _require, _rows, _utc


OPERATION = "POST /api/flow/master/{kind}"


def _decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def _payload(card):
    value = _decoded(card["payload"])
    return {"path_args": value.get("path_args") or {}, "query": value.get("query") or {},
            "body": value.get("body") or {}}


def _confirmation(item, card):
    snapshot = _decoded(item["submission_snapshot"])
    payload = _payload(card)
    _require(item["kind"] == "confirmation" and item["proposal_id"] == card["id"]
             and item["work_item_id"] == card["source_work_item_id"] and item["run_id"] is None
             and item["attempt_no"] == 1 and item["item_key"] == "confirmation:" + card["id"]
             and isinstance(snapshot, dict) and set(snapshot) == {
                 "operation_id", "path_args", "query", "body", "request_id", "actor_id", "store_id",
                 "role", "access_version", "confirmed_at"}
             and snapshot["operation_id"] == card["operation_id"] == OPERATION
             and all(snapshot[key] == payload[key] for key in ("path_args", "query", "body"))
             and snapshot["actor_id"] == card["owner_id"] and snapshot["store_id"] == card["store_id"]
             and snapshot["role"] == card["owner_role"] and snapshot["access_version"] == card["access_version"]
             and snapshot["request_id"] is None and payload["body"].get("request_id") is None
             and isinstance(snapshot["confirmed_at"], str)
             and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", snapshot["confirmed_at"])
             and _digest(snapshot) == item["submission_digest"],
             "原确认必须按真实proposal/work来源冻结同本人门店、内容、版本与摘要，不造原回执")
    return snapshot


@contextmanager
def batch_submission_fault(manifest):
    """Wrap the Web process's gateway once; all unarmed calls pass through."""
    from app import business_assistant_gateway as gateway
    import httpx

    runtime, evidence = Path(manifest["runtime_root"]).resolve(), Path(manifest["evidence_root"]).resolve()
    database = Path(manifest["database_path"]).resolve()
    _require(runtime.is_dir() and evidence.is_dir() and database.is_relative_to(runtime),
             "批量返回丢失仅可安装在本局外部合成实例")
    arm_path, ledger_path = runtime / "batch-result-unknown-arm.json", evidence / "batch-submission-fault.json"
    _require(not arm_path.exists() and not ledger_path.exists(), "不能复用旧批量故障arm或账本")
    ledger = {"schema": 1, "phase": "unarmed", "native_invocations": 0, "loss_injections": 0}
    _atomic_json(ledger_path, ledger)
    original, used = gateway.invoke, False

    async def invoke(request, user, operation_id, path_args=None, query=None, body=None):
        nonlocal used, ledger
        if not arm_path.is_file():
            return await original(request, user, operation_id, path_args, query, body)
        arm = _load(arm_path)
        target = "/api/business-assistant/sessions/" + arm["session_id"] + "/proposals/" + arm["proposal_id"] + "/confirm"
        if request.method != "POST" or request.url.path != target:
            return await original(request, user, operation_id, path_args, query, body)
        if used:
            ledger.update(phase="duplicate_fault_target", repeated_at=_utc())
            _atomic_json(ledger_path, ledger)
            raise RuntimeError("The armed native confirmation cannot be replayed")
        used = True
        ledger.update(phase="armed_target_seen", proposal_id=arm["proposal_id"], work_item_id=arm["work_item_id"],
                      session_id=arm["session_id"], owner_id=arm["owner_id"], store_id=arm["store_id"], observed_at=_utc())
        _atomic_json(ledger_path, ledger)
        try:
            _require(set(arm) == {"schema", "group", "run_id", "session_id", "proposal_id", "work_item_id", "owner_id",
                "store_id", "owner_role", "access_version", "proposal_digest", "proposal_version", "proposal_payload_sha256",
                "prepare_work_sha256", "operation_id", "payload", "name", "phone"}
                and arm["schema"] == 1 and re.fullmatch(r"浏览器批量unknown_[0-9a-f]{12}", arm["group"])
                and arm["name"] == arm["group"] + "_B" and operation_id == arm["operation_id"] == OPERATION
                and getattr(user, "id", None) == arm["owner_id"] and getattr(user, "role", None) == arm["owner_role"]
                and getattr(user, "access_version", None) == arm["access_version"]
                and getattr(user, "_active_store_id", None) == arm["store_id"]
                and request.headers.get("x-store-id") == str(arm["store_id"])
                and request.headers.get("cookie") and request.headers.get("x-csrf-token"),
                "arm必须匹配原第二客户卡、员工本人、本店与原confirm路径")
            submitted = {"path_args": path_args or {}, "query": query or {}, "body": body or {}}
            _require(submitted == arm["payload"] and submitted["path_args"] == {"kind": "customers"}
                     and submitted["query"] == {} and _digest(submitted) == arm["proposal_payload_sha256"]
                     and await request.json() == {"digest": arm["proposal_digest"]},
                     "故障只能匹配员工原点击的digest及原冻结业务路径和完整正文")
            cards = _rows(database, "SELECT * FROM business_assistant_proposals WHERE id=?", (arm["proposal_id"],))
            works = _rows(database, "SELECT * FROM business_assistant_work_items WHERE id=?", (arm["work_item_id"],))
            items = _rows(database, "SELECT * FROM business_assistant_run_items WHERE proposal_id=? AND kind='confirmation'", (arm["proposal_id"],))
            runs = _rows(database, "SELECT * FROM business_assistant_runs WHERE id=?", (arm["run_id"],))
            _require(len(cards) == len(works) == len(items) == len(runs) == 1, "第二原卡/准备来源/确认冻结/原Run必须唯一真实存在")
            card, item = cards[0], items[0]
            _require(card["status"] == "executing" and card["version"] == arm["proposal_version"] + 1
                     and card["digest"] == arm["proposal_digest"] and _payload(card) == arm["payload"]
                     and (card["owner_id"], card["store_id"], card["session_id"], card["source_work_item_id"])
                         == (arm["owner_id"], arm["store_id"], arm["session_id"], arm["work_item_id"])
                     and card["step_label"] == arm["group"] and card["request_id"] == runs[0]["request_id"]
                     and runs[0]["status"] == "succeeded"
                     and (runs[0]["owner_id"], runs[0]["store_id"], runs[0]["session_id"])
                         == (arm["owner_id"], arm["store_id"], arm["session_id"])
                     and works[0]["item_kind"] == "prepare" and works[0]["status"] == "prepared"
                     and works[0]["operation_id"] == OPERATION and works[0]["origin_request_id"] == runs[0]["request_id"]
                     and (works[0]["owner_id"], works[0]["store_id"], works[0]["session_id"])
                         == (arm["owner_id"], arm["store_id"], arm["session_id"])
                     and _digest(works[0]) == arm["prepare_work_sha256"] and item["status"] == "running"
                     and not _rows(database, "SELECT id FROM flow_customers WHERE name=?", (arm["name"],)),
                     "故障点必须在真实冻结已提交、B原客户尚未产生的边界")
            snapshot = _confirmation(item, card)
            ledger.update(phase="native_invoking", native_invocations=1, confirmation_id=item["id"],
                          submission_digest=item["submission_digest"], snapshot_sha256=_digest(snapshot), invoked_at=_utc())
            _atomic_json(ledger_path, ledger)
            result = await original(request, user, operation_id, path_args, query, body)
            customers = _rows(database, "SELECT * FROM flow_customers WHERE name=?", (arm["name"],))
            _require(result.get("status") == 201 and len(customers) == 1, "原invoke必须真实返回201且客户已提交后才允许丢返回")
            customer = customers[0]
            audits = _rows(database, "SELECT * FROM audit_logs WHERE entity_type='flow_master' AND entity_id=? AND action='master_create' ORDER BY id", (customer["id"],))
            _require(result.get("data", {}).get("id") == customer["id"] and customer["name"] == arm["name"]
                     and customer["phone"] == arm["phone"] and customer["owner_id"] == arm["owner_id"]
                     and customer["store_id"] == arm["store_id"] and not customer["contact_allowed"]
                     and len(audits) == 1 and audits[0]["actor_id"] == arm["owner_id"]
                     and audits[0]["store_id"] == arm["store_id"] and audits[0]["reason"] == "客户档案",
                     "原201必须对应本人本店真实B客户与原master_create审计，不能合成成功JSON")
            ledger.update(phase="native_committed_response_dropped", native_status=201, customer_id=customer["id"],
                          customer_sha256=_digest(customer), audit_id=audits[0]["id"], audit_sha256=_digest(audits[0]),
                          native_returned_at=_utc(), loss_injections=1, fault_type="httpx.ReadError")
            _atomic_json(ledger_path, ledger)
        except Exception as error:
            ledger.update(phase="fault_validation_failed", error_type=type(error).__name__, failed_at=_utc())
            _atomic_json(ledger_path, ledger)
            raise
        raise httpx.ReadError("Synthetic batch response lost after the original native commit")

    gateway.invoke = invoke
    normal = False
    try:
        yield
        normal = True
    finally:
        gateway.invoke = original
        if normal and arm_path.exists():
            final = _load(ledger_path)
            _require(used and final["phase"] == "native_committed_response_dropped"
                     and final["native_invocations"] == final["loss_injections"] == 1,
                     "armed批量故障未实际一次原提交并丢返回，正常生命周期不能记通过")


async def _prepare(e, context, credentials, mode):
    from playwright.async_api import expect

    user = await e.login(context, credentials)
    await e.ready()
    before = e.business_snapshot("batch_" + mode + "_original_business_before")
    old = {table: e.db.rows("SELECT * FROM " + table + " ORDER BY id") for table in ("flow_customers", "audit_logs")}
    token = uuid.uuid4().hex[:12]
    group = "浏览器批量" + mode + "_" + token
    number = int(token, 16) % 100000000
    phones = ["199" + str((number + index) % 100000000).zfill(8) for index in range(3)]
    if mode == "rule":
        phones[1] = phones[0]
    values = [{"name": group + "_" + "ABC"[index], "phone": phones[index],
               "contact_allowed": False, "confirm_new_customer": False} for index in range(3)]
    _require(not e.db.rows("SELECT id FROM flow_customers WHERE phone IN (?,?,?)", tuple(phones)),
             "三客户原输入必须使用此前不存在的合法合成电话")
    await e.send("新建客户批量 " + group + "\n" + json.dumps({"rows": values}, ensure_ascii=False))
    run_id, session_id = e.latest_run, e.latest_session
    run = e.db.rows("SELECT * FROM business_assistant_runs WHERE id=?", (run_id,))[0]
    cards = e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY step_order,created_at,id", (session_id,))
    _require(run["status"] == "succeeded" and run["error_code"] is None and run["owner_id"] == user["id"]
             and len(cards) == 3 and len({card["id"] for card in cards}) == 3
             and [_payload(card)["body"].get("values") for card in cards] == values,
             "原完整批量应按员工A/B/C事实实际准备三张来源卡，无漏行或假填")
    works = []
    for card in cards:
        source = e.db.rows("SELECT * FROM business_assistant_work_items WHERE id=?", (card["source_work_item_id"],))
        _require(len(source) == 1 and card["status"] == "pending" and not _decoded(card["questions"])
                 and card["owner_id"] == user["id"] and card["store_id"] == run["store_id"]
                 and card["operation_id"] == OPERATION and card["step_label"] == group
                 and card["request_id"] == run["request_id"] and not card["idempotent"]
                 and _payload(card)["path_args"] == {"kind": "customers"} and _payload(card)["query"] == {}
                 and source[0]["status"] == "prepared" and source[0]["item_kind"] == "prepare"
                 and source[0]["operation_id"] == OPERATION and source[0]["session_id"] == session_id
                 and source[0]["owner_id"] == user["id"] and source[0]["store_id"] == run["store_id"]
                 and source[0]["origin_request_id"] == run["request_id"], "原卡缺少完整当前本人本店准备来源/同组关系")
        works.append(source[0])
    _require(len({work["id"] for work in works}) == len({work["input_item_id"] for work in works}) == 3
             and len({card["request_id"] for card in cards}) == 1, "完整三行必须有三个稳定WorkItem及同一确认组")
    items = e.db.rows("SELECT * FROM business_assistant_run_items WHERE run_id=? ORDER BY id", (run_id,))
    children = [row for row in items if row["kind"] == "batch_row"]
    batch = [row for row in items if row["kind"] == "tool" and row["tool_name"] == "prepare_business_batch"]
    _require(len(batch) == 1 and batch[0]["status"] == "succeeded" and len(children) == 3
             and all(child["status"] == "succeeded" for child in children)
             and {child["proposal_id"] for child in children} == {card["id"] for card in cards}
             and {child["work_item_id"] for child in children} == {work["id"] for work in works}
             and not e.db.rows("SELECT id FROM business_assistant_run_items WHERE kind='confirmation' AND proposal_id IN (?,?,?)", tuple(card["id"] for card in cards)),
             "不能用三张展示卡替代原完整批量工具及逐行实际准备结果")
    for card in cards:
        sidebar = e.page.locator('#ba-sidebar-root [data-baws-action="open"][data-key="proposal:' + card["id"] + '"]')
        await expect(sidebar).to_have_count(1, timeout=10000)
        await expect(sidebar).to_be_visible()
        await expect(sidebar.locator('.ba-side-status')).to_have_text("待你确认")
    e.observe("batch_" + mode + "_sidebar_after_preparation_without_manual_refresh", {
        "proposal_keys": ["proposal:" + card["id"] for card in cards], "statuses": ["pending"] * 3,
        "status_labels": ["待你确认"] * 3, "manual_refresh": False, "sidebar_totals_inferred": False})
    e.business_unchanged(before, "batch_" + mode + "_original_business_after_preparation")
    e.observe("batch_" + mode + "_three_source_cards", {"run_id": run_id, "session_id": session_id,
        "group": group, "values": values, "proposal_ids": [card["id"] for card in cards],
        "work_item_ids": [work["id"] for work in works], "batch_tool_id": batch[0]["id"],
        "input_count": 3, "prepared_count": 3, "confirmation_count": 0, "business_accepted": False})
    return {"user": user, "before": before, "old": old, "run": run, "cards": cards, "works": works,
            "group": group, "values": values, "session_id": session_id}


def _business_delta(e, prepared, count):
    after = e.business_snapshot("batch_original_business_after_partial_confirmation")
    changed = {name for name in prepared["before"]["tables"].keys() | after["tables"].keys()
               if prepared["before"]["tables"].get(name) != after["tables"].get(name)}
    _require(changed == {"flow_customers", "audit_logs"}, "原批量只允许实际已提交客户和原审计新增")
    added = {}
    for table, old in prepared["old"].items():
        current = {row["id"]: row for row in e.db.rows("SELECT * FROM " + table + " ORDER BY id")}
        _require(all(current.get(row["id"]) == row for row in old), "批量更改或删除旧事实：" + table)
        old_ids = {row["id"] for row in old}
        added[table] = [row for key, row in current.items() if key not in old_ids]
        _require(len(added[table]) == count, "原批量新增行数不符合实际已提交项：" + table)
    customers = sorted(added["flow_customers"], key=lambda row: row["id"])
    _require([(row["name"], row["phone"]) for row in customers]
                == [(row["name"], row["phone"]) for row in prepared["values"][:count]]
             and all(row["owner_id"] == prepared["user"]["id"] and row["store_id"] == prepared["run"]["store_id"]
                     and not row["contact_allowed"] for row in customers), "实际原客户姓名/电话/选择/本人门店不一致")
    for customer in customers:
        audits = [row for row in added["audit_logs"] if row["entity_id"] == customer["id"]]
        _require(len(audits) == 1 and audits[0]["entity_type"] == "flow_master" and audits[0]["action"] == "master_create"
                 and audits[0]["actor_id"] == prepared["user"]["id"] and audits[0]["store_id"] == prepared["run"]["store_id"]
                 and audits[0]["reason"] == "客户档案", "原批量每个已提交客户须恰一条真实同本人同店审计")
    e.observe("batch_original_business_append_only", {"changed_tables": sorted(changed),
        "appended_customer_ids": [row["id"] for row in customers], "appended_audit_ids": [row["id"] for row in added["audit_logs"]],
        "old_rows_whole_unchanged": True, "all_other_business_tables_unchanged": True,
        "successful_business_transactions": count, "whole_batch_rollback": False})
    return after, customers


async def _confirm_and_review(e, prepared, mode):
    from playwright.async_api import expect

    cards, session_id = prepared["cards"], prepared["session_id"]
    prefix = "/api/business-assistant/sessions/" + session_id + "/proposals/"
    requests, responses = [], []
    def requested(request):
        if request.method == "POST" and urlsplit(request.url).path.startswith(prefix) and urlsplit(request.url).path.endswith("/confirm"):
            requests.append(request)
    def responded(response):
        if response.request.method == "POST" and urlsplit(response.url).path.startswith(prefix) and urlsplit(response.url).path.endswith("/confirm"):
            responses.append(response)
    e.page.on("request", requested)
    e.page.on("response", responded)
    try:
        await e.click(".ba-batch-tools > summary", "展开本组批量办理")
        await e.click('[data-ba-action="card-confirm-all"]', "员工核对并办理本组")
        await expect(e.page.locator("#modal-title")).to_have_text("核对本组办理事项")
        labels = await e.page.locator("#modal .ba-batch-review p").all_text_contents()
        _require(len(labels) == 3 and all(value["name"] in labels[index] for index, value in enumerate(prepared["values"])),
                 "批量审阅必须展示真实A/B/C原三卡顺序和姓名")
        _require(not requests, "打开批量审阅不等于确认，不得提前POST")
        e.business_unchanged(prepared["before"], "batch_" + mode + "_after_review_before_explicit_submit")
        await e.snapshot("batch-" + mode + "-original-three-card-review")
        await e.click('#modal button[type="submit"]', "员工已核对，逐项办理")
        def final_cards():
            rows = e.db.rows("SELECT id,status FROM business_assistant_proposals WHERE session_id=?", (session_id,))
            states = {row["id"]: row["status"] for row in rows}
            return states if states.get(cards[0]["id"]) == "succeeded" and states.get(cards[1]["id"]) in {"failed", "uncertain"} else None
        await e.wait(final_cards, "原逐项确认在第二项失败或不明后暂停", timeout=40)
        await e.ready()
        await expect(e.page.locator("#business-assistant")).to_contain_text("已成功办理 1 / 3 项")
        await expect(e.page.locator("#business-assistant")).to_contain_text("后续尚未提交")
        await e.wait(lambda: len(responses) == 2, "两张原confirm HTTP真实返回")
        expected_paths = [prefix + card["id"] + "/confirm" for card in cards[:2]]
        _require([urlsplit(request.url).path for request in requests] == expected_paths
                 and [urlsplit(response.url).path for response in responses] == expected_paths,
                 "前端只能依次POST A/B，第三项不得提交或重复请求")
        for index, (request, response) in enumerate(zip(requests, responses)):
            headers = await request.all_headers()
            body = request.post_data_json
            view = await response.json()
            expected_state = "succeeded" if index == 0 else "failed" if mode == "rule" else "uncertain"
            by_id = {row["id"]: row for row in view["proposals"]}
            outcomes = view["confirmation_results"]
            _require(response.status == 200 and headers.get("cookie") and headers.get("x-csrf-token")
                     and headers.get("x-store-id") == str(prepared["run"]["store_id"])
                     and body == {"digest": cards[index]["digest"]} and set(by_id) == {card["id"] for card in cards}
                     and by_id[cards[index]["id"]]["status"] == expected_state
                     and len(outcomes) == 1 and outcomes[0]["id"] == cards[index]["id"]
                     and outcomes[0]["status"] == expected_state and outcomes[0]["result_persisted"] is True,
                     "助手confirm HTTP200不能冒充原业务成功，须保留每卡真实结果与本人Cookie/CSRF")
            e.observe("batch_native_confirm_" + "AB"[index], {"proposal_id": cards[index]["id"],
                "path": expected_paths[index], "http_status": response.status, "card_status": expected_state,
                "cookie_present": True, "csrf_present": True, "store_id": prepared["run"]["store_id"],
                "posted_original_digest": True, "business_result": by_id[cards[index]["id"]]["result"]})
        final = e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY step_order,created_at,id", (session_id,))
        _require([row["id"] for row in final] == [card["id"] for card in cards]
                 and [row["status"] for row in final] == ["succeeded", "failed" if mode == "rule" else "uncertain", "pending"]
                 and final[2] == cards[2]
                 and e.db.rows("SELECT * FROM business_assistant_work_items WHERE id=?", (prepared["works"][2]["id"],)) == [prepared["works"][2]],
                 "第二项故障不得回滚A、提交C或改写C原pending卡/WorkItem")
        sidebar_labels = ["原操作已办理", "办理未完成" if mode == "rule" else "结果待核对", "待你确认"]
        for card, label in zip(final, sidebar_labels):
            sidebar = e.page.locator('#ba-sidebar-root [data-baws-action="open"][data-key="proposal:' + card["id"] + '"]')
            await expect(sidebar).to_have_count(1, timeout=10000)
            await expect(sidebar).to_be_visible()
            await expect(sidebar.locator('.ba-side-status')).to_have_text(label, timeout=10000)
        e.observe("batch_" + mode + "_sidebar_after_confirmation_without_manual_refresh", {
            "proposal_keys": ["proposal:" + card["id"] for card in final], "statuses": [card["status"] for card in final],
            "status_labels": sidebar_labels, "manual_refresh": False, "sidebar_totals_inferred": False})
        mutable = {"status", "version", "result", "started_at", "finished_at"}
        for original, current in zip(cards[:2], final[:2]):
            _require(all(current[key] == original[key] for key in original.keys() - mutable), "确认不得替换原卡来源/意图/摘要/身份")
        a_result, b_result = _decoded(final[0]["result"]), _decoded(final[1]["result"])
        _require(a_result["status"] == 201 and b_result["status"] == (409 if mode == "rule" else 503),
                 "原逐项业务状态必须是A201及B自然409或明确结果不明503")
        if mode == "rule":
            _require(isinstance(b_result.get("data"), dict)
                     and b_result["data"].get("detail") == "此联系电话有当前获权的客户档案，请明确选择复用，或核对后确认另建独立档案；不会自动合并"
                     and "权限" not in b_result["message"] and not b_result.get("hint"),
                     "B必须由原客户选择规则拒绝，不得伪称权限或捏造评审refusal")
        else:
            ledger = _load(Path(e.manifest["evidence_root"]) / "batch-submission-fault.json")
            _require(ledger["phase"] == "native_committed_response_dropped" and ledger["native_status"] == 201
                     and ledger["native_invocations"] == ledger["loss_injections"] == 1
                     and ledger["proposal_id"] == cards[1]["id"] and b_result["data"] is None
                     and b_result["message"] == "未收到办理结果，请先到原页面核对记录，避免重复办理",
                     "结果不明必须来源原B真实201提交后的一次返回丢失，不能造未知状态")
            e.observe("batch_original_B_committed_response_lost", ledger)
        confirmations = e.db.rows("SELECT * FROM business_assistant_run_items WHERE kind='confirmation' AND proposal_id IN (?,?,?) ORDER BY created_at,id", tuple(card["id"] for card in cards))
        _require(len(confirmations) == 2 and [item["proposal_id"] for item in confirmations] == [card["id"] for card in cards[:2]],
                 "确认记录须按真实proposal/work来源读取且只存在A/B，无C冻结提交")
        for index, item in enumerate(confirmations):
            snapshot = _confirmation(item, cards[index])
            expected_error = None if index == 0 else "precondition_conflict" if mode == "rule" else "runtime_unavailable"
            _require(item["status"] == ("succeeded" if index == 0 else "failed" if mode == "rule" else "uncertain")
                     and item["error_code"] == expected_error and item["finished_at"], "原确认attempt结果/错误分类不符")
            e.observe("batch_frozen_confirmation_" + "AB"[index], {"confirmation_id": item["id"],
                "proposal_id": item["proposal_id"], "work_item_id": item["work_item_id"], "run_id": item["run_id"],
                "status": item["status"], "error_code": item["error_code"], "submission_digest": item["submission_digest"],
                "frozen_snapshot_sha256": _digest(snapshot), "native_request_id": snapshot["request_id"],
                "receipt_lookup_tested": False})
        after, customers = _business_delta(e, prepared, 1 if mode == "rule" else 2)
        _require(a_result["data"]["id"] == customers[0]["id"], "原A201结果须指向真实新增客户")
        if mode == "unknown":
            _require(ledger["customer_id"] == customers[1]["id"] and ledger["customer_sha256"] == _digest(customers[1]),
                     "丢返回账本必须对应真实B已提交客户整行")
        await e.click('[data-ba-action="queue-filter"][data-filter="attention"]', "查看原第二卡需处理结果")
        shown = e.page.locator('.ba-proposal[data-proposal="' + cards[1]["id"] + '"]')
        await expect(shown).to_be_visible()
        await expect(shown).to_contain_text(prepared["values"][1]["name"])
        await expect(shown.locator(".pill")).to_have_text("未办成" if mode == "rule" else "待核对结果")
        if mode == "unknown":
            await expect(shown).to_contain_text("结果尚未确定：原单可能已经提交")
            await expect(shown).to_contain_text("不要重复办理")
            receipt_before = e.business_snapshot("batch_unknown_original_business_before_receipt_lookup")
            receipt_works = e.db.rows("SELECT * FROM business_assistant_work_items WHERE session_id=? ORDER BY id", (session_id,))
            receipt_runs = e.db.rows("SELECT * FROM business_assistant_runs WHERE session_id=? ORDER BY id", (session_id,))
            receipt_path = prefix + cards[1]["id"] + "/execution-result"
            selector = '#business-assistant-cards [data-baws-action="receipt"][data-session="' + session_id + '"][data-proposal="' + cards[1]["id"] + '"]'
            await expect(e.page.locator(selector)).to_have_text("核对办理结果")
            async with e.page.expect_response(lambda response: urlsplit(response.url).path == receipt_path
                                              and response.request.method == "GET") as pending:
                await e.click(selector, "员工核对第二卡原办理结果，不重发业务")
            receipt_response = await pending.value
            receipt_headers = await receipt_response.request.all_headers()
            receipt = await receipt_response.json()
            _require(receipt_response.status == 200 and receipt_response.url == e.origin + receipt_path
                     and receipt_response.request.post_data is None and receipt_headers.get("cookie")
                     and receipt_headers.get("x-store-id") == str(prepared["run"]["store_id"])
                     and isinstance(receipt, dict) and set(receipt) == {
                         "status", "checked_at", "object_refs", "evidence_refs", "reason_code"}
                     and receipt["status"] == "unsupported" and receipt["reason_code"] == "receipt_family_not_registered"
                     and receipt["object_refs"] == receipt["evidence_refs"] == []
                     and isinstance(receipt["checked_at"], str)
                     and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", receipt["checked_at"]),
                     "原本人本店GET应明确客户档案不支持可靠回执，不能伪称已查得成功或缺失回执")
            await expect(e.page.locator("#toast")).to_have_text("这类业务暂不支持助手核对，请到原页面核对。")
            await expect(e.page.locator("#toast")).to_be_visible()
            await expect(shown.locator(".pill")).to_have_text("待核对结果")
            _require([urlsplit(request.url).path for request in requests] == expected_paths
                     and e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY step_order,created_at,id", (session_id,)) == final
                     and e.db.rows("SELECT * FROM business_assistant_run_items WHERE kind='confirmation' AND proposal_id IN (?,?,?) ORDER BY created_at,id", tuple(card["id"] for card in cards)) == confirmations
                     and e.db.rows("SELECT * FROM business_assistant_work_items WHERE session_id=? ORDER BY id", (session_id,)) == receipt_works
                     and e.db.rows("SELECT * FROM business_assistant_runs WHERE session_id=? ORDER BY id", (session_id,)) == receipt_runs,
                     "回执核对仅可读取，不能改写原卡/WorkItem/冻结提交/Run或重发任何confirm")
            e.business_unchanged(receipt_before, "batch_unknown_original_business_after_receipt_lookup")
            e.observe("batch_B_native_receipt_lookup_unsupported", {"proposal_id": cards[1]["id"],
                "confirmation_id": confirmations[1]["id"], "path": receipt_path, "method": "GET", "http_status": 200,
                "cookie_present": True, "store_id": prepared["run"]["store_id"], "receipt_lookup_tested": True,
                "receipt": receipt, "card_status_after_lookup": "uncertain", "whole_cards_unchanged": True,
                "whole_work_items_unchanged": True, "whole_frozen_confirmations_unchanged": True,
                "whole_runs_unchanged": True, "original_business_table_count": receipt_before["table_count"],
                "original_business_sha256": receipt_before["sha256"], "confirm_request_count": 2,
                "third_confirm_request_count": 0, "business_replayed": False})
            await e.snapshot("batch-unknown-original-receipt-unsupported-still-uncertain")
            await expect(e.page.locator('#business-assistant-cards [data-ba-action="confirm"][data-id="' + cards[1]["id"] + '"]')).to_have_count(0)
            # The original toast retains its text after fading; wait for the
            # native six-second timer before observing a second, late lookup.
            await e.page.wait_for_function("() => { const x=document.querySelector('#toast'); return x && !x.classList.contains('visible'); }", timeout=8000)
            release, held, drained = asyncio.Event(), asyncio.Event(), asyncio.Event()
            route_errors, held_requests = [], []

            async def hold_receipt(route):
                held_requests.append(route.request)
                try:
                    _require(len(held_requests) == 1 and route.request.method == "GET"
                             and route.request.url == e.origin + receipt_path,
                             "迟到探针只能暂停本卡一次原生GET")
                    held.set()
                    await asyncio.wait_for(release.wait(), timeout=10)
                except Exception as error:
                    route_errors.append(e.scrub(error))
                finally:
                    try:
                        # Dispatch the unchanged original request to the server.
                        await route.continue_()
                    except Exception as error:
                        route_errors.append(e.scrub(error))
                    finally:
                        drained.set()

            ui_snapshot = """() => ({
                heading: document.querySelector('#ba-current-heading')?.textContent,
                session_id: businessAssistantState.session?.id || null,
                context: businessAssistantState.context, generation: businessAssistantState.generation,
                draft: document.querySelector('#business-assistant-input')?.value,
                card_count: document.querySelectorAll('#business-assistant-cards .ba-proposal').length,
                receipt_button_count: document.querySelectorAll('#business-assistant-cards [data-baws-action="receipt"]').length,
                receipt_keys: globalThis.AssistantWorkspace.snapshot().receipts.slice().sort(),
                old_receipt_toast_visible: Boolean(document.querySelector('#toast')?.classList.contains('visible')
                    && document.querySelector('#toast')?.textContent === '这类业务暂不支持助手核对，请到原页面核对。')
            })"""
            await e.page.route(e.origin + receipt_path, hold_receipt)
            try:
                async with e.page.expect_response(lambda response: response.url == e.origin + receipt_path
                                                  and response.request.method == "GET") as late_pending:
                    await e.click(selector, "原核对GET派发后切换新对话")
                    await asyncio.wait_for(held.wait(), timeout=5)
                    await e.click('[data-ba-action="new"]', "员工点击原新对话入口")
                    await expect(e.page.locator('.ba-handoff-choice[role="alert"]')).to_contain_text("当前事项还有 2 张待确认或在办的卡片")
                    await expect(e.page.locator('[data-ba-action="handoff-open"]')).to_have_text("保留当前事项并打开")
                    await e.click('[data-ba-action="handoff-open"]', "员工明确保留第三卡并打开新对话")
                    await expect(e.page.locator('#ba-current-heading')).to_have_text("新对话")
                    await e.ready()
                    await expect(e.page.locator('#business-assistant-cards .ba-proposal')).to_have_count(0)
                    new_ui = await e.page.evaluate(ui_snapshot)
                    _require(new_ui["session_id"] is None and new_ui["draft"] == ""
                             and new_ui["receipt_button_count"] == 0 and not new_ui["old_receipt_toast_visible"],
                             "原新对话必须为空且未创建业务确认或残留旧核对提示")
                    release.set()
                late_response = await late_pending.value
                # body() waits for the complete original response without the
                # pinned Playwright finished() target-close watcher.
                await late_response.body()
                await asyncio.wait_for(drained.wait(), timeout=3)
                late_headers = await late_response.request.all_headers()
                late_receipt = await late_response.json()
                _require(late_response.status == 200 and late_response.request.post_data is None
                         and late_headers.get("cookie") and late_headers.get("x-store-id") == str(prepared["run"]["store_id"])
                         and set(late_receipt) == set(receipt)
                         and late_receipt["status"] == "unsupported"
                         and late_receipt["reason_code"] == "receipt_family_not_registered"
                         and late_receipt["object_refs"] == late_receipt["evidence_refs"] == []
                         and isinstance(late_receipt["checked_at"], str)
                         and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", late_receipt["checked_at"]),
                         "切换后必须接收原服务器真实unsupported200，不伪造或恢复回执")
                await e.page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                _require(await e.page.evaluate(ui_snapshot) == new_ui,
                         "旧会话迟到核对不能污染新对话或再弹旧提示；快照只读取缓存键")
                _require([urlsplit(request.url).path for request in requests] == expected_paths
                         and e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY step_order,created_at,id", (session_id,)) == final
                         and e.db.rows("SELECT * FROM business_assistant_run_items WHERE kind='confirmation' AND proposal_id IN (?,?,?) ORDER BY created_at,id", tuple(card["id"] for card in cards)) == confirmations
                         and e.db.rows("SELECT * FROM business_assistant_work_items WHERE session_id=? ORDER BY id", (session_id,)) == receipt_works
                         and e.db.rows("SELECT * FROM business_assistant_runs WHERE session_id=? ORDER BY id", (session_id,)) == receipt_runs,
                         "迟到GET及新对话不得改写原卡/WorkItem/冻结提交/Run或重放A/B/C")
                e.business_unchanged(receipt_before, "batch_unknown_original_business_after_late_receipt_in_new_conversation")
                e.observe("batch_B_native_late_receipt_ignored_in_new_conversation", {
                    "proposal_id": cards[1]["id"], "path": receipt_path, "method": "GET", "http_status": 200,
                    "native_request_held_count": len(held_requests), "gate_timeout_seconds": 10,
                    "request_continued_unchanged": True, "receipt": late_receipt, "new_conversation": new_ui,
                    "old_receipt_toast_visible": False, "receipt_cache_keys_unchanged": True,
                    "receipt_cache_value_observed": False, "whole_cards_unchanged": True,
                    "whole_work_items_unchanged": True, "whole_frozen_confirmations_unchanged": True,
                    "whole_runs_unchanged": True, "original_business_table_count": receipt_before["table_count"],
                    "original_business_sha256": receipt_before["sha256"], "confirm_request_count": 2,
                    "third_confirm_request_count": 0, "business_replayed": False})
                await e.snapshot("batch-unknown-late-receipt-new-conversation-remains-empty")
            finally:
                release.set()
                try:
                    if held_requests:
                        await asyncio.wait_for(drained.wait(), timeout=3)
                finally:
                    await e.page.unroute(e.origin + receipt_path, hold_receipt)
            _require(len(held_requests) == 1 and not route_errors,
                     "原GET暂停必须恰一次且有限收尾，超时或路由错误不得记通过：" + repr(route_errors))
        await expect(e.page.locator('#business-assistant-cards [data-ba-action="confirm"][data-id="' + cards[1]["id"] + '"]')).to_have_count(0)
        await e.snapshot("batch-" + mode + "-second-card-stops-remaining")
        await e.click('[data-ba-action="refresh"]', "原UI刷新批量暂停结果")
        await e.ready()
        await e.click('[data-ba-action="history"]', "展开原对话历史")
        await e.click('[data-ba-action="session"][data-id="' + session_id + '"]', "原UI重读本组原对话")
        await e.ready()
        await e.click('[data-ba-action="queue-filter"][data-filter="pending"]', "核对第三卡仍待本人确认")
        third = e.page.locator('[data-proposal="' + cards[2]["id"] + '"]')
        await expect(third).to_be_visible()
        await expect(third.locator(".pill")).to_have_text("待确认")
        _require([urlsplit(request.url).path for request in requests] == expected_paths
                 and e.db.rows("SELECT * FROM business_assistant_proposals WHERE session_id=? ORDER BY step_order,created_at,id", (session_id,)) == final
                 and e.db.rows("SELECT * FROM business_assistant_run_items WHERE kind='confirmation' AND proposal_id IN (?,?,?) ORDER BY created_at,id", tuple(card["id"] for card in cards)) == confirmations
                 and e.db.rows("SELECT * FROM business_assistant_work_items WHERE id=?", (prepared["works"][2]["id"],)) == [prepared["works"][2]],
                 "刷新或历史重读不能重放A/B、提交C或改写既有冻结记录")
        e.business_unchanged(after, "batch_" + mode + "_original_business_after_refresh_and_history")
        e.observe("batch_" + mode + "_stopped_after_second", {"proposal_ids": [card["id"] for card in cards],
            "statuses": [row["status"] for row in final], "confirm_request_count": 2,
            "third_confirm_request_count": 0, "third_whole_card_unchanged": True, "third_whole_work_item_unchanged": True,
            "frozen_confirmation_count": 2, "refresh_replayed_business": False, "all_three_original_cards_retained": True,
            "assistant_http_200_is_business_success": False, "whole_batch_rollback": False})
        await e.snapshot("batch-" + mode + "-third-pending-after-history-read")
    finally:
        e.page.remove_listener("request", requested)
        e.page.remove_listener("response", responded)


async def batch_rule_failure(e, context, credentials):
    prepared = await _prepare(e, context, credentials, "rule")
    await _confirm_and_review(e, prepared, "rule")


async def batch_result_unknown(e, context, credentials):
    prepared = await _prepare(e, context, credentials, "unknown")
    card, work = prepared["cards"][1], prepared["works"][1]
    arm_path = Path(e.manifest["runtime_root"]) / "batch-result-unknown-arm.json"
    _require(not arm_path.exists(), "本局第二卡结果丢失必须全新arm")
    arm = {"schema": 1, "group": prepared["group"], "run_id": prepared["run"]["id"], "session_id": prepared["session_id"],
           "proposal_id": card["id"], "work_item_id": work["id"], "owner_id": card["owner_id"], "store_id": card["store_id"],
           "owner_role": card["owner_role"], "access_version": card["access_version"], "proposal_digest": card["digest"],
           "proposal_version": card["version"], "proposal_payload_sha256": _digest(_payload(card)),
           "prepare_work_sha256": _digest(work), "operation_id": card["operation_id"], "payload": _payload(card),
           "name": prepared["values"][1]["name"], "phone": prepared["values"][1]["phone"]}
    e.action("synthetic_native_result_loss_arm", "仅arm本组真实第二卡原201后的返回丢失", proposal_id=card["id"], work_item_id=work["id"])
    _atomic_json(arm_path, arm)
    e.observe("batch_second_card_result_loss_armed", {key: value for key, value in arm.items() if key != "payload"})
    await _confirm_and_review(e, prepared, "unknown")
