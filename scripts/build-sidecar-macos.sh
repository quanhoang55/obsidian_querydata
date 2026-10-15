#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
target_triple="$(rustc -vV | sed -n 's/^host: //p')"
binary_name="obsidianquery-backend-${target_triple}"

cd "$project_root/backend"
uv sync --group desktop
OBSIDIANQUERY_BINARY_NAME="$binary_name" uv run --group desktop pyinstaller \
  --noconfirm --clean --distpath dist/desktop --workpath build/desktop desktop.spec
mkdir -p "$project_root/frontend/src-tauri/binaries"
cp "dist/desktop/$binary_name" "$project_root/frontend/src-tauri/binaries/$binary_name"
chmod +x "$project_root/frontend/src-tauri/binaries/$binary_name"
echo "Built frontend/src-tauri/binaries/$binary_name"
