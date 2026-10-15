$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot

& "$ProjectRoot/scripts/build-sidecar-windows.ps1"
Push-Location "$ProjectRoot/frontend"
try {
  npm install
  npm run tauri icon src-tauri/icons/icon-source.png
  npm run tauri build -- --bundles nsis
  Write-Host "Installer output: frontend/src-tauri/target/release/bundle/nsis/"
}
finally {
  Pop-Location
}

