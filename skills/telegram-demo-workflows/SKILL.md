---
name: telegram-demo-workflows
description: 5 verified, rehearsed Telegram → MacBook demo workflows for filming content. Each is designed to work 100% of the time, look visually impressive on camera, and be completable in under 60 seconds. Use these when filming "AI takes over my computer" content.
triggers: [demo, film, content, record, show, camera, telegram controls, computer control demo]
tier: full
---

# Telegram Demo Workflows — 5 Content-Ready Sequences

> Every workflow below has been stress-tested. Each works in a single Telegram message.
> Visual: cursor animates on screen. Impressive in frame.

---

## Before Filming — Quick Pre-Flight

Send from Telegram first:
```
screenshot
```
Confirm you get back a screenshot. If yes — you're live. Takes 3 seconds.

---

## Demo 1: "I just told my AI to open YouTube and play music"

**Send this exact message to Telegram:**
```
play lofi hip hop on youtube
```

**What happens visually:**
1. Chrome opens (or activates)
2. YouTube search navigates automatically
3. First video auto-clicks and plays
4. Cursor moves on screen (visible to camera)

**Why it's content-worthy:** Viewer sees the YouTube page load and music start playing from a single text message. Zero touch on your end.

**Backup if YouTube play fails:**
```
open youtube.com in chrome and scroll down
```

---

## Demo 2: "My AI agent took a screenshot and sent it to me"

**Send:**
```
take a screenshot and show me what's on my screen
```

**What happens:**
1. Screenshot captured
2. Image appears in your Telegram chat
3. Claude describes what's on screen

**Why it's content-worthy:** Your phone literally receives a live photo of your MacBook screen. Undeniable proof the agent controls your computer.

---

## Demo 3: "I sent one message and it opened my apps and set up my workspace"

**Send:**
```
set up my morning workspace: open Chrome, open Spotify, and snap Chrome to the left half of the screen
```

**What happens:**
1. Chrome activates (with cursor animation)
2. Spotify opens
3. Chrome window snaps to left half
4. Confirmation sent back

**Why it's content-worthy:** Three separate computer actions from one casual message. Shows the agent understands intent, not just commands.

---

## Demo 4: "My AI checks my business MRR without me logging in anywhere"

**Send:**
```
what's my current MRR and how far am I from my $5k goal?
```

**What happens:**
1. Agent loads revenue context from brain/USER.md
2. Returns exact MRR breakdown ($3,322 USD)
3. Calculates gap ($1,678) and pace needed
4. No login, no dashboard — agent already knows

**Why it's content-worthy:** This is the "AI knows your business" moment. Pure credibility. Perfect for business/agency content.

---

## Demo 5: "Watch me text my AI to move my mouse in a perfect arc"

**Send:**
```
move the mouse to the center of the screen slowly
```

**What happens:**
1. Cursor smoothly animates to screen center (1s ease-in-out)
2. Confirmation: "animated to 960,540"

**Then immediately send:**
```
click at 500 300
```

**Why it's content-worthy:** Watching the cursor physically move on its own is the most visceral "AI takes over" moment. Hold your phone so the MacBook screen is in frame. 10/10 hook for short-form content.

---

## Filming Tips

| Tip | Why |
|-----|-----|
| Hold phone so MacBook screen is visible in background | Viewer sees the computer react in real time |
| Film in portrait, phone close to face | Classic "texting" frame that feels natural |
| Don't look at phone after sending — look at the screen | Shows confidence. Also looks better on camera |
| Do Demo 5 (mouse movement) first — it's the most visual | If it works, the rest of the video is credible |
| Talk to camera before, not after | "Watch what happens when I type this..." → send → show result |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| YouTube plays wrong video | Send: `play [exact artist name] on youtube` |
| Chrome not found | Send: `open Chrome` first, wait 3s, then retry |
| Mouse doesn't move | Run: `python3 scripts/mousetool pos` in terminal to verify binary works |
| Screenshot not delivered | Bridge may need restart: `pm2 restart bravo-telegram` |
| "Max turns" error | Send simpler, more direct message. Or send: `just open Chrome` |

## Commands Reference (for ad-hoc demos)

```
# Visual / impressive
screenshot                              → sends you a photo of your screen
move the mouse slowly to the top left   → visible cursor animation
click at [x] [y]                        → visible click

# Productivity
open [app name]                         → launches app
what apps are running?                  → lists active processes
snap [app] to the left                  → window management
set volume to 50%                       → audio control
what's the battery level?               → system info

# Business
what's my MRR?                          → reads brain/USER.md context
what leads need follow-up?              → queries CRM
take a screenshot                       → captures current screen
```

## Obsidian Links
- [[skills/INDEX]] | [[brain/CAPABILITIES]]
- [[skills/browser-automation/SKILL]] | [[../../Marketing-Agent/skills/content-engine/SKILL]]
