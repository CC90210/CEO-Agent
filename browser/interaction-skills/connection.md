---
tags: [browser, automation]
last_updated: 2026-05-21
---

# Connection And Attach

Use this when Browser Harness is installed but not attached to Chrome/Edge.

## Diagnose

```powershell
python scripts/browser/browser_harness_doctor.py
```

If the executable exists but daemon is not alive, run:

```powershell
& (Get-Command browser-harness).Source --setup
```

## Windows Notes

This machine uses a local Windows compatibility patch in `C:\Users\User\APPS\browser-harness`.

- If `socket.AF_UNIX` is unavailable, the harness uses localhost TCP.
- The stable checkout is editable, so local patches affect the installed executable immediately.
- Direct command invocation can be inconsistent on Windows; use `& (Get-Command browser-harness).Source` when in doubt.

## Chrome Approval

Chrome/Edge may need one-time profile approval:

1. Choose the normal profile if the profile picker appears.
2. In `chrome://inspect/#remote-debugging`, enable the remote debugging/discovery option if shown.
3. Click `Allow` if Chrome prompts.
4. Re-run `python scripts/browser/browser_harness_doctor.py`.

## Smoke Test

```powershell
@'
new_tab("https://github.com/browser-use/browser-harness")
wait_for_load()
print(page_info())
'@ | & (Get-Command browser-harness).Source
```

## Related
- [[browser/README]]
- [[browser/interaction-skills/INDEX]]
- [[skills/browser-automation/SKILL]]


## Related (graph)

- [[browser/interaction-skills/INDEX]]
- [[browser/interaction-skills/approval-gates]]
- [[browser/interaction-skills/domain-skill-lifecycle]]
- [[browser/interaction-skills/evidence]]
