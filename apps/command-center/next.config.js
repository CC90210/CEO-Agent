/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Serverless Supabase reads only — no custom image loader, no edge middleware needed for v1.
  experimental: {},
};

module.exports = nextConfig;
