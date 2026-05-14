#!/usr/bin/env bash
# Ad-hoc Mac codesign for the unsigned alpha.
#
# This does NOT satisfy Apple notarization or Gatekeeper's "trusted developer"
# requirement. Users will still see "Apple cannot verify..." until we ship a
# Developer ID-signed + notarized build (Phase 5 of the rearchitecture plan).
#
# What it DOES do: stamp the app with a stable ad-hoc identity so:
#  - the bundle's signature is consistent across runs
#  - users who clear quarantine with `xattr -d com.apple.quarantine ...` get a
#    cleaner launch experience
#  - macOS doesn't randomise the team identifier between builds
#
# Run from the desktop app directory after `npm run build:mac`:
#   bash scripts/adhoc-sign-mac.sh dist/mac-arm64/OASIS\ AI.app
#
# Cost: $0. Reversibility: signing is idempotent; re-run safely.

set -euo pipefail

APP_PATH="${1:-}"
if [[ -z "$APP_PATH" ]]; then
  echo "usage: $(basename "$0") <path-to-.app>" >&2
  exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
  echo "error: $APP_PATH is not a directory" >&2
  exit 1
fi

if ! command -v codesign >/dev/null 2>&1; then
  echo "error: codesign not found. This script must run on macOS." >&2
  exit 1
fi

echo "Ad-hoc signing $APP_PATH ..."
codesign --force --deep --sign - "$APP_PATH"
codesign --verify --verbose=2 "$APP_PATH" || {
  echo "warn: verification reported issues — review output above" >&2
}
echo "Done. Note: this build is still unsigned by Apple. Users must right-click → Open or run xattr -d com.apple.quarantine."
