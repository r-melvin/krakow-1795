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
from mathutils import noise as mnoise

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
    "hops": (0.46, 0.50, 0.24), "dun": (0.52, 0.46, 0.36), "straw": (0.86, 0.74, 0.48),
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


TEX_DIR = os.path.join(ROOT, "assets", "textures")
LINEN = {"cream", "apron", "wimple", "flour", "stocking", "grey_white", "white_coat_linen"}
SILK = {"zupan_gold", "crimson", "purple", "saffron", "ottoman_green", "sky_blue"}
# normal-map strength per surface kind: wool shows its folds and twill, silk is smooth, fur and straw are deep
NSTR = {"cloth": 2.2, "linen": 1.5, "silk": 0.8, "fur": 2.4, "felt": 1.1, "straw": 1.8, "leather": 0.9}


def _np():
    import numpy
    return numpy


def _img_arr(path):
    np = _np()
    im = bpy.data.images.load(path, check_existing=False)
    w, hh = im.size
    a = np.empty(w * hh * 4, np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    return a.reshape(hh, w, 4)[..., :3].copy()


def _save_png(path, arr):
    np = _np()
    hh, w = arr.shape[:2]
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=2)
    im = bpy.data.images.new("_tmp_" + os.path.basename(path), w, hh, alpha=False)
    rgba = np.ones((hh, w, 4), np.float32)
    rgba[..., :3] = np.clip(arr, 0.0, 1.0)
    im.pixels.foreach_set(rgba.ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)


def _band_noise(res, lo, hi, seed, aniso=(1.0, 1.0)):
    """Tileable band-limited noise (cycles per tile between lo and hi), zero mean, unit deviation."""
    np = _np()
    rng = np.random.default_rng(seed)
    F = np.fft.fft2(rng.standard_normal((res, res)))
    fy = np.fft.fftfreq(res)[:, None] * res * aniso[1]
    fx = np.fft.fftfreq(res)[None, :] * res * aniso[0]
    r = np.sqrt(fx * fx + fy * fy)
    mask = ((r >= lo) & (r <= hi)).astype(np.float64)
    n = np.real(np.fft.ifft2(F * mask))
    return (n - n.mean()) / (n.std() + 1e-9)


def _normal_from_height(hgt, strength):
    np = _np()
    dx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) * 0.5 * strength
    dy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) * 0.5 * strength
    n = np.stack([-dx, -dy, np.ones_like(hgt)], axis=2)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def _char_tex(kind):
    """Costume textures generated with numpy and cached in assets/textures/char_<kind>_{col,rough,nrm}.png.
    Colour maps are near-white so M() tints them with the COL entry.
      clothc  wool: the baked cloth from build_assets with its fold and wear contrast lifted
      fur     curly lambskin (astrakhan) and fox/sable pile for kolpaks, otoks and tufts
      felt    fulled felt for hats: mottled, fine fuzz
      straw   plaited straw braid sewn round in bands (straw hats)"""
    paths = {k: os.path.join(TEX_DIR, "char_%s_%s.png" % (kind, k)) for k in ("col", "rough", "nrm")}
    if all(os.path.exists(p) for p in paths.values()):
        return paths
    np = _np()
    res = 512
    if kind == "clothc":
        base = _cloth_textures()
        col = _img_arr(base["col"])
        nrm = _img_arr(base["nrm"])
        lum = col.mean(axis=2, keepdims=True)
        mott = _band_noise(col.shape[0], 2, 6, 11)[..., None]
        col = 0.86 + (col - lum.mean()) * 2.2 + mott * 0.015
        xy = (nrm[..., :2] - 0.5) * 1.6
        z = np.sqrt(np.clip(1.0 - (xy ** 2).sum(axis=2), 0.05, 1.0))
        nrm = np.concatenate([xy + 0.5, z[..., None] * 0.5 + 0.5], axis=2)
        rough = np.full(col.shape[:2], 0.9) + mott[..., 0] * 0.02
        _save_png(paths["col"], col)
        _save_png(paths["nrm"], nrm)
        _save_png(paths["rough"], rough)
        return paths
    if kind == "fur":
        c1 = _band_noise(res, 34, 60, 1)
        c2 = _band_noise(res, 20, 34, 2)
        curl = np.clip(1.0 - np.abs(c1) * 0.9, 0, 1) ** 2 * 0.65 + np.clip(1.0 - np.abs(c2) * 0.9, 0, 1) ** 2 * 0.35
        clump = _band_noise(res, 3, 9, 3)
        fine = _band_noise(res, 120, 250, 4)
        hgt = curl * 0.8 + clump * 0.08 + fine * 0.05
        col = 0.52 + curl * 0.55 + clump * 0.05 + fine * 0.04
        rough = 0.93 - curl * 0.06
        nrm = _normal_from_height(hgt, 9.0)
    elif kind == "felt":
        m1 = _band_noise(res, 2, 8, 5)
        m2 = _band_noise(res, 30, 80, 6)
        fz = _band_noise(res, 150, 256, 7)
        hgt = m1 * 0.3 + m2 * 0.25 + fz * 0.45
        col = 0.86 + m1 * 0.035 + m2 * 0.02 + fz * 0.03
        rough = 0.9 + fz * 0.02
        nrm = _normal_from_height(hgt, 0.9)
    elif kind == "straw":
        yy, xx = np.mgrid[0:res, 0:res] / res
        rows = 18                                    # plait rows per tile
        s = (yy * rows) % 1.0
        half = np.where(s < 0.5, 1.0, -1.0)
        phase = xx * 64 + half * s * 3.0
        strand = 0.5 + 0.5 * np.cos(phase * math.tau)
        edge = np.clip(np.minimum(s, 1 - s) * 12, 0, 1) * np.clip(np.abs(s - 0.5) * 16, 0, 1)
        fib = _band_noise(res, 90, 220, 8, aniso=(0.25, 1.0))
        tone = _band_noise(res, 3, 12, 9)
        hgt = strand * edge * 0.8 + fib * 0.06
        col = 0.72 + strand * edge * 0.28 + fib * 0.04 + tone * 0.05 - (1 - edge) * 0.25
        rough = 0.72 + (1 - strand) * 0.12
        nrm = _normal_from_height(hgt, 6.0)
    else:
        raise KeyError(kind)
    _save_png(paths["col"], col)
    _save_png(paths["rough"], rough)
    _save_png(paths["nrm"], nrm)
    return paths


def _rough_map(src, rough):
    """Roughness map re-centred on `rough` (cached), so wool, linen and silk differ while keeping texture."""
    path = src.replace("_rough.png", "_rough%02d.png" % int(round(rough * 100)))
    if not os.path.exists(path):
        np = _np()
        a = _img_arr(src)[..., 0]
        _save_png(path, np.clip(rough + (a - a.mean()) * 1.5, 0.05, 1.0))
    return path


def M(key, rough=None, tex=None, nstr=None):
    """Material for a COL key. tex: None (wool/linen/silk cloth texture for cloth keys, plain otherwise), "plain",
    "cloth", "silk", "fur", "felt", "straw". Roughness and normal strength follow the kind of cloth."""
    if tex is None:
        tex = "plain" if (key in NOT_CLOTH or key not in COL) else "cloth"
    if tex != "plain" and key not in COL:
        tex = "plain"
    if rough is None:
        rough = {"plain": 0.85, "cloth": 0.9 if key in LINEN else 0.93, "silk": 0.55, "fur": 0.95, "felt": 0.9, "straw": 0.8}[tex]
    ck = (key, tex, round(rough, 2))
    if ck in _mats:
        return _mats[ck]
    m = bpy.data.materials.new("cloth_%s%s_%02d" % (key, "" if tex in ("cloth", "plain") else "_" + tex, int(round(rough * 100))))
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = rough
    if tex == "plain":
        b.inputs["Base Color"].default_value = (*COL.get(key, (0.5, 0.5, 0.5)), 1.0)
    else:
        paths = _char_tex("clothc" if tex in ("cloth", "silk") else tex)
        if nstr is None:
            nstr = NSTR["linen" if (tex == "cloth" and key in LINEN) else tex]
        def img(p, colour):
            im = bpy.data.images.load(p, check_existing=True)
            im.colorspace_settings.name = "sRGB" if colour else "Non-Color"
            return im
        tc = nt.nodes.new("ShaderNodeTexImage"); tc.image = img(paths["col"], True)
        tn = nt.nodes.new("ShaderNodeTexImage"); tn.image = img(paths["nrm"], False)
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        nt.links.new(tc.outputs["Color"], mix.inputs[6])
        mix.inputs[7].default_value = (*COL[key], 1.0)
        nt.links.new(mix.outputs[2], b.inputs["Base Color"])
        if tex != "silk":
            tr = nt.nodes.new("ShaderNodeTexImage"); tr.image = img(_rough_map(paths["rough"], rough), False)
            nt.links.new(tr.outputs["Color"], b.inputs["Roughness"])
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = nstr
        nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    _mats[ck] = m
    MAT_KEY[m.name] = key
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


DRAPE = {"coat", "coat_skirt", "skirt", "breeches"}
DRAPE_CTX = {}
GARMENT_EXTRA = []      # seam strips made inside garment(), collected by build_clothes
MAT_KEY = {}
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
    # weld: the helper has split vertices (e.g. along the top of the shoulder) that open up when the arm is raised
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0005)
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
    if name == "boot_foot":
        # the foot skin is dense (toes); a boot does not need it
        dc = obj.modifiers.new("dec", "DECIMATE")
        dc.ratio = 0.35
        bpy.ops.object.modifier_apply(modifier="dec")
    if name == "coat_skirt" and DRAPE_CTX.get("vent"):
        vent_split(obj, DRAPE_CTX)
    hem = drape(obj, name, rig, DRAPE_CTX) if (name in DRAPE and DRAPE_CTX) else None
    seams, n_pre = seam_prepare(obj, name, DRAPE_CTX, hem) if (name in SEAMED and DRAPE_CTX) else (None, 0)
    sol = obj.modifiers.new("solid", "SOLIDIFY")
    sol.thickness = thickness + 0.014
    sol.offset = offset       # 0 = both sides of the helper surface (robust to inward normals); >0 pushes outward
    sol.use_even_offset = False
    sol.thickness_clamp = 1.0
    sol.use_rim = True
    if hem:
        # double-folded hem: the free lower edges are ~8 mm thicker than the body of the cloth
        vg = obj.vertex_groups.new(name="_hem")
        for vi, w in hem.items():
            vg.add([vi], w, "REPLACE")
        sol.vertex_group = "_hem"
        sol.thickness_vertex_group = sol.thickness / (sol.thickness + 0.008)
        sol.thickness = sol.thickness + 0.008
    bpy.ops.object.modifier_apply(modifier="solid")
    if hem:
        obj.vertex_groups.remove(obj.vertex_groups["_hem"])
    if name in ("skirt", "coat_skirt", "coat") and DRAPE_CTX:
        skirt_weights(obj, rig, DRAPE_CTX)
    if seams:
        so = seam_build(obj, seams, n_pre, MAT_KEY.get(mat.name, "charcoal"), rig, DRAPE_CTX)
        if so:
            GARMENT_EXTRA.append(so)
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


def apron_panel(pts, rig, waist_z, knee_z, mat, bones, pad=0.03, bones_by_z=None, half_w=0.17, stiff=False):
    """Flat cloth panel hanging from the waist in front of the body (front is -Y), following the silhouette."""
    rows = []
    n_rows = 10
    n_cols = 37
    for i in range(n_rows):
        z = waist_z + 0.03 - (waist_z + 0.03 - (knee_z + 0.04)) * i / (n_rows - 1)
        ring = silhouette_ring(pts, z, pad, n=48, bones=bones)
        row = []
        for j in range(n_cols):
            t = i / (n_rows - 1)
            hw_i = half_w * (0.82 + 0.3 * t)                # gathered at the waist, spreading to the hem
            x = -hw_i + 2 * hw_i * j / (n_cols - 1)
            # front-most ring point near this x
            best = min((p for p in ring if abs(p[0] - x) < 0.06), key=lambda p: p[1], default=None)
            y = (best[1] if best else min(p[1] for p in ring)) - 0.01
            # gathered into the waistband: fine pleats at the top opening into fewer, deeper folds at the hem
            t = i / (n_rows - 1)
            # nine pleats gathered into the waistband, fanning out and deepening toward the hem
            ph = (j / (n_cols - 1)) * 9 * math.tau + 0.6 * _nz((x, 0, z), 5.0) * t
            pleat = abs(math.sin(ph / 2)) ** 0.7
            y -= (0.009 * (1 - t) + 0.03 * t ** 1.1) * pleat * (0.35 if stiff else 1.0)
            row.append((x, y, z + 0.014 * t ** 3 * (pleat - 0.5) * (0.35 if stiff else 1.0)))
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


def buttons(surf, rig, z_lo, z_hi, n, mat, bones_by_z, x=0.0, hole=None):
    """Row of domed buttons on the garment's front surface (front is -Y), each with a worked buttonhole beside it."""
    out = []
    for i in range(n):
        z = z_lo + (z_hi - z_lo) * i / max(1, n - 1)
        y = _surface_y(surf, x, z, True, win=0.018)
        if y is None:
            continue
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=5, radius=0.0095, location=(x, y - 0.002, z))
        b = bpy.context.object
        b.scale.y = 0.45
        bpy.ops.object.transform_apply(scale=True)
        bpy.ops.object.shade_smooth()
        b.data.materials.append(mat)
        b.name = "button"
        bone = next((bn for (zz, bn) in bones_by_z if z >= zz), bones_by_z[-1][1])
        _weight_to_bone(b, rig, bone)
        out.append(b)
        if hole:
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x - 0.016, y - 0.0008, z))
            hb = bpy.context.object
            hb.scale = (0.022, 0.002, 0.0038)
            bpy.ops.object.transform_apply(scale=True)
            hb.data.materials.append(hole)
            hb.name = "buttonhole"
            _weight_to_bone(hb, rig, bone)
            out.append(hb)
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


# ------------------------------------------------------------------ mesh tools for costume details
def _nz(p, s=1.0, off=0.0):
    """Perlin noise in -1..1 at a position (scaled)."""
    return mnoise.noise(Vector((p[0] * s + off, p[1] * s - off * 0.7, p[2] * s + off * 0.3)))


def _grid(bm, rows, closed=True, close_rows=False, cap_top=None, cap_bot=None):
    """Quad strips between consecutive rows of points (all rows the same length). Optional fan caps."""
    V = [[bm.verts.new(p) for p in r] for r in rows]
    n, m = len(rows[0]), len(rows)
    for i in range(m - 1 + (1 if close_rows else 0)):
        a, b = V[i], V[(i + 1) % m]
        for k in range(n if closed else n - 1):
            k2 = (k + 1) % n
            try:
                bm.faces.new((a[k], a[k2], b[k2], b[k]))
            except ValueError:
                pass
    for cap, row, rev in ((cap_top, V[-1], False), (cap_bot, V[0], True)):
        if cap is None:
            continue
        c = bm.verts.new(cap)
        for k in range(n if closed else n - 1):
            q = (row[k], row[(k + 1) % n], c)
            try:
                bm.faces.new(q[::-1] if rev else q)
            except ValueError:
                pass
    return V


def _frames(path, closed=False, hint=None):
    """Tangent / normal / binormal along a polyline by parallel transport. `hint` seeds the first normal."""
    n = len(path)
    T = []
    for i in range(n):
        a = path[(i - 1) % n] if (closed or i > 0) else path[i]
        b = path[(i + 1) % n] if (closed or i < n - 1) else path[i]
        t = (b - a)
        T.append(t.normalized() if t.length > 1e-9 else Vector((0, 0, 1)))
    up = Vector(hint) if hint is not None else Vector((0, 0, 1))
    if abs(up.normalized().dot(T[0])) > 0.95:
        up = Vector((1, 0, 0))
    N = [(up - T[0] * up.dot(T[0])).normalized()]
    for i in range(1, n):
        v = N[-1] - T[i] * N[-1].dot(T[i])
        N.append(v.normalized() if v.length > 1e-9 else N[-1])
    return T, N, [t.cross(nn) for t, nn in zip(T, N)]


def _sweep(bm, path, profile, closed=False, hint=None, scale=None, caps=True):
    """Sweep a closed 2D profile [(a, b) along normal/binormal] along a polyline. scale(i) tapers it."""
    T, N, Bn = _frames(path, closed, hint)
    rows = []
    for i, p in enumerate(path):
        s = scale(i / max(1, len(path) - 1)) if scale else 1.0
        rows.append([p + N[i] * (a * s) + Bn[i] * (b * s) for a, b in profile])
    return _grid(bm, rows, closed=True, close_rows=closed,
                 cap_top=(path[-1] if caps and not closed else None), cap_bot=(path[0] if caps and not closed else None))


def _circle(r, k=6, sy=1.0):
    return [(r * math.cos(math.tau * i / k), r * sy * math.sin(math.tau * i / k)) for i in range(k)]


def _mk(name, bm, mat, rig, bone="head", angle=50, uv=0.4, solid=0.0, solid_off=0.0, sub=0, recalc=True):
    """bmesh -> skinned object: optional solidify / subsurf, smooth-by-angle shading, cube UVs, welded to a bone."""
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    me.materials.append(mat)
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    if sub:
        sm = o.modifiers.new("s", "SUBSURF"); sm.levels = sub
        bpy.ops.object.modifier_apply(modifier="s")
    if solid:
        so = o.modifiers.new("solid", "SOLIDIFY"); so.thickness = solid; so.offset = solid_off; so.use_rim = True
        bpy.ops.object.modifier_apply(modifier="solid")
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    unwrap(o, uv)
    if bone:
        _weight_to_bone(o, rig, bone)
    return o


def _obj_points(obj):
    """World-space vertex positions of an object as evaluated now (fitted MPFB assets)."""
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    ps = [obj.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return ps


class HeadField:
    """Outline of skull + hair around a fixed centre, per angle and height (convex support radius), so hats can
    be lofted a set distance off the head at any height without clipping hair."""
    def __init__(self, pts, cx, cy, n, z0, z1, step=0.008, band=0.03):
        self.cx, self.cy, self.n, self.z0, self.step = cx, cy, n, z0, step
        self.dirs = [(math.cos(math.tau * k / n), math.sin(math.tau * k / n)) for k in range(n)]
        self.levels = []
        z = z0
        while z <= z1 + 1e-6:
            sl = [(p.x - cx, p.y - cy) for p in pts if abs(p.z - z) < step * 0.75]
            radii = []
            for dx, dy in self.dirs:
                best = 0.0
                for rx, ry in sl:
                    d = rx * dx + ry * dy
                    if d > best and abs(rx * dy - ry * dx) < band:
                        best = d
                radii.append(best)
            self.levels.append(radii)
            z += step

    def r(self, k, z):
        f = (z - self.z0) / self.step
        i = max(0, min(len(self.levels) - 2, int(math.floor(f))))
        t = max(0.0, min(1.0, f - i))
        k %= self.n
        return self.levels[i][k] * (1 - t) + self.levels[i + 1][k] * t

    def rmax(self, k, za, zb):
        """Largest radius over a height range (clearance for a band)."""
        lo, hi = min(za, zb), max(za, zb)
        steps = max(2, int((hi - lo) / (self.step * 0.5)) + 1)
        return max(self.r(k, lo + (hi - lo) * j / (steps - 1)) for j in range(steps))

    def at(self, k, z, r):
        dx, dy = self.dirs[k % self.n]
        return Vector((self.cx + dx * r, self.cy + dy * r, z))

    def radial(self, k):
        dx, dy = self.dirs[k % self.n]
        return Vector((dx, dy, 0.0))


def tilt_z(a, zf, zs, zb):
    """Height of a hat edge at angle a (0 = +X, -pi/2 = front): front zf, sides zs, back zb, smoothly blended."""
    s = math.sin(a)
    if s < 0:
        return zs + (zf - zs) * (-s) ** 1.4
    return zs + (zb - zs) * s ** 1.4


def _surface_y(surf, x, z, front=True, win=0.025):
    """Front-most (or back-most) garment surface y at (x, z)."""
    sl = [p.y for p in surf if abs(p.x - x) < win and abs(p.z - z) < win]
    if not sl:
        sl = [p.y for p in surf if abs(p.x - x) < win * 2.5 and abs(p.z - z) < win * 2.5]
    if not sl:
        return None
    return min(sl) if front else max(sl)


def surface_panel(name, surf, quad, mat, rig, bones_by_z, lift=0.004, thick=0.004, rows=6, cols=5, front=True, curl=0.0):
    """Flat cloth panel (lapel, waistcoat front, pocket flap) laid on a garment's surface: quad = four (x, z) corners
    TL, TR, BR, BL, projected onto the front (or back) of `surf` and lifted off it. curl lifts the outer edge."""
    (x0, z0), (x1, z1), (x2, z2), (x3, z3) = quad
    grid = []
    for i in range(rows):
        v = i / (rows - 1)
        row = []
        for j in range(cols):
            u = j / (cols - 1)
            xt, zt = x0 + (x1 - x0) * u, z0 + (z1 - z0) * u
            xb, zb = x3 + (x2 - x3) * u, z3 + (z2 - z3) * u
            x, z = xt + (xb - xt) * v, zt + (zb - zt) * v
            y = _surface_y(surf, x, z, front)
            if y is None:
                return None
            sgn = -1 if front else 1
            row.append(Vector((x, y + sgn * (lift + curl * u * u), z)))
        grid.append(row)
    bm = bmesh.new()
    _grid(bm, grid, closed=False)
    o = _mk(name, bm, mat, rig, bone=None, angle=60, uv=0.4, solid=thick, solid_off=-1 if front else 1)
    for bn in set(b for _, b in bones_by_z):
        if bn not in o.vertex_groups:
            o.vertex_groups.new(name=bn)
    for v in o.data.vertices:
        bone = next((bn for (zz, bn) in bones_by_z if v.co.z >= zz), bones_by_z[-1][1])
        o.vertex_groups[bone].add([v.index], 1.0, "REPLACE")
    am = o.modifiers.new("arm", "ARMATURE")
    am.object = rig
    o.parent = rig
    return o


def _dark(key, f=0.4):
    """A darker shade of a COL entry (seams, buttonholes, piping)."""
    dk = key + "_dk"
    if dk not in COL:
        COL[dk] = tuple(c * f for c in COL.get(key, (0.3, 0.3, 0.3)))
    return dk


# ------------------------------------------------------------------ belts, sashes, drape
def garment_points(objs, bones, rig):
    """(position, dominant bone) for garment vertices whose dominant bone is in `bones` (skips the sleeves)."""
    out = []
    allb = set(b.name for b in rig.data.bones)
    for o in objs:
        if not o:
            continue
        names = {g.index: g.name for g in o.vertex_groups}
        for v in o.data.vertices:
            dom = max(((g.weight, names.get(g.group)) for g in v.groups if names.get(g.group) in allb), default=(0, None))[1]
            if dom in bones:
                out.append((o.matrix_world @ v.co, dom))
    return out


def tilted_ring(pts, zc, dip, pad, n, bones):
    """Silhouette ring round the waist, dipping `dip` lower at the front than at the back."""
    lo = silhouette_ring(pts, zc - dip, pad, n, bones=bones)
    hi = silhouette_ring(pts, zc + dip, pad, n, bones=bones)
    ring = []
    for k in range(n):
        a = math.tau * k / n
        f = (1 - math.sin(a)) / 2           # 1 at the front (-Y), 0 at the back
        ring.append(Vector(lo[k]).lerp(Vector(hi[k]), 1 - f))
    return ring


def waist_belt(key, surf, zc, rig, bone, bones, silk=None, long_coat=True):
    """Belts worn over the coat: `surf` are the coat/skirt vertices so the belt sits on the cloth, not the skin.
       leather -> 36 mm strap, 3 mm thick, brass frame buckle with prong and a tongue end through a keeper
       rope    -> two twisted strands round the waist, knot at the left hip, two hanging frayed ends
       black   -> narrow silk girdle (gartel)
       other   -> pas / sash: two flat wraps, the upper one slightly offset, knotted at the left hip with fringed tails"""
    out = []
    n = 40
    if key == "leather" or key == "tan_boot":
        mat = M(key, 0.35, tex="plain")
        r0 = tilted_ring(surf, zc - 0.018, 0.012, 0.003, n, bones)
        r1 = tilted_ring(surf, zc + 0.018, 0.012, 0.003, n, bones)
        bm = bmesh.new()
        _grid(bm, [r0, r1], closed=True)
        out.append(_mk("belt", bm, mat, rig, bone=bone, angle=40, uv=0.3, solid=0.003, solid_off=1.0))
        f = min(range(n), key=lambda k: r0[k].y)
        c = (r0[f] + r1[f]) / 2 + Vector((0, -0.006, 0))
        brass = M("brass", 0.3)
        for size, off in (((0.05, 0.006, 0.006), (0, 0, 0.024)), ((0.05, 0.006, 0.006), (0, 0, -0.024)),
                          ((0.006, 0.006, 0.054), (0.024, 0, 0)), ((0.006, 0.006, 0.054), (-0.024, 0, 0)),
                          ((0.004, 0.005, 0.05), (0.0, -0.002, 0)), ((0.03, 0.004, 0.003), (0.012, -0.003, 0.0))):
            bpy.ops.mesh.primitive_cube_add(size=1, location=c + Vector(off))
            b = bpy.context.object
            b.scale = size
            bpy.ops.object.transform_apply(scale=True)
            bv = b.modifiers.new("b", "BEVEL"); bv.width = 0.0012; bv.segments = 1
            bpy.ops.object.modifier_apply(modifier="b")
            b.data.materials.append(brass); b.name = "buckle"
            _weight_to_bone(b, rig, bone); out.append(b)
        # keeper loop beside the buckle
        kf = (f + 3) % n
        kc = (r0[kf] + r1[kf]) / 2
        bpy.ops.mesh.primitive_cube_add(size=1, location=kc + Vector((0, -0.004, 0)))
        kp = bpy.context.object
        kp.scale = (0.012, 0.004, 0.042)
        bpy.ops.object.transform_apply(scale=True)
        kp.data.materials.append(mat); kp.name = "belt_keeper"
        _weight_to_bone(kp, rig, bone); out.append(kp)
        return out
    if key == "rope":
        mat = M("rope", 0.9)
        ring = tilted_ring(surf, zc, 0.015, 0.008, 64, bones)
        path = []
        for i in range(len(ring) * 3):
            t = i / 3
            k0 = int(t) % len(ring)
            path.append(Vector(ring[k0]).lerp(Vector(ring[(k0 + 1) % len(ring)]), t - int(t)))
        T, N, Bn = _frames(path, closed=True, hint=(0, 0, 1))
        L = sum((path[(i + 1) % len(path)] - path[i]).length for i in range(len(path)))
        for strand in (0, 1):
            sp = []
            s_acc = 0.0
            for i, p in enumerate(path):
                if i:
                    s_acc += (p - path[i - 1]).length
                ph = s_acc / 0.022 * math.tau + strand * math.pi
                sp.append(p + N[i] * (0.0035 * math.cos(ph)) + Bn[i] * (0.0035 * math.sin(ph)))
            bm = bmesh.new()
            _sweep(bm, sp, _circle(0.0045, 6), closed=True)
            out.append(_mk("rope_belt", bm, mat, rig, bone=bone, angle=70, uv=0.1))
        k = min(range(len(ring)), key=lambda kk: (Vector(ring[kk]) - Vector((0.10, -0.2, zc))).length)
        kp = Vector(ring[k]) + Vector((0.0, -0.01, 0))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.016, location=kp)
        kn = bpy.context.object
        kn.scale = (1.2, 0.8, 1.0)
        kn.data.materials.append(mat); kn.name = "rope_knot"
        _weight_to_bone(kn, rig, bone); out.append(kn)
        for j, (dx, L2) in enumerate(((-0.012, 0.20), (0.014, 0.16))):
            end = [kp + Vector((dx + 0.01 * (i / 6) ** 2 * (1 if j else -1), -0.012 - 0.004 * i / 6, -L2 * i / 6)) for i in range(7)]
            bm = bmesh.new()
            _sweep(bm, end, _circle(0.0065, 6), scale=lambda t: 1.0 + 0.4 * max(0.0, t - 0.85) / 0.15)
            out.append(_mk("rope_end", bm, mat, rig, bone=bone, angle=70, uv=0.1))
        return out
    silk = key in SILK if silk is None else silk
    tex = "silk" if silk else "cloth"
    mat = M(key, 0.55 if silk else 0.92, tex=tex)
    if key == "black":
        mat = M("black", 0.5, tex="silk")
        layers = [(zc, 0.028)]
    else:
        layers = [(zc - 0.022, 0.05), (zc + 0.02, 0.046)] if long_coat else [(zc, 0.05)]
    pad = 0.004
    for li, (z, hgt) in enumerate(layers):
        rows = []
        for fz, extra in ((-0.5, 0.0), (-0.25, 0.0025), (0.25, 0.0035), (0.5, 0.0005)):
            rows.append(tilted_ring(surf, z + fz * hgt, 0.01, pad + extra + li * 0.004, n, bones))
        bm = bmesh.new()
        _grid(bm, rows, closed=True)
        out.append(_mk("sash", bm, mat, rig, bone=bone, angle=55, uv=0.3, solid=0.003, solid_off=1.0))
    if key == "black":
        return out
    # knot at the left hip and two tails hanging down the thigh, fringed at the ends
    ring = tilted_ring(surf, zc, 0.01, pad + 0.012, n, bones)
    k = min(range(n), key=lambda kk: (ring[kk] - Vector((0.14, -0.12, zc))).length)
    kp = ring[k]
    d = Vector((kp.x, kp.y + 0.02, 0)).normalized()
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=7, radius=0.03, location=kp + d * 0.008)
    kn = bpy.context.object
    kn.scale = (1.0, 0.7, 0.85)
    kn.data.materials.append(mat); kn.name = "sash_knot"
    _weight_to_bone(kn, rig, bone); out.append(kn)
    # tails: laid on the cloth surface below the knot (they hang, following hip and thigh), two soft folds along
    # their length, edges curling in, and a fringe of loose threads at the end
    cx = sum(p.x for (p, dd) in surf) / max(1, len(surf))
    cy = sum(p.y for (p, dd) in surf) / max(1, len(surf))
    ak = math.atan2(kp.y - cy, kp.x - cx)
    local = [(p, math.atan2(p.y - cy, p.x - cx)) for (p, dd) in surf if abs(math.atan2(p.y - cy, p.x - cx) - ak) < 0.9]
    def surf_r(a, z):
        dx, dy = math.cos(a), math.sin(a)
        best = 0.0
        for p, _ in local:
            if abs(p.z - z) < 0.02:
                rx, ry = p.x - cx, p.y - cy
                dd_ = rx * dx + ry * dy
                if dd_ > best and abs(rx * dy - ry * dx) < 0.025:
                    best = dd_
        return best
    ncol = 7
    fold_off = [-0.002, 0.004, 0.009, 0.003, 0.009, 0.004, -0.002]
    for j, (da, L, w) in enumerate(((-0.10, 0.30, 0.062), (0.16, 0.24, 0.056))):
        rows = []
        segs = 8
        for i in range(segs + 1):
            t = i / segs
            zz = kp.z - 0.025 - L * t
            r_c = surf_r(ak + da, zz) or 0.2
            ww = w * (1 - 0.12 * t)
            row = []
            for c in range(ncol):
                u = c / (ncol - 1) - 0.5
                a = ak + da + u * ww / r_c + 0.02 * math.sin(t * 4 + j) * (1 if j else -1)
                r = max(surf_r(a, zz), r_c * 0.9) + 0.010 + 0.004 * j + fold_off[c] * (0.6 + 0.4 * t)
                row.append(Vector((cx + math.cos(a) * r, cy + math.sin(a) * r, zz)))
            rows.append(row)
        last = rows[-1]
        nf = 2 * (ncol - 1) + 1
        top, fr = [], []
        for q in range(nf):
            f = q / (nf - 1) * (ncol - 1)
            i0 = min(ncol - 2, int(f))
            p = last[i0].lerp(last[i0 + 1], f - i0)
            top.append(p)
            fr.append(p + Vector((0, 0, -(0.04 if q % 2 == 0 else 0.022))))
        bm = bmesh.new()
        _grid(bm, rows, closed=False)
        _grid(bm, [top, fr], closed=False)
        out.append(_mk("sash_tail", bm, mat, rig, bone=bone, angle=60, uv=0.3, solid=0.002))
    return out


def drape(obj, name, rig, ctx):
    """Real folds in the garment mesh (before thickening): simple subdivision for resolution, then outward-only
    displacement so nothing moves into the body.
      skirt / coat_skirt : vertical hanging folds growing to the hem, gathers at the waist, flare, scalloped hem
      coat               : elbow creases (inside of the bend), compression rings above the cuffs, waist wrinkles
      breeches           : bag above the knee band
    Returns per-vertex hem weights (1 at the lower free edges, falling off over ~2 cm) for the double-fold hem."""
    B = ctx["B"]
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    dl = bm.verts.layers.deform.active
    names = {g.index: g.name for g in obj.vertex_groups}
    bones = set(b.name for b in rig.data.bones)
    # extra resolution only where folds need it (keeps the triangle budget): whole skirts, sleeves at elbow and cuff
    if name in ("skirt", "coat_skirt"):
        # folds hang vertically: only the edges running round the skirt need splitting
        sub_edges = [e for e in bm.edges if abs(e.verts[0].co.z - e.verts[1].co.z) < 0.5 * e.calc_length()]
    elif name == "coat":
        hot = []
        for side in ("l", "r"):
            hot += [B["lowerarm_" + side][0], B["hand_" + side][0]]
        sub_edges = [e for e in bm.edges if all(min((v.co - h).length for h in hot) < 0.13 for v in e.verts)]
    else:
        sub_edges = []
    if sub_edges:
        bmesh.ops.subdivide_edges(bm, edges=sub_edges, cuts=1, use_grid_fill=True, quad_corner_type="INNER_VERT")
    zs = [v.co.z for v in bm.verts]
    ztop, zbot = max(zs), min(zs)
    seed = ctx.get("seed", 0) * 1.37
    def dom(v):
        if dl is None:
            return None
        d = v[dl]
        return max(((w, names.get(i)) for i, w in d.items() if names.get(i) in bones), default=(0, None))[1]
    moves = {}
    if name in ("skirt", "coat_skirt"):
        px, py = B["pelvis"][0].x, B["pelvis"][0].y
        long_ = name == "skirt"
        nf = 11 if long_ else 9
        A_fold = 0.024 if long_ else 0.018
        flare = 0.018 if long_ else 0.035
        for v in bm.verts:
            t = max(0.0, min(1.0, (ztop - v.co.z) / max(1e-3, ztop - zbot)))
            rx, ry = v.co.x - px, v.co.y - py
            rl = math.hypot(rx, ry) or 1.0
            th = math.atan2(ry, rx)
            wander = _nz(v.co, 3.0, seed)
            f = 0.5 + 0.5 * math.sin(th * nf + 2.6 * wander + 0.8 * _nz(v.co, 8.0, seed + 4))
            f = 1 - (1 - f) ** 2
            g = 0.5 + 0.5 * math.sin(th * 38 + 1.2 * wander)
            sfac = (abs(rx) / rl) ** 2
            # hem flare: +4.5 cm at the front, +6.5 cm at the back (room for knee and trailing foot), +2 cm at the sides
            fl = (0.045 + (0.02 if ry > 0 else 0.0) - 0.025 * sfac) * t ** 1.6 + flare * 0.3 * t ** 1.5
            disp = A_fold * f * t ** 1.1 + 0.005 * g * max(0.0, 1 - t / 0.3) + fl
            moves[v] = Vector((rx / rl * disp, ry / rl * disp, 0.0))
    elif name == "coat":
        cy_t = B["spine_02"][0].y
        waist_z = ctx["waist_z"]
        for v in bm.verts:
            d = dom(v)
            co = v.co
            disp = 0.0025 * (0.5 + 0.5 * _nz(co, 6.0, seed))
            rdir = None
            if d in ("upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "hand_l", "hand_r"):
                side = d[-1]
                e = B["lowerarm_" + side][0]
                hnd = B["hand_" + side][0]
                ax = (hnd - e).normalized()
                ax_up = (e - B["upperarm_" + side][0]).normalized()
                rel = co - e
                along = rel.dot(ax)
                use_ax = ax if along > 0 else ax_up
                perp = rel - use_ax * rel.dot(use_ax)
                if perp.length < 1e-5:
                    continue
                rdir = perp.normalized()
                front = Vector((0, -1, 0))
                inner = max(0.0, rdir.dot((front - use_ax * front.dot(use_ax)).normalized()))
                crease = max(0.0, math.sin(along * math.tau / 0.03 + 2.5 * _nz(co, 7.0, seed + 1))) ** 2
                disp += 0.008 * crease * math.exp(-(along / 0.07) ** 2) * (0.25 + 0.75 * inner)
                s = (hnd - co).dot(ax)
                if 0.02 < s < 0.17:
                    ang = math.atan2(rdir.dot(ax.cross(front).normalized()), rdir.dot(front))
                    ring = max(0.0, math.sin(s * math.tau / 0.04 + ang + 2.0 * _nz(co, 9.0, seed + 2))) ** 1.5
                    disp += 0.006 * ring * (1 - s / 0.17)
                # sleeve hangs looser on the underside of the upper arm
                disp += 0.004 * max(0.0, -rdir.z) * max(0.0, -along) / 0.3
            else:
                rx, ry = co.x, co.y - cy_t
                rl = math.hypot(rx, ry) or 1.0
                rdir = Vector((rx / rl, ry / rl, 0))
                dz = co.z - waist_z
                if -0.25 < dz < 0.08:
                    w = max(0.0, math.sin(co.z * math.tau / 0.035 + 3.0 * _nz(co, 5.0, seed + 3))) ** 2
                    disp += 0.004 * w * math.exp(-(dz / 0.06) ** 2)
                if dz < -0.02:          # coat below the waist (long coats): hanging vertical folds
                    th = math.atan2(ry, rx)
                    t = min(1.0, -dz / 0.25)
                    f = 0.5 + 0.5 * math.sin(th * 10 + 2.2 * _nz(co, 3.0, seed))
                    disp += 0.012 * f * t
            moves[v] = rdir * disp
    elif name == "breeches":
        knee_z = ctx["knee_z"]
        for v in bm.verts:
            d = dom(v)
            if d not in ("thigh_l", "thigh_r", "calf_l", "calf_r"):
                continue
            side = d[-1]
            a0, a1 = B["thigh_" + side]
            ax = (a1 - a0).normalized()
            rel = v.co - a0
            perp = rel - ax * rel.dot(ax)
            if perp.length < 1e-5:
                continue
            s = v.co.z - knee_z
            bag = math.sin(math.pi * (s - 0.02) / 0.16) if 0.02 < s < 0.18 else 0.0
            crease = 0.5 + 0.5 * _nz(v.co, 12.0, seed + 5)
            moves[v] = perp.normalized() * (0.008 * bag + 0.003 * crease * (1 if s < 0.3 else 0.3))
    for v, m in moves.items():
        v.co += m
    if name in ("skirt", "coat_skirt") and ctx.get("legs"):
        # clearance: nothing of the legs (plus a boot's thickness) may sit outside the cloth in the rest pose
        px, py = B["pelvis"][0].x, B["pelvis"][0].y
        NA = 96
        grid = {}
        for p in ctx["legs"]:
            ka = int((math.atan2(p.y - py, p.x - px) % math.tau) / math.tau * NA) % NA
            kz = int(math.floor(p.z / 0.01))
            r = math.hypot(p.x - px, p.y - py)
            if r > grid.get((ka, kz), 0.0):
                grid[(ka, kz)] = r
        knee = ctx["knee_z"]
        for v in bm.verts:
            if v.co.z > knee + 0.15:
                continue
            rx, ry = v.co.x - px, v.co.y - py
            r = math.hypot(rx, ry) or 1e-6
            ka = int((math.atan2(ry, rx) % math.tau) / math.tau * NA) % NA
            kz = int(math.floor(v.co.z / 0.01))
            need = max((grid.get(((ka + da) % NA, kz + dz), 0.0) for da in (-2, -1, 0, 1, 2) for dz in (-2, -1, 0, 1, 2)), default=0.0)
            clear = 0.012 + 0.02 * max(0.0, min(1.0, (knee + 0.15 - v.co.z) / 0.3))
            if need and r < need + clear:
                f = (need + clear) / r
                v.co.x = px + rx * f
                v.co.y = py + ry * f
    if name in ("skirt", "coat_skirt"):
        # keep the hem a clean line: relax the lower boundary along itself (height and outline)
        for _ in range(4):
            upd = {}
            for v in bm.verts:
                if v.is_boundary and v.co.z < zbot + 0.04:
                    nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
                    if len(nb) == 2:
                        avg = (nb[0].co + nb[1].co) / 2
                        upd[v] = Vector((v.co.x * 0.6 + avg.x * 0.4, v.co.y * 0.6 + avg.y * 0.4, v.co.z * 0.4 + avg.z * 0.6))
            for v, c in upd.items():
                v.co = c
    # hem weights: free lower edges (neighbours above), falling off over two rings
    bm.verts.ensure_lookup_table()
    hem = {}
    frontier = []
    for v in bm.verts:
        if v.is_boundary:
            nb = [e.other_vert(v) for e in v.link_edges if not e.is_boundary]
            if nb and sum(x.co.z for x in nb) / len(nb) > v.co.z + 0.001:
                hem[v.index] = 1.0
                frontier.append(v)
    for w in (0.8, 0.5):
        nxt = []
        for v in frontier:
            for e in v.link_edges:
                o = e.other_vert(v)
                if o.index not in hem:
                    hem[o.index] = w
                    nxt.append(o)
        frontier = nxt
    bm.to_mesh(obj.data)
    bm.free()
    return hem


# ------------------------------------------------------------------ skirt skinning, back vent, seams
def _smooth01(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def skirt_weights(obj, rig, ctx):
    """One skinning scheme for hanging cloth below the crotch (thigh head height), so raised or striding legs do
    not punch through: the helper's own weights at the crotch, blended linearly over 0.35 m into same-side thigh
    shares of front 0.75 -> 0.55 (knee to hem), back 0.85 -> 0.75 with a calf share of up to 0.75 at the back hem
    for the trailing foot, sides 0.9; the rest is pelvis. Left and right blend over 18 cm across the centre line
    so cloth between the legs stretches instead of tearing. (Tested in the walk frames: pelvis-dominant front and
    back panels let the legs through.)"""
    B = ctx["B"]
    hip = (B["thigh_l"][0].z + B["thigh_r"][0].z) / 2
    knee = ctx["knee_z"]
    px, py = B["pelvis"][0].x, B["pelvis"][0].y
    me = obj.data
    if not me.vertices:
        return
    hem = min(v.co.z for v in me.vertices)
    bones = set(b.name for b in rig.data.bones)
    for g in ("pelvis", "thigh_l", "thigh_r", "calf_l", "calf_r"):
        if g not in obj.vertex_groups:
            obj.vertex_groups.new(name=g)
    gname = {g.index: g.name for g in obj.vertex_groups}
    new_w = {}
    for v in me.vertices:
        z = v.co.z
        if z >= hip:
            continue
        rx, ry = v.co.x - px, v.co.y - py
        rl = math.hypot(rx, ry) or 1.0
        back = ry > 0
        if z > knee:
            cf, cs = (0.85 if back else 0.75), 0.9
            calf = 0.0
        else:
            u = (knee - z) / max(1e-3, knee - hem)
            cf = (0.85 - 0.1 * u) if back else (0.75 - 0.2 * u)
            cs = 0.9 - 0.05 * u
            # the trailing foot kicks up behind: the back hem follows the calf (and the sides a little)
            calf = (0.75 * u ** 0.7) * (min(1.0, ry / rl * 1.5) if back else 0.0) + 0.15 * u * (abs(rx) / rl)
        sfac = (abs(rx) / rl) ** 2
        cap = cf + (cs - cf) * sfac
        wl = _smooth01((rx + 0.09) / 0.18)
        th = cap * (1 - calf)
        cl = cap * calf
        target = {"pelvis": 1.0 - cap, "thigh_l": th * wl, "thigh_r": th * (1.0 - wl), "calf_l": cl * wl, "calf_r": cl * (1.0 - wl)}
        orig = {gname[g.group]: g.weight for g in v.groups if gname.get(g.group) in bones}
        tot = sum(orig.values()) or 1.0
        b = max(0.0, min(1.0, (hip - z) / 0.35))       # ramped in over 0.35 m below the crotch
        mix = {}
        for k_ in set(orig) | set(target):
            mix[k_] = orig.get(k_, 0.0) / tot * (1 - b) + target.get(k_, 0.0) * b
        new_w[v.index] = mix
    for g in obj.vertex_groups:
        if g.name in bones:
            g.remove([vi for vi in new_w])
    for vi, mix in new_w.items():
        for k_, w in mix.items():
            if w > 1e-4:
                if k_ not in obj.vertex_groups:
                    obj.vertex_groups.new(name=k_)
                obj.vertex_groups[k_].add([vi], w, "REPLACE")


def vent_split(obj, ctx):
    """Back vent of a frock-coat skirt: split the cloth up the centre back from the hem, and lay an overlap flap
    (a 3 cm strip of the left panel, duplicated 6 mm outward and reaching across the split)."""
    B = ctx["B"]
    py = B["pelvis"][0].y
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    zs = [v.co.z for v in bm.verts]
    z0, z1 = min(zs), max(zs)
    vtop = z0 + (z1 - z0) * 0.62
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=0.0008, plane_co=(0, 0, 0), plane_no=(1, 0, 0))
    cut = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)
           and all(v.co.y > py + 0.02 and v.co.z < vtop for v in e.verts)]
    if not cut:
        bm.free()
        return
    bmesh.ops.split_edges(bm, edges=cut)
    for v in bm.verts:
        if abs(v.co.x) < 0.0012 and v.co.y > py + 0.02 and v.co.z < vtop and v.link_faces:
            sx = sum(f.calc_center_median().x for f in v.link_faces)
            v.co.x += 0.002 if sx > 0 else -0.002
    flap = [f for f in bm.faces if 0 < f.calc_center_median().x < 0.03 and f.calc_center_median().y > py + 0.02
            and f.calc_center_median().z < vtop]
    if flap:
        dup = bmesh.ops.duplicate(bm, geom=flap)
        for v in [g for g in dup["geom"] if isinstance(g, bmesh.types.BMVert)]:
            rx, ry = v.co.x, v.co.y - py
            rl = math.hypot(rx, ry) or 1.0
            v.co.x += rx / rl * 0.006
            v.co.y += ry / rl * 0.006
            if v.co.x < 0.004:
                v.co.x -= 0.012 * (1 - v.co.x / 0.004)
    bm.to_mesh(obj.data)
    bm.free()


def _chains(edges):
    """Chain (a, b) index pairs into polylines: list of (indices, closed)."""
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    seen = set()
    out = []
    starts = [v for v, n in adj.items() if len(n) != 2] + list(adj)
    for s_ in starts:
        for nb in adj[s_]:
            if (min(s_, nb), max(s_, nb)) in seen:
                continue
            path = [s_]
            prev, cur = s_, nb
            seen.add((min(s_, nb), max(s_, nb)))
            while True:
                path.append(cur)
                nxt = [x for x in adj[cur] if x != prev and (min(cur, x), max(cur, x)) not in seen]
                if len(adj[cur]) != 2 or not nxt:
                    break
                prev, cur = cur, nxt[0]
                seen.add((min(prev, cur), max(prev, cur)))
            closed = path[-1] == path[0]
            if len(path) >= 3:
                out.append((path[:-1] if closed else path, closed))
    return out


SEAMED = {"coat", "coat_skirt", "skirt", "breeches", "cuffs"}


def seam_prepare(obj, name, ctx, hem):
    """Before thickening: cut seam lines into the cloth (centre back, side seams, sleeve heads, breeches outer
    seam) with bisect planes and collect them, plus the stitching line 6 mm inside every free edge (hems, cuffs,
    fronts, neck). Returns seam paths as lists of (vertex, interior neighbour, t) and updates the hem weights."""
    B = ctx["B"]
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    dl = bm.verts.layers.deform.active
    names = {g.index: g.name for g in obj.vertex_groups}
    def dom(v):
        if dl is None:
            return None
        return max(((w, names.get(i)) for i, w in v[dl].items() if names.get(i) in ctx["bones"]), default=(0, None))[1]
    n0 = len(bm.verts)
    TORSO = {"spine_01", "spine_02", "spine_03", "pelvis", "clavicle_l", "clavicle_r", "neck_01"}
    cy = B["spine_02"][0].y
    planes = []
    if name in ("coat", "skirt") or (name == "coat_skirt" and not ctx.get("vent")):
        planes.append(((0, 0, 0), (1, 0, 0), lambda v: v.co.y > cy + 0.02 and dom(v) not in ctx["arms"]))
    if name in ("coat", "skirt"):
        armpit = min(B["upperarm_l"][0].z, B["upperarm_r"][0].z) - 0.06
        planes.append(((0, cy, 0), (0, 1, 0), lambda v: abs(v.co.x) > 0.06 and v.co.z < armpit and dom(v) not in ctx["arms"]))
    if name == "coat":
        for sd in ("l", "r"):
            h0, h1 = B["upperarm_" + sd]
            d = (h1 - h0).normalized()
            planes.append((h0 + d * 0.035, d, lambda v, h0=h0: (v.co - h0).length < 0.15))
    if name == "breeches":
        for sd, sx in (("l", 1), ("r", -1)):
            t0 = B["thigh_" + sd][0]
            planes.append(((0, t0.y, 0), (0, 1, 0), lambda v, sx=sx, t0=t0: v.co.x * sx > abs(t0.x) and dom(v) in ("thigh_l", "thigh_r")))
    cut_edges = []
    for co, no, ok in planes:
        res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=0.0006, plane_co=co, plane_no=no)
        cut_edges += [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge) and all(ok(v) for v in e.verts)]
    bm.verts.index_update()
    if hem is not None:
        for v in bm.verts[n0:]:
            w = max((hem.get(e.other_vert(v).index, 0.0) for e in v.link_edges), default=0.0)
            if w:
                hem[v.index] = w
    paths = []
    for idx, closed in _chains([(e.verts[0].index, e.verts[1].index) for e in cut_edges if e.is_valid]):
        paths.append(([(i, i, 0.0) for i in idx], closed))
    bm.verts.ensure_lookup_table()
    bnd = [(e.verts[0].index, e.verts[1].index) for e in bm.edges if e.is_boundary]
    for idx, closed in _chains(bnd):
        items = []
        for k, i in enumerate(idx):
            v = bm.verts[i]
            a = bm.verts[idx[k - 1]].co if (closed or k > 0) else v.co
            b = bm.verts[idx[(k + 1) % len(idx)]].co if (closed or k < len(idx) - 1) else v.co
            tan = (b - a).normalized() if (b - a).length > 1e-9 else Vector((1, 0, 0))
            inner = [e.other_vert(v) for e in v.link_edges if not e.is_boundary]
            if not inner:
                items.append((i, i, 0.0))
                continue
            o = min(inner, key=lambda x: abs((x.co - v.co).normalized().dot(tan)))
            L = (o.co - v.co).length
            items.append((i, o.index, min(0.9, 0.006 / max(L, 1e-4))))
        paths.append((items, closed))
    bm.to_mesh(obj.data)
    bm.free()
    return paths, len(obj.data.vertices)


def seam_build(obj, paths, n0, key, rig, ctx):
    """After thickening: lay a 2.5 mm darker stitched strip along each seam path on the outer face of the cloth.
    Each strip vertex copies the skin weights of the cloth vertex under it, so seams move with the garment."""
    me = obj.data
    if len(me.vertices) != 2 * n0 or not paths:
        return None
    B = ctx["B"]
    names = {g.index: g.name for g in obj.vertex_groups}
    def axis_dist(i):
        v = me.vertices[i]
        dm = max(((g.weight, names.get(g.group)) for g in v.groups if names.get(g.group) in ctx["bones"]), default=(0, "pelvis"))[1]
        h0, h1 = B.get(dm, B["pelvis"])
        seg = h1 - h0
        t = max(0.0, min(1.0, (v.co - h0).dot(seg) / max(seg.length_squared, 1e-9)))
        return (v.co - (h0 + seg * t)).length
    cache = {}
    def outer(i):
        if i not in cache:
            a, b = i, i + n0
            cache[i] = (a, b) if axis_dist(a) >= axis_dist(b) else (b, a)
        return cache[i]
    bm = bmesh.new()
    wmap = []
    for items, closed in paths:
        P, Nn, src, bad = [], [], [], []
        for (i, j, t) in items:
            oi, ii = outer(i)
            oj, ij = outer(j)
            p = me.vertices[oi].co.lerp(me.vertices[oj].co, t)
            q = me.vertices[ii].co.lerp(me.vertices[ij].co, t)
            n = (p - q)
            bad.append(n.length > 0.04)
            P.append(p)
            Nn.append(n.normalized() if n.length > 1e-6 else Vector((0, 0, 1)))
            src.append(oj if t > 0.5 else oi)
        if len(P) < 3:
            continue
        m = len(P)
        rowL, rowR = [], []
        for k in range(m):
            a = P[k - 1] if (closed or k > 0) else P[k]
            b = P[(k + 1) % m] if (closed or k < m - 1) else P[k]
            tan = (b - a)
            side = tan.cross(Nn[k])
            side = side.normalized() if side.length > 1e-9 else Vector((1, 0, 0))
            c = P[k] + Nn[k] * 0.0012
            vl = bm.verts.new(c - side * 0.0015)
            vr = bm.verts.new(c + side * 0.0015)
            rowL.append(vl); rowR.append(vr)
            wmap += [src[k], src[k]]
        for k in range(m if closed else m - 1):
            k2 = (k + 1) % m
            if (P[k] - P[k2]).length > 0.025 or bad[k] or bad[k2]:
                continue
            try:
                bm.faces.new((rowL[k], rowL[k2], rowR[k2], rowR[k]))
            except ValueError:
                pass
    if not bm.verts:
        bm.free()
        return None
    o = _mk("seam_" + obj.name, bm, M(_dark(key, 0.38), 1.0, tex="plain"), rig, bone=None, angle=80, uv=0.2, recalc=False)
    for g in obj.vertex_groups:
        o.vertex_groups.new(name=g.name)
    srcw = {}
    for vi, si in enumerate(wmap):
        if si not in srcw:
            srcw[si] = [(names[g.group], g.weight) for g in me.vertices[si].groups]
        for gn, w in srcw[si]:
            o.vertex_groups[gn].add([vi], w, "REPLACE")
    am = o.modifiers.new("arm", "ARMATURE")
    am.object = rig
    o.parent = rig
    return o


# ------------------------------------------------------------------ headwear
HAT_N = 48          # points around every hat ring (corners of square crowns land on k = 0, 12, 24, 36)


def build_hat(hat, spec, rig, pts, top_z, extra=()):
    """Headwear lofted off the measured head and hair. The bottom edge is tilted (front above the brows, back
    lower over the occiput); every ring keeps a clearance over skull and hair from a HeadField."""
    out = []
    head_skin = [p for (p, d) in pts if d == "head"]
    hw, hd, hcx, hcy = head_box(pts, top_z)
    brow = None
    for o in bpy.data.objects:
        if o.type == "MESH" and "eyebrow" in o.name.lower():
            bz = [p.z for p in _obj_points(o)]
            if bz:
                brow = max(bz)
    if brow is None or not (top_z - 0.16 < brow < top_z - 0.04):
        brow = top_z - 0.095
    hair = []
    for o in bpy.data.objects:
        if o.type == "MESH" and o.name != "Human" and not any(k in o.name.lower() for k in ("eye", "teeth", "brow", "lash", "tongue")) \
                and o.name.startswith("Human.") or o.name == "veil":
            hair += [p for p in _obj_points(o) if p.z > brow - 0.10]
    # hair only counts close to the skull: a ponytail or long hair hanging behind must not inflate the hat
    skin_f = HeadField(head_skin, hcx, hcy, HAT_N, brow - 0.12, top_z + 0.01)
    kept = []
    for p in hair:
        a = math.atan2(p.y - hcy, p.x - hcx)
        k = int(round(a / math.tau * HAT_N)) % HAT_N
        rs = skin_f.r(k, min(p.z, top_z - 0.005))
        if math.hypot(p.x - hcx, p.y - hcy) < rs + 0.03 or p.z > top_z - 0.03:
            kept.append(p)
    F = HeadField(head_skin + kept, hcx, hcy, HAT_N, brow - 0.12, top_z + 0.05)
    crown = max([p.z for p in head_skin + kept] + [top_z])
    n = HAT_N
    A = [math.tau * k / n for k in range(n)]
    col = spec.get("hat_colour")
    log("hat %s: brow %.3f crown %.3f (skin top %.3f) head %.3f x %.3f" % (hat, brow, crown, top_z, hw, hd))

    def ring_z(zf, zs, zb):
        return [tilt_z(a, zf, zs, zb) for a in A]

    def rolled_band(name, zs, hgt, thick, pad, mat, noise=0.0, prof=None, uv=0.25):
        """A rolled band (fur otok, cap turn-up, coif) as a closed tube swept round the tilted base ring."""
        prof = prof or [(0.0, -0.002), (0.55, -0.006), (0.9, 0.12), (1.0, 0.45), (0.92, 0.8), (0.6, 1.0), (0.2, 1.06), (0.0, 1.02)]
        r0 = [F.rmax(k, zs[k] - 0.004, zs[k] + hgt) + pad for k in range(n)]
        rows = []
        for (dr, dz) in prof:
            row = []
            for k in range(n):
                z = zs[k] + dz * hgt
                r = r0[k] + dr * thick
                if noise and dr > 0.3:
                    p = F.at(k, z, r)
                    r += noise * (_nz(p, 38.0) * 0.7 + _nz(p, 90.0, 3.1) * 0.3)
                row.append(F.at(k, z, r))
            rows.append(row)
        bm = bmesh.new()
        _grid(bm, [list(r) for r in zip(*rows)], closed=True, close_rows=True)   # profile loop x ring loop
        out.append(_mk(name, bm, mat, rig, angle=70, uv=uv))
        return r0

    def dome(name, zs, pad, mat, puff=None, top_extra=0.0, levels=9, shift=(0.0, 0.0), solid=0.0, uv=0.35, ripple=None):
        """Skull cap from the tilted base ring up over the crown: ellipse profile, never inside head+hair+pad."""
        zt = crown + pad + top_extra
        rows = []
        for j in range(levels):
            phi = (math.pi / 2) * j / levels
            row = []
            for k in range(n):
                rb = F.rmax(k, zs[k], zs[k] + 0.01) + pad
                z = zs[k] + (zt - zs[k]) * math.sin(phi)
                r = rb * math.cos(phi)
                r = max(r, F.r(k, z) + pad) if z < crown else r
                if puff:
                    r += puff(A[k], j / levels)
                if ripple:
                    r += ripple(A[k], j / levels, F.at(k, z, r))
                sh = math.sin(phi) ** 2
                p = F.at(k, z, r)
                row.append(Vector((p.x + shift[0] * sh, p.y + shift[1] * sh, p.z)))
            rows.append(row)
        bm = bmesh.new()
        _grid(bm, rows, closed=True, cap_top=(hcx + shift[0], hcy + shift[1], zt))
        # every face points away from the skull, so the shell always thickens outward (no inverted patches)
        hc = Vector((hcx, hcy, crown - 0.06))
        bm.normal_update()
        flip = [f for f in bm.faces if f.normal.dot(f.calc_center_median() - hc) < 0]
        if flip:
            bmesh.ops.reverse_faces(bm, faces=flip)
        o = _mk(name, bm, mat, rig, angle=70, uv=uv, solid=solid, solid_off=1.0, recalc=False)
        out.append(o)
        return rows

    def piping(name, path, r, mat, closed=False, k=5):
        bm = bmesh.new()
        _sweep(bm, path, _circle(r, k), closed=closed)
        out.append(_mk(name, bm, mat, rig, angle=80, uv=0.2))

    def ribbon(name, path, w, t, mat, hint, closed=False, taper=None):
        bm = bmesh.new()
        _sweep(bm, path, [(-t / 2, -w / 2), (t / 2, -w / 2), (t / 2, w / 2), (-t / 2, w / 2)], closed=closed, hint=hint, scale=taper)
        out.append(_mk(name, bm, mat, rig, angle=40, uv=0.2))

    def feather(name, base, direction, length, width, mat, curve=0.3, side=Vector((1, 0, 0))):
        """A feather or plume: flat vane tapering to a point, bent along its length."""
        d = Vector(direction).normalized()
        sd = (Vector(side) - d * Vector(side).dot(d)).normalized()
        bend = d.cross(sd).normalized()
        segs = 8
        path = [base + d * (length * i / segs) + bend * (curve * length * (i / segs) ** 2) for i in range(segs + 1)]
        bm = bmesh.new()
        rows = []
        for i, p in enumerate(path):
            t = i / segs
            w = width * math.sin(math.pi * min(1.0, 0.15 + t * 0.95)) * (1.0 - 0.3 * t)
            rows.append([p - sd * w, p, p + sd * w])
        _grid(bm, [list(r) for r in rows], closed=False)
        out.append(_mk(name, bm, mat, rig, angle=80, uv=0.2, solid=0.0015))

    def square_r(a, c, p, bow=0.0, rot=0.0):
        """Radius of a rounded square (corners at rot + k*90 deg) of corner distance c; p=1 diamond-straight edges."""
        x, y = math.cos(a - rot), math.sin(a - rot)
        r = c / (abs(x) ** p + abs(y) ** p) ** (1.0 / p)
        mid = math.sin(2 * (a - rot)) ** 2
        return r * (1.0 - bow * mid)

    def four_corner_cap(name, crown_key, band_key, band_tex, H, c, p, corner_lift, pillow, band_h, band_t, trim=None, soft=0.0):
        """Konfederatka / krakuska: fur or cloth otok round the head, a crown flaring into a four-cornered top
        (corners front, back and sides), rounded top edge, pillowed faces and top, piping down the corner seams."""
        zs = ring_z(brow + 0.018, brow + 0.004, brow - 0.012)
        r0 = rolled_band(name + "_band", zs, band_h, band_t, 0.004, M(band_key, tex=band_tex), noise=0.004 if band_tex == "fur" else 0.0)
        z_top = max(zs) + band_h + H
        J = 12
        rows = []
        corner_rows = {k: [] for k in (0, n // 4, n // 2, 3 * n // 4)}
        for j in range(J + 1):
            t = j / J
            row = []
            for k in range(n):
                a = A[k]
                zb = zs[k] + band_h * 0.8
                rb = r0[k] + band_t * 0.35
                rt = square_r(a, c, p, bow=0.025)
                e = t ** 1.7
                z = zb + (z_top - zb) * (t if t < 0.9 else 0.9 + (t - 0.9) * 0.6)
                r = rb + (rt - rb) * e
                r += pillow * math.sin(math.pi * t) * math.sin(2 * a) ** 2          # faces bulge between the corners
                r += soft * _nz(F.at(k, z, r), 18.0) * t
                if j == J:                                                         # rounded top edge
                    r -= 0.012
                    z += 0.006
                cf = abs(math.cos(2 * a)) ** 6
                z += corner_lift * cf * t ** 3
                row.append(F.at(k, z, r))
                if k in corner_rows:
                    corner_rows[k].append(row[-1])
            rows.append(row)
        # top panel: pillowed, corners lifted, slight dish just inside the edge
        top = rows[-1]
        zc = sum(p.z for p in top) / n
        for f in (0.82, 0.55, 0.28):
            row = []
            for k in range(n):
                q = top[k]
                x = hcx + (q.x - hcx) * f
                y = hcy + (q.y - hcy) * f
                z = zc + (q.z - zc) * f ** 2 + 0.012 * (1 - f * f) - 0.004 * math.sin(math.pi * f)
                row.append(Vector((x, y, z)))
            rows.append(row)
        bm = bmesh.new()
        _grid(bm, rows, closed=True, cap_top=(hcx, hcy, zc + 0.012))
        out.append(_mk(name + "_top", bm, M(crown_key), rig, angle=75, uv=0.35))
        if trim:
            tm = M(trim, 0.45, tex="plain")
            for k, path in corner_rows.items():
                q = [p + F.radial(k) * 0.002 for p in path[2:]]
                piping(name + "_seam", q, 0.0028, tm)
            edge = [p + F.radial(k) * 0.001 + Vector((0, 0, 0.001)) for k, p in enumerate(rows[J])]
            piping(name + "_edge", edge, 0.003, tm, closed=True)
        return zs, r0, rows

    if hat == "konfederatka":
        # stiff square crown over a grey/black lambskin otok; gold cord on the seams, jewelled brooch and heron plume
        c = (hw / 2 + 0.085) * 1.06
        zs, r0, rows = four_corner_cap("hat", col or "crimson", spec.get("hat_band", "fur"), "fur", H=0.10, c=c, p=1.12,
                                       corner_lift=0.006, pillow=0.006, band_h=0.058, band_t=0.028, trim=spec.get("hat_trim", "zupan_gold"))
        k = int(round((-0.30 * math.pi) % math.tau / math.tau * n)) % n       # left front
        zb = zs[k] + 0.03
        p = F.at(k, zb, r0[k] + 0.03)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.013, location=p)
        br = bpy.context.object
        br.scale = (1, 1, 1)
        br.data.materials.append(M("brass", 0.3)); br.name = "hat_brooch"
        _weight_to_bone(br, rig, "head")
        out.append(br)
        up = Vector((0, 0.35, 1.0)) + F.radial(k) * 0.25
        feather("hat_plume", p + Vector((0, 0.004, 0.006)), up, 0.20, 0.011, M(spec.get("plume", "cream"), 0.8, tex="plain"), curve=0.35, side=F.radial(k).cross(Vector((0, 0, 1))))
        feather("hat_plume", p + Vector((0, 0.008, 0.004)), up + Vector((0.1, 0.25, -0.2)), 0.16, 0.009, M("black", 0.7), curve=0.4, side=F.radial(k).cross(Vector((0, 0, 1))))

    elif hat == "krakuska":
        # Krakow rogatywka: soft red cloth crown, black lambskin otok, peacock-feather bunch and hanging ribbons
        c = (hw / 2 + 0.06) * 1.12
        zs, r0, rows = four_corner_cap("hat", col or "red_cap", "black", "fur", H=0.085, c=c, p=1.45, corner_lift=0.022,
                                       pillow=0.01, band_h=0.045, band_t=0.024, trim=None, soft=0.004)
        k = int(round((-0.22 * math.pi) % math.tau / math.tau * n)) % n
        base = F.at(k, zs[k] + 0.03, r0[k] + 0.022)
        rng = random.Random(spec.get("seed", 3))
        for i in range(6):
            d = Vector((0.15 + rng.uniform(-0.25, 0.25), 0.25 + rng.uniform(-0.15, 0.35), 1.0)) + F.radial(k) * 0.3
            L = 0.22 + rng.uniform(-0.05, 0.08)
            dd = d.normalized()
            piping("feather_quill", [base + dd * (L * t / 6) for t in range(7)], 0.0016, M("buff", 0.6, tex="plain"), k=4)
            tip = base + dd * L
            feather("feather", tip - dd * 0.07, dd, 0.075, 0.012, M("feather", 0.5, tex="plain"), curve=0.1, side=dd.cross(Vector((0, 1, 0))))
            bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=5, radius=0.009, location=tip - dd * 0.035 - dd.cross(Vector((0, 1, 0))).normalized() * 0.002)
            e = bpy.context.object
            e.scale = (1.0, 0.35, 1.3)
            e.data.materials.append(M("navy", 0.4)); e.name = "feather_eye"
            _weight_to_bone(e, rig, "head")
            out.append(e)
        # ribbons from the back of the band
        for i, rk in enumerate(("facing_red", "sky_blue", "dress_green", "saffron")):
            kk = (n // 4 + (i - 1.5) * 2) % n
            kk = int(kk)
            p0 = F.at(kk, zs[kk] + 0.02, r0[kk] + 0.02)
            path = [p0 + Vector((0.004 * i, 0.012 + 0.01 * t, -0.045 * t)) for t in range(7)]
            ribbon("hat_ribbon", path, 0.016, 0.0012, M(rk, 0.6, tex="silk"), hint=F.radial(kk))

    elif hat == "fur":
        # kolpak / shapka: tall lambskin walls, irregular, rolled at the lip; cloth top panel sunk inside with a dent
        fur_key = col or "fur"
        zs = ring_z(brow + 0.016, brow + 0.002, brow - 0.014)
        H = 0.15
        rows = []
        prof = [(0.0, -0.004), (0.02, -0.002), (0.03, 0.04), (0.034, 0.3), (0.034, 0.6), (0.032, 0.85), (0.028, 0.95), (0.018, 1.0), (0.006, 0.985)]
        rb = [F.rmax(k, zs[k], zs[k] + 0.06) + 0.004 for k in range(n)]
        for (dr, dz) in prof:
            row = []
            for k in range(n):
                z = zs[k] + dz * H
                r = rb[k] + dr
                p = F.at(k, z, r)
                if dr > 0.01:
                    r += 0.009 * _nz(p, 9.0) + 0.004 * _nz(p, 30.0, 2.0)
                    z += 0.012 * _nz(p, 8.0, 5.0) * dz
                row.append(F.at(k, z, r))
            rows.append(row)
        bm = bmesh.new()
        _grid(bm, rows, closed=True)
        out.append(_mk("hat_fur", bm, M(fur_key, tex="fur"), rig, angle=75, uv=0.22))
        lip = rows[-1]
        zc = sum(p.z for p in lip) / n
        trows = []
        for f in (1.0, 0.8, 0.55, 0.3):
            row = []
            for k in range(n):
                q = lip[k]
                x = hcx + (q.x - hcx) * f
                y = hcy + (q.y - hcy) * f
                dent = 0.03 * (1 - f) * (0.6 + 0.4 * abs(math.cos(A[k])))       # pinched front-to-back crease
                z = (q.z - 0.008) if f == 1.0 else zc - 0.012 - dent
                row.append(Vector((x, y, z)))
            trows.append(row)
        bm = bmesh.new()
        _grid(bm, trows, closed=True, cap_top=(hcx, hcy, zc - 0.045))
        out.append(_mk("hat_top", bm, M(spec.get("hat_top", "black" if fur_key in ("black", "charcoal") else "wine")), rig, angle=70, uv=0.3, solid=0.003))

    elif hat == "biretta":
        # square stiff cap (flat sides front/back/sides), three curved horns (none on the wearer's left), pompom
        key = col or "black"
        zs = ring_z(brow + 0.022, brow + 0.012, brow - 0.004)
        H = 0.068
        c = hw / 2 + 0.014
        rows = []
        for j in range(7):
            t = j / 6
            row = []
            for k in range(n):
                rb = F.rmax(k, zs[k], zs[k] + H) + 0.004
                rt = square_r(A[k], c, 7.0)
                r = rb + (rt - rb) * min(1.0, t * 1.6)
                z = zs[k] + (max(zs) + H - zs[k]) * t
                if j == 6:
                    r -= 0.008
                    z += 0.003
                row.append(F.at(k, z, r))
            rows.append(row)
        top = rows[-1]
        zt = sum(p.z for p in top) / n
        for f in (0.7, 0.35):
            rows.append([Vector((hcx + (q.x - hcx) * f, hcy + (q.y - hcy) * f, zt + 0.004)) for q in top])
        bm = bmesh.new()
        _grid(bm, rows, closed=True, cap_top=(hcx, hcy, zt + 0.005))
        out.append(_mk("hat_top", bm, M(key), rig, angle=40, uv=0.3))
        # horns: curved fins standing on the top along the axes front (-Y), wearer's right (-X) and back (+Y)
        for ax in ((0, -1), (-1, 0), (0, 1)):
            d = Vector((ax[0], ax[1], 0))
            L = c * 0.95
            outline = []
            segs = 10
            for i in range(segs + 1):
                s_ = i / segs
                hgt = 0.04 * math.sin(math.pi * (0.08 + 0.84 * s_)) ** 0.7 * (0.5 + 0.5 * s_)
                outline.append((0.25 * L + 0.75 * L * s_, hgt))
            bm = bmesh.new()
            side = d.cross(Vector((0, 0, 1))) * 0.0035
            topv, botv = [], []
            for (rr, hh) in outline:
                base = Vector((hcx, hcy, zt + 0.003)) + d * rr
                topv.append(base + Vector((0, 0, hh)))
                botv.append(base)
            _grid(bm, [[p - side for p in botv], [p - side for p in topv], [p + side for p in topv], [p + side for p in botv]], closed=False, close_rows=True)
            out.append(_mk("hat_ridge", bm, M(key), rig, angle=40, uv=0.3))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.02, location=(hcx, hcy, zt + 0.022))
        tuft = bpy.context.object
        tuft.data.materials.append(M(spec.get("tuft", key), tex="fur")); tuft.name = "hat_tuft"
        bpy.ops.object.shade_smooth()
        unwrap(tuft, 0.1)
        _weight_to_bone(tuft, rig, "head")
        out.append(tuft)

    elif hat == "tricorne":
        # cocked hat: rounded felt crown, brim turned up on three sides meeting in corners (front, back left, back
        # right), bound edge (gold or white lace for soldiers), loop and button on the left panel, cockade for soldiers
        key = col or "black"
        felt = M(key, 0.88, tex="felt")
        zs = ring_z(brow + 0.02, brow + 0.006, brow - 0.01)
        rb = [F.rmax(k, zs[k], zs[k] + 0.03) + 0.004 for k in range(n)]
        zt = crown + 0.022
        rows = []
        for j in range(8):
            t = j / 8
            row = []
            for k in range(n):
                phi = t * math.pi / 2
                z = zs[k] + (zt - zs[k]) * math.sin(phi) ** 0.85
                r = max(rb[k] * (math.cos(phi) ** 0.55) * 1.02, F.r(k, z) + 0.006 if z < crown else 0.0)
                row.append(F.at(k, z, r))
            rows.append(row)
        bm = bmesh.new()
        _grid(bm, rows, closed=True, cap_top=(hcx, hcy + 0.004, zt + 0.004))
        out.append(_mk("hat_crown", bm, felt, rig, angle=70, uv=0.35))
        corners = [-math.pi / 2, -math.pi / 2 + math.tau / 3, -math.pi / 2 - math.tau / 3]
        def cornerness(a):
            best = 0.0
            for cc in corners:
                d = abs((a - cc + math.pi) % math.tau - math.pi)
                best = max(best, max(0.0, 1.0 - d / (math.pi / 3)))
            return best
        brim = []
        R = 7
        for k in range(n):
            cf = cornerness(A[k])
            front = max(0.0, -math.sin(A[k])) ** 4
            w = 0.10 + 0.05 * cf ** 1.5 + 0.012 * front
            alpha = math.radians(88 - 42 * cf ** 1.2 - 6 * front * cf)
            p = F.at(k, zs[k] - 0.002, rb[k] - 0.002)
            col_ = [p.copy()]
            d = F.radial(k)
            for i in range(1, R + 1):
                s = i / R
                ang = alpha * min(1.0, (s / 0.3)) ** 1.2
                step = w / R
                p = p + d * (step * math.cos(ang)) + Vector((0, 0, step * math.sin(ang)))
                col_.append(p.copy())
            brim.append(col_)
        rows = [[brim[k][i] for k in range(n)] for i in range(R + 1)]
        bm = bmesh.new()
        _grid(bm, rows, closed=True)
        out.append(_mk("hat_brim", bm, felt, rig, angle=65, uv=0.35, solid=0.004))
        mil = spec.get("coat") == "white_coat" or spec.get("hat_trim")
        trim = spec.get("hat_trim") or ("zupan_gold" if (mil and spec.get("sword")) else ("cream" if mil else _dark(key, 0.5)))
        edge = rows[-1]
        piping("hat_lace", [p + Vector((0, 0, 0.001)) for p in edge], 0.0045, M(trim, 0.5, tex="plain" if trim.endswith("_dk") else "cloth"), closed=True, k=6)
        # loop and button on the left panel (between the front and back-left corners)
        k = int(round(((-math.pi / 2 + math.pi / 3) % math.tau) / math.tau * n)) % n
        top_pt = rows[-1][k]
        low_pt = rows[2][k]
        loop_path = [low_pt.lerp(top_pt, t) + F.radial(k) * 0.004 for t in (0.0, 0.33, 0.66, 1.0)]
        ribbon("hat_loop", loop_path, 0.008, 0.0015, M(trim if mil else _dark(key, 0.3), 0.5, tex="plain"), hint=F.radial(k))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=0.007, location=low_pt + F.radial(k) * 0.007 + Vector((0, 0, 0.008)))
        bt = bpy.context.object
        bt.data.materials.append(M(spec.get("button_colour", "brass"), 0.35)); bt.name = "hat_button"
        _weight_to_bone(bt, rig, "head"); out.append(bt)
        if mil:
            ck = low_pt.lerp(top_pt, 0.55) + F.radial(k) * 0.006
            rosette = []
            nrm = F.radial(k)
            ax1 = nrm.cross(Vector((0, 0, 1))).normalized()
            ax2 = nrm.cross(ax1).normalized()
            bm = bmesh.new()
            ringp = []
            for i in range(24):
                a = math.tau * i / 24
                rr = 0.02 + 0.002 * math.sin(a * 12)
                ringp.append(ck + ax1 * (rr * math.cos(a)) + ax2 * (rr * math.sin(a)) + nrm * 0.002 * math.cos(a * 12))
            inner = [ck.lerp(p, 0.45) + nrm * 0.003 for p in ringp]
            _grid(bm, [ringp, inner], closed=True, cap_top=ck + nrm * 0.004)
            out.append(_mk("hat_cockade", bm, M("black", 0.6), rig, angle=80, uv=0.1, solid=0.002))

    elif hat in ("felt", "straw"):
        # round-crowned felt hat with a ribbon band (raftsmen, carters), or a wide straw hat (field hands, boatmen)
        straw = hat == "straw"
        key = "straw" if straw else (col or "charcoal")
        mat = M(key, 0.8 if straw else 0.88, tex="straw" if straw else "felt")
        zs = ring_z(brow + 0.022, brow + 0.008, brow - 0.006)
        rb = [F.rmax(k, zs[k], zs[k] + 0.04) + 0.006 for k in range(n)]
        zt = crown + (0.03 if straw else 0.028)
        rows = []
        for j in range(8):
            t = j / 7
            row = []
            for k in range(n):
                z = zs[k] + (zt - zs[k]) * t
                r = rb[k] * (1.0 - 0.08 * t)
                if t > 0.8:
                    r *= 1.0 - (t - 0.8) * 0.9
                row.append(F.at(k, z, max(r, F.r(k, z) + 0.006 if z < crown else 0.0)))
            rows.append(row)
        top = rows[-1]
        for f in (0.7, 0.35):
            rows.append([Vector((hcx + (q.x - hcx) * f, hcy + (q.y - hcy) * f, q.z + 0.008 * (1 - f))) for kk, q in enumerate(top)])
        bm = bmesh.new()
        _grid(bm, rows, closed=True, cap_top=(hcx, hcy, zt + 0.006))
        out.append(_mk("hat_crown", bm, mat, rig, angle=70, uv=0.3))
        W = 0.10 if straw else 0.082
        brows_ = []
        for i in range(6):
            s = i / 5
            row = []
            for k in range(n):
                fb = abs(math.sin(A[k]))
                droop = (-0.018 * fb + 0.012 * (1 - fb)) * s ** 2 if not straw else -0.02 * s ** 2
                row.append(F.at(k, zs[k] + droop + (0.0 if i else 0.001), rb[k] - 0.002 + W * s))
            brows_.append(row)
        bm = bmesh.new()
        _grid(bm, brows_, closed=True)
        out.append(_mk("hat_brim", bm, mat, rig, angle=70, uv=0.3, solid=0.004))
        band_rows = [[F.at(k, zs[k] + dz, rb[k] * (1.0 - 0.08 * dz / (zt - zs[k])) + 0.0025) for k in range(n)] for dz in (0.002, 0.03)]
        bm = bmesh.new()
        _grid(bm, band_rows, closed=True)
        out.append(_mk("hat_band", bm, M(spec.get("hat_band", "black"), 0.6, tex="silk"), rig, angle=50, uv=0.2, solid=0.002))
        edge = [p + Vector((0, 0, 0.0)) for p in brows_[-1]]
        if not straw:
            piping("hat_edge", edge, 0.0028, M(_dark(key, 0.6), 0.8, tex="plain"), closed=True, k=5)

    elif hat == "cap":
        # soft wool cap: slouched puffy crown with random creases, rolled turn-up band, small knot on top
        key = col or "brown_coat"
        rng = random.Random(spec.get("seed", 5) * 7 + 1)
        zs = ring_z(brow + 0.026, brow + 0.004, brow - 0.02)
        slump = (rng.uniform(-0.025, 0.025), rng.uniform(0.0, 0.03))
        def puff(a, u):
            return 0.012 * math.sin(math.pi * u) + 0.004
        def crease(a, u, p):
            return 0.004 * _nz(p, 24.0, rng.random() * 10) * u
        rows = dome("hat", zs, 0.008, M(key), puff=puff, top_extra=0.025, levels=9, shift=slump, ripple=crease)
        rolled_band("hat_band", [z - 0.004 for z in zs], 0.032, 0.012, 0.008, M(key), prof=[(0.0, 0.0), (0.6, -0.05), (1.0, 0.3), (1.0, 0.7), (0.7, 1.0), (0.0, 1.0)])
        tip = Vector((hcx + slump[0], hcy + slump[1], crown + 0.008 + 0.025 + 0.004))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=5, radius=0.009, location=tip)
        kn = bpy.context.object
        kn.scale.z = 0.6
        kn.data.materials.append(M(key)); kn.name = "hat_knot"
        _weight_to_bone(kn, rig, "head"); out.append(kn)

    elif hat in ("bonnet", "kerchief", "wimple"):
        key = col or {"bonnet": "cream", "kerchief": "kerchief_red", "wimple": "veil"}[hat]
        chin_pts = [p for (p, d) in pts if d == "head" and p.y < hcy - 0.05 and abs(p.x - hcx) < 0.02 and brow - 0.2 < p.z < brow - 0.06]
        chin_z = min((p.z for p in chin_pts), default=brow - 0.13)
        chin_pts = [p for p in chin_pts if p.z < chin_z + 0.02]
        jaw = HeadField([p for (p, d) in pts if d in ("head", "neck_01")], hcx, hcy, HAT_N, chin_z - 0.03, brow + 0.02, step=0.01)

        def chin_ties(name, w, t, mat, knot=True):
            """Ties from both sides down along the jaw, meeting in a knot or bow under the chin."""
            zt_ = brow - 0.035
            for sgn in (1, -1):
                path = []
                steps = 7
                for i in range(steps + 1):
                    u = i / steps
                    z = zt_ + (chin_z - 0.012 - zt_) * u
                    a = (-math.pi / 2) + sgn * (math.pi / 2 - 0.25) * (1 - u) ** 0.8 + sgn * 0.12
                    k = int(round((a % math.tau) / math.tau * HAT_N)) % HAT_N
                    path.append(jaw.at(k, z, jaw.r(k, z) + 0.006 + t))
                path[-1] = Vector((hcx + sgn * 0.012, path[-1].y, chin_z - 0.014))
                ribbon(name, path, w, t, mat, hint=Vector((sgn, -0.3, 0)))
            if knot:
                kp = Vector((hcx, min(p.y for p in chin_pts) + 0.03 if chin_pts else hcy - 0.05, chin_z - 0.02))
                for sx in (-1, 1):
                    bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=5, radius=w * 0.9, location=kp + Vector((sx * w * 0.9, -0.004, 0)))
                    lb = bpy.context.object
                    lb.scale = (1.3, 0.55, 0.8)
                    lb.data.materials.append(mat); lb.name = name + "_bow"
                    _weight_to_bone(lb, rig, "head"); out.append(lb)
                for sx in (-1, 1):
                    ribbon(name + "_end", [kp + Vector((sx * (0.004 * i + 0.002 * i * i), -0.006 - 0.002 * i, -0.02 * i)) for i in range(6)], w * 0.8, t, mat,
                           hint=Vector((0, -1, 0)), taper=lambda u: 1.0 - 0.3 * u)

        if hat == "bonnet":
            # mob cap: puffed caul gathered into a ribbon band, pleated frill framing the face, ties under the chin
            zs = ring_z(brow + 0.03, brow - 0.02, brow - 0.06)
            ribbon_key = spec.get("ribbon", "dress_blue" if key in ("cream", "apron", "wimple") else "cream")
            def puff(a, u):
                back = max(0.0, math.sin(a))
                ears = abs(math.cos(a)) ** 3 * max(0.0, 1 - u * 2.2)          # cloth sagging out over the ears
                return (0.006 + 0.022 * back) * math.sin(math.pi * min(1.0, u * 1.3)) + 0.004 + 0.012 * ears
            def gathers(a, u, p):
                back = max(0.0, math.sin(a)) ** 1.5
                g = (0.5 + 0.5 * math.sin(a * 36 + 2 * _nz(p, 20.0)))
                return (0.004 + 0.006 * back) * max(0.0, 1 - u * 1.4) * g + 0.004 * _nz(p, 14.0, 4.0) * u
            dome("hat", zs, 0.01, M(key), puff=puff, top_extra=0.004, levels=12, ripple=gathers, solid=0.004)
            rb = [F.rmax(k, zs[k], zs[k] + 0.02) + 0.014 for k in range(n)]
            # frill: pleated strip standing out from the band (sinusoidal flutes), wider at the face
            N2 = 2 * n
            fr = []
            for i in range(4):
                s = i / 3
                row = []
                for kk in range(N2):
                    a = math.tau * kk / N2
                    k0 = kk // 2
                    r = (rb[k0] + rb[(k0 + (kk % 2)) % n]) / 2
                    z0 = (zs[k0] + zs[(k0 + (kk % 2)) % n]) / 2
                    face = max(0.0, -math.sin(a)) ** 0.7
                    W = 0.03 + 0.016 * face
                    wave = 0.009 * s ** 0.8 * math.sin(kk * math.pi + 0.5)       # alternating flutes
                    d = Vector((math.cos(a), math.sin(a), 0))
                    row.append(Vector((hcx, hcy, 0)) + d * (r + W * s * (0.55 + 0.35 * face) + wave) + Vector((0, 0, z0 - W * s * (0.75 - 0.55 * face) + wave * 0.5)))
                fr.append(row)
            bm = bmesh.new()
            _grid(bm, fr, closed=True)
            out.append(_mk("hat_frill", bm, M(key), rig, angle=80, uv=0.25, solid=0.0015))
            rolled_band("hat_ribbon", [z + 0.006 for z in zs], 0.02, 0.004, 0.019, M(ribbon_key, 0.55, tex="silk"),
                        prof=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
            chin_ties("hat_tie", 0.012, 0.0015, M(ribbon_key, 0.55, tex="silk"))
        elif hat == "kerchief":
            # head kerchief: folded edge framing the face, covers ears and nape, point hanging at the back, knotted
            # under the chin
            zs = ring_z(brow + 0.04, brow - 0.05, brow - 0.085)
            def puff(a, u):
                ears = abs(math.cos(a)) ** 3 * max(0.0, 1 - u * 2.0)
                return 0.004 + 0.008 * max(0.0, math.sin(a)) * math.sin(math.pi * u) + 0.014 * ears
            def folds(a, u, p):
                # creases radiating back from the knot, gathered cloth at the nape, soft lumps
                back = max(0.0, math.sin(a)) ** 2
                c = 0.006 * (0.5 + 0.5 * math.sin(a * 9 + 3 * _nz(p, 12.0, 1.3))) * (1 - u) ** 1.5
                g = 0.007 * back * max(0.0, 1 - u * 1.8) * (0.5 + 0.5 * math.sin(a * 30 + 2 * _nz(p, 18.0)))
                return c + g + 0.004 * _nz(p, 10.0, 7.0)
            rows = dome("hat", zs, 0.008, M(key), puff=puff, top_extra=0.0, levels=12, ripple=folds, solid=0.004)
            base = rows[0]
            fk = [k for k in range(n) if math.sin(A[k]) < 0.25]
            fk.sort(key=lambda k: (A[k] + math.pi / 2 + math.pi) % math.tau)
            edge = [base[k] + F.radial(k) * 0.005 for k in fk]
            piping("hat_fold", edge, 0.008, M(key), k=6)
            # back point
            kb = n // 4
            tri = []
            for i in range(5):
                s = i / 4
                wdt = 0.07 * (1 - s)
                c0 = base[kb] + Vector((0, 0.01 + 0.012 * s, -0.08 * s))
                tri.append([c0 + Vector((-wdt, 0, 0)), c0, c0 + Vector((wdt, 0, 0))])
            bm = bmesh.new()
            _grid(bm, tri, closed=False)
            out.append(_mk("hat_tail", bm, M(key), rig, angle=70, uv=0.3, solid=0.003))
            chin_ties("hat_tie", 0.028, 0.004, M(key))
        else:
            # nun: black under-cap and a starched white coif band across the brow (veil and wimple collar elsewhere)
            zs = ring_z(brow + 0.03, brow - 0.01, brow - 0.03)
            dome("hat", zs, 0.006, M(key), top_extra=0.004, levels=8)
            rolled_band("hat_band", [z - 0.004 for z in zs], 0.03, 0.003, 0.007, M("wimple", 0.85), prof=[(0.0, 0.0), (0.8, -0.02), (1.0, 0.2), (1.0, 0.8), (0.8, 1.02), (0.0, 1.0)])

    # small caps that go with or without a hat
    if "zucchetto" in extra:
        # skullcap of eight gores with a little stem, following the crown of the skull
        key = spec["zucchetto"]
        zb = crown - 0.052
        rows = []
        L = 6
        for j in range(L):
            phi = (math.pi / 2) * j / L
            row = []
            for k in range(n):
                rb = F.r(k, zb) + 0.004
                z = zb + (crown + 0.004 - zb) * math.sin(phi)
                r = max(rb * math.cos(phi), F.r(k, z) + 0.004 if z < crown - 0.002 else 0.0)
                row.append(F.at(k, z, r))
            rows.append(row)
        bm = bmesh.new()
        _grid(bm, rows, closed=True, cap_top=(hcx, hcy, crown + 0.005))
        out.append(_mk("zucchetto", bm, M(key, 0.6, tex="silk"), rig, angle=70, uv=0.3, solid=0.003, solid_off=1.0))
        for g in range(8):
            k = g * n // 8
            piping("zucchetto_seam", [rows[j][k] + F.radial(k) * 0.0035 + Vector((0, 0, 0.002 * j / L)) for j in range(L)], 0.0015, M(_dark(key, 0.6), 0.5, tex="plain"), k=4)
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.004, depth=0.012, location=(hcx, hcy, crown + 0.01))
        st = bpy.context.object
        st.data.materials.append(M(key, 0.6, tex="silk")); st.name = "zucchetto_stem"
        _weight_to_bone(st, rig, "head"); out.append(st)
    if "phrygian" in extra:
        # liberty cap: soft cone rising from the head, its tip flopping forward
        zs = ring_z(brow + 0.022, brow - 0.004, brow - 0.03)
        rb = [F.rmax(k, zs[k], zs[k] + 0.03) + 0.006 for k in range(n)]
        zb = sum(zs) / n
        rows = []
        L = 12
        for j in range(L + 1):
            u = j / L
            cxu = hcx
            cyu = hcy - 0.1 * u ** 2.2
            czu = zb + (crown - zb + 0.06) * math.sin(u * math.pi * 0.6) / math.sin(math.pi * 0.6)
            row = []
            for k in range(n):
                base = F.at(k, zs[k], rb[k])
                sc = (1 - u) ** 0.9 * (1 + 0.15 * math.sin(math.pi * u)) + 0.02
                p = Vector((cxu + (base.x - hcx) * sc, cyu + (base.y - hcy) * sc, czu + (base.z - zb) * (1 - u)))
                if p.z < crown + 0.01 and u < 0.6:
                    kk = k
                    rr = math.hypot(p.x - hcx, p.y - hcy)
                    need = F.r(kk, p.z) + 0.006
                    if rr < need:
                        d = F.radial(kk)
                        p = Vector((hcx + d.x * need, hcy + d.y * need, p.z))
                row.append(p)
            rows.append(row)
        bm = bmesh.new()
        _grid(bm, rows, closed=True, cap_top=rows[-1][0].lerp(rows[-1][n // 2], 0.5))
        out.append(_mk("phrygian", bm, M("red_cap"), rig, angle=70, uv=0.3, solid=0.003, solid_off=1.0))
    return out


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

    DRAPE_CTX.clear()
    DRAPE_CTX.update({"B": B, "waist_z": waist_z, "knee_z": knee_z, "seed": spec.get("seed", 0) or 0, "vent": spec.get("coat_len", "mid") == "mid",
                      "bones": set(b.name for b in rig.data.bones), "arms": ARMS})
    GARMENT_EXTRA.clear()
    pts = skin_points(h, me, rig)
    DRAPE_CTX["legs"] = [p for (p, d) in pts if d in LEGS_UP | CALF | FEET]

    coat_len = spec.get("coat_len", "mid")
    coat = spec["coat"]
    if coat_len == "long":
        spec = dict(spec, breeches=coat, stockings=coat)     # hidden under the skirt; same colour kills any z-fight
    out = []

    # coat body + sleeves (tights helper, torso and arms, above the coat hem)
    hem = waist_z - 0.05 if coat_len == "short" else waist_z - 0.20
    has_collar = bool(spec.get("collar"))
    def coat_fn(i, co, g, dom):
        if not helper(g, "helper-tights"):
            return False
        if dom in ARMS:
            return not near_hand(co)
        if dom == "neck_01":
            return not has_collar
        if dom in TORSO:
            if coat_len == "mid" and co.z < waist_z - 0.14 and co.y < -0.03 and abs(co.x) < 0.07 + (waist_z - 0.14 - co.z) * 0.6:
                return False        # 1790s cutaway: the fronts curve away below the waist over the breeches
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

    names = [g.name for g in h.vertex_groups]
    TB = {"spine_01", "spine_02", "spine_03", "pelvis"}
    tights_pts = [v.co.copy() for v in me.vertices if any(names[x.group] == "helper-tights" and x.weight > 0.5 for x in v.groups)]

    # garment surface for everything laid on top of the coat (belts, lapels, buttons, flaps)
    surf_objs = [o for o in out if o and o.name in ("coat", "coat_skirt", "skirt")]
    surf = garment_points(surf_objs, TB | LEGS_UP, rig)
    surf_v = [p for (p, d) in surf]
    coat_v = [p for (p, d) in garment_points([o for o in surf_objs if o.name == "coat"], TB | LEGS_UP, rig)]
    by_z = [(B["spine_03"][0].z, "spine_03"), (B["spine_02"][0].z, "spine_02"), (B["spine_01"][0].z, "spine_01"), (0.0, "pelvis")]
    nz = B["neck_01"][0].z

    # sash / belt: worn on the cloth, thin, with a buckle, knot or tails
    if spec.get("sash"):
        out += waist_belt(spec["sash"], surf, waist_z - 0.005, rig, "spine_02", TB | LEGS_UP, long_coat=coat_len == "long")

    # coat fronts: lapels over a waistcoat (frock and military coats), overlapping front edge on long coats, pocket flaps
    front_objs = []
    if coat_len == "mid" and spec.get("collar"):
        facing = spec.get("lapels") or spec.get("cuffs") or coat
        wc = spec.get("waistcoat") or (spec.get("breeches") if spec.get("breeches") not in (None, coat) else "cream")
        w = surface_panel("waistcoat", surf_v, [(-0.048, nz - 0.03), (0.048, nz - 0.03), (0.06, waist_z - 0.15), (-0.06, waist_z - 0.15)],
                          M(wc), rig, by_z, lift=0.003, thick=0.003, rows=12, cols=5)
        if w:
            out.append(w); front_objs.append(w)
        for sx in (1, -1):
            s3 = B["spine_03"][0].z
            q = [(sx * 0.034, nz - 0.015), (sx * 0.118, nz - 0.035), (sx * 0.088, s3 - 0.07), (sx * 0.05, s3 - 0.055)]
            lp = surface_panel("lapel", surf_v, q, M(facing), rig, by_z, lift=0.009, thick=0.004, rows=10, cols=5, curl=0.004)
            if lp:
                out.append(lp)
            if coat_len == "mid":
                zf = waist_z - 0.085
                q = [(sx * 0.09, zf + 0.02), (sx * 0.175, zf + 0.024), (sx * 0.172, zf - 0.018), (sx * 0.093, zf - 0.024)]
                pf = surface_panel("pocket_flap", coat_v, q, M(coat), rig, by_z, lift=0.003, thick=0.003, rows=3, cols=5, curl=0.004)
                if pf:
                    out.append(pf)
    if coat_len == "long":
        skirt_o = next((o for o in out if o and o.name == "skirt"), None)
        hem_z = min((v.co.z for v in skirt_o.data.vertices), default=knee_z) if skirt_o else knee_z
        edge = spec.get("trim") or (spec.get("collar") if spec.get("collar") not in (None, "cream", "white_coat", "wimple") else coat)
        fe = surface_panel("front_edge", surf_v, [(-0.016, nz - 0.02), (0.016, nz - 0.02), (0.016, hem_z + 0.03), (-0.016, hem_z + 0.03)],
                           M(edge), rig, by_z, lift=0.003, thick=0.003, rows=18, cols=2)
        if fe:
            out.append(fe); front_objs.append(fe)

    # collar band
    if spec.get("collar"):
        nz = B["neck_01"][0].z
        cl = band("collar", pts, nz - 0.03, nz + 0.045, 0.025 if spec.get("wimple") else 0.012, M(spec["collar"]), rig, "neck_01", thickness=0.018 if spec.get("wimple") else 0.012, extra_top=0.008, bones={"neck_01"})
        set_weights(cl, {"neck_01": 0.5, "spine_03": 0.5})      # bends between head and chest instead of cutting the jaw
        out.append(cl)

    # buttons down the front
    if spec.get("buttons", True) and coat_len != "long" or spec.get("buttons") == "long":
        top = B["neck_01"][0].z - 0.05
        bsurf = surf_v + [o.matrix_world @ v.co for o in front_objs for v in o.data.vertices]
        bsurf = [p for p in bsurf if abs(p.x) < 0.06]
        lo = (waist_z - 0.08) if coat_len != "long" else hem + 0.06
        out += buttons(bsurf, rig, lo, top, 8 if coat_len != "long" else 12, M(spec.get("button_colour", "brass"), 0.35), by_z,
                       hole=M(_dark(spec.get("waistcoat") or coat, 0.3), 0.9, tex="plain"))

    # breeches (hip to knee) and stockings (knee to ankle)
    breech_top = knee_z + 0.12 if coat_len == "long" else 9.0
    out.append(garment(h, rig, me, info, "breeches", lambda i, co, g, dom: helper(g, "helper-tights") and ((dom in LEGS_UP and knee_z - 0.03 < co.z <= breech_top) or (dom == "pelvis" and knee_z < co.z <= min(breech_top, hem - 0.05) if coat_len != "short" else (dom == "pelvis" and co.z < waist_z))), M(spec.get("breeches", "black")), 0.012))
    # the tights helper is open at the crotch: a fitted patch over the skin closes it
    if coat_len != "long":
        out.append(garment(h, rig, me, info, "breeches_in", lambda i, co, g, dom: skin_face(g) and dom in LEGS_UP | {"pelvis", "spine_01"} and knee_z + 0.05 < co.z <= min(breech_top, waist_z - 0.06), M(spec.get("breeches", "black")), 0.002, offset=0.4))
    out.append(garment(h, rig, me, info, "stockings", lambda i, co, g, dom: helper(g, "helper-tights") and (dom in CALF or (dom in LEGS_UP and co.z <= knee_z - 0.03)) and co.z > ankle_z + spec.get("boot_height", 0.12), M(spec.get("stockings", "stocking")), 0.008))

    # boots: lower calf band of the tights + the body's own foot surface (beggars go barefoot)
    bh = ankle_z + spec.get("boot_height", 0.12)
    if spec.get("boots") is None and "boots" in spec:
        bh = -1.0
    if bh > 0:
        out.append(garment(h, rig, me, info, "boot_leg", lambda i, co, g, dom: helper(g, "helper-tights") and dom in CALF | FEET and co.z <= bh + 0.005, M(spec.get("boots") or "leather", 0.5), 0.022 if coat_len != "long" else 0.004))
        out.append(garment(h, rig, me, info, "boot_foot", lambda i, co, g, dom: skin_face(g) and dom in FEET | CALF and co.z < bh, M(spec.get("boots") or "leather", 0.5), 0.014))
    for side, bone in ((1, "calf_l"), (-1, "calf_r")):
        if bh < 0:
            break
        leg = {"calf_l", "foot_l", "thigh_l"} if side > 0 else {"calf_r", "foot_r", "thigh_r"}
        if coat_len != "long" or bh < 0.2:
            bl = next((o for o in out if o and o.name == "boot_leg"), None)
            lp = garment_points([bl], leg | {"calf_l", "calf_r"}, rig) if bl else []
            lp = [(p, d) for (p, d) in lp if p.x * side > 0.0] or pts
            out.append(band("boot_top", lp, bh - 0.035, bh + 0.004, 0.003, M(spec.get("boots") or "leather", 0.5), rig, bone, thickness=0.004, n=24, side=side, bones=None if lp is not pts else leg, extra_top=0.006))
        if coat_len != "long":
            br = next((o for o in out if o and o.name == "breeches"), None)
            kp = garment_points([br], leg, rig) if br else []
            kp = [(p, d) for (p, d) in kp if p.x * side > 0.0 and abs(p.z - knee_z) < 0.06] or pts
            out.append(band("knee_band", kp, knee_z - 0.012, knee_z + 0.012, 0.0, M(spec.get("breeches", "black")), rig, bone, thickness=0.003, n=24, side=side, bones=None if kp is not pts else leg))

    # headwear: lofted off the measured head and hair (see build_hat)
    hat = spec.get("hat")
    extra = tuple(k for k in ("zucchetto", "phrygian") if spec.get(k))
    if hat or extra:
        out += build_hat(hat, spec, rig, pts, top_z, extra)
    # ---- rags: holes torn near the hems, more the lower you go
    if spec.get("ragged"):
        rng = random.Random(spec.get("seed", 7))
        for o in out:
            if o and o.name in ("coat", "skirt", "breeches", "stockings", "hat", "hat_top"):
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
    if spec.get("apron"):
        long_surf = coat_len == "long" and surf
        out.append(apron_panel(surf if long_surf else pts, rig, waist_z, knee_z, M(spec["apron"]), None if long_surf else TB | LEGS_UP, pad=0.012 if long_surf else 0.03, stiff=spec["apron"] == "leather",
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
    out += GARMENT_EXTRA
    # hanging pieces over the skirt share its skinning so legs cannot poke through them either
    for o in out:
        if not o:
            continue
        base = o.name.split(".")[0]
        if base in ("apron", "front_edge"):
            skirt_weights(o, rig, DRAPE_CTX)
        elif base in ("sash_tail", "rope_end"):
            set_weights(o, {"pelvis": 0.6, "thigh_l": 0.4})
        elif base in ("belt", "buckle", "belt_keeper", "sash", "sash_knot", "rope_belt", "rope_knot"):
            set_weights(o, {"pelvis": 0.5, "spine_01": 0.5})     # follows a forward bend without cutting the coat
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


def set_weights(obj, weights):
    """Replace all skin weights of a rigid part with fixed bone weights, e.g. {"neck_01": 0.5, "spine_03": 0.5}."""
    for g in list(obj.vertex_groups):
        obj.vertex_groups.remove(g)
    idx = list(range(len(obj.data.vertices)))
    for bn, w in weights.items():
        obj.vertex_groups.new(name=bn).add(idx, w, "REPLACE")


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


def make_animations(rig, fps=30, stride=1.0, clips=("sentry",)):
    """Per-character clips as NLA tracks. The shared anim_library.glb (build_animations.py) now drives idle and
    walk, so by default only "sentry" (townsfolk holding a lantern) is baked; pass clips to bake the old
    idle/walk fallbacks too."""
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
            ("thigh_l", "X", 28 * s * stride), ("calf_l", "X", stride * (max(0, -40 * c) if s < 0 else 12 + 20 * max(0, -c))),
            ("thigh_r", "X", -28 * s * stride), ("calf_r", "X", stride * (max(0, 40 * c) if s > 0 else 12 + 20 * max(0, c))),
            ("upperarm_l", "X", -22 * s), ("upperarm_r", "X", 22 * s),
            ("lowerarm_l", "X", -10 - 8 * max(0, -s)), ("lowerarm_r", "X", -10 - 8 * max(0, s)),
            ("head", "Z", -2 * s),
        ]
    frames = list(range(1, 26))
    if "walk" in clips:
        action("walk", frames, [walk_pose((f - 1) / 24) for f in frames])

    def idle_pose(t):
        s = math.sin(t * math.tau)
        return [("spine_02", "X", 1.5 * s), ("spine_03", "X", 1.0 * s), ("head", "Z", 3 * math.sin(t * math.tau * 0.5)),
                ("upperarm_l", "X", -2 * s), ("upperarm_r", "X", -2 * s), ("lowerarm_l", "X", -6), ("lowerarm_r", "X", -6)]
    frames = list(range(1, 62))
    if "idle" in clips:
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


def enhance_eyes():
    """Iris with more depth (contrast, saturation, black pupil, dark limbal ring), wet cornea: near-zero
    roughness, strong specular and a clearcoat so lights leave a catch-light. Cached enhanced iris image."""
    cache = os.path.join(ROOT, "assets", "textures", "eye_enhanced.png")
    for m in bpy.data.materials:
        low = m.name.lower()
        if not ("high-poly" in low or "low-poly" in low) or not m.node_tree:
            continue
        nt = m.node_tree
        b = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image), None)
        if b is None:
            continue
        b.inputs["Roughness"].default_value = 0.06
        for name, val in (("Specular IOR Level", 1.0), ("IOR", 1.42), ("Coat Weight", 1.0), ("Coat Roughness", 0.03)):
            if name in b.inputs:
                b.inputs[name].default_value = val
        if tex is None:
            continue
        if os.path.exists(cache):
            tex.image = bpy.data.images.load(cache, check_existing=True)
            continue
        img = tex.image
        w, hgt = img.size
        px = list(img.pixels)
        cx, cy = w / 2, hgt / 2
        for i in range(0, len(px), 4):
            r, g, bch = px[i], px[i + 1], px[i + 2]
            lum = 0.3 * r + 0.59 * g + 0.11 * bch
            sat = max(r, g, bch) - min(r, g, bch)
            if lum < 0.09:                       # pupil: pure black
                r = g = bch = 0.0
            elif sat > 0.12 and lum < 0.72:      # iris: lift the fibres out of the dark, more saturation
                r, g, bch = [c ** 0.68 for c in (r, g, bch)]
                lum2 = 0.3 * r + 0.59 * g + 0.11 * bch
                r, g, bch = [max(0.0, min(1.0, lum2 + (c - lum2) * 1.3)) for c in (r, g, bch)]
            px[i], px[i + 1], px[i + 2] = r, g, bch
        img.pixels = px
        img.filepath_raw = cache
        img.file_format = "PNG"
        img.save()
        tex.image = bpy.data.images.load(cache, check_existing=True)


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
    enhance_eyes()
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
        if o and ty == "Teeth":
            dc = o.modifiers.new("dec", "DECIMATE")      # 7k triangles of mostly hidden teeth; applied with the rest pose
            dc.ratio = 0.3
        log("asset", ty, nm, "->", o.name if o else None, [m.type for m in o.modifiers] if o else "")
    if spec.get("hair"):
        o = add(h, "hair", spec["hair"], "Hair")
        log("asset Hair", spec["hair"], "->", o.name if o else None)
        if o and spec.get("veil"):
            o.name = "veil"
            o.data.materials.clear()
            o.data.materials.append(M("veil"))
    eye_shadow(rig)
    clothes = build_clothes(h, rig, spec)
    log("garments", [c.name for c in clothes])
    rest_arms_down(rig)
    if spec.get("musket"):
        _musket(rig)
    make_animations(rig)
    tris = {o.name: sum(len(pl.vertices) - 2 for pl in o.data.polygons) for o in bpy.data.objects if o.type == "MESH"}
    hat_t = sum(t for n_, t in tris.items() if n_.startswith(("hat", "feather", "zucchetto", "phrygian")))
    log("triangles: total %d, headwear %d, garments %d" % (sum(tris.values()), hat_t,
        sum(t for n_, t in tris.items() if not n_.startswith("Human"))))
    export(rig, name)


MUSKET_OFFSET = (0.01, 0.02, -0.42)     # butt position relative to the hand_r head in the rest pose


def _musket(rig):
    """Austrian infantry musket, 1784 pattern, at shoulder arms: full-length walnut stock, round barrel,
    brass bands and butt plate, lock plate, trigger guard, ramrod, sling. Welded to the right hand."""
    bpy.context.view_layer.update()
    hand = (rig.matrix_world @ rig.pose.bones["hand_r"].matrix).to_translation()
    sh = (rig.matrix_world @ rig.pose.bones["upperarm_r"].matrix).to_translation()
    # the stock's wrist (z0 + 0.42) sits in the palm; see MUSKET_OFFSET (build_animations models the same weld)
    x, y = hand.x + MUSKET_OFFSET[0], hand.y + MUSKET_OFFSET[1]
    z0 = hand.z + MUSKET_OFFSET[2]
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
                     "breeches": "grey_coat", "stockings": "stocking", "boots": "leather", "boot_height": 0.12, "hat": "straw", "buttons": False},
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
                         "breeches": "charcoal", "stockings": "grey_coat", "boots": "leather", "boot_height": 0.12, "hat": "felt", "button_colour": "pewter", "max_tex": 1024},
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
                      "breeches": "brown_coat", "stockings": "grey_coat", "boots": "leather", "boot_height": 0.30, "hat": "straw", "hat_colour": "brown_coat", "buttons": False, "max_tex": 1024},
    # flisak: Vistula raftsman in a sukmana-style coat and cap
    "dist_raftsman": {"macro": {"gender": 1.0, "age": 0.38, "muscle": 0.8, "weight": 0.5, "height": 0.62}, "targets": {"head-rectangular": 0.3, "chin-width-incr": 0.2},
                      "hair": "long01", "hair_tint": "blond", "brows": "eyebrow001", "coat": "sukmana", "coat_len": "long", "collar": "cream", "sash": "facing_red",
                      "boots": "leather", "boot_height": 0.30, "hat": "felt", "hat_colour": "black", "buttons": False, "max_tex": 1024},
    "dist_customs_clerk": {"macro": {"gender": 0.9, "age": 0.36, "muscle": 0.35, "weight": 0.4, "height": 0.55}, "targets": {"nose-point-width-decr": 0.3},
                           "hair": "ponytail01", "hair_tint": "brown", "brows": "eyebrow002", "coat": "grey_white", "coat_len": "mid", "cuffs": "black", "collar": "black",
                           "breeches": "grey_white", "stockings": "stocking", "boots": "black", "boot_height": 0.12, "hat": "tricorne", "button_colour": "pewter", "max_tex": 1024},
    # Kleparz: grain market, stables, carts
    "dist_grain_dealer": {"macro": {"gender": 0.95, "age": 0.5, "muscle": 0.5, "weight": 0.72, "height": 0.54}, "targets": {"head-square": 0.3, "chin-jaw-drop-incr": 0.2},
                          "hair": "short01", "hair_tint": "brown", "brows": "eyebrow005", "coat": "mustard", "coat_len": "mid", "collar": "brown_coat", "cuffs": "brown_coat",
                          "breeches": "brown_coat", "stockings": "stocking", "boots": "tan_boot", "boot_height": 0.30, "hat": "felt", "hat_colour": "brown_coat", "button_colour": "brass", "max_tex": 1024},
    "dist_horse_dealer": {"macro": {"gender": 1.0, "age": 0.44, "muscle": 0.65, "weight": 0.5, "height": 0.6, "race": {"caucasian": 0.85, "asian": 0.1, "african": 0.05}},
                          "targets": {"nose-hump-incr": 0.4, "head-oval": 0.2}, "hair": "short04", "hair_tint": "black", "brows": "eyebrow007",
                          "coat": "leather", "coat_len": "mid", "collar": "fur", "cuffs": "fur", "sash": "facing_red", "breeches": "buff",
                          "boots": "black", "boot_height": 0.40, "hat": "krakuska", "buttons": False, "sword": False, "max_tex": 1024},
    "dist_carter": {"macro": {"gender": 1.0, "age": 0.5, "muscle": 0.65, "weight": 0.55, "height": 0.55}, "targets": {"chin-prominent-incr": 0.3},
                    "hair": "short02", "hair_tint": "dark_brown", "brows": "eyebrow003", "coat": "brown_coat", "coat_len": "mid", "collar": "brown_coat", "sash": "leather",
                    "breeches": "grey_coat", "stockings": "grey_coat", "boots": "leather", "boot_height": 0.38, "hat": "felt", "hat_colour": "grey_coat", "buttons": False, "max_tex": 1024},
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
    hats_m = ["cap", "tricorne", None, "felt", None, "krakuska"]
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
