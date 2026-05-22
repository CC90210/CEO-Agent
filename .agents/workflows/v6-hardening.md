# V6 Production Hardening Execution Plan

> **System Message for Autonomous Agent (Bravo / Codex / OpenCode)**
> 
> **Context:** A recent deep diagnostic audit identified specific gaps in the Business-Empire-Agent's production readiness. While the architectural substrate (V6 Apex) is strong, there are critical gaps in CI testing, state file accuracy, documentation drift, and git hygiene.
> **Objective:** Execute the following high-leverage fixes sequentially to harden the repository and achieve true production-grade status.
> **Role:** You are the Lead Architect / Backend Executor. Read this prompt and self-execute the phases below.

## Execution Rules
1. **Surgical Precision**: Only touch what is necessary for each step.
2. **Verification First**: After every step, verify the fix (e.g., run `git status`, `pytest`, or the capability graph script).
3. **Continuous Sync**: Update `memory/SESSION_LOG.md` and `brain/STATE.md` after completing the workflow.

## Phase 1: Testing & CI Pipeline Integrity
- **Target**: `.github/workflows/deploy-vps.yml`
- **Action**: Update the testing step to include the `tests/` directory. Currently, it only runs `pytest scripts/` and skips the most critical integration tests (`test_event_bus.py`, `test_hook_regression.py`, etc.). Modify the CI step to run both `tests/` and `scripts/`.
- **Verification**: Ensure the YAML syntax remains valid.

## Phase 2: Capability Graph & Documentation Sync
- **Targets**: `scripts/build_capability_graph.py`, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `ANTIGRAVITY.md`, `OPENCODE.md`
- **Action**:
  1. // turbo
     Execute `python scripts/build_capability_graph.py` to regenerate `brain/CAPABILITY_GRAPH.json`.
  2. Read the accurate inventory numbers (Skills and Python scripts) from the newly generated JSON.
  3. Update the inventory claims in `AGENTS.md` and all other entry point markdown files to exactly match the ground truth on disk. Remove the false "160 skills / 196 scripts" claim.
- **Verification**: Check `git diff` to ensure all 5 entry points reflect the correct numbers.

## Phase 3: State Drift Remediation
- **Target**: `brain/STATE.md`
- **Action**: Locate the section discussing `exec-override` Phase 2 (around line 11). The `exec-override` system was deleted on 2026-05-22, but the state file still describes it in the present tense. Strike-through or delete this paragraph entirely to prevent LLM hallucination on reboot.
- **Verification**: Ensure `brain/STATE.md` no longer presents `exec-override` as an active mechanism.

## Phase 4: Git Hygiene & Archive Cleanup
- **Targets**: `scripts/_archive/`, `memory/ARCHIVES/`, `.gitignore`
- **Action**: 
  1. // turbo
     Remove tracked `.pyc` files from the repository index without deleting them from the filesystem using `git rm --cached -r scripts/_archive/__pycache__` (or similar).
  2. Untrack any `__pycache__` directories residing in archive folders.
  3. Ensure `.gitignore` comprehensively covers `__pycache__/` and `*.pyc` globally so they aren't re-added.
- **Verification**: Run `git status` to ensure `.pyc` files are staged for deletion from the index but remain ignored.

## Phase 5: Security Guard Enforcement
- **Target**: `.env.agents` (if permitted) and `brain/STATE.md`
- **Action**: Flip `EMPIRE_HOOK_SECRET_GUARD` from `report` to `enforce`. If you are running as an agent without direct access to `.env.agents` (due to Secret Guard), add a high-priority task to `memory/ACTIVE_TASKS.md` instructing the human operator (CC) to make this change.
- **Verification**: Confirm the guard mode change is documented in the session log.
