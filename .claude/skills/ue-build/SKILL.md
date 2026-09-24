---
name: ue-build
description: Build the Kraków 1795 Unreal project on Linux with UnrealBuildTool, or cook/package it with RunUAT BuildCookRun, under the project's CPU/GPU locks. Use after any C++ change, before ue-test/ue-shot, or when asked to package a Linux build.
---

# ue-build: UBT and UAT wrappers (Linux, UE 5.8.x)

Status: DRAFT. Every `TODO` below must be confirmed after the engine is installed (see docs/UNREAL_SPIKE.md).

## When to use
- After editing anything under `unreal/Source/` (C++ modules) or `unreal/Plugins/*/Source/`.
- Before `ue-test`, `ue-shot`, `ue-py` with `-run=` (a stale editor binary silently runs old code).
- To produce a Linux client package in `export/ue/`.
Do not use for Blueprint or Python-only changes; those need no build.

## Variables (confirm once, then keep at the top of every command)
```bash
UE=/opt/UE_5.8                                       # TODO: engine root (prebuilt zip unpacked here)
P=/home/richard/Projects/games/prototypes/krakow-1795/unreal/Krakow.uproject   # TODO: project path
TARGET=KrakowEditor                                  # TODO: <ProjectName>Editor from unreal/Source/*.Target.cs
ROOT=/home/richard/Projects/games/prototypes/krakow-1795
```

## Commands
Editor target, incremental (the everyday one):
```bash
$ROOT/tools/with_cpu.sh -n 24 $UE/Engine/Build/BatchFiles/Linux/Build.sh $TARGET Linux Development \
  -Project=$P -Progress -NoHotReloadFromIDE 2>&1 | tee /tmp/ue-build.log | tail -30
echo "exit=${PIPESTATUS[0]}"
```
Game (non-editor) target for `-game` runs and packaging:
```bash
$ROOT/tools/with_cpu.sh -n 24 $UE/Engine/Build/BatchFiles/Linux/Build.sh Krakow Linux Development -Project=$P -Progress
```
Clean rebuild of the project module only (never clean the engine):
```bash
rm -rf $(dirname $P)/Binaries $(dirname $P)/Intermediate && <incremental command above>
```
Cook + stage + pak + archive a Linux client:
```bash
$ROOT/tools/with_cpu.sh -n 24 $UE/Engine/Build/BatchFiles/RunUAT.sh BuildCookRun -project=$P -platform=Linux \
  -clientconfig=Development -build -cook -stage -pak -archive -archivedirectory=$ROOT/export/ue \
  -unattended -utf8output -nop4 2>&1 | tee /tmp/ue-cook.log | tail -40
```
Add `-nocompileeditor` when the editor binary is already current; drop `-build` when only content changed.

## Exit codes and log parsing
- UBT and UAT return non-zero on failure; trust them. Print the first error, not the tail:
  `grep -m5 -E "error:|Error:|ERROR:" /tmp/ue-build.log`
- UAT summary line: `grep -E "BUILD (SUCCESSFUL|FAILED)|AutomationTool exiting with ExitCode" /tmp/ue-cook.log`
- Record wall time of every build in docs/UNREAL_SPIKE.md section 6.1 during the spike.

## Pitfalls
- Live Coding is Windows-only; Hot Reload on Linux is unreliable. After a successful build, restart any running editor
  or `-game` process; never rely on the in-editor Compile button.
- If incremental builds are unexpectedly slow (minutes for one file), disable UBA locally:
  `~/.config/Unreal Engine/UnrealBuildTool/BuildConfiguration.xml` with
  `<Configuration><BuildConfiguration><bAllowUBAExecutor>false</bAllowUBAExecutor></BuildConfiguration></Configuration>`
  (5.6 regression thread; re-test on 5.8). TODO: measure both ways.
- RAM: a full engine-side action graph can exceed 30 GB with 32 jobs. `with_cpu.sh -n 24` plus
  `-MaxParallelActions=20` (TODO: confirm flag accepted by Build.sh) keeps the box responsive; add a 32 GB swapfile.
- The first build after enabling a plugin compiles that plugin's modules; expect minutes, not seconds.
- Never run two UBT invocations on the same project at once (shared Intermediate/); the CPU lock does not serialise
  them, so check `pgrep -f UnrealBuildTool` first.
- No mono needed: UE 5.x ships its own dotnet under `Engine/Binaries/ThirdParty/DotNet`. If UBT fails to start
  over ICU/libssl, install `icu` and `openssl-1.1` from the CachyOS repos (TODO: confirm which are actually missing).
- Wayland is irrelevant for builds; only the editor GUI needs `SDL_VIDEODRIVER=x11`.
