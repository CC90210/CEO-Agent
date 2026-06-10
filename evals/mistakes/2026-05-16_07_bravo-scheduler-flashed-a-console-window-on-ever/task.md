# Regression: bravo-scheduler Flashed a Console Window on Every PM2 Restart (2026-05-16)

## What went wrong
`ecosystem.config.js` configured `bravo-scheduler` with `interpreter: PYTHON` (`.venv\Scripts\python.exe` — console subsystem). PM2's `windowsHide: true` was set but, per the file's own warning, unreliable across PM2 versions on Windows. Visible symptom: a `python.exe` console window briefly flashed onto CC's screen with the venv-Python path as the title — frequently enough that CC explicitly flagged the noise as "annoying" and "stopping my work."

## The behavior that must NOT recur
1. Fixed: `ecosystem.config.js` line 110 changed from `interpreter: PYTHON` to `interpreter: PYTHONW` with a comment marking the 2026-05-16 fix. Reloaded via `pm2 delete bravo-scheduler && pm2 start ecosystem.config.js --only bravo-scheduler && pm2 save`. Verified live: scheduler now runs as `pythonw.exe` (PID 21240 + venv-relauncher 15720) and self-reports `Python: ...\pythonw.exe` in its banner.
2. **Rule going forward:** *any* new PM2 entry in `ecosystem.config.js` that runs a Python daemon on Windows MUST use `PYTHONW`, not `PYTHON`. Reviewers of this file should grep `interpreter: PYTHON\b` and reject any match that isn't deliberate (and document why). The exit-code evidence proves this isn't just cosmetic — console interpreters get reaped by phantom Ctrl-C in PM2's process tree.
3. *
