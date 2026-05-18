# apps/command-center — extracted

This directory was extracted to its own repo on 2026-05-18:

**Canonical location:** https://github.com/CC90210/oasis-command-center

Local clone (per CC's setup): `~/APPS/oasis-command-center`

Three files in this directory exist solely to keep the stale Vercel
project that's still rooted here from erroring on every push:

- `package.json` — minimal stub so `npm install` doesn't fail
- `vercel.json` — `ignoreCommand: "exit 0"` skips the build
- `README.md` — this file

Do NOT add real code here. All Command Center work happens in the
standalone repo.
