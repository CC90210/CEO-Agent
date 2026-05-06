"""
Draft Critic — the adversarial second-opinion reviewer that runs on every
Claude-drafted outbound before it reaches send_gateway.

This is the direct answer to CC's #1 complaint in the 2026-04-19 audit:
"the AI doesn't know the social cues, it sends 10 emails that all sound
the same and miss the room." A single Claude call drafting in isolation
misses relationship stage, drifts into AI-slop phrasing, invents facts
that aren't in the interaction history, and forgets CC's voice.

The critic is a SECOND Claude instance (different prompt, different
mandate) that reviews the draft with a sharp red pen. It:
  1. Scores the draft 0–10 on persona-match + freshness + factual
     grounding + stage-fit.
  2. Names specific AI-slop phrases to remove.
  3. Rewrites problem lines or flags the whole draft for CC review.
  4. Returns a ship/revise/escalate verdict.

One retry loop: failing drafts get the critic's notes fed back to the
drafter. If the revision still fails, the draft is escalated to CC for
manual review rather than auto-sent.

USAGE FROM PYTHON
-----------------
    from draft_critic import critique, critique_and_revise

    verdict = critique(
        draft_subject="Save 10+ hours...",
        draft_body="Hi Jane, I hope this email finds you well...",
        relationship_context=ctx_from_context_builder,
        brand="oasis",
        intent="commercial",
    )
    # verdict = {
    #   "verdict": "ship" | "revise" | "escalate",
    #   "score": 6.0,
    #   "issues": [{"type": "slop_phrase", "excerpt": "...", "reason": "..."}],
    #   "suggested_revisions": {"opening": "...", "cta": "..."},
    #   "notes": "One-sentence summary"
    # }

    # OR: one call that drafts, critiques, and returns the best version
    final = critique_and_revise(
        initial_draft_fn=lambda: draft_email_claude(lead, env_vars),
        relationship_context=ctx,
        brand="oasis",
        intent="commercial",
        max_revisions=1,
    )

CLI
---
    python scripts/draft_critic.py critique \\
        --subject "Save 10+ hours/week..." \\
        --body-file /tmp/draft.txt \\
        --stage cold --brand oasis --json

DESIGN
------
1. Claude Haiku as critic. Fast enough to run inline in outreach_batch
   without making CC wait. Cheap (~$0.0002/review).
2. Structured output. Fixed schema, never free-form.
3. Single retry. If a draft fails critique and the revision also fails,
   escalate rather than infinite-loop.
4. Slop phrase database. ~25 hardcoded phrases that are always bad.
   The critic can find more but these are always-flagged.
5. Relationship-stage-aware. "Hope this finds you well" is tolerable
   to a warm lead but devastating to a cold one; the critic knows.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


# ---- Env --------------------------------------------------------------------

def load_env() -> dict[str, str]:
    env_path = PROJECT_ROOT / ".env.agents"
    if not env_path.exists():
        return {}
    env_vars: dict[str, str] = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()
    for k, v in env_vars.items():
        os.environ.setdefault(k, v)
    return env_vars


# ---- Always-flag slop phrases -----------------------------------------------
# These phrases mark a message as AI-generated / generic-template on first
# glance. Always flag them regardless of context. This list is curated, not
# exhaustive — the Claude critic finds subtler issues on top.

SLOP_PHRASES = [
    r"\bi hope this (email )?finds you well\b",
    r"\bi hope you'?re (doing )?well\b",
    # 2026-04-27: removed "i wanted to reach out|connect" — CC wants brief
    # personal-sounding cold opens like "Hi, wanted to reach out — we help
    # local X..." to ship without auto-flagging. Long-form templates with
    # "I came across your..." still flagged below.
    r"\bi came across your (profile|business|company|website)\b",
    r"\bquick question\b",
    r"\bjust checking in\b",
    r"\bdid you have a chance to\b",
    r"\bmoving forward\b",
    r"\bin today'?s (fast-?paced|competitive) (world|landscape|market)\b",
    r"\bleverage (your|the)\b",
    r"\bsynerg(y|ies|ize)\b",
    r"\bcircle back\b",
    r"\bunlock the power of\b",
    r"\btake your .* to the next level\b",
    r"\bgame[- ]chang(er|ing)\b",
    r"\brevolution(ize|ary|izing) (your|the)\b",
    r"\bat the end of the day\b",
    r"\bno pressure,? just\b",
    r"\bi wanted to (follow up|touch base)\b",
    r"\bas per my (previous|last) email\b",
    r"\blooking forward to hearing (back )?from you\b",
    r"\bplease feel free to\b",
    r"\bwithout further ado\b",
    r"\bfor what it'?s worth\b",
]

SLOP_PATTERNS = [re.compile(p, re.IGNORECASE) for p in SLOP_PHRASES]


def find_slop(body: str) -> list[dict]:
    """Scan a draft body for always-bad phrases. Returns list of hits."""
    hits: list[dict] = []
    for pat in SLOP_PATTERNS:
        for m in pat.finditer(body or ""):
            hits.append({
                "type": "slop_phrase",
                "excerpt": m.group(0),
                "pattern": pat.pattern,
                "position": m.start(),
            })
    return hits


# ---- Critic prompt ----------------------------------------------------------

CRITIC_SYSTEM_PROMPT = """You are a brutal-honest editor reviewing a sales
email before it goes out. You work for Conaugh McKenna (CC), a 22-year-old
founder of OASIS AI Solutions. CC's voice is direct, specific, unpretentious,
and never sounds like a template. He writes at 2am to a friend.

Your job: catch anything that would make a human recipient roll their eyes.
AI-slop phrases ("I hope this finds you well"). Fake urgency ("limited
spots!"). Vague flattery. Facts not supported by the interaction history.
Cold-email language in a warm-relationship context. Or the opposite —
over-familiar language in a first touch.

IMPORTANT — brief is good. CC prefers short, personal-sounding cold opens
over long pitches. A 2-3 sentence cold email like "Hi {name}, wanted to
reach out — we help local {vertical} automate their {pain}. Happy to show
a demo. — Conaugh" is FINE. Do NOT flag for length, do NOT demand more
specificity, do NOT demand a stronger CTA. Short + human + direct beats
long + polished every time. Only escalate length if the email is over 200
words AND wandering, or under 20 words AND has no actual ask.

OUTPUT SCHEMA — JSON ONLY, no markdown, no prose outside the object:
{
  "verdict":      "ship" | "revise" | "escalate",
  "score":        number 0.0 .. 10.0,
  "issues": [
    {
      "type":     one of [slop_phrase, stage_mismatch, ungrounded_claim,
                          voice_drift, over_familiar, under_specific,
                          weak_cta, length],
      "excerpt":  short substring from the draft that triggered this,
      "reason":   one sentence explaining why this is a problem
    }
  ],
  "suggested_revisions": {
    "opening_line":    "... or null",
    "cta":             "... or null",
    "whole_body":      "... or null if only small edits needed"
  },
  "notes": "One sentence summary of the critique"
}

Rules:
- verdict=ship when score >= 6.5 AND zero high-severity issues
- verdict=revise when score 4.0..6.5 — one retry is allowed
- verdict=escalate when score < 4.0 OR any issue has type=ungrounded_claim
  (fact hallucination is an automatic escalation, no auto-revision)
- Be specific. Never output "this sounds generic" — always name the phrase.
- If the draft is already great, return verdict=ship with a short notes
  field. Do not invent issues. Brief + direct is great.
- Output only the JSON object."""


REVISER_SYSTEM_PROMPT = """You are CC (Conaugh McKenna), rewriting a draft
that failed editor review. The editor's notes are below. Apply them
faithfully — rewrite the opening, fix the CTA, strip AI-slop — but keep
the original message's intent and structure.

Voice reminders:
- Write at 2am to a friend. Direct, specific, unpretentious.
- Never "hope this finds you well." Never "wanted to reach out."
- Concrete pain point in the first line if cold. Reference their words if warm.
- Short. Max 120 words for cold; longer fine for warm if content justifies it.

OUTPUT SCHEMA — JSON ONLY:
{
  "subject": "...",
  "body":    "..."
}

Output only the JSON object."""


def _call_haiku(system_prompt: str, user_msg: str, env: dict[str, str],
                max_tokens: int = 600) -> str:
    """Return the raw text response from Haiku."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic SDK not installed")
    api_key = env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing in .env.agents")
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)
    return text


def _build_critic_user_msg(
    subject: str,
    body: str,
    relationship_context: Optional[dict],
    brand: str,
    intent: str,
    slop_hits: list[dict],
) -> str:
    parts = [f"BRAND: {brand}", f"INTENT: {intent}"]
    if relationship_context:
        ctx_lines = []
        stage = relationship_context.get("relationship_stage")
        if stage:
            ctx_lines.append(f"RELATIONSHIP STAGE: {stage}")
        if relationship_context.get("name"):
            ctx_lines.append(f"RECIPIENT: {relationship_context['name']}")
        if relationship_context.get("company"):
            ctx_lines.append(f"COMPANY: {relationship_context['company']}")
        if relationship_context.get("outbound_count") is not None:
            ctx_lines.append(f"PRIOR OUTBOUND: {relationship_context['outbound_count']}")
        if relationship_context.get("inbound_count") is not None:
            ctx_lines.append(f"PRIOR INBOUND: {relationship_context['inbound_count']}")
        if relationship_context.get("sentiment_signal"):
            ctx_lines.append(f"LAST REPLY SENTIMENT: {relationship_context['sentiment_signal']}")
        if relationship_context.get("notes"):
            ctx_lines.append(f"NOTES: {str(relationship_context['notes'])[:200]}")
        if ctx_lines:
            parts.append("RELATIONSHIP CONTEXT:")
            parts.extend(f"  {l}" for l in ctx_lines)
    if slop_hits:
        parts.append("PRE-FLAGGED SLOP PHRASES (must be fixed):")
        parts.extend(f"  - {h['excerpt']}" for h in slop_hits)
    parts.append("")
    parts.append("DRAFT TO CRITIQUE:")
    parts.append(f"Subject: {subject}")
    parts.append("")
    parts.append(body[:3500])
    return "\n".join(parts)


def _validate_critic_output(raw: dict, slop_hits: list[dict]) -> dict:
    verdict = raw.get("verdict", "revise")
    if verdict not in {"ship", "revise", "escalate"}:
        verdict = "revise"
    score = float(raw.get("score", 5.0) or 5.0)
    score = max(0.0, min(10.0, score))
    issues = raw.get("issues") or []
    if not isinstance(issues, list):
        issues = []
    for h in slop_hits:
        # Prepend any slop hits that the critic missed
        already = any((i.get("excerpt") or "").lower() == h["excerpt"].lower()
                       for i in issues)
        if not already:
            issues.insert(0, {
                "type": "slop_phrase",
                "excerpt": h["excerpt"],
                "reason": "Pre-flagged always-bad phrase from the slop-phrase list.",
            })
    # Auto-downgrade verdict if there are unresolved slop hits
    if issues and verdict == "ship":
        if any(i.get("type") == "slop_phrase" for i in issues):
            verdict = "revise"
    # Auto-escalate on ungrounded_claim
    if any(i.get("type") == "ungrounded_claim" for i in issues):
        verdict = "escalate"
    return {
        "verdict": verdict,
        "score": score,
        "issues": issues[:10],
        "suggested_revisions": raw.get("suggested_revisions") or {},
        "notes": (raw.get("notes") or "")[:300],
    }


# ---- Public API -------------------------------------------------------------

def critique(
    draft_subject: str,
    draft_body: str,
    relationship_context: Optional[dict] = None,
    brand: str = "oasis",
    intent: str = "commercial",
    env: Optional[dict[str, str]] = None,
) -> dict:
    """Run the critic on a draft. Never raises. On Haiku failure returns
    a conservative verdict (escalate) with reason."""
    e = env if env is not None else load_env()
    slop_hits = find_slop(draft_body)
    try:
        user_msg = _build_critic_user_msg(
            draft_subject, draft_body, relationship_context, brand, intent, slop_hits
        )
        text = _call_haiku(CRITIC_SYSTEM_PROMPT, user_msg, e, max_tokens=800)
        raw = json.loads(text)
        return _validate_critic_output(raw, slop_hits)
    except Exception as exc:  # noqa: BLE001
        # If the critic itself fails, escalate so CC sees the draft rather
        # than shipping an un-reviewed message. Fail-closed.
        return {
            "verdict": "escalate",
            "score": 0.0,
            "issues": [{
                "type": "critic_unavailable",
                "excerpt": "",
                "reason": f"Critic failed: {exc}. Escalate to CC for manual review.",
            }] + [{
                "type": "slop_phrase",
                "excerpt": h["excerpt"],
                "reason": "Pre-flagged always-bad phrase.",
            } for h in slop_hits],
            "suggested_revisions": {},
            "notes": f"Critic call failed; escalated. Error: {exc}",
        }


def critique_draft(
    draft_subject: str,
    draft_body: str,
    relationship_context: Optional[dict] = None,
    brand: str = "oasis",
    intent: str = "commercial",
    env: Optional[dict[str, str]] = None,
) -> dict:
    """Gateway-friendly wrapper around critique().

    send_gateway wants a strict ship/reject gate. Any non-ship verdict is
    treated as reject so low-quality or unreviewed drafts fail closed before
    they ever hit SMTP.
    """
    result = critique(
        draft_subject=draft_subject,
        draft_body=draft_body,
        relationship_context=relationship_context,
        brand=brand,
        intent=intent,
        env=env,
    )
    reasons: list[str] = []
    for issue in result.get("issues") or []:
        excerpt = (issue.get("excerpt") or "").strip()
        reason = (issue.get("reason") or "").strip()
        if excerpt and reason:
            reasons.append(f"{excerpt}: {reason}")
        elif reason:
            reasons.append(reason)
        elif excerpt:
            reasons.append(excerpt)
    if result.get("notes"):
        reasons.append(str(result["notes"]))
    return {
        "verdict": "ship" if result.get("verdict") == "ship" else "reject",
        "score": result.get("score"),
        "issues": result.get("issues") or [],
        "reasons": reasons[:10],
        "notes": result.get("notes") or "",
        "raw_verdict": result.get("verdict"),
    }


def revise(
    draft_subject: str,
    draft_body: str,
    verdict: dict,
    relationship_context: Optional[dict] = None,
    brand: str = "oasis",
    intent: str = "commercial",
    env: Optional[dict[str, str]] = None,
) -> Optional[dict]:
    """Ask Haiku to rewrite the draft based on the critic's verdict.
    Returns {subject, body} or None on failure."""
    e = env if env is not None else load_env()
    try:
        user_parts = [
            f"BRAND: {brand}",
            f"INTENT: {intent}",
        ]
        if relationship_context and relationship_context.get("relationship_stage"):
            user_parts.append(f"STAGE: {relationship_context['relationship_stage']}")
        user_parts.append("")
        user_parts.append("EDITOR'S VERDICT:")
        user_parts.append(f"  Score: {verdict.get('score')}")
        user_parts.append(f"  Notes: {verdict.get('notes')}")
        if verdict.get("issues"):
            user_parts.append("  Issues:")
            for i in verdict["issues"]:
                user_parts.append(f"    - [{i.get('type')}] \"{i.get('excerpt','')}\" — {i.get('reason','')}")
        sr = verdict.get("suggested_revisions") or {}
        if sr.get("opening_line"):
            user_parts.append(f"  Suggested opening: {sr['opening_line']}")
        if sr.get("cta"):
            user_parts.append(f"  Suggested CTA: {sr['cta']}")
        user_parts.append("")
        user_parts.append("ORIGINAL DRAFT:")
        user_parts.append(f"Subject: {draft_subject}")
        user_parts.append("")
        user_parts.append(draft_body[:3500])
        text = _call_haiku(REVISER_SYSTEM_PROMPT, "\n".join(user_parts), e,
                           max_tokens=600)
        return json.loads(text)
    except Exception as exc:  # noqa: BLE001
        print(f"[draft_critic] revise failed: {exc}", file=sys.stderr)
        return None


def critique_and_revise(
    draft_subject: str,
    draft_body: str,
    relationship_context: Optional[dict] = None,
    brand: str = "oasis",
    intent: str = "commercial",
    max_revisions: int = 1,
    env: Optional[dict[str, str]] = None,
) -> dict:
    """Run critique. If verdict=revise, rewrite and critique the revision
    (up to max_revisions times). Return the best version with final status.

    Returns::
        {
          "final_verdict": "ship" | "escalate",
          "final_subject": str,
          "final_body": str,
          "revisions_made": int,
          "critique_history": [verdict1, verdict2, ...],
          "escalation_reason": str | None
        }
    """
    e = env if env is not None else load_env()
    history: list[dict] = []
    subject, body = draft_subject, draft_body
    revisions = 0

    for attempt in range(max_revisions + 1):
        v = critique(subject, body, relationship_context, brand, intent, e)
        history.append(v)
        if v["verdict"] == "ship":
            return {
                "final_verdict": "ship",
                "final_subject": subject,
                "final_body": body,
                "revisions_made": revisions,
                "critique_history": history,
                "escalation_reason": None,
            }
        if v["verdict"] == "escalate":
            return {
                "final_verdict": "escalate",
                "final_subject": subject,
                "final_body": body,
                "revisions_made": revisions,
                "critique_history": history,
                "escalation_reason": v.get("notes") or "Critic flagged escalate",
            }
        # verdict == "revise" — try rewriting
        if attempt >= max_revisions:
            break
        revised = revise(subject, body, v, relationship_context, brand, intent, e)
        if not revised or not revised.get("body"):
            break
        subject = revised.get("subject", subject)
        body = revised.get("body")
        revisions += 1

    # Ran out of revisions — escalate whatever we have
    return {
        "final_verdict": "escalate",
        "final_subject": subject,
        "final_body": body,
        "revisions_made": revisions,
        "critique_history": history,
        "escalation_reason": "Revision did not reach ship verdict within limit",
    }


# ---- CLI --------------------------------------------------------------------

def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _cmd_critique(args) -> int:
    body = args.body
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    rel_ctx: dict[str, Any] = {"relationship_stage": args.stage}
    if args.recipient:
        rel_ctx["name"] = args.recipient
    if args.company:
        rel_ctx["company"] = args.company
    v = critique(
        draft_subject=args.subject,
        draft_body=body,
        relationship_context=rel_ctx,
        brand=args.brand,
        intent=args.intent,
    )
    if args.output_json:
        _print_json(v)
    else:
        print(f"verdict: {v['verdict']}   score: {v['score']}")
        print(f"notes:   {v['notes']}")
        if v["issues"]:
            print("issues:")
            for i in v["issues"]:
                print(f"  [{i.get('type')}] \"{i.get('excerpt','')}\"")
                print(f"    -> {i.get('reason','')}")
    return 0 if v["verdict"] == "ship" else 1


def _cmd_revise_round_trip(args) -> int:
    body = args.body
    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    result = critique_and_revise(
        draft_subject=args.subject,
        draft_body=body,
        relationship_context={"relationship_stage": args.stage},
        brand=args.brand,
        intent=args.intent,
        max_revisions=args.max_revisions,
    )
    if args.output_json:
        _print_json(result)
    else:
        print(f"final verdict: {result['final_verdict']}")
        print(f"revisions: {result['revisions_made']}")
        print(f"subject: {result['final_subject']}")
        print("body:")
        print(result["final_body"])
    return 0 if result["final_verdict"] == "ship" else 1


def main() -> None:
    p = argparse.ArgumentParser(
        prog="draft_critic.py",
        description="Adversarial review of Claude-drafted outbound.",
    )
    p.add_argument("--json", dest="output_json", action="store_true")
    sub = p.add_subparsers(dest="command")

    pc = sub.add_parser("critique", help="Critique a single draft")
    pc.add_argument("--subject", required=True)
    pc.add_argument("--body", default=None)
    pc.add_argument("--body-file", dest="body_file", default=None)
    pc.add_argument("--stage", default="cold",
                     choices=["cold", "contacted", "warm", "engaged",
                              "dormant", "active_client", "lost"])
    pc.add_argument("--brand", default="oasis",
                     choices=["oasis", "conaugh_mckenna", "nostalgic"])
    pc.add_argument("--intent", default="commercial",
                     choices=["commercial", "transactional", "internal"])
    pc.add_argument("--recipient", default=None)
    pc.add_argument("--company", default=None)

    pr = sub.add_parser("revise", help="Critique and auto-rewrite")
    pr.add_argument("--subject", required=True)
    pr.add_argument("--body", default=None)
    pr.add_argument("--body-file", dest="body_file", default=None)
    pr.add_argument("--stage", default="cold",
                     choices=["cold", "contacted", "warm", "engaged",
                              "dormant", "active_client", "lost"])
    pr.add_argument("--brand", default="oasis",
                     choices=["oasis", "conaugh_mckenna", "nostalgic"])
    pr.add_argument("--intent", default="commercial",
                     choices=["commercial", "transactional", "internal"])
    pr.add_argument("--max-revisions", dest="max_revisions", type=int, default=1)

    args = p.parse_args()
    if args.command == "critique":
        if not args.body and not args.body_file:
            pc.error("Provide --body or --body-file")
        sys.exit(_cmd_critique(args))
    elif args.command == "revise":
        if not args.body and not args.body_file:
            pr.error("Provide --body or --body-file")
        sys.exit(_cmd_revise_round_trip(args))
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
