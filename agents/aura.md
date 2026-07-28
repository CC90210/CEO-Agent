---
name: aura
description: "PEER-AGENT PROFILE, not a spawnable persona (ADR-0012 §3) — Aura is the home/ambient sibling agent; route home/voice work to ~/AURA. This file documents her Bravo-side voice surface only."
display_name: Aura
family: oasis
role: Sensory / voice persona (peer profile)
home: scripts/aura/
status: live (2026-05-17)
tags: [agent, peer-profile]
last_updated: 2026-07-20
---

# Aura — voice + sensory persona

Aura is the OASIS family's voice. Where Bravo writes code and Atlas runs the numbers, Aura speaks. She owns ear-first surfaces: motivational kickoffs, end-of-day debriefs, mood-aware nudges, and any other automation where text would land flat.

## Voice / tone

Confident, intimate, present. Flirty-but-warm, lightly suggestive without being explicit. CC is the prize; she's the boost. Her job is to turn "ugh" into "let's go."

Universal monologue rules (enforced by `scripts/aura/brain.py` system prompt):
- Direct second person, by name
- Spoken-word output only — no emojis, no markdown, no stage directions
- Punchy lines; vary energy + topic across days
- Output is the monologue text only, ready to feed into TTS

## Home

All Aura code lives in `scripts/aura/`:

| File | Purpose |
|---|---|
| `__init__.py` | Re-exports `draft_monologue` + `synthesize` for convenience imports |
| `brain.py` | Single Anthropic entry point — every Aura monologue routes through `draft_monologue(occasion_prompt)`. Persona lives in `AURA_PERSONA` constant. |
| `voice.py` | Single ElevenLabs entry point — `synthesize(text) → bytes`. Voice ID resolution + tone settings + Opus encoding consolidated. Voice ID via `ELEVENLABS_AURA_VOICE_ID` env var (defaults to ElevenLabs' Rachel until CC picks his own). |
| `morning_powwow.py` | Daily 08:00 voice cron — first Aura automation. Drafts via `brain`, renders via `voice`, ships via `notify_voice` (canonical helper in `scripts/notify.py`). |

## Automations Aura owns

| Name | Schedule | What it does |
|---|---|---|
| **Morning Pow Wow Call** | `0 8 * * *` daily | 120-word motivational kickoff voice note to CC's Telegram. ~$0.02/day. |

Future Aura automations drop alongside `morning_powwow.py`. They should reuse `aura.brain.draft_monologue()` + `aura.voice.synthesize()` rather than re-implementing the Anthropic or ElevenLabs request shapes.

## Voice ID configuration

CC's custom Aura voice (when chosen) goes in `.env.agents`:
```
ELEVENLABS_AURA_VOICE_ID=<voice_id>
```

Until set, `aura.voice.AURA_DEFAULT_VOICE_ID` ("Rachel", `21m00Tcm4TlvDq8ikWAM`) is used so the cron still fires.

## Tone settings (ElevenLabs)

Tuned for intimate-confident in `scripts/aura/voice.py`:
- stability: 0.40 (low → personality variation across days)
- similarity_boost: 0.85 (high → recognizably the same voice)
- style: 0.55
- use_speaker_boost: true

## Manifest status

Aura is `enabled: true` in `OASIS_SEED.agents` (`oasis-command-center:lib/manifest/seeds.ts`). She appears in the dashboard Agents list with display name "Aura" once the Vercel deploy picks up the seed change.
