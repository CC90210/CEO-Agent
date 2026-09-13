"use strict";
/* Synthetic scripted upstream for spillover integration tests. */
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const { URL } = require("node:url");
const argv = process.argv.slice(2);
function arg(name) { const i = argv.indexOf(name); return i < 0 ? null : argv[i + 1]; }
const port = Number(arg("--port"));
const scriptPath = arg("--script");
const logPath = arg("--log");
if (!Number.isInteger(port) || !scriptPath || !logPath) { console.error("usage: --port N --script file --log file"); process.exit(2); }
let queue = JSON.parse(fs.readFileSync(scriptPath, "utf8"));
if (!Array.isArray(queue)) queue = queue.scenarios || [];
function sha(value) { return crypto.createHash("sha256").update(value || "").digest("hex"); }
function append(row) { fs.appendFileSync(logPath, JSON.stringify(row) + "\n"); }
function collect(req) { return new Promise((resolve, reject) => { const chunks=[]; req.on("data",c=>chunks.push(c)); req.on("end",()=>resolve(Buffer.concat(chunks))); req.on("error",reject); }); }
function pick(req) {
  const i = queue.findIndex(x => (!x.match || (!x.match.path || x.match.path === req.url) && (!x.match.method || x.match.method.toUpperCase() === req.method)));
  return i < 0 ? null : queue.splice(i, 1)[0];
}
const server = http.createServer(async (req, res) => {
  const body = await collect(req);
  let parsed = null; try { parsed = JSON.parse(body.toString("utf8")); } catch {}
  append({ method:req.method, path:req.url, header_names:Object.keys(req.headers).sort(), authorization_sha256:sha(req.headers.authorization),
    "x-route-model":req.headers["x-route-model"] || null, body_sha256:sha(body), top_level_body_keys:parsed && typeof parsed === "object" ? Object.keys(parsed).sort() : [] });
  const step = pick(req);
  if (!step) { res.writeHead(500,{"content-type":"application/json"}); res.end(JSON.stringify({error:{type:"api_error",message:"no scripted response"}})); return; }
  res.socket.setNoDelay(true);
  res.writeHead(step.status || 200, step.headers || {});
  if (Array.isArray(step.sse_frames)) {
    let elapsed = 0;
    for (const frame of step.sse_frames) {
      elapsed += Number(frame.delay_ms || 0);
      setTimeout(() => { if (!res.destroyed) res.write(String(frame.raw || "")); }, elapsed);
    }
    const finishAt = elapsed + Number(step.hang_ms || 0);
    setTimeout(() => { if (res.destroyed) return; if (step.close_mid_stream) res.destroy(); else res.end(); }, finishAt);
    return;
  }
  if (step.hang_ms) { setTimeout(() => step.close_mid_stream ? res.destroy() : res.end(step.body === undefined ? "" : (typeof step.body === "string" ? step.body : JSON.stringify(step.body))), step.hang_ms); return; }
  const out = Buffer.isBuffer(step.body) ? step.body : Buffer.from(typeof step.body === "string" ? step.body : JSON.stringify(step.body === undefined ? "" : step.body));
  if (step.close_mid_stream) { res.write(out.subarray(0, Math.max(1, Math.floor(out.length / 2)))); res.destroy(); } else res.end(out);
});
server.on("clientError", (_e, socket) => socket.destroy());
server.listen(port, "127.0.0.1", () => console.log(`LISTENING ${server.address().port}`));
for (const sig of ["SIGTERM","SIGINT"]) process.on(sig,()=>server.close(()=>process.exit(0)));
