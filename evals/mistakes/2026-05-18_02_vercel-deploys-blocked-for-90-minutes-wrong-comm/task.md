# Regression: Vercel Deploys Blocked for 90 Minutes — Wrong Committer Identity After Repo Extraction (2026-05-18)

## What went wrong
The Command Center went DOWN for ~30 minutes after I patched the stale `agent-dashboard` Vercel project to deploy as a no-op static page, on the wrong assumption that a separate Vercel project was already deploying the new `oasis-command-center` standalone repo. Listing all Vercel projects on CC's account showed there was no such project — the `agent-dashboard` project (linked to CEO-Agent) WAS the only deploy of the Command Center. Patching it to no-op took the production URL offline. After unlinking + re-linking the project to `oasis-command-center`, every subsequent push went BLOCKED. Took 5 attempts (3 trigger-empty-commits + 2 wrong author/committer combinations) before identifying the actual reason from the API: `readyStateReason: "The Deployment was blocked because GitHub could not 

## The behavior that must NOT recur
1. **`feedback_vercel_committer_identity.md` added to auto-memory** — codifies the GitHub-noreply identity (`214530671+CC90210@users.noreply.github.com`) as the canonical author + committer for ANY agent-authored push to a Vercel-linked repo on CC's account.
2. **Per-repo `user.name + user.email` already locked on oasis-command-center** — `git config` (no --global) overrides the agent identity for this specific repo so future pushes from any Bravo session pass Vercel's check without re-discovery.
3. **`scripts/integrations/vercel_relink_command_center.py` left in the repo** — a runnable artifact + documentation of the recovery procedure. If Vercel ever reverts settings, re-run it.
4. **`scripts/vercel_disable_stale_project.py` deleted** — the misleadingly-named "disable" script (it never d
