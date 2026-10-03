"""Read the original presales handoff at five native browser widths.

This scenario uses an existing synthetic lead before the followup scenario
changes it. It never submits a transfer or assistant/business operation.
"""
from __future__ import annotations

import asyncio
import json

from playwright.async_api import expect

from sales_business import require


SCENARIO = "presales-handoff-responsive-cutie-14"
WIDTHS = (360, 390, 414, 768, 1440)


async def mobile_handoff(e, context, credentials):
    require(e.manifest.get("synthetic_data_only") is True, "交接布局只读复验必须使用本次合成实例")
    case_ids = e.manifest["lead_plan"]["case_ids"]
    require(case_ids, "本次原生接待前置不能为空")
    placeholders = ",".join("?" for _ in case_ids)
    rows = e.db.rows(
        "SELECT c.id AS case_id,c.number,c.title,c.state,c.store_id,t.id AS task_id,"
        "t.title AS task_title,t.due_date,t.assignee_id,t.role,t.status "
        "FROM flow_cases c JOIN flow_tasks t ON t.case_id=c.id "
        f"WHERE c.id IN ({placeholders}) AND c.kind='lead' AND c.state='unassigned' "
        "AND t.key='assign' AND t.status='open' ORDER BY c.id,t.id", tuple(case_ids))
    require(rows, "请在跟进改变原接待之前执行交接布局场景")
    row = rows[0]  # Existing fixture identity, never a guessed constant ID.
    user = await e.login(context, credentials, role="admin", route="case/" + str(row["case_id"]))
    await expect(e.page.locator("#store")).to_have_value(str(row["store_id"]))
    await expect(e.page.locator("#main h1")).to_have_text(row["title"])
    await expect(e.page.locator("#main > .loading")).to_have_count(0)
    require(user["role"] == "admin", "复用原管理员转交可见性，不模拟岗位")
    # The original login intentionally appends its own audit. Protect the
    # subsequent read/resize path after that legitimate login has committed.
    before = e.business_snapshot("cutie14_original_business_after_login_before_resize")
    network_start = len(e.network)
    panel = e.page.locator("#main .panel").filter(
        has=e.page.locator(".panelhead h2", has_text="分工与交接"))
    await expect(panel).to_have_count(1)
    handoff_selector = '[data-baws-action="handoff"][data-baws-ref="task:' + str(row["task_id"]) + '"]'
    task_ui = panel.locator(".taskitem").filter(has=e.page.locator(handoff_selector))
    await expect(task_ui).to_have_count(1)
    await expect(task_ui.locator(".description strong")).to_have_text(row["task_title"])
    await expect(task_ui.locator('[data-act="assign"]')).to_have_text("转交")
    await expect(task_ui.locator(handoff_selector)).to_have_text("交给助手")
    if row["due_date"]:
        await expect(task_ui.locator(".description p").first).to_contain_text(row["due_date"])

    report = {"issue": 14, "scenario": SCENARIO, "scope": "original_presales_handoff_readonly",
              "case_id": row["case_id"], "task_id": row["task_id"], "widths": [],
              "complete": False, "passed": False, "employee_acceptance": False,
              "real_device_touch_tested": False, "business_submission": False}
    report_path = e.directory / "mobile-handoff.json"

    def save():
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save()
    for width in WIDTHS:
        e.action("viewport", "Cutie #14 原生交接布局", width=width, height=900)
        await e.page.set_viewport_size({"width": width, "height": 900})
        e.action("scroll", "原交接卡进入真实视口")
        await panel.scroll_into_view_if_needed()
        await expect(task_ui.locator('[data-act="assign"]')).to_be_visible()
        await expect(task_ui.locator(handoff_selector)).to_be_visible()
        geometry = await task_ui.evaluate("""task => {
          const rect = x => {const r=x.getBoundingClientRect();return {
            x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}};
          const text = x => {const range=document.createRange();range.selectNodeContents(x);
            return Array.from(range.getClientRects()).map(r=>({x:r.x,y:r.y,right:r.right,bottom:r.bottom}))};
          const description=task.querySelector('.description');
          const meta=description.querySelector('p');
          const controls=Array.from(task.querySelectorAll(':scope>button,:scope>.pill')).map(x=>({
            label:x.textContent.trim(),rect:rect(x),text_rects:text(x),
            scroll_width:x.scrollWidth,client_width:x.clientWidth}));
          const font=getComputedStyle(meta);
          return {viewport:innerWidth,document_width:document.documentElement.scrollWidth,
            panel:rect(task.closest('.panel')),task:rect(task),description:rect(description),
            metadata:rect(meta),metadata_text:meta.textContent.trim(),
            metadata_lines:meta.getBoundingClientRect().height/parseFloat(font.lineHeight),
            controls};
        }""")
        viewport_path = e.directory / f"cutie14-{width}-viewport.png"
        card_path = e.directory / f"cutie14-{width}-handoff.png"
        await e.page.screenshot(path=str(viewport_path), full_page=False)
        await panel.screenshot(path=str(card_path))
        item = {"width": width, "geometry": geometry, "viewport_screenshot": str(viewport_path),
                "card_screenshot": str(card_path), "passed": False}
        report["widths"].append(item)
        save()
        e.observe("cutie14_" + str(width), item)
        require(geometry["viewport"] == width, "浏览器真实视口宽度未生效")
        require(geometry["document_width"] <= width + 1, f"{width}px交接原页横向溢出")
        require(geometry["description"]["width"] >= 160,
                f"{width}px交接说明列仍被压成窄列")
        require(geometry["metadata_lines"] <= 3.1,
                f"{width}px原姓名、岗位和日期仍过度折行")
        bounds = geometry["panel"]
        for control in geometry["controls"]:
            box = control["rect"]
            require(box["x"] >= bounds["x"] - 1 and box["right"] <= bounds["right"] + 1
                    and box["x"] >= -1 and box["right"] <= width + 1,
                    f"{width}px状态或操作超出卡片/视口：{control['label']}")
            require(control["scroll_width"] <= control["client_width"] + 1,
                    f"{width}px操作文字被按钮裁切：{control['label']}")
            for fragment in control["text_rects"]:
                require(fragment["x"] >= box["x"] - 1 and fragment["right"] <= box["right"] + 1,
                        f"{width}px状态或操作文字超出控件：{control['label']}")
        item["passed"] = True
        save()
    if e.response_jobs:
        await asyncio.gather(*list(e.response_jobs))
    writes = [item for item in e.network[network_start:] if item["event"] == "request"
              and item["method"] not in {"GET", "HEAD", "OPTIONS"}
              and item["path"] != "/api/auth/login"]
    require(not writes, "只读交接布局复验发送了非登录写请求")
    e.business_unchanged(before, "cutie14_original_business_after_five_widths")
    report.update(complete=True, passed=True, business_unchanged=True,
                  native_login=True, business_or_assistant_write_requests=0)
    save()
    e.observe("cutie14_complete", {"report": str(report_path), "widths": list(WIDTHS),
                                  "business_unchanged": True})


MOBILE_HANDOFF_SCENARIOS = ((SCENARIO, mobile_handoff, 90),)
