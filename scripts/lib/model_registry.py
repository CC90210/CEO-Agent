"""Canonical Claude model IDs for the whole fleet.

Single source of truth so a model bump is one edit here instead of a
grep across both repos. Callers import inside try/except with the
literal as fallback, so a missing/stale clone degrades gracefully:

    from lib.model_registry import HAIKU  # via bootstrap_bravo_path()

Tiers (2026-07 Fable 5 standard):
  FABLE  — top-tier reasoning + Bravo's lead agent loop (Claude 5 / Mythos-class,
           above Opus). Architecture, hyperthink, long-horizon autonomous work.
  OPUS   — heavy code/reasoning (the workhorse coder tier).
  SONNET — customer-facing drafting + vision (ad copy, sales angle,
           bank-statement parsing).
  HAIKU  — high-volume classify/extract ticks (lender response classifier,
           sentinel sentiment, offer-term extraction, read-only validator).

Fable 5 API note: thinking is always-on (omit the `thinking` param — an explicit
`disabled` 400s), sampling params (temperature/top_p/top_k) are rejected, no
assistant prefill, and it can return stop_reason="refusal". Direct API callers
that target FABLE should opt into server-side fallbacks to OPUS. Most fleet
invocation goes through the CLI runtime, not raw API, so these constants are the
canonical reference; runtime model selection is per-chassis.
"""

FABLE = "claude-fable-5"
HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-8"
