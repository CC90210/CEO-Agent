import type { Config } from "tailwindcss";

// OASIS AI Agent Command Center — premium dark theme with OASIS BLUE accent.
// Brand pivot 2026-04-30: gold #e8c547 -> OASIS blue #3b82f6 (with deeper
// #2563eb for muted variants). Status semantics unchanged.
const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./content/**/*.{md,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#06070a",
          panel: "#0e1014",
          raised: "#15181e",
          elev: "#1c2028",
          border: "#22262e",
          hover: "#1a1d24",
        },
        fg: {
          DEFAULT: "#faf9f5",
          muted: "#9ca0a8",
          dim: "#5b6068",
          faint: "#3a3d44",
        },
        accent: {
          DEFAULT: "#3b82f6",        // OASIS blue
          muted: "#2563eb",          // deeper blue
          soft: "rgba(59, 130, 246, 0.12)",
          glow: "rgba(59, 130, 246, 0.35)",
        },
        status: {
          hot: "#ef4444",
          warm: "#f59e0b",
          engaged: "#10b981",
          info: "#60a5fa",
          cold: "#6b7280",
          dormant: "#4b5563",
          lost: "#1f2937",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Inter",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "JetBrains Mono",
          "Consolas",
          "monospace",
        ],
        serif: ["Iowan Old Style", "Palatino Linotype", "Georgia", "serif"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.4s ease-out",
        "slide-up": "slideUp 0.5s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      boxShadow: {
        glow: "0 0 24px rgba(59, 130, 246, 0.22)",
        card: "0 1px 3px rgba(0, 0, 0, 0.4), 0 1px 2px rgba(0, 0, 0, 0.6)",
        elev: "0 8px 24px rgba(0, 0, 0, 0.5)",
      },
    },
  },
  plugins: [],
};

export default config;
