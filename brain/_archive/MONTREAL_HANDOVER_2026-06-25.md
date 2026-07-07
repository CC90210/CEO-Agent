# Session Handover — Montreal / MacBook (2026-06-25)

> **For: a fresh Claude Code chat on CC's MacBook.** CC is moving to Montreal Saturday
> and continuing work on the Mac while the PC is set up. This captures the full state of
> the long Windows session so you can continue seamlessly. Read this first, then verify
> any claim against live code before acting (claims here are a snapshot, not ground truth).

---

## 0. Machine transition (Windows → Mac) — read this first

- **All work is in git.** On the Mac, `git clone`/`pull` each repo. Windows paths
  `C:\Users\User\APPS\<repo>` map to Mac `~/APPS/<repo>` (or wherever you clone).
- **What runs WHERE — don't assume the Mac runs the services:**
  - **Dashboard** (oasis-command-center) → Vercel (auto-deploys on push to `main`). No local server needed to ship.
  - **Bridges/daemons** (`bravo-coord`, `bravo-telegram`, `dashboard-email-consumer`, `event-router`, etc.) run under **PM2 on the Windows rig**. They keep running while the PC is up. If the PC goes down, the OASIS coordination chat + email consumer pause until the Mac (or PC) runs them. To run them on the Mac you'd need `.env.agents` + the venv there.
  - **SunBiz VPS** = `ssh root@srv1723601`, code at `/srv/sunbiz/` (`ceo-agent` + `sunbiz-agent`). Always-on, independent of CC's laptop.
- **Commit author MUST be CC90210** in oasis-command-center or Vercel blocks the deploy
  (`git config user.email "214530671+CC90210@users.noreply.github.com"`, name `CC90210`).
- **oasis-command-center `main` is SHARED with APEX** (Adon's agent). Always
  `git pull --rebase origin main` before pushing — concurrent commits are normal.
- **Testing gotcha:** `server-only` modules can't be run under `tsx` directly — use
  `npx tsx --conditions=react-server <script>` (the crop test relies on this).

---

## 1. Empire north star (unchanged)

**$10,000 USD Net MRR by Sept 30, 2026.** BreezeAdvance is a paying client (David + Adon) →
SunBiz/Breeze development is open. Three SunBiz reps: **Matt** (owner, Submissions@sunbizfunding.com),
**Jordan**, **Alex** (Ezra = the owner persona, aliased to Matt).

---

## 2. What shipped this session (oasis-command-center, HEAD `102ef09`)

| Commit | What | Status |
|---|---|---|
| `d9e04c4`+`4247f51` | **Per-agent Text Torrent SMS** — each rep texts from their own number (`texttorrent_from_number`), shared API key; resolver wired into the 3 manual send sites; inbound-webhook fix so replies to per-rep DIDs route back | Shipped. Pending below. |
| `aabe63e` | **Default stage** on the Opportunity Pipeline (merchant defaulted) | Shipped, live |
| `d1c8591` | **Latency** — 3 hot-path `Promise.all` (lead-drawer timeline, scoped board reads, lead detail) | Shipped |
| `d7831c2` | **Lead/application drawer responsive overhaul** — composers open as a full-height overlay (no more compaction on half-screen/mobile); stat tiles 2×2 | Shipped. **Visual QA → Dawn.** |
| `0b4744f` | **Bulk email** on lead + application boards (multi-select already existed; added the email action; per-lead template render, queued via send_gateway for CASL/cooldown) | Shipped, owner/admin gated |
| `076932e`+`e669f72`+`102ef09` | **Signature extraction** — drop an old app → Claude locates the signature → server-side crop (sharp/pdfjs+napi-canvas) → operator confirms preview → lands on the SunBiz PDF. `102ef09` = Codex hardening (5 findings: isolate write gate, link invariant, regen-failure surfaced, PDF dim cap, PNG-magic validation). | Shipped + runtime-verified. **e2e/visual QA + Vercel deploy watch → Dawn.** |

**Business-Empire-Agent / CEO-Agent** (HEAD `9924cd0b`): `70e461a4` drop shop-out address →
`e7f6c713` fail-closed guard (`ADDRESS_SUPPRESS_ALLOWED_SOURCES={"shop_out"}`) + test (green) →
`85a5eb2e` coord fast-ack for CC chatter → `eef16bf1` pre-Montreal sync + APEX spec →
`9924cd0b` drain bulk-email queued rows in dashboard_email_consumer.

---

## 3. OPEN / PENDING — what to pick up next (prioritized)

1. **Signature feature — real-document e2e + Vercel deploy watch.** Drop a few REAL signed
   apps (PDF + photo): does vision find the signature, is the crop clean, does it render on
   the PDF? The operator-confirm step is the "right every time" net. **And confirm the Vercel
   deploy went GREEN** — new native deps (`sharp`, `pdfjs-dist`, `@napi-rs/canvas`) must build
   on Linux. They're dynamic-imported (runtime only) so the build shouldn't choke, but verify.
   "New from document" mode redirects before the signature step — only "Autofill from
   application" (existing lead) has it; adding it to the new-lead path is an easy follow-up.
2. **Shop-out address removal — VPS deploy.** Code is committed (`e7f6c713`) but runs on the
   VPS. Needs `cd /srv/sunbiz/ceo-agent && git pull --ff-only`, run
   `python scripts/tests/test_address_suppression.py`, then reload the bridge/shop-out
   process. See the VPS prompt referenced in §5.
3. **Per-agent Text Torrent — finish.** (a) live `sender_id` confirmation send (worst case =
   no-op); (b) `SUNBIZ_TT_OWNER_NUMBER=+1…` (Matt's number) in `/srv/sunbiz/ceo-agent/.env.agents`
   for automated/Helios sends; (c) optional admin "Team" view to set a rep's number for them.
4. **Latency backlog (18 items).** Highest-leverage = **JSONB expression indexes** on
   `data->>stage/status/phone/email` (drives every board + inbound-SMS read). It's a DB
   migration → verify against the live DB first + get CC's OK. Others: Applications page
   eagerly loads ~518 rows incl ~443 terminal; bundle-split ChatWidget/recharts/signature_pad.
5. **Drawer overhaul** — Dawn's pixel QA across mobile/MacBook-half/full; possible header
   sub-section (owner/collaborator dropdowns) tightening.

---

## 4. Decisions locked this session (don't relitigate)

- **TT per-agent:** ONE shared API key + per-rep sending number (`sender_id`). Manual send →
  the rep (from their number). Automated/sequence send → the **owner's number**, attributed to
  **Helios**. (Bots can't see each other in Telegram — see §6.)
- **Signature legal posture (CC-approved):** treat as a **visual reproduction of the
  already-retained signed upload**, with a **mandatory operator confirm** each time +
  signature-pad fallback. Crop is **full server-side** (sharp + pdfjs-dist + @napi-rs/canvas).
- **Bulk commercial email** is QUEUED through `send_gateway` (CASL/suppression/cooldown), never
  auto-fired per recipient.

---

## 5. Reference docs created this session (in `brain/`)

- `brain/HANDOVER_TT_PER_AGENT_FOR_ADON.md` — the per-agent TT handover for Adon/APEX.
- `brain/APEX_COORDINATION_SETUP_FOR_ADON.md` — spec for making APEX a real CLI-harness
  coordinator (the "bots can't see each other → use the agent_activity table" model).
- **VPS shop-out deploy** — a standalone prompt was drafted but is NOT committed (lost before
  commit). The full deploy steps live in **§3 item 2** above (`git pull` on
  `/srv/sunbiz/ceo-agent` → run `test_address_suppression.py` → reload the bridge/shop-out
  process). Recreate the standalone prompt if you want one for the on-box agent.

---

## 6. Coordination state (Bravo ↔ APEX ↔ Dawn ↔ Adon)

- **OASIS Telegram group** (`-5165125484`: CC + Adon + Bravo + APEX) = **human↔agent**.
  **`agent_activity` table** (bravo Supabase) = **agent↔agent** — the ONLY Bravo↔APEX path,
  because **Telegram bots cannot see each other's messages** (platform rule).
- **APEX** = Adon's agent; actively building on our TT work (commits `e33d413`/`6a5b7e7`/
  `9a32924`/`9e49c70` — TT conversations sectioning, history sync, blast guard, lead-scope filter).
- **Dawn** = doing QA on Adon's side (drawer + signature e2e handed to her via the group).
- **Bravo's group bridge** (`bravo-coord`, Windows PM2) now **instant-acks CC's chatter**
  ("yo" no longer ignored) + spawns the real Claude CLI for substance (`85a5eb2e`).
- Post status: `python scripts/integrations/agent_activity.py post --status … --task … [--mirror]`.

---

## 7. Gotchas / patterns to carry forward

- **CC90210 commit author** for oasis-command-center (Vercel block otherwise).
- **Rebase before push** (shared main with APEX).
- **Rule 8:** anything touching money/legal/send-substrate → run a Codex audit before declaring
  done (`node ~/.claude/codex-plugin/scripts/codex-companion.mjs adversarial-review --base HEAD~N --wait "…"`).
  This session it caught 5 real issues on the signature write path + the address-suppression bypass.
- **`server-only` + tsx** → `--conditions=react-server`.
- **Native deps on Vercel** (signature feature) — verify the Linux build is green.
- **State sync after work:** `python scripts/state/state_sync.py --note "…"`.
