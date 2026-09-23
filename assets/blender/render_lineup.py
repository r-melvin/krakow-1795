"""Lineup of every character (front, standing) plus a grid of face close-ups.
Run: blender -b --python assets/blender/render_lineup.py -- <outdir>"""
import bpy, math, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS = os.path.join(ROOT, "assets", "models")
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = args[0] if args else os.path.join(ROOT, "docs", "screenshots")
NAMES = ["watchman", "figure_noble", "figure_artist", "figure_veteran", "figure_merchant", "figure_priest", "figure_kazimierz", "figure_townsman", "figure_townswoman"]

def scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.40, 0.44, 0.52, 1)
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 3.0; sun.angle = 0.5
    so = bpy.data.objects.new("sun", sun); sc.collection.objects.link(so); so.rotation_euler = (math.radians(55), 0, math.radians(35))
    fill = bpy.data.lights.new("fill", "SUN"); fill.energy = 1.0
    fo = bpy.data.objects.new("fill", fill); sc.collection.objects.link(fo); fo.rotation_euler = (math.radians(60), 0, math.radians(-120))
    return sc

def cam(sc, loc, target, lens=50):
    c = bpy.data.cameras.new("c"); c.lens = lens
    co = bpy.data.objects.new("cam", c); sc.collection.objects.link(co); sc.camera = co
    co.location = loc
    d = (target[0]-loc[0], target[1]-loc[1], target[2]-loc[2])
    co.rotation_euler = (math.atan2(math.hypot(d[0], d[1]), -d[2]), 0, math.atan2(d[1], d[0]) - math.pi/2)

def load(name, x=0.0, y=0.0, rz=0.0):
    bpy.ops.import_scene.gltf(filepath=os.path.join(MODELS, name + ".glb"))
    root = [o for o in bpy.context.selected_objects if o.parent is None][0]
    root.rotation_mode = "XYZ"; root.location = (x, y, 0); root.rotation_euler = (0, 0, rz)

sc = scene(); sc.render.resolution_x, sc.render.resolution_y = 2700, 1200
for i, n in enumerate(NAMES):
    load(n, i * 0.85, 0, math.radians(10))
cx = (len(NAMES) - 1) * 0.85 / 2
cam(sc, (cx, -9.0, 1.05), (cx, 0, 0.95), lens=60)
sc.render.filepath = os.path.join(OUT, "lineup.png"); bpy.ops.render.render(write_still=True); print("[lineup]", sc.render.filepath)

sc = scene(); sc.render.resolution_x, sc.render.resolution_y = 2700, 900
for i, n in enumerate(NAMES):
    load(n, i * 0.42, 0, math.radians(15))
cx = (len(NAMES) - 1) * 0.42 / 2
cam(sc, (cx, -2.6, 1.64), (cx, 0, 1.60), lens=85)
sc.render.filepath = os.path.join(OUT, "lineup_faces.png"); bpy.ops.render.render(write_still=True); print("[lineup]", sc.render.filepath)
