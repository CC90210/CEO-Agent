"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { UserProfile } from "@/lib/supabase";
import { FAMILY_AGENT_KEYS, AGENT_REGISTRY } from "@/lib/agents";

export function ProfileEditor({ profile }: { profile: UserProfile }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [fullName, setFullName] = useState(profile.full_name);
  const [displayName, setDisplayName] = useState(profile.display_name || "");
  const [brand, setBrand] = useState(profile.brand);
  const [mrrTarget, setMrrTarget] = useState(String(profile.mrr_target_usd));
  const [mrrCurrent, setMrrCurrent] = useState(String(profile.mrr_current_usd));
  const [mrrDate, setMrrDate] = useState(profile.mrr_target_date || "");
  const [manifesto, setManifesto] = useState(profile.manifesto || "");
  const [primaryAgent, setPrimaryAgent] = useState(profile.primary_agent);
  const [enabled, setEnabled] = useState<Set<string>>(new Set(profile.agents_enabled));

  function toggleAgent(key: string) {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function onSave() {
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      const r = await fetch("/api/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: fullName,
          display_name: displayName || null,
          brand,
          mrr_target_usd: Number(mrrTarget) || 0,
          mrr_current_usd: Number(mrrCurrent) || 0,
          mrr_target_date: mrrDate || null,
          manifesto: manifesto || null,
          primary_agent: primaryAgent,
          agents_enabled: Array.from(enabled),
        }),
      });
      const body = await r.json();
      if (!r.ok || !body.ok) {
        setErr(body.error || `error ${r.status}`);
        return;
      }
      setMsg("Saved.");
      router.refresh();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid sm:grid-cols-2 gap-4">
        <Field label="Full name">
          <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </Field>
        <Field label="Display name">
          <input className="input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="e.g. CC" />
        </Field>
        <Field label="Brand">
          <input className="input" value={brand} onChange={(e) => setBrand(e.target.value)} />
        </Field>
        <Field label="Primary agent">
          <select className="select" value={primaryAgent} onChange={(e) => setPrimaryAgent(e.target.value)}>
            {FAMILY_AGENT_KEYS.map((k) => (
              <option key={k} value={k}>{AGENT_REGISTRY[k]?.label || k}</option>
            ))}
          </select>
        </Field>
        <Field label="MRR target (USD)">
          <input className="input" type="number" value={mrrTarget} onChange={(e) => setMrrTarget(e.target.value)} />
        </Field>
        <Field label="MRR current (USD)">
          <input className="input" type="number" value={mrrCurrent} onChange={(e) => setMrrCurrent(e.target.value)} />
        </Field>
        <Field label="MRR target date">
          <input className="input" type="date" value={mrrDate} onChange={(e) => setMrrDate(e.target.value)} />
        </Field>
        <Field label="Email">
          <input className="input opacity-60" value={profile.email} disabled />
        </Field>
      </div>

      <Field label="Manifesto / direction (shown on Today)">
        <textarea
          className="textarea"
          value={manifesto}
          onChange={(e) => setManifesto(e.target.value)}
          rows={6}
          placeholder="A line you want to read every morning."
        />
      </Field>

      <div>
        <div className="label mb-2">Agents enabled</div>
        <ul className="grid sm:grid-cols-2 gap-2">
          {FAMILY_AGENT_KEYS.map((key) => {
            const a = AGENT_REGISTRY[key];
            const on = enabled.has(key);
            return (
              <li key={key}>
                <button
                  type="button"
                  onClick={() => toggleAgent(key)}
                  className={`w-full text-left p-3 rounded-md border flex items-center gap-3 transition-all ${
                    on
                      ? "bg-accent-soft border-accent text-fg"
                      : "bg-bg-elev border-bg-border text-fg-muted hover:border-bg-hover"
                  }`}
                >
                  <div
                    className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${
                      on ? "bg-accent border-accent text-bg" : "border-fg-faint"
                    }`}
                  >
                    {on && <CheckIcon />}
                  </div>
                  <div>
                    <div className={`font-bold uppercase tracking-wider text-xs ${on ? "text-accent" : ""}`}>{a.label}</div>
                    <div className="text-xs">{a.role}</div>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="flex items-center gap-3 pt-2">
        <button onClick={onSave} disabled={busy} className="btn-primary">
          {busy ? "Saving…" : "Save profile"}
        </button>
        {msg && <span className="text-status-engaged text-sm">{msg}</span>}
        {err && <span className="text-status-hot text-sm">{err}</span>}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="label">{label}</div>
      {children}
    </div>
  );
}

function CheckIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
      <path d="M2.5 6.5L5 9L9.5 3.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
