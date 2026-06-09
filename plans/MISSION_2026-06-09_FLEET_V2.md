# MISSION — FLEET HARMONIZATION V2 (Bravo @ fleet scope)
Saved verbatim by Bravo at mission start, 2026-06-09. Constitution = V1 brief
`plans/MISSION_2026-06-09_AUDIT_REMEDIATION.md` §0 (prime directives) + §2 (phase rules).
Resume rule: after compaction/new session, re-read this + `..._FLEET_V2_PROGRESS.md`, resume at first unchecked item.

## 0. GOVERNING RULES
Bravo at fleet scope. V1 §0 + §2 apply. Fleet deltas:
- **First actions:** save this brief; create `..._FLEET_V2_PROGRESS.md`; build Todo list. (done)
- **Per-repo isolation.** Never uncommitted changes in two repos at once. Finish-commit-push (or rollback) in one repo before touching the next.
- **Clone what's missing.** `git clone https://github.com/CC90210/<repo>.git`. Private/absent → mark SKIPPED, continue.
- **Trust repos over brief.** Re-locate moved things; log deltas.
- **Four-line report** after every phase (V1 §5 template).

## 1. CONTEXT — FLEET SCAN (verified 2026-06-09)
V1 (CEO-Agent) 6.9.0 confirmed shipped; LOCKSTEP ×5; portable tests pass on cold clone (~0.19s). One genuine miss → Phase 1.

Repo classes + findings (evidence-checked):
- **CEO-Agent** (Agent/Bravo): 🔴 residual lead PII — purge was path-keyed; lead names ([REDACTED]/[REDACTED] cluster, 2026-03-02 batch) survive in HEAD `memory/daily/2026-03-02_execution_log.json` + history blobs (`docs/[REDACTED]_ROI_Analysis.md`, `memory/ARCHIVES/sessions-2026-03.md`, old SESSION_LOG/LONG_TERM commits). 🟡 `data/email_suppressions.csv` tracked AND gitignored (contradiction). 🟡 V1 deferred queue open. 22 `refs/pull/*` still carry pre-rewrite history.
- **SunBiz-Agent** (Solara/Helios; agent+client product): 🟠 `.claude/mcp.json` + `.vscode/mcp.json` tracked (env-ref, no literal secrets). 🟡 1 test for an email-sending system. No LOCKSTEP. CSVs clean (public/fixture).
- **CFO-Agent (Atlas)**: 🟠 `.claude/mcp.json` tracked (no literals). 27 tests + CI. No LOCKSTEP.
- **CMO-Agent (Maven)**: 🟠 mcp.json ×2 tracked (no literals). 🟠 no CI. 12 tests. 46MB tree (vendored vendor/copycat). No LOCKSTEP. Sends email → compliance surface.
- **hermes** (commerce agent): healthy (brain/, 16 tests, CI). No LOCKSTEP.
- **Aura-Home-Agent**: harness docs + CI, 0 tests. No LOCKSTEP.
- **oasis-command-center** (product/dashboard): healthiest — 28 tests, CI, redaction libs, no tracked env (only sk_live_ hit = fake fixture). 🟠 no agent onboarding doc (no CLAUDE/AGENTS.md). ❓ visibility decision (§6.2).
- **oasis-ai-platform** (product, legacy?): 🟠 hardcoded Supabase JWT + project ref (`src/lib/supabase.ts:7`, `src/pages/portal/TestConnection.tsx:8`); decoded role=anon (no emergency) but kills rotation. ❓ live or superseded (§6.3).
- **real-estate-App (PropFlow)**: CI + 3 tests + CLAUDE.md. Wave-B candidate.
- **kli-hub-dashboard** (dormant): 🟡 `prisma/dev.db` tracked (verified empty). Untrack. No CI.
- **gritly · tiktik · ig-setter-pro · nostalgic-requests · cc-funnel · shopify-ad-engine · grapevinecottage** (dormant): no CI/tests/harness mostly. Triage Phase 7.
- **Life-Preservation** (personal): out of scope; hygiene scan only.

Pattern: LOCKSTEP in exactly 1 repo; CI in 7/18. V2 makes the substrate the continent.

## 2. V2 ARCHITECTURE
Reject copy-paste-across-repos (recreates drift at fleet scale). Instead:
- **empire-harness** — new private repo = single source of universal substrate: LOCKSTEP block, 4 portable drift tests, checkers, guard conventions, CI template, PII sweep, scaffold generator, `harness_sync.py`. Each repo pins `HARNESS_VERSION` + one test failing on checksum mismatch. Fleet upgrade = bump core → sync each → tests prove.
- **fleet_doctor.py** — one command, plain-English health table per repo (tests/parity/freshness/secrets/guards/CI/last-commit). How CC notices the difference; prototype of a product feature (harness-health panel in command-center for client agents). CLI-first.
- **new_agent.py** — stamps a new client/vertical agent repo hardened on day one (entry points+LOCKSTEP, brain skeleton, tests, CI, guards, gitignore).
- **Content-keyed PII sweeps** — `pii_sweep.py`; sweep by operator-adjudicated strings, never paths alone (goldstorm lesson).
- **FLEET.md** — manifest in empire-harness: repo, class, visibility decision + owner, harness version, doctor status.

## 3. PHASES
- **P0 Fleet Preflight:** verify each repo exists locally + clean; clone missing; record HEADs. Bundle-backup every repo to be modified. `gh auth status` (authed → I create repos/PRs; else CC click §6.1). Gate: bundle list + HEAD table.
- **P1 CEO-Agent residual PII (content-keyed) 🔴 GATE:** build candidate-string list (provenance each; incl [REDACTED]/[REDACTED] + leads_batch2 names); present to CC "REAL LEAD / MY DATA / UNSURE(purge)"; on GO: fix HEAD (scrub/redact `memory/daily/2026-03-02_execution_log.json`) commit; history pass in mirror (`filter-repo --replace-text` + `--invert-paths` for whole lead docs); verify `git log --all -S` =0; force-push; resync. Resolve CSV contradiction (`git rm --cached`, ensure example, casl tests pass). Write `pii_sweep.py` (+`--emails-heuristic`, `--rewrite`); test on CEO post-purge (0 hits). Gate: clean sweep pasted.
- **P2 Build empire-harness:** create repo (gh or CC §6.1); populate blocks/ tests/ tools/ scaffold/ ci/ FLEET.md VERSION(1.0.0), extracting from CEO-Agent. Gate: pytest -q green inside empire-harness; pushed.
- **P3 CEO-Agent adopts core (dogfood):** `harness_sync.py --apply`; LOCKSTEP stays in 5 entry points but parity also compares to core canonical. Gate: CEO pytest ≥ V1 count; sync --check clean; push.
- **P4 Sibling adoption Wave A (SunBiz→CFO→CMO→hermes→Aura):** per repo isolated: backup; mcp.json hygiene (rm --cached, gitignore, .template, history credential check — STOP+gate if real cred ever in history); harness_sync --apply (LOCKSTEP, portable tests, importlib, CI, HARNESS_VERSION); guard modes; repo-specific deep item (SunBiz email send-surface compliance + tenant scoping; CFO `brain/FINANCIAL_ACTIONS.md` money-gate enumeration; CMO email compliance + vendor footprint proposal; hermes/Aura sync+freshness, Aura first smoke test). Gate per repo: tests green, sync --check clean, CI present, pushed.
- **P5 oasis-command-center (GATE §6.2 first):** apply visibility decision; write CLAUDE.md+AGENTS.md (product-flavored, LOCKSTEP); verify no tracked env, redaction tests green, RLS posture → `docs/SECURITY_POSTURE.md` (flag tenant table w/o RLS, don't fix schema). Optional `app/api/fleet-health` stub. Gate: tests green; pushed.
- **P6 oasis-ai-platform disposition (GATE §6.3):** superseded → archive + README banner. Live → move URL+anon key to env, delete hardcoded pair, verify RLS, document. (Anon keys ship to browsers; sin = hardcode+no rotation, not apocalypse — calibrate.)
- **P7 Dormant tier + fleet_doctor live:** untrack `kli-hub-dashboard/prisma/dev.db` (+gitignore); `fleet_quick_audit.py` across dormant → FLEET.md + ARCHIVE/KEEP/MINIMAL-HARDEN proposals (execute only zero-risk gitignore fixes; archiving = CC list); Life-Preservation hygiene scan only (private to CC). Run `fleet_doctor.py` across everything; paste table (proof-of-difference).
- **P8 CEO deferred queue (small only):** bridge windowless flags (4 `subprocess.run` ~110/2299/2567/2590, verify bridge starts); ~6 bare `from send_gateway import`→`integrations.`; mock `reserve_send_slot` so 4 tests green offline (+ `@pytest.mark.live` skip). send_gateway decomposition STAYS OUT (V2.1). Gate: CEO pytest -q fully green offline.
- **FINAL:** FLEET.md finalized + committed; all repos pushed; bundles listed. CEO CHANGELOG [6.9.1] fleet harmonization; empire-harness tagged v1.0.0. Final report: fleet_doctor table + per-repo four-liners + CC manual-actions block.

## 4. CC DECIDES (only four)
1. Repo creation (if gh not authed): click New repo → empire-harness, private.
2. oasis-command-center visibility: rec = private (it's the product). Public → RLS audit becomes blocking.
3. oasis-ai-platform: live or dead (one word) → decides P6 branch.
4. PII adjudication for P1 (mark list) + dormant archive checklist later. Plus standing `.env.agents` guard-mode lines per machine if V1 item 3 undone.
Also open from V1: 22 `refs/pull/*` on CEO-Agent (GitHub Support ticket or accept).

## 5. fleet_quick_audit.py SPEC (build P2)
Per repo one block: tracked-file count · stack signals (next.config*/pyproject) · tests count (test_*.py,*.test.*,*.spec.*) · CI (.github/workflows/*) · harness markers (CLAUDE/AGENTS/LOCKSTEP/brain) · tracked-sensitive filenames (.env* non-template, mcp.json non-template, credentials*, *.pem/key/p12, *.db/sqlite) · tracked .log/.csv · secret-pattern hits (Stripe sk_live_/sk_test_/whsec_, Google AIza, JWT eyJhbGciOi…, Slack xox?-, GitHub ghp_/github_pat_, private-key headers, postgres://user:pass@, Telegram \d{8,10}:AA…, AWS AKIA, SendGrid SG., Resend re_, Firecrawl fc-, OpenAI sk-proj-, Anthropic sk-ant-) — file:line + first-14-char mask, never full values · distinct third-party-ish emails (exclude example/noreply/own-domain/common-prefix). `--json` for fleet_doctor. `--deep`: unshallow + pickaxe history.

## 6. ROLLBACK
V1 §7 machinery: per-phase tags per repo, bundles outside repos, filter-repo only in throwaway mirrors until explicit push. Phase isolation = independent restore.
