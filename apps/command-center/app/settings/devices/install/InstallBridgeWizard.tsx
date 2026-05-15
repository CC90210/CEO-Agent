"use client";

/**
 * InstallBridgeWizard — inline wizard for the dedicated /settings/devices/install
 * page. Same flow as InstallBridgeModal (mint pair code → render OS one-liner
 * → poll /api/devices for a new pairing → success), but rendered as a page
 * card instead of a fixed-position modal.
 *
 * Duplicating the polling/mint logic instead of factoring it out keeps the
 * blast radius of this PR small. If a third surface ever needs the same flow,
 * pull it into a shared hook (useBridgePairing) then.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Loader2,
  Check,
  Copy,
  Clock,
  AlertCircle,
  Apple,
  Monitor,
  Terminal,
  ExternalLink,
} from "lucide-react";

type OS = "windows" | "macos" | "linux";

function detectOS(): OS {
  if (typeof navigator === "undefined") return "windows";
  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes("mac os") || ua.includes("macintosh")) return "macos";
  if (ua.includes("linux") && !ua.includes("android")) return "linux";
  return "windows";
}

function oneLinerFor(os: OS, code: string): string {
  // PowerShell env-var prefix on the iex'd command — verified working in
  // InstallBridgeModal:2026-05-10. Bash uses the prefix on `bash` (not
  // `curl`) so the subshell that runs the script inherits the variable.
  const winShell = `$env:BRAVO_PAIR_CODE="${code}"; irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex`;
  const nixShell = `curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | BRAVO_PAIR_CODE=${code} bash`;
  return os === "windows" ? winShell : nixShell;
}

type DeviceLite = { id: string; created_at: string; revoked_at: string | null };

export function InstallBridgeWizard() {
  const [os, setOs] = useState<OS>("windows");
  const [code, setCode] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [mintedAt, setMintedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<"mint" | "command" | "watching" | "connected">("mint");
  const [copied, setCopied] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);

  useEffect(() => {
    setOs(detectOS());
  }, []);

  // Mint pair code on mount (and on re-entry after expiry).
  useEffect(() => {
    if (phase !== "mint") return;
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch("/api/auth/pair-code", { method: "POST" });
        const j = await r.json();
        if (cancelled) return;
        if (!j.ok) {
          setError(j.error || `http_${r.status}`);
          return;
        }
        setCode(j.code);
        setExpiresAt(j.expires_at);
        setMintedAt(Date.now());
        setPhase("command");
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "mint_failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [phase]);

  // Countdown
  useEffect(() => {
    if (!expiresAt) return;
    const tick = () => {
      const left = Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000));
      setSecondsLeft(left);
      if (left === 0 && phase !== "connected") {
        setError("Pair code expired before the installer ran. Generating a fresh one.");
        setCode(null);
        setExpiresAt(null);
        setMintedAt(null);
        setPhase("mint");
      }
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [expiresAt, phase]);

  // Poll /api/devices — flip to connected when a new pairing row appears
  // after the moment we minted the code.
  useEffect(() => {
    if (phase !== "command" && phase !== "watching") return;
    if (!mintedAt) return;
    let cancelled = false;
    let cycles = 0;
    const poll = async () => {
      try {
        const r = await fetch("/api/devices");
        const j = await r.json();
        if (cancelled) return;
        if (j.ok && Array.isArray(j.devices)) {
          const fresh = (j.devices as DeviceLite[]).find(
            (d) => !d.revoked_at && new Date(d.created_at).getTime() > mintedAt
          );
          if (fresh) {
            setPhase("connected");
            return;
          }
        }
      } catch {
        // Transient blip — keep polling.
      }
      cycles += 1;
      if (cycles >= 3 && phase === "command") setPhase("watching");
    };
    poll();
    const t = setInterval(poll, 2000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [phase, mintedAt]);

  const oneLiner = useMemo(() => (code ? oneLinerFor(os, code) : ""), [os, code]);

  function handleCopy() {
    if (typeof navigator === "undefined" || !navigator.clipboard || !oneLiner) return;
    navigator.clipboard.writeText(oneLiner).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  const mm = Math.floor(secondsLeft / 60).toString().padStart(2, "0");
  const ss = (secondsLeft % 60).toString().padStart(2, "0");

  return (
    <div className="rounded-xl border border-bg-border bg-bg-elev/40 p-5 space-y-5">
      <div>
        <h2 className="text-base font-bold text-fg">Pair this machine</h2>
        <p className="text-xs text-fg-muted mt-0.5">
          One command on your machine. The dashboard polls for your bridge to come online — usually 60–90 seconds.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-status-warm/40 bg-status-warm/10 p-3 text-sm text-status-warm flex items-start gap-2">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {phase === "mint" && (
        <div className="text-fg-muted text-sm flex items-center gap-2 py-8 justify-center">
          <Loader2 className="w-4 h-4 animate-spin" /> Generating a one-time pair code…
        </div>
      )}

      {(phase === "command" || phase === "watching") && code && (
        <>
          <div className="space-y-2">
            <div className="text-[11px] uppercase tracking-wider font-bold text-fg-dim">
              Step 1 — confirm your OS
            </div>
            <div className="flex gap-2">
              {(["windows", "macos", "linux"] as OS[]).map((o) => (
                <button
                  key={o}
                  type="button"
                  onClick={() => setOs(o)}
                  className={`flex-1 inline-flex items-center justify-center gap-2 py-2 px-3 rounded-md border text-sm transition ${
                    os === o
                      ? "border-accent bg-accent/10 text-accent font-bold"
                      : "border-bg-border text-fg-muted hover:border-bg-border-strong"
                  }`}
                >
                  {o === "windows" && <Monitor className="w-4 h-4" />}
                  {o === "macos" && <Apple className="w-4 h-4" />}
                  {o === "linux" && <Terminal className="w-4 h-4" />}
                  {o === "windows" ? "Windows" : o === "macos" ? "macOS" : "Linux"}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between flex-wrap gap-1">
              <div className="text-[11px] uppercase tracking-wider font-bold text-fg-dim">
                Step 2 — paste this in your {os === "windows" ? "PowerShell" : "terminal"}
              </div>
              <div className="text-[11px] text-fg-dim font-mono inline-flex items-center gap-1">
                <Clock className="w-3 h-3" /> code expires in {mm}:{ss}
              </div>
            </div>
            <div className="rounded-lg bg-bg-deep border border-bg-border p-3 font-mono text-xs text-fg leading-relaxed break-all select-all">
              {oneLiner}
            </div>
            <button
              type="button"
              onClick={handleCopy}
              className="btn-primary inline-flex items-center gap-2"
            >
              {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              {copied ? "Copied!" : "Copy command"}
            </button>
          </div>

          <div className="rounded-lg border border-bg-border bg-bg-deep/40 p-3">
            <div className="flex items-center gap-2 text-sm text-fg-muted">
              <Loader2 className="w-4 h-4 animate-spin text-accent" />
              <span>
                {phase === "command"
                  ? "Run the command — we're listening for your bridge to come online."
                  : "Watching for your bridge… this usually takes 60–90 seconds while pip installs."}
              </span>
            </div>
            <div className="text-[11px] text-fg-dim mt-1.5">
              Need to run it on a different machine? The pair code works from any terminal as long as it's redeemed before it expires.
            </div>
          </div>

          <div className="text-xs text-fg-dim">
            Prefer a download over a curl pipe? Grab the desktop installer at{" "}
            <Link
              href="/download"
              className="text-accent hover:text-accent-bright inline-flex items-center gap-1"
            >
              /download <ExternalLink className="w-3 h-3" />
            </Link>
            .
          </div>
        </>
      )}

      {phase === "connected" && (
        <div className="space-y-3">
          <div className="rounded-lg border border-status-engaged/40 bg-status-engaged/10 p-4 flex items-start gap-3">
            <Check className="w-5 h-5 text-status-engaged shrink-0 mt-0.5" />
            <div>
              <div className="font-bold text-fg">Bridge is online.</div>
              <div className="text-sm text-fg-muted mt-1">
                Open any agent chat. The mode picker in the chat header will start defaulting to{" "}
                <span className="text-accent font-mono">CLI (bridge)</span> on Auto. Your chat now runs through this machine's Claude subscription with full file + script access.
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            <Link href="/" className="btn-primary inline-flex items-center gap-2">
              Open a chat
            </Link>
            <Link
              href="/settings#devices"
              className="btn-secondary inline-flex items-center gap-2"
            >
              Manage devices
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
