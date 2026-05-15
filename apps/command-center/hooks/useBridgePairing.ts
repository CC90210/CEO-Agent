"use client";

/**
 * useBridgePairing — shared state machine for the bridge install flow.
 *
 * Owns:
 *   - OS detection on mount (Windows / macOS / Linux from UA)
 *   - Mint pair-code POST → /api/auth/pair-code, with retry knob
 *   - Live countdown of the code's 15-min TTL; auto re-mint on expiry
 *   - 2-second poll of /api/devices for a new pairing row created after
 *     the moment the code was minted; flip to "connected" on detection
 *   - Pre-built OS-specific one-liner (PowerShell on Windows, bash else)
 *
 * Two consumers as of 2026-05-15:
 *   - components/settings/InstallBridgeModal.tsx — modal opened from
 *     Settings → Devices
 *   - app/settings/devices/install/InstallBridgeWizard.tsx — dedicated
 *     /settings/devices/install page
 *
 * Both used to duplicate this whole state machine character-for-character.
 * Any change (new schema, new install flow, different polling cadence)
 * needed to land in both files. Extracting it kills that drift surface
 * and lets the two surfaces stay tiny render-only wrappers.
 */

import { useEffect, useMemo, useState } from "react";

export type OS = "windows" | "macos" | "linux";

export type Phase = "mint" | "command" | "watching" | "connected";

export type BridgePairing = {
  os: OS;
  setOs: (os: OS) => void;
  code: string | null;
  oneLiner: string;
  /** Seconds remaining on the current code's TTL. 0 if no code yet. */
  secondsLeft: number;
  phase: Phase;
  error: string | null;
  /** Bump to re-attempt mint after a failure. */
  retryMint: () => void;
};

function detectOS(): OS {
  if (typeof navigator === "undefined") return "windows";
  const ua = navigator.userAgent.toLowerCase();
  if (ua.includes("mac os") || ua.includes("macintosh")) return "macos";
  if (ua.includes("linux") && !ua.includes("android")) return "linux";
  return "windows";
}

function oneLinerFor(os: OS, code: string): string {
  // PowerShell env-var prefix on the iex'd command — verified working
  // 2026-05-10 self-review. Bash uses the prefix on `bash` (not `curl`)
  // so the subshell that runs the script inherits the variable.
  const winShell = `$env:BRAVO_PAIR_CODE="${code}"; irm https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.ps1 | iex`;
  const nixShell = `curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | BRAVO_PAIR_CODE=${code} bash`;
  return os === "windows" ? winShell : nixShell;
}

type DeviceLite = { id: string; created_at: string; revoked_at: string | null };

export function useBridgePairing(): BridgePairing {
  const [os, setOs] = useState<OS>("windows");
  const [code, setCode] = useState<string | null>(null);
  const [expiresAt, setExpiresAt] = useState<string | null>(null);
  const [mintedAt, setMintedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("mint");
  const [secondsLeft, setSecondsLeft] = useState(0);
  // Bumped by retryMint() — sits in the mint effect's deps so a bump
  // re-runs the POST even though `phase` is still "mint".
  const [mintAttempt, setMintAttempt] = useState(0);

  useEffect(() => {
    setOs(detectOS());
  }, []);

  // Mint pair code on mount, on re-entry after expiry, or on retry.
  useEffect(() => {
    if (phase !== "mint") return;
    let cancelled = false;
    setError(null);
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
  }, [phase, mintAttempt]);

  // Countdown — auto re-mints when the code hits zero (unless we've
  // already connected, in which case the code is moot).
  useEffect(() => {
    if (!expiresAt) return;
    const tick = () => {
      const left = Math.max(
        0,
        Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000)
      );
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

  // Poll /api/devices — flip to "connected" when a new pairing row appears
  // with created_at > the moment we minted the code. Once the operator
  // has spent ~6s in "command" without a hit, downgrade copy to
  // "watching" so they know we're listening (mostly cosmetic).
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

  return {
    os,
    setOs,
    code,
    oneLiner,
    secondsLeft,
    phase,
    error,
    retryMint: () => setMintAttempt((n) => n + 1),
  };
}
