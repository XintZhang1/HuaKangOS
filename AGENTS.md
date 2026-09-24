## Current checkpoint: assistant thinking and streaming · 2026-09-24

Read CHECKPOINT_STATUS.json and docs/verification/assistant-thinking-20260924/测试报告.md for current evidence. Work only in this candidate; preserve original directory and preview data. Head g35t_assistant_thinking adds a per-message boolean; historical migrations remain unchanged. Assistant defaults to thinking off with an explicit toggle and true SSE; search behavior stays unchanged. Raw reasoning is memory-only within a tool chain, never shown or persisted. Native forms still require separate employee confirmation. Do not expose code/shell/SQL/arbitrary endpoints. See 续开发交接_2026-09-24-业务助手思考流式.md for current boundaries. Earlier entries below are historical.

## Current checkpoint: workflow handbook and search · 2026-09-24

Work only in E:/proj/huakangos_t02g_recovery_pending_20260922/dealer_desk. Preserve the original E:/proj/dealer_desk and existing local preview accounts/data. Read CHECKPOINT_STATUS.json and docs/verification/workflow-handbook-20260924/测试报告.md for this checkpoint's evidence. Earlier full-backend counts are historical; this help/navigation round uses targeted assistant/store regression and all frontend Node tests, plus actual synthetic Chrome. No migration or business transition changed; f24s, statement21/cash7 stay in place.

The 193 original requirements map to 111 workflows in docs/workflow-source/business.json and services.json. Actual synthetic entry screenshots are mapped in screenshots.json and stored under web/workflow-assets; they are not proof that every business branch was executed. Keep titles, buttons and roles synchronized with the real native pages. Build with scripts/build_workflow_guides.py and validate --check; final publication must not use --draft. The generated web/workflow-guides.json, web/workflow-handbook.html and portable docs/全量工作流手册.html are outputs, not hand-edited sources. Screenshot hashes and publication review are checked.

web/workflowcontent.js owns pure help search/rendering and the in-page screenshot viewer; workflowguides.js owns current-store navigation and unsent assistant intent; workflowhandbook.js handles offline/served handbook. The global search reads only static instructions. app/workflow_guides_api.py exposes read-only DeepSeek help matching only on zero local results (server rechecks) or explicit manual trigger. It removes all business tools and accepts only existing catalogue IDs; never turn recommendation text into a URL or command. Frontend debounce, per-context cache and stale-request guards must remain. Never query customer/business records merely to search help. AI entry fills a new unsent draft only: no automatic provider request, business submission or code execution. Preserve existing drafts, busy sessions and pending proposals; clear intent on store change/logout; do not abandon an open business form. Offline system links default to local port8000; deployed handbook uses its current origin.

The previous selected-file assistant contract remains: the employee selects/uploads supported bounded files, chooses rows/text, reviews outgoing content and explicitly sends it. Parsing isn't business evidence; generated forms require explicit human confirmation through original role/store/version/idempotency boundaries. Never give the model arbitrary filesystem paths, shell/code tools or automatic submission.

### Preserved earlier handoff

## Current checkpoint: employee journeys · 2026-09-24

Work only in this candidate; preserve E:/proj/dealer_desk. Read CHECKPOINT_STATUS.json and docs/verification/employee-journeys-20260924/测试报告.md for final/current evidence. The database head is f24s_business_assistant. No migration this round; statement21/cash7 unchanged. Prior counts below are history.

The employee simplification contract is in docs/员工操作简化_20260924.md. One-form vehicle catalogue creation uses vehicle_catalog_service.create_entry via /api/vehicle-catalog/entry, explicit hierarchy and one transaction; never manufacture stock. New customer + initial sales quote use the native quote transaction and explicit duplicate-phone choice. Preserve the old existing-customer idempotency payload. An uncertain browser submission retries its frozen body/key; never re-run phone resolution or silently change fields on retry.

web/livechoices.js owns existing scoped selectors and optional select[data-search-select]; selection IDs, required/disabled state, IME, context epochs and stale callbacks matter. Search text is not a confirmed selection. Historical inventory report choices must keep inactive sources and identical chart/CSV scope. web/formhelpers.js adds same-form evidence upload through the original file API, with a per-form upload lock. Preserve original scan/category/signature-version requirements and original disabled state. No second transaction may secretly perform a business transition while merely uploading or selecting.

Future simplification must reduce repeated typing/navigation while retaining original role, approval, stock, cash and evidence facts. Do not flatten preparation into physical movement or take an AI statement as confirmation. The prior user-approved business assistant remains confirmation-only through guarded original business APIs; this round made no external model calls.

### Preserved earlier handoff

## Current development checkpoint: u13h original business branches · 2026-09-23

Work only in this candidate directory. Original E:/proj/dealer_desk remains untouched. Runtime source is frozen during each full regression; see CHECKPOINT_STATUS.json before editing or claiming results. Database head e13r_member_fee_corrections, new statement definition21 and cash definition7; historical scopes never expand silently. Earlier u13h runs and t02g-fix1 below are preserved history, not acceptance of subsequently changed source.

New domains include finance corrections, procurement prepayments, addon gifts, supplier overpayment refunds, vehicle other income, original-responsibility rework, recharge corrections, local member pricing, detailed work/material repair packages and same-amount renewal-fee recording corrections. Original requirements and the two user exclusions remain authoritative. See docs/原需审计后续处理-u13h.md and docs/晚上试用指引.md for concrete company-rule limits.

repair_package_* owns frozen component Q/C/P/S, exact original intervals, source-bound purchases, actual fulfillment and unused original refunds. C/P/S use independent floor differences: an interval can have C0/P1 and signed discount; never invent a cash or customer allocation to absorb the tail. Completed part returns need actual original stock return; completed work is not unused. Preserve independent refund tasks after source completion; cancel only unpaid proposed/authorized purchases atomically when their original source terminates. Positive refunds require original real account/reference; zero-P component cancellation never fabricates cash.

Member pricing freezes approved local rules in original quotes; package contract lines do not receive a second discount. Package points/revenue use original P at actual fulfillment; original returns reverse original P. Already-spent points debt does not block actual cash refund. aftercare's zero-customer package snapshot must never expose insurance/manufacturer/internal cash; general case net_charge still includes all actual payers.

Partial receipt corrections retain original actual refunds and freeze immutable refund slices. Corrected gross must cover real original refunds; business allocation is the remaining net. Do not rewrite original cash, stock, completed work or aftercare approvals. Definitions19/20 add local component and refund-slice references without counting them as extra cash or revenue.

Renewal-fee corrections change only the verified same-amount receipt account/reference/evidence through independent approval and an append-only correction chain. Preserve the original fee, customer/member, membership period, amount and original receipt business date. Cash definition7 excludes replaced receipt rows and correction reversals; the effective receipt is counted once. A later actual refund uses the effective original account and its actual refund date with an immutable refund basis; correcting a receipt after an actual refund never rewrites that refund or voids the period again. Statement definition21 adds three local count-only sources; definitions1–20 remain frozen. This records actual business receipts/refunds and never invokes bank payment or group-center funds clearing.

Production, actual PostgreSQL and company acceptance remain separate gates. Preserve the user's existing preview administrator and records; backup/copy-upgrade/restore before updating that preview. Never seed, reset or run tests against it.

## Current repair checkpoint: t02g-fix1 · 2026-09-23

The owner explicitly authorized repairs in this candidate directory and confirmed both exclusions: no group-member-center actual funds clearing/payment/arrival approvals, and no peer-store cooperation/admission approval. Keep original supplier/insurer masters, member bookkeeping and business cash/refunds. Work against the original 193 requirements; do not invent extra domains.

This checkpoint unifies vehicle-operation role/subtype checks across ordinary and dossier access. Wrong old grants remain immutable but suspended; valid customer returns remain readable. Unknown original cost remains null, not zero. Questionnaire chart exports require the complete version/digest/question selector and narrow the already authorized report. Tests and browser child processes isolate attachment storage as well as the database.

Windows preview startup is per-source-directory, checks the running process's startup fingerprint, and loads first-admin setup before ordinary login. Current real Windows browser validation is authorized by the owner; earlier "browser deferred" notes below are historical. Real PostgreSQL, company acceptance and production deployment remain separate pending gates. Do not relabel prior scoped test results as the current full run. See CHECKPOINT_STATUS.json and docs/验收与限制.md for exact results. No historic migration changes in this repair.

## Preserved development checkpoint: t02g-dossier-masters

Cross-store dossier snapshots / exact individual files are implemented in `dossier_grant_*`, not a live arbitrary case serializer. Scope is frozen at request and independently approved; account/role/access generation/source visibility/expiry/revocation and current file scanning are rechecked on every read. Ordinary case/file URLs stay closed cross-store. No raw nested JSON, automatic related cases or newly-added attachments leak through the snapshot. Audit must commit before response. Already-downloaded copies cannot be revoked remotely.

Current migration chain ends `r80e_vehicle_transport -> s91f_dossier_grants -> t02g_master_completion`; never rewrite old migrations. Material brand is an optional typed ItemProfile reference, old updates without the key preserve it. Seven dictionaries reuse existing flow_references. Parameter UI links to native rule editors and safe read-only deployment facts; never broadens native write/read permissions or leaks configuration secrets.

Current status/limits are `docs/实施进度.md`, `docs/原始需求范围复核.md`, `CHECKPOINT_STATUS.json`. Later text describing earlier checkpoint gaps is historical, not authority to revive excluded modules. Do not convert 193-item counts to completion percentages or inherited results into current passes.

## Authoritative scope correction · 2026-09-22

Use `全新搭建：功能需求表.docx` (identical to `docs/原始功能需求表.docx`) plus the owner's explicit revisions, NOT assistant-created extensions. All stores are peer, directly operated group stores. Do NOT build shared-counterparty/local-relationship approval. Keep the original supplier/insurer master records and normal references. The existing separate group finance system handles actual payments; the member center is bookkeeping only. Do NOT build group-center actual clearing, payment/bank interfaces, paid/arrived approvals or require their acceptance. Existing business cash registration, refunds, receivables and monthly statements remain in scope. Only granular cross-store original-record/per-file authorization remains from those three proposals. Then audit the original 193 requirements without adding modules. Real browser/real PostgreSQL execution is owner-deferred; preserve runnable tests, never block feature development on it. See `docs/需求范围纠正_20260922.md`.

# Historical resumable checkpoint — 2026-09-22

Read `CHECKPOINT_STATUS.json` and `续开发交接_2026-09-22.md` FIRST. Current r80e-vehicle follows the actually saved q79d gate checkpoint and confirmed p68c base; head r80e_vehicle_transport. New original VIN transport observations, independent plans, original in-transit loss/paired burden, actual found inventory generation, claim original cash/refund, typed clearing and monthly12 are implemented. q79d actual gate and p68c native retail/material-search/questionnaires are retained. See docs/verification/r80e-vehicle: vehicle-final08 is 102 scoped frozen-runtime tests, NOT full current-project acceptance. Old q79d full run had two hardcoded migration head assertions; corrected and re-run in vehicle-final08. Real browser/PG are DEFERRED_BY_USER; new runnable scripts retained, no actual environment run. Next: granular original-record/file grants, then original-scope audit/final same-tree tests. No real company operations, Git push, deployment or external AI.

# huakangos — implementation handoff

## Product contract

This is a workflow-first Chinese dealership application, not a collection of CRUD forms. Primary goal: fewer mistakes and less employee burden. Never add employee-surveillance/performance rankings, endless mandatory fields, or an AI decision-maker for business transitions. Staff attest only to their own input/actions; the backend owns validation, links, assignments and parallel coordination.

The source `docs/原始功能需求表.docx` is a compressed inventory, not a confirmed process definition. `docs/需求覆盖表.md` distinguishes source scope from our implemented/default/proposed design. Do not claim all source features are finished because a top-level menu exists.

**Do not reintroduce automatic code generation, Git push, Feishu code approval or unattended deployment.** Daily optional AI summaries are separate and default off.

## Current architecture / where to edit

| Path | Responsibility |
|---|---|
| `app/sales_quote_*.py`, `service_orders_*.py` | Versioned vehicle quotes and independently settled customer service fees/pass-through principal; never refund typed service principal through generic order aftercare |
| `app/vehicle_catalog_*.py`, `inventory_reports_api.py`, `*_period_analytics.py`, `procurement_analytics.py` | Explicit model hierarchy and scoped inventory/procurement period reports; unknown opening history stays incomplete |
| `app/transfer_exception_*.py`, `transfer_loss_reports.py`, `reconciliation_v8.py` | New material transfer v3 investigations, original-batch loss, actual external recovery, paired loss clearing and frozen local statement sources; never invent a goods recovery or cancel posted loss |
| `app/flow_specs.py` | Executable kind/action/field/role/state catalogue; front and back share it |
| `app/flow_engine.py` | Guarded state transitions, parallel child cases, task routing, finance/stock/member side effects |
| `app/flow_models.py` | Store-scoped versioned records and immutable evidence/ledgers |
| `app/flow_api.py` | Scoped endpoints, idempotency envelope, lookups, masters, file download |
| `app/business_entity_*.py` | Independently approved legal entity revisions, store/account bindings, new case/cash attribution, original-source returns and fail-closed production opening |
| `app/visit_activity_*.py`, `app/material_value_*.py` | Actual contact/gate events and detailed goods/service/unallocated value reconciliation; same source rows for charts and CSV |
| `app/flow_documents.py` | Plain-text templates, immutable DOCX snapshots, signed-source association, file validation |
| `app/flow_analytics.py` | Combined period/current/cohort analytics, tables used for drilldown/export |
| `app/analytics.py`, `reports.py` | Legacy-compatible snapshot plus new combined summary, deterministic rules, optional AI |
| `app/tenancy.py` | Query scope, write-store guard and ownership enforcement |
| `app/security.py` | Passwords, sessions, CSRF and roles |
| `app/group_models.py`, `group_service.py`, `group_api.py` | Explicitly authorized shared identities, central principal wallet, local settlement links and refund workflow |
| `app/report_worker.py`, `backup_integrity.py` | Standalone report process and read-only SQLite restore validation |
| `app/file_security*.py` | Fail-closed quarantine, ClamAV adapter, immutable scan audit and file usability guard |
| `app/master_*.py` | Typed store masters, reference guards and reviewed new-store opening inventory |
| `app/procurement_*.py` | Multi-line procurement, receipt/return batches, actual cash and supplier payable |
| `app/transfer_*.py` | Explicitly authorized cross-store material coordination, physical postings and paired internal balances |
| `app/vehicle_transfer_*.py` | Central VIN custody, distinct inventory generations, real vehicle handoffs and paired balances |
| `app/vehicle_procurement_*.py` | Vehicle plans, frozen prices, actual supplier payments, VIN shipments/receipts/returns |
| `app/retail_*.py`, `inventory_availability.py` | Independent accessory sales, reservations shared by every stock consumer, original-cost returns |
| `app/reconciliation_*.py` | Immutable period source versions, independent seal/reopen, actual two-store clearing and offsets |
| `app/stock_reports.py`, `commercial_analytics.py` | Source-backed period stock, actual-date retail returns and procurement/cash separation |
| `app/repair_*.py` | Repair v3 quotes, customer authorization, stock facts, quality and separate payer settlement |
| `app/group_benefits_*.py` | Frozen benefit rules and separate bonus/points/coupon/package units, refunds and internal clearing |
| `app/customer_service*.py`, `reminder_worker.py` | Customer vehicle facts, scoped history grants, explicit service actions and approved internal reminder rules |
| `docs/requirements.json`, `scripts/requirements.py` | Stable HK-001 through HK-193 source requirement and acceptance register |
| `app/main.py`, `services.py` | Existing v0.2 records retained; new legacy business writes (including raw vehicle records) disabled by default |
| `web/app.js`, `styles.css` | Chinese task UI, dynamic forms, native SVG charts; no CDN or bundler |
| `migrations/versions/c803_workflow.py` | Frozen 0.3 schema, old user-role constraint upgrade |

## Development commands

Use Python 3.11–3.13. Never point tests at a company database.

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check web/app.js  # syntax check only; Node is NOT required to run the app
python -m app.cli init --demo  # new independent test DB only; explicitly set FILE_SCAN_MODE=structure_only for synthetic trials
python -m app.run
```

`tests/conftest.py` force-sets a temporary database and disables AI/scheduler. It enables the **local-only legacy-write switch for old service regression tests**. Production forbids that switch; dedicated tests verify default write blocking. Do not interpret old regression write permissions as production UI capabilities.

Optional browser script: install Playwright separately, install Chromium, then `python tests/browser_smoke.py`. `--bridge` uses actual Chromium DOM with a Python HTTP transport bridge where managed browsers cannot navigate localhost. Bridge success does not prove browser cookie/CSP/network behavior. Test real mode on the deployment machine before release.

## Non-negotiable invariants

1. **Tenant scope on every read/write, including files, exports, tasks and related IDs.** ORM queries, not identity-map-only `get`, must enforce store criteria. A multi-store view is read-only. Do not modify a row's store_id to simulate a transfer.
2. **Version checks + same transaction.** A command's changes to Case, Task, ledger, hold, events and idempotency receipt commit once. Do not commit halfway through an action. On conflict refresh; do not blind-retry an operation with a new request ID.
3. **No arbitrary state edit endpoint.** A new button needs a defined action, fields, permission, guard, side effects, task responsibility and exception handling.
4. **Money = integer fen.** Decimal input must have at most2 fractional digits, not silently rounded. Material quantity = integer thousandths. Preserve inventory value exactly through issue/return; no float accounting.
5. **Financial/stock/member facts are not workflow wishes.** Generating a task does not move goods, charge balance, confirm payment or issue an invoice. Actual role confirmation and evidence are separate.
6. **No double collection/vehicle occupancy.** VehicleHold and legacy active sales must be checked together with a version lock on Vehicle; CashEntry is the single cash source, PaymentLink connects it to cases. Do not count both as cash.
7. **Immutable ledgers and evidence.** Corrections append attributable records and must reverse the correct original amount. Do not overwrite/delete PaymentLink, StockMove, MemberEntry, FlowEvent or FileAsset through the app. Database administrators remain technically privileged; this is not cryptographically tamper-proof storage.
8. **Signed documents bind to generated bytes/snapshot/template version.** A template edit never rewrites history. A stale snapshot cannot confirm the current order. A file upload is not signature verification or malware clearance.
9. **Frontend cannot be the permission boundary.** API validates again. Prices/costs and financial files have role restrictions. New employee roles must be changed in Python, SQL check constraints, migrations and tests together.
10. **Analytics definitions are contracts.** Period sales by delivery date; stock/balance/tasks are current, not historical reconstruction; cohort shares the same reception batch. Each chart's table must contain the same population as its plotted measure. Internal repair chargebacks are excluded from customer settlement revenue.
11. **Daily summary AI never mutates business data.** Its external payload uses allowlists, numeric aggregates and aliases; no raw customer info, file contents or free text. Combined `workflow.metrics` already includes legacy rows; do not add `metrics` again. The user's explicit 2026-09-23/24 request separately authorizes an employee-confirmed business assistant: it may read native role/store-scoped business data and prepare existing commands, but only a separate employee confirmation invokes the original API. Never execute model code, arbitrary URLs/SQL, credentials changes, or model-invented approvals. Do not reuse the daily-summary switch for this module.
12. **No secrets in repository/artifacts.** `.env`, database, evidence, backup, logs and real customer screenshots stay outside deliverables. No shared default passwords. Demo data and template approval are confined to new synthetic databases.

## Migration / deployment

Alembic migrations are append-only. Do not import mutable model metadata to create old migration revisions. Before upgrade: consistent backup, copy to separate DB, migrate and compare, then validate restore. Existing v0.2 sales/repairs/policies remain separate history and default read-only; **no automatic inference of their unfinished workflow state**. A new data-transfer script must explicitly handle those states and files.

`flow_files.content` uses database BLOBs for bounded small trials; defaults 10MiB/file,100files/case,1GiB/store. This makes SQLite backup include evidence. Larger deployments need private object storage, blob manifests, checked two-phase object/DB writes, retention, virus scanning, quarantine and combined restore tests. Do not simply write to a public static directory.

SQLite/one worker and Windows real Chrome HTTP are validated trial paths. A temporary local PostgreSQL instance also verifies migrations, typed transfer fingerprints, concurrency and dump/restore; see docs/PostgreSQL验证.md for the exact run. This does not establish production load or deployment readiness. Production HTTPS, real ClamAV, multi-machine concurrency, macOS and Docker still need deployment-side validation. Production requires secure cookies, explicit hosts, FILE_SCAN_MODE=clamav and no legacy write switch.

## Honest current limits / next priorities

See coverage matrix. The k137 wave adds insurance/v3, addon/v3, order/v4 typed child dispatch, procurement/v3 current-average stock cost versus original supplier credit, actual repair material analytics and versioned account access. Old order/v3 and procurement/v2 semantics remain explicit. New monthly snapshots use definition 7, old 1–6 remain frozen. PostgreSQL17.11 actual k137 transfer/restore:312 tables,5941 rows,317 attachments (2 private objects),291 sequences, real account CAS plus inventory/member concurrency. The final frozen k137 suite reported 905 passed, 1 skipped in 1124.87s; late narrow privacy/cancellation/browser checks are separately recorded. The initial 881 passed/10 failed run is retained as resolved history. Still outstanding: transport loss, full legal entity/account integration, granular history/file grants, retail group-benefit settlement, all36 reports and company production validation. Reference dictionaries coexist with typed masters; do not assume every old flow consumes them.

New generic cases use flow version 2; dedicated detailed repair v3 history remains supported, while new intake-derived repairs use v4 with immutable VIN/source and actual resource gates. Warehouse and independent membership/intake use v2; dedicated invoice uses v3. There is explicit kind/version catalogue and handler dispatch; unknown versions fail closed. Version 1 history is preserved, but v1 physical order inspection/dispatch/delivery is intentionally blocked until a separately reviewed migration and reinspection. Never silently promote legacy free text to a passed inspection.

The 0.4 foundation now has store-specific roles and a request-only effective principal; never overwrite ORM User.role when switching stores. Group identities and wallets are protected central tables accessed only through the group service; ordinary case/file/stock/cash queries remain store-scoped. Group member cash lives in CashEntry once; GroupPaymentLink is settlement only. Preserve independent `group_refund_`, `benefit_refund_` and `invoice_adjust` tasks when an associated source case completes. See `docs/实施进度.md` for actual progress; the six-stage v1 plan is not complete.

Material transfer central records also require service authority. Its narrowly scoped coordination can update the other party's task/case and paired internal receivable in the same transaction; actual inventory changes always belong to the actor's current store. In-transit assets belong to the source store until acceptance/return. Procurement and transfers have dedicated APIs, not generic flow actions. Open tasks retain their assignee/due date; only an explicit handoff changes responsibility. All evidence use must call file_security.require_usable, not merely look up FileAsset. Missing historic scan status stays quarantined. Opening import applies once to a new non-demo store and never infers unfinished history.

Group benefit face credit C, purchase consideration P and internal settlement S are frozen per issuance rule. Revenue uses P at redemption, not issuance cash or internal S; show group/service-store discounts separately. Each unit kind is independent. Customer service history grants expose a minimal service summary only: they do not grant original case, financial or file access. Automated reminder records explicitly distinguish system execution from an employee click.

Warehouse enrollment is explicit: do not infer historical bins. All material StockMove adapters consume exact prepared location allocations for enrolled items in the same transaction, and warehouse/retail/approved-procurement-return/addon holds share availability. A preparation increments the source Case, not Item; do not invalidate old stock-count snapshots by merely preparing bins. Store balances include local in-transit and always reconcile to Item value; paired bin entries must not become additional purchases or sales.

Membership lifecycle rules and point eligibility freeze before service authorization. Cash is recorded once; points debt is a noncash entitlement recovery and must not block actual monetary refunds. New intake repairs bind verified VIN and real source; full-internal rework never copies the original cash/receivable. Invoice applications, independent approval and actual results are separate immutable facts; pending red does not free blue capacity. Reconciliation summary.definition_version preserves historical source scope (missing means1); new definition5 includes claims, vehicle import and frozen retail bundles; definitions1-4 preserve their historical source scope. Unknown definition versions fail closed.

Claims approvals are not cash. Customer reimbursement usage is limited to original actual customer cash across all claims; approved source reductions block competing refunds/corrections until resolved. Unused third-party pass-through cash has its own original-source refund, without inventing a customer payment. CSV imports invoke existing procurement actions within one transaction; trial always rolls back. Retail bundle prices freeze per set before multiplying quantity, and original line allocations survive partial returns. New reconciliation sources are explicit definition5; old snapshots never silently expand.

## Required change checklist

For every changed business branch: define actor, entry condition, required facts, authoritative source, atomic side effects, next assignee, files in/out, timeout and cancellation/undo. Add happy-path + refusal + cross-store + duplicate + stale-version tests. For money/quantity changes add conservation and competing-operation tests. For reports reconcile chart totals with original rows and CSV. For templates render generated DOCX and inspect every page. For UI test an actual employee account, not only admin; inspect narrow layouts and Chinese errors.

Update coverage, workflow catalogue, metric definitions and validation record together with the code. Do not call an untested branch complete.


## k137 domain boundaries

Insurance premium is pass-through, approved commission is a separate receivable and actual cash remains CashEntry once. Financial event payloads and payments must use role projections; plain nested action JSON is not safe for sales/service/inventory. Addon acceptance and original return determine service facts; generated tasks or authorization do not move inventory. An installed accessory gifted back with a returned vehicle is linked at zero incremental inventory value, not fabricated capitalized purchase cost. Procurement/v3 returns reverse original supplier credit but use current moving-average stock cost and an immutable difference fact; never consume another domain's approved stock hold. Dedicated original-domain terminations must complete before parent sales aftercare; freeze the independently resolved IDs and prove original facts as of the parent decision time in restores.

## l248 domain boundaries

Legal identity is separate from the huakangos brand. Production new cases require an approved local entity policy. Freeze the original case context before its first event, and cash context in the same actual posting transaction. Derived aftercare/invoice/claims/returns inherit only the verified original source; old unknown cases/cash cannot acquire today's identity. New invoice issuer fields and generated document snapshots match the original immutable revision. Contexts never count as extra revenue or cash.

A new formal store first approves entity/store/account configuration and policy, then imports opening facts using explicit approved Account IDs. Each opening action rechecks the original account/version/channel snapshot. OpeningAccountEntry records the original baseline date; no CashEntry is fabricated. Reversible trials reuse approved accounts and roll back all opening effects. Legacy no-policy test imports retain their original empty-account creation contract. Inventory views must not expose account_context, owner mappings or financial proof.

The l248 nonempty PostgreSQL17.11 migration and restore verifies328 tables,6701 rows,367 files (2 private objects) and298 sequences, including long invoice identity and policy-before-opening. The74-module frozen regression passed988 tests with1 Windows symlink skip in1185.87s; all recorded source hashes were unchanged throughout the run. Evidence is in docs/验收与限制.md. Unregistered next-wave modules were explicitly excluded. Actual visit activity does not infer an arrival from an appointment or a departure from cancellation. Material value reports preserve order-level unallocated adjustments; they do not invent SKU margins for unknown legacy lines.

## m359 transport loss checkpoint

New material transfers use v3, with original v2 dispatch intact. Physical dispatch/accept/return and loss share the parent version lock and cumulative original batch value. Active investigations pause ordinary physical commands; real returned goods require an explicit passed quality fact. Loss, frozen burdens, external confirmed targets and actual cash remain distinct. `material_loss` clearing pairs by posting_id AND exception_id; normal completion preserves `transfer_recovery_` tasks. Statement definition 8 adds seven local original sources; 1–7 never expand silently. Found goods after posted loss still require a separate original recovery workflow; do not fake it with an ordinary receipt. Independent future retail/group and observation drafts are not registered or part of this checkpoint.

## 2026-09-22 continuation checkpoint: n46a-fix1

The uploaded archive already registered n46a models/routes/migration. Top-level m359 evidence was historical. Keep DB head `n46a_operations_extensions`; no historical migration was edited in this checkpoint. The runtime `ClearingBucket` CHECK now includes `material_found`, matching n46a, so reverse actual clearing no longer fails with a misleading version-conflict response.

New statement definition **9** adds only six local `transfer_goods_*` fact/link sources (see `reconciliation_v9.py`). Keep prior definitions 1–8 unchanged; no new retail/group sources are frozen. `GoodsFact` counts observations, not stock; `GoodsPosting` restores original cost; `GoodsSettlement` reverses internal liability; `GoodsRefund` links an existing actual payment and adds no cash. All central physical/review reads require domain authority AND explicit local store filtering. Backup validation compares immutable origins and frozen-subset summaries without substituting later facts. A digest is not an externally signed anti-admin-tampering guarantee.

**Retail/group public writes are deliberately blocked** by `retail_group_readiness.py`. UI reads advertise `write_enabled=false`; no environment, header or request bypass. Native retail receive/refund/actual return, source invoice, external settlement, old group case actions and unbound retail-eligible issuance must not bypass the boundary. Native points sync checks the boundary only after finding an authorized nonempty points claim; no-op sync must not block unrelated return requests. Do not remove the boundary until every native hook, price/points/invoice/report/statement source and original return has real registered-router tests. `test_retail_group_service.py` explicitly attaches missing hooks inside isolated domain authority and is NOT production-acceptance evidence.

Observation validator must return a mapping for an absent legacy domain and reject a partial schema. Use nonempty l248→m359→n46a migrations, compare original row fingerprints and validate old cash/clearing. Current verification and environment limitations are in `续开发交接_2026-09-22.md`. Do not relabel historical Windows/Chrome or PostgreSQL evidence as this run's result.

## Business assistant checkpoint · 2026-09-24

Current working tree is the candidate directory `E:/proj/huakangos_t02g_recovery_pending_20260922/dealer_desk`; the original directory remains preserved. User selected DeepSeek again. The separate assistant prepares native business operations for explicit employee confirmation, with current roles/store/version/idempotency enforced by the original APIs; daily AI summaries remain disabled. Never turn chat text into automatic approval or expose arbitrary code, SQL, endpoints or credentials to the model.

Head `f24s_business_assistant` adds four assistant tables. The frozen 144-module regression passed 1833 tests with one Windows symlink skip; 694 source files were unchanged. 55 JS syntax checks and 59 Node checks passed. Actual synthetic DeepSeek evidence covers lead creation, phone supplementation and callback, plus brand creation with a real 390px Chrome confirmation. Zero-model cold opening, refresh and normal login passed. This is limited model coverage, not company acceptance of all 193 requirements.

The original local preview was backed up, upgraded and restarted without changing its 74 existing rows; current accounts remain usable. See `docs/verification/business-assistant-20260924/测试报告.md`, `docs/业务助手使用说明.md`, `docs/业务助手模拟问题清单.md` and `续开发交接_2026-09-24.md` for current evidence and limitations. Current PostgreSQL, production deployment and company business acceptance remain pending. MiMo is an inactive adapter and failed historical experiment, never an automatic fallback.
