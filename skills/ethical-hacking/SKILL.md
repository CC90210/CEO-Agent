---
name: ethical-hacking
description: Authorized offensive security — reconnaissance, vulnerability assessment, and web/network pentest methodology for CC's own infrastructure, authorized client engagements, and legal bug bounty programs. Defensive intent only. Never operates without written authorization.
triggers: [pentest, penetration test, ethical hacking, vulnerability assessment, security audit, bug bounty, offensive security, recon, osint, red team]
tier: strategic
dependencies: [security-protocol, security-reviewer, firecrawl, playwright-mcp, systematic-debugging]
tags: [security, offensive, authorized, compliance]
last_updated: 2026-05-21
---

# ETHICAL HACKING — Authorized Offensive Security

> Find vulnerabilities before criminals do — on systems you are authorized to test. Zero exceptions.

## Prime Directive

**NO AUTHORIZATION = NO TESTING.** Before any active scanning, input fuzzing, or exploitation:

1. Written scope of work (email is fine — paper trail required)
2. Target list explicitly enumerated (IPs, domains, apps, no wildcards)
3. Time window defined
4. Out-of-scope list (production data, customer PII, third-party services)
5. Contact for emergencies
6. CC's signature on authorization letter if client engagement

**If any of the six are missing, STOP and ask CC.** Unauthorized testing is a federal crime (CFAA in US, Criminal Code s.342.1 in Canada). Bravo refuses to execute offensive techniques without authorization, regardless of who asks.

## Scope of This Skill

**IN SCOPE:**
- CC's own infrastructure (OASIS AI, PropFlow, Nostalgic, cc-funnel, BEA)
- Paid client engagements with SOW
- Public bug bounty programs (HackerOne, Bugcrowd, Intigriti) — only targets listed in scope
- CTF challenges
- Controlled lab environments (DVWA, HackTheBox, TryHackMe)
- Defensive research: understanding attacker TTPs to improve OASIS defenses

**OUT OF SCOPE (Bravo will refuse):**
- Any target without written authorization
- DoS / DDoS / resource exhaustion attacks
- Social engineering of real individuals without consent
- Data exfiltration beyond proof-of-concept (screenshot one record, not a full dump)
- Persistence mechanisms / backdoors
- Pivoting beyond agreed boundaries
- Anything that touches third-party systems not in scope

## Methodology (PTES + OWASP WSTG Hybrid)

### Phase 1 — Pre-Engagement
- Confirm authorization, scope, rules of engagement
- Set up isolated testing environment (separate VM, no credentials mixing)
- Communication channel to client (encrypted, daily check-ins)
- Emergency stop protocol (one Telegram command halts all automation)

### Phase 2 — Passive Reconnaissance
No packets touch the target. Pure OSINT:
- **Domain enum:** `firecrawl_tool.py scrape <target>` + public DNS lookups
- **Certificate transparency:** crt.sh queries (manual)
- **GitHub exposure:** search for leaked secrets, config files, internal hostnames
- **LinkedIn / job postings:** tech stack fingerprinting
- **Wayback Machine:** historical endpoint discovery
- **Google dorking:** `site:target.com filetype:env` style queries
- **Shodan / Censys:** read-only, authorized accounts only

### Phase 3 — Active Scanning
Only after Phase 1 authorization confirms active testing is allowed:
- **Port scanning:** nmap (install separately — not in current shed)
- **Service enumeration:** version detection, banner grabbing
- **Web discovery:** `ffuf` / `gobuster` for directory brute-forcing within scope
- **Playwright MCP:** authenticated app crawling, form enumeration

### Phase 4 — Vulnerability Analysis
Map findings to OWASP Top 10 / CWE / CVE:
- **Injection:** SQL, NoSQL, command, LDAP, XPath
- **Broken auth:** session fixation, weak tokens, credential stuffing resistance
- **Sensitive data exposure:** TLS config, storage, in-transit
- **XXE, XSS, CSRF, SSRF:** classic web vulns
- **Insecure deserialization**
- **Known vulnerable components:** npm audit, pip-audit, OS CVEs
- **Logging/monitoring gaps:** can the defender see the attack?

### Phase 5 — Exploitation (Proof of Concept Only)
- One vulnerability at a time, smallest possible impact
- Screenshot or single-record retrieval to prove — never dump databases
- Immediate rollback if any collateral effect observed
- **NEVER escalate privileges beyond what's needed to prove the finding**

### Phase 6 — Reporting
Deliverable structure (use `scripts/proposal_generator.py` as template base):
1. **Executive summary** (non-technical, risk in business terms)
2. **Findings by severity** (CVSS 3.1 scoring: critical / high / medium / low / info)
3. **Each finding:** title, CWE, affected asset, reproduction steps, evidence, business impact, remediation
4. **Remediation roadmap** (prioritized, with effort estimates)
5. **Appendix:** raw tool output, methodology notes, retest criteria

### Phase 7 — Remediation Validation
- Client fixes findings
- Retest scope-limited to remediated items
- Sign-off letter

## CVSS 3.1 Quick Reference

| Severity | Score | Action |
|---|---|---|
| Critical | 9.0-10.0 | Immediate — call CC, escalate within 24h |
| High | 7.0-8.9 | Fix within 1 week |
| Medium | 4.0-6.9 | Fix within 1 month |
| Low | 0.1-3.9 | Fix at convenience |
| Info | 0.0 | Awareness only |

## Decision Matrix — Which Skill Fires?

| Situation | Skill |
|---|---|
| Authorized offensive test of real target | **ethical-hacking** (this skill) |
| Reviewing CC's own code before merge | `security-reviewer` agent |
| Hardening config / secrets / credentials | `security-protocol` |
| OWASP Top 10 code audit | `security-reviewer` agent |
| CASL / privacy compliance review | `compliance` skill (if exists) or manual |

## Tooling in Bravo's Current Shed

**Available today:**
- `firecrawl_tool.py` — passive recon, OSINT, content scraping
- Playwright MCP — authenticated web testing, form fuzzing, screenshot evidence
- `supabase_tool.py` — verify RLS policies on CC's own projects
- GitHub MCP — search for secret leaks in repos
- Python — custom fuzzers, HTTP clients

**Missing / install on demand:**
- `nmap` — network scanning (install via chocolatey / brew when scope demands)
- `ffuf` / `gobuster` — web content discovery
- `sqlmap` — SQL injection proof-of-concept (use with extreme care, dry-run flags)
- `burpsuite-community` — intercepting proxy for manual testing

**Never install on BEA machine:**
- Metasploit (too broad, crosses into weaponization)
- Cobalt Strike / Sliver / C2 frameworks (offensive operator tooling, not pentest)

## Business Angle — New Revenue Stream

CC is exploring cybersecurity. Positioning for OASIS AI:

- **"Security Posture Assessment"** — $2,500 flat fee, 5-day engagement, passive recon + Top 10 review + written report. Low-risk entry offer.
- **"Full Web Pentest"** — $5,000-10,000, 10-day engagement, full methodology above.
- **Retainer:** $500/mo monitoring + quarterly retest + incident response on call.
- **Target market:** CC's existing agency clients first (HVAC, wellness) — low competition, high trust.
- **Certification path:** eJPT ($200) → PNPT ($400) → OSCP ($1,600). eJPT is enough to charge for assessments.

## From Offense to Defense — Secure-by-Default Coding

The most valuable output of understanding offensive security is that every line of code you ship afterward is safer. This section is why CC wanted ethical hacking research in the first place: **so Bravo writes software that attackers can't easily break.**

### The Secure Defaults Checklist (apply to EVERY app Bravo builds)

**Authentication & sessions:**
- [ ] Passwords hashed with argon2id (not bcrypt, not SHA-anything)
- [ ] Session tokens cryptographically random, 256 bits minimum, httpOnly + secure + sameSite=strict cookies
- [ ] Session fixation prevented (rotate token on login)
- [ ] MFA available, even if not forced
- [ ] Rate limiting on auth endpoints (5 attempts / 15 min)
- [ ] Password reset uses single-use, expiring tokens (not email as proof)

**Input validation:**
- [ ] All user input validated at the server boundary with explicit allowlists (Zod, Pydantic, Joi)
- [ ] Never trust `req.body`, query params, headers, or cookies as authoritative
- [ ] Parameterized queries for SQL — never string interpolation
- [ ] HTML output escaped by default (React does this; raw `dangerouslySetInnerHTML` is banned without review)
- [ ] File uploads: content-type allowlist, size limits, separate storage bucket, no execution permissions

**Authorization:**
- [ ] Supabase RLS policies on EVERY table — no exceptions for "internal" tables
- [ ] Authorization checked at every request, not just at login
- [ ] Cross-tenant isolation verified (can user A read user B's data? Test it)
- [ ] Admin actions require re-authentication

**Secrets & config:**
- [ ] Zero hardcoded credentials in code (CLAUDE.md Rule 3 / security-protocol)
- [ ] `.env.agents` or equivalent gitignored
- [ ] Secrets rotated on any suspected exposure — see `skills/security-protocol/SKILL.md`
- [ ] API keys scoped to minimum permissions needed

**Transport & storage:**
- [ ] TLS 1.3 only, HSTS enabled, no mixed content
- [ ] PII encrypted at rest where possible
- [ ] Logs scrubbed of tokens, passwords, session IDs before writing
- [ ] Backups encrypted and tested for restore

**Supply chain:**
- [ ] `npm audit` / `pip-audit` run before ship, fail the build on critical findings
- [ ] Dependencies pinned to exact versions in lockfiles, lockfiles committed
- [ ] No `latest` tags in production Dockerfiles
- [ ] Review transitive dependencies for known-bad packages periodically

**Observability:**
- [ ] Security-relevant events logged (login success/fail, permission denied, rate-limit hit)
- [ ] Logs centralized, not just in `tmp/`
- [ ] Alerts on unusual patterns (spike in 401s, new IP geo, mass downloads)

### The Threat Model Reflex

Before shipping any new feature, Bravo asks five questions in order:

1. **What am I trusting?** (user input, third-party API, another service, the database)
2. **What happens if that trust is wrong?** (what breaks, what leaks, what escalates)
3. **Who benefits from breaking it?** (drive-by scanner, competitor, insider, state actor)
4. **What's my cheapest mitigation?** (validation, rate limit, auth check, encryption)
5. **How would I detect an attack against this code?** (logs, metrics, alerts)

If any of the five answers is "I don't know," the feature is not ready to ship.

### Offense-Informed Code Review Checklist

When reviewing CC's code (or any app in the registry), run through:

- **Every user-input path** — can I inject, overflow, or traverse?
- **Every auth check** — can I skip it with a crafted header, token, or cookie?
- **Every DB query** — parameterized? RLS verified?
- **Every external API call** — timeout, retry, error handling, rate limit?
- **Every file operation** — path traversal, symlink, race condition?
- **Every deserialization** — untrusted source? Safe parser?
- **Every "TODO" in security code** — assume it's still TODO in production

### Using This to Charge More

When CC pitches OASIS AI retainers against lower-cost competitors, the secure-by-default stack is a differentiator:

> "Most agencies ship you a working app. I ship you a working app that passed my own penetration test. Same price."

That's a legitimate competitive edge, not a marketing line. It's true because Bravo actually runs the checklist.

## Anti-Patterns

- Running tools without reading what they do
- "Just a quick scan" of anything without written scope
- Keeping exploit artifacts on disk after engagement ends
- Using same credentials across test and production systems
- Reporting findings to anyone except the contracted client
- Telling CC "it's probably fine" without verification
- Skipping the retest phase

## Escalation Protocol

- **Found critical in the wild (unauthorized exposure of third party):** STOP, document, report to target's security team via coordinated disclosure channel. Never exploit. Tell CC immediately.
- **Client asks to expand scope mid-test:** Pause, get it in writing, resume.
- **Unclear if a target is in scope:** Treat as out of scope until clarified.

## Learning Path (CC Personal Development)

1. **Week 1-2:** TryHackMe "Complete Beginner" path
2. **Week 3-4:** OWASP Juice Shop (complete all challenges)
3. **Week 5-6:** HackTheBox Starting Point
4. **Week 7-8:** eJPT cert (Elearnsecurity Junior Penetration Tester)
5. **Ongoing:** Bug bounty on HackerOne (public programs only, start with disclosed reports)

Log progress in `memory/cybersecurity_learning.md` (create on first session).

## Obsidian Links
- [[skills/security-protocol/SKILL.md]]
- `.claude/agents/security-reviewer.md` *(security-reviewer is an agent, not a skill — invoke via Task tool with subagent_type:"security-reviewer")*
- [[brain/RISK_REGISTER]]
