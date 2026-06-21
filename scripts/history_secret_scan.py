"""Read-only git-history secret scanner (sanitized output only).

Answers the critical question for PUBLIC repos: was a real credential ever
COMMITTED to history (and thus exposed forever, even if later deleted)?

Reports filenames, commit short-shas, and the matched secret *type/prefix* only
— NEVER the secret value. Safe to run; mutates nothing. Run per repo:

    python scripts/history_secret_scan.py [<repo_path>]
"""
import re
import subprocess
import sys
from collections import defaultdict

REPO = sys.argv[1] if len(sys.argv) > 1 else "."

# Secret-shaped FILENAMES that should never be in history.
SECRET_FILE_RE = re.compile(
    r"(^|/)\.env(\.|$)|\.pem$|\.key$|credentials\.json$|service_account.*\.json$|"
    r"id_rsa$|id_ed25519$|\.p12$|\.pfx$",
    re.IGNORECASE,
)

# High-signal secret VALUE prefixes/shapes (report type only, never the value).
VALUE_PATTERNS = {
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "openai_key": re.compile(r"sk-(?:proj-|live-)?[A-Za-z0-9]{32,}"),
    "github_pat": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "stripe_live": re.compile(r"sk_live_[A-Za-z0-9]{20,}"),
    "aws_akid": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "supabase_service_jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
}

# Obvious placeholders to ignore in the value scan.
PLACEHOLDER = re.compile(r"(\.\.\.|xxxx|your[_-]|example|placeholder|REDACTED|<[^>]+>|FAKE|dummy)", re.IGNORECASE)


def git(*args):
    return subprocess.run(
        ["git", "-C", REPO, *args],
        capture_output=True, text=True, errors="replace",
    ).stdout


def main():
    print(f"== git-history secret scan: {REPO} ==")
    commits = git("rev-list", "--all", "--count").strip()
    print(f"commits scanned: {commits}")

    # 1) Secret-shaped filenames ever added.
    added = git("log", "--all", "--pretty=format:", "--name-only", "--diff-filter=A")
    # Intentionally-committed, non-secret stencils are not findings.
    allow = re.compile(r"\.(template|example|sample|dist)$", re.IGNORECASE)
    files = sorted({
        f for f in added.splitlines()
        if f and SECRET_FILE_RE.search(f) and not allow.search(f)
    })
    print(f"\n[1] secret-shaped FILENAMES ever added to history: {len(files)}")
    for f in files[:50]:
        print(f"    !! {f}")
    if not files:
        print("    (none — clean)")

    # 2) Secret VALUE patterns anywhere in full history diff (type + location only).
    full = git("log", "--all", "-p", "--no-color")
    hits = defaultdict(int)
    samples = defaultdict(list)
    cur_commit, cur_file = "", ""
    for line in full.splitlines():
        if line.startswith("commit "):
            cur_commit = line.split()[1][:9]
        elif line.startswith("+++ b/"):
            cur_file = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            if PLACEHOLDER.search(line):
                continue
            for kind, pat in VALUE_PATTERNS.items():
                if pat.search(line):
                    hits[kind] += 1
                    loc = f"{cur_commit}:{cur_file}"
                    if loc not in samples[kind] and len(samples[kind]) < 5:
                        samples[kind].append(loc)
    print(f"\n[2] secret VALUE patterns in history (type + location only, NO values):")
    if not hits:
        print("    (none — clean)")
    for kind, n in sorted(hits.items(), key=lambda x: -x[1]):
        print(f"    !! {kind}: {n} match-lines  e.g. {', '.join(samples[kind])}")

    verdict = "CLEAN" if not files and not hits else "REVIEW_NEEDED"
    print(f"\nVERDICT: {verdict}")


if __name__ == "__main__":
    main()
