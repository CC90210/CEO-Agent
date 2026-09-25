"""Create/inspect the Stripe webhook that feeds the command center's Finances ledger.

    python scripts/integrations/stripe_finance_webhook.py status
    python scripts/integrations/stripe_finance_webhook.py create

The endpoint lives in OASIS's OWN Stripe account. Creating one needs
"Webhook Endpoints write", which the Worker's restricted key deliberately lacks,
so this one-time admin step runs locally with the organization key scoped by
Stripe-Context to acct_1RyM4HHj2zGc7I1J (verified before any write). The org
key never leaves this machine. Stripe shows a signing secret only once, at creation, so `create`
writes it straight into this repo's env store under the Worker manifest's
namespaced source (OASIS_COMMAND_CENTER__STRIPE_FINANCE_WEBHOOK_SECRET) and
prints only a digest; `wrangler_tool.py secrets-push --app
oasis-command-center` then delivers it. `create` refuses when an endpoint for
the URL already exists (its secret is unrecoverable; delete it in the Stripe
dashboard first, deliberately).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.stripe_tool import StripeClient  # noqa: E402  (org key + Stripe-Context, retries)
from lib.env_store import digest, update_env_values  # noqa: E402
from lib.secret_loader import ENV_FILE, load_env  # noqa: E402

URL = "https://oasisai.work/api/webhooks/stripe-finance"
OASIS_ACCOUNT = "acct_1RyM4HHj2zGc7I1J"
STORE_KEY = "OASIS_COMMAND_CENTER__STRIPE_FINANCE_WEBHOOK_SECRET"
EVENTS = (
    "payment_intent.succeeded",
    "charge.succeeded",
    "charge.refunded",
    "invoice.paid",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
)


def _client() -> StripeClient:
    client = StripeClient(load_env(required=["STRIPE_ORG_KEY"])["STRIPE_ORG_KEY"], OASIS_ACCOUNT)
    account = client.get("account").get("id")
    if account != OASIS_ACCOUNT:
        raise SystemExit(f"refusing: the key reaches {account}, not OASIS's {OASIS_ACCOUNT}")
    return client


def _existing(client: StripeClient) -> list[dict]:
    rows = client.get("webhook_endpoints", {"limit": 100}).get("data") or []
    return [r for r in rows if r.get("url") == URL]


def status() -> int:
    rows = _existing(_client())
    if not rows:
        print(f"no endpoint for {URL}")
    for r in rows:
        print(f"{r.get('id')} status={r.get('status')} events={len(r.get('enabled_events') or [])} api={r.get('api_version')}")
    stored = load_env().get(STORE_KEY) or ""
    print(f"{STORE_KEY}: {'set ' + digest(stored) if stored else 'absent'}")
    return 0 if rows and stored else 1


def create() -> int:
    client = _client()
    if _existing(client):
        raise SystemExit(f"an endpoint for {URL} already exists; its secret cannot be read back. Use `status`.")
    form = [("url", URL), ("description", "OASIS command center - Finances ledger")]
    form += [("enabled_events[]", e) for e in EVENTS]
    created = client.post("webhook_endpoints", form)
    secret = created.get("secret") or ""
    if not secret.startswith("whsec_"):
        raise SystemExit(f"endpoint {created.get('id')} created but Stripe returned no signing secret")
    update_env_values(ENV_FILE, {STORE_KEY: secret})
    print(f"created {created.get('id')} for {URL} ({len(EVENTS)} events); stored {STORE_KEY} {digest(secret)}")
    print("next: wrangler_tool.py secrets-push --app oasis-command-center")
    return 0


if __name__ == "__main__":
    verb = sys.argv[1] if len(sys.argv) > 1 else "status"
    raise SystemExit({"status": status, "create": create}.get(verb, status)())
