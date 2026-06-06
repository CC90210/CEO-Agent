# How to push the VPS-merged branches

> The prior agent merged its `fix/vps-readiness-patches` branch into
> `main` LOCALLY on the VPS but didn't push to GitHub (its scope rule
> says agents don't push from the VPS). This 30-second doc walks you
> through doing it yourself.
>
> You only need this once after the finalization pass. Future agent
> rounds will push from CC's PC after a diff review.

## What you're pushing

Two repos on the VPS have merged changes that GitHub doesn't see yet:

- `/srv/sunbiz/ceo-agent` (mirrors `CC90210/CEO-Agent` — Bravo / shared substrate)
- `/srv/sunbiz/sunbiz-agent` (mirrors `CC90210/SunBiz-Agent` — Solara / Helios daemons)

The merges from `fix/vps-readiness-patches` are sitting on `main` on
the VPS only. After you push, GitHub catches up + your PC sees the
same code state.

## Steps

### 1. SSH to the VPS

```
ssh root@srv1723601
```

(Or whatever your SSH command is — same one you used to run the
diagnostic / finalization prompts.)

### 2. Push CEO-Agent

```
cd /srv/sunbiz/ceo-agent
```

Quick sanity check — see what's about to go up:

```
git fetch origin
git status --short
git log --oneline origin/main..main
```

You should see:
- `git status` clean (no uncommitted changes)
- `git log` showing 1+ commits ahead of origin/main — these are the
  finalization-pass merges

If both look right:

```
git push origin main
```

Expect a `main -> main` line. If git asks for credentials, paste your
GitHub Personal Access Token (the one tied to the
`CC90210/users.noreply.github.com` identity — same one Vercel checks
for the auto-deploy gate).

### 3. Push SunBiz-Agent

```
cd /srv/sunbiz/sunbiz-agent
git fetch origin
git status --short
git log --oneline origin/main..main
git push origin main
```

Same shape as CEO-Agent.

### 4. Confirm from your PC

Back in your PC's terminal:

```
git -C C:/Users/User/CEO-Agent fetch origin && git -C C:/Users/User/CEO-Agent log --oneline -5
git -C C:/Users/User/SunBiz-Agent fetch origin && git -C C:/Users/User/SunBiz-Agent log --oneline -5
```

You should see the VPS commits in both repos' history.

### 5. (Optional) Pull on your PC so your local copies match

```
git -C C:/Users/User/CEO-Agent pull --ff-only origin main
git -C C:/Users/User/SunBiz-Agent pull --ff-only origin main
```

If `--ff-only` errors out because your local commits diverged, run
`git status` on that repo and resolve before pulling. CC's standing
rule: never `git reset --hard` without flagging — those local commits
might be unpushed work you want to keep.

## If git push fails

| Symptom | Cause | Fix |
|---|---|---|
| `fatal: Authentication failed` | GitHub PAT not configured | Set up the same Vercel-recognized identity: `git config user.email "214530671+CC90210@users.noreply.github.com"` per-repo, then `git config --global credential.helper store` and paste the PAT once. |
| `! [rejected]        main -> main (non-fast-forward)` | Someone else pushed to origin/main while VPS was working | This shouldn't happen if you're the only operator. If it did: `git pull --rebase origin main` then re-push. STOP and report if the rebase has conflicts. |
| `error: failed to push some refs` (other) | Network blip or GitHub outage | Retry. If repeated, check status.github.com. |

## Once everything's pushed

Vercel auto-deploys oasis-command-center from `main`. CEO-Agent and
SunBiz-Agent don't auto-deploy (no Vercel project) — the VPS pulls
them on its next git ops cycle, but since the VPS already has the
code (it's where the merges were made), nothing else needs to fire.

You can then move on to the rest of the punch list:
- Twilio / Anthropic credential paste (Monday meeting per your note)
- Optional non-root migration (brain/VPS_NONROOT_MIGRATION_PROMPT.md)
- Try the new intake features (resume link + smarter dedup + fuzzy match)
