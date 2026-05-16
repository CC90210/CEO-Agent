import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const STOP_COMMAND_RE = /^(STOP|UNSUBSCRIBE|QUIT|CANCEL|END)$/i;

export function isStopCommand(body: unknown): boolean {
  return typeof body === "string" && STOP_COMMAND_RE.test(body.trim());
}

function findCaslComplianceScript(): string | null {
  const roots = Array.from(new Set([
    process.cwd(),
    resolve(process.cwd(), "../.."),
  ]));

  for (const root of roots) {
    const candidate = join(root, "scripts", "casl_compliance.py");
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

export function suppressPhoneViaCasl(
  phone: string,
  source: "twilio_inbound" | "texttorrent_inbound",
): Promise<{ ok: true } | { ok: false; error: string }> {
  const script = findCaslComplianceScript();
  if (!script) {
    return Promise.resolve({ ok: false, error: "scripts/casl_compliance.py not found" });
  }

  const repoRoot = dirname(dirname(script));
  const pythonBin = process.env.PYTHON_BIN || process.env.PYTHON || "python";

  return new Promise((resolveResult) => {
    let settled = false;
    let stdout = "";
    let stderr = "";
    let timeout: ReturnType<typeof setTimeout> | null = null;

    const finish = (result: { ok: true } | { ok: false; error: string }) => {
      if (settled) return;
      settled = true;
      if (timeout) clearTimeout(timeout);
      resolveResult(result);
    };

    const proc = spawn(
      pythonBin,
      [
        script,
        "suppress-phone",
        "--phone",
        phone,
        "--reason",
        "stop_received",
        "--source",
        source,
      ],
      { cwd: repoRoot, shell: false },
    );

    timeout = setTimeout(() => {
      if (!settled) {
        proc.kill();
        finish({ ok: false, error: "casl_compliance.py suppress-phone timed out" });
      }
    }, 10_000);

    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });
    proc.on("error", (err) => {
      finish({ ok: false, error: err.message });
    });
    proc.on("close", (code) => {
      if (code === 0) {
        finish({ ok: true });
      } else {
        const detail = (stderr || stdout || `exit ${code}`).slice(0, 500);
        finish({ ok: false, error: detail });
      }
    });
  });
}
