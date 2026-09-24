"""Contact sheets for assets/models/anim_library.glb, retargeted onto real characters the way Godot does it.

Run:
  blender -b --python assets/blender/render_animations.py -- [--char watchman] [--out DIR] [--frames 6] [clip ...]
      one sheet per clip: side view on top, 3/4 front below
  blender -b --python assets/blender/render_animations.py -- --review [--out DIR] [--frames 8] [clip ...]
      fight review: 5 rows (front, left side, right side, 3/4 front, back) x 8 frames per clip. Player weapon clips
      play on figure_veteran with a stand-in prop in hand_r (cudgel, sabre, knife or pistol); guard and reaction clips
      on the watchman with his welded musket; takedown plays as a pair (veteran behind, watchman in front at
      TAKEDOWN_OFFSET, the offset scripts should snap to).

Retarget rule (identical to scripts/core/assets.gd): the library bone's rotation, expressed as a world-space
delta from its rest (R = Qlib @ basis @ Qlib^-1), is applied to the target bone's own rest
(basis_t = Qt^-1 @ R @ Qt). The pelvis translation is scaled by the ratio of pelvis heights.
"""
import bpy
import math
import os
import subprocess
import sys
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS = os.path.join(ROOT, "assets", "models")
TAKEDOWN_OFFSET = 0.22      # victim origin this far in front of the attacker, both facing the same way (= build_animations)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    if name in argv:
        i = argv.index(name)
        v = argv[i + 1]
        del argv[i:i + 2]
        return v
    return default


REVIEW = "--review" in argv
if REVIEW:
    argv.remove("--review")
CHAR = opt("--char", "watchman")
OUTDIR = opt("--out", "/tmp/anim_sheets")
NFRAMES = int(opt("--frames", "8" if REVIEW else "6"))
ONLY = [a for a in argv if not a.startswith("--")]
os.makedirs(os.path.join(OUTDIR, "tiles"), exist_ok=True)

PLAYER_CLIPS = {"attack_swing": "cudgel", "attack_thrust": "cudgel", "block": "cudgel", "sabre_draw": "sabre", "sabre_slash": "sabre",
                "sabre_parry": "sabre", "knife_stab": "knife", "pistol_draw": "pistol", "pistol_aim": "pistol", "pistol_fire": "pistol",
                "takedown": None, "fall_land_roll": None, "stumble": None,
                "walk": None, "walk_player": None, "walk_fast": None, "run": None, "sneak": None, "carry_basket": None}
GUARD_CLIPS = ["musket_ready", "musket_present", "musket_aim", "musket_fire", "musket_reload", "bayonet_thrust", "musket_butt", "guard_seize",
               "hit_react", "hit_react_back", "stagger", "shoved", "grabbed", "knocked_down", "knocked_down_forward", "death_fall",
               "death_fall_forward", "death_kneel", "death_musket", "get_up", "get_up_prone"]
REVIEW_CLIPS = list(PLAYER_CLIPS) + GUARD_CLIPS


def import_glb(path):
    before = set(bpy.data.objects)
    acts = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    rig = next(o for o in new if o.type == "ARMATURE")
    return rig, new, [a for a in bpy.data.actions if a not in acts]


class Target:
    """An imported character that receives retargeted library poses."""

    def __init__(self, name):
        self.rig, self.objs, acts = import_glb(os.path.join(MODELS, name + ".glb"))
        for a in acts:
            bpy.data.actions.remove(a)
        if self.rig.animation_data:
            for tr in list(self.rig.animation_data.nla_tracks):
                self.rig.animation_data.nla_tracks.remove(tr)
            self.rig.animation_data.action = None
        self.q = {b.name: b.matrix_local.to_quaternion() for b in self.rig.data.bones}
        self.scale = self.rig.data.bones["pelvis"].head_local.z / lib.data.bones["pelvis"].head_local.z
        for pb in self.rig.pose.bones:
            pb.rotation_mode = "QUATERNION"

    def apply(self, pose):
        for name, (q, loc) in pose.items():
            if name not in self.q:
                continue
            R = qlib[name] @ q @ qlib[name].inverted()
            pb = self.rig.pose.bones[name]
            pb.rotation_quaternion = self.q[name].inverted() @ R @ self.q[name]
            if name == "pelvis":
                pb.location = self.q[name].inverted() @ ((qlib[name] @ loc) * self.scale)
            else:
                pb.location = (0, 0, 0)

    def hide(self, h):
        for o in self.objs:
            if o.type == "MESH" and not o.name.startswith("Icosphere"):
                o.hide_render = h


bpy.ops.wm.read_factory_settings(use_empty=True)
lib, lib_objs, lib_acts = import_glb(os.path.join(MODELS, "anim_library.glb"))
for o in lib_objs:
    if o.type == "MESH":
        o.hide_render = True
clips = {a.name: a for a in lib_acts}
if lib.animation_data:
    for tr in list(lib.animation_data.nla_tracks):
        lib.animation_data.nla_tracks.remove(tr)
else:
    lib.animation_data_create()
qlib = {b.name: b.matrix_local.to_quaternion() for b in lib.data.bones}
print("[render] clips:", len(clips))

sc = bpy.context.scene


def eval_lib(act, frame):
    lib.animation_data.action = act
    if hasattr(lib.animation_data, "action_slot") and act.slots:
        lib.animation_data.action_slot = act.slots[0]
    sc.frame_set(int(frame), subframe=frame - int(frame))
    return {pb.name: (pb.rotation_quaternion.copy(), pb.location.copy()) for pb in lib.pose.bones}


# ---- stage
def material(name, rgb):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1)
    return m


bpy.ops.mesh.primitive_plane_add(size=10, location=(0, 0, 0))
ground = bpy.context.object
ground.data.materials.append(material("ground", (0.35, 0.37, 0.33)))
# 0.25 m grid lines on the ground so feet sliding / planting reads
for i in range(-8, 9):
    for axis in (0, 1):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(i * 0.25 if axis == 0 else 0, i * 0.25 if axis == 1 else 0, 0.001))
        ln = bpy.context.object
        ln.scale = (0.006, 4.0, 0.001) if axis == 0 else (4.0, 0.006, 0.001)
        ln.data.materials.append(material("grid", (0.26, 0.27, 0.24)))
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -1.05, 0.5))
ledge = bpy.context.object
ledge.data.materials.append(ground.data.materials[0])
ledge.hide_render = True
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.color_type = "TEXTURE"
sc.display.shading.show_shadows = True
sc.display.shading.show_cavity = True
sc.render.film_transparent = False
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.75, 0.78, 0.82)
cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam


def aim(pos, target):
    cam.location = pos
    cam.rotation_euler = (Vector(target) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()


def render(path):
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


# ---- props for the review (stand-ins: the player figures carry no weapons)
def make_prop(kind, tgt):
    """A simple weapon parented to hand_r: it crosses the fist along the thumb direction (pistol: along the hand)."""
    rig = tgt.rig
    bone = rig.data.bones["hand_r"]
    head = bone.head_local
    d = (rig.data.bones["middle_01_r"].head_local - head).normalized()          # wrist -> knuckles
    fist = head + d * 0.075
    thumb = (rig.data.bones["thumb_02_r"].head_local - head)
    t = (thumb - d * thumb.dot(d)).normalized()                                 # across the palm, thumb side
    wood, steel = material("wood", (0.30, 0.18, 0.09)), material("steel", (0.62, 0.63, 0.66))
    parts = []

    def rod(r, length, start, axis, mat, verts=10):
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=length)
        o = bpy.context.object
        o.matrix_world = Matrix.Translation(start + axis * length / 2) @ axis.to_track_quat("Z", "Y").to_matrix().to_4x4()
        o.data.materials.append(mat)
        parts.append(o)
    if kind == "cudgel":
        rod(0.022, 0.12, fist - t * 0.10, t, wood)
        rod(0.032, 0.58, fist + t * 0.02, t, wood)
    elif kind == "sabre":
        rod(0.016, 0.14, fist - t * 0.05, t, material("grip", (0.1, 0.08, 0.07)))
        rod(0.045, 0.012, fist + t * 0.08, t, material("brass", (0.8, 0.62, 0.25)), verts=16)
        bpy.ops.mesh.primitive_cube_add(size=1)
        b = bpy.context.object
        b.matrix_world = Matrix.Translation(fist + t * 0.50) @ t.to_track_quat("Z", "Y").to_matrix().to_4x4() @ Matrix.Diagonal((0.006, 0.030, 0.82, 1))
        b.data.materials.append(steel)
        parts.append(b)
    elif kind == "knife":
        rod(0.014, 0.10, fist - t * 0.05, t, wood)
        rod(0.010, 0.17, fist + t * 0.05, t, steel, verts=6)
    elif kind == "pistol":
        rod(0.016, 0.11, fist - t * 0.03, t, wood)                              # grip across the fist
        rod(0.011, 0.30, fist + t * 0.06 - d * 0.03, d, steel)                  # barrel along the hand
    tail = rig.matrix_world @ bone.matrix_local @ Matrix.Translation((0, bone.length, 0))
    for o in parts:
        o.color = (0.85, 0.85, 0.9, 1) if kind in ("sabre", "knife") and o.dimensions.z > 0.15 else (0.30, 0.18, 0.08, 1)
        mw = o.matrix_world.copy()
        o.parent = rig
        o.parent_type = "BONE"
        o.parent_bone = "hand_r"
        o.matrix_parent_inverse = tail.inverted()
        o.matrix_basis = mw
    return parts


def sheet(name, rows, title):
    out = os.path.join(OUTDIR, name + ".png")
    files = [f for row in rows for f in row]
    subprocess.run(["montage"] + files + ["-tile", "%dx%d" % (len(rows[0]), len(rows)), "-geometry", "+2+2",
                    "-title", title, "-pointsize", "18", out], check=False)
    print("[render] sheet", out)


# ------------------------------------------------------------------ review mode
if REVIEW:
    sc.render.resolution_x = 190
    sc.render.resolution_y = 240
    vet = Target("figure_veteran")
    wat = Target("watchman")
    # flat object colours so limbs, weapons and the two bodies of the takedown pair read apart
    sc.display.shading.color_type = "OBJECT"
    MUSKET_PARTS = ("stock", "butt", "barrel", "muzzle", "ramrod", "lock", "cock", "trigger", "band", "sling")
    for tg, rgb in ((vet, (0.72, 0.42, 0.26)), (wat, (0.55, 0.68, 0.86))):
        for o in tg.objs:
            if o.type == "MESH":
                o.color = (*rgb, 1)
                if o.name.startswith(MUSKET_PARTS):
                    o.color = (0.22, 0.13, 0.06, 1)
                if "high-poly" in o.name or "eye" in o.name.lower() or "teeth" in o.name:
                    o.color = (0.9, 0.9, 0.9, 1)
    ground.color = (0.36, 0.37, 0.34, 1)
    for o in bpy.data.objects:
        if o.name.startswith("Cube") and o is not ledge:
            o.color = (0.26, 0.27, 0.24, 1)
    wat_victim_pos = Vector((0, -TAKEDOWN_OFFSET, 0))       # the characters face -Y
    props = {k: make_prop(k, vet) for k in ("cudgel", "sabre", "knife", "pistol")}
    VIEWS = [("front", (0, -6, 1.1)), ("left", (6, 0, 1.0)), ("right", (-6, 0, 1.0)), ("front34", (4.2, -4.2, 1.9)), ("back", (0, 6, 1.2))]
    names = [n for n in REVIEW_CLIPS if n in clips and (not ONLY or n in ONLY)]
    for name in names:
        act = clips[name]
        f0, f1 = act.frame_range
        player = name in PLAYER_CLIPS
        pair = name == "takedown"
        vet.hide(not player)
        wat.hide(player and not pair)
        wat.rig.location = wat_victim_pos if pair else (0, 0, 0)
        for k, ps in props.items():
            for o in ps:
                o.hide_render = not (player and PLAYER_CLIPS.get(name) == k)
        floor = name.startswith(("knocked", "death", "get_up", "fall", "stumble", "stagger", "takedown"))
        cam_data.ortho_scale = 3.6 if floor else 2.7
        rows = {v: [] for v, _ in VIEWS}
        victim = clips.get("takedown_victim")
        for i in range(NFRAMES):
            fr = f0 + (f1 - f0) * i / (NFRAMES - 1)
            pose = eval_lib(act, fr)
            (vet if player else wat).apply(pose)
            if pair and victim:
                wat.apply(eval_lib(victim, victim.frame_range[0] + (victim.frame_range[1] - victim.frame_range[0]) * i / (NFRAMES - 1)))
            bpy.context.view_layer.update()
            centre = Vector((0, -TAKEDOWN_OFFSET * 0.5 if pair else 0, 0.85 if not floor else 0.6))
            for v, pos in VIEWS:
                aim(Vector(pos) + Vector((0, centre.y, 0)), centre)
                p = os.path.join(OUTDIR, "tiles", "%s_%s_%d.png" % (name, v, i))
                render(p)
                rows[v].append(p)
        who = ("veteran + %s" % PLAYER_CLIPS[name]) if player and PLAYER_CLIPS[name] else ("veteran (behind) + watchman" if pair else ("veteran" if player else "watchman"))
        sheet(name, [rows[v] for v, _ in VIEWS], "%s  (%s, %.2f s)   rows: front / left / right / 3-4 front / back" % (name, who, (f1 - f0) / sc.render.fps))
    sys.exit(0)


# ------------------------------------------------------------------ plain mode
sc.render.resolution_x = 260
sc.render.resolution_y = 330
tgt = Target(CHAR)
VIEWS = {"side": ((6.0, 0.0, 1.0), (0, 0, 0.85)), "front34": ((4.2, -4.2, 1.9), (0, 0, 0.8))}
names = [n for n in sorted(clips) if not ONLY or n in ONLY]
for name in names:
    act = clips[name]
    f0, f1 = act.frame_range
    ledge.hide_render = name not in ("climb_short", "crouch_hide")
    ledge.scale = (1.6, 0.6, 1.0) if name == "climb_short" else (1.6, 0.3, 1.6)
    ledge.location = (0, -0.75, 0.5) if name == "climb_short" else (0, 0.62, 0.8)
    tiles = {v: [] for v in VIEWS}
    for i in range(NFRAMES):
        fr = f0 + (f1 - f0) * i / max(1, NFRAMES - 1)
        tgt.apply(eval_lib(act, fr))
        bpy.context.view_layer.update()
        for v, (pos, target) in VIEWS.items():
            aim(pos, target)
            big = name.startswith(("prone", "knocked", "death", "get_up", "fall", "climb", "crouch_crawl", "takedown", "stumble", "crouch_to", "stagger"))
            cam_data.ortho_scale = 3.4 if big else 2.4
            p = os.path.join(OUTDIR, "tiles", "%s_%s_%d.png" % (name, v, i))
            render(p)
            tiles[v].append(p)
    sheet(name, [tiles["side"], tiles["front34"]], "%s  (%s, %d frames)" % (name, CHAR, int(f1 - f0)))
