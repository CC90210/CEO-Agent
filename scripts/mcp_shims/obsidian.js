// Obsidian MCP shim — replaces obsidian-mcp-wrapper.cmd.
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env.agents') });

if (!process.env.OBSIDIAN_API_KEY) {
  console.error('ERROR: OBSIDIAN_API_KEY not found in .env.agents');
  process.exit(1);
}

const env = {
  ...process.env,
  OBSIDIAN_BASE_URL: process.env.OBSIDIAN_BASE_URL || 'http://127.0.0.1:27123',
  OBSIDIAN_VERIFY_SSL: 'false',
  OBSIDIAN_ENABLE_CACHE: 'true',
};

const { spawn } = require('child_process');
const child = spawn(
  process.platform === 'win32' ? 'npx.cmd' : 'npx',
  ['-y', 'obsidian-mcp-server'],
  { stdio: 'inherit', windowsHide: true, shell: false, env }
);
child.on('exit', (code) => process.exit(code ?? 0));
child.on('error', (err) => { console.error(err); process.exit(1); });
