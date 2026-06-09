# HANDOFF → Fable — Fleet Harmonization V2 complete
**Date:** 2026-06-09 · **Author:** Bravo · **Scope:** the whole OASIS repo fleet (18 repos)

> **TL;DR:** The agent-harness substrate that made the CEO-Agent audit (V1) work is now a
> shipped product — **`CC90210/empire-harness` v1.0.0** — and **8 repos have adopted it**.
> Every agent/product repo now boots with the same LOCKSTEP discipline contract, so whichever
> AI CC opens (OpenCode, Antigravity chat, Claude Code, Codex) in whichever repo, it wakes up
> disciplined. The fleet went from **LOCKSTEP-in-1-repo to LOCKSTEP-in-8**. Run
> `python empire-harness/tools/fleet_doctor.py --fleet <paths>` to see it.

---

## 1. The outcome CC asked for
> "I should notice a real change in how I use my AI… OpenCode, Antigravity, Claude Code, Codex."

That change is now structural, not aspirational: the **LOCKSTEP `tool_discipline` block**
(evidence-before-claims · read-before-edit + verify-after · visible todos · tool-failure fallback ·
the four-line report · plain-English-to-CC · definition-of-done) is byte-identical in the entry
points of **CEO, SunBiz, CFO, CMO, hermes, Aura, and oasis-command-center**. Any model that opens
any of those repos reads that contract first. A bundled drift test fails if a block is hand-edited
away from the fleet canonical — so it can't silently rot.

## 2. fleet_doctor table (the proof — 2026-06-09)
```
REPO                    HARNESS  LOCK  CI   TESTS  LAST COMMIT
Business-Empire-Agent   1.0.0    yes   yes  32     (CEO/Bravo — dogfood)
empire-harness          —(self)  —     CI*  5      (the source of truth)
SunBiz-Agent            1.0.0    yes   yes  2
CFO-Agent               1.0.0    yes   yes  28
CMO-Agent               1.0.0    yes   yes  13     (+ first CI added)
hermes                  1.0.0    yes   yes  17
AURA                    1.0.0    yes   yes  1      (+ first test ever)
oasis-command-center    1.0.0    yes   yes  29     (+ first agent docs)
oasis-ai-platform       —        NO    NO   0      (gated: CC live/dead)
realestate-App          —        NO    yes  3      (wave-B)
kli-hub-dashboard       —        NO    NO   0      (dormant; dev.db untracked)
```

## 3. What shipped, by phase
- **empire-harness v1.0.0** (private, tagged) — LOCKSTEP block · portable drift tests (parity/wiki/harness-sync) · tools (`harness_sync`, `fleet_doctor`, `fleet_quick_audit`, `pii_sweep`, `scan_secrets`, `check_brain_freshness`, `new_agent`) · hardened agent **scaffold** · CI template · `FLEET.md`. Mechanism: repos pin `HARNESS_VERSION` + record synced-file checksums in `harness.lock`; a test fails on drift. **Fleet upgrade = bump VERSION → `harness_sync --apply` per repo → tests prove it.** No copy-paste drift.
- **P1 — CEO residual PII:** content-keyed purge of 25 adjudicated lead strings (the audit's path-keyed V1 purge had missed content that leaked into history). Branches+tags verified clean on a fresh clone. CSV untracked.
- **P3–P5 adoption:** CEO dogfooded the core; 5 siblings + command-center adopted (LOCKSTEP + pin + drift test). **mcp.json hygiene** on SunBiz/CFO/CMO (untracked + `.template` + gitignored — verified no literal secrets). **CFO** got `brain/FINANCIAL_ACTIONS.md` (money-action register). **CMO** got its first CI. **command-center** got its first agent docs (CLAUDE/AGENTS) + `docs/SECURITY_POSTURE.md`.
- **P6 — oasis-ai-platform:** documented (`SECURITY_NOTE.md`) — calibrated: the hardcoded key is an **anon** key (public by design; rotation-hygiene, not a leak); `supabase.ts` already env-with-fallback, only `TestConnection.tsx` fully hardcoded.
- **P7 — kli-hub** empty `prisma/dev.db` untracked; `fleet_doctor` table above.

## 4. CC's outstanding decisions + actions (the only things left for you)
1. **#2 — `oasis-command-center` visibility:** PUBLIC now. Rec **private** (it exposes API routes + tenant logic). If kept public, the per-route tenant-filter RLS audit (in its `docs/SECURITY_POSTURE.md`) becomes mandatory. *Don't flip it blindly — confirm Vercel deploys from a private repo first.*
2. **#3 — `oasis-ai-platform`: live or dead?** Dead → `gh repo archive` + README banner. Live → env-migrate `TestConnection.tsx` (set Vercel env first) + RLS audit + rotate. Steps in its `SECURITY_NOTE.md`.
3. **Re-sync Mac + VPS** (P1 rewrote CEO history again): `git fetch origin && git reset --hard origin/main`.
4. **GitHub PR-ref residual** (CEO): old lead data persists in `refs/pull/*` (binary blobs; git can't rewrite) → GitHub Support purge, or make CEO-Agent private.
5. **Dormant archive list:** gritly · tiktik · ig-setter-pro · nostalgic-requests · cc-funnel · shopify-ad-engine · grapevinecottage — mark each ARCHIVE / KEEP / MINIMAL-HARDEN (I only did the zero-risk kli-hub fix).
6. **Recover stashed WIP:** CFO had uncommitted work — `git -C ~/APPS/CFO-Agent stash pop` (gmail-receipts dedupe). oasis-ai-platform's `vercel.json` WIP left untouched.

## 5. Deferred (precise, ready for a fresh session — "V2.1")
- **CEO P8:** (a) bridge windowless-flags — `bravo_cli/bridge_chat_server.py` lines 110/2299/2567/2590 add `creationflags=WINDOWLESS_FLAGS` (from `lib.subprocess_helpers`); verify the bridge still starts. (b) ~6 bare `from send_gateway import` → `from integrations.send_gateway import` (verify per-daemon path first — they work today). (c) mock `reserve_send_slot` so 4 `test_send_gateway` tests pass offline + `@pytest.mark.live`. (d) **`send_gateway.py` 163KB decomposition** — its own session, move-only.
- **Per-repo deep dives:** command-center per-route tenant-filter audit; CMO `vendor/` footprint (gitignore + pip/submodule for mcp-google-ads, ~46MB); SunBiz send-surface compliance trace; CFO per-site money-gate trace.
- **`fleet_quick_audit` scanner allowlist (instrument polish):** the secret-pattern scanner has no allowlist, so the `fleet_doctor` SECRETS column reports false positives — test fixtures (`sk-ant-1234567`, `sk_live_abcdef`), DSN format-strings (`postgresql://{…}`), and even the scanner's own spec doc (the FLEET_V2 brief line that *lists* the patterns). Verified 2026-06-09: 6 flagged hits across the fleet, **0 real**. Fix: skip `test_*`/`*.test.*`/`*.spec.*` paths + lines with `{`/`}` template markers + obviously-fake masks, so the column is signal. Until then, the SECRETS count is an upper bound, not a finding.
- **realestate-App (PropFlow):** wave-B harness adoption.

## 6. Fable's next-round playbook
The hard part is done — the harness exists and the agent fleet consumes it. Next round is **breadth + depth**, in priority order:
1. **Resolve CC's 6 decisions above** (they unblock command-center/oasis-ai-platform disposition + the dormant tier).
2. **Wave-B adoption:** run `harness_sync --apply` / the adopt pattern on PropFlow + any dormant kept alive. Use `fleet_doctor` to find the gaps (any repo showing `LOCK=NO`).
3. **Productize the instrument:** `fleet_doctor --json` is the CLI prototype of a **harness-health panel in oasis-command-center** pointed at *client* agents — the same instrument that proves CC's fleet is healthy proves a client's is. This is a real product feature, not internal tooling.
4. **`new_agent.py` is the business machine:** every new client/vertical agent (`python empire-harness/tools/new_agent.py <dir> --name X --role "…"`) ships hardened on day one — entry points + LOCKSTEP + brain + tests + CI + gitignore + harness pin. Onboard clients *with* the harness, not audit it in later.
5. **Clear V2.1** (the deferred list in §5) in a fresh session.

## Pointers
- Full per-phase record: `plans/MISSION_2026-06-09_FLEET_V2_PROGRESS.md`
- The brief: `plans/MISSION_2026-06-09_FLEET_V2.md`
- The substrate: `CC90210/empire-harness` (`FLEET.md` is the live map)
- V1 (audit remediation, V6.9.0): `plans/HANDOFF_FABLE_2026-06-09.md`
