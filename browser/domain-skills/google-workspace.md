# Google Workspace

## Site

- URL patterns: Gmail, Drive, Calendar, Docs, Sheets, Slides, Admin console
- Auth assumptions: CC may be logged in locally. Outbound and sharing actions are approval-gated.
- Agent owner: Bravo
- Last verified: 2026-04-22

## Use Cases

- Read-only: inspect docs, drive files, calendar, inbox, labels, admin settings.
- Draft-only: draft documents or emails locally.
- Approval required: send, share, delete, invite, change admin/user/security settings.

## Preferred Tools

- Use `python scripts/google_tool.py` for Gmail, Drive, Docs, Sheets, Slides, Calendar, and Tasks.
- Browser Harness is for UI-only tasks and visual verification.

## Traps

- Multiple Google accounts can be logged in. Confirm account/avatar context.
- Sharing dialogs can expose files externally.
- Gmail send is outbound communication and must respect Bravo's send rules.

## Approval Gates

Approval required before sending, sharing externally, deleting files, changing admin settings, changing security settings, or inviting users.
