---
tags: [scripts]
last_updated: 2026-07-20
---

# Archived Scripts

Files here are retained for provenance and are not active CLI capabilities or chat-bridge
tools. New code must not import them. Each archived script needs a maintained successor or a
documented historical outcome.

| Archived script | Reason | Maintained successor |
|---|---|---|
| `history_secret_scan.py` | Its sanitized history and secret-filename checks were merged into the canonical scanner. | `scripts/scan_secrets.py --history` |
| `harness_plugin.py` | Static chassis data duplicated and drifted from the generated capability graph and genome. | `scripts/capability_query.py`, `scripts/agent_genome.py`, and `brain/ORCHESTRATION.md` |

## Obsidian Links
- [[brain/CAPABILITIES]]
- [[brain/QUICK_REFERENCE]]
