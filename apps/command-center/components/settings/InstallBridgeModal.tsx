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

import { useState } from "react";
import { Loader2, Check, Copy, X, Clock, AlertCircle, Apple, Monitor, Terminal } from "lucide-react";
import { useBridgePairing, type OS } from "@/hooks/useBridgePairing";

export function InstallBridgeModal({ onClose }: { onClose: () => void }) {
  // All pairing state + side effects (mint, countdown, polling, retry)
  // live in the shared hook. This file is now render-only.
  const { os, setOs, code, oneLiner, secondsLeft, phase, error, retryMint } =
    useBridgePairing();
  const [copied, setCopied] = useState(false);

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

          {phase === "mint" && !error && (
            <div className="text-fg-muted text-sm flex items-center gap-2 py-8 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" /> Generating a one-time pair code…
            </div>
          )}
          {phase === "mint" && error && (
            <div className="py-4 flex justify-center">
              <button
                type="button"
                onClick={retryMint}
                className="btn-primary inline-flex items-center gap-2"
              >
                Try again
              </button>
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
