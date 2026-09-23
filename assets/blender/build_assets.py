"""Stylised assets for Krakow 1795 (Rynek Glowny, winter 1795/96). Fable (2004) flavour:
rounded bevelled forms, walls that lean, roofs that sag and flare, chunky stone, big hands and boots.

Run:  blender -b --python assets/blender/build_assets.py
Writes one .glb per asset into assets/models/.

Conventions
- Metres. Blender Z up. glTF export maps Blender (x, y, z) -> Godot (x, z, -y).
- Buildings: front face at Blender -Y (Godot +Z). Origin at base centre.
- Figures: front at Blender +Y (Godot -Z), matching a Node3D's forward. Origin at feet.
- Collision meshes are named <asset>-col; Godot turns them into StaticBody3D colliders on import.
- Blender 5.x: transform_apply also bakes location, so every primitive ends up with world-space vertices and a
  zero origin. Every helper that edits vertices relies on that.
"""
import bpy
import bmesh
import math
import os
import random
import sys
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "models")
os.makedirs(OUT, exist_ok=True)
RNG = random.Random(1795)

# ------------------------------------------------------------------ palette (warm, painterly)
PAL = {
    "plaster_ochre": (0.90, 0.64, 0.30), "plaster_rose": (0.86, 0.52, 0.42), "plaster_cream": (0.94, 0.84, 0.58),
    "plaster_sage": (0.58, 0.68, 0.44), "plaster_blue": (0.50, 0.64, 0.78), "plaster_white": (0.94, 0.91, 0.84),
    "stone": (0.70, 0.65, 0.55), "stone_dark": (0.46, 0.43, 0.38), "stone_pale": (0.80, 0.76, 0.66),
    "brick": (0.58, 0.28, 0.19), "brick_dark": (0.42, 0.19, 0.14),
    "tile": (0.56, 0.26, 0.16), "tile_dark": (0.38, 0.17, 0.12), "tile_moss": (0.46, 0.34, 0.18),
    "copper": (0.26, 0.50, 0.44), "lead": (0.32, 0.33, 0.37), "gold": (0.95, 0.74, 0.30),
    "glass": (0.12, 0.15, 0.22), "glass_warm": (0.55, 0.38, 0.16),
    "wood": (0.46, 0.31, 0.18), "wood_dark": (0.26, 0.17, 0.10), "timber": (0.30, 0.20, 0.12),
    "iron": (0.10, 0.10, 0.11), "canvas": (0.76, 0.66, 0.50), "canvas_stripe": (0.58, 0.22, 0.20),
    "snow": (0.90, 0.92, 0.96), "skin": (0.86, 0.66, 0.54), "hair": (0.24, 0.16, 0.10), "eye": (0.05, 0.05, 0.06),
    "white_coat": (0.92, 0.92, 0.94), "facing_red": (0.66, 0.12, 0.14), "black": (0.07, 0.07, 0.08),
    "crimson": (0.58, 0.10, 0.16), "zupan_gold": (0.86, 0.68, 0.30), "sukmana": (0.84, 0.80, 0.70),
    "red_cap": (0.76, 0.12, 0.12), "green_coat": (0.16, 0.32, 0.22), "brown_coat": (0.38, 0.25, 0.14),
    "navy": (0.14, 0.18, 0.34), "feather": (0.10, 0.48, 0.36), "shutter": (0.30, 0.42, 0.36),
}
_mats = {}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mats.clear()


def M(key, rough=0.85, emit=None, emit_strength=0.0):
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new(key)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*PAL[key], 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emit_strength
    _mats[key] = m
    return m


# ------------------------------------------------------------------ finishing: the "Fable" pass
def finish(o, bevel=0.06, seg=2, subsurf=0, wonk=0.0, smooth=40.0, keep_base=True):
    """Wonk the corners, bevel the edges, optionally subdivide, then smooth by angle."""
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    if wonk > 0:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.x += RNG.uniform(-wonk, wonk)
            v.co.y += RNG.uniform(-wonk, wonk)
            if not keep_base or v.co.z > zmin + 0.01:
                v.co.z += RNG.uniform(-wonk, wonk) * 0.5
        bm.to_mesh(o.data)
        bm.free()
    if bevel > 0:
        d = o.dimensions
        w = min(bevel, max(0.005, min(d.x, d.y, d.z) * 0.3))
        m = o.modifiers.new("bevel", "BEVEL")
        m.width = w
        m.segments = seg
        m.limit_method = "ANGLE"
        m.angle_limit = math.radians(50)
        bpy.ops.object.modifier_apply(modifier="bevel")
    if subsurf > 0:
        m = o.modifiers.new("sub", "SUBSURF")
        m.levels = subsurf
        bpy.ops.object.modifier_apply(modifier="sub")
    if smooth:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(smooth))
    return o


def shear(o, kx, ky, z0=0.0):
    """Lean a whole object: x += (z-z0)*kx, y += (z-z0)*ky. The base at z0 stays put."""
    bm = bmesh.new()
    bm.from_mesh(o.data)
    for v in bm.verts:
        v.co.x += (v.co.z - z0) * kx
        v.co.y += (v.co.z - z0) * ky
    bm.to_mesh(o.data)
    bm.free()
    return o


def edit_verts(o, fn):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    for v in bm.verts:
        fn(v.co)
    bm.to_mesh(o.data)
    bm.free()
    return o


# ------------------------------------------------------------------ primitives (world-space verts, zero origin)
def _finish_prim(o, name, mat):
    o.name = name
    if mat:
        o.data.materials.append(mat)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o


def box(name, size, loc, mat=None, rot=(0, 0, 0), **fin):
    """loc = base centre; the box sits on loc.z."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0], loc[1], loc[2] + size[2] / 2), rotation=rot)
    o = bpy.context.object
    o.scale = size
    o = _finish_prim(o, name, mat)
    return finish(o, **fin) if fin else o


def cbox(name, size, center, mat=None, rot=(0, 0, 0), **fin):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center, rotation=rot)
    o = bpy.context.object
    o.scale = size
    o = _finish_prim(o, name, mat)
    return finish(o, **fin) if fin else o


def taper_box(name, size, loc, mat=None, top=0.7, **fin):
    """Box whose top face is scaled by `top` about its centre (buttresses, chimneys, stocks)."""
    o = box(name, size, loc, mat)
    zt = loc[2] + size[2]
    cx, cy = loc[0], loc[1]
    def f(co):
        if co.z > zt - 1e-4:
            co.x = cx + (co.x - cx) * top
            co.y = cy + (co.y - cy) * top
    edit_verts(o, f)
    return finish(o, **fin) if fin else o


def cyl(name, r, h, loc, mat=None, verts=24, rot=(0, 0, 0), r2=None, center=False, **fin):
    """Vertical cylinder. Base at loc.z unless center=True. r2 = top radius for a cone/frustum."""
    c = loc if center else (loc[0], loc[1], loc[2] + h / 2)
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=c, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=h, location=c, rotation=rot)
    o = _finish_prim(bpy.context.object, name, mat)
    return finish(o, **fin) if fin else o


def sphere(name, r, center, mat=None, seg=20, rings=12, zscale=1.0, **fin):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=r, location=center)
    o = bpy.context.object
    o.scale.z = zscale
    o = _finish_prim(o, name, mat)
    fin.setdefault("bevel", 0)
    return finish(o, **fin)


def torus(name, R, r, center, mat=None, rot=(0, 0, 0), **fin):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=24, minor_segments=10, location=center, rotation=rot)
    o = _finish_prim(bpy.context.object, name, mat)
    fin.setdefault("bevel", 0)
    return finish(o, **fin)


def blob(name, size, loc, mat=None, **fin):
    """Rounded lump: cube with subsurf. Heads, boots, hair, mascarons."""
    fin.setdefault("subsurf", 2)
    fin.setdefault("bevel", 0)
    return box(name, size, loc, mat, **fin)


def roof(name, L, W, H, loc, mat, sag=0.25, flare=0.30, cuts=6, top_w=0.0, along_x=True, **fin):
    """Sagging, flaring roof solid. Ridge along X (or Y). loc = base centre at eaves level.
    flare: how far the mid-slope sits below the straight chord (0 = straight, 0.3 = pagoda-ish sweep).
    top_w: width of a flat ridge (for mansard lower slopes)."""
    bm = bmesh.new()
    slices = []
    for i in range(cuts + 1):
        t = -1 + 2 * i / cuts
        u = t if along_x else t
        x = loc[0] + (L / 2) * u
        hr = H - sag * (1 - t * t)
        prof = []
        half = W / 2
        # eave, mid, ridge (one or two points), mid, eave
        prof.append((-half, 0.0))
        ym = -half + (half - top_w / 2) * 0.45
        zm = hr * 0.45 - flare * hr * 0.45
        prof.append((ym, zm))
        if top_w > 0:
            prof.append((-top_w / 2, hr))
            prof.append((top_w / 2, hr))
        else:
            prof.append((0.0, hr))
        prof.append((-ym, zm))
        prof.append((half, 0.0))
        vs = []
        for (py, pz) in prof:
            if along_x:
                vs.append(bm.verts.new((x, loc[1] + py, loc[2] + pz)))
            else:
                vs.append(bm.verts.new((loc[0] + py, loc[1] + (L / 2) * u, loc[2] + pz)))
        slices.append(vs)
    n = len(slices[0])
    for i in range(cuts):
        a, b = slices[i], slices[i + 1]
        for j in range(n - 1):
            bm.faces.new((a[j], a[j + 1], b[j + 1], b[j]))
        bm.faces.new((a[0], b[0], b[n - 1], a[n - 1]))       # underside
    bm.faces.new(list(reversed(slices[0])))
    bm.faces.new(slices[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    fin.setdefault("bevel", 0.05)
    fin.setdefault("smooth", 35)
    return finish(o, **fin)


def arch(name, w, h, depth, loc, mat, rot_z=0.0, verts=24, **fin):
    """Round-topped slab, base centre at loc, depth along Y (rotated about the base point by rot_z)."""
    parts = [box(name + "_b", (w, depth, h - w / 2), loc, mat),
             cyl(name + "_t", w / 2, depth, (loc[0], loc[1], loc[2] + h - w / 2), mat, verts=verts, rot=(math.pi / 2, 0, 0), center=True)]
    o = join(parts, name)
    if rot_z:
        c, s = math.cos(rot_z), math.sin(rot_z)
        def f(co):
            dx, dy = co.x - loc[0], co.y - loc[1]
            co.x = loc[0] + dx * c - dy * s
            co.y = loc[1] + dx * s + dy * c
        edit_verts(o, f)
    fin.setdefault("bevel", 0.04)
    return finish(o, **fin)


def join(objs, name):
    objs = [o for o in objs if o is not None]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    j = bpy.context.object
    j.name = name
    return j


def export(name, visual, col=None):
    if col is not None:
        col.name = name + "-colonly"
        col.parent = visual
        col.display_type = "WIRE"
    visual.name = name
    path = os.path.join(OUT, name + ".glb")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True)
    print("[assets] wrote", os.path.relpath(path, ROOT), "tris~", sum(len(p.polygons) for p in [visual.data]))


# ------------------------------------------------------------------ architectural details
def window(parts, x, y_face, z, w=1.1, h=1.8, arched=False, shutters=False, warm=False):
    """Window on a wall facing -Y, outer face at y_face. Chunky wonky wooden frame, dark or lit glass, mullions."""
    fr = M("wood_dark")
    t = 0.14
    parts.append(box("jamb", (t, 0.16, h + 0.1), (x - w / 2 - t / 2, y_face - 0.08, z - 0.05), fr, bevel=0.03, wonk=0.015))
    parts.append(box("jamb", (t, 0.16, h + 0.1), (x + w / 2 + t / 2, y_face - 0.08, z - 0.05), fr, bevel=0.03, wonk=0.015))
    if arched:
        parts.append(arch("head", w + 2 * t, (w + 2 * t) / 2 + 0.1, 0.16, (x, y_face - 0.08, z + h - (w + 2 * t) / 2 - 0.1 + 0.05), fr, bevel=0.03))
        parts.append(arch("glass", w, w / 2, 0.08, (x, y_face - 0.10, z + h - w / 2), M("glass_warm" if warm else "glass", 0.3), bevel=0))
    else:
        parts.append(box("head", (w + 2 * t, 0.18, t), (x, y_face - 0.09, z + h), fr, bevel=0.03, wonk=0.015))
    parts.append(box("glass", (w, 0.08, h), (x, y_face - 0.10, z), M("glass_warm" if warm else "glass", 0.3), bevel=0))
    parts.append(box("mull", (0.07, 0.05, h - 0.02), (x, y_face - 0.15, z), M("wood_dark"), bevel=0.02))
    parts.append(box("mull", (w, 0.05, 0.07), (x, y_face - 0.15, z + h * 0.6), M("wood_dark"), bevel=0.02))
    parts.append(box("sill", (w + 0.5, 0.30, 0.14), (x, y_face - 0.15, z - 0.18), M("stone"), bevel=0.04, wonk=0.02))
    if shutters:
        for sx in (-1, 1):
            parts.append(box("shutter", (0.45, 0.08, h - 0.1), (x + sx * (w / 2 + t + 0.25), y_face - 0.05, z), M("shutter"), bevel=0.03, wonk=0.02))


def cornice(parts, w, d, z, t=0.28, proud=0.25, mat=None, wonk=0.03):
    parts.append(box("cornice", (w + proud * 2, d + proud * 2, t), (0, 0, z), mat or M("stone"), bevel=0.06, wonk=wonk))


def quoins(parts, width, depth, z0, z1, face, cx=0.0):
    """Alternating stone blocks up the front corners."""
    z = z0
    i = 0
    while z < z1 - 0.3:
        for sx in (-1, 1):
            w = 0.9 if i % 2 == 0 else 0.6
            parts.append(box("quoin", (w, 0.30, 0.5), (cx + sx * (width / 2 - w / 2 + 0.05), face - 0.10, z), M("stone_pale"), bevel=0.05, wonk=0.02))
        z += 0.56
        i += 1


def door(parts, x, face, w=2.2, h=3.2):
    parts.append(arch("portal", w + 0.7, h + 0.4, 0.42, (x, face - 0.30, 0), M("stone"), bevel=0.06))
    parts.append(arch("door", w, h, 0.16, (x, face - 0.36, 0), M("wood_dark"), bevel=0.03))
    for i in range(1, 4):
        parts.append(box("plank", (0.04, 0.04, h - 0.5), (x - w / 2 + w * i / 4, face - 0.40, 0.1), M("black"), bevel=0))
    for zz in (0.8, h - 1.0):
        parts.append(box("strap", (w - 0.3, 0.05, 0.14), (x, face - 0.41, zz), M("iron", 0.6), bevel=0.02))
        for sx in (-1, 1):
            parts.append(sphere("stud", 0.06, (x + sx * (w / 2 - 0.25), face - 0.44, zz + 0.07), M("iron", 0.6), seg=8, rings=6))
    parts.append(torus("ring", 0.14, 0.03, (x + 0.55, face - 0.45, 1.4), M("iron", 0.6), rot=(math.pi / 2, 0, 0)))
    parts.append(box("keystone", (0.5, 0.46, 0.7), (x, face - 0.32, h + 0.2), M("stone_pale"), bevel=0.05, wonk=0.02))
    parts.append(box("step", (w + 1.0, 0.7, 0.18), (x, face - 0.45, 0), M("stone_dark"), bevel=0.05, wonk=0.02))


def chimney(parts, x, y, z, h=2.6):
    lean_x, lean_y = RNG.uniform(-0.08, 0.08), RNG.uniform(-0.05, 0.05)
    c = taper_box("chimney", (0.9, 0.9, h), (x, y, z), M("brick"), top=0.85, bevel=0.06, wonk=0.03)
    shear(c, lean_x, lean_y, z0=z)
    parts.append(c)
    tx, ty = x + h * lean_x, y + h * lean_y
    parts.append(box("cap", (1.1, 1.1, 0.22), (tx, ty, z + h - 0.02), M("stone_dark"), bevel=0.05, wonk=0.02))
    parts.append(cyl("pot", 0.22, 0.6, (tx, ty, z + h + 0.18), M("brick_dark"), verts=12, r2=0.18, bevel=0.03))
    parts.append(box("snow", (0.9, 0.9, 0.1), (tx, ty, z + h + 0.20), M("snow"), bevel=0.04))


# ------------------------------------------------------------------ TENEMENT (kamienica)
def tenement(name, width, storeys, roof_kind, colour, bays=3, pilasters=False, arched_windows=False, shutters=False):
    reset()
    D = 8.0
    GF, FL = 4.2, 3.3
    body_h = GF + FL * (storeys - 1)
    plaster = M(colour)
    stone = M("stone")
    parts = []
    face = -D / 2
    jetty = 0.22

    # storeys as separate wonky masses: ground floor stone, upper floors plaster stepping slightly outward
    parts.append(box("gf", (width, D, GF), (0, 0, 0), M("stone_pale"), bevel=0.10, wonk=0.06))
    for i in range(1, int((GF - 0.4) / 0.62)):
        parts.append(box("course", (width + 0.06, 0.05, 0.05), (0, face - 0.03, i * 0.62), M("stone_dark"), bevel=0))
    for s in range(1, storeys):
        z0 = GF + FL * (s - 1)
        parts.append(box("floor", (width + jetty * s * 0.4, D + jetty * s, FL), (0, -jetty * s * 0.5, z0), plaster, bevel=0.12, wonk=0.07))
        parts.append(box("beam", (width + jetty * s * 0.4 + 0.3, 0.26, 0.26), (0, face - jetty * s - 0.10, z0 - 0.1), M("timber"), bevel=0.05, wonk=0.02))
    quoins(parts, width, D, GF, body_h, face - jetty * (storeys - 1) - 0.02)

    bay_w = width / bays
    xs = [-width / 2 + bay_w * (i + 0.5) for i in range(bays)]
    px = xs[bays // 2] if bays % 2 else xs[0]
    door(parts, px, face)
    for x in xs:
        if abs(x - px) < 0.1:
            continue
        window(parts, x, face, 1.4, w=1.2, h=1.7, arched=True, warm=RNG.random() < 0.4)
    for s in range(1, storeys):
        z0 = GF + FL * (s - 1)
        yf = face - jetty * s
        for x in xs:
            window(parts, x, yf, z0 + 0.8, arched=arched_windows and s == 1, shutters=shutters, warm=RNG.random() < 0.3)
        if pilasters:
            for i in range(bays + 1):
                px_ = -width / 2 + bay_w * i
                px_ = max(min(px_, width / 2 - 0.3), -width / 2 + 0.3)
                parts.append(box("pil", (0.5, 0.16, FL - 0.4), (px_, yf - 0.08, z0 + 0.15), M("plaster_white"), bevel=0.04, wonk=0.02))

    yfront = face - jetty * (storeys - 1)
    cornice(parts, width + jetty * (storeys - 1) * 0.4, D + jetty * (storeys - 1), body_h - 0.05, t=0.45, proud=0.40)
    top = body_h + 0.4
    Wr = D + jetty * (storeys - 1) + 1.2

    if roof_kind == "gable":
        parts.append(roof("roof", width + 0.9, Wr, 4.6, (0, -jetty * (storeys - 1) * 0.5, top), M("tile"), sag=0.35, flare=0.30))
        for x in xs[:: max(1, bays - 1)]:
            parts.append(box("dormer", (1.3, 1.6, 1.4), (x, yfront + 1.3, top + 0.9), plaster, bevel=0.06, wonk=0.03))
            parts.append(roof("dormer_r", (1.8), 1.7, 0.9, (x, yfront + 1.3, top + 2.3), M("tile_dark"), sag=0.05, flare=0.2, cuts=3, along_x=False))
            parts.append(box("dormer_w", (0.7, 0.08, 0.8), (x, yfront + 0.5, top + 1.2), M("glass_warm", 0.3), bevel=0))
            parts.append(box("dormer_f", (0.9, 0.10, 1.0), (x, yfront + 0.48, top + 1.1), M("wood_dark"), bevel=0.02))
        chimney(parts, width * 0.3, 1.2, top + 2.0)
        roof_top = top + 4.8
    elif roof_kind == "attyka":
        parts.append(box("attic_wall", (width + 0.3, D + jetty * (storeys - 1) + 0.2, 2.3), (0, -jetty * (storeys - 1) * 0.5, top - 0.4), plaster, bevel=0.10, wonk=0.04))
        for x in xs:
            parts.append(arch("blind", bay_w * 0.55, 1.5, 0.14, (x, yfront - 0.10, top + 0.1), M("plaster_white"), bevel=0.03))
        n = max(2, int(width / 2.2))
        for i in range(n + 1):
            x = -width / 2 + (width / n) * i
            parts.append(box("pin", (0.5, 0.5, 0.9), (x, yfront + 0.25, top + 1.8), stone, bevel=0.06, wonk=0.02))
            parts.append(cyl("pin_top", 0.32, 0.7, (x, yfront + 0.25, top + 2.7), stone, verts=8, r2=0.08, bevel=0.03))
            parts.append(sphere("pin_ball", 0.20, (x, yfront + 0.25, top + 3.5), M("gold", 0.35), seg=12, rings=8))
        for i in range(n):
            x = -width / 2 + (width / n) * (i + 0.5)
            parts.append(cyl("cren", (width / n) * 0.42, 0.42, (x, yfront + 0.25, top + 1.8), stone, verts=20, rot=(math.pi / 2, 0, 0), center=True, bevel=0.03))
        parts.append(roof("lowroof", width, D - 1.5, 1.4, (0, 0.6, top + 1.7), M("tile_dark"), sag=0.1, flare=0.1))
        chimney(parts, -width * 0.25, 1.5, top + 1.5, h=2.2)
        roof_top = top + 3.7
    else:  # mansard
        parts.append(roof("mansard_lo", width + 0.9, Wr, 2.8, (0, -jetty * (storeys - 1) * 0.5, top), M("tile"), sag=0.15, flare=-0.10, top_w=Wr * 0.5))
        parts.append(roof("mansard_hi", width + 0.9, Wr * 0.5, 2.2, (0, -jetty * (storeys - 1) * 0.5, top + 2.8), M("tile_dark"), sag=0.25, flare=0.2))
        for x in xs:
            # dormers punch out through the lower slope
            parts.append(box("dormer", (1.2, 1.9, 1.5), (x, yfront + 0.9, top + 0.35), plaster, bevel=0.06, wonk=0.03))
            parts.append(box("dormer_w", (0.65, 0.08, 0.85), (x, yfront - 0.09, top + 0.65), M("glass_warm", 0.3), bevel=0))
            parts.append(box("dormer_f", (0.9, 0.12, 1.05), (x, yfront - 0.06, top + 0.55), M("wood_dark"), bevel=0.02))
            parts.append(roof("dormer_r", 1.6, 2.1, 0.7, (x, yfront + 0.9, top + 1.85), M("lead"), sag=0.05, flare=0.2, cuts=3, along_x=False))
        chimney(parts, -width * 0.3, 1.0, top + 2.6, h=2.4)
        roof_top = top + 4.9

    parts.append(box("snow_c", (width + 1.0, D + 1.0, 0.12), (0, -jetty * (storeys - 1) * 0.5, body_h + 0.4), M("snow"), bevel=0.05, wonk=0.03))

    visual = join(parts, name)
    lean_x, lean_y = RNG.uniform(-0.025, 0.025), RNG.uniform(-0.02, 0.005)
    shear(visual, lean_x, lean_y)
    col = box("col", (width + 0.2, D + jetty * (storeys - 1), roof_top), (0, -jetty * (storeys - 1) * 0.5, 0))
    shear(col, lean_x, lean_y)
    export(name, visual, col)


# ------------------------------------------------------------------ SUKIENNICE (Cloth Hall, Renaissance state)
def sukiennice():
    reset()
    L, W, H = 34.0, 9.0, 8.0
    gap = 3.2
    stone = M("stone")
    plaster = M("plaster_cream")
    parts, col = [], []
    half = (L - gap) / 2
    for sx in (-1, 1):
        cx = sx * (gap / 2 + half / 2)
        parts.append(box("hall", (half, W, H), (cx, 0, 0), plaster, bevel=0.18, wonk=0.05))
        col.append(box("c", (half, W, H), (cx, 0, 0)))
        n = int(half / 3.4)
        for i in range(n):
            x = cx - half / 2 + half / n * (i + 0.5)
            for sy in (-1, 1):
                yf = sy * W / 2
                parts.append(arch("winf", 1.9, 4.0, 0.22, (x, yf - sy * 0.06, 2.8), stone, bevel=0.04))
                parts.append(arch("win", 1.4, 3.6, 0.14, (x, yf - sy * 0.14, 3.0), M("glass_warm" if RNG.random() < 0.5 else "glass", 0.3), bevel=0))
    parts.append(box("gap_roof", (gap + 0.6, W, 2.2), (0, 0, H - 2.2), plaster, bevel=0.1))
    for sy in (-1, 1):
        parts.append(arch("gap_arch", gap + 0.5, 6.4, 0.5, (0, sy * (W / 2 - 0.05), 0), stone, bevel=0.06))
        parts.append(arch("gap_void", gap - 0.4, 5.9, 0.6, (0, sy * (W / 2 - 0.05), 0), M("glass", 0.6), bevel=0))
    col.append(box("c", (gap + 0.6, W, 2.2), (0, 0, H - 2.2)))

    cornice(parts, L, W, H - 0.1, t=0.4, proud=0.35)
    A0 = H + 0.3
    parts.append(box("attic", (L + 0.4, W + 0.4, 2.6), (0, 0, A0), plaster, bevel=0.1, wonk=0.03))
    n = 15
    step = L / n
    for i in range(n + 1):
        x = -L / 2 + step * i
        for sy in (-1, 1):
            y = sy * (W / 2 + 0.25)
            parts.append(box("pin", (0.55, 0.55, 1.6), (x, y, A0 + 2.2), stone, bevel=0.06, wonk=0.02))
            parts.append(cyl("pin_top", 0.36, 0.8, (x, y, A0 + 3.8), stone, verts=8, r2=0.08, bevel=0.03))
            parts.append(sphere("ball", 0.22, (x, y, A0 + 4.7), M("gold", 0.35), seg=12, rings=8))
    for i in range(n):
        x = -L / 2 + step * (i + 0.5)
        for sy in (-1, 1):
            y = sy * (W / 2 + 0.25)
            parts.append(cyl("cren", step * 0.42, 0.5, (x, y, A0 + 2.6), stone, verts=20, rot=(math.pi / 2, 0, 0), center=True, bevel=0.03))
            parts.append(blob("mascaron", (0.5, 0.35, 0.6), (x, y - sy * 0.18, A0 + 1.3), M("stone_dark")))
    parts.append(roof("roof", L - 0.5, W - 1.2, 2.2, (0, 0, A0 + 2.4), M("tile_dark"), sag=0.2, flare=0.1))

    for sx in (-1, 1):
        x0 = sx * (L / 2 + 1.5)
        for j in range(4):
            y = -W / 2 + (W / 3) * j
            parts.append(cyl("colm", 0.40, 5.0, (x0 + sx * 1.2, y, 0), stone, verts=16, r2=0.33, bevel=0.03))
            parts.append(box("colcap", (1.0, 1.0, 0.35), (x0 + sx * 1.2, y, 5.0), stone, bevel=0.06, wonk=0.02))
            parts.append(box("colbase", (0.9, 0.9, 0.3), (x0 + sx * 1.2, y, 0), stone, bevel=0.05))
            col.append(box("c", (0.7, 0.7, 5.0), (x0 + sx * 1.2, y, 0)))
        parts.append(box("logroof", (3.4, W + 0.5, 0.8), (x0, 0, 5.35), stone, bevel=0.08, wonk=0.02))
        parts.append(box("logbal", (3.4, W + 0.5, 0.9), (x0, 0, 6.15), plaster, bevel=0.08, wonk=0.02))
        for j in range(3):
            y = -W / 2 + (W / 3) * (j + 0.5)
            parts.append(arch("logarch", W / 3 - 0.9, 2.0, 3.4, (x0, y, 3.3), M("glass", 0.5), rot_z=math.pi / 2, bevel=0))
        col.append(box("c", (3.4, W + 0.5, 1.7), (x0, 0, 5.35)))

    for sy in (-1, 1):
        for i in range(-2, 3):
            if i == 0:
                continue
            x = i * 6.0 + (1.5 if i < 0 else -1.5)
            y = sy * (W / 2 + 1.0)
            parts.append(box("kram", (3.0, 1.9, 2.3), (x, y, 0), M("wood"), bevel=0.06, wonk=0.05))
            parts.append(roof("kram_roof", 3.5, 2.4, 0.9, (x, y, 2.3), M("wood_dark"), sag=0.08, flare=0.2, cuts=3))
            parts.append(box("kram_shut", (2.4, 0.10, 1.2), (x, y + sy * 1.0, 0.9), M("wood_dark"), bevel=0.03, wonk=0.02))
            col.append(box("c", (3.0, 1.9, 2.3), (x, y, 0)))

    parts.append(box("snow", (L + 0.8, W + 0.8, 0.12), (0, 0, H + 0.3), M("snow"), bevel=0.05, wonk=0.03))
    visual = join(parts, "sukiennice")
    export("sukiennice", visual, join(col, "col"))


# ------------------------------------------------------------------ ST MARY'S (Kosciol Mariacki)
def st_marys():
    reset()
    brick = M("brick")
    bdark = M("brick_dark")
    stone = M("stone")
    parts, col = [], []
    NW, NL, NH = 14.0, 30.0, 18.0
    parts.append(box("nave", (NW, NL, NH), (0, 2, 0), brick, bevel=0.2, wonk=0.05))
    col.append(box("c", (NW, NL, NH), (0, 2, 0)))
    for sx in (-1, 1):
        parts.append(box("aisle", (3.0, NL - 2, NH * 0.6), (sx * (NW / 2 + 1.5), 2, 0), brick, bevel=0.15, wonk=0.04))
        col.append(box("c", (3.0, NL - 2, NH * 0.6), (sx * (NW / 2 + 1.5), 2, 0)))
        parts.append(roof("aisle_roof", NL - 2, 3.6, 2.2, (sx * (NW / 2 + 1.5), 2, NH * 0.6), M("tile"), sag=0.1, flare=0.1, along_x=False, top_w=0.0))
        for j in range(6):
            y = -NL / 2 + 4 + (NL - 2) / 5 * j
            parts.append(taper_box("buttress", (1.4, 1.2, NH * 0.62), (sx * (NW / 2 + 3.5), y, 0), bdark, top=0.55, bevel=0.06, wonk=0.03))
            col.append(box("c", (1.4, 1.2, NH * 0.62), (sx * (NW / 2 + 3.5), y, 0)))
        for j in range(5):
            y = -NL / 2 + 4 + (NL - 2) / 5 * (j + 0.5)
            parts.append(arch("cw", 1.6, 5.5, 0.25, (sx * (NW / 2 + 0.05), y, NH * 0.6 + 1.2), M("glass", 0.3), rot_z=math.pi / 2, bevel=0))
    parts.append(roof("roof", NL, NW + 0.8, 9.5, (0, 2, NH), M("tile_dark"), sag=0.4, flare=0.25, along_x=False))
    parts.append(cyl("apse", NW / 2 - 1, NH - 3, (0, NL / 2 + 2, 0), brick, verts=10, bevel=0.1))
    col.append(cyl("c", NW / 2 - 1, NH - 3, (0, NL / 2 + 2, 0), None, verts=8))
    parts.append(cyl("apse_roof", NW / 2 - 0.8, 5, (0, NL / 2 + 2, NH - 3), M("tile_dark"), verts=10, r2=0.2, bevel=0.03))

    front = -NL / 2 + 2
    x = -NW / 2 + 1.5
    parts.append(taper_box("tn", (6.2, 6.2, 30.0), (x, front - 1.0, 0), brick, top=0.92, bevel=0.15, wonk=0.04))
    col.append(box("c", (6.2, 6.2, 30.0), (x, front - 1.0, 0)))
    parts.append(cyl("tn_oct", 3.5, 7.0, (x, front - 1.0, 30.0), brick, verts=8, bevel=0.08))
    for k in range(8):
        a = math.tau * k / 8
        parts.append(box("tn_pin", (0.55, 0.55, 2.0), (x + 3.3 * math.cos(a), front - 1.0 + 3.3 * math.sin(a), 36.0), stone, bevel=0.05))
        parts.append(cyl("tn_pintop", 0.4, 1.2, (x + 3.3 * math.cos(a), front - 1.0 + 3.3 * math.sin(a), 38.0), stone, verts=8, r2=0.05, bevel=0.03))
    parts.append(cyl("tn_spire", 3.1, 13.5, (x, front - 1.0, 37.0), M("lead", 0.5), verts=16, r2=0.06, bevel=0.03))
    parts.append(torus("tn_crown", 2.5, 0.28, (x, front - 1.0, 40.8), M("gold", 0.35)))
    for k in range(8):
        a = math.tau * k / 8
        parts.append(cyl("tn_crownpt", 0.22, 1.1, (x + 2.4 * math.cos(a), front - 1.0 + 2.4 * math.sin(a), 40.9), M("gold", 0.35), verts=6, r2=0.03, bevel=0))
    for k in range(4):
        a = math.tau * k / 4 + math.pi / 4
        parts.append(cyl("tn_turret", 0.7, 4.5, (x + 3.6 * math.cos(a), front - 1.0 + 3.6 * math.sin(a), 34.5), M("lead", 0.5), verts=8, r2=0.03, bevel=0))
    for zz in (8, 16, 24):
        parts.append(arch("tn_w", 1.5, 4.2, 0.25, (x, front - 4.05, zz), M("glass", 0.3), bevel=0))
        parts.append(arch("tn_wf", 1.9, 4.5, 0.2, (x, front - 4.0, zz - 0.15), stone, bevel=0.03))
    x = NW / 2 - 1.5
    parts.append(taper_box("ts", (6.2, 6.2, 25.0), (x, front - 1.0, 0), brick, top=0.92, bevel=0.15, wonk=0.04))
    col.append(box("c", (6.2, 6.2, 25.0), (x, front - 1.0, 0)))
    parts.append(cyl("ts_drum", 3.3, 2.6, (x, front - 1.0, 25.0), stone, verts=16, bevel=0.06))
    parts.append(sphere("ts_dome", 3.5, (x, front - 1.0, 27.6), M("copper", 0.5), seg=24, rings=14, zscale=0.95))
    parts.append(cyl("ts_lantern", 1.0, 2.6, (x, front - 1.0, 30.6), stone, verts=10, bevel=0.04))
    parts.append(cyl("ts_lantop", 1.3, 1.8, (x, front - 1.0, 33.2), M("copper", 0.5), verts=10, r2=0.05, bevel=0.03))
    parts.append(cyl("ts_clock", 1.3, 0.25, (x, front - 4.05, 20.0), M("plaster_white"), verts=24, rot=(math.pi / 2, 0, 0), center=True, bevel=0.03))
    for zz in (8, 14):
        parts.append(arch("ts_w", 1.5, 4.2, 0.25, (x, front - 4.05, zz), M("glass", 0.3), bevel=0))
        parts.append(arch("ts_wf", 1.9, 4.5, 0.2, (x, front - 4.0, zz - 0.15), stone, bevel=0.03))
    parts.append(arch("portal", 4.4, 8.0, 0.7, (0, front - 0.35, 0), stone, bevel=0.08))
    parts.append(arch("portal2", 3.6, 7.4, 0.5, (0, front - 0.45, 0), M("stone_dark"), bevel=0.05))
    parts.append(arch("door", 2.9, 6.8, 0.3, (0, front - 0.55, 0), M("wood_dark"), bevel=0.03))
    parts.append(torus("rose", 2.4, 0.35, (0, front - 0.2, 12.5), stone, rot=(math.pi / 2, 0, 0)))
    parts.append(cyl("rose_g", 2.2, 0.3, (0, front - 0.15, 12.5), M("glass_warm", 0.3), verts=24, rot=(math.pi / 2, 0, 0), center=True, bevel=0))
    parts.append(roof("gable", 1.2, NW + 0.8, 9.5, (0, front + 0.6, NH), bdark, sag=0.0, flare=0.25, cuts=2, along_x=False))
    parts.append(box("snow", (NW + 0.8, NL, 0.12), (0, 2, NH + 0.02), M("snow"), bevel=0.05))
    visual = join(parts, "st_marys")
    export("st_marys", visual, join(col, "col"))


# ------------------------------------------------------------------ TOWN HALL (Ratusz, before 1820)
def town_hall():
    reset()
    parts, col = [], []
    brick = M("brick")
    stone = M("stone")
    parts.append(box("hall", (16.0, 8.0, 9.0), (-9.0, 0, 0), M("plaster_white"), bevel=0.15, wonk=0.06))
    col.append(box("c", (16.0, 8.0, 9.0), (-9.0, 0, 0)))
    parts.append(roof("hall_roof", 16.8, 9.0, 4.4, (-9.0, 0, 9.0), M("tile"), sag=0.3, flare=0.25))
    quoins(parts, 16.0, 8.0, 0.3, 9.0, -4.0, cx=-9.0)
    for i in range(4):
        x = -15.5 + 4.0 * i
        window(parts, x, -4.0, 1.5, w=1.2, h=2.0, arched=True, warm=True)
        window(parts, x, -4.0, 5.5, w=1.2, h=2.0, shutters=True)
    parts.append(taper_box("tower", (7.0, 7.0, 24.0), (0, 0, 0), brick, top=0.9, bevel=0.15, wonk=0.04))
    col.append(box("c", (7.0, 7.0, 24.0), (0, 0, 0)))
    parts.append(box("tower_base", (7.8, 7.8, 3.0), (0, 0, 0), stone, bevel=0.1, wonk=0.03))
    for zz in (6, 12, 18):
        parts.append(arch("tw", 1.2, 3.0, 0.25, (0, -3.6, zz), M("glass", 0.3), bevel=0))
        parts.append(arch("twf", 1.6, 3.3, 0.2, (0, -3.55, zz - 0.15), stone, bevel=0.03))
    for k in range(4):
        a = math.tau * k / 4
        cx, cy = 3.5 * math.sin(a), -3.5 * math.cos(a)
        parts.append(cyl("clock", 1.5, 0.3, (cx, cy, 20.5), M("plaster_white"), verts=24, rot=(math.pi / 2, 0, a), center=True, bevel=0.03))
        parts.append(torus("clockrim", 1.5, 0.12, (cx, cy, 20.5), M("gold", 0.4), rot=(math.pi / 2, 0, a)))
    door(parts, 0, -3.5, w=1.8, h=3.4)
    parts.append(cyl("drum", 3.7, 3.0, (0, 0, 24.0), stone, verts=8, bevel=0.08))
    parts.append(sphere("onion", 3.7, (0, 0, 28.6), M("copper", 0.5), seg=24, rings=14, zscale=1.15))
    parts.append(cyl("onion_neck", 1.4, 2.2, (0, 0, 31.9), stone, verts=10, bevel=0.05))
    parts.append(sphere("onion2", 1.7, (0, 0, 34.7), M("copper", 0.5), seg=20, rings=12, zscale=1.2))
    parts.append(cyl("spike", 0.18, 3.0, (0, 0, 36.3), M("gold", 0.4), verts=8, r2=0.02, bevel=0))
    parts.append(sphere("ball", 0.5, (0, 0, 37.8), M("gold", 0.4), seg=12, rings=8))
    parts.append(box("snow", (7.4, 7.4, 0.1), (0, 0, 24.0), M("snow"), bevel=0.05))
    visual = join(parts, "town_hall")
    export("town_hall", visual, join(col, "col"))


# ------------------------------------------------------------------ ST ADALBERT'S
def st_adalbert():
    reset()
    parts, col = [], []
    parts.append(box("body", (7.0, 7.0, 5.0), (0, 0, 0), M("plaster_white"), bevel=0.2, wonk=0.08))
    col.append(box("c", (7.0, 7.0, 5.0), (0, 0, 0)))
    parts.append(box("base", (7.6, 7.6, 1.0), (0, 0, 0), M("stone_dark"), bevel=0.1, wonk=0.04))
    parts.append(cyl("drum", 3.6, 2.2, (0, 0, 5.0), M("plaster_white"), verts=16, bevel=0.08))
    parts.append(sphere("dome", 3.8, (0, 0, 7.4), M("copper", 0.5), seg=24, rings=14, zscale=0.85))
    parts.append(cyl("lantern", 0.9, 1.6, (0, 0, 10.4), M("plaster_white"), verts=10, bevel=0.04))
    parts.append(cyl("lantop", 1.2, 1.3, (0, 0, 12.0), M("copper", 0.5), verts=10, r2=0.03, bevel=0.03))
    door(parts, 0, -3.5, w=1.4, h=2.6)
    for sx in (-1, 1):
        parts.append(arch("w", 0.7, 1.6, 0.25, (sx * 2.3, -3.55, 2.2), M("glass_warm", 0.3), bevel=0))
    parts.append(box("snow", (7.3, 7.3, 0.1), (0, 0, 5.0), M("snow"), bevel=0.05))
    visual = join(parts, "st_adalbert")
    export("st_adalbert", visual, join(col, "col"))


# ------------------------------------------------------------------ street furniture
def market_stall():
    reset()
    parts = [box("counter", (2.4, 1.2, 1.1), (0, 0, 0), M("wood"), bevel=0.05, wonk=0.04),
             box("counter_top", (2.7, 1.5, 0.10), (0, 0, 1.1), M("wood_dark"), bevel=0.04, wonk=0.02)]
    for x in (-1.15, 1.15):
        for y in (-0.55, 0.55):
            parts.append(cyl("post", 0.07, 2.4, (x, y, 0), M("wood_dark"), verts=8, bevel=0.02))
    parts.append(roof("awning", 3.0, 2.0, 0.7, (0, 0, 2.3), M("canvas"), sag=0.15, flare=0.3, cuts=4, bevel=0.03))
    for i in range(3):
        parts.append(box("stripe", (0.3, 1.9, 0.03), (-0.9 + i * 0.9, 0, 2.31), M("canvas_stripe"), bevel=0))
    parts.append(blob("sack", (0.55, 0.45, 0.45), (-0.7, 0.1, 1.18), M("canvas")))
    parts.append(box("crate", (0.6, 0.45, 0.35), (0.6, 0.1, 1.18), M("wood_dark"), bevel=0.03, wonk=0.02))
    parts.append(blob("loaf", (0.3, 0.2, 0.15), (0.0, 0.2, 1.18), M("plaster_ochre")))
    export("market_stall", join(parts, "market_stall"), box("c", (2.4, 1.2, 1.1), (0, 0, 0)))


def barrel():
    reset()
    parts = [cyl("lo", 0.38, 0.5, (0, 0, 0), M("wood"), verts=16, r2=0.47, bevel=0.02),
             cyl("hi", 0.47, 0.5, (0, 0, 0.5), M("wood"), verts=16, r2=0.38, bevel=0.02)]
    for z in (0.12, 0.82):
        parts.append(cyl("hoop", 0.46, 0.07, (0, 0, z), M("iron", 0.5), verts=16, r2=0.46, bevel=0.01))
    parts.append(cyl("hoopm", 0.49, 0.07, (0, 0, 0.47), M("iron", 0.5), verts=16, bevel=0.01))
    export("barrel", join(parts, "barrel"), cyl("c", 0.47, 1.0, (0, 0, 0), None, verts=8))


def crate_stack():
    reset()
    parts = [box("c1", (1.0, 0.8, 0.6), (0, 0, 0), M("wood"), bevel=0.04, wonk=0.02),
             box("c2", (0.8, 0.8, 0.5), (0.1, 0.05, 0.6), M("wood_dark"), bevel=0.04, wonk=0.02, rot=(0, 0, 0.15)),
             box("c3", (0.9, 0.7, 0.55), (1.0, 0.1, 0), M("wood"), bevel=0.04, wonk=0.02)]
    export("crate_stack", join(parts, "crate_stack"), box("c", (2.0, 0.9, 1.1), (0.5, 0, 0)))


def cart():
    reset()
    wood, dark = M("wood"), M("wood_dark")
    parts = [box("bed", (1.2, 2.2, 0.15), (0, 0, 0.6), wood, bevel=0.03, wonk=0.02)]
    for sx in (-1, 1):
        parts.append(box("side", (0.08, 2.2, 0.5), (sx * 0.6, 0, 0.75), wood, bevel=0.02, wonk=0.02))
        parts.append(cyl("wheel", 0.62, 0.12, (sx * 0.74, -0.2, 0.6), dark, verts=16, rot=(0, math.pi / 2, 0), center=True, bevel=0.02))
        parts.append(cyl("rim", 0.62, 0.13, (sx * 0.74, -0.2, 0.6), M("iron", 0.5), verts=16, rot=(0, math.pi / 2, 0), center=True, r2=0.62, bevel=0.01))
        parts.append(cyl("wheel_in", 0.5, 0.14, (sx * 0.74, -0.2, 0.6), M("black"), verts=16, rot=(0, math.pi / 2, 0), center=True, bevel=0))
        for k in range(4):
            parts.append(cbox("spoke", (0.06, 0.06, 1.1), (sx * 0.74, -0.2, 0.6), wood, rot=(0, 0, math.tau * k / 8) if False else (math.tau * k / 8, 0, 0), bevel=0.01))
        parts.append(sphere("hub", 0.12, (sx * 0.78, -0.2, 0.6), dark, seg=10, rings=6))
        parts.append(cyl("shaft", 0.05, 1.7, (sx * 0.42, 1.1, 0.45), dark, verts=8, rot=(math.pi / 2 - 0.15, 0, 0), bevel=0.01))
    parts.append(box("back", (1.2, 0.08, 0.5), (0, -1.1, 0.75), wood, bevel=0.02))
    parts.append(cyl("axle", 0.06, 1.7, (0, -0.2, 0.6), dark, verts=8, rot=(0, math.pi / 2, 0), center=True, bevel=0))
    parts.append(blob("load", (1.0, 1.5, 0.6), (0, -0.1, 0.7), M("canvas")))
    export("cart", join(parts, "cart"), box("c", (1.5, 2.4, 1.25), (0, 0, 0)))


def well():
    reset()
    stone = M("stone_dark")
    parts = []
    for k in range(8):
        a = math.tau * k / 8
        parts.append(cbox("stone", (0.95, 0.55, 0.5), (1.15 * math.cos(a), 1.15 * math.sin(a), 0.25), stone, rot=(0, 0, a + math.pi / 2), bevel=0.06, wonk=0.03))
        parts.append(cbox("stone", (0.95, 0.55, 0.5), (1.15 * math.cos(a + math.pi / 8), 1.15 * math.sin(a + math.pi / 8), 0.75), stone, rot=(0, 0, a + math.pi / 8 + math.pi / 2), bevel=0.06, wonk=0.03))
    parts.append(cyl("hole", 1.0, 0.05, (0, 0, 1.0), M("glass", 0.4), verts=16, bevel=0))
    for sx in (-1, 1):
        parts.append(cyl("post", 0.09, 2.4, (sx * 1.1, 0, 1.0), M("wood_dark"), verts=8, bevel=0.02))
    parts.append(cyl("beam", 0.08, 2.6, (0, 0, 3.35), M("wood_dark"), verts=8, rot=(0, math.pi / 2, 0), center=True, bevel=0.02))
    parts.append(roof("wroof", 3.2, 1.8, 0.9, (0, 0, 3.45), M("tile_dark"), sag=0.1, flare=0.25, cuts=3))
    parts.append(cyl("windlass", 0.14, 2.0, (0, 0, 2.9), M("wood"), verts=10, rot=(0, math.pi / 2, 0), center=True, bevel=0.02))
    parts.append(cyl("bucket", 0.16, 0.3, (0, 0, 1.6), M("wood"), verts=10, r2=0.14, bevel=0.02))
    parts.append(box("snowcap", (1.2, 1.2, 0.1), (0.4, 0.3, 1.0), M("snow"), bevel=0.05, wonk=0.03))
    export("well", join(parts, "well"), cyl("c", 1.4, 1.0, (0, 0, 0), None, verts=8))


def lantern_post():
    reset()
    iron = M("iron", 0.6)
    parts = [cyl("post", 0.12, 3.6, (0, 0, 0), M("wood_dark"), verts=10, r2=0.09, bevel=0.02),
             box("post_cap", (0.3, 0.3, 0.12), (0, 0, 3.6), iron, bevel=0.03)]
    # curved bracket from short cylinders
    for i in range(4):
        a = math.pi / 2 * (i + 0.5) / 4
        cx, cz = 0.55 - 0.55 * math.cos(a), 2.85 + 0.55 * math.sin(a)
        parts.append(cyl("arm", 0.03, 0.26, (cx, 0, cz), iron, verts=8, rot=(0, a, 0), center=True, bevel=0))
    parts.append(cyl("arm2", 0.03, 0.4, (0.75, 0, 3.4), iron, verts=8, rot=(0, math.pi / 2, 0), center=True, bevel=0))
    parts.append(box("cage", (0.36, 0.36, 0.5), (0.9, 0, 2.75), iron, bevel=0.03))
    parts.append(box("glow", (0.30, 0.30, 0.44), (0.9, 0, 2.78), M("gold", 0.3, emit=(1.0, 0.72, 0.35), emit_strength=6.0), bevel=0.02))
    parts.append(cyl("cap", 0.28, 0.25, (0.9, 0, 3.25), iron, verts=8, r2=0.03, bevel=0.01))
    for s in (-1, 1):
        parts.append(box("bar", (0.03, 0.4, 0.5), (0.9 + s * 0.17, 0, 2.75), iron, bevel=0))
        parts.append(box("bar2", (0.4, 0.03, 0.5), (0.9, s * 0.17, 2.75), iron, bevel=0))
    export("lantern_post", join(parts, "lantern_post"), cyl("c", 0.14, 3.6, (0, 0, 0), None, verts=6))


# Human figures are built by build_characters.py (MakeHuman via MPFB2). Nothing here.


if __name__ == "__main__" and "--animals" not in sys.argv:
    tenement("tenement_a", 10.0, 3, "gable", "plaster_ochre", bays=3, shutters=True)
    tenement("tenement_b", 8.0, 3, "attyka", "plaster_rose", bays=2)
    tenement("tenement_c", 12.0, 4, "mansard", "plaster_cream", bays=3, pilasters=True, arched_windows=True)
    tenement("tenement_d", 10.0, 3, "attyka", "plaster_sage", bays=3, arched_windows=True, shutters=True)
    tenement("tenement_e", 8.0, 4, "gable", "plaster_blue", bays=2, shutters=True)
    sukiennice()
    st_marys()
    town_hall()
    st_adalbert()
    market_stall()
    barrel()
    crate_stack()
    cart()
    well()
    lantern_post()
    print("[assets] done")


# ------------------------------------------------------------------ ANIMALS AND THE DRAGON (lofted along the body axis)
def loft_y(name, rings, mat, verts=16, subsurf=2, smooth=60):
    """Tube lofted along Y: rings are (y, cx, cz, rx, rz). Front of the animal at -Y."""
    bm = bmesh.new()
    loops = []
    for (y, cx, cz, rx, rz) in rings:
        loop = []
        for i in range(verts):
            t = math.tau * i / verts
            loop.append(bm.verts.new((cx + rx * math.cos(t), y, cz + rz * math.sin(t))))
        loops.append(loop)
    for a, b in zip(loops, loops[1:]):
        for i in range(verts):
            bm.faces.new((a[i], a[(i + 1) % verts], b[(i + 1) % verts], b[i]))
    for loop, ring, flip in ((loops[0], rings[0], True), (loops[-1], rings[-1], False)):
        c = bm.verts.new((ring[1], ring[0], ring[2]))
        for i in range(verts):
            a, b = loop[i], loop[(i + 1) % verts]
            bm.faces.new((c, b, a) if flip else (c, a, b))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    return finish(o, bevel=0, subsurf=subsurf, smooth=smooth)


def leg(name, top, bottom, r_top, r_bottom, mat, knee=None):
    """Tapered leg from top (x,y,z) to bottom, optional knee point for a bend."""
    pts = [top, knee, bottom] if knee else [top, bottom]
    rings = []
    n = len(pts)
    for i, p in enumerate(pts):
        r = r_top + (r_bottom - r_top) * i / (n - 1)
        rings.append((p[1], p[0], p[2], r, r))
    # loft_y needs rings ordered along y; legs are vertical, so build with a plain vertical loft instead
    bm = bmesh.new()
    loops = []
    verts = 12
    for (yy, cx, cz, rx, rz) in rings:
        loops.append([bm.verts.new((cx + rx * math.cos(math.tau * k / verts), yy + rz * math.sin(math.tau * k / verts), cz)) for k in range(verts)])
    for a, b in zip(loops, loops[1:]):
        for i in range(verts):
            bm.faces.new((a[i], a[(i + 1) % verts], b[(i + 1) % verts], b[i]))
    for loop, flip in ((loops[0], True), (loops[-1], False)):
        c = bm.verts.new(sum((v.co for v in loop), Vector((0, 0, 0))) / verts)
        for i in range(verts):
            a, b = loop[i], loop[(i + 1) % verts]
            bm.faces.new((c, b, a) if flip else (c, a, b))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    return finish(o, bevel=0, subsurf=2, smooth=60)


def dog_vizsla():
    """Hungarian Vizsla: lean pointer, rust-gold, floppy ears, whip tail. About 0.6 m at the shoulder."""
    reset()
    PAL["vizsla"] = (0.62, 0.36, 0.16)
    PAL["nose"] = (0.35, 0.22, 0.16)
    coat = M("vizsla", 0.8)
    parts = []
    H = 0.58
    # body: chest deep, tucked waist, rump
    parts.append(loft_y("body", [(-0.30, 0, H - 0.02, 0.09, 0.12), (-0.18, 0, H - 0.04, 0.12, 0.17), (0.0, 0, H - 0.05, 0.115, 0.15),
                                 (0.14, 0, H - 0.02, 0.10, 0.12), (0.26, 0, H - 0.01, 0.085, 0.10), (0.34, 0, H - 0.04, 0.05, 0.06)], coat))
    # neck and head
    parts.append(loft_y("neck", [(-0.28, 0, H, 0.07, 0.08), (-0.40, 0, H + 0.08, 0.06, 0.07), (-0.48, 0, H + 0.15, 0.055, 0.06)], coat))
    parts.append(loft_y("head", [(-0.46, 0, H + 0.16, 0.055, 0.06), (-0.54, 0, H + 0.17, 0.062, 0.065), (-0.62, 0, H + 0.15, 0.05, 0.05),
                                 (-0.72, 0, H + 0.12, 0.035, 0.035), (-0.78, 0, H + 0.11, 0.028, 0.028)], coat))
    parts.append(sphere("nose", 0.02, (0, -0.79, H + 0.115), M("nose", 0.4), seg=10, rings=6))
    for sx in (-1, 1):
        parts.append(sphere("eye", 0.012, (sx * 0.035, -0.60, H + 0.18), M("black", 0.3), seg=8, rings=6))
        # floppy ear: flat lobe hanging beside the head
        e = box("ear", (0.02, 0.06, 0.14), (sx * 0.065, -0.52, H + 0.05), coat, bevel=0.008, subsurf=1)
        edit_verts(e, lambda co, sx=sx: setattr(co, "x", co.x + sx * 0.02 * (1 - (co.z - H - 0.05) / 0.14)))
        parts.append(e)
    # legs (front straight, hind angled)
    for sx in (-1, 1):
        parts.append(leg("foreleg", (sx * 0.07, -0.20, H - 0.08), (sx * 0.075, -0.20, 0.0), 0.038, 0.025, coat, knee=(sx * 0.072, -0.21, 0.28)))
        parts.append(leg("hindleg", (sx * 0.075, 0.22, H - 0.10), (sx * 0.08, 0.30, 0.0), 0.05, 0.025, coat, knee=(sx * 0.078, 0.17, 0.26)))
        for yy in (-0.20, 0.30):
            parts.append(box("paw", (0.06, 0.08, 0.03), (sx * 0.076, yy - 0.01, 0), coat, bevel=0.01, subsurf=1))
    parts.append(loft_y("tail", [(0.32, 0, H - 0.02, 0.02, 0.02), (0.48, 0, H - 0.08, 0.014, 0.014), (0.62, 0, H - 0.20, 0.007, 0.007)], coat))
    visual = join(parts, "dog_vizsla")
    export("dog_vizsla", visual, box("c", (0.24, 1.1, H + 0.2), (0, 0, 0)))


def dog_pomeranian():
    """Pomeranian: tiny, round, fluffy, orange or cream, plumed tail over the back, fox face. 0.25 m tall."""
    reset()
    PAL["pom"] = (0.86, 0.58, 0.28)
    PAL["pom_light"] = (0.94, 0.80, 0.58)
    coat = M("pom", 0.95)
    light = M("pom_light", 0.95)
    parts = []
    H = 0.22
    parts.append(sphere("body", 0.13, (0, 0.02, H - 0.05), coat, seg=20, rings=14, zscale=0.85))
    parts.append(sphere("ruff", 0.12, (0, -0.07, H - 0.02), light, seg=20, rings=14, zscale=0.9))
    parts.append(sphere("head", 0.065, (0, -0.15, H + 0.06), coat, seg=16, rings=12))
    parts.append(loft_y("muzzle", [(-0.17, 0, H + 0.04, 0.03, 0.03), (-0.22, 0, H + 0.03, 0.015, 0.015)], light))
    parts.append(sphere("nose", 0.011, (0, -0.225, H + 0.03), M("black", 0.4), seg=8, rings=6))
    for sx in (-1, 1):
        parts.append(sphere("eye", 0.009, (sx * 0.028, -0.19, H + 0.07), M("black", 0.3), seg=8, rings=6))
        parts.append(cyl("ear", 0.018, 0.04, (sx * 0.04, -0.13, H + 0.10), coat, verts=6, r2=0.003, bevel=0))
    for sx in (-1, 1):
        for yy in (-0.06, 0.09):
            parts.append(leg("leg", (sx * 0.05, yy, H - 0.10), (sx * 0.052, yy, 0.0), 0.025, 0.02, coat))
    parts.append(sphere("tail", 0.07, (0, 0.13, H + 0.05), light, seg=14, rings=10, zscale=0.6))
    visual = join(parts, "dog_pomeranian")
    export("dog_pomeranian", visual, box("c", (0.2, 0.42, H + 0.12), (0, 0, 0)))


def cat():
    reset()
    PAL["tabby"] = (0.42, 0.38, 0.32)
    coat = M("tabby", 0.9)
    parts = []
    H = 0.26
    parts.append(loft_y("body", [(-0.16, 0, H - 0.03, 0.06, 0.07), (0.0, 0, H - 0.04, 0.065, 0.075), (0.16, 0, H - 0.03, 0.06, 0.07), (0.22, 0, H - 0.04, 0.03, 0.035)], coat))
    parts.append(loft_y("neck", [(-0.15, 0, H, 0.045, 0.045), (-0.22, 0, H + 0.04, 0.04, 0.04)], coat))
    parts.append(sphere("head", 0.05, (0, -0.25, H + 0.07), coat, seg=16, rings=12, zscale=0.9))
    parts.append(sphere("muzzle", 0.025, (0, -0.29, H + 0.05), coat, seg=10, rings=8, zscale=0.7))
    parts.append(sphere("nose", 0.007, (0, -0.31, H + 0.055), M("facing_red", 0.5), seg=8, rings=6))
    for sx in (-1, 1):
        parts.append(sphere("eye", 0.008, (sx * 0.022, -0.285, H + 0.08), M("gold", 0.3), seg=8, rings=6))
        parts.append(cyl("ear", 0.018, 0.04, (sx * 0.03, -0.24, H + 0.10), coat, verts=3, r2=0.002, bevel=0))
    for sx in (-1, 1):
        for yy in (-0.10, 0.12):
            parts.append(leg("leg", (sx * 0.04, yy, H - 0.06), (sx * 0.042, yy, 0.0), 0.02, 0.015, coat))
    parts.append(loft_y("tail", [(0.20, 0, H - 0.02, 0.015, 0.015), (0.36, 0, H + 0.06, 0.012, 0.012), (0.44, 0, H + 0.18, 0.008, 0.008)], coat))
    visual = join(parts, "cat")
    export("cat", visual, box("c", (0.14, 0.7, H + 0.1), (0, 0, 0)))


def dragon():
    """Smok Wawelski: the Wawel dragon, coiled at the mouth of its cave. About 6 m nose to tail. Easter egg."""
    reset()
    PAL["dragon"] = (0.16, 0.30, 0.22)
    PAL["dragon_belly"] = (0.55, 0.50, 0.30)
    PAL["dragon_spine"] = (0.10, 0.18, 0.14)
    scale_ = M("dragon", 0.7)
    belly = M("dragon_belly", 0.8)
    dark = M("dragon_spine", 0.6)
    parts = []
    H = 1.2
    # body curving: build rings with x offsets to coil
    body = []
    for i in range(9):
        t = i / 8
        yy = -1.2 + 2.8 * t
        cx = 0.5 * math.sin(t * math.pi)
        r = 0.55 * math.sin(0.3 + t * 2.5) + 0.25
        body.append((yy, cx, H - 0.1 + 0.1 * math.sin(t * math.pi), max(0.18, r), max(0.16, r * 0.9)))
    parts.append(loft_y("body", body, scale_, verts=20))
    parts.append(loft_y("belly", [(y, cx, cz - rz * 0.35, rx * 0.7, rz * 0.5) for (y, cx, cz, rx, rz) in body], belly, verts=16))
    # neck arching up and head
    neck = [(-1.15, 0, H + 0.1, 0.32, 0.30), (-1.6, -0.1, H + 0.6, 0.26, 0.26), (-1.95, -0.15, H + 1.2, 0.22, 0.22), (-2.15, -0.15, H + 1.7, 0.2, 0.2)]
    parts.append(loft_y("neck", neck, scale_, verts=16))
    head = [(-2.1, -0.15, H + 1.75, 0.22, 0.2), (-2.45, -0.15, H + 1.8, 0.28, 0.24), (-2.85, -0.15, H + 1.72, 0.22, 0.17), (-3.2, -0.15, H + 1.62, 0.14, 0.10), (-3.35, -0.15, H + 1.6, 0.06, 0.05)]
    parts.append(loft_y("head", head, scale_, verts=16))
    for sx in (-1, 1):
        parts.append(sphere("eye", 0.06, (-0.15 + sx * 0.17, -2.6, H + 1.88), M("gold", 0.2), seg=12, rings=8))
        parts.append(cyl("horn", 0.06, 0.45, (-0.15 + sx * 0.16, -2.35, H + 1.95), dark, verts=8, r2=0.01, rot=(0.5, sx * 0.3, 0), bevel=0))
        parts.append(cyl("nostril", 0.03, 0.02, (-0.15 + sx * 0.06, -3.3, H + 1.68), dark, verts=8, bevel=0))
    # spines along the back
    for i in range(14):
        t = i / 13
        yy = -2.0 + 4.4 * t
        seg_ = neck if yy < -1.15 else body
        parts.append(cyl("spine", 0.08 - 0.03 * t, 0.28 - 0.1 * t, (0.5 * math.sin(max(0, (yy + 1.2) / 2.8) * math.pi) if yy > -1.2 else -0.1, yy, H + 0.45 + (0.9 * max(0, -yy - 1.15) if yy < -1.15 else 0)), dark, verts=4, r2=0.01, bevel=0))
    # tail
    parts.append(loft_y("tail", [(1.55, 0.0, H - 0.05, 0.25, 0.22), (2.2, 0.35, H - 0.2, 0.17, 0.15), (2.8, 0.9, H - 0.4, 0.10, 0.09), (3.3, 1.5, H - 0.6, 0.05, 0.05)], scale_, verts=14))
    # wings: folded, membrane as flat fans
    for sx in (-1, 1):
        w = box("wing", (0.06, 1.6, 1.3), (sx * 0.62, 0.1, H + 0.2), dark, bevel=0.02)
        edit_verts(w, lambda co, sx=sx: setattr(co, "x", co.x + sx * 0.5 * ((co.z - H - 0.2) / 1.3) ** 2))
        parts.append(w)
        parts.append(cyl("wing_bone", 0.05, 1.5, (sx * 0.7, 0.1, H + 0.2), scale_, verts=8, r2=0.02, rot=(0, sx * 0.35, 0), bevel=0))
    # legs, crouched
    for sx in (-1, 1):
        parts.append(leg("foreleg", (sx * 0.45, -0.8, H - 0.2), (sx * 0.65, -1.0, 0.0), 0.16, 0.1, scale_, knee=(sx * 0.6, -0.7, 0.5)))
        parts.append(leg("hindleg", (sx * 0.5, 1.0, H - 0.2), (sx * 0.8, 1.3, 0.0), 0.2, 0.12, scale_, knee=(sx * 0.7, 0.8, 0.55)))
        for yy in (-1.0, 1.3):
            for k in range(3):
                parts.append(cyl("claw", 0.04, 0.22, (sx * (0.65 if yy < 0 else 0.8) + (k - 1) * 0.09, yy - 0.15, 0.03), dark, verts=6, r2=0.005, rot=(math.pi / 2 + 0.2, 0, 0), bevel=0))
    visual = join(parts, "dragon")
    export("dragon", visual, box("c", (2.4, 6.8, H + 2.1), (0, 0.4, 0)))


if __name__ == "__main__" and "--animals" in sys.argv:
    dog_vizsla()
    dog_pomeranian()
    cat()
    dragon()
    print("[assets] animals done")


# ------------------------------------------------------------------ more street animals (period Krakow): horse, goat, pig, goose, pigeon
def horse():
    """Draught/riding horse, bay. About 1.55 m at the withers. Stands square."""
    reset()
    PAL["bay"] = (0.36, 0.22, 0.12)
    PAL["mane"] = (0.10, 0.07, 0.05)
    coat = M("bay", 0.75)
    mane = M("mane", 0.9)
    parts = []
    W = 1.50
    parts.append(loft_y("body", [(-0.70, 0, W - 0.25, 0.22, 0.30), (-0.45, 0, W - 0.22, 0.30, 0.40), (-0.10, 0, W - 0.24, 0.32, 0.42),
                                 (0.30, 0, W - 0.25, 0.31, 0.40), (0.62, 0, W - 0.23, 0.27, 0.34), (0.85, 0, W - 0.30, 0.15, 0.20)], coat, verts=20))
    parts.append(loft_y("neck", [(-0.65, 0, W - 0.10, 0.17, 0.25), (-0.95, 0, W + 0.15, 0.14, 0.20), (-1.20, 0, W + 0.42, 0.11, 0.15), (-1.35, 0, W + 0.58, 0.10, 0.12)], coat, verts=16))
    parts.append(loft_y("head", [(-1.32, 0, W + 0.60, 0.11, 0.13), (-1.45, 0, W + 0.55, 0.12, 0.15), (-1.65, 0, W + 0.40, 0.09, 0.11),
                                 (-1.85, 0, W + 0.22, 0.07, 0.08), (-1.95, 0, W + 0.15, 0.06, 0.06)], coat, verts=16))
    parts.append(box("mane", (0.05, 0.75, 0.20), (0, -1.0, W + 0.30), mane, bevel=0.01, subsurf=1))
    edit_verts(parts[-1], lambda co: setattr(co, "z", co.z + 0.55 * ((-1.0 - co.y) / 0.4)))
    for sx in (-1, 1):
        parts.append(cyl("ear", 0.035, 0.14, (sx * 0.07, -1.38, W + 0.68), coat, verts=6, r2=0.005, rot=(0.2, sx * 0.25, 0), bevel=0))
        parts.append(sphere("eye", 0.022, (sx * 0.10, -1.55, W + 0.50), M("black", 0.3), seg=10, rings=6))
        parts.append(leg("foreleg", (sx * 0.16, -0.45, W - 0.35), (sx * 0.17, -0.45, 0.0), 0.09, 0.05, coat, knee=(sx * 0.165, -0.47, 0.62)))
        parts.append(leg("hindleg", (sx * 0.17, 0.55, W - 0.35), (sx * 0.18, 0.68, 0.0), 0.12, 0.05, coat, knee=(sx * 0.175, 0.50, 0.58)))
        for yy in (-0.45, 0.68):
            parts.append(cyl("hoof", 0.065, 0.07, (sx * 0.17, yy, 0), M("black", 0.5), verts=10, bevel=0.01))
    parts.append(box("tail", (0.08, 0.10, 0.75), (0, 0.92, W - 0.95), mane, bevel=0.02, subsurf=1))
    visual = join(parts, "horse")
    export("horse", visual, box("c", (0.6, 2.7, W + 0.7), (0, -0.4, 0)))


def goat():
    reset()
    PAL["goat"] = (0.72, 0.68, 0.60)
    coat = M("goat", 0.9)
    parts = []
    H = 0.62
    parts.append(loft_y("body", [(-0.28, 0, H - 0.05, 0.11, 0.14), (0.0, 0, H - 0.06, 0.13, 0.16), (0.26, 0, H - 0.05, 0.11, 0.13), (0.34, 0, H - 0.07, 0.05, 0.06)], coat))
    parts.append(loft_y("neck", [(-0.26, 0, H, 0.07, 0.08), (-0.42, 0, H + 0.12, 0.06, 0.07), (-0.50, 0, H + 0.20, 0.055, 0.06)], coat))
    parts.append(loft_y("head", [(-0.48, 0, H + 0.21, 0.055, 0.06), (-0.60, 0, H + 0.18, 0.05, 0.05), (-0.70, 0, H + 0.14, 0.035, 0.035)], coat))
    parts.append(box("beard", (0.03, 0.03, 0.08), (0, -0.66, H + 0.03), M("hair"), bevel=0.005, subsurf=1))
    for sx in (-1, 1):
        parts.append(cyl("horn", 0.02, 0.18, (sx * 0.035, -0.50, H + 0.25), M("stone_dark"), verts=6, r2=0.004, rot=(-0.6, sx * 0.4, 0), bevel=0))
        parts.append(box("ear", (0.02, 0.05, 0.10), (sx * 0.07, -0.50, H + 0.12), coat, bevel=0.005, subsurf=1))
        parts.append(sphere("eye", 0.012, (sx * 0.04, -0.58, H + 0.20), M("gold", 0.3), seg=8, rings=6))
        parts.append(leg("foreleg", (sx * 0.07, -0.20, H - 0.10), (sx * 0.075, -0.20, 0.0), 0.035, 0.022, coat))
        parts.append(leg("hindleg", (sx * 0.075, 0.22, H - 0.10), (sx * 0.08, 0.26, 0.0), 0.045, 0.022, coat, knee=(sx * 0.078, 0.18, 0.28)))
    parts.append(cyl("tail", 0.02, 0.10, (0, 0.34, H - 0.02), coat, verts=6, r2=0.005, rot=(-1.0, 0, 0), bevel=0))
    visual = join(parts, "goat")
    export("goat", visual, box("c", (0.24, 1.0, H + 0.3), (0, 0, 0)))


def pig():
    reset()
    PAL["pig"] = (0.82, 0.62, 0.56)
    coat = M("pig", 0.8)
    parts = []
    H = 0.55
    parts.append(loft_y("body", [(-0.40, 0, H - 0.20, 0.17, 0.18), (-0.15, 0, H - 0.22, 0.22, 0.24), (0.15, 0, H - 0.22, 0.22, 0.24), (0.40, 0, H - 0.20, 0.17, 0.18), (0.48, 0, H - 0.22, 0.08, 0.09)], coat, verts=20))
    parts.append(loft_y("head", [(-0.40, 0, H - 0.18, 0.14, 0.15), (-0.58, 0, H - 0.20, 0.10, 0.10), (-0.68, 0, H - 0.22, 0.06, 0.06)], coat))
    parts.append(cyl("snout", 0.055, 0.03, (0, -0.70, H - 0.22), M("facing_red", 0.7), verts=12, rot=(math.pi / 2, 0, 0), bevel=0.005))
    for sx in (-1, 1):
        parts.append(box("ear", (0.06, 0.02, 0.10), (sx * 0.09, -0.45, H - 0.06), coat, bevel=0.005, subsurf=1, rot=(0.3, sx * 0.4, 0)))
        parts.append(sphere("eye", 0.012, (sx * 0.06, -0.55, H - 0.14), M("black", 0.3), seg=8, rings=6))
        for yy in (-0.25, 0.30):
            parts.append(leg("leg", (sx * 0.10, yy, H - 0.35), (sx * 0.10, yy, 0.0), 0.05, 0.035, coat))
    parts.append(cyl("tail", 0.012, 0.12, (0, 0.50, H - 0.14), coat, verts=6, r2=0.004, rot=(-0.8, 0.6, 0), bevel=0))
    visual = join(parts, "pig")
    export("pig", visual, box("c", (0.44, 1.3, H + 0.05), (0, 0, 0)))


def goose():
    reset()
    PAL["goose"] = (0.94, 0.93, 0.90)
    coat = M("goose", 0.85)
    parts = []
    H = 0.30
    parts.append(loft_y("body", [(-0.18, 0, H, 0.08, 0.09), (0.0, 0, H, 0.11, 0.12), (0.18, 0, H + 0.02, 0.08, 0.09), (0.30, 0, H + 0.08, 0.03, 0.03)], coat))
    parts.append(loft_y("neck", [(-0.16, 0, H + 0.04, 0.04, 0.04), (-0.24, 0, H + 0.20, 0.035, 0.035), (-0.26, 0, H + 0.36, 0.033, 0.033)], coat))
    parts.append(sphere("head", 0.045, (0, -0.27, H + 0.40), coat, seg=12, rings=8, zscale=0.9))
    parts.append(cyl("beak", 0.022, 0.07, (0, -0.33, H + 0.39), M("gold", 0.5), verts=8, r2=0.008, rot=(math.pi / 2, 0, 0), bevel=0))
    for sx in (-1, 1):
        parts.append(sphere("eye", 0.007, (sx * 0.028, -0.29, H + 0.42), M("black", 0.3), seg=8, rings=6))
        parts.append(leg("leg", (sx * 0.035, 0.02, H - 0.05), (sx * 0.04, 0.02, 0.0), 0.012, 0.01, M("gold", 0.6)))
        parts.append(box("foot", (0.06, 0.07, 0.01), (sx * 0.04, 0.0, 0), M("gold", 0.6), bevel=0.003))
    visual = join(parts, "goose")
    export("goose", visual, box("c", (0.24, 0.6, H + 0.5), (0, 0, 0)))


def pigeon():
    reset()
    PAL["pigeon"] = (0.45, 0.46, 0.52)
    coat = M("pigeon", 0.85)
    parts = []
    H = 0.08
    parts.append(loft_y("body", [(-0.06, 0, H, 0.035, 0.04), (0.0, 0, H, 0.045, 0.05), (0.07, 0, H + 0.01, 0.03, 0.035), (0.14, 0, H + 0.04, 0.015, 0.012)], coat))
    parts.append(sphere("head", 0.024, (0, -0.075, H + 0.05), coat, seg=10, rings=8))
    parts.append(cyl("beak", 0.006, 0.02, (0, -0.10, H + 0.048), M("black", 0.5), verts=6, r2=0.002, rot=(math.pi / 2, 0, 0), bevel=0))
    for sx in (-1, 1):
        parts.append(leg("leg", (sx * 0.012, 0.0, H - 0.03), (sx * 0.014, 0.0, 0.0), 0.004, 0.003, M("facing_red", 0.6)))
    visual = join(parts, "pigeon")
    export("pigeon", visual, box("c", (0.08, 0.24, H + 0.1), (0, 0, 0)))


if __name__ == "__main__" and "--animals" in sys.argv:
    horse()
    goat()
    pig()
    goose()
    pigeon()
    print("[assets] farm animals done")


# ------------------------------------------------------------------ parametric dog: breeds plausible in 1795 Krakow
def dog(name, colour, H=0.55, L=1.0, chest=1.0, slim=1.0, ear="drop", tail="whip", muzzle=1.0, fluff=0.0, second=None):
    """H shoulder height, L body length factor, chest depth factor, slim width factor,
    ear: drop|prick|fold, tail: whip|curl|plume|sabre, muzzle length factor, fluff adds a thick coat shell."""
    reset()
    PAL[name + "_c"] = colour
    coat = M(name + "_c", 0.85)
    coat2 = M(name + "_c", 0.85)
    if second:
        PAL[name + "_c2"] = second
        coat2 = M(name + "_c2", 0.85)
    parts = []
    s = H / 0.58
    bl = L * s
    rings = [(-0.30 * bl, 0, H - 0.02, 0.09 * slim * s, 0.12 * chest * s), (-0.18 * bl, 0, H - 0.04, 0.12 * slim * s, 0.17 * chest * s),
             (0.0, 0, H - 0.05, 0.115 * slim * s, 0.15 * chest * s), (0.14 * bl, 0, H - 0.02, 0.10 * slim * s, 0.12 * s),
             (0.26 * bl, 0, H - 0.01, 0.085 * slim * s, 0.10 * s), (0.34 * bl, 0, H - 0.04, 0.05 * s, 0.06 * s)]
    parts.append(loft_y("body", rings, coat))
    if fluff:
        parts.append(loft_y("fluff", [(y, cx, cz, rx + fluff, rz + fluff) for (y, cx, cz, rx, rz) in rings[:5]], coat2))
    parts.append(loft_y("neck", [(-0.28 * bl, 0, H, 0.07 * s, 0.08 * s), (-0.40 * bl, 0, H + 0.08 * s, 0.06 * s, 0.07 * s), (-0.48 * bl, 0, H + 0.15 * s, 0.055 * s, 0.06 * s)], coat))
    hz = H + 0.16 * s
    hy = -0.46 * bl
    parts.append(loft_y("head", [(hy, 0, hz, 0.055 * s, 0.06 * s), (hy - 0.08 * s, 0, hz + 0.01 * s, 0.062 * s, 0.065 * s), (hy - 0.16 * s, 0, hz - 0.01 * s, 0.05 * s, 0.05 * s),
                                 (hy - (0.16 + 0.10 * muzzle) * s, 0, hz - 0.04 * s, 0.035 * s, 0.035 * s), (hy - (0.16 + 0.16 * muzzle) * s, 0, hz - 0.05 * s, 0.028 * s, 0.028 * s)], coat2 if second else coat))
    nose_y = hy - (0.16 + 0.17 * muzzle) * s
    parts.append(sphere("nose", 0.02 * s, (0, nose_y, hz - 0.045 * s), M("nose", 0.4) if "nose" in PAL else M("black", 0.4), seg=10, rings=6))
    for sx in (-1, 1):
        parts.append(sphere("eye", 0.012 * s, (sx * 0.035 * s, hy - 0.14 * s, hz + 0.02 * s), M("black", 0.3), seg=8, rings=6))
        if ear == "drop":
            e = box("ear", (0.02 * s, 0.06 * s, 0.14 * s), (sx * 0.065 * s, hy - 0.06 * s, hz - 0.11 * s), coat2 if second else coat, bevel=0.008, subsurf=1)
            edit_verts(e, lambda co, sx=sx: setattr(co, "x", co.x + sx * 0.02 * s * (1 - (co.z - hz + 0.11 * s) / (0.14 * s))))
            parts.append(e)
        elif ear == "prick":
            parts.append(cyl("ear", 0.03 * s, 0.09 * s, (sx * 0.045 * s, hy - 0.05 * s, hz + 0.05 * s), coat, verts=6, r2=0.005, rot=(0.1, sx * 0.25, 0), bevel=0))
        else:
            parts.append(box("ear", (0.05 * s, 0.03 * s, 0.05 * s), (sx * 0.06 * s, hy - 0.06 * s, hz + 0.02 * s), coat, bevel=0.008, subsurf=1))
        parts.append(leg("foreleg", (sx * 0.07 * slim * s, -0.20 * bl, H - 0.08), (sx * 0.075 * slim * s, -0.20 * bl, 0.0), 0.038 * s, 0.025 * s, coat, knee=(sx * 0.072 * slim * s, -0.21 * bl, H * 0.48)))
        parts.append(leg("hindleg", (sx * 0.075 * slim * s, 0.22 * bl, H - 0.10), (sx * 0.08 * slim * s, 0.30 * bl, 0.0), 0.05 * s, 0.025 * s, coat, knee=(sx * 0.078 * slim * s, 0.17 * bl, H * 0.45)))
        for yy in (-0.20 * bl, 0.30 * bl):
            parts.append(box("paw", (0.06 * s, 0.08 * s, 0.03 * s), (sx * 0.076 * slim * s, yy - 0.01, 0), coat, bevel=0.01, subsurf=1))
    ty = 0.32 * bl
    if tail == "whip":
        parts.append(loft_y("tail", [(ty, 0, H - 0.02, 0.02 * s, 0.02 * s), (ty + 0.16 * s, 0, H - 0.08 * s, 0.014 * s, 0.014 * s), (ty + 0.30 * s, 0, H - 0.20 * s, 0.007 * s, 0.007 * s)], coat))
    elif tail == "sabre":
        parts.append(loft_y("tail", [(ty, 0, H - 0.02, 0.025 * s, 0.025 * s), (ty + 0.14 * s, 0, H + 0.04 * s, 0.02 * s, 0.02 * s), (ty + 0.24 * s, 0, H + 0.12 * s, 0.01 * s, 0.01 * s)], coat))
    elif tail == "curl":
        parts.append(torus("tail", 0.05 * s, 0.018 * s, (0.02 * s, ty, H + 0.03 * s), coat, rot=(0, math.pi / 2, 0)))
    else:  # plume
        parts.append(sphere("tail", 0.08 * s, (0, ty + 0.02, H + 0.05 * s), coat2 if second else coat, seg=14, rings=10, zscale=0.7))
    visual = join(parts, name)
    export(name, visual, box("c", (0.26 * s, 1.1 * bl, H + 0.25 * s), (0, 0, 0)))


if __name__ == "__main__" and "--animals" in sys.argv:
    dog("dog_ogar", (0.12, 0.09, 0.07), H=0.60, L=1.05, chest=1.1, ear="drop", tail="sabre", muzzle=1.1, second=(0.55, 0.32, 0.14))   # Polish hound, black and tan
    dog("dog_chart", (0.55, 0.55, 0.58), H=0.72, L=1.05, chest=1.15, slim=0.75, ear="fold", tail="whip", muzzle=1.3)                  # Polish greyhound
    dog("dog_podhalan", (0.93, 0.92, 0.88), H=0.68, L=1.1, chest=1.05, ear="drop", tail="plume", muzzle=0.9, fluff=0.03)           # Tatra shepherd
    dog("dog_mongrel", (0.50, 0.38, 0.24), H=0.48, L=1.0, ear="fold", tail="sabre", muzzle=1.0)                                     # street dog
    dog("dog_pug", (0.80, 0.68, 0.50), H=0.28, L=0.85, chest=1.2, slim=1.2, ear="fold", tail="curl", muzzle=0.25, second=(0.15, 0.12, 0.10))   # salon pug
    print("[assets] dogs done")
