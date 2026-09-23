import bpy, math, os, sys
ROOT = "/home/richard/Projects/games/prototypes/krakow-1795/assets/models"
OUT = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.path.join(os.path.dirname(ROOT), "..", "docs", "screenshots")
groups = {
  "tenements": (["tenement_a","tenement_b","tenement_c","tenement_d","tenement_e"], 14.0, 9.0),
  "landmarks": (["st_adalbert","town_hall","sukiennice","st_marys"], 40.0, 18.0),
  "props": (["market_stall","barrel","crate_stack","cart","well","lantern_post"], 4.5, 1.6),
  "figures": (["watchman","figure_noble","figure_artist","figure_veteran","figure_merchant","figure_priest","figure_kazimierz","figure_townsman","figure_townswoman"], 1.3, 1.0),
}
for gname, (names, spacing, h) in groups.items():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 2400, 1200
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.45, 0.55, 0.7, 1)
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    sun = bpy.data.lights.new("sun", "SUN"); sun.energy = 3.0; sun.angle = 0.3
    so = bpy.data.objects.new("sun", sun); sc.collection.objects.link(so); so.rotation_euler = (math.radians(50), 0, math.radians(-35))
    for i, n in enumerate(names):
        bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, n + ".glb"))
        objs = list(bpy.context.selected_objects)
        root = [o for o in objs if o.parent is None][0]
        for o in objs:
            if "-col" in o.name:
                o.hide_render = True
        root.location.x = i * spacing
    span = len(names) * spacing
    cx = span / 2 - spacing / 2
    cam = bpy.data.cameras.new("c"); cam.type = "ORTHO"; cam.ortho_scale = span * 1.02
    co = bpy.data.objects.new("cam", cam); sc.collection.objects.link(co); sc.camera = co
    co.location = (cx - span * 0.25, -span * 0.9, h + span * 0.30)
    d = (cx - co.location.x, 0 - co.location.y, h - co.location.z)
    co.rotation_euler = (math.atan2(math.hypot(d[0], d[1]), -d[2]), 0, math.atan2(d[1], d[0]) - math.pi / 2)
    sc.render.filepath = os.path.join(OUT, "sheet_%s.png" % gname)
    bpy.ops.render.render(write_still=True)
    print("[sheet]", sc.render.filepath)
