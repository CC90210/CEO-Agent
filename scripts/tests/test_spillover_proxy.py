"""Loopback integration tests for the dependency-free Claude Spillover proxy."""
from __future__ import annotations
import contextlib, hashlib, http.client, json, os, shutil, signal, subprocess, time
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
PROXY=ROOT/"scripts/spillover/spillover_proxy.js"
FAKE=ROOT/"scripts/tests/fixtures/spillover/fake_upstream.js"
NODE=shutil.which("node")
pytestmark=pytest.mark.skipif(NODE is None,reason="node missing")
OAUTH="Bearer sk-ant-oat-synthetic-never-real"
LANE="lane-synthetic-only"
UA="claude-cli/2.1.268 (external, cli)"
LIMIT_HEADERS={"content-type":"application/json","anthropic-ratelimit-unified-status":"rejected","anthropic-ratelimit-unified-representative-claim":"five_hour","anthropic-ratelimit-unified-reset":"1999999999","retry-after":"3600"}
LIMIT_BODY={"type":"error","error":{"type":"rate_limit_error","message":"synthetic account limit"}}

def stop(p):
    if p.poll() is not None:return
    p.kill()
    try:p.wait(2)
    except subprocess.TimeoutExpired:pass
def start(cmd):
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    line=p.stdout.readline().strip()
    assert line.startswith("LISTENING "),(line,p.stderr.read())
    return p,int(line.split()[1])

@contextlib.contextmanager
def rig(tmp_path,anthropic,omni,mode="spill",extra=None,now_offset=0,initial_state=None,top_level=None):
    procs=[]
    tmp_path.mkdir(parents=True,exist_ok=True)
    try:
        def upstream(name,script):
            sp=tmp_path/f"{name}.json"; log=tmp_path/f"{name}.jsonl"; log.unlink(missing_ok=True); sp.write_text(json.dumps(script),encoding="utf8")
            p,port=start([NODE,str(FAKE),"--port","0","--script",str(sp),"--log",str(log)]);procs.append(p);return port,log
        ap,alog=upstream("anthropic",anthropic);op,olog=upstream("omni",omni)
        home=tmp_path/"home";state=home/"state";state.mkdir(parents=True,exist_ok=True)
        base=json.loads((ROOT/"config/spillover.json").read_text(encoding="utf-8-sig"));base["proxy"].update({"mode":mode,"probe_interval_sec":600,"fallback_first_content_timeout_ms":250,"fallback_retry_budget_ms":80,"fallback_persistent_outage_sec":60,"fallback_health_fail_threshold":3,"fallback_health_ttl_ok_ms":100,"fallback_health_ttl_fail_ms":30,"stream_silence_abort_ms":150,"ping_interval_ms":30,"fallback_window_tokens":200000,"allow_fault_injection":True})
        if extra:base["proxy"].update(extra)
        if top_level:base.update(top_level)
        (home/"config.json").write_text(json.dumps(base),encoding="utf8")
        if initial_state is not None: (state/"state.json").write_text(json.dumps(initial_state),encoding="utf8")
        cmd=[NODE,str(PROXY),"--test","--state-dir",str(state),"--anthropic-base",f"http://127.0.0.1:{ap}","--omniroute-base",f"http://127.0.0.1:{op}","--lane-key",LANE,"--port","0","--now-offset",str(now_offset)]
        pp,port=start(cmd);procs.append(pp);yield port,state,alog,olog,home
    finally:
        for p in reversed(procs):stop(p)

def request(port,path="/v1/messages",method="POST",body=b'{"model":"claude-sonnet","messages":[{"role":"user","content":"hi"}]}',headers=None):
    h={"host":f"127.0.0.1:{port}","authorization":OAUTH,"user-agent":UA,"anthropic-version":"2023-06-01","content-type":"application/json",**(headers or {})}
    c=http.client.HTTPConnection("127.0.0.1",port,timeout=3);c.request(method,path,body=body,headers=h);r=c.getresponse();data=r.read();hs={k.lower():v for k,v in r.getheaders()};c.close();return r.status,hs,data

def health(port):
    c=http.client.HTTPConnection("127.0.0.1",port,timeout=3);c.request("GET","/__spillover/health",headers={"host":f"127.0.0.1:{port}"});r=c.getresponse();data=json.loads(r.read());c.close();return data

def rows(path):return [json.loads(x) for x in path.read_text(encoding="utf8").splitlines()] if path.exists() else []
def basic_sse(model="fallback-id"):
    return [{"delay_ms":0,"raw":f'event: message_start\ndata: {{"type":"message_start","message":{{"model":"{model}","content":[]}}}}\n\n'},
      {"delay_ms":0,"raw":'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'},
      {"delay_ms":0,"raw":'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ok"}}\n\n'},
      {"delay_ms":0,"raw":'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n'}]

def test_direct_byte_identical_and_special_paths(tmp_path):
    blob=b'raw\x00beta\xff'; scenarios=[]
    for method,path in [("POST","/v1/messages?beta=true"),("HEAD","/api/hello"),("GET","/v1/models"),("POST","/v1/messages/count_tokens")]:
        scenarios.append({"match":{"method":method,"path":path},"status":200,"headers":{"content-type":"application/octet-stream","x-unknown-beta":"future"},"body":blob.decode("latin1") if method!="HEAD" else ""})
    with rig(tmp_path,scenarios,[],mode="observe") as (port,_,alog,_,_):
        status,h,data=request(port,"/v1/messages?beta=true",body=b'{"unknown":"beta"}',headers={"anthropic-beta":"future-value"});assert status==200 and h["x-unknown-beta"]=="future"
        for method,path in [("HEAD","/api/hello"),("GET","/v1/models"),("POST","/v1/messages/count_tokens")]: assert request(port,path,method)[0]==200
        sent=rows(alog)[0];assert sent["authorization_sha256"]==hashlib.sha256(OAUTH.encode()).hexdigest()

def test_errors_and_transient_are_unmodified(tmp_path):
    bodies=[({"match":{"path":"/v1/messages"},"status":400,"headers":{"x-test":"sig"},"body":"invalid-signature"},400,b"invalid-signature"),({"match":{"path":"/v1/messages"},"status":529,"body":"busy"},529,b"busy"),({"match":{"path":"/v1/messages"},"status":401,"body":"no"},401,b"no"),({"match":{"path":"/v1/messages"},"status":429,"body":"transient"},429,b"transient")]
    with rig(tmp_path,[x[0] for x in bodies],[],mode="spill") as (port,*_):
        for _,status,body in bodies:
            got=request(port);assert (got[0],got[2])==(status,body)

def test_limit_replayed_without_claude_secret_and_state(tmp_path):
    anth=[{"match":{"path":"/v1/messages"},"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}]
    omni=[{"match":{"method":"GET","path":"/v1/models"},"status":200,"body":{}},{"match":{"path":"/v1/messages"},"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()}]
    body=json.dumps({"model":"claude-sonnet","metadata":{"x":1},"context_management":{},"tools":[{"name":"Bash","input_schema":{}},{"name":"web_search_2025","type":"web_search_2025"},{"name":"lazy","defer_loading":True}],"messages":[{"role":"user","content":"hi"}]}).encode()
    with rig(tmp_path,anth,omni) as (port,state,_,olog,_):
        status,_,data=request(port,body=body,headers={"x-bravo-debug":"drop","x-claude-code-test":"drop"});assert status==200 and b'"model":"claude-sonnet"' in data
        st=json.loads((state/"state.json").read_text());assert st["mode"]=="spilling" and st["limit"]["reset_source"]=="unified-reset"
        logs=rows(olog);post=next(x for x in logs if x["method"]=="POST");assert post["authorization_sha256"]==hashlib.sha256(f"Bearer {LANE}".encode()).hexdigest();assert post["x-route-model"]=="bravo-fallback"
        assert not ({"x-bravo-debug","x-claude-code-test","user-agent"}&set(post["header_names"]));assert "metadata" not in post["top_level_body_keys"]

def test_spilling_eligibility_and_count_tokens(tmp_path):
    anth=[{"match":{"path":"/v1/messages"},"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}]+[{"status":200,"body":"direct"} for _ in range(4)]
    omni=[{"match":{"method":"GET","path":"/v1/models"},"status":200,"body":{}},{"match":{"path":"/v1/messages"},"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()}]
    with rig(tmp_path,anth,omni) as (port,_,alog,olog,_):
        assert request(port)[0]==200
        assert request(port,"/v1/messages/count_tokens")[0]==404
        for headers in ({"x-api-key":"x"},{"user-agent":"sdk-cli/1"},{"x-bravo-lane":"automation"},{"x-bravo-spill":"deny"}):assert request(port,headers=headers)[2]==b"direct"
        assert len([x for x in rows(olog) if x["method"]=="POST"])==1 and len(rows(alog))==5

@pytest.mark.parametrize("mode",["observe","passthrough"])
def test_non_spill_modes(mode,tmp_path):
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}]
    with rig(tmp_path,anth,[],mode=mode) as (port,state,*_):
        assert request(port)[0]==429;assert json.loads((state/"state.json").read_text())["mode"]=="direct"

def test_probe_400_flips_direct_and_is_verbatim(tmp_path):
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY},{"status":400,"headers":{"x-probe":"yes"},"body":"invalid-signature"}]
    omni=[{"match":{"method":"GET","path":"/v1/models"},"status":200,"body":{}},{"match":{"path":"/v1/messages"},"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()}]
    with rig(tmp_path,anth,omni,extra={"probe_interval_sec":0}) as (port,state,*_):
        assert request(port)[0]==200;got=request(port);assert got[0]==400 and got[2]==b"invalid-signature";assert json.loads((state/"state.json").read_text())["mode"]=="direct"

def test_fallback_thinking_removed_indices_and_model(tmp_path):
    sse=(ROOT/"scripts/tests/fixtures/spillover/omniroute_stream_with_thinking.sse").read_text()
    frames=[{"raw":x+"\n\n"} for x in sse.strip().split("\n\n")]
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}];omni=[{"match":{"method":"GET"},"status":200,"body":{}},{"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":frames}]
    with rig(tmp_path,anth,omni) as (port,*_):
        status,_,body=request(port);text=body.decode();assert status==200 and "thinking" not in text and '"index":0' in text and '"index":1' in text and "fallback-synthetic-model" not in text

def test_context_overflow_exact_wording(tmp_path):
    overflow=json.loads((ROOT/"scripts/tests/fixtures/spillover/omniroute_context_length_exceeded.json").read_text())
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}];omni=[{"match":{"method":"GET"},"status":200,"body":{}},{"status":400,"headers":{"content-type":"application/json"},"body":overflow["body"]}]
    with rig(tmp_path,anth,omni) as (port,*_):
        status,_,body=request(port);assert status==400;assert json.loads(body)["error"]["message"]=="prompt is too long: 150321 tokens > 128000 maximum"

def test_context_overflow_exact_wording_in_stream(tmp_path):
    # Finding 6: a pre-content SSE 'error' frame naming a context overflow gets the same exact
    # wording as the non-stream path above, instead of a generic "fallback error before content".
    stream=(ROOT/"scripts/tests/fixtures/spillover/omniroute_stream_context_overflow.sse").read_text()
    frames=[{"raw":x+"\n\n"} for x in stream.strip().split("\n\n")]
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}]
    omni=[{"match":{"method":"GET"},"status":200,"body":{}},{"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":frames}]
    with rig(tmp_path,anth,omni) as (port,*_):
        status,_,body=request(port);assert status==400
        assert json.loads(body)["error"]["message"]=="prompt is too long: 150321 tokens > 128000 maximum"

def test_security_gates_and_poison(tmp_path):
    with rig(tmp_path,[],[],mode="spill") as (port,state,*_):
        assert request(port,headers={"host":"evil.example"})[0]==403
        assert request(port,method="OPTIONS")[0]==405
        assert request(port,headers={"anthropic-version":""})[0]==400
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}];omni=[{"match":{"method":"GET"},"status":200,"body":{}}]
    with rig(tmp_path/"poison",anth,omni) as (port,state,_,olog,_):
        body=b'{"model":"claude-sonnet","messages":[{"role":"user","content":"sk-ant-poison"}]}'
        assert request(port,body=body)[0]==429
        # The vacuous check used to be that events.jsonl never contains headers or bodies -- true
        # by construction regardless of the poison gate, so it proved nothing. Prove instead that
        # OmniRoute never received the poisoned request at all (only the earlier health GET).
        posted=[x for x in rows(olog) if x["method"]=="POST"]
        assert posted==[]

def test_header_carried_poison_dropped_by_allowlist(tmp_path):
    # Finding 8b: an extra client header smuggling a Claude-shaped secret is dropped by the
    # allowlist itself (finding 7), before poisoned() would ever get a chance to inspect it.
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}]
    omni=[{"match":{"method":"GET","path":"/v1/models"},"status":200,"body":{}},
          {"match":{"path":"/v1/messages"},"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()}]
    with rig(tmp_path,anth,omni) as (port,state,_,olog,_):
        status,_,data=request(port,headers={"x-leaky-secret":"sk-ant-should-never-leave-this-header"})
        assert status==200 and b'"model":"claude-sonnet"' in data
        post=next(x for x in rows(olog) if x["method"]=="POST")
        assert "x-leaky-secret" not in post["header_names"]
        assert post["contains_sk_ant_header_value"] is False

def test_fallback_headers_exact_allowlisted_set(tmp_path):
    # Finding 8c: pin the exact header set OmniRoute receives on a normal spill, so a future
    # change to the allowlist (or an accidental extra header) shows up as a failing test.
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}]
    omni=[{"match":{"method":"GET","path":"/v1/models"},"status":200,"body":{}},
          {"match":{"path":"/v1/messages"},"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()}]
    with rig(tmp_path,anth,omni) as (port,state,_,olog,_):
        assert request(port)[0]==200
        post=next(x for x in rows(olog) if x["method"]=="POST")
        assert set(post["header_names"])=={"accept-encoding","anthropic-version","authorization","connection","content-length","content-type","host","x-omniroute-compression","x-route-model"}

def test_oversize_replay_returns_stored_429(tmp_path):
    original=json.dumps(LIMIT_BODY,separators=(",",":")).encode()
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":original.decode()}]
    omni=[]
    with rig(tmp_path,anth,omni,extra={"max_replay_body_bytes":80}) as (port,state,*_):
        body=json.dumps({"model":"claude-sonnet","messages":[{"role":"user","content":"x"*200}]}).encode()
        status,_,got=request(port,body=body);assert status==429 and got==original


def test_fault_injection_honored_only_when_allowed(tmp_path):
    from datetime import datetime, timedelta, timezone
    expires=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat()
    omni=[{"match":{"method":"GET"},"status":200,"body":{}},{"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()}]
    with rig(tmp_path,[],omni) as (port,state,*_):
        (state/"fault.json").write_text(json.dumps({"mode":"force_limit","expires_at":expires}))
        assert request(port)[0]==200
        assert json.loads((state/"state.json").read_text())["mode"]=="spilling"


def test_fallback_short_then_persistent_failure(tmp_path):
    original=json.dumps(LIMIT_BODY,separators=(",",":")).encode()
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":original.decode()}]
    omni=[{"match":{"method":"GET"},"status":200,"body":{}},{"status":500,"body":"down"}]
    with rig(tmp_path,anth,omni,extra={"fallback_retry_budget_ms":0,"fallback_health_fail_threshold":2}) as (port,state,*_):
        assert request(port)[0]==529
        # Cached failed health makes the next request persistent at the configured threshold.
        time.sleep(.05)
        status,_,body=request(port);assert status==429 and body==original


def test_sse_frame_size_cap_ends_stream_and_marks_unhealthy(tmp_path):
    # Finding 3: a fallback stream frame with no blank-line terminator must not grow the SSE
    # reassembly buffer without bound.
    committed=basic_sse()[0]["raw"]+basic_sse()[1]["raw"]  # message_start + content_block_start, both properly terminated
    huge="x"*5000  # one giant chunk, no blank-line terminator anywhere
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}]
    omni=[{"match":{"method":"GET","path":"/v1/models"},"status":200,"body":{}},
          {"match":{"path":"/v1/messages"},"status":200,"headers":{"content-type":"text/event-stream"},
           "sse_frames":[{"raw":committed},{"raw":huge}]}]
    with rig(tmp_path,anth,omni,extra={"max_sse_frame_bytes":1000}) as (port,*_):
        status,_,body=request(port)
        assert status==200 and b'"type":"api_error"' in body and b'fallback stream frame too large' in body
        assert health(port)["fallback_healthy"] is False

def test_stream_error_rewritten_and_silence_aborted(tmp_path):
    stream=(ROOT/"scripts/tests/fixtures/spillover/omniroute_stream_error.sse").read_text()
    frames=[{"raw":x+"\n\n"} for x in stream.strip().split("\n\n")]
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}]
    omni=[{"match":{"method":"GET"},"status":200,"body":{}},{"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":frames}]
    with rig(tmp_path,anth,omni) as (port,*_):
        status,_,body=request(port);assert status==200 and b'"type":"api_error"' in body and b'"type":"stream_error"' not in body
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}]
    omni=[{"match":{"method":"GET"},"status":200,"body":{}},{"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()[:2],"hang_ms":500}]
    with rig(tmp_path/"poison",anth,omni,extra={"stream_silence_abort_ms":80,"ping_interval_ms":20}) as (port,*_):
        status,_,body=request(port);assert status==200 and b'overloaded_error' in body


def test_probe_transient_429_stays_spilling_and_uses_fallback(tmp_path):
    # Finding 5: a probe answer of 429 -- of ANY kind, including a merely transient one that never
    # reached full unified-rejected shape -- must not flip the state machine back to direct. Only a
    # non-429, non-5xx, non-529 probe answer proves the account is actually clear again.
    transient_headers={"content-type":"application/json"}  # no unified-rejected marker => "transient"
    transient_body=json.dumps({"type":"error","error":{"type":"rate_limit_error","message":"transient"}})
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY},{"status":429,"headers":transient_headers,"body":transient_body}]
    omni=[{"match":{"method":"GET","path":"/v1/models"},"status":200,"body":{}},
          {"match":{"path":"/v1/messages"},"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()},
          {"match":{"path":"/v1/messages"},"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()}]
    with rig(tmp_path,anth,omni,extra={"probe_interval_sec":0}) as (port,state,*_):
        assert request(port)[0]==200  # first request: 429 from Anthropic enters spilling, served by fallback
        status,_,body=request(port)  # second request is the due probe; Anthropic answers transient 429
        assert status==200 and b'"model":"claude-sonnet"' in body  # served by fallback, not passed through
        assert health(port)["mode"]=="spilling"

def test_alert_spawn_error_does_not_crash_proxy(tmp_path):
    # Finding 1: a bad python_exe (or missing script) makes childProcess.spawn() emit an async
    # 'error' event rather than throw. Without a listener that crashes the worker exactly when it
    # is entering fallback. --test suppresses real alerts by default; test_alerts_enabled is the
    # narrow escape hatch that lets this test exercise the spawn path itself.
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}]
    omni=[{"match":{"method":"GET","path":"/v1/models"},"status":200,"body":{}},
          {"match":{"path":"/v1/messages"},"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()}]
    with rig(tmp_path,anth,omni,extra={"test_alerts_enabled":True},top_level={"python_exe":str(tmp_path/"no-such-python.exe")}) as (port,_,_,_,home):
        status,_,data=request(port)
        assert status==200 and b'"model":"claude-sonnet"' in data
        assert health(port)["ok"] is True  # the worker is still alive and answering
        time.sleep(.3)  # the spawn 'error' event is asynchronous
        assert (home/"state"/"logs"/"alerts.log").exists()

def test_client_disconnect_during_ping_keeps_proxy_healthy(tmp_path):
    # Finding 4: the ping/silence timer's fire-and-forget write must not turn a dead client socket
    # into an unhandled rejection.
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY}]
    omni=[{"match":{"method":"GET","path":"/v1/models"},"status":200,"body":{}},
          {"match":{"path":"/v1/messages"},"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()[:2],"hang_ms":2000}]
    with rig(tmp_path,anth,omni,extra={"ping_interval_ms":20,"stream_silence_abort_ms":100000}) as (port,*_):
        h={"host":f"127.0.0.1:{port}","authorization":OAUTH,"user-agent":UA,"anthropic-version":"2023-06-01","content-type":"application/json"}
        c=http.client.HTTPConnection("127.0.0.1",port,timeout=3)
        c.request("POST","/v1/messages",body=b'{"model":"claude-sonnet","messages":[{"role":"user","content":"hi"}]}',headers=h)
        r=c.getresponse()
        r.read(1)  # let the stream commit, then disconnect mid-stream
        c.close()
        time.sleep(.3)  # let several ping ticks fire against the closed socket
        assert health(port)["ok"] is True

def test_state_persist_failure_reported_in_health(tmp_path):
    # Finding 2: saveState().catch(()=>{}) used to drop persistence failures on the floor. Health
    # must surface persist_ok:false while the worker keeps serving requests.
    anth=[{"status":200,"body":"direct"} for _ in range(3)]
    with rig(tmp_path,anth,[],mode="observe",extra={"test_force_persist_failure":True}) as (port,*_):
        for _ in range(3):
            assert request(port)[0]==200
        assert health(port)["persist_ok"] is False

def test_state_persist_failure_alert_rate_limited(tmp_path):
    # Finding 2: at 3 consecutive persistence failures the proxy alerts once, and stays quiet on
    # further failures within the hour rather than alerting on every request.
    anth=[{"status":200,"body":"direct"} for _ in range(6)]
    with rig(tmp_path,anth,[],mode="observe",
             extra={"test_force_persist_failure":True,"test_alerts_enabled":True},
             top_level={"python_exe":str(tmp_path/"no-such-python.exe")}) as (port,_,_,_,home):
        for _ in range(6):
            assert request(port)[0]==200
        time.sleep(.3)
        alerts=(home/"state"/"logs"/"alerts.log").read_text(encoding="utf8")
        assert alerts.count("state_write_failed")==1

def test_now_offset_reset_goes_direct(tmp_path):
    initial={"schema_version":1,"mode":"spilling","config_mode":"spill","limit":{"detected_at":"2026-01-01T00:00:00Z","reset_at":"2026-09-13T00:30:00Z","reset_source":"unified-reset","claim":"five_hour","captured":"synthetic.json"}}
    anth=[{"status":400,"body":"after-reset"}]
    with rig(tmp_path,anth,[],now_offset=31_536_000,initial_state=initial) as (port,*_):
        status,_,body=request(port);assert status==400 and body==b"after-reset"

def test_twenty_limits_one_transition(tmp_path):
    import concurrent.futures
    anth=[{"status":429,"headers":LIMIT_HEADERS,"body":LIMIT_BODY} for _ in range(20)]
    omni=[]
    for _ in range(20):
        omni += [{"match":{"method":"GET"},"status":200,"body":{}},{"match":{"method":"POST"},"status":200,"headers":{"content-type":"text/event-stream"},"sse_frames":basic_sse()}]
    with rig(tmp_path,anth,omni,mode="spill") as (port,state,*_):
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
            results=list(ex.map(lambda _ : request(port)[0],range(20)))
        assert results==[200]*20
        events=(state/"events.jsonl").read_text()
        assert events.count("entered_fallback")==1
