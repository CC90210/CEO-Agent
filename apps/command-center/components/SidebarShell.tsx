"use client";

/**
 * SidebarShell — mobile-aware wrapper around Sidebar.
 *
 * Desktop (md and up): identical to rendering <Sidebar> directly —
 * always-visible 240px aside on the left.
 *
 * Mobile (< md): Sidebar collapses off-screen by default. A fixed top
 * bar with a hamburger button toggles a slide-in drawer. Tapping any
 * nav link closes the drawer (via pathname-change effect). A backdrop
 * absorbs taps outside the drawer.
 *
 * State lives here so server components (the layout) can keep
 * rendering the nav definition as data without going client.
 */

import { useEffect, useRef, useState, type ComponentProps } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { Menu } from "lucide-react";
import { Sidebar } from "./Sidebar";

type SidebarProps = ComponentProps<typeof Sidebar>;

export function SidebarShell(props: SidebarProps) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const hamburgerRef = useRef<HTMLButtonElement | null>(null);

  // Close the drawer whenever the route changes — operator taps a nav
  // link, we slide it shut so they see the page they navigated to.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Lock body scroll while the drawer is open so the page underneath
  // doesn't pan around as the operator scrolls the nav list.
  useEffect(() => {
    if (open) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [open]);

  // Accessibility — keyboard escape + restore focus to the hamburger
  // when the drawer closes. Without these a keyboard user could open
  // the drawer and have no way to dismiss it (no Esc handler) or to
  // get focus back to a sensible anchor after closing.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  useEffect(() => {
    if (!open && hamburgerRef.current && document.activeElement === document.body) {
      // Drawer just closed and nothing else has focus — return it to
      // the hamburger so the next Tab lands somewhere predictable.
      hamburgerRef.current.focus({ preventScroll: true });
    }
  }, [open]);

  return (
    <>
      {/* Mobile top bar — desktop hides this. */}
      <div className="md:hidden fixed top-0 inset-x-0 h-14 z-30 bg-bg-panel border-b border-bg-border flex items-center px-3 gap-3">
        <button
          ref={hamburgerRef}
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open menu"
          aria-expanded={open}
          aria-controls="sidebar-drawer"
          className="inline-flex h-9 w-9 items-center justify-center rounded-md text-fg-muted hover:text-fg hover:bg-bg-elev"
        >
          <Menu className="w-5 h-5" />
        </button>
        <Link href="/" className="text-sm font-bold text-fg truncate">
          {props.brand || "OASIS AI"}
        </Link>
      </div>

      {/* Backdrop — only on mobile, only when drawer is open. md+
          ignores both (drawer is part of the layout there). */}
      {open && (
        <button
          type="button"
          aria-label="Close menu"
          onClick={() => setOpen(false)}
          className="md:hidden fixed inset-0 z-30 bg-black/60 backdrop-blur-sm"
        />
      )}

      {/* The aside itself — Sidebar owns its own close button (mobile)
          via the onMobileClose prop, so the X always tracks the sidebar's
          actual width instead of a magic offset. */}
      <Sidebar {...props} isMobileOpen={open} onMobileClose={() => setOpen(false)} />
    </>
  );
}

