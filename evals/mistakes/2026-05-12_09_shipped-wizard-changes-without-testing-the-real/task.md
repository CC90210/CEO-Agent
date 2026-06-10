# Regression: Shipped Wizard Changes Without Testing the Real `curl | bash` Mac Path (2026-05-12)

## What went wrong
I declared the SunBiz experience layer shipped without verifying the actual Mac bootstrap path the client uses: `curl -fsSL https://raw.githubusercontent.com/CC90210/CEO-Agent/main/install.sh | bash`. The installer succeeded, auto-updated the wizard, then the first interactive prompt dropped back to the shell because the wizard inherited a piped stdin and read EOF. That made the golden-path onboarding unusable even though the dashboard and docs work had passed.

## The behavior that must NOT recur
1. Any change to onboarding, wizard copy, or setup flow must be verified through the real bootstrap entrypoint, not just `python bravo_cli/main.py setup`.
2. When a launcher can be invoked through a pipe, explicitly test TTY handoff and self-restart behavior before shipping.
3. Treat installer/bootstrap flows as product-critical surfaces equal to the dashboard: builds are not enough.
