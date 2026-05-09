// GitHub MCP shim — replaces github-mcp-wrapper.cmd.
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env.agents') });

if (!process.env.GITHUB_PERSONAL_ACCESS_TOKEN) {
  console.error('ERROR: GITHUB_PERSONAL_ACCESS_TOKEN not found in .env.agents');
  process.exit(1);
}

const { spawn } = require('child_process');
const child = spawn(
  process.platform === 'win32' ? 'npx.cmd' : 'npx',
  ['-y', '@modelcontextprotocol/server-github'],
  { stdio: 'inherit', windowsHide: true, shell: false, env: process.env }
);
child.on('exit', (code) => process.exit(code ?? 0));
child.on('error', (err) => { console.error(err); process.exit(1); });
