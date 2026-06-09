---
tags: [apps-context, local-only, operator]
last_updated: 2026-06-09
---
# APPS_CONTEXT — local-only operator app context

This directory holds **per-operator, local-only context** for the apps/brands the
operator runs (one `*_CLAUDE.md` per app, plus supporting research/data). It is
**gitignored** (see `.gitignore`: `APPS_CONTEXT/*` with `!APPS_CONTEXT/README.md`)
because it contains operator-specific business context that should not live in a
public repo.

`[[APPS_CONTEXT/...]]` wiki-links in tracked docs (e.g. `brain/APP_REGISTRY.md`)
point here intentionally — they resolve on the operator's machine and are
documented as local-only. The wiki-link integrity test
(`scripts/tests/test_wiki_links.py`) treats `APPS_CONTEXT/` as a documented
local-only store, so these links don't read as broken.

## What lives here (local files, not in git)
- `<APP>_CLAUDE.md` — per-app operating context (routing, constraints, voice).
- Supporting research / data files for those apps.

## Convention
- One file per app, named `<APP>_CLAUDE.md` (UPPER_SNAKE).
- Treat everything here as operator-private. Never commit beyond this README.

## Related
- [[brain/APP_REGISTRY]]
- [[CONTEXT]]
