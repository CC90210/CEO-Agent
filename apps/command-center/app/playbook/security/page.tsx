import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import {
  ArrowLeft,
  ShieldCheck,
  Database,
  KeyRound,
  Network,
  Eye,
  AlertTriangle,
} from "lucide-react";

export const dynamic = "force-static";

/**
 * /playbook/security — operator-facing summary of the security model.
 *
 * Mirror of brain/SECURITY_MODEL.md but in dashboard form so an operator
 * can answer "is this safe for my client?" without opening Obsidian.
 * Full architecture detail + verification commands live in the brain doc.
 */

type Section = {
  title: string;
  subtitle: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  body: React.ReactNode;
};

const SECTIONS: Section[] = [
  {
    title: "Multi-tenant isolation",
    subtitle: "One shared Supabase. RLS at every row that matters.",
    icon: Database,
    body: (
      <>
        <p>
          Every paying client uses the same dashboard URL and the same
          Supabase project ({" "}<code className="text-accent">phctllmtsogkovoilwos</code>).
          Isolation is enforced at the Postgres layer via Row-Level
          Security policies on every tenant-scoped table.
        </p>
        <p>
          API routes resolve <code className="text-accent">tenant_id</code>{" "}
          server-side from the auth cookie or bridge token — never from
          request body. Reviewers grep new routes for{" "}
          <code className="text-accent">.from(...)</code> without a nearby{" "}
          <code className="text-accent">.eq(&quot;tenant_id&quot;, ...)</code>{" "}
          filter; that&apos;s the contract.
        </p>
        <p className="text-xs text-fg-dim">
          RLS coverage verified 2026-05-09: 7 migration files spanning
          every tenant-scoped table (chat_sessions, agent_model_config,
          bridge_pairings, leads, mrr_snapshots, agent_events, etc.).
        </p>
      </>
    ),
  },
  {
    title: "Encryption at rest",
    subtitle: "AES-256-GCM with scrypt KDF. Master key in Vercel only.",
    icon: KeyRound,
    body: (
      <>
        <p>
          Provider API keys (Anthropic, OpenAI, Stripe, etc.) that
          clients paste into Settings get encrypted before storage.
          Algorithm: AES-256-GCM (authenticated — tampering is detected).
          KDF: <code className="text-accent">scryptSync</code> with a
          fixed deploy-wide salt. Master secret:{" "}
          <code className="text-accent">BRAVO_FIELD_ENCRYPTION_KEY</code>{" "}
          env var, set on Vercel only, minimum 16 chars.
        </p>
        <p>
          On-disk format:{" "}
          <code className="text-accent">
            base64(iv).base64(authTag).base64(ciphertext)
          </code>
          . Stored in <code className="text-accent">agent_model_config.encrypted_api_key</code>.
        </p>
        <p className="text-xs text-fg-dim">
          File: <code className="text-accent">apps/command-center/lib/field-encryption.ts</code>.
          Rotating BRAVO_FIELD_ENCRYPTION_KEY orphans every stored
          ciphertext — treated as a master secret, set once.
        </p>
      </>
    ),
  },
  {
    title: "Bridge token lifecycle",
    subtitle: "Mint → SHA-256 hash → store. Idempotent rotation by fingerprint.",
    icon: Network,
    body: (
      <>
        <p>
          Each paired machine gets an <code className="text-accent">oab_&lt;32-byte-hex&gt;</code>{" "}
          bearer token, SHA-256 hashed before storage in{" "}
          <code className="text-accent">bridge_pairings.bridge_token_hash</code>.
          Plaintext returned to the daemon once and stored at{" "}
          <code className="text-accent">~/.oasis/bridge_token</code> (chmod 600 on Unix).
        </p>
        <p>
          The pair endpoint is now <strong className="text-fg">idempotent by{" "}
          <code className="text-accent">(tenant_id, machine_fingerprint)</code></strong>{" "}
          — re-pairing rotates the token on the existing row instead of
          creating duplicates. Migration 030 enforces this at the DB
          level via a partial unique index{" "}
          <code className="text-accent">WHERE revoked_at IS NULL</code>.
          Race-safe: any concurrent insert that would create a duplicate
          gets rejected with PostgreSQL code 23505 and the route falls
          into the rotate path.
        </p>
        <p>
          Revocation: set <code className="text-accent">revoked_at</code>{" "}
          non-null. <code className="text-accent">/api/bridge/ping</code>{" "}
          returns 403 immediately; the dashboard{" "}
          <Link href="/operations" className="text-accent hover:text-accent-bright">
            /operations
          </Link>{" "}
          page filters revoked rows.
        </p>
      </>
    ),
  },
  {
    title: "HMAC self-pair",
    subtitle: "Per-profile shared secret. Constant-time compare server-side.",
    icon: ShieldCheck,
    body: (
      <>
        <p>
          The bridge daemon doesn&apos;t have CC&apos;s wizard-side
          credentials — it bootstraps itself via HMAC headers{" "}
          (<code className="text-accent">x-oasis-profile-id</code> +{" "}
          <code className="text-accent">x-oasis-secret</code>). The
          secret is per-profile, issued by{" "}
          <code className="text-accent">scripts/n8n_webhook_secret.py issue --save-env</code>,{" "}
          SHA-256 hashed before storage.
        </p>
        <p>
          Verification (<code className="text-accent">_hmacAuthEmail()</code>{" "}
          in the pair route): pulls the row by{" "}
          <code className="text-accent">profile_id</code> first, then uses{" "}
          <code className="text-accent">crypto.timingSafeEqual</code> to
          compare hashes — eliminates the timing side-channel from
          SQL-level equality. Length-mismatch returns null safely.
        </p>
      </>
    ),
  },
  {
    title: "Audit trail",
    subtitle: "Every cron, every chat, every pair. Tenant-scoped.",
    icon: Eye,
    body: (
      <>
        <p>
          The <code className="text-accent">agent_events</code> table
          captures every cron fire, agent reasoning loop, outbound send,
          and inbound webhook classification. Visible in real-time at{" "}
          <Link href="/operations" className="text-accent hover:text-accent-bright">
            /operations
          </Link>{" "}
          → Activity Tape. Tenant-scoped via RLS.
        </p>
        <p>
          Bridge log: <code className="text-accent">~/.oasis/bridge.log</code>{" "}
          on the operator&apos;s machine. Captures every heartbeat,
          chat-server start/stop, pair attempt. Local only — never
          transmitted to the dashboard.
        </p>
      </>
    ),
  },
  {
    title: "Out of scope (and why)",
    subtitle: "What we don't defend against, with rationale.",
    icon: AlertTriangle,
    body: (
      <>
        <p>
          <strong className="text-fg">Host compromise</strong> on the
          operator&apos;s machine — if an attacker has root/admin on
          their laptop, they can read{" "}
          <code className="text-accent">~/.oasis/bridge_token</code> and{" "}
          <code className="text-accent">.env.agents</code>. Mitigation
          is the operator&apos;s responsibility (disk encryption, OS
          login password). The platform doesn&apos;t pretend to defend
          against root-level local compromise.
        </p>
        <p>
          <strong className="text-fg">Self-hosted Supabase</strong> — clients
          who need strict data residency would need their own database.
          Tier B (cloud-only mode) and Tier D (self-host) are roadmap
          items, not shipped.
        </p>
        <p>
          <strong className="text-fg">SOC 2 / ISO 27001 paperwork</strong>{" "}
          — not in scope for V6. Code is open for clients to audit
          directly if their compliance regime requires.
        </p>
      </>
    ),
  },
];

export default function SecurityPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <Link
        href="/playbook"
        className="inline-flex items-center gap-1.5 text-xs text-fg-muted hover:text-accent transition-colors"
      >
        <ArrowLeft size={14} /> Playbook
      </Link>

      <PageHeader
        title="Security model"
        subtitle="How tenant isolation, encryption, and bridge authentication actually work. The answer to 'is this safe for my client?'"
        action={<Tag tone="accent">canonical · maps to brain/SECURITY_MODEL.md</Tag>}
      />

      <Card title="The one-paragraph version" subtitle="Read this if you have 30 seconds.">
        <div className="text-sm text-fg-muted leading-relaxed space-y-2">
          <p>
            One shared dashboard + Supabase, with Postgres Row-Level
            Security policies enforcing per-tenant isolation on every
            row that matters. Provider API keys encrypted at rest with
            AES-256-GCM (scrypt-derived key, master secret on Vercel
            only). Bridge daemons authenticate via SHA-256-hashed bearer
            tokens that the dashboard rotates per-machine. Self-pair from
            the daemon uses HMAC headers verified with constant-time
            compare. The pair endpoint is idempotent by{" "}
            <code className="text-accent">(tenant_id, machine_fingerprint)</code>{" "}
            via a DB-level partial unique index, so re-installs never
            leak duplicate rows.
          </p>
        </div>
      </Card>

      {SECTIONS.map((section) => {
        const Icon = section.icon;
        return (
          <Card
            key={section.title}
            title={section.title}
            subtitle={section.subtitle}
            action={<Icon size={20} className="text-accent" />}
          >
            <div className="text-sm text-fg-muted leading-relaxed space-y-2">
              {section.body}
            </div>
          </Card>
        );
      })}

      <Card title="Verification commands" subtitle="Spot-check any of the above against live state.">
        <div className="text-xs text-fg-muted leading-relaxed space-y-2">
          <p>Run these in a terminal at the repo root:</p>
          <pre className="bg-bg-deep border border-bg-border rounded p-3 text-xs font-mono text-fg overflow-x-auto whitespace-pre">{`# Plaintext live secrets in any MCP config (should be zero)
python scripts/audit_mcp_secrets.py

# RLS enabled on every tenant-scoped table
grep -lE "ENABLE ROW LEVEL SECURITY" database/*.sql

# Pair endpoint uses constant-time compare
grep -n "timingSafeEqual" apps/command-center/app/api/auth/pair/route.ts

# Migration 030 applied (try inserting a duplicate — should fail with 23505)
python -c "
import sys; sys.path.insert(0, 'scripts')
from supabase_tool import load_env, get_client
client = get_client(load_env(), 'bravo')
try:
  client.table('bridge_pairings').insert({
    'tenant_id': '<your-tenant-id>',
    'machine_fingerprint': '<existing-fp>',
    'label': 'test', 'bridge_token_hash': 'x'
  }).execute()
  print('UNEXPECTED: constraint NOT firing')
except Exception as e:
  print(f'OK: constraint enforced ({getattr(e, \\"code\\", str(e)[:40])})')
"`}</pre>
          <p className="text-fg-dim pt-1">
            Full architecture detail + threat model:{" "}
            <code className="text-accent">brain/SECURITY_MODEL.md</code>.
          </p>
        </div>
      </Card>
    </div>
  );
}
