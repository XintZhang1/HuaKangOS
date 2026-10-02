"""Focused native UI checks on the current isolated scenario's real sources.

The caller owns login, business prerequisites and the Evidence instance. These
checks submit no business or assistant operation and never read an earlier run.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import sqlite3

from playwright.async_api import expect

from sales_business import require


async def review_followup_ui(e, session_id, plan_id, proposal_id, case_id):
    """Review the current followup's untouched second card and local draft."""
    require(e.manifest.get("synthetic_data_only") is True, "M16只允许当前隔离合成实例")
    session = e.db.rows("SELECT * FROM business_assistant_sessions WHERE id=?", (session_id,))
    plan = e.db.rows("SELECT * FROM business_assistant_work_plans WHERE id=?", (plan_id,))
    proposals = e.db.rows("SELECT * FROM business_assistant_proposals WHERE id=?", (proposal_id,))
    cases = e.db.rows("SELECT id,store_id,number,title FROM flow_cases WHERE id=?", (case_id,))
    require(len(session) == len(plan) == len(proposals) == len(cases) == 1, "M16原会话、计划、卡片或原单不唯一")
    session, plan, proposal, case = session[0], plan[0], proposals[0], cases[0]
    require(plan["session_id"] == proposal["session_id"] == session_id
            and session["owner_id"] == plan["owner_id"] == proposal["owner_id"]
            and session["store_id"] == plan["store_id"] == proposal["store_id"] == case["store_id"]
            and str(session["store_id"]) == await e.page.locator("#store").input_value()
            and proposal["status"] == "pending", "M16未复用本人本店真实后继卡")
    payload = json.loads(proposal["payload"])
    require(payload["path_args"]["case_id"] == case_id, "M16后继卡关联原单不同")
    grants = e.db.rows("SELECT status FROM business_assistant_followup_grants WHERE plan_id=?", (plan_id,))
    require(grants and all(row["status"] == "revoked" for row in grants), "M16应在原跟进结束后进行只读补测")

    def assistant_rows():
        # One read transaction protects every field, including changes that
        # leave row counts unchanged. Only hashes enter the evidence report.
        plan_ids = "SELECT id FROM business_assistant_work_plans WHERE session_id=?"
        run_ids = "SELECT id FROM business_assistant_runs WHERE session_id=?"
        card_ids = "SELECT id FROM business_assistant_proposals WHERE session_id=?"
        queries = {
            "business_assistant_sessions": ("id=?", (session_id,)),
            "business_assistant_messages": ("session_id=?", (session_id,)),
            "business_assistant_issues": ("session_id=?", (session_id,)),
            "business_assistant_proposals": ("session_id=?", (session_id,)),
            "business_assistant_work_plans": ("session_id=?", (session_id,)),
            "business_assistant_plan_steps": ("plan_id IN (" + plan_ids + ")", (session_id,)),
            "business_assistant_followup_grants": ("session_id=?", (session_id,)),
            "business_assistant_work_items": ("session_id=?", (session_id,)),
            "business_assistant_runs": ("session_id=?", (session_id,)),
            "business_assistant_context_snapshots": ("session_id=?", (session_id,)),
            "business_assistant_run_items": (
                "run_id IN (" + run_ids + ") OR proposal_id IN (" + card_ids + ")", (session_id, session_id)),
            "business_assistant_run_events": ("run_id IN (" + run_ids + ")", (session_id,)),
            "business_assistant_wake_events": (
                "plan_id IN (" + plan_ids + ") OR proposal_id IN (" + card_ids + ")", (session_id, session_id)),
            "business_assistant_notifications": (
                "session_id=? OR plan_id IN (" + plan_ids + ") OR proposal_id IN (" + card_ids + ")",
                (session_id, session_id, session_id)),
        }
        tables = {}
        with sqlite3.connect(e.db.path.as_uri() + "?mode=ro", uri=True, timeout=5) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            for table, (where, values) in queries.items():
                cursor = connection.execute("SELECT * FROM " + table + " WHERE " + where + " ORDER BY id", values)
                records = cursor.fetchall()
                encoded = json.dumps({"columns": [col[0] for col in cursor.description], "rows": records},
                                     ensure_ascii=False, separators=(",", ":"),
                                     default=lambda value: {"bytes_sha256": hashlib.sha256(value).hexdigest()})
                tables[table] = {"rows": len(records), "sha256": hashlib.sha256(encoded.encode()).hexdigest()}
        digest = hashlib.sha256(json.dumps(tables, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {"sha256": digest, "tables": tables}

    async def tab_until(predicate, limit, label):
        trail = []
        for _ in range(limit):
            e.action("keyboard", label, key="Tab")
            await e.page.keyboard.press("Tab")
            focused = await e.page.evaluate("""() => {const x=document.activeElement;return {
              tag:x.tagName,id:x.id,action:x.dataset.baAction||x.dataset.bawsAction||null,
              proposal_id:x.closest('[data-proposal]')?.dataset.proposal||null,
              label:(x.getAttribute('aria-label')||x.textContent||'').trim().slice(0,70)}}""")
            trail.append(focused)
            if predicate(focused):
                e.observe(label, {"reached": True, "trail": trail})
                return
        e.observe(label, {"reached": False, "trail": trail})
        require(False, label + "：原生Tab未到达目标")

    before = e.business_snapshot("M16_before_native_ui_review")
    assistant_before = assistant_rows()
    e.observe("M16_assistant_rows_before", assistant_before)
    input_selector = "#business-assistant-input"
    original_viewport = e.page.viewport_size
    original_draft = await e.page.locator(input_selector).input_value()
    draft = original_draft or "事项界面核对，保留未发送草稿"
    await e.fill(input_selector, draft, "M16保留未发送草稿")
    expiry = datetime.fromisoformat(proposal["expires_at"].replace("Z", "+00:00"))
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    expired = expiry <= datetime.now(timezone.utc)
    chosen_filter = "attention" if expired else "pending"
    queue_selector = '[data-ba-action="queue-filter"][data-filter="' + chosen_filter + '"]'
    await e.click(queue_selector, "M16按原卡真实截止时间查看")
    selected = e.page.locator("#ba-queue-select")
    require(await selected.count() == 1, "M16原卡选择器不唯一")
    if await selected.input_value() != proposal_id:
        e.action("select", "M16按真实卡片ID选择", proposal_id=proposal_id)
        await selected.select_option(proposal_id)

    for width in (390, 768, 1440):
        label = "M16-" + str(width)
        e.action("viewport", label, width=width, height=1000)
        await e.page.set_viewport_size({"width": width, "height": 1000})
        await e.page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        await e.click('[data-ba-action="history"]', "M16展开原历史入口")
        await expect(e.page.locator('[data-ba-action="history"]')).to_have_attribute("aria-expanded", "true")
        await expect(e.page.locator('.ba-history-popover [data-ba-action="session"][data-id="' + session_id + '"]')).to_have_count(1)
        await e.click('[data-ba-action="history"]', "M16关闭历史后核对主卡")
        await expect(e.page.locator(".ba-history-popover")).to_have_count(0)
        pane = e.page.locator('[data-ba-action="pane-cards"]')
        if await pane.is_visible():
            await e.click('[data-ba-action="pane-cards"]', "M16查看办理事项主卡")
        card = e.page.locator('[data-proposal="' + proposal_id + '"]')
        await expect(card).to_be_visible()
        await expect(card).to_contain_text(case["number"])
        await expect(card).to_contain_text(case["title"])
        await expect(card).to_contain_text("已过期" if expired else "待确认")
        require(await card.locator('a[href="#case/' + str(case_id) + '"]').count() >= 1, "M16主卡缺少真实原单深链接")
        layout = await e.page.evaluate("() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth})")
        e.observe(label + "_main_card_layout", {**layout, "session_id": session_id, "plan_id": plan_id,
                                              "proposal_id": proposal_id, "case_id": case_id, "expired": expired})
        require(layout["scrollWidth"] <= width + 1, label + "：主卡导致整页横向溢出")
        await e.snapshot(label + "-history-closed-main-card")

        if width <= 1024:
            toggle = e.page.locator('[data-baws-action="drawer"]')
            await expect(toggle).to_be_visible()
            for close_by in ("Escape", "mask"):
                await e.click('[data-baws-action="drawer"]', "M16打开本人事项抽屉")
                await expect(toggle).to_have_attribute("aria-expanded", "true")
                await expect(e.page.locator(".ba-side-mask.shown")).to_be_visible()
                if close_by == "Escape":
                    e.action("keyboard", "M16关闭事项抽屉", key="Escape")
                    await e.page.keyboard.press("Escape")
                else:
                    e.action("click", "M16原抽屉遮罩", width=width)
                    await e.page.locator(".ba-side-mask.shown").click(position={"x": width - 5, "y": 60})
                await expect(toggle).to_have_attribute("aria-expanded", "false")
                await expect(toggle).to_be_focused()
                await expect(e.page.locator(".ba-side-mask.shown")).to_have_count(0)
                require(not await e.page.locator(".ba-runtime-workspace").evaluate("x => x.classList.contains('drawer-open')"),
                        label + "：抽屉关闭后仍占主卡")
                e.observe(label + "_" + close_by + "_focus", {"trigger_focused": True, "drawer_closed": True})

        await e.click(queue_selector, "M16从原事项状态按钮开始键盘遍历")
        await tab_until(lambda focused: focused["proposal_id"] == proposal_id, 35, label + "_card_Tab")
        chat = e.page.locator('[data-ba-action="pane-chat"]')
        if await chat.is_visible():
            await e.click('[data-ba-action="pane-chat"]', "M16返回对话保留草稿")
        await e.click('[data-ba-action="history"]', "M16原历史按钮键盘起点")
        await e.click('[data-ba-action="history"]', "M16关闭历史回到输入")
        await tab_until(lambda focused: focused["id"] == "business-assistant-input", 80, label + "_input_Tab")
        await expect(e.page.locator(input_selector)).to_have_value(draft)
        await expect(e.page.locator(".ba-history-popover")).to_have_count(0)
        await e.snapshot(label + "-native-keyboard-draft")

    if not original_draft:
        await e.fill(input_selector, original_draft, "M16清理本次未发送验证草稿")
    if original_viewport:
        e.action("viewport", "M16恢复原场景宽度", **original_viewport)
        await e.page.set_viewport_size(original_viewport)
    assistant_after = assistant_rows()
    e.observe("M16_assistant_rows_after", assistant_after)
    require(assistant_before == assistant_after, "M16读取改变原会话、卡片、计划或Runtime关联全行")
    e.business_unchanged(before, "M16_after_native_ui_review")
    result = {"session_id": session_id, "plan_id": plan_id, "proposal_id": proposal_id, "case_id": case_id,
              "widths": [390, 768, 1440], "card_expired_at_actual_time": expired,
              "assistant_rows_sha256": assistant_before["sha256"], "all_related_assistant_rows_unchanged": True,
              "original_business_unchanged": True, "draft_preserved": True, "business_accepted": False}
    e.observe("M16_pending_ui_review", result)
    return result


async def review_report_table(e, wrapper, label, width=768):
    """Use one trusted wheel to expose this original table's complete last column."""
    require(e.manifest.get("synthetic_data_only") is True, "报表补测只允许当前隔离合成实例")
    require(await wrapper.count() == 1, label + "：原表格容器必须唯一")
    before_business = e.business_snapshot(label + "_before_native_horizontal")
    original_viewport = e.page.viewport_size
    e.action("viewport", label, width=width, height=1000)
    await e.page.set_viewport_size({"width": width, "height": 1000})
    await wrapper.scroll_into_view_if_needed()
    before = await wrapper.evaluate("""x => {const b=x.getBoundingClientRect();
      const header=document.querySelector('.topbar')?.getBoundingClientRect();
      const clip={left:Math.max(0,b.left),right:Math.min(innerWidth,b.right),
                  top:Math.max(0,b.top,header?.bottom||0),bottom:Math.min(innerHeight,b.bottom)};
      const point={x:(clip.left+clip.right)/2,y:(clip.top+clip.bottom)/2};
      const hit=document.elementFromPoint(point.x,point.y);
      return {left:x.scrollLeft,width:x.clientWidth,scrollWidth:x.scrollWidth,point,
              intersection:clip,wrapper_contains_hit:!!hit&&x.contains(hit),
              page:{width:innerWidth,scrollWidth:document.documentElement.scrollWidth}};}""")
    e.observe(label + "_native_wheel_start", before)
    visible = before["intersection"]
    require(visible["right"] > visible["left"] + 2 and visible["bottom"] > visible["top"] + 2
            and before["wrapper_contains_hit"], label + "：真实滚轮落点未命中可见原表格")
    require(before["page"]["scrollWidth"] <= width + 1, label + "：原报表整页横向溢出")
    await e.page.mouse.move(before["point"]["x"], before["point"]["y"])
    acknowledgement = asyncio.create_task(wrapper.evaluate("""x => new Promise(resolve => {
      const started=performance.now(),wheel=[],scroll=[];let timer,done=false;
      const finish=timedOut=>{if(done)return;done=true;clearTimeout(timer);
        x.removeEventListener('wheel',onWheel);x.removeEventListener('scroll',onScroll);
        resolve({timed_out:timedOut,wheel_events:wheel,scroll_events:scroll,left:x.scrollLeft,
                 width:x.clientWidth,scrollWidth:x.scrollWidth,
                 right_reached:x.scrollLeft>=x.scrollWidth-x.clientWidth-1});};
      const check=()=>{if(wheel.length&&x.scrollLeft>=x.scrollWidth-x.clientWidth-1)finish(false);};
      const onWheel=event=>{wheel.push({trusted:event.isTrusted,delta_x:event.deltaX,
        delta_y:event.deltaY,x:event.clientX,y:event.clientY});requestAnimationFrame(check);};
      const onScroll=()=>{scroll.push({left:x.scrollLeft,elapsed_ms:performance.now()-started});check();};
      x.addEventListener('wheel',onWheel,{passive:true});x.addEventListener('scroll',onScroll,{passive:true});
      timer=setTimeout(()=>finish(true),5000);
    })"""))
    try:
        await asyncio.sleep(0)
        await e.page.evaluate("() => true")
        e.action("mouse_wheel", label, delta_x=10000, delta_y=0, point=before["point"], attempt=1)
        await e.page.mouse.wheel(10000, 0)
        ack = await acknowledgement
    finally:
        if not acknowledgement.done():
            acknowledgement.cancel()
            await asyncio.gather(acknowledgement, return_exceptions=True)
    after = await wrapper.evaluate("""x => {const box=x.getBoundingClientRect();return {
      left:x.scrollLeft,width:x.clientWidth,scrollWidth:x.scrollWidth,
      page:{width:innerWidth,scrollWidth:document.documentElement.scrollWidth},
      right_columns:[...x.querySelectorAll('tbody tr')].map(row=>[...row.querySelectorAll('td')].slice(-3).map(cell=>{
        const b=cell.getBoundingClientRect();return {text:cell.innerText.trim(),
          within_table:b.left>=box.left-1&&b.right<=box.right+1};}))};}""")
    overflow = before["scrollWidth"] > before["width"] + 1
    acknowledged = (not ack["timed_out"] and len(ack["wheel_events"]) == 1
                    and ack["wheel_events"][0]["trusted"]
                    and ack["wheel_events"][0]["delta_x"] == 10000 and ack["wheel_events"][0]["delta_y"] == 0)
    reached = (ack["right_reached"] and (not overflow
               or before["left"] >= before["scrollWidth"] - before["width"] - 1 or after["left"] > before["left"]))
    last_visible = bool(after["right_columns"]) and all(row and row[-1]["within_table"] for row in after["right_columns"])
    whole_page_fits = after["page"]["scrollWidth"] <= width + 1
    passed = acknowledged and reached and last_visible and whole_page_fits
    result = {"before": before, "ack": ack, "after": after, "overflow": overflow, "passed": passed}
    e.observe(label + "_native_horizontal", result)
    await e.snapshot(label + ("-right-columns" if passed else "-native-wheel-failed"))
    require(acknowledged, label + "：未收到单次可信原生滚轮事件")
    require(reached, label + "：真实横滚未抵达原表右端")
    require(last_visible, label + "：原表末列仍被裁切或没有真实来源行")
    require(whole_page_fits, label + "：横滚令整页溢出")
    e.business_unchanged(before_business, label + "_after_native_horizontal")
    if original_viewport:
        e.action("viewport", label + "恢复原场景宽度", **original_viewport)
        await e.page.set_viewport_size(original_viewport)
    return result
