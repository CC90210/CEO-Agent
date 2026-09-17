"""oasisgpu.py — local driver for the Hostinger GPU box (OasisGPU).

One command from this repo instead of hand-typed ssh. Stores the host once in
config/gpu/oasisgpu.json (NO credentials — host/user/port only; auth is your
ssh key or the panel password typed interactively).

    python scripts/gpu/oasisgpu.py set-host 1.2.3.4
    python scripts/gpu/oasisgpu.py smoke          # nvidia-smi + disk/ram, read-only
    python scripts/gpu/oasisgpu.py bootstrap      # ship + run oasisgpu_bootstrap.sh
    python scripts/gpu/oasisgpu.py shell          # interactive session
    python scripts/gpu/oasisgpu.py run "df -h"    # one-off command
    python scripts/gpu/oasisgpu.py tunnel 8188    # forward a web UI to localhost
    python scripts/gpu/oasisgpu.py pull outputs   # rsync /opt/oasis/outputs down

Why a tunnel and not an exposed port: Hostinger's own docs warn an exposed GPU
service is "publicly accessible to anyone with the IP address". ComfyUI and
friends ship with no auth at all — a forwarded port is the only safe default.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

CAPABILITY_META = {
    "category": "infra.gpu",
    "lifecycle": "active",
    "risk": "remote_exec",
    "triggers": [
        "connect to the gpu server",
        "bootstrap the gpu box",
        "open comfyui from the gpu instance",
        "check what gpu the server has",
    ],
    "owner": "bravo",
    "project": "empire",
    "bridge": {"visible": False},
}

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "config" / "gpu" / "oasisgpu.json"
BOOTSTRAP = Path(__file__).resolve().parent / "oasisgpu_bootstrap.sh"


def _load() -> dict:
    if not CONFIG.exists():
        return {}
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _save(cfg: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


DEFAULT_KEY = Path.home() / ".ssh" / "oasisgpu_ed25519"


def _target() -> tuple[str, str, int]:
    cfg = _load()
    host = cfg.get("host")
    if not host:
        sys.exit(
            "no host configured.\n"
            "  hPanel -> Dev tools -> GPU -> Manage -> Overview shows the IP.\n"
            "  then: python scripts/gpu/oasisgpu.py set-host <ip>"
        )
    return host, cfg.get("user", "root"), int(cfg.get("port", 22))


def _key_path() -> Path | None:
    """The identity file's PATH, or None.

    Only the path is ever handled here. The key's contents are never read by
    this process and must never be read into an agent's context — ssh is the
    only thing that opens it.
    """
    cfg = _load()
    key = Path(cfg.get("identity") or DEFAULT_KEY)
    return key if key.exists() else None


def _identity() -> list[str]:
    """`-i <key>` args, or [] to let ssh use its own defaults."""
    key = _key_path()
    if key is None:
        return []
    # IdentitiesOnly stops ssh offering every other key first and tripping
    # MaxAuthTries (the bootstrap sets it to 3) before it reaches this one.
    return ["-i", str(key), "-o", "IdentitiesOnly=yes"]


# accept-new trusts a first-seen host key but still refuses a CHANGED one, so a
# fresh box connects unattended while key-swap tampering is still caught.
COMMON_OPTS = ["-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15"]
# BatchMode makes ssh fail instead of blocking on a password/passphrase prompt
# that a non-interactive caller can never answer.
BATCH_OPTS = ["-o", "BatchMode=yes"]


def _conn_opts(batch: bool = True) -> list[str]:
    """Identity + hardening options shared by ssh, scp and rsync.

    Built in ONE place. scp previously got the identity but not these options,
    so `bootstrap` and `stack` could hang on a host-key prompt during their
    upload step while the ssh step that followed was fully non-interactive —
    a hang in the half of the command nobody was looking at.
    """
    return _identity() + COMMON_OPTS + (BATCH_OPTS if batch else [])


def _ssh_base(batch: bool = True) -> list[str]:
    if not shutil.which("ssh"):
        sys.exit("ssh client not found on PATH (Windows: install OpenSSH Client feature)")
    host, user, port = _target()
    return ["ssh", "-p", str(port), *_conn_opts(batch), f"{user}@{host}"]


def _scp_base(batch: bool = True) -> list[str]:
    if not shutil.which("scp"):
        sys.exit("scp not found on PATH")
    _, _, port = _target()
    # scp spells the port -P (capital); ssh spells it -p. Mixing them up yields
    # a confusing "usage:" dump rather than a connection error.
    return ["scp", "-P", str(port), *_conn_opts(batch)]


def _remote(path: str) -> str:
    host, user, _ = _target()
    return f"{user}@{host}:{path}"


def _run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}\n", flush=True)
    return subprocess.call(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description="OasisGPU remote driver")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sh = sub.add_parser("set-host", help="save the instance IP")
    sh.add_argument("host")
    sh.add_argument("--user", default="root")
    sh.add_argument("--port", type=int, default=22)

    sub.add_parser("show", help="print saved connection target")
    sub.add_parser("smoke", help="read-only hardware report over ssh")
    sub.add_parser("bootstrap", help="upload + run the baseline build-out")
    st = sub.add_parser("stack", help="upload + run the model stack installer")
    st.add_argument("--with-duix", action="store_true", help="also install Duix-Avatar (attribution required)")
    st.add_argument("--with-wan2gp", action="store_true", help="also install Wan2GP (no client-facing portal)")
    st.add_argument("--plan", action="store_true", help="print the tier plan, install nothing")
    sub.add_parser("shell", help="interactive ssh session")

    r = sub.add_parser("run", help="run one command on the box")
    r.add_argument("command")

    pu = sub.add_parser("push", help="copy a local file to the box")
    pu.add_argument("local")
    pu.add_argument("remote", nargs="?", default=None,
                    help="remote path (default: /tmp/<basename>)")

    t = sub.add_parser("tunnel", help="forward a remote port to localhost")
    t.add_argument("port", type=int)

    p = sub.add_parser("pull", help="rsync a /opt/oasis subdir down to tmp/")
    p.add_argument("what", default="outputs", nargs="?")

    args = ap.parse_args()

    if args.cmd == "set-host":
        cfg = _load()
        cfg.update({"host": args.host, "user": args.user, "port": args.port})
        _save(cfg)
        print(f"saved -> {args.user}@{args.host}:{args.port}  ({CONFIG.relative_to(REPO_ROOT)})")
        return 0

    if args.cmd == "show":
        cfg = _load()
        print(json.dumps(cfg, indent=2) if cfg else "no host configured")
        return 0

    if args.cmd == "smoke":
        remote = (
            "echo '--- GPU ---'; (nvidia-smi || echo 'NO DRIVER / NO nvidia-smi'); "
            "echo '--- OS ---'; . /etc/os-release && echo \"$PRETTY_NAME $(uname -r)\"; "
            "echo '--- DISK ---'; df -h /; echo '--- RAM ---'; free -h; "
            "echo '--- DOCKER ---'; (docker --version || echo 'no docker')"
        )
        return _run(_ssh_base() + [remote])

    if args.cmd == "bootstrap":
        if not BOOTSTRAP.exists():
            sys.exit(f"missing {BOOTSTRAP}")
        rc = _run(_scp_base() + [str(BOOTSTRAP), _remote("/tmp/oasisgpu_bootstrap.sh")])
        if rc != 0:
            return rc
        # dos2unix inline: the file is authored on Windows and bash chokes on CRLF.
        rc = _run(_ssh_base() + [
            "sed -i 's/\\r$//' /tmp/oasisgpu_bootstrap.sh && bash /tmp/oasisgpu_bootstrap.sh"
        ])
        if rc == 75:
            print(
                "\nHALF-BUILT: the NVIDIA driver was installed but the box must reboot.\n"
                "  Reboot it (hPanel has the button), then run bootstrap again.\n"
                "  Docker, firewall and the venv have NOT been set up yet."
            )
        elif rc != 0:
            print(f"\nbootstrap FAILED (exit {rc}) — read the last '[FAIL]' line above.")
        return rc

    if args.cmd == "stack":
        script = Path(__file__).resolve().parent / "oasisgpu_stack.sh"
        if not script.exists():
            sys.exit(f"missing {script}")
        rc = _run(_scp_base() + [str(script), _remote("/tmp/oasisgpu_stack.sh")])
        if rc != 0:
            return rc
        flags = " ".join(f for f, on in (
            ("--with-duix", args.with_duix),
            ("--with-wan2gp", args.with_wan2gp),
            ("--plan", args.plan),
        ) if on)
        return _run(_ssh_base() + [
            f"sed -i 's/\\r$//' /tmp/oasisgpu_stack.sh && bash /tmp/oasisgpu_stack.sh {flags}".strip()
        ])

    if args.cmd == "shell":
        # Interactive: no BatchMode, so a password/passphrase prompt can be answered.
        return _run(_ssh_base(batch=False))

    if args.cmd == "run":
        return _run(_ssh_base() + [args.command])

    if args.cmd == "push":
        src = Path(args.local)
        if not src.exists():
            sys.exit(f"no such file: {src}")
        # Authoring scripts locally and pushing them beats heredoc-over-ssh,
        # which mangles quoting on anything non-trivial.
        dest = args.remote or f"/tmp/{src.name}"
        # Git Bash/MSYS rewrites a POSIX arg like /tmp/x.py into C:/.../tmp/x.py
        # BEFORE python is invoked, so the remote path silently becomes a
        # Windows path and scp fails with "dest open". Catch it and say why.
        if re.match(r"^[A-Za-z]:[\\/]", dest):
            sys.exit(
                f"remote path looks Windows-ified: {dest}\n"
                "  Git Bash rewrote it. Omit the remote argument (defaults to "
                "/tmp/<name>), or prefix with a second slash: //tmp/<name>"
            )
        rc = _run(_scp_base() + [str(src), _remote(dest)])
        if rc == 0:
            print(f"pushed -> {dest}")
        return rc

    if args.cmd == "tunnel":
        host, user, port = _target()
        print(f"forwarding remote :{args.port} -> http://localhost:{args.port}")
        print("leave this window open; Ctrl-C closes the tunnel\n")
        # batch=False: a tunnel is long-lived and may legitimately need to
        # prompt. Options come from _conn_opts so this path cannot drift out
        # of sync with ssh/scp/rsync the way it just did.
        return _run(["ssh", "-p", str(port), *_conn_opts(batch=False), "-N",
                     "-L", f"{args.port}:localhost:{args.port}", f"{user}@{host}"])

    if args.cmd == "pull":
        _, _, port = _target()  # host/user come from _remote()
        dest = REPO_ROOT / "tmp" / "oasisgpu"
        dest.mkdir(parents=True, exist_ok=True)
        if shutil.which("rsync"):
            # rsync -e takes ONE shell-parsed string, so the key path is
            # re-quoted with forward slashes: a Windows path like
            # C:\Users\User\.ssh\key loses every backslash when the remote
            # shell word-splits it, and ssh then looks for a file called
            # "C:UsersUser.sshkey". Reusing _conn_opts keeps the options
            # identical to every other path instead of a hand-built subset.
            opts = " ".join(o.replace("\\", "/") for o in _conn_opts())
            ssh_cmd = f"ssh -p {port} {opts}".strip()
            return _run(["rsync", "-avz", "-e", ssh_cmd,
                         _remote(f"/opt/oasis/{args.what}/"), str(dest / args.what) + "/"])
        return _run(_scp_base() + ["-r", _remote(f"/opt/oasis/{args.what}"), str(dest)])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
