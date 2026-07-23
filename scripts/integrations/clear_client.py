"""integrations/clear_client.py — Thomson Reuters CLEAR S2S person search.

CLEAR is the MANUAL, SECONDARY fallback for merchant contact enrichment. The
automated path is TruePeopleSearch (uw_lead_enricher). Nothing in this module is
ever called by a daemon, a cron, or a retry loop: every query originates from a
human clicking "Pull CLAIR Report" in the dashboard. That is a policy constraint,
not an implementation detail —

  * Every CLEAR query is made under a PERMISSIBLE USE (DPPA / GLB / VOTER codes,
    from CLEAR_DPPA / CLEAR_GLB / CLEAR_VOTER). Those codes assert a legal basis
    for accessing regulated personal data. A basis is something a person has, so
    a person has to ask.
  * Queries are billable against a production account (CLEAR_ENVIRONMENT=prod).

Transport, verified against s2s.thomsonreuters.com on 2026-07-21:
  * mutual TLS — client cert from CLEAR_PFX_CERTIFICATE (base64 PKCS#12),
    unlocked with CLEAR_PASSPHRASE. Issued by "Thomson Reuters CLEAR S2S
    Issuing CA" to Breeze Advance, valid to 2026-09-15.
  * HTTP Basic on top of that, CLEAR_USERNAME / CLEAR_PASSWORD.
  * REST + XML: POST /api/v2/person/searchResults, Content-Type application/xml.
  * QuotaGuard Static SOCKS5 proxy (QUOTAGUARD_SOCKS5_URL) on EVERY request —
    CLEAR authorizes by source-IP allowlist, and only the proxy's two static
    egress IPs (52.5.238.209 / 52.6.13.167) are whitelisted on the account.
    The proxy is applied per-request in this module ONLY — never via
    HTTP_PROXY/HTTPS_PROXY — because the relay quota is metered. Before any
    billable POST, verify_tunnel() confirms the egress IP via api.ipify.org
    and ABORTS on any mismatch; there is no direct-connection fallback (it
    would fail auth and leak intent).

The PKCS#12 blob is decrypted to a PEM in a 0600 temp file for the duration of a
call and unlinked in a finally block — openssl-backed HTTP clients need a file
path, but the private key must not outlive the request.

WIRE-FORMAT CAVEAT: the endpoint, the request XML and the response schema in
this module are built from Thomson Reuters' published S2S documentation and are
NOT yet confirmed against a live response — the first real query is gated on
operator approval because it is billable and regulated. Everything
format-specific is deliberately confined to _build_search_xml() and
_parse_search_xml() so reconciling with the real payload touches two functions
and nothing else. `raw_report` is always persisted verbatim, so even a response
this module fails to parse is preserved for inspection.
"""

from __future__ import annotations

import base64
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

CLEAR_HOSTS = {
    "prod": "https://s2s.thomsonreuters.com",
    # TR's test environment. NOTE: "s2scert.thomsonreuters.com" (the name we
    # originally guessed) is NXDOMAIN — the host integrators actually use is
    # s2s.beta.thomsonreuters.com (DNS + mTLS CertificateRequest confirmed
    # 2026-07-22). "cert" kept as an alias for existing CLEAR_ENVIRONMENT values.
    "beta": "https://s2s.beta.thomsonreuters.com",
    "cert": "https://s2s.beta.thomsonreuters.com",
}
SEARCH_PATH = "/api/v2/person/searchResults"

#: The QuotaGuard Static egress IPs whitelisted on the CLEAR account. A CLEAR
#: request from any other source IP fails auth, so the tunnel gate refuses to
#: proceed unless api.ipify.org (fetched through the proxy) returns one of these.
QUOTAGUARD_ALLOWED_IPS = {"52.5.238.209", "52.6.13.167"}
IPIFY_URL = "https://api.ipify.org"
TUNNEL_CHECK_TIMEOUT = 15

DEFAULT_TIMEOUT = (10, 15)   # (connect, read) — spec: 15s hard timeout
MAX_ATTEMPTS = 3
RETRY_STATUSES = {429, 500, 502, 503, 504}
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 8.0


class ClearError(Exception):
    """A CLEAR call failed. `code` is a stable slug for the UI."""

    def __init__(self, code: str, message: str, status: Optional[int] = None,
                 body: Optional[str] = None,
                 headers: Optional[dict[str, str]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.body = (body or "")[:4000]
        # Diagnostic response headers. `Server: cloudflare` + a CF-RAY id means
        # the refusal came from the edge (IP/cert firewall rule), while an XML
        # body with a SubStatusCode means CLEAR's application refused the
        # account/entitlement — two different fixes, distinguishable only here.
        self.headers = dict(headers or {})


class ClearNotConfigured(ClearError):
    def __init__(self, missing: list[str]) -> None:
        super().__init__(
            "not_configured",
            "CLEAR credentials missing from .env.agents: " + ", ".join(missing),
        )
        self.missing = missing


@dataclass
class ClearQuery:
    """What we are asking CLEAR. Mirrors the columns on clair_reports so the
    persisted provenance and the request can never drift apart."""
    first_name: str = ""
    last_name: str = ""
    middle_name: str = ""
    street: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    dob: str = ""            # ISO YYYY-MM-DD when known
    reference: str = "sunbiz-manual-lookup"

    @classmethod
    def from_lead(cls, data: dict[str, Any], reference: str = "sunbiz-manual-lookup") -> "ClearQuery":
        name = str(
            data.get("owner_name") or data.get("contact_name") or data.get("name") or ""
        ).strip()
        parts = [p for p in re.split(r"\s+", name) if p]
        first = str(data.get("first_name") or (parts[0] if parts else "")).strip()
        last = str(data.get("last_name") or (parts[-1] if len(parts) > 1 else "")).strip()
        middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""
        return cls(
            first_name=first,
            last_name=last,
            middle_name=str(data.get("middle_name") or middle).strip(),
            # People-search indexes individuals, so the OWNER's home address
            # discriminates far better than the business address.
            street=str(data.get("owner_address_line1") or data.get("home_address")
                       or data.get("business_address_line1") or data.get("address") or "").strip(),
            city=str(data.get("owner_address_city") or data.get("home_city")
                     or data.get("business_city") or data.get("city") or "").strip(),
            state=str(data.get("owner_address_state") or data.get("home_state")
                      or data.get("business_state_code") or data.get("state_code") or "").strip(),
            zip_code=str(data.get("owner_address_zip") or data.get("home_zip")
                         or data.get("business_zip") or data.get("zip") or "").strip(),
            dob=str(data.get("owner_dob") or data.get("dob") or "").strip(),
            reference=reference,
        )

    def is_searchable(self) -> tuple[bool, str]:
        """CLEAR bills per query, so refuse one that cannot identify anybody."""
        if not self.last_name:
            return False, "a last name is required"
        if not (self.city or self.state or self.zip_code or self.dob):
            return False, "a last name alone is not enough — need city/state, ZIP, or DOB"
        return True, ""

    def as_columns(self) -> dict[str, Any]:
        """The query_* columns on clair_reports."""
        return {
            "query_name": " ".join(p for p in (self.first_name, self.middle_name, self.last_name) if p),
            "query_address": self.street or None,
            "query_city": self.city or None,
            "query_state": self.state or None,
            "query_zip": self.zip_code or None,
            "query_dob": self.dob or None,
        }


@dataclass
class ClearResult:
    status: str                       # completed | no_results | error
    people: list[dict[str, Any]] = field(default_factory=list)
    phones: list[dict[str, Any]] = field(default_factory=list)
    raw_report: Optional[str] = None
    raw_format: str = "xml"
    http_status: Optional[int] = None
    error_message: Optional[str] = None

    @property
    def result_count(self) -> int:
        return len(self.people)


# ── configuration ───────────────────────────────────────────────────────────

#: QUOTAGUARD_SOCKS5_URL is required alongside the credentials: without the
#: proxy a CLEAR call comes from the wrong source IP, fails auth, and leaks
#: intent — so a missing proxy env means "not configured", never "go direct".
_REQUIRED = ("CLEAR_USERNAME", "CLEAR_PASSWORD", "CLEAR_PFX_CERTIFICATE",
             "CLEAR_PASSPHRASE", "QUOTAGUARD_SOCKS5_URL")


def _socks5h(url: str) -> str:
    """Rewrite socks5:// -> socks5h:// so DNS also resolves through the tunnel
    (keeps the CLEAR hostname lookup off this box's resolver)."""
    return "socks5h://" + url[len("socks5://"):] if url.startswith("socks5://") else url


def clear_config(env: Optional[dict[str, str]] = None) -> dict[str, str]:
    env = env if env is not None else dict(os.environ)
    missing = [k for k in _REQUIRED if not (env.get(k) or "").strip()]
    if missing:
        raise ClearNotConfigured(missing)
    environment = (env.get("CLEAR_ENVIRONMENT") or "prod").strip().lower()
    return {
        "username": env["CLEAR_USERNAME"].strip(),
        "password": env["CLEAR_PASSWORD"].strip(),
        "pfx_b64": env["CLEAR_PFX_CERTIFICATE"].strip(),
        "passphrase": env["CLEAR_PASSPHRASE"].strip(),
        "environment": environment,
        "base_url": CLEAR_HOSTS.get(environment, CLEAR_HOSTS["prod"]),
        "dppa": (env.get("CLEAR_DPPA") or "").strip(),
        "glb": (env.get("CLEAR_GLB") or "").strip(),
        "voter": (env.get("CLEAR_VOTER") or "").strip(),
        "proxy_url": _socks5h(env["QUOTAGUARD_SOCKS5_URL"].strip()),
    }


def is_configured(env: Optional[dict[str, str]] = None) -> bool:
    try:
        clear_config(env)
        return True
    except ClearNotConfigured:
        return False


def _write_client_pem(pfx_b64: str, passphrase: str) -> str:
    """PKCS#12 -> a 0600 PEM (key + cert + chain). Caller MUST unlink it."""
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, pkcs12,
    )
    try:
        der = base64.b64decode(pfx_b64)
        key, cert, chain = pkcs12.load_key_and_certificates(der, passphrase.encode())
    except Exception as e:  # noqa: BLE001
        raise ClearError("bad_certificate",
                         f"CLEAR_PFX_CERTIFICATE / CLEAR_PASSPHRASE could not be loaded: {e}") from e
    if key is None or cert is None:
        raise ClearError("bad_certificate", "PKCS#12 bundle has no key/certificate pair")

    fd, path = tempfile.mkstemp(prefix="clear_client_", suffix=".pem")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
            fh.write(cert.public_bytes(Encoding.PEM))
            for extra in (chain or []):
                fh.write(extra.public_bytes(Encoding.PEM))
        os.chmod(path, 0o600)
        return path
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


# ── wire format (the two functions to reconcile against a live response) ────

def _el(parent: ET.Element, tag: str, text: str = "") -> ET.Element:
    node = ET.SubElement(parent, tag)
    if text:
        node.text = text
    return node


def _build_search_xml(q: ClearQuery, cfg: dict[str, str]) -> bytes:
    """PersonSearchRequest. The permissible-use block is mandatory — CLEAR
    rejects a query that does not assert one."""
    root = ET.Element("PersonSearchRequest")

    purpose = _el(root, "PermissiblePurpose")
    _el(purpose, "GLB", cfg.get("glb", ""))
    _el(purpose, "DPPA", cfg.get("dppa", ""))
    _el(purpose, "VOTER", cfg.get("voter", ""))

    _el(root, "Reference", q.reference)

    criteria = _el(root, "Criteria")
    person = _el(criteria, "PersonCriteria")
    if q.first_name:
        _el(person, "FirstName", q.first_name)
    if q.middle_name:
        _el(person, "MiddleName", q.middle_name)
    if q.last_name:
        _el(person, "LastName", q.last_name)
    if q.street:
        _el(person, "Street", q.street)
    if q.city:
        _el(person, "City", q.city)
    if q.state:
        _el(person, "State", q.state)
    if q.zip_code:
        _el(person, "ZipCode", q.zip_code)
    if q.dob:
        _el(person, "DOB", q.dob)

    return b'<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="utf-8")


def _text(node: Optional[ET.Element]) -> str:
    return (node.text or "").strip() if node is not None and node.text else ""


def _local(tag: str) -> str:
    """Strip any XML namespace so parsing survives a namespaced response."""
    return tag.rsplit("}", 1)[-1]


def _find(node: ET.Element, *names: str) -> Optional[ET.Element]:
    """First descendant whose local-name matches any of `names`."""
    wanted = {n.lower() for n in names}
    for child in node.iter():
        if _local(child.tag).lower() in wanted:
            return child
    return None


def _findall(node: ET.Element, *names: str) -> list[ET.Element]:
    wanted = {n.lower() for n in names}
    return [c for c in node.iter() if _local(c.tag).lower() in wanted]


def _parse_search_xml(body: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(people, phones) from a PersonSearchResponse.

    Namespace- and shape-tolerant on purpose: it searches by local element name
    rather than a fixed path, so a wrapper element or namespace prefix we did
    not anticipate does not zero out the parse. Anything it cannot interpret is
    still preserved by the caller in raw_report.
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        raise ClearError("bad_response", f"CLEAR returned XML that could not be parsed: {e}",
                         body=body) from e

    people: list[dict[str, Any]] = []
    seen_numbers: set[str] = set()
    phones: list[dict[str, Any]] = []

    for rec in _findall(root, "PersonResult", "Person", "PersonRecord", "Record"):
        name = _text(_find(rec, "FullName", "Name"))
        if not name:
            first = _text(_find(rec, "FirstName"))
            last = _text(_find(rec, "LastName"))
            name = " ".join(p for p in (first, last) if p)

        person_phones: list[dict[str, Any]] = []
        for pn in _findall(rec, "Phone", "PhoneNumber", "PhoneInfo"):
            number = _text(_find(pn, "Number", "PhoneNumber")) or _text(pn)
            digits = re.sub(r"\D", "", number)
            if len(digits) == 11 and digits.startswith("1"):
                digits = digits[1:]
            if len(digits) != 10:
                continue
            entry = {
                "number": digits,
                "type": _text(_find(pn, "PhoneType", "Type")) or None,
                "carrier": _text(_find(pn, "Carrier", "Provider")) or None,
                "last_seen": _text(_find(pn, "LastSeen", "LastReportedDate")) or None,
            }
            person_phones.append(entry)
            if digits not in seen_numbers:
                seen_numbers.add(digits)
                phones.append({**entry, "person": name or None})

        addresses = []
        for ad in _findall(rec, "Address", "AddressInfo"):
            line = " ".join(x for x in (
                _text(_find(ad, "Street", "AddressLine1")),
                _text(_find(ad, "City")),
                _text(_find(ad, "State")),
                _text(_find(ad, "ZipCode", "Zip")),
            ) if x)
            if line:
                addresses.append(line)

        if name or person_phones or addresses:
            people.append({
                "name": name or None,
                "age": _text(_find(rec, "Age")) or None,
                "dob": _text(_find(rec, "DOB", "DateOfBirth")) or None,
                "entity_id": _text(_find(rec, "PersonEntityId", "EntityId")) or None,
                "addresses": addresses,
                "phones": person_phones,
            })

    return people, phones


# ── transport core (shared by every endpoint) ───────────────────────────────

def verify_tunnel(proxy_url: str, timeout: int = TUNNEL_CHECK_TIMEOUT) -> str:
    """Prove the proxy egresses from a CLEAR-whitelisted IP; return that IP.

    Runs before EVERY billable POST (and is callable at service start). Fetches
    api.ipify.org THROUGH the proxy; unless the answer is one of
    QUOTAGUARD_ALLOWED_IPS this raises ClearError — wrong IP, dead relay, or
    missing env all ABORT. Never logs proxy_url (it embeds the relay password).
    """
    if not (proxy_url or "").strip():
        raise ClearError("tunnel_unverified",
                         "QUOTAGUARD_SOCKS5_URL is not set — refusing to call CLEAR directly")
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        resp = requests.get(IPIFY_URL, proxies=proxies, timeout=timeout)
        resp.raise_for_status()
        egress_ip = (resp.text or "").strip()
    except requests.RequestException as e:
        raise ClearError(
            "tunnel_unverified",
            f"could not verify QuotaGuard tunnel egress via ipify: {type(e).__name__}: {e}",
        ) from e
    if egress_ip not in QUOTAGUARD_ALLOWED_IPS:
        raise ClearError(
            "tunnel_unverified",
            f"proxy egress IP {egress_ip!r} is not in the CLEAR whitelist "
            f"{sorted(QUOTAGUARD_ALLOWED_IPS)} — aborting before any billable call",
        )
    return egress_ip


def clear_post(
    path: str,
    payload: bytes,
    cfg: dict[str, str],
    timeout: tuple[int, int] = DEFAULT_TIMEOUT,
) -> tuple[int, str]:
    """POST an XML body to a CLEAR S2S endpoint and return (status_code, body).

    The one place that owns the transport contract for EVERY endpoint: mutual
    TLS (client cert decrypted to a 0600 temp PEM, unlinked in a finally),
    HTTP Basic, exponential backoff, and the error taxonomy. Endpoint methods
    build a request and parse a response; they never touch the socket, so the
    verified transport can never drift between them.

    Every request goes through the QuotaGuard SOCKS5 proxy (per-request
    `proxies=`, never process-global), gated by verify_tunnel() — a wrong or
    unverifiable egress IP aborts BEFORE anything billable happens, and there
    is no direct-connection fallback.

    Retries transport faults and 429/5xx only — never a 4xx, which means the
    request or the permissible use was rejected and a repeat would bill again
    for the same refusal. Connect-phase failures retry (the request never
    reached CLEAR); a read timeout does NOT (CLEAR may have received and
    billed it — repeating would bill again). Raises ClearError; on 2xx
    returns the raw body.
    """
    url = cfg["base_url"] + path
    proxies = {"http": cfg["proxy_url"], "https": cfg["proxy_url"]}
    verify_tunnel(cfg["proxy_url"])  # ABORTS unless egress is whitelisted
    pem_path = _write_client_pem(cfg["pfx_b64"], cfg["passphrase"])
    last_exc: Optional[Exception] = None
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                resp = requests.post(
                    url,
                    data=payload,
                    headers={
                        "Content-Type": "application/xml",
                        "Accept": "application/xml",
                        "User-Agent": "SunBiz-CLEAR-Client/1.0",
                    },
                    auth=(cfg["username"], cfg["password"]),
                    cert=pem_path,
                    proxies=proxies,
                    timeout=timeout,
                )
            except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
                # Connect-phase failure: the request never reached CLEAR, so a
                # retry cannot double-bill.
                last_exc = e
                if attempt == MAX_ATTEMPTS:
                    raise ClearError("network_error", f"could not reach CLEAR: {e}") from e
                _backoff(attempt)
                continue
            except requests.RequestException as e:
                # Read timeout / mid-response failure: CLEAR may have already
                # received and billed the query. Fail loud, never auto-retry.
                raise ClearError(
                    "network_error",
                    f"CLEAR call failed after send ({type(e).__name__}: {e}); "
                    "NOT retried — the query may already have been billed",
                ) from e

            if resp.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                _backoff(attempt)
                continue

            body = resp.text or ""
            diag_headers = {
                k: v for k, v in resp.headers.items()
                if k.lower() in ("server", "cf-ray", "content-type", "date")
            }
            if resp.status_code in (401, 403):
                raise ClearError("unauthorized",
                                 "CLEAR rejected the credentials or the permissible use "
                                 f"(HTTP {resp.status_code})", resp.status_code, body,
                                 headers=diag_headers)
            if resp.status_code >= 400:
                raise ClearError("http_error", f"CLEAR returned HTTP {resp.status_code}",
                                 resp.status_code, body, headers=diag_headers)
            return resp.status_code, body
        raise ClearError("network_error", f"CLEAR unreachable after {MAX_ATTEMPTS} attempts: {last_exc}")
    finally:
        try:
            os.unlink(pem_path)
        except OSError:
            pass


def _backoff(attempt: int) -> None:
    """Exponential backoff with jitter. Deterministic base so tests are stable;
    jitter avoids synchronized retries. attempt is 1-based."""
    import random
    import time
    delay = min(BACKOFF_BASE_S * (2 ** (attempt - 1)), BACKOFF_MAX_S)
    time.sleep(delay + random.uniform(0, delay * 0.25))


# ── person search (wire format UNVERIFIED — no 2xx has ever been observed) ──

def person_search(
    query: ClearQuery,
    env: Optional[dict[str, str]] = None,
    timeout: tuple[int, int] = DEFAULT_TIMEOUT,
) -> ClearResult:
    """Run ONE CLEAR person search. Manual, operator-initiated calls only.

    HONESTY NOTE (2026-07-22): the earlier "VERIFIED live" claim was wrong —
    what was exercised on 2026-07-21 was only a TLS handshake, which the
    Cloudflare edge completes for anyone. No CLEAR request has ever returned
    2xx on this account, so this request/response shape is docs-derived like
    every other endpoint. Every endpoint reuses the same clear_post() transport.
    """
    ok, why = query.is_searchable()
    if not ok:
        raise ClearError("insufficient_criteria", why)

    cfg = clear_config(env)
    status, body = clear_post(SEARCH_PATH, _build_search_xml(query, cfg), cfg, timeout)
    people, phones = _parse_search_xml(body)
    return ClearResult(
        status="completed" if people else "no_results",
        people=people,
        phones=phones,
        raw_report=body,
        raw_format="xml",
        http_status=status,
    )
