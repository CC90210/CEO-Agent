"""Canonical Claude model IDs for the whole fleet.

Single source of truth so a model bump is one edit here instead of a
grep across both repos. Callers import inside try/except with the
literal as fallback, so a missing/stale clone degrades gracefully:

    from lib.model_registry import HAIKU  # via bootstrap_bravo_path()

Tiers:
  HAIKU  — high-volume classify/extract ticks (lender response classifier,
           sentinel sentiment, offer-term extraction).
  SONNET — customer-facing drafting + vision (ad copy, sales angle,
           bank-statement parsing).
"""

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"
OPUS = "claude-opus-4-8"
