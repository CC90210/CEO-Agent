import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { getActiveProfile } from "@/lib/queries";

export const metadata: Metadata = {
  title: "OASIS AI · Agent Command Center",
  description:
    "The operating system for your AI agents. Outbound, inbound, decisions, pipeline, and the daily ops plan — all in one place.",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  let profile = null;
  try {
    profile = await getActiveProfile();
  } catch {
    // Misconfigured env — render the shell anyway so the operator sees a useful error
  }

  return (
    <html lang="en">
      <body className="grain">
        <Sidebar
          brand={profile?.brand || "OASIS AI"}
          operatorName={profile?.display_name || profile?.full_name || "Operator"}
          primaryAgent={profile?.primary_agent || "bravo"}
        />
        <main className="ml-60 min-h-screen relative z-10">
          <div className="mx-auto max-w-7xl px-8 py-8">{children}</div>
          <footer className="mx-auto max-w-7xl px-8 py-6 text-xs text-fg-faint">
            <div className="border-t border-bg-border pt-4 flex justify-between">
              <span>
                OASIS AI · Agent Command Center · v1.0
              </span>
              <span>
                "Only good things from now on."
              </span>
            </div>
          </footer>
        </main>
      </body>
    </html>
  );
}
