"""Direct test of warm_claude_pool — bypass bridge SSE layer to see if
events flow at all."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bravo_cli.warm_claude_pool import use_or_create
from pathlib import Path

events_seen = []

def on_event(ev):
    events_seen.append(ev)
    print(f"[{time.time():.1f}] EVENT: type={ev.get('type')} subtype={ev.get('subtype')} keys={list(ev.keys())[:6]}", flush=True)

print(f"[{time.time():.1f}] spawning warm pool entry for bravo", flush=True)
wp = use_or_create(
    pool_key="test:direct",
    agent="bravo",
    root=Path("c:/Users/User/Business-Empire-Agent"),
    prompt_text="yo wsp",
    resume_session_id=None,
)
print(f"[{time.time():.1f}] spawned. is_alive={wp.is_alive()}", flush=True)

print(f"[{time.time():.1f}] calling send_turn", flush=True)
ok = wp.send_turn("yo wsp", on_event, max_seconds=120)
print(f"[{time.time():.1f}] send_turn returned ok={ok}, events_seen={len(events_seen)}", flush=True)

wp.kill("test_complete")
