"""
Stripe SDK Integration — Universal Multi-Account Agent Tool
Uses the Stripe Organization API key with Stripe-Context header
for seamless access to all 3 brand accounts with ONE key.
All credentials loaded from .env.agents (never hardcoded).

Usage (from any agent via terminal):
  python scripts/stripe_tool.py list-accounts
  python scripts/stripe_tool.py balance [--account oasis]
  python scripts/stripe_tool.py customers [--limit 10] [--account propflow]
  python scripts/stripe_tool.py products [--limit 10]
  python scripts/stripe_tool.py prices [--product prod_xxx]
  python scripts/stripe_tool.py invoices [--customer cus_xxx] [--status paid|open|draft]
  python scripts/stripe_tool.py subscriptions [--customer cus_xxx] [--status active|canceled]
  python scripts/stripe_tool.py payment-links [--limit 10]
  python scripts/stripe_tool.py create-payment-link --price price_xxx [--quantity 1]
  python scripts/stripe_tool.py create-customer --email x@y.com --name "Name"
  python scripts/stripe_tool.py create-invoice --customer cus_xxx
  python scripts/stripe_tool.py charges [--limit 10]
  python scripts/stripe_tool.py refund <charge_id> [--amount 500]
  python scripts/stripe_tool.py events [--type payment_intent.succeeded] [--limit 10]
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)


STRIPE_API = "https://api.stripe.com/v1"
STRIPE_VERSION = "2025-01-27.acacia"


def load_env():
    """Load .env.agents from project root."""
    env_path = Path(__file__).resolve().parent.parent / ".env.agents"
    if not env_path.exists():
        print(f"ERROR: {env_path} not found", file=sys.stderr)
        sys.exit(1)
    
    env_vars = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


# Multi-account configuration — one org key, per-account context IDs
ACCOUNTS = {
    "oasis": {
        "acct_id_key": "STRIPE_OASIS_ACCT_ID",
        "default_id": "acct_1RyM4HHj2zGc7I1J",
        "description": "OASIS AI Solutions"
    },
    "propflow": {
        "acct_id_key": "STRIPE_PROPFLOW_ACCT_ID",
        "default_id": None,
        "description": "PropFlow"
    },
    "nostalgic": {
        "acct_id_key": "STRIPE_NOSTALGIC_ACCT_ID",
        "default_id": None,
        "description": "Nostalgic Requests"
    }
}


class StripeClient:
    """Lightweight Stripe API client using the org key + Stripe-Context header."""
    
    def __init__(self, org_key, account_id):
        self.headers = {
            "Authorization": f"Bearer {org_key}",
            "Stripe-Version": STRIPE_VERSION,
            "Stripe-Context": account_id,
        }
        self.account_id = account_id
    
    def get(self, endpoint, params=None):
        """GET request to Stripe API."""
        resp = requests.get(f"{STRIPE_API}/{endpoint}", headers=self.headers, params=params or {}, timeout=15)
        if resp.status_code != 200:
            error = resp.json().get("error", {})
            raise Exception(f"Stripe API error ({resp.status_code}): {error.get('message', resp.text[:300])}")
        return resp.json()
    
    def post(self, endpoint, data=None):
        """POST request to Stripe API."""
        resp = requests.post(f"{STRIPE_API}/{endpoint}", headers=self.headers, data=data or {}, timeout=15)
        if resp.status_code not in (200, 201):
            error = resp.json().get("error", {})
            raise Exception(f"Stripe API error ({resp.status_code}): {error.get('message', resp.text[:300])}")
        return resp.json()


def get_client(env_vars, account="oasis"):
    """Create a StripeClient for the specified account."""
    org_key = env_vars.get("STRIPE_ORG_KEY")
    if not org_key:
        print("ERROR: STRIPE_ORG_KEY not found in .env.agents", file=sys.stderr)
        sys.exit(1)
    
    config = ACCOUNTS.get(account)
    if not config:
        print(f"ERROR: Unknown account '{account}'. Options: {list(ACCOUNTS.keys())}", file=sys.stderr)
        sys.exit(1)
    
    # Get account ID from env or use default
    acct_id = env_vars.get(config["acct_id_key"]) or config["default_id"]
    if not acct_id:
        print(f"ERROR: No account ID for '{account}'. Add {config['acct_id_key']}=acct_xxx to .env.agents", file=sys.stderr)
        print(f"\n  To find the account ID:", file=sys.stderr)
        print(f"  1. Log into Stripe Dashboard for {config['description']}", file=sys.stderr)
        print(f"  2. Go to Settings > Account details", file=sys.stderr)
        print(f"  3. Copy the Account ID (starts with acct_)", file=sys.stderr)
        print(f"  4. Add to .env.agents: {config['acct_id_key']}=acct_xxx", file=sys.stderr)
        sys.exit(1)
    
    return StripeClient(org_key, acct_id)


def format_amount(amount, currency="usd"):
    """Format cents to dollars."""
    if amount is None:
        return "N/A"
    return f"${amount / 100:.2f} {currency.upper()}"


def generate_payment_link(
    amount_cents: int,
    label: str,
    currency: str = "cad",
    recurring: str = None,
    account: str = "oasis",
) -> dict:
    """Create product + price + payment link in one shot. Importable by other scripts.

    Args:
        amount_cents: Price in cents (e.g., 25000 for $250.00)
        label: Human-readable product name (e.g., "OASIS AI Monthly Retainer")
        currency: ISO currency code (default: "cad")
        recurring: "month" or "year" for subscriptions, None for one-time
        account: Stripe account alias (default: "oasis")

    Returns:
        {"url": "https://buy.stripe.com/...", "price_id": "price_...", "product_id": "prod_..."}
    """
    env_vars = load_env()
    client = get_client(env_vars, account)

    prod = client.post("products", {"name": label})

    params = {
        "unit_amount": str(amount_cents),
        "currency": currency,
        "product": prod["id"],
    }
    if recurring:
        params["recurring[interval]"] = recurring

    price = client.post("prices", params)
    link = client.post("payment_links", {
        "line_items[0][price]": price["id"],
        "line_items[0][quantity]": "1",
    })

    return {
        "url": link.get("url", ""),
        "price_id": price["id"],
        "product_id": prod["id"],
    }


# ── Commands ──────────────────────────────────────────────

def cmd_list_accounts(env_vars, args):
    """List all configured Stripe accounts and their connection status."""
    org_key = env_vars.get("STRIPE_ORG_KEY")
    if not org_key:
        print("ERROR: STRIPE_ORG_KEY not found in .env.agents")
        return
    
    print("Configured Stripe Accounts:\n")
    for name, config in ACCOUNTS.items():
        acct_id = env_vars.get(config["acct_id_key"]) or config["default_id"]
        if acct_id:
            try:
                client = StripeClient(org_key, acct_id)
                bal = client.get("balance")
                avail = sum(a["amount"] for a in bal.get("available", [])) / 100
                currency = bal.get("available", [{}])[0].get("currency", "usd").upper()
                status = f"LIVE - Balance: ${avail:.2f} {currency}"
            except Exception as e:
                status = f"ERROR - {str(e)[:80]}"
        else:
            status = "NOT CONFIGURED - add account ID to .env.agents"
        
        print(f"  [{name}] {config['description']}")
        print(f"    Account ID: {acct_id or 'MISSING'}")
        print(f"    Status: {status}")
        print()


def cmd_balance(client, args):
    """Get current Stripe balance."""
    bal = client.get("balance")
    print("Stripe Account Balance:\n")
    for b in bal.get("available", []):
        print(f"  Available: {format_amount(b['amount'], b['currency'])}")
    for b in bal.get("pending", []):
        print(f"  Pending:   {format_amount(b['amount'], b['currency'])}")


def cmd_customers(client, args):
    """List customers."""
    params = {"limit": args.limit}
    if args.email:
        params["email"] = args.email
    data = client.get("customers", params)
    
    print(f"Customers (showing up to {args.limit}):\n")
    for c in data.get("data", []):
        email = c.get("email", "no email")
        name = c.get("name", "unnamed")
        print(f"  [{c['id']}] {name} -- {email}")
    print(f"\n--- {len(data.get('data', []))} customer(s) ---")


def cmd_products(client, args):
    """List products."""
    data = client.get("products", {"limit": args.limit})
    
    print(f"Products (showing up to {args.limit}):\n")
    for p in data.get("data", []):
        status = "[active]" if p.get("active") else "[inactive]"
        print(f"  [{p['id']}] {p.get('name', 'unnamed')} -- {status}")
        if p.get("description"):
            print(f"    {p['description'][:80]}")
    print(f"\n--- {len(data.get('data', []))} product(s) ---")


def cmd_prices(client, args):
    """List prices."""
    params = {"limit": args.limit}
    if args.product:
        params["product"] = args.product
    data = client.get("prices", params)
    
    print(f"Prices (showing up to {args.limit}):\n")
    for p in data.get("data", []):
        recurring = ""
        if p.get("recurring"):
            recurring = f" / {p['recurring'].get('interval', '')}"
        print(f"  [{p['id']}] {format_amount(p.get('unit_amount'), p.get('currency', 'usd'))}{recurring} -- {p.get('type', '')}")
        if p.get("product"):
            print(f"    Product: {p['product']}")
    print(f"\n--- {len(data.get('data', []))} price(s) ---")


def cmd_invoices(client, args):
    """List invoices."""
    params = {"limit": args.limit}
    if args.customer:
        params["customer"] = args.customer
    if args.status:
        params["status"] = args.status
    data = client.get("invoices", params)
    
    print(f"Invoices (showing up to {args.limit}):\n")
    for inv in data.get("data", []):
        customer = inv.get("customer_name") or inv.get("customer_email") or inv.get("customer", "N/A")
        print(f"  [{inv['id']}] {format_amount(inv.get('amount_due'), inv.get('currency', 'usd'))} -- {inv.get('status', '?')} -- {customer}")
    print(f"\n--- {len(data.get('data', []))} invoice(s) ---")


def cmd_subscriptions(client, args):
    """List subscriptions."""
    params = {"limit": args.limit}
    if args.customer:
        params["customer"] = args.customer
    if args.status:
        params["status"] = args.status
    data = client.get("subscriptions", params)
    
    print(f"Subscriptions (showing up to {args.limit}):\n")
    for s in data.get("data", []):
        items = s.get("items", {}).get("data", [])
        items_desc = ", ".join([
            format_amount(item.get("price", {}).get("unit_amount"), item.get("price", {}).get("currency", "usd"))
            for item in items
        ]) if items else "no items"
        
        print(f"  [{s['id']}] {s.get('status', '?')} -- {items_desc}")
        if s.get("customer"):
            print(f"    Customer: {s['customer']}")
    print(f"\n--- {len(data.get('data', []))} subscription(s) ---")


def cmd_charges(client, args):
    """List recent charges."""
    data = client.get("charges", {"limit": args.limit})
    
    print(f"Recent Charges (showing up to {args.limit}):\n")
    for c in data.get("data", []):
        status = "succeeded" if c.get("status") == "succeeded" else c.get("status", "?")
        desc = c.get("description", "no description")
        print(f"  [{c['id']}] {format_amount(c.get('amount'), c.get('currency', 'usd'))} -- {status}")
        print(f"    {desc}")
    print(f"\n--- {len(data.get('data', []))} charge(s) ---")


def cmd_payment_links(client, args):
    """List payment links."""
    data = client.get("payment_links", {"limit": args.limit})
    
    print(f"Payment Links (showing up to {args.limit}):\n")
    for link in data.get("data", []):
        status = "[active]" if link.get("active") else "[inactive]"
        print(f"  [{link['id']}] {status}")
        print(f"    URL: {link.get('url', 'N/A')}")
    print(f"\n--- {len(data.get('data', []))} link(s) ---")


def cmd_create_payment_link(client, args):
    """Create a new payment link."""
    result = client.post("payment_links", {
        "line_items[0][price]": args.price,
        "line_items[0][quantity]": args.quantity,
    })
    print(f"Payment link created!")
    print(f"  ID:  {result['id']}")
    print(f"  URL: {result.get('url', 'N/A')}")


def cmd_create_price(client, args):
    """Create a price (and optionally a product) for custom payment links."""
    # Create an ad-hoc product if none specified
    product_id = args.product
    if not product_id:
        prod = client.post("products", {
            "name": args.label or f"OASIS Custom - ${args.amount / 100:.0f}",
        })
        product_id = prod["id"]

    params = {
        "unit_amount": str(args.amount),
        "currency": args.currency,
        "product": product_id,
    }
    if args.recurring:
        params["recurring[interval]"] = args.recurring  # "month" or "year"

    result = client.post("prices", params)
    price_id = result["id"]
    kind = f"/ {args.recurring}" if args.recurring else "one-time"
    print(f"Price created!")
    print(f"  ID:       {price_id}")
    print(f"  Amount:   {format_amount(args.amount, args.currency)} {kind}")
    print(f"  Product:  {product_id}")

    # Auto-create payment link if --link flag is set
    if args.link:
        link = client.post("payment_links", {
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
        })
        print(f"  Pay Link: {link.get('url', 'N/A')}")


def cmd_quick_link(client, args):
    """One-shot: create product + price + payment link from just an amount and label."""
    prod = client.post("products", {
        "name": args.label,
    })
    params = {
        "unit_amount": str(args.amount),
        "currency": args.currency,
        "product": prod["id"],
    }
    if args.recurring:
        params["recurring[interval]"] = args.recurring

    price = client.post("prices", params)
    link = client.post("payment_links", {
        "line_items[0][price]": price["id"],
        "line_items[0][quantity]": "1",
    })
    kind = f"/{args.recurring}" if args.recurring else "one-time"
    print(f"{link.get('url', 'ERROR')}")
    if not getattr(args, "output_json", False):
        amt = format_amount(args.amount, args.currency)
        print(f"  ({amt} {kind} — {args.label})")


def cmd_create_customer(client, args):
    """Create a new customer."""
    params = {}
    if args.email:
        params["email"] = args.email
    if args.name:
        params["name"] = args.name
    if args.phone:
        params["phone"] = args.phone
    if args.description:
        params["description"] = args.description
    
    result = client.post("customers", params)
    print(f"Customer created!")
    print(f"  ID:    {result['id']}")
    print(f"  Name:  {result.get('name', 'N/A')}")
    print(f"  Email: {result.get('email', 'N/A')}")


def cmd_create_invoice(client, args):
    """Create a draft invoice for a customer."""
    params = {"customer": args.customer}
    if args.description:
        params["description"] = args.description
    if args.auto_advance:
        params["auto_advance"] = "true"
    
    result = client.post("invoices", params)
    print(f"Invoice created (draft)!")
    print(f"  ID:     {result['id']}")
    print(f"  Status: {result.get('status', '?')}")
    print(f"  URL:    {result.get('hosted_invoice_url', 'finalize to get URL')}")


def cmd_refund(client, args):
    """Refund a charge."""
    params = {"charge": args.charge_id}
    if args.amount:
        params["amount"] = str(args.amount)
    
    result = client.post("refunds", params)
    print(f"Refund created!")
    print(f"  ID:     {result['id']}")
    print(f"  Amount: {format_amount(result.get('amount'), result.get('currency', 'usd'))}")
    print(f"  Status: {result.get('status', '?')}")


def cmd_events(client, args):
    """List recent events/webhooks."""
    params = {"limit": args.limit}
    if args.type:
        params["type"] = args.type
    data = client.get("events", params)
    
    print(f"Recent Events (showing up to {args.limit}):\n")
    for e in data.get("data", []):
        ts = datetime.datetime.fromtimestamp(e.get("created", 0)).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  [{e['id']}] {e.get('type', '?')} -- {ts}")
    print(f"\n--- {len(data.get('data', []))} event(s) ---")


def main():
    parser = argparse.ArgumentParser(
        description="Stripe SDK Tool -- Universal multi-account payment access via org key",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list-accounts   (shows all 3 brands and their status)
  %(prog)s balance
  %(prog)s balance --account propflow
  %(prog)s customers --limit 5
  %(prog)s products
  %(prog)s prices --product prod_xxx
  %(prog)s invoices --status open
  %(prog)s subscriptions --status active
  %(prog)s charges --limit 5
  %(prog)s payment-links
  %(prog)s create-payment-link --price price_xxx
  %(prog)s create-price --amount 25000 --label "OASIS Setup" --link
  %(prog)s quick-link --amount 50000 --label "OASIS Retainer" --recurring month
  %(prog)s create-customer --email cc@oasis.ai --name "CC McKenna"
  %(prog)s create-invoice --customer cus_xxx
  %(prog)s refund ch_xxx --amount 500
  %(prog)s events --type payment_intent.succeeded

Accounts: oasis (default), propflow, nostalgic
To add an account: STRIPE_PROPFLOW_ACCT_ID=acct_xxx in .env.agents
        """
    )
    
    # Parent parser for shared --account and --json flags
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("--account", "-a", default="oasis", choices=list(ACCOUNTS.keys()),
                               help="Stripe account to use (default: oasis)")
    parent_parser.add_argument("--json", dest="output_json", action="store_true",
                               help="Output raw JSON for agent consumption")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # list-accounts
    subparsers.add_parser("list-accounts", help="List configured Stripe accounts and status")
    
    # balance
    subparsers.add_parser("balance", parents=[parent_parser], help="Get account balance")
    
    # customers
    p_cust = subparsers.add_parser("customers", parents=[parent_parser], help="List customers")
    p_cust.add_argument("--limit", "-l", type=int, default=10)
    p_cust.add_argument("--email", help="Filter by email")
    
    # products
    p_prod = subparsers.add_parser("products", parents=[parent_parser], help="List products")
    p_prod.add_argument("--limit", "-l", type=int, default=10)
    
    # prices
    p_price = subparsers.add_parser("prices", parents=[parent_parser], help="List prices")
    p_price.add_argument("--limit", "-l", type=int, default=10)
    p_price.add_argument("--product", help="Filter by product ID")
    
    # invoices
    p_inv = subparsers.add_parser("invoices", parents=[parent_parser], help="List invoices")
    p_inv.add_argument("--limit", "-l", type=int, default=10)
    p_inv.add_argument("--customer", help="Filter by customer ID")
    p_inv.add_argument("--status", choices=["draft", "open", "paid", "uncollectible", "void"])
    
    # subscriptions
    p_sub = subparsers.add_parser("subscriptions", parents=[parent_parser], help="List subscriptions")
    p_sub.add_argument("--limit", "-l", type=int, default=10)
    p_sub.add_argument("--customer", help="Filter by customer ID")
    p_sub.add_argument("--status", choices=["active", "canceled", "incomplete", "past_due", "trialing", "unpaid"])
    
    # charges
    p_charges = subparsers.add_parser("charges", parents=[parent_parser], help="List recent charges")
    p_charges.add_argument("--limit", "-l", type=int, default=10)
    
    # payment-links
    p_pl = subparsers.add_parser("payment-links", parents=[parent_parser], help="List payment links")
    p_pl.add_argument("--limit", "-l", type=int, default=10)
    
    # create-payment-link
    p_cpl = subparsers.add_parser("create-payment-link", parents=[parent_parser], help="Create a payment link")
    p_cpl.add_argument("--price", required=True, help="Price ID (price_xxx)")
    p_cpl.add_argument("--quantity", type=int, default=1)

    # create-price
    p_cp = subparsers.add_parser("create-price", parents=[parent_parser], help="Create a price (and optionally a product)")
    p_cp.add_argument("--amount", required=True, type=int, help="Amount in cents (e.g., 25000 for $250)")
    p_cp.add_argument("--label", help="Product name (auto-generated if omitted)")
    p_cp.add_argument("--currency", default="cad")
    p_cp.add_argument("--recurring", choices=["month", "year"], help="Recurring interval")
    p_cp.add_argument("--product", help="Existing product ID (creates new if omitted)")
    p_cp.add_argument("--link", action="store_true", help="Also create a payment link")

    # quick-link (one-shot: amount + label → payment link URL)
    p_ql = subparsers.add_parser("quick-link", parents=[parent_parser], help="Create payment link from just an amount and label")
    p_ql.add_argument("--amount", required=True, type=int, help="Amount in cents")
    p_ql.add_argument("--label", required=True, help="Product name")
    p_ql.add_argument("--currency", default="cad")
    p_ql.add_argument("--recurring", choices=["month", "year"], help="Recurring interval")

    # create-customer
    p_cc = subparsers.add_parser("create-customer", parents=[parent_parser], help="Create a customer")
    p_cc.add_argument("--email", required=True)
    p_cc.add_argument("--name", required=True)
    p_cc.add_argument("--phone")
    p_cc.add_argument("--description")
    
    # create-invoice
    p_ci = subparsers.add_parser("create-invoice", parents=[parent_parser], help="Create a draft invoice")
    p_ci.add_argument("--customer", required=True, help="Customer ID")
    p_ci.add_argument("--description")
    p_ci.add_argument("--auto-advance", action="store_true", help="Auto-finalize")
    
    # refund
    p_refund = subparsers.add_parser("refund", parents=[parent_parser], help="Refund a charge")
    p_refund.add_argument("charge_id", help="Charge ID to refund")
    p_refund.add_argument("--amount", type=int, help="Partial refund amount in cents")
    
    # events
    p_events = subparsers.add_parser("events", parents=[parent_parser], help="List recent events")
    p_events.add_argument("--limit", "-l", type=int, default=10)
    p_events.add_argument("--type", help="Event type filter (e.g., payment_intent.succeeded)")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    env_vars = load_env()
    
    # list-accounts doesn't need a specific account
    if args.command == "list-accounts":
        cmd_list_accounts(env_vars, args)
        return

    # All other commands need an authenticated client
    client = get_client(env_vars, args.account)

    # JSON mode: call API and dump raw response
    json_mode = getattr(args, "output_json", False)

    # Map commands to (handler, API endpoint) for JSON passthrough
    json_endpoints = {
        "balance": "balance",
        "customers": "customers",
        "products": "products",
        "prices": "prices",
        "invoices": "invoices",
        "subscriptions": "subscriptions",
        "charges": "charges",
        "payment-links": "payment_links",
        "events": "events",
    }

    if json_mode and args.command in json_endpoints:
        endpoint = json_endpoints[args.command]
        params = {}
        # Only add limit for list endpoints (not balance)
        if args.command != "balance" and hasattr(args, "limit"):
            params["limit"] = args.limit
        # Add optional filters
        for attr in ("customer", "email", "status", "product", "type"):
            val = getattr(args, attr, None)
            if val:
                params[attr] = val
        data = client.get(endpoint, params)
        print(json.dumps(data, indent=2))
        return

    commands = {
        "balance": cmd_balance,
        "customers": cmd_customers,
        "products": cmd_products,
        "prices": cmd_prices,
        "invoices": cmd_invoices,
        "subscriptions": cmd_subscriptions,
        "charges": cmd_charges,
        "payment-links": cmd_payment_links,
        "create-payment-link": cmd_create_payment_link,
        "create-price": cmd_create_price,
        "quick-link": cmd_quick_link,
        "create-customer": cmd_create_customer,
        "create-invoice": cmd_create_invoice,
        "refund": cmd_refund,
        "events": cmd_events,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        if json_mode:
            # For write commands, execute and dump result
            # (handled by individual cmd funcs for now)
            pass
        cmd_func(client, args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
