#!/usr/bin/env python3
"""contract_tool.py — generate, send and track client contracts.

The operator side of the OASIS contract module. Creates a contract from an
operator-authored template, mints the signing link, sends it through the
outbound chokepoint, and reports status. The client side is the public signing
page in oasis-command-center.

⚠️ UPL BOUNDARY — READ BEFORE ADDING A TEMPLATE.
Templates here are OPERATOR-AUTHORED text with variable substitution. This tool
does not draft, interpret, or advise on legal terms, and no model is called
anywhere in it. Lex (`~/APPS/Lex-Agent`) owns legal review and carries the
unauthorised-practice-of-law gate; contract LANGUAGE questions route there, and
anything novel goes to CC's actual counsel. What this file automates is
document assembly and signature tracking — mechanics, not law.

Usage:
    python scripts/integrations/contract_tool.py templates
    python scripts/integrations/contract_tool.py create --template agency_retainer \
        --lead-id <uuid> --var monthly_fee=6000 --var start_date=2026-08-15
    python scripts/integrations/contract_tool.py send --contract-id <uuid> [--apply]
    python scripts/integrations/contract_tool.py status [--contract-id <uuid>]
"""
from __future__ import annotations

CAPABILITY_META = {
    "category": "sales.contracts",
    "lifecycle": "active",
    # external_write: `send --apply` emails a real client a signing link.
    # create/templates/status are read-or-local only, but a module is
    # classified by its most dangerous path.
    "risk": "external_write",
    "triggers": [
        "generate a contract", "send a contract", "client contract",
        "signing link", "contract status", "retainer agreement",
    ],
    "owner": "bravo",
    "project": "oasis",
    # Hidden from the bridge: emailing a client a binding document is operator
    # intent, never a chat turn.
    "bridge": {"visible": False},
}

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "integrations"))

from lib.tls_trust import ensure_os_trust  # noqa: E402

ensure_os_trust()

from email_engine import load_env, get_supabase  # noqa: E402

PUBLIC_ORIGIN = "https://oasisai.work"
DEFAULT_EXPIRY_DAYS = 30

# ── Templates ────────────────────────────────────────────────────────────────
#
# Plain markdown with {placeholder} substitution. Deliberately conservative and
# deliberately short: a template nobody reads is a template nobody can defend.
# Every {var} must be supplied at create time — a contract that renders
# "{monthly_fee}" to a client is worse than no contract at all, so rendering
# hard-fails on a missing variable rather than leaving the brace.

TEMPLATES: dict[str, dict[str, Any]] = {
    "agency_retainer": {
        "label": "Agency Retainer — ongoing AI automation services",
        "required": ["client_legal_name", "monthly_fee", "start_date", "scope_summary"],
        "optional": {"term_months": "12", "notice_days": "30"},
        "body": """# AI Automation Services Agreement

**Between:** OASIS AI Solutions ("Provider") and **{client_legal_name}** ("Client")
**Effective:** {start_date}

## 1. Scope

Provider will deliver the following on an ongoing basis:

{scope_summary}

Work outside this scope is quoted separately and agreed in writing before it begins.

## 2. Fees

**${monthly_fee} per month**, invoiced on the 1st, payable within 14 days.
Fees cover the scope in section 1. Third-party costs (hosting, model usage, SaaS
licences) are passed through at cost and itemised.

## 3. Term and termination

Initial term of **{term_months} months**, continuing month to month thereafter.
Either party may terminate with **{notice_days} days** written notice. Fees for
work already performed remain payable. On termination Provider hands over
credentials, documentation and any work product Client has paid for.

## 4. Ownership

Client owns the deliverables and the data. Provider retains ownership of its
pre-existing tools, frameworks and general know-how, and may reuse those on
other engagements. Nothing here transfers Client's data or confidential
information to Provider beyond what is needed to perform the work.

## 5. Confidentiality

Each party keeps the other's non-public information confidential and uses it
only to perform this agreement. This survives termination.

## 6. What Provider does not warrant

AI systems are probabilistic. Provider will apply reasonable professional skill
but does not warrant that any automated output is error-free, and Client remains
responsible for reviewing output before relying on it for a decision that
matters. Provider's total liability is capped at the fees paid in the preceding
three months.

---

By signing below, Client agrees to the terms above.
""",
    },
    "custom_implementation": {
        "label": "Custom Agent Implementation — fixed-scope build",
        "required": ["client_legal_name", "project_fee", "start_date",
                     "deliverables", "milestone_dates"],
        "optional": {"payment_split": "50% on signing, 50% on delivery"},
        "body": """# Custom AI Agent Implementation Agreement

**Between:** OASIS AI Solutions ("Provider") and **{client_legal_name}** ("Client")
**Effective:** {start_date}

## 1. Deliverables

{deliverables}

## 2. Milestones

{milestone_dates}

Dates assume Client provides access, data and decisions within 3 business days
of request. Delays on Client's side move the dates by the same amount.

## 3. Fee

**${project_fee}** total. Payment: {payment_split}.

## 4. Changes

A change to the deliverables in section 1 is a change order: scoped, priced and
agreed in writing before work begins. Provider will not silently absorb scope.

## 5. Acceptance

Client has 10 business days from delivery of each milestone to accept or raise
specific defects in writing. Absent a written response, the milestone is
accepted.

## 6. Ownership and liability

Client owns the deliverables on final payment. Provider retains its pre-existing
tools and general know-how. AI output is probabilistic; Client reviews before
relying on it. Provider's total liability is capped at the fees paid.

---

By signing below, Client agrees to the terms above.
""",
    },
    "mutual_nda": {
        "label": "Mutual NDA — pre-engagement discussions",
        "required": ["client_legal_name", "start_date"],
        "optional": {"term_years": "2"},
        "body": """# Mutual Non-Disclosure Agreement

**Between:** OASIS AI Solutions and **{client_legal_name}**
**Effective:** {start_date}

## 1. Confidential information

Non-public information disclosed by either party in connection with evaluating a
possible working relationship — including business plans, customer data,
pricing, systems and source code.

## 2. Obligations

Each party will keep the other's confidential information private, use it only
to evaluate the possible relationship, and share it only with people who need it
and are under equivalent obligations.

## 3. Exclusions

Information that is public, already known without obligation, independently
developed, or lawfully received from a third party. Disclosure required by law
is permitted with prompt notice where legally allowed.

## 4. Term

Obligations last **{term_years} years** from the effective date. Neither party is
obliged to disclose anything, and this agreement does not create a partnership
or an obligation to proceed.

---

By signing below, both parties agree to the terms above.
""",
    },
}


class MissingVariables(Exception):
    pass


def render(template_key: str, variables: dict[str, str]) -> str:
    """Substitute variables. Hard-fails on a missing one.

    A contract that reaches a client showing a literal "{monthly_fee}" is worse
    than no contract — it is unsignable and it looks amateur. So this raises
    rather than leaving the placeholder.
    """
    tpl = TEMPLATES.get(template_key)
    if not tpl:
        raise KeyError(f"unknown template {template_key!r}; try: {', '.join(TEMPLATES)}")

    merged = {**tpl["optional"], **variables}
    missing = [k for k in tpl["required"] if not str(merged.get(k, "")).strip()]
    if missing:
        raise MissingVariables(
            f"template {template_key!r} requires: {', '.join(missing)}")

    body = tpl["body"]
    for k, v in merged.items():
        body = body.replace("{" + k + "}", str(v))

    leftover = re.findall(r"\{([a-z_][a-z0-9_]*)\}", body)
    if leftover:
        raise MissingVariables(
            f"unsubstituted placeholders remain: {sorted(set(leftover))}")
    return body


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_templates(_args) -> None:
    for key, t in TEMPLATES.items():
        print(f"  {key}")
        print(f"      {t['label']}")
        print(f"      required: {', '.join(t['required'])}")
        if t["optional"]:
            print(f"      optional: {', '.join(f'{k}={v}' for k, v in t['optional'].items())}")


def cmd_create(args) -> None:
    db = get_supabase(load_env())
    variables = dict(kv.split("=", 1) for kv in (args.var or []) if "=" in kv)

    lead = None
    if args.lead_id:
        rows = db.table("leads").select("id,name,email,company,tenant_id") \
                 .eq("id", args.lead_id).execute().data
        if not rows:
            print(f"lead {args.lead_id} not found", file=sys.stderr)
            raise SystemExit(1)
        lead = rows[0]

    client_name = args.client_name or (lead or {}).get("company") or (lead or {}).get("name")
    client_email = args.client_email or (lead or {}).get("email")
    if not client_name or not client_email:
        print("need --client-name and --client-email (or a --lead-id that has them)",
              file=sys.stderr)
        raise SystemExit(2)

    variables.setdefault("client_legal_name", client_name)
    variables.setdefault("start_date", datetime.now(timezone.utc).date().isoformat())

    body = render(args.template, variables)

    tenant_id = (lead or {}).get("tenant_id") or args.tenant_id
    if not tenant_id:
        print("need --tenant-id (the lead has none)", file=sys.stderr)
        raise SystemExit(2)

    row = {
        "tenant_id": tenant_id,
        "lead_id": args.lead_id,
        "client_name": client_name,
        "client_email": client_email,
        "contract_type": args.template,
        "terms_body": body,
        "variables": variables,
        "status": "draft",
        "expires_at": (datetime.now(timezone.utc)
                       + timedelta(days=args.expiry_days)).isoformat(),
    }

    if not args.apply:
        print(f"DRY RUN — would create {args.template} for {client_name} <{client_email}>")
        print(f"  expires in {args.expiry_days} days")
        print(f"  rendered {len(body)} chars, {len(body.splitlines())} lines")
        print("\n--- first 20 lines ---")
        print("\n".join(body.splitlines()[:20]))
        print("\nre-run with --apply to write.")
        return

    created = db.table("contracts").insert(row).execute().data[0]
    link = f"{PUBLIC_ORIGIN}/contracts/sign/{created['sign_token']}"
    print(json.dumps({
        "contract_id": created["id"],
        "status": created["status"],
        "client": f"{client_name} <{client_email}>",
        "signing_link": link,
        "expires_at": created["expires_at"],
    }, indent=2) if args.json else
        f"CREATED {created['id']}\n  {client_name} <{client_email}>\n  {link}")


def cmd_send(args) -> None:
    db = get_supabase(load_env())
    rows = db.table("contracts").select("*").eq("id", args.contract_id).execute().data
    if not rows:
        print(f"contract {args.contract_id} not found", file=sys.stderr)
        raise SystemExit(1)
    c = rows[0]
    if c["status"] not in ("draft", "sent", "viewed"):
        print(f"refusing to send a contract in status {c['status']!r}", file=sys.stderr)
        raise SystemExit(1)

    link = f"{PUBLIC_ORIGIN}/contracts/sign/{c['sign_token']}"
    subject = f"Your OASIS AI agreement — ready to sign"
    body = (
        f"Hi {c['client_name']},\n\n"
        f"Your agreement is ready. You can read it in full and sign it here:\n\n"
        f"{link}\n\n"
        f"It takes about a minute — read the terms, sign, done. The link is unique "
        f"to you, so please don't forward it.\n\n"
        f"Anything you want changed before you sign, just reply to this email and "
        f"we'll sort it out.\n\n"
        f"Conaugh McKenna\nOASIS AI Solutions\noasisai.work\n"
    )

    # V5.6 outbound chokepoint. NEVER smtplib directly — send_gateway owns CASL
    # suppression, the dedup ledger, brand footers and the outbound log.
    #
    # Signature verified against the source, not recalled: send(channel,
    # agent_source, *, to_email, subject, body_text, ...). An earlier draft of
    # this file imported a `send_email` helper that does not exist — it would
    # have raised ImportError at the exact moment CC tried to email a client a
    # contract. Confirmed against the working call site in booking_engine.py.
    from send_gateway import send as gateway_send  # noqa: E402

    res = gateway_send(
        "email",
        "contract_send",
        to_email=c["client_email"],
        subject=subject,
        body_text=body,
        lead_id=c.get("lead_id"),
        # A contract a client asked for is transactional, not marketing. The
        # wrong intent here would put a CASL marketing footer on a legal
        # document and could route it through cold-outreach suppression.
        intent="transactional",
        metadata={"contract_id": c["id"], "contract_type": c["contract_type"]},
        dry_run=not args.apply,
        db=db,
    )

    # send_gateway signals via `status`, never `ok`. Every return path in that
    # module is one of: sent | dry_run | blocked | error. Reading a nonexistent
    # `ok` key would have evaluated False on a SUCCESSFUL send, leaving the
    # contract stuck at 'draft' while the client already had the email — a
    # silent state divergence that only shows up in production. The dry run
    # surfaced it because the returned dict had no `ok` in it at all.
    status = res.get("status") if isinstance(res, dict) else None
    ok = status == "sent"
    if not args.apply:
        print(f"DRY RUN — would email {c['client_email']}")
        print(f"  subject : {subject}")
        print(f"  link    : {link}")
        print(f"  gateway : {str(res)[:220]}")
        return

    if ok:
        db.table("contracts").update({
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", c["id"]).execute()
    else:
        # blocked (CASL suppression / cooldown) and error are NOT the same as
        # sent, and neither should look like success in the exit code.
        print(f"NOT SENT — gateway status {status!r}", file=sys.stderr)

    print(json.dumps({"sent": ok, "gateway_status": status,
                      "contract_id": c["id"], "result": str(res)[:300]}, indent=2))
    if not ok:
        raise SystemExit(1)


def cmd_status(args) -> None:
    db = get_supabase(load_env())
    q = db.table("contracts").select(
        "id,client_name,client_email,contract_type,status,sent_at,first_viewed_at,signed_at,expires_at")
    if args.contract_id:
        q = q.eq("id", args.contract_id)
    rows = q.order("created_at", desc=True).limit(args.limit).execute().data or []
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print("no contracts")
        return
    print(f"{'status':<9} {'type':<24} {'client':<32} signed")
    for r in rows:
        print(f"{r['status']:<9} {r['contract_type'][:24]:<24} "
              f"{(r['client_name'] or '')[:32]:<32} {(r['signed_at'] or '—')[:19]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Client contract generation + tracking")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("templates", help="list available templates")

    c = sub.add_parser("create", help="render a contract and mint its signing link")
    c.add_argument("--template", required=True, choices=list(TEMPLATES))
    c.add_argument("--lead-id")
    c.add_argument("--tenant-id")
    c.add_argument("--client-name")
    c.add_argument("--client-email")
    c.add_argument("--var", action="append", metavar="KEY=VALUE")
    c.add_argument("--expiry-days", type=int, default=DEFAULT_EXPIRY_DAYS)
    c.add_argument("--apply", action="store_true")
    c.add_argument("--json", action="store_true")

    s = sub.add_parser("send", help="email the signing link via send_gateway")
    s.add_argument("--contract-id", required=True)
    s.add_argument("--apply", action="store_true")

    st = sub.add_parser("status", help="contract pipeline")
    st.add_argument("--contract-id")
    st.add_argument("--limit", type=int, default=20)
    st.add_argument("--json", action="store_true")

    a = ap.parse_args()
    try:
        {"templates": cmd_templates, "create": cmd_create,
         "send": cmd_send, "status": cmd_status}[a.cmd](a)
    except (MissingVariables, KeyError) as exc:
        # A missing --var is expected operator error, not a crash. Stack-tracing
        # at someone trying to write a contract is just noise in front of the
        # one line they need.
        print(f"ERROR: {exc}", file=sys.stderr)
        if isinstance(exc, MissingVariables):
            print("  supply them with: --var key=value  (repeatable)", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
