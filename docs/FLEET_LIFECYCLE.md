# Fleet process lifecycle

Windows daemon supervision is owned by `scripts/ops/fleet_watchdog.py`. PM2 is
retired on this machine and must not be used as a second supervisor. The
committed launch commands remain in `ecosystem.config.js`; the committed
lifecycle decision and retention reason for every daemon live in
`config/fleet_lifecycle.json`.

## Current posture

Every currently deployed daemon is intentionally `always_on`. None was disabled
to make the process list look smaller:

- `bravo-scheduler`, `bravo-ig-dm`, and the dashboard email pair keep inbound,
  sales, follow-up, and approved communication moving.
- `bravo-telegram`, `atlas-telegram`, and `maven-telegram` are CC's mobile
  command and alert channels.
- `bravo-coord` and `event-router` carry CC/Adon/APEX coordination and events.
- `claude-bridge` and `claude-bridge-ping` keep the Agent Command Center's
  local runner reachable and current.
- `breeze-live-watch` keeps live project state flowing into the harness.

The full per-process reason and owner are machine-readable in the lifecycle
config and visible with:

```powershell
python scripts/ops/fleet_watchdog.py lifecycle
python scripts/ops/fleet_watchdog.py status --json
```

An app present in the launch manifest but absent from the lifecycle config is
`unclassified` and fails closed: the watchdog reports it as unrunnable and will
not silently turn a new background worker into a permanent service.

## Independent roots, not raw PID count

On Windows, a virtual-environment launcher and its real Python interpreter often
appear as two matching PIDs in one parent/child tree. That is one daemon. Status
therefore publishes `pids`, `root_pids`, and `root_count`. More than one
independent root is state `duplicate`, which is unhealthy in the harness, health
digest, parity check, cron check, and Agent Command Center panel.

An `up` pass reconciles an enabled duplicate by provenance-checking every match,
stopping all independent trees, and starting exactly one. `--dry-run` reports
that plan without stopping anything.

## On-demand workers

Future burst workers that do not need continuous availability must be committed
with `"mode": "on_demand"`. They run only while a bounded operator lease is
active:

```powershell
python scripts/ops/fleet_watchdog.py lease <name> --minutes 30 --reason "approved export"
python scripts/ops/fleet_watchdog.py up --only <name>
python scripts/ops/fleet_watchdog.py release-lease <name>
```

The maximum lease is 24 hours. A normal `up` pass starts a leased worker and
stops an on-demand worker whose lease expired. This mechanism applies only to
processes explicitly classified `on_demand`; it cannot stop the current
always-on Telegram, revenue, or Agent Command Center services.

`~/.pm2/dump.pm2` is optional compatibility input for old entries. A missing
snapshot is silent. A present but corrupt snapshot remains a diagnostic because
it may contain evidence of a legacy process that still needs migration.
