/**
 * /configure — public agent-configurator landing.
 *
 * The "Configure your own agent" button on /welcome lands here. Visitor
 * picks an agent, answers a few personalization questions, the page
 * generates a custom install one-liner that clones the right repo +
 * pre-fills their answers, and surfaces the OASIS AI checkout link if
 * they need to purchase access.
 *
 * No auth required to view this — it's a pre-signup funnel.
 */

import Link from "next/link";
import { redirect } from "next/navigation";
import { ArrowRight, Sparkles, ShieldCheck } from "lucide-react";
import { getSessionUser } from "@/lib/supabase-server";
import { ConfigureFlow } from "@/components/landing/ConfigureFlow";

export const dynamic = "force-dynamic";

export default async function ConfigurePage() {
  const user = await getSessionUser().catch(() => null);
  if (user) redirect("/onboarding"); // already signed in → use authenticated wizard

  return (
    <main className="min-h-screen bg-bg-deep relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div
          className="absolute -top-[20%] left-1/2 -translate-x-1/2 w-[1200px] h-[700px] rounded-full opacity-30 blur-3xl"
          style={{
            background:
              "radial-gradient(circle, rgba(59,130,246,0.4), transparent 70%)",
          }}
        />
      </div>

      <header className="relative z-10 mx-auto max-w-5xl px-6 py-5 flex items-center justify-between">
        <Link href="/welcome" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-gradient-to-br from-accent to-cyan-400 shadow-[0_0_20px_-2px_rgba(0,212,255,0.6)]">
            <span className="text-bg-deep font-black text-sm">O</span>
          </div>
          <div className="leading-none">
            <div className="font-black text-fg tracking-tight text-sm">OASIS AI</div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-fg-dim">Configure</div>
          </div>
        </Link>
        <div className="flex items-center gap-3 text-xs">
          <Link href="/login" className="text-fg-muted hover:text-fg transition-colors">
            Sign in
          </Link>
          <a
            href="https://oasisai.work"
            target="_blank"
            rel="noopener noreferrer"
            className="text-fg-muted hover:text-fg transition-colors"
          >
            oasisai.work
          </a>
        </div>
      </header>

      <section className="relative z-10 mx-auto max-w-3xl px-6 py-8 pb-20">
        <div className="mb-8">
          <div className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/5 px-3 py-1 text-xs text-accent mb-4">
            <Sparkles className="w-3 h-3" /> No account needed yet
          </div>
          <h1 className="text-3xl sm:text-4xl font-black text-fg leading-tight tracking-tight">
            Configure your own agent.
          </h1>
          <p className="mt-3 text-fg-muted">
            Pick the agent role you want, tell us about your business, and we&apos;ll generate a one-line install command tailored to you. The install clones the right repo onto your machine, runs the setup wizard with your answers pre-filled, and you&apos;re running locally with full file access in under five minutes.
          </p>
        </div>

        <ConfigureFlow />

        <div className="mt-10 rounded-xl border border-bg-border bg-bg-elev/50 p-5 text-sm">
          <div className="flex items-center gap-2 mb-3">
            <ShieldCheck className="w-4 h-4 text-accent" />
            <h2 className="font-bold text-fg">How this works · security model</h2>
          </div>
          <ol className="space-y-2.5 text-fg-muted text-[13px] leading-relaxed list-decimal list-inside">
            <li>
              <strong className="text-fg">Local-first.</strong> Everything runs on your machine. Your API keys, files, and data live in <code className="text-accent">~/.bravo</code> + the agent&apos;s repo folder — they never leave your device. Our cloud only sees your tenant settings (encrypted at rest with a per-tenant key) and chat metadata.
            </li>
            <li>
              <strong className="text-fg">Bring your own model.</strong> OpenRouter (one key, every model) is the easy path. Direct Anthropic / OpenAI / Gemini also supported. Your key sits in <code className="text-accent">.env.agents</code> on your machine, gitignored, and is read at runtime when the bridge calls the model.
            </li>
            <li>
              <strong className="text-fg">localhost:9100 is YOUR machine&apos;s loopback.</strong> Not a shared network, not someone else&apos;s computer. The bridge daemon binds to <code className="text-accent">127.0.0.1:9100</code> only — kernel-level, the OS will refuse any connection from outside your machine. When the dashboard fetches <code className="text-accent">http://localhost:9100/chat</code>, that request never leaves your computer.
            </li>
            <li>
              <strong className="text-fg">Browser-side gate.</strong> Chrome blocks HTTPS pages from accessing local-network endpoints by default (Private Network Access). You&apos;ll see a one-time prompt the first time the dashboard tries to talk to your bridge — clicking <em>Allow</em> creates a per-origin permission. The only origins that can fetch your bridge are the dashboards in the bridge&apos;s CORS allowlist (today: <code className="text-accent">agent-dashboard-cc90210.vercel.app</code> + your own localhost dev server).
            </li>
            <li>
              <strong className="text-fg">Path-allowlisted file reads.</strong> The bridge can only read files under the agent&apos;s repo root. Any path that escapes (<code>..</code>, absolute paths outside the repo, OS-level paths like <code>/etc</code> or <code>C:\Windows</code>) is rejected before <code>fs.read</code> runs.
            </li>
            <li>
              <strong className="text-fg">HMAC-paired heartbeat.</strong> The bridge identifies itself to the dashboard with a per-machine bearer token issued during pairing (HMAC-bound to your tenant + machine fingerprint, stored in <code className="text-accent">~/.oasis/bridge_token</code>). You can revoke any paired machine from <code className="text-accent">/devices</code> — the bridge sees a 403 on its next ping and self-stops within 60s.
            </li>
            <li>
              <strong className="text-fg">No third-party data sharing.</strong> Your file contents, agent prompts, and chat transcripts route browser → localhost direct. The model provider you chose (Anthropic / OpenRouter / etc.) sees the prompt + tool calls because that&apos;s how the model runs — but only through your key, billed to your account. We do not proxy your traffic through our servers.
            </li>
            <li>
              <strong className="text-fg">Open the loop with payment</strong> only if you want a managed deploy or premium support — <a href="https://oasisai.work" target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">oasisai.work</a> handles checkout via Stripe.
            </li>
          </ol>
        </div>
      </section>
    </main>
  );
}
