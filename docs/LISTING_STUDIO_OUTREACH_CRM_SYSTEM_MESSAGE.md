---
tags: [docs, vps, listing-studio, mandy-management, runbook, crm]
last_updated: 2026-08-24
---

# Listing Studio VPS Agent — Outreach CRM & Follow-Up Engine (created 2026-08-24)

> Paste the block below as the first message to a **Claude Code** session on the
> empire VPS (web terminal or SSH), launched from `/srv/listing-studio`.
> Sequel to `docs/LISTING_STUDIO_VPS_AGENT_SYSTEM_MESSAGE.md` (the five 2026-08-19
> missions). Covers the client's 2026-08-24 request: a place in the CRM for everyone
> HE reaches out to manually, conversation-hold tracking, and follow-ups that work
> TODAY — before the Twilio number exists. Hardened by a 4-lens adversarial review
> (46 findings integrated) on 2026-08-24.

---

```text
You are running on the empire VPS (Ubuntu) at /srv/listing-studio — the worker host for
Mandy Management · Listing Studio (repo: CC90210/real-estate-marketing-suite, deployed at
real-estate-marketing-suite.vercel.app). The Next.js app deploys from GitHub via Vercel;
this VPS runs the PM2 daemons (rems-render, rems-publish, plus whatever the 2026-08-19
session added — verify with pm2 list). The database is the dedicated Turso DB
`real-estate-marketing-suite` (credentials in /srv/listing-studio/.env.local — never
print their values).

WHY YOU ARE HERE (client request, 2026-08-24, verbatim intent):
The property manager is texting prospective renters manually from his own phone while
Zillow syndication is pending. His words: "I need a place on the CRM where I can put
everyone's information that I reached out to and where we are holding in conversation.
I have too many people I'm texting — some are really good — and then I send texts and
forget to get back to them. I need automated follow-ups. I don't mind putting the names,
numbers and info in, I just need to have this going now."

Product requirements:
  R1. Fast MANUAL entry of contacts (name + phone minimum, on his phone, backlog bulk-paste).
  R2. Per-contact "where we're holding": pipeline stage AND whose turn it is to reply —
      including entering someone as "they replied, I owe them" (that is his headline pain).
  R3. A surface AND a push notification that reach him with who is waiting on HIM.
      He is forgetful by his own account — a dashboard he must remember to open is not
      a solution on its own.
  R4. Automated follow-ups: REMINDER mode ships now with zero new credentials; auto-SMS
      arms later via an explicit procedure when the Twilio number lands (never silently).
  R5. Live now. Ship reminder mode even if every upgrade path is still blocked on CC.

SAFETY RULES (non-negotiable — extends the 2026-08-19 brief):
- Never print secret values. Check presence with grep -c, never cat .env files.
- Touch ONLY /srv/listing-studio. No other tenant, repo, or database.
- GIT IDENTITY (hard requirement, incident 2026-08-19): before ANY commit run
    git config user.name "CC90210"
    git config user.email "214530671+CC90210@users.noreply.github.com"
- NEVER `git push --force` to main and never rewrite already-pushed history to fix
  authorship. If origin/main has commits the VPS lacks, rebase your local commits onto
  origin/main and push normally; if the rebase conflicts, STOP and report to CC.
- All app code changes: commit + push to main; confirm the Vercel deployment reaches
  READY **and that the READY deployment's commit SHA equals origin/main HEAD** before
  claiming done. /api/health returning ok proves nothing about WHICH build is live.
- After changing daemon code: pm2 restart <daemon> && pm2 save, then show pm2 logs
  proving a clean start (no restart loop).
- Every outbound SMS/DM/digest you test goes to CC's own number/handle/chat FIRST —
  never a real lead, never the client's own channel until CC says go.
- TEST DATA IS RADIOACTIVE: any seeded/synthetic lead uses CC's own phone number ONLY
  and a name prefixed "ZZTEST". Before close-out, delete every ZZTEST row and prove
  zero remain (SELECT COUNT(*) by the marker). A live queue is not a test fixture —
  a forgotten seeded row becomes an automated text to a stranger weeks later.
- If live code contradicts this brief, trust the code and flag the discrepancy to CC.
  This brief was written WITHOUT repo access — column names, paths, and route names are
  intent, not gospel. Read the live schema first and REUSE what the 0013-series already
  built instead of duplicating it.

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — VERIFY LIVE STATE & CLOSE OUT 2026-08-19 (before any new work)
═══════════════════════════════════════════════════════════════════════════════
The 2026-08-19 session built: CRM lead profiles + touch timeline (migration 0013 series),
vertical lifecycle leads page, Zernio DM inbox poller, and an SMS follow-up worker that
fail-closes without Twilio creds. Its deploy was blocked because Vercel refuses commits
authored as root@srv, and the 0013 rename left two temporary compatibility views pending
drop. Verify what actually landed:

  1. pm2 list && cd /srv/listing-studio && git status && git log --oneline -8
  2. git config user.name / user.email — if not CC90210, fix NOW.
  3. DEPLOY TRUTH: git fetch, then compare origin/main HEAD against the commit SHA of
     the latest READY Vercel PRODUCTION deployment (Vercel CLI/API, or probe a route/
     field that only exists post-0013). The 08-19 failure shape was commits ON
     origin/main that Vercel refused to BUILD — "is it pushed?" answers yes while prod
     runs a 2-day-old build. If the deployed SHA lags origin/main: fix git identity,
     push a new correctly-authored commit (empty is fine) to trigger a fresh build, and
     wait for READY at the right SHA. If local commits were never pushed: rebase onto
     origin/main if diverged (never force-push), then push. Nothing else proceeds until
     production verifiably runs the 0013-series code.
  4. Migrations: ls the migrations dir; note the highest applied number; new work uses
     the next free number.
  5. Compat views: read the current view list + DDL from sqlite_master and SAVE that DDL
     to a dated file. Take a DB dump (turso db shell .dump or equivalent) to a dated file
     on the VPS. Only then, and only after step 3's SHA check passes, drop the views as
     the 08-19 session documented; verify app health after.
  6. Env presence (counts only, exact names): grep -c TWILIO_ACCOUNT_SID .env* ;
     grep -c TELEGRAM_BOT_TOKEN_MANDY .env* ; grep -c TELEGRAM_CHAT_ID_MANDY .env* .
     A generic TELEGRAM_BOT_TOKEN match does NOT count — Bravo/empire bot tokens must
     never carry Mandy client data (recorded rule). Also probe the repo/env for ANY
     existing email-send capability (Resend/SMTP/nodemailer/etc.) — it decides the
     digest channel in Mission 8. Missing Twilio creds do NOT block this brief.
  7. Read the ACTUAL schema: leads columns (incl. the 0013 consent columns and the SMS
     worker's consent-gate predicate — read the worker's WHERE clause, you must write
     the SAME columns it reads), how dormancy is stored (the 0819 brief specified a
     dormant FLAG, not a status value — confirm), whether STOP suppression already has
     a column, the timeline table's event types, and — critically — the TIMESTAMP
     CONVENTION the 0013 tables use (epoch integer vs string format). Every new
     timestamp column and comparison in this brief uses THAT convention, and "now" is
     generated on the same side (all-SQL or all-app) so comparisons are exact — mixing
     JS ISO strings ('...T...Z') with SQLite datetime('now') ('... ...') compares
     lexicographically and silently misfires on same-day due times.
  8. Note any CHECK constraints on status / event type / hold columns. SQLite cannot
     ALTER a CHECK; if a new value below would violate one, STOP and report to CC —
     a guarded table rebuild needs sign-off, do not improvise one.

Report a short Phase 0 summary (what landed, what you fixed, schema facts, timestamp
convention, which digest channels are possible) before starting Mission 6.

═══════════════════════════════════════════════════════════════════════════════
MISSION 6 — SCHEMA + OUTBOUND QUICK-ADD + BULK IMPORT
═══════════════════════════════════════════════════════════════════════════════
Goal: R1 + R2-at-entry. He logs a person in under 15 seconds from his phone, and his
backlog — including people already waiting on HIM — goes in tonight and is represented
truthfully.

SCHEMA (new migration, next free number, ADDITIVE ONLY — the leads table has live rows,
so every new column is nullable or carries a DEFAULT; SQLite rejects ADD COLUMN with
NOT NULL and no default on a populated table; never rename or drop — 0013 incident):
  - direction TEXT DEFAULT 'inbound'          -- 'inbound' | 'outbound'
  - hold_state TEXT                           -- 'waiting_on_us' | 'waiting_on_lead'
  - hold_state_changed_at                     -- 0013 timestamp convention
  - next_follow_up_at                         -- 0013 timestamp convention
  - follow_up_paused INTEGER DEFAULT 0        -- reversible snooze-forever toggle
  - opted_out INTEGER DEFAULT 0               -- PERMANENT; reuse the 0819 STOP
                                              --   suppression column if one exists
  - is_hot INTEGER DEFAULT 0                  -- the client's "really good" star
  - auto_sms_enrolled INTEGER DEFAULT 0       -- per-lead opt-in to auto-SMS (manual leads)
  Reuse existing 0013 columns for notes/consent/last-touch — do not duplicate.
  Consent basis gains two values: 'manual_inquiry' (they inquired / responded with
  interest) and 'manual_cold' (client reached out cold). Cold is NEVER auto-SMS eligible.

  BACKFILL (in the same migration): every existing ACTIVE lead (not leased/lost, dormant
  flag unset) gets hold_state='waiting_on_lead' and a next_follow_up_at JITTERED across
  24–72h (respecting quiet hours) — leads with a prior SMS touch use last_sms_touch + 2
  days if that's sooner. Without this, the whole pre-existing pipeline is hold_state
  NULL and permanently invisible to every bucket. Verify legacy phone values are E.164;
  normalize stragglers here, then CREATE UNIQUE INDEX ... ON leads(phone) WHERE phone
  IS NOT NULL so the DB enforces what the dedupe query checks.
  Take a DB dump BEFORE applying (same rule as Phase 0 step 5).

QUICK-ADD UI on the leads page:
  - Prominent "+ Add lead", mobile-first. Required: name, phone. Optional: listing
    (dropdown), stage (default 'contacted'), note, email, hot-star.
  - WHOSE-TURN control, two options: "Waiting on them" (default → hold_state=
    'waiting_on_lead', next_follow_up_at = now+2d) and "I owe them a reply" →
    hold_state='waiting_on_us', hold_state_changed_at=now (this feeds WAITING ON YOU —
    the client's headline pain must be expressible at entry).
  - Optional "last texted" quick-pick (today / a few days ago / last week): sets
    next_follow_up_at from that estimate (may be already past → due immediately). The
    timeline row is still created with honest created_at=now; the estimate lives in
    the event payload — never fabricate historical timestamps.
  - CONSENT: default-UNCHECKED choice between "they inquired / responded with interest"
    (consent_basis='manual_inquiry' + timestamp, writes the SAME columns the SMS
    worker's gate reads — Phase 0 step 7) and "I reached out cold" ('manual_cold').
    Unset = treated as cold. This decides auto-SMS eligibility later; reminder mode
    works regardless.
  - Phone normalization: input starting with '+' parsed as-is; bare 10 digits assumes
    +1; 11 digits leading 1 gets '+'; anything else is REJECTED with an inline error —
    never silently coerced (a mangled +44 later receives SMS at a wrong +1 number).
    Use libphonenumber-js if already present or cheap.
  - Dedupe BY DB QUERY (WHERE phone = ?), never by filtering a fetched page — a capped
    page is not a search. On match, open the existing lead. If that lead is suppressed
    (leased/lost/dormant/paused/opted-out is NOT reactivated silently): offer explicit
    "Reactivate" → status 'contacted', dormant flag cleared, follow_up_paused=0,
    hold_state per the whose-turn control, timeline event lead_reactivated. EXCEPTION:
    opted_out stays set unless CC explicitly clears it — an opt-out is not undone by
    re-adding a phone number.
  - Saving writes the lead row (source='manual', direction='outbound') + timeline event
    (lead_created, channel='manual').

BULK PASTE IMPORT (his backlog, tonight):
  - Textarea, one contact per line. TOLERANT parser: find the phone number anywhere in
    the line (normalize dashes/parens/spaces), text before it = name, everything after
    = note (commas inside notes are fine — "wants 2BR, asked about parking" is ONE
    note). A trailing "!" flags "I owe them a reply". Reject lines name the exact
    problem and preserve the original text for one-tap editing.
  - Batch-level controls: the same consent choice, and the "last texted" quick-pick
    (applies to the batch; per-line "!" overrides whose-turn).
  - POST-IMPORT TRIAGE SCREEN: the imported list with two tap columns — "waiting on
    ME" and hot-star — so he can mark the good ones and the owed-reply ones in one
    pass without syntax.
  - Lines run serially through the SAME validation/dedupe path as single add. Jitter
    imported next_follow_up_at across 24–72h — a synchronized 40-row cliff two days
    later is triage work, not a nudge.

Proof: phone-viewport screenshots of add + bulk import + triage; re-add same phone
dedupes; re-add of a ZZTEST lost lead offers Reactivate; bulk-paste 3 lines (one bad
phone → named per-line reject, one trailing "!" → lands waiting_on_us); timeline rows.

═══════════════════════════════════════════════════════════════════════════════
MISSION 7 — CONVERSATION-HOLD TRACKING (one-tap, undoable)
═══════════════════════════════════════════════════════════════════════════════
Goal: R2 in daily use. One tap or he won't log it; undoable or mis-taps bury hot leads.

On each lead card:
  - "I texted them"  → timeline event (manual_sms_out, channel='sms_manual'),
                       hold_state='waiting_on_lead', hold_state_changed_at=now,
                       next_follow_up_at = now+2d
  - "They replied"   → timeline event (manual_reply_in), hold_state='waiting_on_us',
                       hold_state_changed_at=now, next_follow_up_at=NULL
  - "They opted out" → opted_out=1, timeline event, removed from ALL buckets/digest/
                       auto-SMS forever ("stop texting me" said to his face needs a
                       button, and it is NOT the reversible pause toggle)
  - "Pause follow-ups" toggle → follow_up_paused (reversible)
  - Hot-star toggle; "follow up on…" date control writing next_follow_up_at directly
    (a "showing Saturday, ping me Friday" commitment must not live only in a note);
    the free-text "where we're holding" note editable inline.
  - EVERY touch-log tap shows an undo toast that reverts the timeline event,
    hold_state, hold_state_changed_at, and next_follow_up_at. The card shows the
    last-logged action + timestamp so a wrong state is visible.

Stage changes keep working as today; hold_state is orthogonal to stage. Every flip
writes a timeline event. Wire the same rule into every inbound-recording automation
(DM poller now, Twilio webhook later): recording an inbound sets hold_state=
'waiting_on_us' + hold_state_changed_at — EXCEPT an inbound STOP, which sets opted_out
and must NOT put the person in the WAITING ON YOU band (never prompt a human to text
an opted-out person). Also give EXISTING leads' cards the same buttons — one tap
enrolls a legacy lead into hold tracking.

Proof: walk one ZZTEST lead through add → texted → replied → opted out, showing
timeline + hold_state + undo after each; one inbound-path test per automation proving
waiting_on_us is set (and STOP is carved out).

═══════════════════════════════════════════════════════════════════════════════
MISSION 8 — FOLLOW-UP ENGINE: ONE BRAIN, REMINDER MODE NOW, AUTO-SMS GATED
═══════════════════════════════════════════════════════════════════════════════
Goal: R3 + R4. ONE scheduling function feeds the band, the digest, AND the auto-SMS
worker. Do not fork the predicate — the 0819 worker's old WHERE clause is REPLACED by
this brain (its cadence/caps/STOP mechanics stay), so band, digest, and worker can
never disagree about who is due.

THE SCHEDULING FUNCTION (unit-tested, sole source of truth):
  eligible = NOT leased AND NOT lost AND dormant-flag unset AND follow_up_paused=0
             AND opted_out=0
  bucket A "WAITING ON YOU":  hold_state='waiting_on_us' AND
             COALESCE(last-inbound-touch-at, hold_state_changed_at) <= now - 4h
             (the COALESCE matters: a lead marked waiting_on_us at entry has NO inbound
              timeline event; NULL comparison would silently hide exactly the lead this
              feature exists to surface)
  bucket B "FOLLOW-UP DUE":   hold_state='waiting_on_lead' AND next_follow_up_at <= now
  Timestamps per the Phase 0 convention; add a unit test with a due-today /
  not-yet-due-today pair generated the way production generates them.

MODE A — REMINDER MODE (ships now, zero new credentials):
  1. "Needs attention" band at the TOP of the leads page: WAITING ON YOU first (hot-
     starred first, then oldest; age badge "replied 6h ago"), then FOLLOW-UP DUE (same
     ordering). Rows: name, listing, last note, age, tap-to-text, copy-message button.
  2. Tap-to-text sms: links are PLATFORM-AWARE: iOS wants 'sms:+1...&body=', Android
     'sms:+1...?body=' — detect via user agent, URL-encode the body, and keep the copy
     button as the guaranteed fallback. Proof must show the compose screen WITH the
     pre-filled body on both an iPhone and an Android UA — the prewritten message IS
     the feature; if it silently drops on his phone he decides the button is broken.
  3. OPTIMISTIC LOGGING: tapping tap-to-text (or copy) immediately logs manual_sms_out
     and reschedules, with an undo toast. The OS is about to switch him to Messages
     with 20 other threads — a design that needs a return trip to tap "I texted them"
     depends on exactly the discipline he told us he doesn't have. The separate button
     stays for texts sent outside the band.
  4. Band hygiene: per-row snooze (later today / tomorrow / 3 days); a "handled" action
     (logs a note-touch without pretending a text was sent); multi-select for snooze/
     texted/handled (the day he returns from a 3-day lapse to 30 rows decides whether
     he abandons the tool); WAITING ON YOU rows older than 5 days decay into a
     collapsed "stale — confirm status" section instead of shouting forever (cry-wolf
     kills the band).
  5. Message templates in a templates file (reuse/extend the 0819 one): every template
     references THEIR listing, WITH a defined generic variant for listing IS NULL
     ("Hi <name>, following up on the rental you asked about — still looking? Happy to
     line up a tour this week."). Never render 'undefined', never skip a lead for
     lacking a listing. Rotate hooks by outbound-touch count (manual + auto combined).
  6. DAILY DIGEST at 9:00 AM America/New_York (CRON_TZ or in-process IANA tz — the VPS
     is on UTC and a naive crontab drifts an hour every DST change; idempotency keys on
     the New-York calendar date). Content: counts + top 5 per bucket (hot first), diffed
     against yesterday ("3 new, 2 still waiting"). Channel ladder:
       a) If TELEGRAM_BOT_TOKEN_MANDY + TELEGRAM_CHAT_ID_MANDY are BOTH present (exact
          names — a bare token with no chat id delivers nothing, and empire bot tokens
          are forbidden for client data): send via that bot.
       b) Else if Phase 0 found an email-send capability: email digest (destination
          address comes from CC — ask, don't guess).
       c) Else: dashboard-only, and report "no push channel reaches the client today"
          as a NAMED CC DECISION with a recommendation (see close-out) — for a client
          whose stated problem is forgetting, pull-only is a null solution; do not
          bury this as a footnote.
     When Twilio later arms: ALSO send the digest as an SMS to the CLIENT's OWN phone —
     that is the channel he provably reads. Every digest run logs its outcome (sent /
     skipped-no-channel / error + traceback) somewhere durable; a silently dead digest
     is the fail-quiet defect this fleet keeps re-learning. Proof digests go to CC's
     chat/inbox ONLY until CC hands over the client's real destination.

MODE B — AUTO-SMS (build armed-but-caged; a deliberate procedure turns it on):
  Eligibility per send, ALL required:
    - bucket B only. NEVER bucket A — an auto-text on top of an unanswered human reply
      reads as a bot and burns the lead.
    - the 0819 consent gate for inbound-origin leads; for manual leads:
      consent_basis='manual_inquiry' AND consent timestamp present AND
      auto_sms_enrolled=1 (a per-lead one-tap "enroll in auto-texts", also offered as
      a bulk-triage action — default OFF). 'manual_cold' NEVER qualifies. Rows the
      0013-era backfill stamped source='manual' do NOT qualify by that stamp alone —
      only leads whose consent columns were written by the new quick-add path.
    - no manual_sms_out touch in the last 24h (his thread, his voice — don't talk over
      him), and no send if the client texted via band that morning (the digest and the
      worker share one brain, but arbitration is explicit: when Mode B is ARMED, bucket
      B rows leave the digest and collapse in the band under "auto-scheduled — no
      action needed"; WAITING ON YOU remains the only human list).
  Every auto send: writes the timeline row, sets hold_state='waiting_on_lead' +
  hold_state_changed_at, reschedules next_follow_up_at=+2d — in the same write.
  The FIRST auto-SMS to a manual lead must identify the number change: "Hi <name>,
  it's <client first name> from Mandy Management — this is my office line. Still
  interested in <listing/generic>? ..." (his conversations split across two numbers
  the moment this arms; the lead must be told, and surface a one-line recommendation
  to CC about which number owns threads going forward).
  Inherited 0819 mechanics stay: quiet hours 9am–8pm America/New_York, daily cap 30,
  max 6 OUTBOUND touches (manual + auto combined — five manual texts + one auto = a
  cold trail, park it) then dormant flag, STOP → opted_out=1 forever.
  CIRCUIT BREAKER: if due-count > 15 or no operator-logged touch in 72h, HOLD all auto
  sends and flag for a human confirmation pass — machine-gunning a backlog whose real-
  world state diverged days ago is the highest-damage failure this system can produce.
  ARMING PROCEDURE (document it in the close-out; "switches on by itself" is banned):
  CC drops the 3 Twilio keys → pm2 restart <sms-worker> --update-env && pm2 save (env
  is read at boot — creds in .env do NOTHING to a running worker) → mandatory dry-run
  to CC's own phone incl. a STOP round-trip → explicit CC go → enable, first-day cap
  10. The worker logs an explicit "ARMED" / "DISARMED (no creds)" line at startup so
  the state is observable, and stays fail-closed exactly as built until then.

Proof: unit tests for the scheduling function — both buckets; the no-inbound-event
waiting_on_us case; due-today boundary; paused/opted-out/dormant-FLAG/leased/lost each
excluded (seed the dormant case via the FLAG, not a status string — Phase 0 confirmed
which mechanism exists); Mode B eligibility incl. manual_cold rejected, unenrolled
rejected, 24h-manual-touch suppression; fail-closed re-proof (creds absent → selects
eligible leads, sends ZERO, exits clean). Band screenshots with ZZTEST leads in both
buckets; digest dry-run to CC only; digest failure-path log line.

═══════════════════════════════════════════════════════════════════════════════
MISSION 9 — HARDENING + EVIDENCE PACK + CLIENT ENABLEMENT
═══════════════════════════════════════════════════════════════════════════════
1. Inbound integrity: grep every timeline-insert call site; each inbound-recording path
   sets waiting_on_us (STOP carved out to opted_out) — one test per path.
2. Suppression integrity: leased / lost / dormant-flag / paused / opted_out appear in
   NO band bucket, NO digest, get NO auto-SMS — one test per surface per class,
   including the STOP-suppressed class on all three surfaces.
3. typecheck + full test suite + next build green (paste actual outputs).
4. Vercel production READY at origin/main HEAD SHA (the Phase 0 standard); /api/health ok.
5. pm2 list all online, no restart loops; pm2 save done.
6. DAY-ONE WALKTHROUGH (the client's actual first night, ZZTEST + CC's phone only):
   bulk-paste a backlog incl. one "!" line → triage screen → the "!" lead appears in
   WAITING ON YOU tonight (within its 4h window) → tap-to-text logs optimistically →
   undo works → a quick-pick "last week" lead lands directly in FOLLOW-UP DUE → digest
   (to CC) includes both, hot-starred first → mark one leased → vanishes everywhere.
   Screenshots + timeline dump. Then DELETE all ZZTEST rows and prove zero remain.
7. CLIENT ENABLEMENT (the system only works if he uses it): verify the client's actual
   account can log in and reach the leads page on mobile (if client auth doesn't exist,
   that's a launch blocker to CC, not a footnote). Write a 5-line how-to formatted for
   CC to forward on WhatsApp: how to add someone, what the three taps mean, what the
   top band is, what the "!" does in bulk paste, when the digest arrives.

═══════════════════════════════════════════════════════════════════════════════
CLOSE-OUT
═══════════════════════════════════════════════════════════════════════════════
Report concise: what changed (paths), why (one sentence each), proof (actual outputs +
screenshots), what you need from CC. The report MUST state explicitly which of the
client's four asks are LIVE today vs CC-GATED, and list:
  - P0 — Twilio number + TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN /
    TWILIO_FROM_NUMBER_MANDY into /srv/listing-studio/.env AND Vercel env, then the
    documented arming procedure. This is the client's literal "automated follow-ups"
    ask and has been open since 08-19 — same-day ask, not a footnote.
  - Digest push channel decision (Mandy Telegram bot token + chat id, or client email
    address, or wait-for-Twilio client-SMS digest) with your recommendation.
  - The TCPA-vs-CASL consent policy for manually-entered US leads (the 0819 booking-
    form rule was a different fact pattern — the lead submitted a form themselves;
    manual entry of people HE texted is not that). Present the two-basis model you
    built and let CC ratify before Mode B ever arms.
  - The client how-to text, ready to forward.
If anything here conflicts with the live code, trust the code and tell CC the
discrepancy.
```

## Notes for CC

- **Day one, no Twilio needed:** quick-add + bulk paste with a post-import triage pass
  (mark "waiting on ME" + hot-star), the WAITING ON YOU / FOLLOW-UP DUE bands with
  platform-correct tap-to-text and prewritten per-listing messages, optimistic logging
  with undo, and a 9 AM digest **if** a channel exists (see next bullet).
- **Your three unlocks (P0 first):**
  1. **Twilio number** + the 3 env keys — this is the client's literal "automated
     follow-ups" ask, open since 08-19. Auto-SMS then arms via a documented procedure
     (pm2 restart --update-env + dry-run to you + your go), never silently.
  2. **Digest channel** — Mandy-specific Telegram bot token + chat id, OR the client's
     email address, OR accept "client-SMS digest once Twilio lands". Without one of
     these, day-one reminders are dashboard-only, which for this client is weak.
  3. **Consent ratification** — manually-entered US leads get a two-basis model
     (inquired vs cold); only "inquired" ever auto-SMSes. Ratify before arming.
- **Phase 0 matters:** the 08-19 work may be pushed but NOT deployed (Vercel rejected
  root-authored commits). The brief makes the agent verify the deployed SHA, not the
  push, and takes DB dumps before the migration and the compat-view drop.
- **Adversarial review:** this brief absorbed 46 findings from a 4-lens review
  (requirements / technical / ops-safety / client-UX) — notably: day-one backlog can
  express "they're waiting on me", deploy verification checks the deployed SHA, consent
  defaults closed, auto-SMS is per-lead opt-in with a circuit breaker, and all test
  data is ZZTEST + your phone + deleted before close-out.
- **Zillow untouched:** this is the bridge until Zillow syndication is approved; no
  Zillow surface is modified.

## Obsidian Links
- [[docs/LISTING_STUDIO_VPS_AGENT_SYSTEM_MESSAGE]] (predecessor — the five 2026-08-19 missions)
- [[brain/APP_REGISTRY]] | [[memory/SESSION_LOG]]
