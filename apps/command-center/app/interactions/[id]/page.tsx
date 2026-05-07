/**
 * /interactions/[id] — full detail view of one lead_interactions row.
 *
 * Surfaces what's in metadata.classification (intent/agent_action/summary/
 * priority/agent_label) plus the email body, sender, lead linkage, raw
 * metadata for debugging. Tenant-scoped.
 */

import { notFound, redirect } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, AlertCircle, ExternalLink, Mail, MessageSquare, Phone } from "lucide-react";
import { Card, PageHeader, Tag } from "@/components/Card";
import { getActiveProfile } from "@/lib/queries";
import { getServiceSupabase } from "@/lib/supabase-server";
import { timeAgo, truncate } from "@/lib/fmt";
import type { LeadInteraction } from "@/lib/supabase";

export const dynamic = "force-dynamic";

type Lead = {
  id: string;
  name: string | null;
  email: string | null;
  company: string | null;
  status: string | null;
  score: number | null;
  source: string | null;
};

function channelIcon(channel: string) {
  if (channel === "email") return <Mail className="w-4 h-4" />;
  if (channel === "dm" || channel === "linkedin") return <MessageSquare className="w-4 h-4" />;
  if (channel === "call") return <Phone className="w-4 h-4" />;
  return <Mail className="w-4 h-4" />;
}

function intentTone(intent: string): "engaged" | "hot" | "warm" | "neutral" | "accent" {
  const i = intent.toLowerCase();
  if (i === "hot_lead" || i === "frustrated") return "hot";
  if (i === "sales" || i === "business_opportunity" || i === "partnership") return "engaged";
  if (i === "strategic" || i === "pricing_question") return "accent";
  if (i === "ambiguous" || i === "security") return "warm";
  return "neutral";
}

export default async function InteractionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!id || !/^[0-9a-f-]{36}$/i.test(id)) notFound();

  const profile = await getActiveProfile().catch(() => null);
  if (!profile?.tenant_id) redirect("/login?next=/interactions/" + id);

  const db = getServiceSupabase();
  const { data: row } = await db
    .from("lead_interactions")
    .select("*")
    .eq("id", id)
    .eq("tenant_id", profile.tenant_id)
    .maybeSingle();

  if (!row) notFound();
  const interaction = row as LeadInteraction;

  let lead: Lead | null = null;
  if (interaction.lead_id) {
    const { data: l } = await db
      .from("leads")
      .select("id, name, email, company, status, score, source")
      .eq("id", interaction.lead_id)
      .maybeSingle();
    lead = (l as Lead) || null;
  }

  const meta = (interaction.metadata || {}) as Record<string, unknown>;
  const classification = (meta.classification || {}) as Record<string, unknown>;
  const isInbound = ["email_received", "email_reply", "dm_received"].includes(interaction.type);
  const isOutbound = ["email_sent", "dm_sent", "linkedin_sent", "call_made"].includes(interaction.type);
  const fromIdentity = (meta.from_identity || meta.from_name || meta.from_email || "—") as string;

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center gap-2">
        <Link
          href={isInbound ? "/" : "/pipeline"}
          className="text-fg-muted hover:text-accent text-sm inline-flex items-center gap-1.5 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Back to {isInbound ? "Today" : "Pipeline"}
        </Link>
      </div>

      <PageHeader
        title={truncate(interaction.subject || "(no subject)", 80)}
        subtitle={
          <span className="inline-flex items-center gap-2">
            {channelIcon(interaction.channel)}
            <span>{interaction.type}</span>
            <span>·</span>
            <span>{timeAgo(interaction.created_at)}</span>
            {interaction.agent_source && (
              <>
                <span>·</span>
                <span className="font-mono">{interaction.agent_source}</span>
              </>
            )}
          </span>
        }
        action={
          <Tag tone={isInbound ? "accent" : "engaged"}>{isInbound ? "inbound" : isOutbound ? "outbound" : "interaction"}</Tag>
        }
      />

      {/* Classification — only when present */}
      {Object.keys(classification).length > 0 && (
        <Card title="Classification" subtitle="From the n8n inbound qualifier or send_gateway">
          <div className="grid sm:grid-cols-2 gap-3">
            {classification.intent !== undefined && (
              <Field label="Intent">
                <Tag tone={intentTone(String(classification.intent))}>
                  {String(classification.intent)}
                </Tag>
              </Field>
            )}
            {classification.priority !== undefined && (
              <Field label="Priority">
                <Tag
                  tone={
                    String(classification.priority) === "high"
                      ? "hot"
                      : String(classification.priority) === "low"
                        ? "neutral"
                        : "warm"
                  }
                >
                  {String(classification.priority)}
                </Tag>
              </Field>
            )}
            {classification.agent_action !== undefined && (
              <Field label="Agent action">
                <span className="font-mono text-sm text-fg">{String(classification.agent_action)}</span>
              </Field>
            )}
            {classification.agent_label !== undefined && (
              <Field label="Agent owner">
                <span className="font-bold uppercase tracking-wider text-sm text-accent">
                  {String(classification.agent_label)}
                </span>
              </Field>
            )}
            {classification.sentiment !== undefined && (
              <Field label="Sentiment">
                <span className="text-sm text-fg">{String(classification.sentiment)}</span>
              </Field>
            )}
            {classification.confidence !== undefined && (
              <Field label="Confidence">
                <span className="text-sm font-mono text-fg">
                  {Number(classification.confidence).toFixed(2)}
                </span>
              </Field>
            )}
          </div>
          {classification.summary !== undefined && String(classification.summary).trim().length > 0 && (
            <div className="mt-4 pt-4 border-t border-bg-border">
              <div className="text-[11px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-1.5">
                Agent summary
              </div>
              <div className="text-sm text-fg leading-relaxed">{String(classification.summary)}</div>
            </div>
          )}
          {classification.notes !== undefined && String(classification.notes).trim().length > 0 && (
            <div className="mt-4 pt-4 border-t border-bg-border">
              <div className="text-[11px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-1.5">
                Classifier notes
              </div>
              <div className="text-sm text-fg-muted leading-relaxed">
                {String(classification.notes)}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Email envelope */}
      <Card title="Envelope">
        <div className="grid sm:grid-cols-[8rem_1fr] gap-y-2 text-sm">
          <span className="text-fg-muted">{isInbound ? "From" : "To"}</span>
          <span className="font-mono text-fg break-all">{fromIdentity}</span>

          <span className="text-fg-muted">Subject</span>
          <span className="text-fg">{interaction.subject || "(no subject)"}</span>

          <span className="text-fg-muted">Channel</span>
          <span className="text-fg">{interaction.channel}</span>

          <span className="text-fg-muted">When</span>
          <span className="text-fg">
            {new Date(interaction.created_at).toLocaleString("en-CA", {
              dateStyle: "long",
              timeStyle: "short",
            })}
          </span>

          {meta.message_id ? (
            <>
              <span className="text-fg-muted">Message ID</span>
              <span className="font-mono text-xs text-fg-dim break-all">{String(meta.message_id)}</span>
            </>
          ) : null}
        </div>
      </Card>

      {/* Body */}
      {interaction.content && (
        <Card title="Body">
          <pre className="text-sm text-fg whitespace-pre-wrap leading-relaxed font-sans">
            {interaction.content}
          </pre>
        </Card>
      )}

      {/* Linked lead */}
      {lead && (
        <Card
          title="Linked lead"
          subtitle={`${lead.status || "no status"} · score ${lead.score ?? "—"} · source ${lead.source || "—"}`}
          action={
            <Link
              href={`/pipeline?show=all`}
              className="text-xs text-accent hover:text-accent-bright inline-flex items-center gap-1"
            >
              Open in pipeline <ExternalLink className="w-3 h-3" />
            </Link>
          }
        >
          <div className="space-y-1">
            <div className="text-fg font-bold">{lead.name || "(unnamed)"}</div>
            {lead.company && <div className="text-fg-muted text-sm">{lead.company}</div>}
            {lead.email && (
              <div className="text-fg-dim text-xs font-mono break-all">{lead.email}</div>
            )}
          </div>
        </Card>
      )}

      {/* Raw metadata — for debugging when something looks off */}
      <Card title="Raw metadata" subtitle="Full row payload for debugging">
        <pre className="text-[11px] text-fg-dim font-mono leading-relaxed overflow-x-auto">
          {JSON.stringify({ ...interaction, content: undefined }, null, 2)}
        </pre>
      </Card>

      {!interaction.content && !classification.summary && (
        <div className="rounded-md border border-status-warm/40 bg-status-warm/10 p-3 text-sm text-status-warm flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <div>
            This row has no body or classifier summary. The n8n workflow may have written
            the row with metadata only, or the classifier didn&apos;t emit an{" "}
            <code>oasis-routing</code> block. Check the agent&apos;s system prompt.
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-1">
        {label}
      </div>
      <div>{children}</div>
    </div>
  );
}
