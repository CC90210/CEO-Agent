// Firecrawl MCP shim — replaces firecrawl-mcp-wrapper.cmd.
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env.agents') });

if (!process.env.FIRECRAWL_API_KEY) {
  console.error('ERROR: FIRECRAWL_API_KEY not found in .env.agents');
  process.exit(1);
}

const { spawn } = require('child_process');
const child = spawn(
  process.platform === 'win32' ? 'npx.cmd' : 'npx',
  ['-y', 'firecrawl-mcp'],
  { stdio: 'inherit', windowsHide: true, shell: false, env: process.env }
);
child.on('exit', (code) => process.exit(code ?? 0));
child.on('error', (err) => { console.error(err); process.exit(1); });
