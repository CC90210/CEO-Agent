# Regression: Assumed Shared Supabase Tenanting for a New Client Product (2026-05-11)

## What went wrong
The initial Sun Biz Agent build treated Sun as a row-level tenant inside CC's existing Agent Command Center and scoped the funding-ops data layer around shared Supabase queries. CC corrected the architecture: Sun Biz Agent is a separate client product, and client operational data should be Turso/libSQL-backed rather than assumed into CC's shared Supabase tenancy model.

## The behavior that must NOT recur
1. When a build involves a new client-facing product, explicitly classify the data boundary before writing tenant-scoped queries: shared-internal app, white-label multi-tenant app, or separate client product.
2. If CC names Turso/libSQL for a client automation, write that correction into repo memory the same turn and mark any Supabase reader as transitional scaffolding, not future architecture.
3. Reuse shell/UI substrate only after separating "shared chrome" from "shared data model" in the plan. Shared sidebar components do NOT imply shared persistence.
4. Update `brain/AGENTS.md` whenever a client agent's ownership/topology changes so future sessions stop booting from stale mental models.
