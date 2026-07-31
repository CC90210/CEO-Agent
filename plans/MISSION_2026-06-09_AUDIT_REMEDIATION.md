---
tags: [plans]
last_updated: 2026-06-09
---

# MISSION BRIEF — AUDIT REMEDIATION V1
Business-Empire-Agent (CEO-Agent / Bravo) — 2026-06-09

> Saved verbatim by Bravo at mission start. The garbled audit-findings table from the
> original paste has been reconstructed into a readable form below; all facts preserved.
> This is the canonical reference doc — re-read after any context compaction, then resume
> from the first unchecked item in `plans/MISSION_2026-06-09_PROGRESS.md`.

CC: how to use this file.

Open a fresh Claude Code session in Antigravity, repo root, model Opus 4.8 (Sonnet 4.6 is acceptable for Phases 3, 7, 8, 9 only).
Paste this entire document as your first message. Say nothing else.
The agent will pause twice for your approval. Phase 1 needs you to type **GO PHASE 1**. Phase 4 needs **GO PHASE 4 — prod is current**. Everything else runs without you.
At the end you get a plain-English report and two copy-paste commands for your Mac and VPS.

---

## 0. WHO YOU ARE AND HOW YOU OPERATE ON THIS MISSION

You are Bravo, operating per CLAUDE.md, executing a remediation mission derived from an external architecture + security audit of this repository (performed against commit fa47807-era state, full 853-commit history scanned). This brief governs the mission. Where it conflicts with style preferences, this brief wins. Where it conflicts with brain/SECURITY_MODEL.md or brain/EXECUTION_RULES.md, those win — stop and report instead.

Your first three actions, before anything else:

1. Save this entire brief verbatim to `plans/MISSION_2026-06-09_AUDIT_REMEDIATION.md` (do not commit yet — Phase 0 handles git state).
2. Create `plans/MISSION_2026-06-09_PROGRESS.md` with a checklist of Phases 0–10, all unchecked.
3. Create a Todo list mirroring the phases. One phase in_progress at a time, ever.

Prime directives for this entire mission:

- **Evidence before claims.** Never state something about the repo from memory — run the command and look. Never report a phase complete without pasting the verification gate's actual output.
- **Read before edit.** Open and read any file (or the relevant region) before modifying it.
- **Trust the repo over this brief.** The audit was a snapshot. If a file, function, or line number named here has moved or changed, re-locate it with git grep, adapt, and log the delta in the progress file. Do not force the brief's assumption onto a repo that has evolved.
- **One phase, one commit (minimum).** Commit message format: `mission(remediation): phase N — <summary>`. Tag before starting each phase: `git tag mission-p<N>-start`.
- **Red means stop.** If a verification gate fails twice after honest fixes, roll that phase back (`git reset --hard mission-p<N>-start`), mark it BLOCKED in the progress file with the failing output, and continue to the next independent phase. Never push a broken state.
- **Secrets discipline.** Never print the contents of `.env*`, `.claude/mcp.json`, `state/secret_access.log*`, or any guard log into chat or any committed file. Reference them by name. When appending to `.env.agents`, append only — never echo the file.
- **Tool failure protocol.** If an MCP tool or integration fails twice, fall back to plain bash/python equivalents, note the fallback in the progress file, and keep moving. Silent skips are forbidden.
- **Context survival.** After any context compaction or new session, your first action is to re-read `plans/MISSION_2026-06-09_AUDIT_REMEDIATION.md` and the progress file, then resume from the first unchecked item.
- **Report in plain English.** CC is the founder, not an engineer. Every phase ends with the four-line report from §5. Jargon gets one-clause translations.

---

## 1. CONTEXT — WHAT THE AUDIT FOUND (verified facts you build on)

These were verified by direct inspection. Re-verify anything you depend on.

- **F1 — Prospect PII is public:** `memory/outreach_archive/` (7 files, ~40 business-owner names, 6 emails in `2026-03-02_leads_batch2.md`) and `data/email_suppressions.csv` (1 real Gmail) are tracked despite `.gitignore` rules — the files predate the rules, and gitignore never untracks. Evidence: `git ls-files memory/outreach_archive data/email_suppressions.csv`
- **F2 — `data/email_suppressions.csv` is a runtime dependency:** `scripts/casl_compliance.py:38` uses it as the legacy STOP-list tier of `should_suppress()`. Supabase table `email_suppressions` (migration 094) is authoritative; CSV read-errors fail closed by design. Evidence: `casl_compliance.py` docstring ~lines 180–200
- **F3 — `scripts/dashboard_email_consumer.py`** (PM2 app `dashboard-email-consumer`, `ecosystem.config.js:310`) sends to arbitrary `to_email` from a Supabase queue via `lib.smtp_send` / Gmail API with zero suppression or CASL checks — 0 grep hits for `suppress` / `casl`.
- **F4 — Guards default non-enforcing:** `scripts/state/exec_guard.py:161` → report; `secret_guard.py:110` → report; `state_guard.py:117` → off. No `EMPIRE_HOOK_*` overrides exist in `.claude/settings.json`.
- **F5 — Migrations:** 88 files, duplicate numeric prefixes at 030, 031, 037, 057, gaps elsewhere. `scripts/apply_migration.py` applies single files and has no per-file applied ledger (no `schema_migrations` table, no checksums). 12 migrations are non-idempotent backfills. Evidence: `ls database/`, `apply_migration.py`
- **F6 — Version drift:** `CLAUDE.md:1` says "BRAVO V6.0" (12 V6.0 refs), `CLAUDE.md:5` hardcodes "You are Claude Sonnet 4.6", `ANTIGRAVITY.md:1` carries a stale "(synced 2026-05-10)" stamp. Canonical current version per `CHANGELOG.md` is 6.8.3.
- **F7 — Routing-doc drift:** `brain/WHEN_TO_USE_SKILLS.md` mentions 35/149 skills; `brain/CAPABILITY_GRAPH.json` covers 149/149. `brain/INDEX.md` references 2 of 65 brain files. `memory/INDEX.md` + `memory/MEMORY_INDEX.md` are duplicate indexes whose targets mostly dangle in a fresh clone.
- **F8 — 88/810 wiki-links don't resolve** in a public clone — mostly gitignored targets (`memory/PATTERNS`, `MISTAKES`, `DECISIONS`, `APPS_CONTEXT/*`), plus cross-repo `../CMO-Agent/...` links, one literal `[[wikilinks]]` in `brain/CAPABILITIES.md`, and directory links in `brain/BRAVO_PRODUCT_ROADMAP.md`.
- **F9 — Brain freshness:** only 14/65 brain files carry `last_updated` frontmatter; 11 of those exceed their own thresholds, including `SECURITY_MODEL.md`, `EXECUTION_RULES.md`, `AGENT_ROUTER.md`, `WHEN_TO_USE_SKILLS.md`.
- **F10 — Hygiene:** 12 `VPS_*`/`MAC_*`/`MULTI_MACHINE_*` deploy prompts live in `brain/`; `SECURITY_ANTIGRAVITY_FIX_LOG.md` (machine forensics, ASR-in-AuditMode disclosure) sits tracked at root; `app/` is an empty breadcrumb dir (dashboard extracted 2026-05-18); `.gitignore` has duplicate patterns and a mojibake line ("Security �"). Note: `rules/` (datalog compliance) and `.rules/` (agent rules) are different things — do NOT merge them.
- **F11 — Git history is clean of real secrets** (verified across all 853 commits; only EXAMPLE- placeholders). No rotation needed. Do not "fix" this.

---

## 2. PHASES

### PHASE 0 — Preflight & Backup (no approval needed)
Why (plain English): before surgery, we photograph the patient and bank blood.

1. `git status` — if dirty, commit WIP as `wip: pre-mission snapshot` (or stash with a named stash and record it in the progress file).
2. Confirm branch is `main` and synced: `git fetch origin && git status` must show up-to-date or ahead; if ahead, `git push`.
3. Record state: `git rev-parse HEAD` → write into the progress file.
4. Full git backup outside the repo: `git bundle create ../BEA_backup_$(date +%Y%m%d_%H%M).bundle --all`
5. Local-only precious files backup (these are gitignored and would not survive a machine loss): create `../BEA_local_backup_<date>/` and copy into it: `.env.agents`, `.claude/mcp.json` (if present), `memory/` (entire dir), `state/` (entire dir), `data/pulse/`, `data/email_suppressions.csv`, `brain/USER.md`, `brain/operator.profile.json`. Verify the copies exist with `ls`. Do not print any file contents.
6. Verification gate: bundle file exists and `git bundle verify ../BEA_backup_*.bundle` passes; backup dir listing shown.

### PHASE 1 — PII History Purge 🔴 (GATE: wait for CC to type GO PHASE 1)
Why: real prospects' names and emails have been on a public repo since March. We remove them from every commit that ever existed, not just the latest one. This rewrites public history — the one genuinely dangerous operation in this mission — so it is isolated, backed up, and approved.

Before requesting GO, present CC this paragraph verbatim: "Phase 1 rewrites the public GitHub history to remove prospect data. After it runs: (a) your Mac and VPS clones will be out of sync until you run one command on each (I'll give it to you at the end), (b) if GitHub branch protection blocks force-pushes on main, you'll need to temporarily disable it in Settings → Branches, (c) anyone who already forked or scraped the repo still has the old data — this stops the bleeding, it doesn't unspill the milk. Type GO PHASE 1 to proceed."

Steps after GO:

1. Pre-checks in the working repo:
   - `git ls-files memory/outreach_archive data/email_suppressions.csv` — confirm targets are tracked; list them in the progress file.
   - `git grep -rn "outreach_archive" scripts/` — there is one reference in `scripts/core/self_audit.py`. Read it. If it only inspects the local directory (which survives as untracked files), no change needed; if it asserts the files are tracked, adjust it now and note the change.
2. Ensure local is fully pushed (`git push`), then build the rewrite workspace outside the repo:
   ```
   cd ..
   python -m pip install git-filter-repo
   git clone --mirror https://github.com/CC90210/CEO-Agent.git BEA_rewrite.git
   cd BEA_rewrite.git
   git filter-repo --invert-paths --path memory/outreach_archive --path data/email_suppressions.csv --force
   ```
3. Verify the purge inside the mirror (all three must return empty / 0):
   ```
   git log --all --oneline -- memory/outreach_archive
   git log --all --oneline -- data/email_suppressions.csv
   git log --all -S "goldstorm" --oneline
   ```
4. Push the rewritten history (filter-repo strips the remote on purpose):
   ```
   git remote add origin https://github.com/CC90210/CEO-Agent.git
   git push origin --force --all
   git push origin --force --tags
   ```
   If push is rejected for protection rules, stop and tell CC exactly which GitHub setting to flip, then retry.
5. Re-sync the working repo: `cd ../<repo> && git fetch origin && git reset --hard origin/main`. Reassure CC in your report: gitignored local files (`.env.agents`, `state/`, `memory/SESSION_LOG.md`, the CSV, the outreach files themselves) are untouched by this reset — they remain on disk as untracked files, now hidden by `.gitignore`.
6. Post-purge hardening commits (normal commits, in the working repo):
   - Append to `.gitignore`: `data/email_suppressions.csv` (it was never ignored — that's why it got committed) and verify `memory/outreach_archive/` rule still present.
   - Create `data/email_suppressions.example.csv` containing only the header row `email,reason,added_at` — so fresh forks have the schema.
   - Recreate `memory/outreach_archive/INDEX.md` as a sanitized stub: explain the archive is local-only operator data, schema of what lives there, zero names/emails.
   - Resilience patch: read `should_suppress()` in `scripts/casl_compliance.py`. Required behavior: CSV read error stays fail-closed (current design — correct, losing the STOP list is a CASL hazard); CSV file absent (fresh fork) must log a loud warning and fall through to the Supabase tier rather than crashing or silently failing closed forever. If current code doesn't distinguish absent vs unreadable, patch it so it does, and add a unit test for both cases in `scripts/tests/`.
7. Verification gate: the three history checks from step 3 re-run against origin after a fresh `git fetch` (empty); `git ls-files data/email_suppressions.csv` returns nothing; local CSV still exists on disk; new tests pass.

### PHASE 2 — Dashboard Email Compliance 🟠
Why: one daemon can email leads while skipping every legal/safety gate the rest of the system enforces. We make compliance live at send time, where it legally matters.

1. Read in full: `scripts/dashboard_email_consumer.py`, the public surface of `scripts/casl_compliance.py` (`should_suppress`, `build_casl_footer`, `build_casl_footer_html`), and how `send_gateway.py` classifies `intent="transactional"` vs commercial.
2. Implement, immediately before any send in the consumer:
   - Suppression: call `should_suppress()` for the recipient (respecting tenant/brand scoping if the queue row carries it). On hit: do not send; mark row status `suppressed`; log one structured line.
   - CASL footer: if the row is commercial/lead-facing (default to commercial unless the row is explicitly flagged internal/transactional — match the gateway's classification logic, don't invent a new one), ensure the CASL footer is present; append via the `build_casl_footer*` helpers when missing.
   - Preserve existing retry/failure semantics exactly.
3. Upgrade `scripts/email_doctor.py` check #5 so it is structural, not cosmetic: flag any file under `scripts/` importing `lib.smtp_send` or `smtplib` that is not on an explicit allowlist (`send_gateway`, `email_engine` if legitimately present, and the now-compliant `dashboard_email_consumer`). The allowlist lives at the top of email_doctor with a comment explaining why each entry is allowed.
4. New test file `scripts/tests/test_dashboard_email_consumer_compliance.py`: suppressed recipient → skipped + status set; commercial send without footer → footer appended; transactional/internal row → unchanged behavior. Mock the transport; never send real email from tests.
5. Verification gate:
   ```
   python -m pytest scripts/tests/test_send_gateway.py scripts/tests/test_dashboard_email_consumer_compliance.py -q
   python scripts/email_doctor.py
   ```
   Both green; doctor output pasted.

### PHASE 3 — Guard Enforcement 🟠
Why: the safety guards currently watch and take notes; they don't block. On a system that touches money and outbound email, watching isn't protection.

1. Review evidence first: scan `state/secret_guard.log` and `state/exec_guard.log` (do not paste contents — they may reference secret names; summarize counts only). Count would-block events in the last 14 days.
2. Set modes:
   - `secret_guard` → enforce (regardless of log noise — secret access should always be gated).
   - `exec_guard` → enforce if the 14-day would-block count is 0; otherwise leave report, and file the noisy patterns as a follow-up item in the progress file with a one-week soak plan.
   - `state_guard` → report (from off).
3. Apply in both places so every runtime sees them: an env block in `.claude/settings.json` (`EMPIRE_HOOK_SECRET_GUARD`, `EMPIRE_HOOK_EXEC_GUARD`, `EMPIRE_HOOK_STATE_GUARD`), and appended lines in `.env.agents` (append-only; never display the file). Mirror the same lines into `.env.agents.template` with comments so fresh installs inherit safe defaults.
4. Smoke-test each guard: invoke each guard module the way its hook does (read each file's `__main__` / entry function to learn the invocation) with the env var set, confirm the mode string it reports matches intent.
5. Update `brain/SECURITY_MODEL.md`'s description of default modes to match reality (this also feeds Phase 9).
6. Verification gate: smoke-test output for all three guards pasted; settings.json diff shown.

### PHASE 4 — Migration Ledger 🟠 (GATE: wait for CC to type GO PHASE 4 — prod is current)
Why: 88 database change-scripts with duplicate numbers and no record of what's been applied means one wrong re-run of a non-idempotent backfill could damage live data. We add a ledger instead of renaming files — renaming already-applied migrations is forbidden because nothing tracks them by content, and a rename invites a catastrophic re-apply.

Before requesting GO, ask CC to confirm one thing in plain English: "Is the production Supabase database currently up to date with every migration in database/? If yes, type GO PHASE 4 — prod is current and I'll mark all 88 as already-applied in the new ledger. If unsure, say so and I'll generate a checklist instead of assuming."

Steps after GO:

1. Read `scripts/apply_migration.py` end to end. Learn its `exec_sql` RPC pattern and CLI shape.
2. Create `database/100_schema_migrations_ledger.sql`: a `schema_migrations` table — `filename text primary key, sha256 text not null, applied_at timestamptz default now(), applied_by text`. Idempotent (create table if not exists). RLS posture consistent with other internal tables (check how migration 094 handles it and match).
3. Extend `apply_migration.py`: before applying, check ledger by filename; warn-and-require `--force` if filename present with a different checksum; after a successful apply, insert/update the ledger row. Keep the existing CLI contract intact; add `--status` to print applied vs pending by comparing `database/*.sql` to ledger rows.
4. Backfill: apply 100 itself, then insert ledger rows (filename + current sha256) for all existing migration files, `applied_by='mission-remediation-backfill'`.
5. Ordering rule, documented in `database/MIGRATION_NOTES.md`: ordering is lexicographic by filename; duplicate numeric prefixes (030/031/037/057) are historical and harmless under lexicographic order; never renumber an applied migration; new migrations start at the next free integer ≥ 101.
6. Verification gate: `python scripts/apply_migration.py --status` output pasted showing 89 applied (88 + the ledger migration), 0 pending.

### PHASE 5 — Version Single-Sourcing + Entry-Point Parity Test 🟠
Why: the version currently lives in five headers and a changelog, and they disagree (V6.0 vs 6.8.3). One source, one test, drift becomes impossible.

1. Determine canonical version: `CHANGELOG.md` top released entry (currently 6.8.3). This mission itself will ship as 6.9.0 — add the [6.9.0] CHANGELOG entry in the final phase, not now.
2. Make `brain/STATE.md` the single source: ensure it carries a machine-readable line/frontmatter key `architecture_version: V6.8.3` (read STATE.md first; integrate with its existing structure rather than bolting on).
3. Fix the five entry points (CLAUDE.md, GEMINI.md, ANTIGRAVITY.md, AGENTS.md, OPENCODE.md):
   - Headers/stamps reference the canonical version (update the stale V6.0 titles and the 12 stray V6.0 refs in CLAUDE.md where they denote current version — leave historical mentions that genuinely describe the V6.0 era).
   - Delete the "(synced 2026-05-10)" stamp from `ANTIGRAVITY.md:1`.
   - Replace `CLAUDE.md:5`'s "You are Claude Sonnet 4.6" with model-agnostic phrasing consistent with GEMINI.md's "identity is agent-first, not model-driven" doctrine.
4. Create `scripts/tests/test_entrypoint_parity.py` asserting: all five files exist; each contains the exact `architecture_version` string from `brain/STATE.md`; each references CONTEXT.md; and every block wrapped in `<!-- LOCKSTEP:<name> --> ... <!-- /LOCKSTEP:<name> -->` markers is byte-identical across all five files (Phase 8 adds the first such block — write the test to pass with zero blocks present too).
5. Verification gate: parity test green; `grep -c "V6.0" CLAUDE.md` shown before/after.

### PHASE 6 — Generate Routing Docs From the Graph 🟠
Why: CAPABILITY_GRAPH.json is the only artifact with 100% coverage. Hand-written maps drift; generated ones can't.

1. Read `scripts/build_capability_graph.py` to learn the graph schema.
2. Add an `--emit-docs` mode that regenerates, each topped with `<!-- GENERATED by scripts/build_capability_graph.py --emit-docs — do not hand-edit -->`:
   - `brain/WHEN_TO_USE_SKILLS.md` — all 149 skills: name, trigger summary, one-line "use when". Preserve any hand-written preamble above a `<!-- GENERATED-BELOW -->` marker if you choose to keep curated intro text.
   - `brain/INDEX.md` — every `brain/*.md` file, categorized, with its first heading as the description.
   - `memory/INDEX.md` — same treatment for memory; convert `memory/MEMORY_INDEX.md` into a three-line pointer to `memory/INDEX.md` (do not delete it — inbound wiki-links reference it).
3. Add `scripts/tests/test_generated_docs_fresh.py`: regenerate into a temp dir, diff against committed versions, fail on mismatch. This makes staleness a test failure forever.
4. Verification gate: generator runs clean; freshness test green; skill row count in WHEN_TO_USE_SKILLS.md ≥ 149 (show the count).

### PHASE 7 — Wiki-Link Integrity 🟡
Why: a fresh clone (or your own agent after a re-clone) currently meets 88 dead links in its own brain. The graph should load whole.

1. Ship template stubs following the existing `SESSION_LOG.template.md` pattern: `memory/PATTERNS.template.md`, `memory/MISTAKES.template.md`, `memory/DECISIONS.template.md` (schema + one example entry each, zero real data). Add an `APPS_CONTEXT/README.md` explaining that directory is local-only, with a `.gitignore` negation `!APPS_CONTEXT/README.md`.
2. Fix the genuinely broken links: the literal `[[wikilinks]]` in `brain/CAPABILITIES.md`; directory links in `brain/BRAVO_PRODUCT_ROADMAP.md` → point at the dirs' INDEX/SAFETY files; mark cross-repo links (`../CMO-Agent/...`, `../CFO-Agent/...`) with a consistent `(sibling repo)` suffix convention.
3. Create `scripts/tests/test_wiki_links.py`: every `[[target]]` in tracked .md files must resolve to (a) a tracked file, (b) a tracked `<name>.template.md`, or (c) carry the `(sibling repo)` marker. Print unresolved links on failure.
4. Verification gate: link test green; report the before/after broken count (was 88).

### PHASE 8 — Hygiene + the LOCKSTEP Discipline Block 🟡
Why: clear the clutter, and install the durable fix for "the agent forgets its tools and makes CC do too much."

1. Moves (update all inbound wiki/md links you find via `git grep` for each basename before moving):
   - `git mv docs/deploy/VPS_*.md docs/deploy/MAC_*.md docs/deploy/MULTI_MACHINE_PAIRING_PROMPT.md docs/deploy/`
   - `git rm SECURITY_ANTIGRAVITY_FIX_LOG.md` — first copy it to `../BEA_local_backup_<date>/` so CC keeps the record. (It stays in old git history; that's acceptable — it's low-sensitivity. Note this in the report.)
   - Delete `app/` after appending its breadcrumb (dashboard extracted 2026-05-18 → new repo URL, read it from `app/README.md`) into `brain/APP_REGISTRY.md`.
   - Do not touch `rules/` (datalog compliance — different animal from `.rules/`) or `templates/` vs `_templates/` (different purposes).
2. `.gitignore` cleanup: dedupe repeated patterns (`*.pt`, `*.pth`, `*.key`, `*.pem`, `tmp/` appear twice), fix the mojibake line `# Security � key...` → `# Security — key and certificate files`.
3. Insert the LOCKSTEP block from §4 below, byte-identical, near the top of all five entry points (immediately after each file's identity preamble), wrapped exactly in `<!-- LOCKSTEP:tool_discipline -->` / `<!-- /LOCKSTEP:tool_discipline -->`.
4. Verification gate: `pytest scripts/tests/test_entrypoint_parity.py scripts/tests/test_wiki_links.py -q` green (parity now validates the block ×5); `git status` clean after commit.

### PHASE 9 — Brain Freshness Sweep 🟡
Why: the freshness system exists but covers 20% of the brain. Memory you can't date is memory you can't trust.

1. For the 51 `brain/*.md` files lacking frontmatter: add YAML frontmatter with `last_updated: 2026-06-09` and `freshness_threshold_days:` (30 for operational docs, 90 for stable reference like SOUL.md, CEO_OPERATING_SYSTEM.md — use judgment, note choices). Insert without disturbing content; if a file already has frontmatter missing only these keys, add the keys.
2. For the 11 stale files: actually skim each against current reality. `SECURITY_MODEL.md` gets a real review — it must now describe enforce-mode guards (Phase 3) and the dashboard-consumer compliance (Phase 2). Others: update what's wrong, or bump the date with a `verified: 2026-06-09` note if accurate.
3. Add `scripts/check_brain_freshness.py` (reporting tool, not a failing test): prints files past threshold. Add one line to `PLAYBOOK.md` wiring it into the existing heartbeat/daily routine wherever that lives.
4. Verification gate: `python scripts/check_brain_freshness.py` output pasted showing 0 stale.

### PHASE 10 — send_gateway Decomposition 🟡 (OPTIONAL — strongly recommend a fresh session after Phases 0–9 are merged and stable for a day)
Why: 163KB in one file is a maintenance hazard, but refactoring the money path in the same breath as nine other changes is how outages happen. Mechanical move only, zero behavior change.

1. Baseline: run `python -m pytest scripts/tests/test_send_gateway.py -q` and record the exact pass count.
2. Convert `scripts/integrations/send_gateway.py` into package `scripts/integrations/send_gateway/` with `__init__.py` re-exporting the identical public API (`send`, the CLI entry, every name other modules import — find importers first: `git grep -ln "send_gateway" scripts`). Split internals into `gates.py`, `transports.py`, `policy.py`, `cli.py` along the existing section boundaries. Move code; do not "improve" it.
3. Gate: the 88KB test file passes unmodified with the identical pass count; `python scripts/email_doctor.py` green; one importer smoke-tested.

---

## 3. FINAL PHASE — Full Verification, Ship, Report

1. Run the whole battery and paste outputs:
   ```
   python -m pytest -q
   python scripts/email_doctor.py
   python scripts/scan_secrets.py
   python scripts/check_brain_freshness.py
   python scripts/build_capability_graph.py --emit-docs && git diff --stat
   git grep -c "goldstorm" || echo CLEAN
   ```
2. Add the [6.9.0] entry to `CHANGELOG.md` summarizing this mission; set `architecture_version: V6.9.0` in `brain/STATE.md`; confirm parity test still green (entry points reference the canonical source, so this should be a 1-file bump — if it isn't, your Phase 5 wiring is wrong; fix it).
3. Write `memory/RETROSPECTIVE_2026-06-09_audit_remediation.md` following the style of the existing 2026-05-14 retrospective: what changed, what was deliberately deferred (Phase 10 if skipped, exec_guard soak if applicable), lessons.
4. `git push`. Update the progress file: all boxes checked or explicitly BLOCKED-with-reason.
5. Deliver the final CC report (§5 format), ending with the manual actions block:
   - Mac + VPS, one command each: `git fetch origin && git reset --hard origin/main` (explain: local secrets/state survive because they're gitignored).
   - If exec_guard stayed in report: the one-week soak plan and what "clean log" means.
   - Optional: GitHub Support can purge cached views of the old commits if CC wants belt-and-suspenders on the PII removal.

---

## 4. THE LOCKSTEP BLOCK (insert verbatim in Phase 8, all five entry points)

```markdown
<!-- LOCKSTEP:tool_discipline -->
## Tool & Verification Discipline (non-negotiable)

1. **Evidence before claims.** Never assert repo/system state from memory. Run the command, read the file, then speak. "I believe" is banned where `grep` can answer.
2. **Read before edit. Verify after edit.** Every modification is followed by its proof: the test run, the lint, the command output. No proof → not done.
3. **Track multi-step work visibly.** Three or more steps → maintain a Todo list. Exactly one item in_progress at a time. Update it in real time, not retroactively.
4. **Tool failure ≠ task failure.** If an MCP/tool call fails twice, fall back to bash/python equivalents and say so. Silently skipping a step because a tool was flaky is the worst failure mode in this system.
5. **Never end a work session without the four-line report:**
   - **Changed:** what was modified (paths).
   - **Why:** one plain-English sentence per change.
   - **Proof:** the verification command + its actual output.
   - **Needs from CC:** specific asks, or "nothing."
6. **Plain English to CC, always.** CC is the founder. Translate jargon in one clause. If CC must make a decision, give a recommendation plus the one-sentence tradeoff — never an unranked list of options.
7. **Definition of done:** the verification gate passed and its output is in the report. Anything else is "in progress," and you say so.
<!-- /LOCKSTEP:tool_discipline -->
```

---

## 5. CC REPORT TEMPLATE (end of every phase + final)

```
PHASE <N> — <name>: ✅ DONE / ⛔ BLOCKED
Changed: <files / systems touched>
Why: <one sentence per change, plain English>
Proof: <verification command + pasted output>
Needs from CC: <specific ask, or "nothing">
```

---

## 6. WHAT CC PERSONALLY MUST DO (everything else is the agent's job)

- Type **GO PHASE 1** when asked (and flip GitHub branch protection off/on if the push is rejected).
- Type **GO PHASE 4 — prod is current** only if the live Supabase really has every migration applied; say "unsure" otherwise.
- After the final report: run the one re-sync command on the Mac and the VPS.

---

## 7. ROLLBACK PLAYBOOK

- Any phase: `git reset --hard mission-p<N>-start` (tags were set in §2 rules).
- Catastrophic: restore from the bundle — `git clone ../BEA_backup_<date>.bundle restored && cd restored && git remote set-url origin https://github.com/CC90210/CEO-Agent.git`.
- Phase 1 specifically: the bundle contains pre-rewrite history; force-pushing it back restores the old public state (including the PII — only do this if something truly broke, then re-run the purge).
- Local-only files: copies live in `../BEA_local_backup_<date>/`.

End of mission brief.

## Obsidian Links
- [[brain/STATE]]
- [[memory/INDEX]]
