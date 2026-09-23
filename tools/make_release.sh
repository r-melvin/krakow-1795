#!/usr/bin/env bash
# Zips the generated models and attaches them to a GitHub release (creating it if needed).
# Usage: tools/make_release.sh <tag> [--notes "text"]
# The zip unpacks over the project root: assets/models/*.glb and assets/ground/*.png.
set -euo pipefail
cd "$(dirname "$0")/.."
TAG="${1:?usage: tools/make_release.sh <tag> [--notes text]}"; shift || true
NOTES="Generated models for ${TAG}. Unzip in the project root, then: godot --headless --import --path . && godot --path ."
[[ "${1:-}" == "--notes" ]] && NOTES="$2"
mkdir -p export
ZIP="export/krakow-1795-models-${TAG}.zip"
rm -f "$ZIP"
echo "== zipping $(ls assets/models/*.glb | wc -l) models"
zip -q -r "$ZIP" assets/models/*.glb assets/ground/*.png
ls -l "$ZIP" | awk '{printf "== %s %.0f MB\n", $9, $5/1048576}'
if gh release view "$TAG" >/dev/null 2>&1; then
  gh release upload "$TAG" "$ZIP" --clobber
else
  gh release create "$TAG" "$ZIP" --title "$TAG" --notes "$NOTES"
fi
echo "== attached to release $TAG"
