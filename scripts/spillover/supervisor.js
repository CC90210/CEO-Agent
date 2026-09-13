#!/usr/bin/env node
"use strict";
/**
 * Claude Spillover supervisor — CONTRACT.md §10-11.
 *
 * The cluster primary. It:
 *   - holds the proxy port: one cluster worker runs spillover_proxy.js and shares the primary's handle;
 *   - respawns that worker after 250 ms, backing off to 5 s after 5 crashes within 60 s;
 *   - runs OmniRoute as a separate child with an allowlisted env and restarts it with backoff (5 s -> 60 s);
 *   - stops on SIGINT / SIGTERM, or when HOME_DIR/state/supervisor.stop appears (polled every 2 s).
 *
 * Exit codes: 0 stopped cleanly, or another instance of ours already serves the port;
 *             1 fatal error; 2 bad arguments; 3 the port is held by a foreign listener.
 *
 * Secrets (fetched with `lane_key.py get`) live only in this process's memory and in OmniRoute's env.
 * They never reach argv, a log line or a file; OmniRoute's own output is redacted before it is logged.
 * Zero npm dependencies.
 */

const cluster = require("node:cluster");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const { execFile, execFileSync, spawn } = require("node:child_process");

const IS_WIN = process.platform === "win32";

const LOG_ROTATE_BYTES = 5 * 1024 * 1024;
const STOP_POLL_MS = 2000;
const WORKER_RESPAWN_MS = 250;
const WORKER_BACKOFF_MS = 5000;
const WORKER_CRASH_WINDOW_MS = 60000;
const WORKER_CRASH_THRESHOLD = 5;
const OMNI_BACKOFF_MIN_MS = 5000;
const OMNI_BACKOFF_MAX_MS = 60000;
const OMNI_STABLE_MS = 60000;
const OMNI_DEFAULT_PORT = 20128;
const PROXY_DEFAULT_PORT = 20131;
const HEALTH_TIMEOUT_MS = 2000;
const SECRET_TIMEOUT_MS = 15000;
const PROCESS_QUERY_TIMEOUT_MS = 20000;
const STALE_EXIT_WAIT_MS = 10000;
const CHILD_EXIT_WAIT_MS = 5000;

// CONTRACT §10: the only inherited variables any child may see.
const ENV_ALLOWLIST = [
  "SystemRoot", "SYSTEMROOT", "PATH", "TEMP", "TMP", "USERPROFILE",
  "LOCALAPPDATA", "APPDATA", "HOME", "COMPUTERNAME",
];
const FORBIDDEN_ENV_PREFIXES = ["ANTHROPIC_", "OPENAI_", "CLAUDE_"];
// env var name -> lane_key.py secret name
// JWT_SECRET and API_KEY_SECRET must be stable across restarts. The backend-only build stubs OmniRoute's
// instrumentation, so ensureSecrets() never runs to generate them. If API_KEY_SECRET changed on restart,
// the lane key would stop validating.
const OMNI_SECRETS = {
  STORAGE_ENCRYPTION_KEY: "storage_encryption",
  INITIAL_PASSWORD: "initial_password",
  JWT_SECRET: "jwt_secret",
  API_KEY_SECRET: "api_key_secret",
};
const OMNI_FIXED_ENV_NAMES = [
  "PORT", "API_PORT", "DASHBOARD_PORT", "OMNIROUTE_SERVER_HOST", "HOSTNAME", "REQUIRE_API_KEY",
  "DATA_DIR", "OMNIROUTE_NO_UPDATE_NOTIFIER", "OMNIROUTE_MEMORY_MB", "NODE_ENV",
];

// CONTRACT §11 flags (all value-taking), plus the supervisor-only --omniroute-cmd.
const TEST_VALUE_FLAGS = [
  "--state-dir", "--anthropic-base", "--omniroute-base", "--lane-key", "--port", "--now-offset", "--omniroute-cmd",
];
const URL_FLAGS = ["--anthropic-base", "--omniroute-base"];
// Flags forwarded verbatim to the proxy worker (never --omniroute-cmd, which is ours alone).
const WORKER_FORWARD_FLAGS = ["--anthropic-base", "--omniroute-base", "--lane-key", "--now-offset"];

// ---------------------------------------------------------------------------------------------------------
// Arguments and config
// ---------------------------------------------------------------------------------------------------------

class UsageError extends Error {}

function flagKey(flag) {
  return flag.replace(/^--/, "").replace(/-([a-z])/g, (_, c) => c.toUpperCase());
}

function isLoopbackHost(hostname) {
  return hostname === "127.0.0.1" || hostname === "localhost";
}

function urlPort(u) {
  if (u.port) return Number(u.port);
  return u.protocol === "https:" ? 443 : 80;
}

/**
 * Production takes no arguments. Test flags are honoured only together with --test and loopback-only
 * URLs; anything else throws UsageError (exit 2). Environment overrides are never read.
 */
function parseArgs(argv) {
  const opts = { test: false, raw: {} };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--test") {
      opts.test = true;
      continue;
    }
    if (!TEST_VALUE_FLAGS.includes(a)) throw new UsageError(`unknown argument: ${a}`);
    const v = argv[i + 1];
    if (v === undefined || v.startsWith("--")) throw new UsageError(`${a} needs a value`);
    if (Object.prototype.hasOwnProperty.call(opts.raw, a)) throw new UsageError(`${a} given twice`);
    opts.raw[a] = v;
    i++;
  }
  const given = Object.keys(opts.raw);
  if (!opts.test) {
    if (given.length) throw new UsageError(`${given.join(", ")} only allowed with --test`);
    return opts;
  }
  if (!opts.raw["--state-dir"]) throw new UsageError("--test requires --state-dir");
  for (const f of URL_FLAGS) {
    const v = opts.raw[f];
    if (v === undefined) continue;
    let u;
    try {
      u = new URL(v);
    } catch {
      throw new UsageError(`${f} is not a valid URL`);
    }
    if (u.protocol !== "http:" && u.protocol !== "https:") throw new UsageError(`${f} must be http(s)`);
    if (!isLoopbackHost(u.hostname)) throw new UsageError(`${f} host must be 127.0.0.1 or localhost`);
    opts[flagKey(f)] = u;
  }
  if (opts.raw["--port"] !== undefined) {
    const p = Number(opts.raw["--port"]);
    if (!Number.isInteger(p) || p < 1 || p > 65535) throw new UsageError("--port must be an integer 1-65535");
    opts.port = p;
  }
  if (opts.raw["--now-offset"] !== undefined && !Number.isFinite(Number(opts.raw["--now-offset"]))) {
    throw new UsageError("--now-offset must be a number of seconds");
  }
  if (opts.raw["--omniroute-cmd"] !== undefined) {
    opts.omnirouteCmd = path.resolve(opts.raw["--omniroute-cmd"]);
    if (!fs.existsSync(opts.omnirouteCmd)) throw new UsageError(`--omniroute-cmd not found: ${opts.omnirouteCmd}`);
  }
  opts.stateDir = path.resolve(opts.raw["--state-dir"]);
  return opts;
}

function defaultHomeDir() {
  if (IS_WIN) {
    const base = process.env.LOCALAPPDATA;
    if (!base) throw new Error("LOCALAPPDATA is not set; cannot resolve HOME_DIR");
    return path.join(base, "bravo-spillover");
  }
  if (process.platform === "darwin") {
    return path.join(os.homedir(), "Library", "Application Support", "bravo-spillover");
  }
  return path.join(os.homedir(), ".local", "share", "bravo-spillover");
}

function loadConfig(homeDir, test) {
  const file = path.join(homeDir, "config.json");
  let raw;
  try {
    raw = fs.readFileSync(file, "utf8");
  } catch (e) {
    if (e.code === "ENOENT" && test) return {};
    throw new Error(`cannot read ${file}: ${e.message}`);
  }
  let cfg;
  try {
    cfg = JSON.parse(raw.replace(/^﻿/, ""));
  } catch (e) {
    throw new Error(`${file} is not valid JSON: ${e.message}`);
  }
  if (!cfg || typeof cfg !== "object" || Array.isArray(cfg)) throw new Error(`${file} must hold a JSON object`);
  return cfg;
}

function asObject(v, name) {
  if (v === undefined || v === null) return {};
  if (typeof v !== "object" || Array.isArray(v)) throw new Error(`config ${name} must be an object`);
  return v;
}

/** Everything the supervisor needs, resolved once at startup. */
function resolveSettings(opts, cfg, homeDir, appDir) {
  const proxy = asObject(cfg.proxy, "proxy");
  const omni = asObject(cfg.omniroute, "omniroute");

  const host = proxy.host === undefined ? "127.0.0.1" : proxy.host;
  if (host !== "127.0.0.1") throw new Error(`proxy.host must be 127.0.0.1, got ${JSON.stringify(host)}`);
  const port = opts.test && opts.port !== undefined ? opts.port : proxy.port === undefined ? PROXY_DEFAULT_PORT : proxy.port;
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error(`proxy.port is invalid: ${port}`);

  // Production OmniRoute always listens on 20128. A test run only starts it on the --omniroute-base port,
  // so a test can never touch the real one.
  let omniPort = OMNI_DEFAULT_PORT;
  if (opts.test) omniPort = opts.omnirouteBase ? urlPort(opts.omnirouteBase) : null;

  const memoryMb = omni.memory_mb === undefined ? 1536 : omni.memory_mb;
  if (!Number.isInteger(memoryMb) || memoryMb <= 0) throw new Error(`omniroute.memory_mb is invalid: ${memoryMb}`);
  const logEnv = asObject(omni.log_env, "omniroute.log_env");

  const pythonExe = typeof cfg.python_exe === "string" && cfg.python_exe ? cfg.python_exe : null;
  // Test mode: --state-dir D *is* HOME_DIR/state, so HOME_DIR = parent of D (same rule as the proxy worker).
  const stateDir = opts.test ? opts.stateDir : path.join(homeDir, "state");
  const logsDir = path.join(stateDir, "logs");
  // omniroute.runtime_dir is the OmniRoute install that serves the fallback leg: the pinned git build
  // (default HOME_DIR/omniroute-src) or an npm install. It may be absolute or relative to HOME_DIR.
  const omniSrc = typeof omni.runtime_dir === "string" && omni.runtime_dir
    ? path.resolve(homeDir, omni.runtime_dir)
    : path.join(homeDir, "omniroute-src");

  const workerArgs = [];
  if (opts.test) {
    workerArgs.push("--test", "--state-dir", opts.stateDir, "--port", String(port));
    for (const f of WORKER_FORWARD_FLAGS) {
      if (opts.raw[f] !== undefined) workerArgs.push(f, opts.raw[f]);
    }
  }

  return {
    test: opts.test,
    homeDir,
    appDir,
    binDir: path.join(homeDir, "bin"),
    stateDir,
    logsDir,
    pidFile: path.join(stateDir, "supervisor.pid"),
    stopFile: path.join(stateDir, "supervisor.stop"),
    proxyScript: path.join(appDir, "spillover_proxy.js"),
    workerArgs,
    pythonExe,
    host,
    port,
    omniEnabled: omni.enabled !== false,
    omniPort,
    omniSrc,
    omniData: path.join(homeDir, "omniroute-data"),
    omniCmd: opts.omnirouteCmd || path.join(omniSrc, "bin", "omniroute.mjs"),
    memoryMb,
    logEnv,
  };
}

// ---------------------------------------------------------------------------------------------------------
// Logs
// ---------------------------------------------------------------------------------------------------------

/** Append-only log file that rotates to <file>.1 once the next write would pass maxBytes. */
class RotatingLog {
  constructor(file, maxBytes = LOG_ROTATE_BYTES) {
    this.file = file;
    this.maxBytes = maxBytes;
    this.fd = null;
    this.size = 0;
  }

  open() {
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    this.fd = fs.openSync(this.file, "a");
    this.size = fs.fstatSync(this.fd).size;
  }

  write(text) {
    if (this.fd === null) this.open();
    const buf = Buffer.from(text, "utf8");
    if (this.size > 0 && this.size + buf.length > this.maxBytes) this.rotate();
    fs.writeSync(this.fd, buf);
    this.size += buf.length;
  }

  rotate() {
    fs.closeSync(this.fd);
    this.fd = null;
    try {
      fs.rmSync(`${this.file}.1`, { force: true });
      fs.renameSync(this.file, `${this.file}.1`);
    } catch (e) {
      // Keep appending to the current file; the next oversized write retries the rotation.
      process.stderr.write(`log rotation failed for ${this.file}: ${e.message}\n`);
    }
    this.open();
  }

  close() {
    if (this.fd === null) return;
    try {
      fs.closeSync(this.fd);
    } catch (e) {
      process.stderr.write(`closing ${this.file} failed: ${e.message}\n`);
    }
    this.fd = null;
  }
}

let supervisorLog = null;
let echoToConsole = true;

function log(level, msg) {
  const line = `${new Date().toISOString()} [${level}] ${msg}\n`;
  if (supervisorLog) {
    try {
      supervisorLog.write(line);
    } catch (e) {
      process.stderr.write(`supervisor.log write failed: ${e.message}\n`);
    }
  }
  if (echoToConsole) (level === "error" ? process.stderr : process.stdout).write(line);
}

// Launched hidden, the console can vanish; the file log stays authoritative.
function guardConsoleStreams() {
  for (const stream of [process.stdout, process.stderr]) {
    stream.on("error", (e) => {
      echoToConsole = false;
      if (supervisorLog) supervisorLog.write(`${new Date().toISOString()} [warn] console echo disabled: ${e.message}\n`);
    });
  }
}

/** Replaces every known secret value with <redacted>. tailKeep = chars that could still start a secret. */
function makeRedactor(secretValues) {
  const values = secretValues.filter((v) => typeof v === "string" && v.length >= 4);
  const longest = values.reduce((m, v) => Math.max(m, v.length), 0);
  const redact = (text) => {
    let out = text;
    for (const v of values) out = out.split(v).join("<redacted>");
    return out;
  };
  redact.tailKeep = Math.max(0, longest - 1);
  return redact;
}

const MAX_PENDING_CHARS = 64 * 1024;

/** Copies a child's output stream into a RotatingLog line by line, redacting secret values first. */
function pipeToLog(stream, logFile, redact) {
  let pending = "";
  const emit = (text) => {
    try {
      logFile.write(text);
    } catch (e) {
      process.stderr.write(`${logFile.file} write failed: ${e.message}\n`);
    }
  };
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    pending += chunk;
    const nl = pending.lastIndexOf("\n");
    if (nl >= 0) {
      emit(redact(pending.slice(0, nl + 1)));
      pending = pending.slice(nl + 1);
    }
    if (pending.length > MAX_PENDING_CHARS) {
      // A huge unterminated line: flush it, holding back a tail that could be the start of a secret.
      const red = redact(pending);
      const cut = red.length - redact.tailKeep;
      emit(red.slice(0, cut));
      pending = red.slice(cut);
    }
  });
  stream.on("end", () => {
    if (pending) emit(`${redact(pending)}\n`);
    pending = "";
  });
}

// ---------------------------------------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------------------------------------

/** CONTRACT §10 allowlist, read from `source`; NODE_EXTRA_CA_CERTS only when that file exists. */
function allowlistedEnv(source) {
  const env = {};
  for (const name of ENV_ALLOWLIST) {
    const v = source[name];
    if (typeof v === "string" && v !== "") env[name] = v;
  }
  const ca = source.NODE_EXTRA_CA_CERTS;
  if (typeof ca === "string" && ca !== "" && fs.existsSync(ca)) env.NODE_EXTRA_CA_CERTS = ca;
  return env;
}

function normEnvKey(k) {
  return IS_WIN ? k.toUpperCase() : k;
}

/**
 * cluster.fork() merges process.env into the worker's env and cannot remove keys, so the only way to
 * give the proxy worker an allowlisted env is to reduce this process's own env to the allowlist first.
 */
function scrubProcessEnv(allowed) {
  const keep = new Set(Object.keys(allowed).map(normEnvKey));
  for (const k of Object.keys(process.env)) {
    if (!keep.has(normEnvKey(k))) delete process.env[k];
  }
}

function hasForbiddenPrefix(name) {
  const upper = name.toUpperCase();
  return FORBIDDEN_ENV_PREFIXES.some((p) => upper.startsWith(p));
}

/** OmniRoute's env: allowlist + config log_env + the fixed launch vars + secrets. */
function buildOmnirouteEnv(baseEnv, s, secrets, warn) {
  const env = { ...baseEnv };
  const reserved = new Set([
    ...OMNI_FIXED_ENV_NAMES, ...Object.keys(OMNI_SECRETS), "NODE_EXTRA_CA_CERTS", "NODE_OPTIONS",
  ]);
  for (const [k, v] of Object.entries(s.logEnv)) {
    if (!/^[A-Z][A-Z0-9_]*$/.test(k) || hasForbiddenPrefix(k) || reserved.has(k)) {
      warn(`omniroute.log_env key ${JSON.stringify(k)} refused (reserved, forbidden or malformed)`);
      continue;
    }
    if (!["string", "number", "boolean"].includes(typeof v)) {
      warn(`omniroute.log_env.${k} refused: value must be a string, number or boolean`);
      continue;
    }
    env[k] = String(v);
  }
  const port = String(s.omniPort);
  Object.assign(env, {
    PORT: port,
    API_PORT: port,
    DASHBOARD_PORT: port,
    OMNIROUTE_SERVER_HOST: "127.0.0.1",
    HOSTNAME: "127.0.0.1",
    REQUIRE_API_KEY: "true",
    DATA_DIR: s.omniData,
    OMNIROUTE_NO_UPDATE_NOTIFIER: "1",
    OMNIROUTE_MEMORY_MB: String(s.memoryMb),
    NODE_ENV: "production",
  });
  for (const [name, value] of Object.entries(secrets)) env[name] = value;
  const bad = Object.keys(env).filter(hasForbiddenPrefix);
  if (bad.length) throw new Error(`refusing to launch omniroute with ${bad.join(", ")} in its env`);
  return env;
}

// ---------------------------------------------------------------------------------------------------------
// Secrets and alerts (both through python_exe; neither ever puts a secret in argv or a log)
// ---------------------------------------------------------------------------------------------------------

/** `python_exe bin/lane_key.py get <name>` -> {ok, value} or {ok:false, why}. `why` never holds output. */
function fetchSecret(s, baseEnv, name) {
  if (!s.pythonExe) return { ok: false, why: "python_exe is not set in config.json" };
  const script = path.join(s.binDir, "lane_key.py");
  if (!fs.existsSync(script)) return { ok: false, why: `${script} not found` };
  let out;
  try {
    out = execFileSync(s.pythonExe, [script, "get", name], {
      env: baseEnv,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      timeout: SECRET_TIMEOUT_MS,
      encoding: "utf8",
      maxBuffer: 64 * 1024,
    });
  } catch (e) {
    // e.message / e.stdout may carry process output: report only the failure shape.
    if (e.code === "ETIMEDOUT") return { ok: false, why: "timed out" };
    if (typeof e.status === "number") return { ok: false, why: `exit ${e.status}` };
    return { ok: false, why: e.code || "spawn failed" };
  }
  const value = out.replace(/[\r\n]+$/, "");
  if (!value) return { ok: false, why: "empty value" };
  return { ok: true, value };
}

/** CONTRACT §14: `<python_exe> <HOME_DIR>/bin/spillover_alert.py <kind> <message>`, detached, never awaited. */
function sendAlert(s, baseEnv, kind, message) {
  const script = path.join(s.binDir, "spillover_alert.py");
  if (!s.pythonExe) {
    log("error", `alert ${kind} NOT sent: python_exe is not set in config.json`);
    return;
  }
  if (!fs.existsSync(script)) {
    log("error", `alert ${kind} NOT sent: ${script} not found`);
    return;
  }
  try {
    const child = spawn(s.pythonExe, [script, kind, message], {
      detached: true,
      windowsHide: true,
      stdio: "ignore",
      env: baseEnv,
      cwd: s.homeDir,
    });
    child.on("error", (e) => log("error", `alert ${kind} spawn failed: ${e.message}`));
    child.unref();
    log("warn", `alert ${kind}: ${message}`);
  } catch (e) {
    log("error", `alert ${kind} spawn failed: ${e.message}`);
  }
}

// ---------------------------------------------------------------------------------------------------------
// Small utilities shared by single-instance, worker and OmniRoute logic
// ---------------------------------------------------------------------------------------------------------

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** true if `pid` is a live process we could see (ESRCH -> dead; EPERM -> alive, just not ours to signal). */
function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return e.code === "EPERM";
  }
}

function writePidFile(s) {
  fs.mkdirSync(path.dirname(s.pidFile), { recursive: true });
  fs.writeFileSync(s.pidFile, String(process.pid));
}

/** Windows-only: `taskkill /T /F` a whole process tree. Resolves regardless of outcome (best effort). */
function killTreeWindows(pid) {
  return new Promise((resolve) => {
    execFile(
      "taskkill",
      ["/T", "/F", "/PID", String(pid)],
      { windowsHide: true, timeout: STALE_EXIT_WAIT_MS },
      () => resolve(),
    );
  });
}

// ---------------------------------------------------------------------------------------------------------
// Single instance (CONTRACT §10-11)
// ---------------------------------------------------------------------------------------------------------

/** Binds host:port and immediately releases it. Resolves true if free, false on EADDRINUSE. */
function probeBind(host, port) {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once("error", (e) => {
      if (e.code === "EADDRINUSE") {
        resolve(false);
        return;
      }
      reject(e);
    });
    srv.once("listening", () => srv.close(() => resolve(true)));
    srv.listen(port, host);
  });
}

/** GET /__spillover/health -> parsed JSON on 200, else null. Never rejects. */
function fetchHealth(host, port, timeoutMs) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (v) => {
      if (done) return;
      done = true;
      resolve(v);
    };
    const req = http.get({ host, port, path: "/__spillover/health", timeout: timeoutMs }, (res) => {
      const chunks = [];
      res.on("data", (c) => chunks.push(c));
      res.on("end", () => {
        if (res.statusCode !== 200) {
          finish(null);
          return;
        }
        try {
          finish(JSON.parse(Buffer.concat(chunks).toString("utf8")));
        } catch {
          finish(null);
        }
      });
      res.on("error", () => finish(null));
    });
    req.on("timeout", () => {
      req.destroy();
      finish(null);
    });
    req.on("error", () => finish(null));
  });
}

// ---------------------------------------------------------------------------------------------------------
// Stale OmniRoute listener (CONTRACT §10): before spawning, kill a leftover process that still owns
// omniPort and whose command line names our omniSrc. The selection rule is a pure function of a process
// table so it can be unit-tested with a fabricated table; only the Windows query beneath it touches the OS.
// ---------------------------------------------------------------------------------------------------------

/**
 * rows: [{pid, port, state, commandLine}, ...] (state defaults to "LISTENING" if omitted).
 * Returns the pid of the first LISTENING row on `port` whose commandLine contains `srcDir`, else null.
 */
function selectStaleOmniOwner(rows, port, srcDir) {
  if (!srcDir || !Array.isArray(rows)) return null;
  const needle = String(srcDir);
  for (const row of rows) {
    if (!row) continue;
    if (Number(row.port) !== Number(port)) continue;
    const state = String(row.state === undefined ? "LISTENING" : row.state).toUpperCase();
    if (state !== "LISTENING") continue;
    const cmd = String(row.commandLine || "");
    if (cmd.includes(needle)) return Number(row.pid);
  }
  return null;
}

/** Windows-only live process table for TCP listeners on `port` (pid, port, state, commandLine). */
function queryWindowsPortOwners(port) {
  return new Promise((resolve, reject) => {
    const script = [
      "$ErrorActionPreference='SilentlyContinue'",
      "$rows=@()",
      `foreach($c in Get-NetTCPConnection -LocalPort ${Number(port)} -State Listen){`,
      '$p=Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)"',
      "$rows+=[PSCustomObject]@{pid=$c.OwningProcess;port=$c.LocalPort;state='LISTENING';commandLine=$p.CommandLine}",
      "}",
      "$rows | ConvertTo-Json -Compress",
    ].join(";");
    execFile(
      "powershell.exe",
      ["-NoProfile", "-NonInteractive", "-Command", script],
      { windowsHide: true, timeout: PROCESS_QUERY_TIMEOUT_MS, maxBuffer: 1024 * 1024 },
      (err, stdout) => {
        if (err) {
          reject(err);
          return;
        }
        const text = String(stdout || "").trim();
        if (!text) {
          resolve([]);
          return;
        }
        try {
          const parsed = JSON.parse(text);
          resolve(Array.isArray(parsed) ? parsed : [parsed]);
        } catch (e) {
          reject(e);
        }
      },
    );
  });
}

async function killStaleOmniListener(s) {
  if (!IS_WIN) return;
  let rows;
  try {
    rows = await queryWindowsPortOwners(s.omniPort);
  } catch (e) {
    log("warn", `stale-listener query failed: ${e.message}`);
    return;
  }
  const pid = selectStaleOmniOwner(rows, s.omniPort, s.omniSrc);
  if (!pid || pid === process.pid) return;
  log("warn", `killing stale omniroute listener pid=${pid} on port ${s.omniPort} (matches ${s.omniSrc})`);
  await killTreeWindows(pid);
  const deadline = Date.now() + STALE_EXIT_WAIT_MS;
  while (pidAlive(pid) && Date.now() < deadline) await sleep(200);
}

// ---------------------------------------------------------------------------------------------------------
// Cluster primary: one worker runs spillover_proxy.js and shares the primary's listening handle.
// Respawns after WORKER_RESPAWN_MS, backing off to WORKER_BACKOFF_MS after WORKER_CRASH_THRESHOLD crashes
// within WORKER_CRASH_WINDOW_MS.
// ---------------------------------------------------------------------------------------------------------

let currentWorker = null;
let workerCrashTimes = [];
let workerRespawnTimer = null;
let shuttingDown = false;

function forkWorker() {
  if (shuttingDown) return;
  const worker = cluster.fork();
  currentWorker = worker;
  log("info", `proxy worker forked pid=${worker.process.pid}`);
  worker.once("exit", (code, signal) => {
    if (currentWorker === worker) currentWorker = null;
    if (shuttingDown) return;
    const now = Date.now();
    workerCrashTimes.push(now);
    workerCrashTimes = workerCrashTimes.filter((t) => now - t <= WORKER_CRASH_WINDOW_MS);
    const delay = workerCrashTimes.length >= WORKER_CRASH_THRESHOLD ? WORKER_BACKOFF_MS : WORKER_RESPAWN_MS;
    log("warn", `proxy worker pid=${worker.process.pid} exited code=${code} signal=${signal}; respawning in ${delay}ms`);
    clearTimeout(workerRespawnTimer);
    // Deliberately not unref'd: this pending respawn is exactly what must keep the supervisor alive
    // between the worker's exit and its replacement, or the whole process could exit before the
    // callback ever runs.
    workerRespawnTimer = setTimeout(forkWorker, delay);
  });
  worker.on("error", (e) => log("error", `proxy worker error: ${e.message}`));
}

function onceWorkerExit(worker, timeoutMs) {
  return new Promise((resolve) => {
    if (worker.isDead()) {
      resolve(true);
      return;
    }
    const t = setTimeout(() => resolve(false), timeoutMs);
    worker.once("exit", () => {
      clearTimeout(t);
      resolve(true);
    });
  });
}

async function stopWorker(worker) {
  if (!worker) return;
  const exited = onceWorkerExit(worker, CHILD_EXIT_WAIT_MS);
  try {
    worker.kill();
  } catch (e) {
    log("warn", `worker kill failed: ${e.message}`);
  }
  const ok = await exited;
  if (!ok && worker.process && worker.process.pid) {
    log("warn", `worker pid=${worker.process.pid} did not exit in time; forcing`);
    if (IS_WIN) await killTreeWindows(worker.process.pid);
    else {
      try {
        worker.process.kill("SIGKILL");
      } catch {
        // already gone
      }
    }
  }
}

// ---------------------------------------------------------------------------------------------------------
// OmniRoute child: allowlisted + secret-bearing env, restarted with backoff (CONTRACT §10, §16).
// ---------------------------------------------------------------------------------------------------------

let omniChild = null;
let omniTimer = null;
let omniBackoffMs = OMNI_BACKOFF_MIN_MS;
let omniStartedAt = 0;

/** Picks the next OmniRoute restart delay and advances the backoff state as a side effect. */
function nextOmniBackoff(ranMs) {
  if (ranMs >= OMNI_STABLE_MS) {
    omniBackoffMs = OMNI_BACKOFF_MIN_MS;
    return omniBackoffMs;
  }
  const delay = omniBackoffMs;
  omniBackoffMs = Math.min(omniBackoffMs * 2, OMNI_BACKOFF_MAX_MS);
  return delay;
}

function scheduleOmni(s, baseEnv, delayMs) {
  if (shuttingDown) return;
  clearTimeout(omniTimer);
  // Not unref'd, for the same reason as workerRespawnTimer above: a pending OmniRoute (re)start is
  // real outstanding work, not background bookkeeping the process should be willing to exit under.
  omniTimer = setTimeout(() => attemptStartOmni(s, baseEnv), delayMs);
}

/** Fetches all four OMNI_SECRETS. Returns {ok:true, secrets} or {ok:false} (already logged + alerted). */
function collectOmniSecrets(s, baseEnv) {
  const secrets = {};
  for (const [envName, secretName] of Object.entries(OMNI_SECRETS)) {
    const r = fetchSecret(s, baseEnv, secretName);
    if (!r.ok) {
      log("error", `omniroute secret ${secretName} unavailable: ${r.why}`);
      sendAlert(s, baseEnv, "omniroute_secrets_missing", `omniroute secret ${secretName} unavailable: ${r.why}`);
      return { ok: false };
    }
    secrets[envName] = r.value;
  }
  return { ok: true, secrets };
}

async function attemptStartOmni(s, baseEnv) {
  if (shuttingDown || !s.omniEnabled) return;
  if (!fs.existsSync(s.omniCmd)) {
    log("info", `omniroute cmd not found, skipping: ${s.omniCmd}`);
    return;
  }
  await killStaleOmniListener(s);
  if (shuttingDown) return;

  const fetched = collectOmniSecrets(s, baseEnv);
  if (!fetched.ok) {
    scheduleOmni(s, baseEnv, nextOmniBackoff(0));
    return;
  }

  let env;
  try {
    env = buildOmnirouteEnv(baseEnv, s, fetched.secrets, (m) => log("warn", m));
  } catch (e) {
    log("error", `refusing to start omniroute: ${e.message}`);
    return;
  }

  fs.mkdirSync(s.omniData, { recursive: true });
  const omniLog = new RotatingLog(path.join(s.logsDir, "omniroute.log"));
  const redact = makeRedactor(Object.values(fetched.secrets));

  let child;
  try {
    child = spawn(
      process.execPath,
      ["--use-system-ca", s.omniCmd, "serve", "--no-open", "--port", String(s.omniPort)],
      { cwd: s.omniSrc, windowsHide: true, env, stdio: ["ignore", "pipe", "pipe"] },
    );
  } catch (e) {
    log("error", `omniroute spawn failed: ${e.message}`);
    scheduleOmni(s, baseEnv, nextOmniBackoff(0));
    return;
  }

  omniChild = child;
  omniStartedAt = Date.now();
  pipeToLog(child.stdout, omniLog, redact);
  pipeToLog(child.stderr, omniLog, redact);
  log("info", `omniroute started pid=${child.pid} port=${s.omniPort}`);

  child.once("exit", (code, signal) => {
    if (omniChild === child) omniChild = null;
    omniLog.close();
    if (shuttingDown) return;
    const delay = nextOmniBackoff(Date.now() - omniStartedAt);
    log("warn", `omniroute pid=${child.pid} exited code=${code} signal=${signal}; restarting in ${delay}ms`);
    scheduleOmni(s, baseEnv, delay);
  });
  child.on("error", (e) => log("error", `omniroute process error: ${e.message}`));
}

async function stopOmni(child) {
  if (!child || !child.pid) return;
  if (IS_WIN) {
    await killTreeWindows(child.pid);
    return;
  }
  const exited = new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) {
      resolve(true);
      return;
    }
    const t = setTimeout(() => resolve(false), CHILD_EXIT_WAIT_MS);
    child.once("exit", () => {
      clearTimeout(t);
      resolve(true);
    });
  });
  try {
    child.kill("SIGTERM");
  } catch {
    // already gone
  }
  if (!(await exited)) {
    try {
      child.kill("SIGKILL");
    } catch {
      // already gone
    }
  }
}

// ---------------------------------------------------------------------------------------------------------
// Shutdown (CONTRACT §10): SIGINT/SIGTERM, or the stop file, polled every STOP_POLL_MS.
// ---------------------------------------------------------------------------------------------------------

function setupShutdown(s) {
  const stopTimer = setInterval(() => {
    if (!shuttingDown && fs.existsSync(s.stopFile)) {
      shutdown(s, "stop file").catch((e) => log("error", `shutdown failed: ${e.message}`));
    }
  }, STOP_POLL_MS);
  // Not unref'd: a supervisor daemon must stay alive on its own polling, not because something else
  // happens to be keeping the event loop busy. It only ever exits via an explicit process.exit().
  for (const sig of ["SIGINT", "SIGTERM"]) {
    process.on(sig, () => {
      shutdown(s, sig).catch((e) => log("error", `shutdown failed: ${e.message}`));
    });
  }
}

async function shutdown(s, reason) {
  if (shuttingDown) return;
  shuttingDown = true;
  log("info", `shutting down (${reason})`);
  clearTimeout(workerRespawnTimer);
  clearTimeout(omniTimer);
  await Promise.all([stopWorker(currentWorker), stopOmni(omniChild)]);
  try {
    fs.rmSync(s.stopFile, { force: true });
  } catch (e) {
    log("warn", `removing stop file failed: ${e.message}`);
  }
  try {
    fs.rmSync(s.pidFile, { force: true });
  } catch (e) {
    log("warn", `removing pid file failed: ${e.message}`);
  }
  log("info", "shutdown complete");
  if (supervisorLog) supervisorLog.close();
  process.exit(0);
}

// ---------------------------------------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------------------------------------

async function main() {
  let opts;
  try {
    opts = parseArgs(process.argv.slice(2));
  } catch (e) {
    if (e instanceof UsageError) {
      console.error(`usage error: ${e.message}`);
      process.exit(2);
    }
    throw e;
  }

  // Test mode never touches the real HOME_DIR: --state-dir *is* HOME_DIR/state, and HOME_DIR/app is
  // where the test stages whichever worker script (real spillover_proxy.js or a stub) it wants run.
  const homeDir = opts.test ? path.dirname(opts.stateDir) : defaultHomeDir();
  const appDir = opts.test ? path.join(homeDir, "app") : __dirname;
  const cfg = loadConfig(homeDir, opts.test);
  const s = resolveSettings(opts, cfg, homeDir, appDir);

  fs.mkdirSync(s.stateDir, { recursive: true });
  fs.mkdirSync(s.logsDir, { recursive: true });

  supervisorLog = new RotatingLog(path.join(s.logsDir, "supervisor.log"));
  guardConsoleStreams();
  log("info", `supervisor starting pid=${process.pid} port=${s.port} test=${!!s.test}`);

  const baseEnv = allowlistedEnv(process.env);

  // 1. Single instance (CONTRACT §10-11).
  let free;
  try {
    free = await probeBind(s.host, s.port);
  } catch (e) {
    log("error", `cannot probe ${s.host}:${s.port}: ${e.message}`);
    process.exit(1);
  }
  if (!free) {
    const h = await fetchHealth(s.host, s.port, HEALTH_TIMEOUT_MS);
    if (h && h.ok === true) {
      log("info", `port ${s.port} already served by our own instance (pid ${h.pid}, instance ${h.instance_id}); exiting`);
      process.exit(0);
    }
    log("error", `port ${s.port} is held by a foreign process`);
    sendAlert(s, baseEnv, "supervisor_port_foreign", `spillover port ${s.port} is held by a non-spillover process`);
    process.exit(3);
  }

  writePidFile(s);
  setupShutdown(s);
  process.on("uncaughtException", (e) => log("error", `uncaught exception: ${e.stack || e.message}`));

  // cluster.fork() merges process.env into the worker's env and cannot subtract keys, so the primary's
  // own env must already be reduced to the allowlist before the first fork (CONTRACT §10).
  scrubProcessEnv(baseEnv);

  cluster.setupPrimary({ exec: s.proxyScript, args: s.workerArgs, windowsHide: true });
  forkWorker();

  if (s.omniEnabled && fs.existsSync(s.omniCmd)) {
    attemptStartOmni(s, baseEnv);
  } else if (s.omniEnabled) {
    log("info", `omniroute cmd not found, skipping: ${s.omniCmd}`);
  } else {
    log("info", "omniroute disabled by config");
  }
}

if (require.main === module) {
  main().catch((e) => {
    const message = (e && e.stack) || String(e);
    try {
      log("error", `fatal: ${message}`);
    } catch {
      // logging itself failed; fall through to stderr below
    }
    console.error(message);
    process.exit(1);
  });
}

module.exports = { selectStaleOmniOwner, parseArgs, resolveSettings, UsageError };
