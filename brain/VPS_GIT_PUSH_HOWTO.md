# VPS — push the merged branches (paste-ready prompt)

> Paste the block between the triple-dashes into the Claude Code session
> running ON the SunBiz VPS. No SSH-from-Windows needed — CC stays in
> his usual VPS chat and the VPS agent does the work.

## What this does

Two repos on the VPS have local merges that GitHub doesn't see yet:

- `/srv/sunbiz/ceo-agent` (mirrors `CC90210/CEO-Agent`)
- `/srv/sunbiz/sunbiz-agent` (mirrors `CC90210/SunBiz-Agent`)

The VPS agent pushes both, confirms GitHub caught up, reports back.

## Paste into VPS Claude Code

---

You are a Claude Code agent on CC's SunBiz Funding VPS. A prior
finalization pass merged its `fix/vps-readiness-patches` branch into
`main` LOCALLY on two repos but didn't push to GitHub. Your job: push
both, verify, report. Strictly SunBiz scope — touch nothing else.

## Step 1 — Push CEO-Agent

```bash
cd /srv/sunbiz/ceo-agent
git fetch origin
git status --short
git log --oneline origin/main..main
```

Expect: `git status` clean, `git log` shows ≥1 commit ahead. Then:

```bash
git push origin main
```

If git asks for credentials, the PAT is already in
`~/.git-credentials` or `/root/.git-credentials`. If it isn't, STOP
and tell CC — don't paste tokens around.

## Step 2 — Push SunBiz-Agent

```bash
cd /srv/sunbiz/sunbiz-agent
git fetch origin
git status --short
git log --oneline origin/main..main
git push origin main
```

## Step 3 — Verify

```bash
cd /srv/sunbiz/ceo-agent && git log --oneline origin/main..main   # expect EMPTY
cd /srv/sunbiz/sunbiz-agent && git log --oneline origin/main..main  # expect EMPTY
```

Both empty = origin caught up.

## Step 4 — Report back to CC

Tell CC:
- Which commits were pushed (the SHAs from step 1+2's `git log`)
- Whether the verify pass came back empty for both
- Anything weird (auth prompt, rebase needed, push rejected)

If push was rejected with `non-fast-forward`: STOP. Don't `pull
--rebase` blindly — that means someone else pushed during your window.
Report to CC and wait for the call on how to reconcile.

---

## What happens after

- Vercel auto-deploys `oasis-command-center` from `main` (already current).
- CEO-Agent + SunBiz-Agent have no Vercel project — code is already
  running on the VPS, push just syncs GitHub.
- CC's Windows-side clones (`C:/Users/User/CEO-Agent`,
  `C:/Users/User/SunBiz-Agent`) will fetch the new commits on the next
  Bravo session via `git fetch origin`.
