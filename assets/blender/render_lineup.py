import os
"""Lineup of every character (front, standing) plus a grid of face close-ups.
Run: blender -b --python assets/blender/render_lineup.py -- <outdir>"""
import bpy, math, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS = os.path.join(ROOT, "assets", "models")
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = args[0] if args else os.path.join(ROOT, "docs", "screenshots")
import sys as _sys
_only = [a for a in (_sys.argv[_sys.argv.index("--") + 2:] if "--" in _sys.argv else [])]
GROUPS = {
    "lineup": ["watchman", "figure_noble", "figure_artist", "figure_veteran", "figure_merchant", "figure_priest", "figure_kazimierz", "figure_townsman"],
    "lineup_women": ["figure_noble_f", "figure_artist_f", "figure_veteran_f", "figure_merchant_f", "figure_priest_f", "figure_kazimierz_f", "figure_townswoman"],
    "lineup_cast_a": ["cast_governor", "cast_officer", "cast_polizei", "cast_informer", "cast_russian_envoy", "cast_prussian_banker", "cast_agent_f", "cast_bishop"],
    "lineup_cast_b": ["cast_hostess_f", "cast_printer", "cast_jacobin", "cast_smuggler", "cast_boatman", "cast_student", "cast_burgomaster", "cast_magnate"],
    "lineup_cast_c": ["cast_hajduk", "cast_falconer", "cast_beggar", "cast_beggar_f", "cast_urchin", "cast_urchin_f", "cast_child", "cast_child_f"],
    "lineup_crowd_m": ["npc_m_%02d" % i for i in range(8)],
    "lineup_crowd_f": ["npc_f_%02d" % i for i in range(8)],
    "test": _only,
}
if _only:
    GROUPS = {"test": _only}
else:
    GROUPS.pop("test")

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
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.40, 0.44, 0.52, 1)
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

_IDLE = {}

def lib_idle():
    """The shared library's idle clip (characters no longer bake idle/walk); cached per scene rebuild."""
    key = id(bpy.context.scene)
    if key in _IDLE:
        return _IDLE[key]
    _IDLE.clear()
    path = os.path.join(MODELS, "anim_library.glb")
    if not os.path.exists(path):
        _IDLE[key] = None
        return None
    before_a, before_o = set(bpy.data.actions), set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [a for a in bpy.data.actions if a not in before_a]
    for a in new:
        a.use_fake_user = True
    for o in [o for o in bpy.data.objects if o not in before_o]:
        bpy.data.objects.remove(o)
    idle = [a for a in new if a.name.lower().split(".")[0] in ("idle", "idle_alert")]
    idle.sort(key=lambda a: a.name.lower() != "idle")
    _IDLE[key] = idle[0] if idle else None
    return _IDLE[key]

def load(name, x=0.0, y=0.0, rz=0.0, frame=0):
    bpy.ops.import_scene.gltf(filepath=os.path.join(MODELS, name + ".glb"))
    root = [o for o in bpy.context.selected_objects if o.parent is None][0]
    root.rotation_mode = "XYZ"; root.location = (x, y, 0); root.rotation_euler = (0, 0, rz)
    # the importer activates the figure's first clip ("sentry"); pose everyone with the library idle instead,
    # each at a different phase so the row does not move in lockstep
    if root.type == "ARMATURE":
        if root.animation_data is None:
            root.animation_data_create()
        for tr in list(root.animation_data.nla_tracks):
            root.animation_data.nla_tracks.remove(tr)
        idle = lib_idle()
        if idle is not None:
            root.animation_data.action = idle
            try:
                root.animation_data.action_slot = idle.slots[0]
            except (AttributeError, IndexError):
                pass
            for fc in idle.fcurves if hasattr(idle, "fcurves") else []:
                pass
            root.animation_data.action_extrapolation = "HOLD"
            # phase offset via a per-object frame shift: emulate by nudging the scene frame later; store it
            root["idle_phase"] = frame
        else:
            root.animation_data.action = None

for tag, NAMES in GROUPS.items():
    sc = scene(); sc.render.resolution_x, sc.render.resolution_y = 2700, 1200
    for i, n in enumerate(NAMES):
        load(n, i * 0.85, 0, math.radians(10))
    cx = (len(NAMES) - 1) * 0.85 / 2
    sc.frame_set(14)
    cam(sc, (cx, -9.0, 1.05), (cx, 0, 0.95), lens=44)
    sc.render.filepath = os.path.join(OUT, tag + ".png"); bpy.ops.render.render(write_still=True); print("[lineup]", sc.render.filepath)

    sc = scene(); sc.render.resolution_x, sc.render.resolution_y = 2700, 900
    for i, n in enumerate(NAMES):
        load(n, i * 0.42, 0, math.radians(15))
    cx = (len(NAMES) - 1) * 0.42 / 2
    sc.frame_set(14)
    cam(sc, (cx, -2.6, 1.60), (cx, 0, 1.55), lens=42)
    sc.render.filepath = os.path.join(OUT, tag + "_faces.png"); bpy.ops.render.render(write_still=True); print("[lineup]", sc.render.filepath)
