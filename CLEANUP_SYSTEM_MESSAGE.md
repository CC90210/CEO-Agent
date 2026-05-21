# SYSTEM MESSAGE — Business-Empire-Agent Cleanup & Optimization

> **Target Agent:** Codex / any advanced AI code agent
> **Mission:** Transform Business-Empire-Agent from "impressive but messy" into a clean, pruned, properly wired, turnkey system
> **Scope:** Full repository — file structure, cross-references, broken links, stale state, deployment configs, test suite
> **Constraint:** DO NOT break working systems. DO NOT delete anything without confirming it's truly dead. DO NOT change business logic. This is a cleanup, not a rewrite.

---

## IDENTITY & CONTEXT

You are operating on `C:\Users\User\Business-Empire-Agent` — CC's (Conaugh McKenna) autonomous AI operations hub. This is a multi-AI, multi-agent system with:
- **1,424 git-tracked files** across 45 top-level directories
- **160 skills** (150 active + 10 archived)
- **197 Python scripts** in scripts/
- **65 Supabase migrations** (001-062)
- **5 AI entry points** (CLAUDE.md, AGENTS.md, GEMINI.md, ANTIGRAVITY.md, OPENCODE.md)
- **V6 pillars:** State (SQLite/WAL), Retrieval (FTS5+LanceDB hybrid), Sandbox (exec/state/secret guards), Secrets (secret_loader)
- **North Star:** $5,000 USD Net MRR by June 18, 2026

The system WORKS but has accumulated significant drift. Your job is to clean it without breaking it.

---

## GOLDEN RULES

1. **Read before writing.** Always read the current state of a file before editing.
2. **One change at a time.** Verify each fix before moving to the next.
3. **Never break working code.** If a script works, don't refactor it unless the fix is trivial.
4. **Preserve git history.** Use edits, not delete+recreate.
5. **Update cross-references.** When you move/rename anything, update ALL references.
6. **Sync entry points.** When you change something that entry points reference, update ALL five.
7. **Log your work.** Update `memory/SESSION_LOG.md` after each phase.
8. **Ask before deleting.** If unsure whether something is dead, flag it for CC.
9. **No drive-by changes.** Fix what's in scope. Don't "while I'm here" refactor.
10. **Verify after every change.** Run the relevant test, check the import, confirm the path.

---

## PHASE 1: CRITICAL FIXES (Do These First — They Break Things)

### 1.1 Fix Systematic Wikilink Bug in ALL Skills

**Problem:** Every wikilink `[[skills/xxx/SKILL]]` resolves to `skills/xxx/SKILL/SKILL.md` (double SKILL). ~300+ broken links.

**Fix:**
- Search all `skills/*/SKILL.md` files for the pattern `\[\[skills/([^/]+)/SKILL\]\]`
- Replace with `[[skills/$1/SKILL.md]]`
- Also fix `[[skills/INDEX]]` → `[[skills/INDEX.md]]`
- Also fix `[[skills/SKILL_LOADING]]` → `[[skills/SKILL_LOADING.md]]`
- Verify no links now resolve to non-existent paths

**Files affected:** ~160 SKILL.md files

### 1.2 Fix Broken Script References in Skills

**Problem:** 11 skills reference scripts that don't exist.

**Action per skill:**
- `skills/docx/SKILL.md` — Remove references to `scripts/office/soffice.py`, `scripts/office/unpack.py`, `scripts/accept_changes.py`, `scripts/office/validate.py`, `scripts/comment.py`, `scripts/office/pack.py`. Either mark skill as deprecated/archived, or update to use actual available tools.
- `skills/xlsx/SKILL.md` — Remove references to `scripts/recalc.py`, `scripts/office/soffice.py`. Same treatment.
- `skills/pptx/SKILL.md` — Remove references to `scripts/thumbnail.py`, `scripts/office/unpack.py`, `scripts/office/soffice.py`. Same treatment.
- `skills/agent-forge/SKILL.md` — Remove reference to `scripts/doctor.py`.
- `skills/ceo-dashboard/SKILL.md` — Remove references to `scripts/late_tool.py`.
- `skills/cli-anything/SKILL.md` — Remove references to `scripts/late_tool.py`, `scripts/edit_content_v2.py`.
- `skills/mcp-operations/SKILL.md` — Remove references to `scripts/late_tool.py`.
- `skills/python-daemon-automation/SKILL.md` — Remove references to `scripts/daemon_name.py`, `scripts/bravo_startup.py`, `scripts/skool_engine.py`, `scripts/skool_watchdog.py`.
- `skills/webapp-testing/SKILL.md` — Remove references to `scripts/with_server.py`.
- `skills/context-optimization/SKILL.md` — Remove reference to `scripts/instagram_engine.py`.
- `skills/daily-planner/SKILL.md` — Remove references to `scripts/content_engine.py`, `scripts/late_publisher.py`.

**Decision:** For skills where ALL script references are broken, move to `skills/_archive/` with a note explaining why. For skills with SOME broken refs, fix the broken refs and keep the skill active.

### 1.3 Fix Skills Referencing Deleted Skills

**Problem:** 12 references across 10 skills point to deleted skills: `lead-management`, `competitive-intelligence`, `content-engine`, `playwright`.

**Fix:**
- Search all SKILL.md files for references to these deleted skills
- Replace with the closest existing equivalent:
  - `lead-management` → `client-success` or `score-b2b-lead-quality`
  - `competitive-intelligence` → `market-research`
  - `content-engine` → `content` workflow in `.agents/workflows/content.md`
  - `playwright` → `browser-harness` or `cloak-browser`
- If no equivalent exists, remove the reference entirely

### 1.4 Fix Browser/ Directory Script References

**Problem:** Skills reference `browser/browser_harness_doctor.py`, `browser/cloak_browser_tool.py`, etc. — these exist in `scripts/browser/` not `browser/`.

**Fix:**
- Search all SKILL.md files for `browser/` script references
- Update paths to `scripts/browser/`
- Verify the scripts exist at the new paths

### 1.5 Fix agents/config.toml Missing Reference

**Problem:** 8+ skills reference `agents/config.toml` which doesn't exist.

**Fix:**
- Check if `agents/` has any config file that serves this purpose
- If not, create a minimal `agents/config.toml` with the expected structure
- Or update skills to reference the actual config location

### 1.6 Fix state/exec_override.py Missing Reference

**Problem:** exec-override skill references `state/exec_override.py` 8 times.

**Fix:**
- The actual file is `scripts/state/exec_guard.py` and `scripts/state/exec_override_consumer.py`
- Update the skill to reference the correct files
- If a specific `exec_override.py` is needed, check if its functionality is covered by existing files

### 1.7 Fix Placeholder Bugs

**Problem:** `skills/memory-journaling/SKILL.md` references `skills/Y/SKILL.md` and `skills/writing-skills/SKILL.md` references `skills/path/SKILL.md`.

**Fix:** These are clearly placeholder bugs. Find the intended skill reference or remove the broken link.

---

## PHASE 2: ENTRY POINT SYNC (Make All 5 Files Consistent)

### 2.1 Sync All Entry Points to CLAUDE.md (Canonical)

**CLAUDE.md is the canonical source.** Update AGENTS.md, GEMINI.md, ANTIGRAVITY.md, and OPENCODE.md to match:

**Must sync:**
- V6.7 Agentic OS Orchestration section
- V6.8 Agent-OS Vocabulary Layer section
- V6.5 Multi-Machine Bridge Arbitration (`scripts/bridge_lock.py`)
- Capability Graph section (`brain/CAPABILITY_GRAPH.json`)
- Current skill count: 160 (150 active + 10 archived)
- Current CLI tool count: verify with `ls scripts/*.py scripts/**/*.py | wc -l`
- Current MCP count: 9 (as defined in `.claude/mcp.json`)
- Current subagent count: verify with `ls .claude/agents/`
- Current workflow count: verify with `ls .agents/workflows/`
- MRR goal: $5,000 USD Net MRR by June 18, 2026

### 2.2 Fix @-Import Violations

**Problem:** GEMINI.md:26 and ANTIGRAVITY.md:27 use `@ARCHITECTURE.md`.

**Fix:** Replace with `[ARCHITECTURE.md](ARCHITECTURE.md)`

### 2.3 Fix .rules/01-identity.md MRR Goal

**Problem:** Says "May 15, 2026" — should be "June 18, 2026".

### 2.4 Add OPENCODE.md to AGENTS.md Rule 4 Cross-File Sync List

**Problem:** AGENTS.md Rule 4 lists entry points to sync but omits OPENCODE.md.

### 2.5 Remove .env.agents from MCP Config List in AGENTS.md

**Problem:** AGENTS.md Rule 4 lists `.env.agents` as an MCP config — it's a credentials file.

### 2.6 Fix .gemini/rules/ Drift Risk

**Problem:** `.gemini/rules/` contains copies of CLAUDE.md, GEMINI.md, etc. — these will drift.

**Fix:** Either replace with symlinks (if Windows supports them) or remove the copies and have .gemini/ reference the root files.

---

## PHASE 3: SCRIPT CLEANUP (scripts/ Directory)

### 3.1 Move Underscore-Prefixed Scripts to lib/

**Problem:** `_subprocess_helpers.py` (imported by 40+ scripts) and `_outbound_log_post.py` (imported by send_gateway) are actively imported but underscore-prefixed (implies private/internal).

**Fix:**
- Move `_subprocess_helpers.py` → `scripts/lib/subprocess_helpers.py`
- Move `_outbound_log_post.py` → `scripts/lib/outbound_log_post.py`
- Update ALL imports (search for `import _subprocess_helpers` and `import _outbound_log_post`)
- Verify no other underscore-prefixed scripts at root are actively imported

### 3.2 Archive lib/safe_error.py

**Problem:** 0 files import it.

**Fix:** Move to `scripts/_archive/safe_error.py` or delete if truly unused.

### 3.3 Add __init__.py to Missing Subpackages

**Problem:** `snapshots/` and `underwriting/` lack `__init__.py` but are imported as packages.

**Fix:** Add minimal `__init__.py` to both directories.

### 3.4 Fix V5.6 Outbound Chokepoint Violations

**Problem:** `integrations/google_tool.py:224` and `dashboard_email_consumer.py:215` send email via smtplib directly, bypassing send_gateway.

**Fix:**
- For `google_tool.py`: Route through `send_gateway.py` or document why it's an exception (Google Workspace API may require direct send)
- For `dashboard_email_consumer.py`: Route through `send_gateway.py`
- Verify no other direct smtplib usage exists (search for `smtplib.SMTP`)

### 3.5 Standardize .env.agents Loading

**Problem:** 42 files reference `.env.agents` without using canonical `secret_loader`.

**Fix:** This is a LARGE change. Do it incrementally:
- Start with the 12 files using `load_dotenv` directly — convert them to use `secret_loader`
- The remaining 42 that build their own path can be left for now (they work, just not canonical)
- Document the preferred pattern in a comment at the top of `secret_loader.py`

### 3.6 Fix Test Suite

**Problem:** 36/69 tests fail in `test_send_gateway.py`, `test_email_engine.py` broken, `test_n8n_inbound_rpc.py` has zero test functions.

**Fix:**
- Fix import paths in `test_send_gateway.py` — use proper module paths
- Fix `test_email_engine.py` import path
- Either add tests to `test_n8n_inbound_rpc.py` or rename it (it's not a test file)
- Add a `test` script to `package.json`
- Run `python -m pytest scripts/ -v` and verify all tests pass

### 3.7 Clean Up Empty _archive Directories

**Problem:** `scripts/_archive/` and `skills/_archive/` are empty.

**Fix:** Delete the empty directories. Keep `.agents/workflows/_archive/` (has 2 files).

---

## PHASE 4: BRAIN & MEMORY CLEANUP

### 4.1 Fix brain/STATE.md Manifest

**Problem:** Manifest last synced 2026-05-04 (17 days stale). Script/skill counts wrong.

**Fix:**
- Run actual counts: `ls scripts/*.py scripts/**/*.py | wc -l`, `find skills -name SKILL.md | wc -l`
- Update manifest with current counts
- Update `last_synced` timestamp

### 4.2 Fix memory/ACTIVE_TASKS.md

**Problem:** Stale hardcoded dates, old MRR deadline, stale BUILD status.

**Fix:**
- Update MRR deadline to June 18, 2026
- Remove hardcoded day/date references (use dynamic computation or remove)
- Update BUILD status table to reflect shipped state
- Update `last_updated` frontmatter
- Add `freshness_threshold_days: 7` if missing

### 4.3 Fix brain/ Cross-References

**Problem:** QUICK_REFERENCE.md has zero cross-references to other core brain files. INTENTS.md and WHEN_TO_USE_SKILLS.md missing QUICK_REFERENCE reference.

**Fix:** Add bidirectional cross-references between all 5 core brain files:
- AGENT_ROUTER.md
- EXECUTION_RULES.md
- INTENTS.md
- WHEN_TO_USE_SKILLS.md
- QUICK_REFERENCE.md

### 4.4 Fix Brain Files Referencing Missing Scripts

**Problem:** 25 scripts referenced in brain files don't exist.

**Fix:**
- For Sun Biz scripts (`state_bridge.py`, `sms_engine.py`, `funding_intel.py`, `deal_tracker.py`, `renewal_scanner.py`, `email_blast.py`): Check if these were migrated to a different location or are planned. If neither, remove references from `brain/AGENTS.md` and add a note.
- For Suga Sean scripts (`fan_engagement.py`, `merch_scheduler.py`, `social_publisher.py`): Same treatment.
- For Aura scripts (`aura_analytics.py`, `aura_audit.py`): Same treatment.
- For archived scripts (`skool_engine.py`, `outreach_batch.py`, `content_pipeline.py`): Update references to point to archived location or remove.
- For moved scripts (`content_pipeline.py` → CMO-Agent): Update reference to point to CMO-Agent location.

### 4.5 Fix Brain Files Referencing Missing Skills

**Problem:** 16 skills referenced in brain files don't exist.

**Fix:** Same approach as 4.4 — check if migrated, planned, or deleted. Update or remove references.

### 4.6 Add Orphaned Brain Files to INDEX.md

**Problem:** `SETUP_WIZARD_2_SPEC.md`, `SHARED_DB.md`, `SUNBIZ_CRM_KNOWN_GAPS.md`, `V68_AGENT_OS_PATTERNS.md` not in `brain/INDEX.md`.

**Fix:** Add them to the index, or move to `_archive/` if they're no longer relevant.

### 4.7 Add Frontmatter to Memory Files Missing It

**Problem:** 17 memory files have no `last_updated` or `freshness_threshold_days`.

**Fix:** Add frontmatter to each. Use the file's last git commit date as `last_updated` if available, or today's date. Set reasonable `freshness_threshold_days` based on file type.

---

## PHASE 5: DEPLOYMENT & INFRASTRUCTURE FIXES

### 5.1 Fix Docker Compose Broken Paths

**Problem:** All 3 compose files have broken script paths.

**Fix in docker-compose.yml:**
- `bravo-webhook`: Change command to `uvicorn hooks.webhook_listener:app` or set `working_dir: /app/scripts/hooks`
- `bravo-scheduler`: Change command to `python scripts/scheduler.py` or set `working_dir: /app/scripts`
- Healthcheck: Change to `python scripts/core/self_audit.py --health-only`

**Fix in docker-compose.local.yml:**
- `bravo-webhook`: Same as above
- `state-api`: Change to `uvicorn state.state_api:app` or set `working_dir: /app/scripts/state`

**Fix in docker-compose.cloud.yml:**
- `state-api`: Same as local

**Fix in Dockerfile:**
- Healthcheck: Change to `python scripts/core/self_audit.py --health-only`

### 5.2 Fix Caddyfile Hardcoded Email

**Problem:** `Konamak@icloud.com` hardcoded.

**Fix:** Replace with environment variable `${ADMIN_EMAIL:-admin@oasisai.work}`

### 5.3 Fix Gateway Hardcoded Paths

**Problem:** `gateway/adapters/telegram.js` has hardcoded `.venv/Scripts/python.exe`, `C:\Temp`, Claude/Gemini paths.

**Fix:**
- Use environment variables with sensible defaults
- Add path resolution logic that tries multiple locations
- Document required environment variables in gateway/README.md

### 5.4 Fix Install Script Smoke Test Paths

**Problem:** `install/install.ps1` references `scripts/self_audit.py` and `scripts/browser_harness_doctor.py` at wrong paths.

**Fix:**
- Update to `scripts/core/self_audit.py`
- Update to `scripts/browser/browser_harness_doctor.py`

### 5.5 Add Missing Env Vars to .env.example

**Problem:** `EMPIRE_V6_MODE`, `EMPIRE_HOOK_SECRET_GUARD`, `EMPIRE_HOOK_EXEC_GUARD`, `EMPIRE_HOOK_STATE_GUARD`, `OASIS_OUTBOUND_HMAC_SECRET`, `EMPIRE_OVERRIDE_HMAC_KEY` missing.

**Fix:** Add them to `.env.example` with commented-out defaults.

### 5.6 Fix Database Migration Sequence

**Problem:** Migration 047 missing. 030 and 031 have duplicate prefixes.

**Fix:**
- Check if 047 was skipped intentionally (gap is acceptable if documented)
- For 030/031 duplicates: Check if both are needed. If so, rename to `030a_`, `030b_` or similar. If one is obsolete, archive it.

---

## PHASE 6: STRUCTURAL CLEANUP

### 6.1 Resolve rules/ vs .rules/

**Problem:** `rules/` (1 file) and `.rules/` (8 files) are confusing.

**Fix:** If `rules/` is a stray/legacy, move its content to `.rules/` and delete the directory. If it serves a purpose, rename it to something clearer.

### 6.2 Resolve _templates/ vs templates/

**Problem:** Two template directories.

**Fix:** Merge into one or clearly document the difference. If `_templates/` is internal snippets, rename to `templates/snippets/`.

### 6.3 Handle Empty app/ Directory

**Problem:** `app/` has 0 files, 3 subdirectories.

**Fix:** If the command center is in a separate repo (oasis-command-center), delete the empty `app/` directory. If it's a future scaffold, add a README explaining the intent.

### 6.4 Handle apps/agent-runner/

**Problem:** Abandoned skeleton code.

**Fix:** Move to `_archive/agent-runner/` or delete if truly abandoned. Document the decision.

### 6.5 Clean Up .obsidian/ Tracked Binaries

**Problem:** Plugin binaries (8.2 MB) tracked despite gitignore.

**Fix:** Run `git rm --cached .obsidian/plugins/*/main.js .obsidian/plugins/*/styles.css` to untrack them. They're already gitignored so future commits won't include them.

### 6.6 Stale Plans in .agents/plans/

**Problem:** 2.5 months old.

**Fix:** Move to `.agents/plans/_archive/` or update if still relevant.

### 6.7 Fix .claude/mcp.json.template Divergence

**Problem:** Template references `.cmd` wrapper files that don't exist. Live mcp.json uses `.js` shims.

**Fix:** Update the template to match the live mcp.json structure, or create the missing `.cmd` files.

### 6.8 Fix Telegram Agent Version Strings

**Problem:** Says "BRAVO V5.5" in prompt, version inconsistency V15.7 vs V15.8.

**Fix:** Update to current version (V6.x for Bravo, unify to V15.8 for telegram agent).

---

## PHASE 7: VERIFICATION & FINAL SYNC

### 7.1 Run Full Test Suite

```bash
python -m pytest scripts/ -v --tb=short
```

All tests should pass. Document any that can't be fixed (require external services, sibling repos, etc.).

### 7.2 Verify All Script Imports

```bash
python -c "
import py_compile, sys, glob
errors = []
for f in glob.glob('scripts/**/*.py', recursive=True):
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError as e:
        errors.append(f'{f}: {e}')
if errors:
    print('FAILURES:')
    for e in errors:
        print(e)
    sys.exit(1)
print('All scripts compile cleanly')
"
```

### 7.3 Verify Skill References

Write a script that checks every SKILL.md for references to files that don't exist:
- Script paths referenced
- Skill paths referenced
- Brain/memory paths referenced
Flag any that don't resolve.

### 7.4 Verify Entry Point Consistency

Run a diff-style check across all 5 entry points to confirm they now have consistent:
- MRR goal
- Skill count
- CLI tool count
- MCP count
- Subagent count
- Workflow count
- V6 section content

### 7.5 Verify Docker Compose

```bash
docker compose -f infra/docker-compose.local.yml config
docker compose -f infra/docker-compose.yml config
docker compose -f infra/docker-compose.cloud.yml config
```

All should produce valid config output without errors.

### 7.6 Update SESSION_LOG.md

Log all changes made, files touched, and any decisions that need CC's review.

### 7.7 Generate Cleanup Summary

Create a summary document listing:
- What was fixed
- What was archived
- What was deleted
- What needs CC's review
- What remains as known issues

---

## PRIORITY ORDER

Execute phases in this order:
1. **Phase 1** (Critical — broken references)
2. **Phase 2** (Entry point sync)
3. **Phase 3** (Script cleanup)
4. **Phase 4** (Brain & memory)
5. **Phase 5** (Deployment/infra)
6. **Phase 6** (Structural cleanup)
7. **Phase 7** (Verification)

Within each phase, execute items in the order listed. Do NOT skip phases. Do NOT move to the next phase until the current phase is verified complete.

---

## WHAT NOT TO TOUCH

- `.env.agents` — credentials, CC manages
- `brain/SOUL.md` — immutable
- Supabase production database — read-only unless explicitly asked
- `revenue_events`, `monthly_metrics` tables — financial truth
- Any file CC has explicitly said not to touch
- Business logic in working scripts
- The Telegram bridge (telegram_agent.js) — only fix version strings, don't refactor

---

## COMMUNICATION PROTOCOL

- Report progress after each phase
- Flag any contradictions or ambiguities before acting
- Present deletion candidates to CC before deleting
- Use plain English — CC is a founder, not an engineer
- When done, present a summary: what changed, what's cleaner, what needs attention

---

*This system message was generated by a deep diagnostic audit on 2026-05-21. It incorporates findings from 4 parallel audit agents covering: file structure, scripts, skills, brain/memory/config, and apps/infra.*
