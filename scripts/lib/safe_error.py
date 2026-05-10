"""Scrub credentials out of exception output before any LLM-visible surface gets it."""

from __future__ import annotations

import re
import traceback
from typing import Iterable

_CREDENTIAL_KEY_PATTERNS = [
    re.compile(r"\b[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS|CREDENTIAL|API|BEARER|JWT)\b"),
    re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{8,}"),
    re.compile(r"\bsbp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bsk-(?:ant|proj)-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[A-Z0-9]{12,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{12,}", re.IGNORECASE),
]


def scrub(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _CREDENTIAL_KEY_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    out = re.sub(
        r"((?:Authorization|X-Api-Key|api[_-]?key)\s*[:=]\s*)\S+",
        r"\1[REDACTED]",
        out,
        flags=re.IGNORECASE,
    )
    return out


def scrub_traceback(exc: BaseException) -> str:
    raw = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return scrub(raw)


def scrub_lines(lines: Iterable[str]) -> list[str]:
    return [scrub(line) for line in lines]
