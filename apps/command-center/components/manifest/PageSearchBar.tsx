"use client";

/**
 * PageSearchBar — universal client-side search input that writes the
 * query to the URL as ?q=<text>.
 *
 * Mounted above the Kanban / Table on every list-flavored page kind
 * (offers / funded-deals / renewals / commissions / lenders, plus any
 * future entity surface). The server-side renderer (ManifestKanban,
 * ManifestTable) reads `searchParams.q` and filters its rows in-memory
 * before render.
 *
 * Why URL-state rather than client-only local state:
 *   - shareable links: an operator can send "/t/sun/renewals?q=acme"
 *     to a teammate
 *   - keeps the Kanban + Table both server-rendered (no full client
 *     refactor required to add search to existing entity pages)
 *   - Next.js router.replace updates the URL without a full reload;
 *     the searchParams change reruns the page render and re-fetches
 *     the filtered rows
 *
 * Debounce: 250ms. Fast enough to feel instant; slow enough that
 * typing "acme construction" doesn't fire 16 navigation events. The
 * keystroke-to-server-filter round-trip is sub-100ms on typical
 * deploys so the operator sees results well under a second after
 * stopping typing.
 *
 * Layout: full-width input with a clear button and an optional
 * "+ New <entity>" CTA on the right. Mirrors the Salesforce list-view
 * header pattern Adon pattern-matches against from his current CRM.
 */

import { useEffect, useState, useTransition } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

type Props = {
  /** Singular noun used in the placeholder copy + + New CTA. */
  entityLabel: string;
  /** Optional href for the + New <entity> button. Hidden when omitted. */
  newHref?: string;
};

export function PageSearchBar({ entityLabel, newHref }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const initial = searchParams.get("q") || "";

  const [value, setValue] = useState(initial);
  const [, startTransition] = useTransition();

  // Sync state when the URL changes from underneath us (e.g. the
  // operator clicked a chevron filter or navigated back/forward).
  useEffect(() => {
    setValue(searchParams.get("q") || "");
  }, [searchParams]);

  // Debounced URL write — 250ms after the operator stops typing.
  useEffect(() => {
    const next = value.trim();
    const current = searchParams.get("q") || "";
    if (next === current.trim()) return;
    const t = setTimeout(() => {
      const params = new URLSearchParams(Array.from(searchParams.entries()));
      if (next) params.set("q", next);
      else params.delete("q");
      const qs = params.toString();
      startTransition(() => {
        router.replace(qs ? `${pathname}?${qs}` : pathname);
      });
    }, 250);
    return () => clearTimeout(t);
  }, [value, pathname, router, searchParams]);

  return (
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
        <input
          type="search"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={`Search ${entityLabel.toLowerCase()}s by name, email, phone, amount…`}
          className="w-full rounded-md border border-bg-border bg-bg-deep px-3 py-1.5 text-sm text-fg placeholder:text-fg-dim focus:border-accent focus:outline-none"
          aria-label={`Search ${entityLabel.toLowerCase()}s`}
        />
        {value && (
          <button
            type="button"
            onClick={() => setValue("")}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-fg-dim hover:text-fg text-xs"
            aria-label="Clear search"
          >
            ×
          </button>
        )}
      </div>
      {newHref && (
        <Link
          href={newHref}
          className="shrink-0 inline-flex items-center gap-1 rounded-md bg-accent/15 hover:bg-accent/25 border border-accent/40 text-accent px-3 py-1.5 text-[12px] font-semibold whitespace-nowrap"
        >
          + New {entityLabel.toLowerCase()}
        </Link>
      )}
    </div>
  );
}
