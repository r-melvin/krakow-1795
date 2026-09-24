"""Window-life props for Krakow 1795: what people tip, throw and cook with at the windows (scripts/city/window_life.gd).

Run:  blender -b --python assets/blender/build_window_props.py [-- --only bucket,cabbage]
Out:  assets/models/{bucket,chamber_pot,basin,cabbage,bottle,bone,rag,pot_on_hook,cauldron,cauldron_fire}.glb

Reuses the primitives, palette, baked materials and exporter of build_assets.py (imported with importlib, never
edited from here). Same conventions: metres, Blender Z up, front at -Y (Godot +Z), origin at the base centre.
Small props carry no collision mesh: window_life.gd gives the thrown ones a runtime RigidBody3D shape.
  bucket         oak staves, two iron hoops, rope bail, a skin of dirty water inside (poured from the sill)
  chamber_pot    glazed faience pot with a handle (the classic contents go out of the window)
  basin          pewter wash basin (a figure empties it)
  cabbage        a spent cabbage head with loose outer leaves (thrown)
  bottle         dark green wine bottle with a cork (thrown)
  bone           a soup bone (thrown to the dogs)
  rag            a crumpled rag / duster (shaken out of the window, sometimes dropped)
  pot_on_hook    an iron wall hook on a bracket with a pot hanging on it, sitting on the sill (a cooking window)
  cauldron       tall iron tripod with a cauldron hung at 1.25 m, to stand over the cafe's brazier
  cauldron_fire  low tripod over a small log fire with a cauldron (the inn yard)
"""
import importlib.util
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("build_assets", os.path.join(HERE, "build_assets.py"))
ba = importlib.util.module_from_spec(_spec)
sys.modules["build_assets"] = ba
_spec.loader.exec_module(ba)

box, cbox, cyl, sphere, torus, blob, join, export, reset, M = (ba.box, ba.cbox, ba.cyl, ba.sphere, ba.torus, ba.blob,
                                                                ba.join, ba.export, ba.reset, ba.M)

# palette additions (module state only; build_assets.py itself is untouched)
ba.PAL.update({
    "faience": (0.88, 0.86, 0.80), "faience_blue": (0.22, 0.34, 0.62), "pewter": (0.52, 0.53, 0.55),
    "cabbage": (0.36, 0.52, 0.22), "cabbage_pale": (0.66, 0.74, 0.42), "bottle_glass": (0.06, 0.16, 0.08),
    "cork": (0.62, 0.46, 0.30), "bone": (0.86, 0.81, 0.68), "rag": (0.58, 0.52, 0.44), "rope": (0.56, 0.46, 0.30),
    "dirty_water": (0.10, 0.09, 0.07), "soup": (0.30, 0.20, 0.10), "log_bark": (0.24, 0.17, 0.11),
})


def _wonk(o, amt, seed):
    import random
    r = random.Random(seed)
    return ba.edit_verts(o, lambda co: (setattr(co, "x", co.x + r.uniform(-amt, amt)), setattr(co, "y", co.y + r.uniform(-amt, amt)),
                                        setattr(co, "z", co.z + r.uniform(-amt, amt) * 0.6)))


# ------------------------------------------------------------------ props
def bucket():
    reset()
    wood, iron = M("wood"), M("iron", 0.55)
    parts = [cyl("staves", 0.125, 0.30, (0, 0, 0), wood, verts=16, r2=0.155, bevel=0.01, seg=1)]
    parts.append(cyl("water", 0.148, 0.01, (0, 0, 0.265), M("dirty_water", 0.08), verts=16, bevel=0))
    parts.append(torus("rim", 0.155, 0.012, (0, 0, 0.30), wood, seg=16, mseg=6))
    for z, r in ((0.05, 0.132), (0.23, 0.150)):
        parts.append(torus("hoop", r, 0.008, (0, 0, z), iron, seg=16, mseg=4))
    parts.append(torus("bail", 0.16, 0.007, (0, 0, 0.30), M("rope", 0.95), rot=(0, math.pi / 2, 0), seg=16, mseg=4))
    # the torus is a full ring: cut away its lower half so only the arch of the bail stays above the rim
    b = parts[-1]
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(b.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < 0.29], context="VERTS")
    bm.to_mesh(b.data)
    bm.free()
    export("bucket", join(parts, "bucket"))


def chamber_pot():
    reset()
    f = M("faience", 0.35)
    parts = [cyl("body", 0.085, 0.13, (0, 0, 0), f, verts=20, r2=0.115, bevel=0.01, seg=2)]
    parts.append(torus("lip", 0.118, 0.012, (0, 0, 0.13), f, seg=20, mseg=6))
    parts.append(torus("band", 0.104, 0.004, (0, 0, 0.09), M("faience_blue", 0.35), seg=20, mseg=4))
    parts.append(cyl("inside", 0.105, 0.005, (0, 0, 0.11), M("dirty_water", 0.1), verts=20, bevel=0))
    parts.append(torus("handle", 0.045, 0.011, (0.13, 0, 0.075), f, rot=(math.pi / 2, 0, 0), seg=14, mseg=6))
    export("chamber_pot", join(parts, "chamber_pot"))


def basin():
    reset()
    p = M("pewter", 0.4)
    parts = [cyl("bowl", 0.15, 0.09, (0, 0, 0), p, verts=24, r2=0.23, bevel=0.01, seg=1)]
    parts.append(torus("rim", 0.235, 0.012, (0, 0, 0.09), p, seg=24, mseg=6))
    parts.append(cyl("water", 0.215, 0.005, (0, 0, 0.075), M("dirty_water", 0.08), verts=24, bevel=0))
    export("basin", join(parts, "basin"))


def cabbage():
    reset()
    c, cp = M("cabbage", 0.7), M("cabbage_pale", 0.6)
    parts = [_wonk(sphere("head", 0.085, (0, 0, 0.085), cp, seg=14, rings=10), 0.008, 3)]
    import random
    r = random.Random(11)
    for k in range(7):
        a = math.tau * k / 7 + r.uniform(-0.2, 0.2)
        leaf = sphere("leaf", 0.075, (0, 0, 0), c, seg=10, rings=6, zscale=0.35)
        leaf.rotation_euler = (0.9 * math.sin(a), -0.9 * math.cos(a), 0)
        leaf.location = (0.05 * math.cos(a), 0.05 * math.sin(a), 0.07 + r.uniform(-0.02, 0.02))
        ba.bpy.ops.object.select_all(action="DESELECT")
        leaf.select_set(True)
        ba.bpy.context.view_layer.objects.active = leaf
        ba.bpy.ops.object.transform_apply(location=True, rotation=True, scale=False)
        parts.append(leaf)
    parts.append(cyl("stalk", 0.02, 0.03, (0, 0, -0.005), M("cabbage_pale", 0.8), verts=8, bevel=0))
    export("cabbage", join(parts, "cabbage"))


def bottle():
    reset()
    g = M("bottle_glass", 0.12)
    parts = [cyl("body", 0.042, 0.17, (0, 0, 0), g, verts=16, bevel=0.006, seg=2)]
    parts.append(cyl("shoulder", 0.042, 0.05, (0, 0, 0.17), g, verts=16, r2=0.015, bevel=0))
    parts.append(cyl("neck", 0.015, 0.075, (0, 0, 0.215), g, verts=12, bevel=0))
    parts.append(torus("lip", 0.016, 0.004, (0, 0, 0.288), g, seg=12, mseg=4))
    parts.append(cyl("cork", 0.012, 0.02, (0, 0, 0.285), M("cork", 0.9), verts=10, bevel=0))
    export("bottle", join(parts, "bottle"))


def bone():
    reset()
    b = M("bone", 0.7)
    parts = [cyl("shaft", 0.018, 0.20, (0, 0, 0.025), b, verts=10, rot=(0, math.pi / 2, 0), center=True, bevel=0)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(sphere("knob", 0.022, (sx * 0.10, sy * 0.014, 0.025), b, seg=10, rings=6))
    export("bone", join(parts, "bone"))


def rag():
    reset()
    o = blob("rag", (0.34, 0.26, 0.04), (0, 0, 0), M("rag", 0.95), subsurf=2)
    _wonk(o, 0.02, 7)
    export("rag", o)


def _pot(parts, x, y, z, r, h, handle_to=None):
    iron = M("iron", 0.55)
    parts.append(cyl("pot", r * 0.8, h, (x, y, z), iron, verts=16, r2=r, bevel=0.01, seg=1))
    parts.append(torus("pot_lip", r, 0.01, (x, y, z + h), iron, seg=16, mseg=4))
    parts.append(cyl("broth", r * 0.95, 0.01, (x, y, z + h - 0.03), M("soup", 0.15), verts=16, bevel=0))
    for sx in (-1, 1):
        parts.append(torus("lug", 0.02, 0.006, (x + sx * r, y, z + h - 0.02), iron, rot=(math.pi / 2, 0, 0), seg=8, mseg=4))
    if handle_to is not None:          # the bail: two straight wires from the lugs up to the hook
        hx, hy, hz = handle_to
        for sx in (-1, 1):
            a = (x + sx * r, y, z + h - 0.02)
            dx, dy, dz = hx - a[0], hy - a[1], hz - a[2]
            L = math.sqrt(dx * dx + dy * dy + dz * dz)
            mid = (a[0] + dx / 2, a[1] + dy / 2, a[2] + dz / 2)
            w = cbox("bail", (0.008, 0.008, L), mid, iron, rot=(math.atan2(-dy, math.hypot(dx, dz)), math.atan2(dx, dz), 0))
            parts.append(w)


def pot_on_hook():
    """Origin on the sill at the wall plane (Godot: window_life puts it on the sill). A bracket juts from the jamb
    at 0.55 m, its hook holds the pot's bail, the pot rests on the sill just outside the glass."""
    reset()
    iron = M("iron", 0.55)
    parts = [cbox("plate", (0.06, 0.02, 0.16), (-0.30, 0.0, 0.55), iron)]
    parts.append(cbox("arm", (0.34, 0.025, 0.025), (-0.15, -0.04, 0.60), iron))
    parts.append(cbox("brace", (0.025, 0.02, 0.28), (-0.22, -0.03, 0.47), iron, rot=(0, math.radians(-40), 0)))
    parts.append(torus("hook", 0.03, 0.006, (0.0, -0.08, 0.56), iron, rot=(math.pi / 2, 0, 0), seg=10, mseg=4))
    parts.append(cbox("hanger", (0.008, 0.008, 0.05), (0.0, -0.06, 0.60), iron))
    _pot(parts, 0.0, -0.08, 0.0, 0.11, 0.13, handle_to=(0.0, -0.08, 0.53))
    export("pot_on_hook", join(parts, "pot_on_hook"))


def _tripod(parts, h, spread):
    iron = M("iron", 0.55)
    for k in range(3):
        a = math.tau * k / 3 + math.pi / 2
        fx, fy = spread * math.cos(a), spread * math.sin(a)
        L = math.sqrt(spread * spread + h * h)
        tilt = math.atan2(spread, h)
        o = cbox("tri_leg", (0.03, 0.03, L), (fx / 2, fy / 2, h / 2), iron, rot=(tilt * math.sin(a), -tilt * math.cos(a), 0))
        parts.append(o)
    parts.append(sphere("apex", 0.04, (0, 0, h), iron, seg=8, rings=6))


def _chain(parts, z0, z1):
    iron = M("iron", 0.55)
    n = max(2, int((z0 - z1) / 0.06))
    for k in range(n):
        z = z0 - (z0 - z1) * (k + 0.5) / n
        parts.append(torus("link", 0.018, 0.005, (0, 0, z), iron, rot=(math.pi / 2, 0, (k % 2) * math.pi / 2), seg=8, mseg=4))


def cauldron():
    """Tall tripod (2 m) for the cafe brazier: the brazier's fire basket (rim 1.09 m) fits between the legs,
    the cauldron hangs in the flames above the coals."""
    reset()
    parts = []
    _tripod(parts, 2.0, 1.05)                  # legs clear the fire basket's rim (r 0.44 at 1.09 m)
    _chain(parts, 1.98, 1.68)
    _pot(parts, 0, 0, 1.32, 0.2, 0.24, handle_to=(0, 0, 1.68))
    export("cauldron", join(parts, "cauldron"))


def cauldron_fire():
    """Low tripod over a log fire, cauldron at 0.3 m: soup for the coachmen in the inn yard."""
    reset()
    parts = []
    _tripod(parts, 1.15, 0.55)
    _chain(parts, 1.13, 0.72)
    _pot(parts, 0, 0, 0.30, 0.22, 0.26, handle_to=(0, 0, 0.72))
    import random
    r = random.Random(5)
    for k in range(5):
        a = math.tau * k / 5 + r.uniform(-0.3, 0.3)
        parts.append(cyl("log", 0.04, 0.5, (0.12 * math.cos(a), 0.12 * math.sin(a), 0.06), M("log_bark", 0.95), verts=8,
                         rot=(math.radians(70) * math.sin(a), -math.radians(70) * math.cos(a), 0), center=True, bevel=0))
    parts.append(blob("coals", (0.40, 0.40, 0.10), (0, 0, 0.0), M("ember", 0.9, emit=(1.0, 0.32, 0.06), emit_strength=5.0)))
    parts.append(cyl("ash", 0.55, 0.01, (0, 0, 0.0), M("soot", 0.95), verts=16, bevel=0))
    for k in range(9):
        a = math.tau * k / 9
        parts.append(_wonk(blob("ring_stone", (0.14, 0.11, 0.08), (0.46 * math.cos(a), 0.46 * math.sin(a), 0), M("stone_dark"), subsurf=1), 0.01, k))
    export("cauldron_fire", join(parts, "cauldron_fire"))


BUILDS = [("bucket", bucket), ("chamber_pot", chamber_pot), ("basin", basin), ("cabbage", cabbage), ("bottle", bottle),
          ("bone", bone), ("rag", rag), ("pot_on_hook", pot_on_hook), ("cauldron", cauldron), ("cauldron_fire", cauldron_fire)]


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only = None
    if "--only" in argv and argv.index("--only") + 1 < len(argv):
        only = argv[argv.index("--only") + 1].split(",")
    for name, fn in BUILDS:
        if only and name not in only:
            continue
        fn()
    print("[window_props] tris", " ".join("%s=%d" % kv for kv in ba.TRI_LOG.items()))
