# Kraków 1795

Third-person stealth / intrigue / puzzle prototype. Godot 4.7, GDScript. Design: `docs/GDD.md`.

## Run
```
godot --path .            # play
godot -e --path .         # open editor
godot --headless --path . --quit-after 2000 -- --smoke   # headless loop test
```

## Controls
WASD move, Shift sprint, Ctrl or C crouch, mouse look, Esc release mouse.

## Layout
- `data/` factions, origins, districts (JSON, loaded by `GameState`)
- `scripts/core/` `game_state.gd` (autoload, campaign state + day/night resolve), `main.gd` (phase switching)
- `scripts/stealth/` player controller, guard AI (vision cone + hearing + suspicion), safe house objective
- `scripts/city/` procedural greybox district (CSG). Swap for Blender glTF as assets land.
- `scripts/ui/` origin select, day panel, night HUD
- `assets/blender/` source .blend files, `assets/models/` exported .glb

## Blender pipeline
1. Model in metres, Z up in Blender, front facing -Y; export glTF 2.0 (.glb) with "+Y up" (default). Blender -Y lands on Godot +Z.
   `blender -b --python assets/blender/build_assets.py` regenerates all placeholder assets.
2. Name collision meshes with `-col` suffix (Godot imports them as StaticBody3D colliders). Use `-colonly` for invisible collision.
3. Drop `.glb` in `assets/models/`. Godot imports automatically. Instance in `greybox_district.gd` in place of the matching `_box()` call.
4. Target scale reference: tenement floor 3.5 m, Sukiennice hall ~100 m long (greybox uses 30 m for playability).
