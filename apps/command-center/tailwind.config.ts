import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // OASIS AI brand palette — dark charcoal + gold accent, matches the
        // email templates in funnel_nurture.py and the brand identity across
        // outreach_engine. Stays consistent with what lead recipients see.
        bg: {
          DEFAULT: "#0a0a0a",
          panel: "#111111",
          raised: "#1a1a1a",
          border: "#222222",
        },
        fg: {
          DEFAULT: "#faf9f5",
          muted: "#888888",
          dim: "#555555",
        },
        accent: {
          DEFAULT: "#e8c547",
          muted: "#8a7429",
        },
        status: {
          hot: "#ef4444",
          warm: "#f59e0b",
          engaged: "#10b981",
          cold: "#6b7280",
          dormant: "#4b5563",
          lost: "#1f2937",
        },
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
