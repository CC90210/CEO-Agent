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


_POOL_LOCK = threading.RLock()
_WARM_POOL: dict[str, "WarmClaudeProcess"] = {}

# Limits — tune via env if a deployment has different RAM.
_POOL_MAX_SIZE = int(os.environ.get("BRAVO_WARM_POOL_MAX", "8"))
_POOL_IDLE_TIMEOUT_S = int(os.environ.get("BRAVO_WARM_IDLE_S", str(15 * 60)))

# A reaper thread is started lazily on first use (don't pay the
# bookkeeping cost when nobody's chatting).
_REAPER_STARTED = False


def _resolve_claude_bin() -> Optional[str]:
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
    ):
        self.agent = agent
        self.root = root
        self.created_at = time.time()
        self.last_used_at = self.created_at
        self.busy = True  # busy during initial spawn
        self.lock = threading.Lock()
        self.session_id: Optional[str] = resume_session_id
        self._first_prompt_consumed = False

        claude_bin = _resolve_claude_bin()
        if not claude_bin:
            raise FileNotFoundError("claude CLI not on PATH")

        # `-p` is required for --print mode. We pass the FIRST prompt as the
        # arg; subsequent prompts arrive via stdin in stream-json format.
        # --input-format stream-json keeps stdin open so the process awaits
        # more prompts after emitting the first response.
        args = [
            claude_bin,
            "-p", first_prompt,
            "--permission-mode", "bypassPermissions",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--max-turns", "12",
            "--setting-sources", "project,local",
        ]
        if resume_session_id:
            args.extend(["--resume", resume_session_id])

        env = dict(os.environ)
        env.update({
            "CI": "true",
            "NONINTERACTIVE": "true",
            "PAGER": "cat",
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
        })

        self.proc = subprocess.Popen(
            args,
            cwd=str(root),
            stdin=subprocess.PIPE,    # CHANGED from DEVNULL — we write turns here
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            env=env,
            creationflags=(0x08000000 if os.name == "nt" else 0),
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

        def _pump():
            try:
                assert self.proc.stdout is not None
                for raw in self.proc.stdout:
                    self._stdout_q.put(raw)
            except Exception:
                pass
            finally:
                self._stdout_eof = True
                self._stdout_q.put(None)  # sentinel

        self._pump_thread = threading.Thread(
            target=_pump, daemon=True, name=f"warm-pump-{agent}"
        )
        self._pump_thread.start()

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
                if self._first_prompt_consumed:
                    # New turn: write user message to stdin in stream-json format.
                    # Claude Code expects:
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
                else:
                    # First turn — prompt was already passed to claude via -p.
                    # Just mark consumed and read the response.
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


def use_or_create(
    pool_key: str,
    agent: str,
    root: Path,
    prompt_text: str,
    resume_session_id: Optional[str] = None,
) -> WarmClaudeProcess:
    """Either reuse a warm process for this pool_key or spawn a new one.

    pool_key should be `f"{tenant_id}:{agent}:{session_id_or_NEW}"` so
    different sessions get different processes.

    Caller must invoke .send_turn() to drive the conversation. If the
    returned process is being created fresh, send_turn will skip the
    stdin write (the prompt was passed via -p).
    """
    _start_reaper_once()

    with _POOL_LOCK:
        existing = _WARM_POOL.get(pool_key)
        if existing and existing.is_alive() and not existing.busy:
            existing.last_used_at = time.time()
            return existing
        # Stale or busy — kill (busy means another turn is in flight,
        # but our handler calls one-at-a-time per pool_key so this
        # shouldn't happen in practice).
        if existing:
            existing.kill(reason="stale_or_busy")
            _WARM_POOL.pop(pool_key, None)
        _evict_oldest_if_full()
        wp = WarmClaudeProcess(agent, root, prompt_text, resume_session_id)
        _WARM_POOL[pool_key] = wp
        return wp


def prewarm(
    pool_key: str,
    agent: str,
    root: Path,
) -> bool:
    """Speculatively spawn a warm process and silently consume the
    initialization turn. After this returns, the pool entry exists,
    claude has booted, MCP servers are loaded, and the next real
    turn lands instantly via send_turn().

    The "init" prompt is `system_init` — short, neutral, gets a
    boilerplate "Acknowledged" or similar from claude. We discard
    every event for that initial turn (don't forward to any client)
    so the operator never sees it. The init exchange IS in claude's
    session history, but it's prefixed clearly enough that the
    agent's persona ignores it on the user's real first prompt.

    Returns True if the process spawned and the init turn completed;
    False on FileNotFoundError (claude CLI missing) or any spawn /
    stream error. Best-effort — if pre-warm fails, the user's real
    first turn falls through to cold-spawn as before.
    """
    _start_reaper_once()

    with _POOL_LOCK:
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
        wp = WarmClaudeProcess(agent, root, "system_init", resume_session_id=None)
    except Exception:
        return False

    # Consume the init turn silently.
    consumed_ok = wp.send_turn("system_init", on_event=lambda _ev: None, max_seconds=120)
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
    """Explicit kill — used by /chat reset / sign-out flows."""
    with _POOL_LOCK:
        wp = _WARM_POOL.pop(pool_key, None)
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
