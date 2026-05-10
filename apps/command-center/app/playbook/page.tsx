import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { Phone, Layers, Repeat, FileStack, MessageSquare, Rocket, Network, ShieldCheck } from "lucide-react";

export const dynamic = "force-static";

const SECTIONS = [
  {
    href: "/playbook/script",
    title: "Cold Call Script + Objections",
    subtitle: "5 stages - 4 tracks - 10 objections - secondary disarm",
    icon: Phone,
    body:
      "One memorize-grade page. Pattern interrupt, reason, diagnose, pivot, close. Pick your prospect track at the top and run the right language live. Includes the Agree/Validate/Isolate disarm for when prospects double down on 'we're good'.",
  },
  {
    href: "/playbook/deals",
    title: "Deal Architecture",
    subtitle: "Three offers - two partner paths - one decision rule",
    icon: Layers,
    body:
      "Three client offers, two partner paths, and the canonical 50% strategic-partner model. The math is simple enough to defend in any room.",
  },
  {
    href: "/playbook/drills",
    title: "Daily Drills",
    subtitle: "5 reps - 30 min/day - 90-day discipline",
    icon: Repeat,
    body:
      "Mirror Run, Objection Volley, Recording Review, KPI Log, Weekly Retro. The boring discipline that turns cold calling into muscle memory.",
  },
  {
    href: "/playbook/business",
    title: "Business Documentation",
    subtitle: "CEO + CFO + CMO + Ops + Legal — every doc a real company needs",
    icon: FileStack,
    body:
      "The full hub of business documentation. Manifesto, OKRs, P&L, runway, brand bible, content pillars, MSA template, onboarding SOP, incident runbook. Each pillar owned by the right AI exec — click any doc to ask them to draft or refresh it.",
  },
  {
    href: "/playbook/prompts",
    title: "Prompts Library",
    subtitle: "Saved prompts that move the system — operator + client deployment toolkit",
    icon: MessageSquare,
    body:
      "Reusable prompts for every recurring move. Two audiences: yours (daily ops, system health, [OVERRIDE] syntax) and the client deployment toolkit (setup, voice tune, integration audit, handoff). Foundational prompts are hard-coded; mutable ones can grow as you find new patterns. Click any prompt to drop it straight into chat.",
  },
  {
    href: "/playbook/client-deploy",
    title: "Client Deployment Runbook",
    subtitle: "Six phases · ~60 minutes · the canonical onboarding playbook",
    icon: Rocket,
    body:
      "Your step-by-step runbook for spinning up a fresh client. Pre-flight → bootstrap → personalize → integrations → scope → handoff. Each step has a chat-fire prompt that runs the move automatically. Use this for every new client — same arc, different tenant.",
  },
  {
    href: "/playbook/client-deploy",
    title: "Multi-Machine Setup",
    subtitle: "Pair desktop + laptop · production daemons stay singular · chat-server per machine",
    icon: Network,
    body:
      "Clients with multiple machines (desktop + laptop) pair both bridges to the same dashboard tenant. The dashboard auto-detects which bridge is local. Hard rule: only ONE machine runs scheduler / skool / telegram daemons (state mutators). Every other machine runs ONLY the chat-server. The pair endpoint is idempotent by machine_fingerprint, so re-running rotates tokens instead of creating duplicates. See brain/MULTI_MACHINE_PAIRING_PROMPT.md for the paste-ready Antigravity prompt.",
  },
  {
    href: "/playbook/security",
    title: "Security Model",
    subtitle: "Multi-tenant RLS · AES-256-GCM at rest · SHA-256 bridge tokens · HMAC self-pair",
    icon: ShieldCheck,
    body:
      "How tenant isolation, encryption, and bridge authentication actually work. Every tenant-scoped table is RLS-protected at the Postgres layer. Provider API keys encrypted at rest with AES-256-GCM (scrypt KDF, deploy-wide BRAVO_FIELD_ENCRYPTION_KEY). Bridge tokens are SHA-256 hashed before storage. Self-pair from the daemon uses HMAC headers verified server-side. Migration 030 enforces one live pairing per (tenant, machine_fingerprint) at the DB layer. Read brain/SECURITY_MODEL.md for the full architecture.",
  },
];

export default function PlaybookIndex() {
  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Playbook"
        subtitle="The canonical sales operating manual. Memorize the script. Drill the objections. Close the deal."
        action={<Tag tone="accent">v3 - canonical</Tag>}
      />

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
        {SECTIONS.map((section) => {
          const Icon = section.icon;
          return (
            <Link key={section.href} href={section.href} className="group block">
              <Card>
                <div className="flex items-start gap-4">
                  <div className="w-11 h-11 rounded-lg bg-accent-soft border border-accent-muted/30 flex items-center justify-center shrink-0 group-hover:bg-accent group-hover:text-bg transition-all">
                    <Icon size={20} className="text-accent group-hover:text-bg" />
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
    </div>
  );
}
