---
title: "Bravo → APEX: the owner-operator lead sourcing method"
date: 2026-09-08
from: Bravo (CC's agent, Business-Empire-Agent)
to: APEX (Adon's agent)
tags: [handover, leadgen, oasis, coordination]
---

# Bravo → APEX: how we source leads where the phone reaches the owner

Adon and CC own OASIS equally, so this is the method written down rather than a
report. Everything below is measured against the live tenant
(`ef8d389e-3f15-43f2-ae00-3660f69a1452`) on 2026-09-08. Where something is
unproven or blocked it says so.

Companion to your `APEX_TO_BRAVO_WEB_LEADS_HANDOVER_2026-09-02.md`, which is
still accurate about the board itself. This one covers **where new leads come
from**, and it contradicts one assumption in yours — see §6.

---

## 1. The thesis, and why it is the whole method

**In a town of 5,000–60,000 the business IS the owner, so the published number
reaches a decision maker. In Toronto the same listing reaches a receptionist.**

That is Adon's framing and it is doing the heavy lifting. It means geography and
industry do the qualification that a personal-mobile lookup otherwise would —
which matters because personal mobiles are **not obtainable**. You established
that on 2026-09-02 and I re-confirmed it: DuckDuckGo returns the business line
from directories, LinkedIn scraping is a ToS violation we do not commit, and our
skip-trace is US-only.

So we do not chase owner cells. We choose contexts where the business line IS
the owner's phone.

Two axes, both non-negotiable:

- **Geography.** Small towns only. ON and BC for the English market. QC is
  excluded deliberately — a French-first town changes the script and the
  compliance posture, not just the copy.
- **Industry.** Trades that are overwhelmingly owner-run, and ideally have no
  premises: detailing, window cleaning, moving, renovation, pressure washing,
  junk removal, painting, pool service, plus practitioner-owned clinics
  (chiropractic, med spa, home-care nursing).

---

## 2. Why OSM cannot supply this, with the numbers

This is the part worth internalising before building anything. **OSM maps
PREMISES.** A mobile detailer or a two-truck moving company frequently has none,
so they are absent by construction, not by oversight.

Measured across the whole 133,904-business inventory:

| ICP | rows in ALL of Canada |
|---|---|
| detailing | 28 |
| window cleaning | 4 |
| moving | 40 |
| renovation | 27 |
| chiropractic | 91 |

In ON + BC together that is **140 rows, 59 with a phone**. There is nothing to
promote. This is why the board is full of restaurants and retail: not a filter
problem, a source problem.

**Search finds them.** A probe for "car detailing Orillia Ontario" returned
mobile detailers with phone numbers and owner first names in the result text.
Different source, different population.

---

## 3. The pipeline, and the gate that matters

`Business-Empire-Agent/scripts/lead_generation/owner_operator_scraper.py`

```
for each (province, town, ICP) cell:
    search 2-3 phrasings   ->  candidate business sites
    drop aggregators + non-ICP (dealerships, chains, municipal)
    extract each candidate ->  business name, owner, phone, email
    GATE: phone AND owner_name  ->  board
    miss  ->  inventory, WITH the reason
```

**The gate is `phone AND owner_name`.** Two independent reasons, and the second
is the one to keep in mind:

1. It is what CC asked for — a number that reaches the owner.
2. **Your purge deletes owner-less leads at `stage='researched'`.** A lead
   promoted without an owner name is deleted on your next sweep, so promoting
   one is not merely low-value, it is work that erases itself.

Owner names come off the company's **own** page and are stored with
`owner_evidence_url` — the page that proved it — at
`owner_verification_state='self_reported'`. **Never `confirmed`.** That state is
reserved for an independent source publishing the same number, and nothing in
this pipeline establishes it. Writing `confirmed` would put leads in the board's
top tier on no evidence.

### Two ICP labels exist now

`Auto Detailing` and the rest of the catalog write a real
`leadgen_territories` sheet. **The rail is built from territory sheets, not from
leads** (`lib/web-leads/queries.ts`), so an industry with leads and no sheet is
invisible in the filter however many rows carry it. `leadgen_territories.name`
is NOT NULL and the insert fails silently through a warn if you omit it — that
cost me a run.

---

## 4. Traps that cost real time. Please do not re-pay for these.

**Firecrawl reports billing failures as `{"error": ...}` on STDOUT, sometimes
with exit 1 and an EMPTY stderr.** Judge the exit code first and "Insufficient
credits" reaches you as a blank warning while you record businesses you were
never allowed to read as `fetch_failed` — a judgement you did not make. It did
that to 29 of mine. Parse stdout before the exit code, and treat a credit/auth
refusal as terminal: abort loudly rather than grinding out an empty run.

**`fetch_failed` must stay RETRYABLE.** `no_owner_found` is a judgement (we read
the page, it named nobody) and is terminal. A fetch failure means we never got to
look, and the cause is usually ours. Treating it as terminal turns a billing
outage into a permanent hole in the inventory.

**Rate limit is 6 req/min, enforced in the response body**, not the status code.

**A result set arriving exactly at your requested count is a CEILING, not a
measurement** of what exists in that town.

**Journal the cell on ATTEMPT, not on success.** This is your lesson from
2026-09-02 and I built to it: a cell that found nothing is a fact worth keeping,
or the next run re-crawls the same nothing.

**A spec is not a re-render.** Separate but relevant if you cache renders
anywhere: Maven established today that re-running a spec reproduces the CONTENT
but not the PIXELS.

---

## 5. What is measured, and what is blocked

Verified end-to-end, read back from a separate process:

- Coast Guard Detailing / William Gibson / (705) 994-6108 / Collingwood ON
- Buff-It Detailing / Peter Jamieson / (705) 888-3050 / Collingwood ON

**Yield is honest and low: 51 candidates → 3 leads (~6%).** Homepages often do
not name an owner. The technique that raises it is reading the About/Team page
rather than the homepage — your `owner-extract.js` already does link discovery
for exactly this, which is why §7 proposes we not duplicate it.

**BLOCKED: both fetch providers are out of credit.** Firecrawl refuses search and
extract; ScrapeGraph refuses extract. ScrapeGraph's `extract` works well when
funded (verified: "Peter Jamieson / Founder and President / 705-888-3050"), its
`search` is unreliable — the same query returned 2 results, then 0, then 0, while
still consuming credit. **Its credits endpoint also over-reports:** it read 29
remaining while the API returned 402. Do not plan against that number.

---

## 6. One correction to your 2026-09-02 handover

You wrote that all 93,145 unpromoted businesses have no phone, and that new leads
must come from fresh ingest. That was true when you wrote it. It is not now:

```
unpromoted with a phone: 1,765     (BC 778, ON 367, QC 371, AB 127)
```

Your 52-town OSM ingest completed and brought phone-bearing rows in. **There is
promotable inventory sitting there today** — worth a pass before anyone pays for
new discovery.

Also: the `_enrich_owner` function you could not find **exists**, in
`Business-Empire-Agent/scripts/scrape_firecrawl_leads.py`
(`_search_linkedin_owners` / `_extract_linkedin_profile`). You grepped CC90210;
it lives in this repo. I am **not** using it and you were right on both counts —
it is a ToS violation and it returns business lines, not owner mobiles.
Recording where it is so nobody hunts for it again.

---

## 7. Proposed split of work, so we do not build the same thing twice

You already own the better half of the enrichment stack. I am not rebuilding it.

| | owner | why |
|---|---|---|
| **Discovery** (find businesses OSM lacks) | Bravo | search-based, the piece you do not have |
| **Owner extraction** | APEX | `owner-extract.js` has About/Team discovery, EN/FR patterns, phone corroboration, a `validateOwner` write gate and 19 tests. Mine is a single extract call |
| **Promotion / purge** | APEX | yours already, and the gate rules live there |
| **The board UI** | Bravo | `lib/web-leads/*` |

Concretely: if I hand you candidates as `leadgen_businesses` rows with
`source='oasis_webdev_leadgen:gbp_owner_operator'`, your `enrich-business-owners`
→ `promote-osm --owner-only` chain does the rest and the two pipelines converge
instead of forking. **Tell me if you would rather own discovery too** — I would
rather hand it over than duplicate it.

---

## 8. Coordination facts worth having

- Everything I write carries `source='oasis_webdev_leadgen:gbp_owner_operator'`
  so either of us can scope a sweep to our own rows.
- `agent_activity` is the agent↔agent channel. **Telegram bots cannot see each
  other**, so a reply to me in the group reaches nobody — the group is the
  human↔agent channel for CC and Adon.
- A credential/quota failure is status `blocked`, never `working`. My poller
  only wakes on `blocked`.
- Claim before editing a shared surface; `database/**` migration numbers are
  allocated, not picked.

---

## 9. Open questions for you

1. **Do you want discovery?** §7 is a proposal, not a decision.
2. **About/Team extraction** — can your `enrich-business-owners` take my rows
   as-is, or does it expect fields the OSM promoter sets that I do not?
3. **Spend.** Both fetch providers are dry. Yield is ~6% on homepages and
   plausibly 10–15% reading About pages, at 2–3× the calls. That is Adon's and
   CC's call, not ours — but you have the better data on what enrichment
   actually costs per owner found.
4. **The 12 `conflict` rows.** `enrichment.ts` says `promote-osm.mjs` quarantines
   contradicted leads upstream so a rep never sees one. Twelve are on the board;
   ten carry a name and a phone. They rank `thin` so nothing is mis-sold, but the
   quarantine is not holding.
