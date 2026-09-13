"use strict";
/*
 * Claude Spillover proxy state machine.
 * DIRECT forwards every request to Anthropic. An eligible account-wide limit atomically records a
 * sanitized capture and enters SPILLING. In SPILLING, eligible Messages requests use OmniRoute,
 * except periodic Anthropic probes; reset time or a successful probe returns to DIRECT. Observe and
 * passthrough record/forward limits but never transition. No Claude credential crosses the fallback leg.
 */
const childProcess = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const http = require("node:http");
const https = require("node:https");
const path = require("node:path");
const zlib = require("node:zlib");
const { once } = require("node:events");
const { URL } = require("node:url");
const detector = require("./limit_detector.js");

const argv = process.argv.slice(2);
const isTest = argv.includes("--test");
function arg(name) { const i=argv.indexOf(name); return i < 0 ? undefined : argv[i+1]; }
function die(message) { console.error(message); process.exit(2); }
function loopbackUrl(value) { try { return ["127.0.0.1","localhost"].includes(new URL(value).hostname); } catch { return false; } }
const overrideNames=["--state-dir","--anthropic-base","--omniroute-base","--lane-key","--port","--now-offset"];
if (!isTest && overrideNames.some(x=>argv.includes(x))) die("test overrides require --test");
if (isTest && (!arg("--state-dir") || !loopbackUrl(arg("--anthropic-base")) || !loopbackUrl(arg("--omniroute-base")))) die("test URLs and state directory are required and must be loopback");

const homeDir = isTest ? path.dirname(path.resolve(arg("--state-dir"))) : path.dirname(__dirname);
const stateDir = isTest ? path.resolve(arg("--state-dir")) : path.join(homeDir,"state");
const configPath = isTest && fs.existsSync(path.join(homeDir,"config.json")) ? path.join(homeDir,"config.json") : (isTest ? path.resolve(__dirname,"../../config/spillover.json") : path.join(homeDir,"config.json"));
fs.mkdirSync(stateDir,{recursive:true}); fs.mkdirSync(path.join(stateDir,"captured"),{recursive:true});
let fullConfig=JSON.parse(fs.readFileSync(configPath,"utf8"));
let cfg={...fullConfig.proxy};
if (isTest) { cfg.anthropic_base=arg("--anthropic-base"); cfg.omniroute_base=arg("--omniroute-base"); cfg.port=Number(arg("--port")); }
const host=cfg.host || "127.0.0.1";
if (host !== "127.0.0.1") die("proxy host must be 127.0.0.1");
const nowOffsetMs=isTest ? Number(arg("--now-offset") || 0)*1000 : 0;
const nowMs=()=>Date.now()+nowOffsetMs;
const nowIso=()=>new Date(nowMs()).toISOString();
// Test runs normally pass --lane-key; one that omits it exercises the production loader below.
const laneKeyFromLoader=!(isTest && arg("--lane-key")!==undefined);
let laneKey=laneKeyFromLoader ? loadLaneKey() : String(arg("--lane-key"));
let laneKeyRetryAt=0;
let configMtime=0;
const instanceId=crypto.randomUUID();
let transitionPromise=null;
let storedLimitRaw=null;
let healthCache={healthy:true,at:0};
let state=loadState();

// A missing or unreadable lane key must never stop the proxy: the direct leg needs no key, and the
// fallback leg reports itself down until one loads (checkHealth). Only the failure's code is logged,
// never the helper's output.
function loadLaneKey() {
  try {
    // -S: lane_key.py is stdlib only, and skipping the venv's site import cuts this synchronous call from ~1.4 s to ~0.1 s.
    return childProcess.execFileSync(fullConfig.python_exe,["-S",path.join(homeDir,"bin","lane_key.py"),"get","omniroute_lane"],{encoding:"utf8",windowsHide:true,timeout:5000,stdio:["ignore","pipe","pipe"]}).trim();
  } catch (e) {
    console.error(`spillover: lane key unavailable (${e.code||`exit ${e.status}`}); fallback leg stays down until it loads`);
    return "";
  }
}
function blankState() { return {schema_version:1,mode:"direct",config_mode:cfg.mode,limit:null,fallback:{healthy:true,checked_at:null,consecutive_failures:0,last_error:null,outage_since:null},last_probe_at:null,counters:{direct:0,fallback:0,limit_passthrough:0,overloaded_529:0,automation:0,errors:0},last_route:null,instance_id:instanceId,pid:process.pid,started_at:nowIso(),version:readVersion()}; }
function readVersion(){ try{return fs.readFileSync(path.join(__dirname,"VERSION"),"utf8").trim() || "dev";}catch{return "dev";} }
function loadState(){ try { const old=JSON.parse(fs.readFileSync(path.join(stateDir,"state.json"),"utf8")); return {...blankState(),...old,instance_id:instanceId,pid:process.pid,started_at:nowIso(),config_mode:cfg.mode}; } catch{return blankState();} }
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
async function atomicJson(file,obj){ const tmp=`${file}.${process.pid}.${crypto.randomBytes(4).toString("hex")}.tmp`; await fs.promises.writeFile(tmp,JSON.stringify(obj,null,2)); for(let i=0;i<10;i++){try{await fs.promises.rename(tmp,file);return;}catch(e){if(!["EPERM","EBUSY"].includes(e.code)||i===9)throw e;await sleep(10*(i+1));}} }
let persistOk=true;
let persistConsecutiveFailures=0;
let lastPersistAlertAt=0;
const PERSIST_ALERT_INTERVAL_MS=60*60*1000;
function notePersistFailure(e){
  persistOk=false;
  persistConsecutiveFailures++;
  console.error(`spillover: state.json write failed (${persistConsecutiveFailures} in a row): ${e&&e.message||e}`);
  if(persistConsecutiveFailures>=3&&nowMs()-lastPersistAlertAt>=PERSIST_ALERT_INTERVAL_MS){
    lastPersistAlertAt=nowMs();
    alert("state_write_failed",`state.json has failed to persist ${persistConsecutiveFailures} times in a row`);
  }
}
function notePersistSuccess(){persistOk=true;persistConsecutiveFailures=0;}
async function saveState(){
  state.config_mode=cfg.mode;
  try{
    // proxy.test_force_persist_failure is a narrow, --test-only hook that stands in for an
    // unwritable state dir so the failure path can be exercised deterministically.
    if(isTest&&cfg.test_force_persist_failure)throw new Error("test forced persist failure");
    await atomicJson(path.join(stateDir,"state.json"),state);
    notePersistSuccess();
  }catch(e){
    notePersistFailure(e);
  }
}
// Logs a line to state/logs/alerts.log instead of throwing, so a broken alert path never takes
// down the worker that is busy handling the fallback it is trying to report on.
function logAlertFailure(reason){try{const dir=path.join(stateDir,"logs");fs.mkdirSync(dir,{recursive:true});fs.appendFileSync(path.join(dir,"alerts.log"),`${nowIso()} ${reason}\n`);}catch{}}
// --test suppresses real alert delivery by default; proxy.test_alerts_enabled is a narrow,
// test-only escape hatch (honoured only when isTest) used to exercise the spawn/error path itself.
function alertsSuppressedForTest(){return isTest&&!cfg.test_alerts_enabled;}
function alert(kind,message){
  if(alertsSuppressedForTest()||!cfg.alerts||(!cfg.alerts.telegram&&!cfg.alerts.toast))return;
  let c;
  try{
    c=childProcess.spawn(fullConfig.python_exe,[path.join(homeDir,"bin","spillover_alert.py"),kind,message],{detached:true,windowsHide:true,stdio:"ignore"});
  }catch(e){
    logAlertFailure(`spawn threw for ${kind}: ${e.message}`);
    return;
  }
  // A missing python_exe or script path surfaces as an async 'error' event, not a throw. Without
  // this listener Node treats it as unhandled and crashes the worker right as it enters fallback.
  c.on("error",(e)=>logAlertFailure(`spawn error for ${kind}: ${e.message}`));
  c.unref();
}
function safeMessage(s){return String(s||"").replace(/req_[A-Za-z0-9_-]+|org[A-Za-z0-9_-]+|[0-9a-f]{8}-[0-9a-f-]{27,}/gi,"<ID>");}
function capture429(status,headers,body){const kept={};for(const [k,v] of Object.entries(headers)){const n=k.toLowerCase();if(n.startsWith("anthropic-ratelimit-")||["retry-after","date","content-type"].includes(n))kept[n]=v;}let err={};try{const b=JSON.parse(body.toString("utf8"));err={type:b.error&&b.error.type||null,message:safeMessage(b.error&&b.error.message)};}catch{} const name=`429-${Date.now()}.json`;fs.writeFileSync(path.join(stateDir,"captured",name),JSON.stringify({status,header_names:Object.keys(headers),headers:kept,error:err},null,2));return name;}
function rotateEvents(){const f=path.join(stateDir,"events.jsonl");try{if(fs.statSync(f).size>=5*1024*1024)fs.renameSync(f,f+".1");}catch{}}
function event(row){rotateEvents();fs.appendFileSync(path.join(stateDir,"events.jsonl"),JSON.stringify({ts:nowIso(),...row})+"\n");}
function lowerHeaders(h){const o={};for(const [k,v] of Object.entries(h||{}))o[k.toLowerCase()]=v;return o;}
const HOP=new Set(["connection","keep-alive","proxy-authenticate","proxy-authorization","te","trailer","transfer-encoding","upgrade"]);
function directHeaders(headers,url){const out={};for(const [k,v] of Object.entries(headers)){const n=k.toLowerCase();if(HOP.has(n)||n.startsWith("proxy-")||n.startsWith("x-bravo-"))continue;out[n]=v;}out.host=url.host;return out;}
// Defense-in-depth: an ALLOWLIST, not a denylist. Only these four client headers ever cross into
// the fallback leg; everything else (including any header an attacker invents) is dropped by
// construction, before the poisoned() check even runs as the last line of defense.
const FALLBACK_HEADER_ALLOWLIST=new Set(["content-type","accept","anthropic-version","anthropic-beta"]);
function fallbackHeaders(headers,url,body,routeModel){
  const out={};
  for(const [k,v] of Object.entries(headers)){
    const n=k.toLowerCase();
    if(FALLBACK_HEADER_ALLOWLIST.has(n))out[n]=v;
  }
  out.host=url.host;
  out.authorization=`Bearer ${laneKey}`;
  out["x-route-model"]=routeModel;
  out["x-omniroute-compression"]="off";
  out["accept-encoding"]="identity";
  out["content-length"]=String(body.length);
  return out;
}
function requestUpstream(base,req,headers,body){const u=new URL(req.url,base);const transport=u.protocol==="https:"?https:http;let handle;const promise=new Promise((resolve,reject)=>{handle=transport.request({protocol:u.protocol,hostname:u.hostname,port:u.port||undefined,path:u.pathname+u.search,method:req.method,headers},resolve);handle.on("error",reject);if(body.length)handle.write(body);handle.end();});return {promise,abort:()=>handle&&handle.destroy()};}
function collectRequest(req,max){return new Promise((resolve,reject)=>{const a=[];let n=0;req.on("data",c=>{n+=c.length;if(n>max){reject(Object.assign(new Error("request body too large"),{code:"BODY_TOO_LARGE"}));req.destroy();}else a.push(c)});req.on("end",()=>resolve(Buffer.concat(a)));req.on("error",reject);});}
function collectResponse(up,max,timeoutMs){return new Promise((resolve,reject)=>{const a=[];let n=0;const t=setTimeout(()=>{up.destroy();reject(new Error("response buffer timeout"));},timeoutMs);up.on("data",c=>{n+=c.length;if(n>max){clearTimeout(t);up.destroy();reject(new Error("response buffer limit"));}else a.push(c)});up.on("end",()=>{clearTimeout(t);resolve(Buffer.concat(a))});up.on("error",e=>{clearTimeout(t);reject(e)});});}
function decompressedCopy(buf,encoding){try{if(encoding==="gzip")return zlib.gunzipSync(buf);if(encoding==="br")return zlib.brotliDecompressSync(buf);if(encoding==="deflate")return zlib.inflateSync(buf);}catch{}return buf;}
async function writeChunk(res,chunk){if(!res.write(chunk))await once(res,"drain");}
// Every fire-and-forget stream write (pings, error frames sent from a timer) goes through this
// helper so a dead client socket ends the response instead of becoming an unhandled rejection.
function safeWrite(res,chunk){return writeChunk(res,chunk).catch(()=>{if(!res.writableEnded)try{res.end();}catch{}});}
function endStreamWithError(res,error){return safeWrite(res,formatSse("error",{type:"error",error})).finally(()=>{if(!res.writableEnded)res.end();});}
function maxSseFrameBytes(){return Number.isFinite(cfg.max_sse_frame_bytes)?cfg.max_sse_frame_bytes:1048576;}
function sendJson(res,status,obj,headers={}){const b=Buffer.from(JSON.stringify(obj));res.writeHead(status,{"content-type":"application/json","content-length":b.length,...headers});res.end(b);return b.length;}
function anthropicError(res,status,type,message){return sendJson(res,status,{type:"error",error:{type,message}});}
function validHost(req,port){const h=String(req.headers.host||"").toLowerCase();return h===`127.0.0.1:${port}`||h===`localhost:${port}`;}
function isLoopback(req){const a=(req.socket.remoteAddress||"").replace(/^::ffff:/,"");return a==="127.0.0.1"||a==="::1";}
function laneOf(req){if(String(req.headers["x-bravo-lane"]||"").toLowerCase()==="automation")return "automation";return detector.isOAuthBearer(req.headers.authorization)?"interactive":"other";}
function eligible(req){const pathname=new URL(req.url,"http://x").pathname;const ep=detector.parseEntrypoint(req.headers["user-agent"]);return req.method==="POST"&&(pathname==="/v1/messages"||pathname==="/v1/messages/count_tokens")&&!req.headers["x-api-key"]&&detector.isOAuthBearer(req.headers.authorization)&&cfg.spill_entrypoints.includes(ep)&&String(req.headers["x-bravo-lane"]||"").toLowerCase()!=="automation"&&String(req.headers["x-bravo-spill"]||"").toLowerCase()!=="deny";}
function attribution(block){if(!block||block.type!=="text"||typeof block.text!=="string")return false;const s=block.text.trimStart().toLowerCase();return s.startsWith("x-anthropic-billing-header")||s.includes("claude code")&&(/attribution|powered by|generated by/.test(s));}
function normalizeBlock(b){if(b&&b.type==="tool_reference")return {type:"text",text:`[Tool reference: ${b.tool_name||b.name||"tool"}]`};return b;}
function normalizeBody(body){const b=JSON.parse(JSON.stringify(body));delete b.context_management;delete b.metadata;if(Array.isArray(b.tools))b.tools=b.tools.filter(t=>(t.type===undefined||t.type==="custom")&&!t.defer_loading&&!/tool.?search/i.test(String(t.name||t.type||"")));if(Array.isArray(b.system)){if(attribution(b.system[0]))b.system.shift();b.system=b.system.map(normalizeBlock);}else if(attribution(b.system))delete b.system;if(Array.isArray(b.messages))for(const m of b.messages)if(Array.isArray(m.content))m.content=m.content.map(normalizeBlock);return b;}
function poisoned(headers,body){return Object.values(headers).some(v=>String(v).includes("sk-ant-"))||body.includes("sk-ant-");}
function retryAfter(){if(!state.limit)return "60";return String(Math.max(1,Math.ceil((Date.parse(state.limit.reset_at)-nowMs())/1000)));}
function sendStoredLimit(res){if(!storedLimitRaw)return anthropicError(res,429,"rate_limit_error","Claude subscription usage limit reached");const h={...storedLimitRaw.headers,"retry-after":retryAfter()};delete h["content-length"];res.writeHead(429,h);res.end(storedLimitRaw.body);return storedLimitRaw.body.length;}
function persistentFallback(){const f=state.fallback;return f.consecutive_failures>=cfg.fallback_health_fail_threshold||(f.outage_since&&nowMs()-Date.parse(f.outage_since)>=cfg.fallback_persistent_outage_sec*1000);}
async function markHealth(ok,error){const f=state.fallback;f.healthy=ok;f.checked_at=nowIso();if(ok){f.consecutive_failures=0;f.last_error=null;f.outage_since=null;}else{f.consecutive_failures++;f.last_error=String(error||"fallback unavailable");if(!f.outage_since)f.outage_since=nowIso();}healthCache={healthy:ok,at:nowMs()};await saveState();}
async function checkHealth(force=false){const ttl=healthCache.healthy?cfg.fallback_health_ttl_ok_ms:cfg.fallback_health_ttl_fail_ms;if(!force&&nowMs()-healthCache.at<ttl)return healthCache.healthy;
  // No lane key yet (setup not run, or the store unreadable): the fallback is down, and it must never
  // be called with an empty bearer. The reload is synchronous, so it is retried at most once a minute.
  if(!laneKey&&laneKeyFromLoader&&nowMs()>=laneKeyRetryAt){laneKeyRetryAt=nowMs()+60000;laneKey=loadLaneKey();}
  if(!laneKey){await markHealth(false,"lane key not set");return false;}
  const fake=readFault();if(fake&&fake.mode==="omniroute_down"){await markHealth(false,"fault omniroute_down");return false;}for(let attempt=0;attempt<2;attempt++){try{const u=new URL("/v1/models",cfg.omniroute_base);const h={authorization:`Bearer ${laneKey}`};const result=await new Promise((resolve,reject)=>{const q=http.request(u,{method:"GET",headers:h},resolve);q.setTimeout(Math.min(3000,cfg.fallback_first_content_timeout_ms),()=>q.destroy(new Error("health timeout")));q.on("error",reject);q.end();});result.resume();if(result.statusCode>=200&&result.statusCode<500&&result.statusCode!==401){await markHealth(true);return true;}if(result.statusCode===401&&attempt===0&&!isTest){laneKey=loadLaneKey();continue;}throw new Error(`health status ${result.statusCode}`);}catch(e){if(attempt===1||isTest){await markHealth(false,e.message);return false;}}}return false;}
function readFault(){try{const f=JSON.parse(fs.readFileSync(path.join(stateDir,"fault.json"),"utf8"));const expires=Date.parse(f.expires_at);if(!cfg.allow_fault_injection||!Number.isFinite(expires)||expires<=nowMs()||expires>nowMs()+3600000)return null;return f;}catch{return null;}}
async function enterSpilling(classification,status,headers,body){if(transitionPromise)return transitionPromise;transitionPromise=(async()=>{if(state.mode==="spilling")return;const captured=capture429(status,headers,body);storedLimitRaw={status,headers:{...headers},body:Buffer.from(body)};state.mode="spilling";state.last_probe_at=nowIso();state.limit={detected_at:nowIso(),reset_at:new Date(classification.reset_at*1000).toISOString(),reset_source:classification.reset_source,claim:classification.claim,captured};await saveState();event({req_id:null,method:null,path:null,lane:null,entrypoint:null,cc_version:null,route:"local",status:429,upstream_status:429,ms:0,bytes_in:0,bytes_out:0,reason:"entered_fallback",route_model:null,unified:detector.unifiedTelemetry(headers)});alert("entered_fallback",`Claude limit reached until ${state.limit.reset_at}`);})();try{await transitionPromise;}finally{transitionPromise=null;}}
async function returnDirect(reason){if(state.mode!=="spilling")return;state.mode="direct";state.limit=null;storedLimitRaw=null;await saveState();alert("back_to_claude",`Back on Claude: ${reason}`);}
function maybeReset(){const f=readFault();if(f&&f.mode==="force_reset"){return returnDirect("forced reset");}if(state.mode==="spilling"&&state.limit&&nowMs()>=Date.parse(state.limit.reset_at))return returnDirect("limit reset time reached");return Promise.resolve();}
function shouldProbe(){return state.mode==="spilling"&&(!state.last_probe_at||nowMs()-Date.parse(state.last_probe_at)>=cfg.probe_interval_sec*1000);}
async function direct(req,res,body,meta,asProbe=false){const url=new URL(cfg.anthropic_base);const h=directHeaders(req.headers,url);const call=requestUpstream(cfg.anthropic_base,req,h,body);let up;try{up=await call.promise;}catch(e){return finishError(res,meta,e);}let closed=false;res.once("close",()=>{if(!res.writableEnded){closed=true;call.abort();}});
  if(up.statusCode!==429){if(asProbe&&![529].includes(up.statusCode)&&up.statusCode<500)await returnDirect(`probe status ${up.statusCode}`);res.writeHead(up.statusCode,up.headers);res.flushHeaders();res.socket&&res.socket.setNoDelay(true);let n=0;try{for await(const c of up){n+=c.length;await writeChunk(res,c);}if(!closed)res.end();record(meta,"direct",up.statusCode,up.statusCode,n,asProbe?"probe":null);}catch(e){if(!closed)finishError(res,meta,e);}return;}
  let raw;try{raw=await collectResponse(up,65536,5000);}catch(e){return finishError(res,meta,e);}const copy=decompressedCopy(raw,String(up.headers["content-encoding"]||"").toLowerCase());const c=detector.classify({status:429,headers:lowerHeaders(up.headers),bodyText:copy.toString("utf8"),nowMs:nowMs()},{reset_clamp_min_sec:cfg.reset_clamp_min_sec,reset_clamp_max_sec:cfg.reset_clamp_max_sec});
  // A probe answered with a 429 of ANY kind (subscription, model-scoped, or merely transient)
  // never flips back to direct: Anthropic is still saying no. Only a non-429, non-5xx, non-529
  // probe answer (handled above) means the account is actually clear again.
  if(c.kind==="subscription_limit"&&cfg.mode!=="passthrough"){if(cfg.mode==="spill"&&eligible(req)){await enterSpilling(c,429,up.headers,raw);return fallback(req,res,body,meta);}state.counters.limit_passthrough++;await saveState();}
  else if(asProbe&&cfg.mode==="spill"&&eligible(req)){return fallback(req,res,body,meta);}
  res.writeHead(429,up.headers);res.end(raw);record(meta,"direct",429,429,raw.length,c.kind);
}
function record(meta,route,status,upstreamStatus,bytesOut,reason,routeModel=null){state.counters[route==="direct"?"direct":route==="fallback"?"fallback":route==="overloaded-529"?"overloaded_529":"limit_passthrough"]++;state.last_route={at:nowIso(),route,status,lane:meta.lane};saveState();event({...meta,route,status,upstream_status:upstreamStatus,ms:Date.now()-meta.started,bytes_out:bytesOut,reason,route_model:routeModel,unified:null});}
function finishError(res,meta,e){state.counters.errors++;if(!res.headersSent)anthropicError(res,502,"api_error",`spillover upstream error: ${e.message}`);else res.destroy();record(meta,"local",502,null,0,"internal_error");}
function contextOverflow(obj){const e=obj&&obj.error||{};const text=String(e.message||"");if(e.code!=="context_length_exceeded"&&!/maximum context|context length|too many tokens|prompt is too long/i.test(text))return null;const nums=[...text.matchAll(/(\d[\d,]*)\s*tokens?/gi)].map(x=>Number(x[1].replace(/,/g,"")));const window=(text.match(/(?:maximum context length is|context length of)\s*(\d[\d,]*)/i)||[])[1];return {used:nums.length?Math.max(...nums):detector.estimateTokens(obj),window:window?Number(window.replace(/,/g,"")):cfg.fallback_window_tokens};}
function transformJson(buf,model){let obj;try{obj=JSON.parse(buf.toString("utf8"));}catch{return {body:buf,status:null};}const overflow=contextOverflow(obj);if(overflow)return {body:Buffer.from(JSON.stringify({type:"error",error:{type:"invalid_request_error",message:`prompt is too long: ${overflow.used} tokens > ${overflow.window} maximum`}})),status:400};if(obj.model)obj.model=model;if(obj.message&&obj.message.model)obj.message.model=model;if(Array.isArray(obj.content))obj.content=obj.content.filter(x=>!["thinking","redacted_thinking"].includes(x.type));return {body:Buffer.from(JSON.stringify(obj)),status:null};}
function parseSseFrame(raw){const lines=raw.split(/\r?\n/);let eventName="",data="";for(const line of lines){if(line.startsWith("event:"))eventName=line.slice(6).trim();if(line.startsWith("data:"))data+=(data?"\n":"")+line.slice(5).trimStart();}let obj=null;try{obj=JSON.parse(data);}catch{}return {eventName,data,obj};}
function formatSse(eventName,obj){return `event: ${eventName}\ndata: ${JSON.stringify(obj)}\n\n`;}
function transformFrame(raw,model,map,dropped){const p=parseSseFrame(raw);if(!p.obj)return raw+"\n\n";if(p.obj.type==="message_start"&&p.obj.message)p.obj.message.model=model;const idx=p.obj.index;if(p.obj.type==="content_block_start"){const type=p.obj.content_block&&p.obj.content_block.type;if(type==="thinking"||type==="redacted_thinking"){dropped.add(idx);return "";}map.set(idx,map.size);}if(idx!==undefined){if(dropped.has(idx))return "";if(map.has(idx))p.obj.index=map.get(idx);}if((p.eventName==="error"||p.obj.type==="error")&&p.obj.error&&p.obj.error.type==="stream_error")return formatSse("error",{type:"error",error:{type:"api_error",message:p.obj.error.message||"fallback stream failed"}});return formatSse(p.eventName||p.obj.type,p.obj);}
async function fallbackAttempt(req,body){const parsed=JSON.parse(body.toString("utf8"));const normalized=normalizeBody(parsed);if(detector.estimateTokens(normalized)>cfg.fallback_window_tokens)return {kind:"too_large"};const serialized=Buffer.from(JSON.stringify(normalized));const routeModel=/haiku/i.test(String(parsed.model||""))?cfg.route_model_fast:cfg.route_model_main;const u=new URL(cfg.omniroute_base);const headers=fallbackHeaders(req.headers,u,serialized,routeModel);if(poisoned(headers,serialized.toString("utf8")))return {kind:"poisoned"};const call=requestUpstream(cfg.omniroute_base,req,headers,serialized);let up;try{up=await call.promise;}catch(e){return {kind:"failure",error:e.message};}if(up.statusCode===401){up.resume();if(!isTest)try{laneKey=loadLaneKey();}catch{}return {kind:"failure",error:"fallback 401"};}const ct=String(up.headers["content-type"]||"");if(!ct.includes("text/event-stream")){let raw;try{raw=await collectResponse(up,16*1024*1024,cfg.fallback_first_content_timeout_ms);}catch(e){return {kind:"failure",error:e.message};}if(up.statusCode>=500||up.statusCode===429||up.statusCode===529)return {kind:"failure",error:`fallback status ${up.statusCode}`};const tr=transformJson(raw,parsed.model);return {kind:"json",up,status:tr.status||up.statusCode,body:tr.body,routeModel,headers:up.headers};}
  return await prepareSse(up,call,parsed.model,routeModel);
}
function prepareSse(up,call,model,routeModel){return new Promise(resolve=>{let raw="",committed=false,done=false;const held=[];const timeout=setTimeout(()=>finish({kind:"failure",error:"fallback first content timeout"}),cfg.fallback_first_content_timeout_ms);
  function detach(){up.off("data",onData);up.off("end",onEnd);up.off("error",onError);}
  function finish(v){if(done)return;done=true;clearTimeout(timeout);detach();if(v.kind==="failure")call.abort();else up.pause();resolve(v);}
  function onData(chunk){raw+=chunk;let pos;while((pos=raw.search(/\r?\n\r?\n/))>=0){const frame=raw.slice(0,pos);const sep=raw.slice(pos).match(/^\r?\n\r?\n/)[0];raw=raw.slice(pos+sep.length);const p=parseSseFrame(frame);
    if((p.eventName==="error")||(p.obj&&p.obj.type==="error")){
      // Same wording contract as the non-stream path: an error that names a context overflow gets
      // the exact "prompt is too long" 400, not a generic "before content" failure.
      const overflow=p.obj&&contextOverflow(p.obj);
      if(overflow){
        const body=Buffer.from(JSON.stringify({type:"error",error:{type:"invalid_request_error",message:`prompt is too long: ${overflow.used} tokens > ${overflow.window} maximum`}}));
        finish({kind:"json",up,status:400,body,headers:{"content-type":"application/json"},routeModel});
        return;
      }
      finish({kind:"failure",error:"fallback error before content"});return;
    }
    held.push(frame+"\n\n");if(p.obj&&p.obj.type==="content_block_start"){committed=true;finish({kind:"sse",up,initial:held.join(""),remainder:raw,model,routeModel});return;}}}
  function onEnd(){if(!committed)finish({kind:"failure",error:"fallback EOF before content"});}
  function onError(e){finish({kind:"failure",error:e.message});}
  up.setEncoding("utf8");up.on("data",onData);up.on("end",onEnd);up.on("error",onError);
});}
async function streamCommitted(res,result,meta){
  const {up,model,routeModel}=result;
  res.writeHead(up.statusCode,{...up.headers,"content-type":"text/event-stream"});
  res.flushHeaders();res.socket&&res.socket.setNoDelay(true);
  const map=new Map(),dropped=new Set();
  let buffer=result.initial+result.remainder,last=Date.now(),ended=false;
  const flush=async()=>{
    let pos;
    while((pos=buffer.search(/\r?\n\r?\n/))>=0){
      const frame=buffer.slice(0,pos);
      const sep=buffer.slice(pos).match(/^\r?\n\r?\n/)[0];
      buffer=buffer.slice(pos+sep.length);
      const out=transformFrame(frame,model,map,dropped);
      if(out)await writeChunk(res,out);
    }
  };
  await flush();
  // A frame with no blank-line terminator (a misbehaving or malicious fallback) would otherwise
  // grow `buffer` without bound. Abort the stream once the unflushed remainder crosses the cap.
  function abortOversizedFrame(){
    ended=true;
    up.destroy();
    endStreamWithError(res,{type:"api_error",message:"fallback stream frame too large"});
    markHealth(false,"fallback stream frame too large");
  }
  const timer=setInterval(()=>{
    const quiet=Date.now()-last;
    if(quiet>=cfg.stream_silence_abort_ms){
      ended=true;
      up.destroy();
      endStreamWithError(res,{type:"overloaded_error",message:"fallback stream became silent"});
      markHealth(false,"stream silence");
    }else if(quiet>=cfg.ping_interval_ms){
      safeWrite(res,"event: ping\ndata: {\"type\":\"ping\"}\n\n");
    }
  },Math.max(10,Math.min(cfg.ping_interval_ms,1000)));
  try{
    for await(const c of up){
      if(ended)break;
      last=Date.now();
      buffer+=c.toString();
      if(buffer.length>maxSseFrameBytes()){abortOversizedFrame();break;}
      await flush();
    }
    if(!ended){await flush();res.end();await markHealth(true);record(meta,"fallback",up.statusCode,up.statusCode,0,null,routeModel);}
  }catch(e){
    if(!ended)res.destroy();
    await markHealth(false,e.message);
  }finally{
    clearInterval(timer);
  }
}
async function fallback(req,res,body,meta){if(body.length>cfg.max_replay_body_bytes){sendStoredLimit(res);record(meta,"limit-429",429,429,storedLimitRaw?storedLimitRaw.body.length:0,"body_too_large");return;}if(!(await checkHealth()))return fallbackFailure(res,meta,"fallback health down");const start=Date.now();let delay=50;while(Date.now()-start<=cfg.fallback_retry_budget_ms){const result=await fallbackAttempt(req,body);if(result.kind==="too_large"){alert("session_too_large","Session exceeds fallback context window");sendStoredLimit(res);record(meta,"limit-429",429,429,0,"session_too_large");return;}if(result.kind==="poisoned"){event({...meta,route:"local",status:429,upstream_status:null,ms:Date.now()-meta.started,bytes_out:0,reason:"security_poison_block",route_model:null,unified:null});sendStoredLimit(res);return;}if(result.kind==="json"){const h={...result.headers,"content-length":result.body.length};res.writeHead(result.status,h);res.end(result.body);await markHealth(true);record(meta,"fallback",result.status,result.up.statusCode,result.body.length,null,result.routeModel);return;}if(result.kind==="sse"){await streamCommitted(res,result,meta);return;}await markHealth(false,result.error);if(Date.now()-start+delay>cfg.fallback_retry_budget_ms)break;await sleep(delay);delay=Math.min(delay*2,1000);}return fallbackFailure(res,meta,"fallback failed before content");}
function fallbackFailure(res,meta,message){if(persistentFallback()){sendStoredLimit(res);alert("fallback_down",message);record(meta,"limit-429",429,null,0,"fallback_down");}else{const n=anthropicError(res,529,"overloaded_error",message);record(meta,"overloaded-529",529,null,n,"fallback_transient");}}
async function handle(req,res){const started=Date.now();const port=server.address()&&server.address().port||cfg.port;const ep=detector.parseEntrypoint(req.headers["user-agent"]);const meta={req_id:crypto.randomUUID(),method:req.method,path:req.url,lane:laneOf(req),entrypoint:ep,cc_version:detector.claudeCodeVersion(req.headers["user-agent"]),started,bytes_in:0};if(!isLoopback(req)||!validHost(req,port)){anthropicError(res,403,"permission_error","loopback host required");return;}if(req.method==="OPTIONS"){res.writeHead(405,{allow:"GET, HEAD, POST"});res.end();return;}if(req.method==="GET"&&req.url==="/__spillover/health"){sendJson(res,200,{ok:true,instance_id:instanceId,pid:process.pid,version:state.version,config_mode:cfg.mode,mode:state.mode,reset_at:state.limit&&state.limit.reset_at||null,fallback_healthy:state.fallback.healthy,persist_ok:persistOk});return;}const pathname=new URL(req.url,"http://x").pathname;if(req.method==="POST"&&pathname.startsWith("/v1/messages")&&!req.headers["anthropic-version"]){anthropicError(res,400,"invalid_request_error","anthropic-version header is required");return;}await maybeReset();const max=256*1024*1024;let body;try{body=await collectRequest(req,max);}catch(e){if(e.code==="BODY_TOO_LARGE"&&state.mode==="spilling")sendStoredLimit(res);else anthropicError(res,413,"invalid_request_error","request body too large");return;}meta.bytes_in=body.length;
  const fault=readFault();if(fault&&fault.mode==="force_limit"&&eligible(req)&&state.mode==="direct"){const raw=Buffer.from(JSON.stringify({type:"error",error:{type:"rate_limit_error",message:"synthetic forced limit"}}));const headers={"content-type":"application/json","anthropic-ratelimit-unified-status":"rejected","anthropic-ratelimit-unified-representative-claim":"five_hour","anthropic-ratelimit-unified-reset":String(Math.floor(Date.parse(fault.expires_at)/1000))};const c=detector.classify({status:429,headers,bodyText:raw.toString(),nowMs:nowMs()},{reset_clamp_min_sec:cfg.reset_clamp_min_sec,reset_clamp_max_sec:cfg.reset_clamp_max_sec});storedLimitRaw={status:429,headers,body:raw};await enterSpilling(c,429,headers,raw);return fallback(req,res,body,meta);}
  if(cfg.mode==="passthrough"){if(state.mode!=="direct"){state.mode="direct";state.limit=null;storedLimitRaw=null;await saveState();}return direct(req,res,body,meta);}
  if(state.mode==="spilling"&&eligible(req)){if(pathname.endsWith("/count_tokens")){anthropicError(res,404,"not_found_error","count_tokens is unavailable during spillover");return;}if(shouldProbe()){state.last_probe_at=nowIso();await saveState();return direct(req,res,body,meta,true);}return fallback(req,res,body,meta);}
  return direct(req,res,body,meta);
}

const server=http.createServer((req,res)=>{Promise.resolve(handle(req,res)).catch(e=>{const meta={req_id:crypto.randomUUID(),method:req.method,path:req.url,lane:laneOf(req),entrypoint:null,cc_version:null,started:Date.now(),bytes_in:0};finishError(res,meta,e);});});
server.on("clientError",(_e,s)=>s.destroy());
// A rejection we did not anticipate should not silently vanish, but it also should not take the
// whole worker down mid-request — log it and keep serving.
process.on("unhandledRejection",(reason)=>{console.error(`spillover: unhandled rejection: ${reason&&reason.stack||reason}`);});
// A truly unexpected exception means we no longer trust process state; exit so the supervisor
// respawns a clean worker rather than limping on.
process.on("uncaughtException",(err)=>{console.error(`spillover: uncaught exception: ${err&&err.stack||err}`);process.exit(1);});
server.listen(cfg.port,host,async()=>{await saveState();console.log(`LISTENING ${server.address().port}`);});
let reloadTimer=setInterval(()=>{try{const st=fs.statSync(configPath);if(configMtime&&st.mtimeMs!==configMtime){fullConfig=JSON.parse(fs.readFileSync(configPath,"utf8"));cfg={...cfg,...fullConfig.proxy};if(cfg.mode==="passthrough"){state.mode="direct";state.limit=null;storedLimitRaw=null;}saveState().catch(()=>{});}configMtime=st.mtimeMs;}catch{}},2000);reloadTimer.unref();
for(const sig of ["SIGTERM","SIGINT"])process.on(sig,()=>{clearInterval(reloadTimer);server.close(()=>process.exit(0));});





