---
name: create-prd
description: Generate a comprehensive 15-section Product Requirements Document for client projects. Includes research, user stories, technical architecture, and AI effort compression table.
user-invocable: true
---

# /create-prd — Product Requirements Document

## Steps

1. Ask CC for the project name, client, and high-level requirements.

2. Research the client's industry and competitors:
   - Use OpenCLI: `opencli twitter search "<industry>" --json`
   - Use Playwright for competitor website analysis

3. Generate a 15-section PRD:
   - **1. Executive Summary** — 2-3 sentences on the product vision
   - **2. Problem Statement** — What pain point does this solve?
   - **3. Target Users** — Who uses this and why?
   - **4. User Stories** — 5-10 "As a [role], I want [feature] so that [benefit]"
   - **5. Success Metrics** — KPIs and measurable outcomes
   - **6. Features (MVP)** — Prioritized feature list (MoSCoW)
   - **7. Features (V2)** — Future roadmap items
   - **8. Technical Architecture** — Stack, services, data flow
   - **9. Database Schema** — Tables, relationships, RLS policies
   - **10. API Endpoints** — Routes, methods, payloads
   - **11. UI/UX Requirements** — Wireframe descriptions, responsive breakpoints
   - **12. Integrations** — Third-party services (Stripe, Supabase, n8n)
   - **13. Security Requirements** — Auth, RLS, input validation, OWASP
   - **14. Timeline & Milestones** — Phased delivery with dual effort estimates
   - **15. Pricing & Revenue Model** — How the client monetizes

4. Include AI Effort Compression table (human time vs CC+Bravo time).

5. Save to `.agents/plans/prd-<project-name>.md`.

6. Present to CC for review and iteration.
