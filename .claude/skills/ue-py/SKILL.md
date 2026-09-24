---
name: ue-py
description: Run a Python script inside the Unreal Editor for Kraków 1795 either headless (commandlet, -nullrhi) or against the already-running editor via Python remote execution, and return its stdout. Use for any editor automation: asset queries, level edits, imports, material instances, DataTable fills.
---

# ue-py: editor Python, headless or live

Status: DRAFT. Confirm `TODO` items after install.

## When to use
- Any task that the `unreal` Python module can do: create/save assets, spawn actors into a level, set properties,
  build material instances, query the asset registry, drive Interchange imports, fill DataTables.
- Prefer the **headless commandlet** for batch/CI-style work (deterministic, no GUI, no GPU).
- Prefer **remote execution** when an editor is already open (MCP session in progress) and you need the result in
  seconds instead of a 20-60 s cold start.
Not for gameplay: editor Python never runs in `-game` or packaged builds.

## Variables
```bash
UE=/opt/UE_5.8                                   # TODO
P=/home/richard/Projects/games/prototypes/krakow-1795/unreal/Krakow.uproject   # TODO
ED=$UE/Engine/Binaries/Linux/UnrealEditor-Cmd
ROOT=/home/richard/Projects/games/prototypes/krakow-1795
COMMON="-unattended -nop4 -nosplash -nosound -stdout -FullStdOutLogOutput"
```
Scripts live in `$ROOT/tools/ue/*.py` (TODO: create the folder). Each script prints a final line
`RESULT: {json}` so callers can parse it.

## Headless commandlet (fastest, no level loaded)
```bash
$ROOT/tools/with_cpu.sh -n 8 $ED $P -run=pythonscript -script=$ROOT/tools/ue/list_assets.py -nullrhi $COMMON \
  2>&1 | tee /tmp/ue-py.log | grep -E "^LogPython|RESULT:|Error:" 
```
- If the script needs a level: first line `unreal.EditorLoadingAndSavingUtils.load_map("/Game/Maps/City")`.
- Inline code: `-script="import unreal\nprint(unreal.SystemLibrary.get_engine_version())"`.
- Full editor init instead (loads startup map, runs `init_unreal.py`, exits when done):
  `$ED $P -ExecutePythonScript=$ROOT/tools/ue/x.py -nullrhi $COMMON`.

## Live editor via remote execution
One-time: Project Settings > Plugins > Python > **Enable Remote Execution** (writes
`[/Script/PythonScriptPlugin.PythonScriptPluginSettings] bRemoteExecution=True` to `Config/DefaultEngine.ini`;
TODO confirm key name). Defaults: multicast 239.0.0.1:6766, command TCP 127.0.0.1:6776.
```bash
python3 - <<'PY'
import sys; sys.path.append("/opt/UE_5.8/Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python")  # TODO path
import remote_execution as r
re = r.RemoteExecution(); re.start()
import time; t=time.time()
while not re.remote_nodes and time.time()-t < 5: time.sleep(0.1)
re.open_command_connection(re.remote_nodes[0]["node_id"])
res = re.run_command(open(sys.argv[1] if len(sys.argv)>1 else "/dev/stdin").read(), exec_mode=r.MODE_EXEC_FILE)
print(res.get("output")); re.stop()
PY
```
Alternative when the Epic MCP server is up: call `ProgrammaticToolset.execute_tool_script` through the official
`unreal-mcp` skill instead of this path.

## Returning stdout
- Commandlet: all `print()` output arrives on stdout prefixed `LogPython:`; the process exit code is 0 even when the
  script raised. Detect failure with `grep -E "LogPython: Error|Traceback" /tmp/ue-py.log`.
- Remote execution: `res["success"]` and `res["output"]` (a list of `{type, output}` dicts).

## Pitfalls
- Python is 3.11.8 bundled; no pip into the engine. Pure-Python helpers go in `tools/ue/lib/`; add it to
  `sys.path` at the top of each script.
- `unreal.EditorLevelLibrary` is deprecated: use `unreal.get_editor_subsystem(unreal.EditorActorSubsystem)`,
  `LevelEditorSubsystem`, `EditorAssetSubsystem`, `UnrealEditorSubsystem`.
- Always `unreal.EditorAssetLibrary.save_directory("/Game/Krakow")` (or `save_loaded_asset`) before exit;
  the commandlet does not autosave.
- Commandlets skip most shader compilation but the first run after a big import still compiles for minutes.
- Two editor processes on the same project fight over the DDC and asset registry; do not run a commandlet while
  a live editor has unsaved changes to the same assets.
- Startup time is the tax: batch many operations per script and pass a JSON job file rather than looping the process.
