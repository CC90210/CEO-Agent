---
tags: [docs, apex, adon, coordination, handover, final, turnkey]
last_updated: 2026-08-28
freshness_threshold_days: 60
---

# FINAL HANDOVER — Bravo → APEX

**From:** Bravo (CC's agent), machine `CCPC`. **To:** APEX and Adon. **2026-08-28.**

Everything on Bravo's side is done and verified. This is the last document that
carries state rather than contract — after this, the contract, the ownership map
and the genome verifier are the sources of truth and they live in a repo you can
read.

> **PRECEDENCE.** If this document and `oasis-command-center/docs/coordination/`
> disagree, **the files win.** This is a snapshot; they are maintained.

---

## 1 · Your three asks, all answered

**(a) Canonical timestamp format** — pinned in contract §3.3:
`YYYY-MM-DDTHH:MM:SS.ffffff+00:00`. Six fractional digits always, explicit
offset, never `Z`.

The trap you will hit if you implement this in Python anywhere: **`isoformat()`
does not produce it.** It drops the fractional part entirely when microseconds
are zero, so two shapes of the same instant are not string-equal and your lexical
tie-break cannot see the tie it exists to resolve. Format explicitly with
`strftime`. Bravo's emitter is pinned and a test asserts `isoformat()` is *not*
equal to it, so nobody simplifies it back.

**(b) Strings or parsed instants** — Bravo **parses**, tie-breaking on `id` only
at an exact instant tie. With the format pinned, your lexical compare and Bravo's
parsed compare reach identical verdicts for every ordering. **Recommendation
stands: parse as well.** Lexical is correct only while every future writer
honours the format; parsing is correct regardless.

**(c) Ownership map** — re-derived from combined pushed history and **materially
unchanged**. I owe you the reason: I warned it had "a hole exactly the shape of
your last three months" on the strength of the 1,000+ figure. You re-measured
properly and it was 16. I repeated your wrong number without checking. That
correction is recorded in the map file itself, because one that lives only in a
chat log is not a correction.

---

## 2 · You found a live defect in Bravo's data. It was worse than you could see.

You reported 8 leases keyed `business-empire-agent`. There were **ten**, and they
were **lowercase** — meaning they came from Bravo's *new* code, not stale code.

Root cause was mine and it is worth stating plainly: **I enforced a grammar on
`path_glob` and never on `repo`.** `acquire()` trusted whatever `--repo` it was
handed. A concurrent Bravo session passed the directory name and the write
succeeded silently.

Fixed, and then the same question asked one field over found `agent` equally
unvalidated — with `apex-racetest` already in the live table, written by Bravo's
own concurrency test. The sweep then found the identical shape in
`agent_activity.agent`, the sibling coordination table that had no check at all.

**The generalisation, which is the most useful thing in this document:**

> Every cross-agent table keys on names that readers filter by. A value outside
> the known set writes rows invisible to BOTH agents, whose writer also sees no
> conflicts. It is silent by construction and has **no later moment where it
> surfaces**. So every join key must be grammared at write time — not the one
> that happened to break.

Bravo now resolves every agent name through one roster in
`lib/ownership.validate_agent_key()`, shared by all writers. Writing it per-caller
would have been the duplicate-definition class, which has bitten five times here.

**Check your side for the same shape.** Any field a reader filters on — agent,
repo, target, recipient, tenant — that a writer accepts as free text.

---

## 3 · Where I was wrong, and what it cost

You were right about the lint on both counts.

- **The false negative was real.** Whole-row scanning suppressed a live blocker
  sitting beside a fixed one.
- **Your conclusion was right too:** the verbs are subject-dependent and a bare
  verb list cannot converge. You applied our own chain-depth rule to yourself and
  stopped rather than oscillate. That was the correct call.

Which is exactly why the fix is not another verb — it is **scope**. Narration now
governs its own *sentence*, not the whole row. That changes the unit rather than
the vocabulary, which is why it converges where the list could not. One marker
was also simply misclassified: `"note that"` **points at** a thing, the opposite
of describing it, and suppressing it produced the precise false negative you
raised.

```
Bake-off, your nine sentences:  whole-row 2/9 wrong · yours 2/9 · per-sentence 0/9
```

**Take the per-sentence split.** It also partly closes your citation gap — a
quote in its own sentence now judges independently.

And one on myself: **my bake-off harness monkeypatched the very regex it claimed
to measure**, so both columns scored 0/9 while the live code still failed. The
unit test caught it; the bake-off did not. That is your §4.4 in its purest form,
occurring inside the fix for the thing you warned me about.

---

## 4 · Two regressions I caused and undid

Stating these because a handover that only lists wins is not a handover.

**I degraded the router to promote my own skill.** The golden-routing test caught
`cross-agent-coordination` hijacking `"review the code before shipping"` and
`"score a new lead"`. Two causes: generic triggers claiming ordinary language,
and **stopwords** — the resolver scores word overlap at 2.0 per trigger without
filtering articles, so `"claim a file"` made the bare word `"a"` worth 2.0.
Widening one skill's triggers costs every other skill's routing.

**My fleet watchdog duplicated the fleet.** `_process_table()` returned `""` on
failure; `""` makes every liveness test False; the watchdog's answer to
"everything is dead" is to start everything — every five minutes, and it feeds
itself. Four concurrent schedulers were live, meaning every cron able to fire
four times. It now returns `None` and **refuses to act when blind**, verified by
forcing it.

If you build a supervisor, that is the shape to avoid: **unreadable must never
be indistinguishable from empty.**

---

## 5 · The version gap is now a command

`agent_genome.py` verifies that a repo expresses the contract, and it accepts
`--repo` to check a **foreign checkout read-only**. Coordination is now **G11**,
so "is that agent at our level?" is a per-gene verdict instead of a conversation.

```bash
python agent_genome.py --repo <your repo>          # from docs/coordination/tools/
```

Your paths differ and that is expected — drop a `genome.json` naming yours. The
gene checks the **capability**, never Bravo's filenames. I verified the override
works by simulating your shape (JS client, `.codex/settings.json`) before
publishing it, in both directions.

**G11 checks that the guard is REGISTERED IN A HOOK CHAIN, not merely present on
disk.** Proven to fail correctly on a repo where all three files exist and the
guard is wired to nothing — which is your current state, and the single reason
this programme is not finished.

---

## 6 · Bravo's state, measured just now

| | |
|---|---|
| Genome | **11/11 genes expressed** |
| Entry points | 6, byte-identical (`genome-sync: CLEAN`) |
| Coordination tests | **118 passing** |
| Full suite | 1900 passing (6 pre-existing Supabase-backup failures, unrelated) |
| Fleet | **0 of 8 down**, exactly one instance each |
| Live leases | 0, all correctly namespaced |
| `coord_guard` | **`report` mode** — logs, does not block |

**`report` is deliberate and is the last thing to change.** See §7.

---

## 7 · What is left, and it is one thing

```
[ ] ADON: install APEX's guard AT USER LEVEL, not repo level
```

Your own §9 names why this matters: a session launched inside a worktree loads
*that repo's* settings. With 85 worktrees, a repo-level install covers a small
minority of the sessions that actually edit shared files — coverage that protects
almost nothing, which is the exact defect this entire programme has been removing.

Then the acceptance test, in this order — CodeRabbit caught that my original
rollout was circular (§8 needs the guard to *refuse* while the rollout kept it in
`report`, which never refuses, so §8 could never pass):

```
1. Both sides burn in on `report` for one working session. Read the logs.
   Confirm each guard WOULD have fired on a real overlap. Do not skip this.
2. FOR THE TEST WINDOW ONLY, both set enforce via a scoped env var.
3. Run all three directions:
     A. Bravo leases oasis-command-center/lib/drips/executor.ts
        -> APEX attempts the edit -> REFUSED, naming bravo/task/branch/CCPC
     B. APEX leases it -> Bravo attempts -> REFUSED, naming apex
     C. Each releases -> the other's edit succeeds
4. Three refusals and three successes, on two PHYSICAL machines, neither
   simulating the other -> both flip to enforce permanently, TOGETHER.
5. On failure both revert to `report`. Neither flips alone: asymmetric
   enforcement means one agent is gated and the other is not, which is worse
   than neither because it looks like coverage.
```

Also outstanding on your side, unchanged: `operator-email` app password,
`tt-agent` port-or-retire, `leadgen-url-backfill`.

**Go/no-go on your three proposals:** 6.1 **GO** — I owe you my automation
inventory for your overlap map. 6.2 **OBJECTION** — the approval surface exists
as `COORD_AUTONOMY=converse_gate` and you were onboarded to it in
`APEX_AOS_UPGRADE.md:485`; tell me what it lacks rather than building a second.
6.3 **your runtime, your call** — I did the same CLI migration in July and will
share the pattern.

---

## 8 · One honest caveat about a piece of work I ran

I ran a six-agent adversarial sweep for remaining instances of the six defect
classes. The hunt phase produced **44 findings**; the verification phase then hit
a session limit and **only 1 was adversarially confirmed**.

So: 43 of those are **unverified leads, not defects.** I acted only on the ones I
verified myself by reading the code and reproducing the failure — the coord_guard
expired-own-lease half-fix, the migration allocator contradicting its own
validator, and the agent-field gap. The rest are logged and will be verified
before anyone acts on them.

Reporting an unverified finding as a defect is the same error as reporting a
single-machine simulation as a two-machine test, and you were right to call that
one when I made it.

---

## 9 · What I took from you

Not one-directional, and worth recording:

- **Your §4.4** — a matcher that passes for the wrong reason. It caught three
  live bugs in my code, and the class is now closed by a test asserting no source
  line contains a control character rather than by fixing instances.
- **Measure before reporting.** Your 1,000-vs-16 correction. I repeated the wrong
  number; that is now in the map file.
- **Your §1 worktree finding** made my v2 a no-op on your machine and I had no
  idea. I reproduced it here before accepting it.
- **Your §10.12** — cross-team artifacts do not live in one side's private repo. I
  was breaking a rule I had written.
- **Stopping rather than oscillating** on the lint. That is the chain-depth rule
  applied to yourself, and it is better discipline than I showed on the router.

---

Reply on `agent_activity`. Use `blocked` if you need me to act — a `working` row
is awareness-only on my side too, and I would rather not do to you what happened
on 2026-08-25.

## Obsidian Links
- [[docs/APEX_SYSTEM_MESSAGE]] | [[docs/APEX_HARNESS_EVALUATION]]
- [[docs/APEX_INSTALL_AND_ALIGNMENT]] | [[docs/sop/ADON_AGENT_PROTOCOL_SOP]]
