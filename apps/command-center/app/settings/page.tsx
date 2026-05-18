import Link from "next/link";
import { Card, PageHeader, Tag, EmptyState } from "@/components/Card";
import { IntegrationDot } from "@/components/IntegrationDot";
import {
  getActiveProfile,
  integrationsHealth,
  getTenant,
  getPlanTemplates,
  aiServicesWithKey,
  getBridgeOnline,
} from "@/lib/queries";
import { safe } from "@/lib/api-helpers";
import { ChangePasswordForm } from "@/components/ChangePasswordForm";
import { ProfileEditor } from "@/components/settings/ProfileEditor";
import { BrandLogoCard } from "@/components/settings/BrandLogoCard";
import { QuickInviteCard } from "@/components/settings/QuickInviteCard";
import { PlanTemplateEditor } from "@/components/settings/PlanTemplateEditor";
import { AgentConfigEditor } from "@/components/settings/AgentConfigEditor";
import { MyAgentsCard } from "@/components/settings/MyAgentsCard";
import { DevicesEditor } from "@/components/settings/DevicesEditor";
import { ProviderAccountsCard } from "@/components/settings/ProviderAccountsCard";
import { LocalCliProvidersCard } from "@/components/settings/LocalCliProvidersCard";
import { TOOL_DEFINITIONS } from "@/lib/cloud-tool-runner";
import { chatAgentKeys } from "@/lib/agent-personas";
import { resolveClientProfileSlug } from "@/lib/client-profiles";
import { getManifest } from "@/lib/manifest/loader";
import { visibleIntegrationsForTenant } from "@/lib/integrations-registry";
import { resolveAgentKey } from "@/lib/agents";
import { isOperatorEmail } from "@/lib/operator-credentials";
import { getSessionUser } from "@/lib/supabase-server";
import type { IntegrationHealth } from "@/lib/supabase";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const profile = await safe("settings.profile", getActiveProfile(), null);
  const [integrations, tenant, templates, connectedAiSet, user, bridgeOnline] = await Promise.all([
    safe("settings.integrations_health", integrationsHealth(profile?.tenant_id || null), []),
    profile?.tenant_id ? safe("settings.tenant", getTenant(profile.tenant_id), null) : Promise.resolve(null),
    profile ? safe("settings.plan_templates", getPlanTemplates(profile.id), []) : Promise.resolve([]),
    safe("settings.ai_keys", aiServicesWithKey(profile?.tenant_id || null), new Set<string>()),
    getSessionUser().catch(() => null),
    safe("settings.bridge_online", getBridgeOnline(profile?.tenant_id ?? null), false),
  ]);
  const weekday = templates.find((t) => t.kind === "weekday") || null;
  const weekend = templates.find((t) => t.kind === "weekend") || null;

  // Load the tenant's manifest so the Settings page can render tenant-
  // specific blocks (compliance posture, brand). Falls back gracefully if
  // the slug can't be resolved or the manifest load errors — Settings still
  // renders, the compliance card just stays hidden.
  const manifestSlug = tenant ? resolveClientProfileSlug(tenant) : null;
  const manifest = manifestSlug
    ? await safe("settings.manifest", getManifest(manifestSlug), null)
    : null;

  // Tenant-aware integration visibility. Show only what this tenant's
  // enabled agents actually need + AI providers (no used_by). Operators
  // (OASIS) see everything including platform infra (Vercel, Cloudflare,
  // GitHub, etc.). Client tenants only see what their agent mix exposes —
  // re-enable an agent later and the integrations grow back.
  const enabledAgents = (profile?.agents_enabled || []).map(resolveAgentKey);
  const enabledChatAgentKeys = chatAgentKeys().filter((k) =>
    ((profile?.agents_enabled || chatAgentKeys()).map(resolveAgentKey)).includes(k),
  );
  const isOperator = isOperatorEmail(user?.email || undefined);
  const teamProfile = profile as (typeof profile & { is_owner?: boolean; team_role?: string }) | null;
  const canManageTenant =
    !!teamProfile &&
    (teamProfile.is_owner || teamProfile.team_role === "owner" || teamProfile.team_role === "admin");
  const visibleDefs = visibleIntegrationsForTenant(enabledAgents, { isOperator });
  const visibleServices = new Set(visibleDefs.map((d) => d.service));
  const visibleIntegrations = integrations.filter((h: IntegrationHealth) => visibleServices.has(h.service));

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader title="Settings" subtitle="Profile, password, plan templates, integrations." />

      {!profile ? (
        <Card title="No profile loaded">
          <EmptyState message="Sign in to edit your profile." />
        </Card>
      ) : (
        <>
          <Card
            title="Profile"
            subtitle={`Signed in as ${profile.email}`}
            action={
              <div className="flex items-center gap-2">
                {tenant && (
                  <Tag tone={tenant.purchase_status === "active" ? "engaged" : "warm"}>
                    {tenant.plan_tier} · {tenant.purchase_status}
                  </Tag>
                )}
                <a
                  href="/onboarding/welcome"
                  className="text-xs text-accent hover:text-accent/80 underline underline-offset-2"
                  title="Re-open the personalisation wizard to edit timezone / default agent / briefing channel"
                >
                  Open personalisation wizard →
                </a>
                {canManageTenant && (
                  <a
                    href="/settings/audit-log"
                    className="text-xs text-accent hover:text-accent/80 underline underline-offset-2"
                  >
                    Audit log →
                  </a>
                )}
              </div>
            }
          >
            <ProfileEditor profile={profile} />
          </Card>

          <Card
            title="Branding"
            subtitle="Your logo is applied to every new form, public application page, and anywhere else the dashboard shows your brand."
          >
            <BrandLogoCard
              initialLogoUrl={tenant?.logo_url ?? null}
              canManage={canManageTenant}
            />
          </Card>

          {canManageTenant && (
            <Card
              title="Team"
              subtitle="Invite teammates so they can sign into this tenant. Each invite is a one-time link — send it via Slack / email / SMS."
              action={
                <a
                  href="/team"
                  className="inline-flex items-center gap-1 text-xs text-accent hover:text-accent-bright"
                >
                  Manage team & invites →
                </a>
              }
            >
              <QuickInviteCard />
              <p className="text-[11px] text-fg-dim leading-relaxed mt-3">
                Invitees land on /invite/&lt;token&gt;, sign up, and join
                this tenant automatically. Solara recognizes them by name
                and respects their role.
              </p>
            </Card>
          )}

          <Card title="Password" subtitle="Change your sign-in password">
            <ChangePasswordForm />
          </Card>

          {/* Devices — operator/admin can pair THEIR machine to run the
              local bridge. Tenant admins need this too so they can give
              their agents full Claude-Code-class capability without
              waiting on the empire operator. Non-admin employees still
              don't see it. */}
          {canManageTenant && (
            <Card
              title="Devices (advanced)"
              subtitle="Pair a machine on your network to run the local bridge — gives your agents file-system, bash, and full MCP access. Optional: a connected AI provider account below is enough for chat without ever pairing a machine."
              action={
                <Link
                  href="/settings/devices/install"
                  className="inline-flex items-center gap-1 rounded-lg bg-accent text-bg-deep px-3 py-1.5 text-xs font-bold hover:bg-accent-bright"
                >
                  Pair a machine →
                </Link>
              }
            >
              <DevicesEditor />
            </Card>
          )}

          {/* Compliance posture card removed — TCPA rules now live in the
              manifest editor only. The Settings page never edited them
              anyway and the read-only summary was noise. */}
          {/* Top-level "Connect a provider" surface. Lives ABOVE the
              per-agent Agents card so the very first thing operators see
              under Settings is the provider-account grid. The per-agent
              paste-key UX is one click away (anchor #agents). */}
          <Card
            id="providers"
            title="AI provider accounts"
            subtitle={
              canManageTenant
                ? "Connect at least one AI account so your agents can think. OpenRouter is the easiest — one key powers every model. Anthropic Direct, OpenAI Direct, and Google Gemini are the per-vendor paths if you prefer."
                : "These are the team's AI accounts. Your admin connects them once — your chats will route through whichever account they pick."
            }
          >
            <ProviderAccountsCard
              connectedServices={connectedAiSet}
              bridgeOnline={bridgeOnline}
              canManageTeam={canManageTenant}
            />
          </Card>

          {/* Local CLI detection probes the bridge daemon which is
              machine-specific. For tenant operators it surfaces the
              operator's (CC's) machine state, which is both confusing
              and a leak. Empire-only. */}
          {isOperator && <LocalCliProvidersCard />}

          <Card
            id="agents"
            title="Per-agent overrides"
            subtitle="Optional. By default every enabled agent uses the team AI provider account from above. Use this card only if a specific agent needs a different model or its OWN key (e.g., Solara on Claude Sonnet but Helios on GPT-5). Leave a row alone to inherit the team default."
            action={
              <Tag tone={bridgeOnline ? "engaged" : "neutral"}>
                {bridgeOnline ? "Tool access: bridge online" : "Tool access: cloud only"}
              </Tag>
            }
          >
            {canManageTenant ? (
              <AgentConfigEditor
                agentKeys={enabledChatAgentKeys}
                bridgeOnline={bridgeOnline}
                agentPalettes={Object.fromEntries(
                  (manifest?.agents || []).map((a) => [
                    a.slug.toLowerCase(),
                    a.tool_palette,
                  ])
                )}
                manifestSlug={manifestSlug}
                // Slim catalog for the per-agent palette editor. Server-side
                // TOOL_DEFINITIONS contains the full input_schema JSON which
                // the client UI doesn't need; we pass name + description +
                // defer flag (for grouping into Cloud vs Bridge sections).
                toolCatalog={TOOL_DEFINITIONS.map((t) => ({
                  name: t.name,
                  description: t.description,
                  defer: !!t.defer,
                }))}
              />
            ) : (
              <EmptyState message="Team-wide model defaults are managed by an owner or admin. Scroll down to 'Use my own AI keys (just for me)' if you'd rather plug in your own AI account." />
            )}
          </Card>

          <MyAgentsCard
            enabledAgentKeys={enabledChatAgentKeys}
            agentLabels={Object.fromEntries(
              (manifest?.agents || []).map((a) => [
                a.slug.toLowerCase(),
                a.display_name || a.slug,
              ]),
            )}
          />

          <Card
            title="Weekday template"
            subtitle="Monday–Friday recurring schedule. Materializes nightly via cron."
          >
            <PlanTemplateEditor kind="weekday" existing={weekday} />
          </Card>

          <Card
            title="Weekend template"
            subtitle="Saturday + Sunday recurring schedule"
          >
            <PlanTemplateEditor kind="weekend" existing={weekend} />
          </Card>

          <Card
            title="Integrations"
            subtitle={
              isOperator
                ? "Health across every connected system (operator view — includes platform infra). Open the Integrations page for the full setup grid."
                : "Health across the systems your enabled agents actually use. Enable more agents to unlock additional integrations."
            }
          >
            <div className="grid sm:grid-cols-2 gap-3">
              {visibleIntegrations.map((h: IntegrationHealth) => (
                <IntegrationDot
                  key={h.service}
                  health={h}
                  connection={{ hasCredentials: connectedAiSet.has(h.service) }}
                />
              ))}
              {visibleIntegrations.length === 0 && (
                <div className="col-span-full text-sm text-fg-muted">
                  No integrations active for your current agent set. Enable an agent above to see what they need.
                </div>
              )}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
