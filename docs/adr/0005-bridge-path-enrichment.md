---
adr: 0005
title: Bridge PATH enrichment for GUI-launched subprocess CLIs
status: accepted
date: 2026-05-23
deciders: [bravo, cc]
supersedes: null
superseded_by: null
---

# ADR-0005 — Bridge PATH enrichment for GUI-launched subprocess CLIs

## Context

The local bridge daemon (`bravo_cli/bridge_chat_server.py` listening on `localhost:9100`) spawns CLI subprocesses to handle chat turns — `claude` / `codex` / `gemini` binaries plus their downstream helpers (`node`, `ripgrep`, etc).

On 2026-05-23 CC's Mac chat returned "agent returned no response" for every CLI provider. Root cause was a compound bug:

1. **Slim LaunchServices PATH.** macOS launchd-spawned bridges inherit a minimal `PATH=/usr/bin:/bin:/usr/sbin:/sbin`. Homebrew-installed `gemini`, `codex`, `claude` (all in `/opt/homebrew/bin` on Apple Silicon, `/usr/local/bin` on Intel) were invisible. nvm-installed Node and friends (in `~/.nvm/versions/node/<v>/bin`) likewise invisible.
2. **Bare `shutil.which()` in `_which_cli`.** Only checked the slim inherited PATH. Returned `None` for binaries that worked perfectly in the operator's Terminal.
3. **Subprocess `env` didn't enrich PATH.** Even when `_which_cli` succeeded via fallback, the spawned CLI's own child processes inherited the slim PATH and failed (`env: node: No such file or directory`, exit 127).
4. **Warm pool inherited the same bug.** `warm_claude_pool._resolve_claude_bin` had its own bare `shutil.which`. Warm-spawned Claude died on every cold start.

Same architectural class of problem in two places. Needed one fix pattern.

## Decision

Introduce two shared helpers in `bravo_cli/_subprocess_helpers.py` AND `scripts/lib/subprocess_helpers.py` (the two copies are kept parallel by convention):

### `which_cli(name)` — enriched binary lookup

Tiered resolution:
1. `shutil.which(name)` — fast win when the binary IS on inherited PATH.
2. On Windows: also try `name + ".cmd"` / `name + ".exe"`.
3. On macOS / Linux: walk a curated list of common install dirs:
   - `/opt/homebrew/bin` (Apple Silicon Homebrew)
   - `/usr/local/bin`, `/usr/local/sbin` (Intel Homebrew + manual installs)
   - `~/.npm-global/bin` (npm `prefix=`)
   - `~/.bun/bin`, `~/.deno/bin`, `~/.cargo/bin` (Bun / Deno / Rust)
   - `~/.local/bin` (pipx, manual)
   - `/usr/bin`, `/bin` (system fallback)
4. Last resort on macOS / Linux: `bash -lc 'command -v <name> || true'` with a 1.5s timeout. A login shell sources the user's `~/.zshrc` / `~/.bash_profile`, picking up `nvm` / asdf / chruby / arbitrary versioned install dirs.

Cached per-binary for the process lifetime so the expensive login-shell fallback runs at most once per `<binary>`.

### `enriched_path(found_bin)` — subprocess PATH builder

Returns a PATH string suitable for passing as `env["PATH"]` to `subprocess.run` / `Popen`. Layered, de-duped, in priority order:

1. Parent directory of the resolved binary (so sibling helpers like `gemini-utils` resolve).
2. The curated Mac/Linux install dirs.
3. The login-shell PATH (cached).
4. The current `os.environ.get("PATH")`.

Every CLI spawn in the bridge now sets `env["PATH"] = enriched_path(<resolved bin>)`. That includes `_run_codex_cli`, `_run_gemini_cli`, the Claude cold-spawn in `_run_chat_via_claude`, and the warm-pool spawn in `warm_claude_pool.py`.

## Consequences

**Positive:**
- macOS launchd / Electron-spawned bridges find every CLI a Terminal would.
- Subprocess children (node, ripgrep, npm helpers spawned BY gemini/codex) also see the enriched PATH so their own dependencies resolve.
- One helper, three callers. Adding a future fourth caller (e.g. a `_run_aider_cli`) gets PATH parity for free.
- Diagnostic surface (`GET /diagnostics/cli`) uses the same helper so what the dashboard reports matches what chat actually spawns.

**Negative:**
- 1.5s overhead on the FIRST `_which_cli` call for any binary not in curated dirs (one-time login-shell probe). Subsequent calls are cached. Acceptable.
- The curated install-dir list is opinionated for CC's macOS setup. Other clients using exotic install methods (chruby, asdf, custom prefixes) need the bash -lc fallback to pick up their PATH — which works, but adds the 1.5s overhead per binary.
- Two copies of the helper exist (`bravo_cli/_subprocess_helpers.py` and `scripts/lib/subprocess_helpers.py`) because `bravo_cli` is a proper Python package and `scripts/` runs via `sys.path` injection. The two MUST stay byte-equivalent for the helpers; a CI check could enforce that.

## Verification

End-to-end on CC's Mac after this landed:
```
cli_status returns:
  claude:  installed=True  authenticated=True  v=2.1.81
  codex:   installed=True  authenticated=True  v=codex-cli 0.133.0
  gemini:  installed=True  authenticated=True  v=0.42.0

/chat (cli_provider=claude / codex / gemini) returns:
  event: delta data: {"text": "...real response..."}
```

Implementation commits:
- `50cfbec4` — initial PATH enrichment in bridge_chat_server.py
- `cf45747b` — also route claude lookup via which_cli
- `9b2ef600` — extract helpers to subprocess_helpers, fix cli_status + install_cli
- `ba8353d8` — warm pool PATH enrichment + cold-spawn fallback
- `f3aa0025` — observable heartbeat marker (related operational fix)

## Related

- ADR-0004 (entry-file lockstep policy) — codified the broader "shared helpers must stay in parallel" pattern.
- `claudekit` dependency (commit `cd80601c`) — separate but related: `.claude/settings.json` declares Stop hooks that call `claudekit-hooks`; install.sh / install.ps1 now install it explicitly so the hook doesn't fail silently.
