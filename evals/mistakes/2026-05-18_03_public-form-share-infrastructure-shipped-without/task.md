# Regression: Public-Form Share Infrastructure Shipped Without Adversarial Review — 9 Bugs in 2 Codex Passes (2026-05-18)

## What went wrong
Shipped the new public form-share flow (anonymous `/f/<tenant>/<form>` route, server-side lead creation on first submit, Supabase Storage uploads, tenant brand logo, `read_only` role enforcement) and called it "production ready" twice. Codex adversarial pass 1 found 5 real bugs in the same diff: (1) HIGH — `anonymous_init` bypassed the rate limiter because the existing bucket keyed on `lead_id` which is freshly minted per anonymous request, so every bot request got its own bucket; (2) HIGH — `inline_base64` blobs accepted against any payload key with attacker-controlled MIME, no form-schema validation; (3) MEDIUM — form lookup by `slug` alone allowed multi-tenant collision + tenant enumeration via 404 diff; (4) MEDIUM — signed-URL minter trusted mutable `storage_path` (confused-deputy via 

## The behavior that must NOT recur
1. **`feedback_adversarial_review_before_done.md` added to auto-memory** — codifies "unauthenticated public-facing surface = Codex adversarial review before declaring done, two passes minimum."
2. **`feedback_security_must_be_server_side.md` added** — prompt-based role enforcement is documented as advisory only; server-side gates in `lib/role-gates.ts` are the authoritative boundary.
3. **`lib/role-gates.ts` ships as the canonical role-deny single source.** Both the cloud-tool palette filter and the marker-action dispatcher consume from it.
4. **`database/057_lead_documents_storage_path_check.sql` ships a CHECK constraint** forcing `storage_path LIKE tenant_id::text || '/%'`. Defense-in-depth at the DB layer.
5. **Shop-out + signed-URL minter both audit the prefix at the app layer too.** B
