import bpy, math, os, sys
from mathutils import Vector
ROOT = "/home/richard/Projects/games/prototypes/krakow-1795/assets/models"
OUT = "/tmp/claude-1000/-home-richard-Projects-games-prototypes/b3410009-46e2-4cf5-83a5-e84b06dd70e9/scratchpad"
# name: (camera pos, look-at) in Blender coords
VIEWS = {
    "int_tavern": ((0.3, 0.7, 1.8), (-0.6, 6.0, 1.6)),
    "int_shop": ((1.2, 0.5, 1.7), (-0.6, 5.5, 1.2)),
    "int_workshop": ((1.2, 0.5, 1.7), (-1.2, 5.0, 1.0)),
    "int_church": ((0.0, 1.0, 1.7), (0.0, 20.0, 4.0)),
    "int_salon": ((-0.8, 0.6, 1.7), (1.2, 6.0, 1.4)),
    "int_flat": ((0.6, 0.45, 1.6), (-0.5, 4.5, 0.9)),
    "int_stair": ((3.0, -2.5, 2.4), (0.0, 1.8, 1.2)),
}
want = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else list(VIEWS)
for name in want:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.eevee.taa_render_samples = 16
    sc.view_settings.view_transform = "AgX"
    sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
    bg = sc.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.16, 0.19, 0.32, 1); bg.inputs[1].default_value = 0.35 if name != "int_stair" else 2.0
    bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, name + ".glb"))
    for o in list(sc.objects):
        if "-col" in o.name:
            o.hide_render = True
        if o.name.startswith("lamp_"):
            kind = o.name.split("_")[1]
            e = {"fire": 120, "candle": 25, "lantern": 90, "chandelier": 160, "window": 30}.get(kind, 50)
            L = bpy.data.lights.new(o.name + "_L", "POINT"); L.energy = e; L.color = (1.0, 0.7, 0.4); L.shadow_soft_size = 0.2
            lo = bpy.data.objects.new(o.name + "_L", L); sc.collection.objects.link(lo); lo.location = o.matrix_world.translation
    cam = bpy.data.cameras.new("c"); cam.lens = 14
    co = bpy.data.objects.new("cam", cam); sc.collection.objects.link(co); sc.camera = co
    p, t = VIEWS[name]
    co.location = p
    d = Vector(t) - Vector(p)
    co.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, "interiors_%s.png" % name)
    bpy.ops.render.render(write_still=True)
    print("[render]", sc.render.filepath)
