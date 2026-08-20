# OasisAI Agent Architecture Alignment & Turso Cutover Handover

> **For Adon & APEX Agent**
> **From:** CC & Bravo (Business-Empire-Agent / OasisAI Hub)
> **Date:** August 20, 2026
> **Subject:** Turso/libSQL Migration Alignment, Supabase Context Eradication, and Harness Self-Improvement Protocol

---

## 1. Executive Overview

OasisAI has officially cut over its primary database layer from legacy Supabase (Postgres) to **Turso (libSQL)** across 191 tables. 

To prevent data drift, false-assurance green signals, and cross-agent context leaks as our platforms scale together, this document provides the exact system message, architecture rules, and harness verification patterns for **APEX** (Adon's agent) to adopt.

---

## 2. COPY-PASTE SYSTEM MESSAGE FOR APEX AGENT

*Copy everything between the triple backticks below and paste it into APEX's system prompt or configuration:*

```markdown
# APEX AGENT SYSTEM DIRECTIVE — DATABASE TRUTH & HARNESS INTEGRITY

## 1. Primary Database Contract (Turso / libSQL First)
- **Primary Database:** Turso/libSQL (`turso_tool.py` / `lib.turso_supabase_compat`).
- **Retired Infrastructure:** Supabase is DEPRECATED for primary data operations. Do NOT query Supabase for leads, contracts, daily metrics, or tenant state.
- **Fail-Closed Guarantee:** Any database access function MUST use Turso libSQL compatibility. Fallbacks to raw Supabase on error are strictly blocked.
- **Credentials:** Credentials live exclusively in `.env.agents`. Never hardcode keys or reference legacy Supabase service role keys.

## 2. Harness Discipline & Verification (Non-Negotiable)
1. **Evidence Before Claims:** Run the verification check (`python scripts/harness_eval.py` / `self_audit.py`), read the output, then report state. Never assert system state from memory.
2. **Read Before Edit, Verify After Edit:** Every code change must be followed by tests or syntax validation.
3. **No Workarounds:** If a CLI tool or driver fails, report the error immediately. Do not write ad-hoc workaround scripts or hardcode keys.
4. **Capability Graph Synchronization:** When adding or modifying any script, skill, or workflow, ALWAYS include a `CAPABILITY_META` block and re-index the capability graph (`python scripts/build_capability_graph.py`).
5. **Clean Memory Frontmatter:** Ensure `SESSION_LOG.md` and state files maintain exactly ONE YAML frontmatter block. Atomic writes must sanitize duplicated headers automatically.

## 3. Eradication of Legacy Supabase Assumptions
- Search and annotate/clean any legacy references to Supabase in operational markdown files using the doc-sweep tool (`python scripts/core/doc_sweep.py`).
- Maintain zero unclassified Tier-1 / Tier-2 hits in core documentation.
```

---

## 3. Technical Changes & Architecture Blueprint

### A. Database Topology (Turso / libSQL)
- **Primary Engine:** Turso libSQL (SQLite-compatible at scale with edge replication).
- **Python Bridge:** `scripts/integrations/turso_tool.py` and `scripts/lib/turso_supabase_compat.py`.
- **Tenant Isolation:** All tenant tables (`leads`, `lead_interactions`, `contracts`) strictly enforce `tenant_id` stamping on reads and writes.

### B. Harness Self-Improvement & Multi-Agent Harmony
1. **Deterministic Eval Gate:** `python scripts/harness_eval.py` checks 14 system invariants (lockstep entry points, graph freshness, daily brief data, PM2 fleet, fail-closed guards).
2. **Self-Audit Gate:** `python scripts/core/self_audit.py --json` scores 100+ repo parameters and blocks unregistered scripts or graph drift.
3. **Genome Parity:** `python scripts/agent_genome.py` verifies 10 core agent capabilities are fully expressed across all entry points.
4. **Automatic State & Memory Sync:** `python scripts/state/state_sync.py` cleans duplicate frontmatter, updates operational state (`brain/STATE.md`), and refreshes C-Suite pulse files (`data/pulse/*.json`).

---

## 4. Verification Commands

Run these commands in your repository to verify total alignment:

```bash
# 1. Verify system harness (Target: 14/14 checks pass)
python scripts/harness_eval.py

# 2. Rebuild capability graph after adding scripts/skills
python scripts/build_capability_graph.py

# 3. Check for stale Supabase references in documentation
python scripts/core/doc_sweep.py --term Supabase --brain --memory --json

# 4. Verify agent genome expression (Target: 10/10 expressed)
python scripts/agent_genome.py

# 5. Run full state sync & heartbeat update
python scripts/state/state_sync.py --note "Turso alignment verified"
```

---
*Signed by Bravo (OasisAI Lead Architect)*
