#!/usr/bin/env bash
# OASIS AI install — stable URL, repo-visibility-proof.
#
#   curl -fsSL https://agent-dashboard-cc90210.vercel.app/install.sh | bash
#   OASIS_PROFILE=hermes curl -fsSL https://agent-dashboard-cc90210.vercel.app/install.sh | bash
#
# This URL is the canonical install entry point. The underlying GitHub
# repo (CC90210/CEO-Agent) may flip visibility — this script always fetches
# the latest install/quickstart.sh, transparently bridging public→gh-auth
# if the public path 404s.

set -euo pipefail
REPO="CC90210/CEO-Agent"
FILE="install/quickstart.sh"

echo "==> OASIS AI install"
echo "    repo: https://github.com/$REPO"
echo

if SCRIPT="$(curl -fsSL "https://raw.githubusercontent.com/$REPO/main/$FILE" 2>/dev/null)"; then
    bash -c "$SCRIPT"
    exit $?
fi

echo "Public URL returned 404 (repo may be private)." >&2
echo "Falling back to authenticated GitHub CLI..." >&2

if ! command -v gh >/dev/null 2>&1; then
    cat >&2 <<EOF
GitHub CLI not installed. Install it first:
  macOS:    brew install gh
  Ubuntu:   sudo apt install gh
  Windows:  winget install GitHub.cli
Then re-run this install command.
EOF
    exit 1
fi

if ! gh auth status -h github.com >/dev/null 2>&1; then
    gh auth login -h github.com
fi

SCRIPT_B64="$(gh api "repos/$REPO/contents/$FILE" --jq .content | tr -d '\n')"
SCRIPT="$(printf '%s' "$SCRIPT_B64" | { base64 -d 2>/dev/null || base64 -D; })"
bash -c "$SCRIPT"
