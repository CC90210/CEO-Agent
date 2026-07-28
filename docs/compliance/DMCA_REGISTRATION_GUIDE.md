---
description: "SOP for registering a DMCA Designated Agent with the U.S. Copyright Office, and why the Canadian notice-and-notice regime still applies alongside it"
tags: [compliance, legal, dmca, copyright, sop]
last_updated: 2026-07-27
freshness_threshold_days: 365
verified: 2026-07-27
---

# DMCA Designated Agent — Registration SOP

> Related: [[docs/compliance/LEGAL_COMPLIANCE_AUDIT]] · [[brain/APP_REGISTRY]]
> **Owner:** CC. This requires a real name, a real address, and a payment — Bravo cannot complete it.

## Why this matters

Publishing a DMCA policy page does **not** give you safe harbour. Under 17 U.S.C. § 512(c),
a service provider is eligible for protection from copyright liability for user-uploaded
content **only if** it has designated an agent with the U.S. Copyright Office *and* published
that agent's contact information. Miss the registration and you can be liable for content a
user uploaded, even though your policy page says all the right things.

The pages shipped 2026-07-27 (`oasisai.work/dmca`, `nostalgicrequests.com/dmca`) are written
so they are accurate *before* registration — they describe practice, and each carries a
callout saying safe harbour is not yet established. Once the steps below are done, delete
those callouts.

## Who needs to register

Any property that hosts material uploaded at the direction of users:

| Property | UGC surface | Needs registration |
|---|---|---|
| OASIS Command Center | Lead-document dropzone, tenant logo upload, form file fields | **Yes** |
| Nostalgic Requests | Guest song requests and messages | **Yes** |
| PropFlow | Screening-report and document uploads | **Yes** — pending Adon sign-off |
| OASIS AI Platform (marketing) | None | No |

Client-owned apps (Breeze, BreezeAdvance, SunBiz, Blue Rise, Hermes, Arthrisil) each need
their **own** registration under their **own** entity. Do not register them under OASIS.

## Steps

1. **Create an account** at the DMCA Designated Agent Directory:
   <https://dmca.copyright.gov/osp/>
   Use a role address you will keep (`legal@oasisai.work`), not a personal one.

2. **Register the service provider.** The "service provider" is the legal entity —
   *OASIS AI Solutions* — not the product name. List every product name the public might
   know it by as an **alternate name** on the same registration (Command Center, oasisai.work).
   Alternate names are free and are what makes the directory searchable by a complainant.

3. **Name the designated agent.** This can be a role ("Copyright Agent") rather than a
   person, which is preferable — it survives staffing changes. Provide:
   - full physical street address (a PO box alone is not accepted)
   - telephone number
   - email — must match what is published on the site: `dmca@oasisai.work`

4. **Pay the fee.** $6 USD per registration, by card. Nostalgic Requests is a separate
   service provider and needs its own $6 registration with `dmca@nostalgicrequests.com`.

5. **Verify the published contact matches the filing exactly.** A mismatch between the
   directory entry and the site is a common reason safe harbour is challenged. The site
   values live in:
   - `oasis-command-center/lib/legal/constants.ts` → `LEGAL_CONTACTS.dmca`
   - `nostalgic-requests/app/dmca/page.tsx`

6. **Create the mailboxes.** `dmca@oasisai.work` and `dmca@nostalgicrequests.com` must
   actually receive mail before the registration is filed. An unrouted address published as
   a designated agent is worse than none.

7. **Remove the "registration pending" callouts** in `app/dmca/page.tsx` (both apps) and
   the `openGaps` entry in `PRIVACY_NUTRITION_LABEL.json`.

8. **Diarise renewal.** Registrations must be **renewed every three years** or they lapse
   and safe harbour goes with them. Next renewal: three years from the filing date.

## Canada: notice-and-notice still applies

The DMCA is US law. Canada does not have a takedown safe harbour — it has
**notice-and-notice** under ss. 41.25–41.27 of the *Copyright Act*. Obligations differ:

- On receiving a compliant notice you must **forward it to the affected user** and retain
  records for six months (or one year if proceedings start).
- You are **not** required to remove the content on notice alone.
- Failing to forward a compliant notice exposes you to statutory damages of $5,000–$10,000.
- A notice may **not** include a settlement demand or payment request — those are prohibited
  in Canadian notices, and you may refuse to forward one that contains them.

Because OASIS operates from Quebec and serves US users, both regimes apply in parallel. The
shipped policy text covers both; the operational difference is that a Canadian-user notice
gets forwarded, while a US-user notice can trigger removal plus counter-notice.

## Handling a notice — quick runbook

1. Log it. Date received, complainant, material identified.
2. Check the six § 512(c)(3) elements. Incomplete → reply requesting the missing elements;
   do not act on it.
3. Canadian user → forward the notice, retain records, no removal.
4. US user → remove or disable access expeditiously, notify the user, tell them about the
   counter-notice route.
5. Counter-notice received → forward to complainant. Restore after 10–14 business days
   unless they confirm a court filing.
6. Track repeat infringers. A termination policy that is never enforced does not count.
