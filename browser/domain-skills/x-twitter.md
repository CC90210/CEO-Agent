# X / Twitter

## Site

- URL patterns: `https://x.com/`, `https://twitter.com/`
- Auth assumptions: CC or Maven may be logged in locally.
- Agent owner: Maven
- Last verified: 2026-04-22

## Use Cases

- Read-only: inspect posts, notifications, analytics, profiles.
- Draft-only: prepare post/reply text locally.
- Approval required: post, reply, DM, follow, unfollow, like, repost, delete.

## Traps

- Compose state can persist across navigation.
- Rate limits and automation flags are common.
- The UI changes often; verify with screenshots.

## Approval Gates

Approval required before any public or private account action.
