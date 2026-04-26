# Atlas Finalization Prompt — V1.0 (Foundation build + 6-lens deep audit)

> **STATUS: ACTIVE — paste into Atlas 2026-04-26+.**
>
> **How to use:** Open Claude Code in `C:\Users\User\APPS\CFO-Agent` (fresh session). Copy the entire prompt below — everything between the two `---` rules — and paste as Atlas's first message. Atlas takes control, runs the 6-lens pass autonomously, builds what's missing, and reports back.

## Why Atlas's pass is different from Maven's

This is **Atlas's first** structural finalization. Unlike Maven (which already shipped V1.1), Atlas has:
- **0 sub-agents** in `agents/` (the directory doesn't exist)
- **0 `.claude/agents/`** native subagents
- **2 test files only** (`stress_test_bot.py`, `test_money_math.py`) for a system that handles real money math
- **No send_gateway / spend_gate / dispatch_gate equivalent** — and Atlas writes `cfo_pulse.json` (which Maven uses to gate paid spend), so a chokepoint is overdue

The good: 19/19 skills already have valid frontmatter. Identity is explicit ("not an auto-trader, research and advice only"). 71 docs in `docs/`. Pulse publisher exists at `cfo/pulse.py`.

This pass is **foundation-build-driven**: build the agent fleet, expand test coverage to math-grade rigor, formalize the cfo_pulse contract, ship a dispatch chokepoint.

---

You are Atlas, AI Chief Financial Officer. CC is authorizing a deep
finalization pass focused on YOUR specific finance/tax/research surface.
Your identity from main.py is explicit: "Not an auto-trader. Research and
advice, not automation." That constraint is load-bearing for this pass.

Take control. Don't ask permission for prescribed steps.

═══ ATLAS-SPECIFIC SURFACE ═══

You own: tax (CRA-accurate, T1/T2/GST), accounting (cashflow, AR/AP,
invoicing, books), research (SEC, fundamentals, earnings, historical
patterns), portfolio advisory (rebalancing, tax-loss harvest, position
sizing), runway/budget/wealth tracking, FIRE planning, compliance (cross-
border, departure-tax, incorporation), behavioral-finance discipline,
the cfo_pulse.json that gates Maven's paid campaigns and Bravo's spend
decisions.

You DO NOT own: trade execution (forbidden by your own SOUL — research and
advice only), marketing or ad spend (Maven), client relationships or
revenue ops (Bravo), home automation (Aura).

Auto-trade automation in `archive/trading-automation/` is LEGACY — read-
only reference, do not reactivate.

═══ KNOWN STRUCTURAL GAPS (from 2026-04-26 audit) ═══

  - 0 agents in `agents/` directory (the directory doesn't even exist).
    Maven has 19, Bravo has 14. Atlas has none. This is the largest gap.
  - 0 .claude/agents/ subagents. No native Claude Code dispatchable specialists.
  - 7 scripts in `scripts/` (lean) but only 2 test files
    (stress_test_bot.py, test_money_math.py). Most modules in cfo/,
    finance/, research/, utils/ have ZERO tests.
  - No send_gateway / spend_gate / trade_gate equivalent. You don't trade,
    so a "trade gate" isn't strictly needed — but you DO send Telegram
    alerts, write cfo_pulse.json (which Maven reads to authorize spend),
    and could in theory file taxes. Each of those needs a chokepoint.
  - 19/19 skills have valid frontmatter (already solid — DO NOT regress)
  - 71 docs/*.md (heavy documentation footprint — verify each is current)

═══ THE 6-LENS PASS ═══

Walk in order. One-paragraph finding per lens to
`docs/FINALIZATION_REPORT_2026-04-26.md` before moving on.

Lens 1 — AGENT FLEET BUILD (60 min, HIGHEST PRIORITY)
  Atlas needs sub-agents. You currently have skills (passive) but no
  dispatchable agents. Create `agents/` directory with these 8 minimum:

  1. tax-strategist.md (Opus) — quarterly review, T1/T2 prep, tax-loss
     harvest decisions, GST/HST filing
  2. portfolio-analyst.md (Opus) — position sizing, rebalancing
     recommendations, sector exposure analysis
  3. research-analyst.md (Sonnet) — SEC filings, earnings calls,
     fundamentals, historical patterns
  4. cashflow-monitor.md (Sonnet) — AR/AP aging, runway calc, burn rate
     drift detection
  5. compliance-auditor.md (Opus) — cross-border, departure-tax, CRA
     residency rules, incorporation timing
  6. behavioral-finance-guard.md (Sonnet) — anti-FOMO, anti-loss-aversion,
     overrides CC's emotion-driven trade requests with cooling-off period
  7. wealth-tracker.md (Sonnet) — net worth snapshot, FIRE projection,
     savings rate
  8. debugger.md (Sonnet) — root-cause analysis for tax math errors,
     accounting reconciliation breaks, API failures

  Each agent: YAML frontmatter (name/description/model/tools), then a body
  describing the agent's specialty + decision authority + escalation rules.
  Use Bravo's `agents/writer.md` and Maven's `agents/ad-strategist.md` as
  reference patterns.

Lens 2 — TEST COVERAGE EXPANSION (45 min)
  You have 2 test files. Money math errors are catastrophic — every
  finance/tax module needs unit tests. Minimum new tests:

  • tests/test_tax.py — CRA bracket math 2024 + 2025, GST/HST calc,
    capital gains 50% inclusion, dividend tax credit, T2 corporate tax.
    Use known-answer fixtures (e.g., $100K income → exact federal+ON owed).
  • tests/test_crypto_acb.py — adjusted-cost-base running average, FIFO
    vs ACB modes, cross-exchange merge, partial dispositions
  • tests/test_cashflow.py — AR aging buckets, runway calc, burn rate
  • tests/test_wealth.py — net worth snapshot, FIRE projection sanity
  • tests/test_pulse.py — cfo_pulse.json schema validation, freshness
    check, Maven-readable shape

  Run pytest. ALL must pass before moving on. If a test surfaces a real
  math bug, fix the production code (this is exactly why you write tests).

Lens 3 — CFO_PULSE CONTRACT WITH MAVEN (30 min, CRITICAL)
  Maven uses your cfo_pulse.json to gate paid campaign launches. If your
  pulse format drifts, Maven fails closed and CC's ad budget sits idle.

  • Read cfo/pulse.py — what's the EXACT schema? Document it in
    `brain/CFO_PULSE_CONTRACT.md` with example JSON.
  • Required fields (verify they exist): timestamp (ISO 8601 UTC),
    runway_months, mrr_actual, mrr_target, channel_budgets (dict of
    channel→{brand→{daily_cap, monthly_cap}}), spend_decisions (list of
    {channel, brand, approved_at, amount, reason}).
  • Write a schema validator (cfo/pulse_schema.py) — both publishers and
    readers run this on every write/read.
  • Stale-write protection: pulse publish() must refuse to write if
    runway calc is older than 6 hours (force a refresh).
  • Add to tests/test_pulse.py: pulse refuses to write malformed schema;
    pulse marked stale after 24h; pulse field-by-field validation.

Lens 4 — TAX-FILING + REPORT-SEND CHOKEPOINT (45 min)
  You file taxes (T1/T2/GST), send wealth reports to CC, send compliance
  alerts. Each is irreversible-ish or high-impact. Build a thin chokepoint:

  • Create `cfo/dispatch_gate.py` — single function `dispatch(action,
    payload, dry_run=False)` that gates:
      - tax-filing submissions (CRA NETFILE, GST ELS) — DRY-RUN ONLY for
        now, since you don't actually transmit yet; the gate stops you
        from accidentally wiring a real submission later
      - cfo_pulse.json writes — runs the schema validator first
      - Telegram outbound alerts — rate-limited to 30/day, no duplicates
        within 1h, kills if `ATLAS_FORCE_DRY_RUN=1`
      - Email reports to CC — same rate limit
  • Killswitch env var: `ATLAS_FORCE_DRY_RUN=1` short-circuits ALL outbound
    + writes. Verify with a test.
  • Wire telegram_bridge.py + atlas_tools.py + cfo/pulse.py to use the gate.

Lens 5 — RESEARCH PIPELINE FUNCTIONAL TESTS (30 min)
  research/ has 18 files including SEC client, finnhub, fundamentals,
  earnings calendar, historical patterns. Verify each:
  • SEC EDGAR rate-limit honored (10/sec hard limit, your client should
    self-throttle below that)
  • Finnhub API key check + fallback when key missing
  • Earnings calendar fetches at least the next 7 days for any given ticker
  • Historical patterns module returns reasonable results on a known case
    (e.g., AAPL 2008-2010 drawdown should classify as "deep correction")
  • _data_integrity.py checks: write 5 sanity tests using fixtures

Lens 6 — ADVERSARIAL REVIEW (30 min, parallel sub-agents)
  Spawn 4 sub-agents in parallel:
  1. Security: SEC/finnhub API keys in .env.agents only, no leaks in logs
     or commit history; Telegram bot token rotation plan; Supabase RLS
     policies on financial tables
  2. Math reviewer: walk every tax + ACB + capital-gains computation, hunt
     off-by-one, rounding, currency-conversion direction errors. This is
     CC's actual money — no math should be uncertain.
  3. CC's-future-self: 6 months from now, CC opens this for tax season.
     What's confusing? What's stale? Which doc is canonical?
  4. Maven's perspective: read your cfo_pulse.json schema as Maven would.
     Is the contract obvious? Could a small format change silently break
     Maven's spend gate?

═══ SUCCESS CRITERIA ═══

  [ ] agents/ directory exists with 8+ agents, all valid frontmatter
  [ ] tests/ has ≥ 6 test files (was 2), all pass
  [ ] cfo/pulse_schema.py validator exists, runs on every write+read
  [ ] cfo/dispatch_gate.py chokepoint exists, killswitch verified
  [ ] brain/CFO_PULSE_CONTRACT.md documents the Maven-readable schema
  [ ] brain/CFO_PULSE_CONTRACT.md exists and is linked from
      brain/SHARED_DB.md (cross-agent contract registry)
  [ ] Tax math verified against known-answer fixtures
  [ ] Crypto ACB verified against known-answer fixtures
  [ ] Research pipeline smoke-tested without API errors
  [ ] Adversarial findings: every Math/Security hit fixed or deferred
      with reason
  [ ] git status clean, all tests pass, commit exists, NOT pushed yet

═══ FINAL DELIVERABLE ═══

`docs/FINALIZATION_REPORT_2026-04-26.md` with 6 lens-paragraphs + 4 closing
sections (already-solid / fixed / deferred / next-up).

Post completion to Bravo AND Maven (Maven needs to know the cfo_pulse
contract is now formalized):
  python scripts/agent_inbox.py --json post --from atlas --to bravo \
    --priority normal --subject "Atlas finalization V1.0 complete" \
    --body "Report at <path>. Tests: <N>/<N>. New: 8 agents, dispatch gate,
            pulse schema validator. Math verified on known fixtures."
  python scripts/agent_inbox.py --json post --from atlas --to maven \
    --priority high --subject "cfo_pulse schema now formalized" \
    --body "See brain/CFO_PULSE_CONTRACT.md for the exact contract you
            should validate against. Schema validator at
            cfo/pulse_schema.py — copy or import for your gate logic."

Begin with Lens 1 — your largest gap is the missing agent fleet.

---

## What CC does after pasting

1. Watch Atlas complete Lens 1 — that's the agent-fleet build (8 new files in `agents/`)
2. Don't intervene mid-lens — verification gates do their job
3. Critical: Atlas's Lens 3 + Lens 4 affect Maven. Once Atlas posts the "cfo_pulse schema now formalized" message to Maven's inbox, Maven needs to update its CFO gate code accordingly. That's a follow-up cycle.
4. Read `docs/FINALIZATION_REPORT_2026-04-26.md` when Atlas finishes
5. Check Bravo's inbox: `python scripts/agent_inbox.py list --to bravo`
