"""Render check for exported characters: front / three-quarter / side / back, a walk frame, and a face close-up.
Run: blender -b --python assets/blender/render_characters.py -- <outdir> name1 name2 ..."""
import bpy, math, os, sys
from mathutils import Vector
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS = os.path.join(ROOT, "assets", "models")
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = args[0] if args else os.path.join(ROOT, "docs", "screenshots")
names = args[1:] or ["watchman"]

def scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
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

for name in names:
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

