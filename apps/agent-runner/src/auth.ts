import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { createRemoteJWKSet, jwtVerify, type JWTPayload } from "jose";
import type { IncomingMessage } from "node:http";

export type AuthenticatedContext = {
  accessToken: string;
  userId: string;
  email: string | null;
  profileId: string;
  tenantId: string;
  tenantSlug: string | null;
  tenantName: string | null;
  canUseManagedAuth: boolean;
  origin: string | null;
};

type UserProfileRow = {
  id: string;
  tenant_id: string;
  email: string | null;
};

type TenantRow = {
  id: string;
  slug: string | null;
  name: string | null;
  custom_fields: Record<string, unknown> | null;
};

let supabaseAdmin: SupabaseClient | null = null;
let jwks: ReturnType<typeof createRemoteJWKSet> | null = null;

function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required env: ${name}`);
  }
  return value;
}

function supabaseUrl(): string {
  return (
    process.env.BRAVO_SUPABASE_URL ||
    process.env.SUPABASE_URL ||
    requiredEnv("BRAVO_SUPABASE_URL")
  );
}

export function getSupabaseAdmin(): SupabaseClient {
  if (supabaseAdmin) return supabaseAdmin;
  const url = supabaseUrl();
  const key =
    process.env.BRAVO_SUPABASE_SERVICE_ROLE_KEY ||
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    requiredEnv("BRAVO_SUPABASE_SERVICE_ROLE_KEY");

  supabaseAdmin = createClient(url, key, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
    },
  });

  return supabaseAdmin;
}

function allowedOrigins(): string[] {
  return (process.env.RUNNER_ALLOWED_ORIGINS || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

export function resolveCorsOrigin(req: IncomingMessage): string | null {
  const origin = req.headers.origin ?? null;
  if (!origin) return null;
  if (allowedOrigins().length === 0) return origin;
  return allowedOrigins().includes(origin) ? origin : null;
}

export function buildCorsHeaders(origin: string | null): Record<string, string> {
  const allowOrigin = origin ?? allowedOrigins()[0] ?? "*";
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Headers": "authorization, content-type, last-event-id",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Credentials": "false",
    "Vary": "Origin",
  };
}

function bearerToken(req: IncomingMessage): string {
  const authHeader = req.headers.authorization || "";
  const [scheme, token] = authHeader.split(" ");
  if (scheme !== "Bearer" || !token) {
    throw new Error("Missing bearer token.");
  }
  return token;
}

async function verifySupabaseJwt(token: string): Promise<JWTPayload> {
  if (!jwks) {
    jwks = createRemoteJWKSet(
      new URL(`${supabaseUrl()}/auth/v1/.well-known/jwks.json`)
    );
  }

  const { payload } = await jwtVerify(token, jwks, {
    issuer: `${supabaseUrl()}/auth/v1`,
    audience: "authenticated",
  });

  return payload;
}

export async function requireAuth(
  req: IncomingMessage
): Promise<AuthenticatedContext> {
  const origin = resolveCorsOrigin(req);
  if (req.headers.origin && !origin) {
    throw new Error("Origin is not allowed for this runner.");
  }

  const accessToken = bearerToken(req);
  const payload = await verifySupabaseJwt(accessToken);
  const userId = String(payload.sub || "");
  const email = typeof payload.email === "string" ? payload.email : null;

  if (!userId) {
    throw new Error("JWT did not include a subject.");
  }

  const admin = getSupabaseAdmin();
  const profileResult = await admin
    .from("user_profiles")
    .select("id, tenant_id, email")
    .eq("auth_user_id", userId)
    .maybeSingle();

  const profile = profileResult.data as UserProfileRow | null;
  if (!profile?.tenant_id) {
    throw new Error("No user profile is linked to this auth user.");
  }

  const tenantResult = await admin
    .from("tenants")
    .select("id, slug, name, custom_fields")
    .eq("id", profile.tenant_id)
    .maybeSingle();

  const tenant = tenantResult.data as TenantRow | null;
  if (!tenant) {
    throw new Error("Profile tenant could not be resolved.");
  }

  const managedAuthFlag =
    tenant.custom_fields &&
    typeof tenant.custom_fields === "object" &&
    tenant.custom_fields.managed_auth_allowed === true;

  return {
    accessToken,
    userId,
    email,
    profileId: profile.id,
    tenantId: tenant.id,
    tenantSlug: tenant.slug,
    tenantName: tenant.name,
    canUseManagedAuth: managedAuthFlag,
    origin,
  };
}
