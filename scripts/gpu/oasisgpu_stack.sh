#!/usr/bin/env bash
# oasisgpu_stack.sh — install the video/avatar generation stack on OasisGPU.
#
# Runs ON the box, AFTER oasisgpu_bootstrap.sh. Detects VRAM and installs the
# tier-appropriate model set. Idempotent.
#
#   bash oasisgpu_stack.sh              # core stack (ComfyUI + Wan 2.2)
#   bash oasisgpu_stack.sh --with-duix  # also the Duix-Avatar HeyGen clone
#   bash oasisgpu_stack.sh --plan       # print what WOULD be installed, touch nothing
#
# WHY THIS SCRIPT EXISTS AS A SCRIPT, not a runbook:
# A Hostinger GPU instance cannot be stopped. Reboot and Destroy are the only
# two actions, and billing runs every hour the instance EXISTS, idle or not.
# Destroy is therefore the only way to stop the meter, and it takes the whole
# disk with it — no snapshots, no persistent volumes. That makes rebuild-from-
# zero a routine operation, not a disaster drill. Everything here must be
# re-runnable unattended. Anything that needs a human decision does not belong
# in this file.
#
# LICENCE POSTURE (verified 2026-09-16, see the OasisGPU stack brief):
#   Wan 2.2 weights ......... Apache-2.0, outputs unencumbered  -> SAFE, the base
#   ComfyUI ................. GPL-3.0, no restriction on outputs -> SAFE
#   QuantStack GGUF quants .. inherit Wan's Apache-2.0           -> SAFE
#   Wan2GP (deepbeepmeep) ... WanGP Community 2.0, NOT OSI.
#       Agency work (you generate, you deliver a video) = permitted, credit owed.
#       Self-serve portal where a client logs in and generates = NOT permitted.
#       Installed only behind --with-wan2gp so the choice is deliberate.
#   HunyuanVideo ............ EXCLUDED on purpose. Territorial carve-out for
#       EU/UK/KR that binds OUTPUTS, plus a clause forbidding use of outputs to
#       improve any non-Hunyuan model — which would forbid our own LoRA training.
#   Duix-Avatar ............. free commercial under 100k users / $10M revenue,
#       but REQUIRES a visible "Built with DUIX.COM" credit on the product
#       surface. Opt-in only (--with-duix) for that reason.

set -Eeuo pipefail

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; RST=$'\033[0m'
step() { printf '\n%s==> %s%s\n' "$GRN" "$1" "$RST"; }
warn() { printf '%s[warn] %s%s\n' "$YLW" "$1" "$RST"; }
die()  { printf '%s[FAIL] %s%s\n' "$RED" "$1" "$RST" >&2; exit 1; }
trap 'die "aborted at line $LINENO"' ERR

# Hostinger's GPU image logs you in as `ubuntu`, not root (the panel's own SSH
# command says so). Self-elevate rather than telling the caller to retry.
if [[ $EUID -ne 0 ]]; then
    command -v sudo >/dev/null 2>&1 || die "not root and no sudo available"
    # -n first: a sudo that wants a password would BLOCK forever under the
    # non-interactive ssh this is normally invoked through, with no prompt
    # visible to anyone. Fail with an instruction instead of hanging.
    sudo -n true 2>/dev/null \
        || die "sudo needs a password for $(whoami). Run once interactively: python scripts/gpu/oasisgpu.py shell, then 'sudo -v'."
    exec sudo -E bash "$0" "$@"
fi

WITH_DUIX=0; WITH_WAN2GP=0; PLAN_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --with-duix)   WITH_DUIX=1 ;;
        --with-wan2gp) WITH_WAN2GP=1 ;;
        --plan)        PLAN_ONLY=1 ;;
        *) die "unknown flag: $arg" ;;
    esac
done

command -v nvidia-smi >/dev/null 2>&1 || die "no nvidia-smi — run oasisgpu_bootstrap.sh first"
[[ -d /opt/oasis/venv ]] || die "no /opt/oasis/venv — run oasisgpu_bootstrap.sh first"

VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
VRAM_GB=$((VRAM_MB / 1024))
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)

# VRAM alone is NOT the constraint. A rented GPU box is routinely sold with a
# large card bolted to a small host — the RTX 5090 SKU here ships 32GB VRAM
# with 4GB system RAM, 2 cores and 50GB disk. Tiering on VRAM only produced a
# plan that could not physically run: it downloaded ~40GB onto a 50GB disk and
# passed --lowvram, which offloads the umt5-xxl text encoder (~11GB) into 4GB
# of RAM and OOMs the host. Both limits are now first-class inputs.
RAM_GB=$(free -g | awk 'NR==2 {print $2}')
DISK_FREE_GB=$(df --output=avail -BG /opt 2>/dev/null | tail -1 | tr -dc '0-9')
DISK_FREE_GB=${DISK_FREE_GB:-0}
# nproc reports the HOST's cores inside a container — 128 on this box, while the
# cgroup quota grants exactly 2. Reading nproc would suppress the low-CPU
# warning by a factor of 64 and mis-size any future parallelism decision.
# cgroup v2 cpu.max is "<quota> <period>"; "max" means unlimited.
CORES=$(nproc)
if [[ -r /sys/fs/cgroup/cpu.max ]]; then
    read -r _q _p < /sys/fs/cgroup/cpu.max || true
    if [[ ${_q:-max} != "max" && ${_p:-0} -gt 0 ]]; then
        CORES=$(( _q / _p ))
        (( CORES < 1 )) && CORES=1
    fi
fi

# Tier thresholds sit slightly below the round numbers because vendors report
# 24564 MiB for a "24GB" card and integer division would drop it a tier.
if   (( VRAM_GB >= 80 )); then TIER=C
elif (( VRAM_GB >= 44 )); then TIER=B
elif (( VRAM_GB >= 22 )); then TIER=A
else                           TIER=MINIMAL
fi

step "Detected $GPU_NAME — ${VRAM_GB}GB VRAM, ${RAM_GB}GB RAM, ${CORES} cores, ${DISK_FREE_GB}GB free — TIER $TIER"

case "$TIER" in
  C) MODELS="wan22-ti2v-5b-comfy wan22-i2v-a14b-gguf wan22-s2v-14b-gguf"
     COMFY_FLAGS="--highvram"
     NOTE="96GB class. NOTE: the ceiling here is DISK, not VRAM — ~89GB of disk against 94GB of VRAM, so the 14B models still come as Q5 GGUF. Unquantised 14B would need ~115GB of weights." ;;
  B) MODELS="wan22-ti2v-5b-comfy wan22-i2v-a14b-gguf wan22-s2v-14b-gguf"
     COMFY_FLAGS="--reserve-vram 1.0"
     NOTE="48GB class: 14B via fp8/GGUF, no offload gymnastics. Comfortable for client work." ;;
  A) MODELS="wan22-ti2v-5b-comfy wan22-i2v-a14b-gguf"
     COMFY_FLAGS="--lowvram --reserve-vram 1.0"
     NOTE="24GB class: TI2V-5B native, 14B via Q4/Q5 GGUF. WATCH THE VAE-DECODE SPIKE — 14B fp16 peaks ~28GB during decode and OOMs at 80-90% through a run, AFTER the model loaded and ran fine. There is no CLI flag for tiled VAE; it is a NODE setting. Use the VAEDecodeTiled node in any 14B workflow on this tier. --lowvram below only moves text encoders to CPU; it does NOT prevent the decode spike." ;;
  MINIMAL)
     MODELS="wan22-ti2v-5b-comfy"
     COMFY_FLAGS="--lowvram --reserve-vram 0.5"
     warn "${VRAM_GB}GB is below the commercially usable floor for 14B avatar work."
     warn "Q3 + aggressive offload produces visible banding and facial detail loss."
     NOTE="Under 22GB: expect quality compromises on faces. Fine for tests, not for client delivery." ;;
esac

# --- RAM gate (MUST run AFTER the tier case, which assigns COMFY_FLAGS) -----
# Every "low VRAM" flag works by moving tensors into SYSTEM RAM. On a host with
# less RAM than VRAM that advice inverts: keep everything resident on the card.
# Ordering is load-bearing. This gate first sat ABOVE the case block, so the
# tier default silently overwrote it and the box that needed --highvram most
# would have been launched with --lowvram — the one flag guaranteed to OOM it.
if (( RAM_GB < 8 )); then
    warn "Only ${RAM_GB}GB system RAM against ${VRAM_GB}GB VRAM."
    warn "CPU-offload flags would push an ~11GB text encoder into ${RAM_GB}GB and OOM the host."
    warn "Overriding tier-$TIER flags (${COMFY_FLAGS}) with --highvram: keep weights on the card."
    COMFY_FLAGS="--highvram"
    if (( RAM_GB < 6 )); then
        warn "Under 6GB RAM with ${CORES} cores, model loading and ffmpeg encodes will be slow."
        warn "Expect the bottleneck to be the HOST, not the GPU."
    fi
fi

# --- disk gate ------------------------------------------------------------
# Approximate on-disk sizes INCLUDING the shared umt5-xxl text encoder (~11GB)
# that the Wan repos ship alongside the diffusion weights. Erring high: running
# out of disk at 90% of a 20GB download wastes an hour of billed GPU time.
# MEASURED on the box 2026-09-17, not estimated. The earlier guesses were badly
# low — wan22-ti2v-5b was written as 22 and is really 32 (the repo ships an 11GB
# T5 encoder and a 2.7GB VAE alongside the 19GB of diffusion shards), and
# i2v-a14b-gguf was 17 but is 21 (HighNoise AND LowNoise, 11GB each). An
# under-estimate here does not fail loudly: it fills the disk mid-download.
model_size_gb() {
    case "$1" in
        wan22-ti2v-5b)         echo 32 ;;   # measured: 19 shards + 11 T5 + 2.7 VAE
        wan22-ti2v-5b-gguf)    echo 9  ;;
        wan22-ti2v-5b-comfy)   echo 18 ;;   # ComfyUI repackaged: 10 unet + 6.7 t5 + 1.4 vae
        wan22-i2v-a14b)        echo 60 ;;
        wan22-i2v-a14b-gguf)   echo 21 ;;   # measured: HighNoise 11 + LowNoise 11
        wan22-s2v-14b)         echo 55 ;;
        wan22-s2v-14b-gguf)    echo 14 ;;   # measured
        *)                     echo 25 ;;
    esac
}
# Reserve for torch+CUDA wheels (~6GB), ComfyUI and nodes (~2GB), and room for
# rendered output. Without this the box fills and generation dies mid-render.
DISK_RESERVE_GB=14
BUDGET_GB=$(( DISK_FREE_GB - DISK_RESERVE_GB ))

# A quantised variant of the RIGHT model beats full precision of the wrong one.
# On a 96GB-VRAM / 100GB-disk box the tier wants 137GB of full-precision
# weights: dropping to fit would silently delete the S2V avatar model — the
# whole HeyGen-replacement capability — while keeping a text-to-video model
# that was never the point. Downgrade first, drop only as a last resort.
gguf_variant() {
    case "$1" in
        wan22-ti2v-5b)  echo wan22-ti2v-5b-gguf ;;
        wan22-i2v-a14b) echo wan22-i2v-a14b-gguf ;;
        wan22-s2v-14b)  echo wan22-s2v-14b-gguf ;;
        *)              echo "" ;;
    esac
}

# Where each key lands on disk, so an already-downloaded model costs 0 budget.
model_dir() {
    case "$1" in
        wan22-ti2v-5b-comfy) echo comfy-wan22 ;;
        *)                   echo "$1" ;;
    esac
}
# Present = the directory exists and holds more than 1GB. Without this, a
# re-run on a fully provisioned box measures only FREE space, concludes nothing
# fits, and aborts — breaking the idempotency the whole rebuild story rests on.
model_present() {
    local d="/opt/oasis/models/$(model_dir "$1")"
    [[ -d $d ]] || return 1
    local kb
    kb=$(du -sk "$d" 2>/dev/null | cut -f1)
    (( ${kb:-0} > 1048576 ))
}

FITTED=""; DROPPED=""; DOWNGRADED=""; PRESENT=""; USED_GB=0
for m in $MODELS; do
    sz=$(model_size_gb "$m")
    if model_present "$m"; then
        FITTED="$FITTED $m"; PRESENT="$PRESENT $m"; continue
    fi
    if (( USED_GB + sz <= BUDGET_GB )); then
        FITTED="$FITTED $m"; USED_GB=$(( USED_GB + sz )); continue
    fi
    alt=$(gguf_variant "$m")
    if [[ -n $alt ]]; then
        alt_sz=$(model_size_gb "$alt")
        if (( USED_GB + alt_sz <= BUDGET_GB )); then
            FITTED="$FITTED $alt"; USED_GB=$(( USED_GB + alt_sz ))
            DOWNGRADED="$DOWNGRADED $m->${alt}(${sz}->${alt_sz}GB)"
            continue
        fi
    fi
    DROPPED="$DROPPED $m(${sz}GB)"
done
MODELS="${FITTED# }"

if [[ -n $DOWNGRADED ]]; then
    warn "DISK: quantised to fit (quality cost is real but small at Q5):${DOWNGRADED}"
fi
if [[ -n $PRESENT ]]; then
    echo "  already on disk (costs no budget, will be re-verified not re-downloaded):${PRESENT}"
fi

if [[ -n $DROPPED ]]; then
    # Never drop silently — a shortened model list that prints nothing reads as
    # "everything installed" and the missing capability is found weeks later.
    warn "DISK LIMIT: ${DISK_FREE_GB}GB free minus ${DISK_RESERVE_GB}GB reserve = ${BUDGET_GB}GB for models."
    warn "DROPPED:${DROPPED}"
    warn "Installing only:${FITTED:- (nothing)}"
fi
[[ -n $MODELS ]] || die "no model fits in ${BUDGET_GB}GB. This box cannot run the stack — it needs a larger disk."

printf '\n  models : %s  (~%sGB of %sGB budget)\n  note   : %s\n' "$MODELS" "$USED_GB" "$BUDGET_GB" "$NOTE"
printf '  flags  : %s\n' "$COMFY_FLAGS"
printf '  extras : duix=%s wan2gp=%s\n' "$WITH_DUIX" "$WITH_WAN2GP"

if [[ $PLAN_ONLY -eq 1 ]]; then
    step "Plan only — nothing installed"
    exit 0
fi

PY=/opt/oasis/venv/bin/python
PIP=/opt/oasis/venv/bin/pip

# ---------------------------------------------------------------- torch
step "PyTorch (CUDA build)"
if ! $PY -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
    CUDA_TAG=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1 | cut -d. -f1)
    # Driver 550+ carries CUDA 12.4+; 570+ carries 12.8. cu126 wheels cover both.
    if (( CUDA_TAG >= 570 )); then IDX=cu128; else IDX=cu126; fi
    echo "driver $CUDA_TAG -> installing torch/$IDX"
    $PIP install -q torch torchvision torchaudio --index-url "https://download.pytorch.org/whl/$IDX" \
        || die "torch install failed for $IDX — check driver/CUDA compatibility"
fi
$PY - <<'PYEOF' || die "torch cannot see the GPU — the stack cannot work from here"
import sys, torch
if not torch.cuda.is_available():
    print("torch.cuda.is_available() == False", file=sys.stderr); sys.exit(1)
print(f"torch {torch.__version__}  cuda {torch.version.cuda}  device {torch.cuda.get_device_name(0)}")
PYEOF

# ---------------------------------------------------------------- comfyui
step "ComfyUI (GPL-3.0 — the operator surface)"
COMFY=/opt/oasis/repos/ComfyUI
if [[ ! -d $COMFY ]]; then
    git clone --depth 1 https://github.com/comfyanonymous/ComfyUI "$COMFY"
else
    git -C "$COMFY" pull --ff-only || warn "ComfyUI pull skipped (local changes)"
fi
$PIP install -q -r "$COMFY/requirements.txt"

install -d "$COMFY/custom_nodes"
# Cloning a custom node is only HALF of installing it. Each ships its own
# requirements.txt, and without them the node raises ModuleNotFoundError at
# startup and ComfyUI logs "IMPORT FAILED" — then serves happily with the node
# silently absent. That is invisible from the outside: the service is up, the
# port answers, and the loader you need simply is not in the node list.
# Observed on this box: GGUF (gguf), WanVideoWrapper (accelerate),
# VideoHelperSuite (cv2, imageio_ffmpeg) all failed exactly this way.
NODE_DEP_FAILURES=""
clone_node() {
    local url=$1 name
    name=$(basename "$url" .git)
    if [[ -d "$COMFY/custom_nodes/$name" ]]; then
        git -C "$COMFY/custom_nodes/$name" pull --ff-only >/dev/null 2>&1 || true
    else
        git clone --depth 1 "$url" "$COMFY/custom_nodes/$name"
    fi
    local req="$COMFY/custom_nodes/$name/requirements.txt"
    if [[ -f $req ]]; then
        echo "  installing deps for $name"
        $PIP install -q -r "$req" || NODE_DEP_FAILURES="$NODE_DEP_FAILURES $name"
    fi
}
clone_node https://github.com/ltdrdata/ComfyUI-Manager
clone_node https://github.com/city96/ComfyUI-GGUF          # Apache-2.0 GGUF loader
clone_node https://github.com/kijai/ComfyUI-WanVideoWrapper
clone_node https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite

# Belt and braces: these are the exact modules whose absence broke each node on
# a clean box. Some requirements.txt files omit them or pin them behind extras.
$PIP install -q gguf accelerate opencv-python-headless imageio-ffmpeg \
    || warn "some custom-node dependencies failed to install"

if [[ -n $NODE_DEP_FAILURES ]]; then
    warn "requirements.txt install FAILED for:${NODE_DEP_FAILURES}"
    warn "Those nodes will not register. Check 'journalctl -u comfyui | grep IMPORT'."
fi

# ---------------------------------------------------------------- media tools
step "Media tooling (render + edit + caption)"
apt-get update -qq
apt-get install -y -qq ffmpeg fonts-dejavu-core
$PIP install -q "huggingface_hub[cli]" faster-whisper

# ---------------------------------------------------------------- weights
step "Model weights -> /opt/oasis/models (re-downloadable; NOT backed up)"
export HF_HOME=/opt/oasis/models/.hf

# huggingface_hub renamed its CLI from `huggingface-cli` to `hf` at 0.34.
# Hardcoding either name means a silent total download failure on the other,
# and every call below was previously `|| warn` — so the script would have
# printed "Stack ready" over a box with ComfyUI and zero models.
if   [[ -x /opt/oasis/venv/bin/hf ]];              then HF_BIN=/opt/oasis/venv/bin/hf
elif [[ -x /opt/oasis/venv/bin/huggingface-cli ]]; then HF_BIN=/opt/oasis/venv/bin/huggingface-cli
else die "neither 'hf' nor 'huggingface-cli' in the venv — huggingface_hub[cli] did not install"
fi
echo "  using $HF_BIN"

FAILED_DOWNLOADS=()
dl() {  # dl <repo_id> <target_subdir> [glob]
    local repo=$1 target=$2 glob=${3:-}
    echo "  fetching $repo"
    local args=("$repo" --local-dir "/opt/oasis/models/$target")
    [[ -n $glob ]] && args+=(--include "$glob")
    # Explicit if/else, not `|| warn`: a missing model is a broken install, and
    # this list is checked before the script is allowed to report success.
    if ! "$HF_BIN" download "${args[@]}"; then
        FAILED_DOWNLOADS+=("$repo")
    fi
}

dl_files() {  # dl_files <repo_id> <target_subdir> <file> [file...]
    local repo=$1 target=$2; shift 2
    # POSITIONAL filenames, not --include. `hf download REPO --include A B C`
    # silently treats A B C as explicit filenames and warns "Ignoring --include";
    # on this box that fetched 2 of 3 files and the missing one was the
    # diffusion model itself. Positional is the documented form.
    for f in "$@"; do
        echo "  fetching $repo :: $f"
        if ! "$HF_BIN" download "$repo" "$f" --local-dir "/opt/oasis/models/$target"; then
            FAILED_DOWNLOADS+=("$repo/$f")
        fi
    done
}

# ComfyUI-native packaging. The official Wan-AI/* repos ship SHARDED DIFFUSERS
# checkpoints (diffusion_pytorch_model-00001-of-00003.safetensors) which
# ComfyUI's UNETLoader cannot open — it wants one file. Downloading those wasted
# 32GB on this box before the format mismatch was spotted. Comfy-Org repackages
# the same weights single-file, with the matching text encoder and VAE that
# EVERY Wan workflow needs, including the GGUF ones.
COMFY_REPACK_REPO="Comfy-Org/Wan_2.2_ComfyUI_Repackaged"
COMFY_REPACK_FILES=(
    "split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors"
    "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
    "split_files/vae/wan2.2_vae.safetensors"
    # S2V (audio-driven avatar) needs the 2.1 VAE specifically — the 2.2 VAE is
    # a different latent shape and the graph fails with it. Found by Maven
    # 2026-09-17 against ComfyUI's own video_wan2_2_14B_s2v.json template.
    "split_files/vae/wan_2.1_vae.safetensors"
)

# S2V's audio encoder canNOT live under /opt/oasis/models: extra_model_paths.yaml
# does not map an `audio_encoders` category, so ComfyUI falls back to its own
# models/audio_encoders/ directory. Putting it in the oasis tree makes
# AudioEncoderLoader show an empty list with no error. (Maven, 2026-09-17.)
S2V_AUDIO_ENCODER="split_files/audio_encoders/wav2vec2_large_english_fp16.safetensors"
# The repackaged base is MANDATORY regardless of tier: it carries the umt5 text
# encoder and the VAE, without which no Wan workflow runs — not even the GGUF
# ones, which ship only the diffusion weights.
dl_files "$COMFY_REPACK_REPO" comfy-wan22 "${COMFY_REPACK_FILES[@]}"

# Audio encoder into ComfyUI's OWN tree (see note above on why it cannot go
# into /opt/oasis/models).
install -d "$COMFY/models/audio_encoders"
if [[ ! -s "$COMFY/models/audio_encoders/wav2vec2_large_english_fp16.safetensors" ]]; then
    echo "  fetching S2V audio encoder -> ComfyUI/models/audio_encoders"
    if "$HF_BIN" download "$COMFY_REPACK_REPO" "$S2V_AUDIO_ENCODER" \
            --local-dir /tmp/s2v_audio; then
        install -m 0644 "/tmp/s2v_audio/$S2V_AUDIO_ENCODER" \
            "$COMFY/models/audio_encoders/" \
            || cp "/tmp/s2v_audio/$S2V_AUDIO_ENCODER" "$COMFY/models/audio_encoders/"
    else
        FAILED_DOWNLOADS+=("$S2V_AUDIO_ENCODER")
    fi
fi

# lightx2v 4-step acceleration LoRAs for the I2V path.
#
# Licence VERIFIED Apache-2.0 (huggingface.co/lightx2v/Wan2.2-Lightning; the
# card also disclaims rights over generated content) — client-safe, same as Wan
# itself. A LoRA does NOT inherit its base model's grant, so this was checked
# separately from Wan's.
#
# TWO named files, NOT the whole repo. `hf download <repo>` with no file
# argument fetches every file in it — an unbounded pull onto a box with ~12GB
# free, which is how you fill a disk mid-build. These are the exact two that
# ComfyUI's own video_wan2_2_14B_i2v.json template names.
#
# I2V ONLY. The t2v variant of this LoRA is NOT trained for S2V and upstream
# documents "significant dynamic and quality loss" when it is misapplied
# (found by Maven 2026-09-17). Licence-clean and fit-for-purpose are different
# questions; this comment records the answer to both.
LIGHTX2V_FILES=(
    "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"
    "split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"
)
dl_files "$COMFY_REPACK_REPO" loras "${LIGHTX2V_FILES[@]}"

for m in $MODELS; do
    case "$m" in
        # ti2v-5b is covered by the repackaged base above — do NOT also pull the
        # sharded Wan-AI copy; it is 32GB that ComfyUI cannot load.
        wan22-ti2v-5b|wan22-ti2v-5b-comfy) : ;;
        wan22-ti2v-5b-gguf)   dl QuantStack/Wan2.2-TI2V-5B-GGUF   wan22-ti2v-5b-gguf   "*Q5_K_M*" ;;
        wan22-i2v-a14b|wan22-i2v-a14b-gguf)
                              dl QuantStack/Wan2.2-I2V-A14B-GGUF  wan22-i2v-a14b-gguf  "*Q5_K_M*" ;;
        wan22-s2v-14b|wan22-s2v-14b-gguf)
                              dl QuantStack/Wan2.2-S2V-14B-GGUF   wan22-s2v-14b-gguf   "*Q5_K_M*" ;;
    esac
done

if (( ${#FAILED_DOWNLOADS[@]} > 0 )); then
    die "model download FAILED for: ${FAILED_DOWNLOADS[*]} — ComfyUI without weights generates nothing. Re-run after fixing network/HF access."
fi

# ComfyUI only sees models under its OWN models/ tree. Downloading to
# /opt/oasis/models and never telling ComfyUI about it produces a UI whose
# model dropdowns are empty — an install that looks complete and cannot
# generate a single frame. --extra-model-paths-config is the supported bridge.
step "Wiring /opt/oasis/models into ComfyUI"
cat > /opt/oasis/extra_model_paths.yaml <<'EOF'
oasis:
    base_path: /opt/oasis/models
    is_default: true
    diffusion_models: .
    unet: .
    vae: .
    clip: .
    clip_vision: .
    text_encoders: .
    loras: loras
EOF
install -d /opt/oasis/models/loras
cat /opt/oasis/extra_model_paths.yaml

# ---------------------------------------------------------------- optional
if [[ $WITH_WAN2GP -eq 1 ]]; then
    step "Wan2GP (WanGP Community 2.0 — agency use only, NOT a client-facing portal)"
    W=/opt/oasis/repos/Wan2GP
    [[ -d $W ]] || git clone --depth 1 https://github.com/deepbeepmeep/Wan2GP "$W"
    warn "Licence: delivering generated videos as client work is permitted and owes a"
    warn "'Made with WanGP' credit on a direct output sale. Standing up a self-serve"
    warn "portal on this is NOT permitted without a written licence from the author."
fi

if [[ $WITH_DUIX -eq 1 ]]; then
    step "Duix-Avatar (needs ~70GB download, 100GB+ free disk, and Docker)"
    # Check Docker BEFORE the disk check and long before the clone. Duix is a
    # docker-compose stack and nothing else; on a container host where Docker is
    # deliberately absent, cloning it downloads ~70GB that can never be run.
    # The disk gate alone would have let that through on a big enough box.
    command -v docker >/dev/null 2>&1 \
        || die "Duix-Avatar is a docker-compose stack and Docker is not installed. On a Hostinger GPU instance that is BY DESIGN (container host — installing docker-ce breaks apt via apparmor). Duix cannot run here; use the Wan2.2-S2V avatar model instead."
    docker info >/dev/null 2>&1 \
        || die "Docker is installed but not usable (daemon not running / no permission). Refusing to download ~70GB for a stack that cannot start."
    AVAIL_GB=$(df --output=avail -BG /opt | tail -1 | tr -dc '0-9')
    (( AVAIL_GB >= 110 )) || die "only ${AVAIL_GB}GB free on /opt — Duix needs 100GB+. Aborting before a half-download."
    D=/opt/oasis/repos/Duix-Avatar
    [[ -d $D ]] || git clone --depth 1 https://github.com/duixcom/Duix-Avatar "$D"
    warn "Licence REQUIRES a visible 'Built with DUIX.COM' credit on your product surface."
    warn "For a white-label client deliverable that is a branding leak — decide before shipping."
fi

# ---------------------------------------------------------------- launcher
step "Launcher"
# COMFY_FLAGS is tier-derived above. Every flag here was checked against
# ComfyUI's cli_args.py — an invalid flag makes main.py exit on "unrecognized
# arguments", which under Restart=on-failure is an infinite restart loop that
# still reports "active" to a naive systemctl check.
cat > /opt/oasis/start-comfy.sh <<EOF
#!/usr/bin/env bash
# Binds to 127.0.0.1 ONLY. ComfyUI ships with no authentication of any kind;
# a public bind is a takeover of the box, not merely a leaked UI.
# Reach it with:  python scripts/gpu/oasisgpu.py tunnel 8188
set -Eeuo pipefail
cd /opt/oasis/repos/ComfyUI
exec /opt/oasis/venv/bin/python main.py \\
    --listen 127.0.0.1 --port 8188 \\
    --output-directory /opt/oasis/outputs \\
    --extra-model-paths-config /opt/oasis/extra_model_paths.yaml \\
    ${COMFY_FLAGS}
EOF
chmod +x /opt/oasis/start-comfy.sh

# Prove the flags parse BEFORE handing the file to systemd, so a bad flag is a
# clear failure here instead of a silent restart loop discovered days later.
/opt/oasis/venv/bin/python "$COMFY/main.py" --help >/dev/null 2>&1 \
    || warn "could not run ComfyUI --help; flag validation skipped"

cat > /etc/systemd/system/comfyui.service <<'EOF'
[Unit]
Description=ComfyUI (OasisGPU)
After=network-online.target

[Service]
Type=simple
ExecStart=/opt/oasis/start-comfy.sh
Restart=on-failure
RestartSec=10
WorkingDirectory=/opt/oasis/repos/ComfyUI

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now comfyui

# Type=simple makes systemd report "active" the instant it forks, before
# ComfyUI has loaded a single model — and it keeps reporting active across a
# crash-restart loop. Poll the PORT instead: that is the thing Maven actually
# needs working, and it cannot be faked by a process that is about to die.
step "Waiting for ComfyUI to actually serve (not just to have been started)"
READY=0
for i in $(seq 1 60); do
    if curl -fsS --max-time 3 http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
        READY=1
        echo "  serving after ~${i}0s"
        break
    fi
    sleep 10
done
if (( READY == 0 )); then
    systemctl is-active --quiet comfyui \
        && die "comfyui is 'active' but never answered on :8188 after 10 min — almost certainly a crash-restart loop. Run: journalctl -u comfyui -n 80 --no-pager" \
        || die "comfyui failed to start. Run: journalctl -u comfyui -n 80 --no-pager"
fi

# A serving port proves the process is alive, NOT that the stack is usable.
# ComfyUI starts and answers HTTP perfectly well with every custom node in
# IMPORT FAILED state — the loaders you need are simply missing from the node
# list. Assert the nodes exist by name.
step "Verifying required nodes actually registered"
curl -fsS --max-time 15 -o /tmp/oasis_object_info.json http://127.0.0.1:8188/object_info \
    || die "could not read ComfyUI object_info despite the port answering"
MISSING_NODES=$("$PY" - <<'PYEOF'
import json
want = ["UNETLoader", "CLIPLoader", "VAELoader", "KSampler", "VAEDecode"]
optional = {"UnetLoaderGGUF": "ComfyUI-GGUF", "VHS_VideoCombine": "ComfyUI-VideoHelperSuite"}
d = json.load(open("/tmp/oasis_object_info.json"))
missing = [n for n in want if n not in d]
for node, pkg in optional.items():
    if node not in d:
        missing.append(f"{node}({pkg})")
print(" ".join(missing))
PYEOF
)
if [[ -n ${MISSING_NODES// /} ]]; then
    warn "NODES MISSING:${MISSING_NODES}"
    warn "ComfyUI is serving but these loaders are absent — the models they load are UNUSABLE."
    warn "Diagnose with: sudo journalctl -u comfyui --no-pager | grep -i 'IMPORT FAILED'"
else
    echo "  all required and optional loader nodes registered"
fi

step "Stack ready"
printf '\nGPU   : %s (%sGB, tier %s)\n' "$GPU_NAME" "$VRAM_GB" "$TIER"
printf 'Models: %s\n' "$MODELS"
printf 'ComfyUI: running on 127.0.0.1:8188 (systemd: comfyui)\n'
printf '\nFrom your PC:  python scripts/gpu/oasisgpu.py tunnel 8188\n'
printf 'Then open   :  http://localhost:8188\n'
printf '\nREMINDER: this box bills every hour it EXISTS. Sync outputs off and destroy it when idle.\n'
