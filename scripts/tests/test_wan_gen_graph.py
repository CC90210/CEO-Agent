"""Guard the ComfyUI workflow graphs in scripts/gpu/wan_gen.py.

The t2v graph here is the one that ACTUALLY RENDERED on MavenGPU on
2026-09-17 (oasis_smoke_00001_.mp4 — h264, 832x480, 49 frames, 82 seconds).
wan_gen.py was created by merging wan_t2v.py and wan_i2v.py to kill ~80 lines
of duplication, and this pins the merge: if the graph drifts from the shape
that is known to work, these tests fail rather than a billed 7-minute render.

The i2v assertions cover the mixture-of-experts wiring, where a wrong flag
DEGRADES OUTPUT SILENTLY instead of raising — the failure mode a human would
not notice until a client saw the clip.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WAN_GEN = REPO_ROOT / "scripts" / "gpu" / "wan_gen.py"


def _load():
    spec = importlib.util.spec_from_file_location("wan_gen", WAN_GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def wan():
    assert WAN_GEN.exists(), f"missing {WAN_GEN}"
    return _load()


# ----------------------------------------------------------------- t2v

def test_t2v_graph_matches_the_render_that_worked(wan):
    """Byte-for-byte pin of the proven smoke-test graph."""
    g = wan.build_t2v(prompt="a test prompt", name="oasis_smoke",
                      width=832, height=480, length=49,
                      steps=20, cfg=5.0, seed=12345, shift=8.0, fps=24.0)

    assert g["1"]["class_type"] == "UNETLoader"
    assert g["1"]["inputs"]["unet_name"].endswith("wan2.2_ti2v_5B_fp16.safetensors"), \
        "must use the ComfyUI-REPACKAGED single file; the Wan-AI sharded " \
        "diffusers weights cannot be opened by UNETLoader"
    assert g["2"]["inputs"]["type"] == "wan", "CLIPLoader type must be 'wan'"
    assert g["8"]["class_type"] == "KSampler"
    assert g["8"]["inputs"]["sampler_name"] == "uni_pc"
    assert g["8"]["inputs"]["scheduler"] == "simple"
    assert g["8"]["inputs"]["steps"] == 20
    assert g["7"]["class_type"] == "ModelSamplingSD3", "Wan needs the sigma shift node"
    assert g["7"]["inputs"]["shift"] == 8.0
    assert g["6"]["inputs"]["length"] == 49
    assert g["11"]["class_type"] == "SaveVideo"
    assert g["11"]["inputs"]["filename_prefix"] == "oasis_smoke"


def test_t2v_negative_prompt_is_wired_to_the_negative_input(wan):
    """A negative prompt that exists but is not connected does nothing."""
    g = wan.build_t2v("p", "n", 832, 480, 49, 20, 5.0, 1, 8.0, 24.0)
    neg_node = g["8"]["inputs"]["negative"][0]
    assert g[neg_node]["inputs"]["text"] == wan.NEGATIVE
    pos_node = g["8"]["inputs"]["positive"][0]
    assert g[pos_node]["inputs"]["text"] == "p"


# ----------------------------------------------------------------- i2v

def test_i2v_uses_both_moe_experts(wan):
    g = wan.build_i2v("f.png", "p", "n", 1280, 704, 81, 30, 3.5, 1, 8.0, 15, 24.0)
    unets = {n["inputs"]["unet_name"] for n in g.values()
             if n["class_type"] == "UnetLoaderGGUF"}
    assert len(unets) == 2, "the A14B MoE needs BOTH experts loaded"
    assert any("HighNoise" in u for u in unets)
    assert any("LowNoise" in u for u in unets)


def test_i2v_expert_handoff_flags_are_exact(wan):
    """These four flags silently degrade output when wrong. Pin them."""
    g = wan.build_i2v("f.png", "p", "n", 1280, 704, 81, 30, 3.5, 1, 8.0, 15, 24.0)
    high, low = g["11"]["inputs"], g["12"]["inputs"]

    assert high["add_noise"] == "enable"
    assert high["start_at_step"] == 0
    assert high["end_at_step"] == 15
    assert high["return_with_leftover_noise"] == "enable", \
        "high-noise pass MUST leave noise for the low-noise pass to finish"

    assert low["add_noise"] == "disable", \
        "low-noise pass must NOT re-noise the latent it was handed"
    assert low["start_at_step"] == 15, "low-noise must resume exactly at the boundary"
    assert low["return_with_leftover_noise"] == "disable"


def test_i2v_latent_chains_high_into_low(wan):
    """The second pass must consume the FIRST pass's latent, not a fresh one."""
    g = wan.build_i2v("f.png", "p", "n", 1280, 704, 81, 30, 3.5, 1, 8.0, 15, 24.0)
    assert g["11"]["inputs"]["latent_image"] == ["8", 2], \
        "high-noise pass takes WanImageToVideo's third output (the latent)"
    assert g["12"]["inputs"]["latent_image"] == ["11", 0], \
        "low-noise pass must chain from the high-noise pass"


def test_i2v_conditioning_comes_from_wanimagetovideo_not_raw_encode(wan):
    """WanImageToVideo REWRITES the conditioning; using the raw encode drops
    the reference image and silently produces a text-to-video result."""
    g = wan.build_i2v("f.png", "p", "n", 1280, 704, 81, 30, 3.5, 1, 8.0, 15, 24.0)
    for sampler in ("11", "12"):
        assert g[sampler]["inputs"]["positive"] == ["8", 0]
        assert g[sampler]["inputs"]["negative"] == ["8", 1]


def test_the_two_vaes_are_not_interchangeable(wan):
    """THE defect Maven caught before the first I2V render.

    TI2V-5B ships a new high-compression Wan 2.2 VAE; the A14B models are Wan
    2.1-architecture and need the 16-channel 2.1 VAE. Verified against
    ComfyUI's own shipped templates. A mismatch does NOT raise — the latent
    channel counts differ and the render silently produces mush.
    """
    t2v = wan.build_t2v("p", "n", 832, 480, 49, 20, 5.0, 1, 8.0, 24.0)
    i2v = wan.build_i2v("f.png", "p", "n", 1280, 704, 81, 20, 3.5, 1, 5.0, 10, 16.0)

    t2v_vae = t2v["3"]["inputs"]["vae_name"]
    i2v_vae = i2v["4"]["inputs"]["vae_name"]

    assert t2v_vae.endswith("wan2.2_vae.safetensors"), \
        f"TI2V-5B must use the 2.2 VAE, got {t2v_vae}"
    assert i2v_vae.endswith("wan_2.1_vae.safetensors"), \
        f"A14B i2v must use the 2.1 VAE, got {i2v_vae}"
    assert t2v_vae != i2v_vae, "a single shared VAE constant is the bug this pins"


def test_i2v_decode_uses_the_same_vae_it_encoded_with(wan):
    """Encoding with one VAE and decoding with another is the same class of
    silent corruption, one step later."""
    i2v = wan.build_i2v("f.png", "p", "n", 1280, 704, 81, 20, 3.5, 1, 5.0, 10, 16.0)
    encode_vae_node = i2v["8"]["inputs"]["vae"][0]
    decode_vae_node = i2v["13"]["inputs"]["vae"][0]
    assert encode_vae_node == decode_vae_node


def test_i2v_start_image_is_connected(wan):
    g = wan.build_i2v("frame.png", "p", "n", 1280, 704, 81, 30, 3.5, 1, 8.0, 15, 24.0)
    assert g["8"]["inputs"]["start_image"] == ["7", 0]
    assert g["7"]["inputs"]["image"] == "frame.png"


def test_both_modes_emit_a_video_file(wan):
    for g in (wan.build_t2v("p", "n", 832, 480, 49, 20, 5.0, 1, 8.0, 24.0),
              wan.build_i2v("f.png", "p", "n", 1280, 704, 81, 30, 3.5, 1, 8.0, 15, 24.0)):
        savers = [n for n in g.values() if n["class_type"] == "SaveVideo"]
        assert len(savers) == 1, "exactly one SaveVideo, or nothing lands on disk"


# ----------------------------------------------------------------- s2v

# ONE arg set, two builders. Duplicating the defaults would let the A/B arms
# drift apart in the FIXTURE — precisely the failure the A/B exists to rule out.
S2V_ARGS = dict(image_name="face.png", audio_name="vo.wav", prompt="p", name="n",
                width=720, height=1280, length=37, steps=20, cfg=6.0, seed=1,
                shift=8.0, fps=16.0, fp8=True)


def _s2v(wan, **kw):
    """The VERIFIED graph — what produced the confirmed lip-synced clip."""
    return wan.build_s2v(**{**S2V_ARGS, **kw})


def _s2v_fixed(wan, **kw):
    """The EXPERIMENTAL frame-0 variant (cut + concat + pixel trim)."""
    return wan.build_s2v_frame0_fix(**{**S2V_ARGS, **kw})


def test_s2v_uses_the_21_vae_not_the_22(wan):
    """S2V is A14B-lineage. The 2.2 VAE silently produces mush here."""
    g = _s2v(wan)
    assert g["3"]["inputs"]["vae_name"].endswith("wan_2.1_vae.safetensors")


def test_s2v_frame0_fix_matches_the_official_template_wiring(wan):
    """Traced from ComfyUI's video_wan2_2_14B_s2v.json:
         sampled -> LatentCut(dim=t, index=0, amount=1)
                 -> LatentConcat(samples1=cut, samples2=sampled, dim=t)
                 -> VAEDecode
    Wan's VAE is temporally causal, so latent frame 0 decodes with no
    preceding context and smears."""
    g = _s2v_fixed(wan)
    cut = g["13"]
    assert cut["class_type"] == "LatentCut"
    assert cut["inputs"]["dim"] == "t"
    assert cut["inputs"]["index"] == 0
    assert cut["inputs"]["amount"] == 1
    assert cut["inputs"]["samples"] == ["12", 0], "must cut from the SAMPLER output"

    cat = g["14"]
    assert cat["class_type"] == "LatentConcat"
    assert cat["inputs"]["dim"] == "t"
    assert cat["inputs"]["samples1"] == ["13", 0], "duplicated frame goes FIRST"
    assert cat["inputs"]["samples2"] == ["12", 0], "then the full sampled latent"

    assert g["15"]["inputs"]["samples"] == ["14", 0], \
        "VAEDecode must consume the padded latent, not the raw sampler output"


def test_default_s2v_graph_has_no_latent_duplication(wan):
    """The DEFAULT is the graph that produced the verified clip. If the
    experimental nodes leak into it, every take silently changes length."""
    off = _s2v(wan)
    assert "13" not in off and "14" not in off
    assert off["15"]["inputs"]["samples"] == ["12", 0]
    assert not [n for n in off.values()
                if n["class_type"] in ("LatentCut", "LatentConcat")]


def test_the_frame0_ab_differs_ONLY_in_the_inserted_nodes(wan):
    """An A/B whose arms drift apart measures the drift, not the fix.

    The experimental graph is built additively on the verified one, so the two
    must be identical except for the two inserted nodes and the one rewired
    VAEDecode input. If anything else differs, the comparison is worthless.
    """
    base, fixed = _s2v(wan), _s2v_fixed(wan)

    assert set(fixed) - set(base) == {"13", "14", "18"}, "only the fix nodes may be added"
    assert not set(base) - set(fixed), "the fix must not REMOVE nodes"

    differing = sorted(k for k in base if base[k] != fixed.get(k))
    assert differing == ["15", "16"], \
        f"only VAEDecode and CreateVideo should be rewired, but these differ: {differing}"

    assert base["15"]["inputs"]["samples"] == ["12", 0], "default decodes off the sampler"
    assert fixed["15"]["inputs"]["samples"] == ["14", 0], "fixed decodes off the concat"


def test_s2v_audio_is_muxed_into_the_output(wan):
    """A talking head with no audio track is a silent clip nobody notices
    until playback."""
    g = _s2v(wan)
    assert g["16"]["inputs"].get("audio") == ["7", 0], \
        "CreateVideo must receive the LoadAudio output"
    assert g["8"]["inputs"]["audio"] == ["7", 0], "same source drives the encoder"


def test_s2v_conditioning_comes_from_wansoundimagetovideo(wan):
    g = _s2v(wan)
    assert g["12"]["inputs"]["positive"] == ["11", 0]
    assert g["12"]["inputs"]["negative"] == ["11", 1]
    assert g["12"]["inputs"]["latent_image"] == ["11", 2]
    assert g["11"]["inputs"]["ref_image"] == ["9", 0]
    assert g["11"]["inputs"]["audio_encoder_output"] == ["8", 0]


def test_s2v_gguf_and_fp8_select_different_loaders(wan):
    fp8 = _s2v(wan, fp8=True)
    gguf = _s2v(wan, fp8=False)
    assert fp8["1"]["class_type"] == "UNETLoader"
    assert gguf["1"]["class_type"] == "UnetLoaderGGUF"


def test_every_node_reference_resolves(wan):
    """An input pointing at a node id that does not exist is a 400 from
    ComfyUI after the job is queued — catch it here instead."""
    for label, g in (("t2v", wan.build_t2v("p", "n", 832, 480, 49, 20, 5.0, 1, 8.0, 24.0)),
                     ("i2v", wan.build_i2v("f.png", "p", "n", 1280, 704, 81, 30, 3.5, 1, 8.0, 15, 24.0)),
                     ("s2v", _s2v(wan)),
                     ("s2v_frame0fix", _s2v_fixed(wan))):
        for node_id, node in g.items():
            for field, val in node["inputs"].items():
                if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
                    assert val[0] in g, \
                        f"{label}: node {node_id}.{field} references missing node {val[0]}"


def test_frame0_fix_trims_the_padding_back_off(wan):
    """MEASURED: the bare cut+concat turned --length 25 into 29 frames, because
    one prepended LATENT frame becomes four PIXEL frames. Without the trim the
    fix silently lengthens every take. The trim must be in the pixel domain —
    trimming latents would discard the very context the fix adds."""
    g = _s2v_fixed(wan, length=25)

    trim = g["18"]
    assert trim["class_type"] == "ImageFromBatch"
    assert trim["inputs"]["image"] == ["15", 0], "must trim the DECODED frames"
    assert trim["inputs"]["batch_index"] == 4, "drop the 4 prepended pixel frames"
    assert trim["inputs"]["length"] == 25, "output exactly what was requested"

    assert g["16"]["inputs"]["images"] == ["18", 0],         "CreateVideo must consume the TRIMMED frames, not the padded decode"
    assert _s2v(wan, length=25)["16"]["inputs"]["images"] == ["15", 0],         "the default path has no trim and must decode straight through"


def test_frame0_fix_requested_length_flows_to_the_trim(wan):
    """A hardcoded trim length would silently truncate longer takes."""
    for n in (25, 49, 81):
        assert _s2v_fixed(wan, length=n)["18"]["inputs"]["length"] == n
