#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"

"$project_root/scripts/build-sidecar-macos.sh"
cd "$project_root/frontend"
npm install
npm run tauri icon src-tauri/icons/icon-source.png

if ! npm run tauri build -- --bundles dmg; then
  echo "Tauri's DMG tool failed; creating a compatible HFS disk image fallback."
  app_path="$project_root/frontend/src-tauri/target/release/bundle/macos/ObsidianQuery.app"
  architecture="$(uname -m)"
  staging_dir="$(mktemp -d /tmp/obsidianquery-dmg.XXXXXX)"
  output_path="$project_root/frontend/src-tauri/target/release/bundle/dmg/ObsidianQuery_0.1.0_${architecture}.dmg"
  temporary_output="${staging_dir}.dmg"
  codesign --force --deep --sign - "$app_path"
  ditto "$app_path" "$staging_dir/ObsidianQuery.app"
  ln -s /Applications "$staging_dir/Applications"
  hdiutil makehybrid -hfs -hfs-volume-name ObsidianQuery -o "$temporary_output" "$staging_dir"
  mv -f "$temporary_output" "$output_path"
fi

echo "DMG output: frontend/src-tauri/target/release/bundle/dmg/"

