#!/usr/bin/env python3
"""Sets sane 3D import settings on every extracted texture under assets/models (Godot writes them as lossless
by default when the editor never sees them in 3D): VRAM compression, normal-map flag by name, a size cap by
role (2048 for player figures, leaders and buildings; 1024 for crowd, townsfolk, district and cast figures,
props and interiors). Run after `godot --headless --import`, then import again. Idempotent."""
import re, sys, os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "assets", "models")
HI = ("figure_", "hist_", "watchman", "tenement_", "ten_", "st_marys", "sukiennice", "town_hall", "st_adalbert",
      "kingpin_house", "campanile", "synagogue", "uniate", "collegium", "florian", "barbican", "wawel", "castle")
LO_CROWD = ("npc_", "dist_", "town_", "cast_")


def cap_for(name: str) -> int:
    if name.startswith(HI):
        return 2048
    if name.startswith(LO_CROWD):
        return 1024
    if name.startswith("int_") or name.startswith("kit_") or name.startswith("vendor_"):
        return 1024
    return 2048


def is_normal(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in ("_nrm", "normal", "_norm", "nrm."))


def set_param(text: str, key: str, value: str) -> str:
    pat = re.compile(r"^" + re.escape(key) + r"=.*$", re.M)
    if pat.search(text):
        return pat.sub(f"{key}={value}", text)
    return text.replace("[params]\n", f"[params]\n\n{key}={value}\n", 1)


changed = 0
for path in glob.glob(os.path.join(MODELS, "*.import")):
    text = open(path).read()
    if 'importer="texture"' not in text:
        continue
    base = os.path.basename(path)[:-len(".import")]
    new = text
    new = set_param(new, "compress/mode", "2")
    new = set_param(new, "compress/high_quality", "false")
    new = set_param(new, "compress/normal_map", "1" if is_normal(base) else "0")
    new = set_param(new, "mipmaps/generate", "true")
    new = set_param(new, "process/size_limit", str(cap_for(base)))
    new = set_param(new, "detect_3d/compress_to", "0")
    if new != text:
        open(path, "w").write(new)
        changed += 1
print(f"[import_settings] updated {changed} texture import files")
