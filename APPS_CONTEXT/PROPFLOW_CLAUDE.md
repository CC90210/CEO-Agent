> **ROUTING:** Local `C:\Users\User\realestate-App` | GitHub: CC90210/real-estate-App | Deploy: Vercel

# PropFlow — Real Estate Management Platform

## Project Overview

PropFlow is a comprehensive property management SaaS platform for real estate professionals. It combines CRM, document generation, AI chat, and marketing tools into one Stripe-quality UI. Built for white-label distribution to real estate agencies.

## Tech Stack

- **Frontend:** Next.js 14+ (App Router), TypeScript, Tailwind CSS
- **Backend:** Supabase (PostgreSQL, Auth, Storage, Realtime)
- **Hosting:** Vercel
- **Payments:** Stripe (subscriptions for SaaS tiers)
- **AI:** Google Gemini API (chat assistant, marketing generator)
- **File generation:** PDF document generation
- **Domain:** propflow.io (or may change)

## Database Structure (Supabase)

Key tables:
- `areas` → `buildings` → `units` (hierarchical property management)
- `applications` (tenant application tracking with status workflow)
- `landlords` (landlord profiles linked to properties)
- `documents` (generated PDFs — property sheets, lease proposals, etc.)
- `users` (role-based: Admin, Landlord, Agent)

## Core Features

1. **Dashboard** — Overview stats, recent activity, quick actions
2. **Property Management** — Areas → Buildings → Units hierarchy, CRUD, image gallery
3. **Application Tracking** — Status workflow: Submitted → Screening → Approved/Denied
4. **Document Generator** — Property Summary Sheet, Showing Sheet, Lease Proposal, Application Summary
5. **AI Chat Assistant** — Query property database in natural language
6. **AI Marketing Generator** — Listing descriptions, social posts, email templates
7. **Landlord Management** — Profiles, property linking, landlord portal
8. **Role-Based Access** — Admin (full), Landlord (their properties), Agent (limited)

## Design Standards

- Stripe-like clean UI (light theme, subtle shadows, rounded corners)
- Blue primary color (#2563EB), clean whites and grays
- Responsive — desktop-first but fully mobile compatible
- Lucide React icons
- Professional typography, generous whitespace

## White Label Architecture

- Multi-tenant design (organization-based isolation)
- Customizable branding (logo, colors, domain)
- Each agency gets their own subdomain or custom domain
- Shared infrastructure, isolated data

## Development Commands

```bash
npm run dev          # Start development server
npm run build        # Build for production
npm run lint         # Run ESLint
npx supabase db push # Push database migrations
```

## Key Commands

```
/deploy              → Build, test, and deploy to Vercel
/generate-docs       → Generate/update API documentation
/add-feature         → Plan and implement a new feature
/db-migrate          → Create and push a database migration
```

## Obsidian Links
- [[APPS_CONTEXT/INDEX]] | [[brain/APP_REGISTRY]]
