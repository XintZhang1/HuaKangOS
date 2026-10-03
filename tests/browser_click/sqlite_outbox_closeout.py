"""Finite native UI concurrency and read-only outbox transaction observations."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import os
import uuid

from runtime_faults import _atomic_json, _digest, _load, _require, _utc


@contextmanager
def observe_outbox(manifest):
    from app import assistant_runtime_outbox as outbox, assistant_runtime_queue as queue
    from app.db import engine
    from sqlalchemy import event
    from unittest.mock import patch

    path = Path(manifest["evidence_root"]) / ("outbox-transactions-" + str(os.getpid()) + ".json")
    current = ContextVar("synthetic_outbox_observation", default=None)
    report = {"schema": 1, "synthetic_only": True, "calls": [], "database_errors": []}
    original_reserve = queue._sqlite_writer

    def reserve(db):
        row = current.get()
        if row is not None:
            row["reservations"].append({"before_transaction": db.in_transaction(), "sql": []})
        original_reserve(db)
        if row is not None:
            reservation = row["reservations"][-1]
            reservation["after_transaction"] = db.in_transaction()
            reservation["writer_reserved"] = any(sql["verb"] == "UPDATE" and sql["runs_table"]
                                                for sql in reservation["sql"])

    def before_sql(connection, cursor, statement, parameters, context, executemany):
        row = current.get()
        if row is None or not row["reservations"]:
            return
        reservation = row["reservations"][-1]
        if "after_transaction" in reservation:
            return
        verb = statement.strip().split(None, 1)[0].upper()
        reservation["sql"].append({"verb": verb if verb in {"BEGIN", "UPDATE", "SELECT"} else "other",
                                   "runs_table": "business_assistant_runs" in statement})

    def error(context):
        code = getattr(context.original_exception, "sqlite_errorcode", None)
        if code is not None:
            report["database_errors"].append({"code": code, "utc": _utc(),
                                              "outbox_call": (current.get() or {}).get("kind")})
            _atomic_json(path, report)

    def wrapper(original, kind):
        async def observed(*args, **kwargs):
            row = {"kind": kind, "started_at": _utc(), "reservations": []}
            token = current.set(row)
            try:
                value = await original(*args, **kwargs)
                row["result"] = getattr(value, "state", getattr(value, "status", None))
                row["event_id"] = getattr(value, "event_id", None)
                return value
            except Exception as exc:
                row["error_type"] = type(exc).__name__
                raise
            finally:
                current.reset(token)
                if row["reservations"] or row.get("error_type"):
                    report["calls"].append(row)
                    _atomic_json(path, report)
        return observed

    event.listen(engine, "before_cursor_execute", before_sql)
    event.listen(engine, "handle_error", error)
    _atomic_json(path, report)
    try:
        with patch.object(queue, "_sqlite_writer", reserve), \
                patch.object(outbox, "dispatch_one", wrapper(outbox.dispatch_one, "dispatch")), \
                patch.object(outbox, "poll_due_plan", wrapper(outbox.poll_due_plan, "poll")):
            yield
    finally:
        event.remove(engine, "before_cursor_execute", before_sql)
        event.remove(engine, "handle_error", error)
        _atomic_json(path, report)


async def sqlite_native_concurrency(e, context, credentials):
    from scenarios import Evidence
    from customer_service_business import customer_form, fields
    from vehicle_purchase_business import nav
    from playwright.async_api import expect
    from urllib.parse import urlsplit

    actors, contexts, evidence = [], [], []
    initial = e.business_snapshot("native_concurrency_original_business_before")
    old_customers = e.db.rows("SELECT * FROM flow_customers ORDER BY id")
    source_tables = {"flow_customers", "flow_cases", "flow_tasks", "flow_events", "flow_request_receipts", "audit_logs"}
    old_sources = {table: {_digest(row) for row in e.db.rows("SELECT * FROM " + table)} for table in source_tables}
    try:
        for role in ("admin", "manager", "finance"):
            ctx = await context.browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
            contexts.append(ctx)
            item = Evidence(e.manifest, e.secrets, e.directory.name + "-" + role)
            evidence.append(item)
            page = await ctx.new_page()
            page.set_default_timeout(15000)
            await item.attach(ctx, page)
            user = await item.login(ctx, credentials, role)
            user = {**user, "store_id": int(await item.page.locator("#store").input_value())}
            await nav(item, "master/customers", "客户档案", "/api/flow/master/customers")
            actors.append((item, user))
        writes = []

        async def create(actor, index):
            item, user = actor
            name = "合成并发客户_" + uuid.uuid4().hex[:12]
            phone = "199" + str(int(uuid.uuid4().hex[:10], 16) % 100000000).zfill(8)
            await expect(item.page.locator('#main [data-act="newmaster"][data-kind="customers"]')).to_be_visible()
            await customer_form(item)
            await fields(item, {"name": name, "phone": phone, "contact_allowed": False,
                                "note": "有限原生并发第" + str(index) + "轮"})
            async with item.page.expect_response(lambda r: r.request.method == "POST" and
                    urlsplit(r.url).path == "/api/flow/master/customers") as pending:
                await item.click('#modal form button[type="submit"]', "原表单单次提交客户")
            response = await pending.value
            body = await response.json()
            _require(response.status == 201 and body["name"] == name and body["store_id"] == user["store_id"],
                     "有限原生并发新增客户未返回原201/本人门店")
            await expect(item.page.locator("#modal")).not_to_be_visible()
            writes.append({"id": body["id"], "name": name, "phone": phone, "status": response.status})

        async def refresh(item):
            async with item.page.expect_response(lambda r: r.request.method == "GET" and
                    urlsplit(r.url).path == "/api/flow/master/customers") as pending:
                item.action("browser_reload", "财务原页面并发读取")
                await item.page.reload(wait_until="domcontentloaded")
            _require((await pending.value).status == 200, "原页面并发读取失败")

        for index in range(4):
            await asyncio.gather(create(actors[0], index), create(actors[1], index), refresh(actors[2][0]))
        _require(len(writes) == 8 and len({row["id"] for row in writes}) == 8, "并发提交不是八个独立唯一客户")
        now = {row["id"]: row for row in e.db.rows("SELECT * FROM flow_customers ORDER BY id")}
        _require(all(now[row["id"]] == row for row in old_customers), "并发新增覆盖旧客户")
        # The original Flow creates actual wake sources. Master customer
        # writes alone do not emit Flow events and cannot exercise dispatch.
        for item, _ in actors[:2]:
            await nav(item, "cases/lead", "售前接待", "/api/flow/cases")

        async def create_lead(actor, index):
            item, user = actor
            button = item.page.locator('[data-act="newcase"][data-kind="lead"]')
            await expect(button).to_be_visible()
            await item.click('[data-act="newcase"][data-kind="lead"]', "原新建售前接待")
            await expect(item.page.locator("#modal-title")).to_have_text("新建售前接待")
            name = "合成并发接待_" + uuid.uuid4().hex[:12]
            await item.fill('#modal [name="customer_name"]', name, "原接待客户姓名")
            await item.page.locator('#modal [name="source"]').select_option(label="展厅到店")
            item.action("select", "原接待来源", value="展厅到店")
            async with item.page.expect_response(lambda r: r.request.method == "POST" and
                    urlsplit(r.url).path == "/api/flow/cases") as pending:
                await item.click('#modal form button[type="submit"]', "单次原生接待提交")
            response = await pending.value
            body = await response.json()
            _require(response.status == 201 and body["store_id"] == user["store_id"],
                     "原生并发售前接待没有本人门店的201")
            await expect(item.page.locator("#modal")).not_to_be_visible()
            await expect(item.page.locator("#main h1")).to_have_text(body["title"])

        for index in range(4):
            await asyncio.gather(create_lead(actors[0], index), create_lead(actors[1], index), refresh(actors[2][0]))
            for item, _ in actors[:2]:
                await nav(item, "cases/lead", "售前接待", "/api/flow/cases")
        after = e.business_snapshot("native_concurrency_original_business_after")
        changed = {name for name in initial["tables"] if initial["tables"][name] != after["tables"][name]}
        _require(changed == source_tables,
                 "并发客户/接待新增修改了其它原业务表")
        for table, hashes in old_sources.items():
            _require(hashes.issubset({_digest(row) for row in e.db.rows("SELECT * FROM " + table)}),
                     "并发新增覆盖或删除旧来源行：" + table)
        await e.wait(lambda: not e.db.rows("SELECT id FROM business_assistant_wake_events WHERE state='pending'"),
                     "全部真实唤醒自然分发", timeout=45)
        traces = [_load(path) for path in Path(e.manifest["evidence_root"]).glob("outbox-transactions-*.json")]
        trace = {"calls": [row for report in traces for row in report["calls"]],
                 "database_errors": [row for report in traces for row in report["database_errors"]]}
        reservations = [r for call in trace["calls"] for r in call["reservations"]]
        _require(reservations and all(r["writer_reserved"] and not r["before_transaction"]
                                     for r in reservations), "分发写事务没有在来源读取前预留SQLite写锁")
        _require(not trace["database_errors"], "有限负载发生SQLite异常，不能关闭SQ01")
        events = e.db.rows("SELECT id,signal_key,state FROM business_assistant_wake_events ORDER BY id")
        _require(all(row["state"] == "dispatched" for row in events) and
                 len({row["signal_key"] for row in events}) == len(events), "唤醒丢失或重复")
        e.observe("cutie_sq01_finite_native_matrix", {"writes": writes, "trace": trace, "events": events,
                  "old_customer_rows_unchanged": True, "other_business_tables_unchanged": True,
                  "capacity_benchmark": False, "postgresql_tested": False})
    finally:
        for item in evidence:
            result = await item.finish()
            e.actions.extend(item.actions)
            e.network.extend(item.network)
            e.page_errors.extend(item.page_errors)
            e.external_requests.extend(item.external_requests)
            e.observe("concurrent_actor_evidence", {"directory": str(item.directory), **result})
        for ctx in contexts:
            await ctx.close()


SQLITE_OUTBOX_SCENARIOS = (("sqlite-native-outbox-concurrency", sqlite_native_concurrency, 180),)
