---
description: "Paste-prompt for SunBiz VPS: contains git commands to persist SMS fix to a feature branch, answers 3 persistence-strategy questions"
tags: [vps, sunbiz, bridge, paste-prompt, task]
last_updated: 2026-06-22
---
# VPS Agent — Task 3 (persist the SMS fix; answers to your 3 questions)

> **CC:** paste this into the SunBiz VPS session to back up the SMS fix so it isn't lost on reboot.
> 30 seconds; safe (a branch push only, never main). Paste-prompt only.

```text
Great work — self-test closed and the SMS fix is tested + live. Persist it now, and here are the
answers to your three questions:

1) PUSH THE FIX (persist it — it's currently only running uncommitted):
   git checkout -b bravo/sms-e164-skip
   git add scripts/sequence_runner.py
   git commit -m "fix(sequences): E.164-normalize SMS recipients + skip-and-advance instead of failing the step, so email touches behind a bad/bodyless SMS step still fire (7/8 sequences led with SMS)"
   git push -u origin bravo/sms-e164-skip
   Pushing a BRANCH is safe — it doesn't touch main and doesn't deploy. This just backs the fix up
   to GitHub so a reboot can't lose it. CC will review + merge from his PC tomorrow. (Do NOT push
   to main / do NOT force-push.)

2) BODYLESS SMS STEPS: leave them SKIPPING for now — do not send empty SMS and do not edit sequence
   data. CC will decide tomorrow whether to add body_text to those reminder steps or disable them.
   Your skip-and-advance already makes this safe (email still fires).

3) The 3 historically-failed 8fc506b2 leads (phone=None, SMS-only): leave as-is, no action — noted.

Then report one line: the branch name + commit hash you pushed, and confirm pm2 shows the
sequence-runner online. That's it for tonight.
```

[[VPS_SUNBIZ_TASK2_PROMPT]] · [[VPS_SUNBIZ_BRIDGE_PROMPT]] · `project_sunbiz_funding_website`
