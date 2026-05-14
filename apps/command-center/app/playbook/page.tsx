import Link from "next/link";
import { cookies } from "next/headers";
import { ArrowRight, BookOpen, MessageSquareText, RefreshCcw, Users } from "lucide-react";
import { Card, PageHeader, Tag } from "@/components/Card";
import { safe } from "@/lib/api-helpers";
import {
  DEMO_CLIENT_PROFILE_COOKIE,
  getClientCommandCenterProfileById,
  resolveClientProfileSlug,
} from "@/lib/client-profiles";
import { listPlaybooks, type PlaybookFile } from "@/lib/playbooks";
import { getActiveProfile, getTenant } from "@/lib/queries";
import { demoHref } from "@/lib/demo-href";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type PlaybookSection = {
  href: string;
  title: string;
  subtitle: string;
  body: string;
};

const SECTIONS: PlaybookSection[] = [
  {
    href: "/playbook/script",
    title: "Cold Call Script + Objections",
    subtitle: "5 stages - 4 tracks - 10 objections - secondary disarm",
    body:
      "One memorize-grade page. Pattern interrupt, reason, diagnose, pivot, close. Pick your prospect track at the top and run the right language live. Includes the Agree/Validate/Isolate disarm for when prospects double down on 'we're good'.",
  },
  {
    href: "/playbook/deals",
    title: "Deal Architecture",
    subtitle: "Three offers - two partner paths - one decision rule",
    body:
      "Three client offers, two partner paths, and the canonical 50% strategic-partner model. The math is simple enough to defend in any room.",
  },
  {
    href: "/playbook/drills",
    title: "Daily Drills",
    subtitle: "5 reps - 30 min/day - 90-day discipline",
    body:
      "Mirror Run, Objection Volley, Recording Review, KPI Log, Weekly Retro. The boring discipline that turns cold calling into muscle memory.",
  },
  {
    href: "/playbook/business",
    title: "Business Documentation",
    subtitle: "CEO + CFO + CMO + Ops + Legal - every doc a real company needs",
    body:
      "The full hub of business documentation. Manifesto, OKRs, P&L, runway, brand bible, content pillars, MSA template, onboarding SOP, incident runbook. Each pillar owned by the right AI exec - click any doc to ask them to draft or refresh it.",
  },
  {
    href: "/playbook/prompts",
    title: "Prompts Library",
    subtitle: "Saved prompts that move the system - operator + client deployment toolkit",
    body:
      "Reusable prompts for every recurring move. Two audiences: yours (daily ops, system health, [OVERRIDE] syntax) and the client deployment toolkit (setup, voice tune, integration audit, handoff). Foundational prompts are hard-coded; mutable ones can grow as you find new patterns. Click any prompt to drop it straight into chat.",
  },
  {
    href: "/playbook/client-deploy",
    title: "Client Deployment Runbook",
    subtitle: "Six phases - ~60 minutes - the canonical onboarding playbook",
    body:
      "Your step-by-step runbook for spinning up a fresh client. Pre-flight -> bootstrap -> personalize -> integrations -> scope -> handoff. Each step has a chat-fire prompt that runs the move automatically. Use this for every new client - same arc, different tenant.",
  },
  {
    href: "/playbook/client-deploy",
    title: "Multi-Machine Setup",
    subtitle: "Pair desktop + laptop - production daemons stay singular - chat-server per machine",
    body:
      "Clients with multiple machines (desktop + laptop) pair both bridges to the same dashboard tenant. The dashboard auto-detects which bridge is local. Hard rule: only ONE machine runs scheduler / skool / telegram daemons (state mutators). Every other machine runs ONLY the chat-server. The pair endpoint is idempotent by machine_fingerprint, so re-running rotates tokens instead of creating duplicates. See brain/MULTI_MACHINE_PAIRING_PROMPT.md for the paste-ready Antigravity prompt.",
  },
  {
    href: "/playbook/onboarding",
    title: "Operator Onboarding (V6.0)",
    subtitle: "What your agent does - Safe asks - Escalation triggers - Pause + rollback",
    body:
      "Four short SOPs for new operators. Render markdown directly from docs/playbooks/ so non-technical clients can read the agent's contract in the dashboard without opening the repo. Update the markdown, redeploy, and every operator sees the new SOP next refresh.",
  },
  {
    href: "/playbook/security",
    title: "Security Model",
    subtitle: "Multi-tenant RLS - AES-256-GCM at rest - SHA-256 bridge tokens - HMAC self-pair",
    body:
      "How tenant isolation, encryption, and bridge authentication actually work. Every tenant-scoped table is RLS-protected at the Postgres layer. Provider API keys encrypted at rest with AES-256-GCM (scrypt KDF, deploy-wide BRAVO_FIELD_ENCRYPTION_KEY). Bridge tokens are SHA-256 hashed before storage. Self-pair from the daemon uses HMAC headers verified server-side. Migration 030 enforces one live pairing per (tenant, machine_fingerprint) at the DB layer. Read brain/SECURITY_MODEL.md for the full architecture.",
  },
];

const SUN_MANUAL_ORDER = [
  "01-getting-started",
  "02-safe-interaction",
  "03-when-to-call-cc",
  "04-pause-and-rollback",
] as const;

// Slugs that belong to the SunBiz operating manual and must NEVER appear on
// the OASIS Playbook index (otherwise "Meet Solara" leaks into CC's portal).
const SUN_PLAYBOOK_SLUGS = new Set<string>([
  ...SUN_MANUAL_ORDER,
  "05-customer-onboarding-script",
  "06-sunbiz-runbook",
]);

const SUN_MANUAL_META: Record<string, { eyebrow: string; summary: string }> = {
  "01-getting-started": {
    eyebrow: "Step 01",
    summary: "Meet Solara and understand what she owns across the funding pipeline.",
  },
  "02-safe-interaction": {
    eyebrow: "Step 02",
    summary: "Learn how to ask for work, when to review before sending, and how to keep the lane clean.",
  },
  "03-when-to-call-cc": {
    eyebrow: "Step 03",
    summary: "Know the moments when a human opinion, approval, or escalation matters.",
  },
  "04-pause-and-rollback": {
    eyebrow: "Step 04",
    summary: "See how to pause changes, correct mistakes, and move forward calmly.",
  },
};

export default async function PlaybookIndex() {
  const operatingManual = await listPlaybooks();
  const profile = await safe("playbook.profile", getActiveProfile(), null);
  const demoProfileSlug = (await cookies()).get(DEMO_CLIENT_PROFILE_COOKIE)?.value || null;
  const demoProfile = getClientCommandCenterProfileById(demoProfileSlug);
  const tenantProfileSlug =
    demoProfile.id !== "default"
      ? demoProfile.id
      : profile?.tenant_id
        ? await safe(
            "playbook.tenant_profile_slug",
            (async () => {
              const tenant = await getTenant(profile.tenant_id || "");
              return resolveClientProfileSlug(tenant);
            })(),
            null
          )
        : null;

  if (tenantProfileSlug === "sun") {
    const manualFiles = SUN_MANUAL_ORDER
      .map((slug) => operatingManual.find((file) => file.slug === slug) || null)
      .filter((file): file is PlaybookFile => file !== null);
    return <SunBizPlaybookIndex manualFiles={manualFiles} demoMode={demoProfile.id === "sun"} />;
  }

  const defaultManual = operatingManual.filter((f) => !SUN_PLAYBOOK_SLUGS.has(f.slug));
  return <DefaultPlaybookIndex operatingManual={defaultManual} />;
}

function DefaultPlaybookIndex({ operatingManual }: { operatingManual: PlaybookFile[] }) {
  return (
    <div className="space-y-8 animate-fade-in">
      <PageHeader
        title="Playbook"
        subtitle="The canonical sales operating manual. Memorize the script. Drill the objections. Close the deal."
        action={<Tag tone="accent">v3 - canonical</Tag>}
      />

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
        {SECTIONS.map((section, index) => {
          return (
            <Link key={`${section.href}-${index}`} href={section.href} className="group block">
              <Card>
                <div className="flex items-start gap-4">
                  <div className="w-11 h-11 rounded-lg bg-accent-soft border border-accent-muted/30 flex items-center justify-center shrink-0 text-accent font-bold tracking-[0.16em] group-hover:bg-accent group-hover:text-bg transition-all">
                    {(index + 1).toString().padStart(2, "0")}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-fg font-bold text-base group-hover:text-accent transition-colors">
                      {section.title}
                    </div>
                    <div className="text-xs text-fg-muted mt-0.5 uppercase tracking-wider font-medium">
                      {section.subtitle}
                    </div>
                    <p className="text-sm text-fg-muted mt-3 leading-relaxed">{section.body}</p>
                  </div>
                </div>
              </Card>
            </Link>
          );
        })}
      </div>

      {operatingManual.length > 0 && (
        <section className="space-y-4">
          <div>
            <h2 className="text-lg font-bold text-fg">Operating manual</h2>
            <p className="text-sm text-fg-muted">
              Verbatim scripts and deployment runbooks. Read top-to-bottom on the
              call. Don&apos;t paraphrase.
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            {operatingManual.map((file) => (
              <Link
                key={file.slug}
                href={`/playbook/${file.slug}`}
                className="group block"
              >
                <Card>
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="text-fg font-semibold group-hover:text-accent transition-colors">
                        {file.title}
                      </div>
                      <div className="text-[11px] text-fg-dim mt-1 uppercase tracking-wider font-mono">
                        {file.audience} - {file.slug}.md
                      </div>
                    </div>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function SunBizPlaybookIndex({
  manualFiles,
  demoMode = false,
}: {
  manualFiles: PlaybookFile[];
  demoMode?: boolean;
}) {
  const chatHref = demoHref("/agent", { demoMode });
  const renewalsHref = demoHref("/renewals", { demoMode });
  const playbookEntryHref = (slug: string) => demoHref(`/playbook/${slug}`, { demoMode });
  return (
    <div className="space-y-8 animate-fade-in">
      <PageHeader
        title="Playbook"
        subtitle="The guide your team uses to work with Solara day to day."
        action={<Tag tone="engaged">client guide</Tag>}
      />

      <section className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
        <section className="rounded-[28px] border border-amber-300/30 bg-[radial-gradient(circle_at_top_left,rgba(251,191,36,0.2),transparent_34%),linear-gradient(135deg,rgba(24,24,27,0.96),rgba(15,23,42,0.94))] p-6 shadow-[0_24px_80px_-36px_rgba(251,191,36,0.55)]">
          <div className="inline-flex items-center gap-2 rounded-full border border-amber-300/25 bg-amber-300/10 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.18em] text-amber-100">
            <BookOpen className="h-3.5 w-3.5" />
            Unified Onboarding Manual
          </div>
          <h2 className="mt-4 text-3xl font-black tracking-tight text-white">
            Four short pages. One shared operating rhythm.
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-amber-50/80 sm:text-base">
            This is the version your Sun Biz team should actually read. No system language. No setup clutter. Just how to work with Solara, when to review something, when to call CC, and how to pause changes if something feels off.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link href={chatHref} className="btn-send inline-flex items-center gap-2">
              Chat with Solara <MessageSquareText className="h-4 w-4" />
            </Link>
            <Link href={renewalsHref} className="btn-secondary inline-flex items-center gap-2">
              Review renewals <RefreshCcw className="h-4 w-4" />
            </Link>
          </div>
        </section>

        <Card title="Where to start" subtitle="Read these once in order, then keep them nearby.">
          <div className="space-y-3">
            {manualFiles.map((file, index) => {
              const meta = SUN_MANUAL_META[file.slug] || {
                eyebrow: `Step ${(index + 1).toString().padStart(2, "0")}`,
                summary: file.title,
              };
              return (
                <Link
                  key={file.slug}
                  href={playbookEntryHref(file.slug)}
                  className="group flex items-start gap-3 rounded-2xl border border-bg-border bg-bg-elev/35 px-4 py-3 transition-all hover:border-amber-300/35 hover:bg-amber-300/6"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-amber-300/25 bg-amber-300/10 text-xs font-black tracking-[0.16em] text-amber-100">
                    {(index + 1).toString().padStart(2, "0")}
                  </div>
                  <div className="min-w-0">
                    <div className="text-[10px] uppercase tracking-[0.16em] text-fg-dim font-bold">
                      {meta.eyebrow}
                    </div>
                    <div className="mt-1 text-sm font-semibold text-fg group-hover:text-amber-200">
                      {file.title}
                    </div>
                    <div className="mt-1 text-xs leading-6 text-fg-muted">{meta.summary}</div>
                  </div>
                </Link>
              );
            })}
          </div>
        </Card>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {manualFiles.map((file) => {
          const meta = SUN_MANUAL_META[file.slug] || {
            eyebrow: "Guide",
            summary: file.title,
          };
          return (
            <Link key={file.slug} href={playbookEntryHref(file.slug)} className="group block">
              <Card>
                <div className="space-y-3">
                  <div className="inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.16em] font-bold text-amber-200">
                    <Users className="h-3.5 w-3.5" />
                    {meta.eyebrow}
                  </div>
                  <div className="text-fg font-bold text-base group-hover:text-amber-200 transition-colors">
                    {file.title}
                  </div>
                  <p className="text-sm text-fg-muted leading-relaxed">{meta.summary}</p>
                  <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-amber-200">
                    Read now <ArrowRight className="h-3.5 w-3.5" />
                  </div>
                </div>
              </Card>
            </Link>
          );
        })}
      </section>
    </div>
  );
}
