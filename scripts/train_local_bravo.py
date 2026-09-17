#!/usr/bin/env python3
"""Build and validate the private ChatML dataset for ``bravo-14b-v2``.

The builder deliberately mines repository *metadata* (module docstrings,
CAPABILITY_META declarations, and skill frontmatter) instead of copying whole
files.  Whole-file mining can memorize credentials, customer identifiers,
prompt-injection fixtures, and stale implementation details.  Stable backend
behaviour is taught through reviewed, executable examples below.

Usage:
  python scripts/train_local_bravo.py
  python scripts/train_local_bravo.py --verify data/bravo_dataset.jsonl
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import ipaddress
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Sequence
from urllib.parse import urlsplit, urlunsplit


REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = REPO_ROOT / "data" / "bravo_dataset.jsonl"
BRAVO_SYSTEM_PROMPT = (
    "You are Bravo — CC's right hand: CEO, COO, and CTO of OASIS AI Solutions in one."
)
DEFAULT_MAX_SAMPLE_CHARS = 7_600

_SKIP_SCRIPT_PARTS = {"__pycache__", "_archive", "tests", "fixtures", ".venv"}
_SKIP_SCRIPT_PATHS = {
    "scripts/llm_training/generate_dataset.py",
    "scripts/llm_training/train_unsloth.py",
}
_INJECTION_LINE = re.compile(
    r"(?i)(ignore (?:all |any )?(?:previous|prior) instructions|"
    r"reveal|print|repeat).{0,80}(system prompt|credential|secret|private key)|"
    r"email.{0,30}admin.{0,30}credential"
)
_PRIVATE_KEY = re.compile(
    r"-----BEGIN(?P<label>(?: [A-Z0-9]+)? PRIVATE KEY| PGP PRIVATE KEY BLOCK)-----.*?"
    r"-----END(?P=label)-----",
    re.DOTALL,
)
_PRIVATE_KEY_HEADER = re.compile(
    r"-----BEGIN(?:(?: [A-Z0-9]+)? PRIVATE KEY| PGP PRIVATE KEY BLOCK)-----"
)
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}")
_TOKEN_VALUE = re.compile(
    r"\b(?:sk_(?:live|test)_[A-Za-z0-9]{24,}|"
    r"rk_(?:live|test)_[A-Za-z0-9]{24,}|"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{16,}|"
    r"gh[po]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|"
    r"sbp_[A-Za-z0-9]{40,}|xox[baprs]-[A-Za-z0-9-]{16,}|"
    r"(?:AKIA|ASIA)[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{35}|"
    r"\d{6,}:[A-Za-z0-9_-]{30,}|AC[a-f0-9]{32}|"
    r"[MN][A-Za-z0-9]{23}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}|"
    r"EAA[A-Za-z0-9]{100,}|\d{14,20}\|[A-Za-z0-9]{20,40})\b"
)
_SECRET_ASSIGNMENT = re.compile(
    r'''(?ix)
    (\b(?:api[_-]?key|client[_-]?secret|password|private[_-]?key|secret|token)\b
    \s*[:=]\s*["'])
    ([^"'\r\n]{8,})
    (["'])
    '''
)
_ENV_FALLBACK = re.compile(
    r'''(?ix)
    ((?:os\.environ\.get|os\.getenv)\(\s*["']
    [A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)[A-Z0-9_]*
    ["']\s*,\s*["'])
    ([^"'\r\n]{8,})
    (["']\s*\))
    '''
)
_JWT_VALUE = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@([A-Z0-9.-]+\.[A-Z]{2,})\b", re.IGNORECASE)
_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_WINDOWS_HOME = re.compile(
    r"(?i)\b[A-Z]:\\Users\\[^\\\s]+(?:\\[^\s`\"']*)?"
)
_POSIX_HOME = re.compile(r"(?<![\w.])/(?:home|Users)/[^/\s]+(?:/[^\s`\"']*)?")
_LONG_ID = re.compile(r"(?<![\w.])-?\d{10,}(?![\w.])")
_PHONE = re.compile(
    r"(?<!\w)(?:\+?1[ .-]?)?\(?[2-9]\d{2}\)?[ .-]\d{3}[ .-]\d{4}(?!\w)"
)
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_URL = re.compile(r"https?://[^\s`<>\"']+")

_SAFE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "test.invalid"}
_SAFE_IP_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("127.0.0.0/8", "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
)


class DatasetValidationError(ValueError):
    """Raised when a JSONL row is unsafe or incompatible with the trainer."""


@dataclass(frozen=True)
class TrainingSample:
    source: str
    kind: str
    user: str
    assistant: str
    source_sha256: str

    def to_record(self) -> dict[str, list[dict[str, str]]]:
        return {
            "messages": [
                {"role": "system", "content": BRAVO_SYSTEM_PROMPT},
                {"role": "user", "content": self.user},
                {"role": "assistant", "content": self.assistant},
            ]
        }


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _source_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _clean_url(match: re.Match[str]) -> str:
    raw = match.group(0)
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return "<REDACTED_URL>"
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return "<REDACTED_URL>"
    # Query strings routinely carry OAuth codes, signatures, and customer IDs.
    netloc = hostname
    try:
        port = parsed.port
    except ValueError:
        return "<REDACTED_URL>"
    if port:
        netloc += f":{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def _clean_email(match: re.Match[str]) -> str:
    domain = match.group(1).lower()
    return match.group(0) if domain in _SAFE_EMAIL_DOMAINS else "<REDACTED_EMAIL>"


def _clean_ipv4(match: re.Match[str]) -> str:
    raw = match.group(0)
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return raw
    if any(address in network for network in _SAFE_IP_NETWORKS):
        return raw
    return "<REDACTED_IP>"


def sanitize_text(text: str) -> str:
    """Remove values that should never become memorized model weights."""

    clean = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    clean = _PRIVATE_KEY.sub("<REDACTED_PRIVATE_KEY>", clean)
    clean = _PRIVATE_KEY_HEADER.sub("<REDACTED_PRIVATE_KEY>", clean)
    clean = _BEARER_TOKEN.sub("Bearer <REDACTED_TOKEN>", clean)
    clean = _TOKEN_VALUE.sub("<REDACTED_SECRET>", clean)
    clean = _SECRET_ASSIGNMENT.sub(r"\1<REDACTED_SECRET>\3", clean)
    clean = _ENV_FALLBACK.sub(r"\1<REDACTED_SECRET>\3", clean)
    clean = _JWT_VALUE.sub("<REDACTED_JWT>", clean)
    clean = _EMAIL.sub(_clean_email, clean)
    clean = _UUID.sub("<REDACTED_UUID>", clean)
    clean = _WINDOWS_HOME.sub("<REPO_PATH>", clean)
    clean = _POSIX_HOME.sub("<HOME_PATH>", clean)
    clean = _LONG_ID.sub("<REDACTED_ID>", clean)
    clean = _PHONE.sub("<REDACTED_PHONE>", clean)
    clean = _IPV4.sub(_clean_ipv4, clean)
    clean = _URL.sub(_clean_url, clean)
    return "\n".join(line.rstrip() for line in clean.splitlines()).strip()


def _remove_injection_fixtures(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if _INJECTION_LINE.search(line):
            lines.append("[Prompt-injection fixture omitted from training corpus.]")
        else:
            lines.append(line)
    return "\n".join(lines)


def _truncate_at_line(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    clipped = text[: limit - 52]
    boundary = clipped.rfind("\n")
    if boundary >= limit // 2:
        clipped = clipped[:boundary]
    return clipped.rstrip() + "\n[Excerpt truncated by dataset builder.]"


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized
    end = normalized.find("\n---\n", 4)
    if end < 0:
        return {}, normalized
    values: dict[str, str] = {}
    for line in normalized[4:end].splitlines():
        if ":" not in line or line[:1].isspace():
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values, normalized[end + 5 :]


def _capability_meta(tree: ast.Module) -> dict:
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "CAPABILITY_META" for target in targets):
            continue
        value = node.value
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _command_lines(text: str, limit: int = 12) -> list[str]:
    commands: list[str] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("$>").strip()
        if re.match(r"^(?:python|py|npm|npx|ollama)\s+", line, re.IGNORECASE):
            commands.append(sanitize_text(line))
        if len(commands) >= limit:
            break
    return commands


def _public_symbols(tree: ast.Module, limit: int = 14) -> list[str]:
    symbols: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_") or node.name == "__main__":
                symbols.append(node.name)
        if len(symbols) >= limit:
            break
    return symbols


def _iter_python_catalog(repo_root: Path) -> Iterator[TrainingSample]:
    scripts_root = repo_root / "scripts"
    for path in sorted(scripts_root.rglob("*.py"), key=lambda item: item.as_posix().lower()):
        relative = path.relative_to(repo_root)
        if any(part in _SKIP_SCRIPT_PARTS for part in relative.parts):
            continue
        if relative.as_posix() in _SKIP_SCRIPT_PATHS:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=relative.as_posix())
        except (OSError, UnicodeError, SyntaxError):
            continue
        module_doc = ast.get_docstring(tree, clean=True) or ""
        meta = _capability_meta(tree)
        if not module_doc and not meta:
            continue

        safe_doc = sanitize_text(_remove_injection_fixtures(module_doc))
        purpose = safe_doc.split("\n\n", 1)[0].strip()
        commands = _command_lines(safe_doc)
        symbols = _public_symbols(tree)
        response = [f"Canonical path: `{relative.as_posix()}`."]
        if purpose:
            response.extend(("", "Purpose:", _truncate_at_line(purpose, 1_400)))
        if meta:
            lifecycle = sanitize_text(str(meta.get("lifecycle", "unspecified")))
            risk = sanitize_text(str(meta.get("risk", "unspecified")))
            category = sanitize_text(str(meta.get("category", "unspecified")))
            response.extend(("", f"Registry: category={category}; lifecycle={lifecycle}; risk={risk}."))
        if symbols:
            response.extend(("", "Public entry points: " + ", ".join(f"`{name}`" for name in symbols) + "."))
        if commands:
            response.extend(("", "Documented CLI forms:", *(f"- `{command}`" for command in commands)))
        response.extend(
            (
                "",
                "Read the live file and run its `--help`/read-only command before acting; "
                "credentials stay in the sanctioned secret store and mutations retain their approval gates.",
            )
        )
        yield TrainingSample(
            source=relative.as_posix(),
            kind="script_catalog",
            user=f"In Business-Empire-Agent, what does `{relative.as_posix()}` do and how should I use it?",
            assistant=_truncate_at_line("\n".join(response), 4_000),
            source_sha256=_source_sha256(path),
        )


def _skill_license(skill_dir: Path) -> str:
    candidates = [
        skill_dir / name
        for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING")
        if (skill_dir / name).is_file()
    ]
    if not candidates:
        return "repo-internal-or-unknown"
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in candidates).lower()
    if any(marker in text for marker in ("proprietary", "all rights reserved", "anthropic")):
        return "restricted"
    if any(marker in text for marker in ("mit license", "apache license", "bsd license")):
        return "permissive"
    return "unknown"


def _body_intro(body: str) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if stripped.startswith(("```", "<!--", "[[")):
            continue
        current.append(stripped)
        if sum(len(part) for part in current) > 900:
            break
    if current:
        paragraphs.append(" ".join(current))
    return paragraphs[0] if paragraphs else ""


def _iter_skill_catalog(repo_root: Path) -> Iterator[TrainingSample]:
    skills_root = repo_root / "skills"
    skill_files = sorted(skills_root.rglob("SKILL.md"), key=lambda item: item.as_posix().lower())
    for path in skill_files:
        relative_skill = path.relative_to(skills_root)
        if any(part.startswith("_") for part in relative_skill.parts):
            continue
        raw = path.read_text(encoding="utf-8", errors="strict")
        meta, body = _frontmatter(raw)
        relative = path.relative_to(repo_root).as_posix()
        name = sanitize_text(meta.get("name") or path.parent.name)
        description = sanitize_text(meta.get("description", ""))
        triggers = sanitize_text(meta.get("triggers", ""))
        tier = sanitize_text(meta.get("tier", "unspecified"))
        license_status = _skill_license(path.parent)

        response = [f"Skill: `{name}`", f"Canonical file: `{relative}`", f"Tier: `{tier}`"]
        if description:
            response.append(f"Use it for: {_truncate_at_line(description, 1_200)}")
        if triggers:
            response.append(f"Registered triggers: {_truncate_at_line(triggers, 900)}")
        if license_status != "restricted":
            intro = sanitize_text(_remove_injection_fixtures(_body_intro(body)))
            if intro:
                response.append(f"Workflow summary from the live skill: {_truncate_at_line(intro, 1_000)}")
            commands = _command_lines(_remove_injection_fixtures(body), limit=8)
            if commands:
                response.extend(("Documented commands:", *(f"- `{command}`" for command in commands)))
        else:
            response.append(
                "The bundled instructions have restricted provenance, so only registry metadata is embedded; "
                "open the live skill at runtime for its full workflow."
            )
        response.append("Use the live skill file when executing; this catalog entry is routing knowledge, not current state.")
        yield TrainingSample(
            source=relative,
            kind="skill_catalog",
            user=(
                f"When should Bravo use the `{name}` skill defined at `{relative}`, "
                "and where is its canonical workflow?"
            ),
            assistant=_truncate_at_line("\n\n".join(response), 4_200),
            source_sha256=_source_sha256(path),
        )


def _markdown_sections(text: str) -> Iterator[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^(#{2,3})\s+(.+?)\s*$", text))
    for index, match in enumerate(matches):
        level = len(match.group(1))
        end = len(text)
        for following in matches[index + 1 :]:
            if len(following.group(1)) <= level:
                end = following.start()
                break
        yield match.group(2).strip(), text[match.end() : end].strip()


def _iter_persona_rules(repo_root: Path) -> Iterator[TrainingSample]:
    requested = {
        "brain/SOUL.md": (
            "identity",
            "personality",
            "core values",
            "prime directive",
            "communication rules",
        ),
        "AGENTS.md": (
            "tool & verification discipline",
            "identity — when cc asks",
            "triage",
            "credentials and security",
            "outbound chokepoint",
            "verification",
            "no destructive operations",
            "untrusted content discipline",
        ),
    }
    for relative, needles in requested.items():
        path = repo_root / relative
        text = path.read_text(encoding="utf-8", errors="strict")
        for heading, body in _markdown_sections(text):
            lowered = heading.lower()
            if not any(needle in lowered for needle in needles):
                continue
            safe = sanitize_text(body)
            if not safe:
                continue
            yield TrainingSample(
                source=relative,
                kind="persona_rule",
                user=f"What is Bravo's repository rule for “{sanitize_text(heading)}”?",
                assistant=_truncate_at_line(safe, 5_400),
                source_sha256=_source_sha256(path),
            )


def _curated_backend_samples() -> Sequence[TrainingSample]:
    entries = [
        (
            "identity",
            "Introduce yourself to CC in one sentence and name your operating roles.",
            "I'm Bravo, CC's right hand — CEO, COO, and CTO in one — running through the local model this time. What do you need?",
        ),
        (
            "network_concepts",
            "Explain the difference between DNS resolution, HTTP scraping, discovering this machine's public IP, and logging a visitor's IP.",
            "DNS resolution maps a hostname to addresses with `socket`; it does not download a page. HTTP scraping makes an HTTP request and parses the response. A public-IP service reports the caller's outward-facing address. A Flask/FastAPI server logs the visitor address from the accepted socket, using forwarding headers only when a known reverse proxy is configured to overwrite them.",
        ),
        (
            "backend_code",
            "Write a typed Python function that accepts a hostname or URL and resolves its hostname to one IPv4 address without making an HTTP request.",
            '''```python
from __future__ import annotations

import socket
from urllib.parse import urlsplit


def resolve_ipv4(value: str) -> str:
    """Resolve a hostname or URL through DNS; raise a clear error on bad input."""
    candidate = value.strip()
    if not candidate:
        raise ValueError("hostname is required")
    parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"could not extract a hostname from {value!r}")
    ascii_hostname = hostname.encode("idna").decode("ascii")
    try:
        return socket.gethostbyname(ascii_hostname)
    except socket.gaierror as exc:
        raise LookupError(f"DNS resolution failed for {hostname!r}") from exc
```

`socket.gethostbyname()` performs IPv4 DNS resolution only. Use `socket.getaddrinfo(..., family=socket.AF_UNSPEC)` when the caller needs both IPv4 and IPv6.''',
        ),
        (
            "backend_code",
            "Build a Flask endpoint that writes bounded JSON visitor-IP logs and trusts X-Forwarded-For only from configured reverse proxies.",
            '''```python
from __future__ import annotations

import ipaddress
import json
import logging
import os
from logging.handlers import TimedRotatingFileHandler

from flask import Flask, request


app = Flask(__name__)
handler = TimedRotatingFileHandler("visitor-ip.jsonl", when="midnight", backupCount=14, encoding="utf-8")
handler.setFormatter(logging.Formatter("%(message)s"))
logger = logging.getLogger("visitor_ip")
logger.setLevel(logging.INFO)
logger.addHandler(handler)


def _trusted_proxy_networks() -> list[ipaddress._BaseNetwork]:
    values = (value.strip() for value in os.getenv("TRUSTED_PROXY_CIDRS", "").split(","))
    return [ipaddress.ip_network(value) for value in values if value]


def visitor_ip() -> str:
    peer_text = request.remote_addr or ""
    try:
        peer = ipaddress.ip_address(peer_text)
    except ValueError:
        return "unknown"
    if any(peer in network for network in _trusted_proxy_networks()):
        # The trusted edge must overwrite, not append to, X-Forwarded-For.
        forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            return "unknown"
    return str(peer)


@app.get("/visit")
def record_visit() -> tuple[dict[str, bool], int]:
    user_agent = request.headers.get("User-Agent", "")[:512].replace("\\n", " ").replace("\\r", " ")
    logger.info(json.dumps({"ip": visitor_ip(), "user_agent": user_agent}, separators=(",", ":")))
    return {"ok": True}, 200
```

Run the Flask application behind a production WSGI server. Set `TRUSTED_PROXY_CIDRS` only to proxy networks you control; otherwise a client can spoof `X-Forwarded-For`. The rotating handler enforces a 14-file retention cap.''',
        ),
        (
            "backend_code",
            "Implement a thread-safe token-bucket rate limiter whose clock cannot move backward and whose capacity invariant cannot be exceeded.",
            '''```python
from __future__ import annotations

import time
from threading import Lock


class TokenBucket:
    def __init__(self, capacity: float, refill_per_second: float) -> None:
        if capacity <= 0 or refill_per_second <= 0:
            raise ValueError("capacity and refill_per_second must be positive")
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self.tokens = float(capacity)
        self.updated_at = time.monotonic()
        self._lock = Lock()

    def allow(self, cost: float = 1.0) -> bool:
        if cost <= 0 or cost > self.capacity:
            raise ValueError("cost must be positive and no greater than capacity")
        with self._lock:
            now = time.monotonic()
            elapsed = max(0.0, now - self.updated_at)
            self.updated_at = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
            if self.tokens < cost:
                return False
            self.tokens -= cost
            return True
```

This limiter is process-local. For multiple workers, put the bucket state and update in one atomic Redis Lua script or another shared transactional store.''',
        ),
        (
            "backend_code",
            "Write an async FastAPI webhook endpoint that verifies the raw-body HMAC, rejects stale requests, and avoids timing-leaky comparison.",
            '''```python
from __future__ import annotations

import hashlib
import hmac
import os
import time

from fastapi import FastAPI, Header, HTTPException, Request


app = FastAPI()
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"].encode("utf-8")


@app.post("/webhooks/events")
async def receive_event(
    request: Request,
    x_webhook_signature: str = Header(...),
    x_webhook_timestamp: str = Header(...),
) -> dict[str, bool]:
    if not x_webhook_timestamp.isdigit():
        raise HTTPException(400, "invalid timestamp")
    timestamp = int(x_webhook_timestamp)
    if abs(int(time.time()) - timestamp) > 300:
        raise HTTPException(401, "stale webhook")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 1_000_000:
            raise HTTPException(413, "payload too large")
        chunks.append(chunk)
    body = b"".join(chunks)
    signed = x_webhook_timestamp.encode("ascii") + b"." + body
    expected = hmac.new(WEBHOOK_SECRET, signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_webhook_signature):
        raise HTTPException(401, "invalid signature")
    # Persist the provider event ID behind a UNIQUE constraint before side effects.
    return {"accepted": True}
```

Read and verify the exact raw bytes before JSON parsing. The production write path must claim a provider event ID atomically so retries are idempotent.''',
        ),
        (
            "backend_code",
            "Create a FastAPI JWT dependency that fixes the algorithm and validates issuer and audience instead of merely decoding a token.",
            '''```python
from __future__ import annotations

import os
from typing import Any

import jwt
from fastapi import Header, HTTPException


JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ISSUER = os.environ["JWT_ISSUER"]
JWT_AUDIENCE = os.environ["JWT_AUDIENCE"]


def require_claims(authorization: str = Header(...)) -> dict[str, Any]:
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "missing bearer token")
    try:
        claims = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "invalid token") from exc
    return claims
```

For asymmetric production tokens, fetch and cache the issuer's JWKS and pin the expected asymmetric algorithm; never accept the token header's algorithm as policy.''',
        ),
        (
            "backend_code",
            "Show a parameterized, tenant-scoped SQLite write with an idempotency key and an atomic transaction.",
            '''```python
from __future__ import annotations

import sqlite3
from pathlib import Path


def record_event(
    database_path: Path,
    *,
    tenant_id: str,
    idempotency_key: str,
    payload_json: str,
) -> bool:
    if not tenant_id or not idempotency_key:
        raise ValueError("tenant_id and idempotency_key are required")
    with sqlite3.connect(database_path, timeout=10.0) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        cursor = connection.execute(
            """
            INSERT INTO webhook_events (tenant_id, idempotency_key, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(tenant_id, idempotency_key) DO NOTHING
            """,
            (tenant_id, idempotency_key, payload_json),
        )
        return cursor.rowcount == 1
```

Back this write with `UNIQUE (tenant_id, idempotency_key)` and `NOT NULL` constraints. Business-Empire-Agent's live remote SQLite-compatible backend is Turso, so use its canonical wrapper for production rather than inventing a second credential path.''',
        ),
        (
            "backend_code",
            "Write a bounded HTTP text fetcher that rejects non-HTTP schemes, sets a timeout, caps bytes, and fails loudly on bad status.",
            '''```python
from __future__ import annotations

from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def fetch_text(url: str, *, timeout_seconds: float = 15.0, max_bytes: int = 2_000_000) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("an absolute http(s) URL is required")
    request = Request(url, headers={"User-Agent": "BravoResearch/1.0"})
    with urlopen(request, timeout=timeout_seconds) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"HTTP request failed with status {response.status}")
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ValueError("response exceeded byte limit")
        charset = response.headers.get_content_charset() or "utf-8"
        return body.decode(charset, errors="replace")
```

For URLs supplied by untrusted users, add SSRF controls: resolve every redirect target, reject private/link-local/loopback ranges, and connect through a transport that pins the validated address to prevent DNS rebinding. In this repo, prefer `python scripts/research_fetch.py <url> --json`.''',
        ),
        (
            "backend_code",
            "Write a Python DNS helper that returns deduplicated IPv4 and IPv6 addresses without making an HTTP request.",
            '''```python
from __future__ import annotations

import socket


def resolve_addresses(hostname: str, port: int = 443) -> list[str]:
    """Resolve both address families and preserve resolver order."""
    normalized = hostname.strip().encode("idna").decode("ascii")
    if not normalized:
        raise ValueError("hostname is required")
    try:
        answers = socket.getaddrinfo(
            normalized,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise LookupError(f"DNS resolution failed for {hostname!r}") from exc
    return list(dict.fromkeys(answer[4][0] for answer in answers))
```

`socket.getaddrinfo()` asks the configured DNS resolver for address records. It does not scrape the domain or discover the visitor address of an HTTP request.''',
        ),
        (
            "backend_code",
            "Build a FastAPI visitor-IP endpoint that logs JSON and accepts X-Forwarded-For only when the direct peer is a configured trusted proxy.",
            '''```python
from __future__ import annotations

import ipaddress
import json
import logging
import os

from fastapi import FastAPI, Request


app = FastAPI()
logger = logging.getLogger("visitor_ip")
TRUSTED_PROXIES = tuple(
    ipaddress.ip_network(value.strip())
    for value in os.getenv("TRUSTED_PROXY_CIDRS", "").split(",")
    if value.strip()
)


def client_ip(request: Request) -> str:
    peer_text = request.client.host if request.client else ""
    try:
        peer = ipaddress.ip_address(peer_text)
    except ValueError:
        return "unknown"
    if any(peer in network for network in TRUSTED_PROXIES):
        forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            return "unknown"
    return str(peer)


@app.get("/visit")
async def record_visit(request: Request) -> dict[str, bool]:
    logger.info(json.dumps({"ip": client_ip(request)}, separators=(",", ":")))
    return {"ok": True}
```

Configure `TRUSTED_PROXY_CIDRS` with only the reverse proxies you control, and configure that edge to overwrite incoming forwarding headers. An untrusted client must never be allowed to select the logged address.''',
        ),
        (
            "backend_code",
            "Write a complete TypeScript Next.js webhook route that verifies a timestamped raw-body HMAC before parsing JSON.",
            '''```typescript
import * as crypto from "node:crypto";

const MAX_BODY_BYTES = 1_000_000;
const MAX_AGE_SECONDS = 300;

export async function POST(request: Request): Promise<Response> {
  const timestampText = request.headers.get("x-webhook-timestamp") ?? "";
  const suppliedHex = request.headers.get("x-webhook-signature") ?? "";
  if (!/^\\d+$/.test(timestampText) || !/^[a-f0-9]{64}$/i.test(suppliedHex)) {
    return Response.json({ error: "invalid signature headers" }, { status: 400 });
  }
  const timestamp = Number(timestampText);
  if (Math.abs(Math.floor(Date.now() / 1000) - timestamp) > MAX_AGE_SECONDS) {
    return Response.json({ error: "stale webhook" }, { status: 401 });
  }
  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (!Number.isFinite(contentLength) || contentLength > MAX_BODY_BYTES) {
    return Response.json({ error: "payload too large" }, { status: 413 });
  }
  if (!request.body) {
    return Response.json({ error: "empty payload" }, { status: 400 });
  }
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    received += value.byteLength;
    if (received > MAX_BODY_BYTES) {
      await reader.cancel();
      return Response.json({ error: "payload too large" }, { status: 413 });
    }
    chunks.push(value);
  }
  const rawBody = Buffer.concat(chunks.map((chunk) => Buffer.from(chunk)), received);
  const secret = process.env.WEBHOOK_SECRET;
  if (!secret) throw new Error("WEBHOOK_SECRET is not configured");
  const signed = Buffer.concat([Buffer.from(`${timestampText}.`), rawBody]);
  const expected = crypto.createHmac("sha256", secret).update(signed).digest();
  const supplied = Buffer.from(suppliedHex, "hex");
  if (supplied.length !== expected.length || !crypto.timingSafeEqual(expected, supplied)) {
    return Response.json({ error: "invalid signature" }, { status: 401 });
  }
  const event: unknown = JSON.parse(rawBody.toString("utf8"));
  return Response.json({ accepted: true, eventReceived: event !== null });
}
```

Verify the exact bytes before JSON parsing. The production handler should then insert the provider event ID behind a unique constraint before causing side effects.''',
        ),
        (
            "direct_execution",
            "Write an authorized internal-service health checker now. Answer with complete Python and one run command, without generic disclaimer bloat.",
            '''```python
from __future__ import annotations

import argparse
import asyncio

import httpx


async def check(client: httpx.AsyncClient, url: str) -> tuple[str, int]:
    response = await client.get(url)
    response.raise_for_status()
    return url, response.status_code


async def main(urls: list[str], concurrency: int, timeout: float) -> None:
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async def bounded(url: str) -> tuple[str, int]:
            async with semaphore:
                return await check(client, url)

        for url, status in await asyncio.gather(*(bounded(url) for url in urls)):
            print(f"{status} {url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("urls", nargs="+")
    parser.add_argument("--concurrency", type=int, default=4, choices=range(1, 17))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    asyncio.run(main(args.urls, args.concurrency, args.timeout))
```

Run: `python health_check.py https://example.com/health --concurrency 4 --timeout 10`.''',
        ),
    ]
    samples = []
    for kind, user, assistant in entries:
        safe_user = sanitize_text(user)
        safe_assistant = sanitize_text(assistant)
        samples.append(
            TrainingSample(
                source="curated/backend_patterns",
                kind=kind,
                user=safe_user,
                assistant=safe_assistant,
                source_sha256=_sha256_bytes((safe_user + "\n" + safe_assistant).encode("utf-8")),
            )
        )
    return samples


def build_samples(repo_root: Path = REPO_ROOT) -> list[TrainingSample]:
    """Build a deterministic, deduplicated corpus from reviewed source classes."""

    candidates: Iterable[TrainingSample] = (
        *_curated_backend_samples(),
        *_iter_persona_rules(repo_root),
        *_iter_python_catalog(repo_root),
        *_iter_skill_catalog(repo_root),
    )
    deduplicated: dict[str, TrainingSample] = {}
    for sample in candidates:
        user = sanitize_text(sample.user)
        assistant = sanitize_text(sample.assistant)
        if not user or not assistant:
            continue
        key = _sha256_bytes((user.casefold().strip() + "\n" + assistant.casefold().strip()).encode("utf-8"))
        deduplicated.setdefault(
            key,
            TrainingSample(
                source=sample.source,
                kind=sample.kind,
                user=user,
                assistant=assistant,
                source_sha256=sample.source_sha256,
            ),
        )
    return sorted(
        deduplicated.values(),
        key=lambda sample: (sample.kind, sample.source.casefold(), sample.user.casefold()),
    )


def _sensitive_match(text: str) -> str | None:
    checks = (
        ("private key", _PRIVATE_KEY),
        ("private key header", _PRIVATE_KEY_HEADER),
        ("bearer token", _BEARER_TOKEN),
        ("provider token", _TOKEN_VALUE),
        ("literal secret assignment", _SECRET_ASSIGNMENT),
        ("hardcoded environment secret fallback", _ENV_FALLBACK),
        ("JWT", _JWT_VALUE),
        ("phone number", _PHONE),
        ("UUID", _UUID),
        ("Windows home path", _WINDOWS_HOME),
        ("POSIX home path", _POSIX_HOME),
    )
    for label, pattern in checks:
        if pattern.search(text):
            return label
    for match in _EMAIL.finditer(text):
        if match.group(1).lower() not in _SAFE_EMAIL_DOMAINS:
            return "non-example email"
    for match in _IPV4.finditer(text):
        raw = match.group(0)
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if not any(address in network for network in _SAFE_IP_NETWORKS):
            return "non-example IP address"
    return None


def _validate_records(
    records: Iterable[dict], *, max_sample_chars: int = DEFAULT_MAX_SAMPLE_CHARS
) -> dict[str, int]:
    seen: set[str] = set()
    count = 0
    max_chars = 0
    for line_number, record in enumerate(records, 1):
        if set(record) != {"messages"} or not isinstance(record["messages"], list):
            raise DatasetValidationError(f"line {line_number}: expected only a messages array")
        messages = record["messages"]
        if [message.get("role") for message in messages] != ["system", "user", "assistant"]:
            raise DatasetValidationError(f"line {line_number}: roles must be system/user/assistant")
        if any(set(message) != {"role", "content"} for message in messages):
            raise DatasetValidationError(f"line {line_number}: each message must contain role and content only")
        if any(not isinstance(message["content"], str) or not message["content"].strip() for message in messages):
            raise DatasetValidationError(f"line {line_number}: message content must be non-empty text")
        if messages[0]["content"] != BRAVO_SYSTEM_PROMPT:
            raise DatasetValidationError(f"line {line_number}: non-canonical system prompt")
        sample_chars = sum(len(message["content"]) for message in messages)
        if sample_chars > max_sample_chars:
            raise DatasetValidationError(
                f"line {line_number}: {sample_chars} characters exceeds {max_sample_chars} limit"
            )
        sensitive = _sensitive_match("\n".join(message["content"] for message in messages))
        if sensitive:
            raise DatasetValidationError(f"line {line_number}: found {sensitive}")
        fingerprint = _sha256_bytes(
            (messages[1]["content"].casefold().strip() + "\n" + messages[2]["content"].casefold().strip()).encode("utf-8")
        )
        if fingerprint in seen:
            raise DatasetValidationError(f"line {line_number}: duplicate instruction/response")
        seen.add(fingerprint)
        count += 1
        max_chars = max(max_chars, sample_chars)
    if count == 0:
        raise DatasetValidationError("dataset is empty")
    return {"samples": count, "max_sample_chars": max_chars}


def verify_dataset(
    path: Path | str,
    *,
    max_sample_chars: int = DEFAULT_MAX_SAMPLE_CHARS,
    source_root: Path | str | None = None,
) -> dict[str, int | str]:
    dataset_path = Path(path)
    if not dataset_path.is_file():
        raise DatasetValidationError(f"dataset not found: {dataset_path}")
    records = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                raise DatasetValidationError(f"line {line_number}: blank JSONL rows are not allowed")
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise DatasetValidationError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
    stats = _validate_records(records, max_sample_chars=max_sample_chars)
    dataset_sha256 = _sha256_bytes(dataset_path.read_bytes())
    manifest_path = dataset_path.with_suffix(".manifest.json")
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DatasetValidationError(f"manifest is invalid JSON: {exc.msg}") from exc
        if manifest.get("schema_version") != 1:
            raise DatasetValidationError("unsupported dataset manifest schema")
        if manifest.get("dataset") != dataset_path.name:
            raise DatasetValidationError("dataset filename does not match manifest")
        if manifest.get("dataset_sha256") != dataset_sha256:
            raise DatasetValidationError("dataset content does not match manifest SHA-256")
        if manifest.get("samples") != stats["samples"]:
            raise DatasetValidationError("dataset row count does not match manifest")
        expected_system_hash = _sha256_bytes(BRAVO_SYSTEM_PROMPT.encode("utf-8"))
        if manifest.get("system_prompt_sha256") != expected_system_hash:
            raise DatasetValidationError("system prompt does not match manifest")
        provenance = manifest.get("provenance")
        if not isinstance(provenance, list) or len(provenance) != stats["samples"]:
            raise DatasetValidationError("dataset provenance does not match manifest row count")
        live_root = Path(source_root).resolve() if source_root is not None else None
        if live_root is None and manifest.get("repo_root_name") == REPO_ROOT.name:
            live_root = REPO_ROOT.resolve()
        for expected_line, entry in enumerate(provenance, 1):
            source = entry.get("source") if isinstance(entry, dict) else None
            if not isinstance(source, str) or not source or Path(source).is_absolute() or ".." in Path(source).parts:
                raise DatasetValidationError("manifest contains an invalid source path")
            if entry.get("line") != expected_line:
                raise DatasetValidationError("manifest provenance line numbers are invalid")
            source_hash = entry.get("source_sha256")
            if not isinstance(source_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
                raise DatasetValidationError("manifest contains an invalid source SHA-256")
            if live_root is not None and not source.startswith("curated/"):
                source_path = (live_root / source).resolve()
                try:
                    source_path.relative_to(live_root)
                except ValueError as exc:
                    raise DatasetValidationError("manifest source escapes the repository") from exc
                if not source_path.is_file():
                    raise DatasetValidationError(f"manifest source is missing: {source}")
                if _source_sha256(source_path) != source_hash:
                    raise DatasetValidationError(f"stale source provenance: {source}")
    return {**stats, "sha256": dataset_sha256}


def write_dataset(
    samples: Sequence[TrainingSample],
    output_path: Path | str = DATASET_PATH,
    *,
    repo_root: Path = REPO_ROOT,
    max_sample_chars: int = DEFAULT_MAX_SAMPLE_CHARS,
) -> dict[str, int | str]:
    output = Path(output_path)
    ordered = sorted(samples, key=lambda sample: (sample.kind, sample.source.casefold(), sample.user.casefold()))
    records = [sample.to_record() for sample in ordered]
    validation_stats = _validate_records(records, max_sample_chars=max_sample_chars)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    dataset_sha256 = _sha256_bytes(output.read_bytes())
    manifest = {
        "schema_version": 1,
        "dataset": output.name,
        "dataset_sha256": dataset_sha256,
        "samples": validation_stats["samples"],
        "max_sample_chars": validation_stats["max_sample_chars"],
        "system_prompt_sha256": _sha256_bytes(BRAVO_SYSTEM_PROMPT.encode("utf-8")),
        "repo_root_name": repo_root.name,
        "provenance": [
            {
                "line": index,
                "kind": sample.kind,
                "source": sample.source,
                "source_sha256": sample.source_sha256,
            }
            for index, sample in enumerate(ordered, 1)
        ],
    }
    manifest_path = output.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return verify_dataset(
        output,
        max_sample_chars=max_sample_chars,
        source_root=repo_root,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=DATASET_PATH)
    parser.add_argument("--verify", type=Path, help="verify an existing dataset instead of generating")
    parser.add_argument("--max-sample-chars", type=int, default=DEFAULT_MAX_SAMPLE_CHARS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.verify:
            stats = verify_dataset(
                args.verify,
                max_sample_chars=args.max_sample_chars,
                source_root=args.repo_root.resolve(),
            )
            print(json.dumps({"ok": True, "path": str(args.verify), **stats}, indent=2))
            return 0
        samples = build_samples(args.repo_root.resolve())
        stats = write_dataset(
            samples,
            args.output,
            repo_root=args.repo_root.resolve(),
            max_sample_chars=args.max_sample_chars,
        )
        print(json.dumps({"ok": True, "path": str(args.output), **stats}, indent=2))
        return 0
    except (DatasetValidationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
