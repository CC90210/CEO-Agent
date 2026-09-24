"""Safely stage the shared OASIS Calendar credential bundle for Vercel.

The command is a dry run unless ``--apply`` is passed.  Dedicated
GOOGLE_SYSTEM_CALENDAR_* names are preferred.  Older root stores may instead
contain a paired GOOGLE_CLIENT_* or GWS_CLIENT_* client plus
GOOGLE_REFRESH_TOKEN; those candidates are never trusted by name alone.  Each
complete pair is verified against Google, including Calendar scope and owner,
before the accepted bundle can be deployed.

Credential values are passed to Vercel over stdin and are never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from lib.secret_loader import SecretLoaderRefused, load_env as _load_secret_env


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP_DIR = REPO_ROOT.parent / "APPS" / "oasis-command-center"

REQUIRED_VARIABLES = (
    "GOOGLE_SYSTEM_CALENDAR_CLIENT_ID",
    "GOOGLE_SYSTEM_CALENDAR_CLIENT_SECRET",
    "GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN",
    "GOOGLE_SYSTEM_CALENDAR_ADDRESS",
    "GOOGLE_CALENDAR_ID",
)

CANDIDATE_VARIABLES = REQUIRED_VARIABLES + (
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "GWS_CLIENT_ID",
    "GWS_CLIENT_SECRET",
    "GOOGLE_REFRESH_TOKEN",
    "BREEZE_GOOGLE_REFRESH_TOKEN",
    "GMAIL_USER",
)

CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"
CALENDAR_FULL_SCOPE = "https://www.googleapis.com/auth/calendar"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
CALENDAR_ENDPOINT = "https://www.googleapis.com/calendar/v3/calendars"


class BundleValidationError(ValueError):
    """The local system-Calendar bundle is absent or structurally invalid."""


class CredentialVerificationError(RuntimeError):
    """Google rejected the client/token pair or its Calendar identity."""


class DeploymentError(RuntimeError):
    """Vercel did not accept the already-verified credential bundle."""


class GwsCredentialLoadError(RuntimeError):
    """The locally encrypted, working gws credential could not be exported."""


@dataclass(frozen=True, slots=True, repr=False)
class CalendarCredentialBundle:
    """The indivisible credential/config set required by OCC Calendar."""

    client_id: str
    client_secret: str
    refresh_token: str
    address: str
    calendar_id: str

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "CalendarCredentialBundle":
        normalized = {
            name: str(values.get(name) or "").strip()
            for name in REQUIRED_VARIABLES
        }
        missing = [name for name, value in normalized.items() if not value]
        if missing:
            raise BundleValidationError(
                "missing required system Calendar field(s): " + ", ".join(missing)
            )

        address = normalized["GOOGLE_SYSTEM_CALENDAR_ADDRESS"].lower()
        if "@" not in address or any(character.isspace() for character in address):
            raise BundleValidationError(
                "GOOGLE_SYSTEM_CALENDAR_ADDRESS must be the credential owner's email address"
            )

        client_id = normalized["GOOGLE_SYSTEM_CALENDAR_CLIENT_ID"]
        if not client_id.endswith(".apps.googleusercontent.com"):
            raise BundleValidationError(
                "GOOGLE_SYSTEM_CALENDAR_CLIENT_ID is not a Google OAuth client id"
            )

        return cls(
            client_id=client_id,
            client_secret=normalized["GOOGLE_SYSTEM_CALENDAR_CLIENT_SECRET"],
            refresh_token=normalized["GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN"],
            address=address,
            calendar_id=normalized["GOOGLE_CALENDAR_ID"],
        )

    def vercel_items(self) -> tuple[tuple[str, str], ...]:
        return (
            ("GOOGLE_SYSTEM_CALENDAR_CLIENT_ID", self.client_id),
            ("GOOGLE_SYSTEM_CALENDAR_CLIENT_SECRET", self.client_secret),
            ("GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN", self.refresh_token),
            ("GOOGLE_SYSTEM_CALENDAR_ADDRESS", self.address),
            ("GOOGLE_CALENDAR_ID", self.calendar_id),
        )


def load_environment() -> Mapping[str, Any]:
    """Load audited candidate keys without parser warning side channels."""

    try:
        return _load_secret_env(_audit_keys=CANDIDATE_VARIABLES)
    except (OSError, SecretLoaderRefused) as exc:
        raise BundleValidationError(
            f"canonical credential loader refused or failed ({type(exc).__name__})"
        ) from None


def calendar_bundle_candidates(
    values: Mapping[str, Any],
) -> list[tuple[str, CalendarCredentialBundle]]:
    """Build only complete client/secret/token pairings from the root store."""

    address = str(
        values.get("GOOGLE_SYSTEM_CALENDAR_ADDRESS")
        or values.get("GMAIL_USER")
        or ""
    ).strip()
    calendar_id = str(values.get("GOOGLE_CALENDAR_ID") or "primary").strip()
    pairings = (
        (
            "GOOGLE_SYSTEM_CALENDAR_CLIENT_ID",
            "GOOGLE_SYSTEM_CALENDAR_CLIENT_SECRET",
            "GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN",
        ),
        ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"),
        ("GWS_CLIENT_ID", "GWS_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"),
        (
            "GOOGLE_CLIENT_ID",
            "GOOGLE_CLIENT_SECRET",
            "BREEZE_GOOGLE_REFRESH_TOKEN",
        ),
        ("GWS_CLIENT_ID", "GWS_CLIENT_SECRET", "BREEZE_GOOGLE_REFRESH_TOKEN"),
    )

    candidates: list[tuple[str, CalendarCredentialBundle]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for client_key, secret_key, token_key in pairings:
        client_id = str(values.get(client_key) or "").strip()
        client_secret = str(values.get(secret_key) or "").strip()
        refresh_token = str(values.get(token_key) or "").strip()
        if not all((client_id, client_secret, refresh_token, address, calendar_id)):
            continue
        identity = (client_id, client_secret, refresh_token, address, calendar_id)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            bundle = CalendarCredentialBundle.from_mapping(
                {
                    "GOOGLE_SYSTEM_CALENDAR_CLIENT_ID": client_id,
                    "GOOGLE_SYSTEM_CALENDAR_CLIENT_SECRET": client_secret,
                    "GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN": refresh_token,
                    "GOOGLE_SYSTEM_CALENDAR_ADDRESS": address,
                    "GOOGLE_CALENDAR_ID": calendar_id,
                }
            )
        except BundleValidationError:
            continue
        candidates.append(
            (f"{client_key} + {secret_key} + {token_key}", bundle)
        )

    if not candidates:
        raise BundleValidationError(
            "no complete Calendar credential pairing was found in the canonical store; "
            "expected a paired system, GOOGLE_CLIENT, or GWS client plus an existing "
            "refresh token and Calendar owner address"
        )
    return candidates


def export_gws_calendar_bundle(
    values: Mapping[str, Any],
    *,
    runner: Callable[..., Any] = subprocess.run,
    find_executable: Callable[[str], str | None] = shutil.which,
) -> tuple[str, CalendarCredentialBundle]:
    """Capture the active encrypted gws session without exposing its values."""

    gws = find_executable("gws")
    if not gws:
        raise GwsCredentialLoadError("gws CLI is not installed or is not on PATH")
    try:
        result = runner(
            [gws, "auth", "export", "--unmasked"],
            capture_output=True,
            text=True,
            shell=False,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GwsCredentialLoadError(
            f"encrypted gws credential export failed ({type(exc).__name__})"
        ) from None
    if result.returncode != 0:
        raise GwsCredentialLoadError(
            f"encrypted gws credential export failed (exit {result.returncode}); output withheld"
        )
    try:
        exported = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        raise GwsCredentialLoadError(
            "encrypted gws credential export returned invalid JSON"
        ) from None
    if not isinstance(exported, dict):
        raise GwsCredentialLoadError(
            "encrypted gws credential export returned an invalid credential shape"
        )

    address = str(
        values.get("GOOGLE_SYSTEM_CALENDAR_ADDRESS")
        or values.get("GMAIL_USER")
        or ""
    ).strip()
    calendar_id = str(values.get("GOOGLE_CALENDAR_ID") or "primary").strip()
    try:
        bundle = CalendarCredentialBundle.from_mapping(
            {
                "GOOGLE_SYSTEM_CALENDAR_CLIENT_ID": exported.get("client_id"),
                "GOOGLE_SYSTEM_CALENDAR_CLIENT_SECRET": exported.get("client_secret"),
                "GOOGLE_SYSTEM_CALENDAR_REFRESH_TOKEN": exported.get("refresh_token"),
                "GOOGLE_SYSTEM_CALENDAR_ADDRESS": address,
                "GOOGLE_CALENDAR_ID": calendar_id,
            }
        )
    except BundleValidationError as exc:
        raise GwsCredentialLoadError(
            f"encrypted gws credential export was incomplete ({exc})"
        ) from None
    return "encrypted gws credential store", bundle


def _read_json_response(request: urllib.request.Request) -> Mapping[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_code = f"HTTP {exc.code}"
        try:
            body = json.loads(exc.read().decode("utf-8"))
            if isinstance(body, dict) and isinstance(body.get("error"), str):
                error_code = body["error"]
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        raise CredentialVerificationError(
            f"Google credential verification failed ({error_code}); response withheld"
        ) from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CredentialVerificationError(
            f"Google credential verification was unavailable ({type(exc).__name__})"
        ) from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CredentialVerificationError(
            "Google credential verification returned an invalid response"
        ) from None

    if not isinstance(payload, dict):
        raise CredentialVerificationError(
            "Google credential verification returned an invalid response"
        )
    return payload


def _exchange_refresh_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> Mapping[str, Any]:
    body = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    return _read_json_response(request)


def _fetch_calendar(access_token: str, calendar_id: str) -> Mapping[str, Any]:
    encoded_id = urllib.parse.quote(calendar_id, safe="")
    request = urllib.request.Request(
        f"{CALENDAR_ENDPOINT}/{encoded_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    return _read_json_response(request)


def verify_google_bundle(
    bundle: CalendarCredentialBundle,
    *,
    exchange_token: Callable[[str, str, str], Mapping[str, Any]] = _exchange_refresh_token,
    fetch_calendar: Callable[[str, str], Mapping[str, Any]] = _fetch_calendar,
) -> None:
    """Prove the exact client/token pair, scope, owner, and target Calendar."""

    token_response = exchange_token(
        bundle.client_id,
        bundle.client_secret,
        bundle.refresh_token,
    )
    access_token = str(token_response.get("access_token") or "")
    if not access_token:
        raise CredentialVerificationError(
            "Google did not issue an access token for the system client/token pair"
        )

    scopes = set(str(token_response.get("scope") or "").split())
    if not ({CALENDAR_EVENTS_SCOPE, CALENDAR_FULL_SCOPE} & scopes):
        raise CredentialVerificationError(
            "Calendar scope is missing from the system refresh credential"
        )

    primary = fetch_calendar(access_token, "primary")
    primary_id = str(primary.get("id") or "").strip().lower()
    if primary_id != bundle.address:
        raise CredentialVerificationError(
            "system Calendar owner does not match GOOGLE_SYSTEM_CALENDAR_ADDRESS"
        )

    if bundle.calendar_id.lower() != "primary":
        target = fetch_calendar(access_token, bundle.calendar_id)
        target_id = str(target.get("id") or "").strip().lower()
        if target_id != bundle.calendar_id.lower():
            raise CredentialVerificationError(
                "Google Calendar target does not match GOOGLE_CALENDAR_ID"
            )


def deploy_bundle(
    bundle: CalendarCredentialBundle,
    app_dir: Path,
    *,
    runner: Callable[..., Any] = subprocess.run,
    find_executable: Callable[[str], str | None] = shutil.which,
) -> None:
    """Deploy all five prevalidated values to Vercel Production via stdin."""

    if not app_dir.is_dir():
        raise DeploymentError(f"OCC app directory not found: {app_dir}")
    vercel = find_executable("vercel")
    if not vercel:
        raise DeploymentError("Vercel CLI is not installed or is not on PATH")

    child_env = dict(os.environ)
    node_options = child_env.get("NODE_OPTIONS", "").split()
    if "--use-system-ca" not in node_options:
        node_options.append("--use-system-ca")
    child_env["NODE_OPTIONS"] = " ".join(node_options)

    for name, value in bundle.vercel_items():
        result = runner(
            [
                vercel,
                "env",
                "add",
                name,
                "production",
                "--force",
                "--sensitive",
                "--yes",
            ],
            cwd=app_dir,
            input=value + "\n",
            env=child_env,
            text=True,
            capture_output=True,
            shell=False,
            check=False,
        )
        if result.returncode != 0:
            raise DeploymentError(
                f"Vercel rejected {name} (exit {result.returncode}); output withheld"
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the OCC system Calendar credential bundle; dry-run by default."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="verify the bundle against Google, then write all five Production variables",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    env_loader: Callable[[], Mapping[str, Any]] | None = None,
    verifier: Callable[[CalendarCredentialBundle], None] | None = None,
    deployer: Callable[[CalendarCredentialBundle, Path], None] | None = None,
    gws_loader: (
        Callable[
            [Mapping[str, Any]],
            tuple[str, CalendarCredentialBundle] | None,
        ]
        | None
    ) = None,
    app_dir: Path | None = None,
    stdout: TextIO | None = None,
) -> int:
    args = _parser().parse_args(argv)
    output = stdout or sys.stdout
    load = env_loader or load_environment
    verify = verifier or verify_google_bundle
    deploy = deployer or deploy_bundle
    load_gws = gws_loader or export_gws_calendar_bundle
    destination = app_dir or DEFAULT_APP_DIR

    try:
        values = load()
        candidates = calendar_bundle_candidates(values)
    except BundleValidationError as exc:
        print(f"ERROR: {exc}", file=output)
        return 1

    print("System Calendar deployment slots:", file=output)
    for name in REQUIRED_VARIABLES:
        print(f"  - {name}", file=output)
    print("Configured credential candidate set(s):", file=output)
    for source, _bundle in candidates:
        print(f"  - {source}", file=output)

    if not args.apply:
        print(
            "DRY RUN: no Google or Vercel calls made. Re-run with --apply to verify "
            "the configured pairings and deploy only the accepted one.",
            file=output,
        )
        return 0

    selected_source = ""
    selected_bundle: CalendarCredentialBundle | None = None
    verification_failures: list[str] = []
    for source, bundle in candidates:
        try:
            verify(bundle)
        except CredentialVerificationError as exc:
            verification_failures.append(f"{source}: {exc}")
            continue
        selected_source = source
        selected_bundle = bundle
        break

    if selected_bundle is None:
        try:
            gws_candidate = load_gws(values)
        except GwsCredentialLoadError as exc:
            verification_failures.append(str(exc))
            gws_candidate = None
        if gws_candidate is not None:
            source, bundle = gws_candidate
            try:
                verify(bundle)
            except CredentialVerificationError as exc:
                verification_failures.append(f"{source}: {exc}")
            else:
                selected_source = source
                selected_bundle = bundle

    if selected_bundle is None:
        print(
            "ERROR: Google rejected every configured Calendar credential pairing; "
            + "; ".join(verification_failures),
            file=output,
        )
        return 1

    try:
        deploy(selected_bundle, destination)
    except DeploymentError as exc:
        print(f"ERROR: {exc}", file=output)
        return 1

    print(
        "Applied the verified five-field system Calendar bundle to Vercel Production "
        f"from {selected_source}.",
        file=output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
