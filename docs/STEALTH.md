# Stealth review and design

Audit of the stealth systems in the playable slice, what the classics of the genre do that we do not,
and a phased plan to apply it to Kraków, 1795. Written against the code in `scripts/stealth/`,
`scripts/npc/`, `scripts/mission/` and `data/missions.json`.

## 1. What exists today

### Detection (`guard.gd`)
- **Sight**: a 70° cone, 14 m, one ray from the guard's eye to the player's head. Score falls off with
  distance (0.3 at the edge, 1.0 point blank) and is multiplied by `player.visibility`, which is 1.0
  standing and 0.5 crouching. **Light is not part of it**: the player comment mentions a light probe but
  nothing reads one, so a lantern pool and a black alley are identical to a guard.
- **Hearing**: a radius of 8 m scaled by `player.noise` (0 still, 0.15 crouch-walk, 0.45 walk, 1.0 sprint).
  Walls are ignored.
- **Suspicion**: 0..100, +45/s at full visibility, −12/s when unseen. Thresholds: 20 Curious, 60 Searching
  (6 s search of `last_known`), 100 Alarm (sticks until suspicion decays to 0, and each alarm adds crackdown).
- **Disguise** (salon cloak): sight and hearing ×0.25 unless sprinting, crouching or lingering within 3 m for
  more than 4 s. Guards seize the player after 2 s within 1.3 m while alarmed and the player is not fighting.
- **Witnessing**: a guard downed in a fight is seen by any guard with line of sight; a quiet rear takedown is not.
- **Curfew**: at 22:00 the view distance doubles for 3 game minutes.

### Player (`player.gd`)
- Walk, sprint, crouch, rear takedown within 1.5 m, cudgel swing, carrying (0.7× speed, no sprint).
- No lean, no peek, no cover, no hiding places, no body dragging, no throwables, no lockpicking.

### Feedback (`hud.gd`, guard cone)
- Each guard draws a flat wedge on the cobbles tinted by its state (dim green, amber, orange, red) and a
  `?` / `!?` / `!!` label above its head. The HUD shows one word for the worst guard's state and an eye icon.
- Nothing tells the player how visible or how loud they are, or which guard is the one reacting.

### Distractions and intel
- One scripted distraction: the false pamphlet planted on the informer from behind, which sends the watch to
  the Florian Gate (a mission flag, not a general system).
- Intel is delivered by dialogue (the printer, the smuggler, the hostess) and the day briefing. No
  overheard conversations, no posters, no documents to read, no maps.
- Storylines (`data/storylines.json`) are timed NPC loops (delivery, procession, informer) that can be
  watched, but nothing in them is stealth-relevant yet apart from the informer's route.

### Crowds and enforcers
- ~19 NPC walkers and 4 animals exist, but crowds do nothing for detection: a guard's ray ignores NPCs
  (only physics bodies block it, and NPC bodies do not) and there is no "blend" state.
- Enforcers do not exist: any guard is fooled equally by the cloak.

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
