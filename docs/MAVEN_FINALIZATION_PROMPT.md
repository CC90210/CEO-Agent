# Maven Finalization Prompt — V1.1 → V1.2 (Integration debt + 6-lens deep audit)

> **STATUS: ACTIVE — paste into Maven 2026-04-26+.**
>
> **How to use:** Open Claude Code in `C:\Users\User\CMO-Agent` (fresh session). Copy the entire prompt below — everything between the two `---` rules — and paste as Maven's first message. Maven takes control, runs the 6-lens pass autonomously, ships the report, and posts to Bravo's inbox.

## Why this is different from MAVEN_UPDATE_PROMPT.md

That earlier prompt was V1.0→V1.1 — frontmatter repair + skill imports + the initial send_gateway build. It's **complete** (commit `067cde8`).

This is V1.1→V1.2 — **integration debt** (4 scripts Bravo just transferred to Maven on 2026-04-26 in commit `3eb5b13` aren't yet wired through `send_gateway`) plus a 6-lens deep audit hardening the existing system against marketing-specific failure modes (UTM hygiene, creative fatigue, CFO spend-gate freshness, brand-voice drift).

Maven shipped V1.1 well — this pass is about **going deeper on what already works**.

---

You are Maven, AI Chief Marketing Officer. CC is authorizing a deep finalization
pass focused on YOUR specific marketing surface. You shipped V1.1 successfully
on 2026-04-26 (commit 067cde8) — frontmatter, send_gateway, RESPONSIBILITY_
BOUNDARIES are all in place. This pass is about closing the integration debt
from the V1.1→V1.2 transition and finding what V1.1 missed.

Take control. Don't ask permission for prescribed steps.

═══ MAVEN-SPECIFIC SURFACE ═══

You own: ad spend (Meta + Google), email blasts, social posting (Late/Zernio),
Instagram automation, content production pipeline (video + image + caption),
funnel/landing pages, brand voice, audience targeting.

You DO NOT own: cold outreach (Bravo), client relationships (Bravo), primary retainer/
Skool community (Bravo), trade execution (Atlas), tax/runway (Atlas), home
automation (Aura).

═══ KNOWN INTEGRATION DEBT FROM 2026-04-26 ═══

Bravo transferred 4 scripts to you (commit 3eb5b13). 2 of them are NOT yet
routed through your send_gateway:

  - scripts/late_publisher.py (19,245 bytes) — UNTRACKED, NOT routed through
    send_gateway. Posts to Late/Zernio directly. CASL exemption is only valid
    for organic posts to your own audience; if any post is paid promotion or
    targets a list, send_gateway MUST gate it.
  - scripts/instagram_engine.py (70,064 bytes) — UNTRACKED, NOT routed
    through send_gateway. Auto-replies to DMs in CC's brand voice. This is
    one-to-one outbound at scale and inherits CASL+anti-spam concerns.
  - scripts/late_tool.py (11,819 bytes) — UNTRACKED. Bravo's CEO dashboard
    subprocesses to it (cross-repo) for the "posts published this week" stat;
    DO NOT change the JSON output shape of `posts --status published --json`.
  - scripts/codex_image_gen.py (7,644 bytes) — UNTRACKED. Generates content
    images via Codex/OpenAI. No send-safety implications, but verify it
    doesn't leak credentials.

═══ THE 6-LENS PASS ═══

Walk these in order. Write a one-paragraph finding to
`docs/FINALIZATION_REPORT_2026-04-26.md` after each lens before moving on.

Lens 1 — TRANSFER INTEGRATION (45 min, HIGHEST PRIORITY)
  • git status — confirm 4 untracked files: late_tool.py, late_publisher.py,
    instagram_engine.py, codex_image_gen.py
  • Smoke-import each. Fix any ImportError.
  • Rewire late_publisher.py to route through send_gateway (channel="email"
    for nurture-style posts, or add a new channel="social" with its own caps
    if your gateway doesn't have one). Cap suggestion: 50 social posts/day,
    10/hour per platform.
  • Rewire instagram_engine.py: outbound DM replies route through
    send_gateway with channel="instagram_dm", daily cap 30, hourly cap 5,
    cooldown 24h per recipient. Inbound DM read still happens directly.
  • Add tests at scripts/test_late_publisher.py and
    scripts/test_instagram_engine.py — at minimum: golden path, killswitch
    short-circuits, cap exceeded blocks, draft_critic non-ship verdict blocks.
  • Update brain/CAPABILITIES.md with the 4 new scripts.
  • Update brain/AGENTS.md if any sub-agent owns these new scripts.
  • Commit + verify tests still 100%.

Lens 2 — SEND_GATEWAY DEEP AUDIT (45 min)
  • You shipped send_gateway with 48/48 tests in V1.1. Add 10 more cases
    targeting marketing-specific scenarios:
      - List-targeting (sending to >50 recipients in <1 hour) triggers
        list-mode caps separate from one-to-one caps
      - Paid-channel send blocked when cfo_pulse.json is stale (> 24h)
      - Paid-channel send blocked when cfo_pulse.json budget = 0 for the
        channel/brand combo
      - UTM tag sanitization: every outbound link MUST have utm_source,
        utm_medium, utm_campaign — block if missing
      - Brand-voice drift: draft_critic checks the draft against
        brain/MARKETING_CANON.md (your existing canon) — block if voice
        differs significantly
      - Image attachments must pass an alt-text presence check (ADA/anti-
        slop discipline)
      - Subject-line slop detection: block "Unlock the power of...",
        all-caps subjects, generic emoji-only opens
      - Same-creative-twice within 14d to same recipient → blocked
        (creative fatigue)
      - First-send-to-cold-recipient must include double-opt-in confirmation
      - VIP-segment override: critic verdict can be ship-with-warning for
        flagged VIP lists (define VIP via env or table)

Lens 3 — CFO SPEND GATE — END TO END (30 min)
  • cfo_pulse.json read path: walk the code that reads Atlas's pulse before
    any paid launch. Verify it (a) reads from the actual Atlas repo path via
    sibling_repos (you copied it from Bravo in V1.1), (b) handles missing
    file as fail-closed, (c) handles stale (>24h) as fail-closed, (d) parses
    the JSON schema Atlas writes, (e) compares channel + brand + amount.
  • Write 5 integration tests covering each fail mode.
  • Document the exact expected schema in brain/CFO_GATE_CONTRACT.md so if
    Atlas changes its pulse format, you can detect drift.

Lens 4 — CONTENT PIPELINE FUNCTIONAL (45 min)
  • content_pipeline.py orchestrates raw video → captioned cinematic output
    + thumbnail + per-platform captions + scheduled distribution. End-to-end
    smoke test: feed it a real 30-second test clip from media/raw/, watch it
    produce all 6 outputs without manual intervention.
  • Caption sync: Whisper word-level timestamps must match audio (the
    historical regression). Test on a clip with known phonemes.
  • Image generation contextual insertion: codex_image_gen.py prompts must
    be derived from video transcript, not hardcoded. Verify.
  • Per-platform character limit enforcement: x=280, threads=500,
    instagram=2200, linkedin=3000, tiktok=4000. Add a unit test per platform.

Lens 5 — ATTRIBUTION & ROAS RIGOR (30 min)
  • Every outbound campaign must produce a row in your attribution table
    with: source, medium, campaign, creative_id, send_at, gate_decision,
    spend_committed. Walk meta_ads_engine + google_ads_engine + email_blast
    and verify the write happens.
  • Performance reporter (scripts/performance_reporter.py) reads attribution
    + insights APIs. Verify it computes CPL, CAC, ROAS correctly with a
    synthetic dataset where the answers are known.
  • Add brain/ATTRIBUTION_MODEL.md as canonical reference if not exhaustive.

Lens 6 — ADVERSARIAL REVIEW (30 min, parallel sub-agents)
  • Spawn 4 sub-agents in parallel:
    1. Security: hardcoded secrets, .env.agents access, Meta/Google token
       exposure, image upload SSRF risk
    2. Reliability: what fails when Meta API rate-limits? Google Ads token
       expires? Late/Zernio is down? cfo_pulse stale during peak hours?
    3. CC's-future-self: 6 months from now, can CC re-launch a paused
       campaign without reading any code?
    4. Bravo's perspective: where does Maven still bleed into CEO domain?
       (Re-read brain/RESPONSIBILITY_BOUNDARIES.md.)

═══ SUCCESS CRITERIA ═══

  [ ] 4 transferred scripts: tracked, imported, tested, gated
  [ ] send_gateway test count ≥ 58 (was 48; +10 from Lens 2)
  [ ] cfo gate fail-closed under all 5 fail modes
  [ ] content_pipeline runs end-to-end on a test clip without intervention
  [ ] Per-platform caption length tests pass for all 5 platforms
  [ ] Attribution row written for every campaign launch path
  [ ] Performance reporter math verified on synthetic data
  [ ] Adversarial findings: every Sec/Reliability hit either fixed or
      documented in "Known Limitations" with reason
  [ ] self_audit health_score ≥ 95
  [ ] git status clean, all tests pass, commit exists, NOT pushed yet

═══ FINAL DELIVERABLE ═══

`docs/FINALIZATION_REPORT_2026-04-26.md` with 6 lens-paragraphs + 4 closing
sections (already-solid / fixed / deferred / next-up).

Post completion to Bravo via:
  python scripts/agent_inbox.py --json post --from maven --to bravo \
    --priority normal --subject "V1.2 finalization complete" \
    --body "Report at <path>. Tests: <N>/<N>. New: 4 transferred scripts
            integrated, send_gateway +10 cases, content_pipeline e2e
            verified. Adversarial: <findings_summary>."

Begin with Lens 1.

---

## What CC does after pasting

1. Watch Maven complete Lens 1 — that's the integration-debt close, highest blast-radius if it goes wrong (placeholder names leaking into IG DMs, etc.)
2. Don't intervene mid-lens — verification gates do their job
3. Read `docs/FINALIZATION_REPORT_2026-04-26.md` when Maven finishes
4. Check Bravo's inbox: `python scripts/agent_inbox.py list --to bravo`