"""Assets for Krakow 1795 (Rynek Glowny, winter 1795/96). Fable (2004) silhouettes (walls that lean a little,
roofs that sag and flare, chunky stone) dressed in baked PBR materials so the buildings sit beside the realistic
MakeHuman characters: lime plaster, brick, sandstone, beaver-tail roof tiles, weathered oak, iron, glass, snow.

Run:  blender -b --python assets/blender/build_assets.py [-- --rebake] [-- --only tenement_a,st_marys]
      blender -b --python assets/blender/build_assets.py -- --textures      (bake the texture cache only)
      blender -b --python assets/blender/build_assets.py -- --animals       (animals and the dragon)
Writes one .glb per asset into assets/models/.

Conventions
- Metres. Blender Z up. glTF export maps Blender (x, y, z) -> Godot (x, z, -y).
- Buildings: front face at Blender -Y (Godot +Z). Origin at base centre.
- Figures: front at Blender +Y (Godot -Z), matching a Node3D's forward. Origin at feet.
- Collision meshes are named <asset>-colonly; Godot turns them into StaticBody3D colliders on import.
- Blender 5.x: transform_apply also bakes location, so every primitive ends up with world-space vertices and a
  zero origin. Every helper that edits vertices relies on that.

Materials
- M(key) returns a textured material when PAL key maps to a texture kind in TEX_OF (plaster, brick, sandstone,
  tile, oak, iron, metal, glass, snow, cloth, cobbles, thatch, log, field); otherwise a flat colour.
- Each kind is a procedural node tree (tileable: 4D noise on a torus, cell patterns with integer counts) baked
  with Cycles onto a plane the size of one texture repeat: DIFFUSE colour, ROUGHNESS, tangent NORMAL. The PNGs
  are cached in assets/textures/ (skipped on re-runs unless --rebake). Texel density is ~512 px/m everywhere
  (2048 px over 4 m for plaster, tile, cobbles, field; 1024 px over 2 m for the rest).
- The export material multiplies the baked colour by a per-key tint (glTF baseColorFactor), so one plaster
  bake serves ochre, rose, cream, sage and blue houses. Keys ending in "_damp" use the plaster bake with a
  rising-damp tide line anchored at z=0 (plinths).
- UVs are generated at export (auto_uv) per face: walls map u along the wall, v up; roof slopes map v up the
  slope so tile courses run level; vertical cylinders and domes map around their axis. Faces keep a random
  per-part offset so repeats do not line up.
"""
import bpy
import bmesh
import math
import os
import random
import sys
import time
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "models")
TEX = os.path.join(ROOT, "assets", "textures")
os.makedirs(OUT, exist_ok=True)
os.makedirs(TEX, exist_ok=True)
RNG = random.Random(1795)
RNG_UV = random.Random(96)
REBAKE = "--rebake" in sys.argv
WONK = 0.5          # global scale on finish(wonk=...): old masonry, not cartoon
JPEG_Q = 88

# ------------------------------------------------------------------ palette
PAL = {
    "plaster_ochre": (0.90, 0.64, 0.30), "plaster_rose": (0.86, 0.52, 0.42), "plaster_cream": (0.94, 0.84, 0.58),
    "plaster_sage": (0.58, 0.68, 0.44), "plaster_blue": (0.50, 0.64, 0.78), "plaster_white": (0.94, 0.91, 0.84),
    "stone": (0.70, 0.65, 0.55), "stone_dark": (0.46, 0.43, 0.38), "stone_pale": (0.80, 0.76, 0.66),
    "brick": (0.58, 0.28, 0.19), "brick_dark": (0.42, 0.19, 0.14),
    "tile": (0.56, 0.26, 0.16), "tile_dark": (0.38, 0.17, 0.12), "tile_moss": (0.46, 0.34, 0.18),
    "copper": (0.26, 0.50, 0.44), "lead": (0.32, 0.33, 0.37), "gold": (0.95, 0.74, 0.30),
    "glass": (0.09, 0.11, 0.15), "glass_warm": (0.50, 0.34, 0.15),
    "wood": (0.46, 0.31, 0.18), "wood_dark": (0.26, 0.17, 0.10), "timber": (0.30, 0.20, 0.12),
    "iron": (0.10, 0.10, 0.11), "ember": (0.9, 0.25, 0.05), "flame": (1.0, 0.6, 0.2), "soot": (0.08, 0.075, 0.07), "canvas": (0.76, 0.66, 0.50), "canvas_stripe": (0.58, 0.22, 0.20),
    "snow": (0.90, 0.92, 0.96), "skin": (0.86, 0.66, 0.54), "hair": (0.24, 0.16, 0.10), "eye": (0.05, 0.05, 0.06),
    "white_coat": (0.92, 0.92, 0.94), "facing_red": (0.66, 0.12, 0.14), "black": (0.07, 0.07, 0.08),
    "crimson": (0.58, 0.10, 0.16), "zupan_gold": (0.86, 0.68, 0.30), "sukmana": (0.84, 0.80, 0.70),
    "red_cap": (0.76, 0.12, 0.12), "green_coat": (0.16, 0.32, 0.22), "brown_coat": (0.38, 0.25, 0.14),
    "navy": (0.14, 0.18, 0.34), "feather": (0.10, 0.48, 0.36), "shutter": (0.30, 0.42, 0.36),
    # architecture added with the texture pass
    "void": (0.025, 0.025, 0.03), "plaster_lime": (0.93, 0.93, 0.92), "plaster_limeblue": (0.80, 0.86, 0.92),
    "plaster_grey": (0.74, 0.72, 0.68), "cobble": (1.0, 1.0, 1.0), "thatch": (1.0, 1.0, 1.0), "log": (1.0, 1.0, 1.0),
    "log_lime": (0.95, 0.96, 1.0), "field": (1.0, 1.0, 1.0), "water": (0.05, 0.08, 0.10), "hay": (0.72, 0.60, 0.36),
    "salt": (0.86, 0.85, 0.82), "straw": (0.80, 0.70, 0.45),
    # building pass 2: painted shutters per district, stained glass, copper patina, wooden shingles
    "shutter_red": (0.52, 0.17, 0.13), "shutter_blue": (0.26, 0.38, 0.52), "shutter_ochre": (0.70, 0.52, 0.24),
    "shutter_grey": (0.46, 0.48, 0.46), "shutter_brown": (0.36, 0.24, 0.15),
    "glass_stained": (1.0, 1.0, 1.0), "patina": (1.0, 1.0, 1.0), "shingle": (1.0, 1.0, 1.0), "shingle_dark": (1.0, 1.0, 1.0),
    "plaster_pink": (0.90, 0.68, 0.62), "plaster_straw": (0.92, 0.80, 0.52), "plaster_mint": (0.72, 0.82, 0.70),
    "plaster_oxblood": (0.60, 0.30, 0.24), "plaster_umber": (0.72, 0.58, 0.42),
}
_mats = {}

# texture kind -> (resolution, metres per repeat)
TEXSPEC = {
    "plaster": (2048, 4.0), "plaster_damp": (2048, 4.0), "tile": (2048, 4.0), "cobbles": (2048, 4.0), "field": (2048, 4.0),
    "brick": (1024, 2.0), "sandstone": (1024, 2.0), "oak": (1024, 2.0), "iron": (1024, 2.0), "metal": (1024, 2.0),
    "glass": (1024, 2.0), "snow": (1024, 2.0), "cloth": (1024, 2.0), "thatch": (1024, 2.0), "log": (1024, 2.0),
    "stained": (1024, 2.0), "patina": (1024, 2.0), "shingle": (2048, 4.0),
}
# bump a kind's revision to force a rebake of just that kind (a <kind>.rev sidecar in assets/textures records it)
TEX_REV = {"snow": 2, "brick": 2, "stained": 1, "patina": 1, "shingle": 1, "flags": 2, "mud": 3}
TEX_OF = {}
for _k in ("plaster_ochre", "plaster_rose", "plaster_cream", "plaster_sage", "plaster_blue", "plaster_white",
           "plaster_lime", "plaster_limeblue", "plaster_grey", "plaster_pink", "plaster_straw", "plaster_mint",
           "plaster_oxblood", "plaster_umber", "shutter_red", "shutter_blue", "shutter_ochre", "shutter_grey", "shutter_brown"):
    TEX_OF[_k] = "plaster"
TEX_OF.update({"stone": "sandstone", "stone_dark": "sandstone", "stone_pale": "sandstone", "brick": "brick",
               "brick_dark": "brick", "tile": "tile", "tile_dark": "tile", "tile_moss": "tile", "wood": "oak",
               "wood_dark": "oak", "timber": "oak", "shutter": "oak", "iron": "iron", "lead": "metal",
               "copper": "metal", "glass": "glass", "glass_warm": "glass", "snow": "snow", "canvas": "cloth",
               "canvas_stripe": "cloth", "cobble": "cobbles", "thatch": "thatch", "log": "log", "log_lime": "log",
               "field": "field", "hay": "thatch", "straw": "thatch", "salt": "snow", "glass_stained": "stained",
               "patina": "patina", "shingle": "shingle", "shingle_dark": "shingle"})
# tint = glTF baseColorFactor over the bake. Neutral bakes (plaster, metal, glass, cloth) take the palette colour.
TINT = {"brick": (1, 1, 1), "brick_dark": (0.70, 0.64, 0.62), "tile": (1, 1, 1), "tile_dark": (0.74, 0.68, 0.66),
        "tile_moss": (0.86, 0.86, 0.72), "stone": (0.92, 0.91, 0.90), "stone_dark": (0.64, 0.63, 0.62),
        "stone_pale": (1, 1, 1), "wood": (1, 1, 1), "wood_dark": (0.56, 0.52, 0.50), "timber": (0.70, 0.66, 0.62),
        "shutter": (0.60, 0.82, 0.74), "iron": (1, 1, 1), "snow": (1, 1, 1), "cobble": (1, 1, 1), "thatch": (0.85, 0.8, 0.74),
        "log": (0.78, 0.70, 0.62), "log_lime": (1, 1, 1), "field": (1, 1, 1), "hay": (1.0, 1.0, 1.0),
        "straw": (1.0, 1.0, 1.0), "salt": (0.95, 0.93, 0.90), "glass_stained": (1, 1, 1), "patina": (1, 1, 1),
        "shingle": (1, 1, 1), "shingle_dark": (0.66, 0.64, 0.64)}
METALLIC = {"iron": 0.55, "metal": 0.25}
_tex_rep = {}        # material name -> metres per repeat (read by auto_uv)


def _desat(c, k=0.18, dim=0.96):
    l = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
    return tuple((v + (l - v) * k) * dim for v in c)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mats.clear()
    _tex_rep.clear()
    _MARKS.clear()
    _CLIMB.clear()
    _EXTRA.clear()


_EXTRA = []          # (name, object): separate child nodes kept out of the joined visual (runtime-tagged parts)
_CLIMB = []          # (kind, object): climbable colliders exported as climb_<kind>_<n>-colonly
_MARKS = []          # [kind, location, rot_z]: named empties (Chimney_n, Window_n, Furnace_n) exported with the asset


# ------------------------------------------------------------------ procedural texture graphs
class _G:
    """Tiny node-graph builder for tileable procedural textures in UV space (u, v in 0..1 = one repeat)."""

    def __init__(s, nt):
        s.nt, s.N, s.L = nt, nt.nodes, nt.links
        tc = s.N.new("ShaderNodeTexCoord")
        sep = s.N.new("ShaderNodeSeparateXYZ")
        s.L.new(tc.outputs["UV"], sep.inputs[0])
        s.u, s.v = sep.outputs[0], sep.outputs[1]
        s.cu, s.su = s.m("COSINE", s.mul(s.u, math.tau)), s.m("SINE", s.mul(s.u, math.tau))
        s.cv, s.sv = s.m("COSINE", s.mul(s.v, math.tau)), s.m("SINE", s.mul(s.v, math.tau))

    def _in(s, sock, val):
        if isinstance(val, bpy.types.NodeSocket):
            s.L.new(val, sock)
        elif isinstance(val, (tuple, list)):
            val = tuple(val)
            if sock.type == "RGBA" and len(val) == 3:
                val = val + (1.0,)
            sock.default_value = val
        else:
            sock.default_value = val

    def m(s, op, a, b=0.0, c=0.0, clamp=False):
        n = s.N.new("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        s._in(n.inputs[0], a)
        s._in(n.inputs[1], b)
        s._in(n.inputs[2], c)
        return n.outputs[0]

    def add(s, a, b): return s.m("ADD", a, b)
    def sub(s, a, b): return s.m("SUBTRACT", a, b)
    def mul(s, a, b): return s.m("MULTIPLY", a, b)
    def div(s, a, b): return s.m("DIVIDE", a, b)
    def mn(s, a, b): return s.m("MINIMUM", a, b)
    def mx(s, a, b): return s.m("MAXIMUM", a, b)
    def fl(s, a): return s.m("FLOOR", a)
    def fr(s, a): return s.m("FRACT", a)
    def mod(s, a, b): return s.m("FLOORED_MODULO", a, b)
    def clamp(s, a): return s.m("ADD", a, 0.0, clamp=True)
    def one_minus(s, a): return s.m("SUBTRACT", 1.0, a, clamp=True)
    def lerp(s, t, a, b): return s.add(a, s.mul(t, s.sub(b, a)))
    def edge(s, c): return s.mn(c, s.sub(1.0, c))          # distance of a cell coordinate to the nearest cell edge

    def smooth(s, x, e0, e1):
        n = s.N.new("ShaderNodeMapRange")
        n.interpolation_type = "SMOOTHSTEP"
        n.clamp = True
        s._in(n.inputs[0], x)
        s._in(n.inputs[1], e0)
        s._in(n.inputs[2], e1)
        n.inputs[3].default_value, n.inputs[4].default_value = 0.0, 1.0
        return n.outputs[0]

    def comb(s, x, y, z=0.0):
        n = s.N.new("ShaderNodeCombineXYZ")
        s._in(n.inputs[0], x)
        s._in(n.inputs[1], y)
        s._in(n.inputs[2], z)
        return n.outputs[0]

    def _torus(s, fu, fv, seed):
        ru, rv = fu / math.tau, fv / math.tau
        x = s.add(s.mul(s.cu, ru), seed * 5.31)
        y = s.mul(s.su, ru)
        z = s.mul(s.cv, rv)
        w = s.add(s.mul(s.sv, rv), seed * 2.73)
        return s.comb(x, y, z), w

    def noise(s, fu, fv, detail=3.0, rough=0.5, dist=0.0, seed=0.0, wshift=None):
        """Tileable fBm: ~fu features across and fv up one repeat."""
        vec, w = s._torus(fu, fv, seed)
        if wshift is not None:
            w = s.add(w, wshift)
        n = s.N.new("ShaderNodeTexNoise")
        n.noise_dimensions = "4D"
        s.L.new(vec, n.inputs["Vector"])
        s._in(n.inputs["W"], w)
        n.inputs["Scale"].default_value = 1.0
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        n.inputs["Distortion"].default_value = dist
        return n.outputs["Fac"]

    def voronoi(s, fu, fv, feature="F1", seed=0.0, rand=1.0):
        vec, w = s._torus(fu, fv, seed)
        n = s.N.new("ShaderNodeTexVoronoi")
        n.voronoi_dimensions = "4D"
        n.feature = feature
        s.L.new(vec, n.inputs["Vector"])
        s._in(n.inputs["W"], w)
        n.inputs["Scale"].default_value = 1.0
        n.inputs["Randomness"].default_value = rand
        return n.outputs["Distance"]

    def white(s, a, b, seed=0.0):
        n = s.N.new("ShaderNodeTexWhiteNoise")
        n.noise_dimensions = "3D"
        s.L.new(s.comb(a, b, seed), n.inputs["Vector"])
        return n.outputs["Value"]

    def mix(s, fac, a, b, blend="MIX"):
        n = s.N.new("ShaderNodeMix")
        n.data_type = "RGBA"
        n.blend_type = blend
        n.clamp_factor = True
        s._in(n.inputs[0], fac)
        s._in([i for i in n.inputs if i.name == "A" and i.type == "RGBA"][0], a)
        s._in([i for i in n.inputs if i.name == "B" and i.type == "RGBA"][0], b)
        return [o for o in n.outputs if o.type == "RGBA"][0]

    def ramp(s, x, stops):
        n = s.N.new("ShaderNodeValToRGB")
        els = n.color_ramp.elements
        while len(els) < len(stops):
            els.new(0.5)
        for e, (p, c) in zip(els, stops):
            e.position = p
            e.color = tuple(c) + (1.0,)
        s._in(n.inputs[0], x)
        return n.outputs[0]

    def cells(s, nu, nv, stagger=0.5):
        """Running-bond cells: nu across, nv up (integers so the pattern tiles). Returns cu, cv, iu, iv, row parity."""
        rv = s.mul(s.v, nv)
        iv = s.fl(rv)
        cv = s.fr(rv)
        par = s.mod(iv, 2.0)
        ru = s.add(s.mul(s.u, nu), s.mul(par, stagger))
        iu = s.mod(s.fl(ru), nu)
        return s.fr(ru), cv, iu, s.mod(iv, nv), par


def _tx_plaster(g, damp=False):
    big = g.noise(3, 3, 4, 0.55, seed=1)
    mid = g.noise(14, 14, 5, 0.55, seed=2)
    fine = g.noise(110, 110, 3, 0.6, seed=3)
    streak = g.noise(40, 2.2, 4, 0.5, dist=0.4, seed=4)
    zone = g.smooth(g.noise(5, 1.5, 2, 0.5, seed=5), 0.45, 0.68)
    streakm = g.mul(g.smooth(streak, 0.52, 0.72), zone)
    col = g.ramp(big, [(0.2, (0.78, 0.75, 0.69)), (0.8, (0.94, 0.92, 0.87))])
    col = g.mix(g.mul(g.sub(mid, 0.3), 0.5), col, (0.72, 0.69, 0.62))
    col = g.mix(g.mul(streakm, 0.6), col, (0.40, 0.37, 0.33))
    # plaster lost in patches: the rough lime render and a hint of brick show through
    lossn = g.noise(6, 6, 6, 0.6, seed=6)
    loss = g.smooth(lossn, 0.675, 0.685)
    repair = g.smooth(g.noise(7, 7, 2, 0.4, seed=60), 0.60, 0.62)
    col = g.mix(g.mul(repair, 0.35), col, (0.86, 0.84, 0.78))
    under = g.mix(g.smooth(g.noise(30, 60, 2, seed=7), 0.4, 0.7), (0.60, 0.52, 0.44), (0.52, 0.30, 0.22))
    col = g.mix(loss, col, under)
    rim = g.mul(g.smooth(lossn, 0.69, 0.705), g.one_minus(loss))
    col = g.mix(g.mul(rim, 0.5), col, (0.55, 0.52, 0.47))
    # hairline cracks, only in some zones
    vd = g.voronoi(6, 6, "DISTANCE_TO_EDGE", seed=8)
    crack = g.mul(g.one_minus(g.smooth(vd, 0.0, 0.007)), g.smooth(g.noise(3, 3, 2, seed=9), 0.66, 0.74))
    col = g.mix(g.mul(crack, 0.55), col, (0.30, 0.28, 0.25))
    h = g.add(0.55, g.mul(g.sub(fine, 0.5), 0.45))
    h = g.add(h, g.mul(g.sub(mid, 0.5), 0.35))
    h = g.sub(h, g.mul(loss, 0.45))
    h = g.sub(h, g.mul(crack, 0.5))
    rough = g.add(0.80, g.mul(fine, 0.12))
    rough = g.sub(rough, g.mul(streakm, 0.06))
    if damp:
        zm = g.mul(g.v, 4.0)                                       # metres above the base (v anchored at z=0)
        tide = g.add(0.85, g.mul(g.sub(g.noise(10, 0, 3, 0.6, seed=10), 0.5), 0.7))
        above = g.smooth(g.sub(zm, tide), -0.06, 0.02)
        dampm = g.one_minus(above)
        col = g.mix(g.mul(dampm, 0.62), col, (0.34, 0.33, 0.28))
        salts = g.mul(g.mul(g.smooth(g.sub(zm, tide), -0.25, -0.03), dampm), g.smooth(fine, 0.55, 0.62))
        col = g.mix(g.mul(salts, 0.7), col, (0.93, 0.93, 0.90))
        splash = g.one_minus(g.smooth(zm, 0.0, 0.4))
        col = g.mix(g.mul(splash, 0.5), col, (0.22, 0.20, 0.17))
        rough = g.sub(rough, g.mul(dampm, 0.22))
        h = g.sub(h, g.mul(splash, g.mul(fine, 0.3)))
    h = g.add(h, g.mul(repair, 0.08))
    return col, rough, h, 0.014


def _tx_brick(g):
    # English-style bond: a course of stretchers (8 per 2 m), a course of headers (16), 26 courses per 2 m
    rv = g.mul(g.v, 26.0)
    iv = g.fl(rv)
    cv = g.fr(rv)
    par = g.mod(iv, 2.0)
    nu = g.add(8.0, g.mul(par, 8.0))
    ru = g.add(g.mul(g.u, nu), g.mul(par, 0.5))
    iu = g.mod(g.fl(ru), nu)
    cu = g.fr(ru)
    du = g.mul(g.edge(cu), g.div(2.0, nu))
    dv = g.mul(g.edge(cv), 2.0 / 26.0)
    d = g.mn(du, dv)
    bm = g.smooth(d, 0.004, 0.007)
    hb = g.smooth(d, 0.004, 0.018)
    r = g.white(g.add(iu, g.mul(par, 57.0)), iv, 1.0)
    r2 = g.white(g.add(iu, g.mul(par, 57.0)), iv, 2.0)
    bc = g.ramp(r, [(0.0, (0.34, 0.13, 0.08)), (0.35, (0.48, 0.21, 0.13)), (0.75, (0.57, 0.27, 0.17)), (1.0, (0.64, 0.36, 0.23))])
    glaze = g.mul(par, g.smooth(r2, 0.80, 0.82))                # dark glazed headers (Gothic zendrowka)
    bc = g.mix(g.mul(glaze, 0.8), bc, (0.24, 0.12, 0.10))
    fine = g.noise(90, 90, 4, 0.6, seed=11)
    bc = g.mix(g.mul(g.sub(fine, 0.35), 0.45), bc, (0.28, 0.14, 0.10))
    soot = g.smooth(g.noise(4, 3, 4, seed=12), 0.5, 0.75)
    bc = g.mix(g.mul(soot, 0.35), bc, (0.20, 0.16, 0.14))
    mort = g.mix(g.noise(60, 60, 3, seed=13), (0.50, 0.47, 0.42), (0.66, 0.63, 0.57))
    mort = g.mix(g.mul(soot, 0.4), mort, (0.30, 0.28, 0.25))
    col = g.mix(bm, mort, bc)
    # old lime-wash surviving in patches, thin enough that the bond shows through
    lw = g.mul(g.smooth(g.noise(3, 3, 5, 0.6, seed=90), 0.60, 0.66), g.smooth(g.noise(40, 40, 3, seed=91), 0.25, 0.55))
    col = g.mix(g.mul(lw, 0.55), col, (0.78, 0.76, 0.70))
    h = g.add(g.mul(bm, g.add(0.55, g.mul(hb, 0.35))), g.mul(fine, 0.12))
    rough = g.lerp(bm, 0.95, g.sub(0.86, g.mul(glaze, 0.45)))
    return col, rough, h, 0.012


def _tx_sandstone(g):
    cu, cv, iu, iv, par = g.cells(3.0, 4.0, 0.5)
    d = g.mn(g.mul(g.edge(cu), 2.0 / 3.0), g.mul(g.edge(cv), 0.5))
    bm = g.smooth(d, 0.002, 0.005)
    ch = g.smooth(d, 0.002, 0.02)
    r = g.white(iu, iv, 3.0)
    col = g.ramp(r, [(0.0, (0.52, 0.47, 0.39)), (0.3, (0.64, 0.58, 0.47)), (0.65, (0.72, 0.66, 0.53)), (1.0, (0.78, 0.71, 0.60))])
    tool = g.add(0.5, g.mul(g.m("SINE", g.mul(g.add(g.mul(g.u, 150.0), g.mul(g.v, 150.0)), math.tau)), 0.5))
    blot = g.noise(10, 10, 5, 0.6, seed=61)
    col = g.mix(g.mul(g.sub(blot, 0.35), 0.5), col, (0.46, 0.42, 0.35))
    bed = g.noise(2.5, 36, 3, 0.5, dist=0.6, seed=14)
    col = g.mix(g.mul(g.sub(bed, 0.4), 0.5), col, (0.52, 0.46, 0.36))
    grain = g.noise(160, 160, 2, 0.6, seed=15)
    col = g.mix(g.mul(g.sub(grain, 0.4), 0.3), col, (0.84, 0.80, 0.70))
    grime = g.mul(g.smooth(g.noise(4, 4, 5, seed=16), 0.48, 0.72), g.smooth(g.noise(30, 3, 3, dist=0.3, seed=17), 0.4, 0.7))
    col = g.mix(g.mul(grime, 0.55), col, (0.30, 0.28, 0.25))
    pits = g.one_minus(g.smooth(g.voronoi(70, 70, "F1", seed=18), 0.05, 0.14))
    pits = g.mul(pits, g.smooth(g.noise(6, 6, 2, seed=19), 0.5, 0.65))
    col = g.mix(g.mul(pits, 0.5), col, (0.35, 0.32, 0.27))
    col = g.mix(g.mul(g.one_minus(bm), 0.75), col, (0.40, 0.37, 0.32))
    h = g.add(g.mul(bm, g.add(0.6, g.mul(ch, 0.3))), g.mul(grain, 0.15))
    h = g.sub(h, g.mul(pits, 0.35))
    h = g.add(h, g.add(g.mul(tool, 0.06), g.mul(blot, 0.2)))
    rough = g.add(0.84, g.mul(grain, 0.1))
    return col, rough, h, 0.016


def _tx_tile(g):
    # beaver-tail (karpiowka) tiles: 16 across, 24 courses per 4 m, v runs up the slope, staggered by half a tile
    cu, cv, iu, iv, par = g.cells(16.0, 24.0, 0.5)
    x = g.sub(g.mul(cu, 2.0), 1.0)
    e = g.mul(g.mul(x, x), 0.30)                                  # rounded tail: edge sits higher at the sides
    t = g.sub(cv, e)
    own = g.smooth(t, -0.015, 0.012)
    gap = g.smooth(g.mul(g.edge(cu), 0.25), 0.002, 0.006)
    h_own = g.sub(1.0, g.mul(g.clamp(t), 0.45))
    h_below = g.sub(0.52, g.mul(g.sub(e, cv), 0.25))
    h = g.lerp(own, h_below, h_own)
    h = g.mul(h, g.add(0.7, g.mul(gap, 0.3)))
    r = g.white(iu, iv, 4.0)
    col = g.ramp(r, [(0.0, (0.34, 0.13, 0.08)), (0.3, (0.46, 0.18, 0.10)), (0.7, (0.54, 0.24, 0.13)), (1.0, (0.50, 0.29, 0.18))])
    fine = g.noise(120, 120, 3, 0.6, seed=20)
    col = g.mix(g.mul(g.sub(fine, 0.35), 0.35), col, (0.30, 0.15, 0.10))
    dirt = g.one_minus(g.smooth(t, 0.0, 0.25))
    col = g.mix(g.mul(dirt, 0.35), col, (0.22, 0.14, 0.10))
    lich = g.mul(g.smooth(g.noise(6, 6, 5, seed=21), 0.56, 0.68), g.smooth(g.noise(50, 50, 3, seed=22), 0.35, 0.6))
    col = g.mix(g.mul(lich, 0.75), col, (0.40, 0.40, 0.30))
    spot = g.mul(g.one_minus(g.smooth(g.voronoi(90, 90, "F1", seed=23), 0.08, 0.16)), g.smooth(g.noise(8, 8, 2, seed=24), 0.55, 0.65))
    col = g.mix(g.mul(spot, 0.7), col, (0.70, 0.62, 0.34))
    col = g.mix(g.mul(g.one_minus(own), 0.55), col, (0.10, 0.06, 0.05))
    col = g.mix(g.mul(g.one_minus(gap), 0.6), col, (0.08, 0.05, 0.04))
    rough = g.add(0.68, g.add(g.mul(lich, 0.2), g.mul(fine, 0.08)))
    return col, rough, h, 0.025


def _tx_oak(g):
    iu = g.fl(g.mul(g.u, 8.0))
    cu = g.fr(g.mul(g.u, 8.0))
    r = g.white(iu, 0.0, 5.0)
    grain = g.noise(90, 2.5, 6, 0.6, dist=0.5, seed=25, wshift=g.mul(r, 13.0))
    rings = g.add(0.5, g.mul(g.m("SINE", g.mul(g.add(g.mul(g.u, 56.0), g.mul(grain, 4.0)), math.tau)), 0.5))
    ringl = g.smooth(rings, 0.78, 0.96)
    col = g.ramp(r, [(0.0, (0.24, 0.16, 0.10)), (1.0, (0.38, 0.27, 0.17))])
    col = g.mix(g.mul(ringl, 0.4), col, (0.20, 0.14, 0.09))
    col = g.mix(g.mul(g.sub(grain, 0.3), 0.4), col, (0.52, 0.42, 0.30))
    weather = g.smooth(g.noise(4, 5, 4, seed=26), 0.38, 0.7)
    col = g.mix(g.mul(weather, 0.5), col, (0.36, 0.34, 0.31))
    check = g.mul(g.smooth(g.noise(160, 3, 3, seed=27), 0.74, 0.77), g.smooth(g.noise(5, 5, 2, seed=28), 0.5, 0.62))
    col = g.mix(g.mul(check, 0.9), col, (0.08, 0.06, 0.05))
    gap = g.smooth(g.mul(g.edge(cu), 0.25), 0.002, 0.005)
    col = g.mix(g.one_minus(gap), col, (0.06, 0.05, 0.04))
    h = g.add(g.mul(gap, 0.6), g.mul(grain, 0.25))
    h = g.sub(h, g.add(g.mul(check, 0.35), g.mul(ringl, 0.08)))
    rough = g.add(0.74, g.mul(weather, 0.15))
    return col, rough, h, 0.006


def _tx_iron(g):
    dents = g.smooth(g.voronoi(40, 40, "F1", seed=29), 0.0, 0.6)
    rust = g.mul(g.smooth(g.noise(8, 8, 6, 0.6, seed=30), 0.58, 0.68), 0.8)
    fine = g.noise(120, 120, 3, seed=31)
    col = g.mix(g.mul(fine, 0.3), (0.11, 0.11, 0.12), (0.20, 0.19, 0.19))
    rc = g.ramp(fine, [(0.3, (0.26, 0.12, 0.05)), (0.7, (0.46, 0.24, 0.10))])
    col = g.mix(rust, col, rc)
    h = g.add(g.mul(dents, 0.35), g.mul(rust, g.mul(fine, 0.5)))
    rough = g.add(0.45, g.mul(rust, 0.45))
    return col, rough, h, 0.004


def _tx_metal(g):
    iu = g.fl(g.mul(g.u, 4.0))
    cu = g.fr(g.mul(g.u, 4.0))
    seam = g.one_minus(g.smooth(g.mul(g.edge(cu), 0.5), 0.004, 0.014))
    cv = g.fr(g.add(g.mul(g.v, 2.0), g.mul(g.mod(iu, 2.0), 0.5)))
    cross = g.one_minus(g.smooth(g.edge(cv), 0.002, 0.006))
    streak = g.noise(24, 2, 4, dist=0.3, seed=32)
    big = g.noise(3, 3, 3, seed=33)
    col = g.mix(g.mul(g.sub(streak, 0.25), 0.5), (0.84, 0.84, 0.82), (0.62, 0.62, 0.60))
    col = g.mix(g.mul(big, 0.3), col, (0.95, 0.95, 0.92))
    col = g.mix(g.mul(g.add(seam, cross), 0.4), col, (0.45, 0.45, 0.44))
    h = g.add(g.add(seam, g.mul(cross, 0.5)), g.mul(g.noise(5, 5, 2, seed=34), 0.2))
    rough = g.add(0.5, g.mul(streak, 0.25))
    return col, rough, h, 0.01


def _tx_glass(g):
    # small leaded panes (8 x 8 per 2 m), each with its own tint and crown-glass wobble
    iu = g.fl(g.mul(g.u, 8.0))
    iv = g.fl(g.mul(g.v, 8.0))
    cu = g.fr(g.mul(g.u, 8.0))
    cv = g.fr(g.mul(g.v, 8.0))
    d = g.mul(g.mn(g.edge(cu), g.edge(cv)), 0.25)
    came = g.one_minus(g.smooth(d, 0.006, 0.010))
    r = g.white(iu, iv, 6.0)
    pane = g.ramp(r, [(0.0, (0.82, 0.86, 0.84)), (1.0, (1.0, 1.0, 0.97))])
    dirt = g.smooth(g.noise(6, 6, 4, seed=35), 0.5, 0.8)
    pane = g.mix(g.mul(dirt, 0.3), pane, (0.70, 0.68, 0.62))
    col = g.mix(came, pane, (0.08, 0.08, 0.08))
    wob = g.noise(30, 30, 2, seed=36)
    bull = g.sub(0.25, g.mul(g.add(g.mul(g.sub(cu, 0.5), g.sub(cu, 0.5)), g.mul(g.sub(cv, 0.5), g.sub(cv, 0.5))), 0.5))
    h = g.add(g.mul(came, 1.0), g.add(g.mul(wob, 0.15), g.mul(bull, 0.3)))
    rough = g.lerp(came, g.add(0.05, g.mul(dirt, 0.25)), 0.55)
    return col, rough, h, 0.003


def _tx_snow(g):
    # settled snow: soft wind ripples, a grain of little crystals, cold blue in the hollows (the subsurface tint
    # of real snow), and sparse glints: tiny facets with low roughness that catch lantern light
    lumps = g.noise(6, 6, 5, 0.55, seed=37)
    ripple = g.noise(3, 14, 3, 0.5, dist=0.8, seed=41)
    fine = g.noise(140, 140, 2, seed=38)
    grain = g.noise(420, 420, 1, seed=42)
    hol = g.one_minus(g.smooth(g.add(g.mul(lumps, 0.7), g.mul(ripple, 0.3)), 0.30, 0.62))
    col = g.mix(hol, (0.95, 0.965, 0.99), (0.70, 0.78, 0.93))
    col = g.mix(g.mul(g.smooth(fine, 0.2, 0.5), 0.25), (0.86, 0.89, 0.95), col)
    glint = g.mul(g.smooth(g.white(g.fl(g.mul(g.u, 360.0)), g.fl(g.mul(g.v, 360.0)), 9.0), 0.985, 0.992),
                  g.smooth(grain, 0.45, 0.6))
    col = g.mix(g.mul(glint, 0.9), col, (1.0, 1.0, 1.0))
    col = g.mix(g.mul(g.sub(grain, 0.4), 0.12), col, (0.80, 0.84, 0.92))
    h = g.add(g.add(g.mul(lumps, 0.6), g.mul(ripple, 0.25)), g.add(g.mul(fine, 0.1), g.mul(grain, 0.05)))
    rough = g.sub(g.add(0.70, g.mul(fine, 0.14)), g.mul(glint, 0.6))
    return col, rough, h, 0.03


def _tx_stained(g):
    """Leaded stained glass: diamond quarries in ruby, cobalt, amber, green and a pale grisaille, lead cames, a
    roundel of deeper colour every half repeat and a faint painted wash. Used as both colour and emission."""
    a = g.add(g.u, g.v)
    b = g.sub(g.u, g.v)
    ra, rb = g.mul(a, 6.0), g.mul(b, 6.0)
    ia, ib = g.fl(ra), g.fl(rb)
    ca, cb = g.fr(ra), g.fr(rb)
    d = g.mn(g.edge(ca), g.edge(cb))
    came = g.one_minus(g.smooth(d, 0.025, 0.06))
    k1, k2 = g.mod(g.sub(ia, ib), 12.0), g.mod(g.add(ia, ib), 12.0)
    r = g.white(k1, k2, 7.0)
    col = g.ramp(r, [(0.0, (0.62, 0.05, 0.05)), (0.22, (0.05, 0.12, 0.55)), (0.42, (0.85, 0.55, 0.08)),
                     (0.58, (0.10, 0.42, 0.14)), (0.74, (0.45, 0.08, 0.42)), (1.0, (0.85, 0.80, 0.60))])
    cu, cv = g.fr(g.mul(g.u, 2.0)), g.fr(g.mul(g.v, 2.0))
    rr = g.m("SQRT", g.add(g.mul(g.sub(cu, 0.5), g.sub(cu, 0.5)), g.mul(g.sub(cv, 0.5), g.sub(cv, 0.5))))
    disc = g.one_minus(g.smooth(rr, 0.26, 0.27))
    ring = g.mul(g.smooth(rr, 0.25, 0.265), g.one_minus(g.smooth(rr, 0.285, 0.30)))
    petal = g.smooth(g.m("SINE", g.mul(g.m("ARCTAN2", g.sub(cv, 0.5), g.sub(cu, 0.5)), 6.0)), 0.2, 0.5)
    inner = g.mix(g.mul(petal, g.one_minus(g.smooth(rr, 0.1, 0.2))), (0.70, 0.06, 0.08), (0.95, 0.72, 0.18))
    col = g.mix(disc, col, inner)
    came = g.mx(g.mul(came, g.one_minus(disc)), ring)
    wash = g.noise(12, 12, 4, seed=43)
    col = g.mix(g.mul(g.sub(wash, 0.35), 0.5), col, (0.20, 0.16, 0.10))
    col = g.mix(came, col, (0.03, 0.03, 0.03))
    h = g.add(g.mul(came, 1.0), g.mul(wash, 0.1))
    rough = g.lerp(came, 0.12, 0.6)
    return col, rough, h, 0.004


def _tx_patina(g):
    """Old copper sheet: verdigris over brown copper, standing seams (4 per 2 m) and staggered cross seams,
    darker streaks washed down from each seam, pale salt blooms."""
    iu = g.fl(g.mul(g.u, 4.0))
    cu = g.fr(g.mul(g.u, 4.0))
    seam = g.one_minus(g.smooth(g.mul(g.edge(cu), 0.5), 0.003, 0.012))
    cv = g.fr(g.add(g.mul(g.v, 3.0), g.mul(g.mod(iu, 2.0), 0.5)))
    cross = g.one_minus(g.smooth(g.mul(g.edge(cv), 0.66), 0.002, 0.006))
    streak = g.noise(40, 1.5, 4, 0.6, dist=0.4, seed=44)
    big = g.noise(3, 3, 4, seed=45)
    col = g.ramp(big, [(0.2, (0.22, 0.46, 0.40)), (0.6, (0.33, 0.60, 0.52)), (0.9, (0.45, 0.68, 0.60))])
    brown = g.smooth(g.mul(streak, g.add(0.6, g.mul(big, 0.5))), 0.52, 0.66)
    col = g.mix(g.mul(brown, 0.8), col, (0.26, 0.17, 0.10))
    bloom = g.smooth(g.noise(18, 18, 3, seed=46), 0.66, 0.74)
    col = g.mix(g.mul(bloom, 0.5), col, (0.72, 0.80, 0.74))
    col = g.mix(g.mul(g.add(seam, cross), 0.35), col, (0.12, 0.22, 0.18))
    h = g.add(g.add(seam, g.mul(cross, 0.4)), g.mul(g.noise(8, 8, 2, seed=47), 0.25))
    rough = g.add(0.55, g.mul(bloom, 0.2))
    return col, rough, h, 0.01


def _tx_shingle(g):
    """Split-oak shingles (gont): 32 courses per 4 m, 36 shingles across with a random width jitter, silver-grey
    weathering, darker butts, moss in the lower courses of shaded patches. v runs up the slope."""
    cu, cv, iu, iv, par = g.cells(36.0, 32.0, 0.5)
    r = g.white(iu, iv, 5.0)
    jog = g.mul(g.sub(g.white(iu, iv, 6.0), 0.5), 0.08)
    gap = g.smooth(g.mul(g.edge(g.fr(g.add(cu, jog))), 1.0 / 9.0), 0.002, 0.006)
    butt = g.smooth(cv, 0.0, 0.10)
    grain = g.noise(260, 8, 3, dist=0.4, seed=48)
    col = g.ramp(r, [(0.0, (0.30, 0.27, 0.24)), (0.4, (0.42, 0.38, 0.33)), (0.8, (0.52, 0.48, 0.42)), (1.0, (0.40, 0.31, 0.22))])
    col = g.mix(g.mul(g.sub(grain, 0.3), 0.4), col, (0.62, 0.60, 0.56))
    col = g.mix(g.mul(g.one_minus(butt), 0.55), col, (0.10, 0.09, 0.08))
    moss = g.mul(g.smooth(g.noise(5, 5, 4, seed=49), 0.58, 0.7), g.smooth(g.noise(60, 60, 2, seed=50), 0.4, 0.6))
    col = g.mix(g.mul(moss, 0.7), col, (0.26, 0.30, 0.14))
    col = g.mix(g.mul(g.one_minus(gap), 0.8), col, (0.05, 0.045, 0.04))
    h = g.add(g.mul(g.sub(1.0, g.mul(cv, 0.5)), gap), g.mul(grain, 0.15))
    rough = g.add(0.78, g.mul(grain, 0.12))
    return col, rough, h, 0.02


def _tx_cloth(g):
    # wool broadcloth: twill weave, slubs, wear, and soft drape folds running down the cloth (v is the hang
    # direction on garments) so the normal map catches light in the folds
    wu = g.m("SINE", g.mul(g.u, 520.0 * math.tau))
    wv = g.m("SINE", g.mul(g.v, 520.0 * math.tau))
    weave = g.add(0.5, g.mul(g.mul(wu, wv), 0.5))
    stain = g.smooth(g.noise(4, 4, 5, seed=39), 0.5, 0.78)
    slub = g.noise(300, 10, 2, seed=40)
    folds = g.noise(7.0, 0.9, 3, 0.45, seed=50)            # long streaks along v
    folds2 = g.noise(3.0, 0.5, 2, 0.5, seed=51)
    fold = g.add(g.mul(folds, 0.7), g.mul(folds2, 0.3))
    crease = g.smooth(fold, 0.42, 0.5)
    col = g.mix(g.mul(g.sub(slub, 0.4), 0.3), (0.92, 0.90, 0.85), (0.78, 0.75, 0.68))
    col = g.mix(g.mul(stain, 0.4), col, (0.50, 0.44, 0.36))
    col = g.mix(g.mul(g.sub(1.0, weave), 0.05), col, (0.5, 0.5, 0.5))
    col = g.mix(g.mul(g.one_minus(crease), 0.14), col, (0.35, 0.33, 0.30))    # faint shadow in the fold valleys
    h = g.add(g.add(g.mul(weave, 0.03), g.mul(slub, 0.03)), g.mul(fold, 0.94))
    return col, g.add(0.84, g.mul(slub, 0.1)), h, 0.02


def _tx_cobbles(g):
    # field stones set in staggered rows (24 x 28 per 4 m): lumpy, rounded, battered boulders rather than cut setts.
    # Every stone differs in size, position, roundness, outline (noise-warped), dome height, tilt, hue and brightness;
    # tops are bumpy with chipped facets and pits; some stones sit sunken and dirty; sand, gravel and frost in the
    # joints; wet dark patches at large scale.
    cu, cv, iu, iv, par = g.cells(24.0, 28.0, 0.5)
    r = g.white(iu, iv, 7.0)       # hue family
    r2 = g.white(iu, iv, 8.0)      # size
    r3 = g.white(iu, iv, 9.0)      # x offset
    r4 = g.white(iu, iv, 10.0)     # z offset
    r5 = g.white(iu, iv, 11.0)     # rounding / aspect
    r6 = g.white(iu, iv, 12.0)     # dome / brightness
    cw, chh = 4.0 / 24.0, 4.0 / 28.0
    shrink = g.add(0.0025, g.mul(r2, 0.007))
    rad = g.add(0.024, g.mul(r5, 0.034))          # heavy rounding: ovals and blobs, not rectangles
    offx = g.mul(g.sub(r3, 0.5), 0.12 * cw)
    offz = g.mul(g.sub(r4, 0.5), 0.10 * chh)
    # warp the outline so no edge is straight and no two stones share a shape
    wx = g.mul(g.sub(g.noise(80, 80, 3, seed=50), 0.5), 0.034)
    wz = g.mul(g.sub(g.noise(80, 80, 3, seed=51), 0.5), 0.034)
    px = g.m("ABSOLUTE", g.add(g.sub(g.mul(g.sub(cu, 0.5), cw), offx), wx))
    pz = g.m("ABSOLUTE", g.add(g.sub(g.mul(g.sub(cv, 0.5), chh), offz), wz))
    halfw = g.mx(g.sub(g.sub(cw / 2, rad), g.add(shrink, g.m("ABSOLUTE", offx))), 0.0)
    halfh = g.mx(g.sub(g.sub(chh / 2, rad), g.add(shrink, g.m("ABSOLUTE", offz))), 0.0)
    qx = g.sub(px, halfw)
    qz = g.sub(pz, halfh)
    ox, oz = g.mx(qx, 0.0), g.mx(qz, 0.0)
    outside = g.m("SQRT", g.add(g.mul(ox, ox), g.mul(oz, oz)))
    inside = g.mn(g.mx(qx, qz), 0.0)
    sd = g.sub(g.add(outside, inside), rad)
    stone = g.smooth(g.mul(sd, -1.0), 0.0, 0.004)
    # boulder profile: an ellipsoid cap over the stone's extents (steep at the rim, rounded crown, no ridges),
    # then bumps, worn facets, pits and chipped rims
    ew, eh = g.mul(g.add(halfw, rad), 1.12), g.mul(g.add(halfh, rad), 1.12)
    ex, ez = g.m("DIVIDE", px, ew), g.m("DIVIDE", pz, eh)
    cap = g.mul(stone, g.m("SQRT", g.mx(g.sub(1.0, g.add(g.mul(ex, ex), g.mul(ez, ez))), 0.0)))
    # worn flat on top (feet and wheels), steep and battered at the sides
    dome = g.mn(g.mul(cap, 1.6), 1.0)
    flat = g.smooth(cap, 0.5, 0.8)
    lump = g.mul(g.mul(g.sub(g.noise(44, 44, 4, seed=52), 0.5), 1.4), g.one_minus(g.mul(flat, 0.75)))
    facet = g.mul(g.mul(g.sub(g.voronoi(40, 40, feature="F1", seed=53), 0.35), 0.8), g.one_minus(g.mul(flat, 0.6)))
    pit = g.smooth(g.voronoi(120, 120, seed=54), 0.0, 0.09)
    chip = g.mul(g.smooth(g.voronoi(58, 58, seed=55), 0.0, 0.18), g.one_minus(flat))
    sunken = g.smooth(r2, 0.93, 0.96)
    # colour families and per-stone brightness
    grey = g.ramp(r, [(0.0, (0.20, 0.19, 0.19)), (0.5, (0.36, 0.35, 0.34)), (1.0, (0.50, 0.48, 0.45))])
    warm = g.ramp(r, [(0.0, (0.28, 0.21, 0.16)), (0.5, (0.44, 0.35, 0.27)), (1.0, (0.56, 0.46, 0.36))])
    cool = g.ramp(r, [(0.0, (0.22, 0.25, 0.30)), (0.5, (0.34, 0.37, 0.43)), (1.0, (0.46, 0.49, 0.54))])
    pink = g.ramp(r, [(0.0, (0.36, 0.27, 0.25)), (0.5, (0.50, 0.40, 0.37)), (1.0, (0.58, 0.48, 0.45))])
    fam = g.mix(g.smooth(r5, 0.25, 0.35), grey, warm)
    fam = g.mix(g.smooth(r5, 0.55, 0.65), fam, cool)
    fam = g.mix(g.smooth(r5, 0.88, 0.94), fam, pink)
    bright = g.add(0.78, g.mul(r6, 0.44))
    col = g.mix(1.0, fam, bright, blend="MULTIPLY")
    # mottling within a stone, speckle and mica flecks, lighter fresh chips, dark pits
    mottle = g.add(0.45, g.mul(g.noise(30, 30, 4, seed=56), 1.1))
    col = g.mix(1.0, col, mottle, blend="MULTIPLY")
    col = g.mix(g.mul(g.one_minus(dome), 0.55), col, g.mix(1.0, col, (0.6, 0.58, 0.55), blend="MULTIPLY"))
    speck = g.noise(320, 320, 1, seed=41)
    col = g.mix(g.mul(g.smooth(speck, 0.6, 0.66), 0.5), col, (0.12, 0.12, 0.12))
    col = g.mix(g.mul(g.smooth(speck, 0.32, 0.27), 0.45), col, (0.78, 0.76, 0.72))
    col = g.mix(g.mul(chip, 0.35), col, g.mix(1.0, col, (1.35, 1.32, 1.28), blend="MULTIPLY"))
    col = g.mix(g.mul(pit, 0.5), col, g.mix(1.0, col, (0.55, 0.55, 0.55), blend="MULTIPLY"))
    # large-scale wet and dirty patches, wheel tracks along u
    wet = g.smooth(g.noise(2.2, 2.2, 3, seed=45), 0.45, 0.7)
    track = g.mul(g.smooth(g.noise(1.0, 6.0, 2, seed=46), 0.55, 0.75), 0.5)
    col = g.mix(g.mul(wet, 0.45), col, (0.10, 0.10, 0.11))
    col = g.mix(track, col, g.mix(1.0, col, (0.7, 0.7, 0.7), blend="MULTIPLY"))
    col = g.mix(sunken, col, g.mix(1.0, col, (0.55, 0.55, 0.55), blend="MULTIPLY"))
    tilt = g.mul(g.add(g.mul(g.sub(cu, 0.5), g.sub(r2, 0.5)), g.mul(g.sub(cv, 0.5), g.sub(r, 0.5))), 1.4)
    wear = g.noise(8, 8, 4, seed=42)
    snowj = g.smooth(g.noise(9, 9, 5, seed=43), 0.62, 0.74)
    grain = g.noise(420, 420, 2, seed=47)
    gravel = g.smooth(g.voronoi(160, 160, seed=48), 0.0, 0.35)
    damp = g.smooth(g.noise(5, 5, 4, seed=49), 0.4, 0.75)
    joint = g.ramp(grain, [(0.3, (0.13, 0.11, 0.09)), (0.55, (0.22, 0.19, 0.15)), (0.8, (0.34, 0.30, 0.24))])
    joint = g.mix(g.mul(g.one_minus(gravel), 0.5), joint, (0.42, 0.40, 0.36))
    joint = g.mix(g.mul(damp, 0.5), joint, (0.08, 0.07, 0.06))
    joint = g.mix(snowj, joint, (0.82, 0.84, 0.90))
    dust = g.mul(g.smooth(g.noise(11, 11, 5, seed=44), 0.68, 0.82), g.one_minus(dome))
    col = g.mix(g.mul(dust, 0.22), col, (0.82, 0.84, 0.90))
    col = g.mix(stone, joint, col)
    hdome = g.add(0.22, g.mul(r6, 0.30))
    jointh = g.add(g.add(0.04, g.mul(grain, 0.08)), g.add(g.mul(g.one_minus(gravel), 0.06), g.mul(snowj, 0.22)))
    top = g.add(g.add(g.mul(dome, hdome), g.mul(g.add(lump, facet), dome)), g.mul(g.add(g.mul(pit, -0.25), g.mul(chip, -0.30)), dome))
    stoneh = g.mul(g.add(g.add(0.40, tilt), top), g.sub(1.0, g.mul(sunken, 0.5)))
    h = g.add(g.mul(stone, stoneh), g.mul(g.one_minus(stone), jointh))
    rough = g.lerp(stone, g.add(0.9, g.mul(gravel, 0.1)),
                   g.add(g.add(0.5, g.mul(chip, 0.15)), g.add(g.mul(wear, 0.3), g.mul(wet, -0.25))))
    return col, rough, h, 0.08


def _tx_thatch(g):
    # rye straw laid in overlapping courses (5 per 2 m), stalk ends pointing down the slope; weathered grey-brown,
    # darker and mossy where the straw is old, bright fresh patches where it was mended
    rv = g.mul(g.v, 5.0)
    cv = g.fr(rv)
    iv = g.fl(rv)
    wob = g.mul(g.sub(g.noise(9, 3, 3, seed=57), 0.5), 0.35)
    cvw = g.fr(g.add(rv, wob))
    stalk = g.noise(320, 4, 4, 0.7, dist=1.2, seed=45, wshift=g.mul(iv, 3.1))
    fine = g.noise(600, 12, 2, 0.6, seed=58)
    clump = g.noise(24, 5, 3, seed=46)
    col = g.ramp(stalk, [(0.25, (0.16, 0.13, 0.09)), (0.5, (0.34, 0.29, 0.20)), (0.7, (0.48, 0.41, 0.28)), (0.85, (0.60, 0.52, 0.36))])
    col = g.mix(g.mul(g.smooth(fine, 0.55, 0.75), 0.4), col, (0.62, 0.55, 0.40))
    grey = g.smooth(g.noise(4, 4, 4, seed=47), 0.35, 0.7)
    col = g.mix(g.mul(grey, 0.5), col, (0.36, 0.34, 0.31))
    fresh = g.smooth(g.noise(3, 3, 3, seed=59), 0.66, 0.72)
    col = g.mix(g.mul(fresh, 0.5), col, (0.62, 0.52, 0.30))
    moss = g.mul(g.smooth(g.noise(5, 5, 5, seed=48), 0.55, 0.7), g.smooth(clump, 0.4, 0.6))
    col = g.mix(g.mul(moss, 0.75), col, (0.17, 0.20, 0.10))
    shade = g.one_minus(g.smooth(cvw, 0.0, 0.18))
    col = g.mix(g.mul(shade, 0.35), col, (0.08, 0.07, 0.05))
    h = g.add(g.mul(g.sub(1.0, g.mul(cvw, 0.35)), 0.5), g.add(g.mul(stalk, 0.45), g.mul(clump, 0.25)))
    return col, g.add(0.86, g.mul(stalk, 0.1)), h, 0.05


def _tx_log(g):
    # horizontal hewn logs (8 per 2 m) with clay chinking, limewashed and flaking
    rv = g.mul(g.v, 8.0)
    cv = g.fr(rv)
    iv = g.fl(rv)
    y = g.sub(g.mul(cv, 2.0), 1.0)
    bulge = g.m("SQRT", g.mx(g.sub(1.0, g.mul(y, y)), 0.0))
    chink = g.one_minus(g.smooth(bulge, 0.25, 0.45))
    grain = g.noise(3, 60, 5, 0.6, dist=0.5, seed=49, wshift=g.mul(iv, 7.0))
    wood = g.ramp(grain, [(0.3, (0.30, 0.22, 0.14)), (0.7, (0.46, 0.35, 0.23))])
    lime = g.mix(g.noise(40, 40, 3, seed=50), (0.86, 0.87, 0.88), (0.96, 0.96, 0.95))
    flake = g.smooth(g.noise(8, 10, 6, seed=51), 0.62, 0.64)
    col = g.mix(flake, lime, wood)
    col = g.mix(chink, col, (0.62, 0.56, 0.46))
    split = g.mul(g.smooth(g.noise(4, 120, 3, seed=52), 0.74, 0.77), g.one_minus(chink))
    col = g.mix(g.mul(split, 0.8), col, (0.12, 0.10, 0.08))
    h = g.add(g.mul(bulge, 0.8), g.mul(grain, 0.1))
    h = g.sub(h, g.add(g.mul(split, 0.2), g.mul(flake, 0.05)))
    return col, g.add(0.82, g.mul(flake, 0.1)), h, 0.04


def _tx_field(g):
    # ploughed strip field under snow: furrows run along u (22 per 4 m), stubble rows, soil showing on the ridges
    rv = g.mul(g.v, 22.0)
    cv = g.fr(rv)
    ridge = g.m("SINE", g.mul(g.fr(g.add(rv, g.mul(g.noise(2, 1, 2, seed=63), 1.5))), math.pi))
    wind = g.noise(3, 3, 4, seed=53)
    snow_depth = g.add(g.mul(wind, 0.8), g.mul(g.noise(40, 12, 3, seed=62), 0.3))
    bare = g.smooth(g.sub(ridge, snow_depth), 0.05, 0.25)
    soil = g.mix(g.noise(60, 60, 4, seed=54), (0.16, 0.12, 0.09), (0.30, 0.23, 0.16))
    snow = g.mix(g.noise(20, 20, 3, seed=55), (0.80, 0.83, 0.90), (0.95, 0.96, 0.99))
    col = g.mix(bare, snow, soil)
    stub = g.one_minus(g.smooth(g.voronoi(160, 22 * 6, "F1", seed=56), 0.06, 0.12))
    stub = g.mul(stub, g.smooth(ridge, 0.4, 0.7))
    col = g.mix(g.mul(stub, 0.85), col, (0.52, 0.44, 0.26))
    h = g.add(g.mul(ridge, 0.7), g.add(g.mul(stub, 0.25), g.mul(g.one_minus(bare), 0.15)))
    rough = g.lerp(bare, 0.7, 0.92)
    return col, rough, h, 0.05


RECIPES = {"plaster": _tx_plaster, "plaster_damp": lambda g: _tx_plaster(g, damp=True), "brick": _tx_brick,
           "sandstone": _tx_sandstone, "tile": _tx_tile, "oak": _tx_oak, "iron": _tx_iron, "metal": _tx_metal,
           "glass": _tx_glass, "snow": _tx_snow, "cloth": _tx_cloth, "cobbles": _tx_cobbles, "thatch": _tx_thatch,
           "log": _tx_log, "field": _tx_field, "stained": _tx_stained, "patina": _tx_patina, "shingle": _tx_shingle}


def _tex_paths(kind):
    return {p: os.path.join(TEX, "%s_%s.png" % (kind, p)) for p in ("col", "rough", "nrm")}


_baked_this_run = set()


HEIGHT_EXPORT = {"cobbles"}
TEX_DIR = os.path.join(ROOT, "assets", "textures")


def bake_texture(kind):
    """Bake one texture kind to assets/textures/<kind>_{col,rough,nrm}.png (cached). Runs in a scratch scene, so it
    is safe to call in the middle of building an asset."""
    paths = _tex_paths(kind)
    revf = os.path.join(TEX, "%s.rev" % kind)
    rev_ok = TEX_REV.get(kind, 1) == 1 or (os.path.exists(revf) and open(revf).read().strip() == str(TEX_REV[kind]))
    if all(os.path.exists(p) for p in paths.values()) and (not REBAKE or kind in _baked_this_run) and (rev_ok or kind in _baked_this_run):
        return paths
    t0 = time.time()
    res, rep = TEXSPEC[kind]
    win = bpy.context.window
    prev = win.scene
    sc = bpy.data.scenes.new("_bake_" + kind)
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 2
    sc.cycles.use_denoising = False
    sc.render.threads_mode = "AUTO"
    bk = sc.render.bake
    bk.margin = 0
    me = bpy.data.meshes.new("_bakeplane")
    bm = bmesh.new()
    h = rep / 2
    vs = [bm.verts.new(c) for c in ((-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0))]
    f = bm.faces.new(vs)
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = uv
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("_bakeplane", me)
    sc.collection.objects.link(ob)
    mat = bpy.data.materials.new("_bake_" + kind)
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    g = _G(nt)
    col, rough, hgt, dist = RECIPES[kind](g)
    nt.links.new(col, bsdf.inputs["Base Color"])
    nt.links.new(rough, bsdf.inputs["Roughness"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = dist
    bump.inputs["Strength"].default_value = 1.0
    nt.links.new(hgt, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    me.materials.append(mat)
    tnode = nt.nodes.new("ShaderNodeTexImage")
    nt.nodes.active = tnode
    win.scene = sc
    vl = sc.view_layers[0]
    vl.objects.active = ob
    ob.select_set(True, view_layer=vl)
    passes = [("col", "DIFFUSE"), ("rough", "ROUGHNESS"), ("nrm", "NORMAL")]
    if kind in HEIGHT_EXPORT:
        passes.append(("hgt", "EMIT"))
    for p, btype in passes:
        if btype == "EMIT":
            # route the height field through emission so it bakes as a plain greyscale image
            nt.links.new(hgt, bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = 1.0
            nt.links.new(g.add(0.0, 0.0), bsdf.inputs["Base Color"])
        img = bpy.data.images.new("%s_%s" % (kind, p), res, res, alpha=False)
        img.colorspace_settings.name = "sRGB" if p == "col" else "Non-Color"
        tnode.image = img
        kw = dict(type=btype, margin=0, use_clear=True)
        if btype == "DIFFUSE":
            kw["pass_filter"] = {"COLOR"}
        if btype == "NORMAL":
            kw["normal_space"] = "TANGENT"
        with bpy.context.temp_override(scene=sc, view_layer=vl, active_object=ob, object=ob,
                                       selected_objects=[ob], selected_editable_objects=[ob]):
            bpy.ops.object.bake(**kw)
        img.filepath_raw = paths.get(p, os.path.join(TEX_DIR, "%s_%s.png" % (kind, p)))
        img.file_format = "PNG"
        img.save()
        if btype == "EMIT":
            gdir = os.path.join(ROOT, "assets", "ground")
            os.makedirs(gdir, exist_ok=True)
            img.filepath_raw = os.path.join(gdir, "%s_height.png" % kind)
            img.save()
        bpy.data.images.remove(img)
    win.scene = prev
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)
    bpy.data.materials.remove(mat)
    bpy.data.scenes.remove(sc)
    _baked_this_run.add(kind)
    with open(revf, "w") as fh:
        fh.write(str(TEX_REV.get(kind, 1)))
    print("[tex] baked %s %dpx in %.1fs" % (kind, res, time.time() - t0))
    return paths


def _img(path, colour):
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return im


TEX_HALF = False     # set per asset by the build loop: the outer-town sets embed half-resolution copies of the bakes


def _half(path):
    """A cached half-resolution copy of a baked texture (assets/textures/<kind>_<pass>_half.png)."""
    hp = path[:-4] + "_half.png"
    if not os.path.exists(hp) or os.path.getmtime(hp) < os.path.getmtime(path):
        im = bpy.data.images.load(path)
        im.scale(max(64, im.size[0] // 2), max(64, im.size[1] // 2))
        im.filepath_raw = hp
        im.file_format = "PNG"
        im.save()
        bpy.data.images.remove(im)
    return hp


def _tex_material(key, kind, tint):
    paths = bake_texture(kind)
    if TEX_HALF:
        paths = {p: _half(v) for p, v in paths.items()}
    m = bpy.data.materials.new(key)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    ic = nt.nodes.new("ShaderNodeTexImage")
    ic.image = _img(paths["col"], True)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 1.0
    a = [i for i in mix.inputs if i.name == "A" and i.type == "RGBA"][0]
    b = [i for i in mix.inputs if i.name == "B" and i.type == "RGBA"][0]
    nt.links.new(ic.outputs["Color"], a)
    b.default_value = (*[min(1.0, c) for c in tint], 1.0)
    nt.links.new([o for o in mix.outputs if o.type == "RGBA"][0], bsdf.inputs["Base Color"])
    ir = nt.nodes.new("ShaderNodeTexImage")
    ir.image = _img(paths["rough"], False)
    nt.links.new(ir.outputs["Color"], bsdf.inputs["Roughness"])
    inr = nt.nodes.new("ShaderNodeTexImage")
    inr.image = _img(paths["nrm"], False)
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(inr.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Metallic"].default_value = METALLIC.get(kind, 0.0)
    _tex_rep[key] = TEXSPEC[kind][1]
    return m


def M(key, rough=0.85, emit=None, emit_strength=0.0):
    """Material by palette key. Architectural keys get baked PBR textures; the rest stay flat colours."""
    if key in _mats:
        return _mats[key]
    kind = None
    if key.endswith("_damp") and key[:-5] in PAL:
        kind, tint = "plaster_damp", _desat(PAL[key[:-5]])
    elif key in TEX_OF and not emit:
        kind = TEX_OF[key]
        tint = TINT.get(key) or _desat(PAL[key])
    if kind:
        m = _tex_material(key, kind, tint)
        if key == "glass_warm":           # lit windows: a warm glow for the night scene
            bsdf = m.node_tree.nodes["Principled BSDF"]
            bsdf.inputs["Emission Color"].default_value = (1.0, 0.64, 0.30, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 1.5
        if kind == "stained":             # candles inside: the glass colours glow faintly at night
            bsdf = m.node_tree.nodes["Principled BSDF"]
            ic = [n for n in m.node_tree.nodes if n.type == "TEX_IMAGE"][0]
            m.node_tree.links.new(ic.outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = 1.2 if key == "glass_stained" else 0.6
    else:
        m = bpy.data.materials.new(key)
        bsdf = m.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (*PAL[key], 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        if key == "gold":
            bsdf.inputs["Metallic"].default_value = 0.8
        if emit:
            bsdf.inputs["Emission Color"].default_value = (*emit, 1.0)
            bsdf.inputs["Emission Strength"].default_value = emit_strength
    _mats[key] = m
    return m


def is_wood(mat):
    return mat is not None and TEX_OF.get(mat.name) == "oak"


# ------------------------------------------------------------------ UVs
def _tag(o, mode=0.0, c=(0.0, 0.0), grain=0.0, mat=None, offset=None):
    """Per-face UV hints read by auto_uv: mode 1 = map around a vertical axis at c; grain 1 = rotate 90 degrees
    (wood running horizontally); a random per-part offset, except damp plinths which stay anchored at z=0."""
    me = o.data
    n = len(me.polygons)
    if n == 0:
        return o
    anchor = mat is not None and mat.name.endswith("_damp")
    ou, ov = RNG_UV.random(), (0.0 if anchor else RNG_UV.random())
    if offset is not None:
        ou, ov = offset
    a = me.attributes.get("uvp") or me.attributes.new("uvp", "FLOAT_VECTOR", "FACE")
    a.data.foreach_set("vector", [mode, c[0], c[1]] * n)
    b = me.attributes.get("uvo") or me.attributes.new("uvo", "FLOAT_VECTOR", "FACE")
    b.data.foreach_set("vector", [ou, ov, grain] * n)
    return o


def auto_uv(o):
    """Project UVs per face at a fixed texel density (metres per repeat from the material)."""
    me = o.data
    if not me.polygons:
        return
    for uvl_ in list(me.uv_layers)[1:]:
        me.uv_layers.remove(uvl_)
    uvl = me.uv_layers[0] if me.uv_layers else me.uv_layers.new(name="UVMap")
    n = len(me.polygons)
    P = [0.0] * (3 * n)
    O = [0.0] * (3 * n)
    if "uvp" in me.attributes:
        me.attributes["uvp"].data.foreach_get("vector", P)
    if "uvo" in me.attributes:
        me.attributes["uvo"].data.foreach_get("vector", O)
    reps = [(_tex_rep.get(m.name, 2.0) if m else 2.0) for m in me.materials] or [2.0]
    co = [v.co.copy() for v in me.vertices]
    lv = [0] * len(me.loops)
    me.loops.foreach_get("vertex_index", lv)
    out = [0.0] * (2 * len(me.loops))
    Z = Vector((0, 0, 1))
    Y = Vector((0, 1, 0))
    for p in me.polygons:
        i = p.index
        nrm = p.normal
        mode = P[3 * i]
        ou, ov, grain = O[3 * i], O[3 * i + 1], O[3 * i + 2]
        rep = reps[min(p.material_index, len(reps) - 1)]
        li0 = p.loop_start
        if mode > 0.5 and abs(nrm.z) < 0.9:
            cx, cy = P[3 * i + 1], P[3 * i + 2]
            fc = p.center
            a0 = math.atan2(fc.y - cy, fc.x - cx)
            r = max(0.05, math.hypot(fc.x - cx, fc.y - cy))
            for li in range(li0, li0 + p.loop_total):
                v = co[lv[li]]
                a = math.atan2(v.y - cy, v.x - cx)
                while a - a0 > math.pi:
                    a -= math.tau
                while a - a0 < -math.pi:
                    a += math.tau
                uu, vv = a * r, v.z
                if grain > 0.5:
                    uu, vv = -vv, uu
                out[2 * li] = uu / rep + ou
                out[2 * li + 1] = vv / rep + ov
            continue
        if abs(nrm.z) > 0.95:
            s = (Y - nrm * nrm.dot(Y)).normalized()
        else:
            s = (Z - nrm * nrm.z).normalized()
        t = s.cross(nrm)
        for li in range(li0, li0 + p.loop_total):
            v = co[lv[li]]
            uu, vv = v.dot(t), v.dot(s)
            if grain > 0.5:
                uu, vv = -vv, uu
            out[2 * li] = uu / rep + ou
            out[2 * li + 1] = vv / rep + ov
    uvl.data.foreach_set("uv", out)


# ------------------------------------------------------------------ finishing: the "Fable" pass (halved for masonry)
def finish(o, bevel=0.06, seg=2, subsurf=0, wonk=0.0, smooth=40.0, keep_base=True):
    """Wonk the corners, bevel the edges, optionally subdivide, then smooth by angle."""
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    wonk *= WONK
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
def _finish_prim(o, name, mat, mode=0.0, c=(0.0, 0.0), grain=0.0):
    o.name = name
    if mat:
        o.data.materials.append(mat)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    _tag(o, mode, c, grain, mat)
    return o


def box(name, size, loc, mat=None, rot=(0, 0, 0), **fin):
    """loc = base centre; the box sits on loc.z."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0], loc[1], loc[2] + size[2] / 2), rotation=rot)
    o = bpy.context.object
    o.scale = size
    grain = 1.0 if is_wood(mat) and size[2] < max(size[0], size[1]) else 0.0
    o = _finish_prim(o, name, mat, grain=grain)
    return finish(o, **fin) if fin else o


def cbox(name, size, center, mat=None, rot=(0, 0, 0), **fin):
    bpy.ops.mesh.primitive_cube_add(size=1, location=center, rotation=rot)
    o = bpy.context.object
    o.scale = size
    grain = 1.0 if is_wood(mat) and size[2] < max(size[0], size[1]) else 0.0
    o = _finish_prim(o, name, mat, grain=grain)
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
    upright = tuple(rot) == (0, 0, 0)
    o = _finish_prim(bpy.context.object, name, mat, mode=1.0 if upright else 0.0, c=(loc[0], loc[1]),
                     grain=0.0 if upright or not is_wood(mat) else 1.0)
    return finish(o, **fin) if fin else o


def sphere(name, r, center, mat=None, seg=20, rings=12, zscale=1.0, **fin):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=r, location=center)
    o = bpy.context.object
    o.scale.z = zscale
    o = _finish_prim(o, name, mat, mode=1.0, c=(center[0], center[1]))
    fin.setdefault("bevel", 0)
    return finish(o, **fin)


def torus(name, R, r, center, mat=None, rot=(0, 0, 0), seg=24, mseg=10, **fin):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, major_segments=seg, minor_segments=mseg, location=center, rotation=rot)
    o = _finish_prim(bpy.context.object, name, mat)
    fin.setdefault("bevel", 0)
    return finish(o, **fin)


def blob(name, size, loc, mat=None, **fin):
    """Rounded lump: cube with subsurf. Heads, boots, hair, mascarons."""
    fin.setdefault("subsurf", 2)
    fin.setdefault("bevel", 0)
    return box(name, size, loc, mat, **fin)


def _mesh_obj(name, bm, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    if mat:
        o.data.materials.append(mat)
    _tag(o, mat=mat)
    return o


def wedge(name, size, loc, mat=None, **fin):
    """Triangular prism, ridge along X at the top, base centre at loc (a lean-to roof, a step, a gable end)."""
    L, W, H = size
    bm = bmesh.new()
    a = [bm.verts.new((loc[0] - L / 2, loc[1] - W / 2, loc[2])), bm.verts.new((loc[0] - L / 2, loc[1] + W / 2, loc[2])),
         bm.verts.new((loc[0] - L / 2, loc[1], loc[2] + H))]
    b = [bm.verts.new((loc[0] + L / 2, v.co.y, v.co.z)) for v in a]
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))
    for i in range(3):
        j = (i + 1) % 3
        bm.faces.new((a[i], b[i], b[j], a[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _mesh_obj(name, bm, mat)
    fin.setdefault("bevel", 0)
    return finish(o, **fin)


def pyramid(name, size, loc, mat=None, apex=0.0, **fin):
    """Four-sided pyramid (spire, pinnacle, hipped cap). size = (x, y, h); apex = flat top half-width."""
    X, Y, H = size
    bm = bmesh.new()
    base = [bm.verts.new((loc[0] + sx * X / 2, loc[1] + sy * Y / 2, loc[2])) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    if apex > 0:
        top = [bm.verts.new((loc[0] + sx * apex, loc[1] + sy * apex, loc[2] + H)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        bm.faces.new(top)
        for i in range(4):
            bm.faces.new((base[i], base[(i + 1) % 4], top[(i + 1) % 4], top[i]))
    else:
        t = bm.verts.new((loc[0], loc[1], loc[2] + H))
        for i in range(4):
            bm.faces.new((base[i], base[(i + 1) % 4], t))
    bm.faces.new(list(reversed(base)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _mesh_obj(name, bm, mat)
    fin.setdefault("bevel", 0)
    return finish(o, **fin)


def roof(name, L, W, H, loc, mat, sag=0.25, flare=0.30, cuts=6, top_w=0.0, along_x=True, courses=0, ridge=False, **fin):
    """Sagging, flaring roof solid. Ridge along X (or Y). loc = base centre at eaves level.
    flare: how far the mid-slope sits below the straight chord (0 = straight, 0.3 = pagoda-ish sweep).
    top_w: width of a flat ridge (for mansard lower slopes).
    courses: number of raised tile-course lines laid across each slope; ridge: half-round ridge tiles."""
    def P(u, py, pz):
        if along_x:
            return Vector((loc[0] + (L / 2) * u, loc[1] + py, loc[2] + pz))
        return Vector((loc[0] + py, loc[1] + (L / 2) * u, loc[2] + pz))

    bm = bmesh.new()
    slices, profs = [], []
    for i in range(cuts + 1):
        t = -1 + 2 * i / cuts
        hr = H - sag * (1 - t * t)
        half = W / 2
        prof = [(-half, 0.0)]
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
        profs.append((t, prof))
        slices.append([bm.verts.new(P(t, py, pz)) for (py, pz) in prof])
    n = len(slices[0])
    for i in range(cuts):
        a, b = slices[i], slices[i + 1]
        for j in range(n - 1):
            bm.faces.new((a[j], a[j + 1], b[j + 1], b[j]))
        bm.faces.new((a[0], b[0], b[n - 1], a[n - 1]))       # underside
    bm.faces.new(list(reversed(slices[0])))
    bm.faces.new(slices[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _mesh_obj(name, bm, mat)
    fin.setdefault("bevel", 0.05)
    fin.setdefault("smooth", 35)
    o = finish(o, **fin)
    if not courses and not ridge:
        return o
    # raised course lines and ridge tiles as a second mesh on the finished surface
    bm = bmesh.new()

    def along(prof, idx, f):
        """Point and outward normal (in profile space) at fraction f from eave (idx[0]) to ridge (idx[-1])."""
        segs = [(prof[idx[k]], prof[idx[k + 1]]) for k in range(len(idx) - 1)]
        lens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs]
        tot = sum(lens)
        d = f * tot
        for (a, b), ln in zip(segs, lens):
            if d <= ln or (a, b) == segs[-1]:
                k = min(1.0, d / ln) if ln else 0
                py, pz = a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
                sy, sz = (b[0] - a[0]) / ln, (b[1] - a[1]) / ln
                ny, nz = -sz, sy
                if nz < 0:
                    ny, nz = -ny, -nz
                return py, pz, sy, sz, ny, nz
            d -= ln

    sides = [[0, 1, 2], [n - 1, n - 2, n - 3]]
    for idx in sides:
        for c in range(courses):
            f = 0.08 + 0.84 * (c + 0.5) / courses
            rows = []
            for (t, prof) in profs:
                py, pz, sy, sz, ny, nz = along(prof, idx, f)
                r0 = P(t, py + ny * 0.005, pz + nz * 0.005)
                r1 = P(t, py + ny * 0.055 - sy * 0.01, pz + nz * 0.055 - sz * 0.01)
                r2 = P(t, py + sy * 0.30 + ny * 0.012, pz + sz * 0.30 + nz * 0.012)
                rows.append([bm.verts.new(r0), bm.verts.new(r1), bm.verts.new(r2)])
            for a, b in zip(rows, rows[1:]):
                bm.faces.new((a[0], b[0], b[1], a[1]))
                bm.faces.new((a[1], b[1], b[2], a[2]))
    if ridge and top_w == 0:
        rings = []
        for (t, prof) in profs:
            py, pz = prof[2]
            ring = []
            for k in range(7):
                ang = math.pi * k / 6
                ring.append(bm.verts.new(P(t * 1.01, py + 0.13 * math.cos(ang), pz - 0.04 + 0.11 * math.sin(ang))))
            rings.append(ring)
        for a, b in zip(rings, rings[1:]):
            for k in range(6):
                bm.faces.new((a[k], a[k + 1], b[k + 1], b[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    c = _mesh_obj(name + "_courses", bm, mat)
    for p in c.data.polygons:
        p.use_smooth = False
    return join([o, c], name)


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


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


TRI_LOG = {}


def export(name, visual, col=None):
    if col is not None:
        col.name = name + "-colonly"
        col.parent = visual
        col.display_type = "WIRE"
    visual.name = name
    auto_uv(visual)
    counts = {}
    for kind, loc, rz in _MARKS:
        n = counts.get(kind, 0)
        counts[kind] = n + 1
        e = bpy.data.objects.new(kind[1:] if kind.startswith("!") else "%s_%d" % (kind, n), None)
        bpy.context.collection.objects.link(e)
        e.empty_display_size = 0.3
        e.location = loc
        e.rotation_euler = (0.0, 0.0, rz)
        e.parent = visual
    for (nm, o) in _EXTRA:
        auto_uv(o)
        o.parent = visual
        o.name = nm
    for i, (kind, o) in enumerate(_CLIMB):
        o.name = "climb_%s_%d-colonly" % (kind, i)
        o.parent = visual
        o.display_type = "WIRE"
    path = os.path.join(OUT, name + ".glb")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
                              export_image_format="JPEG", export_jpeg_quality=JPEG_Q, export_image_quality=JPEG_Q)
    TRI_LOG[name] = tris(visual)
    print("[assets] wrote", os.path.relpath(path, ROOT), "tris", TRI_LOG[name], "MB %.1f" % (os.path.getsize(path) / 1e6))


# ------------------------------------------------------------------ facades with real openings (no booleans)
REV = 0.15          # window reveal: glass sits this far behind the wall face
_FACES = {           # face -> (A axis along the wall, outward normal N); A x Z = N
    "-Y": (Vector((1, 0, 0)), Vector((0, -1, 0))),
    "+Y": (Vector((-1, 0, 0)), Vector((0, 1, 0))),
    "-X": (Vector((0, -1, 0)), Vector((-1, 0, 0))),
    "+X": (Vector((0, 1, 0)), Vector((1, 0, 0))),
}


def _wp(face, plane, a, z, out=0.0):
    """World point on a wall: `a` along the wall, `z` up, `out` metres outward from the wall plane."""
    A, N = _FACES[face]
    axis = Vector((abs(N.x), abs(N.y), 0))
    return A * a + Vector((0, 0, z)) + axis * plane + N * out


def rise_of(shape, w):
    return {"rect": 0.0, "round": w / 2, "pointed": w * 0.866, "seg": w * 0.18}[shape]


def outline(ac, zb, w, h, shape="rect", seg=8):
    """Opening outline, counter-clockwise in (a, z). h is the full height including the arch."""
    xl, xr, zt = ac - w / 2, ac + w / 2, zb + h
    zs = zt - rise_of(shape, w)
    pts = [(xl, zb), (xr, zb), (xr, zs)]
    if shape == "round":
        for k in range(1, seg):
            t = math.pi * k / seg
            pts.append((ac + w / 2 * math.cos(t), zs + w / 2 * math.sin(t)))
    elif shape == "pointed":
        n = max(3, seg // 2)
        for k in range(1, n + 1):
            t = math.radians(60) * k / n
            pts.append((xl + w * math.cos(t), zs + w * math.sin(t)))
        for k in range(1, n):
            t = math.radians(120) + math.radians(60) * k / n
            pts.append((xr + w * math.cos(t), zs + w * math.sin(t)))
    elif shape == "seg":
        r = (w * w / 4 + (zt - zs) ** 2) / (2 * (zt - zs))
        cz = zt - r
        a0 = math.asin((w / 2) / r)
        for k in range(1, seg):
            t = math.pi / 2 - a0 + 2 * a0 * k / seg
            pts.append((ac + r * math.cos(t), cz + r * math.sin(t)))
    pts.append((xl, zs))
    return pts


def facade(name, mat, face, plane, a0, a1, z0, z1, openings, depth=REV, back=True):
    """A wall face from a0..a1, z0..z1 on `plane`, with openings punched as an inset ring of faces.
    openings: (a_centre, z_bottom, width, full_height, shape). Each opening gets a reveal `depth` deep and
    (back=True) a back face, so it reads as a recess with or without a wall behind. The outer rim is folded
    back by `depth` too: put the building mass `depth` behind the plane."""
    xs, zs = {round(a0, 4), round(a1, 4)}, {round(z0, 4), round(z1, 4)}
    ops = []
    for (ac, zb, w, h, shape) in openings:
        xl, xr, zt = ac - w / 2, ac + w / 2, zb + h
        zsp = zt - rise_of(shape, w)
        xs |= {round(xl, 4), round(xr, 4)}
        zs |= {round(zb, 4), round(zt, 4)}
        if shape != "rect":
            xs.add(round(ac, 4))
            zs.add(round(zsp, 4))
        ops.append((ac, zb, w, h, shape, xl, xr, zt, zsp))
    xs, zs = sorted(xs), sorted(zs)
    bm = bmesh.new()
    cache = {}

    def F(vs):
        try:
            bm.faces.new(vs)
        except ValueError:
            pass          # shared edge with the rim (door sills at z0): keep one copy

    def V(a, z, d=0.0):
        k = (round(a, 4), round(z, 4), round(d, 4))
        if k not in cache:
            cache[k] = bm.verts.new(_wp(face, plane, a, z, -d))
        return cache[k]

    def on_x(z, a_from, a_to):
        """Grid points strictly between a_from and a_to on a horizontal line (either direction)."""
        lo, hi = min(a_from, a_to), max(a_from, a_to)
        mids = [x for x in xs if lo + 1e-4 < x < hi - 1e-4]
        return mids if a_to > a_from else list(reversed(mids))

    def on_z(a, z_from, z_to):
        lo, hi = min(z_from, z_to), max(z_from, z_to)
        mids = [z for z in zs if lo + 1e-4 < z < hi - 1e-4]
        return mids if z_to > z_from else list(reversed(mids))

    def refine(pts):
        """Insert grid points along axis-aligned edges of a closed outline so faces share every vertex."""
        out = []
        for i, p in enumerate(pts):
            q = pts[(i + 1) % len(pts)]
            out.append(p)
            if abs(p[1] - q[1]) < 1e-5:
                out += [(x, p[1]) for x in on_x(p[1], p[0], q[0])]
            elif abs(p[0] - q[0]) < 1e-5:
                out += [(p[0], z) for z in on_z(p[0], p[1], q[1])]
        return out

    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            am, zm = (xs[i] + xs[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2
            if any(o[5] < am < o[6] and o[1] < zm < o[7] for o in ops):
                continue
            F([V(xs[i], zs[j]), V(xs[i + 1], zs[j]), V(xs[i + 1], zs[j + 1]), V(xs[i], zs[j + 1])])
    for (ac, zb, w, h, shape, xl, xr, zt, zsp) in ops:
        ol = outline(ac, zb, w, h, shape)
        if shape != "rect":
            # spandrels between the arch and the opening's bounding rectangle
            arc = ol[2:]                                   # (xr, zs) .. apex .. (xl, zs)
            apex_i = min(range(len(arc)), key=lambda k: abs(arc[k][0] - ac) + abs(arc[k][1] - zt))
            right, left = arc[:apex_i + 1], arc[apex_i:]
            rs = [(xr, zsp)] + [(xr, z) for z in on_z(xr, zsp, zt)] + [(xr, zt)] + [(x, zt) for x in on_x(zt, xr, ac)] + list(reversed(right))[:-1]
            ls = list(reversed(left)) + [(x, zt) for x in on_x(zt, ac, xl)] + [(xl, zt)] + [(xl, z) for z in on_z(xl, zt, zsp)]
            for poly in (ls, rs):
                vs = []
                for (pa, pz) in poly:
                    v = V(pa, pz)
                    if v not in vs:
                        vs.append(v)
                if len(vs) >= 3:
                    F(vs)
        ring = refine(ol)
        for k in range(len(ring)):
            p, q = ring[k], ring[(k + 1) % len(ring)]
            F((V(*p), V(*q), V(q[0], q[1], depth), V(p[0], p[1], depth)))
        if back:
            F([V(a, z, depth) for (a, z) in ring])
    rim = refine([(a0, z0), (a0, z1), (a1, z1), (a1, z0)])
    for k in range(len(rim)):
        p, q = rim[k], rim[(k + 1) % len(rim)]
        F((V(*p), V(*q), V(q[0], q[1], depth), V(p[0], p[1], depth)))
    o = _mesh_obj(name, bm, mat)
    for p in o.data.polygons:
        p.use_smooth = False
    return o


def slab(name, pts, face, plane, d0, d1, mat, smooth=False):
    """Extrude a CCW outline (a, z) between d0 and d1 metres outward of a wall plane (glass, leaves, voussoirs)."""
    bm = bmesh.new()
    f = [bm.verts.new(_wp(face, plane, a, z, d1)) for (a, z) in pts]
    b = [bm.verts.new(_wp(face, plane, a, z, d0)) for (a, z) in pts]
    bm.faces.new(f)
    bm.faces.new(list(reversed(b)))
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((f[i], b[i], b[j], f[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _mesh_obj(name, bm, mat)
    for p in o.data.polygons:
        p.use_smooth = smooth
    return o


def fbox(name, face, plane, a, out, zb, sa, sd, sz, mat, **fin):
    """Box on a wall: centred at `a` along it, its centre `out` metres outward, base at zb; sa along the wall,
    sd outward, sz up."""
    A, N = _FACES[face]
    c = _wp(face, plane, a, 0.0, out)
    size = (sa, sd, sz) if abs(A.x) > 0.5 else (sd, sa, sz)
    return box(name, size, (c.x, c.y, zb), mat, **fin)


def voussoirs(parts, face, plane, ac, zs, w, t, mat, shape="round", n=9, proud=0.08, key=0.12):
    """Stone arch ring over an opening of width w springing at zs: n wedge blocks and a taller keystone."""
    for k in range(n):
        gap = 0.012
        t0, t1 = math.pi * k / n + gap, math.pi * (k + 1) / n - gap
        if shape == "pointed":
            # map the half-circle parameter onto the two arcs of an equilateral pointed arch
            def P(tt, r_off):
                if tt <= math.pi / 2:
                    ang = math.radians(60) * (tt / (math.pi / 2))
                    return (ac - w / 2 + (w + r_off) * math.cos(ang), zs + (w + r_off) * math.sin(ang))
                ang = math.radians(120) + math.radians(60) * ((tt - math.pi / 2) / (math.pi / 2))
                return (ac + w / 2 + (w + r_off) * math.cos(ang), zs + (w + r_off) * math.sin(ang))
        else:
            def P(tt, r_off):
                return (ac + (w / 2 + r_off) * math.cos(tt), zs + (w / 2 + r_off) * math.sin(tt))
        ro = t + (key if k == n // 2 else 0.0)
        pts = [P(t0, 0.0), P(t0, ro), P(t1, ro), P(t1, 0.0)]
        parts.append(slab("vous", pts, face, plane, 0.0, proud + (0.03 if k == n // 2 else 0.0), mat))


def win_unit(parts, face, plane, a, zb, w, h, shape="rect", warm=False, shutters=False, surround="stone_pale",
             sill=True, head="lintel", cross=True, bars=False, snow=True, mark=False, shutter_col="shutter",
             shutter_open=(180, 180), glass=None, drip=True, louvre=False, tracery=False):
    """Glazed window set into a facade() opening (a, zb, w, h, shape) with its REV-deep reveal: glass and a
    timber frame at the back of the reveal, a stone sill and lintel (or an arch of voussoirs), a raised
    surround, optional open shutters and iron bars."""
    fr = M("wood_dark")
    ol = outline(a, zb, w, h, shape)
    zs = zb + h - rise_of(shape, w)
    if louvre:                                    # belfry opening: dark void behind slanted oak boards
        parts.append(slab("void", ol, face, plane, -REV + 0.005, -REV + 0.02, M("void")))
        zs_ = zb + h - rise_of(shape, w)
        for k in range(int((zs_ - zb) / 0.3)):
            parts.append(fbox("louvre", face, plane, a, -REV + 0.08, zb + 0.1 + k * 0.3, w - 0.04, 0.03, 0.2, M("wood_dark")))
    else:
        parts.append(slab("glass", ol, face, plane, -REV + 0.005, -REV + 0.025, M(glass or ("glass_warm" if warm else "glass"))))
    if tracery and shape == "pointed":            # two lights under an oculus, in stone
        zs_ = zb + h - rise_of(shape, w)
        rot = (math.pi / 2, 0, 0) if face in ("-Y", "+Y") else (0, math.pi / 2, 0)
        c = _wp(face, plane, a, zs_ + w * 0.32, -REV + 0.07)
        parts.append(torus("trac_ring", w * 0.24, 0.045, tuple(c), M("stone_pale"), rot=rot, seg=12, mseg=4))
        parts.append(fbox("trac_mull", face, plane, a, -REV + 0.07, zb, 0.1, 0.1, zs_ - zb + w * 0.08, M("stone_pale")))
        cross = False
    if mark:
        mark_window(face, plane, a, zb)
        if zb > 3.0 and sill:
            c = _wp(face, plane, a, zb - 0.06, 0.1)
            A, N = _FACES[face]
            climb("ledge", (w + 0.3, 0.3, 0.12) if abs(A.x) > 0.5 else (0.3, w + 0.3, 0.12), (c.x, c.y, zb - 0.06))
    t = 0.07
    fz = zs - zb
    parts.append(fbox("frame", face, plane, a - w / 2 + t / 2, -REV + 0.06, zb, t, 0.07, fz, fr))
    parts.append(fbox("frame", face, plane, a + w / 2 - t / 2, -REV + 0.06, zb, t, 0.07, fz, fr))
    parts.append(fbox("frame", face, plane, a, -REV + 0.06, zb, w, 0.07, t, fr))
    parts.append(fbox("frame", face, plane, a, -REV + 0.06, zs - t, w, 0.07, t, fr))
    if cross:
        parts.append(fbox("mull", face, plane, a, -REV + 0.065, zb, 0.07, 0.06, fz, fr))
        if shape == "rect":
            parts.append(fbox("trans", face, plane, a, -REV + 0.065, zb + fz * 0.66, w, 0.06, 0.07, fr))
    if bars:
        for k in range(3):
            parts.append(fbox("bar", face, plane, a - w / 3 + w / 3 * k, -0.04, zb, 0.03, 0.03, fz, M("iron")))
        parts.append(fbox("bar", face, plane, a, -0.04, zb + fz * 0.5, w, 0.03, 0.03, M("iron")))
    if sill:
        parts.append(fbox("sill", face, plane, a, (0.12 - REV) / 2, zb - 0.12, w + 0.3, 0.12 + REV, 0.12, M("stone")))
        if drip:                                  # throated drip under the sill nose
            parts.append(fbox("drip", face, plane, a, 0.1, zb - 0.16, w + 0.24, 0.04, 0.04, M("stone_dark")))
        if snow:
            parts.append(fbox("sill_snow", face, plane, a, (0.1 - REV) / 2 + 0.01, zb, w + 0.2, 0.08 + REV, 0.03, M("snow")))
    if surround:
        sm = M(surround)
        bw = 0.13
        parts.append(fbox("sur", face, plane, a - w / 2 - bw / 2, 0.025, zb - 0.02, bw, 0.05, zs - zb + 0.02, sm))
        parts.append(fbox("sur", face, plane, a + w / 2 + bw / 2, 0.025, zb - 0.02, bw, 0.05, zs - zb + 0.02, sm))
    if shape == "rect":
        if head == "lintel":
            parts.append(fbox("lintel", face, plane, a, 0.04, zs, w + 0.42, 0.08, 0.24, M("stone")))
            parts.append(fbox("key", face, plane, a, 0.07, zs - 0.02, 0.22, 0.1, 0.3, M("stone_pale")))
            parts.append(fbox("hood", face, plane, a, 0.08, zs + 0.24, w + 0.56, 0.16, 0.08, M("stone"), bevel=0.02, seg=1))
            if snow:
                parts.append(fbox("hood_snow", face, plane, a, 0.08, zs + 0.32, w + 0.5, 0.14, 0.025, M("snow")))
    else:
        voussoirs(parts, face, plane, a, zs, w, 0.16, M("stone"), shape=shape, n=7 if shape == "round" else 8)
    if shutters in ("board", "louvre"):
        shutter_pair(parts, face, plane, a, zb, w, fz, style=shutters, colour=shutter_col, open_deg=shutter_open)
    elif shutters:
        sw = w / 2 + 0.04
        for sx in (-1, 1):
            parts.append(fbox("shutter", face, plane, a + sx * (w / 2 + 0.16 + sw / 2), 0.04, zb, sw, 0.05, fz, M("shutter"), bevel=0.01, seg=1))
            for zz in (zb + 0.2, zb + fz - 0.3):
                parts.append(fbox("hinge", face, plane, a + sx * (w / 2 + 0.16 + sw / 2), 0.07, zz, sw * 0.8, 0.012, 0.04, M("iron")))


def door_unit(parts, face, plane, a, w=2.0, h=3.0, portal=True, fanlight=True, surround="stone"):
    """Panelled double door in a round-arched facade() opening (a, 0, w, h + w/2, "round"): two leaves with
    raised panels and iron straps, a fanlight with radial bars, a stone portal of jambs and voussoirs."""
    wd = M("wood_dark")
    iron = M("iron")
    lw = w / 2 - 0.02
    for sx in (-1, 1):
        lx = a + sx * (w / 4 + 0.005)
        parts.append(fbox("leaf", face, plane, lx, -REV + 0.05, 0.0, lw, 0.07, h, wd))
        for r in range(3):
            pz = 0.25 + r * (h - 0.4) / 3
            ph = (h - 0.4) / 3 - 0.18
            parts.append(fbox("panel", face, plane, lx, -REV + 0.095, pz, lw - 0.24, 0.03, ph, wd, bevel=0.012, seg=1))
        for zz in (0.45, h * 0.5, h - 0.45):
            parts.append(fbox("strap", face, plane, lx - sx * 0.04, -REV + 0.12, zz, lw - 0.1, 0.012, 0.07, iron))
            for k in range(2):
                parts.append(fbox("stud", face, plane, lx - lw / 2 + 0.12 + k * (lw - 0.24), -REV + 0.13, zz + 0.02, 0.035, 0.02, 0.035, iron))
    parts.append(torus("ring", 0.09, 0.015, tuple(_wp(face, plane, a + 0.22, 1.25, -REV + 0.14)), iron,
                       rot=(math.pi / 2, 0, 0) if face in ("-Y", "+Y") else (0, math.pi / 2, 0), seg=12, mseg=6))
    parts.append(fbox("transom", face, plane, a, -REV + 0.07, h, w, 0.1, 0.12, wd))
    if fanlight:
        r = w / 2
        pts = [(a - r, h + 0.12), (a + r, h + 0.12)] + [(a + r * math.cos(math.pi * k / 10), h + 0.12 + r * math.sin(math.pi * k / 10)) for k in range(1, 10)]
        parts.append(slab("fan", pts, face, plane, -REV + 0.005, -REV + 0.02, M("glass_warm")))
        for k in range(1, 6):
            ang = math.pi * k / 6
            c, s = math.cos(ang), math.sin(ang)
            px, pz = -s * 0.015, c * 0.015
            bar = [(a + px, h + 0.12 + pz), (a - px, h + 0.12 - pz), (a - px + c * r, h + 0.12 - pz + s * r), (a + px + c * r, h + 0.12 + pz + s * r)]
            parts.append(slab("fanbar", bar, face, plane, -REV + 0.02, -REV + 0.04, iron))
    if portal:
        st = M(surround)
        for sx in (-1, 1):
            parts.append(fbox("jamb", face, plane, a + sx * (w / 2 + 0.2), 0.08, 0.0, 0.4, 0.16, h, st, bevel=0.03, seg=1))
            parts.append(fbox("jamb_base", face, plane, a + sx * (w / 2 + 0.2), 0.11, 0.0, 0.5, 0.22, 0.45, M("stone_dark"), bevel=0.03, seg=1))
            parts.append(fbox("impost", face, plane, a + sx * (w / 2 + 0.2), 0.12, h - 0.02, 0.52, 0.24, 0.16, st, bevel=0.02, seg=1))
        voussoirs(parts, face, plane, a, h + 0.12, w, 0.4, st, n=9, proud=0.14, key=0.18)
        mascaron(parts, face, plane, a, h + 0.12 + w / 2 + 0.5, s=0.26, mat=st)
        parts.append(fbox("cornice", face, plane, a, 0.18, h + 0.12 + w / 2 + 0.58, w + 1.3, 0.36, 0.14, st, bevel=0.03, seg=1))
        parts.append(fbox("corn_snow", face, plane, a, 0.18, h + 0.12 + w / 2 + 0.72, w + 1.2, 0.32, 0.05, M("snow"), bevel=0.02, seg=1))
    parts.append(fbox("step", face, plane, a, 0.3, 0.0, w + 0.9, 0.6, 0.16, M("stone_dark"), bevel=0.03, seg=1))
    parts.append(fbox("threshold", face, plane, a, -REV / 2, 0.0, w, REV, 0.1, M("stone_dark")))


def shop_sign(parts, x, y_face, z, board=True, emblem="disc", side=1):
    """Wrought-iron bracket sticking out of a -Y wall at (x, z) with a hanging oak sign board."""
    iron = M("iron")
    L = 1.0
    parts.append(box("plate", (0.1, 0.04, 0.36), (x, y_face - 0.02, z - 0.28), iron))
    parts.append(box("arm", (0.035, L, 0.035), (x, y_face - L / 2, z), iron))
    ang = math.atan2(0.45, L * 0.8)
    parts.append(cbox("brace", (0.03, math.hypot(L * 0.8, 0.45), 0.03), (x, y_face - L * 0.4, z - 0.225), iron, rot=(-ang, 0, 0)))
    parts.append(torus("scroll", 0.1, 0.014, (x, y_face - L * 0.55, z - 0.12), iron, rot=(0, math.pi / 2, 0), seg=10, mseg=4))
    parts.append(sphere("finial", 0.035, (x, y_face - L, z + 0.01), iron, seg=8, rings=5))
    if board:
        for dy in (-0.25, 0.25):
            parts.append(box("chain", (0.012, 0.012, 0.14), (x, y_face - L * 0.6 + dy, z - 0.14), iron))
        parts.append(box("board", (0.05, 0.72, 0.52), (x, y_face - L * 0.6, z - 0.66), M("wood"), bevel=0.012, seg=1))
        parts.append(box("board_rim", (0.06, 0.76, 0.05), (x, y_face - L * 0.6, z - 0.16), M("wood_dark"), bevel=0.01, seg=1))
        if emblem == "disc":
            parts.append(cyl("emblem", 0.17, 0.07, (x, y_face - L * 0.6, z - 0.40), M("gold", 0.35), verts=16, rot=(0, math.pi / 2, 0), center=True))
        elif emblem == "key":
            parts.append(box("emblem", (0.07, 0.4, 0.06), (x, y_face - L * 0.6, z - 0.43), M("gold", 0.35)))
            parts.append(torus("emblem_r", 0.08, 0.025, (x, y_face - L * 0.6 - 0.24, z - 0.40), M("gold", 0.35), rot=(0, math.pi / 2, 0), seg=12, mseg=4))
        elif emblem == "pretzel":
            for dy in (-0.07, 0.07):
                parts.append(torus("emblem", 0.1, 0.03, (x, y_face - L * 0.6 + dy, z - 0.42), M("plaster_ochre"), rot=(0, math.pi / 2, 0), seg=12, mseg=5))
        elif emblem == "boot":
            parts.append(box("emblem", (0.07, 0.14, 0.26), (x, y_face - L * 0.6 + 0.05, z - 0.52), M("black")))
            parts.append(box("emblem2", (0.07, 0.3, 0.1), (x, y_face - L * 0.6 - 0.03, z - 0.62), M("black")))


def drainpipe(parts, x, y, z_top, walls, r=0.055):
    """Lead downpipe at (x, y) from a hopper head under the cornice to a shoe at the pavement; `walls` lists
    (z, wall_y) for the brackets that tie it back to each storey's face."""
    lead = M("lead")
    parts.append(cyl("pipe", r, z_top - 0.25, (x, y, 0.25), lead, verts=8))
    climb("pipe", (0.3, 0.3, z_top), (x, y, z_top / 2))
    parts.append(taper_box("hopper", (0.26, 0.24, 0.32), (x, y, z_top - 0.05), lead, top=1.35))
    parts.append(box("gutter_link", (0.1, abs(walls[-1][1] - y) + 0.2, 0.1), (x, (y + walls[-1][1]) / 2, z_top + 0.15), lead))
    parts.append(cyl("shoe", r, 0.3, (x, y - 0.1, 0.16), lead, verts=8, rot=(math.radians(60), 0, 0), center=True))
    for (z, wy) in walls:
        d = abs(wy - y) + 0.04
        parts.append(box("clip", (0.05, d, 0.05), (x, (wy + y) / 2, z), M("iron")))
        parts.append(cyl("collar", r + 0.015, 0.06, (x, y, z - 0.005), lead, verts=8))


def cornice(parts, w, d, z, t=0.28, proud=0.25, mat=None, wonk=0.03, front=None, modillions=True):
    """Moulded cornice around a w x d block at height z: fascia, projecting corona with a cyma on top, and (for
    the -Y front at y=front) a row of modillion blocks under the corona."""
    mat = mat or M("stone")
    parts.append(box("cornice_f", (w + proud * 0.5, d + proud * 0.5, t * 0.35), (0, 0, z), mat, bevel=0.02, seg=1, wonk=wonk * 0.5))
    parts.append(box("cornice_c", (w + proud * 2, d + proud * 2, t * 0.4), (0, 0, z + t * 0.35), mat, bevel=0.04, seg=1, wonk=wonk))
    parts.append(box("cornice_t", (w + proud * 1.5, d + proud * 1.5, t * 0.25), (0, 0, z + t * 0.75), mat, bevel=0.03, seg=1, wonk=wonk * 0.5))
    if front is not None and modillions:
        n = max(4, int(w / 0.55))
        for i in range(n + 1):
            x = -w / 2 + w * i / n
            parts.append(box("modil", (0.12, proud, t * 0.25), (x, front - proud / 2 - proud * 0.25, z + t * 0.1), mat))


def quoins(parts, width, depth, z0, z1, face, cx=0.0):
    """Alternating stone blocks up the front corners."""
    z = z0
    i = 0
    while z < z1 - 0.3:
        hgt = min(0.5, z1 - z - 0.06)
        for sx in (-1, 1):
            w = 0.9 if i % 2 == 0 else 0.6
            parts.append(box("quoin", (w, 0.12, hgt), (cx + sx * (width / 2 - w / 2 + 0.02), face - 0.05, z), M("stone_pale"), bevel=0, wonk=0.02))
        z += 0.56
        i += 1


def door(parts, x, face, w=2.2, h=3.2):
    """Legacy portal (slabs on a plain wall). New facades use facade() + door_unit()."""
    parts.append(arch("portal", w + 0.7, h + 0.4, 0.42, (x, face - 0.30, 0), M("stone"), bevel=0.06))
    parts.append(arch("door", w, h, 0.16, (x, face - 0.36, 0), M("wood_dark"), bevel=0.03))
    for zz in (0.8, h - 1.0):
        parts.append(box("strap", (w - 0.3, 0.05, 0.14), (x, face - 0.41, zz), M("iron", 0.6), bevel=0.02))
    parts.append(box("keystone", (0.5, 0.46, 0.7), (x, face - 0.32, h + 0.2), M("stone_pale"), bevel=0.05, wonk=0.02))
    parts.append(box("step", (w + 1.0, 0.7, 0.18), (x, face - 0.45, 0), M("stone_dark"), bevel=0.05, wonk=0.02))


def chimney(parts, x, y, z, h=2.6):
    lean_x, lean_y = RNG.uniform(-0.04, 0.04), RNG.uniform(-0.025, 0.025)
    c = box("chimney", (0.9, 0.9, h), (x, y, z), M("brick"), bevel=0.03, seg=1, wonk=0.02)
    shear(c, lean_x, lean_y, z0=z)
    parts.append(c)
    tx, ty = x + h * lean_x, y + h * lean_y
    parts.append(box("band", (1.0, 1.0, 0.12), (x + (h - 0.5) * lean_x, y + (h - 0.5) * lean_y, z + h - 0.5), M("brick_dark"), bevel=0.02, seg=1))
    parts.append(box("cap", (1.1, 1.1, 0.16), (tx, ty, z + h - 0.02), M("stone_dark"), bevel=0.03, seg=1))
    for k, dx in enumerate((-0.2, 0.2)):
        parts.append(cyl("pot", 0.14, 0.45, (tx + dx, ty, z + h + 0.14), M("terracotta" if k else "brick_dark"), verts=10, r2=0.11))
        mark("Chimney", (tx + dx, ty, z + h + 0.62))
    parts.append(box("snow", (0.98, 0.98, 0.05), (tx, ty, z + h + 0.14), M("snow"), bevel=0.02, seg=1))
    rl = []
    rime(rl, "-X", x - 0.45, -y, z + 0.3, 0.8, h - 0.9, seed=int(abs(x * 10)))
    for o in rl:
        shear(o, lean_x, lean_y, z0=z)
    parts += rl
    return (x, y)


def plinth(parts, x0, x1, y_face, h=0.5, proud=0.08, mat=None, skip=()):
    """Stone or damp-plaster plinth along a -Y wall from x0 to x1, broken at each (xa, xb) in skip."""
    segs, a = [], x0
    for (xa, xb) in sorted(skip):
        if xa > a:
            segs.append((a, xa))
        a = max(a, xb)
    if a < x1:
        segs.append((a, x1))
    for (xa, xb) in segs:
        if xb - xa > 0.05:
            parts.append(box("plinth", (xb - xa, proud + 0.05, h), ((xa + xb) / 2, y_face - proud / 2 + 0.025, 0), mat or M("stone_dark"), bevel=0.02, seg=1))


def dormer(parts, x, y_front, zb, w, h, wall, roofmat, depth=1.6, warm=False, snow=False):
    """Dormer with a real window: plaster cheeks and front, a recessed casement, a small tiled gable roof."""
    parts.append(box("dormer", (w, depth - REV, h), (x, y_front + REV + (depth - REV) / 2, zb), wall, bevel=0.03, seg=1))
    ww, wh = w * 0.52, h * 0.58
    op = [(x, zb + 0.28, ww, wh, "rect")]
    parts.append(facade("dormer_face", wall, "-Y", y_front, x - w / 2 - 0.01, x + w / 2 + 0.01, zb, zb + h, op))
    win_unit(parts, "-Y", y_front, x, zb + 0.28, ww, wh, "rect", warm=warm, surround=None, head=None, cross=True, snow=snow)
    parts.append(box("dormer_board", (w + 0.12, 0.08, 0.12), (x, y_front - 0.03, zb + h - 0.06), M("wood_dark")))
    parts.append(roof("dormer_r", depth + 0.35, w + 0.4, h * 0.55, (x, y_front + depth / 2 - 0.15, zb + h), roofmat, sag=0.03, flare=0.1, cuts=3, along_x=False, bevel=0.03))
    if snow:
        sn = roof_snow("dormer_snow", depth + 0.35, w + 0.4, h * 0.55, (x, y_front + depth / 2 - 0.15, zb + h), sag=0.03, flare=0.1,
                       cuts=3, along_x=False, thick=0.05, cell=0.8, bare=0.2, slide=0.0, seed=int(x * 7) + 3, lip=0.04)
        if sn:
            parts.append(sn)
        icicles(parts, (x - w / 2 - 0.2, y_front - 0.25), (x - w / 2 - 0.2, y_front + depth - 0.4), zb + h - 0.02, maxlen=0.25, seed=int(x * 5), density=3)
        icicles(parts, (x + w / 2 + 0.2, y_front - 0.25), (x + w / 2 + 0.2, y_front + depth - 0.4), zb + h - 0.02, maxlen=0.25, seed=int(x * 5) + 1, density=3)


# ------------------------------------------------------------------ DETAIL PASS: markers, snow blankets, ice, shutters, iron
# Named empties for the runtime (smoke from chimneys, people at windows, forge light): `mark()` records one, export()
# writes it as a child node of the asset root (Chimney_<n>, Window_<n>, Furnace_<n>, numbered from 0 per asset).
FACE_ROT = {"-Y": 0.0, "+Y": math.pi, "+X": math.pi / 2, "-X": -math.pi / 2}


def mark(kind, loc, rot_z=0.0):
    _MARKS.append([kind, Vector(loc), rot_z])


def mark_window(face, plane, a, zb):
    """Window_<n> on the sill centre of an openable window, its -Y (Blender front) pointing out of the facade."""
    mark("Window", _wp(face, plane, a, zb, 0.02), FACE_ROT[face])


def shear_marks(kx, ky, z0=0.0):
    for m in _MARKS:
        m[1].x += (m[1].z - z0) * kx
        m[1].y += (m[1].z - z0) * ky


from mathutils import noise as _mnoise


def _n01(p, f, seed):
    return 0.5 + 0.5 * _mnoise.noise(Vector((p.x * f + seed * 17.31, p.y * f - seed * 5.13, p.z * f + seed * 2.97)))


def snow_shell(src, name="snow", thick=0.07, minz=0.35, bare=0.23, lee=(0.25, 1.0), lee_k=0.8, drifts=(), seed=0,
               cell=0.75, slide=0.28, lip=0.07, keep_src=False, flat_k=1.0, maxz=1.01):
    """A conformal snow blanket over the upward faces of `src` (consumed unless keep_src): the faces are subdivided
    to ~`cell` metres, some are dropped where the snow slid off (random bare patches, more of them low on the
    slope, and downslope slide strips on steep faces that show the tiles), then the rest is lifted a centimetre
    and solidified outward with a per-vertex thickness: noise, thicker on the lee slopes (lee = the downwind
    direction in asset space), thinner along a scoured ridge, piled up in `drifts` (x, y, radius, extra metres)
    against chimneys and dormers, and a lip that curls a few cm over the eaves. Thin (thick ~ 5-9 cm): no blocks."""
    bm = bmesh.new()
    bm.from_mesh(src.data)
    if not keep_src:
        bpy.data.objects.remove(src, do_unlink=True)
    bm.normal_update()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z < minz or f.normal.z > maxz], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    for _ in range(6):
        long = [e for e in bm.edges if e.calc_length() > cell]
        if not long:
            break
        bmesh.ops.subdivide_edges(bm, edges=long, cuts=1, use_grid_fill=True)
    bm.normal_update()
    if not bm.verts:
        bm.free()
        return None
    # ragged outlines: triangulate with mixed diagonals and jitter the interior vertices in the surface plane, so
    # bare patches and slide strips read as torn snow rather than grid squares
    jr = random.Random(seed + 77)
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="ALTERNATE")
    outer = bm.verts.layers.int.new("outer")
    for v in bm.verts:
        v[outer] = 1 if v.is_boundary else 0
    for v in bm.verts:
        if v.is_boundary:
            continue
        n = v.normal
        j = Vector((jr.uniform(-1, 1), jr.uniform(-1, 1), jr.uniform(-1, 1))) * cell * 0.15
        v.co += j - n * j.dot(n)
    bm.normal_update()
    zs = [v.co.z for v in bm.verts]
    z0, z1 = min(zs), max(zs)
    zr = max(0.01, z1 - z0)
    rng = random.Random(seed)
    band_r = {}
    dead = []
    for f in bm.faces:
        c = f.calc_center_median()
        n = f.normal
        zf = (c.z - z0) / zr
        if _n01(c, 0.55, seed) + 0.08 * (jr.random() - 0.5) < bare + 0.12 * (1.0 - zf) - (0.25 if n.z > 0.97 else 0.0):
            dead.append(f)
            continue
        if n.z < 0.92 and slide > 0:
            t = Vector((-n.y, n.x, 0.0))
            if t.length > 1e-4:
                t.normalize()
                key = (int(math.floor((c.dot(t) + 0.25 * _mnoise.noise(c * 1.7)) / 0.8)), round(n.x * 2), round(n.y * 2))
                if key not in band_r:
                    band_r[key] = (rng.random(), rng.uniform(0.2, 0.75))
                pr, ln = band_r[key]
                if pr < slide and zf < ln:
                    dead.append(f)
    bmesh.ops.delete(bm, geom=list(set(dead)), context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    if not bm.faces:
        bm.free()
        return None
    # round off the torn edges of the bare patches: relax the new boundary loops (not the roof's own outline)
    for _ in range(4):
        moves = {}
        for v in bm.verts:
            if not v.is_boundary or v[outer]:
                continue
            nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(nb) == 2:
                moves[v] = (nb[0].co + nb[1].co) * 0.5
        for v, p in moves.items():
            v.co = v.co * 0.4 + p * 0.6
    bm.normal_update()
    L = Vector((lee[0], lee[1], 0.0))
    L = L.normalized() if L.length > 1e-4 else L
    ws = {}
    for v in bm.verts:
        n = v.normal
        t = 0.55 + 0.9 * _n01(v.co, 1.4, seed + 3)
        h = Vector((n.x, n.y, 0.0))
        if h.length > 0.05:
            d = h.normalized().dot(L)
            t *= 1.0 + lee_k * max(0.0, d) - 0.35 * max(0.0, -d)
        else:
            t *= flat_k
        if (v.co.z - z0) / zr > 0.93 and n.z < 0.95:
            t *= 0.6
        for (dx, dy, r, extra) in drifts:
            dd = math.hypot(v.co.x - dx, v.co.y - dy)
            if dd < r:
                t += (extra / thick) * (1.0 - dd / r) ** 2
        ws[v.index] = t
        v.co += n * 0.012
    for v in {v for e in bm.edges if e.is_boundary for v in e.verts}:
        if v.co.z < z0 + 0.1 and v.normal.z < 0.97:
            h = Vector((v.normal.x, v.normal.y, 0.0))
            if h.length > 0.05:
                v.co += h.normalized() * lip
                v.co.z -= lip * 0.3
    tmax = max(ws.values())
    o = _mesh_obj(name, bm, M("snow"))
    vg = o.vertex_groups.new(name="th")
    for i, t in ws.items():
        vg.add([i], max(0.05, t / tmax), "REPLACE")
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    m = o.modifiers.new("solid", "SOLIDIFY")
    m.thickness = thick * tmax
    m.offset = 1.0
    m.use_rim = True
    m.use_even_offset = False
    m.use_quality_normals = True
    m.vertex_group = "th"
    m.thickness_vertex_group = 0.05
    bpy.ops.object.modifier_apply(modifier="solid")
    o.vertex_groups.clear()
    _tag(o, mat=M("snow"))
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(70))
    return o


def roof_snow(name, L, W, H, loc, sag=0.25, flare=0.30, cuts=6, top_w=0.0, along_x=True, **kw):
    """snow_shell() over a clean (unbevelled) copy of the same roof() solid."""
    kw.setdefault("cell", 1.0)
    base = roof(name + "_base", L, W, H, loc, None, sag=sag, flare=flare, cuts=cuts, top_w=top_w, along_x=along_x, bevel=0)
    return snow_shell(base, name, **kw)


def cap_snow(name, obj_fn, **kw):
    """snow_shell() over a throwaway primitive built by obj_fn() (domes, spires, pinnacle caps)."""
    kw.setdefault("slide", 0.0)
    return snow_shell(obj_fn(), name, **kw)


def icicles(parts, p0, p1, z, maxlen=0.45, seed=0, r=0.03, density=2.4, gap=0.3):
    """A row of thin tapered icicles hanging from z along p0-p1 (four-sided cones in one mesh, ~4 tris each),
    lengths skewed short with the odd long spear, clustered where the drip is."""
    rng = random.Random(seed)
    p0, p1 = Vector((p0[0], p0[1], z)), Vector((p1[0], p1[1], z))
    n = max(2, int((p1 - p0).length * density))
    bm = bmesh.new()
    for i in range(n):
        if rng.random() < gap:
            continue
        t = (i + rng.uniform(0.15, 0.85)) / n
        p = p0.lerp(p1, t)
        ln = 0.05 + maxlen * rng.random() ** 2.4
        rr = r * (0.55 + 0.7 * rng.random()) * (0.6 + ln / maxlen * 0.6)
        _tube(bm, p + Vector((0, 0, 0.01)), p + Vector((rng.uniform(-0.02, 0.02), rng.uniform(-0.02, 0.02), -ln)), rr, 0.0, n=4)
    if not bm.verts:
        bm.free()
        return
    o = _mesh_obj("icicles", bm, M("ice", 0.08))
    for f in o.data.polygons:
        f.use_smooth = True
    parts.append(o)


def eave_icicles(parts, L, W, z, loc=(0.0, 0.0), along_x=True, sides=(-1, 1), seed=0, **kw):
    """Icicles under both eaves of a roof(L, W, ..., loc) at eave height z."""
    x, y = loc[0], loc[1]
    for k, s in enumerate(sides):
        if along_x:
            icicles(parts, (x - L / 2 + 0.2, y + s * W / 2), (x + L / 2 - 0.2, y + s * W / 2), z, seed=seed + k, **kw)
        else:
            icicles(parts, (x + s * W / 2, y - L / 2 + 0.2), (x + s * W / 2, y + L / 2 - 0.2), z, seed=seed + k, **kw)


def snow_cap(parts, x, y, z, r, h=None, seg=10):
    """A little dome of snow on a finial, ball, post or pinnacle top."""
    h = h if h is not None else r * 0.45
    o = sphere("cap_snow", r, (x, y, z), M("snow"), seg=seg, rings=5, zscale=h / r)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < z - 0.001], context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    parts.append(o)


def rime(parts, face, plane, a, zb, w, h, seed=0):
    """Thin frost crust on a windward face: a few irregular white scabs a few mm proud of the wall."""
    rng = random.Random(seed)
    for k in range(int(max(1, w * h / 4.0))):
        aa = a + rng.uniform(-w / 2, w / 2)
        zz = zb + rng.uniform(0.2, 1.0) ** 0.5 * h
        sw, sh = rng.uniform(0.2, 0.6), rng.uniform(0.08, 0.3)
        pts = [(aa - sw / 2, zz), (aa + sw / 2, zz + rng.uniform(-0.04, 0.04)), (aa + sw * 0.3, zz + sh), (aa - sw * 0.4, zz + sh * 0.8)]
        parts.append(slab("rime", pts, face, plane, 0.0, 0.006, M("snow")))


def _swing(o, hinge, ang):
    c, s = math.cos(ang), math.sin(ang)
    def f(co):
        dx, dy = co.x - hinge.x, co.y - hinge.y
        co.x, co.y = hinge.x + dx * c - dy * s, hinge.y + dx * s + dy * c
    return edit_verts(o, f)


def shutter_pair(parts, face, plane, a, zb, w, h, style="board", colour="shutter", open_deg=(180, 180), snow=True):
    """Two shutter leaves hinged on the window's outer jambs. style "board" (ledged planks with a Z brace) or
    "louvre" (stiles, rails and slanted slats). open_deg per leaf: 180 = folded back flat against the wall,
    ~100 = standing out half-open, 0 = closed over the window."""
    A, N = _FACES[face]
    mat = M(colour)
    iron = M("iron")
    sw = w / 2 + 0.03
    for k, sx in enumerate((-1, 1)):
        hinge_a = a + sx * (w / 2 + 0.02)
        hinge = _wp(face, plane, hinge_a, 0.0, 0.05)
        ac = hinge_a - sx * sw / 2                      # closed position: spanning into the opening
        leaf = []
        if style == "louvre":
            for aa in (ac - sw / 2 + 0.035, ac + sw / 2 - 0.035):
                leaf.append(fbox("stile", face, plane, aa, 0.05, zb, 0.07, 0.04, h, mat))
            for zz in (zb, zb + h / 2 - 0.035, zb + h - 0.07):
                leaf.append(fbox("rail", face, plane, ac, 0.05, zz, sw - 0.1, 0.035, 0.07, mat))
            ns = max(4, int(h / 0.3))
            for j in range(ns):
                zz = zb + 0.09 + (h - 0.18) * (j + 0.5) / ns - 0.03
                if abs(zz - (zb + h / 2)) < 0.06:
                    continue
                sl = fbox("slat", face, plane, ac, 0.05, zz, sw - 0.12, 0.012, 0.075, mat)
                o = _wp(face, plane, ac, zz + 0.04, 0.05)
                ax = A
                def tilt(co, o=o, ax=ax):
                    rel = co - o
                    along = rel.dot(ax)
                    perp = rel - ax * along
                    zc, nc = perp.z, perp - Vector((0, 0, perp.z))
                    ang = math.radians(35)
                    nn = nc.length * (1 if nc.dot(N) >= 0 else -1)
                    z2 = zc * math.cos(ang) - nn * math.sin(ang)
                    n2 = zc * math.sin(ang) + nn * math.cos(ang)
                    co.xyz = o + ax * along + N * n2 + Vector((0, 0, z2))
                edit_verts(sl, tilt)
                leaf.append(sl)
        else:
            leaf.append(fbox("leaf", face, plane, ac, 0.05, zb, sw, 0.04, h, mat))
            for zz in (zb + 0.18, zb + h - 0.3):
                leaf.append(fbox("ledge", face, plane, ac, 0.085, zz, sw - 0.06, 0.03, 0.1, mat))
            leaf.append(fbox("plank", face, plane, ac - sw / 6, 0.072, zb, 0.012, 0.01, h, M("wood_dark")))
            leaf.append(fbox("plank", face, plane, ac + sw / 6, 0.072, zb, 0.012, 0.01, h, M("wood_dark")))
        for zz in ((zb + 0.2, zb + h - 0.26) if style != "louvre" else ()):
            leaf.append(fbox("strap", face, plane, hinge_a - sx * sw * 0.35, 0.09, zz, sw * 0.7, 0.01, 0.035, iron))
        lo = join(leaf, "shutter")
        dirv = A * (-sx)
        sgn = 1.0 if dirv.cross(N).z > 0 else -1.0
        _swing(lo, hinge, math.radians(open_deg[k]) * sgn)
        parts.append(lo)
        if 60 < open_deg[k] < 170 and snow:
            pass
    # the iron catches (holdbacks) on the wall
    for sx in (-1, 1):
        parts.append(fbox("catch", face, plane, a + sx * (w / 2 + sw + 0.05), 0.04, zb + 0.35, 0.03, 0.08, 0.03, iron))


def wall_anchor(parts, face, plane, a, z, kind="S"):
    """Wrought-iron tie-rod anchor (kotwa) on a facade at a floor line: an S, an X or a plain bar."""
    iron = M("iron")
    if kind == "X":
        for ang in (0.6, -0.6):
            b = fbox("anchor", face, plane, a, 0.02, z - 0.35, 0.05, 0.03, 0.7, iron)
            c = _wp(face, plane, a, z, 0.02)
            A, N = _FACES[face]
            def rot(co, c=c, ang=ang, A=A):
                rel = co - c
                u, zz = rel.dot(A), rel.z
                rest = rel - A * u - Vector((0, 0, zz))
                u2, z2 = u * math.cos(ang) - zz * math.sin(ang), u * math.sin(ang) + zz * math.cos(ang)
                co.xyz = c + A * u2 + Vector((0, 0, z2)) + rest
            edit_verts(b, rot)
            parts.append(b)
    else:
        parts.append(fbox("anchor", face, plane, a, 0.02, z - 0.3, 0.05, 0.03, 0.6, iron))
        if kind == "S":
            parts.append(fbox("anchor_t", face, plane, a + 0.07, 0.02, z + 0.26, 0.14, 0.03, 0.05, iron))
            parts.append(fbox("anchor_b", face, plane, a - 0.07, 0.02, z - 0.3, 0.14, 0.03, 0.05, iron))
        parts.append(fbox("anchor_nut", face, plane, a, 0.04, z - 0.04, 0.08, 0.04, 0.08, iron))


def balcony_iron(parts, face, plane, a, z, w=2.2, d=0.85, seed=0):
    """Stone balcony slab on three carved consoles with a wrought-iron railing (balusters, a scrolled panel in
    front), snow on the slab and the top rail and a fringe of icicles under the slab lip."""
    st, iron = M("stone_pale"), M("iron")
    parts.append(fbox("bal_slab", face, plane, a, d / 2, z - 0.18, w, d, 0.18, st, bevel=0.03, seg=1))
    cc = _wp(face, plane, a, z - 0.09, d / 2)
    A_, N_ = _FACES[face]
    climb("ledge", (w, d, 0.2) if abs(A_.x) > 0.5 else (d, w, 0.2), (cc.x, cc.y, z - 0.09))
    for k in (-1, 0, 1):
        c = fbox("console", face, plane, a + k * (w / 2 - 0.25), 0.25, z - 0.7, 0.24, 0.5, 0.52, st, bevel=0.02, seg=1)
        A, N = _FACES[face]
        base = _wp(face, plane, 0, z - 0.7, 0.0)
        def taper(co, base=base, N=N):
            rel = co - base
            out = rel.dot(N)
            zz = rel.z
            if zz < 0.2:
                co.xyz = co - N * out + N * min(out, 0.08)
        edit_verts(c, taper)
        parts.append(c)
    H = 0.95
    parts.append(fbox("bal_rail", face, plane, a, d - 0.06, z + H - 0.04, w - 0.08, 0.05, 0.05, iron))
    parts.append(fbox("bal_bot", face, plane, a, d - 0.06, z + 0.08, w - 0.08, 0.04, 0.035, iron))
    for s in (-1, 1):
        parts.append(fbox("bal_side_r", face, plane, a + s * (w / 2 - 0.06), d / 2, z + H - 0.04, 0.05, d - 0.1, 0.05, iron))
        parts.append(fbox("bal_side_b", face, plane, a + s * (w / 2 - 0.06), d / 2, z + 0.08, 0.035, d - 0.1, 0.035, iron))
        for j in range(3):
            parts.append(fbox("bal_sbal", face, plane, a + s * (w / 2 - 0.06), 0.15 + j * (d - 0.25) / 2, z + 0.1, 0.02, 0.02, H - 0.14, iron))
    n = int((w - 0.2) / 0.13)
    for j in range(n + 1):
        aa = a - (w - 0.2) / 2 + (w - 0.2) * j / n
        if abs(aa - a) < 0.32:
            continue
        parts.append(fbox("bal_bal", face, plane, aa, d - 0.06, z + 0.1, 0.02, 0.02, H - 0.14, iron))
    ctr = _wp(face, plane, a, z + H * 0.5, d - 0.06)
    rot = (math.pi / 2, 0, 0) if face in ("-Y", "+Y") else (0, math.pi / 2, 0)
    parts.append(torus("bal_scroll", 0.2, 0.014, tuple(ctr), iron, rot=rot, seg=12, mseg=3))
    for s in (-1, 1):
        c2 = _wp(face, plane, a + s * 0.17, z + H * 0.5 + 0.2 * s, d - 0.06)
        parts.append(torus("bal_scroll", 0.1, 0.012, tuple(c2), iron, rot=rot, seg=8, mseg=3))
    parts.append(fbox("bal_snow", face, plane, a, d / 2 + 0.02, z, w - 0.14, d - 0.12, 0.04, M("snow")))
    parts.append(fbox("bal_rsnow", face, plane, a, d - 0.06, z + H + 0.01, w - 0.2, 0.06, 0.025, M("snow")))
    p0, p1 = _wp(face, plane, a - w / 2 + 0.1, 0, d + 0.01), _wp(face, plane, a + w / 2 - 0.1, 0, d + 0.01)
    icicles(parts, p0, p1, z - 0.18, maxlen=0.35, seed=seed, density=3.0)


def gallery_wood(parts, face, plane, a0, a1, z, d=1.2, posts=4, roof_h=2.6, seed=0):
    """Courtyard gallery (ganek): joists out of the wall, a plank deck, turned posts to a lean-to roof above,
    a rail of flat cut-out balusters, snow on the rail, the deck edge and the little roof."""
    wd, dk = M("wood"), M("wood_dark")
    w = a1 - a0
    ac = (a0 + a1) / 2
    parts.append(fbox("gal_deck", face, plane, ac, d / 2, z - 0.08, w, d, 0.08, wd))
    gc = _wp(face, plane, ac, z - 0.06, d / 2)
    A_, N_ = _FACES[face]
    climb("ledge", (w, d, 0.12) if abs(A_.x) > 0.5 else (d, w, 0.12), (gc.x, gc.y, z - 0.06))
    for k in range(int(w / 0.9) + 1):
        aa = a0 + 0.1 + (w - 0.2) * k / max(1, int(w / 0.9))
        parts.append(fbox("gal_joist", face, plane, aa, d / 2, z - 0.28, 0.14, d + 0.1, 0.2, dk))
    for k in range(posts + 1):
        aa = a0 + 0.08 + (w - 0.16) * k / posts
        parts.append(fbox("gal_post", face, plane, aa, d - 0.08, z, 0.12, 0.12, roof_h, dk))
        parts.append(fbox("gal_brace", face, plane, aa, d - 0.4, z + roof_h - 0.45, 0.08, 0.6, 0.08, dk))
    parts.append(fbox("gal_rail", face, plane, ac, d - 0.08, z + 0.95, w, 0.1, 0.07, wd))
    parts.append(fbox("gal_rsnow", face, plane, ac, d - 0.08, z + 1.02, w - 0.1, 0.1, 0.03, M("snow")))
    nb = int(w / 0.24)
    for k in range(nb):
        aa = a0 + 0.12 + (w - 0.24) * (k + 0.5) / nb
        parts.append(fbox("gal_bal", face, plane, aa, d - 0.08, z, 0.1, 0.025, 0.95, wd))
    parts.append(fbox("gal_plate", face, plane, ac, d - 0.08, z + roof_h, w + 0.2, 0.14, 0.14, dk))
    A, N = _FACES[face]
    c0 = _wp(face, plane, ac, z + roof_h + 0.14, d / 2)
    pts = [(a0 - 0.2, z + roof_h + 0.1), (a1 + 0.2, z + roof_h + 0.1), (a1 + 0.2, z + roof_h + 0.2), (a0 - 0.2, z + roof_h + 0.2)]
    roofp = slab("gal_roof", pts, face, plane, 0.0, d + 0.35, M("shingle"))
    def pitch(co):
        out = (co - _wp(face, plane, 0, 0, 0)).dot(N)
        co.z += 0.6 * (1.0 - out / (d + 0.35))
    edit_verts(roofp, pitch)
    parts.append(roofp)
    sn = slab("gal_roof_snow", [(a0 - 0.15, z + roof_h + 0.2), (a1 + 0.15, z + roof_h + 0.2), (a1 + 0.15, z + roof_h + 0.25), (a0 - 0.15, z + roof_h + 0.25)], face, plane, 0.05, d + 0.3, M("snow"))
    edit_verts(sn, pitch)
    parts.append(sn)
    p0, p1 = _wp(face, plane, a0, 0, d + 0.35), _wp(face, plane, a1, 0, d + 0.35)
    icicles(parts, p0, p1, z + roof_h + 0.1, maxlen=0.4, seed=seed)


def rustication(parts, face, plane, a0, a1, z0, z1, ops=(), course=0.5, proud=0.035, mat=None):
    """Banded rustication: horizontal stone courses standing proud with sunk joints, broken around openings
    (a, zb, w, h, shape) (their bounding rectangles plus the arch ring)."""
    mat = mat or M("stone")
    z = z0
    while z < z1 - 0.1:
        zt = min(z1, z + course) - 0.04
        segs = [(a0, a1)]
        for (a, zb, w, h, sh) in ops:
            if zb - 0.02 < zt and zb + h + 0.35 > z:
                lo, hi = a - w / 2 - 0.08, a + w / 2 + 0.08
                nxt = []
                for (s0, s1) in segs:
                    if hi <= s0 or lo >= s1:
                        nxt.append((s0, s1))
                    else:
                        if lo > s0:
                            nxt.append((s0, lo))
                        if hi < s1:
                            nxt.append((hi, s1))
                segs = nxt
        for (s0, s1) in segs:
            if s1 - s0 > 0.1:
                parts.append(fbox("rust", face, plane, (s0 + s1) / 2, proud / 2, z, s1 - s0, proud, zt - z, mat))
        z += course


def dome_ribs(parts, cx, cy, zc, r, n=8, zscale=1.0, mat=None, snow=True, z_from=0.0, width=0.07):
    """Standing ribs down a dome (sphere centre zc, radius r, squashed by zscale) from the top to z_from above the
    centre, with a thin line of snow lodged on the upper side of each rib."""
    mat = mat or M("gold", 0.4)
    bm = bmesh.new()
    bs = bmesh.new()
    lat0 = math.asin(max(-0.99, min(0.99, z_from / (r * zscale))))
    steps = 8
    for k in range(n):
        a = math.tau * k / n
        prev = None
        for j in range(steps + 1):
            lat = lat0 + (math.pi / 2 - 0.08 - lat0) * j / steps
            p = Vector((cx + (r + 0.03) * math.cos(lat) * math.cos(a), cy + (r + 0.03) * math.cos(lat) * math.sin(a), zc + (r + 0.03) * math.sin(lat) * zscale))
            if prev is not None:
                _tube(bm, prev, p, width, width, n=4)
                if snow and lat > 0.35:
                    up = Vector((0, 0, width * 0.9))
                    _tube(bs, prev + up, p + up, width * 0.8, width * 0.8, n=4)
            prev = p
    parts.append(_mesh_obj("ribs", bm, mat))
    if snow and bs.verts:
        parts.append(_mesh_obj("rib_snow", bs, M("snow")))
    else:
        bs.free()


def rot_panel(parts, name, cx, cy, ang, pts, d0, d1, mat):
    """Extrude an (a, z) outline on a vertical plane facing direction `ang` (radians) through (cx, cy)."""
    n = Vector((math.cos(ang), math.sin(ang), 0.0))
    t = Vector((-math.sin(ang), math.cos(ang), 0.0))
    bm = bmesh.new()
    f = [bm.verts.new(Vector((cx, cy, 0)) + t * a + n * d1 + Vector((0, 0, z))) for (a, z) in pts]
    b = [bm.verts.new(Vector((cx, cy, 0)) + t * a + n * d0 + Vector((0, 0, z))) for (a, z) in pts]
    bm.faces.new(f)
    bm.faces.new(list(reversed(b)))
    for i in range(len(pts)):
        j = (i + 1) % len(pts)
        bm.faces.new((f[i], b[i], b[j], f[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _mesh_obj(name, bm, mat)
    for p in o.data.polygons:
        p.use_smooth = False
    parts.append(o)
    return o


def clock_face(parts, c, n, R, hh=11, mm=50, mat_hand=None):
    """Hour ticks, a chapter ring and two hands on a clock dial of radius R centred at c facing the unit normal n."""
    n = Vector(n).normalized()
    t = Vector((-n.y, n.x, 0.0)) * -1.0          # the viewer's right, looking at the dial from outside
    up = Vector((0, 0, 1))
    c = Vector(c) + n * 0.01
    bm = bmesh.new()
    def quad(u0, v0, u1, v1, dir_u, dir_v, off):
        pts = [c + n * off + dir_u * u + dir_v * v for (u, v) in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
        bm.faces.new([bm.verts.new(p) for p in pts])
    for k in range(12):
        th = math.tau * k / 12
        du = t * math.cos(th) - up * math.sin(th)      # radial direction on the dial (k=0 at 3 o'clock)
        dv = t * math.sin(th) + up * math.cos(th)
        L = 0.22 if k % 3 == 0 else 0.12
        wdt = 0.05 if k % 3 == 0 else 0.03
        quad(R * 0.78, -wdt, R * 0.78 + L, wdt, du, dv, 0.0)
    for (ang, L, wdt) in ((math.tau * ((hh % 12) + mm / 60) / 12, R * 0.52, 0.07), (math.tau * mm / 60, R * 0.78, 0.045)):
        dirv = t * math.sin(ang) + up * math.cos(ang)
        perp = t * math.cos(ang) - up * math.sin(ang)
        pts = [c + n * 0.02 - dirv * 0.12 - perp * wdt, c + n * 0.02 - dirv * 0.12 + perp * wdt,
               c + n * 0.02 + dirv * L * 0.8 + perp * wdt * 1.4, c + n * 0.02 + dirv * L, c + n * 0.02 + dirv * L * 0.8 - perp * wdt * 1.4]
        bm.faces.new([bm.verts.new(p) for p in pts])
    o = _mesh_obj("clock_marks", bm, mat_hand or M("black"))
    parts.append(o)
    parts.append(sphere("clock_boss", 0.07, tuple(c + n * 0.04), M("gold", 0.35), seg=8, rings=5))


def mascaron(parts, face, plane, a, z, s=0.3, mat=None):
    """Carved head on a keystone: a lumpy face with brow, nose and a hint of beard."""
    mat = mat or M("stone_pale")
    c = _wp(face, plane, a, z, 0.08)
    parts.append(blob("masc", (s, s * 0.5, s * 1.2), (c.x, c.y, z - s * 0.6), mat, subsurf=1))
    n = _wp(face, plane, a, z + s * 0.05, 0.08 + s * 0.3)
    parts.append(blob("masc_nose", (s * 0.18, s * 0.2, s * 0.3), (n.x, n.y, z - s * 0.1), mat, subsurf=1))


# ------------------------------------------------------------------ TENEMENT (kamienica)
SIGNS = iter(["disc", "key", "pretzel", "boot", "disc", "key", "boot", "pretzel"] * 4)


def tenement(name, width, storeys, roof_kind, colour, bays=3, pilasters=False, arched_windows=False, shutters=False,
             shutter_col="shutter", shutter_style="louvre", balcony=None, gallery=False, seed=0):
    """Kamienica facing the square. The street openings (door, shop windows, upper windows) are fixed: dressing.gd
    mirrors them. shutters: painted louvred or boarded leaves (shutter_style) in the district colour, mostly
    folded back, a few standing half-open or closed. balcony: storey index whose middle window becomes a
    balcony door with a wrought-iron balcony. gallery: a timber courtyard gallery on the back (+Y) wall.
    The back wall facing the outer streets gets plain casements, anchors and a frost crust; the roof gets a
    snow blanket with drifts at the chimney and dormers and icicles along the eaves and the cornice."""
    reset()
    rng = random.Random(seed or hash(name) & 0xffff)
    D = 8.0
    GF, FL = 4.2, 3.3
    body_h = GF + FL * (storeys - 1)
    plaster = M(colour)
    spale = M("stone_pale")
    stone = M("stone")
    parts = []
    face = -D / 2
    jetty = 0.22

    bay_w = width / bays
    xs = [-width / 2 + bay_w * (i + 0.5) for i in range(bays)]
    px = xs[bays // 2] if bays % 2 else xs[0]
    dw, dh = 2.0, 2.9

    # ground floor: rusticated sandstone, a portal and arched shop windows recessed into it
    gf_open = [(px, 0.0, dw, dh + 0.12 + dw / 2, "round")]
    gf_win = [(x, 1.25, 1.3, 2.2, "round") for x in xs if abs(x - px) > 0.1]
    parts.append(box("gf", (width, D - REV, GF), (0, REV / 2, 0), spale, bevel=0.05, seg=1, wonk=0.03))
    parts.append(facade("gf_face", spale, "-Y", face, -width / 2 - 0.01, width / 2 + 0.01, 0.0, GF, gf_open + gf_win))
    door_unit(parts, "-Y", face, px, dw, dh)
    for (x, zb, w, h, sh) in gf_win:
        win_unit(parts, "-Y", face, x, zb, w, h, sh, warm=RNG.random() < 0.5, surround=None, bars=True, cross=True, mark=True)
    rustication(parts, "-Y", face, -width / 2, width / 2, 0.55, GF - 0.3, gf_open + gf_win, course=0.62, proud=0.03, mat=spale)
    plinth(parts, -width / 2, width / 2, face, h=0.55, skip=[(px - dw / 2 - 0.45, px + dw / 2 + 0.45)])
    parts.append(box("gf_band", (width + 0.1, 0.22, 0.22), (0, face - 0.06, GF - 0.26), stone, bevel=0.03, seg=1))
    side = 1 if px < 0.5 else -1
    sx_ = px + side * (dw / 2 + 1.05)
    if abs(sx_) < width / 2 - 0.6:
        shop_sign(parts, sx_, face, 3.5, emblem=next(SIGNS))

    walls = [(1.0, face), (3.0, face)]
    for s in range(1, storeys):
        z0 = GF + FL * (s - 1)
        yf = face - jetty * s
        ws = width + jetty * s * 0.4
        parts.append(box("floor", (ws, D + jetty * s - REV, FL), (0, -jetty * s * 0.5 + REV / 2, z0), plaster, bevel=0.06, seg=1, wonk=0.035))
        ops = [(x, z0 + 0.8, 1.1, 1.85 if not (arched_windows and s == 1) else 2.1, "round" if (arched_windows and s == 1) else "rect") for x in xs]
        bal_x = None
        if balcony == s:
            bal_x = xs[len(xs) // 2]
            ops = [(x, z0 + 0.1, 1.1, 2.55, "rect") if x == bal_x else o for (x, o) in zip(xs, ops)]
        parts.append(facade("face", plaster, "-Y", yf, -ws / 2 - 0.01, ws / 2 + 0.01, z0, z0 + FL, ops))
        for (x, zb, w, h, sh) in ops:
            if x == bal_x:
                win_unit(parts, "-Y", yf, x, zb, w, h, sh, warm=True, sill=False, snow=False, drip=False)
                balcony_iron(parts, "-Y", yf, x, zb, w=2.4, d=0.85, seed=s + 11)
                continue
            op = (180, 180)
            r = rng.random()
            if r < 0.18:
                op = (rng.uniform(95, 125), 180)
            elif r < 0.3 and s > 1:
                op = (180, rng.uniform(100, 130))
            elif r < 0.36 and s > 1:
                op = (0, 0)
            st = shutter_style if (shutters and sh == "rect") else False
            win_unit(parts, "-Y", yf, x, zb, w, h, sh, warm=RNG.random() < 0.3, shutters=st, shutter_col=shutter_col,
                     shutter_open=op, mark=(s == 1))
        parts.append(box("string", (ws + 0.16, 0.30 + jetty, 0.22), (0, yf + 0.1 + jetty / 2 - 0.12, z0 - 0.12), spale, bevel=0.03, seg=1, wonk=0.02))
        quoins(parts, ws, D, z0 + 0.12, z0 + FL, yf)
        for ax_ in (-ws / 2 + 0.75, ws / 2 - 0.75):
            wall_anchor(parts, "-Y", yf, ax_ + (bay_w * 0.5 if abs(ax_ + bay_w * 0.5) < ws / 2 - 0.6 and False else 0), z0 + FL - 0.35, kind="S" if s % 2 else "X")
        if pilasters:
            for i in range(bays + 1):
                px_ = -width / 2 + bay_w * i
                px_ = max(min(px_, width / 2 - 0.3), -width / 2 + 0.3)
                parts.append(box("pil", (0.42, 0.10, FL - 0.4), (px_, yf - 0.05, z0 + 0.15), M("plaster_white")))
                parts.append(box("pil_cap", (0.56, 0.16, 0.14), (px_, yf - 0.08, z0 + FL - 0.3), spale))
        walls.append((z0 + 1.2, yf))

    yfront = face - jetty * (storeys - 1)
    wtop = width + jetty * (storeys - 1) * 0.4
    dtop = D + jetty * (storeys - 1)
    cornice(parts, wtop, dtop, body_h - 0.05, t=0.5, proud=0.40, modillions=False)
    # the cornice is centred on the top storey mass
    for p_ in parts[-3:]:
        edit_verts(p_, lambda co: setattr(co, "y", co.y - jetty * (storeys - 1) * 0.5))
    nmod = max(4, int(wtop / 0.55))
    for i in range(nmod + 1):
        x = -wtop / 2 + wtop * i / nmod
        parts.append(box("modil", (0.12, 0.34, 0.14), (x, yfront - 0.17, body_h), stone))
    drainpipe(parts, (wtop / 2 - 0.35) * (1 if side < 0 else -1), yfront - 0.14, body_h - 0.25, walls)
    icicles(parts, (-wtop / 2 - 0.2, yfront - 0.62), (wtop / 2 + 0.2, yfront - 0.62), body_h - 0.05, maxlen=0.5, seed=seed + 1, density=2.0, gap=0.45)

    # the back wall on the outer street: casements (glass and frame on the plaster, no reveal), anchors, frost
    yb = D / 2
    for s in range(1, storeys):
        z0 = GF + FL * (s - 1)
        for x in (-width / 4, width / 4):
            if gallery and s == 1:
                continue
            parts.append(fbox("bk_glass", "+Y", yb, -x, 0.01, z0 + 0.9, 0.9, 0.02, 1.4, M("glass_warm" if rng.random() < 0.25 else "glass")))
            parts.append(fbox("bk_frame", "+Y", yb, -x, 0.03, z0 + 0.84, 1.08, 0.04, 0.08, M("wood_dark")))
            parts.append(fbox("bk_frame", "+Y", yb, -x, 0.03, z0 + 2.3, 1.08, 0.04, 0.08, M("wood_dark")))
            parts.append(fbox("bk_mull", "+Y", yb, -x, 0.03, z0 + 0.9, 0.06, 0.04, 1.4, M("wood_dark")))
            parts.append(fbox("bk_sill", "+Y", yb, -x, 0.06, z0 + 0.78, 1.2, 0.12, 0.08, stone))
            parts.append(fbox("bk_snow", "+Y", yb, -x, 0.06, z0 + 0.86, 1.1, 0.1, 0.025, M("snow")))
        wall_anchor(parts, "+Y", yb, 0.0, z0 + FL - 0.35, kind="S")
    parts.append(fbox("bk_door", "+Y", yb, width / 2 - 1.4, 0.02, 0.0, 1.1, 0.05, 2.2, M("wood_dark")))
    parts.append(fbox("bk_door_step", "+Y", yb, width / 2 - 1.4, 0.2, 0.0, 1.4, 0.4, 0.14, M("stone_dark")))
    parts.append(fbox("bk_damp", "+Y", yb, 0.0, 0.01, 0.0, width, 0.02, 0.7, M(colour + "_damp")))
    rime(parts, "+Y", yb, 0.0, body_h * 0.45, width * 0.8, body_h * 0.5, seed=seed + 5)
    if gallery:
        gallery_wood(parts, "+Y", yb, -width / 2 + 0.6, width / 2 - 0.6, GF + 0.1, d=1.2, posts=max(3, int(width / 2.6)), roof_h=2.7, seed=seed)
        for x in (-width / 4, width / 4):
            parts.append(fbox("gal_door", "+Y", yb, -x, 0.02, GF + 0.1, 0.95, 0.05, 2.1, M("wood")))

    top = body_h + 0.4
    Wr = dtop + 1.2
    yc = -jetty * (storeys - 1) * 0.5
    drifts = []
    lee = (rng.uniform(-0.4, 0.4), 1.0)

    if roof_kind == "gable":
        parts.append(roof("roof", width + 0.9, Wr, 4.6, (0, yc, top), M("tile"), sag=0.18, flare=0.16, courses=6, ridge=True))
        for x in xs[:: max(1, bays - 1)]:
            dormer(parts, x, yfront + 1.0, top + 0.55, 1.3, 1.45, plaster, M("tile_dark"), warm=RNG.random() < 0.4, snow=True)
            drifts.append((x, yfront + 3.0, 1.3, 0.16))
        cx_, cy_ = chimney(parts, width * 0.3, 1.2, top + 2.0)
        drifts.append((cx_, cy_ - 0.8, 1.2, 0.22))
        sn = roof_snow("roof_snow", width + 0.9, Wr, 4.6, (0, yc, top), sag=0.18, flare=0.16, thick=0.07, drifts=drifts, lee=lee, seed=seed + 2)
        eave_icicles(parts, width + 0.9, Wr, top - 0.02, (0, yc), seed=seed + 3, maxlen=0.55)
        roof_top = top + 4.8
    elif roof_kind == "attyka":
        aw_front = yfront - 0.05
        parts.append(box("attic_wall", (width + 0.3, dtop + 0.2 - REV, 2.3), (0, yc + REV / 2, top - 0.4), plaster, bevel=0.06, seg=1, wonk=0.03))
        blind = [(x, top + 0.0, bay_w * 0.5, 1.6, "round") for x in xs]
        parts.append(facade("attic_face", plaster, "-Y", yc - (dtop + 0.2) / 2, -(width + 0.3) / 2 - 0.01, (width + 0.3) / 2 + 0.01, top - 0.4, top + 1.9, blind))
        af = yc - (dtop + 0.2) / 2
        for x in xs:
            parts.append(box("blind_pil", (0.22, 0.08, 1.2), (x - bay_w * 0.25 - 0.14, af - 0.04, top), M("plaster_white")))
            parts.append(box("blind_pil", (0.22, 0.08, 1.2), (x + bay_w * 0.25 + 0.14, af - 0.04, top), M("plaster_white")))
            voussoirs(parts, "-Y", af, x, top + 1.6 - bay_w * 0.25, bay_w * 0.5, 0.12, M("plaster_white"), n=7, proud=0.05, key=0.08)
            parts.append(fbox("blind_snow", "-Y", af, x, -REV + 0.08, top - 0.005, bay_w * 0.5, 0.14, 0.025, M("snow")))
        parts.append(box("attic_base", (width + 0.5, 0.3, 0.2), (0, af - 0.1, top - 0.45), spale, bevel=0.03, seg=1))
        parts.append(box("coping", (width + 0.6, dtop + 0.5, 0.18), (0, yc, top + 1.9), stone, bevel=0.03, seg=1, wonk=0.02))
        parts.append(box("coping_snow", (width + 0.5, dtop + 0.4, 0.03), (0, yc, top + 2.08), M("snow"), bevel=0.01, seg=1))
        icicles(parts, (-width / 2, af - 0.15), (width / 2, af - 0.15), top + 1.9, maxlen=0.35, seed=seed + 4, density=2.2, gap=0.4)
        n = max(2, int(width / 2.2))
        py_ = af + 0.2
        for i in range(n + 1):
            x = -width / 2 + (width / n) * i
            parts.append(box("pin_base", (0.62, 0.62, 0.16), (x, py_, top + 2.08), stone, bevel=0.02, seg=1))
            parts.append(box("pin", (0.48, 0.48, 0.8), (x, py_, top + 2.24), stone, bevel=0.03, seg=1, wonk=0.02))
            parts.append(box("pin_cap", (0.6, 0.6, 0.12), (x, py_, top + 3.04), stone, bevel=0.02, seg=1))
            parts.append(box("pin_capsnow", (0.56, 0.56, 0.03), (x, py_, top + 3.16), M("snow")))
            parts.append(pyramid("pin_top", (0.34, 0.34, 0.8), (x, py_, top + 3.16), stone, apex=0.03))
            parts.append(sphere("pin_ball", 0.13, (x, py_, top + 4.05), M("gold", 0.35), seg=10, rings=6))
            snow_cap(parts, x, py_, top + 4.1, 0.1, 0.05, seg=8)
        for i in range(n):
            x = -width / 2 + (width / n) * (i + 0.5)
            parts.append(cyl("cren", (width / n) * 0.36, 0.3, (x, py_, top + 2.08), stone, verts=16, rot=(math.pi / 2, 0, 0), center=True, bevel=0.02, seg=1))
        parts.append(roof("lowroof", width, D - 1.5, 1.4, (0, 0.6, top + 1.7), M("tile_dark"), sag=0.05, flare=0.05, courses=3))
        cx_, cy_ = chimney(parts, -width * 0.25, 1.5, top + 1.5, h=2.2)
        drifts.append((cx_, cy_ - 0.7, 1.1, 0.2))
        drifts.append((0.0, af + 1.0, width, 0.12))          # snow banked up behind the parapet
        sn = roof_snow("roof_snow", width, D - 1.5, 1.4, (0, 0.6, top + 1.7), sag=0.05, flare=0.05, thick=0.08, drifts=drifts, lee=lee, seed=seed + 2, bare=0.2, slide=0.1)
        roof_top = top + 3.7
    else:  # mansard
        parts.append(roof("mansard_lo", width + 0.9, Wr, 2.8, (0, yc, top), M("tile"), sag=0.08, flare=-0.05, top_w=Wr * 0.5, courses=4))
        parts.append(roof("mansard_hi", width + 0.9, Wr * 0.5, 2.2, (0, yc, top + 2.8), M("tile_dark"), sag=0.12, flare=0.1, courses=2, ridge=True))
        for x in xs:
            dormer(parts, x, yfront + 0.05, top + 0.3, 1.2, 1.55, plaster, M("lead"), depth=1.9, warm=RNG.random() < 0.4, snow=True)
        cx_, cy_ = chimney(parts, -width * 0.3, 1.0, top + 2.6, h=2.4)
        drifts.append((cx_, cy_ - 0.7, 1.0, 0.2))
        lo = roof_snow("roof_snow_lo", width + 0.9, Wr, 2.8, (0, yc, top), sag=0.08, flare=-0.05, top_w=Wr * 0.5, thick=0.06, lee=lee, seed=seed + 6, bare=0.36, slide=0.4, minz=0.5, maxz=0.95, cell=1.2)
        if lo:
            parts.append(lo)
        sn = roof_snow("roof_snow", width + 0.9, Wr * 0.5, 2.2, (0, yc, top + 2.8), sag=0.12, flare=0.1, thick=0.07, drifts=drifts, lee=lee, seed=seed + 2)
        eave_icicles(parts, width + 0.9, Wr, top - 0.02, (0, yc), seed=seed + 3, maxlen=0.5)
        roof_top = top + 4.9
    if sn:
        parts.append(sn)

    parts.append(box("snow_c", (wtop + 0.7, dtop + 0.7, 0.035), (0, yc, body_h + 0.45), M("snow"), bevel=0.015, seg=1, wonk=0.01))

    visual = join(parts, name)
    lean_x, lean_y = RNG.uniform(-0.0125, 0.0125), RNG.uniform(-0.01, 0.0025)
    shear(visual, lean_x, lean_y)
    shear_marks(lean_x, lean_y)
    # collision: the body to the eaves and the real roof shape on top, so the roofs can be walked (parkour)
    if roof_kind == "attyka":
        col = box("col", (width + 0.2, D + jetty * (storeys - 1), top + 2.1), (0, -jetty * (storeys - 1) * 0.5, 0))
    else:
        col = join([box("col", (width + 0.2, D + jetty * (storeys - 1), top), (0, -jetty * (storeys - 1) * 0.5, 0)),
                    wedge("col_roof", (width + 0.9, Wr, 4.6 if roof_kind == "gable" else 4.9), (0, yc, top))], "col")
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
        parts.append(box("hall", (half, W - 2 * REV, H), (cx, 0, 0), plaster, bevel=0.1, seg=1, wonk=0.05))
        col.append(box("c", (half, W, H), (cx, 0, 0)))
        n = int(half / 3.4)
        xs = [cx - half / 2 + half / n * (i + 0.5) for i in range(n)]
        for face, plane, sgn in (("-Y", -W / 2, 1), ("+Y", W / 2, -1)):
            a0, a1 = sorted((sgn * (cx - half / 2), sgn * (cx + half / 2)))
            ops = [(sgn * x, 2.6, 1.5, 3.9, "round") for x in xs]
            parts.append(facade("hall_face", plaster, face, plane, a0 - 0.01, a1 + 0.01, 0.0, H, ops))
            for (a, zb, w, h, sh) in ops:
                win_unit(parts, face, plane, a, zb, w, h, sh, warm=RNG.random() < 0.5, surround=None, cross=True)
            parts.append(fbox("plinth", face, plane, sgn * cx, 0.04, 0.0, half, 0.08, 1.1, M("plaster_cream_damp"), bevel=0.02, seg=1))
            parts.append(fbox("plinth_cap", face, plane, sgn * cx, 0.07, 1.1, half, 0.14, 0.1, stone, bevel=0.02, seg=1))
    parts.append(box("gap_roof", (gap + 0.6, W, 2.2), (0, 0, H - 2.2), plaster, bevel=0.06, seg=1))
    for sy in (-1, 1):
        parts.append(arch("gap_arch", gap + 0.5, 6.4, 0.5, (0, sy * (W / 2 - 0.05), 0), stone, bevel=0.04, seg=1))
        parts.append(arch("gap_void", gap - 0.4, 5.9, 0.6, (0, sy * (W / 2 - 0.05), 0), M("void"), bevel=0))
        voussoirs(parts, "-Y" if sy < 0 else "+Y", sy * (W / 2 + 0.2), 0, 5.9 - (gap - 0.4) / 2, gap - 0.4, 0.45, stone, n=9, proud=0.1, key=0.2)
    col.append(box("c", (gap + 0.6, W, 2.2), (0, 0, H - 2.2)))

    cornice(parts, L, W, H - 0.1, t=0.5, proud=0.35, modillions=False)
    for sy in (-1, 1):
        for i in range(int(L / 0.6) + 1):
            parts.append(box("modil", (0.12, 0.3, 0.14), (-L / 2 + i * 0.6, sy * (W / 2 + 0.15), H - 0.05), stone))
    A0 = H + 0.3
    AW = W + 0.4
    parts.append(box("attic", (L + 0.4, AW - 2 * REV, 2.6), (0, 0, A0), plaster, bevel=0.06, seg=1, wonk=0.03))
    n = 15
    step = L / n
    for face, plane, sgn in (("-Y", -AW / 2, 1), ("+Y", AW / 2, -1)):
        ops = [(sgn * (-L / 2 + step * (i + 0.5)), A0 + 0.35, step * 0.42, 1.7, "round") for i in range(n)]
        parts.append(facade("attic_face", plaster, face, plane, -(L + 0.4) / 2 - 0.01, (L + 0.4) / 2 + 0.01, A0, A0 + 2.6, ops))
    for sx in (-1, 1):
        parts.append(box("attic_end", (0.02, AW, 2.6), (sx * (L / 2 + 0.2), 0, A0), plaster))
    parts.append(box("attic_cop", (L + 0.8, AW + 0.3, 0.2), (0, 0, A0 + 2.6), stone, bevel=0.03, seg=1, wonk=0.02))
    parts.append(box("attic_snow", (L + 0.7, AW + 0.2, 0.06), (0, 0, A0 + 2.8), M("snow"), bevel=0.02, seg=1))
    for i in range(n + 1):
        x = -L / 2 + step * i
        for sy in (-1, 1):
            y = sy * (W / 2 + 0.25)
            parts.append(box("pin", (0.5, 0.5, 1.0), (x, y, A0 + 2.8), stone, bevel=0.03, seg=1, wonk=0.02))
            parts.append(box("pin_cap", (0.62, 0.62, 0.12), (x, y, A0 + 3.8), stone, bevel=0.02, seg=1))
            parts.append(pyramid("pin_top", (0.36, 0.36, 0.9), (x, y, A0 + 3.92), stone, apex=0.03))
            parts.append(sphere("ball", 0.16, (x, y, A0 + 4.95), M("gold", 0.35), seg=10, rings=6))
    for i in range(n):
        x = -L / 2 + step * (i + 0.5)
        for sy in (-1, 1):
            y = sy * (W / 2 + 0.25)
            parts.append(cyl("cren", step * 0.40, 0.4, (x, y, A0 + 2.8), stone, verts=16, rot=(math.pi / 2, 0, 0), center=True, bevel=0.02, seg=1))
            parts.append(blob("mascaron", (0.46, 0.3, 0.56), (x + step * 0.5, y - sy * 0.12, A0 + 1.0), M("stone_dark"), subsurf=1))
    parts.append(roof("roof", L - 0.5, W - 1.2, 2.2, (0, 0, A0 + 2.4), M("tile_dark"), sag=0.1, flare=0.05, courses=3, ridge=True))

    for sx in (-1, 1):
        x0 = sx * (L / 2 + 1.5)
        for j in range(4):
            y = -W / 2 + (W / 3) * j
            parts.append(cyl("colm", 0.36, 4.6, (x0 + sx * 1.2, y, 0.35), stone, verts=16, r2=0.30, bevel=0.02, seg=1))
            parts.append(box("colcap", (0.95, 0.95, 0.25), (x0 + sx * 1.2, y, 4.95), stone, bevel=0.04, seg=1, wonk=0.02))
            parts.append(cyl("colcap2", 0.42, 0.18, (x0 + sx * 1.2, y, 4.78), stone, verts=16, r2=0.5))
            parts.append(box("colbase", (0.9, 0.9, 0.35), (x0 + sx * 1.2, y, 0), stone, bevel=0.03, seg=1))
            col.append(box("c", (0.7, 0.7, 5.0), (x0 + sx * 1.2, y, 0)))
        parts.append(box("logroof", (3.4, W + 0.5, 0.8), (x0, 0, 5.2), stone, bevel=0.05, seg=1, wonk=0.02))
        parts.append(box("logbal", (3.4, W + 0.5, 0.9), (x0, 0, 6.0), plaster, bevel=0.05, seg=1, wonk=0.02))
        for j in range(3):
            y = -W / 2 + (W / 3) * (j + 0.5)
            parts.append(arch("logarch", W / 3 - 0.9, 2.0, 3.4, (x0, y, 3.3), M("void"), rot_z=math.pi / 2, bevel=0))
        col.append(box("c", (3.4, W + 0.5, 1.7), (x0, 0, 5.2)))

    for sy in (-1, 1):
        for i in range(-2, 3):
            if i == 0:
                continue
            x = i * 6.0 + (1.5 if i < 0 else -1.5)
            y = sy * (W / 2 + 1.0)
            parts.append(box("kram", (3.0, 1.9, 2.3), (x, y, 0), M("wood"), bevel=0.03, seg=1, wonk=0.04))
            parts.append(roof("kram_roof", 3.5, 2.4, 0.9, (x, y, 2.3), M("tile_dark"), sag=0.04, flare=0.1, cuts=3, courses=2))
            parts.append(box("kram_shut", (2.4, 0.08, 1.2), (x, y + sy * 0.98, 0.9), M("wood_dark"), bevel=0.02, seg=1))
            parts.append(box("kram_sill", (2.6, 0.4, 0.08), (x, y + sy * 1.1, 0.85), M("wood_dark"), bevel=0.01, seg=1))
            col.append(box("c", (3.0, 1.9, 2.3), (x, y, 0)))

    parts.append(box("snow", (L + 0.8, W + 0.8, 0.04), (0, 0, H + 0.35), M("snow"), bevel=0.015, seg=1, wonk=0.01))
    parts.append(roof_snow("roof_snow", L - 0.5, W - 1.2, 2.2, (0, 0, A0 + 2.4), sag=0.1, flare=0.05, thick=0.08, seed=61, cell=1.4, bare=0.18, slide=0.1))
    for sy in (-1, 1):
        icicles(parts, (-L / 2, sy * (AW / 2 + 0.2)), (L / 2, sy * (AW / 2 + 0.2)), A0 + 2.6, maxlen=0.4, seed=62 + sy, density=1.6, gap=0.5)
        icicles(parts, (-L / 2, sy * (W / 2 + 0.55)), (L / 2, sy * (W / 2 + 0.55)), H - 0.1, maxlen=0.55, seed=64 + sy, density=1.4, gap=0.5)
        for i in range(n + 1):
            snow_cap(parts, -L / 2 + step * i, sy * (W / 2 + 0.25), A0 + 5.07, 0.13, 0.06, seg=6)
        for i in range(-2, 3):
            if i == 0:
                continue
            x = i * 6.0 + (1.5 if i < 0 else -1.5)
            sn = roof_snow("kram_snow", 3.5, 2.4, 0.9, (x, sy * (W / 2 + 1.0), 2.3), sag=0.04, flare=0.1, cuts=3, thick=0.05, cell=0.6, seed=66 + i, slide=0.0)
            if sn:
                parts.append(sn)
            icicles(parts, (x - 1.6, sy * (W / 2 + 2.2)), (x + 1.6, sy * (W / 2 + 2.2)), 2.28, maxlen=0.3, seed=70 + i, density=2.5)
    for sx in (-1, 1):
        x0 = sx * (L / 2 + 1.5)
        parts.append(box("log_snow", (3.3, W + 0.4, 0.035), (x0, 0, 6.9), M("snow")))
    # climbing: drainpipes up the long walls to the cornice, the market booths' roofs, a wall-walk inside the attic
    # and its coping (the parapet a thief can crouch behind)
    for sy in (-1, 1):
        for x in (-11.0, 11.0):
            drainpipe(parts, x, sy * (W / 2 + 0.15), H - 0.2, [(2.0, sy * W / 2), (5.0, sy * W / 2)])
        climb("ledge", (L + 0.8, 0.9, 0.3), (0, sy * (AW / 2), A0 + 2.75))
        climb("ledge", (L, 1.2, 0.2), (0, sy * (AW / 2 - 0.9), 8.5))
        for i in range(-2, 3):
            if i == 0:
                continue
            x = i * 6.0 + (1.5 if i < 0 else -1.5)
            climb("mantle", (3.5, 2.4, 0.25), (x, sy * (W / 2 + 1.0), 2.85))
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
    front = -NL / 2 + 2
    parts.append(box("nave", (NW - 2 * REV, NL - REV, NH), (0, 2 + REV / 2, 0), brick, bevel=0.1, seg=1, wonk=0.04))
    col.append(box("c", (NW, NL, NH), (0, 2, 0)))
    # clerestory: tall pointed windows above the aisle roofs, recessed into the nave walls
    ys = [-NL / 2 + 4 + (NL - 2) / 5 * (j + 0.5) for j in range(5)]
    for face, plane, sgn in (("-X", -NW / 2, -1), ("+X", NW / 2, 1)):
        ops = [(sgn * y, NH * 0.6 + 2.0, 1.6, 4.4, "pointed") for y in ys]
        parts.append(facade("clere", brick, face, plane, -NL / 2 + 2 - 0.01 if sgn > 0 else -(NL / 2 + 2) - 0.01,
                            NL / 2 + 2 + 0.01 if sgn > 0 else NL / 2 - 2 + 0.01, NH * 0.6 + 0.3, NH, ops))
        for (a, zb, w, h, sh) in ops:
            win_unit(parts, face, plane, a, zb, w, h, sh, surround=None, sill=True, cross=True, snow=True, glass="glass_stained", tracery=True)
    for sx in (-1, 1):
        face = "-X" if sx < 0 else "+X"
        plane = sx * (NW / 2 + 3.0)
        parts.append(box("aisle", (3.0 - REV, NL - 2, NH * 0.6), (sx * (NW / 2 + 1.5 - REV / 2), 2, 0), brick, bevel=0.08, seg=1, wonk=0.04))
        col.append(box("c", (3.0, NL - 2, NH * 0.6), (sx * (NW / 2 + 1.5), 2, 0)))
        ops = [(sx * y, 2.0, 1.7, 7.2, "pointed") for y in ys]
        a0, a1 = sorted((sx * (-NL / 2 + 3), sx * (NL / 2 + 1)))
        parts.append(facade("aisle_face", brick, face, plane, a0 - 0.01, a1 + 0.01, 0.0, NH * 0.6, ops))
        for (a, zb, w, h, sh) in ops:
            win_unit(parts, face, plane, a, zb, w, h, sh, surround=None, cross=True, glass="glass_stained", tracery=True)
        parts.append(fbox("aisle_plinth", face, plane, sx * 2, 0.06, 0, NL - 2, 0.12, 0.8, M("stone_dark"), bevel=0.02, seg=1))
        parts.append(roof("aisle_roof", NL - 2, 3.6, 2.2, (sx * (NW / 2 + 1.5), 2, NH * 0.6), M("tile"), sag=0.05, flare=0.05, along_x=False, courses=2))
        for j in range(6):
            y = -NL / 2 + 4 + (NL - 2) / 5 * j
            parts.append(taper_box("buttress", (1.4, 1.2, NH * 0.62), (sx * (NW / 2 + 3.5), y, 0), bdark, top=0.55, bevel=0.04, seg=1, wonk=0.03))
            parts.append(pyramid("butt_cap", (0.9, 0.8, 0.8), (sx * (NW / 2 + 3.5) - sx * 0.15, y, NH * 0.62), stone))
            col.append(box("c", (1.4, 1.2, NH * 0.62), (sx * (NW / 2 + 3.5), y, 0)))
    parts.append(roof("roof", NL, NW + 0.8, 9.5, (0, 2, NH), M("tile_dark"), sag=0.2, flare=0.12, along_x=False, courses=6, ridge=True))
    parts.append(cyl("apse", NW / 2 - 1, NH - 3, (0, NL / 2 + 2, 0), brick, verts=10, bevel=0.06, seg=1))
    col.append(cyl("c", NW / 2 - 1, NH - 3, (0, NL / 2 + 2, 0), None, verts=8))
    parts.append(cyl("apse_roof", NW / 2 - 0.8, 5, (0, NL / 2 + 2, NH - 3), M("tile_dark"), verts=10, r2=0.2, bevel=0.02, seg=1))
    for k in range(5):
        a = math.pi * (k + 0.5) / 5
        bx, by = (NW / 2 - 0.6) * math.cos(a), NL / 2 + 2 + (NW / 2 - 0.6) * math.sin(a)
        parts.append(taper_box("apse_butt", (1.1, 1.1, NH - 4), (bx, by, 0), bdark, top=0.6, bevel=0.03, seg=1))
    # the presbytery's tall east windows: stained glass with a stone mullion and an oculus, lit from within
    for k in range(4):
        wa = math.pi * (k + 1) / 5
        wr = (NW / 2 - 1) * math.cos(math.pi / 10) + 0.02
        wx, wy = wr * math.cos(wa), NL / 2 + 2 + wr * math.sin(wa)
        pw = 1.5
        rot_panel(parts, "apse_glass", wx, wy, wa, outline(0.0, 4.2, pw, 8.0, "pointed"), -0.02, 0.02, M("glass_stained"))
        rot_panel(parts, "apse_rev", wx, wy, wa, [(-pw / 2 - 0.2, 4.0), (pw / 2 + 0.2, 4.0)] + outline(0.0, 4.0, pw + 0.4, 8.4, "pointed")[2:], 0.0, 0.08, bdark)
        rot_panel(parts, "apse_glass2", wx, wy, wa, outline(0.0, 4.2, pw, 8.0, "pointed"), 0.081, 0.09, M("glass_stained"))
        rot_panel(parts, "apse_mull", wx, wy, wa, [(-0.05, 4.2), (0.05, 4.2), (0.05, 10.8), (-0.05, 10.8)], 0.08, 0.2, stone)
        rot_panel(parts, "apse_tr", wx, wy, wa, [(-pw / 2, 7.4), (pw / 2, 7.4), (pw / 2, 7.5), (-pw / 2, 7.5)], 0.08, 0.18, stone)
        rot_panel(parts, "apse_sill", wx, wy, wa, [(-pw / 2 - 0.25, 4.0), (pw / 2 + 0.25, 4.0), (pw / 2 + 0.25, 4.15), (-pw / 2 - 0.25, 4.15)], 0.0, 0.3, stone)
        rot_panel(parts, "apse_sillsnow", wx, wy, wa, [(-pw / 2 - 0.2, 4.15), (pw / 2 + 0.2, 4.15), (pw / 2 + 0.2, 4.18), (-pw / 2 - 0.2, 4.18)], 0.05, 0.28, M("snow"))

    # west front between the towers: a tall pointed window over the stepped portal
    fo = [(0.0, 8.8, 3.0, 7.6, "pointed")]
    parts.append(facade("west", brick, "-Y", front, -2.45, 2.45, 0.0, NH, fo))
    win_unit(parts, "-Y", front, 0.0, 8.8, 3.0, 7.6, "pointed", surround=None, cross=True, glass="glass_stained", tracery=True)
    for x in (-5.5, 5.5):
        tall = x < 0
        TH = 30.0 if tall else 25.0
        tf = front - 1.0 - 3.1
        parts.append(box("tower", (6.2 - REV, 6.2 - REV, TH), (x + (REV / 2 if tall else -REV / 2), front - 1.0 + REV / 2, 0), brick, bevel=0.1, seg=1, wonk=0.04))
        col.append(box("c", (6.2, 6.2, TH), (x, front - 1.0, 0)))
        zz_list = (8, 16, 24) if tall else (8, 14)
        ops = [(x, zz, 1.5, 4.2, "pointed") for zz in zz_list]
        parts.append(facade("tower_f", brick, "-Y", tf, x - 3.11, x + 3.11, 0.0, TH, ops))
        for (a, zb, w, h, sh) in ops:
            win_unit(parts, "-Y", tf, a, zb, w, h, sh, surround=None, cross=False, louvre=zb == zz_list[-1])
        sface, splane = ("-X", x - 3.1) if tall else ("+X", x + 3.1)
        sa = -(front - 1.0) if tall else (front - 1.0)
        sops = [(sa, zz, 1.4, 4.0, "pointed") for zz in zz_list]
        parts.append(facade("tower_s", brick, sface, splane, sa - 3.11, sa + 3.11, 0.0, TH, sops))
        for (a, zb, w, h, sh) in sops:
            win_unit(parts, sface, splane, a, zb, w, h, sh, surround=None, cross=False, louvre=zb == zz_list[-1])
        for zz in [z - 0.6 for z in zz_list] + [TH - 0.4]:
            parts.append(box("band", (6.5, 6.5, 0.25), (x, front - 1.0, zz), stone, bevel=0.03, seg=1))
        for cx_ in (x - 3.1, x + 3.1):
            parts.append(taper_box("t_butt", (1.0, 1.0, TH * 0.55), (cx_, tf - 0.2, 0), bdark, top=0.55, bevel=0.03, seg=1, wonk=0.02))
            parts.append(taper_box("t_butt2", (0.6, 0.6, TH * 0.25), (cx_, tf - 0.05, TH * 0.55), bdark, top=0.5, bevel=0.02, seg=1))
    x = -NW / 2 + 1.5
    parts.append(cyl("tn_oct", 3.5, 7.0, (x, front - 1.0, 30.0), brick, verts=8, bevel=0.05, seg=1))
    for k in range(8):
        a = math.tau * k / 8
        parts.append(box("tn_pin", (0.55, 0.55, 2.0), (x + 3.3 * math.cos(a), front - 1.0 + 3.3 * math.sin(a), 36.0), stone, bevel=0.03, seg=1))
        parts.append(cyl("tn_pintop", 0.4, 1.2, (x + 3.3 * math.cos(a), front - 1.0 + 3.3 * math.sin(a), 38.0), stone, verts=8, r2=0.05, bevel=0.02, seg=1))
    parts.append(cyl("tn_spire", 3.1, 13.5, (x, front - 1.0, 37.0), M("lead", 0.5), verts=16, r2=0.06, bevel=0.02, seg=1))
    parts.append(torus("tn_crown", 2.5, 0.28, (x, front - 1.0, 40.8), M("gold", 0.35)))
    for k in range(8):
        a = math.tau * k / 8
        parts.append(cyl("tn_crownpt", 0.22, 1.1, (x + 2.4 * math.cos(a), front - 1.0 + 2.4 * math.sin(a), 40.9), M("gold", 0.35), verts=6, r2=0.03, bevel=0))
    for k in range(4):
        a = math.tau * k / 4 + math.pi / 4
        parts.append(cyl("tn_turret", 0.7, 4.5, (x + 3.6 * math.cos(a), front - 1.0 + 3.6 * math.sin(a), 34.5), M("lead", 0.5), verts=8, r2=0.03, bevel=0))
    x = NW / 2 - 1.5
    parts.append(cyl("ts_drum", 3.3, 2.6, (x, front - 1.0, 25.0), stone, verts=16, bevel=0.04, seg=1))
    parts.append(sphere("ts_dome", 3.5, (x, front - 1.0, 27.6), M("patina"), seg=24, rings=14, zscale=0.95))
    parts.append(cyl("ts_lantern", 1.0, 2.6, (x, front - 1.0, 30.6), stone, verts=10, bevel=0.03, seg=1))
    parts.append(cyl("ts_lantop", 1.3, 1.8, (x, front - 1.0, 33.2), M("patina"), verts=10, r2=0.05, bevel=0.02, seg=1))
    parts.append(cyl("ts_clock", 1.3, 0.25, (x, front - 4.2, 20.0), M("plaster_white"), verts=24, rot=(math.pi / 2, 0, 0), center=True, bevel=0.02, seg=1))
    parts.append(torus("ts_clockrim", 1.3, 0.1, (x, front - 4.3, 20.0), M("gold", 0.4), rot=(math.pi / 2, 0, 0), seg=24, mseg=6))
    parts.append(arch("portal", 4.4, 8.0, 0.7, (0, front - 0.35, 0), stone, bevel=0.05, seg=1))
    parts.append(arch("portal2", 3.6, 7.4, 0.5, (0, front - 0.45, 0), M("stone_dark"), bevel=0.04, seg=1))
    parts.append(arch("door", 2.9, 6.8, 0.3, (0, front - 0.55, 0), M("wood_dark"), bevel=0.02, seg=1))
    for zz in (1.2, 3.0, 4.8):
        parts.append(box("dstrap", (2.6, 0.04, 0.1), (0, front - 0.72, zz), M("iron")))
    parts.append(box("dsplit", (0.06, 0.04, 5.3), (0, front - 0.72, 0), M("iron")))
    parts.append(roof("gable", 1.2, NW + 0.8, 9.5, (0, front + 0.6, NH), bdark, sag=0.0, flare=0.12, cuts=2, along_x=False))
    parts.append(box("snow", (NW + 0.8, NL, 0.04), (0, 2, NH + 0.02), M("snow"), bevel=0.015, seg=1))
    # winter: a blanket on the great roof (thicker on the lee side), the aisles, the apse cone, the helm dome's ribs
    parts.append(roof_snow("roof_snow", NL, NW + 0.8, 9.5, (0, 2, NH), sag=0.2, flare=0.12, along_x=False, thick=0.08,
                           lee=(1.0, 0.2), seed=31, cell=1.3, bare=0.2))
    eave_icicles(parts, NL - 1.0, NW + 0.8, NH - 0.02, (0, 2), along_x=False, seed=32, maxlen=0.8, density=1.6)
    for sx in (-1, 1):
        sn = roof_snow("aisle_snow", NL - 2, 3.6, 2.2, (sx * (NW / 2 + 1.5), 2, NH * 0.6), sag=0.05, flare=0.05, along_x=False,
                       thick=0.07, seed=33 + sx, cell=1.0, lee=(-sx, 0.0), drifts=[(sx * (NW / 2 + 0.2), 2 + dy, 1.5, 0.12) for dy in (-10, 0, 10)])
        if sn:
            parts.append(sn)
        eave_icicles(parts, NL - 3, 3.6, NH * 0.6 - 0.02, (sx * (NW / 2 + 1.5), 2), along_x=False, sides=(sx,), seed=35 + sx, maxlen=0.6)
    sn = cap_snow("apse_snow", lambda: cyl("tmp", NW / 2 - 0.8, 5, (0, NL / 2 + 2, NH - 3), None, verts=10, r2=0.2), thick=0.07, cell=0.9, bare=0.25, slide=0.3)
    if sn:
        parts.append(sn)
    xd = NW / 2 - 1.5
    dome_ribs(parts, xd, front - 1.0, 27.6, 3.5, n=8, zscale=0.95, mat=M("patina"), z_from=0.2)
    sn = cap_snow("dome_snow", lambda: sphere("tmp", 3.5, (xd, front - 1.0, 27.6), None, seg=24, rings=14, zscale=0.95), minz=0.62, thick=0.06, cell=0.6, bare=0.2)
    if sn:
        parts.append(sn)
    snow_cap(parts, xd, front - 1.0, 33.1, 1.1, 0.12)
    visual = join(parts, "st_marys")
    export("st_marys", visual, join(col, "col"))


# ------------------------------------------------------------------ TOWN HALL (Ratusz, before 1820)
def town_hall():
    reset()
    parts, col, tower = [], [], []
    brick = M("brick")
    stone = M("stone")
    white = M("plaster_white")
    parts.append(box("hall", (16.0, 8.0 - REV, 9.0), (-9.0, REV / 2, 0), white, bevel=0.1, seg=1, wonk=0.05))
    col.append(box("c", (16.0, 8.0, 9.0), (-9.0, 0, 0)))
    parts.append(roof("hall_roof", 16.8, 9.0, 4.4, (-9.0, 0, 9.0), M("tile"), sag=0.15, flare=0.12, courses=5, ridge=True))
    xs = [-15.5 + 4.0 * i for i in range(4)]
    ops = [(x, 1.4, 1.2, 2.5, "round") for x in xs] + [(x, 5.4, 1.2, 2.1, "rect") for x in xs]
    parts.append(facade("hall_face", white, "-Y", -4.0, -17.01, -0.99, 0.0, 9.0, ops))
    for (a, zb, w, h, sh) in ops:
        win_unit(parts, "-Y", -4.0, a, zb, w, h, sh, warm=sh == "round", shutters=sh == "rect", surround="stone_pale" if sh == "rect" else None)
    quoins(parts, 16.0, 8.0, 1.0, 9.0, -4.0, cx=-9.0)
    parts.append(box("plinth", (16.0, 0.12, 1.0), (-9.0, -4.04, 0), M("plaster_white_damp"), bevel=0.02, seg=1))
    parts.append(box("string", (16.1, 0.24, 0.2), (-9.0, -4.08, 4.5), stone, bevel=0.02, seg=1))
    cornice(parts, 16.0, 8.0, 8.8, t=0.4, proud=0.3, modillions=False)
    for p_ in parts[-3:]:
        edit_verts(p_, lambda co: setattr(co, "x", co.x - 9.0))
    drainpipe(parts, -16.6, -4.2, 8.6, [(1.5, -4.0), (4.8, -4.0), (7.5, -4.0)])
    parts.append(roof_snow("hall_snow", 16.8, 9.0, 4.4, (-9.0, 0, 9.0), sag=0.15, flare=0.12, thick=0.07, seed=42, lee=(0.2, 1.0),
                           drifts=[(-14.0, 1.0, 1.2, 0.2)]))
    eave_icicles(parts, 16.8, 9.0, 8.98, (-9.0, 0), seed=43, maxlen=0.6)
    chimney(parts, -14.0, 1.8, 11.0, h=2.2)
    for x in xs:
        mark_window("-Y", -4.0, x, 1.4)

    tower.append(box("tower", (7.0, 7.0 - REV, 24.0), (0, REV / 2, 0), brick, bevel=0.1, seg=1, wonk=0.04))
    col.append(box("c", (7.0, 7.0, 24.0), (0, 0, 0)))
    tops = [(0, zz, 1.2, 3.0, "round") for zz in (6, 12, 18)]
    tower.append(facade("tower_f", brick, "-Y", -3.5, -3.51, 3.51, 3.0, 24.0, tops))
    for (a, zb, w, h, sh) in tops:
        win_unit(tower, "-Y", -3.5, a, zb, w, h, sh, surround=None, cross=False)
    tower.append(box("tower_base", (7.8, 7.8 - 0.4 - REV, 3.0), (0, (0.4 + REV) / 2, 0), stone, bevel=0.06, seg=1, wonk=0.03))
    tower.append(facade("base_f", stone, "-Y", -3.9, -3.91, 3.91, 0.0, 3.0, [(0, 0.0, 1.5, 1.9 + 0.12 + 0.75, "round")]))
    door_unit(tower, "-Y", -3.9, 0.0, 1.5, 1.9, portal=False)
    voussoirs(tower, "-Y", -3.9, 0.0, 1.9 + 0.12, 1.5, 0.2, M("stone_pale"), n=7, proud=0.1, key=0.1)
    for zz in (5.4, 11.4, 17.4, 23.6):
        tower.append(box("band", (7.3, 7.3, 0.22), (0, 0, zz), stone, bevel=0.03, seg=1))
    for k in range(4):
        a = math.tau * k / 4
        cx, cy = 3.6 * math.sin(a), -3.6 * math.cos(a)
        tower.append(cyl("clock", 1.5, 0.3, (cx, cy, 20.5), white, verts=24, rot=(math.pi / 2, 0, a), center=True, bevel=0.02, seg=1))
        tower.append(torus("clockrim", 1.5, 0.12, (cx * 1.03, cy * 1.03, 20.5), M("gold", 0.4), rot=(math.pi / 2, 0, a)))
    tower.append(cyl("drum", 3.7, 3.0, (0, 0, 24.0), stone, verts=8, bevel=0.05, seg=1))
    tower.append(sphere("onion", 3.7, (0, 0, 28.6), M("patina"), seg=24, rings=14, zscale=1.15))
    tower.append(cyl("onion_neck", 1.4, 2.2, (0, 0, 31.9), stone, verts=10, bevel=0.03, seg=1))
    tower.append(sphere("onion2", 1.7, (0, 0, 34.7), M("patina"), seg=20, rings=12, zscale=1.2))
    tower.append(cyl("spike", 0.18, 3.0, (0, 0, 36.3), M("gold", 0.4), verts=8, r2=0.02, bevel=0))
    tower.append(sphere("ball", 0.5, (0, 0, 37.8), M("gold", 0.4), seg=12, rings=8))
    tower.append(box("snow", (7.4, 7.4, 0.1), (0, 0, 24.0), M("snow"), bevel=0.03, seg=1))
    for k in range(4):
        a = math.tau * k / 4
        n = Vector((math.sin(a), -math.cos(a), 0.0))
        clock_face(tower, Vector((0, 0, 20.5)) + n * 3.75, n, 1.5, hh=11, mm=50)
    rustication(tower, "-Y", -3.9, -3.9, 3.9, 0.2, 2.9, [(0.0, 0.0, 1.5, 2.65, "round")], course=0.45, proud=0.04, mat=stone)
    for face_, plane_ in (("-X", -3.9), ("+X", 3.9), ("+Y", 3.9)):
        rustication(tower, face_, plane_, -3.9, 3.9, 0.2, 2.9, [], course=0.45, proud=0.04, mat=stone)
    dome_ribs(tower, 0, 0, 28.6, 3.7, n=8, zscale=1.15, mat=M("gold", 0.4), z_from=-0.5, width=0.06)
    sn = cap_snow("onion_snow", lambda: sphere("tmp", 3.7, (0, 0, 28.6), None, seg=24, rings=14, zscale=1.15), minz=0.6, thick=0.06, cell=0.6, bare=0.2)
    if sn:
        tower.append(sn)
    sn = cap_snow("onion2_snow", lambda: sphere("tmp", 1.7, (0, 0, 34.7), None, seg=20, rings=12, zscale=1.2), minz=0.65, thick=0.04, cell=0.4, bare=0.15)
    if sn:
        tower.append(sn)
    icicles(tower, (-3.7, -3.72), (3.7, -3.72), 23.9, maxlen=0.5, seed=41, density=1.8)
    t = join(tower, "tower")
    shear(t, 0.006, 0.004)          # the real tower leans; it still does
    parts.append(t)
    visual = join(parts, "town_hall")
    export("town_hall", visual, join(col, "col"))


# ------------------------------------------------------------------ ST ADALBERT'S
def st_adalbert():
    reset()
    parts, col = [], []
    white = M("plaster_white")
    parts.append(box("body", (7.0 - 2 * REV, 7.0 - REV, 5.0), (0, REV / 2, 0), white, bevel=0.1, seg=1, wonk=0.06))
    col.append(box("c", (7.0, 7.0, 5.0), (0, 0, 0)))
    ops = [(0.0, 0.0, 1.4, 2.4 + 0.12 + 0.7, "round"), (-2.3, 2.0, 0.8, 1.8, "round"), (2.3, 2.0, 0.8, 1.8, "round")]
    parts.append(facade("front", white, "-Y", -3.5, -3.51, 3.51, 0.0, 5.0, ops))
    door_unit(parts, "-Y", -3.5, 0.0, 1.4, 2.4, portal=True)
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", -3.5, a, zb, w, h, sh, warm=True, surround=None)
    for face, plane in (("-X", -3.5), ("+X", 3.5)):
        sops = [(0.0, 2.0, 0.8, 1.8, "round")]
        parts.append(facade("side", white, face, plane, -3.49, 3.49, 0.0, 5.0, sops))
        win_unit(parts, face, plane, 0.0, 2.0, 0.8, 1.8, "round", warm=True, surround=None)
    parts.append(box("base_back", (7.6, 3.8, 1.0), (0, 1.9, 0), M("stone_dark"), bevel=0.05, seg=1, wonk=0.03))
    plinth(parts, -3.8, 3.8, -3.5, h=1.0, proud=0.3, mat=M("stone_dark"), skip=[(-1.3, 1.3)])
    for sx in (-1, 1):
        parts.append(box("base_side", (0.3, 3.9, 1.0), (sx * 3.65, -1.6, 0), M("stone_dark"), bevel=0.03, seg=1))
    cornice(parts, 7.0, 7.0, 4.9, t=0.35, proud=0.2, modillions=False)
    parts.append(cyl("drum", 3.6, 2.2, (0, 0, 5.0), white, verts=16, bevel=0.05, seg=1))
    for k in range(8):
        a = math.tau * (k + 0.5) / 8
        parts.append(cbox("drum_win", (0.7, 0.1, 1.1), (3.58 * math.cos(a), 3.58 * math.sin(a), 6.1), M("glass"), rot=(0, 0, a + math.pi / 2)))
    parts.append(sphere("dome", 3.8, (0, 0, 7.4), M("patina"), seg=24, rings=14, zscale=0.85))
    parts.append(cyl("lantern", 0.9, 1.6, (0, 0, 10.4), white, verts=10, bevel=0.03, seg=1))
    parts.append(cyl("lantop", 1.2, 1.3, (0, 0, 12.0), M("patina"), verts=10, r2=0.03, bevel=0.02, seg=1))
    parts.append(box("snow", (7.3, 7.3, 0.04), (0, 0, 5.3), M("snow"), bevel=0.015, seg=1))
    dome_ribs(parts, 0, 0, 7.4, 3.8, n=12, zscale=0.85, mat=M("patina"), z_from=0.1, width=0.06)
    sn = cap_snow("dome_snow", lambda: sphere("tmp", 3.8, (0, 0, 7.4), None, seg=24, rings=14, zscale=0.85), minz=0.6, thick=0.06, cell=0.6, bare=0.22, lee=(1, 0))
    if sn:
        parts.append(sn)
    snow_cap(parts, 0, 0, 12.0, 1.15, 0.1)
    icicles(parts, (-3.7, -3.72), (3.7, -3.72), 4.95, maxlen=0.45, seed=51)
    visual = join(parts, "st_adalbert")
    export("st_adalbert", visual, join(col, "col"))


# ------------------------------------------------------------------ street furniture
def market_stall():
    reset()
    parts = [box("counter", (2.4, 1.2, 1.1), (0, 0, 0), M("wood"), bevel=0.03, seg=1, wonk=0.04),
             box("counter_top", (2.7, 1.5, 0.10), (0, 0, 1.1), M("wood_dark"), bevel=0.02, seg=1, wonk=0.02)]
    for x in (-1.15, 1.15):
        for y in (-0.55, 0.55):
            parts.append(cyl("post", 0.07, 2.4, (x, y, 0), M("wood_dark"), verts=8, bevel=0.01, seg=1))
    parts.append(roof("awning", 3.0, 2.0, 0.7, (0, 0, 2.3), M("canvas"), sag=0.12, flare=0.25, cuts=4, bevel=0.02))
    for i in range(3):
        parts.append(box("stripe", (0.3, 1.9, 0.03), (-0.9 + i * 0.9, 0, 2.31), M("canvas_stripe"), bevel=0))
    parts.append(blob("sack", (0.55, 0.45, 0.45), (-0.7, 0.1, 1.18), M("canvas")))
    parts.append(box("crate", (0.6, 0.45, 0.35), (0.6, 0.1, 1.18), M("wood_dark"), bevel=0.02, seg=1, wonk=0.02))
    parts.append(blob("loaf", (0.3, 0.2, 0.15), (0.0, 0.2, 1.18), M("zupan_gold")))
    export("market_stall", join(parts, "market_stall"), box("c", (2.4, 1.2, 1.1), (0, 0, 0)))


def barrel():
    reset()
    parts = [cyl("lo", 0.38, 0.5, (0, 0, 0), M("wood"), verts=16, r2=0.47, bevel=0.01, seg=1),
             cyl("hi", 0.47, 0.5, (0, 0, 0.5), M("wood"), verts=16, r2=0.38, bevel=0.01, seg=1)]
    for z in (0.12, 0.82):
        parts.append(cyl("hoop", 0.46, 0.07, (0, 0, z), M("iron", 0.5), verts=16, r2=0.46, bevel=0.01, seg=1))
    parts.append(cyl("hoopm", 0.49, 0.07, (0, 0, 0.47), M("iron", 0.5), verts=16, bevel=0.01, seg=1))
    parts.append(cyl("snow", 0.36, 0.05, (0, 0, 1.0), M("snow"), verts=16, bevel=0.01, seg=1))
    export("barrel", join(parts, "barrel"), cyl("c", 0.47, 1.0, (0, 0, 0), None, verts=8))


def crate_stack():
    reset()
    parts = [box("c1", (1.0, 0.8, 0.6), (0, 0, 0), M("wood"), bevel=0.02, seg=1, wonk=0.02),
             box("c2", (0.8, 0.8, 0.5), (0.1, 0.05, 0.6), M("wood_dark"), bevel=0.02, seg=1, wonk=0.02, rot=(0, 0, 0.15)),
             box("c3", (0.9, 0.7, 0.55), (1.0, 0.1, 0), M("wood"), bevel=0.02, seg=1, wonk=0.02)]
    for (x, y, z, sx, sy) in ((0, 0, 0.6, 1.0, 0.8), (1.0, 0.1, 0.55, 0.9, 0.7)):
        parts.append(box("slat", (sx + 0.02, 0.04, 0.06), (x, y - sy / 2, z - 0.25), M("wood_dark")))
    export("crate_stack", join(parts, "crate_stack"), box("c", (2.0, 0.9, 1.1), (0.5, 0, 0)))


def cart():
    reset()
    wood, dark = M("wood"), M("wood_dark")
    parts = [box("bed", (1.2, 2.2, 0.15), (0, 0, 0.6), wood, bevel=0.02, seg=1, wonk=0.02)]
    for sx in (-1, 1):
        parts.append(box("side", (0.08, 2.2, 0.5), (sx * 0.6, 0, 0.75), wood, bevel=0.01, seg=1, wonk=0.02))
        parts.append(cyl("wheel", 0.62, 0.12, (sx * 0.74, -0.2, 0.6), dark, verts=16, rot=(0, math.pi / 2, 0), center=True, bevel=0.01, seg=1))
        parts.append(cyl("rim", 0.62, 0.13, (sx * 0.74, -0.2, 0.6), M("iron", 0.5), verts=16, rot=(0, math.pi / 2, 0), center=True, r2=0.62, bevel=0.01, seg=1))
        parts.append(cyl("wheel_in", 0.5, 0.14, (sx * 0.74, -0.2, 0.6), M("black"), verts=16, rot=(0, math.pi / 2, 0), center=True, bevel=0))
        for k in range(4):
            parts.append(cbox("spoke", (0.06, 0.06, 1.1), (sx * 0.74, -0.2, 0.6), wood, rot=(math.tau * k / 8, 0, 0), bevel=0.01, seg=1))
        parts.append(sphere("hub", 0.12, (sx * 0.78, -0.2, 0.6), dark, seg=10, rings=6))
        parts.append(cyl("shaft", 0.05, 1.7, (sx * 0.42, 1.1, 0.45), dark, verts=8, rot=(math.pi / 2 - 0.15, 0, 0), bevel=0.01, seg=1))
    parts.append(box("back", (1.2, 0.08, 0.5), (0, -1.1, 0.75), wood, bevel=0.01, seg=1))
    parts.append(cyl("axle", 0.06, 1.7, (0, -0.2, 0.6), dark, verts=8, rot=(0, math.pi / 2, 0), center=True, bevel=0))
    parts.append(blob("load", (1.0, 1.5, 0.6), (0, -0.1, 0.7), M("canvas")))
    export("cart", join(parts, "cart"), box("c", (1.5, 2.4, 1.25), (0, 0, 0)))


def brazier():
    """Watch brazier: iron fire-basket on three legs, glowing coals inside, a ring of ash on the cobbles."""
    reset()
    iron = M("iron", 0.55)
    parts = [cyl("bowl", 0.34, 0.30, (0, 0, 0.75), iron, verts=12, r2=0.42, bevel=0.01, seg=1)]
    parts.append(cyl("bowl_in", 0.30, 0.26, (0, 0, 0.78), M("black"), verts=12, r2=0.38, bevel=0))
    for k in range(8):
        a = math.tau * k / 8
        parts.append(cbox("bar", (0.03, 0.03, 0.34), (0.38 * math.cos(a), 0.38 * math.sin(a), 0.92), iron, rot=(0, 0, a), bevel=0))
    parts.append(cyl("rim", 0.44, 0.04, (0, 0, 1.05), iron, verts=12, r2=0.44, bevel=0.005, seg=1))
    for k in range(3):
        a = math.tau * k / 3 + math.pi / 6
        parts.append(cbox("leg", (0.04, 0.04, 0.85), (0.22 * math.cos(a), 0.22 * math.sin(a), 0.42), iron, rot=(0.12 * math.sin(a), -0.12 * math.cos(a), 0), bevel=0))
    parts.append(blob("coals", (0.62, 0.62, 0.22), (0, 0, 0.95), M("ember", 0.9, emit=(1.0, 0.32, 0.06), emit_strength=6.0)))
    parts.append(blob("flame", (0.30, 0.30, 0.42), (0, 0, 1.25), M("flame", 0.9, emit=(1.0, 0.55, 0.12), emit_strength=9.0)))
    parts.append(cyl("ash", 0.7, 0.01, (0, 0, 0.0), M("soot", 0.95), verts=16, bevel=0))
    export("brazier", join(parts, "brazier"), cyl("c", 0.45, 1.1, (0, 0, 0), verts=8, bevel=0))


def lantern_post():
    reset()
    iron = M("iron", 0.6)
    parts = [cyl("post", 0.12, 3.6, (0, 0, 0), M("wood_dark"), verts=10, r2=0.09, bevel=0.01, seg=1),
             box("post_cap", (0.3, 0.3, 0.12), (0, 0, 3.6), iron, bevel=0.02, seg=1),
             cyl("post_foot", 0.2, 0.4, (0, 0, 0), M("stone_dark"), verts=10, r2=0.16, bevel=0.02, seg=1)]
    for i in range(4):
        a = math.pi / 2 * (i + 0.5) / 4
        cx, cz = 0.55 - 0.55 * math.cos(a), 2.85 + 0.55 * math.sin(a)
        parts.append(cyl("arm", 0.03, 0.26, (cx, 0, cz), iron, verts=8, rot=(0, a, 0), center=True, bevel=0))
    parts.append(cyl("arm2", 0.03, 0.4, (0.75, 0, 3.4), iron, verts=8, rot=(0, math.pi / 2, 0), center=True, bevel=0))
    parts.append(box("cage", (0.36, 0.36, 0.5), (0.9, 0, 2.75), iron, bevel=0.02, seg=1))
    parts.append(box("glow", (0.30, 0.30, 0.44), (0.9, 0, 2.78), M("gold", 0.3, emit=(1.0, 0.72, 0.35), emit_strength=6.0), bevel=0.02))
    parts.append(cyl("cap", 0.28, 0.25, (0.9, 0, 3.25), iron, verts=8, r2=0.03, bevel=0.01))
    for s in (-1, 1):
        parts.append(box("bar", (0.03, 0.4, 0.5), (0.9 + s * 0.17, 0, 2.75), iron, bevel=0))
        parts.append(box("bar2", (0.4, 0.03, 0.5), (0.9, s * 0.17, 2.75), iron, bevel=0))
    export("lantern_post", join(parts, "lantern_post"), cyl("c", 0.14, 3.6, (0, 0, 0), None, verts=6))


def ground_cobbles():
    """4 x 4 m tileable granite-sett paving slab: top at z=0, 0.2 m thick, centred on the origin. Its texture
    repeats exactly once across the slab (no random UV offset), so slabs laid edge to edge on a 4 m grid, all at
    the same rotation, pave seamlessly. Includes a flat collision box."""
    reset()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=8, y_subdivisions=8, size=4.0, location=(0, 0, 0))
    top = bpy.context.object
    top = _finish_prim(top, "top", M("cobble"))
    _tag(top, mat=M("cobble"), offset=(0.5, 0.5))
    rng = random.Random(44)
    def f(co):
        if abs(abs(co.x) - 2) > 1e-3 and abs(abs(co.y) - 2) > 1e-3:
            co.z += rng.uniform(-0.012, 0.004)
    edit_verts(top, f)
    skirt = box("skirt", (4.0, 4.0, 0.2), (0, 0, -0.2), M("stone_dark"))
    bm = bmesh.new()
    bm.from_mesh(skirt.data)
    bmesh.ops.delete(bm, geom=[fc for fc in bm.faces if fc.normal.z > 0.5], context="FACES")
    bm.to_mesh(skirt.data)
    bm.free()
    export("ground_cobbles", join([top, skirt], "ground_cobbles"), box("c", (4.0, 4.0, 0.5), (0, 0, -0.5)))


# ------------------------------------------------------------------ shared blocks for the district variants
def front_block(parts, W, D, H, mat, ops, z0=0.0, cx=0.0, cy=0.0, bevel=0.06, wonk=0.04):
    """Mass W x D x H with a -Y facade (openings `ops` in world x) recessed REV. Returns the facade plane y."""
    parts.append(box("mass", (W, D - REV, H), (cx, cy + REV / 2, z0), mat, bevel=bevel, seg=1, wonk=wonk))
    plane = cy - D / 2
    parts.append(facade("front", mat, "-Y", plane, cx - W / 2 - 0.01, cx + W / 2 + 0.01, z0, z0 + H, ops))
    return plane


def gable_slab(parts, face, plane, a0, a1, zb, rise, mat, thick=0.3, out=0.0):
    """Triangular gable wall standing on zb between a0 and a1 (plaster, brick or boards)."""
    pts = [(a0, zb), (a1, zb), ((a0 + a1) / 2, zb + rise)]
    parts.append(slab("gable", pts, face, plane, out - thick, out, mat))


def hip_roof(name, L, W, H, loc, mat, hip=None, thick=0.25):
    """Hipped roof solid (thatch, shingles): eaves rectangle L x W at loc.z, ridge along X, hips `hip` long."""
    hip = W / 2 if hip is None else hip
    x, y, z = loc
    bm = bmesh.new()
    e = [bm.verts.new((x + sx * L / 2, y + sy * W / 2, z)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    r = [bm.verts.new((x - L / 2 + hip, y, z + H)), bm.verts.new((x + L / 2 - hip, y, z + H))]
    lo = [bm.verts.new((v.co.x - (v.co.x - x) * 0.04, v.co.y - (v.co.y - y) * 0.06, z - thick)) for v in e]
    bm.faces.new((e[0], e[1], r[1], r[0]))
    bm.faces.new((e[2], e[3], r[0], r[1]))
    bm.faces.new((e[1], e[2], r[1]))
    bm.faces.new((e[3], e[0], r[0]))
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((e[i], lo[i], lo[j], e[j]))
    bm.faces.new(list(reversed(lo)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _mesh_obj(name, bm, mat)
    return finish(o, bevel=0.08, seg=2, smooth=35)


def hip_snow(name, L, W, H, loc, hip=None, frac=0.62):
    """Snow lying on the upper `frac` of a hip_roof(L, W, H, loc): same slopes, so it hugs the thatch."""
    hip = W / 2 if hip is None else hip
    x, y, z = loc
    Wf = W * frac
    Lf = L - (W - Wf)
    return hip_roof(name, Lf, Wf, H * frac + 0.08, (x, y, z + H * (1 - frac) + 0.02), M("snow"), hip=max(0.1, hip - (W - Wf) / 2), thick=0.06)


def pitched(parts, name, L, W, H, loc, mat, along_x=True, snow=False, courses=0, sag=0.06, flare=0.06):
    parts.append(roof(name, L, W, H, loc, mat, sag=sag, flare=flare, along_x=along_x, courses=courses, ridge=courses > 0))
    if snow:
        x, y, z = loc
        parts.append(roof(name + "_snow", L - 0.1, W * 0.47, H * 0.45 + 0.1, (x, y, z + H * 0.54), M("snow"), sag=sag,
                          flare=0.0, along_x=along_x, top_w=0.25, cuts=4))


def small_windows(parts, plane, xs, zb, w=0.8, h=1.1, shape="rect", **kw):
    for x in xs:
        win_unit(parts, "-Y", plane, x, zb, w, h, shape, **kw)


def shop_door(parts, plane, x, w=1.6, h=2.2):
    """Arched shop door: timber leaves with an iron-barred fanlight and a plain stone surround."""
    door_unit(parts, "-Y", plane, x, w, h, portal=False)
    voussoirs(parts, "-Y", plane, x, h + 0.12, w, 0.26, M("stone"), n=7, proud=0.07, key=0.1)
    for sx in (-1, 1):
        parts.append(box("dj", (0.26, 0.1, h + 0.12), (x + sx * (w / 2 + 0.13), plane - 0.05, 0), M("stone"), bevel=0.02, seg=1))


# ------------------------------------------------------------------ KAZIMIERZ
def kaz_house_a():
    """Two-storey Kazimierz house, eaves to the street: plain lime plaster, small windows, two arched shop doors."""
    reset()
    parts = []
    W, D, GF, FL = 9.0, 8.0, 3.6, 3.0
    wall = M("plaster_lime")
    gops = [(-2.4, 0.0, 1.6, 2.2 + 0.12 + 0.8, "round"), (2.4, 0.0, 1.6, 2.2 + 0.12 + 0.8, "round"), (0.0, 1.3, 0.8, 1.1, "rect")]
    y = front_block(parts, W, D, GF, wall, gops)
    for x in (-2.4, 2.4):
        shop_door(parts, y, x)
    win_unit(parts, "-Y", y, 0.0, 1.3, 0.8, 1.1, bars=True, surround=None)
    parts.append(box("plinth", (W, 0.1, 0.5), (0, y - 0.03, 0), M("plaster_lime_damp")))
    uops = [(x, GF + 0.8, 0.8, 1.2, "rect") for x in (-3.0, -1.0, 1.0, 3.0)]
    y2 = front_block(parts, W, D, FL, wall, uops, z0=GF)
    small_windows(parts, y2, [o[0] for o in uops], GF + 0.8, 0.8, 1.2, surround="stone", shutters=True, warm=False)
    parts.append(box("string", (W + 0.1, 0.2, 0.18), (0, y - 0.06, GF - 0.1), M("stone"), bevel=0.02, seg=1))
    cornice(parts, W, D, GF + FL - 0.05, t=0.3, proud=0.22, modillions=False)
    pitched(parts, "roof", W + 0.8, D + 1.0, 3.6, (0, 0, GF + FL + 0.2), M("tile"), courses=4)
    dormer(parts, 0.0, -D / 2 + 1.1, GF + FL + 0.55, 1.2, 1.3, wall, M("tile_dark"))
    chimney(parts, 2.6, 1.0, GF + FL + 1.6, h=2.0)
    shop_sign(parts, -0.9, y, 3.1, emblem="key")
    drainpipe(parts, W / 2 - 0.25, y - 0.12, GF + FL - 0.2, [(1.0, y), (4.0, y2)])
    visual = join(parts, "kaz_house_a")
    shear(visual, 0.006, -0.004)
    export("kaz_house_a", visual, box("c", (W, D, GF + FL + 3.8), (0, 0, 0)))


def kaz_house_b():
    """Gable-fronted Gothic house, narrow and deep, grey plaster, pointed shop arch and a stepped brick gable."""
    reset()
    parts = []
    W, D, H = 7.0, 11.0, 6.6
    wall = M("plaster_grey")
    ops = [(-1.4, 0.0, 1.8, 3.4, "pointed"), (1.8, 1.2, 0.7, 1.2, "rect"),
           (-1.6, 4.0, 0.7, 1.3, "rect"), (0.0, 4.0, 0.7, 1.3, "rect"), (1.6, 4.0, 0.7, 1.3, "rect")]
    y = front_block(parts, W, D, H, wall, ops)
    door_unit(parts, "-Y", y, -1.4, 1.8, 1.8, portal=False, fanlight=False)
    tymp = [(-2.3, 1.92), (-0.5, 1.92)] + outline(-1.4, 0.0, 1.8, 3.4, "pointed")[3:-1]
    parts.append(slab("tymp", tymp, "-Y", y, -REV + 0.01, -REV + 0.05, M("wood_dark")))
    voussoirs(parts, "-Y", y, -1.4, 3.4 - 1.8 * 0.866, 1.8, 0.24, M("stone"), shape="pointed", n=8, proud=0.08, key=0.06)
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, bars=zb < 2, surround="stone", warm=RNG.random() < 0.4)
    parts.append(box("plinth", (W, 0.1, 0.5), (0, y - 0.03, 0), M("stone_dark")))
    parts.append(box("string", (W + 0.1, 0.18, 0.16), (0, y - 0.06, 3.6), M("stone"), bevel=0.02, seg=1))
    rise = 4.6
    gable_slab(parts, "-Y", y, -W / 2, W / 2, H, rise, M("brick"), thick=0.4, out=0.0)
    for k in range(4):                                     # stepped gable copings
        zz = H + rise * k / 4
        hw = W / 2 * (1 - k / 4)
        for sx in (-1, 1):
            parts.append(box("step", (0.7, 0.55, 0.9), (sx * (hw - 0.35), y + 0.05, zz), M("brick_dark"), bevel=0.02, seg=1))
            parts.append(box("stepcap", (0.8, 0.65, 0.1), (sx * (hw - 0.35), y + 0.05, zz + 0.9), M("stone"), bevel=0.02, seg=1))
    parts.append(slab("gwin", outline(0.0, H + 1.0, 0.8, 1.6, "pointed"), "-Y", y, 0.0, 0.03, M("glass")))
    parts.append(slab("gwin2", outline(0.0, H + 3.0, 0.5, 0.9, "round"), "-Y", y, 0.0, 0.03, M("glass")))
    parts.append(roof("roof", D, W + 0.6, rise, (0, 0.2, H), M("tile_dark"), sag=0.05, flare=0.04, along_x=False, courses=5, ridge=True))
    chimney(parts, 1.4, 2.5, H + 1.6, h=2.6)
    visual = join(parts, "kaz_house_b")
    shear(visual, -0.005, -0.004)
    export("kaz_house_b", visual, box("c", (W, D, H + rise), (0, 0, 0)))


def kaz_synagogue():
    """Old Synagogue (Stara Synagoga): Gothic stone hall with brick buttresses, tall pointed windows, the roof
    hidden behind a Renaissance attic with a blind arcade and crenellation; no tower. A lower women's annex."""
    reset()
    parts, col = [], []
    W, D, H = 12.0, 20.0, 9.0
    wall = M("stone_pale")
    ops = [(0.0, 0.0, 1.8, 2.4 + 0.12 + 0.9, "round"), (-3.4, 3.5, 1.2, 3.6, "round"), (3.4, 3.5, 1.2, 3.6, "round")]
    parts.append(box("hall", (W - 2 * REV, D - REV, H), (0, REV / 2, 0), wall, bevel=0.06, seg=1, wonk=0.04))
    col.append(box("c", (W, D, H), (0, 0, 0)))
    y = -D / 2
    parts.append(facade("front", wall, "-Y", y, -W / 2 - 0.01, W / 2 + 0.01, 0, H, ops))
    door_unit(parts, "-Y", y, 0.0, 1.8, 2.4, surround="stone")
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, warm=True, surround=None)
    ys = [-D / 2 + 2.5 + i * 3.75 for i in range(5)]
    for face, plane, sgn in (("-X", -W / 2, -1), ("+X", W / 2, 1)):
        sops = [(sgn * yy + sgn * 1.9, 2.8, 1.3, 5.0, "pointed") for yy in ys[:-1]]
        parts.append(facade("side", wall, face, plane, -D / 2 - 0.01, D / 2 + 0.01, 0, H, sops))
        for (a, zb, w, h, sh) in sops:
            win_unit(parts, face, plane, a, zb, w, h, sh, warm=True, surround=None, cross=False)
        for yy in ys:
            parts.append(taper_box("butt", (1.2, 1.3, H * 0.8), (sgn * (W / 2 + 0.55), yy, 0), M("brick"), top=0.6, bevel=0.03, seg=1, wonk=0.03))
            parts.append(pyramid("butt_cap", (0.75, 0.8, 0.7), (sgn * (W / 2 + 0.4), yy, H * 0.8), M("stone")))
    for x in (-W / 2, W / 2):
        parts.append(taper_box("fbutt", (1.2, 1.2, H * 0.8), (x, y - 0.5, 0), M("brick"), top=0.6, bevel=0.03, seg=1))
    # Renaissance attic all round, hiding a low roof
    A0 = H
    parts.append(box("attic", (W + 0.3, D + 0.3 - 2 * REV, 2.4), (0, 0, A0), M("plaster_white"), bevel=0.04, seg=1))
    aops = [(x, A0 + 0.3, 1.2, 1.6, "round") for x in (-4.2, -1.4, 1.4, 4.2)]
    parts.append(facade("attic_f", M("plaster_white"), "-Y", -(D + 0.3) / 2, -(W + 0.3) / 2 - 0.01, (W + 0.3) / 2 + 0.01, A0, A0 + 2.4, aops))
    parts.append(facade("attic_b", M("plaster_white"), "+Y", (D + 0.3) / 2, -(W + 0.3) / 2 - 0.01, (W + 0.3) / 2 + 0.01, A0, A0 + 2.4, aops))
    parts.append(box("attic_base", (W + 0.6, D + 0.6, 0.25), (0, 0, A0 - 0.1), M("stone"), bevel=0.03, seg=1))
    parts.append(box("coping", (W + 0.6, D + 0.6, 0.18), (0, 0, A0 + 2.4), M("stone"), bevel=0.02, seg=1))
    for i in range(7):
        x = -W / 2 + W * i / 6
        for yy in (-(D + 0.3) / 2 + 0.2, (D + 0.3) / 2 - 0.2):
            parts.append(box("merlon", (0.7, 0.4, 0.8), (x, yy, A0 + 2.58), M("stone"), bevel=0.02, seg=1))
            parts.append(pyramid("merlon_top", (0.5, 0.3, 0.4), (x, yy, A0 + 3.38), M("stone")))
    parts.append(roof("lowroof", D - 0.6, W - 0.4, 1.8, (0, 0, A0 + 0.5), M("tile_dark"), along_x=False, sag=0.03, flare=0.03, courses=2))
    parts.append(box("snow", (W + 0.5, D + 0.5, 0.06), (0, 0, A0 + 2.58), M("snow")))
    # women's annex against the west side
    ax = -W / 2 - 3.2
    parts.append(box("annex", (4.0, 10.0, 5.0), (ax, 2.0, 0), M("plaster_grey"), bevel=0.05, seg=1, wonk=0.04))
    col.append(box("c", (4.0, 10.0, 5.0), (ax, 2.0, 0)))
    parts.append(facade("annex_f", M("plaster_grey"), "-Y", 2.0 - 5.0 - 0.001, ax - 2.01, ax + 2.01, 0, 5.0, [(ax, 1.8, 0.8, 1.4, "round")]))
    win_unit(parts, "-Y", 2.0 - 5.0 - 0.001, ax, 1.8, 0.8, 1.4, "round", surround=None)
    parts.append(roof("annex_roof", 10.4, 4.6, 1.5, (ax, 2.0, 5.0), M("tile"), along_x=False, sag=0.03, flare=0.03, courses=2))
    sn = roof_snow("roof_snow", D - 0.6, W - 0.4, 1.8, (0, 0, A0 + 0.5), sag=0.03, flare=0.03, along_x=False, thick=0.08, seed=81, bare=0.15, slide=0.0,
                   drifts=[(0, -D / 2 + 1.2, W, 0.15), (0, D / 2 - 1.2, W, 0.15)])
    if sn:
        parts.append(sn)
    sn = roof_snow("annex_snow", 10.4, 4.6, 1.5, (ax, 2.0, 5.0), sag=0.03, flare=0.03, along_x=False, thick=0.06, seed=82, cell=0.9)
    if sn:
        parts.append(sn)
    eave_icicles(parts, 10.0, 4.6, 4.98, (ax, 2.0), along_x=False, sides=(-1,), seed=83, maxlen=0.5)
    for yy in (-(D + 0.6) / 2, (D + 0.6) / 2):
        icicles(parts, (-W / 2, yy), (W / 2, yy), A0 + 2.4, maxlen=0.35, seed=84 + int(yy), density=1.8, gap=0.5)
    for i in range(7):
        x = -W / 2 + W * i / 6
        for yy in (-(D + 0.3) / 2 + 0.2, (D + 0.3) / 2 - 0.2):
            parts.append(box("merlon_snow", (0.66, 0.36, 0.03), (x, yy, A0 + 3.38), M("snow")))
    visual = join(parts, "kaz_synagogue")
    export("kaz_synagogue", visual, join(col, "col"))


# ------------------------------------------------------------------ GARBARY (tanners' suburb)
def timber_frame(parts, face, plane, a0, a1, z0, z1, posts=4, braces=True):
    """Oak posts, rails and braces laid on a plastered wall face."""
    oak = M("timber")
    for i in range(posts + 1):
        a = a0 + (a1 - a0) * i / posts
        parts.append(fbox("post", face, plane, a, 0.05, z0, 0.2, 0.1, z1 - z0, oak, bevel=0.01, seg=1))
    for zz in (z0, (z0 + z1) / 2, z1 - 0.2):
        parts.append(fbox("rail", face, plane, (a0 + a1) / 2, 0.05, zz, a1 - a0, 0.1, 0.2, oak, bevel=0.01, seg=1))
    if braces:
        for i in range(posts):
            aa, bb = a0 + (a1 - a0) * i / posts, a0 + (a1 - a0) * (i + 1) / posts
            zm = (z0 + z1) / 2
            pts = [(aa + 0.1, zm), (aa + 0.26, zm), (bb - 0.1, z1 - 0.2), (bb - 0.26, z1 - 0.2)] if i % 2 == 0 else \
                  [(bb - 0.26, zm), (bb - 0.1, zm), (aa + 0.26, z1 - 0.2), (aa + 0.1, z1 - 0.2)]
            parts.append(slab("brace", pts, face, plane, 0.0, 0.1, oak))


def garb_workshop():
    """Tannery shed: timber-framed walls on three sides, open to the street, tanning vats and hides on poles."""
    reset()
    parts, col = [], []
    W, D, H = 10.0, 7.0, 3.4
    infill = M("plaster_lime")
    oak = M("timber")
    parts.append(box("back", (W, 0.3, H), (0, D / 2 - 0.15, 0), infill, bevel=0.02, seg=1, wonk=0.03))
    timber_frame(parts, "-Y", D / 2 - 0.3, -W / 2, W / 2, 0.0, H, posts=5)
    col.append(box("c", (W, 0.3, H), (0, D / 2 - 0.15, 0)))
    for sx in (-1, 1):
        parts.append(box("side", (0.3, D, H), (sx * (W / 2 - 0.15), 0, 0), infill, bevel=0.02, seg=1, wonk=0.03))
        timber_frame(parts, "-X" if sx < 0 else "+X", sx * W / 2, -D / 2, D / 2, 0.0, H, posts=3)
        col.append(box("c", (0.3, D, H), (sx * (W / 2 - 0.15), 0, 0)))
    for x in (-W / 6, W / 6):
        parts.append(box("fpost", (0.26, 0.26, H), (x, -D / 2 + 0.2, 0), oak, bevel=0.02, seg=1, wonk=0.02))
        col.append(box("c", (0.26, 0.26, H), (x, -D / 2 + 0.2, 0)))
    parts.append(box("head", (W + 0.2, 0.3, 0.3), (0, -D / 2 + 0.2, H - 0.3), oak, bevel=0.02, seg=1))
    parts.append(box("floor", (W, D, 0.08), (0, 0, 0), M("stone_dark")))
    gable_slab(parts, "-X", -W / 2, -D / 2, D / 2, H, 2.8, M("wood_dark"), thick=0.12)
    gable_slab(parts, "+X", W / 2, -D / 2, D / 2, H, 2.8, M("wood_dark"), thick=0.12)
    pitched(parts, "roof", W + 0.9, D + 1.2, 2.9, (0, 0, H), M("tile_moss"), courses=3)
    for i, (x, y) in enumerate(((-3.0, 0.8), (-1.2, 1.4), (0.8, 0.9), (2.8, 1.3))):
        parts.append(cyl("vat", 0.7, 1.0, (x, y, 0), M("wood"), verts=14, bevel=0.01, seg=1))
        for z in (0.15, 0.8):
            parts.append(cyl("hoop", 0.72, 0.06, (x, y, z), M("iron"), verts=14))
        parts.append(cyl("liquor", 0.64, 0.02, (x, y, 0.9), M("water" if i % 2 else "brown_coat", 0.15), verts=14))
        col.append(cyl("c", 0.7, 1.0, (x, y, 0), None, verts=8))
    parts.append(cyl("pole", 0.05, W - 1.0, (0, -1.6, 2.4), oak, verts=8, rot=(0, math.pi / 2, 0), center=True))
    for k in range(5):
        hide = box("hide", (0.9, 0.03, 1.3), (-3.6 + k * 1.8, -1.6, 1.1), M("brown_coat" if k % 2 else "sukmana"), bevel=0.01, seg=1, wonk=0.1)
        parts.append(hide)
    parts.append(box("bark", (1.6, 1.0, 0.7), (4.0, -1.5, 0), M("wood_dark"), bevel=0.05, seg=1, wonk=0.12))
    visual = join(parts, "garb_workshop")
    export("garb_workshop", visual, join(col, "col"))


def garb_house():
    """Low plaster house of the tanners' suburb: one storey, limewash with a blue tint, board gables, mossy tiles."""
    reset()
    parts = []
    W, D, H = 8.0, 6.5, 3.2
    wall = M("plaster_limeblue")
    ops = [(-1.6, 0.0, 1.0, 2.0, "rect"), (0.6, 1.0, 0.8, 1.0, "rect"), (2.6, 1.0, 0.8, 1.0, "rect")]
    y = front_block(parts, W, D, H, wall, ops)
    parts.append(fbox("door", "-Y", y, -1.6, -REV + 0.05, 0, 0.96, 0.06, 1.98, M("wood_dark")))
    for zz in (0.4, 1.5):
        parts.append(fbox("strap", "-Y", y, -1.6, -REV + 0.09, zz, 0.9, 0.02, 0.06, M("iron")))
    parts.append(fbox("lintel", "-Y", y, -1.6, 0.04, 2.0, 1.4, 0.1, 0.18, M("timber")))
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, surround=None, head=None, shutters=True, sill=True)
        parts.append(fbox("lintel", "-Y", y, a, 0.04, zb + h, w + 0.4, 0.1, 0.16, M("timber")))
    parts.append(box("plinth", (W, 0.1, 0.45), (0, y - 0.03, 0), M("plaster_limeblue_damp")))
    for sx in (-1, 1):
        face = "-X" if sx < 0 else "+X"
        gable_slab(parts, face, sx * W / 2, -D / 2 - 0.2, D / 2 + 0.2, H, 3.0, M("wood"), thick=0.08, out=0.05)
        for k in range(1, 6):
            a = -D / 2 + (D) * k / 6
            parts.append(fbox("batten", face, sx * W / 2, a, 0.1, H, 0.06, 0.04, 3.0 * (1 - abs(a) / (D / 2 + 0.2)) - 0.05, M("wood_dark")))
    parts.append(box("sole", (W + 0.1, D + 0.1, 0.2), (0, 0, H - 0.1), M("timber"), bevel=0.02, seg=1))
    pitched(parts, "roof", W + 1.0, D + 1.4, 3.1, (0, 0, H), M("tile_moss"), courses=3)
    chimney(parts, 1.2, 0.4, H + 1.4, h=1.8)
    visual = join(parts, "garb_house")
    shear(visual, 0.008, 0.004)
    export("garb_house", visual, box("c", (W, D, H + 3.1), (0, 0, 0)))


# ------------------------------------------------------------------ DOCKS (the Vistula at Kazimierz)
def dock_granary():
    """Brick granary (spichlerz): four storeys, gable to the river, small shuttered windows, stacked loading doors
    and a hoist beam with a pulley under the ridge."""
    reset()
    parts = []
    W, D, H = 10.0, 12.0, 11.0
    brick = M("brick")
    ops = []
    for s in range(4):
        z = 0.6 + s * 2.7
        ops.append((0.0, z if s else 0.0, 1.6, 2.1 if s else 2.4, "seg" if s == 0 else "rect"))
        for x in (-3.2, 3.2):
            ops.append((x, z + 0.8, 0.6, 0.8, "rect"))
    y = front_block(parts, W, D, H, brick, ops, bevel=0.05, wonk=0.03)
    for (a, zb, w, h, sh) in ops:
        if abs(a) < 0.1:
            for sx in (-1, 1):
                parts.append(fbox("ldoor", "-Y", y, a + sx * (w / 4 + 0.01), -REV + 0.05, zb, w / 2 - 0.03, 0.06, h - (0.3 if sh == "seg" else 0.02), M("wood_dark")))
                parts.append(fbox("lstrap", "-Y", y, a + sx * (w / 4), -REV + 0.1, zb + 0.4, w / 2 - 0.1, 0.02, 0.07, M("iron")))
            parts.append(fbox("lsill", "-Y", y, a, 0.05, zb - 0.1, w + 0.3, 0.3, 0.12, M("stone")))
        else:
            parts.append(slab("glass", outline(a, zb, w, h), "-Y", y, -REV + 0.005, -REV + 0.02, M("void")))
            parts.append(fbox("ishutter", "-Y", y, a + 0.5, 0.03, zb, 0.36, 0.04, h, M("iron")))
            parts.append(fbox("bar", "-Y", y, a, -0.05, zb, 0.03, 0.03, h, M("iron")))
            parts.append(fbox("sill", "-Y", y, a, 0.02, zb - 0.1, w + 0.2, 0.2, 0.1, M("stone")))
    for s in range(1, 4):
        parts.append(box("band", (W + 0.1, 0.12, 0.14), (0, y - 0.05, 0.6 + s * 2.7 - 0.3), M("brick_dark")))
    rise = 6.0
    gable_slab(parts, "-Y", y, -W / 2, W / 2, H, rise, brick, thick=0.35, out=0.0)
    parts.append(slab("gdoor", outline(0.0, H + 0.3, 1.2, 1.9), "-Y", y, 0.0, 0.05, M("wood_dark")))
    for k in range(3):
        parts.append(slab("gslit", outline(-1.8 + k * 1.8, H + 3.0 + (0.6 if k == 1 else 0), 0.25, 0.9), "-Y", y, 0.0, 0.03, M("void")))
    parts.append(box("hoist", (0.3, 2.2, 0.3), (0, y - 0.8, H + 2.9), M("timber"), bevel=0.02, seg=1))
    parts.append(box("hoist_brace", (0.2, 0.2, 1.3), (0, y - 0.35, H + 1.7), M("timber")))
    parts.append(cyl("pulley", 0.2, 0.08, (0, y - 1.7, H + 2.7), M("wood"), verts=12, rot=(0, math.pi / 2, 0), center=True))
    parts.append(cyl("rope", 0.02, H + 2.2, (0, y - 1.9, 0.5), M("canvas"), verts=6))
    parts.append(box("hook", (0.1, 0.05, 0.25), (0, y - 1.9, 0.3), M("iron")))
    parts.append(roof("roof", D, W + 0.6, rise, (0, 0.2, H), M("tile"), along_x=False, sag=0.08, flare=0.05, courses=6, ridge=True))
    for k in range(3):
        parts.append(box("vent", (0.5, 0.9, 0.6), (W / 2 * 0.55, -3 + k * 3, H + 2.4), M("tile_dark"), bevel=0.03, seg=1))
    for zz in (2.0, 7.0):
        for sx in (-1, 1):
            parts.append(box("anchor", (0.08, 0.06, 0.8), (sx * 2.2, y - 0.03, zz), M("iron")))
    visual = join(parts, "dock_granary")
    export("dock_granary", visual, box("c", (W, D, H + rise), (0, 0, 0)))


def dock_wharf():
    """Timber quay segment, 8 m along the river (X) and 4 m deep, deck top at z=0 (street level), front edge
    (river side) at -Y; oak piles run 2.5 m down to the water. Mooring posts and a coiled rope."""
    reset()
    parts = []
    L, Dp = 8.0, 4.0
    for k in range(16):
        x = -L / 2 + L * (k + 0.5) / 16
        parts.append(box("plank", (L / 16 - 0.02, Dp, 0.08), (x, 0, -0.08), M("wood"), bevel=0.01, seg=1, wonk=0.02))
    for x in (-L / 2 + 0.3, 0.0, L / 2 - 0.3):
        for y in (-Dp / 2 + 0.2, Dp / 2 - 0.3):
            parts.append(cyl("pile", 0.16, 2.6, (x, y, -2.68), M("timber"), verts=10, bevel=0.01, seg=1))
    parts.append(box("stringer", (L, 0.24, 0.3), (0, -Dp / 2 + 0.2, -0.4), M("timber"), bevel=0.02, seg=1))
    parts.append(box("stringer", (L, 0.24, 0.3), (0, Dp / 2 - 0.3, -0.4), M("timber"), bevel=0.02, seg=1))
    parts.append(box("fender", (L, 0.2, 0.25), (0, -Dp / 2 - 0.05, -0.3), M("wood_dark"), bevel=0.02, seg=1))
    for k in range(9):
        parts.append(box("fender_v", (0.18, 0.14, 1.6), (-L / 2 + k * L / 8, -Dp / 2 - 0.12, -1.6), M("wood_dark"), bevel=0.01, seg=1))
    for x in (-2.8, 2.8):
        parts.append(cyl("bollard", 0.18, 0.7, (x, -Dp / 2 + 0.4, 0), M("timber"), verts=12, r2=0.2, bevel=0.02, seg=1))
        parts.append(cyl("bollard_cap", 0.24, 0.1, (x, -Dp / 2 + 0.4, 0.7), M("iron"), verts=12))
        parts.append(cyl("bollard_snow", 0.2, 0.05, (x, -Dp / 2 + 0.4, 0.8), M("snow"), verts=12))
    parts.append(torus("coil", 0.32, 0.05, (0.8, -0.6, 0.05), M("canvas"), seg=16, mseg=6))
    parts.append(torus("coil2", 0.22, 0.05, (0.8, -0.6, 0.13), M("canvas"), seg=16, mseg=6))
    parts.append(box("snow", (L - 1.0, 1.6, 0.03), (-0.5, 1.0, 0), M("snow"), bevel=0.01, seg=1, wonk=0.1))
    parts.append(box("sack", (0.9, 0.6, 0.5), (-2.6, 0.9, 0), M("canvas"), bevel=0.1, seg=2, wonk=0.05))
    visual = join(parts, "dock_wharf")
    export("dock_wharf", visual, box("c", (L, Dp, 0.4), (0, 0, -0.4)))


def salt_barge():
    """Vistula salt barge (galar) loaded with Wieliczka salt blocks. Waterline at z=0, hull 14 m along X,
    3.2 m beam, gunwale 0.7 m above the water. Prop: no collision beyond a hull box."""
    reset()
    parts = []
    L, B = 14.0, 3.2
    hull = box("hull", (L, B, 1.2), (0, 0, -0.5), M("timber"), bevel=0.06, seg=1)
    def taper(co):
        t = max(0.0, (abs(co.x) - L * 0.32) / (L * 0.18))
        co.y *= 1.0 - 0.45 * t
        if t > 0 and co.z > -0.3:
            co.z += 0.35 * t
        if t > 0 and co.z < -0.3:
            co.x -= math.copysign(0.8 * t, co.x)
    edit_verts(hull, taper)
    parts.append(hull)
    parts.append(box("deck", (L * 0.62, B - 0.4, 0.06), (0, 0, 0.55), M("wood")))
    for k in range(7):
        parts.append(box("rib", (0.12, B + 0.02, 0.1), (-L * 0.3 + k * L * 0.1, 0, 0.62), M("wood_dark")))
    for i in range(4):
        for j in range(2):
            for lv in range(2 - (i % 2)):
                parts.append(cyl("salt", 0.32, 0.9, (-3.0 + i * 1.9 + lv * 0.3, -0.6 + j * 1.2, 0.93 + lv * 0.62), M("salt"), verts=10, rot=(0, math.pi / 2, 0), center=True, bevel=0.03, seg=1))
    parts.append(cyl("oar", 0.06, 6.0, (L / 2 + 1.2, 0, 1.2), M("wood"), verts=8, rot=(0, math.pi / 2 - 0.2, 0), center=True))
    parts.append(box("blade", (1.4, 0.06, 0.4), (L / 2 + 3.6, 0, 0.35), M("wood"), bevel=0.01, seg=1))
    parts.append(box("oar_post", (0.2, 0.2, 1.0), (L / 2 - 1.0, 0, 0.6), M("timber")))
    parts.append(box("snow", (L * 0.5, B - 0.6, 0.03), (0, 0, 1.25), M("snow"), wonk=0.2))
    visual = join(parts, "salt_barge")
    export("salt_barge", visual, box("c", (L, B, 1.8), (0, 0, -0.5)))


# ------------------------------------------------------------------ KLEPARZ (market town north of the walls)
def klep_house():
    """Kleparz house: one and a half storeys, ochre lime plaster, a timber porch on posts, a dormer in the roof."""
    reset()
    parts = []
    W, D, H = 10.0, 7.0, 3.4
    wall = M("plaster_ochre")
    ops = [(0.0, 0.0, 1.1, 2.1, "rect")] + [(x, 1.0, 0.85, 1.15, "rect") for x in (-3.4, -1.7, 1.7, 3.4)]
    y = front_block(parts, W, D, H, wall, ops)
    parts.append(fbox("door", "-Y", y, 0.0, -REV + 0.05, 0, 1.06, 0.06, 2.08, M("wood_dark")))
    for r in range(2):
        parts.append(fbox("dpanel", "-Y", y, 0.0, -REV + 0.09, 0.3 + r * 0.95, 0.8, 0.03, 0.75, M("wood_dark"), bevel=0.01, seg=1))
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, surround="plaster_white", head="lintel", shutters=True, warm=RNG.random() < 0.4)
    parts.append(box("plinth", (W, 0.1, 0.5), (0, y - 0.03, 0), M("plaster_ochre_damp")))
    for x in (-1.1, 1.1):
        parts.append(cyl("porch_post", 0.1, 2.6, (x, y - 1.6, 0.15), M("timber"), verts=8, bevel=0.01, seg=1))
    parts.append(box("porch_floor", (2.8, 1.8, 0.15), (0, y - 0.9, 0), M("wood"), bevel=0.01, seg=1))
    parts.append(roof("porch_roof", 2.2, 3.0, 0.9, (0, y - 0.9, 2.75), M("tile_dark"), along_x=False, sag=0.02, flare=0.05, cuts=3))
    parts.append(box("porch_beam", (2.6, 0.18, 0.18), (0, y - 1.6, 2.6), M("timber")))
    cornice(parts, W, D, H - 0.05, t=0.25, proud=0.2, modillions=False, mat=M("plaster_white"))
    pitched(parts, "roof", W + 0.8, D + 1.0, 3.6, (0, 0, H + 0.15), M("tile"), courses=4)
    dormer(parts, -2.6, -D / 2 + 1.0, H + 0.5, 1.2, 1.3, wall, M("tile_dark"))
    dormer(parts, 2.6, -D / 2 + 1.0, H + 0.5, 1.2, 1.3, wall, M("tile_dark"))
    chimney(parts, 0.0, 0.8, H + 1.8, h=1.9)
    visual = join(parts, "klep_house")
    shear(visual, -0.006, 0.003)
    export("klep_house", visual, box("c", (W, D, H + 3.8), (0, 0, 0)))


def klep_stable():
    """Timber stable for market-day horses: vertical oak boards, a stable door split in halves, a hay loft under a
    thatched roof with its hatch open and hay showing."""
    reset()
    parts = []
    W, D, H = 12.0, 7.0, 3.2
    boards = M("wood")
    ops = [(-3.0, 0.0, 1.4, 2.3, "rect"), (3.0, 0.0, 1.4, 2.3, "rect"), (0.0, 1.5, 0.9, 0.5, "rect")]
    y = front_block(parts, W, D, H, boards, ops, wonk=0.05)
    for x in (-3.0, 3.0):
        parts.append(fbox("door_lo", "-Y", y, x, -REV + 0.05, 0, 1.36, 0.06, 1.2, M("wood_dark")))
        parts.append(fbox("door_hi", "-Y", y, x - 0.5, -0.3, 1.25, 0.1, 0.9, 1.0, M("wood_dark")))
        parts.append(fbox("door_x", "-Y", y, x, -REV + 0.1, 0.1, 1.2, 0.03, 0.12, M("timber")))
        parts.append(fbox("frame", "-Y", y, x, 0.05, 2.3, 1.8, 0.12, 0.2, M("timber")))
    parts.append(slab("hay_hole", outline(0.0, 1.5, 0.9, 0.5), "-Y", y, -REV + 0.005, -REV + 0.02, M("void")))
    for x in (-W / 2, -W / 6, W / 6, W / 2):
        parts.append(fbox("post", "-Y", y, x, 0.08, 0, 0.22, 0.16, H, M("timber"), bevel=0.01, seg=1))
    parts.append(box("sill", (W + 0.2, 0.3, 0.3), (0, y + 0.05, 0), M("timber")))
    for sx in (-1, 1):
        face = "-X" if sx < 0 else "+X"
        gable_slab(parts, face, sx * W / 2, -D / 2, D / 2, H, 3.6, boards, thick=0.1, out=0.02)
        parts.append(slab("loft", outline(0.0, H + 0.6, 1.2, 1.3), face, sx * W / 2, 0.02, 0.05, M("void")))
        parts.append(fbox("hay", face, sx * W / 2, 0.0, 0.1, H + 0.6, 1.1, 0.3, 0.7, M("hay"), bevel=0.1, seg=1, wonk=0.12))
        parts.append(fbox("hatch", face, sx * W / 2, 0.95, 0.3, H + 0.6, 0.08, 0.6, 1.3, M("wood_dark")))
    parts.append(hip_roof("roof", W + 1.2, D + 1.4, 3.8, (0, 0, H), M("thatch"), hip=1.2))
    parts.append(hip_snow("roof_snow", W + 1.2, D + 1.4, 3.8, (0, 0, H), hip=1.2))
    parts.append(box("trough", (2.0, 0.5, 0.5), (0, y - 0.6, 0), M("wood_dark"), bevel=0.02, seg=1))
    parts.append(box("trough_ice", (1.8, 0.4, 0.02), (0, y - 0.6, 0.45), M("glass")))
    parts.append(box("hay_pile", (1.6, 1.2, 0.8), (-5.2, y - 1.0, 0), M("hay"), bevel=0.3, seg=2, wonk=0.2))
    visual = join(parts, "klep_stable")
    export("klep_stable", visual, box("c", (W, D, H + 3.8), (0, 0, 0)))


# ------------------------------------------------------------------ KANONICZA (canons' street under Wawel)
def kan_house():
    """Canon's house: two storeys and an attic, cream plaster, a Renaissance stone portal with pilasters and an
    entablature, and a deep gate passage (the courtyard entry) with an arcade glimpsed at its end."""
    reset()
    parts, col = [], []
    W, D, GF, FL = 13.0, 10.0, 4.2, 3.4
    wall = M("plaster_cream")
    gate_w = 3.0
    ops = [(-3.0, 0.0, 1.8, 2.8 + 0.12 + 0.9, "round"), (2.8, 0.0, gate_w, 2.6 + gate_w / 2, "round"), (-5.6, 1.4, 0.9, 1.6, "rect")]
    gl, gr = 2.8 - gate_w / 2 - 0.3, 2.8 + gate_w / 2 + 0.3
    parts.append(box("mass_l", (gl + W / 2, D - REV, GF), ((gl - W / 2) / 2, REV / 2, 0), wall, bevel=0.05, seg=1))
    parts.append(box("mass_r", (W / 2 - gr, D - REV, GF), ((gr + W / 2) / 2, REV / 2, 0), wall, bevel=0.05, seg=1))
    y = -D / 2
    parts.append(facade("front_l", wall, "-Y", y, -W / 2 - 0.01, gl, 0, GF, ops[:1] + ops[2:]))
    parts.append(facade("front_r", wall, "-Y", y, gr, W / 2 + 0.01, 0, GF, []))
    parts.append(facade("gate", wall, "-Y", y, gl, gr, 0.0, GF, [ops[1]], depth=D * 0.8, back=False))
    parts.append(box("gate_floor", (gate_w, D * 0.8, 0.06), (2.8, y + D * 0.4, 0), M("cobble")))
    col.append(box("c", (W / 2 + 0.8, D, GF + FL), (-W / 4, 0, 0)))
    col.append(box("c", (W / 2 - 4.3, D, GF + FL), (W / 2 - (W / 2 - 4.3) / 2, 0, 0)))
    col.append(box("c", (gate_w + 0.2, D, FL + 0.9), (2.8, 0, GF - 0.9)))
    # courtyard arcade seen through the passage
    for k in range(3):
        x = 2.8 - 2.4 + k * 2.4
        parts.append(cyl("arc_col", 0.18, 2.6, (x, y + D * 0.8 + 1.6, 0), M("stone"), verts=12, bevel=0.01, seg=1))
    parts.append(box("arc_beam", (6.0, 0.4, 0.5), (2.8, y + D * 0.8 + 1.6, 2.6), M("plaster_white")))
    parts.append(box("court_wall", (8.0, 0.3, 4.0), (2.8, y + D * 0.8 + 3.5, 0), M("plaster_white")))
    parts.append(box("court_floor", (8.0, 3.6, 0.04), (2.8, y + D * 0.8 + 1.8, 0), M("snow")))
    door_unit(parts, "-Y", y, -3.0, 1.8, 2.8, portal=False)
    st = M("stone_pale")
    for sx in (-1, 1):
        parts.append(box("pil", (0.42, 0.24, 3.9), (-3.0 + sx * 1.35, y - 0.12, 0.35), st, bevel=0.02, seg=1))
        parts.append(box("pil_base", (0.56, 0.32, 0.35), (-3.0 + sx * 1.35, y - 0.16, 0), M("stone"), bevel=0.02, seg=1))
        parts.append(box("pil_cap", (0.56, 0.32, 0.2), (-3.0 + sx * 1.35, y - 0.16, 4.25), st, bevel=0.02, seg=1))
    voussoirs(parts, "-Y", y, -3.0, 2.92, 1.8, 0.3, st, n=9, proud=0.1, key=0.14)
    parts.append(box("architrave", (3.4, 0.34, 0.24), (-3.0, y - 0.17, 4.45), st, bevel=0.02, seg=1))
    parts.append(box("frieze", (3.3, 0.26, 0.34), (-3.0, y - 0.13, 4.69), M("stone"), bevel=0.01, seg=1))
    parts.append(box("inscr", (2.2, 0.03, 0.2), (-3.0, y - 0.27, 4.76), M("gold", 0.4)))
    parts.append(box("cornice_p", (3.7, 0.44, 0.18), (-3.0, y - 0.22, 5.03), st, bevel=0.02, seg=1))
    parts.append(wedge("pediment", (3.4, 0.3, 0.6), (-3.0, y - 0.15, 5.21), st))
    voussoirs(parts, "-Y", y, 2.8, 2.6, gate_w, 0.36, M("stone"), n=11, proud=0.1, key=0.16)
    for sx in (-1, 1):
        parts.append(box("gjamb", (0.4, 0.2, 2.6), (2.8 + sx * (gate_w / 2 + 0.2), y - 0.1, 0), M("stone"), bevel=0.02, seg=1))
        parts.append(cyl("bumper", 0.22, 0.6, (2.8 + sx * (gate_w / 2 - 0.1), y + 0.3, 0), M("stone_dark"), verts=10, r2=0.12))
    win_unit(parts, "-Y", y, -5.6, 1.4, 0.9, 1.6, "rect", bars=True, surround="stone")
    parts.append(box("plinth", (W, 0.1, 0.5), (0, y - 0.03, 0), M("stone_dark")))
    uops = [(x, GF + 0.8, 1.1, 1.9, "rect") for x in (-5.0, -2.5, 0.0, 2.5, 5.0)]
    y2 = front_block(parts, W, D, FL, wall, uops, z0=GF)
    for (a, zb, w, h, sh) in uops:
        win_unit(parts, "-Y", y2, a, zb, w, h, sh, surround="stone_pale", warm=RNG.random() < 0.35)
    parts.append(box("string", (W + 0.16, 0.26, 0.22), (0, y - 0.08, GF - 0.12), st, bevel=0.02, seg=1))
    quoins(parts, W, D, 0.5, GF + FL, y)
    cornice(parts, W, D, GF + FL - 0.05, t=0.45, proud=0.35, modillions=False)
    for i in range(24):
        parts.append(box("modil", (0.12, 0.3, 0.13), (-W / 2 + i * W / 23, y - 0.15, GF + FL), M("stone")))
    top = GF + FL + 0.35
    pitched(parts, "roof", W + 0.8, D + 1.1, 4.4, (0, 0, top), M("tile"), courses=5)
    for x in (-3.5, 0.0, 3.5):
        dormer(parts, x, y + 1.1, top + 0.55, 1.2, 1.35, wall, M("tile_dark"), warm=x == 0.0)
    chimney(parts, -4.4, 1.2, top + 1.6, h=2.2)
    chimney(parts, 4.4, 1.6, top + 1.4, h=2.2)
    drainpipe(parts, -W / 2 + 0.25, y - 0.12, GF + FL - 0.2, [(1.0, y), (4.5, y2)])
    visual = join(parts, "kan_house")
    export("kan_house", visual, join(col, "col"))


# ------------------------------------------------------------------ WAWEL
def wawel_wall():
    """Curtain wall segment, 8 m along X, 2.4 m thick, 9 m to the wall-walk: battered sandstone base, brick upper
    wall, arrow loops, crenellated parapet with merlons. Outside face at -Y. Segments butt end to end."""
    reset()
    parts = []
    L, T, H = 8.0, 2.4, 9.0
    base = box("batter", (L, T + 0.6, 2.6), (0, 0.3, 0), M("stone"), bevel=0.03, seg=1)
    edit_verts(base, lambda co: setattr(co, "y", co.y + (0.6 if co.y < 0 and co.z > 1.0 else 0.0)))
    parts.append(base)
    ops = [(x, 4.8, 0.22, 1.4, "rect") for x in (-2.4, 0.0, 2.4)]
    parts.append(box("wall", (L, T - REV, H - 2.6), (0, REV / 2, 2.6), M("brick"), bevel=0.02, seg=1))
    parts.append(facade("face", M("brick"), "-Y", -T / 2, -L / 2, L / 2, 2.6, H, ops, depth=0.5))
    for (a, zb, w, h, sh) in ops:
        parts.append(box("loop_sill", (0.5, 0.2, 0.1), (a, -T / 2 - 0.05, zb - 0.1), M("stone")))
        parts.append(box("loop_cross", (0.6, 0.02, 0.12), (a, -T / 2 + 0.3, zb + 0.6), M("void")))
    parts.append(box("band", (L, 0.25, 0.25), (0, -T / 2 - 0.05, 2.55), M("stone"), bevel=0.02, seg=1))
    for k in range(5):
        parts.append(box("corbel", (0.3, 0.45, 0.4), (-L / 2 + 0.8 + k * 1.6, -T / 2 - 0.2, H - 0.4), M("stone"), bevel=0.02, seg=1))
    parts.append(box("parapet_base", (L, 0.7, 0.2), (0, -T / 2 - 0.1, H), M("stone"), bevel=0.02, seg=1))
    parts.append(box("parapet", (L, 0.6, 1.0), (0, -T / 2 - 0.05, H + 0.2), M("brick"), bevel=0.02, seg=1))
    for k in range(4):
        x = -L / 2 + 1.0 + k * 2.0
        parts.append(box("merlon", (1.1, 0.6, 1.1), (x, -T / 2 - 0.05, H + 1.2), M("brick"), bevel=0.02, seg=1, wonk=0.02))
        parts.append(box("merlon_cap", (1.2, 0.7, 0.1), (x, -T / 2 - 0.05, H + 2.3), M("stone")))
        parts.append(box("merlon_snow", (1.1, 0.6, 0.06), (x, -T / 2 - 0.05, H + 2.4), M("snow")))
    parts.append(box("walk", (L, T - 0.6, 0.1), (0, 0.3, H), M("stone_dark")))
    parts.append(box("walk_snow", (L - 0.2, T - 0.9, 0.05), (0, 0.35, H + 0.1), M("snow"), wonk=0.1))
    parts.append(box("inner_rail", (L, 0.3, 0.9), (0, T / 2 - 0.15, H), M("brick")))
    visual = join(parts, "wawel_wall")
    export("wawel_wall", visual, box("c", (L, T + 0.6, H + 1.2), (0, 0.3, 0)))


def wawel_gate():
    """Gate tower, 9 x 9 m, 16 m to the parapet: a vaulted passage straight through (walkable), a half-raised
    portcullis, arrow loops, machicolation corbels, a battlemented parapet and a pyramidal roof. Front at -Y."""
    reset()
    parts, col = [], []
    S, H = 9.0, 16.0
    gw, gh = 3.4, 3.4 + 1.7
    gate = (0.0, 0.0, gw, gh, "round")
    # the front facade's reveal runs the full depth: it is the passage; its rim folded back S is the side walls
    parts.append(facade("front", M("stone"), "-Y", -S / 2, -S / 2, S / 2, 0.0, 5.5, [gate], depth=S, back=False))
    parts.append(facade("back", M("stone"), "+Y", S / 2, -S / 2, S / 2, 0.0, 5.5, [gate], depth=0.01, back=False))
    ops = [(x, zz, 0.25, 1.5, "rect") for zz in (7.5, 11.0) for x in (-2.5, 2.5)] + [(0.0, 8.5, 1.0, 2.0, "round")]
    parts.append(box("upper", (S - 2 * 0.3, S - 2 * 0.3, H - 5.5), (0, 0, 5.5), M("brick"), bevel=0.02, seg=1))
    for face, plane in (("-Y", -S / 2), ("+Y", S / 2), ("-X", -S / 2), ("+X", S / 2)):
        parts.append(facade("up_" + face, M("brick"), face, plane, -S / 2, S / 2, 5.5, H, ops, depth=0.3))
    for (a, zb, w, h, sh) in ops:
        if w > 0.5:
            win_unit(parts, "-Y", -S / 2, a, zb, w, h, sh, surround=None, cross=False)
    parts.append(box("roofslab", (S, S, 0.3), (0, 0, 5.2), M("stone")))
    parts.append(box("band", (S + 0.3, S + 0.3, 0.3), (0, 0, 5.5), M("stone"), bevel=0.02, seg=1))
    voussoirs(parts, "-Y", -S / 2, 0.0, gh - gw / 2, gw, 0.5, M("stone_pale"), n=11, proud=0.12, key=0.2)
    parts.append(box("arms", (1.2, 0.12, 1.4), (0, -S / 2 - 0.1, 6.2), M("stone_pale"), bevel=0.03, seg=1))
    parts.append(cyl("arms_boss", 0.4, 0.1, (0, -S / 2 - 0.18, 6.9), M("gold", 0.4), verts=16, rot=(math.pi / 2, 0, 0), center=True))
    for k in range(7):
        parts.append(box("pc_v", (0.08, 0.1, 2.4), (-gw / 2 + 0.3 + k * (gw - 0.6) / 6, -S / 2 + 0.6, 2.6), M("iron")))
    for k in range(4):
        parts.append(box("pc_h", (gw - 0.2, 0.1, 0.08), (0, -S / 2 + 0.6, 2.8 + k * 0.6), M("iron")))
    for k in range(7):
        parts.append(cyl("pc_tooth", 0.05, 0.25, (-gw / 2 + 0.3 + k * (gw - 0.6) / 6, -S / 2 + 0.6, 2.35), M("iron"), verts=4, r2=0.005))
    for face, plane in (("-Y", -S / 2), ("+Y", S / 2), ("-X", -S / 2), ("+X", S / 2)):
        for k in range(6):
            a = -S / 2 + 0.75 + k * 1.5
            parts.append(fbox("corbel", face, plane, a, 0.25, H - 0.6, 0.35, 0.5, 0.6, M("stone"), bevel=0.02, seg=1))
    parts.append(box("parapet", (S + 1.0, S + 1.0, 1.0), (0, 0, H), M("brick"), bevel=0.02, seg=1))
    for sx in range(5):
        for side in range(4):
            x = -S / 2 - 0.2 + sx * (S + 0.4) / 4
            px, py = [(x, -S / 2 - 0.25), (x, S / 2 + 0.25), (-S / 2 - 0.25, x), (S / 2 + 0.25, x)][side]
            parts.append(box("merlon", (0.9, 0.9, 1.0), (px, py, H + 1.0), M("brick"), bevel=0.02, seg=1))
            parts.append(box("merlon_cap", (1.0, 1.0, 0.1), (px, py, H + 2.0), M("stone")))
    parts.append(pyramid("roof", (S - 0.4, S - 0.4, 6.0), (0, 0, H + 1.0), M("tile_dark"), apex=0.2))
    parts.append(pyramid("roof_snow", (S * 0.55, S * 0.55, 2.7), (0, 0, H + 4.35), M("snow"), apex=0.2))
    parts.append(cyl("finial", 0.12, 1.6, (0, 0, H + 7.0), M("gold", 0.4), verts=8, r2=0.02))
    visual = join(parts, "wawel_gate")
    for sx in (-1, 1):
        col.append(box("c", ((S - gw) / 2, S, H + 1), (sx * (S / 2 - (S - gw) / 4), 0, 0)))
    col.append(box("c", (gw, S, H + 1 - gh), (0, 0, gh)))
    export("wawel_gate", visual, join(col, "col"))


DISTRICT_BUILDS = [
    ("kaz_house_a", kaz_house_a), ("kaz_house_b", kaz_house_b), ("kaz_synagogue", kaz_synagogue),
    ("garb_workshop", garb_workshop), ("garb_house", garb_house), ("dock_granary", dock_granary),
    ("dock_wharf", dock_wharf), ("salt_barge", salt_barge), ("klep_house", klep_house), ("klep_stable", klep_stable),
    ("kan_house", kan_house), ("wawel_wall", wawel_wall), ("wawel_gate", wawel_gate),
]


# ------------------------------------------------------------------ FARMLAND outside the walls (Lesser Poland, 1795)
def farm_field():
    """8 x 8 m strip-field tile: furrows along X as real geometry matched to the baked furrow texture (snow in
    the troughs, soil and stubble on the ridges). Top near z=0; tiles seamlessly on an 8 m grid at one rotation."""
    reset()
    L = 8.0
    nx, ny = 8, 352
    bm = bmesh.new()
    rng = random.Random(8)
    lift = [rng.uniform(-0.02, 0.02) for _ in range(nx + 1)]
    lift[0] = lift[-1] = 0.0
    rows = []
    for j in range(ny + 1):
        yy = -L / 2 + L * j / ny
        cv = ((yy / 4.0 + 0.5) * 22.0) % 1.0
        z = 0.06 * (math.sin(math.pi * cv) - 0.5)
        rows.append([bm.verts.new((-L / 2 + L * i / nx, yy, z + lift[i])) for i in range(nx + 1)])
    for j in range(ny):
        for i in range(nx):
            bm.faces.new((rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]))
    o = _mesh_obj("field", bm, M("field"))
    _tag(o, mat=M("field"), offset=(0.5, 0.5))
    for p in o.data.polygons:
        p.use_smooth = True
    skirt = box("skirt", (L, L, 0.3), (0, 0, -0.33), M("field"))
    export("farm_field", join([o, skirt], "farm_field"), box("c", (L, L, 0.5), (0, 0, -0.5)))


def farm_fence():
    """Split-rail fence segment, 4 m along X, centred; posts at both ends (neighbouring segments share them)."""
    reset()
    parts = []
    for x in (-2.0, 0.0, 2.0):
        p = cyl("post", 0.08, 1.35, (x, 0, 0), M("timber"), verts=7, r2=0.065, bevel=0.01, seg=1)
        shear(p, RNG.uniform(-0.03, 0.03), RNG.uniform(-0.04, 0.04))
        parts.append(p)
        parts.append(cyl("post_snow", 0.07, 0.05, (x, 0, 1.35), M("snow"), verts=7))
    for zz, dy in ((0.55, 0.09), (1.05, -0.09)):
        for k in range(2):
            x0 = -2.0 + 2.0 * k
            r = box("rail", (2.3, 0.1, 0.13), (x0 + 1.0, dy, zz), M("wood"), bevel=0.02, seg=1, wonk=0.03)
            edit_verts(r, lambda co, x0=x0: setattr(co, "z", co.z - 0.05 * math.sin(math.pi * min(1, max(0, (co.x - x0) / 2.0)))))
            parts.append(r)
            parts.append(box("rail_snow", (2.1, 0.08, 0.04), (x0 + 1.0, dy, zz + 0.1), M("snow"), wonk=0.03))
    parts.append(box("drift", (4.0, 0.7, 0.18), (0, 0.1, 0), M("snow"), bevel=0.15, seg=2, wonk=0.1))
    export("farm_fence", join(parts, "farm_fence"), box("c", (4.2, 0.3, 1.3), (0, 0, 0)))


def log_corners(parts, W, D, H, n=10):
    """Crossed log ends sticking out at the four corners of a log house."""
    for k in range(n):
        z = (k + 0.5) * H / n
        for sx in (-1, 1):
            for sy in (-1, 1):
                if k % 2:
                    parts.append(cyl("logend", 0.12, 0.5, (sx * (W / 2 + 0.1), sy * D / 2, z), M("timber"), verts=6, rot=(0, math.pi / 2, 0), center=True))
                else:
                    parts.append(cyl("logend", 0.12, 0.5, (sx * W / 2, sy * (D / 2 + 0.1), z), M("timber"), verts=6, rot=(math.pi / 2, 0, 0), center=True))


def farm_cottage():
    """Chata: a limewashed log cottage on an oak sill, small windows with blue frames, a thatched hipped roof
    under snow and a limewashed chimney. Door on the long side facing -Y."""
    reset()
    parts = []
    W, D, H = 9.0, 6.0, 2.5
    wall = M("log_lime")
    ops = [(-1.2, 0.2, 0.95, 1.85, "rect"), (1.2, 0.9, 0.6, 0.7, "rect"), (3.0, 0.9, 0.6, 0.7, "rect"), (-3.2, 0.9, 0.6, 0.7, "rect")]
    parts.append(box("sill_beam", (W + 0.3, D + 0.3, 0.25), (0, 0, 0), M("timber"), bevel=0.03, seg=1, wonk=0.03))
    y = front_block(parts, W, D, H - 0.25, wall, ops, z0=0.25, wonk=0.05)
    parts.append(fbox("door", "-Y", y, -1.2, -REV + 0.05, 0.45, 0.92, 0.06, 1.83, M("shutter")))
    parts.append(fbox("door_x", "-Y", y, -1.2, -REV + 0.1, 1.1, 0.85, 0.03, 0.1, M("wood_dark")))
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb + 0.25, w, h, sh, surround=None, head=None, sill=False, cross=True, warm=RNG.random() < 0.5)
        parts.append(fbox("wframe", "-Y", y, a, 0.03, zb + 0.2, w + 0.2, 0.06, h + 0.12, M("plaster_limeblue")))
    parts.append(fbox("step", "-Y", y, -1.2, 0.3, 0, 1.2, 0.6, 0.2, M("stone_dark"), bevel=0.03, seg=1))
    log_corners(parts, W, D, H)
    parts.append(hip_roof("roof", W + 1.6, D + 1.8, 3.9, (0, 0, H), M("thatch"), hip=2.0, thick=0.35))
    parts.append(hip_snow("roof_snow", W + 1.6, D + 1.8, 3.9, (0, 0, H), hip=2.0))
    parts.append(box("ridge", (W - 2.0, 0.5, 0.25), (0, 0, H + 3.8), M("thatch"), bevel=0.1, seg=2))
    parts.append(box("chim", (0.8, 0.8, 1.6), (0.9, 0.3, H + 3.0), M("plaster_lime"), bevel=0.04, seg=1, wonk=0.05))
    parts.append(box("chim_cap", (0.95, 0.95, 0.1), (0.9, 0.3, H + 4.6), M("snow"), bevel=0.03, seg=1))
    parts.append(box("drift", (W + 1.0, 1.0, 0.25), (0, y - 0.8, 0), M("snow"), bevel=0.2, seg=2, wonk=0.12))
    parts.append(box("bench", (1.6, 0.35, 0.08), (1.9, y - 0.4, 0.45), M("wood")))
    for x in (1.3, 2.5):
        parts.append(box("bench_leg", (0.08, 0.3, 0.45), (x, y - 0.4, 0), M("wood")))
    visual = join(parts, "farm_cottage")
    shear(visual, 0.006, -0.005)
    export("farm_cottage", visual, box("c", (W + 0.3, D + 0.3, H + 4.0), (0, 0, 0)))


def farm_barn():
    """Stodola: an oak-framed barn of vertical boards with a great double door (one leaf ajar) and a steep
    thatched roof under snow."""
    reset()
    parts, col = [], []
    W, D, H = 14.0, 8.0, 4.0
    boards = M("timber")
    dw, dh = 4.0, 3.6
    ops = [(0.0, 0.0, dw, dh, "rect")]
    y = front_block(parts, W, D, H, boards, ops, wonk=0.05)
    parts.append(fbox("leaf_l", "-Y", y, -dw / 4, -REV + 0.06, 0.05, dw / 2 - 0.04, 0.08, dh - 0.1, M("wood")))
    leaf = fbox("leaf_r", "-Y", y, dw / 4, -REV + 0.06, 0.05, dw / 2 - 0.04, 0.08, dh - 0.1, M("wood"))
    c, s = math.cos(0.5), math.sin(0.5)
    hx, hy = dw / 2, y - REV + 0.06
    def swing(co):
        dx, dy = co.x - hx, co.y - hy
        co.x, co.y = hx + dx * c + dy * s, hy - dx * s + dy * c
    edit_verts(leaf, swing)
    parts.append(leaf)
    parts.append(slab("dark", outline(dw / 4, 0.05, dw / 2, dh - 0.1), "-Y", y, -REV + 0.0, -REV + 0.01, M("void")))
    for zz in (0.5, dh - 0.8):
        parts.append(fbox("brace", "-Y", y, -dw / 4, -REV + 0.12, zz, dw / 2 - 0.2, 0.04, 0.16, M("wood_dark")))
    parts.append(fbox("lintel", "-Y", y, 0, 0.05, dh, dw + 0.8, 0.14, 0.3, M("wood_dark")))
    for x in (-W / 2, -W / 4, -dw / 2 - 0.1, dw / 2 + 0.1, W / 4, W / 2):
        parts.append(fbox("post", "-Y", y, x, 0.07, 0, 0.26, 0.14, H, M("wood_dark"), bevel=0.01, seg=1))
    parts.append(box("sole", (W + 0.3, D + 0.3, 0.3), (0, 0, 0), M("stone_dark"), bevel=0.03, seg=1, wonk=0.04))
    for sx in (-1, 1):
        gable_slab(parts, "-X" if sx < 0 else "+X", sx * W / 2, -D / 2, D / 2, H, 2.2, boards, thick=0.1, out=0.02)
    parts.append(hip_roof("roof", W + 1.4, D + 1.8, 5.2, (0, 0, H), M("thatch"), hip=1.6, thick=0.35))
    parts.append(hip_snow("roof_snow", W + 1.4, D + 1.8, 5.2, (0, 0, H), hip=1.6))
    parts.append(box("ridge", (W - 2.4, 0.5, 0.3), (0, 0, H + 5.1), M("thatch"), bevel=0.1, seg=2))
    parts.append(box("straw", (2.0, 1.6, 0.7), (0.4, y + 1.2, 0), M("hay"), bevel=0.3, seg=2, wonk=0.2))
    visual = join(parts, "farm_barn")
    export("farm_barn", visual, box("c", (W, D, H + 5.0), (0, 0, 0)))


def _haystack(name, R, H):
    reset()
    parts = [cyl("stack", R, H * 0.45, (0, 0, 0), M("hay"), verts=16, r2=R * 1.05, bevel=0.1, seg=2),
             sphere("top", R * 1.05, (0, 0, H * 0.45), M("hay"), seg=16, rings=10, zscale=(H * 0.55) / (R * 1.05))]
    bm = bmesh.new()
    bm.from_mesh(parts[1].data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < H * 0.45 - 0.01], context="VERTS")
    bm.to_mesh(parts[1].data)
    bm.free()
    parts.append(sphere("snowcap", R * 0.8, (0, 0, H * 0.45 + H * 0.22), M("snow"), seg=16, rings=8, zscale=(H * 0.36) / (R * 0.8)))
    bm = bmesh.new()
    bm.from_mesh(parts[-1].data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < H * 0.72], context="VERTS")
    bm.to_mesh(parts[-1].data)
    bm.free()
    parts.append(cyl("pole", 0.06, H + 0.7, (0, 0, 0), M("timber"), verts=6, r2=0.035))
    parts.append(box("skirt", (R * 2.2, R * 2.2, 0.15), (0, 0, 0), M("snow"), bevel=0.3, seg=2, wonk=0.2))
    for k in range(4):
        a = math.tau * k / 4 + 0.4
        parts.append(cyl("rope", 0.02, H * 0.7, (R * 0.9 * math.cos(a), R * 0.9 * math.sin(a), H * 0.2), M("canvas"), verts=4, rot=(0.25 * math.sin(a), -0.25 * math.cos(a), 0)))
    export(name, join(parts, name), cyl("c", R, H * 0.8, (0, 0, 0), None, verts=8))


def farm_haystack():
    """Stog: a tall hay rick around a central pole, tied down, snow on its crown (4.5 m)."""
    _haystack("farm_haystack", 1.9, 4.5)


def farm_haystack_small():
    _haystack("farm_haystack_small", 1.1, 2.4)


def farm_mill():
    """Water mill on a stream: timber mill house with a thatched roof, an overshot wheel on the +X side fed by a
    wooden flume, the stream running along Y in a stone-banked channel (water at z=-0.35)."""
    reset()
    parts, col = [], []
    W, D, H = 7.0, 8.0, 3.8
    boards = M("timber")
    ops = [(-1.0, 0.0, 1.1, 2.1, "rect"), (1.6, 1.3, 0.7, 0.8, "rect")]
    parts.append(box("footing", (W + 0.3, D + 0.3, 0.5), (0, 0, 0), M("stone"), bevel=0.03, seg=1, wonk=0.04))
    y = front_block(parts, W, D, H - 0.5, boards, ops, z0=0.5)
    parts.append(fbox("door", "-Y", y, -1.0, -REV + 0.05, 0.5, 1.06, 0.06, 2.06, M("wood_dark")))
    parts.append(fbox("step", "-Y", y, -1.0, 0.35, 0, 1.4, 0.7, 0.5, M("stone_dark"), bevel=0.03, seg=1))
    win_unit(parts, "-Y", y, 1.6, 1.8, 0.7, 0.8, "rect", surround=None, head=None, cross=True, warm=True)
    for x in (-W / 2, 0.0, W / 2):
        parts.append(fbox("post", "-Y", y, x, 0.07, 0.5, 0.24, 0.14, H - 0.5, M("wood_dark"), bevel=0.01, seg=1))
    col.append(box("c", (W + 0.3, D + 0.3, H), (0, 0, 0)))
    parts.append(hip_roof("roof", W + 1.4, D + 1.6, 3.6, (0, 0, H), M("thatch"), hip=1.4, thick=0.3))
    parts.append(hip_snow("roof_snow", W + 1.4, D + 1.6, 3.6, (0, 0, H), hip=1.4))
    parts.append(box("chim", (0.6, 0.6, 1.4), (-1.5, 1.5, H + 2.2), M("brick"), bevel=0.03, seg=1))
    # stream and banks along Y beside the +X wall
    sx0 = W / 2 + 1.4
    parts.append(box("water", (2.4, 16.0, 0.02), (sx0, 0, -0.37), M("water", 0.08)))
    for dx in (-1.3, 1.3):
        parts.append(box("bank", (0.5, 16.0, 0.6), (sx0 + dx, 0, -0.55), M("stone_dark"), bevel=0.04, seg=1, wonk=0.06))
    parts.append(box("bed", (2.4, 16.0, 0.1), (sx0, 0, -0.9), M("stone_dark")))
    parts.append(box("ice", (0.8, 5.0, 0.03), (sx0 + 0.7, -4.0, -0.35), M("snow"), wonk=0.2))
    # overshot wheel: two rims, spokes, paddles, axle into the wall
    R = 2.2
    wc = (sx0, 0.0, R - 0.25)
    for dx in (-0.4, 0.4):
        parts.append(torus("rim", R, 0.07, (wc[0] + dx, wc[1], wc[2]), M("wood_dark"), rot=(0, math.pi / 2, 0), seg=24, mseg=5))
        for k in range(8):
            a = math.tau * k / 8
            parts.append(cbox("spoke", (0.08, 0.1, R * 2), (wc[0] + dx, wc[1], wc[2]), M("wood"), rot=(a, 0, 0)))
    for k in range(16):
        a = math.tau * k / 16
        parts.append(cbox("paddle", (0.9, 0.06, 0.45), (wc[0], wc[1] + (R - 0.15) * math.cos(a), wc[2] + (R - 0.15) * math.sin(a)), M("wood"), rot=(a, 0, 0)))
    parts.append(cyl("axle", 0.14, 2.2, (W / 2 + 0.4, 0.0, wc[2]), M("timber"), verts=10, rot=(0, math.pi / 2, 0), center=True))
    parts.append(box("bearing", (0.4, 0.5, 0.5), (sx0 + 0.75, 0.0, wc[2] - 0.5), M("stone"), bevel=0.02, seg=1))
    col.append(box("c", (1.2, 2 * R, 2 * R), (sx0, 0, 0)))
    # flume on trestles bringing water over the top of the wheel
    fz = wc[2] + R + 0.15
    parts.append(box("flume", (0.9, 6.0, 0.35), (sx0, -3.3, fz), M("wood"), bevel=0.02, seg=1))
    parts.append(box("flume_water", (0.7, 6.0, 0.02), (sx0, -3.3, fz + 0.28), M("water", 0.08)))
    for yy in (-5.5, -3.0):
        for dx in (-0.35, 0.35):
            parts.append(box("trestle", (0.14, 0.14, fz + 0.37), (sx0 + dx, yy, -0.37), M("timber")))
    visual = join(parts, "farm_mill")
    export("farm_mill", visual, join(col, "col"))


def farm_shrine():
    """Roadside kapliczka: a limewashed brick pillar on a stone step with a glazed niche holding a small figure
    of the Virgin, a tin-roofed cap and an iron cross."""
    reset()
    parts = []
    S, H = 0.9, 2.2
    parts.append(box("step", (1.5, 1.5, 0.25), (0, 0, 0), M("stone_dark"), bevel=0.03, seg=1, wonk=0.03))
    parts.append(box("pillar", (S, S - 0.3, H), (0, 0.15, 0.25), M("plaster_lime"), bevel=0.03, seg=1, wonk=0.03))
    niche = (0.0, 1.35, 0.5, 0.8, "round")
    parts.append(facade("niche_f", M("plaster_lime"), "-Y", -S / 2, -S / 2 - 0.01, S / 2 + 0.01, 0.25, H + 0.25, [niche], depth=0.3))
    parts.append(box("niche_sill", (0.66, 0.22, 0.06), (0, -S / 2 - 0.02, 1.29), M("stone")))
    parts.append(cyl("robe", 0.1, 0.45, (0, -S / 2 + 0.16, 1.35), M("navy"), verts=10, r2=0.06))
    parts.append(sphere("head", 0.055, (0, -S / 2 + 0.16, 1.86), M("plaster_white"), seg=10, rings=6))
    parts.append(torus("halo", 0.08, 0.008, (0, -S / 2 + 0.2, 1.9), M("gold", 0.3), rot=(math.pi / 2, 0, 0), seg=12, mseg=4))
    parts.append(slab("niche_glass", outline(0.0, 1.35, 0.5, 0.8, "round"), "-Y", -S / 2, -0.02, 0.0, M("glass")))
    parts.append(box("cornice", (S + 0.2, S + 0.2, 0.12), (0, 0, H + 0.25), M("plaster_lime"), bevel=0.03, seg=1))
    parts.append(pyramid("cap", (S + 0.3, S + 0.3, 0.7), (0, 0, H + 0.37), M("lead"), apex=0.02))
    parts.append(pyramid("cap_snow", (S * 0.7, S * 0.7, 0.45), (0, 0, H + 0.62), M("snow"), apex=0.02))
    parts.append(box("cross_v", (0.04, 0.04, 0.6), (0, 0, H + 1.05), M("iron")))
    parts.append(box("cross_h", (0.3, 0.04, 0.04), (0, 0, H + 1.45), M("iron")))
    parts.append(box("drift", (1.6, 1.6, 0.1), (0, 0.1, 0.0), M("snow"), bevel=0.2, seg=2, wonk=0.1))
    export("farm_shrine", join(parts, "farm_shrine"), box("c", (1.5, 1.5, H + 0.4), (0, 0, 0)))


def farm_manor():
    """Folwark manor (dwor): single storey, limewashed, a four-column porch with a pediment, a broken
    (mansard) roof with dormers, shuttered windows and two chimneys."""
    reset()
    parts, col = [], []
    W, D, H = 22.0, 12.0, 4.2
    wall = M("plaster_white")
    xs = [-9.2, -6.6, -4.0, 4.0, 6.6, 9.2, -1.4, 1.4]
    ops = [(0.0, 0.0, 1.6, 3.2 + 0.12 + 0.8, "round")] + [(x, 1.1, 1.1, 1.9, "rect") for x in xs]
    y = front_block(parts, W, D, H, wall, ops)
    plinth(parts, -W / 2, W / 2, y, h=0.55, proud=0.06, mat=M("plaster_white_damp"), skip=[(-3.1, 3.1)])
    col.append(box("c", (W, D, H + 4.0), (0, 0, 0)))
    door_unit(parts, "-Y", y, 0.0, 1.6, 3.2, portal=False)
    for x in xs:
        win_unit(parts, "-Y", y, x, 1.1, 1.1, 1.9, "rect", shutters=True, surround="plaster_white", warm=RNG.random() < 0.4)
    cornice(parts, W, D, H - 0.05, t=0.35, proud=0.28, modillions=False, mat=M("plaster_white"))
    # porch: steps, four columns, entablature, pediment, its own little roof
    py = y - 2.2
    parts.append(box("porch_floor", (6.0, 2.6, 0.55), (0, y - 1.3, 0), M("stone"), bevel=0.03, seg=1))
    for k in range(3):
        parts.append(box("porch_step", (3.0, 0.35, 0.18 * (3 - k)), (0, y - 2.6 - 0.35 * (k + 0.5), 0), M("stone"), bevel=0.02, seg=1))
    for x in (-2.4, -0.8, 0.8, 2.4):
        parts.append(cyl("col", 0.2, 3.1, (x, py, 0.55), M("plaster_white"), verts=12, r2=0.17, bevel=0.01, seg=1))
        parts.append(box("col_cap", (0.5, 0.5, 0.16), (x, py, 3.62), M("stone"), bevel=0.02, seg=1))
        parts.append(box("col_base", (0.5, 0.5, 0.14), (x, py, 0.55), M("stone"), bevel=0.02, seg=1))
    parts.append(box("entab", (5.6, 2.6, 0.45), (0, y - 1.25, 3.78), M("plaster_white"), bevel=0.03, seg=1))
    parts.append(slab("pediment", [(-2.9, 4.23), (2.9, 4.23), (0.0, 5.4)], "-Y", py - 0.2, -0.25, 0.1, M("plaster_white")))
    parts.append(cyl("oculus", 0.28, 0.06, (0, py - 0.32, 4.7), M("glass"), verts=12, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(roof("porch_roof", 2.8, 6.2, 1.2, (0, y - 1.2, 4.23), M("tile_dark"), along_x=False, sag=0.02, flare=0.03, cuts=3))
    parts.append(roof("porch_snow", 2.7, 3.0, 0.62, (0, y - 1.2, 4.83), M("snow"), along_x=False, sag=0.02, top_w=0.2, cuts=3))
    # mansard (lamany) roof
    top = H + 0.3
    parts.append(roof("mansard_lo", W + 0.8, D + 1.2, 2.3, (0, 0, top), M("tile_dark"), sag=0.06, flare=-0.05, top_w=(D + 1.2) * 0.55, courses=3))
    parts.append(roof("mansard_hi", W + 0.8, (D + 1.2) * 0.55, 1.8, (0, 0, top + 2.3), M("tile_dark"), sag=0.08, flare=0.05, courses=2, ridge=True))
    parts.append(roof("mansard_snow", W + 0.6, (D + 1.2) * 0.5, 1.75, (0, 0, top + 2.38), M("snow"), sag=0.08, flare=0.05, top_w=0.3))
    for x in (-6.6, 6.6):
        dormer(parts, x, -D / 2 + 0.3, top + 0.35, 1.2, 1.4, wall, M("tile_dark"), depth=1.8, warm=False)
    for x in (-5.0, 5.0):
        chimney(parts, x, 0.8, top + 2.8, h=1.6)
    parts.append(box("drift", (W, 1.0, 0.2), (0, y - 0.6, 0), M("snow"), bevel=0.2, seg=2, wonk=0.15))
    visual = join(parts, "farm_manor")
    export("farm_manor", visual, join(col, "col"))


FARM_BUILDS = [
    ("farm_field", farm_field), ("farm_fence", farm_fence), ("farm_cottage", farm_cottage), ("farm_barn", farm_barn),
    ("farm_haystack", farm_haystack), ("farm_haystack_small", farm_haystack_small), ("farm_mill", farm_mill),
    ("farm_shrine", farm_shrine), ("farm_manor", farm_manor),
]
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
    """Smok Wawelski now lives in build_animals.py (rigged, scale texture baked, idle clip, glowing eyes and
    nostrils): delegate, so `build_assets.py -- --animals` still writes the same dragon.glb."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("krakow_build_animals", os.path.join(ROOT, "assets", "blender", "build_animals.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.dragon()


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


# ------------------------------------------------------------------ build
# ------------------------------------------------------------------ DRESSING: the lived-in pass (placed by scripts/city/dressing.gd)
# Winter 1795/96 flavour props: bare limes and chestnuts, tubbed yews, window boxes, ivy, dead grass, guild signs on
# iron brackets, painted fascia boards, shop fronts, a cafe, an inn with its coach, benches, a railed churchyard green
# and the clutter of a town that is used: crates, sacks, sledges, laundry, brooms and trampled snow.
# Wall-mounted pieces have their origin on the wall face (front = Blender -Y); free-standing ones at their base centre.
from mathutils import Quaternion

PAL.update({
    "bark": (0.15, 0.135, 0.12), "terracotta": (0.60, 0.30, 0.18), "ivy": (0.09, 0.19, 0.09), "ivy_pale": (0.16, 0.26, 0.12),
    "yew": (0.06, 0.15, 0.07), "juniper": (0.12, 0.20, 0.14), "dead_grass": (0.50, 0.42, 0.27), "dead_stalk": (0.33, 0.26, 0.16),
    "soil": (0.14, 0.10, 0.07), "paper": (0.86, 0.82, 0.70), "paper_old": (0.76, 0.70, 0.55), "ink": (0.06, 0.05, 0.05),
    "sign_green": (0.10, 0.22, 0.15), "sign_red": (0.42, 0.08, 0.08), "sign_blue": (0.10, 0.15, 0.30),
    "sign_black": (0.05, 0.05, 0.06), "sign_wine": (0.30, 0.06, 0.10), "crust": (0.62, 0.38, 0.16), "crust_dark": (0.42, 0.24, 0.10),
    "bottle": (0.06, 0.16, 0.09), "bottle_brown": (0.22, 0.10, 0.04), "bolt_red": (0.60, 0.14, 0.12), "bolt_blue": (0.18, 0.26, 0.50),
    "bolt_green": (0.22, 0.40, 0.26), "linen": (0.90, 0.88, 0.82), "sacking": (0.62, 0.52, 0.36),
    "flower_white": (0.92, 0.90, 0.84), "flower_pink": (0.70, 0.40, 0.50), "leaf_dark": (0.07, 0.15, 0.08),
    "rosemary": (0.24, 0.30, 0.24), "bay_leaf": (0.12, 0.22, 0.10), "grape": (0.22, 0.07, 0.18), "bronze": (0.50, 0.34, 0.16),
    "muck": (0.17, 0.12, 0.08), "gravel": (0.50, 0.47, 0.43), "snow_dirty": (0.66, 0.66, 0.68), "ice": (0.62, 0.72, 0.80),
    "coach_green": (0.08, 0.17, 0.12), "coach_red": (0.40, 0.10, 0.07), "leather": (0.20, 0.12, 0.07), "berry": (0.55, 0.08, 0.06),
    "dried_flower": (0.62, 0.36, 0.20), "coffee": (0.10, 0.06, 0.04), "mud": (0.16, 0.13, 0.10),
})


def _tx_slush(g):
    """Trodden street snow: grey-blue packed slush, boot prints pressed into it in loose staggered rows, dirt
    streaks dragged along by cart wheels and soles, grit freckles. Matte (roughness ~0.85)."""
    lumps = g.noise(5, 5, 4, 0.55, seed=61)
    fine = g.noise(120, 120, 2, seed=62)
    # boot prints: one oval pit pair (toe, heel) per staggered cell, turned and shifted per cell, some cells empty
    cu, cv, iu, iv, par = g.cells(7, 5, stagger=0.5)
    jit = g.white(iu, iv, 3.0)
    jit2 = g.white(iu, iv, 7.0)
    keep = g.smooth(jit, 0.35, 0.42)
    ang = g.mul(g.sub(jit2, 0.5), 2.2)
    ca, sa = g.m("COSINE", ang), g.m("SINE", ang)
    ox = g.sub(cu, g.add(0.5, g.mul(g.sub(jit2, 0.5), 0.35)))
    oy = g.sub(cv, g.add(0.5, g.mul(g.sub(jit, 0.5), 0.25)))
    rx = g.sub(g.mul(ox, ca), g.mul(oy, sa))
    ry = g.add(g.mul(ox, sa), g.mul(oy, ca))
    dx = g.mul(rx, 3.4)
    dy = g.mul(ry, 1.5)
    d_toe = g.add(g.mul(dx, dx), g.mul(g.sub(dy, -0.12), g.sub(dy, -0.12)))
    d_heel = g.add(g.mul(dx, dx), g.mul(g.mul(g.sub(dy, 0.3), 1.6), g.mul(g.sub(dy, 0.3), 1.6)))
    pit = g.mul(g.mx(g.one_minus(g.smooth(d_toe, 0.04, 0.12)), g.one_minus(g.smooth(d_heel, 0.02, 0.07))), keep)
    streak = g.smooth(g.noise(1.5, 14, 3, 0.5, seed=63), 0.52, 0.72)
    grit = g.smooth(fine, 0.7, 0.76)
    col = g.mix(lumps, (0.37, 0.40, 0.45), (0.46, 0.49, 0.54))
    col = g.mix(g.mul(pit, 0.5), col, (0.33, 0.34, 0.36))
    col = g.mix(g.mul(streak, 0.6), col, (0.30, 0.27, 0.23))
    col = g.mix(g.mul(grit, 0.5), col, (0.16, 0.15, 0.14))
    h = g.sub(g.add(g.mul(lumps, 0.45), g.mul(fine, 0.08)), g.add(g.mul(pit, 0.4), g.mul(streak, 0.12)))
    rough = g.add(0.8, g.mul(fine, 0.1))
    return col, rough, h, 0.035


def _tx_hedge(g):
    """Clipped yew/box in winter: small leaf clusters (bright tips, dark gaps between them), bronzed winter
    patches, deep near-black hollows where the shell thins."""
    cell = g.voronoi(70, 70, seed=71)
    cell2 = g.voronoi(150, 150, seed=72)
    leaf = g.one_minus(g.smooth(cell, 0.3, 0.75))
    leaf2 = g.one_minus(g.smooth(cell2, 0.3, 0.7))
    bronze = g.smooth(g.noise(4, 4, 4, 0.55, seed=73), 0.55, 0.72)
    hollow = g.smooth(g.noise(9, 9, 3, 0.5, seed=74), 0.64, 0.74)
    col = g.mix(g.add(g.mul(leaf, 0.7), g.mul(leaf2, 0.3)), (0.012, 0.025, 0.012), (0.07, 0.13, 0.05))
    col = g.mix(g.mul(bronze, 0.4), col, (0.11, 0.09, 0.04))
    col = g.mix(g.mul(hollow, 0.8), col, (0.015, 0.02, 0.012))
    h = g.sub(g.add(g.mul(leaf, 0.6), g.mul(leaf2, 0.25)), g.mul(hollow, 0.5))
    rough = g.add(0.72, g.mul(g.one_minus(leaf), 0.18))
    return col, rough, h, 0.02


def _tx_juniper(g):
    """Juniper / rosemary foliage: finer needle clusters than the hedge, blue-green with grey bloom, dark gaps."""
    cell = g.voronoi(130, 130, seed=81)
    cell2 = g.voronoi(260, 260, seed=82)
    leaf = g.one_minus(g.smooth(cell, 0.3, 0.75))
    leaf2 = g.one_minus(g.smooth(cell2, 0.3, 0.7))
    bloom = g.smooth(g.noise(5, 5, 4, 0.55, seed=83), 0.5, 0.7)
    hollow = g.smooth(g.noise(10, 10, 3, 0.5, seed=84), 0.64, 0.74)
    col = g.mix(g.add(g.mul(leaf, 0.65), g.mul(leaf2, 0.35)), (0.012, 0.025, 0.022), (0.07, 0.13, 0.11))
    col = g.mix(g.mul(bloom, 0.45), col, (0.13, 0.17, 0.16))
    col = g.mix(g.mul(hollow, 0.8), col, (0.012, 0.018, 0.016))
    h = g.sub(g.add(g.mul(leaf, 0.55), g.mul(leaf2, 0.3)), g.mul(hollow, 0.5))
    rough = g.add(0.7, g.mul(g.one_minus(leaf), 0.2))
    return col, rough, h, 0.015


RECIPES.update({"slush": _tx_slush, "hedge": _tx_hedge, "juniper": _tx_juniper})
TEXSPEC.update({"slush": (1024, 2.0), "hedge": (1024, 2.0), "juniper": (1024, 2.0)})
PAL.update({"snow_dirty": (0.55, 0.58, 0.62), "hedge_leaf": (1.0, 1.0, 1.0), "juniper_leaf": (1.0, 1.0, 1.0), "rosemary_leaf": (1.0, 1.0, 1.0), "bay_leafy": (1.0, 1.0, 1.0), "hedge_core": (0.012, 0.018, 0.01)})
TEX_OF.update({"bolt_red": "cloth", "bolt_blue": "cloth", "bolt_green": "cloth", "linen": "cloth",
               "sacking": "cloth", "snow_dirty": "slush", "hedge_leaf": "hedge", "juniper_leaf": "juniper", "rosemary_leaf": "juniper", "bay_leafy": "hedge", "coach_green": "oak", "coach_red": "oak"})
TINT.update({"bark": (0.52, 0.47, 0.42), "snow_dirty": (1.0, 1.0, 1.0), "hedge_leaf": (1.0, 1.0, 1.0), "juniper_leaf": (0.9, 1.0, 1.08), "rosemary_leaf": (1.25, 1.3, 1.2), "bay_leafy": (1.1, 1.2, 1.0), "sacking": (0.80, 0.70, 0.52),
             "coach_green": (0.26, 0.42, 0.32), "coach_red": (0.78, 0.36, 0.28)})
_SERIF = [p for p in ("/usr/share/fonts/liberation/LiberationSerif-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSerif-Bold.ttf",
                      "/usr/share/fonts/noto/NotoSerif-Bold.ttf") if os.path.exists(p)]


def _tube(bm, p0, p1, r0, r1, n=6):
    """Open frustum between two points into a bmesh (r1 = 0 closes it to a point). Faces point outward."""
    p0, p1 = Vector(p0), Vector(p1)
    ax = p1 - p0
    if ax.length < 1e-6:
        return
    ax.normalize()
    ref = Vector((0, 0, 1)) if abs(ax.z) < 0.9 else Vector((1, 0, 0))
    u = ax.cross(ref).normalized()
    v = ax.cross(u)
    angs = [math.tau * k / n for k in range(n)]
    ring0 = [bm.verts.new(p0 + (u * math.cos(a) + v * math.sin(a)) * r0) for a in angs]
    if r1 <= 1e-5:
        tip = bm.verts.new(p1)
        for k in range(n):
            f = bm.faces.new((ring0[k], ring0[(k + 1) % n], tip))
            f.smooth = True
        return
    ring1 = [bm.verts.new(p1 + (u * math.cos(a) + v * math.sin(a)) * r1) for a in angs]
    for k in range(n):
        f = bm.faces.new((ring0[k], ring0[(k + 1) % n], ring1[(k + 1) % n], ring1[k]))
        f.smooth = True


def _bm_obj(name, bm, mat):
    o = _mesh_obj(name, bm, mat)
    return o


def _quad(bm, pts, smooth=False):
    f = bm.faces.new([bm.verts.new(Vector(p)) for p in pts])
    f.smooth = smooth
    return f


def _lumpy(name, r, center, mat, zscale=1.0, amp=0.15, seed=0, seg=12, rings=8, zmin=None):
    """Irregular rounded mass (shrub, snow heap, sack): a UV sphere with every vertex pushed in or out."""
    o = sphere(name, r, center, mat, seg=seg, rings=rings, zscale=zscale, smooth=70)
    rng = random.Random(seed)
    cx, cy, cz = center

    def f(co):
        k = 1.0 + rng.uniform(-amp, amp)
        co.x = cx + (co.x - cx) * k
        co.y = cy + (co.y - cy) * k
        co.z = cz + (co.z - cz) * k
        if zmin is not None and co.z < zmin:
            co.z = zmin
    return edit_verts(o, f)


def _text(name, body, size, loc, mat, depth=0.006, width=None, res=2):
    """Serif lettering standing on a -Y face, centred at loc (x, y_front, z), converted to a mesh."""
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.object.text_add(location=(0, 0, 0))
    o = bpy.context.object
    cu = o.data
    cu.body = body
    if _SERIF:
        cu.font = bpy.data.fonts.load(_SERIF[0], check_existing=True)
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.size = size
    cu.extrude = depth
    cu.resolution_u = res
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.convert(target="MESH")
    o = bpy.context.object
    if width and o.dimensions.x > width:
        s = width / o.dimensions.x
        o.scale = (s, s, s)
    o.rotation_euler = (math.pi / 2, 0, 0)
    o.location = loc
    return _finish_prim(o, name, mat)


def _slush_patch(name, outline, centre, lift=0.018, seed=0):
    """Packed slush lying on the setts: a low mound over `outline` (closed list of (x, y)) with a thin lip at 6 mm.
    dressing.gd fades alpha from 1 at 55 % of the radius to 0 at that lip, so no disc edge shows on the cobbles."""
    rng = random.Random(seed)
    bm = bmesh.new()
    cx, cy = centre
    c = bm.verts.new((cx, cy, lift))
    mid, rim = [], []
    for (x, y) in outline:
        mid.append(bm.verts.new((cx + (x - cx) * 0.55, cy + (y - cy) * 0.55, lift * rng.uniform(0.7, 0.95))))
        rim.append(bm.verts.new((x, y, 0.006)))
    n = len(outline)
    for k in range(n):
        j = (k + 1) % n
        bm.faces.new((c, mid[k], mid[j]))
        bm.faces.new((mid[k], rim[k], rim[j], mid[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        if f.normal.z < 0:
            f.normal_flip()
        f.smooth = True
    rim_set = set(rim)
    col = bm.loops.layers.color.new("Col")
    for f in bm.faces:
        for lp in f.loops:
            lp[col] = (1.0, 1.0, 1.0, 0.0 if lp.vert in rim_set else 1.0)
    return _bm_obj(name, bm, _slush_mat())


def _slush_mat():
    """The slush material, exported with glTF alphaMode BLEND. The exporter does not write the "Col" rim alpha to
    COLOR_0, so scripts/city/dressing.gd rebuilds the fade from vertex height (rim verts sit at 6 mm)."""
    m = M("slush_trod")          # not "*snow*": Assets' weather pass would swap it for the melt shader
    if not m.get("feather"):
        nt = m.node_tree
        bsdf = nt.nodes["Principled BSDF"]
        vc = nt.nodes.new("ShaderNodeVertexColor")
        vc.layer_name = "Col"
        nt.links.new(vc.outputs["Alpha"], bsdf.inputs["Alpha"])
        try:
            m.surface_render_method = "BLENDED"
        except AttributeError:
            m.blend_method = "BLEND"
        m["feather"] = 1
    return m


def _blob_outline(r, n, seed, sx=1.0, sy=1.0):
    rng = random.Random(seed)
    ph = [rng.uniform(0, math.tau) for _ in range(3)]
    out = []
    for k in range(n):
        a = math.tau * k / n
        rr = r * (1 + 0.14 * math.sin(3 * a + ph[0]) + 0.08 * math.sin(5 * a + ph[1]) + rng.uniform(-0.06, 0.06))
        out.append((math.cos(a) * rr * sx, math.sin(a) * rr * sy))
    return out


# ------------------------------------------------------------------ trees
def _tree(name, seed, trunk_h, trunk_r, L0, depth, kids, spread, up, snow_levels=(1, 2, 3)):
    """Bare winter tree: a leaning trunk that forks into `kids`+leader branches per level, snow along the upper
    side of the near-horizontal limbs. One bark mesh plus one snow mesh."""
    reset()
    rng = random.Random(seed)
    bm, sb = bmesh.new(), bmesh.new()

    def grow(p, d, L, r, lvl):
        n = max(4, 8 - lvl)
        if lvl <= 2:
            mid = p + d * (L * 0.5) + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.3, 0.3))) * L * 0.07
            _tube(bm, p, mid, r, r * 0.84, n)
            _tube(bm, mid, p + d * L, r * 0.84, r * 0.68, n)
            e = p + d * L
        else:
            e = p + d * L
            _tube(bm, p, e, r, r * 0.66, n)
        if lvl in snow_levels and d.z < 0.75:
            off = Vector((0, 0, r * 0.8))
            _tube(sb, p + off, e + off, r * 0.62, r * 0.42, 4)
        if lvl >= depth:
            tw = (d + Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 0.25))).normalized()
            _tube(bm, e, e + tw * L * 0.55, r * 0.6, 0.0, 3)
            return
        nk = kids + (1 if lvl == 0 else 0)
        base_az = rng.uniform(0, math.tau)
        for i in range(nk):
            az = base_az + math.tau * i / nk + rng.uniform(-0.4, 0.4)
            ang = rng.uniform(0.55, 1.0) * spread
            perp = d.orthogonal().normalized()
            perp.rotate(Quaternion(d, az))
            nd = d.copy()
            nd.rotate(Quaternion(perp, ang))
            nd.z += up
            nd.normalize()
            grow(e, nd, L * rng.uniform(0.62, 0.8), r * 0.6, lvl + 1)
        if lvl < depth - 1:
            ld = (d + Vector((rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), 0.1))).normalized()
            grow(e, ld, L * 0.75, r * 0.7, lvl + 1)

    # root flare and trunk
    lean = Vector((rng.uniform(-0.06, 0.06), rng.uniform(-0.06, 0.06), 1.0)).normalized()
    _tube(bm, (0, 0, -0.05), (0, 0, 0.35), trunk_r * 1.5, trunk_r * 1.05, 9)
    top = Vector((0, 0, 0.35)) + lean * (trunk_h - 0.35)
    _tube(bm, (0, 0, 0.35), top, trunk_r * 1.05, trunk_r * 0.85, 9)
    for k in range(4):                      # buttress roots
        a = math.tau * k / 4 + rng.uniform(-0.3, 0.3)
        _tube(bm, (math.cos(a) * trunk_r * 0.6, math.sin(a) * trunk_r * 0.6, 0.3),
              (math.cos(a) * trunk_r * 2.3, math.sin(a) * trunk_r * 2.3, -0.04), trunk_r * 0.35, trunk_r * 0.12, 5)
    grow(top, lean, L0, trunk_r * 0.85, 0)
    bark = _bm_obj(name + "_bark", bm, M("bark"))
    snow = _bm_obj(name + "_snow", sb, M("snow"))
    ring = _slush_patch("snow_ring", _blob_outline(trunk_r * 3.4, 20, seed + 5), (0, 0), lift=0.03, seed=seed)
    visual = join([bark, snow, ring], name)
    export(name, visual, box("c", (trunk_r * 2.2, trunk_r * 2.2, trunk_h + 1.0), (0, 0, 0)))


def tree_linden():
    """Small-leaved lime, pollarded high: tall oval crown of upswept limbs."""
    _tree("tree_linden", 11, 3.0, 0.2, 2.2, 4, 2, 0.62, 0.35)


def tree_chestnut():
    """Horse chestnut: shorter trunk, broad spreading crown of heavier limbs."""
    _tree("tree_chestnut", 23, 2.3, 0.25, 2.4, 4, 2, 0.85, 0.12)


# ------------------------------------------------------------------ plants
def _tub(parts, w, h, loc=(0, 0, 0)):
    """Square Versailles-style oak planter with iron bands and ball feet."""
    x, y, z = loc
    parts.append(taper_box("tub", (w, w, h), (x, y, z + 0.06), M("wood_dark"), top=1.12, bevel=0.015, seg=1))
    for zz in (0.12, h - 0.06):
        s = 1.0 + 0.12 * (zz / h)
        parts.append(box("band", (w * s + 0.02, w * s + 0.02, 0.035), (x, y, z + 0.06 + zz), M("iron", 0.5)))
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(sphere("foot", 0.05, (x + sx * w * 0.4, y + sy * w * 0.4, z + 0.04), M("wood_dark"), seg=8, rings=5))
            parts.append(sphere("knob", 0.04, (x + sx * w * 0.56, y + sy * w * 0.56, z + h + 0.1), M("wood_dark"), seg=8, rings=5))
    parts.append(box("soil", (w * 1.05, w * 1.05, 0.02), (x, y, z + h + 0.02), M("soil")))


def _leafy(parts, name, r, center, mat, zscale=1.0, seed=0, seg=14, rings=10, holes=0.03, twigs=8, snow=0.6,
           amp=0.12, flat_top=None):
    """Leafy clipped mass (tub yew, juniper, bay ball, rosemary): a sphere shell displaced by layered noise and
    clad in a foliage bake, a few faces cut out onto a near-black core, twig tips poking out and a sunk snow cap
    (`snow` = cap radius as a fraction of r, 0 for none). Appends to parts."""
    from mathutils import noise as mnoise
    rng = random.Random(seed)
    cx, cy, cz = center
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, radius=r, location=center)
    o = bpy.context.object
    o.scale.z = zscale
    o = _finish_prim(o, name, mat, mode=1.0, c=(cx, cy))
    off = Vector((seed * 1.7, seed * 0.9, seed * 2.3))

    def f(co):
        d = Vector((co.x - cx, co.y - cy, (co.z - cz) / zscale))
        n = d.normalized() if d.length > 1e-6 else Vector((0, 0, 1))
        q = n * 2.2 + off
        dn = mnoise.noise(q) * 0.6 + mnoise.noise(q * 2.6) * 0.3 + mnoise.noise(q * 6.3) * 0.15
        k = 1.0 + amp * dn
        co.x = cx + (co.x - cx) * k
        co.y = cy + (co.y - cy) * k
        co.z = cz + (co.z - cz) * k
        if flat_top is not None and co.z > flat_top:
            co.z = flat_top + (co.z - flat_top) * 0.25
    edit_verts(o, f)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.faces.ensure_lookup_table()
    cut = [fc for fc in bm.faces if abs(fc.normal.z) < 0.6 and rng.random() < holes]
    bmesh.ops.delete(bm, geom=cut, context="FACES_ONLY")
    for fc in bm.faces:
        fc.smooth = True
    bm.to_mesh(o.data)
    bm.free()
    parts.append(o)
    parts.append(sphere(name + "_core", r * 0.8, center, M("hedge_core", 0.95), seg=8, rings=6, zscale=zscale))
    tw = bmesh.new()
    for k in range(twigs):
        a = rng.uniform(0, math.tau)
        el = rng.uniform(-0.3, 1.0)
        n = Vector((math.cos(a) * math.cos(el), math.sin(a) * math.cos(el), math.sin(el)))
        p0 = Vector((cx + n.x * r * 0.95, cy + n.y * r * 0.95, cz + n.z * r * zscale * 0.95))
        d = (n + Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0.3))).normalized()
        L = r * rng.uniform(0.25, 0.5)
        _tube(tw, p0 - d * 0.03, p0 + d * L, 0.004, 0.0, 3)
    if twigs:
        parts.append(_bm_obj(name + "_twigs", tw, M("dead_stalk")))
    if snow:
        top = cz + r * zscale * (1.0 + amp * 0.3) if flat_top is None else flat_top + 0.01
        cap = _lumpy(name + "_snow", r * snow, (cx + rng.uniform(-0.02, 0.02), cy, top - r * 0.12), M("snow"),
                     zscale=0.3, amp=0.25, seed=seed + 1, seg=10, rings=5, zmin=top - r * 0.25)
        parts.append(cap)


def shrub_tub():
    """Clipped yew in an oak tub, snow on its shoulders: flanks a door."""
    reset()
    parts = []
    _tub(parts, 0.55, 0.5)
    parts.append(cyl("stem", 0.04, 0.3, (0, 0, 0.55), M("bark"), verts=6))
    _leafy(parts, "yew", 0.34, (0, 0, 1.05), M("hedge_leaf"), zscale=1.6, seed=3, seg=16, rings=12, twigs=10, snow=0.55)
    _leafy(parts, "yew_top", 0.15, (0.02, 0.0, 1.66), M("hedge_leaf"), zscale=1.3, seed=4, seg=10, rings=7, holes=0.0, twigs=4, snow=0.9)
    export("shrub_tub", join(parts, "shrub_tub"), box("c", (0.65, 0.65, 1.2), (0, 0, 0)))


def shrub_juniper():
    """Upright juniper in a round tub: a darker, narrower evergreen."""
    reset()
    parts = [cyl("tub", 0.28, 0.45, (0, 0, 0), M("wood"), verts=14, r2=0.33, bevel=0.01, seg=1)]
    for zz in (0.08, 0.37):
        parts.append(cyl("hoop", 0.3 + zz * 0.1, 0.04, (0, 0, zz), M("iron", 0.5), verts=14, bevel=0))
    parts.append(cyl("soil", 0.31, 0.02, (0, 0, 0.43), M("soil"), verts=14, bevel=0))
    _leafy(parts, "jun", 0.24, (0, 0, 1.1), M("juniper_leaf"), zscale=2.8, seed=8, seg=14, rings=16, twigs=10, snow=0.6, amp=0.1)
    export("shrub_juniper", join(parts, "shrub_juniper"), cyl("c", 0.32, 1.2, (0, 0, 0), None, verts=8))


def _pot(parts, r, h, loc):
    x, y, z = loc
    parts.append(cyl("pot", r * 0.78, h, (x, y, z), M("terracotta"), verts=14, r2=r, bevel=0.008, seg=1))
    parts.append(cyl("pot_rim", r * 1.06, 0.05, (x, y, z + h - 0.05), M("terracotta"), verts=14, bevel=0.008, seg=1))
    parts.append(cyl("pot_soil", r * 0.95, 0.02, (x, y, z + h - 0.03), M("soil"), verts=14, bevel=0))


def pot_herbs():
    """An innkeeper's pair: rosemary in a low pot and a clipped bay standard in a tall one."""
    reset()
    parts = []
    rng = random.Random(31)
    _pot(parts, 0.2, 0.28, (-0.28, 0, 0))
    bm = bmesh.new()
    for k in range(22):
        a, rr = rng.uniform(0, math.tau), rng.uniform(0, 0.12)
        p0 = Vector((-0.28 + math.cos(a) * rr, math.sin(a) * rr, 0.27))
        d = Vector((math.cos(a) * 0.3, math.sin(a) * 0.3, 1.0)).normalized()
        _tube(bm, p0, p0 + d * rng.uniform(0.28, 0.45), 0.012, 0.0, 3)
    parts.append(_bm_obj("rosemary", bm, M("rosemary_leaf")))
    _leafy(parts, "rosemary_body", 0.14, (-0.28, 0, 0.43), M("rosemary_leaf"), zscale=0.85, seed=32, seg=12, rings=8,
           holes=0.04, twigs=6, snow=0.6, amp=0.2)
    _pot(parts, 0.17, 0.4, (0.22, 0.02, 0))
    parts.append(cyl("bay_stem", 0.018, 0.75, (0.22, 0.02, 0.38), M("bark"), verts=6))
    _leafy(parts, "bay", 0.22, (0.22, 0.02, 1.22), M("bay_leafy"), seed=34, seg=14, rings=10, twigs=7, snow=0.6)
    export("pot_herbs", join(parts, "pot_herbs"))


def pot_hellebore():
    """Christmas roses in a stoneware pot: the only flowers of a Krakow January, pale and nodding."""
    reset()
    parts = []
    rng = random.Random(41)
    _pot(parts, 0.2, 0.26, (0, 0, 0))
    bm = bmesh.new()
    for k in range(14):                       # dark leathery leaves: tilted quads
        a = math.tau * k / 14 + rng.uniform(-0.2, 0.2)
        c = Vector((math.cos(a) * 0.12, math.sin(a) * 0.12, 0.3))
        d = Vector((math.cos(a), math.sin(a), 0.0))
        s = Vector((-math.sin(a), math.cos(a), 0.0))
        tip = c + d * 0.2 + Vector((0, 0, 0.1 + rng.uniform(-0.04, 0.04)))
        _quad(bm, [c - s * 0.04, c + d * 0.08 - s * 0.07 + Vector((0, 0, 0.06)), tip, c + d * 0.08 + s * 0.07 + Vector((0, 0, 0.06))])
        _quad(bm, [c + s * 0.04, c + d * 0.08 + s * 0.07 + Vector((0, 0, 0.06)), tip, c + d * 0.08 - s * 0.07 + Vector((0, 0, 0.06))])
    parts.append(_bm_obj("leaves", bm, M("leaf_dark")))
    for k in range(9):
        a, rr = rng.uniform(0, math.tau), rng.uniform(0.02, 0.13)
        p = (math.cos(a) * rr, math.sin(a) * rr, 0.42 + rng.uniform(-0.04, 0.05))
        mat = M("flower_white") if k % 3 else M("flower_pink")
        parts.append(cyl("flower", 0.038, 0.012, p, mat, verts=5, rot=(rng.uniform(0.6, 1.3), 0, a), center=True, bevel=0))
        parts.append(sphere("eye", 0.012, p, M("zupan_gold"), seg=5, rings=3))
    export("pot_hellebore", join(parts, "pot_hellebore"))


def window_box():
    """Planter under an upper window: dead geranium stalks and a crust of snow. Origin = top back edge, on the wall."""
    reset()
    parts = [box("box", (1.1, 0.24, 0.2), (0, -0.14, -0.2), M("wood_dark"), bevel=0.012, seg=1),
             box("rim", (1.14, 0.27, 0.03), (0, -0.14, -0.02), M("wood"), bevel=0.008, seg=1),
             box("soil", (1.04, 0.2, 0.02), (0, -0.14, -0.035), M("soil"))]
    for sx in (-0.4, 0.4):
        parts.append(box("bracket", (0.04, 0.2, 0.04), (sx, -0.1, -0.28), M("iron")))
        parts.append(cbox("brace", (0.03, 0.03, 0.24), (sx, -0.08, -0.2), M("iron"), rot=(0.7, 0, 0)))
    rng = random.Random(51)
    bm = bmesh.new()
    for k in range(26):
        x = rng.uniform(-0.48, 0.48)
        y = -0.14 + rng.uniform(-0.07, 0.07)
        p0 = Vector((x, y, -0.03))
        h = rng.uniform(0.12, 0.34)
        bend = Vector((rng.uniform(-0.08, 0.08), rng.uniform(-0.12, 0.02), 0))
        p1 = p0 + Vector((0, 0, h * 0.6)) + bend * 0.3
        p2 = p0 + Vector((0, 0, h)) + bend
        _tube(bm, p0, p1, 0.008, 0.006, 3)
        _tube(bm, p1, p2, 0.006, 0.0, 3)
        if k % 4 == 0:
            _tube(bm, p2, p2 + Vector((bend.x * 0.5, -0.05, -0.08)), 0.012, 0.0, 4)   # a dead flower head nodding
    parts.append(_bm_obj("stalks", bm, M("dead_stalk")))
    parts.append(edit_verts(blob("snow", (1.06, 0.22, 0.06), (0, -0.14, -0.035), M("snow"), subsurf=1),
                            lambda co: setattr(co, "z", co.z + 0.015 * math.sin(co.x * 9.0))))
    export("window_box", join(parts, "window_box"))


def ivy_patch():
    """Common ivy climbing a wall from a root at the pavement: wandering stems and ~500 dark leaves.
    Origin = foot on the wall face; about 2.4 m wide and 4.5 m tall."""
    reset()
    rng = random.Random(61)
    stems, leaves = bmesh.new(), bmesh.new()
    for s in range(8):
        p = Vector((rng.uniform(-0.25, 0.25), -0.03, 0.0))
        heading = rng.uniform(-0.6, 0.6)
        steps = rng.randint(12, 20)
        for i in range(steps):
            heading += rng.uniform(-0.35, 0.35)
            heading = max(-1.0, min(1.0, heading))
            q = p + Vector((math.sin(heading) * 0.25, 0, math.cos(heading) * 0.25))
            q.x = max(-1.2, min(1.2, q.x))
            _tube(stems, p, q, 0.012 * (1 - i / steps) + 0.005, 0.012 * (1 - (i + 1) / steps) + 0.005, 3)
            for k in range(5):
                c = p + (q - p) * rng.random() + Vector((rng.uniform(-0.14, 0.14), 0, rng.uniform(-0.1, 0.1)))
                sz = rng.uniform(0.05, 0.085) * (1.1 - 0.4 * i / steps)
                a = rng.uniform(-0.6, 0.6)
                ux, uz = math.cos(a), math.sin(a)
                depth = -0.035 - rng.uniform(0.0, 0.05)
                pts = [(0, -0.9), (0.75, -0.1), (0.4, 0.75), (-0.4, 0.75), (-0.75, -0.1)]
                verts = [leaves.verts.new(Vector((c.x + (px * ux - pz * uz) * sz, depth - 0.02 * (abs(px) < 0.1), c.z + (px * uz + pz * ux) * sz)))
                         for (px, pz) in pts]
                f = leaves.faces.new(verts)
                f.smooth = False
            p = q
            if q.z > 4.6:
                break
    st = _bm_obj("stems", stems, M("bark"))
    lv = _bm_obj("leaves", leaves, M("ivy"))
    export("ivy_patch", join([st, lv], "ivy_patch"))


def weed_tuft():
    """Tuft of dead grass and a seed stalk between setts. Tiny: instanced by the hundred via MultiMesh."""
    reset()
    rng = random.Random(71)
    bm = bmesh.new()
    for k in range(9):
        a = rng.uniform(0, math.tau)
        base = Vector((math.cos(a) * 0.025, math.sin(a) * 0.025, -0.01))
        out = Vector((math.cos(a), math.sin(a), 0)) * rng.uniform(0.04, 0.12)
        h = rng.uniform(0.1, 0.24)
        side = Vector((-math.sin(a), math.cos(a), 0)) * 0.012
        mid = base + out * 0.4 + Vector((0, 0, h * 0.6))
        tip = base + out + Vector((0, 0, h))
        v0, v1 = bm.verts.new(base - side), bm.verts.new(base + side)
        v2, v3 = bm.verts.new(mid + side * 0.7), bm.verts.new(mid - side * 0.7)
        vt = bm.verts.new(tip)
        bm.faces.new((v0, v1, v2, v3))
        bm.faces.new((v3, v2, vt))
    _tube(bm, (0, 0, 0), (0.02, 0.01, 0.3), 0.004, 0.003, 3)
    _tube(bm, (0.02, 0.01, 0.3), (0.025, 0.012, 0.36), 0.012, 0.0, 4)
    export("weed_tuft", _bm_obj("weed_tuft", bm, M("dead_grass")))


def straw_scatter():
    """Straw and hay trodden into the snow around a stall: a low mound and loose stalks. Origin = centre."""
    reset()
    rng = random.Random(81)
    bm = bmesh.new()
    for k in range(240):
        r = abs(rng.gauss(0, 0.6))
        a = rng.uniform(0, math.tau)
        c = Vector((math.cos(a) * r * 1.3, math.sin(a) * r * 0.8, 0.004 + rng.uniform(0, 0.015)))
        b = rng.uniform(0, math.tau)
        d = Vector((math.cos(b), math.sin(b), 0)) * rng.uniform(0.08, 0.2)
        s = Vector((-math.sin(b), math.cos(b), 0)) * 0.006
        _quad(bm, [c - d - s, c + d - s, c + d + s + Vector((0, 0, 0.004)), c - d + s + Vector((0, 0, 0.004))])
    parts = [_bm_obj("straw", bm, M("straw"))]
    parts.append(_lumpy("mound", 0.35, (0.3, 0.1, 0.0), M("hay"), zscale=0.25, amp=0.2, seed=82, seg=10, rings=6, zmin=-0.01))
    export("straw_scatter", join(parts, "straw_scatter"))


def door_wreath():
    """Dried wreath for a door leaf: straw ring bound with dried flowers, rowan berries and a red ribbon.
    Origin = back of the ring on the door; hangs about 0.55 m across."""
    reset()
    rng = random.Random(91)
    parts = [torus("ring", 0.2, 0.055, (0, -0.05, 0), M("hay"), rot=(math.pi / 2, 0, 0), seg=18, mseg=6)]
    edit_verts(parts[0], lambda co: (setattr(co, "x", co.x * (1 + rng.uniform(-0.05, 0.05))), setattr(co, "z", co.z * (1 + rng.uniform(-0.05, 0.05)))))
    for k in range(14):
        a = math.tau * k / 14 + rng.uniform(-0.1, 0.1)
        mat = [M("dried_flower"), M("berry"), M("flower_white"), M("rosemary")][k % 4]
        parts.append(sphere("bud", 0.03 + 0.01 * (k % 2), (math.cos(a) * 0.2, -0.1, math.sin(a) * 0.2), mat, seg=6, rings=4))
    parts.append(box("ribbon", (0.12, 0.03, 0.08), (0, -0.1, -0.25), M("canvas_stripe"), bevel=0.01, seg=1))
    for sx in (-1, 1):
        parts.append(cbox("tail", (0.05, 0.015, 0.22), (sx * 0.05, -0.1, -0.34), M("canvas_stripe"), rot=(0, -sx * 0.3, 0)))
    parts.append(box("nail", (0.02, 0.05, 0.02), (0, -0.03, 0.24), M("iron")))
    export("door_wreath", join(parts, "door_wreath"))


# ------------------------------------------------------------------ guild signs on wrought-iron brackets
def _bracket(parts, L=1.15):
    """Wall plate, arm, diagonal brace and scrolls sticking out along -Y at z=0. Returns the hang point (y)."""
    iron = M("iron", 0.55)
    parts.append(box("plate", (0.12, 0.04, 0.62), (0, -0.02, -0.5), iron, bevel=0.01, seg=1))
    parts.append(box("arm", (0.04, L, 0.04), (0, -L / 2, -0.02), iron, bevel=0.005, seg=1))
    bm = bmesh.new()
    _tube(bm, (0, -0.02, -0.45), (0, -L * 0.72, -0.02), 0.016, 0.016, 5)
    for k in range(7):                                         # a scroll curling under the arm
        a0, a1 = math.tau * k / 8, math.tau * (k + 1) / 8
        r0, r1 = 0.14 - k * 0.012, 0.14 - (k + 1) * 0.012
        c = Vector((0, -L * 0.45, -0.17))
        _tube(bm, c + Vector((0, math.cos(a0) * r0, math.sin(a0) * r0)), c + Vector((0, math.cos(a1) * r1, math.sin(a1) * r1)), 0.012, 0.012, 4)
    for k in range(5):                                         # a curl rising over the arm by the wall
        a0, a1 = math.pi + math.pi * k / 5, math.pi + math.pi * (k + 1) / 5
        c = Vector((0, -0.16, 0.08))
        _tube(bm, c + Vector((0, math.cos(a0) * 0.1, -math.sin(a0) * 0.1)), c + Vector((0, math.cos(a1) * 0.1, -math.sin(a1) * 0.1)), 0.011, 0.011, 4)
    parts.append(_bm_obj("iron_work", bm, iron))
    parts.append(sphere("finial", 0.04, (0, -L, -0.02), iron, seg=8, rings=5))
    hy = -L * 0.72
    for dy in (-0.12, 0.12):
        parts.append(box("chain", (0.012, 0.012, 0.2), (0, hy + dy, -0.22), iron))
    return hy


def _guild(name, emblem):
    reset()
    parts = []
    hy = _bracket(parts)
    emblem(parts, hy, -0.62)
    visual = join(parts, name)
    export(name, visual)


def _em_pretzel(parts, y, z):
    """A proper Brezel: a heart-shaped loop open at the top notch, the two ends twisted across the middle."""
    m = M("crust", 0.6)
    bm = bmesh.new()
    k_ = 0.0145
    zc = z + 0.12

    def heart(t):
        hx = 16 * math.sin(t) ** 3
        hz = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        return Vector((0.0, y + hx * k_, zc + hz * k_))
    pts = [heart(0.22 + (math.tau - 0.44) * i / 36) for i in range(37)]
    for a_, b_ in zip(pts, pts[1:]):
        _tube(bm, a_, b_, 0.034, 0.034, 6)
    for start, sgn in ((pts[0], -1), (pts[-1], 1)):
        end = Vector((0.0, y + sgn * 0.15, zc - 9 * k_))
        mid = (start + end) * 0.5 + Vector((sgn * 0.03, 0, 0.0))
        _tube(bm, start, mid, 0.034, 0.033, 6)
        _tube(bm, mid, end, 0.033, 0.03, 6)
    parts.append(_bm_obj("pretzel", bm, m))
    for p_ in pts[::6]:
        parts.append(sphere("salt", 0.012, (p_.x - 0.03, p_.y, p_.z + 0.02), M("salt"), seg=4, rings=3))
    parts.append(box("hook", (0.02, 0.02, 0.1), (0, y, zc + 12 * k_ - 0.02), M("iron")))


def _em_boot(parts, y, z):
    lea = M("black", 0.35)
    parts.append(box("shaft", (0.14, 0.2, 0.42), (0, y + 0.04, z - 0.18), lea, bevel=0.03, seg=2))
    parts.append(box("cuff", (0.16, 0.23, 0.08), (0, y + 0.04, z + 0.2), M("leather"), bevel=0.02, seg=1))
    parts.append(box("foot", (0.14, 0.36, 0.14), (0, y - 0.09, z - 0.3), lea, bevel=0.04, seg=2))
    parts.append(box("heel", (0.13, 0.08, 0.06), (0, y + 0.1, z - 0.36), M("wood_dark")))
    parts.append(box("sole", (0.15, 0.3, 0.025), (0, y - 0.12, z - 0.33), M("wood_dark")))
    parts.append(box("hook", (0.02, 0.26, 0.02), (0, y, z + 0.29), M("iron")))


def _em_key(parts, y, z):
    g = M("gold", 0.35)
    parts.append(torus("bow", 0.1, 0.03, (0, y, z + 0.18), g, rot=(0, math.pi / 2, 0), seg=16, mseg=6))
    parts.append(cyl("shaft", 0.028, 0.5, (0, y, z - 0.4), g, verts=8))
    parts.append(box("bit", (0.03, 0.13, 0.12), (0, y - 0.07, z - 0.4), g))
    parts.append(box("bit2", (0.03, 0.05, 0.06), (0, y - 0.15, z - 0.34), g))
    parts.append(cyl("collar", 0.045, 0.04, (0, y, z + 0.04), g, verts=8))
    parts.append(box("hook", (0.02, 0.26, 0.02), (0, y, z + 0.29), M("iron")))


def _em_ring(parts, y, z):
    g = M("gold", 0.3)
    parts.append(torus("band", 0.2, 0.04, (0, y, z - 0.08), g, rot=(0, math.pi / 2, 0), seg=24, mseg=8))
    parts.append(cyl("setting", 0.07, 0.07, (0, y, z + 0.13), g, verts=8))
    parts.append(sphere("stone", 0.065, (0, y, z + 0.22), M("crimson", 0.1), seg=10, rings=6))
    parts.append(box("hook", (0.02, 0.26, 0.02), (0, y, z + 0.29), M("iron")))


def _em_grapes(parts, y, z):
    m = M("grape", 0.35)
    rng = random.Random(101)
    rows = [4, 4, 3, 3, 2, 1]
    for i, n in enumerate(rows):
        for k in range(n):
            yy = y + (k - (n - 1) / 2) * 0.085 + rng.uniform(-0.01, 0.01)
            parts.append(sphere("grape", 0.05, (rng.uniform(-0.02, 0.02), yy, z + 0.1 - i * 0.075), m, seg=7, rings=4))
    bm = bmesh.new()
    pts = [(0, 0.0), (0.12, 0.08), (0.2, 0.02), (0.22, 0.14), (0.12, 0.22), (0.02, 0.18)]
    vs = [bm.verts.new((0.0, y - 0.12 + px, z + 0.14 + pz)) for px, pz in pts]
    bm.faces.new(vs)
    parts.append(_bm_obj("leaf", bm, M("gold", 0.35)))
    parts.append(cyl("stalk", 0.015, 0.14, (0, y, z + 0.14), M("wood_dark"), verts=5))
    parts.append(box("hook", (0.02, 0.26, 0.02), (0, y, z + 0.28), M("iron")))


def _em_tankard(parts, y, z):
    pw = M("lead", 0.35)
    parts.append(cyl("body", 0.12, 0.3, (0, y, z - 0.2), pw, verts=14, r2=0.105, bevel=0.01, seg=1))
    for zz in (-0.16, 0.05):
        parts.append(cyl("band", 0.125, 0.03, (0, y, z + zz), pw, verts=14, bevel=0))
    parts.append(cyl("lid", 0.115, 0.04, (0, y, z + 0.1), pw, verts=14, r2=0.09, bevel=0.01, seg=1))
    parts.append(sphere("knob", 0.03, (0, y + 0.08, z + 0.16), pw, seg=6, rings=4))
    parts.append(torus("handle", 0.1, 0.022, (0, y + 0.15, z - 0.05), pw, rot=(0, math.pi / 2, 0), seg=12, mseg=5))
    parts.append(_lumpy("foam", 0.1, (0, y, z + 0.1), M("linen"), zscale=0.4, amp=0.2, seed=5, seg=8, rings=5))
    parts.append(box("hook", (0.02, 0.26, 0.02), (0, y, z + 0.18), M("iron")))


def _em_coffee(parts, y, z):
    cu = M("bronze", 0.35)
    parts.append(cyl("base", 0.14, 0.18, (0, y, z - 0.32), cu, verts=14, r2=0.1, bevel=0.01, seg=1))
    parts.append(cyl("neck", 0.1, 0.16, (0, y, z - 0.14), cu, verts=14, r2=0.07, bevel=0.01, seg=1))
    parts.append(cyl("lid", 0.08, 0.1, (0, y, z + 0.02), cu, verts=14, r2=0.02, bevel=0.01, seg=1))
    parts.append(sphere("knob", 0.025, (0, y, z + 0.13), M("gold", 0.35), seg=6, rings=4))
    bm = bmesh.new()
    _tube(bm, (0, y - 0.1, z - 0.26), (0, y - 0.22, z - 0.12), 0.03, 0.022, 6)
    _tube(bm, (0, y - 0.22, z - 0.12), (0, y - 0.26, z - 0.0), 0.022, 0.012, 6)
    parts.append(_bm_obj("spout", bm, cu))
    parts.append(torus("handle", 0.1, 0.018, (0, y + 0.14, z - 0.18), M("wood_dark"), rot=(0, math.pi / 2, 0), seg=12, mseg=5))
    parts.append(box("hook", (0.02, 0.26, 0.02), (0, y, z + 0.28), M("iron")))


def _em_scissors(parts, y, z):
    st = M("iron", 0.35)
    for s in (-1, 1):
        parts.append(cbox("blade", (0.025, 0.05, 0.46), (0, y + s * 0.03, z - 0.2), M("lead", 0.3), rot=(s * 0.28, 0, 0), bevel=0.005, seg=1))
        parts.append(torus("handle", 0.07, 0.02, (0, y + s * 0.1, z + 0.13), M("gold", 0.35), rot=(0, math.pi / 2, 0), seg=12, mseg=5))
    parts.append(cyl("pivot", 0.025, 0.06, (0, y, z - 0.02), st, verts=8, rot=(0, math.pi / 2, 0), center=True))
    parts.append(box("hook", (0.02, 0.26, 0.02), (0, y, z + 0.26), M("iron")))


def _em_mortar(parts, y, z):
    br = M("bronze", 0.4)
    parts.append(cyl("foot", 0.13, 0.05, (0, y, z - 0.36), br, verts=14, bevel=0.01, seg=1))
    parts.append(cyl("bowl", 0.1, 0.26, (0, y, z - 0.31), br, verts=14, r2=0.16, bevel=0.01, seg=1))
    parts.append(cyl("lip", 0.17, 0.03, (0, y, z - 0.07), br, verts=14, bevel=0.005, seg=1))
    parts.append(cyl("inside", 0.14, 0.01, (0, y, z - 0.045), M("black"), verts=14, bevel=0))
    bm = bmesh.new()
    _tube(bm, (0, y + 0.05, z - 0.15), (0, y - 0.1, z + 0.2), 0.03, 0.02, 6)
    parts.append(_bm_obj("pestle", bm, M("wood")))
    parts.append(box("hook", (0.02, 0.36, 0.02), (0, y, z + 0.2), M("iron")))


def guild_pretzel(): _guild("guild_pretzel", _em_pretzel)
def guild_boot(): _guild("guild_boot", _em_boot)
def guild_key(): _guild("guild_key", _em_key)
def guild_ring(): _guild("guild_ring", _em_ring)
def guild_grapes(): _guild("guild_grapes", _em_grapes)
def guild_tankard(): _guild("guild_tankard", _em_tankard)
def guild_coffee(): _guild("guild_coffee", _em_coffee)
def guild_scissors(): _guild("guild_scissors", _em_scissors)
def guild_mortar(): _guild("guild_mortar", _em_mortar)


# ------------------------------------------------------------------ painted fascia boards with gilt serif lettering
def _board(name, text, colour, w=2.0, h=0.5, sub=None):
    """Board flat on the wall: moulded frame, painted field, raised gilt letters. Origin = bottom centre on the wall."""
    reset()
    bt = 0.04
    parts = [box("board", (w, bt, h), (0, -bt / 2, 0), M(colour, 0.5), bevel=0.008, seg=1)]
    for zz in (0.0, h - 0.035):
        parts.append(box("frame_h", (w + 0.06, bt + 0.03, 0.035), (0, -(bt + 0.03) / 2, zz), M("gold", 0.35), bevel=0.008, seg=1))
    for sx in (-1, 1):
        parts.append(box("frame_v", (0.035, bt + 0.03, h), (sx * (w / 2 + 0.012), -(bt + 0.03) / 2, 0), M("gold", 0.35), bevel=0.008, seg=1))
        parts.append(sphere("boss", 0.03, (sx * (w / 2 - 0.1), -bt - 0.01, h / 2), M("gold", 0.35), seg=8, rings=5))
    if sub:
        parts.append(_text("letters", text, h * 0.5, (0, -bt - 0.003, h * 0.63), M("gold", 0.35), width=w - 0.35))
        parts.append(_text("sub", sub, h * 0.22, (0, -bt - 0.003, h * 0.24), M("gold", 0.35), width=w - 0.4))
    else:
        parts.append(_text("letters", text, h * 0.62, (0, -bt - 0.003, h * 0.5), M("gold", 0.35), width=w - 0.3))
    parts.append(box("snow", (w + 0.04, 0.07, 0.025), (0, -0.04, h), M("snow"), bevel=0.01, seg=1))
    export(name, join(parts, name))


def sign_winiarnia(): _board("sign_winiarnia", "Winiarnia", "sign_wine")
def sign_kawiarnia(): _board("sign_kawiarnia", "Kawiarnia", "sign_green")
def sign_piekarnia(): _board("sign_piekarnia", "Piekarnia", "sign_blue")
def sign_apotheke(): _board("sign_apotheke", "APOTHEKE", "sign_black", sub="Pod Złotym Lwem")
def sign_goldschmied(): _board("sign_goldschmied", "Goldschmied", "sign_red")
def sign_zajazd(): _board("sign_zajazd", "ZAJAZD", "sign_green", w=2.4, h=0.55, sub="pod Złotą Różą")


# ------------------------------------------------------------------ shop fronts
def _shutters(parts, ww=1.3, z0=1.3, h=1.45):
    """A pair of plank shutters folded back flat against the wall either side of a window of width ww."""
    sw = ww / 2 + 0.03
    for sx in (-1, 1):
        cx = sx * (ww / 2 + 0.06 + sw / 2)
        parts.append(box("shutter", (sw, 0.04, h), (cx, -0.03, z0), M("shutter"), bevel=0.008, seg=1))
        for k in range(1, 4):
            parts.append(box("plank", (0.008, 0.045, h - 0.02), (cx - sw / 2 + sw * k / 4, -0.03, z0 + 0.01), M("wood_dark")))
        for zz in (z0 + 0.2, z0 + h - 0.26):
            parts.append(box("ledge", (sw - 0.04, 0.05, 0.08), (cx, -0.06, zz), M("shutter"), bevel=0.005, seg=1))
            parts.append(box("strap", (sw * 0.9, 0.012, 0.035), (cx - sx * 0.04, -0.09, zz + 0.02), M("iron")))
        parts.append(cbox("brace", (0.06, 0.02, h * 0.8), (cx, -0.07, z0 + h / 2), M("shutter"), rot=(0, sx * 0.42, 0)))
        parts.append(box("catch", (0.05, 0.08, 0.02), (sx * (ww / 2 + 0.12 + sw), -0.04, z0 + h * 0.5), M("iron")))


def _ledge(parts, w=1.7):
    parts.append(box("ledge", (w, 0.42, 0.08), (0, -0.21, 1.05), M("stone_pale"), bevel=0.015, seg=1))
    for sx in (-1, 1):
        parts.append(taper_box("corbel", (0.14, 0.3, 0.3), (sx * (w / 2 - 0.15), -0.15, 0.75), M("stone"), top=1.0, bevel=0.01, seg=1))


def shopfront_bakery():
    """Baker's window: open shutters and a stone ledge of loaves, rolls and a pretzel stick. Origin = window axis
    on the wall at ground level."""
    reset()
    parts = []
    _shutters(parts)
    _ledge(parts)
    rng = random.Random(111)
    parts.append(box("board", (1.4, 0.34, 0.03), (0, -0.22, 1.13), M("wood"), bevel=0.005, seg=1))
    for k in range(6):
        x = -0.55 + k * 0.22
        mat = M("crust") if k % 2 else M("crust_dark")
        parts.append(_lumpy("loaf", 0.1, (x, -0.24 + rng.uniform(-0.04, 0.04), 1.2), mat, zscale=0.6, amp=0.06, seed=112 + k, seg=10, rings=6, zmin=1.16))
    for k in range(5):
        parts.append(_lumpy("roll", 0.05, (-0.45 + k * 0.22, -0.34, 1.19), M("crust"), zscale=0.7, amp=0.06, seed=120 + k, seg=8, rings=5, zmin=1.16))
    parts.append(cyl("stick", 0.01, 0.5, (0.62, -0.25, 1.16), M("wood_dark"), verts=5))
    for k in range(3):
        parts.append(torus("pretzel", 0.06, 0.018, (0.62, -0.25, 1.3 + k * 0.13), M("crust"), rot=(math.pi / 2, 0, 0), seg=10, mseg=5))
    export("shopfront_bakery", join(parts, "shopfront_bakery"))


def shopfront_cloth():
    """Draper's window: bolts of red, blue and green cloth on the ledge, one unrolled over the shutter."""
    reset()
    parts = []
    _shutters(parts)
    _ledge(parts)
    for k, key in enumerate(("bolt_red", "bolt_blue", "bolt_green", "linen", "bolt_red")):
        x = -0.6 + k * 0.3
        parts.append(cyl("bolt", 0.09, 0.4, (x, -0.22, 1.22), M(key), verts=10, rot=(math.pi / 2, 0, 0), center=True, bevel=0.01, seg=1))
    parts.append(cyl("bolt_top", 0.08, 0.38, (-0.3, -0.22, 1.38), M("bolt_blue"), verts=10, rot=(math.pi / 2, 0, 0), center=True, bevel=0.01, seg=1))
    parts.append(box("drape", (0.36, 0.02, 0.8), (0.95, -0.1, 1.5), M("bolt_red"), bevel=0.005, seg=1))
    export("shopfront_cloth", join(parts, "shopfront_cloth"))


def shopfront_bottles():
    """Wine or apothecary window: dark bottles, stoneware jars and a small cask on the ledge."""
    reset()
    parts = []
    _shutters(parts)
    _ledge(parts)
    rng = random.Random(131)
    for k in range(7):
        x = -0.62 + k * 0.17
        mat = M("bottle", 0.1) if k % 3 else M("bottle_brown", 0.1)
        y = -0.25 + rng.uniform(-0.05, 0.05)
        parts.append(cyl("bottle", 0.045, 0.2, (x, y, 1.13), mat, verts=8))
        parts.append(cyl("neck", 0.016, 0.1, (x, y, 1.33), mat, verts=6))
        parts.append(cyl("cork", 0.018, 0.02, (x, y, 1.43), M("wood"), verts=6))
    for k in range(2):
        parts.append(cyl("jar", 0.07, 0.16, (-0.25 + k * 0.5, -0.36, 1.13), M("stone_pale"), verts=10, r2=0.05, bevel=0.01, seg=1))
    parts.append(cyl("cask", 0.11, 0.24, (0.65, -0.26, 1.24), M("wood"), verts=10, rot=(0, math.pi / 2, 0), center=True, bevel=0.01, seg=1))
    export("shopfront_bottles", join(parts, "shopfront_bottles"))


def oriel_cafe():
    """Timber oriel (bay) window for the cafe's first floor: glazed on three sides, lit, lead roof with snow.
    Origin = base centre on the wall; 1.7 m wide, 0.65 m deep, 2.3 m tall plus the corbel below."""
    reset()
    W, D, H = 1.7, 0.65, 2.3
    wd, fr = M("wood_dark"), M("wood")
    parts = [taper_box("corbel", (W, D, 0.45), (0, -D / 2, -0.45), wd, top=1.0, bevel=0.02, seg=1)]
    edit_verts(parts[0], lambda co: setattr(co, "y", co.y * (0.2 if co.z < -0.4 else 1.0)))
    parts.append(box("floor", (W + 0.08, D + 0.06, 0.12), (0, -(D + 0.06) / 2, 0), fr, bevel=0.02, seg=1))
    parts.append(box("apron", (W, D, 0.75), (0, -D / 2, 0.12), wd, bevel=0.015, seg=1))
    for sx in (-1, 0, 1):
        parts.append(box("panel", (0.4, 0.02, 0.45), (sx * 0.52, -D - 0.005, 0.26), fr, bevel=0.005, seg=1))
    parts.append(box("glass_f", (W - 0.1, 0.03, 1.2), (0, -D + 0.04, 0.87), M("glass_warm")))
    for sx in (-1, 1):
        parts.append(box("glass_s", (0.03, D - 0.1, 1.2), (sx * (W / 2 - 0.04), -D / 2, 0.87), M("glass_warm")))
        parts.append(box("post", (0.09, 0.09, 1.3), (sx * (W / 2 - 0.045), -D + 0.045, 0.87), wd))
    for k in range(1, 4):
        parts.append(box("mull", (0.05, 0.05, 1.2), (-W / 2 + W * k / 4, -D + 0.03, 0.87), wd))
    for zz in (0.87, 1.47, 2.07):
        parts.append(box("rail", (W, 0.07, 0.06), (0, -D + 0.035, zz - 0.03), wd))
    parts.append(box("head", (W + 0.1, D + 0.08, 0.2), (0, -(D + 0.08) / 2, 2.07), fr, bevel=0.02, seg=1))
    parts.append(roof("roof", W + 0.25, (D + 0.25) * 2, 0.35, (0, 0, 2.27), M("lead"), sag=0.02, flare=0.05, cuts=3))
    parts.append(roof("snow", W + 0.2, (D + 0.2) * 2, 0.4, (0, 0, 2.3), M("snow"), sag=0.02, flare=0.05, cuts=3))
    visual = join(parts, "oriel_cafe")
    bm = bmesh.new()
    bm.from_mesh(visual.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.y > 0.001], context="VERTS")   # the half roof inside the wall
    bm.to_mesh(visual.data)
    bm.free()
    export("oriel_cafe", visual)


def wall_lantern():
    """Oil lantern on a wall bracket over a door. Origin = bracket foot on the wall; lantern hangs 0.55 m out."""
    reset()
    iron = M("iron", 0.55)
    parts = [box("plate", (0.12, 0.03, 0.3), (0, -0.015, -0.2), iron)]
    bm = bmesh.new()
    _tube(bm, (0, 0, 0), (0, -0.55, 0), 0.015, 0.015, 5)
    _tube(bm, (0, 0, -0.18), (0, -0.4, 0), 0.012, 0.012, 5)
    parts.append(_bm_obj("arm", bm, iron))
    parts.append(box("cage", (0.24, 0.24, 0.34), (0, -0.55, -0.44), iron, bevel=0.01, seg=1))
    parts.append(box("glow", (0.2, 0.2, 0.3), (0, -0.55, -0.42), M("gold", 0.3, emit=(1.0, 0.72, 0.35), emit_strength=6.0)))
    parts.append(cyl("cap", 0.18, 0.14, (0, -0.55, -0.1), iron, verts=8, r2=0.02))
    parts.append(cyl("hook", 0.01, 0.1, (0, -0.55, -0.1), iron, verts=4))
    parts.append(cyl("snow", 0.13, 0.03, (0, -0.55, -0.06), M("snow"), verts=8, r2=0.03))
    export("wall_lantern", join(parts, "wall_lantern"))


# ------------------------------------------------------------------ benches, cafe furniture
def bench_wood():
    """Plank bench with a back rail on splayed legs, a lick of snow on the seat end. 1.8 m long."""
    reset()
    wd, w = M("wood_dark"), M("wood")
    parts = []
    for k in range(2):
        parts.append(box("seat", (1.8, 0.16, 0.04), (0, -0.1 + k * 0.17, 0.44), w, bevel=0.006, seg=1, wonk=0.01))
    for sx in (-0.75, 0.75):
        for sy, tilt in ((-0.14, 0.1), (0.14, -0.1)):
            parts.append(cbox("leg", (0.06, 0.06, 0.47), (sx, sy, 0.22), wd, rot=(tilt, 0, 0)))
        parts.append(box("rail", (0.06, 0.4, 0.05), (sx, 0, 0.38), wd))
        parts.append(cbox("back_post", (0.05, 0.05, 0.5), (sx, 0.19, 0.7), wd, rot=(-0.18, 0, 0)))
    parts.append(cbox("back", (1.75, 0.03, 0.14), (0, 0.22, 0.88), w, rot=(-0.18, 0, 0), bevel=0.006, seg=1))
    parts.append(cbox("back2", (1.75, 0.03, 0.08), (0, 0.2, 0.7), w, rot=(-0.18, 0, 0), bevel=0.006, seg=1))
    parts.append(box("stretcher", (1.5, 0.04, 0.04), (0, 0, 0.16), wd))
    parts.append(edit_verts(blob("snow", (0.5, 0.3, 0.035), (0.6, 0, 0.48), M("snow"), subsurf=1), lambda co: None))
    export("bench_wood", join(parts, "bench_wood"), box("c", (1.8, 0.5, 0.9), (0, 0.02, 0)))


def bench_stone():
    """Sandstone slab bench on two blocks, set against a church wall; snow along the back half."""
    reset()
    st = M("stone")
    parts = [box("slab", (1.9, 0.48, 0.12), (0, 0, 0.36), st, bevel=0.02, seg=1, wonk=0.02)]
    for sx in (-0.7, 0.7):
        parts.append(taper_box("block", (0.3, 0.4, 0.36), (sx, 0, 0), M("stone_dark"), top=0.9, bevel=0.02, seg=1, wonk=0.02))
    parts.append(edit_verts(blob("snow", (1.8, 0.22, 0.05), (0, 0.1, 0.48), M("snow"), subsurf=1), lambda co: None))
    export("bench_stone", join(parts, "bench_stone"), box("c", (1.9, 0.5, 0.5), (0, 0, 0)))


def _chair(parts, x, y, face, snow=False, upturned_z=None):
    """Rush-seated ladder-back chair at (x, y), back towards `face` (radians about Z)."""
    wd = M("wood_dark")
    c, s = math.cos(face), math.sin(face)

    def P(px, py):
        return (x + px * c - py * s, y + px * s + py * c)

    objs = []
    objs.append(box("seat", (0.42, 0.4, 0.04), (0, 0, 0.44), M("straw")))
    for px in (-0.18, 0.18):
        for py in (-0.17, 0.17):
            h = 0.95 if py > 0 else 0.46
            objs.append(box("leg", (0.035, 0.035, h), (px, py, 0), wd))
        objs.append(box("side", (0.03, 0.34, 0.03), (px, 0, 0.2), wd))
    for zz in (0.62, 0.76, 0.9):
        objs.append(box("slat", (0.36, 0.025, 0.05), (0, 0.17, zz), wd))
    ob = join(objs, "chair")

    def f(co):
        px, py = co.x, co.y
        if upturned_z is not None:                    # legs up, seat on the table top
            co.z = upturned_z + (0.46 - co.z)
        co.x, co.y = P(px, py)
    edit_verts(ob, f)
    parts.append(ob)
    if snow:
        parts.append(edit_verts(blob("csnow", (0.36, 0.34, 0.03), (x, y, 0.48), M("snow"), subsurf=1), lambda co: None))


def _round_table(parts, x=0.0, y=0.0):
    wd = M("wood_dark")
    parts.append(cyl("top", 0.42, 0.04, (x, y, 0.72), M("wood"), verts=18, bevel=0.01, seg=1))
    parts.append(cyl("pillar", 0.05, 0.7, (x, y, 0.02), wd, verts=8))
    for k in range(3):
        a = math.tau * k / 3
        parts.append(cbox("foot", (0.34, 0.06, 0.05), (x + math.cos(a) * 0.16, y + math.sin(a) * 0.16, 0.03), wd, rot=(0, 0, a)))


def cafe_table_set():
    """Cafe table with two chairs drawn up, cups and a copper pot left out, a candle in a glass."""
    reset()
    parts = []
    _round_table(parts)
    _chair(parts, 0.0, 0.62, 0.0)
    _chair(parts, 0.1, -0.64, math.pi + 0.2)
    for (x, y) in ((0.12, 0.2), (-0.1, -0.2)):
        parts.append(cyl("saucer", 0.07, 0.01, (x, y, 0.76), M("plaster_white"), verts=10))
        parts.append(cyl("cup", 0.04, 0.06, (x, y, 0.77), M("plaster_white"), verts=10, r2=0.045))
        parts.append(cyl("coffee", 0.038, 0.005, (x, y, 0.825), M("coffee"), verts=10))
    parts.append(cyl("pot", 0.06, 0.14, (-0.18, 0.12, 0.76), M("bronze", 0.35), verts=10, r2=0.04))
    parts.append(cyl("candle_glass", 0.045, 0.12, (0.2, -0.05, 0.76), M("glass"), verts=8))
    parts.append(cyl("candle", 0.02, 0.07, (0.2, -0.05, 0.765), M("flame", 0.9, emit=(1.0, 0.62, 0.25), emit_strength=5.0), verts=6))
    export("cafe_table_set", join(parts, "cafe_table_set"), cyl("c", 0.45, 0.8, (0, 0, 0), None, verts=8))


def chairs_stacked():
    """Closed for the winter: chairs upturned on a table, snow on the legs and the table edge."""
    reset()
    parts = []
    _round_table(parts)
    for f_ in (0.3, 2.9):
        _chair(parts, -math.sin(f_) * 0.26, math.cos(f_) * 0.26, f_, upturned_z=0.76)
    parts.append(edit_verts(blob("snow", (0.5, 0.5, 0.04), (0, 0, 1.24), M("snow"), subsurf=1), lambda co: None))
    parts.append(cyl("edge_snow", 0.4, 0.03, (0, 0, 0.76), M("snow"), verts=14))
    _chair(parts, 0.75, 0.2, 1.8, snow=True)            # one left out, drifted
    export("chairs_stacked", join(parts, "chairs_stacked"), box("c", (1.5, 1.0, 1.2), (0.3, 0, 0)))


# ------------------------------------------------------------------ the inn yard and street furniture
def cellar_hatch():
    """Wine-cellar entrance: stone kerb round a pair of sloping plank doors, one propped open on the dark stair.
    Origin = middle of the back edge on the wall; 1.5 m wide, projects 1.3 m."""
    reset()
    W, D = 1.5, 1.3
    st = M("stone_dark")
    parts = [box("kerb_l", (0.2, D, 0.5), (-W / 2 - 0.1, -D / 2, 0), st, bevel=0.02, seg=1, wonk=0.02),
             box("kerb_r", (0.2, D, 0.5), (W / 2 + 0.1, -D / 2, 0), st, bevel=0.02, seg=1, wonk=0.02),
             box("kerb_f", (W + 0.4, 0.2, 0.15), (0, -D - 0.1, 0), st, bevel=0.02, seg=1),
             box("void", (W, D - 0.02, 0.02), (0, -D / 2, 0.02), M("void"))]
    for sx in (-1, 1):
        edit_verts(parts[0 if sx < 0 else 1], lambda co: setattr(co, "z", 0.15 + (0.35 * (co.y + D) / D) if co.z > 0.1 else co.z))
    ang = math.atan2(0.35, D)
    L = math.hypot(D, 0.35)
    parts.append(cbox("leaf_l", (W / 2 - 0.02, L, 0.05), (-W / 4, -D / 2, 0.35), M("wood"), rot=(ang, 0, 0), bevel=0.008, seg=1))
    for k in range(3):
        parts.append(cbox("strap", (W / 2 - 0.08, 0.05, 0.015), (-W / 4, -0.2 - k * 0.45, 0.46 - k * 0.12), M("iron"), rot=(ang, 0, 0)))
    parts.append(cbox("leaf_r", (0.05, L, W / 2 - 0.02), (W / 2 + 0.23, -D / 2, 0.35 + W / 4 + 0.05), M("wood"), bevel=0.008, seg=1))
    for k in range(3):
        parts.append(box("strap_r", (0.015, L - 0.1, 0.05), (W / 2 + 0.2, -D / 2, 0.55 + k * 0.22), M("iron")))
    parts.append(edit_verts(blob("snow", (W / 2, 0.8, 0.04), (-W / 4, -D / 2, 0.4), M("snow"), subsurf=1),
                            lambda co: setattr(co, "z", co.z + 0.27 * (co.y + D / 2) / D)))
    export("cellar_hatch", join(parts, "cellar_hatch"), box("c", (W + 0.4, D + 0.2, 0.55), (0, -(D + 0.2) / 2, 0)))


def notice_board():
    """Parish notice board on two posts under a little shingled roof, posted with Austrian proclamations and a
    theatre bill. 1.6 m wide."""
    reset()
    wd = M("wood_dark")
    parts = []
    for sx in (-0.8, 0.8):
        parts.append(box("post", (0.1, 0.1, 2.35), (sx, 0, 0), wd, bevel=0.01, seg=1))
    parts.append(box("board", (1.6, 0.05, 1.0), (0, 0, 1.0), M("wood"), bevel=0.01, seg=1))
    parts.append(box("frame", (1.7, 0.07, 0.06), (0, 0, 0.97), wd))
    parts.append(roof("roof", 1.95, 0.5, 0.22, (0, 0, 2.08), M("tile_dark"), sag=0.02, flare=0.1, cuts=3))
    parts.append(roof("rsnow", 1.9, 0.46, 0.26, (0, 0, 2.1), M("snow"), sag=0.02, flare=0.1, cuts=3, top_w=0.1))
    bills = [(-0.45, 1.5, 0.5, 0.62, "paper", "PATENT"), (0.2, 1.62, 0.55, 0.4, "paper_old", "THEATER"),
             (0.35, 1.18, 0.42, 0.34, "paper", "Obwieszczenie"), (-0.5, 1.08, 0.36, 0.3, "paper_old", None),
             (0.6, 1.5, 0.2, 0.3, "linen", None)]
    for i, (x, zc, w, h, mat, title) in enumerate(bills):
        yf = -0.03 - 0.002 * i
        parts.append(cbox("bill", (w, 0.004, h), (x, yf, zc), M(mat), rot=(0, (i % 3 - 1) * 0.03, 0)))
        if title:
            parts.append(_text("title", title, h * 0.13, (x, yf - 0.004, zc + h * 0.32), M("ink"), depth=0.0, width=w * 0.85, res=1))
        for k in range(4 if title else 3):
            lw = w * (0.75 if k % 2 else 0.6)
            parts.append(box("line", (lw, 0.002, 0.012), (x, yf - 0.003, zc + h * 0.12 - k * h * 0.14), M("ink")))
    parts.append(sphere("seal", 0.03, (-0.45, -0.04, 1.28), M("crimson", 0.4), seg=8, rings=4))
    export("notice_board", join(parts, "notice_board"), box("c", (1.8, 0.2, 2.3), (0, 0, 0)))


def water_trough():
    """Hewn stone horse trough, frozen over, with a crust of snow on the rim and a bucket left by it."""
    reset()
    st = M("stone")
    parts = [box("trough", (1.8, 0.6, 0.6), (0, 0, 0), st, bevel=0.03, seg=1, wonk=0.02),
             box("ice", (1.6, 0.44, 0.02), (0, 0, 0.5), M("ice", 0.08)),
             box("plinth", (1.9, 0.7, 0.08), (0, 0, 0), M("stone_dark"), bevel=0.02, seg=1)]
    for sx in (-1, 1):
        parts.append(edit_verts(blob("snow", (0.5, 0.64, 0.05), (sx * 0.55, 0, 0.59), M("snow"), subsurf=1), lambda co: None))
    parts.append(cyl("bucket", 0.15, 0.28, (1.2, 0.2, 0), M("wood"), verts=10, r2=0.13, bevel=0.01, seg=1))
    parts.append(cyl("bucket_hoop", 0.155, 0.03, (1.2, 0.2, 0.2), M("iron"), verts=10))
    export("water_trough", join(parts, "water_trough"), box("c", (1.9, 0.7, 0.65), (0, 0, 0)))


def hitching_post():
    """Oak tethering post with an iron ring and a stone foot, a halter rope still knotted to it."""
    reset()
    parts = [cyl("post", 0.09, 1.15, (0, 0, 0), M("wood_dark"), verts=8, r2=0.08, bevel=0.01, seg=1),
             cyl("foot", 0.16, 0.2, (0, 0, 0), M("stone_dark"), verts=8, r2=0.13, bevel=0.01, seg=1),
             sphere("cap", 0.1, (0, 0, 1.15), M("wood_dark"), seg=8, rings=5, zscale=0.6),
             torus("ring", 0.07, 0.012, (0, -0.1, 0.95), M("iron"), rot=(0, math.pi / 2, 0), seg=12, mseg=4),
             cyl("snow", 0.08, 0.05, (0, 0, 1.2), M("snow"), verts=8, r2=0.03)]
    bm = bmesh.new()
    pts = [(0, -0.1, 0.88), (0.05, -0.2, 0.7), (0.12, -0.28, 0.45), (0.2, -0.3, 0.2)]
    for a, b in zip(pts, pts[1:]):
        _tube(bm, a, b, 0.012, 0.012, 4)
    parts.append(_bm_obj("rope", bm, M("sacking")))
    export("hitching_post", join(parts, "hitching_post"), cyl("c", 0.12, 1.2, (0, 0, 0), None, verts=6))


def woodpile_leanto():
    """Firewood stacked under a plank lean-to against a wall, a chopping block and axe in front.
    Origin = middle of the back edge on the wall; 2.4 m wide, 1.1 m deep."""
    reset()
    W, D = 2.4, 1.1
    wd = M("wood_dark")
    parts = []
    for sx in (-1, 1):
        parts.append(box("post", (0.1, 0.1, 1.75), (sx * (W / 2 - 0.05), -D + 0.05, 0), wd, bevel=0.01, seg=1))
        parts.append(box("wall_post", (0.1, 0.08, 2.15), (sx * (W / 2 - 0.05), -0.04, 0), wd))
    ang = math.atan2(0.45, D + 0.2)
    L = math.hypot(D + 0.2, 0.45)
    parts.append(cbox("roof", (W + 0.2, L, 0.05), (0, -(D + 0.2) / 2, 1.97), M("wood"), rot=(ang, 0, 0), bevel=0.008, seg=1))
    parts.append(cbox("rsnow", (W + 0.1, L - 0.1, 0.07), (0, -(D + 0.2) / 2, 2.03), M("snow"), rot=(ang, 0, 0), bevel=0.02, seg=1))
    rng = random.Random(141)
    bm = bmesh.new()
    rows = 7
    for r in range(rows):
        n = 11
        for k in range(n):
            x = -W / 2 + 0.15 + (W - 0.3) * (k + 0.5 * (r % 2)) / n
            if x > W / 2 - 0.12:
                continue
            rr = rng.uniform(0.07, 0.09)
            z = 0.09 + r * 0.16
            y0, y1 = -0.08, -D + 0.12 + rng.uniform(-0.04, 0.04)
            _tube(bm, (x, y0, z), (x, y1, z), rr, rr, 7)
            f = [bm.verts.new((x + math.cos(math.tau * j / 7) * rr, y1, z + math.sin(math.tau * j / 7) * rr)) for j in range(7)]
            bm.faces.new(list(reversed(f)))
    parts.append(_bm_obj("logs", bm, M("log")))
    parts.append(cyl("block", 0.24, 0.45, (0.6, -D - 0.45, 0), M("log"), verts=10, bevel=0.01, seg=1))
    parts.append(cbox("axe_handle", (0.04, 0.04, 0.7), (0.62, -D - 0.5, 0.7), M("wood"), rot=(0.4, 0.1, 0)))
    parts.append(box("axe_head", (0.03, 0.16, 0.1), (0.62, -D - 0.36, 0.4), M("iron")))
    for k in range(3):
        parts.append(cyl("split", 0.07, 0.35, (-0.5 + k * 0.2, -D - 0.4 - k * 0.1, 0.07), M("log"), verts=6, rot=(0, math.pi / 2, k), center=True))
    export("woodpile_leanto", join(parts, "woodpile_leanto"), box("c", (W, D, 1.9), (0, -D / 2, 0)))


def coach():
    """Travelling coach (kareta) at the inn: dark-green lacquered body on perch and leather braces, red wheels,
    coachman's box forward, luggage on the roof under snow. Pole towards +X (Godot +X at rot 0)."""
    reset()
    body, red, blk = M("coach_green"), M("coach_red"), M("black", 0.5)
    parts = []
    b = box("body", (1.9, 1.35, 1.25), (-0.1, 0, 1.0), body, bevel=0.06, seg=2)
    edit_verts(b, lambda co: setattr(co, "x", -0.1 + (co.x + 0.1) * (0.82 if co.z < 1.2 else 1.0)))
    parts.append(b)
    for sy in (-1, 1):
        y = sy * 0.68
        parts.append(box("win", (0.5, 0.03, 0.5), (-0.1, y, 1.55), M("glass_warm" if sy < 0 else "glass")))
        for sx in (-0.7, 0.5):
            parts.append(box("qwin", (0.3, 0.03, 0.42), (sx, y, 1.6), M("glass")))
        parts.append(box("door_frame", (0.66, 0.04, 1.05), (-0.1, y, 1.05), M("gold", 0.4)))
        parts.append(box("door", (0.6, 0.05, 0.98), (-0.1, y, 1.08), body))
        parts.append(box("crest", (0.18, 0.06, 0.2), (-0.1, y, 1.25), M("gold", 0.4)))
        parts.append(box("step", (0.35, 0.2, 0.03), (-0.1, sy * 0.8, 0.55), M("iron")))
        parts.append(box("perch_brace", (2.8, 0.06, 0.06), (-0.1, sy * 0.45, 0.72), M("leather")))
        for (wx, r) in ((-0.95, 0.72), (1.15, 0.52)):
            wy = sy * 0.86
            parts.append(torus("rim", r, 0.04, (wx, wy, r), red, rot=(math.pi / 2, 0, 0), seg=20, mseg=5))
            parts.append(torus("tyre", r + 0.03, 0.025, (wx, wy, r), M("iron", 0.5), rot=(math.pi / 2, 0, 0), seg=20, mseg=4))
            parts.append(cyl("hub", 0.09, 0.2, (wx, wy, r), red, verts=10, rot=(math.pi / 2, 0, 0), center=True))
            for k in range(6):
                parts.append(cbox("spoke", (0.035, 0.035, r * 2 - 0.06), (wx, wy, r), red, rot=(0, math.pi * k / 6, 0)))
            parts.append(cyl("axle", 0.04, 0.9, (wx, sy * 0.4, r), blk, verts=6, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(box("perch", (2.9, 0.12, 0.1), (0.05, 0, 0.52), M("wood_dark")))
    parts.append(box("undercarriage", (0.4, 1.4, 0.12), (1.15, 0, 0.62), M("wood_dark")))
    parts.append(box("roof", (1.95, 1.42, 0.08), (-0.1, 0, 2.25), blk, bevel=0.03, seg=1))
    parts.append(box("trunk", (1.1, 0.8, 0.4), (-0.25, 0, 2.33), M("leather"), bevel=0.04, seg=1))
    parts.append(edit_verts(blob("snow", (1.8, 1.3, 0.08), (-0.1, 0, 2.31), M("snow"), subsurf=1), lambda co: None))
    parts.append(edit_verts(blob("snow_t", (1.0, 0.72, 0.07), (-0.25, 0, 2.72), M("snow"), subsurf=1), lambda co: None))
    parts.append(box("boot", (0.5, 1.0, 0.45), (1.12, 0, 0.72), body, bevel=0.03, seg=1))
    parts.append(box("box_seat", (0.4, 0.9, 0.12), (1.2, 0, 1.55), M("leather"), bevel=0.02, seg=1))
    parts.append(box("box_back", (0.08, 0.9, 0.3), (1.0, 0, 1.55), M("leather")))
    parts.append(box("hammercloth", (0.44, 0.95, 0.4), (1.2, 0, 1.17), M("crimson", 0.8)))
    parts.append(cbox("footboard", (0.4, 0.8, 0.04), (1.55, 0, 1.2), M("wood_dark"), rot=(0, -0.5, 0)))
    for sy in (-1, 1):
        parts.append(box("lamp", (0.12, 0.12, 0.2), (0.95, sy * 0.55, 1.75), M("iron")))
    bm = bmesh.new()
    _tube(bm, (1.3, 0, 0.62), (3.4, 0, 0.45), 0.045, 0.035, 6)
    parts.append(_bm_obj("pole", bm, M("wood_dark")))
    parts.append(box("swingletree", (0.1, 0.9, 0.06), (1.75, 0, 0.58), M("wood_dark")))
    export("coach", join(parts, "coach"), box("c", (3.0, 1.9, 2.4), (0.05, 0, 0)))


# ------------------------------------------------------------------ everyday clutter
def shovel_broom():
    """Snow shovel and birch broom leaned on a wall by a heap of cleared snow. Origin = on the wall at the pavement."""
    reset()
    parts = [cbox("shovel_h", (0.04, 0.04, 1.3), (-0.3, -0.15, 0.62), M("wood"), rot=(-0.2, 0.05, 0)),
             cbox("shovel_blade", (0.38, 0.03, 0.42), (-0.28, -0.26, 0.2), M("wood_dark"), rot=(-0.2, 0.05, 0), bevel=0.008, seg=1),
             cbox("broom_h", (0.035, 0.035, 1.3), (0.25, -0.18, 0.72), M("wood"), rot=(-0.18, -0.08, 0))]
    rng = random.Random(151)
    bm = bmesh.new()
    for k in range(26):
        a = rng.uniform(0, math.tau)
        top = Vector((0.24 + math.cos(a) * 0.03, -0.24 + math.sin(a) * 0.03, 0.42))
        bot = Vector((0.24 + math.cos(a) * rng.uniform(0.05, 0.16), -0.28 + math.sin(a) * rng.uniform(0.04, 0.1), 0.02))
        _tube(bm, top, bot, 0.006, 0.003, 3)
    parts.append(_bm_obj("twigs", bm, M("dead_stalk")))
    parts.append(cyl("binding", 0.04, 0.08, (0.24, -0.24, 0.4), M("sacking"), verts=8))
    parts.append(_lumpy("heap", 0.5, (-0.7, -0.35, 0.0), M("snow_dirty"), zscale=0.5, amp=0.18, seed=152, seg=12, rings=7, zmin=-0.01))
    parts.append(_lumpy("heap2", 0.35, (-1.2, -0.3, 0.0), M("snow"), zscale=0.45, amp=0.2, seed=153, seg=10, rings=6, zmin=-0.01))
    export("shovel_broom", join(parts, "shovel_broom"))


def sacks_crates():
    """Deliveries at a shop door: two crates, three sacks slumped against them, a wicker basket of turnips."""
    reset()
    rng = random.Random(161)
    parts = [box("crate", (0.7, 0.5, 0.45), (0, 0, 0), M("wood"), bevel=0.015, seg=1, wonk=0.02),
             box("crate2", (0.55, 0.45, 0.4), (0.05, 0.02, 0.45), M("wood_dark"), bevel=0.015, seg=1, wonk=0.02, rot=(0, 0, 0.2))]
    for (x, y) in ((-0.62, -0.05), (0.62, -0.1), (-0.5, -0.45)):
        parts.append(_lumpy("sack", 0.25, (x, y, 0.22), M("sacking"), zscale=1.25, amp=0.12, seed=rng.randint(0, 999), seg=10, rings=7, zmin=0.0))
        parts.append(cyl("tie", 0.07, 0.08, (x, y, 0.5), M("sacking"), verts=6, r2=0.03))
    parts.append(edit_verts(blob("snow", (0.6, 0.4, 0.04), (0.05, 0.02, 0.85), M("snow"), subsurf=1), lambda co: None))
    parts.append(cyl("basket", 0.2, 0.22, (0.7, -0.5, 0), M("straw"), verts=10, r2=0.24, bevel=0.01, seg=1))
    for k in range(5):
        a = math.tau * k / 5
        parts.append(sphere("turnip", 0.07, (0.7 + math.cos(a) * 0.1, -0.5 + math.sin(a) * 0.1, 0.24), M("flower_white"), seg=7, rings=4))
    export("sacks_crates", join(parts, "sacks_crates"), box("c", (1.5, 0.8, 0.8), (0.05, -0.1, 0)))


def handcart():
    """Two-wheeled barrow of a porter, its handles down on the cobbles, a sack and a rope in the bed."""
    reset()
    wd, w = M("wood_dark"), M("wood")
    parts = [box("bed", (0.9, 1.3, 0.06), (0, 0, 0.5), w, bevel=0.01, seg=1)]
    for sx in (-1, 1):
        parts.append(box("side", (0.04, 1.3, 0.25), (sx * 0.45, 0, 0.56), w))
        parts.append(torus("wheel", 0.42, 0.035, (sx * 0.55, 0.15, 0.44), wd, rot=(0, math.pi / 2, 0), seg=16, mseg=5))
        for k in range(4):
            parts.append(cbox("spoke", (0.03, 0.03, 0.8), (sx * 0.55, 0.15, 0.44), wd, rot=(math.pi * k / 4, 0, 0)))
        parts.append(cyl("hub", 0.07, 0.12, (sx * 0.55, 0.15, 0.44), wd, verts=8, rot=(0, math.pi / 2, 0), center=True))
        bm = bmesh.new()
        _tube(bm, (sx * 0.4, -0.6, 0.5), (sx * 0.35, -1.5, 0.05), 0.03, 0.028, 6)
        parts.append(_bm_obj("handle", bm, wd))
        parts.append(cbox("leg", (0.04, 0.04, 0.45), (sx * 0.4, 0.55, 0.26), wd))
    parts.append(cyl("axle", 0.03, 1.1, (0, 0.15, 0.44), wd, verts=6, rot=(0, math.pi / 2, 0), center=True))
    parts.append(_lumpy("sack", 0.25, (0.1, 0.1, 0.72), M("sacking"), zscale=0.7, amp=0.12, seed=171, seg=10, rings=6))
    parts.append(torus("rope", 0.15, 0.015, (-0.2, -0.3, 0.56), M("sacking"), seg=12, mseg=4))
    export("handcart", join(parts, "handcart"), box("c", (1.1, 1.6, 0.9), (0, 0, 0)))


def sledge():
    """Hand sledge on curled runners with a load of firewood roped on; propped by a wall or left in the snow."""
    reset()
    wd = M("wood_dark")
    parts = []
    for sx in (-1, 1):
        bm = bmesh.new()
        pts = [(sx * 0.3, 0.7, 0.03), (sx * 0.3, -0.5, 0.03), (sx * 0.3, -0.72, 0.1), (sx * 0.3, -0.8, 0.26), (sx * 0.3, -0.7, 0.36)]
        for a, b in zip(pts, pts[1:]):
            _tube(bm, a, b, 0.025, 0.025, 5)
        parts.append(_bm_obj("runner", bm, M("iron", 0.5)))
        for y in (-0.4, 0.0, 0.5):
            parts.append(box("knee", (0.04, 0.04, 0.2), (sx * 0.3, y, 0.05), wd))
    for k in range(6):
        parts.append(box("slat", (0.72, 0.14, 0.03), (0, -0.45 + k * 0.2, 0.25), M("wood"), bevel=0.005, seg=1))
    for k in range(4):
        parts.append(cyl("log", 0.07, 0.9, (-0.2 + k * 0.13, 0.05, 0.36 + (k % 2) * 0.06), M("log"), verts=7, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(box("rope", (0.7, 0.02, 0.02), (0, 0.05, 0.47), M("sacking")))
    parts.append(edit_verts(blob("snow", (0.5, 0.6, 0.04), (0, 0.1, 0.45), M("snow"), subsurf=1), lambda co: None))
    export("sledge", join(parts, "sledge"), box("c", (0.7, 1.6, 0.5), (0, -0.05, 0)))


def muck_heap():
    """Stable muck and old straw, steaming faintly by the inn yard, a pitchfork stuck in it."""
    reset()
    parts = [_lumpy("muck", 0.9, (0, 0, 0.0), M("muck"), zscale=0.5, amp=0.18, seed=181, seg=14, rings=8, zmin=-0.02),
             _lumpy("straw", 0.6, (0.3, -0.2, 0.1), M("straw"), zscale=0.45, amp=0.2, seed=182, seg=10, rings=6, zmin=-0.02),
             _lumpy("snow", 0.45, (-0.25, 0.25, 0.25), M("snow_dirty"), zscale=0.35, amp=0.2, seed=183, seg=10, rings=6)]
    parts.append(cbox("fork", (0.035, 0.035, 1.4), (0.2, 0.1, 0.95), M("wood"), rot=(0.25, 0.15, 0)))
    for k in (-1, 0, 1):
        parts.append(cbox("tine", (0.012, 0.012, 0.3), (0.08 + k * 0.05, -0.06, 0.25), M("iron"), rot=(0.25, 0.15, 0)))
    export("muck_heap", join(parts, "muck_heap"), box("c", (1.5, 1.5, 0.5), (0, 0, 0)))


def doormat_scraper():
    """Rush doormat at a threshold and an iron boot scraper set into a stone beside it. Origin = mat centre."""
    reset()
    parts = [box("mat", (0.9, 0.55, 0.018), (0, 0, 0.0), M("straw"), bevel=0.005, seg=1)]
    for k in range(4):
        parts.append(box("weave", (0.86, 0.02, 0.004), (0, -0.2 + k * 0.13, 0.018), M("dead_stalk")))
    parts.append(box("stone", (0.3, 0.2, 0.08), (0.75, 0, 0), M("stone_dark"), bevel=0.01, seg=1))
    for sx in (-1, 1):
        parts.append(box("upright", (0.02, 0.02, 0.2), (0.75 + sx * 0.12, 0, 0.08), M("iron")))
        parts.append(sphere("knob", 0.02, (0.75 + sx * 0.12, 0, 0.29), M("iron"), seg=6, rings=4))
    parts.append(box("blade", (0.26, 0.012, 0.05), (0.75, 0, 0.14), M("iron")))
    export("doormat_scraper", join(parts, "doormat_scraper"))


def trampled_snow():
    """Old snow shovelled to the wall foot and packed by boots: an irregular slush apron (boot prints and dirt
    streaks baked into its grey-blue slush texture) whose rim sinks among the setts. Origin = on the wall at the
    pavement; 3 m along the wall, up to 1.4 m out."""
    reset()
    rng = random.Random(191)
    ring = []
    n = 26
    for k in range(n):
        t = k / (n - 1)
        x = -1.5 + 3.0 * t
        y = -(0.35 + 1.0 * math.sin(math.pi * t) ** 0.8 * rng.uniform(0.75, 1.1))
        ring.append((x, y))
    outline_pts = ring + [(1.5, 0.02), (0.5, 0.02), (-0.5, 0.02), (-1.5, 0.02)]
    parts = [_slush_patch("slush", outline_pts, (0.0, -0.35), lift=0.02, seed=193)]
    parts.append(_lumpy("drift", 0.5, (0.0, -0.1, 0.0), M("snow"), zscale=0.28, amp=0.2, seed=192, seg=14, rings=6, zmin=-0.01))
    edit_verts(parts[-1], lambda co: (setattr(co, "x", co.x * 2.4), setattr(co, "y", min(co.y, 0.0))))
    export("trampled_snow", join(parts, "trampled_snow"))


# ------------------------------------------------------------------ the churchyard green
def park_railing():
    """3 m of low wrought-iron railing on a sandstone kerb: spear-headed bars between square posts."""
    reset()
    L = 3.0
    iron = M("iron", 0.55)
    parts = [box("kerb", (L, 0.28, 0.2), (0, 0, 0), M("stone"), bevel=0.02, seg=1, wonk=0.02),
             box("kerb_snow", (L - 0.05, 0.22, 0.03), (0, 0, 0.2), M("snow"), bevel=0.01, seg=1)]
    for x in (-L / 2 + 0.06, L / 2 - 0.06):
        parts.append(box("post", (0.08, 0.08, 1.0), (x, 0, 0.2), iron))
        parts.append(sphere("ball", 0.05, (x, 0, 1.24), iron, seg=8, rings=5))
    for z in (0.3, 0.95):
        parts.append(box("rail", (L - 0.1, 0.03, 0.03), (0, 0, z), iron))
    n = 20
    for k in range(n):
        x = -L / 2 + 0.15 + (L - 0.3) * k / (n - 1)
        parts.append(box("bar", (0.018, 0.018, 0.85), (x, 0, 0.23), iron))
        parts.append(pyramid("spear", (0.045, 0.02, 0.09), (x, 0, 1.08), iron))
    export("park_railing", join(parts, "park_railing"), box("c", (L, 0.3, 1.1), (0, 0, 0)))


def hedge():
    """3 m of clipped yew/box hedge in winter, 0.85 m high: a round-shouldered shell displaced 2-4 cm by layered
    noise and clad in a baked leaf-cluster texture, torn open in places onto a near-black core, broken caps of
    snow on the top and a few twigs the shears missed."""
    from mathutils import noise as mnoise
    reset()
    rng = random.Random(211)
    hx, hy, H, R = 1.5, 0.36, 0.85, 0.13
    step = 0.085
    bm = bmesh.new()

    def grid(axis_u, axis_v, fixed, nu, nv, u0, u1, v0, v1):
        vs = []
        for i in range(nu + 1):
            row = []
            for j in range(nv + 1):
                p = [0.0, 0.0, 0.0]
                p[axis_u] = u0 + (u1 - u0) * i / nu
                p[axis_v] = v0 + (v1 - v0) * j / nv
                p[fixed[0]] = fixed[1]
                row.append(bm.verts.new(p))
            vs.append(row)
        for i in range(nu):
            for j in range(nv):
                bm.faces.new((vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]))
    nx, ny, nz = int(2 * hx / step), max(4, int(2 * hy / step)), int(H / step)
    grid(0, 2, (1, -hy), nx, nz, -hx, hx, 0.0, H)
    grid(0, 2, (1, hy), nx, nz, -hx, hx, 0.0, H)
    grid(1, 2, (0, -hx), ny, nz, -hy, hy, 0.0, H)
    grid(1, 2, (0, hx), ny, nz, -hy, hy, 0.0, H)
    grid(0, 1, (2, H), nx, ny, -hx, hx, -hy, hy)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    ix, iy, iz = hx - R, hy - R, H - R
    for v in bm.verts:
        p = v.co.copy()
        c = Vector((max(-ix, min(ix, p.x)), max(-iy, min(iy, p.y)), min(iz, p.z)))
        d = p - c
        nrm = d.normalized() if d.length > 1e-6 else Vector((0, 0, 1))
        base = c + nrm * R
        q = base * 3.0
        dn = (mnoise.noise(q) * 0.6 + mnoise.noise(q * 2.7 + Vector((5, 1, 3))) * 0.3 + mnoise.noise(q * 7.1) * 0.15)
        amt = 0.03 + 0.012 * dn
        if base.z < 0.1:
            amt *= base.z / 0.1                       # the foot stays tucked on the ground
        v.co = base + nrm * (amt - 0.03) + Vector((0, 0, 0))
        v.co.z = max(0.0, v.co.z)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    holes = [f for f in bm.faces if 0.18 < f.calc_center_median().z < H - 0.12 and abs(f.normal.z) < 0.5 and rng.random() < 0.025]
    bmesh.ops.delete(bm, geom=holes, context="FACES_ONLY")
    for f in bm.faces:
        f.smooth = True
    shell = _bm_obj("shell", bm, M("hedge_leaf"))
    core = box("core", (2 * hx - 0.14, 2 * hy - 0.14, H - 0.1), (0, 0, 0), M("hedge_core", 0.95))
    parts = [shell, core]
    for k in range(7):                                  # broken snow caps
        x = -1.25 + k * 0.42 + rng.uniform(-0.1, 0.1)
        cap = _lumpy("snowcap", 0.32, (x, rng.uniform(-0.04, 0.04), H - 0.035), M("snow"), zscale=0.2, amp=0.25,
                     seed=220 + k, seg=10, rings=5, zmin=H - 0.06)
        edit_verts(cap, lambda co, x=x: setattr(co, "x", x + (co.x - x) * rng.uniform(0.9, 1.5)))
        parts.append(cap)
    tw = bmesh.new()
    for k in range(18):
        side = rng.choice((-1, 1))
        if k % 3 == 0:
            p0 = Vector((rng.uniform(-1.3, 1.3), rng.uniform(-0.2, 0.2), H))
            d = Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 1.0)).normalized()
        else:
            p0 = Vector((rng.uniform(-1.35, 1.35), side * (hy - 0.02), rng.uniform(0.3, H - 0.1)))
            d = Vector((rng.uniform(-0.4, 0.4), side * 1.0, rng.uniform(0.1, 0.7))).normalized()
        L = rng.uniform(0.1, 0.22)
        _tube(tw, p0 - d * 0.04, p0 + d * L, 0.005, 0.0, 3)
        _tube(tw, p0 + d * L * 0.5, p0 + d * L * 0.5 + (d + Vector((0.3, 0.2, 0.2))).normalized() * L * 0.4, 0.003, 0.0, 3)
    parts.append(_bm_obj("twigs", tw, M("dead_stalk")))
    export("hedge", join(parts, "hedge"), box("c", (2 * hx, 2 * hy, H), (0, 0, 0)))


def lawn_snow():
    """Snow-covered lawn: a soft 6 x 5 m cushion a hand deep that feathers out to nothing at the edges, dead grass
    showing through in patches."""
    reset()
    rng = random.Random(221)
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=16, y_subdivisions=14, size=1.0, location=(0, 0, 0))
    o = _finish_prim(bpy.context.object, "lawn", M("snow"))

    def f(co):
        x, y = co.x * 6.0, co.y * 5.0
        edge = min(3.0 - abs(x), 2.5 - abs(y))
        k = max(0.0, min(1.0, edge / 0.6))
        co.x, co.y = x, y
        co.z = (0.07 + rng.uniform(-0.015, 0.02)) * k - 0.01 * (1 - k)
    edit_verts(o, f)
    for p in o.data.polygons:
        p.use_smooth = True
    parts = [o]
    export("lawn_snow", join(parts, "lawn_snow"))


def gravel_path():
    """Raked gravel path, 1.4 x 6 m, trodden snow along its middle. Lies on the setts (top 3 cm)."""
    reset()
    rng = random.Random(231)
    parts = [box("path", (1.4, 6.0, 0.03), (0, 0, -0.005), M("gravel", 0.95), bevel=0.01, seg=1)]
    for k in range(10):
        parts.append(edit_verts(blob("tread", (rng.uniform(0.3, 0.5), rng.uniform(0.5, 1.0), 0.02),
                                     (rng.uniform(-0.2, 0.2), -2.6 + k * 0.58, 0.02), M("snow_dirty"), subsurf=1), lambda co: None))
    for sx in (-1, 1):
        parts.append(box("edge", (0.08, 6.0, 0.06), (sx * 0.74, 0, -0.01), M("stone_dark"), bevel=0.01, seg=1))
    export("gravel_path", join(parts, "gravel_path"))


# ------------------------------------------------------------------ cloth: laundry and awnings as draped panels
PAL.update({"cloth_laundry_linen": (0.92, 0.90, 0.84), "cloth_laundry_undyed": (0.74, 0.68, 0.56),
            "cloth_laundry_indigo": (0.16, 0.22, 0.42), "cloth_laundry_red": (0.66, 0.12, 0.10),
            "cloth_laundry_frozen": (0.84, 0.86, 0.88), "slush_trod": (1.0, 1.0, 1.0)})
TEX_OF.update({"cloth_laundry_linen": "cloth", "cloth_laundry_undyed": "cloth", "cloth_laundry_indigo": "cloth",
               "cloth_laundry_red": "cloth", "cloth_laundry_frozen": "cloth", "slush_trod": "slush"})
TINT.update({"slush_trod": (1.0, 1.0, 1.0)})


def _grid_faces(bm, grid, smooth=True, up=False):
    """Quads over a vertex grid; up=True flips any face whose normal points down (roof-like cloth seen from above)."""
    nu, nv = len(grid) - 1, len(grid[0]) - 1
    faces = []
    for i in range(nu):
        row = []
        for j in range(nv):
            f = bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
            f.smooth = smooth
            if up:
                f.normal_update()
                if f.normal.z < 0:
                    f.normal_flip()
            row.append(f)
        faces.append(row)
    return faces


def _garment(bm, zline, d0, w, h, nu, nv, seed, frozen=False, belly=0.1, lift=0.12, taper=(1.0, 1.0), foot=0.0,
             x_off=0.0, pegs=True):
    """One hanging piece on a line running along -Y (distance d from the wall hook; z of the line = zline(d)).
    A nu x nv panel pinned at two pegs: catenary sag between them, gathered folds fanning down from the pegs, a
    wind belly out along +X and a hem corner lifted by the wind. Frozen pieces hang stiff: shallow folds, a held
    shape and a couple of sharp cracked creases. Returns the peg distances."""
    rng = random.Random(seed)
    dc = d0 + w / 2
    pa, pb = d0 + 0.05, d0 + w - 0.05
    fold_a = 0.012 if frozen else 0.045
    nf = rng.uniform(4.0, 6.0) * w
    ph = rng.uniform(0, math.tau)
    grid = []
    for i in range(nu + 1):
        t = i / nu
        col = []
        for j in range(nv + 1):
            v = j / nv
            wv = w * (taper[0] + (taper[1] - taper[0]) * v)
            d = dc + (t - 0.5) * wv
            dt = dc + (t - 0.5) * w
            tp = min(max((dt - pa) / max(pb - pa, 1e-3), 0.0), 1.0)
            ztop = zline(min(max(dt, pa), pb)) - 0.035 * w * math.sin(math.pi * tp) - 0.02
            if dt < pa or dt > pb:                               # beyond a peg the corner flops down
                ztop -= 0.25 * abs(dt - (pa if dt < pa else pb))
            z = ztop - h * v * (1.0 + 0.03 * math.sin(math.pi * t))
            x = x_off
            x += fold_a * math.sin(t * nf * math.pi + ph) * v ** 0.6
            x += fold_a * 0.45 * math.sin(t * nf * 2.3 * math.pi + ph * 1.7 + v * 2.0) * v
            for pd in (pa, pb):                                  # pinch folds radiating from each peg
                g = math.exp(-((dt - pd) / 0.09) ** 2)
                x += (0.006 if frozen else 0.02) * g * math.sin(v * 14.0 + pd * 5.0) * (1.0 - v) * 3.0
                z -= 0.012 * g * (1 - v)
            x += belly * math.sin(math.pi * t) * math.sin(math.pi * min(v * 1.15, 1.0)) * (0.5 if frozen else 1.0)
            cw = (max(0.0, (t - 0.55) / 0.45) ** 2) * (max(0.0, (v - 0.55) / 0.45) ** 2)
            z += lift * cw
            x += lift * 0.9 * cw
            d -= 0.04 * cw
            if frozen:                                           # two cracked creases across the stiff cloth
                for cv in (0.38, 0.71):
                    x += 0.014 * max(0.0, 1.0 - abs(v - cv) * 18.0)
            if foot and v > 0.78:                                 # a stocking's foot turns out along the line
                k = (v - 0.78) / 0.22
                d += foot * k
                z += h * 0.12 * k * k
            x += rng.uniform(-0.003, 0.003)
            col.append(bm.verts.new((x, -d, z)))
        grid.append(col)
    _grid_faces(bm, grid, smooth=not frozen)
    return (pa, pb) if pegs else ()


def _laundry(name, items):
    """A 6 m washing line from a wall hook out to a forked pole, hung with draped garments (see _garment).
    Each item: (kind, material key, d0, seed, frozen)."""
    reset()
    Ly, H = 6.0, 3.2

    def zline(d):
        return H - 0.45 * math.sin(math.pi * min(max(d, 0.0), Ly) / Ly)
    parts = [box("wall_hook", (0.06, 0.1, 0.06), (0, -0.05, H - 0.03), M("iron"))]
    bm = bmesh.new()
    pts = [Vector((0, -Ly * k / 16, zline(Ly * k / 16))) for k in range(17)]
    for a, b in zip(pts, pts[1:]):
        _tube(bm, a, b, 0.007, 0.007, 4)
    parts.append(_bm_obj("line", bm, M("sacking")))
    bm = bmesh.new()
    _tube(bm, (0, -Ly, 0), (0, -Ly, H + 0.2), 0.05, 0.04, 6)
    _tube(bm, (0, -Ly, H), (0, -Ly + 0.12, H + 0.3), 0.03, 0.02, 5)
    parts.append(_bm_obj("pole", bm, M("wood_dark")))
    parts.append(cyl("pole_foot", 0.2, 0.05, (0, -Ly, -0.01), M("snow_dirty"), verts=8))
    pegs = []
    for (kind, mat, d0, seed, frozen) in items:
        bm = bmesh.new()
        if kind == "sheet":
            pegs += _garment(bm, zline, d0, 1.15, 1.35, 20, 30, seed, frozen, belly=0.14, lift=0.18)
        elif kind == "sheet_small":
            pegs += _garment(bm, zline, d0, 1.0, 1.1, 16, 24, seed, frozen, belly=0.1, lift=0.12)
        elif kind in ("shirt", "smock"):
            s = 1.0 if kind == "shirt" else 0.7
            pegs += _garment(bm, zline, d0, 0.62 * s, 0.78 * s, 12, 16, seed, frozen, belly=0.06, lift=0.08)
            for side, dd in ((-1, d0 - 0.035), (1, d0 + 0.62 * s - 0.155 * s)):      # sleeves hanging at the shoulders
                _garment(bm, zline, dd + (0.0 if side < 0 else 0.035), 0.155 * s, 0.6 * s, 3, 10, seed + side * 7,
                         frozen, belly=0.015, lift=0.0, taper=(1.0, 0.8), x_off=0.018, pegs=False)
        elif kind == "petticoat":
            pegs += _garment(bm, zline, d0, 0.7, 0.85, 14, 18, seed, frozen, belly=0.09, lift=0.1, taper=(0.9, 1.35))
        elif kind == "apron":
            pegs += _garment(bm, zline, d0, 0.55, 0.7, 10, 14, seed, frozen, belly=0.05, lift=0.08)
            for dd in (d0 + 0.02, d0 + 0.53):
                p0 = Vector((0.0, -dd, zline(dd) - 0.03))
                _tube(bm, p0, p0 + Vector((0.03, -0.02, -0.42)), 0.006, 0.005, 3)
        elif kind == "stockings":
            for k in range(2):
                pegs += _garment(bm, zline, d0 + k * 0.16, 0.11, 0.58, 3, 12, seed + k, frozen, belly=0.01, lift=0.0,
                                 taper=(1.0, 0.8), foot=0.12)
        elif kind == "kerchief":
            pegs += _garment(bm, zline, d0, 0.45, 0.38, 8, 8, seed, frozen, belly=0.03, lift=0.05, taper=(1.0, 0.04))
        parts.append(_bm_obj(kind, bm, M(mat)))
    for pd in pegs:
        parts.append(box("peg", (0.025, 0.018, 0.075), (0.0, -pd, zline(pd) - 0.05), M("wood")))
    return parts, Ly, H


def laundry_line():
    """Washing from a wall hook to a pole: a linen sheet, a shirt with its sleeves hanging, a petticoat, a pair of
    indigo stockings and a red kerchief. Origin = under the wall hook; the line runs 6 m out along -Y at 3.2 m."""
    parts, Ly, H = _laundry("laundry_line", [
        ("sheet", "cloth_laundry_linen", 0.35, 301, False), ("shirt", "cloth_laundry_undyed", 1.7, 302, False),
        ("petticoat", "cloth_laundry_linen", 2.55, 303, False), ("stockings", "cloth_laundry_indigo", 3.5, 304, False),
        ("kerchief", "cloth_laundry_red", 4.05, 305, False)])
    export("laundry_line", join(parts, "laundry_line"), box("c", (0.2, 0.2, H), (0, -Ly, 0)))


def laundry_line_b():
    """The second alley's line: a sheet frozen board-stiff, an indigo apron, a child's smock and undyed stockings."""
    parts, Ly, H = _laundry("laundry_line_b", [
        ("sheet_small", "cloth_laundry_frozen", 0.4, 311, True), ("apron", "cloth_laundry_indigo", 1.65, 312, False),
        ("smock", "cloth_laundry_linen", 2.45, 313, False), ("stockings", "cloth_laundry_undyed", 3.2, 314, True),
        ("kerchief", "cloth_laundry_red", 3.75, 315, False)])
    export("laundry_line_b", join(parts, "laundry_line_b"), box("c", (0.2, 0.2, H), (0, -Ly, 0)))


def _two_mat(o, mat_b, pick):
    """Give `o` a second material and move the faces for which pick(face_centre) is true onto it."""
    o.data.materials.append(mat_b)
    for p in o.data.polygons:
        if pick(p.center):
            p.material_index = 1
    return o


def awning_striped():
    """Striped canvas awning as cloth: the panel sags between the iron arms and bellies under a snow load, a small
    ripple runs across it, and a scalloped valance hangs from the front bar. Origin = top edge on the wall;
    2.0 m wide, projects 1.15 m and drops 0.5 m."""
    reset()
    W, D, drop = 2.0, 1.15, 0.5
    n = 8
    nu, nv = 24, 12
    S = 0.09
    rng = random.Random(401)

    def surf(x, s):
        sag = S * math.sin(math.pi * s) * (1.0 - (2.0 * x / W) ** 2)
        rip = 0.008 * math.sin(x * 17.0 + s * 5.0) * math.sin(math.pi * s)
        return Vector((x, -D * s, -drop * s - sag + rip))
    bm = bmesh.new()
    grid = [[bm.verts.new(surf(-W / 2 + W * i / nu, j / nv)) for j in range(nv + 1)] for i in range(nu + 1)]
    _grid_faces(bm, grid, up=True)
    # the underside too (single-sided glTF materials cull it, and the awning is mostly seen from below)
    dup = bmesh.ops.duplicate(bm, geom=list(bm.faces))
    under = [g for g in dup["geom"] if isinstance(g, bmesh.types.BMFace)]
    bmesh.ops.reverse_faces(bm, faces=under)
    for v in {v for f in under for v in f.verts}:
        v.co.z -= 0.002
    canvas = _bm_obj("canvas", bm, M("canvas"))
    stripe = lambda c: int((c.x + W / 2) / (W / n)) % 2 == 1
    _two_mat(canvas, M("canvas_stripe"), stripe)
    parts = [canvas]
    # valance: a strip hanging from the front bar, its hem cut in one scallop per stripe, a slight flutter
    bm = bmesh.new()
    vu, vv = 64, 4
    grid = []
    for i in range(vu + 1):
        x = -W / 2 + W * i / vu
        fr = ((x + W / 2) / (W / n)) % 1.0
        hem = 0.12 + 0.1 * math.sin(math.pi * fr)
        col = []
        for j in range(vv + 1):
            v = j / vv
            col.append(bm.verts.new((x, -D - 0.012 * math.sin(x * 9.0) * v - 0.004 * v, -drop - 0.01 - hem * v)))
        grid.append(col)
    _grid_faces(bm, grid)
    dup = bmesh.ops.duplicate(bm, geom=list(bm.faces))
    bmesh.ops.reverse_faces(bm, faces=[g for g in dup["geom"] if isinstance(g, bmesh.types.BMFace)])
    val = _bm_obj("valance", bm, M("canvas"))
    _two_mat(val, M("canvas_stripe"), stripe)
    parts.append(val)
    # snow lying in the belly: a cushion that follows the sagging canvas and thins to nothing at its edges
    bm = bmesh.new()
    su, sv = 14, 8
    grid = []
    for i in range(su + 1):
        col = []
        for j in range(sv + 1):
            x = -W * 0.4 + W * 0.8 * i / su
            s = 0.2 + 0.62 * j / sv
            th = 0.06 * math.sin(math.pi * i / su) * math.sin(math.pi * j / sv) * (0.8 + 0.4 * rng.random())
            p = surf(x, s)
            col.append(bm.verts.new((p.x, p.y, p.z + 0.004 + th)))
        grid.append(col)
    _grid_faces(bm, grid, up=True)
    parts.append(_bm_obj("snow", bm, M("snow")))
    parts.append(box("roller", (W + 0.1, 0.1, 0.1), (0, -0.05, -0.05), M("wood_dark"), bevel=0.01, seg=1))
    bm = bmesh.new()
    _tube(bm, (-W / 2 - 0.02, -D, -drop - 0.005), (W / 2 + 0.02, -D, -drop - 0.005), 0.014, 0.014, 6)
    for sx in (-1, 1):
        _tube(bm, (sx * W / 2, 0, -0.9), (sx * W / 2, -D, -drop), 0.015, 0.015, 5)
        _tube(bm, (sx * W / 2, 0, 0), (sx * W / 2, -D, -drop), 0.012, 0.012, 5)
    parts.append(_bm_obj("iron", bm, M("iron")))
    export("awning_striped", join(parts, "awning_striped"))


DRESSING_BUILDS = [
    ("tree_linden", tree_linden), ("tree_chestnut", tree_chestnut), ("shrub_tub", shrub_tub), ("shrub_juniper", shrub_juniper),
    ("pot_herbs", pot_herbs), ("pot_hellebore", pot_hellebore), ("window_box", window_box), ("ivy_patch", ivy_patch),
    ("weed_tuft", weed_tuft), ("straw_scatter", straw_scatter), ("door_wreath", door_wreath),
    ("guild_pretzel", guild_pretzel), ("guild_boot", guild_boot), ("guild_key", guild_key), ("guild_ring", guild_ring),
    ("guild_grapes", guild_grapes), ("guild_tankard", guild_tankard), ("guild_coffee", guild_coffee),
    ("guild_scissors", guild_scissors), ("guild_mortar", guild_mortar),
    ("sign_winiarnia", sign_winiarnia), ("sign_kawiarnia", sign_kawiarnia), ("sign_piekarnia", sign_piekarnia),
    ("sign_apotheke", sign_apotheke), ("sign_goldschmied", sign_goldschmied), ("sign_zajazd", sign_zajazd),
    ("shopfront_bakery", shopfront_bakery), ("shopfront_cloth", shopfront_cloth), ("shopfront_bottles", shopfront_bottles),
    ("awning_striped", awning_striped), ("oriel_cafe", oriel_cafe), ("wall_lantern", wall_lantern),
    ("bench_wood", bench_wood), ("bench_stone", bench_stone), ("cafe_table_set", cafe_table_set), ("chairs_stacked", chairs_stacked),
    ("cellar_hatch", cellar_hatch), ("notice_board", notice_board), ("water_trough", water_trough), ("hitching_post", hitching_post),
    ("woodpile_leanto", woodpile_leanto), ("coach", coach), ("shovel_broom", shovel_broom), ("sacks_crates", sacks_crates),
    ("handcart", handcart), ("sledge", sledge), ("muck_heap", muck_heap), ("doormat_scraper", doormat_scraper),
    ("trampled_snow", trampled_snow), ("laundry_line", laundry_line), ("laundry_line_b", laundry_line_b), ("park_railing", park_railing), ("hedge", hedge),
    ("lawn_snow", lawn_snow), ("gravel_path", gravel_path),
]


# ------------------------------------------------------------------ BUILDINGS PASS 2: more house types, water, industry, faith,
# the castle and the justice props (placed on the outer streets by scripts/city/outer_city.gd)
def _roof_set(parts, L, W, H, loc, mat, along_x=True, sag=0.12, flare=0.1, courses=4, drifts=(), seed=0, ice=True, thick=0.07, top_w=0.0, sides=(-1, 1), cell=1.0):
    """A tiled/shingled roof() with its snow blanket and eave icicles."""
    parts.append(roof("roof", L, W, H, loc, mat, sag=sag, flare=flare, along_x=along_x, courses=courses, ridge=courses > 0 and top_w == 0, top_w=top_w))
    sn = roof_snow("roof_snow", L, W, H, loc, sag=sag, flare=flare, along_x=along_x, top_w=top_w, thick=thick, drifts=drifts, seed=seed, cell=cell)
    if sn:
        parts.append(sn)
    if ice:
        eave_icicles(parts, L - 0.4, W, loc[2] - 0.02, loc[:2], along_x=along_x, seed=seed + 1, sides=sides)


def _hip_set(parts, L, W, H, loc, mat, hip=None, seed=0, thick=0.07):
    parts.append(hip_roof("roof", L, W, H, loc, mat, hip=hip))
    sn = cap_snow("roof_snow", lambda: hip_roof("tmp", L, W, H, loc, None, hip=hip), thick=thick, seed=seed, cell=0.9, slide=0.12, bare=0.17)
    if sn:
        parts.append(sn)
    x, y, z = loc
    icicles(parts, (x - L / 2 + 0.4, y - W / 2), (x + L / 2 - 0.4, y - W / 2), z - 0.02, seed=seed + 1)
    icicles(parts, (x - L / 2 + 0.4, y + W / 2), (x + L / 2 - 0.4, y + W / 2), z - 0.02, seed=seed + 2)


def _upper_windows(parts, plane, xs, z0, w=1.0, h=1.7, mark_=False, shutters=False, col="shutter", style="board", rng=None, surround="stone_pale", shape="rect", warm_p=0.3):
    for x in xs:
        op = (180, 180)
        if rng and rng.random() < 0.25:
            op = (rng.uniform(95, 130), 180)
        win_unit(parts, "-Y", plane, x, z0, w, h, shape, warm=RNG.random() < warm_p, shutters=style if shutters else False,
                 shutter_col=col, shutter_open=op, mark=mark_, surround=surround)


def ten_renaissance(name="ten_renaissance", colour="plaster_straw", shutter_col="shutter_red", seed=21):
    """Renaissance house with a tall Polish attic (attyka) of blind arcades, volutes, obelisks and a sgraffito
    band, hiding a butterfly roof with snow banked in its valley. Rusticated ground floor, framed windows. 9 m."""
    reset()
    rng = random.Random(seed)
    W, D, GF, FL, S = 9.0, 9.0, 4.2, 3.3, 3
    wall = M(colour)
    parts = []
    xs = [-3.0, 0.0, 3.0]
    gops = [(0.0, 0.0, 2.0, 2.9 + 0.12 + 1.0, "round"), (-3.0, 1.2, 1.2, 2.1, "round"), (3.0, 1.2, 1.2, 2.1, "round")]
    y = front_block(parts, W, D, GF, M("stone_pale"), gops)
    door_unit(parts, "-Y", y, 0.0, 2.0, 2.9)
    for (a, zb, w, h, sh) in gops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, bars=True, surround=None, mark=True, warm=RNG.random() < 0.5)
    rustication(parts, "-Y", y, -W / 2, W / 2, 0.5, GF - 0.3, gops, course=0.55, mat=M("stone_pale"))
    plinth(parts, -W / 2, W / 2, y, h=0.5, skip=[(-1.5, 1.5)])
    H = GF + FL * (S - 1)
    ops = [(x, GF + FL * s + 0.8, 1.05, 1.8, "rect") for s in range(S - 1) for x in xs]
    y2 = front_block(parts, W, D, FL * (S - 1), wall, ops, z0=GF)
    for (a, zb, w, h, sh) in ops:
        win_unit(parts, "-Y", y2, a, zb, w, h, sh, shutters="board", shutter_col=shutter_col, mark=zb < GF + FL,
                 shutter_open=(rng.choice((180, 180, 110)), 180), warm=RNG.random() < 0.3)
    for s in range(S - 1):
        parts.append(box("string", (W + 0.1, 0.2, 0.2), (0, y2 - 0.08, GF + FL * s - 0.1), M("stone"), bevel=0.02, seg=1))
        for ax in (-W / 2 + 0.6, W / 2 - 0.6):
            wall_anchor(parts, "-Y", y2, ax, GF + FL * (s + 1) - 0.4, "S")
    quoins(parts, W, D, GF, H, y2)
    cornice(parts, W, D, H - 0.05, t=0.35, proud=0.25, modillions=False)
    # the attic: a tall screen wall with a blind arcade and a sgraffito band, crest of volutes and obelisks
    A0, AH = H + 0.3, 3.2
    parts.append(box("attic", (W + 0.2, 0.6, AH), (0, y2 + 0.3, A0), wall, bevel=0.03, seg=1))
    bl = [(x, A0 + 0.9, 1.6, 1.9, "round") for x in (-3.2, -1.05, 1.05, 3.2)]
    parts.append(facade("attic_f", wall, "-Y", y2 - 0.01, -W / 2 - 0.1, W / 2 + 0.1, A0, A0 + AH, bl, depth=0.2))
    for (a, zb, w, h, sh) in bl:
        parts.append(fbox("bl_pil", "-Y", y2, a - w / 2 - 0.12, 0.04, A0 + 0.7, 0.2, 0.08, 1.7, M("plaster_white")))
        parts.append(fbox("bl_snow", "-Y", y2, a, -0.08, zb, w, 0.2, 0.03, M("snow")))
        voussoirs(parts, "-Y", y2, a, zb + h - w / 2, w, 0.12, M("plaster_white"), n=7, proud=0.05, key=0.08)
    for k in range(18):                                            # sgraffito: dark and light squares
        parts.append(fbox("sgraf", "-Y", y2, -W / 2 + 0.25 + k * (W - 0.5) / 17, 0.01, A0 + 0.25, 0.25, 0.02, 0.25, M("stone_dark" if k % 2 else "plaster_white")))
    parts.append(box("att_cop", (W + 0.5, 0.9, 0.18), (0, y2 + 0.3, A0 + AH), M("stone"), bevel=0.02, seg=1))
    parts.append(box("att_cop_snow", (W + 0.4, 0.8, 0.03), (0, y2 + 0.3, A0 + AH + 0.18), M("snow")))
    icicles(parts, (-W / 2, y2 - 0.16), (W / 2, y2 - 0.16), A0 + AH, maxlen=0.4, seed=seed + 1, gap=0.4)
    zt = A0 + AH + 0.18
    for i, x in enumerate((-W / 2 + 0.2, -W / 4, 0.0, W / 4, W / 2 - 0.2)):
        parts.append(box("ob_base", (0.5, 0.5, 0.35), (x, y2 + 0.2, zt), M("stone"), bevel=0.02, seg=1))
        parts.append(pyramid("obelisk", (0.36, 0.36, 1.6 if i % 2 == 0 else 1.1), (x, y2 + 0.2, zt + 0.35), M("stone"), apex=0.03))
        parts.append(sphere("ob_ball", 0.12, (x, y2 + 0.2, zt + (2.0 if i % 2 == 0 else 1.5)), M("gold", 0.35), seg=8, rings=5))
        snow_cap(parts, x, y2 + 0.2, zt + 0.35, 0.26, 0.05, seg=6)
    for x in (-W / 8 * 3, -W / 8, W / 8, W / 8 * 3):                 # volutes between the obelisks
        parts.append(torus("volute", 0.35, 0.09, (x, y2 + 0.2, zt + 0.35), M("stone"), rot=(math.pi / 2, 0, 0), seg=12, mseg=4))
    # butterfly roof behind: two slopes falling to a central valley gutter
    for sx in (-1, 1):
        r = roof("bfly", D - 0.6, W / 2, 1.6, (sx * W / 4, y2 + D / 2, A0), M("tile_dark"), sag=0.02, flare=0.0, along_x=False, cuts=3)
        parts.append(r)
    parts.append(box("valley_snow", (1.6, D - 0.8, 0.45), (0, y2 + D / 2, A0), M("snow"), bevel=0.2, seg=2, wonk=0.1))
    for sx in (-1, 1):
        sn = roof_snow("bfly_snow", D - 0.6, W / 2, 1.6, (sx * W / 4, y2 + D / 2, A0), sag=0.02, flare=0.0, along_x=False, cuts=3, thick=0.07, seed=seed + sx, cell=0.9)
        if sn:
            parts.append(sn)
    chimney(parts, -2.5, y2 + D - 2.0, A0 + 0.6, h=2.6)
    chimney(parts, 2.8, y2 + D / 2 + 1.0, A0 + 0.8, h=2.4)
    drainpipe(parts, W / 2 - 0.3, y2 - 0.12, H - 0.2, [(1.0, y), (GF + 1.2, y2), (GF + FL + 1.2, y2)])
    visual = join(parts, name)
    shear(visual, 0.004, -0.004)
    shear_marks(0.004, -0.004)
    export(name, visual, box("c", (W, D, A0 + AH), (0, 0, 0)))


def ten_gothic(name="ten_gothic", colour="plaster_grey", seed=22):
    """Narrow Gothic gable house (6.5 m), gable end to the street: plastered lower storeys with a pointed portal
    and paired windows, a stepped brick gable pierced by blind pointed niches, a steep roof running back."""
    reset()
    rng = random.Random(seed)
    W, D, H = 6.5, 12.0, 8.4
    wall = M(colour)
    parts = []
    ops = [(-1.2, 0.0, 1.7, 3.3, "pointed"), (1.7, 1.2, 0.8, 1.5, "rect"),
           (-1.6, 4.4, 0.75, 1.5, "rect"), (-0.7, 4.4, 0.75, 1.5, "rect"), (0.9, 4.4, 0.75, 1.5, "rect"), (1.8, 4.4, 0.75, 1.5, "rect")]
    y = front_block(parts, W, D, H, wall, ops)
    door_unit(parts, "-Y", y, -1.2, 1.7, 1.8, portal=False, fanlight=False)
    tymp = [(-2.05, 1.92), (-0.35, 1.92)] + outline(-1.2, 0.0, 1.7, 3.3, "pointed")[3:-1]
    parts.append(slab("tymp", tymp, "-Y", y, -REV + 0.01, -REV + 0.05, M("wood_dark")))
    voussoirs(parts, "-Y", y, -1.2, 3.3 - 1.7 * 0.866, 1.7, 0.24, M("stone"), shape="pointed", n=8)
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, bars=zb < 2, surround="stone", head="lintel", cross=True, mark=True,
                 shutters="board" if zb > 2 else False, shutter_col="shutter_brown", shutter_open=(rng.choice((180, 105)), 180))
    parts.append(box("plinth", (W, 0.1, 0.5), (0, y - 0.03, 0), M("stone_dark")))
    parts.append(box("string", (W + 0.1, 0.18, 0.16), (0, y - 0.06, 3.9), M("stone"), bevel=0.02, seg=1))
    for z in (3.9, 7.2):
        wall_anchor(parts, "-Y", y, -W / 2 + 0.4, z, "X")
        wall_anchor(parts, "-Y", y, W / 2 - 0.4, z, "X")
    rise = 6.0
    gable_slab(parts, "-Y", y, -W / 2, W / 2, H, rise, M("brick"), thick=0.4)
    niches = [(-1.3, H + 0.6, 0.6, 2.0), (0.0, H + 0.6, 0.7, 3.2), (1.3, H + 0.6, 0.6, 2.0), (0.0, H + 4.1, 0.45, 1.1)]
    for (a, zb, w, h) in niches:
        parts.append(slab("niche", outline(a, zb, w, h, "pointed"), "-Y", y, 0.0, 0.04, M("plaster_white")))
    parts.append(slab("gwin", outline(0.0, H + 1.2, 0.5, 1.4, "pointed"), "-Y", y, 0.04, 0.06, M("glass_warm")))
    for k in range(5):
        zz = H + rise * k / 5
        hw = W / 2 * (1 - k / 5)
        for sx in (-1, 1):
            parts.append(box("step", (0.6, 0.5, rise / 5), (sx * (hw - 0.3), y + 0.1, zz), M("brick_dark"), bevel=0.02, seg=1))
            parts.append(box("stepcap", (0.7, 0.6, 0.1), (sx * (hw - 0.3), y + 0.1, zz + rise / 5), M("stone")))
            parts.append(box("stepsnow", (0.62, 0.52, 0.035), (sx * (hw - 0.3), y + 0.1, zz + rise / 5 + 0.1), M("snow")))
            icicles(parts, (sx * (hw - 0.6), y - 0.21), (sx * hw, y - 0.21), zz + rise / 5, maxlen=0.25, seed=seed + k * 2 + sx)
    parts.append(pyramid("finial", (0.3, 0.3, 0.9), (0, y + 0.1, H + rise), M("stone"), apex=0.02))
    _roof_set(parts, D, W + 0.5, rise, (0, 0.2, H), M("tile_dark"), along_x=False, sag=0.06, flare=0.04, courses=5, seed=seed, cell=1.0,
              drifts=[(1.2, 3.0, 1.0, 0.2)])
    chimney(parts, 1.2, 3.8, H + 2.4, h=2.8)
    drainpipe(parts, W / 2 - 0.2, y - 0.12, H - 0.2, [(1.0, y), (4.5, y)])
    visual = join(parts, name)
    shear(visual, -0.005, -0.004)
    shear_marks(-0.005, -0.004)
    export(name, visual, box("c", (W, D, H + rise), (0, 0, 0)))


def ten_baroque(name="ten_baroque", colour="plaster_pink", seed=23):
    """Baroque palace front (14 m): giant pilasters, a central risalit with a column portal carrying a wrought-
    iron balcony, pedimented piano-nobile windows (triangular and segmental), a pediment with a cartouche and a
    mansard with oval dormers."""
    reset()
    rng = random.Random(seed)
    W, D, GF, FL = 14.0, 10.0, 4.4, 3.6
    H = GF + FL * 2
    wall = M(colour)
    white = M("plaster_white")
    parts = []
    xs = [-5.6, -3.2, 0.0, 3.2, 5.6]
    gops = [(0.0, 0.0, 2.2, 3.2 + 0.12 + 1.1, "round")] + [(x, 1.1, 1.2, 2.0, "rect") for x in xs if x]
    y = front_block(parts, W, D, GF, white, gops)
    door_unit(parts, "-Y", y, 0.0, 2.2, 3.2, portal=False)
    for (a, zb, w, h, sh) in gops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, bars=True, surround="stone_pale", mark=True, warm=RNG.random() < 0.5)
    rustication(parts, "-Y", y, -W / 2, W / 2, 0.5, GF - 0.25, gops, course=0.5, proud=0.04, mat=white)
    for sx in (-1, 1):                                      # portal columns and entablature carrying the balcony
        parts.append(cyl("pcol", 0.26, 3.9, (sx * 1.65, y - 0.55, 0.5), M("stone_pale"), verts=14, r2=0.22, bevel=0.01, seg=1))
        parts.append(box("pcol_b", (0.7, 0.7, 0.5), (sx * 1.65, y - 0.55, 0), M("stone"), bevel=0.02, seg=1))
        parts.append(box("pcol_c", (0.7, 0.7, 0.25), (sx * 1.65, y - 0.55, 4.4), M("stone_pale"), bevel=0.02, seg=1))
    parts.append(box("entab", (4.2, 1.1, 0.4), (0, y - 0.5, 4.6), M("stone_pale"), bevel=0.03, seg=1))
    y2 = front_block(parts, W, D, FL * 2, wall, [(x, GF + s * FL + (0.2 if (s == 0 and x == 0) else 0.7), 1.2, 2.5 if (s == 0 and x == 0) else 2.0, "rect") for s in range(2) for x in xs], z0=GF)
    for s in range(2):
        for x in xs:
            zb = GF + s * FL + (0.2 if (s == 0 and x == 0) else 0.7)
            if s == 0 and x == 0:
                win_unit(parts, "-Y", y2, x, zb, 1.2, 2.5, "rect", warm=True, sill=False, snow=False, drip=False, head=None, surround="stone_pale")
                balcony_iron(parts, "-Y", y2, 0.0, GF + 0.2, w=3.8, d=1.0, seed=seed)
                continue
            win_unit(parts, "-Y", y2, x, zb, 1.2, 2.0, "rect", warm=RNG.random() < 0.35, surround="stone_pale", mark=s == 0,
                     head="lintel" if s else None, shutters="louvre" if s else False, shutter_col="shutter_grey", shutter_open=(rng.choice((180, 180, 100)), 180))
            if s == 0:                                         # piano nobile pediments
                zt = zb + 2.0 + 0.1
                if int(x) % 2 == 0:
                    parts.append(slab("ped", [(x - 0.95, zt), (x + 0.95, zt), (x, zt + 0.55)], "-Y", y2, 0.0, 0.18, M("stone_pale")))
                else:
                    parts.append(slab("ped", [(x + 0.95 * math.cos(math.pi * k / 8), zt + 0.4 * math.sin(math.pi * k / 8)) for k in range(0, 9)], "-Y", y2, 0.0, 0.18, M("stone_pale")))
                parts.append(fbox("ped_snow", "-Y", y2, x, 0.1, zt + 0.02, 1.7, 0.2, 0.03, M("snow")))
    for x in (-W / 2 + 0.3, -1.6, 1.6, W / 2 - 0.3):           # giant pilasters through two storeys
        parts.append(box("gpil", (0.6, 0.14, FL * 2 - 0.5), (x, y2 - 0.07, GF + 0.1), white))
        parts.append(box("gpil_cap", (0.8, 0.24, 0.3), (x, y2 - 0.12, H - 0.5), M("stone_pale"), bevel=0.02, seg=1))
    parts.append(box("risalit", (3.4, 0.12, FL * 2), (0, y2 - 0.06, GF), wall))
    cornice(parts, W, D, H - 0.1, t=0.45, proud=0.35, modillions=False)
    icicles(parts, (-W / 2, y2 - 0.55), (W / 2, y2 - 0.55), H - 0.1, maxlen=0.5, seed=seed + 2, gap=0.45)
    # pediment over the risalit with a cartouche
    parts.append(slab("pediment", [(-2.2, H + 0.35), (2.2, H + 0.35), (0.0, H + 2.0)], "-Y", y2 - 0.3, 0.0, 0.5, white))
    parts.append(slab("ped_rim", [(-2.4, H + 0.3), (2.4, H + 0.3), (0.0, H + 2.15)], "-Y", y2 - 0.3, -0.05, 0.05, M("stone_pale")))
    parts.append(blob("cartouche", (0.9, 0.2, 0.8), (0, y2 - 0.35, H + 0.7), M("stone_pale"), subsurf=1))
    parts.append(sphere("cart_gold", 0.14, (0, y2 - 0.46, H + 1.1), M("gold", 0.35), seg=8, rings=5))
    top = H + 0.35
    parts.append(roof("mansard_lo", W + 0.6, D + 0.8, 2.6, (0, 0, top), M("tile"), sag=0.05, flare=-0.05, top_w=(D + 0.8) * 0.5, courses=3))
    _roof_set(parts, W + 0.6, (D + 0.8) * 0.5, 1.8, (0, 0, top + 2.6), M("tile_dark"), sag=0.08, courses=2, seed=seed, ice=False)
    lo = roof_snow("mans_snow", W + 0.6, D + 0.8, 2.6, (0, 0, top), sag=0.05, flare=-0.05, top_w=(D + 0.8) * 0.5, thick=0.06, seed=seed + 5, minz=0.5, maxz=0.95, cell=1.2, bare=0.35, slide=0.4)
    if lo:
        parts.append(lo)
    for x in (-4.4, 4.4):                                        # oeil-de-boeuf dormers
        parts.append(box("od_body", (1.1, 1.2, 1.1), (x, -D / 2 + 1.2, top + 0.7), wall))
        parts.append(cyl("od_ring", 0.42, 0.14, (x, -D / 2 + 0.58, top + 1.25), M("stone_pale"), verts=16, rot=(math.pi / 2, 0, 0), center=True))
        parts.append(cyl("od_glass", 0.32, 0.05, (x, -D / 2 + 0.62, top + 1.25), M("glass_warm"), verts=12, rot=(math.pi / 2, 0, 0), center=True))
        parts.append(sphere("od_cap", 0.65, (x, -D / 2 + 1.1, top + 1.8), M("lead"), seg=12, rings=6, zscale=0.6))
        snow_cap(parts, x, -D / 2 + 1.1, top + 2.05, 0.5, 0.12)
    for x in (-5.0, 5.0):
        chimney(parts, x, 1.2, top + 2.6, h=2.2)
    visual = join(parts, name)
    export(name, visual, box("c", (W, D, top + 4.5), (0, 0, 0)))


def ten_burgher(name="ten_burgher", colour="plaster_umber", shutter_col="shutter", seed=24):
    """Plain plastered burgher house (10 m) with a shop arcade (podcienie) of three round arches over a vaulted
    walk, board shutters, a hipped roof with a dormer, and a timber gallery on the courtyard side."""
    reset()
    rng = random.Random(seed)
    W, D, GF, FL, S = 10.0, 10.0, 4.0, 3.2, 3
    wall = M(colour)
    parts, col = [], []
    AD = 2.6                                              # arcade depth
    ops = [(x, 0.0, 2.4, 2.6 + 1.2, "round") for x in (-3.2, 0.0, 3.2)]
    parts.append(facade("arc_front", wall, "-Y", -D / 2, -W / 2, W / 2, 0.0, GF, ops, depth=AD, back=False))
    parts.append(box("arc_ceiling", (W, AD, 0.2), (0, -D / 2 + AD / 2, GF - 0.2), wall))
    for (a, zb, w, h, sh) in ops:
        voussoirs(parts, "-Y", -D / 2, a, 2.6, 2.4, 0.3, M("stone"), n=9, proud=0.06, key=0.12)
    for x in (-4.8, -1.6, 1.6, 4.8):
        col.append(box("c", (0.4, 0.6, GF), (x, -D / 2 + 0.3, 0)))
    parts.append(box("arc_floor", (W, AD, 0.06), (0, -D / 2 + AD / 2, 0), M("stone_dark")))
    shop = -D / 2 + AD
    sops = [(-3.2, 0.0, 1.5, 2.5, "rect"), (0.0, 0.8, 2.0, 1.8, "seg"), (3.2, 0.8, 2.0, 1.8, "seg")]
    parts.append(box("gf", (W, D - AD - REV, GF), (0, shop + REV + (D - AD - REV) / 2, 0), wall))
    parts.append(facade("shopf", wall, "-Y", shop, -W / 2, W / 2, 0, GF, sops))
    parts.append(fbox("sdoor", "-Y", shop, -3.2, -REV + 0.05, 0, 1.46, 0.06, 2.46, M("shutter")))
    for (a, zb, w, h, sh) in sops[1:]:
        win_unit(parts, "-Y", shop, a, zb, w, h, sh, warm=True, surround=None, mark=True)
        parts.append(fbox("counter", "-Y", shop, a, 0.3, zb - 0.1, w + 0.2, 0.6, 0.08, M("wood")))
    y = -D / 2
    H = GF + FL * (S - 1)
    uops = [(x, GF + FL * s + 0.7, 1.0, 1.6, "rect") for s in range(S - 1) for x in (-3.4, -1.1, 1.1, 3.4)]
    parts.append(box("upper", (W, D - REV, FL * (S - 1)), (0, REV / 2, GF), wall, bevel=0.04, seg=1, wonk=0.03))
    parts.append(facade("upf", wall, "-Y", y, -W / 2 - 0.01, W / 2 + 0.01, GF, H, uops))
    for (a, zb, w, h, sh) in uops:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, surround="plaster_white", head=None, shutters="board", shutter_col=shutter_col,
                 shutter_open=(rng.choice((180, 180, 100, 0)) if zb > GF + FL else 180, 180), mark=zb < GF + FL, warm=RNG.random() < 0.3)
    for s in range(S - 1):
        wall_anchor(parts, "-Y", y, -W / 2 + 0.5, GF + FL * (s + 1) - 0.4, "S")
        wall_anchor(parts, "-Y", y, W / 2 - 0.5, GF + FL * (s + 1) - 0.4, "S")
    parts.append(box("band", (W + 0.1, 0.16, 0.2), (0, y - 0.05, GF - 0.1), M("plaster_white")))
    cornice(parts, W, D, H - 0.05, t=0.3, proud=0.22, modillions=False, mat=M("plaster_white"))
    gallery_wood(parts, "+Y", D / 2, -W / 2 + 0.5, W / 2 - 0.5, GF + 0.1, d=1.3, posts=4, roof_h=2.6, seed=seed)
    _hip_set(parts, W + 0.9, D + 0.9, 4.2, (0, 0, H + 0.2), M("tile"), hip=3.2, seed=seed)
    dormer(parts, 0.0, -D / 2 + 0.9, H + 0.6, 1.3, 1.4, wall, M("tile_dark"), snow=True)
    chimney(parts, 2.0, 1.5, H + 2.2, h=2.4)
    drainpipe(parts, -W / 2 + 0.25, y - 0.12, H - 0.2, [(1.0, y), (GF + 1.0, y)])
    visual = join(parts, name)
    col.append(box("c", (W, D - AD, H + 4.2), (0, AD / 2, 0)))
    col.append(box("c", (W, AD, H - GF + 4.2), (0, -D / 2 + AD / 2, GF)))
    export(name, visual, join(col, "col"))


def ten_timber(name="ten_timber", seed=25):
    """Half-timbered gable house of the suburbs (Kleparz, Garbary): stone and plaster ground floor, a jettied
    timber-framed upper storey with plastered infill and braces, a framed street gable, shingle roof. 8 m."""
    reset()
    rng = random.Random(seed)
    W, D, GF, FL = 8.0, 10.0, 3.2, 2.9
    parts = []
    ops = [(-2.0, 0.0, 1.3, 2.3, "rect"), (1.2, 1.0, 0.9, 1.1, "rect"), (2.9, 1.0, 0.9, 1.1, "rect")]
    y = front_block(parts, W, D, GF, M("plaster_lime"), ops)
    parts.append(fbox("door", "-Y", y, -2.0, -REV + 0.05, 0, 1.26, 0.06, 2.26, M("shutter_brown")))
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, surround=None, head=None, shutters="board", shutter_col="shutter_blue", mark=True, shutter_open=(rng.choice((180, 110)), 180))
    parts.append(box("plinth", (W, 0.12, 0.6), (0, y - 0.04, 0), M("stone_dark")))
    jet = 0.4
    y2 = y - jet
    uops = [(x, GF + 0.8, 0.8, 1.2, "rect") for x in (-2.6, -0.9, 0.9, 2.6)]
    parts.append(box("upper", (W + 0.2, D + jet - REV, FL), (0, -jet / 2 + REV / 2, GF), M("plaster_lime")))
    parts.append(facade("upf", M("plaster_lime"), "-Y", y2, -W / 2 - 0.1, W / 2 + 0.1, GF, GF + FL, uops))
    for (a, zb, w, h, sh) in uops:
        win_unit(parts, "-Y", y2, a, zb, w, h, sh, surround=None, head=None, sill=True, mark=True, warm=RNG.random() < 0.4)
    timber_frame(parts, "-Y", y2, -W / 2 - 0.1, W / 2 + 0.1, GF, GF + FL, posts=8, braces=False)
    for k in range(9):
        parts.append(box("joist", (0.16, jet + 0.2, 0.18), (-W / 2 + k * W / 8, y - jet / 2, GF - 0.18), M("timber")))
    rise = 4.6
    gable_slab(parts, "-Y", y2, -W / 2 - 0.1, W / 2 + 0.1, GF + FL, rise, M("plaster_lime"), thick=0.3)
    zg = GF + FL
    for a in (-2.0, 0.0, 2.0):
        zt = zg + rise * (1 - abs(a) / (W / 2 + 0.1))
        parts.append(fbox("gpost", "-Y", y2, a, 0.05, zg, 0.18, 0.1, zt - zg - 0.1, M("timber")))
    parts.append(fbox("grail", "-Y", y2, 0, 0.05, zg + 1.5, W * 0.62, 0.1, 0.18, M("timber")))
    for sx in (-1, 1):
        pts = [(sx * (W / 2 + 0.1), zg), (sx * (W / 2 - 0.1), zg), (sx * 0.1, zg + rise), (sx * 0.3, zg + rise)]
        parts.append(slab("gbarge", pts if sx < 0 else list(reversed(pts)), "-Y", y2, 0.0, 0.12, M("timber")))
    win_unit(parts, "-Y", y2, 0.0, zg + 1.8, 0.7, 0.9, "rect", surround=None, head=None, sill=False)
    _roof_set(parts, D + jet + 0.8, W + 0.8, rise, (0, -jet / 2, zg), M("shingle"), along_x=False, sag=0.08, flare=0.05, courses=0, seed=seed, cell=1.0)
    chimney(parts, 1.6, 2.0, zg + 1.8, h=2.2)
    visual = join(parts, name)
    shear(visual, 0.008, -0.004)
    shear_marks(0.008, -0.004)
    export(name, visual, box("c", (W, D, zg + rise), (0, 0, 0)))


def ten_wooden(name="ten_wooden", seed=26):
    """Wooden suburban house: limewashed-log walls on a stone sill, carved window frames with blue shutters, a
    porch (ganek) on turned posts, a steep shingle roof with a gablet, a stack in the middle. 9 m."""
    reset()
    rng = random.Random(seed)
    W, D, H = 9.0, 7.0, 3.0
    parts = []
    ops = [(-1.8, 0.25, 1.0, 2.0, "rect"), (0.6, 1.0, 0.8, 1.0, "rect"), (2.6, 1.0, 0.8, 1.0, "rect"), (-3.6, 1.0, 0.8, 1.0, "rect")]
    parts.append(box("sill", (W + 0.3, D + 0.3, 0.3), (0, 0, 0), M("stone_dark"), bevel=0.03, seg=1, wonk=0.04))
    y = front_block(parts, W, D, H - 0.3, M("log"), ops, z0=0.3)
    parts.append(fbox("door", "-Y", y, -1.8, -REV + 0.05, 0.3, 0.96, 0.06, 1.95, M("shutter_blue")))
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb + 0.3, w, h, sh, surround=None, head=None, sill=False, mark=True, warm=RNG.random() < 0.5,
                 shutters="board", shutter_col="shutter_blue", shutter_open=(rng.choice((180, 120)), 180))
        parts.append(fbox("wframe", "-Y", y, a, 0.03, zb + 0.22, w + 0.24, 0.05, h + 0.16, M("plaster_lime")))
        parts.append(slab("wcrown", [(a - w / 2 - 0.16, zb + 0.3 + h + 0.08), (a + w / 2 + 0.16, zb + 0.3 + h + 0.08), (a, zb + 0.3 + h + 0.4)], "-Y", y, 0.0, 0.06, M("plaster_lime")))
    log_corners(parts, W, D, H)
    # porch
    for x in (-2.8, -0.8):
        parts.append(cyl("ppost", 0.1, 2.6, (x, y - 1.5, 0.3), M("wood"), verts=8, bevel=0.01, seg=1))
    parts.append(box("pfloor", (2.6, 1.7, 0.3), (-1.8, y - 0.85, 0), M("wood_dark")))
    parts.append(box("prail", (2.4, 0.08, 0.08), (-1.8, y - 1.5, 1.2), M("wood")))
    sn = []
    _roof_set(parts, 2.3, 2.8, 1.2, (-1.8, y - 1.2, 2.9), M("shingle"), along_x=False, courses=0, sag=0.02, flare=0.05, seed=seed + 7, cell=0.6, sides=(-1, 1))
    _hip_set(parts, W + 1.4, D + 1.6, 4.4, (0, 0, H), M("shingle"), hip=1.4, seed=seed)
    parts.append(box("stack", (0.8, 0.8, 1.4), (0.3, 0.4, H + 3.4), M("plaster_lime"), bevel=0.03, seg=1, wonk=0.04))
    parts.append(box("stack_cap", (0.94, 0.94, 0.05), (0.3, 0.4, H + 4.8), M("snow")))
    mark("Chimney", (0.3, 0.4, H + 4.9))
    parts.append(box("drift", (W + 0.8, 0.9, 0.22), (1.2, y - 0.6, 0), M("snow"), bevel=0.2, seg=2, wonk=0.12))
    visual = join(parts, name)
    shear(visual, 0.006, -0.005)
    shear_marks(0.006, -0.005)
    export(name, visual, box("c", (W + 0.3, D + 0.3, H + 4.4), (0, 0, 0)))


# ------------------------------------------------------------------ water: fountain, well, pump, trough, street gutter
def fountain():
    """Public fountain (studnia miejska): an octagonal stone basin with a moulded rim, a baluster pillar with a
    small bowl and a spout figure (a lion's mask); the water is frozen over, icicles hang from bowl and spout."""
    reset()
    parts = []
    R = 2.4
    st, sp = M("stone"), M("stone_pale")
    parts.append(cyl("step", R + 0.6, 0.2, (0, 0, 0), M("stone_dark"), verts=8, bevel=0.03, seg=1))
    for k in range(8):
        a = math.tau * (k + 0.5) / 8
        parts.append(cbox("wall", (2 * R * math.tan(math.pi / 8) + 0.02, 0.32, 0.75), (R * math.cos(math.pi / 8) * math.cos(a), R * math.cos(math.pi / 8) * math.sin(a), 0.575), st, rot=(0, 0, a + math.pi / 2), bevel=0.02, seg=1))
        parts.append(cbox("rim", (2 * (R + 0.08) * math.tan(math.pi / 8) + 0.04, 0.46, 0.14), ((R + 0.02) * math.cos(math.pi / 8) * math.cos(a), (R + 0.02) * math.cos(math.pi / 8) * math.sin(a), 1.0), sp, rot=(0, 0, a + math.pi / 2), bevel=0.03, seg=1))
        parts.append(cbox("rim_snow", (2 * (R + 0.08) * math.tan(math.pi / 8) - 0.1, 0.36, 0.035), ((R + 0.02) * math.cos(math.pi / 8) * math.cos(a), (R + 0.02) * math.cos(math.pi / 8) * math.sin(a), 1.085), M("snow"), rot=(0, 0, a + math.pi / 2)))
        c = Vector((math.cos(math.tau * k / 8), math.sin(math.tau * k / 8), 0)) * (R + 0.16)
        parts.append(box("post", (0.3, 0.3, 1.0), (c.x, c.y, 0.2), sp))
        parts.append(sphere("post_ball", 0.16, (c.x, c.y, 1.36), sp, seg=8, rings=5))
        snow_cap(parts, c.x, c.y, 1.42, 0.12, 0.05, seg=6)
    parts.append(cyl("ice", R - 0.12, 0.05, (0, 0, 0.72), M("ice", 0.05), verts=16))
    parts.append(cyl("ice_snow", R * 0.6, 0.03, (0.5, 0.3, 0.77), M("snow"), verts=12))
    parts.append(cyl("pillar_base", 0.5, 0.5, (0, 0, 0.7), sp, verts=12, r2=0.4, bevel=0.02, seg=1))
    parts.append(cyl("pillar", 0.28, 1.4, (0, 0, 1.2), sp, verts=12, r2=0.22, bevel=0.02, seg=1))
    parts.append(sphere("baluster", 0.36, (0, 0, 1.9), sp, seg=12, rings=8, zscale=0.8))
    parts.append(cyl("bowl", 0.35, 0.35, (0, 0, 2.4), sp, verts=16, r2=1.05, bevel=0.02, seg=1))
    parts.append(cyl("bowl_ice", 0.98, 0.04, (0, 0, 2.72), M("ice", 0.05), verts=16))
    parts.append(cyl("bowl_snow", 0.9, 0.04, (0, 0, 2.74), M("snow"), verts=16))
    icicles(parts, (-1.0, -0.35), (1.0, -0.35), 2.72, maxlen=0.6, seed=1, density=4)
    icicles(parts, (-1.0, 0.35), (1.0, 0.35), 2.72, maxlen=0.6, seed=2, density=4)
    parts.append(cyl("fig_ped", 0.22, 0.5, (0, 0, 2.75), sp, verts=10, bevel=0.01, seg=1))
    parts.append(blob("fig_body", (0.45, 0.4, 0.9), (0, 0, 3.25), M("bronze", 0.4), subsurf=2))
    parts.append(sphere("fig_head", 0.17, (0, 0, 4.25), M("bronze", 0.4), seg=10, rings=7))
    snow_cap(parts, 0, 0, 4.36, 0.14, 0.06, seg=6)
    for k in range(4):                                        # lion masks with a spout each, frozen mid-flow
        a = math.tau * k / 4
        c = Vector((math.cos(a), math.sin(a), 0))
        parts.append(sphere("mask", 0.16, tuple(c * 0.3 + Vector((0, 0, 1.7))), M("bronze", 0.4), seg=10, rings=6))
        parts.append(cyl("spout", 0.035, 0.35, tuple(c * 0.5 + Vector((0, 0, 1.62))), M("bronze", 0.4), verts=6, rot=(0, math.pi / 2, a), center=True))
        bm = bmesh.new()
        _tube(bm, c * 0.66 + Vector((0, 0, 1.6)), c * 0.9 + Vector((0, 0, 0.78)), 0.06, 0.03, n=6)
        parts.append(_mesh_obj("frozen_jet", bm, M("ice", 0.05)))
    export("fountain", join(parts, "fountain"), cyl("c", R + 0.3, 1.1, (0, 0, 0), None, verts=8))


def well():
    """Town well: an octagonal dressed-stone curb with snow on its lip, two oak posts carrying a windlass with a
    crank and a coil of rope, a bucket on the curb and another hanging, and a shingle roof under snow with
    icicles along both eaves."""
    reset()
    stone = M("stone_dark")
    parts = []
    for k in range(8):
        a = math.tau * k / 8
        parts.append(cbox("stone", (0.95, 0.55, 0.5), (1.15 * math.cos(a), 1.15 * math.sin(a), 0.25), stone, rot=(0, 0, a + math.pi / 2), bevel=0.04, seg=1, wonk=0.03))
        parts.append(cbox("stone", (0.95, 0.55, 0.5), (1.15 * math.cos(a + math.pi / 8), 1.15 * math.sin(a + math.pi / 8), 0.75), stone, rot=(0, 0, a + math.pi / 8 + math.pi / 2), bevel=0.04, seg=1, wonk=0.03))
        parts.append(cbox("lip", (0.9, 0.62, 0.1), (1.15 * math.cos(a), 1.15 * math.sin(a), 1.05), M("stone"), rot=(0, 0, a + math.pi / 2), bevel=0.02, seg=1))
        parts.append(cbox("lip_snow", (0.8, 0.5, 0.03), (1.15 * math.cos(a), 1.15 * math.sin(a), 1.115), M("snow"), rot=(0, 0, a + math.pi / 2)))
    parts.append(cyl("hole", 0.92, 0.05, (0, 0, 0.9), M("void"), verts=16, bevel=0))
    for sx in (-1, 1):
        parts.append(cyl("post", 0.1, 2.5, (sx * 1.15, 0, 0.95), M("timber"), verts=8, bevel=0.01, seg=1))
        parts.append(cbox("brace", (0.07, 0.07, 0.9), (sx * 0.95, 0, 3.05), M("timber"), rot=(0, sx * 0.6, 0)))
    parts.append(cyl("beam", 0.09, 2.7, (0, 0, 3.45), M("timber"), verts=8, rot=(0, math.pi / 2, 0), center=True, bevel=0.01, seg=1))
    parts.append(cyl("windlass", 0.15, 2.1, (0, 0, 2.7), M("wood"), verts=10, rot=(0, math.pi / 2, 0), center=True, bevel=0.01, seg=1))
    parts.append(cyl("rope_coil", 0.19, 0.7, (0, 0, 2.7), M("sacking"), verts=10, rot=(0, math.pi / 2, 0), center=True))
    parts.append(cyl("crank_arm", 0.03, 0.5, (1.3, 0, 2.5), M("iron"), verts=6, center=True))
    parts.append(cyl("crank_axle", 0.03, 0.25, (1.2, 0, 2.7), M("iron"), verts=6, rot=(0, math.pi / 2, 0), center=True))
    parts.append(cyl("crank_grip", 0.04, 0.3, (1.45, 0, 2.28), M("wood_dark"), verts=6, rot=(0, math.pi / 2, 0), center=True))
    parts.append(cyl("rope", 0.015, 1.1, (0, 0, 1.55), M("sacking"), verts=5))
    parts.append(cyl("bucket", 0.17, 0.32, (0, 0, 1.25), M("wood"), verts=10, r2=0.15, bevel=0.01, seg=1))
    parts.append(cyl("bucket_hoop", 0.18, 0.04, (0, 0, 1.45), M("iron"), verts=10))
    parts.append(cyl("bucket2", 0.17, 0.32, (0.75, -0.95, 1.1), M("wood"), verts=10, r2=0.15, bevel=0.01, seg=1))
    parts.append(cyl("bucket2_ice", 0.14, 0.02, (0.75, -0.95, 1.38), M("ice", 0.05), verts=10))
    _roof_set(parts, 3.3, 2.0, 1.0, (0, 0, 3.55), M("shingle"), sag=0.04, flare=0.1, courses=0, seed=7, cell=0.5, thick=0.06)
    parts.append(box("drift", (3.4, 3.4, 0.12), (0.3, 0.2, 0), M("snow"), bevel=0.25, seg=2, wonk=0.15))
    export("well", join(parts, "well"), cyl("c", 1.45, 1.1, (0, 0, 0), None, verts=8))


def water_pump():
    """Wooden pump-post (drewniana pompa) c. 1800: a squared oak trunk bound with iron, a pivoted lever handle, a
    lead spout over a hollowed stone trough, frozen, with icicles from the spout; a flag-stone apron."""
    reset()
    parts = []
    parts.append(box("apron", (1.6, 1.8, 0.12), (0, -0.3, 0), M("stone_dark"), bevel=0.03, seg=1, wonk=0.04))
    parts.append(box("trunk", (0.34, 0.34, 2.1), (0, 0.2, 0.12), M("timber"), bevel=0.03, seg=1, wonk=0.02))
    for z in (0.5, 1.2, 1.9):
        parts.append(box("band", (0.38, 0.38, 0.06), (0, 0.2, z), M("iron")))
    parts.append(pyramid("cap", (0.5, 0.5, 0.3), (0, 0.2, 2.22), M("wood_dark"), apex=0.03))
    parts.append(pyramid("cap_snow", (0.36, 0.36, 0.2), (0, 0.2, 2.34), M("snow"), apex=0.03))
    parts.append(box("pivot", (0.06, 0.2, 0.25), (0.2, 0.2, 1.75), M("iron")))
    lever = box("lever", (0.07, 1.3, 0.07), (0.26, -0.35, 1.85), M("wood_dark"))
    edit_verts(lever, lambda co: setattr(co, "z", co.z - (0.2 - co.y) * 0.35))
    parts.append(lever)
    parts.append(cyl("spout", 0.05, 0.45, (0, -0.1, 1.05), M("lead"), verts=8, rot=(math.radians(70), 0, 0), center=True))
    parts.append(box("trough", (0.9, 0.6, 0.45), (0, -0.55, 0.12), M("stone"), bevel=0.04, seg=1))
    parts.append(box("trough_ice", (0.76, 0.46, 0.02), (0, -0.55, 0.52), M("ice", 0.05)))
    icicles(parts, (-0.03, -0.27), (0.03, -0.27), 1.0, maxlen=0.5, seed=3, density=40, gap=0.2, r=0.03)
    bm = bmesh.new()
    _tube(bm, (0, -0.3, 0.98), (0.02, -0.4, 0.55), 0.05, 0.08, n=6)
    parts.append(_mesh_obj("ice_column", bm, M("ice", 0.05)))
    parts.append(box("drift", (1.4, 1.0, 0.12), (0.2, 0.3, 0), M("snow"), bevel=0.2, seg=2, wonk=0.1))
    export("water_pump", join(parts, "water_pump"), box("c", (0.5, 0.9, 1.3), (0, -0.2, 0)))


def horse_trough():
    """Stone horse trough, 2.4 m, iced over, snow on its rim and a slop of frozen spill on the ground."""
    reset()
    parts = [box("trough", (2.4, 0.8, 0.7), (0, 0, 0), M("stone"), bevel=0.05, seg=1, wonk=0.03),
             box("ice", (2.2, 0.6, 0.02), (0, 0, 0.62), M("ice", 0.05)),
             box("snow_l", (2.3, 0.08, 0.03), (0, -0.36, 0.7), M("snow")), box("snow_r", (2.3, 0.08, 0.03), (0, 0.36, 0.7), M("snow"))]
    for x in (-1.0, 1.0):
        parts.append(box("foot", (0.3, 0.9, 0.12), (x, 0, 0), M("stone_dark")))
    icicles(parts, (-1.1, -0.41), (1.1, -0.41), 0.7, maxlen=0.18, seed=4, density=3)
    parts.append(box("spill", (1.6, 1.2, 0.02), (0.2, -0.6, 0), M("ice", 0.05), wonk=0.2))
    export("horse_trough", join(parts, "horse_trough"), box("c", (2.4, 0.8, 0.7), (0, 0, 0)))


# ------------------------------------------------------------------ industry
def windmill():
    """Post mill (kozlak): the whole timber body turns on a great post braced by quarter-bars on crossed sills and
    stone piers; a ladder and tail pole at the back, four bare lattice sails (canvas furled for winter) on a
    tilted windshaft, boarded walls, a curved roof under snow with icicles."""
    reset()
    parts, col = [], []
    tm, wd, dk = M("timber"), M("wood"), M("wood_dark")
    for a in (0.0, math.pi / 2):
        parts.append(cbox("sill", (7.0, 0.4, 0.4), (0, 0, 0.9), tm, rot=(0, 0, a + math.pi / 4)))
    for k in range(4):
        a = math.tau * k / 4 + math.pi / 4
        c = Vector((math.cos(a), math.sin(a), 0)) * 3.2
        parts.append(box("pier", (0.8, 0.8, 0.7), (c.x, c.y, 0), M("stone"), bevel=0.04, seg=1, wonk=0.04))
        parts.append(box("pier_snow", (0.7, 0.7, 0.04), (c.x, c.y, 1.1), M("snow")))
        bm = bmesh.new()
        _tube(bm, c * 0.95 + Vector((0, 0, 1.1)), Vector((0, 0, 4.0)), 0.16, 0.14, n=6)
        parts.append(_mesh_obj("quarter", bm, tm))
    parts.append(cyl("post", 0.32, 4.4, (0, 0, 0.7), tm, verts=10))
    col.append(box("c", (1.2, 1.2, 4.5), (0, 0, 0)))
    for k in range(4):
        a = math.tau * k / 4 + math.pi / 4
        c = Vector((math.cos(a), math.sin(a), 0)) * 3.2
        col.append(box("c", (0.8, 0.8, 1.2), (c.x, c.y, 0)))
    # the body (buck)
    BW, BD, BH, z0 = 4.2, 5.6, 5.4, 4.6
    parts.append(box("crown", (1.2, BD, 0.5), (0, 0, z0 - 0.5), tm))
    parts.append(box("buck", (BW, BD, BH), (0, 0, z0), wd, bevel=0.04, seg=1, wonk=0.05))
    for k in range(9):
        x = -BW / 2 + k * BW / 8
        parts.append(box("batten", (0.06, BD + 0.04, BH), (x, 0, z0), dk))
    for k in range(4):
        parts.append(box("batten_s", (BW + 0.04, 0.04, 0.12), (0, -BD / 2 - 0.01, z0 + 0.6 + k * 1.4), dk))
    parts.append(box("door", (1.0, 0.06, 1.8), (0, BD / 2 + 0.02, z0 + 0.2), dk))
    parts.append(box("win", (0.6, 0.06, 0.6), (1.2, -BD / 2 - 0.02, z0 + 3.2), M("glass_warm")))
    rf = roof("roof", BD + 0.6, BW + 0.8, 1.8, (0, 0, z0 + BH), M("shingle"), along_x=False, sag=0.0, flare=-0.35, cuts=4)
    parts.append(rf)
    sn = roof_snow("roof_snow", BD + 0.6, BW + 0.8, 1.8, (0, 0, z0 + BH), along_x=False, sag=0.0, flare=-0.35, cuts=4, thick=0.07, cell=0.7, seed=9)
    if sn:
        parts.append(sn)
    eave_icicles(parts, BD, BW + 0.8, z0 + BH - 0.02, (0, 0), along_x=False, seed=10, maxlen=0.5)
    # ladder and tail pole down the back
    for sx in (-0.45, 0.45):
        parts.append(cbox("stringer", (0.12, 0.12, 6.4), (sx, BD / 2 + 1.9, z0 / 2 + 0.3), tm, rot=(math.radians(-38), 0, 0)))
    for k in range(12):
        t = (k + 0.5) / 12
        parts.append(box("rung", (0.9, 0.24, 0.05), (0, BD / 2 + 3.9 - t * 4.0, 0.5 + t * (z0 - 0.4)), wd))
    parts.append(cbox("tail", (0.2, 0.2, 7.8), (0, BD / 2 + 2.6, z0 / 2 + 0.6), tm, rot=(math.radians(-45), 0, 0)))
    col.append(box("c", (1.2, 4.0, 1.2), (0, BD / 2 + 3.4, 0)))
    # sails
    hub = Vector((0, -BD / 2 - 0.6, z0 + BH - 1.2))
    tilt = math.radians(10)
    ax = Vector((0, -math.cos(tilt), math.sin(tilt)))
    parts.append(cyl("shaft", 0.3, 1.8, tuple(hub + Vector((0, 0.9, -0.15))), tm, verts=10, rot=(math.pi / 2 + tilt, 0, 0), center=True))
    parts.append(sphere("poll", 0.45, tuple(hub), dk, seg=10, rings=6))
    u0 = Vector((1, 0, 0))
    v0 = ax.cross(u0).normalized()
    bm = bmesh.new()
    for k in range(4):
        a = math.tau * k / 4 + 0.35
        d = u0 * math.cos(a) + v0 * math.sin(a)
        p = d.cross(ax).normalized()
        _tube(bm, hub, hub + d * 8.5, 0.14, 0.09, n=4)
        for side in (0.35, 1.7):
            _tube(bm, hub + d * 1.8 + p * side, hub + d * 8.4 + p * side, 0.04, 0.04, n=4)
        for j in range(12):
            t = 1.8 + (8.4 - 1.8) * j / 11
            _tube(bm, hub + d * t, hub + d * t + p * 1.7, 0.03, 0.03, n=4)
        _tube(bm, hub + d * 2.0 + p * 1.0, hub + d * 8.0 + p * 1.0, 0.12, 0.1, n=6)   # furled canvas along the sail
    parts.append(_mesh_obj("sails", bm, wd))
    visual = join(parts, "windmill")
    export("windmill", visual, join(col, "col"))


def watermill():
    """Town water mill on the Mlynowka: a brick ground floor with a timber upper storey and a hipped tile roof;
    a stone-walled mill race raised along the +X side with a sluice, dark water and ice floes, and an
    undershot wheel dipping into it, icicles hanging off its paddles."""
    reset()
    parts, col = [], []
    W, D, GF, H = 9.0, 8.0, 3.2, 6.0
    ops = [(-1.8, 0.0, 1.4, 2.5, "rect"), (1.5, 1.2, 0.9, 1.1, "seg")]
    y = front_block(parts, W, D, GF, M("brick"), ops)
    parts.append(fbox("door", "-Y", y, -1.8, -REV + 0.05, 0, 1.36, 0.06, 2.46, M("wood_dark")))
    win_unit(parts, "-Y", y, 1.5, 1.2, 0.9, 1.1, "seg", warm=True, surround=None, mark=True)
    uops = [(x, GF + 0.8, 0.8, 1.0, "rect") for x in (-2.6, 0.0, 2.6)]
    y2 = front_block(parts, W, D, H - GF, M("plaster_lime"), uops, z0=GF)
    for (a, zb, w, h, sh) in uops:
        win_unit(parts, "-Y", y2, a, zb, w, h, sh, surround=None, head=None, mark=True, warm=RNG.random() < 0.4)
    timber_frame(parts, "-Y", y2, -W / 2, W / 2, GF, H, posts=6, braces=True)
    col.append(box("c", (W, D, H + 3.5), (0, 0, 0)))
    _hip_set(parts, W + 1.2, D + 1.2, 3.6, (0, 0, H), M("tile"), hip=2.0, seed=12)
    chimney(parts, -2.2, 1.4, H + 1.6, h=2.2)
    # raised race along +X
    rx = W / 2 + 1.6
    for dx in (-1.1, 1.1):
        parts.append(box("race_wall", (0.5, 22.0, 1.3), (rx + dx, 0, 0), M("stone"), bevel=0.03, seg=1, wonk=0.04))
        parts.append(box("race_snow", (0.45, 22.0, 0.04), (rx + dx, 0, 1.3), M("snow"), wonk=0.03))
        col.append(box("c", (0.5, 22.0, 1.3), (rx + dx, 0, 0)))
    parts.append(box("race_bed", (1.8, 22.0, 0.3), (rx, 0, 0), M("stone_dark")))
    parts.append(box("water", (1.72, 22.0, 0.02), (rx, 0, 0.95), M("water", 0.04)))
    rng = random.Random(13)
    for k in range(6):
        parts.append(box("floe", (rng.uniform(0.4, 1.0), rng.uniform(0.5, 1.4), 0.04), (rx + rng.uniform(-0.4, 0.4), -9 + k * 3.4 + rng.uniform(-0.6, 0.6), 0.96), M("ice", 0.05), wonk=0.1))
    parts.append(box("sluice", (2.8, 0.25, 0.3), (rx, -6.5, 2.2), M("timber")))
    for dx in (-1.25, 1.25):
        parts.append(box("sl_post", (0.22, 0.22, 2.5), (rx + dx, -6.5, 0), M("timber")))
    parts.append(box("sl_gate", (1.7, 0.1, 1.1), (rx, -6.5, 1.0), M("wood_dark")))
    parts.append(box("sl_snow", (2.7, 0.2, 0.04), (rx, -6.5, 2.5), M("snow")))
    R = 2.4
    wc = Vector((rx, 0.0, 0.95 + R - 0.5))
    bm = bmesh.new()
    for dx in (-0.55, 0.55):
        for k in range(24):
            a0, a1 = math.tau * k / 24, math.tau * (k + 1) / 24
            _tube(bm, wc + Vector((dx, R * math.cos(a0), R * math.sin(a0))), wc + Vector((dx, R * math.cos(a1), R * math.sin(a1))), 0.08, 0.08, n=4)
        for k in range(8):
            a = math.tau * k / 8
            _tube(bm, wc + Vector((dx, 0, 0)), wc + Vector((dx, R * math.cos(a), R * math.sin(a))), 0.06, 0.06, n=4)
    parts.append(_mesh_obj("wheel", bm, M("wood_dark")))
    for k in range(16):
        a = math.tau * k / 16
        parts.append(cbox("paddle", (1.3, 0.06, 0.55), (wc.x, wc.y + (R - 0.2) * math.cos(a), wc.z + (R - 0.2) * math.sin(a)), M("wood"), rot=(a, 0, 0)))
        if math.sin(a) > 0.2:
            icicles(parts, (wc.x - 0.5, wc.y + (R - 0.2) * math.cos(a)), (wc.x + 0.5, wc.y + (R - 0.2) * math.cos(a)), wc.z + (R - 0.45) * math.sin(a), maxlen=0.3, seed=20 + k, density=4)
    parts.append(cyl("axle", 0.18, 2.6, (W / 2 + 0.3, 0.0, wc.z), M("timber"), verts=10, rot=(0, math.pi / 2, 0), center=True))
    visual = join(parts, "watermill")
    export("watermill", visual, join(col, "col"))


def _glow(key="ember", strength=6.0):
    return M(key, 0.9, emit=(1.0, 0.36, 0.08), emit_strength=strength)


def bell_foundry():
    """Bell foundry (ludwisarnia): a brick casting hall with a wide arched front, a tall tapering furnace stack,
    the furnace mouth glowing orange, a clay bell mould in the casting pit and a finished bell hung on a trestle
    in the yard."""
    reset()
    parts, col = [], []
    W, D, H = 12.0, 9.0, 5.0
    ops = [(-1.0, 0.0, 4.4, 3.4 + 2.2, "round"), (4.2, 1.6, 1.0, 1.6, "seg")]
    y = front_block(parts, W, D, H, M("brick"), ops)
    parts.append(slab("hall_dark", outline(-1.0, 0.0, 4.4, 5.6, "round"), "-Y", y, -D + 0.6, -D + 0.62, M("void")))
    win_unit(parts, "-Y", y, 4.2, 1.6, 1.0, 1.6, "seg", warm=True, surround=None, mark=True)
    voussoirs(parts, "-Y", y, -1.0, 3.4, 4.4, 0.4, M("stone"), n=11, proud=0.1, key=0.2)
    rustication(parts, "-Y", y, -W / 2, W / 2, 0.0, 1.0, ops, course=0.5, mat=M("stone_dark"))
    col.append(box("c", (2.8, D, H), (-4.6, 0, 0)))
    col.append(box("c", (4.8, D, H), (3.6, 0, 0)))
    col.append(box("c", (4.4, D, H - 5.6 + 0.01), (-1.0, 0, 5.6)))
    col.append(box("c", (W, 1.0, H), (0, D / 2 - 0.5, 0)))
    _roof_set(parts, W + 0.8, D + 1.0, 3.6, (0, 0, H), M("tile_dark"), courses=4, seed=30, drifts=[(3.8, 1.0, 1.6, 0.25)])
    # furnace stack at the back corner and the glowing furnace inside the arch
    parts.append(taper_box("stack", (2.2, 2.2, 15.0), (3.8, 2.4, 0), M("brick"), top=0.55))
    parts.append(box("stack_band", (1.5, 1.5, 0.25), (3.8, 2.4, 13.0), M("brick_dark")))
    parts.append(box("stack_cap", (1.45, 1.45, 0.2), (3.8, 2.4, 15.0), M("stone_dark")))
    mark("Chimney", (3.8, 2.4, 15.3))
    col.append(box("c", (2.2, 2.2, 15.0), (3.8, 2.4, 0)))
    parts.append(box("furnace", (3.2, 2.4, 2.4), (-1.0, D / 2 - 2.0, 0), M("brick_dark"), bevel=0.05, seg=1))
    parts.append(arch("furnace_mouth", 1.0, 1.1, 0.1, (-1.0, D / 2 - 3.21, 0.35), _glow(strength=9.0), bevel=0))
    mark("Furnace", (-1.0, D / 2 - 3.4, 0.9))
    parts.append(blob("mould", (2.2, 2.2, 2.2), (-1.0, -0.6, -0.4), M("terracotta"), subsurf=2))
    parts.append(cyl("pit_rim", 1.6, 0.15, (-1.0, -0.6, 0), M("stone_dark"), verts=16))
    # finished bell on a trestle outside
    bx = -4.3
    for sx in (-1, 1):
        parts.append(cbox("tr_leg", (0.2, 0.2, 3.4), (bx + sx * 1.2, y - 2.0, 1.6), M("timber"), rot=(0, sx * 0.2, 0)))
    parts.append(box("tr_beam", (3.2, 0.3, 0.3), (bx, y - 2.0, 3.2), M("timber")))
    parts.append(box("tr_snow", (3.1, 0.26, 0.04), (bx, y - 2.0, 3.5), M("snow")))
    parts.append(cyl("bell", 0.55, 1.1, (bx, y - 2.0, 1.7), M("bronze", 0.35), verts=20, r2=0.35))
    parts.append(sphere("bell_top", 0.36, (bx, y - 2.0, 2.8), M("bronze", 0.35), seg=16, rings=8, zscale=0.5))
    parts.append(cyl("bell_lip", 0.62, 0.12, (bx, y - 2.0, 1.62), M("bronze", 0.35), verts=20))
    col.append(box("c", (2.8, 0.6, 3.4), (bx, y - 2.0, 0)))
    parts.append(box("woodpile", (2.6, 1.0, 1.2), (5.0, y - 0.8, 0), M("log"), bevel=0.1, seg=1, wonk=0.1))
    parts.append(box("wp_snow", (2.5, 0.9, 0.06), (5.0, y - 0.8, 1.2), M("snow"), wonk=0.05))
    visual = join(parts, "bell_foundry")
    export("bell_foundry", visual, join(col, "col"))


def forge():
    """Blacksmith's forge (kuznia): an open-fronted timber shed against a brick back wall; a raised brick hearth
    with glowing coals under a hood and chimney, leather bellows, the anvil on its stump, a quench tub, a rack of
    tongs and hammers, horseshoes on the post and a grindstone outside."""
    reset()
    parts, col = [], []
    W, D, H = 7.0, 5.0, 3.0
    parts.append(box("back", (W, 0.5, H), (0, D / 2 - 0.25, 0), M("brick"), bevel=0.02, seg=1, wonk=0.03))
    col.append(box("c", (W, 0.5, H), (0, D / 2 - 0.25, 0)))
    for sx in (-1, 1):
        parts.append(box("side", (0.2, D, H), (sx * (W / 2 - 0.1), 0, 0), M("timber"), wonk=0.03))
        for k in range(6):
            parts.append(box("board", (0.04, 0.05, H), (sx * (W / 2 + 0.01), -D / 2 + 0.4 + k * 0.84, 0), M("wood_dark")))
        col.append(box("c", (0.2, D, H), (sx * (W / 2 - 0.1), 0, 0)))
        parts.append(box("fpost", (0.25, 0.25, H), (sx * (W / 2 - 0.2), -D / 2 + 0.15, 0), M("timber")))
    parts.append(box("head", (W, 0.3, 0.3), (0, -D / 2 + 0.15, H - 0.3), M("timber")))
    parts.append(box("floor", (W, D, 0.04), (0, 0, 0), M("soot", 0.95)))
    _roof_set(parts, W + 0.8, D + 1.2, 2.2, (0, 0, H), M("shingle"), courses=0, seed=40, drifts=[(1.5, 0.8, 1.2, 0.2)], cell=0.8)
    # hearth, hood and chimney
    parts.append(box("hearth", (2.0, 1.4, 0.8), (1.5, D / 2 - 1.2, 0), M("brick_dark"), bevel=0.03, seg=1))
    parts.append(box("hearth_top", (2.1, 1.5, 0.08), (1.5, D / 2 - 1.2, 0.8), M("stone_dark")))
    parts.append(blob("coals", (0.9, 0.7, 0.2), (1.5, D / 2 - 1.2, 0.84), _glow(strength=8.0)))
    parts.append(blob("flame", (0.4, 0.3, 0.35), (1.5, D / 2 - 1.2, 0.9), M("flame", 0.9, emit=(1.0, 0.55, 0.12), emit_strength=10.0)))
    mark("Furnace", (1.5, D / 2 - 1.2, 1.0))
    col.append(box("c", (2.0, 1.4, 0.8), (1.5, D / 2 - 1.2, 0)))
    parts.append(pyramid("hood", (2.2, 1.6, 1.3), (1.5, D / 2 - 1.1, 1.8), M("brick"), apex=0.4))
    parts.append(box("flue", (0.8, 0.8, 3.8), (1.5, D / 2 - 1.1, 3.0), M("brick"), bevel=0.02, seg=1))
    parts.append(box("flue_cap", (1.0, 1.0, 0.15), (1.5, D / 2 - 1.1, 6.8), M("stone_dark")))
    mark("Chimney", (1.5, D / 2 - 1.1, 7.0))
    parts.append(wedge("bellows", (0.9, 1.3, 0.5), (-0.1, D / 2 - 1.0, 0.7), M("leather")))
    parts.append(box("bellows_arm", (0.06, 1.8, 0.06), (-0.1, D / 2 - 1.5, 1.6), M("wood_dark")))
    # anvil
    parts.append(cyl("stump", 0.35, 0.55, (0.8, -0.4, 0), M("log"), verts=10))
    parts.append(box("anvil", (0.7, 0.26, 0.28), (0.8, -0.4, 0.55), M("iron")))
    parts.append(cyl("horn", 0.12, 0.35, (1.3, -0.4, 0.72), M("iron"), verts=8, rot=(0, math.pi / 2, 0), r2=0.01, center=True))
    col.append(cyl("c", 0.4, 0.8, (0.8, -0.4, 0), None, verts=8))
    parts.append(cyl("tub", 0.4, 0.6, (2.9, 0.2, 0), M("wood"), verts=12))
    parts.append(cyl("tub_water", 0.36, 0.02, (2.9, 0.2, 0.55), M("water", 0.05), verts=12))
    for k in range(5):                                        # tools on the back wall
        parts.append(box("tool", (0.05, 0.05, 0.9), (-2.8 + k * 0.3, D / 2 - 0.55, 1.2), M("iron")))
        parts.append(box("tool_head", (0.16, 0.08, 0.1), (-2.8 + k * 0.3, D / 2 - 0.55, 2.05), M("iron")))
    parts.append(box("rack", (1.8, 0.08, 0.1), (-2.2, D / 2 - 0.52, 2.15), M("wood_dark")))
    for k in range(4):
        parts.append(torus("shoe", 0.1, 0.02, (-W / 2 + 0.2, -D / 2 - 0.0, 1.2 + k * 0.3), M("iron"), rot=(math.pi / 2, 0, 0), seg=8, mseg=4))
    parts.append(cyl("grind", 0.45, 0.12, (-2.6, -D / 2 - 1.0, 0.75), M("stone"), verts=16, rot=(0, math.pi / 2, 0), center=True))
    parts.append(box("grind_frame", (0.2, 1.0, 0.7), (-2.6, -D / 2 - 1.0, 0), M("timber")))
    parts.append(box("drift", (W + 1.0, 0.9, 0.2), (0, -D / 2 - 0.9, 0), M("snow"), bevel=0.2, seg=2, wonk=0.1))
    parts.append(box("melt", (2.0, 1.4, 0.015), (1.0, -D / 2 - 0.4, 0), M("water", 0.05), wonk=0.2))
    visual = join(parts, "forge")
    export("forge", visual, join(col, "col"))


def brewery():
    """Propination brewhouse (browar): two brick storeys, a louvred malt-kiln cowl on the ridge, a tall round
    stack, a copper kettle under a lean-to at the side with its fire glowing, casks stacked by the door."""
    reset()
    parts, col = [], []
    W, D, H = 14.0, 9.0, 6.4
    ops = [(-4.0, 0.0, 2.2, 2.6 + 1.1, "round")] + [(x, 1.4, 1.0, 1.4, "seg") for x in (-0.5, 2.4, 5.2)] + [(x, 4.0, 1.0, 1.4, "seg") for x in (-4.0, -0.5, 2.4, 5.2)]
    y = front_block(parts, W, D, H, M("brick"), ops)
    door_unit(parts, "-Y", y, -4.0, 2.2, 2.6, portal=False)
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, surround=None, warm=RNG.random() < 0.5, mark=zb < 5, bars=zb < 2)
    parts.append(box("band", (W + 0.1, 0.2, 0.25), (0, y - 0.06, 3.3), M("stone"), bevel=0.02, seg=1))
    col.append(box("c", (W, D, H + 4.5), (0, 0, 0)))
    _roof_set(parts, W + 0.8, D + 1.0, 4.2, (0, 0, H), M("tile"), courses=5, seed=50, drifts=[(0, 0.5, 2.0, 0.2)])
    parts.append(box("cowl", (2.2, 2.2, 1.6), (0, 0, H + 3.9), M("wood_dark")))
    for k in range(4):
        parts.append(box("cowl_louvre", (2.3, 2.3, 0.08), (0, 0, H + 4.1 + k * 0.35), M("wood")))
    parts.append(pyramid("cowl_roof", (2.8, 2.8, 1.2), (0, 0, H + 5.5), M("shingle"), apex=0.05))
    parts.append(pyramid("cowl_snow", (1.6, 1.6, 0.68), (0, 0, H + 6.02), M("snow"), apex=0.05))
    parts.append(cyl("stack", 0.9, 16.0, (5.6, 2.0, 0), M("brick"), verts=14, r2=0.6))
    parts.append(cyl("stack_cap", 0.72, 0.3, (5.6, 2.0, 16.0), M("brick_dark"), verts=14))
    mark("Chimney", (5.6, 2.0, 16.4))
    col.append(cyl("c", 0.9, 16.0, (5.6, 2.0, 0), None, verts=8))
    # kettle house lean-to on the -X end
    kx = -W / 2 - 2.0
    for yy in (-2.5, 2.5):
        parts.append(box("lt_post", (0.25, 0.25, 3.4), (kx - 1.6, yy, 0), M("timber")))
    parts.append(roof("lt_roof", 4.4, 6.4, 0.9, (kx, 0, 3.4), M("shingle"), along_x=False, sag=0.02, flare=0.0, cuts=3))
    sn = roof_snow("lt_snow", 4.4, 6.4, 0.9, (kx, 0, 3.4), along_x=False, sag=0.02, flare=0.0, cuts=3, thick=0.06, cell=0.7, seed=51)
    if sn:
        parts.append(sn)
    parts.append(box("kettle_base", (2.4, 2.4, 1.0), (kx, 0, 0), M("brick_dark"), bevel=0.03, seg=1))
    parts.append(arch("kettle_fire", 0.7, 0.6, 0.1, (kx, -1.21, 0.1), _glow(strength=7.0), bevel=0))
    mark("Furnace", (kx, -1.4, 0.4))
    parts.append(cyl("kettle", 1.0, 1.0, (kx, 0, 1.0), M("copper", 0.4), verts=18, r2=1.1))
    parts.append(sphere("kettle_dome", 1.1, (kx, 0, 2.0), M("patina"), seg=18, rings=8, zscale=0.55))
    parts.append(cyl("kettle_pipe", 0.15, 2.4, (kx, 0, 2.5), M("copper", 0.4), verts=8))
    col.append(box("c", (2.4, 2.4, 2.6), (kx, 0, 0)))
    rng = random.Random(52)
    for k in range(6):
        parts.append(cyl("cask", 0.45, 0.9, (-1.8 + (k % 3) * 0.95, y - 0.8 - (k // 3) * 0.95, 0), M("wood"), verts=12, r2=0.45))
        parts.append(cyl("cask_snow", 0.38, 0.03, (-1.8 + (k % 3) * 0.95, y - 0.8 - (k // 3) * 0.95, 0.9), M("snow"), verts=12))
    col.append(box("c", (3.0, 2.0, 0.9), (-0.85, y - 1.3, 0)))
    parts.append(box("bush_pole", (0.08, 1.2, 0.08), (-2.6, y - 0.6, 4.0), M("wood_dark")))
    parts.append(blob("bush", (0.5, 0.5, 0.5), (-2.6, y - 1.2, 3.6), M("dead_grass")))
    visual = join(parts, "brewery")
    export("brewery", visual, join(col, "col"))


def cooper_yard():
    """Cooper's yard (bednarz): a lean-to workshop, stacks of seasoning staves, casks at every stage (raised with
    trusses, fired over a cresset, hooped and finished), a shaving horse and hoops on pegs, inside a wattle fence."""
    reset()
    parts, col = [], []
    W, D = 10.0, 8.0
    parts.append(box("shed_back", (6.0, 0.3, 3.0), (-1.0, D / 2 - 0.15, 0), M("timber"), wonk=0.03))
    col.append(box("c", (6.0, 0.3, 3.0), (-1.0, D / 2 - 0.15, 0)))
    for x in (-3.8, -1.0, 1.8):
        parts.append(box("shed_post", (0.2, 0.2, 2.4), (x, D / 2 - 2.5, 0), M("timber")))
    sh = roof("shed_roof", 6.6, 2.8, 0.7, (-1.0, D / 2 - 1.3, 2.4), M("shingle"), sag=0.02, flare=0.0, cuts=3)
    parts.append(sh)
    sn = roof_snow("shed_snow", 6.6, 2.8, 0.7, (-1.0, D / 2 - 1.3, 2.4), sag=0.02, flare=0.0, cuts=3, thick=0.06, cell=0.7, seed=60)
    if sn:
        parts.append(sn)
    icicles(parts, (-4.2, D / 2 - 2.7), (2.2, D / 2 - 2.7), 2.38, seed=61, maxlen=0.4)
    rng = random.Random(62)
    for k in range(3):                                         # stave stacks, crossed layers
        x = 3.0 + (k % 2) * 1.2
        yb = -2.0 + k * 1.6
        for j in range(6):
            parts.append(box("staves", (1.0, 0.9, 0.12), (x, yb, j * 0.14), M("wood"), rot=(0, 0, (j % 2) * math.pi / 2)))
        parts.append(box("staves_snow", (0.9, 0.9, 0.05), (x, yb, 0.84), M("snow")))
        col.append(box("c", (1.2, 1.2, 0.9), (x, yb, 0)))
    for k in range(5):                                         # finished casks
        x, yy = -3.6 + k * 1.0, -2.4 + (k % 2) * 0.4
        parts.append(cyl("cask", 0.4, 0.45, (x, yy, 0), M("wood"), verts=12, r2=0.46))
        parts.append(cyl("cask2", 0.46, 0.45, (x, yy, 0.45), M("wood"), verts=12, r2=0.4))
        for z in (0.1, 0.8):
            parts.append(cyl("hoop", 0.44, 0.05, (x, yy, z), M("iron"), verts=12))
        parts.append(cyl("cask_snow", 0.34, 0.03, (x, yy, 0.9), M("snow"), verts=12))
    col.append(box("c", (5.0, 1.4, 0.9), (-1.6, -2.2, 0)))
    parts.append(cyl("raised", 0.5, 0.7, (-1.0, 1.2, 0), M("wood"), verts=12, r2=0.3))
    parts.append(cyl("cresset", 0.25, 0.3, (-1.0, 1.2, 0), M("iron"), verts=8))
    parts.append(blob("cresset_fire", (0.35, 0.35, 0.3), (-1.0, 1.2, 0.2), _glow(strength=6.0)))
    mark("Furnace", (-1.0, 1.2, 0.5))
    parts.append(box("horse", (0.3, 1.6, 0.5), (0.8, 1.6, 0), M("timber")))
    parts.append(box("horse_seat", (0.35, 1.2, 0.08), (0.8, 1.6, 0.5), M("wood")))
    for k in range(4):
        parts.append(torus("hoop_peg", 0.4, 0.02, (-3.5 + k * 0.5, D / 2 - 0.35, 1.8), M("iron"), rot=(math.pi / 2, 0, 0), seg=12, mseg=3))
    for sx, sy, L_, a in ((-1, 0, D, math.pi / 2), (1, 0, D, math.pi / 2), (0, -1, W, 0.0)):
        if sy:
            for x0 in (-W / 2, 1.5):
                parts.append(box("fence", (W / 2 - 1.5 if x0 < 0 else W / 2 - 1.5, 0.12, 1.1), (x0 + (W / 2 - 1.5) / 2, -D / 2, 0), M("wood_dark"), wonk=0.04))
                parts.append(box("fence_snow", (W / 2 - 1.6, 0.1, 0.035), (x0 + (W / 2 - 1.5) / 2, -D / 2, 1.1), M("snow")))
        else:
            parts.append(box("fence", (0.12, D, 1.1), (sx * W / 2, 0, 0), M("wood_dark"), wonk=0.04))
            parts.append(box("fence_snow", (0.1, D - 0.1, 0.035), (sx * W / 2, 0, 1.1), M("snow")))
            col.append(box("c", (0.12, D, 1.1), (sx * W / 2, 0, 0)))
    visual = join(parts, "cooper_yard")
    export("cooper_yard", visual, join(col, "col"))


def tannery_frame():
    """Tanners' drying frame: two trestles with poles hung with stretched hides, a vat of liquor beside, frozen."""
    reset()
    parts = []
    for x in (-2.0, 2.0):
        for sy in (-1, 1):
            parts.append(cbox("leg", (0.12, 0.12, 2.6), (x, sy * 0.5, 1.25), M("timber"), rot=(sy * 0.25, 0, 0)))
    parts.append(cyl("pole", 0.06, 4.6, (0, 0, 2.45), M("timber"), verts=8, rot=(0, math.pi / 2, 0), center=True))
    parts.append(cyl("pole_snow", 0.05, 4.4, (0, 0, 2.52), M("snow"), verts=6, rot=(0, math.pi / 2, 0), center=True))
    for k in range(4):
        h = box("hide", (0.85, 0.03, 1.3), (-1.5 + k, 0, 1.1), M("leather" if k % 2 else "sacking"), wonk=0.12)
        parts.append(h)
        parts.append(box("hide_snow", (0.8, 0.05, 0.03), (-1.5 + k, 0, 2.4), M("snow")))
    parts.append(cyl("vat", 0.7, 1.0, (0, -1.6, 0), M("wood"), verts=14))
    parts.append(cyl("vat_ice", 0.64, 0.02, (0, -1.6, 0.92), M("ice", 0.05), verts=14))
    for z in (0.15, 0.8):
        parts.append(cyl("hoop", 0.72, 0.06, (0, -1.6, z), M("iron"), verts=14))
    export("tannery_frame", join(parts, "tannery_frame"), box("c", (4.4, 1.2, 2.5), (0, 0, 0)))


# ------------------------------------------------------------------ faith: campanile, synagogues, Uniate church, prayer house
def campanile():
    """Free-standing bell tower (dzwonnica): a square brick shaft with stone quoins and string courses, a clock
    dial, an open belfry of paired round arches showing the bells, a copper helm with ribs and snow, a cross."""
    reset()
    parts, col = [], []
    S, H = 5.4, 22.0
    parts.append(box("shaft", (S - 2 * REV, S - 2 * REV, H), (0, 0, 0), M("brick"), bevel=0.04, seg=1, wonk=0.03))
    col.append(box("c", (S, S, H), (0, 0, 0)))
    for face, plane in (("-Y", -S / 2), ("+Y", S / 2), ("-X", -S / 2), ("+X", S / 2)):
        ops = [(0.0, 0.0, 1.6, 2.4 + 0.8, "round")] if face == "-Y" else []
        ops += [(0.0, 7.0, 0.5, 1.4, "round"), (-0.75, H - 5.2, 1.2, 3.6, "round"), (0.75, H - 5.2, 1.2, 3.6, "round")]
        parts.append(facade("f" + face, M("brick"), face, plane, -S / 2, S / 2, 0.0, H, ops, depth=REV if face != "-Y" else REV))
        for (a, zb, w, h, sh) in ops:
            if zb > H - 6:
                parts.append(slab("belfry_void", outline(a, zb, w, h, sh), face, plane, -S / 2 + 0.2, -S / 2 + 0.22, M("void")))
                parts.append(fbox("bel_rail", face, plane, a, -0.05, zb, w, 0.08, 0.9, M("wood_dark")))
                voussoirs(parts, face, plane, a, zb + h - w / 2, w, 0.16, M("stone"), n=7, proud=0.06)
            elif zb > 1:
                win_unit(parts, face, plane, a, zb, w, h, sh, surround=None, cross=False)
        parts.append(fbox("colonnette", face, plane, 0.0, 0.05, H - 5.2, 0.22, 0.2, 3.0, M("stone_pale")))
        if face == "-Y":
            door_unit(parts, face, plane, 0.0, 1.6, 2.4, portal=True)
        rustication(parts, face, plane, -S / 2, S / 2, 0.0, 2.0, [(0.0, 0.0, 1.6, 3.2, "round")] if face == "-Y" else [], course=0.5, mat=M("stone"))
    for z in (5.0, 11.0, H - 5.8, H - 0.3):
        parts.append(box("string", (S + 0.25, S + 0.25, 0.3), (0, 0, z), M("stone"), bevel=0.02, seg=1))
        parts.append(box("string_snow", (S + 0.15, S + 0.15, 0.03), (0, 0, z + 0.3), M("snow")))
    for sx in (-1, 1):
        for sy in (-1, 1):
            z, i = 2.0, 0
            while z < H - 0.6:
                w = 0.8 if i % 2 == 0 else 0.5
                parts.append(box("quoin", (w if i % 2 == 0 else 0.5, 0.5 if i % 2 == 0 else w, 0.45), (sx * (S / 2 - 0.2), sy * (S / 2 - 0.2), z), M("stone_pale"), bevel=0))
                z += 0.5
                i += 1
    clock_face(parts, Vector((0, -S / 2 - 0.08, 14.0)), (0, -1, 0), 1.1, hh=11, mm=50)
    parts.append(cyl("dial", 1.2, 0.12, (0, -S / 2 - 0.04, 14.0), M("plaster_white"), verts=24, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(torus("dial_rim", 1.2, 0.07, (0, -S / 2 - 0.1, 14.0), M("gold", 0.35), rot=(math.pi / 2, 0, 0), seg=24, mseg=4))
    for (x, r) in ((-0.9, 0.6), (0.9, 0.45)):                  # the bells
        parts.append(cyl("bell", r, r * 1.6, (x, 0.0, H - 4.4), M("bronze", 0.35), verts=16, r2=r * 0.62))
        parts.append(sphere("bell_top", r * 0.64, (x, 0.0, H - 4.4 + r * 1.6), M("bronze", 0.35), seg=12, rings=6, zscale=0.5))
    parts.append(box("bell_beam", (S - 0.6, 0.3, 0.3), (0, 0, H - 1.6), M("timber")))
    icicles(parts, (-S / 2, -S / 2 - 0.13), (S / 2, -S / 2 - 0.13), H - 0.3, maxlen=0.5, seed=71)
    # helm: a four-sided copper pyramid over a short drum-like lantern
    parts.append(pyramid("helm", (S + 0.4, S + 0.4, 6.5), (0, 0, H), M("patina"), apex=0.3))
    sn = cap_snow("helm_snow", lambda: pyramid("tmp", (S + 0.4, S + 0.4, 6.5), (0, 0, H), None, apex=0.3), minz=0.3, thick=0.06, cell=0.7, bare=0.14, slide=0.15, lee=(1, 0.3))
    if sn:
        parts.append(sn)
    parts.append(cyl("lant", 0.5, 1.2, (0, 0, H + 6.5), M("patina"), verts=8))
    parts.append(sphere("lant_ball", 0.4, (0, 0, H + 8.0), M("gold", 0.35), seg=10, rings=6))
    parts.append(box("cross_v", (0.1, 0.1, 1.8), (0, 0, H + 8.3), M("gold", 0.35)))
    parts.append(box("cross_h", (0.8, 0.1, 0.1), (0, 0, H + 9.4), M("gold", 0.35)))
    visual = join(parts, "campanile")
    export("campanile", visual, join(col, "col"))


def synagogue_wooden():
    """A smaller synagogue with a tall tiered wooden roof: plastered masonry prayer hall with high round-headed
    windows, a three-tier shingled roof, a timber women's gallery on the side reached by an outside stair."""
    reset()
    parts, col = [], []
    W, D, H = 10.0, 12.0, 6.0
    wall = M("plaster_limeblue")
    ops = [(0.0, 0.0, 1.6, 2.4 + 0.8, "round"), (-3.0, 2.6, 1.0, 2.6, "round"), (3.0, 2.6, 1.0, 2.6, "round")]
    y = front_block(parts, W, D, H, wall, ops)
    door_unit(parts, "-Y", y, 0.0, 1.6, 2.4, portal=True)
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, warm=True, surround="stone_pale", mark=True)
    for face, plane, sgn in (("+X", W / 2, 1),):
        sops = [(yy, 2.6, 1.0, 2.6, "round") for yy in (-3.5, 0.0, 3.5)]
        parts.append(facade("side", wall, face, plane, -D / 2, D / 2, 0.0, H, sops))
        for (a, zb, w, h, sh) in sops:
            win_unit(parts, face, plane, a, zb, w, h, sh, warm=True, surround="stone_pale")
    parts.append(box("plinth", (W + 0.1, D + 0.1, 0.6), (0, 0, 0), M("plaster_limeblue_damp")))
    parts.append(slab("tablets", [(-0.5, 4.2), (0.5, 4.2), (0.5, 5.0), (0.25, 5.3), (0.0, 5.0), (-0.25, 5.3), (-0.5, 5.0)], "-Y", y, 0.0, 0.08, M("stone_pale")))
    col.append(box("c", (W, D, H + 8), (0, 0, 0)))
    cornice(parts, W, D, H - 0.05, t=0.3, proud=0.25, modillions=False, mat=M("plaster_white"))
    z = H
    for k, (L, Wd, h) in enumerate(((W + 1.6, D + 1.6, 2.6), (W - 1.8, D - 1.8, 2.2), (W - 5.0, D - 5.0, 2.4))):
        _hip_set(parts, L, Wd, h, (0, 0, z), M("shingle"), hip=min(L, Wd) / 2 - 0.2, seed=80 + k)
        z += h * 0.7
        if k < 2:
            parts.append(box("tier_wall", (W - 3.6 - 2.8 * k, D - 3.6 - 2.8 * k, 0.9), (0, 0, z - 0.3), M("wood_dark")))
            z += 0.6
    # women's gallery on -X with an outside stair
    gx = -W / 2 - 1.6
    parts.append(box("gal", (3.2, D - 2.0, 3.2), (gx, 0, 2.6), M("log"), bevel=0.03, seg=1))
    for yy in (-D / 2 + 1.2, 0.0, D / 2 - 1.2):
        parts.append(box("gal_post", (0.24, 0.24, 2.6), (gx - 1.4, yy, 0), M("timber")))
    for k in range(4):
        parts.append(fbox("gal_win", "-X", gx - 1.6, -(-3.0 + k * 2.0), 0.02, 3.8, 0.7, 0.03, 0.9, M("glass_warm")))
    parts.append(roof("gal_roof", D - 1.6, 3.8, 1.3, (gx, 0, 5.8), M("shingle"), along_x=False, sag=0.03, flare=0.05, cuts=3))
    sn = roof_snow("gal_snow", D - 1.6, 3.8, 1.3, (gx, 0, 5.8), along_x=False, sag=0.03, flare=0.05, cuts=3, thick=0.06, cell=0.8, seed=85)
    if sn:
        parts.append(sn)
    eave_icicles(parts, D - 2.0, 3.8, 5.78, (gx, 0), along_x=False, sides=(-1,), seed=86)
    for k in range(10):
        parts.append(box("stair", (1.0, 0.3, 0.1), (gx - 2.2, -D / 2 + 0.2 + k * 0.32, 0.26 * (k + 1)), M("wood")))
    parts.append(cbox("stair_str", (0.1, 3.9, 0.2), (gx - 2.7, -D / 2 + 1.6, 1.4), M("timber"), rot=(math.atan2(2.6, 3.2), 0, 0)))
    col.append(box("c", (3.2, D - 2.0, 5.8), (gx, 0, 0)))
    visual = join(parts, "synagogue_wooden")
    export("synagogue_wooden", visual, join(col, "col"))


def _cross3(parts, x, y, z, s=1.0, mat=None):
    """Three-bar (Eastern) cross: a short top bar, the main bar, and a slanted foot bar."""
    mat = mat or M("gold", 0.35)
    parts.append(box("x3_v", (0.08 * s, 0.08 * s, 1.8 * s), (x, y, z), mat))
    parts.append(box("x3_t", (0.45 * s, 0.07 * s, 0.07 * s), (x, y, z + 1.5 * s), mat))
    parts.append(box("x3_m", (0.8 * s, 0.07 * s, 0.08 * s), (x, y, z + 1.2 * s), mat))
    parts.append(cbox("x3_f", (0.55 * s, 0.07 * s, 0.07 * s), (x, y, z + 0.45 * s), mat, rot=(0, math.radians(-20), 0)))


def uniate_church():
    """Greek Catholic (Uniate) church: plastered nave with round windows and an apse, a west tower carrying a drum
    and a copper onion cupola with ribs, a small onion over the sanctuary, three-bar crosses. (Orthodox proper
    had no church in Krakow in 1795; the Uniates did.)"""
    reset()
    parts, col = [], []
    W, D, H = 8.0, 14.0, 7.0
    wall = M("plaster_white")
    parts.append(box("nave", (W - 2 * REV, D, H), (0, 1.0, 0), wall, bevel=0.06, seg=1, wonk=0.03))
    col.append(box("c", (W, D, H), (0, 1.0, 0)))
    for face, plane in (("-X", -W / 2), ("+X", W / 2)):
        sops = [(yy * (1 if face == "+X" else -1), 3.0, 1.1, 2.6, "round") for yy in (-2.5, 1.0, 4.5)]
        parts.append(facade("side", wall, face, plane, -D / 2 + 1.0 - 0.01, D / 2 + 1.0 + 0.01, 0.0, H, sops))
        for (a, zb, w, h, sh) in sops:
            win_unit(parts, face, plane, a, zb, w, h, sh, warm=True, surround="plaster_ochre", glass="glass_stained")
    parts.append(cyl("apse", 3.0, H - 1.0, (0, D / 2 + 1.0, 0), wall, verts=12, bevel=0.03, seg=1))
    col.append(cyl("c", 3.0, H - 1.0, (0, D / 2 + 1.0, 0), None, verts=8))
    parts.append(sphere("apse_roof", 3.1, (0, D / 2 + 1.0, H - 1.0), M("patina"), seg=16, rings=8, zscale=0.5))
    sn = cap_snow("apse_snow", lambda: sphere("tmp", 3.1, (0, D / 2 + 1.0, H - 1.0), None, seg=16, rings=8, zscale=0.5), minz=0.5, thick=0.05, cell=0.6)
    if sn:
        parts.append(sn)
    _roof_set(parts, D, W + 0.8, 3.8, (0, 1.0, H), M("shingle_dark"), along_x=False, courses=0, seed=90, cell=1.0)
    parts.append(box("pilaster_band", (W + 0.2, D + 0.1, 0.35), (0, 1.0, H - 0.4), M("plaster_ochre")))
    # sanctuary cupola on the ridge
    sx_, sy_ = 0.0, D / 2 - 1.5
    parts.append(cyl("s_drum", 0.9, 1.4, (sx_, sy_, H + 2.8), M("plaster_white"), verts=12))
    parts.append(sphere("s_onion", 1.15, (sx_, sy_, H + 4.8), M("patina"), seg=16, rings=10, zscale=1.2))
    parts.append(cyl("s_tip", 0.2, 1.0, (sx_, sy_, H + 6.0), M("patina"), verts=8, r2=0.02))
    sn = cap_snow("s_snow", lambda: sphere("tmp", 1.15, (sx_, sy_, H + 4.8), None, seg=16, rings=10, zscale=1.2), minz=0.65, thick=0.04, cell=0.35)
    if sn:
        parts.append(sn)
    _cross3(parts, sx_, sy_, H + 6.6, s=0.7)
    # west tower with the main drum and onion
    TS, TH = 5.0, 11.0
    ty = -D / 2 + 1.0 - TS / 2 + 0.4
    parts.append(box("tower", (TS - 2 * REV, TS - REV, TH), (0, ty + REV / 2, 0), wall, bevel=0.05, seg=1))
    col.append(box("c", (TS, TS, TH), (0, ty, 0)))
    tf = ty - TS / 2
    ops = [(0.0, 0.0, 1.6, 2.4 + 0.8, "round"), (0.0, 5.2, 0.9, 1.8, "round"), (0.0, 8.4, 1.0, 1.8, "round")]
    parts.append(facade("tower_f", wall, "-Y", tf, -TS / 2, TS / 2, 0.0, TH, ops))
    door_unit(parts, "-Y", tf, 0.0, 1.6, 2.4, portal=True, surround="stone_pale")
    win_unit(parts, "-Y", tf, 0.0, 5.2, 0.9, 1.8, "round", warm=True, surround="plaster_ochre", glass="glass_stained")
    win_unit(parts, "-Y", tf, 0.0, 8.4, 1.0, 1.8, "round", louvre=True, surround="plaster_ochre")
    parts.append(slab("icon", [(-0.5, 3.8), (0.5, 3.8), (0.5, 4.8), (0.0, 5.05), (-0.5, 4.8)], "-Y", tf, 0.0, 0.05, M("gold", 0.3)))
    parts.append(slab("icon_in", [(-0.38, 3.9), (0.38, 3.9), (0.38, 4.75), (-0.38, 4.75)], "-Y", tf, 0.05, 0.07, M("navy")))
    for z in (4.6, TH - 0.2):
        parts.append(box("tband", (TS + 0.2, TS + 0.2, 0.3), (0, ty, z), M("plaster_ochre"), bevel=0.02, seg=1))
        parts.append(box("tband_snow", (TS + 0.1, TS + 0.1, 0.03), (0, ty, z + 0.3), M("snow")))
    quoins(parts, TS, TS, 0.3, TH, tf)
    parts.append(cyl("drum", 1.9, 2.4, (0, ty, TH + 0.1), M("plaster_white"), verts=16, bevel=0.02, seg=1))
    for k in range(8):
        a = math.tau * (k + 0.5) / 8
        parts.append(cbox("drum_win", (0.45, 0.08, 1.2), (1.9 * math.cos(a), ty + 1.9 * math.sin(a), TH + 1.3), M("glass_warm"), rot=(0, 0, a + math.pi / 2)))
    parts.append(sphere("onion", 2.4, (0, ty, TH + 4.2), M("patina"), seg=20, rings=12, zscale=1.25))
    bm = bmesh.new()
    _tube(bm, (0, ty, TH + 6.9), (0, ty, TH + 8.2), 0.5, 0.02, n=10)
    parts.append(_mesh_obj("onion_tip", bm, M("patina")))
    dome_ribs(parts, 0, ty, TH + 4.2, 2.4, n=8, zscale=1.25, mat=M("gold", 0.35), z_from=-0.6, width=0.05)
    sn = cap_snow("onion_snow", lambda: sphere("tmp", 2.4, (0, ty, TH + 4.2), None, seg=20, rings=12, zscale=1.25), minz=0.62, thick=0.05, cell=0.5, bare=0.2)
    if sn:
        parts.append(sn)
    _cross3(parts, 0, ty, TH + 8.1, s=1.0)
    icicles(parts, (-TS / 2, tf - 0.12), (TS / 2, tf - 0.12), TH - 0.2, maxlen=0.4, seed=91)
    visual = join(parts, "uniate_church")
    export("uniate_church", visual, join(col, "col"))


def prayer_house():
    """Small Protestant (Lutheran-Reformed) prayer house: a plain limewashed hall with tall round-headed windows
    and no tower (the law allowed none), a hipped tile roof with a little ridge turret (sygnaturka)."""
    reset()
    parts, col = [], []
    W, D, H = 14.0, 9.0, 6.0
    wall = M("plaster_lime")
    ops = [(0.0, 0.0, 1.6, 2.4 + 0.8, "round"), (-2.8, 2.0, 1.0, 2.8, "round"), (2.8, 2.0, 1.0, 2.8, "round"),
           (-5.4, 2.0, 1.0, 2.8, "round"), (5.4, 2.0, 1.0, 2.8, "round"), (0.0, 4.2, 0.9, 0.9, "round")]
    y = front_block(parts, W, D, H, wall, ops)
    door_unit(parts, "-Y", y, 0.0, 1.6, 2.4, portal=False)
    parts.append(slab("pediment_door", [(-1.4, 3.4), (1.4, 3.4), (0.0, 4.0)], "-Y", y, 0.0, 0.14, M("stone_pale")))
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, warm=True, surround="plaster_white", mark=zb < 3)
    for face, plane in (("-X", -W / 2), ("+X", W / 2)):
        sops = [(yy, 2.0, 1.0, 2.8, "round") for yy in (-2.0, 2.0)]
        parts.append(facade("side", wall, face, plane, -D / 2, D / 2, 0.0, H, sops))
        for (a, zb, w, h, sh) in sops:
            win_unit(parts, face, plane, a, zb, w, h, sh, warm=True, surround="plaster_white")
    parts.append(box("plinth", (W + 0.1, D + 0.1, 0.5), (0, 0, 0), M("plaster_lime_damp")))
    cornice(parts, W, D, H - 0.05, t=0.3, proud=0.22, modillions=False, mat=M("plaster_white"))
    col.append(box("c", (W, D, H + 4), (0, 0, 0)))
    _hip_set(parts, W + 0.9, D + 0.9, 4.0, (0, 0, H + 0.2), M("tile"), hip=3.0, seed=95)
    parts.append(box("turret", (1.0, 1.0, 1.4), (0, 0, H + 3.8), M("wood_dark")))
    parts.append(cyl("turret_spire", 0.8, 2.2, (0, 0, H + 5.2), M("lead"), verts=8, r2=0.03))
    parts.append(sphere("turret_ball", 0.16, (0, 0, H + 7.5), M("gold", 0.35), seg=8, rings=5))
    parts.append(box("turret_cross", (0.06, 0.06, 0.8), (0, 0, H + 7.6), M("iron")))
    visual = join(parts, "prayer_house")
    export("prayer_house", visual, join(col, "col"))


def shrine_column():
    """Roadside column shrine (figura): a stone pedestal and a Tuscan column carrying a small painted figure of St
    John Nepomuk under a tin umbrella, a wrought-iron railing round the base, a candle lantern, snow on it all."""
    reset()
    parts = []
    parts.append(box("step", (2.2, 2.2, 0.25), (0, 0, 0), M("stone_dark"), bevel=0.03, seg=1))
    parts.append(box("ped", (1.0, 1.0, 1.4), (0, 0, 0.25), M("stone"), bevel=0.03, seg=1))
    parts.append(box("ped_cap", (1.2, 1.2, 0.15), (0, 0, 1.65), M("stone_pale"), bevel=0.02, seg=1))
    parts.append(box("ped_snow", (1.1, 1.1, 0.04), (0, 0, 1.8), M("snow")))
    parts.append(cyl("col", 0.26, 2.6, (0, 0, 1.8), M("stone_pale"), verts=12, r2=0.22, bevel=0.01, seg=1))
    parts.append(box("capital", (0.6, 0.6, 0.2), (0, 0, 4.4), M("stone_pale"), bevel=0.02, seg=1))
    parts.append(cyl("robe", 0.22, 1.0, (0, 0, 4.6), M("black"), verts=10, r2=0.12))
    parts.append(cyl("surplice", 0.2, 0.4, (0, 0, 5.1), M("linen"), verts=10, r2=0.16))
    parts.append(sphere("head", 0.12, (0, 0, 5.72), M("skin"), seg=10, rings=6))
    parts.append(cyl("biretta", 0.1, 0.1, (0, 0, 5.8), M("black"), verts=8))
    for k in range(5):
        a = math.tau * k / 5
        parts.append(sphere("star", 0.035, (0.18 * math.cos(a), 0.18 * math.sin(a), 6.05), M("gold", 0.3), seg=6, rings=4))
    parts.append(cyl("umbrella", 0.75, 0.45, (0, 0, 6.2), M("lead"), verts=12, r2=0.05))
    parts.append(cyl("umb_snow", 0.55, 0.25, (0, 0, 6.35), M("snow"), verts=12, r2=0.04))
    icicles(parts, (-0.7, -0.2), (0.7, -0.2), 6.2, maxlen=0.2, seed=97, density=6)
    parts.append(box("cross", (0.04, 0.04, 0.5), (0, 0, 6.65), M("iron")))
    for sx, sy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        L_ = 2.0
        parts.append(box("rail", (L_ if sy else 0.04, 0.04 if sy else L_, 0.04), (sx * 0.98, sy * 0.98, 1.05), M("iron")))
        for k in range(9):
            t = -0.9 + k * 0.225
            parts.append(box("bar", (0.025, 0.025, 0.8), (sx * 0.98 + (t if sy else 0), sy * 0.98 + (0 if sy else t), 0.25), M("iron")))
    parts.append(box("lantern", (0.2, 0.2, 0.3), (0, -0.62, 1.15), M("gold", 0.3, emit=(1.0, 0.7, 0.35), emit_strength=4.0)))
    export("shrine_column", join(parts, "shrine_column"), box("c", (2.1, 2.1, 1.8), (0, 0, 0)))


def monastery_wall():
    """8 m of monastery enclosure wall: plastered brick on a stone footing, a buttress, a tile coping ridged with
    snow; outer face at -Y. Segments butt end to end."""
    reset()
    parts = []
    L, T, H = 8.0, 0.8, 3.6
    parts.append(box("footing", (L, T + 0.2, 0.5), (0, 0, 0), M("stone_dark"), wonk=0.02))
    parts.append(box("wall", (L, T, H - 0.5), (0, 0, 0.5), M("plaster_grey"), wonk=0.03))
    parts.append(box("wall_damp", (L + 0.01, T + 0.02, 0.6), (0, 0, 0.5), M("plaster_grey_damp")))
    parts.append(taper_box("butt", (0.9, 0.9, 2.8), (L / 2 - 0.5, -T / 2 - 0.4, 0), M("brick"), top=0.6))
    parts.append(roof("coping", L + 0.05, T + 0.5, 0.45, (0, 0, H), M("tile_dark"), sag=0.0, flare=0.0, cuts=4, courses=1))
    sn = roof_snow("coping_snow", L + 0.05, T + 0.5, 0.45, (0, 0, H), sag=0.0, flare=0.0, cuts=4, thick=0.07, cell=0.6, bare=0.12, slide=0.0, seed=98)
    if sn:
        parts.append(sn)
    eave_icicles(parts, L - 0.2, T + 0.5, H - 0.02, (0, 0), seed=99, sides=(-1,), maxlen=0.35)
    rime(parts, "-Y", -T / 2, 0.0, 1.5, L * 0.8, 1.8, seed=100)
    export("monastery_wall", join(parts, "monastery_wall"), box("c", (L, T + 0.2, H + 0.4), (0, 0, 0)))


def monastery_gate():
    """Monastery gateway: an arched carriage gate with oak leaves (one ajar), a stone surround, a niche with a
    figure of the Virgin above, a gabled tile cap; wall stubs either side. Front at -Y; walkable through."""
    reset()
    parts, col = [], []
    W, T, H = 6.0, 1.2, 6.4
    gw, gh = 3.0, 2.8 + 1.5
    parts.append(facade("front", M("plaster_grey"), "-Y", -T / 2, -W / 2, W / 2, 0.0, H, [(0.0, 0.0, gw, gh, "round")], depth=T, back=False))
    parts.append(box("top", (W, T, H - gh - 0.02), (0, 0, gh + 0.01), M("plaster_grey")))
    voussoirs(parts, "-Y", -T / 2, 0.0, gh - gw / 2, gw, 0.35, M("stone"), n=11, proud=0.1, key=0.2)
    for sx in (-1, 1):
        parts.append(box("jamb", (0.4, 0.2, gh - gw / 2), (sx * (gw / 2 + 0.2), -T / 2 - 0.1, 0), M("stone"), bevel=0.02, seg=1))
    leaf = fbox("leaf_l", "-Y", -T / 2, -gw / 4, -0.3, 0.0, gw / 2 - 0.04, 0.1, gh - gw / 2, M("wood_dark"))
    parts.append(leaf)
    leaf2 = fbox("leaf_r", "-Y", -T / 2, gw / 4, -0.3, 0.0, gw / 2 - 0.04, 0.1, gh - gw / 2, M("wood_dark"))
    _swing(leaf2, Vector((gw / 2, -T / 2 + 0.3, 0)), math.radians(70))
    parts.append(leaf2)
    niche = (0.0, gh + 0.5, 0.8, 1.3, "round")
    parts.append(slab("niche_bg", outline(*niche), "-Y", -T / 2, 0.0, 0.02, M("plaster_limeblue")))
    parts.append(fbox("niche_sill", "-Y", -T / 2, 0.0, 0.1, gh + 0.4, 1.0, 0.25, 0.1, M("stone")))
    parts.append(cyl("figure", 0.14, 0.7, (0, -T / 2 - 0.1, gh + 0.5), M("navy"), verts=8, r2=0.08))
    parts.append(sphere("fig_head", 0.07, (0, -T / 2 - 0.1, gh + 1.27), M("plaster_white"), seg=8, rings=5))
    parts.append(roof("cap", T + 0.8, W + 0.6, 1.4, (0, 0, H), M("tile_dark"), along_x=True, sag=0.03, flare=0.05, courses=2))
    parts[-1] = parts[-1]
    sn = roof_snow("cap_snow", T + 0.8, W + 0.6, 1.4, (0, 0, H), along_x=True, sag=0.03, flare=0.05, thick=0.06, cell=0.5, seed=101)
    if sn:
        parts.append(sn)
    for sx in (-1, 1):
        parts.append(box("stub", (2.0, 0.8, 3.6), (sx * (W / 2 + 1.0), 0.2, 0), M("plaster_grey")))
        parts.append(box("stub_cop", (2.0, 1.1, 0.25), (sx * (W / 2 + 1.0), 0.2, 3.6), M("tile_dark")))
        parts.append(box("stub_snow", (1.95, 1.0, 0.05), (sx * (W / 2 + 1.0), 0.2, 3.85), M("snow")))
        col.append(box("c", ((W - gw) / 2 + 2.0, T, H), (sx * (gw / 2 + ((W - gw) / 2 + 2.0) / 2), 0, 0)))
    col.append(box("c", (gw, T, H - gh), (0, 0, gh)))
    icicles(parts, (-W / 2, -T / 2 - 0.4), (W / 2, -T / 2 - 0.4), H - 0.02, maxlen=0.4, seed=102)
    visual = join(parts, "monastery_gate")
    export("monastery_gate", visual, join(col, "col"))


# ------------------------------------------------------------------ the castle
def wawel_far():
    """Wawel for the far skyline (no collision, ~6k tris): the hill, the curtain wall with the Senators' and
    Sandomierska towers, the palace's snowy roofs round its courtyard, and the cathedral with its towers and the
    gold dome of the Sigismund Chapel. Built at 1:1, placed ~150 m off; roofs are snow white."""
    reset()
    parts = []
    snow, br, st, pl = M("snow"), M("brick"), M("stone"), M("plaster_cream")
    hill = cyl("hill", 70.0, 12.0, (0, 0, -1.0), M("stone_dark"), verts=16, r2=55.0)
    rng = random.Random(3)
    edit_verts(hill, lambda co: (setattr(co, "x", co.x * (1 + rng.uniform(-0.05, 0.05))), setattr(co, "y", co.y * 0.7)))
    parts.append(hill)
    parts.append(cyl("hill_snow", 56.0, 0.4, (0, 0, 11.0), snow, verts=16))
    edit_verts(parts[-1], lambda co: setattr(co, "y", co.y * 0.7))
    # curtain wall ring
    pts = [(math.cos(a) * 52, math.sin(a) * 34) for a in [math.tau * k / 14 for k in range(14)]]
    for i in range(14):
        p0, p1 = Vector((*pts[i], 0)), Vector((*pts[(i + 1) % 14], 0))
        c = (p0 + p1) / 2
        L = (p1 - p0).length
        ang = math.atan2(p1.y - p0.y, p1.x - p0.x)
        parts.append(cbox("curtain", (L + 0.5, 2.5, 8.0), (c.x, c.y, 15.0), br, rot=(0, 0, ang)))
        parts.append(cbox("curtain_snow", (L + 0.5, 2.6, 0.3), (c.x, c.y, 19.1), snow, rot=(0, 0, ang)))
    def tower(x, y, r, h, roof_h, cone=True):
        parts.append(cyl("tower", r, h, (x, y, 11.0), br, verts=12))
        parts.append(cyl("tower_band", r + 0.4, 1.2, (x, y, 11.0 + h - 1.2), st, verts=12))
        parts.append(cyl("tower_roof", r + 0.6, roof_h, (x, y, 11.0 + h), snow if cone else M("patina"), verts=12, r2=0.1))
    tower(-38, -24, 5.0, 22.0, 9.0)            # Senators' Tower (Lubranka)
    tower(-50, 8, 4.5, 18.0, 7.0)              # Sandomierska
    tower(40, -22, 4.0, 16.0, 6.0)             # Thieves' Tower
    # the palace round its arcaded courtyard
    for (cx, cy, L, W) in ((10, 10, 44, 10), (10, 38, 44, 10), (-7, 24, 10, 38), (27, 24, 10, 38)):
        parts.append(box("palace", (L, W, 14.0), (cx, cy - 14, 11.0), pl))
        parts.append(roof("palace_roof", L, W + 1.0, 6.0, (cx, cy - 14, 25.0), snow, sag=0.0, flare=0.0, cuts=2, along_x=L > W))
        for k in range(int(max(L, W) / 4)):
            t = -max(L, W) / 2 + 2 + k * 4
            px, py = (cx + t, cy - 14 - W / 2 - 0.05) if L > W else (cx - L / 2 - 0.05, cy - 14 + t)
            parts.append(box("pwin", (1.2 if L > W else 0.1, 0.1 if L > W else 1.2, 2.0), (px, py, 17.0), M("glass_warm")))
    # cathedral: nave, towers, and the Sigismund Chapel's gold dome on its drum
    cx, cy = -20, -8
    parts.append(box("nave", (44, 14, 22), (cx, cy, 11.0), st))
    parts.append(roof("nave_roof", 44, 15, 10, (cx, cy, 33.0), snow, sag=0.0, flare=0.0, cuts=2))
    for (tx, h) in ((cx - 24, 36), (cx + 20, 30)):
        parts.append(box("ctower", (8, 8, h), (tx, cy - 3, 11.0), br))
        parts.append(cyl("ctower_helm", 5.0, 8.0, (tx, cy - 3, 11.0 + h), M("patina"), verts=8, r2=1.5))
        parts.append(sphere("ctower_bulb", 2.2, (tx, cy - 3, 20.0 + h), M("patina"), seg=10, rings=6))
        parts.append(cyl("ctower_spike", 0.4, 5.0, (tx, cy - 3, 22.0 + h), M("gold", 0.35), verts=6, r2=0.05))
    parts.append(box("chapel", (10, 10, 14), (cx - 6, cy - 12, 11.0), st))
    parts.append(cyl("chapel_drum", 4.2, 5.0, (cx - 6, cy - 12, 25.0), st, verts=16))
    parts.append(sphere("sigismund_dome", 4.6, (cx - 6, cy - 12, 30.0), M("gold", 0.25), seg=20, rings=10, zscale=0.9))
    parts.append(cyl("chapel_lantern", 1.2, 3.0, (cx - 6, cy - 12, 34.0), M("gold", 0.25), verts=10))
    parts.append(sphere("chapel_crown", 0.9, (cx - 6, cy - 12, 37.6), M("gold", 0.25), seg=10, rings=6))
    parts.append(sphere("vasa_dome", 3.8, (cx + 4, cy - 12, 29.0), M("patina"), seg=16, rings=8, zscale=0.9))
    parts.append(box("vasa", (8, 8, 14), (cx + 4, cy - 12, 11.0), st))
    # the lit windows twinkle across the river at night
    for k in range(7):
        parts.append(box("cwin", (1.2, 0.1, 5.0), (cx - 18 + k * 6, cy - 7.05, 18.0), M("glass_warm")))
    visual = join(parts, "wawel_far")
    export("wawel_far", visual, None)


def castle_gate():
    """Near castle gate: a square gate tower with a vaulted passage (walkable), two round flanking towers with
    conical roofs, wall stubs with battlements, a drawbridge lowered over a dry ditch, snow on every ledge."""
    reset()
    parts, col = [], []
    S, H = 8.0, 14.0
    gw, gh = 3.4, 3.4 + 1.7
    parts.append(facade("front", M("stone"), "-Y", -S / 2, -S / 2, S / 2, 0.0, 5.5, [(0.0, 0.0, gw, gh, "round")], depth=S, back=False))
    parts.append(facade("back", M("stone"), "+Y", S / 2, -S / 2, S / 2, 0.0, 5.5, [(0.0, 0.0, gw, gh, "round")], depth=0.01, back=False))
    parts.append(box("upper", (S - 0.6, S - 0.6, H - 5.5), (0, 0, 5.5), M("brick")))
    parts.append(box("roofslab", (S, S, 0.3), (0, 0, 5.2), M("stone")))
    ops = [(0.0, 8.0, 1.0, 1.8, "round"), (-2.4, 8.0, 0.25, 1.4, "rect"), (2.4, 8.0, 0.25, 1.4, "rect")]
    parts.append(facade("up_f", M("brick"), "-Y", -S / 2, -S / 2, S / 2, 5.5, H, ops, depth=0.3))
    win_unit(parts, "-Y", -S / 2, 0.0, 8.0, 1.0, 1.8, "round", surround=None, warm=True, cross=False)
    voussoirs(parts, "-Y", -S / 2, 0.0, gh - gw / 2, gw, 0.5, M("stone_pale"), n=11, proud=0.12, key=0.2)
    parts.append(fbox("arms", "-Y", -S / 2, 0.0, 0.08, 6.0, 1.2, 0.14, 1.4, M("stone_pale")))
    parts.append(cyl("eagle", 0.35, 0.08, (0, -S / 2 - 0.2, 6.7), M("plaster_white"), verts=12, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(box("band", (S + 0.3, S + 0.3, 0.3), (0, 0, 5.5), M("stone"), bevel=0.02, seg=1))
    parts.append(box("band_snow", (S + 0.2, S + 0.2, 0.03), (0, 0, 5.8), M("snow")))
    for face, plane in (("-Y", -S / 2), ("+Y", S / 2), ("-X", -S / 2), ("+X", S / 2)):
        for k in range(5):
            parts.append(fbox("corbel", face, plane, -S / 2 + 0.8 + k * 1.6, 0.25, H - 0.6, 0.35, 0.5, 0.6, M("stone")))
    parts.append(box("parapet", (S + 0.9, S + 0.9, 1.0), (0, 0, H), M("brick")))
    for sx in range(5):
        for side in range(4):
            x = -S / 2 - 0.2 + sx * (S + 0.4) / 4
            px, py = [(x, -S / 2 - 0.25), (x, S / 2 + 0.25), (-S / 2 - 0.25, x), (S / 2 + 0.25, x)][side]
            parts.append(box("merlon", (0.8, 0.8, 0.9), (px, py, H + 1.0), M("brick")))
            parts.append(box("merlon_snow", (0.72, 0.72, 0.04), (px, py, H + 1.9), M("snow")))
    parts.append(pyramid("roof", (S - 0.4, S - 0.4, 5.0), (0, 0, H + 1.0), M("tile_dark"), apex=0.2))
    sn = cap_snow("roof_snow", lambda: pyramid("tmp", (S - 0.4, S - 0.4, 5.0), (0, 0, H + 1.0), None, apex=0.2), minz=0.3, thick=0.07, cell=0.8, slide=0.3)
    if sn:
        parts.append(sn)
    for sx in (-1, 1):
        tx = sx * (S / 2 + 2.6)
        parts.append(cyl("rtower", 3.0, 11.0, (tx, -0.5, 0), M("brick"), verts=16))
        parts.append(cyl("rtower_base", 3.4, 2.5, (tx, -0.5, 0), M("stone"), verts=16, r2=3.0))
        for k in range(3):
            a = -math.pi / 2 + (k - 1) * 0.6
            parts.append(cbox("loop", (0.2, 0.15, 1.3), (tx + 3.02 * math.cos(a), -0.5 + 3.02 * math.sin(a), 6.0), M("void"), rot=(0, 0, a + math.pi / 2)))
        parts.append(cyl("rtower_roof", 3.5, 5.0, (tx, -0.5, 11.0), M("tile_dark"), verts=16, r2=0.1))
        sn = cap_snow("rt_snow", lambda tx=tx: cyl("tmp", 3.5, 5.0, (tx, -0.5, 11.0), None, verts=16, r2=0.1), minz=0.5, thick=0.06, cell=0.8, slide=0.3)
        if sn:
            parts.append(sn)
        icicles(parts, (tx - 2.8, -3.9), (tx + 2.8, -3.9), 10.98, maxlen=0.5, seed=110 + sx)
        col.append(cyl("c", 3.2, 11.0, (tx, -0.5, 0), None, verts=8))
        wx = sx * (S / 2 + 2.6 + 3.0 + 3.0)
        parts.append(box("wall", (6.0, 2.4, 8.0), (wx, 0.3, 0), M("brick")))
        for k in range(3):
            parts.append(box("wmerlon", (1.0, 0.6, 0.9), (wx - 2.0 + k * 2.0, -0.6, 8.0), M("brick")))
            parts.append(box("wmerlon_snow", (0.92, 0.52, 0.04), (wx - 2.0 + k * 2.0, -0.6, 8.9), M("snow")))
        parts.append(box("walk_snow", (6.0, 1.6, 0.05), (wx, 0.6, 8.0), M("snow")))
        col.append(box("c", (6.0, 2.4, 8.0), (wx, 0.3, 0)))
    parts.append(box("bridge", (gw - 0.2, 5.0, 0.25), (0, -S / 2 - 2.5, -0.05), M("wood")))
    for k in range(10):
        parts.append(box("plank", (gw - 0.2, 0.06, 0.02), (0, -S / 2 - 0.3 - k * 0.48, 0.2), M("wood_dark")))
    for sx in (-1, 1):
        bm = bmesh.new()
        _tube(bm, (sx * (gw / 2 - 0.1), -S / 2 - 4.9, 0.3), (sx * (gw / 2 - 0.1), -S / 2 - 0.1, 5.0), 0.04, 0.04, n=4)
        parts.append(_mesh_obj("chain", bm, M("iron")))
    parts.append(box("bridge_snow", (gw - 0.8, 4.6, 0.02), (0.1, -S / 2 - 2.6, 0.2), M("snow_dirty")))
    visual = join(parts, "castle_gate")
    for sx in (-1, 1):
        col.append(box("c", ((S - gw) / 2, S, H + 1), (sx * (S / 2 - (S - gw) / 4), 0, 0)))
    col.append(box("c", (gw, S, H + 1 - gh), (0, 0, gh)))
    export("castle_gate", visual, join(col, "col"))


# ------------------------------------------------------------------ justice props (placed by the street-life scenes)
def pillory():
    """Pregierz: a wooden post on a two-step stone base with a hinged neck-and-wrist board, an iron collar on a
    chain, a small lead cap and a snowy step."""
    reset()
    parts = []
    parts.append(box("step1", (2.4, 2.4, 0.35), (0, 0, 0), M("stone_dark"), bevel=0.03, seg=1, wonk=0.03))
    parts.append(box("step2", (1.6, 1.6, 0.35), (0, 0, 0.35), M("stone"), bevel=0.03, seg=1, wonk=0.03))
    parts.append(box("step_snow", (2.3, 2.3, 0.03), (0.0, 0.0, 0.35), M("snow")))
    parts.append(box("step2_snow", (1.5, 1.5, 0.03), (0, 0, 0.7), M("snow")))
    parts.append(box("post", (0.3, 0.3, 3.0), (0, 0.15, 0.7), M("timber"), bevel=0.02, seg=1))
    parts.append(pyramid("cap", (0.5, 0.5, 0.35), (0, 0.15, 3.7), M("lead"), apex=0.02))
    snow_cap(parts, 0, 0.15, 3.9, 0.15, 0.06, seg=6)
    for zz, dz in ((1.95, 0.0), (2.13, 0.0)):
        parts.append(box("board", (1.4, 0.1, 0.18), (0, -0.05, zz + dz), M("wood")))
    for x, r in ((-0.45, 0.06), (0.0, 0.1), (0.45, 0.06)):
        parts.append(cyl("hole", r, 0.12, (x, -0.05, 2.13), M("void"), verts=10, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(box("board_snow", (1.36, 0.09, 0.025), (0, -0.05, 2.31), M("snow")))
    parts.append(box("hinge", (0.06, 0.12, 0.36), (-0.72, -0.05, 1.95), M("iron")))
    parts.append(box("hasp", (0.06, 0.12, 0.36), (0.72, -0.05, 1.95), M("iron")))
    parts.append(torus("collar", 0.13, 0.02, (0.0, -0.02, 1.2), M("iron"), rot=(0, 0, 0), seg=12, mseg=4))
    bm = bmesh.new()
    _tube(bm, (0, 0.0, 1.6), (0.05, -0.02, 1.25), 0.012, 0.012, n=4)
    parts.append(_mesh_obj("chain", bm, M("iron")))
    export("pillory", join(parts, "pillory"), box("c", (1.6, 1.6, 3.7), (0, 0, 0)))


def stocks():
    """Dyby: a low plank bench behind a two-part board with four leg holes, on oak posts; snow on the board."""
    reset()
    parts = [box("bench", (2.0, 0.4, 0.08), (0, 0.6, 0.42), M("wood"))]
    for x in (-0.85, 0.85):
        parts.append(box("bench_leg", (0.1, 0.35, 0.42), (x, 0.6, 0), M("wood_dark")))
        parts.append(box("post", (0.16, 0.16, 0.9), (x + (0.12 if x > 0 else -0.12), 0, 0), M("timber")))
    parts.append(box("board_lo", (2.1, 0.1, 0.2), (0, 0, 0.25), M("wood")))
    parts.append(box("board_hi", (2.1, 0.1, 0.2), (0, 0, 0.45), M("wood")))
    for x in (-0.65, -0.35, 0.35, 0.65):
        parts.append(cyl("hole", 0.07, 0.12, (x, 0, 0.45), M("void"), verts=10, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(box("board_snow", (2.0, 0.09, 0.025), (0, 0, 0.65), M("snow")))
    parts.append(box("bench_snow", (1.9, 0.36, 0.025), (0, 0.6, 0.5), M("snow")))
    parts.append(box("hasp", (0.12, 0.12, 0.3), (1.08, 0, 0.3), M("iron")))
    export("stocks", join(parts, "stocks"), box("c", (2.3, 1.0, 0.9), (0, 0.3, 0)))


def whipping_post():
    """Kuna / whipping post: an oak post on a stone block with iron rings and a chain at head height, the town
    drum on a stand beside it (the sentence was drummed out)."""
    reset()
    parts = [box("block", (0.9, 0.9, 0.4), (0, 0, 0), M("stone"), bevel=0.03, seg=1, wonk=0.03),
             box("block_snow", (0.8, 0.8, 0.03), (0, 0, 0.4), M("snow")),
             box("post", (0.26, 0.26, 2.4), (0, 0, 0.4), M("timber"), bevel=0.02, seg=1)]
    snow_cap(parts, 0, 0, 2.8, 0.14, 0.05, seg=6)
    for z in (1.8, 2.1):
        parts.append(torus("ring", 0.09, 0.018, (0, -0.2, z), M("iron"), rot=(math.pi / 2, 0, 0), seg=10, mseg=4))
        parts.append(box("staple", (0.06, 0.06, 0.06), (0, -0.14, z + 0.08), M("iron")))
    bm = bmesh.new()
    _tube(bm, (0, -0.25, 1.75), (0.1, -0.3, 1.2), 0.012, 0.012, n=4)
    parts.append(_mesh_obj("chain", bm, M("iron")))
    dx = 1.1
    for k in range(3):
        a = math.tau * k / 3
        parts.append(cbox("stand", (0.05, 0.05, 0.75), (dx + 0.25 * math.cos(a), 0.2 + 0.25 * math.sin(a), 0.36), M("wood_dark"), rot=(0.25 * math.sin(a), -0.25 * math.cos(a), 0)))
    parts.append(cyl("drum", 0.32, 0.4, (dx, 0.2, 0.72), M("crimson"), verts=14))
    for z in (0.72, 1.1):
        parts.append(cyl("drum_hoop", 0.34, 0.05, (dx, 0.2, z), M("wood"), verts=14))
    parts.append(cyl("drum_head", 0.3, 0.02, (dx, 0.2, 1.12), M("paper"), verts=14))
    parts.append(cyl("drum_snow", 0.24, 0.02, (dx, 0.2, 1.14), M("snow"), verts=12))
    for s in (-1, 1):
        parts.append(cbox("stick", (0.03, 0.03, 0.4), (dx + s * 0.08, 0.15, 1.2), M("wood"), rot=(0, 1.2 * s, 0)))
    export("whipping_post", join(parts, "whipping_post"), box("c", (0.9, 0.9, 2.8), (0, 0, 0)))


def gallows():
    """Szubienica outside the walls: two oak posts on a stone footing joined by a beam with braces, a noose on the
    rope, a placard board on its own post and a ladder leaning on the beam; snow along the beam."""
    reset()
    parts = [box("footing", (4.4, 1.4, 0.4), (0, 0, 0), M("stone_dark"), bevel=0.03, seg=1, wonk=0.04),
             box("footing_snow", (4.3, 1.3, 0.03), (0, 0, 0.4), M("snow"))]
    for x in (-1.8, 1.8):
        parts.append(box("post", (0.3, 0.3, 4.0), (x, 0, 0.4), M("timber"), bevel=0.02, seg=1, wonk=0.02))
        parts.append(cbox("brace", (0.14, 0.14, 1.2), (x - 0.4 * (1 if x > 0 else -1), 0, 3.95), M("timber"), rot=(0, (0.8 if x > 0 else -0.8), 0)))
    parts.append(box("beam", (4.2, 0.3, 0.3), (0, 0, 4.4), M("timber"), bevel=0.02, seg=1))
    parts.append(box("beam_snow", (4.1, 0.26, 0.04), (0, 0, 4.7), M("snow")))
    icicles(parts, (-1.6, -0.15), (1.6, -0.15), 4.4, maxlen=0.2, seed=120, density=3)
    parts.append(cyl("rope", 0.02, 1.4, (0.3, 0, 3.0), M("sacking"), verts=5))
    parts.append(torus("noose", 0.14, 0.025, (0.3, 0, 2.86), M("sacking"), rot=(math.pi / 2, 0, 0), seg=10, mseg=4))
    parts.append(box("placard_post", (0.12, 0.12, 2.2), (2.8, -0.5, 0), M("wood_dark")))
    parts.append(box("placard", (0.9, 0.05, 0.6), (2.8, -0.58, 1.6), M("paper_old")))
    parts.append(box("placard_snow", (0.85, 0.06, 0.03), (2.8, -0.58, 2.2), M("snow")))
    for sx in (-0.22, 0.22):
        parts.append(cbox("ladder", (0.07, 0.07, 4.6), (-0.8 + sx, -0.9, 2.15), M("wood"), rot=(math.radians(-12), 0, 0)))
    for k in range(10):
        parts.append(box("lrung", (0.5, 0.05, 0.05), (-0.8, -0.95 + k * 0.085, 0.35 + k * 0.42), M("wood")))
    export("gallows", join(parts, "gallows"), box("c", (4.4, 1.4, 4.7), (0, 0, 0)))


# ------------------------------------------------------------------ CITY WALLS, GATES, THE COLLEGIUM, STREET GUTTERS
def city_tower():
    """Wall tower (baszta) of the city ring: a square brick tower on a battered stone base, arrow loops, a band of
    machicolation corbels, a tiled pyramid roof under snow. Outer face at -Y; wawel_wall segments butt its sides."""
    reset()
    parts = []
    S, H = 7.0, 13.0
    base = box("batter", (S + 0.8, S + 0.8, 3.0), (0, 0, 0), M("stone"), wonk=0.02)
    edit_verts(base, lambda co: (setattr(co, "x", co.x * (0.94 if co.z > 1.5 else 1.0)), setattr(co, "y", co.y * (0.94 if co.z > 1.5 else 1.0))))
    parts.append(base)
    parts.append(box("shaft", (S, S, H - 3.0), (0, 0, 3.0), M("brick"), wonk=0.03))
    for face, plane in (("-Y", -S / 2), ("-X", -S / 2), ("+X", S / 2)):
        for zz in (5.0, 8.5):
            parts.append(fbox("loop", face, plane, 0.0, 0.01, zz, 0.2, 0.03, 1.2, M("void")))
            parts.append(fbox("loop_x", face, plane, 0.0, 0.015, zz + 0.5, 0.5, 0.03, 0.14, M("void")))
    parts.append(box("band", (S + 0.3, S + 0.3, 0.25), (0, 0, 3.0), M("stone")))
    for face, plane in (("-Y", -S / 2), ("+Y", S / 2), ("-X", -S / 2), ("+X", S / 2)):
        for k in range(4):
            parts.append(fbox("corbel", face, plane, -S / 2 + 0.9 + k * 1.75, 0.2, H - 0.6, 0.3, 0.4, 0.6, M("stone")))
    parts.append(box("parapet", (S + 0.6, S + 0.6, 0.9), (0, 0, H), M("brick")))
    parts.append(box("par_snow", (S + 0.5, S + 0.5, 0.04), (0, 0, H + 0.9), M("snow")))
    parts.append(pyramid("roof", (S + 1.0, S + 1.0, 5.0), (0, 0, H + 0.9), M("tile_dark"), apex=0.15))
    sn = cap_snow("roof_snow", lambda: pyramid("tmp", (S + 1.0, S + 1.0, 5.0), (0, 0, H + 0.9), None, apex=0.15), minz=0.3, thick=0.06, cell=0.9, bare=0.15, slide=0.15)
    if sn:
        parts.append(sn)
    parts.append(cyl("finial", 0.08, 1.2, (0, 0, H + 5.9), M("iron"), verts=6, r2=0.02))
    for s in (-1, 1):
        icicles(parts, (-S / 2, s * (S / 2 + 0.45)), (S / 2, s * (S / 2 + 0.45)), H + 0.9, maxlen=0.4, seed=5 + s)
    export("city_tower", join(parts, "city_tower"), box("c", (S + 0.8, S + 0.8, H + 1.0), (0, 0, 0)))


def florian_gate():
    """St Florian's Gate: a tall Gothic gate tower on the north wall, a pointed passage straight through (walkable),
    stone lower storeys, brick above with blind niches, the Piast eagle relief, a Baroque copper helm with a
    lantern, ribs and snow. Outside (towards the Barbican) at -Y."""
    reset()
    parts, col = [], []
    S, H = 10.0, 22.0
    gw, gh = 3.8, 3.8 + 2.4
    parts.append(facade("front", M("stone"), "-Y", -S / 2, -S / 2, S / 2, 0.0, 7.0, [(0.0, 0.0, gw, gh, "pointed")], depth=S, back=False))
    parts.append(facade("back", M("stone"), "+Y", S / 2, -S / 2, S / 2, 0.0, 7.0, [(0.0, 0.0, gw, gh, "pointed")], depth=0.01, back=False))
    voussoirs(parts, "-Y", -S / 2, 0.0, gh - gw * 0.866, gw, 0.45, M("stone_pale"), shape="pointed", n=10, proud=0.12, key=0.1)
    voussoirs(parts, "+Y", S / 2, 0.0, gh - gw * 0.866, gw, 0.45, M("stone_pale"), shape="pointed", n=10, proud=0.12, key=0.1)
    parts.append(box("slab", (S, S, 0.3), (0, 0, 6.8), M("stone")))
    parts.append(box("upper", (S - 0.4, S - 0.4, H - 7.0), (0, 0, 7.0), M("brick")))
    for face, plane in (("-Y", -S / 2 + 0.2), ("+Y", S / 2 - 0.2), ("-X", -S / 2 + 0.2), ("+X", S / 2 - 0.2)):
        for a in (-2.6, 0.0, 2.6):
            parts.append(slab("niche", outline(a, 12.5, 1.4, 5.5, "pointed"), face, plane, 0.0, 0.03, M("plaster_white")))
        parts.append(fbox("band", face, plane, 0.0, 0.1, 11.8, S, 0.2, 0.25, M("stone")))
        parts.append(fbox("band_snow", face, plane, 0.0, 0.1, 12.05, S - 0.1, 0.2, 0.03, M("snow")))
    parts.append(fbox("eagle_plate", "-Y", -S / 2, 0.0, 0.1, 8.0, 2.2, 0.15, 2.6, M("stone_pale")))
    parts.append(blob("eagle", (1.4, 0.2, 1.6), (0, -S / 2 - 0.25, 8.4), M("stone_pale"), subsurf=1))
    for sx in (-1, 1):
        parts.append(taper_box("butt", (1.2, 1.2, 12.0), (sx * (S / 2 + 0.3), -S / 2 + 0.3, 0), M("brick"), top=0.5))
    parts.append(box("parapet", (S + 0.6, S + 0.6, 1.0), (0, 0, H), M("brick")))
    parts.append(box("par_snow", (S + 0.5, S + 0.5, 0.04), (0, 0, H + 1.0), M("snow")))
    icicles(parts, (-S / 2, -S / 2 - 0.35), (S / 2, -S / 2 - 0.35), H + 1.0, maxlen=0.5, seed=13)
    # the Baroque helm
    z = H + 1.0
    parts.append(pyramid("helm_base", (S - 0.8, S - 0.8, 2.6), (0, 0, z), M("patina"), apex=2.6))
    parts.append(cyl("helm_drum", 2.4, 2.4, (0, 0, z + 2.6), M("patina"), verts=12))
    parts.append(sphere("helm_bulb", 2.9, (0, 0, z + 6.2), M("patina"), seg=16, rings=10, zscale=0.9))
    dome_ribs(parts, 0, 0, z + 6.2, 2.9, n=8, zscale=0.9, mat=M("gold", 0.35), z_from=-0.5, width=0.05)
    sn = cap_snow("helm_snow", lambda: sphere("tmp", 2.9, (0, 0, z + 6.2), None, seg=16, rings=10, zscale=0.9), minz=0.6, thick=0.05, cell=0.5, bare=0.2)
    if sn:
        parts.append(sn)
    sn = cap_snow("base_snow", lambda: pyramid("tmp", (S - 0.8, S - 0.8, 2.6), (0, 0, z), None, apex=2.6), minz=0.3, thick=0.06, cell=0.8, bare=0.15, slide=0.1)
    if sn:
        parts.append(sn)
    parts.append(cyl("lantern", 0.8, 2.2, (0, 0, z + 8.7), M("patina"), verts=8))
    parts.append(sphere("lant_bulb", 0.9, (0, 0, z + 11.3), M("patina"), seg=10, rings=6))
    parts.append(cyl("spire", 0.2, 3.0, (0, 0, z + 12.0), M("gold", 0.35), verts=6, r2=0.02))
    visual = join(parts, "florian_gate")
    for sx in (-1, 1):
        col.append(box("c", ((S - gw) / 2, S, H + 1), (sx * (S / 2 - (S - gw) / 4), 0, 0)))
    col.append(box("c", (gw, S, H + 1 - gh), (0, 0, gh)))
    export("florian_gate", visual, join(col, "col"))


def barbican():
    """The Barbican: a round brick bastion (r 12 m) in front of St Florian's Gate, a walkable passage straight
    through along Y between two gate-necks, a crenellated wall-walk, seven slender turrets with conical caps,
    arrow loops in tiers; snow on every merlon. Origin at the centre; the gate-necks face -Y and +Y."""
    reset()
    parts, col = [], []
    R, T, H = 12.0, 2.2, 10.0
    n = 24
    for k in range(n):
        a = math.tau * (k + 0.5) / n
        c = Vector((math.cos(a), math.sin(a), 0)) * (R - T / 2)
        if abs(math.cos(a)) < 0.2:                 # passage gaps at +-Y
            continue
        L = 2 * R * math.tan(math.pi / n) + 0.1
        parts.append(cbox("ring", (L, T, H), (c.x, c.y, H / 2), M("brick"), rot=(0, 0, a + math.pi / 2)))
        col.append(cbox("c", (L, T, H), (c.x, c.y, H / 2), None, rot=(0, 0, a + math.pi / 2)))
        parts.append(cbox("merlon", (L * 0.55, 0.7, 1.0), (c.x * (R - 0.35) / (R - T / 2), c.y * (R - 0.35) / (R - T / 2), H + 0.5), M("brick"), rot=(0, 0, a + math.pi / 2)))
        parts.append(cbox("merlon_snow", (L * 0.5, 0.64, 0.04), (c.x * (R - 0.35) / (R - T / 2), c.y * (R - 0.35) / (R - T / 2), H + 1.02), M("snow"), rot=(0, 0, a + math.pi / 2)))
        parts.append(cbox("walk_snow", (L, T - 0.8, 0.05), (c.x * (R - T / 2 - 0.3) / (R - T / 2), c.y * (R - T / 2 - 0.3) / (R - T / 2), H + 0.02), M("snow"), rot=(0, 0, a + math.pi / 2)))
        for zz in (3.0, 6.5):
            cc = Vector((math.cos(a), math.sin(a), 0)) * (R + 0.01)
            parts.append(cbox("loop", (0.16, 0.05, 1.0), (cc.x, cc.y, zz), M("void"), rot=(0, 0, a + math.pi / 2)))
    parts.append(cyl("batter", R + 0.8, 1.6, (0, 0, 0), M("stone"), verts=24, r2=R + 0.1))
    for sy in (-1, 1):                               # gate-necks
        y0 = sy * (R + 1.0)
        for sx in (-1, 1):
            parts.append(box("neck", (1.8, 4.0, H + 2.0), (sx * 2.6, y0, 0), M("brick")))
            col.append(box("c", (1.8, 4.0, H + 2.0), (sx * 2.6, y0, 0)))
        parts.append(box("neck_top", (7.0, 4.0, 3.0), (0, y0, H - 1.0), M("brick")))
        parts.append(box("neck_snow", (6.9, 3.9, 0.05), (0, y0, H + 2.0), M("snow")))
        parts.append(arch("neck_arch", 3.4, 5.2, 4.2, (0, y0, 0), M("void"), bevel=0))
        voussoirs(parts, "-Y" if sy < 0 else "+Y", sy * (R + 3.0), 0.0, 3.5, 3.4, 0.4, M("stone_pale"), n=9, proud=0.1)
        parts.append(pyramid("neck_roof", (7.4, 4.4, 2.6), (0, y0, H + 2.0), M("tile_dark"), apex=0.1))
    for k in range(7):
        a = math.tau * (k + 0.5) / 7 + 0.2
        c = Vector((math.cos(a), math.sin(a), 0)) * (R + 0.3)
        if abs(math.cos(a)) < 0.3:
            continue
        parts.append(cyl("turret", 1.1, 4.0, (c.x, c.y, H), M("brick"), verts=10))
        parts.append(cyl("turret_cap", 1.4, 3.6, (c.x, c.y, H + 4.0), M("tile_dark"), verts=10, r2=0.05))
        parts.append(cyl("turret_snow", 1.2, 1.6, (c.x, c.y, H + 4.6), M("snow"), verts=10, r2=0.35))
    parts.append(cyl("court_snow", R - T, 0.03, (0, 0, 0), M("snow_dirty"), verts=24))
    visual = join(parts, "barbican")
    export("barbican", visual, join(col, "col"))


def collegium_maius():
    """Collegium Maius, the university's Gothic college (c. 1500): four brick wings round an arcaded courtyard,
    stone window frames with crossed mullions, a stepped gable and an oriel on the street front, a gate passage
    from the street (-Y) into the courtyard. 20 x 28 m."""
    reset()
    parts, col = [], []
    W, D, H, T = 20.0, 28.0, 10.0, 5.0
    br, st = M("brick"), M("stone_pale")
    gw = 2.6
    # street wing (front) with the gate passage
    ops = [(0.0, 0.0, gw, 3.0 + 1.3, "round")] + [(x, zz, 1.1, 1.8, "rect") for zz in (1.6, 5.4) for x in (-7.0, -4.0, 4.0, 7.0)] + [(x, 5.4, 1.1, 1.8, "rect") for x in (-1.3, 1.3)]
    parts.append(facade("front", br, "-Y", -D / 2, -W / 2, W / 2, 0.0, H, ops, depth=REV, back=True))
    parts.append(box("front_mass", (W, T - REV, H), (0, -D / 2 + REV + (T - REV) / 2, 0), br))
    parts.append(slab("gate_void", outline(0.0, 0.0, gw, 4.3, "round"), "-Y", -D / 2, -T + 0.1, -T + 0.12, M("void")))
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", -D / 2, a, zb, w, h, sh, warm=RNG.random() < 0.5, surround="stone_pale", cross=True, mark=zb < 3)
    voussoirs(parts, "-Y", -D / 2, 0.0, 3.0, gw, 0.3, st, n=9, proud=0.08)
    col.append(box("c", ((W - gw) / 2, T, H), (-(gw / 2 + (W - gw) / 4), -D / 2 + T / 2, 0)))
    col.append(box("c", ((W - gw) / 2, T, H), ((gw / 2 + (W - gw) / 4), -D / 2 + T / 2, 0)))
    # side and back wings
    for sx in (-1, 1):
        parts.append(box("side", (T, D - 2 * T, H), (sx * (W / 2 - T / 2), 0, 0), br))
        col.append(box("c", (T, D - 2 * T, H), (sx * (W / 2 - T / 2), 0, 0)))
        for k in range(4):
            yy = -D / 2 + T + 2.0 + k * 4.2
            parts.append(fbox("sw", "-X" if sx < 0 else "+X", sx * W / 2, -yy if sx < 0 else yy, 0.02, 5.4, 1.0, 0.03, 1.8, M("glass_warm" if k % 2 else "glass")))
    parts.append(box("back", (W, T, H), (0, D / 2 - T / 2, 0), br))
    col.append(box("c", (W, T, H), (0, D / 2 - T / 2, 0)))
    # courtyard arcade (cloister) on the inner faces
    cw, cd = W - 2 * T, D - 2 * T
    for k in range(6):
        for (x, y) in [(-cw / 2 + 0.3 + k * (cw - 0.6) / 5, -cd / 2 + 1.4), (-cw / 2 + 0.3 + k * (cw - 0.6) / 5, cd / 2 - 1.4)]:
            parts.append(cyl("arc_col", 0.18, 3.2, (x, y, 0), st, verts=8))
    parts.append(box("gallery", (cw, 1.8, 0.4), (0, -cd / 2 + 0.9, 3.2), st))
    parts.append(box("gallery2", (cw, 1.8, 0.4), (0, cd / 2 - 0.9, 3.2), st))
    parts.append(box("gal_snow", (cw - 0.2, 1.7, 0.04), (0, -cd / 2 + 0.9, 3.6), M("snow")))
    parts.append(box("court_floor", (cw, cd, 0.03), (0, 0, 0), M("snow")))
    # roofs: a steep tiled roof on each wing with snow
    for (L_, W_, loc, ax) in ((W + 0.8, T + 1.0, (0, -D / 2 + T / 2, H), True), (W + 0.8, T + 1.0, (0, D / 2 - T / 2, H), True),
                              (D - 2 * T, T + 1.0, (-W / 2 + T / 2, 0, H), False), (D - 2 * T, T + 1.0, (W / 2 - T / 2, 0, H), False)):
        parts.append(roof("roof", L_, W_, 4.2, loc, M("tile_dark"), sag=0.06, flare=0.05, along_x=ax, courses=3, ridge=True))
        sn = roof_snow("roof_snow", L_, W_, 4.2, loc, sag=0.06, flare=0.05, along_x=ax, thick=0.07, cell=1.0, seed=int(loc[0] + loc[1]))
        if sn:
            parts.append(sn)
    icicles(parts, (-W / 2, -D / 2 - 0.5), (W / 2, -D / 2 - 0.5), H - 0.02, seed=17, maxlen=0.5)
    # stepped gable on the street end and a stone oriel
    for k in range(5):
        zz = H + 4.2 * k / 5
        hw = W / 2 * (1 - k / 5)
        for sx in (-1, 1):
            parts.append(box("step", (0.8, 0.5, 4.2 / 5), (sx * (hw - 0.4), -D / 2 + 0.25, zz), br))
            parts.append(box("step_snow", (0.75, 0.45, 0.035), (sx * (hw - 0.4), -D / 2 + 0.25, zz + 4.2 / 5), M("snow")))
    parts.append(box("oriel", (2.2, 1.0, 2.6), (5.5, -D / 2 - 0.5, 4.2), st))
    parts.append(fbox("oriel_glass", "-Y", -D / 2 - 1.0, 5.5, 0.01, 4.6, 1.6, 0.02, 1.8, M("glass_stained")))
    parts.append(pyramid("oriel_corbel", (2.2, 1.0, 1.0), (5.5, -D / 2 - 0.5, 4.2), st))
    edit_verts(parts[-1], lambda co: setattr(co, "z", 2 * 4.2 - co.z))
    parts.append(pyramid("oriel_roof", (2.4, 1.2, 1.0), (5.5, -D / 2 - 0.5, 6.8), M("patina")))
    parts.append(box("oriel_snow", (1.6, 0.6, 0.12), (5.5, -D / 2 - 0.5, 7.2), M("snow"), bevel=0.05, seg=1))
    chimney(parts, -6.0, D / 2 - T / 2, H + 1.5, h=2.5)
    visual = join(parts, "collegium_maius")
    export("collegium_maius", visual, join(col, "col"))


def gutter_channel():
    """Street gutter (rynsztok), straight 4 m along X: two dressed lip stones standing 4 cm proud of the cobbles
    either side of a dished stone channel whose floor sits 3-4 cm below the lips, a thin dark wet strip of
    snow-melt (low roughness), skins of ice. Lies on the paving (y=0); no collision."""
    reset()
    parts = []
    L = 4.0
    for sy in (-1, 1):
        for k in range(5):
            x = -L / 2 + 0.4 + k * 0.8
            parts.append(box("lip", (0.78, 0.16, 0.045), (x, sy * 0.22, -0.005), M("stone")))
        b = box("dish", (L, 0.16, 0.02), (0, sy * 0.1, -0.005), M("stone_dark"))
        edit_verts(b, lambda co, sy=sy: setattr(co, "z", co.z - (0.012 if abs(co.y) < 0.05 else 0.0)))
        parts.append(b)
    parts.append(box("wet", (L, 0.18, 0.004), (0, 0, 0.004), M("water", 0.04)))
    rng = random.Random(5)
    for k in range(3):
        x = -L / 2 + 0.6 + k * 1.3 + rng.uniform(-0.2, 0.2)
        parts.append(box("ice", (rng.uniform(0.25, 0.5), 0.14, 0.004), (x, rng.uniform(-0.02, 0.02), 0.009), M("ice", 0.05)))
    parts.append(box("slush_l", (L, 0.12, 0.025), (0, -0.36, 0.0), M("snow_dirty")))
    export("gutter_channel", join(parts, "gutter_channel"), None)


def gutter_corner():
    """Mitred corner piece of the gutter: two 1 m arms (along +X and +Y from the origin, the turn's inside in the
    +X+Y quadrant) meeting on the mitre, same lip-dish-wet section as gutter_channel."""
    reset()
    parts = []
    def sw(co):
        co.x, co.y = co.y, co.x
    for arm in (0, 1):
        ps = [box("lip_in", (0.78, 0.16, 0.045), (0.22 + 0.39, 0.22, -0.005), M("stone")),
              box("lip_out", (1.3, 0.16, 0.045), (-0.3 + 0.65, -0.22, -0.005), M("stone")),
              box("dish", (1.0, 0.28, 0.015), (0.5, 0, -0.008), M("stone_dark")),
              box("wet", (1.0, 0.18, 0.004), (0.5, 0, 0.004), M("water", 0.04))]
        if arm:
            for o in ps:
                edit_verts(o, sw)
                o.data.flip_normals()
        parts += ps
    parts.append(box("mitre_wet", (0.28, 0.28, 0.004), (0, 0, 0.004), M("water", 0.04)))
    export("gutter_corner", join(parts, "gutter_corner"), None)


def gutter_slab():
    """Crossing slab: a 1.4 m worn stone slab bridging the gutter at a doorway or a lane crossing, the channel
    running on under it. Across X (the gutter runs along X)."""
    reset()
    parts = [box("slab", (1.4, 1.0, 0.08), (0, 0, 0.0), M("stone"), bevel=0.02, seg=1, wonk=0.02),
             box("slab_snow", (0.6, 0.5, 0.012), (0.2, 0.1, 0.08), M("snow_dirty"), wonk=0.04)]
    for sx in (-1, 1):
        parts.append(box("dark", (0.04, 0.18, 0.02), (sx * 0.71, 0, 0.0), M("void")))
    export("gutter_slab", join(parts, "gutter_slab"), None)


def gutter_outfall():
    """Drain / outfall where a street gutter ends: a stone drain box with an iron grate over a dark sump, the
    channel's last metre sloping into it, a fringe of icicles on the lip of the spout on the moat side (+X)."""
    reset()
    parts = [box("box", (0.9, 0.9, 0.12), (0, 0, -0.08), M("stone_dark"), bevel=0.02, seg=1),
             box("sump", (0.6, 0.6, 0.02), (0, 0, 0.02), M("void"))]
    for k in range(5):
        parts.append(box("grate", (0.04, 0.62, 0.03), (-0.24 + k * 0.12, 0, 0.03), M("iron")))
    parts.append(box("grate_x", (0.62, 0.04, 0.03), (0, 0, 0.035), M("iron")))
    parts.append(box("spout", (0.5, 0.3, 0.12), (0.6, 0, -0.1), M("stone")))
    icicles(parts, (0.85, -0.12), (0.85, 0.12), -0.1, maxlen=0.35, seed=3, density=20, gap=0.2)
    parts.append(box("ice_sheet", (0.6, 0.5, 0.01), (1.0, 0, -0.35), M("ice", 0.05), wonk=0.05))
    export("gutter_outfall", join(parts, "gutter_outfall"), None)


PASS3_BUILDS = [("city_tower", city_tower), ("florian_gate", florian_gate), ("barbican", barbican),
                ("collegium_maius", collegium_maius), ("gutter_corner", gutter_corner), ("gutter_slab", gutter_slab),
                ("gutter_outfall", gutter_outfall)]


# ------------------------------------------------------------------ GROUND SLABS, BACK YARDS AND CLIMBING (pass 4)
# Climbable geometry: extra collision boxes exported as climb_<kind>_<n>-colonly children of the asset (kinds: vault
# <= 1.2 m, mantle <= 2.4 m, ledge for sills, parapets, balconies and gallery decks, pipe for straight climbs such as
# drainpipes and ladders). outer_city.gd puts their StaticBody3D in group "climbable" with meta climb_kind.
def climb(kind, size, center, rot=(0, 0, 0)):
    o = cbox("climb", size, center, None, rot=rot)
    _CLIMB.append((kind, o))
    return o


def _tx_flags(g):
    """Worn sandstone flagstones: staggered rows of large slabs (5 across, 4 rows per 4 m, jittered widths), wide
    dark joints packed with grit and frost, polished wear paths, pale lime stains and chipped arrises."""
    cu, cv, iu, iv, par = g.cells(5.0, 4.0, 0.37)
    d = g.mn(g.mul(g.edge(cu), 4.0 / 5.0), g.mul(g.edge(cv), 1.0))
    joint = g.one_minus(g.smooth(d, 0.012, 0.03))
    chip = g.mul(g.smooth(g.noise(40, 40, 3, seed=92), 0.55, 0.7), g.one_minus(g.smooth(d, 0.03, 0.08)))
    r = g.white(iu, iv, 12.0)
    col = g.ramp(r, [(0.0, (0.36, 0.33, 0.28)), (0.35, (0.50, 0.45, 0.37)), (0.7, (0.60, 0.54, 0.44)), (1.0, (0.44, 0.39, 0.32))])
    grime = g.smooth(g.noise(8, 8, 5, 0.6, seed=98), 0.4, 0.75)
    col = g.mix(g.mul(grime, 0.5), col, (0.24, 0.22, 0.19))
    bed = g.noise(2.0, 20, 3, 0.5, dist=0.5, seed=93)
    col = g.mix(g.mul(g.sub(bed, 0.4), 0.4), col, (0.48, 0.43, 0.35))
    wear = g.smooth(g.noise(2, 6, 3, seed=94), 0.5, 0.7)
    col = g.mix(g.mul(wear, 0.25), col, (0.74, 0.70, 0.62))
    stain = g.smooth(g.noise(6, 6, 4, seed=95), 0.62, 0.72)
    col = g.mix(g.mul(stain, 0.35), col, (0.80, 0.78, 0.72))
    frost = g.smooth(g.noise(30, 30, 2, seed=96), 0.4, 0.7)
    jcol = g.mix(frost, (0.16, 0.15, 0.13), (0.62, 0.66, 0.72))
    col = g.mix(g.mul(chip, 0.5), col, (0.40, 0.36, 0.30))
    col = g.mix(joint, col, jcol)
    grain = g.noise(180, 180, 2, seed=97)
    h = g.sub(g.add(0.7, g.mul(grain, 0.1)), g.add(g.mul(joint, 0.6), g.mul(chip, 0.25)))
    h = g.add(h, g.mul(g.sub(r, 0.5), 0.08))
    rough = g.sub(g.add(0.72, g.mul(grain, 0.1)), g.mul(wear, 0.25))
    return col, rough, h, 0.02


def _tx_mud(g):
    """Frozen packed earth of alleys, yards and suburban roads: brown-grey clay with two cart ruts running along v,
    frozen puddles in the ruts and hollows (dark, glossy, low roughness), trodden straw, grit and snow in patches."""
    lumps = g.noise(5, 5, 4, 0.55, seed=101)
    fine = g.noise(150, 150, 2, seed=102)
    # ruts: two troughs along v at u = 0.3 and 0.7 of the repeat, wobbling
    wob = g.mul(g.sub(g.noise(1, 3, 2, seed=103), 0.5), 0.05)
    uu = g.add(g.u, wob)
    rut = g.mx(g.one_minus(g.smooth(g.m("ABSOLUTE", g.sub(uu, 0.3)), 0.01, 0.06)), g.one_minus(g.smooth(g.m("ABSOLUTE", g.sub(uu, 0.7)), 0.01, 0.06)))
    hollow = g.smooth(g.sub(0.5, lumps), 0.08, 0.2)
    pmask = g.smooth(g.noise(3, 9, 3, seed=107), 0.55, 0.65)
    puddle = g.mul(g.smooth(g.add(g.mul(rut, 0.7), g.mul(hollow, 0.6)), 0.6, 0.66), pmask)
    col = g.mix(g.smooth(lumps, 0.3, 0.7), (0.14, 0.11, 0.08), (0.38, 0.31, 0.22))
    col = g.mix(g.mul(g.smooth(g.noise(12, 12, 4, seed=108), 0.3, 0.7), 0.5), col, (0.28, 0.24, 0.20))
    col = g.mix(g.mul(rut, 0.45), col, (0.16, 0.12, 0.09))
    col = g.mix(g.mul(g.smooth(fine, 0.6, 0.8), 0.4), col, (0.44, 0.40, 0.34))
    straw = g.mul(g.smooth(g.noise(260, 12, 2, dist=0.6, seed=104), 0.72, 0.78), g.smooth(g.noise(4, 4, 3, seed=105), 0.5, 0.65))
    col = g.mix(g.mul(straw, 0.8), col, (0.62, 0.52, 0.30))
    snow = g.smooth(g.noise(7, 7, 4, seed=106), 0.6, 0.66)
    col = g.mix(g.mul(snow, g.one_minus(rut)), col, (0.78, 0.80, 0.84))
    col = g.mix(g.mul(puddle, 0.85), col, (0.12, 0.13, 0.15))
    h = g.sub(g.add(g.mul(lumps, 0.5), g.mul(fine, 0.1)), g.add(g.mul(rut, 0.35), g.mul(puddle, 0.1)))
    h = g.add(h, g.mul(snow, 0.15))
    rough = g.lerp(puddle, g.add(0.82, g.mul(fine, 0.1)), 0.12)
    return col, rough, h, 0.03


RECIPES.update({"flags": _tx_flags, "mud": _tx_mud})
TEXSPEC.update({"flags": (2048, 4.0), "mud": (2048, 4.0)})
HEIGHT_EXPORT.update({"flags", "mud"})
PAL.update({"flags": (1.0, 1.0, 1.0), "mud": (1.0, 1.0, 1.0), "mud_light": (1.0, 1.0, 1.0), "cobble_rough": (1.0, 1.0, 1.0)})
TEX_OF.update({"flags": "flags", "mud": "mud", "mud_light": "mud", "cobble_rough": "cobbles"})
TINT.update({"flags": (1, 1, 1), "mud": (1, 1, 1), "mud_light": (1.35, 1.3, 1.22), "cobble_rough": (0.74, 0.70, 0.66)})


def _slab(name, key, rut=0.0, jitter=0.004, sink=0.0, extra=None):
    """4 x 4 m tileable ground slab like ground_cobbles: top near z=0, texture exactly once across it."""
    reset()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=4, y_subdivisions=4, size=4.0, location=(0, 0, 0))
    top = _finish_prim(bpy.context.object, "top", M(key))
    _tag(top, mat=M(key), offset=(0.5, 0.5))
    rng = random.Random(len(name))
    def f(co):
        edge = abs(abs(co.x) - 2) < 1e-3 or abs(abs(co.y) - 2) < 1e-3
        if rut:
            for ux in (-0.8, 0.8):
                co.z -= rut * max(0.0, 1.0 - abs(co.x - ux) / 0.3)
        if not edge:
            co.z += rng.uniform(-jitter, jitter * 0.3) - sink
    edit_verts(top, f)
    parts = [top] + (extra() if extra else [])
    export(name, join(parts, name) if len(parts) > 1 else top, None)


def ground_flags(): _slab("ground_flags", "flags", jitter=0.003)
def ground_cobbles_lo(): _slab("ground_cobbles_lo", "cobble", jitter=0.006)
def ground_cobbles_rough(): _slab("ground_cobbles_rough", "cobble_rough", jitter=0.02, sink=0.01)
def ground_mud(): _slab("ground_mud", "mud", rut=0.05, jitter=0.015)
def ground_gravel(): _slab("ground_gravel", "mud_light", jitter=0.008)


def ground_planks():
    """Plank walkway for the deep-mud suburban roads: 4 m of boards on two sleepers, 1.2 m wide, top at 0.1 m."""
    reset()
    parts = []
    for sy in (-0.45, 0.45):
        parts.append(box("sleeper", (4.0, 0.14, 0.08), (0, sy, 0.0), M("timber")))
    for k in range(13):
        parts.append(box("board", (0.28, 1.2, 0.03), (-1.85 + k * 0.308, 0, 0.08), M("wood")))
    parts.append(box("snow", (1.4, 0.5, 0.012), (0.6, 0.2, 0.11), M("snow_dirty")))
    export("ground_planks", join(parts, "ground_planks"), None)


def snow_drift():
    """Snow drift banked against a wall: 4 m along X, its back flat to the wall at y=0, sloping out 0.9 m to -Y."""
    reset()
    bm = bmesh.new()
    rng = random.Random(7)
    rows = []
    for i in range(9):
        x = -2.0 + 0.5 * i
        h = 0.35 + 0.18 * math.sin(i * 1.3) + rng.uniform(-0.05, 0.05)
        if i in (0, 8):
            h = 0.05
        d = 0.5 + h * 1.2
        rows.append([bm.verts.new((x, 0.02, -0.02)), bm.verts.new((x, 0.02, h)), bm.verts.new((x, -d * 0.45, h * 0.75)), bm.verts.new((x, -d, -0.02))])
    for a, b in zip(rows, rows[1:]):
        for k in range(3):
            bm.faces.new((a[k], a[k + 1], b[k + 1], b[k]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _mesh_obj("drift", bm, M("snow"))
    for p in o.data.polygons:
        p.use_smooth = True
    export("snow_drift", o, None)


def ladder():
    """A timber ladder leaning on a wall (4.4 m, foot 1.1 m out at -Y): climbable (pipe)."""
    reset()
    parts = []
    ang = math.atan2(1.1, 4.3)
    for sx in (-0.24, 0.24):
        parts.append(cbox("rail", (0.07, 0.07, 4.45), (sx, -0.55, 2.15), M("wood"), rot=(-ang, 0, 0)))
    for k in range(13):
        t = (k + 0.5) / 13
        parts.append(box("rung", (0.52, 0.045, 0.045), (0, -1.1 + t * 1.1, t * 4.3), M("wood_dark")))
    parts.append(box("snow", (0.5, 0.06, 0.02), (0, -1.05, 0.45), M("snow")))
    climb("pipe", (0.7, 0.5, 4.4), (0, -0.55, 2.2), rot=(-ang, 0, 0))
    export("ladder", join(parts, "ladder"), None)


def low_wall():
    """Yard wall, 6 m along X, 1.1 m high (vault), rubble stone with a tile coping and snow."""
    reset()
    parts = [box("wall", (6.0, 0.5, 1.0), (0, 0, 0), M("stone_dark"), wonk=0.03),
             roof("coping", 6.1, 0.7, 0.18, (0, 0, 1.0), M("tile_dark"), sag=0.0, flare=0.0, cuts=3),
             box("snow", (5.9, 0.3, 0.05), (0, 0, 1.13), M("snow"), bevel=0.02, seg=1)]
    climb("vault", (6.0, 0.6, 1.15), (0, 0, 0.575))
    export("low_wall", join(parts, "low_wall"), None)


def water_butt():
    """Rain barrel under a downpipe, iced over (vault)."""
    reset()
    parts = [cyl("butt", 0.42, 1.0, (0, 0, 0), M("wood"), verts=12, r2=0.46),
             cyl("ice", 0.4, 0.02, (0, 0, 0.98), M("ice", 0.05), verts=12),
             cyl("snow", 0.3, 0.03, (0.05, 0.05, 1.0), M("snow"), verts=10)]
    for z in (0.15, 0.85):
        parts.append(cyl("hoop", 0.46, 0.05, (0, 0, z), M("iron"), verts=12))
    climb("vault", (0.9, 0.9, 1.02), (0, 0, 0.51))
    export("water_butt", join(parts, "water_butt"), None)


def yard_shed():
    """Lean-to shed for a back yard: board walls, a shingle roof falling from 2.6 m (back, +Y) to 2.1 m (front),
    snow on it; its roof is solid to stand on (mantle from the ground or from a crate)."""
    reset()
    parts = []
    W, D = 3.2, 2.4
    parts.append(box("walls", (W, D, 2.1), (0, 0, 0), M("timber"), wonk=0.03))
    parts.append(box("door", (0.8, 0.05, 1.8), (-0.6, -D / 2 - 0.02, 0), M("wood_dark")))
    r = box("roof", (W + 0.4, D + 0.5, 0.1), (0, 0, 2.1), M("shingle"))
    edit_verts(r, lambda co: setattr(co, "z", co.z + (co.y + D / 2) / D * 0.5))
    parts.append(r)
    s = box("roof_snow", (W + 0.3, D + 0.3, 0.06), (0, 0, 2.2), M("snow"), bevel=0.03, seg=1)
    edit_verts(s, lambda co: setattr(co, "z", co.z + (co.y + D / 2) / D * 0.5))
    parts.append(s)
    icicles(parts, (-W / 2, -D / 2 - 0.25), (W / 2, -D / 2 - 0.25), 2.08, maxlen=0.3, seed=21)
    c = box("c", (W, D, 2.1), (0, 0, 0))
    rc = climb("mantle", (W + 0.4, D + 0.5, 0.3), (0, 0, 2.3))
    edit_verts(rc, lambda co: setattr(co, "z", co.z + (co.y + D / 2) / D * 0.5))
    export("yard_shed", join(parts, "yard_shed"), c)


def yard_stair():
    """Outside timber stair (a courtyard gallery's access): 10 steps up the wall (+Y side against it) to a 3.4 m
    landing with a rail; the treads are solid (a ramp collider), the landing is a ledge."""
    reset()
    parts, col = [], []
    for k in range(10):
        parts.append(box("tread", (0.32, 1.0, 0.06), (-2.6 + k * 0.32, 0.0, 0.34 * (k + 1) - 0.06), M("wood")))
        parts.append(box("tread_snow", (0.2, 0.9, 0.015), (-2.6 + k * 0.32, 0.0, 0.34 * (k + 1)), M("snow_dirty")))
    parts.append(cbox("stringer", (3.6, 0.1, 0.25), (-1.15, -0.5, 1.7), M("timber"), rot=(0, math.atan2(-3.4, 3.2), 0)))
    parts.append(box("landing", (1.6, 1.2, 0.12), (1.2, 0.1, 3.3), M("wood")))
    for x in (0.45, 1.95):
        parts.append(box("post", (0.12, 0.12, 3.4), (x, -0.45, 0), M("timber")))
    parts.append(box("rail", (1.6, 0.06, 0.06), (1.2, -0.45, 4.3), M("wood")))
    parts.append(box("rail_snow", (1.5, 0.06, 0.02), (1.2, -0.45, 4.36), M("snow")))
    ramp = climb("mantle", (4.4, 1.0, 0.2), (-1.0, 0.0, 1.6), rot=(0, math.atan2(-3.4, 3.2) * 0.98, 0))
    climb("ledge", (1.6, 1.2, 0.12), (1.2, 0.1, 3.36))
    export("yard_stair", join(parts, "yard_stair"), box("c", (0.2, 0.2, 3.3), (1.95, 0.55, 0)))


def perch_ledge():
    """A timber hoarding balcony between two first-floor windows (1.6 m wide, 0.9 m out, deck at 4.3 m), with a
    board parapet to crouch behind: an eavesdropping perch. Wall-mounted: origin on the wall face at ground level,
    front at -Y."""
    reset()
    parts = []
    z = 4.3
    parts.append(box("deck", (1.6, 0.9, 0.08), (0, -0.45, z - 0.08), M("wood_dark")))
    for x in (-0.7, 0.7):
        parts.append(cbox("brace", (0.08, 0.08, 1.1), (x, -0.4, z - 0.5), M("timber"), rot=(math.radians(40), 0, 0)))
    parts.append(box("parapet", (1.6, 0.05, 0.7), (0, -0.88, z), M("wood")))
    for x in (-0.78, 0.78):
        parts.append(box("side", (0.05, 0.85, 0.7), (x, -0.45, z), M("wood")))
    parts.append(box("par_snow", (1.55, 0.06, 0.03), (0, -0.88, z + 0.7), M("snow")))
    icicles(parts, (-0.8, -0.9), (0.8, -0.9), z - 0.08, maxlen=0.3, seed=31, density=5)
    climb("ledge", (1.6, 0.9, 0.12), (0, -0.45, z - 0.06))
    climb("vault", (1.6, 0.08, 0.7), (0, -0.88, z + 0.35))
    export("perch_ledge", join(parts, "perch_ledge"), None)


def sien_passage():
    """A through-passage (sien) where an alley cuts a block: two tenement shoulders 8.6 m deep with a vaulted
    passage 2.4 m wide and 3.2 m high between them under a bridging upper storey, windows over the arch, a lantern,
    steps down into the yard at the back. Front (street) at -Y; walkable through."""
    reset()
    parts, col = [], []
    W, D, H = 3.6, 8.6, 10.4
    gw, gh = 2.4, 3.2
    parts.append(facade("front", M("plaster_grey"), "-Y", -D / 2, -W / 2, W / 2, 0.0, 4.2, [(0.0, 0.0, gw, gh, "round")], depth=D, back=False))
    parts.append(facade("back", M("plaster_grey"), "+Y", D / 2, -W / 2, W / 2, 0.0, 4.2, [(0.0, 0.0, gw, gh, "round")], depth=0.01, back=False))
    voussoirs(parts, "-Y", -D / 2, 0.0, gh - gw / 2, gw, 0.3, M("stone"), n=9, proud=0.08, key=0.12)
    parts.append(box("upper", (W, D, H - 4.2), (0, 0, 4.2), M("plaster_grey")))
    for zz in (5.2, 8.4):
        parts.append(fbox("win", "-Y", -D / 2, 0.0, 0.01, zz, 0.8, 0.03, 1.4, M("glass_warm" if zz < 6 else "glass")))
        parts.append(fbox("sill", "-Y", -D / 2, 0.0, 0.06, zz - 0.1, 1.0, 0.12, 0.1, M("stone")))
        parts.append(fbox("sill_snow", "-Y", -D / 2, 0.0, 0.06, zz, 0.95, 0.1, 0.025, M("snow")))
    parts.append(roof("roof", D + 0.8, W + 0.6, 2.4, (0, 0, H), M("tile_dark"), along_x=False, sag=0.03, flare=0.05, cuts=3))
    sn = roof_snow("roof_snow", D + 0.8, W + 0.6, 2.4, (0, 0, H), along_x=False, sag=0.03, flare=0.05, cuts=3, thick=0.06, cell=0.8, seed=41)
    if sn:
        parts.append(sn)
    parts.append(box("floor", (gw, D, 0.04), (0, 0, 0), M("flags")))
    parts.append(box("lantern", (0.2, 0.2, 0.3), (0, -D / 2 + 0.6, gh - 0.5), M("gold", 0.3, emit=(1.0, 0.7, 0.35), emit_strength=3.0)))
    for sx in (-1, 1):
        col.append(box("c", ((W - gw) / 2, D, H), (sx * (gw / 2 + (W - gw) / 4), 0, 0)))
    col.append(box("c", (gw, D, H - gh), (0, 0, gh)))
    export("sien_passage", join(parts, "sien_passage"), join(col, "col"))


PASS4_BUILDS = [("ground_flags", ground_flags), ("ground_cobbles_lo", ground_cobbles_lo), ("ground_cobbles_rough", ground_cobbles_rough), ("ground_mud", ground_mud),
                ("ground_gravel", ground_gravel), ("ground_planks", ground_planks), ("snow_drift", snow_drift),
                ("ladder", ladder), ("low_wall", low_wall), ("water_butt", water_butt), ("yard_shed", yard_shed),
                ("yard_stair", yard_stair), ("perch_ledge", perch_ledge), ("sien_passage", sien_passage)]


# ------------------------------------------------------------------ THE FINALE NIGHT (pass 5): bathhouse, the kingpin's
# warehouse and townhouse, carpenter's yard, guillotine, torches, riot and fire damage
def extra(name, objs):
    """Keep objs as a separate child node called `name` (not joined into the visual): runtime-tagged parts such as
    the cargo hook or the flammable bales."""
    o = join(objs, name) if len(objs) > 1 else objs[0]
    o.name = name
    _EXTRA.append((name, o))
    return o


def mark_named(name, loc, rot_z=0.0):
    """An anchor empty with an exact name (Door_front, Gate, ...)."""
    _MARKS.append(["!" + name, Vector(loc), rot_z])


def bathhouse():
    """Laznia: a low vaulted bathhouse by the river, 14 x 10 m: brick walls with small high windows, a barrel
    vault under tiles and snow (the snow thinner over the warm vault), a squat chimney that steams, a door with
    a bench and a bucket. Interior footprint 12 x 8 m (walls 1 m thick), door at the middle of the -Y front."""
    reset()
    parts = []
    W, D, H = 14.0, 10.0, 3.4
    ops = [(0.0, 0.0, 1.3, 2.2, "rect")] + [(x, 2.2, 0.8, 0.6, "seg") for x in (-4.6, -2.4, 2.4, 4.6)]
    y = front_block(parts, W, D, H, M("brick"), ops)
    parts.append(fbox("door", "-Y", y, 0.0, -REV + 0.05, 0.0, 1.26, 0.06, 2.16, M("wood_dark")))
    parts.append(fbox("door_lintel", "-Y", y, 0.0, 0.05, 2.2, 1.7, 0.12, 0.25, M("stone")))
    mark_named("Door_front", _wp("-Y", y, 0.0, 0.0, 0.05))
    for (a, zb, w, h, sh) in ops[1:]:
        win_unit(parts, "-Y", y, a, zb, w, h, sh, warm=True, surround=None, head=None, cross=False)
    parts.append(box("plinth", (W + 0.1, D + 0.1, 0.5), (0, 0, 0), M("stone_dark")))
    vault = cyl("vault", D / 2 + 0.4, W + 0.6, (0, 0, H), M("tile_dark"), verts=16, rot=(0, math.pi / 2, 0), center=True)
    bm = bmesh.new()
    bm.from_mesh(vault.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < H - 0.01], context="VERTS")
    bm.to_mesh(vault.data)
    bm.free()
    parts.append(vault)
    sn = cap_snow("vault_snow", lambda: cyl("tmp", D / 2 + 0.4, W + 0.6, (0, 0, H), None, verts=16, rot=(0, math.pi / 2, 0), center=True), minz=0.55, thick=0.04, cell=0.8, bare=0.35)
    if sn:
        parts.append(sn)
    for sx in (-1, 1):
        gable_slab(parts, "-X" if sx < 0 else "+X", sx * W / 2, -D / 2, D / 2, H, D / 2, M("brick"), thick=0.3)
    parts.append(box("chimney", (1.1, 1.1, 3.0), (3.5, 2.0, H + 3.0), M("brick"), bevel=0.02, seg=1))
    parts.append(box("chim_cap", (1.3, 1.3, 0.15), (3.5, 2.0, H + 6.0), M("stone_dark")))
    mark("Chimney", (3.5, 2.0, H + 6.3))
    parts.append(box("bench", (1.6, 0.4, 0.08), (-2.0, y - 0.35, 0.45), M("wood")))
    for x in (-2.6, -1.4):
        parts.append(box("bench_leg", (0.08, 0.35, 0.45), (x, y - 0.35, 0), M("wood")))
    parts.append(cyl("bucket", 0.18, 0.3, (2.0, y - 0.4, 0), M("wood"), verts=10))
    parts.append(box("wet", (2.0, 1.4, 0.01), (0, y - 0.8, 0), M("ice", 0.05)))
    icicles(parts, (-W / 2, y - 0.3), (W / 2, y - 0.3), H, maxlen=0.5, seed=51)
    export("bathhouse", join(parts, "bathhouse"), box("c", (W, D, H + D / 2), (0, 0, 0)))


def kingpin_warehouse():
    """The kingpin's store on the quay: a brick ground floor and a boarded upper floor, a wide loading door, an
    upper hatch with a hoist beam and the cargo hook on its rope (separate node CargoHook: rig, drop), casks and
    straw-bound bales stacked outside (Bales: flammable), a small office with a lit window on the side, a back
    door to the alley. 16 x 12 m, front (river side) at -Y."""
    reset()
    parts, col = [], []
    W, D, GF, H = 16.0, 12.0, 4.0, 8.0
    ops = [(-2.0, 0.0, 3.6, 3.4, "rect"), (4.5, 1.4, 1.0, 1.2, "rect")]
    y = front_block(parts, W, D, GF, M("brick"), ops)
    parts.append(slab("load_dark", outline(-2.0, 0.0, 3.6, 3.4), "-Y", y, -REV - 0.5, -REV - 0.48, M("void")))
    for sx in (-1, 1):
        leaf = fbox("leaf", "-Y", y, -2.0 + sx * 0.9, -REV + 0.05, 0.0, 1.76, 0.07, 3.36, M("wood_dark"))
        _swing(leaf, _wp("-Y", y, -2.0 + sx * 1.8, 0, -REV + 0.05), math.radians(100) * (1 if sx < 0 else -1) * -1)
        parts.append(leaf)
    win_unit(parts, "-Y", y, 4.5, 1.4, 1.0, 1.2, "rect", bars=True, surround=None, head="lintel")
    uops = [(-2.0, GF + 0.3, 2.0, 2.2, "rect"), (4.5, GF + 1.0, 0.9, 1.1, "rect"), (-6.0, GF + 1.0, 0.9, 1.1, "rect")]
    y2 = front_block(parts, W, D, H - GF, M("timber"), uops, z0=GF)
    parts.append(slab("hatch_dark", outline(-2.0, GF + 0.3, 2.0, 2.2), "-Y", y2, -REV - 0.4, -REV - 0.38, M("void")))
    for (a, zb, w, h, sh) in uops[1:]:
        win_unit(parts, "-Y", y2, a, zb, w, h, sh, surround=None, head=None, warm=False)
    for k in range(12):
        parts.append(fbox("batten", "-Y", y2, -W / 2 + 0.2 + k * (W - 0.4) / 11, 0.03, GF, 0.06, 0.05, H - GF, M("wood_dark")))
    col.append(box("c", (W, D, H), (0, 0, 0)))
    _roof_set(parts, W + 0.8, D + 1.0, 4.0, (0, 0, H), M("tile_dark"), courses=4, seed=61)
    # hoist beam over the hatch and the hook on its rope
    parts.append(box("hoist", (0.3, 2.4, 0.3), (-2.0, y2 - 1.0, GF + 3.3), M("timber")))
    parts.append(cbox("hoist_brace", (0.15, 1.4, 0.15), (-2.0, y2 - 0.5, GF + 2.8), M("timber"), rot=(math.radians(45), 0, 0)))
    parts.append(cyl("pulley", 0.18, 0.1, (-2.0, y2 - 2.0, GF + 3.15), M("iron"), verts=10, rot=(0, math.pi / 2, 0), center=True))
    hook = [cyl("hook_rope", 0.02, 3.4, (-2.0, y2 - 2.0, GF - 0.35), M("sacking"), verts=5),
            torus("hook", 0.14, 0.03, (-2.0, y2 - 2.0, GF - 0.45), M("iron"), rot=(math.pi / 2, 0, 0), seg=10, mseg=4),
            box("hook_block", (0.12, 0.12, 0.25), (-2.0, y2 - 2.0, GF - 0.3), M("iron"))]
    extra("CargoHook", hook)
    # office annex on +X with its lit window
    parts.append(box("office", (3.0, 4.0, 3.0), (W / 2 + 1.5, -1.0, 0), M("plaster_grey")))
    parts.append(box("office_win", (0.05, 1.0, 1.0), (W / 2 + 3.02, -1.0, 1.2), M("glass_warm")))
    parts.append(fbox("office_win_f", "-Y", -3.0, W / 2 + 1.5, 0.02, 1.2, 1.0, 0.03, 1.0, M("glass_warm")))
    parts.append(roof("office_roof", 3.4, 4.4, 0.8, (W / 2 + 1.5, -1.0, 3.0), M("shingle"), along_x=False, sag=0.02, flare=0.0, cuts=3))
    sn = roof_snow("office_snow", 3.4, 4.4, 0.8, (W / 2 + 1.5, -1.0, 3.0), along_x=False, sag=0.02, flare=0.0, cuts=3, thick=0.05, cell=0.6, seed=62)
    if sn:
        parts.append(sn)
    col.append(box("c", (3.0, 4.0, 3.0), (W / 2 + 1.5, -1.0, 0)))
    # back door to the alley (+Y)
    parts.append(fbox("back_door", "+Y", D / 2, 5.0, 0.03, 0.0, 1.1, 0.06, 2.1, M("wood_dark")))
    mark_named("Door_back", _wp("+Y", D / 2, 5.0, 0.0, 0.05), math.pi)
    mark_named("Door_front", _wp("-Y", y, -2.0, 0.0, 0.05))
    # casks (poisonable) and bales (flammable) on the quay
    casks = []
    for k in range(6):
        casks.append(cyl("cask", 0.45, 0.9, (-7.0 + (k % 3) * 0.95, y - 1.0 - (k // 3) * 0.95, 0), M("wood"), verts=12, r2=0.45))
        casks.append(cyl("cask_snow", 0.36, 0.03, (-7.0 + (k % 3) * 0.95, y - 1.0 - (k // 3) * 0.95, 0.9), M("snow"), verts=10))
    extra("Casks", casks)
    col.append(box("c", (3.0, 2.0, 0.9), (-6.05, y - 1.5, 0)))
    bales = []
    for k in range(5):
        bx = 2.0 + (k % 3) * 1.25
        bz = 0.0 if k < 3 else 0.8
        bales.append(box("bale", (1.2, 0.8, 0.8), (bx + (0.6 if k >= 3 else 0), y - 1.2, bz), M("hay"), bevel=0.06, seg=1))
        bales.append(box("bale_band", (0.06, 0.82, 0.82), (bx + (0.6 if k >= 3 else 0) - 0.3, y - 1.2, bz - 0.01), M("sacking")))
    extra("Bales", bales)
    col.append(box("c", (3.8, 0.9, 1.6), (3.25, y - 1.2, 0)))
    parts.append(box("snow_drift", (W, 0.8, 0.2), (0, D / 2 + 0.4, 0), M("snow"), bevel=0.15, seg=2, wonk=0.1))
    climb("pipe", (0.3, 0.3, H), (W / 2 - 0.2, y - 0.1, H / 2))
    export("kingpin_warehouse", join(parts, "kingpin_warehouse"), join(col, "col"))


def carpenter_yard():
    """Carpenter's yard (ciesla) outside Kleparz: stacks of squared timber and planks under snow, a sawpit with a
    log on its trestles and the long two-man saw, a work shed, shavings (flammable)."""
    reset()
    parts, col = [], []
    for k in range(3):
        for j in range(4):
            parts.append(box("timber", (5.0, 0.3, 0.3), (-1.0, -3.0 + k * 1.2 + (j % 2) * 0.35, j * 0.32), M("timber")))
        parts.append(box("timber_snow", (4.9, 0.8, 0.05), (-1.0, -2.8 + k * 1.2, 1.28), M("snow")))
        col.append(box("c", (5.0, 0.9, 1.3), (-1.0, -2.8 + k * 1.2, 0)))
    parts.append(box("pit_rim", (4.0, 1.4, 0.2), (3.0, 2.0, 0), M("wood_dark")))
    parts.append(box("pit_dark", (3.6, 1.0, 0.02), (3.0, 2.0, 0.19), M("void")))
    for x in (1.6, 4.4):
        parts.append(box("trestle", (0.2, 1.4, 0.2), (x, 2.0, 0.2), M("timber")))
    parts.append(cyl("log", 0.3, 4.4, (3.0, 2.0, 0.7), M("log"), verts=10, rot=(0, math.pi / 2, 0), center=True))
    parts.append(box("saw", (0.04, 0.02, 2.2), (3.4, 2.0, 0.0), M("iron")))
    parts.append(box("saw_h", (0.5, 0.04, 0.04), (3.4, 2.0, 2.2), M("wood")))
    col.append(box("c", (4.0, 1.4, 1.0), (3.0, 2.0, 0)))
    parts.append(box("shed", (3.0, 2.0, 2.2), (-4.5, 3.0, 0), M("timber")))
    r = box("shed_roof", (3.4, 2.6, 0.1), (-4.5, 3.0, 2.2), M("shingle"))
    edit_verts(r, lambda co: setattr(co, "z", co.z + (co.y - 1.7) * 0.25))
    parts.append(r)
    parts.append(box("shed_snow", (3.3, 2.4, 0.05), (-4.5, 3.0, 2.3), M("snow")))
    col.append(box("c", (3.0, 2.0, 2.2), (-4.5, 3.0, 0)))
    climb("mantle", (3.4, 2.6, 0.3), (-4.5, 3.0, 2.35))
    extra("Shavings", [box("shavings", (1.6, 1.2, 0.2), (1.0, 3.2, 0), M("straw"), bevel=0.1, seg=2, wonk=0.1)])
    export("carpenter_yard", join(parts, "carpenter_yard"), join(col, "col"))


def guillotine():
    """Guillotine on a scaffold: a plank platform with steps, two grooved uprights and a crossbar, the angled
    blade in its weighted block held up by a rope to a cleat, the two-part lunette and a tilting bench, a basket.
    (An import of the Revolution for the finale, not a Krakow fixture.)"""
    reset()
    parts = []
    parts.append(box("platform", (4.0, 3.0, 1.4), (0, 0, 0), M("wood_dark")))
    for k in range(10):
        parts.append(box("plank", (0.38, 3.0, 0.03), (-1.8 + k * 0.4, 0, 1.4), M("wood")))
    for k in range(5):
        parts.append(box("step", (1.2, 0.35, 0.28 * (k + 1)), (-1.2, 1.5 + 0.35 * (4 - k) + 0.175, 0), M("wood")))
    for sx in (-0.4, 0.4):
        parts.append(box("upright", (0.16, 0.2, 4.0), (sx + 0.9, -0.6, 1.43), M("wood_dark")))
    parts.append(box("crossbar", (1.2, 0.3, 0.25), (0.9, -0.6, 5.43), M("wood_dark")))
    blade = [box("weight", (0.66, 0.16, 0.4), (0.9, -0.6, 4.4), M("iron")),
             wedge("blade", (0.64, 0.05, 0.4), (0.9, -0.6, 4.0), M("iron"))]
    edit_verts(blade[1], lambda co: setattr(co, "z", co.z + (co.x - 0.9) * 0.45))
    parts += blade
    parts.append(cyl("rope", 0.012, 1.2, (0.9, -0.6, 4.8), M("sacking"), verts=5))
    parts.append(box("cleat", (0.06, 0.1, 0.2), (1.35, -0.5, 2.6), M("iron")))
    parts.append(box("lunette_lo", (0.64, 0.1, 0.16), (0.9, -0.6, 1.9), M("wood")))
    parts.append(box("lunette_hi", (0.64, 0.1, 0.16), (0.9, -0.6, 2.06), M("wood")))
    parts.append(box("bench", (0.4, 1.8, 0.1), (0.9, 0.4, 1.8), M("wood")))
    parts.append(box("bench_leg", (0.3, 0.1, 0.4), (0.9, 1.2, 1.43), M("wood_dark")))
    parts.append(cyl("basket", 0.3, 0.35, (0.9, -1.1, 1.43), M("straw"), verts=10))
    parts.append(box("snow", (1.6, 1.0, 0.03), (-1.0, -0.6, 1.43), M("snow")))
    export("guillotine", join(parts, "guillotine"), box("c", (4.0, 3.0, 1.4), (0, 0, 0)))


def guillotine_parts():
    """The guillotine unbuilt: its timbers, the crated blade and the bench roped on a cart."""
    reset()
    parts = []
    parts.append(box("bed", (1.4, 3.0, 0.15), (0, 0, 0.6), M("wood")))
    for sx in (-1, 1):
        parts.append(cyl("wheel", 0.6, 0.12, (sx * 0.8, 0.3, 0.6), M("wood_dark"), verts=14, rot=(0, math.pi / 2, 0), center=True))
    for k in range(4):
        parts.append(box("beam", (0.2, 3.2, 0.2), (-0.45 + k * 0.3, 0, 0.75), M("wood_dark")))
    parts.append(box("crate", (0.9, 0.6, 0.5), (0.1, -0.8, 0.95), M("wood")))
    parts.append(box("bench", (0.4, 1.8, 0.1), (0.2, 0.6, 0.95), M("wood")))
    for y in (-1.2, 0.0, 1.2):
        parts.append(box("rope", (1.45, 0.04, 0.04), (0, y, 1.1), M("sacking")))
    parts.append(cyl("shaft", 0.05, 1.8, (0, -2.3, 0.5), M("wood_dark"), verts=6, rot=(math.pi / 2 - 0.2, 0, 0), center=True))
    parts.append(box("snow", (1.2, 2.6, 0.03), (0, 0, 0.97), M("snow")))
    export("guillotine_parts", join(parts, "guillotine_parts"), box("c", (1.8, 3.2, 1.2), (0, 0, 0)))


def torch():
    """A pitch-wrapped torch on a stick (0.9 m, origin at the grip end's bottom), its tip glowing (emissive)."""
    reset()
    parts = [cyl("stick", 0.025, 0.7, (0, 0, 0), M("wood_dark"), verts=6, r2=0.02),
             cyl("wrap", 0.05, 0.22, (0, 0, 0.66), M("soot"), verts=8, r2=0.06),
             blob("flame", (0.12, 0.12, 0.22), (0, 0, 0.84), M("flame", 0.9, emit=(1.0, 0.55, 0.12), emit_strength=9.0))]
    mark("Furnace", (0, 0, 0.95))
    export("torch", join(parts, "torch"), None)


def torch_wall():
    """A torch in a wrought-iron wall bracket (origin on the wall face, front -Y), tip glowing."""
    reset()
    parts = [box("plate", (0.12, 0.03, 0.3), (0, -0.015, 1.9), M("iron")),
             cbox("arm", (0.03, 0.35, 0.03), (0, -0.17, 2.05), M("iron"), rot=(math.radians(-30), 0, 0)),
             torus("ring", 0.05, 0.012, (0, -0.33, 2.15), M("iron"), seg=10, mseg=4),
             cbox("stick", (0.04, 0.04, 0.6), (0, -0.36, 2.25), M("wood_dark"), rot=(math.radians(-15), 0, 0)),
             blob("wrap", (0.1, 0.1, 0.18), (0, -0.44, 2.46), M("soot")),
             blob("flame", (0.12, 0.12, 0.22), (0, -0.46, 2.6), M("flame", 0.9, emit=(1.0, 0.55, 0.12), emit_strength=9.0))]
    mark("Furnace", (0, -0.46, 2.72))
    export("torch_wall", join(parts, "torch_wall"), None)


def broken_stall():
    """A market stall wrecked in a riot: the counter kicked over, a post snapped, the awning torn and hanging."""
    reset()
    parts = [box("counter", (2.4, 1.2, 1.1), (0.2, 0.4, 0), M("wood"), rot=(0, 0, 0.3))]
    edit_verts(parts[0], lambda co: setattr(co, "z", co.z * 0.9))
    for (x, y, h, t) in ((-1.15, -0.55, 2.4, 0.0), (1.15, -0.55, 1.2, 0.4), (-1.15, 0.55, 2.4, 0.1), (1.15, 0.55, 0.8, 0.9)):
        parts.append(cbox("post", (0.14, 0.14, h), (x, y, h / 2), M("wood_dark"), rot=(t, 0, 0)))
    aw = roof("awning", 3.0, 2.0, 0.7, (0, 0, 2.0), M("canvas"), sag=0.3, flare=0.25, cuts=4)
    edit_verts(aw, lambda co: setattr(co, "z", co.z - max(0.0, co.x) * 0.6))
    parts.append(aw)
    for k in range(5):
        parts.append(blob("debris", (0.3, 0.2, 0.1), (RNG.uniform(-2, 2), RNG.uniform(-1.5, 1.5), 0), M("wood" if k % 2 else "crust")))
    export("broken_stall", join(parts, "broken_stall"), box("c", (2.6, 1.6, 1.1), (0.2, 0.4, 0)))


def broken_shutter():
    """A shutter torn off its hinges lying in the snow, a slat or two sprung (1.0 x 1.6 m)."""
    reset()
    parts = [box("leaf", (0.6, 1.6, 0.04), (0, 0, 0.0), M("shutter"), rot=(0.1, 0.05, 0.3))]
    parts.append(box("slat", (0.5, 0.08, 0.02), (0.4, 0.3, 0.02), M("shutter"), rot=(0, 0, 1.0)))
    parts.append(box("hinge", (0.3, 0.04, 0.01), (-0.2, 0.6, 0.05), M("iron")))
    export("broken_shutter", join(parts, "broken_shutter"), None)


def charred_patch():
    """Scorch on the ground (and up a wall at +Y) after a fire: black soot, ash, a few charred timbers, melted snow."""
    reset()
    parts = [cyl("soot", 2.2, 0.01, (0, 0, 0), M("soot", 0.95), verts=16),
             cyl("ash", 1.4, 0.015, (0.3, -0.2, 0), M("plaster_grey"), verts=12),
             box("wall_soot", (3.0, 0.02, 2.4), (0, 1.9, 0), M("soot", 0.95))]
    edit_verts(parts[0], lambda co: (setattr(co, "x", co.x * RNG.uniform(0.8, 1.1))))
    for k in range(4):
        parts.append(cbox("charred", (1.2, 0.14, 0.14), (RNG.uniform(-1, 1), RNG.uniform(-1, 1), 0.07), M("soot", 0.9), rot=(0, 0, RNG.uniform(0, 3))))
    parts.append(cyl("melt", 2.6, 0.005, (0, 0, 0.0), M("water", 0.05), verts=16))
    export("charred_patch", join(parts, "charred_patch"), None)


def kingpin_house():
    """The kingpin's townhouse: a broad late-Baroque three-storey palace front (20 m) with an attic parapet and urns,
    a rusticated ground floor with a carriage gate (sien) into a courtyard, a wrought-iron balcony over the gate,
    tall lit windows with drawn curtains, a pair of lanterns at the gate, a doorman's bench and a bell pull, a
    bought coat of arms, his steps swept clean. Behind: the courtyard with a stable, a well, a back stair to a
    gallery, a privy and a back gate to the alley. Roof access from the neighbour's side by drainpipe and
    chimney-breast steps. Front at -Y. Main block 20 x 10 m (x -10..10, y -12..-2); courtyard y -2..10; back wall
    at y 11."""
    reset()
    parts, col = [], []
    W, D, GF, FL = 20.0, 10.0, 4.6, 3.8
    y0 = -12.0
    H = GF + 2 * FL
    wall = M("plaster_straw")
    white = M("plaster_white")
    cy = y0 + D / 2
    gw, gh = 3.2, 3.0 + 1.6
    # ground floor with the gate passage straight through the block
    gops = [(0.0, 0.0, gw, gh, "round"), (-6.0, 0.0, 1.5, 2.6 + 0.75, "round"), (-8.6, 1.3, 1.2, 2.2, "rect"), (-3.2, 1.3, 1.2, 2.2, "rect"),
            (3.6, 1.3, 1.2, 2.2, "rect"), (6.2, 1.3, 1.2, 2.2, "rect"), (8.6, 1.3, 1.2, 2.2, "rect")]
    parts.append(facade("gf_front", white, "-Y", y0, -W / 2, W / 2, 0.0, GF, gops, depth=REV, back=True))
    parts.append(facade("gf_back", white, "+Y", y0 + D, -W / 2, W / 2, 0.0, GF, gops[:1], depth=0.01, back=False))
    for sx in (-1, 1):                              # the gate passage: side walls and a vault through the block
        parts.append(box("gf_mass", ((W - gw) / 2 - 0.02, D - REV, GF), (sx * (gw / 2 + (W - gw) / 4), cy + REV / 2, 0), white))
    parts.append(box("gf_over_gate", (gw + 0.04, D - REV, GF - gh), (0, cy + REV / 2, gh), white))
    vault_ = cyl("passage_vault", gw / 2, D - REV, (0, cy + REV / 2, gh - gw / 2), M("plaster_white"), verts=12, rot=(math.pi / 2, 0, 0), center=True)
    edit_verts(vault_, lambda co: setattr(co, "z", max(co.z, gh - gw / 2)))
    parts.append(vault_)
    parts.append(box("passage_floor", (gw, D, 0.03), (0, cy, 0), M("flags")))
    door_unit(parts, "-Y", y0, -6.0, 1.5, 2.6, portal=True, surround="stone_pale")
    for (a, zb, w, h, sh) in gops[2:]:
        win_unit(parts, "-Y", y0, a, zb, w, h, sh, warm=True, bars=True, surround="stone_pale", mark=True, glass="glass_warm")
    rustication(parts, "-Y", y0, -W / 2, W / 2, 0.5, GF - 0.3, gops, course=0.55, proud=0.04, mat=white)
    voussoirs(parts, "-Y", y0, 0.0, gh - gw / 2, gw, 0.4, M("stone_pale"), n=11, proud=0.12, key=0.22)
    mascaron(parts, "-Y", y0, 0.0, gh + 0.45, s=0.34)
    parts.append(fbox("gf_band", "-Y", y0, 0.0, 0.08, GF - 0.25, W + 0.1, 0.2, 0.25, M("stone_pale")))
    mark_named("Gate", _wp("-Y", y0, 0.0, 0.0, 0.1))
    mark_named("Door_front", _wp("-Y", y0, -6.0, 0.0, 0.1))
    # upper storeys
    xs = [-8.4, -5.0, -1.7, 1.7, 5.0, 8.4]
    uops = [(x, GF + s * FL + (0.25 if (s == 0 and abs(x) < 2) else 0.7), 1.25, 2.55 if (s == 0 and abs(x) < 2) else 2.2, "rect") for s in range(2) for x in xs]
    parts.append(box("upper", (W, D - REV, 2 * FL), (0, cy + REV / 2, GF), wall))
    parts.append(facade("up_front", wall, "-Y", y0, -W / 2 - 0.01, W / 2 + 0.01, GF, H, uops))
    for (a, zb, w, h, sh) in uops:
        win_unit(parts, "-Y", y0, a, zb, w, h, sh, warm=True, surround="stone_pale", mark=zb < GF + FL, glass="glass_warm",
                 head="lintel" if zb > GF + FL else None, sill=not (zb < GF + 1 and abs(a) < 2), snow=True)
        # drawn curtains behind the glass: dark red panels leaving a lit slit
        for sx in (-1, 1):
            parts.append(fbox("curtain", "-Y", y0, a + sx * w * 0.3, -REV - 0.04, zb + 0.05, w * 0.42, 0.02, h - 0.2, M("crimson")))
        if zb < GF + FL and abs(a) > 2:
            zt = zb + 2.35
            parts.append(slab("ped", [(a - 0.9, zt), (a + 0.9, zt), (a, zt + 0.5)], "-Y", y0, 0.0, 0.16, M("stone_pale")))
            parts.append(fbox("ped_snow", "-Y", y0, a, 0.08, zt + 0.01, 1.5, 0.16, 0.025, M("snow")))
    balcony_iron(parts, "-Y", y0, 0.0, GF + 0.25, w=4.6, d=1.1, seed=71)
    for x in (-W / 2 + 0.3, -3.4, 3.4, W / 2 - 0.3):
        parts.append(box("gpil", (0.6, 0.14, 2 * FL - 0.4), (x, y0 - 0.07, GF + 0.1), white))
        parts.append(box("gpil_cap", (0.8, 0.24, 0.3), (x, y0 - 0.12, H - 0.4), M("stone_pale")))
    for s in range(2):
        for x in (-W / 2 + 0.9, W / 2 - 0.9):
            wall_anchor(parts, "-Y", y0, x, GF + FL * (s + 1) - 0.4, "S")
    cornice(parts, W, D, H - 0.1, t=0.45, proud=0.35, modillions=False)
    for p_ in parts[-3:]:
        edit_verts(p_, lambda co: setattr(co, "y", co.y + cy))
    icicles(parts, (-W / 2, y0 - 0.55), (W / 2, y0 - 0.55), H - 0.1, maxlen=0.5, seed=72, gap=0.45)
    # attic parapet with balusters and urns; a low roof behind it
    A0 = H + 0.35
    parts.append(box("attic", (W + 0.3, 0.5, 1.3), (0, y0 + 0.2, A0), wall))
    for k in range(13):
        x = -W / 2 + 0.8 + k * (W - 1.6) / 12
        parts.append(cyl("baluster", 0.1, 0.8, (x, y0 - 0.08, A0 + 0.25), white, verts=8, r2=0.07))
    parts.append(box("att_cop", (W + 0.5, 0.8, 0.18), (0, y0 + 0.2, A0 + 1.3), M("stone_pale")))
    parts.append(box("att_cop_snow", (W + 0.4, 0.7, 0.03), (0, y0 + 0.2, A0 + 1.48), M("snow")))
    for x in (-W / 2 + 0.3, -3.4, 3.4, W / 2 - 0.3):
        parts.append(cyl("urn_base", 0.25, 0.3, (x, y0 + 0.2, A0 + 1.48), M("stone_pale"), verts=10))
        parts.append(sphere("urn", 0.3, (x, y0 + 0.2, A0 + 2.05), M("stone_pale"), seg=10, rings=6, zscale=1.3))
        parts.append(sphere("flame", 0.12, (x, y0 + 0.2, A0 + 2.5), M("gold", 0.35), seg=8, rings=5))
        snow_cap(parts, x, y0 + 0.2, A0 + 2.4, 0.22, 0.06, seg=8)
    _roof_set(parts, W + 0.6, D + 0.8, 3.4, (0, cy + 0.6, H), M("tile_dark"), courses=3, seed=73, ice=False,
              drifts=[(0, y0 + 1.2, W, 0.12)])
    for x in (-6.0, 6.0):
        chimney(parts, x, cy + 2.0, H + 1.6, h=2.4)
    # the gate: lanterns, bench, bell pull, coat of arms, swept steps (flags, no snow)
    for sx in (-1, 1):
        parts.append(fbox("lantern_arm", "-Y", y0, sx * 2.3, 0.3, 3.3, 0.04, 0.6, 0.04, M("iron")))
        parts.append(fbox("lantern", "-Y", y0, sx * 2.3, 0.6, 2.8, 0.3, 0.3, 0.45, M("gold", 0.3, emit=(1.0, 0.72, 0.35), emit_strength=5.0)))
        parts.append(fbox("lantern_cap", "-Y", y0, sx * 2.3, 0.6, 3.25, 0.4, 0.4, 0.1, M("iron")))
    parts.append(fbox("bench", "-Y", y0, 3.2, 0.35, 0.45, 1.6, 0.4, 0.08, M("wood_dark")))
    for x in (2.6, 3.8):
        parts.append(fbox("bench_leg", "-Y", y0, x, 0.35, 0.0, 0.08, 0.35, 0.45, M("wood_dark")))
    parts.append(fbox("bell_pull", "-Y", y0, -1.95, 0.08, 1.2, 0.02, 0.02, 0.9, M("iron")))
    parts.append(torus("bell_ring", 0.06, 0.012, tuple(_wp("-Y", y0, -1.95, 1.15, 0.09)), M("gold", 0.35), rot=(math.pi / 2, 0, 0), seg=10, mseg=4))
    parts.append(fbox("arms_shield", "-Y", y0, 0.0, 0.12, H - 1.4, 1.1, 0.12, 1.3, M("crimson")))
    parts.append(fbox("arms_band", "-Y", y0, 0.0, 0.19, H - 0.9, 1.1, 0.02, 0.18, M("gold", 0.3)))
    parts.append(blob("arms_crown", (0.9, 0.15, 0.35), (0, y0 - 0.2, H - 0.05), M("gold", 0.3), subsurf=1))
    parts.append(box("steps", (W - 2.0, 1.2, 0.14), (-1.0, y0 - 0.6, 0), M("flags")))
    parts.append(box("steps2", (3.0, 0.5, 0.28), (-6.0, y0 - 0.25, 0), M("stone_pale")))
    for sx in (-1, 1):                       # his neighbours' snow, shovelled against the ends of his frontage
        parts.append(box("drift", (1.6, 1.2, 0.5), (sx * (W / 2 + 0.3), y0 - 0.7, 0), M("snow"), bevel=0.3, seg=2, wonk=0.15))
    mark_named("Post_0", (2.6, y0 - 1.2, 0.0), 0.0)
    mark_named("Post_1", (-2.6, y0 - 1.2, 0.0), 0.0)
    # courtyard: side walls, stable, well, back stair and gallery, privy, back wall with the back gate
    for sx in (-1, 1):
        parts.append(box("yard_wall", (0.6, 13.0, 4.0), (sx * (W / 2 - 0.3), 4.5, 0), M("plaster_grey")))
        parts.append(box("yard_wall_cop", (0.8, 13.0, 0.15), (sx * (W / 2 - 0.3), 4.5, 4.0), M("tile_dark")))
        parts.append(box("yard_wall_snow", (0.7, 12.9, 0.04), (sx * (W / 2 - 0.3), 4.5, 4.15), M("snow")))
        col.append(box("c", (0.6, 13.0, 4.1), (sx * (W / 2 - 0.3), 4.5, 0)))
    parts.append(box("stable", (5.0, 7.0, 3.4), (W / 2 - 3.1, 4.5, 0), M("timber")))
    parts.append(box("stable_door", (0.06, 1.6, 2.4), (W / 2 - 5.63, 3.5, 0), M("wood_dark")))
    parts.append(roof("stable_roof", 7.4, 5.6, 1.4, (W / 2 - 3.1, 4.5, 3.4), M("shingle"), along_x=False, sag=0.03, flare=0.04, cuts=3))
    sn = roof_snow("stable_snow", 7.4, 5.6, 1.4, (W / 2 - 3.1, 4.5, 3.4), along_x=False, sag=0.03, flare=0.04, cuts=3, thick=0.06, cell=0.7, seed=74)
    if sn:
        parts.append(sn)
    col.append(box("c", (5.0, 7.0, 3.4), (W / 2 - 3.1, 4.5, 0)))
    climb("mantle", (5.6, 7.4, 0.3), (W / 2 - 3.1, 4.5, 3.9))
    for k in range(8):
        a = math.tau * k / 8
        parts.append(cbox("well", (0.7, 0.35, 0.8), (-3.0 + 0.8 * math.cos(a), 3.0 + 0.8 * math.sin(a), 0.4), M("stone"), rot=(0, 0, a + math.pi / 2)))
    parts.append(cyl("well_snow", 0.6, 0.02, (-3.0, 3.0, 0.8), M("ice", 0.05), verts=12))
    col.append(cyl("c", 1.0, 0.8, (-3.0, 3.0, 0), None, verts=8))
    gallery_wood(parts, "+Y", y0 + D, -W / 2 + 1.0, 2.0, GF + 0.1, d=1.4, posts=4, roof_h=2.8, seed=75)
    for k in range(12):
        parts.append(box("stair", (1.0, 0.32, 0.06), (-W / 2 + 1.7, y0 + D + 5.4 - k * 0.32, 0.38 * (k + 1)), M("wood")))
    climb("mantle", (1.0, 4.0, 0.2), (-W / 2 + 1.7, y0 + D + 3.6, 2.3), rot=(math.atan2(4.6, 3.8), 0, 0))
    parts.append(box("privy", (1.2, 1.2, 2.2), (-W / 2 + 1.6, 9.6, 0), M("wood_dark")))
    parts.append(box("privy_roof", (1.4, 1.4, 0.1), (-W / 2 + 1.6, 9.6, 2.2), M("shingle")))
    parts.append(box("privy_snow", (1.3, 1.3, 0.05), (-W / 2 + 1.6, 9.6, 2.3), M("snow")))
    col.append(box("c", (1.2, 1.2, 2.2), (-W / 2 + 1.6, 9.6, 0)))
    for sx in (-1, 1):
        parts.append(box("back_wall", (W / 2 - 1.4, 0.6, 3.6), (sx * (W / 4 + 0.7), 10.7, 0), M("plaster_grey")))
        col.append(box("c", (W / 2 - 1.4, 0.6, 3.6), (sx * (W / 4 + 0.7), 10.7, 0)))
        parts.append(box("back_wall_snow", (W / 2 - 1.5, 0.5, 0.05), (sx * (W / 4 + 0.7), 10.7, 3.6), M("snow")))
    parts.append(box("back_gate", (2.6, 0.08, 2.4), (0, 10.95, 0), M("wood_dark")))
    parts.append(box("back_gate_lintel", (3.0, 0.6, 0.3), (0, 10.7, 2.6), M("timber")))
    mark_named("Door_back", (0, 11.2, 0.0), math.pi)
    mark_named("Post_2", (0.0, 5.0, 0.0), math.pi)
    mark_named("Post_3", (0.0, 12.4, 0.0), math.pi)
    parts.append(box("yard_floor", (W - 1.2, 12.4, 0.03), (0, 4.3, 0), M("flags")))
    # roof access from the neighbour's side (+X): a drainpipe and chimney-breast steps up the gable wall
    climb("pipe", (0.3, 0.3, H), (W / 2 + 0.15, y0 + 1.0, H / 2))
    parts.append(cyl("pipe", 0.055, H, (W / 2 + 0.15, y0 + 1.0, 0.0), M("lead"), verts=8))
    for k in range(3):
        climb("ledge", (0.6, 1.2, 0.2), (W / 2 + 0.3, cy + 2.0, 3.0 + k * 2.2))
        parts.append(box("breast", (0.5, 1.2, 0.18), (W / 2 + 0.25, cy + 2.0, 2.9 + k * 2.2), M("brick")))
    climb("ledge", (W + 0.5, 0.8, 0.2), (0, y0 + 0.2, A0 + 1.4))
    # collision: the block either side of the gate passage and over it, the roof to walk on
    col.append(box("c", ((W - gw) / 2, D, H), (-(gw / 2 + (W - gw) / 4), cy, 0)))
    col.append(box("c", ((W - gw) / 2, D, H), ((gw / 2 + (W - gw) / 4), cy, 0)))
    col.append(box("c", (gw, D, H - gh), (0, cy, gh)))
    col.append(wedge("c_roof", (W + 0.6, D + 0.8, 3.4), (0, cy + 0.6, H)))
    export("kingpin_house", join(parts, "kingpin_house"), join(col, "col"))


PASS5_BUILDS = [("bathhouse", bathhouse), ("kingpin_warehouse", kingpin_warehouse), ("carpenter_yard", carpenter_yard),
                ("guillotine", guillotine), ("guillotine_parts", guillotine_parts), ("torch", torch), ("torch_wall", torch_wall),
                ("broken_stall", broken_stall), ("broken_shutter", broken_shutter), ("charred_patch", charred_patch),
                ("kingpin_house", kingpin_house)]


# ------------------------------------------------------------------ UNDERGROUND ENTRANCES (pass 6)
def drain_grate():
    """Street drain grate, 0.9 x 0.6 m: a dressed stone kerb frame flush with the paving, the iron grate (separate
    node `Grate`, the interactable: meta hidden_entrance, set by outer_city.gd) sunk 3 cm, dark shaft below.
    The frame has -colonly collision; the grate has none."""
    reset()
    parts, col = [], []
    for sx in (-1, 1):
        parts.append(box("frame_l", (0.14, 0.88, 0.1), (sx * 0.52, 0, -0.08), M("stone"), bevel=0.015, seg=1))
        col.append(box("c", (0.14, 0.88, 0.1), (sx * 0.52, 0, -0.08)))
        parts.append(box("frame_s", (1.18, 0.14, 0.1), (0, sx * 0.37, -0.08), M("stone"), bevel=0.015, seg=1))
        col.append(box("c", (1.18, 0.14, 0.1), (0, sx * 0.37, -0.08)))
    parts.append(box("shaft", (0.9, 0.6, 0.02), (0, 0, -0.6), M("void")))
    parts.append(box("snow", (0.3, 0.12, 0.015), (0.4, 0.37, 0.02), M("snow_dirty")))
    g = [box("grate_rim", (0.9, 0.6, 0.03), (0, 0, -0.06), M("iron"))]
    bpy.data.objects.remove(g.pop(), do_unlink=True)
    for k in range(7):
        g.append(box("bar", (0.03, 0.6, 0.03), (-0.39 + k * 0.13, 0, -0.05), M("iron")))
    for sy in (-1, 1):
        g.append(box("rail", (0.9, 0.04, 0.035), (0, sy * 0.28, -0.05), M("iron")))
    g.append(torus("ring", 0.04, 0.008, (0.3, 0, -0.01), M("iron"), seg=8, mseg=4))
    extra("Grate", g)
    export("drain_grate", join(parts, "drain_grate"), join(col, "col"))


def outfall_arch():
    """Culvert outfall in a moat or river bank: a brick arch (1.6 m wide) in a stone-faced bank 5 m wide, 2.4 m
    high, a rusted iron grille across it (separate node `Grille`), a frozen trickle fanning out below.
    Front at -Y; the bank face at y=0; collision on the bank, none on the grille."""
    reset()
    parts, col = [], []
    aw, ah = 1.6, 1.6 + 0.8
    parts.append(facade("bank", M("stone_dark"), "-Y", 0.0, -2.5, 2.5, -0.6, 2.4, [(0.0, -0.4, aw, ah, "round")], depth=1.2, back=True))
    parts.append(box("bank_mass", (5.0, 2.0, 3.0), (0, 2.2, -0.6), M("stone_dark")))
    voussoirs(parts, "-Y", 0.0, 0.0, -0.4 + ah - aw / 2, aw, 0.26, M("brick"), n=11, proud=0.05, key=0.06)
    parts.append(slab("dark", outline(0.0, -0.4, aw, ah, "round"), "-Y", 0.0, -1.19, -1.17, M("void")))
    parts.append(box("bank_snow", (5.0, 1.4, 0.06), (0, 0.5, 2.4), M("snow"), bevel=0.03, seg=1))
    g = []
    for k in range(7):
        x = -aw / 2 + 0.15 + k * (aw - 0.3) / 6
        top = -0.4 + ah - aw / 2 + math.sqrt(max(0.0, (aw / 2) ** 2 - x * x)) - 0.05
        g.append(box("bar", (0.04, 0.04, top + 0.4), (x, -0.2, -0.4), M("iron")))
    for z in (0.2, 1.0):
        g.append(box("rail", (aw, 0.05, 0.05), (0, -0.2, z), M("iron")))
    extra("Grille", g)
    bm = bmesh.new()
    _tube(bm, (0, -0.1, -0.35), (0.1, -1.2, -0.58), 0.12, 0.3, n=6)
    parts.append(_mesh_obj("trickle", bm, M("ice", 0.05)))
    parts.append(box("trickle_sheet", (1.2, 1.4, 0.01), (0.1, -1.4, -0.6), M("ice", 0.05), wonk=0.1))
    icicles(parts, (-0.7, -0.3), (0.7, -0.3), -0.4 + ah - 0.2, maxlen=0.4, seed=81, density=6)
    col.append(box("c", (5.0, 1.8, 3.0), (0, 2.3, -0.6)))
    for sx in (-1, 1):
        col.append(box("c", (1.7, 1.2, 3.0), (sx * 1.65, 0.6, -0.6)))
    export("outfall_arch", join(parts, "outfall_arch"), join(col, "col"))


def well_shaft_cap():
    """The square's well capped for winter: the octagonal stone curb with an iron lid (separate node `Lid`,
    hinged at +Y, meta hidden_entrance set at runtime) and a staple and padlock, snow on the curb, no windlass."""
    reset()
    parts = []
    stone = M("stone_dark")
    for k in range(8):
        a = math.tau * k / 8
        parts.append(cbox("stone", (0.95, 0.55, 0.5), (1.15 * math.cos(a), 1.15 * math.sin(a), 0.25), stone, rot=(0, 0, a + math.pi / 2), bevel=0.04, seg=1, wonk=0.03))
        parts.append(cbox("stone", (0.95, 0.55, 0.5), (1.15 * math.cos(a + math.pi / 8), 1.15 * math.sin(a + math.pi / 8), 0.75), stone, rot=(0, 0, a + math.pi / 8 + math.pi / 2), bevel=0.04, seg=1, wonk=0.03))
        parts.append(cbox("lip_snow", (0.8, 0.5, 0.03), (1.15 * math.cos(a), 1.15 * math.sin(a), 1.015), M("snow"), rot=(0, 0, a + math.pi / 2)))
    lid = [cyl("lid", 1.0, 0.05, (0, 0, 1.0), M("iron"), verts=16)]
    for k in range(3):
        lid.append(box("strap", (2.0, 0.08, 0.02), (0, -0.6 + k * 0.6, 1.05), M("iron")))
    lid.append(torus("handle", 0.1, 0.015, (0, -0.8, 1.07), M("iron"), seg=10, mseg=4))
    lid.append(cyl("lid_snow", 0.8, 0.02, (0.1, 0.1, 1.07), M("snow"), verts=12))
    extra("Lid", lid)
    parts.append(box("hinge", (0.5, 0.1, 0.06), (0, 0.98, 1.0), M("iron")))
    parts.append(box("staple", (0.06, 0.06, 0.12), (0, -1.05, 0.95), M("iron")))
    parts.append(box("padlock", (0.1, 0.05, 0.12), (0, -1.1, 0.86), M("iron")))
    parts.append(box("drift", (3.2, 3.2, 0.1), (0.2, 0.2, 0), M("snow"), bevel=0.25, seg=2, wonk=0.12))
    export("well_shaft_cap", join(parts, "well_shaft_cap"), cyl("c", 1.45, 1.05, (0, 0, 0), None, verts=8))


def manhole_stone():
    """A round stone cover slab set into a street (cosmetic): 0.8 m, a lifting ring socket, worn edge, flush."""
    reset()
    parts = [cyl("slab", 0.42, 0.06, (0, 0, -0.05), M("stone"), verts=16),
             cyl("rim", 0.46, 0.05, (0, 0, -0.055), M("stone_dark"), verts=16),
             cyl("socket", 0.05, 0.02, (0.2, 0, 0.0), M("void"), verts=8),
             torus("ring", 0.05, 0.008, (0.2, 0, 0.012), M("iron"), seg=8, mseg=4)]
    export("manhole_stone", join(parts, "manhole_stone"), None)


PASS6_BUILDS = [("drain_grate", drain_grate), ("outfall_arch", outfall_arch), ("well_shaft_cap", well_shaft_cap),
                ("manhole_stone", manhole_stone)]


PASS2_BUILDS = [
    ("ten_renaissance", ten_renaissance), ("ten_renaissance_b", lambda: ten_renaissance("ten_renaissance_b", "plaster_mint", "shutter_brown", seed=31)),
    ("ten_gothic", ten_gothic), ("ten_gothic_b", lambda: ten_gothic("ten_gothic_b", "plaster_oxblood", seed=32)),
    ("ten_baroque", ten_baroque), ("ten_burgher", ten_burgher),
    ("ten_burgher_b", lambda: ten_burgher("ten_burgher_b", "plaster_limeblue", "shutter_red", seed=34)),
    ("ten_timber", ten_timber), ("ten_wooden", ten_wooden),
    ("fountain", fountain), ("water_pump", water_pump), ("horse_trough", horse_trough), ("gutter_channel", gutter_channel),
    ("windmill", windmill), ("watermill", watermill), ("bell_foundry", bell_foundry), ("forge", forge), ("brewery", brewery),
    ("cooper_yard", cooper_yard), ("tannery_frame", tannery_frame),
    ("campanile", campanile), ("synagogue_wooden", synagogue_wooden), ("uniate_church", uniate_church), ("prayer_house", prayer_house),
    ("shrine_column", shrine_column), ("monastery_wall", monastery_wall), ("monastery_gate", monastery_gate),
    ("wawel_far", wawel_far), ("castle_gate", castle_gate),
    ("pillory", pillory), ("stocks", stocks), ("whipping_post", whipping_post), ("gallows", gallows),
]


BUILDS = [
    ("tenement_a", lambda: tenement("tenement_a", 10.0, 3, "gable", "plaster_ochre", bays=3, shutters=True, shutter_col="shutter", shutter_style="louvre", gallery=True, seed=11)),
    ("tenement_b", lambda: tenement("tenement_b", 8.0, 3, "attyka", "plaster_rose", bays=2, seed=12)),
    ("tenement_c", lambda: tenement("tenement_c", 12.0, 4, "mansard", "plaster_cream", bays=3, pilasters=True, arched_windows=True, balcony=3, seed=13)),
    ("tenement_d", lambda: tenement("tenement_d", 10.0, 3, "attyka", "plaster_sage", bays=3, arched_windows=True, shutters=True, shutter_col="shutter_red", shutter_style="board", gallery=True, seed=14)),
    ("tenement_e", lambda: tenement("tenement_e", 8.0, 4, "gable", "plaster_blue", bays=2, shutters=True, shutter_col="shutter_ochre", shutter_style="louvre", seed=15)),
    ("sukiennice", sukiennice), ("st_marys", st_marys), ("town_hall", town_hall), ("st_adalbert", st_adalbert),
    ("market_stall", market_stall), ("barrel", barrel), ("crate_stack", crate_stack), ("cart", cart), ("well", well),
    ("lantern_post", lantern_post), ("brazier", brazier), ("ground_cobbles", ground_cobbles),
] + globals().get("DISTRICT_BUILDS", []) + globals().get("FARM_BUILDS", []) + globals().get("DRESSING_BUILDS", []) + globals().get("PASS2_BUILDS", []) + globals().get("PASS3_BUILDS", []) + globals().get("PASS4_BUILDS", []) + globals().get("PASS5_BUILDS", []) + globals().get("PASS6_BUILDS", [])


def _cli_list(flag):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1].split(",")
    return None


if __name__ == "__main__" and "--animals" not in sys.argv:
    t0 = time.time()
    for k in RECIPES:
        bake_texture(k)
    print("[tex] cache ready in %.1fs (%s)" % (time.time() - t0, TEX))
    if "--textures" not in sys.argv:
        only = _cli_list("--only")
        full = {n for n, _ in BUILDS[:BUILDS.index(next(b for b in BUILDS if b[0] == "ground_cobbles")) + 1]} | {n for n, _ in DRESSING_BUILDS}
        for name, fn in BUILDS:
            if only and name not in only:
                continue
            TEX_HALF = name not in full and name not in ("fountain", "pillory", "gutter_channel", "gutter_corner", "gutter_slab",
                                                         "gutter_outfall", "ground_cobbles_lo", "ground_flags", "ground_mud")
            fn()
        print("[assets] tris", " ".join("%s=%d" % kv for kv in TRI_LOG.items()))
    print("[assets] done in %.1fs" % (time.time() - t0))
