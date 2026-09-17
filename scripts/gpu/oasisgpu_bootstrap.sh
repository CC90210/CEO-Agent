#!/usr/bin/env bash
# oasisgpu_bootstrap.sh — baseline build-out for a fresh Hostinger GPU instance.
#
# Runs ON the box as root. Idempotent: safe to re-run after a reboot or a
# partial failure. Fails LOUD — every step that cannot complete aborts with a
# named reason rather than continuing into a half-built machine.
#
#   bash oasisgpu_bootstrap.sh              # full baseline
#   bash oasisgpu_bootstrap.sh --smoke      # report hardware/driver state only
#
# Deliberately does NOT install any video-gen model repo — the model stack is
# chosen per-GPU-tier (see docs/handovers/2026-09-16_hostinger_gpu_llm_handover.md
# and the OasisGPU stack plan). This lays the floor those repos stand on.

set -Eeuo pipefail

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; RST=$'\033[0m'
step() { printf '\n%s==> %s%s\n' "$GRN" "$1" "$RST"; }
warn() { printf '%s[warn] %s%s\n' "$YLW" "$1" "$RST"; }
die()  { printf '%s[FAIL] %s%s\n' "$RED" "$1" "$RST" >&2; exit 1; }
trap 'die "aborted at line $LINENO — nothing after this point ran"' ERR

# Hostinger's GPU image logs you in as `ubuntu`, not root (the panel's own SSH
# command says so). Self-elevate rather than telling the caller to retry.
if [[ $EUID -ne 0 ]]; then
    command -v sudo >/dev/null 2>&1 || die "not root and no sudo available (you are $(whoami))"
    # -n first: a sudo that wants a password would BLOCK forever under the
    # non-interactive ssh this is normally invoked through, with no prompt
    # visible to anyone. Fail with an instruction instead of hanging.
    sudo -n true 2>/dev/null \
        || die "sudo needs a password for $(whoami). Run once interactively: python scripts/gpu/oasisgpu.py shell, then 'sudo -v'."
    exec sudo -E bash "$0" "$@"
fi

SMOKE_ONLY=0
[[ "${1:-}" == "--smoke" ]] && SMOKE_ONLY=1

# ---------------------------------------------------------------- hardware
step "Hardware + driver smoke test"
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi || die "nvidia-smi is installed but failed to run — driver/kernel mismatch, reboot then re-run"
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
    VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
    printf '\nDetected: %s with %s MB VRAM (%s GB)\n' "$GPU_NAME" "$VRAM_MB" "$((VRAM_MB / 1024))"
    DRIVER_OK=1
else
    warn "nvidia-smi not found — Hostinger's template did not ship drivers"
    DRIVER_OK=0
fi

printf 'Kernel:  %s\n' "$(uname -r)"
printf 'Distro:  %s\n' "$(. /etc/os-release && echo "$PRETTY_NAME")"
printf 'Disk:    %s\n' "$(df -h / | awk 'NR==2 {print $4" free of "$2}')"
printf 'RAM:     %s\n' "$(free -h | awk 'NR==2 {print $7" available of "$2}')"

if [[ $SMOKE_ONLY -eq 1 ]]; then
    step "Smoke only — stopping here"
    exit 0
fi

export DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------- base pkgs
step "Base packages"
apt-get update -qq
apt-get install -y -qq \
    build-essential git curl wget ca-certificates gnupg lsb-release \
    python3 python3-venv python3-pip python3-dev \
    tmux htop nvtop jq unzip rsync ufw fail2ban

# ---------------------------------------------------------------- drivers
if [[ $DRIVER_OK -eq 0 ]]; then
    step "Installing NVIDIA driver (none present)"
    apt-get install -y -qq ubuntu-drivers-common
    ubuntu-drivers install --gpgpu \
        || die "ubuntu-drivers could not install a GPGPU driver — check 'ubuntu-drivers devices' output manually"
    # Exit 75 (EX_TEMPFAIL), never 0: the box is HALF-BUILT here. Exiting 0
    # would make the local driver — and any cron that ever wraps this — report
    # a green baseline for a machine with no Docker, no firewall and no venv.
    warn "driver installed — REBOOT REQUIRED, then re-run this script to continue"
    exit 75
fi

# ---------------------------------------------------------------- docker
step "Docker + NVIDIA container toolkit"
# Hostinger GPU instances ARE containers (systemd-detect-virt: container-other,
# / on containerd overlayfs). Installing Docker here is not merely useless, it
# is ACTIVELY DESTRUCTIVE: docker-ce depends on apparmor, whose postinst runs
# `install /dev/null /etc/apparmor.d/local/...`, and copy-from-/dev/null returns
# a bogus ENOSPC on this overlay (reproduced in /tmp too — the disk was 1% full).
# apparmor then sticks in `iF` state and every later apt-get fails, which blocks
# the entire stack install. The core stack never needs Docker: ComfyUI and torch
# run natively. Verified on this box 2026-09-17.
IS_CONTAINER=0
if systemd-detect-virt --container >/dev/null 2>&1; then
    IS_CONTAINER=1
fi

if (( IS_CONTAINER )); then
    warn "Container host ($(systemd-detect-virt 2>/dev/null)) — SKIPPING Docker by design."
    warn "  Reason: docker-ce pulls apparmor, which cannot configure on this overlay"
    warn "  and leaves apt permanently broken. Core stack runs natively without it."
    warn "  Consequence: --with-duix (Docker-based) is NOT available on this host."
    DOCKER_GPU_OK=0
elif ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
else
    echo "docker already present: $(docker --version)"
fi

# Guarded on IS_CONTAINER: without Docker installed, `nvidia-ctk runtime
# configure --runtime=docker` and `systemctl restart docker` both fail, and
# under `set -e` that aborts the build before the venv is ever created.
if (( ! IS_CONTAINER )) && ! dpkg -s nvidia-container-toolkit >/dev/null 2>&1; then
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
        | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        > /etc/apt/sources.list.d/nvidia-container-toolkit.list
    apt-get update -qq
    apt-get install -y -qq nvidia-container-toolkit
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
fi

step "Checking whether the GPU is usable INSIDE a container"
# A capability PROBE, not a gate. Failing the whole build here would block the
# 95% of the stack that never needs Docker for the sake of the opt-in Duix path
# that does.
if (( IS_CONTAINER )); then
    echo "  skipped (Docker intentionally not installed on a container host)"
elif docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi >/dev/null 2>&1; then
    DOCKER_GPU_OK=1
    echo "  GPU IS visible inside Docker — containerised workloads (e.g. Duix) will work"
else
    warn "GPU is NOT usable inside Docker on this host (expected inside a container)."
    warn "Core stack is unaffected: ComfyUI + torch run natively."
    warn "Docker-based extras (--with-duix) will NOT work here."
fi

# ---------------------------------------------------------------- hardening
step "Firewall + SSH hardening"
# Order matters: allow SSH BEFORE enabling, or ufw locks you out of your own box.
# The provider assigns a NON-22 external port (e.g. 31310) and forwards it, so
# allow both the real sshd port and 22 rather than assuming the default.
# ALL sshd ports, not just the first. Provider drop-ins add extra Port lines
# (this image adds 5020 alongside 22) and Port directives ACCUMULATE rather
# than override. Allowing only the first match can firewall off the very port
# the provider forwards your session through.
SSHD_PORTS=$(sshd -T 2>/dev/null | awk '/^port /{print $2}' | sort -un)
SSHD_PORTS=${SSHD_PORTS:-22}
echo "  sshd ports: $(echo "$SSHD_PORTS" | tr '\n' ' ')"
if ufw allow 22/tcp >/dev/null 2>&1; then
    for p in $SSHD_PORTS; do ufw allow "${p}/tcp" >/dev/null 2>&1 || true; done
    ufw --force default deny incoming >/dev/null
    ufw --force default allow outgoing >/dev/null
    ufw --force enable >/dev/null
    ufw status verbose
else
    # In a container without netfilter permission ufw silently half-applies.
    # Say so plainly: an operator who believes a firewall is up when it is not
    # is worse off than one who knows there is none.
    warn "ufw could not apply rules (container networking). NO host firewall is active."
    warn "Rely on the provider's network boundary and keep every service on 127.0.0.1."
fi

# 00- prefix is load-bearing. sshd Includes sshd_config.d/*.conf in LEXICAL
# order and uses the FIRST value obtained for each keyword. Hostinger's image
# ships 99-haishare.conf containing `PasswordAuthentication yes`, and 'h' sorts
# before 'o', so a 99-oasisgpu.conf is parsed second and silently loses. The
# hardening step then reports success while the box still accepts passwords
# from the internet. Verified on this box 2026-09-17.
SSHD_DROPIN=/etc/ssh/sshd_config.d/00-oasisgpu.conf
STALE_DROPIN=/etc/ssh/sshd_config.d/99-oasisgpu.conf
# The login user here is `ubuntu`, not root, so the key lives in
# /home/ubuntu/.ssh. Checking only /root found nothing and left PASSWORD AUTH
# ENABLED on an internet-facing port — the box stayed open to brute force while
# reporting a successful hardening step.
LOGIN_USER=${SUDO_USER:-root}
LOGIN_HOME=$(getent passwd "$LOGIN_USER" | cut -d: -f6)
KEYED=0
for akf in /root/.ssh/authorized_keys "${LOGIN_HOME:-/root}/.ssh/authorized_keys"; do
    [[ -s $akf ]] && { KEYED=1; echo "  found authorized_keys: $akf"; }
done
if (( KEYED )); then
    cat > "$SSHD_DROPIN" <<'EOF'
PasswordAuthentication no
PermitRootLogin prohibit-password
X11Forwarding no
MaxAuthTries 3
EOF
    # Neutralise the earlier, losing filename rather than deleting it.
    if [[ -f $STALE_DROPIN ]]; then
        printf '# superseded by 00-oasisgpu.conf (lexical precedence)\n' > "$STALE_DROPIN"
    fi
    sshd -t || die "sshd config invalid — NOT restarting; fix $SSHD_DROPIN first"
    systemctl reload ssh
    # Assert the EFFECTIVE value. Writing a config file is not the same as the
    # setting taking effect — a competing drop-in already beat this once.
    EFFECTIVE=$(sshd -T 2>/dev/null | awk '/^passwordauthentication/ {print $2}')
    if [[ $EFFECTIVE == "no" ]]; then
        echo "password auth DISABLED and VERIFIED via sshd -T (key present for ${LOGIN_USER})"
    else
        warn "WROTE the hardening drop-in but sshd still reports passwordauthentication=${EFFECTIVE:-unknown}."
        warn "Another drop-in in /etc/ssh/sshd_config.d/ is winning. Inspect before trusting this box."
    fi
else
    warn "NO ssh key found for root or ${LOGIN_USER} — leaving password auth ON so you are not locked out."
    warn "Add your public key, then re-run this script to close password auth."
fi

systemctl enable --now fail2ban >/dev/null 2>&1 || warn "fail2ban did not start"

# ---------------------------------------------------------------- workspace
step "Workspace + Python venv"
install -d -m 0755 /opt/oasis /opt/oasis/models /opt/oasis/outputs /opt/oasis/repos
if [[ ! -d /opt/oasis/venv ]]; then
    python3 -m venv /opt/oasis/venv
fi
/opt/oasis/venv/bin/pip install -q --upgrade pip wheel setuptools

# ---------------------------------------------------------------- credit guard
step "Credit burn guard"
# Hostinger DESTROYS a GPU instance (and its data) when account credits hit
# zero. Nothing on the box can read the credit balance, so the only defence
# available here is making the work resumable: everything valuable lands in
# /opt/oasis and is rsynced off by the local driver.
cat > /opt/oasis/README-FIRST.txt <<'EOF'
OasisGPU workspace
==================
  /opt/oasis/models   downloaded weights  (big, re-downloadable)
  /opt/oasis/repos    cloned model repos
  /opt/oasis/outputs  generated media + trained adapters  <-- THE ONLY IRREPLACEABLE DIR
  /opt/oasis/venv     shared python env

WARNING: Hostinger bills this instance hourly from account credits. If the
balance reaches zero the instance is DESTROYED along with everything on it.
Treat /opt/oasis/outputs as ephemeral — sync it off the box after every run.
EOF
cat /opt/oasis/README-FIRST.txt

step "Baseline complete"
# Every value here is fallback-guarded. A summary line that can fail turns a
# fully successful build into a reported FAILURE at the last instruction —
# which is exactly what `docker --version` did once Docker was (correctly)
# no longer installed.
printf '\nGPU:    %s (%s GB)\n' "${GPU_NAME:-unknown}" "$((${VRAM_MB:-0} / 1024))"
printf 'Docker: %s\n' "$(command -v docker >/dev/null 2>&1 && docker --version || echo 'not installed (container host — by design)')"
printf 'Python: %s\n' "$(/opt/oasis/venv/bin/python --version 2>&1 || echo unknown)"
printf '\nNext: install the model stack matched to %s GB VRAM.\n' "$((${VRAM_MB:-0} / 1024))"
