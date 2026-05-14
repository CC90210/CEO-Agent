"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const distDir = path.join(root, "dist");
const requireWindowsSigning = process.env.OASIS_REQUIRE_WINDOWS_SIGNING === "true";

function fail(message) {
  console.error(`NO  ${message}`);
  process.exitCode = 1;
}

function ok(message) {
  console.log(`OK  ${message}`);
}

function info(message) {
  console.log(`INFO ${message}`);
}

function getAuthenticodeSignature(filePath) {
  const command = [
    "$ErrorActionPreference = 'Stop'",
    `$signature = Get-AuthenticodeSignature -LiteralPath '${filePath.replace(/'/g, "''")}'`,
    "$signature | Select-Object Status,StatusMessage,SignerCertificate | ConvertTo-Json -Depth 4 -Compress"
  ].join("; ");

  const result = spawnSync(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
    { encoding: "utf8", windowsHide: true }
  );

  if (result.status !== 0) {
    throw new Error((result.stderr || result.stdout || "Get-AuthenticodeSignature failed").trim());
  }

  return JSON.parse(result.stdout);
}

function checkSignature(filePath, label) {
  if (!fs.existsSync(filePath)) {
    if (requireWindowsSigning) fail(`${label} is missing and signing is required`);
    else info(`${label} is missing; skipping signature check`);
    return;
  }

  let signature;
  try {
    signature = getAuthenticodeSignature(filePath);
  } catch (error) {
    const message = `${label} signature could not be inspected: ${error.message}`;
    if (requireWindowsSigning) fail(message);
    else info(`${message} (allowed for alpha builds)`);
    return;
  }
  const status = signature.Status || "Unknown";
  const signer = signature.SignerCertificate?.Subject || "no signer";

  if (status === "Valid") {
    ok(`${label} signature is valid (${signer})`);
    return;
  }

  const message = `${label} signature is ${status}: ${signature.StatusMessage || "no status message"}`;
  if (requireWindowsSigning) fail(message);
  else info(`${message} (allowed for alpha builds)`);
}

if (process.platform !== "win32") {
  info("Windows signature check skipped on non-Windows platform");
  process.exit(0);
}

checkSignature(path.join(distDir, "OASIS-AI-0.1.0-win-x64.exe"), "Windows installer");
checkSignature(path.join(distDir, "win-unpacked", "OASIS AI.exe"), "Windows app executable");

if (process.exitCode) {
  process.exit(process.exitCode);
}
