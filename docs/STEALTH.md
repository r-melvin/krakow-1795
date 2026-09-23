# Stealth review and design

Audit of the stealth systems in the playable slice, what the classics of the genre do that we do not,
and a phased plan to apply it to Kraków, 1795. Written against the code in `scripts/stealth/`,
`scripts/npc/`, `scripts/mission/` and `data/missions.json`.

## 1. What exists today

Phases A, B, C, D and G of section 4 are in (phases E and F are not: see "Hooks" below). Every number lives in
`data/stealth.json`; the files are `scripts/stealth/` (perception.gd, guard.gd, player.gd, watch.gd, hiding_spot.gd,
distraction.gd, stealth_smoke.gd), `scripts/ui/hud.gd` (cues), `scripts/city/greybox_district.gd` (registration and
placement), `population.gd` (crowd query) and `flicker.gd` (dousing).

### Perception (A)
- **Visibility** = posture (stand 1.0, crouch 0.6, prone 0.3, sit 0.7) x light x crowd, 0 inside a hiding spot.
  **Light** is sampled 10x a second at the chest from every OmniLight in group `flame_lights` (lanterns, braziers,
  candle windows, and, registered 0.3 s after build, the dressing lamps, interiors and carriage lamps) with Godot's omni
  attenuation and an occlusion ray, plus the moon (group `moon_light`, 0.25 when a ray toward it is clear), x0.45,
  clamped 0.15..1. Measured: lantern pool 1.00, covered passage 0.15, open moonlight 0.25.
- **Noise** = gait (crouch 0.15, walk 0.45, sprint 1.0, prone 0.075) x surface: cobbles 1.0, snow 0.6, gravel 1.2,
  planks 1.3 (interiors), straw 0.4, mud 1.1, from the `surface` meta on the collider underfoot or the nearest
  `surface_patch` (the dressing's straw, gravel, snow and muck props, tagged by the district). Walls halve hearing.
- **Two-zone cone**: near 0-5 m, 90 deg sees any posture; far 5-14 m, 60 deg sees standing, crouching only at light
  >= 0.75, never prone; peripheral 110 deg (60 % range) catches sprinting. Cover is two rays (head, chest): head only
  0.5, chest only 0.7. Guards sweep their head (+-50 deg; sentries +-35 deg, slower) while standing at a waypoint.
- **Barks**: German/Polish lines in a speech bubble on each state change, lure, body, lamp, runner; only the first of
  an alert episode also goes to the message line (and so the journal).

### Hiding (B)
- 8 hiding spots (`E` hide / leave, or `H`): the east handcart heaped with straw, the Town Hall hay cart, two barrel
  pairs, under the inn-yard coach, the woodpile lean-to, a cellar hatch in the NW alley, a doorway niche on the north
  row. Visibility 0, the camera moves to a peek point. A guard who had the player in view within 1.5 s of going in
  searches the spot and pulls them out; during Evasion guards prod nearby spots (20 %).
- 6 benches (`E` sit): sitting, visibility x0.25 with a townsman within 1.8 m.
- **Lean** (`Q` / `R`, standing or crouched, still): head and camera shift 0.45 m sideways; guards see only the head.
- **Crowd**: 3+ townsfolk within 2.5 m (standing, or walking the player's way), not crouched, sprinting, fighting or
  aiming: x0.35 (`Population.crowd_count`).
- Stealth props never steal the interact target from mission people and props (meta `low_priority`).

### Alert phases, runner, bodies (C)
- `watch.gd` (one per district, group `watch`): CALM -> ALARM (guards within 30 m converge; a runner is sent) ->
  EVASION (3 s without a sighting; 60 s of guards visiting hiding spots and open points within 9 m of the ghost) ->
  CAUTION (3 game-minutes: patrol speed and view x2) -> CALM.
- **Crackdown rises only when a runner reaches the Corporal's post** (St Mary's, (24, 0, -10)): the watch then adds
  crackdown +5 and calls `GameState.raise_alarm` (the night's alarm count). The runner is the nearest guard other than
  the one fighting (a lone guard goes once he has lost the player); a rear takedown is allowed on him from behind.
- Downed guards: hold `E` to drag (half speed); let go near a hiding spot and the body is stashed there. A patrol who
  sees a body goes Searching, kneels over it (it wakes 4 s later), sets CAUTION and sends a runner. A guard waking
  up goes Searching and sets CAUTION.

### Distractions (D)
- **Stone** (hold `G` / right mouse to aim with an arc preview, release): lands with a ring; the nearest guard in
  earshot (8 m x loudness x 2, walls halve) walks over and looks about for 8 s; others glance.
- **Doused lamp** (`E` at any of the 10 street lanterns): off for 30 s (the lamplighter relights it); a guard who
  sees the dark lamp walks over and relights it (5 s) with his back to the square.
- **Barrel** (3 loose ones, `E` kick): rolls away from the player, rumbling, bounces off walls; a guard runs to it.
- **Door knock** (4 tenement doors away from the entrances): a townsman opens and keeps the guard who comes 10 s.
- **Loose horse** (the saddle horse by St Adalbert's, `E` untie): wanders off; the nearest guard follows it 8 s.
- **Church bell**: `watch.ring_bell()` for missions: sound masked 4 s, guards look at the tower.
  `watch.mask_sound(secs)` alone masks. The decoy pamphlet flow is unchanged.

### On-screen (G)
- A thin arc low in the screen centre, under the figure: its length is visibility, its colour noise (white -> amber),
  a dot when hidden. A chevron at the screen edge for the most alarmed guard when he is off-screen. No new text.
- Ground rings for 2 s at stones, barrels, knocks, the horse, the bell and sprinting steps.
- Cones: the near zone always; the far zone fades in with suspicion (hidden when calm).
- The last-known ghost: a rim-lit outline where the watch thinks the player is (Evasion, or a lone searching guard).

### Hooks for phases E and F
- Watch signals: `phase_changed`, `sound_event`, `player_spotted`, `body_found`, `runner_sent`, `runner_arrived`,
  `runner_stopped`, `hiding_changed`, `lamp_changed`, `barked`; `watch.flags` mirrored into `Mission.flags` as
  `stealth_<name>` (e.g. `stealth_phase`, `stealth_runner_arrived`).
- `guard.enforcer` (sees through the disguise, red-tinted cone) and `guard.sight_modifiers` (Callables
  `(guard, player) -> float`) for zone permits; `guard.task` / `set_task()` for scripted errands.

### Smoke
`godot --headless --path . --quit-after 3000 -- --smoke` runs `stealth_smoke.gd` beside the mission smoke, each check
in a private sandbox world (SubViewport with its own World3D; sandbox actors are outside the `guards` / `player`
groups and have no GameState / Mission side effects), printing `[smoke] stealth ...` lines ending OK / FAIL.
`--stealth-shot=/dir` (windowed) saves `stealth_arc_light`, `_arc_dark`, `_hiding`, `_cone_curious`, `_ring`,
`_ghost`, `_chevron`.

### Known limits
- One game minute is one real second, so Caution lasts 3 s at the default; raise `phases.caution_minutes` if it
  should be felt. Side-street barricades in Caution are not built.
- Only guards count as bodies (not the informer or other takedown targets).
- Guards use the navmesh for errands and the runner but still walk their patrol legs in straight lines.

## 2. What the classics teach

| Game | Mechanic | Lesson for us |
|---|---|---|
| Thief (1998) | Light gem, surface-dependent footstep noise, guard barks that narrate alert level, three alert stages with searches | Visibility must be *light*, not just posture. Sound must depend on surface (cobbles, snow, planks, gravel). Guards should *say* what they think. |
| Splinter Cell | Light/sound meters on the HUD, shooting out lights, whistling to lure | A meter or a diegetic cue (the player's own shadow, a lantern's reflection) is worth more than a state word. Lanterns should be extinguishable. |
| Metal Gear Solid | Visible cones on a radar, Alert → Evasion → Caution phases with timers, reinforcements, hiding in a box | Alarm needs an *evasion* phase with a countdown and a *caution* phase where patrols are denser, not a binary. Hiding spots must break line of sight completely. |
| Hitman (2016–) | Disguises with enforcers who see through them, trespass zones, crowd blending, distractions by thrown coins, accidents, body hiding, "instinct" view | The cloak should work by *zone* (a salon guest is fine in the salon, suspicious in the barracks yard) and specific NPCs (the Corporal, the informer) recognise the player. Bodies left in the street should be found. |
| Assassin's Creed | Social stealth: benches, groups of monks/townsfolk, hay carts, notoriety with posters and heralds, rooftops | Kraków has processions, market crowds, church-goers. Sitting on a bench or walking inside a group should lower visibility. Crackdown should have a visible face: wanted bills, more patrols. |
| Dishonored | Lean/peek, ledges and drop-downs, "chaos" changing the world, non-lethal vs lethal consequences | Lean around the arcade pillars. Crackdown already is our chaos; let the map show it (barricades, closed gates, night-time searches). |
| Commandos / Desperados | Vision cones with near (instant) and far (delayed) zones, prone below the cone, distractions (coins, cigarettes), knocking out and tying up | Two-zone cones: near zone detects a crouching player, far zone only a standing one. Prone under windows. Tie up (gag) downed guards so they stay down. |
| Mark of the Ninja | Sound visualised as rings, guards' last-known position as a ghost | Show the noise ring on sprint and on breaking glass; show the ghost the guard is heading for so the player understands the search. |
| Deus Ex / Hitman | Multiple routes: vents, ledges, bribed door, disguise | Already the mission's three approaches. Add the physical routes: cellar door, courtyard passage (Kraków's *sień*), roof of the Cloth Hall arcade. |

## 3. Design for Kraków 1795

### 3.1 Visibility model (replace the 0.5/1.0 constant)
`visibility = posture × light × cover × crowd`
- **Posture**: standing 1.0, crouch 0.6, prone 0.3 (prone also drops below the far cone entirely).
- **Light**: sample the lights at the player's position each frame (sum of lantern/candle/brazier
  contributions from the district's light list with the same attenuation, plus moon 0.25 if not in
  shadow by a downward ray). Clamp 0.15..1.0. Lanterns can be *doused* (interact: turn the wick down,
  30 s before the lamplighter or a guard relights it; a guard who finds a doused lamp goes Curious).
- **Cover**: 0.5 if a corner/pillar/cart is between the guard's eye and the player's chest but not the
  head (a second ray); allows peeking.
- **Crowd**: 0.35 while inside a group (≥3 NPCs within 2.5 m, walking the same way or standing) and not
  crouching, sprinting or armed. 0.25 while sitting on a bench or kneeling at a shrine.

### 3.2 Sound model
- Footstep noise per surface: cobbles 1.0, packed snow 0.6, gravel 1.2, planks 1.3, straw 0.4, water/mud 1.1.
  Surface comes from the ground material under the player (a `surface` metadata on the ground slabs and
  dressing meshes).
- Walls halve hearing (one ray from guard ear to player). Rain/wind weather multiplies all noise ×0.6.
- Sound events with rings the player can see: sprint step, dropped crate, broken bottle, thrown coin
  (deliberate lure), whistle, church bell (masks everything for 4 s: a moment to move).

### 3.3 Cones and awareness
- Two-zone cone: near (0–5 m, 90°) sees crouching and prone in light; far (5–14 m, 60°) sees standing only,
  or crouching in full light. Peripheral (110°) catches sprinting.
- Head look: guards turn their head to scan at waypoints (the animation agent's `guard_alert_look`), so the
  cone sweeps; the player learns to move behind the head turn.
- State barks (Label3D + a line in the log): "Wer da?", "Halt!", "Show yourself.", "Must have been a cat."
- Alert phases (MGS): Alarm (chase, other guards converge) → Evasion (60 s countdown from last sighting,
  guards search cover points near the ghost) → Caution (3 game-minutes of doubled patrols and closed side
  streets) → Calm. Crackdown rises only if the Alarm reaches the Corporal (a runner has to reach the
  guard post: intercept the runner to keep the night quiet).

### 3.4 Hiding
Hiding spots are interactables (`E Hide`) that drop visibility to 0 and lock movement until `E` again:
- Hay cart and straw pile (breaks sight completely; a guard who *saw* you enter searches it and finds you).
- Wine barrels, empty stalls with dropped canvas, a doorway niche (*sień*), the confessional in St Mary's,
  under a carriage, a coal cellar hatch, a snow-covered lean-to.
- Corners and pillars: hold `Ctrl` against a wall to lean; the camera peeks; only the head counts for
  detection, at cover 0.5.
- Crowds: walking inside the procession or a group of church-goers; sitting on a bench with an NPC.
- Bodies: downed guards can be dragged (0.5× speed) into a hiding spot; a guard finding a body goes to
  Searching immediately and the Corporal sends a runner (Caution phase).

### 3.5 Distractions
- Thrown coin or stone (aim with the camera; lands with a sound ring; a guard walks to it, 8 s).
- Knock on a door (an NPC opens and talks to the guard for 10 s).
- Release a tethered horse; set a stall's dog barking; drop a wine barrel (rolls, a guard chases it).
- Doused lamp: guard relights it (20 s, back turned).
- Church bell (mission or bribe of the sacristan): masks sound, draws the watch's eyes to the tower.
- The false pamphlet (existing) becomes one instance of a general "plant a document on an NPC" verb.

### 3.6 Intel
- Overheard conversations: NPC pairs with speech bubbles carry hints ("the Corporal drinks at the Winiarnia
  after ten"); standing within 4 m for 5 s writes the hint to the journal (People / Storylines).
- Posted bills on the notice board (patrol times, the curfew hour, wanted descriptions that reveal the
  player's own notoriety), letters in interiors, a tavern rumour bought for a coin.
- A map in the journal that marks known guard posts, lantern positions and hiding spots the player has used.
- Watching: crouching still for 10 s within sight of a patrol records its route in the journal (a dotted
  loop on the map), like the Hitman "opportunity" discovery.

### 3.7 Disguises and enforcers
- Cloaks/uniforms as zone permits: salon guest (Town Hall interior, the square's east side), Austrian
  private (barracks, gates: but not the salon), clergy (churches, processions), servant (courtyards and
  kitchens). Wrong zone = trespass: guards go Curious on sight and Searching if you stay.
- Enforcers: named NPCs who know the player's face (the informer, the Corporal, the hostess's footman).
  Their cone ignores the disguise; they are marked in the journal once discovered. Killing or bribing an
  enforcer removes them (costs: crackdown or coins or faction standing).
- Notoriety: each alarm raised adds a *description* to the wanted bills; posting-tearing (interact) or
  changing clothes lowers it.

### 3.8 Showing it on screen (kept sparse, per the journal decision)
- A small diegetic visibility cue: the player's own lantern-lit rim light brightens in light and goes
  flat in the dark, plus a thin arc under the crosshair whose length is the current visibility and whose
  colour is the noise (white quiet → amber loud). No numbers.
- Guard cones stay on the ground, but only the near zone is drawn when the guard is Calm; the far zone
  appears as the guard grows Curious. Enforcers' cones are red-edged.
- Sound rings appear for two seconds at the source of a loud event.
- The eye icon in the HUD keeps the worst state; a chevron on the screen edge points at the guard who
  is reacting when they are off-screen.
- Last-known ghost (a faint outline where the guard thinks you are) during Searching.

## 4. Phased plan (files)

| Phase | Work | Files |
|---|---|---|
| A. Light + sound | light sampling, surface noise, wall-muffled hearing, two-zone cones, barks | `player.gd`, `guard.gd`, `greybox_district.gd` (light list + surface metadata) |
| B. Hiding | hiding spots as interactables, lean/peek, crowd blend, prone under cones | `scripts/stealth/hiding_spot.gd` (new), `player.gd`, `dressing.gd` (spots), `population.gd` (group detection) |
| C. Alert phases | Evasion/Caution timers, runner to the Corporal, search points, body finding, dragging | `guard.gd`, `scripts/stealth/watch.gd` (new coordinator), `game_state.gd` |
| D. Distractions | thrown coin, door knock, doused lamp, barrel, horse, bell | `scripts/stealth/distraction.gd` (new), `interactable.gd`, `flicker.gd` (dousing) |
| E. Intel + journal | overhearing, bills, patrol recording, map tab | `journal.gd`, `storyline.gd`, `data/*.json` |
| F. Disguise zones + enforcers | zones on the map, permit per outfit, enforcer flag on NPCs, notoriety bills | `guard.gd`, `data/npcs.json`, `mission_runner.gd` |
| G. On-screen cues | visibility arc, sound rings, off-screen chevron, ghost | `hud.gd`, `guard.gd` |

Phase A and B change the feel most and cost least. C makes failure interesting instead of instant.
D and E are what make the city a puzzle rather than a corridor. F is the Hitman layer and needs the
district zones. G should ship with A so the player can read the new rules.
