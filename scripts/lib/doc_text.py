"""doc_text.py — get text out of a document with NO model and NO network.

The point: an automation must not lose a capability because a subscription hit
its cap. Turning a PDF into text is not an AI problem — it is a parsing problem
that three already-installed pure-Python libraries solve for free. Once the text
exists, the free OpenCode tier (text-only) can read a document it previously had
to skip, and the deterministic extractor in application_fields.py can read it
with no model at all.

This closes the hole behind the 2026-09-03 SunBiz outage. The extraction
daemon's free fallback tier was skipped for `application/pdf` with the note
"PDFs need the API path" — and every one of the 45 real jobs in the queue was a
PDF, so the entire fallback was dead on 100% of production traffic while
appearing, in code review, to exist.

Backends, in order of quality (all already in the venv, no new dependency):
  1. pdfplumber — best layout fidelity, keeps reading order and column breaks
  2. pypdf      — fast, adequate, no external binaries
  3. fitz       — PyMuPDF; different engine, catches files the other two trip on

A PDF with no text layer (a phone photo of a paper application saved as PDF) has
nothing to extract. We say so explicitly — `is_scanned=True` — rather than
returning an empty string that a caller might read as "the document was blank".
That distinction decides whether a rep is told "re-drop this" or "type it in".
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Below this many characters per page, assume there is no real text layer.
# A cover page can legitimately be near-empty; a whole document averaging under
# this is a scan. Merchant applications run 900-4000 chars/page when digital.
SCANNED_CHARS_PER_PAGE = 60

# Hard ceiling on returned text. A 40-page funder packet would otherwise blow
# past any model's context and cost minutes of CPU for pages that never carry
# applicant fields.
MAX_CHARS = 120_000


@dataclass
class DocText:
    text: str = ""
    pages: int = 0
    method: str = "none"
    is_scanned: bool = False
    truncated: bool = False
    error: Optional[str] = None
    tried: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.text.strip())

    @property
    def chars_per_page(self) -> float:
        return (len(self.text) / self.pages) if self.pages else 0.0

    def reason(self) -> str:
        """One operator-readable clause for a job row or a log line."""
        if self.ok:
            return f"{self.method}:{self.pages}p/{len(self.text)}c"
        if self.is_scanned:
            return "no_text_layer(scanned_or_photo)"
        return self.error or "no_text_extracted"


def _via_pdfplumber(raw: bytes) -> tuple[str, int]:
    import pdfplumber  # type: ignore

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        n = len(pdf.pages)
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
            if sum(len(p) for p in parts) > MAX_CHARS:
                break
    return "\n\n".join(parts), n


def _via_pypdf(raw: bytes) -> tuple[str, int]:
    from pypdf import PdfReader  # type: ignore

    reader = PdfReader(io.BytesIO(raw))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
        if sum(len(p) for p in parts) > MAX_CHARS:
            break
    return "\n\n".join(parts), len(reader.pages)


def _via_fitz(raw: bytes) -> tuple[str, int]:
    import fitz  # type: ignore  # PyMuPDF

    parts: list[str] = []
    with fitz.open(stream=raw, filetype="pdf") as doc:
        n = doc.page_count
        for page in doc:
            parts.append(page.get_text() or "")
            if sum(len(p) for p in parts) > MAX_CHARS:
                break
    return "\n\n".join(parts), n


_PDF_BACKENDS = (
    ("pdfplumber", _via_pdfplumber),
    ("pypdf", _via_pypdf),
    ("fitz", _via_fitz),
)


def pdf_to_text(raw: bytes) -> DocText:
    """Best-effort text from PDF bytes. Never raises."""
    out = DocText()
    best: Optional[tuple[str, str, int]] = None  # (method, text, pages)
    for name, fn in _PDF_BACKENDS:
        out.tried.append(name)
        try:
            text, pages = fn(raw)
        except Exception as e:  # noqa: BLE001 — a backend that trips is not fatal, the next one may work
            out.error = f"{name}:{type(e).__name__}"
            continue
        # Keep the richest result rather than the first non-empty one: pypdf
        # frequently returns a few stray characters for a form-heavy PDF that
        # pdfplumber reads properly, and "non-empty" would stop on the junk.
        if best is None or len(text) > len(best[1]):
            best = (name, text, pages)
        if len(text) > SCANNED_CHARS_PER_PAGE * max(pages, 1):
            break  # good enough; don't pay for the other engines

    if best is None:
        out.error = out.error or "all_pdf_backends_failed"
        return out

    method, text, pages = best
    out.method, out.pages = method, pages
    if len(text) > MAX_CHARS:
        text, out.truncated = text[:MAX_CHARS], True
    out.text = text
    out.is_scanned = pages > 0 and (len(text) / pages) < SCANNED_CHARS_PER_PAGE
    if out.is_scanned:
        # Keep whatever text there was (a scan often still has a header), but
        # the flag is what callers route on.
        out.error = out.error or "text_layer_below_threshold"
    return out


def image_to_text(raw: bytes) -> DocText:
    """Images need OCR, which is not installed (no pytesseract/pdf2image).

    Deliberately explicit rather than silently empty: a caller must be able to
    tell "this machine cannot read photos" apart from "this photo was blank",
    because only the first is worth alerting on.
    """
    out = DocText(method="none", is_scanned=True)
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except Exception:
        out.error = "ocr_unavailable(no_pytesseract)"
        return out
    try:
        text = pytesseract.image_to_string(Image.open(io.BytesIO(raw))) or ""
        out.text, out.pages, out.method = text[:MAX_CHARS], 1, "pytesseract"
        out.is_scanned = not text.strip()
        return out
    except Exception as e:  # noqa: BLE001
        out.error = f"ocr_failed:{type(e).__name__}"
        return out


def extract_text(raw: bytes, mime: str) -> DocText:
    """Entry point. `mime` is the job's declared type; content wins over label."""
    m = (mime or "").lower().split(";")[0].strip()
    if raw[:5] == b"%PDF-" or m == "application/pdf":
        return pdf_to_text(raw)
    if m.startswith("image/"):
        return image_to_text(raw)
    # Unknown type: try it as text, then as a PDF. Costs nothing and rescues a
    # mislabelled upload.
    try:
        text = raw.decode("utf-8", errors="strict")
        return DocText(text=text[:MAX_CHARS], pages=1, method="utf8",
                       truncated=len(text) > MAX_CHARS)
    except Exception:  # noqa: BLE001
        return pdf_to_text(raw)


def extract_text_from_path(path: Path, mime: str = "") -> DocText:
    try:
        return extract_text(path.read_bytes(), mime or "")
    except Exception as e:  # noqa: BLE001
        return DocText(error=f"read_failed:{type(e).__name__}")
