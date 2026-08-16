---
adr: 16
title: "The 20-Point Vibe-Security Matrix: audit-time expansion, single-sourced, with a tested defense mapping"
status: accepted
date: 2026-08-15
deciders: [bravo, cc]
supersedes: null
superseded_by: null
tags: [docs, adr, decision, security]
last_updated: 2026-08-15
---

# ADR-0016 — The 20-Point Vibe-Security Matrix: audit-time expansion, single-sourced, with a tested defense mapping

> Numbered 0016, not 0013: [[docs/adr/INDEX]] reserves 0013 and 0014 for the pending
> 0003/0004 collision renumber, which still needs CC's approval before anyone claims them.

## Context

This fleet already carried two matrices, and neither one audits an existing codebase.

- **Seven Production Defenses** (`prompts/_TEMPLATE_SYSTEM_PROMPT.md` § 3.1, mirrored in
  [[skills/vibe-to-execution/SKILL]]) — a *build-time* contract stamped into every system
  message the translator emits. It answers "what must this change satisfy as I write it".
- **Seven-row Anti-Slop Matrix** (`PERSONAL.md` LOCKSTEP `anti_patterns`, stamped into all six
  entry points, rationale in [[brain/EXECUTION_RULES]] § 19) — *process* defects: false
  credential claims, swallowed errors, mock data, unverified completion.

Everything else in the security layer was reactive. [[brain/EXECUTION_RULES]] §§ 13, 14, 15 and
17 each exist because a specific bug shipped and CC or Codex found it. That is four rules
written after the fact, with no mechanism for sweeping a repo *before* being bitten — and the
portfolio has grown to six repos plus client work, several of them vibe-coded at speed.

The forcing incident is on record. On **2026-05-18** Bravo declared the public form-share diff
"TypeScript clean + deploy ready" **twice**. Two Codex adversarial passes then found **nine real
bugs in that same diff**, and eight map to a distinct vulnerability class: a rate limiter keyed
on a caller-minted `lead_id`; `inline_base64` blobs accepted with attacker-controlled MIME; form
lookup by `slug` allowing cross-tenant collision and enumeration; `file_attachments` persisted
straight off the request body; SVG left in the tenant-logo MIME allowlist on a public bucket;
`read_only` enforced only as a sentence in a persona while the write tools stayed in the palette;
a `FOR ALL` RLS policy enabling a confused deputy; and operator chrome rendering over a
prospect's form. Full log: `memory/MISTAKES.md` 2026-05-18.

Two of those are the shape that matters most. The rate limiter **existed**. The role restriction
**existed**. Both defended nothing. A checklist asking "is there a rate limiter?" passes that
diff. Only a check that asks "what is the limiter keyed on?" fails it.

### What building the mapping surfaced

Drafting an explicit defense → points table produced a finding no prose review had: **five of
the twenty points — rate limiting, injection, server-side input validation, XSS, and dependency
hygiene — map to no defense at all.** The seven defenses were written for *building a feature*
and never treated untrusted input or dependency staleness as first-class concerns. "We satisfied
the production defenses" had been reading as "we passed a security review" and was never true.
That gap is the substantive reason this ADR exists; the twenty rows are the vehicle.

### A correction to the originating plan

The plan that requested this work located the seven defenses in `brain/EXECUTION_RULES.md`
§ 3.1 and cited "Defense #2/#3/#6" and "Rule 2" as the existing owners of RLS, webhook
verification and stack-trace handling. `grep -n "Defense" brain/EXECUTION_RULES.md` returns
**zero hits** — the defenses live in `prompts/_TEMPLATE_SYSTEM_PROMPT.md` and
`skills/vibe-to-execution/SKILL.md`; Rule 2 is "never paraphrase a failed attempt as a user
action". Four cross-references were wrong. Executing them verbatim would have written correct
content under anchors nothing reads. Recorded here because the plan's structure was sound and
its anchors were not, and the next imported plan will have the same property
([[brain/EXECUTION_RULES]] § 12).

## Decision

**1. The matrix is twenty points, and it is audit-time.** Each row pairs a defect with a
*mechanical* check — a grep, a query, a command — so a fresh context with no memory of the
incident runs the same audit and gets the same answer. It expands, and does not replace, the
build-time defenses.

**2. Three matrices, three jobs. They are not merged.** Build-time (7 defenses) · audit-time
(20 points) · always-on process (7 anti-slop). The rejected alternative — folding the twenty
into the Anti-Slop Matrix — would have broken `test_antislop_matrix_sync.py` (which pins exactly
seven rows across five surfaces) and conflated "the agent cut a corner" with "a stranger can
read another tenant's data". [[brain/EXECUTION_RULES]] § 21 states the separation, and
`test_section_21_keeps_the_three_matrices_distinct` enforces it.

**3. One in-repo source; copies only for audiences that cannot read the tree.** The twenty rows
live in [[skills/security-protocol/SKILL]]. Every other in-repo surface references it. The sole
exception is [[prompts/20_POINT_SECURITY_AUDITOR_SYSTEM_PROMPT]], the portable message for
Codex, Gemini, and sibling agents auditing other repos — for them a pointer is an empty
instruction, the same reasoning that makes `docs/sop/ADON_AGENT_PROTOCOL_SOP.md` restate
anti-slop. **Every deliberate copy owes a coverage test.**

**4. The defense→point mapping is a tested partition of 1..20.** Every point maps to at most one
defense; `test_every_point_is_mapped_exactly_once` fails if a point is orphaned or
double-claimed. The five unowned points are declared in the table rather than quietly absorbed —
a defense marked `N/A — <reason>` therefore also declares its points out of scope, which is the
only legitimate way to skip one.

**5. The auditor may not be the author.** Rule 8 already requires an independent Codex pass on
big tasks. For security it is the whole mechanism, not a second opinion: nine bugs survived two
of Bravo's own "production ready" claims, and separately the ADR-0015 `fnmatch` allowlist was
asserted fail-closed in an ADR, four commits and a PR body while `memory/../CLAUDE.md` walked
through it. The portable prompt therefore mandates a refutation pass that defaults to *dropping*
unproven findings.

**6. Where a point can be enforced by the database, enforce it there.** The durable fix from
2026-05-18 is `database/057_lead_documents_storage_path_check.sql` —
`CHECK (storage_path LIKE tenant_id::text || '/%')`. Application-layer allowlists are one
refactor from deletion; a constraint is not.

**7. The audit is mandatory before a public flip**, before a new app's first production deploy,
on any diff adding an unauthenticated surface / upload / webhook / tenant-scoped table, and
quarterly across the portfolio.

## Alternatives considered

| Option | Why rejected |
|---|---|
| Extend the Anti-Slop Matrix to 27 rows | Breaks the LOCKSTEP seven-row gate, forces a five-surface edit including the SOP shipped to Adon, and conflates process defects with security holes. The two are read at different moments by different readers. |
| Extend the seven Production Defenses to twenty | Changes the "all 7 apply" contract on two hand-maintained surfaces and invalidates every system message already emitted against it. Build-time and audit-time genuinely differ in scope: five points have no build-time analogue. |
| A new standalone `vibe-security-audit` skill | Splits security routing across two skills, so `capability_query resolve "security"` becomes ambiguous. Extending `security-protocol` kept one destination; its frontmatter now carries the audit vocabulary and it resolves at 18.5 against 7.0 for the next candidate. |
| Ship the matrix as documentation only | This repo's own history says an unenforced doc rots: `memory/PROPOSED_CHANGES.md` held the right schema for 79 days because no code wrote to it (ADR-0015). Hence the drift gate. |

## Consequences

**Positive.** A repo can be swept before an incident rather than after. The five-point coverage
gap in the build-time contract is now visible and stated. The router reaches the matrix from
plain-language audit requests. The portable prompt makes the standard usable by Codex, Gemini,
and any sibling or client agent without access to this tree.

**Negative.** Two surfaces now carry the twenty rows, which is a real drift hazard —
deliberately accepted, and paid for with `scripts/tests/test_20_point_security_contract.py`.
The audit itself is not free: a full twenty-point sweep across two repos is a meaningful token
spend, which is why § 21 names the trigger conditions rather than "run it often".

**Neutral.** `brain/EXECUTION_RULES.md` grows a twenty-first section. The rules file is
approaching the length where it wants an index; that is a separate decision and is not taken
here.

## Compliance

```bash
python -m pytest scripts/tests/test_20_point_security_contract.py -q   # the drift gate
python scripts/capability_query.py resolve "audit codebase for security vulnerabilities"
python scripts/build_capability_graph.py --check
```

### The validation run

The matrix was exercised on 2026-08-15 against both this repo and `oasis-command-center`, six
audit lanes each followed by an adversarial refutation pass. The numbers are themselves the
argument for Decision 5:

| | |
|---|---|
| Raw findings from the audit lanes | 59 |
| **Refuted** by the refutation pass | **14** (24%) |
| Severity **downgraded** on survivors | **35 of 45** (78%) |
| Findings claimed CRITICAL by a finder | 4 — **all four downgraded** |
| Findings surviving at HIGH | 2 |
| Findings whose cited evidence was **fabricated** | 1 — cited an index at `database/093_lead_interactions_call_columns.sql:42`; the file is 45 lines and line 42 is an `ADD COLUMN` |

An audit that only confirms its own findings would have handed CC four CRITICALs, none of
which survived contact with someone re-reading the cited line. The refutation pass is therefore
not a quality nicety in this design — it is the difference between a report and a rumour.

One further lesson came from the run's own plumbing, and it is the reason
[[CONTEXT]] now defines **decorative control**: the aggregation step matched verdicts to
findings on an exact file-path string, while the finder agents emitted repo-relative paths and
the verifier agents emitted repo-prefixed ones. Nothing matched, so every verdict was silently
discarded and all 59 findings were labelled confirmed. The verification stage ran in full, cost
its tokens, produced correct verdicts — and defended nothing, exactly like the rate limiter in
the 2026-05-18 incident that prompted the matrix. Unmatched findings now land in their own
`unverified` bucket instead of defaulting to passed.

### The gate

The gate was validated by mutation rather than by passing: ten deliberate breakages — row
deleted, row gutted, point orphaned, point double-mapped, matrix duplicated into `brain/`,
pointer removed from a defense surface, credential-file prohibition removed, refutation
requirement removed, anti-slop grown to eight rows, § 21 restating the rows — were each applied
and each caught, with the baseline restored green. A gate you have not made fail is not a gate
(ADR-0015).

## Related

[[skills/security-protocol/SKILL]] · [[prompts/20_POINT_SECURITY_AUDITOR_SYSTEM_PROMPT]] ·
[[brain/EXECUTION_RULES]] (§ 13, § 14, § 16, § 17, § 21) · [[CONTEXT]] ·
[[docs/adr/0015-evidence-gated-harness-refinement]] · [[docs/adr/INDEX]]
