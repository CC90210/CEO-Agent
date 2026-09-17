"""Asset staging for scripts/gpu/wan_gen.py.

Images and audio must land in ComfyUI's own input/ directory, which is also
where other agents stage THEIR assets — so the source is frequently already
the destination. shutil.copy2 raises SameFileError on that rather than
no-opping, which crashed the first --frame0-fix run on 2026-09-17.

These exercise the real functions against real files on disk; the only thing
patched is the COMFY root constant, so the copy logic under test is unmodified.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WAN_GEN = REPO_ROOT / "scripts" / "gpu" / "wan_gen.py"


def _load():
    spec = importlib.util.spec_from_file_location("wan_gen_staging", WAN_GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_staging_an_already_staged_file_does_not_raise(tmp_path, monkeypatch):
    """shutil.copy2 raises SameFileError rather than no-opping when src == dest.
    Reusing another agent's assets already sitting in ComfyUI/input is the
    NORMAL case, and it crashed the first --frame0-fix run (2026-09-17)."""
    wan = _load()
    inp = tmp_path / "input"
    inp.mkdir()
    monkeypatch.setattr(wan, "COMFY", tmp_path)
    already = inp / "vo.wav"
    already.write_bytes(b"RIFF....WAVE")

    assert wan.stage_audio(already) == "vo.wav"      # must not raise
    assert already.read_bytes() == b"RIFF....WAVE"   # and must not truncate it

    outside = tmp_path / "elsewhere.wav"
    outside.write_bytes(b"RIFF----WAVE")
    assert wan.stage_audio(outside) == "elsewhere.wav"
    assert (inp / "elsewhere.wav").read_bytes() == b"RIFF----WAVE"
