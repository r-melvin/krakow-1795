"""Interior sets for Krakow 1795: reusable rooms that sit behind a door. Same Fable-ish pass as build_assets.py.

Run:  blender -b --python assets/blender/build_interiors.py [-- int_tavern int_shop ...]
Writes one .glb per set into assets/models/ (int_tavern, int_shop, int_workshop, int_church, int_salon, int_flat, int_stair).

Conventions (on top of build_assets.py)
- Every room: floor top at z=0, walls, ceiling. The entrance wall is centred on y=0 with a door opening at x=0;
  its outer face looks down -Y (Godot +Z), the room extends toward +Y (Godot -Z). So the set's origin is the
  outside of its front door, and a player standing at Blender (0, 1.8, 0) is just inside, facing into the room.
- `<set>-colonly` holds the collision: floor, walls, ceiling, big furniture, stair ramps (prisms).
- Light sources are exported as empties named `lamp_<kind>_<nn>` (kind: lantern, fire, candle, window, chandelier);
  the Godot side hangs an OmniLight3D on each. Their meshes (lantern glass, flames, coals) are emissive.
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
})

CTX = {}          # current room: W, D, t (wall thickness)
LAMPS = []


def start():
    ba.reset()
    LAMPS.clear()
    CTX.clear()


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


def ceiling_beams(parts, W, D, H, step=1.3, summer=True, drop=0.28):
    n = int(D / step)
    for i in range(n):
        y = (D / n) * (i + 0.5)
        parts.append(box("cbeam", (W, 0.22, drop), (0, y, H - drop), M("beam"), bevel=0.04, seg=1, wonk=0.03))
    if summer:
        parts.append(box("summer", (0.34, D, drop + 0.08), (0, D / 2, H - drop - 0.08), M("beam"), bevel=0.05, seg=1, wonk=0.03))


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


def fake_window(parts, side, u, z, w=0.9, h=1.3, glass="moon_glass", strength=0.6, arched=False, sill=True, n=0.0):
    """Window read from inside: deep reveal frame, glowing panes, mullions and sill against the wall face."""
    fr = M("wood_dark")
    g = EM(glass, strength, 0.2)
    if arched:
        parts.append(warch(side, "wframe", w + 0.24, h + 0.12, 0.10, u, n + 0.03, z - 0.06, fr, bevel=0.02))
        parts.append(warch(side, "wglass", w, h, 0.04, u, n + 0.08, z, g, bevel=0))
    else:
        parts.append(wl(side, "wframe", w + 0.24, 0.10, h + 0.24, u, n + 0.03, z - 0.12, fr, bevel=0.02, seg=1, wonk=0.01))
        parts.append(wl(side, "wglass", w, 0.04, h, u, n + 0.08, z, g))
    parts.append(wl(side, "wmull", 0.05, 0.04, h - (w / 2 if arched else 0), u, n + 0.11, z, fr))
    parts.append(wl(side, "wmull", w, 0.04, 0.05, u, n + 0.11, z + h * 0.45, fr))
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
    """Iron lantern hanging on a chain from the ceiling at H, glass centre at z."""
    iron = M("iron", 0.6)
    parts.append(cyl("chain", 0.012, H - z - 0.3, (x, y, z + 0.3), iron, verts=6))
    parts.append(taper_box("lcap", (0.30, 0.30, 0.14), (x, y, z + 0.22), iron, top=0.3))
    parts.append(box("lglass", (0.20, 0.20, 0.30), (x, y, z - 0.10), EM("lamp_glass", 6.0)))
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box("lpost", (0.03, 0.03, 0.34), (x + sx * 0.11, y + sy * 0.11, z - 0.12), iron))
    parts.append(box("lbase", (0.28, 0.28, 0.05), (x, y, z - 0.16), iron))
    lamp(kind, (x, y, z))


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


def finish_set(name, parts, col):
    visual = join(parts, name)
    n = tris(visual)
    export(name, visual, join(col, "col"))
    print("[interiors] %-13s tris=%d lamps=%d%s" % (name, n, len(LAMPS), "  WARNING >20k" if n > 20000 else ""))


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
            fake_window(parts, side, y, 4.8, w=1.2, h=3.8, arched=True, strength=0.9, sill=False)
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
        chair(parts, TX + 0.85 * math.cos(a), TY + 0.85 * math.sin(a), a + math.pi / 2, fancy=True)
    # harpsichord in the back-left corner, settees by the fire and along the back wall
    harpsichord(parts, col, -3.0, 5.2, 0.0)
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
    finish_set("int_salon", parts, col)


# ------------------------------------------------------------------ INT_FLAT (izba, 5 x 5)
def int_flat():
    start()
    W, D, H = 5.0, 5.0, 2.8
    parts, col = shell(W, D, H, "limewash")
    plank_floor(parts, -W / 2, W / 2, 0, D, w=0.28)
    ceiling_beams(parts, W, D, H, step=1.2, summer=False, drop=0.2)
    skirting(parts, "LRB", 0.7, "plaster_blue")
    # bed in the back-left corner, head against the back wall
    BX, BY = -1.6, 3.9
    wd = M("wood_dark")
    parts.append(box("bframe", (1.4, 2.0, 0.35), (BX, BY, 0.1), M("wood", 0.8), bevel=0.03, seg=1, wonk=0.02))
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box("bpost", (0.1, 0.1, 1.2 if sy > 0 else 0.7), (BX + sx * 0.65, BY + sy * 0.95, 0), wd, bevel=0.02, seg=1))
    parts.append(box("bhead", (1.3, 0.06, 0.7), (BX, BY + 0.95, 0.4), wd, bevel=0.02, seg=1))
    parts.append(blob("mattress", (1.3, 1.9, 0.22), (BX, BY, 0.43), M("linen", 0.9), subsurf=1, bevel=0.04))
    parts.append(blob("pillow", (0.9, 0.4, 0.16), (BX, BY + 0.7, 0.62), M("linen", 0.9), subsurf=1, bevel=0.03))
    parts.append(box("blanket", (1.36, 1.2, 0.08), (BX, BY - 0.35, 0.6), M("crimson", 0.9), bevel=0.04, seg=2, wonk=0.03))
    col.append(box("c", (1.4, 2.0, 0.7), (BX, BY, 0)))
    parts.append(wl("B", "cross", 0.05, 0.04, 0.45, BX, 0.02, 1.4, wd))
    parts.append(wl("B", "cross", 0.28, 0.04, 0.05, BX, 0.02, 1.7, wd))
    # chest at the foot of the bed
    parts.append(box("chest", (1.0, 0.5, 0.45), (BX, 2.5, 0), M("wood", 0.8), bevel=0.03, seg=1, wonk=0.02))
    parts.append(box("chestlid", (1.04, 0.54, 0.1), (BX, 2.5, 0.45), M("wood_dark"), bevel=0.03, seg=1, wonk=0.01))
    for sx in (-1, 1):
        parts.append(box("band", (0.06, 0.56, 0.56), (BX + sx * 0.3, 2.5, 0), M("iron", 0.6)))
    col.append(box("c", (1.04, 0.54, 0.55), (BX, 2.5, 0)))
    # table and chair, a jug and bread
    TX, TY = 1.3, 3.3
    table(parts, col, TX, TY, L=0.7, w=1.0, h=0.75, trestle=False)
    chair(parts, TX, TY - 0.6, math.pi)
    chair(parts, TX + 0.8, TY + 0.1, -math.pi / 2)
    parts.append(cyl("jug", 0.07, 0.22, (TX - 0.2, TY + 0.1, 0.75), M("jar", 0.5), verts=10, r2=0.05))
    parts.append(blob("bread", (0.22, 0.14, 0.09), (TX + 0.15, TY, 0.75), M("cloth_ochre", 0.8), subsurf=1))
    plate(parts, TX + 0.1, TY - 0.15, 0.75)
    candle(parts, TX - 0.3, TY - 0.15, 0.75)
    # small tiled stove in the front-left corner, with a lit fire door
    SX, SY = -1.9, 0.9
    tile = M("stove_tile", 0.3)
    trim = M("stove_trim", 0.5)
    parts.append(box("sbase", (0.9, 0.8, 0.2), (SX, SY, 0), M("brick_dark"), bevel=0.02, seg=1))
    parts.append(box("sbody", (0.8, 0.7, 1.0), (SX, SY, 0.2), tile, bevel=0.03, seg=1, wonk=0.01))
    parts.append(box("sband", (0.86, 0.76, 0.08), (SX, SY, 1.2), trim, bevel=0.02, seg=1))
    parts.append(box("stop", (0.64, 0.56, 0.5), (SX, SY, 1.28), tile, bevel=0.03, seg=1, wonk=0.01))
    parts.append(box("scap", (0.72, 0.64, 0.08), (SX, SY, 1.78), trim, bevel=0.02, seg=1))
    for k in range(1, 4):
        parts.append(box("sgrout", (0.82, 0.72, 0.012), (SX, SY, 0.2 + k * 0.25), trim))
    parts.append(box("sdoor", (0.26, 0.03, 0.2), (SX + 0.4, SY, 0.35), EM("fire", 4.0), rot=(0, 0, math.pi / 2)))
    parts.append(box("sdoorf", (0.32, 0.02, 0.26), (SX + 0.41, SY, 0.32), M("iron", 0.6), rot=(0, 0, math.pi / 2)))
    lamp("fire", (SX + 0.6, SY, 0.45))
    col.append(box("c", (0.9, 0.8, 1.86), (SX, SY, 0)))
    parts.append(cyl("pipe", 0.07, H - 1.86, (SX, SY + 0.2, 1.86), M("iron", 0.6), verts=8))
    # window on the right wall with warm light and a candle on the sill
    WY = 3.6
    fake_window(parts, "R", WY, 1.0, w=0.8, h=1.0, glass="warm_glass", strength=2.5)
    cx, cy = _wpos("R", WY + 0.2, 0.14)
    candle(parts, cx, cy, 0.93, h=0.12)
    lamp("window", _wpos("R", WY, 0.4) + (1.4,))
    # a shelf with pots, a coat on a peg
    parts.append(wl("B", "shelf", 1.2, 0.25, 0.04, 1.3, 0.13, 1.6, M("wood", 0.8)))
    for k in range(4):
        px, py = _wpos("B", 0.85 + k * 0.3, 0.13)
        parts.append(cyl("pot", 0.07, 0.14, (px, py, 1.64), M(("jar", "brick_dark", "pewter", "stove_trim")[k], 0.5), verts=8, r2=0.06))
    parts.append(wl("F", "peg", 0.04, 0.12, 0.04, 1.3, 0.06, 1.7, wd))
    parts.append(wl("F", "coat", 0.4, 0.12, 0.9, 1.3, 0.1, 0.85, M("brown_coat", 0.9), bevel=0.04, seg=1, wonk=0.03))
    finish_set("int_flat", parts, col)


SETS = {"int_stair": int_stair, "int_tavern": int_tavern, "int_shop": int_shop, "int_workshop": int_workshop,
        "int_church": int_church, "int_salon": int_salon, "int_flat": int_flat}

if __name__ == "__main__":
    want = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else list(SETS)
    for n in want:
        SETS[n]()
    print("[interiors] done")
