import { Card, PageHeader, Tag } from "@/components/Card";
import {
  Database,
  Search,
  ShieldAlert,
  KeyRound,
  Lock,
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from "lucide-react";
import { headers } from "next/headers";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type GuardSummary = {
  mode: string;
  exists: boolean;
  tail_count: number;
  blocked_count: number;
  would_block_count: number;
  by_layer: Record<string, number>;
  last_event_ts: string | null;
  last_decision: string | null;
};

type StateHealthResponse = {
  available: boolean;
  error?: string;
  hint?: string;
  ts?: string;
  v6_mode?: string;
  deploy_target?: string;
  source?: "state-api" | "supabase-mirror";
  state_db?: {
    exists: boolean;
    size_kb?: number;
    agents?: Array<{
      agent: string;
      status: string;
      current_focus: string | null;
      last_heartbeat: string;
      tick_count: number;
      health: string;
    }>;
    session_log_count?: number;
    transaction_count?: number;
    open_tasks_by_bucket?: Record<string, number>;
    last_transaction?: { ts: string; actor: string; op: string; source_script: string };
  };
  index_db?: {
    exists: boolean;
    size_kb?: number;
    sources?: number;
    chunks?: number;
    by_kind?: Record<string, number>;
    last_indexed?: string;
  };
  guards?: {
    exec_guard: GuardSummary;
    secret_guard: GuardSummary;
    state_guard: GuardSummary;
    secret_access?: GuardSummary;
  };
};

async function fetchHealth(): Promise<StateHealthResponse> {
  const hdrs = await headers();
  const host = hdrs.get("host") || "127.0.0.1:3100";
  const proto = hdrs.get("x-forwarded-proto") || "http";
  const url = `${proto}://${host}/api/state-health`;
  try {
    const res = await fetch(url, { cache: "no-store" });
    return (await res.json()) as StateHealthResponse;
  } catch (err) {
    return {
      available: false,
      error: err instanceof Error ? err.message : "fetch failed",
    };
  }
}

function modeBadge(mode: string) {
  const tone: "accent" | "warm" | "neutral" =
    mode === "enforce" ? "accent" :
    mode === "report"  ? "warm"   :
    "neutral";
  return <Tag tone={tone}>{mode}</Tag>;
}

function modeIcon(mode: string) {
  if (mode === "enforce") return <CheckCircle2 size={16} className="text-status-engaged" />;
  if (mode === "report")  return <AlertTriangle size={16} className="text-status-hot" />;
  return <XCircle size={16} className="text-fg-faint" />;
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  const diff = Date.now() - t;
  if (diff < 60_000)        return `${Math.round(diff / 1000)}s ago`;
  if (diff < 3_600_000)     return `${Math.round(diff / 60_000)}m ago`;
  if (diff < 86_400_000)    return `${Math.round(diff / 3_600_000)}h ago`;
  return `${Math.round(diff / 86_400_000)}d ago`;
}

export default async function SystemHealthPage() {
  const data = await fetchHealth();

  // When state-api isn't reachable from this deploy AND v6 mode is off
  // (the default in production), the rest of the page would render with
  // empty/OFF cards that look like errors — they're not, they're just
  // "local-only services that this cloud deploy can't see." Early-return
  // with a single honest panel so CC doesn't read empty cards as broken.
  const offlineLocalGuards = !data.available && (data.v6_mode === "off" || !data.v6_mode);

  if (offlineLocalGuards) {
    return (
      <div className="space-y-6 animate-fade-in">
        <PageHeader
          title="System Health & Guardrails"
          subtitle="Local-machine guard substrate (V6.0). Off by design on this cloud deploy — the live stats render here only when the state-api daemon is running on your machine."
          action={modeBadge("off")}
        />
        <Card>
          <div className="flex items-start gap-3 p-2">
            <Activity size={20} className="text-fg-dim shrink-0 mt-0.5" />
            <div className="flex-1">
              <div className="font-bold text-fg">Local guard substrate not active here</div>
              <p className="text-sm text-fg-muted mt-1 leading-relaxed">
                These guardrails (Bash Sandbox, Credential Vault, State Mirror Lock) and the
                FTS5 memory retriever run as Python processes on the operator&apos;s machine,
                not on Vercel. The cloud dashboard surfaces their stats only when the
                <code className="text-accent mx-1">state-api</code> daemon is reachable from
                this deploy. On the public Vercel deployment that&apos;s expected to be off —
                guards run locally; this page just visualizes them.
              </p>
              <p className="text-sm text-fg-muted mt-2 leading-relaxed">
                To turn this view on, start the FastAPI service on the operator machine.
                It runs as the <code className="text-accent">state-api</code> container in
                the local compose stack:
              </p>
              <code className="text-xs text-accent font-mono block mt-2 p-2 bg-bg-elev rounded border border-bg-border">
                docker compose -f infra/docker-compose.local.yml up -d state-api
              </code>
              {data.error && (
                <p className="text-xs text-fg-faint mt-3 font-mono">
                  Last fetch error: {data.error}
                </p>
              )}
            </div>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="System Health & Guardrails"
        subtitle={`V6.0 transactional state, FTS5 retrieval, and the three hook guards. ${
          data.deploy_target ? `Target: ${data.deploy_target}.` : ""
        } ${data.v6_mode ? `Mode: ${data.v6_mode}.` : ""} ${
          data.source === "supabase-mirror"
            ? "Source: Supabase mirror (state-api not reachable from this deploy)."
            : data.source === "state-api"
              ? "Source: state-api (canonical)."
              : ""
        }`}
        action={
          <div className="flex items-center gap-2">
            {data.source && (
              <Tag tone={data.source === "state-api" ? "accent" : "warm"}>
                {data.source === "state-api" ? "via state-api" : "via supabase-mirror"}
              </Tag>
            )}
            {modeBadge(data.v6_mode || "off")}
          </div>
        }
      />

      {!data.available && (
        <Card>
          <div className="flex items-start gap-3 p-2">
            <AlertTriangle size={20} className="text-status-hot shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-fg">state-api unreachable</div>
              <p className="text-sm text-fg-muted mt-1">{data.error}</p>
              {data.hint && (
                <code className="text-xs text-accent font-mono block mt-2 p-2 bg-bg-elev rounded border border-bg-border">
                  {data.hint}
                </code>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* ── Empire State DB ────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Database size={16} className="text-accent" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-fg-muted">
            Empire State DB
          </h2>
        </div>
        {data.state_db?.exists ? (
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <div className="text-xs text-fg-dim uppercase tracking-wider">Session log rows</div>
              <div className="text-2xl font-bold text-fg mt-1">
                {data.state_db.session_log_count?.toLocaleString() ?? 0}
              </div>
            </Card>
            <Card>
              <div className="text-xs text-fg-dim uppercase tracking-wider">Audit transactions</div>
              <div className="text-2xl font-bold text-fg mt-1">
                {data.state_db.transaction_count?.toLocaleString() ?? 0}
              </div>
            </Card>
            <Card>
              <div className="text-xs text-fg-dim uppercase tracking-wider">Open tasks</div>
              <div className="text-2xl font-bold text-fg mt-1">
                {Object.values(data.state_db.open_tasks_by_bucket || {}).reduce((a, b) => a + b, 0)}
              </div>
            </Card>
            <Card>
              <div className="text-xs text-fg-dim uppercase tracking-wider">DB size</div>
              <div className="text-2xl font-bold text-fg mt-1">
                {data.state_db.size_kb?.toFixed(0) ?? "—"} KB
              </div>
            </Card>
          </div>
        ) : (
          <Card>
            <div className="text-sm text-fg-muted p-2">
              <code className="text-accent">state/empire_state.db</code> does not exist yet. Run{" "}
              <code className="text-accent">python scripts/state_manager.py heartbeat</code> to bootstrap.
            </div>
          </Card>
        )}

        {data.state_db?.agents && data.state_db.agents.length > 0 && (
          <Card className="mt-4">
            <div className="text-xs text-fg-dim uppercase tracking-wider mb-3">Agents</div>
            <div className="space-y-2">
              {data.state_db.agents.map((a) => (
                <div key={a.agent} className="flex items-center gap-3 text-sm">
                  <span className={`w-2 h-2 rounded-full ${
                    a.health === "green" ? "bg-status-engaged" :
                    a.health === "yellow" ? "bg-status-hot" : "bg-fg-faint"
                  }`} />
                  <span className="font-bold text-fg uppercase tracking-wider w-16">{a.agent}</span>
                  <span className="text-fg-muted">{a.status}</span>
                  <span className="text-fg-faint text-xs ml-auto">
                    tick {a.tick_count} · {relativeTime(a.last_heartbeat)}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>

      {/* ── Guard hooks ────────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <ShieldAlert size={16} className="text-accent" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-fg-muted">
            PreToolUse Guards (24h tail)
          </h2>
        </div>
        <div className="grid md:grid-cols-3 gap-4">
          <GuardCard
            name="exec_guard"
            title="Bash Sandbox"
            icon={Lock}
            description="Blocks DROP, DELETE-no-WHERE, ALTER DROP COLUMN, rm -rf /, force-push to main, fork bombs."
            data={data.guards?.exec_guard}
          />
          <GuardCard
            name="secret_guard"
            title="Credential Vault"
            icon={KeyRound}
            description=".env.agents and friends are not LLM-readable. Blocks Read + cat/grep/sed/awk on secret paths."
            data={data.guards?.secret_guard}
          />
          <GuardCard
            name="state_guard"
            title="State Mirror Lock"
            icon={Database}
            description="Blocks Edit on auto-generated state mirrors so hand-edits don't get clobbered by export."
            data={data.guards?.state_guard}
          />
        </div>
      </div>

      {/* ── Retriever ──────────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Search size={16} className="text-accent" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-fg-muted">
            FTS5 Memory Retriever
          </h2>
        </div>
        <div className="grid md:grid-cols-4 gap-4">
          <Card>
            <div className="text-xs text-fg-dim uppercase tracking-wider">Sources</div>
            <div className="text-2xl font-bold text-fg mt-1">{data.index_db?.sources ?? "—"}</div>
          </Card>
          <Card>
            <div className="text-xs text-fg-dim uppercase tracking-wider">Chunks</div>
            <div className="text-2xl font-bold text-fg mt-1">
              {data.index_db?.chunks?.toLocaleString() ?? "—"}
            </div>
          </Card>
          <Card>
            <div className="text-xs text-fg-dim uppercase tracking-wider">Index size</div>
            <div className="text-2xl font-bold text-fg mt-1">
              {data.index_db?.size_kb?.toFixed(0) ?? "—"} KB
            </div>
          </Card>
          <Card>
            <div className="text-xs text-fg-dim uppercase tracking-wider">Last reindex</div>
            <div className="text-2xl font-bold text-fg mt-1">
              {relativeTime(data.index_db?.last_indexed)}
            </div>
          </Card>
        </div>
        {data.index_db?.by_kind && (
          <div className="mt-3 text-xs text-fg-muted flex flex-wrap gap-3">
            {Object.entries(data.index_db.by_kind).map(([kind, n]) => (
              <span key={kind}>
                <span className="text-fg-dim uppercase tracking-wider">{kind}</span>{" "}
                <span className="text-fg font-mono">{n}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Last transaction ──────────────────────────────────────────── */}
      {data.state_db?.last_transaction && (
        <Card>
          <div className="flex items-center gap-2 mb-2">
            <Activity size={14} className="text-fg-dim" />
            <div className="text-xs text-fg-dim uppercase tracking-wider">Last DB Transaction</div>
          </div>
          <div className="font-mono text-sm text-fg">
            <span className="text-accent">{data.state_db.last_transaction.op}</span>
            <span className="text-fg-muted"> by </span>
            <span className="text-fg">{data.state_db.last_transaction.actor}</span>
            <span className="text-fg-muted"> via </span>
            <span className="text-fg">{data.state_db.last_transaction.source_script}</span>
          </div>
          <div className="text-xs text-fg-faint mt-1">
            {relativeTime(data.state_db.last_transaction.ts)}
          </div>
        </Card>
      )}
    </div>
  );
}

function GuardCard({
  name,
  title,
  icon: Icon,
  description,
  data,
}: {
  name: string;
  title: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  description: string;
  data?: GuardSummary;
}) {
  const mode = data?.mode || "off";
  return (
    <Card>
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg bg-accent-soft border border-accent-muted/30 flex items-center justify-center shrink-0">
          <Icon size={18} className="text-accent" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <div className="font-bold text-fg">{title}</div>
            <div className="flex items-center gap-1.5">
              {modeIcon(mode)}
              {modeBadge(mode)}
            </div>
          </div>
          <div className="text-xs text-fg-dim mt-0.5 font-mono">{name}</div>
          <p className="text-xs text-fg-muted mt-2 leading-relaxed">{description}</p>
          {data && (
            <div className="mt-3 pt-3 border-t border-bg-border space-y-1 text-xs">
              <div className="flex justify-between text-fg-muted">
                <span>Blocked</span>
                <span className="font-mono text-fg">{data.blocked_count}</span>
              </div>
              <div className="flex justify-between text-fg-muted">
                <span>Would-block (report)</span>
                <span className="font-mono text-fg">{data.would_block_count}</span>
              </div>
              <div className="flex justify-between text-fg-muted">
                <span>Last event</span>
                <span className="font-mono text-fg">{relativeTime(data.last_event_ts)}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
