// n8n MCP shim — replaces n8n-mcp-wrapper.cmd.
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env.agents') });

const token = process.env.N8N_BEARER_TOKEN;
if (!token) {
  console.error('ERROR: N8N_BEARER_TOKEN not found in .env.agents');
  process.exit(1);
}
const url = process.env.N8N_MCP_URL || 'https://n8n.srv993801.hstgr.cloud/mcp-server/http';

const { spawn } = require('child_process');
const child = spawn(
  process.platform === 'win32' ? 'npx.cmd' : 'npx',
  ['-y', 'supergateway', '--streamableHttp', url, '--header', `authorization:Bearer ${token}`],
  { stdio: 'inherit', windowsHide: true, shell: false }
);
child.on('exit', (code) => process.exit(code ?? 0));
child.on('error', (err) => { console.error(err); process.exit(1); });
