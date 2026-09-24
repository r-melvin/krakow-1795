# Sky

The sky over the Rynek: atmosphere, a low winter sun, the moon with its phase, stars that turn about the pole,
planets, a faint comet, meteors, two decks of cloud that drift with the wind, and storms with lightning and
thunder. One sky shader, one node, one data file.

| Piece | Where |
|---|---|
| Sky shader (`shader_type sky`) | `assets/shaders/sky.gdshader` |
| Node that drives it (`class_name CitySky`, node name `Sky`) | `scripts/city/sky.gd`, added by `greybox_district.gd` right after `Weather` |
| Cloud looks per weather preset, moon, stars, comet, meteors, lightning | `data/sky.json` |
| Captures | `docs/screenshots/sky/` (`sky_sheet.jpg` is the contact sheet) |

The old `ProceduralSkyMaterial` in `greybox_district._environment()` is gone; `sky.gd` puts a `ShaderMaterial`
`Sky` on the district's `WorldEnvironment` (group `world_env`).

## What it reads (and does not duplicate)

`weather.gd` stays the owner of time, light, fog and exposure. The sky reads:

- `Weather.current()` at 2 Hz and the `changed` signal: `preset`, `kind`, `time_of_day`, `daylight`, `wind`,
  `snow_cover`.
- The weather preset's `sky_top`, `sky_horizon`, `day_top`, `day_horizon`, `fog_color` from `data/weather.json`:
  the night gradient is exactly what the ProceduralSky got, so the SDFGI sky light and the lantern-lit ambient
  do not move. The day gradient is blended with the physical scattering term (`art_mix`).
- The `moon_light` `DirectionalLight3D` that `weather.gd` rotates: while the sun is above -3 degrees the light is
  the sun (its direction, colour and energy drive the disc, the aureole and the cloud lighting); at night it is
  the moon (`Weather.MOON_ROT`) and its energy lights the clouds and scales the moon's glow. The sun's elevation
  below the horizon (twilight) is recomputed from `time_of_day` with the same formula as `weather.gd`
  (`20 * sin(PI * (tod - 6) / 12)`), unless the weather state carries `sun_elevation` / `sun_azimuth` (degrees),
  which win: the day `weather.gd` publishes them, the mirrored formula is dead code.
- The global shader parameter `wind` is not used directly; the accumulated drift comes from the script so a
  change of wind never jumps the clouds.

One environment setting is written by the sky: `fog_aerial_perspective = 0.9`. The engine mixes the on-screen
sky toward `fog_light_color` by `fog_sky_affect` with the fog amount fixed at 1.0 for the sky, and `weather.gd`
sets `fog_sky_affect = 1.0` at night, which made the old sky a flat fog colour. Aerial perspective feeds the
sky's own colour back into that mix (and lets the distance fog take the sky's tint, which is what haze does).
The whiteouts of the fog and blizzard presets come from the shader's own haze term instead.

## The shader

Passes (`render_mode use_half_res_pass`):

- **Half-res pass**: the two cloud decks only, premultiplied colour + alpha.
- **Full-res pass**: atmosphere, twilight, haze, the sun, the moon, stars, planets, the Milky Way, the comet, a
  meteor, then the half-res clouds composited over, then the lightning bolt (below the cloud base) and the
  ground below the horizon.
- **Cubemap pass** (what SDFGI, reflections and the volumetric fog read): the same without the point features
  (stars, meteor, bolt); the clouds are recomputed directly there. `Sky.PROCESS_MODE_INCREMENTAL`,
  `RADIANCE_SIZE_128`: a 128 px face is re-rendered over a few frames when a uniform changes, never a full sky
  per frame.

**Atmosphere.** Five samples along the view ray through an exponential atmosphere on a spherical earth
(Rayleigh scale height 8 km, Mie 1.2 km), with the sun's optical depth per sample from an analytic Chapman
function that also works below the horizon; Rayleigh and Henyey-Greenstein (g 0.7) phase functions. Its scale
is `sun_intensity` (16). On top of it the preset's day gradient times `art_mix` (0.6) and an explicit twilight
band (warm toward the sun's azimuth, violet higher, from -11 to +8 degrees). The night is the preset's gradient
with a very faint warm town glow on the low sky (`town_glow`). Winter haze: `haze` x `exp(-elevation /
haze_height)` toward `haze_color` (the preset's fog colour, day-tinted); `haze = 1, haze_height = 0.9` is the fog
whiteout.

**Sun.** A 0.3 degree disc with limb darkening at 18x the transmitted sunlight (so it blooms), a `1/angle^2`
glare and a soft aureole; the Mie term of the atmosphere gives the wider forward-scatter glow. The disc colour
is the sun's transmittance for its elevation (white at 17 degrees, orange at 3, red at the horizon).

**Moon.** A disc of `moon_size` degrees (1.1: about four times the real 0.26; anything smaller is a dot at a
62 degree field of view) with a Lambert terminator from `moon_phase` (0 new, 0.25 first quarter, 0.5 full,
0.75 last quarter; the lit side faces the sun's side, tilted 22 degrees), maria and crater specks from the cloud
noise, limb darkening, earthshine on the dark side (stronger near new moon). A tight glow, a corona that only
appears where thin cloud covers the moon (`moon_halo` x cloud alpha) and a 22 degree ice halo (`halo22`,
red inner edge, blue-white outer) for the frost and fog presets. The phase advances `phase_per_night` per
campaign night from `phase_night1` (`data/sky.json` "moon").

**Stars.** Three procedural layers on a cube grid in the equatorial frame (one star per cell, magnitude count
law `N(>B) ~ B^-1.25`, so most are faint): 46, 110 and 210 cells per face; the last two are denser inside the
Milky Way band (galactic pole RA 192.85 h, Dec 27.13; the winter Milky Way is faint, `milky_way` 0.6). Colours run
blue-white to orange. Twinkle is a slow sine per star, stronger near the horizon (`twinkle`). Stars fade with
daylight, moonlight (45 % at full moon energy), cloud alpha, haze and horizon extinction. The frame turns with
the local sidereal time: `lst_hours_at_21` (5.0 h for mid-January at 19.9 E) advancing 1.0027 h per game hour,
latitude 50.06 N, so the pole sits due north at 50 degrees. Planets: Jupiter in Gemini, Saturn in Taurus, Venus
low in the west, as three non-twinkling points (`planets`).

**Comet.** A fuzzy coma with a dust tail pointing away from the sun's equatorial position, fixed in the star
frame (RA 1.5 h, Dec +42: high in the west-north-west in the evening). Off until campaign night `from_night`
(3) and only for looks that carry `"comet": true` (clear_frost). `strength` 0.5 reads as a faint smudge with a
tail: an omen for the superstition storyline, not a set piece.

**Meteors.** `sky.gd` schedules one every `mean_interval_s` (40 s) x a random 0.35-1.8 on a clear night; the rate
scales with `(1 - coverage)^2`, `(1 - 0.8 haze)`, the night factor and the look's `meteors` multiplier, so an
overcast sky has none. Half of them radiate from the Quadrantid radiant (RA 15.3 h, Dec +49.5, early January)
when it is up. A meteor is a 6-20 degree streak over 0.35-0.9 s with a head glow and a power-law brightness
(most are faint); `fireball_chance` (4 %) gives a 2x longer, slower, green-white fireball with a lingering
train.

**Clouds.** Two seamless `NoiseTexture2D`s made at start (FastNoiseLite simplex fBm, 512 px 5 octaves and 256 px
4 octaves). The low deck is a plane at `altitude` (relative; lower = more perspective) sampled with a curved
horizon, thresholded by `coverage` with `softness`, eroded by the detail noise (`detail`). Lighting is a second
sample of the noise toward the light: rims facing the sun or moon are bright (`exp(-thickness)`), the interior
darkens with `base_dark`, and thin parts glow when the light is behind them (forward scatter), so the deck goes
silver at the edges, dark underneath, and orange at dusk because the light colour is the transmitted sun. `sheet`
flattens the lighting into a stratus layer, `ragged` adds low torn scud under the deck (nimbostratus), `tower`
raises the contrast and darkens the bases (storm). The high deck is `cirrus`: a sheet stretched along the wind
by `cirrus_streak`, mostly forward-lit, thin. Both drift with the wind (`wind + a little` so calm air still
moves; the cirrus at half speed). A distance fade pulls far cloud into the haze.

**Lightning.** `flash` lights the cloud deck from inside (brightest toward `flash_dir`) and the whole sky a
little; `flash_bolt` draws a seven-segment bolt with two branches (seeded by `flash_seed`) below the cloud
base.

## The node (`scripts/city/sky.gd`)

Every frame: cross-fades the look toward its target (`transition_s`, 18 s), accumulates the cloud drift, steps
the lightning flicker and the meteor. Every 0.5 s: reads the weather and the light, pushes the sun and moon
directions, colours, `daylight`, the star basis, the gradient colours, the moon phase and the comet switch.

Static API:

```
CitySky.instance() -> CitySky
CitySky.set_look("storm")                 a cloud type from data/sky.json, on top of the weather preset
CitySky.set_look({"coverage": 0.6, ...})  parameter overrides; null clears; cleared by the next weather change
CitySky.instance().snap()                 skip the cross-fade
signal lightning(strength: float, delay_s: float)
```

**Storms.** A look with `storm > 0` strikes every `min_gap_s`-`max_gap_s` seconds (scaled by `storm`), at
`min_km`-`max_km` (a third of them pulled close). `strike(km, bolt)`: strength `1.8 / km` clamped to 0.12-1; 2-4
flicker pulses decaying over 55 ms each; a `DirectionalLight3D` (`LightningLight`, `light_energy` x strength,
cold blue-white, shadows only under 3 km) from the flash's direction; a visible bolt for strikes under
`bolt_max_km` (60 %). It emits `lightning(strength, delay_s)` with `delay_s = km / 0.343` and, after that delay,
plays thunder itself: there is no thunder in `assets/audio` yet, so three variants are synthesised on first use
in a `WorkerThreadPool` task (a crack for the near ones, then rumble: noise through wandering low-pass filters
under overlapping bumps, a sub boom, soft clip, normalised near -18 dBFS like the library) and played on the
`SFX` bus at `thunder_db` (-8) plus a strength term, the far variant lower and slower. When `tools/gen_sfx.py`
grows a real `thunder_near` / `thunder_far` set, connect `lightning` in the audio system and set `"thunder":
false` in `data/sky.json`.

## Presets (`data/sky.json`)

`types` are cloud looks; `presets` map a weather preset name to a type plus overrides; `kinds` is the fallback
by weather kind for presets the file does not know.

| Weather preset | Type | Notes |
|---|---|---|
| clear_frost | clear | a few wisps, cirrus 0.06, faint 22 degree halo (0.12), comet on from night 3 |
| light_snow | snow | closed stratus sheet, pale bases, haze 0.6 |
| blizzard | blizzard | sheet + haze whiteout (haze 1, height 0.6), no moon glow |
| sleet | rain (base_dark 0.55, ragged 0.5) | |
| rain_thaw | rain | nimbostratus: closed deck, dark bases, scud, haze 0.55 |
| fog | fog | haze whiteout (1.0 / 0.9), sheet, 22 degree halo 0.5 where the moon shows |
| overcast | overcast | 97 % stratus sheet, no stars |
| clear_day | clear (haze 0.22, cirrus 0.12) | |
| snow_day | cirrus (coverage 0.22, cirrus 0.5, haze 0.4) | a bright hazy winter day |
| storm | storm | towers, base_dark 0.9, scud, lightning; **needs a matching weather.json preset** (see the `_note`) |

Type parameters: `coverage`, `softness`, `scale`, `altitude`, `density`, `base_dark`, `detail`, `sheet`,
`ragged`, `tower`, `cirrus`, `cirrus_streak`, `haze`, `haze_height`, `halo22`, `moon_halo`, `star_strength`,
`meteors` (rate multiplier), `storm` (lightning rate 0..1), and `comet` (bool) on a preset entry.

### Adding a cloud type

1. Add an entry under `types` with all the parameters above (copy the nearest one).
2. Point a preset at it (`"presets": {"<weather preset>": {"type": "<name>", ...overrides}}`) or set it at run
   time with `CitySky.set_look("<name>")`.
3. Capture it: `tools/with_gpu.sh godot --path . -- --perf --sky-shot=/dir --sky-shot-only=<shot>` after adding a
   line to the `shots` table in `sky.gd` (`_Shots._run`): name, weather conditions, look, aim (`"moon"`,
   `"sun"`, `"moon_side"`, `"sun_side"`, `"comet"` or `[azimuth, elevation]`; azimuth 0 = south, 90 = east),
   extra (`"meteor"`, `"flash"`, `"comet"`) and the eye (`""` north-west corner, `"e"` along the north row,
   `"c"` south-east).

## Captures

`docs/screenshots/sky/`: clear_night (moon, stars, a meteor), clear_night_comet, moon_thin_cloud (cirrus veil,
corona, 22 degree halo), fair_night (moonlit cumulus), overcast_night, rain_night, storm_night (a held lightning
frame with the bolt), fog_night, dawn, dawn_cirrus, clear_day, cumulus_day, snow_day, overcast_day, dusk;
`sky_sheet.jpg` is the contact sheet. All from `--sky-shot`, which freezes the scheduled meteors and strikes,
holds a meteor or a flash where the shot asks for one, and quits.

## Performance

`tools/with_gpu.sh godot --path . -- --perf` (a plain night, 40 s settle, 1600x900, MSAA + TAA, SDFGI, SSR,
volumetric mist): see the numbers in the hand-back report and README. The shader has no ray march beyond the
five atmosphere samples; clouds are two textures sampled 4-6 times at half resolution; the star layers are one
hash per pixel each and only run at night; the bolt and meteor branches only run while one is active. The
radiance cubemap is 128 px, incremental.

## Known limits

- The sun follows `weather.gd`'s arc (20 degrees at noon, rising at 06:00); Kraków in January peaks near 17
  degrees and rises about 07:35. That is a two-number change in `weather.gd` (`_apply_sky`), not here.
- The sky is not visible through the fog presets by design; the moon's halo is the only sky feature that shows.
- Meteors, the comet and the bolt are screen-only (not in the radiance cubemap): reflections and SDFGI do not
  see them, which is correct for how faint they are, and the bolt's light on the town is the flash light.
- Cloud shadows on the ground are not cast (the directional light's energy is the weather's, not modulated by
  cloud density under the sun).

## Sun elevation range
weather.gd publishes `sun_elevation` clamped to -18 degrees (astronomical night). Below about -20 the shader's
below-horizon sun depth term overflows and the radiance cubemap floods the town white through SDFGI sky light;
the January arc reaches -40 in the small hours, so the clamp stays until the depth term is bounded in the shader.
