# Character animation

One shared clip library drives all 125 human figures. It is authored procedurally in Blender on one reference
body built with the MPFB `game_engine` rig, exported as `assets/models/anim_library.glb`, and retargeted at runtime
onto each character's own skeleton by `scripts/core/assets.gd`.

```
blender -b --python assets/blender/build_animations.py            # ~8 s, writes anim_library.glb (64 clips, 3.5 MB)
blender -b --python assets/blender/build_animations.py -- --rebuild   # rebuild the cached reference body too
blender -b --python assets/blender/build_animations.py -- walk run    # bake only some clips (the file will then hold only those)
blender -b --python assets/blender/render_animations.py -- --out /tmp/sheets [--char watchman] [clip ...]
```

`render_animations.py` imports a real exported figure plus the library, retargets each clip with the same rule
as Godot, and writes one contact sheet per clip: 6 frames, side view on top, 3/4 front view below, on a ground
plane, with a 1 m ledge for `climb_short` and a wall for `crouch_hide`.

## 1. Rig check (the 125 human glbs as exported on 2026-09-23)

Checked by importing `figure_noble`, `figure_veteran_f`, `watchman`, `npc_f_03`, `cast_beggar` and
`figure_townswoman` in headless Blender, and by parsing the glTF skins of every glb in `assets/models`.

**Skeleton.** Every human glb has the same 53 bones in one skin (animals excluded):

```
Root, pelvis, spine_01, spine_02, spine_03, neck_01, head,
clavicle_{l,r}, upperarm_{l,r}, lowerarm_{l,r}, hand_{l,r},
{thumb,index,middle,ring,pinky}_{01,02,03}_{l,r},
thigh_{l,r}, calf_{l,r}, foot_{l,r}, ball_{l,r}
```

So bone names match across all characters and one library can drive all of them. There are no twist, corrective
or weapon bones.

**Rest poses do not match.** The names match but the rest orientations do not. Measured against `watchman`,
local rest rotations differ by up to 92 deg on `ball_*` (bone roll), 20-23 deg on `spine_01`, 10-15 deg on
`thigh_*` and `pelvis`, and 10-14 deg on `thumb_01_*`. The biggest gaps are on the women: wider hips, and MPFB
recomputes rolls for each body. `rest_arms_down()` only makes the arms consistent. Playing library rotation
tracks raw would twist feet and spines, so the clips are retargeted (section 3).

**Weights.**
- In every exported mesh, zero vertices have no influence.
- The glTF exporter caps influences at 4 per vertex and renormalises, so the exported files cannot have more
  than 4. In the source, `garment()` copies full body weights that can exceed 4. The truncation is silent but
  nothing visibly breaks.
- All garments carry an armature modifier and are parented to `Human_rig`. None are unskinned.
- Hats, hat trims, eye shadow, eyelashes, brows, eyes and teeth are 100 % on `head`. Hair meshes (e.g. `short01`)
  are skinned to `head`/`neck_01`/`spine_03`. That is correct.
- These parts are rigid (bound to one bone):

  | Part | Bone |
  |---|---|
  | buttons, buttonholes | `pelvis` .. `spine_03` |
  | collar | `neck_01` |
  | sash, sash knot | `spine_02` |
  | sash tails | `thigh_l` |
  | knee bands, boot tops | `calf_*` |
  | the whole musket | `hand_r` |

**Deformation.** `thigh` flexed 90 deg with the knee at 90 deg, elbow at 90 deg, and shoulder abducted 90 deg,
rendered on `figure_noble`, `figure_veteran_f` and `watchman`:
- Knee and elbow: acceptable. They lose some volume on the inside of the fold, as expected without corrective
  bones. Breeches, stockings and boots follow.
- Long coat skirts (noble, veteran_f, every long-coated NPC): the front panel stays hanging from
  pelvis/spine/calf weights. A raised thigh passes through it, which shows in `run`, `climb_short`, `sit_idle`,
  `crouch_*` and `prone_crawl`.
- Shoulder at 90 deg abduction on the noble's coat: a seam opens along the top of the shoulder, where
  `garment()` cut the coat between the sleeve and the body.
- Not rendered, but expected from the weights: the rigid collar on `neck_01` will clip into the jaw when the head
  pitches down hard (`bow`, `death_kneel`).
- Also expected, not rendered: the rigid sash on `spine_02` will intersect the coat when the torso bends forward
  (`sneak`, `bow`).
- The musket welded to `hand_r` rotates with the wrist. Its grip is 0.11 m to the side of the wrist and 0.30 m
  above the butt, so order arms (butt on the ground) is impossible and two-handed holds need a roll.

### Fixes needed in `assets/blender/build_characters.py` (not applied here)

1. **`drape()` / `garment()`: skin long coat skirts to the thighs.** For skirt vertices below the crotch
   (z < `thigh_l` head z), blend in the same-side thigh:
   `w_thigh = clamp((crotch_z - z) / 0.35, 0, 1) * 0.55` for front-panel vertices (y < 0), `* 0.25` for the back.
   Take the rest from the current pelvis/spine weights and renormalise. This stops thighs poking through in
   run, climb, sit and crouch.
2. **`garment()`: weld before thickening.** After cutting faces by `keep_fn`, run
   `bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)` on the coat before the solidify step. That closes
   the shoulder seam that opens when the arm is abducted.
3. **Collar and belt/sash weights.**
   - `build_clothes()` / collar: replace `_weight_to_bone(collar, rig, "neck_01")` with a 50/50 split between
     `neck_01` and `spine_03`.
   - `waist_belt()`: weight `belt`/`sash`/`sash_knot` 50/50 to `pelvis` and `spine_01` instead of `spine_02`
     alone.
   - `sash_tail`: `pelvis` 0.6 + `thigh_l` 0.4 instead of all `thigh_l`.
4. **`_musket()`: move the grip into the palm or detach the musket.**
   - Best: export the musket as its own `musket.glb` and let Godot hang it on a `BoneAttachment3D` for `hand_r`,
     so it can be dropped when a guard is knocked down, and so order arms works.
   - Minimum: centre the stock wrist on the palm (`x = hand.x + 0.01`, not `hand.x - 0.11`). If you change this,
     re-tune `musket_hand()` in `build_animations.py`, which models the current offset.
5. **Canonical bone rolls (optional).** After `add_builtin_rig()`, in edit mode align the rolls of `ball_*`,
   `foot_*` and `spine_*` to fixed world axes (`eb.align_roll(...)`). Rests then differ only by real anatomy.
   Runtime retargeting stays in place for the thigh and pelvis angles.
6. **`make_animations()`: stop baking per-character clips (optional).** The library replaces `idle`/`walk`.
   Keep `sentry` only, because townsfolk use it as "holding a lantern" (the chaplain, the priest). Dropping the
   other two makes each glb a little smaller. `Assets.resolve()` already falls back to them if the library is missing.

## 2. The library: source, licence, clips

**Source.** Every clip is procedural, authored in `build_animations.py`, and CC0 like the rest of the generated
assets. No mocap is used and nothing from Mixamo (not redistributable). Retargeting a CC0 set (Quaternius
Universal Animation Library, CMU BVH) was considered and not taken: those sets cover generic locomotion but none
of the period-specific clips (musket drill and reload, period bow, sweeping, haggling). They would also need a
bone map plus rest-pose alignment onto a rig whose rests differ per body anyway. The procedural rig below
already handles that.

**How it is authored.**
- A pose is a flat dict of anatomical parameters. Each bone rotates about world-aligned axes carried by its
  parent, so "`kL` 40" always bends the left knee, whether the body is upright, prone or on its back.
- Legs use analytic two-bone IK with world-space ankle targets, which keeps stance feet planted with no skating.
  The foot has a heel-strike / flat / heel-off roll, and the toes stay flat during heel rise.
- Hands can use IK too, for the ground in prone and crawl clips, the 1 m ledge, a broom handle, a victim's neck,
  and the musket's fore-end. The right hand can instead be driven by a musket pose (butt position, elevation,
  yaw, tilt, roll), inverted through the weld geometry of `_musket()`.
- Locomotion is generated from gait parameters:
  - asymmetric stride with a stance fraction and a Hermite swing arc that includes swing-leg retraction;
  - pelvis bob, sway, roll and yaw, with spine counter-twist;
  - arm swing with lag, and elbows that flex more on the forward swing;
  - gaze stabilisation on the head.
- Keyed clips interpolate every parameter with monotone cubic (PCHIP) splines. Extremes ease in and out without
  overshoot, and named poses (`stand`, `crouch`, `prone`, `lie_back`...) are complete so keys never leak.

**Clips** (30 fps, in place, only the pelvis translates; L = loops, others hold their last frame):

| group | clip (seconds) |
|---|---|
| locomotion | `idle` 6 L, `idle_alert` 2.4 L, `walk` 1.0 L (1.08 m/s), `walk_fast` 0.74 L (1.9 m/s), `jog` 0.7 L (2.6 m/s), `run` 0.62 L (4.8 m/s), `walk_carry` 1.1 L (bundle, forward lean), `carry_basket` 1.05 L |
| stealth | `sneak` 0.9 L (1.4 m/s), `crouch_idle` 3 L, `crouch_hide` 3.6 L (huddled, peeking), `prone_idle` 4 L, `prone_crawl` 1.3 L (0.7 m/s), `prone_crawl_side` 1.6 L, `crouch_crawl` 1.2 L (hands and knees) |
| transitions | `stand_to_crouch` 0.5, `crouch_to_stand` 0.6, `crouch_to_prone` 1.0, `prone_to_crouch` 1.1, `climb_short` 1.8 (1 m ledge; the pelvis ends 1 m up and 0.6 m forward), `get_up` 2.4 (from the back), `get_up_prone` 1.9 |
| player weapons | `attack_swing` 0.85 (cudgel), `attack_thrust` 0.6, `takedown` 2.0 (rear choke, lowers the victim), `sabre_draw` 0.9, `sabre_slash` 0.7, `sabre_parry` 0.55, `knife_stab` 0.55, `pistol_draw` 0.8, `pistol_aim` 2 L, `pistol_fire` 0.6, `block` 0.9 |
| guard | `guard_sentry` 5 L (shoulder arms), `guard_march` 0.72 L (1.8 m/s), `guard_alert_look` 3.2 L (port arms, scanning), `guard_seize` 1.2, `musket_ready` 2.4 L, `musket_aim` 2 L, `musket_fire` 0.9, `musket_reload` 4.2, `bayonet_thrust` 1.0, `musket_butt` 0.9 |
| being attacked | `hit_react` 0.55, `hit_react_back` 0.55, `stagger` 1.3, `shoved` 0.9, `grabbed` 1.5, `takedown_victim` 2.0 (ends lying) |
| falls, deaths | `knocked_down` 1.3 (backwards), `knocked_down_forward` 1.2, `stumble` 1.1, `fall_land_roll` 1.5, `death_fall` 1.7 (backwards), `death_fall_forward` 1.6, `death_kneel` 2.6, `death_musket` 1.8 |
| town life | `talk_gesture_a` 3.2 L, `talk_gesture_b` 3.0 L, `haggle` 3.4 L, `wave` 1.8, `bow` 2.6 (period bow: right foot back, hand across the chest, left arm out), `sit_idle` 5 L (0.47 m seat), `sweep` 1.6 L |

Contact sheets for every clip on the watchman, plus a few on `figure_townswoman`, are in the session scratchpad
(`.../scratchpad/anim/*.png`, `.../scratchpad/anim_female/*.png`). Re-create them with `render_animations.py`.

## 3. Godot side (`scripts/core/assets.gd`)

- `Assets.character(name)` works as before. It also attaches the AnimationLibrary `lib`, one per model name and
  shared by every instance of that model. The library glb is loaded once.
- A clip is retargeted the first time any instance of that model plays it. That costs a few milliseconds.
- **Retarget rule.** Each bone keeps the library rotation as a world-space delta from rest:

  ```
  q_target = A * q_lib * B
  A = Gt(parent)^-1 * Glib(parent)
  B = Glib(bone)^-1 * Gt(bone)
  ```

  G are global rest rotations. Only the pelvis keeps a translation track, applied as a delta from rest and
  scaled by pelvis height.
- The characters' own `idle`/`walk`/`sentry` stay in the default library as fallbacks. `resolve()` tries
  `lib/<clip>`, then the model's own clip, then `FALLBACK`.

**API**

| call | what it does |
|---|---|
| `play(pivot, clip, speed, blend=0.2)` | Cross-fades to a state clip. Ignored while an action runs. |
| `play_move(pivot, clip, ground_speed)` | Locomotion. The playback rate is `ground_speed / CLIP_SPEED[clip]`, clamped to 0.55-1.7. |
| `play_action(pivot, clip, speed, hold)` | One-shot clip. Returns its length. `hold` keeps the last frame (downed, beaten) until `clear_action()` or another action. |
| `is_action()`, `action_clip()`, `clear_action()` | Query or cancel the current action. |
| `has_clip()` | True when the clip resolves to a library clip. |
| `clip_for(state)` | Looks up a clip name in `STATE_CLIP`. |

- `LOOPING` lists the looping clips.
- In `--smoke` runs, `[smoke] anim player=<clip> guard=<clip>` is printed for every new combination. Figures are
  tagged with the `anim_role` meta.

**What each script plays**

- **`player.gd`**
  - Moving:
    - `walk` below 1.6 m/s, otherwise `walk_fast` (3 m/s walk = 1.58x);
    - `run` while sprinting;
    - `sneak` when crouched;
    - `prone_crawl` when prone (new action `prone` on Z, added to `project.godot`; capsule 0.7 m, 0.35x speed,
      noise 0.075 = half of crouch, visibility 0.35, head at 0.3 m; C/Ctrl leaves prone);
    - `walk_carry` while `carrying`.
  - Still: `idle`, `crouch_idle`, `prone_idle`, or `crouch_hide` when crouched within 0.5 m of a wall (8 rays at
    knee height; the figure turns its back to the wall).
  - Stance changes play `stand_to_crouch` / `crouch_to_stand` / `crouch_to_prone` / `prone_to_crouch` while
    still, and are dropped as soon as the player moves.
  - Attacks:
    - rear takedown: `takedown` (lock raised from 0.9 to 1.4 s so the choke reads);
    - fair fight: `attack_swing` (70 %) or `attack_thrust`;
    - miss: `attack_swing`.
  - Struck: `hit_react`, or `hit_react_back` when hit from behind. At health 0, `knocked_down` is held and
    `Mission.fail("Beaten by the watch")` runs as before.
  - The old `_figure.scale.y` crouch squash is gone.
- **`guard.gd`**
  - CALM: `guard_march` while moving, `guard_sentry` at post or waypoint.
  - CURIOUS: `guard_alert_look`.
  - SEARCHING: `guard_march`, or `guard_alert_look` when stopped.
  - ALARM: `run` while chasing, `musket_ready` in reach.
  - Each swing plays `musket_butt` (every third swing `bayonet_thrust`, visual only).
  - `guard_seize` plays once when held close for half of CATCH_TIME.
  - `take_hit` plays `hit_react`.
  - Downed: `knocked_down` in a fair fight, `takedown_victim` after a rear takedown, both held.
  - On waking, `get_up` plays and the guard stands still for its 2.4 s (`_rising`).
  - The stealth logic is otherwise unchanged. There is no musket fire in the game, so `musket_aim` /
    `musket_fire` / `musket_reload` are available but unused.
- **`npc.gd`**
  - Idle clip by data:
    - activity or behaviour `sit`: `sit_idle`;
    - role mentions rumours, gossip or a neighbour: `talk_gesture_a` / `talk_gesture_b` (by id hash);
    - merchant, stall or loaves: `haggle`;
    - lookout, watching, informer or loitering: `idle_alert`;
    - otherwise `idle`.
  - A non-`idle` `clip` field (e.g. `sentry`, the chaplain's lantern) is kept.
  - Walking plays `walk`, `jog` for `run` steps, or `carry_basket` for the water carrier.
  - Takedown plays `takedown_victim` (held), then `get_up` before the NPC resumes.
  - Storyline `play` clips pass through unchanged.
- **`walker.gd`** makes no animation calls and is unchanged.

`data/npcs.json` has no `pose` field. The mapping uses `activity`, `behaviour`, `role` and `clip`.

## 4. Validation

```
blender -b --python assets/blender/build_animations.py          # no Traceback (the glTF exporter prints a harmless
                                                                # "MeshOptimizer is not available" line)
godot --headless --path . --import
godot --headless --path . --quit-after 3000 -- --smoke          # 0 SCRIPT ERROR; underworld/street/salon reach DAWN
godot --path . --quit-after 2500 -- --smoke --shot=DIR          # --quit-after 900 ends before main.gd reaches _shots()
```

In shot mode (`--smoke --shot=`), the player walks in place (`walk_fast`) whenever idle, so
`shot_player_closeup.png` shows the walk cycle.

## 5. Known weaknesses

- The clips are procedural. Locomotion, crouch and prone read well. The combat and falls are clean but stylised
  keyframe animation, not mocap weight.
- Hands have one curl value per hand, not per-finger acting.
- No props except the guard's welded musket. Cudgel, sabre, knife, pistol, broom and basket clips move empty
  hands. Add `BoneAttachment3D` props on `hand_r` in Godot.
- The musket weld forces compromises. `musket_reload` rams along the upper barrel, not at the muzzle, and in
  `knocked_down` / `death_*` / `prone_*` the musket passes through the ground.
- Long-coat skirts clip through raised thighs until fix 1 above is applied.
- `crouch_hide` puts the back to the wall. It does not slide along it.
- `climb_short`, `fall_land_roll` and `stumble` contain travel in the pelvis track (up to 1.2 m), so they need the
  gameplay capsule moved to match. No gameplay uses them yet.
- `walk_fast` at the player's 3 m/s is played at 1.58x, so there is slight foot slide.
- Prone crawling uses the crouch collision rules. There is no crawl-under-obstacle gameplay, so `crouch_crawl`
  is unused.
- The HUD's key hints (`scripts/ui/hud.gd`) do not mention Z for prone yet.
