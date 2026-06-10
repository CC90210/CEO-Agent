"""warm_claude_pool.py — persistent Claude Code processes for low-latency chat.

Why this exists
---------------
The earlier chat path spawned `claude -p <prompt>` fresh on every turn. Cost:
~5-30s of pure overhead (Node runtime startup + Claude Code CLI init + MCP
server boot + brain-file reads + session resume) BEFORE the model even
starts reasoning. Operators perceived chats as "slow" — that overhead was
the bulk of the latency.

Claude Code supports `--input-format stream-json` (verified via `claude --help`):
the CLI accepts subsequent user messages on stdin as JSON events while
keeping the same process alive. We exploit this to amortize cold-start
across turns.

Architecture
------------
- One process per (tenant, agent, session_id). Different sessions get
  different processes so context doesn't leak.
- Pool maintained in-memory in the bridge daemon. Bounded by
  `_POOL_MAX_SIZE` to cap RAM.
- Idle reaper kills processes after `_POOL_IDLE_TIMEOUT_S` of inactivity
  to free memory.
- Per-process lock prevents two concurrent turns from interleaving on
  the same stdin.
- Fallback: if anything goes wrong (process died, stdin closed, parse
  error, etc.) the caller can fall back to the cold-spawn path. The
  pool exposes is_alive() so callers can verify before use.

Caveats
-------
- The first turn on a NEW process still pays the cold-start cost.
  Subsequent turns are fast.
- Pre-warming on chat-widget mount (call use_or_create() before the user
  hits Send) hides cold-start entirely on first turn.
- Claude Code stream-json events are line-delimited JSON. We read each
  line and forward to the caller's event sink.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from ._subprocess_helpers import WINDOWLESS_FLAGS
# is_claude_auth_or_quota_failure lives in _claude_auth too but is consumed
# by bridge_chat_server (which inspects recent_stderr() after a failed
# send_turn) — not here. Only build_claude_spawn_env is needed in the pool.
from ._claude_auth import build_claude_spawn_env
# Multi-agent identity overlay — for SunBiz-Agent which hosts both Solara
# (CLAUDE.md) and Helios (HELIOS.md). Without this, every helios warm
# process spawned in /srv/sunbiz/sunbiz-agent reads CLAUDE.md as the
# system prompt and the operator sees Helios respond as Solara. See
# agent_roots.claude_identity_overlay for the discrimination logic.
from .agent_roots import claude_identity_overlay


_POOL_LOCK = threading.RLock()
_WARM_POOL: dict[str, "WarmClaudeProcess"] = {}

# Limits — tune via env if a deployment has different RAM.
_POOL_MAX_SIZE = int(os.environ.get("BRAVO_WARM_POOL_MAX", "8"))
_POOL_IDLE_TIMEOUT_S = int(os.environ.get("BRAVO_WARM_IDLE_S", str(15 * 60)))

# A reaper thread is started lazily on first use (don't pay the
# bookkeeping cost when nobody's chatting).
_REAPER_STARTED = False


# ─────────────────────────────────────────────────────────────────────
# Chat-lean spawn args — strip MCP servers + slash commands from the
# system prompt for the chat path. Measured 2026-05-10:
#
#   Default boot (all MCPs + skills):     ~50,000 cache_creation tokens
#   With --strict-mcp-config (empty):     ~28,940 cache_creation tokens
#   + --disable-slash-commands:           ~6,662 cache_creation tokens (87% drop)
#
# Why it's safe: the chat agent uses the built-in Read/Edit/Write/Bash/
# Glob/Grep tools. Bash is the universal escape hatch — anything an MCP
# does can also be invoked via `python scripts/<tool>.py`. Skills are
# valuable but the agent can still read individual SKILL.md files via
# Read on demand; what gets stripped is the auto-list of all skills in
# the system prompt.
#
# Override knobs (env vars):
#   OASIS_CHAT_FULL_BOOT=1       — restore the heavy default boot
#                                  (full MCPs + slash commands enabled)
#   OASIS_CHAT_MCP_CONFIG=<path> — point at a non-empty MCP config to
#                                  selectively keep some MCPs (e.g.
#                                  `~/.oasis/chat-mcp.json` with just
#                                  supabase + playwright)
# ─────────────────────────────────────────────────────────────────────
CHAT_MCP_CONFIG_PATH = Path.home() / ".oasis" / "chat-mcp.json"


def _ensure_chat_mcp_config() -> None:
    """Write the empty MCP config if it doesn't exist. Idempotent."""
    try:
        CHAT_MCP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not CHAT_MCP_CONFIG_PATH.exists():
            CHAT_MCP_CONFIG_PATH.write_text('{"mcpServers": {}}', encoding="utf-8")
    except Exception:
        # Permissions issue / read-only home / etc — non-fatal. The
        # spawn will still work, just without --mcp-config injection.
        pass


def chat_lean_args() -> list[str]:
    """Returns the args slice that strips MCPs + slash commands. Empty
    list when OASIS_CHAT_FULL_BOOT=1. Both warm + cold paths splice
    this into their spawn args."""
    if os.environ.get("OASIS_CHAT_FULL_BOOT") == "1":
        return []
    _ensure_chat_mcp_config()
    mcp_path = os.environ.get("OASIS_CHAT_MCP_CONFIG") or str(CHAT_MCP_CONFIG_PATH)
    out: list[str] = []
    if Path(mcp_path).is_file():
        out.extend(["--mcp-config", mcp_path, "--strict-mcp-config"])
    out.append("--disable-slash-commands")
    return out


def _resolve_claude_bin() -> Optional[str]:
    # Mirrors bridge_chat_server._which_cli — walk Homebrew (Apple
    # Silicon + Intel), npm-global, Bun, Deno, pipx, cargo, then fall
    # back to a bash -lc login-shell probe so we find nvm-installed
    # claude on macOS GUI launches (Electron / launchd) where the
    # inherited PATH is the slim LaunchServices set.
    bin_path = shutil.which("claude")
    if bin_path:
        return bin_path
    if os.name == "nt":
        home = Path.home()
        for c in [
            home / ".local" / "bin" / "claude.exe",
            home / "AppData" / "Roaming" / "npm" / "claude.cmd",
        ]:
            if c.is_file():
                return str(c)
        return None
    home = os.path.expanduser("~")
    candidates = [
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
        f"{home}/.npm-global/bin/claude",
        f"{home}/.bun/bin/claude",
        f"{home}/.local/bin/claude",
        f"{home}/.deno/bin/claude",
        f"{home}/.cargo/bin/claude",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    # Final fallback — ask a login shell. Sources ~/.zshrc / ~/.bash_profile
    # so nvm's claude lands in PATH and `command -v` returns it. 1.5s
    # timeout protects against a wedged profile script.
    try:
        proc = subprocess.run(
            ["bash", "-lc", "command -v claude || true"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
            creationflags=WINDOWLESS_FLAGS,
        )
        lines = (proc.stdout or "").strip().splitlines()
        if lines and lines[0] and os.path.exists(lines[0]):
            return lines[0]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _start_reaper_once() -> None:
    global _REAPER_STARTED
    with _POOL_LOCK:
        if _REAPER_STARTED:
            return
        _REAPER_STARTED = True
    t = threading.Thread(target=_reaper_loop, daemon=True, name="warm-claude-reaper")
    t.start()


def _reaper_loop() -> None:
    while True:
        try:
            time.sleep(60)
            _reap_idle()
        except Exception:
            # Reaper thread must never die — swallow and retry.
            pass


def _reap_idle() -> None:
    with _POOL_LOCK:
        now = time.time()
        keys_to_kill: list[str] = []
        for key, wp in _WARM_POOL.items():
            if wp.busy:
                continue
            if (now - wp.last_used_at) > _POOL_IDLE_TIMEOUT_S:
                keys_to_kill.append(key)
            elif not wp.is_alive():
                keys_to_kill.append(key)
        for key in keys_to_kill:
            wp = _WARM_POOL.pop(key, None)
            if wp:
                wp.kill(reason="reaper_idle")


def _evict_oldest_if_full() -> None:
    """Caller already holds _POOL_LOCK."""
    if len(_WARM_POOL) < _POOL_MAX_SIZE:
        return
    oldest_key = min(_WARM_POOL.keys(), key=lambda k: _WARM_POOL[k].last_used_at)
    wp = _WARM_POOL.pop(oldest_key, None)
    if wp:
        wp.kill(reason="evict_for_capacity")


class WarmClaudeProcess:
    """One persistent claude subprocess. Accepts user messages via stdin
    in stream-json format, emits assistant + tool events on stdout.

    Thread-safety: each instance has its own lock. Caller MUST acquire
    the lock (via send_turn) before driving stdin/stdout — concurrent
    turns on the same process would interleave and break parsing.
    """

    def __init__(
        self,
        agent: str,
        root: Path,
        first_prompt: str,
        resume_session_id: Optional[str] = None,
        force_api_key: bool = False,
        disallowed_tools: Optional[list[str]] = None,
    ):
        self.agent = agent
        self.root = root
        self.created_at = time.time()
        self.last_used_at = self.created_at
        self.busy = True  # busy during initial spawn
        self.lock = threading.Lock()
        self.session_id: Optional[str] = resume_session_id
        self._first_prompt_consumed = False
        # Records which auth path this process is spawned under. The
        # send_turn() retry logic and the bridge driver inspect this to
        # decide whether the current turn is the subscription path
        # (eligible for fallback) or already on the paid API key
        # (no further retry — surface the error).
        self.force_api_key = force_api_key
        # Role-based denied tools (the bridge passes the proxy-resolved,
        # sanitized list). Stored so use_or_create() can refuse to reuse a
        # process whose denial set differs from what the caller now needs —
        # a member's locked-down process must NEVER be recycled into an owner
        # turn. Spawned into the claude argv below as --disallowed-tools.
        self.disallowed_tools: list[str] = list(disallowed_tools or [])

        claude_bin = _resolve_claude_bin()
        if not claude_bin:
            raise FileNotFoundError("claude CLI not on PATH")

        # CRITICAL: do NOT pass `-p first_prompt` here. With
        # `--input-format stream-json` claude IGNORES the -p arg and
        # blocks waiting for the first user message on stdin. Pre-fix
        # behaviour: warm spawn would emit hook events then sit
        # silently forever — every turn looked like the agent never
        # responded to "yo wsp." Instead we send EVERY prompt
        # (including the first) via stdin in send_turn() — same
        # codepath, no special-case for the first turn.
        # See scratch/test_warm_pool.py for the smoking-gun test.
        # --output-format stream-json puts claude in non-interactive
        # JSON mode (no TUI). --input-format stream-json keeps stdin
        # open across turns.
        # Multi-agent repos (SunBiz-Agent at /srv/sunbiz/sunbiz-agent hosts
        # both Solara at CLAUDE.md AND Helios at HELIOS.md): suppress
        # project's CLAUDE.md and inject the per-agent file as system
        # prompt. Without this, the helios warm process spawned in that cwd
        # reads CLAUDE.md (Solara) and responds in Solara's voice — the
        # 2026-06-09 identity-bleed bug. Single-agent repos keep current
        # behavior (entry=CLAUDE.md, overlay returns ("","project,local")).
        identity_override, setting_sources = claude_identity_overlay(root, agent)
        args = [
            claude_bin,
            "--permission-mode", "bypassPermissions",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--max-turns", "12",
            "--setting-sources", setting_sources,
        ]
        if identity_override:
            args.extend(["--append-system-prompt", identity_override])
        # Boot-context strip — see chat_lean_args() docstring for the
        # measured 87% drop in cache_creation_input_tokens. Splice
        # before --resume so resume args (if any) come last.
        args.extend(chat_lean_args())
        # Role-based tool gating — the HARD wall for non-owner SunBiz employees.
        # Claude Code refuses to invoke a denied tool, so a locked-down warm
        # process literally cannot get a shell / write files. Empty for
        # owner/admin + CC's localhost path. Tokens were sanitized to [A-Za-z]+
        # by the bridge before reaching here; spawn is shell=False regardless.
        if self.disallowed_tools:
            args.extend(["--disallowed-tools", *self.disallowed_tools])
        if resume_session_id:
            args.extend(["--resume", resume_session_id])

        # Auth-priority env (subscription-first, API-key-on-retry). When
        # force_api_key=False we strip ANTHROPIC_API_KEY so claude falls
        # through to the OAuth token from `claude setup-token`. When
        # force_api_key=True we keep the key in env so claude bills per
        # token from console.anthropic.com. Same pattern Telegram bridge
        # uses (scripts/c_suite_context.js:buildClaudeSpawnEnv).
        env = build_claude_spawn_env(
            force_api_key=force_api_key,
            extras={
                "CI": "true",
                "NONINTERACTIVE": "true",
                "PAGER": "cat",
                "NO_COLOR": "1",
                "FORCE_COLOR": "0",
                # Phase 8.1.2 — match the cold-spawn fix in
                # bridge_chat_server.py. Hooks reference
                # ${CLAUDE_PROJECT_DIR}/scripts/hooks/*.py; without it
                # they exit 2 and Claude Code 2.1.39 swallows the
                # assistant response.
                "CLAUDE_PROJECT_DIR": str(root),
            },
        )
        # Enriched PATH — Claude Code's shebang resolves `node` via PATH,
        # and on macOS GUI-launched bridges the inherited LaunchServices
        # PATH is /usr/bin:/bin:/usr/sbin:/sbin (no /opt/homebrew, no
        # nvm). Result: warm process died immediately with
        # `env: node: No such file or directory` (exit 127). Layering
        # the enriched PATH so nvm/Homebrew node is reachable from the
        # warm subprocess. Mirrors what bridge_chat_server.py's
        # _enriched_path does for the cold-spawn path.
        try:
            try:
                from ._subprocess_helpers import enriched_path as _enriched_path  # type: ignore
            except ImportError:
                from _subprocess_helpers import enriched_path as _enriched_path  # type: ignore
            env["PATH"] = _enriched_path(claude_bin)
        except Exception:
            # Best-effort — if the helper can't import for any reason
            # we keep the existing env. Cold spawn fallback still works.
            pass

        self.proc = subprocess.Popen(
            args,
            cwd=str(root),
            stdin=subprocess.PIPE,    # CHANGED from DEVNULL — we write turns here
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env=env,
            creationflags=WINDOWLESS_FLAGS,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        # Background thread pumps stdout into a queue. Lets send_turn()
        # use queue.get(timeout=...) instead of blocking on readline().
        # Without this, a wedged claude (MCP stall, missing result event)
        # would hang send_turn for the FULL max_seconds and pin the
        # per-process lock — every other turn waiting on this process
        # would block too.
        self._stdout_q: queue.Queue = queue.Queue()
        self._stdout_eof = False
        # Stderr is captured into a rolling buffer (last ~8KB). Read by
        # is_claude_auth_or_quota_failure() after a turn fails so we can
        # tell "subscription quota hit" apart from "real bug". Claude Code
        # emits auth/quota error text on stderr right before exit. Without
        # this, the bridge had no signal to decide whether to retry with
        # the paid API key.
        self._stderr_buf: list[str] = []
        self._stderr_lock = threading.Lock()

        def _pump_stdout():
            try:
                assert self.proc.stdout is not None
                for raw in self.proc.stdout:
                    self._stdout_q.put(raw)
            except Exception:
                pass
            finally:
                self._stdout_eof = True
                self._stdout_q.put(None)  # sentinel

        def _pump_stderr():
            try:
                assert self.proc.stderr is not None
                for raw in self.proc.stderr:
                    with self._stderr_lock:
                        self._stderr_buf.append(raw)
                        # Cap at ~8KB of context. Keep the tail since the
                        # most recent error is the one we care about.
                        total = sum(len(s) for s in self._stderr_buf)
                        while total > 8192 and len(self._stderr_buf) > 1:
                            total -= len(self._stderr_buf.pop(0))
            except Exception:
                pass

        self._pump_thread = threading.Thread(
            target=_pump_stdout, daemon=True, name=f"warm-pump-{agent}"
        )
        self._pump_thread.start()
        self._stderr_thread = threading.Thread(
            target=_pump_stderr, daemon=True, name=f"warm-err-{agent}"
        )
        self._stderr_thread.start()

    def recent_stderr(self) -> str:
        """Return the captured stderr tail. Called after a turn fails so
        callers can decide whether to retry on the API key path."""
        with self._stderr_lock:
            return "".join(self._stderr_buf)

    def is_alive(self) -> bool:
        return self.proc.poll() is None

    def kill(self, reason: str = "") -> None:
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                try:
                    self.proc.stdin.close()
                except Exception:
                    pass
            self.proc.kill()
        except Exception:
            pass

    def send_turn(
        self,
        prompt_text: str,
        on_event: Callable[[dict], None],
        max_seconds: int = 300,
    ) -> bool:
        """Drive one chat turn through this process. Blocks until the
        result event arrives or max_seconds elapses. Returns True on
        clean completion.

        First turn (the one that spawned this process) reuses the
        prompt passed to __init__ — we just read events. Subsequent
        turns write a user-message JSON to stdin.

        Caller is responsible for SSE serialization — `on_event` is
        called with the raw stream-json event dict.
        """
        with self.lock:
            self.busy = True
            self.last_used_at = time.time()

            try:
                # Write user message to stdin in stream-json format on
                # EVERY turn (including the first — see __init__ note
                # about why -p was removed). Claude Code expects:
                #   {"type": "user", "message": {"role": "user",
                #     "content": [{"type": "text", "text": "..."}]}}
                if not self.proc.stdin or self.proc.stdin.closed:
                    return False
                try:
                    msg = {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": prompt_text}],
                        },
                    }
                    self.proc.stdin.write(json.dumps(msg) + "\n")
                    self.proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    return False
                self._first_prompt_consumed = True

                # Read events from the pump thread's queue with a
                # short per-line timeout. Total deadline still bounds
                # the turn at max_seconds. If the pump goes silent
                # for more than `inactivity_window` seconds without a
                # result, we declare the stream wedged and bail —
                # frees the lock so other turns don't pile up behind
                # a hung claude.
                deadline = time.time() + max_seconds
                inactivity_window = 90  # seconds with no event = wedged
                last_event_at = time.time()
                while True:
                    now = time.time()
                    if now > deadline:
                        return False
                    if (now - last_event_at) > inactivity_window:
                        # Stream went silent — claude is stuck. Bail
                        # so the per-process lock releases for other
                        # turns; caller treats this as send_turn_failed
                        # and kills the warm process.
                        return False
                    try:
                        raw = self._stdout_q.get(timeout=1.0)
                    except queue.Empty:
                        continue
                    if raw is None:
                        # Pump signaled EOF — process exited.
                        return False
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    last_event_at = time.time()

                    # Capture session_id from system/init for future --resume.
                    if (
                        ev.get("type") == "system"
                        and ev.get("subtype") == "init"
                        and not self.session_id
                    ):
                        sid = ev.get("session_id")
                        if isinstance(sid, str):
                            self.session_id = sid

                    on_event(ev)

                    # End-of-turn: claude emits a "result" event.
                    if ev.get("type") == "result":
                        return True
            finally:
                self.busy = False
                self.last_used_at = time.time()


# Sticky per-pool-key flag: once a session has fallen over to the paid API
# key (because the subscription hit quota/auth), every subsequent spawn for
# that pool_key uses the API key too. Otherwise we'd retry the subscription
# on every turn and pay the failure latency repeatedly.
_FORCED_API_KEY: set[str] = set()


def mark_force_api_key(pool_key: str) -> None:
    """Mark a pool_key as sticky-paid for the rest of this bridge session.
    Future use_or_create() calls for the same key will spawn with the
    ANTHROPIC_API_KEY in env. Called by the bridge driver after a
    successful auth-failure fallback so the next turn doesn't re-fail
    on the subscription path."""
    with _POOL_LOCK:
        _FORCED_API_KEY.add(pool_key)


def is_forced_api_key(pool_key: str) -> bool:
    """Whether this pool_key has been pinned to the paid API key path."""
    with _POOL_LOCK:
        return pool_key in _FORCED_API_KEY


def use_or_create(
    pool_key: str,
    agent: str,
    root: Path,
    prompt_text: str,
    resume_session_id: Optional[str] = None,
    force_api_key: bool = False,
    disallowed_tools: Optional[list[str]] = None,
) -> WarmClaudeProcess:
    """Either reuse a warm process for this pool_key or spawn a new one.

    pool_key should be `f"{tenant_id}:{agent}:{session_id_or_NEW}"` so
    different sessions get different processes.

    Caller must invoke .send_turn() to drive the conversation. If the
    returned process is being created fresh, send_turn will skip the
    stdin write (the prompt was passed via -p).

    force_api_key: if True (OR if pool_key is in _FORCED_API_KEY due to a
    prior fallback this session), spawn with ANTHROPIC_API_KEY in env so
    claude bills per-token instead of using the subscription OAuth token.
    """
    _start_reaper_once()
    want_disallowed = list(disallowed_tools or [])

    with _POOL_LOCK:
        # Sticky API-key flag wins — once a session falls over to paid,
        # it stays there. Callers don't need to pass force_api_key=True
        # on every subsequent turn; the pool remembers.
        effective_force_api = force_api_key or pool_key in _FORCED_API_KEY
        existing = _WARM_POOL.get(pool_key)
        if existing and existing.is_alive() and not existing.busy:
            # Reuse only if BOTH the auth mode AND the disallowed-tools set
            # match. The disallowed_tools check is the security gate: a
            # locked-down member process (e.g. Bash/Write/Edit denied) must
            # NEVER be handed back to an owner turn (full power), nor an
            # owner's full process to a member. Same kill+respawn pattern as
            # the auth-mode-mismatch path. (The role-fingerprinted pool_key
            # the bridge builds usually prevents collisions upstream; this is
            # the belt-and-suspenders gate for the exact-key reuse path.)
            if (
                existing.force_api_key == effective_force_api
                and existing.disallowed_tools == want_disallowed
            ):
                existing.last_used_at = time.time()
                return existing
            existing.kill(reason="auth_or_tool_gate_mismatch")
            _WARM_POOL.pop(pool_key, None)
        # Stale or busy — kill (busy means another turn is in flight,
        # but our handler calls one-at-a-time per pool_key so this
        # shouldn't happen in practice).
        elif existing:
            existing.kill(reason="stale_or_busy")
            _WARM_POOL.pop(pool_key, None)
        _evict_oldest_if_full()
        wp = WarmClaudeProcess(
            agent,
            root,
            prompt_text,
            resume_session_id,
            force_api_key=effective_force_api,
            disallowed_tools=want_disallowed,
        )
        _WARM_POOL[pool_key] = wp
        return wp


_PREWARM_PROMPT = (
    "[OASIS_RUNTIME_PREWARM] This is an automated initialization ping "
    "from the bridge daemon, NOT a user request. Boot your tools, "
    "load any MCP servers, and reply with exactly the single word "
    '"ready" so the runtime knows you are warm. IGNORE this exchange '
    "completely when responding to the operator's actual messages "
    "later — the user did not send this and never sees it."
)


def prewarm(
    pool_key: str,
    agent: str,
    root: Path,
    disallowed_tools: Optional[list[str]] = None,
) -> bool:
    """Speculatively spawn a warm process and silently consume the
    initialization turn. After this returns, the pool entry exists,
    claude has booted, MCP servers are loaded, and the next real
    turn lands instantly via send_turn().

    The init prompt (_PREWARM_PROMPT) is explicit: it tells the agent
    this is a runtime warmup, asks for a one-word reply, and instructs
    the agent to ignore the exchange when responding to subsequent
    user messages. The exchange IS in claude's session history, but
    the [OASIS_RUNTIME_PREWARM] tag + the explicit "ignore this"
    framing means the agent's persona treats it as out-of-band.

    Returns True if the process spawned and the init turn completed;
    False on FileNotFoundError (claude CLI missing) or any spawn /
    stream error. Best-effort — if pre-warm fails, the user's real
    first turn falls through to cold-spawn as before.
    """
    _start_reaper_once()

    # Honor the sticky API-key flag. If this pool_key already fell over
    # to the paid path in a prior turn, prewarming on the subscription
    # path would just waste 5-30s of cold-start before failing the same
    # way again. Use the same auth mode use_or_create() would resolve.
    with _POOL_LOCK:
        effective_force_api = pool_key in _FORCED_API_KEY
        existing = _WARM_POOL.get(pool_key)
        if existing and existing.is_alive():
            # Already warm — nothing to do.
            return True
        if existing:
            existing.kill(reason="prewarm_replacing_dead")
            _WARM_POOL.pop(pool_key, None)
        _evict_oldest_if_full()

    # Spawn outside the pool lock — claude startup can take 5-30s and
    # we don't want every other pool operation to block.
    try:
        wp = WarmClaudeProcess(
            agent,
            root,
            _PREWARM_PROMPT,
            resume_session_id=None,
            force_api_key=effective_force_api,
            # Match the role's denial set so the first real turn (which builds
            # the pool_key with the same role fingerprint AND checks
            # disallowed_tools equality in use_or_create) can reuse this
            # prewarmed process instead of cold-spawning a fresh one.
            disallowed_tools=disallowed_tools,
        )
    except Exception:
        return False

    # Consume the init turn silently.
    consumed_ok = wp.send_turn(_PREWARM_PROMPT, on_event=lambda _ev: None, max_seconds=120)
    if not consumed_ok:
        # Spawn worked but claude didn't reach a result event — kill
        # the half-started process so the operator's real first turn
        # gets a fresh cold-spawn instead of inheriting a wedged one.
        wp.kill(reason="prewarm_no_result")
        return False

    with _POOL_LOCK:
        _WARM_POOL[pool_key] = wp
    return True


def kill_for_session(pool_key: str) -> None:
    """Explicit kill — used by /chat reset / sign-out flows.

    Kills the exact pool_key AND any role-fingerprinted variants. Since the
    bridge now keys live processes as `{agent}:{tab_id}:{role_fp}` but
    /chat-reset only knows `{agent}:{tab_id}`, we also reap any entry whose key
    starts with `{pool_key}:` — otherwise the locked-down member's process
    would leak past reset until the idle reaper catches it. Exact-key kills
    (the original behavior) still work because the loop matches the exact key
    too."""
    with _POOL_LOCK:
        victims = [
            k for k in list(_WARM_POOL.keys())
            if k == pool_key or k.startswith(pool_key + ":")
        ]
        procs = [_WARM_POOL.pop(k, None) for k in victims]
    for wp in procs:
        if wp:
            wp.kill(reason="explicit")


def pool_status() -> dict:
    """Diagnostic — returns counts for /health endpoint."""
    with _POOL_LOCK:
        now = time.time()
        rows = []
        for key, wp in _WARM_POOL.items():
            rows.append({
                "key": key,
                "agent": wp.agent,
                "alive": wp.is_alive(),
                "busy": wp.busy,
                "age_s": int(now - wp.created_at),
                "idle_s": int(now - wp.last_used_at),
                "session_id": wp.session_id,
            })
        return {
            "size": len(_WARM_POOL),
            "max_size": _POOL_MAX_SIZE,
            "idle_timeout_s": _POOL_IDLE_TIMEOUT_S,
            "processes": rows,
        }
