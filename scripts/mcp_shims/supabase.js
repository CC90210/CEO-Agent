// Supabase MCP shim — replaces supabase-mcp-wrapper.cmd.
// Spawned directly by MCP hosts (Claude Code, Antigravity) via `node`,
// which inherits stdio without allocating a new conhost.exe window.
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env.agents') });

const token = process.env.SUPABASE_ACCESS_TOKEN;
if (!token) {
  console.error('ERROR: SUPABASE_ACCESS_TOKEN not found in .env.agents');
  process.exit(1);
}

const { spawn } = require('child_process');
const child = spawn(
  process.platform === 'win32' ? 'npx.cmd' : 'npx',
  ['-y', '@supabase/mcp-server-supabase@latest', `--access-token=${token}`],
  { stdio: 'inherit', windowsHide: true, shell: false }
);
child.on('exit', (code) => process.exit(code ?? 0));
child.on('error', (err) => { console.error(err); process.exit(1); });
