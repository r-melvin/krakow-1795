"""Render sheets of the interior rooms (assets/models/int_*.glb) with Eevee, lit by their lamp_ empties.

Run:  blender -b --python assets/blender/render_interiors.py [-- OUTDIR [room room ...]]
Writes OUTDIR/interiors_<room>.png (the view from data/interiors.json `rooms.<room>.view`, else just inside the door
looking down the room) and OUTDIR/interiors_<room>_b.png (from the back looking toward the door, or `view_b`), interiors_<room>_<n>.png for
each of `views`, then
OUTDIR/interiors_sheet.png: every room, both views, labelled (needs ImageMagick `montage`).
"""
import bpy, glob, json, os, subprocess, sys
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.join(PROJ, "assets", "models")
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = args[0] if args else os.path.join(PROJ, "docs", "screenshots")
DATA = json.load(open(os.path.join(PROJ, "data", "interiors.json")))
ENERGY = {"fire": 120, "candle": 25, "lantern": 90, "chandelier": 160, "window": 30, "stove": 50, "oven": 140, "forge": 180, "moon": 15}
COLOUR = {"moon": (0.55, 0.66, 1.0)}
EXTRA = {"int_stair": ((3.0, -2.5, 2.4), (0.0, 1.8, 1.2))}


def godot_to_blender(v):
    return (v[0], -v[2], v[1])


def views(name, bounds):
    """[(suffix, (camera, target))...] in Blender coordinates: the front view, the back view, any extras."""
    if name in EXTRA:
        return [("", EXTRA[name])]
    info = DATA.get("rooms", {}).get(name, {})
    v = info.get("view")
    if v:
        front = (godot_to_blender(v[0]), godot_to_blender(v[1]))
    else:
        front = ((0.4, 0.6, 1.7), (-0.3, 6.0, 1.2))
    lo, hi = bounds
    d = min(hi.y - 0.8, max(3.0, front[1][1]))
    z = front[0][2] + 0.1
    back = ((-0.6 * (front[0][0] or 0.5), d, z), (0.2, 0.3, z - 0.6))
    if info.get("view_b"):
        back = (godot_to_blender(info["view_b"][0]), godot_to_blender(info["view_b"][1]))
    out = [("", front), ("_b", back)]
    for i, e in enumerate(info.get("views", [])):
        out.append(("_%d" % (i + 1), (godot_to_blender(e[0]), godot_to_blender(e[1]))))
    return out


def render(name, cam_pos, target, path):
    sc = bpy.context.scene
    co = sc.camera
    co.location = cam_pos
    co.rotation_euler = (Vector(target) - Vector(cam_pos)).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("[render]", path)


rooms = args[1:] if len(args) > 1 else sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(ROOT, "int_*.glb")))
made = []
for name in rooms:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.eevee.taa_render_samples = 16
    sc.view_settings.view_transform = "AgX"
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.16, 0.19, 0.32, 1)
    bg.inputs[1].default_value = 0.35 if name != "int_stair" else 2.0
    bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, name + ".glb"))
    lo, hi = Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))
    for o in list(sc.objects):
        if "-col" in o.name:
            o.hide_render = True
            continue
        if o.type == "MESH":
            for c in o.bound_box:
                w = o.matrix_world @ Vector(c)
                lo = Vector(map(min, lo, w))
                hi = Vector(map(max, hi, w))
        if o.name.startswith("lamp_"):
            kind = o.name.split("_")[1]
            L = bpy.data.lights.new(o.name + "_L", "POINT")
            L.energy = ENERGY.get(kind, 50)
            L.color = COLOUR.get(kind, (1.0, 0.7, 0.4))
            L.shadow_soft_size = 0.2
            lo_ = bpy.data.objects.new(o.name + "_L", L)
            sc.collection.objects.link(lo_)
            lo_.location = o.matrix_world.translation
    cam = bpy.data.cameras.new("c")
    cam.lens = 14
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    for suffix, (cp, tp) in views(name, (lo, hi)):
        p = os.path.join(OUT, "interiors_%s%s.png" % (name, suffix))
        render(name, cp, tp, p)
        made.append(p)

if len(rooms) > 1:
    try:
        sheet = os.path.join(OUT, "interiors_sheet.png")
        cmd = ["montage"]
        for p in made:
            cmd += ["-label", os.path.basename(p)[10:-4], p]
        cmd += ["-tile", "4x", "-geometry", "480x270+4+4", "-pointsize", "16", "-background", "#222", "-fill", "#eee", sheet]
        subprocess.run(cmd, check=True)
        print("[render] sheet", sheet)
    except Exception as e:
        print("[render] no sheet:", e)
