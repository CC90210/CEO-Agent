# Supabase

## Site

- URL patterns: `https://supabase.com/dashboard/project/<project-ref>`
- Auth assumptions: CC may be logged in locally. Service role keys and SQL editor are high risk.
- Agent owner: Bravo/Codex
- Last verified: 2026-04-22

## Use Cases

- Read-only: inspect tables, logs, project status, edge functions, auth settings.
- Draft-only: prepare SQL locally.
- Approval required: run SQL, alter RLS, rotate keys, delete data, change auth or storage policies.

## Preferred Tools

- Use `python scripts/supabase_tool.py select <table> --project bravo` for reads.
- Use `python scripts/apply_migration.py database/<migration>.sql` for approved migrations.
- Browser Harness is for dashboard confirmation and UI-only settings.

## Waits And Traps

- Dashboard panels can lazy-load.
- SQL editor state can persist old text. Verify editor content before any run.
- Multiple projects can look similar. Confirm project ref before acting.

## Approval Gates

Approval required before SQL execution, key changes, RLS changes, auth provider changes, storage policy changes, deletion, imports, exports, or project settings changes.

## Related
- [[browser/README]]
- [[browser/SAFETY]]
- [[skills/browser-harness/SKILL]]
