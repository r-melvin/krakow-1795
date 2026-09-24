"""Street-trade props for Krakow 1795 (scripts/city/vendors.gd, data/vendors.json): what the hawkers of the Rynek
carry and wheel about on a winter night. Each prop <= 2k triangles.

Run:  blender -b --python assets/blender/build_vendor_props.py [-- --only vendor_chestnut_cart,vendor_grinder]
Writes assets/models/vendor_*.glb. Reuses the helpers, palette and baked texture cache of build_assets.py (loaded
with importlib; that file is not modified).

Conventions (as build_assets.py): metres, Blender Z up, glTF maps Blender (x, y, z) -> Godot (x, z, -y).
- Props that stand beside a seller (carts, barrows, stands, the shoe-black's box): origin at the base centre, the
  customer's side at Blender -Y (Godot +Z), the seller's side (handles) at +Y. vendors.gd turns them by the seller's
  facing + PI, so the -Y side faces the customer.
- Props worn on a bone (yokes, the back-frame, the pack, the tray, the ballad bundle): origin at the attachment
  point; the wearer faces Blender +Y (Godot -Z, a Node3D's forward), so a tray reaches to +Y and a pack to -Y.
No collision meshes: vendors.gd adds a box body for the carts itself.
"""
import importlib.util
import math
import os
import random
import sys

import bmesh
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("build_assets", os.path.join(HERE, "build_assets.py"))
ba = importlib.util.module_from_spec(_spec)
sys.modules["build_assets"] = ba
_spec.loader.exec_module(ba)

box, cbox, cyl, sphere, torus, blob, join, export, M = ba.box, ba.cbox, ba.cyl, ba.sphere, ba.torus, ba.blob, ba.join, ba.export, ba.M
reset, _tube, _bm_obj, edit_verts = ba.reset, ba._tube, ba._bm_obj, ba.edit_verts
PI = math.pi

ba.PAL.update({
    "wicker": (0.56, 0.42, 0.22), "tallow": (0.93, 0.88, 0.72), "chestnut": (0.34, 0.17, 0.08), "chestnut_split": (0.80, 0.62, 0.38),
    "fish": (0.64, 0.66, 0.68), "fish_back": (0.26, 0.30, 0.33), "tin": (0.62, 0.63, 0.65), "milk": (0.95, 0.94, 0.90),
    "flint": (0.34, 0.34, 0.36), "coal_glow": (0.9, 0.25, 0.05), "flame_small": (1.0, 0.7, 0.3), "lamp_glow": (1.0, 0.8, 0.45),
    "ring_bread": (0.70, 0.46, 0.20), "poppy": (0.12, 0.11, 0.12),
})
ba.TEX_OF.update({"wicker": "thatch", "tin": "metal"})
ba.TINT.update({"wicker": (0.78, 0.62, 0.42), "tin": (0.80, 0.82, 0.86)})


def glow(key, colour, strength):
    return M(key, 0.9, emit=colour, emit_strength=strength)


def tube(name, pts, r, mat, n=6):
    """Polyline of frusta through `pts` (constant radius)."""
    bm = bmesh.new()
    for a, b in zip(pts, pts[1:]):
        _tube(bm, a, b, r, r, n)
    return _bm_obj(name, bm, mat)


WHEELS = []          # (hub, [parts]) of the cart being built: exported as separate child nodes that vendors.gd spins


def wheel(parts, x, y, zc, R, mat, spokes=4, tyre=True):
    """Cart wheel turning about X: rim torus, spokes, hub. Collected in WHEELS (origin at the hub) instead of `parts`."""
    w = [torus("rim", R, 0.028, (x, y, zc), mat, rot=(0, PI / 2, 0), seg=12, mseg=4)]
    if tyre:
        w.append(torus("tyre", R + 0.012, 0.014, (x, y, zc), M("iron", 0.5), rot=(0, PI / 2, 0), seg=12, mseg=3))
    for k in range(spokes):
        w.append(cbox("spoke", (0.025, 0.025, 2 * R), (x, y, zc), mat, rot=(PI * k / spokes, 0, 0)))
    w.append(cyl("hub", 0.05, 0.1, (x, y, zc), mat, verts=8, rot=(0, PI / 2, 0), center=True))
    WHEELS.append(((x, y, zc), w))


def grip(parts, x, y0, y1, z0, z1, mat):
    """Turned hand-grip on the end of a shaft (a thicker round the hands close on)."""
    parts.append(tube("grip", [(x, y0, z0), (x, y1, z1)], 0.03, mat, n=8))


def export_cart(name, parts):
    """Body joined into one mesh; each wheel a child object named wheel_<n> with its origin on its hub."""
    body = join(parts, name)
    wheels = []
    for k, (hub, wp) in enumerate(WHEELS):
        wo = join(wp, "wheel_%d" % k)
        bpy.ops.object.select_all(action="DESELECT")
        wo.select_set(True)
        bpy.context.view_layer.objects.active = wo
        bpy.context.scene.cursor.location = hub
        bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
        ba.auto_uv(wo)
        wheels.append(wo)
    WHEELS.clear()
    for wo in wheels:
        wo.parent = body
        wo.matrix_parent_inverse = body.matrix_world.inverted()
    total = ba.tris(body) + sum(ba.tris(w) for w in wheels)
    export(name, body)
    ba.TRI_LOG[name] = total
    print("[vendor_props] %s tris incl. wheels %d" % (name, total))


def fish(name, x, y, z, yaw, L=0.26):
    """Low-poly salted fish lying flat: a squashed 6-sided spindle and a tail fin."""
    o = sphere(name, 1.0, (0, 0, 0), M("fish", 0.35), seg=6, rings=4)
    c, s = math.cos(yaw), math.sin(yaw)

    def f(co):
        lx, ly, lz = co.x * L * 0.5, co.y * L * 0.12, co.z * L * 0.07
        if co.z > 0.3:
            lz *= 1.2
        co.x, co.y, co.z = x + lx * c - ly * s, y + lx * s + ly * c, z + lz
    edit_verts(o, f)
    bm = bmesh.new()
    tx, ty = x - c * L * 0.5, y - s * L * 0.5
    px, py = -s, c
    for dz, flip in ((0.0, False), (-0.002, True)):         # two single-sided faces back to back
        a = bm.verts.new((tx, ty, z + dz))
        b = bm.verts.new((tx - c * 0.07 + px * 0.05, ty - s * 0.07 + py * 0.05, z + 0.005 + dz))
        d = bm.verts.new((tx - c * 0.07 - px * 0.05, ty - s * 0.07 - py * 0.05, z + 0.005 + dz))
        bm.faces.new((a, d, b) if flip else (a, b, d))
    return [o, _bm_obj(name + "_tail", bm, M("fish_back", 0.5))]


def yoke_beam(parts):
    """Carved shoulder yoke across the back of the neck, ends dipping a little, a hollow for the neck."""
    pts = [(-0.70, 0.0, -0.03), (-0.42, 0.0, 0.02), (-0.18, -0.06, 0.035), (0.18, -0.06, 0.035), (0.42, 0.0, 0.02), (0.70, 0.0, -0.03)]
    parts.append(tube("yoke", pts, 0.032, M("wood"), n=6))
    for sx in (-1, 1):
        parts.append(cyl("peg", 0.02, 0.07, (sx * 0.66, 0.0, -0.08), M("wood_dark"), verts=6))


# ------------------------------------------------------------------ props that stand beside the seller
def vendor_obwarzanki():
    """Obwarzanek (ring-bread) seller's pitch: a round wicker basket heaped with ring breads on a low stool, and a
    stick threaded with more rings, the way they were carried about the town."""
    reset()
    rng = random.Random(1401)
    wd = M("wood_dark")
    parts = [cyl("seat", 0.26, 0.04, (0, 0, 0.46), M("wood"), verts=10)]
    for k in range(3):
        a = math.tau * k / 3 + 0.3
        parts.append(cbox("leg", (0.035, 0.035, 0.5), (0.17 * math.cos(a), 0.17 * math.sin(a), 0.24), wd,
                          rot=(0.12 * math.sin(a), -0.12 * math.cos(a), 0)))
    parts.append(cyl("basket", 0.24, 0.13, (0, 0, 0.50), M("wicker"), verts=12, r2=0.31))
    parts.append(torus("basket_rim", 0.31, 0.018, (0, 0, 0.63), M("wicker"), seg=12, mseg=4))
    parts.append(cyl("cloth", 0.27, 0.01, (0, 0, 0.585), M("linen"), verts=12))
    bread = M("ring_bread", 0.7)
    for k in range(11):
        a, r = rng.uniform(0, math.tau), math.sqrt(rng.random()) * 0.19
        parts.append(torus("ring", 0.068, 0.022, (r * math.cos(a), r * math.sin(a), 0.61 + rng.uniform(0, 0.05)), bread,
                           rot=(rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0), seg=8, mseg=4))
    # the stick of rings at the back of the basket (seller's side)
    parts.append(cyl("stick", 0.012, 0.75, (0.05, 0.15, 0.55), M("wood"), verts=5))
    for k in range(6):
        parts.append(torus("ring_on_stick", 0.064, 0.021, (0.05 + rng.uniform(-0.02, 0.02), 0.15, 0.80 + k * 0.047), bread,
                           rot=(rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), 0), seg=8, mseg=4))
    parts.append(sphere("salt_pot", 0.05, (-0.2, -0.12, 0.49), M("terracotta"), seg=6, rings=4))
    export("vendor_obwarzanki", join(parts, "vendor_obwarzanki"))


def vendor_chestnut_cart():
    """Chestnut roaster's barrow: an iron stove on two wheels, a perforated pan of chestnuts on glowing coals, a
    stove pipe, a stack of paper cones and a sack of nuts. Handles to the seller's side (+Y)."""
    reset()
    rng = random.Random(1402)
    w, wd, iron = M("wood"), M("wood_dark"), M("iron", 0.55)
    parts = [box("bed", (1.1, 0.56, 0.05), (0, 0, 0.5), w)]
    for sx in (-1, 1):
        wheel(parts, sx * 0.6, 0.06, 0.3, 0.28, wd)
        parts.append(cbox("leg", (0.04, 0.04, 0.5), (sx * 0.45, -0.22, 0.25), wd))
        parts.append(tube("handle", [(sx * 0.3, 0.26, 0.52), (sx * 0.3, 0.64, 0.835)], 0.022, wd))
        grip(parts, sx * 0.3, 0.62, 0.76, 0.825, 0.875, w)
    parts.append(cyl("axle", 0.025, 1.2, (0, 0.06, 0.3), wd, verts=6, rot=(0, PI / 2, 0), center=True))
    parts.append(box("stove", (0.56, 0.44, 0.36), (0, 0, 0.55), iron))
    parts.append(box("door", (0.2, 0.012, 0.09), (0, -0.226, 0.62), glow("coal_glow", (1.0, 0.32, 0.06), 5.0)))
    parts.append(cyl("pan", 0.27, 0.035, (0, 0, 0.91), iron, verts=12))
    parts.append(torus("pan_rim", 0.27, 0.012, (0, 0, 0.95), iron, seg=12, mseg=3))
    parts.append(cyl("coals", 0.25, 0.012, (0, 0, 0.945), glow("coal_glow", (1.0, 0.32, 0.06), 6.0), verts=12))
    parts.append(cyl("pan_handle", 0.015, 0.3, (0.0, -0.4, 0.95), iron, verts=5, rot=(PI / 2, 0, 0), center=True))
    for k in range(12):
        a, r = rng.uniform(0, math.tau), math.sqrt(rng.random()) * 0.21
        mat = M("chestnut", 0.45) if k % 3 else M("chestnut_split", 0.7)
        parts.append(sphere("nut", 0.028, (r * math.cos(a), r * math.sin(a), 0.965), mat, seg=6, rings=3, zscale=0.75))
    parts.append(cyl("pipe", 0.045, 0.6, (0.2, 0.14, 0.91), iron, verts=8))
    parts.append(cyl("pipe_cap", 0.08, 0.06, (0.2, 0.14, 1.51), iron, verts=8, r2=0.03))
    # paper cones on the bed at the side, a sack of raw chestnuts on the other
    paper = M("paper")
    for k in range(4):
        parts.append(cyl("cone", 0.012, 0.15, (-0.45 + (k % 2) * 0.06, -0.1 + (k // 2) * 0.1, 0.55 + 0.02 * k), paper, verts=7, r2=0.055))
    parts.append(ba._lumpy("sack", 0.13, (0.43, 0.02, 0.63), M("sacking"), zscale=0.9, amp=0.12, seed=1403, seg=8, rings=5, zmin=0.55))
    export_cart("vendor_chestnut_cart", parts)


def vendor_grinder():
    """Knife grinder's treadle barrow: one wheel in front, a sandstone grindstone on posts, a flywheel driven by a
    foot treadle, a tin drip-can over the stone. Handles to the seller's side (+Y)."""
    reset()
    wd, w, iron = M("wood_dark"), M("wood"), M("iron", 0.5)
    parts = []
    wheel(parts, 0.0, -0.5, 0.25, 0.23, wd)
    parts.append(cyl("axle", 0.02, 0.36, (0, -0.5, 0.25), iron, verts=6, rot=(0, PI / 2, 0), center=True))
    for sx in (-1, 1):
        parts.append(tube("rail", [(sx * 0.16, -0.5, 0.26), (sx * 0.2, 0.0, 0.56), (sx * 0.24, 0.45, 0.84)], 0.024, wd))
        grip(parts, sx * 0.24, 0.43, 0.56, 0.83, 0.88, w)
        parts.append(cbox("leg", (0.035, 0.035, 0.46), (sx * 0.19, 0.12, 0.23), wd))
        parts.append(cbox("post", (0.05, 0.05, 0.42), (sx * 0.09, -0.05, 0.72), w))
    parts.append(box("deck", (0.42, 0.34, 0.04), (0, -0.05, 0.5), w))
    parts.append(cyl("stone", 0.17, 0.06, (0, -0.05, 0.92), M("stone_dark"), verts=14, rot=(0, PI / 2, 0), center=True))
    parts.append(cyl("spindle", 0.012, 0.3, (0, -0.05, 0.92), iron, verts=5, rot=(0, PI / 2, 0), center=True))
    parts.append(torus("flywheel", 0.26, 0.022, (0.26, 0.12, 0.42), iron, rot=(0, PI / 2, 0), seg=12, mseg=4))
    for k in range(3):
        parts.append(cbox("fly_spoke", (0.02, 0.02, 0.5), (0.26, 0.12, 0.42), iron, rot=(PI * k / 3, 0, 0)))
    parts.append(tube("belt", [(0.26, 0.12, 0.68), (0.03, -0.05, 0.99), (0.03, -0.05, 0.85), (0.26, 0.12, 0.16)], 0.006, M("leather"), n=4))
    parts.append(box("treadle", (0.1, 0.42, 0.025), (0.24, 0.26, 0.06), w, rot=(0.12, 0, 0)))
    parts.append(tube("crank_rod", [(0.24, 0.3, 0.09), (0.26, 0.2, 0.42)], 0.008, iron, n=4))
    parts.append(cyl("drip_post", 0.012, 0.3, (0.0, 0.1, 0.9), iron, verts=5))
    parts.append(tube("drip_arm", [(0.0, 0.1, 1.2), (0.0, -0.05, 1.2)], 0.01, iron, n=4))
    parts.append(cyl("drip_can", 0.06, 0.12, (0.0, -0.05, 1.1), M("tin"), verts=8, r2=0.045))
    parts.append(box("toolbox", (0.3, 0.16, 0.1), (-0.02, 0.3, 0.64), wd, rot=(0.25, 0, 0)))
    parts.append(cbox("blade", (0.02, 0.2, 0.004), (0.0, 0.3, 0.72), M("iron", 0.3), rot=(0.25, 0, 0)))
    export_cart("vendor_grinder", parts)


def vendor_fish_barrow():
    """Fish seller's barrow up from the Vistula: a wicker basket of salted herring and a carp or two, a small keg of
    brined fish, and a horn lantern hung on a pole at the front corner. Handles to the seller's side (+Y)."""
    reset()
    rng = random.Random(1404)
    wd, w = M("wood_dark"), M("wood")
    parts = [box("bed", (0.95, 0.72, 0.05), (0, 0, 0.52), w)]
    for sx in (-1, 1):
        wheel(parts, sx * 0.53, 0.05, 0.3, 0.28, wd)
        parts.append(box("side", (0.03, 0.72, 0.12), (sx * 0.47, 0, 0.57), w))
        parts.append(cbox("leg", (0.04, 0.04, 0.52), (sx * 0.4, -0.3, 0.26), wd))
        parts.append(tube("handle", [(sx * 0.32, 0.34, 0.55), (sx * 0.32, 0.72, 0.835)], 0.022, wd))
        grip(parts, sx * 0.32, 0.70, 0.84, 0.825, 0.875, w)
    parts.append(box("front", (0.95, 0.03, 0.12), (0, -0.35, 0.57), w))
    parts.append(cyl("axle", 0.025, 1.1, (0, 0.05, 0.3), wd, verts=6, rot=(0, PI / 2, 0), center=True))
    parts.append(cyl("basket", 0.26, 0.16, (-0.12, -0.02, 0.57), M("wicker"), verts=12, r2=0.3))
    parts.append(cyl("straw", 0.28, 0.01, (-0.12, -0.02, 0.72), M("straw"), verts=12))
    for k in range(11):                  # herring laid in a fan across the basket, heads outward
        a = PI * k / 10 + rng.uniform(-0.08, 0.08)
        parts += fish("herring", -0.12 + math.cos(a) * 0.1, -0.02 - math.sin(a) * 0.08 + 0.06, 0.745 + 0.014 * (k % 3), -a, L=0.3)
    parts += fish("carp", -0.1, -0.12, 0.8, 0.15, L=0.4)
    parts += fish("carp", -0.16, 0.08, 0.79, -0.2, L=0.38)
    parts.append(cyl("keg", 0.13, 0.26, (0.3, 0.12, 0.55), w, verts=10, r2=0.11))
    parts.append(cyl("keg_hoop", 0.135, 0.02, (0.3, 0.12, 0.62), M("iron", 0.5), verts=10))
    parts.append(cyl("brine", 0.11, 0.01, (0.3, 0.12, 0.8), M("water", 0.2), verts=10))
    # lantern pole at the front corner (lantern centre at (-0.42, -0.5, 1.55): vendors.json lamp.at)
    parts.append(cyl("pole", 0.022, 1.3, (-0.42, -0.3, 0.55), wd, verts=6))
    parts.append(tube("arm", [(-0.42, -0.3, 1.82), (-0.42, -0.5, 1.8)], 0.012, M("iron", 0.5), n=4))
    parts.append(cyl("hook", 0.005, 0.1, (-0.42, -0.5, 1.7), M("iron", 0.5), verts=4))
    parts.append(box("lamp_base", (0.14, 0.14, 0.03), (-0.42, -0.5, 1.44), M("iron", 0.5)))
    parts.append(box("lamp_horn", (0.11, 0.11, 0.17), (-0.42, -0.5, 1.47), glow("lamp_glow", (1.0, 0.72, 0.38), 4.0)))
    parts.append(cyl("lamp_cap", 0.1, 0.07, (-0.42, -0.5, 1.64), M("iron", 0.5), verts=4, r2=0.02))
    export_cart("vendor_fish_barrow", parts)


def vendor_beer_can():
    """Hot-beer (grzaniec) seller's stand: a little board table, a charcoal pot glowing under a big tin can with a
    spout and a lid, three wooden cups."""
    reset()
    wd, w, iron = M("wood_dark"), M("wood"), M("iron", 0.55)
    parts = [box("top", (0.56, 0.36, 0.035), (0, 0, 0.42), w)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(cbox("leg", (0.035, 0.035, 0.42), (sx * 0.23, sy * 0.14, 0.21), wd, rot=(sy * 0.06, -sx * 0.06, 0)))
    parts.append(cyl("pot", 0.14, 0.12, (-0.08, 0, 0.455), iron, verts=10, r2=0.16))
    parts.append(cyl("coals", 0.145, 0.012, (-0.08, 0, 0.57), glow("coal_glow", (1.0, 0.34, 0.07), 5.0), verts=10))
    for k in range(3):
        a = math.tau * k / 3
        parts.append(cbox("trivet", (0.02, 0.02, 0.06), (-0.08 + 0.12 * math.cos(a), 0.12 * math.sin(a), 0.6), iron))
    tin = M("tin")
    parts.append(cyl("can", 0.12, 0.34, (-0.08, 0, 0.62), tin, verts=12, r2=0.105))
    parts.append(cyl("lid", 0.11, 0.05, (-0.08, 0, 0.96), tin, verts=12, r2=0.04))
    parts.append(sphere("knob", 0.02, (-0.08, 0, 1.02), iron, seg=6, rings=3))
    parts.append(tube("spout", [(-0.08, -0.1, 0.72), (-0.08, -0.2, 0.86), (-0.08, -0.25, 0.94)], 0.016, tin, n=6))
    parts.append(torus("handle", 0.09, 0.01, (-0.08, 0.13, 0.82), iron, rot=(0, PI / 2, 0), seg=10, mseg=3))
    for k in range(3):
        parts.append(cyl("cup", 0.035, 0.07, (0.14 + (k % 2) * 0.08, -0.08 + k * 0.08, 0.438), w, verts=8, r2=0.04))
    parts.append(box("cloth", (0.16, 0.14, 0.01), (0.16, 0.08, 0.438), M("linen")))
    export("vendor_beer_can", join(parts, "vendor_beer_can"))


def vendor_herbs():
    """Herb woman's stand: two posts and a bar hung with bunches of dried herbs (heads down), a basket of more at
    the foot."""
    reset()
    rng = random.Random(1405)
    wd = M("wood_dark")
    parts = []
    for sx in (-1, 1):
        parts.append(cyl("post", 0.028, 1.55, (sx * 0.42, 0, 0), wd, verts=6))
        parts.append(tube("foot", [(sx * 0.42, -0.18, 0.02), (sx * 0.42, 0.18, 0.02)], 0.025, wd, n=4))
    parts.append(tube("bar", [(-0.46, 0, 1.5), (0.46, 0, 1.5)], 0.022, wd, n=6))
    mats = [M("dried_flower"), M("dead_stalk"), M("rosemary"), M("dead_grass"), M("berry")]
    for k in range(9):
        x = -0.34 + k * 0.085
        h = rng.uniform(0.22, 0.34)
        parts.append(cyl("string", 0.004, 0.08, (x, 0, 1.42), M("sacking"), verts=3))
        parts.append(cyl("bunch", rng.uniform(0.045, 0.07), h, (x, rng.uniform(-0.02, 0.02), 1.42 - h), mats[k % len(mats)], verts=6, r2=0.012))
    parts.append(cyl("basket", 0.16, 0.2, (0.05, -0.18, 0), M("wicker"), verts=10, r2=0.2))
    for k in range(5):
        a = math.tau * k / 5
        parts.append(cyl("bunch_b", 0.035, 0.26, (0.05 + 0.07 * math.cos(a), -0.18 + 0.07 * math.sin(a), 0.1), mats[(k + 2) % len(mats)],
                         verts=5, r2=0.06, rot=(0.25 * math.sin(a), -0.25 * math.cos(a), 0)))
    export("vendor_herbs", join(parts, "vendor_herbs"))


def vendor_shoeblack_box():
    """Shoe-black's box: a wooden box with a foot-rest on top, brushes, a tin of blacking, a rag."""
    reset()
    wd, w = M("wood_dark"), M("wood")
    parts = [box("box", (0.34, 0.26, 0.24), (0, 0, 0), wd),
             cbox("rest_post", (0.05, 0.05, 0.08), (0, 0, 0.28), w),
             box("rest", (0.1, 0.24, 0.035), (0, 0.0, 0.32), w)]
    parts.append(box("heel", (0.1, 0.03, 0.03), (0, -0.1, 0.355), w))
    for k, x in enumerate((-0.3, -0.22)):
        parts.append(box("brush", (0.06, 0.16, 0.035), (x, -0.05 + 0.08 * k, 0), w, rot=(0, 0, 0.3 * k)))
        parts.append(box("bristle", (0.05, 0.14, 0.025), (x, -0.05 + 0.08 * k, -0.02), M("black"), rot=(0, 0, 0.3 * k)))
    parts.append(cyl("tin", 0.045, 0.04, (0.26, -0.06, 0), M("tin"), verts=10))
    parts.append(cyl("blacking", 0.04, 0.005, (0.26, -0.06, 0.04), M("black", 0.2), verts=10))
    parts.append(box("rag", (0.14, 0.1, 0.012), (0.08, 0.02, 0.24), M("sacking"), rot=(0, 0, 0.4)))
    export("vendor_shoeblack_box", join(parts, "vendor_shoeblack_box"))


# ------------------------------------------------------------------ props worn on a bone
def _buckets(parts, can=False):
    for sx in (-1, 1):
        x = sx * 0.66
        parts.append(tube("rope", [(x, 0.0, -0.1), (x - 0.1, 0.0, -0.72)], 0.007, M("sacking"), n=4))
        parts.append(tube("rope", [(x, 0.0, -0.1), (x + 0.1, 0.0, -0.72)], 0.007, M("sacking"), n=4))
        if can:
            parts.append(cyl("can", 0.12, 0.3, (x, 0, -1.08), M("tin"), verts=10))
            parts.append(cyl("can_neck", 0.12, 0.08, (x, 0, -0.78), M("tin"), verts=10, r2=0.06))
            parts.append(cyl("can_lid", 0.065, 0.03, (x, 0, -0.71), M("wood"), verts=10))
            parts.append(torus("can_hoop", 0.122, 0.008, (x, 0, -0.95), M("iron", 0.5), seg=10, mseg=3))
            parts.append(tube("bail", [(x - 0.1, 0.0, -0.72), (x - 0.06, 0.0, -0.8), (x + 0.06, 0.0, -0.8), (x + 0.1, 0.0, -0.72)], 0.006, M("iron", 0.5), n=4))
        else:
            parts.append(cyl("bucket", 0.13, 0.3, (x, 0, -1.05), M("wood"), verts=10, r2=0.155))
            for z in (-1.0, -0.82):
                parts.append(cyl("hoop", 0.15 if z > -0.9 else 0.14, 0.02, (x, 0, z), M("iron", 0.5), verts=10))
            parts.append(cyl("water", 0.145, 0.01, (x, 0, -0.79), M("water", 0.15), verts=10))
            parts.append(tube("bail", [(x - 0.1, 0.0, -0.72), (x - 0.15, 0.0, -0.78)], 0.006, M("iron", 0.5), n=4))
            parts.append(tube("bail", [(x + 0.1, 0.0, -0.72), (x + 0.15, 0.0, -0.78)], 0.006, M("iron", 0.5), n=4))


def vendor_yoke_water():
    """Water carrier's yoke across the shoulders, two wooden buckets hung on ropes, water slopping at the brim."""
    reset()
    parts = []
    yoke_beam(parts)
    _buckets(parts, can=False)
    export("vendor_yoke_water", join(parts, "vendor_yoke_water"))


def vendor_yoke_milk():
    """Milk woman's yoke with two tinned milk cans, wooden stoppers."""
    reset()
    parts = []
    yoke_beam(parts)
    _buckets(parts, can=True)
    export("vendor_yoke_milk", join(parts, "vendor_yoke_milk"))


def vendor_backframe_wood():
    """Firewood seller's back-frame (nosidła): two poles and rungs with a load of split birch roped on behind."""
    reset()
    rng = random.Random(1406)
    wd = M("wood_dark")
    parts = []
    for sx in (-1, 1):
        parts.append(tube("pole", [(sx * 0.19, 0.0, -0.62), (sx * 0.19, 0.0, 0.32), (sx * 0.17, 0.04, 0.4)], 0.02, wd))
        parts.append(tube("strap", [(sx * 0.15, 0.02, 0.28), (sx * 0.14, 0.2, 0.36), (sx * 0.15, 0.3, 0.2)], 0.012, M("leather"), n=4))
    for z in (-0.5, -0.1, 0.25):
        parts.append(tube("rung", [(-0.2, 0.0, z), (0.2, 0.0, z)], 0.015, wd, n=5))
    parts.append(box("shelf", (0.44, 0.22, 0.03), (0, -0.11, -0.6), wd))
    for k in range(13):
        row, col = k // 4, k % 4
        z = -0.54 + row * 0.1 + rng.uniform(-0.01, 0.01)
        y = -0.06 - col * 0.055 - (row % 2) * 0.02
        parts.append(cyl("log", rng.uniform(0.032, 0.045), rng.uniform(0.62, 0.74), (rng.uniform(-0.03, 0.03), y, z), M("log"),
                         verts=6, rot=(0, PI / 2, rng.uniform(-0.08, 0.08)), center=True))
    for z in (-0.35, -0.1):
        parts.append(tube("lash", [(-0.2, 0.01, z), (-0.2, -0.26, z + 0.02), (0.2, -0.26, z + 0.02), (0.2, 0.01, z)], 0.008, M("sacking"), n=4))
    export("vendor_backframe_wood", join(parts, "vendor_backframe_wood"))


def vendor_pack_cloth():
    """Pedlar's pack: a big bundle of cloth wrapped in sacking and corded, bolts of coloured cloth poking out of the
    top, a flat box of needles, buttons and ribbons strapped on."""
    reset()
    parts = [blob("bundle", (0.48, 0.28, 0.56), (0, -0.14, -0.38), M("sacking"))]
    for z in (-0.25, -0.05):
        parts.append(tube("cord", [(-0.25, 0.0, z), (-0.25, -0.3, z), (0.25, -0.3, z), (0.25, 0.0, z)], 0.008, M("leather"), n=4))
    for sx in (-1, 1):
        parts.append(tube("strap", [(sx * 0.14, 0.0, 0.12), (sx * 0.13, 0.2, 0.22), (sx * 0.14, 0.3, 0.05)], 0.013, M("leather"), n=4))
    for k, (mat, x) in enumerate((("bolt_red", -0.12), ("bolt_blue", 0.02), ("bolt_green", 0.14))):
        parts.append(cyl("bolt", 0.045, 0.52, (x, -0.14 + 0.04 * (k % 2), 0.2), M(mat), verts=8, rot=(0, PI / 2, 0.2 * (k - 1)), center=True))
    parts.append(box("notions_box", (0.36, 0.2, 0.09), (0, -0.14, 0.25), M("wood")))
    parts.append(box("ribbon", (0.3, 0.012, 0.02), (0, -0.245, 0.29), M("crimson")))
    export("vendor_pack_cloth", join(parts, "vendor_pack_cloth"))


def vendor_tray_candles():
    """Candle and tinder seller's tray on a neck strap: bundles of tallow dips, three standing candles (one lit),
    flints, a tinder box and a steel."""
    reset()
    rng = random.Random(1407)
    w = M("wood")
    parts = [box("tray", (0.5, 0.3, 0.02), (0, 0.04, -0.02), w)]
    for sx in (-1, 1):
        parts.append(box("rim_s", (0.02, 0.3, 0.05), (sx * 0.25, 0.04, -0.02), w))
    for sy in (-0.11, 0.19):
        parts.append(box("rim_f", (0.5, 0.02, 0.05), (0, sy, -0.02), w))
    for sx in (-1, 1):
        parts.append(tube("strap", [(sx * 0.22, -0.1, 0.02), (sx * 0.12, -0.22, 0.3), (sx * 0.05, -0.3, 0.38)], 0.01, M("leather"), n=4))
    tallow = M("tallow", 0.6)
    for k in range(8):
        parts.append(cyl("dip", 0.012, 0.2, (-0.18 + (k % 4) * 0.028, 0.02 + (k // 4) * 0.03, 0.0 + (k // 4) * 0.02), tallow,
                         verts=5, rot=(PI / 2, 0, rng.uniform(-0.1, 0.1)), center=True))
    for k, x in enumerate((0.04, 0.1, 0.16)):
        parts.append(cyl("candle", 0.016, 0.15 - 0.02 * k, (x, 0.12, 0.0), tallow, verts=6))
    parts.append(cyl("wick", 0.002, 0.012, (0.04, 0.12, 0.15), M("black"), verts=3))
    parts.append(sphere("flame", 0.012, (0.04, 0.12, 0.172), glow("flame_small", (1.0, 0.68, 0.28), 8.0), seg=6, rings=3, zscale=1.8))
    for k in range(4):
        parts.append(sphere("flint", 0.018, (0.12 + rng.uniform(-0.03, 0.03), -0.02 + rng.uniform(-0.03, 0.03), 0.01), M("flint", 0.4), seg=5, rings=3))
    parts.append(box("tinderbox", (0.08, 0.06, 0.04), (0.2, 0.0, 0.0), M("tin")))
    parts.append(box("steel", (0.07, 0.02, 0.008), (0.2, 0.08, 0.0), M("iron", 0.4)))
    export("vendor_tray_candles", join(parts, "vendor_tray_candles"))


def vendor_ballads():
    """Ballad seller's bundle held in the hand: a stack of folded broadsheets tied with string, one printed sheet
    loose on the front."""
    reset()
    parts = [box("stack", (0.15, 0.05, 0.21), (0, 0.0, -0.24), M("paper_old")),
             box("sheet", (0.15, 0.004, 0.21), (0.005, 0.028, -0.235), M("paper")),
             box("print", (0.11, 0.003, 0.03), (0.005, 0.031, -0.07), M("ink")),
             box("print2", (0.11, 0.003, 0.09), (0.005, 0.031, -0.17), M("paper_old"))]
    parts.append(tube("string", [(-0.08, 0.0, -0.13), (0.0, 0.03, -0.13), (0.08, 0.0, -0.13), (0.0, -0.03, -0.13), (-0.08, 0.0, -0.13)], 0.003, M("sacking"), n=3))
    export("vendor_ballads", join(parts, "vendor_ballads"))


BUILDS = [
    ("vendor_obwarzanki", vendor_obwarzanki), ("vendor_chestnut_cart", vendor_chestnut_cart), ("vendor_grinder", vendor_grinder),
    ("vendor_fish_barrow", vendor_fish_barrow), ("vendor_beer_can", vendor_beer_can), ("vendor_herbs", vendor_herbs),
    ("vendor_shoeblack_box", vendor_shoeblack_box), ("vendor_yoke_water", vendor_yoke_water), ("vendor_yoke_milk", vendor_yoke_milk),
    ("vendor_backframe_wood", vendor_backframe_wood), ("vendor_pack_cloth", vendor_pack_cloth),
    ("vendor_tray_candles", vendor_tray_candles), ("vendor_ballads", vendor_ballads),
]

if __name__ == "__main__":
    only = ba._cli_list("--only")
    for name, fn in BUILDS:
        if only and name not in only:
            continue
        fn()
    over = {k: v for k, v in ba.TRI_LOG.items() if v > 2000}
    print("[vendor_props] tris", " ".join("%s=%d" % kv for kv in ba.TRI_LOG.items()))
    if over:
        print("[vendor_props] OVER BUDGET (2k):", over)
