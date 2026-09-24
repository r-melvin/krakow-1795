#!/usr/bin/env bash
# Rebuilds every generated model from the Blender scripts, then runs the Godot import.
# Usage: JOBS=8 tools/build_all.sh [--no-characters] [--only layout,assets,animals,interiors,props,third_party,animations,audio,characters,import]
# Asset and character builds run JOBS Blender processes in parallel (default 8).
# Needs: blender (5.2) and godot (4.7) on PATH; MPFB2 + MakeHuman system assets installed for characters.
set -euo pipefail
cd "$(dirname "$0")/.."
STAGES="layout,assets,animals,interiors,props,third_party,animations,audio,characters,import"
for a in "$@"; do
  case "$a" in
    --no-characters) STAGES="${STAGES/characters,/}" ;;
    --only=*) STAGES="${a#--only=}" ;;
    --only) shift; STAGES="$1" ;;
    -h|--help) sed -n 2,4p "$0"; exit 0 ;;
  esac
done
has() { [[ ",$STAGES," == *",$1,"* ]]; }
t0=$(date +%s)
mkdir -p assets/models assets/textures assets/ground
JOBS="${JOBS:-8}"
if has layout;      then echo "== city layout";                        python3 tools/gen_city_layout.py; fi
if has assets; then
  echo "== textures (bake once, shared cache)"; blender -b --python assets/blender/build_assets.py -- --textures >/dev/null
  echo "== buildings, props, districts, farm ($JOBS parallel)"
  NAMES=$(blender -b --python-expr "import sys; sys.path.insert(0,'assets/blender'); sys.argv=['x','--','--textures']; import build_assets as b; print('NAMES', ' '.join(n for n,_ in b.BUILDS))" 2>/dev/null | sed -n 's/^NAMES //p')
  echo "$NAMES" | tr ' ' '\n' | awk -v j="$JOBS" '{g[NR%j]=g[NR%j] (g[NR%j]==""?"":",") $0} END{for(k in g) print g[k]}' \
    | xargs -P "$JOBS" -I{} sh -c 'blender -b --python assets/blender/build_assets.py -- --only {} >/dev/null 2>&1 || echo "FAILED group: {}"'
fi
if has animals;     then echo "== procedural animals and the dragon";   blender -b --python assets/blender/build_assets.py -- --animals; fi
if has interiors;   then echo "== interiors";                          blender -b --python assets/blender/build_interiors.py; fi
if has props;       then echo "== vendor, window and kit props";        for b in build_vendor_props build_window_props build_kit_props; do blender -b --python assets/blender/$b.py >/dev/null 2>&1 || echo "FAILED $b"; done; fi
if has third_party; then echo "== third-party animals";                 tools/fetch_animals.sh && blender -b --python assets/blender/build_animals.py; fi
if has animations;  then echo "== animation library";                   blender -b --python assets/blender/build_animations.py; fi
if has audio;       then echo "== audio (procedural synthesis)";        python3 tools/gen_sfx.py; fi
if has characters; then
  echo "== characters ($JOBS parallel)"
  CH=$(blender -b --python-expr "import sys; sys.path.insert(0,'assets/blender'); import build_characters as b; print('NAMES', ' '.join(b.ALL))" 2>/dev/null | sed -n 's/^NAMES //p')
  echo "$CH" | tr ' ' '\n' | xargs -P "$JOBS" -I{} sh -c 'blender -b --python assets/blender/build_characters.py -- {} >/dev/null 2>&1 || echo "FAILED character: {}"'
fi
if has import; then
  echo "== godot import (twice: the second pass applies tools/import_settings.py texture settings)"
  tools/with_cpu.sh godot --headless --import --path . >/dev/null 2>&1 || true
  python3 tools/import_settings.py
  tools/with_cpu.sh godot --headless --import --path . >/dev/null 2>&1 || true
fi
echo "== done in $(( $(date +%s) - t0 )) s"
