---
name: ue-import
description: Import a folder of glTF/GLB (or FBX) files from the Blender/MPFB pipeline into the Kraków 1795 Unreal project through Interchange, with per-folder settings (skeletal vs static, morph targets, materials, destination path), headless. Use when new city meshes or characters are exported from assets/blender.
---

# ue-import: Interchange import of a glTF folder

Status: DRAFT. Confirm `TODO` items after install. Depends on `ue-py`.

## When to use
- After `tools/build_all.sh` (or a Blender headless build) writes new `.glb`/`.gltf` under `assets/models/`.
- To re-import after a rig or morph change (same destination path, so references survive).
Inputs: a source folder and a settings JSON (`tools/ue/import_settings/<name>.json`, TODO create) like:
```json
{"src": "assets/models/people", "dest": "/Game/Krakow/People", "kind": "skeletal",
 "morph_targets": true, "import_materials": true, "import_textures": true, "skeleton": "/Game/Krakow/People/SK_MPFB_Skeleton",
 "max_influences": 4, "recompute_normals": false, "uniform_scale": 100.0}
```

## Command
```bash
ROOT=/home/richard/Projects/games/prototypes/krakow-1795
UE=/opt/UE_5.8; P=$ROOT/unreal/Krakow.uproject; ED=$UE/Engine/Binaries/Linux/UnrealEditor-Cmd   # TODO
$ROOT/tools/with_cpu.sh -n 16 $ED $P -run=pythonscript -nullrhi -unattended -nop4 -stdout -FullStdOutLogOutput \
  -script="$ROOT/tools/ue/import_folder.py $ROOT/tools/ue/import_settings/people.json" 2>&1 | tee /tmp/ue-import.log \
  | grep -E "RESULT:|LogInterchange.*(Error|Warning)|LogPython: Error"
```
Core of `import_folder.py` (TODO: write and test; API names from the 5.8 Python reference):
```python
import unreal, json, sys, glob, os
cfg = json.load(open(sys.argv[1]))
mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
for f in sorted(glob.glob(os.path.join(cfg["src"], "*.gl*"))):
    src = unreal.InterchangeManager.create_source_data(f)
    params = unreal.ImportAssetParameters()
    params.is_automated = True
    pipe = unreal.load_asset("/Interchange/Pipelines/DefaultAssetsPipeline").duplicate_object()  # TODO: project pipeline asset instead
    pipe.common_skeletal_meshes_and_animations_properties.import_only_animations = False
    pipe.mesh_pipeline.import_skeletal_meshes = cfg["kind"] == "skeletal"
    pipe.mesh_pipeline.import_static_meshes = cfg["kind"] == "static"
    pipe.mesh_pipeline.import_morph_targets = cfg.get("morph_targets", True)
    pipe.material_pipeline.import_materials = cfg.get("import_materials", True)
    params.override_pipelines = [pipe]
    ok = mgr.import_asset(cfg["dest"], src, params)
    print("RESULT:", json.dumps({"file": f, "ok": bool(ok)}))
unreal.EditorAssetLibrary.save_directory(cfg["dest"])
```
Better practice: save a configured `InterchangePipelineBase` asset once (`/Game/Krakow/Pipelines/IP_People`) and
reference it in `override_pipelines`; then settings live in one asset instead of code.

## Pitfalls
- **Open bug (UE-392966, reported 2026-08 on 5.8): Interchange glTF keeps only 4 bone influences per vertex.**
  Limit MPFB exports to 4 influences in Blender (`Limit Total` weights), or export FBX for characters.
- Community reports that glTF morph targets/animations mis-imported in 5.5/5.6 and work from 5.7 [unverified]:
  after the first import, open one character in `ue-shot` with a morph driven to 1.0 and check.
- glTF units are metres; UE is centimetres. Interchange scales by 100 by default (TODO confirm in 5.8); do not also
  scale in Blender.
- Textures: Blender glTF packs ORM; Interchange creates a material with glTF material functions. For our painted
  look we will instead assign a master material instance per character (see `ue-py` material step).
- Reimport into the same `dest` with the same file stem keeps the asset name, so Blueprints/levels referencing it
  survive; changing the stem creates a duplicate.
- FBX fallback: legacy FBX importer via `unreal.AssetImportTask` + `FbxImportUI`, or Interchange FBX behind
  `Interchange.FeatureFlags.Import.FBX=1` (experimental).
- Runtime (in-game) glTF import does not support skeletal meshes; this skill is editor-only.
- Large imports: hundreds of meshes take minutes (DDC build + shader compile). Run under `with_cpu.sh -n 16` and
  never in parallel with a Blender build (RAM).
