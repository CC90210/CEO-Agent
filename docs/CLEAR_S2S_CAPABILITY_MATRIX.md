# Thomson Reuters CLEAR S2S — Capability Matrix & Integration Map

> Scope note: this documents **Thomson Reuters CLEAR** (the investigative /
> public-records platform whose credentials live in `.env.agents`). It is **not**
> CLEAR Secure / clearme.com (airport identity verification) — an unaffiliated
> company with a different API. Confirmed via the vendor's own
> [affiliation FAQ](https://www.clearme.com/support/is-clear-affiliated-with-thomson-reuters-clear).

> ⚠️ **2026-07-22 correction:** the "person search VERIFIED live" claim below was
> wrong. What was exercised on 2026-07-21 was a **TLS handshake only** — and the
> endpoint is Cloudflare-fronted, which completes handshakes for anyone, so the
> handshake proved nothing about the account. **No CLEAR request has ever
> returned 2xx.** The first real request (business_search, 2026-07-22) returned
> HTTP 403; diagnosis in progress (see `docs/CLEAR_SUPPORT_CALLSHEET.md`). All
> endpoints are now marked unverified and gated until a live round-trip.

## 1. Transport & authentication (mTLS layer verified; app layer NOT)

| Aspect | Value | Source |
|---|---|---|
| Base URL (prod) | `https://s2s.thomsonreuters.com` | Cloudflare-fronted; mTLS accepted (authenticated GET / reached the app, 404, 2026-07-22) |
| Base URL (beta/test) | `https://s2s.beta.thomsonreuters.com` | the real test host (DNS + mTLS CertificateRequest confirmed 2026-07-22). The previously listed `s2scert.thomsonreuters.com` is NXDOMAIN — it never existed |
| Client auth | **Mutual TLS** — PKCS#12 client cert (`CLEAR_PFX_CERTIFICATE` + `CLEAR_PASSPHRASE`), issued by "Thomson Reuters CLEAR S2S Issuing CA" to Breeze Advance, valid to **2026-09-15** | cert decoded + handshake |
| User auth | HTTP Basic (`CLEAR_USERNAME` / `CLEAR_PASSWORD`) on top of mTLS | documented |
| Format | REST + XML (`Content-Type: application/xml`) | confirmed on person search |
| Permissible use | `PermissiblePurpose` block on every request — `GLB` (`CLEAR_GLB`), `DPPA` (`CLEAR_DPPA`), `VOTER` (`CLEAR_VOTER`). Legally required; a query without it is rejected | documented + built |

**Rate/retry policy (ours, in `clear_client.clear_post`):** 3 attempts, exponential
backoff (1s base, 8s cap, 25% jitter). Retries transport faults + 429/5xx only —
**never a 4xx**, because a 4xx means the request or the permissible use was
rejected and a repeat just bills again for the same refusal. CLEAR does not
publish a numeric rate limit for S2S; the manual-only trigger keeps volume low
by construction.

## 2. Enrichment vectors (capability matrix)

CLEAR S2S follows a **two-phase pattern**: a *Search* returns candidate entities
with IDs; a *Report* takes an entity ID and returns full detail. Every vector
below shares the transport, auth, permissible-use, billing, and audit behaviour
above — only the criteria and payload shape differ.

| Vector | Endpoint | Wired | Verified | Serves |
|---|---|---|:---:|---|
| **Person search** | `/api/v2/person/searchResults` | ✅ | ⚠ doc-only | Locate the owner + phones/addresses. **The phone-enrichment fallback.** (Previously mislabeled "✅ live" on handshake-only evidence.) |
| **Business search** | `/api/v2/business/searchResults` | ✅ | ⚠ doc-only | Locate the merchant business + phones, addresses, principals/registered agents. High value — the merchant *is* a business. |
| **Person report** | `/api/v2/person/reports` | ✅ | ⚠ doc-only | Full detail for a person entity id: complete phone/address history, relatives. |
| **Business report** | `/api/v2/business/reports` | ✅ | ⚠ doc-only | Full detail for a business entity id: filings, principals, contact history. |
| Phone (reverse) | `/api/v2/phone/searchResults` | ▫ not wired | — | Identify the owner of a known number. Low value here (we *seek* numbers). |
| Court records | `/api/v2/court/searchResults` | ▫ not wired | — | Litigation history — an underwriting **risk** signal. Belongs to the background-check consumer, not phone enrichment. |
| Bankruptcy / liens / judgments / UCC | `/api/v2/{bankruptcy,lien,judgment,ucc}/…` | ▫ not wired | — | Financial-distress signals for underwriting risk. |
| Vehicle / DMV, criminal, ID Confirm | (various) | ▫ not wired | — | KYC / risk; permissible-use sensitive. Add only with a confirmed compliance basis. |

**✅ live** = a real 2xx round-trip observed (currently: none).
**⚠ doc-only** = built from TR's published S2S docs + the two-phase pattern; XML
**not yet confirmed against a live response**, so gated (see §4). Note real
integrator evidence (LSEG thread 48419) shows the wire uses XML namespace
`http://clear.thomsonreuters.com/api/search/2.0` — expect our request builders
to need a namespace once past auth.
**▫ not wired** = available on the contract; add via the framework (§5) once the
schema is confirmed. Deliberately *not* fabricated — a made-up schema presented
as production-ready would be worse than absent.

## 3. File structure

```
ceo-agent/scripts/integrations/
  clear_client.py            transport core (clear_post) + VERIFIED person search
                             + config, PKCS#12→PEM, error taxonomy, normalized ClearResult
  clear_endpoints.py         EndpointSpec framework + CAPABILITIES registry
                             + BusinessQuery, normalized ClearEntity, run_endpoint()
  clear_report_service.py    run_clear_report() — dispatch by report_type,
                             persist to clair_reports, one audit row per attempt
ceo-agent/bravo_cli/
  bridge_tools.py            skills: clair_report (run), clair_capabilities (discover)
oasis-command-center/
  database/120_clair_reports.sql        table (+ report_type, entity_id)
  app/api/leads/[id]/clair-report/route.ts   manual trigger (VPS bridge proxy)
  lib/clair/eligibility.ts                    strict-fallback rule (shared)
  components/leads/ClairReportPanel.tsx       isolated report drawer
```

## 4. Skills (agent-invokable)

| Skill (bridge tool) | Purpose | Billable? |
|---|---|---|
| `clair_capabilities` | Enumerate the catalog + `configured` + `verified` flags. Discovery. | No |
| `clair_report` | Run one endpoint for a lead (`report_type` default `person_search`; `entity_id` for reports) and persist it. **Manual, operator-initiated only.** | **Yes** |

**Unverified-endpoint gate:** `run_endpoint` refuses any `verified=False` spec
unless `CLEAR_ALLOW_UNVERIFIED=1`, so a doc-only endpoint cannot silently bill a
regulated prod query. The raw response is persisted verbatim regardless, so the
first real call captures the true schema for reconciliation.

## 5. Adding an endpoint (extension recipe)

1. Write `_build_<x>_xml(query, cfg)` and `_parse_<x>_entities(body)` in
   `clear_endpoints.py` (confine ALL wire-format specifics to these two).
2. Register an `EndpointSpec` in `CAPABILITIES` with `verified=False`.
3. Run it once with `CLEAR_ALLOW_UNVERIFIED=1`, read `raw_report`, reconcile the
   parser against the real payload, then flip `verified=True`.

Nothing else changes — transport, auth, persistence, audit, and the skills are
already generic.

## 6. Compliance invariants (do not remove)

- **Manual only.** No cron, no retry loop, no speculative call. Every query is
  attributable to a signed-in operator (`requested_by` / `requested_by_email` on
  the row) because each asserts a permissible use.
- **Audit every attempt.** Failures get a row too — they still consumed a
  permissible-use assertion.
- **Data separation.** Reports live in `clair_reports`, never merged into
  `tenant_records`. `raw_report` is service-role only.
- **Cert expiry:** 2026-09-15. Renew before then or every call 401s.
