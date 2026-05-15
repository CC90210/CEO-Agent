"use client";

/**
 * InstallBridgeWizard — inline wizard for the dedicated /settings/devices/install
 * page. Same flow as InstallBridgeModal (mint pair code → render OS one-liner
 * → poll /api/devices for a new pairing → success), but rendered as a page
 * card instead of a fixed-position modal.
 *
 * The state machine + polling logic lives in hooks/useBridgePairing.ts so
 * this file is a thin render-only wrapper. The Modal consumes the same hook.
 */

import { useState } from "react";
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
import { useBridgePairing, type OS } from "@/hooks/useBridgePairing";

export function InstallBridgeWizard() {
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

          {/*
            Self-sufficiency follow-up. The pair-code one-liner above starts
            the bridge for THIS session but doesn't survive a reboot. Three
            one-time commands wire it into PM2 so it (and the V6 + cron
            daemons) auto-start on login. Optional — operators who shut down
            their machine nightly should run them; always-on desktops can
            skip.
          */}
          <div className="rounded-lg border border-bg-border bg-bg-elev/40 p-4 space-y-2">
            <div className="text-xs uppercase tracking-wider font-bold text-fg-dim">
              Optional · Make this survive reboots
            </div>
            <p className="text-xs text-fg-muted leading-relaxed">
              The bridge is running in this session. To have it (plus the cron
              poller, event-bus router, and override consumer) auto-start at
              login, run these three one-time commands from the repo root:
            </p>
            <pre className="text-[11px] font-mono text-accent bg-bg-deep border border-bg-border rounded p-2.5 overflow-x-auto select-all">
{`pm2 start ecosystem.config.js
pm2 save
pm2 startup    # follow the platform-specific line PM2 prints`}
            </pre>
            <div className="text-[11px] text-fg-dim">
              After this, your operator daemons (claude-bridge, claude-bridge-ping,
              event-router, override-consumer) survive shutdowns and PM2 will
              auto-restart any of them that crash.
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
