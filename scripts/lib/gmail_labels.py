"""Apply a Gmail label over an already-open IMAP connection.

Bravo's sweep already holds the IMAP connection and the UID of the message it
is processing, so labelling belongs here, in the same run that classifies. That
is the whole point of the 2026-08-28 change: the previous design classified in
Bravo and labelled in Atlas on a separate 15-minute cron, so a publish failure
in between produced a Telegram message saying "Route: financial" and no label
anywhere. One step, no queue, failures immediate.

Contrast with `CFO-Agent/cfo/gmail_receipts.py::add_label_by_message_id`, which
locates a message by RFC Message-ID because it runs later, out-of-band. Same
IMAP verb, same encoding rule; different entry point. This module deliberately
does NOT return a bare False - see `LabelError`.
"""

from __future__ import annotations

from typing import Optional


class LabelError(RuntimeError):
    """A label was not applied. Raised so no caller can mistake it for success.

    The failure this module exists to prevent is the silent one:
    `financial_handoff_consumer.py:942` discards a False return and carries on
    to booking, ack and a success notification as if the label had landed. A
    bare boolean makes that mistake cheap to write; an exception does not.
    """


def encode_label(label: str) -> str:
    """Encode a label for the IMAP wire.

    IMAP mailbox/label names are modified UTF-7 (RFC 3501 s5.1.3): a literal
    '&' MUST be sent as '&-'. Two of the three labels in use contain one
    ("Income & Invoices", "Statements & Notices").

    This is not a hypothetical. Until 2026-08-24 the CFO-Agent path sent labels
    raw, and every '&'-bearing label failed its STORE silently - 42 statement
    notices and every booked payout stayed unlabelled, while the '&'-free
    "Business Expenses" worked. That asymmetry is still visible in the live
    label counts.

    Scope note (mirrors the CFO-Agent implementation): our label names are
    ASCII plus '&', so '&' -> '&-' is the entire encoding. A non-ASCII label
    would need a real modified-UTF-7 encoder; `assert_encodable` guards that.
    """
    safe = str(label).replace("\\", "").replace('"', "")
    return safe.replace("&", "&-")


def assert_encodable(label: str) -> None:
    """Fail loudly if a label is outside what `encode_label` actually handles.

    Without this, a future non-ASCII label (an accented category name, say)
    would be mis-encoded silently - the exact failure mode that cost 42
    messages, wearing different clothes.
    """
    try:
        str(label).encode("ascii")
    except UnicodeEncodeError as exc:
        raise LabelError(
            f"label {label!r} is not ASCII; encode_label only implements the "
            f"ASCII + '&' subset of modified UTF-7 (RFC 3501 s5.1.3). "
            f"Implement a full encoder before using this label."
        ) from exc


def apply_label(imap, uid, label: str, use_uid: bool = False) -> str:
    """Add `label` to the message at `uid`. Returns the label on success.

    Gmail auto-creates a label that does not exist yet, which is what makes the
    January rollover to `Receipts/<next year>/...` work without provisioning.

    `use_uid` selects UID STORE over sequence STORE. It must match how the
    caller addressed the message: the main sweep uses sequence numbers
    (`imap.store`), the read-before-sweep backfill uses UIDs
    (`imap.uid("FETCH", ...)`). Mixing them silently labels the WRONG message,
    so this is a required decision rather than a guess.

    Raises LabelError on anything that is not an OK STORE - including the
    non-OK-status case, which the CFO-Agent version returns as an unlogged
    False.
    """
    if not label:
        raise LabelError("refusing to apply an empty label")
    assert_encodable(label)
    wire = encode_label(label)

    if isinstance(uid, bytes):
        uid = uid.decode("ascii", "ignore")

    try:
        if use_uid:
            status, data = imap.uid("STORE", str(uid), "+X-GM-LABELS", f'"{wire}"')
        else:
            status, data = imap.store(str(uid), "+X-GM-LABELS", f'"{wire}"')
    except Exception as exc:  # noqa: BLE001 - re-raised as LabelError below
        raise LabelError(f"IMAP STORE failed for {label!r} on uid {uid}: {exc}") from exc

    if status != "OK":
        raise LabelError(
            f"IMAP STORE returned {status!r} (not OK) for {label!r} on uid {uid}: {data!r}"
        )
    return label


def read_labels(imap, uid, use_uid: bool = False) -> Optional[list]:
    """Read back X-GM-LABELS for a uid. Used to VERIFY a write, not to decide.

    Returns None when the labels could not be read - callers must not treat
    that as "no labels".
    """
    if isinstance(uid, bytes):
        uid = uid.decode("ascii", "ignore")
    try:
        if use_uid:
            status, data = imap.uid("FETCH", str(uid), "(X-GM-LABELS)")
        else:
            status, data = imap.fetch(str(uid), "(X-GM-LABELS)")
    except Exception:  # noqa: BLE001
        return None
    if status != "OK" or not data:
        return None
    raw = b" ".join(p for p in data if isinstance(p, bytes))
    text = raw.decode("utf-8", "replace")
    start = text.find("X-GM-LABELS")
    if start == -1:
        return None
    seg = text[start:]
    open_paren = seg.find("(")
    close_paren = seg.find(")", open_paren + 1)
    if open_paren == -1 or close_paren == -1:
        return None
    inner = seg[open_paren + 1:close_paren]

    labels, buf, in_quotes = [], "", False
    for ch in inner:
        if ch == '"':
            in_quotes = not in_quotes
            continue
        if ch == " " and not in_quotes:
            if buf:
                labels.append(buf)
                buf = ""
            continue
        buf += ch
    if buf:
        labels.append(buf)
    # Decode the wire form back to the logical name.
    return [lbl.replace("&-", "&") for lbl in labels]
