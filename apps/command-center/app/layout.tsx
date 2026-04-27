import type { Metadata } from "next";
import "./globals.css";
import { Nav } from "@/components/Nav";

export const metadata: Metadata = {
  title: "Bravo — Command Center",
  description:
    "CC's unified view of every agent, every outbound, every inbound, every decision.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <Nav />
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        <footer className="mx-auto max-w-6xl px-6 py-8 text-xs text-fg-dim">
          <div className="border-t border-bg-border pt-4">
            Bravo V5.6 · Outbound Chokepoint + Reasoning Loop · Data:{" "}
            <span className="font-mono">BRAVO_SUPABASE_URL</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
