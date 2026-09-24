# Audio

Every sound in the game is synthesised by `tools/gen_sfx.py` (Python + numpy, ffmpeg/libvorbis for Ogg). There are no
recordings and no third-party samples. Generated audio: CC BY 4.0. Code: MIT.

```
python3 tools/gen_sfx.py            # writes assets/audio/*.wav|*.ogg + assets/audio/manifest.json (~13 s)
python3 tools/gen_sfx.py --list     # the sound list with descriptions
python3 tools/gen_sfx.py --only step_,hoof_   # regenerate some sets (manifest merged)
python3 tools/gen_sfx.py --demo     # also render assets/audio/demo_mix.ogg (20 s walk through the square) and
                                    # print its RMS/peak per 2 s and the timeline
godot --headless --import --path .  # import the new files (tools/build_all.sh's import stage does this too)
```

The generator is deterministic: each file is seeded from its name. It is not a stage of `tools/build_all.sh`; run it
by hand after changing it. Output is 22.05 kHz mono, 16-bit WAV for short point sounds and Ogg Vorbis (q3) for beds,
bells, the hejnał and long tails: 386 files, about 8.7 MB. `--stats` prints the footstep analysis (below).

## Sound list

| Group | Sets (variants) |
|---|---|
| Footsteps | `step_<surface>_<shoe>` for cobbles, flags, snow, mud, gravel, planks, straw x shoe, boot, bare (10 variants each, 210 files); `scuff` (6), `scuff_snow` (4), `drag` (4, prone), `cloth_rustle` (6), `coat_swish` (4) |
| Horses, vehicles | `hoof_walk`, `hoof_trot` (8), `hoof_soft` (3), `horse_stamp` (2), `horse_whinny` (2), `horse_snort` (3), `coachman_hoo` (2), `harness_jingle` (4), `wheel_loop`, `wheel_mud_loop` (4 s loops), `wheel_clack` (4), `cart_creak` (2) |
| Animals | `dog_bark` (4), `dog_bark_far` (2), `dog_growl` (2), `dog_pant`, `cat_meow` (3), `cat_purr` (loop), `pigeon_coo` (3), `pigeon_flap` (2), `crow_caw` (3), `hawk_cry` (2), `owl_hoot` (2) |
| People | `laugh` (2), `cough` (3), `baby_cry` (2), `hiccup` (3), `snore` (2), `grunt` (4), `punch` (4), `body_fall` (2), `lash` (3), `drum_roll`, `drum_beat` (2), `drunk_song` (2), `crowd_jeer` (2) |
| Beds (loops) | `city_murmur_loop` (16 s), `crowd_talk_loop` (10 s), `tavern_loop` (12 s), `prayer_murmur_loop` (12 s), `wind_calm_loop`, `wind_strong_loop` (16 s), `wind_gust` (2), `brazier_loop` (8 s), `grinder_loop` (4 s) |
| Props, stealth | `stone_land` (3), `bottle_smash` (2), `coin_chink` (2), `cabbage_thud` (2), `barrel_roll_loop`, `barrel_clonk`, `door_knock` (2), `door_open`, `door_close`, `shutter_open` (2), `lamp_douse`, `lamp_relight`, `musket_shot`, `pistol_shot`, `smoke_charge`, `flash_crack`, `knife_slash` (2), `splash_slops` (2), `glass_clink` (2) |
| Bells, calls | `bell_great` (St Mary's), `bell_small` (3 pitches), `bell_peal`, `bell_townhall`, `bell_uniate`, `bell_sigismund`, `hejnal`, `schulklopfer_knock` (3) |
| UI | `ui_click`, `ui_hover`, `ui_page` (2) |

## Synthesis

Building blocks: coloured noise (spectral slope), exponentially damped sinusoid modes (resonant bodies), micro-grain
clicks (crunch, grit, crackle), zero-phase FFT filters, a Hann-windowed STFT for time-varying filters, a formant model
(additive harmonic voice or noise through vowel formants), a convolution reverb from decaying noise with early
echoes, soft limiting, equal-power loop crossfades.

- Footsteps: two layers. Heel strike = a short low thud (60-120 Hz sine drop, 14-24 ms decay; boots lowest and
  heaviest, bare feet highest and lightest) plus the surface's contact sound; toe/roll 45-90 ms later = a band-passed
  scuff (1-4 kHz) shaped by the surface. Cobbles: hard click, stony ring, grit tail; flags: a cleaner slap; snow: soft
  crunch (the heel swallowed) with a dry-cold squeak on half the variants; mud: swept wet squelch and a suction pop;
  gravel: many micro-clicks; planks: hollow knock with a 150-250 Hz board resonance (the odd creak); straw: dry
  rustle. Boots add hobnail clicks, bare feet a skin slap.
- Footstep targets (`--stats`, power-weighted centroid / onset-to-peak): cobbles 0.9-2.6 kHz / <=6 ms, flags
  0.5-1.8 kHz / <=6 ms, snow 1.5-4.2 kHz / <=40 ms, mud 0.2-1.0 kHz / <=40 ms, gravel 1.5-4.5 kHz / <=25 ms, planks
  0.2-0.9 kHz / <=8 ms, straw 1.2-4.2 kHz / <=40 ms; every set crest 10-24 dB and RMS -30..-12 dBFS. All 21 sets pass.
- Hooves: impact click + hollow horn resonance (600-1400 Hz modes) + weight thump + faint iron-shoe ring; the walk is
  a two-part clop, the trot a single sharp clop with a flam.
- Wheels: brown-noise rumble, iron-tyre clacks at spoke rate with jitter, random sett bumps, a rattle band driven by
  the bumps, axle creaks (stick-slip saw through resonances).
- Harness: small inharmonic bells (1 : 2.76 : 5.40 : 8.93).
- Voices and animals: additive harmonics under formant tracks (dog barks, the whinny, meows, coos, caws, the hawk, the
  owl, the coachman's "Hooo!", laughs, the baby, grunts, song); murmur and crowd beds are granular babble: many
  voices speaking phrases of vowel syllables (formant-filtered glottal sawtooth, consonant dips, fricatives).
- Bells: hum, prime, tierce, quint, nominal and upper partials, each a slowly beating pair, long per-partial decays,
  a clapper transient, baked reverb. St Mary's great bell has a 98 Hz prime; the Sigismund bell a deep 46 Hz prime,
  lowpassed as heard from far off; the Town Hall clock bell is small and hammer-struck.
- Hejnał: bandlimited brass (harmonics brighten with loudness, a formant bump near 1.3 kHz), attack scoop, delayed
  vibrato, playing an approximation of the Hejnał mariacki in F (rising triad, held C, the turn and fall, the call
  again) that breaks off mid-note with no release, after the legend of the watchman shot as he sounded the alarm
  (a legend popularised much later; the hourly call itself is documented for centuries before 1795). Facade echoes
  and reverb are baked in.
- Weapons: flint snap and pan fizz before the charge; musket = crack + low boom + long echoing tail; pistol sharper.

## Runtime

`scripts/audio/sfx.gd` (class `Sfx`, a node added by `main.gd`):

- `Sfx.play(name, pos, volume_db, pitch_var, pitch)`: `name` is an event of `data/audio.json` `events` (set, volume,
  radius, unit, pitch variance, priority, `also` layers, `secs` limit, bus), else a manifest set (random variant, no
  immediate repeat), else a file. Pooled `AudioStreamPlayer3D`s (`voices.max`, 32); when all are busy the oldest voice
  of lower or equal priority is stolen. A sound beyond its radius from the listener is never started. Inverse-distance
  falloff from `radius * unit`; distance air absorption.
- Occlusion: a ray from the listener to the source at start and every 0.25 s for long voices and loops; blocked =
  900 Hz lowpass and -8 dB.
- `Sfx.play2d`, `Sfx.ui` (UI bus, runs while paused), `Sfx.attach_loop(node, name, db, radius)`, `Sfx.set_loop_db`.
- Buses (created at start): SFX, Ambience, UI, and reverb buses Reverb_Arcade / Reverb_Passage / Reverb_Interior /
  Reverb_Church; a hard limiter on Master. The Master volume setting (GameState) still controls everything.
- Glue: `Sfx.watch_hooks(watch)` voices `sound_event` kinds (`watch_kinds` table: stone, bottle, coin, food, smoke,
  flash, barrel roll / clonk, knock, horse, bell, fight, splash; the player's `step` is left to footsteps) and
  `lamp_changed`; `Sfx.say_hook` and `Sfx.act_hook` map street-life bubbles and clips to sounds.
- Every second it attaches footsteps to guards and the player that lack them.

`scripts/audio/footsteps.gd` (class `Footsteps`): `Footsteps.attach(body, kind)`. People step on each heel strike of
their locomotion clip (the gait in build_animations.py puts the left heel at phase 0 and the right at 0.5), falling
back to one step per stride of distance; the set is `step_<surface>_<shoe>` from `Perception.surface_at()`, each step
+-3 dB and +-6 % pitch. Kinds: shoe, boot (guards), heel (women: the shoe set pitched up), bare (beggars, urchins),
player (sneaking -9 dB with sole scuffs, sprinting +3 dB with a coat swish, cloth rustles, prone = a drag once a crawl
cycle). Scuffs on sharp turns. Steps sit 6-10 dB under the murmur, and a distance low-pass (clear to 3 m, 1.8 kHz at
28 m) makes other people's steps read as distant. Horses beat
at fixed phases of each horse's walk (4) / trot (2) clip, so hooves follow the gait and speed. Vehicles add the wheel
loop pitched and levelled by speed (mud loop on soft ground), sett clacks, jingle, creaks and the coachman's call when
blocked. Dogs, cats, pigeons, crows and the hawk call on timers (growl, purr, wing claps by the player).

`scripts/audio/ambience.gd` (class `Ambience`): wind beds by strength (GameState `weather` if present), the city murmur
by walkers within 40 m, crowd murmur loops parked on groups (group `crowd`, idle clusters), tavern noise at the tavern
doors and the brothel door, the full tavern bed inside, random distant life (dogs, owl, baby, cough, crows, gusts),
reverb zones (Area3D on physics layer 20 with reverb buses: Cloth Hall arcade and passage, alleys, interiors, the
church). The game-clock schedule (`data/audio.json` `schedule`, positions in `places`):

| When | What | Where |
|---|---|---|
| every hour | St Mary's great bell strikes the hour, then the hejnał to one quarter, turning S, W, E, N hour by hour (`all_directions` plays all four every hour, the real ceremony, ~80 s; the call facing the listener is louder) | St Mary's belfry / trumpet window (NE of the square) |
| every hour + 14 s, half hours | Town Hall clock: the hour count; one stroke on the half hour | Town Hall tower (SW) |
| 21:00, 00:00, 03:00 | compline, matins, lauds on the small bells | St Mary's |
| 22:00 | curfew: 12 strokes, the first through `watch.ring_bell()` (the watch turns to the tower) | St Mary's |
| 06:00 (12:00, 18:00) | the Angelus: 3 x 3 strokes, then a peal | St Mary's |
| 21:30, 05:30 | the Uniate chapel's small bell | west, proxy position |
| 00:00, 06:00 with flag `feast_day` | the Wawel Sigismund bell, far off | south, proxy position |
| 05:05-05:45, not day % 7 == 6 | the schulklopfer's knock-knock ... knock on shutters | Kazimierz, proxy position |
| Sabbath eve (day % 7 == 5 or flag `sabbath_eve`) until 22:00 | a low murmur of prayer from the synagogue door | Kazimierz |

While bells and the hejnał ring, `watch.mask_sound(secs)` masks the watch's hearing: `mask_secs` per stroke or call
(hour strokes 1.2 s, the hejnał's first 6 s, curfew strokes 2.5 s, Angelus 2 s, the peal 8 s; the Town Hall clock
does not mask). A game hour is one real minute at clock_scale 1, so these are kept short; tune them in the table. There is no Muslim call to
prayer: Kraków had no mosque in 1795.

## Hooks in other scripts

| File | Hook |
|---|---|
| `scripts/core/main.gd` | adds `Sfx` and `Ambience`; `[smoke] audio ...` lines |
| `scripts/npc/walker.gd` | `Footsteps.attach(self, "auto")` in `setup_navigation` (every townsperson, animal and vendor calls it from `_ready`) |
| `scripts/npc/animal.gd` | `Footsteps.attach(self, "auto")` in `_ready` (vehicles and the hawk skip navigation) |
| `scripts/stealth/watch.gd` | `Sfx.watch_hooks(self)` in `_ready` |
| `scripts/stealth/distraction.gd` | door creak / shut on the knock door |
| `scripts/city/vendors.gd` | brazier crackle loops; the grinder's stone while his sparks fly |
| `scripts/city/street_life.gd` | `say()` and `_act()` hooks; the lash in the flogging; drunks' hiccups |
| `scripts/city/window_life.gd` | shutters, the cat's meow, thrown things landing (slops splash through the watch) |
| `scripts/ui/ui_theme.gd` | `UiTheme.wire_sound()`: clicks, hovers, page turns |
| `scripts/stealth/player.gd` (not edited) | optional: `Footsteps.attach(self, "player")` in `_ready`; Sfx attaches it anyway within a second |

Other systems can call `Sfx.play("musket" | "pistol" | "knife" | "bottle" | ..., pos)` directly.

## Smoke

`godot --headless --path . -- --smoke` prints
`[smoke] audio files=<loaded>/<total> voices_peak=<n> events=<every event forced once>` and
`[smoke] audio ambience wind=... walkers_near=... crowd_groups=... tavern_doors=... reverb_zones=... sequences=...`.
