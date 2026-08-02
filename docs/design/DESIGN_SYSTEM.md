# OASIS Design System — House Style Standard

> Canonical UI standard for all OASIS-family web applications (Bravo dashboards, OASIS Outbound, client deliverables). Established 2026-08-01. New apps default to this house style; client white-label projects override via the theme token layer only — never by forking components.

## 1. Foundations

- **Mode:** Dark-mode first. Light mode is a client-override theme, not a house deliverable.
- **Surface language:** Glassmorphism — frosted panels over a deep base, using backdrop blur + translucent fills + 1px hairline borders. No flat solid cards on the default theme.
- **Motion:** Restrained micro-animations only — 150–250ms ease-out transitions on hover/focus/state change, subtle entrance fades. No parallax, no gratuitous spring physics, no animation that delays access to content.
- **Anti-slop rule:** This system exists to enforce Anti-Slop Matrix row 4 (no generic blue/purple gradient heroes, no centered-everything 3-column icon grids). Every screen should read as intentionally designed.

## 2. Color Tokens (HSL)

Accent identity is per-agent; the base palette is shared.

| Token | Hex | HSL | Use |
|---|---|---|---|
| `--accent-bravo` | `#00f3ff` | `hsl(183, 100%, 50%)` | Cyan — Bravo / tech / engineering surfaces |
| `--accent-atlas` | `#ffb700` | `hsl(43, 100%, 50%)` | Gold — Atlas / finance / revenue surfaces |
| `--accent-maven` | `#ff0055` | `hsl(337, 100%, 50%)` | Crimson — Maven / marketing / content surfaces |
| `--bg-base` | — | `hsl(222, 25%, 6%)` | App background (near-black, cool) |
| `--bg-panel` | — | `hsl(222, 20%, 10% / 0.65)` | Glass panel fill (with `backdrop-filter: blur(16px)`) |
| `--border-hairline` | — | `hsl(222, 15%, 40% / 0.35)` | 1px panel borders |
| `--text-primary` | — | `hsl(210, 20%, 95%)` | Body/headline text |
| `--text-muted` | — | `hsl(215, 12%, 60%)` | Secondary text, captions |
| `--danger` | — | `hsl(0, 75%, 55%)` | Errors, destructive actions |
| `--success` | — | `hsl(150, 65%, 45%)` | Confirmations, healthy status |

Rules:
- Exactly **one accent per view**, chosen by the owning domain (a finance dashboard uses Gold; an ops console uses Cyan). Never blend two agent accents on one screen.
- Accents are for interactive affordances, key metrics, and focus rings — not large fills. Large accent washes read as slop.

## 3. Typography

- **Headings / display:** Outfit (geometric, confident). Weights 500–700.
- **Body / UI:** Inter. Weights 400–600.
- **Scale:** 12 / 14 / 16 / 20 / 24 / 32 / 48 — no arbitrary sizes between steps.
- Real hierarchy: a page has one 32–48px headline, not five bold 20px lines competing.

## 4. Components & Layout

- Panels: `border-radius: 12–16px`, hairline border, glass fill, inner padding 20–24px.
- Buttons: solid accent for primary, ghost (hairline border, transparent fill) for secondary; 8px radius; 150ms hover transition.
- Inputs: glass fill matching panels, accent focus ring (2px, 40% opacity accent).
- Layout: asymmetric, content-led grids. Status/metric clusters align left; never default to centering everything.

## 5. White-Label Override (Client Themes)

Theming is a token swap, never a component fork:

1. All color/spacing/radius values referenced **only** via CSS custom properties (`var(--accent-primary)`, `var(--bg-base)`, …).
2. The house style ships as the `:root` default theme.
3. A client theme is a single override sheet applied via `data-theme="client-slug"` on `<html>`, redefining the tokens (including mapping `--accent-primary` to any of the three agent accents or a client hue).
4. If a client request can't be expressed as token overrides, escalate to Bravo before adding component-level branches — that request is a design-system gap, not a one-off hack.

## 6. Adoption

- New apps (anything under `apps/`, OASIS Outbound surfaces, client sites): scaffold with these tokens from day one.
- Existing apps: migrate opportunistically when touched — no big-bang re-skins without CC's sign-off.
