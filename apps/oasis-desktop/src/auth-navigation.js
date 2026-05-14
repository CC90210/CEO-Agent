"use strict";

const DEFAULT_AUTH_TIMEOUT_MS = 10 * 60 * 1000;
const GOOGLE_AUTH_HOSTS = new Set(["accounts.google.com"]);

function parseUrl(value) {
  try {
    return new URL(value);
  } catch {
    return null;
  }
}

function isSupabaseAuthHost(hostname) {
  return hostname === "supabase.co" || hostname.endsWith(".supabase.co");
}

function isSupabaseAuthUrl(parsed) {
  return (
    parsed?.protocol === "https:" &&
    isSupabaseAuthHost(parsed.hostname) &&
    parsed.pathname.startsWith("/auth/v1/")
  );
}

function isGoogleAuthUrl(parsed) {
  return parsed?.protocol === "https:" && GOOGLE_AUTH_HOSTS.has(parsed.hostname);
}

function hasTrustedRedirectTarget(parsed, allowedOrigins) {
  const redirectCandidates = [
    parsed.searchParams.get("redirect_to"),
    parsed.searchParams.get("redirect_uri"),
    parsed.searchParams.get("next"),
  ].filter(Boolean);

  return redirectCandidates.some((candidate) => {
    const redirect = parseUrl(candidate);
    return !!redirect && allowedOrigins.has(redirect.origin);
  });
}

function isAppCallback(parsed, allowedOrigins) {
  return (
    !!parsed &&
    allowedOrigins.has(parsed.origin) &&
    parsed.pathname.startsWith("/auth/callback")
  );
}

function createAuthNavigationController({
  allowedOrigins,
  now = () => Date.now(),
  timeoutMs = DEFAULT_AUTH_TIMEOUT_MS,
}) {
  let authUntil = 0;

  function isAuthActive() {
    return now() < authUntil;
  }

  function beginAuthFlow() {
    authUntil = now() + timeoutMs;
  }

  function endAuthFlow() {
    authUntil = 0;
  }

  function shouldAllowAuthNavigation(targetUrl) {
    const parsed = parseUrl(targetUrl);
    if (!parsed) return false;

    if (isAppCallback(parsed, allowedOrigins)) {
      endAuthFlow();
      return true;
    }

    if (isSupabaseAuthUrl(parsed) && hasTrustedRedirectTarget(parsed, allowedOrigins)) {
      beginAuthFlow();
      return true;
    }

    if (isAuthActive() && (isSupabaseAuthUrl(parsed) || isGoogleAuthUrl(parsed))) {
      return true;
    }

    return false;
  }

  function noteAllowedAppNavigation(targetUrl) {
    const parsed = parseUrl(targetUrl);
    if (isAppCallback(parsed, allowedOrigins)) endAuthFlow();
  }

  return {
    beginAuthFlow,
    endAuthFlow,
    isAuthActive,
    noteAllowedAppNavigation,
    shouldAllowAuthNavigation,
  };
}

module.exports = {
  createAuthNavigationController,
  hasTrustedRedirectTarget,
  isGoogleAuthUrl,
  isSupabaseAuthUrl,
};
