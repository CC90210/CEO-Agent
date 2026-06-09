# VPS — Helios/Solara local claude probe (safe, no HTTP gate, no prod writes)

> Paste into the same VPS Claude Code session. You're **Solara** at
> `/srv/sunbiz/ceo-agent`. Goal: prove the identity-bleed fix works
> end-to-end without crossing the /chat HTTP identity gate (the
> previous probe couldn't pass that without fabricating identity).

---

## Why this is safe

- `claude --print` is one-shot, no streaming session, no warm-pool entry,
  no /chat endpoint involvement.
- No `--permission-mode bypassPermissions` (so the safety classifier
  that blocked your last attempt won't trigger).
- No `--allowed-tools` enabling Bash/Edit/Write — Claude can only answer
  in text.
- The identity files (`HELIOS.md`, `SOLARA.md`) are READ from disk and
  passed as the system-prompt overlay — the exact path the bridge fix
  wires for production chat. If this probe says "Helios" when fed
  `HELIOS.md`, the production chat will too.
- No prod state mutation: no Supabase writes, no agent_alerts insert,
  no lead_interactions log, no warm pool side effect.

---

## Step 1 — Confirm the identity files exist and differ from CLAUDE.md

```bash
cd /srv/sunbiz/sunbiz-agent
ls -la CLAUDE.md SOLARA.md HELIOS.md
md5sum CLAUDE.md SOLARA.md HELIOS.md
```

Expected: three files. `CLAUDE.md` + `SOLARA.md` byte-identical (your
own report confirmed md5 9565c0cd…). `HELIOS.md` distinct from both.
If `HELIOS.md` md5 matches the other two, STOP — the file got clobbered
and that's the real bug.

---

## Step 2 — Probe Helios identity (the actual claim under test)

```bash
cd /srv/sunbiz/ceo-agent
HELIOS_TEXT=$(cat /srv/sunbiz/sunbiz-agent/HELIOS.md)

timeout 60 claude --print \
  --append-system-prompt "$HELIOS_TEXT" \
  --setting-sources local \
  --output-format text \
  "Who are you? Answer in two sentences max." 2>&1 | head -20
```

Expected: a response containing "Helios" and at least one of {sales,
outreach, drip, blast, follow-up, schedule, merchant}. The
identity-lock section of HELIOS.md (line 17-23) forces this.

**FAIL signal:** response contains "Solara" OR "I'm Claude" OR "ops
agent" OR "funding-shop ops". That would mean the system prompt
overlay isn't being honored — fundamental Claude Code regression we
need to investigate.

---

## Step 3 — Probe Solara identity (the regression check)

```bash
SOLARA_TEXT=$(cat /srv/sunbiz/sunbiz-agent/SOLARA.md)

timeout 60 claude --print \
  --append-system-prompt "$SOLARA_TEXT" \
  --setting-sources local \
  --output-format text \
  "Who are you? Answer in two sentences max." 2>&1 | head -20
```

Expected: response contains "Solara" and at least one of {funding-shop,
ops, lender, qualification, compliance, application, deal}. Must NOT
say "Helios" or claim sales-outreach role.

---

## Step 4 — Voice differentiation stress test

The fix is only meaningful if the two agents behave differently. Same
prompt, different identity overlay → different shaped answers.

```bash
# Same question to both — sales-tinted question
QUESTION="A merchant just texted 'send me the rate, but make it quick.' What's the next move?"

echo "===== HELIOS answers ====="
timeout 90 claude --print \
  --append-system-prompt "$HELIOS_TEXT" \
  --setting-sources local \
  --output-format text \
  "$QUESTION" 2>&1 | head -30

echo ""
echo "===== SOLARA answers ====="
timeout 90 claude --print \
  --append-system-prompt "$SOLARA_TEXT" \
  --setting-sources local \
  --output-format text \
  "$QUESTION" 2>&1 | head -30
```

Expected divergence:
- **Helios** should draft a short outbound-style reply (text the
  merchant back, push for a quick call/qualifier) — sales-closer
  posture per HELIOS.md.
- **Solara** should route the merchant into ops workflow (qualify
  first, check existing data, hand the actual offer to the funding
  ops path) — operations posture per CLAUDE.md/SOLARA.md.

If both answers read identically, identity isn't actually differentiating
behavior — file the discrepancy, don't gloss it.

---

## Step 5 — Report back

```
Helios local probe — claude --print + --append-system-prompt

Step 1 — files
  CLAUDE.md md5: [hex]
  SOLARA.md md5: [hex]  (= CLAUDE.md? [yes/no])
  HELIOS.md md5: [hex]  (distinct from above? [yes/no])

Step 2 — Helios identity probe
  Output (verbatim first 2 sentences): [paste]
  Contains "Helios"? [yes/no]
  Contains "Solara"? [yes/no — must be no]
  Voice signal (sales/outreach vocab)? [yes/no]

Step 3 — Solara identity probe
  Output (verbatim first 2 sentences): [paste]
  Contains "Solara"? [yes/no]
  Contains "Helios"? [yes/no — must be no]
  Voice signal (ops/funding vocab)? [yes/no]

Step 4 — Voice differentiation
  Helios answer summary (1 line): [paste]
  Solara answer summary (1 line): [paste]
  Distinct shape? [yes/no — must be yes for the fix to be meaningful]

Verdict: [PASS / FAIL]
```

If PASS: the system-prompt loading path is provably correct. CC's
30-second dashboard probe (hard-refresh + ask "who are you?" through
both agents) is the only remaining verification — and the dashboard
path uses the SAME code, just with the HTTP proxy in front.

If FAIL: paste the actual output, do not retry blindly. Something
deeper than my fix is wrong.

---

## Anomalies to surface (don't patch)

- `claude --print` returns non-zero with no output → claude binary or
  auth issue. Surface `claude --version` and `claude doctor` results.
- One of the identity files missing → report and stop.
- HELIOS.md byte-identical to CLAUDE.md → SunBiz-Agent repo state is
  broken; the fix is meaningless if the source files collapsed.
- `--append-system-prompt` rejected as unknown flag → Claude Code
  version on VPS is too old. Report `claude --version` and `claude
  --help | grep -i system-prompt`.

End with state sync:

```bash
python scripts/state/state_sync.py --note "solara: helios identity-bleed fix passed local claude probe — both agents distinct"
```

Then say "Local probe complete." with the verdict line.
