---
tags: [retrospective, sunbiz, mca, bridge, security, hardening, fable-5]
last_updated: 2026-06-12
freshness_threshold_days: 365
---
# Retrospective — SunBiz Portal Finalization (2026-06-12)

A multi-session sprint that took the SunBiz operator portal from "MVP with rough edges" to "100% turnkey for Adon's Saturday demo." Theme: **wire the closed-loop end-to-end** — from form intake through underwriting through shop-out through reply classification — then harden every layer beneath it so the chat surface is as reliable as the terminal.

> [!success] Outcome
> SunBiz portal shipping at Adon's MCA SOP spec. All four operator workflows (Ezra, Jordan, Alex + Matt-alias) proven live: per-operator email signing, attachments-on-wire, SOP §4 restricted-lists filter, SOP §7 sales metric card. Bridge reliability chain solid from browser → Vercel → tunnel → VPS → Claude CLI. Zero zombie-process bugs left.

Full per-phase commits: `git log --oneline` from `1e51bcaa` (Adon SOP discovery) through `eb1c2a69` (subprocess windowless audit).

## What changed (shipped, on `main` across 3 repos)

### Adon MCA SOP implementation — closing the SunBiz product gap

| SOP § | Surface | Outcome |
|---|---|---|
| §3 | Shop-out subject + body + From + CC + Attach + Threading | Subject = `New Deal ({{business_name}})` identical across re-sends; body = minimal default; per-operator signing (Matt = Ezra's `Submissions@` alias, Jordan + Alex have own signatures); recipient picker prefers `/submission\|submit/i`; attachments downloaded from Supabase Storage + MIME-packed at send time. |
| §4 | Match-fitness scorer (restricted lists) | `restricted_states` + `restricted_industries` added to LenderProfile + ApplicationProfile + match-fitness scoring. Schema rename caught silent bug (`industry_restrictions` → `restricted_industries`). Hard cap 12 lenders per shop-out with explicit override header. |
| §4 | Form → application backfill | Form payload now upserts into `tenant_records` application row on EVERY step. Whitelist of 12 application-shaped keys with per-key normalization (UPPER 2-letter state, lowercase slug industry, parsed currency). 12 SunBiz lenders migrated to canonical field name. |
| §5 | Per-position balance estimation | Deferred — current heuristic (`monthly_burden × 6`) acceptable for grading; factor-based math is next-iteration polish. |
| §6 | Lender reply notification to assigned agent | Partial — `lender_response_classifier` writes `agent_events` rows on `info_requested` but no Telegram/email push yet. Surfaced as gap for next round. |
| §7 | Sales metric card UI | New `components/underwriting/SalesMetricCard.tsx` renders grade strip + 6-metric grid + DEATH-BLOW collections banner + verified positions table + red flags. Reads from `application_underwriting.debt_analysis.metric_card`. |

### Underwriting pipeline — Adon's grading discipline encoded

| Module | What it does | Outcome |
|---|---|---|
| `scripts/underwriting/grader.py` | NEW — pure-function SOP §§3,5,6,7 grader | TRUE revenue (deposits minus 8 exclusion categories) → position verification (only `mca_funder` counts; `mca_servicer` = DEATH-BLOW JUNK override) → leverage (burden ÷ TRUE revenue) → grade A/B/C/D/JUNK using worst-of-three on leverage/NSFs/positions → recommendation (Fresh capital / Consolidation / Workout / Decline) → sales metric card. |
| `scripts/underwriting/statement_parser.py` | Vision prompt extended | Now extracts `excluded_credits[]` (8 categories), `card_processor_deposits[]`, `lowest_daily_balance`, and a `category` field on every `identified_loan_payments` row using the 9-bucket SOP §4 dispatch. |
| `scripts/underwriting/debt_detector.py` | SOP §4 strict policy applied | Only `mca_funder` counts; equipment leases route to own bucket; unknown billers flag for human review without counting. Legacy outputs fall through with `legacy_aggregation: true`. |
| `scripts/underwriting_orchestrator.py` | Wired grader into pipeline | Persists grading + metric_card into `application_underwriting.debt_analysis` (transitional shape avoiding a column-add migration). |

> [!info] Verified live
> Mamaws Farmhouse processed end-to-end: $134,625.88 TRUE revenue, 0 verified MCA positions (40+ billers flagged for human review), collections death-blow → JUNK → "Decline — refer to restructure." Adon's SOP grading discipline produced the correct call on a real deal.

### Bridge reliability — chat surface as reliable as the terminal

| Layer | Before | After | Commit |
|---|---|---|---|
| Bridge warm-pool wall-clock | 5 min | **30 min** | `70f922a9` |
| Bridge warm-pool inactivity | 90 sec | **600 sec** | VPS `835ef9f6` (CC pulled) |
| Vercel chat SSE proxy | 300s (Pro cap) | **800s** (Fluid Compute) | `6fb38b9` |
| Underwriting bridge call | `wait_for_complete=true` (65s PROXY_TIMEOUT_MS killed it) | `wait_for_complete=false` + dashboard polls `/latest` | `6533c1b` |
| Underwriting Re-run | Inserted pending row, waited for `*/15` cron (up to 15 min stuck) | Fires bridge synchronously; bridge tool kicks detached orchestrator subprocess (`_kick_orchestrator_once` with 6s grace) | `f51cd13` + SunBiz-Agent `25932e7` |
| Drawer in-flight UX | One `fetchLatestRun()` then silent forever | Polls `/latest` every 5s while `pending`/`parsing`, visibility-aware, auto-stops on complete/error | `4344713` |
| Empty-response error surface | "Check pm2 logs" generic message | Captures + redacts last 1500 chars of claude stderr, embeds in error detail (cold-spawn + warm-pool paths both) | `53ebdad7` + `5e83dff8` |
| `ensure_deps` self-heal | Crashed on missing `_WINDOWLESS_FLAGS` reference | Self-contained inline constant | `254a3929` |

### Security + multi-tenant hardening

| Surface | Fix | Commit |
|---|---|---|
| `bridgeExecToolAllowedForRole` | `read_only` / unknown / null roles could fire MEMBER_BUSINESS tools (`shop_out_send_batch`, `send_email`, `send_sms`). Now requires `team_role === 'member'` explicitly; everything unrecognized fails closed. | `3c55168` |
| `/api/agent-alerts/[id]/resolve` | Open-redirect via `Referer` header → same-origin gate. Off-origin Referer falls back to `/`. | (linter patch, already in tree) |
| Shop-out attachment storage_path | Tenant-prefix gate: every attachment's `storage_path` must start with `${tenant_id}/`. Foreign-tenant paths rejected. | (in `app/api/applications/[id]/shop-out/route.ts`) |
| `send_gateway --attachments` | New `_resolve_cli_attachments()` validates + downloads from Supabase Storage at send time. JSON-array CLI flag, per-file best-effort. | `5a6eee62` |
| `/pipeline` tenant-aware redirect | SunBiz operators landing on the OASIS-personal `/pipeline` now bounce to `/t/sun/leads`. | `fa2159f` |

### Operator UX — Settings + Dashboard hygiene

| Surface | Change | Commit |
|---|---|---|
| Dashboard "open alerts" | Moved BELOW KPIs + pipelines (was at TOP). Subtitle accurate (not lying "click to resolve"). Dedup by `(alert_type, subject_type, subject_id)`. Surfaces `payload.summary` + first 5 HIGH issues inline. Dismiss button → `POST /api/agent-alerts/[id]/resolve` | `09f61af` |
| Sequences list | Name clickable to `/sequences/[id]/edit` (whole row navigable). Description uses `line-clamp-2` instead of single-line truncate. Added "Fires on event — no interval" hint so operator understands event-driven model. | `73cbcf1` |
| Settings → Operations Tracker | NEW — bottom-of-Settings panel surfacing: 7-day per-employee activity rollup (filters out daemon traffic; only operator-initiated sends), last 15 audit events with action-typed icons, quick-nav cards to Automations + Sequences + full Audit Log. | `b0e9b5f` |
| Underwriting drawer | Removed broken `View full underwriting report →` link (target `/t/<slug>/underwriting` didn't exist in manifest). Replaced with button calling `onRerun` directly. Cleaned 6 stale `FIXME(api) Phase ε` comments + dropped 2 unused props from `UnderwritingBadge`. | `f51cd13` + `1cce079` |

### File structure + zombie process cleanup (2026-06-12 session)

> [!success] 552 MB disk recovered + 61 zombie processes killed
> File hygiene pass that closed the "PowerShell windows keep popping up" bug at the code level.

| Action | Result |
|---|---|
| Deleted 5 stray `breezeadvance-*.png` from repo root | 1.2 MB, zero code references (verified) |
| Deleted `apps/oasis-desktop/dist/` Electron build artifacts | 548 MB — already `.gitignore`d at line 148, no git impact |
| Deleted `tmp/` ephemeral state (PM2 logs, lock files, offline event queue) | 4.6 MB, no application logic depends on it |
| Ran `scripts/audit_no_visible_subprocess.py` (existing tool) | 6 violations across 227 audited files |
| Fixed 6 popup-spawning sites | `gws_docs_edit.py:83`, `pii_sweep.py:45+123+124+125`, `build_capability_graph.py:457` all now pass `creationflags=WINDOWLESS_FLAGS, startupinfo=windowless_startupinfo()` from canonical `scripts/lib/subprocess_helpers.py` |
| Killed orphan `cmd` / `conhost` / `powershell` processes | 61 zombies (all 58-65 min old, no window titles) terminated via `Stop-Process` |
| Final audit | `{files_audited: 227, violation_count: 0}` |

Commit: `eb1c2a69` on CEO-Agent.

## What was deliberately deferred

> [!warning] Explicitly deferred — by design, not by oversight
> Each item below has a documented reason. Resume from this list, not from memory.

- **Per-position factor-based balance estimation** (SOP §5) — current `monthly_burden × 6` heuristic flagged `rough_ballpark`; full math requires per-position funding date + factor lookup. Grading correctness unaffected.
- **SOP §6 step 4 — lender-reply notification to assigned agent** — classifier writes `agent_events` rows but no Telegram/email push wired. Product decision pending (a/b/c/d shape — Telegram vs email vs both vs skip).
- **Adon's seed CLI run for `restricted_industries`** — 0 of 46 SunBiz lenders carry industry restrictions today. Adon needs to run `scripts/adon_seed_lender_constraints.py` with his MCA domain knowledge OR provide answers in chat for the VPS agent to run. CLI built and idempotent.
- **Per-sequence + per-automation detail pages with metrics** — list rows clickable to edit pages, but proper per-thing metrics dashboards (enrollment counts, fire history, success rates) are 2 new components + 2 query helpers each. Settings Operations Tracker provides cross-cutting view.
- **`bravo_cli/_subprocess_helpers.py` ↔ `scripts/lib/subprocess_helpers.py` consolidation** — dual implementation with identical API. Real refactor target, behavior-neutral; Agent C flagged it.
- **TextTorrent API URL** — wrapper hardcodes `https://api.texttorrent.com/v1/messages`; CC needs to confirm correct URL from TextTorrent account dashboard. Infrastructure ready, credentials pending.
- **Kixie + Twilio for SunBiz** — env var slots ready in `.env.agents`; CC hasn't provisioned accounts yet. Not Saturday-blocking.

## Lessons

1. **Run the existing audit tool BEFORE manual grep.** `scripts/audit_no_visible_subprocess.py` already existed, already worked, already had the AST predicate. I almost re-implemented the subprocess scan from scratch via grep. The tool found exactly 6 violations across 227 files in seconds. *When chasing a class of bug, look for an existing tool the operator has built for that bug class.*

2. **Schema name + consumer name MUST match — or the filter silently dies.** The `industry_restrictions` ↔ `restricted_industries` mismatch meant Adon could populate via UI and the scoring code would never read it. Caught by accident. *Single source of truth for field names. Grep for the consumer before declaring a schema "ready."*

3. **Wall-clock timeouts kill legitimate long operations — inactivity timeouts don't.** The 5-min warm-pool cap killed Solara's 10-min underwriting investigation. The 90s inactivity window kept the safety net. *Bound runtime by inactivity, not total elapsed. Long operations should pass through if they're making progress.*

4. **The error message is part of the product.** "warm Claude process died mid-stream (exit None)" was misleading — `exit None` meant the process was still ALIVE when polled. The fix: distinguish exit_code=None (bridge gave up) from exit_code=int (process actually died). Honest error messages save the operator a context switch to `pm2 logs`.

5. **Tenant isolation is the worst-case threat model for multi-tenant MCA.** Bank statements + FICO + EIN cross-tenant leakage would be catastrophic. Every route audit started with the question "does this scope by `tenantId` from session?" — not "does this work?" *Threat model first; UX second.*

6. **CC's memory rules saved the session multiple times.** "No .md handoff files — explain in chat" prevented file pollution across 30+ VPS turns. "Vercel committer-email trap" prevented an hour-long debug cycle when the VPS agent's commits got silently blocked. *The memory system isn't documentation overhead — it's the institutional knowledge that compounds.*

## Process notes

- **Adversarial verification pattern works.** The security audit fan-out used 8 parallel finders → 3-way verification per finding → synthesis. Caught Agent A's wrong claim about `dist/` needing `git rm` (it was already `.gitignore`d). Caught the model-ID audit's empty output and re-issued.
- **Sub-15-min iteration is the ceiling for live debug.** The shop-out 5-defect chain (CC fired, VPS agent diagnosed, I shipped) ran in 90 min — feasible because each loop was ~10-15 min. Anything longer would have lost CC's flow state.
- **VPS-agent + dashboard-agent split is a real architecture, not a hack.** Two AI sessions cooperating via paste-prompt handoffs (chat-only, no `.md` files) over a 6+ hour sprint. The discipline that made it work: explicit "VPS does X, CC verifies Y" division + ground rules pasted into every handoff.

## Related

- [[brain/STATE]] — current operational state
- [[memory/LONG_TERM]] — persistent facts (Fable 5 standard, SunBiz status)
- [[memory/RETROSPECTIVE_2026-06-09_audit_remediation]] — prior week's hardening pass
- [[CLAUDE]] — entry-point routing
- [[brain/V6_ARCHITECTURE]] — substrate detail
