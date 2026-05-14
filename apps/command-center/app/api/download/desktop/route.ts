import { NextResponse, type NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const RELEASE_TAG = "oasis-desktop-v0.1.0-alpha.4";
const RELEASE_BASE = `https://github.com/CC90210/CEO-Agent/releases/download/${RELEASE_TAG}`;

const DOWNLOADS = {
  windows: `${RELEASE_BASE}/OASIS-AI-0.1.0-win-x64-portable.zip`,
  windowsInstaller: `${RELEASE_BASE}/OASIS-AI-0.1.0-win-x64.exe`,
  mac: `${RELEASE_BASE}/OASIS-AI-0.1.0-mac-arm64.dmg`,
  linux: `${RELEASE_BASE}/OASIS-AI-0.1.0-linux-x86_64.AppImage`,
  linuxDeb: `${RELEASE_BASE}/OASIS-AI-0.1.0-linux-amd64.deb`,
  checksums: `${RELEASE_BASE}/SHA256SUMS-release.txt`,
} as const;

function normalizePlatform(raw: string | null) {
  const value = (raw || "").toLowerCase().trim();
  if (["win", "windows", "windows-zip", "portable"].includes(value)) return "windows";
  if (["windows-installer", "installer", "exe"].includes(value)) return "windowsInstaller";
  if (["mac", "macos", "darwin", "dmg"].includes(value)) return "mac";
  if (["linux", "appimage"].includes(value)) return "linux";
  if (["linux-deb", "deb", "debian", "ubuntu"].includes(value)) return "linuxDeb";
  if (["sha", "sha256", "checksums"].includes(value)) return "checksums";
  return null;
}

function inferPlatform(userAgent: string | null) {
  const ua = (userAgent || "").toLowerCase();
  if (ua.includes("windows")) return "windows";
  if (ua.includes("mac os") || ua.includes("macintosh")) return "mac";
  if (ua.includes("linux")) return "linux";
  return null;
}

export function GET(req: NextRequest) {
  const url = new URL(req.url);
  const explicitPlatform = normalizePlatform(url.searchParams.get("platform"));
  const inferredPlatform = inferPlatform(req.headers.get("user-agent"));
  const platform = explicitPlatform || inferredPlatform;

  if (!platform) {
    return NextResponse.redirect(new URL("/download", req.url));
  }

  return NextResponse.redirect(DOWNLOADS[platform]);
}
