#!/usr/bin/env bash
# Zips the generated models and attaches them to a GitHub release (creating it if needed).
# Usage: tools/make_release.sh <tag> [--notes "text"]
# The zip unpacks over the project root: assets/models/*.glb and assets/ground/*.png.
set -euo pipefail
cd "$(dirname "$0")/.."
TAG="${1:?usage: tools/make_release.sh <tag> [--notes text]}"; shift || true
NOTES="Generated models for ${TAG} in three zips (world, people-a, people-b): unzip all three in the project root, then: godot --headless --import --path . && godot --path ."
[[ "${1:-}" == "--notes" ]] && NOTES="$2"
mkdir -p export
# GitHub caps a release asset at 2 GiB, so the models ship as three zips that all unpack over the project root:
#   -world   buildings, props, interiors, animals, vehicles, animation library, ground maps
#   -people-a  player figures, leaders, cast, the watchman
#   -people-b  crowd, townsfolk and district figures
python3 - "$TAG" <<'PY'
import sys, glob, zipfile, os
tag = sys.argv[1]
files = sorted(glob.glob("assets/models/*.glb") + glob.glob("assets/ground/*.png"))
def part(f):
    b = os.path.basename(f)
    if b.startswith(("figure_", "hist_", "cast_", "watchman")): return "people-a"
    if b.startswith(("npc_", "town_", "dist_")): return "people-b"
    return "world"
groups = {}
for f in files: groups.setdefault(part(f), []).append(f)
for name, fs in groups.items():
    out = f"export/krakow-1795-models-{tag}-{name}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for f in fs: z.write(f)
    mb = os.path.getsize(out) / 1048576
    print(f"== {out} {mb:.0f} MB ({len(fs)} files)")
    assert mb < 2000, f"{out} exceeds the 2 GiB asset limit; split further"
PY
ZIPS=$(ls export/krakow-1795-models-${TAG}-*.zip)
if gh release view "$TAG" >/dev/null 2>&1; then
  gh release upload "$TAG" $ZIPS --clobber
else
  gh release create "$TAG" $ZIPS --title "$TAG" --notes "$NOTES"
fi
echo "== attached $(echo $ZIPS | wc -w) zips to release $TAG"
