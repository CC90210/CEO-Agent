"""lender_response_classifier.py — close the loop on lender shop-out.

Phase 6.4 of the SunBiz CRM build (2026-05-15). Lender threads created
by /api/applications/[id]/shop-out land in application_lender_threads
with status='sent' and a gmail_thread_id once the physical send fires.
This daemon polls Gmail for new messages on those threads, classifies
each via Claude (approved / declined / info_requested), and updates
the thread row so the operator sees the funding-pipeline state without
ever opening Gmail.

Architecture:

  application_lender_threads (status=sent)
        |
        v
  Daemon poll loop  -- per-thread: fetch newest message via google_tool
        |
        v
  Claude classifier  -- prompt: "is this an approval, decline, info
                                  request, or none-of-the-above?"
        |
        v
  Update row.status + last_response_summary + last_response_at

The classifier is conservative: when Claude returns low confidence,
status stays 'responded' (not approved/declined). Operators see the
ambiguity flag and can manually disambiguate. Cheaper than wrong calls
that misroute leads.

SLA-based 'no_response' transition: if a thread has been at status=sent
for longer than the lender's sla_response_days, it auto-flips to
'no_response' without consuming a classifier call. Operator decides
whether to follow up or move on.

CLI:
  python scripts/lender_response_classifier.py loop --interval 300
  python scripts/lender_response_classifier.py once
  python scripts/lender_response_classifier.py tail
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = REPO_ROOT / "state"
LOG_PATH = STATE_DIR / "lender_response_classifier.log"

# Look back this far when scanning Gmail threads on each poll. Older
# threads are presumed already-classified or no_response (and would
# have aged out via the SLA check anyway). Tunable.
THREAD_LOOKBACK_DAYS = 30

# Default response SLA used when the lender row has no sla_response_days
# field. Conservative ~7 business days.
DEFAULT_SLA_DAYS = 10


def _log(msg: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}\n"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass
    print(line.rstrip())


# ─────────────────────────────────────────────────────────────────────
# Supabase client + env loading — mirrors sequence_runner.py
# ─────────────────────────────────────────────────────────────────────


def _supabase():
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.secret_loader import load_env  # type: ignore
    except Exception:
        return None
    try:
        env = load_env()
    except Exception:
        return None
    url = (env.get("BRAVO_SUPABASE_URL") or "").strip()
    key = (env.get("BRAVO_SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


def _load_env_var(name: str) -> str:
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        from lib.secret_loader import load_env  # type: ignore
        return (load_env().get(name) or os.environ.get(name) or "").strip()
    except Exception:
        return os.environ.get(name, "").strip()


# ─────────────────────────────────────────────────────────────────────
# SLA-based no_response auto-flip
# ─────────────────────────────────────────────────────────────────────


def sla_sweep(sb) -> int:
    """Find sent-but-silent threads past their SLA, mark them
    no_response. No classifier calls; cheap + safe."""
    try:
        rows = (
            sb.table("application_lender_threads")
            .select("id, lender_id, tenant_id, sent_at")
            .eq("status", "sent")
            .not_.is_("sent_at", "null")
            .execute()
        )
    except Exception as e:
        _log(f"sla_sweep: read failed: {e}")
        return 0
    if not rows.data:
        return 0

    # Batch-fetch the SLAs from lender rows (tenant_records).
    lender_ids = list({r["lender_id"] for r in rows.data})
    sla_by_lender: dict[str, int] = {}
    try:
        lenders = (
            sb.table("tenant_records")
            .select("id, data")
            .in_("id", lender_ids)
            .eq("entity_type", "lender")
            .execute()
        )
        for L in lenders.data or []:
            sla = (L.get("data") or {}).get("sla_response_days")
            if isinstance(sla, (int, float)) and sla > 0:
                sla_by_lender[L["id"]] = int(sla)
    except Exception as e:
        _log(f"sla_sweep: lender lookup failed: {e}")

    flipped = 0
    now = datetime.now(timezone.utc)
    for r in rows.data:
        sent_at_iso = r.get("sent_at")
        if not sent_at_iso:
            continue
        try:
            sent_at = datetime.fromisoformat(sent_at_iso.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        sla = sla_by_lender.get(r["lender_id"], DEFAULT_SLA_DAYS)
        if (now - sent_at) < timedelta(days=sla):
            continue
        try:
            sb.table("application_lender_threads").update({
                "status": "no_response",
                "last_error": f"SLA {sla}d exceeded; no reply from lender",
            }).eq("id", r["id"]).execute()
            flipped += 1
        except Exception as e:
            _log(f"sla_sweep: update failed row={r['id']}: {e}")
    return flipped


# ─────────────────────────────────────────────────────────────────────
# Gmail thread fetch via google_tool subprocess
# ─────────────────────────────────────────────────────────────────────


def fetch_thread_latest_body(thread_id: str) -> str | None:
    """Pull the most recent message body from a Gmail thread.
    Subprocesses out to google_tool.py to inherit the existing OAuth
    plumbing rather than wiring a second Gmail client here.

    Windows console-window suppression: when the parent daemon is run
    under pythonw.exe via PM2, pythonw doesn't have a console; but
    a child python.exe subprocess WILL allocate one unless we pass
    CREATE_NO_WINDOW. Operator sees no popups regardless.
    """
    if not thread_id:
        return None
    # Windows-only flag — on POSIX it's not defined and we just pass 0.
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "google_tool.py"),
                "gmail",
                "thread-latest",
                "--thread-id",
                thread_id,
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=creationflags,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        _log(f"gmail fetch failed thread={thread_id}: {e}")
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    body = data.get("body") or data.get("snippet") or ""
    return body if isinstance(body, str) else None


# ─────────────────────────────────────────────────────────────────────
# Claude classifier
# ─────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────
# Missing-info second-pass classifier (Phase 20, 2026-05-17)
# ─────────────────────────────────────────────────────────────────────
#
# When the main classifier returns label='info_requested', we run a
# focused second pass to extract WHICH specific artefacts the lender
# is asking for. Output is a fixed-vocabulary array that maps cleanly
# to lead_documents.doc_type values + the lead Kanban card's red chip.
#
# Vocabulary intentionally short — adding to it requires:
#   1. update MISSING_INFO_VOCAB below
#   2. update Phase 20.4 cross-reference in /api/leads/[id]/documents
#      route's POST handler (clears missing_info when matching doc lands)
#   3. update doc_type enum docs in database/049_crm_reconstructor.sql

MISSING_INFO_VOCAB = [
    "bank_statements_3mo",      # most common — last 3 months business banking
    "void_cheque",              # for ACH setup
    "drivers_license",          # owner ID
    "proof_of_ownership",       # articles, op agreement, EIN letter, etc.
    "business_license",         # state/municipal license
    "tax_returns",              # personal or business
    "signed_application",       # original app signature
    "voided_check",             # alias kept for older lender phrasing
    "other",                    # catch-all when lender wants something off-vocab
]

MISSING_INFO_PROMPT = """A lender just emailed asking for additional documentation on a funding application. Identify EVERY artefact they're requesting, mapping each to ONE of this fixed vocabulary:

{vocab}

Return JSON with two keys ONLY:
  {{
    "missing": ["bank_statements_3mo", ...],    // array; empty if nothing concrete is being requested
    "note": "<one-sentence summary of the ask, max 200 chars>"
  }}

Rules:
- Map synonyms to the closest vocab item (e.g. "3 months bank stmts" -> bank_statements_3mo, "DL" -> drivers_license, "EIN letter" -> proof_of_ownership).
- If the lender asks for something not in the vocab, include "other" AND describe it in the note.
- Empty array is correct when the email is a clarifying question, scheduling a call, or otherwise NOT requesting documents.
- No duplicates; preserve the order in which the lender mentions them.

Email body between markers:

<email>
{body}
</email>
"""


def extract_missing_info(body: str) -> dict:
    """Second-pass classifier: when the lender response is info_requested,
    extract a structured list of missing artefacts. Returns
    {"missing": [...], "note": "..."} — empty list on any error so the
    caller can fall through without surfacing a false alarm."""
    api_key = _load_env_var("ANTHROPIC_API_KEY")
    if not api_key:
        return {"missing": [], "note": ""}
    try:
        import requests
    except ImportError:
        return {"missing": [], "note": ""}

    vocab_str = "\n".join(f"  - {v}" for v in MISSING_INFO_VOCAB)
    prompt = MISSING_INFO_PROMPT.format(vocab=vocab_str, body=body[:4000])
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
    except requests.RequestException as e:
        _log(f"missing_info: network error: {e}")
        return {"missing": [], "note": ""}
    if r.status_code >= 400:
        _log(f"missing_info: Anthropic HTTP {r.status_code}")
        return {"missing": [], "note": ""}
    try:
        data = r.json()
    except ValueError:
        return {"missing": [], "note": ""}

    text = "".join(blk.get("text", "") for blk in data.get("content", []) if blk.get("type") == "text").strip()
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        return {"missing": [], "note": ""}
    try:
        parsed = json.loads(text[s : e + 1])
    except json.JSONDecodeError:
        return {"missing": [], "note": ""}

    raw_missing = parsed.get("missing") or []
    if not isinstance(raw_missing, list):
        return {"missing": [], "note": ""}
    # Filter to known vocab + dedup in order.
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in raw_missing:
        if isinstance(item, str) and item in MISSING_INFO_VOCAB and item not in seen:
            seen.add(item)
            cleaned.append(item)
    return {"missing": cleaned, "note": str(parsed.get("note", ""))[:200]}


def apply_missing_info(sb, tenant_id: str, application_id: str, missing: list[str], note: str) -> bool:
    """Resolve application -> lead, merge `missing` into the lead's
    data.missing_info jsonb array (additive — never clears existing
    entries here; the documents-upload path is what clears), then raise
    an agent_alerts row (deduped by lead_id) so CC gets one Telegram
    ping per lead per missing-info-cycle. Returns True if anything
    landed."""
    if not missing or not application_id or not tenant_id:
        return False
    # 1. Look up the application record to get lead_id from its data blob.
    try:
        app_rows = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "application")
            .eq("id", application_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        _log(f"missing_info: app lookup failed app_id={application_id}: {e}")
        return False
    if not app_rows.data:
        return False
    app_data = (app_rows.data[0].get("data") or {})
    lead_id = app_data.get("lead_id")
    if not lead_id:
        return False

    # 2. Read the lead, merge missing_info, write back.
    try:
        lead_rows = (
            sb.table("tenant_records")
            .select("id, data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "lead")
            .eq("id", lead_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        _log(f"missing_info: lead lookup failed lead_id={lead_id}: {e}")
        return False
    if not lead_rows.data:
        return False

    lead_row = lead_rows.data[0]
    lead_data = lead_row.get("data") or {}
    current = lead_data.get("missing_info") or []
    if not isinstance(current, list):
        current = []
    merged_seen = set(current)
    for item in missing:
        if item not in merged_seen:
            merged_seen.add(item)
            current.append(item)

    lead_data["missing_info"] = current
    try:
        sb.table("tenant_records").update({"data": lead_data}).eq("id", lead_row["id"]).execute()
    except Exception as e:
        _log(f"missing_info: lead update failed lead_id={lead_id}: {e}")
        return False

    # 3. Raise an operator alert. dedup_key prevents repeat pings — the
    # unique partial index on agent_alerts means a second insert for
    # the same (tenant_id, dedup_key) while the previous alert is still
    # unresolved will fail silently (which is what we want).
    try:
        sb.table("agent_alerts").insert({
            "tenant_id": tenant_id,
            "alert_type": "missing_info",
            "severity": "warn",
            "subject_type": "lead",
            "subject_id": lead_id,
            "title": f"Missing info: {', '.join(missing[:3])}{' …' if len(missing) > 3 else ''}",
            "body": note or "Lender asked for additional documentation before deciding.",
            "payload": {"missing": missing, "application_id": application_id},
            "dedup_key": f"missing_info:{lead_id}",
        }).execute()
    except Exception:
        # Duplicate alert — already open. Not an error.
        pass

    return True


CLASSIFIER_PROMPT = """You're triaging a lender's email response to a funding-shop submission. Classify the reply into EXACTLY ONE of:

- approved        — lender offered terms (factor rate, amount, advance, etc.)
- declined        — lender passed (no offer; may say "not a fit," "credit declined," etc.)
- info_requested  — lender asked for more docs / clarification / a call before deciding
- unclear         — automated bounce, out-of-office, unrelated reply, or you genuinely can't tell

Return JSON with two keys ONLY:
  {"label": "<one of above>", "summary": "<one-sentence operator-facing summary, max 200 chars>"}

The email body is between the markers below.

<email>
{body}
</email>
"""


def classify_with_claude(body: str) -> dict:
    """Call Claude to classify the lender response. Returns
    {"label": str, "summary": str} or {"label": "unclear", ...} on
    any failure. Best-effort by design."""
    api_key = _load_env_var("ANTHROPIC_API_KEY")
    if not api_key:
        return {"label": "unclear", "summary": "ANTHROPIC_API_KEY not configured"}
    try:
        import requests
    except ImportError:
        return {"label": "unclear", "summary": "requests package not installed"}

    prompt = CLASSIFIER_PROMPT.format(body=body[:4000])
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
    except requests.RequestException as e:
        return {"label": "unclear", "summary": f"network error: {e}"}
    if r.status_code >= 400:
        return {"label": "unclear", "summary": f"Anthropic HTTP {r.status_code}"}
    try:
        data = r.json()
    except ValueError:
        return {"label": "unclear", "summary": "non-JSON response from Anthropic"}
    text = ""
    for blk in data.get("content", []):
        if blk.get("type") == "text":
            text += blk.get("text", "")
    text = text.strip()
    # Try to parse strict JSON; if Claude added prose around it, find
    # the {...} block.
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        s = text.find("{")
        e = text.rfind("}")
        if s != -1 and e > s:
            try:
                parsed = json.loads(text[s : e + 1])
            except json.JSONDecodeError:
                return {"label": "unclear", "summary": "couldn't parse classifier output"}
        else:
            return {"label": "unclear", "summary": "no JSON in classifier output"}

    label = str(parsed.get("label", "")).lower().strip()
    if label not in {"approved", "declined", "info_requested", "unclear"}:
        label = "unclear"
    summary = str(parsed.get("summary", ""))[:200]
    return {"label": label, "summary": summary}


# ─────────────────────────────────────────────────────────────────────
# Lender feedback persistence (migration 069 — 2026-05-25)
# ─────────────────────────────────────────────────────────────────────
# Every terminal classification writes a lender_feedback row so the
# recommender can bias future shop-outs toward lenders who approve deals
# of similar shape (industry × revenue × FICO × time_in_business).
# Best-effort: caller wraps this in try/except; failure here must never
# roll back the thread status update.


def _persist_lender_feedback(sb, thread: dict, label: str) -> None:
    """Write one lender_feedback row for a classified thread.

    2026-05-25 second SunBiz product meeting expansion + migration 069.

    Idempotent: if a row already exists for this thread_id, skip insert.
    Outcome mapping: classifier labels → lender_feedback.outcome enum.
    Application snapshot fields pulled from tenant_records JSONB; any
    missing field is stored as NULL (not zero) so aggregate queries can
    filter on data quality.
    """
    thread_id = thread.get("id")
    application_id = thread.get("application_id")
    tenant_id = thread.get("tenant_id")
    lender_id = thread.get("lender_id")

    if not all([thread_id, application_id, tenant_id, lender_id]):
        return  # not enough context to write a useful tuple

    # Idempotency check — skip if a row already exists for this thread.
    try:
        existing = (
            sb.table("lender_feedback")
            .select("id", count="exact")
            .eq("thread_id", thread_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            return  # already recorded from a prior tick
    except Exception:
        pass  # conservative: try the insert anyway; the DB may reject dup via index

    # Outcome mapping.
    outcome_map = {
        "approved": "approved",
        "declined": "declined",
        "info_requested": "info_requested",
        "unclear": "no_response",
        "no_response": "no_response",
    }
    outcome = outcome_map.get(label, "no_response")

    # Application snapshot — pull from tenant_records JSONB.
    app_data: dict = {}
    try:
        app_row = (
            sb.table("tenant_records")
            .select("data")
            .eq("tenant_id", tenant_id)
            .eq("entity_type", "application")
            .eq("id", application_id)
            .maybeSingle()
            .execute()
        )
        app_data = (app_row.data or {}).get("data") or {}
    except Exception:
        pass  # proceed with empty snapshot; NULLs are valid

    industry = app_data.get("industry") or app_data.get("business_type")
    monthly_revenue_raw = app_data.get("monthly_revenue") or app_data.get("avg_monthly_revenue")
    monthly_revenue = float(monthly_revenue_raw) if monthly_revenue_raw is not None else None
    tib = app_data.get("time_in_business_months")
    time_in_business_months = int(tib) if tib is not None else None
    fico_raw = app_data.get("fico") or app_data.get("credit_score")
    fico = int(fico_raw) if fico_raw is not None else None
    req_raw = app_data.get("requested_amount") or app_data.get("loan_amount")
    requested_amount = float(req_raw) if req_raw is not None else None

    # Approval terms — only populated for approved threads where the
    # classifier or the email body surfaced offer terms.
    funded_amount: float | None = None
    funded_term_days: int | None = None
    funded_buy_rate: float | None = None
    if outcome == "approved":
        # Check if the application data has offer terms recorded by the time
        # the classifier runs (the offer-extractor may have already written them).
        funded_amount_raw = app_data.get("funded_amount") or app_data.get("approved_amount")
        if funded_amount_raw is not None:
            funded_amount = float(funded_amount_raw)
        term_raw = app_data.get("funded_term_days") or app_data.get("term_days")
        if term_raw is not None:
            funded_term_days = int(term_raw)
        rate_raw = app_data.get("funded_buy_rate") or app_data.get("factor_rate")
        if rate_raw is not None:
            funded_buy_rate = float(rate_raw)

    # Decline reason — first 300 chars of the summary if declined.
    decline_reason: str | None = None
    if outcome == "declined":
        # Use the classifier's own summary as the decline reason — it's
        # already normalized to operator-facing language.
        decline_reason = (thread.get("last_response_summary") or "")[:300] or None

    payload: dict = {
        "tenant_id": tenant_id,
        "lender_id": lender_id,
        "application_id": application_id,
        "thread_id": thread_id,
        "outcome": outcome,
        "industry": industry,
        "monthly_revenue": monthly_revenue,
        "time_in_business_months": time_in_business_months,
        "fico": fico,
        "requested_amount": requested_amount,
        "funded_amount": funded_amount,
        "funded_term_days": funded_term_days,
        "funded_buy_rate": funded_buy_rate,
        "decline_reason": decline_reason,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }
    # Remove None values so we don't stomp existing rows with NULL on upsert;
    # only include keys with actual data (nullable columns default to NULL anyway).
    payload = {k: v for k, v in payload.items() if v is not None or k in (
        "tenant_id", "lender_id", "application_id", "thread_id", "outcome", "extracted_at"
    )}

    sb.table("lender_feedback").insert(payload).execute()
    _log(f"lender_feedback: recorded thread={thread_id} outcome={outcome} lender={lender_id}")


# ─────────────────────────────────────────────────────────────────────
# Classifier tick
# ─────────────────────────────────────────────────────────────────────

# Map classifier label -> application_lender_threads.status enum value.
LABEL_TO_STATUS = {
    "approved": "approved",
    "declined": "declined",
    "info_requested": "info_requested",
    # unclear -> stay at 'responded' so the operator sees something
    # came in but decides themselves.
    "unclear": "responded",
}


def classify_tick(sb) -> int:
    """Find threads that have a Gmail thread_id, are still at status=sent,
    fetch the latest reply, classify, update status."""
    try:
        rows = (
            sb.table("application_lender_threads")
            .select("id, tenant_id, application_id, gmail_thread_id, status, sent_at")
            .eq("status", "sent")
            .not_.is_("gmail_thread_id", "null")
            .execute()
        )
    except Exception as e:
        _log(f"classify_tick: read failed: {e}")
        return 0
    if not rows.data:
        return 0

    classified = 0
    for r in rows.data:
        body = fetch_thread_latest_body(r["gmail_thread_id"])
        if not body:
            continue
        result = classify_with_claude(body)
        new_status = LABEL_TO_STATUS.get(result["label"], "responded")
        try:
            sb.table("application_lender_threads").update({
                "status": new_status,
                "last_response_at": datetime.now(timezone.utc).isoformat(),
                "last_response_summary": result["summary"],
            }).eq("id", r["id"]).execute()
            classified += 1
            _log(f"classified thread={r['id']} -> {new_status}: {result['summary']}")
        except Exception as e:
            _log(f"classify_tick: update failed row={r['id']}: {e}")

        # 2026-05-25 second SunBiz product meeting expansion + migration 069:
        # Persist lender intelligence tuple so the recommender can bias
        # future shop-outs toward lenders who approve deals of similar
        # shape (industry × revenue × FICO). Best-effort — write failure
        # MUST NOT roll back the thread status update already applied above.
        if new_status in ("approved", "declined", "info_requested", "no_response"):
            try:
                _persist_lender_feedback(sb, r, result["label"])
            except Exception as exc:
                _log(f"lender_feedback: write failed thread={r['id']} (non-fatal): {exc}")

        # Phase 20: when the lender asked for more info, second-pass
        # extract WHAT is missing → lead.missing_info + agent_alerts.
        if result.get("label") == "info_requested":
            try:
                mi = extract_missing_info(body)
                if mi["missing"]:
                    landed = apply_missing_info(
                        sb,
                        tenant_id=r.get("tenant_id"),
                        application_id=r.get("application_id"),
                        missing=mi["missing"],
                        note=mi["note"],
                    )
                    if landed:
                        _log(f"missing_info applied thread={r['id']} missing={mi['missing']}")
            except Exception as e:
                _log(f"missing_info: extraction crashed thread={r['id']}: {e}")
    return classified


# ─────────────────────────────────────────────────────────────────────
# Daemon
# ─────────────────────────────────────────────────────────────────────


def tick() -> tuple[int, int]:
    sb = _supabase()
    if not sb:
        _log("supabase unavailable — skipping tick")
        return 0, 0
    classified = classify_tick(sb)
    aged = sla_sweep(sb)
    return classified, aged


def loop(interval: int) -> int:
    interval = max(60, int(interval))  # never poll Gmail faster than once a minute
    _log(f"lender-response-classifier up; tick interval = {interval}s")
    # Round 3 R3-11: rate-limited crash alerts. See sequence_runner.py
    # for the rationale.
    crash_window_start = 0.0
    crash_window_count = 0
    while True:
        try:
            tick()
        except Exception as e:
            _log(f"tick crashed: {e}")
            now = time.time()
            if now - crash_window_start > 600:
                crash_window_start = now
                crash_window_count = 0
            if crash_window_count < 2:
                crash_window_count += 1
                try:
                    from notify import notify_daemon_crash  # type: ignore
                    notify_daemon_crash("lender-response-classifier", str(e))
                except Exception:
                    pass
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            _log("classifier shutting down (SIGINT)")
            return 0


def tail(count: int) -> int:
    if not LOG_PATH.exists():
        print("(no log yet)")
        return 0
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-count:]
    except OSError as e:
        print(f"read failed: {e}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Lender response classifier — Gmail label monitor")
    sub = p.add_subparsers(dest="command", required=True)

    once = sub.add_parser("once", help="Run one tick and exit")
    once.set_defaults(func=lambda _a: 0 if tick() else 0)

    lp = sub.add_parser("loop", help="Run continuously")
    lp.add_argument("--interval", type=int, default=300, help="seconds between ticks (default: 300 = 5 min)")
    lp.set_defaults(func=lambda a: loop(a.interval))

    tl = sub.add_parser("tail", help="Print the last N log lines")
    tl.add_argument("--count", type=int, default=50)
    tl.set_defaults(func=lambda a: tail(a.count))

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
