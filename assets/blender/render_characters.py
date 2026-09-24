"""Render check for exported characters: front / three-quarter / side / back, a walk frame, and a face close-up.
Run: blender -b --python assets/blender/render_characters.py -- <outdir> name1 name2 ..."""
import bpy, math, os, sys
from mathutils import Vector
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS = os.environ.get("MODELS_DIR") or os.path.join(ROOT, "assets", "models")
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = args[0] if args else os.path.join(ROOT, "docs", "screenshots")
names = args[1:] or ["watchman"]

def scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    # RENDER_ENGINE=CYCLES renders on the CPU (for when Eevee's EGL context fails on the GPU driver)
    if os.environ.get("RENDER_ENGINE", "").upper() == "CYCLES":
        sc.render.engine = "CYCLES"
        sc.cycles.device = "CPU"
        sc.cycles.samples = int(os.environ.get("CYCLES_SAMPLES", "24"))
        sc.cycles.use_denoising = True
        sc.cycles.max_bounces = 4
    else:
        sc.render.engine = "BLENDER_EEVEE"
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.42, 0.47, 0.56, 1)
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    def sun(name, energy, colour, rx, rz, angle=0.6):
        l = bpy.data.lights.new(name, "SUN"); l.energy = energy; l.color = colour; l.angle = angle
        o = bpy.data.objects.new(name, l); sc.collection.objects.link(o); o.rotation_euler = (math.radians(rx), 0, math.radians(rz))
    sun("key", 2.6, (1.0, 0.93, 0.82), 50, 35)          # warm key, front-left, high
    sun("fill", 0.9, (0.80, 0.88, 1.0), 65, -110)       # cool soft fill from the other side
    sun("rim", 2.0, (1.0, 0.97, 0.9), 35, 160, 0.3)     # rim from behind
    # small bright lamp near the camera: the catch-light in the eyes and the sheen on wet or glossy surfaces
    cl = bpy.data.lights.new("catch", "AREA"); cl.energy = 60.0; cl.color = (1.0, 0.98, 0.95); cl.size = 0.25
    co = bpy.data.objects.new("catch", cl); sc.collection.objects.link(co)
    co.location = (-0.6, -2.2, 1.95); co.rotation_euler = (math.radians(80), 0, math.radians(-15))
    try:
        sc.eevee.use_gtao = True
        sc.eevee.gtao_distance = 0.25
    except AttributeError:
        pass
    try:
        sc.eevee.use_shadows = True
        sc.eevee.use_raytracing = True
    except AttributeError:
        pass
    return sc

def cam(sc, loc, target, lens=50):
    c = bpy.data.cameras.new("c"); c.lens = lens
    co = bpy.data.objects.new("cam", c); sc.collection.objects.link(co); sc.camera = co
    co.location = loc
    d = (target[0]-loc[0], target[1]-loc[1], target[2]-loc[2])
    co.rotation_euler = (math.atan2(math.hypot(d[0], d[1]), -d[2]), 0, math.atan2(d[1], d[0]) - math.pi/2)
    return co

def lib_walk():
    """The walk clip: the model's own if it has one, else the shared anim_library.glb's (characters no longer bake
    idle/walk). Library clips are authored on a reference rest pose, so this is a close preview, not the retarget
    Godot does."""
    before_a, before_o = set(bpy.data.actions), set(bpy.data.objects)
    path = os.path.join(MODELS, "anim_library.glb")
    if not os.path.exists(path):
        return None
    bpy.ops.import_scene.gltf(filepath=path)
    new = [a for a in bpy.data.actions if a not in before_a]
    for a in new:
        a.use_fake_user = True
    for o in [o for o in bpy.data.objects if o not in before_o]:
        bpy.data.objects.remove(o)
    walk = [a for a in new if a.name.lower().split(".")[0].split("_")[-1] == "walk" or a.name.lower().startswith("walk")]
    walk = [a for a in walk if not any(k in a.name.lower() for k in ("fast", "carry"))]
    return walk[0] if walk else None


def load(name, x=0.0, rz=0.0):
    bpy.ops.import_scene.gltf(filepath=os.path.join(MODELS, name + ".glb"))
    objs = list(bpy.context.selected_objects)
    root = [o for o in objs if o.parent is None][0]
    root.rotation_mode = "XYZ"
    root.location.x = x
    root.rotation_euler = (0, 0, rz)
    if root.animation_data:           # the importer makes the first clip active (now "sentry"): show the rest pose
        root.animation_data.action = None
        for tr in list(root.animation_data.nla_tracks):
            root.animation_data.nla_tracks.remove(tr)
    if root.type == "ARMATURE":
        for pb in root.pose.bones:
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = (1, 0, 0, 0)
            pb.location = (0, 0, 0)
            pb.scale = (1, 1, 1)
    return root, objs

# ------------------------------------------------------------------ in-game retarget preview
# Godot (scripts/core/assets.gd, _retarget) plays anim_library.glb clips on every character by keeping each bone's
# world-space rotation delta from rest: q_target = A * q_lib * B. The same thing done here in armature space
# (frame-independent): D = R_lib_pose * R_lib_rest^-1 per bone, target basis = Rrest^-1 * D_parent^-1 * D * Rrest,
# and the pelvis offset scaled by pelvis height. So the clip sheets show what the game shows.
_LIB = {}


def lib_rig():
    try:
        if "rig" in _LIB and _LIB["rig"].name in bpy.data.objects:
            return _LIB["rig"], _LIB["acts"]
    except ReferenceError:          # scene() reset the file
        _LIB.clear()
    path = os.path.join(MODELS, "anim_library.glb")
    before_a, before_o = set(bpy.data.actions), set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new_o = [o for o in bpy.data.objects if o not in before_o]
    rig = next(o for o in new_o if o.type == "ARMATURE")
    for o in new_o:
        if o is not rig and o.type == "MESH":
            bpy.data.objects.remove(o)
    rig.hide_render = True
    acts = {}
    for a in bpy.data.actions:
        if a not in before_a:
            a.use_fake_user = True
            acts[a.name.split(".")[0]] = a
    ad = rig.animation_data_create()
    for tr in list(ad.nla_tracks):
        ad.nla_tracks.remove(tr)
    _LIB.update(rig=rig, acts=acts)
    return rig, acts


def retarget_pose(sc, target, clip, phase):
    lib, acts = lib_rig()
    act = acts.get(clip)
    if act is None or target.type != "ARMATURE":
        return False
    lib.animation_data.action = act
    f0, f1 = act.frame_range
    sc.frame_set(int(round(f0 + (f1 - f0) * phase)))
    bpy.context.view_layer.update()
    D = {}
    for pb in lib.pose.bones:
        D[pb.name] = pb.matrix.to_quaternion() @ pb.bone.matrix_local.to_quaternion().inverted()
    off = lib.pose.bones["pelvis"].head - lib.data.bones["pelvis"].head_local if "pelvis" in lib.pose.bones else None
    scale = target.data.bones["pelvis"].head_local.z / max(0.1, lib.data.bones["pelvis"].head_local.z) if "pelvis" in target.data.bones else 1.0
    from mathutils import Quaternion
    def dq(b):
        while b is not None:
            if b.name in D:
                return D[b.name]
            b = b.parent
        return Quaternion()
    for pb in target.pose.bones:
        b = pb.bone
        rr = b.matrix_local.to_quaternion()
        d = dq(b)
        dp = dq(b.parent)
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = rr.inverted() @ dp.inverted() @ d @ rr
        pb.location = (0, 0, 0)
        if b.name == "pelvis" and off is not None:
            pb.location = rr.inverted() @ (off * scale)
    lib.animation_data.action = None
    bpy.context.view_layer.update()
    return True


def clip_sheet(name, clip, out):
    """Four phases of a library clip, side view (top row) and from behind at 150 deg (bottom row), as the game plays it."""
    sc = scene()
    sc.render.resolution_x, sc.render.resolution_y = 1800, 975
    lib_rig()
    i = 0
    for row, rz in enumerate((math.radians(90), math.radians(150))):
        for q in range(4):
            root, objs = load(name, q * 0.8, rz)
            root.location.z = -row * 2.0
            if not retarget_pose(sc, root, clip, q / 4):
                return None
    cam(sc, (1.2, -11.0, -0.1), (1.2, 0, -0.1), lens=50)
    sc.render.filepath = os.path.join(out, "%s_clip_%s.png" % (name, clip))
    bpy.ops.render.render(write_still=True)
    print("[render]", sc.render.filepath)
    return sc.render.filepath


def clip_audit(name, clips, phases=4, min_verts=12):
    """Skin-through-cloth check under the game's retargeted clips. A body vertex counts as covered if a ray along its
    normal hits a garment in the rest pose; in each clip phase, covered vertices whose ray hits nothing are poking out.
    Only vertices with the cloth right behind them count (the body went through it, not out from under a hem).
    Prints and returns {clip: [(phase, count, {bone: n})]} for phases with at least min_verts exposed."""
    from mathutils.bvhtree import BVHTree
    sc = scene()
    root, objs = load(name, 0.0, 0.0)
    body = next(o for o in objs if o.type == "MESH" and o.name.split(".")[0] == "Human" and len(o.data.vertices) > 5000)
    cloth = [o for o in objs if o.type == "MESH" and not o.name.startswith("Human") and "eye" not in o.name.lower()
             and not any(k in o.name for k in ("musket", "stock", "barrel", "ramrod", "sling", "scabbard", "hilt", "grip", "pike", "cane"))]
    gname = {g.index: g.name for g in body.vertex_groups}
    dom = []
    for v in body.data.vertices:
        dom.append(max(((g.weight, gname[g.group]) for g in v.groups), default=(0, "?"))[1])
    def evaluate():
        dg = bpy.context.evaluated_depsgraph_get()
        eb = body.evaluated_get(dg)
        bm_ = eb.to_mesh()
        mw = body.matrix_world
        pts = [(mw @ v.co, (mw.to_3x3() @ v.normal).normalized()) for v in bm_.vertices]
        eb.to_mesh_clear()
        verts, tris = [], []
        for o in cloth:
            eo = o.evaluated_get(dg)
            m = eo.to_mesh()
            m.calc_loop_triangles()
            off = len(verts)
            verts += [o.matrix_world @ v.co for v in m.vertices]
            tris += [tuple(off + i for i in t.vertices) for t in m.loop_triangles]
            eo.to_mesh_clear()
        return pts, BVHTree.FromPolygons(verts, tris)
    def hits(pts, bvh, idx=None):
        out = set()
        rng_ = range(len(pts)) if idx is None else idx
        for i in rng_:
            p, n = pts[i]
            if bvh.ray_cast(p + n * 0.0015, n, 0.35)[0] is not None:
                out.add(i)
        return out
    bpy.context.view_layer.update()
    pts, bvh = evaluate()
    covered = hits(pts, bvh)
    covered = {i for i in covered if not dom[i].startswith(("hand", "index", "middle", "ring", "pinky", "thumb", "head"))}
    res = {}
    for clip in clips:
        rows = []
        for q in range(phases):
            if not retarget_pose(sc, root, clip, q / phases):
                break
            pts, bvh = evaluate()
            ok = hits(pts, bvh, covered)
            # exposed AND the cloth sits just behind the skin (within 4 cm inward): the body passed through it. A leg
            # that simply swung out from under a hem has no cloth right behind it and is not counted.
            bad = set()
            for i in covered - ok:
                p_, n_ = pts[i]
                if bvh.ray_cast(p_ - n_ * 0.0015, -n_, 0.04)[0] is not None:
                    bad.add(i)
            if len(bad) >= min_verts:
                by = {}
                for i in bad:
                    by[dom[i]] = by.get(dom[i], 0) + 1
                top = dict(sorted(by.items(), key=lambda kv: -kv[1])[:4])
                rows.append((q, len(bad), top))
        res[clip] = rows
        print("[audit] %s %-14s %s" % (name, clip, "; ".join("ph%d:%d %s" % (q, c, top) for q, c, top in rows) or "clean"))
    return res


def rear_sheet(name, out):
    """Back and three-quarter-back views (135, 180, 225 deg) of the upper body under a low raking key light, so any
    anatomy printing through the cloth (shoulder blades, spine groove, deltoids) shows. REAR=1."""
    sc = scene()
    for o in list(sc.collection.objects):
        if o.type == "LIGHT" and o.name in ("key", "fill"):
            o.data.energy *= 0.35
    l = bpy.data.lights.new("rake", "SUN"); l.energy = 4.0; l.angle = 0.05; l.color = (1.0, 0.95, 0.88)
    lo = bpy.data.objects.new("rake", l); sc.collection.objects.link(lo)
    lo.rotation_euler = (math.radians(80), 0, math.radians(120))      # 10 deg above the horizon, from the side-back
    sc.render.resolution_x, sc.render.resolution_y = 2100, 1000
    for i, rz in enumerate((math.radians(135), math.radians(180), math.radians(225))):
        load(name, i * 0.7, rz)
    cam(sc, (0.7, -3.3, 1.35), (0.7, 0, 1.3), lens=55)
    sc.render.filepath = os.path.join(out, name + "_rear.png")
    bpy.ops.render.render(write_still=True)
    print("[render]", sc.render.filepath)


CLIPS = [c for c in os.environ.get("CLIPS", "").split(",") if c]


def eye_sheet(name, out):
    """Tight close-up of both eyes, front and three-quarter (EYES=1): checks the lids cover the iris edge."""
    sc = scene()
    sc.render.resolution_x, sc.render.resolution_y = 1600, 600
    root, objs = load(name, 0.0, 0.0)
    root2, objs2 = load(name, 0.19, math.radians(35))
    bpy.context.view_layer.update()
    eyes = [o for o in objs if o.type == "MESH" and "high-poly" in o.name]
    z, x0 = 1.6, 0.0
    if eyes:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = eyes[0].evaluated_get(dg)
        m = ev.to_mesh()
        ps = [eyes[0].matrix_world @ v.co for v in m.vertices]
        ev.to_mesh_clear()
        z = sum(p.z for p in ps) / len(ps)
        x0 = sum(p.x for p in ps) / len(ps)
    cam(sc, (x0 + 0.095, -1.25, z), (x0 + 0.095, 0, z), lens=135)
    sc.render.filepath = os.path.join(out, name + "_eyes.png")
    bpy.ops.render.render(write_still=True)
    print("[render]", sc.render.filepath)


if os.environ.get("ROW"):
    # ROW=<label> blender -b --python render_characters.py -- <outdir> a b c ...: the figures side by side, front view
    sc = scene()
    sc.render.resolution_x, sc.render.resolution_y = 2700, 900
    for i, n in enumerate(names):
        load(n, i * 0.75, 0.0)
    w = (len(names) - 1) * 0.75
    cam(sc, (w / 2, -6.2, 1.0), (w / 2, 0, 0.9), lens=50)
    sc.render.filepath = os.path.join(OUT, "row_%s.png" % os.environ["ROW"])
    bpy.ops.render.render(write_still=True)
    names = []

for name in names:
    if os.environ.get("CLIP_AUDIT"):
        # CLIPS=walk,sit_idle CLIP_AUDIT=1 blender -b --python render_characters.py -- <outdir> <name>
        import json
        r = clip_audit(name, CLIPS)
        with open(os.path.join(OUT, name + "_clipaudit.json"), "w") as fh:
            json.dump(r, fh)
        continue
    if os.environ.get("EYES"):
        eye_sheet(name, OUT)
        continue
    if os.environ.get("REAR"):
        rear_sheet(name, OUT)
        continue
    if os.environ.get("ONLY_CLIPS"):
        # CLIPS=walk_fast,run ONLY_CLIPS=1 blender -b --python render_characters.py -- <outdir> <name>
        for clip in CLIPS:
            clip_sheet(name, clip, OUT)
        continue
    sc = scene()
    sc.render.resolution_x, sc.render.resolution_y = 2400, 1300
    # character faces Godot +Z = Blender -Y after import; camera sits at -Y to see the front
    for i, rz in enumerate([0, math.radians(45), math.radians(90), math.radians(180)]):
        load(name, i * 0.9, rz)
    root, objs = load(name, 4 * 0.9, 0)
    acts = [a.name for a in bpy.data.actions]
    print("[render] actions:", acts)
    walk = [a for a in bpy.data.actions if "walk" in a.name.lower()] or [lib_walk()]
    if walk[0] and root.type == "ARMATURE":
        ad = root.animation_data_create()
        for tr in list(ad.nla_tracks):
            ad.nla_tracks.remove(tr)
        ad.action = walk[0]
        sc.frame_set(7)
    cam(sc, (1.8, -6.5, 1.1), (1.8, 0, 0.95), lens=55)
    sc.render.filepath = os.path.join(OUT, name + "_turnaround.png"); bpy.ops.render.render(write_still=True)
    print("[render]", sc.render.filepath)
    sc = scene()
    sc.render.resolution_x, sc.render.resolution_y = 1200, 1200
    load(name, 0, math.radians(25))
    cam(sc, (0.30, -0.78, 1.60), (0.0, 0, 1.55), lens=85)
    sc.render.filepath = os.path.join(OUT, name + "_face.png"); bpy.ops.render.render(write_still=True)
    print("[render]", sc.render.filepath)
    if os.environ.get("QUICK", "1") == "1":       # turnaround + face only (set QUICK=0 for the hat/detail/walk sheets)
        for clip in CLIPS:
            clip_sheet(name, clip, OUT)
        continue
    # headwear sheet: front, three-quarter, side, back, and three-quarter from above
    sc = scene()
    sc.render.resolution_x, sc.render.resolution_y = 2600, 620
    top = 0.0
    for i, rz in enumerate([0, math.radians(45), math.radians(90), math.radians(180), math.radians(-135)]):
        _, objs = load(name, i * 0.5, rz)
        bpy.context.view_layer.update()
        for o in objs:
            if o.type == "MESH" and o.name.split(".")[0] == "Human":
                top = max(top, max((o.matrix_world @ Vector(c)).z for c in o.bound_box))
    hz = (top - 0.06) if top > 0 else 1.62
    cam(sc, (1.0, -3.7, hz + 0.11), (1.0, 0, hz), lens=50)
    sc.render.filepath = os.path.join(OUT, name + "_hats.png"); bpy.ops.render.render(write_still=True)
    print("[render]", sc.render.filepath)
    # costume details: torso to knees, front and three-quarter back, close
    sc = scene()
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
    for i, rz in enumerate([0, math.radians(35), math.radians(150)]):
        load(name, i * 0.75, rz)
    cam(sc, (0.75, -3.6, 1.05), (0.75, 0, 0.95), lens=60)
    sc.render.filepath = os.path.join(OUT, name + "_detail.png"); bpy.ops.render.render(write_still=True)
    print("[render]", sc.render.filepath)
    # walk check: four evenly spaced frames of the walk cycle seen from the side and from three-quarter front
    sc = scene()
    sc.render.resolution_x, sc.render.resolution_y = 2800, 900
    i = 0
    lw = lib_walk()
    for rz in (math.radians(90), math.radians(35)):
        for q in range(4):
            before = set(bpy.data.actions)
            root, objs = load(name, i * 0.75, rz)
            new = [a for a in bpy.data.actions if a not in before and "walk" in a.name.lower()] or ([lw] if lw else [])
            if new and root.type == "ARMATURE":
                ad = root.animation_data_create()
                ad.action = None
                for tr in list(ad.nla_tracks):
                    ad.nla_tracks.remove(tr)
                tr = ad.nla_tracks.new()
                f0, f1 = new[0].frame_range
                fr = f0 + (f1 - f0) * q / 4            # four evenly spaced phases of the cycle
                tr.strips.new("w", int(round(40 - (fr - f0))), new[0])
            i += 1
    sc.frame_set(40)
    cam(sc, (2.62, -8.2, 1.0), (2.62, 0, 0.85), lens=50)
    sc.render.filepath = os.path.join(OUT, name + "_walk.png"); bpy.ops.render.render(write_still=True)
    print("[render]", sc.render.filepath)
    for clip in CLIPS:
        clip_sheet(name, clip, OUT)

