"""Audit MCP config files for plaintext live secrets.

Scans every known MCP config location across Claude Code, Anti-Gravity,
Gemini CLI, and VS Code/Cursor. Refuses session boot if any plaintext
live key is detected — guardrail against the 2026-05-06 Stripe-key incident.

Use: python scripts/audit_mcp_secrets.py            # human report
     python scripts/audit_mcp_secrets.py --json     # machine-readable

Exit codes:
    0  no leaks detected
    1  leak detected (caller decides whether to block)
    2  scan error
"""
import argparse
import json
import os
import platform
import re
import sys
from typing import Iterable

# Paths the IDE / CLI tooling reads as MCP config — every one of these must
# stay credential-free. Add new entry points here when integrating new agents.
# Mac CEO-Agent repo path added 2026-05-19 (was ~/Downloads/business-empire-agent
# before the move — see brain/CROSS_MACHINE_SYNC.md).
_HOME = os.path.expanduser('~')
_IS_MAC = platform.system() == 'Darwin'


def _spillover_home_dir() -> str:
    """Claude Spillover HOME_DIR (scripts/spillover/CONTRACT.md section 2).

    Same resolution as scripts/spillover/{lane_key,statusline,ensure_spillover}.py:
    BRAVO_SPILLOVER_HOME overrides everything (tests point it at a temp dir).
    """
    override = os.environ.get('BRAVO_SPILLOVER_HOME')
    if override:
        return override
    if _IS_MAC:
        return os.path.join(_HOME, 'Library', 'Application Support', 'bravo-spillover')
    base = os.environ.get('LOCALAPPDATA') or os.path.join(_HOME, 'AppData', 'Local')
    return os.path.join(base, 'bravo-spillover')


if _IS_MAC:
    MCP_CONFIG_PATHS = [
        os.path.join(_HOME, '.claude.json'),
        os.path.join(_HOME, '.claude', 'mcp.json'),
        os.path.join(_HOME, '.claude', 'settings.json'),
        os.path.join(_HOME, 'Library', 'Application Support', 'Antigravity', 'User', 'mcp.json'),
        os.path.join(_HOME, 'Library', 'Application Support', 'Antigravity', 'User', 'settings.json'),
        os.path.join(_HOME, '.gemini', 'settings.json'),
        os.path.join(_HOME, '.cursor', 'mcp.json'),
        os.path.join(_HOME, 'CEO-Agent', '.vscode', 'mcp.json'),
        os.path.join(_HOME, 'CEO-Agent', '.claude', 'settings.json'),
        os.path.join(_HOME, 'CEO-Agent', '.claude', 'settings.local.json'),
        os.path.join(_HOME, 'CEO-Agent', '.mcp.json'),
    ]
else:
    # Windows branch — pre-rename Business-Empire-Agent paths kept in the
    # list so the audit still inspects them on machines that haven't moved
    # to CEO-Agent yet (leaks live on both layouts identically).
    MCP_CONFIG_PATHS = [
        r'C:\Users\User\.claude.json',
        r'C:\Users\User\.claude\mcp.json',
        r'C:\Users\User\.claude\settings.json',
        r'C:\Users\User\AppData\Roaming\Antigravity\User\mcp.json',
        r'C:\Users\User\AppData\Roaming\Antigravity\User\settings.json',
        r'C:\Users\User\.gemini\settings.json',
        r'C:\Users\User\.cursor\mcp.json',
        r'C:\Users\User\CEO-Agent\.vscode\mcp.json',
        r'C:\Users\User\CEO-Agent\.claude\settings.json',
        r'C:\Users\User\CEO-Agent\.claude\settings.local.json',
        r'C:\Users\User\CEO-Agent\.mcp.json',
        r'C:\Users\User\Business-Empire-Agent\.vscode\mcp.json',
        r'C:\Users\User\Business-Empire-Agent\.claude\settings.json',
        r'C:\Users\User\Business-Empire-Agent\.claude\settings.local.json',
        r'C:\Users\User\Business-Empire-Agent\.mcp.json',
    ]

# Claude Spillover's runtime config (scripts/spillover/CONTRACT.md section 2)
# lives outside the repo, under HOME_DIR, and must stay credential-free the same
# way every other MCP config here does.
MCP_CONFIG_PATHS.append(os.path.join(_spillover_home_dir(), 'config.json'))

# Known live-secret prefixes/patterns. Triggers a hit when found in any
# scanned config file. Order matters only for human-readable labels.
LIVE_SECRET_PATTERNS = [
    ('stripe-live-secret',     re.compile(r'sk_live_[A-Za-z0-9]{20,}')),
    ('stripe-restricted-live', re.compile(r'rk_live_[A-Za-z0-9]{20,}')),
    ('anthropic-api-key',      re.compile(r'sk-ant-[A-Za-z0-9_-]{20,}')),
    ('openai-api-key',         re.compile(r'sk-proj-[A-Za-z0-9_-]{20,}')),
    # OmniRoute (Claude Spillover fallback, CONTRACT section 1) API keys, format
    # confirmed against bravo-spillover/omniroute-src/src/shared/utils/apiKey.ts:
    #   new: sk-{16-hex machineId}-{6-hex keyId}-{8-hex crc}
    #   old: sk-{8-char random}
    # The negative lookahead plus the \b boundaries keep this from double-flagging
    # the sk-ant-... / sk-proj-... families above: neither has 8+ word chars
    # immediately after "sk-" before its next hyphen, so the old-format
    # alternative can never reach a word boundary inside either of them.
    ('omniroute-api-key',      re.compile(r'\bsk-[0-9a-f]{16}-[0-9a-f]{6}-[0-9a-f]{8}\b'
                                          r'|\bsk-(?!ant-|proj-)[A-Za-z0-9]{8}\b')),
    ('supabase-access-token',  re.compile(r'sbp_[a-f0-9]{40}')),
    ('jwt-bearer',             re.compile(r'eyJhbGciOiJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{40,}\.[A-Za-z0-9_-]{20,}')),
    ('late-api-key',           re.compile(r'(?<![A-Za-z0-9])sk_[a-f0-9]{60,}')),
    ('github-pat',             re.compile(r'gh[pousr]_[A-Za-z0-9]{36,}')),
    ('aws-access-key',         re.compile(r'AKIA[0-9A-Z]{16}')),
]

def scan_file(path: str) -> list[dict]:
    """Return list of leak dicts for one file."""
    findings = []
    if not os.path.isfile(path):
        return findings
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except OSError as e:
        return [{'path': path, 'error': str(e)}]

    for label, pat in LIVE_SECRET_PATTERNS:
        for m in pat.finditer(content):
            value = m.group(0)
            # Show only first 12 chars so report itself doesn't leak
            preview = value[:12] + '…'
            findings.append({
                'path': path,
                'kind': label,
                'preview': preview,
                'offset': m.start(),
            })
    return findings


def main(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true', help='emit JSON')
    parser.add_argument('--quiet', action='store_true',
                        help='no output on clean run (for SessionStart hook)')
    args = parser.parse_args(list(argv))

    all_findings = []
    scanned = 0
    for p in MCP_CONFIG_PATHS:
        if os.path.isfile(p):
            scanned += 1
            all_findings.extend(scan_file(p))

    if args.json:
        print(json.dumps({
            'scanned_files': scanned,
            'leak_count': len(all_findings),
            'findings': all_findings,
        }, indent=2))
        return 1 if all_findings else 0

    if not all_findings:
        if not args.quiet:
            print(f'[mcp-audit] OK — {scanned} configs scanned, zero plaintext live secrets')
        return 0

    print('[mcp-audit] LEAK DETECTED — plaintext live secrets in MCP config:')
    for f in all_findings:
        if 'error' in f:
            print(f"  ! error scanning {f['path']}: {f['error']}")
        else:
            print(f"  ! {f['kind']} in {f['path']} (preview: {f['preview']})")
    print()
    print('Remediation:')
    print('  1. Move the literal secret to .env.agents under a named key.')
    print('  2. Replace the inline value in the config with a Node.js shim:')
    print('     "command": "node", "args": ["scripts\\\\mcp_shims\\\\<service>.js"]')
    print('     (see scripts/mcp_shims/github.js for the canonical pattern;')
    print('      the shim loads .env.agents via dotenv and spawns the MCP')
    print('      binary directly with windowsHide:true — no conhost flash.)')
    print('  3. Rotate the leaked credential at the issuer.')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
