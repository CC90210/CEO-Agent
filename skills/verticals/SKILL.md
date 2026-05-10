---
name: verticals
description: Namespace for vertical-specific playbooks (agency, coaching, creator, ecommerce, local-service, saas). Load the matching sub-skill when CC onboards a client in a given vertical — each one will ship lead-gen, pricing, and delivery SOPs tailored to that vertical's economics.
triggers: ["verticals", "use verticals", "run verticals", "namespace for vertical-specific playbooks (agency"]
---

# Verticals — Playbook Namespace

> **This is a namespace, not a skill.** Each subdirectory (`agency/`, `saas/`, `local-service/`, etc.) will house a vertical-specific playbook once it's built.
>
> Triggered by: [[brain/PRODUCT_VERTICALS]] mapping a lead or client to one of these verticals.
> Feeds into: [[brain/PRODUCT_ARCHITECTURE]] "Business in a Box" productization.

## Status

Scaffolding only. No playbooks written yet. Each vertical will get its own `SKILL.md` with:

- **Ideal customer profile** — who buys, who ghosts
- **Pricing anchor** — typical deal size, upsell paths, retainer vs project
- **Top 3 pain points** — things Bravo/Maven should lead every conversation with
- **Lead-gen channels** — where they actually are (vs where founders assume they are)
- **Delivery SOP** — first 30 days that keep churn < 10%

## Verticals in scope

- `agency/` — Agencies selling AI automation, content ops, fractional CMO
- `coaching/` — Coaches, course-creators, transformation businesses
- `creator/` — Personal brands monetizing content, community, products
- `ecommerce/` — Shopify + DTC brands (connects to `APPS/shopify-ad-engine`)
- `local-service/` — HVAC, landscaping, home services, trades (connects to Gritly)
- `saas/` — Bootstrapped and seed SaaS founders

## Build order

Prioritize by CC's active client pipeline. When CC signs the first client in a vertical, that vertical's playbook gets built first.

## 🔗 Obsidian Links
- [[brain/PRODUCT_VERTICALS]] — product/vertical research
- [[brain/PRODUCT_ARCHITECTURE]] — "Business in a Box" productization plan
- [[skills/INDEX]] — full skills registry
