#!/usr/bin/env bash
# Refreshes docs/screenshots/ from the running game (needs a working GPU / Vulkan device) and prints the
# windowed performance line. One Godot run per capture set, all through the GPU lock.
# Usage: tools/refresh_screenshots.sh [--no-commit]
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${OUT:-/tmp/krakow-1795-shots}
rm -rf "$OUT"; mkdir -p "$OUT"
S=docs/screenshots
j() { magick "$1" -quality 86 "$2"; }
run() { tools/with_gpu.sh timeout 900 godot --path . --quit-after 3000 -- --smoke "$@" 2>&1 | grep -E "SCRIPT ERROR|\[smoke\] perf" | head -5 || true; }

echo "== windowed perf (plain night)"
tools/with_gpu.sh timeout 900 godot --path . --quit-after 6000 -- --perf 2>&1 | grep -E "\[smoke\] perf" | tail -3

echo "== in-engine shots";           run --shot="$OUT/game"
echo "== UI screens";                run --shot-ui="$OUT/ui" --shot-journal="$OUT/ui"
echo "== campaign UI";               run --shot-ui="$OUT/campaign"
echo "== stealth cues";              run --stealth-shot="$OUT/stealth" --intel-shot="$OUT/stealth"
echo "== kit and traversal";         run --kit-shot="$OUT/kit"
echo "== street and window life";    run --street-shot="$OUT/street" --window-shot="$OUT/window"
echo "== vendors and dressing";      run --vendor-shot="$OUT/vendors" --dress-shot="$OUT/dressing"
echo "== interiors";                 run --interior-shot="$OUT/interiors"
echo "== weather presets";           run --weather-shot="$OUT/weather"
echo "== outer city";                run --outer-shot="$OUT/outer"

echo "== copying into $S"
for d in game ui campaign stealth kit street window vendors dressing interiors weather outer; do
  [ -d "$OUT/$d" ] || continue
  for f in "$OUT/$d"/*.png; do [ -f "$f" ] && j "$f" "$S/${d}_$(basename "$f" .png).jpg"; done
done
ls "$S" | wc -l
if [[ "${1:-}" != "--no-commit" ]]; then
  git add "$S" && git -c user.name=r-melvin -c user.email=40235254+r-melvin@users.noreply.github.com \
    commit -q -m "Refresh screenshots" && git push -q origin HEAD && echo "== pushed"
fi
