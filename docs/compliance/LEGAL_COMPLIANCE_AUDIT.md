---
description: "Unified legal-compliance status matrix across every app in the registry — AI disclosure, arbitration terms, privacy labels, DMCA — plus the open risks that need counsel or an owner decision"
tags: [compliance, legal, privacy, dmca, audit, ftc, law25]
last_updated: 2026-07-27
freshness_threshold_days: 90
verified: 2026-07-27
---

# Legal Compliance Audit — Empire-Wide

> Pass run 2026-07-27. Status reflects **source code verified on disk**, not intent.
> Related: [[brain/APP_REGISTRY]] · [[docs/compliance/DMCA_REGISTRATION_GUIDE]] · [[CONTEXT]]

## Read this first — two scope decisions

**1. Only OASIS/CC-owned apps received legal copy.** A Terms of Service is a contract
naming a specific legal entity. Of the 22 apps in [[brain/APP_REGISTRY]], most belong to
**other legal entities** — Breeze and BreezeAdvance are David's, SunBiz Funding and Blue
Rise are client lending businesses, Hermes is Emmanuel Lowinger's, Arthrisil is the Trytan
JV (Oasis holds 37.5%). Injecting OASIS's arbitration clause and `dmca@oasisai.work` into
those repos would have produced a contract naming the wrong counterparty, and on the
lending sites could conflict with state-mandated MCA disclosure text. Those repos were
**audited but not modified**. Each needs its own entity's terms, authored for that entity.

**2. The AI disclosure was added to exactly one app, because only one app uses AI.**
A static scan found no LLM SDK in Nostalgic Requests, PropFlow, or the OASIS AI Platform
marketing site. Adding "this application uses AI to process your data" to an app that does
not would be a *false* statement — the same deceptive-practice problem the FTC disclosure
exists to prevent. Only `oasis-command-center` actually calls model providers.

## Status matrix

Legend: **DONE** shipped this pass · **PRE** already existed · **N/A** trigger absent · **OPEN** gap · **OUT** not OASIS's entity to bind

| App | Owner entity | AI disclosure | Arbitration / ToS | Privacy label | DMCA |
|---|---|---|---|---|---|
| **OASIS Command Center** | OASIS AI Solutions | **DONE** | **DONE** | **DONE** | **DONE** |
| **Nostalgic Requests** | CC (personal brand) | N/A — no LLM | PRE (§15, has carve-out) | OPEN | **DONE** |
| **PropFlow** | CC + Adon 50/50 JV | N/A — no LLM | PRE | OPEN | **OPEN — needs Adon** |
| **OASIS AI Platform** (marketing) | OASIS AI Solutions | N/A — no LLM on site | PRE | OPEN | N/A — no UGC |
| Breeze Portal | David's entity | — | OUT | OUT | OUT |
| BreezeAdvance site | David's entity | — | OUT | OUT | OUT |
| SunBiz Funding site | Client (submissions) | — | OUT | OUT | OUT |
| Blue Rise site | Client | — | OUT | OUT | OUT |
| Arthrisil | Trytan JV (Oasis 37.5%) | — | OUT | OUT | OUT |
| Hermes | E. Lowinger | — | OUT | OUT | OUT |
| TIKTIK · Gritly · IG Setter · Grape Vine · On The Hill · Lafreniere | various / pre-launch | — | OUT | OUT | OUT |

## What shipped — OASIS Command Center

| Path | What |
|---|---|
| `lib/legal/constants.ts` | Single source of truth: entity, contacts, subprocessors, data matrix, arbitration carve-outs. Pages render from it so copy cannot drift from the label. |
| `components/legal/LegalPage.tsx` | Shared chrome for the three public legal routes. |
| `app/privacy/page.tsx` | Privacy policy + rendered **Privacy Data Matrix** + subprocessor table with per-path DPA status. |
| `app/terms/page.tsx` | ToS incl. binding arbitration + class-action waiver **with jurisdictional carve-outs**, AI-output disclaimer, DMCA policy (§8). |
| `app/dmca/page.tsx` | Public copyright-notice intake + § 512(c)(3) template. |
| `app/globals.css` | Scoped `.legal-prose` list/table styling. |
| `middleware.ts`, `app/layout.tsx` | `/privacy`, `/terms`, `/dmca` added to public + full-bleed route lists. Without both, the consent link 401s for the exact audience that has no account. |
| `app/signup/page.tsx` | Consent line above the submit control, covering both email and Google paths. |
| `components/forms/FormPublicClient.tsx` | **Brand-neutral** AI-processing disclosure on public forms. |
| `docs/compliance/PRIVACY_NUTRITION_LABEL.json` | Machine-readable manifest for app-store declarations. |
| `components/MainShell.tsx` | Unbranded Privacy/Terms links in the authenticated operator footer. |
| `tests/legal-compliance-drift.test.ts` | **The gate.** `npm run test:legal` fails if the privacy page, the JSON manifest, and `package.json` stop agreeing. |

### Why that last row matters

The privacy page states in prose that this app loads no third-party analytics SDK, and
lists exactly five subprocessors. Those facts live in two hand-maintained places
(`lib/legal/constants.ts` and the JSON manifest) and nothing in the type system ties either
to what the app actually does. The realistic failure is mundane — someone adds
`@vercel/analytics` during a perf sprint and a legal page silently begins telling users
something untrue.

`test:legal` closes that: it fails if any known analytics package appears in
`package.json`, if the two subprocessor lists diverge, if a DPA status disagrees between
surfaces, or if the sensitive-data flags stop matching. It was verified by deliberately
introducing each drift and confirming a non-zero exit, then restoring — a compliance test
that has never been seen to fail is not evidence of anything.

## Open risks — ranked

### 1. Sensitive identifiers reach an LLM under individual subscription terms — HIGH
The funding funnel collects `ssn`, `dob`, `ein`, `tax_id`. Uploaded application documents
are queued to `document_extraction_jobs` and processed by **the Claude CLI running on an
individual subscription** (`app/api/internal/apply-extraction/route.ts` documents this
explicitly). Consumer subscription terms are materially different from Anthropic's
Commercial Terms and DPA — there is no signed DPA covering this path, and it carries other
people's government identifiers across a border.

*This is the most consequential finding in the audit, and it is an architecture issue, not
a copy issue. No wording on a privacy page fixes it.* Options: move extraction to a
commercial API account with a DPA and zero-retention, or redact identifiers before the
document leaves the boundary. Needs CC's decision.

### 2. No French-language legal copy — MEDIUM, Quebec-specific
OASIS AI Solutions is domiciled in Montreal. Under the Charter of the French Language
(art. 55), consumer contracts of adhesion must be available in French. All legal copy
shipped in this pass is English-only.

### 3. Arbitration clause is unenforceable in the operator's own home forum — MEDIUM
Quebec CPA s. 11.1 makes pre-dispute consumer arbitration clauses and class-action waivers
unenforceable; Ontario CPA s. 7–8 is equivalent; *Uber Technologies Inc. v. Heller*, 2020
SCC 16 struck one as unconscionable. The clause was shipped **as requested**, verbatim in
substance, but with explicit carve-outs and a 30-day opt-out — because a no-carve-out
clause is not merely void in Quebec, it risks being struck as abusive under CCQ art. 1437,
which weakens the surrounding agreement. It has real effect against US users. Counsel
should confirm before it is relied on.

### 4. DMCA Designated Agent not registered — MEDIUM
Safe harbour under 17 U.S.C. § 512 requires registration with the U.S. Copyright Office.
Policy text alone does not establish it. See [[docs/compliance/DMCA_REGISTRATION_GUIDE]].

### 5. Law 25 privacy impact assessment not done — MEDIUM
Quebec Law 25 requires a PIA before communicating personal information outside Quebec and
before sensitive data is used in automated processing. Both triggers are met.

### 6. PropFlow ToS changes need Adon — LOW, blocking
PropFlow is a 50/50 JV. Amending user-facing binding terms is not a unilateral call, so it
was left untouched pending Adon's sign-off.

### 7. Nostalgic Requests governing law is stale — LOW
Its ToS names Toronto, Ontario as the arbitration seat and contact address. CC relocated to
Montreal in 2026-07. Changing an arbitration seat is a legal decision, not a find-replace,
so it was flagged rather than edited.

## Not legal advice

Every artifact in this pass is a working draft generated from observed code behaviour. None
has been reviewed by a lawyer. The arbitration, DMCA, and cross-border transfer sections in
particular are jurisdiction-sensitive and should be reviewed by Quebec counsel before being
relied on in a dispute.
