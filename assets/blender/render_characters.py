"""Render check for exported characters: front / three-quarter / side / back, a walk frame, and a face close-up.
Run: blender -b --python assets/blender/render_characters.py -- <outdir> name1 name2 ..."""
import bpy, math, os, sys
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

def load(name, x=0.0, rz=0.0):
    bpy.ops.import_scene.gltf(filepath=os.path.join(MODELS, name + ".glb"))
    objs = list(bpy.context.selected_objects)
    root = [o for o in objs if o.parent is None][0]
    root.rotation_mode = "XYZ"
    root.location.x = x
    root.rotation_euler = (0, 0, rz)
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
    walk = [a for a in bpy.data.actions if "walk" in a.name.lower()]
    if walk and root.type == "ARMATURE":
        root.animation_data_create(); root.animation_data.action = walk[0]
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
