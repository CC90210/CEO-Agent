"""Pin the per-mode CLI defaults in scripts/gpu/wan_gen.py.

The 5B and A14B model families have different native frame rates and sigma
shifts. A shared argparse default block silently applied the 5B values to the
14B path — playing a 16fps model back at 24fps runs it 1.5x fast, which a
viewer reads as "the AI looks wrong" rather than as a config bug. Caught by
Maven 2026-09-17 before any I2V render reached CC.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WAN_GEN = REPO_ROOT / "scripts" / "gpu" / "wan_gen.py"


def _load():
    spec = importlib.util.spec_from_file_location("wan_gen_defaults", WAN_GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _defaults(mode: str) -> dict:
    """Parse a minimal command line for `mode` and return the resolved args."""
    wan = _load()
    import argparse
    import sys

    argv = ["wan_gen.py", mode, "--prompt", "x"]
    if mode in ("i2v", "s2v"):
        argv += ["--image", "/tmp/x.png"]
    if mode == "s2v":
        argv += ["--audio", "/tmp/x.wav"]

    captured = {}
    real_parse = argparse.ArgumentParser.parse_args

    def spy(self, args=None, namespace=None):
        ns = real_parse(self, args, namespace)
        captured.update(vars(ns))
        raise SystemExit(0)  # stop before it tries to reach ComfyUI

    argparse.ArgumentParser.parse_args = spy
    old_argv = sys.argv
    try:
        sys.argv = argv
        with pytest.raises(SystemExit):
            wan.main()
    finally:
        argparse.ArgumentParser.parse_args = real_parse
        sys.argv = old_argv
    return captured


def test_t2v_defaults_match_the_official_5b_template():
    d = _defaults("t2v")
    assert d["fps"] == 24.0, "TI2V-5B is a 24fps model"
    assert d["shift"] == 8.0
    assert d["steps"] == 30
    assert d["cfg"] == 5.0


def test_i2v_defaults_match_the_a14b_family():
    d = _defaults("i2v")
    assert d["fps"] == 16.0, "A14B is a 16fps model; 24 plays it 1.5x fast"
    assert d["shift"] == 5.0, "A14B uses shift 5.0, not the 5B's 8.0"
    assert d["steps"] == 20
    assert d["cfg"] == 3.5


def test_frame0_fix_is_ON_by_default():
    """Flipped ON 2026-09-17 after verification on BOTH axes: frame count
    preserved (--length 25 -> 25; without the trim it was 29) AND the opening
    frame visually sharp at native resolution — eyes, hair strands, skin
    texture, legible background, indistinguishable from a mid-clip frame.
    It supersedes post-render substitution."""
    d = _defaults("s2v")
    assert d["frame0_fix"] is True, "verified on both axes; should default ON"
    assert d["pad_frames"] == 4, \
        "4 pixel frames per prepended latent frame for wan_2.1_vae (measured)"


def test_s2v_defaults_match_the_verified_render():
    """These are the values that produced the confirmed lip-synced clip."""
    d = _defaults("s2v")
    assert d["fps"] == 16.0
    assert d["steps"] == 20
    assert d["cfg"] == 6.0
    assert d["shift"] == 8.0
    assert d["gguf"] is False, "fp8 is the default; GGUF is ~2x slower measured"


def test_the_two_modes_do_not_share_defaults():
    """The actual regression guard: if someone re-merges the default block,
    these values collapse back together and this fails."""
    t, i = _defaults("t2v"), _defaults("i2v")
    assert t["fps"] != i["fps"]
    assert t["shift"] != i["shift"]
