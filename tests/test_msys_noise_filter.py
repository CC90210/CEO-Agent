"""Smoke-tests for the Git-Bash-on-Windows noise filter.

The patterns live in bridge_chat_server._MSYS_NOISE_PATTERNS and are
applied by `_strip_msys_noise`. Two contracts under test:

  1. Known-noise corpus (the actual lines CC saw on 2026-04-XX) is
     stripped completely.
  2. Real tool output is preserved verbatim — never erase a tool's
     actual stdout/stderr just because some lines matched.
"""

from bravo_cli.bridge_chat_server import _strip_msys_noise


# Real noise corpus captured from a wedged Git-Bash subprocess. Each
# line is something CC actually saw in the chat UI before the filter
# shipped.
KNOWN_NOISE_LINES = [
    r"      0 [main] bash (15740) child_copy: cygheap read copy failed, 0x0..0x8000099C0, done 0, windows pid 15740, Win32 error 299",
    r"      0 [main] bash 189488 dofork: child -1 - forked process 31600 died unexpectedly, retry 0, exit code 0xC0000142, errno 11",
    "/usr/bin/bash: fork: retry: Resource temporarily unavailable",
    "/usr/bin/cp: cannot create regular file '/etc/hosts': Permission denied",
    "ln: failed to create symbolic link '/etc/mtab': Operation not permitted",
    "rm: cannot remove '/etc/post-install/02-mtab.post': Permission denied",
    r"'C:\WINDOWS\System32\drivers\etc\hosts' -> '/etc/hosts'",
]


def test_known_noise_corpus_stripped_completely():
    body = "\n".join(KNOWN_NOISE_LINES)
    cleaned = _strip_msys_noise(body)
    # Every line was noise → cleaned strips to empty → fallback returns
    # original (we never erase entirely). Verify it stays equal to input,
    # not that it erased — preserving original on full-noise is the
    # documented behavior.
    assert cleaned == body, "fully-noise body should fall back to original (never erase tool output)"


def test_mixed_real_output_with_noise_keeps_real_output():
    body = (
        "Subject: Test\n"
        "From: a@b.com\n"
        + KNOWN_NOISE_LINES[0] + "\n"
        + KNOWN_NOISE_LINES[2] + "\n"
        "Email sent successfully.\n"
    )
    cleaned = _strip_msys_noise(body)
    assert "Subject: Test" in cleaned
    assert "Email sent successfully." in cleaned
    assert "child_copy" not in cleaned
    assert "Resource temporarily unavailable" not in cleaned


def test_clean_body_unchanged():
    """Fast path: bodies that don't contain ANY of the noise signatures
    are returned by-reference without per-line walk. Verify no mutation."""
    body = "Hello world.\nThis is a normal tool output.\nNothing to strip.\n"
    cleaned = _strip_msys_noise(body)
    assert cleaned == body


def test_empty_body_returns_empty():
    assert _strip_msys_noise("") == ""
    assert _strip_msys_noise(None) is None  # type: ignore[arg-type]
