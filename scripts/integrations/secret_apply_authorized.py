"""Apply an operator-authorized alias: one populated key's value into one open slot.

This exists because the automated matchers cannot settle the only question that
actually matters for a cross-prefix move: *is this the same account?* That is a
business fact, not a string-similarity result. On 2026-08-31 a semantic pass
proposed 12 cross-prefix matches and adversarial verification refuted all 12 —
including two rated "high confidence". The machine's job is to check shape and
tenant; the operator's job is to say "yes, same account".

So this tool refuses to guess. The caller must name BOTH sides explicitly, and
every application is appended to state/secret_alias_authorized.log with the
reason, so a later reader can see it was a human decision and not an inference.

Mechanical checks still run, because an authorized pair can still be a typo:
  * the source must actually be populated,
  * the target must be an OPEN `# FILL` slot (never silently overwrite),
  * both values must share a shape class (a password is not an email),
  * the write is re-read from disk and rolled back if it did not land.

Usage:
  python scripts/integrations/secret_apply_authorized.py \
      --pair TARGET_SRC=SOURCE_KEY --reason "CC confirmed 2026-08-31: same mailbox"
  add --apply to write; default is a dry run.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".env.agents"
LOG = ROOT / "state" / "secret_alias_authorized.log"


def _populated(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if k and v:
            out[k] = v
    return out


def _shape(v: str) -> str:
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", v):
        return "email"
    if v.startswith("http://") or v.startswith("https://"):
        return "url"
    if v.startswith("eyJ") and v.count(".") == 2:
        return "jwt"
    if re.fullmatch(r"[0-9]+(,[0-9]+)*", v):
        return "numeric-id-list"
    return "opaque"


def _looks_like_credential(v: str) -> bool:
    """Cheap entropy test, used only to refuse — never to approve.

    Overwriting a config enum is routine; overwriting a live credential is how a
    tenant loses access with no way back. When unsure, this says True.
    """
    if len(v) >= 24:
        return True
    return bool(re.search(r"[A-Za-z0-9_-]{20,}", v))


def _set_values(text: str, pairs: list[str], apply: bool) -> tuple[int, str]:
    """Overwrite already-populated keys. Separate from alias application because
    the risk profile is different: an alias fills a hole, a set destroys a value.
    """
    pop = _populated(text)
    planned: list[tuple[str, str]] = []
    for spec in pairs:
        key, _, value = spec.partition("=")
        key, value = key.strip(), value.strip()
        current = pop.get(key)
        if current is None:
            print(f"  REFUSED {key}: not present — use --pair to fill a slot, not --set")
            return (-1, text)
        if current == value:
            print(f"  SKIP    {key}: already {value!r}")
            continue
        if _looks_like_credential(current):
            print(f"  REFUSED {key}: current value looks like a live credential, "
                  f"not a config flag — refusing to overwrite it from here")
            return (-1, text)
        print(f"  SET     {key}: {current!r} -> {value!r}")
        planned.append((key, value))

    if not apply:
        return (len(planned), text)
    for key, value in planned:
        text = re.sub(rf"(?m)^{re.escape(key)}=.*$", f"{key}={value}", text, count=1)
    return (len(planned), text)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", action="append", default=[],
                    help="TARGET_FILL_SRC=SOURCE_KEY (repeatable)")
    ap.add_argument("--set", action="append", default=[], dest="set_pairs",
                    help="KEY=VALUE — overwrite a populated NON-credential config value")
    ap.add_argument("--reason", required=True, help="who authorized this, and when")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not a.pair and not a.set_pairs:
        ap.error("give at least one --pair or --set")

    text = STORE.read_text(encoding="utf-8")
    pop = _populated(text)

    planned: list[tuple[str, str, str]] = []
    fatal = False
    for spec in a.pair:
        if "=" not in spec:
            sys.stderr.write(f"bad --pair {spec!r}, expected TARGET=SOURCE\n")
            return 2
        target, _, source = spec.partition("=")
        target, source = target.strip(), source.strip()

        if source not in pop:
            print(f"  REFUSED {target} <- {source}: source is not populated")
            fatal = True
            continue
        if f"# FILL {target}=" not in text:
            state = "already populated" if target in pop else "no such slot"
            print(f"  REFUSED {target} <- {source}: target is not an open FILL slot ({state})")
            fatal = True
            continue
        sh_src = _shape(pop[source])
        planned.append((target, source, sh_src))
        print(f"  OK      {target} <- {source}  [{sh_src}]")

    set_count, set_text = _set_values(text, a.set_pairs, a.apply)
    if set_count < 0:
        fatal = True

    if fatal:
        print("\nrefusing to apply anything while one entry is invalid (all-or-nothing).")
        return 1
    if not a.apply:
        print("\ndry run — re-run with --apply to write.")
        return 0

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = STORE.with_name(f".env.agents.bak.{stamp}")
    shutil.copy2(STORE, backup)
    text = set_text
    for target, source, _sh in planned:
        text = text.replace(f"# FILL {target}=", f"{target}={pop[source]}", 1)
    STORE.write_text(text, encoding="utf-8", newline="\n")

    after = _populated(STORE.read_text(encoding="utf-8"))
    bad = [t for t, s, _ in planned if after.get(t) != pop[s]]
    bad += [k.split("=", 1)[0].strip() for k in a.set_pairs
            if after.get(k.split("=", 1)[0].strip()) != k.split("=", 1)[1].strip()]
    if bad:
        shutil.copy2(backup, STORE)
        sys.stderr.write(f"write verification FAILED for {bad}; store restored from {backup.name}\n")
        return 1

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        for target, source, sh in planned:
            fh.write(json.dumps({
                "ts": stamp, "target": target, "source": source,
                "shape": sh, "reason": a.reason,
            }) + "\n")
        for spec in a.set_pairs:
            key, _, value = spec.partition("=")
            fh.write(json.dumps({
                "ts": stamp, "target": key.strip(), "op": "set",
                "value": value.strip(), "reason": a.reason,
            }) + "\n")
    print(f"\napplied {len(planned)} alias(es) + {set_count} set(s); "
          f"backup {backup.name}; logged to {LOG.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
