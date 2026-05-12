import { createHmac } from "crypto";
import { spawn } from "node:child_process";
import type { ClientCommandCenterProfile } from "./client-profiles";

type SmsDispatchResult = {
  status: number;
  body: Record<string, unknown>;
};

type DispatchSmsInput = {
  clientProfile: ClientCommandCenterProfile;
  tenantSlug: string | null;
  to: string;
  body: string;
};

function _env(name?: string): string {
  if (!name) return "";
  return (process.env[name] || "").trim();
}

function _withDefaultPath(pathname: string | undefined): string {
  if (!pathname) return "/sms/send";
  return pathname.startsWith("/") ? pathname : `/${pathname}`;
}

async function _dispatchSmsRemote({
  clientProfile,
  tenantSlug,
  to,
  body,
}: DispatchSmsInput): Promise<SmsDispatchResult> {
  const sms = clientProfile.sms;
  const baseUrl = _env(sms?.remoteBaseUrlEnv);
  if (!baseUrl) {
    return {
      status: 503,
      body: {
        ok: false,
        error: `Missing hosted agent URL env ${sms?.remoteBaseUrlEnv || "(unset)"}`,
        status: "agent_unconfigured",
      },
    };
  }

  const payload = JSON.stringify({
    to,
    body,
    tenant_slug: tenantSlug,
    client_profile: clientProfile.id,
  });
  const secret = _env(sms?.sharedSecretEnv);
  const headers: Record<string, string> = {
    "content-type": "application/json",
    "x-oasis-tenant-slug": tenantSlug || clientProfile.id,
    "x-oasis-client-profile": clientProfile.id,
  };
  if (secret) {
    if ((sms?.authMode || "none") === "bearer") {
      headers.authorization = `Bearer ${secret}`;
    } else if ((sms?.authMode || "none") === "hmac") {
      const timestamp = Math.floor(Date.now() / 1000).toString();
      const signature = createHmac("sha256", secret)
        .update(`${timestamp}.${payload}`, "utf8")
        .digest("hex");
      headers["x-oasis-timestamp"] = timestamp;
      headers["x-oasis-signature"] = signature;
    }
  }

  const url = `${baseUrl.replace(/\/+$/, "")}${_withDefaultPath(sms?.remotePath)}`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: payload,
      cache: "no-store",
    });
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const parsed = (await res.json()) as Record<string, unknown>;
      return { status: res.status, body: parsed };
    }
    const raw = await res.text();
    return {
      status: res.status,
      body: {
        ok: res.ok,
        error: raw || `Hosted agent returned ${res.status}`,
        status: res.ok ? "ok" : "agent_error",
      },
    };
  } catch (err) {
    return {
      status: 502,
      body: {
        ok: false,
        error: err instanceof Error ? err.message : "Hosted agent request failed",
        status: "agent_unreachable",
      },
    };
  }
}

function _dispatchSmsLocal({
  clientProfile,
  to,
  body,
}: DispatchSmsInput): Promise<SmsDispatchResult> {
  const sms = clientProfile.sms;
  const scriptPath =
    _env(sms?.localScriptEnv) || sms?.localScriptPath || "";
  const pythonBin = _env(sms?.localPythonEnv) || "python";
  if (!scriptPath) {
    return Promise.resolve({
      status: 503,
      body: {
        ok: false,
        error: "Local SMS fallback is enabled but no script path is configured",
        status: "agent_unconfigured",
      },
    });
  }

  return new Promise<SmsDispatchResult>((resolve) => {
    const proc = spawn(
      pythonBin,
      [scriptPath, "send", "--to", to, "--body", body, "--provider", "twilio", "--json"],
      { shell: false }
    );

    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf-8");
    });
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf-8");
    });
    proc.on("error", (err) => {
      resolve({
        status: 500,
        body: {
          ok: false,
          error: `failed to spawn sms_engine.py: ${err.message}`,
          status: "spawn_error",
        },
      });
    });
    proc.on("close", (code) => {
      try {
        const parsed = JSON.parse(stdout) as Record<string, unknown>;
        resolve({ status: parsed.ok ? 200 : 422, body: parsed });
      } catch {
        resolve({
          status: 500,
          body: {
            ok: false,
            error: `sms_engine.py produced non-JSON output (exit ${code})`,
            status: "spawn_error",
            stdout: stdout.slice(0, 500),
            stderr: stderr.slice(0, 500),
          },
        });
      }
    });

    setTimeout(() => {
      if (!proc.killed) {
        proc.kill();
        resolve({
          status: 504,
          body: { ok: false, error: "sms_engine.py timed out", status: "timeout" },
        });
      }
    }, 30_000);
  });
}

export async function dispatchSmsThroughClientAgent(
  input: DispatchSmsInput
): Promise<SmsDispatchResult> {
  const sms = input.clientProfile.sms;
  if (!sms?.enabled) {
    return {
      status: 403,
      body: {
        ok: false,
        error: `SMS is not enabled for client profile ${input.clientProfile.id}`,
        status: "unsupported",
      },
    };
  }

  const remoteBaseUrl = _env(sms.remoteBaseUrlEnv);
  if (remoteBaseUrl) {
    return _dispatchSmsRemote(input);
  }

  if (sms.allowLocalFallback && process.env.NODE_ENV !== "production") {
    return _dispatchSmsLocal(input);
  }

  return {
    status: 503,
    body: {
      ok: false,
      error: `No hosted SMS agent is configured for client profile ${input.clientProfile.id}`,
      status: "agent_unconfigured",
      expected_env: sms.remoteBaseUrlEnv || null,
      data_backend: input.clientProfile.dataBackend,
      deployment_mode: input.clientProfile.deploymentMode,
    },
  };
}
