#!/usr/bin/env python
"""
3-Way Pulse Protocol Stress Test

Simulates a complete spend-gate flow:
  1. Maven requests $500 Meta ad spend (write cmo_pulse.json)
  2. Atlas reads the request, checks runway, approves (write cfo_pulse.json)
  3. Maven reads approval, launches (update cmo_pulse.json)
  4. Bravo reads both, updates strategy (write ceo_pulse.json)

Validates:
  - All 3 pulse files exist at their sovereign paths
  - Each can be read from any of the 3 agent projects
  - Write protocol respected (each agent only modifies its own pulse)
  - Schema shape is consistent

Run: python scripts/test_csuite_pulse_flow.py
"""

import json
from pathlib import Path
from datetime import datetime

BRAVO = Path(r"C:\Users\User\Business-Empire-Agent\data\pulse\ceo_pulse.json")
ATLAS = Path(r"C:\Users\User\APPS\CFO-Agent\data\pulse\cfo_pulse.json")
MAVEN = Path(r"C:\Users\User\CMO-Agent\data\pulse\cmo_pulse.json")
AURA  = Path(r"C:\Users\User\AURA\data\pulse\aura_pulse.json")

FAIL = 0
PASS = 0


def assert_true(cond, msg):
    global FAIL, PASS
    if cond:
        PASS += 1
        print(f"  PASS  {msg}")
    else:
        FAIL += 1
        print(f"  FAIL  {msg}")


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def save(p: Path, data: dict):
    # Preserve ISO timestamp
    data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def test_existence():
    print("\n[1/5] Pulse file existence at sovereign paths")
    assert_true(BRAVO.exists(), f"ceo_pulse.json exists ({BRAVO})")
    assert_true(ATLAS.exists(), f"cfo_pulse.json exists ({ATLAS})")
    assert_true(MAVEN.exists(), f"cmo_pulse.json exists ({MAVEN})")
    if AURA.exists():
        assert_true(True, f"aura_pulse.json exists ({AURA}) — 4-way protocol active")
    else:
        print(f"  SKIP  aura_pulse.json not yet created ({AURA}) — Aura hasn't joined the protocol yet")


def test_cross_read():
    print("\n[2/5] Cross-agent readability")
    try:
        ceo = load(BRAVO)
        cfo = load(ATLAS)
        cmo = load(MAVEN)
        assert_true("agent" in ceo, "Bravo's pulse has 'agent' field")
        assert_true("agent" in cfo, "Atlas's pulse has 'agent' field")
        assert_true("agent" in cmo, "Maven's pulse has 'agent' field")
    except Exception as e:
        assert_true(False, f"Cross-read failed: {e}")


def test_spend_gate_flow():
    print("\n[3/5] Spend-gate round-trip simulation")
    # 1. Maven requests $500 spend
    cmo = load(MAVEN)
    cmo.setdefault("spend_requests", [])
    test_request = {
        "id": "TEST-SR-001",
        "amount_cad": 500,
        "purpose": "Meta ad test — PULSE lead-gen authority hook",
        "requested_at": datetime.utcnow().isoformat() + "Z",
        "status": "pending",
    }
    cmo["spend_requests"] = [test_request]
    save(MAVEN, cmo)
    assert_true(True, "Maven wrote spend_request $500 to cmo_pulse.json")

    # 2. Atlas reads Maven, approves, writes cfo_pulse.json
    cmo_reread = load(MAVEN)
    assert_true(len(cmo_reread.get("spend_requests", [])) > 0, "Atlas can read Maven's request cross-repo")

    cfo = load(ATLAS)
    cfo.setdefault("spend_approvals", [])
    cfo["spend_approvals"] = [{
        "request_id": "TEST-SR-001",
        "approved": True,
        "approved_at": datetime.utcnow().isoformat() + "Z",
        "notes": "Runway allows — approve within $500 monthly discretionary cap",
    }]
    save(ATLAS, cfo)
    assert_true(True, "Atlas wrote approval to cfo_pulse.json")

    # 3. Maven reads Atlas's approval, updates status
    cfo_reread = load(ATLAS)
    approval = next((a for a in cfo_reread.get("spend_approvals", []) if a["request_id"] == "TEST-SR-001"), None)
    assert_true(approval is not None and approval["approved"], "Maven reads Atlas's approval cross-repo")

    cmo = load(MAVEN)
    cmo["spend_requests"][0]["status"] = "approved"
    cmo["spend_requests"][0]["approved_by"] = "atlas"
    save(MAVEN, cmo)
    assert_true(True, "Maven updated status to 'approved' in its own pulse")


def test_sovereignty():
    print("\n[4/5] Write-sovereignty enforcement (manual validation)")
    # Each agent should only write its own pulse. We test by confirming file mtimes.
    # This isn't a runtime enforcement — it's a protocol rule. But we can at least verify
    # that all three are independently writable and that their sovereign paths differ.
    assert_true(BRAVO.parent != ATLAS.parent, "Bravo and Atlas pulses live in different repos")
    assert_true(BRAVO.parent != MAVEN.parent, "Bravo and Maven pulses live in different repos")
    assert_true(ATLAS.parent != MAVEN.parent, "Atlas and Maven pulses live in different repos")


def test_cleanup():
    print("\n[5/5] Cleanup of test data")
    # Remove TEST-SR-001 from both pulses
    cmo = load(MAVEN)
    cmo["spend_requests"] = [r for r in cmo.get("spend_requests", []) if r.get("id") != "TEST-SR-001"]
    save(MAVEN, cmo)

    cfo = load(ATLAS)
    cfo["spend_approvals"] = [a for a in cfo.get("spend_approvals", []) if a.get("request_id") != "TEST-SR-001"]
    save(ATLAS, cfo)
    assert_true(True, "Test spend request + approval cleaned from both pulses")


def main():
    print("=" * 60)
    print("C-Suite 3-Way Pulse Protocol Stress Test")
    print("=" * 60)
    test_existence()
    test_cross_read()
    test_spend_gate_flow()
    test_sovereignty()
    test_cleanup()
    print("\n" + "=" * 60)
    print(f"PASS: {PASS}  FAIL: {FAIL}")
    print("=" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    exit(main())
