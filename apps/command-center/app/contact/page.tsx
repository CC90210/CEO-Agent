"use client";

import { useState } from "react";
import { MarketingShell } from "@/components/MarketingShell";

export default function ContactPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, company, message }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setErr(body.error || "Could not send. Try emailing conaugh@oasisai.work directly.");
        return;
      }
      setDone(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <MarketingShell>
      <section className="px-6 py-24">
        <div className="mx-auto max-w-2xl">
          <div className="text-xs uppercase tracking-[0.18em] font-bold text-accent mb-3">
            Contact
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-fg tracking-tight">
            Tell us what's eating your hours.
          </h1>
          <p className="text-fg-muted mt-4 text-lg">
            We'll respond within 1 business day. Or book a 15-minute call directly:{" "}
            <a
              href="https://calendar.app.google/tpfvJYBGircnGu8G8"
              target="_blank"
              rel="noreferrer"
              className="text-accent hover:underline font-medium"
            >
              calendar.app.google
            </a>
            .
          </p>

          <div className="mt-10 bg-bg-panel border border-bg-border rounded-xl p-7">
            {done ? (
              <div className="text-center py-6">
                <div className="text-2xl font-bold text-fg mb-2">Got it.</div>
                <p className="text-fg-muted">
                  We'll be in touch within 1 business day. Thanks for reaching out.
                </p>
              </div>
            ) : (
              <form onSubmit={onSubmit} className="space-y-4">
                <Field label="Your name" value={name} onChange={setName} required />
                <Field label="Email" type="email" value={email} onChange={setEmail} required />
                <Field label="Company" value={company} onChange={setCompany} />
                <div>
                  <label className="text-xs uppercase tracking-wider font-bold text-fg-muted">
                    What's the process eating your hours?
                  </label>
                  <textarea
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    rows={5}
                    required
                    className="mt-1.5 w-full bg-bg-elev border border-bg-border rounded-md px-3 py-2.5 text-fg focus:border-accent focus:outline-none resize-none"
                  />
                </div>
                {err && (
                  <div className="text-sm text-status-hot bg-status-hot/10 border border-status-hot/30 rounded-md px-3 py-2">
                    {err}
                  </div>
                )}
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full bg-accent text-bg font-bold py-3 rounded-md hover:bg-accent-muted transition-colors disabled:opacity-50 shadow-glow"
                >
                  {busy ? "Sending…" : "Send"}
                </button>
              </form>
            )}
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}

function Field({
  label,
  type = "text",
  value,
  onChange,
  required,
}: {
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
}) {
  return (
    <div>
      <label className="text-xs uppercase tracking-wider font-bold text-fg-muted">
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        className="mt-1.5 w-full bg-bg-elev border border-bg-border rounded-md px-3 py-2.5 text-fg focus:border-accent focus:outline-none"
      />
    </div>
  );
}
