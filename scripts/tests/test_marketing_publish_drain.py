"""The publish drain's contract, tested without publishing anything.

The dangerous property here is not "does it post" — it is "can it post TWICE".
A reel that goes out to five networks a second time cannot be recalled; deleting
a post does not unsend it. So the claim is a compare-and-set, and this proves it
by claiming the same intent twice on purpose.

That test earned its place immediately: the first implementation guarded the
UPDATE correctly and then RE-READ the row to decide whether it had won, which
cannot distinguish "I set this to running" from "someone else did". Both drains
saw `running` and both concluded they held the claim.

  python scripts/tests/test_marketing_publish_drain.py
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

BRAVO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BRAVO / "scripts"))

_spec = importlib.util.spec_from_file_location(
    "marketing_publish_drain", BRAVO / "scripts" / "marketing_publish_drain.py"
)
drain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drain)

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# ── caption building: never invents copy ────────────────────────────────────
print("caption_for")
full = {
    "title": "T", "hook": "the hook.", "body": "the body.",
    "cta": "join the waitlist", "landing_url": "https://oasisai.work/contact",
}
short = drain.caption_for(full, professional=False)
pro = drain.caption_for(full, professional=True)
check("short form leads with the hook", short.startswith("the hook."))
check("linkedin leads with the argument, not the hook", pro.startswith("the body."))
check("cta and landing are appended", "Join the waitlist → https://oasisai.work/contact" in short)
check("both registers carry the landing url", "oasisai.work/contact" in pro)

bare = drain.caption_for({"title": "Just a title"}, professional=False)
check("empty copy falls back to the title", bare == "Just a title", repr(bare))
check(
    "nothing is invented when Maven wrote nothing",
    "waitlist" not in bare and "→" not in bare,
    repr(bare),
)

# A caption must never come back empty — every network rejects that.
check("never returns an empty caption", bool(drain.caption_for({"title": "x"}, professional=True)))

# ── the split matches CMO-Agent/scripts/schedule_posts.py ───────────────────
print("platform split")
check("linkedin is not short form", "linkedin" not in drain.SHORT_FORM)
check(
    "the five short-form networks are exactly the ones schedule_posts lists",
    drain.SHORT_FORM == {"instagram", "tiktok", "youtube", "twitter", "threads"},
    str(sorted(drain.SHORT_FORM)),
)
check(
    "googlebusiness is not publishable from here",
    "googlebusiness" not in drain.SHORT_FORM,
    "CC excluded it deliberately on 2026-07-27 — different content shape",
)

# ── the claim is a real compare-and-set ─────────────────────────────────────
# A fake that behaves like the guarded UPDATE: rows come back only when the row
# actually matched. This is the shape the first implementation got wrong.
print("claim (compare-and-set)")


class _Fake:
    def __init__(self, state="queued"):
        self.state = state
        self._filters = {}
        self._patch = None

    def table(self, _n):
        return self

    def update(self, patch):
        self._patch = patch
        self._filters = {}
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def select(self, *_a, **_k):
        return self

    def execute(self):
        guard = self._filters.get("state")
        matched = guard is None or self.state == guard
        if matched and self._patch:
            self.state = self._patch.get("state", self.state)
        return type("R", (), {"data": [{"id": "i1"}] if matched else []})()


fake = _Fake()
first = drain.claim(fake, "i1")
second = drain.claim(fake, "i1")
check("the first drain claims it", first is True)
check(
    "a second drain CANNOT claim it",
    second is False,
    "two drains would publish the same reel twice, and there is no unsending",
)
check("the row is left running", fake.state == "running")

print()
if failures:
    print(f"FAILED: {len(failures)} — {', '.join(failures)}")
    raise SystemExit(1)
print("marketing_publish_drain: all assertions passed")
