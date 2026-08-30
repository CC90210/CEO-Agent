---
tags: [cloudflare, migration, secrets]
---

# Cloudflare secret manifests

One JSON per app slug (matching `../apps.json` keys). **Key NAMES only — never values.**
Values live in `.env.agents` and are injected by `scripts/integrations/wrangler_tool.py`
into the wrangler child process only.

Schema per file:

```json
{
  "secrets": [
    { "key": "TURSO_DATABASE_URL", "scope": "runtime" },
    { "key": "NEXT_PUBLIC_APP_URL", "scope": "build" },
    { "key": "STRIPE_SECRET_KEY", "source": "SUNBIZ_STRIPE_SECRET_KEY", "scope": "both" }
  ]
}
```

- `key` — the name the Worker/build expects.
- `source` — the `.env.agents` key holding the value (defaults to `key`).
- `scope` — `runtime` (wrangler secret), `build` (injected into the build env,
  e.g. `NEXT_PUBLIC_*`), or `both`.

Populated during Phase 0.5 from `wrangler_tool.py secrets-plan --app <slug> --vercel-diff`.
Related: [[brain/VERCEL_TO_CLOUDFLARE_MIGRATION]] · [[docs/ENV_KEYS_TEMPLATE]]
