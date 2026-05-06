import Link from "next/link";
import { Compass, Home } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center px-6 py-16">
      <div className="max-w-md w-full rounded-2xl border border-bg-border bg-bg-elev p-7 space-y-4 text-center">
        <div className="w-12 h-12 mx-auto rounded-lg bg-accent/15 border border-accent/30 flex items-center justify-center text-accent">
          <Compass className="w-6 h-6" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-fg">Page not found</h1>
          <p className="text-sm text-fg-muted mt-1">
            That route doesn&apos;t exist in your Command Center.
          </p>
        </div>
        <div className="flex justify-center pt-1">
          <Link href="/" className="btn-primary inline-flex items-center gap-1.5 text-sm">
            <Home className="w-4 h-4" /> Back to Today
          </Link>
        </div>
      </div>
    </div>
  );
}
