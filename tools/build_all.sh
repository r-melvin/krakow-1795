#!/usr/bin/env bash
# Rebuilds every generated model from the Blender scripts, then runs the Godot import.
# Usage: tools/build_all.sh [--no-characters] [--only assets,animals,interiors,third_party,animations,characters,import]
# Needs: blender (5.2) and godot (4.7) on PATH; MPFB2 + MakeHuman system assets installed for characters.
set -euo pipefail
cd "$(dirname "$0")/.."
STAGES="assets,animals,interiors,third_party,animations,characters,import"
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
if has assets;      then echo "== buildings, props, districts, farm";  blender -b --python assets/blender/build_assets.py; fi
if has animals;     then echo "== procedural animals and the dragon";   blender -b --python assets/blender/build_assets.py -- --animals; fi
if has interiors;   then echo "== interiors";                          blender -b --python assets/blender/build_interiors.py; fi
if has third_party; then echo "== third-party animals";                 tools/fetch_animals.sh && blender -b --python assets/blender/build_animals.py; fi
if has animations;  then echo "== animation library";                   blender -b --python assets/blender/build_animations.py; fi
if has characters;  then echo "== characters (slow)";                   blender -b --python assets/blender/build_characters.py; fi
if has import;      then echo "== godot import";                        godot --headless --import --path . >/dev/null 2>&1 || true; fi
echo "== done in $(( $(date +%s) - t0 )) s"
