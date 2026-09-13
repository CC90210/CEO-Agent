"""Contract tests for the pure Claude Spillover limit detector."""
from __future__ import annotations
import json, subprocess
from datetime import datetime, timezone
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[2]
DETECTOR = ROOT / "scripts" / "spillover" / "limit_detector.js"
def js(expression):
    source=f"const d=require({json.dumps(str(DETECTOR))}); console.log(JSON.stringify({expression}));"
    return json.loads(subprocess.check_output(["node","-e",source],text=True))
def classify(status=429, headers=None, body=None, now_ms=1_800_000_000_000, opts=None):
    inp={"status":status,"headers":headers or {},"bodyText":json.dumps(body or {}),"nowMs":now_ms}
    return js(f"d.classify({json.dumps(inp)}, {json.dumps(opts or {})})")
BASE={"anthropic-ratelimit-unified-status":"rejected","anthropic-ratelimit-unified-representative-claim":"five_hour","anthropic-ratelimit-unified-reset":"1800003600"}
ERROR={"error":{"type":"rate_limit_error","message":"synthetic"}}
@pytest.mark.parametrize("status,headers,body,kind",[
 (200,{}, {},"none"),(529,{}, {},"transient"),(429,{},ERROR,"transient"),
 (429,{**BASE,"anthropic-ratelimit-unified-status":"allowed","anthropic-ratelimit-unified-overage-status":"rejected"},ERROR,"transient"),
 (429,BASE,{"error":{"type":"api_error"}},"transient"),(429,{**BASE,"anthropic-ratelimit-unified-fallback":"available"},ERROR,"transient"),
 (429,{**BASE,"anthropic-ratelimit-unified-overage-in-use":"true"},ERROR,"transient"),(429,BASE,ERROR,"subscription_limit"),
 (429,{**BASE,"anthropic-ratelimit-unified-representative-claim":"seven_day"},ERROR,"subscription_limit"),
 (429,{**BASE,"anthropic-ratelimit-unified-representative-claim":"seven_day_opus"},ERROR,"model_limit")])
def test_classify_branches(status,headers,body,kind): assert classify(status,headers,body)["kind"]==kind
def test_reset_epoch_rfc3339_and_retry_http_date():
    assert classify(headers=BASE,body=ERROR)["reset_at"]==1_800_003_600
    rfc={**BASE,"anthropic-ratelimit-unified-reset":"2027-01-15T09:00:00Z"}
    assert classify(headers=rfc,body=ERROR)["reset_at"]==int(datetime(2027,1,15,9,tzinfo=timezone.utc).timestamp())
    h={k:v for k,v in BASE.items() if not k.endswith("reset")}; h["retry-after"]="Fri, 15 Jan 2027 09:00:00 GMT"
    assert classify(headers=h,body=ERROR)["reset_source"]=="retry-after"
def test_date_skew_and_clamps():
    assert classify(headers={**BASE,"anthropic-ratelimit-unified-reset":"1"},body=ERROR)["reset_at"]==1_800_000_060
    assert classify(headers={**BASE,"anthropic-ratelimit-unified-reset":"9999999999"},body=ERROR)["reset_at"]==1_800_691_200
    skew={**BASE,"anthropic-ratelimit-unified-reset":"1800000100","date":"Fri, 15 Jan 2027 07:58:20 GMT"}
    assert classify(headers=skew,body=ERROR)["reset_at"]>=1_800_000_060
@pytest.mark.parametrize("ua,entry,version",[("claude-cli/2.1.268 (external, cli)","cli","2.1.268"),("claude-cli/2.1.268 (external, claude-vscode, win32)","claude-vscode","2.1.268"),("claude-cli/2.1.268 (internal, cli)",None,"2.1.268"),("sdk-cli/1.0",None,None)])
def test_parse_entrypoint_variants(ua,entry,version):
    assert js(f"d.parseEntrypoint({json.dumps(ua)})")==entry
    assert js(f"d.claudeCodeVersion({json.dumps(ua)})")==version
def test_oauth_and_estimate_tokens_skip_base64():
    assert js("d.isOAuthBearer('Bearer sk-ant-oat-test')") is True
    assert js("d.isOAuthBearer('Bearer sk-ant-api-test')") is False
    small={"messages":[{"role":"user","content":[{"type":"text","text":"hello"},{"type":"image","source":{"type":"base64","data":"A"*20}}]}]}
    baseline=js(f"d.estimateTokens({json.dumps(small)})")
    expression=f"(()=>{{const b={json.dumps(small)}; b.messages[0].content[1].source.data='A'.repeat(200000); return d.estimateTokens(b)}})()"
    assert baseline==js(expression)
    tool={"tools":[{"name":"Bash","input_schema":{"type":"object","properties":{"command":{"type":"string"}}}}]}
    assert js(f"d.estimateTokens({json.dumps(tool)})")>10

