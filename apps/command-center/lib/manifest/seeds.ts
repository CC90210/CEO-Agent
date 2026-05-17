/**
 * Seed manifests — in-code source of truth that mirrors the legacy
 * lib/client-profiles.ts registry. These are the manifests we serve when:
 *
 *   1. the `tenant_manifests` Supabase table is empty (fresh install), OR
 *   2. the DB is unreachable from a Vercel function for this request, OR
 *   3. the requested slug isn't in the DB but we want a sensible default.
 *
 * Once Phase 2's AI editor lands and writes to Supabase, seeds become the
 * "shipped defaults" — the DB row overrides per tenant. Until then, the seeds
 * ARE the manifests, just loaded through the same pipeline a DB-backed
 * manifest would use, so the cutover in 1b is a no-op for the renderer.
 */

import { CC_NAV, SUGA_NAV, SUN_NAV, type NavItem } from "../nav-config";
import {
  MANIFEST_SCHEMA_VERSION,
  type ManifestNavItem,
  type TenantManifest,
} from "./schema";

function navToManifest(items: NavItem[]): ManifestNavItem[] {
  return items.map((item) => ({
    href: item.href,
    label: item.label,
    icon: item.icon,
    group: item.group,
    badge_key: item.badgeKey,
    expandable: item.expandable,
  }));
}

const FROZEN_AT = "2026-05-13T00:00:00.000Z";

// OASIS AI — CC's own home tenant. Nav still uses bare-path legacy routes
// (which work because the rest of the dashboard has legacy pages at those
// paths) but the manifest now declares pages + entities so /t/oasis renders
// real manifest-driven content for cross-tenant consistency. When the
// legacy bare-path pages get migrated to manifest-driven, we flip the nav
// hrefs to /t/oasis/<path> too.
export const OASIS_SEED: TenantManifest = {
  version: 1,
  tenant_slug: "oasis",
  brand: {
    name: "OASIS AI",
    logo: "oasis",
    subtitle: "Agent Command Center",
    footer_label: "OASIS AI · Agent Command Center · v1.0",
    footer_tagline: '"Only good things from now on."',
  },
  agents: [
    { slug: "bravo", display_name: "Bravo", enabled: true, primary: true },
    { slug: "atlas", display_name: "Atlas", enabled: true },
    { slug: "maven", display_name: "Maven", enabled: true },
    // Aura — voice / sensory persona. Owns scripts/aura/ (morning pow
    // wow + future voice automations). Enabled 2026-05-17 when Aura got
    // her own home directory and first cron. See agents/aura.md.
    { slug: "aura", display_name: "Aura", enabled: true },
  ],
  nav: navToManifest(CC_NAV),
  data_model: [
    {
      name: "lead",
      label: "Lead",
      fields: [
        { name: "name", type: "string", required: true },
        { name: "company", type: "string" },
        { name: "email", type: "string" },
        { name: "phone", type: "string" },
        { name: "source", type: "enum", enum_values: ["referral", "inbound", "outbound", "event", "cold_outreach", "other"] },
        // OASIS lead stages (operator-side sales funnel for AI agent
        // builds + retainers). Different shape from SUN_SEED's funding
        // funnel — these are the stages CC moves a prospect through when
        // selling an OASIS agent.
        //
        //   new          — fresh lead, hasn't been contacted yet
        //   contacted    — first touch sent (cold email / DM / call)
        //   qualified    — replied with intent, fits the ICP
        //   proposal     — SOW / proposal sent
        //   negotiation  — back-and-forth on scope or price
        //   won          — signed, project kicked off
        //   lost         — passed, ghosted, or not a fit
        { name: "stage", type: "enum", enum_values: ["new", "contacted", "qualified", "proposal", "negotiation", "won", "lost"], required: true },
        { name: "score", type: "number" },
        { name: "value_estimate", type: "number" },
        { name: "last_contacted_at", type: "date" },
        { name: "notes", type: "string" },
        // AI scoring fields (Phase 5a). Written by POST /api/leads/[id]/score
        // when an operator clicks "Score with AI" on the lead detail page,
        // OR by a daily cron that scores unscored leads in batches.
        // ai_score: 0-100 fit + close-likelihood + urgency
        // ai_reasoning: 1-2 sentence Claude rationale for the score
        // ai_scored_at: timestamp so the UI can show staleness
        { name: "ai_score", type: "number" },
        { name: "ai_reasoning", type: "string" },
        { name: "ai_scored_at", type: "datetime" },
        // AI next-action fields (Phase 5b). Written by POST
        // /api/leads/[id]/next-action — Claude reads the lead + last 10
        // interactions and recommends a single concrete next move.
        { name: "ai_next_action", type: "string" },
        { name: "ai_next_action_rationale", type: "string" },
        { name: "ai_next_action_at", type: "datetime" },
      ],
    },
    {
      name: "contact",
      label: "Contact",
      fields: [
        { name: "name", type: "string", required: true },
        { name: "email", type: "string" },
        { name: "phone", type: "string" },
        { name: "company", type: "string" },
        { name: "role", type: "string" },
        { name: "lead_id", type: "string" },
        { name: "last_contacted_at", type: "date" },
        { name: "notes", type: "string" },
      ],
    },
    {
      name: "proposal",
      label: "Proposal",
      fields: [
        { name: "title", type: "string", required: true },
        { name: "lead_id", type: "string" },
        // OASIS sells AI agent builds. Proposal lifecycle:
        //   draft       — operator is composing
        //   sent        — link delivered, awaiting view
        //   viewed      — prospect opened the proposal page
        //   signed      — accepted (kicks the "won" stage on the lead)
        //   declined    — passed
        //   expired     — TTL elapsed without action
        { name: "stage", type: "enum", enum_values: ["draft", "sent", "viewed", "signed", "declined", "expired"], required: true },
        { name: "value_usd", type: "number" },
        { name: "monthly_retainer_usd", type: "number" },
        { name: "sent_at", type: "date" },
        { name: "signed_at", type: "date" },
        { name: "notes", type: "string" },
      ],
    },
    {
      name: "task",
      label: "Task",
      fields: [
        { name: "title", type: "string", required: true },
        { name: "agent_slug", type: "string" },
        { name: "status", type: "enum", enum_values: ["pending", "in_progress", "blocked", "done"], required: true },
        { name: "due_date", type: "date" },
      ],
    },
  ],
  pages: [
    { path: "", label: "Today", kind: "dashboard" },
    { path: "reasoning", label: "Reasoning", kind: "reasoning" },
    { path: "leads", label: "Leads (manifest view)", kind: "kanban", entity: "lead", config: { group_by: "stage" } },
    { path: "contacts", label: "Contacts", kind: "table", entity: "contact" },
    { path: "proposals", label: "Proposals", kind: "kanban", entity: "proposal", config: { group_by: "stage" } },
    { path: "tasks", label: "Tasks", kind: "kanban", entity: "task", config: { group_by: "status" } },
  ],
  default_prompts: [
    { agent_slug: "bravo", label: "Daily standup", prompt: "Give me a 5-bullet brief: hot leads, deals closing this week, today's blocks, top priority, anything past-due." },
    { agent_slug: "maven", label: "Draft content drop", prompt: "Pick the highest-leverage move from this week's pipeline and draft a social post in my voice." },
    { agent_slug: "atlas", label: "Cash position", prompt: "Net MRR, current burn, projected runway, anything that looks off in the last 7 days." },
  ],
  data_backend: "supabase",
  deployment_mode: "shared",
  permissions: { local_files: true, computer_control: true, web_access: true },
  onboarding_industry: "custom",
  tier: {
    label: "Enterprise",
    setup_complexity: "Done-for-you",
    monthly_price_hint: "Internal",
    summary: "OASIS HQ · operator chrome · all agents enabled.",
  },
  // CC is the operator — keep the 4-mode chat picker (Phase 3) visible so
  // he can pin CLI / cloud_only / cloud_bridge_tools per turn. End-user
  // tenants below get advanced_picker=false so the dropdown is hidden.
  ui: {
    advanced_picker: true,
  },
  meta: {
    created_at: FROZEN_AT,
    updated_at: FROZEN_AT,
    schema_version: MANIFEST_SCHEMA_VERSION,
  },
};

// SunBiz Funding — fully populated tenant. Used at /t/sun/* as the
// authoritative source. The nav hrefs target the /t/sun/<path> namespace
// so every click lands on a manifest-driven page; the catch-all renderer
// dispatches by `pages[].kind`.
export const SUN_SEED: TenantManifest = {
  version: 1,
  tenant_slug: "sun",
  brand: {
    name: "Sun Biz Funding",
    logo: "sunbiz",
    subtitle: "Agent Command Center",
    footer_label: "Sun Biz Funding · Agent Command Center · v1.0",
    footer_tagline: "Funded deals over noise.",
  },
  agents: [
    // Operational primary — backend admin, Chrome jobs, data collection, workflow runner.
    // Where Ezra goes when they need work done.
    { slug: "solara", display_name: "Solara", enabled: true, primary: true },
    // Brand-facing sales persona — personable, sales-driven outreach, SMS follow-ups.
    // The voice SunBiz leads experience. Name TBD with CC; helios is the working default
    // (sun-themed, matches the Solara linguistic family).
    { slug: "helios", display_name: "Helios", enabled: true },
  ],
  nav: [
    { href: "/t/sun", label: "Dashboard", icon: "LayoutDashboard", group: "Operations" },
    // Top-level /agent chat — Ezra picks between Solara (operational) and
    // Helios (sales) via the in-widget switcher. Lives outside the /t/sun
    // namespace because chat is a shared dashboard surface, not a manifest
    // primitive — this is just the entry point.
    { href: "/agent", label: "Agents", icon: "Bot", group: "Operations" },
    { href: "/t/sun/reasoning", label: "Reasoning", icon: "Brain", group: "Operations" },
    { href: "/t/sun/playbook", label: "Playbook", icon: "BookOpen", group: "Operations" },
    { href: "/t/sun/leads", label: "Leads", icon: "Users", group: "Pipeline" },
    { href: "/t/sun/applications", label: "Applications", icon: "FileText", group: "Pipeline" },
    { href: "/t/sun/import", label: "Import", icon: "Upload", group: "Pipeline" },
    // /forms is top-level (tenant-aware on the server via user.tenant_id).
    // Same shared surface every tenant gets — design forms, mint
    // personalized lead links, replace JotForm.
    { href: "/forms", label: "Forms", icon: "FileCode2", group: "Pipeline" },
    // /sequences is the drip-campaign control panel — same Outreach
    // lane as SMS / Email Blast but for status-triggered automation.
    { href: "/sequences", label: "Sequences", icon: "Sparkles", group: "Pipeline" },
    { href: "/t/sun/offers", label: "Offers", icon: "HandCoins", group: "Deals" },
    { href: "/t/sun/funded-deals", label: "Funded Deals", icon: "BadgeDollarSign", group: "Deals" },
    { href: "/t/sun/renewals", label: "Renewals", icon: "RefreshCcw", group: "Deals" },
    { href: "/t/sun/commissions", label: "Commissions", icon: "DollarSign", group: "Deals" },
    { href: "/t/sun/lenders", label: "Lenders", icon: "Landmark", group: "Network" },
    // Top-level /automations — tenant-aware cron job manager. Bridge polls
    // tenant_cron_jobs and executes locally on the operator's machine.
    // Same surface across every tenant; routes here from any /t/<slug>/
    // path land on the shared /automations page.
    { href: "/automations", label: "Automations", icon: "RefreshCcw", group: "System" },
    // Top-level /settings — already tenant-aware (reads profile.tenant_id).
    // Modeled on the OASIS settings shell: integrations, agents enabled,
    // templates, devices, password. Same shape, tenant-scoped data.
    { href: "/settings", label: "Settings", icon: "Settings", group: "System" },
  ],
  data_model: [
    {
      name: "lead",
      label: "Lead",
      fields: [
        { name: "business_name", type: "string", required: true },
        { name: "contact_name", type: "string" },
        { name: "phone", type: "string" },
        { name: "email", type: "string" },
        { name: "monthly_revenue", type: "number" },
        // Lead Pipeline stages — verbatim Salesforce parity per Adon's
        // 2026-05-16 screenshots. Order = left-to-right arrow flow on
        // the pipeline bar. Colors live in lib/sunbiz-stage-meta.ts.
        //
        //   imported            — fresh CSV/API ingest, no engagement yet
        //   not_interested      — explicitly declined the cold touch
        //   hot_lead            — actively engaging, replied / called back
        //   missing_info        — needs additional data before progressing
        //                         (auto-tagged by Phase 20 classifier)
        //   declined            — lender or operator passed
        //   follow_up           — nurture cadence, waiting on next touch
        //   sent_application    — Solara dispatched the application link
        //   viewed_application  — prospect opened the link (engagement)
        //   signed_application  — prospect completed the application form
        //   default             — repayment failure / bankruptcy
        //   submitted           — submitted to underwriting (graduates to
        //                         Opportunity Pipeline; see offer.stage)
        //   approved            — lender approved (graduates to offer)
        { name: "stage", type: "enum", enum_values: ["imported", "not_interested", "hot_lead", "missing_info", "declined", "follow_up", "sent_application", "viewed_application", "signed_application", "default", "submitted", "approved"], required: true },
        // missing_info — Phase 20 (2026-05-17) classifier output. Array
        // of canonical doc-type strings the lead still owes us before
        // an application can advance. Populated by
        // scripts/lender_response_classifier.py's second LLM pass when
        // an inbound lender email is classified as info_request. The
        // Documents tab on the lead drawer auto-clears entries here
        // when a matching lead_document is uploaded (Phase 20.4).
        // Renders as a red "🔴 Missing: bank_statements_3mo" chip on
        // the lead Kanban card.
        { name: "missing_info", type: "json" },
      ],
    },
    {
      name: "application",
      label: "Application",
      fields: [
        { name: "business_name", type: "string", required: true },
        { name: "contact_name", type: "string" },
        { name: "lead_id", type: "string" },
        { name: "lender_id", type: "string" },
        { name: "requested_amount", type: "number" },
        { name: "submitted_at", type: "datetime" },
        // Opportunity Pipeline status — verbatim Salesforce parity per
        // Adon's 2026-05-16 screenshots. /applications page renders this
        // as the chevron pipeline. "New" is intentionally excluded per
        // the meeting decision. Order = left-to-right arrow flow.
        // Colors in lib/sunbiz-stage-meta.ts under the "application" key.
        //
        //   submitted_to_underwriting — application in lender hands
        //   approved_open_offers      — lender returned a term sheet
        //   contracts_ordered         — contract sent; awaiting signature
        //   funded                    — wire complete; rolls into
        //                               funded_deals + commissions
        //   approved_never_funded     — approved but client never closed
        //                               (revival drip eligible)
        //   no_offers_available       — every lender declined
        //   dead_file                 — client killed the deal
        { name: "status", type: "enum", enum_values: ["submitted_to_underwriting", "approved_open_offers", "contracts_ordered", "funded", "approved_never_funded", "no_offers_available", "dead_file"], required: true },
      ],
    },
    {
      name: "offer",
      label: "Offer",
      fields: [
        { name: "business_name", type: "string", required: true },
        { name: "application_id", type: "string" },
        { name: "lender_id", type: "string" },
        { name: "lender_name", type: "string" },
        { name: "amount", type: "number" },
        { name: "term_months", type: "number" },
        { name: "factor_rate", type: "number" },
        // Opportunity Pipeline stages — verbatim Salesforce parity per
        // Adon's 2026-05-16 screenshots. "New" is intentionally excluded
        // per the meeting decision. Order = left-to-right arrow flow.
        // Colors in lib/sunbiz-stage-meta.ts.
        //
        //   submitted_to_underwriting — application in lender hands
        //   approved_open_offers      — lender returned a term sheet
        //   contracts_ordered         — contract sent to client; awaiting
        //                               signature
        //   funded                    — wire complete; rolls into
        //                               funded_deals + commission split
        //   approved_never_funded     — approved but client never closed
        //                               (revival drip eligible)
        //   no_offers_available       — every lender declined
        //   dead_file                 — file was good but client killed
        //                               it (took a competitor's offer,
        //                               lost contact, changed plans)
        { name: "stage", type: "enum", enum_values: ["submitted_to_underwriting", "approved_open_offers", "contracts_ordered", "funded", "approved_never_funded", "no_offers_available", "dead_file"], required: true },
      ],
    },
    {
      name: "funded_deal",
      label: "Funded Deal",
      fields: [
        { name: "business_name", type: "string", required: true },
        { name: "lead_id", type: "string" },
        { name: "lender_id", type: "string" },
        { name: "lender_name", type: "string" },
        { name: "product_type", type: "enum", enum_values: ["same_day_funding", "mca", "term_loan", "long_term_loan", "line_of_credit", "equipment", "invoice_factoring", "sba"] },
        { name: "amount_funded", type: "number", required: true },
        { name: "funded_at", type: "date" },
        { name: "term_months", type: "number" },
        { name: "factor_rate", type: "number" },
        { name: "repayment_amount", type: "number" },
        { name: "commission_amount", type: "number" },
        { name: "renewal_eligible_at", type: "date" },
        { name: "status", type: "enum", enum_values: ["funded", "renewal_due", "renewed", "lost", "default"] },
      ],
    },
    {
      name: "renewal",
      label: "Renewal",
      fields: [
        { name: "business_name", type: "string", required: true },
        { name: "funded_deal_id", type: "string" },
        { name: "amount_available", type: "number" },
        { name: "due_date", type: "date" },
        { name: "last_contacted_at", type: "date" },
        { name: "next_action", type: "string" },
        { name: "status", type: "enum", enum_values: ["upcoming", "due", "overdue", "renewed", "lost"], required: true },
      ],
    },
    {
      name: "commission",
      label: "Commission",
      fields: [
        { name: "business_name", type: "string", required: true },
        { name: "funded_deal_id", type: "string" },
        { name: "lender_name", type: "string" },
        { name: "broker_share_pct", type: "number" },
        { name: "amount", type: "number" },
        { name: "paid", type: "boolean" },
        { name: "paid_at", type: "date" },
      ],
    },
    {
      name: "lender",
      label: "Lender",
      fields: [
        { name: "name", type: "string", required: true },
        { name: "contact", type: "string" },
        // Phase 6.1 — match-fitness fields per Jordan's 2026-05-15
        // meeting. Operator UI on /lenders/[id]/edit lets the operator
        // populate these; the shop-out flow pre-ranks lenders against
        // each application's profile before the operator picks.
        { name: "product_type", type: "enum", enum_values: ["same_day_funding", "mca", "term_loan", "long_term_loan", "line_of_credit", "equipment", "invoice_factoring", "sba"] },
        { name: "min_monthly_revenue", type: "number" },
        { name: "max_funded_amount", type: "number" },
        { name: "min_time_in_business_months", type: "number" },
        { name: "fico_floor", type: "number" },
        { name: "sla_response_days", type: "number" },
        { name: "notes", type: "string" },
      ],
    },
  ],
  pages: [
    { path: "", label: "Solara — Today", kind: "dashboard" },
    { path: "reasoning", label: "Reasoning", kind: "reasoning" },
    // Two-pipeline superview — Salesforce-replacement overview per the
    // 2026-05-16 meeting. Renders Lead Pipeline (lead.stage) over
    // Opportunity Pipeline (offer.stage) with the submitted→offered
    // graduation visualised. Operators still drill into /leads or
    // /offers individually for full-board interaction.
    // Stacked overview — Lead Pipeline above Opportunity Pipeline.
    // Useful for the morning glance; daily-driving happens on /leads
    // and /applications individually.
    { path: "pipeline", label: "Pipeline", kind: "pipeline", config: { lead_entity: "lead", opportunity_entity: "application" } },
    // Lead Pipeline — the chevron arrow bar + filtered records table,
    // verbatim Salesforce per Adon's screenshots. Replaces the prior
    // /leads Kanban (2026-05-17). Filter by ?stage=<key>.
    { path: "leads", label: "Lead Pipeline", kind: "pipeline_entity", entity: "lead", config: { stage_field: "stage" } },
    // Opportunity Pipeline — same chevron pattern keyed on
    // application.status. Verbatim Salesforce stages (submitted_to_
    // underwriting → funded → dead_file). Replaces the prior
    // /applications Kanban (2026-05-17). Filter by ?stage=<key>.
    {
      path: "applications",
      label: "Opportunity Pipeline",
      kind: "pipeline_entity",
      entity: "application",
      config: { stage_field: "status" },
    },
    // Offers are per-lender term sheets under an application; rendered
    // as the conventional Kanban since they're a sub-detail view, not
    // the operator's primary pipeline.
    { path: "offers", label: "Offers", kind: "kanban", entity: "offer", config: { group_by: "stage" } },
    {
      path: "funded-deals",
      label: "Funded Deals",
      kind: "kanban",
      entity: "funded_deal",
      // Synthetic Kanban bucketing — server computes renewal_window from
      // funded_at + term_months on every row read. Columns:
      //   upcoming (0-40%) → due (40-50%) → overdue (50%+) → renewed → lost
      // Matches the meeting decision (CC + Adon, 2026-05-15) that funded
      // deals get a renewal-window-driven pipeline view instead of a flat
      // table. Operator can flip to ?view=table for sorting/filtering.
      config: { compute_group_by: "renewal_window" },
    },
    { path: "renewals", label: "Renewals", kind: "kanban", entity: "renewal", config: { group_by: "status" } },
    { path: "commissions", label: "Commissions", kind: "table", entity: "commission" },
    { path: "lenders", label: "Lenders", kind: "table", entity: "lender" },
    { path: "import", label: "Import leads", kind: "import" },
    { path: "playbook", label: "Operating Manual", kind: "markdown", config: { body: "## Meet your agents\n\n**Solara** is your funding-shop operator. She watches the pipeline, drafts follow-ups in your voice over text and email, scores incoming applications against your lender book, and surfaces renewal windows before they close.\n\n**Helios** is your sales voice. He runs cold outreach and brings ghosted deals back to the table — the same human-sounding cadence you'd send yourself, just faster.\n\n## Where leads come from\n\n- The **SunBiz application form** (built into the dashboard — see Forms). Personalized links go out by SMS or email; submissions land in Leads in the **Imported** column.\n- **Bulk CSV import** (see Import). Drop a Google Sheet export and Solara de-duplicates by email and phone before adding.\n- **Manual entry** from the Leads page → **+ New lead**.\n\n## Your day, end to end\n\n1. **Open the Dashboard.** Hot leads, missing-info alerts, and renewals due are at the top — that's your priority list.\n2. **Move leads through the pipeline.** Click any chevron stage to see who's there. Drag the hot ones to **Follow Up** and the 3-touch cadence fires automatically.\n3. **Send applications.** When a lead is ready, send them the application link from their detail page. Once they sign and upload bank statements, they graduate to the Opportunity Pipeline.\n4. **Shop the application out.** Open the application card and check **Recommended Lenders** — top fits by FICO, monthly revenue, and time in business. One click forwards the deal to a lender.\n5. **Log the offer.** When a lender returns terms, capture them in Offers. Click **Accept** and the deal rolls into Funded Deals as a draft.\n6. **Watch renewals.** Funded Deals shows the renewal window — anything 40-50% through term is your re-funding focus for the week.\n\n## Behind the scenes\n\n- The **Automations** tab shows the scheduled jobs running on your computer — lead scoring, follow-up checks, daily briefs. You can describe a new one in plain English and your agent writes the script for you.\n- **Settings → Devices** is where you pair the local install. Once paired, the dashboard reads from your machine and your agents can run code in the background." } },
  ],
  default_prompts: [
    // Solara — operational
    { agent_slug: "solara", label: "Morning briefing", prompt: "Pull leads that haven't been touched in 24h, applications waiting on docs, and offers expiring this week." },
    { agent_slug: "solara", label: "Renewal sweep", prompt: "Which funded deals are within 60 days of renewal? Surface the top 3 by amount." },
    { agent_slug: "solara", label: "Lender match", prompt: "For the top 3 qualified leads, recommend the best-fit lender based on monthly revenue and product type." },
    { agent_slug: "solara", label: "Record funded deal", prompt: "Create a funded deal from this note: ABC Corp funded $50,000 today with XYZ Capital on a 12-month term. If anything required is missing, ask one clear question before writing." },
    { agent_slug: "solara", label: "Update renewal status", prompt: "Find the renewal record for ABC Corp and mark the next action as call owner today. If there are multiple matches, show them before updating." },
    // Helios — sales / outreach
    { agent_slug: "helios", label: "Draft cold outreach", prompt: "Draft a first-touch SMS for a freshly qualified lead. Sound human, not corporate. Open with their business pain, not our offer." },
    { agent_slug: "helios", label: "Follow-up cadence", prompt: "For leads that ghosted after the application step, draft a 3-touch revival sequence over 7 days." },
    { agent_slug: "helios", label: "Close the loop", prompt: "An approved offer just expired. Draft the SMS to bring them back to the table without sounding salesy." },
  ],
  // Universal default 2026-05-15 — all tenant data lives in CC's Supabase
  // project, scoped by tenant_id + RLS. Lower onboarding friction (no
  // per-tenant Turso provisioning step). Clients who outgrow the shared
  // tier and want physical isolation can self-host Turso later.
  data_backend: "supabase",
  deployment_mode: "dedicated",
  permissions: { local_files: true, computer_control: false, web_access: true },
  onboarding_industry: "business_funding",
  tier: {
    label: "Pro",
    setup_complexity: "Guided",
    monthly_price_hint: "Custom",
    summary: "Funding shop: Solara + Helios, full pipeline.",
  },
  compliance: {
    tcpa: {
      send_window_local: "9am-9pm",
      honor_opt_outs: true,
      weekend_sends: false,
      opt_out_phrase: "Reply STOP to opt out.",
    },
  },
  integrations: [
    { kind: "jotform", enabled: true, credential_env_key: "SUNBIZ_AGENT_API_URL" },
    { kind: "twilio", enabled: true, credential_env_key: "SUNBIZ_AGENT_HMAC_SECRET" },
    { kind: "turso", enabled: true },
  ],
  // End-user tenant — hide the 4-mode chat picker. Ezra at SunBiz doesn't
  // need to think about CLI vs API; Auto-mode routing handles it silently.
  ui: {
    advanced_picker: false,
  },
  meta: {
    created_at: FROZEN_AT,
    updated_at: FROZEN_AT,
    schema_version: MANIFEST_SCHEMA_VERSION,
  },
};

export const SUGA_SEED: TenantManifest = {
  version: 1,
  tenant_slug: "suga",
  brand: {
    name: "Suga · Brand Command",
    logo: "suga",
    subtitle: "Agent Command Center",
    footer_label: "Suga · Brand Command · v0.1",
    footer_tagline: "Fans first. Always.",
  },
  agents: [
    // Maven (CMO) owns brand work — content, fans, sponsorships, drops.
    // Previously this seed had a 4-agent Lyra package; collapsed 2026-05-14
    // because the brand-command capabilities fold cleanly into Maven, and
    // a tenant-specific agent fork is over-engineering for one client.
    { slug: "maven", display_name: "Maven", enabled: true, primary: true },
  ],
  nav: [
    { href: "/t/suga", label: "Dashboard", icon: "LayoutDashboard", group: "Operations" },
    // Top-level /agent chat — Maven as the primary brand agent.
    { href: "/agent", label: "Agents", icon: "Bot", group: "Operations" },
    { href: "/t/suga/subscribers", label: "Subscribers", icon: "Users", group: "Fans" },
    { href: "/t/suga/posts", label: "Posts", icon: "Megaphone", group: "Brand" },
    { href: "/t/suga/drafts", label: "Drafts", icon: "FileText", group: "Brand" },
    // /forms intentionally absent from SUGA — the form builder is the
    // SunBiz funding-shop workflow (3-step funnel with bank-statement
    // upload + lead.stage transitions). SUGA's fan-signup model uses a
    // different pattern; not the same surface.
    { href: "/t/suga/merch", label: "Merch", icon: "ShoppingBag", group: "Commerce" },
    { href: "/t/suga/sponsorship", label: "Sponsorships", icon: "HandCoins", group: "Sponsorship" },
    // Top-level /automations — same shared cron-job surface every tenant
    // gets. Sidebar entry is mirrored across SUN_SEED + SUGA_SEED + the
    // CC_NAV-derived OASIS_SEED so operators on /t/suga/* land on the
    // same Automations page anyone else does.
    { href: "/automations", label: "Automations", icon: "RefreshCcw", group: "System" },
    { href: "/settings", label: "Settings", icon: "Settings", group: "System" },
  ],
  data_model: [
    {
      name: "subscriber",
      label: "Subscriber",
      fields: [
        { name: "email", type: "string", required: true },
        { name: "name", type: "string" },
        { name: "tier", type: "enum", enum_values: ["free", "vip", "patron"] },
      ],
    },
    {
      name: "post",
      label: "Post",
      fields: [
        { name: "title", type: "string", required: true },
        { name: "platform", type: "enum", enum_values: ["instagram", "x", "tiktok", "youtube", "email"] },
        { name: "status", type: "enum", enum_values: ["draft", "scheduled", "published"], required: true },
      ],
    },
    {
      name: "merch_drop",
      label: "Merch Drop",
      fields: [
        { name: "name", type: "string", required: true },
        { name: "stock", type: "number" },
        { name: "status", type: "enum", enum_values: ["upcoming", "live", "sold_out", "archived"] },
      ],
    },
    {
      name: "sponsorship",
      label: "Sponsorship",
      fields: [
        { name: "brand", type: "string", required: true },
        { name: "value", type: "number" },
        { name: "stage", type: "enum", enum_values: ["outreach", "negotiating", "signed", "delivered", "lost"], required: true },
      ],
    },
  ],
  pages: [
    { path: "", label: "Fans · Today", kind: "dashboard" },
    { path: "reasoning", label: "Reasoning", kind: "reasoning" },
    { path: "subscribers", label: "Subscribers", kind: "table", entity: "subscriber" },
    { path: "posts", label: "Posts", kind: "kanban", entity: "post", config: { group_by: "status" } },
    { path: "drafts", label: "Drafts", kind: "table", entity: "post" },
    { path: "merch", label: "Merch Drops", kind: "kanban", entity: "merch_drop", config: { group_by: "status" } },
    { path: "sponsorship", label: "Sponsorships", kind: "kanban", entity: "sponsorship", config: { group_by: "stage" } },
  ],
  default_prompts: [
    { agent_slug: "maven", label: "Fan check-in", prompt: "Pull the most engaged 10 subscribers this week. Suggest a personalised DM I can send." },
    { agent_slug: "maven", label: "Post idea", prompt: "What's a high-engagement post angle I haven't run this month?" },
    { agent_slug: "maven", label: "Merch drop sweep", prompt: "Which merch drops are due to go live this month? Anything understocked?" },
    { agent_slug: "maven", label: "Weekly brand pulse", prompt: "Summarise this week's posts, subscriber growth, and any sponsorship movement in 5 bullets." },
  ],
  // Universal default 2026-05-15 — all tenant data lives in CC's Supabase
  // project, scoped by tenant_id + RLS. Lower onboarding friction (no
  // per-tenant Turso provisioning step). Clients who outgrow the shared
  // tier and want physical isolation can self-host Turso later.
  data_backend: "supabase",
  deployment_mode: "dedicated",
  permissions: { local_files: false, computer_control: false, web_access: true },
  onboarding_industry: "agency",
  tier: {
    label: "Pro",
    setup_complexity: "Guided",
    monthly_price_hint: "$99/mo",
    summary: "Brand command: posts, fans, merch, sponsorships.",
  },
  // End-user tenant — hide the 4-mode chat picker. SUGA operators see one
  // chat that just works; Auto-mode handles routing.
  ui: {
    advanced_picker: false,
  },
  meta: {
    created_at: FROZEN_AT,
    updated_at: FROZEN_AT,
    schema_version: MANIFEST_SCHEMA_VERSION,
  },
};

/**
 * Slug map for synchronous lookups. The loader uses this as the fallback when
 * Supabase has no row for a slug; the AI editor writes new manifests to DB,
 * never to this map.
 */
export const SEED_MANIFESTS: Record<string, TenantManifest> = {
  default: OASIS_SEED,
  oasis: OASIS_SEED,
  sun: SUN_SEED,
  suga: SUGA_SEED,
};

export function getSeedManifest(slug: string | null | undefined): TenantManifest {
  const key = (slug || "").trim().toLowerCase();
  return SEED_MANIFESTS[key] || OASIS_SEED;
}
