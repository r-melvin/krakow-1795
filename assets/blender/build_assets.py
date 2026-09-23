"""Stylised low-poly assets for Krakow 1795 (Rynek Glowny, winter 1795/96).

Run:  blender -b --python assets/blender/build_assets.py
Writes one .glb per asset into assets/models/.

Conventions
- Metres. Blender Z up. glTF export maps Blender (x, y, z) -> Godot (x, z, -y).
- Buildings: front face at Blender -Y (Godot +Z). Origin at base centre.
- Figures: front at Blender +Y (Godot -Z) so they face the same way as a Node3D's forward. Origin at feet.
- Collision meshes are named <asset>-col; Godot turns them into StaticBody3D colliders on import.
- Blender 5.x: transform_apply also bakes location, so every primitive here ends up with world-space vertices
  and a zero origin. Helpers that edit vertices (wedge, pyramid, arch) rely on that.
- Style: flat colours, hard edges, exaggerated proportions. Real scale is about 3x larger; the district is compressed.
"""
import bpy
import bmesh
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "models")
os.makedirs(OUT, exist_ok=True)

# ------------------------------------------------------------------ palette (late 18th c. Krakow, stylised)
PAL = {
    "plaster_ochre": (0.86, 0.70, 0.42),
    "plaster_rose": (0.82, 0.60, 0.52),
    "plaster_cream": (0.90, 0.85, 0.70),
    "plaster_sage": (0.66, 0.70, 0.56),
    "plaster_blue": (0.62, 0.70, 0.76),
    "plaster_white": (0.92, 0.90, 0.84),
    "stone": (0.68, 0.64, 0.56),
    "stone_dark": (0.48, 0.45, 0.40),
    "brick": (0.55, 0.28, 0.20),
    "brick_dark": (0.42, 0.20, 0.15),
    "tile": (0.50, 0.24, 0.16),
    "tile_dark": (0.36, 0.17, 0.12),
    "copper": (0.28, 0.48, 0.42),
    "lead": (0.30, 0.31, 0.34),
    "gold": (0.92, 0.72, 0.30),
    "glass": (0.10, 0.12, 0.16),
    "wood": (0.42, 0.30, 0.18),
    "wood_dark": (0.24, 0.16, 0.10),
    "iron": (0.10, 0.10, 0.11),
    "canvas": (0.72, 0.64, 0.50),
    "canvas_stripe": (0.55, 0.22, 0.20),
    "snow": (0.88, 0.90, 0.94),
    "skin": (0.82, 0.64, 0.52),
    "hair": (0.22, 0.15, 0.10),
    "white_coat": (0.90, 0.90, 0.92),
    "facing_red": (0.62, 0.12, 0.14),
    "black": (0.06, 0.06, 0.07),
    "crimson": (0.55, 0.10, 0.16),
    "zupan_gold": (0.82, 0.66, 0.30),
    "sukmana": (0.80, 0.76, 0.66),
    "red_cap": (0.72, 0.12, 0.12),
    "green_coat": (0.16, 0.30, 0.22),
    "brown_coat": (0.36, 0.24, 0.14),
    "navy": (0.14, 0.18, 0.32),
    "feather": (0.10, 0.45, 0.35),
}
_mats = {}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mats.clear()


def M(key, rough=0.9, emit=None, emit_strength=0.0):
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


# ------------------------------------------------------------------ primitives
def _finish(o, name, mat):
    o.name = name
    if mat:
        o.data.materials.append(mat)
    return o


def box(name, size, loc, mat=None, rot=(0, 0, 0)):
    """loc = base centre; the box sits on loc.z."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0], loc[1], loc[2] + size[2] / 2), rotation=rot)
    o = bpy.context.object
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    return _finish(o, name, mat)


def cbox(name, size, center, mat=None, rot=(0, 0, 0)):
    """Box by true centre."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=center, rotation=rot)
    o = bpy.context.object
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    return _finish(o, name, mat)


def cyl(name, r, h, loc, mat=None, verts=16, rot=(0, 0, 0), r2=None):
    """Vertical cylinder, base at loc.z. r2 = top radius (cone/frustum)."""
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=(loc[0], loc[1], loc[2] + h / 2), rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=h, location=(loc[0], loc[1], loc[2] + h / 2), rotation=rot)
    return _finish(bpy.context.object, name, mat)


def sphere(name, r, center, mat=None, seg=12, rings=8, zscale=1.0):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=r, location=center)
    o = bpy.context.object
    if zscale != 1.0:
        o.scale.z = zscale
        bpy.ops.object.transform_apply(scale=True)
    return _finish(o, name, mat)


def wedge(name, size, loc, mat=None, ridge_half=0.0, along_x=True):
    """Gable roof: a box whose top edge is pinched to a ridge. Ridge runs along X by default."""
    o = box(name, size, loc, mat)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    for v in bm.verts:
        if v.co.z > loc[2] + size[2] * 0.5 - 1e-4:
            if along_x:
                v.co.y = loc[1] + (ridge_half if v.co.y > loc[1] else -ridge_half)
            else:
                v.co.x = loc[0] + (ridge_half if v.co.x > loc[0] else -ridge_half)
    bm.to_mesh(o.data)
    bm.free()
    return o


def pyramid(name, size, loc, mat=None, top=0.0):
    """Hip / pyramid roof (top=0 for a point, >0 for a flat top)."""
    o = box(name, size, loc, mat)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    for v in bm.verts:
        if v.co.z > loc[2] + size[2] * 0.5 - 1e-4:
            v.co.x = loc[0] + math.copysign(top, v.co.x - loc[0])
            v.co.y = loc[1] + math.copysign(top, v.co.y - loc[1])
    bm.to_mesh(o.data)
    bm.free()
    return o


def arch(name, w, h, depth, loc, mat, rot_z=0.0):
    """Arched slab (round top). loc = base centre of the arch on the wall plane, depth along Y."""
    parts = [box(name + "_b", (w, depth, h - w / 2), loc, mat),
             cyl(name + "_t", w / 2, depth, (loc[0], loc[1] + depth / 2, loc[2] + h - w / 2), mat, verts=12, rot=(math.pi / 2, 0, 0))]
    # cyl() offsets z by h/2 -> undo: we passed h=depth so it moved z by depth/2; fix by setting location directly.
    parts[1].location = (loc[0], loc[1], loc[2] + h - w / 2)
    o = join(parts, name)
    if rot_z:
        # Meshes are in world coordinates (transform_apply bakes location in Blender 5.x), so rotate the
        # vertices about the arch's own base point rather than the object origin.
        bm = bmesh.new()
        bm.from_mesh(o.data)
        c, s = math.cos(rot_z), math.sin(rot_z)
        for v in bm.verts:
            dx, dy = v.co.x - loc[0], v.co.y - loc[1]
            v.co.x = loc[0] + dx * c - dy * s
            v.co.y = loc[1] + dx * s + dy * c
        bm.to_mesh(o.data)
        bm.free()
    return o


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


def export(name, visual, col=None, save_blend=False):
    if col is not None:
        col.name = name + "-col"
        col.parent = visual
        col.display_type = "WIRE"
    visual.name = name
    path = os.path.join(OUT, name + ".glb")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True)
    print("[assets] wrote", os.path.relpath(path, ROOT))
    if save_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "assets", "blender", name + ".blend"))


# ------------------------------------------------------------------ shared details
def window(parts, x, y_face, z, w=1.1, h=1.9, frame=M("stone") if False else None, sill=True, arched=False):
    """Window on a wall whose outer face is at y_face (facing -Y). Frame proud of the wall, dark glass, cross mullion."""
    fr = M("stone")
    parts.append(box("wf", (w + 0.2, 0.10, h + 0.2), (x, y_face - 0.05, z - 0.1), fr))
    parts.append(box("wg", (w, 0.06, h), (x, y_face - 0.13, z), M("glass", 0.3)))
    parts.append(box("wm_v", (0.06, 0.04, h), (x, y_face - 0.18, z), M("plaster_white")))
    parts.append(box("wm_h", (w, 0.04, 0.06), (x, y_face - 0.18, z + h * 0.55), M("plaster_white")))
    if sill:
        parts.append(box("ws", (w + 0.4, 0.22, 0.10), (x, y_face - 0.11, z - 0.2), fr))
    if arched:
        parts.append(arch("wa", w + 0.2, 0.45, 0.10, (x, y_face - 0.05, z + h + 0.05), fr))


def cornice(parts, w, d, z, t=0.25, proud=0.2, mat=None):
    parts.append(box("cornice", (w + proud * 2, d + proud * 2, t), (0, 0, z), mat or M("stone")))


# ------------------------------------------------------------------ TENEMENT (kamienica)
def tenement(name, width, storeys, roof, colour, bays=3, pilasters=False, rustic=True, arched_windows=False):
    reset()
    D = 8.0
    GF, FL = 4.2, 3.4                       # ground floor is taller (shops / entrance hall)
    body_h = GF + FL * (storeys - 1)
    plaster = M(colour)
    stone = M("stone")
    parts = []
    face = -D / 2

    # main mass
    parts.append(box("mass", (width, D, body_h), (0, 0, 0), plaster))

    # rusticated ground floor: proud band with horizontal grooves
    if rustic:
        parts.append(box("rustic", (width + 0.1, 0.12, GF - 0.3), (0, face - 0.06, 0), M("stone_dark")))
        for i in range(1, int((GF - 0.3) / 0.7)):
            parts.append(box("groove", (width + 0.1, 0.04, 0.06), (0, face - 0.14, i * 0.7), plaster))

    bay_w = width / bays
    xs = [-width / 2 + bay_w * (i + 0.5) for i in range(bays)]
    y_face = face - (0.12 if rustic else 0.0)

    # portal: arched doorway in centre bay (or leftmost for even bays), wooden double door
    px = xs[bays // 2] if bays % 2 else xs[0]
    parts.append(arch("portal_frame", 2.6, 3.4, 0.30, (px, face - 0.25, 0), stone))
    parts.append(arch("portal_door", 2.1, 3.1, 0.10, (px, face - 0.30, 0), M("wood_dark")))
    parts.append(box("door_split", (0.06, 0.04, 2.0), (px, face - 0.32, 0), M("iron")))
    parts.append(box("keystone", (0.4, 0.34, 0.6), (px, face - 0.25, 3.15), stone))

    # ground-floor shop windows in the other bays (small, high sill)
    for x in xs:
        if abs(x - px) < 0.1:
            continue
        window(parts, x, y_face, 1.3, w=1.3, h=1.8, arched=True)

    # upper floors
    for s in range(1, storeys):
        z0 = GF + FL * (s - 1)
        cornice(parts, width, D, z0 - 0.12, t=0.18, proud=0.12)
        for x in xs:
            window(parts, x, face, z0 + 0.9, arched=arched_windows and s == 1)
        if pilasters:
            for i in range(bays + 1):
                px_ = -width / 2 + bay_w * i
                px_ = max(min(px_, width / 2 - 0.25), -width / 2 + 0.25)
                parts.append(box("pil", (0.5, 0.14, FL - 0.3), (px_, face - 0.07, z0 + 0.1), M("plaster_white")))
                parts.append(box("pilcap", (0.7, 0.2, 0.2), (px_, face - 0.10, z0 + FL - 0.35), stone))

    # main cornice
    cornice(parts, width, D, body_h - 0.05, t=0.45, proud=0.35)
    top = body_h + 0.4

    if roof == "gable":
        parts.append(wedge("roof", (width + 0.5, D + 0.8, 4.2), (0, 0, top), M("tile"), ridge_half=0.15))
        parts.append(box("ridge", (width + 0.6, 0.5, 0.2), (0, 0, top + 4.15), M("tile_dark")))
        # dormers on the square side
        for x in xs[:: max(1, bays - 1)]:
            parts.append(box("dormer", (1.2, 1.4, 1.3), (x, face + 1.0, top + 0.9), plaster))
            parts.append(wedge("dormer_r", (1.5, 1.6, 0.8), (x, face + 1.0, top + 2.2), M("tile"), ridge_half=0.05, along_x=False))
            parts.append(box("dormer_w", (0.6, 0.06, 0.7), (x, face + 0.25, top + 1.15), M("glass", 0.3)))
        # chimney
        parts.append(box("chimney", (0.9, 0.9, 2.6), (width * 0.3, 1.5, top + 1.8), M("brick")))
        roof_top = top + 4.4
    elif roof == "attyka":
        # Polish Renaissance parapet hiding a low roof: solid wall, arched crenellations, pinnacles, small blind arcade.
        parts.append(box("attic_wall", (width + 0.2, D + 0.2, 2.2), (0, 0, top - 0.4), plaster))
        for x in xs:
            parts.append(arch("blind", bay_w * 0.55, 1.5, 0.12, (x, face - 0.10, top + 0.1), M("plaster_white")))
        n = max(2, int(width / 2.2))
        for i in range(n + 1):
            x = -width / 2 + (width / n) * i
            parts.append(box("pin", (0.45, 0.45, 0.9), (x, face + 0.25, top + 1.8), stone))
            parts.append(pyramid("pin_top", (0.55, 0.55, 0.6), (x, face + 0.25, top + 2.7), stone))
            parts.append(sphere("pin_ball", 0.18, (x, face + 0.25, top + 3.45), M("gold", 0.4), seg=8, rings=6))
        for i in range(n):
            x = -width / 2 + (width / n) * (i + 0.5)
            parts.append(cyl("cren", (width / n) * 0.42, 0.40, (x, face + 0.25, top + 1.8), stone, verts=10, rot=(math.pi / 2, 0, 0)))
            parts[-1].location = (x, face + 0.25, top + 1.8)
        parts.append(wedge("lowroof", (width, D - 1.0, 1.4), (0, 0.4, top + 1.6), M("tile_dark"), ridge_half=0.1))
        roof_top = top + 3.6
    else:  # mansard
        parts.append(wedge("mansard_lo", (width + 0.5, D + 0.8, 2.6), (0, 0, top), M("tile"), ridge_half=(D + 0.8) * 0.32))
        parts.append(wedge("mansard_hi", (width + 0.5, (D + 0.8) * 0.64, 1.8), (0, 0, top + 2.6), M("tile_dark"), ridge_half=0.15))
        for x in xs:
            parts.append(box("dormer", (1.0, 1.2, 1.2), (x, face + 1.1, top + 0.6), plaster))
            parts.append(box("dormer_w", (0.55, 0.06, 0.65), (x, face + 0.48, top + 0.85), M("glass", 0.3)))
            parts.append(box("dormer_cap", (1.3, 1.4, 0.15), (x, face + 1.1, top + 1.8), M("lead")))
        parts.append(box("chimney", (0.8, 0.8, 2.4), (-width * 0.3, 1.0, top + 2.2), M("brick")))
        roof_top = top + 4.4

    # snow dusting on cornice and roof ridge (winter 1795)
    parts.append(box("snow_c", (width + 0.7, D + 0.7, 0.08), (0, 0, body_h + 0.4), M("snow")))

    visual = join(parts, name)
    col = box("col", (width, D, roof_top), (0, 0, 0))
    export(name, visual, col)


# ------------------------------------------------------------------ SUKIENNICE (Cloth Hall, Renaissance state)
def sukiennice():
    reset()
    L, W, H = 34.0, 9.0, 8.0
    gap = 3.2                  # central cross passage, open at night
    stone = M("stone")
    plaster = M("plaster_cream")
    parts, col = [], []
    half = (L - gap) / 2
    for sx in (-1, 1):
        cx = sx * (gap / 2 + half / 2)
        parts.append(box("hall", (half, W, H), (cx, 0, 0), plaster))
        col.append(box("c", (half, W, H), (cx, 0, 0)))
        # tall arched windows along both long sides
        n = int(half / 3.4)
        for i in range(n):
            x = cx - half / 2 + half / n * (i + 0.5)
            for sy in (-1, 1):
                parts.append(arch("win", 1.4, 3.6, 0.12, (x, sy * W / 2 + (-0.06 if sy < 0 else 0.06), 3.0), M("glass", 0.3)))
                parts.append(arch("winf", 1.8, 3.9, 0.10, (x, sy * W / 2 + (-0.05 if sy < 0 else 0.05), 2.85), stone))
    # passage vault + roof over the gap
    parts.append(box("gap_roof", (gap + 0.4, W, 2.0), (0, 0, H - 2.0), plaster))
    parts.append(arch("gap_arch_s", gap, 6.2, 0.3, (0, -W / 2 - 0.15, 0), stone))
    parts.append(arch("gap_arch_n", gap, 6.2, 0.3, (0, W / 2 - 0.15, 0), stone))
    parts.append(arch("gap_void_s", gap - 0.5, 5.9, 0.35, (0, -W / 2 - 0.2, 0), M("glass", 0.5)))
    parts.append(arch("gap_void_n", gap - 0.5, 5.9, 0.35, (0, W / 2 - 0.15, 0), M("glass", 0.5)))
    col.append(box("c", (gap + 0.4, W, 2.0), (0, 0, H - 2.0)))

    # string course + attic (attyka): parapet wall, arched crenellations, pinnacles with balls, mascarons under arches
    cornice(parts, L, W, H - 0.1, t=0.35, proud=0.3)
    A0 = H + 0.25
    parts.append(box("attic", (L + 0.4, W + 0.4, 2.6), (0, 0, A0), plaster))
    n = 15
    step = L / n
    for i in range(n + 1):
        x = -L / 2 + step * i
        for sy in (-1, 1):
            y = sy * (W / 2 + 0.25)
            parts.append(box("pin", (0.5, 0.5, 1.6), (x, y, A0 + 2.2), stone))
            parts.append(pyramid("pin_top", (0.62, 0.62, 0.7), (x, y, A0 + 3.8), stone))
            parts.append(sphere("ball", 0.2, (x, y, A0 + 4.65), M("gold", 0.4), seg=8, rings=6))
    for i in range(n):
        x = -L / 2 + step * (i + 0.5)
        for sy in (-1, 1):
            y = sy * (W / 2 + 0.25)
            c = cyl("cren", step * 0.42, 0.5, (x, y, 0), stone, verts=12, rot=(math.pi / 2, 0, 0))
            c.location = (x, y, A0 + 2.6)
            parts.append(c)
            parts.append(sphere("mascaron", 0.28, (x, y - sy * 0.25, A0 + 1.5), M("stone_dark"), seg=8, rings=6, zscale=1.3))
    # low hidden roof
    parts.append(wedge("roof", (L - 0.5, W - 1.2, 2.2), (0, 0, A0 + 2.4), M("tile_dark"), ridge_half=0.1))

    # loggias at the short ends (Padovano): 3 arches on columns, 3 m deep, with a small balustrade above
    for sx in (-1, 1):
        x0 = sx * (L / 2 + 1.5)
        for j in range(4):
            y = -W / 2 + (W / 3) * j
            parts.append(cyl("colm", 0.35, 5.0, (x0 + sx * 1.2, y, 0), stone, verts=10))
            parts.append(box("colcap", (0.9, 0.9, 0.3), (x0 + sx * 1.2, y, 5.0), stone))
            col.append(box("c", (0.7, 0.7, 5.0), (x0 + sx * 1.2, y, 0)))
        parts.append(box("logroof", (3.2, W + 0.4, 0.8), (x0, 0, 5.3), stone))
        parts.append(box("logbal", (3.2, W + 0.4, 0.9), (x0, 0, 6.1), plaster))
        for j in range(3):
            y = -W / 2 + (W / 3) * (j + 0.5)
            parts.append(arch("logarch", W / 3 - 0.8, 1.9, 3.4, (x0, y, 3.4), M("glass", 0.5), rot_z=math.pi / 2))
        col.append(box("c", (3.2, W + 0.4, 1.7), (x0, 0, 5.3)))

    # kramy: wooden booths leaning on the long sides (cover)
    for sy in (-1, 1):
        for i in range(-2, 3):
            if i == 0:
                continue
            x = i * 6.0 + (1.5 if i < 0 else -1.5)
            y = sy * (W / 2 + 1.0)
            parts.append(box("kram", (3.0, 1.9, 2.4), (x, y, 0), M("wood")))
            parts.append(box("kram_roof", (3.4, 2.3, 0.15), (x, y, 2.4), M("wood_dark")))
            parts.append(box("kram_shut", (2.4, 0.08, 1.2), (x, y + sy * 1.0, 1.0), M("wood_dark")))
            col.append(box("c", (3.0, 1.9, 2.4), (x, y, 0)))

    parts.append(box("snow", (L + 0.6, W + 0.6, 0.08), (0, 0, H + 0.25), M("snow")))
    visual = join(parts, "sukiennice")
    export("sukiennice", visual, join(col, "col"))


# ------------------------------------------------------------------ ST MARY'S (Kosciol Mariacki), brick Gothic, two unequal towers
def st_marys():
    reset()
    brick = M("brick")
    bdark = M("brick_dark")
    stone = M("stone")
    parts, col = [], []
    NW, NL, NH = 14.0, 30.0, 18.0
    # nave, aisles lower, buttresses, steep roof, polygonal-ish apse at the back (+Y)
    parts.append(box("nave", (NW, NL, NH), (0, 2, 0), brick))
    col.append(box("c", (NW, NL, NH), (0, 2, 0)))
    for sx in (-1, 1):
        parts.append(box("aisle", (3.0, NL - 2, NH * 0.6), (sx * (NW / 2 + 1.5), 2, 0), brick))
        col.append(box("c", (3.0, NL - 2, NH * 0.6), (sx * (NW / 2 + 1.5), 2, 0)))
        parts.append(wedge("aisle_roof", (3.4, NL - 2, 2.0), (sx * (NW / 2 + 1.5), 2, NH * 0.6), M("tile"), ridge_half=1.6, along_x=False))
        for j in range(6):
            y = -NL / 2 + 2 + (NL - 2) / 5 * j + 2
            parts.append(box("buttress", (1.2, 1.0, NH * 0.62), (sx * (NW / 2 + 3.5), y, 0), bdark))
            col.append(box("c", (1.2, 1.0, NH * 0.62), (sx * (NW / 2 + 3.5), y, 0)))
        for j in range(5):
            y = -NL / 2 + 2 + (NL - 2) / 5 * (j + 0.5) + 2
            parts.append(arch("cw", 1.6, 5.5, 0.2, (sx * (NW / 2 + 0.05), y, NH * 0.6 + 1.2), M("glass", 0.3), rot_z=math.pi / 2))
    parts.append(wedge("roof", (NW + 0.6, NL, 9.0), (0, 2, NH), M("tile_dark"), ridge_half=0.1))
    parts.append(cyl("apse", NW / 2 - 1, NH - 3, (0, NL / 2 + 2, 0), brick, verts=8))
    col.append(cyl("c", NW / 2 - 1, NH - 3, (0, NL / 2 + 2, 0), None, verts=8))
    parts.append(cyl("apse_roof", NW / 2 - 0.8, 5, (0, NL / 2 + 2, NH - 3), M("tile_dark"), verts=8, r2=0.2))

    # towers at the front (-Y). North tower (taller, Gothic spire with crown) on the left (-X), south tower with Renaissance cupola.
    front = -NL / 2 + 2
    # north
    x = -NW / 2 + 1.5
    parts.append(box("tn", (6.0, 6.0, 30.0), (x, front - 1.0, 0), brick))
    col.append(box("c", (6.0, 6.0, 30.0), (x, front - 1.0, 0)))
    parts.append(cyl("tn_oct", 3.4, 7.0, (x, front - 1.0, 30.0), brick, verts=8))
    for k in range(8):
        a = math.tau * k / 8
        parts.append(box("tn_pin", (0.5, 0.5, 2.0), (x + 3.3 * math.cos(a), front - 1.0 + 3.3 * math.sin(a), 36.0), stone))
        parts.append(pyramid("tn_pintop", (0.6, 0.6, 1.0), (x + 3.3 * math.cos(a), front - 1.0 + 3.3 * math.sin(a), 38.0), stone))
    parts.append(cyl("tn_spire", 3.0, 13.0, (x, front - 1.0, 37.0), M("lead", 0.5), verts=8, r2=0.05))
    parts.append(cyl("tn_crown", 2.3, 0.5, (x, front - 1.0, 40.5), M("gold", 0.35), verts=8, r2=2.5))
    for k in range(8):
        a = math.tau * k / 8
        parts.append(box("tn_crownpt", (0.35, 0.35, 0.9), (x + 2.2 * math.cos(a), front - 1.0 + 2.2 * math.sin(a), 41.0), M("gold", 0.35)))
    for k in range(4):
        a = math.tau * k / 4 + math.pi / 4
        parts.append(cyl("tn_turret", 0.6, 4.0, (x + 3.6 * math.cos(a), front - 1.0 + 3.6 * math.sin(a), 34.5), M("lead", 0.5), verts=6, r2=0.02))
    for zz in (8, 16, 24):
        parts.append(arch("tn_w", 1.4, 4.0, 0.2, (x, front - 4.05, zz), M("glass", 0.3)))
    # south
    x = NW / 2 - 1.5
    parts.append(box("ts", (6.0, 6.0, 25.0), (x, front - 1.0, 0), brick))
    col.append(box("c", (6.0, 6.0, 25.0), (x, front - 1.0, 0)))
    parts.append(cyl("ts_drum", 3.2, 2.5, (x, front - 1.0, 25.0), stone, verts=12))
    parts.append(sphere("ts_dome", 3.4, (x, front - 1.0, 27.5), M("copper", 0.5), seg=12, rings=8, zscale=0.9))
    parts.append(cyl("ts_lantern", 1.0, 2.5, (x, front - 1.0, 30.3), stone, verts=8))
    parts.append(cyl("ts_lantop", 1.2, 1.6, (x, front - 1.0, 32.8), M("copper", 0.5), verts=8, r2=0.05))
    parts.append(box("ts_clock", (2.4, 0.2, 2.4), (x, front - 4.05, 20.0), M("plaster_white")))
    for zz in (8, 14):
        parts.append(arch("ts_w", 1.4, 4.0, 0.2, (x, front - 4.05, zz), M("glass", 0.3)))
    # great west portal + rose-ish window between the towers
    parts.append(arch("portal", 4.0, 7.5, 0.6, (0, front - 0.3, 0), stone))
    parts.append(arch("door", 3.2, 6.8, 0.3, (0, front - 0.45, 0), M("wood_dark")))
    parts.append(cyl("rose", 2.6, 0.3, (0, front - 0.15, 0), M("glass", 0.3), verts=12, rot=(math.pi / 2, 0, 0)))
    parts[-1].location = (0, front - 0.15, 12.5)
    parts.append(wedge("gable", (NW + 0.6, 1.0, 9.0), (0, front + 0.5, NH), bdark, ridge_half=0.1))
    parts.append(box("snow", (NW + 0.8, NL, 0.08), (0, 2, NH + 0.02), M("snow")))

    visual = join(parts, "st_marys")
    export("st_marys", visual, join(col, "col"))


# ------------------------------------------------------------------ TOWN HALL TOWER (Ratusz, as it stood before 1820)
def town_hall():
    reset()
    parts, col = [], []
    brick = M("brick")
    stone = M("stone")
    # the hall itself (stylised, low, attached to the tower) and the tall tower
    parts.append(box("hall", (16.0, 8.0, 9.0), (-9.0, 0, 0), M("plaster_white")))
    col.append(box("c", (16.0, 8.0, 9.0), (-9.0, 0, 0)))
    parts.append(wedge("hall_roof", (16.5, 8.6, 4.0), (-9.0, 0, 9.0), M("tile"), ridge_half=0.1))
    for i in range(4):
        x = -15.5 + 4.0 * i
        window(parts, x, -4.0, 1.5, w=1.2, h=2.0, arched=True)
        window(parts, x, -4.0, 5.5, w=1.2, h=2.0)
    parts.append(box("tower", (7.0, 7.0, 24.0), (0, 0, 0), brick))
    col.append(box("c", (7.0, 7.0, 24.0), (0, 0, 0)))
    parts.append(box("tower_base", (7.6, 7.6, 3.0), (0, 0, 0), stone))
    for zz in (6, 12, 18):
        parts.append(arch("tw", 1.2, 3.0, 0.2, (0, -3.55, zz), M("glass", 0.3)))
    # clock faces on all four sides
    for k in range(4):
        a = math.tau * k / 4
        cx, cy = 3.55 * math.sin(a), -3.55 * math.cos(a)
        c = cyl("clock", 1.4, 0.2, (cx, cy, 0), M("plaster_white"), verts=16, rot=(math.pi / 2, 0, a))
        c.location = (cx, cy, 20.5)
        parts.append(c)
    parts.append(arch("tdoor", 2.2, 3.6, 0.5, (0, -3.6, 0), stone))
    parts.append(arch("tdoor_in", 1.7, 3.2, 0.3, (0, -3.7, 0), M("wood_dark")))
    # baroque cupola: octagonal drum, onion dome, lantern, spike with ball
    parts.append(cyl("drum", 3.6, 3.0, (0, 0, 24.0), stone, verts=8))
    parts.append(sphere("onion", 3.6, (0, 0, 28.5), M("copper", 0.5), seg=12, rings=10, zscale=1.15))
    parts.append(cyl("onion_neck", 1.3, 2.0, (0, 0, 31.8), stone, verts=8))
    parts.append(sphere("onion2", 1.6, (0, 0, 34.5), M("copper", 0.5), seg=10, rings=8, zscale=1.2))
    parts.append(cyl("spike", 0.15, 3.0, (0, 0, 36.0), M("gold", 0.4), verts=6, r2=0.02))
    parts.append(sphere("ball", 0.45, (0, 0, 37.5), M("gold", 0.4), seg=8, rings=6))
    parts.append(box("snow", (7.4, 7.4, 0.08), (0, 0, 24.0), M("snow")))
    visual = join(parts, "town_hall")
    export("town_hall", visual, join(col, "col"))


# ------------------------------------------------------------------ ST ADALBERT'S (tiny Romanesque church, baroque dome)
def st_adalbert():
    reset()
    parts, col = [], []
    parts.append(box("body", (7.0, 7.0, 5.0), (0, 0, 0), M("plaster_white")))
    col.append(box("c", (7.0, 7.0, 5.0), (0, 0, 0)))
    parts.append(box("base", (7.4, 7.4, 1.0), (0, 0, 0), M("stone_dark")))
    parts.append(cyl("drum", 3.6, 2.2, (0, 0, 5.0), M("plaster_white"), verts=12))
    parts.append(sphere("dome", 3.7, (0, 0, 7.4), M("copper", 0.5), seg=12, rings=8, zscale=0.85))
    parts.append(cyl("lantern", 0.9, 1.6, (0, 0, 10.3), M("plaster_white"), verts=8))
    parts.append(cyl("lantop", 1.1, 1.2, (0, 0, 11.9), M("copper", 0.5), verts=8, r2=0.03))
    parts.append(arch("door", 1.6, 2.6, 0.3, (0, -3.55, 0), M("wood_dark")))
    for sx in (-1, 1):
        parts.append(arch("w", 0.7, 1.6, 0.2, (sx * 2.3, -3.55, 2.2), M("glass", 0.3)))
    parts.append(box("snow", (7.2, 7.2, 0.08), (0, 0, 5.0), M("snow")))
    visual = join(parts, "st_adalbert")
    export("st_adalbert", visual, join(col, "col"))


# ------------------------------------------------------------------ street furniture
def market_stall():
    reset()
    parts = [box("counter", (2.4, 1.2, 1.1), (0, 0, 0), M("wood")),
             box("counter_top", (2.6, 1.4, 0.08), (0, 0, 1.1), M("wood_dark"))]
    for x in (-1.15, 1.15):
        for y in (-0.55, 0.55):
            parts.append(box("post", (0.1, 0.1, 2.4), (x, y, 0), M("wood_dark")))
    parts.append(wedge("awning", (2.9, 1.8, 0.6), (0, 0, 2.3), M("canvas"), ridge_half=0.05))
    for i in range(3):
        parts.append(box("stripe", (0.3, 1.82, 0.02), (-0.9 + i * 0.9, 0, 2.31), M("canvas_stripe")))
    parts.append(box("sack", (0.5, 0.4, 0.4), (-0.7, 0.1, 1.18), M("canvas")))
    parts.append(box("crate", (0.6, 0.45, 0.35), (0.6, 0.1, 1.18), M("wood_dark")))
    export("market_stall", join(parts, "market_stall"), box("c", (2.4, 1.2, 1.1), (0, 0, 0)))


def barrel():
    reset()
    parts = [cyl("body", 0.42, 1.0, (0, 0, 0), M("wood"), verts=12, r2=0.42)]
    parts.append(cyl("bulge", 0.46, 0.5, (0, 0, 0.25), M("wood"), verts=12))
    for z in (0.12, 0.82):
        parts.append(cyl("hoop", 0.47, 0.06, (0, 0, z), M("iron", 0.5), verts=12))
    export("barrel", join(parts, "barrel"), cyl("c", 0.47, 1.0, (0, 0, 0), None, verts=8))


def crate_stack():
    reset()
    parts = [box("c1", (1.0, 0.8, 0.6), (0, 0, 0), M("wood")),
             box("c2", (0.8, 0.8, 0.5), (0.1, 0.05, 0.6), M("wood_dark")),
             box("c3", (0.9, 0.7, 0.55), (1.0, 0.1, 0), M("wood"))]
    for o in parts:
        pass
    export("crate_stack", join(parts, "crate_stack"), box("c", (2.0, 0.9, 1.1), (0.5, 0, 0)))


def cart():
    reset()
    wood, dark = M("wood"), M("wood_dark")
    parts = [box("bed", (1.2, 2.2, 0.15), (0, 0, 0.6), wood)]
    for sx in (-1, 1):
        parts.append(box("side", (0.08, 2.2, 0.5), (sx * 0.6, 0, 0.75), wood))
        w = cyl("wheel", 0.6, 0.1, (0, 0, 0), dark, verts=12, rot=(0, math.pi / 2, 0))
        w.location = (sx * 0.72, -0.2, 0.6)
        parts.append(w)
        parts.append(box("shaft", (0.08, 1.6, 0.08), (sx * 0.4, 1.7, 0.5), dark))
    parts.append(box("back", (1.2, 0.08, 0.5), (0, -1.1, 0.75), wood))
    parts.append(box("axle", (1.6, 0.1, 0.1), (0, -0.2, 0.55), dark))
    parts.append(box("load", (0.9, 1.4, 0.5), (0, -0.1, 0.75), M("canvas")))
    export("cart", join(parts, "cart"), box("c", (1.5, 2.4, 1.25), (0, 0, 0)))


def well():
    reset()
    stone = M("stone_dark")
    parts = [cyl("rim", 1.3, 1.0, (0, 0, 0), stone, verts=8),
             cyl("hole", 1.0, 0.05, (0, 0, 1.0), M("glass", 0.4), verts=8)]
    for sx in (-1, 1):
        parts.append(box("post", (0.15, 0.15, 2.4), (sx * 1.1, 0, 1.0), M("wood_dark")))
    parts.append(box("beam", (2.6, 0.15, 0.15), (0, 0, 3.3), M("wood_dark")))
    parts.append(wedge("wroof", (3.0, 1.6, 0.8), (0, 0, 3.45), M("tile_dark"), ridge_half=0.05))
    parts.append(cyl("windlass", 0.12, 2.0, (0, 0, 0), M("wood"), verts=8, rot=(0, math.pi / 2, 0)))
    parts[-1].location = (0, 0, 2.9)
    parts.append(box("bucket", (0.3, 0.3, 0.3), (0, 0, 1.6), M("wood")))
    parts.append(cyl("snowcap", 1.35, 0.08, (0, 0, 1.0), M("snow"), verts=8))
    export("well", join(parts, "well"), cyl("c", 1.3, 1.0, (0, 0, 0), None, verts=8))


def lantern_post():
    """Oil lantern on a wooden post with an iron bracket, as lit by the city from the 1770s."""
    reset()
    iron = M("iron", 0.6)
    parts = [box("post", (0.18, 0.18, 3.6), (0, 0, 0), M("wood_dark")),
             box("post_cap", (0.26, 0.26, 0.1), (0, 0, 3.6), iron),
             box("arm", (0.9, 0.05, 0.05), (0.4, 0, 3.35), iron),
             box("brace", (0.05, 0.05, 0.7), (0.75, 0, 2.7), iron),
             box("cage", (0.36, 0.36, 0.5), (0.8, 0, 2.55), iron),
             box("glow", (0.28, 0.28, 0.42), (0.8, 0, 2.59), M("gold", 0.3, emit=(1.0, 0.72, 0.35), emit_strength=6.0)),
             pyramid("cap", (0.46, 0.46, 0.25), (0.8, 0, 3.05), iron)]
    for s in (-1, 1):
        parts.append(box("bar", (0.03, 0.4, 0.5), (0.8 + s * 0.17, 0, 2.55), iron))
        parts.append(box("bar2", (0.4, 0.03, 0.5), (0.8, s * 0.17, 2.55), iron))
    export("lantern_post", join(parts, "lantern_post"), box("c", (0.2, 0.2, 3.6), (0, 0, 0)))


# ------------------------------------------------------------------ FIGURES (front = +Y)
def humanoid(name, coat, hat, breeches="black", coat_len="short", cuffs=None, sash=None, boots="black",
             hair=True, beard=False, musket=False, collar=None):
    reset()
    parts = []
    C = M(coat)
    # legs & boots
    for sx in (-1, 1):
        parts.append(box("leg", (0.17, 0.2, 0.55), (sx * 0.11, 0, 0.32), M(breeches)))
        parts.append(box("boot", (0.19, 0.24, 0.34), (sx * 0.11, 0.02, 0), M(boots)))
    # torso and coat skirt
    parts.append(box("torso", (0.50, 0.30, 0.72), (0, 0, 0.84), C))
    if coat_len == "long":
        parts.append(box("skirt", (0.56, 0.36, 0.55), (0, 0, 0.32), C))
    elif coat_len == "mid":
        parts.append(box("skirt", (0.54, 0.34, 0.30), (0, 0, 0.56), C))
    if collar:
        parts.append(box("collar", (0.30, 0.34, 0.08), (0, 0, 1.50), M(collar)))
    if sash:
        parts.append(box("sash", (0.53, 0.33, 0.14), (0, 0, 0.80), M(sash)))
    # arms with cuffs
    for sx in (-1, 1):
        parts.append(box("arm", (0.14, 0.14, 0.60), (sx * 0.33, 0, 0.92), C))
        if cuffs:
            parts.append(box("cuff", (0.16, 0.16, 0.12), (sx * 0.33, 0, 0.92), M(cuffs)))
        parts.append(box("hand", (0.11, 0.11, 0.12), (sx * 0.33, 0, 0.80), M("skin")))
    # head
    parts.append(box("head", (0.24, 0.24, 0.26), (0, 0, 1.56), M("skin")))
    if hair:
        parts.append(box("hair", (0.26, 0.14, 0.24), (0, -0.07, 1.60), M("hair")))
    if beard:
        parts.append(box("beard", (0.20, 0.06, 0.14), (0, 0.13, 1.52), M("hair")))
    # hats
    if hat == "tricorne":
        b = cyl("brim", 0.34, 0.05, (0, 0, 1.80), M("black"), verts=3, rot=(0, 0, math.pi / 2))
        parts.append(b)
        parts.append(cyl("crown", 0.14, 0.13, (0, 0, 1.82), M("black"), verts=8))
    elif hat == "konfederatka":
        parts.append(box("fur", (0.32, 0.32, 0.08), (0, 0, 1.78), M("hair")))
        parts.append(box("cap", (0.30, 0.30, 0.16), (0, 0, 1.86), M("crimson")))
    elif hat == "krakuska":
        parts.append(box("band", (0.30, 0.30, 0.06), (0, 0, 1.80), M("black")))
        parts.append(box("cap", (0.28, 0.28, 0.14), (0, 0, 1.86), M("red_cap")))
        parts.append(box("feather", (0.03, 0.03, 0.42), (0.13, -0.05, 1.86), M("feather"), rot=(0, -0.35, 0)))
    elif hat == "biretta":
        parts.append(box("cap", (0.26, 0.26, 0.12), (0, 0, 1.80), M("black")))
        parts.append(box("ridge", (0.04, 0.26, 0.06), (0, 0, 1.92), M("black")))
    elif hat == "round":
        parts.append(cyl("brim", 0.24, 0.03, (0, 0, 1.80), M("black"), verts=10))
        parts.append(cyl("crown", 0.14, 0.15, (0, 0, 1.82), M("black"), verts=10))
    elif hat == "fur":
        parts.append(cyl("furhat", 0.18, 0.17, (0, 0, 1.80), M("hair"), verts=10))
    if musket:
        parts.append(box("stock", (0.05, 0.06, 0.9), (0.42, 0.02, 0.65), M("wood_dark")))
        parts.append(box("barrel", (0.035, 0.035, 1.0), (0.42, 0.02, 1.45), M("lead", 0.4)))
        parts.append(box("cartridge", (0.22, 0.10, 0.16), (-0.2, -0.18, 0.72), M("black")))
        parts.append(box("belt", (0.08, 0.32, 0.72), (-0.1, 0, 0.84), M("plaster_white")))
    export(name, join(parts, name))


def figures():
    # Austrian infantry, 1795: white coat, red facings, black tricorne, black gaiters, musket at the shoulder.
    humanoid("watchman", "white_coat", "tricorne", breeches="plaster_white", coat_len="mid", cuffs="facing_red",
             collar="facing_red", boots="black", hair=False, musket=True)
    # Origins
    humanoid("figure_noble", "crimson", "konfederatka", breeches="zupan_gold", coat_len="long", sash="zupan_gold", boots="brown_coat", collar="zupan_gold")
    humanoid("figure_artist", "green_coat", "round", breeches="brown_coat", coat_len="mid", cuffs="brown_coat", collar="plaster_white")
    humanoid("figure_veteran", "sukmana", "krakuska", breeches="brown_coat", coat_len="long", sash="facing_red", boots="black", cuffs="facing_red")
    humanoid("figure_merchant", "brown_coat", "tricorne", breeches="black", coat_len="mid", cuffs="zupan_gold", collar="plaster_white")
    humanoid("figure_priest", "black", "biretta", breeches="black", coat_len="long", collar="plaster_white")
    humanoid("figure_kazimierz", "navy", "fur", breeches="black", coat_len="long", beard=True)
    # generic townsfolk for later crowds
    humanoid("figure_townsman", "brown_coat", "round", breeches="brown_coat", coat_len="mid")
    humanoid("figure_townswoman", "plaster_sage", None, breeches="plaster_sage", coat_len="long", collar="plaster_white")


# ------------------------------------------------------------------ main
if __name__ == "__main__":
    random.seed(1795)
    tenement("tenement_a", 10.0, 3, "gable", "plaster_ochre", bays=3)
    tenement("tenement_b", 8.0, 3, "attyka", "plaster_rose", bays=2)
    tenement("tenement_c", 12.0, 4, "mansard", "plaster_cream", bays=3, pilasters=True, arched_windows=True)
    tenement("tenement_d", 10.0, 3, "attyka", "plaster_sage", bays=3, arched_windows=True)
    tenement("tenement_e", 8.0, 4, "gable", "plaster_blue", bays=2)
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
    figures()
    print("[assets] done")
