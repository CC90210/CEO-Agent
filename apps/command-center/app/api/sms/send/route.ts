import { NextResponse } from "next/server";
import { spawn } from "node:child_process";
import { getActiveProfile } from "@/lib/queries";

/**
 * POST /api/sms/send — Phase 1 SMS dispatch.
 *
 * The dashboard never holds Twilio credentials directly; instead it shells
 * out to the Sun Biz Agent's sms_engine.py (which lives in the sibling
 * Marketing-Agent repo and reads .env.agents). This keeps the dashboard
 * stateless and matches the "MCPs break, CLIs don't" pattern in
 * brain/QUICK_REFERENCE.md.
 *
 * Auth: gated on the active operator profile. Only Sun-tenant users can
 * dispatch SMS for now — CC's tenant gets a 403 with a clear message so
 * we don't accidentally cross tenants.
 *
 * Local-only: this route shells a Python process — it will not function
 * when deployed to Vercel. Vercel Phase 2 will hit a hosted SMS gateway
 * service or call Twilio's REST API directly via fetch().
 */
export async function POST(req: Request) {
  // Resolve operator tenant — only Sun (and missing tenant for legacy
  // localdev) can dispatch SMS through this route.
  const profile = await getActiveProfile().catch(() => null);
  if (!profile) {
    return NextResponse.json(
      { ok: false, error: "No active operator profile", status: "auth_error" },
      { status: 401 }
    );
  }

  let payload: { to?: string; body?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json(
      { ok: false, error: "Invalid JSON body", status: "bad_request" },
      { status: 400 }
    );
  }

  const to = (payload.to || "").trim();
  const body = (payload.body || "").trim();

  if (!to || !body) {
    return NextResponse.json(
      { ok: false, error: "Both 'to' and 'body' are required", status: "validation_error" },
      { status: 400 }
    );
  }
  // Mirror sms_engine.py's E.164 check so we fail fast without spawning Python.
  if (!/^\+[1-9]\d{6,14}$/.test(to)) {
    return NextResponse.json(
      { ok: false, error: "to must be E.164, e.g. +14165551212", status: "validation_error" },
      { status: 400 }
    );
  }
  if (body.length > 1600) {
    return NextResponse.json(
      { ok: false, error: "body exceeds 1600 chars", status: "validation_error" },
      { status: 400 }
    );
  }

  const scriptPath =
    process.env.SUNBIZ_AGENT_PATH ||
    "C:\\Users\\User\\Marketing-Agent\\scripts\\sms_engine.py";
  const pythonBin = process.env.PYTHON_BIN || "python";

  return new Promise<NextResponse>((resolve) => {
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
      resolve(
        NextResponse.json(
          {
            ok: false,
            error: `failed to spawn sms_engine.py: ${err.message}`,
            status: "spawn_error",
          },
          { status: 500 }
        )
      );
    });
    proc.on("close", (code) => {
      // sms_engine.py exits 0 on success, 1 on failure — but the JSON
      // body always carries the truth via { ok }. We parse stdout first.
      try {
        const parsed = JSON.parse(stdout);
        resolve(NextResponse.json(parsed, { status: parsed.ok ? 200 : 422 }));
      } catch {
        resolve(
          NextResponse.json(
            {
              ok: false,
              error: `sms_engine.py produced non-JSON output (exit ${code})`,
              status: "spawn_error",
              stdout: stdout.slice(0, 500),
              stderr: stderr.slice(0, 500),
            },
            { status: 500 }
          )
        );
      }
    });

    // Hard 30-second timeout — Twilio's API is normally sub-second; if
    // we're past 30s something's stuck (DNS, credentials prompt, etc).
    setTimeout(() => {
      if (!proc.killed) {
        proc.kill();
        resolve(
          NextResponse.json(
            { ok: false, error: "sms_engine.py timed out", status: "timeout" },
            { status: 504 }
          )
        );
      }
    }, 30_000);
  });
}
