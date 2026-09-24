---
name: ue-shot
description: Take offscreen screenshots of a Kraków 1795 Unreal level from a JSON list of cameras (position, rotation, FOV, time of day) with no visible window, under the GPU lock, writing PNGs to a folder. Use to refresh docs/screenshots/ue or to verify a visual change without opening the editor.
---

# ue-shot: offscreen screenshots from a camera list

Status: DRAFT. Confirm `TODO` items after install. Counterpart of `tools/refresh_screenshots.sh`.

## When to use
- After a lighting, material, import or city-layout change, to see it.
- To produce the side-by-side comparison set against Godot (same cameras as `docs/screenshots/`).
Requires the game target built (`ue-build`) and a GPU: always through `tools/with_gpu.sh`.

## Inputs
`tools/ue/cameras/<set>.json` (TODO create), matching the Godot shot list:
```json
{"map": "/Game/Maps/City", "res": [1920, 1080],
 "shots": [{"name": "rynek_dusk", "pos": [1200, -340, 180], "rot": [-8, 35, 0], "fov": 70, "hour": 17.5},
           {"name": "florian_night", "pos": [4100, 2200, 210], "rot": [-4, -120, 0], "fov": 60, "hour": 23.0}]}
```

## Command
```bash
ROOT=/home/richard/Projects/games/prototypes/krakow-1795
UE=/opt/UE_5.8; P=$ROOT/unreal/Krakow.uproject; ED=$UE/Engine/Binaries/Linux/UnrealEditor-Cmd   # TODO
OUT=/tmp/ue-shots/$(date +%s); mkdir -p $OUT
$ROOT/tools/with_gpu.sh timeout 900 $ED $P /Game/Maps/City -game -RenderOffscreen -resx=1920 -resy=1080 \
  -unattended -nosplash -nosound -nop4 -stdout -FullStdOutLogOutput -NoLiveCoding \
  -ExecCmds="Krakow.Shots $ROOT/tools/ue/cameras/game.json $OUT" 2>&1 | tee $OUT/run.log | grep -E "\[shot\]|Error:|Fatal"
ls $OUT
```
`Krakow.Shots` is a small C++ console command (TODO: implement in the game module) that loads the JSON, and per shot:
sets the time of day on our sky subsystem, teleports a `ACameraActor`, waits N frames for Lumen/VSM/PSO warm-up,
calls `FScreenshotRequest::RequestScreenshot(path, false, false)` (or the `HighResShot 1920x1080 filename=` console
command), waits for the write, then prints `[shot] name path`; after the last shot it runs `Quit`.
Interim option before that exists, one process per shot:
```bash
-ExecCmds="Krakow.TimeOfDay 17.5; Camera.Teleport 1200 -340 180 -8 35 0; HighResShot 1920x1080 filename=$OUT/rynek.png; Quit"
```
(TODO: confirm a stock `Camera`/`teleport`-style command; the first-person default is `BugItGo X Y Z P Y R`.)

## Cinematic/batch alternative: Movie Render Queue
```bash
$ROOT/tools/with_gpu.sh $ED $P /Game/Maps/City -game -RenderOffscreen -MoviePipelineConfig=/Game/Cine/Q_Shots \
  -windowed -resx=1920 -resy=1080 -log -unattended
```
Writes PNG/EXR sequences per shot with proper temporal accumulation; better for hero images, slower.

## Pitfalls
- `-nullrhi` produces black frames; screenshots need a real Vulkan device, hence the GPU lock.
- `HighResShot` is unavailable in Shipping builds; use Development.
- First run after import/lighting change compiles shaders and PSOs for minutes and the first frames are blurry
  (Lumen/TSR accumulation). Warm up 30-60 frames before each shot; keep all shots in one process.
- Wayland: `-RenderOffscreen` makes no window, so no SDL display issues; if Vulkan fails to init without a display,
  set `DISPLAY=:0` (TODO check) or run under the existing X session.
- Lock discipline: one GPU job machine-wide; Godot and Blender GPU renders share `/tmp/krakow-1795-gpu.lock`.
- Resolution/AA: `r.ScreenPercentage 100`, `r.TemporalAA.Upsampling 0` for like-for-like comparisons with Godot's MSAA.
- Time budget: expect 40-90 s per process even when warm; budget accordingly in agent loops.
