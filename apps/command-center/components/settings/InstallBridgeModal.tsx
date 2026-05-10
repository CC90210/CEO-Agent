"use client";

/**
 * InstallBridgeModal — full-page modal that walks the operator from
 * "click Install" to "bridge is online" without ever leaving the
 * dashboard tab.
 *
 * Flow:
 *   1. Mint a single-use 15-min pair-code via /api/auth/pair-code
 *   2. Detect OS, render the OS-appropriate one-liner with the code
 *      embedded as the BRAVO_PAIR_CODE env var
 *   3. Operator copies + pastes into a fresh terminal (or runs from a
 *      script the dashboard helped them download — out of scope v1)
 *   4. Modal polls /api/devices every 2s; when a new device appears
 *      with created_at > the moment we minted the code, transition to
 *      success state
 *   5. Operator clicks Done; the parent component reloads its device
 *      list to show the new pairing
 *
 * Why a shared component: identical flow ships from Settings → Devices
 * AND from /onboarding step 3. Wrapping the logic in one place means
 * any future improvement (Linux flavour detection, installer download
 * link, etc.) lands in both surfaces with one edit.
 */

import { useEffect, useMemo, useState } from "react";
import { Loader2, Check, Copy, X, Clock, AlertCircle, Apple, Monitor, Terminal } from "lucide-react";

type OS = "windows" | "macos" | "linux";

function detectOS(): OS {
  if (typeof navigator === "undefined") return "windows";
  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes("mac os") || ua.includes("macintosh")) return "macos";
  if (ua.includes("linux") && !ua.includes("android")) return "linux";
  return "windows";
}

function oneLinerFor(os: OS, code: string): string {
  // PowerShell: $env:VAR is session-scoped, inherited by `iex`'d
  // commands and any child processes. Works.
  const winShell = `$env:BRAVO_PAIR_CODE="${code}"; irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex`;
  // Bash: env-var prefix on `curl` would scope the var to curl ONLY
  // — the bash subshell after the pipe wouldn't inherit it. Putting
  // the prefix on the `bash` side makes it the env for the shell
  // that runs the install script + the wizard subprocess. Verified
  // 2026-05-10 self-review: the wrong shape would silently lose the
  // pair-code and drop back to the manual-paste prompt.
  const nixShell = `curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | BRAVO_PAIR_CODE=${code} bash`;
  return os === "windows" ? winShell : nixShell;
}

type DeviceLite = { id: string; created_at: string; revoked_at: string | null };

export function InstallBridgeModal({ onClose }: { onClose: () => void }) {
  const [os, setOs] = useState<OS>("windows");
  const [code, setCode] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [mintedAt, setMintedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<"mint" | "command" | "watching" | "connected">("mint");
  const [copied, setCopied] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);

  // Detect OS once on mount.
  useEffect(() => {
    setOs(detectOS());
  }, []);

  // Mint the pair-code as soon as the modal opens.
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

  // Live countdown for the code's TTL.
  useEffect(() => {
    if (!expiresAt) return;
    const tick = () => {
      const left = Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000));
      setSecondsLeft(left);
      if (left === 0 && phase !== "connected") {
        // Code expired before redemption — re-mint cleanly.
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

  // While the code is live, poll devices every 2s. As soon as a new
  // pairing row appears (created_at > mintedAt) flip to "connected".
  useEffect(() => {
    if (phase !== "command" && phase !== "watching") return;
    if (!mintedAt) return;
    let cancelled = false;
    let cycleCount = 0;
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
        // Transient network blip — keep polling.
      }
      cycleCount += 1;
      // After ~3 cycles (6s) without a new device, swap the user-facing
      // copy from "command" to "watching" so they know we're listening.
      if (cycleCount >= 3 && phase === "command") {
        setPhase("watching");
      }
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-bg-deep/80 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-xl border border-bg-border bg-bg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-bg-border">
          <div>
            <h2 className="text-lg font-bold text-fg">Install Claude Code CLI bridge</h2>
            <p className="text-xs text-fg-muted mt-0.5">
              One command on your machine — your dashboard chat will use your local Claude Code subscription.
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-fg-dim hover:text-fg-muted p-1"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-5">
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
              {/* OS picker */}
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

              {/* Command */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
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

              {/* Watching status */}
              <div className="rounded-lg border border-bg-border bg-bg-deep/40 p-3">
                <div className="flex items-center gap-2 text-sm text-fg-muted">
                  <Loader2 className="w-4 h-4 animate-spin text-accent" />
                  <span>
                    {phase === "command"
                      ? "Run the command — we're listening for your bridge to come online."
                      : "Watching for your bridge…  this usually takes 60–90 seconds while pip installs."}
                  </span>
                </div>
                <div className="text-[11px] text-fg-dim mt-1.5">
                  Need to run it on a different machine? The pair code works from any terminal as long as it's redeemed before it expires.
                </div>
              </div>
            </>
          )}

          {phase === "connected" && (
            <div className="py-6 space-y-3">
              <div className="rounded-lg border border-status-engaged/40 bg-status-engaged/10 p-4 flex items-start gap-3">
                <Check className="w-5 h-5 text-status-engaged shrink-0 mt-0.5" />
                <div>
                  <div className="font-bold text-fg">Bridge is online.</div>
                  <div className="text-sm text-fg-muted mt-1">
                    Refresh the chat header on /agents — the agent badge should flip to{" "}
                    <span className="text-accent font-mono">local bridge · Claude Code CLI</span>.
                    Your chat now runs through your machine's Claude subscription, with full file + script access.
                  </div>
                </div>
              </div>
              <button onClick={onClose} className="btn-primary w-full">
                Done
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
