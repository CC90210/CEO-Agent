# Evidence Capture

Use this when proving a browser action worked.

## Default Evidence

- `page_info()` for URL/title/viewport state.
- `screenshot()` after every meaningful visible action.
- Safe exported files only when the site provides an export and the data is non-sensitive or approved.

## Evidence Folder

Use `browser/evidence/` for safe local artifacts.

Do not commit private screenshots, customer data, account data, cookies, tokens, or anything that would be unsafe in Git.

## Pattern

```powershell
@'
new_tab("https://example.com")
wait_for_load()
print(page_info())
print(screenshot("browser/evidence/example-home.png"))
'@ | & (Get-Command browser-harness).Source
```

## Verify Before Acting

After a click, type, upload, scroll, or navigation:

1. Take a screenshot.
2. Check page state.
3. Confirm no modal, auth wall, validation error, or wrong account appeared.
4. Continue only if state matches the task.

## Related
- [[browser/README]]
- [[browser/interaction-skills/INDEX]]
- [[skills/browser-automation/SKILL]]


## Related (graph)

- [[browser/interaction-skills/INDEX]]
- [[browser/interaction-skills/approval-gates]]
- [[browser/interaction-skills/connection]]
- [[browser/interaction-skills/domain-skill-lifecycle]]
