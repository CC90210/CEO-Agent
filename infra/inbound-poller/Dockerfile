# OASIS AI Agent Command Center — inbound email poller (24/7 VPS)
#
# Runs `email_engine.py check-inbox` every 5 minutes against Gmail IMAP,
# classifies each unread message via inbound_classifier, writes to the
# unified ledger via the record_inbound_from_n8n RPC, and pings
# integrations_health for the Command Center green dot.
#
# Deployed to Hetzner per docs/V6_ARCHITECTURE.md. Replaces the local
# `scheduler.py` cron that only ran when CC's machine was on.

FROM python:3.12-slim

# System deps — minimal
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only what the poller needs
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY scripts/email_engine.py             /app/scripts/email_engine.py
COPY scripts/inbound_classifier.py       /app/scripts/inbound_classifier.py
COPY scripts/integration_health.py       /app/scripts/integration_health.py
COPY scripts/name_utils.py               /app/scripts/name_utils.py

# Tini handles PID 1 + signal forwarding so SIGTERM cleanly stops the poller
ENTRYPOINT ["/usr/bin/tini", "--"]

# The poller loop is run by the host's systemd timer (5-minute interval) OR by
# this container's internal loop. Default: internal loop, hands-free.
CMD ["sh", "-c", "while true; do python /app/scripts/email_engine.py check-inbox || true; sleep 300; done"]
