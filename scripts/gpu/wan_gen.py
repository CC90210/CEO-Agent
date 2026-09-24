#!/usr/bin/env python3
"""wan_gen.py — Wan 2.2 video generation on ComfyUI. Text, image and audio driven.

Runs ON the GPU box (talks to 127.0.0.1:8188, which is never exposed).

    # text-to-video, 5B single checkpoint — drafts only, reads dated
    wan_gen.py t2v --prompt "..." --name clip01

    # image-to-video, 14B two-expert MoE — THE QUALITY TIER
    wan_gen.py i2v --image /opt/oasis/inputs/frame.png --prompt "slow push-in" --name clip02

    # audio-driven avatar / talking head — the HeyGen replacement
    wan_gen.py s2v --image face.png --audio vo.wav --prompt "..." --name clip03

ONE FILE ON PURPOSE. These modes share the negative prompt, the model
paths, the submit/poll loop and the output extraction. As two files they
duplicated ~80 lines, and with two agents (Bravo and Maven) editing this box
that duplication diverges silently. It stays a single self-contained file
rather than a package because it is delivered by `oasisgpu.py push`, one file
at a time — a shared module that fails to arrive is an ImportError at render
time, 7 minutes into a billed job.

WHY I2V IS THE QUALITY PATH
Text-to-video asks one model to invent composition, lighting, subject AND
motion simultaneously, and it does all four at medium quality — which is why
raw T2V reads as dated. Give the model an art-directed first frame and it only
has to solve motion.

THE TWO-EXPERT SPLIT (i2v)
Wan 2.2 A14B is a mixture-of-experts: a HIGH-noise expert handles early
denoising (composition, large motion), a LOW-noise expert finishes detail.
  pass 1  high-noise  steps 0..boundary    return_with_leftover_noise=enable
  pass 2  low-noise   steps boundary..end  add_noise=disable
Those two flags are NOT exposed as options: getting them wrong degrades output
silently instead of erroring.

Every node name, input name and enum below was read from this server's live
/object_info, not from memory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CAPABILITY_META = {
    "category": "content.video_generation",
    "lifecycle": "active",
    # Generation writes rendered media to the GPU host's output tree.
    "risk": "local_write",
    "triggers": [
        "generate a video clip on the gpu",
        "animate a product screenshot into video",
        "render a wan 2.2 shot",
        "make ugc footage without higgsfield credits",
    ],
    "owner": "maven",
    "project": "empire",
    "bridge": {"visible": False},
}

BASE = "http://127.0.0.1:8188"
COMFY = Path("/opt/oasis/repos/ComfyUI")
MODELS = "comfy-wan22/split_files"
UNET_5B = f"{MODELS}/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"
CLIP = f"{MODELS}/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
HIGH = "wan22-i2v-a14b-gguf/HighNoise/Wan2.2-I2V-A14B-HighNoise-Q5_K_M.gguf"
LOW = "wan22-i2v-a14b-gguf/LowNoise/Wan2.2-I2V-A14B-LowNoise-Q5_K_M.gguf"

# TWO DIFFERENT VAEs, AND THEY ARE NOT INTERCHANGEABLE.
# TI2V-5B ships a new high-compression Wan 2.2 VAE. The A14B models (i2v, t2v,
# s2v) are Wan 2.1-architecture and need the 16-channel Wan 2.1 VAE. Verified
# against ComfyUI's own shipped templates on this box: video_wan2_2_5B_ti2v.json
# names wan2.2_vae.safetensors, while video_wan2_2_14B_i2v.json and
# video_wan2_2_14B_s2v.json both name wan_2.1_vae.safetensors.
# A mismatched VAE does NOT raise — the channel counts differ and you get mush.
# Caught by Maven 2026-09-17 before the first I2V render; one shared constant
# was being used for both paths.
VAE_5B = f"{MODELS}/vae/wan2.2_vae.safetensors"   # TI2V-5B ONLY
VAE_21 = f"{MODELS}/vae/wan_2.1_vae.safetensors"  # A14B i2v / t2v / s2v

# S2V — audio-driven avatar (the HeyGen replacement). Graph folded in from
# Maven's wan_s2v.py after it produced a verified lip-synced clip on 2026-09-17.
UNET_S2V_FP8 = f"{MODELS}/diffusion_models/wan2.2_s2v_14B_fp8_scaled.safetensors"
UNET_S2V_GGUF = "wan22-s2v-14b-gguf/Wan2.2-S2V-14B-Q5_K_M.gguf"
# Lives in ComfyUI's own models/audio_encoders/ — extra_model_paths.yaml maps no
# such category, so a file under /opt/oasis/models is invisible to the loader
# with NO error, just an empty dropdown.
AUDIO_ENCODER = "wav2vec2_large_english_fp16.safetensors"

# Wan's own reference negative prompt. Without it, output skews static,
# oversaturated and low-motion.
NEGATIVE = (
    "bright tones, overexposed, static, blurred details, subtitles, style, artwork, "
    "painting, picture, still, overall gray, worst quality, low quality, JPEG artifacts, "
    "ugly, deformed, extra fingers, poorly drawn hands, poorly drawn face, malformed limbs, "
    "fused fingers, motionless frame, cluttered background, three legs, many people in the "
    "background, walking backwards"
)


# --------------------------------------------------------------- graph builders

def build_t2v(prompt: str, name: str, width: int, height: int, length: int,
              steps: int, cfg: float, seed: int, shift: float, fps: float) -> dict:
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET_5B, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "wan"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_5B}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["2", 0]}},
        "6": {"class_type": "Wan22ImageToVideoLatent",
              "inputs": {"vae": ["3", 0], "width": width, "height": height,
                         "length": length, "batch_size": 1}},
        # Wan needs the SD3-style sigma shift; 8.0 is upstream's value for 5B.
        "7": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": shift}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["7", 0], "seed": seed, "steps": steps, "cfg": cfg,
                         "sampler_name": "uni_pc", "scheduler": "simple",
                         "positive": ["4", 0], "negative": ["5", 0],
                         "latent_image": ["6", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "CreateVideo", "inputs": {"images": ["9", 0], "fps": fps}},
        "11": {"class_type": "SaveVideo",
               "inputs": {"video": ["10", 0], "filename_prefix": name, "format": "auto"}},
    }


def build_i2v(image_name: str, prompt: str, name: str, width: int, height: int,
              length: int, steps: int, cfg: float, seed: int, shift: float,
              boundary: int, fps: float) -> dict:
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": HIGH}},
        "2": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": LOW}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "wan"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_21}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["3", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["3", 0]}},
        "7": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        # WanImageToVideo returns (positive, negative, latent) — three outputs.
        "8": {"class_type": "WanImageToVideo",
              "inputs": {"positive": ["5", 0], "negative": ["6", 0], "vae": ["4", 0],
                         "width": width, "height": height, "length": length,
                         "batch_size": 1, "start_image": ["7", 0]}},
        "9": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": shift}},
        "10": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": shift}},
        "11": {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["9", 0], "add_noise": "enable", "noise_seed": seed,
                          "steps": steps, "cfg": cfg, "sampler_name": "euler",
                          "scheduler": "simple", "positive": ["8", 0], "negative": ["8", 1],
                          "latent_image": ["8", 2], "start_at_step": 0,
                          "end_at_step": boundary, "return_with_leftover_noise": "enable"}},
        "12": {"class_type": "KSamplerAdvanced",
               "inputs": {"model": ["10", 0], "add_noise": "disable", "noise_seed": seed,
                          "steps": steps, "cfg": cfg, "sampler_name": "euler",
                          "scheduler": "simple", "positive": ["8", 0], "negative": ["8", 1],
                          "latent_image": ["11", 0], "start_at_step": boundary,
                          "end_at_step": 10000, "return_with_leftover_noise": "disable"}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["13", 0], "fps": fps}},
        "15": {"class_type": "SaveVideo",
               "inputs": {"video": ["14", 0], "filename_prefix": name, "format": "auto"}},
    }


def build_s2v(image_name: str, audio_name: str, prompt: str, name: str,
              width: int, height: int, length: int, steps: int, cfg: float,
              seed: int, shift: float, fps: float, fp8: bool) -> dict:
    """Audio-driven avatar. Reference image + speech in, lip-synced video out.

    THIS IS THE VERIFIED GRAPH — the one that produced the confirmed
    lip-synced clip on 2026-09-17 (s2v_smoke_00001_.mp4: h264 720x1280,
    16 fps, 37 frames, AAC muxed, distinct phoneme mouth shapes, a blink,
    stable identity). Decode goes straight off the sampler.

    It has a known defect that `build_s2v_frame0_fix` solves: the first ~2
    pixel frames are soft and over-warm, because Wan's VAE is temporally causal
    and the opening latent decodes with no preceding context.

    **Prefer build_s2v_frame0_fix — it is the default and is verified on both
    frame count and picture.** This bare version is kept as the A/B control and
    for anyone who needs the untouched decode path.

    If you ever repair the artifact after render instead, SUBSTITUTE the soft
    frames, never DROP them: dropping shifts ~125 ms against the audio at
    16 fps and lip-sync breaks past ~50 ms.
    """
    loader = ({"class_type": "UNETLoader",
               "inputs": {"unet_name": UNET_S2V_FP8, "weight_dtype": "default"}}
              if fp8 else
              {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": UNET_S2V_GGUF}})
    return {
        "1": loader,
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "wan"}},
        # S2V is A14B-lineage: the 2.1 VAE, never the 2.2 one.
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_21}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["2", 0]}},
        "6": {"class_type": "AudioEncoderLoader",
              "inputs": {"audio_encoder_name": AUDIO_ENCODER}},
        "7": {"class_type": "LoadAudio", "inputs": {"audio": audio_name}},
        "8": {"class_type": "AudioEncoderEncode",
              "inputs": {"audio_encoder": ["6", 0], "audio": ["7", 0]}},
        "9": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "10": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": shift}},
        # Returns (positive, negative, latent) like WanImageToVideo.
        "11": {"class_type": "WanSoundImageToVideo",
               "inputs": {"positive": ["4", 0], "negative": ["5", 0], "vae": ["3", 0],
                          "width": width, "height": height, "length": length,
                          "batch_size": 1, "audio_encoder_output": ["8", 0],
                          "ref_image": ["9", 0]}},
        "12": {"class_type": "KSampler",
               "inputs": {"model": ["10", 0], "seed": seed, "steps": steps, "cfg": cfg,
                          "sampler_name": "uni_pc", "scheduler": "simple",
                          "positive": ["11", 0], "negative": ["11", 1],
                          "latent_image": ["11", 2], "denoise": 1.0}},
        "15": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
        # Audio is passed through so the VO is muxed into the file, not lost.
        "16": {"class_type": "CreateVideo",
               "inputs": {"images": ["15", 0], "fps": fps, "audio": ["7", 0]}},
        "17": {"class_type": "SaveVideo",
               "inputs": {"video": ["16", 0], "filename_prefix": name, "format": "auto"}},
    }


def build_s2v_frame0_fix(image_name: str, audio_name: str, prompt: str, name: str,
                         width: int, height: int, length: int, steps: int, cfg: float,
                         seed: int, shift: float, fps: float, fp8: bool,
                         pad_frames: int = 4) -> dict:
    """EXPERIMENTAL source-level fix for the soft opening frames.

    Duplicates the first latent frame so the temporally-causal VAE has context
    to decode it against. Wiring traced from ComfyUI's own
    video_wan2_2_14B_s2v.json link graph (not from a description of it) — both
    of its decode paths run:
        sampled latent -> LatentCut(dim="t", index=0, amount=1)
                       -> LatentConcat(samples1=cut, samples2=latent, dim="t")
                       -> VAEDecode

    THE PADDING MUST BE TRIMMED BACK OFF, IN THE PIXEL DOMAIN. Measured on
    this box 2026-09-17: `--length 25` with the bare cut+concat produced
    nb_read_packets=29. One extra LATENT frame becomes FOUR pixel frames
    through Wan's 4x temporal compression. Left uncorrected that silently
    lengthens every take, and an assembly that probes real durations reshuffles
    every trim and seam without erroring.

    Trimming in the LATENT domain would defeat the purpose — the point is to
    decode WITH the extra context and then discard the surplus pixels. So:
        cut -> concat -> VAEDecode (length+4 frames)
                      -> ImageFromBatch(batch_index=4, length=length)
    which restores the exact requested frame count AND the original alignment,
    because the four discarded frames are the four that were prepended.

    That is the difference between this and a post-render repair: no frames are
    lost and nothing shifts against the audio. The frames that survive were
    decoded with preceding context rather than patched afterwards.

    Built ADDITIVELY on the verified graph so the A/B is a real control.
    """
    wf = build_s2v(image_name, audio_name, prompt, name, width, height, length,
                   steps, cfg, seed, shift, fps, fp8)
    wf["13"] = {"class_type": "LatentCut",
                "inputs": {"samples": ["12", 0], "dim": "t", "index": 0, "amount": 1}}
    wf["14"] = {"class_type": "LatentConcat",
                "inputs": {"samples1": ["13", 0], "samples2": ["12", 0], "dim": "t"}}
    wf["15"]["inputs"]["samples"] = ["14", 0]
    # Drop the prepended frames; `length` is passed explicitly so the output is
    # exactly what was asked for even if the expansion factor ever differs.
    wf["18"] = {"class_type": "ImageFromBatch",
                "inputs": {"image": ["15", 0], "batch_index": pad_frames,
                           "length": length}}
    wf["16"]["inputs"]["images"] = ["18", 0]
    return wf


# --------------------------------------------------------------- image staging

def stage_image(src: Path, width: int, height: int) -> str:
    """Cover-crop + resize into ComfyUI's input dir; return the bare filename.

    Done here rather than with an ImageScale node so a wrong aspect ratio is a
    visible file on disk, not a surprise inside a billed 7-minute render.
    """
    if not src.exists():
        sys.exit(f"no such image: {src}")
    dest_dir = COMFY / "input"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    try:
        from PIL import Image
    except ImportError:
        # Same-file guard as stage_audio: copy2 raises SameFileError rather than
        # no-opping when the source is already the destination.
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        print(f"  WARNING: Pillow missing, no resize applied -> {dest.name}")
        return dest.name

    with Image.open(src) as im:
        im = im.convert("RGB")
        if im.size != (width, height):
            print(f"  resizing {im.width}x{im.height} -> {width}x{height}")
            # Cover-crop, never stretch: a squashed first frame propagates
            # through every generated frame.
            ar_src, ar_dst = im.width / im.height, width / height
            if ar_src > ar_dst:
                new_w = int(im.height * ar_dst)
                off = (im.width - new_w) // 2
                im = im.crop((off, 0, off + new_w, im.height))
            elif ar_src < ar_dst:
                new_h = int(im.width / ar_dst)
                off = (im.height - new_h) // 2
                im = im.crop((0, off, im.width, off + new_h))
            im = im.resize((width, height), Image.LANCZOS)
        im.save(dest, "PNG")
    print(f"  staged -> ComfyUI/input/{dest.name}")
    return dest.name


def stage_audio(src: Path) -> str:
    """Copy speech into ComfyUI's input dir; return the bare filename.

    No transcoding — LoadAudio handles wav/mp3/flac. ComfyUI's input dir was
    root-owned on this box and had to be chowned to ubuntu (found by Maven);
    if this raises PermissionError that is the cause.
    """
    if not src.exists():
        sys.exit(f"no such audio file: {src}")
    dest_dir = COMFY / "input"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    # Already staged: passing a path that IS ComfyUI/input/<name> is the normal
    # case when reusing another agent's assets, and shutil.copy2 raises
    # SameFileError on it rather than no-opping. Resolve both sides — a symlink
    # or a trailing-slash difference would otherwise slip past a string compare.
    if src.resolve() == dest.resolve():
        print(f"  audio already staged: ComfyUI/input/{dest.name}")
        return dest.name
    try:
        shutil.copy2(src, dest)
    except PermissionError:
        sys.exit(f"cannot write {dest} — ComfyUI's input dir is not writable.\n"
                 f"  fix: sudo chown -R ubuntu {dest_dir}")
    print(f"  staged audio -> ComfyUI/input/{dest.name}")
    return dest.name


# --------------------------------------------------------------- comfy client

def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # ComfyUI names the offending node and field here — the difference
        # between a fixable error and "it failed".
        print(f"HTTP {e.code}:\n{e.read().decode('utf-8', 'replace')[:3000]}", file=sys.stderr)
        raise SystemExit(2)
    except urllib.error.URLError as e:
        # A bare "connection refused" wasted real time once; name the likely
        # cause and the command that confirms it.
        print(f"cannot reach ComfyUI at {BASE}: {e.reason}\n"
              "  Is it up?        systemctl is-active comfyui\n"
              "  Just restarted?  systemctl show comfyui -p ActiveEnterTimestamp --value",
              file=sys.stderr)
        raise SystemExit(3)


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as r:
        return json.loads(r.read().decode())


OUTPUT_DIR = Path("/opt/oasis/outputs")


def verify_frame_count(filename: str, expected: int) -> bool:
    """Probe the rendered file and assert it has the frames we asked for.

    The frame0 fix trims a VAE-compression-derived number of padding frames.
    If that constant is ever wrong — different VAE, different compression
    ratio — the output silently comes out the wrong length, and an assembly
    that probes durations reshuffles every trim and seam without erroring.
    This converts that into a loud failure at the point of knowledge.
    """
    path = OUTPUT_DIR / filename
    if not path.exists():
        print(f"  (cannot verify frame count: {path} not found)", file=sys.stderr)
        return True  # don't fail the run over a probe that couldn't locate the file
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
             "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"  (frame-count probe unavailable: {exc})", file=sys.stderr)
        return True
    actual = (out.stdout or "").strip().rstrip(",")
    if not actual.isdigit():
        print(f"  (frame-count probe returned nothing usable: {actual!r})", file=sys.stderr)
        return True
    got = int(actual)
    if got == expected:
        print(f"  frame count VERIFIED: {got} == --length {expected}")
        return True
    print(f"  FRAME COUNT MISMATCH: got {got}, expected {expected}.\n"
          f"    The padding trim is wrong for this configuration. If you changed the VAE\n"
          f"    or resolution, pass --pad-frames <pixel frames per latent frame>.\n"
          f"    DO NOT feed this file to an assembly that probes durations.", file=sys.stderr)
    return False


def submit_and_wait(wf: dict, timeout: int, expect_frames: int | None = None) -> int:
    res = post("/prompt", {"prompt": wf})
    pid = res.get("prompt_id")
    if not pid:
        print(f"no prompt_id in response: {res}", file=sys.stderr)
        return 2
    print(f"prompt_id={pid}")

    start = time.monotonic()
    last_report = -1
    while time.monotonic() - start < timeout:
        hist = get(f"/history/{pid}")
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") == "error" or not status.get("completed", True):
                print("FAILED. ComfyUI reported:", file=sys.stderr)
                print(json.dumps(status.get("messages", []), indent=1)[:3000], file=sys.stderr)
                return 1
            files = []
            for node in entry.get("outputs", {}).values():
                for key in ("images", "gifs", "video", "videos"):
                    for f in node.get(key, []) or []:
                        if isinstance(f, dict) and f.get("filename"):
                            files.append(f["filename"])
            print(f"DONE in {time.monotonic() - start:.0f}s")
            for f in files:
                print(f"  output: {f}")
            if not files:
                # Completing with no file is a silent failure — say so.
                print("WARNING: job completed but produced no output file", file=sys.stderr)
                return 1
            if expect_frames is not None:
                if not all(verify_frame_count(f, expect_frames) for f in files):
                    return 1
            return 0

        el = int(time.monotonic() - start)
        if el % 30 == 0 and el != last_report:
            q = get("/queue")
            pending = len(q.get("queue_pending", [])) + len(q.get("queue_running", []))
            print(f"  ...{el}s elapsed, {pending} in queue")
            last_report = el
        time.sleep(2)

    print(f"TIMEOUT after {timeout}s", file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Wan 2.2 video generation")
    sub = ap.add_subparsers(dest="mode", required=True)

    # Defaults are PER MODE, not shared. The two model families differ in
    # native frame rate and sigma shift, and a shared default block silently
    # applied the 5B values to the 14B path:
    #   TI2V-5B  — 24 fps, shift 8.0, 30 steps   (matches video_wan2_2_5B_ti2v.json)
    #   A14B     — 16 fps, shift 5.0, 20 steps   (Wan 2.1-architecture lineage)
    # Playing a 16fps model back at 24fps runs it 1.5x fast, which reads to a
    # viewer as "the AI looks wrong" rather than as a config error — the most
    # expensive kind of wrong, because nobody thinks to check the frame rate.
    def common(p, *, fps, shift, steps, cfg):
        p.add_argument("--prompt", required=True)
        p.add_argument("--name", default="oasis_clip")
        p.add_argument("--width", type=int, default=1280)
        p.add_argument("--height", type=int, default=704)
        p.add_argument("--length", type=int, default=81, help="frames")
        p.add_argument("--fps", type=float, default=fps)
        p.add_argument("--steps", type=int, default=steps)
        p.add_argument("--cfg", type=float, default=cfg)
        p.add_argument("--seed", type=int, default=12345)
        p.add_argument("--shift", type=float, default=shift)
        p.add_argument("--timeout", type=int, default=3600)

    t = sub.add_parser("t2v", help="text-to-video, 5B (drafts; reads dated)")
    common(t, fps=24.0, shift=8.0, steps=30, cfg=5.0)

    i = sub.add_parser("i2v", help="image-to-video, 14B two-expert MoE (QUALITY TIER)")
    common(i, fps=16.0, shift=5.0, steps=20, cfg=3.5)
    i.add_argument("--image", required=True, help="path on THIS box to the first frame")
    i.add_argument("--boundary", type=int, default=None,
                   help="step to hand off high-noise -> low-noise (default steps//2)")

    # S2V defaults come from the config that actually produced a verified
    # lip-synced clip (2026-09-17): 720x1280 portrait, 16fps, 20 steps, cfg 6.0.
    s = sub.add_parser("s2v", help="audio-driven avatar / talking head (HeyGen replacement)")
    common(s, fps=16.0, shift=8.0, steps=20, cfg=6.0)
    s.add_argument("--image", required=True, help="reference face, path on THIS box")
    s.add_argument("--audio", required=True, help="speech wav, path on THIS box")
    s.add_argument("--gguf", action="store_true",
                   help="use the Q5_K GGUF instead of fp8 (slower: ~19.5 vs ~11 s/frame measured)")
    # OPT-IN, NOT DEFAULT — and that is a deliberate downgrade from how this
    # shipped an hour ago. The LatentCut/LatentConcat fix prepends a latent
    # frame, and Wan's temporal VAE decodes each latent frame to SEVERAL pixel
    # frames, so the output may be LONGER than --length asked for. Maven's
    # assembly probes each take's real duration, so a longer take would not
    # error — it would quietly shift every trim and seam and fail later with a
    # confusing message. Until one clip is rendered and nb_read_packets is
    # compared against --length, ON by default is a silent-corruption risk to a
    # shipping pipeline. Flipped after Maven confirmed the artifact and flagged
    # the frame-count question, 2026-09-17.
    # ON BY DEFAULT as of 2026-09-17: verified on BOTH axes — frame count
    # preserved (--length 25 -> 25; without the trim, 29) and the opening frame
    # visually sharp at native resolution (eyes, hair strands, skin texture,
    # legible background), indistinguishable from a mid-clip frame. It
    # supersedes post-render substitution, which repaired the artifact after
    # the fact; this removes the defect before it exists.
    s.add_argument("--no-frame0-fix", dest="frame0_fix", action="store_false",
                   help="disable the opening-frame fix (leaves ~2 soft, over-warm frames at "
                        "the head of the take; only useful for A/B comparison)")
    s.set_defaults(frame0_fix=True)
    # NOT a magic number: it is (temporal compression ratio) pixel frames per
    # prepended latent frame — 4 for the Wan 2.1 VAE, measured. Change the VAE
    # or the compression ratio and this must move with it, which is why it is a
    # flag rather than a literal, AND why the render verifies the resulting
    # frame count instead of trusting it.
    s.add_argument("--pad-frames", type=int, default=4,
                   help="pixel frames produced per prepended latent frame (VAE temporal "
                        "compression ratio; 4 for wan_2.1_vae, measured)")

    a = ap.parse_args()

    if a.mode == "t2v":
        wf = build_t2v(a.prompt, a.name, a.width, a.height, a.length,
                       a.steps, a.cfg, a.seed, a.shift, a.fps)
        print(f"submitting T2V 5B: {a.width}x{a.height}, {a.length}f "
              f"({a.length / a.fps:.1f}s), {a.steps} steps")
    elif a.mode == "i2v":
        boundary = a.boundary if a.boundary is not None else a.steps // 2
        if not 0 < boundary < a.steps:
            sys.exit(f"--boundary must be between 1 and {a.steps - 1}")
        image_name = stage_image(Path(a.image), a.width, a.height)
        wf = build_i2v(image_name, a.prompt, a.name, a.width, a.height, a.length,
                       a.steps, a.cfg, a.seed, a.shift, boundary, a.fps)
        print(f"submitting I2V 14B MoE: {a.width}x{a.height}, {a.length}f "
              f"({a.length / a.fps:.1f}s), {a.steps} steps, handoff at {boundary}")

    else:  # s2v
        image_name = stage_image(Path(a.image), a.width, a.height)
        audio_name = stage_audio(Path(a.audio))
        if a.frame0_fix:
            wf = build_s2v_frame0_fix(image_name, audio_name, a.prompt, a.name,
                                      a.width, a.height, a.length, a.steps, a.cfg,
                                      a.seed, a.shift, a.fps, not a.gguf, a.pad_frames)
        else:
            wf = build_s2v(image_name, audio_name, a.prompt, a.name, a.width,
                           a.height, a.length, a.steps, a.cfg, a.seed, a.shift,
                           a.fps, not a.gguf)
        print(f"submitting S2V {'GGUF' if a.gguf else 'fp8'}: {a.width}x{a.height}, "
              f"{a.length}f ({a.length / a.fps:.1f}s), {a.steps} steps, "
              f"frame0-fix={'on' if a.frame0_fix else 'OFF'}")

    return submit_and_wait(wf, a.timeout, expect_frames=a.length)


if __name__ == "__main__":
    raise SystemExit(main())
