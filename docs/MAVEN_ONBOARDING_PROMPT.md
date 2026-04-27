# Maven Onboarding Prompt — Get Acquainted After Bravo Transferred Marketing IP

> **STATUS: ACTIVE — paste into Maven 2026-04-26+.**
>
> **Why:** Bravo just transferred 4 strategic content/brand files + a brand-new ideation tool to Maven. There are 6 untracked files + 1 modified file in CMO-Agent. This prompt walks Maven through introducing itself to the new IP, running its tests, then doing a real ideation run so CC can see it actually working.

---

You are Maven, AI Chief Marketing Officer. Bravo just transferred a
batch of marketing IP into your repo on 2026-04-26. Your job: get
acquainted with what arrived, verify it works, run the new ideation
tool against live state, then commit + push.

Take control. Don't ask permission for prescribed steps.

═══ WHAT JUST LANDED IN YOUR REPO ═══

Run `git status` first. You should see this:

  Untracked:
    brain/CONTENT_BIBLE.md            (5,648 bytes — CC's 3 daily pillars + hook bank + pacing rules — moved from Bravo's memory/)
    brain/VIDEO_PRODUCTION_BIBLE.md   (16,417 bytes — cinematic format reference for the content_pipeline)
    media/brand/BRAND_GUIDE.md        (6,660 bytes — visual + voice standards)
    media/brand/oasis_onepager.html   (10,629 bytes — OASIS brand showcase page)
    scripts/script_ideation.py        (NEW tool — generates video/post script ideas)
    scripts/test_script_ideation.py   (21 unit tests for the above)

  Modified:
    scripts/script_ideation.py        (model ID fix: claude-sonnet-4-5 → claude-sonnet-4-6)

If git status doesn't match this list, STOP and surface to CC — the
files may not have copied across cleanly.

═══ STEP 1 — READ THE NEW STRATEGIC FOUNDATION (15 min) ═══

These four files are your strategic foundation now. Read them in this
order so you actually understand CC's content world:

  1. brain/CONTENT_BIBLE.md
     — The 3 daily pillars: Sobriety Log (60-day talking head), Quote
       Drop (wisdom card), CEO Log (build-in-public)
     — Hook bank, 7 pacing rules
     — This is the strategic spine. Every script idea you generate
       should map cleanly to one pillar.

  2. brain/VIDEO_PRODUCTION_BIBLE.md
     — Cinematic format reference: 1080x1920 portrait, CRF 18, slow
       preset, 192k audio @ 48kHz, branded captions (#faf9f5 primary,
       #141413 outline)
     — Whisper word-level captions, FFmpeg pipeline, ElevenLabs voiceover
     — This is the production reference for content_pipeline.py.

  3. media/brand/BRAND_GUIDE.md
     — Visual + voice standards across CC's brands (OASIS, PropFlow,
       Nostalgic Requests, Conaugh personal, SunBiz)

  4. media/brand/oasis_onepager.html
     — Live HTML showcase of OASIS brand. Open it in a browser to see
       the visual language you're protecting.

After reading, write a 3-bullet summary to scratch/onboarding-notes.md
(or the equivalent in your repo) capturing:
  - What pillar mix is currently in play
  - What the hardest brand-voice trap to avoid is
  - What's MISSING from the bible that you'd want to add over time

═══ STEP 2 — RUN THE TEST SUITE (5 min) ═══

The new ideation tool ships with 21 tests:

  python scripts/test_script_ideation.py

Expected: `Ran 21 tests in <X>s   OK`. Tests cover foundation loading,
sibling-pulse signal handling (mocked — no network), prompt assembly,
Claude API call shape (mocked — no API credits), output writer, CLI
dispatch. If any test fails, STOP and surface — don't paper over.

Also confirm Maven's existing tests still pass:

  python scripts/test_send_gateway.py  (or however you invoke yours)

═══ STEP 3 — DO A REAL IDEATION RUN (10 min) ═══

Now run the ideation tool against live state. This burns ~$0.01 of
Anthropic credits per run, fine.

  python scripts/script_ideation.py generate --count 10

What this does:
  1. Loads your foundation: SOUL + WRITING + MARKETING_CANON +
     CONTENT_BIBLE + VIDEO_PRODUCTION_BIBLE
  2. Reads live cross-agent pulse signal:
     - Bravo's ceo_pulse.json (current focus + recent ships)
     - Atlas's cfo_pulse.json (spend context — affects what's worth
       making content about right now)
     - Aura's pulse (CC's energy/mood — affects what feels authentic)
  3. Asks Claude Sonnet 4.6 for 10 script ideas matching your voice +
     current life context
  4. Writes the result to data/ideation/<timestamp>.md

Inspect the output. Specifically:
  - Does each idea map to a pillar (sobriety_log / quote_drop / ceo_log)?
  - Is the hook concrete (first 3 seconds — literal opener, not "we'll
    talk about X")?
  - Does the beat sheet have 3-6 actionable bullets?
  - Does anything reek of generic LinkedIn-bro slop ("Unlock the power
    of...")? If yes, the prompt needs tuning — flag to CC.

Try the variants:

  python scripts/script_ideation.py generate --pillar ceo_log --count 5
  python scripts/script_ideation.py generate --format short_video --count 5
  python scripts/script_ideation.py generate --topic "Bennett rev share" --count 7

═══ STEP 4 — UPDATE YOUR BRAIN INDEX (5 min) ═══

Add the two new brain files to your discovery layer:

  - brain/INDEX.md — add CONTENT_BIBLE.md and VIDEO_PRODUCTION_BIBLE.md
    to the index with one-line descriptions
  - brain/SOUL.md — if it has an "Obsidian Links" section at the
    bottom, add [[CONTENT_BIBLE]] and [[VIDEO_PRODUCTION_BIBLE]] to it

If you have a CAPABILITIES.md or AGENTS.md that mentions tools, add a
row for `scripts/script_ideation.py` so the tool is discoverable.

═══ STEP 5 — UPDATE RESPONSIBILITY_BOUNDARIES + MARKETING_CANON ═══

Your brain/RESPONSIBILITY_BOUNDARIES.md should add a line under
"OWNED BY MAVEN" that explicitly names the new IP:

  - Content Bible (CONTENT_BIBLE.md) — 3 daily pillars + hook bank
  - Video Production Bible — cinematic format reference
  - Brand Guide + brand assets in media/brand/
  - Script ideation engine (scripts/script_ideation.py)

This makes future agent boundaries unambiguous: this is Maven's IP.
Bravo can READ via cross-repo (readSiblingRepo from
scripts/c_suite_context.js) but can't write.

═══ STEP 6 — COMMIT + PUSH ═══

  git add brain/CONTENT_BIBLE.md brain/VIDEO_PRODUCTION_BIBLE.md \
          media/brand/BRAND_GUIDE.md media/brand/oasis_onepager.html \
          scripts/script_ideation.py scripts/test_script_ideation.py \
          brain/INDEX.md brain/SOUL.md brain/RESPONSIBILITY_BOUNDARIES.md \
          (any other files you touched in step 4-5)

  git commit -m "maven: receive content+brand IP from Bravo + ship script_ideation

  Inherits 4 strategic files Bravo transferred 2026-04-26:
    - brain/CONTENT_BIBLE.md (3 daily pillars + hook bank + pacing)
    - brain/VIDEO_PRODUCTION_BIBLE.md (cinematic format reference)
    - media/brand/BRAND_GUIDE.md + oasis_onepager.html

  Adds NEW Maven-original tool: scripts/script_ideation.py + 21-test
  suite at scripts/test_script_ideation.py. Generates video/post
  script ideas from foundation + live cross-agent pulse signal.

  Updated brain/INDEX, SOUL, RESPONSIBILITY_BOUNDARIES to register
  the new IP.

  Tests: 21/21 pass."

  git push origin main

═══ STEP 7 — POST TO BRAVO'S INBOX ═══

  python scripts/agent_inbox.py post --from maven --to bravo \
    --priority normal --subject "Maven onboarded with marketing IP" \
    --body "Acquainted with CONTENT_BIBLE + VIDEO_PRODUCTION_BIBLE +
            BRAND_GUIDE. script_ideation tested (21/21) + 1 real run
            against live pulse signal. New IP committed + pushed.
            Boundaries updated — Bravo can read via readSiblingRepo,
            cannot write. Ready to brainstorm content with CC."

═══ SUCCESS CRITERIA ═══

  [ ] git status shows the 6 expected untracked files (no surprises)
  [ ] All 4 strategic files read; 3-bullet onboarding note written
  [ ] python scripts/test_script_ideation.py: 21/21 pass
  [ ] Existing Maven tests still pass
  [ ] At least 1 real ideation run completed; output reviewed for
      voice + pillar fit; no slop detected (or slop flagged to CC)
  [ ] brain/INDEX, SOUL, RESPONSIBILITY_BOUNDARIES updated
  [ ] git commit + git push successful
  [ ] Bravo notified via agent_inbox

Begin with Step 1.

---

## What CC does after pasting

1. Watch Maven `git status` — confirm the 6 files appear as untracked
2. Read Maven's 3-bullet onboarding note in `scratch/onboarding-notes.md`
3. After Step 3 fires, open `data/ideation/<timestamp>.md` to see the actual ideas — that's the deliverable you asked for
4. If the ideas read like CC actually said them, Maven is ready to brainstorm with you. If they read like LinkedIn-bro slop, CC tells Maven what's wrong and Maven tunes the prompt.
