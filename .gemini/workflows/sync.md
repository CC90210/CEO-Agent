---
description: End-of-session sync — update state, tasks, and session log
---

# Sync Command

## What This Command Does
Performs the mandatory end-of-session memory sync: updates STATE.md, ACTIVE_TASKS.md, SESSION_LOG.md, and captures any learnings.

## When to Use
Use `/sync` before ending any session — this is **mandatory** per session protocol.

## How It Works / Steps

1. Review what was accomplished this session.

2. Update `brain/STATE.md`:
   - Update the "Last Heartbeat" section with today's date, agent name, and summary of work done
   - Update "Known Issues" if any were resolved or new ones discovered
   - Update "Operational Status" if energy/confidence/focus changed

3. Update `memory/ACTIVE_TASKS.md`:
   - Mark completed tasks as done
   - Add any new tasks discovered during the session

4. Append to `memory/SESSION_LOG.md`:
   ```
   ## [date] — Session via [agent]
   - [bullet list of what was done]
   - [any issues encountered]
   - [next steps]
   ```

5. If any mistakes were made, log to `memory/MISTAKES.md` with root cause and prevention.

6. If new patterns discovered, log to `memory/PATTERNS.md` (tag `[PROBATIONARY]`).

7. If any tasks failed, add a reflexion entry to `memory/SELF_REFLECTIONS.md`.

8. Say: "Memory synced. [X] files updated, [Y] tasks completed."
