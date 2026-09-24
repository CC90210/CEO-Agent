"""hostinger_tool.py — Hostinger account/VPS/GPU read + controlled mutation for the fleet.

House pattern (wrangler_tool.py): the token loads via the sanctioned
secret_loader, is sent ONLY as a Bearer header to developers.hostinger.com,
and is never printed, logged, or placed on argv.

    python scripts/integrations/hostinger_tool.py whoami
    python scripts/integrations/hostinger_tool.py vps list
    python scripts/integrations/hostinger_tool.py vps get <id>
    python scripts/integrations/hostinger_tool.py vps metrics <id>
    python scripts/integrations/hostinger_tool.py ssh-keys
    python scripts/integrations/hostinger_tool.py add-key --name <n> --pubkey-file <f.pub>
    python scripts/integrations/hostinger_tool.py billing subscriptions
    python scripts/integrations/hostinger_tool.py gpu probe
    python scripts/integrations/hostinger_tool.py raw <path>

THE TRAP (verified 2026-09-16): plain urllib/python UAs get HTTP 403
`error code: 1010` from Cloudflare in front of developers.hostinger.com. Every
request here MUST carry a browser User-Agent. See
pattern_a_default_client_identity_can_be_what_an_edge_blocks.

GPU is Beta and hPanel-only — `/api/gpu/*` returned 404 on every probed shape
as of 2026-09-16. `gpu probe` re-runs that probe so the fleet notices the day
it ships. Full context: docs/handovers/2026-09-16_hostinger_gpu_llm_handover.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CAPABILITY_META = {
    "category": "infra.hostinger",
    "lifecycle": "active",
    # external_write, not external_read: `add-key` POSTs a public key to the
    # account. The fleet routes on this field, so leaving it at read would let
    # a mutation run through a read-only path.
    "risk": "external_write",
    "triggers": [
        "list the hostinger vps fleet",
        "find the gpu instance ip address",
        "check hostinger billing, credits, or subscriptions",
        "look up a hostinger server's connection details",
        "register an ssh public key on the hostinger account",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from lib.secret_loader import load_env  # noqa: E402

BASE = "https://developers.hostinger.com"
# Cloudflare 1010 blocks stock python-urllib UAs (same wall as cloudflare_admin.py).
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"

# CC's `.env.agents` carried the typo'd name first; accept both, prefer the standard.
TOKEN_KEYS = ("HOSTINGER_API_TOKEN", "HOSTSTINGER_KEY", "HOSTINGER_KEY", "HOSTINGER_TOKEN")

# 90 req/min per user — self-throttle so a loop can never trip it.
_MIN_INTERVAL = 0.7
_last_call = [0.0]


class HostingerError(RuntimeError):
    pass


def _token() -> str:
    env = load_env(_audit_keys=list(TOKEN_KEYS))
    for key in TOKEN_KEYS:
        val = (env.get(key) or "").strip()
        if val:
            return val
    raise HostingerError(
        "no Hostinger token in .env.agents — expected HOSTINGER_API_TOKEN "
        f"(also accepted: {', '.join(TOKEN_KEYS[1:])})"
    )


def call(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, object]:
    """Return (status, parsed_json_or_text). Never raises on HTTP status."""
    wait = _MIN_INTERVAL - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.monotonic()

    url = path if path.startswith("http") else f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {_token()}")
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        status = exc.code
    except urllib.error.URLError as exc:
        raise HostingerError(f"network error reaching {url}: {exc.reason}") from exc

    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, raw


def _emit(payload: object, as_json: bool) -> None:
    """Human table for lists of flat records; JSON for everything else.

    `--json` used to select between two identical branches. A flag that does
    nothing is worse than no flag — it reads as a supported mode in the routing
    table and silently is not one.
    """
    if as_json or not isinstance(payload, list) or not payload:
        print(json.dumps(payload, indent=2, default=str))
        return
    if not all(isinstance(row, dict) for row in payload):
        print(json.dumps(payload, indent=2, default=str))
        return

    cols = list(payload[0].keys())
    widths = {c: max(len(str(c)), *(len(str(r.get(c, ""))) for r in payload)) for c in cols}
    print("  ".join(str(c).ljust(widths[c]) for c in cols))
    print("  ".join("-" * widths[c] for c in cols))
    for row in payload:
        print("  ".join(str(row.get(c, "")).ljust(widths[c]) for c in cols))


def _fleet() -> list[dict]:
    status, body = call("/api/vps/v1/virtual-machines")
    if status != 200:
        raise HostingerError(f"vps list failed: HTTP {status} — {body}")
    if isinstance(body, dict):
        body = body.get("data", body)
    return body if isinstance(body, list) else [body]


def _summarize(vm: dict) -> dict:
    """Pull the fields that actually matter for connecting to a box."""
    return {
        "id": vm.get("id"),
        "hostname": vm.get("hostname"),
        "state": vm.get("state"),
        "ipv4": [ip.get("address") for ip in (vm.get("ipv4") or []) if isinstance(ip, dict)]
        or vm.get("ip_address"),
        "ipv6": [ip.get("address") for ip in (vm.get("ipv6") or []) if isinstance(ip, dict)],
        "template": (vm.get("template") or {}).get("name") if isinstance(vm.get("template"), dict) else vm.get("template"),
        "plan": vm.get("plan"),
        "cpus": vm.get("cpus"),
        "memory_mb": vm.get("memory"),
        "disk_mb": vm.get("disk"),
        "created_at": vm.get("created_at"),
    }


GPU_PROBE_PATHS = [
    "/api/gpu/v1/instances",
    "/api/gpu/v1/virtual-machines",
    "/api/vps/v1/gpu",
    "/api/vps/v1/gpu-instances",
    "/api/gpu/v1/servers",
    "/api/compute/v1/gpu",
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Hostinger API CLI (read-first).")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("whoami", help="prove the token works; show fleet size")

    vps = sub.add_parser("vps", help="virtual machine operations")
    vsub = vps.add_subparsers(dest="vcmd", required=True)
    vsub.add_parser("list", help="list all virtual machines (summary)")
    vsub.add_parser("list-raw", help="list all virtual machines (full payload)")
    g = vsub.add_parser("get", help="one machine, full payload")
    g.add_argument("id")
    m = vsub.add_parser("metrics", help="machine metrics")
    m.add_argument("id")

    sub.add_parser("ssh-keys", help="public keys registered on the account")
    ak = sub.add_parser("add-key", help="register a PUBLIC key on the account")
    ak.add_argument("--name", required=True)
    ak.add_argument("--pubkey-file", required=True,
                    help="path to a .pub file (public half ONLY — never a private key)")
    b = sub.add_parser("billing", help="billing/credits")
    b.add_argument("what", nargs="?", default="subscriptions",
                   choices=["subscriptions", "catalog", "orders"])
    sub.add_parser("gpu", help="GPU endpoint radar").add_argument(
        "action", nargs="?", default="probe", choices=["probe"])
    r = sub.add_parser("raw", help="GET an arbitrary API path")
    r.add_argument("path")

    args = ap.parse_args()

    try:
        if args.cmd == "whoami":
            fleet = _fleet()
            _emit({"ok": True, "base": BASE, "machines": len(fleet),
                   "hostnames": [v.get("hostname") for v in fleet]}, args.json)

        elif args.cmd == "vps":
            if args.vcmd == "list":
                _emit([_summarize(v) for v in _fleet()], args.json)
            elif args.vcmd == "list-raw":
                _emit(_fleet(), args.json)
            elif args.vcmd == "get":
                status, body = call(f"/api/vps/v1/virtual-machines/{args.id}")
                _emit({"status": status, "data": body}, args.json)
            elif args.vcmd == "metrics":
                status, body = call(f"/api/vps/v1/virtual-machines/{args.id}/metrics")
                _emit({"status": status, "data": body}, args.json)

        elif args.cmd == "ssh-keys":
            status, body = call("/api/vps/v1/public-keys")
            _emit({"status": status, "data": body}, args.json)

        elif args.cmd == "add-key":
            text = Path(args.pubkey_file).read_text(encoding="utf-8").strip()
            # Refuse a private key outright. Uploading one would hand the
            # account a credential that is supposed to never leave the machine,
            # and a mistyped filename is the realistic way that happens.
            if "PRIVATE KEY" in text or not text.startswith(("ssh-", "ecdsa-")):
                raise HostingerError(
                    f"{args.pubkey_file} is not an OpenSSH PUBLIC key "
                    "(expected a single line starting with 'ssh-'). Refusing to upload."
                )
            status, body = call("/api/vps/v1/public-keys", method="POST",
                                body={"name": args.name, "key": text})
            _emit({"status": status, "data": body,
                   "note": "account-level key: selectable in the SSH key field on FUTURE deploys; "
                           "does NOT reach an already-running instance"}, args.json)

        elif args.cmd == "billing":
            path = {"subscriptions": "/api/billing/v1/subscriptions",
                    "catalog": "/api/billing/v1/catalog",
                    "orders": "/api/billing/v1/orders"}[args.what]
            status, body = call(path)
            _emit({"status": status, "data": body}, args.json)

        elif args.cmd == "gpu":
            results = []
            for p in GPU_PROBE_PATHS:
                status, body = call(p)
                results.append({"path": p, "status": status,
                                "hit": status not in (404, 403, 405)})
            _emit({"gpu_api_available": any(r["hit"] for r in results),
                   "probes": results}, args.json)

        elif args.cmd == "raw":
            status, body = call(args.path)
            _emit({"status": status, "data": body}, args.json)

    except HostingerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
