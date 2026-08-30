---
name: EXTERNAL REVIEW INTEGRATION
description: The map of external automated reviewers (CodeRabbit, Dependabot, Vercel, GitHub CI, Copilot) wired to our pushes — their scopes per repo, the current open signal, and the protocol to fold their findings into the memory + self-improvement loop instead of letting them silo in GitHub.
mutability: EVOLVING
tags: [brain, review, ci, github, vercel, dependabot, coderabbit, self-improvement, autonomy]
last_updated: 2026-08-20
freshness_threshold_days: 30
verified: 2026-07-20
---
# EXTERNAL REVIEW INTEGRATION — Fold the Bots Into the Loop

> **Why this exists.** Much of what we push is reviewed by machines — CodeRabbit reads the diff, Dependabot
> watches the dependency tree, Vercel builds + checks the deploy, GitHub Actions runs CI. **Coverage is
> conditional, not universal:** a check only fires if it's installed *and* its trigger matches (branch filter,
> PR vs. push, draft state). An ordinary feature-branch push may get *no* CI at all — so never assume "the bots
> reviewed it"; confirm which checks actually ran (`gh pr checks <n> --repo <owner>/<repo>`). That signal is
> *real, free, and continuous* — but today it dies inside a GitHub PR page. It never reaches
> `memory/MISTAKES.md`, never compounds into a validation rule, never surfaces in the nightly self-improvement
> sweep. This doc maps those reviewers, their scopes, the **current open signal**, and the protocol to make
> their findings part of our conscious loop. This is how we convert "bots comment" into "the agent gets
> permanently smarter and more autonomous."

Related: [[brain/ORCHESTRATION]] · [[brain/EXECUTION_RULES]] (Rule 16) · [[skills/ship/SKILL]] · [[skills/code-review/SKILL]] · [[brain/SUBCONSCIOUS_LAYER]]

---

## 1. The reviewer map (who reviews what, per repo)

Verified live via `gh` on 2026-07-20 across the 6 active repos. **Scope = what each bot actually looks at.**

| Reviewer | Scope (what it catches) | Trigger | Where its output lands |
|----------|------------------------|---------|------------------------|
| **CodeRabbit** (`coderabbitai`) | Line-level correctness, logic bugs, N+1 queries, missing guards, security smells, style — on the **diff** | PR opened / pushed | PR review comments (GitHub) |
| **Dependabot** | Vulnerable dependencies (CVE/GHSA), version drift; opens bump-PRs | Continuous (security DB) + schedule | Security tab alerts + auto-PRs |
| **Vercel** | Build success, deploy preview, runtime/edge warnings | Push to a connected branch | PR deployment comment + check run |
| **GitHub Actions CI** (`.github/workflows/*`) | Our own gates — `substrate-eval.yml` (parity/genome drift), `deploy-vps.yml` (tests + pip-audit + skill scan), build/lint | Push / PR | Check runs (pass/fail) |
| **GitHub Copilot review** | Correctness + style suggestions | On request | *Not installed on any repo (as of 2026-07-20)* |
| **GitHub secret scanning + push protection** | Committed secrets (keys, tokens) | Push | Security alerts / push block | *Disabled on both public repos (2026-07-20)* |

**Per-repo coverage (2026-07-20):**

| Repo | Visibility | CodeRabbit | Dependabot alerts | CI | Branch protection |
|------|-----------|-----------|-------------------|----|-------------------|
| `Business-Empire-Agent` | public | installed (thin history) | **12 open (4 high)** | substrate-eval + deploy-vps | none |
| `oasis-command-center` | public | active | on | CI `build` (red on last 5 merges) | none |
| `breeze-portal` | private | — | GHAS-gated (403) | — | none |
| `revline` | private | — | GHAS-gated | — | none — *no PR ever opened* |
| `sunbiz-funding` | private | — | GHAS-gated | — | none — *no PR ever opened* |
| `arthrisil-website` | private | — | GHAS-gated | — | none |

**Structural truth to internalize:** with **no branch protection anywhere**, every one of these signals is **advisory
only** — a red CI check or an unaddressed CodeRabbit CRITICAL does not block a merge. Signal without teeth gets
ignored. That is the root cause of the open items below.

---

## 2. Current open signal (harvested 2026-07-20 — act on these)

> These are the concrete findings the bots already produced that fell through the cracks. This is the exact
> failure mode the protocol below prevents.

| # | Severity | Repo | Finding | Source |
|---|----------|------|---------|--------|
| 1 | **CRITICAL** | oasis-command-center | Bounce-scan cron (`app/api/cron/scan-bounces/route.ts`, runs every 30 min) pass-1 `client.fetch(allUids,…)` is **unguarded against an empty search result** — a zero-match lookback throws IMAP "Invalid messageset", the route 500s, and its own watchdog alert never fires. Still live on `main`. | CodeRabbit on closed-unmerged PR #46 (`apex/bounce-twopass`) |
| 2 | HIGH | oasis-command-center | Same cron: `lookbackDays` capped at 30 vs Vercel `maxDuration=60` with **no elapsed-time bailout** in the scan loop → hard timeout kills it with no exception path (watchdog silent). | CodeRabbit PR #46 |
| 3 | HIGH | oasis-command-center | CI `build` job **failed on the last 5 consecutive merged PRs** — `package-lock.json` out of sync (`@emnapi/core` missing). Merges anyway (no protection). Vercel deploy uses a different install path so prod isn't broken, but the CI signal has been red + ignored all day. | GitHub Actions |
| 4 | HIGH | Business-Empire-Agent | **12 open Dependabot alerts (4 high):** undici WebSocket DoS (GHSA-vxpw-j846-p89q), nodemailer `raw` file-read/SSRF (GHSA-p6gq-j5cr-w38f), form-data CRLF injection (GHSA-hmw2-7cc7-3qxx), tmp path traversal (GHSA-ph9p-34f9-6g65). Bump-PRs #35/#33/#32/#31/#27 sit open + unreviewed. | Dependabot |
| 5 | MEDIUM | both public repos | **Secret scanning + push protection disabled** (free for public repos). CLAUDE.md Rule 4 records a real prior 2026-05-06 plaintext-Stripe-key leak — this is the free control that would have caught it. | GitHub settings |

**Ownership + safe handling:**
- #1/#2 live in **oasis-command-center** (shared app repo, production, and #46 was APEX's branch). Per RULE 7 + coordination etiquette, these are **surfaced for CC/APEX, not unilaterally pushed** by Bravo. Check `agent_activity.py claims` before any edit.
- #3 (lockfile) and #4 (Dependabot bumps) are lower-risk but still outward changes → confirm before merging (bumps can break; CI must pass first).
- #5 is a repo-settings mutation → CC approves (one `gh api -X PATCH` each, zero code change).

---

## 3. The gap (why signal doesn't compound today)

We already have the *ingredients* — we just never connected them:

- `scripts/core/codex_review.py` → records Codex verdicts to `task_outcomes` (state DB). **Reuse this pattern.**
- `scripts/hooks/webhook_listener.py` → FastAPI server already receiving Stripe/n8n/telegram webhooks, signature-verifying, publishing to the event bus. **Add GitHub/Vercel routes here.**
- `scripts/integrations/send_gateway.py` → the "normalize → dedupe → log → route" chokepoint pattern. **Mirror it for reviews.**
- `scripts/core/agent_self_improvement.py` → nightly sweep over `MISTAKES/PATTERNS/SESSION_LOG`. **Add `external_reviews` as a source.**
- `scripts/core/cron_engine.py` → 23 seeded jobs. **Add a harvest job.**

**What's missing:** a chokepoint + a store + a rollup. No `external_reviews` table, no `review_gateway`, no harvest cron, no memory file. A CodeRabbit finding like "N+1 in leads.tsx:42" is visible to CC only if he reads the PR; it never becomes a prevention rule.

> ### ⚠️ SUPERSEDED 2026-07-29 — the loop is BUILT and RUNNING
>
> The gap above describes the state before 2026-07-29. What actually shipped differs
> from the §4 design in one important way, so read this before building on that diagram.
>
> **Shipped:**
> - `scripts/review_harvest.py` — reads UNRESOLVED review threads **live via `gh`**
> - `scripts/review_fix.py` — applies the fix, baselines + re-runs tests, pushes to the PR branch
> - `scripts/review_loop.py` — the cron entry point that drains the queue
> - `email_playbook.detect_review_notification()` + `email_engine._enqueue_review_harvest()`
> - `[[skills/review-harvest/SKILL]]`
> - cron **`Bravo — Review Harvest`** (`*/15 * * * *`, `timeout: 1500`) — seeded and active
>
> **Design change vs §4 — no webhook, no `external_reviews` table.** §4 proposed a webhook
> chokepoint writing findings into a table. We took the opposite approach: **the email is a
> NOTIFICATION, the GitHub API is the SOURCE OF TRUTH.** A webhook payload and a DB row are
> both point-in-time snapshots; by the time either is processed the thread may be resolved,
> the line moved, or the comment edited. Acting on a stored snapshot re-litigates settled
> code. So nothing is stored except a *seen-set* (`tmp/review_threads_seen.json`), and every
> decision re-reads live `isResolved`/`isOutdated` state via GraphQL — the only place those
> fields exist (REST does not expose them).
>
> **Still open from §4:** the `external_reviews` store, the `EXTERNAL_FEEDBACK.md` rollup, and
> the nightly compounding into prevention rules (maturity level 3). Those remain worth building
> — the harvester now produces the input they need. Branch protection (level 4) is still absent
> on every repo, so all of this remains advisory.

---

## 4. The protocol (the design — build on CC's go)

Mirror the outbound-chokepoint architecture. One entry point, one store, one rollup, one memory file.

```
GitHub / Vercel / Dependabot / CodeRabbit
        │  webhook events (EXACT names): pull_request_review + pull_request_review_comment (CodeRabbit
        │  posts as GitHub reviews / inline review comments), check_run / check_suite (CI + Vercel).
        │  Dependabot: the `dependabot_alert` webhook only fires on assignee/state *changes*, NOT on new-alert
        │  creation — so POLL `GET /repos/{owner}/{repo}/dependabot/alerts?state=open` on the harvest schedule.
        ▼
scripts/hooks/webhook_listener.py            ← add routes: POST /webhooks/github/{repo}, /webhooks/vercel
        │  (verify X-Hub-Signature-256 HMAC)
        ▼
scripts/core/review_gateway.py               ← NEW: normalize → dedupe → log → event_bus
        │
        ▼
state/empire_state.db  external_reviews       ← NEW table
   (id, repo, pr_number, commit_sha, tool, severity, finding_text, file, line, finding_hash, created_at, processed_at)
        │
        ▼  nightly cron 'External Review Harvest' (04:30, after Harness Eval)
scripts/core/review_harvest.py --digest       ← NEW: group unprocessed findings by pattern
        │
        ├──▶ memory/EXTERNAL_FEEDBACK.md       ← NEW file (kept separate from hand-edited MISTAKES.md)
        │
        └──▶ scripts/core/agent_self_improvement.py   ← reads EXTERNAL_FEEDBACK; a cluster of ≥3 similar
                                                         findings → propose a code-review checklist rule
```

**Design decisions (locked defaults; override in build):**
- **Store** structured `{severity, finding, file, line}` + `finding_hash` for dedup (not raw blobs). Dedup key is `(repo, pr_number, tool, finding_hash, commit_sha)` — `commit_sha` **must** be in both the schema and the key, so the *same* finding re-flagged on a *new* commit becomes a new occurrence row (an unresolved regression), while an identical re-post on the same commit is deduped. Without `commit_sha` in the key, later-commit re-flags get silently discarded and recurrence counts corrupt.
- **Memory target** = a NEW `memory/EXTERNAL_FEEDBACK.md`, never hand-edited `MISTAKES.md` (keeps bot noise out of curated lessons; a promoted pattern graduates to MISTAKES/VALIDATION rules by hand).
- **Harvest skill** ([[skills/review-harvest/SKILL]]) runs **CLI-only** (`disable_model_invocation`) — no LLM paraphrasing of what CodeRabbit said; structured JSON only, to prevent hallucinated findings.
- **Latency** = hybrid: nightly cron for the compounding memory rollup; a webhook path for instant Telegram alert on a CRITICAL finding ("fix before shipping").
- **Vercel** has no default outbound webhook → either enable GitHub Check-Runs integration or poll the Vercel API on the cron. Start with polling (simpler, one script).

**Ship integration:** `skills/ship/SKILL.md` Phase 4 gains a substep — query `external_reviews` for the PR and append any findings under an "External Tool Findings" section, so CodeRabbit/Vercel findings surface *pre-merge* in the same report as our own code review + Validator verdict.

---

## 5. The maturity ladder (how autonomy increases)

The goal CC named — "full, conscious, autonomous power" — is reached by climbing this ladder deliberately, per repo:

1. **Advisory** (today) — bots comment; humans may or may not read.
2. **Harvested** — findings flow into `external_reviews` + `EXTERNAL_FEEDBACK.md`; nothing is lost.
3. **Compounded** — repeated finding-classes become prevention rules in the nightly sweep; the agent stops repeating them.
4. **Gated** — the two public repos get branch protection requiring CI green + CodeRabbit-CRITICAL-clear before merge; the signal grows teeth.
5. **Self-healing** — a harvested CRITICAL with an obvious fix is delegated to Codex (`task --write`), reviewed, and proposed as a PR automatically — with CC approving the merge.

Each rung is a discrete, CC-approvable step. We do not jump to rung 5; we climb.

---

## 6. Operator quick actions (the current backlog, ranked)

1. **Fix #1** (bounce-cron empty-search guard) — surgical ~3-line guard; coordinate with APEX (his branch), fresh commit, not re-open #46.
2. **Merge Dependabot bumps** #35/#33/#32/#31/#27 after a CI/test pass — routine, closes 4 high alerts.
3. **Regenerate** oasis-command-center `package-lock.json` to green the CI `build` job.
4. **Enable** secret scanning + push protection on both public repos (free, one PATCH each).
5. **Decide** branch protection on the two public repos (turns advisory signal into a merge gate — rung 4).
6. **Build** the harvest pipeline (§4) — delegate the backend to Codex; Bravo wires memory + skill.
