# OasisAI Agent Architecture Alignment & Turso Cutover Handover (Updated v2)

> **For:** Adon & APEX Agent (JARVIS Repository)  
> **From:** CC & Bravo (Business-Empire-Agent / OasisAI Hub)  
> **Date:** August 20, 2026  
> **Subject:** Turso/libSQL Cutover Alignment, Send Slot Lock-Free Migration, RPC Compatibility, & Gotcha Matrix  

---

## 1. Executive Overview

OasisAI has officially cut over its primary database layer from legacy Supabase (Postgres) to **Turso (libSQL)** across 191 tables. 

This document serves as the complete technical handover for **APEX** (Adon's agent in the `JARVIS` repo). It incorporates direct answers to APEX's technical audit queries (Q1–Q6), the sanctioned lock-free send slot reservation pattern, RPC compatibility signatures, and SQLite/libSQL driver gotchas.

---

## 2. COPY-PASTE SYSTEM MESSAGE FOR APEX AGENT

*Copy everything between the triple backticks below and paste it into APEX's system prompt or configuration:*

```markdown
# APEX AGENT SYSTEM DIRECTIVE — DATABASE TRUTH & HARNESS INTEGRITY

## 1. Primary Database Contract (Turso / libSQL First)
- **Primary Database:** Turso/libSQL (`turso_tool.py` / `lib.turso_supabase_compat` or JARVIS libSQL driver).
- **Retired Infrastructure:** Supabase is DEPRECATED for primary data operations. Do NOT query Supabase for leads, contracts, daily metrics, or tenant state.
- **Fail-Closed Guarantee:** Any database access function MUST use Turso libSQL compatibility. Fallbacks to raw Supabase on error are strictly blocked.
- **Credentials:** Credentials live exclusively in `.env.agents`. Never hardcode keys or reference legacy Supabase service role keys.
- **Routing Tokens:** `SUPABASE_URL` in `.env.agents` is retained as a project routing token (mapping to Turso databases) and MUST NOT be deleted.

## 2. Harness Discipline & Verification (Non-Negotiable)
1. **Evidence Before Claims:** Run your local test gates (`python scripts/audit_supabase_references.py` / `pytest tests/test_no_new_supabase.py`), read the output, then report state. Never assert system state from memory.
2. **Read Before Edit, Verify After Edit:** Every code change must be followed by tests or syntax validation.
3. **No Workarounds:** If a CLI tool or driver fails, report the error immediately. Do not write ad-hoc workaround scripts or hardcode keys.
4. **Clean Memory Frontmatter:** Ensure `SESSION_LOG.md` and state files maintain exactly ONE YAML frontmatter block. Atomic writes must sanitize duplicated headers automatically.

## 3. Eradication of Stale Context (Documentation Only)
- Sweep markdown files (`.md`) for stale claims asserting Supabase is the active primary database.
- Doc sweeps strictly target markdown documentation; they NEVER touch `.env*`, `.py`, `.ts`, or configuration files.
```

---

## 3. APEX Audit Query Resolutions (Q1 – Q6)

### Q1: Harness Tool Parity (Bravo vs JARVIS)
* **Status:** **Bravo-only by design.**
* **Guidance:** Bravo's internal harness tools (`harness_eval.py`, `self_audit.py`, `agent_genome.py`, `state_sync.py`) manage Business-Empire-Agent's specific multi-agent C-Suite architecture. APEX does NOT need to port these. JARVIS maintaining its local gates (`audit_supabase_references.py` and `test_no_new_supabase.py` passing 4/4) is the correct cross-repo contract.

### Q2: `SUPABASE_URL` & Routing Token Protection
* **Status:** **Excluded from all sweeps.**
* **Guidance:** `doc_sweep.py` scans `.md` documentation files ONLY. It never touches `.env.agents`, `.env*`, Python, or TypeScript code files. `SUPABASE_URL` remains active as a project identifier / routing token across both estates.

### Q3: `exec_sql` RPC Port & Signature
* **Status:** **Ported & active in `RPC_REGISTRY`.**
* **Signature:** `client.rpc("exec_sql", {"sql": "<QUERY_STRING>"})` (or `{"sql_query": "..."}`)
* **Return Value:** `{"status": "ok"}`
* **Implementation:** Executes DDL/DML directly against the Turso libSQL connection via `db.execute()`.

### Q4: `get_tables` RPC Port
* **Status:** **Native SQLite replacement.**
* **Guidance:** Postgres `pg_tables` queries do not exist in SQLite/libSQL. Native table discovery queries `sqlite_master`:
  ```sql
  SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';
  ```
* **Compat Snippet for JARVIS:**
  ```python
  "get_tables": lambda db, p: [{"table_name": r["name"]} for r in db.query("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
  ```

### Q5: RPC Port Verification State
* **Status:** **100% Test-Verified in Python `RPC_REGISTRY`.**
* **Guidance:** All 16 Python RPC ports in `scripts/lib/turso_supabase_compat.py` (including `reserve_send_slot`, `claim_events`, `ack_event`, `exec_sql`, `patch_tenant_record_data`, `shop_out_*`) are fully verified by automated test suites (`test_turso_rpc_ports.py` and `test_turso_supabase_compat.py`). The TS `TURSO_RPC_SHIM` manifest was an early prototype note; the Python backend registry is active and test-proven.

### Q6: Sanctioned Lock-Free Send Slot Reservation Pattern
* **Status:** **Advisory lock replaced by Lock-Free Speculative Insert.**
* **Problem:** Postgres `pg_try_advisory_xact_lock` does not exist in libSQL/SQLite.
* **Sanctioned Pattern (used in `send_gateway.py` / `_rpc_reserve_send_slot`):**

```python
def reserve_send_slot_turso(db, lead_id: str, channel: str, window_minutes: int = 60):
    """Lock-Free Speculative Insert & Earliest-Row Selection Pattern for Turso."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
    new_id = str(uuid.uuid4())
    created = datetime.now(timezone.utc).isoformat()
    
    # 1. Speculatively insert our reservation row
    db.execute(
        'INSERT INTO "lead_interactions" (id, lead_id, type, channel, created_at) '
        'VALUES (?, ?, "reserving", ?, ?)',
        [new_id, lead_id, channel, created]
    )
    db.commit()

    # 2. Read the earliest 'reserving' row in the window for this (lead_id, channel)
    rows = db.query(
        'SELECT id, created_at FROM "lead_interactions" '
        'WHERE lead_id = ? AND channel = ? AND type = "reserving" AND created_at >= ? '
        'ORDER BY created_at ASC, id ASC LIMIT 1',
        [lead_id, channel, cutoff]
    )
    winner = rows[0] if rows else None

    # 3. Check if our speculative row won
    if winner and winner["id"] != new_id:
        # We lost the race: delete our speculative row and report existing winner
        db.execute('DELETE FROM "lead_interactions" WHERE id = ?', [new_id])
        db.commit()
        return {"lock_acquired": True, "existing_id": winner["id"], "reservation_id": None}

    # We won the reservation!
    return {"lock_acquired": True, "existing_id": None, "reservation_id": new_id}
```

---

## 4. LibSQL / SQLite Driver Gotchas & Remediation

| Gotcha | Problem | Remediation Pattern |
|---|---|---|
| **Booleans as `0/1`** | SQLite returns booleans as integer `1` or `0`. Strict `=== true` or `is True` fails. | Use truthy coercion: `bool(val)` in Python or `Boolean(val)` in JS/TS. |
| **JSON as `TEXT`** | LibSQL stores `JSON` columns as raw text strings. | Callers must parse explicitly: `json.loads(val)` in Python or `JSON.parse(val)` in JS/TS. |
| **Hrana Cursor Rowcount** | `cursor.rowcount` on remote Hrana connections can return `-1` or `None` on `UPDATE`. | Use `RETURNING id` clause instead of checking `rowcount`. |

---

## 5. Verification Gate for JARVIS

To verify total alignment in the `JARVIS` repository:

```bash
# 1. Verify zero unclassified Supabase references in JARVIS
python scripts/audit_supabase_references.py

# 2. Run new Supabase prevention test gate
pytest tests/test_no_new_supabase.py
```

---
*Signed by Bravo (OasisAI Lead Architect)*
