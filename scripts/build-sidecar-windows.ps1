$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TargetTriple = (rustc -vV | Select-String '^host: ').ToString().Replace('host: ', '').Trim()
$BinaryName = "obsidianquery-backend-$TargetTriple"

Push-Location "$ProjectRoot/backend"
try {
  uv sync --group desktop
  $env:OBSIDIANQUERY_BINARY_NAME = $BinaryName
  uv run --group desktop pyinstaller --noconfirm --clean --distpath dist/desktop --workpath build/desktop desktop.spec
  New-Item -ItemType Directory -Force "$ProjectRoot/frontend/src-tauri/binaries" | Out-Null
  Copy-Item "dist/desktop/$BinaryName.exe" "$ProjectRoot/frontend/src-tauri/binaries/$BinaryName.exe" -Force
  Write-Host "Built frontend/src-tauri/binaries/$BinaryName.exe"
}
finally {
  Pop-Location
}
