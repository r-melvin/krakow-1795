---
name: ue-test
description: Run the Kraków 1795 Unreal automation tests headless (the Unreal equivalent of `godot --headless -- --smoke`), parse index.json into pass/fail per test, and return a non-zero exit on failure. Use after C++ or data changes and before committing.
---

# ue-test: headless Automation tests with parsed results

Status: DRAFT. Confirm `TODO` items after install.

## When to use
- After any change to `unreal/Source/` (run `ue-build` first) or to `data/*.json`.
- As the gate before commits, exactly where `--smoke` is used today.

## Test layout (convention)
- C++ tests in `unreal/Source/KrakowCore/Tests/*.spec.cpp` using `IMPLEMENT_SIMPLE_AUTOMATION_TEST` or
  `DEFINE_SPEC`, names `Krakow.Data.Missions`, `Krakow.Stealth.Visibility`, `Krakow.Campaign.SevenNights`.
- Flags: `EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter` so they run under `-nullrhi`
  in the editor commandlet without a viewport. Level-based functional tests need a map: use `Krakow.World.*` and
  load `/Game/Maps/TestCity` inside the test.

## Command
```bash
ROOT=/home/richard/Projects/games/prototypes/krakow-1795
UE=/opt/UE_5.8; P=$ROOT/unreal/Krakow.uproject; ED=$UE/Engine/Binaries/Linux/UnrealEditor-Cmd   # TODO
R=/tmp/ue-report; rm -rf $R; mkdir -p $R
$ROOT/tools/with_cpu.sh -n 16 timeout 1200 $ED $P -nullrhi -unattended -nop4 -nosplash -nosound \
  -stdout -FullStdOutLogOutput -NoLiveCoding \
  -ExecCmds="Automation RunTests Krakow" -TestExit="Automation Test Queue Empty" \
  -ReportExportPath=$R -abslog=$R/run.log > /dev/null 2>&1
python3 $ROOT/tools/ue/parse_report.py $R/index.json; echo "tests exit=$?"
```
Filters: `Automation RunTests Krakow.Stealth` (prefix), `Automation RunFilter Smoke`, `Automation List` to enumerate.
Multiple commands separated by `;`.

`tools/ue/parse_report.py` (TODO create):
```python
import json, sys
r = json.load(open(sys.argv[1])); bad = 0
for t in r.get("tests", []):
    st = t.get("state"); print(f"{st:8} {t.get('fullTestPath')}")
    if st != "Success":
        bad += 1
        for e in t.get("entries", []):
            if e.get("event", {}).get("type") in ("Error", "Warning"): print("   ", e["event"].get("message"))
print(f"{r.get('succeeded',0)} passed, {r.get('failed',0)} failed, {r.get('notRun',0)} not run")
sys.exit(1 if bad or r.get("failed", 0) else 0)
```
(Field names `tests`, `state`, `fullTestPath`, `entries`, `succeeded`, `failed` are from the 5.x report schema;
TODO verify against a real `index.json`.)

## Gauntlet (later, for packaged builds)
```bash
$UE/Engine/Build/BatchFiles/RunUAT.sh RunUnreal -project=$P -platform=Linux -configuration=Development \
  -build=editor -test=UE.EditorAutomation -runtest="Krakow" -unattended
```
UAT returns non-zero on failure and writes logs under `Saved/Logs`/`-uploaddir`.

## Pitfalls
- **The editor process exits 0 even when tests fail.** Only the parsed `index.json` (or UAT) is authoritative.
- If `index.json` is missing, the run crashed or never reached the queue: `grep -E "Fatal|Assertion|Error:" $R/run.log | head`.
- `-TestExit` matches a log line; if a test hangs the process never exits, hence `timeout 1200`.
- Tests that touch rendering, PIE, or Slate need the editor with an RHI (drop `-nullrhi`, add the GPU lock); keep
  those in a separate `Krakow.Visual.*` group run by `ue-shot`-style jobs.
- Do not run tests while another editor instance has the project open with unsaved changes (asset registry races).
- First run after a build or import pays shader/DDC time; keep the DDC on NVMe and never delete it casually.
- Warnings are not failures by default; if the smoke should fail on `SCRIPT ERROR`-style log errors as today,
  set `bSuppressLogErrors=false`/`bElevateLogWarningsToErrors` in `[/Script/AutomationController.AutomationControllerSettings]` (TODO confirm keys).
