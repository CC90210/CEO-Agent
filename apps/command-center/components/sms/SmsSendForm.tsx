"use client";

import { useState } from "react";
import { Send, CheckCircle2, AlertCircle } from "lucide-react";

type SendResult = {
  ok: boolean;
  provider?: string;
  to_hash?: string;
  status?: string;
  sid?: string | null;
  error?: string | null;
};

export function SmsSendForm() {
  const [to, setTo] = useState("");
  const [body, setBody] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SendResult | null>(null);

  const charCount = body.length;
  const segments = charCount === 0 ? 0 : Math.ceil(charCount / 160);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);
    try {
      const r = await fetch("/api/sms/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to, body }),
      });
      const data: SendResult = await r.json();
      setResult(data);
      if (data.ok) {
        setBody("");
      }
    } catch (err) {
      setResult({
        ok: false,
        error: err instanceof Error ? err.message : "Network error",
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="block text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold mb-1.5">
          To (E.164)
        </label>
        <input
          type="tel"
          value={to}
          onChange={(e) => setTo(e.target.value)}
          placeholder="+14165551212"
          required
          pattern="^\+[1-9]\d{6,14}$"
          className="w-full px-3 py-2 bg-bg-elev border border-bg-border rounded-md text-fg text-sm font-mono focus:outline-none focus:border-accent transition-colors"
        />
      </div>

      <div>
        <div className="flex items-baseline justify-between mb-1.5">
          <label className="text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold">
            Message
          </label>
          <span className="text-[10px] text-fg-faint font-mono">
            {charCount} / 1600 · {segments} {segments === 1 ? "segment" : "segments"}
          </span>
        </div>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={5}
          maxLength={1600}
          required
          placeholder="Hi {first_name}, this is Sun Biz Funding..."
          className="w-full px-3 py-2 bg-bg-elev border border-bg-border rounded-md text-fg text-sm focus:outline-none focus:border-accent transition-colors resize-none"
        />
        <p className="text-[10px] text-fg-faint mt-1">
          TCPA: recipient must have opt-in on file. Quiet hours (8am-9pm local) enforced server-side.
        </p>
      </div>

      <button
        type="submit"
        disabled={submitting || !to || !body}
        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-accent text-bg-deep rounded-md text-sm font-bold hover:bg-accent/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Send size={14} />
        {submitting ? "Sending..." : "Send SMS"}
      </button>

      {result && (
        <div
          className={`flex items-start gap-2 px-3 py-2 rounded-md text-xs ${
            result.ok
              ? "bg-status-engaged/10 border border-status-engaged/30 text-status-engaged"
              : "bg-status-hot/10 border border-status-hot/30 text-status-hot"
          }`}
        >
          {result.ok ? (
            <CheckCircle2 size={14} className="flex-shrink-0 mt-0.5" />
          ) : (
            <AlertCircle size={14} className="flex-shrink-0 mt-0.5" />
          )}
          <div>
            {result.ok ? (
              <>
                <div className="font-bold">Sent via {result.provider}</div>
                <div className="font-mono text-[10px] opacity-75">
                  status={result.status} · sid={result.sid || "—"}
                </div>
              </>
            ) : (
              <>
                <div className="font-bold">Failed ({result.status || "error"})</div>
                <div className="font-mono text-[10px] opacity-75">{result.error}</div>
              </>
            )}
          </div>
        </div>
      )}
    </form>
  );
}
