/**
 * Browser-side Supabase client. Used by sign-in / sign-up / sign-out forms.
 * Reads the anon key — RLS enforces all access.
 */
"use client";

import { createBrowserClient } from "@supabase/ssr";

export function getBrowserSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anon) {
    throw new Error(
      "Browser Supabase misconfigured: NEXT_PUBLIC_SUPABASE_URL + NEXT_PUBLIC_SUPABASE_ANON_KEY required (set in Vercel env)."
    );
  }
  return createBrowserClient(url, anon);
}
