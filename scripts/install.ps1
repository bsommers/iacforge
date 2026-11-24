# Install iacforge (Windows) from git via uv or pipx, then run `iacforge doctor`.
# Override the source with $env:IACFORGE_REPO.
$ErrorActionPreference = 'Stop'

$repo = if ($env:IACFORGE_REPO) { $env:IACFORGE_REPO } else { 'git+https://github.com/bsommers/iacforge' }
$pkg = "iacforge[mcp] @ $repo"

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host 'Installing with uv tool...'
    uv tool install --force $pkg
} elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
    Write-Host 'Installing with pipx...'
    pipx install --force $pkg
} else {
    Write-Error "Need 'uv' or 'pipx' on PATH. uv: https://docs.astral.sh/uv/getting-started/installation/  pipx: https://pipx.pypa.io/stable/installation/"
    exit 1
}

if (-not (Get-Command iacforge -ErrorAction SilentlyContinue)) {
    Write-Warning "'iacforge' is not on PATH yet; run 'uv tool update-shell' (or 'pipx ensurepath') and restart your shell."
    exit 0
}

Write-Host ''
try { iacforge doctor } catch { Write-Warning $_ }

Write-Host @'

Next steps (install engines yourself, iacforge never fetches them):
  OpenTofu: https://opentofu.org/docs/intro/install/
  Pulumi:   https://www.pulumi.com/docs/install/   (only for engine: pulumi)
Then: iacforge init; iacforge validate; iacforge plan
'@
