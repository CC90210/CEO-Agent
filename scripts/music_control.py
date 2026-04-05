#!/usr/bin/env python3
"""
SoundCloud Music Control — Atomic browser-based music commands.
Uses Chrome + AppleScript. Requires: Chrome > View > Developer > Allow JavaScript from Apple Events.

Usage:
  python3 scripts/music_control.py play --query "24 songs playboy carti"
  python3 scripts/music_control.py pause
  python3 scripts/music_control.py resume
  python3 scripts/music_control.py skip
  python3 scripts/music_control.py previous
  python3 scripts/music_control.py current
  python3 scripts/music_control.py search --query "lo-fi beats"

All commands support --json flag.
"""

import argparse
import json
import platform
import re
import subprocess
import sys
import time
import urllib.parse


def guard_macos():
    if platform.system() != "Darwin":
        print(json.dumps({"error": "music_control.py is macOS-only."}))
        sys.exit(1)


def run_osascript(script, timeout=30):
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip()}
        return {"ok": True, "output": result.stdout.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timed out after {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def chrome_open_url(url):
    """Open URL in Chrome and wait for load."""
    script = f'''
tell application "Google Chrome"
    activate
    if (count of windows) = 0 then
        make new window
    end if
    set URL of active tab of window 1 to "{url}"
end tell
delay 1
set maxWait to 15
set waited to 0
repeat while waited < maxWait
    tell application "Google Chrome"
        set isLoading to loading of active tab of window 1
    end tell
    if not isLoading then exit repeat
    delay 1
    set waited to waited + 1
end repeat
tell application "Google Chrome"
    return title of active tab of window 1
end tell
'''
    return run_osascript(script, timeout=25)


def chrome_js(js_code, timeout=15):
    """Execute JavaScript in Chrome's active tab."""
    escaped = js_code.replace("\\", "\\\\").replace('"', '\\"')
    script = f'''
tell application "Google Chrome"
    set jsResult to execute active tab of window 1 javascript "{escaped}"
    return jsResult
end tell
'''
    return run_osascript(script, timeout=timeout)


def chrome_get_url():
    """Get Chrome active tab URL."""
    return run_osascript('tell application "Google Chrome" to return URL of active tab of window 1')


def chrome_get_title():
    """Get Chrome active tab title."""
    return run_osascript('tell application "Google Chrome" to return title of active tab of window 1')


def search_soundcloud_curl(query, limit=5):
    """Search SoundCloud via curl (no JS needed). Returns list of track URLs."""
    encoded = urllib.parse.quote(query)
    url = f"https://soundcloud.com/search?q={encoded}"
    try:
        result = subprocess.run(
            ["curl", "-s", "-L", url, "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return []
        html = result.stdout
        # Extract track URLs from HTML (format: /username/track-name)
        urls = re.findall(r'href="(/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)"', html)
        seen = []
        skip = {'/search', '/discover', '/you/', '/legal/', '/pages/', '/terms', '/privacy',
                '/settings', '/messages', '/notifications', '/upload', '/charts', '/people',
                '/stations', '/feed', '/library', '/collection', '/pro', '/go'}
        for u in urls:
            if u in seen:
                continue
            parts = u.strip("/").split("/")
            if len(parts) != 2:
                continue
            if any(s in u for s in skip):
                continue
            if parts[0] in ('explore', 'tags', 'jobs', 'press', 'creator', 'blog', 'community'):
                continue
            seen.append(u)
            if len(seen) >= limit:
                break
        return seen
    except Exception:
        return []


# ---- COMMANDS ----

def cmd_play(args):
    """Search SoundCloud and play the first result."""
    query = args.query

    # Step 1: Find the first track URL via curl (no JS needed)
    track_urls = search_soundcloud_curl(query)

    if not track_urls:
        return {"ok": False, "error": f"No tracks found for '{query}'"}

    track_url = f"https://soundcloud.com{track_urls[0]}"

    # Step 2: Open the track page directly in Chrome
    r = chrome_open_url(track_url)
    if not r.get("ok"):
        return r

    # Step 3: Wait for the track page to fully render
    time.sleep(3)

    # Step 4: Get track info from page title
    title_r = chrome_get_title()
    track_title = title_r.get("output", "Unknown") if title_r.get("ok") else "Unknown"
    if " | " in track_title:
        track_title = track_title.split(" | ")[0]

    # Step 5: Try clicking play via JS first
    r3 = chrome_js("""
(function() {
    var btn = document.querySelector('.playButton, [aria-label*="Play"], [title="Play"], button.sc-button-play');
    if (btn) { btn.click(); return 'playing'; }
    var bottom = document.querySelector('.playControls__play');
    if (bottom) { bottom.click(); return 'playing-bottom'; }
    return 'no-play-button';
})()
""")

    play_status = r3.get("output", "") if r3.get("ok") else ""

    if not r3.get("ok") or play_status == "no-play-button":
        # Fallback: send spacebar via System Events (SoundCloud keyboard shortcut)
        run_osascript('''
tell application "Google Chrome" to activate
delay 0.5
tell application "System Events"
    key code 49
end tell
''')

    return {"ok": True, "output": f"Now playing: {track_title}"}


def cmd_pause(args):
    """Pause/toggle playback."""
    url_r = chrome_get_url()
    if url_r.get("ok") and "soundcloud.com" in url_r.get("output", ""):
        r = chrome_js("""
(function() {
    var btn = document.querySelector('.playControls__play');
    if (btn) { btn.click(); return 'toggled'; }
    return 'no-button';
})()
""")
        if r.get("ok") and r.get("output") != "no-button":
            return {"ok": True, "output": "Toggled play/pause"}

    # Fallback: spacebar
    run_osascript('''
tell application "Google Chrome" to activate
delay 0.3
tell application "System Events"
    key code 49
end tell
''')
    return {"ok": True, "output": "Toggled play/pause"}


def cmd_resume(args):
    """Resume playback (same as pause — toggle)."""
    return cmd_pause(args)


def cmd_skip(args):
    """Skip to next track."""
    url_r = chrome_get_url()
    if url_r.get("ok") and "soundcloud.com" in url_r.get("output", ""):
        r = chrome_js("""
(function() {
    var btn = document.querySelector('.playControls__next, .skipControl__next');
    if (btn) { btn.click(); return 'skipped'; }
    return 'no-button';
})()
""")
        if r.get("ok") and r.get("output") != "no-button":
            return {"ok": True, "output": "Skipped to next track"}

    # Fallback: Shift+Right arrow
    run_osascript('''
tell application "Google Chrome" to activate
delay 0.3
tell application "System Events"
    key code 124 using {shift down}
end tell
''')
    return {"ok": True, "output": "Skipped to next track"}


def cmd_previous(args):
    """Go to previous track."""
    url_r = chrome_get_url()
    if url_r.get("ok") and "soundcloud.com" in url_r.get("output", ""):
        r = chrome_js("""
(function() {
    var btn = document.querySelector('.playControls__prev, .skipControl__previous');
    if (btn) { btn.click(); return 'prev'; }
    return 'no-button';
})()
""")
        if r.get("ok") and r.get("output") != "no-button":
            return {"ok": True, "output": "Went to previous track"}

    # Fallback: Shift+Left arrow
    run_osascript('''
tell application "Google Chrome" to activate
delay 0.3
tell application "System Events"
    key code 123 using {shift down}
end tell
''')
    return {"ok": True, "output": "Went to previous track"}


def cmd_current(args):
    """Get info about the currently playing track."""
    url_r = chrome_get_url()
    if not url_r.get("ok") or "soundcloud.com" not in url_r.get("output", ""):
        return {"ok": False, "error": "Chrome is not on SoundCloud"}

    r = chrome_js("""
(function() {
    var title = document.querySelector('.playbackSoundBadge__titleLink span');
    var artist = document.querySelector('.playbackSoundBadge__lightLink span');
    var progress = document.querySelector('.playbackTimeline__timePassed span:last-child');
    var duration = document.querySelector('.playbackTimeline__duration span:last-child');
    var isPlaying = !!document.querySelector('.playControls__play.playing');
    return JSON.stringify({
        title: title ? title.textContent.trim() : 'Unknown',
        artist: artist ? artist.textContent.trim() : 'Unknown',
        progress: progress ? progress.textContent.trim() : '?',
        duration: duration ? duration.textContent.trim() : '?',
        playing: isPlaying
    });
})()
""")
    if not r.get("ok"):
        # Fallback: page title
        title_r = chrome_get_title()
        title = title_r.get("output", "Unknown") if title_r.get("ok") else "Unknown"
        if " | " in title:
            title = title.split(" | ")[0]
        return {"ok": True, "output": f"On SoundCloud: {title}"}

    try:
        info = json.loads(r["output"])
        status = "Playing" if info.get("playing") else "Paused"
        return {
            "ok": True,
            "output": f"{status}: {info['title']} by {info['artist']} [{info['progress']}/{info['duration']}]",
            "detail": info
        }
    except (json.JSONDecodeError, KeyError):
        return {"ok": True, "output": r["output"]}


def cmd_search(args):
    """Search SoundCloud and show results."""
    query = args.query
    encoded = urllib.parse.quote(query)
    search_url = f"https://soundcloud.com/search?q={encoded}"

    r = chrome_open_url(search_url)
    if not r.get("ok"):
        return r

    time.sleep(2)

    # Try getting result titles via JS
    r2 = chrome_js("""
(function() {
    var results = [];
    var items = document.querySelectorAll('.soundTitle__title span');
    for (var i = 0; i < Math.min(items.length, 10); i++) {
        results.push((i+1) + '. ' + items[i].textContent.trim());
    }
    return results.length > 0 ? results.join('\\n') : 'Results loaded (enable JS for details)';
})()
""")

    if r2.get("ok"):
        return r2

    # Fallback: just confirm the page loaded
    return {"ok": True, "output": f"Search results loaded for '{query}'"}


# ---- MAIN ----

def main():
    guard_macos()

    json_output = "--json" in sys.argv
    if json_output:
        sys.argv.remove("--json")

    parser = argparse.ArgumentParser(description="SoundCloud Music Control via Chrome")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("play", help="Search and play a track")
    p.add_argument("--query", required=True, help="Search query")

    sub.add_parser("pause", help="Pause current track")
    sub.add_parser("resume", help="Resume playback")
    sub.add_parser("skip", help="Skip to next track")
    sub.add_parser("previous", help="Go to previous track")
    sub.add_parser("current", help="Show current track info")

    p = sub.add_parser("search", help="Search without playing")
    p.add_argument("--query", required=True, help="Search query")

    args = parser.parse_args()

    commands = {
        "play": cmd_play, "pause": cmd_pause, "resume": cmd_resume,
        "skip": cmd_skip, "previous": cmd_previous, "current": cmd_current,
        "search": cmd_search,
    }

    result = commands[args.command](args)

    if json_output:
        print(json.dumps(result))
    else:
        if result.get("ok"):
            print(result.get("output", "Done."))
        else:
            print(f"ERROR: {result.get('error', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
