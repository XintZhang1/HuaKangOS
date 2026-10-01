"""Two original-UI system checks, using only this run's finite parent facts.

Synthetic personal passwords stay in the parent's private runtime file. Original
business writes use native forms; SELECT snapshots protect unrelated old rows.
No app import, direct positive HTTP submission, audit export, or unknown replay.
"""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from playwright.async_api import expect

from sales_business import login_as, require
from sales_order_business import checkpoint_evidence, fixed_dependency
from system_management_business import (
    field, fresh_identity, native_login, one, open_page, original_submit, parameter_partial,
    password_edges, personal_password, revoked_page, save_private, sessions,
    switch_store,
)
from vehicle_purchase_business import checkbox, select_value

SCENARIO = "system-followon-hk192-193"
SYSTEM = "system-management-hk189-191"
PURCHASE = "vehicle-purchase-hk171-177-178-026-021-018-029"
CONTRACTS = {
    "HK-192": ("参数设置密码修改", ["当前岗位安全参数投影与原配置按钮导航", "本人原密码拒绝、合法修改、全部旧会话失效与重新登录", "管理员原登录图片上传、实际公开JPEG与恢复默认"]),
    "HK-193": ("系统日志", ["本轮非空原日志的类型、原编号筛选及真实分页", "原详情与actor/action/entity/id/before/after/reason/time一致", "admin/manager/auditor当前店范围与管理类别排除", "临时一店auditor授权经原UI恢复，CAS/收据/会话及全部旧业务保护"]),
}
KEYS = {"users": ("id",), "user_stores": ("user_id", "store_id"),
        "audit_logs": ("id",), "user_access_receipts": ("id",), "app_metadata": ("key",)}
EXCLUDED = ("users", "stores", "feedback", "maintenance")
DEPLOYMENT_LABELS = {
    "timezone": "业务时区", "session_hours": "登录有效时长（小时）",
    "inventory_aging_days": "库存库龄提醒（天）", "repair_overdue_days": "维修超期提醒（天）",
    "receivable_grace_days": "应收宽限（天）", "low_margin_percent": "低毛利提醒（%）",
    "large_cash_yuan": "大额收支提醒（元）", "discount_review_percent": "折扣复核提醒（%）",
    "daily_report_hour": "每日日报时刻（小时）", "daily_report_minute": "每日日报时刻（分钟）",
}
AUDIT_ENTITY_LABELS = {"vehicles": "整车库存", "sales": "原有销售单", "repairs": "原有维修单", "policies": "原有保险单", "cash": "财务流水",
    "flow": "业务流程", "typed_master": "业务资料", "dictionary": "分类设置", "vehicle_catalog": "车型目录", "customer_vehicle": "客户车辆",
    "care_rule": "客户提醒规则", "care_grant": "客户资料授权", "users": "员工账号", "stores": "门店", "findings": "数据复核", "feedback": "反馈", "maintenance": "系统维护"}
AUDIT_ACTION_LABELS = {"create": "建立记录", "update": "修改记录", "submit": "提交审核", "approve": "审核通过", "reject": "退回", "void": "作废", "advance": "确认进度",
    "login": "登录", "download": "下载文件", "export": "导出", "create_user": "新增员工", "update_user": "修改员工", "create_store": "新增门店", "update_store": "修改门店",
    "change_password": "修改密码", "reset_password": "重置密码", "review": "复核记录", "flow_create": "建立流程业务", "flow_action": "办理业务", "document": "生成文件", "upload": "上传凭据"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(table, row):
    return tuple(row[k] for k in KEYS[table])


def protected_rows(e, table):
    rows = e.db.rows("SELECT * FROM " + table + " ORDER BY " + ",".join(KEYS[table]))
    if table == "app_metadata":
        # The common business digest excludes this exact worker-owned prefix.
        rows = [r for r in rows if not r["key"].startswith("assistant_runtime_worker:")]
    return rows


class Guard:
    """Only the explicit new employee or login-photo key may change old rows."""
    def __init__(self, e, label, *, employee=None, photo=False):
        require((employee is not None) != photo, "系统守卫只能选择一个有限写入对象")
        self.e, self.label, self.employee, self.photo = e, label, employee, photo
        self.allowed = {"audit_logs", "app_metadata"} if photo else {"audit_logs", "users", "user_stores", "user_access_receipts"}
        self.before = e.business_snapshot("before_" + label)
        self.old = {table: protected_rows(e, table) for table in self.allowed}
        self.old_sessions = e.db.rows("SELECT * FROM login_sessions ORDER BY id")

    def added(self, table):
        old = {identity(table, r) for r in self.old[table]}
        return [r for r in protected_rows(self.e, table) if identity(table, r) not in old]

    def finish(self):
        after = self.e.business_snapshot("after_" + self.label)
        other = [t for t in self.before["tables"].keys() | after["tables"].keys()
                 if t not in self.allowed and self.before["tables"].get(t) != after["tables"].get(t)]
        require(not other, "系统动作改变无关业务表：" + "、".join(sorted(other)))
        for table, rows in self.old.items():
            current = {identity(table, r): r for r in protected_rows(self.e, table)}
            old_keys = {identity(table, r) for r in rows}
            for row in rows:
                key = identity(table, row)
                mutable = (table == "app_metadata" and row["key"] == "public_login_photo") or (table == "user_stores" and row["user_id"] == self.employee)
                if mutable:
                    continue
                require(key in current, "系统动作删除旧行：" + table)
                if table == "users" and row["id"] == self.employee:
                    require({k: v for k, v in row.items() if k != "access_version"} == {k: v for k, v in current[key].items() if k != "access_version"}, "审计临时授权改变员工其它资料或密码")
                else:
                    require(current[key] == row, "系统动作覆盖无关旧行：" + table)
            if table == "users":
                require(set(current) == old_keys, "审计授权新增或删除账号")
            elif table == "user_stores":
                require(all(r["user_id"] == self.employee for r in self.added(table)), "审计授权新增其它员工关系")
            elif table == "app_metadata":
                require(all(r["key"] == "public_login_photo" for r in self.added(table)), "登录图片改动其它metadata键")
        now = self.e.db.rows("SELECT * FROM login_sessions ORDER BY id")
        require([r for r in self.old_sessions if r["user_id"] != self.employee] == [r for r in now if r["user_id"] != self.employee], "原系统动作改变其它员工会话")
        require(len(self.added("audit_logs")) == 1, "一次系统原操作必须只追加一条指定审计")
        if not self.photo:
            require(len(self.added("user_access_receipts")) == 1, "一次原授权必须只追加一条收据")
        return {"explicit_employee_id": self.employee, "photo_key_only": self.photo,
                "all_unrelated_old_rows_and_other_stores_protected": True, "cash_stock_membership_files_unchanged": True,
                "audit_ids": [r["id"] for r in self.added("audit_logs")]}


class Checkpoint:
    def __init__(self, e):
        self.e, self.active = e, None
        raw = Path(__file__).with_name("business_acceptance_catalog.json").read_bytes()
        self.digest = sha(raw)
        catalog = {r["id"]: r for r in json.loads(raw)["requirements"]}
        for key, (title, _) in CONTRACTS.items():
            row = catalog[key]
            require(row["title"] == title and row["source_review_status"] == "source_reviewed" and any(c["check_id"] == key + "-business" for c in row["acceptance_checks"]), key + " 原目录合同未核准")
        self.path = e.directory / "business-checkpoint.json"
        self.report = {"schema": 1, "scenario": SCENARIO, "scope": list(CONTRACTS), "complete": False, "passed": False,
            "execution": "native_browser_original_forms", "source_contract_sha256": self.digest,
            "candidate_sha256": sha(Path(__file__).read_bytes()), "full_193_business_acceptance": False,
            "full_registered_suite_complete": False, "human_acceptance": "pending",
            "provenance": {k: e.manifest[k] for k in ("origin", "source_root", "runtime_root", "evidence_root", "database_path")},
            "conditions": {"synthetic_data_only": True, "audit_export_supported": False, "audit_export_executed": False,
                           "avatar_business_executed": False, "company_brand_approval": False, "private_attachment_or_clamav_acceptance": False},
            "requirements": [{"id": key, "title": title, "status": "not_tested", "business_accepted": False,
                "human_criteria": {"simple_flow": "pending", "concise_copy": "pending"},
                "acceptance_checks": [{"id": key + "-business", "check_id": key + "-business", "status": "not_tested", "criteria": criteria, "evidence": {}}]} for key, (title, criteria) in CONTRACTS.items()]}
        self.save()

    def save(self):
        raw = json.dumps(self.report, ensure_ascii=False, indent=2) + "\n"
        self.path.write_text(raw, encoding="utf-8")

    def start(self, key):
        self.active = next(r for r in self.report["requirements"] if r["id"] == key)
        self.active.update(status="running", evidence_action_start=len(self.e.actions))
        self.active["acceptance_checks"][0]["status"] = "running"
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
        for r in self.report["requirements"]:
            if r["status"] == "running":
                r["status"] = r["acceptance_checks"][0]["status"] = "failed" if r is self.active else "partial"
        self.report.update(error=self.e.scrub(error), failed_requirement=self.active["id"] if self.active else "source_or_final_guard")
        self.save()

    def finish(self, sources):
        require(all(r["status"] == "passed" for r in self.report["requirements"]), "参数与日志两项未完整执行")
        require(self.report.get("temporary_auditor_restored") is True, "临时一店审计授权未恢复，不能完成后继")
        self.report.update(complete=True, passed=True, executed_requirements=2, passed_requirements=2, report_sources=sources)
        self.save()
        self.e.observe("system_followon_checkpoint", {"path": str(self.path), "passed_checks": 2, "business_accepted": False, "audit_export_supported": False})


def dependencies(e, cp):
    root, runtime = Path(e.manifest["evidence_root"]).resolve(), Path(e.manifest["runtime_root"]).resolve()
    require(e.manifest.get("synthetic_data_only") is True and Path(e.manifest["database_path"]).resolve().is_relative_to(runtime), "系统后继只允许本次外部合成库")
    provenance_raw = (root / "provenance.json").read_bytes()
    provenance = json.loads(provenance_raw)
    require(provenance["snapshot_stable"] is True, "系统后继来源镜像未冻结")
    for name in ("system_followon_business.py", "system_management_business.py", "vehicle_purchase_business.py", "sales_business.py", "sales_order_business.py", "business_acceptance_catalog.json"):
        require(provenance["script_files"].get(name) == sha(Path(__file__).with_name(name).read_bytes()), "系统后继脚本不是同轮指纹：" + name)
    cp.report["mirror"] = {"source_sha256": provenance["source_sha256"], "script_sha256": provenance["script_sha256"], "provenance_sha256": sha(provenance_raw)}
    original = fixed_dependency(e, cp, SYSTEM)
    purchase = fixed_dependency(e, cp, PURCHASE)
    staff = checkpoint_evidence(original, "HK-191")["staff_actions"]
    require(len(staff) >= 2 and staff[0]["default_sales"] is True and staff[1]["default_sales"] is True, "父系统没有两名真实UI新增员工")
    receiver, manager = one(e, "users", staff[0]["user_id"]), one(e, "users", staff[1]["user_id"])
    require(receiver["id"] != manager["id"] and receiver["role"] == manager["role"] == "sales" and receiver["active"] == manager["active"] == 1 and receiver["must_change_password"] == manager["must_change_password"] == 0, "前序两名新员工当前状态不可用")
    observed = json.loads((root / SYSTEM / "observations.json").read_text(encoding="utf-8"))
    pointers = [r["value"] for r in observed if r["label"] == "synthetic_system_private_credentials"]
    require(len(pointers) == 1 and pointers[0]["credentials_in_evidence"] is False, "系统随机账号缺唯一私有来源")
    secret_path = Path(pointers[0]["path"]).resolve()
    require(secret_path.parent == runtime and secret_path.name.startswith("system-management-accounts-") and secret_path.is_file(), "系统密码来源不在本次runtime")
    private = json.loads(secret_path.read_text(encoding="utf-8"))
    require(private["synthetic_data_only"] is True, "系统账号来源不是合成实例")
    for key, account in (("receiver", receiver), ("manager", manager)):
        secret = private["accounts"][key]
        require(secret["id"] == account["id"] and secret["username"] == account["username"], "私有账号来源串员工")
        require(secret.get("current_password_stage") in secret, "私有账号缺当前已观察密码阶段")
        e.secrets.extend(value for name, value in secret.items() if isinstance(value, str) and name not in {"username", "current_password_stage"})
    first, second = e.manifest["stores"][0]["id"], e.manifest["stores"][1]["id"]
    original_roles = {r["store_id"]: r["role"] for r in e.db.rows("SELECT * FROM user_stores WHERE user_id=? ORDER BY store_id", (receiver["id"],))}
    require(original_roles == {int(k): v for k, v in staff[0]["store_roles"].items()}, "甲当前原两店授权不同于明确UI创建事实")
    third = set(original_roles) - {second}
    require(len(third) == 1 and first not in original_roles and original_roles[second] == "service" and original_roles[next(iter(third))] == "auditor", "甲当前授权不符合系统父有限事实或HK190前置")
    require(e.db.rows("SELECT store_id,role FROM user_stores WHERE user_id=? ORDER BY store_id", (manager["id"],)) == [{"store_id": first, "role": "manager"}], "乙主管当前授权非本店")
    source_supplier = checkpoint_evidence(purchase, "HK-171")["supplier"]
    supplier = one(e, "master_suppliers", source_supplier["id"])
    require(supplier == source_supplier and supplier["store_id"] == first and supplier["active"] == 1, "本次有限供应商已变化或串店")
    source_audits = e.db.rows("SELECT * FROM audit_logs WHERE entity_type='typed_master' AND entity_id=? AND store_id=? AND reason='供应商' AND action IN ('master_create','master_update') ORDER BY id", (supplier["id"], first))
    require(len(source_audits) == 2 and [r["action"] for r in source_audits] == ["master_create", "master_update"] and source_audits[0]["actor_id"] == source_audits[1]["actor_id"] == e.manifest["users"][e.manifest["business_fixtures"]["vehicle_purchase"]["manager_key"]]["id"], "本轮供应商没有精确新增/编辑原审计")
    require(json.loads(source_audits[1]["after_data"])["contact_name"] == supplier["contact_name"] and json.loads(source_audits[1]["after_data"])["phone"] == supplier["phone"], "供应商编辑审计不对应当前事实")
    store_actions = checkpoint_evidence(original, "HK-189")["store_actions"]
    require(next(iter(third)) == store_actions[0]["store_id"], "甲审计岗位不是本轮实际UI新机构")
    edited_store = store_actions[1]
    store_audit = one(e, "audit_logs", edited_store["audit_id"])
    require(store_audit["entity_type"] == "stores" and store_audit["action"] == "update_store" and store_audit["store_id"] == 0, "本次系统原门店审计不是global0")
    cp.report["source_preconditions"] = {"receiver_id": receiver["id"], "manager_id": manager["id"], "receiver_original_store_roles": original_roles,
        "supplier_id": supplier["id"], "supplier_audit_ids": [r["id"] for r in source_audits], "store_audit_id": store_audit["id"], "private_passwords_in_report": False}
    cp.save()
    return {"receiver": receiver, "manager": manager, "first": first, "second": second, "third": next(iter(third)), "original_roles": original_roles,
            "private_path": secret_path, "private": private, "supplier": supplier, "supplier_audits": source_audits, "store_audit": store_audit}


def current_password(src, key):
    secret = src["private"]["accounts"][key]
    return secret[secret["current_password_stage"]]


async def new_staff_page(e, context, contexts, src, key, store_id, role):
    _, page = await fresh_identity(e, context, contexts)
    result = await native_login(e, one(e, "users", src[key]["id"]), current_password(src, key))
    if result["active_store_id"] != store_id:
        result = await switch_store(e, store_id, one(e, "users", src[key]["id"]), role)
    require(result["current_role"] == role and result["active_store_id"] == store_id, "本人原登录未投影预期当前店岗位")
    await open_page(e, "parameters", "参数与个人密码", "/api/parameters/catalog")
    return page, result


async def configuration(e, account, role, *, target=None):
    base = await parameter_partial(e, account, role=role)
    body = await open_page(e, "parameters", "参数与个人密码", "/api/parameters/catalog")
    entries = body["entries"]
    require(len({r["route"] for r in entries}) == len(entries), "参数原入口重复")
    await expect(e.page.locator('#main .chartgrid [data-act="open"][data-route]')).to_have_count(len(entries))
    for item in entries:
        await expect(e.page.locator('#main .chartgrid [data-act="open"][data-route="' + item["route"] + '"]')).to_be_visible()
        require(isinstance(item["can_write"], bool) and not item["route"].startswith(("http", "/")), "参数返回了任意外部或非原路由")
        if item["route"] in {"membership-rules", "recharge-bundle-rules"}:
            require(item["can_write"] is (role == "admin"), "参数规则写权限与原admin-only合同不符")
    if role in {"admin", "manager"}:
        deployment = body["deployment"]
        require(isinstance(deployment, dict) and set(deployment) == set(DEPLOYMENT_LABELS), "安全部署投影不符合原白名单")
        await e.click('details.mux-setting-detail > summary', "展开只读部署参数")
        for key, label in DEPLOYMENT_LABELS.items():
            fact = e.page.locator("details.mux-setting-detail .fact").filter(has=e.page.locator(".key").filter(has_text=label))
            await expect(fact).to_have_count(1)
            value = deployment[key]
            displayed = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
            await expect(fact.locator(".value")).to_have_text(displayed)
    else:
        require(body["deployment"] is None, "非部署管理岗位取得技术参数")
        await expect(e.page.locator("details.mux-setting-detail")).to_have_count(0)
    route_proof = None
    if target:
        route, title, path = target
        require(any(item["route"] == route for item in entries), "本店目录没有所选原参数入口")
        before = e.business_snapshot("before_native_parameter_entry")
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == path) as pending:
            await e.click('#main .chartgrid [data-act="open"][data-route="' + route + '"]', "从参数卡打开原配置页面")
        response = await pending.value
        require(response.status == 200 and response.request.headers.get("x-store-id") == await e.page.locator("#store").input_value(), "原参数导航读取失败或串店")
        data = await response.json()
        await expect(e.page.locator("#main h1")).to_have_text(title)
        await expect(e.page.locator("#main .notice.error,.errorpage")).to_have_count(0)
        e.business_unchanged(before, "after_native_parameter_entry")
        route_proof = {"route": route, "path": path, "status": 200, "native_button_clicked": True, "response_items": len(data.get("items", data.get("resources", []))), "rules_written": False}
        await open_page(e, "parameters", "参数与个人密码", "/api/parameters/catalog")
    return {**base, "original_entry_count": len(entries), "entry_routes": [r["route"] for r in entries], "native_configuration_entry": route_proof,
            "deployment_values_verified": role in {"admin", "manager"}, "arbitrary_configuration_write": False}


async def password_check(e, context, contexts, src, receiver_page):
    sibling, _ = await new_staff_page(e, context, contexts, src, "receiver", src["second"], "service")
    e.page = receiver_page
    secret = src["private"]["accounts"]["receiver"]
    new = secrets.token_urlsafe(24)
    e.secrets.append(new)
    secret["system_followon"] = new
    save_private(src["private_path"], src["private"])
    edges = await password_edges(e, current_password(src, "receiver"), secret["wrong_old"], new, secret["short_new"], src["second"])
    require(sessions(e, src["receiver"]["id"]) >= 2, "本人改密没有两个实际旧会话")
    changed = await personal_password(e, one(e, "users", src["receiver"]["id"]), current_password(src, "receiver"), new, src["second"], opened=True)
    first_revoked = await revoked_page(e, receiver_page, src["receiver"]["id"])
    second_revoked = await revoked_page(e, sibling, src["receiver"]["id"])
    secret["current_password_stage"] = "system_followon"
    save_private(src["private_path"], src["private"])
    e.page = receiver_page
    login = await native_login(e, one(e, "users", src["receiver"]["id"]), current_password(src, "receiver"))
    require(login["current_role"] == "service" and login["active_store_id"] == src["second"], "本人新密码登录后逐店岗位不符")
    return {"edges": edges, "original_password_change": changed, "old_pages_revoked": [first_revoked, second_revoked], "new_password_native_login": login, "existing_users_passwords_changed": False}


async def jpeg_fact(e, response):
    from PIL import Image
    require(response.status == 200 and response.headers.get("content-type", "").startswith("image/jpeg"), "原登录图片不是实际公开JPEG")
    raw = await response.body()
    with Image.open(io.BytesIO(raw)) as image:
        require(image.format == "JPEG" and image.width >= 320 and image.height >= 320, "原公开登录图片未解码为合格JPEG")
        size = list(image.size)
        require(not image.getexif(), "原公开登录图片未清除EXIF")
    image = e.page.locator('img.brand-photo-preview[alt="当前登录图片"]')
    await expect(image).to_be_visible()
    await e.page.wait_for_function("() => {const x=document.querySelector('img.brand-photo-preview');return x && x.complete && x.naturalWidth>0 && x.naturalHeight>0;}")
    return {"path": "/api/branding/photo", "native_image_request": True, "status": 200, "content_type": "image/jpeg", "length": len(raw), "sha256": sha(raw), "decoded_size": size, "visible_loaded": True}


def photo_audit(e, guard, admin, action, store_id, *, digest=None):
    rows = guard.added("audit_logs")
    require(len(rows) == 1, "登录图片未产生唯一原维护审计")
    row = rows[0]
    require(row["actor_id"] == admin["id"] and row["action"] == action and row["entity_type"] == "maintenance" and row["entity_id"] is None and row["store_id"] == store_id, "登录图片维护审计身份或门店错误")
    before = json.loads(row["before_data"]) if row["before_data"] is not None else None
    require(before is None and (json.loads(row["after_data"]) if row["after_data"] else None) == ({"sha256": digest} if digest else None), "登录图片前后审计与实际JPEG不一致")
    require(row["reason"] == ("更换登录图片" if digest else "恢复默认登录图片"), "登录图片维护审计文案不符")
    return {"id": row["id"], "actor_id": row["actor_id"], "action": action, "store_id": store_id, "entity_type": "maintenance"}


async def branding(e, admin, store_id):
    from PIL import Image
    require(not e.db.rows("SELECT key FROM app_metadata WHERE key='public_login_photo'"), "本批不得覆盖已有登录图片成果")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/branding/photo") as initial_image:
        await open_page(e, "parameters", "参数与个人密码", "/api/parameters/catalog")
    default = await jpeg_fact(e, await initial_image.value)
    image = Image.new("RGB", (360, 360), (24, 90, 100))
    image.paste((235, 190, 65), (40, 40, 320, 180))
    output = io.BytesIO()
    image.save(output, format="PNG")
    raw = output.getvalue()
    path = Path(e.manifest["runtime_root"]).resolve() / "system-followon-synthetic-login-photo.png"
    with path.open("xb") as file:
        file.write(raw)
    await e.click('#main [data-act="brand-photo"]', "管理员选择本批合成登录图片")
    await expect(e.page.locator("#modal-title")).to_have_text("更换登录图片")
    e.action("file", "选择仓库外无客户资料的合成PNG", length=len(raw), sha256=sha(raw))
    await e.page.locator('#modal input[name="file"]').set_input_files(str(path))
    guard = Guard(e, "native_login_photo_replace", photo=True)
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/branding/photo") as native_image:
        async with e.page.expect_response(lambda r: r.request.method == "POST" and urlsplit(r.url).path == "/api/branding/photo") as submitted:
            await e.click('#modal form button[type="submit"]', "保存管理员核对的原登录图片")
        response = await submitted.value
        body = await response.json()
        require(response.status == 200 and body.get("ok") is True, "原登录图片提交失败")
        headers = await response.request.all_headers()
        require(headers.get("x-store-id") == str(store_id) and headers.get("cookie") and headers.get("x-csrf-token") and headers.get("content-type", "").startswith("multipart/form-data;"), "原图片上传未使用真实Cookie/CSRF/当前门店multipart")
    displayed = await jpeg_fact(e, await native_image.value)
    rows = e.db.rows("SELECT * FROM app_metadata WHERE key='public_login_photo'")
    require(len(rows) == 1, "原登录图片没有唯一metadata来源")
    value = json.loads(rows[0]["value"])
    require(set(value) == {"image", "sha256"} and value["sha256"] == displayed["sha256"] == body["sha256"] and sha(base64.b64decode(value["image"], validate=True)) == body["sha256"], "原图片响应/公开字节/metadata哈希不符")
    replacement_audit = photo_audit(e, guard, admin, "replace_photo", store_id, digest=body["sha256"])
    replacement_guard = guard.finish()
    await expect(e.page.locator("#modal")).not_to_be_visible()
    await e.snapshot("hk192-native-login-photo")
    reset_guard = Guard(e, "native_login_photo_reset", photo=True)
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/branding/photo") as restored_image:
        async with e.page.expect_response(lambda r: r.request.method == "DELETE" and urlsplit(r.url).path == "/api/branding/photo") as deleted:
            await e.click('#main [data-act="brand-photo-reset"]', "管理员恢复原默认登录图片")
        reset = await deleted.value
        reset_body = await reset.json()
        reset_headers = await reset.request.all_headers()
        require(reset.status == 200 and reset_body == {"ok": True} and reset_headers.get("cookie") and reset_headers.get("x-csrf-token") and reset_headers.get("x-store-id") == str(store_id), "原登录图片恢复失败")
    restored = await jpeg_fact(e, await restored_image.value)
    require(not e.db.rows("SELECT key FROM app_metadata WHERE key='public_login_photo'") and restored["sha256"] == default["sha256"], "恢复后不是原默认图片或metadata未撤除")
    reset_audit = photo_audit(e, reset_guard, admin, "reset_photo", store_id)
    reset_safety = reset_guard.finish()
    return {"synthetic_input": {"length": len(raw), "sha256": sha(raw), "format": "PNG", "size": [360, 360]}, "default": default, "uploaded_public_jpeg": displayed,
            "replace_audit": replacement_audit, "replace_guard": replacement_guard, "restored_public_jpeg": restored, "reset_audit": reset_audit, "reset_guard": reset_safety,
            "avatar_business": False, "private_attachment_scan": False}


async def memberships(e, admin, employee_id, roles, store_id, *, restoring, require_old_session=True):
    target = one(e, "users", employee_id)
    old_session_count = sessions(e, employee_id)
    require(target["role"] == "sales" and target["active"] == 1 and (old_session_count > 0 or not require_old_session), "原授权变更缺明确新员工及待撤销会话")
    previous = e.db.rows("SELECT * FROM user_stores WHERE user_id=? ORDER BY store_id", (employee_id,))
    require({r["store_id"]: r["role"] for r in previous} != roles, "原授权变更没有实际差异")
    await open_page(e, "users", "员工账号", "/api/users")
    await e.click(f'#main [data-act="edituser"][data-id="{employee_id}"]', "恢复原两店授权" if restoring else "明确追加本店审计岗位")
    await expect(e.page.locator("#modal-title")).to_have_text("编辑员工")
    await field(e, "display_name", target["display_name"])
    await select_value(e, '#modal [name="role"]', "sales", "保留新员工账号默认销售岗位")
    await checkbox(e, '#modal [name="active"]', True, "保留新员工启用状态")
    await checkbox(e, '#modal [name="can_group_summary"]', bool(target["can_group_summary"]), "保留原集团汇总授权")
    boxes = e.page.locator('#modal [name="store_ids"]')
    available = [int(await boxes.nth(index).get_attribute("value")) for index in range(await boxes.count())]
    require(set(roles) <= set(available), "原表单没有本次明确门店候选")
    for key in available:
        await checkbox(e, f'#modal [name="store_ids"][value="{key}"]', key in roles, "逐店明确原授权范围")
        if key in roles:
            await select_value(e, f'#modal [name="store_role_{key}"]', roles[key], "明确本店岗位")
    guard = Guard(e, "restore_auditor_memberships" if restoring else "add_explicit_auditor_membership", employee=employee_id)
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/users") as refreshed:
        body, request, native = await original_submit(e, f"/api/users/{employee_id}", 200, method="PUT", store_id=store_id, version=target["access_version"])
    refresh = await refreshed.value
    require(refresh.status == 200, "原授权提交后员工列表未重新读取")
    await refresh.body()
    require(request["access_version"] == target["access_version"] and request["role"] == "sales" and request["active"] is True
            and request["display_name"] == target["display_name"] and request["can_group_summary"] is bool(target["can_group_summary"])
            and set(request["store_ids"]) == set(roles) and {r["store_id"]: r["role"] for r in request["store_roles"]} == roles,
            "原授权请求不符合明确CAS/岗位/门店")
    current = one(e, "users", employee_id)
    actual = e.db.rows("SELECT * FROM user_stores WHERE user_id=? ORDER BY store_id", (employee_id,))
    require(current["access_version"] == target["access_version"] + 1 and {r["store_id"]: r["role"] for r in actual} == roles
            and sessions(e, employee_id) == 0, "原授权未精确变化一版/恢复门店/撤销全部本人会话")
    receipts, audits = guard.added("user_access_receipts"), guard.added("audit_logs")
    require(len(receipts) == len(audits) == 1, "一次授权不是唯一原收据及审计")
    receipt, audit = receipts[0], audits[0]
    values = {k: v for k, v in request.items() if k != "request_id"}
    digest = sha(json.dumps({"target_id": employee_id, "values": values}, sort_keys=True, ensure_ascii=False).encode())
    require(receipt["actor_id"] == admin["id"] and receipt["target_id"] == employee_id and receipt["request_key"] == request["request_id"]
            and receipt["previous_version"] == target["access_version"] and receipt["digest"] == digest and json.loads(receipt["request_data"]) == values
            and json.loads(receipt["result"]) == body and receipt["audit_id"] == audit["id"], "原授权收据CAS/原因/范围/digest不符")
    require(audit["actor_id"] == admin["id"] and audit["action"] == "update_user" and audit["entity_type"] == "users"
            and audit["entity_id"] == employee_id and audit["store_id"] == 0
            and audit["reason"] == "核对账号授权版本后修改；原登录会话全部失效", "原授权审计身份/原因/全局归属不符")
    require(json.loads(audit["before_data"])["access_version"] == target["access_version"]
            and json.loads(audit["after_data"])["access_version"] == current["access_version"], "原审计未保留授权前后版本")
    await expect(e.page.locator(f'#main tr:has([data-act="edituser"][data-id="{employee_id}"])')).to_contain_text(target["display_name"])
    safety = guard.finish()
    return {**native, **safety, "user_id": employee_id, "previous_access_version": target["access_version"], "access_version": current["access_version"],
            "store_roles": roles, "receipt_id": receipt["id"], "audit_id": audit["id"], "restoring_original_roles": restoring,
            "old_session_count": old_session_count, "all_old_sessions_revoked": True}


def audit_projection(e, store_id, role, *, entity_type="", entity_id=None, page=1):
    where, values = ("store_id IN (?,0)", [store_id]) if role == "admin" else ("store_id=? AND entity_type NOT IN ('users','stores','feedback','maintenance')", [store_id])
    if entity_type:
        where += " AND entity_type=?"
        values.append(entity_type)
    if entity_id is not None:
        where += " AND entity_id=?"
        values.append(entity_id)
    total = e.db.rows("SELECT COUNT(*) AS n FROM audit_logs WHERE " + where, tuple(values))[0]["n"]
    rows = e.db.rows("SELECT * FROM audit_logs WHERE " + where + " ORDER BY id DESC LIMIT 30 OFFSET ?", (*values, (page - 1) * 30))
    return total, rows


def no_secrets(e, value):
    forbidden = {"password", "password_hash", "current_password", "new_password", "csrf_hash", "dealer_session", "raw_reasoning", "reasoning_content"}
    if isinstance(value, dict):
        require(not forbidden.intersection(value), "原审计响应泄露凭据或推理字段")
        for nested in value.values():
            no_secrets(e, nested)
    elif isinstance(value, list):
        for nested in value:
            no_secrets(e, nested)
    elif isinstance(value, str):
        require(not any(secret and secret in value for secret in e.secrets), "原审计响应包含本批密码")


def local_time(value):
    instant = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
    local = instant.astimezone(ZoneInfo("Asia/Shanghai"))
    return f"{local.year}/{local.month}/{local.day} {local.hour:02d}:{local.minute:02d}:{local.second:02d}", instant


async def audit_view(e, response, account, store_id, role, *, entity_type="", entity_id=None, page=1):
    require(response.request.method == "GET" and urlsplit(response.url).path == "/api/audit" and response.status == 200, "原UI日志读取失败")
    query = parse_qs(urlsplit(response.url).query)
    expected = {"page": [str(page)]}
    if entity_type:
        expected["entity_type"] = [entity_type]
    if entity_id is not None:
        expected["entity_id"] = [str(entity_id)]
    require(query == expected and response.request.headers.get("x-store-id") == str(store_id), "日志原请求筛选/页码/门店不匹配")
    headers = await response.request.all_headers()
    require(bool(headers.get("cookie")), "原审计读取没有原生同源Cookie")
    body = await response.json()
    total, rows = audit_projection(e, store_id, role, entity_type=entity_type, entity_id=entity_id, page=page)
    require(body["page"] == page and body["total"] == total and [r["id"] for r in body["items"]] == [r["id"] for r in rows], "原审计分页/范围/顺序与只读DB不符")
    no_secrets(e, body)
    await expect(e.page.locator("#main h1")).to_have_text("操作记录")
    await expect(e.page.locator('#audit-filters [name="entity_type"]')).to_have_value(entity_type)
    await expect(e.page.locator('#audit-filters [name="entity_id"]')).to_have_value(str(entity_id) if entity_id is not None else "")
    await expect(e.page.locator('#main [data-act="auditdetail"]')).to_have_count(len(rows))
    await expect(e.page.locator("#main .pagination > span")).to_have_text(f"共 {total:,} 条 · 第 {page} 页")
    for item, row in zip(body["items"], rows):
        for key in ("id", "actor_id", "action", "entity_type", "entity_id", "reason", "store_id"):
            require(item[key] == row[key], "原审计字段与DB不符：" + key)
        for key in ("before_data", "after_data"):
            require(item[key] == (json.loads(row[key]) if row[key] is not None else None), "原审计前后快照与DB不符")
        actor = one(e, "users", row["actor_id"]) if row["actor_id"] is not None else None
        require(item["actor_name"] == (actor["display_name"] if actor else "系统"), "原审计操作人标签不符")
        displayed, instant = local_time(row["occurred_at"])
        require(datetime.fromisoformat(item["occurred_at"].replace("Z", "+00:00")) == instant, "原审计UTC时间不符")
        tr = e.page.locator(f'#main tr:has([data-act="auditdetail"][data-id="{row["id"]}"])')
        await expect(tr).to_have_count(1)
        await expect(tr.locator("td").nth(0)).to_have_text(displayed)
        await expect(tr.locator("td").nth(1)).to_have_text(item["actor_name"])
        await expect(tr.locator("td").nth(2)).to_have_text(AUDIT_ACTION_LABELS.get(row["action"]) or row["reason"] or "业务操作")
        await expect(tr.locator("td").nth(3)).to_have_text(AUDIT_ENTITY_LABELS.get(row["entity_type"], "资料管理"))
        await expect(tr.locator("td").nth(4)).to_have_text(str(row["entity_id"]) if row["entity_id"] is not None else "—")
        await expect(tr.locator("td").nth(5)).to_have_text(row["reason"] or "—")
        require(row["store_id"] in ({store_id, 0} if role == "admin" else {store_id}), "原审计混入其它店")
        if role != "admin":
            require(row["entity_type"] not in EXCLUDED, "非admin取得管理类别审计")
    proof = {"native_ui": True, "path": "/api/audit", "role": role, "actor_id": account["id"], "current_store_id": store_id,
             "page": page, "entity_type": entity_type, "entity_id": entity_id, "total": total, "item_ids": [r["id"] for r in rows],
             "api_database_all_fields_match": True, "visible_times_actor_ids_match": True, "export_supported": False, "export_executed": False}
    e.observe("native_scoped_audit_page", proof)
    return body, proof


async def audit_open(e, account, store_id, role):
    before = e.business_snapshot("before_original_audit_open")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/audit") as pending:
        await open_page(e, "audit", "操作记录", "/api/audit")
    body, proof = await audit_view(e, await pending.value, account, store_id, role)
    e.business_unchanged(before, "after_original_audit_open")
    return body, proof


async def audit_filter(e, account, store_id, role, entity_type, entity_id=None):
    before = e.business_snapshot("before_original_audit_filter")
    await select_value(e, '#audit-filters [name="entity_type"]', entity_type, "明确选择原审计业务类型")
    await e.fill('#audit-filters [name="entity_id"]', str(entity_id) if entity_id is not None else "", "输入明确原记录编号或清空")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/audit") as pending:
        await e.click('#audit-filters button[type="submit"]', "按原类型及编号查询日志")
    body, proof = await audit_view(e, await pending.value, account, store_id, role, entity_type=entity_type, entity_id=entity_id)
    e.business_unchanged(before, "after_original_audit_filter")
    return body, proof


async def audit_reset(e, account, store_id, role):
    before = e.business_snapshot("before_original_audit_reset")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/audit") as pending:
        await e.click('#audit-filters [data-act="audit-reset"]', "清空原日志筛选并回第一页")
    body, proof = await audit_view(e, await pending.value, account, store_id, role)
    e.business_unchanged(before, "after_original_audit_reset")
    return body, proof


async def audit_page_to(e, account, store_id, role, body, target, *, entity_type="", entity_id=None):
    require(1 <= target <= max(1, (body["total"] + 29) // 30), "明确目标页超出原审计范围")
    before = e.business_snapshot("before_native_known_audit_pages")
    direction = 1 if target > body["page"] else -1
    proofs = []
    for page in range(body["page"] + direction, target + direction, direction):
        async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/audit") as pending:
            await e.click(f'#main [data-act="page"][data-page="{page}"]', "原分页读取已核定的日志页")
        body, proof = await audit_view(e, await pending.value, account, store_id, role, entity_type=entity_type, entity_id=entity_id, page=page)
        proofs.append(proof)
    e.business_unchanged(before, "after_native_known_audit_pages")
    return body, proofs


async def locate_audit_page(e, account, store_id, role, body, audit_id, *, entity_type, entity_id):
    where, values = ("store_id IN (?,0)", [store_id]) if role == "admin" else ("store_id=? AND entity_type NOT IN ('users','stores','feedback','maintenance')", [store_id])
    where += " AND entity_type=? AND entity_id=? AND id>?"
    values.extend((entity_type, entity_id, audit_id))
    offset = e.db.rows("SELECT COUNT(*) AS n FROM audit_logs WHERE " + where, tuple(values))[0]["n"]
    target = offset // 30 + 1
    before = e.business_snapshot("before_known_audit_page_navigation")
    body, proofs = await audit_page_to(e, account, store_id, role, body, target, entity_type=entity_type, entity_id=entity_id)
    require(any(r["id"] == audit_id for r in body["items"]), "已核定原日志页没有明确来源")
    e.business_unchanged(before, "after_known_audit_page_navigation")
    return body, proofs


async def audit_pages(e, account, store_id, role):
    first, initial = await audit_reset(e, account, store_id, role)
    require(first["total"] > 30 and len(first["items"]) == 30, "同轮非空日志不足两页，不能冒充分页完成")
    before = e.business_snapshot("before_native_audit_pagination")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/audit") as next_page:
        await e.click('#main [data-act="page"][data-page="2"]', "读取实际第二页原日志")
    second, second_proof = await audit_view(e, await next_page.value, account, store_id, role, page=2)
    require(second["items"] and not ({r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}), "原日志两页重复或第二页为空")
    async with e.page.expect_response(lambda r: r.request.method == "GET" and urlsplit(r.url).path == "/api/audit") as previous:
        await e.click('#main [data-act="page"][data-page="1"]', "回到原日志第一页")
    returned, returned_proof = await audit_view(e, await previous.value, account, store_id, role)
    require(returned["items"] == first["items"] and returned["total"] == first["total"], "只读分页期间原审计来源改变")
    e.business_unchanged(before, "after_native_audit_pagination")
    return [initial, second_proof, returned_proof]


async def audit_detail(e, body, audit_id, *, scope_label, fields):
    item = next((r for r in body["items"] if r["id"] == audit_id), None)
    require(item is not None, "明确原审计不在本次原UI响应内")
    before = e.business_snapshot("before_native_audit_detail")
    await e.click(f'#main [data-act="auditdetail"][data-id="{audit_id}"]', "核对明确原业务日志详情")
    await expect(e.page.locator("#modal-title")).to_have_text("操作详情")
    summary = e.page.locator("#modal .stack > p")
    displayed, _ = local_time(one(e, "audit_logs", audit_id)["occurred_at"])
    await expect(summary).to_contain_text(item["actor_name"])
    await expect(summary).to_contain_text(item["reason"] or "业务操作")
    await expect(summary).to_contain_text(displayed)
    header = e.page.locator("#modal .stack > .facts").nth(0)
    await expect(header.locator(".fact").filter(has=e.page.locator(".key").filter(has_text="业务范围")).locator(".value")).to_have_text(scope_label)
    await expect(header.locator(".fact").filter(has=e.page.locator(".key").filter(has_text="原记录编号")).locator(".value")).to_have_text(str(item["entity_id"]) if item["entity_id"] is not None else "—")
    visible = {}
    for key, label in fields.items():
        values = []
        for heading, column in (("操作前", "before_data"), ("操作后", "after_data")):
            value = (item[column] or {}).get(key)
            if value is None or value == "":
                continue
            group = e.page.locator('#modal h3:text-is("' + heading + '") + .facts')
            fact = group.locator(".fact").filter(has=e.page.locator(".key").filter(has_text=label))
            await expect(fact).to_have_count(1)
            text = ("是" if value else "否") if isinstance(value, bool) else str(value)
            if key.endswith("_cents"):
                require(isinstance(value, int), "金额原源不是整数分")
                text = ("-" if value < 0 else "") + f"{abs(value) // 100:,}.{abs(value) % 100:02d}"
            elif key.endswith("_milli"):
                require(isinstance(value, int), "数量原源不是整数千分位")
                text = ("-" if value < 0 else "") + f"{abs(value) // 1000:,}" + (("." + f"{abs(value) % 1000:03d}".rstrip("0")) if abs(value) % 1000 else "")
            await expect(fact.locator(".value")).to_have_text(text)
            values.append({"side": column, "visible_text": text})
        require(values, "所核详情字段没有实际原来源：" + key)
        visible[key] = values
    await e.snapshot(f"hk193-native-audit-{audit_id}")
    await e.click('#modal .modalhead [data-act="close"]', "关闭只读原日志详情")
    await expect(e.page.locator("#modal")).not_to_be_visible()
    e.business_unchanged(before, "after_native_audit_detail")
    return {"audit_id": audit_id, "entity_type": item["entity_type"], "entity_id": item["entity_id"], "actor_id": item["actor_id"], "action": item["action"],
            "native_detail_clicked": True, "utc_api_and_shanghai_ui_matched": True, "fields": visible, "business_unchanged": True}


async def audit_viewports(e):
    before = e.business_snapshot("before_audit_viewports")
    table = e.page.locator('#main .audit-records table')
    originals = await table.locator('tbody tr').evaluate_all(
        "rows => rows.map(r => ({id:r.querySelector('[data-id]').dataset.id,cells:[...r.cells].map(c=>c.textContent.trim())}))")
    require(originals and all(len(r["cells"]) == 7 for r in originals), "日志宽度核对缺非空七原字段")
    original_viewport = e.page.viewport_size
    results = []
    try:
        for width in (390, 768, 1440):
            e.action("viewport", "核对原日志显示宽度", width=width, height=1000)
            await e.page.set_viewport_size({"width": width, "height": 1000})
            await expect(table).to_be_visible()
            current = await table.locator('tbody tr').evaluate_all(
                "rows => rows.map(r => ({id:r.querySelector('[data-id]').dataset.id,cells:[...r.cells].map(c=>c.textContent.trim())}))")
            require(current == originals, "改变宽度丢失或改写原日志七字段")
            require(await table.locator('thead th').all_text_contents()
                    == ["时间", "操作人", "操作", "业务范围", "原记录编号", "说明", "查看"], "日志七列表头不完整")
            geometry = await table.evaluate("t => {const w=t.parentElement;return {page_width:document.documentElement.clientWidth,page_scroll:document.documentElement.scrollWidth,wrapper_width:w.clientWidth,wrapper_scroll:w.scrollWidth,row_heights:[...t.querySelectorAll('tbody tr')].map(r=>r.getBoundingClientRect().height)}}")
            require(geometry["page_scroll"] <= geometry["page_width"]
                    and geometry["wrapper_scroll"] <= geometry["wrapper_width"], "原日志在此宽度横向溢出")
            buttons = table.locator('[data-act="auditdetail"]')
            await expect(buttons).to_have_count(len(originals))
            for index in range(len(originals)):
                await expect(buttons.nth(index)).to_be_visible()
                await expect(buttons.nth(index)).to_be_enabled()
            await e.snapshot("hk193-audit-width-" + str(width))
            results.append({"width": width, "geometry": geometry, "audit_ids": [r["id"] for r in originals],
                            "seven_original_fields_unchanged": True, "original_details_visible_enabled": True,
                            "native_screenshot_written": True})
    finally:
        if original_viewport is not None:
            await e.page.set_viewport_size(original_viewport)
    e.business_unchanged(before, "after_audit_viewports")
    e.observe("native_audit_viewports", results)
    return results


async def role_audit(e, account, store_id, role, src):
    original, opened = await audit_open(e, account, store_id, role)
    require(original["total"] > 0 and original["items"], "本店岗位只能看空审计页，不能通过")
    viewports = await audit_viewports(e) if role == "manager" else []
    paged = await audit_pages(e, account, store_id, role)
    body, filtered = await audit_filter(e, account, store_id, role, "typed_master", src["supplier"]["id"])
    details, scoped_pages = [], []
    for row in src["supplier_audits"]:
        body, moved = await locate_audit_page(e, account, store_id, role, body, row["id"], entity_type="typed_master", entity_id=src["supplier"]["id"])
        scoped_pages.extend(moved)
        details.append(await audit_detail(e, body, row["id"], scope_label="业务资料", fields={"name": "名称", "code": "编码", "contact_name": "联系人", "phone": "联系电话"}))
    if body["total"] <= 30:
        await expect(e.page.locator('#main [data-act="page"][data-page="2"]')).to_be_disabled()
    type_body, type_filter = await audit_filter(e, account, store_id, role, "typed_master")
    require(type_body["total"] > 0 and type_body["items"], "原主档类型筛选没有实际来源")
    if type_body["total"] > 30:
        second_type, forward = await audit_page_to(e, account, store_id, role, type_body, 2, entity_type="typed_master")
        _, back = await audit_page_to(e, account, store_id, role, second_type, 1, entity_type="typed_master")
        scoped_pages.extend(forward + back)
    exclusions = []
    if role != "admin":
        for entity in EXCLUDED:
            result, proof = await audit_filter(e, account, store_id, role, entity, src["store_audit"]["entity_id"] if entity == "stores" else None)
            require(result["total"] == 0 and result["items"] == [], "非admin未排除原管理类型")
            exclusions.append(proof)
    else:
        global_body, global_proof = await audit_filter(e, account, store_id, role, "stores", src["store_audit"]["entity_id"])
        details.append(await audit_detail(e, global_body, src["store_audit"]["id"], scope_label="门店", fields={"name": "名称", "code": "编码"}))
        exclusions.append(global_proof)
    return {"role": role, "nonempty_original_page": opened, "native_viewports": viewports, "actual_two_page_navigation": paged, "supplier_filter": filtered, "type_only_filter": type_filter,
            "actual_filtered_page_navigation": scoped_pages, "native_details": details,
            "management_type_checks": exclusions, "query_zero_business_write": True, "money_details_with_no_source": "not_tested", "audit_export_supported": False, "audit_export_executed": False}


async def audit_invalid_identifier(e):
    before = e.business_snapshot("before_native_audit_invalid_identifier")
    await e.fill('#audit-filters [name="entity_id"]', "0", "核对原编号必须是正整数")
    requests = []
    listener = lambda request: requests.append(request) if request.method == "GET" and urlsplit(request.url).path == "/api/audit" else None
    e.page.on("request", listener)
    try:
        await e.click('#audit-filters button[type="submit"]', "无效原编号由原UI明确拒绝")
        await expect(e.page.locator('#audit-filters [name="entity_id"]:invalid')).to_have_count(1)
        require(not requests, "无效原编号仍发出原审计查询")
        e.business_unchanged(before, "after_native_audit_invalid_identifier")
    finally:
        e.page.remove_listener("request", listener)
    await e.fill('#audit-filters [name="entity_id"]', "", "修正原编号输入并清除原字段错误")
    await expect(e.page.locator('#audit-filters [name="entity_id"]:invalid')).to_have_count(0)
    return {"native_invalid_positive_integer": True, "actual_audit_get_count": 0, "input_correction_cleared_validity": True, "business_unchanged": True}


async def system_followon_business(e, context, credentials):
    cp = Checkpoint(e)
    main_page, contexts = e.page, []
    src, admin, added, restored = None, None, False, False
    try:
        src = dependencies(e, cp)
        cp.start("HK-192")
        admin = await login_as(e, context, credentials, "admin", "parameters", src["first"])
        admin_configuration = await configuration(e, admin, "admin")
        photo = await branding(e, admin, src["first"])
        cp.note(admin_parameters=admin_configuration, login_photo=photo)
        manager_page, manager_login = await new_staff_page(e, context, contexts, src, "manager", src["first"], "manager")
        manager_configuration = await configuration(e, src["manager"], "manager", target=("service-intake/resources", "工位与快捷项目", "/api/service-intake/catalog"))
        receiver_page, receiver_login = await new_staff_page(e, context, contexts, src, "receiver", src["second"], "service")
        receiver_configuration = await configuration(e, src["receiver"], "service", target=("customer-reminders", "车辆提醒与续保提取", "/api/customer-service/reminders/rules"))
        password = await password_check(e, context, contexts, src, receiver_page)
        await switch_store(e, src["third"], one(e, "users", src["receiver"]["id"]), "auditor")
        auditor_configuration = await configuration(e, src["receiver"], "auditor")
        await switch_store(e, src["second"], one(e, "users", src["receiver"]["id"]), "service")
        await cp.passed(manager_parameters=manager_configuration, receiver_parameters=receiver_configuration, auditor_parameters=auditor_configuration,
                        actual_manager_login=manager_login, actual_receiver_login=receiver_login, personal_password=password,
                        arbitrary_environment_write=False, original_rules_not_republished=True, login_photo_restored=True)
        cp.start("HK-193")
        e.page = main_page
        await audit_open(e, admin, src["first"], "admin")
        invalid_id = await audit_invalid_identifier(e)
        admin_audit = await role_audit(e, admin, src["first"], "admin", src)
        cp.note(admin_audit=admin_audit, invalid_identifier_no_request=invalid_id)
        e.page = manager_page
        manager_audit = await role_audit(e, src["manager"], src["first"], "manager", src)
        cp.note(manager_audit=manager_audit)
        e.page = main_page
        extra_roles = {**src["original_roles"], src["first"]: "auditor"}
        extra = await memberships(e, admin, src["receiver"]["id"], extra_roles, src["first"], restoring=False)
        added = True
        cp.note(temporary_auditor_authorization=extra)
        revoked = await revoked_page(e, receiver_page, src["receiver"]["id"])
        receiver_login = await native_login(e, one(e, "users", src["receiver"]["id"]), current_password(src, "receiver"))
        require(receiver_login["active_store_id"] == src["first"] and receiver_login["current_role"] == "auditor" and receiver_login["account_role"] == "sales", "追加授权后本人未取得一店审计原投影")
        auditor_audit = await role_audit(e, src["receiver"], src["first"], "auditor", src)
        await switch_store(e, src["third"], one(e, "users", src["receiver"]["id"]), "auditor")
        empty, switched = await audit_open(e, src["receiver"], src["third"], "auditor")
        require(not any(r["id"] in {x["id"] for x in src["supplier_audits"]} for r in empty["items"]), "换店审计夹入一店原供应商日志")
        absent, negative = await audit_filter(e, src["receiver"], src["third"], "auditor", "typed_master", src["supplier"]["id"])
        require(absent["total"] == 0 and absent["items"] == [], "原他店类型及编号被当前店读出")
        cp.note(auditor_audit=auditor_audit, authorization_old_page_revoked=revoked, actual_auditor_login=receiver_login,
                native_store_switch_scope=switched, other_store_source_negative=negative)
        e.page = main_page
        restored_evidence = await memberships(e, admin, src["receiver"]["id"], src["original_roles"], src["first"], restoring=True)
        restored = True
        cp.report["temporary_auditor_restored"] = True
        cp.note(original_two_store_authorization_restored=restored_evidence)
        restored_revoked = await revoked_page(e, receiver_page, src["receiver"]["id"])
        final_login = await native_login(e, one(e, "users", src["receiver"]["id"]), current_password(src, "receiver"))
        require(final_login["active_store_id"] == src["second"] and final_login["current_role"] == "service" and set(final_login["store_ids"]) == set(src["original_roles"]), "恢复后本人登录仍带一店岗位或丢原门店")
        cp.note(restoration_old_page_revoked=restored_revoked, restored_native_login=final_login,
                hk190_recipient_source_store_permission_absent=src["first"] not in final_login["store_ids"])
        await cp.passed(audit_export_supported=False, audit_export_executed=False, admin_manager_auditor_nonempty_scope_complete=True,
                        restoration_exact_original_roles=True, money_details_without_source="not_tested")
        cp.finish({"receiver_id": src["receiver"]["id"], "manager_id": src["manager"]["id"], "supplier_id": src["supplier"]["id"],
                   "source_audit_ids": [r["id"] for r in src["supplier_audits"]], "receiver_restored_store_roles": src["original_roles"]})
    except Exception as error:
        cp.failed(error)
        # A known successful temporary grant may be explicitly undone, once,
        # through the original editor. This is not a replay of an unknown write.
        if added and not restored:
            try:
                e.page = main_page
                cleanup = await memberships(e, admin, src["receiver"]["id"], src["original_roles"], src["first"], restoring=True, require_old_session=False)
                cp.report.update(temporary_auditor_restored=True, failed_run_explicit_ui_restoration=cleanup)
                cp.save()
            except Exception as cleanup_error:
                cp.report.update(temporary_auditor_restored=False, restoration_error=e.scrub(cleanup_error))
                cp.save()
        raise
    finally:
        if e.response_jobs:
            await asyncio.gather(*list(e.response_jobs))
        e.page = main_page
        for separate in reversed(contexts):
            await separate.close()


SYSTEM_FOLLOWON_SCENARIOS = ((SCENARIO, system_followon_business, 240),)
