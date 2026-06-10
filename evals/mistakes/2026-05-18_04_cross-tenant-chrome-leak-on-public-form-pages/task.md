# Regression: Cross-Tenant Chrome Leak on Public Form Pages (2026-05-18)

## What went wrong
The new `/f/<tenant>/<form>` route correctly rendered the form, but it rendered INSIDE the operator dashboard's root layout — meaning prospects opening a SunBiz public application form saw the full SunBiz operator sidebar (Dashboard, Agents, Leads, Applications…) plus the operator footer plus the "POWERED BY OASIS AI" branding. The layout's `isFullBleed` check listed `/login`, `/onboarding`, `/welcome` etc. as chrome-bypass routes — but never `/f/`. Bug shipped at the same time the route was created and went unnoticed in two earlier "ready to ship" claims. CC caught it via screenshot.

## The behavior that must NOT recur
1. **`feedback_public_routes_two_layer_gate.md` added to auto-memory** — codifies that new public routes are a two-file change minimum: `middleware.ts` PUBLIC_PATH_PREFIXES + `app/layout.tsx` FULL_BLEED_PREFIXES.
2. **`feedback_test_user_journey_incognito.md` added** — share-link / public-URL features must be incognito-tested against production before "done."
3. **Layout refactored** — `isFullBleed` is now a `FULL_BLEED_PREFIXES` array with `.some()`, matching the pattern middleware uses. Lower friction for adding a new entry.
4. **`feedback_tenant_chrome_bleed_check.md` added** — separate rule for "any path rendering Tenant X's chrome to a session belonging to Tenant Y needs a page-level access gate" (`requireTenantPreviewAccess`).
