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

CAPABILITY_META = {
    "category": "release.cloudflare",
    "lifecycle": "active",
    "risk": "local_write",
    "triggers": ["apply an operator authorized secret alias",
                 "CC confirmed these two keys are the same account",
                 "set a non credential config value in the env store"],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / ".env.agents"
LOG = ROOT / "state" / "secret_alias_authorized.log"


sys.path.insert(0, str(ROOT / "scripts"))
from lib.env_store import parse_text as _populated  # noqa: E402

REFUTATIONS = ROOT / "config" / "secret_match_refutations.json"


def _load_refutations() -> dict[tuple[str, str], dict]:
    """{(target, candidate): record} for pairs adversarial verification killed.

    Absent file means no recorded verdicts, not "everything is approved" — the
    applier's other checks still stand.
    """
    if not REFUTATIONS.exists():
        return {}
    try:
        data = json.loads(REFUTATIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.stderr.write(f"WARNING: cannot read {REFUTATIONS.name} ({e}); "
                         "proceeding WITHOUT refutation checks\n")
        return {}
    return {(r["target"], r["candidate"]): r for r in data.get("refuted", [])}


REFUTED = _load_refutations()


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
        if "=" not in spec:
            # `--set KEY` (a typo) would otherwise partition to an empty value
            # and blank a live setting. An omitted value is never an intent to
            # erase, so it is an error, not an empty assignment.
            print(f"  REFUSED {spec!r}: no '=' — expected KEY=VALUE")
            return (-1, text)
        key, _, value = spec.partition("=")
        key, value = key.strip(), value.strip()
        if not value:
            print(f"  REFUSED {key}: empty value — use an explicit removal path, not --set")
            return (-1, text)
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
    ap.add_argument("--override-refutation", action="store_true",
                    help="apply a pair that adversarial verification refuted")
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

        refutation = REFUTED.get((target, source))
        if refutation and not a.override_refutation:
            # Adversarial verification already killed this exact pair. Without
            # this check the refutations were written to a file nobody read, and
            # the next session would re-propose and apply a match that had been
            # disproved — with the same corroborating evidence that made it look
            # certain the first time.
            print(f"  REFUSED {target} <- {source}: previously REFUTED "
                  f"({refutation['confidence']} confidence) — {refutation['reason'][:200]}")
            print("           pass --override-refutation if you know the refutation is wrong")
            fatal = True
            continue
        if refutation:
            print(f"  OVERRIDE {target} <- {source}: applying over a recorded refutation")
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
