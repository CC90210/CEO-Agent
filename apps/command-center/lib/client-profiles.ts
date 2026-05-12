import { CC_NAV, SUN_NAV, SUGA_NAV, type NavItem } from "./nav-config";
import type { Tenant } from "./supabase";

export const DEMO_CLIENT_PROFILE_COOKIE = "oasis_demo_client_profile";

export type ClientDataBackend = "supabase" | "turso";
export type ClientDeploymentMode = "shared" | "dedicated";
export type ClientAgentAuthMode = "none" | "bearer" | "hmac";

export type ClientSmsTransport = {
  enabled: boolean;
  remoteBaseUrlEnv?: string;
  remotePath?: string;
  authMode?: ClientAgentAuthMode;
  sharedSecretEnv?: string;
  localPythonEnv?: string;
  localScriptEnv?: string;
  localScriptPath?: string;
  allowLocalFallback?: boolean;
};

export type ClientCommandCenterProfile = {
  id: string;
  brand: string;
  logo: "oasis" | "sunbiz" | "suga";
  subtitle: string;
  footerLabel: string;
  footerTagline: string;
  agentLabel: string;
  primaryAgent: string;
  dataBackend: ClientDataBackend;
  deploymentMode: ClientDeploymentMode;
  nav: NavItem[];
  sms?: ClientSmsTransport;
};

const DEFAULT_PROFILE: ClientCommandCenterProfile = {
  id: "default",
  brand: "OASIS AI",
  logo: "oasis",
  subtitle: "Agent Command Center",
  footerLabel: "OASIS AI · Agent Command Center · v1.0",
  footerTagline: '"Only good things from now on."',
  agentLabel: "Bravo",
  primaryAgent: "bravo",
  dataBackend: "supabase",
  deploymentMode: "shared",
  nav: CC_NAV,
};

const SUN_PROFILE: ClientCommandCenterProfile = {
  id: "sun",
  brand: "Sun Biz Funding",
  logo: "sunbiz",
  subtitle: "Operations Command",
  footerLabel: "Sun Biz Funding · Operations Command · v1.0",
  footerTagline: "Funded deals over noise.",
  agentLabel: "Solara",
  primaryAgent: "sunbiz",
  // Operator correction (2026-05-11): client data belongs in Turso,
  // even while the shared dashboard shell still lives inside the empire app.
  dataBackend: "turso",
  deploymentMode: "dedicated",
  nav: SUN_NAV,
  sms: {
    enabled: true,
    remoteBaseUrlEnv: "SUNBIZ_AGENT_API_URL",
    remotePath: "/sms/send",
    authMode: "hmac",
    sharedSecretEnv: "SUNBIZ_AGENT_HMAC_SECRET",
    localPythonEnv: "PYTHON_BIN",
    localScriptEnv: "SUNBIZ_AGENT_PATH",
    localScriptPath: "C:\\Users\\User\\Marketing-Agent\\scripts\\sms_engine.py",
    allowLocalFallback: true,
  },
};

const SUGA_PROFILE: ClientCommandCenterProfile = {
  id: "suga",
  brand: "Suga Sean O'Malley",
  logo: "suga",
  subtitle: "Brand Command",
  footerLabel: "Suga · Brand Command · v0.1",
  footerTagline: "Fans first. Always.",
  agentLabel: "Suga",
  primaryAgent: "suga_sean",
  // Brand + fan data is PII-adjacent — Turso local file by default. Cloud
  // override via EMPIRE_DATA_BACKEND=supabase_cloud at runtime if needed.
  dataBackend: "turso",
  deploymentMode: "dedicated",
  nav: SUGA_NAV,
};

const CLIENT_PROFILES: Record<string, ClientCommandCenterProfile> = {
  default: DEFAULT_PROFILE,
  sun: SUN_PROFILE,
  suga: SUGA_PROFILE,
};

function _readTenantProfileSlug(
  tenant: Pick<Tenant, "slug" | "custom_fields"> | null | undefined
): string | null {
  if (!tenant) return null;
  const custom = (tenant.custom_fields || {}) as Record<string, unknown>;
  const customSlug =
    custom.command_center_profile_slug ||
    custom.command_center_profile ||
    custom.dashboard_profile_slug ||
    custom.dashboard_profile;
  if (typeof customSlug === "string" && customSlug.trim()) {
    return customSlug.trim().toLowerCase();
  }
  if (typeof tenant.slug === "string" && tenant.slug.trim()) {
    return tenant.slug.trim().toLowerCase();
  }
  return null;
}

export function resolveClientProfileSlug(
  tenant: Pick<Tenant, "slug" | "custom_fields"> | null | undefined
): string | null {
  return _readTenantProfileSlug(tenant);
}

export function getClientCommandCenterProfile(
  tenantOrSlug?: Pick<Tenant, "slug" | "custom_fields"> | string | null
): ClientCommandCenterProfile {
  const slug =
    typeof tenantOrSlug === "string"
      ? tenantOrSlug.trim().toLowerCase()
      : _readTenantProfileSlug(tenantOrSlug || null);
  if (!slug) return DEFAULT_PROFILE;
  return CLIENT_PROFILES[slug] || DEFAULT_PROFILE;
}

export function getClientCommandCenterProfileById(
  id: string | null | undefined
): ClientCommandCenterProfile {
  if (!id) return DEFAULT_PROFILE;
  return CLIENT_PROFILES[id.trim().toLowerCase()] || DEFAULT_PROFILE;
}

export function getClientProfileSlugForBrand(
  brand: string | null | undefined,
  email?: string | null
): string | null {
  const text = `${brand || ""} ${email || ""}`.toLowerCase();
  const compact = text.replace(/[^a-z0-9]+/g, " ").trim();
  if (
    compact.includes("sun biz") ||
    compact.includes("sunbiz") ||
    (compact.includes("sun") && compact.includes("funding"))
  ) {
    return "sun";
  }
  if (
    compact.includes("suga sean") ||
    compact.includes("sugasean") ||
    compact.includes("o malley") ||
    compact.includes("omalley")
  ) {
    return "suga";
  }
  return null;
}
