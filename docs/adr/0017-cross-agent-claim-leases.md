---
tags: [docs, adr, decision, coordination, apex, leases]
last_updated: 2026-08-27
status: accepted
---

# ADR 0017 — Cross-agent claims become enforced path leases

**Status:** Accepted · **Date:** 2026-08-27 · **Deciders:** CC, Bravo
**Supersedes:** the claim convention in [[docs/OASIS_AGENT_COORDINATION_SPEC]] §5

## Context

Bravo (CC) and APEX (Adon) edit the same repos from two machines. Since 2026-06
the coordination contract said "claim before you touch a shared file", using the
free-text `agent_activity.files` column.

Measured over the 90 days to 2026-08-27, that convention prevented nothing:

- 203 `agent_activity` rows — both agents were participating; the wire was live.
- ~40% of rows carried any file claim; 60 `working` rows against 25 `done`, so
  claims were released only by ageing out of a 6h read window.
- **226 of 1,596 files** in `oasis-command-center` touched by both sides.
- **117 cross-side edits of the same file inside 48h**, across 65 files, the
  shortest gap under 30 minutes.
- Zero collisions ever detected.

Two independent causes:

1. **Nothing enforced it.** Every other safety rule in this repo is a PreToolUse
   hook (`secret_guard`, `exec_guard`, `state_guard`, `subprocess_guard`) and all
   held. Coordination was the only safety-critical protocol enforced by prose.
2. **Claims were not comparable.** Bravo wrote `["pipeline","settings","Turso"]`;
   APEX wrote `["services/leadgen/**","oasis:app/lead-sheets/**"]`. `claims()`
   compared them by exact string. `"pipeline"` can never equal
   `app/(dash)/pipeline/page.tsx`.

## Decision

A claim becomes a **lease on a repo-relative path**, held in shared Turso
(`coord_claims`) and enforced by a PreToolUse hook.

1. **Grammar at write time.** `coord_claim._validate_paths` refuses concept
   names, namespace prefixes, and absolute paths — judged for BOTH platforms,
   since `Path("/etc/passwd").is_absolute()` is False on Windows and APEX may be
   on macOS. An unmatchable claim is worse than none: it reads as coverage.
2. **TTL + heartbeat + explicit release,** with `SessionEnd` auto-release. A
   crashed agent's lease frees itself.
3. **One denial condition.** `coord_guard` refuses an edit only when a *different*
   agent holds a live lease covering that exact path. Own leases, unclaimed
   paths and non-repo files never block. Autonomy is untouched; only silent
   mutual reverts become impossible.
4. **Ownership is data.** `brain/OWNERSHIP_MAP.yaml`, derived from commit
   attribution, marks the measured-contested set where a lease is mandatory.
   Unmapped paths resolve to contested — unknown is contested by definition.

## Consequences

**Deliberate trade-offs, each chosen against an alternative:**

- **Fails DEGRADED, not closed.** This is a collision gate, not a security gate.
  `secret_guard` fails closed because a leaked key is worse than a blocked
  command; here, failing closed during a Turso outage would halt all editing on
  both machines — far worse than the collision it prevents. It falls back to a
  local mirror, re-evaluates expiry against the clock now, and logs staleness.
- **Resolves the acquire race rather than preventing it.** libSQL offers no
  cross-connection advisory lock, so `acquire()` rechecks after committing and
  releases if a peer's lease is older. The tiebreak `(acquired_at, id)` is a
  total order both agents compute identically without communicating.
- **Expiry is parsed, never string-compared.** APEX is a second writer; a lease
  expiring at 16:34 UTC written `18:34+02:00` sorts above a UTC now of 16:39 and
  would read as live for two hours.
- **The hook hot path imports no DB client.** The first version cost 4-5s per
  edit; a guard that slow gets switched off, and a switched-off guard is the
  original problem. Now 80ms above interpreter floor.
- **Ships in `report` mode.** Burn in, read `state/coord_guard.log`, confirm it
  *would* have fired on a real overlap, then flip. Make the guard fire once on
  purpose before trusting it.

**Costs accepted:** one more hook on every Edit/Write; a Turso dependency in the
edit path (mitigated by the mirror); and both agents must now release leases
explicitly or wait out a 90-minute TTL.

**Not decided here:** branch protection on the shared repos (requires CC's
approval — it adds PR friction for both operators) and APEX's implementation of
its side, which is specified in [[docs/APEX_SYSTEM_MESSAGE]].

## Obsidian Links
- [[docs/APEX_SYSTEM_MESSAGE]] | [[docs/sop/ADON_AGENT_PROTOCOL_SOP]]
- [[brain/AGENT_ORCHESTRATION]] | [[docs/adr/INDEX]]
