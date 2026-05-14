/**
 * Demo-mode link anchoring.
 *
 * In a public demo (e.g. /demo/sun) the shell renders client branding but the
 * underlying routes (/agent, /leads, /renewals, ...) are auth-gated and
 * tenant-scoped, so navigating to them either bounces unauth visitors to
 * /login or — worse for authed previewers — silently re-renders the OASIS
 * shell with the demo cookie still set. Until Phase 1 ships real /t/<slug>/...
 * tenant routing, the safe answer is "in demo, every link anchors to the
 * demo landing." This helper centralises that rule so the three callsites
 * (Sidebar nav, SunBizDashboard CTAs, SunBizPlaybookIndex CTAs) stay in lockstep.
 */

export function demoHref(
  realHref: string,
  opts: { demoMode?: boolean; landingPath?: string } = {}
): string {
  if (!opts.demoMode) return realHref;
  return opts.landingPath || "/demo/sun";
}
