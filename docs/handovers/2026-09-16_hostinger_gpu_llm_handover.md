# Handover for Claude Code — Hostinger API Access, GPU Instance (OasisGPU), Video-Gen + Custom-LLM Lanes

> **TARGET AUDIENCE**: Claude Code (Bravo's primary chassis)
> **AUTHOR**: Bravo (Kimi Code CLI session)
> **DATE**: 2026-09-16
> **SUBJECT**: Newly verified Hostinger API capability, errored GPU instance (destroy + redeploy path), SSH keypair state on CC's PC, and the two build lanes this server unlocks (video generation + QLoRA custom-LLM fine-tuning)

---

## Executive Summary

CC rented a **Hostinger GPU instance** ("OasisGPU" — RTX PRO 6000, 96 GB VRAM, Ubuntu 24.04) to run (a) video-generation GitHub repos and (b) our existing QLoRA fine-tuning pipeline (the "custom LLM" workstream). The first deploy **errored on Hostinger's side** — nothing provisioned, 0 credits burned, 6,000 credit balance intact. The fix is **Destroy → redeploy with the correct public SSH key** (details in §3).

In the same session CC added a **Hostinger API token** to `.env.agents`. I verified it live against the API (proof in §2). The API covers VPS/domains/DNS/email/billing — **not GPU** (Beta, hPanel-only, verified via 404 probes). The capability is real but not yet wired into the fleet's tooling — building `scripts/integrations/hostinger_tool.py` is the main implementation task in this handover (§4).

---

## 1. SSH Keypair State (CC's PC)

- CC generated a fresh **ed25519** keypair at `C:\Users\User\.ssh\id_ed25519`, **overwriting an existing key**. Anywhere the OLD public key was registered (GitHub, other VPSes) now rejects him. Check: `ssh -T git@github.com` — if "Permission denied", add the new public key to GitHub → Settings → SSH Keys.
- The key is **passphrase-protected**.
- Public key (safe to share, this is the deploy-form value):

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJfsU7i77XWUOxqQyH+Nqdk9oHFLyRg1QLYpoYudz8RM user@CCPC
```

- **OPEN SECURITY QUESTION (ask CC before any server work):** during the first failed GPU deploy, did CC paste the *private* key (`id_ed25519`, the `BEGIN OPENSSH PRIVATE KEY` block) into Hostinger's form instead of the public one? CC never confirmed. If yes → the private key left the PC → **rotate the keypair** (`ssh-keygen -t ed25519`, overwrite again, re-register the new pub key at GitHub + anywhere else) before provisioning anything.

---

## 2. Hostinger API — Verified Facts (evidence, not memory)

Token lives in `.env.agents` — **currently under the typo'd name `HOSTSTINGER_KEY` (line 616)**. CC was asked to rename it to **`HOSTINGER_API_TOKEN`** (the standard name the tooling below should expect) and delete the malformed line 615 (`HOSTSTINGER API KEY` — no `=`, breaks python-dotenv parsing). Pre-existing broken line 570 (`CEREBRAS API KEY:`) has the same disease — flag to CC, don't touch (`.env.agents` is CC-only per AGENTS.md).

Verified this session (2026-09-16):

| Fact | Evidence |
|---|---|
| Token is valid; account readable | `GET /api/vps/v1/virtual-machines` → **HTTP 200**, returned live fleet (e.g. `srv993801.hstgr.cloud`, KVM 2, n8n template, running) |
| Base URL | `https://developers.hostinger.com` (paths: `/api/<product>/<version>/...`) — **not** `api.hostinger.com` |
| Cloudflare bot wall | Plain `urllib` requests → **HTTP 403 `error code: 1010`**. Any client MUST send a browser `User-Agent` header (curl with a Chrome UA works) |
| Auth | `Authorization: Bearer <token>` |
| Rate limit | 90 req/min per user (see `X-RateLimit-*` headers) |
| **GPU endpoints** | **None.** `/api/gpu/v1/instances`, `/api/vps/v1/gpu`, `/api/gpu/v1/virtual-machines` all → **404**. GPU is Beta and hPanel-only |
| Docs | https://developers.hostinger.com/ — products: hosting, domains, DNS, email, VPS, WordPress, ecommerce, billing |
| Official extras | Hostinger CLI, Python/TS/PHP SDKs, and an **official MCP server** (`@hostinger/mcp`, ~372 tools, or hosted `https://mcp.hostinger.com`) — generated from the same OpenAPI spec |

`capability_probe.py` does **not** know `hostinger` yet (`unknown service 'hostinger'`) — registration is part of §4.

---

## 3. GPU Instance (OasisGPU) — Where It Stands & The Fix

- Panel state: **Status: Error**, 0 credits/hour burn, credit balance **6,000** untouched.
- Meaning: provisioning failed on Hostinger's side before the OS ever came up. There is no data, no config, nothing to preserve. Error state does not self-heal.
- **Recommendation given to CC: Destroy it and redeploy.** Steps for whoever picks this up:
  1. Resolve the §1 open question first (rotate keypair if the private key was pasted into Hostinger).
  2. hPanel → GPU → OasisGPU → **Destroy**.
  3. **+ Get GPU** → same spec if desired (RTX PRO 6000 96GB / Ubuntu 24.04) → paste the **public key one-liner** (§1) into the SSH key field.
  4. If it errors again with the correct key: Hostinger capacity/beta issue → retry later, try an alternate GPU SKU/region if offered, or open a Hostinger ticket (balance screenshot is proof nothing was consumed).
  5. Once running: `ssh root@<ip>` from CC's PC, then the server build-out in §5.
- **2026-09-16 PM update — second deploy also failed, this time INSTANTLY.** Failure-mode read: first deploy ran partway then errored (build failure); second failed at allocation (before any build). Instant-fail pattern = capacity rejection or account/credit gate, NOT anything CC configured. Hostinger's own [GPU setup doc](https://www.hostinger.com/support/how-to-set-up-a-gpu-instance-at-hostinger/) warns "GPU availability may be limited in certain regions due to high demand." Guidance given to CC: retry RTX PRO 6000 in a **different region**; if still instant-fail, try **L40S 48GB** (their own vLLM tutorial uses it; sufficient for video-gen + QLoRA 7–8B); if ALL SKUs/regions instant-fail → account-level gate → Hostinger 24/7 support ticket.
- **Billing model gotcha (from same doc):** GPU instances bill hourly from account credits (~€1 = 100 credits; 6,000 credits ≈ €60), and **if credits hit zero the instance is DESTROYED with all data**. Non-negotiable once a box is live: cost-watchdog cron (§6 idea #1) + snapshot policy (idea #2) + keep CC topped up. Also: check the "estimated continuous use time" shown at the review step before Deploy — a tiny estimate means balance is the gate.

---

## 4. Implementation Task — Wire Hostinger Into the Fleet

Build **`scripts/integrations/hostinger_tool.py`** following the `wrangler_tool.py` pattern (argparse subcommands, reads `.env.agents` via dotenv, `--json` flag before subcommand per QUICK_REFERENCE convention):

- Subcommands (start read-only): `whoami`, `vps list`, `vps get <id>`, `vps metrics <id>`, later `vps restart|stop|start <id>`, `firewall list`, `billing subscriptions`.
- Requirements: `HOSTINGER_API_TOKEN` from `.env.agents`; base URL `https://developers.hostinger.com`; **always send a browser User-Agent** (Cloudflare 1010 otherwise — this is the trap that will bite any naive implementation); respect the 90 req/min limit; never print the token.
- **RULE 4 cross-file sync once the tool exists:** register `hostinger` in `scripts/capability_probe.py` (service → env var `HOSTINGER_API_TOKEN` + check command), add routing rows to `brain/QUICK_REFERENCE.md` (Database & Infrastructure table) and `brain/CAPABILITIES.md`, and add a line to the Rule 2 tool table in **all six entry points** (CLAUDE.md, GEMINI.md, ANTIGRAVITY.md, OPENCODE.md, ZCODE.md, AGENTS.md) — or run `python scripts/genome_sync.py` if the change fits the germline pattern.
- Optional bigger play: register the **official Hostinger MCP server** (`@hostinger/mcp`) instead of/alongside the CLI tool — 372 ready-made tools. If you do, RULE 4 applies to all MCP configs (11 paths — `scripts/audit_mcp_secrets.py MCP_CONFIG_PATHS` is the authoritative list) and update the MCP count in the entry points' Inventory section. Recommendation: build the small CLI first (matches fleet idiom, works in cron), consider MCP second.

---

## 5. Server Build-Out Runbook (once OasisGPU is running)

1. **Smoke:** `nvidia-smi` (confirm the RTX PRO 6000 is visible). If Hostinger's template lacks drivers: install NVIDIA driver + CUDA, then Docker + `nvidia-container-toolkit`.
2. **Hardening:** key-only auth (`PasswordAuthentication no`), non-root sudo user, `ufw` default-deny inbound except SSH, fail2ban. Snapshot the box in hPanel after clean baseline.
3. **GitHub access from the box:** prefer SSH **agent forwarding** (`ssh -A`) so no keys live on the server; alternative is a per-repo deploy key. Never copy CC's personal private key to the server.
4. **Video-gen lane:** clone the chosen repo (ComfyUI / Wan-class model repos CC picks), run in Docker, access the web UI via **SSH tunnel** (`ssh -L 8188:localhost:8188 user@<ip>`) — never expose app ports to the public internet.
5. **Custom-LLM lane (expectation already set with CC: fine-tune, not train-from-scratch):** the pipeline already exists in this repo —
   - `scripts/run_qlora_train.py` (training runner)
   - `config/requirements.bravo-qlora.txt` (pinned deps: transformers 4.57.6, trl 1.13.0, peft 0.20.0, bitsandbytes 0.50.2 — install a CUDA-matched torch first)
   - `data/bravo_dataset.jsonl` (+ `.manifest.json`) — the Bravo personality dataset
   - Prior art docs: `docs/handover_custom_llm.md`, `docs/CODEX_HANDOVER_LOCAL_MODEL_TRAINING.md`, `docs/AI_WORKSTATION_ROADMAP.md`
   96 GB VRAM comfortably fits QLoRA on 7–8B and likely LoRA on much larger; run training as an overnight job and sync adapters back to the repo (gitignored weights path, manifest-updated).

---

## 6. Enhancement Ideas (CC said "enhance in any way" — ranked)

1. **Cost watchdog cron** (highest value): once GPU API endpoints exist (or via billing endpoints), a `cron_engine` job that alerts CC via `notify.py` when burn rate or balance crosses thresholds. GPU credits evaporate silently otherwise.
2. **Snapshot/backup policy**: scheduled hPanel snapshots of OasisGPU after baseline + after each working model/repo install.
3. **`scripts/run_qlora_train.py` remote mode**: a `--host` flag that rsyncs the dataset up, runs training over SSH, and pulls adapters back — so the whole fine-tune is one command from this repo.
4. **GPU API radar**: re-probe `/api/gpu/*` monthly (cheap cron) so the fleet notices the day Hostinger ships GPU API support and CLI management becomes possible.
5. Register the GPU box in the AI-workstation roadmap doc so Atlas can see the credit burn in finance reviews.

---

## 7. Security Notes (non-negotiable)

- The **private** key (`C:\Users\User\.ssh\id_ed25519`) never leaves the PC, never goes in `.env.agents`, never goes in any web form. Only the `.pub` one-liner does.
- `.env.agents` is CC-managed — agents may verify presence (probe pattern) but never read values into chat or edit the file.
- Hostinger token: keep it in `.env.agents` only; the CLI tool must never echo it; sending it as a Bearer header to `developers.hostinger.com` only.
- Any real mutation on Hostinger (destroy/recreate VPS, firewall changes, billing) follows RULE 8 — explicit CC approval per action. The errored OasisGPU destroy has CC's approval already (he asked whether to do it; answer was yes).

---

## 8. Verification Checklist (definition of done for this handover)

- [ ] §1 open question resolved; keypair rotated if needed; `ssh -T git@github.com` green
- [ ] `.env.agents`: line 615 deleted, `HOSTSTINGER_KEY` → `HOSTINGER_API_TOKEN` (CC does this)
- [ ] `python scripts/capability_probe.py check hostinger` → AVAILABLE
- [ ] `python scripts/integrations/hostinger_tool.py vps list` returns the fleet (browser-UA header in place)
- [ ] OasisGPU running, `ssh` in with the new key, `nvidia-smi` shows the RTX PRO 6000
- [ ] QUICK_REFERENCE + CAPABILITIES + six entry points synced (RULE 4)
- [ ] `memory/SESSION_LOG.md` updated; `state_sync.py --note` run
