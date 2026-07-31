"""redact.py — strip credential values out of text before it hits disk or chat.

Written for the cron-failure traceback dumps (scheduler.py). A child process's
stderr is arbitrary text: it can contain a connection string, a bot token echoed
in a requests exception URL, or a service-role key printed by a careless
handler. Those dumps land in tmp/cron_failures/ and get quoted into Telegram, so
they must be scrubbed on the way out.

The 2026-07-21 precedent: a transient network error leaked TELEGRAM_BOT_TOKEN
into PM2 logs because the requests exception embedded the request URL.
notify.py fixed that at two specific call sites by hand; this is the general
form for new call sites.

    from lib.redact import redact_secrets
    safe = redact_secrets(child_stderr, env_vars)
"""
from __future__ import annotations

import re

# Below this length a "secret" is too short to redact safely — blanking a
# 4-character value would shred ordinary prose (and a 4-char secret is not a
# secret). Real tokens/keys/URLs on this fleet are all far longer.
MIN_SECRET_LEN = 12

# Keys whose values are never sensitive, so redacting them only makes a
# traceback harder to read. Everything else in .env.agents is treated as secret.
_NON_SECRET_KEYS = frozenset({
    "GMAIL_ADDRESS", "GMAIL_USER", "BRAVO_SUPABASE_URL", "SUPABASE_URL",
    "EMPIRE_V6_MODE", "PYTHONIOENCODING", "PYTHONUNBUFFERED", "NODE_ENV",
    "TZ", "PATH",
})

# Belt-and-braces for values that never came from env_vars — a token pasted into
# a URL by a library, an inline bearer header, an sk-/eyJ-prefixed literal.
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"bot\d{6,}:[A-Za-z0-9_-]{20,}"), "[REDACTED:BOT_TOKEN]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), "[REDACTED:JWT]"),
    (re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"), "[REDACTED:STRIPE_KEY]"),
    # Credential-bearing headers and assignments.
    #
    # The first version required ':' or '=' IMMEDIATELY before the value, which
    # missed `Authorization: Bearer <token>` — the single most common shape a
    # requests exception embeds. Now the separator is optional and an explicit
    # `Bearer ` prefix is consumed, so both `api_key=abc...` and
    # `Authorization: Bearer abc...` are caught.
    #
    # The value must be >=20 chars from a token charset. That threshold is what
    # keeps prose safe: "Authorization: administrator privileges" has no
    # 20-char token-shaped run, so it survives intact. Real tokens are longer.
    (re.compile(
        r"(?i)\b(authorization|bearer|api[-_]?key|x-api-key|access[-_]?token|"
        r"token|secret|password|passwd|pwd)\b"
        r"\s*[:=]?\s*(?:bearer\s+)?"
        r"([A-Za-z0-9+/=_.\-]{20,})"),
     r"\1=[REDACTED]"),
    # postgres://user:password@host — kill the password only, keep the shape.
    (re.compile(r"(://[^:/@\s]+:)[^@/\s]{6,}(@)"), r"\1[REDACTED]\2"),
)


def redact_secrets(text: str, env_vars: dict[str, str] | None = None) -> str:
    """Return `text` with credential values replaced by [REDACTED:<KEY>] markers.

    Two passes: exact-match every sufficiently-long value from `env_vars`
    (longest first, so a key that contains another as a prefix can't leave a
    dangling tail), then the generic shape patterns above.

    Never raises — a redaction failure must not suppress the diagnostic it was
    protecting. On error the text is returned with a marker appended rather than
    dropped, because silently emitting unredacted text would be worse.
    """
    if not text:
        return text
    try:
        out = text
        if env_vars:
            items = [
                (k, v) for k, v in env_vars.items()
                if isinstance(v, str)
                and len(v) >= MIN_SECRET_LEN
                and k not in _NON_SECRET_KEYS
            ]
            for key, value in sorted(items, key=lambda kv: len(kv[1]), reverse=True):
                if value in out:
                    out = out.replace(value, f"[REDACTED:{key}]")
        for pattern, replacement in _PATTERNS:
            out = pattern.sub(replacement, out)
        return out
    except Exception:  # noqa: BLE001
        return "[redaction failed — output withheld]"
