# IMPLEMENTATION PLAN & SYSTEM MESSAGE: Custom Painting/Restoration Management Software

## 1. Product Vision & Value Proposition
**Goal:** Build a consolidated, custom operational software for a 7-person painting and restoration company to replace multiple disparate subscriptions (Jobber, Housecall Pro, PaintScout) into one proprietary, unified dashboard.
**Value:** Instead of paying multiple monthly SaaS fees and dealing with clunky integrations, the client gets a 100% tailored solution that they own.
**Pricing Model:** One-time build fee ($7k - $10k), potentially with a small ongoing maintenance retainer. No per-user seat fees like Jobber.

## 2. Core Functional Requirements (To Replace Jobber & PaintScout)

### A. Lead & Client Management (CRM)
*   **Customer Profiles:** Store contact info, property details, and past jobs.
*   **Lead Pipeline:** Kanban-style board (New Lead -> Walkthrough -> Quoted -> Scheduled -> Complete).

### B. Estimating & Quoting (PaintScout Alternative)
*   **Line-Item Estimates:** Ability to add labor, paint, materials, and custom markup.
*   **Document Generation:** Generate clean, branded PDF quotes.
*   **E-Signatures/Approvals:** Clients can view a web link to their quote and click "Accept".

### C. Job Scheduling & Field Dispatch (Jobber Alternative)
*   **Calendar View:** Drag-and-drop scheduling for the crews.
*   **Field View:** Mobile-friendly view for crews to see today's job, property address, paint codes, and access codes.
*   **Job Status:** Mark jobs as "In Progress" or "Complete".

### D. Invoicing & Payments (Stripe Integration)
*   **Automated Invoicing:** Convert accepted quotes into invoices with one click.
*   **Payment Processing:** Securely collect credit card via Stripe Checkout or Stripe Elements.
*   **Client Onboarding (Stripe):** Client needs to be walked through setting up their own Stripe account so payments route directly to their bank.

---

## 3. Technology Stack

*   **Framework:** Next.js (App Router, React)
*   **Styling:** Tailwind CSS + shadcn/ui (for rapid, clean dashboard components)
*   **Database & Auth:** Supabase (PostgreSQL, Row Level Security for multi-tenant data if ever expanded, secure authentication)
*   **Payments:** Stripe (Stripe Connect or direct standard integration depending on account ownership)
*   **Hosting & Deployment:** Vercel (seamless Next.js integration)
*   **Version Control:** GitHub

---

## 4. System Message / Agent Build Instructions
*(This section can be passed directly to the coding agent to initiate the build)*

**System Prompt:**
"You are a Senior Full-Stack Next.js Developer. Your task is to initialize a new SaaS web application tailored for a painting and restoration company. The goal of this application is to consolidate features from Jobber and PaintScout into a single, specialized dashboard.

**Step 1: Initialization**
*   Create a Next.js (App Router) project with Tailwind CSS.
*   Set up the repository structure and push to a new GitHub repository.

**Step 2: Database Setup**
*   Initialize Supabase. Create tables for: `clients`, `jobs`, `quotes`, `quote_line_items`, and `invoices`.

**Step 3: Core Dashboard UI**
*   Build a responsive sidebar navigation.
*   Create a "Pipeline" view for active leads and jobs.
*   Create an "Estimating" interface to generate quotes, allowing line-item additions for spray, stain, and prep work.

**Step 4: Stripe & Documents**
*   Integrate standard Stripe payment processing so the client can send an invoice link that securely processes credit cards.
*   Implement a PDF generation library (like `jspdf` or `react-pdf`) to generate branded quotes and invoices.

Please acknowledge these requirements and prepare the `npx create-next-app` commands and initial schema."

## Obsidian Links
- [[.agents/workflows/INDEX]] | [[brain/DASHBOARD]]
