"""Contact sheets for assets/models/anim_library.glb, retargeted onto a real character the way Godot does it.

Run:  blender -b --python assets/blender/render_animations.py -- [--char watchman] [--out DIR] [--frames 6] [clip ...]
Out:  DIR/<clip>.png: 6 frames per clip, top row side view, bottom row 3/4 front view, with a ground plane.

Retarget rule (identical to scripts/core/assets.gd): the library bone's rotation, expressed as a world-space
delta from its rest (R = Qlib @ basis @ Qlib^-1), is applied to the target bone's own rest
(basis_t = Qt^-1 @ R @ Qt). The pelvis translation is scaled by the ratio of pelvis heights.
"""
import bpy
import os
import subprocess
import sys
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS = os.path.join(ROOT, "assets", "models")

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    if name in argv:
        i = argv.index(name)
        v = argv[i + 1]
        del argv[i:i + 2]
        return v
    return default


CHAR = opt("--char", "watchman")
OUTDIR = opt("--out", "/tmp/anim_sheets")
NFRAMES = int(opt("--frames", "6"))
ONLY = [a for a in argv if not a.startswith("--")]
os.makedirs(os.path.join(OUTDIR, "tiles"), exist_ok=True)


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    rig = next(o for o in new if o.type == "ARMATURE")
    return rig, new


bpy.ops.wm.read_factory_settings(use_empty=True)
acts_before = set(bpy.data.actions)
tgt, tgt_objs = import_glb(os.path.join(MODELS, CHAR + ".glb"))
for a in list(bpy.data.actions):
    if a not in acts_before:
        bpy.data.actions.remove(a)
if tgt.animation_data:
    for tr in list(tgt.animation_data.nla_tracks):
        tgt.animation_data.nla_tracks.remove(tr)
    tgt.animation_data.action = None
acts_before = set(bpy.data.actions)
lib, lib_objs = import_glb(os.path.join(MODELS, "anim_library.glb"))
for o in lib_objs:
    if o.type == "MESH":
        o.hide_render = True
clips = {a.name: a for a in bpy.data.actions if a not in acts_before}
if lib.animation_data:
    for tr in list(lib.animation_data.nla_tracks):
        lib.animation_data.nla_tracks.remove(tr)
else:
    lib.animation_data_create()
print("[render] clips:", len(clips), sorted(clips))

qlib = {b.name: b.matrix_local.to_quaternion() for b in lib.data.bones}
qt = {b.name: b.matrix_local.to_quaternion() for b in tgt.data.bones}
scale = tgt.data.bones["pelvis"].head_local.z / lib.data.bones["pelvis"].head_local.z
for pb in tgt.pose.bones:
    pb.rotation_mode = "QUATERNION"

# ---- stage: ground, light, cameras
sc = bpy.context.scene
bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
ground = bpy.context.object
gm = bpy.data.materials.new("ground")
gm.diffuse_color = (0.35, 0.37, 0.33, 1)
ground.data.materials.append(gm)
# a 1 m ledge block and a wall behind (for climb / hide reading), hidden unless needed
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -1.05, 0.5))
ledge = bpy.context.object
ledge.scale = (1.6, 0.6, 1.0)
ledge.data.materials.append(gm)
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "TEXTURE"
sc.display.shading.show_shadows = True
sc.display.shading.show_cavity = True
sc.render.resolution_x = 260
sc.render.resolution_y = 330
sc.render.film_transparent = False
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.75, 0.78, 0.82)
cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam


def aim(obj, pos, target):
    obj.location = pos
    d = Vector(target) - Vector(pos)
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


VIEWS = {
    "side": ((6.0, 0.0, 1.0), (0, 0, 0.85)),
    "front34": ((4.2, -4.2, 1.9), (0, 0, 0.8)),
}


def eval_lib(act, frame):
    lib.animation_data.action = act
    if hasattr(lib.animation_data, "action_slot") and act.slots:
        lib.animation_data.action_slot = act.slots[0]
    sc.frame_set(int(frame), subframe=frame - int(frame))
    out = {}
    for pb in lib.pose.bones:
        q = pb.rotation_quaternion if pb.rotation_mode == "QUATERNION" else pb.matrix_basis.to_quaternion()
        out[pb.name] = (q.copy(), pb.location.copy())
    return out


def apply(pose):
    for name, (q, loc) in pose.items():
        if name not in qt:
            continue
        R = qlib[name] @ q @ qlib[name].inverted()
        pb = tgt.pose.bones[name]
        pb.rotation_quaternion = qt[name].inverted() @ R @ qt[name]
        if name == "pelvis":
            off = qlib[name] @ loc
            pb.location = qt[name].inverted() @ (off * scale)
        else:
            pb.location = (0, 0, 0)
    bpy.context.view_layer.update()


names = [n for n in sorted(clips) if not ONLY or n in ONLY]
for name in names:
    act = clips[name]
    f0, f1 = act.frame_range
    ledge.hide_render = name not in ("climb_short", "crouch_hide")
    ledge.location = (0, -0.75, 0.5) if name == "climb_short" else (0, 0.62, 0.5)
    ledge.scale = (1.6, 0.6, 1.0) if name == "climb_short" else (1.6, 0.3, 1.6)
    ledge.location.z = ledge.scale.z / 2
    tiles = {v: [] for v in VIEWS}
    for i in range(NFRAMES):
        fr = f0 + (f1 - f0) * i / max(1, NFRAMES - 1) if not name.endswith("_loop") else f0 + (f1 - f0) * i / NFRAMES
        apply(eval_lib(act, fr))
        for v, (pos, target) in VIEWS.items():
            aim(cam, pos, target)
            big = name.startswith(("prone", "knocked", "death", "get_up", "fall", "climb", "crouch_crawl", "takedown", "stumble", "crouch_to", "stagger"))
            cam_data.ortho_scale = 3.4 if big else 2.4
            p = os.path.join(OUTDIR, "tiles", "%s_%s_%d.png" % (name, v, i))
            sc.render.filepath = p
            bpy.ops.render.render(write_still=True)
            tiles[v].append(p)
    out = os.path.join(OUTDIR, name + ".png")
    subprocess.run(["montage"] + tiles["side"] + tiles["front34"] + ["-tile", "%dx2" % NFRAMES, "-geometry", "+2+2",
                    "-title", "%s  (%s, %d frames)" % (name, CHAR, int(f1 - f0)), "-pointsize", "18", out], check=False)
    print("[render] sheet", out)
