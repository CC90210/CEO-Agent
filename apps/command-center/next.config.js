const path = require("path");
const fs = require("fs");

// Local agent sessions use the repo-level .env.agents file, while Vercel uses
// project env vars. Load it when present so local smoke tests match production.
const agentsEnvPath = path.join(__dirname, "..", "..", ".env.agents");
if (fs.existsSync(agentsEnvPath)) {
  const lines = fs.readFileSync(agentsEnvPath, "utf8").split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const [key, ...rest] = line.split("=");
    const name = key.trim();
    if (!name || process.env[name]) continue;
    let value = rest.join("=").trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[name] = value;
  }
}

// .env.agents uses BRAVO_* names. The browser client needs NEXT_PUBLIC_*
// aliases for the public Supabase URL + anon key. Do not alias service-role.
process.env.NEXT_PUBLIC_SUPABASE_URL ||= process.env.BRAVO_SUPABASE_URL || "";
process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||= process.env.BRAVO_SUPABASE_ANON_KEY || "";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Scope file tracing to this app dir only — without this, Next.js scans
  // the parent repo and hits locked tmp/* files (e.g. the Skool browser
  // daemon's cookie store) during 'Collecting build traces', failing builds
  // with EBUSY. App is fully self-contained anyway.
  outputFileTracingRoot: path.join(__dirname),
  // V6.0 Docker deployment — produce .next/standalone with a self-contained
  // server.js + trimmed node_modules. Required by infra/Dockerfile.commandcenter.
  // No effect on Vercel (Vercel uses its own builder; this just enables an
  // additional output directory).
  output: "standalone",
};

module.exports = nextConfig;
