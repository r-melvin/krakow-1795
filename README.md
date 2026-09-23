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
- `scripts/city/` procedural greybox district (CSG). Swap for Blender glTF as assets land. A NavigationRegion3D is baked at runtime from the static collision.
- `scripts/npc/` townsfolk (`npc.gd`: schedules of posts from `data/npcs.json`), animals (`animal.gd`, `follow`), shared navmesh walking with avoidance (`walker.gd`), scripted storylines from `data/storylines.json` (`storyline.gd`). World clock: `GameState.clock_minutes` / `clock_scale` (night starts 21:00, 1 s = 1 game minute).
- `scripts/ui/` origin select, day panel, night HUD
- `assets/blender/` source .blend files, `assets/models/` exported .glb

## Assets (all generated, all editable)
`assets/blender/build_assets.py` builds every model from primitives and exports glTF. Rerun after edits:
```
blender -b --python assets/blender/build_assets.py
```
Contact sheets in `docs/screenshots/*.jpg`. Era references baked into the generator:
Sukiennice in its Renaissance state (attyka parapet, end loggias, no side arcades), St Mary's with its unequal
towers, the Town Hall still standing (demolished 1820), St Adalbert's dome, kamienice with attyka / gable /
mansard roofs, Austrian infantry in white with tricornes, origins in kontusz, sukmana, cassock, frock coat.

## Characters (MakeHuman via MPFB2)
`assets/blender/build_characters.py` builds every person on the MakeHuman base mesh (CC0) through the MPFB2
Blender extension: parametric body and face, skin texture, eyes, brows, lashes, teeth, hair, a game-engine
skeleton, an arms-down rest pose, and idle / walk / sentry clips. Era clothing is cut from MakeHuman's
body-conforming helper geometry and thickened, so it follows the skin and cannot clip. Hats come from the
scalp faces or the pack's cocked hat. Exported as glTF with textures (2048 px), front facing +Z; the Godot
side turns them with `Assets.character()` and drives clips with `Assets.play()`.

One-time setup (already done on this machine):
```
blender -b --command extension install-file -r user_default -e mpfb.zip     # from extensions.blender.org
# then extract makehuman_system_assets_cc0.zip into ~/.config/blender/5.2/extensions/.user/user_default/mpfb/data
```
Rebuild all or some: `blender -b --python assets/blender/build_characters.py [-- watchman figure_noble | base | cast | townsfolk | npc]`.
Rosters in that file: `CHARACTERS` (player origins, man and woman each, and the watchman), `CAST` (faction leaders,
villains, spies, beggars, urchins, children), `TOWNSFOLK` (shopkeepers, innkeeper, tradesmen), `crowd_specs()`
(seeded background townsfolk with varied skin, age, hair and cloth). Generated character files are not committed
(see .gitignore); run the build once after cloning. Animals and the Wawel dragon: `blender -b --python assets/blender/build_assets.py -- --animals`.
Check renders: `render_characters.py -- <outdir> <names>` (turnaround + face) and `render_lineup.py -- <outdir>`.

## Blender pipeline
1. Model in metres, Z up in Blender, front facing -Y; export glTF 2.0 (.glb) with "+Y up" (default). Blender -Y lands on Godot +Z.
   `blender -b --python assets/blender/build_assets.py` regenerates all placeholder assets.
2. Name collision meshes with `-col` suffix (Godot imports them as StaticBody3D colliders). Use `-colonly` for invisible collision.
3. Drop `.glb` in `assets/models/`. Godot imports automatically. Instance in `greybox_district.gd` in place of the matching `_box()` call.
4. Target scale reference: tenement floor 3.5 m, Sukiennice hall ~100 m long (greybox uses 30 m for playability).
