import os
"""Contact sheets of the exported glTF assets, rendered with EEVEE under a low winter sun and a sky-blue world.

Run:  blender -b --python assets/blender/render_sheets.py -- <outdir> [group,group,...]
Groups: tenements, landmarks, props, districts, farm, houses2, industry, faith, water, castle, stmarys,
        figures (figures only when named).
"""
import bpy, math, os, sys
ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "assets", "models")
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = args[0] if args else os.path.join(os.path.dirname(ROOT), "..", "docs", "screenshots")
WANT = args[1].split(",") if len(args) > 1 else ["tenements", "landmarks", "props", "districts", "farm", "houses2", "houses3", "faith2",
                                                 "industry", "faith", "water", "castle", "stmarys", "walls", "finale", "yard"]
groups = {
    "tenements": (["tenement_a", "tenement_b", "tenement_c", "tenement_d", "tenement_e"], 14.0, 9.0),
    "landmarks": (["st_adalbert", "town_hall", "sukiennice", "st_marys"], 40.0, 18.0),
    "props": (["market_stall", "barrel", "crate_stack", "cart", "well", "lantern_post", "ground_cobbles"], 5.0, 1.6),
    "districts": (["kaz_house_a", "kaz_house_b", "kaz_synagogue", "garb_workshop", "garb_house", "dock_granary",
                   "dock_wharf", "salt_barge", "klep_house", "klep_stable", "kan_house", "wawel_wall", "wawel_gate"], 17.0, 7.0),
    "farm": (["farm_field", "farm_fence", "farm_cottage", "farm_barn", "farm_haystack", "farm_haystack_small",
              "farm_mill", "farm_shrine", "farm_manor"], 15.0, 4.0),
    "houses2": (["ten_renaissance", "ten_gothic", "ten_baroque", "ten_burgher", "ten_timber"], 14.0, 9.0),
    "houses3": (["ten_renaissance_b", "ten_gothic_b", "ten_burgher_b", "ten_wooden"], 14.0, 9.0),
    "industry": (["windmill", "watermill", "bell_foundry", "forge", "brewery", "cooper_yard", "tannery_frame"], 14.0, 8.0),
    "faith": (["campanile", "synagogue_wooden", "uniate_church", "prayer_house"], 14.0, 10.0),
    "faith2": (["kaz_synagogue", "shrine_column", "monastery_gate", "monastery_wall", "farm_shrine"], 10.0, 6.0),
    "water": (["fountain", "well", "water_pump", "horse_trough", "gutter_channel", "pillory", "stocks", "whipping_post",
               "gallows"], 5.0, 2.0),
    "castle": (["castle_gate", "wawel_far"], 40.0, 20.0),
    "walls": (["city_tower", "florian_gate", "barbican", "collegium_maius", "sien_passage"], 20.0, 12.0),
    "finale": (["kingpin_house", "kingpin_warehouse", "bathhouse", "carpenter_yard", "guillotine", "guillotine_parts"], 16.0, 10.0),
    "yard": (["yard_shed", "yard_stair", "ladder", "low_wall", "water_butt", "perch_ledge", "torch_wall", "torch",
              "broken_stall", "broken_shutter", "charred_patch", "gutter_channel", "gutter_corner", "gutter_slab", "gutter_outfall",
              "snow_drift"], 4.0, 2.0),
    "stmarys": (["st_marys"], 40.0, 30.0),
    "figures": (["watchman", "figure_noble", "figure_artist", "figure_veteran", "figure_merchant", "figure_priest",
                 "figure_kazimierz", "figure_townsman", "figure_townswoman"], 1.3, 1.0),
}
for gname, (names, spacing, h) in groups.items():
    if gname not in WANT:
        continue
    names = [n for n in names if os.path.exists(os.path.join(ROOT, n + ".glb"))]
    if not names:
        continue
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
    sc.render.resolution_x, sc.render.resolution_y = 2400, 1200
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.eevee.taa_render_samples = 32
    try:
        sc.eevee.use_shadows = True
        sc.eevee.use_raytracing = True
    except AttributeError:
        pass
    sc.world = bpy.data.worlds.new("w")
    bg = sc.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.42, 0.52, 0.68, 1)
    bg.inputs[1].default_value = 0.9
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 4.0
    sun.angle = math.radians(2.0)
    sun.color = (1.0, 0.93, 0.84)
    so = bpy.data.objects.new("sun", sun)
    sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(55), 0, math.radians(-35))
    # a snowy ground plane so the buildings sit on something
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, -0.01))
    gp = bpy.context.object
    gm = bpy.data.materials.new("ground")
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.62, 0.64, 0.68, 1)
    gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
    gp.data.materials.append(gm)
    # pack assets left to right by their real widths, two rows when there are many
    import mathutils
    roots = []
    for n in names:
        bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, n + ".glb"))
        objs = list(bpy.context.selected_objects)
        root = [o for o in objs if o.parent is None][0]
        for o in objs:
            if "-col" in o.name:
                o.hide_render = True
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ mathutils.Vector(c) for o in objs if o.type == "MESH" and "-col" not in o.name for c in o.bound_box]
        roots.append((root, min(p.x for p in pts), max(p.x for p in pts), max(p.z for p in pts), min(p.y for p in pts), max(p.y for p in pts)))
    gap = max(1.0, spacing * 0.12)
    total = sum(r[2] - r[1] + gap for r in roots)
    rows = 2 if len(roots) > 6 else 1
    row_w = total / rows
    cur, row, rowdepth, placed = 0.0, 0, 0.0, []
    yoff = 0.0
    for (root, x0, x1, top, y0, y1) in roots:
        if rows > 1 and cur > row_w * 1.02 and row == 0:
            row, cur = 1, 0.0
            yoff = max(pp[4] for pp in placed) + 4.0
        root.location.x = cur - x0
        root.location.y = yoff - y0 if row else -y1
        placed.append((cur, cur + x1 - x0, top, row, root.location.y + y1))
        cur += x1 - x0 + gap
    span = max(pp[1] for pp in placed)
    h = max(pp[2] for pp in placed) * 0.45
    cx = span / 2
    depth = max(pp[4] for pp in placed)
    gp.scale = (span * 3, span * 3, 1)
    gp.location.x = cx
    cam = bpy.data.cameras.new("c")
    cam.type = "ORTHO"
    cam.ortho_scale = span * 1.06
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    cy = depth * 0.35
    co.location = (cx - span * 0.2, cy - span * 0.9, h + span * 0.42)
    d = (cx - co.location.x, cy - co.location.y, h - co.location.z)
    co.rotation_euler = (math.atan2(math.hypot(d[0], d[1]), -d[2]), 0, math.atan2(d[1], d[0]) - math.pi / 2)
    sc.render.filepath = os.path.join(OUT, "sheet_%s.png" % gname)
    bpy.ops.render.render(write_still=True)
    print("[sheet]", sc.render.filepath)
