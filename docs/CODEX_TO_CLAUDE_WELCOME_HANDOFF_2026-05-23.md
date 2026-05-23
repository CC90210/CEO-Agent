# Codex To Claude Handoff - OASIS Welcome Scroll Assembly

Date: 2026-05-23  
Owner: Claude Code / Bravo next pass  
Dashboard repo: `C:\Users\User\APPS\oasis-command-center`  
Relevant route: `/welcome`

## Why This Exists

CC reported that the welcome page is closer visually, but still not fully functional:

- the scroll assembly did not feel tied to user scroll
- one screenshot showed the reasoning core docking, but deeper scroll showed a blank background
- the Bridge Tools layer did not read as attached physical tooling
- Claude Code needs a durable handoff so it stays in the loop without CC repeating the same feedback

## Current Welcome Baseline

Current dashboard main contains the newer 11-phase agent assembly plus Codex's
arm-tool polish:

- `a176645 feat(welcome): plain-English manifest + head-anchored modules + density cleanup`
- `bfffdad feat(welcome): forearm tool gauntlets + audit-fix OpenRouter model IDs`
- `6021a8f chore(welcome): remove temporary verification artifacts`
- `7358d12 fix(welcome): restore full 11-phase agent assembly`
- composition root: `components/landing/AgentAssemblyScrollScene.tsx`
- figure: `components/landing/agent-assembly/AgentFigure.tsx`
- modules: `components/landing/agent-assembly/modules/*`

The page now maps real OASIS/Bravo subsystems into the visual assembly instead of generic decoration.

## Intelligence Layer Map

These are the 11 layers shown in the manifest HUD and assembled onto the agent:

1. `Reasoning Core` - multi-model brain with Claude, GPT, and backup providers
2. `State Pulse` - operational heartbeat tracking actions and events
3. `Memory Spine` - hybrid keyword and semantic recall across the knowledge base
4. `Browser Optics` - browser/search capability represented as the visor
5. `Bridge Tools` - local bridge actions and automation scripts
6. `Guard Shield` - secret, execution, and state guardrails
7. `Output Channels` - Telegram, email, dashboard feed outputs
8. `Security Mesh` - credential and access audit envelope
9. `Business Layer` - brand, voice, audience, goals
10. `Command Centre` - Pulse, crons, funnel, pipeline control bar
11. `Dashboard Metrics` - revenue, pipeline health, conversion analytics

## Codex Changes In This Pass

Dashboard files touched:

- `components/landing/agent-assembly/AgentFigure.tsx`
- `components/landing/agent-assembly/modules/ToolLimbs.tsx`
- `components/landing/agent-assembly/modules/DashboardMetrics.tsx`
- `components/landing/agent-assembly/modules/BusinessLayer.tsx`
- `components/landing/AgentAssemblyScrollScene.tsx`

What changed:

- Added `leftArmChildren` and `rightArmChildren` slots to `AgentFigure`.
- Moved Bridge Tools out of the body layer and into the animated arm groups.
- Rebuilt Bridge Tools as arm-mounted gauntlets with physical tool glyphs:
  hammer, screwdriver, laptop, wrench, and search/scope.
- Shifted `DashboardMetrics` further left so it clears the BRAND tag.
- Pushed Business Layer tags outward to reduce collision with the figure and arm tools.
- Confirmed `/welcome` root no longer uses `overflow-hidden`; fixed backgrounds are behind the scroll scene.
- Removed accidentally tracked `tmp/` verification screenshots/spec from the dashboard repo and added
  `tmp/` to `.gitignore` plus `tmp/**` to `tsconfig.json` excludes.
- Restored the 11-phase scroll sequence after the gauntlet pass regressed the scene to 8 phases.
  Business Layer, Command Centre, and Dashboard Metrics now install as phases 9-11 again.

## User Feedback To Preserve

CC's stated direction:

- The agent must stay with the user as they scroll.
- It should feel like a physical AI is being assembled, not like UI bubbles floating around.
- Browser/search should become a physical part of the body, such as optics/visor.
- Tools should attach to arms and feel like hammers, screwdrivers, computers, and operational tools.
- At the bottom, the entry choices remain:
  - Build your own agent
  - Sign in automatically
  - Download the desktop app

## Known Risk

The full-page screenshot of a sticky scroll scene will always show a long blank region because the pinned viewport is only captured once at the current scroll position. That is not the same as actual scrolling.

The real verification must use an interactive browser and inspect multiple scroll positions, not only `--full-page` screenshots.

If the user still sees blank space while manually scrolling, inspect:

- `app/welcome/page.tsx` for any ancestor with `overflow-hidden`, `overflow-auto`, or `overflow-scroll`
- `components/landing/AgentAssemblyScrollScene.tsx` sticky wrapper:
  `min-[641px]:sticky min-[641px]:top-0 min-[641px]:h-screen`
- z-index/background layering around the sticky scene
- reduced-motion or compact breakpoint forcing static behavior

## Verification Completed

Ran in `C:\Users\User\APPS\oasis-command-center`:

```bash
npx tsc --noEmit
npm run lint
```

Results:

- TypeScript clean.
- Lint clean except the pre-existing `components/agents/AgentChat.tsx:275` hook dependency warning.
- Vercel production deployment for `7358d12` is Ready:
  `https://agent-dashboard-r1zz4az4f-cc90210.vercel.app`
- Production alias probe: `https://agent-dashboard-cc90210.vercel.app/welcome` returned HTTP 200.
- Related route probes returned HTTP 200:
  `/command-centre-explained`, `/configure`, `/download`.
- Anonymous/headless Playwright production pass at 1440x900 checked ten real scroll stops.
  Evidence: scrollHeight 10680, maxScroll 9780, manifestCount 11, no console errors,
  Bridge Tools present, Dashboard Metrics present. Active rows advanced through
  State Pulse, Memory Spine, Browser Optics, Guard Shield, Output Channels,
  Business Layer, Command Centre, and Dashboard Metrics. The final entry choices
  appeared at the bottom.

Important note: `https://agent-dashboard.vercel.app/welcome` returned 404; the live production alias
for this project is `https://agent-dashboard-cc90210.vercel.app`.

## Desktop Workstream Reminder

The OASIS macOS desktop production push is still separate and not completed by this welcome pass.

Claude/Codex should continue from the larger desktop checklist:

- Developer ID signing and notarization
- hardened runtime entitlement audit
- auto-updater
- keychain-backed API key storage
- bridge sidecar reliability
- macOS-native menu/chrome
- first-launch onboarding
- universal binary verification
- DMG/ZIP distribution

Apple Developer Program status remains unknown and may block production notarization.
