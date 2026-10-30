# Bridge Hub — MASTER COMPLETION PLAN

განახლება: 2026-10-30, Chat181 (Chat180 history preserved). სტატუსი: სამუშაო გეგმა; **Production HOLD**.
ეს არის ერთი საერთო შესრულების გეგმა. ძველი გეგმები, ანგარიშები და კოდი ინახება.
შემდეგი სამუშაოები განახლდება ამავე ფაილში, მტკიცებულებით და ზუსტი commit-ით.

## 1. წყარო, შემოწმების ფარგლები და სტატუსები

საწყისი კოდი: `52a35d9b8330bbbf9aa6b91c17f01cf9f4ce7b46`.
`main`: `aa8ba59ca816bbb6c74523979289b59ed9265554`.
PR #153: `a2f629ad070546ec47a1393a5b9ad47eac8992ca`, OPEN/DRAFT, 5 commits/4 files.
PR #154: OPEN/DRAFT, 186 commits/93 changed files at this checkpoint; already
contains #153. Do not merge the two independently or rewrite their histories.

შემოწმდა ყველა 1,054 tracked ფაილის ინვენტარი და hash; 738 Python ფაილი
AST-ით იკითხება სინტაქსური შეცდომის გარეშე. აქედან 358 app Python ფაილია,
276 unit და 65 integration test module; 168 docs ფაილი, 36 static HTML.
575 route decorator არის **დეკლარირებული**; ეს არ ნიშნავს 575 დადასტურებულად
დარეგისტრირებულ/ავტორიზებულ endpoint-ს. რეალური registry:
`app/core/router_registry.py`. ყველა კოდის სტრიქონის ხელით უსაფრთხოების
სერტიფიცირება ამ ინვენტარის შედეგი არ არის.

წაკითხულია არსებული AI Chief Accountant master plan, ERP expansion,
trust/subscription/ledger გეგმები, Chat175–179 ანგარიშები და ისტორიული
Central Bridge Service, AI Accounting Bridge Roadmap და Control Tower Strategy.
პირადი Windows მისამართები, handoff და აღდგენის დეტალები საჯარო GitHub-ში არ იწერება.

| სტატუსი | მნიშვნელობა |
|---|---|
| DRAFT-VERIFIED | არსებული ქცევა დადასტურებულია იზოლირებულ ტესტში; live არ იგულისხმება |
| REPAIR | კოდში ნანახი კონკრეტული შეუსაბამობა; შესწორება და regression საჭიროა |
| FINISH | საფუძველი არსებობს; ფუნქციური ჯაჭვი/კონტრაქტი დასასრულებელია |
| RETEST | კოდი არსებობს; ახლანდელი სრული მიღების მტკიცებულება არ გვაქვს |
| DESIGN | მიზანი/დოკუმენტი არსებობს; სრული runtime განხორციელება არ დასტურდება |
| EXTERNAL-HOLD | საჭიროა ოპერატორის, vendor-ის ან ცალკე ნებადართული გარემოს მტკიცებულება |

`P0` = tenant/data/financial truth/recovery release blocker. `P1` = აუცილებელი
სანდო V1 workflow, commercial control ან ოპერაციული მიღება. `P2` = გაფართოება.
არც ერთი ფუნქცია არ ითვლება მთლიანად დასრულებულად მხოლოდ ფაილის, UI მენიუს,
დოკუმენტის ტექსტის ან მწვანე CI icon-ის არსებობით.

## 2. V1-ის ზუსტი საზღვარი

V1 არის არსებული ბუღალტრული და AI ბირთვით აგებული Finance Control Tower:
ნებადართული კომპანიები → დოკუმენტი/ბანკი/ერთი ERP წყარო → evidence →
AI draft/შეჯერება → უფლებამოსილი review → სანდო ანგარიშები და AI Chat.

ორი ფინანსური რეჟიმი მკაფიოდ უნდა გაიმიჯნოს. **A: ERP authority** — ERP რჩება
ოფიციალურ აღრიცხვად; Bridge კითხულობს, ადარებს და ხსნის წყაროებით. **B: Bridge
authority** — official actuals მოდის დამტკიცებული posted ledger-იდან.
ERP-ისა და Bridge-ის ერთი ოპერაცია მეორედ არ უნდა ჩაითვალოს. Draft/approved,
simulation და forecast ცალკე რჩება. Canonical source contract განსაზღვრავს
tenant/company, source, external ID/revision, period, currency/FX, as-of და evidence-ს.

V1-ში აუცილებელია ერთი სრული read/import ჯაჭვი, ერთი სრული document-to-review
ჯაჭვი, financial/AI parity, audit, durable recovery და საბაზისო commercial control.
პირველი vendor ირჩევა რეალურად ხელმისაწვდომი ნებადართული sandbox-ით;
**1C არ არის V1-ის სავალდებულო დამოკიდებულება**. Vendor-ის არქონა არ უნდა
შენიღბოს mock/demo შედეგმა. Live write მხოლოდ ცალკე მიღებული connector-ისთვის.

V1-ის შემდეგ: სრული შვიდი agent-ის დამოუკიდებელი delivery ქსელი, advanced
AI CFO/forecast backtesting, მეორე/მესამე ERP, სრული warehouse/payroll ERP,
universal RS.ge submission, ავტომატური ფინანსური execution და ახალი ქვეყნები.
არსებული payroll/inventory კოდი ინახება და გამოიყენება საჭირო mapping/preview-ში.

## 3. ფუნქციების საერთო მატრიცა

ცხრილში არსებული DRAFT-VERIFIED სტატუსიც მოითხოვს შესაბამის საბოლოო G-gate-ს.
ქვემოთ მოცემული „ტესტი/შემდეგი“ არის მიღების მოთხოვნა, არა უკვე გავლილი შედეგი.

### უსაფრთხოება და ინფრასტრუქტურა

| ID / Scope | არსებული საფუძველი და მდგომარეობა | შემდეგი სამუშაო / მიღების ტესტი |
|---|---|---|
| SEC-01 P0 V1 | JWT/RBAC/platform membership; `authz.py`, `auth_service.py`; DRAFT-VERIFIED ნაწილობრივ | სრული request middleware order; forged tenant/role, inactive user, platform-vs-tenant admin, A/B/C denial |
| SEC-02 P0 V1 | refresh/password/session version; Chat164–169; DRAFT-VERIFIED | migration 015/016 readiness, revoke old access/refresh, concurrent reset, compatibility-preserving rollback; live region parity EXTERNAL-HOLD |
| SEC-03 P0 V1 | durable OAuth state + migration 014; DRAFT-VERIFIED | provider-bound one-use state, callback/browser/SMTP E2E; real provider EXTERNAL-HOLD |
| SEC-04 P0 V1 | DB tenant ContextVar and forced-RLS synthetic tests | რეალური roles/owners/grants/RLS, no-context/connection reuse და migration 013 audit; live EXTERNAL-HOLD |
| SEC-05 P0 V1 | Host/origin/proxy and Redis/SlowAPI guards; DRAFT-VERIFIED | observed proxy/host inventory, two actual replicas/outage, redirects/websocket; flags unchanged until separately authorized |
| SEC-06 P0 V1 | credential vault/encryption/masked reads, migrations 009/012; vault CI exists | key loss/rotation, cross-tenant refs, redacted logs, runtime grant/schema parity and real connector auth |
| SEC-07 P0 V1 | signed branding/report/audit guards; Chat175 | all sibling routes, attachment download and unsafe legacy preview; positive/negative JWT HTTP/browser |
| SEC-08 P0 V1 | signed tenant and write RBAC through ERP routes/services; DRAFT-VERIFIED at `da32bac`; live adapter remains HOLD | PG15/16 A/B import/upsert/list/classifier with real sync helper under nonowner FORCE-RLS; default rows preserved; no demo credential load or persistence |
| OPS-01 P0 V1 | backups/PITR/restore runbooks, historical snapshot | current backup/PITR/RPO/RTO and isolated DB+GCS restore evidence; EXTERNAL-HOLD; never restore over live DB |
| OPS-02 P0 V1 | preserved conflicted Windows/worktrees/manifests | retain source/index/ACL and all unique staged work; restoration acceptance distinct from semantic Git parity; originals read-only |
| OPS-03 P0 V1 | additive SQL files + startup DDL shims | actual schema inventory, privileged migration order, zero runtime DDL under nonowner, additive compatibility/rollback tests |
| OPS-04 P1 V1 | health/version/logging/metrics modules | sanitized diagnostics, correlation, queue age, alert delivery, liveness vs readiness, latency/load and artifact provenance |
| OPS-05 P1 V1 | GitHub CI; backend/PG15/16/Redis/Chroma verified at Chat179 | reproducible build, dependency/license review, exact SHA results; frontend build is currently SKIPPED, not PASS |

### აღრიცხვა და ფინანსური კონტროლი

| ID / Scope | არსებული საფუძველი და მდგომარეობა | შემდეგი სამუშაო / მიღების ტესტი |
|---|---|---|
| FIN-01 P0 V1-B | `posted_ledger_validation.py`, `posting_service.py`; DRAFT-VERIFIED Chat180 for stored-line validation and Decimal precision | validate stored lines before INSERT; finite amounts, both sides, balanced rounded totals, missing account/date/source and Decimal precision; real writer→PG |
| FIN-02 P0 V1-B | cooperative transaction lock DRAFT-VERIFIED at `a91b50f`; direct-SQL uniqueness FINISH | concurrent same-draft writers, same/different tenant, retry/rollback, no duplicate header/source; DB uniqueness vs cooperative lock distinguished |
| FIN-03 P0 V1 | `financial_statements_service.py` guards; main four joins fixed | sibling `ledger_service.py` tenant join/date normalization repaired and verified in Chat180; broad-line RLS + bounded-date PG PASS; retain JWT/UI retest |
| FIN-04 P0 V1 | canonical historical read types, alias normalization, whole-basis unknown/contradiction guard and writer mapping preflight implemented; CI pending | no historical backfill; typed custom history preserved; complete tenant COA import/mapping and live inventory remain |
| FIN-05 P0 V1 | stored functional GEL reports and rounded-balance guards DRAFT-VERIFIED `547ba51`; legacy foreign totals fail closed | posting static fallback repair in progress; quote source/effective date/freshness, exact output precision, real schema/provider acceptance remain |
| FIN-06 P0 V1-B | migration 011 ledger + Chat179 composite FK candidate | append-only UPDATE/DELETE, header/line totals, source links and correction states; candidate SQL tested only; live rollout EXTERNAL-HOLD |
| FIN-07 P0 V1 | canonical P&L reused by two AI readers; DRAFT-VERIFIED for synthetic GEL | all report/dashboard/AI tools share authority, period, currency and no-data semantics; unposted/demo/reversed exclusions |
| FIN-08 P1 V1 | balance sheet assets/liabilities/equity read path | current profit/retained earnings, opening balances, period close and FX; trial equation and complete equity reconciliation, not just asset totals |
| FIN-09 P1 V1 | unknown periods fail closed; unavailable CFO cashflow is null; DRAFT-VERIFIED at `2381108` | complete classification-review workflow and actual cash reconciliation; FX/compound/noncash/reversals and UI unavailable-state acceptance remain |
| FIN-10 P1 V1 | trial/account/counterparty ledgers have legacy posted-draft paths | consistent source flag/labels, opening/period/closing balances and statement parity; no silent fallback |
| FIN-11 P0 V1-B | approval/correction/period-lock services, historical guarded candidates | actual route→transaction→audit; maker/checker, concurrent close vs posting, locked dates, immutable reversal; preserve candidate provenance |
| FIN-12 P0 V1-B writes | posting/ERP success and local ledger are separate transactions | durable receipt/outbox/reconciliation; timeout and unknown result, commit failure, duplicate importer; never retry external mutation blindly |
| FIN-13 P1 V1 | payroll/tax/VAT services and rules exist | posted-only authoritative basis, current policy pack/SME sign-off, payroll history, declaration preview vs filed status; no live submission |
| FIN-14 P1 V1 | monthly/year close, opening balances, reconciliation modules | end-to-end checklist, unmet evidence, period lock, closing entries, rollback/no partial mutation |
| FIN-15 P1 optional V1 | AR/AP/aging/budget/cost centers/fixed assets/inventory exist | narrow pilot-critical reports; provenance, units, valuation and double-entry controls. Full ERP expansion P2; do not duplicate existing systems |

### დოკუმენტები და ინტეგრაციები

| ID / Scope | არსებული საფუძველი და მდგომარეობა | შემდეგი სამუშაო / მიღების ტესტი |
|---|---|---|
| ING-01 P1 V1 | upload/parser/document_processing/canonical schemas | PDF/CSV/XLSX → evidence → valid draft; rejected files, schema/version, duplicate content and A/B owners |
| ING-02 P1 V1 | OCR worker/callback routes, document AI | multipage/rotation/quality corpus, callback signature/replay, retry/crash and exactly-one draft; external OCR only separately authorized |
| ING-03 P1 V1 | Email/IMAP collector/inbound/background modules | attachment→OCR→draft durability, duplicate message, mailbox state, reconnect and async pool safety; no real email send |
| ING-04 P0 V1 | `storage_service.py`, GCS/evidence bundles | tenant object authority, signed URL expiry, path traversal/SSRF review, DB-object parity and restore; live GCS EXTERNAL-HOLD |
| ING-05 P1 V1 | Bank CSV/parser/Bank Brain/reconciliation | deterministic golden bank formats, units/signs, duplicate statement, partial matching, ownership, replay and FX; no live transfer |
| ING-06 P1 V1 | RS.ge SOAP/read/compare/draft workflow | reconcile actual WSDL/API contract; read-only sandbox, pagination/status mapping, error/retry, per-tenant vault; external calls EXTERNAL-HOLD |
| ING-07 P0 write safety / P1 V1 read | Balance/ORIS/1C adapters contain demo/generic endpoint assumptions | one vendor-verified read adapter, capability matrix, record/COA/report mapping, cursor/freshness. Preserve disabled write gates |
| ING-08 P0 V1 | tenant/RBAC/demo safety DRAFT-VERIFIED; complete live source adapter FINISH | source-of-record and external identity, revision/dedup, tenant propagation, no demo data labelled official; SEC-08 first |
| ING-09 P1 V1 fallback | journal/CSV/XML/PDF exports exist | formula injection, safe file names, evidence links, totals and one logical operation per import; exporter alone cannot ensure vendor dedup |
| ING-10 P2 | second ERP, live bank API, universal tax submission | only after first adapter's accepted contract; vendor-specific receipt/idempotency tests, per-action authorization |

### AI, agents და მომხმარებლის ინტერფეისი

| ID / Scope | არსებული საფუძველი და მდგომარეობა | შემდეგი სამუშაო / მიღების ტესტი |
|---|---|---|
| AI-01 P0 V1 | Chat177 signed tenant/role/action checks; DRAFT-VERIFIED | every tool/alternate route denies unapproved mutation; prompt injection cannot alter policy; JWT HTTP negative corpus |
| AI-02 P1 V1 | orchestrator/intent/tool registry/Ask/Claude routes | one result contract: company/source/period/as-of/currency/status/evidence/missing; no-data is not zero; Georgian/English golden questions |
| AI-03 P1 V1 | scoped new chat IDs + tenant cache keys | durable multi-replica history, per-user export/delete, cancellation; safe authorized legacy migration; no automatic old-session reassignment |
| AI-04 P1 V1 | accounting rules, business_logic_ai, learning/QA/feedback | canonical draft output, deterministic validation, confidence calibration, approved human corrections; no automatic execution authority |
| AI-05 P1 optional / P2 | internal tenant Chroma search + real ONNX PASS | verified tenant/source provenance, model/version policy, Georgian quality corpus and read/write ownership before HTTP exposure; keep disabled meanwhile |
| AI-06 P1 V1 read | CFO dashboard, insights, forecast helpers | all actuals reconcile with authoritative reports; assumptions/missing sources explicit; advanced forecast/backtest P2 |
| AI-07 P2 | `app/ai_systems` modules are not proof of seven autonomous deployed agents | catalogue Accountant/CFO/Tax/Legal/Email/OCR/QA roles and restricted tools; permissions, service identities, failure/cost budgets per role |
| AI-08 P1 minimal V1 / P2 distributed | Central Bridge architecture exists; `route_bridge_service.py` is not the proposed durable bus | reuse existing jobs for V1; versioned envelope, tenant/agent authorization, durable inbox/outbox/dedup/ack/retry/cancel and two dummy agents in isolated PG; Cloud Tasks deployment separately authorized |
| UI-01 P1 V1 | 36 legacy HTML pages + bundled React assets; React source build absent here | choose one supported V1 UI path, inspect API/auth contracts, browser keyboard/error/loading/empty state, company switch and no sensitive URL tokens |
| UI-02 P1 V1 | approval/evidence/cockpit/client portal pages exist | user can inspect evidence, edit draft, approve/reject, see resulting authoritative report and audit; E2E fixture per role |
| UI-03 P1 V1 | notifications/WebSocket history/search/report routes exist | replay/reconnect/permissions, per-user tenant boundaries; retest historical 404/405 endpoints against effective app routes, not guessed aliases |

### კომერციული ფუნქციები

| ID / Scope | არსებული საფუძველი და მდგომარეობა | შემდეგი სამუშაო / მიღების ტესტი |
|---|---|---|
| COM-01 P1 V1 paid | subscription service AND middleware are implemented/registered; old plan saying absent is stale | status/plan/trial/expires schema and path categories, unknown-state fail closed, renew/suspend/grace/clock-boundary tests; billing must not bypass tenant safety |
| COM-02 P1 V1 | SaaS/signup/tenant/partner/admin modules exist | controlled onboarding, invited members, company selector, read-only suspended access, support/audit; no invented platform privilege |
| COM-03 P1 V1 paid / P2 provider | plans/usage/billing surfaces exist; real provider settlement unverified | deterministic usage/quotas and entitlement; signed webhook replay/idempotency in sandbox; payment processor/revenue activation separately approved |
| COM-04 P1 V1 | basic ops/config docs and support surfaces | pilot cohort, support/incident/recovery runbooks, cost per document/chat/job, export/data retention/offboarding; test authorization before deletion |
| COM-05 P2 | multi-country/advanced packages/full ERP surfaces | expand only against measured pilot use; pricing is a hypothesis until customer/cost evidence; preserve existing modules |

## 4. სამუშაოს თანმიმდევრობა და დამოკიდებულებები

| რიგი | ეტაპი | ფუნქციები / დასრულების მტკიცებულება | რეჟიმი |
|---|---|---|---|
| 0 | baseline + ეს გეგმა | source inventory, main/153/154 ancestry, current handoff, G0 preservation | READ-ONLY; COMPLETE for this checkpoint |
| 1 | Ledger validation და sibling readers | FIN-01/03/04; failing-before + passing-after, actual PG15/16 writer/report tests | DRAFT-VERIFIED at `af537f8`; PG15/16 432 each |
| 2 | Retry/concurrency და import tenant | FIN-02, SEC-08/ING-08 safety; simultaneous writers and A/B memory import | DRAFT-VERIFIED; actual DB uniqueness/live provider history remain open |
| 3 | Financial reconciliation | FIN-05/07/08/09/10/13; FX, complete balance, unknown cashflow and all AI/report readers | DRAFT |
| 4 | Mutation boundaries | FIN-06/11/12, SEC-01/04/06/07; all direct/correction/export paths and rollback | DRAFT; DB candidates remain unapplied |
| 5 | Documents/jobs and commercial controls | ING-01..05, AI-03/04, COM-01..04; crash/replay, quotas, lifecycle and onboarding | DRAFT; synthetic identities/data |
| 6 | Canonical read adapter + AI Control Tower | ING-06..09, AI-02/06/08, UI-01..03; one reliable authority/read/reconcile journey | offline/sandbox; vendor dependency explicit |
| 7 | სრული მიღება | G0–G8 and test matrix below; exact tested artifact | independent staging/operations approval needed |
| 8 | გაფართოება | AI-07, distributed bridge, forecast/backtest, second ERP, advanced SaaS | after relevant gates; P2 |

თუ რომელიმე ეტაპის ერთი ნაწილი მოითხოვს აკრძალულ მოქმედებას, ის იღებს
EXTERNAL-HOLD-ს. სხვა დამოუკიდებელი Draft სამუშაო გრძელდება თანხმობის მოლოდინის გარეშე.
30/60/90 დღე იწყება stabilization gate-ის შემდეგ; ეს გეგმა კალენდარულ დაპირებას არ იძლევა.

## 5. დიდი Draft PR-ის უსაფრთხო დაყოფა

არსებული PR #153/#154 არ იხურება, არ reset/rebase/force-push-დება და არ იშლება.
ინტეგრირებული head რჩება regression-ის წყაროდ. თითოეულ ახალ შესწორებას აქვს
ცალკე commit/range, ტესტები და rollback note. Review slices:

| Slice | სფერო | წინაპირობა / მთავარი ფაილები |
|---|---|---|
| R01 | membership/signup/OAuth durable state | #153 + auth claims, OAuth route, migration 014 + tests |
| R02 | session revocation/password recovery | R01; auth_service/routes_auth, migrations 015/016 |
| R03 | proxy/origin/Host/WebSocket boundary | R01; middleware + shared origin/client-IP helpers |
| R04 | Redis/SlowAPI global quotas | R03; limiter/policy/security/main + disposable Redis |
| R05 | signed tenant branding/report/audit | R01/R02 + DB context; authz + selected read/write routes |
| R06 | AI tool/session/financial authority | R05; AI routes/session/context/tool registry |
| R07 | posted writer/report correctness | R05; posting/financial/ledger/cashflow services + migration-011 tests |
| R08 | disabled vector groundwork | R06; vector module + real Chroma/ONNX tests; no activation |
| R09 | current minimal repairs | one confirmed defect per commit with narrow regression + cross-package check |
| R10 | runbooks/candidate schema/plan | accompanying slice; never treated as an executed migration |

გასაყოფად საჭიროა **semantic hunks და dependency graph**, არა shared ფაილების
ბრმად გადატანა. `routes_auth.py`, `main.py` და workflow-ები რამდენიმე slice-ს ეკუთვნის.
სუფთა staging branches იქმნება immutable baseline-იდან; ყოველი slice-ით მიიღება
გასაშვები tree და დადებითი/უარყოფითი კონტროლი. წყაროს commit→slice mapping
და integrated end-tree comparison მოწმდება მანამდე, სანამ ვინმე merge-ს განიხილავს.

Stacked Draft-ების შემთხვევაში base იქნება წინა slice და diff იქნება მხოლოდ
იმ slice-ის. ჯერ CI-ის `pull_request.branches: [main]` შეზღუდვა უნდა მოერგოს
კონკრეტულ review branches-ს უსაფრთხოდ; წინააღმდეგ შემთხვევაში green/absent
checks დამოუკიდებელ verification-ს არ ნიშნავს. Deployment job ყოველთვის
SKIPPED უნდა იყოს PR-ზე. ფართო workflow dispatch არ გამოიყენება, რადგან არსებულ
deploy workflow-ში manual dispatch-ს deployment-ის უფლება აქვს.

ამ ეტაპზე ეს არის გაყოფის **გეგმა**; არსებული 186-commit ისტორია არ გადაწერილა.
ახალი bounded commits შეიძლება შეამოწმოს reviewer-მა exact compare range-ით.
ყოველი slice-ის მიღება: preconditions, scoped diff, no unrelated edits, migration
compatibility, fixture/smoke/full regression, failure recovery და reviewer sign-off.

## 6. საბოლოო მიღების ტესტები

| Gate | სავალდებულო პაკეტი | მიღების პირობა |
|---|---|---|
| G0 | source/worktree/index/backup manifest + restore procedure | ყველა უნიკალური სამუშაო დაცულია; ACL/raw-index გამონაკლისები ცალკე დადასტურებულია |
| G1 | signed HTTP + PG nonowner FORCE RLS + WebSocket | tenants A/B/C, role/user boundaries, no-context/pool reuse, injection attempts and revocation; unauthorized success = 0 |
| G2 | golden accounting fixtures | precise GEL/FX, rounding, journal/headers/lines/source, reversals, period close; P&L/BS/CF/TB/AI agree for the same authority/period |
| G3 | negative/retry/concurrency/fault injection | no official mock/demo/approved values, no unapproved action, duplicate request once, timeout/unknown receipt recoverable |
| G4 | independently approved runtime | exact SHA→image digest→service; Host/TLS/proxy/auth/Redis replicas; latency/load and rollback observed |
| G5 | schema/grants/backup/PITR + isolated restore | real role/schema attestation, migration order/compatibility, recoverable DB and GCS; no runtime DDL on unprivileged role |
| G6 | document/email/OCR/bank jobs | process kill/restart/replay, lease expiry, duplicate attachment, 1 evidence→1 logical draft, ownership and unsupported formats |
| G7 | UI/API + reproducible CI | effective route matrix; actual frontend build or explicitly accepted maintained static UI; browser E2E for accountant/reviewer/CFO/admin |
| G8 | commercial/pilot acceptance | expire/renew/suspend/quotas, support and cost monitoring, finance/security/ops sign-off, explicitly approved pilot scope |

Existing required regression: full backend + smoke, PG15 and PG16 matrix,
Redis7 shared quota, real Chroma/ONNX if touched, tenant membership/vault/RLS,
PR127 reporting and PR84 snapshots. Document-only assertion tests are not a
substitute for runtime tests. Financial/legal policy sign-off and provider
connectivity cannot be inferred from mocks. No P0 may remain open at release.

## 7. შესრულების ჟურნალი

| ნაბიჯი | შედეგი | მტკიცებულება |
|---|---|---|
| Chat179 baseline | last confirmed full CI | 8,257 backend PASS / 3 SKIP; PG15/16 412 each; Chroma/ONNX 43; deploy/build SKIPPED |
| Chat180 plan | source/roadmaps/main/PR ancestry reviewed; matrices and gates defined | baseline inventory; exact source SHA above |
| Chat180 stage 1 | stored-line validation, Decimal and trial tenant/date repaired | `af537f8917864120d347c87fcb1a6ef71dd52408`; backend 8,276 PASS / 3 SKIP; PG15/16 432 each; all 9 CI workflows PASS |
| Chat180 stage 2 | transaction-bound READ COMMITTED cooperative source lock; autocommit/stale snapshots refused | `a91b50f60281600edc8c8d4a79f925e9369384ad`; backend 8,277 PASS / 3 SKIP; PG15/16 437 EACH; all 9 CI PASS; DB uniqueness remains open |
| Chat180 stage 3 | signed ERP memory/import scope, write RBAC, redaction and demo isolation; incomplete live history adapter fails closed | `da32bac9ce1a8c461f63823adcaec6c5b9e4adb7`; backend 8,319 PASS / 3 SKIP; PG15/16 480 EACH; all 9 CI PASS |
| Chat180 stage 4 | incomplete official cashflow refused; missing/malformed CFO cashflow stays null, verified zero stays zero | `23811088fd116ce8ae4d5973c177820fc1580b44`; backend 8,331 PASS / 3 SKIP; PG15/16 492 EACH; real reporting fixture + all 9 CI PASS |

ყოველი ეტაპი განაახლებს ამ ჟურნალს, ტექნიკურ ანგარიშსა და სრულ **პირად**
Master Handoff-ს. GitHub-ში ინახება მხოლოდ სანიტიზებული გეგმა/კოდი/ანგარიში;
ხელმისაწვდომი private handoff სრულ ისტორიას ინარჩუნებს.

აკრძალულია ცალკე თანხმობის გარეშე: merge, Production deploy/config,
რეალური DB migration და Windows ორიგინალების შეცვლა. ეს შეზღუდვები არ
აჩერებს უკვე ნებადართულ Draft corrections/isolated tests-ს.


## 8. ამ checkpoint-ის შემდეგი უსაფრთხო სამუშაო

ოთხი დასრულებული ცვლილება საერთო V1 მიღებას არ ნიშნავს. შემდეგი ყველაზე
მაღალი ფინანსური რისკია FIN-05: GEL-ით დასათაურებული ანგარიშები ჯერ raw
foreign-currency debit/credit-ს აჯამებს. ჯერ შექმენით failing real-PG
mixed-currency მაგალითი, გადაამოწმეთ amount_gel/ორიგინალი posting FX/
rounding და ყველა P&L/BS/TB/CFO/AI reader; rate=1 ან ახალი კურსი არ გამოიცნოთ.
ასევე შეამოწმეთ stored functional-currency debit/credit-ის სენტების ბალანსი.

შემდეგ FIN-04/06/11/12: უცნობი/ისტორიული account_type-ის დაკარგული თანხები,
DB source uniqueness და immutability, close-vs-post races, ERP receipt/outbox.
FIN-08 retained result/equity და COM-01 subscription lifecycle რჩება ღია.
Live history adapter, frontend E2E, runtime RLS/backup/recovery/region/provenance
კვლავ საჭიროებს შესაბამის მტკიცებულებას. Provider API-ს ნამდვილ ხელშეკრულებას
ვერ დაამტკიცებს synthetic stub; Production readiness ამ ეტაპზე HOLD-ია.

Review-ის bounded source ranges, ყოველგვარი ისტორიის გადაწერის გარეშე:

| ცვლილება | exact compare range | დამოუკიდებელი შემოწმება |
|---|---|---|
| Stored cents / reader tenant+DATE | `c215adb..af537f8` | invalid-before, Decimal, rounded lines, PG15/16 writer→report |
| Cooperative source concurrency | `af537f8..a91b50f` | eight simultaneous PG connections, A/B, rollback, isolation/autocommit |
| ERP memory tenant / demo safety | `a91b50f..da32bac` | signed route guard, read-vs-write, actual sync helper + nonowner FORCE-RLS |
| Incomplete cashflow / CFO null | `da32bac..2381108` | unknown movement, complete zero, malformed/unavailable, real report period fixture |

ეს ranges cumulative Draft-ის მცირე review-ებად წაკითხვის საშუალებას იძლევა;
ცალკე stacked PR-ები ჯერ არ შექმნილა და main-ზე არაფერი ინტეგრირებულა.


## Chat181 — FIN-05 მიმდინარეობს

საწყისი HEAD `81d2150e0efc5e15b35db9358d1c35459d18b616` და ოთხივე
მიმაგრებული ფაილი/ZIP manifest გადამოწმებულია. Isolated regression commit
`28794b0e63dfc3cb548efe93c4a7dde6e41134fe`: PG15/16 14 FAIL /492 PASS EACH;
რეალურად 120 გამოჩნდა სწორი310GEL-ის ნაცვლად. ეს არის ტესტის მტკიცებულება,
არა production failure ან release candidate.

Draft candidate უკვე ერთ stored functional basis-ს იყენებს P&L/BS/CF/TB-ში;
unknown/invalid FX და legacy foreign totals unavailable-ია, არა guessed GEL.
GEL-rate1 და functional-rounded balance ინვარიანტები writer-ზე დგას.
Stage1 exact-SHA `547ba514cd1a60a48453df58d06b7ba4545f3673`: all9CI PASS; backend8344/3SKIP; PG15/16 514EACH. შემდეგ დამოუკიდებელი P0 არის posting-rate
lookup-ში static fallback/source/date provenance, შემდეგ FIN-04 unknown COA.
მთავარი გეგმის ზემოთ მოცემული ისტორიული ჩანაწერები არ წაშლილა.


### მიმდინარე ნაბიჯი — 2026-10-30

ზემოთ Chat180 section8 ინახება როგორც ისტორიული checkpoint; მიმდინარე
შემდეგი ნაბიჯი ეს Chat181 ჩანაწერია. Stage1 უკვე დადასტურებულია. Stage2
კეტავს posting-ის hardcoded FX fallback-ს (3 failing-before რეგრესია),
ასწორებს DATE binding-ს და ინარჩუნებს ზუსტ8decimal posting rate-ს.
Stage2 `5ef73cddcc1e3bea85d522dd7de76113d6ea01eb`: all9CI PASS; backend8351/3SKIP; PG15/16 522EACH. შემდეგი დამოუკიდებელი საკითხია FIN-04:
NULL/unknown/contradictory account_type-მა ოფიციალური თანხები არ უნდა დამალოს.
FX quote provenance/freshness და report-output precision ჯერ ღიაა.


### FIN-04 candidate

Test-only `12eac81133761adf27c036c1528a89a2756fc334`: PG15/16 12FAIL/523PASS
EACH; NULL/alias შემოსავალი ნულად ჩანდა. Candidate იყენებს მხოლოდ არსებულ
canonical COA-ს runtime ინტერპრეტაციას, unknown/contradictory metadata-ს
არ მალავს, ყველა ოფიციალურ reader/AI/CFO-ს unavailable-ს აძლევს.
ისტორიული rows არ იცვლება. Writer და Bridge-authority preflight unregistered
account-ს აჩერებს. სრული tenant custom COA mapping ჯერ დასასრულებელია.
Exact candidate CI pending; production/V1 acceptance HOLD.
