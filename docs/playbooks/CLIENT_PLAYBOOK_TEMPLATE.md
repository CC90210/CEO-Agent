---
tags: [docs, playbooks, client, template, maintainer]
purpose: Reusable template for a per-client maintainer playbook — CC's operator runbook for maintaining a client's deployed autonomous agent system (their box, their repos, their domain). Copy to NN-<client>-maintainer.md and fill the tokens. First instance: 05-breeze-maintainer.md.
owner: CC (Conaugh McKenna)
---

# Client Maintainer Playbook — {{CLIENT_NAME}}

> Copy this to `docs/playbooks/NN-{{client_slug}}-maintainer.md`, replace every `{{token}}`,
> and delete this note. The point: when you connect to {{CLIENT_NAME}}'s box you know exactly
> where to `cd` and how to spawn the Claude maintainer to fix/change things.

## Fill these tokens
- `{{CLIENT_NAME}}` / `{{client_slug}}` — e.g. BreezeAdvance / breeze
- `{{ssh_host}}` — Mac Mini SSH alias (add to `~/.ssh/config`)
- `{{client_repo_path}}` — e.g. `~/APPS/breeze-portal`
- `{{client_domain}}` — e.g. `app.breezeadvance.com` / `bridge.breezeadvance.com`
- `{{bridge_pm2}}` / `{{scheduler_pm2}}` — PM2 app names (e.g. `breeze-bridge` / `breeze-scheduler`)
- `{{employees}}` — the autonomous AI employees + their triggers

## The invariant structure (every client playbook has these sections)
0. **Model in one paragraph** — what's theirs, what runs where, how you maintain it.
1. **Connect** — `ssh {{ssh_host}}` or in person.
2. **Where everything lives** — the on-disk map (repo, bridge, agents, tools, migrations, env).
3. **Spawn the maintainer** — `cd {{client_repo_path}} && claude` → describe the change → ship.
4. **Common tasks cookbook** — deploy a change; chat down; an employee failed; see what employees
   did; restart; health check; add a sequence; apply a migration.
5. **Safety** — guards still apply; autonomous sends DRAFT-gated; subscription auth (never API key).
6. **Moving the box** — tunnels are outbound-only, so relocation needs no network reconfig.

## Rules for every client deployment
- **Full separation:** the client owns their GitHub org + Cloudflare account + domain + Supabase.
  Nothing on `oasisai.work`; zero OASIS/Bravo identity in the client's agents.
- **The maintainer is Bravo/the CEO harness** (your tool) — it builds/changes, then idles.
- **Register the client** in `brain/APP_REGISTRY.md` + `brain/C_SUITE_ARCHITECTURE.md`.
- **Health gates:** `node agents/tools/doctor.mjs` (client harness) + `machine_parity.py --check`
  (maintainer) + live probes on the client domain.

## Reference instance
- [[docs/playbooks/05-breeze-maintainer]] — the fully-worked BreezeAdvance example.
- [[docs/playbooks/INDEX]] — all playbooks.
