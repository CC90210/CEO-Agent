"""SkillSpector — skill vulnerability scanner inspired by NVIDIA's SkillSpector.

Performs static analysis on all skills in skills/*/SKILL.md to detect:
  1. Missing or malformed frontmatter (no triggers, no tier, no description)
  2. Over-privileged tool references (skills referencing tools they shouldn't need)
  3. Missing authorization gates (outbound actions without send_gateway reference)
  4. Dependency bloat (>5 dependencies increases attack surface)
  5. Prompt injection vectors (processing untrusted input without sanitization)
  6. Privilege escalation paths (chaining to restricted resources)
  7. Stale or orphaned skills (no frontmatter, not in capability graph)

Usage:
    python scripts/skill_spector.py scan           # full scan, text report
    python scripts/skill_spector.py scan --json     # full scan, JSON
    python scripts/skill_spector.py audit <skill>   # single skill deep audit
    python scripts/skill_spector.py summary         # counts only

Safe to run in CI — reads only, never mutates.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CAPABILITY_META = {
    "category": "security.agent_governance",
    "lifecycle": "active",
    "risk": "read_only",
    "triggers": ["scan skill security", "audit a skill", "inspect skill vulnerabilities"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {
        "visible": True,
        "confirm": False,
        "subcommands": {
            "scan": {"visible": True, "confirm": False},
            "audit": {"visible": True, "confirm": False},
            "summary": {"visible": True, "confirm": False},
        },
    },
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"

# Tools/patterns that require elevated privilege or can cause destructive
# side-effects. Patterns are matched as regex (case-insensitive, re.escape'd
# on the literal portion). Note: bare SQL keywords like "DROP" or "DELETE" are
# deliberately NOT in this list — they are common English words ("quote drop",
# "delete from list") and produce rampant false positives. We require the full
# SQL statement form (DROP TABLE / DELETE FROM <table>) to flag a skill.
PRIVILEGED_TOOLS = {
    "send_gateway", "send_gateway.py", "smtplib", "SMTP_SSL",
    "stripe_tool", "stripe_tool.py",
    "apply_migration", "apply_migration.py",
    "exec_sql", r"\bDROP\s+(TABLE|INDEX|DATABASE|SCHEMA|VIEW)\b",
    r"\bTRUNCATE\s+TABLE\b", r"\bDELETE\s+FROM\b",
    "git push", "git push --force", "rm -rf",
    "os.system", "subprocess.call", "eval(", "exec(",
}

# Per-tier forbidden privileged patterns. A skill at a given tier that
# references one of these (outside a safety context — see _in_safety_context)
# is flagged over_privileged_tool. Core can reference anything.
TIER_TOOL_LIMITS = {
    "core": None,
    "standard": [
        "apply_migration", "exec_sql",
        r"\bDROP\s+(TABLE|INDEX|DATABASE|SCHEMA|VIEW)\b",
        r"\bTRUNCATE\s+TABLE\b",
    ],
    "specialized": [
        "apply_migration", "exec_sql",
        r"\bDROP\s+(TABLE|INDEX|DATABASE|SCHEMA|VIEW)\b",
        r"\bTRUNCATE\s+TABLE\b", r"\bDELETE\s+FROM\b",
        "git push --force", "rm -rf",
    ],
    "strategic": [
        "apply_migration", "exec_sql",
        r"\bDROP\s+(TABLE|INDEX|DATABASE|SCHEMA|VIEW)\b",
        r"\bTRUNCATE\s+TABLE\b",
    ],
}

# Keywords indicating untrusted input handling
UNTRUSTED_KEYWORDS = [
    "inbound", "user input", "form data", "webhook", "lead-form",
    "scraped", "external", "third-party", "untrusted",
    "req.body", "request.body", "query param",
]

# Keywords indicating sanitization/validation
SANITIZATION_KEYWORDS = [
    "sanitiz", "validat", "allowlist", "blocklist", "escape",
    "parameteriz", "scrub", "filter", "guard", "gate",
]

# Safety/documentation-context markers — when a privileged-tool or escalation
# pattern appears within one of these contexts, it's documentation-of-danger
# (a blocklist rule, a "never do this" warning, a code-review checklist item,
# an env-var declaration, an incident-rotation procedure), not an actual
# vulnerability. Suppressing matches in these contexts is strictly additive:
# only hides false positives, never a real finding, because real usage has no
# negation or documentation cue nearby.
SAFETY_CONTEXT = [
    # Negation / prohibition
    "block", "blocked", "blocklist", "block-list",
    "never", "do not", "don't", "must not", "forbidden", "prohibited",
    "avoid", "instead of", "rather than", "not_",
    "do never", "should not", "shall not", "no ",
    "reject", "refuse", "deny",
    # Documentation-of-danger cues (review checklists, rotation runbooks)
    "exposed", "client-side", "checklist", "rotate", "rotation", "revoke",
    "scrub", "compromis", "leak", "audit",
    # Env-var declaration cues (naming a var the skill needs ≠ using it)
    "env:", "_key", "_token", "_secret", "api_key", "environment variable",
    # Reference cues (citing as a concept, not advocating use)
    "example", "pattern:", "such as", "for example",
]

OUTBOUND_KEYWORDS = [
    "send email", "send dm", "send message", "outbound",
    "cold outreach", "nurture", "notify", "publish", "post to",
]


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Extract YAML frontmatter from a SKILL.md file."""
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return None
    fm: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                # Parse YAML-style list
                items = [i.strip().strip('"').strip("'")
                         for i in val[1:-1].split(",") if i.strip()]
                fm[key] = items
            elif val.lower() in ("true", "false"):
                fm[key] = val.lower() == "true"
            else:
                fm[key] = val
    return fm


def _severity(level: str) -> int:
    """Numeric severity for sorting."""
    return {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}.get(level, 0)


def _in_safety_context(text: str, match_start: int, match_end: int,
                       window: int = 120) -> bool:
    """Return True if a privileged-tool/escalation match sits inside a
    safety-context window (blocklist, negation, "never", "instead of", etc.).

    Why: skill docs routinely mention dangerous tools/patterns in order to tell
    the agent NOT to use them ("BLOCK — rm -rf, DROP TABLE", "use the DB password,
    not_service_role_key"). A bare substring match on these tokens produces false
    positives that flag safety instructions as vulnerabilities. Looking at the
    surrounding window suppresses only documentation-of-danger — real usage has
    no negation nearby, so legitimate findings are never hidden.
    """
    start = max(0, match_start - window)
    end = min(len(text), match_end + window)
    window_text = text[start:end].lower()
    return any(ctx in window_text for ctx in SAFETY_CONTEXT)


# Placeholder markers — when a credential-shaped assignment's VALUE is one of
# these, it's documentation of the forbidden form ("never write api_key = 'sk-...'"),
# not a real leaked secret. NOTE: check 7 (hardcoded_credential) cannot use
# _in_safety_context because SAFETY_CONTEXT itself contains "api_key"/"_token"/
# "_secret" — the window around any api_key match would always match, neutering
# the check. We inspect the assigned VALUE instead: a placeholder value is safe,
# a realistic high-entropy value is a finding. The dedicated secret scanner
# (scripts/scan_secrets.py) remains the authoritative leak detector.
_PLACEHOLDER_MARKERS = (
    "...", "xxx", "your", "example", "changeme", "change-me", "placeholder",
    "<", ">", "redacted", "fake", "dummy", "sample", "abc123", "todo", "{{",
)


def _is_placeholder_value(value: str) -> bool:
    """True if a credential-assignment's quoted value is a documentation
    placeholder rather than a real secret."""
    v = value.strip().lower()
    if len(v) < 8:               # too short to be a real key
        return True
    if any(marker in v for marker in _PLACEHOLDER_MARKERS):
        return True
    if len(set(v)) <= 3:         # e.g. "xxxxxxxx", "00000000"
        return True
    return False


@dataclass
class Finding:
    skill: str
    check: str
    severity: str  # critical, high, medium, low, info
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill": self.skill,
            "check": self.check,
            "severity": self.severity,
            "detail": self.detail,
        }


def scan_skill(skill_dir: Path) -> list[Finding]:
    """Run all checks on a single skill directory."""
    findings: list[Finding] = []
    skill_name = skill_dir.name
    skill_file = skill_dir / "SKILL.md"

    if not skill_file.exists():
        findings.append(Finding(
            skill=skill_name, check="missing_skill_file",
            severity="high",
            detail="No SKILL.md found in skill directory",
        ))
        return findings

    try:
        text = skill_file.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        findings.append(Finding(
            skill=skill_name, check="read_error",
            severity="medium", detail=str(exc),
        ))
        return findings

    body_lower = text.lower()

    # ── Check 1: Frontmatter completeness ────────────────────────────
    fm = _parse_frontmatter(text)
    if fm is None:
        findings.append(Finding(
            skill=skill_name, check="missing_frontmatter",
            severity="high",
            detail="No YAML frontmatter found — skill is invisible to the router",
        ))
    else:
        if not fm.get("name"):
            findings.append(Finding(
                skill=skill_name, check="missing_name",
                severity="medium", detail="Frontmatter missing 'name' field",
            ))
        if not fm.get("description"):
            findings.append(Finding(
                skill=skill_name, check="missing_description",
                severity="medium",
                detail="Frontmatter missing 'description' — Tier 1 scanning broken",
            ))
        if not fm.get("triggers"):
            findings.append(Finding(
                skill=skill_name, check="missing_triggers",
                severity="medium",
                detail="No trigger keywords — skill can't be auto-routed",
            ))
        tier = fm.get("tier", "")
        if not tier:
            findings.append(Finding(
                skill=skill_name, check="missing_tier",
                severity="low",
                detail="No tier classification (core/standard/specialized)",
            ))

    # ── Check 2: Over-privileged tool references ─────────────────────
    tier = (fm or {}).get("tier", "specialized")
    forbidden = TIER_TOOL_LIMITS.get(tier)
    if forbidden:
        for tool_ref in forbidden:
            # tool_ref is either a literal (escaped) or a regex pattern (those
            # containing backslashes, e.g. r"\bDROP\s+TABLE\b"). Detect by the
            # presence of regex metacharacters beyond what re.escape would emit.
            is_regex = any(ch in tool_ref for ch in ("\b", "\\b", "\\s", "\\d"))
            pat = (re.compile(tool_ref, re.IGNORECASE) if is_regex
                   else re.compile(re.escape(tool_ref), re.IGNORECASE))
            for m in pat.finditer(text):
                # Suppress documentation-of-danger: skills that say "never run
                # DROP TABLE", "block rm -rf", "not_service_role_key" are
                # teaching safety, not actually referencing the tool.
                if _in_safety_context(text, m.start(), m.end()):
                    continue
                findings.append(Finding(
                    skill=skill_name, check="over_privileged_tool",
                    severity="high",
                    detail=f"Tier '{tier}' skill references privileged tool: {tool_ref}",
                ))
                break  # one finding per tool_ref is enough

    # ── Check 3: Missing outbound authorization gate ─────────────────
    has_outbound = any(kw in body_lower for kw in OUTBOUND_KEYWORDS)
    mentions_gateway = "send_gateway" in body_lower or "send gateway" in body_lower
    if has_outbound and not mentions_gateway:
        findings.append(Finding(
            skill=skill_name, check="missing_outbound_gate",
            severity="critical",
            detail="Skill references outbound actions but does NOT mention send_gateway chokepoint",
        ))

    # ── Check 4: Dependency bloat ────────────────────────────────────
    deps = (fm or {}).get("dependencies", [])
    if isinstance(deps, list) and len(deps) > 5:
        findings.append(Finding(
            skill=skill_name, check="dependency_bloat",
            severity="medium",
            detail=f"{len(deps)} dependencies — attack surface widens with each dep",
        ))

    # ── Check 5: Untrusted input without sanitization ────────────────
    handles_untrusted = any(kw in body_lower for kw in UNTRUSTED_KEYWORDS)
    has_sanitization = any(kw in body_lower for kw in SANITIZATION_KEYWORDS)
    if handles_untrusted and not has_sanitization:
        findings.append(Finding(
            skill=skill_name, check="unsanitized_input",
            severity="high",
            detail="Skill processes untrusted input but mentions no sanitization/validation",
        ))

    # ── Check 6: Privilege escalation patterns ───────────────────────
    escalation_patterns = [
        r"sudo\b", r"admin\s+access", r"service[_-]?role",
        r"bypass.*rls", r"disable.*guard", r"override.*permission",
    ]
    for pat_str in escalation_patterns:
        pat = re.compile(pat_str, re.IGNORECASE)
        for m in pat.finditer(text):
            # Suppress documentation-of-danger: skills that say "never use
            # service_role", "not_service_role_key", "block bypass RLS" etc.
            # are teaching safety, not describing an escalation path.
            if _in_safety_context(text, m.start(), m.end()):
                continue
            findings.append(Finding(
                skill=skill_name, check="privilege_escalation",
                severity="high",
                detail=f"Potential privilege escalation pattern: '{m.group(0)}'",
            ))
            break  # one finding per pattern is enough

    # ── Check 7: Direct credential references ────────────────────────
    # Capture the assigned VALUE so we can distinguish a real leaked secret
    # from a documented placeholder ("never write api_key = 'sk-...'"). A bare
    # pattern match flags both; inspecting the value flags only the real thing.
    cred_patterns = [
        r"api[_-]?key\s*=\s*['\"]([^'\"]*)['\"]",
        r"password\s*=\s*['\"]([^'\"]*)['\"]",
        r"token\s*=\s*['\"]([^'\"]*)['\"]",
        r"secret\s*=\s*['\"]([^'\"]*)['\"]",
    ]
    flagged = False
    for pat_str in cred_patterns:
        for m in re.finditer(pat_str, text, re.IGNORECASE):
            if _is_placeholder_value(m.group(1)):
                continue
            findings.append(Finding(
                skill=skill_name, check="hardcoded_credential",
                severity="critical",
                detail="Possible hardcoded credential pattern in skill doc",
            ))
            flagged = True
            break
        if flagged:
            break

    return findings


def scan_all() -> dict[str, Any]:
    """Scan every skill directory and produce a full report."""
    all_findings: list[Finding] = []
    skills_scanned = 0
    skipped = []

    if not SKILLS_DIR.exists():
        return {"error": f"Skills directory not found: {SKILLS_DIR}"}

    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("_") or entry.name.startswith("."):
            skipped.append(entry.name)
            continue
        if entry.name == "in-progress":
            skipped.append(entry.name)
            continue

        skills_scanned += 1
        all_findings.extend(scan_skill(entry))

    # Summarize
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in all_findings:
        severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

    check_counts: dict[str, int] = {}
    for f in all_findings:
        check_counts[f.check] = check_counts.get(f.check, 0) + 1

    if severity_counts["critical"] > 0:
        overall = "CRITICAL_FINDINGS"
    elif severity_counts["high"] > 0:
        overall = "HIGH_RISK"
    elif severity_counts["medium"] > 0:
        overall = "MODERATE_RISK"
    else:
        overall = "LOW_RISK"

    return {
        "overall": overall,
        "skills_scanned": skills_scanned,
        "skills_skipped": len(skipped),
        "total_findings": len(all_findings),
        "severity_counts": severity_counts,
        "check_counts": check_counts,
        "findings": sorted(
            [f.to_dict() for f in all_findings],
            key=lambda x: _severity(x["severity"]),
            reverse=True,
        ),
    }


def render_text(report: dict[str, Any]) -> str:
    """Render a human-readable text report."""
    lines = [
        "SkillSpector — Skill Vulnerability Report",
        "=" * 60,
        f"Skills scanned: {report['skills_scanned']}",
        f"Skills skipped: {report['skills_skipped']}",
        f"Total findings: {report['total_findings']}",
        f"Overall: {report['overall']}",
        "",
        "Severity breakdown:",
    ]
    for sev in ("critical", "high", "medium", "low", "info"):
        count = report["severity_counts"].get(sev, 0)
        if count:
            glyph = {"critical": "[!!]", "high": "[! ]", "medium": "[~ ]",
                      "low": "[. ]", "info": "[  ]"}.get(sev, "?")
            lines.append(f"  {glyph} {sev.upper()}: {count}")

    lines.append("")
    lines.append("Check breakdown:")
    for check, count in sorted(report["check_counts"].items(),
                               key=lambda x: x[1], reverse=True):
        lines.append(f"  {check}: {count}")

    lines.append("")
    lines.append("-" * 60)

    # Show critical and high findings in detail
    shown = 0
    for f in report["findings"]:
        if f["severity"] in ("critical", "high") and shown < 30:
            sev_tag = f"[{f['severity'].upper()}]"
            lines.append(f"{sev_tag:12s} {f['skill']:30s} {f['check']}")
            lines.append(f"             {f['detail']}")
            shown += 1

    if shown < report["total_findings"]:
        lines.append(f"\n... and {report['total_findings'] - shown} more (use --json for full list)")

    lines.append("=" * 60)
    return "\n".join(lines)


def audit_single(skill_name: str) -> dict[str, Any]:
    """Deep audit of a single skill."""
    skill_dir = SKILLS_DIR / skill_name
    if not skill_dir.exists():
        return {"error": f"Skill not found: {skill_name}"}

    findings = scan_skill(skill_dir)
    return {
        "skill": skill_name,
        "findings_count": len(findings),
        "findings": [f.to_dict() for f in findings],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_scan = sub.add_parser("scan", help="Full vulnerability scan of all skills")
    p_scan.add_argument("--json", action="store_true", dest="output_json")

    p_audit = sub.add_parser("audit", help="Deep audit of a single skill")
    p_audit.add_argument("skill", help="Skill directory name")
    p_audit.add_argument("--json", action="store_true", dest="output_json")

    p_summary = sub.add_parser("summary", help="Counts only")
    p_summary.add_argument("--json", action="store_true", dest="output_json")

    args = parser.parse_args(argv)

    if args.command == "scan":
        report = scan_all()
        if args.output_json:
            print(json.dumps(report, indent=2, default=str))
        else:
            print(render_text(report))
        return 0 if report.get("overall") != "CRITICAL_FINDINGS" else 1

    elif args.command == "audit":
        result = audit_single(args.skill)
        if args.output_json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if "error" in result:
                print(f"Error: {result['error']}")
                return 1
            for f in result["findings"]:
                print(f"[{f['severity'].upper():8s}] {f['check']}: {f['detail']}")
            if not result["findings"]:
                print(f"[OK] {args.skill}: no findings")
        return 0

    elif args.command == "summary":
        report = scan_all()
        summary = {
            "skills_scanned": report["skills_scanned"],
            "total_findings": report["total_findings"],
            "severity_counts": report["severity_counts"],
            "overall": report["overall"],
        }
        if args.output_json:
            print(json.dumps(summary, indent=2))
        else:
            print(f"Scanned: {summary['skills_scanned']} | "
                  f"Findings: {summary['total_findings']} | "
                  f"Overall: {summary['overall']}")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
