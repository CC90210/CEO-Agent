"""Find which stored secret pairs with a given Google OAuth client id.

A client id is public — it appears in the consent URL in every user's address
bar — so it can be read straight off a live deployment. Its secret cannot. That
leaves a question no amount of name-matching can answer: of the several
`*CLIENT_SECRET*` keys in the store, which one belongs to THIS client?

Google's token endpoint answers it, without a valid authorization code:

    invalid_client  -> the id/secret pair failed authentication. Wrong secret.
    invalid_grant   -> the pair AUTHENTICATED, then the bogus code was rejected.
                       That is a match.

So we send a deliberately invalid code and read which error comes back. Nothing
is granted, no token is issued, and the request is indistinguishable from a
user mistyping a code. The candidate secret is sent to Google — the party that
issued it and already knows it — and to nobody else.

WHY THIS EXISTS: on 2026-08-31 the store's GOOGLE_CLIENT_ID was found to differ
from the one live production actually uses. Deploying the store's pair would
have swapped the OAuth client underneath a working app: sign-in fails with
redirect_uri_mismatch, and every stored refresh token dies, because a refresh
token is only exchangeable by the client that minted it.

    python scripts/integrations/google_client_pair_probe.py \
        --client-id <public id> --candidates KEY_A KEY_B KEY_C
    python scripts/integrations/google_client_pair_probe.py \
        --client-id <public id> --scan            # every *CLIENT_SECRET* in the store
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "read_only",
    "triggers": ["which client secret goes with this google oauth client",
                 "find the matching google client secret",
                 "verify a google oauth client id and secret pair"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib.env_store import parse_text as _populated  # noqa: E402

STORE = ROOT / ".env.agents"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TIMEOUT = 30


def _digest(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8", "replace")).hexdigest()[:12]


def probe(client_id: str, secret: str) -> tuple[str, str]:
    """Return (google error code, human note) for this id/secret pair."""
    body = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": secret,
        # Deliberately invalid. It must FAIL — we are reading which failure.
        "code": "bravo-pair-probe-not-a-real-code",
        "grant_type": "authorization_code",
        "redirect_uri": "https://oasisai.work/api/auth/google/callback",
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            # Should be unreachable: a bogus code cannot succeed.
            return ("unexpected_success", f"HTTP {r.status} — investigate by hand")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode())
        except Exception:
            return ("unreadable", f"HTTP {e.code} with an unparseable body")
        return (payload.get("error", "unknown"),
                payload.get("error_description", ""))
    except Exception as e:                      # noqa: BLE001 — network, reported
        return ("probe_failed", str(e))


VERDICT = {
    "invalid_grant": ("MATCH  ", "pair authenticated; only the bogus code was rejected"),
    "invalid_client": ("no     ", "pair failed authentication — wrong secret for this client"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--client-id", help="the PUBLIC client id, given literally")
    # A client id is public, but pulling one out of the store on the command
    # line means echoing a store value — which secret_guard blocks, correctly,
    # since it cannot know which entries are public. Reading it internally keeps
    # the guard's rule intact instead of working around it.
    g.add_argument("--client-id-from-key",
                   help="store key holding the client id; read internally, never printed")
    ap.add_argument("--candidates", nargs="*", default=[],
                    help="store key names holding candidate secrets")
    ap.add_argument("--scan", action="store_true",
                    help="test every key whose name contains CLIENT_SECRET")
    ap.add_argument("--check-redirect-uri", metavar="URI",
                    help="ask Google whether this client accepts this redirect URI")
    a = ap.parse_args()

    pop = _populated(STORE.read_text(encoding="utf-8"))

    client_id = a.client_id
    if a.client_id_from_key:
        client_id = pop.get(a.client_id_from_key)
        if not client_id:
            sys.stderr.write(f"{a.client_id_from_key} is not populated\n")
            return 2

    if a.check_redirect_uri:
        # A valid pair still cannot sign anyone in if the callback URL is not
        # registered on that client. Google decides this at the AUTH endpoint,
        # before any consent: an unregistered URI comes back as an error page
        # naming redirect_uri_mismatch, a registered one redirects onward to
        # login. No user is involved and nothing is granted either way.
        auth = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
            "client_id": client_id,
            "redirect_uri": a.check_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
        })
        req = urllib.request.Request(auth, headers={"User-Agent": "bravo-redirect-check/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read().decode("utf-8", "replace")
                status = r.status
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            status = e.code
        except Exception as e:                  # noqa: BLE001 — network, reported
            print(f"  redirect-uri check FAILED to run: {e}")
            return 1
        low = body.lower()
        if "redirect_uri_mismatch" in low:
            print(f"  MISMATCH  Google explicitly rejected {a.check_redirect_uri}\n"
                  f"            for this client. Sign-in through it cannot work.")
            return 1
        if "invalid_client" in low or "deleted_client" in low:
            print(f"  INVALID   Google does not recognise this client (HTTP {status})")
            return 1
        # This check proves ONE direction only. An explicit redirect_uri_mismatch
        # is conclusive; its absence is not — Google serves a login interstitial
        # before validating the URI in some flows, so an unregistered URI can
        # come back looking fine. Measured: a desktop client returned HTTP 200
        # for https://definitely-not-registered.example/cb. Reporting that as
        # ACCEPTED would green-light a deploy that then cannot sign anyone in.
        print(f"  INCONCLUSIVE  no mismatch error for {a.check_redirect_uri} "
              f"(HTTP {status}).\n                This is NOT proof the URI is "
              f"registered — only that Google did not say so here.")
        return 0

    names = list(a.candidates)
    if a.scan:
        names += [k for k in pop if "CLIENT_SECRET" in k.upper()]
    names = sorted(set(names))
    if not names:
        sys.stderr.write("no candidate keys given\n")
        return 2

    print(f"client_id …{client_id[-28:]} (sha256:{_digest(client_id)})")
    print(f"probing {len(names)} candidate secret(s) against Google's token endpoint\n")

    matches = []
    for k in names:
        v = pop.get(k)
        if not v:
            print(f"  ABSENT   {k}")
            continue
        err, note = probe(client_id, v)
        verdict, explain = VERDICT.get(err, (f"?{err}", note))
        print(f"  {verdict} {k:56} sha256:{_digest(v)}  {explain}")
        if err == "invalid_grant":
            matches.append(k)

    print()
    if len(matches) == 1:
        print(f"MATCHED: {matches[0]} is the secret for this client.")
        return 0
    if not matches:
        print("NO MATCH. This client's secret is not in the store under any name —\n"
              "it has to come from the Google Cloud Console for this exact client.")
        return 1
    print(f"AMBIGUOUS: {len(matches)} keys matched ({', '.join(matches)}). "
          "They are duplicates of one secret; pick either.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
