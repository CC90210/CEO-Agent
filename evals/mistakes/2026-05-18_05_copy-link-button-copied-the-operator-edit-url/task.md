# Regression: Copy-Link Button Copied the Operator Edit URL (2026-05-18)

## What went wrong
Shipped a "Copy link" button on the `/forms` list page so operators could share a form URL with prospects. The button copied `<origin>/forms/<id>/edit` — the admin-only editor URL — instead of the prospect-facing public URL. CC opened the copied URL in an incognito window and got the dashboard login page. The fix required (a) adding the actual public form route (`/f/<tenant>/<form>`), (b) threading the tenant slug down to FormsListClient, (c) verifying middleware allowlist included `/f/`, (d) verifying layout chrome bypass included `/f/`. A 30-second incognito test before the first claim of "shipped" would have caught it instantly.

## The behavior that must NOT recur
1. **`feedback_test_user_journey_incognito.md` is now the durable rule** — share-link / public-URL features get incognito-tested against production before "done."
2. **`feedback_verification_means_actual_probing.md` codifies the broader pattern** — health endpoints, build status, TypeScript exit codes are adjacent signals, not verification. "Verified" requires HTTP-probing the exact URL the user will hit.
3. **The Copy button now copies the actual public URL** (`<origin>/f/<tenant_slug>/<form_slug>`) and is disabled when the form isn't enabled or the tenant slug fails to resolve.
