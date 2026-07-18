---
description: "Retrospective of system health diagnostic + ZCode integration with verified live outputs: capability-graph drift closure, entry-point registry updates, audits"
tags: [retrospective, health-diagnostic, integrity, auto-fix, capability-graph, zcode-entry-point]
last_updated: 2026-06-17
freshness_threshold_days: 365
---
# Retrospective — System Health Diagnostic + ZCode Entry Point (2026-06-17)

Two pieces of work landed on `main` this session: (1) a system-health diagnostic pass that closed capability-graph drift and corrected stale inventory counts across the harness, and (2) a brand-new sixth entry point — `ZCODE.md` — so GLM-5 models running through the ZCode CLI wake up as Bravo with the full harness. The ZCode integration was then put through **two independent audits** (a 5-check verification workflow + a Codex review), which caught five registry-wiring gaps and a generated-index freshness trap that the first pass missed; all were fixed before commit.

> [!warning] Provenance note for the next reader
> This file is split into **(A) verified live this session** — checks I ran and file changes I made, with the actual command output — and **(B) inherited from the diagnostic handoff** — live-credential probes reported by an earlier pass that I did **not** re-run. Don't treat (B) as freshly confirmed. (Rule 1: evidence before claims. Rule 10: inherited claims are archived context, not verified state — this applies to the audit subagents' claims too, every one of which was re-verified live before acting.)

---

## (A) Verified live this session — with real output

### A1. ZCode entry point created (`ZCODE.md`)
- New 6th lockstep entry point, modeled on the lean `OPENCODE.md` template.
- H1 is version-agnostic (`# ZCODE — BRAVO`); references `CONTEXT.md`; both `LOCKSTEP:tool_discipline` and `LOCKSTEP:untrusted_content` blocks are **byte-identical** to the other five (sha256-confirmed by the audit + the parity/canonical tests).
- ZCode-specific content: GLM-5 Turbo from `.zcode/`; **CLI-only tool surface** — maps each MCP capability to its `scripts/` CLI equivalent. Rules section carries a note that it's a condensed CLI-chassis subset (numbering follows the OpenCode convention; CLAUDE.md is authoritative).

### A2. Parity test extended 5 → 6 entry points
- `scripts/tests/test_entrypoint_parity.py`: `ENTRY_POINTS` includes `"ZCODE.md"`; docstring + `test_all_entry_points_exist` renamed. → `Ran 5 tests — OK`.

### A3. Sibling cross-refs + Rule 4 lists updated for the 6th door
- Sibling blockquotes updated in all five existing entry points (CLAUDE/GEMINI/ANTIGRAVITY/AGENTS/OPENCODE) — "five/four" → "six/five", ZCODE.md added.
- Rule 4 lists: `CLAUDE.md` (sibling line + `@`-import enumeration + Rule 4 list), `AGENTS.md` (sibling line + Entry-points list), `OPENCODE.md` (sibling line + Rule 4 line).
- `brain/AGENTS.md` "AI Entry Points" section completed (previously listed only GEMINI + ANTIGRAVITY) — now enumerates all six.

### A4. ZCode wired into ALL operational entry-point registries (audit-driven)
Both independent audits flagged that adding ZCODE.md to the parity test alone leaves it invisible to the gates that hardcode the entry-point set. Fixed every one:
- `scripts/tests/test_harness_canonical.py` `KNOWN` — ZCODE's LOCKSTEP blocks now drift-checked against `harness.lock`. Test still green (3/3).
- `scripts/core/memory_retriever.py` `SCOPES["entry"]` — ZCODE.md now in the FTS5 retrieval index.
- `scripts/retriever_postedit.py` `ENTRY_FILES` — edits to ZCODE.md now trigger the reindex hook.
- `scripts/core/sync_entry_points.py` `SYNC_MAP` — generates the `.gemini/rules/ZCODE.md` mirror.
- `scripts/deploy/verify_deploy.py` entry tuple — ZCODE.md now in the deploy entry-point check (see pre-existing-issue note below re: marker drift).

### A5. `.gemini/rules/` mirrors regenerated (`sync_entry_points.py`)
- Generated `.gemini/rules/ZCODE.md`. **Side effect, disclosed:** the tool re-synced all six mirrors, and the five existing ones (`CLAUDE/GEMINI/ANTIGRAVITY/AGENTS/OPENCODE`) had drifted substantially from their sources — the sync reconciled that pre-existing staleness. Verified each `.gemini/rules/X.md` is now an **exact mirror** of `X.md` (EOL-normalized diff empty). No unique content clobbered — these are generated mirrors.

### A6. Capability graph — matches disk, no drift
- `python scripts/build_capability_graph.py --check` → `OK — capability graph matches disk.`
- Node breakdown read from `brain/CAPABILITY_GRAPH.json`: **320 nodes** — 150 skills, 105 scripts, 21 agents, 9 mcp, 35 workflows — **40 edges**.

### A7. Generated docs fresh (post-commit-safe)
- The audit caught a real trap: creating this retrospective adds a 19th tracked `memory/*.md`, but `memory/INDEX.md` still said "18 files" → the freshness gate would FAIL the moment the retro is committed. Fixed by regenerating docs with the retro staged: `python scripts/build_capability_graph.py --emit-docs` → `memory/INDEX.md` now "**19 files**".
- `python scripts/tests/test_generated_docs_fresh.py` → `Ran 2 tests — OK` (with the retro staged, i.e. the committed state).

### A8. Routing accuracy, wiki-links, harness canonical, system health
- `test_routing_accuracy.py` → `Ran 2 tests — OK`.
- `test_wiki_links.py` → **0 unresolved** (ZCODE.md + `.gemini/rules/ZCODE.md` tracked).
- `test_harness_canonical.py` → `Ran 3 tests — OK`.
- `python scripts/system_health.py --json` → `reds: 0, yellows: 2` (pre-existing noise floor: 87 raw subprocess calls / 53 files; 173 bare `except→pass` / 88 files). All other checks green.
- **Correction to the inherited handoff:** there are **no** "8 broken wikilinks" — `test_wiki_links.py` reports zero. That claim was stale.

### A9. Stale inventory counts corrected (entry points + CAPABILITIES.md)
| Metric | Old (stale) | New (verified vs graph) |
|---|---|---|
| Active skills | 148–149 | **150** |
| Archived skills | 11 | **10** |
| Top-level scripts | 114–115 | **105** |
| Total scripts (inc. subpackages) | 215–218 | **238** |
| Cron SEED jobs | 20 | **23** |
| Inventory sync date | 2026-06-06 | **2026-06-17** |

### A10. Cleanup
- Removed stray 0-byte `nul` file (Windows redirect artifact).

---

## (B) Inherited from the diagnostic handoff — NOT re-verified this session

Live-credential probes reported by an earlier pass; I did not re-run them. Re-confirm before relying on any.

| Subsystem | Reported | Re-verify with |
|---|---|---|
| Supabase | 3 projects, keys valid | `python scripts/integrations/supabase_tool.py list-projects --json` |
| Stripe | 3 accounts LIVE | `python scripts/integrations/stripe_tool.py list-accounts --json` |
| Google Workspace | 10/10 PASS | `python scripts/google_tool.py test` |
| Telegram | force-send OK | `python scripts/notify.py --force "probe"` |
| GitHub / Vercel / Firecrawl / n8n | valid | service CLI probes |
| MCP secret audit | 0 plaintext leaks | `python scripts/audit_mcp_secrets.py` |
| Orphaned MCP procs | ~69 reapable | `python scripts/core/system_health_check.py` |

---

## Independent audits (Rule 8)

- **Bravo verification workflow (5 read-only checks):** lockstep byte-identity PASS, sibling completeness PASS, registry enumeration WARN→fixed, ZCODE content WARN (rule-numbering + unverified MCP assumption), retro-vs-repo flagged the index-freshness trap.
- **Codex independent review (exit 0):** two P2 findings, both corroborating the workflow — (1) ZCODE not wired into the 5 operational registries, (2) retrospective missing from `memory/INDEX.md`. Both fixed (A4, A7).
- Two independent auditors converging on the same gaps is why these were caught before commit rather than surfacing as a later drift bug.

---

## Pre-existing issues flagged (NOT introduced by this work, NOT fixed here)

1. **`verify_deploy.py` "Entry Points" check is already red for ALL entry points.** It greps for four V6.5–V6.8 marker strings ("Multi-Machine Bridge Arbitration", "Capability Graph", "Agentic OS Orchestration", "Agent-OS Vocabulary Layer") that **none** of the six entry points contain anymore — they were consolidated into `brain/V6_ARCHITECTURE.md` during the entry-point slim-down. ZCODE.md was added to the tuple for registry completeness, but the gate stays `DO_NOT_DEPLOY` until the marker check is updated to match the slimmed entry points (or the markers re-added). Separate task.
2. **`CLAUDE.md:94` says "49 CLI tools"** in RULE 2 prose — stale and inconsistent with the corrected Inventory block ("105 top-level CLI tools"). Left as-is because "49" may have counted a specific subset (service-integration wrappers) rather than all top-level scripts; needs CC/Claude Code to confirm the intended metric before changing.

---

## Files changed (24, all staged on `main`)

`ZCODE.md` (new) · `.gemini/rules/ZCODE.md` (new mirror) · `.gemini/rules/{CLAUDE,GEMINI,ANTIGRAVITY,AGENTS,OPENCODE}.md` (resynced from stale) · `CLAUDE.md` · `GEMINI.md` · `ANTIGRAVITY.md` · `AGENTS.md` · `OPENCODE.md` · `brain/AGENTS.md` · `brain/CAPABILITIES.md` · `brain/CAPABILITY_GRAPH.json` · `brain/WHEN_TO_USE_SKILLS.md` · `memory/INDEX.md` · `memory/RETROSPECTIVE_2026-06-17_system_health_diagnostic.md` (this file) · `scripts/tests/test_entrypoint_parity.py` · `scripts/tests/test_harness_canonical.py` · `scripts/core/memory_retriever.py` · `scripts/core/sync_entry_points.py` · `scripts/deploy/verify_deploy.py` · `scripts/retriever_postedit.py`

---

## Claude Code action items

1. **Cross-check ZCODE.md's GLM-5 tool-surface claims** against the ZCode CLI's actual capabilities — "no native MCP servers; route via `scripts/`" was written from the OpenCode precedent + the plan, not a live ZCode probe. Also confirm whether ZCode can shell out to `node` for the Codex delegation lane (Rule 8 in ZCODE.md is conditional on it).
2. **Decide the `verify_deploy.py` marker drift** (pre-existing issue #1) — update the V6.5–V6.8 marker check to match the slimmed entry points, or re-add the markers. This is the only thing keeping the deploy gate red on entry points.
3. **Settle `CLAUDE.md:94` "49 CLI tools"** (pre-existing issue #2) — confirm the intended metric, then sync the number.
4. **Optional:** generalize `brain/ORCHESTRATION.md`'s 3-tier model table (Haiku/Sonnet/Opus) to capability tiers (fast/reasoning/critical) now that a non-Anthropic chassis (GLM-5) is in the family. `scripts/model_router.py` already supports multi-provider routing.
