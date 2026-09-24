"""Interior sets for Krakow 1795: rooms that sit behind a door. Same Fable-ish pass as build_assets.py.

Run:  blender -b --python assets/blender/build_interiors.py [-- int_tavern int_shop_baker ...]
Writes one .glb per room into assets/models/. A room is `<set>` or `<set>_<variant>`: the set is the shell family
(shop, workshop, tavern, cellar, flat, salon, church, chapel, guard), the variant is the trade dressed into it.
data/interiors.json maps every door to a set + variant; scripts/city/interiors.gd instances the rooms.

Conventions (on top of build_assets.py)
- Every room: floor top at z=0, walls, ceiling. The entrance wall is centred on y=0 with a door opening at x=0;
  its outer face looks down -Y (Godot +Z), the room extends toward +Y (Godot -Z). So the set's origin is the
  outside of its front door, and a player standing at Blender (0, 1.8, 0) is just inside, facing into the room.
  Keep (0, 0.4..2.6) clear: the exit trigger and the spawn point live there.
- `<set>-colonly` holds the collision: floor, walls, ceiling, big furniture, stair ramps (prisms).
- Light sources are exported as empties named `lamp_<kind>_<nn>` (kind: lantern, fire, candle, window, chandelier,
  stove, oven, forge); the Godot side hangs an OmniLight3D (flickering for flames) on each. Their meshes (lantern
  glass, flames, coals, oven mouths) are emissive.
- NPC markers: empties `Post_<n>` where somebody should stand or sit; their Godot -Z (forward) is the facing.
- Props a script must find stay separate meshes under the room node (the guard post's `ledger`).
- Windows are read from inside as a night view: dark sky, the roofline across the street, a lantern glowing.
- Budget: <= 40k tris per room.
"""
import bpy
import bmesh
import importlib.util
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("build_assets", os.path.join(HERE, "build_assets.py"))
ba = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ba)
box, cbox, cyl, sphere, torus, blob, roof, arch = ba.box, ba.cbox, ba.cyl, ba.sphere, ba.torus, ba.blob, ba.roof, ba.arch
finish, join, export, M, PAL, taper_box, edit_verts = ba.finish, ba.join, ba.export, ba.M, ba.PAL, ba.taper_box, ba.edit_verts

RNG = random.Random(1796)

PAL.update({
    "plank": (0.50, 0.34, 0.20), "plank_b": (0.42, 0.27, 0.15), "plank_c": (0.56, 0.39, 0.23), "beam": (0.22, 0.14, 0.08),
    "limewash": (0.88, 0.81, 0.66), "limewash_b": (0.80, 0.72, 0.56), "plinth": (0.52, 0.40, 0.30),
    "stove_tile": (0.20, 0.42, 0.36), "stove_trim": (0.86, 0.80, 0.64),
    "fire": (1.0, 0.42, 0.10), "flame": (1.0, 0.72, 0.34), "lamp_glass": (1.0, 0.66, 0.30), "coal": (0.07, 0.05, 0.04),
    "parquet_a": (0.58, 0.38, 0.20), "parquet_b": (0.36, 0.21, 0.11),
    "panel": (0.40, 0.52, 0.46), "panel_trim": (0.93, 0.88, 0.74), "damask": (0.58, 0.16, 0.18),
    "mirror": (0.92, 0.93, 0.96), "marble": (0.90, 0.87, 0.82), "velvet": (0.52, 0.10, 0.14), "linen": (0.92, 0.88, 0.78),
    "baize": (0.10, 0.34, 0.18), "vault_blue": (0.10, 0.18, 0.46), "star": (1.0, 0.80, 0.36), "wax": (0.96, 0.93, 0.82),
    "pew": (0.30, 0.19, 0.10), "altar_blue": (0.10, 0.14, 0.34), "sack": (0.72, 0.62, 0.44),
    "moon_glass": (0.26, 0.36, 0.58), "warm_glass": (1.0, 0.62, 0.28),
    "cloth_green": (0.20, 0.40, 0.26), "cloth_blue": (0.18, 0.26, 0.52), "cloth_ochre": (0.78, 0.56, 0.20),
    "jar": (0.66, 0.46, 0.28), "pewter": (0.60, 0.62, 0.64), "brass": (0.82, 0.62, 0.26), "water": (0.08, 0.12, 0.16),
    "floor_stone": (0.62, 0.58, 0.50), "floor_stone_b": (0.48, 0.45, 0.40), "paint_dark": (0.18, 0.12, 0.10),
    "night_sky": (0.05, 0.08, 0.17), "night_roof": (0.015, 0.015, 0.025), "night_glow": (1.0, 0.62, 0.26),
    "soot_ceil": (0.10, 0.07, 0.05), "soot_wall": (0.34, 0.28, 0.22), "flour": (0.93, 0.91, 0.86),
    "dough": (0.90, 0.82, 0.64), "crust": (0.62, 0.36, 0.14), "crust_b": (0.48, 0.26, 0.10),
    "leather": (0.36, 0.20, 0.10), "leather_b": (0.22, 0.12, 0.07), "hide": (0.66, 0.50, 0.34),
    "label": (0.90, 0.86, 0.72), "ink": (0.08, 0.07, 0.06), "paper": (0.92, 0.89, 0.80),
    "terracotta": (0.64, 0.30, 0.18), "tile_w": (0.86, 0.84, 0.78), "tile_k": (0.14, 0.13, 0.13),
    "tile_ochre": (0.74, 0.54, 0.26), "tile_red": (0.52, 0.18, 0.12), "tallow": (0.92, 0.86, 0.62),
    "straw_bed": (0.76, 0.64, 0.34), "bone": (0.86, 0.82, 0.70), "herb": (0.36, 0.42, 0.20), "herb_b": (0.50, 0.44, 0.22),
    "icon_red": (0.62, 0.12, 0.10), "icon_blue": (0.12, 0.20, 0.48), "icon_green": (0.16, 0.34, 0.24),
    "parochet": (0.42, 0.08, 0.16), "musket": (0.28, 0.18, 0.10), "coat_blue": (0.16, 0.20, 0.40),
    "wallpaper": (0.64, 0.58, 0.40), "wall_green": (0.46, 0.54, 0.44), "wall_rose": (0.70, 0.46, 0.42),
    "curtain_red": (0.56, 0.10, 0.14), "brick_vault": (0.46, 0.24, 0.16), "coffee": (0.20, 0.11, 0.06),
    "glass_green": (0.16, 0.30, 0.18), "wine": (0.30, 0.04, 0.08), "felt_green": (0.12, 0.30, 0.18),
    "horn": (0.95, 0.62, 0.30), "wicker": (0.52, 0.38, 0.20), "copper_pot": (0.62, 0.34, 0.18), "earth": (0.22, 0.18, 0.14), "earth_b": (0.29, 0.23, 0.17),
})
PAL["sack"] = (0.56, 0.47, 0.32)
PAL["straw_bed"] = (0.60, 0.48, 0.24)
PAL["flour"] = (0.84, 0.82, 0.76)

CTX = {}          # current room: W, D, t (wall thickness)
LAMPS = []
POSTS = []
KEEP = []         # objects exported as their own named mesh under the room node
SURF = {}         # surface kind -> collision boxes exported as surf_<kind>-colonly (floors with their own footstep sound)
FX = []           # particle / exit markers (fx_smoke_nn, fx_steam_nn, fx_drip_nn, Exit_<name>)
BUDGET = 40000


CEILING = {       # room -> ceiling fixture style for lantern() (default: an iron lantern)
    "int_tavern": "wheel", "int_tavern_beerhall": "wheel", "int_tavern_inn": "horn", "int_store_warehouse": "horn",
    "int_tavern_kawiarnia": "oil", "int_bath_lazna": "chain", "int_workshop_cooper": "horn", "int_workshop_forge": "horn",
    "int_shop_chandler": "wheel", "int_house_kingpin": "oil", "int_flat_scholar": "none", "int_flat_burgher": "none",
    "int_shop_tailor": "oil", "int_shop_goldsmith": "oil", "int_guard_post": "lantern", "int_undercroft": "lantern",
}
ROOM = [""]       # the room being built (set by the __main__ loop)


def start():
    ba.reset()
    LAMPS.clear()
    POSTS.clear()
    KEEP.clear()
    SURF.clear()
    FX.clear()
    CTX.clear()
    CTX["ceiling"] = CEILING.get(ROOM[0], "lantern")
    CTX["moons"] = 0


def post(x, y, a=0.0, z=0.0):
    """NPC marker. Its Godot forward (-Z) looks along Blender (-sin a, cos a): a=0 looks into the room (+Y)."""
    o = bpy.data.objects.new("Post_%d" % len(POSTS), None)
    bpy.context.collection.objects.link(o)
    o.location = (x, y, z)
    o.rotation_euler = (0.0, 0.0, a)
    o.empty_display_size = 0.3
    POSTS.append(o)
    return o


def post_at(x, y, tx, ty, z=0.0):
    """NPC marker at (x, y) looking toward (tx, ty)."""
    return post(x, y, math.atan2(-(tx - x), ty - y), z)


def keep(o, name):
    """A prop that stays its own mesh (named) under the room node, for scripts to find."""
    o.name = name
    KEEP.append(o)
    return o


def EM(key, strength=4.0, rough=0.5):
    return M(key, rough, emit=PAL[key], emit_strength=strength)


def MET(key, rough=0.3):
    fresh = key not in ba._mats
    m = M(key, rough)
    if fresh:
        m.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 1.0
    return m


def lamp(kind, loc):
    o = bpy.data.objects.new("lamp_%s_%02d" % (kind, len(LAMPS)), None)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.empty_display_size = 0.2
    LAMPS.append(o)
    return o


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def cut(o, cutters):
    """Boolean-difference each cutter out of o, then delete the cutters."""
    for c in cutters:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        m = o.modifiers.new("cut", "BOOLEAN")
        m.operation = "DIFFERENCE"
        m.object = c
        m.solver = "EXACT"
        bpy.ops.object.modifier_apply(modifier=m.name)
        bpy.data.objects.remove(c, do_unlink=True)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return o


def place(objs, x, y, rot=0.0, z=0.0, name="grp"):
    """Join parts built around the origin (front facing -Y) and move them: rot about Z, then translate.
    rot=0 faces -Y, PI faces +Y, PI/2 faces +X, -PI/2 faces -X."""
    o = join(objs, name)
    c, s = math.cos(rot), math.sin(rot)

    def f(co):
        X, Y = co.x, co.y
        co.x = x + X * c - Y * s
        co.y = y + X * s + Y * c
        co.z += z
    edit_verts(o, f)
    return o


def prism(name, x0, x1, y0, y1, z0, z1, mat=None):
    """Right-triangle prism: floor from y0 to y1, rising to z1 at y1 (under-stair wedge, ramp collider)."""
    bm = bmesh.new()
    a = [bm.verts.new((x0, y0, z0)), bm.verts.new((x0, y1, z0)), bm.verts.new((x0, y1, z1))]
    b = [bm.verts.new((x1, y0, z0)), bm.verts.new((x1, y1, z0)), bm.verts.new((x1, y1, z1))]
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    for i in range(3):
        j = (i + 1) % 3
        bm.faces.new((a[i], b[i], b[j], a[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    if mat:
        o.data.materials.append(mat)
    return o


# ------------------------------------------------------------------ walls in room-local terms
def wl(side, name, su, sn, sz, u, n, z, mat=None, **fin):
    """Box against a wall's inner face. u = position along the wall, n = distance of the box centre from the face
    into the room, z = base. su/sn/sz = size along wall / out of wall / up."""
    W, D, t = CTX["W"], CTX["D"], CTX["t"]
    if side == "F":
        return box(name, (su, sn, sz), (u, t / 2 + n, z), mat, **fin)
    if side == "B":
        return box(name, (su, sn, sz), (u, D - n, z), mat, **fin)
    if side == "L":
        return box(name, (sn, su, sz), (-W / 2 + n, u, z), mat, **fin)
    return box(name, (sn, su, sz), (W / 2 - n, u, z), mat, **fin)


def warch(side, name, w, h, dn, u, n, z, mat, **fin):
    W, D, t = CTX["W"], CTX["D"], CTX["t"]
    if side == "F":
        return arch(name, w, h, dn, (u, t / 2 + n, z), mat, **fin)
    if side == "B":
        return arch(name, w, h, dn, (u, D - n, z), mat, **fin)
    if side == "L":
        return arch(name, w, h, dn, (-W / 2 + n, u, z), mat, rot_z=math.pi / 2, **fin)
    return arch(name, w, h, dn, (W / 2 - n, u, z), mat, rot_z=math.pi / 2, **fin)


def _wall_geo(side):
    """(u0, u1, centre of the wall along its normal, normal axis) for one wall."""
    W, D, t = CTX["W"], CTX["D"], CTX["t"]
    if side == "F":
        return -W / 2 - t, W / 2 + t, 0.0, "y"
    if side == "B":
        return -W / 2 - t, W / 2 + t, D + t / 2, "y"
    if side == "L":
        return -t / 2, D + t, -W / 2 - t / 2, "x"
    return -t / 2, D + t, W / 2 + t / 2, "x"


def _wbox(side, name, a, b, z0, z1, mat=None, thick=None):
    t = thick or CTX["t"]
    u0, u1, c, axis = _wall_geo(side)
    if axis == "y":
        return box(name, (b - a, t, z1 - z0), ((a + b) / 2, c, z0), mat)
    return box(name, (t, b - a, z1 - z0), (c, (a + b) / 2, z0), mat)


def wall(side, H, mat, openings=(), wonk=0.02):
    """One wall with openings [(u, w, h, arched)], h = total height. Returns (visual, [collision boxes])."""
    u0, u1, c, axis = _wall_geo(side)
    t = CTX["t"]
    o = _wbox(side, "wall_" + side, u0, u1, 0, H, M(mat))
    finish(o, bevel=0, wonk=wonk, smooth=0)
    cutters = []
    for (u, w, h, arched) in openings:
        hr = h - w / 2 if arched else h
        if axis == "y":
            cutters.append(box("cut", (w, t * 4, hr + 0.3), (u, c, -0.3)))
            if arched:
                cutters.append(cyl("cutc", w / 2, t * 4, (u, c, hr), verts=24, rot=(math.pi / 2, 0, 0), center=True))
        else:
            cutters.append(box("cut", (t * 4, w, hr + 0.3), (c, u, -0.3)))
            if arched:
                cutters.append(cyl("cutc", w / 2, t * 4, (c, u, hr), verts=24, rot=(0, math.pi / 2, 0), center=True))
    if cutters:
        cut(o, cutters)
    col = []
    cur = u0
    for (u, w, h, arched) in sorted(openings):
        col.append(_wbox(side, "c", cur, u - w / 2, 0, H))
        col.append(_wbox(side, "c", u - w / 2, u + w / 2, h - (w * 0.15 if arched else 0), H))
        cur = u + w / 2
    col.append(_wbox(side, "c", cur, u1, 0, H))
    return o, col


def door_leaf(parts, w, h, arched, y):
    """Closed plank door filling the opening, seen from inside. y = its inner face."""
    wd = M("wood_dark")
    if arched:
        parts.append(arch("leaf", w, h, 0.08, (0, y - 0.04, 0), wd, bevel=0.02))
    else:
        parts.append(box("leaf", (w, 0.08, h), (0, y - 0.04, 0), wd, bevel=0.02, seg=1))
    for i in range(1, 4):
        parts.append(box("gap", (0.03, 0.02, h - (w / 2 if arched else 0.1) - 0.1), (-w / 2 + w * i / 4, y + 0.005, 0.05), M("black")))
    for zz in (0.5, h * 0.62):
        parts.append(box("strap", (w - 0.2, 0.03, 0.09), (0, y + 0.015, zz), M("iron", 0.6)))
    parts.append(torus("ring", 0.08, 0.018, (w * 0.3, y + 0.05, 1.05), M("iron", 0.6), rot=(math.pi / 2, 0, 0)))
    parts.append(box("latch", (0.22, 0.04, 0.05), (w * 0.3, y + 0.02, 1.15), M("iron", 0.6)))


def shell(W, D, H, wall_mat, ceil_mat="beam", t=0.3, door_w=1.3, door_h=2.3, arched=False, ceiling=True,
          openings=None, frame=True):
    """Floor slab, four walls, optional ceiling slab, entrance door at the origin. Returns (parts, col)."""
    CTX.update(W=W, D=D, t=t)
    openings = openings or {}
    parts, col = [], []
    parts.append(box("slab", (W + 2 * t, D + 2 * t, 0.3), (0, D / 2, -0.32), M("beam")))
    col.append(box("c", (W + 2 * t, D + 2 * t, 0.4), (0, D / 2, -0.4)))
    if ceiling:
        parts.append(box("ceiling", (W + 2 * t, D + 2 * t, 0.25), (0, D / 2, H), M(ceil_mat)))
        col.append(box("c", (W + 2 * t, D + 2 * t, 0.25), (0, D / 2, H)))
    for side in "LRB":
        v, c = wall(side, H, wall_mat, openings.get(side, ()))
        parts.append(v)
        col += c
    front = [(0.0, door_w, door_h, arched)] + list(openings.get("F", ()))
    v, c = wall("F", H, wall_mat, front)
    parts.append(v)
    col += c
    col.append(box("c", (door_w + 0.1, 0.12, door_h), (0, -t / 2 + 0.06, 0)))   # plug behind the door leaf
    door_leaf(parts, door_w, door_h, arched, -t / 2 + 0.10)
    if frame:
        fr = M("timber")
        for sx in (-1, 1):
            parts.append(box("jamb", (0.16, 0.10, door_h - (door_w / 2 if arched else 0) + 0.05), (sx * (door_w / 2 + 0.08), t / 2 + 0.03, 0), fr, bevel=0.03, seg=1, wonk=0.01))
        if not arched:
            parts.append(box("lintel", (door_w + 0.5, 0.12, 0.18), (0, t / 2 + 0.04, door_h), fr, bevel=0.03, seg=1, wonk=0.01))
    parts.append(box("threshold", (door_w + 0.1, t + 0.1, 0.04), (0, 0, 0), M("stone_dark"), bevel=0.01, seg=1))
    return parts, col


# ------------------------------------------------------------------ floors, ceilings, trim
def plank_floor(parts, x0, x1, y0, y1, w=0.30, mats=("plank", "plank_b", "plank_c")):
    n = max(1, int(round((x1 - x0) / w)))
    w = (x1 - x0) / n
    for i in range(n):
        x = x0 + w * (i + 0.5)
        ya = y0
        while ya < y1 - 0.05:
            yb = min(y1, ya + RNG.uniform(1.8, 3.6))
            parts.append(box("plank", (w - 0.014, yb - ya - 0.014, 0.05), (x, (ya + yb) / 2, -0.05), M(RNG.choice(mats), 0.8)))
            ya = yb


def tile_floor(parts, x0, x1, y0, y1, s=1.0, mats=("floor_stone", "floor_stone_b"), checker=True, wonk=0.0):
    nx = max(1, int(round((x1 - x0) / s)))
    ny = max(1, int(round((y1 - y0) / s)))
    sx, sy = (x1 - x0) / nx, (y1 - y0) / ny
    for i in range(nx):
        for j in range(ny):
            m = mats[(i + j) % 2] if checker else RNG.choice(mats)
            o = box("tile", (sx - 0.02, sy - 0.02, 0.05), (x0 + sx * (i + 0.5), y0 + sy * (j + 0.5), -0.05), M(m, 0.7))
            if wonk:
                edit_verts(o, lambda co: setattr(co, "z", co.z + (RNG.uniform(-wonk, wonk) if co.z > -0.01 else 0)))
            parts.append(o)


def ceiling_beams(parts, W, D, H, step=1.3, summer=True, drop=0.28, mat="beam", y0=0.0):
    n = max(1, int(D / step))
    for i in range(n):
        y = y0 + (D / n) * (i + 0.5)
        parts.append(box("cbeam", (W, 0.22, drop), (0, y, H - drop), M(mat), bevel=0.04, seg=1, wonk=0.03))
    if summer:
        parts.append(box("summer", (0.34, D, drop + 0.08), (0, y0 + D / 2, H - drop - 0.08), M(mat), bevel=0.05, seg=1, wonk=0.03))


def timber_frame(parts, sides, H, step=2.0, rail=None):
    """Posts (and an optional rail) standing proud of the plaster, Fachwerk-style."""
    for side in sides:
        L = CTX["W"] if side in "FB" else CTX["D"]
        u_lo, u_hi = (-L / 2, L / 2) if side in "FB" else (0.2, L)
        n = max(1, int((u_hi - u_lo) / step))
        for i in range(n + 1):
            u = u_lo + (u_hi - u_lo) * i / n
            if side == "F" and abs(u) < 1.2:
                continue
            parts.append(wl(side, "post", 0.22, 0.08, H, u, 0.03, 0, M("beam"), bevel=0.03, seg=1, wonk=0.02))
        if rail:
            parts.append(wl(side, "rail", u_hi - u_lo, 0.08, 0.18, (u_lo + u_hi) / 2, 0.05, rail, M("beam"), bevel=0.03, seg=1, wonk=0.02))


def skirting(parts, sides, h, mat, n=0.03):
    for side in sides:
        L = CTX["W"] if side in "FB" else CTX["D"]
        u = 0.0 if side in "FB" else L / 2
        parts.append(wl(side, "skirt", L, 0.06, h, u, n, 0, M(mat)))


def fake_window(parts, side, u, z, w=0.9, h=1.3, glass="moon_glass", strength=0.6, arched=False, sill=True, n=0.0,
                night=True, bars=False, lamp_side=None):
    """Window read from inside: deep reveal frame, panes, mullions and sill against the wall face. night=True shows
    the street at night through it: dark sky, the roofline opposite with one lit window, a lantern glowing below."""
    fr = M("wood_dark")
    if night:
        g = EM("night_sky", 0.55, 0.2)
    else:
        g = EM(glass, strength, 0.2)
    if arched:
        parts.append(warch(side, "wframe", w + 0.24, h + 0.12, 0.10, u, n + 0.03, z - 0.06, fr, bevel=0.02))
        parts.append(warch(side, "wglass", w, h, 0.04, u, n + 0.08, z, g, bevel=0))
    else:
        parts.append(wl(side, "wframe", w + 0.24, 0.10, h + 0.24, u, n + 0.03, z - 0.12, fr, bevel=0.02, seg=1, wonk=0.01))
        parts.append(wl(side, "wglass", w, 0.04, h, u, n + 0.08, z, g))
    if night:
        roof = M("night_roof", 0.9)
        rh = h * RNG.uniform(0.30, 0.42)
        parts.append(wl(side, "nroof", w, 0.01, rh, u, n + 0.105, z, roof))
        gx = RNG.uniform(-0.25, 0.1) * w
        parts.append(wl(side, "ngable", w * 0.34, 0.01, h * 0.14, u + gx, n + 0.105, z + rh, roof))
        parts.append(wl(side, "nchim", w * 0.06, 0.01, h * 0.16, u + gx + w * 0.26, n + 0.105, z + rh, roof))
        parts.append(wl(side, "nlit", w * 0.07, 0.01, h * 0.07, u + gx - w * 0.05, n + 0.11, z + rh * 0.55, EM("night_glow", 2.5, 0.4)))
        ls = lamp_side if lamp_side is not None else RNG.choice((-1, 1))
        gp = _wpos(side, u + ls * w * 0.3, n + 0.11)
        parts.append(sphere("nlamp", 0.035, (gp[0], gp[1], z + rh * 0.35), EM("night_glow", 9.0, 0.3), seg=8, rings=4))
        parts.append(sphere("nhalo", 0.07, (gp[0], gp[1], z + rh * 0.35), EM("night_glow", 1.2, 0.3), seg=8, rings=4))
        if CTX.get("moons", 0) < 2:
            CTX["moons"] = CTX.get("moons", 0) + 1
            mx, my = _wpos(side, u, n + 0.5)
            lamp("moon", (mx, my, z + h * 0.6))
        for k in range(3):
            sp = _wpos(side, u + RNG.uniform(-0.4, 0.4) * w, n + 0.105)
            parts.append(sphere("nstar", 0.008, (sp[0], sp[1], z + h * RNG.uniform(0.7, 0.92)), EM("star", 4.0, 0.3), seg=4, rings=2))
    parts.append(wl(side, "wmull", 0.05, 0.04, h - (w / 2 if arched else 0), u, n + 0.13, z, fr))
    parts.append(wl(side, "wmull", w, 0.04, 0.05, u, n + 0.13, z + h * 0.45, fr))
    if bars:
        for k in range(5):
            parts.append(wl(side, "wbar", 0.025, 0.025, h, u - w / 2 + w * (k + 0.5) / 5, n + 0.17, z, M("iron", 0.5)))
        for zz in (0.25, 0.75):
            parts.append(wl(side, "wbarh", w, 0.03, 0.03, u, n + 0.18, z + h * zz, M("iron", 0.5)))
    if sill:
        parts.append(wl(side, "wsill", w + 0.4, 0.26, 0.07, u, n + 0.13, z - 0.14, M("stone"), bevel=0.02, seg=1, wonk=0.01))


# ------------------------------------------------------------------ props (built around the origin, front -Y)
def candle(parts, x, y, z, h=0.18, r=0.022, holder=True):
    if holder:
        parts.append(cyl("cstick", 0.045, 0.03, (x, y, z), M("brass", 0.35), verts=8))
        parts.append(cyl("cstick", 0.014, 0.08, (x, y, z + 0.03), M("brass", 0.35), verts=6))
        z += 0.11
    parts.append(cyl("wax", r, h, (x, y, z), M("wax", 0.5), verts=8))
    parts.append(cyl("flame", 0.014, 0.05, (x, y, z + h + 0.005), EM("flame", 8.0), verts=6, r2=0.0))


def lantern(parts, x, y, H, z, kind="lantern"):
    """Ceiling light hanging from H, light centre at z. The room's light plan (CTX["ceiling"]) picks the fixture:
    lantern (iron, glazed), horn (iron frame with dull horn panes), wheel (iron candle-wheel), oil (brass oil lamp
    with a glass chimney), chain (a small lamp on a chain, the bathhouse), none (nothing: the room stays dark)."""
    style = CTX.get("ceiling", "lantern") if kind == "lantern" else kind
    if style == "none":
        return
    if style == "wheel":
        return candle_wheel(parts, x, y, H, z)
    if style == "oil":
        return oil_lamp(parts, x, y, H, z)
    if style == "chain":
        return chain_lamp(parts, x, y, H, z)
    iron = M("iron", 0.6)
    if style == "horn":
        parts.append(cyl("chain", 0.012, H - z - 0.3, (x, y, z + 0.3), iron, verts=6))
        parts.append(cyl("hcap", 0.15, 0.16, (x, y, z + 0.18), iron, verts=8, r2=0.03))
        parts.append(cyl("hglass", 0.12, 0.34, (x, y, z - 0.17), EM("horn", 2.2, 0.6), verts=8))
        for k in range(4):
            a = math.tau * k / 4 + math.pi / 4
            parts.append(box("hpost", (0.02, 0.02, 0.36), (x + 0.125 * math.cos(a), y + 0.125 * math.sin(a), z - 0.18), iron))
        parts.append(cyl("hbase", 0.14, 0.04, (x, y, z - 0.2), iron, verts=8))
        parts.append(torus("hring", 0.05, 0.01, (x, y, z + 0.38), iron, rot=(math.pi / 2, 0, 0), seg=8, mseg=3))
        lamp("horn", (x, y, z))
        return
    parts.append(cyl("chain", 0.012, H - z - 0.3, (x, y, z + 0.3), iron, verts=6))
    parts.append(taper_box("lcap", (0.30, 0.30, 0.14), (x, y, z + 0.22), iron, top=0.3))
    parts.append(box("lglass", (0.20, 0.20, 0.30), (x, y, z - 0.10), EM("lamp_glass", 6.0)))
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box("lpost", (0.03, 0.03, 0.34), (x + sx * 0.11, y + sy * 0.11, z - 0.12), iron))
    parts.append(box("lbase", (0.28, 0.28, 0.05), (x, y, z - 0.16), iron))
    lamp(kind, (x, y, z))


def candle_wheel(parts, x, y, H, z, r=0.5, n=8):
    """Iron candle-wheel: a hoop hung on three chains from a hook, tallow candles in drip cups round it."""
    iron = M("iron", 0.6)
    parts.append(torus("wheel", r, 0.02, (x, y, z), iron, seg=24, mseg=4))
    parts.append(torus("whub", 0.08, 0.02, (x, y, z), iron, seg=10, mseg=4))
    for k in range(4):
        a = math.tau * k / 4
        parts.append(cbox("wspoke", (r, 0.015, 0.015), (x + r / 2 * math.cos(a), y + r / 2 * math.sin(a), z), iron, rot=(0, 0, a)))
    top = z + 0.7
    for k in range(3):
        a = math.tau * k / 3 + 0.3
        cx, cy = x + r * math.cos(a), y + r * math.sin(a)
        ln = math.sqrt(r * r + 0.49)
        tilt = math.atan2(r, 0.7)
        parts.append(cbox("wchain", (0.01, 0.01, ln), ((cx + x) / 2, (cy + y) / 2, (z + top) / 2), iron,
                          rot=(tilt * math.sin(a), -tilt * math.cos(a), 0)))
    parts.append(cyl("wrope", 0.012, H - top, (x, y, top), iron, verts=6))
    for k in range(n):
        a = math.tau * (k + 0.5) / n
        cx, cy = x + r * math.cos(a), y + r * math.sin(a)
        parts.append(cyl("wcup", 0.04, 0.03, (cx, cy, z + 0.01), iron, verts=8, r2=0.05))
        parts.append(cyl("wcandle", 0.018, RNG.uniform(0.1, 0.18), (cx, cy, z + 0.04), M("tallow", 0.5), verts=6))
        parts.append(cyl("wflame", 0.012, 0.04, (cx, cy, z + 0.2), EM("flame", 8.0), verts=6, r2=0.0))
        parts.append(blob("wdrip", (0.03, 0.03, 0.06), (cx, cy, z - 0.04), M("tallow", 0.5), subsurf=1))
    lamp("wheel", (x, y, z + 0.2))


def oil_lamp(parts, x, y, H, z):
    """Brass hanging oil lamp: a fount on three chains, a glass chimney, a smoke bell above."""
    br = MET("brass", 0.3)
    parts.append(cyl("ochain", 0.01, H - z - 0.6, (x, y, z + 0.6), br, verts=6))
    parts.append(cyl("obell", 0.14, 0.12, (x, y, z + 0.5), br, verts=12, r2=0.04))
    for k in range(3):
        a = math.tau * k / 3
        parts.append(cbox("ostay", (0.008, 0.008, 0.5), (x + 0.1 * math.cos(a), y + 0.1 * math.sin(a), z + 0.25), br))
    parts.append(sphere("ofount", 0.13, (x, y, z - 0.05), br, seg=14, rings=8, zscale=0.7))
    parts.append(cyl("ogallery", 0.07, 0.04, (x, y, z + 0.03), br, verts=10))
    parts.append(cyl("ochimney", 0.04, 0.26, (x, y, z + 0.07), EM("lamp_glass", 5.0, 0.2), verts=10, r2=0.03))
    parts.append(cyl("ofinial", 0.02, 0.1, (x, y, z - 0.2), br, verts=8, r2=0.0))
    lamp("oil", (x, y, z + 0.15))


def chain_lamp(parts, x, y, H, z):
    """A clay oil lamp in an iron cradle on a long chain."""
    parts.append(cyl("cchain", 0.01, H - z - 0.08, (x, y, z + 0.08), M("iron", 0.6), verts=6))
    parts.append(torus("ccradle", 0.08, 0.01, (x, y, z), M("iron", 0.6), seg=10, mseg=3))
    parts.append(blob("clamp", (0.16, 0.1, 0.06), (x, y, z - 0.03), M("terracotta", 0.6), subsurf=1))
    parts.append(cyl("cflame", 0.012, 0.05, (x + 0.07, y, z + 0.02), EM("flame", 8.0), verts=6, r2=0.0))
    lamp("chainlamp", (x + 0.07, y, z + 0.1))


def sconce(parts, side, u, z=1.8, n=0.0):
    """Wall sconce: an iron bracket, a tin reflector behind the flame, a drip pan and a tallow candle."""
    iron = M("iron", 0.55)
    parts.append(wl(side, "sbackplate", 0.1, 0.02, 0.3, u, n + 0.01, z - 0.15, iron))
    parts.append(wl(side, "sreflector", 0.24, 0.015, 0.34, u, n + 0.03, z - 0.02, MET("pewter", 0.15), bevel=0.01, seg=1))
    parts.append(wl(side, "sarm", 0.025, 0.2, 0.025, u, n + 0.12, z - 0.06, iron))
    px, py = _wpos(side, u, n + 0.2)
    parts.append(cyl("span", 0.05, 0.015, (px, py, z - 0.05), iron, verts=8))
    parts.append(cyl("scandle", 0.018, 0.13, (px, py, z - 0.035), M("tallow", 0.5), verts=6))
    parts.append(cyl("sflame", 0.012, 0.04, (px, py, z + 0.1), EM("flame", 8.0), verts=6, r2=0.0))
    parts.append(blob("sdrip", (0.03, 0.03, 0.05), (px, py, z - 0.09), M("tallow", 0.5), subsurf=1))
    lx, ly = _wpos(side, u, n + 0.24)
    lamp("sconce", (lx, ly, z + 0.12))


def rushlight(parts, x, y, z):
    """Rushlight holder: an iron nip on a wooden block holding a peeled rush at a slant; a tiny flame."""
    parts.append(cyl("rblock", 0.05, 0.05, (x, y, z), M("wood_dark"), verts=8))
    parts.append(cyl("rstem", 0.006, 0.18, (x, y, z + 0.05), M("iron", 0.5), verts=4))
    parts.append(cbox("rush", (0.005, 0.005, 0.3), (x + 0.07, y, z + 0.25), M("straw_bed", 0.8), rot=(0, 0.9, 0)))
    parts.append(cyl("rflame", 0.008, 0.03, (x + 0.19, y, z + 0.33), EM("flame", 8.0), verts=4, r2=0.0))
    lamp("rush", (x + 0.19, y, z + 0.38))


SCONCES = {       # room -> [(side, u, z)]: wall sconces added at finish_set
    "int_tavern": [("L", 1.4, 2.0), ("R", 1.2, 1.9), ("R", 3.4, 1.9)],
    "int_shop": [("R", 3.6, 1.8)],
    "int_workshop": [("B", 1.4, 1.9)],
    "int_church": [("F", -4.5, 2.2), ("F", 4.5, 2.2)],
    "int_salon": [("B", -1.0, 1.9), ("F", -2.6, 1.9)],
    "int_shop_baker": [("F", -0.9, 1.9)],
    "int_shop_shoemaker": [("B", 1.6, 1.8)],
    "int_shop_goldsmith": [("R", 1.4, 1.7)],
    "int_shop_apothecary": [("R", 1.8, 1.8)],
    "int_shop_tailor": [("R", 3.5, 1.9)],
    "int_shop_cloth": [("R", 1.0, 1.9)],
    "int_shop_chandler": [("L", 2.2, 1.8)],
    "int_workshop_locksmith": [("L", 1.2, 1.8)],
    "int_workshop_cooper": [("R", 3.0, 1.9)],
    "int_workshop_forge": [("R", 1.0, 2.0)],
    "int_tavern_beerhall": [("L", 1.6, 1.9), ("L", 6.2, 1.9), ("R", 3.9, 1.9), ("F", -4.4, 1.9)],
    "int_tavern_kawiarnia": [("L", 5.2, 1.9), ("R", 4.8, 1.9)],
    "int_tavern_inn": [("R", 5.2, 1.9), ("L", 1.2, 1.9), ("F", 4.4, 1.9)],
    "int_cellar_wine": [],
    "int_salon_brothel": [("L", 1.0, 1.8), ("B", 0.8, 1.8)],
    "int_flat_burgher": [("L", 4.3, 1.8)],
    "int_flat_scholar": [],
    "int_guard_post": [("B", 0.8, 1.9), ("F", -1.2, 1.9)],
    "int_chapel_synagogue": [("F", -3.8, 2.0), ("F", 3.8, 2.0)],
    "int_chapel_uniate": [],
    "int_bath_lazna": [("L", 1.0, 1.8)],
    "int_store_warehouse": [("L", 3.0, 2.2), ("R", 7.0, 2.2)],
}


def barrel(parts, x, y, z=0.0, r=0.32, h=0.85, lying=False, rot=0.0):
    wm = M("wood", 0.8)
    iron = M("iron", 0.6)
    p = [cyl("staves", r * 0.86, h / 2, (0, 0, 0), wm, verts=12, r2=r),
         cyl("staves", r, h / 2, (0, 0, h / 2), wm, verts=12, r2=r * 0.86)]
    for zz in (0.06, h / 2 - 0.03, h - 0.1):
        rr = r * (0.88 if zz < 0.1 or zz > h - 0.15 else 1.0) + 0.012
        p.append(cyl("hoop", rr, 0.05, (0, 0, zz), iron, verts=12))
    o = join(p, "barrel")
    if lying:
        # roll it onto its side along X, centred on its middle
        def f(co):
            X, Z = co.x, co.z - h / 2
            co.x, co.z = Z, X + r
        edit_verts(o, f)
    o = place([o], x, y, rot, z)
    parts.append(o)
    return o


def table(parts, col, x, y, L=1.6, w=0.8, h=0.78, along_y=True, top_mat="wood", trestle=True):
    p = [box("ttop", (w, L, 0.07), (0, 0, h - 0.07), M(top_mat, 0.8), bevel=0.03, seg=1, wonk=0.015)]
    wm = M("wood_dark")
    if trestle:
        for sy in (-1, 1):
            yy = sy * (L / 2 - 0.22)
            for sx in (-1, 1):
                p.append(box("tleg", (0.07, 0.07, h - 0.05), (sx * 0.18, yy, 0), wm, rot=(0, sx * -0.35, 0)))
            p.append(box("tfoot", (w - 0.1, 0.09, 0.08), (0, yy, 0), wm))
        p.append(box("tstretch", (0.07, L - 0.4, 0.08), (0, 0, 0.35), wm))
    else:
        for sx in (-1, 1):
            for sy in (-1, 1):
                p.append(box("tleg", (0.06, 0.06, h - 0.07), (sx * (w / 2 - 0.07), sy * (L / 2 - 0.07), 0), wm))
    parts.append(place(p, x, y, 0 if along_y else math.pi / 2))
    if col is not None:
        col.append(box("c", (w, L, h) if along_y else (L, w, h), (x, y, 0)))


def bench(parts, x, y, L=1.5, along_y=True, h=0.45):
    wm = M("wood", 0.8)
    p = [box("bseat", (0.30, L, 0.06), (0, 0, h - 0.06), wm, bevel=0.02, seg=1, wonk=0.01)]
    for sy in (-1, 1):
        p.append(box("bleg", (0.26, 0.06, h - 0.06), (0, sy * (L / 2 - 0.15), 0), M("wood_dark")))
    parts.append(place(p, x, y, 0 if along_y else math.pi / 2))


def chair(parts, x, y, rot=0.0, fancy=False):
    wm = M("wood_dark")
    up = M("velvet", 0.9) if fancy else wm
    p = [box("seat", (0.46, 0.44, 0.07), (0, 0, 0.42), up, bevel=0.025, seg=1)]
    for sx in (-1, 1):
        p.append(box("leg", (0.05, 0.05, 0.42), (sx * 0.19, -0.18, 0), wm))
        p.append(box("leg", (0.05, 0.05, 0.98), (sx * 0.19, 0.19, 0), wm))
    p.append(box("back", (0.40, 0.05, 0.42), (0, 0.19, 0.52), up, bevel=0.02, seg=1))
    if fancy:
        p.append(box("crest", (0.46, 0.06, 0.06), (0, 0.19, 0.96), MET("gold", 0.35), bevel=0.02, seg=1))
    parts.append(place(p, x, y, rot))


def tankard(parts, x, y, z):
    parts.append(cyl("tank", 0.045, 0.14, (x, y, z), M("pewter", 0.35), verts=8))


def plate(parts, x, y, z):
    parts.append(cyl("plate", 0.11, 0.02, (x, y, z), M("pewter", 0.4), verts=10))


def bottle(parts, x, y, z, mat="glass"):
    parts.append(cyl("bottle", 0.04, 0.2, (x, y, z), M(mat, 0.3), verts=8))
    parts.append(cyl("neck", 0.015, 0.08, (x, y, z + 0.2), M(mat, 0.3), verts=6))


def shelf_unit(parts, col, side, u, L, n, z0=0.4, dz=0.5, depth=0.35, goods="jars"):
    """Open shelves standing against a wall, stocked."""
    wm = M("wood", 0.8)
    top = z0 + dz * (n - 1)
    for sgn in (-1, 1):
        parts.append(wl(side, "upright", 0.05, depth, top + 0.1, u + sgn * L / 2, depth / 2, 0, M("wood_dark")))
    for i in range(n):
        z = z0 + dz * i
        parts.append(wl(side, "board", L, depth, 0.04, u, depth / 2, z, wm))
        k = 0.1
        while k < L - 0.15:
            uu = u - L / 2 + k
            kind = goods if goods != "mixed" else RNG.choice(("jars", "cloth", "boxes", "bottles"))
            if kind == "jars":
                r = RNG.uniform(0.05, 0.08)
                hh = RNG.uniform(0.12, 0.26)
                pos = _wpos(side, uu, depth / 2)
                parts.append(cyl("jar", r, hh, (pos[0], pos[1], z + 0.04), M(RNG.choice(("jar", "stove_trim", "brick_dark")), 0.5), verts=8, r2=r * 0.8))
                k += r * 2 + 0.05
            elif kind == "bottles":
                pos = _wpos(side, uu, depth / 2)
                bottle(parts, pos[0], pos[1], z + 0.04, RNG.choice(("glass", "copper", "glass_warm")))
                k += 0.11
            elif kind == "cloth":
                ln = min(0.5, depth + 0.05)
                pos = _wpos(side, uu, depth / 2)
                o = cyl("bolt", 0.08, ln, (pos[0], pos[1], z + 0.12), M(RNG.choice(("cloth_green", "cloth_blue", "crimson", "cloth_ochre", "linen")), 0.9),
                        verts=10, rot=(math.pi / 2, 0, 0) if side in "LR" else (0, math.pi / 2, 0), center=True)
                edit_verts(o, lambda co: None)
                parts.append(o)
                k += 0.18
            else:
                s = RNG.uniform(0.16, 0.26)
                parts.append(wl(side, "gbox", s, depth * 0.8, s * 0.7, uu + s / 2, depth / 2, z + 0.04, M(RNG.choice(("wood", "canvas", "sack")), 0.8)))
                k += s + 0.04
    col.append(wl(side, "c", L, depth, top + 0.1, u, depth / 2, 0))


def _wpos(side, u, n):
    W, D, t = CTX["W"], CTX["D"], CTX["t"]
    return {"F": (u, t / 2 + n), "B": (u, D - n), "L": (-W / 2 + n, u), "R": (W / 2 - n, u)}[side]


def fire(parts, x, y, z, w=0.7, kind="fire", strength=10.0):
    for i in range(3):
        parts.append(cyl("log", 0.06, w, (x, y + (i - 1) * 0.1, z + 0.06 + (0.08 if i == 1 else 0)), M("wood_dark"), verts=8, rot=(0, math.pi / 2, 0), center=True))
    parts.append(box("embers", (w * 0.8, 0.35, 0.04), (x, y, z), EM("fire", strength * 0.5)))
    for k in range(4):
        fx = x + (k - 1.5) * w * 0.2
        parts.append(cyl("flame", 0.07, RNG.uniform(0.22, 0.38), (fx, y, z + 0.1), EM("flame", strength), verts=6, r2=0.0))
    lamp(kind, (x, y, z + 0.4))


def stair(parts, col, x, y0, z0=0.0, width=1.0, rise=2.8, steps=14, run=0.26, rail_sides=(1,), closed=True):
    """Straight stair climbing toward +Y. Treads, risers, stringers, newels, handrails; wedge collider underneath."""
    L = run * steps
    wm = M("wood", 0.8)
    dk = M("wood_dark")
    for i in range(steps):
        zt = z0 + rise * (i + 1) / steps
        yy = y0 + run * i
        parts.append(box("tread", (width, run + 0.03, 0.05), (x, yy + run / 2, zt - 0.05), wm, bevel=0.015, seg=1, wonk=0.008))
        parts.append(box("riser", (width - 0.02, 0.03, rise / steps), (x, yy + 0.015, zt - rise / steps), dk))
    ang = math.atan2(rise, L)
    ln = math.hypot(rise, L)
    for sx in (-1, 1):
        parts.append(cbox("stringer", (0.06, ln - 0.1, 0.26), (x + sx * (width / 2 + 0.03), y0 + L / 2, z0 + rise / 2 + 0.06), dk, rot=(ang, 0, 0)))
    if closed:
        parts.append(prism("under", x - width / 2, x + width / 2, y0, y0 + L, z0, z0 + rise - 0.06, M("plank_b", 0.8)))
    for sx in rail_sides:
        xr = x + sx * (width / 2 + 0.03)
        parts.append(box("newel", (0.1, 0.1, 1.1), (xr, y0 + 0.05, z0), dk, bevel=0.02, seg=1))
        parts.append(box("newel", (0.1, 0.1, 1.0), (xr, y0 + L - 0.05, z0 + rise), dk, bevel=0.02, seg=1))
        parts.append(cbox("hrail", (0.07, ln, 0.07), (xr, y0 + L / 2, z0 + rise / 2 + 0.95), wm, rot=(ang, 0, 0)))
        for i in range(0, steps, 2):
            yy = y0 + run * (i + 0.5)
            zt = z0 + rise * (i + 1) / steps
            parts.append(box("baluster", (0.035, 0.035, 0.92), (xr, yy, zt), dk))
    col.append(prism("c", x - width / 2, x + width / 2, y0, y0 + L, z0, z0 + rise))
    return L


MANIFEST = {}


def finish_set(name, parts, col):
    for (side, u, z) in SCONCES.get(name, []):
        sconce(parts, side, u, z)
    visual = join(parts, name)
    n = tris(visual) + sum(tris(k) for k in KEEP)
    for k in KEEP:
        k.parent = visual
    for kind, boxes in SURF.items():
        sc = join(boxes, "surf_" + kind)
        sc.name = "surf_%s-colonly" % kind
        sc.parent = visual
        sc.display_type = "WIRE"
    export(name, visual, join(col, "col"))
    MANIFEST[name] = (n, len(LAMPS), len(POSTS))
    print("[interiors] %-26s tris=%d lamps=%d posts=%d%s" % (name, n, len(LAMPS), len(POSTS), "  WARNING >%dk" % (BUDGET // 1000) if n > BUDGET else ""))


# ------------------------------------------------------------------ shared shell system
FLOOR_SURFACE = {"planks": "planks", "parquet": "planks", "flags": "stone", "brick": "stone", "tiles": "tiles",
                 "terracotta": "tiles", "earth": "stone"}


def xf(x, y, rot, lx, ly):
    """Local (lx, ly) of a group placed at (x, y) turned by rot -> room coordinates."""
    c, s = math.cos(rot), math.sin(rot)
    return (x + lx * c - ly * s, y + lx * s + ly * c)


def vault(parts, W, D, spring, mat, y0=0.0, ribs=0, rib_mat="stone", x0=0.0):
    """Inward-facing barrel vault over x in [x0-W/2, x0+W/2], y in [y0, y0+D], springing at z=spring."""
    R = W / 2
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=R, depth=D, location=(x0, y0 + D / 2, spring),
                                        rotation=(math.pi / 2, 0, 0), end_fill_type="NOTHING")
    v = bpy.context.object
    v.name = "vault"
    v.data.materials.append(M(mat, 0.9))
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bm = bmesh.new()
    bm.from_mesh(v.data)
    bmesh.ops.delete(bm, geom=[vv for vv in bm.verts if vv.co.z < spring - 0.01], context="VERTS")
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(v.data)
    bm.free()
    bpy.ops.object.shade_smooth()
    parts.append(v)
    for k in range(ribs):
        y = y0 + D * (k + 0.5) / ribs
        for a in range(8):
            a0 = math.pi * a / 8 + math.pi / 16
            parts.append(cbox("rib", (0.2, 0.22, R * math.pi / 8 + 0.04), (x0 + R * 0.97 * math.cos(a0), y, spring + R * 0.97 * math.sin(a0)),
                              M(rib_mat), rot=(0, -a0, 0)))


def paver_floor(parts, x0, x1, y0, y1, a=0.5, b=0.25, mats=("tile_red", "brick_vault", "terracotta"), z=0.0):
    rows = max(1, int(round((y1 - y0) / b)))
    b = (y1 - y0) / rows
    for j in range(rows):
        x = x0 - (a / 2 if j % 2 else 0.0)
        while x < x1 - 0.01:
            xa, xb = max(x0, x), min(x1, x + a)
            if xb - xa > 0.04:
                parts.append(box("paver", (xb - xa - 0.015, b - 0.015, 0.05), ((xa + xb) / 2, y0 + b * (j + 0.5), z - 0.05), M(RNG.choice(mats), 0.85)))
            x += a


def lay_floor(parts, kind, x0, x1, y0, y1, z=0.0):
    if kind == "planks":
        plank_floor(parts, x0, x1, y0, y1, w=0.28)
    elif kind == "parquet":
        tile_floor(parts, x0, x1, y0, y1, s=0.7, mats=("parquet_a", "parquet_b"))
    elif kind == "flags":
        tile_floor(parts, x0, x1, y0, y1, s=0.9, checker=False, wonk=0.01)
    elif kind == "tiles":
        tile_floor(parts, x0, x1, y0, y1, s=0.5, mats=("tile_w", "tile_k"))
    elif kind == "terracotta":
        tile_floor(parts, x0, x1, y0, y1, s=0.4, mats=("terracotta", "tile_ochre"), checker=False)
    elif kind == "brick":
        paver_floor(parts, x0, x1, y0, y1)
    elif kind == "earth":
        tile_floor(parts, x0, x1, y0, y1, s=1.2, mats=("earth", "earth_b"), checker=False, wonk=0.02)


def flip_y(o, s):
    """Mirror y -> s - y and fix the winding."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    for v in bm.verts:
        v.co.y = s - v.co.y
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    return o


def room(W, D, H, wall="limewash", floor="planks", ceil="beams", t=0.3, door_w=1.3, door_h=2.3, arched=False,
         openings=None, frame=True, spring=None, beam_step=1.3, summer=True, skirt=None, rib=0):
    """The shared shell: walls (with openings), a floor of `floor` kind, a ceiling of `ceil` kind
    (beams | soot | flat | vault; a vault springs at `spring` and the walls rise to its crown)."""
    top = spring + W / 2 + 0.05 if ceil == "vault" else H
    cm = {"beams": "beam", "soot": "soot_ceil", "flat": "limewash", "vault": wall}[ceil]
    parts, col = shell(W, D, top, wall, ceil_mat=cm, t=t, door_w=door_w, door_h=door_h, arched=arched,
                       openings=openings, frame=frame)
    lay_floor(parts, floor, -W / 2, W / 2, 0, D)
    if ceil == "beams":
        ceiling_beams(parts, W, D, H, step=beam_step, summer=summer, drop=0.24)
    elif ceil == "soot":
        ceiling_beams(parts, W, D, H, step=beam_step, summer=summer, drop=0.26, mat="soot_ceil")
        for side in "LRB":
            L = W if side == "B" else D
            parts.append(wl(side, "soot", L, 0.02, 0.9, 0.0 if side == "B" else L / 2, 0.005, H - 0.9, M("soot_wall", 0.95)))
    elif ceil == "flat":
        for side in "LRBF":
            L = W if side in "FB" else D
            parts.append(wl(side, "cornice", L, 0.16, 0.18, 0.0 if side in "FB" else L / 2, 0.08, H - 0.18, M("limewash_b", 0.7), bevel=0.04, seg=1))
    elif ceil == "vault":
        vault(parts, W, D + 0.02, spring, wall, y0=-0.01, ribs=rib)
    if skirt:
        skirting(parts, "LRB", skirt[1], skirt[0])
    CTX["surface"] = FLOOR_SURFACE[floor]
    CTX["H"] = H if ceil != "vault" else top
    return parts, col


# ------------------------------------------------------------------ prop library (room coordinates unless noted)
def tiled_stove(parts, col, x, y, rot=0.0, lit=True, tile="stove_tile", trim="stove_trim", w=0.9, d=0.8, h=2.1):
    """Kachlowy piec: tiled body, cornice band, a smaller upper stage, a fire door at the front (-Y local)."""
    tm, tr = M(tile, 0.3), M(trim, 0.5)
    lo = h * 0.55
    p = [box("sbase", (w + 0.1, d + 0.1, 0.2), (0, 0, 0), M("brick_dark"), bevel=0.02, seg=1),
         box("sbody", (w, d, lo), (0, 0, 0.2), tm, bevel=0.03, seg=1, wonk=0.01),
         box("sband", (w + 0.07, d + 0.07, 0.09), (0, 0, 0.2 + lo), tr, bevel=0.02, seg=1),
         box("stop", (w * 0.8, d * 0.8, h * 0.33), (0, 0, 0.29 + lo), tm, bevel=0.03, seg=1, wonk=0.01),
         box("scap", (w * 0.92, d * 0.92, 0.1), (0, 0, 0.29 + lo + h * 0.33), tr, bevel=0.02, seg=1)]
    for k in range(1, 4):
        p.append(box("sgrout", (w + 0.012, d + 0.012, 0.012), (0, 0, 0.2 + k * lo / 4), tr))
    for k in range(1, 3):
        p.append(box("sgroutv", (0.012, d + 0.012, lo), (-w / 2 + k * w / 3, 0, 0.2), tr))
        p.append(box("sgroutv", (w + 0.012, 0.012, lo), (0, -d / 2 + k * d / 3, 0.2), tr))
    p.append(box("sdoorf", (0.34, 0.02, 0.28), (0, -d / 2 - 0.005, 0.3), M("iron", 0.6)))
    p.append(box("sdoor", (0.24, 0.02, 0.18), (0, -d / 2 - 0.015, 0.35), EM("fire", 5.0) if lit else M("coal", 0.9)))
    parts.append(place(p, x, y, rot))
    col.append(place([box("c", (w + 0.1, d + 0.1, h + 0.3), (0, 0, 0))], x, y, rot))
    if lit:
        lx, ly = xf(x, y, rot, 0, -d / 2 - 0.4)
        lamp("stove", (lx, ly, 0.5))


def iron_stove(parts, col, x, y, lit=False):
    """Small cast-iron box stove on legs with a pipe to the ceiling."""
    iron = M("iron", 0.55)
    parts.append(box("istove", (0.55, 0.45, 0.6), (x, y, 0.18), iron, bevel=0.02, seg=1))
    parts.append(box("istop", (0.62, 0.52, 0.04), (x, y, 0.78), iron))
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(cyl("ileg", 0.025, 0.18, (x + sx * 0.22, y + sy * 0.17, 0), iron, verts=6))
    parts.append(box("idoor", (0.22, 0.02, 0.16), (x, y - 0.235, 0.35), EM("fire", 5.0) if lit else M("coal", 0.9)))
    parts.append(cyl("ipipe", 0.06, CTX.get("H", 3.0) - 0.82, (x, y + 0.1, 0.82), iron, verts=8))
    col.append(box("c", (0.62, 0.52, 0.82), (x, y, 0)))
    if lit:
        lamp("stove", (x, y - 0.5, 0.45))


def counter(parts, col, x, y, L, w=0.6, h=0.95, rot=0.0, mat="wood_dark", top="wood", panels=True):
    """Shop counter, customer side toward local -Y."""
    p = [box("counter", (L, w, h), (0, 0, 0), M(mat), bevel=0.04, seg=1, wonk=0.02),
         box("ctop", (L + 0.2, w + 0.15, 0.07), (0, 0, h), M(top, 0.6), bevel=0.03, seg=1, wonk=0.01)]
    if panels:
        n = max(1, int(L / 0.9))
        for i in range(n):
            p.append(box("cpanel", (L / n - 0.2, 0.03, h - 0.4), (-L / 2 + L / n * (i + 0.5), -w / 2 - 0.01, 0.2), M("wood", 0.8), bevel=0.01, seg=1))
    parts.append(place(p, x, y, rot))
    col.append(place([box("c", (L + 0.2, w + 0.15, h + 0.07), (0, 0, 0))], x, y, rot))
    return h + 0.07


def scales(parts, x, y, z, rot=0.0, s=1.0):
    brass = M("brass", 0.35)
    p = [box("sbase", (0.22 * s, 0.14 * s, 0.04 * s), (0, 0, 0), M("wood_dark")),
         cyl("spost", 0.015 * s, 0.42 * s, (0, 0, 0.04 * s), brass, verts=6),
         box("sbeam", (0.56 * s, 0.02 * s, 0.02 * s), (0, 0, 0.44 * s), brass)]
    for sx in (-1, 1):
        for a in (-1, 1):
            p.append(cbox("sstring", (0.004, 0.004, 0.26 * s), (sx * 0.27 * s + a * 0.04 * s, 0, 0.32 * s), brass, rot=(0, a * 0.15, 0)))
        p.append(cyl("span", 0.09 * s, 0.02 * s, (sx * 0.27 * s, 0, 0.18 * s), brass, verts=10, r2=0.06 * s))
    parts.append(place(p, x, y, rot, z))


def cask(parts, col, x, y, z=0.0, r=0.42, L=1.1, rot=0.0, cradle=True, tap=False, mark=True):
    """Cask lying on its side along local Y (ends face local -Y/+Y), optionally on a cradle, with a tap."""
    wm = M("wood", 0.8)
    iron = M("iron", 0.6)
    zc = z + r + (0.18 if cradle else 0.0)
    p = [cyl("cask", r * 0.86, L / 2, (0, -L / 4, zc), wm, verts=14, r2=r, rot=(-math.pi / 2, 0, 0), center=True),
         cyl("cask", r, L / 2, (0, L / 4, zc), wm, verts=14, r2=r * 0.86, rot=(-math.pi / 2, 0, 0), center=True)]
    for yy in (-L / 2 + 0.06, -L / 6, L / 6, L / 2 - 0.06):
        rr = r * (0.9 if abs(yy) > L / 3 else 1.0) + 0.01
        p.append(cyl("hoop", rr, 0.05, (0, yy, zc), iron, verts=14, rot=(math.pi / 2, 0, 0), center=True))
    p.append(cyl("head", r * 0.84, 0.02, (0, -L / 2 - 0.005, zc), M("wood_dark"), verts=14, rot=(math.pi / 2, 0, 0), center=True))
    if mark:
        p.append(box("mark", (0.22, 0.01, 0.12), (0, -L / 2 - 0.02, zc + 0.12), M("chalk" if "chalk" in PAL else "linen", 0.9)))
    if tap:
        p.append(cyl("tap", 0.025, 0.14, (0, -L / 2 - 0.07, zc - r * 0.55), M("brass", 0.35), verts=6, rot=(math.pi / 2, 0, 0), center=True))
        p.append(box("tapk", (0.02, 0.02, 0.07), (0, -L / 2 - 0.12, zc - r * 0.55), M("brass", 0.35)))
    if cradle:
        for yy in (-L / 3, L / 3):
            p.append(box("cradle", (r * 1.8, 0.12, 0.22), (0, yy, z), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(place(p, x, y, rot))
    if col is not None:
        col.append(place([box("c", (2 * r, L, 2 * r + (0.18 if cradle else 0)), (0, 0, z))], x, y, rot))
    return zc + r


def rug(parts, x, y, w, L, mat="crimson", border="cloth_ochre", rot=0.0):
    parts.append(place([box("rug", (w, L, 0.012), (0, 0, 0), M(border, 0.95)),
                        box("rugc", (w - 0.2, L - 0.2, 0.014), (0, 0, 0), M(mat, 0.95))], x, y, rot))


def portrait(parts, side, u, z, w=0.8, h=1.0, sitter="plaster_rose", coat="navy", n=0.02):
    """Gilt frame, a dark ground, a bust (face and coat) roughly painted."""
    parts.append(wl(side, "pframe", w + 0.14, 0.06, h + 0.14, u, n + 0.03, z - 0.07, MET("gold", 0.35), bevel=0.02, seg=1))
    parts.append(wl(side, "pcanvas", w, 0.02, h, u, n + 0.065, z, M("paint_dark", 0.6)))
    parts.append(wl(side, "pcoat", w * 0.62, 0.012, h * 0.42, u, n + 0.078, z, M(coat, 0.7)))
    fx, fy = _wpos(side, u, n + 0.08)
    parts.append(blob("pface", (w * 0.2, 0.02, h * 0.24), (fx, fy, z + h * 0.44), M(sitter, 0.6), subsurf=1))


def mirror(parts, side, u, z, w=0.9, h=1.4, n=0.02):
    parts.append(wl(side, "mframe", w + 0.16, 0.06, h + 0.16, u, n + 0.03, z - 0.08, MET("gold", 0.35), bevel=0.03, seg=1))
    parts.append(wl(side, "mirror", w, 0.02, h, u, n + 0.07, z, MET("mirror", 0.04)))
    parts.append(wl(side, "mcrest", w * 0.6, 0.07, 0.22, u, n + 0.035, z + h + 0.06, MET("gold", 0.35), bevel=0.03, seg=1))


def pegs(parts, side, u0, u1, z, n=0.0):
    parts.append(wl(side, "pegrail", u1 - u0, 0.04, 0.1, (u0 + u1) / 2, n + 0.02, z, M("wood_dark")))


def hanging_coat(parts, side, u, z, mat="brown_coat", n=0.0):
    parts.append(wl(side, "peg", 0.04, 0.12, 0.04, u, n + 0.06, z, M("wood_dark")))
    parts.append(wl(side, "coat", 0.42, 0.14, 0.95, u, n + 0.11, z - 0.95, M(mat, 0.9), bevel=0.05, seg=1, wonk=0.04))


def bed(parts, col, x, y, rot=0.0, w=1.2, L=2.0, blanket="crimson", posts=True, canopy=None):
    """Bed, head toward local +Y."""
    wd = M("wood_dark")
    p = [box("bframe", (w, L, 0.35), (0, 0, 0.1), M("wood", 0.8), bevel=0.03, seg=1, wonk=0.02),
         box("bhead", (w - 0.1, 0.06, 0.75), (0, L / 2 - 0.03, 0.35), wd, bevel=0.02, seg=1),
         blob("mattress", (w - 0.1, L - 0.1, 0.22), (0, 0, 0.43), M("linen", 0.9), subsurf=1, bevel=0.04),
         blob("pillow", (w - 0.4, 0.4, 0.16), (0, L / 2 - 0.3, 0.62), M("linen", 0.9), subsurf=1, bevel=0.03),
         box("blanket", (w + 0.06, L * 0.6, 0.08), (0, -L * 0.18, 0.6), M(blanket, 0.9), bevel=0.04, seg=2, wonk=0.03)]
    if posts:
        for sx in (-1, 1):
            for sy in (-1, 1):
                ph = (2.0 if canopy else 1.2) if sy > 0 else (2.0 if canopy else 0.7)
                p.append(box("bpost", (0.08, 0.08, ph), (sx * (w / 2 - 0.04), sy * (L / 2 - 0.04), 0), wd, bevel=0.02, seg=1))
    if canopy:
        p.append(box("tester", (w + 0.1, L + 0.1, 0.12), (0, 0, 2.0), wd, bevel=0.02, seg=1))
        for sx in (-1, 1):
            p.append(box("bcurt", (0.08, 0.5, 1.9), (sx * (w / 2 + 0.02), L / 2 - 0.3, 0.1), M(canopy, 0.9), bevel=0.03, seg=1, wonk=0.03))
            p.append(box("bcurt", (0.08, 0.35, 1.9), (sx * (w / 2 + 0.02), -L / 2 + 0.2, 0.1), M(canopy, 0.9), bevel=0.03, seg=1, wonk=0.03))
        p.append(box("bval", (w + 0.16, L + 0.16, 0.25), (0, 0, 1.8), M(canopy, 0.9), bevel=0.02, seg=1))
    parts.append(place(p, x, y, rot))
    col.append(place([box("c", (w, L, 0.7), (0, 0, 0))], x, y, rot))


def washstand(parts, col, x, y, rot=0.0):
    p = [box("wstand", (0.6, 0.45, 0.8), (0, 0, 0), M("wood_dark"), bevel=0.02, seg=1),
         box("wtop", (0.64, 0.49, 0.04), (0, 0, 0.8), M("marble", 0.3)),
         cyl("basin", 0.2, 0.08, (0, 0, 0.84), M("tile_w", 0.2), verts=12, r2=0.14),
         cyl("jug", 0.07, 0.24, (0.18, 0.1, 0.84), M("tile_w", 0.2), verts=10, r2=0.05),
         box("towel", (0.3, 0.02, 0.35), (0, -0.24, 0.45), M("linen", 0.9), bevel=0.01, seg=1)]
    parts.append(place(p, x, y, rot))
    col.append(place([box("c", (0.64, 0.49, 0.84), (0, 0, 0))], x, y, rot))


def stool(parts, x, y, h=0.5, r=0.17, tipped=False):
    p = [cyl("stool", r, 0.05, (0, 0, h - 0.05), M("wood", 0.8), verts=10)]
    for k in range(3):
        a = math.tau * k / 3
        p.append(cbox("sleg", (0.035, 0.035, h), (r * 0.6 * math.cos(a), r * 0.6 * math.sin(a), h / 2 - 0.02), M("wood_dark"),
                      rot=(0.12 * math.sin(a), -0.12 * math.cos(a), 0)))
    o = place(p, 0, 0)
    if tipped:
        def f(co):
            Y, Z = co.y, co.z
            co.y, co.z = -Z, Y + r
        edit_verts(o, f)
    parts.append(place([o], x, y, RNG.uniform(0, 3)))


def round_table(parts, col, x, y, r=0.4, h=0.74, top="marble", base="iron", tripod=True):
    parts.append(cyl("rtop", r, 0.04, (x, y, h - 0.04), M(top, 0.25 if top == "marble" else 0.7), verts=16, bevel=0.01, seg=1))
    parts.append(cyl("rped", 0.03, h - 0.1, (x, y, 0.06), M(base, 0.5), verts=8))
    if tripod:
        for k in range(3):
            a = math.tau * k / 3
            parts.append(cbox("rfoot", (0.32, 0.035, 0.035), (x + 0.15 * math.cos(a), y + 0.15 * math.sin(a), 0.03), M(base, 0.5), rot=(0, 0, a)))
    else:
        parts.append(cyl("rbase", 0.22, 0.05, (x, y, 0), M(base, 0.5), verts=10))
    col.append(cyl("c", r, h, (x, y, 0), None, verts=8))


def cup(parts, x, y, z, mat="tile_w"):
    parts.append(cyl("saucer", 0.06, 0.01, (x, y, z), M(mat, 0.2), verts=8))
    parts.append(cyl("cup", 0.035, 0.05, (x, y, z + 0.01), M(mat, 0.2), verts=8, r2=0.03))


def loaf(parts, x, y, z, big=True, rot=0.0):
    if big:
        parts.append(place([blob("loaf", (0.26, 0.16, 0.11), (0, 0, 0), M(RNG.choice(("crust", "crust_b")), 0.7), subsurf=1)], x, y, rot, z))
    else:
        parts.append(place([blob("roll", (0.1, 0.08, 0.06), (0, 0, 0), M("crust", 0.7), subsurf=1)], x, y, rot, z))


def pretzel(parts, x, y, z, flat=True):
    """Obwarzanek: a boiled-and-baked ring."""
    parts.append(torus("obw", 0.07, 0.022, (x, y, z + (0.022 if flat else 0)), M("crust", 0.6), seg=10, mseg=5,
                       rot=(0, 0, 0) if flat else (math.pi / 2, 0, 0)))


def jar(parts, x, y, z, r=0.06, h=0.2, body="tile_w", label=True, lid="brass"):
    """Albarello: glazed body, a painted label band, a lid."""
    parts.append(cyl("jar", r, h, (x, y, z), M(body, 0.3), verts=8, r2=r * 0.85))
    if label:
        parts.append(cyl("label", r * 0.97 + 0.004, h * 0.32, (x, y, z + h * 0.3), M("label", 0.6), verts=8))
    parts.append(cyl("lid", r * 0.9, 0.03, (x, y, z + h), M(lid, 0.4), verts=6, r2=r * 0.4))


def book_row(parts, side, u0, u1, z, n, depth=0.22, mats=("crimson", "leather", "leather_b", "icon_green", "coat_blue", "cloth_ochre")):
    u = u0
    while u < u1 - 0.03:
        th = RNG.uniform(0.03, 0.07)
        hh = RNG.uniform(0.2, 0.32)
        if RNG.random() < 0.06:
            u += 0.08
            continue
        parts.append(wl(side, "book", th, depth * RNG.uniform(0.75, 0.95), hh, u + th / 2, n, z, M(RNG.choice(mats), 0.8)))
        u += th + 0.004


def bookcase(parts, col, side, u, L, H=2.4, shelves=6, depth=0.3):
    wm = M("wood_dark")
    parts.append(wl(side, "bcback", L, 0.03, H, u, 0.015, 0, M("wood", 0.8)))
    for sgn in (-1, 1):
        parts.append(wl(side, "bcside", 0.05, depth, H, u + sgn * (L / 2 - 0.025), depth / 2, 0, wm))
    parts.append(wl(side, "bctop", L + 0.1, depth + 0.05, 0.08, u, depth / 2, H, wm, bevel=0.02, seg=1))
    for i in range(shelves):
        z = 0.1 + i * (H - 0.2) / shelves
        parts.append(wl(side, "bcshelf", L - 0.1, depth, 0.03, u, depth / 2, z, wm))
        book_row(parts, side, u - L / 2 + 0.06, u + L / 2 - 0.06, z + 0.03, depth / 2 + 0.02, depth)
    col.append(wl(side, "c", L, depth, H, u, depth / 2, 0))


def herb_bunch(parts, x, y, z, s=1.0):
    parts.append(cyl("hstr", 0.004, 0.25, (x, y, z - 0.25), M("canvas", 0.9), verts=4))
    parts.append(cyl("herbs", 0.07 * s, 0.32 * s, (x, y, z - 0.25 - 0.32 * s), M(RNG.choice(("herb", "herb_b", "straw_bed")), 0.95), verts=6, r2=0.015,
                     wonk=0.01))


def key_shape(parts, side, u, z, n, s=1.0, mat="iron"):
    """A big key hanging bit-down on a wall board."""
    m = M(mat, 0.45)
    px, py = _wpos(side, u, n)
    rot = (0, math.pi / 2, 0) if side in "FB" else (math.pi / 2, 0, 0)
    parts.append(torus("kbow", 0.03 * s, 0.008 * s, (px, py, z), m, rot=rot, seg=8, mseg=4))
    parts.append(wl(side, "kshaft", 0.012 * s, 0.012 * s, 0.14 * s, u, n, z - 0.17 * s, m))
    parts.append(wl(side, "kbit", 0.03 * s, 0.012 * s, 0.035 * s, u + 0.02 * s, n, z - 0.17 * s, m))


def candle_bottle(parts, x, y, z):
    """Candle stuck in a wine bottle, drips of wax down the neck."""
    parts.append(cyl("cbot", 0.04, 0.2, (x, y, z), M("glass_green", 0.25), verts=8))
    parts.append(cyl("cneck", 0.016, 0.07, (x, y, z + 0.2), M("glass_green", 0.25), verts=6))
    parts.append(blob("drip", (0.05, 0.05, 0.1), (x, y, z + 0.17), M("wax", 0.5), subsurf=1))
    candle(parts, x, y, z + 0.27, h=0.1, r=0.016, holder=False)


def candelabrum(parts, col, x, y, h=1.6, arms=5):
    """Standing brass girandole."""
    br = M("brass", 0.35)
    parts.append(cyl("gbase", 0.22, 0.08, (x, y, 0), br, verts=10, r2=0.12))
    parts.append(cyl("gshaft", 0.03, h, (x, y, 0.08), br, verts=8))
    for k in range(arms):
        if k == 0:
            candle(parts, x, y, h + 0.08, h=0.2, r=0.02, holder=False)
            continue
        a = math.tau * k / (arms - 1)
        ax, ay = x + 0.22 * math.cos(a), y + 0.22 * math.sin(a)
        parts.append(cbox("garm", (0.24, 0.02, 0.02), ((x + ax) / 2, (y + ay) / 2, h - 0.06), br, rot=(0, 0, a)))
        parts.append(cyl("gcup", 0.03, 0.04, (ax, ay, h - 0.06), br, verts=8))
        candle(parts, ax, ay, h - 0.02, h=0.18, r=0.018, holder=False)
    lamp("candle", (x, y, h + 0.3))
    if col is not None:
        col.append(cyl("c", 0.22, h, (x, y, 0), None, verts=6))


def brass_chandelier(parts, x, y, H, z, arms=8, r=0.55, kind="chandelier"):
    """Dutch brass chandelier: a ball, S-arms with candles, hung from the ceiling."""
    br = M("brass", 0.3)
    parts.append(cyl("bchain", 0.012, H - z - 0.2, (x, y, z + 0.2), M("iron", 0.6), verts=6))
    parts.append(cyl("bstem", 0.03, 0.4, (x, y, z - 0.2), br, verts=8))
    parts.append(sphere("bball", 0.14, (x, y, z - 0.28), br, seg=12, rings=6))
    for k in range(arms):
        a = math.tau * k / arms
        cx, cy = x + r * math.cos(a), y + r * math.sin(a)
        parts.append(cbox("barm", (r, 0.025, 0.025), (x + r / 2 * math.cos(a), y + r / 2 * math.sin(a), z - 0.2), br, rot=(0, -0.25, a)))
        parts.append(cyl("bpan", 0.05, 0.02, (cx, cy, z - 0.08), br, verts=8))
        candle(parts, cx, cy, z - 0.06, h=0.14, r=0.016, holder=False)
    lamp(kind, (x, y, z))


def muskets(parts, col, side, u, n_guns=6):
    """Wall rack of muskets standing butt-down."""
    wm = M("wood_dark")
    L = n_guns * 0.16 + 0.2
    parts.append(wl(side, "rrack", L, 0.3, 0.08, u, 0.15, 0.1, wm))
    parts.append(wl(side, "rrack", L, 0.12, 0.08, u, 0.08, 1.2, wm))
    for k in range(n_guns):
        uu = u - L / 2 + 0.18 + k * 0.16
        parts.append(wl(side, "mstock", 0.05, 0.12, 0.62, uu, 0.16, 0.18, M("musket", 0.7)))
        parts.append(wl(side, "mbarrel", 0.022, 0.022, 0.95, uu, 0.14, 0.8, M("iron", 0.35)))
        parts.append(wl(side, "mbayo", 0.012, 0.012, 0.35, uu, 0.14, 1.75, M("pewter", 0.3)))
        parts.append(wl(side, "mlock", 0.03, 0.04, 0.06, uu + 0.02, 0.2, 0.72, M("iron", 0.35)))
    col.append(wl(side, "c", L, 0.35, 1.3, u, 0.18, 0))


# ------------------------------------------------------------------ INT_STAIR (shared module)
def int_stair():
    start()
    parts, col = [], []
    CTX.update(W=1.0, D=4.0, t=0.1)
    stair(parts, col, 0.0, 0.0, width=1.0, rise=2.8, steps=14, run=0.26, rail_sides=(-1, 1))
    parts.append(box("landing", (1.2, 1.2, 0.12), (0, 3.64 + 0.6, 2.68), M("plank", 0.8), bevel=0.02, seg=1))
    col.append(box("c", (1.2, 1.2, 0.12), (0, 3.64 + 0.6, 2.68)))
    finish_set("int_stair", parts, col)


# ------------------------------------------------------------------ INT_TAVERN (karczma, ~10 x 8)
def int_tavern():
    start()
    W, D, H = 10.0, 8.0, 5.0
    parts, col = shell(W, D, H, "limewash")
    plank_floor(parts, -W / 2, W / 2, 0, D)
    ceiling_beams(parts, W, D, H, step=1.3)
    timber_frame(parts, "LRBF", H, step=2.0, rail=2.6)
    skirting(parts, "LRB", 0.9, "plinth")
    # gallery along the back wall
    GY, GZ = 6.0, 2.8
    parts.append(box("gallery", (W, D - GY, 0.2), (0, (GY + D) / 2, GZ - 0.2), M("plank", 0.8), bevel=0.03, seg=1, wonk=0.02))
    parts.append(box("gbeam", (W, 0.26, 0.3), (0, GY + 0.13, GZ - 0.5), M("beam"), bevel=0.04, seg=1, wonk=0.02))
    col.append(box("c", (W, D - GY, 0.2), (0, (GY + D) / 2, GZ - 0.2)))
    for x in (-3.4, -0.6, 2.2):
        parts.append(box("gpost", (0.24, 0.24, GZ - 0.5), (x, GY + 0.13, 0), M("beam"), bevel=0.04, seg=1, wonk=0.02))
        parts.append(box("gbrace", (0.9, 0.14, 0.14), (x, GY + 0.13, GZ - 0.85), M("beam"), bevel=0.02, seg=1))
        col.append(box("c", (0.24, 0.24, GZ), (x, GY + 0.13, 0)))
    rail_x1 = 3.85
    parts.append(box("grail", (rail_x1 + W / 2, 0.08, 0.08), ((rail_x1 - W / 2) / 2, GY + 0.05, GZ + 0.95), M("wood", 0.8), bevel=0.02, seg=1))
    x = -W / 2 + 0.25
    while x < rail_x1:
        parts.append(box("gbal", (0.05, 0.05, 0.95), (x, GY + 0.05, GZ), M("wood_dark")))
        x += 0.3
    col.append(box("c", (rail_x1 + W / 2, 0.12, 1.1), ((rail_x1 - W / 2) / 2, GY + 0.05, GZ)))
    # stair up the right wall to the gallery
    stair(parts, col, 4.4, GY - 0.26 * 11, 0.0, width=1.0, rise=GZ, steps=11, run=0.26, rail_sides=(-1,))
    # gallery furnishing: a table, a door to the rooms, a window
    n0, c0 = len(parts), len(col)
    table(parts, col, -2.8, 7.2, L=1.2, w=0.7, along_y=False, trestle=False)
    tankard(parts, -2.9, 7.2, 0.78)
    for i in range(2):
        chair(parts, -3.2 + i * 0.8, 7.75, 0, False)
    for o in parts[n0:] + col[c0:]:          # lift the lot onto the gallery floor
        edit_verts(o, lambda co: setattr(co, "z", co.z + GZ))
    parts.append(wl("B", "gdoor", 1.0, 0.08, 2.0, 1.2, 0.02, GZ, M("wood_dark"), bevel=0.02, seg=1))
    parts.append(wl("B", "gdoorframe", 1.3, 0.06, 2.2, 1.2, 0.01, GZ, M("beam")))
    fake_window(parts, "B", -0.8, GZ + 0.9, w=0.8, h=1.0)
    # bar counter under the gallery, barrels and bottle shelves behind it
    parts.append(box("bar", (5.4, 0.7, 1.05), (-0.8, 6.55, 0), M("wood_dark"), bevel=0.04, seg=1, wonk=0.02))
    parts.append(box("bartop", (5.6, 0.85, 0.07), (-0.8, 6.55, 1.05), M("wood", 0.6), bevel=0.03, seg=1, wonk=0.01))
    for i in range(6):
        parts.append(box("barpanel", (0.7, 0.03, 0.6), (-3.1 + i * 0.92, 6.19, 0.22), M("wood", 0.8), bevel=0.01, seg=1))
    col.append(box("c", (5.6, 0.85, 1.12), (-0.8, 6.55, 0)))
    for k in range(3):
        barrel(parts, -4.2 + k * 0.72, 7.55, 0.2, r=0.33, h=0.8, lying=True, rot=math.pi / 2)
    parts.append(box("cradle", (2.3, 0.7, 0.2), (-3.5, 7.55, 0), M("wood_dark")))
    col.append(box("c", (2.4, 0.8, 0.9), (-3.5, 7.55, 0)))
    for z in (1.2, 1.7):
        parts.append(wl("B", "bshelf", 2.8, 0.3, 0.04, 0.8, 0.15, z, M("wood", 0.8)))
        for k in range(9):
            pos = _wpos("B", -0.4 + k * 0.3, 0.15)
            if k % 3 == 2:
                tankard(parts, pos[0], pos[1], z + 0.04)
            else:
                bottle(parts, pos[0], pos[1], z + 0.04, ("glass", "copper", "glass_warm")[k % 3])
    for k in range(4):
        tankard(parts, -2.6 + k * 0.5, 6.45, 1.12)
    # fireplace on the left wall
    FY = 3.6
    stone = M("stone")
    parts.append(wl("L", "hearth", 2.4, 1.0, 0.18, FY, 0.5, 0, M("stone_dark"), bevel=0.03, seg=1, wonk=0.02))
    for s in (-1, 1):
        parts.append(wl("L", "cheek", 0.45, 0.85, 1.5, FY + s * 0.95, 0.42, 0, stone, bevel=0.05, seg=1, wonk=0.03))
    parts.append(wl("L", "lintel", 2.4, 0.95, 0.45, FY, 0.47, 1.5, stone, bevel=0.06, seg=2, wonk=0.03))
    parts.append(wl("L", "mantel", 2.7, 1.05, 0.12, FY, 0.52, 1.95, M("beam"), bevel=0.03, seg=1, wonk=0.02))
    parts.append(wl("L", "fireback", 1.5, 0.1, 1.5, FY, 0.06, 0, M("coal", 0.9)))
    hood = taper_box("hood", (0.9, 2.2, H - 2.07), (-W / 2 + 0.45, FY, 2.07), M("limewash_b"), top=0.7, bevel=0.06, wonk=0.03)
    parts.append(hood)
    fire(parts, -W / 2 + 0.45, FY, 0.18, w=0.9)
    for k in range(3):
        parts.append(cyl("jug", 0.07, 0.2, (-W / 2 + 0.5, FY - 0.8 + k * 0.8, 2.07), M(("jar", "pewter", "brick_dark")[k], 0.5), verts=8, r2=0.05))
    col.append(wl("L", "c", 2.4, 1.0, H, FY, 0.5, 0))
    # four trestle tables with benches, pots and tankards
    for tx in (-2.0, 2.0):
        for ty in (2.9, 4.8):
            table(parts, col, tx, ty, L=1.5, w=0.8)
            for sx in (-1, 1):
                bench(parts, tx + sx * 0.62, ty, L=1.4)
            for k in range(3):
                tankard(parts, tx + RNG.uniform(-0.25, 0.25), ty + RNG.uniform(-0.6, 0.6), 0.78)
            plate(parts, tx + 0.15, ty - 0.3, 0.78)
            candle(parts, tx, ty + 0.1, 0.78, holder=True)
    # barrels by the door
    for (bx, by, bz) in ((4.3, 0.75, 0.0), (3.6, 0.6, 0.0), (4.0, 0.7, 0.85), (-4.3, 0.8, 0.0)):
        barrel(parts, bx, by, bz, r=0.32, h=0.85)
    col.append(box("c", (1.4, 0.9, 1.7), (4.0, 0.7, 0)))
    col.append(box("c", (0.7, 0.7, 0.85), (-4.3, 0.8, 0)))
    parts.append(box("crate", (0.6, 0.6, 0.5), (-3.6, 0.7, 0), M("wood", 0.8), bevel=0.03, seg=1, wonk=0.02))
    # windows either side of the door, and on the left wall by the fire
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 2.9, 1.1, w=1.0, h=1.3)
    fake_window(parts, "L", 6.4, 3.4, w=0.8, h=1.0)
    # hanging lanterns
    for (lx, ly) in ((-2.0, 3.85), (2.0, 3.85), (0.0, 1.6)):
        lantern(parts, lx, ly, H - 0.28, 3.1)
    lantern(parts, 0.6, 6.9, GZ - 0.2, 2.1)
    # antlers and a painted board over the fire for character
    parts.append(wl("F", "sign", 1.2, 0.05, 0.5, -2.9, 0.02, 3.0, M("canvas_stripe", 0.8), bevel=0.02, seg=1))
    post(-0.8, 7.05, math.pi)                                  # the karczmarz behind the bar
    for (tx, ty) in ((-2.0, 2.9), (2.0, 4.8), (-2.0, 4.8)):
        post_at(tx - 0.62, ty, tx, ty)                          # drinkers on the benches
        post_at(tx + 0.62, ty + 0.3, tx, ty)
    post_at(-3.6, 3.6, -W / 2, 3.6)                            # warming at the fire
    post_at(-2.8, 7.75, -2.8, 7.2, z=2.8)                      # up on the gallery
    finish_set("int_tavern", parts, col)


# ------------------------------------------------------------------ INT_SHOP (kram, 6 x 6 with a back room)
def int_shop():
    start()
    W, D, H = 6.0, 6.0, 3.4
    BX0, BX1, BD = 0.4, 3.0, 2.4        # back room behind the back wall: x from BX0 to BX1, depth BD
    parts, col = shell(W, D, H, "limewash", openings={"B": [(1.9, 1.0, 2.1, False)]})
    t = CTX["t"]
    # back room: floor, walls, ceiling
    parts.append(box("bslab", (BX1 - BX0 + t * 2, BD + t, 0.3), ((BX0 + BX1) / 2, D + t + BD / 2, -0.32), M("beam")))
    col.append(box("c", (BX1 - BX0 + t * 2, BD + t, 0.4), ((BX0 + BX1) / 2, D + t + BD / 2, -0.4)))
    parts.append(box("bceil", (BX1 - BX0 + t * 2, BD + t, 0.25), ((BX0 + BX1) / 2, D + t + BD / 2, H - 0.6)))
    parts[-1].data.materials.append(M("beam"))
    for (sz, loc) in (((t, BD + t, H), (BX0 - t / 2, D + t / 2 + BD / 2, 0)), ((t, BD + t, H), (BX1 + t / 2, D + t / 2 + BD / 2, 0)),
                      ((BX1 - BX0 + 2 * t, t, H), ((BX0 + BX1) / 2, D + t + BD, 0))):
        parts.append(box("bwall", sz, loc, M("limewash_b"), bevel=0, wonk=0.02, smooth=0))
        col.append(box("c", sz, loc))
    plank_floor(parts, BX0, BX1, D, D + t + BD, w=0.3)
    plank_floor(parts, -W / 2, W / 2, 0, D, w=0.26)
    ceiling_beams(parts, W, D, H, step=1.2, summer=False, drop=0.22)
    skirting(parts, "LRF", 0.8, "shutter")
    # parts of the back wall frame the doorway
    for s in (-1, 1):
        parts.append(wl("B", "bdjamb", 0.14, 0.1, 2.15, 1.9 + s * 0.57, 0.03, 0, M("timber"), bevel=0.02, seg=1))
    parts.append(wl("B", "bdlintel", 1.4, 0.12, 0.18, 1.9, 0.04, 2.1, M("timber"), bevel=0.02, seg=1))
    # counter across the room, merchant side toward the back
    parts.append(box("counter", (3.6, 0.6, 0.95), (-0.8, 3.1, 0), M("wood_dark"), bevel=0.04, seg=1, wonk=0.02))
    parts.append(box("ctop", (3.8, 0.75, 0.07), (-0.8, 3.1, 0.95), M("wood", 0.6), bevel=0.03, seg=1, wonk=0.01))
    for i in range(4):
        parts.append(box("cpanel", (0.7, 0.03, 0.55), (-2.2 + i * 0.93, 2.79, 0.2), M("wood", 0.8), bevel=0.01, seg=1))
    col.append(box("c", (3.8, 0.75, 1.02), (-0.8, 3.1, 0)))
    # scales on the counter
    brass = M("brass", 0.35)
    parts.append(box("sbase", (0.22, 0.14, 0.04), (-0.4, 3.1, 1.02), M("wood_dark")))
    parts.append(cyl("spost", 0.015, 0.42, (-0.4, 3.1, 1.06), brass, verts=6))
    parts.append(box("sbeam", (0.56, 0.02, 0.02), (-0.4, 3.1, 1.46), brass))
    for sx in (-1, 1):
        for a in (-1, 1):
            parts.append(cbox("sstring", (0.004, 0.004, 0.26), (-0.4 + sx * 0.27 + a * 0.04, 3.1, 1.34), brass, rot=(0, a * 0.15, 0)))
        parts.append(cyl("span", 0.09, 0.02, (-0.4 + sx * 0.27, 3.1, 1.2), brass, verts=10, r2=0.06))
    # goods on the counter: bolts, a basket, a ledger
    for i, c in enumerate(("cloth_blue", "crimson", "cloth_green")):
        parts.append(cyl("bolt", 0.09, 0.55, (-2.0 + i * 0.25, 3.05, 1.11), M(c, 0.9), verts=10, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(box("ledger", (0.3, 0.22, 0.05), (0.4, 3.15, 1.02), M("crimson", 0.8), bevel=0.01, seg=1))
    candle(parts, 0.75, 3.2, 1.02)
    # shelves behind the counter and along the left wall
    shelf_unit(parts, col, "B", -1.2, 3.2, 5, goods="mixed")
    shelf_unit(parts, col, "L", 4.4, 2.6, 4, goods="cloth")
    shelf_unit(parts, col, "R", 1.4, 1.8, 3, goods="jars", z0=0.5)
    # customer side: a sack or two and a barrel of something
    for (sx, sy) in ((-2.4, 0.9), (-2.0, 1.3)):
        parts.append(blob("sack", (0.45, 0.4, 0.62), (sx, sy, 0), M("sack", 0.95), subsurf=1, wonk=0.04))
    barrel(parts, 2.3, 0.9, 0.0, r=0.28, h=0.75)
    col.append(box("c", (0.6, 0.6, 0.75), (2.3, 0.9, 0)))
    # back room: crates, sacks, a candle
    for (cx, cy, cz, s) in ((1.0, D + 1.9, 0, 0.7), (1.0, D + 1.9, 0.7, 0.55), (2.4, D + 2.1, 0, 0.6), (1.9, D + 2.2, 0, 0.5)):
        parts.append(box("crate", (s, s, s), (cx, cy, cz), M("wood", 0.8), bevel=0.03, seg=1, wonk=0.02))
    col.append(box("c", (2.2, 0.8, 1.2), (1.7, D + 2.0, 0)))
    parts.append(blob("sack", (0.45, 0.4, 0.6), (2.6, D + 1.1, 0), M("sack", 0.95), subsurf=1, wonk=0.04))
    candle(parts, 2.4, D + 2.1, 0.6, holder=True)
    lamp("candle", (2.4, D + 1.9, 1.0))
    # display windows either side of the door
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 1.9, 0.9, w=1.1, h=1.4)
    lantern(parts, 0.0, 1.8, H - 0.22, 2.4)
    lantern(parts, -0.8, 4.4, H - 0.22, 2.4)
    finish_set("int_shop", parts, col)


# ------------------------------------------------------------------ INT_WORKSHOP (kuznia / warsztat, 8 x 6)
def int_workshop():
    start()
    W, D, H = 8.0, 6.0, 3.8
    parts, col = shell(W, D, H, "limewash_b")
    tile_floor(parts, -W / 2, W / 2, 0, D, s=0.8, checker=False, wonk=0.012)
    ceiling_beams(parts, W, D, H, step=1.5, summer=True)
    timber_frame(parts, "LRB", H, step=2.0, rail=None)
    skirting(parts, "LRBF", 0.6, "brick_dark")
    # forge in the back-left corner
    brick = M("brick")
    FX, FY = -2.6, 5.2
    parts.append(box("forge", (2.0, 1.4, 0.85), (FX, FY, 0), brick, bevel=0.05, seg=1, wonk=0.03))
    parts.append(box("forgetop", (2.1, 1.5, 0.1), (FX, FY, 0.85), M("stone_dark"), bevel=0.03, seg=1, wonk=0.02))
    parts.append(box("coals", (0.8, 0.6, 0.06), (FX, FY - 0.1, 0.95), EM("fire", 5.0)))
    for k in range(6):
        parts.append(blob("coal", (0.14, 0.12, 0.08), (FX + RNG.uniform(-0.35, 0.35), FY - 0.1 + RNG.uniform(-0.25, 0.25), 0.97), M("coal", 0.9), subsurf=1))
    lamp("fire", (FX, FY - 0.2, 1.3))
    parts.append(taper_box("fhood", (2.0, 1.4, 1.0), (FX, FY + 0.05, 1.9), M("brick_dark"), top=0.45, bevel=0.05, wonk=0.03))
    parts.append(box("flue", (0.9, 0.65, H - 2.9), (FX, FY + 0.2, 2.9), M("brick_dark"), bevel=0.04, seg=1, wonk=0.02))
    for s in (-1, 1):
        parts.append(box("fpost", (0.2, 0.2, 1.05), (FX + s * 0.9, FY - 0.55, 0.85), brick))
    col.append(box("c", (2.1, 1.5, H), (FX, FY, 0)))
    # bellows beside the forge
    parts.append(box("bellows", (0.5, 1.1, 0.25), (FX + 1.35, FY + 0.1, 0.9), M("brown_coat", 0.9), bevel=0.05, seg=2, wonk=0.02, rot=(0.25, 0, 0)))
    parts.append(box("bboard", (0.55, 1.15, 0.04), (FX + 1.35, FY + 0.1, 1.12), M("wood_dark"), rot=(0.25, 0, 0)))
    parts.append(box("bstand", (0.4, 0.4, 0.8), (FX + 1.35, FY + 0.1, 0), M("wood_dark"), bevel=0.02, seg=1))
    # anvil on its stump
    AX, AY = -1.6, 3.5
    parts.append(cyl("stump", 0.32, 0.5, (AX, AY, 0), M("wood", 0.9), verts=10, bevel=0.03, seg=1, wonk=0.02))
    iron = M("iron", 0.45)
    parts.append(taper_box("abase", (0.3, 0.22, 0.14), (AX, AY, 0.5), iron, top=0.7))
    parts.append(box("awaist", (0.16, 0.14, 0.12), (AX, AY, 0.64), iron))
    parts.append(box("aface", (0.46, 0.18, 0.1), (AX + 0.04, AY, 0.76), iron, bevel=0.015, seg=1))
    parts.append(cyl("ahorn", 0.07, 0.3, (AX - 0.33, AY, 0.81), iron, verts=10, r2=0.01, rot=(0, -math.pi / 2, 0), center=True))
    parts.append(box("hhead", (0.14, 0.05, 0.05), (AX + 0.1, AY + 0.03, 0.86), iron))
    parts.append(cbox("hhandle", (0.03, 0.34, 0.03), (AX + 0.1, AY - 0.15, 0.885), M("wood", 0.8)))
    col.append(cyl("c", 0.35, 0.86, (AX, AY, 0), None, verts=8))
    # quench tub
    parts.append(cyl("tub", 0.36, 0.5, (-3.4, 3.4, 0), M("wood", 0.8), verts=12, bevel=0.02, seg=1))
    parts.append(cyl("tubw", 0.32, 0.02, (-3.4, 3.4, 0.46), M("water", 0.05), verts=12))
    col.append(cyl("c", 0.36, 0.5, (-3.4, 3.4, 0), None, verts=8))
    # workbench along the right wall with a vice, a plane and shavings
    BY = 3.7
    parts.append(wl("R", "bench", 2.8, 0.8, 0.09, BY, 0.45, 0.82, M("wood", 0.7), bevel=0.03, seg=1, wonk=0.015))
    for s in (-1, 1):
        for nn in (0.15, 0.75):
            parts.append(wl("R", "bleg", 0.09, 0.09, 0.82, BY + s * 1.25, nn, 0, M("wood_dark")))
    parts.append(wl("R", "bshelf", 2.6, 0.7, 0.04, BY, 0.45, 0.2, M("wood", 0.8)))
    col.append(wl("R", "c", 2.8, 0.8, 0.91, BY, 0.45, 0))
    vx, vy = _wpos("R", BY - 1.0, 0.9)
    parts.append(box("vice", (0.12, 0.2, 0.2), (vx, vy, 0.8), iron))
    parts.append(cbox("vscrew", (0.25, 0.025, 0.025), (vx - 0.1, vy, 0.95), iron))
    px, py = _wpos("R", BY + 0.3, 0.5)
    parts.append(box("plane", (0.08, 0.3, 0.07), (px, py, 0.91), M("wood_dark"), bevel=0.01, seg=1))
    for k in range(5):
        sx, sy = _wpos("R", BY + RNG.uniform(-0.8, 0.8), RNG.uniform(0.3, 0.7))
        parts.append(blob("shaving", (0.06, 0.08, 0.02), (sx, sy, 0.91), M("canvas", 0.9), subsurf=1))
    # tool board over the bench
    parts.append(wl("R", "toolboard", 2.4, 0.04, 1.0, BY, 0.02, 1.35, M("plank_b", 0.8)))
    for k in range(7):
        u = BY - 1.0 + k * 0.33
        kind = k % 3
        if kind == 0:     # hammer
            parts.append(wl("R", "thandle", 0.03, 0.03, 0.34, u, 0.06, 1.55, M("wood", 0.8)))
            parts.append(wl("R", "thead", 0.14, 0.05, 0.05, u, 0.06, 1.89, iron))
        elif kind == 1:   # saw
            parts.append(wl("R", "tblade", 0.12, 0.01, 0.55, u, 0.05, 1.45, M("pewter", 0.3)))
            parts.append(wl("R", "tgrip", 0.1, 0.04, 0.12, u, 0.06, 2.0, M("wood", 0.8)))
        else:             # tongs
            for a in (-1, 1):
                sx, sy = _wpos("R", u, 0.06)
                parts.append(cbox("ttong", (0.02, 0.02, 0.6), (sx, sy, 1.75), iron, rot=(a * 0.08, 0, 0)))
    for k in range(5):     # horseshoes on the back wall by the forge
        sx, sy = _wpos("B", -0.9 + k * 0.22, 0.04)
        parts.append(torus("shoe", 0.07, 0.013, (sx, sy, 1.9), iron, rot=(math.pi / 2, 0, 0)))
    # wood pile in the front-right corner
    for row in range(3):
        for k in range(4 - row):
            y = 0.55 + (k + row * 0.5) * 0.26 + 0.1
            parts.append(cyl("log", 0.12, 1.1, (3.3, y, 0.12 + row * 0.22), M(("wood", "wood_dark", "timber")[RNG.randrange(3)], 0.9),
                             verts=8, rot=(0, math.pi / 2, 0), center=True, bevel=0.02, seg=1, wonk=0.01))
    col.append(box("c", (1.1, 1.2, 0.7), (3.3, 1.0, 0)))
    parts.append(cyl("block", 0.28, 0.45, (2.2, 1.2, 0), M("wood", 0.9), verts=10, bevel=0.02, seg=1))
    parts.append(cbox("axe_h", (0.035, 0.035, 0.6), (2.2, 1.25, 0.72), M("wood", 0.8), rot=(0.3, 0, 0)))
    parts.append(box("axe_b", (0.16, 0.03, 0.12), (2.2, 1.12, 0.42), iron))
    # iron stock leaning by the door, a lantern over the bench and one by the anvil
    for k in range(4):
        parts.append(cbox("bar", (0.03, 0.03, 1.4), (-3.7 + k * 0.06, 0.5, 0.68), iron, rot=(0, 0.15, 0)))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 2.4, 1.1, w=0.9, h=1.1)
    lantern(parts, 2.4, BY, H - 0.28, 2.3)
    lantern(parts, -0.6, 2.0, H - 0.28, 2.5)
    post_at(AX + 0.7, AY - 0.3, AX, AY)                        # at the anvil
    post_at(*_wpos("R", BY, 1.2), *_wpos("R", BY, 0.3))        # at the bench
    post_at(FX + 1.3, FY - 1.0, FX, FY)                        # minding the forge
    finish_set("int_workshop", parts, col)


# ------------------------------------------------------------------ INT_CHURCH (nave 12 x 24, starry blue vault)
def int_church():
    start()
    W, D, H = 12.0, 24.0, 10.0
    NICHES = (6.0, 12.0, 18.0)
    NW, NH, ND = 2.6, 4.6, 1.5
    AX = 3.6                   # arcade line (nave | aisle)
    parts, col = shell(W, D, H, "stone_pale", t=0.6, door_w=2.2, door_h=4.0, arched=True, ceiling=False, frame=False,
                       openings={"L": [(y, NW, NH, True) for y in NICHES], "R": [(y, NW, NH, True) for y in NICHES]})
    t = CTX["t"]
    tile_floor(parts, -W / 2, W / 2, 0, D, s=1.5)
    # flat ceiling over the aisles and a lid over everything (hidden above the vault)
    for sx in (-1, 1):
        parts.append(box("aceil", (W / 2 - AX + t, D + t, 0.3), (sx * (AX + (W / 2 - AX + t) / 2), D / 2, H), M("vault_blue")))
    parts.append(box("lid", (W + 2 * t, D + 2 * t, 0.3), (0, D / 2, H + AX + 0.4), M("vault_blue")))
    col.append(box("c", (W + 2 * t, D + 2 * t, 0.3), (0, D / 2, H)))
    # chapels: alcoves behind the niche openings, each with an altar, candles and a dark painting
    for sx in (-1, 1):
        xw = sx * (W / 2 + t)
        for y in NICHES:
            xc = xw + sx * ND / 2
            parts.append(box("nfloor", (ND, NW + 0.4, 0.3), (xc, y, -0.3), M("floor_stone_b")))
            parts.append(box("nback", (0.3, NW + 0.6, NH + 0.5), (xw + sx * (ND + 0.15), y, 0), M("limewash_b"), bevel=0, wonk=0.02, smooth=0))
            parts.append(box("nceil", (ND + 0.3, NW + 0.6, 0.3), (xc + sx * 0.15, y, NH), M("vault_blue")))
            for sy in (-1, 1):
                parts.append(box("nside", (ND, 0.3, NH + 0.3), (xc, y + sy * (NW / 2 + 0.15), 0), M("limewash_b")))
                col.append(box("c", (ND, 0.3, NH), (xc, y + sy * (NW / 2 + 0.15), 0)))
            col.append(box("c", (0.3, NW + 0.6, NH), (xw + sx * (ND + 0.15), y, 0)))
            ax = xw + sx * (ND - 0.35)
            parts.append(box("naltar", (0.6, 1.3, 0.95), (ax, y, 0), M("stone"), bevel=0.04, seg=1, wonk=0.02))
            parts.append(box("ncloth", (0.64, 1.36, 0.06), (ax, y, 0.95), M("linen", 0.9)))
            parts.append(box("nframe", (0.08, 1.2, 1.5), (xw + sx * (ND - 0.05), y, 1.5), MET("gold", 0.35), bevel=0.02, seg=1))
            parts.append(box("npaint", (0.06, 1.0, 1.3), (xw + sx * (ND - 0.1), y, 1.6), M(RNG.choice(("paint_dark", "altar_blue", "crimson")), 0.7)))
            for dy in (-0.45, 0.45):
                candle(parts, ax, y + dy, 1.01, h=0.25)
            lamp("candle", (ax - sx * 0.3, y, 1.5))
            # stone surround on the nave side of the opening
            for sy in (-1, 1):
                parts.append(box("npil", (0.2, 0.35, NH - NW / 2), (sx * (W / 2 - 0.08), y + sy * (NW / 2 + 0.12), 0), M("stone"), bevel=0.03, seg=1, wonk=0.01))
    # arcades: walls on the arcade line with pointed-ish round openings, columns in the piers
    ARC = (3.0, 7.0, 11.0, 15.0)
    AW, AHT = 3.2, 6.4
    y_end = 17.4
    for sx in (-1, 1):
        x = sx * AX
        o = box("arcade", (0.7, y_end - t / 2, H), (x, (t / 2 + y_end) / 2, 0), M("stone_pale"), bevel=0, wonk=0.015, smooth=0)
        cutters = []
        for y in ARC:
            cutters.append(box("cut", (2.0, AW, AHT - AW / 2 + 0.3), (x, y, -0.3)))
            cutters.append(cyl("cutc", AW / 2, 2.0, (x, y, AHT - AW / 2), verts=24, rot=(0, math.pi / 2, 0), center=True))
        cut(o, cutters)
        parts.append(o)
        # lintel over the chancel sides so the vault has something to stand on
        parts.append(box("chlintel", (0.7, D - y_end, H - AHT), (x, (y_end + D) / 2, AHT), M("stone_pale"), bevel=0, wonk=0.015, smooth=0))
        for y in (1.0, 5.0, 9.0, 13.0, 17.0):
            parts.append(cyl("column", 0.42, AHT - AW / 2 - 0.5, (x, y, 0.4), M("stone"), verts=16, r2=0.38, bevel=0.03, seg=1))
            parts.append(box("cbase", (1.0, 1.0, 0.4), (x, y, 0), M("stone_dark"), bevel=0.05, seg=1, wonk=0.01))
            parts.append(taper_box("ccap", (0.8, 0.8, 0.45), (x, y, AHT - AW / 2 - 0.1), M("stone"), top=1.35, bevel=0.04, seg=1))
            col.append(box("c", (0.9, 0.9, AHT), (x, y, 0)))
        for y in ARC:
            col.append(box("c", (0.7, AW, H - AHT + 0.2), (x, y, AHT - 0.2)))
        # clerestory-ish tall windows on the outer walls between the chapels
        side = "L" if sx < 0 else "R"
        for y in (3.0, 9.0, 15.0, 21.0):
            fake_window(parts, side, y, 4.8, w=1.2, h=3.8, arched=True, strength=0.9, sill=False, night=False)
    # starry vault over the nave: an inward-facing half cylinder springing from the arcade tops
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=AX, depth=D + t, location=(0, D / 2, H), rotation=(math.pi / 2, 0, 0), end_fill_type="NOTHING")
    v = bpy.context.object
    v.name = "vault"
    v.data.materials.append(M("vault_blue", 0.8))
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bm = bmesh.new()
    bm.from_mesh(v.data)
    bmesh.ops.delete(bm, geom=[vv for vv in bm.verts if vv.co.z < H - 0.01], context="VERTS")
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(v.data)
    bm.free()
    bpy.ops.object.shade_smooth()
    parts.append(v)
    for k in range(9):          # transverse ribs
        y = 1.0 + k * (D - 2.0) / 8
        for a in range(8):
            a0 = math.pi * a / 8 + math.pi / 16
            parts.append(cbox("rib", (0.35, 0.3, AX * math.pi / 8 + 0.05), (AX * 0.97 * math.cos(a0), y, H + AX * 0.97 * math.sin(a0)), M("stone"), rot=(0, -a0, 0)))
    for k in range(70):         # gold stars
        a = RNG.uniform(0.2, math.pi - 0.2)
        y = RNG.uniform(0.8, D - 0.8)
        parts.append(sphere("star", 0.09, (AX * 0.985 * math.cos(a), y, H + AX * 0.985 * math.sin(a)), EM("star", 2.0, 0.3), seg=6, rings=3))
    # sanctuary: two steps, altar, gilded triptych retable (a nod to Stoss), candles
    parts.append(box("step1", (W, D - 18.8, 0.18), (0, (18.8 + D) / 2, 0), M("stone"), bevel=0.03, seg=1, wonk=0.01))
    parts.append(box("step2", (W, D - 19.5, 0.18), (0, (19.5 + D) / 2, 0.18), M("stone_pale"), bevel=0.03, seg=1, wonk=0.01))
    col.append(prism("c", -W / 2, W / 2, 18.4, 18.8, 0, 0.18))
    col.append(box("c", (W, D - 18.8, 0.18), (0, (18.8 + D) / 2, 0)))
    col.append(box("c", (W, D - 19.5, 0.36), (0, (19.5 + D) / 2, 0)))
    AY = 21.8
    parts.append(box("altar", (2.6, 1.1, 1.0), (0, AY, 0.36), M("stone"), bevel=0.05, seg=1, wonk=0.02))
    parts.append(box("antep", (2.2, 0.04, 0.8), (0, AY - 0.57, 0.44), M("crimson", 0.7)))
    parts.append(box("aclth", (2.7, 1.2, 0.05), (0, AY, 1.36), M("linen", 0.9)))
    col.append(box("c", (2.7, 1.2, 1.4), (0, AY, 0.36)))
    # the sanctuary lamp: red glass in a silver-gilt cup on a long chain before the altar
    parts.append(cyl("slchain", 0.008, 7.5, (1.8, AY - 1.4, 2.8), MET("gold", 0.3), verts=4))
    parts.append(cyl("slcup", 0.12, 0.2, (1.8, AY - 1.4, 2.6), MET("gold", 0.3), verts=10, r2=0.16))
    parts.append(cyl("slglass", 0.07, 0.1, (1.8, AY - 1.4, 2.78), EM("icon_red", 3.0, 0.3), verts=10))
    lamp("sanctuary", (1.8, AY - 1.4, 2.7))
    for k in range(6):
        x = -1.1 + k * 0.44
        candle(parts, x, AY + 0.3, 1.41, h=0.3 + (0.1 if k in (2, 3) else 0.0))
    parts.append(box("crucifix", (0.05, 0.05, 0.7), (0, AY + 0.3, 1.41), MET("gold", 0.3)))
    parts.append(box("crucifix", (0.35, 0.05, 0.05), (0, AY + 0.3, 1.9), MET("gold", 0.3)))
    lamp("candle", (0, AY - 0.4, 2.0))
    gold = MET("gold", 0.3)
    RY = D - 0.35
    parts.append(box("retable", (3.0, 0.5, 5.2), (0, RY, 0.36 + 1.6), gold, bevel=0.06, seg=1))
    parts.append(box("predella", (3.4, 0.6, 1.6), (0, RY, 0.36), M("altar_blue", 0.6), bevel=0.04, seg=1))
    parts.append(box("rinner", (2.5, 0.1, 4.4), (0, RY - 0.25, 2.3), M("altar_blue", 0.6)))
    for k in range(5):
        parts.append(blob("figure", (0.35, 0.25, 1.4 if k == 2 else 1.1), (-0.95 + k * 0.475, RY - 0.35, 2.6), gold, subsurf=1))
    for sx in (-1, 1):
        parts.append(box("wing", (1.5, 0.12, 4.4), (sx * 2.3, RY - 0.4, 2.3), gold, rot=(0, 0, sx * -0.35), bevel=0.04, seg=1))
        parts.append(box("wingp", (1.2, 0.05, 3.9), (sx * 2.3, RY - 0.5, 2.55), M("altar_blue", 0.6), rot=(0, 0, sx * -0.35)))
    for k in range(3):
        parts.append(cyl("pinnacle", 0.25, 1.6, (-1.0 + k, RY, 7.16), gold, verts=8, r2=0.02))
    col.append(box("c", (5.4, 1.2, 7.0), (0, RY - 0.2, 0.36)))
    for sx in (-1, 1):   # big floor candelabra flanking the altar
        x = sx * 2.2
        parts.append(cyl("cand_base", 0.25, 0.1, (x, 20.6, 0.36), M("brass", 0.35), verts=10))
        parts.append(cyl("cand_shaft", 0.04, 1.5, (x, 20.6, 0.46), M("brass", 0.35), verts=8))
        candle(parts, x, 20.6, 1.96, h=0.4, r=0.04, holder=False)
        lamp("candle", (x, 20.6, 2.6))
        col.append(cyl("c", 0.25, 2.0, (x, 20.6, 0.36), None, verts=8))
    # pews in two blocks facing the altar
    for k in range(10):
        y = 3.0 + k * 1.2
        for sx in (-1, 1):
            xc = sx * 1.9
            L = 2.3
            p = [box("pseat", (L, 0.42, 0.06), (0, 0, 0.44), M("pew", 0.7)),
                 box("pback", (L, 0.06, 0.55), (0, -0.24, 0.5), M("pew", 0.7), bevel=0.02, seg=1),
                 box("pkneel", (L, 0.16, 0.1), (0, 0.42, 0.1), M("pew", 0.8))]
            for ex in (-1, 1):
                p.append(box("pend", (0.07, 0.6, 1.0), (ex * (L / 2 + 0.035), -0.05, 0), M("wood_dark")))
            parts.append(place(p, xc, y, 0.0))
            col.append(box("c", (L + 0.14, 0.62, 1.0), (xc, y - 0.05, 0)))
    # hanging lanterns down the nave, a font by the door
    for y in (4.0, 10.0, 16.0):
        lantern(parts, 0, y, H + AX - 0.1, 5.2, kind="chandelier")
    parts.append(cyl("font", 0.45, 0.9, (-2.2, 1.6, 0), M("stone"), verts=12, r2=0.55, bevel=0.03, seg=1))
    parts.append(cyl("fontw", 0.46, 0.02, (-2.2, 1.6, 0.89), M("water", 0.05), verts=12))
    col.append(cyl("c", 0.55, 0.9, (-2.2, 1.6, 0), None, verts=8))
    # rose window over the door
    parts.append(torus("rose", 1.5, 0.15, (0, t / 2 + 0.1, 7.2), M("stone"), rot=(math.pi / 2, 0, 0)))
    parts.append(cyl("roseg", 1.4, 0.05, (0, t / 2 + 0.05, 7.2), EM("moon_glass", 0.9, 0.2), verts=24, rot=(math.pi / 2, 0, 0), center=True))
    for a in range(4):
        parts.append(cbox("rosebar", (2.8, 0.05, 0.08), (0, t / 2 + 0.12, 7.2), M("stone"), rot=(0, a * math.pi / 4, 0)))
    gold = MET("gold", 0.3)
    # the pulpit on the north arcade column: tub, back panel, sounding board with its gilt crest, stair from the aisle
    PX, PY = -2.95, 13.0
    parts.append(cyl("ptub", 0.55, 1.0, (PX, PY, 2.1), M("pew", 0.6), verts=8, bevel=0.02, seg=1))
    parts.append(cyl("prail", 0.6, 0.08, (PX, PY, 3.1), gold, verts=8))
    parts.append(cyl("pcone", 0.1, 0.8, (PX, PY, 1.3), gold, verts=8, r2=0.55))
    for k in range(8):
        a = math.tau * (k + 0.5) / 8
        parts.append(cbox("ppanel", (0.3, 0.02, 0.6), (PX + 0.555 * math.cos(a), PY + 0.555 * math.sin(a), 2.55), gold, rot=(0, 0, a + math.pi / 2)))
    parts.append(box("pback", (0.12, 0.8, 1.4), (-3.45, PY, 3.1), M("pew", 0.6), bevel=0.02, seg=1))
    parts.append(cyl("pboard", 0.8, 0.15, (PX - 0.1, PY, 4.5), M("pew", 0.6), verts=12, bevel=0.03, seg=1))
    parts.append(cyl("pvalance", 0.82, 0.12, (PX - 0.1, PY, 4.38), gold, verts=12))
    parts.append(cyl("pcrest", 0.3, 0.6, (PX - 0.1, PY, 4.65), gold, verts=8, r2=0.02))
    parts.append(sphere("pdove", 0.1, (PX - 0.1, PY, 4.36), gold, seg=8, rings=4))
    for i in range(8):
        parts.append(box("pstep", (0.8, 0.3, 0.06), (-4.45, PY + 2.3 - i * 0.25, 0.25 * (i + 1) - 0.06), M("pew", 0.7)))
        parts.append(box("pstring", (0.06, 0.3, 0.25 * (i + 1)), (-4.05, PY + 2.3 - i * 0.25, 0.0), M("pew", 0.7)))
    parts.append(cbox("psrail", (0.05, 2.4, 0.05), (-4.02, PY + 1.4, 1.9), gold, rot=(-0.72, 0, 0)))
    col.append(box("c", (0.9, 2.2, 1.0), (-4.45, PY + 1.4, 0)))
    # the confessional in the south aisle between two chapels
    CX, CY = W / 2 - 0.5, 9.0
    p = [box("cbooth", (1.0, 0.9, 2.5), (0, 0, 0), M("pew", 0.6), bevel=0.02, seg=1),
         box("cdoor", (0.7, 0.04, 1.8), (0, -0.46, 0.1), M("wood_dark"), bevel=0.01, seg=1),
         box("cgrate", (0.5, 0.05, 0.4), (0, -0.47, 1.4), M("coal", 0.8)),
         box("ccrown", (2.6, 1.0, 0.25), (0, 0.05, 2.5), gold, bevel=0.04, seg=1),
         cyl("ccrest", 0.25, 0.5, (0, -0.1, 2.75), gold, verts=8, r2=0.02)]
    for k in range(4):
        p.append(box("cgbar", (0.02, 0.06, 0.4), (-0.18 + k * 0.12, -0.48, 1.4), gold))
    for sx in (-1, 1):
        p.append(box("cwing", (0.8, 0.9, 2.1), (sx * 0.9, 0.05, 0), M("pew", 0.6), bevel=0.02, seg=1))
        p.append(box("ccurt", (0.6, 0.05, 1.6), (sx * 0.9, -0.42, 0.3), M("crimson", 0.9), bevel=0.02, seg=1, wonk=0.03))
        p.append(box("ckneel", (0.6, 0.3, 0.15), (sx * 0.9, -0.55, 0), M("pew", 0.8)))
    parts.append(place(p, CX, CY, math.pi / 2))
    col.append(box("c", (1.0, 2.6, 2.6), (CX, CY, 0)))
    # side altars on the chancel step at the heads of the aisles, retables with their paintings
    for sx in (-1, 1):
        ax, ay = sx * 4.9, 19.5
        parts.append(box("saltar", (1.4, 0.7, 0.95), (ax, ay, 0.36), M("stone"), bevel=0.03, seg=1, wonk=0.01))
        parts.append(box("scloth", (1.46, 0.76, 0.05), (ax, ay, 1.31), M("linen", 0.9)))
        parts.append(box("santep", (1.2, 0.03, 0.7), (ax, ay - 0.36, 0.44), M("altar_blue" if sx < 0 else "crimson", 0.7)))
        parts.append(box("sretable", (1.4, 0.2, 2.6), (ax, ay + 0.35, 1.36), gold, bevel=0.03, seg=1))
        parts.append(box("spaint", (1.0, 0.05, 1.7), (ax, ay + 0.22, 1.6), M("paint_dark", 0.6)))
        parts.append(blob("sfigure", (0.35, 0.03, 0.9), (ax, ay + 0.19, 1.9), M("altar_blue" if sx < 0 else "icon_red", 0.6), subsurf=1))
        parts.append(sphere("shalo", 0.13, (ax, ay + 0.18, 2.95), gold, seg=8, rings=4))
        parts.append(cyl("spinn", 0.2, 0.7, (ax, ay + 0.35, 3.96), gold, verts=8, r2=0.02))
        for dx in (-0.5, 0.5):
            candle(parts, ax + dx, ay - 0.1, 1.36, h=0.25)
        lamp("candle", (ax, ay - 0.6, 1.9))
        col.append(box("c", (1.4, 0.9, 3.0), (ax, ay + 0.1, 0.36)))
    # votive candles on an iron stand before the Virgin's altar
    VX, VY = -4.9, 18.1
    parts.append(cbox("vrack", (1.1, 0.5, 0.04), (VX, VY, 0.95), M("iron", 0.5), rot=(0.35, 0, 0)))
    parts.append(box("vstand", (0.06, 0.06, 0.9), (VX - 0.45, VY, 0), M("iron", 0.5)))
    parts.append(box("vstand", (0.06, 0.06, 0.9), (VX + 0.45, VY, 0), M("iron", 0.5)))
    parts.append(box("vbox", (0.25, 0.2, 0.3), (VX + 0.7, VY - 0.1, 0), M("wood_dark")))
    for i in range(3):
        for j in range(9):
            if RNG.random() < 0.2:
                continue
            x = VX - 0.48 + j * 0.12
            y = VY - 0.18 + i * 0.16
            z = 0.93 + (y - (VY - 0.18)) * 0.36 + 0.04
            parts.append(cyl("votive", 0.022, 0.05, (x, y, z), M("icon_red", 0.4), verts=6))
            parts.append(cyl("vflame", 0.008, 0.03, (x, y, z + 0.05), EM("flame", 8.0), verts=4, r2=0.0))
    lamp("candle", (VX, VY - 0.3, 1.3))
    col.append(box("c", (1.1, 0.6, 1.1), (VX, VY, 0)))
    post(0.0, 20.9, 0.0, z=0.36)                               # the priest at the high altar
    post_at(-4.9, 17.3, -4.9, 18.1)                            # lighting a votive candle
    post_at(CX - 1.0, CY - 0.9, CX, CY - 0.9)                  # a penitent kneeling at the confessional
    for (px, py) in ((-1.9, 6.6), (1.9, 9.0), (-1.9, 11.4), (1.9, 4.2)):
        post(px, py, 0.0)                                       # at prayer in the pews
    post_at(-1.4, 1.2, 0.0, 0.0)                               # a beggar by the font
    finish_set("int_church", parts, col)


# ------------------------------------------------------------------ INT_SALON (10 x 8, parquet and panelling)
def harpsichord(parts, col, x, y, rot):
    """Wing-shaped case on turned legs, keyboard at the front (-Y), lid propped up."""
    outline = [(-0.46, 0.0), (0.46, 0.0), (0.46, 0.5), (0.30, 1.1), (0.10, 1.7), (-0.16, 2.1), (-0.46, 2.2)]
    bm = bmesh.new()
    lo = [bm.verts.new((px, py, 0.72)) for (px, py) in outline]
    hi = [bm.verts.new((px, py, 0.98)) for (px, py) in outline]
    bm.faces.new(list(reversed(lo)))
    bm.faces.new(hi)
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("harpsi")
    bm.to_mesh(me)
    bm.free()
    case = bpy.data.objects.new("harpsi", me)
    bpy.context.collection.objects.link(case)
    case.data.materials.append(M("shutter", 0.5))
    finish(case, bevel=0.02, seg=1, smooth=30)
    p = [case]
    for (lx, ly) in ((-0.38, 0.1), (0.38, 0.1), (-0.38, 2.05), (0.3, 0.6), (0.0, 1.6)):
        p.append(cyl("hleg", 0.035, 0.72, (lx, ly, 0), MET("gold", 0.35), verts=8, r2=0.025))
    p.append(box("keys", (0.8, 0.18, 0.03), (0, -0.05, 0.84), M("linen", 0.4)))
    for k in range(10):
        p.append(box("bkey", (0.02, 0.1, 0.02), (-0.36 + k * 0.08, -0.01, 0.87), M("black", 0.4)))
    p.append(box("lid", (0.9, 1.9, 0.02), (0.0, 1.1, 0.98), M("shutter", 0.5), rot=(0, -0.7, 0)))
    edit_verts(p[-1], lambda co: setattr(co, "x", co.x + 0.35))
    p.append(box("lidstick", (0.02, 0.02, 0.5), (0.25, 1.1, 0.98), M("wood", 0.7)))
    p.append(box("gilt", (0.94, 0.02, 0.06), (0, 0.0, 0.92), MET("gold", 0.35)))
    parts.append(place(p, x, y, rot))
    col.append(place([box("c", (0.95, 2.2, 1.0), (0, 1.1, 0))], x, y, rot))


def settee(parts, col, x, y, rot, L=1.8):
    wm = MET("gold", 0.4)
    up = M("velvet", 0.9)
    p = [box("sframe", (L, 0.7, 0.3), (0, 0, 0.12), M("wood_dark"), bevel=0.03, seg=1),
         blob("scush", (L - 0.2, 0.62, 0.16), (0, -0.02, 0.4), up, subsurf=1, bevel=0.03),
         blob("sback", (L - 0.1, 0.16, 0.6), (0, 0.3, 0.42), up, subsurf=1, bevel=0.03),
         box("screst", (L, 0.08, 0.06), (0, 0.32, 1.0), wm, bevel=0.02, seg=1)]
    for sx in (-1, 1):
        p.append(box("sarm", (0.12, 0.66, 0.35), (sx * (L / 2 - 0.06), 0, 0.42), up, bevel=0.04, seg=1))
        for sy in (-1, 1):
            p.append(cyl("sleg", 0.03, 0.12, (sx * (L / 2 - 0.1), sy * 0.28, 0), wm, verts=6))
    parts.append(place(p, x, y, rot))
    col.append(place([box("c", (L, 0.75, 0.9), (0, 0.02, 0))], x, y, rot))


def panel_frame(parts, side, u, z, w, h, n=0.04, mat="panel_trim", t=0.06):
    parts.append(wl(side, "pf", w, 0.03, t, u, n, z, M(mat, 0.6)))
    parts.append(wl(side, "pf", w, 0.03, t, u, n, z + h - t, M(mat, 0.6)))
    parts.append(wl(side, "pf", t, 0.03, h, u - w / 2 + t / 2, n, z, M(mat, 0.6)))
    parts.append(wl(side, "pf", t, 0.03, h, u + w / 2 - t / 2, n, z, M(mat, 0.6)))


def int_salon():
    start()
    W, D, H = 10.0, 8.0, 4.2
    parts, col = shell(W, D, H, "panel", ceil_mat="panel_trim", door_w=1.4, door_h=2.5, frame=False)
    # parquet: two woods in a checker of squares, each square split into three strips
    tile_floor(parts, -W / 2, W / 2, 0, D, s=0.8, mats=("parquet_a", "parquet_b"))
    # dado panelling, framed upper panels, cornice
    for side in "LRBF":
        L = W if side in "FB" else D
        u0 = -L / 2 if side in "FB" else 0.0
        parts.append(wl(side, "dado", L, 0.05, 0.95, u0 + L / 2, 0.02, 0, M("damask", 0.7)))
        parts.append(wl(side, "dadorail", L, 0.09, 0.08, u0 + L / 2, 0.04, 0.95, M("panel_trim", 0.6)))
        parts.append(wl(side, "skirt", L, 0.08, 0.16, u0 + L / 2, 0.04, 0, M("panel_trim", 0.6)))
        parts.append(wl(side, "cornice", L, 0.22, 0.26, u0 + L / 2, 0.1, H - 0.26, M("panel_trim", 0.6), bevel=0.05, seg=1))
        n = int(L / 2.0)
        for i in range(n):
            u = u0 + L * (i + 0.5) / n
            if side == "F" and abs(u) < 1.2:
                continue
            if side == "R" and abs(u - D / 2) < 1.4:
                continue   # mirror goes here
            if side == "L" and any(abs(u - wy) < 0.9 for wy in (2.4, 5.6)):
                continue   # windows
            panel_frame(parts, side, u, 1.35, L / n - 0.6, H - 2.0)
            panel_frame(parts, side, u, 0.2, L / n - 0.6, 0.6, mat="panel_trim")
    parts.append(box("dcorn", (W, D, 0.02), (0, D / 2, H - 0.02), M("panel_trim", 0.6)))
    parts.append(cyl("rosette", 0.6, 0.06, (0, D / 2, H - 0.06), M("panel_trim", 0.6), verts=16, bevel=0.02, seg=1))
    # door surround
    for sx in (-1, 1):
        parts.append(box("dpil", (0.2, 0.1, 2.6), (sx * 0.85, CTX["t"] / 2 + 0.05, 0), M("panel_trim", 0.6), bevel=0.02, seg=1))
    parts.append(box("dped", (2.0, 0.16, 0.3), (0, CTX["t"] / 2 + 0.08, 2.6), M("panel_trim", 0.6), bevel=0.03, seg=1))
    # windows on the left wall with velvet curtains
    for wy in (2.4, 5.6):
        fake_window(parts, "L", wy, 1.0, w=1.1, h=2.2, strength=0.7)
        for s in (-1, 1):
            parts.append(wl("L", "curtain", 0.45, 0.14, 3.0, wy + s * 0.8, 0.2, 0.05, M("velvet", 0.9), bevel=0.05, seg=1, wonk=0.04))
        parts.append(wl("L", "pelmet", 2.1, 0.2, 0.35, wy, 0.2, 3.35, MET("gold", 0.4), bevel=0.03, seg=1))
    # marble fireplace on the right wall, mirror above it
    MY = D / 2
    marble = M("marble", 0.25)
    for s in (-1, 1):
        parts.append(wl("R", "fcheek", 0.3, 0.45, 1.1, MY + s * 0.65, 0.22, 0, marble, bevel=0.03, seg=1))
    parts.append(wl("R", "flintel", 1.6, 0.45, 0.22, MY, 0.22, 1.1, marble, bevel=0.03, seg=1))
    parts.append(wl("R", "fmantel", 1.9, 0.55, 0.07, MY, 0.27, 1.32, marble, bevel=0.02, seg=1))
    parts.append(wl("R", "fback", 1.0, 0.05, 1.1, MY, 0.02, 0, M("coal", 0.9)))
    parts.append(wl("R", "fhearth", 2.0, 0.8, 0.05, MY, 0.4, 0, marble))
    fx, fy = _wpos("R", MY, 0.25)
    fire(parts, fx, fy, 0.06, w=0.6, strength=8.0)
    col.append(wl("R", "c", 1.9, 0.6, 1.4, MY, 0.3, 0))
    parts.append(wl("R", "mframe", 1.4, 0.06, 2.0, MY, 0.03, 1.5, MET("gold", 0.35), bevel=0.03, seg=1))
    parts.append(wl("R", "mirror", 1.2, 0.02, 1.8, MY, 0.07, 1.6, MET("mirror", 0.04)))
    parts.append(wl("R", "mcrest", 0.8, 0.08, 0.3, MY, 0.04, 3.45, MET("gold", 0.35), bevel=0.04, seg=1))
    for s in (-1, 1):
        cx, cy = _wpos("R", MY + s * 0.7, 0.3)
        candle(parts, cx, cy, 1.39, h=0.2)
    cx, cy = _wpos("R", MY, 0.3)
    parts.append(box("clock", (0.14, 0.3, 0.35), (cx, cy, 1.39), MET("gold", 0.35), bevel=0.03, seg=1))
    # chandelier
    CZ = H - 1.3
    gold = MET("gold", 0.35)
    parts.append(cyl("cstem", 0.02, 1.0, (0, MY, CZ + 0.3), gold, verts=6))
    parts.append(sphere("cball", 0.12, (0, MY, CZ + 0.1), gold, seg=10, rings=6))
    parts.append(torus("cring", 0.55, 0.025, (0, MY, CZ), gold))
    for k in range(8):
        a = math.tau * k / 8
        cx, cy = 0.55 * math.cos(a), MY + 0.55 * math.sin(a)
        parts.append(cbox("carm", (0.55, 0.02, 0.02), (0.27 * math.cos(a), MY + 0.27 * math.sin(a), CZ + 0.05), gold, rot=(0, 0, a)))
        candle(parts, cx, cy, CZ, h=0.14, r=0.018, holder=False)
        parts.append(sphere("drop", 0.03, (0.45 * math.cos(a + 0.4), MY + 0.45 * math.sin(a + 0.4), CZ - 0.12), M("mirror", 0.05), seg=6, rings=4))
    lamp("chandelier", (0, MY, CZ + 0.2))
    # card table with four chairs, cards and a candlestick
    TX, TY = -1.6, 3.2
    parts.append(cyl("ctop", 0.55, 0.05, (TX, TY, 0.72), M("wood_dark", 0.5), verts=16, bevel=0.015, seg=1))
    parts.append(cyl("cbaize", 0.5, 0.01, (TX, TY, 0.77), M("baize", 0.95), verts=16))
    parts.append(cyl("cped", 0.06, 0.7, (TX, TY, 0.02), M("wood_dark"), verts=8, r2=0.04))
    parts.append(cyl("cfoot", 0.3, 0.04, (TX, TY, 0), M("wood_dark"), verts=10))
    for k in range(9):
        parts.append(box("card", (0.06, 0.09, 0.004), (TX + RNG.uniform(-0.3, 0.3), TY + RNG.uniform(-0.3, 0.3), 0.78), M("linen", 0.6), rot=(0, 0, RNG.uniform(0, 3))))
    candle(parts, TX + 0.1, TY + 0.05, 0.78)
    lamp("candle", (TX, TY, 1.3))
    col.append(cyl("c", 0.55, 0.77, (TX, TY, 0), None, verts=8))
    for k in range(4):
        a = math.tau * k / 4 + math.pi / 4
        chair(parts, TX + 0.85 * math.cos(a), TY + 0.85 * math.sin(a), a - math.pi / 2, fancy=True)
    # the pianoforte in the back-left corner (a Viennese grand, wing-shaped like the old harpsichord), a music desk
    # and two candles on it; settees by the fire and along the back wall
    harpsichord(parts, col, -3.0, 5.2, 0.0)
    parts.append(cbox("musicdesk", (0.62, 0.02, 0.3), (-3.0, 5.32, 1.13), M("shutter", 0.5), rot=(0.3, 0, 0)))
    for k in range(2):
        parts.append(cbox("music", (0.24, 0.005, 0.3), (-3.13 + k * 0.26, 5.3, 1.14), M("paper", 0.9), rot=(0.3, 0, (k - 0.5) * 0.1)))
        for j in range(5):
            parts.append(cbox("stave", (0.2, 0.004, 0.004), (-3.13 + k * 0.26, 5.295, 1.05 + j * 0.05), M("ink", 0.9), rot=(0.3, 0, 0)))
    for sx in (-1, 1):
        candle(parts, -3.0 + sx * 0.36, 5.28, 0.98, h=0.16)
    chair(parts, -3.0, 4.6, 0.0 + math.pi, fancy=True)
    parts[-1].name = "hstool"
    settee(parts, col, 1.5, D - 0.5, math.pi)
    settee(parts, col, 2.6, MY, -math.pi / 2, L=1.6)
    chair(parts, 4.0, MY - 1.4, -math.pi / 2 - 0.5, fancy=True)
    chair(parts, 4.0, MY + 1.4, -math.pi / 2 + 0.5, fancy=True)
    parts.append(cyl("sidetable", 0.3, 0.7, (4.3, D - 0.6, 0), M("wood_dark"), verts=10, r2=0.1))
    parts.append(cyl("sidetop", 0.32, 0.04, (4.3, D - 0.6, 0.7), M("marble", 0.25), verts=12))
    parts.append(cyl("vase", 0.1, 0.35, (4.3, D - 0.6, 0.74), M("plaster_blue", 0.3), verts=10, r2=0.06))
    # portrait on the back wall over the settee
    parts.append(wl("B", "portframe", 1.3, 0.08, 1.6, 1.5, 0.04, 1.6, MET("gold", 0.35), bevel=0.03, seg=1))
    parts.append(wl("B", "portrait", 1.1, 0.05, 1.4, 1.5, 0.08, 1.7, M("paint_dark", 0.6)))
    parts.append(blob("sitter", (0.4, 0.05, 0.6), _wpos("B", 1.5, 0.11) + (1.95,), M("plaster_rose", 0.6), subsurf=1))
    # more portraits: the King in crimson over the pianoforte, the host's family on the right wall
    portrait(parts, "B", -3.0, 1.9, w=0.9, h=1.15, coat="crimson", n=0.04)
    portrait(parts, "B", 4.0, 1.7, w=0.6, h=0.8, sitter="plaster_rose", coat="cloth_blue", n=0.04)
    portrait(parts, "R", 1.5, 1.7, w=0.7, h=0.9, coat="navy", n=0.04)
    portrait(parts, "R", 6.5, 1.7, w=0.7, h=0.9, coat="green_coat", n=0.04)
    # the reading desk against the front wall: the Constitution of the Third of May open on its stand
    RX = 3.4
    ry = CTX["t"] / 2 + 0.32
    parts.append(box("rdesk", (1.2, 0.6, 0.76), (RX, ry, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("rdtop", (1.26, 0.64, 0.04), (RX, ry, 0.76), M("wood", 0.5)))
    for k in range(2):
        parts.append(box("rdrawer", (0.5, 0.02, 0.18), (RX - 0.28 + k * 0.56, ry - 0.31, 0.5), M("wood", 0.6), bevel=0.01, seg=1))
    col.append(box("c", (1.26, 0.64, 0.8), (RX, ry, 0)))
    parts.append(cbox("rstand", (0.7, 0.44, 0.03), (RX, ry + 0.02, 0.92), M("wood_dark"), rot=(-0.45, 0, 0)))
    for sx in (-1, 1):
        parts.append(cbox("cpage", (0.32, 0.4, 0.012), (RX + sx * 0.165, ry + 0.0, 0.945), M("paper", 0.85), rot=(-0.45, 0, sx * -0.04)))
        parts.append(cbox("ctitle", (0.2, 0.05, 0.004), (RX + sx * 0.165, ry + 0.13, 1.01), M("crimson" if sx < 0 else "ink", 0.9), rot=(-0.45, 0, 0)))
        for j in range(9):
            parts.append(cbox("cline", (0.24, 0.006, 0.003), (RX + sx * 0.165, ry + 0.08 - j * 0.03, 0.99 - j * 0.013), M("ink", 0.9), rot=(-0.45, 0, 0)))
    parts.append(cyl("seal", 0.035, 0.01, (RX + 0.05, ry - 0.2, 0.8), M("crimson", 0.5), verts=10))
    parts.append(box("ribbon", (0.02, 0.2, 0.004), (RX + 0.05, ry - 0.1, 0.8), M("crimson", 0.7)))
    parts.append(cyl("inkstand", 0.05, 0.05, (RX + 0.45, ry - 0.1, 0.8), MET("pewter", 0.2), verts=10))
    parts.append(cbox("quill", (0.01, 0.01, 0.28), (RX + 0.46, ry - 0.09, 0.96), M("paper", 0.9), rot=(0.3, -0.3, 0)))
    candle(parts, RX - 0.5, ry - 0.1, 0.8)
    lamp("candle", (RX - 0.3, ry + 0.3, 1.5))
    chair(parts, RX, ry + 0.75, math.pi, fancy=True)
    # standing girandoles in the corners
    for (gx, gy) in ((-4.5, 0.7), (4.6, 0.8), (4.6, 6.6)):
        candelabrum(parts, col, gx, gy, h=1.6)
    post(0.8, 4.6, math.pi)                                  # Pani Zofia (data/missions.json hostess_inside)
    for k in range(4):
        a = math.tau * k / 4 + math.pi / 4
        post_at(TX + 0.85 * math.cos(a), TY + 0.85 * math.sin(a), TX, TY)   # guests at cards
    post(-3.0, 4.6, 0.0)                                     # at the pianoforte
    post_at(RX, ry + 0.75, RX, ry)                           # reading the Constitution
    post_at(2.6, MY, 0.0, MY)                                # on the settee by the fire
    post_at(4.0, MY - 1.4, 4.9, MY)                          # warming at the fire
    post_at(1.5, D - 0.5, 1.5, 0.0)                          # on the back settee
    finish_set("int_salon", parts, col)


# ------------------------------------------------------------------ TRADES: shops and workshops behind the Rynek doors
def int_shop_baker():
    """Piekarz: a brick bake-oven with a glowing mouth, the dough trough, loaves and obwarzanki, flour everywhere."""
    start()
    W, D, H = 6.5, 6.0, 3.4
    parts, col = room(W, D, H, "limewash_b", "brick", "beams", skirt=("plinth", 0.6))
    # oven against the back wall, left: brick mass, dome, hood, glowing arched mouth, ash pit, ledge
    OX = -1.5
    parts.append(wl("B", "oven", 2.8, 1.5, 1.75, OX, 0.75, 0, M("brick"), bevel=0.05, seg=1, wonk=0.03))
    parts.append(wl("B", "ovtop", 2.6, 1.35, 0.35, OX, 0.72, 1.75, M("brick_dark"), bevel=0.12, seg=2, wonk=0.03))
    ox, oy = _wpos("B", OX, 0.7)
    parts.append(taper_box("ohood", (2.2, 1.3, H - 2.1), (ox, oy, 2.1), M("limewash_b"), top=0.55, bevel=0.05, wonk=0.03))
    parts.append(warch("B", "omframe", 0.95, 0.8, 0.03, OX, 1.51, 0.68, M("iron", 0.6), bevel=0.01))
    parts.append(warch("B", "omouth", 0.72, 0.6, 0.03, OX, 1.53, 0.76, EM("fire", 5.0), bevel=0))
    parts.append(warch("B", "oash", 0.6, 0.42, 0.03, OX, 1.51, 0.08, M("coal", 0.9), bevel=0))
    parts.append(wl("B", "oledge", 1.3, 0.35, 0.07, OX, 1.66, 0.66, M("stone"), bevel=0.02, seg=1))
    for k in range(4):
        px, py = _wpos("B", OX + RNG.uniform(-0.2, 0.2), 1.6)
        parts.append(blob("ember", (0.08, 0.06, 0.04), (px, py, 0.77), EM("fire", 7.0), subsurf=1))
    col.append(wl("B", "c", 2.8, 1.5, H, OX, 0.75, 0))
    lx, ly = _wpos("B", OX, 2.0)
    lamp("oven", (lx, ly, 1.0))
    parts.append(wl("B", "odoor", 0.8, 0.05, 0.65, OX + 1.75, 1.2, 0.0, M("iron", 0.6), rot=(0.0, 0.0, 0.0)))
    # peels: one leaning on the wall by the oven, one resting on the ledge
    parts.append(cbox("peel_h", (0.04, 0.04, 2.3), (0.25, D - 0.4, 1.12), M("wood", 0.8), rot=(-0.16, 0, 0)))
    parts.append(cbox("peel_b", (0.34, 0.02, 0.46), (0.25, D - 0.22, 2.28), M("wood", 0.8), rot=(-0.16, 0, 0), bevel=0.01, seg=1))
    parts.append(cbox("peel2_h", (0.04, 1.9, 0.04), (OX + 0.3, D - 2.6, 0.76), M("wood", 0.8), rot=(0.05, 0, 0.1)))
    parts.append(cbox("peel2_b", (0.34, 0.44, 0.02), (OX + 0.2, D - 1.62, 0.72), M("wood", 0.8), rot=(0, 0, 0.1)))
    # firewood for the oven
    for row in range(3):
        for k in range(4 - row):
            parts.append(cyl("log", 0.08, 0.9, (0.9 + k * 0.17 + row * 0.08, D - 0.55, 0.08 + row * 0.15), M(RNG.choice(("wood", "timber", "wood_dark")), 0.9),
                             verts=7, rot=(math.pi / 2, 0, 0), center=True))
    col.append(box("c", (0.8, 0.9, 0.5), (1.15, D - 0.55, 0)))
    # dough trough (dzieza) on the right wall, dough rising in it, a scraper
    TU = 4.2
    parts.append(wl("R", "trough", 2.1, 0.7, 0.32, TU, 0.42, 0.5, M("wood", 0.8), bevel=0.03, seg=1, wonk=0.02))
    for s_ in (-1, 1):
        for nn in (0.15, 0.7):
            parts.append(wl("R", "tleg", 0.08, 0.08, 0.5, TU + s_ * 0.9, nn, 0, M("wood_dark")))
    tx, ty = _wpos("R", TU, 0.42)
    parts.append(blob("dough", (0.6, 1.9, 0.16), (tx, ty, 0.76), M("dough", 0.7), subsurf=2))
    parts.append(wl("R", "tlid", 2.1, 0.04, 0.7, TU, 0.05, 0.85, M("wood", 0.8), bevel=0.02, seg=1))
    col.append(wl("R", "c", 2.1, 0.75, 0.9, TU, 0.42, 0))
    # work table: floured, dough balls, a rolling pin, shaped loaves waiting for the oven
    table(parts, col, -0.9, 3.3, L=1.8, w=0.9, h=0.86, along_y=False, trestle=False)
    parts.append(box("flourtop", (1.5, 0.7, 0.006), (-0.9, 3.3, 0.86), M("flour", 0.95), wonk=0.03))
    for k in range(5):
        parts.append(blob("dball", (0.16, 0.16, 0.09), (-1.5 + k * 0.28, 3.15 + RNG.uniform(-0.05, 0.1), 0.86), M("dough", 0.7), subsurf=1))
    parts.append(cyl("rpin", 0.03, 0.45, (-0.5, 3.5, 0.9), M("wood", 0.6), verts=8, rot=(0, math.pi / 2, 0.3), center=True))
    for k in range(3):
        loaf(parts, -1.2 + k * 0.3, 3.55, 0.86, rot=0.2)
    # bread rack on the left wall: loaves, rolls and rings
    RU = 3.0
    for i in range(4):
        z = 0.35 + i * 0.45
        parts.append(wl("L", "rboard", 2.6, 0.45, 0.035, RU, 0.24, z, M("wood", 0.8)))
        k = 0.15
        while k < 2.45:
            px, py = _wpos("L", RU - 1.3 + k, 0.24)
            if i % 2:
                loaf(parts, px, py, z + 0.035, rot=math.pi / 2 + RNG.uniform(-0.2, 0.2))
                k += 0.2
            else:
                pretzel(parts, px, py, z + 0.035)
                k += 0.16
    for s_ in (-1, 1):
        parts.append(wl("L", "rpost", 0.05, 0.45, 1.8, RU + s_ * 1.32, 0.24, 0, M("wood_dark")))
    col.append(wl("L", "c", 2.7, 0.5, 1.8, RU, 0.25, 0))
    # the selling counter by the door: baskets of rolls, a stick of obwarzanki, scales
    ch = counter(parts, col, 1.7, 1.9, 1.9)
    for k in range(2):
        bx = 1.1 + k * 0.5
        parts.append(cyl("basket", 0.2, 0.14, (bx, 1.85, ch), M("wicker", 0.9), verts=10, r2=0.23))
        for j in range(4):
            loaf(parts, bx + RNG.uniform(-0.1, 0.1), 1.85 + RNG.uniform(-0.1, 0.1), ch + 0.1, big=False, rot=RNG.uniform(0, 3))
    parts.append(cyl("ostick", 0.012, 0.6, (2.3, 1.9, ch), M("wood", 0.8), verts=6))
    for j in range(7):
        pretzel(parts, 2.3, 1.9, ch + 0.05 + j * 0.06)
    scales(parts, 2.1, 2.05, ch, s=0.8)
    candle(parts, 0.95, 2.05, ch)
    # flour: sacks by the door, an open one, dust on the floor
    for (sx, sy) in ((-2.7, 0.8), (-2.2, 0.7), (-2.5, 1.25)):
        parts.append(blob("sack", (0.45, 0.4, 0.65), (sx, sy, 0), M("sack", 0.95), subsurf=1, wonk=0.04))
    parts.append(cyl("osack", 0.24, 0.55, (-2.0, 1.45, 0), M("sack", 0.95), verts=10, r2=0.27))
    parts.append(cyl("oflour", 0.25, 0.02, (-2.0, 1.45, 0.55), M("flour", 0.95), verts=10))
    parts.append(blob("sack", (0.4, 0.62, 0.3), (-2.45, 1.8, 0.62), M("sack", 0.95), subsurf=1, wonk=0.04))
    col.append(box("c", (1.2, 1.3, 0.9), (-2.4, 1.1, 0)))
    for (fx, fy, fw, fl) in ((-0.9, 2.5, 1.1, 0.5), (2.3, 4.2, 0.4, 1.0), (-2.0, 2.0, 0.6, 0.4), (-1.5, 4.4, 0.7, 0.4), (0.6, 3.9, 0.35, 0.3)):
        parts.append(blob("fdust", (fw, fl, 0.004), (fx, fy, 0.0), M("flour", 0.95), subsurf=2, wonk=0.08))
    # windows, light
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 2.1, 1.0, w=1.0, h=1.3)
    lantern(parts, 0.3, 3.1, H - 0.24, 2.3)
    post(OX, D - 2.3, 0.0)                    # the baker at the oven mouth
    post_at(1.9, TU, W / 2 - 0.4, TU)         # journeyman kneading at the trough
    post(1.7, 2.65, math.pi)                  # behind the counter
    post_at(-0.9, 2.6, -0.9, 3.3)             # the boy shaping loaves
    post_at(1.3, 1.2, 1.5, 1.9)               # a customer
    finish_set("int_shop_baker", parts, col)


def boot(parts, x, y, z, rot=0.0, mat="leather", tall=True):
    m = M(mat, 0.5)
    p = [blob("bshaft", (0.1, 0.12, 0.34 if tall else 0.14), (0, 0, 0.06), m, subsurf=1),
         blob("bfoot", (0.1, 0.26, 0.1), (0, -0.07, 0.0), m, subsurf=1),
         box("bheel", (0.08, 0.07, 0.04), (0, 0.04, -0.01), M("leather_b", 0.6))]
    parts.append(place(p, x, y, rot, z))


def int_shop_shoemaker():
    """Szewc: the cobbler's low bench and its globe lamp, lasts by the dozen, hides over a pole, boots on pegs."""
    start()
    W, D, H = 6.0, 5.5, 3.2
    parts, col = room(W, D, H, "limewash", "planks", "beams", skirt=("plaster_blue", 0.7))
    # cobbler's bench by the left window: seat, tool tray, the boot on its last, lap stone, water-globe lamp
    fake_window(parts, "L", 2.3, 1.1, w=0.9, h=1.1)
    BX, BY = -2.2, 2.3
    p = [box("cseat", (0.5, 1.5, 0.08), (0, 0, 0.36), M("wood", 0.8), bevel=0.02, seg=1, wonk=0.01)]
    for sy in (-1, 1):
        for sx in (-1, 1):
            p.append(box("cleg", (0.06, 0.06, 0.36), (sx * 0.2, sy * 0.66, 0), M("wood_dark")))
    p.append(box("ctray", (0.5, 0.6, 0.1), (0, 0.45, 0.44), M("wood_dark"), bevel=0.01, seg=1))
    for k in range(3):
        p.append(box("cdiv", (0.5, 0.02, 0.1), (0, 0.2 + k * 0.18, 0.44), M("wood", 0.8)))
    for k in range(9):
        p.append(cyl("awl", 0.006, 0.12, (RNG.uniform(-0.2, 0.2), 0.3 + RNG.uniform(0, 0.3), 0.5), M("iron", 0.4), verts=4, rot=(RNG.uniform(-0.4, 0.4), 0.3, 0)))
        p.append(cyl("awlh", 0.014, 0.05, (RNG.uniform(-0.2, 0.2), 0.3 + RNG.uniform(0, 0.3), 0.54), M("wood", 0.6), verts=6))
    p.append(blob("lapstone", (0.22, 0.18, 0.05), (0.05, -0.3, 0.44), M("stone_dark", 0.6), subsurf=1))
    p.append(cyl("gstand", 0.012, 0.35, (0.18, 0.7, 0.54), M("wood_dark"), verts=6))
    p.append(sphere("globe", 0.1, (0.18, 0.7, 0.98), M("water", 0.05), seg=12, rings=8))
    parts.append(place(p, BX, BY, 0.0))
    col.append(box("c", (0.55, 1.55, 0.5), (BX, BY, 0)))
    candle(parts, BX + 0.18, BY + 0.9, 0.44, h=0.14)
    lamp("candle", (BX + 0.2, BY + 0.6, 1.1))
    boot(parts, BX + 0.02, BY - 0.1, 0.46, rot=0.4, mat="hide")
    parts.append(blob("last", (0.09, 0.24, 0.08), (BX + 0.02, BY - 0.12, 0.47), M("wood", 0.7), subsurf=1))
    stool(parts, BX + 0.9, BY - 0.2, h=0.4)
    for k in range(8):
        parts.append(blob("scrap", (RNG.uniform(0.06, 0.16), RNG.uniform(0.04, 0.1), 0.006), (BX + RNG.uniform(0.3, 1.2), BY + RNG.uniform(-0.8, 0.8), 0), M(RNG.choice(("hide", "leather", "leather_b")), 0.8), subsurf=1))
    parts.append(cyl("sbucket", 0.18, 0.3, (BX + 0.1, BY + 1.15, 0), M("wood", 0.8), verts=10, r2=0.2))
    parts.append(cyl("sbwater", 0.18, 0.01, (BX + 0.1, BY + 1.15, 0.26), M("water", 0.05), verts=10))
    # lasts: shelves on the back wall, left, pairs of wooden feet in every size
    LU = -1.4
    for i in range(5):
        z = 0.4 + i * 0.38
        parts.append(wl("B", "lboard", 2.6, 0.3, 0.03, LU, 0.16, z, M("wood", 0.8)))
        k = 0.12
        while k < 2.45:
            px, py = _wpos("B", LU - 1.3 + k, 0.16)
            sz = RNG.uniform(0.8, 1.15)
            for dx in (-0.045, 0.045):
                parts.append(blob("last", (0.08 * sz, 0.22 * sz, 0.08 * sz), (px + dx, py, z + 0.03), M(RNG.choice(("wood", "timber")), 0.7), subsurf=1))
            k += 0.24
    for s_ in (-1, 1):
        parts.append(wl("B", "lpost", 0.05, 0.3, 2.0, LU + s_ * 1.32, 0.16, 0, M("wood_dark")))
    col.append(wl("B", "c", 2.7, 0.35, 2.0, LU, 0.17, 0))
    # hides: a pole across the back right corner, hides draped over it; rolled hides beneath
    hx0, hx1 = 0.4, 2.8
    parts.append(cyl("hpole", 0.035, hx1 - hx0, ((hx0 + hx1) / 2, D - 0.55, 2.05), M("wood", 0.8), verts=8, rot=(0, math.pi / 2, 0), center=True))
    for k, hm in enumerate(("hide", "leather", "hide", "leather_b")):
        hx = hx0 + 0.35 + k * 0.55
        for sgn in (-1, 1):
            parts.append(cbox("hidef", (0.55, 0.02, 1.2), (hx, D - 0.55 + sgn * 0.12, 1.48), M(hm, 0.8), rot=(sgn * 0.2, 0, 0), bevel=0.01, seg=1, wonk=0.04))
    for s_ in (hx0, hx1):
        parts.append(box("hpost", (0.07, 0.07, 2.05), (s_, D - 0.55, 0), M("wood_dark")))
    for k in range(3):
        parts.append(cyl("hroll", 0.14, 0.7, (1.0 + k * 0.4, D - 0.5, 0.14), M(("hide", "leather", "leather_b")[k], 0.8), verts=10, rot=(math.pi / 2, 0, 0), center=True))
    col.append(box("c", (hx1 - hx0, 0.7, 2.0), ((hx0 + hx1) / 2, D - 0.55, 0)))
    # boots and shoes on pegs along the right wall
    for zi, z in enumerate((1.35, 2.05)):
        pegs(parts, "R", 0.9, D - 0.4, z + 0.3)
        u = 1.1
        while u < D - 0.6:
            bx, by = _wpos("R", u, 0.14)
            for dy in (-0.07, 0.07):
                boot(parts, bx, by + dy, z - 0.05, rot=-math.pi / 2, mat=RNG.choice(("leather", "leather_b", "black", "hide")), tall=zi == 1 or RNG.random() < 0.5)
            u += 0.42
    # counter by the door with a pair of buckled shoes, a box of buckles, the ledger
    ch = counter(parts, col, 1.4, 1.7, 1.8)
    boot(parts, 1.0, 1.65, ch, rot=0.3, mat="black", tall=False)
    boot(parts, 1.18, 1.62, ch, rot=0.2, mat="black", tall=False)
    for dx in (0.0, 0.18):
        parts.append(box("buckle", (0.05, 0.02, 0.04), (1.02 + dx, 1.5, ch + 0.08), MET("brass", 0.3)))
    parts.append(box("ledger", (0.3, 0.22, 0.04), (1.9, 1.75, ch), M("leather_b", 0.8), bevel=0.01, seg=1))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 1.9, 1.0, w=1.0, h=1.2)
    lantern(parts, 0.2, 2.9, H - 0.24, 2.2)
    post_at(BX + 0.05, BY - 0.2, BX + 0.8, BY - 0.2)   # the shoemaker on his bench
    post_at(BX + 0.9, BY + 0.5, BX, BY)                 # apprentice on the stool
    post(1.4, 2.35, math.pi)                            # behind the counter
    post_at(1.6, 1.0, 1.4, 1.7)                         # customer
    finish_set("int_shop_shoemaker", parts, col)


def int_shop_goldsmith():
    """Zlotnik: stone vault, barred windows, the strongbox, the bench with its skin and tiny tools, a display case."""
    start()
    W, D = 6.0, 6.0
    parts, col = room(W, D, 0, "limewash", "flags", "vault", spring=2.3, rib=2)
    skirting(parts, "LRB", 0.9, "panel")
    for side in "LRB":
        L = W if side == "B" else D
        parts.append(wl(side, "dadorail", L, 0.06, 0.06, 0.0 if side == "B" else L / 2, 0.03, 0.9, M("panel_trim", 0.6)))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 1.9, 1.0, w=0.9, h=1.2, bars=True)
    fake_window(parts, "L", 3.2, 1.2, w=0.8, h=0.9, bars=True)
    # the jeweller's bench under the left window: skin, bench pin, gravers in a rack, a stake, the lamp and globe
    BY = 3.2
    parts.append(wl("L", "jbench", 1.8, 0.7, 0.08, BY, 0.4, 0.88, M("wood", 0.6), bevel=0.02, seg=1))
    parts.append(wl("L", "jbody", 1.8, 0.6, 0.7, BY, 0.34, 0.14, M("wood_dark"), bevel=0.02, seg=1))
    sx_, sy_ = _wpos("L", BY, 0.8)
    parts.append(blob("jskin", (0.25, 0.5, 0.06), (sx_ - 0.02, sy_, 0.7), M("hide", 0.8), subsurf=1))
    parts.append(box("jpin", (0.14, 0.08, 0.03), (sx_ + 0.06, sy_, 0.96), M("wood", 0.7)))
    for k in range(10):
        gx, gy = _wpos("L", BY - 0.6 + k * 0.06, 0.1)
        parts.append(cyl("graver", 0.004, 0.1, (gx, gy, 0.96), M("iron", 0.3), verts=4))
        parts.append(sphere("gknob", 0.011, (gx, gy, 1.07), M("wood", 0.6), seg=6, rings=3))
    parts.append(wl("L", "grack", 0.7, 0.05, 0.03, BY - 0.33, 0.1, 1.0, M("wood_dark")))
    for k in range(4):
        px, py = _wpos("L", BY + 0.2 + k * 0.08, 0.3)
        parts.append(box("plier", (0.012, 0.09, 0.008), (px, py, 0.965), M("iron", 0.3), rot=(0, 0, RNG.uniform(-0.3, 0.3))))
    px, py = _wpos("L", BY + 0.55, 0.35)
    parts.append(cyl("stake", 0.03, 0.08, (px, py, 0.96), M("iron", 0.3), verts=8))
    parts.append(box("dplate", (0.05, 0.14, 0.01), (px + 0.1, py - 0.2, 0.965), M("iron", 0.3)))
    lx, ly = _wpos("L", BY + 0.4, 0.2)
    parts.append(cyl("olamp", 0.05, 0.05, (lx, ly, 0.96), M("brass", 0.35), verts=8, r2=0.03))
    parts.append(cyl("oflame", 0.01, 0.04, (lx, ly, 1.01), EM("flame", 8.0), verts=6, r2=0.0))
    parts.append(sphere("oglobe", 0.07, (lx + 0.12, ly, 1.08), M("water", 0.05), seg=10, rings=6))
    lamp("candle", (lx + 0.2, ly, 1.2))
    for k in range(6):
        gx, gy = _wpos("L", BY - 0.3 + RNG.uniform(-0.2, 0.3), 0.55)
        parts.append(torus("ring", 0.012, 0.003, (gx, gy, 0.965), MET("gold", 0.25), seg=8, mseg=4))
    col.append(wl("L", "c", 1.8, 0.75, 0.96, BY, 0.4, 0))
    stool(parts, *_wpos("L", BY, 1.15), h=0.6)
    # the strongbox in the back right corner: iron bands, studs, a padlock
    SX, SY = 2.2, D - 0.6
    parts.append(box("splinth", (1.2, 0.8, 0.12), (SX, SY, 0), M("stone_dark"), bevel=0.02, seg=1))
    parts.append(box("sbox", (1.0, 0.62, 0.62), (SX, SY, 0.12), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("slid", (1.04, 0.66, 0.1), (SX, SY, 0.74), M("wood_dark"), bevel=0.02, seg=1))
    for k in range(4):
        parts.append(box("sband", (0.06, 0.68, 0.74), (SX - 0.42 + k * 0.28, SY, 0.12), M("iron", 0.5)))
    parts.append(box("sbandh", (1.06, 0.68, 0.06), (SX, SY, 0.4), M("iron", 0.5)))
    parts.append(box("slock", (0.14, 0.04, 0.16), (SX, SY - 0.34, 0.55), M("iron", 0.4)))
    parts.append(torus("shackle", 0.05, 0.012, (SX, SY - 0.36, 0.72), M("iron", 0.4), rot=(math.pi / 2, 0, 0), seg=10, mseg=4))
    col.append(box("c", (1.2, 0.8, 0.86), (SX, SY, 0)))
    # counter across the room: velvet pad, scales, a ledger, a candle
    ch = counter(parts, col, 0.5, 3.4, 2.6, mat="wood_dark")
    parts.append(box("pad", (0.5, 0.35, 0.01), (0.1, 3.3, ch), M("velvet", 0.9)))
    for k in range(5):
        parts.append(torus("ring", 0.014, 0.004, (0.0 + k * 0.05, 3.3 + RNG.uniform(-0.1, 0.1), ch + 0.014), MET("gold", 0.25), seg=8, mseg=4, rot=(0, 0.3, 0)))
    scales(parts, 0.9, 3.45, ch, s=0.8)
    parts.append(box("ledger", (0.32, 0.24, 0.05), (1.5, 3.45, ch), M("crimson", 0.8), bevel=0.01, seg=1))
    candle(parts, -0.5, 3.5, ch)
    lamp("candle", (-0.5, 3.4, ch + 0.5))
    # display case near the door: a glazed-looking cabinet with cups, chains and rings on velvet
    CX, CY = -1.9, 1.6
    parts.append(box("case", (1.3, 0.6, 0.85), (CX, CY, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("cvel", (1.18, 0.5, 0.01), (CX, CY, 0.85), M("velvet", 0.9)))
    for (dx, dy) in ((-0.62, 0), (0.62, 0), (0, -0.28), (0, 0.28)):
        parts.append(box("cframe", (0.04 if dx else 1.28, 0.04 if dy else 0.58, 0.28), (CX + dx, CY + dy, 0.85), MET("brass", 0.3)))
    for k in range(3):
        gx = CX - 0.4 + k * 0.4
        parts.append(cyl("goblet", 0.035, 0.1, (gx, CY + 0.1, 0.86), MET("gold", 0.2), verts=10, r2=0.05))
        parts.append(cyl("gstem", 0.01, 0.06, (gx, CY + 0.1, 0.86), MET("gold", 0.2), verts=6))
    for k in range(6):
        parts.append(torus("ring", 0.015, 0.004, (CX - 0.45 + k * 0.18, CY - 0.12, 0.865), MET("gold", 0.25), seg=8, mseg=4))
    parts.append(torus("chain", 0.12, 0.006, (CX + 0.3, CY - 0.05, 0.862), MET("gold", 0.25), seg=16, mseg=4))
    parts.append(cyl("pyx", 0.05, 0.06, (CX - 0.2, CY - 0.05, 0.86), M("pewter", 0.2), verts=10))
    col.append(box("c", (1.3, 0.6, 1.15), (CX, CY, 0)))
    # a little melting hearth with a crucible glowing, back left
    FU = -1.9
    parts.append(wl("B", "mhearth", 1.0, 0.7, 0.8, FU, 0.35, 0, M("brick"), bevel=0.03, seg=1, wonk=0.02))
    hx, hy = _wpos("B", FU, 0.35)
    parts.append(box("mcoal", (0.5, 0.4, 0.05), (hx, hy, 0.8), EM("fire", 4.0)))
    parts.append(cyl("crucible", 0.07, 0.12, (hx, hy, 0.82), M("brick_dark", 0.8), verts=8, r2=0.09))
    parts.append(taper_box("mhood", (1.0, 0.7, 0.9), (hx, hy, 1.5), M("limewash_b"), top=0.4, bevel=0.03))
    parts.append(cyl("mflue", 0.14, 3.5, (hx, hy, 2.4), M("limewash_b"), verts=8))
    col.append(wl("B", "c", 1.0, 0.7, 0.85, FU, 0.35, 0))
    lamp("forge", (hx, hy - 0.5, 1.1))
    # silver on a wall shelf
    parts.append(wl("R", "pshelf", 1.6, 0.25, 0.04, 2.6, 0.13, 1.6, M("wood_dark")))
    for k in range(5):
        px, py = _wpos("R", 2.0 + k * 0.3, 0.13)
        if k % 2:
            parts.append(cyl("tankard", 0.05, 0.14, (px, py, 1.64), M("pewter", 0.2), verts=10))
        else:
            parts.append(cyl("plate", 0.12, 0.012, (px, py + 0.06, 1.64 + 0.12), M("pewter", 0.2), verts=12, rot=(0, math.pi / 2, 0), center=True))
    lantern(parts, 0.4, 2.0, 3.9, 2.4)
    post_at(*_wpos("L", BY, 1.1), *_wpos("L", BY, 0.2))   # the goldsmith at his bench
    post(0.5, 4.0, math.pi)                                 # behind the counter
    post_at(-1.9, 2.3, -1.9, 1.6)                           # a client at the case
    post_at(hx, hy - 1.0, hx, hy)                           # apprentice at the hearth
    finish_set("int_shop_goldsmith", parts, col)


def int_shop_apothecary():
    """Apteka: jar-lined shelves with painted labels, mortar and scales, a still on its furnace, herbs drying,
    a skull and the stuffed crocodile over the counter."""
    start()
    W, D, H = 6.0, 6.0, 3.6
    parts, col = room(W, D, H, "limewash", "tiles", "beams", beam_step=1.0, summer=False)
    CTX["H"] = H
    # shelving: the whole back wall and most of the left wall, floor to beams, jars and bottles
    def jar_shelves(side, u, L, n):
        top = 0.5 + 0.42 * (n - 1)
        for sgn in (-1, 1):
            parts.append(wl(side, "upright", 0.06, 0.34, top + 0.2, u + sgn * L / 2, 0.17, 0, M("wood_dark")))
        parts.append(wl(side, "scornice", L + 0.2, 0.4, 0.12, u, 0.2, top + 0.2, M("wood_dark"), bevel=0.03, seg=1))
        parts.append(wl(side, "sbase", L, 0.36, 0.45, u, 0.18, 0, M("wood_dark"), bevel=0.02, seg=1))
        for i in range(n):
            z = 0.45 + 0.42 * i
            parts.append(wl(side, "board", L, 0.34, 0.03, u, 0.17, z, M("wood", 0.8)))
            k = 0.1
            while k < L - 0.1:
                px, py = _wpos(side, u - L / 2 + k, 0.17)
                if RNG.random() < 0.18:
                    bottle(parts, px, py, z + 0.03, RNG.choice(("glass_green", "glass", "copper")))
                    k += 0.12
                else:
                    r = RNG.uniform(0.05, 0.07)
                    jar(parts, px, py, z + 0.03, r=r, h=RNG.uniform(0.16, 0.24), body=RNG.choice(("tile_w", "tile_w", "icon_blue", "tile_ochre")))
                    k += r * 2 + 0.03
        col.append(wl(side, "c", L, 0.36, top + 0.3, u, 0.18, 0))
    jar_shelves("B", -0.4, 4.6, 6)
    jar_shelves("L", 3.4, 3.4, 6)
    # the counter, with a bronze mortar and pestle, scales, the skull, an hourglass, paper packets
    ch = counter(parts, col, 0.3, 3.1, 3.0, mat="wood_dark")
    parts.append(cyl("mortar", 0.14, 0.2, (-0.6, 3.05, ch), M("brass", 0.4), verts=12, r2=0.17))
    parts.append(cyl("mortin", 0.13, 0.01, (-0.6, 3.05, ch + 0.19), M("coal", 0.8), verts=12))
    parts.append(cyl("pestle", 0.025, 0.36, (-0.58, 3.05, ch + 0.28), M("brass", 0.4), verts=8, rot=(0.3, 0.2, 0), center=True))
    scales(parts, 0.3, 3.2, ch, s=0.8)
    sx_, sy_ = 1.2, 3.1
    parts.append(blob("skull", (0.15, 0.19, 0.15), (sx_, sy_, ch + 0.02), M("bone", 0.6), subsurf=2))
    parts.append(blob("jaw", (0.11, 0.1, 0.05), (sx_, sy_ - 0.05, ch), M("bone", 0.6), subsurf=1))
    for dx in (-0.035, 0.035):
        parts.append(sphere("socket", 0.025, (sx_ + dx, sy_ - 0.09, ch + 0.1), M("coal", 0.9), seg=6, rings=4))
    parts.append(box("book", (0.3, 0.22, 0.06), (1.35, 3.3, ch), M("leather_b", 0.8), bevel=0.01, seg=1))
    for k in range(4):
        parts.append(box("packet", (0.08, 0.06, 0.03), (-0.1 + k * 0.1, 2.9, ch), M("paper", 0.8), rot=(0, 0, RNG.uniform(-0.3, 0.3))))
    parts.append(cyl("hgl", 0.04, 0.08, (1.65, 3.05, ch + 0.02), M("glass", 0.1), verts=8, r2=0.005))
    parts.append(cyl("hgl", 0.005, 0.08, (1.65, 3.05, ch + 0.1), M("glass", 0.1), verts=8, r2=0.04))
    parts.append(cyl("sand", 0.03, 0.03, (1.65, 3.05, ch + 0.02), M("tile_ochre", 0.9), verts=8, r2=0.01))
    candle(parts, -1.0, 3.25, ch)
    lamp("candle", (-1.0, 3.1, ch + 0.5))
    # the still in the back right corner: brick furnace glowing, copper pot, alembic head, neck, receiver
    SX, SY = 2.3, D - 0.7
    parts.append(box("sfurn", (0.9, 0.8, 0.75), (SX, SY, 0), M("brick"), bevel=0.03, seg=1, wonk=0.02))
    parts.append(box("sfdoor", (0.26, 0.02, 0.18), (SX, SY - 0.41, 0.22), EM("fire", 5.0)))
    parts.append(cyl("spot", 0.28, 0.35, (SX, SY, 0.75), MET("copper_pot", 0.35), verts=14, r2=0.22))
    parts.append(cyl("shead", 0.2, 0.3, (SX, SY, 1.1), MET("copper_pot", 0.35), verts=12, r2=0.06))
    parts.append(cbox("sneck", (0.035, 0.035, 0.95), (SX - 0.45, SY - 0.1, 1.15), MET("copper_pot", 0.35), rot=(0, -1.1, 0)))
    parts.append(sphere("recv", 0.14, (SX - 0.9, SY - 0.1, 0.8), M("glass_green", 0.1), seg=12, rings=8))
    parts.append(box("rstand", (0.3, 0.3, 0.66), (SX - 0.9, SY - 0.1, 0), M("wood_dark")))
    col.append(box("c", (1.4, 0.9, 1.3), (SX - 0.3, SY, 0)))
    lamp("stove", (SX, SY - 0.8, 0.4))
    # herbs drying on strings under the beams
    for i in range(6):
        y = (D / 6) * (i + 0.5)
        for k in range(RNG.randint(3, 5)):
            herb_bunch(parts, RNG.uniform(-2.4, 2.4), y + RNG.uniform(-0.08, 0.08), H - 0.24, s=RNG.uniform(0.8, 1.2))
    # the stuffed crocodile hanging over the counter
    CZ = H - 0.8
    parts.append(blob("croc", (0.26, 1.3, 0.16), (0.3, 3.1, CZ), M("icon_green", 0.7), subsurf=2))
    parts.append(taper_box("csnout", (0.18, 0.5, 0.08), (0.3, 3.9, CZ + 0.03), M("icon_green", 0.7), top=0.4))
    parts.append(cbox("ctail", (0.12, 0.9, 0.08), (0.34, 2.05, CZ + 0.08), M("icon_green", 0.7), rot=(0, 0, 0.2)))
    for sgn in (-1, 1):
        for yy in (2.8, 3.5):
            parts.append(cbox("cleg", (0.2, 0.05, 0.04), (0.3 + sgn * 0.2, yy, CZ + 0.04), M("icon_green", 0.7), rot=(0, 0, sgn * 0.5)))
        parts.append(cyl("cchain", 0.005, H - CZ - 0.12, (0.3, 3.1 + sgn * 0.5, CZ + 0.12), M("iron", 0.6), verts=4))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 1.9, 1.0, w=1.0, h=1.3)
    lantern(parts, -1.4, 1.8, H - 0.24, 2.4)
    post(0.3, 3.8, math.pi)                   # the apothecary behind the counter
    post_at(0.6, 2.3, 0.3, 3.1)               # a customer
    post_at(SX - 0.5, SY - 1.1, SX, SY)       # assistant at the still
    post_at(-1.8, 4.6, -1.8, D)               # at the shelves
    finish_set("int_shop_apothecary", parts, col)


def int_workshop_locksmith():
    """Slusarz: boards of keys, locks and padlocks, the vice bench, a forge corner with its coals."""
    start()
    W, D, H = 7.0, 6.0, 3.4
    parts, col = room(W, D, H, "limewash_b", "brick", "soot", beam_step=1.4)
    CTX["H"] = H
    # key boards on the back wall
    for (u, rows) in ((0.6, 4), (2.4, 4)):
        parts.append(wl("B", "kboard", 1.4, 0.04, 1.1, u, 0.02, 1.2, M("plank_b", 0.8), bevel=0.01, seg=1))
        for r in range(rows):
            for c in range(6):
                uu = u - 0.55 + c * 0.22
                z = 2.15 - r * 0.25
                parts.append(wl("B", "knail", 0.01, 0.04, 0.01, uu, 0.05, z + 0.03, M("iron", 0.5)))
                key_shape(parts, "B", uu, z, 0.06, s=RNG.uniform(0.7, 1.2), mat=RNG.choice(("iron", "iron", "brass")))
    # padlocks and a door lock-plate on the left wall
    parts.append(wl("L", "lboard", 2.4, 0.04, 0.9, 3.4, 0.02, 1.3, M("plank_b", 0.8)))
    for k in range(6):
        u = 2.4 + k * 0.38
        px, py = _wpos("L", u, 0.1)
        parts.append(wl("L", "padlock", 0.12, 0.05, 0.13, u, 0.08, 1.55 - (k % 2) * 0.35, M("iron", 0.4), bevel=0.01, seg=1))
        parts.append(torus("pshack", 0.04, 0.01, (px, py, 1.73 - (k % 2) * 0.35), M("iron", 0.4), rot=(math.pi / 2, 0, math.pi / 2), seg=8, mseg=4))
    parts.append(wl("L", "lockplate", 0.4, 0.05, 0.55, 5.0, 0.03, 1.2, M("iron", 0.45), bevel=0.01, seg=1))
    for k in range(3):
        parts.append(wl("L", "lbolt", 0.12, 0.03, 0.04, 5.0 + 0.05, 0.07, 1.35 + k * 0.12, M("brass", 0.3)))
    # the bench along the right wall with two vices, files, a lock opened up
    BY = 3.2
    parts.append(wl("R", "bench", 3.2, 0.8, 0.1, BY, 0.45, 0.85, M("wood", 0.7), bevel=0.03, seg=1, wonk=0.015))
    for s_ in (-1, 1):
        for nn in (0.15, 0.75):
            parts.append(wl("R", "bleg", 0.1, 0.1, 0.85, BY + s_ * 1.45, nn, 0, M("wood_dark")))
    col.append(wl("R", "c", 3.2, 0.8, 0.95, BY, 0.45, 0))
    iron = M("iron", 0.45)
    for du in (-1.1, 0.4):
        vx, vy = _wpos("R", BY + du, 0.88)
        parts.append(box("vice", (0.14, 0.22, 0.24), (vx, vy, 0.8), iron))
        parts.append(box("vjaw", (0.16, 0.05, 0.1), (vx, vy - 0.12, 0.98), iron))
        parts.append(cbox("vscrew", (0.03, 0.3, 0.03), (vx, vy - 0.22, 0.9), iron))
        parts.append(cbox("vbar", (0.25, 0.02, 0.02), (vx, vy - 0.36, 0.9), iron))
        parts.append(cyl("vleg", 0.025, 0.8, (vx, vy - 0.05, 0), iron, verts=6))
    for k in range(6):
        fx, fy = _wpos("R", BY - 0.5 + k * 0.1, 0.5)
        parts.append(box("file", (0.02, 0.28, 0.008), (fx, fy, 0.95), M("pewter", 0.4), rot=(0, 0, RNG.uniform(-0.2, 0.2))))
    lx, ly = _wpos("R", BY + 1.0, 0.45)
    parts.append(box("lockbox", (0.25, 0.18, 0.06), (lx, ly, 0.95), M("iron", 0.45)))
    for k in range(4):
        parts.append(cyl("gear", 0.03, 0.01, (lx + RNG.uniform(-0.08, 0.08), ly + RNG.uniform(-0.05, 0.05), 1.01), M("brass", 0.3), verts=8))
    parts.append(wl("R", "toolboard", 2.6, 0.04, 0.9, BY, 0.02, 1.4, M("plank_b", 0.8)))
    for k in range(8):
        u = BY - 1.1 + k * 0.32
        parts.append(wl("R", "thandle", 0.03, 0.03, 0.3, u, 0.06, 1.6, M("wood", 0.8)))
        parts.append(wl("R", "thead", 0.12 if k % 2 else 0.03, 0.04, 0.05 if k % 2 else 0.25, u, 0.06, 1.9 if k % 2 else 1.35, iron))
    # forge corner, back left: small hearth, coals, hood, a stake anvil, bellows
    FX, FY = -2.7, D - 0.8
    parts.append(box("forge", (1.3, 1.1, 0.8), (FX, FY, 0), M("brick"), bevel=0.04, seg=1, wonk=0.03))
    parts.append(box("forgetop", (1.4, 1.2, 0.08), (FX, FY, 0.8), M("stone_dark")))
    parts.append(box("coals", (0.55, 0.45, 0.05), (FX + 0.1, FY - 0.1, 0.88), EM("fire", 6.0)))
    for k in range(5):
        parts.append(blob("coal", (0.12, 0.1, 0.07), (FX + RNG.uniform(-0.2, 0.3), FY - 0.1 + RNG.uniform(-0.2, 0.2), 0.9), M("coal", 0.9), subsurf=1))
    parts.append(taper_box("fhood", (1.3, 1.1, 0.9), (FX, FY + 0.05, 1.7), M("brick_dark"), top=0.45, bevel=0.04, wonk=0.03))
    parts.append(box("flue", (0.55, 0.5, H - 2.6), (FX, FY + 0.2, 2.6), M("brick_dark")))
    col.append(box("c", (1.4, 1.2, H), (FX, FY, 0)))
    lamp("forge", (FX + 0.1, FY - 0.6, 1.2))
    parts.append(box("bellows", (0.4, 0.8, 0.2), (FX + 1.05, FY + 0.05, 0.85), M("leather", 0.9), bevel=0.05, seg=2, rot=(0.25, 0, 0)))
    parts.append(box("bstand", (0.35, 0.35, 0.8), (FX + 1.05, FY + 0.05, 0), M("wood_dark")))
    AX, AY = -1.4, D - 2.0
    parts.append(cyl("stump", 0.25, 0.55, (AX, AY, 0), M("wood", 0.9), verts=10, bevel=0.02, seg=1))
    parts.append(box("anvil", (0.3, 0.13, 0.14), (AX, AY, 0.55), iron, bevel=0.01, seg=1))
    parts.append(cyl("ahorn", 0.05, 0.18, (AX - 0.22, AY, 0.64), iron, verts=8, r2=0.01, rot=(0, -math.pi / 2, 0), center=True))
    col.append(cyl("c", 0.28, 0.7, (AX, AY, 0), None, verts=8))
    # an iron gate grille leaning by the door, a chest with a fine lock
    for k in range(6):
        parts.append(cbox("grille", (0.03, 0.03, 1.8), (-3.2 + k * 0.14, 0.55, 0.92), iron, rot=(0.12, 0, 0)))
    for zz in (0.4, 1.4):
        parts.append(cbox("grilleh", (0.8, 0.03, 0.03), (-2.85, 0.5 + zz * 0.12, zz), iron))
    parts.append(box("chest", (0.9, 0.5, 0.5), (1.9, 0.75, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("chestplate", (0.2, 0.02, 0.25), (1.9, 0.49, 0.18), M("brass", 0.3)))
    col.append(box("c", (0.9, 0.5, 0.5), (1.9, 0.75, 0)))
    table(parts, col, 0.0, 3.4, L=1.6, w=0.8, h=0.86, along_y=False, trestle=True)
    parts.append(box("tlock", (0.35, 0.25, 0.08), (-0.3, 3.4, 0.86), M("iron", 0.45), bevel=0.01, seg=1))
    for k in range(7):
        parts.append(cyl("tpart", RNG.uniform(0.015, 0.04), 0.01, (0.1 + RNG.uniform(0, 0.5), 3.4 + RNG.uniform(-0.25, 0.25), 0.86), M(RNG.choice(("brass", "iron")), 0.3), verts=8))
    for k in range(3):
        parts.append(cyl("tspring", 0.012, 0.12, (0.5 + k * 0.05, 3.2, 0.86), M("iron", 0.3), verts=6, rot=(0, math.pi / 2, 0), center=True))
    candle(parts, 0.6, 3.55, 0.86)
    lamp("candle", (0.5, 3.4, 1.4))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 2.2, 1.1, w=0.9, h=1.1)
    lantern(parts, 1.4, BY, H - 0.26, 2.3)
    post_at(*_wpos("R", BY - 1.1, 1.3), *_wpos("R", BY - 1.1, 0.5))   # at the vice
    post_at(FX + 0.3, FY - 1.2, FX, FY)                                  # at the forge
    post_at(AX + 0.6, AY - 0.3, AX, AY)                                  # at the anvil
    post_at(0.8, 1.6, 0.6, D)                                            # a customer at the key boards
    finish_set("int_workshop_locksmith", parts, col)


def dress_form(parts, col, x, y, rot=0.0, coat=None):
    p = [blob("torso", (0.46, 0.3, 0.66), (0, 0, 0.98), M("linen", 0.9), subsurf=2),
         cyl("fneck", 0.04, 0.12, (0, 0, 1.6), M("wood", 0.7), verts=8),
         sphere("fknob", 0.05, (0, 0, 1.74), M("wood", 0.7), seg=8, rings=4),
         cyl("fpole", 0.02, 1.0, (0, 0, 0.05), M("wood_dark"), verts=6)]
    for k in range(3):
        a = math.tau * k / 3
        p.append(cbox("ffoot", (0.4, 0.04, 0.03), (0.18 * math.cos(a), 0.18 * math.sin(a), 0.03), M("wood_dark"), rot=(0, 0, a)))
    if coat:
        p.append(blob("coat", (0.52, 0.36, 1.0), (0, 0, 0.55), M(coat, 0.9), subsurf=1, wonk=0.02))
        for sx in (-1, 1):
            p.append(cbox("sleeve", (0.12, 0.14, 0.6), (sx * 0.28, 0, 1.22), M(coat, 0.9), rot=(0, sx * 0.15, 0), bevel=0.03, seg=1))
        p.append(box("frog", (0.02, 0.02, 0.4), (0, -0.16, 1.1), MET("gold", 0.3)))
    parts.append(place(p, x, y, rot))
    col.append(cyl("c", 0.25, 1.7, (x, y, 0), None, verts=6))


def int_shop_tailor():
    """Krawiec: bolts of cloth, the cutting table with shears and chalk, dress forms, a cheval mirror, the
    tailors' board by the window where they sit cross-legged."""
    start()
    W, D, H = 6.0, 6.0, 3.3
    parts, col = room(W, D, H, "wallpaper", "planks", "beams", skirt=("panel", 0.8))
    shelf_unit(parts, col, "L", 3.9, 3.4, 5, goods="cloth", z0=0.35, dz=0.42)
    # upright bolts in a rack by the back wall
    for k in range(7):
        parts.append(cyl("ubolt", 0.08, 1.3, (-2.5 + k * 0.18, D - 0.3, 0), M(RNG.choice(("cloth_green", "cloth_blue", "crimson", "cloth_ochre", "linen", "navy")), 0.9), verts=10,
                         rot=(0.12, 0, 0)))
    parts.append(wl("B", "brail", 1.4, 0.06, 0.06, -1.95, 0.12, 1.1, M("wood_dark")))
    col.append(wl("B", "c", 1.4, 0.4, 1.3, -1.95, 0.2, 0))
    # the cutting table: cloth spread, paper patterns, shears, chalk, a pincushion, the yardstick
    TX, TY = 0.5, 3.3
    table(parts, col, TX, TY, L=2.2, w=1.1, h=0.88, along_y=False, trestle=False)
    parts.append(box("tcloth", (1.7, 0.9, 0.008), (TX - 0.1, TY, 0.88), M("cloth_blue", 0.9), wonk=0.02))
    for k in range(3):
        parts.append(box("pattern", (0.4, 0.25, 0.004), (TX - 0.5 + k * 0.4, TY + RNG.uniform(-0.2, 0.2), 0.89), M("paper", 0.9), rot=(0, 0, RNG.uniform(-0.5, 0.5))))
    for a in (-0.3, 0.3):
        parts.append(box("shears", (0.25, 0.018, 0.01), (TX + 0.6, TY - 0.2, 0.89), M("iron", 0.35), rot=(0, 0, a)))
    parts.append(box("chalk", (0.05, 0.03, 0.02), (TX + 0.3, TY + 0.3, 0.89), M("flour", 0.9)))
    parts.append(sphere("pins", 0.05, (TX + 0.85, TY + 0.3, 0.9), M("crimson", 0.9), seg=8, rings=4))
    parts.append(box("yard", (1.0, 0.03, 0.012), (TX - 0.2, TY - 0.4, 0.89), M("wood", 0.6)))
    # dress forms at the back right: one bare, one wearing a half-made kontusz
    dress_form(parts, col, 1.6, D - 0.8, math.pi)
    dress_form(parts, col, 2.4, D - 1.2, math.pi + 0.4, coat="crimson")
    # cheval mirror on the right wall by the front
    MX, MY = 2.4, 1.8
    parts.append(box("mfoot", (0.7, 0.3, 0.05), (MX, MY, 0), M("wood_dark")))
    for s_ in (-1, 1):
        parts.append(box("mpost", (0.05, 0.05, 1.8), (MX, MY + s_ * 0.32, 0.05), M("wood_dark")))
    parts.append(box("mframe", (0.06, 0.62, 1.5), (MX, MY, 0.35), MET("gold", 0.35), bevel=0.02, seg=1, rot=(0, -0.08, 0)))
    parts.append(box("mglass", (0.02, 0.54, 1.4), (MX - 0.04, MY, 0.4), MET("mirror", 0.04), rot=(0, -0.08, 0)))
    col.append(box("c", (0.3, 0.7, 1.8), (MX, MY, 0)))
    # the tailors' board under the left window: they sit on it cross-legged; work and a candle on it
    fake_window(parts, "L", 1.6, 1.1, w=0.9, h=1.2)
    bx_, by_ = _wpos("L", 1.6, 0.65)
    parts.append(box("tboard", (1.2, 1.5, 0.45), (bx_, by_, 0), M("wood", 0.8), bevel=0.02, seg=1))
    parts.append(box("twork", (0.5, 0.4, 0.01), (bx_ + 0.1, by_ + 0.3, 0.45), M("navy", 0.9), wonk=0.02))
    parts.append(box("twork", (0.4, 0.3, 0.01), (bx_ - 0.2, by_ - 0.3, 0.45), M("cloth_green", 0.9), wonk=0.02))
    candle(parts, bx_ - 0.4, by_, 0.45)
    lamp("candle", (bx_ - 0.2, by_, 1.0))
    col.append(box("c", (1.2, 1.5, 0.45), (bx_, by_, 0)))
    # coats waiting to be collected
    for k, cm in enumerate(("navy", "brown_coat", "green_coat")):
        hanging_coat(parts, "B", 0.2 + k * 0.55, 2.0, cm)
    ch = counter(parts, col, -1.3, 1.9, 1.6, mat="wood_dark")
    parts.append(box("ledger", (0.3, 0.22, 0.04), (-1.6, 1.95, ch), M("leather_b", 0.8)))
    parts.append(cyl("tbolt", 0.07, 0.5, (-0.9, 1.9, ch + 0.07), M("crimson", 0.9), verts=10, rot=(0, math.pi / 2, 0), center=True))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 1.9, 1.0, w=1.0, h=1.3)
    lantern(parts, 0.5, TY, H - 0.24, 2.3)
    lantern(parts, 1.6, D - 1.6, H - 0.24, 2.3)
    for dx in (-0.7, 0.7):
        candle(parts, TX + dx, TY + 0.4, 0.88)
    lamp("candle", (TX, TY + 0.4, 1.4))
    post_at(bx_, by_, bx_ + 1, by_)            # tailor on the board
    post_at(TX, TY - 0.8, TX, TY)              # cutter
    post_at(MX - 0.9, MY, MX, MY)              # customer at the mirror
    post(-1.3, 2.5, math.pi)                   # behind the counter
    finish_set("int_shop_tailor", parts, col)


def folded_stack(parts, side, u, z, n, depth=0.34):
    hh = 0
    for i in range(RNG.randint(3, 6)):
        th = RNG.uniform(0.045, 0.075)
        parts.append(wl(side, "fold", RNG.uniform(0.36, 0.42), depth * 0.85, th, u + RNG.uniform(-0.01, 0.01), n, z + hh,
                        M(RNG.choice(("cloth_green", "cloth_blue", "crimson", "cloth_ochre", "linen", "navy", "brown_coat", "sukmana", "velvet")), 0.9), bevel=0.012, seg=1))
        hh += th


def int_shop_cloth():
    """Sukiennik: pigeonholes of folded cloth to the beams, the counter with the Krakow ell, samples on a rod,
    bales roped up by the door."""
    start()
    W, D, H = 7.0, 6.5, 3.6
    parts, col = room(W, D, H, "limewash", "planks", "beams")
    for (side, u, L) in (("B", 0.0, 6.4), ("L", 3.9, 3.8)):
        n = 6
        for sgn in (-1, 1):
            parts.append(wl(side, "upright", 0.06, 0.4, 2.8, u + sgn * L / 2, 0.2, 0, M("wood_dark")))
        k = 1
        while k * 0.8 < L - 0.1:
            parts.append(wl(side, "div", 0.04, 0.4, 2.4, u - L / 2 + k * 0.8, 0.2, 0.4, M("wood_dark")))
            k += 1
        for i in range(n):
            z = 0.4 + i * 0.42
            parts.append(wl(side, "board", L, 0.4, 0.03, u, 0.2, z, M("wood", 0.8)))
            if i < n - 1:
                c = 0
                while (c + 0.5) * 0.8 < L:
                    folded_stack(parts, side, u - L / 2 + (c + 0.5) * 0.8, z + 0.03, 0.2)
                    c += 1
        parts.append(wl(side, "scornice", L + 0.2, 0.46, 0.12, u, 0.23, 2.8, M("wood_dark"), bevel=0.03, seg=1))
        col.append(wl(side, "c", L, 0.42, 2.9, u, 0.21, 0))
    # the counter, a bolt unrolled across it, the ell (lokiec) with brass ends, shears, a sample book
    ch = counter(parts, col, 0.2, 3.3, 3.4)
    parts.append(cyl("bolt", 0.1, 0.62, (-1.1, 3.35, ch + 0.1), M("cloth_green", 0.9), verts=12, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(box("unroll", (1.8, 0.6, 0.006), (-0.1, 3.35, ch), M("cloth_green", 0.9), wonk=0.01))
    parts.append(box("ell", (0.62, 0.03, 0.02), (0.1, 3.05, ch + 0.006), M("iron", 0.35)))
    for sx in (-1, 1):
        parts.append(box("ellend", (0.03, 0.04, 0.03), (0.1 + sx * 0.3, 3.05, ch + 0.006), M("brass", 0.3)))
    for a in (-0.3, 0.3):
        parts.append(box("shears", (0.25, 0.018, 0.01), (1.0, 3.2, ch), M("iron", 0.35), rot=(0, 0, a)))
    parts.append(box("sbook", (0.35, 0.28, 0.07), (1.5, 3.4, ch), M("leather", 0.8), bevel=0.01, seg=1))
    for k in range(4):
        parts.append(box("swatch", (0.1, 0.08, 0.004), (1.42 + k * 0.04, 3.2, ch + 0.07), M(("crimson", "navy", "cloth_ochre", "cloth_green")[k], 0.9)))
    candle(parts, 1.8, 3.25, ch)
    lamp("candle", (1.6, 3.2, ch + 0.5))
    # samples hanging from a rod on the right wall
    parts.append(wl("R", "srod", 3.0, 0.04, 0.04, 3.0, 0.15, 2.0, M("brass", 0.3)))
    for k in range(13):
        u = 1.6 + k * 0.22
        parts.append(wl("R", "sample", 0.18, 0.01, 0.35, u, 0.15, 1.63, M(RNG.choice(("cloth_green", "cloth_blue", "crimson", "cloth_ochre", "navy", "velvet", "sukmana", "zupan_gold")), 0.9)))
    # bales by the door, roped
    for (bx, by, bz) in ((2.6, 0.9, 0.0), (2.6, 0.9, 0.55), (1.8, 0.8, 0.0), (-2.7, 0.9, 0.0)):
        parts.append(box("bale", (0.75, 0.55, 0.55), (bx, by, bz), M("canvas", 0.9), bevel=0.05, seg=1, wonk=0.03))
        for dx in (-0.2, 0.2):
            parts.append(box("rope", (0.03, 0.57, 0.57), (bx + dx, by, bz - 0.01), M("straw", 0.9)))
    col.append(box("c", (1.8, 0.6, 1.1), (2.2, 0.9, 0)))
    col.append(box("c", (0.75, 0.55, 0.55), (-2.7, 0.9, 0)))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 1.7, 1.0, w=1.0, h=1.3)
    lantern(parts, -0.6, 2.2, H - 0.24, 2.4)
    lantern(parts, 1.2, 4.6, H - 0.24, 2.4)
    post(0.2, 4.0, math.pi)                   # the merchant
    post(-1.3, 4.0, math.pi)                  # his clerk
    post_at(0.4, 2.5, 0.2, 3.3)               # a customer
    post_at(2.3, 3.0, 3.5, 3.0)               # someone fingering the samples
    finish_set("int_shop_cloth", parts, col)


def raising_cask(parts, x, y, r_top=0.36, r_bot=0.55, h=0.9, n=16):
    """A cask being raised: staves in a truss hoop at the top, splayed at the foot."""
    for k in range(n):
        a = math.tau * k / n
        xt, yt = x + r_top * math.cos(a), y + r_top * math.sin(a)
        xb, yb = x + r_bot * math.cos(a), y + r_bot * math.sin(a)
        lean = math.atan2(r_bot - r_top, h)
        parts.append(cbox("stave", (0.11, 0.03, h), ((xt + xb) / 2, (yt + yb) / 2, h / 2), M("wood", 0.8), rot=(lean, 0, a - math.pi / 2)))
    parts.append(torus("rhoop", r_top + 0.03, 0.02, (x, y, h - 0.08), M("iron", 0.5), seg=16, mseg=4))
    parts.append(torus("rhoop2", (r_top + r_bot) / 2 + 0.05, 0.02, (x, y, h * 0.55), M("iron", 0.5), seg=16, mseg=4))


def int_workshop_cooper():
    """Bednarz: stacks of staves, hoops on the wall, a cask being raised and fired over a cresset, finished casks."""
    start()
    W, D, H = 8.0, 6.5, 3.8
    parts, col = room(W, D, H, "limewash_b", "earth", "beams", beam_step=1.6)
    # stave stacks along the left wall, crossed layers
    for k in range(3):
        yb = 1.4 + k * 1.5
        for j in range(7):
            along = j % 2 == 0
            for i in range(5):
                if along:
                    parts.append(box("stave", (0.1, 1.2, 0.03), (-W / 2 + 0.3 + i * 0.12, yb, j * 0.05), M("wood", 0.8)))
                else:
                    parts.append(box("stave", (0.62, 0.1, 0.03), (-W / 2 + 0.55, yb - 0.5 + i * 0.25, j * 0.05), M("wood", 0.8)))
        col.append(box("c", (0.7, 1.2, 0.4), (-W / 2 + 0.55, yb, 0)))
    for k in range(9):
        parts.append(cbox("lean", (0.1, 0.03, 1.3), (-W / 2 + 0.2, D - 0.8 + k * 0.06, 0.64), M("wood", 0.8), rot=(0, 0.15, 0)))
    # hoops on pegs on the back wall
    for k in range(9):
        u = -2.6 + k * 0.55
        r = RNG.uniform(0.26, 0.42)
        px, py = _wpos("B", u, 0.06)
        parts.append(torus("hoop", r, 0.012, (px, py, 2.6 - r), M("iron" if k % 3 else "wood", 0.5), rot=(math.pi / 2, 0, 0), seg=16, mseg=4))
        parts.append(wl("B", "hpeg", 0.03, 0.1, 0.03, u, 0.05, 2.6, M("wood_dark")))
    # the cask being raised, a cresset burning inside it to bend the staves
    RX, RY = 0.8, 3.6
    raising_cask(parts, RX, RY)
    parts.append(cyl("cresset", 0.18, 0.2, (RX, RY, 0.05), M("iron", 0.5), verts=8, r2=0.24))
    parts.append(cyl("cfire", 0.14, 0.05, (RX, RY, 0.23), EM("fire", 8.0), verts=8))
    for k in range(3):
        parts.append(cyl("flame", 0.06, RNG.uniform(0.2, 0.3), (RX + RNG.uniform(-0.06, 0.06), RY + RNG.uniform(-0.06, 0.06), 0.25), EM("flame", 9.0), verts=6, r2=0.0))
    lamp("fire", (RX, RY, 1.0))
    col.append(cyl("c", 0.55, 0.95, (RX, RY, 0), None, verts=8))
    # finished casks and one on the block being hooped; the cooper's tools
    for (bx, by, bz) in ((2.9, 0.8, 0.0), (3.3, 1.5, 0.0), (2.9, 1.5, 0.85)):
        barrel(parts, bx, by, bz, r=0.33, h=0.85)
    col.append(box("c", (1.2, 1.4, 1.7), (3.1, 1.2, 0)))
    cask(parts, col, 2.6, D - 1.0, 0.0, r=0.4, L=0.9, rot=math.pi / 2, cradle=True, mark=False)
    for (bx, by) in ((3.4, 3.2), (3.4, 4.0), (-0.9, 5.6)):
        barrel(parts, bx, by, 0.0, r=0.3, h=0.8)
        col.append(cyl("c", 0.32, 0.8, (bx, by, 0), None, verts=8))
    for k in range(6):
        parts.append(torus("floorhoop", RNG.uniform(0.3, 0.4), 0.012, (2.2 + RNG.uniform(-0.2, 0.2), 2.4 + RNG.uniform(-0.2, 0.2), 0.012 + k * 0.025), M("iron", 0.5), seg=16, mseg=4))
    parts.append(wl("B", "tbench", 2.2, 0.6, 0.08, 1.0, 0.35, 0.82, M("wood", 0.7)))
    for s_ in (-1, 1):
        parts.append(wl("B", "tleg", 0.08, 0.5, 0.82, 1.0 + s_ * 1.0, 0.35, 0, M("wood_dark")))
    col.append(wl("B", "c", 2.2, 0.6, 0.9, 1.0, 0.35, 0))
    for k, (tl, tw) in enumerate(((0.35, 0.12), (0.4, 0.05), (0.3, 0.08), (0.25, 0.1))):
        tx, ty = _wpos("B", 0.2 + k * 0.45, 0.35)
        parts.append(box("tool", (tw, tl, 0.03), (tx, ty, 0.9), M("iron", 0.45)))
        parts.append(cbox("toolh", (0.03, 0.3, 0.03), (tx, ty - 0.3, 0.915), M("wood", 0.7)))
    # the shaving horse by the front left
    SX, SY = -1.8, 1.2
    parts.append(cbox("shorse", (0.25, 1.6, 0.08), (SX, SY, 0.5), M("wood", 0.8), rot=(0.12, 0, 0)))
    for s_ in (-1, 1):
        parts.append(cbox("sleg", (0.06, 0.06, 0.55), (SX, SY + s_ * 0.65, 0.25), M("wood_dark"), rot=(s_ * 0.2, 0, 0)))
    parts.append(box("shead", (0.25, 0.1, 0.5), (SX, SY + 0.4, 0.5), M("wood_dark")))
    parts.append(box("sstave", (0.1, 0.9, 0.03), (SX, SY + 0.25, 0.62), M("wood", 0.8), rot=(0.12, 0, 0)))
    parts.append(cbox("dknife", (0.5, 0.03, 0.02), (SX, SY + 0.05, 0.7), M("iron", 0.4)))
    for k in range(18):
        parts.append(blob("shaving", (RNG.uniform(0.06, 0.12), RNG.uniform(0.06, 0.14), 0.02), (RNG.uniform(-2.8, 1.8), RNG.uniform(0.8, 5.5), 0), M("canvas", 0.9), subsurf=1))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 2.4, 1.1, w=0.9, h=1.1)
    lantern(parts, 2.0, 3.0, H - 0.26, 2.5)
    post_at(RX - 0.9, RY - 0.4, RX, RY)          # cooper at the cask
    post_at(SX, SY - 0.6, SX, SY)                # apprentice on the horse
    post_at(1.0, D - 1.3, 1.0, D)                # at the tool bench
    finish_set("int_workshop_cooper", parts, col)


def int_shop_chandler():
    """Swiecarz: the wax vat on its fire, a dipping wheel hung with half-dipped candles, candles in pairs from
    the beams, moulds, tallow blocks."""
    start()
    W, D, H = 6.0, 6.0, 3.4
    parts, col = room(W, D, H, "limewash_b", "flags", "soot", beam_step=1.2)
    # the vat: brick hearth in the back left, copper cauldron, glowing fire door
    VX, VY = -1.9, D - 0.9
    parts.append(box("vhearth", (1.4, 1.2, 0.6), (VX, VY, 0), M("brick"), bevel=0.04, seg=1, wonk=0.03))
    parts.append(box("vdoor", (0.36, 0.02, 0.24), (VX, VY - 0.61, 0.12), EM("fire", 6.0)))
    parts.append(cyl("vat", 0.5, 0.45, (VX, VY, 0.6), MET("copper_pot", 0.35), verts=16, r2=0.56))
    parts.append(cyl("wax", 0.53, 0.01, (VX, VY, 1.0), M("tallow", 0.4), verts=16))
    parts.append(taper_box("vhood", (1.4, 1.2, 0.8), (VX, VY + 0.1, 1.9), M("limewash_b"), top=0.45, bevel=0.03))
    parts.append(box("vflue", (0.5, 0.5, H - 2.7), (VX, VY + 0.3, 2.7), M("limewash_b")))
    col.append(box("c", (1.4, 1.2, 1.1), (VX, VY, 0)))
    lamp("fire", (VX + 0.4, VY - 0.9, 0.5))
    # dipping wheel beside the vat: a post, four arms, rows of candles hanging from each
    DX, DY = -0.3, D - 1.6
    parts.append(cyl("dpost", 0.05, H, (DX, DY, 0), M("wood_dark"), verts=8))
    for k in range(4):
        a = math.tau * k / 4 + 0.3
        parts.append(cbox("darm", (1.3, 0.05, 0.05), (DX + 0.65 * math.cos(a) * 0.5, DY + 0.65 * math.sin(a) * 0.5, 1.9), M("wood_dark"), rot=(0, 0, a)))
        for j in range(5):
            rr = 0.15 + j * 0.11
            cx, cy = DX + rr * math.cos(a), DY + rr * math.sin(a)
            ln = RNG.uniform(0.25, 0.4)
            parts.append(cyl("wick", 0.003, 0.1, (cx, cy, 1.8), M("linen", 0.9), verts=4))
            parts.append(cyl("dipc", 0.015, ln, (cx, cy, 1.8 - ln), M("tallow", 0.5), verts=6, r2=0.01))
    col.append(cyl("c", 0.1, H, (DX, DY, 0), None, verts=6))
    # hanging candles: rods across under the beams, pairs of candles tied by their wicks
    for (y, x0, x1) in ((2.6, -2.6, 2.6), (3.8, 0.8, 2.6), (1.6, 0.6, 2.6)):
        parts.append(cyl("hrod", 0.02, x1 - x0, ((x0 + x1) / 2, y, H - 0.5), M("wood", 0.8), verts=6, rot=(0, math.pi / 2, 0), center=True))
        x = x0 + 0.1
        while x < x1 - 0.05:
            for dy in (-0.03, 0.03):
                ln = RNG.uniform(0.25, 0.35)
                parts.append(cyl("hc", 0.013, ln, (x, y + dy, H - 0.53 - ln), M(RNG.choice(("wax", "tallow")), 0.5), verts=6, r2=0.009))
            x += 0.09
    # moulds in a frame on the right bench, tallow blocks, boxes of finished candles
    BY = 3.0
    parts.append(wl("R", "bench", 2.4, 0.7, 0.08, BY, 0.38, 0.82, M("wood", 0.7)))
    for s_ in (-1, 1):
        parts.append(wl("R", "bleg", 0.08, 0.6, 0.82, BY + s_ * 1.1, 0.38, 0, M("wood_dark")))
    col.append(wl("R", "c", 2.4, 0.7, 0.9, BY, 0.38, 0))
    mx, my = _wpos("R", BY - 0.5, 0.4)
    parts.append(box("mframe", (0.3, 0.7, 0.05), (mx, my, 0.9), M("wood_dark")))
    for i in range(2):
        for j in range(6):
            parts.append(cyl("mould", 0.02, 0.32, (mx - 0.07 + i * 0.14, my - 0.28 + j * 0.11, 0.9), M("pewter", 0.3), verts=6))
    for k in range(4):
        tx, ty = _wpos("R", BY + 0.3 + k * 0.22, 0.4)
        parts.append(box("tallow", (0.18, 0.12, 0.1), (tx, ty, 0.9), M("tallow", 0.6), bevel=0.01, seg=1, wonk=0.01))
    for k in range(3):
        parts.append(box("cbox", (0.5, 0.35, 0.3), (1.9 + (k % 2) * 0.1, 0.7 + k * 0.05, k * 0.3 if k < 2 else 0.0), M("wood", 0.8), bevel=0.02, seg=1))
    col.append(box("c", (0.6, 0.45, 0.6), (1.95, 0.75, 0)))
    ch = counter(parts, col, -1.2, 2.2, 1.8)
    for k in range(4):
        bx = -1.8 + k * 0.3
        for j in range(5):
            parts.append(cyl("bc", 0.013, 0.28, (bx + (j % 3) * 0.03, 2.2 + (j // 3) * 0.03, ch + 0.015), M("wax", 0.5), verts=6, rot=(0, math.pi / 2, 0), center=True))
    candle(parts, -0.5, 2.25, ch)
    lamp("candle", (-0.5, 2.2, ch + 0.5))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 1.9, 1.0, w=1.0, h=1.3)
    lantern(parts, 1.2, 3.2, H - 0.26, 2.3)
    post_at(VX + 0.2, VY - 1.3, VX, VY)       # chandler at the vat
    post_at(DX + 0.9, DY - 0.6, DX, DY)       # dipping
    post(-1.2, 2.9, math.pi)                  # behind the counter
    post_at(*_wpos("R", BY, 1.2), *_wpos("R", BY, 0.3))
    finish_set("int_shop_chandler", parts, col)


# ------------------------------------------------------------------ DRINK, LODGING AND PLEASURE
def back_room(parts, col, BX0, BX1, BD, H, floor="planks", wall="limewash_b", door_u=None, door_w=1.0, door_h=2.1, jambs=True):
    """A room behind the back wall, x from BX0 to BX1, depth BD, reached through an opening in the back wall
    (the caller cuts it: openings={"B": [(u, w, h, False)]}). Returns the back room's y range (y0, y1)."""
    D, t = CTX["D"], CTX["t"]
    y0, y1 = D + t / 2, D + t + BD
    parts.append(box("bslab", (BX1 - BX0 + t * 2, BD + t, 0.3), ((BX0 + BX1) / 2, D + t + BD / 2, -0.32), M("beam")))
    col.append(box("c", (BX1 - BX0 + t * 2, BD + t, 0.4), ((BX0 + BX1) / 2, D + t + BD / 2, -0.4)))
    parts.append(box("bceil", (BX1 - BX0 + t * 2, BD + t, 0.25), ((BX0 + BX1) / 2, D + t + BD / 2, H - 0.4), M("beam")))
    col.append(box("c", (BX1 - BX0 + t * 2, BD + t, 0.25), ((BX0 + BX1) / 2, D + t + BD / 2, H - 0.4)))
    for (sz, loc) in (((t, BD + t, H), (BX0 - t / 2, D + t / 2 + BD / 2, 0)), ((t, BD + t, H), (BX1 + t / 2, D + t / 2 + BD / 2, 0)),
                      ((BX1 - BX0 + 2 * t, t, H), ((BX0 + BX1) / 2, D + t + BD + t / 2, 0))):
        parts.append(box("bwall", sz, loc, M(wall), bevel=0, wonk=0.02, smooth=0))
        col.append(box("c", sz, loc))
    lay_floor(parts, floor, BX0, BX1, D, y1)
    if jambs and door_u is not None:
        for s_ in (-1, 1):
            parts.append(wl("B", "bdjamb", 0.14, 0.1, door_h + 0.05, door_u + s_ * (door_w / 2 + 0.07), 0.03, 0, M("timber"), bevel=0.02, seg=1))
        parts.append(wl("B", "bdlintel", door_w + 0.4, 0.12, 0.18, door_u, 0.04, door_h, M("timber"), bevel=0.02, seg=1))
    return y0, y1


def int_tavern_beerhall():
    """Piwiarnia: low smoke-blackened beams, long tables, casks on a trestle with their taps, the serving hatch,
    a green tiled stove with a bench round it, drunks' benches and the evening's damage."""
    start()
    W, D, H = 11.0, 8.0, 3.4
    parts, col = room(W, D, H, "limewash_b", "flags", "soot", beam_step=1.15, skirt=("plinth", 0.9))
    CTX["H"] = H
    # casks on a trestle along the back wall, taps toward the room; the tapster's counter in front
    for k, cx in enumerate((-4.2, -3.0, -1.8)):
        cask(parts, None, cx, D - 0.75, 0.55, r=0.5, L=1.1, rot=0.0, cradle=True, tap=True)
    parts.append(box("trestle", (3.8, 0.9, 0.12), (-3.0, D - 0.75, 0.43), M("wood_dark"), bevel=0.02, seg=1))
    for tx in (-4.7, -3.0, -1.3):
        for dy in (-0.35, 0.35):
            parts.append(box("tleg", (0.12, 0.12, 0.43), (tx, D - 0.75 + dy, 0), M("wood_dark")))
    col.append(box("c", (3.9, 1.2, 1.8), (-3.0, D - 0.7, 0)))
    for cx in (-4.2, -3.0, -1.8):
        parts.append(cyl("dripb", 0.14, 0.18, (cx, D - 1.42, 0), M("wood", 0.8), verts=10, r2=0.15))
    ch = counter(parts, col, -2.8, D - 2.1, 3.8)
    for k in range(6):
        tankard(parts, -4.3 + k * 0.55, D - 2.15, ch)
    parts.append(box("slate", (0.9, 0.04, 0.6), (-2.8, D - 0.04, 2.1), M("coal", 0.8), bevel=0.01, seg=1))
    for k in range(9):
        parts.append(box("tally", (0.012, 0.01, 0.1), (-3.15 + k * 0.08, D - 0.07, 2.35 - (k // 5) * 0.2), M("flour", 0.9), rot=(0, 0.3 if k % 5 == 4 else 0, 0)))
    # the serving hatch in the right wall: frame, ledge, the kitchen's glow behind, jugs waiting
    HU = D - 2.2
    parts.append(wl("R", "hframe", 1.5, 0.12, 1.2, HU, 0.06, 0.95, M("beam"), bevel=0.02, seg=1))
    parts.append(wl("R", "hvoid", 1.2, 0.02, 0.95, HU, 0.125, 1.07, EM("night_glow", 0.35, 0.9)))
    parts.append(wl("R", "hledge", 1.6, 0.4, 0.07, HU, 0.2, 1.0, M("wood", 0.7), bevel=0.02, seg=1))
    parts.append(wl("R", "hshutter", 1.3, 0.05, 0.6, HU, 0.35, 2.15, M("wood_dark"), rot=(0, 0, 0)))
    for k in range(3):
        jx, jy = _wpos("R", HU - 0.45 + k * 0.4, 0.22)
        parts.append(cyl("jug", 0.08, 0.24, (jx, jy, 1.07), M(("jar", "brick_dark", "pewter")[k], 0.5), verts=10, r2=0.05))
    hx, hy = _wpos("R", HU, -0.3)
    lamp("candle", (hx, hy, 1.5))
    # green tiled stove on the left wall, a bench round it
    tiled_stove(parts, col, -W / 2 + 0.65, 3.8, rot=math.pi / 2, w=1.2, d=1.0, h=2.3)
    for dy in (-1.0, 1.0):
        bench(parts, -W / 2 + 0.55, 3.8 + dy * 1.25, L=1.2, along_y=False)
    # long tables with benches, tankards, a dish of herring, candles
    for tx in (0.2, 3.0):
        table(parts, col, tx, 3.9, L=3.8, w=0.85)
        for sx in (-1, 1):
            bench(parts, tx + sx * 0.66, 3.9, L=3.6)
        for k in range(7):
            tankard(parts, tx + RNG.uniform(-0.28, 0.28), 3.9 + RNG.uniform(-1.6, 1.6), 0.78)
        plate(parts, tx - 0.1, 3.3, 0.78)
        for k in range(3):
            parts.append(blob("herring", (0.04, 0.16, 0.02), (tx - 0.1 + (k - 1) * 0.05, 3.3, 0.8), M("pewter", 0.4), subsurf=1))
        candle(parts, tx, 3.2, 0.78)
        candle(parts, tx, 4.8, 0.78)
    # drunks' benches along the front and right walls; spilt tankards, a tipped stool, a puddle, a lost cap
    bench(parts, 3.5, 0.55, L=2.6, along_y=False)
    bench(parts, W / 2 - 0.35, 1.9, L=2.2)
    parts.append(cyl("spill", 0.045, 0.14, (2.4, 1.2, 0.045), M("pewter", 0.35), verts=8, rot=(0, math.pi / 2, 0.6), center=True))
    parts.append(blob("puddle", (0.5, 0.35, 0.004), (2.3, 1.35, 0.0), M("water", 0.05), subsurf=1))
    stool(parts, 1.8, 2.0, tipped=True)
    parts.append(blob("cap", (0.22, 0.2, 0.08), (W / 2 - 0.35, 2.6, 0.45), M("red_cap", 0.9), subsurf=1))
    parts.append(cyl("spill2", 0.045, 0.14, (-1.2, 5.9, 0.045), M("pewter", 0.35), verts=8, rot=(0, math.pi / 2, -0.3), center=True))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 2.4, 1.1, w=1.0, h=1.2)
    for (lx, ly) in ((0.2, 2.6), (3.0, 5.2), (-2.8, 5.0)):
        lantern(parts, lx, ly, H - 0.26, 2.3)
    post(-2.8, D - 1.5, math.pi)                                     # tapster behind the counter
    for (px, py, tx) in ((-0.46, 3.0, 0.2), (-0.46, 4.6, 0.2), (0.86, 3.6, 0.2), (2.34, 3.2, 3.0), (3.66, 4.4, 3.0), (3.66, 2.8, 3.0)):
        post_at(px, py, tx, py)                                       # drinkers on the benches
    post_at(3.5, 0.6, 3.5, 3.0)                                       # a drunk on the front bench
    post_at(W / 2 - 0.4, 1.6, 0.0, 1.6)                               # another against the right wall
    post_at(*_wpos("R", HU, 0.9), *_wpos("R", HU, 0.0))               # serving girl at the hatch
    post_at(-W / 2 + 0.6, 2.55, -W / 2 + 0.6, 3.8)                    # dozing on the stove bench
    finish_set("int_tavern_beerhall", parts, col)


def newspaper_rack(parts, side, u, z, n=4):
    parts.append(wl(side, "nrail", n * 0.42 + 0.1, 0.05, 0.06, u, 0.03, z, M("wood_dark")))
    for k in range(n):
        uu = u - (n - 1) * 0.21 + k * 0.42
        parts.append(wl(side, "nstick", 0.4, 0.03, 0.025, uu, 0.07, z - 0.08, M("wood", 0.6)))
        parts.append(wl(side, "npaper", 0.34, 0.012, 0.5, uu, 0.075, z - 0.6, M("paper", 0.9)))
        parts.append(wl(side, "nhead", 0.28, 0.004, 0.04, uu, 0.084, z - 0.18, M("ink", 0.9)))
        for j in range(7):
            parts.append(wl(side, "nline", 0.13, 0.003, 0.012, uu - 0.075, 0.084, z - 0.26 - j * 0.04, M("ink", 0.9)))
            parts.append(wl(side, "nline", 0.13, 0.003, 0.012, uu + 0.075, 0.084, z - 0.26 - j * 0.04, M("ink", 0.9)))


def int_tavern_kawiarnia():
    """Kawiarnia: marble tables, the coffee counter with a brass urn and a sugar loaf, newspapers on sticks, a card
    table in the corner, the big mirror, a white tiled stove."""
    start()
    W, D, H = 8.0, 7.0, 3.8
    parts, col = room(W, D, H, "wall_green", "tiles", "flat", skirt=("panel_trim", 0.9))
    for side in "LRB":
        L = W if side == "B" else D
        parts.append(wl(side, "dadorail", L, 0.06, 0.06, 0.0 if side == "B" else L / 2, 0.03, 0.9, M("panel_trim", 0.6)))
    # coffee counter at the back right, marble top: brass urn, pots, cups, the sugar loaf; shelves behind
    CX = 1.5
    ch = counter(parts, col, CX, D - 1.2, 3.4, mat="wood_dark", top="marble")
    UX, UY = CX + 0.9, D - 1.15
    br = MET("brass", 0.25)
    for k in range(3):
        a = math.tau * k / 3
        parts.append(cyl("uleg", 0.015, 0.14, (UX + 0.12 * math.cos(a), UY + 0.12 * math.sin(a), ch), br, verts=6))
    parts.append(sphere("urn", 0.2, (UX, UY, ch + 0.34), br, seg=14, rings=8, zscale=1.25))
    parts.append(cyl("uneck", 0.07, 0.12, (UX, UY, ch + 0.56), br, verts=10, r2=0.1))
    parts.append(sphere("ufin", 0.04, (UX, UY, ch + 0.72), br, seg=8, rings=4))
    parts.append(cyl("utap", 0.015, 0.14, (UX, UY - 0.22, ch + 0.2), br, verts=6, rot=(math.pi / 2, 0, 0), center=True))
    for sx in (-1, 1):
        parts.append(torus("uhandle", 0.06, 0.01, (UX + sx * 0.22, UY, ch + 0.4), br, rot=(math.pi / 2, 0, math.pi / 2), seg=10, mseg=4))
    for k in range(2):
        px = CX - 0.3 + k * 0.35
        parts.append(cyl("cpot", 0.07, 0.2, (px, D - 1.2, ch), M("copper", 0.35), verts=10, r2=0.04))
        parts.append(cbox("cpoth", (0.02, 0.14, 0.02), (px, D - 1.05, ch + 0.1), M("wood_dark")))
    parts.append(cyl("sugar", 0.08, 0.3, (CX - 1.1, D - 1.15, ch + 0.06), M("flour", 0.5), verts=10, r2=0.01))
    parts.append(cyl("sugarp", 0.085, 0.07, (CX - 1.1, D - 1.15, ch), M("icon_blue", 0.8), verts=10))
    parts.append(cyl("tray", 0.2, 0.012, (CX - 0.6, D - 1.3, ch), br, verts=12))
    for k in range(3):
        cup(parts, CX - 0.7 + k * 0.1, D - 1.3 + (k % 2) * 0.08, ch + 0.012)
    for z in (1.4, 1.85):
        parts.append(wl("B", "cshelf", 3.0, 0.28, 0.04, CX, 0.14, z, M("wood_dark")))
        for k in range(10):
            px, py = _wpos("B", CX - 1.35 + k * 0.3, 0.14)
            if k % 3 == 0:
                parts.append(cyl("canister", 0.06, 0.18, (px, py, z + 0.04), M(("copper", "icon_blue", "crimson")[k % 3], 0.4), verts=8))
            else:
                cup(parts, px, py, z + 0.04)
    lamp("candle", (UX - 0.3, UY - 0.2, ch + 0.6))
    candle(parts, CX - 1.5, D - 1.3, ch)
    # marble tables with two chairs each, cups on them
    for (tx, ty) in ((-2.6, 1.9), (1.7, 1.8), (2.8, 3.8), (-0.6, 3.6)):
        round_table(parts, col, tx, ty, r=0.38, h=0.74)
        for a in (0.4, 0.4 + math.pi):
            chair(parts, tx + 0.62 * math.sin(a), ty - 0.62 * math.cos(a), a + math.pi)
        cup(parts, tx + 0.1, ty, 0.74)
        if RNG.random() < 0.6:
            cup(parts, tx - 0.12, ty + 0.08, 0.74)
    candle(parts, -0.6, 3.6, 0.74, h=0.12)
    lamp("candle", (-0.6, 3.6, 1.2))
    # card table in the back left corner: felt, cards, stakes, candles, four chairs
    GX, GY = -2.4, D - 1.5
    parts.append(box("gtable", (1.0, 1.0, 0.72), (GX, GY, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("gfelt", (0.9, 0.9, 0.012), (GX, GY, 0.72), M("felt_green", 0.95)))
    col.append(box("c", (1.0, 1.0, 0.74), (GX, GY, 0)))
    for k in range(10):
        parts.append(box("card", (0.06, 0.09, 0.004), (GX + RNG.uniform(-0.3, 0.3), GY + RNG.uniform(-0.3, 0.3), 0.735), M("paper", 0.6), rot=(0, 0, RNG.uniform(0, 3))))
    for k in range(6):
        parts.append(cyl("coin", 0.012, 0.004, (GX + RNG.uniform(-0.3, 0.3), GY + RNG.uniform(-0.3, 0.3), 0.735), MET("gold", 0.3), verts=8))
    for sx in (-1, 1):
        candle(parts, GX + sx * 0.35, GY + 0.35, 0.735)
    lamp("candle", (GX, GY, 1.4))
    for k in range(4):
        a = math.tau * k / 4
        chair(parts, GX + 0.8 * math.sin(a), GY - 0.8 * math.cos(a), a + math.pi)
    # newspapers on sticks on the left wall, the mirror on the right, the King over the counter end
    newspaper_rack(parts, "L", 3.4, 1.9, n=4)
    mirror(parts, "R", 2.2, 1.2, w=1.2, h=1.7)
    portrait(parts, "B", -0.6, 1.5, w=0.8, h=1.0, coat="crimson")
    # white tiled stove in the front left corner
    tiled_stove(parts, col, -W / 2 + 0.6, 0.9, rot=math.pi / 2, tile="tile_w", trim="stove_trim", w=0.8, d=0.8, h=2.3)
    oil_lamp(parts, 0.2, 3.0, H, H - 1.1)
    oil_lamp(parts, -2.4, D - 1.5, H, H - 1.3)
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 2.0, 1.0, w=1.1, h=1.7)
    post(CX, D - 0.55, math.pi)                                  # the waiter at the urn
    for (tx, ty) in ((-2.6, 1.9), (1.7, 1.8), (2.8, 3.8)):
        post_at(tx + 0.62 * math.sin(0.4), ty - 0.62 * math.cos(0.4), tx, ty)
    for k in range(3):
        a = math.tau * k / 4
        post_at(GX + 0.8 * math.sin(a), GY - 0.8 * math.cos(a), GX, GY)   # card players
    post_at(-W / 2 + 0.9, 3.4, -W / 2, 3.4)                     # reading the Gazette
    finish_set("int_tavern_kawiarnia", parts, col)


def int_tavern_inn():
    """Zajazd: the taproom with its hearth and a counter with the guest ledger and room keys, the coach-yard doors
    with luggage piled by them, and a back room of beds."""
    start()
    W, D, H = 10.0, 7.0, 3.4
    DU = 3.0
    parts, col = room(W, D, H, "limewash", "planks", "beams", openings={"B": [(DU, 1.0, 2.1, False)]}, skirt=("plinth", 0.8))
    CTX["H"] = H
    timber_frame(parts, "LR", H, step=2.2, rail=2.4)
    BX0, BX1, BD = 0.9, 4.9, 4.0
    y0, y1 = back_room(parts, col, BX0, BX1, BD, H, door_u=DU)
    # back room: three beds, a washstand, a chest, a candle, a window
    for k, bx in enumerate((1.6, 2.9, 4.2)):
        bed(parts, col, bx, y1 - 1.05, 0.0, w=0.95, L=1.9, blanket=("crimson", "cloth_blue", "sukmana")[k])
    washstand(parts, col, BX0 + 0.4, y0 + 0.5, math.pi / 2)
    parts.append(box("chest", (0.9, 0.45, 0.45), (4.3, y0 + 0.45, 0), M("wood", 0.8), bevel=0.03, seg=1))
    col.append(box("c", (0.9, 0.45, 0.5), (4.3, y0 + 0.45, 0)))
    candle(parts, 4.3, y0 + 0.45, 0.45, h=0.14)
    lamp("candle", (3.6, y0 + 1.0, 1.2))
    parts.append(box("bwin", (0.05, 0.8, 1.0), (BX1 - 0.03, (y0 + y1) / 2, 1.1), EM("night_sky", 0.5)))
    parts.append(sphere("bwlamp", 0.03, (BX1 - 0.06, (y0 + y1) / 2 + 0.2, 1.35), EM("night_glow", 8.0), seg=6, rings=3))
    # hearth on the right wall
    FU = 2.6
    stone = M("stone")
    parts.append(wl("R", "hearth", 2.0, 0.9, 0.16, FU, 0.45, 0, M("stone_dark"), bevel=0.03, seg=1))
    for s_ in (-1, 1):
        parts.append(wl("R", "cheek", 0.4, 0.8, 1.4, FU + s_ * 0.8, 0.4, 0, stone, bevel=0.05, seg=1, wonk=0.03))
    parts.append(wl("R", "lintel", 2.0, 0.9, 0.4, FU, 0.45, 1.4, stone, bevel=0.05, seg=1, wonk=0.03))
    parts.append(wl("R", "mantel", 2.3, 1.0, 0.1, FU, 0.5, 1.8, M("beam"), bevel=0.03, seg=1))
    parts.append(wl("R", "fireback", 1.2, 0.08, 1.4, FU, 0.05, 0, M("coal", 0.9)))
    hx, hy = _wpos("R", FU, 0.45)
    parts.append(taper_box("hood", (0.9, 2.0, H - 1.9), (hx, hy, 1.9), M("limewash_b"), top=0.7, bevel=0.05, wonk=0.03))
    fire(parts, hx, hy, 0.16, w=0.8)
    col.append(wl("R", "c", 2.0, 0.95, H, FU, 0.47, 0))
    # the innkeeper's counter, back left: the ledger open, quill and ink, a hand bell; room keys on a board
    ch = counter(parts, col, -2.6, D - 1.4, 2.6)
    LX, LY = -2.4, D - 1.45
    parts.append(box("ledgerL", (0.22, 0.32, 0.03), (LX - 0.115, LY, ch), M("paper", 0.8), rot=(0, 0.06, 0)))
    parts.append(box("ledgerR", (0.22, 0.32, 0.03), (LX + 0.115, LY, ch), M("paper", 0.8), rot=(0, -0.06, 0)))
    parts.append(box("ledgerC", (0.48, 0.34, 0.02), (LX, LY, ch - 0.005), M("leather_b", 0.8)))
    for j in range(8):
        for sx in (-1, 1):
            parts.append(box("iline", (0.16, 0.006, 0.002), (LX + sx * 0.115, LY - 0.12 + j * 0.03, ch + 0.031), M("ink", 0.9)))
    parts.append(cyl("inkwell", 0.03, 0.05, (LX + 0.35, LY + 0.05, ch), M("ink", 0.3), verts=8))
    parts.append(cbox("quill", (0.01, 0.01, 0.28), (LX + 0.36, LY + 0.06, ch + 0.16), M("paper", 0.9), rot=(0.4, 0.2, 0)))
    parts.append(cyl("bell", 0.04, 0.06, (LX - 0.5, LY, ch), M("brass", 0.3), verts=10, r2=0.015))
    candle(parts, LX - 0.8, LY + 0.1, ch)
    lamp("candle", (LX - 0.4, LY - 0.2, ch + 0.5))
    parts.append(wl("B", "keyboard", 1.2, 0.04, 0.6, -2.6, 0.02, 1.5, M("plank_b", 0.8)))
    for k in range(8):
        u = -3.05 + (k % 4) * 0.3
        z = 1.95 - (k // 4) * 0.28
        key_shape(parts, "B", u, z, 0.06, s=0.8)
        parts.append(wl("B", "ktag", 0.05, 0.01, 0.07, u, 0.06, z - 0.22, M("wood", 0.6)))
    # the coach-yard doors in the left wall: two leaves, strap hinges, the bar, snow blown in under them
    CU = 3.6
    for s_ in (-1, 1):
        parts.append(wl("L", "cdoor", 1.2, 0.08, 2.7, CU + s_ * 0.61, 0.04, 0, M("wood_dark"), bevel=0.02, seg=1))
        for zz in (0.5, 1.4, 2.3):
            parts.append(wl("L", "cstrap", 0.8, 0.03, 0.08, CU + s_ * 0.75, 0.09, zz, M("iron", 0.6)))
    parts.append(wl("L", "cframe", 2.8, 0.1, 0.25, CU, 0.03, 2.7, M("beam"), bevel=0.02, seg=1))
    parts.append(wl("L", "cbar", 2.6, 0.1, 0.12, CU, 0.14, 1.2, M("wood", 0.8)))
    for s_ in (-1, 1):
        parts.append(wl("L", "cbrack", 0.08, 0.14, 0.2, CU + s_ * 1.1, 0.1, 1.15, M("iron", 0.6)))
    sx_, sy_ = _wpos("L", CU, 0.35)
    parts.append(blob("snowin", (0.5, 2.0, 0.03), (sx_, sy_, 0.0), M("snow", 0.6), subsurf=1, wonk=0.05))
    parts.append(wl("L", "whip", 0.02, 0.02, 1.4, CU - 1.7, 0.08, 0.7, M("leather_b", 0.8)))
    px, py = _wpos("L", CU + 1.7, 0.12)
    parts.append(torus("horn", 0.12, 0.02, (px, py, 1.9), M("brass", 0.3), rot=(0, math.pi / 2, 0), seg=12, mseg=4))
    # luggage by the coach doors: trunks, a portmanteau, a hatbox
    for (lx, ly, lz, s) in ((-4.3, 1.3, 0.0, (0.7, 0.9, 0.5)), (-4.3, 1.3, 0.5, (0.55, 0.7, 0.35)), (-3.7, 0.8, 0.0, (0.5, 0.35, 0.35))):
        parts.append(box("trunk", s, (lx, ly, lz), M(RNG.choice(("leather", "leather_b", "wood_dark")), 0.8), bevel=0.03, seg=1))
        parts.append(box("tband", (s[0] + 0.02, 0.05, s[2] + 0.02), (lx, ly, lz - 0.01), M("iron", 0.6)))
    parts.append(cyl("hatbox", 0.18, 0.2, (-3.8, 1.35, 0), M("cloth_ochre", 0.8), verts=12))
    col.append(box("c", (0.8, 1.0, 0.9), (-4.3, 1.3, 0)))
    # tables and benches, a wall bench
    for (tx, ty) in ((-1.2, 3.0), (1.4, 3.6)):
        table(parts, col, tx, ty, L=1.8, w=0.8)
        for sx in (-1, 1):
            bench(parts, tx + sx * 0.62, ty, L=1.7)
        for k in range(3):
            tankard(parts, tx + RNG.uniform(-0.25, 0.25), ty + RNG.uniform(-0.6, 0.6), 0.78)
        plate(parts, tx + 0.1, ty - 0.3, 0.78)
        candle(parts, tx, ty + 0.2, 0.78)
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 2.6, 1.1, w=1.0, h=1.3)
    lantern(parts, 0.0, 2.2, H - 0.24, 2.3)
    lantern(parts, -2.6, 4.2, H - 0.24, 2.3)
    post(LX, D - 0.8, math.pi)                                # the innkeeper at the ledger
    post_at(LX, D - 2.3, LX, LY)                              # a guest signing in
    for (px, py, tx) in ((-1.82, 3.0, -1.2), (-0.58, 3.4, -1.2), (0.78, 3.6, 1.4), (2.02, 3.2, 1.4)):
        post_at(px, py, tx, py)
    post_at(*_wpos("L", CU, 1.3), *_wpos("L", CU, 0.0))       # the ostler by the coach doors
    post(1.6, y1 - 1.0, math.pi)                              # asleep in the back room
    post_at(3.0, y0 + 1.0, 3.0, y1)                           # guest in the back room
    finish_set("int_tavern_inn", parts, col)


def screen(parts, col, x, y, rot=0.0, mat="wallpaper"):
    p = []
    for k in range(3):
        a = (k - 1) * 0.5
        p.append(cbox("scr", (0.5, 0.03, 1.6), (math.sin(a) * 0.0 + (k - 1) * 0.47, abs(k - 1) * 0.1, 0.85), M(mat, 0.8), rot=(0, 0, -a * 0.6), bevel=0.01, seg=1))
        p.append(cbox("scrf", (0.52, 0.04, 0.05), ((k - 1) * 0.47, abs(k - 1) * 0.1, 1.66), M("wood_dark"), rot=(0, 0, -a * 0.6)))
    parts.append(place(p, x, y, rot))
    col.append(place([box("c", (1.5, 0.3, 1.7), (0, 0.05, 0))], x, y, rot))


def int_salon_brothel():
    """The house with the red lantern: a warm parlour (tiled stove, settees, curtains, the madam's desk), a
    staircase to the rooms above, and one bedroom behind a curtain. Nothing on show but the furniture."""
    start()
    W, D, H = 8.0, 6.5, 4.4
    DU = -2.2
    parts, col = room(W, D, H, "wall_rose", "terracotta", "flat", openings={"B": [(DU, 1.1, 2.2, False)]}, skirt=("panel_trim", 0.25))
    CTX["H"] = H
    for side in "LRB":
        L = W if side == "B" else D
        parts.append(wl(side, "dado", L, 0.03, 0.9, 0.0 if side == "B" else L / 2, 0.015, 0, M("curtain_red", 0.8)))
        parts.append(wl(side, "dadorail", L, 0.06, 0.06, 0.0 if side == "B" else L / 2, 0.03, 0.9, M("panel_trim", 0.6)))
    BX0, BX1, BD = -3.8, -0.4, 3.4
    y0, y1 = back_room(parts, col, BX0, BX1, BD, 3.4, floor="terracotta", wall="wall_rose", door_u=DU, door_w=1.1, door_h=2.2)
    # the curtain drawn aside across the bedroom doorway
    for s_ in (-1, 1):
        parts.append(wl("B", "dcurt", 0.35, 0.12, 2.3, DU + s_ * 0.65, 0.12, 0.0, M("curtain_red", 0.9), bevel=0.04, seg=1, wonk=0.04))
    parts.append(wl("B", "dpelmet", 1.6, 0.14, 0.2, DU, 0.12, 2.2, MET("gold", 0.4), bevel=0.02, seg=1))
    # the bedroom: a curtained bed, a washstand, a chair with a shawl, a mirror, a candle, a screen
    bed(parts, col, -2.6, y1 - 1.1, 0.0, w=1.4, L=2.0, blanket="velvet", canopy="curtain_red")
    washstand(parts, col, -0.85, y1 - 0.5, math.pi)
    chair(parts, -1.0, y0 + 0.8, math.pi / 2 + 0.3, fancy=True)
    parts.append(box("shawl", (0.5, 0.2, 0.02), (-1.0, y0 + 0.8, 0.5), M("zupan_gold", 0.9), bevel=0.01, seg=1, wonk=0.03))
    parts.append(box("bmirror", (0.04, 0.5, 0.7), (BX1 - 0.03, y0 + 1.6, 1.2), MET("mirror", 0.04)))
    parts.append(box("bmframe", (0.03, 0.6, 0.8), (BX1 - 0.015, y0 + 1.6, 1.15), MET("gold", 0.35)))
    screen(parts, col, -3.2, y0 + 0.5, 0.2)
    candle(parts, -0.85, y1 - 0.35, 0.84, h=0.12)
    lamp("candle", (-1.5, y1 - 0.9, 1.3))
    # tiled stove, rose and white, in the front left corner
    tiled_stove(parts, col, -W / 2 + 0.6, 1.1, rot=math.pi / 2, tile="wall_rose", trim="tile_w", w=0.8, d=0.8, h=2.4)
    # settees round a low table with a decanter and glasses; a rug
    rug(parts, -1.3, 3.0, 2.4, 1.8, mat="curtain_red")
    settee(parts, col, -1.3, 4.0, math.pi, L=1.8)
    settee(parts, col, -3.3, 3.0, math.pi / 2, L=1.6)
    parts.append(box("ltable", (0.9, 0.55, 0.42), (-1.3, 2.9, 0), M("wood_dark"), bevel=0.02, seg=1))
    col.append(box("c", (0.9, 0.55, 0.42), (-1.3, 2.9, 0)))
    parts.append(cyl("decanter", 0.07, 0.2, (-1.5, 2.9, 0.42), M("wine", 0.1), verts=10, r2=0.03))
    for k in range(3):
        parts.append(cyl("glass", 0.03, 0.09, (-1.2 + k * 0.12, 2.85, 0.42), M("glass", 0.1), verts=8, r2=0.035))
    candle(parts, -0.95, 3.0, 0.42)
    # windows with heavy curtains
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 2.2, 1.0, w=0.9, h=1.4)
        for s_ in (-1, 1):
            parts.append(wl("F", "curtain", 0.4, 0.14, 2.8, sx * 2.2 + s_ * 0.7, 0.2, 0.0, M("curtain_red", 0.9), bevel=0.05, seg=1, wonk=0.04))
        parts.append(wl("F", "pelmet", 1.8, 0.2, 0.3, sx * 2.2, 0.2, 2.8, MET("gold", 0.4), bevel=0.03, seg=1))
    # the staircase up the right wall to a landing and a shut door: the rooms above
    SX = W / 2 - 0.6
    L_ = stair(parts, col, SX, 1.4, 0.0, width=1.0, rise=2.8, steps=12, run=0.28, rail_sides=(-1,))
    LY0 = 1.4 + L_
    parts.append(box("landing", (1.2, D - LY0, 0.15), (SX - 0.1, (LY0 + D) / 2, 2.65), M("plank", 0.8), bevel=0.02, seg=1))
    col.append(box("c", (1.2, D - LY0, 0.15), (SX - 0.1, (LY0 + D) / 2, 2.65)))
    parts.append(box("lrail", (0.06, D - LY0, 0.06), (SX - 0.66, (LY0 + D) / 2, 3.7), M("wood", 0.8)))
    for k in range(4):
        parts.append(box("lbal", (0.04, 0.04, 0.9), (SX - 0.66, LY0 + 0.1 + k * (D - LY0 - 0.2) / 3, 2.8), M("wood_dark")))
    col.append(box("c", (0.08, D - LY0, 1.0), (SX - 0.66, (LY0 + D) / 2, 2.8)))
    parts.append(wl("B", "updoor", 0.9, 0.06, 2.0, SX, 0.03, 2.8, M("wood_dark"), bevel=0.02, seg=1))
    parts.append(wl("B", "updframe", 1.1, 0.05, 2.15, SX, 0.01, 2.8, M("panel_trim", 0.6)))
    lamp("candle", (SX - 0.3, D - 0.6, 4.0))
    candle(parts, SX + 0.35, D - 0.3, 2.8, h=0.14)
    # the madam's desk on the left wall: ledger, purse, coins, a bell, a candle; her chair
    MU = 4.6
    dx, dy = _wpos("L", MU, 0.4)
    parts.append(box("desk", (0.6, 1.1, 0.76), (dx, dy, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("desktop", (0.66, 1.16, 0.04), (dx, dy, 0.76), M("wood", 0.5)))
    parts.append(box("dledger", (0.24, 0.32, 0.04), (dx, dy - 0.15, 0.8), M("crimson", 0.8)))
    parts.append(blob("purse", (0.12, 0.1, 0.08), (dx + 0.05, dy + 0.25, 0.8), M("velvet", 0.8), subsurf=1))
    for k in range(5):
        parts.append(cyl("coin", 0.012, 0.004 * (k + 1), (dx - 0.1, dy + 0.3, 0.8), MET("gold", 0.3), verts=8))
    parts.append(cyl("bell", 0.035, 0.06, (dx + 0.1, dy + 0.4, 0.8), M("brass", 0.3), verts=10, r2=0.015))
    candle(parts, dx - 0.1, dy - 0.45, 0.8)
    lamp("candle", (dx + 0.2, dy - 0.3, 1.4))
    col.append(box("c", (0.66, 1.16, 0.8), (dx, dy, 0)))
    chair(parts, dx + 0.55, dy, -math.pi / 2, fancy=True)
    mirror(parts, "L", 2.2, 1.3, w=0.7, h=1.1)
    # a birdcage on a stand by the window; a crystal lustre
    parts.append(cyl("bcstand", 0.02, 1.3, (1.3, 0.8, 0), M("brass", 0.3), verts=6))
    parts.append(cyl("bcage", 0.16, 0.32, (1.3, 0.8, 1.3), M("brass", 0.3), verts=10))
    parts.append(sphere("bcdome", 0.16, (1.3, 0.8, 1.62), M("brass", 0.3), seg=10, rings=4, zscale=0.6))
    brass_chandelier(parts, -1.0, 3.0, H, H - 1.2, arms=6, r=0.4)
    post_at(dx + 0.55, dy, dx, dy)                                # the madam at her desk
    post_at(-1.3, 4.0, -1.3, 2.9)                                 # on the settee
    post_at(-3.3, 3.0, -1.3, 3.0)                                 # on the other settee
    post_at(1.0, 1.4, 0.0, 0.3)                                   # the doorman inside the door
    post_at(SX - 0.1, D - 0.5, SX - 0.1, LY0, z=2.8)              # on the landing
    post_at(-1.6, y0 + 1.2, -2.6, y1)                             # in the bedroom
    finish_set("int_salon_brothel", parts, col)


def int_cellar_wine():
    """Winiarnia: a narrow landing inside the door, steps down through an arch into a brick barrel vault lined with
    casks on cradles, a great tun at the end, a tasting table with candles stuck in bottles."""
    start()
    W, D, t = 5.0, 11.0, 0.4
    ZF = -1.6                  # cellar floor
    SP = 0.2                   # vault springing
    PW = 1.4                   # passage width
    LY, SY = 2.4, 4.6          # landing end, foot of the stair
    TOP = SP + W / 2 + 0.1
    CTX.update(W=W, D=D, t=t, H=TOP)
    parts, col = [], []
    brick = "brick"
    # outer walls, floor slab, lid
    for (sz, loc) in (((t, D + 2 * t, TOP - ZF + 0.3), (-W / 2 - t / 2, D / 2, ZF - 0.3)), ((t, D + 2 * t, TOP - ZF + 0.3), (W / 2 + t / 2, D / 2, ZF - 0.3)),
                      ((W + 2 * t, t, TOP - ZF + 0.3), (0, D + t / 2, ZF - 0.3)), ((W + 2 * t, t, -ZF + 0.3), (0, 0, ZF - 0.3))):
        parts.append(box("cwall", sz, loc, M(brick, 0.9), bevel=0, wonk=0.02, smooth=0))
        col.append(box("c", sz, loc))
    v, c = wall("F", TOP, brick, [(0.0, 1.1, 2.2, True)])
    parts.append(v)
    col += c
    col.append(box("c", (1.2, 0.12, 2.2), (0, -t / 2 + 0.06, 0)))
    door_leaf(parts, 1.1, 2.2, True, -t / 2 + 0.10)
    parts.append(box("threshold", (1.2, t + 0.1, 0.04), (0, 0, 0), M("stone_dark"), bevel=0.01, seg=1))
    parts.append(box("lid", (W + 2 * t, D + 2 * t, 0.3), (0, D / 2, TOP), M(brick)))
    col.append(box("c", (W + 2 * t, D + 2 * t, 0.3), (0, D / 2, TOP)))
    parts.append(box("fslab", (W, D - SY, 0.3), (0, (SY + D) / 2, ZF - 0.3), M(brick)))
    col.append(box("c", (W, D - SY + 0.2, 0.4), (0, (SY + D) / 2, ZF - 0.4)))
    paver_floor(parts, -W / 2, W / 2, SY, D, z=ZF)
    # the passage: walls either side from the door to the arch, landing slab, stair
    for sx in (-1, 1):
        xc = sx * (PW / 2 + (W / 2 - PW / 2) / 2)
        parts.append(box("pwall", (W / 2 - PW / 2, SY - t / 2, TOP - ZF), (xc, (t / 2 + SY) / 2, ZF), M(brick, 0.9), bevel=0, wonk=0.015, smooth=0))
        col.append(box("c", (W / 2 - PW / 2, SY - t / 2, TOP - ZF), (xc, (t / 2 + SY) / 2, ZF)))
    parts.append(box("landing", (PW, LY - t / 2, -ZF), (0, (t / 2 + LY) / 2, ZF), M(brick)))
    col.append(box("c", (PW, LY - t / 2 + 0.05, -ZF), (0, (t / 2 + LY) / 2, ZF)))
    paver_floor(parts, -PW / 2, PW / 2, t / 2, LY, a=0.35, b=0.35, mats=("floor_stone", "floor_stone_b"))
    steps = 7
    run = (SY - LY) / steps
    for i in range(steps):
        zt = -(i + 1) * (-ZF) / steps
        yy = LY + run * i
        parts.append(box("tread", (PW, run + 0.02, 0.08), (0, yy + run / 2, zt - 0.08), M("stone", 0.8), bevel=0.02, seg=1, wonk=0.01))
        parts.append(box("riser", (PW - 0.01, 0.03, -ZF / steps + 0.08), (0, yy + 0.015, zt - 0.08), M("stone_dark", 0.8)))
    col.append(flip_y(prism("c", -PW / 2, PW / 2, LY, SY, ZF, 0.0), LY + SY))       # rises toward the door
    parts.append(flip_y(prism("under", -PW / 2, PW / 2, LY, SY, ZF, 0.0, M(brick)), LY + SY))
    parts.append(cyl("hrail", 0.03, SY - LY + 0.4, (PW / 2 - 0.06, (LY + SY) / 2, -0.2 + 0.9), M("iron", 0.5), verts=6,
                     rot=(math.pi / 2 - math.atan2(-ZF, SY - LY), 0, 0), center=True))
    # the vaults: a low one over the passage, the big one over the cellar, a brick arch where they meet
    vault(parts, PW, SY - t / 2, 2.0, brick, y0=t / 2)
    vault(parts, W, D - SY + 0.02, SP, brick, y0=SY - 0.01, ribs=3, rib_mat="brick_dark")
    for sx in (-1, 1):
        parts.append(box("apier", (0.25, 0.3, 2.0 - ZF), (sx * (PW / 2 + 0.12), SY + 0.15, ZF), M("brick_dark", 0.9), bevel=0.02, seg=1))
    parts.append(torus("arch", PW / 2 + 0.12, 0.12, (0, SY + 0.15, 2.0), M("brick_dark", 0.9), rot=(math.pi / 2, 0, 0), seg=16, mseg=4))
    # casks along both walls, ends to the aisle, chalk marks; the great tun at the end
    for sx in (-1, 1):
        for k in range(3):
            cy = SY + 1.0 + k * 1.3
            cask(parts, col, sx * (W / 2 - 0.62), cy, ZF, r=0.45, L=1.05, rot=-sx * math.pi / 2, cradle=True, tap=k == 1)
            candle_bottle(parts, sx * (W / 2 - 0.55), cy + 0.55, ZF + 1.1) if k == 2 else None
    cask(parts, col, 0.0, D - 1.0, ZF, r=0.95, L=1.5, rot=0.0, cradle=True, tap=True)
    parts.append(torus("tunring", 0.6, 0.03, (0, D - 1.77, ZF + 1.13), MET("gold", 0.4), rot=(math.pi / 2, 0, 0), seg=16, mseg=4))
    parts.append(sphere("tunboss", 0.12, (0, D - 1.78, ZF + 1.13), MET("gold", 0.4), seg=10, rings=6))
    # wine racks by the tun: bottles lying
    for sx in (-1, 1):
        rx = sx * 1.75
        parts.append(box("rack", (0.8, 0.4, 1.4), (rx, D - 0.3, ZF), M("wood_dark"), bevel=0.02, seg=1))
        for i in range(4):
            for j in range(4):
                parts.append(cyl("rbot", 0.035, 0.3, (rx - 0.27 + j * 0.18, D - 0.46, ZF + 0.2 + i * 0.3), M("glass_green", 0.2), verts=6, rot=(math.pi / 2, 0, 0), center=True))
        col.append(box("c", (0.8, 0.45, 1.4), (rx, D - 0.3, ZF)))
    # the tasting table, stools, glasses, a jug, candles in bottles
    TX, TY = 0.0, SY + 2.2
    table(parts, col, TX, TY, L=1.2, w=0.7, h=0.8, along_y=True, trestle=False)
    edit_verts(parts[-1], lambda co: setattr(co, "z", co.z + ZF))
    col[-1].location.z += 0
    edit_verts(col[-1], lambda co: setattr(co, "z", co.z + ZF))
    for k in range(3):
        parts.append(cyl("goblet", 0.035, 0.08, (TX - 0.15 + k * 0.15, TY - 0.3 + k * 0.2, ZF + 0.86), M("wine", 0.1), verts=8, r2=0.045))
        parts.append(cyl("gstem", 0.008, 0.06, (TX - 0.15 + k * 0.15, TY - 0.3 + k * 0.2, ZF + 0.8), M("glass", 0.1), verts=6))
    parts.append(cyl("jug", 0.08, 0.24, (TX + 0.15, TY + 0.3, ZF + 0.8), M("jar", 0.5), verts=10, r2=0.05))
    candle_bottle(parts, TX - 0.1, TY + 0.1, ZF + 0.8)
    candle_bottle(parts, TX + 0.1, TY - 0.45, ZF + 0.8)
    lamp("candle", (TX, TY, ZF + 1.5))
    for (sx, sy) in ((-0.65, TY - 0.3), (0.65, TY + 0.2), (-0.6, TY + 0.45)):
        n0 = len(parts)
        stool(parts, sx, sy, h=0.5)
        edit_verts(parts[-1], lambda co: setattr(co, "z", co.z + ZF))
    # wall niches with candles in bottles; a lantern at the arch and one by the tun
    for (sx, yy) in ((-1, SY + 3.3), (1, SY + 2.0)):
        candle_bottle(parts, sx * (W / 2 - 0.5), yy, ZF + 1.1)
        lamp("candle", (sx * (W / 2 - 0.7), yy, ZF + 1.7))
    candle_bottle(parts, PW / 2 - 0.2, 0.6, 0.0)
    lamp("candle", (0.3, 0.9, 0.6))
    parts.append(box("pbracket", (0.05, 0.3, 0.05), (-PW / 2 + 0.15, 3.0, 1.7), M("iron", 0.6)))
    parts.append(box("plglass", (0.16, 0.16, 0.24), (-PW / 2 + 0.2, 3.0, 1.45), EM("lamp_glass", 6.0)))
    parts.append(taper_box("plcap", (0.22, 0.22, 0.1), (-PW / 2 + 0.2, 3.0, 1.69), M("iron", 0.6), top=0.3))
    lamp("lantern", (-PW / 2 + 0.35, 3.0, 1.5))
    parts.append(box("udoor", (0.06, 0.8, 1.7), (-W / 2 + 0.03, 9.6, ZF), M("wood_dark", 0.8), bevel=0.01, seg=1))
    parts.append(box("uframe", (0.04, 1.0, 1.85), (-W / 2 + 0.01, 9.6, ZF), M("brick_dark", 0.9)))
    parts.append(torus("uring", 0.05, 0.01, (-W / 2 + 0.08, 9.3, ZF + 0.9), M("iron", 0.5), rot=(0, math.pi / 2, 0), seg=8, mseg=3))
    exit_marker("undercroft", (-W / 2 + 0.6, 9.6, ZF), math.pi / 2)
    lantern(parts, 0.0, SY + 0.9, TOP, 1.2)
    lantern(parts, 0.0, D - 2.3, TOP, 1.4)
    CTX["surface"] = "stone"
    post_at(TX + 0.6, TY - 0.3, TX, TY, z=ZF)       # the vintner at the tasting table
    post_at(TX - 0.65, TY - 0.3, TX, TY, z=ZF)       # tasters
    post_at(TX - 0.6, TY + 0.45, TX, TY, z=ZF)
    post_at(0.9, D - 2.4, 0.0, D - 1.0, z=ZF)        # the cellar boy at the tun
    finish_set("int_cellar_wine", parts, col)


# ------------------------------------------------------------------ LODGINGS: three flats
def int_flat_garret():
    """A poor garret under the roof slope: a straw pallet, a cold stove, a crate for a table, one candle stub,
    washing on a string and the plaster coming off the laths."""
    start()
    W, D, H = 5.0, 4.5, 2.7
    parts, col = room(W, D, H, "limewash_b", "planks", "flat")
    CTX["H"] = H
    # the roof slope over the left side, rafters under it; a collider keeps heads out of the low part
    ang = math.atan2(1.5, 3.1)
    ln = math.hypot(1.5, 3.1)
    parts.append(cbox("slope", (ln + 0.1, D + 0.4, 0.1), (-W / 2 + 1.55, D / 2, 1.2 + 0.75 + 0.04), M("plank_b", 0.9), rot=(0, -ang, 0)))
    for k in range(5):
        y = 0.4 + k * (D - 0.8) / 4
        parts.append(cbox("rafter", (ln, 0.12, 0.14), (-W / 2 + 1.55, y, 1.2 + 0.75 - 0.07), M("beam"), rot=(0, -ang, 0), bevel=0.02, seg=1, wonk=0.02))
    parts.append(box("purlin", (0.16, D, 0.16), (-W / 2 + 0.1, D / 2, 1.05), M("beam"), bevel=0.02, seg=1))
    col.append(box("c", (1.15, D, H), (-W / 2 + 0.58, D / 2, 0)))
    # plaster off the laths in patches, damp stains
    for (side, u, z, w, h) in (("R", 1.4, 1.5, 0.6, 0.4), ("B", 1.2, 0.5, 0.5, 0.3), ("F", 1.6, 1.8, 0.4, 0.3)):
        parts.append(wl(side, "lathpatch", w, 0.012, h, u, 0.006, z, M("wood_dark", 0.9)))
        for j in range(int(h / 0.06)):
            parts.append(wl(side, "lath", w * 0.9, 0.01, 0.03, u, 0.014, z + 0.02 + j * 0.06, M("plank_b", 0.9)))
    parts.append(wl("R", "damp", 1.2, 0.006, 0.7, 3.2, 0.004, 1.8, M("soot_wall", 0.95), wonk=0.03))
    # the straw pallet under the slope, a ragged blanket, a rolled coat for a pillow
    parts.append(blob("pallet", (0.95, 1.9, 0.16), (-W / 2 + 0.6, 2.4, 0), M("straw_bed", 0.95), subsurf=1, wonk=0.04))
    parts.append(box("rblanket", (0.9, 1.1, 0.05), (-W / 2 + 0.65, 2.1, 0.14), M("sukmana", 0.95), bevel=0.03, seg=2, wonk=0.05))
    parts.append(cyl("rollcoat", 0.1, 0.6, (-W / 2 + 0.6, 3.2, 0.2), M("brown_coat", 0.9), verts=8, rot=(0, math.pi / 2, 0), center=True))
    for k in range(6):
        parts.append(blob("straw", (0.18, 0.08, 0.01), (-W / 2 + 1.2 + RNG.uniform(0, 0.4), 1.5 + RNG.uniform(0, 1.8), 0), M("straw_bed", 0.95), subsurf=1))
    # the cold stove in the back right, ash spilt, an empty pot on it
    iron_stove(parts, col, 1.6, D - 0.5, lit=False)
    parts.append(blob("ash", (0.5, 0.35, 0.01), (1.6, D - 0.95, 0), M("stone_dark", 0.95), subsurf=1))
    parts.append(cyl("pot", 0.12, 0.14, (1.6, D - 0.5, 0.82), M("iron", 0.6), verts=10))
    # a crate for a table: a candle stub, a crust, a tin cup; a stool, a broken chair
    parts.append(box("crate", (0.6, 0.45, 0.5), (0.3, 2.6, 0), M("wood", 0.9), bevel=0.02, seg=1, wonk=0.03))
    for k in range(3):
        parts.append(box("slat", (0.62, 0.02, 0.08), (0.3, 2.37, 0.08 + k * 0.16), M("plank_b", 0.9)))
    col.append(box("c", (0.6, 0.45, 0.5), (0.3, 2.6, 0)))
    rushlight(parts, 0.15, 2.6, 0.5)
    parts.append(blob("crust", (0.12, 0.08, 0.05), (0.42, 2.55, 0.5), M("crust_b", 0.8), subsurf=1))
    parts.append(cyl("tincup", 0.04, 0.08, (0.45, 2.72, 0.5), M("pewter", 0.4), verts=8))
    stool(parts, 0.3, 1.9, h=0.42)
    stool(parts, 1.5, 1.4, h=0.45, tipped=True)
    # washing on a string across the room, a bucket, a chamber pot, a bundle, a holy picture
    parts.append(cbox("line", (W - 1.6, 0.006, 0.006), (0.7, 3.6, 2.0), M("canvas", 0.9)))
    for k, cm in enumerate(("linen", "sukmana", "linen")):
        parts.append(box("rag", (0.35, 0.02, 0.5), (0.0 + k * 0.6, 3.6, 1.5), M(cm, 0.95), bevel=0.01, seg=1, wonk=0.04))
    parts.append(cyl("bucket", 0.16, 0.3, (2.1, 1.1, 0), M("wood", 0.8), verts=10, r2=0.18))
    parts.append(cyl("cpot", 0.12, 0.14, (-1.2, 0.8, 0), M("jar", 0.5), verts=10, r2=0.14))
    parts.append(blob("bundle", (0.5, 0.4, 0.35), (1.9, 3.2, 0), M("sack", 0.95), subsurf=1, wonk=0.04))
    parts.append(wl("B", "holy", 0.3, 0.02, 0.4, -0.4, 0.01, 1.5, M("icon_blue", 0.7)))
    parts.append(wl("B", "holyf", 0.14, 0.01, 0.2, -0.4, 0.025, 1.6, MET("gold", 0.4)))
    # a small window in the gable, the moon in it
    fake_window(parts, "B", 0.8, 1.2, w=0.6, h=0.7, sill=True)
    post_at(-W / 2 + 0.6, 2.4, 0.0, 2.4)          # asleep on the pallet
    post_at(0.3, 1.8, 0.3, 2.6)                   # on the stool at the crate
    finish_set("int_flat_garret", parts, col)


def tall_clock(parts, col, side, u):
    x, y = _wpos(side, u, 0.2)
    parts.append(box("cbase", (0.5, 0.36, 0.5), (x, y, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("ctrunk", (0.36, 0.28, 1.1), (x, y, 0.5), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("chood", (0.5, 0.36, 0.55), (x, y, 1.6), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("ccrest", (0.54, 0.4, 0.1), (x, y, 2.15), MET("gold", 0.35), bevel=0.02, seg=1))
    parts.append(cyl("cface", 0.17, 0.02, (x, y - 0.18, 1.87), M("tile_w", 0.3), verts=16, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(cbox("chand", (0.01, 0.005, 0.12), (x, y - 0.195, 1.91), M("ink", 0.5)))
    parts.append(cbox("chand", (0.08, 0.005, 0.01), (x + 0.04, y - 0.195, 1.87), M("ink", 0.5)))
    parts.append(cyl("cbob", 0.07, 0.01, (x, y - 0.145, 0.8), M("brass", 0.3), verts=12, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(box("cwin", (0.2, 0.01, 0.6), (x, y - 0.14, 0.62), M("coal", 0.3)))
    col.append(box("c", (0.5, 0.4, 2.25), (x, y, 0)))


def int_flat_burgher():
    """A burgher's parlour: the tiled stove going, the tall clock, a table laid for tea, the glass cabinet with the
    good porcelain, the couple's portraits over the sofa."""
    start()
    W, D, H = 6.0, 5.5, 3.1
    parts, col = room(W, D, H, "wallpaper", "parquet", "flat", skirt=("panel_trim", 0.2))
    CTX["H"] = H
    for side in "LRB":
        L = W if side == "B" else D
        parts.append(wl(side, "dado", L, 0.03, 0.85, 0.0 if side == "B" else L / 2, 0.015, 0, M("panel", 0.7)))
        parts.append(wl(side, "dadorail", L, 0.06, 0.06, 0.0 if side == "B" else L / 2, 0.03, 0.85, M("panel_trim", 0.6)))
    tiled_stove(parts, col, -W / 2 + 0.75, D - 0.75, rot=math.pi * 0.75, w=0.9, d=0.9, h=2.5)
    tall_clock(parts, col, "B", 1.2)
    # the tea table: cloth, pot, cups, sugar, a candlestick; four chairs round it, a rug under
    TX, TY = 0.5, 2.9
    rug(parts, TX, TY, 2.4, 2.0)
    table(parts, col, TX, TY, L=1.1, w=0.9, h=0.76, trestle=False)
    parts.append(box("tcloth", (1.0, 1.2, 0.2), (TX, TY, 0.58), M("linen", 0.9), bevel=0.02, seg=1))
    parts.append(sphere("teapot", 0.08, (TX, TY + 0.1, 0.86), M("tile_w", 0.2), seg=10, rings=6))
    parts.append(cbox("tspout", (0.02, 0.1, 0.02), (TX, TY - 0.0, 0.88), M("tile_w", 0.2), rot=(0.6, 0, 0)))
    for (dx, dy) in ((-0.25, -0.3), (0.25, -0.3), (-0.25, 0.35), (0.25, 0.35)):
        cup(parts, TX + dx, TY + dy, 0.78)
    parts.append(cyl("sugarb", 0.05, 0.06, (TX + 0.15, TY + 0.1, 0.78), M("tile_w", 0.2), verts=10))
    candle(parts, TX - 0.15, TY + 0.05, 0.78)
    lamp("candle", (TX, TY, 1.4))
    for (dx, dy, r) in ((0, -0.75, 0.0), (0, 0.75, math.pi), (-0.7, 0, -math.pi / 2), (0.7, 0, math.pi / 2)):
        chair(parts, TX + dx, TY + dy, r, fancy=True)
    # the sofa on the left wall under the portraits; the glass cabinet on the right wall
    settee(parts, col, -W / 2 + 0.45, 2.4, math.pi / 2, L=1.7)
    portrait(parts, "L", 1.9, 1.5, w=0.55, h=0.7, coat="navy")
    portrait(parts, "L", 2.9, 1.5, w=0.55, h=0.7, sitter="plaster_rose", coat="crimson")
    CU = 3.2
    parts.append(wl("R", "cab", 1.2, 0.45, 1.9, CU, 0.23, 0, M("wood_dark"), bevel=0.02, seg=1))
    parts.append(wl("R", "cabtop", 1.3, 0.5, 0.1, CU, 0.25, 1.9, M("wood_dark"), bevel=0.03, seg=1))
    for i in range(3):
        z = 0.9 + i * 0.35
        parts.append(wl("R", "cabsh", 1.1, 0.4, 0.02, CU, 0.3, z, M("wood", 0.6)))
        for k in range(4):
            px, py = _wpos("R", CU - 0.4 + k * 0.27, 0.36)
            if i == 1:
                parts.append(cyl("plate", 0.1, 0.012, (px, py + 0.04, z + 0.12), M("tile_w", 0.2), verts=12, rot=(0, math.pi / 2 + 0.2, 0), center=True))
            else:
                cup(parts, px, py, z + 0.02, mat="tile_w" if k % 2 else "icon_blue")
    for k in range(3):
        parts.append(wl("R", "cabmull", 0.03, 0.02, 1.0, CU - 0.55 + k * 0.55, 0.47, 0.85, M("wood_dark")))
    col.append(wl("R", "c", 1.3, 0.5, 2.0, CU, 0.25, 0))
    # chest of drawers by the door with a mirror over it and two candlesticks
    parts.append(wl("R", "chest", 1.1, 0.5, 0.85, 1.2, 0.25, 0, M("wood_dark"), bevel=0.02, seg=1))
    for k in range(3):
        parts.append(wl("R", "drawer", 1.0, 0.02, 0.22, 1.2, 0.51, 0.08 + k * 0.26, M("wood", 0.6), bevel=0.01, seg=1))
    col.append(wl("R", "c", 1.1, 0.5, 0.9, 1.2, 0.25, 0))
    mirror(parts, "R", 1.2, 1.35, w=0.7, h=0.9)
    for du in (-0.35, 0.35):
        cx, cy = _wpos("R", 1.2 + du, 0.25)
        candle(parts, cx, cy, 0.85)
    parts.append(wl("B", "cross", 0.05, 0.04, 0.45, -1.4, 0.02, 1.8, M("wood_dark")))
    parts.append(wl("B", "cross", 0.26, 0.04, 0.05, -1.4, 0.02, 2.1, M("wood_dark")))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 1.9, 1.0, w=0.9, h=1.4)
        for s_ in (-1, 1):
            parts.append(wl("F", "curtain", 0.3, 0.1, 2.3, sx * 1.9 + s_ * 0.6, 0.18, 0.2, M("cloth_green", 0.9), bevel=0.04, seg=1, wonk=0.03))
    post_at(-1.8, D - 1.6, TX, TY)                     # the master by the stove
    post_at(TX, TY + 0.75, TX, TY)                     # his wife at the tea table
    post_at(TX - 0.7, TY, TX, TY)                      # a guest
    post_at(1.4, 1.0, 0.0, 0.3)                        # the maid by the door
    finish_set("int_flat_burgher", parts, col)


def orrery(parts, x, y, z):
    br = M("brass", 0.3)
    parts.append(cyl("obase", 0.14, 0.04, (x, y, z), M("wood_dark"), verts=12))
    parts.append(cyl("ostem", 0.015, 0.3, (x, y, z + 0.04), br, verts=6))
    parts.append(sphere("osun", 0.05, (x, y, z + 0.36), MET("gold", 0.25), seg=10, rings=6))
    parts.append(torus("oring", 0.26, 0.006, (x, y, z + 0.34), br, seg=24, mseg=4))
    parts.append(torus("omer", 0.26, 0.006, (x, y, z + 0.34), br, rot=(math.pi / 2, 0, 0.5), seg=24, mseg=4))
    parts.append(torus("omer", 0.26, 0.006, (x, y, z + 0.34), br, rot=(math.pi / 2, 0, 2.1), seg=24, mseg=4))
    for k, (r, pr, pm) in enumerate(((0.09, 0.012, "copper"), (0.13, 0.016, "tile_ochre"), (0.17, 0.018, "icon_blue"), (0.22, 0.014, "crimson"))):
        a = k * 1.9 + 0.4
        parts.append(cbox("oarm", (r, 0.005, 0.005), (x + r / 2 * math.cos(a), y + r / 2 * math.sin(a), z + 0.32), br, rot=(0, 0, a)))
        parts.append(cyl("opin", 0.003, 0.03, (x + r * math.cos(a), y + r * math.sin(a), z + 0.32), br, verts=4))
        parts.append(sphere("oplanet", pr, (x + r * math.cos(a), y + r * math.sin(a), z + 0.36), M(pm, 0.4), seg=8, rings=4))


def int_flat_scholar():
    """A scholar's room: books to the ceiling, the desk under the window heaped with papers, an orrery, a globe,
    a telescope, a narrow bed with more books on it."""
    start()
    W, D, H = 5.5, 5.0, 3.0
    parts, col = room(W, D, H, "limewash", "planks", "beams", beam_step=1.25, summer=False)
    CTX["H"] = H
    bookcase(parts, col, "B", 0.0, 5.2, H=2.55, shelves=7)
    bookcase(parts, col, "L", 3.1, 2.9, H=2.55, shelves=7)
    # the desk under the right window: an open folio, papers, ink and quill, spectacles, a book stack, a candle
    fake_window(parts, "R", 2.6, 1.05, w=0.9, h=1.2)
    DU = 2.6
    dx, dy = _wpos("R", DU, 0.45)
    parts.append(box("desk", (0.8, 1.5, 0.05), (dx, dy, 0.74), M("wood", 0.6), bevel=0.02, seg=1))
    for sy in (-1, 1):
        parts.append(box("dped", (0.7, 0.4, 0.74), (dx, dy + sy * 0.52, 0), M("wood_dark"), bevel=0.02, seg=1))
    col.append(box("c", (0.8, 1.5, 0.8), (dx, dy, 0)))
    parts.append(box("folioL", (0.3, 0.22, 0.02), (dx - 0.05, dy - 0.12, 0.79), M("paper", 0.8), rot=(0.05, 0, 0)))
    parts.append(box("folioR", (0.3, 0.22, 0.02), (dx - 0.05, dy + 0.12, 0.79), M("paper", 0.8), rot=(-0.05, 0, 0)))
    for j in range(7):
        for sy in (-1, 1):
            parts.append(box("fline", (0.005, 0.16, 0.002), (dx - 0.16 + j * 0.035, dy + sy * 0.12, 0.812), M("ink", 0.9)))
    for k in range(9):
        parts.append(box("paper", (0.2, 0.28, 0.003), (dx + RNG.uniform(-0.3, 0.25), dy + RNG.uniform(-0.6, 0.6), 0.79 + k * 0.003), M("paper", 0.9), rot=(0, 0, RNG.uniform(-0.6, 0.6))))
    parts.append(cyl("inkwell", 0.03, 0.05, (dx + 0.2, dy + 0.45, 0.79), M("ink", 0.3), verts=8))
    parts.append(cbox("quill", (0.01, 0.01, 0.3), (dx + 0.21, dy + 0.46, 0.96), M("paper", 0.9), rot=(0.3, -0.3, 0)))
    for sx in (-1, 1):
        parts.append(torus("spect", 0.02, 0.003, (dx + 0.1, dy - 0.45 + sx * 0.025, 0.795), M("brass", 0.3), seg=8, mseg=3))
    for k in range(5):
        parts.append(box("dbook", (0.22, 0.3, 0.05), (dx + 0.15, dy - 0.55, 0.79 + k * 0.05), M(RNG.choice(("leather", "leather_b", "crimson")), 0.8), rot=(0, 0, RNG.uniform(-0.2, 0.2))))
    candle(parts, dx + 0.2, dy + 0.2, 0.79)
    lamp("candle", (dx - 0.1, dy + 0.1, 1.3))
    chair(parts, dx - 0.65, dy, -math.pi / 2)
    # the orrery on a small round table, the globe on its stand
    round_table(parts, col, 0.6, 2.9, r=0.35, h=0.72, top="wood_dark", base="wood_dark", tripod=True)
    orrery(parts, 0.6, 2.9, 0.72)
    GX, GY = -1.4, 1.2
    for k in range(3):
        a = math.tau * k / 3
        parts.append(cbox("gleg", (0.03, 0.03, 0.8), (GX + 0.14 * math.cos(a), GY + 0.14 * math.sin(a), 0.4), M("wood_dark"), rot=(0.12 * math.sin(a), -0.12 * math.cos(a), 0)))
    parts.append(torus("ghoriz", 0.3, 0.02, (GX, GY, 0.82), M("wood", 0.6), seg=20, mseg=4))
    parts.append(sphere("globe", 0.26, (GX, GY, 0.84), M("paper", 0.6), seg=16, rings=10))
    for (bx, by, bz, s) in ((GX + 0.08, GY - 0.1, 0.84, (0.12, 0.2, 0.3)), (GX - 0.1, GY + 0.1, 0.9, (0.1, 0.14, 0.2)), (GX + 0.1, GY + 0.12, 0.7, (0.1, 0.1, 0.16))):
        parts.append(blob("land", s, (bx, by, bz), M("cloth_ochre", 0.8), subsurf=1))
    parts.append(torus("gmer", 0.29, 0.008, (GX, GY, 0.84), M("brass", 0.3), rot=(math.pi / 2, 0.4, 0), seg=20, mseg=4))
    col.append(cyl("c", 0.32, 1.1, (GX, GY, 0), None, verts=6))
    # telescope on a tripod by the front window
    TX, TY = 1.6, 0.9
    for k in range(3):
        a = math.tau * k / 3 + 0.3
        parts.append(cbox("tleg", (0.025, 0.025, 1.3), (TX + 0.18 * math.cos(a), TY + 0.18 * math.sin(a), 0.63), M("wood", 0.7), rot=(0.15 * math.sin(a), -0.15 * math.cos(a), 0)))
    parts.append(cyl("tube", 0.045, 0.9, (TX, TY - 0.1, 1.35), M("brass", 0.3), verts=10, r2=0.035, rot=(1.2, 0, 0), center=True))
    fake_window(parts, "F", 1.6, 1.0, w=0.9, h=1.3)
    # narrow bed in the front left, books on the blanket and on the floor; a small iron stove going
    bed(parts, col, -2.3, 2.9, 0.0, w=0.8, L=1.9, blanket="cloth_blue", posts=False)
    for k in range(3):
        parts.append(box("bbook", (0.2, 0.28, 0.05), (-2.3 + RNG.uniform(-0.15, 0.15), 2.6 + k * 0.15, 0.66), M(RNG.choice(("leather", "crimson")), 0.8), rot=(0, 0, RNG.uniform(-0.5, 0.5))))
    for k in range(6):
        parts.append(box("fbook", (0.22, 0.3, 0.06), (-0.9, 3.8, k * 0.06), M(RNG.choice(("leather", "leather_b", "icon_green", "crimson")), 0.8), rot=(0, 0, RNG.uniform(-0.3, 0.3))))
    iron_stove(parts, col, 1.9, D - 0.9, lit=True)
    lantern(parts, 0.0, 2.3, H - 0.24, 2.0)
    post_at(dx - 0.65, dy, dx, dy)                   # the scholar at his desk
    post_at(0.6, 2.2, 0.6, 2.9)                      # a visitor at the orrery
    finish_set("int_flat_scholar", parts, col)


# ------------------------------------------------------------------ THE SMITHY AND THE WATCH
def int_workshop_forge():
    """Kuznia: a raised hearth roaring under its hood, the great bellows, the anvil, the quench trough, racks of
    tongs, horseshoes and wheel tyres, soot on everything."""
    start()
    W, D, H = 8.0, 7.0, 4.2
    parts, col = room(W, D, H, "soot_wall", "earth", "soot", beam_step=1.5)
    CTX["H"] = H
    HX, HY = 0.2, D - 0.85
    parts.append(box("hearth", (2.4, 1.5, 0.8), (HX, HY, 0), M("brick"), bevel=0.05, seg=1, wonk=0.03))
    parts.append(box("htop", (2.5, 1.6, 0.1), (HX, HY, 0.8), M("stone_dark"), bevel=0.03, seg=1))
    parts.append(box("coals", (1.0, 0.8, 0.06), (HX, HY - 0.15, 0.9), EM("fire", 7.0)))
    for k in range(10):
        parts.append(blob("coal", (0.15, 0.12, 0.08), (HX + RNG.uniform(-0.6, 0.6), HY - 0.15 + RNG.uniform(-0.45, 0.35), 0.92), M("coal", 0.9), subsurf=1))
    for k in range(5):
        parts.append(cyl("flame", 0.08, RNG.uniform(0.25, 0.45), (HX + RNG.uniform(-0.3, 0.3), HY - 0.15 + RNG.uniform(-0.2, 0.2), 0.94), EM("flame", 10.0), verts=6, r2=0.0))
    parts.append(cbox("workpiece", (0.6, 0.03, 0.03), (HX + 0.5, HY - 0.5, 0.97), EM("fire", 5.0), rot=(0, 0, 0.3)))
    parts.append(taper_box("hood", (2.6, 1.6, 1.3), (HX, HY + 0.05, 2.1), M("brick_dark"), top=0.4, bevel=0.05, wonk=0.03))
    parts.append(box("flue", (1.0, 0.7, H - 3.4), (HX, HY + 0.3, 3.4), M("brick_dark")))
    for s_ in (-1, 1):
        parts.append(box("hpost", (0.22, 0.22, 1.3), (HX + s_ * 1.1, HY - 0.6, 0.8), M("brick")))
    col.append(box("c", (2.5, 1.6, H), (HX, HY, 0)))
    lamp("forge", (HX, HY - 0.9, 1.3))
    # great bellows to the left of the hearth, the lever and its chain
    BX = HX - 2.1
    parts.append(box("bstand", (0.9, 1.4, 0.7), (BX, HY, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("bellows", (0.8, 1.5, 0.35), (BX, HY, 0.75), M("leather", 0.9), bevel=0.08, seg=2, wonk=0.02, rot=(0.12, 0, 0)))
    parts.append(box("bboard", (0.85, 1.55, 0.05), (BX, HY, 1.1), M("wood_dark"), rot=(0.12, 0, 0)))
    parts.append(cbox("blever", (0.08, 2.4, 0.08), (BX, HY - 1.0, 2.2), M("wood", 0.8), rot=(-0.35, 0, 0)))
    parts.append(cyl("bchain", 0.01, 0.9, (BX, HY - 2.0, 1.2), M("iron", 0.6), verts=4))
    parts.append(box("bpost", (0.15, 0.15, 2.6), (BX, HY + 0.4, 0), M("wood_dark")))
    col.append(box("c", (0.9, 1.5, 1.2), (BX, HY, 0)))
    # the anvil on its stump before the hearth, hammers resting on it
    AX, AY = 0.3, D - 3.0
    iron = M("iron", 0.45)
    parts.append(cyl("stump", 0.38, 0.52, (AX, AY, 0), M("wood", 0.9), verts=12, bevel=0.03, seg=1, wonk=0.02))
    parts.append(taper_box("abase", (0.36, 0.26, 0.16), (AX, AY, 0.52), iron, top=0.7))
    parts.append(box("awaist", (0.2, 0.16, 0.14), (AX, AY, 0.68), iron))
    parts.append(box("aface", (0.56, 0.2, 0.12), (AX + 0.05, AY, 0.82), iron, bevel=0.015, seg=1))
    parts.append(cyl("ahorn", 0.085, 0.36, (AX - 0.4, AY, 0.88), iron, verts=10, r2=0.01, rot=(0, -math.pi / 2, 0), center=True))
    parts.append(box("hhead", (0.16, 0.06, 0.06), (AX + 0.15, AY + 0.03, 0.94), iron))
    parts.append(cbox("hhandle", (0.035, 0.4, 0.035), (AX + 0.15, AY - 0.18, 0.97), M("wood", 0.8)))
    col.append(cyl("c", 0.4, 0.94, (AX, AY, 0), None, verts=8))
    # quench trough to the right of the hearth; rack of tongs and hammers above it
    QX = HX + 2.1
    parts.append(box("trough", (1.3, 0.6, 0.6), (QX, HY + 0.2, 0), M("stone", 0.8), bevel=0.03, seg=1, wonk=0.02))
    parts.append(box("twater", (1.1, 0.45, 0.01), (QX, HY + 0.2, 0.55), M("water", 0.05)))
    col.append(box("c", (1.3, 0.6, 0.6), (QX, HY + 0.2, 0)))
    parts.append(wl("B", "track", 1.8, 0.06, 0.08, QX, 0.05, 2.1, M("wood_dark")))
    for k in range(8):
        u = QX - 0.8 + k * 0.22
        if k % 2:
            parts.append(wl("B", "tong", 0.02, 0.03, 0.8, u - 0.015, 0.09, 1.3, iron))
            parts.append(wl("B", "tong", 0.02, 0.03, 0.8, u + 0.015, 0.09, 1.3, iron))
        else:
            parts.append(wl("B", "hhandle", 0.03, 0.03, 0.45, u, 0.09, 1.65, M("wood", 0.8)))
            parts.append(wl("B", "hhead", 0.14, 0.06, 0.06, u, 0.09, 2.1 - 0.06, iron))
    # horseshoes on the right wall, wheel tyres leaning on the left, a grindstone, the coal heap, iron stock
    for r in range(3):
        for k in range(8):
            sx, sy = _wpos("R", 2.0 + k * 0.28, 0.04)
            parts.append(torus("shoe", 0.07, 0.014, (sx, sy, 1.4 + r * 0.3), iron, rot=(math.pi / 2, 0, math.pi / 2), seg=10, mseg=4))
    parts.append(wl("R", "srail", 2.4, 0.04, 0.05, 3.0, 0.02, 2.05, M("wood_dark")))
    for k in range(3):
        wx, wy = _wpos("L", 2.0 + k * 0.25, 0.12 + k * 0.05)
        parts.append(torus("tyre", 0.62, 0.03, (wx, wy, 0.64), iron, rot=(0.12 + k * 0.05, math.pi / 2, math.pi / 2), seg=24, mseg=4))
    col.append(wl("L", "c", 0.8, 0.4, 1.3, 2.25, 0.2, 0))
    GX, GY = -2.8, 1.3
    parts.append(box("gframe", (0.2, 0.9, 0.6), (GX, GY, 0), M("wood_dark")))
    parts.append(cyl("gstone", 0.35, 0.12, (GX, GY, 0.75), M("stone", 0.7), verts=16, rot=(0, math.pi / 2, 0), center=True))
    parts.append(box("gtrough", (0.3, 0.8, 0.2), (GX, GY, 0.38), M("wood", 0.8)))
    col.append(box("c", (0.4, 0.9, 1.1), (GX, GY, 0)))
    for k in range(14):
        parts.append(blob("coalheap", (RNG.uniform(0.2, 0.4), RNG.uniform(0.2, 0.4), RNG.uniform(0.1, 0.25)), (-W / 2 + 0.5 + RNG.uniform(0, 0.8), D - 0.6 - RNG.uniform(0, 0.7), 0), M("coal", 0.9), subsurf=1))
    col.append(box("c", (1.2, 1.0, 0.4), (-W / 2 + 0.7, D - 0.8, 0)))
    for k in range(6):
        parts.append(cbox("stock", (0.03, 0.03, 1.8), (2.8 + k * 0.07, 0.5, 0.88), iron, rot=(0.15, 0, 0)))
    hanging_coat(parts, "F", -2.4, 2.1, "leather")
    parts.append(wl("F", "tring", 0.1, 0.06, 0.1, 2.0, 0.03, 1.2, iron))
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 2.6, 1.2, w=0.8, h=1.0)
    lantern(parts, -1.8, 2.6, H - 0.26, 2.6)
    post_at(AX + 0.8, AY - 0.3, AX, AY)          # the smith at the anvil
    post_at(AX - 0.9, AY - 0.4, AX, AY)          # the striker
    post_at(BX + 0.2, HY - 1.6, BX, HY)          # at the bellows lever
    post_at(1.5, 1.2, AX, AY)                    # a carter waiting
    finish_set("int_workshop_forge", parts, col)


def ledger_book(x, y, z, rot=0.0):
    """The Corporal's Ledger: an open duty book, one mesh, named `ledger`."""
    p = [box("lcover", (0.5, 0.36, 0.02), (0, 0, 0), M("leather_b", 0.8), bevel=0.005, seg=1),
         box("lpageL", (0.23, 0.33, 0.025), (-0.118, 0, 0.02), M("paper", 0.85), rot=(0, 0.05, 0)),
         box("lpageR", (0.23, 0.33, 0.025), (0.118, 0, 0.02), M("paper", 0.85), rot=(0, -0.05, 0))]
    for j in range(10):
        for sx in (-1, 1):
            p.append(box("lline", (0.17, 0.005, 0.002), (sx * 0.118, -0.13 + j * 0.028, 0.046), M("ink", 0.9)))
    p.append(box("lribbon", (0.012, 0.2, 0.003), (0.0, -0.22, 0.02), M("crimson", 0.8)))
    return keep(place(p, x, y, rot, z), "ledger")


def int_guard_post():
    """Odwach: a table with the rota and the Corporal's Ledger, a rack of muskets, greatcoats on pegs, a drum, a
    stove, and a barred cell in the back corner."""
    start()
    W, D, H = 7.0, 6.0, 3.2
    parts, col = room(W, D, H, "limewash", "flags", "beams", skirt=("plinth", 0.9))
    CTX["H"] = H
    # the table: the ledger (its own mesh), ink and quill, a candle, a tankard, dice; a bench and stools
    TX, TY = -1.0, 3.0
    table(parts, col, TX, TY, L=1.6, w=0.85, h=0.78, along_y=False, trestle=True)
    ledger_book(TX - 0.2, TY, 0.78, rot=0.1)
    parts.append(cyl("inkwell", 0.03, 0.05, (TX + 0.2, TY + 0.15, 0.78), M("ink", 0.3), verts=8))
    parts.append(cbox("quill", (0.01, 0.01, 0.28), (TX + 0.21, TY + 0.16, 0.94), M("paper", 0.9), rot=(0.3, -0.3, 0)))
    candle(parts, TX + 0.45, TY - 0.1, 0.78)
    lamp("candle", (TX + 0.3, TY, 1.3))
    tankard(parts, TX - 0.6, TY + 0.2, 0.78)
    for k in range(2):
        parts.append(box("die", (0.02, 0.02, 0.02), (TX + 0.55 + k * 0.04, TY + 0.25, 0.78), M("bone", 0.5), rot=(0, 0, k * 0.7)))
    bench(parts, TX, TY + 0.7, L=1.5, along_y=False)
    stool(parts, TX - 0.2, TY - 0.7)
    stool(parts, TX + 0.5, TY - 0.7)
    # the rota pinned on the back wall by the table
    parts.append(wl("B", "rota", 0.55, 0.01, 0.75, -1.4, 0.005, 1.4, M("paper", 0.9)))
    for j in range(8):
        parts.append(wl("B", "rline", 0.48, 0.004, 0.006, -1.4, 0.012, 1.5 + j * 0.075, M("ink", 0.9)))
    for k in range(3):
        parts.append(wl("B", "rcol", 0.006, 0.004, 0.6, -1.6 + k * 0.15, 0.012, 1.48, M("ink", 0.9)))
    parts.append(wl("B", "rhead", 0.4, 0.004, 0.04, -1.4, 0.012, 2.08, M("crimson", 0.9)))
    # musket rack on the left wall, cartridge boxes above, coats and caps on pegs, the drum
    muskets(parts, col, "L", 2.2, n_guns=7)
    parts.append(wl("L", "cshelf", 1.3, 0.25, 0.04, 2.2, 0.13, 1.85, M("wood_dark")))
    for k in range(4):
        cx, cy = _wpos("L", 1.75 + k * 0.3, 0.13)
        parts.append(box("cartbox", (0.12, 0.2, 0.14), (cx, cy, 1.89), M("black", 0.6), bevel=0.01, seg=1))
        parts.append(box("cbadge", (0.005, 0.06, 0.06), (cx + 0.06, cy, 1.93), M("brass", 0.3)))
    for k in range(3):
        hanging_coat(parts, "L", 4.0 + k * 0.5, 2.1, "coat_blue")
        cx, cy = _wpos("L", 4.0 + k * 0.5, 0.12)
        parts.append(blob("czapka", (0.2, 0.2, 0.16), (cx, cy, 2.12), M("crimson" if k == 1 else "coat_blue", 0.8), subsurf=1))
    DX, DY = -2.8, 0.9
    parts.append(cyl("drum", 0.24, 0.36, (DX, DY, 0), M("icon_blue", 0.6), verts=14))
    for zz in (0.0, 0.33):
        parts.append(cyl("drim", 0.25, 0.04, (DX, DY, zz), M("crimson", 0.6), verts=14))
    for k in range(6):
        a = math.tau * k / 6
        parts.append(cbox("dcord", (0.01, 0.01, 0.34), (DX + 0.245 * math.cos(a), DY + 0.245 * math.sin(a), 0.18), M("linen", 0.8), rot=(0.3 * math.sin(a), -0.3 * math.cos(a), 0)))
    parts.append(cyl("dhead", 0.24, 0.005, (DX, DY, 0.37), M("paper", 0.8), verts=14))
    for a in (-0.3, 0.3):
        parts.append(cbox("dstick", (0.3, 0.015, 0.015), (DX + 0.05, DY, 0.39), M("wood", 0.7), rot=(0, 0, a)))
    col.append(cyl("c", 0.25, 0.4, (DX, DY, 0), None, verts=8))
    # the cell: bars along x = CX0 and y = CY0 to the back right corner, a barred door, straw, bucket, a chain
    CX0, CY0 = 1.1, 3.4
    iron = M("iron", 0.45)
    k = 0.0
    while CY0 + k < D - 0.05:
        parts.append(cyl("bar", 0.018, H - 0.25, (CX0, CY0 + k, 0), iron, verts=6))
        k += 0.14
    k = 0.0
    DOOR0, DOOR1 = 1.6, 2.5
    while CX0 + k < W / 2 - 0.05:
        x = CX0 + k
        parts.append(cyl("bar", 0.018, H - 0.25, (x + (0.1 if DOOR0 <= x <= DOOR1 else 0.0), CY0 - (0.12 if DOOR0 <= x <= DOOR1 else 0.0), 0), iron, verts=6))
        k += 0.14
    for zz in (0.1, 1.1, 2.1, H - 0.3):
        parts.append(box("band", (0.05, D - CY0, 0.05), (CX0, (CY0 + D) / 2, zz), iron))
        parts.append(box("band", (W / 2 - CX0, 0.05, 0.05), ((CX0 + W / 2) / 2, CY0, zz), iron))
    parts.append(box("clock", (0.12, 0.08, 0.16), (DOOR1 + 0.05, CY0 - 0.12, 1.0), iron, bevel=0.01, seg=1))
    col.append(box("c", (0.08, D - CY0, H), (CX0, (CY0 + D) / 2, 0)))
    col.append(box("c", (W / 2 - CX0, 0.08, H), ((CX0 + W / 2) / 2, CY0, 0)))
    for k in range(8):
        parts.append(blob("cstraw", (0.4, 0.25, 0.03), (RNG.uniform(1.5, 3.1), RNG.uniform(4.0, 5.7), 0), M("straw_bed", 0.95), subsurf=1))
    parts.append(cyl("cbucket", 0.15, 0.28, (3.1, 3.8, 0), M("wood", 0.8), verts=10, r2=0.17))
    parts.append(wl("R", "cbench", 1.6, 0.4, 0.45, 4.9, 0.2, 0, M("wood", 0.8), bevel=0.02, seg=1))
    for k in range(6):
        cx, cy = _wpos("B", 2.6, 0.05)
        parts.append(torus("chain", 0.04, 0.01, (cx, cy, 1.6 - k * 0.07), iron, rot=(math.pi / 2 if k % 2 else 0, 0, 0), seg=8, mseg=3))
    # key ring on a hook by the cell door; the stove in the front left; a bench under the window
    parts.append(torus("kring", 0.06, 0.008, (DOOR1 + 0.3, CY0 - 0.15, 1.5), iron, rot=(math.pi / 2, 0, 0), seg=10, mseg=3))
    for k in range(3):
        parts.append(box("key", (0.012, 0.012, 0.14), (DOOR1 + 0.27 + k * 0.03, CY0 - 0.15, 1.3), iron))
    iron_stove(parts, col, -W / 2 + 0.6, 1.8, lit=True)
    bench(parts, 2.2, 0.55, L=1.8, along_y=False)
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 2.2, 1.1, w=0.8, h=1.0, bars=True)
    lantern(parts, -0.6, 2.2, H - 0.24, 2.2)
    lantern(parts, 2.3, 2.6, H - 0.24, 2.2)
    post_at(TX, TY + 0.7, TX, TY)                 # the corporal at the table, the ledger in front of him
    post_at(TX - 0.2, TY - 0.7, TX, TY)           # a soldier at dice
    post_at(*_wpos("L", 2.2, 1.0), *_wpos("L", 2.2, 0.0))   # at the musket rack
    post_at(1.2, 1.0, 0.0, 0.0)                   # the sentry inside the door
    post_at(2.4, 4.8, CX0, CY0)                   # the prisoner in the cell
    finish_set("int_guard_post", parts, col)


# ------------------------------------------------------------------ HOUSES OF PRAYER
def int_chapel_synagogue():
    """Synagogue: a vaulted hall, the bimah in the middle behind its iron grille, the Aron ha-Kodesh on the east wall
    under its curtain and tablets, benches along the walls, brass chandeliers, the eternal light."""
    start()
    W, D = 10.0, 13.0
    SP = 4.4
    parts, col = room(W, D, 0, "limewash", "flags", "vault", spring=SP, rib=4, t=0.5, door_w=1.5, door_h=2.6, arched=True, frame=False)
    CTX["H"] = SP + W / 2
    skirting(parts, "LRBF", 0.6, "stone_pale")
    # the bimah: octagonal platform, steps front and back, iron grille and rail, a desk with its cloth
    BY = 6.2
    parts.append(cyl("bimah", 1.7, 0.6, (0, BY, 0), M("stone_pale", 0.8), verts=8, bevel=0.02, seg=1))
    for sy in (-1, 1):
        for k in range(2):
            parts.append(box("bstep", (1.0, 0.3, 0.2 * (k + 1)), (0, BY + sy * (1.85 - k * 0.28), 0), M("stone", 0.8), bevel=0.02, seg=1))
    col.append(cyl("c", 1.7, 0.6, (0, BY, 0), None, verts=8))
    for sy in (-1, 1):
        col.append(prism("c", -0.5, 0.5, BY + sy * 2.3, BY + sy * 1.4, 0, 0.6))
    iron = M("iron", 0.45)
    for k in range(8):
        a = math.tau * (k + 0.5) / 8
        x0, y0 = 1.62 * math.cos(a), BY + 1.62 * math.sin(a)
        a2 = math.tau * (k + 1.5) / 8
        x1, y1 = 1.62 * math.cos(a2), BY + 1.62 * math.sin(a2)
        parts.append(cyl("bpost", 0.04, 1.3, (x0, y0, 0.6), iron, verts=6))
        parts.append(sphere("bknob", 0.06, (x0, y0, 1.95), MET("brass", 0.3), seg=8, rings=4))
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        if abs(mx) < 0.4:
            continue                    # the openings over the steps
        seg = math.hypot(x1 - x0, y1 - y0)
        ang = math.atan2(y1 - y0, x1 - x0)
        parts.append(cbox("brail", (seg, 0.05, 0.05), (mx, my, 1.85), iron, rot=(0, 0, ang)))
        parts.append(cbox("brail", (seg, 0.03, 0.03), (mx, my, 0.75), iron, rot=(0, 0, ang)))
        for j in range(1, 7):
            f = j / 7
            parts.append(cyl("bbar", 0.012, 1.1, (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, 0.75), iron, verts=4))
            if j % 2:
                parts.append(torus("bscroll", 0.07, 0.01, (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, 1.55), iron, rot=(math.pi / 2, 0, ang), seg=8, mseg=3))
    parts.append(taper_box("bdesk", (0.9, 0.6, 1.0), (0, BY + 0.2, 0.6), M("wood_dark"), top=0.9, bevel=0.02))
    parts.append(cbox("bdtop", (1.0, 0.7, 0.04), (0, BY + 0.2, 1.62), M("parochet", 0.9), rot=(0.25, 0, 0)))
    parts.append(box("bdcloth", (0.96, 0.02, 0.45), (0, BY - 0.12, 1.15), M("parochet", 0.9)))
    parts.append(box("bdfringe", (0.96, 0.025, 0.05), (0, BY - 0.13, 1.1), MET("gold", 0.35)))
    col.append(box("c", (0.9, 0.6, 1.7), (0, BY + 0.2, 0.6)))
    for (cx, cy) in ((-1.1, BY - 1.0), (1.1, BY - 1.0), (-1.1, BY + 1.0), (1.1, BY + 1.0)):
        parts.append(cyl("bcand", 0.03, 0.9, (cx, cy, 0.6), MET("brass", 0.3), verts=8))
        candle(parts, cx, cy, 1.5, h=0.2, r=0.025, holder=False)
    lamp("candle", (0, BY - 0.8, 2.2))
    # the Aron ha-Kodesh on the back (east) wall: steps, columns, entablature, curtain, tablets, crown
    AU = 0.0
    for k in range(3):
        parts.append(wl("B", "astep", 3.2 - k * 0.5, 1.2 - k * 0.3, 0.18 * (k + 1), AU, 0.6 - k * 0.15, 0, M("stone_pale", 0.8), bevel=0.02, seg=1))
    col.append(wl("B", "c", 3.2, 1.2, 0.54, AU, 0.6, 0))
    parts.append(wl("B", "aniche", 1.6, 0.35, 2.4, AU, 0.18, 0.54, M("stone", 0.8), bevel=0.02, seg=1))
    parts.append(wl("B", "acurtain", 1.4, 0.06, 2.2, AU, 0.38, 0.6, M("parochet", 0.9), bevel=0.02, seg=1, wonk=0.01))
    parts.append(wl("B", "aborder", 1.44, 0.065, 0.12, AU, 0.385, 0.6, MET("gold", 0.35)))
    parts.append(wl("B", "aborder", 1.44, 0.065, 0.12, AU, 0.385, 2.68, MET("gold", 0.35)))
    cx_, cy_ = _wpos("B", AU, 0.43)
    parts.append(blob("acrown", (0.32, 0.04, 0.22), (cx_, cy_, 2.1), MET("gold", 0.3), subsurf=1))
    for s_ in (-1, 1):
        px, py = _wpos("B", AU + s_ * 1.05, 0.35)
        parts.append(cyl("acol", 0.14, 2.6, (px, py, 0.54), M("stone_pale", 0.6), verts=12, bevel=0.02, seg=1))
        parts.append(box("acap", (0.36, 0.36, 0.2), (px, py, 3.14), M("stone", 0.6), bevel=0.02, seg=1))
    parts.append(wl("B", "aentab", 2.7, 0.5, 0.4, AU, 0.3, 3.34, M("stone", 0.6), bevel=0.03, seg=1))
    parts.append(warch("B", "apedim", 2.0, 1.0, 0.3, AU, 0.3, 3.74, M("stone_pale", 0.6), bevel=0.03))
    for s_ in (-1, 1):
        parts.append(warch("B", "atablet", 0.42, 0.62, 0.08, AU + s_ * 0.23, 0.5, 3.8, MET("gold", 0.3), bevel=0.01))
    for s_ in (-1, 1):
        parts.append(wl("B", "alion", 0.3, 0.1, 0.4, AU + s_ * 0.75, 0.48, 3.85, MET("gold", 0.35), bevel=0.05, seg=1, wonk=0.03))
    col.append(wl("B", "c", 2.7, 0.6, 4.6, AU, 0.3, 0))
    nx, ny = _wpos("B", AU, 1.6)
    parts.append(cyl("ntchain", 0.008, SP + 5 - 3.2, (nx, ny, 3.2), M("iron", 0.6), verts=4))
    parts.append(cyl("ntlamp", 0.1, 0.18, (nx, ny, 3.0), MET("brass", 0.3), verts=10, r2=0.06))
    parts.append(sphere("ntglass", 0.07, (nx, ny, 2.97), EM("fire", 5.0, 0.3), seg=8, rings=4))
    lamp("candle", (nx, ny, 2.9))
    for s_ in (-1, 1):
        candelabrum(parts, col, AU + s_ * 1.8, D - 1.1, h=1.5)
    # benches along the walls, facing the bimah, with stenders (reading desks) in front of a few
    for sx in (-1, 1):
        for k in range(4):
            y = 1.6 + k * 2.0
            x = sx * (W / 2 - 0.35)
            p = [box("bseat", (0.4, 1.7, 0.06), (0, 0, 0.44), M("pew", 0.7)),
                 box("bback", (0.06, 1.7, 0.6), (sx * 0.2, 0, 0.5), M("pew", 0.7), bevel=0.02, seg=1)]
            for ey in (-1, 1):
                p.append(box("bend", (0.45, 0.06, 0.9), (0, ey * 0.85, 0), M("wood_dark")))
            parts.append(place(p, x, y, 0.0))
            col.append(box("c", (0.45, 1.75, 0.9), (x, y, 0)))
            if k % 2 == 0:
                sx2 = x - sx * 0.8
                parts.append(box("stender", (0.4, 0.5, 0.95), (sx2, y, 0), M("wood_dark"), bevel=0.02, seg=1))
                parts.append(cbox("sttop", (0.5, 0.6, 0.03), (sx2, y, 1.0), M("wood", 0.7), rot=(0, sx * 0.35, 0)))
                col.append(box("c", (0.4, 0.5, 1.0), (sx2, y, 0)))
    for k in range(2):
        for s_ in (-1, 1):
            parts.append(box("pbench", (2.2, 0.4, 0.45), (s_ * 1.4, 9.4 + k * 0.9, 0), M("pew", 0.7), bevel=0.02, seg=1))
            parts.append(box("pback", (2.2, 0.06, 0.45), (s_ * 1.4, 9.4 + k * 0.9 - 0.18, 0.45), M("pew", 0.7)))
            col.append(box("c", (2.2, 0.45, 0.9), (s_ * 1.4, 9.4 + k * 0.9, 0)))
    # brass chandeliers down the hall
    for y in (3.0, BY, 9.6):
        brass_chandelier(parts, 0, y, SP + W / 2, SP + 1.0, arms=8, r=0.6, kind="brasslamp")
    # high round-headed windows; the women's gallery grilles over the door
    for side in "LR":
        for y in (2.8, 6.2, 9.6):
            fake_window(parts, side, y, 2.4, w=1.1, h=2.4, arched=True, sill=False)
    for u in (-3.0, -1.6, 1.6, 3.0):
        parts.append(wl("F", "grille", 0.9, 0.05, 0.9, u, 0.03, 3.3, M("coal", 0.9)))
        for j in range(6):
            parts.append(wl("F", "gbar", 0.02, 0.03, 0.9, u - 0.4 + j * 0.16, 0.07, 3.3, M("wood_dark")))
            parts.append(wl("F", "gbar", 0.9, 0.03, 0.02, u, 0.07, 3.3 + j * 0.16, M("wood_dark")))
    post_at(0.0, BY - 0.4, 0.0, BY + 0.2, z=0.6)            # the cantor at the bimah desk
    post_at(0.0, D - 2.4, 0.0, D)                            # the shammes before the ark
    for (sx, y) in ((-1, 1.6), (-1, 5.6), (1, 3.6), (1, 7.6)):
        post_at(sx * (W / 2 - 0.4), y, 0.0, BY)             # on the wall benches
    post_at(-1.4, 9.1, -1.4, D)                              # in the front bench
    finish_set("int_chapel_synagogue", parts, col)


def icon_panel(parts, side, u, z, w, h, n, mat, halo=True):
    parts.append(wl(side, "ipanel", w, 0.03, h, u, n, z, M(mat, 0.6)))
    parts.append(wl(side, "iframe", w + 0.06, 0.02, 0.03, u, n - 0.005, z + h, MET("gold", 0.3)))
    parts.append(wl(side, "iframe", w + 0.06, 0.02, 0.03, u, n - 0.005, z - 0.03, MET("gold", 0.3)))
    if halo:
        hx, hy = _wpos(side, u, n + 0.02)
        r = min(w, h) * 0.22
        parts.append(cyl("halo", r, 0.01, (hx, hy, z + h * 0.72), MET("gold", 0.25), verts=12, rot=(math.pi / 2, 0, 0), center=True))
        parts.append(blob("iface", (r * 0.9, 0.012, r * 1.1), (hx, hy - 0.008, z + h * 0.72 - r * 0.55), M("plaster_rose", 0.6), subsurf=1))
        parts.append(wl(side, "irobe", w * 0.6, 0.012, h * 0.5, u, n + 0.02, z + 0.05, M(RNG.choice(("icon_red", "icon_blue", "icon_green")), 0.6)))


def int_chapel_uniate():
    """Cerkiew: the iconostasis across the east end (gilt tiers of icons, the royal doors, deacons' doors), brass
    candle stands bristling with tapers, hanging lampadas, an icon on its stand."""
    start()
    W, D = 7.0, 9.0
    SP = 3.6
    parts, col = room(W, D, 0, "limewash", "flags", "vault", spring=SP, rib=3, t=0.5, door_w=1.4, door_h=2.5, arched=True, frame=False)
    CTX["H"] = SP + W / 2
    for side in "LR":
        parts.append(wl(side, "frieze", D, 0.02, 0.35, D / 2, 0.01, SP - 0.4, M("icon_blue", 0.7)))
        parts.append(wl(side, "friezeg", D, 0.025, 0.04, D / 2, 0.012, SP - 0.44, MET("gold", 0.35)))
    skirting(parts, "LRF", 0.7, "icon_red")
    # the solea (a step up before the iconostasis) and the iconostasis wall itself
    IY = 7.6
    parts.append(box("solea", (W, D - IY + 0.8, 0.2), (0, IY + (D - IY) / 2 - 0.4, 0), M("stone_pale", 0.8), bevel=0.02, seg=1))
    col.append(box("c", (W, D - IY + 0.8, 0.2), (0, IY + (D - IY) / 2 - 0.4, 0)))
    IH = 5.2
    parts.append(box("iconostasis", (W, 0.3, IH), (0, IY + 0.15, 0.2), M("wood_dark", 0.6), bevel=0.02, seg=1))
    col.append(box("c", (W, 0.35, IH), (0, IY + 0.15, 0.2)))
    CTX["D"] = IY           # wl("B", ...) now measures from the iconostasis face
    n = 0.0
    gold = MET("gold", 0.3)
    parts.append(wl("B", "iplinth", W, 0.08, 0.6, 0.0, n + 0.04, 0.2, gold))
    for u in (-2.9, -1.95, 1.95, 2.9):
        parts.append(wl("B", "icol", 0.14, 0.12, 2.6, u, n + 0.06, 0.8, gold, bevel=0.02, seg=1))
    # main tier: Christ and the Theotokos either side of the royal doors, the patron and St Nicholas outside
    for (u, mat) in ((-2.42, "icon_green"), (-1.35, "icon_red"), (1.35, "icon_blue"), (2.42, "icon_red")):
        icon_panel(parts, "B", u, 0.95, 0.8, 1.9, n + 0.03, "altar_blue" if abs(u) < 2 else mat)
    # royal doors: two leaves, gilt openwork, a small icon on each; deacons' doors
    for s_ in (-1, 1):
        parts.append(wl("B", "rdoor", 0.58, 0.06, 2.2, s_ * 0.3, n + 0.03, 0.8, gold, bevel=0.01, seg=1))
        for j in range(4):
            parts.append(wl("B", "rvine", 0.44, 0.02, 0.05, s_ * 0.3, n + 0.07, 1.1 + j * 0.4, M("wood_dark", 0.5)))
        icon_panel(parts, "B", s_ * 0.3, 2.3, 0.34, 0.45, n + 0.07, "icon_blue", halo=True)
    parts.append(warch("B", "rarch", 1.3, 0.7, 0.05, 0.0, n + 0.03, 2.9, gold, bevel=0.01))
    # upper tiers: the Last Supper over the doors, the feasts and the apostles in rows, the crucifix on top
    parts.append(wl("B", "supper", 1.3, 0.03, 0.5, 0.0, n + 0.03, 3.25, M("icon_red", 0.6)))
    for k in range(13):
        parts.append(sphere("shalo", 0.035, _wpos("B", -0.54 + k * 0.09, n + 0.05) + (3.58,), MET("gold", 0.25), seg=6, rings=3))
    parts.append(wl("B", "tierbeam", W, 0.1, 0.1, 0.0, n + 0.05, 3.8, gold))
    for k in range(9):
        u = -3.0 + k * 0.75
        if abs(u) < 0.5:
            continue
        icon_panel(parts, "B", u, 3.0, 0.55, 0.7, n + 0.03, RNG.choice(("icon_red", "icon_blue", "icon_green")))
    for k in range(11):
        u = -3.1 + k * 0.62
        icon_panel(parts, "B", u, 3.95, 0.5, 0.6, n + 0.03, RNG.choice(("icon_red", "icon_blue", "icon_green")))
    parts.append(wl("B", "tierbeam", W, 0.1, 0.1, 0.0, n + 0.05, 4.6, gold))
    parts.append(wl("B", "cross", 0.1, 0.06, 1.1, 0.0, n + 0.05, 4.75, gold))
    parts.append(wl("B", "cross", 0.6, 0.06, 0.1, 0.0, n + 0.05, 5.4, gold))
    parts.append(cbox("crossf", (0.4, 0.06, 0.06), _wpos("B", 0.0, n + 0.05) + (5.0,), gold, rot=(0, 0.3, 0)))
    CTX["D"] = D
    # lampadas hanging before the main icons; candle stands full of tapers; the icon on its stand
    for u in (-1.35, 0.0, 1.35):
        lx, ly = u, IY - 0.7
        parts.append(cyl("lchain", 0.006, SP + W / 2 - 2.6, (lx, ly, 2.6), M("brass", 0.3), verts=4))
        parts.append(cyl("lcup", 0.07, 0.12, (lx, ly, 2.45), EM("icon_red", 2.0, 0.3), verts=10, r2=0.09))
        parts.append(cyl("lflame", 0.012, 0.04, (lx, ly, 2.57), EM("flame", 8.0), verts=6, r2=0.0))
        lamp("candle", (lx, ly, 2.4))
    for sx in (-1, 1):
        cx, cy = sx * 1.6, IY - 1.3
        parts.append(cyl("tstand", 0.05, 0.95, (cx, cy, 0), MET("brass", 0.3), verts=8, r2=0.03))
        parts.append(cyl("tbase", 0.25, 0.06, (cx, cy, 0), MET("brass", 0.3), verts=10))
        parts.append(cyl("ttray", 0.3, 0.08, (cx, cy, 0.95), MET("brass", 0.3), verts=14, r2=0.32))
        parts.append(cyl("tsand", 0.29, 0.01, (cx, cy, 1.02), M("tile_ochre", 0.9), verts=14))
        for k in range(14):
            a = RNG.uniform(0, math.tau)
            rr = RNG.uniform(0.02, 0.24)
            candle(parts, cx + rr * math.cos(a), cy + rr * math.sin(a), 1.03, h=RNG.uniform(0.12, 0.3), r=0.008, holder=False)
        lamp("candle", (cx, cy, 1.6))
        col.append(cyl("c", 0.3, 1.1, (cx, cy, 0), None, verts=6))
    AX, AY = 0.0, 4.2
    parts.append(taper_box("analogion", (0.5, 0.5, 1.05), (AX, AY, 0), M("wood_dark"), top=0.8, bevel=0.02))
    parts.append(box("ancloth", (0.56, 0.56, 0.9), (AX, AY, 0.2), M("parochet", 0.9), bevel=0.02, seg=1))
    parts.append(cbox("anicon", (0.36, 0.46, 0.03), (AX, AY, 1.12), M("altar_blue", 0.6), rot=(0.4, 0, 0)))
    parts.append(cbox("anframe", (0.4, 0.5, 0.02), (AX, AY, 1.1), MET("gold", 0.3), rot=(0.4, 0, 0)))
    col.append(box("c", (0.56, 0.56, 1.1), (AX, AY, 0)))
    for sx in (-1, 1):
        parts.append(box("wbench", (0.4, 3.0, 0.45), (sx * (W / 2 - 0.3), 3.0, 0), M("pew", 0.7), bevel=0.02, seg=1))
        col.append(box("c", (0.4, 3.0, 0.45), (sx * (W / 2 - 0.3), 3.0, 0)))
    for side in "LR":
        for y in (2.2, 5.4):
            fake_window(parts, side, y, 2.0, w=0.9, h=1.7, arched=True, sill=False)
    icon_panel(parts, "L", 6.7, 1.3, 0.6, 0.8, 0.02, "icon_green")
    post_at(0.0, IY - 0.7, 0.0, 0.0, z=0.2)          # the priest before the royal doors
    post_at(-1.6, IY - 2.0, -1.6, IY - 1.3)          # lighting a taper
    post_at(0.6, 3.2, 0.0, IY)                       # worshippers standing
    post_at(-0.8, 2.4, 0.0, IY)
    post_at(W / 2 - 0.35, 3.0, 0.0, 3.0)             # an old man on the wall bench
    finish_set("int_chapel_uniate", parts, col)


# ------------------------------------------------------------------ THE FINALE: the kingpin's house, the bathhouse, the warehouse
def iwall(parts, col, axis, a, b, at, z0, z1, mat, openings=(), t=0.2, trim="timber"):
    """Partition wall. axis "x": runs along x from a to b at y=at; "y": along y at x=at.
    openings: [(centre, width, height)] measured from z0. Door frames in `trim`."""
    def seg(u0, u1, zz0, zz1):
        if u1 - u0 < 0.01 or zz1 - zz0 < 0.01:
            return
        if axis == "x":
            size, loc = (u1 - u0, t, zz1 - zz0), ((u0 + u1) / 2, at, zz0)
        else:
            size, loc = (t, u1 - u0, zz1 - zz0), (at, (u0 + u1) / 2, zz0)
        parts.append(box("iwall", size, loc, M(mat), bevel=0, wonk=0.01, smooth=0))
        col.append(box("c", size, loc))
    cur = a
    for (c, w, h) in sorted(openings):
        seg(cur, c - w / 2, z0, z1)
        seg(c - w / 2, c + w / 2, z0 + h, z1)
        if trim:
            for s_ in (-1, 1):
                u = c + s_ * (w / 2 + 0.05)
                if axis == "x":
                    parts.append(box("jamb", (0.1, t + 0.06, h), (u, at, z0), M(trim), bevel=0.02, seg=1))
                else:
                    parts.append(box("jamb", (t + 0.06, 0.1, h), (at, u, z0), M(trim), bevel=0.02, seg=1))
            if axis == "x":
                parts.append(box("lint", (w + 0.3, t + 0.06, 0.12), (c, at, z0 + h), M(trim), bevel=0.02, seg=1))
            else:
                parts.append(box("lint", (t + 0.06, w + 0.3, 0.12), (at, c, z0 + h), M(trim), bevel=0.02, seg=1))
        cur = c + w / 2
    seg(cur, b, z0, z1)


def floor_region(parts, kind, x0, x1, y0, y1, z=0.0, surf=None):
    """Floor finish over a region plus its collision slab in the matching surface group."""
    if z == 0.0:
        lay_floor(parts, kind, x0, x1, y0, y1)
    else:
        n0 = len(parts)
        lay_floor(parts, kind, x0, x1, y0, y1)
        for o in parts[n0:]:
            edit_verts(o, lambda co: setattr(co, "z", co.z + z))
    s = surf or FLOOR_SURFACE[kind]
    SURF.setdefault(s, []).append(box("c", (x1 - x0, y1 - y0, 0.4), ((x0 + x1) / 2, (y0 + y1) / 2, z - 0.4)))


def fx(kind, loc):
    """Particle marker for interiors.gd: fx_smoke (tobacco haze), fx_steam, fx_drip."""
    o = bpy.data.objects.new("fx_%s_%02d" % (kind, len(FX)), None)
    bpy.context.collection.objects.link(o)
    o.location = loc
    FX.append(o)
    return o


def exit_marker(name, loc, a=0.0):
    """A second way out: interiors.gd puts an exit trigger here (destination from data/interiors.json `exits`)."""
    o = bpy.data.objects.new("Exit_%s" % name, None)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (0, 0, a)
    FX.append(o)
    return o


def stuffed_bear(parts, col, x, y, rot=0.0):
    fur = M("leather_b", 0.95)
    p = [blob("btorso", (0.7, 0.5, 1.1), (0, 0, 0.5), fur, subsurf=2),
         blob("bhead", (0.34, 0.36, 0.32), (0, -0.12, 1.6), fur, subsurf=2),
         blob("bsnout", (0.14, 0.18, 0.12), (0, -0.34, 1.66), M("hide", 0.8), subsurf=1),
         sphere("bnose", 0.03, (0, -0.43, 1.74), M("black", 0.3), seg=6, rings=3)]
    for sx in (-1, 1):
        p.append(blob("bear_ear", (0.1, 0.06, 0.1), (sx * 0.14, -0.05, 1.88), fur, subsurf=1))
        p.append(cbox("barm", (0.16, 0.16, 0.6), (sx * 0.38, -0.2, 1.2), fur, rot=(-1.0, sx * 0.4, 0), bevel=0.06, seg=2))
        p.append(blob("bleg", (0.22, 0.26, 0.55), (sx * 0.2, 0.0, 0.05), fur, subsurf=1))
        p.append(sphere("beye", 0.018, (sx * 0.07, -0.3, 1.74), M("black", 0.2), seg=6, rings=3))
    p.append(box("bplinth", (0.9, 0.8, 0.1), (0, 0, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(place(p, x, y, rot))
    col.append(cyl("c", 0.45, 2.0, (x, y, 0), None, verts=8))


def int_house_kingpin():
    """The kingpin's house, new money and no taste. Ground floor: the hall (tiled stove, the footman's hooded
    chair, the stair), a gilded parlour (mirrors, clock, a pianoforte nobody plays, a stuffed bear), the card room
    (green baize, decanters, punch, tobacco haze), the strongroom behind its iron door, the dining room and the
    office with the river-trade maps. The bookcase in the office stands ajar on a stair down to a brick passage
    that slopes to the river and a boat. Upstairs: the bedroom, a canopy bed and the mistress's dressing table.
    Out the back: the courtyard, a privy and the stable."""
    start()
    W, D, H, H2, t = 14.0, 12.0, 3.6, 7.3, 0.3
    FL = 3.8                                 # upper floor level
    SHX = 5.0                                # the secret stair's x
    parts, col = shell(W, D, H2, "limewash", ceil_mat="limewash", t=t, door_w=1.4, door_h=2.6,
                       openings={"B": [(0.0, 1.2, 2.4, False), (SHX, 1.0, 2.2, False)]})
    CTX["H"] = H
    col.pop(0)                               # the floor slab goes into surface groups instead
    # floors
    floor_region(parts, "tiles", -1.5, 1.5, 0, D)
    floor_region(parts, "parquet", -W / 2, -1.5, 0, D)
    floor_region(parts, "parquet", 1.5, W / 2, 0, 5.0)
    floor_region(parts, "flags", 1.5, W / 2, 5.0, 8.0)
    floor_region(parts, "planks", 1.5, W / 2, 8.0, D)
    # ground-floor partitions
    iwall(parts, col, "y", 0, D, -1.5, 0, H, "limewash", [(3.0, 1.2, 2.4), (11.2, 1.0, 2.3)])
    iwall(parts, col, "y", 0, D, 1.5, 0, H, "limewash", [(2.5, 1.2, 2.4), (6.5, 1.0, 2.2), (10.0, 1.0, 2.3)])
    iwall(parts, col, "x", -W / 2, -1.6, 6.0, 0, H, "limewash")
    iwall(parts, col, "x", 1.6, W / 2, 5.0, 0, H, "limewash")
    iwall(parts, col, "x", 1.6, W / 2, 8.0, 0, H, "limewash")
    # the upper floor slab with the stair hole (x -1.5..-0.5, y 6.3..10.2), a plaster ceiling under it
    SY0, SY1 = 6.3, 10.2
    for (x0, x1, y0, y1) in ((-W / 2, W / 2, 0, SY0), (-W / 2, W / 2, SY1, D), (-W / 2, -1.5, SY0, SY1), (-0.5, W / 2, SY0, SY1)):
        parts.append(box("upfloor", (x1 - x0, y1 - y0, FL - H), ((x0 + x1) / 2, (y0 + y1) / 2, H), M("limewash_b")))
    for (x0, x1, y0, y1) in ((-W / 2, 1.5, 6.0, SY0), (-W / 2, 1.5, SY1, D), (-W / 2, -1.5, SY0, SY1), (-0.5, 1.5, SY0, SY1)):
        floor_region(parts, "parquet", x0, x1, y0, y1, z=FL)
    col.append(box("c", (W, 6.0, FL - H), (0, 3.0, H)))
    col.append(box("c", (W / 2 - 1.5, D - 6.0, FL - H), ((W / 2 + 1.5) / 2, 9.0, H)))
    # upstairs: the bedroom over the dining room, walls round it
    iwall(parts, col, "x", -W / 2, 1.6, 6.0, FL, H2, "wallpaper")
    iwall(parts, col, "y", 6.0, D, 1.5, FL, H2, "wallpaper")
    parts.append(box("bpaper", (0.02, D - 6.0, H2 - FL), (-W / 2 + 0.02, 9.0, FL), M("wallpaper", 0.8)))
    parts.append(box("bpaperB", (W / 2 + 1.5, 0.02, H2 - FL), ((-W / 2 + 1.5) / 2, D - 0.01, FL), M("wallpaper", 0.8)))
    # ---- the hall: stove, the footman's chair, the stair, a mirror, a lantern
    tiled_stove(parts, col, -1.05, 4.8, rot=math.pi / 2, w=0.7, d=0.7, h=2.4, tile="icon_blue", trim="tile_w")
    FX_, FY_ = 1.0, 1.1
    p = [box("fseat", (0.6, 0.55, 0.45), (0, 0, 0), M("leather_b", 0.8), bevel=0.03, seg=1),
         box("fback", (0.66, 0.1, 1.8), (0, 0.28, 0), M("leather_b", 0.8), bevel=0.03, seg=1)]
    for sx in (-1, 1):
        p.append(box("fside", (0.08, 0.6, 1.8), (sx * 0.33, 0.02, 0), M("leather_b", 0.8), bevel=0.02, seg=1))
    p.append(box("fhood", (0.74, 0.62, 0.1), (0, 0.02, 1.8), M("leather_b", 0.8), bevel=0.03, seg=1))
    parts.append(place(p, FX_, FY_, -math.pi / 2))
    col.append(box("c", (0.6, 0.7, 1.9), (FX_, FY_, 0)))
    stair(parts, col, -1.0, SY0, 0.0, width=1.0, rise=FL, steps=15, run=0.26, rail_sides=(1,))
    rug(parts, 0.0, 6.0, 1.4, 9.0, mat="crimson", border="zupan_gold")
    parts.append(box("console", (0.4, 1.2, 0.8), (1.25, 4.4, 0), MET("gold", 0.3), bevel=0.02, seg=1))
    parts.append(box("contop", (0.45, 1.3, 0.04), (1.25, 4.4, 0.8), M("marble", 0.2)))
    col.append(box("c", (0.45, 1.3, 0.85), (1.25, 4.4, 0)))
    parts.append(cyl("urn", 0.12, 0.4, (1.25, 4.4, 0.84), M("plaster_blue", 0.2), verts=12, r2=0.07))
    parts.append(box("hmframe", (0.06, 0.9, 1.4), (1.38, 4.4, 1.2), MET("gold", 0.3), bevel=0.03, seg=1))
    parts.append(box("hmglass", (0.02, 0.75, 1.25), (1.34, 4.4, 1.27), MET("mirror", 0.04)))
    parts.append(box("arms", (0.06, 0.7, 0.8), (-1.38, 1.8, 1.8), MET("gold", 0.3), bevel=0.05, seg=1))
    parts.append(box("armsf", (0.02, 0.5, 0.55), (-1.34, 1.8, 1.9), M("crimson", 0.6)))
    lantern(parts, 0.0, 2.6, H, 2.4)
    lantern(parts, 0.0, 8.5, H, 2.4)
    # ---- the parlour: too much gilt
    PX0, PX1 = -W / 2, -1.5
    parts.append(box("damask", (0.02, 6.0, H), (PX0 + 0.01, 3.0, 0), M("damask", 0.7)))
    for k in range(2):
        parts.append(box("mframe", (0.06, 1.1, 2.1), (PX0 + 0.04, 1.5 + k * 3.0, 1.0), MET("gold", 0.3), bevel=0.03, seg=1))
        parts.append(box("mglass", (0.02, 0.9, 1.9), (PX0 + 0.08, 1.5 + k * 3.0, 1.1), MET("mirror", 0.04)))
        parts.append(box("mcrest", (0.08, 0.7, 0.3), (PX0 + 0.05, 1.5 + k * 3.0, 3.1), MET("gold", 0.3), bevel=0.04, seg=1))
    rug(parts, -4.3, 3.0, 3.4, 2.6, mat="velvet", border="zupan_gold")
    harpsichord(parts, col, -5.4, 3.8, math.pi / 2 + 0.2)
    stuffed_bear(parts, col, -6.3, 5.3, math.pi * 0.75)
    settee(parts, col, -3.8, 5.55, math.pi, L=1.8)
    for k in range(2):
        chair(parts, -4.9 + k * 2.2, 1.4, 0.0 + (k - 0.5) * 0.6, fancy=True)
    parts.append(cyl("ptable", 0.4, 0.05, (-3.8, 3.0, 0.72), MET("gold", 0.3), verts=14))
    parts.append(cyl("ptop", 0.42, 0.03, (-3.8, 3.0, 0.77), M("marble", 0.2), verts=14))
    parts.append(cyl("pleg", 0.06, 0.72, (-3.8, 3.0, 0), MET("gold", 0.3), verts=8, r2=0.03))
    col.append(cyl("c", 0.42, 0.8, (-3.8, 3.0, 0), None, verts=8))
    parts.append(box("pclock", (0.36, 0.22, 0.45), (-3.8, 3.0, 0.8), MET("gold", 0.25), bevel=0.04, seg=1))
    parts.append(cyl("pcface", 0.1, 0.02, (-3.8, 2.88, 1.05), M("tile_w", 0.2), verts=12, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(box("pcherub", (0.1, 0.1, 0.18), (-3.8, 3.0, 1.25), MET("gold", 0.25), bevel=0.05, seg=2))
    parts.append(box("gclock", (0.5, 0.36, 2.3), (-2.3, 0.45, 0), MET("gold", 0.3), bevel=0.02, seg=1))
    parts.append(cyl("gcface", 0.17, 0.02, (-2.3, 0.62, 1.9), M("tile_w", 0.2), verts=16, rot=(math.pi / 2, 0, 0), center=True))
    col.append(box("c", (0.5, 0.36, 2.3), (-2.3, 0.45, 0)))
    # portrait of the master of the house over the settee
    parts.append(box("pframe", (1.2, 0.08, 1.4), (-4.2, 5.95, 1.4), MET("gold", 0.3), bevel=0.04, seg=1))
    parts.append(box("pcanvas", (1.0, 0.04, 1.2), (-4.2, 5.9, 1.5), M("paint_dark", 0.6)))
    parts.append(blob("pface", (0.22, 0.02, 0.3), (-4.2, 5.87, 2.05), M("plaster_rose", 0.6), subsurf=1))
    parts.append(box("pcoat", (0.6, 0.02, 0.5), (-4.2, 5.87, 1.55), M("crimson", 0.6)))
    brass_chandelier(parts, -4.2, 3.0, H, H - 0.9, arms=8, r=0.5)
    fake_window(parts, "F", -4.3, 1.0, w=1.1, h=1.6)
    # ---- the card room: baize, cards, stakes, decanters and the punch bowl, the haze
    CX, CY = 4.3, 2.6
    parts.append(box("ctable", (1.6, 1.1, 0.72), (CX, CY, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("cbaize", (1.5, 1.0, 0.012), (CX, CY, 0.72), M("baize", 0.95)))
    col.append(box("c", (1.6, 1.1, 0.74), (CX, CY, 0)))
    for k in range(14):
        parts.append(box("card", (0.06, 0.09, 0.004), (CX + RNG.uniform(-0.6, 0.6), CY + RNG.uniform(-0.35, 0.35), 0.735), M("paper", 0.6), rot=(0, 0, RNG.uniform(0, 3))))
    for k in range(10):
        parts.append(cyl("coin", 0.013, 0.004 * RNG.randint(1, 5), (CX + RNG.uniform(-0.5, 0.5), CY + RNG.uniform(-0.3, 0.3), 0.735), MET("gold", 0.3), verts=8))
    for (dx, dy, r) in ((0, -0.85, 0.0), (0, 0.85, math.pi), (-1.1, 0, -math.pi / 2), (1.1, 0, math.pi / 2)):
        chair(parts, CX + dx, CY + dy, r, fancy=True)
    for k in range(2):
        candle(parts, CX - 0.4 + k * 0.8, CY, 0.735)
    lamp("candle", (CX, CY, 1.4))
    parts.append(box("sideboard", (1.6, 0.5, 0.9), (4.3, 4.6, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("sbtop", (1.7, 0.55, 0.04), (4.3, 4.6, 0.9), M("marble", 0.2)))
    col.append(box("c", (1.7, 0.55, 0.95), (4.3, 4.6, 0)))
    dec = [cyl("decanter", 0.08, 0.22, (0, 0, 0), M("wine", 0.1), verts=12, r2=0.035),
           cyl("dneck", 0.02, 0.08, (0, 0, 0.22), M("glass", 0.1), verts=8),
           sphere("dstopper", 0.03, (0, 0, 0.32), M("glass", 0.1), seg=8, rings=4)]
    keep(place(dec, 3.8, 4.6, 0.0, 0.94), "decanter")
    dec2 = [cyl("decanter", 0.08, 0.22, (0, 0, 0), M("tile_ochre", 0.1), verts=12, r2=0.035),
            cyl("dneck", 0.02, 0.08, (0, 0, 0.22), M("glass", 0.1), verts=8),
            sphere("dstopper", 0.03, (0, 0, 0.32), M("glass", 0.1), seg=8, rings=4)]
    keep(place(dec2, 4.05, 4.65, 0.0, 0.94), "decanter_2")
    bowl = [cyl("pbowl", 0.22, 0.14, (0, 0, 0.04), MET("pewter", 0.2), verts=16, r2=0.26),
            cyl("pfoot", 0.08, 0.05, (0, 0, 0), MET("pewter", 0.2), verts=12),
            cyl("punch", 0.25, 0.01, (0, 0, 0.16), M("wine", 0.2), verts=16),
            cbox("ladle", (0.02, 0.02, 0.35), (0.12, 0, 0.3), MET("pewter", 0.2), rot=(0, 0.5, 0))]
    keep(place(bowl, 4.75, 4.6, 0.0, 0.94), "punch_bowl")
    for k in range(4):
        parts.append(cyl("glass", 0.03, 0.09, (3.5 + k * 0.1, 4.45, 0.94), M("glass", 0.1), verts=8, r2=0.035))
    parts.append(box("pipes", (0.3, 0.15, 0.05), (CX + 0.5, CY + 0.35, 0.735), M("wood_dark")))
    for k in range(3):
        fx("smoke", (CX + (k - 1) * 0.6, CY, 1.8))
    fake_window(parts, "F", 4.3, 1.0, w=1.1, h=1.6)
    parts.append(box("cdamask", (W / 2 - 1.5, 0.02, H), ((W / 2 + 1.5) / 2, 4.88, 0), M("felt_green", 0.8)))
    # ---- the strongroom: an iron door standing open, chests, a money ledger
    iron = M("iron", 0.45)
    dx0, dy0 = 1.6, 6.5
    parts.append(cbox("irondoor", (0.08, 1.0, 2.2), (dx0 + 0.45, dy0 + 0.35, 1.1), iron, rot=(0, 0, 1.2), bevel=0.01, seg=1))
    for k in range(4):
        parts.append(cbox("idrivet", (0.1, 0.9, 0.05), (dx0 + 0.47, dy0 + 0.36, 0.3 + k * 0.5), M("iron", 0.3), rot=(0, 0, 1.2)))
    for (sx, sy, s) in ((6.2, 5.6, 1.0), (6.2, 6.6, 0.9), (6.3, 7.5, 0.8), (4.6, 7.5, 0.9)):
        parts.append(box("chest", (0.8 * s, 0.55 * s, 0.5 * s), (sx, sy, 0), M("wood_dark"), bevel=0.02, seg=1))
        for k in range(2):
            parts.append(box("cband", (0.05, 0.57 * s, 0.52 * s), (sx - 0.2 * s + k * 0.4 * s, sy, 0), iron))
        parts.append(box("clock", (0.1, 0.03, 0.12), (sx, sy - 0.29 * s, 0.25 * s), iron))
        col.append(box("c", (0.8 * s, 0.55 * s, 0.5 * s), (sx, sy, 0)))
    parts.append(box("coinbags", (0.6, 0.4, 0.05), (6.2, 5.6, 0.5), M("sack", 0.9)))
    for k in range(4):
        parts.append(blob("coinbag", (0.18, 0.16, 0.16), (6.0 + k * 0.14, 5.6, 0.5), M("sack", 0.9), subsurf=1))
    sl = [box("lcover", (0.44, 0.32, 0.05), (0, 0, 0), M("crimson", 0.8), bevel=0.01, seg=1),
          box("lclasp", (0.05, 0.1, 0.055), (0.2, 0, 0), M("brass", 0.3))]
    keep(place(sl, 6.2, 6.6, 0.3, 0.45), "strong_ledger")
    # ---- the office: the desk with the river maps, a chair, a globe; the bookcase ajar on the secret stair
    OX, OY = 4.0, 10.4
    parts.append(box("odesk", (1.8, 0.9, 0.76), (OX, OY, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("odtop", (1.9, 1.0, 0.04), (OX, OY, 0.76), M("leather", 0.7)))
    col.append(box("c", (1.9, 1.0, 0.8), (OX, OY, 0)))
    parts.append(box("map", (1.2, 0.7, 0.004), (OX - 0.1, OY, 0.8), M("paper", 0.9), rot=(0, 0, 0.05)))
    for k in range(5):
        parts.append(box("river", (0.25, 0.03, 0.002), (OX - 0.6 + k * 0.22, OY - 0.05 + math.sin(k) * 0.12, 0.805), M("icon_blue", 0.8), rot=(0, 0, math.sin(k * 1.3) * 0.6)))
    for k in range(6):
        parts.append(cyl("pin", 0.01, 0.03, (OX - 0.5 + RNG.uniform(0, 1.0), OY + RNG.uniform(-0.3, 0.3), 0.805), M("crimson", 0.5), verts=4))
    parts.append(cyl("mroll", 0.04, 0.8, (OX + 0.6, OY + 0.3, 0.84), M("paper", 0.9), verts=8, rot=(0, math.pi / 2, 0.3), center=True))
    parts.append(cyl("inkwell", 0.03, 0.05, (OX + 0.7, OY - 0.2, 0.8), M("ink", 0.3), verts=8))
    chair(parts, OX, OY + 0.75, math.pi, fancy=True)
    candle(parts, OX - 0.7, OY - 0.25, 0.8)
    lamp("candle", (OX - 0.5, OY, 1.4))
    parts.append(box("oframe", (1.4, 0.06, 1.0), (OX, 8.2, 1.4), MET("gold", 0.3)))
    parts.append(box("omap", (1.3, 0.04, 0.9), (OX, 8.24, 1.45), M("paper", 0.8)))
    for k in range(4):
        parts.append(box("omriver", (0.4, 0.01, 0.03), (OX - 0.45 + k * 0.3, 8.27, 1.8 - k * 0.12), M("icon_blue", 0.8), rot=(0, 0.3 * (-1) ** k, 0)))
    bookcase(parts, col, "R", 10.0, 3.2, H=2.6, shelves=6)
    # the hidden door: a bookcase leaf swung open off the back wall opening
    leaf = [box("hbc", (1.0, 0.3, 2.3), (0, 0, 0), M("wood_dark"), bevel=0.01, seg=1)]
    for i in range(5):
        leaf.append(box("hbcsh", (0.92, 0.26, 0.03), (0, -0.02, 0.1 + i * 0.44), M("wood", 0.8)))
    o = place(leaf, 0, 0)
    n0 = len(parts)
    for i in range(5):
        book_row(parts, "F", -0.44, 0.44, 0.13 + i * 0.44, 0.0, 0.22)
    books = parts[n0:]
    del parts[n0:]
    for b_ in books:
        edit_verts(b_, lambda co: setattr(co, "y", co.y - CTX["t"] / 2 - 0.12))
    leaf_o = join([o] + books, "hidden")
    keep(place([leaf_o], SHX - 0.5, D - 0.2, math.pi * 0.62), "hidden_door")
    # the secret stair down under the courtyard, then the brick passage to the river
    SW = 1.0
    ZB = -2.8
    y_top = D + t
    steps = 11
    run = 0.34
    y_bot = y_top + steps * run
    for sx in (-1, 1):
        wx = SHX + sx * (SW / 2 + 0.2)
        parts.append(box("shwall", (0.4, y_bot - D, 2.6 - ZB + 0.3), (wx, (D + y_bot) / 2, ZB - 0.3), M("brick_vault", 0.9), bevel=0, wonk=0.015, smooth=0))
        col.append(box("c", (0.4, y_bot - D, 2.6 - ZB + 0.3), (wx, (D + y_bot) / 2, ZB - 0.3)))
    parts.append(box("shroof", (SW + 0.8, y_bot - D, 0.3), (SHX, (D + y_bot) / 2, 2.6), M("brick_vault", 0.9)))
    col.append(box("c", (SW + 0.8, y_bot - D, 0.3), (SHX, (D + y_bot) / 2, 2.6)))
    for i in range(steps):
        zt = ZB * (i + 1) / steps
        yy = y_top + run * i
        parts.append(box("tread", (SW, run + 0.02, 0.08), (SHX, yy + run / 2, zt - 0.08), M("stone", 0.8), bevel=0.015, seg=1))
        parts.append(box("riser", (SW, 0.03, -ZB / steps + 0.08), (SHX, yy + 0.015, zt - 0.08), M("stone_dark", 0.8)))
    SURF.setdefault("stone", []).append(flip_y(prism("c", SHX - SW / 2, SHX + SW / 2, y_top, y_bot, ZB, 0.0), y_top + y_bot))
    SURF["stone"].append(box("c", (SW, t + 0.1, 0.4), (SHX, D + t / 2, -0.4)))
    parts.append(flip_y(prism("under", SHX - SW / 2, SHX + SW / 2, y_top, y_bot, ZB - 0.3, -0.05, M("brick_vault")), y_top + y_bot))
    # passage: sloping floor, walls, a low vault; water drips
    TY0, TY1 = y_bot, y_bot + 8.0
    TZ1 = ZB - 0.6
    TW = 1.4
    parts.append(flip_y(prism("tfloor", SHX - TW / 2, SHX + TW / 2, TY0, TY1, TZ1 - 0.3, ZB, M("floor_stone_b", 0.9)), TY0 + TY1))
    SURF["stone"].append(flip_y(prism("c", SHX - TW / 2, SHX + TW / 2, TY0, TY1, TZ1 - 0.3, ZB), TY0 + TY1))
    SURF["stone"].append(box("c", (TW, TY1 - TY0, 0.3), (SHX, (TY0 + TY1) / 2, TZ1 - 0.6)))
    for sx in (-1, 1):
        wx = SHX + sx * (TW / 2 + 0.2)
        parts.append(box("twall", (0.4, TY1 - TY0, 2.8), (wx, (TY0 + TY1) / 2, TZ1 - 0.3), M("brick_vault", 0.9), bevel=0, wonk=0.02, smooth=0))
        col.append(box("c", (0.4, TY1 - TY0, 2.8), (wx, (TY0 + TY1) / 2, TZ1 - 0.3)))
    vault(parts, TW, TY1 - TY0, ZB + 1.3, "brick_vault", y0=TY0, x0=SHX)
    col.append(box("c", (TW + 0.8, TY1 - TY0, 0.3), (SHX, (TY0 + TY1) / 2, ZB + 1.3 + TW / 2 + 0.05)))
    parts.append(box("tlid", (TW + 0.8, TY1 - TY0, 0.3), (SHX, (TY0 + TY1) / 2, ZB + 1.3 + TW / 2 + 0.05), M("brick_vault")))
    for k in range(3):
        fx("drip", (SHX + RNG.uniform(-0.3, 0.3), TY0 + 1.5 + k * 2.4, ZB + 1.9))
        parts.append(blob("wet", (0.5, 0.7, 0.005), (SHX + RNG.uniform(-0.2, 0.2), TY0 + 1.5 + k * 2.4, ZB - (k + 1) * 0.15 + 0.01), M("water", 0.05), subsurf=1))
    lantern(parts, SHX, TY0 + 0.6, ZB + 2.0, ZB + 1.6)
    # the boat chamber: a ledge, black water, the river arch with the grille up, the boat
    CY0, CY1 = TY1, TY1 + 4.0
    CW = 4.0
    ZW = TZ1 - 0.35
    parts.append(box("cledge", (CW, 1.2, 0.3), (SHX, CY0 + 0.6, TZ1 - 0.3), M("floor_stone", 0.9)))
    SURF["stone"].append(box("c", (CW, 1.2, 0.3), (SHX, CY0 + 0.6, TZ1 - 0.3)))
    parts.append(box("cwater", (CW, CY1 - CY0 - 1.2, 0.02), (SHX, (CY0 + 1.2 + CY1) / 2, ZW), M("water", 0.03)))
    col.append(box("c", (CW, CY1 - CY0 - 1.2, 0.3), (SHX, (CY0 + 1.2 + CY1) / 2, ZW - 0.5)))
    for (sz, loc) in (((0.4, CY1 - CY0, 3.4), (SHX - CW / 2 - 0.2, (CY0 + CY1) / 2, ZW - 0.6)), ((0.4, CY1 - CY0, 3.4), (SHX + CW / 2 + 0.2, (CY0 + CY1) / 2, ZW - 0.6))):
        parts.append(box("cwall", sz, loc, M("brick_vault", 0.9), bevel=0, wonk=0.02, smooth=0))
        col.append(box("c", sz, loc))
    for sx in (-1, 1):
        parts.append(box("cfront", ((CW - TW) / 2, 0.4, 3.4), (SHX + sx * (TW / 2 + (CW - TW) / 4), CY0 - 0.2, ZW - 0.6), M("brick_vault", 0.9), bevel=0, smooth=0))
    vault(parts, CW, CY1 - CY0, ZW + 1.2, "brick_vault", y0=CY0, x0=SHX, ribs=2, rib_mat="brick_dark")
    parts.append(box("clid", (CW + 0.8, CY1 - CY0, 0.3), (SHX, (CY0 + CY1) / 2, ZW + 1.2 + CW / 2 + 0.05), M("brick_vault")))
    col.append(box("c", (CW + 0.8, CY1 - CY0, 0.3), (SHX, (CY0 + CY1) / 2, ZW + 1.2 + CW / 2 + 0.05)))
    # the river end: an arch full of night, the grille hauled up
    parts.append(box("rend", (CW + 0.8, 0.4, 3.6), (SHX, CY1 + 0.2, ZW - 0.6), M("brick_vault", 0.9)))
    col.append(box("c", (CW + 0.8, 0.4, 3.6), (SHX, CY1 + 0.2, ZW - 0.6)))
    parts.append(arch("rnight", 2.4, 2.4, 0.05, (SHX, CY1 - 0.03, ZW), EM("night_sky", 0.6, 0.2), bevel=0))
    parts.append(box("rriver", (2.4, 0.04, 0.4), (SHX, CY1 - 0.06, ZW), M("water", 0.03)))
    parts.append(sphere("rlamp", 0.05, (SHX + 0.7, CY1 - 0.07, ZW + 0.6), EM("night_glow", 9.0), seg=6, rings=3))
    for k in range(9):
        parts.append(box("grille", (0.03, 0.05, 0.9), (SHX - 1.1 + k * 0.275, CY1 - 0.1, ZW + 1.6), M("iron", 0.45)))
    parts.append(box("grilleh", (2.4, 0.05, 0.05), (SHX, CY1 - 0.1, ZW + 1.6), M("iron", 0.45)))
    BXB, BYB = SHX, CY0 + 2.4
    hull = taper_box("hull", (1.1, 2.6, 0.45), (BXB, BYB, ZW - 0.15), M("wood_dark"), top=1.25, bevel=0.05, wonk=0.02)
    edit_verts(hull, lambda co: setattr(co, "x", BXB + (co.x - BXB) * (1.0 - 0.7 * max(0.0, abs(co.y - BYB) - 0.8) / 0.5)))
    parts.append(hull)
    parts.append(box("hinside", (0.8, 1.9, 0.03), (BXB, BYB, ZW + 0.12), M("plank_b", 0.9)))
    for k in range(2):
        parts.append(box("thwart", (0.9, 0.2, 0.04), (BXB, BYB - 0.5 + k, ZW + 0.25), M("wood", 0.8)))
    for sx in (-1, 1):
        parts.append(cbox("oar", (0.04, 2.0, 0.04), (BXB + sx * 0.5, BYB, ZW + 0.35), M("wood", 0.8), rot=(0, 0, sx * 0.1)))
    parts.append(cbox("mooring", (0.02, 1.4, 0.02), (BXB, CY0 + 1.0, ZW + 0.2), M("straw", 0.9), rot=(0.1, 0, 0)))
    parts.append(cyl("bollard", 0.08, 0.35, (BXB, CY0 + 0.4, TZ1), M("wood_dark"), verts=8))
    col.append(box("c", (1.2, 2.7, 0.4), (BXB, BYB, ZW - 0.15)))
    exit_marker("boat", (BXB, BYB, ZW + 0.3), 0.0)
    for j in range(6):
        parts.append(box("ugate", (0.04, 0.04, 2.0), (SHX + CW / 2 - 0.05, CY0 + 0.15 + j * 0.18, TZ1), M("iron", 0.35)))
    exit_marker("undercroft", (SHX + CW / 2 - 0.6, CY0 + 0.6, TZ1), -math.pi / 2)
    lamp("lantern", (SHX - 1.2, CY0 + 0.5, TZ1 + 1.4))
    parts.append(cyl("lpost", 0.03, 1.2, (SHX - 1.2, CY0 + 0.5, TZ1), M("iron", 0.6), verts=6))
    parts.append(box("lglass", (0.18, 0.18, 0.26), (SHX - 1.2, CY0 + 0.5, TZ1 + 1.2), EM("lamp_glass", 6.0)))
    # ---- the dining room: a long table laid, chairs, a sideboard with silver, candelabra
    DX, DY = -4.3, 9.0
    table(parts, col, DX, DY, L=3.2, w=1.1, h=0.76, along_y=True, trestle=False)
    parts.append(box("dcloth", (1.2, 3.3, 0.18), (DX, DY, 0.6), M("linen", 0.9), bevel=0.02, seg=1))
    for k in range(4):
        for sx in (-1, 1):
            chair(parts, DX + sx * 0.8, DY - 1.2 + k * 0.8, sx * math.pi / 2, fancy=True)
            plate(parts, DX + sx * 0.35, DY - 1.2 + k * 0.8, 0.78)
    for yy in (DY - 0.8, DY + 0.8):
        parts.append(cyl("dcand", 0.04, 0.35, (DX, yy, 0.78), MET("gold", 0.3), verts=8))
        for dx in (-0.1, 0.0, 0.1):
            candle(parts, DX + dx, yy, 1.13, h=0.16, r=0.015, holder=False)
    lamp("candle", (DX, DY, 1.6))
    parts.append(cyl("roast", 0.18, 0.1, (DX, DY, 0.78), MET("pewter", 0.2), verts=12))
    parts.append(blob("goose", (0.28, 0.2, 0.14), (DX, DY, 0.84), M("crust", 0.6), subsurf=1))
    parts.append(box("dsideb", (0.5, 1.8, 0.9), (-W / 2 + 0.3, 8.5, 0), M("wood_dark"), bevel=0.02, seg=1))
    col.append(box("c", (0.55, 1.8, 0.95), (-W / 2 + 0.3, 8.5, 0)))
    for k in range(4):
        parts.append(cyl("silver", 0.05, 0.2, (-W / 2 + 0.3, 7.9 + k * 0.4, 0.9), MET("pewter", 0.15), verts=10, r2=0.03))
    parts.append(box("dpaper", (0.02, 6.0, H), (-W / 2 + 0.01, 9.0, 0), M("wall_green", 0.8)))
    brass_chandelier(parts, DX, DY, H, H - 0.9, arms=6, r=0.45)
    # ---- upstairs, the bedroom: canopy bed, the mistress's dressing table, a wardrobe
    BZ = FL
    n0, c0 = len(parts), len(col)
    bed(parts, col, -5.2, D - 1.2, 0.0, w=1.6, L=2.1, blanket="velvet", canopy="curtain_red")
    dt = [box("dtable", (1.2, 0.5, 0.74), (0, 0, 0), M("tile_w", 0.4), bevel=0.02, seg=1),
          box("dskirt", (1.26, 0.56, 0.6), (0, 0, 0.1), M("wall_rose", 0.9), bevel=0.04, seg=1, wonk=0.02),
          box("dmirror", (0.6, 0.04, 0.8), (0, 0.2, 0.78), MET("mirror", 0.04)),
          box("dmframe", (0.7, 0.03, 0.9), (0, 0.23, 0.73), MET("gold", 0.3))]
    for k in range(5):
        dt.append(cyl("dbottle", 0.025, 0.1, (-0.45 + k * 0.1, -0.05, 0.74), M(RNG.choice(("glass", "wine", "tile_ochre", "icon_blue")), 0.1), verts=8, r2=0.012))
    dt.append(cyl("powder", 0.06, 0.05, (0.35, -0.08, 0.74), M("wall_rose", 0.5), verts=10))
    dt.append(sphere("puff", 0.04, (0.35, -0.08, 0.81), M("flour", 0.9), seg=8, rings=4))
    dt.append(box("fan", (0.2, 0.08, 0.01), (0.1, -0.15, 0.745), M("zupan_gold", 0.7), rot=(0, 0, 0.3)))
    parts.append(place(dt, -2.4, D - 0.4, math.pi))
    col.append(box("c", (1.26, 0.56, 0.8), (-2.4, D - 0.4, 0)))
    chair(parts, -2.4, D - 1.0, math.pi, fancy=True)
    parts.append(box("wardrobe", (0.6, 1.4, 2.3), (-W / 2 + 0.35, 7.2, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("wcrest", (0.66, 1.5, 0.2), (-W / 2 + 0.35, 7.2, 2.3), MET("gold", 0.3), bevel=0.03, seg=1))
    col.append(box("c", (0.6, 1.4, 2.4), (-W / 2 + 0.35, 7.2, 0)))
    rug(parts, -3.8, 9.2, 2.6, 2.0, mat="velvet", border="zupan_gold")
    candle(parts, -2.7, D - 0.45, 0.74)
    lamp("candle", (-2.4, D - 1.0, 1.5))
    lamp("candle", (-4.3, 9.4, 2.0))
    for o in parts[n0:] + col[c0:]:
        edit_verts(o, lambda co: setattr(co, "z", co.z + BZ))
    for L_ in LAMPS[-3:]:
        L_.location.z += BZ
    for k in range(4):
        parts.append(box("hbal", (0.04, 0.04, 0.95), (-0.45, SY0 + 0.3 + k * 1.2, BZ), M("wood_dark")))
    parts.append(box("hrail", (0.07, SY1 - SY0, 0.07), (-0.45, (SY0 + SY1) / 2, BZ + 0.95), M("wood", 0.8)))
    parts.append(box("hrail", (1.0, 0.07, 0.07), (-1.0, SY0, BZ + 0.95), M("wood", 0.8)))
    col.append(box("c", (0.08, SY1 - SY0, 1.0), (-0.45, (SY0 + SY1) / 2, BZ)))
    col.append(box("c", (1.0, 0.08, 1.0), (-1.0, SY0, BZ)))
    fake_window(parts, "B", -4.0, BZ + 1.0, w=1.0, h=1.5)
    # ---- out the back: the courtyard under the night sky, the stable, the privy, a pump
    YC0, YC1 = D + t, D + t + 6.0
    floor_region(parts, "flags", -W / 2, W / 2, YC0, YC1)
    for (sz, loc) in (((t, YC1 - YC0 + t, 4.0), (-W / 2 - t / 2, (YC0 + YC1) / 2, 0)), ((t, YC1 - YC0 + t, 4.0), (W / 2 + t / 2, (YC0 + YC1) / 2, 0)),
                      ((W + 2 * t, t, 4.0), (0, YC1 + t / 2, 0))):
        parts.append(box("ywall", sz, loc, M("brick", 0.9), bevel=0, wonk=0.02, smooth=0))
        col.append(box("c", sz, loc))
        parts.append(box("ysnow", (sz[0] + 0.04, sz[1] + 0.04, 0.06), (loc[0], loc[1], 4.0), M("snow", 0.6)))
    parts.append(box("sky", (W + 6, YC1 - YC0 + 6, 0.1), (0, (YC0 + YC1) / 2, 11.0), EM("night_sky", 0.45, 0.2)))
    parts.append(box("skyside", (W + 6, 0.1, 7.0), (0, YC1 + 3.0, 4.0), EM("night_sky", 0.45, 0.2)))
    for k in range(40):
        parts.append(sphere("star", 0.03, (RNG.uniform(-W / 2 - 2, W / 2 + 2), RNG.uniform(YC0 - 2, YC1 + 2.9), 10.94), EM("star", 3.0), seg=4, rings=2))
    for k in range(10):
        parts.append(blob("snow", (RNG.uniform(0.6, 1.5), RNG.uniform(0.4, 1.0), 0.05), (RNG.uniform(-6, 6), RNG.uniform(YC0 + 0.5, YC1 - 0.5), 0), M("snow", 0.6), subsurf=1, wonk=0.05))
    # the stable along the left wall: lean-to roof on posts, two stalls, a hay rack, a saddle, harness
    SX0, SX1 = -W / 2, -2.4
    SY_ = YC1 - 3.2
    parts.append(cbox("sroof", (SX1 - SX0 + 0.4, 3.6, 0.12), ((SX0 + SX1) / 2, YC1 - 1.6, 2.8), M("shingle", 0.9), rot=(-0.25, 0, 0)))
    for x in (SX0 + 0.2, (SX0 + SX1) / 2, SX1):
        parts.append(box("spost", (0.18, 0.18, 2.4), (x, SY_, 0), M("timber")))
        col.append(box("c", (0.18, 0.18, 2.4), (x, SY_, 0)))
    for x in (SX0 + 1.5, (SX0 + SX1) / 2 + 0.6):
        parts.append(box("stall", (0.08, 2.6, 1.4), (x, YC1 - 1.4, 0), M("wood_dark"), bevel=0.01, seg=1))
        col.append(box("c", (0.08, 2.6, 1.4), (x, YC1 - 1.4, 0)))
    parts.append(box("hayrack", (SX1 - SX0 - 0.5, 0.4, 0.6), ((SX0 + SX1) / 2, YC1 - 0.25, 1.3), M("wood", 0.8)))
    for k in range(6):
        parts.append(blob("hay", (RNG.uniform(0.6, 1.1), RNG.uniform(0.5, 0.9), RNG.uniform(0.1, 0.3)), (RNG.uniform(SX0 + 0.5, SX1 - 0.5), RNG.uniform(YC1 - 2.5, YC1 - 0.4), 0), M("hay", 0.95), subsurf=1, wonk=0.04))
    parts.append(box("strestle", (0.25, 0.8, 0.9), (SX1 - 0.5, SY_ - 0.8, 0), M("wood_dark")))
    parts.append(blob("saddle", (0.45, 0.6, 0.2), (SX1 - 0.5, SY_ - 0.8, 0.9), M("leather", 0.7), subsurf=1))
    lantern(parts, (SX0 + SX1) / 2, SY_ + 0.6, 2.6, 2.0)
    # the privy in the far right corner, the pump in the middle, the secret stair's housing is brick
    PX, PY = W / 2 - 0.7, YC1 - 0.7
    parts.append(box("privy", (1.0, 1.0, 2.2), (PX, PY, 0), M("plank_b", 0.9), bevel=0.01, seg=1, wonk=0.02))
    parts.append(cbox("proof", (1.2, 1.2, 0.08), (PX, PY, 2.25), M("shingle", 0.9), rot=(0.2, 0, 0)))
    parts.append(box("pdoor", (0.7, 0.04, 1.9), (PX, PY - 0.52, 0.05), M("wood_dark", 0.9)))
    parts.append(box("pmoon", (0.08, 0.02, 0.12), (PX, PY - 0.55, 1.6), M("coal", 0.9)))
    col.append(box("c", (1.0, 1.0, 2.2), (PX, PY, 0)))
    parts.append(box("pump", (0.25, 0.25, 1.2), (1.0, YC0 + 3.0, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(cbox("phandle", (0.04, 0.6, 0.04), (1.0, YC0 + 2.8, 1.25), M("iron", 0.5), rot=(0.4, 0, 0)))
    parts.append(cyl("ptrough", 0.3, 0.3, (1.0, YC0 + 2.6, 0), M("wood", 0.8), verts=10))
    parts.append(cyl("pice", 0.28, 0.01, (1.0, YC0 + 2.6, 0.28), M("snow", 0.3), verts=10))
    col.append(box("c", (0.6, 0.8, 1.2), (1.0, YC0 + 2.8, 0)))
    parts.append(box("shhouse", (SW + 0.8, y_bot - D - t, 2.9), (SHX, (D + t + y_bot) / 2, 0), M("brick", 0.9), bevel=0.02, seg=1))
    CTX["surface"] = "tiles"
    # bodyguards and the household
    post(0.6, 3.6, math.pi)                                 # 0 bodyguard in the hall, watching the door
    post_at(1.0, 2.0, -1.0, 2.5)                            # 1 at the card room door
    post_at(1.0, 9.4, -1.0, 9.4)                            # 2 at the office door
    post(0.0, D - 1.0, 0.0)                                 # 3 the one who always looks behind: faces the back door
    post_at(CX, CY + 0.85, CX, CY)                          # 4 the kingpin at cards
    post_at(CX - 1.1, CY, CX, CY)                           # 5 a player
    post_at(CX + 1.1, CY, CX, CY)                           # 6 a player
    post_at(FX_ - 0.1, FY_, -1.0, FY_)                      # 7 the footman in his chair
    post_at(-2.4, D - 1.0, -2.4, D, z=BZ)                   # 8 the mistress at her dressing table
    post_at(OX, OY + 0.75, OX, OY)                          # 9 at the office desk
    post_at(SX1 - 1.0, SY_ - 0.4, SX1 - 0.5, SY_ - 0.8)     # 10 the stable boy
    post_at(-3.5, 1.8, -3.8, 3.0)                           # 11 in the parlour
    finish_set("int_house_kingpin", parts, col)


def int_bath_lazna():
    """Laznia: the changing room (benches, hooks, the attendant's towels, a rack where weapons are left), the steam
    room (tiered benches, the stove heaped with hot stones, the water tub and ladle, birch whisks), the cold plunge
    and the masseur's slab, oil lamps in niches, wet stone underfoot, a back door to the alley."""
    start()
    W, D, H = 10.0, 9.0, 3.2
    YP = 3.6
    parts, col = room(W, D, H, "stone_pale", "flags", "flat", t=0.4)
    CTX["H"] = H
    iwall(parts, col, "x", -W / 2, W / 2, YP, 0, H, "stone_pale", [(-2.5, 1.0, 2.2), (2.5, 1.2, 2.3)], t=0.3, trim="wood_dark")
    iwall(parts, col, "y", YP, D, 0.2, 0, H, "stone_pale", [], t=0.3, trim=None)
    parts.append(box("steamceil", (W / 2 + 0.05, D - YP - 0.15, 0.08), ((-W / 2 + 0.05) / 2, (YP + D) / 2, 2.75), M("plank_b", 0.9)))
    for k in range(6):
        parts.append(box("steambeam", (W / 2 + 0.05, 0.14, 0.16), ((-W / 2 + 0.05) / 2, YP + 0.5 + k * 0.9, 2.6), M("beam"), bevel=0.02, seg=1))
    for k in range(9):
        parts.append(blob("wet", (RNG.uniform(0.4, 1.0), RNG.uniform(0.3, 0.7), 0.003), (RNG.uniform(-4, 4), RNG.uniform(0.6, D - 0.6), 0.0), M("water", 0.04), subsurf=2, wonk=0.08))
    # changing room: benches along the front and left walls, hooks with clothes, the weapons rack, towels
    for (x, y, L, along) in ((-3.2, 0.5, 2.6, False), (-W / 2 + 0.35, 2.0, 2.6, True)):
        bench(parts, x, y, L=L, along_y=along)
    pegs(parts, "L", 0.6, 3.2, 1.7)
    for k, cm in enumerate(("brown_coat", "navy", "sukmana", "coat_blue")):
        hanging_coat(parts, "L", 0.9 + k * 0.6, 1.72, cm)
    pegs(parts, "F", -4.4, -1.8, 1.7)
    for k, cm in enumerate(("green_coat", "brown_coat", "linen")):
        hanging_coat(parts, "F", -4.0 + k * 0.8, 1.72, cm)
    rack = [box("wrback", (1.6, 0.05, 1.2), (0, 0.2, 0.9), M("wood_dark"), bevel=0.01, seg=1),
            box("wrshelf", (1.6, 0.3, 0.05), (0, 0.05, 0.9), M("wood_dark"))]
    for k in range(3):
        a = -0.6 + k * 0.6
        rack.append(cbox("sword", (0.02, 0.02, 0.95), (a, 0.12, 1.5), M("pewter", 0.3), rot=(0, 0.1, 0)))
        rack.append(box("hilt", (0.14, 0.03, 0.03), (a - 0.05, 0.12, 1.95), MET("brass", 0.3)))
    for k in range(2):
        rack.append(box("pistol", (0.3, 0.05, 0.05), (-0.3 + k * 0.6, 0.02, 0.96), M("musket", 0.7), rot=(0, 0, 0.2)))
        rack.append(box("pbarrel", (0.2, 0.025, 0.025), (-0.25 + k * 0.6, 0.0, 0.99), M("iron", 0.35)))
    rack.append(cbox("cudgel", (0.05, 0.05, 0.8), (0.65, 0.1, 0.4), M("wood", 0.8), rot=(0.1, 0.15, 0)))
    wr = place(rack, W / 2 - 0.25, 1.9, math.pi / 2)
    keep(wr, "weapons_rack")
    col.append(box("c", (0.4, 1.7, 2.1), (W / 2 - 0.2, 1.9, 0)))
    parts.append(box("adesk", (1.2, 0.6, 0.9), (2.2, 1.2, 0), M("wood_dark"), bevel=0.02, seg=1))
    col.append(box("c", (1.2, 0.6, 0.95), (2.2, 1.2, 0)))
    for k in range(5):
        parts.append(box("towel", (0.4, 0.3, 0.07), (1.9, 1.2, 0.9 + k * 0.07), M("linen", 0.9), bevel=0.02, seg=1))
    parts.append(box("coinbox", (0.25, 0.18, 0.1), (2.5, 1.2, 0.9), M("wood", 0.7)))
    candle(parts, 2.7, 1.1, 0.9)
    lamp("candle", (2.4, 1.0, 1.5))
    # the steam room: tiered benches along the back and left walls, the stove with its stones, the tub, whisks
    for tier in range(3):
        z = 0.45 * (tier + 1)
        dep = 0.55 * (3 - tier)
        parts.append(box("tier", (5.0 - tier * 0.2, dep, 0.06), (-2.4, D - dep / 2, z - 0.06), M("plank", 0.8), bevel=0.01, seg=1))
        parts.append(box("tierface", (5.0 - tier * 0.2, 0.04, z), (-2.4, D - dep, 0), M("plank_b", 0.8)))
        col.append(box("c", (5.0 - tier * 0.2, dep, z), (-2.4, D - dep / 2, 0)))
    SX, SY = -0.8, YP + 1.0
    parts.append(box("sstove", (1.2, 1.0, 0.9), (SX, SY, 0), M("brick", 0.9), bevel=0.04, seg=1, wonk=0.02))
    parts.append(box("sfire", (0.34, 0.02, 0.24), (SX, SY - 0.51, 0.15), EM("fire", 6.0)))
    for k in range(18):
        parts.append(blob("stone", (0.18, 0.16, 0.12), (SX + RNG.uniform(-0.45, 0.45), SY + RNG.uniform(-0.35, 0.35), 0.9 + RNG.uniform(0, 0.15)),
                          EM("fire", 0.8, 0.8) if k % 4 == 0 else M("stone_dark", 0.8), subsurf=1))
    col.append(box("c", (1.2, 1.0, 1.1), (SX, SY, 0)))
    lamp("stove", (SX, SY - 0.8, 0.5))
    for k in range(2):
        fx("steam", (SX + (k - 0.5) * 0.5, SY, 1.2))
    fx("steam", (-2.4, D - 1.2, 2.0))
    parts.append(cyl("tub", 0.35, 0.5, (-3.6, YP + 0.7, 0), M("wood", 0.8), verts=12, r2=0.38))
    for zz in (0.08, 0.4):
        parts.append(cyl("thoop", 0.37, 0.04, (-3.6, YP + 0.7, zz), M("iron", 0.5), verts=12))
    parts.append(cyl("twater", 0.35, 0.01, (-3.6, YP + 0.7, 0.46), M("water", 0.05), verts=12))
    parts.append(cbox("ladle", (0.03, 0.5, 0.03), (-3.4, YP + 0.7, 0.62), M("wood", 0.7), rot=(0.4, 0, 0.3)))
    col.append(cyl("c", 0.38, 0.5, (-3.6, YP + 0.7, 0), None, verts=8))
    for k in range(5):
        herb_bunch(parts, -4.6, YP + 0.5 + k * 0.5, 2.3, s=1.3)
    for x in (-3.8, -1.2):
        chain_lamp(parts, x, D - 1.6, 2.72, 2.05)
    # the plunge room: the cold basin with steps, the masseur's slab with oils, lamps in niches, the back door
    PX, PY = 2.8, D - 1.4
    parts.append(box("basin", (2.4, 1.8, 0.85), (PX, PY, 0), M("stone", 0.7), bevel=0.04, seg=1, wonk=0.01))
    parts.append(box("bwater", (2.1, 1.5, 0.01), (PX, PY, 0.8), M("water", 0.03)))
    parts.append(box("bstep", (0.8, 0.35, 0.4), (PX, PY - 1.07, 0), M("stone", 0.7), bevel=0.02, seg=1))
    col.append(box("c", (2.4, 1.8, 0.85), (PX, PY, 0)))
    col.append(box("c", (0.8, 0.35, 0.4), (PX, PY - 1.07, 0)))
    MX, MY = 2.0, YP + 1.4
    parts.append(box("slab", (0.8, 2.0, 0.8), (MX, MY, 0), M("marble", 0.3), bevel=0.03, seg=1))
    parts.append(box("slabcloth", (0.84, 1.2, 0.02), (MX, MY + 0.2, 0.8), M("linen", 0.9), bevel=0.01, seg=1, wonk=0.02))
    col.append(box("c", (0.8, 2.0, 0.82), (MX, MY, 0)))
    for k in range(3):
        parts.append(cyl("oil", 0.04, 0.14, (MX + 0.3, MY - 0.8 + k * 0.1, 0.8), M(("glass_green", "tile_ochre", "copper")[k], 0.2), verts=8, r2=0.015))
    for (side, u) in (("R", 4.8), ("B", 1.4), ("B", 4.0)):
        parts.append(warch(side, "niche", 0.4, 0.5, 0.05, u, 0.02, 1.6, M("coal", 0.9), bevel=0))
        nx, ny = _wpos(side, u, 0.15)
        parts.append(cyl("olamp", 0.05, 0.04, (nx, ny, 1.6), M("terracotta", 0.6), verts=8, r2=0.03))
        parts.append(cyl("oflame", 0.01, 0.04, (nx, ny, 1.64), EM("flame", 8.0), verts=6, r2=0.0))
        lamp("candle", (nx, ny, 1.8))
    DU = 5.8
    parts.append(wl("R", "bdoor", 1.0, 0.08, 2.1, DU, 0.04, 0, M("wood_dark"), bevel=0.02, seg=1))
    for zz in (0.4, 1.6):
        parts.append(wl("R", "bstrap", 0.8, 0.03, 0.07, DU, 0.09, zz, M("iron", 0.6)))
    parts.append(wl("R", "bframe", 1.2, 0.05, 2.25, DU, 0.02, 0, M("beam")))
    parts.append(wl("R", "bbar", 1.1, 0.08, 0.1, DU, 0.14, 1.1, M("wood", 0.8)))
    ex, ey = _wpos("R", DU, 0.6)
    exit_marker("back", (ex, ey, 0.0), -math.pi / 2)
    for k in range(3):
        parts.append(cyl("bucket", 0.15, 0.3, (4.2 + (k % 2) * 0.3, YP + 0.5 + k * 0.3, 0), M("wood", 0.8), verts=10, r2=0.17))
    fake_window(parts, "F", 3.8, 1.6, w=0.7, h=0.7)
    lantern(parts, 0.0, 1.8, H, 2.3)
    lantern(parts, 2.6, 6.0, H, 2.3)
    CTX["surface"] = "stone"
    post_at(-2.4, D - 0.7, -2.4, 0.0, z=1.35)               # the kingpin on the top tier of the steam room
    post_at(-1.2, D - 1.8, -2.4, 0.0, z=0.9)                # a guard sweating beside him
    post_at(SX - 0.9, SY - 0.7, SX, SY)                     # the stoker at the stones
    post_at(MX + 0.7, MY, MX, MY)                           # the masseur at his slab
    post(2.2, 1.9, math.pi)                                 # the attendant behind the towels
    post_at(W / 2 - 1.0, 1.9, W / 2, 1.9)                   # the man who minds the weapons rack
    post_at(ex - 0.6, ey, ex + 1.0, ey)                     # by the back door
    finish_set("int_bath_lazna", parts, col)


def int_store_warehouse():
    """Spichlerz on the quay: a cavernous store of bales and casks, a hoist over the hatch into the loft, the
    clerk's cabin with its lit window and strongbox, a back door to the river."""
    start()
    W, D, H = 14.0, 16.0, 7.6
    LZ = 3.6                             # loft floor level
    LY0 = 9.0                            # loft from here to the back
    parts, col = room(W, D, H, "plank_b", "planks", "beams", beam_step=2.0, t=0.35, door_w=2.2, door_h=3.0)
    CTX["H"] = H
    timber_frame(parts, "LRB", H, step=2.6, rail=LZ + 0.2)
    # the loft: floor with the hatch, joists, rail along its edge, a steep stair
    HX0, HX1, HY0, HY1 = -1.0, 1.0, 10.5, 12.5
    for (x0, x1, y0, y1) in ((-W / 2, HX0, LY0, D), (HX1, W / 2, LY0, D), (HX0, HX1, LY0, HY0), (HX0, HX1, HY1, D)):
        parts.append(box("loft", (x1 - x0, y1 - y0, 0.15), ((x0 + x1) / 2, (y0 + y1) / 2, LZ - 0.15), M("plank", 0.8)))
        SURF.setdefault("planks", []).append(box("c", (x1 - x0, y1 - y0, 0.15), ((x0 + x1) / 2, (y0 + y1) / 2, LZ - 0.15)))
    for k in range(9):
        y = LY0 + 0.3 + k * (D - LY0 - 0.6) / 8
        if HY0 - 0.1 < y < HY1 + 0.1:
            continue
        parts.append(box("joist", (W, 0.2, 0.25), (0, y, LZ - 0.4), M("beam"), bevel=0.02, seg=1, wonk=0.02))
    parts.append(box("lbeam", (W, 0.3, 0.35), (0, LY0 + 0.15, LZ - 0.5), M("beam"), bevel=0.02, seg=1))
    for x in (-4.5, -1.5, 1.5, 4.5):
        parts.append(box("lpost", (0.3, 0.3, LZ - 0.5), (x, LY0 + 0.15, 0), M("beam"), bevel=0.02, seg=1, wonk=0.02))
        col.append(box("c", (0.3, 0.3, LZ), (x, LY0 + 0.15, 0)))
    parts.append(box("lrail", (W - 2.0, 0.08, 0.08), (1.0, LY0 + 0.05, LZ + 0.95), M("wood", 0.8)))
    for k in range(12):
        parts.append(box("lbal", (0.06, 0.06, 0.95), (-5.5 + k * 1.0, LY0 + 0.05, LZ), M("wood_dark")))
    col.append(box("c", (W - 2.0, 0.1, 1.0), (1.0, LY0 + 0.05, LZ)))
    for (x0, x1, y0, y1) in ((HX0, HX1, HY0 - 0.05, HY0 + 0.05), (HX0, HX1, HY1 - 0.05, HY1 + 0.05), (HX0 - 0.05, HX0 + 0.05, HY0, HY1), (HX1 - 0.05, HX1 + 0.05, HY0, HY1)):
        parts.append(box("hcoaming", (x1 - x0, y1 - y0, 0.12), ((x0 + x1) / 2, (y0 + y1) / 2, LZ), M("beam")))
    stair(parts, col, -W / 2 + 0.7, LY0 - 3.64, 0.0, width=1.0, rise=LZ, steps=14, run=0.26, rail_sides=(1,))
    # the hoist: a beam out over the hatch under the ridge, pulley, rope, a bale hanging on the hook
    parts.append(box("hbeam", (0.3, 5.0, 0.35), (0.0, (HY0 + HY1) / 2, H - 0.6), M("beam"), bevel=0.03, seg=1))
    parts.append(cyl("pulley", 0.22, 0.08, (0.0, (HY0 + HY1) / 2, H - 0.95), M("wood", 0.7), verts=14, rot=(0, math.pi / 2, 0), center=True))
    parts.append(cyl("rope", 0.02, H - 1.2 - 2.6, (0.0, (HY0 + HY1) / 2 - 0.2, 2.6), M("straw", 0.9), verts=6))
    parts.append(cyl("rope2", 0.02, H - 1.0, (0.0, (HY0 + HY1) / 2 + 0.2, 0.0), M("straw", 0.9), verts=6))
    parts.append(torus("hook", 0.08, 0.02, (0.0, (HY0 + HY1) / 2 - 0.2, 2.55), M("iron", 0.5), rot=(math.pi / 2, 0, 0), seg=10, mseg=4))
    parts.append(box("hbale", (1.0, 0.7, 0.8), (0.0, (HY0 + HY1) / 2 - 0.2, 1.7), M("canvas", 0.9), bevel=0.06, seg=1, wonk=0.03))
    for dx in (-0.25, 0.25):
        parts.append(box("hrope", (0.03, 0.72, 0.82), (dx, (HY0 + HY1) / 2 - 0.2, 1.69), M("straw", 0.9)))
    parts.append(cyl("winch", 0.18, 1.0, (0.9, (HY0 + HY1) / 2 + 0.6, 0.9), M("wood", 0.8), verts=10, rot=(0, math.pi / 2, 0), center=True))
    for sx in (-1, 1):
        parts.append(box("wpost", (0.12, 0.3, 1.0), (0.9 + sx * 0.55, (HY0 + HY1) / 2 + 0.6, 0), M("wood_dark")))
    col.append(box("c", (1.3, 0.4, 1.1), (0.9, (HY0 + HY1) / 2 + 0.6, 0)))
    lamp("lantern", (0.3, HY0 - 0.2, LZ + 2.0))
    # bales in stacks (flammable), casks in rows with one tapped for tasting (poisonable)
    stacks = [(-5.2, 3.0, 3, 2), (-5.2, 6.0, 2, 2), (4.5, 10.8, 3, 3), (-3.0, 13.5, 2, 2), (5.0, 14.2, 3, 2)]
    for si, (bx, by, nz, ny) in enumerate(stacks):
        p = []
        for iz in range(nz):
            for iy in range(ny):
                for ix in range(2):
                    p.append(box("bale", (1.0, 0.8, 0.7), (bx - 0.5 + ix * 1.02, by - 0.4 * (ny - 1) + iy * 0.82, iz * 0.72), M(RNG.choice(("canvas", "sack")), 0.9), bevel=0.05, seg=1, wonk=0.03))
                    p.append(box("brope", (0.03, 0.82, 0.72), (bx - 0.5 + ix * 1.02 + 0.2, by - 0.4 * (ny - 1) + iy * 0.82, iz * 0.72 - 0.01), M("straw", 0.9)))
        z_off = LZ if by > LY0 else 0.0
        o = place(p, 0, 0, 0.0, z_off)
        keep(o, "bales_%d" % si)
        col.append(box("c", (2.05, 0.82 * ny, 0.72 * nz), (bx, by, z_off)))
    for row in range(2):
        for k in range(5):
            cask(parts, col, -1.8 + k * 0.95, 2.4 + row * 1.3, 0.0, r=0.4, L=1.0, rot=math.pi / 2, cradle=True, mark=True)
    tcask = [cyl("cask", 0.44 * 0.86, 0.55, (0, -0.275, 0.62), M("wood", 0.8), verts=14, r2=0.44, rot=(-math.pi / 2, 0, 0), center=True),
             cyl("cask", 0.44, 0.55, (0, 0.275, 0.62), M("wood", 0.8), verts=14, r2=0.44 * 0.86, rot=(-math.pi / 2, 0, 0), center=True),
             cyl("head", 0.37, 0.02, (0, -0.56, 0.62), M("wood_dark"), verts=14, rot=(math.pi / 2, 0, 0), center=True),
             cyl("tap", 0.025, 0.14, (0, -0.62, 0.4), M("brass", 0.35), verts=6, rot=(math.pi / 2, 0, 0), center=True),
             box("chalk", (0.3, 0.01, 0.1), (0, -0.58, 0.8), M("flour", 0.9))]
    for yy in (-0.45, 0.0, 0.45):
        tcask.append(cyl("hoop", 0.45, 0.05, (0, yy, 0.62), M("iron", 0.6), verts=14, rot=(math.pi / 2, 0, 0), center=True))
    for yy in (-0.35, 0.35):
        tcask.append(box("cradle", (0.8, 0.12, 0.22), (0, yy, 0), M("wood_dark"), bevel=0.02, seg=1))
    keep(place(tcask, 2.7, 5.4, 0.0), "tasting_cask")
    col.append(box("c", (0.9, 1.1, 1.1), (2.7, 5.4, 0)))
    parts.append(cyl("tcup", 0.04, 0.08, (2.4, 4.7, 0), M("pewter", 0.3), verts=8))
    for k in range(6):
        parts.append(box("crate", (0.7, 0.7, 0.6), (-5.6 + (k % 3) * 0.75, 10.5 + (k // 3) * 0.75, 0), M("wood", 0.8), bevel=0.03, seg=1, wonk=0.02))
    col.append(box("c", (2.3, 1.5, 0.6), (-4.85, 10.9, 0)))
    for k in range(5):
        parts.append(blob("sack", (0.5, 0.4, 0.7), (-3.4 + k * 0.45, 7.8, 0), M("sack", 0.95), subsurf=1, wonk=0.04))
    col.append(box("c", (2.4, 0.5, 0.7), (-2.5, 7.8, 0)))
    # the steelyard on a post, a handcart
    parts.append(box("spost", (0.2, 0.2, 2.8), (1.8, 7.5, 0), M("beam")))
    parts.append(cbox("syard", (1.6, 0.05, 0.05), (1.8, 7.3, 2.5), M("iron", 0.45), rot=(0, 0.1, 0)))
    parts.append(cyl("sweight", 0.08, 0.14, (2.4, 7.3, 2.2), M("iron", 0.45), verts=8))
    col.append(box("c", (0.2, 0.2, 2.8), (1.8, 7.5, 0)))
    # the clerk's cabin by the door: timber walls, a lit window, the desk, the strongbox
    CX0, CX1, CY0, CY1 = 3.2, 6.6, 0.4, 3.6
    CH = 2.5
    iwall(parts, col, "y", CY0, CY1, CX0, 0, CH, "plank", [(2.6, 0.9, 2.1)], t=0.1, trim="beam")
    iwall(parts, col, "x", CX0, CX1, CY1, 0, CH, "plank", [], t=0.1, trim=None)
    parts.append(box("croof", (CX1 - CX0 + 0.3, CY1 - CY0 + 0.3, 0.12), ((CX0 + CX1) / 2, (CY0 + CY1) / 2, CH), M("plank_b", 0.8)))
    col.append(box("c", (CX1 - CX0 + 0.3, CY1 - CY0 + 0.3, 0.12), ((CX0 + CX1) / 2, (CY0 + CY1) / 2, CH)))
    parts.append(box("cwglow", (1.2, 0.12, 0.8), (4.9, CY1, 1.2), EM("warm_glass", 0.7, 0.3)))
    parts.append(box("cwmull", (1.25, 0.14, 0.05), (4.9, CY1, 1.58), M("beam")))
    parts.append(box("cwmull", (0.05, 0.14, 0.85), (4.9, CY1, 1.18), M("beam")))
    parts.append(box("cwglow2", (0.12, 0.9, 0.8), (CX0, 1.2, 1.2), EM("warm_glass", 0.7, 0.3)))
    parts.append(box("cdesk", (1.2, 0.6, 0.78), (5.3, CY1 - 0.5, 0), M("wood_dark"), bevel=0.02, seg=1))
    col.append(box("c", (1.2, 0.6, 0.8), (5.3, CY1 - 0.5, 0)))
    parts.append(box("cledger", (0.4, 0.3, 0.05), (5.2, CY1 - 0.5, 0.78), M("leather_b", 0.8)))
    parts.append(box("cpapers", (0.3, 0.2, 0.02), (5.7, CY1 - 0.45, 0.78), M("paper", 0.9)))
    candle(parts, 4.8, CY1 - 0.45, 0.78)
    lamp("candle", (5.0, CY1 - 1.0, 1.5))
    chair(parts, 5.3, CY1 - 1.1, 0.0)
    sb = [box("sbox", (0.8, 0.5, 0.5), (0, 0, 0), M("iron", 0.45), bevel=0.02, seg=1),
          box("sblid", (0.84, 0.54, 0.08), (0, 0, 0.5), M("iron", 0.4), bevel=0.02, seg=1),
          box("sblock", (0.12, 0.04, 0.14), (0, -0.27, 0.3), M("brass", 0.3))]
    keep(place(sb, 6.1, 1.0, math.pi / 2), "strongbox")
    col.append(box("c", (0.6, 0.9, 0.6), (6.1, 1.0, 0)))
    # the back door onto the river stair
    parts.append(wl("B", "bdoor", 1.4, 0.08, 2.5, 4.5, 0.04, 0, M("wood_dark"), bevel=0.02, seg=1))
    for zz in (0.4, 1.3, 2.2):
        parts.append(wl("B", "bstrap", 1.2, 0.03, 0.08, 4.5, 0.09, zz, M("iron", 0.6)))
    parts.append(wl("B", "bframe", 1.7, 0.06, 2.7, 4.5, 0.02, 0, M("beam")))
    ex, ey = _wpos("B", 4.5, 0.6)
    exit_marker("back", (ex, ey, 0.0), 0.0)
    for sx in (-1, 1):
        fake_window(parts, "F", sx * 4.5, 3.8, w=0.9, h=1.1, bars=True)
    fake_window(parts, "R", 12.5, LZ + 1.4, w=1.0, h=1.2)
    lantern(parts, -2.0, 4.0, H - 0.6, 3.0)
    lantern(parts, 3.0, 8.0, H - 0.6, 3.2)
    lantern(parts, -2.0, 13.0, H - 0.6, LZ + 2.2)
    CTX["surface"] = "planks"
    post_at(5.3, CY1 - 1.1, 5.3, CY1 - 0.5)                # the clerk at his desk
    post_at(0.9, (HY0 + HY1) / 2 + 1.2, 0.0, (HY0 + HY1) / 2)   # at the winch
    post_at(2.7, 4.4, 2.7, 5.4)                            # by the tasting cask
    post_at(-3.0, 12.0, 0.0, 11.5, z=LZ)                   # a porter in the loft by the hatch
    post_at(4.0, D - 1.5, 4.5, D)                          # by the back door
    post_at(0.0, 1.5, 0.0, 4.0)                            # a watchman inside the doors
    finish_set("int_store_warehouse", parts, col)


# ------------------------------------------------------------------ THE UNDERCROFT: culverts and cellars under the Rynek
def rat(x, y, z, a, i):
    """A rat, its own mesh (`rat_<i>`) so interiors.gd can make it scurry."""
    fur = M("coal", 0.9)
    p = [blob("rbody", (0.07, 0.16, 0.06), (0, 0, 0.0), fur, subsurf=1),
         blob("rhead", (0.05, 0.07, 0.045), (0, -0.1, 0.01), fur, subsurf=1),
         cbox("rtail", (0.01, 0.2, 0.01), (0, 0.17, 0.01), M("plaster_rose", 0.7), rot=(0.2, 0, 0.3))]
    for sx in (-1, 1):
        p.append(sphere("rear", 0.012, (sx * 0.02, -0.12, 0.05), M("plaster_rose", 0.7), seg=6, rings=3))
    return keep(place(p, x, y, a, z), "rat_%d" % i)


def culvert(parts, col, x0, x1, y0, y1, spring=0.9, gaps_l=(), gaps_r=(), channel=0.9, lid=2.6, flooded=None):
    """Brick culvert along Y: walkways either side, a channel of black water down the middle, a barrel vault.
    gaps_l/gaps_r = [(y, w)] openings in the side walls (side drains, alcoves, doors); flooded = (ya, yb) where the
    walkways are gone and the water runs wall to wall."""
    W = x1 - x0
    xc = (x0 + x1) / 2
    wall_h = lid + 0.3
    for (xw, gaps) in ((x0 - 0.2, gaps_l), (x1 + 0.2, gaps_r)):
        cur = y0
        for (gy, gw) in sorted(gaps) + [(y1 + 1e3, 0.0)]:
            a, b = cur, min(y1, gy - gw / 2)
            if b - a > 0.01:
                parts.append(box("cwall", (0.4, b - a, wall_h + 0.5), (xw, (a + b) / 2, -0.5), M("brick", 0.9), bevel=0, wonk=0.02, smooth=0))
                col.append(box("c", (0.4, b - a, wall_h + 0.5), (xw, (a + b) / 2, -0.5)))
            if gy < y1:
                parts.append(box("clintel", (0.4, gw, wall_h - 1.9), (xw, gy, 1.9), M("brick", 0.9), bevel=0, smooth=0))
                col.append(box("c", (0.4, gw, wall_h - 1.9), (xw, gy, 1.9)))
            cur = gy + gw / 2
    ch0, ch1 = xc - channel / 2, xc + channel / 2
    fa, fb = flooded if flooded else (y1 + 1, y1 + 1)
    for (a, b) in ((y0, min(y1, fa)), (max(y0, fb), y1)):
        if b - a < 0.01:
            continue
        for (wa, wb) in ((x0, ch0), (ch1, x1)):
            parts.append(box("walk", (wb - wa, b - a, 0.3), ((wa + wb) / 2, (a + b) / 2, -0.3), M("floor_stone_b", 0.9), bevel=0.02, seg=1, wonk=0.01))
            SURF.setdefault("stone", []).append(box("c", (wb - wa, b - a, 0.4), ((wa + wb) / 2, (a + b) / 2, -0.4)))
            parts.append(box("kerb", (0.12, b - a, 0.06), ((wb if wa == x0 else wa) + (-0.06 if wa == x0 else 0.06), (a + b) / 2, -0.04), M("stone", 0.8)))
        parts.append(box("chbed", (channel, b - a, 0.2), (xc, (a + b) / 2, -0.6), M("coal", 0.9)))
        parts.append(box("chwater", (channel, b - a, 0.01), (xc, (a + b) / 2, -0.16), M("water", 0.02)))
        SURF.setdefault("water", []).append(box("c", (channel, b - a, 0.4), (xc, (a + b) / 2, -0.8)))
    if flooded:
        a, b = max(y0, fa), min(y1, fb)
        parts.append(box("fbed", (W, b - a, 0.2), (xc, (a + b) / 2, -0.55), M("coal", 0.9)))
        parts.append(box("fwater", (W, b - a, 0.01), (xc, (a + b) / 2, -0.1), M("water", 0.02)))
        SURF.setdefault("water", []).append(box("c", (W, b - a, 0.4), (xc, (a + b) / 2, -0.75)))
    vault(parts, W, y1 - y0, spring, "brick", y0=y0, x0=xc)
    parts.append(box("clid", (W + 0.8, y1 - y0, 0.3), (xc, (y0 + y1) / 2, lid), M("brick")))
    col.append(box("c", (W + 0.8, y1 - y0, 0.3), (xc, (y0 + y1) / 2, lid)))


def side_drain(parts, col, side, y, name, L=2.4, w=1.2):
    """A side drain off the culvert wall at y, ending under a street grate: a shaft with iron bars at the top,
    the night and a street lantern's glow above, dust in the light. Exit_<name> sits under the grate."""
    sgn = -1 if side == "L" else 1
    xa = sgn * 1.7
    xb = xa + sgn * L
    x0, x1 = min(xa, xb), max(xa, xb)
    parts.append(box("dfloor", (L, w, 0.3), ((x0 + x1) / 2, y, -0.3), M("floor_stone_b", 0.9), wonk=0.01))
    SURF.setdefault("stone", []).append(box("c", (L, w, 0.4), ((x0 + x1) / 2, y, -0.4)))
    parts.append(box("dtrickle", (L, 0.25, 0.01), ((x0 + x1) / 2, y, 0.005), M("water", 0.02)))
    for sy in (-1, 1):
        parts.append(box("dwall", (L, 0.3, 2.2), ((x0 + x1) / 2, y + sy * (w / 2 + 0.15), -0.3), M("brick", 0.9), bevel=0, smooth=0))
        col.append(box("c", (L, 0.3, 2.2), ((x0 + x1) / 2, y + sy * (w / 2 + 0.15), -0.3)))
    sx0 = xb - sgn * 0.9
    sa, sb = min(sx0, xb), max(sx0, xb)
    parts.append(box("droof", (L - 0.9, w + 0.6, 0.3), ((x0 + x1) / 2 - sgn * 0.45, y, 1.9), M("stone_dark", 0.9)))
    col.append(box("c", (L, w + 0.6, 0.3), ((x0 + x1) / 2, y, 1.9)))
    parts.append(box("dend", (0.3, w + 0.6, 6.0), (xb + sgn * 0.15, y, -0.3), M("brick", 0.9), bevel=0, smooth=0))
    col.append(box("c", (0.3, w + 0.6, 6.0), (xb + sgn * 0.15, y, -0.3)))
    SH = 5.2
    for sy in (-1, 1):
        parts.append(box("swall", (0.9, 0.3, SH - 1.9), ((sa + sb) / 2, y + sy * (w / 2 + 0.15), 1.9), M("brick", 0.9), bevel=0, smooth=0))
    parts.append(box("swall", (0.3, w + 0.6, SH - 2.2), (sa - 0.15 if sgn > 0 else sb + 0.15, y, 2.2), M("brick", 0.9), bevel=0, smooth=0))
    for k in range(6):
        parts.append(box("grate", (0.9, 0.04, 0.05), ((sa + sb) / 2, y - w / 2 + 0.1 + k * (w - 0.2) / 5, SH), M("iron", 0.45)))
    parts.append(box("gframe", (1.0, w + 0.2, 0.06), ((sa + sb) / 2, y, SH + 0.05), M("iron", 0.45)))
    parts.append(box("gsky", (1.4, w + 0.6, 0.05), ((sa + sb) / 2, y, SH + 0.5), EM("night_sky", 0.8, 0.2)))
    parts.append(sphere("gglow", 0.18, ((sa + sb) / 2 + 0.3, y + 0.2, SH + 0.45), EM("night_glow", 3.0), seg=8, rings=4))
    for k in range(4):
        parts.append(cbox("rung", (0.4, 0.03, 0.03), (xb - sgn * 0.08, y, 2.2 + k * 0.7), M("iron", 0.5)))
    lamp("shaft", ((sa + sb) / 2, y, SH - 0.8))
    fx("dust", ((sa + sb) / 2, y, 2.8))
    exit_marker(name, ((sa + sb) / 2, y, 0.0), 0.0)


def int_undercroft():
    """Under the Rynek, 1795: no sewers yet, but the medieval brick culverts that carry the gutters to the moat and
    the river, and the cellars two and three deep under the tenements, many broken through into each other.
    A cellar under the wine merchant's hatch; the culvert with its black channel and walkways; side drains up to
    the street grates; the junction chamber with its rusted grille; the smugglers' cellar (casks, cards, a hidden
    stair up into a tenement cellar); the fence's den; the alcove where bodies go, with rats; the shaft of the old
    well; the flooded stretch with a plank; the outfall to the river with a boat and a gate to the kingpin's
    passage. A few guttering lanterns and the grates' light; the rest is dark."""
    start()
    CTX.update(W=3.0, D=63.0, t=0.4, H=2.4)
    parts, col = [], []
    # ---- the entrance cellar under the hatch: brick vault, a ladder up to the hatch, the door we came through
    CTX.update(W=3.0, D=3.0, t=0.4)
    v, c = wall("F", 2.8, "brick", [(0.0, 1.1, 2.1, False)])
    parts.append(v)
    col += c
    col.append(box("c", (1.2, 0.12, 2.1), (0, -0.14, 0)))
    door_leaf(parts, 1.1, 2.1, False, -0.1)
    parts.append(box("threshold", (1.2, 0.5, 0.04), (0, 0, 0), M("stone_dark"), bevel=0.01, seg=1))
    for sx in (-1, 1):
        parts.append(box("ewall", (0.4, 3.0, 3.3), (sx * 1.7, 1.5, -0.5), M("brick", 0.9), bevel=0, smooth=0))
        col.append(box("c", (0.4, 3.0, 3.3), (sx * 1.7, 1.5, -0.5)))
    parts.append(box("efloor", (3.0, 3.0, 0.3), (0, 1.5, -0.3), M("floor_stone", 0.9), wonk=0.01))
    SURF.setdefault("stone", []).append(box("c", (3.0, 3.2, 0.4), (0, 1.5, -0.4)))
    vault(parts, 3.0, 3.0, 1.2, "brick", y0=0.0)
    parts.append(box("elid", (3.8, 3.0, 0.3), (0, 1.5, 2.8), M("brick")))
    col.append(box("c", (3.8, 3.0, 0.3), (0, 1.5, 2.8)))
    for k in range(7):
        parts.append(box("lrung", (0.5, 0.04, 0.04), (-1.2, 2.2, 0.3 + k * 0.35), M("wood", 0.8)))
    for sx in (-1, 1):
        parts.append(cbox("lrail", (0.05, 0.05, 2.7), (-1.2 + sx * 0.25, 2.25, 1.3), M("wood", 0.8), rot=(0.05, 0, 0)))
    parts.append(box("hatchlid", (0.9, 0.9, 0.06), (-1.2, 2.3, 2.62), M("wood_dark", 0.8)))
    for k in range(3):
        parts.append(box("hslit", (0.9, 0.02, 0.07), (-1.2, 2.0 + k * 0.3, 2.61), EM("night_glow", 0.8)))
    barrel(parts, 1.0, 0.8, 0.0, r=0.3, h=0.8)
    col.append(cyl("c", 0.32, 0.8, (1.0, 0.8, 0), None, verts=8))
    parts.append(box("wlbr", (0.05, 0.25, 0.05), (1.2, 0.35, 1.9), M("iron", 0.6)))
    lantern(parts, 1.2, 0.5, 1.95, 1.6)
    # ---- culvert A: the entrance cellar opens onto it
    CTX.update(W=3.0, D=63.0, t=0.4)
    culvert(parts, col, -1.5, 1.5, 3.0, 28.0, gaps_l=[(19.0, 1.2)], gaps_r=[(9.0, 1.2)])
    side_drain(parts, col, "R", 9.0, "grate_a")
    side_drain(parts, col, "L", 19.0, "grate_b")
    for k in range(4):
        fx("drip", (RNG.uniform(-1.0, 1.0), 5.0 + k * 6.0, 2.0))
    for k in range(6):
        parts.append(blob("mud", (RNG.uniform(0.3, 0.7), RNG.uniform(0.3, 0.9), 0.02), (RNG.choice((-1, 1)) * RNG.uniform(0.7, 1.2), RNG.uniform(4, 27), 0.0), M("earth", 0.9), subsurf=1, wonk=0.05))
    # ---- the junction chamber: the culverts meet, the rusted grille across the way on, doors west and east
    JY0, JY1 = 28.0, 34.0
    JW = 6.0
    for (xw, doors) in ((-JW / 2 - 0.2, [(31.0, 1.1)]), (JW / 2 + 0.2, [(31.0, 1.1)])):
        cur = JY0
        for (gy, gw) in doors + [(JY1 + 1e3, 0)]:
            a, b = cur, min(JY1, gy - gw / 2)
            parts.append(box("jwall", (0.4, b - a, 4.6), (xw, (a + b) / 2, -0.5), M("brick", 0.9), bevel=0, smooth=0))
            col.append(box("c", (0.4, b - a, 4.6), (xw, (a + b) / 2, -0.5)))
            if gy < JY1:
                parts.append(box("jlint", (0.4, gw, 2.2), (xw, gy, 1.9), M("brick", 0.9), bevel=0, smooth=0))
                col.append(box("c", (0.4, gw, 2.2), (xw, gy, 1.9)))
                for s_ in (-1, 1):
                    parts.append(box("jjamb", (0.5, 0.12, 1.95), (xw, gy + s_ * (gw / 2 + 0.06), 0), M("stone", 0.8)))
            cur = gy + gw / 2
    for (yy, sgn) in ((JY0, -1), (JY1, 1)):
        for sx in (-1, 1):
            parts.append(box("jend", (JW / 2 - 1.5, 0.4, 4.6), (sx * (1.5 + (JW / 2 - 1.5) / 2), yy + sgn * 0.2, -0.5), M("brick", 0.9), bevel=0, smooth=0))
            col.append(box("c", (JW / 2 - 1.5, 0.4, 4.6), (sx * (1.5 + (JW / 2 - 1.5) / 2), yy + sgn * 0.2, -0.5)))
        parts.append(box("jover", (3.0, 0.4, 2.0), (0, yy + sgn * 0.2, 2.1), M("brick", 0.9), bevel=0, smooth=0))
    parts.append(box("jfloor", (JW, JY1 - JY0, 0.3), (0, (JY0 + JY1) / 2, -0.3), M("floor_stone_b", 0.9), wonk=0.01))
    for (wa, wb) in ((-JW / 2, -0.45), (0.45, JW / 2)):
        SURF["stone"].append(box("c", (wb - wa, JY1 - JY0, 0.4), ((wa + wb) / 2, (JY0 + JY1) / 2, -0.4)))
    parts.append(box("jchan", (0.9, JY1 - JY0, 0.02), (0, (JY0 + JY1) / 2, -0.005), M("water", 0.02)))
    SURF["water"].append(box("c", (0.9, JY1 - JY0, 0.4), (0, (JY0 + JY1) / 2, -0.4)))
    parts.append(box("jchbed", (0.9, JY1 - JY0, 0.2), (0, (JY0 + JY1) / 2, -0.6), M("coal", 0.9)))
    vault(parts, JW, JY1 - JY0, 1.4, "brick", y0=JY0, ribs=2, rib_mat="brick_dark")
    parts.append(box("jlid", (JW + 0.8, JY1 - JY0, 0.3), (0, (JY0 + JY1) / 2, 4.5), M("brick")))
    col.append(box("c", (JW + 0.8, JY1 - JY0, 0.3), (0, (JY0 + JY1) / 2, 4.5)))
    iron = M("iron", 0.35)
    for k in range(11):
        x = -1.4 + k * 0.28
        if 0.6 < x < 1.2:
            parts.append(cbox("gbent", (0.035, 0.035, 1.9), (x + 0.12, JY1 + 0.15, 0.95), M("iron", 0.35), rot=(0, 0.35, 0)))
            continue
        parts.append(box("grille", (0.035, 0.035, 2.0), (x, JY1 + 0.1, -0.3), M("brick_dark", 0.4)))
    for zz in (0.4, 1.5):
        parts.append(box("grilleh", (3.0, 0.05, 0.05), (0, JY1 + 0.1, zz), M("brick_dark", 0.4)))
    col.append(box("c", (2.0, 0.1, 2.0), (-0.5, JY1 + 0.1, 0)))
    lantern(parts, -1.8, 30.0, 4.5, 2.0)
    # ---- the smugglers' cellar, west: casks, cards, a lantern, the hidden stair up into a tenement cellar
    SX0, SX1, SY0, SY1 = -9.2, -3.4, 29.0, 33.4
    sw = SX1 - SX0
    for (sz, loc) in (((sw, 0.4, 3.8), ((SX0 + SX1) / 2, SY0 - 0.2, -0.5)), ((sw, 0.4, 3.8), ((SX0 + SX1) / 2, SY1 + 0.2, -0.5))):
        parts.append(box("swall", sz, loc, M("brick", 0.9), bevel=0, smooth=0))
        col.append(box("c", sz, loc))
    for (a, b) in ((SY0, 30.8), (31.8, SY1)):
        parts.append(box("swallw", (0.4, b - a, 3.8), (SX0 - 0.2, (a + b) / 2, -0.5), M("brick", 0.9), bevel=0, smooth=0))
        col.append(box("c", (0.4, b - a, 3.8), (SX0 - 0.2, (a + b) / 2, -0.5)))
    parts.append(box("slint", (0.4, 1.0, 1.4), (SX0 - 0.2, 31.3, 1.9), M("brick", 0.9)))
    col.append(box("c", (0.4, 1.0, 1.4), (SX0 - 0.2, 31.3, 1.9)))
    floor_region(parts, "flags", SX0, SX1, SY0, SY1)
    parts.append(box("sfloor", (sw, SY1 - SY0, 0.3), ((SX0 + SX1) / 2, (SY0 + SY1) / 2, -0.3), M("floor_stone_b")))
    parts.append(box("sceil", (sw + 0.4, SY1 - SY0 + 0.4, 0.3), ((SX0 + SX1) / 2, (SY0 + SY1) / 2, 2.4), M("brick_vault", 0.9)))
    for k in range(4):
        parts.append(box("sbeam", (0.2, SY1 - SY0, 0.22), (SX0 + 0.8 + k * 1.4, (SY0 + SY1) / 2, 2.18), M("beam"), bevel=0.02, seg=1))
    col.append(box("c", (sw + 0.4, SY1 - SY0 + 0.4, 0.3), ((SX0 + SX1) / 2, (SY0 + SY1) / 2, 2.4)))
    for k in range(3):
        cask(parts, col, -8.4 + k * 1.1, SY1 - 0.65, 0.0, r=0.42, L=1.0, rot=math.pi, cradle=True, mark=True)
    sc = [cyl("cask", 0.4 * 0.86, 0.5, (0, -0.25, 0.58), M("wood", 0.8), verts=14, r2=0.4, rot=(-math.pi / 2, 0, 0), center=True),
          cyl("cask", 0.4, 0.5, (0, 0.25, 0.58), M("wood", 0.8), verts=14, r2=0.4 * 0.86, rot=(-math.pi / 2, 0, 0), center=True),
          cyl("head", 0.33, 0.02, (0, -0.51, 0.58), M("wood_dark"), verts=14, rot=(math.pi / 2, 0, 0), center=True),
          cyl("tap", 0.025, 0.14, (0, -0.57, 0.38), M("brass", 0.35), verts=6, rot=(math.pi / 2, 0, 0), center=True)]
    for yy in (-0.4, 0.0, 0.4):
        sc.append(cyl("hoop", 0.41, 0.05, (0, yy, 0.58), M("iron", 0.6), verts=14, rot=(math.pi / 2, 0, 0), center=True))
    for yy in (-0.3, 0.3):
        sc.append(box("cradle", (0.75, 0.12, 0.2), (0, yy, 0), M("wood_dark"), bevel=0.02, seg=1))
    keep(place(sc, -4.3, SY1 - 0.8, math.pi * 0.9), "smugglers_cask")
    col.append(box("c", (0.9, 1.1, 1.0), (-4.3, SY1 - 0.8, 0)))
    TX, TY = -6.2, 30.6
    table(parts, col, TX, TY, L=1.2, w=0.8, h=0.76, along_y=False, trestle=False)
    for k in range(9):
        parts.append(box("card", (0.06, 0.09, 0.004), (TX + RNG.uniform(-0.4, 0.4), TY + RNG.uniform(-0.25, 0.25), 0.765), M("paper", 0.6), rot=(0, 0, RNG.uniform(0, 3))))
    for k in range(5):
        parts.append(cyl("coin", 0.012, 0.006, (TX + RNG.uniform(-0.3, 0.3), TY + RNG.uniform(-0.2, 0.2), 0.765), MET("gold", 0.3), verts=8))
    tankard(parts, TX + 0.4, TY + 0.2, 0.76)
    parts.append(taper_box("tlcap", (0.22, 0.22, 0.1), (TX - 0.35, TY + 0.1, 1.08), M("iron", 0.6), top=0.3))
    parts.append(box("tlglass", (0.16, 0.16, 0.26), (TX - 0.35, TY + 0.1, 0.82), EM("lamp_glass", 5.0)))
    parts.append(box("tlbase", (0.2, 0.2, 0.04), (TX - 0.35, TY + 0.1, 0.78), M("iron", 0.6)))
    lamp("lantern", (TX - 0.35, TY + 0.1, 1.0))
    for (sx, sy) in ((TX - 0.4, TY - 0.6), (TX + 0.5, TY - 0.6), (TX, TY + 0.65)):
        stool(parts, sx, sy)
    for (bx, bz) in ((-8.6, 0.0), (-8.6, 0.45), (-8.6, 0.9), (-7.9, 0.0)):
        parts.append(box("bale", (0.6, 0.5, 0.45), (bx, SY0 + 0.4, bz), M("canvas", 0.9), bevel=0.04, seg=1))
    col.append(box("c", (1.3, 0.6, 1.35), (-8.3, SY0 + 0.4, 0)))
    # the hidden door: a plank door standing open in the west wall, a stair going up into the dark
    parts.append(cbox("hdoor", (0.06, 0.95, 1.85), (SX0 + 0.35, 30.5, 0.93), M("wood_dark", 0.8), rot=(0, 0, -1.1)))
    for i in range(6):
        parts.append(box("hstep", (0.3, 0.9, 0.2 * (i + 1)), (SX0 - 0.55 - i * 0.3, 31.3, 0), M("stone", 0.8)))
    parts.append(box("hvoid", (0.05, 0.9, 1.8), (SX0 - 2.5, 31.3, 1.2), M("coal", 0.9)))
    exit_marker("cellar", (SX0 + 0.5, 31.3, 0.0), math.pi / 2)
    # ---- the fence's den, east: stolen goods, a desk with scales and a candle, a pallet behind a curtain
    FX0, FX1, FY0, FY1 = 3.4, 9.2, 29.0, 33.4
    fw = FX1 - FX0
    for (sz, loc) in (((fw, 0.4, 3.8), ((FX0 + FX1) / 2, FY0 - 0.2, -0.5)), ((fw, 0.4, 3.8), ((FX0 + FX1) / 2, FY1 + 0.2, -0.5)),
                      ((0.4, FY1 - FY0 + 0.8, 3.8), (FX1 + 0.2, (FY0 + FY1) / 2, -0.5))):
        parts.append(box("fwall", sz, loc, M("brick", 0.9), bevel=0, smooth=0))
        col.append(box("c", sz, loc))
    floor_region(parts, "planks", FX0, FX1, FY0, FY1)
    parts.append(box("ffloor", (fw, FY1 - FY0, 0.3), ((FX0 + FX1) / 2, (FY0 + FY1) / 2, -0.3), M("floor_stone_b")))
    parts.append(box("fceil", (fw + 0.4, FY1 - FY0 + 0.4, 0.3), ((FX0 + FX1) / 2, (FY0 + FY1) / 2, 2.4), M("brick_vault", 0.9)))
    col.append(box("c", (fw + 0.4, FY1 - FY0 + 0.4, 0.3), ((FX0 + FX1) / 2, (FY0 + FY1) / 2, 2.4)))
    parts.append(box("fcurtain", (0.1, 0.5, 1.9), (3.7, 31.9, 0.05), M("sukmana", 0.9), bevel=0.03, seg=1, wonk=0.03))
    DX, DY = 6.0, 30.0
    parts.append(box("fdesk", (1.4, 0.7, 0.78), (DX, DY, 0), M("wood_dark"), bevel=0.02, seg=1))
    col.append(box("c", (1.4, 0.7, 0.8), (DX, DY, 0)))
    scales(parts, DX - 0.3, DY, 0.78, s=0.7)
    for k in range(4):
        parts.append(torus("ring", 0.013, 0.004, (DX + 0.2 + k * 0.05, DY - 0.1, 0.785), MET("gold", 0.25), seg=8, mseg=4))
    parts.append(box("fledger", (0.26, 0.2, 0.04), (DX + 0.35, DY + 0.1, 0.78), M("leather_b", 0.8)))
    candle(parts, DX + 0.55, DY - 0.15, 0.78, h=0.1)
    lamp("candle", (DX + 0.4, DY - 0.3, 1.3))
    chair(parts, DX, DY + 0.65, math.pi)
    for k in range(4):
        parts.append(cyl("csticks", 0.05, 0.4 + k * 0.05, (FX1 - 0.4, FY0 + 0.4 + k * 0.25, 0.0), MET("gold", 0.3), verts=8, r2=0.03))
    parts.append(box("fclock", (0.3, 0.2, 0.4), (FX1 - 0.5, FY0 + 1.6, 0.6), MET("gold", 0.3), bevel=0.03, seg=1))
    parts.append(box("fcrate", (0.6, 0.6, 0.6), (FX1 - 0.5, FY0 + 1.6, 0.0), M("wood", 0.8), bevel=0.02, seg=1))
    parts.append(cyl("carpet", 0.18, 2.0, (FX0 + 2.5, FY1 - 0.3, 0.18), M("crimson", 0.9), verts=10, rot=(0, math.pi / 2, 0), center=True))
    for k in range(3):
        parts.append(box("fframe", (0.9, 0.06, 0.7), (FX1 - 0.3, FY1 - 1.4 + k * 0.1, 0.0), MET("gold", 0.35), rot=(0.15, 0, math.pi / 2)))
    parts.append(box("fchest", (0.9, 0.5, 0.5), (FX0 + 1.0, FY1 - 0.4, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(blob("fpallet", (1.6, 0.7, 0.15), (FX0 + 1.4, FY1 - 1.1, 0), M("straw_bed", 0.95), subsurf=1))
    col.append(box("c", (2.4, 0.5, 0.6), (FX0 + 1.5, FY1 - 0.35, 0)))
    col.append(box("c", (0.8, 2.2, 1.0), (FX1 - 0.4, FY0 + 1.1, 0)))
    # ---- culvert B beyond the grille: the body-dump alcove, the old well, a third grate, the flooded stretch
    culvert(parts, col, -1.5, 1.5, JY1 + 0.2, 58.0, gaps_l=[(38.5, 1.6), (50.0, 1.2)], gaps_r=[(44.0, 1.2)], flooded=(52.0, 56.0))
    AY0, AY1 = 37.7, 39.3
    parts.append(box("afloor", (1.6, AY1 - AY0, 0.3), (-2.5, (AY0 + AY1) / 2, -0.4), M("earth", 0.9)))
    SURF.setdefault("mud", []).append(box("c", (1.6, AY1 - AY0, 0.4), (-2.5, (AY0 + AY1) / 2, -0.5)))
    for (sz, loc) in (((1.6, 0.3, 2.3), (-2.5, AY0 - 0.15, -0.4)), ((1.6, 0.3, 2.3), (-2.5, AY1 + 0.15, -0.4)), ((0.3, AY1 - AY0 + 0.6, 2.3), (-3.45, (AY0 + AY1) / 2, -0.4))):
        parts.append(box("awall", sz, loc, M("brick", 0.9), bevel=0, smooth=0))
        col.append(box("c", sz, loc))
    parts.append(box("aroof", (1.9, AY1 - AY0 + 0.6, 0.3), (-2.5, (AY0 + AY1) / 2, 1.9), M("stone_dark", 0.9)))
    col.append(box("c", (1.9, AY1 - AY0 + 0.6, 0.3), (-2.5, (AY0 + AY1) / 2, 1.9)))
    parts.append(blob("bundle", (0.5, 1.4, 0.3), (-2.7, 38.5, -0.1), M("sack", 0.95), subsurf=1, wonk=0.04))
    parts.append(blob("bundle2", (0.4, 0.9, 0.25), (-2.2, 38.2, -0.1), M("linen", 0.95), subsurf=1, wonk=0.04))
    for k in range(6):
        parts.append(cyl("bone", 0.015, RNG.uniform(0.15, 0.35), (-2.4 + RNG.uniform(-0.5, 0.5), 38.5 + RNG.uniform(-0.6, 0.6), -0.08), M("bone", 0.6), verts=5, rot=(math.pi / 2, 0, RNG.uniform(0, 3)), center=True))
    parts.append(blob("askull", (0.13, 0.16, 0.12), (-3.0, 39.0, -0.1), M("bone", 0.6), subsurf=2))
    for i, (rx, ry, ra) in enumerate(((-2.0, 38.0, 0.4), (-2.9, 37.9, 2.0), (-2.3, 39.0, 4.0), (-1.1, 40.2, 1.2), (0.9, 36.4, 3.3))):
        rat(rx, ry, 0.02 if rx > -1.5 else -0.07, ra, i)
    # the old well: a round shaft rising to the square, iron rungs, a bucket on its rope, black water in a ring
    WX, WY = 2.9, 44.0
    parts.append(box("wpass", (1.0, 1.2, 0.3), (2.0, WY, -0.3), M("floor_stone_b", 0.9)))
    SURF["stone"].append(box("c", (1.0, 1.2, 0.4), (2.0, WY, -0.4)))
    for sy in (-1, 1):
        parts.append(box("wpwall", (1.0, 0.3, 2.2), (2.0, WY + sy * 0.75, -0.3), M("brick", 0.9), bevel=0, smooth=0))
        col.append(box("c", (1.0, 0.3, 2.2), (2.0, WY + sy * 0.75, -0.3)))
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=1.0, depth=13.0, location=(WX + 0.6, WY, 6.0), end_fill_type="NOTHING")
    ws = bpy.context.object
    ws.name = "wshaft"
    ws.data.materials.append(M("brick", 0.9))
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bm = bmesh.new()
    bm.from_mesh(ws.data)
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(ws.data)
    bm.free()
    bpy.ops.object.shade_smooth()
    parts.append(ws)
    for k in range(8):
        a = math.tau * k / 8
        col.append(box("c", (0.5, 0.5, 13.0), (WX + 0.6 + 1.2 * math.cos(a), WY + 1.2 * math.sin(a), -0.5)))
    parts.append(cyl("wfloor", 1.0, 0.3, (WX + 0.6, WY, -0.3), M("floor_stone_b", 0.9), verts=16))
    SURF["stone"].append(cyl("c", 1.0, 0.4, (WX + 0.6, WY, -0.4), None, verts=8))
    parts.append(torus("wring", 0.55, 0.12, (WX + 0.8, WY, 0.05), M("stone", 0.8), seg=16, mseg=6))
    parts.append(cyl("wwater", 0.5, 0.01, (WX + 0.8, WY, 0.0), M("water", 0.02), verts=16))
    for k in range(14):
        parts.append(cbox("wrung", (0.04, 0.35, 0.03), (WX + 1.5, WY, 0.5 + k * 0.6), M("iron", 0.45)))
    parts.append(cyl("wrope", 0.012, 11.0, (WX + 0.8, WY, 1.0), M("straw", 0.9), verts=4))
    parts.append(cyl("wbucket", 0.14, 0.24, (WX + 0.8, WY, 0.76), M("wood", 0.8), verts=10, r2=0.16))
    parts.append(cyl("wtop", 1.1, 0.05, (WX + 0.6, WY, 12.4), EM("night_sky", 0.7, 0.2), verts=16))
    lamp("shaft", (WX + 0.6, WY, 4.0))
    fx("dust", (WX + 0.6, WY, 3.0))
    exit_marker("well", (WX + 0.3, WY, 0.0), -math.pi / 2)
    side_drain(parts, col, "L", 50.0, "grate_c")
    parts.append(box("wlbr2", (0.25, 0.05, 0.05), (1.45, 45.6, 1.75), M("iron", 0.6)))
    lantern(parts, 1.3, 45.6, 1.8, 1.45)
    parts.append(box("plank", (0.32, 5.0, 0.05), (1.0, 54.0, 0.0), M("plank_b", 0.9), rot=(0.0, 0.03, 0.0), wonk=0.02))
    SURF.setdefault("planks", []).append(box("c", (0.4, 5.0, 0.35), (1.0, 54.0, -0.3)))
    for k in range(3):
        fx("drip", (RNG.uniform(-1.0, 1.0), 40.0 + k * 6.0, 2.0))
    # ---- the outfall: a ledge, the river through the arch, the boat, a gate into the kingpin's passage
    OY0, OY1 = 58.0, 63.0
    OW = 5.0
    for sx in (-1, 1):
        parts.append(box("owall", (0.4, OY1 - OY0, 4.2), (sx * (OW / 2 + 0.2), (OY0 + OY1) / 2, -0.8), M("brick", 0.9), bevel=0, smooth=0))
        col.append(box("c", (0.4, OY1 - OY0, 4.2), (sx * (OW / 2 + 0.2), (OY0 + OY1) / 2, -0.8)))
        parts.append(box("ofront", (OW / 2 - 1.5, 0.4, 4.2), (sx * (1.5 + (OW / 2 - 1.5) / 2), OY0 - 0.2, -0.8), M("brick", 0.9), bevel=0, smooth=0))
        col.append(box("c", (OW / 2 - 1.5, 0.4, 4.2), (sx * (1.5 + (OW / 2 - 1.5) / 2), OY0 - 0.2, -0.8)))
    parts.append(box("oledge", (OW, 1.3, 0.3), (0, OY0 + 0.65, -0.3), M("floor_stone", 0.9)))
    SURF["stone"].append(box("c", (OW, 1.3, 0.4), (0, OY0 + 0.65, -0.4)))
    parts.append(box("owater", (OW, OY1 - OY0 - 1.3, 0.02), (0, (OY0 + 1.3 + OY1) / 2, -0.3), M("water", 0.02)))
    col.append(box("c", (OW, OY1 - OY0 - 1.3, 0.3), (0, (OY0 + 1.3 + OY1) / 2, -1.2)))
    vault(parts, OW, OY1 - OY0, 1.2, "brick", y0=OY0, ribs=2, rib_mat="brick_dark")
    parts.append(box("olid", (OW + 0.8, OY1 - OY0, 0.3), (0, (OY0 + OY1) / 2, 3.8), M("brick")))
    col.append(box("c", (OW + 0.8, OY1 - OY0, 0.3), (0, (OY0 + OY1) / 2, 3.8)))
    parts.append(box("oend", (OW + 0.8, 0.4, 4.6), (0, OY1 + 0.2, -0.8), M("brick", 0.9)))
    col.append(box("c", (OW + 0.8, 0.4, 4.6), (0, OY1 + 0.2, -0.8)))
    parts.append(arch("onight", 2.8, 2.6, 0.05, (0, OY1 - 0.03, -0.3), EM("night_sky", 0.6, 0.2), bevel=0))
    parts.append(sphere("olamp", 0.05, (0.8, OY1 - 0.07, 0.3), EM("night_glow", 9.0), seg=6, rings=3))
    for k in range(10):
        parts.append(box("ogrille", (0.03, 0.05, 1.0), (-1.3 + k * 0.29, OY1 - 0.1, 1.5), M("brick_dark", 0.4)))
    BY_ = OY0 + 3.0
    hull = taper_box("hull", (1.0, 2.4, 0.42), (0.0, BY_, -0.45), M("wood_dark"), top=1.25, bevel=0.05, wonk=0.02)
    edit_verts(hull, lambda co: setattr(co, "x", co.x * (1.0 - 0.7 * max(0.0, abs(co.y - BY_) - 0.7) / 0.5)))
    parts.append(hull)
    parts.append(box("hinside", (0.7, 1.7, 0.03), (0.0, BY_, -0.08), M("plank_b", 0.9)))
    parts.append(cbox("oar", (0.04, 1.9, 0.04), (0.45, BY_, 0.1), M("wood", 0.8), rot=(0, 0, 0.1)))
    parts.append(cyl("bollard", 0.08, 0.35, (-0.8, OY0 + 0.5, 0.0), M("wood_dark"), verts=8))
    parts.append(cbox("mooring", (0.02, 1.6, 0.02), (-0.4, OY0 + 1.3, 0.1), M("straw", 0.9), rot=(0.1, 0, 0.3)))
    col.append(box("c", (1.1, 2.5, 0.4), (0.0, BY_, -0.45)))
    exit_marker("boat", (0.0, BY_, 0.0), 0.0)
    # the gate in the east wall: the kingpin's passage comes in here
    for k in range(6):
        parts.append(box("kgate", (0.04, 0.04, 2.0), (OW / 2 - 0.05, OY0 + 0.2 + k * 0.18, 0.0), M("iron", 0.35)))
    parts.append(box("kgateh", (0.05, 1.0, 0.05), (OW / 2 - 0.05, OY0 + 0.65, 1.2), M("iron", 0.35)))
    exit_marker("kingpin", (OW / 2 - 0.6, OY0 + 0.65, 0.0), -math.pi / 2)
    lantern(parts, -1.5, OY0 + 0.6, 3.6, 1.9)
    CTX["surface"] = "stone"
    post_at(DX, DY + 0.65, DX, DY)                     # the fence at his desk
    post_at(TX - 0.4, TY - 0.6, TX, TY)                # smuggler at cards
    post_at(TX + 0.5, TY - 0.6, TX, TY)                # the other smuggler
    post_at(-2.2, 31.0, -3.4, 31.0)                    # the guard dog at the smugglers' door
    post_at(0.9, 26.0, 0.9, 3.0)                       # a lookout on the walkway, watching back up the culvert
    finish_set("int_undercroft", parts, col)


SETS = {"int_stair": int_stair, "int_tavern": int_tavern, "int_shop": int_shop, "int_workshop": int_workshop,
        "int_church": int_church, "int_salon": int_salon,
        "int_shop_baker": int_shop_baker, "int_shop_shoemaker": int_shop_shoemaker, "int_shop_goldsmith": int_shop_goldsmith,
        "int_shop_apothecary": int_shop_apothecary, "int_shop_tailor": int_shop_tailor, "int_shop_cloth": int_shop_cloth,
        "int_shop_chandler": int_shop_chandler, "int_workshop_locksmith": int_workshop_locksmith,
        "int_workshop_cooper": int_workshop_cooper, "int_workshop_forge": int_workshop_forge,
        "int_tavern_beerhall": int_tavern_beerhall, "int_tavern_kawiarnia": int_tavern_kawiarnia, "int_tavern_inn": int_tavern_inn,
        "int_cellar_wine": int_cellar_wine, "int_salon_brothel": int_salon_brothel,
        "int_flat_garret": int_flat_garret, "int_flat_burgher": int_flat_burgher, "int_flat_scholar": int_flat_scholar,
        "int_guard_post": int_guard_post, "int_chapel_synagogue": int_chapel_synagogue, "int_chapel_uniate": int_chapel_uniate,
        "int_undercroft": int_undercroft, "int_house_kingpin": int_house_kingpin, "int_bath_lazna": int_bath_lazna, "int_store_warehouse": int_store_warehouse}

if __name__ == "__main__":
    want = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else list(SETS)
    for n in want:
        ROOM[0] = n
        SETS[n]()
    print("[interiors] %d rooms: %s" % (len(MANIFEST), ", ".join("%s %d" % (k, v[0]) for k, v in MANIFEST.items())))
    print("[interiors] done")
