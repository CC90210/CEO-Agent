"""Join multi-line className="..." string attributes onto one line (Tailwind-safe).

Next 15's loader chain rejects styled-jsx components whose className strings
span lines ("Unterminated string constant") — Next 14 tolerated them. Found
during the 2026-08 Cloudflare migration (TIKTIK); expect the same in Wave 2
apps that carry hand-wrapped Tailwind class strings.

    python scripts/join_multiline_classnames.py <app-src-dir>

Whitespace-only change: Tailwind class lists are whitespace-separated, so
collapsing newlines to single spaces is semantics-identical.
"""
import re
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "local_write",
    "triggers": [
        "next 15 unterminated string constant classname",
        "join multi-line classnames before next upgrade",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

pattern = re.compile(r'(className\s*=\s*")([^"]*?)(")', re.DOTALL)


def fix_text(text: str) -> tuple[str, int]:
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        body = m.group(2)
        if "\n" in body:
            count += 1
            body = " ".join(body.split())
        return m.group(1) + body + m.group(3)

    return pattern.sub(repl, text), count


def main(root: str) -> None:
    total_files = 0
    total_fixes = 0
    for p in Path(root).rglob("*.tsx"):
        text = p.read_text(encoding="utf-8")
        new, n = fix_text(text)
        if n:
            p.write_text(new, encoding="utf-8", newline="\n")
            total_files += 1
            total_fixes += n
            print(f"{p}: {n} joined")
    print(f"done: {total_fixes} strings across {total_files} files")


if __name__ == "__main__":
    main(sys.argv[1])
