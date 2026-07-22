# CLEAR S2S Support Call Sheet — "Not Authorized" (SubStatusCode 10003)

**Who to call:** CLEAR Technical Support **1-800-937-8529**
(Account Support 1-800-328-4880 if they punt to the account team.)
Say: *"Our server-to-server (S2S) API integration gets 'Not Authorized',
SubStatusCode 10003, on every request — we need the S2S implementation team."*

## The facts to give them

| Item | Value |
|---|---|
| Company / cert subject | Breeze Advance (CN=Breeze Advance, Brooklyn NY, admin@breezeadvance.com) |
| Client cert serial | `0x44508f5a680912353099637e4102888c` |
| Cert issuer | Thomson Reuters CLEAR S2S Issuing CA (expires **2026-09-15**) |
| Server egress IP | `2.25.159.226` (static VPS) |
| Endpoint called | `POST https://s2s.thomsonreuters.com/api/v2/business/searchResults` |
| Result | HTTP 403 wrapping XML `StatusCode 401 / SubStatusCode 10003 "Not Authorized."` (namespace `http://clear.thomsonreuters.com/api/core/2.0`) |
| Evidence timestamp | 2026-07-22 17:58:25 GMT, CF-Ray `a1f45551daeedc28-EWR` |
| Second endpoint, same result | `POST /api/v2/person/searchResults` → identical 401/10003, 2026-07-22 18:25:49 GMT, CF-Ray `a1f47d782cefefa7-EWR` — so this is **account-level**, not a per-endpoint entitlement issue |
| History | Zero successful API calls ever on this account (cert issued Dec 2024) |
| Auth used | mTLS client cert + HTTP Basic (7-digit numeric username) + PermissiblePurpose GLB=Q / DPPA=3 / VOTER=7 |

Note: the mTLS layer works — an authenticated GET reaches the application
(404), and the 403 above is CLEAR's application XML, not an edge block. The
problem is squarely account/credential/entitlement authorization.

## Questions to ask (in order)

1. **Is this S2S account activated for production?** Credentials and cert were
   issued December 2024 but no call has ever been authorized.
2. **Which endpoints are entitled on the account?** Person Search? Business
   Search? Person/Business Reports? (We know these are licensed separately.)
3. **Are our permissible-use codes approved on the account** — GLB=Q, DPPA=3,
   VOTER=7? Is 10003 what a purpose mismatch returns?
4. **Is the Basic-auth pair we hold the final S2S credentials** (username is
   7 digits, password is 6 chars) — or onboarding/pickup credentials that were
   supposed to be exchanged for production ones?
5. **Does the account require egress-IP registration?** If yes, register
   `2.25.159.226`. (Do NOT buy/route through any proxy — this box has a static
   IP.)
6. **Should we integration-test on `s2s.beta.thomsonreuters.com` first**, and
   does beta need separate beta-issued credentials/cert?
7. Ask them to grant **developer-portal access** (developerportal.thomsonreuters.com,
   CLEAR System-to-System page) so we can pull the official S2S implementation
   guide — request/response schemas (search 2.0 namespace, results-URI flow).

## After the call

Whatever they enable/correct, the next verification is: ONE person_search for
an operator-chosen lead via `clair_report` (or the scratchpad runner). A 2xx
persists the true response schema to `clair_reports.raw_report`; reconcile the
parsers, flip that endpoint's `verified=True`, and the phone-enrichment
fallback is live. Every attempt (success or failure) is already audited in
`clair_reports`.
