#!/usr/bin/env sh
# Install iacforge (Linux/macOS) from git via uv or pipx, then run `iacforge doctor`.
# Override the source with IACFORGE_REPO (default below).
set -eu

REPO="${IACFORGE_REPO:-git+https://github.com/bsommers/iacforge}"

if command -v uv >/dev/null 2>&1; then
  echo "Installing with uv tool..."
  uv tool install --force "iacforge[mcp] @ ${REPO}"
elif command -v pipx >/dev/null 2>&1; then
  echo "Installing with pipx..."
  pipx install --force "iacforge[mcp] @ ${REPO}"
else
  echo "error: need 'uv' or 'pipx' on PATH." >&2
  echo "  uv:   https://docs.astral.sh/uv/getting-started/installation/" >&2
  echo "  pipx: https://pipx.pypa.io/stable/installation/" >&2
  exit 1
fi

if ! command -v iacforge >/dev/null 2>&1; then
  echo "warning: 'iacforge' is not on PATH yet; try 'uv tool update-shell' (or 'pipx ensurepath') and restart your shell." >&2
  exit 0
fi

echo
iacforge doctor || true

cat <<'MSG'

Next steps (install engines yourself, iacforge never fetches them):
  OpenTofu: https://opentofu.org/docs/intro/install/
  Pulumi:   https://www.pulumi.com/docs/install/   (only for engine: pulumi)
Then: iacforge init && iacforge validate && iacforge plan
MSG
