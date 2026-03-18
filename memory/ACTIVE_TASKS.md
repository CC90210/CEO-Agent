# ACTIVE TASKS
> Read this FIRST at the start of every session. Priority is marked with [P0] Critical, [P1] High, [P2] Medium.

## Target: $1,000 Net MRR by March 31, 2026 (GOAL EXCEEDED)

To reach this goal, we need **3 new clients** for OASIS (assuming ~$300-$500/mo retainer or high-ticket setup fee).

### Current Progress
- **Current Net:** ~$2,691 ($191 base + $2,500 Bennett Community Manager role) + $3,000 upfront cash collected.
- **Gap to Goal:** $0 (+$1,691 surplus)
- **Pipeline:** 50+ leads researched, 20+ emails sent, 2 warm leads (Cedarwood, Vortex)
- **Next Milestone:** Start building technical assets for Week 2 and 4 for Bennett's accelerator.

## This Week (March 17) — TIKTIK IP Camera Integration + Accelerator Delivery

### Monday (March 17) — TIKTIK IP Camera Integration COMPLETE
- [x] [P0] **IP Camera Management System** — Built full database schema with cameras table + RLS policies. Multi-tenant support (cameras scoped to centers).
- [x] [P0] **Camera CRUD API Routes** — `/api/cameras` endpoint with GET/POST/PUT/DELETE, full authentication, user's center scoping, secure credential handling.
- [x] [P0] **Kiosk Stream Config Endpoint** — `/api/cameras/stream-config` service-role GET that returns only enabled camera stream names (no credentials exposed to frontend).
- [x] [P0] **go2rtc Config Generator Endpoint** — `/api/cameras/go2rtc-config` service-role GET protected by GO2RTC_API_KEY that generates YAML config with full RTSP source URLs.
- [x] [P0] **CameraFeed Component** — WebRTC connection to go2rtc proxy, canvas bounding boxes, face recognition overlay (integrates with Smart Mode face-api.js).
- [x] [P0] **CameraTab in Admin Dashboard** — 5th admin tab for managing cameras. Configure RTSP URLs, location, stream quality.
- [x] [P0] **Docker Infrastructure** — Created docker-compose.yml + go2rtc.yaml for RTSP→WebRTC proxy deployment.
- [x] [P0] **Deploy to Vercel** — Pushed commit 4ed1e4a to origin/master. Live at https://tiktik-psi.vercel.app
- [ ] [P1] **WAITING: Midas Network Spec** — Need (1) Lorex NVR IP address, (2) Admin credentials, (3) Camera channel numbers. Then deploy go2rtc on his network.
- [ ] [P1] **Verify Camera Feed in Smart Mode** — Once go2rtc running, test camera stream in Auto Clock-In overlay. Confirm face recognition works with IP camera feed (not just browser webcam).

## Next Week (March 17+) — Execution

- [ ] [P0] **Confirm Camera System with Midas** — Call/message Midas to get exact Lorex NVR specs. Provide him docker setup instructions.
- [ ] [P0] **Deploy go2rtc on Midas Network** — Once he provides IP/creds, run `docker-compose up` on his network. Test RTSP→WebRTC proxy.
- [ ] [P0] **Test IP Camera in Smart Mode** — Verify camera feed displays in Clock-In screen, face recognition works with camera (not webcam).
- [ ] [P0] **Build next technical asset for Bennett Accelerator** — Clarify which week 2/4 asset is needed.
- [ ] [P1] **Build automated "Touch 2" follow-up workflow in n8n** — Follow-up sequence for warm leads.
- [ ] [P1] **Build "High-Ticket Automation Template" for rapid delivery** — Template for future clients.

## Infrastructure (Ongoing)

- [ ] [P1] **Create reusable Google Meet link** — Store in .env.agents.
- [ ] [P2] **Add ELEVENLABS_API_KEY to .env.agents** — CC to provide.
- [ ] [P2] **Reconfigure Stripe MCP** — Use cmd wrapper.
- [ ] [P2] **Reconfigure Supabase MCP** — Use npx with --access-token.
- [ ] [P2] **LinkedIn Chrome Auth** — Needed for automated outreach engine.

## Blocked / Waiting

| Task | Blocked By | Since | Notes |
|------|-----------|-------|-------|
| TIKTIK Camera Feed Deployment | Midas camera system spec | 2026-03-17 | Built system, waiting for NVR IP/credentials/channels |
| TIKTIK Smart Mode Camera Testing | go2rtc Docker deployment | 2026-03-17 | Once running on Midas network, test face recognition with IP camera |
| PropFlow development | Monitoring — pivoting dev hours to OASIS | 2026-03-01 | — |
| LinkedIn automation | Need local Chrome auth hookup | 2026-03-04 | — |
| On The Bay Painting software | Client not ready to switch — revisit in weeks/months | 2026-03-16 | — |

*Last updated: 2026-03-17*
