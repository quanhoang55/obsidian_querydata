#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"

"$project_root/scripts/build-sidecar-macos.sh"
cd "$project_root/frontend"
npm install
npm run tauri icon src-tauri/icons/icon-source.png
npm run tauri build -- --bundles dmg

echo "DMG output: frontend/src-tauri/target/release/bundle/dmg/"

