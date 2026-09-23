# Kraków 1795

Third-person stealth / intrigue / puzzle prototype. Godot 4.7, GDScript. Design: `docs/GDD.md`.

## Run
```
godot --path .            # play
godot -e --path .         # open editor
godot --headless --path . --quit-after 3000 -- --smoke   # headless loop test: plays the mission three ways
```

## Controls
WASD move, Shift sprint, Ctrl or C crouch, Z prone, E interact, F or left mouse attack (from behind: silent takedown),
1-4 dialogue replies, J or Tab journal, mouse look, Esc pause.

## Layout
- `data/` factions, origins, districts (JSON, loaded by `GameState`)
- `scripts/core/` `game_state.gd` (autoload, campaign state + day/night resolve), `main.gd` (phase switching)
- `scripts/stealth/` player controller, guard AI (vision cone + hearing + suspicion), safe house objective
- `scripts/city/` procedural greybox district (CSG). Swap for Blender glTF as assets land. A NavigationRegion3D is baked at runtime from the static collision.
- `scripts/npc/` townsfolk (`npc.gd`: schedules of posts from `data/npcs.json`), animals (`animal.gd`, `follow`), shared navmesh walking with avoidance (`walker.gd`), scripted storylines from `data/storylines.json` (`storyline.gd`). World clock: `GameState.clock_minutes` / `clock_scale` (night starts 21:00, 1 s = 1 game minute).
- `scripts/ui/` splash, main menu, options, character select with 3D preview, day briefing, sparse night HUD, pause, dawn report, journal (missions, discovered storylines, people, log)
- `scripts/mission/` mission runner, dialogue, interactables and the mission smoke test; missions in `data/missions.json`
- `scripts/city/dressing.gd` street dressing (trees, signs, shop fronts, café, benches, park, clutter); `flicker.gd` flame lights
- `assets/blender/build_animations.py` shared 64-clip animation library (`anim_library.glb`), retargeted to every figure at runtime by `assets.gd`; see `docs/ANIMATION.md`
- `docs/STEALTH.md` stealth audit and design plan; `docs/ANIMALS.md` animal model sources and licences
- `assets/blender/` source .blend files, `assets/models/` exported .glb

## Assets (all generated, all editable)
`assets/blender/build_assets.py` builds every model from primitives and exports glTF. Rerun after edits:
```
blender -b --python assets/blender/build_assets.py
```
Buildings carry baked PBR materials (lime plaster with grime, cracks and rising damp, brick, sandstone, beaver-tail
roof tiles, weathered oak, iron, leaded glass, snow, thatch, cobbles): procedural Cycles bakes cached in
`assets/textures/` (ignored by Godot; `-- --rebake` to redo, `-- --textures` to bake only, `-- --only a,b` for a
subset). Besides the Rynek set it builds district variants (`kaz_*`, `garb_*`, `dock_*`, `salt_barge`, `klep_*`,
`kan_house`, `wawel_wall`, `wawel_gate`), farmland (`farm_*`) and a tileable 4 m paving slab `ground_cobbles`.
Sheets: `blender -b --python assets/blender/render_sheets.py -- <outdir> [tenements,landmarks,props,districts,farm]`.
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

## Licence
- Code (GDScript, Python generators, project files): MIT, see `LICENSE`.
- Original art, generated models, documents and screenshots in this repository: CC BY 4.0
  (https://creativecommons.org/licenses/by/4.0/). Credit "Kraków 1795 project".
Change either if you prefer; nothing else in the repository constrains the choice.

## Attribution and third-party material
- **MakeHuman** base mesh, targets, skins, eyes, hair and clothes: the MakeHuman community, released under CC0
  (`makehuman_system_assets_cc0`). https://www.makehumancommunity.org/
- **MPFB2** (MakeHuman Plugin for Blender), used as a build-time tool only, not redistributed here: GPL v3.
  https://github.com/makehumancommunity/mpfb2
- **Godot Engine** 4.7: MIT. https://godotengine.org/
- **Blender** 5.2: GPL, used as a tool. https://www.blender.org/
- **Animals** (built by `assets/blender/build_animals.py` from sources fetched by `tools/fetch_animals.sh`;
  details in `docs/ANIMALS.md`):
  - Horse (and the harnessed horses): model and textures by **Lyndon Daniels** ("Realtime Rancher's 3D Model
    Pack"), rig by **ChadM**, OpenGameArt, CC0. https://opengameart.org/content/rigged-horse
  - Hound and spitz: recoloured **Quaternius** Wolf and Husky ("Ultimate Animated Animal Pack"), CC0.
    https://quaternius.com/packs/ultimateanimatedanimals.html
  - Cat: "Simple Cat" by **Drummyfish**, OpenGameArt, CC0. https://opengameart.org/content/simple-cat
  - Pigeon: "Low poly 3D Pigeon model (rigged + animated)" by **mujtaba-io**, OpenGameArt, CC0.
    https://opengameart.org/content/low-poly-3d-pigeon-model-rigged-animated-untextured
  - Crow: "Raven" by **Teh_Bucket**, OpenGameArt, CC0. https://opengameart.org/content/raven-0
  - Hawk: "Hawk Lp Rigged" by **Sherkiz**, via Poly Pizza, **CC-BY 3.0** (modified: rescaled, re-oriented,
    clips renamed). https://poly.pizza/m/RkN6MEbP6g
- Buildings, props, the carriage, the cart, the harness, interiors and clothing geometry are generated by scripts
  in `assets/blender/` from primitives; textures are baked procedurally. No third-party models or textures are
  included beyond the MakeHuman material and the animals above.
- Historical setting: Kraków after the Third Partition (1795). Names of real institutions and places are used
  as history; all characters are fictional.

## Building from a fresh clone
The generated models (`assets/models/*.glb`, about 1.3 GB) are not in git. Two ways to get them:

**A. Download** the `krakow-1795-models-<tag>.zip` asset from the latest
[GitHub release](https://github.com/r-melvin/krakow-1795/releases) and unzip it in the project root
(it contains `assets/models/` and `assets/ground/`), then `godot --headless --import --path .` and `godot --path .`.

**B. Rebuild** everything from the scripts:
1. Install Godot 4.7 and Blender 5.2, then the MPFB2 extension and the MakeHuman system assets pack (see
   *Characters* above).
2. `tools/build_all.sh` runs, in order: textures and buildings/props (`build_assets.py`), the district and farm
   sets, animals and the dragon (`--animals`), interiors (`build_interiors.py`), the third-party animal fetch
   and conversion (`tools/fetch_animals.sh`, `build_animals.py`), the animation library (`build_animations.py`),
   all characters (`build_characters.py`, the slow part: ~2-4 min each), and finally the Godot import.
   `tools/build_all.sh --no-characters` skips the people; `--only assets,interiors` picks stages.
3. `godot --path .`

`tools/make_release.sh <tag>` zips the models and attaches them to a GitHub release (maintainers).
