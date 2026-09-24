---
name: ue-data
description: Sync Kraków 1795's JSON sources in data/ (missions, npcs, factions, rumours, stealth, city_layout, ...) into Unreal DataTables/DataAssets headless, keeping JSON as the single source of truth. Use after editing any data/*.json when the Unreal project reads DataTables rather than raw JSON.
---

# ue-data: JSON to DataTable sync

Status: DRAFT. Confirm `TODO` items after install. Depends on `ue-py`.

## Decision first
Two valid designs; the spike should pick one on day 2:
1. **Read JSON at runtime in C++** (`FFileHelper` + `FJsonObjectConverter::JsonObjectStringToUStruct`) from
   `Content/Data/*.json` copied verbatim from `data/`. Zero asset churn, diffs stay text, no sync step. Mark the
   folder as a non-asset directory to cook (`[/Script/UnrealEd.ProjectPackagingSettings] +DirectoriesToAlwaysStageAsUFS=(Path="Data")`).
2. **DataTables** for tabular files (editor tooling, references from Blueprints/Details panels). This skill covers 2;
   with 1 the "sync" is `rsync -a data/ unreal/Content/Data/`.

## Row structs
Each table needs a C++ `USTRUCT(BlueprintType)` deriving from `FTableRowBase` in
`unreal/Source/KrakowCore/Data/*.h` (TODO create), fields named exactly as the JSON keys (UE matches by
property name, case-insensitive; nested objects need nested USTRUCTs; arrays map to `TArray`).
Our JSON is mostly `{ "id": {...}, ... }` or `[ {...}, ... ]`; UE's importer expects an **array of objects with a
`Name` key** per row. `tools/ue/json_to_dt.py` (TODO) converts:
```python
def to_rows(obj, key="id"):
    if isinstance(obj, dict): return [{"Name": k, **v} for k, v in obj.items()]
    return [{"Name": r.get(key, str(i)), **r} for i, r in enumerate(obj)]
```

## Command
```bash
ROOT=/home/richard/Projects/games/prototypes/krakow-1795
UE=/opt/UE_5.8; P=$ROOT/unreal/Krakow.uproject; ED=$UE/Engine/Binaries/Linux/UnrealEditor-Cmd   # TODO
$ROOT/tools/with_cpu.sh -n 8 $ED $P -run=pythonscript -nullrhi -unattended -nop4 -stdout -FullStdOutLogOutput \
  -script="$ROOT/tools/ue/sync_data.py $ROOT/tools/ue/data_map.json" 2>&1 | grep -E "RESULT:|LogDataTable|LogPython: Error"
```
`tools/ue/data_map.json` (TODO) lists `{"data/missions.json": {"table": "/Game/Krakow/Data/DT_Missions", "struct": "/Script/KrakowCore.MissionRow", "key": "id"}, ...}`.
`sync_data.py` core:
```python
import unreal, json, sys, tempfile
from json_to_dt import to_rows
m = json.load(open(sys.argv[1])); eal = unreal.EditorAssetLibrary
for src, spec in m.items():
    rows = to_rows(json.load(open(src)), spec.get("key", "id"))
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(rows, tmp); tmp.close()
    struct = unreal.load_object(None, spec["struct"])
    dt = eal.load_asset(spec["table"])
    if not dt:
        f = unreal.DataTableFactory(); f.struct = struct
        pkg, name = spec["table"].rsplit("/", 1)
        dt = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, pkg, unreal.DataTable, f)
    ok = unreal.DataTableFunctionLibrary.fill_data_table_from_json_file(dt, tmp.name, struct)
    eal.save_loaded_asset(dt)
    print("RESULT:", json.dumps({"table": spec["table"], "rows": len(rows), "ok": bool(ok)}))
```
Passing the struct as the third argument forces an automated import (no dialogs).

## Verification
- `ok` false: the log names the offending row/field (`LogDataTable: Error`). Common causes: a key present in JSON
  but missing from the USTRUCT (fatal for import), enum strings not matching `UENUM` names, numbers where UE expects
  `FName`.
- Round-trip check: `unreal.DataTableFunctionLibrary.get_data_table_row_names(dt)` count equals `len(rows)`.

## Pitfalls
- DataTables are binary `.uasset`; commit them as build outputs (LFS) but never edit them in the editor; the JSON wins
  on next sync. Consider `.gitattributes` `unreal/Content/Krakow/Data/** -diff`.
- Struct changes require `ue-build` (editor target) before the sync, or the commandlet loads the old struct.
- Nested arrays of structs are fine; maps (`TMap`) import only with string keys.
- `city_layout.json` and `campaign.json` are graphs, not tables: keep those as runtime JSON (design 1) or split
  them into several tables (nodes, edges, phases).
- Large files (`missions.json` is 7k lines) import in seconds; the 20-60 s cost is editor startup, so sync all
  tables in one process.
