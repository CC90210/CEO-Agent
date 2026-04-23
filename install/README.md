# Install — Bravo One-Command Setup

Idempotent installers for Windows, macOS, Linux, and WSL. Safe to re-run.
Neither script reads, writes, or copies the secrets file — they only generate
a keys-only template for the operator to fill in manually.

## Windows

```powershell
powershell -ExecutionPolicy Bypass -File install/install.ps1
```

Options:
- `-SkipPathUpdate` — don't add `~\.bravo\bin` to user PATH
- `-DryRun` — report what would happen without writing
- `-Quiet` — suppress the banner

## macOS / Linux / WSL

```bash
bash install/install.sh
```

Options:
- `--skip-path` — don't append to `~/.zshrc` or `~/.bashrc`
- `--dry-run` — report what would happen without writing

## What Gets Created

```
~/.bravo/
├── bin/
│   └── bravo (POSIX) or bravo.cmd (Windows)   # launcher shim
├── config.toml                                # copied from config/bravo-config.example.toml
├── .env.template                              # keys-only, no values
├── profiles/
│   ├── bravo.toml
│   ├── atlas.toml
│   ├── maven.toml
│   ├── aura.toml
│   └── hermes.toml
├── sessions/
│   └── bravo.sqlite                           # populated on first `bravo sessions ingest`
├── logs/
├── skills/
├── browser/
│   ├── domain-skills/
│   └── interaction-skills/
└── cache/
```

## Under the Hood

Both installers call `install/bootstrap.py` (cross-platform Python helper) which:

1. Parses `.env.agents` for **key names only** (values are never read, copied, or logged)
2. Writes `~/.bravo/.env.template` with `KEY=` lines the operator completes by hand
3. Calls `runtime.profile_home.ensure_home(...)` to create the tree + seed profiles
4. Writes the `bravo` launcher shim to `~/.bravo/bin/`

You can also invoke the bootstrap directly:

```bash
python install/bootstrap.py --check    # report prereqs, don't write
python install/bootstrap.py --json     # run + emit JSON
python install/bootstrap.py --no-shim  # skip the launcher
```

## Smoke Tests (run after install)

```bash
bravo doctor       # full 100-point health check
bravo status       # one-screen operational summary
bravo agent list   # see the 20 registered sub-agents
```

## Install Principles (Non-Negotiable)

- Windows-first. POSIX/WSL second. macOS tested opportunistically.
- No installer reads, writes, or copies the secrets file.
- No installer runs destructive database, Stripe, git, or file operations.
- Setup generates templates, checks tools, explains next actions.
- Doctor is read-only.
- Idempotent: safe to re-run any number of times.
- The `bravo` shim is a thin launcher, not a reimplementation.

## Related
- [[runtime/profile_home]] — ensure_home implementation
- [[bravo_cli/main]] — the CLI the installer wires up
- [[brain/BRAVO_PRODUCT_ROADMAP]] — where this install path fits
