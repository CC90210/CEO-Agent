// Late (Zernio) MCP shim — replaces late-mcp-wrapper.cmd.
// Note: Late MCP uses uvx (Python uv) not npx — LATE_API_KEY is read from env.
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env.agents') });

if (!process.env.LATE_API_KEY) {
  console.error('ERROR: LATE_API_KEY not found in .env.agents');
  process.exit(1);
}

const { spawn } = require('child_process');

// AVG's TLS scanner MITMs outbound HTTPS with a root that is in the Windows
// store but NOT in certifi, which broke this server two ways at once
// (diagnosed 2026-08-13 via the identical failure in CMO-Agent's late_tool.py):
//   1. uv's OWN downloader could not fetch the packages —
//      "invalid peer certificate: UnknownIssuer". Hence --native-tls.
//   2. the SDK's httpx calls then died with CERTIFICATE_VERIFY_FAILED. The fix
//      is truststore.inject_into_ssl(), which is an IN-PROCESS patch — no env
//      var can carry it in, so the plain `late-mcp` console script can never
//      pick it up. We call its entrypoint (late.mcp.server:mcp.run, read from
//      the package's console_scripts metadata) after injecting instead.
// SSLKEYLOGFILE: AVG points it at a kernel device handle that CPython opens
// inside ssl.create_default_context(); a stale handle raises before a byte is
// sent. That is the documented cause of the 2026-07-29 fleet outage.
const childEnv = { ...process.env };
delete childEnv.SSLKEYLOGFILE;

const child = spawn(
  process.platform === 'win32' ? 'uvx.exe' : 'uvx',
  ['--native-tls', '--from', 'late-sdk[mcp]', '--with', 'truststore',
   'python', '-c',
   'import truststore; truststore.inject_into_ssl(); ' +
   'from late.mcp.server import mcp; mcp.run()'],
  { stdio: 'inherit', windowsHide: true, shell: false, env: childEnv }
);
child.on('exit', (code) => process.exit(code ?? 0));
child.on('error', (err) => { console.error(err); process.exit(1); });
