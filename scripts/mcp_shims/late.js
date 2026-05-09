// Late (Zernio) MCP shim — replaces late-mcp-wrapper.cmd.
// Note: Late MCP uses uvx (Python uv) not npx — LATE_API_KEY is read from env.
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env.agents') });

if (!process.env.LATE_API_KEY) {
  console.error('ERROR: LATE_API_KEY not found in .env.agents');
  process.exit(1);
}

const { spawn } = require('child_process');
const child = spawn(
  process.platform === 'win32' ? 'uvx.exe' : 'uvx',
  ['--from', 'late-sdk[mcp]', 'late-mcp'],
  { stdio: 'inherit', windowsHide: true, shell: false, env: process.env }
);
child.on('exit', (code) => process.exit(code ?? 0));
child.on('error', (err) => { console.error(err); process.exit(1); });
