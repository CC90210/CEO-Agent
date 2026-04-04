> **ROUTING:** GitHub: CC90210/nostalgic-requests | Supabase: jqybbrtzpvmefgzzdagz | Deploy: Vercel

# Nostalgic Requests — Performer Song Request Platform

## Project Overview

Nostalgic Requests is a premium song request and payment platform for live music performers (DJs, live musicians, karaoke hosts). Audience members scan a QR code, request songs, pay instantly, and performers manage a real-time queue.

## How It Works

1. Performer creates an event → Gets unique QR code
2. Audience scans QR → Beautiful mobile portal opens
3. Audience searches any song (iTunes/Spotify integration) → Selects request tier
4. Pays via Apple Pay / Google Pay → Instant checkout via Stripe
5. Performer sees request in real-time dashboard → Manages queue live
6. SMS notification → "Your song is up next!" sent to requester
7. Lead captured → Phone + email stored for future marketing

## Revenue Model

- **Platform fee:** 5% of each transaction (Nostalgic Requests' cut)
- **Stripe fees:** 2.9% + $0.30 (charged separately by Stripe)
- **Performers set their own prices** (we provide suggested defaults)

### Default Pricing Tiers

| Package | Suggested Price | Description |
|---------|----------------|-------------|
| Single | $5 | One song request |
| Double Up | $8 | Two songs (save $2) |
| Party Pack | $12 | Three songs (save $3) |
| Priority Play | +$10 | Skip the line |
| Shoutout | +$5 | Personal dedication |
| Guaranteed Next | +$20 | Play immediately next |

## Tech Stack

- **Frontend:** Next.js, TypeScript, Tailwind CSS
- **Backend:** Supabase (auth, database, realtime subscriptions)
- **Payments:** Stripe Connect (onboarding performers as connected accounts)
- **SMS:** Twilio (notifications to requesters)
- **Music Search:** iTunes Search API / Spotify API
- **Hosting:** Vercel
- **QR Generation:** Dynamic QR codes per event

## Design Direction

- Dark theme with purple/pink gradients
- Premium, nightlife aesthetic
- Mobile-first (audience uses phones at venues)
- Fast, minimal-tap checkout flow
- Brand tagline: "Get Paid to Play" / "Your Stage. Your Rules. Your Revenue."

## Expansion Plans

- Photographers (photo request + priority booking at events)
- Sketch artists / caricaturists
- Bartenders / mixologists (custom cocktail requests)
- Any live event professional

## Key Commands

```
/deploy                    → Deploy to Vercel
/add-performer-feature     → Add a new feature for performer dashboard
/test-payment              → Test Stripe Connect payment flow
```

## Obsidian Links
- [[APPS_CONTEXT/INDEX]] | [[brain/APP_REGISTRY]]
