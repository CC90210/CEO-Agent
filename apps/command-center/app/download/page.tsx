import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  Cloud,
  Cpu,
  Download,
  KeyRound,
  MonitorDown,
  ShieldCheck,
  Workflow,
  XCircle,
} from "lucide-react";
import { OasisLogo } from "@/components/brand/OasisLogo";

export const dynamic = "force-dynamic";

const VERSION = "0.1.0";
const CHANNEL = "alpha";
const RELEASE_TAG = "oasis-desktop-v0.1.0-alpha.4";
const RELEASE_URL = `https://github.com/CC90210/CEO-Agent/releases/tag/${RELEASE_TAG}`;
const AUTO_DOWNLOAD_URL = "/api/download/desktop";
const WINDOWS_PORTABLE_URL = "/api/download/desktop?platform=windows";
const WINDOWS_INSTALLER_URL = "/api/download/desktop?platform=windows-installer";
const MAC_DMG_URL = "/api/download/desktop?platform=mac";
const LINUX_APPIMAGE_URL = "/api/download/desktop?platform=linux";
const LINUX_DEB_URL = "/api/download/desktop?platform=linux-deb";
const CHECKSUM_URL = "/api/download/desktop?platform=checksums";
const CHECKSUMS = [
  "Windows portable zip: 07dea7cf78ce4ae36321dbdebb0e0c246dbf0c173699c2bd31e3fa9fa88e9c76",
  "Windows installer: 18e09eb6efd275d06c6b2f8f1e116f3edfe9635e888b0d6fb04cf069f3db23cd",
  "macOS: 3119cdd4f3e6b7e7f61e715375fa980937964abedc8a393d9d8273bc120d6d63",
  "Linux AppImage: 7df499a4fe4d0f9746d41ff6e13b85bcc6368ec59287820f288fa1508f5ef777",
  "Linux deb: 0fc038c210e54b331169f8d443d12fa423eb0a43c5a900ec051e66e36bce33ab",
];

export default function DownloadPage() {
  return (
    <main className="min-h-screen bg-bg-deep text-fg relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div
          className="absolute -top-[22%] left-1/2 h-[760px] w-[1400px] -translate-x-1/2 rounded-full opacity-40 blur-3xl"
          style={{ background: "radial-gradient(circle, rgba(0,212,255,0.42), rgba(59,130,246,0.18) 38%, transparent 70%)" }}
        />
        <div
          className="absolute bottom-[-18%] right-[-12%] h-[620px] w-[860px] rounded-full opacity-30 blur-3xl"
          style={{ background: "radial-gradient(circle, rgba(34,197,94,0.20), transparent 68%)" }}
        />
      </div>

      <header className="relative z-10 mx-auto flex max-w-7xl items-center justify-between px-6 py-6 sm:px-10">
        <Link href="/welcome" className="group flex items-center gap-2.5">
          <OasisLogo size={36} priority className="transition-shadow group-hover:shadow-[0_0_28px_-2px_rgba(0,212,255,0.8)]" />
          <div className="leading-none">
            <div className="font-black tracking-tight text-fg">OASIS AI</div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-fg-dim">Desktop Alpha</div>
          </div>
        </Link>
        <nav className="flex items-center gap-3 sm:gap-5">
          <Link href="/welcome" className="text-sm text-fg-muted transition-colors hover:text-fg">
            Command Center
          </Link>
          <a href={RELEASE_URL} target="_blank" rel="noopener noreferrer" className="btn-secondary !px-3.5 !py-2 text-xs">
            GitHub Release
          </a>
        </nav>
      </header>

      <section className="relative z-10 mx-auto grid max-w-7xl gap-8 px-6 pb-16 pt-12 sm:px-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
        <div>
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/5 px-3 py-1 text-xs text-accent">
            <MonitorDown className="h-3.5 w-3.5" /> Desktop alpha - v{VERSION}
          </div>
          <h1 className="text-5xl font-black leading-[1.04] tracking-tight text-fg sm:text-7xl">
            Download{" "}
            <span className="bg-gradient-to-r from-accent via-cyan-300 to-accent bg-clip-text text-transparent">
              OASIS Desktop.
            </span>
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-fg-muted sm:text-xl">
            This is the installable shell for the OASIS Agent Command Center. It is not a Chrome extension.
            It runs as a desktop app and prepares the local runtime for files, tools, automations, and provider-powered agents.
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            <a href={AUTO_DOWNLOAD_URL} className="btn-send sm:col-span-2 !justify-center !px-5 !py-4 text-base">
              <Download className="h-5 w-5" /> Download for this computer
            </a>
            <a href={WINDOWS_PORTABLE_URL} className="btn-secondary !px-5 !py-3 text-sm">
              <Download className="h-4 w-4" /> Windows portable zip
            </a>
            <a href={WINDOWS_INSTALLER_URL} className="btn-secondary !px-5 !py-3 text-sm">
              <Download className="h-4 w-4" /> Windows installer alpha
            </a>
            <a href={MAC_DMG_URL} className="btn-secondary !px-5 !py-3 text-sm">
              <Download className="h-4 w-4" /> Mac dmg only
            </a>
            <a href={LINUX_APPIMAGE_URL} className="btn-secondary !px-5 !py-3 text-sm">
              <Download className="h-4 w-4" /> Linux AppImage
            </a>
            <a href={LINUX_DEB_URL} className="btn-secondary !px-5 !py-3 text-sm">
              <Download className="h-4 w-4" /> Linux deb
            </a>
            <a href={CHECKSUM_URL} target="_blank" rel="noopener noreferrer" className="btn-secondary !px-5 !py-3 text-sm">
              SHA-256 checksum
            </a>
          </div>
          <div className="mt-4 rounded-xl border border-accent/25 bg-accent/10 p-4 text-sm leading-relaxed text-fg-muted">
            <strong className="text-fg">Windows note:</strong> use the portable zip first. A Mac <span className="font-mono text-accent">.dmg</span>{" "}
            will make Windows ask you to pick an app, and an unsigned installer can be blocked by corporate security while it runs from Temp.
            Save the zip to Downloads, extract it, then open <span className="font-mono text-accent">OASIS AI.exe</span> from the extracted folder.
            SmartScreen will warn this build is from an unknown publisher — that&apos;s expected on the unsigned alpha.
            Click <span className="font-mono text-accent">More info</span> then <span className="font-mono text-accent">Run anyway</span>.
          </div>
          <div className="mt-3 rounded-xl border border-amber-300/25 bg-amber-300/10 p-4 text-sm leading-relaxed text-fg-muted">
            <strong className="text-fg">macOS note:</strong> Gatekeeper will say <em>&quot;Apple cannot verify that OASIS AI is free of malware.&quot;</em>{" "}
            This alpha is not yet Apple Developer ID-signed. Two ways to open it:
            <ul className="mt-2 space-y-1.5 list-disc pl-5">
              <li>
                <strong className="text-fg">Right-click → Open</strong> the app in Applications, then click <span className="font-mono text-amber-200">Open</span> in
                the warning dialog. macOS will trust it for future launches.
              </li>
              <li>
                Or run this once in Terminal to clear the quarantine flag:
                <pre className="mt-1.5 overflow-x-auto rounded-lg border border-amber-300/20 bg-bg-deep/80 px-3 py-2 font-mono text-xs text-amber-100">
                  xattr -d com.apple.quarantine &quot;/Applications/OASIS AI.app&quot;
                </pre>
              </li>
            </ul>
          </div>
          <div className="mt-5 rounded-xl border border-bg-border bg-bg-elev/50 p-4 font-mono text-xs text-fg-dim">
            <div className="mb-2 uppercase tracking-[0.14em] text-fg-muted">Current checksums</div>
            <div className="space-y-1">
              {CHECKSUMS.map((checksum) => (
                <div key={checksum} className="break-all text-accent">{checksum}</div>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-3xl border border-accent/25 bg-bg-elev/55 p-5 shadow-[0_28px_100px_-36px_rgba(0,212,255,0.55)] backdrop-blur-xl">
          <div className="rounded-2xl border border-bg-border bg-bg-deep/80 p-5">
            <div className="mb-4 flex items-center justify-between border-b border-bg-border pb-4">
              <div>
                <div className="text-xs uppercase tracking-[0.18em] text-accent">OASIS AI</div>
                <div className="text-lg font-black">Desktop Product Model</div>
              </div>
              <div className="rounded-full border border-accent/35 bg-accent/10 px-3 py-1 font-mono text-[10px] text-accent">
                {CHANNEL}
              </div>
            </div>
            <div className="space-y-3">
              <ModelRow icon={<KeyRound className="h-4 w-4" />} title="Provider connection" body="OAuth/account sign-in, API key, or OASIS subscription." />
              <ModelRow icon={<Cloud className="h-4 w-4" />} title="Cloud workspace" body="Hosted Command Center with no local file or desktop access." />
              <ModelRow icon={<Cpu className="h-4 w-4" />} title="This desktop" body="Local bridge access for approved files, browser actions, automations, and tools." />
              <ModelRow icon={<Workflow className="h-4 w-4" />} title="Target contract" body="Provider connection + runtime access = full agent capability." />
            </div>
          </div>
        </div>
      </section>

      <section className="relative z-10 mx-auto max-w-7xl px-6 pb-24 sm:px-10">
        <div className="grid gap-4 lg:grid-cols-3">
          <Panel title="How To Download" icon={<Download className="h-5 w-5" />}>
            <ol className="space-y-2 text-sm text-fg-muted">
              <li>1. Pick the download for your operating system.</li>
              <li>2. On Windows, use the zip first if your security blocks temp-launched apps.</li>
              <li>3. Install or open the alpha app.</li>
              <li>4. Sign in to the Command Center.</li>
              <li>5. Choose provider connection and desktop access.</li>
            </ol>
          </Panel>
          <Panel title="Chrome Extension?" icon={<XCircle className="h-5 w-5" />}>
            <p className="text-sm leading-relaxed text-fg-muted">
              No. OASIS Desktop is a native desktop app. A Chrome extension may come later for browser-specific capture,
              but the product we are building now is the downloadable desktop runtime.
            </p>
          </Panel>
          <Panel title="Alpha Safety" icon={<ShieldCheck className="h-5 w-5" />}>
            <ul className="space-y-2 text-sm text-fg-muted">
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 text-accent" /> Sandbox and context isolation are enabled.</li>
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 text-accent" /> Support bundles redact obvious secrets.</li>
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 text-accent" /> This build is unsigned and for internal alpha testing.</li>
            </ul>
          </Panel>
        </div>
      </section>
    </main>
  );
}
function ModelRow({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="flex gap-3 rounded-xl border border-bg-border bg-bg-elev/40 p-3">
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg border border-accent/30 bg-accent/12 text-accent">
        {icon}
      </div>
      <div>
        <div className="text-sm font-bold text-fg">{title}</div>
        <div className="text-xs leading-relaxed text-fg-muted">{body}</div>
      </div>
    </div>
  );
}

function Panel({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-bg-border bg-bg-elev/45 p-5 backdrop-blur">
      <div className="mb-3 flex items-center gap-2 text-accent">
        {icon}
        <h2 className="text-sm font-black uppercase tracking-[0.14em] text-fg">{title}</h2>
      </div>
      {children}
    </div>
  );
}
