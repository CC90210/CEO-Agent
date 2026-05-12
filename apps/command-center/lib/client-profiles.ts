import { CC_NAV, SUN_NAV, type NavItem } from "./nav-config";
import type { Tenant } from "./supabase";

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
  subtitle: string;
  footerLabel: string;
  footerTagline: string;
  primaryAgent: string;
  dataBackend: ClientDataBackend;
  deploymentMode: ClientDeploymentMode;
  nav: NavItem[];
  sms?: ClientSmsTransport;
};

const DEFAULT_PROFILE: ClientCommandCenterProfile = {
  id: "default",
  brand: "OASIS AI",
  subtitle: "Agent Command Center",
  footerLabel: "OASIS AI · Agent Command Center · v1.0",
  footerTagline: '"Only good things from now on."',
  primaryAgent: "bravo",
  dataBackend: "supabase",
  deploymentMode: "shared",
  nav: CC_NAV,
};

const SUN_PROFILE: ClientCommandCenterProfile = {
  id: "sun",
  brand: "Sun Biz Funding",
  subtitle: "Operations Command",
  footerLabel: "Sun Biz Funding · Operations Command · v1.0",
  footerTagline: "Funded deals over noise.",
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

const CLIENT_PROFILES: Record<string, ClientCommandCenterProfile> = {
  default: DEFAULT_PROFILE,
  sun: SUN_PROFILE,
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
