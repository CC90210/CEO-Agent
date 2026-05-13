"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

function findRepoRoot(startDir) {
  let current = startDir;
  while (current && current !== path.dirname(current)) {
    if (fs.existsSync(path.join(current, "bravo_cli", "local_bridge.py"))) {
      return current;
    }
    current = path.dirname(current);
  }
  return null;
}

function commandVersion(command, args) {
  const candidates = process.platform === "win32"
    ? [command, `${command}.exe`, `${command}.cmd`, `${command}.bat`]
    : [command];
  for (const executable of candidates) {
    const result = spawnSync(executable, args, { encoding: "utf8", windowsHide: true });
    if (result.error || result.status !== 0) continue;
    return (result.stdout || result.stderr).trim().split(/\r?\n/)[0] || "ok";
  }
  return null;
}

const root = findRepoRoot(path.resolve(__dirname, "..", "..", ".."));
const npmVersion = process.env.npm_config_user_agent
  ? process.env.npm_config_user_agent.split(" ")[0].replace("npm/", "")
  : commandVersion("npm", ["-v"]);
const checks = [
  ["node", process.version],
  ["npm", npmVersion],
  ["electron package", fs.existsSync(path.join(__dirname, "..", "node_modules", "electron")) ? "installed" : "missing"],
  ["repo root", root || "not found"],
  ["bridge module", root && fs.existsSync(path.join(root, "bravo_cli", "local_bridge.py")) ? "found" : "missing"],
  ["python", commandVersion(process.platform === "win32" ? "python" : "python3", ["--version"])],
  ["command center url", process.env.OASIS_COMMAND_CENTER_URL || "https://agent-dashboard-cc90210.vercel.app"]
];

let ok = true;
for (const [name, value] of checks) {
  const healthy = Boolean(value) && value !== "missing" && value !== "not found";
  if (!healthy) ok = false;
  console.log(`${healthy ? "OK " : "NO "} ${name}: ${value || "missing"}`);
}

process.exit(ok ? 0 : 1);
