# `app/` — Empty / Reserved

This directory previously held the OASIS Command Center dashboard. The
dashboard was extracted to its own repo on 2026-05-18 and now lives at:

- **Repo:** [CC90210/oasis-command-center](https://github.com/CC90210/oasis-command-center)
- **Local clone:** `~/APPS/oasis-command-center`
- **Production:** `agent-dashboard-cc90210.vercel.app`

This empty `app/` directory is kept as a marker so anyone searching for the
dashboard source from old documentation knows where it went. The `app/api/`
subdirectory is also empty for the same reason.

**Do not put new code here.** Either:
1. Add it to the extracted `oasis-command-center` repo (for dashboard work), or
2. Add it to `scripts/` or `apps/<name>/` (for new agent components).

Once enough time has passed and no stale doc references this path, the entire
`app/` tree can be removed. CC has not approved that deletion yet.

## Cross-references
- [[memory/feedback_command_center_extracted]] — extraction history
- [[brain/APP_REGISTRY]] — current routing for all apps
