"""Lifelike characters for Krakow 1795, built on the MakeHuman base mesh via the MPFB2 Blender add-on.

Run:  blender -b --python assets/blender/build_characters.py
Needs: MPFB extension installed and the MakeHuman system assets pack (CC0) extracted into MPFB's user data.

Each character: parametric body (macro sliders + face targets), skin texture, eyes, brows, lashes, teeth,
hair, then era clothing cut from MakeHuman's body-conforming helper geometry (so it never clips), a cocked
hat or a cap built on the scalp helper, a game-engine skeleton, an arms-down rest pose, and idle/walk
animations. Exported as glTF with textures for Godot. Front faces Godot +Z (Assets.character turns it).
"""
import bpy
import bmesh
import math
import os
import random
import sys
from mathutils import Matrix, Vector

from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.locationservice import LocationService
from bl_ext.user_default.mpfb.services.targetservice import TargetService

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "models")
USER = LocationService.get_user_data()
TARGETS = os.path.join(LocationService.get_mpfb_data(), "targets")
os.makedirs(OUT, exist_ok=True)

COL = {
    "white_coat": (0.90, 0.90, 0.92), "facing_red": (0.62, 0.10, 0.12), "black": (0.05, 0.05, 0.06),
    "crimson": (0.52, 0.08, 0.14), "zupan_gold": (0.80, 0.62, 0.26), "sukmana": (0.82, 0.78, 0.66),
    "red_cap": (0.72, 0.10, 0.10), "green_coat": (0.13, 0.28, 0.20), "brown_coat": (0.34, 0.22, 0.12),
    "navy": (0.12, 0.15, 0.30), "feather": (0.10, 0.45, 0.35), "cream": (0.90, 0.86, 0.72),
    "stocking": (0.86, 0.84, 0.78), "leather": (0.22, 0.14, 0.08), "tan_boot": (0.48, 0.32, 0.16),
    "fur": (0.20, 0.13, 0.08), "sage": (0.50, 0.58, 0.40), "grey": (0.45, 0.45, 0.47), "buff": (0.78, 0.68, 0.50),
    "steel": (0.55, 0.56, 0.60), "wood": (0.30, 0.18, 0.09), "wood_dark": (0.20, 0.12, 0.06), "brass": (0.80, 0.62, 0.25), "pewter": (0.50, 0.50, 0.52),
    "wimple": (0.95, 0.94, 0.90), "veil": (0.04, 0.04, 0.05), "apron": (0.88, 0.86, 0.80), "kerchief_red": (0.70, 0.12, 0.14),
    "dress_blue": (0.22, 0.30, 0.48), "dress_green": (0.20, 0.36, 0.28), "dress_plum": (0.40, 0.14, 0.26),
    "purple": (0.36, 0.10, 0.40), "grey_coat": (0.36, 0.36, 0.38), "charcoal": (0.16, 0.16, 0.18), "olive": (0.30, 0.32, 0.18),
    "rust": (0.52, 0.24, 0.12), "mustard": (0.68, 0.52, 0.18), "teal": (0.14, 0.34, 0.36), "wine": (0.38, 0.10, 0.14),
    "livery_blue": (0.16, 0.26, 0.56), "rope": (0.62, 0.54, 0.38), "silver": (0.75, 0.76, 0.78),
    "flour": (0.84, 0.82, 0.76), "indigo": (0.14, 0.16, 0.34), "ochre_cloth": (0.62, 0.46, 0.20), "grey_white": (0.68, 0.68, 0.65),
    "saffron": (0.84, 0.58, 0.12), "madder": (0.60, 0.17, 0.11), "ottoman_green": (0.10, 0.34, 0.25), "sky_blue": (0.42, 0.56, 0.72),
    "hops": (0.46, 0.50, 0.24), "dun": (0.52, 0.46, 0.36),
}
HAIR_TINTS = {"black": (0.10, 0.08, 0.08), "dark_brown": (0.45, 0.32, 0.24), "brown": (0.85, 0.66, 0.48), "auburn": (0.95, 0.45, 0.25),
              "blond": (1.25, 1.10, 0.80), "grey": (1.05, 1.05, 1.05), "white": (1.6, 1.55, 1.5), "red": (1.05, 0.40, 0.22)}
HAIR_BLEND = {"grey": ((0.55, 0.55, 0.56), 0.75), "white": ((0.92, 0.90, 0.86), 0.85), "blond": ((0.85, 0.72, 0.42), 0.5)}   # (colour, amount)
CURRENT = {"hair_tint": None}
_mats = {}
_CLOTH_PATHS = None
NOT_CLOTH = {"steel", "pewter", "brass", "silver", "wood", "wood_dark", "leather", "black", "iron", "skin", "eye", "hair"}


def _cloth_textures():
    """Baked wool broadcloth (colour, roughness, normal with drape folds) from build_assets.py, cached on disk."""
    global _CLOTH_PATHS
    if _CLOTH_PATHS is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("ba", os.path.join(ROOT, "assets", "blender", "build_assets.py"))
        ba = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ba)
        _CLOTH_PATHS = ba.bake_texture("cloth")
    return _CLOTH_PATHS


def M(key, rough=0.85):
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new("cloth_" + key)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = rough
    if key in NOT_CLOTH or key not in COL:
        b.inputs["Base Color"].default_value = (*COL.get(key, (0.5, 0.5, 0.5)), 1.0)
    else:
        paths = _cloth_textures()
        def img(p, colour):
            im = bpy.data.images.load(p, check_existing=True)
            im.colorspace_settings.name = "sRGB" if colour else "Non-Color"
            return im
        tc = nt.nodes.new("ShaderNodeTexImage"); tc.image = img(paths["col"], True)
        tr = nt.nodes.new("ShaderNodeTexImage"); tr.image = img(paths["rough"], False)
        tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = img(paths["nrm"], False)
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        nt.links.new(tc.outputs["Color"], mix.inputs[6])
        mix.inputs[7].default_value = (*COL[key], 1.0)
        nt.links.new(mix.outputs[2], b.inputs["Base Color"])
        nt.links.new(tr.outputs["Color"], b.inputs["Roughness"])
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = 1.0
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    _mats[key] = m
    return m


def unwrap(o, repeat=0.55):
    """Smart-project UVs and scale them so one texture repeat covers about `repeat` metres."""
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.cube_project(cube_size=repeat, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def log(*a):
    print("[char]", *a)


# ------------------------------------------------------------------ body
def make_body(spec):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mats.clear()
    macro = {"gender": 0.5, "age": 0.5, "muscle": 0.5, "weight": 0.5, "proportions": 0.5, "height": 0.5,
             "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.05, "caucasian": 0.9, "african": 0.05}}
    macro.update(spec.get("macro", {}))
    h = HumanService.create_human(scale=0.1, feet_on_ground=True, macro_detail_dict=macro)
    female = macro.get("gender", 0.5) < 0.5
    if female:
        targets = {"head-scale-vert-decr": 0.25, "chin-height-decr": 0.10, "chin-width-decr": 0.25, "head-oval": 0.25,
                   "nose-scale-vert-decr": 0.15, "nose-point-width-decr": 0.15, "chin-prominent-decr": 0.15}
    else:
        targets = {"head-scale-vert-decr": 0.30, "head-scale-horiz-incr": 0.12, "chin-height-decr": 0.15, "head-scale-depth-incr": 0.08}
    targets.update(spec.get("targets", {}))
    for tname, w in targets.items():
        group = tname.split("-")[0]
        path = os.path.join(TARGETS, group, tname + ".target.gz")
        if os.path.exists(path):
            TargetService.load_target(h, path, weight=w)
        else:
            log("missing target", tname)
    return h


def add(h, sub, name, atype, mat="MAKESKIN"):
    p = os.path.join(USER, sub, name, name + ".mhclo")
    if not os.path.exists(p):
        log("missing asset", p)
        return None
    o = HumanService.add_mhclo_asset(p, h, asset_type=atype, subdiv_levels=0, material_type=mat)
    return o


# ------------------------------------------------------------------ garments from helper geometry
def snapshot(h):
    """Evaluated copy of the basemesh with shape keys applied and helpers unmasked. Keeps vertex groups."""
    mask = [m for m in h.modifiers if m.type == "MASK"]
    arm = [m for m in h.modifiers if m.type == "ARMATURE"]
    for m in mask + arm:
        m.show_viewport = False
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(h.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    for m in mask + arm:
        m.show_viewport = True
    return me


def face_info(h, me, rig):
    """Per face: centre, averaged group weights, majority dominant bone. Garments are cut per face so
    every helper face lands in exactly one garment and there are no gaps at boundaries."""
    names = [g.name for g in h.vertex_groups]
    bones = set(b.name for b in rig.data.bones)
    vinfo = []
    for v in me.vertices:
        groups = {names[g.group]: g.weight for g in v.groups}
        dom = max(((w, n) for n, w in groups.items() if n in bones), default=(0, None))[1]
        vinfo.append((groups, dom))
    info = []
    for f in me.polygons:
        groups = {}
        doms = {}
        for vi in f.vertices:
            g, d = vinfo[vi]
            for n, w in g.items():
                groups[n] = groups.get(n, 0) + w / len(f.vertices)
            doms[d] = doms.get(d, 0) + 1
        dom = max(doms.items(), key=lambda kv: kv[1])[0]
        info.append((Vector(f.center), groups, dom))
    return info


SOFTEN = {"coat": (4, 0.6), "coat_skirt": (3, 0.5), "skirt": (4, 0.6), "breeches": (3, 0.5), "stockings": (1, 0.3), "cuffs": (1, 0.3)}


def garment(h, rig, me, info, name, keep_fn, mat, thickness=0.012, smooth=True, offset=0.0):
    """Cut a garment out of the helper geometry: keep faces passing keep_fn, thicken, rig with body weights."""
    mesh = me.copy()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for g in h.vertex_groups:
        obj.vertex_groups.new(name=g.name)
    keep = [keep_fn(i, *info[i]) for i in range(len(mesh.polygons))]
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    dead_faces = [f for f in bm.faces if not keep[f.index]]
    bmesh.ops.delete(bm, geom=dead_faces, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    # smooth the cut edge so hems and collars are not sawtoothed
    bm.verts.ensure_lookup_table()
    for _ in range(3):
        moves = {}
        for v in bm.verts:
            if not v.is_boundary:
                continue
            nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(nb) >= 2:
                avg = sum((n.co for n in nb), Vector((0, 0, 0))) / len(nb)
                moves[v] = v.co.lerp(avg, 0.5)
        for v, co in moves.items():
            v.co = co
    bm.to_mesh(mesh)
    bm.free()
    if len(mesh.polygons) == 0:
        bpy.data.objects.remove(obj)
        return None
    mesh.materials.clear()
    mesh.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if name in SOFTEN:
        it, fac = SOFTEN[name]
        sm = obj.modifiers.new("soften", "SMOOTH")
        sm.iterations = it
        sm.factor = fac
        bpy.ops.object.modifier_apply(modifier="soften")
        offset = max(offset, 0.5)
        thickness += 0.006
    sol = obj.modifiers.new("solid", "SOLIDIFY")
    sol.thickness = thickness + 0.014
    sol.offset = offset       # 0 = both sides of the helper surface (robust to inward normals); >0 pushes outward
    sol.use_even_offset = False
    sol.thickness_clamp = 1.0
    sol.use_rim = True
    bpy.ops.object.modifier_apply(modifier="solid")
    if smooth:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(60))
    unwrap(obj)
    am = obj.modifiers.new("arm", "ARMATURE")
    am.object = rig
    obj.parent = rig
    return obj


def skin_points(h, me, rig=None):
    """Real skin vertices (no helpers, no joint cubes) as (position, dominant bone)."""
    names = [g.name for g in h.vertex_groups]
    bones = set(b.name for b in rig.data.bones) if rig else set()
    pts = []
    for v in me.vertices:
        g = {names[x.group]: x.weight for x in v.groups}
        if g.get("body", 0) > 0.5 and g.get("JointCubes", 0) < 0.01 and g.get("HelperGeometry", 0) < 0.01 and g.get("helper-hair", 0) < 0.01:
            dom = max(((w, nm) for nm, w in g.items() if nm in bones), default=(0, None))[1]
            pts.append((v.co.copy(), dom))
    return pts


def silhouette_ring(pts, z, pad, n=32, slab=0.02, side=0, bones=None):
    """Polygon hugging the body's outline at height z, using only vertices of the given bones
    (so arms hanging beside the waist do not widen a sash)."""
    def ok(p, d, sl_):
        return abs(p.z - z) < sl_ and (side == 0 or p.x * side > 0.02) and (bones is None or d in bones)
    sl = [p for (p, d) in pts if ok(p, d, slab)]
    if len(sl) < 8:
        sl = [p for (p, d) in pts if ok(p, d, slab * 3)]
    cx = sum(p.x for p in sl) / len(sl)
    cy = sum(p.y for p in sl) / len(sl)
    ring = []
    for k in range(n):
        a = math.tau * k / n
        dx, dy = math.cos(a), math.sin(a)
        best = 0.0
        for p in sl:
            rx, ry = p.x - cx, p.y - cy
            d = rx * dx + ry * dy
            if d > best and abs(rx * dy - ry * dx) < 0.06:
                best = d
        ring.append((cx + dx * (best + pad), cy + dy * (best + pad), z))
    return ring


def band(name, pts, z0, z1, pad, mat, rig, bone, thickness=0.02, n=32, side=0, extra_top=0.0, bones=None):
    """A cloth band (sash, hat band, boot top) as a lofted ring between two heights, welded to one bone."""
    r0 = silhouette_ring(pts, z0, pad, n, side=side, bones=bones)
    r1 = silhouette_ring(pts, z1, pad + extra_top, n, side=side, bones=bones)
    bm = bmesh.new()
    v0 = [bm.verts.new(p) for p in r0]
    v1 = [bm.verts.new(p) for p in r1]
    for i in range(n):
        bm.faces.new((v0[i], v0[(i + 1) % n], v1[(i + 1) % n], v1[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    me.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    sol = o.modifiers.new("solid", "SOLIDIFY")
    sol.thickness = thickness
    sol.offset = 0.0
    sol.use_rim = True
    bpy.ops.object.modifier_apply(modifier="solid")
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))
    unwrap(o, 0.4)
    _weight_to_bone(o, rig, bone)
    return o


def apron_panel(pts, rig, waist_z, knee_z, mat, bones, pad=0.03, bones_by_z=None, half_w=0.17):
    """Flat cloth panel hanging from the waist in front of the body (front is -Y), following the silhouette."""
    rows = []
    n_rows = 8
    n_cols = 9
    for i in range(n_rows):
        z = waist_z + 0.03 - (waist_z + 0.03 - (knee_z + 0.04)) * i / (n_rows - 1)
        ring = silhouette_ring(pts, z, pad, n=48, bones=bones)
        row = []
        for j in range(n_cols):
            x = -half_w + 2 * half_w * j / (n_cols - 1)
            # front-most ring point near this x
            best = min((p for p in ring if abs(p[0] - x) < 0.06), key=lambda p: p[1], default=None)
            y = (best[1] if best else min(p[1] for p in ring)) - 0.01
            row.append((x, y, z))
        rows.append(row)
    bm = bmesh.new()
    vs = [[bm.verts.new(p) for p in row] for row in rows]
    for i in range(n_rows - 1):
        for j in range(n_cols - 1):
            bm.faces.new((vs[i][j], vs[i][j + 1], vs[i + 1][j + 1], vs[i + 1][j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("apron")
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("apron", me)
    bpy.context.collection.objects.link(o)
    me.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    sol = o.modifiers.new("solid", "SOLIDIFY")
    sol.thickness = 0.008
    bpy.ops.object.modifier_apply(modifier="solid")
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(60))
    unwrap(o, 0.5)
    # weights by height so the panel bends with the hips and thighs
    for bn in set(b for _, b in (bones_by_z or [])):
        o.vertex_groups.new(name=bn)
    for v in o.data.vertices:
        bone = next((bn for (zz, bn) in (bones_by_z or []) if v.co.z >= zz), (bones_by_z or [(0, "pelvis")])[-1][1])
        o.vertex_groups[bone].add([v.index], 1.0, "REPLACE")
    am = o.modifiers.new("arm", "ARMATURE")
    am.object = rig
    o.parent = rig
    return o


def buttons(pts_tights, rig, z_lo, z_hi, n, mat, bones_by_z):
    """Row of buttons down the front centre line (front is -Y)."""
    out = []
    for i in range(n):
        z = z_lo + (z_hi - z_lo) * i / max(1, n - 1)
        sl = [p for p in pts_tights if abs(p.z - z) < 0.03 and abs(p.x) < 0.04]
        if not sl:
            continue
        y = min(p.y for p in sl) - 0.012
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.011, location=(0, y, z))
        b = bpy.context.object
        b.scale.y = 0.5
        bpy.ops.object.transform_apply(scale=True)
        b.data.materials.append(mat)
        b.name = "button"
        bone = next((bn for (zz, bn) in bones_by_z if z >= zz), bones_by_z[-1][1])
        _weight_to_bone(b, rig, bone)
        out.append(b)
    return out


def eye_shadow(rig):
    """Dark translucent shell over the upper front of each eyeball: the upper lid's shadow, baked."""
    eye = next((o for o in bpy.data.objects if o.type == "MESH" and "high-poly" in o.name), None)
    if eye is None:
        return None
    sh = eye.copy()
    sh.data = eye.data.copy()
    sh.name = "eye_shadow"
    bpy.context.collection.objects.link(sh)
    for m in list(sh.modifiers):
        if m.type != "ARMATURE":
            sh.modifiers.remove(m)
    bm = bmesh.new()
    bm.from_mesh(sh.data)
    kill = [f for f in bm.faces if not (f.normal.y < -0.1 and f.normal.z > -0.05)]
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    for v in bm.verts:
        v.co += v.normal * 0.0012
    bm.to_mesh(sh.data)
    bm.free()
    m = bpy.data.materials.new("eye_shadow")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.02, 0.015, 0.01, 1)
    b.inputs["Alpha"].default_value = 0.65
    b.inputs["Roughness"].default_value = 1.0
    sh.data.materials.clear()
    sh.data.materials.append(m)
    return sh


def head_box(pts, top_z):
    """Width, depth and centre of the skull just below the crown."""
    sl = [p for (p, d) in pts if top_z - 0.10 < p.z < top_z - 0.02 and d == "head"]
    xs = [p.x for p in sl]
    ys = [p.y for p in sl]
    # bounding-box centre, moved a little back: the brow ridge and nose pull the front forward
    return (max(xs) - min(xs)), (max(ys) - min(ys)), (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2 + 0.012


def helper(groups, gname, thresh=0.5):
    return groups.get(gname, 0) > thresh


def skin_face(groups):
    """True for real body surface faces (not helpers, not joint cubes)."""
    return (groups.get("body", 0) > 0.5 and groups.get("JointCubes", 0) < 0.01 and groups.get("HelperGeometry", 0) < 0.01
            and groups.get("helper-hair", 0) < 0.01)


def build_clothes(h, rig, spec):
    me = snapshot(h)
    info = face_info(h, me, rig)
    B = {b.name: (rig.matrix_world @ b.head_local, rig.matrix_world @ b.tail_local) for b in rig.data.bones}
    waist_z = B["spine_02"][0].z
    knee_z = (B["calf_l"][0].z + B["calf_r"][0].z) / 2
    ankle_z = (B["foot_l"][0].z + B["foot_r"][0].z) / 2
    hand_heads = [B["hand_l"][0], B["hand_r"][0]]
    top_z = max(c.z for (c, g, d) in info if skin_face(g))     # crown of the skull (skin only, no helpers or joint cubes)
    log("crown z %.2f (head bone tail %.2f)" % (top_z, B["head"][1].z))
    log("waist %.2f knee %.2f ankle %.2f top %.2f" % (waist_z, knee_z, ankle_z, top_z))

    TORSO = {"spine_01", "spine_02", "spine_03", "pelvis", "clavicle_l", "clavicle_r", "neck_01"}
    ARMS = {"upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r"}
    LEGS_UP = {"thigh_l", "thigh_r"}
    CALF = {"calf_l", "calf_r"}
    FEET = {"foot_l", "foot_r", "ball_l", "ball_r"}

    def near_hand(co):
        return min((co - hh).length for hh in hand_heads) < 0.11

    coat_len = spec.get("coat_len", "mid")
    coat = spec["coat"]
    if coat_len == "long":
        spec = dict(spec, breeches=coat, stockings=coat)     # hidden under the skirt; same colour kills any z-fight
    out = []

    # coat body + sleeves (tights helper, torso and arms, above the coat hem)
    hem = waist_z - 0.02 if coat_len == "short" else waist_z - 0.20
    has_collar = bool(spec.get("collar"))
    def coat_fn(i, co, g, dom):
        if not helper(g, "helper-tights"):
            return False
        if dom in ARMS:
            return not near_hand(co)
        if dom == "neck_01":
            return not has_collar
        if dom in TORSO:
            return co.z > hem - 0.05
        if dom in LEGS_UP and coat_len == "long":
            return co.z > hem
        return False
    out.append(garment(h, rig, me, info, "coat", coat_fn, M(coat), 0.014))

    # cuffs
    if spec.get("cuffs"):
        out.append(garment(h, rig, me, info, "cuffs", lambda i, co, g, dom: helper(g, "helper-tights") and dom in ARMS and near_hand(co), M(spec["cuffs"]), 0.026))
    else:
        out.append(garment(h, rig, me, info, "cuffs", lambda i, co, g, dom: helper(g, "helper-tights") and dom in ARMS and near_hand(co), M(coat), 0.014))

    # coat skirts for mid coats: knee length, flared, open at the front (1790s frock coat)
    if coat_len == "mid":
        out.append(garment(h, rig, me, info, "coat_skirt", lambda i, co, g, dom: helper(g, "helper-skirt") and co.z > knee_z + 0.10 and not (abs(co.x) < 0.075 and co.y < -0.02), M(coat), 0.012, offset=0.6))
    # skirt for long coats (kontusz, sukmana, cassock, bekishe)
    if coat_len == "long":
        out.append(garment(h, rig, me, info, "skirt", lambda i, co, g, dom: helper(g, "helper-skirt"), M(coat), 0.03, offset=0.75))

    pts = skin_points(h, me, rig)
    names = [g.name for g in h.vertex_groups]
    TB = {"spine_01", "spine_02", "spine_03", "pelvis"}
    tights_pts = [v.co.copy() for v in me.vertices if any(names[x.group] == "helper-tights" and x.weight > 0.5 for x in v.groups)]

    # sash / belt: a real band around the waist
    if spec.get("sash"):
        out.append(band("sash", pts, waist_z - 0.06, waist_z + 0.05, 0.035, M(spec["sash"]), rig, "spine_02", thickness=0.024, bones=TB))

    # collar band
    if spec.get("collar"):
        nz = B["neck_01"][0].z
        out.append(band("collar", pts, nz - 0.03, nz + 0.045, 0.025 if spec.get("wimple") else 0.012, M(spec["collar"]), rig, "neck_01", thickness=0.018 if spec.get("wimple") else 0.012, extra_top=0.008, bones={"neck_01"}))

    # buttons down the front
    if spec.get("buttons", True) and coat_len != "long" or spec.get("buttons") == "long":
        top = B["neck_01"][0].z - 0.05
        out += buttons(tights_pts, rig, hem + 0.06, top, 8 if coat_len != "long" else 12, M(spec.get("button_colour", "brass"), 0.35),
                       [(B["spine_03"][0].z, "spine_03"), (B["spine_02"][0].z, "spine_02"), (B["spine_01"][0].z, "spine_01"), (0.0, "pelvis")])

    # breeches (hip to knee) and stockings (knee to ankle)
    breech_top = knee_z + 0.12 if coat_len == "long" else 9.0
    out.append(garment(h, rig, me, info, "breeches", lambda i, co, g, dom: helper(g, "helper-tights") and ((dom in LEGS_UP and knee_z - 0.03 < co.z <= breech_top) or (dom == "pelvis" and knee_z < co.z <= min(breech_top, hem - 0.05) if coat_len != "short" else (dom == "pelvis" and co.z < waist_z))), M(spec.get("breeches", "black")), 0.012))
    # the tights helper is open at the crotch: a fitted patch over the skin closes it
    if coat_len != "long":
        out.append(garment(h, rig, me, info, "breeches_in", lambda i, co, g, dom: skin_face(g) and dom in LEGS_UP | {"pelvis"} and knee_z + 0.05 < co.z <= min(breech_top, waist_z - 0.06), M(spec.get("breeches", "black")), 0.002, offset=0.4))
    out.append(garment(h, rig, me, info, "stockings", lambda i, co, g, dom: helper(g, "helper-tights") and (dom in CALF or (dom in LEGS_UP and co.z <= knee_z - 0.03)) and co.z > ankle_z + spec.get("boot_height", 0.12), M(spec.get("stockings", "stocking")), 0.008))

    # boots: lower calf band of the tights + the body's own foot surface (beggars go barefoot)
    bh = ankle_z + spec.get("boot_height", 0.12)
    if spec.get("boots") is None and "boots" in spec:
        bh = -1.0
    if bh > 0:
        out.append(garment(h, rig, me, info, "boot_leg", lambda i, co, g, dom: helper(g, "helper-tights") and dom in CALF | FEET and co.z <= bh + 0.005, M(spec.get("boots") or "leather", 0.5), 0.022))
        out.append(garment(h, rig, me, info, "boot_foot", lambda i, co, g, dom: skin_face(g) and dom in FEET | CALF and co.z < bh, M(spec.get("boots") or "leather", 0.5), 0.014))
    for side, bone in ((1, "calf_l"), (-1, "calf_r")):
        if bh < 0:
            break
        leg = {"calf_l", "foot_l", "thigh_l"} if side > 0 else {"calf_r", "foot_r", "thigh_r"}
        if coat_len != "long" or bh < 0.2:
            out.append(band("boot_top", pts, bh - 0.03, bh + 0.015, 0.03, M(spec.get("boots") or "leather", 0.5), rig, bone, thickness=0.010, n=20, side=side, bones=leg))
        if coat_len != "long":
            out.append(band("knee_band", pts, knee_z - 0.02, knee_z + 0.01, 0.024, M(spec.get("breeches", "black")), rig, bone, thickness=0.008, n=20, side=side, bones=leg))

    # hats: fitted solids sized from the measured head, sunk over short hair; bands hug the skull outline
    hat = spec.get("hat")
    hw, hd, hcx, hcy = head_box(pts, top_z)
    def scalp_face(g):
        return skin_face(g) and g.get("scalp", 0) > 0.5
    def cap_face(co, g, dom, depth=0.10):
        """Head skin from the crown down to `depth` below it, leaving the face free."""
        if not (skin_face(g) and dom == "head") or co.z < top_z - depth:
            return False
        return not (co.y < hcy - 0.03 and co.z < top_z - 0.055)
    def solid(name, size, base_z, mat, bevel=0.02, verts=None):
        if verts:
            bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=size[0] / 2, depth=size[2], location=(hcx, hcy, base_z + size[2] / 2))
            o = bpy.context.object
            o.scale.y = size[1] / size[0]
        else:
            bpy.ops.mesh.primitive_cube_add(size=1, location=(hcx, hcy, base_z + size[2] / 2))
            o = bpy.context.object
            o.scale = size
        bpy.ops.object.transform_apply(scale=True)
        if bevel:
            bv = o.modifiers.new("b", "BEVEL"); bv.width = bevel; bv.segments = 3
            bpy.ops.object.modifier_apply(modifier="b")
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
        o.data.materials.append(mat)
        o.name = name
        _weight_to_bone(o, rig, "head")
        return o
    def soft_crown(name, w, d, hgt, base_z, mat, corner_lift=0.025, dish=0.012):
        """Cloth cap crown: a pillow with four raised corners (konfederatka / rogatywka / biretta shape)."""
        bpy.ops.mesh.primitive_cube_add(size=1, location=(hcx, hcy, base_z + hgt / 2))
        o = bpy.context.object
        o.scale = (w, d, hgt)
        bpy.ops.object.transform_apply(scale=True)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=3, use_grid_fill=True)
        zmax = max(v.co.z for v in bm.verts)
        for v in bm.verts:
            if v.co.z > zmax - 1e-4:
                fx = abs(v.co.x - hcx) / (w / 2)
                fy = abs(v.co.y - hcy) / (d / 2)
                corner = max(0.0, fx * fy) ** 1.5
                v.co.z += corner_lift * corner - dish * (1 - max(fx, fy))
            elif v.co.z > base_z + 1e-4:
                # slight outward puff of the sides
                t = (v.co.z - base_z) / hgt
                v.co.x += (v.co.x - hcx) * 0.06 * math.sin(t * math.pi)
                v.co.y += (v.co.y - hcy) * 0.06 * math.sin(t * math.pi)
        bm.to_mesh(o.data)
        bm.free()
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        sub = o.modifiers.new("s", "SUBSURF"); sub.levels = 2
        bpy.ops.object.modifier_apply(modifier="s")
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(60))
        o.data.materials.append(mat)
        o.name = name
        _weight_to_bone(o, rig, "head")
        return o
    if hat == "konfederatka":
        out.append(soft_crown("hat_top", hw + 0.12, hd + 0.08, 0.13, top_z - 0.07, M("crimson")))
        out.append(band("hat_band", pts, top_z - 0.09, top_z - 0.03, 0.04, M("fur"), rig, "head", thickness=0.05, n=28, bones={"head"}))
    elif hat == "krakuska":
        out.append(soft_crown("hat_top", hw + 0.09, hd + 0.06, 0.11, top_z - 0.065, M("red_cap"), corner_lift=0.03))
        out.append(band("hat_band", pts, top_z - 0.085, top_z - 0.03, 0.03, M("black"), rig, "head", thickness=0.04, n=28, bones={"head"}))
        bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.012, radius2=0.002, depth=0.30, location=(hcx + hw / 2 + 0.02, hcy, top_z + 0.08), rotation=(0.2, 0.6, 0))
        f = bpy.context.object
        f.data.materials.append(M("feather"))
        f.name = "feather"
        _weight_to_bone(f, rig, "head")
        out.append(f)
    elif hat == "biretta":
        out.append(soft_crown("hat_top", hw + 0.07, hd + 0.05, 0.10, top_z - 0.055, M("black"), corner_lift=0.015, dish=0.0))
        for rot in (0, 1):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(hcx, hcy, top_z + 0.045 + 0.015))
            r = bpy.context.object
            r.scale = ((hw + 0.03) if rot else 0.02, 0.02 if rot else (hd + 0.01), 0.035)
            bpy.ops.object.transform_apply(scale=True)
            r.data.materials.append(M("black")); r.name = "hat_ridge"
            _weight_to_bone(r, rig, "head")
            out.append(r)
    elif hat == "fur":
        out.append(solid("hat_top", (hw + 0.11, hd + 0.11, 0.17), top_z - 0.065, M(spec.get("hat_colour", "fur")), 0.03, verts=24))
    elif hat == "bonnet":
        out.append(garment(h, rig, me, info, "hat", lambda i, co, g, dom: cap_face(co, g, dom, 0.11), M(spec.get("hat_colour", "cream")), 0.05, offset=0.85))
        out.append(band("hat_band", pts, top_z - 0.045, top_z - 0.015, 0.012, M(spec.get("hat_colour", "cream")), rig, "head", thickness=0.012, n=28, bones={"head"}))
    elif hat == "kerchief":
        out.append(garment(h, rig, me, info, "hat", lambda i, co, g, dom: cap_face(co, g, dom, 0.12), M(spec.get("hat_colour", "kerchief_red")), 0.045, offset=0.85))
        out.append(band("hat_band", pts, top_z - 0.05, top_z - 0.02, 0.012, M(spec.get("hat_colour", "kerchief_red")), rig, "head", thickness=0.012, n=28, bones={"head"}))
    elif hat == "wimple":
        # nun: black cap under the veil, white coif band across the forehead, white wimple at the neck (collar)
        out.append(garment(h, rig, me, info, "hat", lambda i, co, g, dom: cap_face(co, g, dom, 0.13), M("veil"), 0.03, offset=0.85))
        out.append(band("hat_band", pts, top_z - 0.05, top_z - 0.02, 0.012, M("wimple"), rig, "head", thickness=0.012, n=28, bones={"head"}))
    elif hat == "cap":
        out.append(garment(h, rig, me, info, "hat", lambda i, co, g, dom: cap_face(co, g, dom, 0.10), M(spec.get("hat_colour", "brown_coat")), 0.05, offset=0.85))
        out.append(band("hat_band", pts, top_z - 0.05, top_z - 0.025, 0.012, M(spec.get("hat_colour", "brown_coat")), rig, "head", thickness=0.012, n=28, bones={"head"}))
    # ---- rags: holes torn near the hems, more the lower you go
    if spec.get("ragged"):
        rng = random.Random(spec.get("seed", 7))
        for o in out:
            if o and o.name in ("coat", "skirt", "breeches", "stockings", "hat"):
                bm = bmesh.new()
                bm.from_mesh(o.data)
                zs = [v.co.z for v in bm.verts]
                z0, z1 = min(zs), max(zs)
                kill = []
                for f in bm.faces:
                    t = (f.calc_center_median().z - z0) / max(1e-3, z1 - z0)
                    if t < 0.22 and rng.random() < spec["ragged"] * (1.0 - t / 0.22):
                        kill.append(f)
                bmesh.ops.delete(bm, geom=kill, context="FACES")
                bm.to_mesh(o.data)
                bm.free()

    # ---- extra props
    if spec.get("hawk"):
        _hawk(rig, pts)
    if spec.get("zucchetto"):
        out.append(garment(h, rig, me, info, "zucchetto", lambda i, co, g, dom: scalp_face(g) and co.z > top_z - 0.045, M(spec["zucchetto"]), 0.03))
    if spec.get("phrygian"):
        out.append(garment(h, rig, me, info, "phrygian", lambda i, co, g, dom: scalp_face(g) and co.z > top_z - 0.09, M("red_cap"), 0.035))
    if spec.get("apron"):
        out.append(apron_panel(pts, rig, waist_z, knee_z, M(spec["apron"]), TB | LEGS_UP, pad=0.045 if coat_len == "long" else 0.03,
                               bones_by_z=[(B["spine_02"][0].z, "spine_02"), (B["spine_01"][0].z, "spine_01"), (B["pelvis"][0].z, "pelvis"), (0.0, "thigh_l")]))
    if False and spec.get("apron"):
        if coat_len == "long":
            out.append(garment(h, rig, me, info, "apron", lambda i, co, g, dom: helper(g, "helper-skirt") and co.z < waist_z + 0.02 and co.y < -0.04, M(spec["apron"]), 0.02, offset=0.9))
        else:
            out.append(garment(h, rig, me, info, "apron", lambda i, co, g, dom: helper(g, "helper-tights") and dom in TB | LEGS_UP and knee_z + 0.05 < co.z < waist_z + 0.06 and co.y < -0.03, M(spec["apron"]), 0.02, offset=0.9))
    if spec.get("chain"):
        cz = B["spine_03"][0].z + 0.06
        out.append(band("chain", pts, cz - 0.008, cz + 0.008, 0.045, M("brass", 0.3), rig, "spine_03", thickness=0.012, bones=TB))
    if spec.get("cross"):
        cz = B["spine_03"][0].z + 0.02
        sl = [p for p in tights_pts if abs(p.z - cz) < 0.03 and abs(p.x) < 0.04]
        fy = (min(p.y for p in sl) if sl else -0.14) - 0.03
        for size, off in (((0.012, 0.012, 0.11), 0.0), ((0.07, 0.012, 0.012), 0.03)):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, fy, cz + off))
            c = bpy.context.object
            c.scale = size
            bpy.ops.object.transform_apply(scale=True)
            c.data.materials.append(M("brass", 0.3))
            c.name = "cross"
            _weight_to_bone(c, rig, "spine_03")
            out.append(c)
    if spec.get("sword"):
        hz = B["pelvis"][0].z
        sl = [p for (p, d) in pts if d in ("pelvis", "thigh_l") and abs(p.z - hz) < 0.03 and p.x > 0]
        sx = (max(p.x for p in sl) if sl else 0.17) + (0.10 if coat_len == "long" else 0.04)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(sx, 0.03, hz - 0.42))
        blade = bpy.context.object
        blade.scale = (0.03, 0.012, 0.85)
        bpy.ops.object.transform_apply(scale=True)
        blade.data.materials.append(M("charcoal", 0.5))
        blade.name = "scabbard"
        bpy.ops.mesh.primitive_cube_add(size=1, location=(sx, 0.03, hz + 0.02))
        hilt = bpy.context.object
        hilt.scale = (0.11, 0.025, 0.03)
        bpy.ops.object.transform_apply(scale=True)
        hilt.data.materials.append(M("brass", 0.35))
        hilt.name = "hilt"
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.014, depth=0.12, location=(sx, 0.03, hz + 0.09))
        grip = bpy.context.object
        grip.data.materials.append(M("wood_dark") if "wood_dark" in COL else M("leather"))
        grip.name = "grip"
        for o in (blade, hilt, grip):
            o.rotation_euler = (0.18, 0, 0)
            bpy.ops.object.select_all(action="DESELECT"); o.select_set(True); bpy.context.view_layer.objects.active = o
            bpy.ops.object.transform_apply(rotation=True)
            _weight_to_bone(o, rig, "pelvis")
            out.append(o)
    return [o for o in out if o]


def _hawk(rig, pts):
    """A hawk perched on the left fist (falconry). Built after the rest pose so it sits on the hanging hand."""
    bpy.context.view_layer.update()
    hand = (rig.matrix_world @ rig.pose.bones["hand_l"].matrix).to_translation()
    cx, cy, cz = hand.x + 0.02, hand.y - 0.04, hand.z + 0.02
    parts = []
    def ell(name, size, center, mat, seg=14, rings=8):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=1.0, location=center)
        o = bpy.context.object
        o.scale = size
        bpy.ops.object.transform_apply(scale=True)
        bpy.ops.object.shade_smooth()
        o.data.materials.append(mat)
        o.name = name
        parts.append(o)
        return o
    brown = M("brown_coat", 0.9)
    pale = M("buff", 0.9)
    ell("hawk_body", (0.055, 0.085, 0.07), (cx, cy, cz + 0.08), brown)
    ell("hawk_breast", (0.045, 0.06, 0.06), (cx, cy - 0.035, cz + 0.065), pale, seg=12)
    ell("hawk_head", (0.035, 0.04, 0.035), (cx, cy - 0.07, cz + 0.15), brown, seg=12)
    for sx in (-1, 1):
        ell("hawk_wing", (0.02, 0.09, 0.05), (cx + sx * 0.045, cy + 0.01, cz + 0.085), brown, seg=10)
        ell("hawk_eye", (0.006, 0.006, 0.006), (cx + sx * 0.018, cy - 0.095, cz + 0.158), M("black", 0.3), seg=6, rings=4)
    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.012, radius2=0.002, depth=0.03, location=(cx, cy - 0.115, cz + 0.145), rotation=(math.pi / 2, 0, 0))
    beak = bpy.context.object
    beak.data.materials.append(M("charcoal", 0.4)); beak.name = "hawk_beak"; parts.append(beak)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy + 0.10, cz + 0.06))
    tail = bpy.context.object
    tail.scale = (0.05, 0.09, 0.012)
    bpy.ops.object.transform_apply(scale=True)
    tail.rotation_euler = (0.5, 0, 0)
    bpy.ops.object.select_all(action="DESELECT"); tail.select_set(True); bpy.context.view_layer.objects.active = tail
    bpy.ops.object.transform_apply(rotation=True)
    tail.data.materials.append(brown); tail.name = "hawk_tail"; parts.append(tail)
    # hood (falconry hood with a plume) and the glove
    ell("hawk_hood", (0.037, 0.042, 0.037), (cx, cy - 0.07, cz + 0.152), M("leather", 0.7), seg=12)
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.004, depth=0.05, location=(cx, cy - 0.07, cz + 0.20))
    plume = bpy.context.object
    plume.data.materials.append(M("facing_red")); plume.name = "hawk_plume"; parts.append(plume)
    ell("glove", (0.06, 0.075, 0.09), (hand.x, hand.y, hand.z - 0.04), M("leather", 0.7), seg=12)
    for o in parts:
        _weight_to_bone(o, rig, "hand_l")


def _weight_to_bone(obj, rig, bone):
    vg = obj.vertex_groups.new(name=bone)
    vg.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")
    am = obj.modifiers.new("arm", "ARMATURE")
    am.object = rig
    obj.parent = rig


# ------------------------------------------------------------------ pose & animation
def rotate_bone_world(rig, pb, axis, degrees):
    """Rotate a pose bone about a world axis through its head, keeping children attached."""
    head = (rig.matrix_world @ pb.matrix).to_translation()
    R = Matrix.Rotation(math.radians(degrees), 4, axis)
    T = Matrix.Translation(head)
    pb.matrix = rig.matrix_world.inverted() @ (T @ R @ T.inverted()) @ (rig.matrix_world @ pb.matrix)
    bpy.context.view_layer.update()


def set_pose(rig, frame, pose):
    """pose: list of (bone, axis, degrees) applied in order (parents first). Keys all rotated bones."""
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.context.view_layer.update()
    for bone, axis, deg in pose:
        rotate_bone_world(rig, rig.pose.bones[bone], axis, deg)
    for pb in rig.pose.bones:
        pb.keyframe_insert("rotation_quaternion", frame=frame)
        pb.keyframe_insert("location", frame=frame)


def bake_shape_keys(o):
    """Collapse all shape keys (MakeHuman targets) into the mesh so modifiers can be applied."""
    if not o.data.shape_keys:
        return
    o.shape_key_add(name="baked", from_mix=True)
    for k in list(o.data.shape_keys.key_blocks)[:-1]:
        o.shape_key_remove(k)
    o.shape_key_remove(o.data.shape_keys.key_blocks[0])


def aim_bone(rig, pb, direction):
    """Rotate a pose bone (about its head) so it points along a world direction. Children follow."""
    bpy.context.view_layer.update()
    mw = rig.matrix_world @ pb.matrix
    head = mw.to_translation()
    tail = (mw @ Matrix.Translation((0, pb.length, 0))).to_translation()
    cur = (tail - head).normalized()
    q = cur.rotation_difference(Vector(direction).normalized())
    T = Matrix.Translation(head)
    pb.matrix = rig.matrix_world.inverted() @ (T @ q.to_matrix().to_4x4() @ T.inverted()) @ mw
    bpy.context.view_layer.update()


def rest_arms_down(rig, arm_drop=62, elbow=8):
    """Turn the A-pose into a relaxed stance and make it the new rest pose."""
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="POSE")
    # MakeHuman faces -Y. Upper arm hangs slightly outward, forearm slightly forward, hand continues the forearm.
    for side, sx in (("l", 1), ("r", -1)):
        hand = rig.pose.bones["hand_" + side]
        before = (rig.matrix_world @ hand.matrix).to_translation().z
        aim_bone(rig, rig.pose.bones["upperarm_" + side], (sx * 0.24, 0.04, -1.0))
        aim_bone(rig, rig.pose.bones["lowerarm_" + side], (sx * 0.16, -0.20, -1.0))
        aim_bone(rig, hand, (sx * 0.08, -0.30, -1.0))
        log("arm", side, "hand z %.2f -> %.2f" % (before, (rig.matrix_world @ hand.matrix).to_translation().z))
    # bake the pose into every skinned child, then apply it as the rest pose
    children = [o for o in bpy.data.objects if o.type == "MESH"]
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in children:
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bake_shape_keys(o)
        for m in list(o.modifiers):
            if m.type != "ARMATURE":
                bpy.ops.object.modifier_apply(modifier=m.name)
        for m in list(o.modifiers):
            bpy.ops.object.modifier_apply(modifier=m.name)
        am = o.modifiers.new("arm", "ARMATURE")
        am.object = rig
        # single UV layer, so the exporter cannot pick a helper layout
        uvs = o.data.uv_layers
        if len(uvs) > 1:
            keep = uvs.active.name
            for layer in [u for u in uvs if u.name != keep]:
                uvs.remove(layer)
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def make_animations(rig, fps=30):
    """Idle sway and a walk cycle as separate NLA tracks so glTF exports both."""
    bpy.context.scene.render.fps = fps
    rig.animation_data_create()

    def action(name, frames, poses):
        act = bpy.data.actions.new(name)
        rig.animation_data.action = act
        for f, pose in zip(frames, poses):
            set_pose(rig, f, pose)
        act.use_fake_user = True
        rig.animation_data.action = None
        track = rig.animation_data.nla_tracks.new()
        track.name = name
        strip = track.strips.new(name, int(frames[0]), act)
        strip.name = name
        return act

    # walk: 24 frames loop. Thigh swing +-28, knee bend on the trailing leg, arm counter-swing, torso bob.
    def walk_pose(t):
        s = math.sin(t * math.tau)
        c = math.cos(t * math.tau)
        return [
            ("pelvis", "X", 0),
            ("spine_02", "Z", 4 * s),
            ("thigh_l", "X", 28 * s), ("calf_l", "X", max(0, -40 * c) if s < 0 else 12 + 20 * max(0, -c)),
            ("thigh_r", "X", -28 * s), ("calf_r", "X", max(0, 40 * c) if s > 0 else 12 + 20 * max(0, c)),
            ("upperarm_l", "X", -22 * s), ("upperarm_r", "X", 22 * s),
            ("lowerarm_l", "X", -10 - 8 * max(0, -s)), ("lowerarm_r", "X", -10 - 8 * max(0, s)),
            ("head", "Z", -2 * s),
        ]
    frames = list(range(1, 26))
    action("walk", frames, [walk_pose((f - 1) / 24) for f in frames])

    def idle_pose(t):
        s = math.sin(t * math.tau)
        return [("spine_02", "X", 1.5 * s), ("spine_03", "X", 1.0 * s), ("head", "Z", 3 * math.sin(t * math.tau * 0.5)),
                ("upperarm_l", "X", -2 * s), ("upperarm_r", "X", -2 * s), ("lowerarm_l", "X", -6), ("lowerarm_r", "X", -6)]
    frames = list(range(1, 62))
    action("idle", frames, [idle_pose((f - 1) / 60) for f in frames])

    def sentry_pose(t):
        return [("lowerarm_r", "X", -85), ("upperarm_r", "Y", -8), ("lowerarm_l", "X", -6), ("head", "Z", 4 * math.sin(t * math.tau))]
    frames = list(range(1, 62))
    action("sentry", frames, [sentry_pose((f - 1) / 60) for f in frames])


# ------------------------------------------------------------------ export
def tune_skin():
    for m in bpy.data.materials:
        if "body" not in m.name.lower() or not m.node_tree:
            continue
        b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not b:
            continue
        b.inputs["Roughness"].default_value = 0.55
        try:
            b.inputs["Subsurface Weight"].default_value = 0.08
            b.inputs["Subsurface Radius"].default_value = (1.0, 0.2, 0.1)
            b.inputs["Subsurface Scale"].default_value = 0.02
        except KeyError:
            pass


def simplify_textured_materials():
    """MPFB wires textures through node groups the glTF exporter cannot follow (eyes come out white).
    Rebuild each textured material as image -> Principled BSDF, keeping the alpha link for strands."""
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        imgs = [n for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
        if not imgs:
            continue
        if m.name.startswith("cloth_"):
            continue
        bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        direct = bsdf and bsdf.inputs["Base Color"].links and bsdf.inputs["Base Color"].links[0].from_node.type == "TEX_IMAGE"
        if direct:
            continue
        diffuse = sorted(imgs, key=lambda n: (not ("diffuse" in n.image.name.lower() or "color" in n.image.name.lower()),
                                                ("normal" in n.image.name.lower()) or ("bump" in n.image.name.lower()), -n.image.size[0]))[0]
        normal = next((n for n in imgs if "normal" in n.image.name.lower()), None)
        nt = m.node_tree
        for n in list(nt.nodes):
            if n not in (diffuse, normal):
                nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        b.inputs["Roughness"].default_value = 0.6
        low = m.name.lower()
        strands = any(k in low for k in ("short0", "long0", "ponytail", "bob0", "braid", "afro", "eyebrow"))
        if strands and CURRENT.get("hair_tint"):
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            mix.inputs[7].default_value = (*HAIR_TINTS[CURRENT["hair_tint"]], 1.0)
            nt.links.new(diffuse.outputs["Color"], mix.inputs[6])
            nt.links.new(mix.outputs[2], b.inputs["Base Color"])
        else:
            nt.links.new(diffuse.outputs["Color"], b.inputs["Base Color"])
        nt.links.new(diffuse.outputs["Alpha"], b.inputs["Alpha"])
        if normal:
            nm = nt.nodes.new("ShaderNodeNormalMap")
            normal.image.colorspace_settings.name = "Non-Color"
            nt.links.new(normal.outputs["Color"], nm.inputs["Color"])
            nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
        nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
        log("  simplified material", m.name, "->", diffuse.image.name)


def fix_material_alpha():
    """MPFB builds every material alpha-blended. Blended skin and teeth sort against each other by object origin
    and draw through the face. Opaque for skin, eyes, teeth, hats, cloth; alpha-clip only for strand textures."""
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        low = m.name.lower()
        strands = any(k in low for k in ("hair", "eyebrow", "eyelash", "short0", "long0", "ponytail", "bob0", "braid", "afro"))
        eyes = "high-poly" in low or "low-poly" in low or "eye_shadow" in low
        try:
            m.surface_render_method = "BLENDED" if eyes else "DITHERED"
        except Exception:
            m.blend_method = "BLEND" if eyes else ("CLIP" if strands else "OPAQUE")
        m.use_backface_culling = False
        if strands or eyes:
            m.alpha_threshold = 0.4
            continue
        for n in m.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                for link in list(n.inputs["Alpha"].links):
                    m.node_tree.links.remove(link)
                n.inputs["Alpha"].default_value = 1.0


def bake_hair_tint():
    """Godot's glTF import ignores mix nodes, so tint the strand textures' pixels directly."""
    tint = CURRENT.get("hair_tint")
    if not tint:
        return
    r, g, b = HAIR_TINTS[tint]
    blend = HAIR_BLEND.get(tint)
    for img in bpy.data.images:
        low = img.name.lower()
        if not any(k in low for k in ("short0", "long0", "ponytail", "bob0", "braid", "afro", "eyebrow")):
            continue
        px = list(img.pixels)
        for i in range(0, len(px), 4):
            if blend:
                (cr, cg, cb), a = blend
                lum = 0.3 * px[i] + 0.59 * px[i + 1] + 0.11 * px[i + 2]
                px[i] = px[i] * (1 - a) + cr * (0.6 + 0.8 * lum) * a
                px[i + 1] = px[i + 1] * (1 - a) + cg * (0.6 + 0.8 * lum) * a
                px[i + 2] = px[i + 2] * (1 - a) + cb * (0.6 + 0.8 * lum) * a
            else:
                px[i] = min(1.0, px[i] * r)
                px[i + 1] = min(1.0, px[i + 1] * g)
                px[i + 2] = min(1.0, px[i + 2] * b)
        img.pixels = px
        img.name = img.name + "_" + tint
        img.pack()


def shrink_images(max_size=2048):
    for img in bpy.data.images:
        if img.size[0] > max_size or img.size[1] > max_size:
            img.scale(min(img.size[0], max_size), min(img.size[1], max_size))


def spec_max_tex():
    return CURRENT.get("max_tex", 2048)


def export(rig, name):
    # MakeHuman faces Blender -Y, which lands on Godot +Z. Godot turns character instances by PI.
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.select_set(True)
            if o.parent is None:
                o.parent = rig
    bpy.context.view_layer.objects.active = rig
    for o in bpy.data.objects:
        log("  export", o.name, o.type, "parent", o.parent.name if o.parent else None,
            "verts", len(o.data.vertices) if o.type == "MESH" else len(o.data.bones), "uv", [u.name for u in o.data.uv_layers] if o.type == "MESH" else "")
    shrink_images(spec_max_tex())
    bake_hair_tint()
    simplify_textured_materials()
    tune_skin()
    fix_material_alpha()
    # anything that is not the rig, the body, an MPFB asset, a garment or the musket is a stray helper
    for o in list(bpy.data.objects):
        if o.type == "MESH" and not (o.parent == rig or o.name.startswith("Human")):
            log("  removing stray", o.name)
            bpy.data.objects.remove(o)
    path = os.path.join(OUT, name + ".glb")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
                              export_image_format="AUTO", export_jpeg_quality=85, export_animations=True,
                              export_animation_mode="NLA_TRACKS", export_rest_position_armature=True,
                              export_skins=True, export_morph=False, export_def_bones=True)
    log("wrote", os.path.relpath(path, ROOT), "%.1f MB" % (os.path.getsize(path) / 1e6))


FACE_TARGETS = ["nose-hump-incr", "nose-hump-decr", "nose-scale-vert-incr", "nose-scale-vert-decr", "nose-point-width-incr", "nose-point-width-decr",
                "nose-scale-horiz-incr", "nose-flaring-incr", "chin-prominent-incr", "chin-prominent-decr", "chin-width-incr", "chin-width-decr",
                "chin-height-incr", "chin-cleft-incr", "head-round", "head-oval", "head-square", "head-rectangular", "head-diamond",
                "head-scale-horiz-incr", "head-scale-horiz-decr", "head-fat-incr", "head-fat-decr"]


def face_variety(seed, n=5, amount=0.35):
    rng = random.Random(seed)
    out = {}
    for t in rng.sample(FACE_TARGETS, n):
        out[t] = round(rng.uniform(0.1, amount), 2)
    # extra groups if present on disk
    for group in ("eyes", "mouth", "cheek", "forehead", "ears"):
        d = os.path.join(TARGETS, group)
        if os.path.isdir(d) and rng.random() < 0.7:
            files = [f for f in os.listdir(d) if f.endswith(".target.gz") and "-decr" in f or f.endswith(".target.gz") and "-incr" in f]
            if files:
                out[rng.choice(files).replace(".target.gz", "")] = round(rng.uniform(0.1, 0.35), 2)
    return out


def pick_skin(macro, gender_f, seed=0):
    race = macro.get("race", {"caucasian": 1})
    rng = random.Random(seed)
    keys = list(race.keys())
    r = rng.choices(keys, weights=[max(0.0, race[k]) for k in keys])[0]
    age = macro.get("age", 0.5)
    a = "young" if age < 0.45 else ("middleage" if age < 0.7 else "old")
    name = "%s_%s_%s" % (a, r, "female" if gender_f else "male")
    alt = name + "2"
    if os.path.isdir(os.path.join(USER, "skins", alt)) and rng.random() < 0.5:
        return alt
    return name


def build(name, spec):
    log("=== building", name)
    CURRENT["hair_tint"] = spec.get("hair_tint")
    CURRENT["max_tex"] = spec.get("max_tex", 2048)
    if "skin" not in spec:
        spec = dict(spec, skin=pick_skin(spec.get("macro", {}), spec.get("macro", {}).get("gender", 0.5) < 0.5, spec.get("seed", hash(name) & 0xffff)))
    if spec.get("hat") in ("bonnet", "kerchief", "cap", "wimple") and not spec.get("veil"):
        spec = dict(spec, hair=None)
    elif spec.get("hat") in ("fur", "konfederatka", "krakuska", "biretta") and not spec.get("veil"):
        spec = dict(spec, hair="short01")
    if spec.get("seed") is not None or spec.get("face_variety", True):
        spec = dict(spec, targets=dict(face_variety(spec.get("seed", hash(name) & 0xffff)), **spec.get("targets", {})))
    h = make_body(spec)
    skin = os.path.join(USER, "skins", spec.get("skin", "young_caucasian_male"), spec.get("skin", "young_caucasian_male") + ".mhmat")
    HumanService.set_character_skin(skin, h, skin_type="GAMEENGINE")
    rig = HumanService.add_builtin_rig(h, "game_engine")
    for sub, nm, ty in [("eyes", "high-poly", "Eyes"), ("eyebrows", spec.get("brows", "eyebrow001"), "Eyebrows"),
                        ("eyelashes", "eyelashes01", "Eyelashes"), ("teeth", "teeth_base", "Teeth")]:
        o = add(h, sub, nm, ty)
        log("asset", ty, nm, "->", o.name if o else None, [m.type for m in o.modifiers] if o else "")
    if spec.get("hair"):
        o = add(h, "hair", spec["hair"], "Hair")
        log("asset Hair", spec["hair"], "->", o.name if o else None)
        if o and spec.get("veil"):
            o.name = "veil"
            o.data.materials.clear()
            o.data.materials.append(M("veil"))
    eye_shadow(rig)
    if spec.get("hat") == "tricorne":
        o = add(h, "clothes", "fedora_cocked", "Clothes")
        log("asset Hat ->", o.name if o else None)
        if o:
            o.data.materials.clear()
            o.data.materials.append(M(spec.get("hat_colour", "black"), 0.8))
    clothes = build_clothes(h, rig, spec)
    log("garments", [c.name for c in clothes])
    rest_arms_down(rig)
    if spec.get("musket"):
        _musket(rig)
    make_animations(rig)
    export(rig, name)


def _musket(rig):
    """Austrian infantry musket, 1784 pattern, at shoulder arms: full-length walnut stock, round barrel,
    brass bands and butt plate, lock plate, trigger guard, ramrod, sling. Welded to the right hand."""
    bpy.context.view_layer.update()
    hand = (rig.matrix_world @ rig.pose.bones["hand_r"].matrix).to_translation()
    sh = (rig.matrix_world @ rig.pose.bones["upperarm_r"].matrix).to_translation()
    x, y = hand.x - 0.11, hand.y + 0.02
    z0 = hand.z - 0.30            # butt toe near the knee
    L = 1.50                      # overall length
    parts = []
    def keep(o, name, mat):
        o.data.materials.append(mat); o.name = name; parts.append(o); return o
    def box(name, size, center, mat, rot=(0, 0, 0)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=center, rotation=rot)
        o = bpy.context.object; o.scale = size
        bpy.ops.object.transform_apply(scale=True)
        return keep(o, name, mat)
    def cyl(name, r, h, center, mat, verts=12, rot=(0, 0, 0), r2=None):
        if r2 is None:
            bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=center, rotation=rot)
        else:
            bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=h, location=center, rotation=rot)
        bpy.ops.object.shade_smooth()
        return keep(bpy.context.object, name, mat)
    walnut = M("wood_dark", 0.6)
    steel = M("steel", 0.35)
    brass = M("brass", 0.3)
    # stock: butt, wrist, fore-end (tapering to the muzzle band)
    butt = box("stock_butt", (0.045, 0.13, 0.36), (x, y + 0.01, z0 + 0.18), walnut)
    bpy.ops.object.select_all(action="DESELECT"); butt.select_set(True); bpy.context.view_layer.objects.active = butt
    bm = bmesh.new(); bm.from_mesh(butt.data)
    for v in bm.verts:
        if v.co.z > z0 + 0.30:
            v.co.y = y + 0.005 + (v.co.y - y - 0.01) * 0.45     # narrows into the wrist
    bm.to_mesh(butt.data); bm.free()
    bv = butt.modifiers.new("b", "BEVEL"); bv.width = 0.01; bv.segments = 2
    bpy.ops.object.modifier_apply(modifier="b"); bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    box("butt_plate", (0.048, 0.135, 0.012), (x, y + 0.01, z0), brass)
    box("stock_wrist", (0.036, 0.05, 0.14), (x, y + 0.02, z0 + 0.42), walnut)
    box("stock_fore", (0.034, 0.045, L - 0.60), (x, y + 0.035, z0 + 0.49 + (L - 0.60) / 2), walnut)
    # barrel and ramrod along the fore-end
    cyl("barrel", 0.011, L - 0.44, (x, y + 0.012, z0 + 0.44 + (L - 0.44) / 2), steel, verts=12)
    cyl("muzzle", 0.013, 0.05, (x, y + 0.012, z0 + L - 0.02), steel, verts=12)
    cyl("ramrod", 0.004, L - 0.62, (x, y + 0.062, z0 + 0.50 + (L - 0.62) / 2), steel, verts=8)
    # lock plate, cock, trigger guard
    box("lock_plate", (0.006, 0.03, 0.13), (x + 0.02, y + 0.02, z0 + 0.46), steel)
    box("cock", (0.006, 0.02, 0.05), (x + 0.024, y + 0.005, z0 + 0.50), steel)
    cyl("trigger_guard", 0.028, 0.006, (x, y + 0.055, z0 + 0.40), brass, verts=16, rot=(0, math.pi / 2, 0))
    # brass barrel bands
    for zz in (0.62, 0.92, 1.24):
        box("band", (0.04, 0.056, 0.02), (x, y + 0.03, z0 + zz), brass)
    # sling from the upper band to the trigger guard, hanging on the outside
    cyl("sling", 0.007, 0.62, (x - 0.026, y + 0.03, z0 + 0.72), M("buff", 0.9), verts=6)
    for o in parts:
        _weight_to_bone(o, rig, "hand_r")


CHARACTERS = {
    "watchman": {"macro": {"gender": 0.95, "age": 0.42, "muscle": 0.62, "weight": 0.5, "height": 0.6},
                 "targets": {"chin-prominent-incr": 0.3, "nose-hump-incr": 0.3}, "skin": "young_caucasian_male", "hair": "short01", "brows": "eyebrow003",
                 "coat": "white_coat", "coat_len": "mid", "cuffs": "facing_red", "collar": "facing_red", "breeches": "white_coat", "stockings": "stocking",
                 "boots": "black", "boot_height": 0.30, "hat": "tricorne", "musket": True, "button_colour": "pewter"},
    "figure_noble": {"macro": {"gender": 0.9, "age": 0.5, "muscle": 0.5, "weight": 0.55, "height": 0.55},
                     "targets": {"head-square": 0.3, "chin-width-incr": 0.2}, "skin": "middleage_caucasian_male", "hair": "short01", "brows": "eyebrow005",
                     "coat": "crimson", "coat_len": "long", "sash": "zupan_gold", "collar": "zupan_gold", "breeches": "zupan_gold", "stockings": "zupan_gold",
                     "boots": "tan_boot", "boot_height": 0.35, "hat": "konfederatka", "buttons": "long"},
    "figure_artist": {"macro": {"gender": 0.85, "age": 0.35, "muscle": 0.4, "weight": 0.4, "height": 0.66},
                      "targets": {"head-oval": 0.3, "nose-point-width-decr": 0.2}, "skin": "young_caucasian_male2", "hair": "ponytail01", "brows": "eyebrow002",
                      "coat": "green_coat", "coat_len": "mid", "cuffs": "brown_coat", "collar": "cream", "breeches": "buff", "stockings": "stocking",
                      "boots": "black", "boot_height": 0.12, "hat": "tricorne"},
    "figure_veteran": {"macro": {"gender": 1.0, "age": 0.5, "muscle": 0.75, "weight": 0.55, "height": 0.6},
                       "targets": {"chin-prominent-incr": 0.4, "nose-hump-incr": 0.5}, "skin": "middleage_caucasian_male", "hair": "short01", "brows": "eyebrow007",
                       "coat": "sukmana", "coat_len": "long", "sash": "facing_red", "cuffs": "facing_red", "breeches": "brown_coat", "stockings": "brown_coat",
                       "boots": "leather", "boot_height": 0.30, "hat": "krakuska", "buttons": False},
    "figure_merchant": {"macro": {"gender": 0.9, "age": 0.55, "muscle": 0.45, "weight": 0.7, "height": 0.5},
                        "targets": {"head-round": 0.3, "chin-jaw-drop-incr": 0.2}, "skin": "middleage_caucasian_male", "hair": "short01", "brows": "eyebrow004",
                        "coat": "brown_coat", "coat_len": "mid", "cuffs": "zupan_gold", "collar": "cream", "breeches": "black", "stockings": "stocking",
                        "boots": "black", "boot_height": 0.12, "hat": "tricorne"},
    "figure_priest": {"macro": {"gender": 0.9, "age": 0.6, "muscle": 0.4, "weight": 0.45, "height": 0.5},
                      "targets": {"head-oval": 0.2, "nose-scale-vert-incr": 0.2}, "skin": "old_caucasian_male", "hair": "short01", "brows": "eyebrow006",
                      "coat": "black", "coat_len": "long", "collar": "cream", "breeches": "black", "stockings": "black",
                      "boots": "black", "boot_height": 0.12, "hat": "biretta", "buttons": "long", "button_colour": "black"},
    "figure_kazimierz": {"macro": {"gender": 0.9, "age": 0.5, "muscle": 0.45, "weight": 0.5, "height": 0.5},
                         "targets": {"nose-hump-incr": 0.2, "chin-prominent-incr": 0.2}, "skin": "middleage_caucasian_male", "hair": "short01", "brows": "eyebrow008",
                         "coat": "navy", "coat_len": "long", "collar": "black", "breeches": "black", "stockings": "black",
                         "boots": "black", "boot_height": 0.12, "hat": "fur", "buttons": "long", "button_colour": "black"},
    "figure_townsman": {"macro": {"gender": 0.9, "age": 0.45, "muscle": 0.5, "weight": 0.5, "height": 0.5},
                        "skin": "young_caucasian_male", "hair": "short01", "brows": "eyebrow001",
                        "coat": "brown_coat", "coat_len": "mid", "breeches": "grey", "stockings": "stocking", "boots": "leather", "boot_height": 0.12, "hat": "cap", "button_colour": "pewter"},
    "figure_townswoman": {"macro": {"gender": 0.05, "age": 0.4, "muscle": 0.45, "weight": 0.5, "height": 0.45},
                          "skin": "young_caucasian_female", "hair": "short01", "brows": "eyebrow009",
                          "coat": "sage", "coat_len": "long", "sash": "cream", "collar": "cream", "breeches": "sage", "stockings": "sage", "boots": "black", "boot_height": 0.10, "hat": "bonnet", "buttons": False},
    # ---- female variants of the origins
    "figure_noble_f": {"macro": {"gender": 0.08, "age": 0.45, "muscle": 0.45, "weight": 0.5, "height": 0.5},
                       "targets": {"head-oval": 0.2}, "skin": "young_caucasian_female2", "hair": "short01", "brows": "eyebrow010",
                       "coat": "dress_plum", "coat_len": "long", "sash": "zupan_gold", "collar": "cream", "breeches": "dress_plum", "stockings": "dress_plum",
                       "boots": "tan_boot", "boot_height": 0.10, "hat": "bonnet", "hat_colour": "cream", "buttons": False},
    "figure_artist_f": {"macro": {"gender": 0.1, "age": 0.35, "muscle": 0.4, "weight": 0.42, "height": 0.48},
                        "skin": "young_caucasian_female", "hair": "long01", "brows": "eyebrow011",
                        "coat": "dress_green", "coat_len": "long", "sash": "brown_coat", "collar": "cream", "breeches": "dress_green", "stockings": "dress_green",
                        "boots": "black", "boot_height": 0.10, "hat": None, "buttons": False},
    "figure_veteran_f": {"macro": {"gender": 0.05, "age": 0.5, "muscle": 0.6, "weight": 0.55, "height": 0.5},
                         "skin": "middleage_caucasian_female", "hair": "short01", "brows": "eyebrow012",
                         "coat": "sukmana", "coat_len": "long", "sash": "facing_red", "collar": "cream", "breeches": "sukmana", "stockings": "sukmana",
                         "boots": "leather", "boot_height": 0.12, "hat": "kerchief", "hat_colour": "kerchief_red", "buttons": False},
    "figure_merchant_f": {"macro": {"gender": 0.05, "age": 0.5, "muscle": 0.45, "weight": 0.62, "height": 0.48},
                          "skin": "middleage_caucasian_female", "hair": "short01", "brows": "eyebrow009",
                          "coat": "dress_blue", "coat_len": "long", "sash": "cream", "collar": "cream", "breeches": "dress_blue", "stockings": "dress_blue",
                          "boots": "black", "boot_height": 0.10, "hat": "bonnet", "hat_colour": "cream", "buttons": False},
    "figure_priest_f": {"macro": {"gender": 0.05, "age": 0.55, "muscle": 0.4, "weight": 0.5, "height": 0.47},
                        "skin": "middleage_caucasian_female", "hair": "long01", "veil": True, "brows": "eyebrow006",
                        "coat": "black", "coat_len": "long", "collar": "wimple", "wimple": True, "breeches": "black", "stockings": "black",
                        "boots": "black", "boot_height": 0.10, "hat": "wimple", "buttons": False},
    "figure_kazimierz_f": {"macro": {"gender": 0.05, "age": 0.45, "muscle": 0.45, "weight": 0.5, "height": 0.47},
                           "skin": "young_caucasian_female2", "hair": "short01", "brows": "eyebrow008",
                           "coat": "navy", "coat_len": "long", "sash": "black", "collar": "cream", "breeches": "navy", "stockings": "navy",
                           "boots": "black", "boot_height": 0.10, "hat": "kerchief", "hat_colour": "black", "buttons": False},
}

CAST = {
    # Austrian occupation
    "cast_governor": {"macro": {"gender": 0.95, "age": 0.72, "muscle": 0.4, "weight": 0.62, "height": 0.55}, "targets": {"chin-jaw-drop-incr": 0.3},
                      "hair": "long01", "hair_tint": "white", "brows": "eyebrow006", "coat": "white_coat", "coat_len": "mid", "cuffs": "facing_red", "collar": "facing_red",
                      "sash": "facing_red", "breeches": "white_coat", "stockings": "stocking", "boots": "black", "boot_height": 0.12, "hat": "tricorne", "sword": True, "button_colour": "brass"},
    "cast_officer": {"macro": {"gender": 1.0, "age": 0.45, "muscle": 0.7, "weight": 0.5, "height": 0.65}, "targets": {"chin-prominent-incr": 0.3},
                     "hair": "ponytail01", "hair_tint": "dark_brown", "brows": "eyebrow003", "coat": "white_coat", "coat_len": "mid", "cuffs": "facing_red", "collar": "facing_red",
                     "sash": "zupan_gold", "breeches": "white_coat", "stockings": "stocking", "boots": "black", "boot_height": 0.32, "hat": "tricorne", "sword": True, "button_colour": "brass"},
    "cast_polizei": {"macro": {"gender": 0.95, "age": 0.55, "muscle": 0.5, "weight": 0.5, "height": 0.55}, "targets": {"nose-hump-incr": 0.4, "head-oval": 0.3},
                     "hair": "short01", "hair_tint": "black", "brows": "eyebrow004", "coat": "charcoal", "coat_len": "long", "collar": "black", "buttons": "long", "button_colour": "black",
                     "boots": "black", "boot_height": 0.12, "hat": "tricorne"},
    "cast_informer": {"macro": {"gender": 0.9, "age": 0.4, "muscle": 0.4, "weight": 0.42, "height": 0.48}, "targets": {"nose-point-width-decr": 0.3},
                      "hair": "short02", "hair_tint": "dark_brown", "brows": "eyebrow002", "coat": "grey_coat", "coat_len": "mid", "collar": "grey_coat", "breeches": "charcoal", "stockings": "stocking",
                      "boots": "leather", "boot_height": 0.12, "hat": "cap", "button_colour": "pewter"},
    # Russia and Prussia
    "cast_russian_envoy": {"macro": {"gender": 0.95, "age": 0.5, "muscle": 0.55, "weight": 0.6, "height": 0.62}, "targets": {"chin-width-incr": 0.3},
                           "hair": "short04", "hair_tint": "black", "brows": "eyebrow007", "coat": "dress_green", "coat_len": "long", "sash": "zupan_gold", "collar": "zupan_gold",
                           "boots": "black", "boot_height": 0.35, "hat": "fur", "buttons": "long", "button_colour": "brass", "sword": True},
    "cast_prussian_banker": {"macro": {"gender": 0.9, "age": 0.6, "muscle": 0.4, "weight": 0.55, "height": 0.5},
                             "hair": "ponytail01", "hair_tint": "grey", "brows": "eyebrow005", "coat": "grey_coat", "coat_len": "mid", "cuffs": "silver", "collar": "cream",
                             "breeches": "charcoal", "stockings": "stocking", "boots": "black", "boot_height": 0.12, "hat": "tricorne", "button_colour": "silver"},
    "cast_agent_f": {"macro": {"gender": 0.05, "age": 0.35, "muscle": 0.45, "weight": 0.45, "height": 0.52},
                     "hair": "long01", "hair_tint": "blond", "brows": "eyebrow011", "coat": "dress_green", "coat_len": "long", "sash": "black", "collar": "cream",
                     "boots": "black", "boot_height": 0.10, "hat": None, "buttons": False},
    # Church
    "cast_bishop": {"macro": {"gender": 0.9, "age": 0.78, "muscle": 0.35, "weight": 0.6, "height": 0.5},
                    "hair": "short01", "hair_tint": "white", "brows": "eyebrow006", "coat": "purple", "coat_len": "long", "sash": "purple", "collar": "cream",
                    "boots": "black", "boot_height": 0.10, "hat": None, "zucchetto": "purple", "cross": True, "buttons": "long", "button_colour": "purple"},
    # Salon
    "cast_hostess_f": {"macro": {"gender": 0.05, "age": 0.48, "muscle": 0.4, "weight": 0.5, "height": 0.5},
                       "hair": "bob01", "hair_tint": "auburn", "brows": "eyebrow010", "coat": "dress_plum", "coat_len": "long", "sash": "zupan_gold", "collar": "cream",
                       "boots": "tan_boot", "boot_height": 0.10, "hat": None, "buttons": False},
    "cast_printer": {"macro": {"gender": 0.9, "age": 0.42, "muscle": 0.5, "weight": 0.48, "height": 0.52},
                     "hair": "short03", "hair_tint": "auburn", "brows": "eyebrow002", "coat": "olive", "coat_len": "mid", "cuffs": "cream", "collar": "cream", "apron": "apron",
                     "breeches": "charcoal", "stockings": "stocking", "boots": "leather", "boot_height": 0.12, "hat": None, "button_colour": "pewter"},
    "cast_jacobin": {"macro": {"gender": 0.85, "age": 0.3, "muscle": 0.45, "weight": 0.42, "height": 0.55},
                     "hair": "long01", "hair_tint": "black", "brows": "eyebrow002", "coat": "navy", "coat_len": "mid", "cuffs": "facing_red", "collar": "facing_red",
                     "breeches": "buff", "stockings": "stocking", "boots": "black", "boot_height": 0.12, "hat": None, "phrygian": True, "button_colour": "brass"},
    # Underworld and street
    "cast_smuggler": {"macro": {"gender": 1.0, "age": 0.5, "muscle": 0.8, "weight": 0.6, "height": 0.62}, "targets": {"chin-prominent-incr": 0.5, "nose-hump-incr": 0.4, "head-square": 0.4},
                      "hair": "short04", "hair_tint": "black", "brows": "eyebrow007", "coat": "leather", "coat_len": "mid", "cuffs": "charcoal", "collar": "charcoal",
                      "breeches": "charcoal", "stockings": "brown_coat", "boots": "black", "boot_height": 0.30, "hat": "cap", "buttons": False, "sword": True},
    "cast_boatman": {"macro": {"gender": 1.0, "age": 0.45, "muscle": 0.7, "weight": 0.55, "height": 0.6},
                     "hair": "short02", "hair_tint": "brown", "brows": "eyebrow001", "coat": "rust", "coat_len": "mid", "sash": "rope", "collar": "rust",
                     "breeches": "grey_coat", "stockings": "stocking", "boots": "leather", "boot_height": 0.12, "hat": "cap", "buttons": False},
    "cast_student": {"macro": {"gender": 0.85, "age": 0.25, "muscle": 0.4, "weight": 0.4, "height": 0.55},
                     "hair": "long01", "hair_tint": "brown", "brows": "eyebrow002", "coat": "dress_blue", "coat_len": "mid", "cuffs": "cream", "collar": "cream",
                     "breeches": "buff", "stockings": "stocking", "boots": "black", "boot_height": 0.12, "hat": None, "button_colour": "pewter"},
    # Guilds and magnates
    "cast_burgomaster": {"macro": {"gender": 0.9, "age": 0.7, "muscle": 0.4, "weight": 0.66, "height": 0.5}, "targets": {"head-round": 0.4},
                         "hair": "short01", "hair_tint": "grey", "brows": "eyebrow005", "coat": "black", "coat_len": "long", "collar": "cream", "chain": True,
                         "boots": "black", "boot_height": 0.10, "hat": "cap", "buttons": "long", "button_colour": "black"},
    "cast_magnate": {"macro": {"gender": 0.95, "age": 0.52, "muscle": 0.6, "weight": 0.62, "height": 0.65}, "targets": {"chin-width-incr": 0.3, "head-square": 0.3},
                     "hair": "short01", "hair_tint": "dark_brown", "brows": "eyebrow005", "coat": "navy", "coat_len": "long", "sash": "zupan_gold", "collar": "zupan_gold",
                     "boots": "tan_boot", "boot_height": 0.35, "hat": "konfederatka", "buttons": "long", "button_colour": "brass", "sword": True},
    "cast_hajduk": {"macro": {"gender": 1.0, "age": 0.35, "muscle": 0.7, "weight": 0.5, "height": 0.62},
                    "hair": "short01", "hair_tint": "black", "brows": "eyebrow003", "coat": "livery_blue", "coat_len": "mid", "cuffs": "facing_red", "collar": "facing_red", "sash": "facing_red",
                    "breeches": "livery_blue", "stockings": "stocking", "boots": "black", "boot_height": 0.32, "hat": "krakuska", "button_colour": "brass", "sword": True},
    "cast_falconer": {"macro": {"gender": 0.95, "age": 0.45, "muscle": 0.55, "weight": 0.5, "height": 0.58},
                      "hair": "short02", "hair_tint": "brown", "brows": "eyebrow001", "coat": "olive", "coat_len": "mid", "cuffs": "leather", "collar": "leather", "sash": "leather",
                      "breeches": "brown_coat", "stockings": "stocking", "boots": "leather", "boot_height": 0.30, "hat": "cap", "buttons": False, "hawk": True},
    # Street poor
    "cast_beggar": {"macro": {"gender": 0.95, "age": 0.8, "muscle": 0.3, "weight": 0.3, "height": 0.45}, "targets": {"chin-prominent-incr": 0.3},
                    "hair": "short04", "hair_tint": "grey", "brows": "eyebrow006", "coat": "grey_coat", "coat_len": "long", "collar": "grey_coat", "sash": "rope",
                    "boots": None, "hat": None, "buttons": False, "ragged": 0.35, "seed": 3, "max_tex": 1024},
    "cast_beggar_f": {"macro": {"gender": 0.05, "age": 0.65, "muscle": 0.3, "weight": 0.35, "height": 0.42},
                      "hair": "short01", "hair_tint": "grey", "brows": "eyebrow009", "coat": "brown_coat", "coat_len": "long", "collar": "brown_coat",
                      "boots": None, "hat": "kerchief", "hat_colour": "grey_coat", "buttons": False, "ragged": 0.3, "seed": 5, "max_tex": 1024},
    "cast_urchin": {"macro": {"gender": 0.9, "age": 0.16, "muscle": 0.45, "weight": 0.4, "height": 0.5},
                    "hair": "short02", "hair_tint": "brown", "brows": "eyebrow001", "coat": "rust", "coat_len": "short", "collar": "rust",
                    "breeches": "grey_coat", "stockings": "stocking", "boots": None, "hat": "cap", "buttons": False, "ragged": 0.3, "seed": 9, "max_tex": 1024},
    "cast_urchin_f": {"macro": {"gender": 0.1, "age": 0.15, "muscle": 0.4, "weight": 0.4, "height": 0.5},
                      "hair": "braid01", "hair_tint": "blond", "brows": "eyebrow009", "coat": "sage", "coat_len": "long", "collar": "cream", "sash": "rope",
                      "boots": None, "hat": "kerchief", "hat_colour": "cream", "buttons": False, "ragged": 0.25, "seed": 11, "max_tex": 1024},
    "cast_child": {"macro": {"gender": 0.9, "age": 0.13, "muscle": 0.45, "weight": 0.45, "height": 0.5},
                   "hair": "short01", "hair_tint": "blond", "brows": "eyebrow001", "coat": "dress_blue", "coat_len": "short", "collar": "cream",
                   "breeches": "buff", "stockings": "stocking", "boots": "leather", "boot_height": 0.10, "hat": None, "button_colour": "pewter", "max_tex": 1024},
    "cast_child_f": {"macro": {"gender": 0.1, "age": 0.14, "muscle": 0.4, "weight": 0.45, "height": 0.5},
                     "hair": "bob02", "hair_tint": "dark_brown", "brows": "eyebrow009", "coat": "dress_plum", "coat_len": "long", "collar": "cream", "sash": "cream",
                     "boots": "black", "boot_height": 0.10, "hat": "bonnet", "hat_colour": "cream", "buttons": False, "max_tex": 1024},
}

TOWNSFOLK = {
    # Inns and taverns
    "town_innkeeper": {"macro": {"gender": 0.95, "age": 0.62, "muscle": 0.45, "weight": 0.85, "height": 0.52}, "targets": {"head-round": 0.4, "chin-jaw-drop-incr": 0.3},
                       "hair": "short03", "hair_tint": "grey", "brows": "eyebrow005", "coat": "brown_coat", "coat_len": "short", "collar": "cream", "apron": "apron",
                       "breeches": "leather", "stockings": "stocking", "boots": "leather", "boot_height": 0.12, "hat": None, "button_colour": "pewter", "max_tex": 1024},
    "town_tavern_maid_f": {"macro": {"gender": 0.05, "age": 0.44, "muscle": 0.5, "weight": 0.5, "height": 0.46, "race": {"caucasian": 0.95, "asian": 0.05, "african": 0.0}},
                           "hair": "short01", "hair_tint": "blond", "brows": "eyebrow009", "coat": "rust", "coat_len": "long", "collar": "cream", "sash": "cream", "apron": "apron",
                           "boots": "leather", "boot_height": 0.10, "hat": "kerchief", "hat_colour": "kerchief_red", "buttons": False, "max_tex": 1024},
    # Rynek and the Sukiennice
    "town_cloth_merchant": {"macro": {"gender": 0.92, "age": 0.55, "muscle": 0.45, "weight": 0.68, "height": 0.55}, "targets": {"head-square": 0.3, "chin-width-incr": 0.2},
                            "hair": "ponytail01", "hair_tint": "dark_brown", "brows": "eyebrow004", "coat": "indigo", "coat_len": "mid", "cuffs": "zupan_gold", "collar": "cream",
                            "breeches": "buff", "stockings": "stocking", "boots": "black", "boot_height": 0.12, "hat": "tricorne", "chain": True, "button_colour": "brass", "max_tex": 1024},
    "town_cloth_merchant_f": {"macro": {"gender": 0.05, "age": 0.5, "muscle": 0.4, "weight": 0.6, "height": 0.48}, "targets": {"head-oval": 0.2},
                              "hair": "short01", "hair_tint": "brown", "brows": "eyebrow010", "coat": "wine", "coat_len": "long", "sash": "zupan_gold", "collar": "cream",
                              "boots": "tan_boot", "boot_height": 0.10, "hat": "bonnet", "hat_colour": "cream", "buttons": False, "max_tex": 1024},
    "town_market_woman_f": {"macro": {"gender": 0.03, "age": 0.6, "muscle": 0.55, "weight": 0.65, "height": 0.42, "race": {"caucasian": 0.9, "asian": 0.1, "african": 0.0}},
                            "targets": {"head-round": 0.3, "nose-scale-vert-incr": 0.2}, "hair": "short01", "hair_tint": "grey", "brows": "eyebrow012",
                            "coat": "ochre_cloth", "coat_len": "long", "collar": "cream", "sash": "brown_coat",
                            "boots": "leather", "boot_height": 0.10, "hat": "kerchief", "hat_colour": "dress_blue", "buttons": False, "max_tex": 1024},
    # Kazimierz
    "town_shopkeeper_kazimierz": {"macro": {"gender": 0.93, "age": 0.58, "muscle": 0.4, "weight": 0.5, "height": 0.5, "race": {"caucasian": 0.85, "asian": 0.1, "african": 0.05}},
                                  "targets": {"nose-hump-incr": 0.4, "nose-scale-vert-incr": 0.2}, "hair": "short01", "hair_tint": "black", "brows": "eyebrow008",
                                  "coat": "black", "coat_len": "long", "collar": "black", "sash": "charcoal", "boots": "black", "boot_height": 0.12,
                                  "hat": "fur", "buttons": "long", "button_colour": "black", "max_tex": 1024},
    # Trades
    "town_baker": {"macro": {"gender": 0.9, "age": 0.4, "muscle": 0.5, "weight": 0.62, "height": 0.5}, "targets": {"head-round": 0.2},
                   "hair": "short02", "hair_tint": "brown", "brows": "eyebrow001", "coat": "flour", "coat_len": "short", "collar": "flour", "apron": "apron",
                   "breeches": "buff", "stockings": "stocking", "boots": "leather", "boot_height": 0.10, "hat": "cap", "buttons": False, "max_tex": 1024},
    "town_blacksmith": {"macro": {"gender": 1.0, "age": 0.45, "muscle": 0.92, "weight": 0.62, "height": 0.62, "race": {"caucasian": 0.92, "asian": 0.03, "african": 0.05}},
                        "targets": {"chin-prominent-incr": 0.4, "head-square": 0.5}, "hair": "short04", "hair_tint": "black", "brows": "eyebrow007",
                        "coat": "charcoal", "coat_len": "short", "collar": "charcoal", "apron": "leather", "breeches": "charcoal", "stockings": "grey_coat",
                        "boots": "black", "boot_height": 0.30, "hat": None, "buttons": False, "max_tex": 1024},
    "town_apothecary": {"macro": {"gender": 0.9, "age": 0.74, "muscle": 0.35, "weight": 0.42, "height": 0.5}, "targets": {"head-oval": 0.3, "nose-scale-vert-incr": 0.3},
                        "hair": "short01", "hair_tint": "white", "brows": "eyebrow006", "coat": "black", "coat_len": "long", "collar": "cream",
                        "boots": "black", "boot_height": 0.10, "hat": "cap", "buttons": "long", "button_colour": "pewter", "max_tex": 1024},
    "town_tailor": {"macro": {"gender": 0.88, "age": 0.48, "muscle": 0.35, "weight": 0.38, "height": 0.46, "race": {"caucasian": 0.8, "asian": 0.15, "african": 0.05}},
                    "targets": {"nose-point-width-decr": 0.3, "head-oval": 0.2}, "hair": "ponytail01", "hair_tint": "auburn", "brows": "eyebrow002",
                    "coat": "teal", "coat_len": "mid", "cuffs": "cream", "collar": "cream", "breeches": "black", "stockings": "stocking",
                    "boots": "black", "boot_height": 0.10, "hat": None, "button_colour": "silver", "max_tex": 1024},
    "town_bookseller": {"macro": {"gender": 0.88, "age": 0.33, "muscle": 0.38, "weight": 0.4, "height": 0.58}, "targets": {"head-rectangular": 0.3},
                        "hair": "short03", "hair_tint": "dark_brown", "brows": "eyebrow002", "coat": "grey_coat", "coat_len": "mid", "cuffs": "black", "collar": "cream",
                        "breeches": "charcoal", "stockings": "stocking", "boots": "black", "boot_height": 0.10, "hat": None, "button_colour": "pewter", "max_tex": 1024},
    # Streets and gates
    "town_coachman": {"macro": {"gender": 1.0, "age": 0.55, "muscle": 0.6, "weight": 0.7, "height": 0.56}, "targets": {"chin-width-incr": 0.3, "nose-hump-incr": 0.2},
                      "hair": "ponytail01", "hair_tint": "brown", "brows": "eyebrow003", "coat": "olive", "coat_len": "long", "collar": "brown_coat", "sash": "leather",
                      "boots": "black", "boot_height": 0.38, "hat": "tricorne", "buttons": "long", "button_colour": "brass", "max_tex": 1024},
    "town_customs_officer": {"macro": {"gender": 0.95, "age": 0.44, "muscle": 0.55, "weight": 0.52, "height": 0.6, "race": {"caucasian": 1.0, "asian": 0.0, "african": 0.0}},
                             "targets": {"chin-prominent-incr": 0.2}, "hair": "ponytail01", "hair_tint": "blond", "brows": "eyebrow004",
                             "coat": "grey_white", "coat_len": "mid", "cuffs": "facing_red", "collar": "facing_red", "breeches": "grey_white", "stockings": "stocking",
                             "boots": "black", "boot_height": 0.30, "hat": "tricorne", "sword": True, "button_colour": "brass", "max_tex": 1024},
    "town_washerwoman_f": {"macro": {"gender": 0.08, "age": 0.42, "muscle": 0.6, "weight": 0.45, "height": 0.44, "race": {"caucasian": 0.9, "asian": 0.05, "african": 0.05}},
                           "hair": "braid01", "hair_tint": "red", "brows": "eyebrow011", "coat": "grey_coat", "coat_len": "long", "collar": "cream", "sash": "rope",
                           "boots": None, "hat": None, "buttons": False, "ragged": 0.1, "seed": 21, "max_tex": 1024},
    "town_lamplighter": {"macro": {"gender": 0.92, "age": 0.42, "muscle": 0.45, "weight": 0.36, "height": 0.6},
                         "hair": "short02", "hair_tint": "blond", "brows": "eyebrow001", "coat": "grey_coat", "coat_len": "mid", "collar": "grey_coat",
                         "breeches": "charcoal", "stockings": "grey_coat", "boots": "leather", "boot_height": 0.12, "hat": "cap", "button_colour": "pewter", "max_tex": 1024},
    "town_night_watchman": {"macro": {"gender": 0.95, "age": 0.68, "muscle": 0.5, "weight": 0.58, "height": 0.52}, "targets": {"nose-hump-incr": 0.3, "chin-jaw-drop-incr": 0.2},
                            "hair": "short04", "hair_tint": "grey", "brows": "eyebrow006", "coat": "brown_coat", "coat_len": "long", "collar": "charcoal", "sash": "leather",
                            "boots": "black", "boot_height": 0.30, "hat": "cap", "buttons": "long", "button_colour": "pewter", "max_tex": 1024},
    # Other residents
    "town_armenian_trader": {"macro": {"gender": 0.93, "age": 0.52, "muscle": 0.5, "weight": 0.6, "height": 0.52, "race": {"caucasian": 0.75, "asian": 0.2, "african": 0.05}},
                             "targets": {"nose-hump-incr": 0.5, "chin-width-incr": 0.2}, "hair": "short04", "hair_tint": "black", "brows": "eyebrow007",
                             "coat": "crimson", "coat_len": "long", "sash": "zupan_gold", "collar": "black",
                             "boots": "tan_boot", "boot_height": 0.30, "hat": "fur", "buttons": "long", "button_colour": "brass", "max_tex": 1024},
    "town_ruthenian_carter_f": {"macro": {"gender": 0.06, "age": 0.36, "muscle": 0.55, "weight": 0.5, "height": 0.5, "race": {"caucasian": 0.9, "asian": 0.1, "african": 0.0}},
                                "targets": {"head-square": 0.2}, "hair": "short01", "hair_tint": "dark_brown", "brows": "eyebrow012",
                                "coat": "sukmana", "coat_len": "long", "collar": "cream", "sash": "facing_red",
                                "boots": "leather", "boot_height": 0.30, "hat": "kerchief", "hat_colour": "cream", "buttons": False, "max_tex": 1024},
    # Money, law and the council
    "town_banker": {"macro": {"gender": 0.92, "age": 0.5, "muscle": 0.4, "weight": 0.66, "height": 0.54, "race": {"caucasian": 1.0, "asian": 0.0, "african": 0.0}},
                    "targets": {"head-round": 0.3, "chin-width-incr": 0.2}, "hair": "ponytail01", "hair_tint": "dark_brown", "brows": "eyebrow005",
                    "coat": "grey_coat", "coat_len": "mid", "cuffs": "black", "collar": "cream", "breeches": "black", "stockings": "stocking",
                    "boots": "black", "boot_height": 0.12, "hat": "tricorne", "button_colour": "silver", "max_tex": 1024},
    "town_sejm_deputy": {"macro": {"gender": 0.95, "age": 0.55, "muscle": 0.55, "weight": 0.6, "height": 0.6}, "targets": {"head-square": 0.3, "nose-hump-incr": 0.2},
                         "hair": "short01", "hair_tint": "brown", "brows": "eyebrow007", "coat": "teal", "coat_len": "long", "sash": "zupan_gold", "collar": "zupan_gold",
                         "boots": "tan_boot", "boot_height": 0.35, "hat": "konfederatka", "buttons": "long", "button_colour": "brass", "sword": True, "max_tex": 1024},
    "town_councillor": {"macro": {"gender": 0.9, "age": 0.66, "muscle": 0.4, "weight": 0.58, "height": 0.5}, "targets": {"chin-jaw-drop-incr": 0.2, "head-oval": 0.2},
                        "hair": "short03", "hair_tint": "grey", "brows": "eyebrow004", "coat": "charcoal", "coat_len": "long", "collar": "cream",
                        "boots": "black", "boot_height": 0.10, "hat": "cap", "buttons": "long", "button_colour": "pewter", "max_tex": 1024},
    "town_mayor": {"macro": {"gender": 0.93, "age": 0.6, "muscle": 0.45, "weight": 0.72, "height": 0.56}, "targets": {"head-square": 0.3, "chin-prominent-incr": 0.2},
                   "hair": "ponytail01", "hair_tint": "grey", "brows": "eyebrow005", "coat": "wine", "coat_len": "mid", "cuffs": "black", "collar": "cream", "chain": True,
                   "breeches": "black", "stockings": "stocking", "boots": "black", "boot_height": 0.12, "hat": "tricorne", "button_colour": "brass", "max_tex": 1024},
    "town_judge": {"macro": {"gender": 0.9, "age": 0.72, "muscle": 0.35, "weight": 0.55, "height": 0.52}, "targets": {"nose-scale-vert-incr": 0.3, "chin-prominent-incr": 0.2},
                   "hair": "long01", "hair_tint": "white", "brows": "eyebrow006", "coat": "black", "coat_len": "long", "collar": "white_coat",
                   "boots": "black", "boot_height": 0.10, "hat": "cap", "buttons": "long", "button_colour": "black", "max_tex": 1024},
    "town_advocate": {"macro": {"gender": 0.9, "age": 0.42, "muscle": 0.4, "weight": 0.45, "height": 0.56}, "targets": {"nose-point-width-decr": 0.3, "head-rectangular": 0.2},
                      "hair": "ponytail01", "hair_tint": "black", "brows": "eyebrow002", "coat": "charcoal", "coat_len": "mid", "cuffs": "cream", "collar": "cream",
                      "breeches": "black", "stockings": "stocking", "boots": "black", "boot_height": 0.12, "hat": "tricorne", "buttons": True, "button_colour": "pewter", "max_tex": 1024},
    "town_notary": {"macro": {"gender": 0.9, "age": 0.6, "muscle": 0.35, "weight": 0.4, "height": 0.48, "race": {"caucasian": 0.9, "asian": 0.1, "african": 0.0}},
                    "targets": {"head-oval": 0.3}, "hair": "short01", "hair_tint": "dark_brown", "brows": "eyebrow008", "coat": "grey_coat", "coat_len": "long", "collar": "cream",
                    "boots": "black", "boot_height": 0.10, "hat": "cap", "buttons": "long", "button_colour": "silver", "max_tex": 1024},
    # University
    "town_professor": {"macro": {"gender": 0.9, "age": 0.82, "muscle": 0.3, "weight": 0.42, "height": 0.5}, "targets": {"nose-scale-vert-incr": 0.3, "head-oval": 0.3},
                       "hair": "short04", "hair_tint": "grey", "brows": "eyebrow006", "coat": "black", "coat_len": "long", "collar": "cream",
                       "boots": "black", "boot_height": 0.10, "hat": "cap", "buttons": "long", "button_colour": "black", "max_tex": 1024},
    "town_scholar": {"macro": {"gender": 0.85, "age": 0.44, "muscle": 0.35, "weight": 0.36, "height": 0.58, "race": {"caucasian": 0.9, "asian": 0.05, "african": 0.05}},
                     "hair": "short02", "hair_tint": "brown", "brows": "eyebrow001", "coat": "navy", "coat_len": "mid", "collar": "cream", "cuffs": "cream",
                     "breeches": "charcoal", "stockings": "stocking", "boots": "black", "boot_height": 0.10, "hat": None, "button_colour": "pewter", "max_tex": 1024},
    # Hired swords
    "town_swiss_sergeant": {"macro": {"gender": 1.0, "age": 0.5, "muscle": 0.88, "weight": 0.58, "height": 0.64}, "targets": {"chin-prominent-incr": 0.5, "head-square": 0.4},
                            "hair": "ponytail01", "hair_tint": "auburn", "brows": "eyebrow003", "coat": "leather", "coat_len": "mid", "cuffs": "facing_red", "collar": "leather",
                            "sash": "facing_red", "breeches": "buff", "stockings": "stocking", "boots": "black", "boot_height": 0.38, "hat": "tricorne", "sword": True,
                            "button_colour": "brass", "max_tex": 1024},
    "town_cossack": {"macro": {"gender": 1.0, "age": 0.4, "muscle": 0.75, "weight": 0.5, "height": 0.62, "race": {"caucasian": 0.85, "asian": 0.15, "african": 0.0}},
                     "targets": {"nose-hump-incr": 0.3, "chin-width-incr": 0.3}, "hair": "short04", "hair_tint": "black", "brows": "eyebrow007",
                     "coat": "indigo", "coat_len": "long", "sash": "facing_red", "collar": "black",
                     "boots": "black", "boot_height": 0.38, "hat": "fur", "buttons": "long", "button_colour": "brass", "sword": True, "max_tex": 1024},
}


# ---- District population (docs/ROSTER.md "District roster"); names dist_<role>[_f]
DISTRICT = {
    # Kazimierz: workshops, shops, the synagogue court
    "dist_goldsmith": {"macro": {"gender": 0.93, "age": 0.56, "muscle": 0.4, "weight": 0.55, "height": 0.5, "race": {"caucasian": 0.9, "asian": 0.07, "african": 0.03}},
                       "targets": {"nose-hump-incr": 0.35, "head-oval": 0.2}, "hair": "short01", "hair_tint": "dark_brown", "brows": "eyebrow008",
                       "coat": "black", "coat_len": "long", "collar": "black", "sash": "zupan_gold", "boots": "black", "boot_height": 0.12,
                       "hat": "cap", "hat_colour": "black", "buttons": "long", "button_colour": "brass", "chain": True, "max_tex": 1024},
    "dist_silversmith": {"macro": {"gender": 0.9, "age": 0.38, "muscle": 0.45, "weight": 0.42, "height": 0.55, "race": {"caucasian": 0.9, "asian": 0.08, "african": 0.02}},
                         "targets": {"nose-scale-vert-incr": 0.3}, "hair": "short02", "hair_tint": "black", "brows": "eyebrow002",
                         "coat": "grey_coat", "coat_len": "mid", "cuffs": "silver", "collar": "cream", "apron": "leather", "breeches": "charcoal", "stockings": "stocking",
                         "boots": "black", "boot_height": 0.12, "hat": "cap", "hat_colour": "charcoal", "button_colour": "silver", "max_tex": 1024},
    "dist_jeweller": {"macro": {"gender": 0.92, "age": 0.64, "muscle": 0.35, "weight": 0.6, "height": 0.48, "race": {"caucasian": 0.88, "asian": 0.1, "african": 0.02}},
                      "targets": {"head-round": 0.3, "nose-hump-incr": 0.3}, "hair": "short01", "hair_tint": "grey", "brows": "eyebrow006",
                      "coat": "wine", "coat_len": "long", "collar": "black", "sash": "black", "boots": "black", "boot_height": 0.12,
                      "hat": "fur", "buttons": "long", "button_colour": "silver", "max_tex": 1024},
    "dist_gem_cutter": {"macro": {"gender": 0.88, "age": 0.3, "muscle": 0.35, "weight": 0.38, "height": 0.52, "race": {"caucasian": 0.9, "asian": 0.05, "african": 0.05}},
                        "targets": {"nose-point-width-decr": 0.3, "head-rectangular": 0.2}, "hair": "short03", "hair_tint": "brown", "brows": "eyebrow001",
                        "coat": "teal", "coat_len": "short", "collar": "cream", "apron": "apron", "breeches": "black", "stockings": "stocking",
                        "boots": "leather", "boot_height": 0.10, "hat": "cap", "hat_colour": "black", "buttons": False, "max_tex": 1024},
    "dist_spice_trader": {"macro": {"gender": 0.93, "age": 0.5, "muscle": 0.45, "weight": 0.66, "height": 0.52, "race": {"caucasian": 0.8, "asian": 0.17, "african": 0.03}},
                          "targets": {"chin-width-incr": 0.3, "nose-hump-incr": 0.2}, "hair": "short01", "hair_tint": "black", "brows": "eyebrow007",
                          "coat": "brown_coat", "coat_len": "long", "collar": "saffron", "sash": "saffron", "apron": "apron", "boots": "tan_boot", "boot_height": 0.12,
                          "hat": "fur", "buttons": "long", "button_colour": "brass", "max_tex": 1024},
    # indigo-stained hands are not possible (skin is one material); the trade shows in indigo cloth instead
    "dist_dye_merchant": {"macro": {"gender": 0.92, "age": 0.46, "muscle": 0.45, "weight": 0.5, "height": 0.56, "race": {"caucasian": 0.88, "asian": 0.1, "african": 0.02}},
                          "targets": {"head-square": 0.2, "nose-scale-vert-incr": 0.2}, "hair": "short04", "hair_tint": "dark_brown", "brows": "eyebrow004",
                          "coat": "indigo", "coat_len": "mid", "cuffs": "madder", "collar": "madder", "breeches": "indigo", "stockings": "stocking",
                          "boots": "black", "boot_height": 0.12, "hat": "tricorne", "button_colour": "pewter", "max_tex": 1024},
    "dist_cloth_trader": {"macro": {"gender": 0.9, "age": 0.6, "muscle": 0.4, "weight": 0.52, "height": 0.5, "race": {"caucasian": 0.9, "asian": 0.08, "african": 0.02}},
                          "targets": {"head-oval": 0.3}, "hair": "short01", "hair_tint": "grey", "brows": "eyebrow005",
                          "coat": "dun", "coat_len": "long", "collar": "black", "sash": "dress_blue", "boots": "black", "boot_height": 0.12,
                          "hat": "cap", "hat_colour": "black", "buttons": "long", "button_colour": "black", "max_tex": 1024},
    # rabbi: long black bekishe, gartel sash, fur hat (shtreimel)
    "dist_rabbi": {"macro": {"gender": 0.92, "age": 0.74, "muscle": 0.35, "weight": 0.48, "height": 0.52, "race": {"caucasian": 0.88, "asian": 0.1, "african": 0.02}},
                   "targets": {"nose-scale-vert-incr": 0.3, "head-oval": 0.3}, "hair": "short01", "hair_tint": "white", "brows": "eyebrow006",
                   "coat": "black", "coat_len": "long", "collar": "white_coat", "sash": "black", "boots": "black", "boot_height": 0.12,
                   "hat": "fur", "buttons": "long", "button_colour": "black", "max_tex": 1024},
    "dist_moneylender": {"macro": {"gender": 0.9, "age": 0.62, "muscle": 0.35, "weight": 0.4, "height": 0.48, "race": {"caucasian": 0.9, "asian": 0.08, "african": 0.02}},
                         "targets": {"nose-hump-incr": 0.4, "chin-prominent-incr": 0.2}, "hair": "short01", "hair_tint": "grey", "brows": "eyebrow008",
                         "coat": "charcoal", "coat_len": "long", "collar": "cream", "sash": "black", "boots": "black", "boot_height": 0.12,
                         "hat": "cap", "hat_colour": "black", "buttons": "long", "button_colour": "silver", "max_tex": 1024},
    "dist_market_woman_f": {"macro": {"gender": 0.04, "age": 0.52, "muscle": 0.5, "weight": 0.62, "height": 0.44, "race": {"caucasian": 0.9, "asian": 0.08, "african": 0.02}},
                            "targets": {"head-round": 0.2, "nose-hump-incr": 0.2}, "hair": "short01", "hair_tint": "dark_brown", "brows": "eyebrow010",
                            "coat": "dress_blue", "coat_len": "long", "collar": "cream", "sash": "cream", "apron": "apron",
                            "boots": "black", "boot_height": 0.10, "hat": "kerchief", "hat_colour": "cream", "buttons": False, "max_tex": 1024},
    # Garbary: tanneries, dye vats, the brewery and its propination tavern
    "dist_tanner": {"macro": {"gender": 1.0, "age": 0.44, "muscle": 0.75, "weight": 0.55, "height": 0.56, "race": {"caucasian": 0.95, "asian": 0.03, "african": 0.02}},
                    "targets": {"chin-prominent-incr": 0.3, "head-square": 0.3}, "hair": "short04", "hair_tint": "brown", "brows": "eyebrow007",
                    "coat": "dun", "coat_len": "short", "collar": "dun", "apron": "leather", "breeches": "brown_coat", "stockings": "grey_coat",
                    "boots": "leather", "boot_height": 0.30, "hat": None, "buttons": False, "ragged": 0.1, "seed": 31, "max_tex": 1024},
    "dist_dyer": {"macro": {"gender": 0.95, "age": 0.34, "muscle": 0.6, "weight": 0.45, "height": 0.54},
                  "targets": {"nose-point-width-incr": 0.3}, "hair": "short02", "hair_tint": "red", "brows": "eyebrow001",
                  "coat": "madder", "coat_len": "short", "collar": "indigo", "apron": "indigo", "breeches": "indigo", "stockings": "grey_coat",
                  "boots": "leather", "boot_height": 0.30, "hat": "cap", "hat_colour": "indigo", "buttons": False, "max_tex": 1024},
    "dist_brewer": {"macro": {"gender": 1.0, "age": 0.52, "muscle": 0.6, "weight": 0.88, "height": 0.55}, "targets": {"head-round": 0.4, "chin-width-incr": 0.3},
                    "hair": "short03", "hair_tint": "auburn", "brows": "eyebrow005", "coat": "brown_coat", "coat_len": "short", "collar": "cream", "apron": "apron",
                    "breeches": "leather", "stockings": "stocking", "boots": "leather", "boot_height": 0.30, "hat": "cap", "hat_colour": "hops", "button_colour": "pewter", "max_tex": 1024},
    "dist_maltster": {"macro": {"gender": 0.95, "age": 0.4, "muscle": 0.55, "weight": 0.5, "height": 0.6}, "targets": {"head-rectangular": 0.3},
                      "hair": "short02", "hair_tint": "blond", "brows": "eyebrow003", "coat": "flour", "coat_len": "short", "collar": "flour", "apron": "sukmana",
                      "breeches": "buff", "stockings": "stocking", "boots": "leather", "boot_height": 0.12, "hat": "cap", "hat_colour": "buff", "buttons": False, "max_tex": 1024},
    "dist_distiller": {"macro": {"gender": 0.93, "age": 0.6, "muscle": 0.45, "weight": 0.55, "height": 0.5}, "targets": {"nose-point-width-incr": 0.4, "nose-scale-vert-incr": 0.2},
                       "hair": "short04", "hair_tint": "grey", "brows": "eyebrow004", "coat": "olive", "coat_len": "mid", "collar": "leather", "cuffs": "leather", "apron": "leather",
                       "breeches": "charcoal", "stockings": "grey_coat", "boots": "black", "boot_height": 0.12, "hat": None, "button_colour": "brass", "max_tex": 1024},
    "dist_cellarman": {"macro": {"gender": 1.0, "age": 0.36, "muscle": 0.8, "weight": 0.6, "height": 0.5, "race": {"caucasian": 0.95, "asian": 0.05, "african": 0.0}},
                       "targets": {"head-square": 0.4, "chin-prominent-incr": 0.2}, "hair": "short01", "hair_tint": "black", "brows": "eyebrow007",
                       "coat": "charcoal", "coat_len": "short", "collar": "charcoal", "apron": "leather", "breeches": "leather", "stockings": "grey_coat",
                       "boots": "black", "boot_height": 0.30, "hat": "cap", "hat_colour": "red_cap", "buttons": False, "max_tex": 1024},
    "dist_journeyman": {"macro": {"gender": 0.9, "age": 0.22, "muscle": 0.5, "weight": 0.4, "height": 0.58, "race": {"caucasian": 0.95, "asian": 0.02, "african": 0.03}},
                        "hair": "short02", "hair_tint": "brown", "brows": "eyebrow001", "coat": "rust", "coat_len": "mid", "collar": "cream",
                        "breeches": "grey_coat", "stockings": "stocking", "boots": "leather", "boot_height": 0.12, "hat": "cap", "hat_colour": "grey_coat",
                        "button_colour": "pewter", "ragged": 0.04, "seed": 33, "max_tex": 1024},
    # ekonom: the magnate's propination steward, better dressed than the brewers he squeezes
    "dist_steward": {"macro": {"gender": 0.95, "age": 0.54, "muscle": 0.45, "weight": 0.64, "height": 0.56}, "targets": {"chin-jaw-drop-incr": 0.2, "head-square": 0.2},
                     "hair": "ponytail01", "hair_tint": "dark_brown", "brows": "eyebrow005", "coat": "dress_green", "coat_len": "mid", "cuffs": "zupan_gold", "collar": "cream",
                     "breeches": "buff", "stockings": "stocking", "boots": "black", "boot_height": 0.32, "hat": "tricorne", "chain": True, "button_colour": "brass", "max_tex": 1024},
    "dist_tavern_keeper": {"macro": {"gender": 0.95, "age": 0.48, "muscle": 0.5, "weight": 0.75, "height": 0.5, "race": {"caucasian": 0.9, "asian": 0.08, "african": 0.02}},
                           "targets": {"head-round": 0.3, "nose-hump-incr": 0.2}, "hair": "short01", "hair_tint": "black", "brows": "eyebrow008",
                           "coat": "navy", "coat_len": "short", "collar": "cream", "sash": "livery_blue", "apron": "apron", "breeches": "brown_coat", "stockings": "stocking",
                           "boots": "black", "boot_height": 0.12, "hat": "cap", "hat_colour": "livery_blue", "buttons": False, "max_tex": 1024},
    # Vistula docks: wharf, salt barges, the customs shed
    "dist_porter": {"macro": {"gender": 1.0, "age": 0.3, "muscle": 0.95, "weight": 0.6, "height": 0.6, "race": {"caucasian": 0.92, "asian": 0.03, "african": 0.05}},
                    "targets": {"chin-prominent-incr": 0.4, "head-square": 0.4}, "hair": "short04", "hair_tint": "dark_brown", "brows": "eyebrow003",
                    "coat": "sukmana", "coat_len": "short", "collar": "sukmana", "sash": "rope", "breeches": "brown_coat", "stockings": "grey_coat",
                    "boots": "leather", "boot_height": 0.12, "hat": None, "buttons": False, "ragged": 0.06, "seed": 35, "max_tex": 1024},
    "dist_salt_trader": {"macro": {"gender": 0.93, "age": 0.58, "muscle": 0.45, "weight": 0.68, "height": 0.52}, "targets": {"head-round": 0.3},
                         "hair": "short03", "hair_tint": "grey", "brows": "eyebrow004", "coat": "grey_white", "coat_len": "long", "collar": "charcoal", "sash": "charcoal",
                         "boots": "black", "boot_height": 0.30, "hat": "konfederatka", "buttons": "long", "button_colour": "pewter", "max_tex": 1024},
    "dist_ferryman": {"macro": {"gender": 1.0, "age": 0.66, "muscle": 0.6, "weight": 0.5, "height": 0.52}, "targets": {"nose-hump-incr": 0.3, "chin-prominent-incr": 0.3},
                      "hair": "short04", "hair_tint": "white", "brows": "eyebrow006", "coat": "olive", "coat_len": "mid", "collar": "olive", "sash": "rope",
                      "breeches": "brown_coat", "stockings": "grey_coat", "boots": "leather", "boot_height": 0.30, "hat": "cap", "hat_colour": "brown_coat", "buttons": False, "max_tex": 1024},
    # flisak: Vistula raftsman in a sukmana-style coat and cap
    "dist_raftsman": {"macro": {"gender": 1.0, "age": 0.38, "muscle": 0.8, "weight": 0.5, "height": 0.62}, "targets": {"head-rectangular": 0.3, "chin-width-incr": 0.2},
                      "hair": "long01", "hair_tint": "blond", "brows": "eyebrow001", "coat": "sukmana", "coat_len": "long", "collar": "cream", "sash": "facing_red",
                      "boots": "leather", "boot_height": 0.30, "hat": "cap", "hat_colour": "black", "buttons": False, "max_tex": 1024},
    "dist_customs_clerk": {"macro": {"gender": 0.9, "age": 0.36, "muscle": 0.35, "weight": 0.4, "height": 0.55}, "targets": {"nose-point-width-decr": 0.3},
                           "hair": "ponytail01", "hair_tint": "brown", "brows": "eyebrow002", "coat": "grey_white", "coat_len": "mid", "cuffs": "black", "collar": "black",
                           "breeches": "grey_white", "stockings": "stocking", "boots": "black", "boot_height": 0.12, "hat": "tricorne", "button_colour": "pewter", "max_tex": 1024},
    # Kleparz: grain market, stables, carts
    "dist_grain_dealer": {"macro": {"gender": 0.95, "age": 0.5, "muscle": 0.5, "weight": 0.72, "height": 0.54}, "targets": {"head-square": 0.3, "chin-jaw-drop-incr": 0.2},
                          "hair": "short01", "hair_tint": "brown", "brows": "eyebrow005", "coat": "mustard", "coat_len": "mid", "collar": "brown_coat", "cuffs": "brown_coat",
                          "breeches": "brown_coat", "stockings": "stocking", "boots": "tan_boot", "boot_height": 0.30, "hat": "cap", "hat_colour": "brown_coat", "button_colour": "brass", "max_tex": 1024},
    "dist_horse_dealer": {"macro": {"gender": 1.0, "age": 0.44, "muscle": 0.65, "weight": 0.5, "height": 0.6, "race": {"caucasian": 0.85, "asian": 0.1, "african": 0.05}},
                          "targets": {"nose-hump-incr": 0.4, "head-oval": 0.2}, "hair": "short04", "hair_tint": "black", "brows": "eyebrow007",
                          "coat": "leather", "coat_len": "mid", "collar": "fur", "cuffs": "fur", "sash": "facing_red", "breeches": "buff",
                          "boots": "black", "boot_height": 0.40, "hat": "krakuska", "buttons": False, "sword": False, "max_tex": 1024},
    "dist_carter": {"macro": {"gender": 1.0, "age": 0.5, "muscle": 0.65, "weight": 0.55, "height": 0.55}, "targets": {"chin-prominent-incr": 0.3},
                    "hair": "short02", "hair_tint": "dark_brown", "brows": "eyebrow003", "coat": "brown_coat", "coat_len": "mid", "collar": "brown_coat", "sash": "leather",
                    "breeches": "grey_coat", "stockings": "grey_coat", "boots": "leather", "boot_height": 0.38, "hat": "cap", "hat_colour": "grey_coat", "buttons": False, "max_tex": 1024},
    "dist_peasant": {"macro": {"gender": 1.0, "age": 0.58, "muscle": 0.6, "weight": 0.45, "height": 0.52}, "targets": {"head-rectangular": 0.3, "nose-scale-vert-incr": 0.2},
                     "hair": "long01", "hair_tint": "grey", "brows": "eyebrow006", "coat": "sukmana", "coat_len": "long", "collar": "sukmana", "sash": "facing_red",
                     "boots": "leather", "boot_height": 0.30, "hat": "krakuska", "buttons": False, "max_tex": 1024},
    "dist_peasant_f": {"macro": {"gender": 0.06, "age": 0.3, "muscle": 0.55, "weight": 0.5, "height": 0.46}, "targets": {"head-round": 0.2},
                       "hair": "braid01", "hair_tint": "blond", "brows": "eyebrow009", "coat": "sukmana", "coat_len": "long", "collar": "cream", "sash": "facing_red", "apron": "apron",
                       "boots": "leather", "boot_height": 0.30, "hat": "kerchief", "hat_colour": "kerchief_red", "buttons": False, "max_tex": 1024},
    # Foreign residents and traders
    "dist_armenian_merchant": {"macro": {"gender": 0.94, "age": 0.62, "muscle": 0.45, "weight": 0.64, "height": 0.5, "race": {"caucasian": 0.72, "asian": 0.25, "african": 0.03}},
                               "targets": {"nose-hump-incr": 0.5, "head-oval": 0.2}, "hair": "short01", "hair_tint": "grey", "brows": "eyebrow007",
                               "coat": "ottoman_green", "coat_len": "long", "collar": "zupan_gold", "sash": "saffron",
                               "boots": "tan_boot", "boot_height": 0.30, "hat": "fur", "buttons": "long", "button_colour": "brass", "max_tex": 1024},
    "dist_greek_merchant": {"macro": {"gender": 0.93, "age": 0.46, "muscle": 0.5, "weight": 0.55, "height": 0.54, "race": {"caucasian": 0.82, "asian": 0.12, "african": 0.06}},
                            "targets": {"nose-scale-vert-incr": 0.3, "chin-prominent-incr": 0.2}, "hair": "short04", "hair_tint": "black", "brows": "eyebrow004",
                            "coat": "dress_blue", "coat_len": "long", "collar": "black", "sash": "crimson",
                            "boots": "black", "boot_height": 0.30, "hat": "cap", "hat_colour": "red_cap", "buttons": "long", "button_colour": "silver", "max_tex": 1024},
    # Ottoman subjects traded at Kraków fairs, but a resident Turk is thin; no turban asset exists, so the "fur" hat stands in
    # (hat_colour cream is set for when fur hats take a colour; today the fur hat is always fur-brown)
    "dist_turkish_merchant": {"macro": {"gender": 0.95, "age": 0.55, "muscle": 0.5, "weight": 0.66, "height": 0.55, "race": {"caucasian": 0.65, "asian": 0.3, "african": 0.05}},
                              "targets": {"nose-hump-incr": 0.4, "chin-width-incr": 0.3}, "hair": "short01", "hair_tint": "black", "brows": "eyebrow007",
                              "coat": "crimson", "coat_len": "long", "collar": "ottoman_green", "sash": "ottoman_green",
                              "boots": "saffron", "boot_height": 0.12, "hat": "fur", "hat_colour": "cream", "buttons": "long", "button_colour": "brass", "max_tex": 1024},
    # Persian carpets came mostly through Armenian middlemen; a Persian dealer in person is plausible but rare
    "dist_persian_carpet_dealer": {"macro": {"gender": 0.93, "age": 0.5, "muscle": 0.4, "weight": 0.5, "height": 0.52, "race": {"caucasian": 0.55, "asian": 0.42, "african": 0.03}},
                                   "targets": {"nose-scale-vert-incr": 0.3, "head-oval": 0.3}, "hair": "short01", "hair_tint": "black", "brows": "eyebrow008",
                                   "coat": "madder", "coat_len": "long", "collar": "indigo", "sash": "indigo",
                                   "boots": "black", "boot_height": 0.12, "hat": "fur", "buttons": False, "max_tex": 1024},
    # Lipka Tatar: Polish-Lithuanian Muslim, often a light-cavalry veteran (asian just above 0.5 so pick_skin chooses the asian skin)
    "dist_tatar": {"macro": {"gender": 1.0, "age": 0.4, "muscle": 0.7, "weight": 0.5, "height": 0.56, "race": {"caucasian": 0.48, "asian": 0.52, "african": 0.0}},
                   "targets": {"head-round": 0.2, "chin-width-incr": 0.3}, "hair": "short04", "hair_tint": "black", "brows": "eyebrow003",
                   "coat": "sky_blue", "coat_len": "long", "collar": "black", "sash": "crimson",
                   "boots": "black", "boot_height": 0.38, "hat": "fur", "buttons": "long", "button_colour": "brass", "sword": True, "max_tex": 1024},
    "dist_hungarian_wine_merchant": {"macro": {"gender": 0.95, "age": 0.52, "muscle": 0.55, "weight": 0.62, "height": 0.58}, "targets": {"nose-hump-incr": 0.3, "head-square": 0.2},
                                     "hair": "short03", "hair_tint": "dark_brown", "brows": "eyebrow005", "coat": "wine", "coat_len": "mid", "cuffs": "zupan_gold", "collar": "zupan_gold",
                                     "sash": "zupan_gold", "breeches": "sky_blue", "boots": "black", "boot_height": 0.40, "hat": "fur", "buttons": True, "button_colour": "brass", "max_tex": 1024},
    "dist_italian_architect": {"macro": {"gender": 0.9, "age": 0.48, "muscle": 0.4, "weight": 0.42, "height": 0.56, "race": {"caucasian": 0.95, "asian": 0.02, "african": 0.03}},
                               "targets": {"nose-scale-vert-incr": 0.3, "head-oval": 0.3}, "hair": "ponytail01", "hair_tint": "black", "brows": "eyebrow002",
                               "coat": "charcoal", "coat_len": "mid", "cuffs": "cream", "collar": "cream", "breeches": "charcoal", "stockings": "stocking",
                               "boots": "black", "boot_height": 0.10, "hat": "tricorne", "button_colour": "silver", "max_tex": 1024},
    "dist_german_master": {"macro": {"gender": 0.95, "age": 0.6, "muscle": 0.55, "weight": 0.66, "height": 0.56}, "targets": {"head-square": 0.3, "chin-prominent-incr": 0.2},
                           "hair": "ponytail01", "hair_tint": "blond", "brows": "eyebrow004", "coat": "brown_coat", "coat_len": "mid", "cuffs": "black", "collar": "black",
                           "apron": "leather", "breeches": "black", "stockings": "stocking", "boots": "black", "boot_height": 0.12, "hat": "tricorne", "button_colour": "pewter", "max_tex": 1024},
    "dist_scottish_pedlar": {"macro": {"gender": 1.0, "age": 0.42, "muscle": 0.5, "weight": 0.38, "height": 0.56}, "targets": {"nose-point-width-incr": 0.3, "chin-prominent-incr": 0.2},
                             "hair": "short02", "hair_tint": "red", "brows": "eyebrow001", "coat": "dun", "coat_len": "mid", "collar": "dun", "sash": "leather",
                             "breeches": "olive", "stockings": "grey_coat", "boots": "leather", "boot_height": 0.12, "hat": "cap", "hat_colour": "navy", "buttons": False,
                             "ragged": 0.05, "seed": 41, "max_tex": 1024},
    "dist_french_emigre": {"macro": {"gender": 0.88, "age": 0.44, "muscle": 0.35, "weight": 0.4, "height": 0.56}, "targets": {"nose-point-width-decr": 0.3, "head-oval": 0.3},
                           "hair": "ponytail01", "hair_tint": "white", "brows": "eyebrow002", "coat": "sky_blue", "coat_len": "mid", "cuffs": "silver", "collar": "cream",
                           "breeches": "cream", "stockings": "stocking", "boots": "black", "boot_height": 0.10, "hat": "tricorne", "button_colour": "silver", "sword": True, "max_tex": 1024},
    "dist_flemish_journeyman": {"macro": {"gender": 0.9, "age": 0.27, "muscle": 0.45, "weight": 0.45, "height": 0.6}, "targets": {"head-rectangular": 0.3},
                                "hair": "short02", "hair_tint": "blond", "brows": "eyebrow001", "coat": "grey_coat", "coat_len": "short", "collar": "cream", "apron": "apron",
                                "breeches": "charcoal", "stockings": "stocking", "boots": "leather", "boot_height": 0.10, "hat": None, "button_colour": "pewter", "max_tex": 1024},
    # artistic liberty: an Indian trader in Kraków via Ottoman and Armenian routes is not documented; kept as a rare figure
    "dist_indian_trader": {"macro": {"gender": 0.93, "age": 0.45, "muscle": 0.45, "weight": 0.45, "height": 0.52, "race": {"caucasian": 0.3, "asian": 0.35, "african": 0.35}},
                           "targets": {"nose-scale-vert-incr": 0.2, "head-oval": 0.3}, "hair": "short01", "hair_tint": "black", "brows": "eyebrow008",
                           "coat": "cream", "coat_len": "long", "collar": "saffron", "sash": "saffron",
                           "boots": "tan_boot", "boot_height": 0.10, "hat": "kerchief", "hat_colour": "saffron", "buttons": False, "max_tex": 1024},
}


def crowd_specs(n_men=8, n_women=8, seed=1795):
    """Seeded background townsfolk: varied skin, age, build, hair style and colour, cloth colours, hats."""
    rng = random.Random(seed)
    coats_m = ["brown_coat", "grey_coat", "olive", "rust", "charcoal", "navy", "mustard", "dress_blue", "teal", "wine"]
    coats_f = ["sage", "dress_blue", "dress_green", "dress_plum", "rust", "grey_coat", "mustard", "teal", "wine", "brown_coat"]
    hair_m = ["short01", "short02", "short03", "short04", "ponytail01"]
    hair_f = ["bob01", "bob02", "braid01", "long01", "ponytail01", "short01"]
    tints = ["black", "dark_brown", "brown", "auburn", "blond", "grey", "red"]
    hats_m = ["cap", "tricorne", None, "cap", None, "krakuska"]
    hats_f = ["bonnet", "kerchief", None, "kerchief", "bonnet"]
    out = {}
    for i in range(n_men + n_women):
        f = i >= n_men
        race = rng.choice([{"caucasian": 0.9, "asian": 0.05, "african": 0.05}] * 8 + [{"caucasian": 0.5, "asian": 0.5, "african": 0.0}, {"caucasian": 0.4, "asian": 0.0, "african": 0.6}])
        age = rng.uniform(0.25, 0.75)
        spec = {"macro": {"gender": rng.uniform(0.0, 0.15) if f else rng.uniform(0.85, 1.0), "age": age, "muscle": rng.uniform(0.35, 0.7),
                          "weight": rng.uniform(0.35, 0.75), "height": rng.uniform(0.4, 0.65), "race": race},
                "targets": {rng.choice(["head-round", "head-oval", "head-square", "head-rectangular"]): rng.uniform(0.1, 0.4),
                            rng.choice(["nose-hump-incr", "nose-scale-vert-incr", "nose-point-width-incr", "chin-prominent-incr", "chin-width-incr"]): rng.uniform(0.1, 0.5)},
                "hair": rng.choice(hair_f if f else hair_m), "hair_tint": rng.choice(tints), "brows": "eyebrow%03d" % rng.randint(1, 12),
                "coat": rng.choice(coats_f if f else coats_m), "coat_len": "long" if f else rng.choice(["mid", "mid", "long", "short"]),
                "collar": rng.choice(["cream", "stocking", None]), "sash": rng.choice([None, "cream", "rope", "black", "facing_red"]) if f or rng.random() < 0.4 else None,
                "breeches": rng.choice(["buff", "charcoal", "grey_coat", "brown_coat"]), "stockings": rng.choice(["stocking", "grey_coat"]),
                "boots": rng.choice(["leather", "black", "tan_boot"]), "boot_height": rng.choice([0.10, 0.12, 0.30]),
                "hat": rng.choice(hats_f if f else hats_m), "hat_colour": rng.choice(["cream", "kerchief_red", "grey_coat", "sage"]),
                "buttons": (not f) and rng.random() < 0.6, "button_colour": rng.choice(["pewter", "brass", "black"]), "max_tex": 1024, "seed": i}
        if spec["hat"] in ("bonnet", "kerchief"):
            spec["hair"] = "short01"
        if spec["hat"] == "tricorne":
            spec["hair"] = rng.choice(["short01", "ponytail01"])
        out["npc_%s_%02d" % ("f" if f else "m", i - n_men if f else i)] = spec
    return out


ALL = dict(CHARACTERS)
ALL.update(CAST)
ALL.update(TOWNSFOLK)
ALL.update(DISTRICT)
ALL.update(crowd_specs())


if __name__ == "__main__":
    only = None
    if "--" in sys.argv:
        only = sys.argv[sys.argv.index("--") + 1:]
    for name, spec in ALL.items():
        if only and name not in only and not (only == ["cast"] and name.startswith("cast_")) and not (only == ["npc"] and name.startswith("npc_")) and not (only == ["townsfolk"] and name.startswith("town_")) and not (only == ["district"] and name.startswith("dist_")) and not (only == ["base"] and (name.startswith("figure_") or name == "watchman")):
            continue
        build(name, spec)
    log("done")
