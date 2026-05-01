const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Scope file tracing to this app dir only — without this, Next.js scans
  // the parent repo and hits locked tmp/* files (e.g. the Skool browser
  // daemon's cookie store) during 'Collecting build traces', failing builds
  // with EBUSY. App is fully self-contained anyway.
  outputFileTracingRoot: path.join(__dirname),
};

module.exports = nextConfig;
