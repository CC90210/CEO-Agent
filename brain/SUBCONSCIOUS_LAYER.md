---
name: SUBCONSCIOUS LAYER
description: The map of the automatic substrate that runs beneath conscious reasoning — hook injection, hybrid retrieval, confidence decay, memory consolidation, capability routing — and the zoom-out↔zoom-in strengthening plan that makes the conscious brain (the 7-phase cycle) rely on a powerful subconscious instead of remembering to do everything by hand.
mutability: EVOLVING
tags: [brain, subconscious, retrieval, memory, self-improvement, zoom, architecture, autonomy]
last_updated: 2026-07-20
freshness_threshold_days: 30
verified: 2026-07-20
---
# THE SUBCONSCIOUS LAYER — What Runs Beneath the Conscious Brain

> **The model.** The **conscious brain** is the 7-phase cycle (ORIENT → RECALL → ASSESS → PLAN → VERIFY →
> EXECUTE → REFLECT — see [[brain/BRAIN_LOOP]]). It is deliberate, expensive, and only as good as what it can
> *reach*. The **subconscious** is everything automatic that runs beneath it: context injected before the agent
> even reads the message, priors retrieved without being asked, confidence that decays on its own, memory that
> consolidates itself at night, routing that resolves intent to capability. **A powerful subconscious means the
> conscious brain doesn't have to remember to be smart — it just is.** This doc maps that layer and the plan to
> strengthen the connective tissue, especially the ability to zoom out to the big picture and zoom back into
> specifics without losing either.

Related: [[brain/BRAIN_LOOP]] · [[brain/RAG_SYSTEM]] · [[brain/EXECUTION_RULES]] · [[skills/self-improvement-protocol/SKILL]] · [[brain/EXTERNAL_REVIEW_INTEGRATION]]

---

## 1. The four layers of the subconscious (what runs, when, what it writes)

| Layer | Mechanism | Trigger / cadence | What it does |
|-------|-----------|-------------------|--------------|
| **Reflexes** (hooks) | `scripts/hooks/session_start.py` (5 parallel checks: state, inbox, staleness, config drift, event freshness); `UserPromptSubmit` (vocabulary injection); `PreToolUse` guards (secret/exec/state/subprocess); `SubagentStop` validator; `PreCompact` summary | Every boot / prompt / tool call | Injects big-picture state + blocks unsafe acts *before* conscious thought |
| **Recall** (retrieval) | `scripts/core/memory_retriever.py` — FTS5 (BM25) + LanceDB (384-dim MiniLM) fused by RRF; freshness decay 0.3%/day floor 0.7; `graph_activation.py` spreads to 1-hop wiki-link neighbors | On query (≤1500-token budget, <100ms) | Finds relevant priors — mistakes, patterns, facts — with file:line refs |
| **Forgetting** (aging) | `scripts/core/memory_aging.py` — exponential confidence decay C(t)=C₀·e^(−λt), λ per category (business .02 / technical .015 / architectural .005 / identity 0) | On scan / SessionStart | Marks what's gone stale so the conscious brain re-verifies instead of trusting |
| **Consolidation** (dreaming) | `scripts/auto_dream.py` (ORIENT→GATHER→CONSOLIDATE→PRUNE) — **currently detects & reports** candidate dedups / `[P]`→`[V]` promotions / over-budget trims (it computes and prints actions; it does not yet safely *write* them); `scripts/core/agent_self_improvement.py` cross-agent sweep | Manual / cron | Surfaces what *should* be consolidated — turning that into an actual safe mutation is prerequisite work |
| **Routing** (capability) | `scripts/capability_query.py` over `brain/CAPABILITY_GRAPH.json` (361 nodes) — lexical rank (triggers 2× / name 1× / desc 0.5×); optional semantic fusion (`EMPIRE_ROUTER_SEMANTIC`) | On intent resolve | Maps "what the operator wants" → the right skill/agent/script |

**This substrate is sophisticated and mostly healthy.** The weakness is not the layers — it's that they are
**decoupled from the conscious brain**: most fire only when the agent *remembers* to call them. A powerful
subconscious fires on its own.

---

## 2. The zoom-out ↔ zoom-in problem (the thing CC named)

The agent must fluidly move between the **macro** (SOUL, STATE, North Star, the capability graph as a whole)
and the **micro** (one file:line, one lead, one guard). Today that movement is **one-directional and manual**:

- **Zoom-out at boot only.** `session_start.py` injects STATE once. After that, the agent dives into specifics
  and never re-checks "did the big picture change / am I still on the path to the North Star?" A 20-turn project
  can drift scope with no alarm. **This is the real remaining gap.**
- **Zoom-in already has a net — but only for retrieval, not for mistakes.** `scripts/hooks/user_prompt_submit.py`
  *already* auto-fires `memory_retriever.query()` on each prompt and classifies the tier (see §3 items 1/4 — built).
  What it does *not* yet do is **predictive mistake-matching**: it retrieves relevant snippets, but doesn't
  specifically surface "this operation type matches a past failure — check before shipping."
- **No synthesis back up.** After a run of micro-work, nothing automatically abstracts "these 5 tasks add up to
  X; here's how it maps to strategy." `STATE.md` updates, but there's no periodic "so what?" pass.

The fix is not more layers, and not a *second* retrieval path — it's **connective tissue on the two moments that
still lack it**: **at checkpoints** (zoom-out stays honest) and **predictive-mistake-matching added to the existing
prompt hook** (zoom-in catches known failures, not just relevant snippets).

---

## 3. The strengthening plan (ranked by leverage)

Each item makes an existing subconscious capability **automatic** instead of manual. Ordered by
value-per-effort. Items marked **[safe-additive]** are read-only injections that can't break execution;
**[needs-CC]** change gated/loop behavior and want a sign-off.

### Already built (leverage the existing hook — do NOT build a second one)

- **Auto-RECALL on task entry** ✅ *implemented* — `scripts/hooks/user_prompt_submit.py` already extracts the
  prompt, classifies the tier, and calls `memory_retriever.py query --json` (top **3** snippets on T2, **5** on
  T3; skipped on T1 greetings), injecting them as context. BRAIN_LOOP Step 2 (RECALL) already fires automatically.
- **Auto context-tier classification** ✅ *implemented* — the same hook's `_tier()` classifies T1/T2/T3 from the
  prompt and scales retrieval depth accordingly.

  → **Do not add a second retrieval path** (it would duplicate tokens/latency and risk conflicting priors). The
  work here is to **measure and harden the existing hook**, and to add the mistake-matcher below *into it*.

### High leverage — the connective tissue that's genuinely missing

1. **Predictive mistake-matching — added to the existing prompt hook** `[safe-additive]` — extend
   `user_prompt_submit.py` so that, in addition to relevant snippets, it pattern-matches the operation type
   (ship / migration / public-route / send) against `MISTAKES.md` and surfaces a red-flag banner:
   *"This is a UI ship — a past one broke in incognito; check [[MISTAKES.md]] before shipping."* Turns Reflexion
   from **reactive** (after failure) into **predictive** (before it). Cheap keyword match on top of a hook that
   already runs. **This is the highest-leverage genuinely-new item.**
2. **North-Star alignment checkpoint** `[safe-additive]` — after every MODERATE+ task, compare the intent recorded
   at ASSESS vs. what was actually done; if alignment < 0.7, surface a yellow flag: *"[0.62] started fixing a form
   field, ended up refactoring RLS — still on the path to the goal?"* This is the **zoom-out net** — non-blocking,
   makes drift visible on multi-turn projects. Directly answers CC's "am I fixing a bug that's on the path to the
   North Star, or a distraction?" This is the moment that genuinely lacks connective tissue.

### Medium leverage — sharpen what exists

5. **Activation-scored routing tiebreak** `[safe-additive]` — feed the existing `skill_activation.activation_score`
   (live schema = `access_count` + `last_accessed` recency + `confidence`; **there is no success-rate/outcome
   field today**) into `resolve_intent()` as a tiebreaker, so a frequently-used, recently-used skill breaks ties
   above a rarely-touched lexical match. *If* we later want true **success-aware** ranking (promote by win-rate,
   not just usage), that requires first building a verified join between skill invocations and `task_outcomes` —
   don't claim success-weighting until that join exists.
6. **Graph-seeded retrieval** `[safe-additive]` — seed queries from high-value nodes (SOUL, current STATE focus,
   North Star) so the associative layer fires *proactively* (surfaces everything linked to the current focus),
   not only reactively after an explicit query.
7. **Give `auto_dream` a real (tested) mutation path, THEN schedule it** `[needs-CC]` — today it only *detects and
   reports* consolidation candidates. Sequence: (a) implement the actual write path (dedup / `[P]`→`[V]` promote /
   trim) behind an explicit `--apply`, (b) prove it with an integration test that seeds a duplicate and asserts it
   is consolidated, (c) *then* schedule it nightly (report-only first, `--apply` after soak). Do not schedule
   "auto-write" before the write path exists and is tested.
8. **Enable `EMPIRE_ROUTER_SEMANTIC=shadow` by default** `[needs-CC]` — start collecting lexical-vs-fused routing
   divergence data (already logs to `router_shadow.jsonl`); after ~100 samples, promote to `on`. Improves skill
   discovery without breaking determinism today.

### Lower leverage — hygiene

9. **Visible confidence markers on cited facts** `[safe-additive]` — when the agent cites a memory fact, annotate
   it with its decayed confidence (`[0.62, 14d old — verify]`) so low-confidence facts are visibly speculative.
10. **Periodic synthesis pass** `[safe-additive]` — every ~8 turns or end-of-session, a one-line "intent-then vs.
    done-now vs. still-aligned?" summary. The lightweight version of the North-Star checkpoint for long sessions.
11. **Verify `pre_compact.py` produces a real session summary** `[needs-verify]` — so context surviving a
    compaction carries "we started with X, did Y, still need Z" instead of restarting blind.

---

## 4. The principle (so we build this right, not more)

- **The subconscious should fire on its own; the conscious brain should be able to trust it.** Every item above
  moves a capability from "the agent must remember to call it" to "it happens automatically." That is the whole
  design goal — a subconscious strong enough that the conscious brain spends its expensive attention on judgment,
  not on remembering to retrieve, re-orient, or re-verify.
- **Zoom-out and zoom-in are two automatic reflexes, not one manual effort.** Zoom-in gets its priors on entry
  (items 1–2); zoom-out stays honest at checkpoints (items 3, 10). Both fire without being asked.
- **Additive-and-read-only first.** The high-leverage items are injections that cannot break execution — they add
  context, they don't gate. Build those first, soak them, then consider the `[needs-CC]` gated changes.
- **Don't add layers; connect the ones we have.** The substrate is already strong (§1). The multiplier is the
  connective tissue in §3, not new machinery.

---

## 5. Build order (safe path)

1. Extend the **existing** `scripts/hooks/user_prompt_submit.py` with predictive mistake-matching (item 1) behind
   a flag — do not add a second retrieval hook; auto-recall + tiering already live there. Soak before enforcing.
2. Add the North-Star checkpoint (item 2) as a REFLECT sub-step in the loop + a one-line ACTIVE_TASKS note.
3. Wire `auto_dream` nightly (item 7) dry-run, then promote.
4. Turn on router shadow (item 8); read the divergence log before promoting.
5. Everything gated (`[needs-CC]`) gets a CC sign-off and a soak window before enforce — never flip a gate cold.
