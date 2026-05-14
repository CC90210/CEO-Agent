"use strict";

const assert = require("node:assert/strict");
const { createAuthNavigationController } = require("../src/auth-navigation");

let currentTime = 1_000;
const allowedOrigins = new Set([
  "https://agent-dashboard-cc90210.vercel.app",
  "http://localhost:3100",
]);
const controller = createAuthNavigationController({
  allowedOrigins,
  now: () => currentTime,
  timeoutMs: 5_000,
});

function expectAllowed(url, message) {
  assert.equal(controller.shouldAllowAuthNavigation(url), true, message);
}

function expectDenied(url, message) {
  assert.equal(controller.shouldAllowAuthNavigation(url), false, message);
}

expectDenied("https://accounts.google.com/o/oauth2/v2/auth", "Google auth is denied before an OAUTH flow starts");
expectDenied("https://evil.supabase.co/rest/v1/users", "non-auth Supabase routes are denied");
expectDenied(
  "https://project.supabase.co/auth/v1/authorize?redirect_to=https%3A%2F%2Fevil.example%2Fauth%2Fcallback",
  "Supabase auth is denied when redirect_to is not a trusted Command Center origin"
);

expectAllowed(
  "https://project.supabase.co/auth/v1/authorize?provider=google&redirect_to=https%3A%2F%2Fagent-dashboard-cc90210.vercel.app%2Fauth%2Fcallback",
  "Supabase auth with trusted redirect_to starts the desktop OAuth flow"
);
assert.equal(controller.isAuthActive(), true, "OAuth flow becomes active");

expectAllowed("https://accounts.google.com/o/oauth2/v2/auth", "Google auth is allowed while the OAuth flow is active");
expectAllowed("https://project.supabase.co/auth/v1/callback", "Supabase auth callback is allowed while active");
expectAllowed("https://agent-dashboard-cc90210.vercel.app/auth/callback?code=abc", "Command Center callback is allowed");
assert.equal(controller.isAuthActive(), false, "Command Center callback ends the OAuth flow");

expectDenied("https://accounts.google.com/o/oauth2/v2/auth", "Google auth is denied again after callback");

expectAllowed(
  "https://project.supabase.co/auth/v1/authorize?provider=google&redirect_to=http%3A%2F%2Flocalhost%3A3100%2Fauth%2Fcallback",
  "loopback development callback can start the OAuth flow"
);
currentTime += 5_001;
expectDenied("https://accounts.google.com/o/oauth2/v2/auth", "OAuth flow expires after timeout");

console.log("OK  desktop auth navigation checks passed");
