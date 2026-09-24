"""Side-on lineup of the animal and vehicle glbs from build_animals.py, next to a 1.75 m man for scale.

Run:  blender -b --python assets/blender/render_animals.py -- [--out /path/prefix] [--clip walk] [--frame 9]
Writes <prefix>_lineup.png (animals) and <prefix>_vehicles.png (carriage and cart with their horses in the slots).
Default prefix: docs/screenshots/animals.

Sheets: blender -b --python assets/blender/render_animals.py -- --sheet horse --clip walk --speed 1.5 --out /tmp/h
writes <out>_<model>_<clip>.png: 8 frames across the clip, side view (top row) and front view (bottom row), over a
0.25 m checker. With --speed the model is carried forward at that ground speed (m/s at playback speed 1), so a
planted hoof or paw must stay on the same checker square while it is on the ground.
"""
import bpy
import math
import os
import sys
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS = os.path.join(ROOT, "assets", "models")


def arg(flag, default):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


PREFIX = arg("--out", os.path.join(ROOT, "docs", "screenshots", "animals"))
CLIP = arg("--clip", "idle")
FRAME = int(arg("--frame", "9"))


def load(name, loc, yaw=0.0):
    """Imports assets/models/<name>.glb under an empty at `loc`, returns (root empty, imported objects)."""
    path = os.path.join(MODELS, name + ".glb")
    if not os.path.exists(path):
        print("[render] missing", name)
        return None, []
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in list(new):      # the glTF importer adds an icosphere as the bone display shape
        if o.type == "MESH" and o.name.startswith("Icosphere"):
            new.remove(o)
            bpy.data.objects.remove(o)
    root = bpy.data.objects.new(name + "_root", None)
    bpy.context.scene.collection.objects.link(root)
    for o in new:
        if "-colonly" in o.name:
            o.hide_render = True
        if o.parent is None:
            o.parent = root
    root.location = loc
    root.rotation_euler.z = yaw
    for o in new:
        if o.type == "ARMATURE" and o.animation_data:
            act = bpy.data.actions.get(CLIP) or bpy.data.actions.get(name + "|" + CLIP)
            cands = [a for a in bpy.data.actions if a.name.split("|")[-1] == CLIP and a.name not in used]
            if cands:
                act = cands[0]
            if act:
                used.add(act.name)
                o.animation_data.action = act
                if getattr(act, "slots", None) and hasattr(o.animation_data, "action_slot"):
                    o.animation_data.action_slot = act.slots[0]
    return root, new


used = set()


def bbox(objs):
    pts = []
    bpy.context.view_layer.update()
    for o in objs:
        if o.type == "MESH" and not o.hide_render:
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    if not pts:
        return Vector(), Vector()
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def stage(width, height, centre_x, out, cam_y=-30.0, ortho=None):
    sc = bpy.context.scene
    sc.frame_set(FRAME)
    ground = bpy.data.meshes.new("ground")
    ground.from_pydata([(-100, -100, 0), (100, -100, 0), (100, 100, 0), (-100, 100, 0)], [], [(0, 1, 2, 3)])
    g = bpy.data.objects.new("ground", ground)
    gm = bpy.data.materials.new("ground")
    gm.diffuse_color = (0.35, 0.35, 0.37, 1)
    if gm.node_tree is None:
        gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.32, 0.32, 0.34, 1)
    ground.materials.append(gm)
    sc.collection.objects.link(g)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = ortho or width * 1.05
    cam.location = (centre_x, cam_y, (height + 0.8) / 2 - 0.4)
    cam.rotation_euler = (math.radians(90), 0, 0)
    sc.camera = cam
    for rot, e in (((0.9, 0.1, -0.6), 3.5), ((1.2, 0.0, 2.2), 1.2)):
        L = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
        L.data.energy = e
        L.rotation_euler = rot
        sc.collection.objects.link(L)
    w = bpy.data.worlds.new("w")
    sc.world = w
    if w.node_tree is None:
        w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.58, 0.64, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    sc.render.engine = "CYCLES"          # Eevee crashes the NVIDIA EGL driver headless on some of these meshes
    sc.cycles.device = "CPU"
    sc.cycles.samples = 24
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 2400
    sc.render.resolution_y = max(400, int(2400 * (height + 0.8) / (width * 1.05)))
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("[render] wrote", out)


def man(x):
    """1.75 m reference: a figure glb if one was built, else a grey post."""
    for n in ("npc_m_00", "figure_townsman"):
        r, objs = load(n, (x, 0, 0), yaw=math.pi / 2)
        if r:
            return objs
    bpy.ops.mesh.primitive_cylinder_add(radius=0.2, depth=1.75, location=(x, 0, 0.875))
    return [bpy.context.object]


def lineup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    x = 0.0
    man(x)
    x += 0.8
    names = ["horse", "horse_harnessed", "dog_hound", "dog_spitz", "cat", "pigeon", "crow", "hawk"]
    for n in names:
        # side view: turn the -Y front to face -X (left of the frame)
        r, objs = load(n, (0, 0, 0), yaw=-math.pi / 2)
        if not r:
            continue
        mn, mx = bbox(objs)
        r.location.x = x - mn.x + 0.15
        bpy.context.view_layer.update()
        mn, mx = bbox(objs)
        print("[render] %-16s length %.2f height %.2f width %.2f" % (n, mx.x - mn.x, mx.z - mn.z, mx.y - mn.y))
        x = mx.x + 0.25
    stage(x, 2.4, x / 2, PREFIX + "_lineup.png")


def vehicles():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    x = 0.0
    man(x)
    x += 1.0
    for veh, lead in (("carriage", 5.2), ("horse_cart", 4.6), ("coach", 3.4)):
        # front (-Y) turned to -X; the horses stand up to `lead` metres ahead of the vehicle origin
        # the coach is built pole-first towards +X (dressing.gd places it that way): turn it like the others
        r, objs = load(veh, (x + lead, 0, 0), yaw=(math.pi if veh == "coach" else -math.pi / 2))
        if not r:
            continue
        bpy.context.view_layer.update()
        allobjs = list(objs)
        for s in [o for o in objs if o.name.startswith("horse_slot")]:
            hr, hobjs = load("horse_harnessed", s.matrix_world.to_translation(), yaw=-math.pi / 2)
            allobjs += hobjs
        mn, mx = bbox(allobjs)
        print("[render] %-16s length %.2f height %.2f (with horses)" % (veh, mx.x - mn.x, mx.z - mn.z))
        x = mx.x + 1.0
    stage(x, 3.2, x / 2, PREFIX + "_vehicles.png")


def sheet(model, clip, speed, n=8):
    import numpy as np
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = 30
    r, objs = load(model, (0, 0, 0))
    rig = next((o for o in objs if o.type == "ARMATURE"), None)
    act = None
    if rig and rig.animation_data:
        for t in rig.animation_data.nla_tracks:
            t.mute = True
        act = next((a for a in bpy.data.actions if a.name.split("|")[-1] == clip), None)
        if act:
            rig.animation_data.action = act
            if getattr(act, "slots", None):
                rig.animation_data.action_slot = act.slots[0]
    f0, f1 = (act.frame_range if act else (1, 2))
    mn, mx = bbox(objs)
    size = max(mx.x - mn.x, mx.y - mn.y, mx.z - mn.z)
    # checker ground
    g = bpy.data.meshes.new("ground")
    g.from_pydata([(-60, -60, 0), (60, -60, 0), (60, 60, 0), (-60, 60, 0)], [], [(0, 1, 2, 3)])
    go = bpy.data.objects.new("ground", g)
    sc.collection.objects.link(go)
    gm = bpy.data.materials.new("checker")
    if gm.node_tree is None:
        gm.use_nodes = True
    nt = gm.node_tree
    ck = nt.nodes.new("ShaderNodeTexChecker")
    ck.inputs["Scale"].default_value = 480.0          # 120 m / 480 = 0.25 m squares
    ck.inputs["Color1"].default_value = (0.42, 0.42, 0.44, 1)
    ck.inputs["Color2"].default_value = (0.30, 0.30, 0.32, 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["UV"], ck.inputs["Vector"])
    g.uv_layers.new()
    nt.links.new(ck.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    g.materials.append(gm)
    L = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    L.data.energy = 3.5
    L.rotation_euler = (0.7, 0.15, 0.9)
    sc.collection.objects.link(L)
    w = bpy.data.worlds.new("w")
    sc.world = w
    if w.node_tree is None:
        w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.62, 0.68, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = size * 1.02
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 12
    sc.cycles.use_denoising = True
    sc.render.resolution_x = sc.render.resolution_y = 480
    tmp = PREFIX + "_tmp.png"
    rows = []
    for view in ("side", "front"):
        tiles = []
        for i in range(n):
            f = f0 + (f1 - f0) * i / n
            sc.frame_set(int(f), subframe=f - int(f))
            dy = -speed * (f - f0) / 30.0          # model front is -Y: travel that way
            r.location = (0, dy, 0)
            c = Vector((0, dy + (mn.y + mx.y) / 2, size * 0.42))
            tilt = math.radians(12)          # a little from above, so the checker shows under the feet
            if view == "side":
                cam.location = c + Vector((size * 3 * math.cos(tilt), 0, size * 3 * math.sin(tilt)))
                cam.rotation_euler = (math.radians(90) - tilt, 0, math.radians(90))
            else:
                cam.location = c + Vector((0, -size * 3 * math.cos(tilt), size * 3 * math.sin(tilt)))
                cam.rotation_euler = (math.radians(90) - tilt, 0, 0)
            sc.render.filepath = tmp
            bpy.ops.render.render(write_still=True)
            im = bpy.data.images.load(tmp)
            a = np.array(im.pixels[:], np.float32).reshape(im.size[1], im.size[0], 4)
            bpy.data.images.remove(im)
            tiles.append(a)
        rows.append(np.concatenate(tiles, axis=1))
    full = np.concatenate(rows[::-1], axis=0)      # pixels are bottom-up: side row on top
    out = bpy.data.images.new("sheet", full.shape[1], full.shape[0])
    out.pixels.foreach_set(full.ravel())
    path = "%s_%s_%s.png" % (PREFIX, model, clip)
    out.filepath_raw = path
    out.file_format = "PNG"
    out.save()
    os.remove(tmp)
    print("[render] sheet", path, "frames %d-%d" % (f0, f1))


if __name__ == "__main__":
    os.makedirs(os.path.dirname(PREFIX), exist_ok=True)
    if "--sheet" in sys.argv:
        for m in arg("--sheet", "horse").split(","):
            sheet(m, CLIP, float(arg("--speed", "0")))
    else:
        lineup()
        vehicles()
