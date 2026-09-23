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
}
_mats = {}

# texture kind -> (resolution, metres per repeat)
TEXSPEC = {
    "plaster": (2048, 4.0), "plaster_damp": (2048, 4.0), "tile": (2048, 4.0), "cobbles": (2048, 4.0), "field": (2048, 4.0),
    "brick": (1024, 2.0), "sandstone": (1024, 2.0), "oak": (1024, 2.0), "iron": (1024, 2.0), "metal": (1024, 2.0),
    "glass": (1024, 2.0), "snow": (1024, 2.0), "cloth": (1024, 2.0), "thatch": (1024, 2.0), "log": (1024, 2.0),
}
TEX_OF = {}
for _k in ("plaster_ochre", "plaster_rose", "plaster_cream", "plaster_sage", "plaster_blue", "plaster_white",
           "plaster_lime", "plaster_limeblue", "plaster_grey"):
    TEX_OF[_k] = "plaster"
TEX_OF.update({"stone": "sandstone", "stone_dark": "sandstone", "stone_pale": "sandstone", "brick": "brick",
               "brick_dark": "brick", "tile": "tile", "tile_dark": "tile", "tile_moss": "tile", "wood": "oak",
               "wood_dark": "oak", "timber": "oak", "shutter": "oak", "iron": "iron", "lead": "metal",
               "copper": "metal", "glass": "glass", "glass_warm": "glass", "snow": "snow", "canvas": "cloth",
               "canvas_stripe": "cloth", "cobble": "cobbles", "thatch": "thatch", "log": "log", "log_lime": "log",
               "field": "field", "hay": "thatch", "straw": "thatch", "salt": "snow"})
# tint = glTF baseColorFactor over the bake. Neutral bakes (plaster, metal, glass, cloth) take the palette colour.
TINT = {"brick": (1, 1, 1), "brick_dark": (0.70, 0.64, 0.62), "tile": (1, 1, 1), "tile_dark": (0.74, 0.68, 0.66),
        "tile_moss": (0.86, 0.86, 0.72), "stone": (0.92, 0.91, 0.90), "stone_dark": (0.64, 0.63, 0.62),
        "stone_pale": (1, 1, 1), "wood": (1, 1, 1), "wood_dark": (0.56, 0.52, 0.50), "timber": (0.70, 0.66, 0.62),
        "shutter": (0.60, 0.82, 0.74), "iron": (1, 1, 1), "snow": (1, 1, 1), "cobble": (1, 1, 1), "thatch": (0.85, 0.8, 0.74),
        "log": (0.78, 0.70, 0.62), "log_lime": (1, 1, 1), "field": (1, 1, 1), "hay": (1.0, 1.0, 1.0),
        "straw": (1.0, 1.0, 1.0), "salt": (0.95, 0.93, 0.90)}
METALLIC = {"iron": 0.55, "metal": 0.25}
_tex_rep = {}        # material name -> metres per repeat (read by auto_uv)


def _desat(c, k=0.18, dim=0.96):
    l = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
    return tuple((v + (l - v) * k) * dim for v in c)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _mats.clear()
    _tex_rep.clear()


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
    lumps = g.noise(6, 6, 5, 0.55, seed=37)
    fine = g.noise(140, 140, 2, seed=38)
    col = g.mix(lumps, (0.80, 0.83, 0.90), (0.95, 0.96, 0.99))
    sp = g.smooth(fine, 0.72, 0.76)
    col = g.mix(g.mul(sp, 0.4), col, (1.0, 1.0, 1.0))
    h = g.add(g.mul(lumps, 0.7), g.mul(fine, 0.12))
    rough = g.add(0.62, g.mul(fine, 0.2))
    return col, rough, h, 0.03


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
    dome = g.mul(stone, g.m("SQRT", g.mx(g.sub(1.0, g.add(g.mul(ex, ex), g.mul(ez, ez))), 0.0)))
    lump = g.mul(g.sub(g.noise(44, 44, 4, seed=52), 0.5), 1.4)
    facet = g.mul(g.sub(g.voronoi(40, 40, feature="F1", seed=53), 0.35), 0.8)
    pit = g.smooth(g.voronoi(120, 120, seed=54), 0.0, 0.09)
    chip = g.mul(g.smooth(g.voronoi(58, 58, seed=55), 0.0, 0.16), g.one_minus(g.mul(dome, 0.7)))
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
    hdome = g.add(0.35, g.mul(r6, 0.65))
    jointh = g.add(g.add(0.04, g.mul(grain, 0.08)), g.add(g.mul(g.one_minus(gravel), 0.06), g.mul(snowj, 0.22)))
    top = g.add(g.add(g.mul(dome, hdome), g.mul(g.add(lump, facet), dome)), g.mul(g.add(g.mul(pit, -0.25), g.mul(chip, -0.30)), dome))
    stoneh = g.mul(g.add(g.add(0.40, tilt), top), g.sub(1.0, g.mul(sunken, 0.5)))
    h = g.add(g.mul(stone, stoneh), g.mul(g.one_minus(stone), jointh))
    rough = g.lerp(stone, g.add(0.9, g.mul(gravel, 0.1)),
                   g.add(g.add(0.5, g.mul(chip, 0.15)), g.add(g.mul(wear, 0.3), g.mul(wet, -0.25))))
    return col, rough, h, 0.10


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
           "log": _tx_log, "field": _tx_field}


def _tex_paths(kind):
    return {p: os.path.join(TEX, "%s_%s.png" % (kind, p)) for p in ("col", "rough", "nrm")}


_baked_this_run = set()


HEIGHT_EXPORT = {"cobbles"}
TEX_DIR = os.path.join(ROOT, "assets", "textures")


def bake_texture(kind):
    """Bake one texture kind to assets/textures/<kind>_{col,rough,nrm}.png (cached). Runs in a scratch scene, so it
    is safe to call in the middle of building an asset."""
    paths = _tex_paths(kind)
    if all(os.path.exists(p) for p in paths.values()) and (not REBAKE or kind in _baked_this_run):
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
    print("[tex] baked %s %dpx in %.1fs" % (kind, res, time.time() - t0))
    return paths


def _img(path, colour):
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return im


def _tex_material(key, kind, tint):
    paths = bake_texture(kind)
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
             sill=True, head="lintel", cross=True, bars=False, snow=True):
    """Glazed window set into a facade() opening (a, zb, w, h, shape) with its REV-deep reveal: glass and a
    timber frame at the back of the reveal, a stone sill and lintel (or an arch of voussoirs), a raised
    surround, optional open shutters and iron bars."""
    fr = M("wood_dark")
    ol = outline(a, zb, w, h, shape)
    zs = zb + h - rise_of(shape, w)
    parts.append(slab("glass", ol, face, plane, -REV + 0.005, -REV + 0.025, M("glass_warm" if warm else "glass")))
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
        parts.append(fbox("sill", face, plane, a, (0.12 - REV) / 2, zb - 0.12, w + 0.3, 0.12 + REV, 0.12, M("stone"), bevel=0.02, seg=1))
        if snow:
            parts.append(fbox("sill_snow", face, plane, a, (0.1 - REV) / 2 + 0.01, zb, w + 0.2, 0.08 + REV, 0.03, M("snow"), bevel=0.01, seg=1))
    if surround:
        sm = M(surround)
        bw = 0.13
        parts.append(fbox("sur", face, plane, a - w / 2 - bw / 2, 0.025, zb - 0.02, bw, 0.05, zs - zb + 0.02, sm))
        parts.append(fbox("sur", face, plane, a + w / 2 + bw / 2, 0.025, zb - 0.02, bw, 0.05, zs - zb + 0.02, sm))
    if shape == "rect":
        if head == "lintel":
            parts.append(fbox("lintel", face, plane, a, 0.04, zs, w + 0.42, 0.08, 0.24, M("stone"), bevel=0.02, seg=1))
            parts.append(fbox("hood", face, plane, a, 0.08, zs + 0.24, w + 0.56, 0.16, 0.08, M("stone"), bevel=0.02, seg=1))
            if snow:
                parts.append(fbox("hood_snow", face, plane, a, 0.08, zs + 0.32, w + 0.5, 0.14, 0.025, M("snow"), bevel=0.01, seg=1))
    else:
        voussoirs(parts, face, plane, a, zs, w, 0.16, M("stone"), shape=shape, n=7 if shape == "round" else 8)
    if shutters:
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
            for k in range(4):
                parts.append(fbox("stud", face, plane, lx - lw / 2 + 0.12 + k * (lw - 0.24) / 3, -REV + 0.13, zz + 0.02, 0.035, 0.02, 0.035, iron))
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
            parts.append(box("quoin", (w, 0.12, hgt), (cx + sx * (width / 2 - w / 2 + 0.02), face - 0.05, z), M("stone_pale"), bevel=0.03, seg=1, wonk=0.02))
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
        parts.append(cyl("pot", 0.14, 0.45, (tx + dx, ty, z + h + 0.14), M("brick_dark"), verts=10, r2=0.11))
    parts.append(box("snow", (1.0, 1.0, 0.08), (tx, ty, z + h + 0.14), M("snow"), bevel=0.03, seg=1))


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
        parts.append(roof("dormer_snow", depth + 0.3, w + 0.44, h * 0.55 + 0.06, (x, y_front + depth / 2 - 0.15, zb + h + 0.02), M("snow"), sag=0.03, flare=0.1, cuts=3, along_x=False, top_w=0.2, bevel=0.03))


# ------------------------------------------------------------------ TENEMENT (kamienica)
SIGNS = iter(["disc", "key", "pretzel", "boot", "disc", "key", "boot", "pretzel"] * 4)


def tenement(name, width, storeys, roof_kind, colour, bays=3, pilasters=False, arched_windows=False, shutters=False):
    reset()
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
        win_unit(parts, "-Y", face, x, zb, w, h, sh, warm=RNG.random() < 0.5, surround=None, bars=True, cross=True)
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
        parts.append(facade("face", plaster, "-Y", yf, -ws / 2 - 0.01, ws / 2 + 0.01, z0, z0 + FL, ops))
        for (x, zb, w, h, sh) in ops:
            win_unit(parts, "-Y", yf, x, zb, w, h, sh, warm=RNG.random() < 0.3, shutters=shutters and sh == "rect")
        parts.append(box("string", (ws + 0.16, 0.30 + jetty, 0.22), (0, yf + 0.1 + jetty / 2 - 0.12, z0 - 0.12), spale, bevel=0.03, seg=1, wonk=0.02))
        quoins(parts, ws, D, z0 + 0.12, z0 + FL, yf)
        if pilasters:
            for i in range(bays + 1):
                px_ = -width / 2 + bay_w * i
                px_ = max(min(px_, width / 2 - 0.3), -width / 2 + 0.3)
                parts.append(box("pil", (0.42, 0.10, FL - 0.4), (px_, yf - 0.05, z0 + 0.15), M("plaster_white"), bevel=0.02, seg=1))
                parts.append(box("pil_cap", (0.56, 0.16, 0.14), (px_, yf - 0.08, z0 + FL - 0.3), spale, bevel=0.02, seg=1))
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
    top = body_h + 0.4
    Wr = dtop + 1.2
    yc = -jetty * (storeys - 1) * 0.5

    if roof_kind == "gable":
        parts.append(roof("roof", width + 0.9, Wr, 4.6, (0, yc, top), M("tile"), sag=0.18, flare=0.16, courses=6, ridge=True))
        for x in xs[:: max(1, bays - 1)]:
            dormer(parts, x, yfront + 1.0, top + 0.55, 1.3, 1.45, plaster, M("tile_dark"), warm=RNG.random() < 0.4)
        chimney(parts, width * 0.3, 1.2, top + 2.0)
        roof_top = top + 4.8
    elif roof_kind == "attyka":
        aw_front = yfront - 0.05
        parts.append(box("attic_wall", (width + 0.3, dtop + 0.2 - REV, 2.3), (0, yc + REV / 2, top - 0.4), plaster, bevel=0.06, seg=1, wonk=0.03))
        blind = [(x, top + 0.0, bay_w * 0.5, 1.6, "round") for x in xs]
        parts.append(facade("attic_face", plaster, "-Y", yc - (dtop + 0.2) / 2, -(width + 0.3) / 2 - 0.01, (width + 0.3) / 2 + 0.01, top - 0.4, top + 1.9, blind))
        af = yc - (dtop + 0.2) / 2
        for x in xs:
            parts.append(box("blind_pil", (0.22, 0.08, 1.2), (x - bay_w * 0.25 - 0.14, af - 0.04, top), M("plaster_white"), bevel=0.015, seg=1))
            parts.append(box("blind_pil", (0.22, 0.08, 1.2), (x + bay_w * 0.25 + 0.14, af - 0.04, top), M("plaster_white"), bevel=0.015, seg=1))
            voussoirs(parts, "-Y", af, x, top + 1.6 - bay_w * 0.25, bay_w * 0.5, 0.12, M("plaster_white"), n=7, proud=0.05, key=0.08)
        parts.append(box("attic_base", (width + 0.5, 0.3, 0.2), (0, af - 0.1, top - 0.45), spale, bevel=0.03, seg=1))
        parts.append(box("coping", (width + 0.6, dtop + 0.5, 0.18), (0, yc, top + 1.9), stone, bevel=0.03, seg=1, wonk=0.02))
        parts.append(box("coping_snow", (width + 0.5, dtop + 0.4, 0.03), (0, yc, top + 2.08), M("snow"), bevel=0.01, seg=1))
        n = max(2, int(width / 2.2))
        py_ = af + 0.2
        for i in range(n + 1):
            x = -width / 2 + (width / n) * i
            parts.append(box("pin_base", (0.62, 0.62, 0.16), (x, py_, top + 2.08), stone, bevel=0.02, seg=1))
            parts.append(box("pin", (0.48, 0.48, 0.8), (x, py_, top + 2.24), stone, bevel=0.03, seg=1, wonk=0.02))
            parts.append(box("pin_cap", (0.6, 0.6, 0.12), (x, py_, top + 3.04), stone, bevel=0.02, seg=1))
            parts.append(pyramid("pin_top", (0.34, 0.34, 0.8), (x, py_, top + 3.16), stone, apex=0.03))
            parts.append(sphere("pin_ball", 0.13, (x, py_, top + 4.05), M("gold", 0.35), seg=10, rings=6))
        for i in range(n):
            x = -width / 2 + (width / n) * (i + 0.5)
            parts.append(cyl("cren", (width / n) * 0.36, 0.3, (x, py_, top + 2.08), stone, verts=16, rot=(math.pi / 2, 0, 0), center=True, bevel=0.02, seg=1))
        parts.append(roof("lowroof", width, D - 1.5, 1.4, (0, 0.6, top + 1.7), M("tile_dark"), sag=0.05, flare=0.05, courses=3))
        chimney(parts, -width * 0.25, 1.5, top + 1.5, h=2.2)
        roof_top = top + 3.7
    else:  # mansard
        parts.append(roof("mansard_lo", width + 0.9, Wr, 2.8, (0, yc, top), M("tile"), sag=0.08, flare=-0.05, top_w=Wr * 0.5, courses=4))
        parts.append(roof("mansard_hi", width + 0.9, Wr * 0.5, 2.2, (0, yc, top + 2.8), M("tile_dark"), sag=0.12, flare=0.1, courses=2, ridge=True))
        for x in xs:
            dormer(parts, x, yfront + 0.05, top + 0.3, 1.2, 1.55, plaster, M("lead"), depth=1.9, warm=RNG.random() < 0.4)
        chimney(parts, -width * 0.3, 1.0, top + 2.6, h=2.4)
        roof_top = top + 4.9

    parts.append(box("snow_c", (wtop + 0.7, dtop + 0.7, 0.035), (0, yc, body_h + 0.45), M("snow"), bevel=0.015, seg=1, wonk=0.01))

    visual = join(parts, name)
    lean_x, lean_y = RNG.uniform(-0.0125, 0.0125), RNG.uniform(-0.01, 0.0025)
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

    parts.append(box("snow", (L + 0.8, W + 0.8, 0.1), (0, 0, H + 0.35), M("snow"), bevel=0.04, seg=1, wonk=0.03))
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
            win_unit(parts, face, plane, a, zb, w, h, sh, surround=None, sill=True, cross=True, snow=True)
    for sx in (-1, 1):
        face = "-X" if sx < 0 else "+X"
        plane = sx * (NW / 2 + 3.0)
        parts.append(box("aisle", (3.0 - REV, NL - 2, NH * 0.6), (sx * (NW / 2 + 1.5 - REV / 2), 2, 0), brick, bevel=0.08, seg=1, wonk=0.04))
        col.append(box("c", (3.0, NL - 2, NH * 0.6), (sx * (NW / 2 + 1.5), 2, 0)))
        ops = [(sx * y, 2.0, 1.7, 7.2, "pointed") for y in ys]
        a0, a1 = sorted((sx * (-NL / 2 + 3), sx * (NL / 2 + 1)))
        parts.append(facade("aisle_face", brick, face, plane, a0 - 0.01, a1 + 0.01, 0.0, NH * 0.6, ops))
        for (a, zb, w, h, sh) in ops:
            win_unit(parts, face, plane, a, zb, w, h, sh, surround=None, cross=True)
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
        wx, wy = (NW / 2 - 1.02) * math.cos(a + math.pi / 10), NL / 2 + 2 + (NW / 2 - 1.02) * math.sin(a + math.pi / 10)
        parts.append(cbox("apse_win", (1.2, 0.08, 6.5), (wx, wy, 7.5), M("glass"), rot=(0, 0, a + math.pi / 10 - math.pi / 2)))

    # west front between the towers: a tall pointed window over the stepped portal
    fo = [(0.0, 8.8, 3.0, 7.6, "pointed")]
    parts.append(facade("west", brick, "-Y", front, -2.45, 2.45, 0.0, NH, fo))
    win_unit(parts, "-Y", front, 0.0, 8.8, 3.0, 7.6, "pointed", warm=True, surround=None, cross=True)
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
            win_unit(parts, "-Y", tf, a, zb, w, h, sh, surround=None, cross=False)
        sface, splane = ("-X", x - 3.1) if tall else ("+X", x + 3.1)
        sa = -(front - 1.0) if tall else (front - 1.0)
        sops = [(sa, zz, 1.4, 4.0, "pointed") for zz in zz_list]
        parts.append(facade("tower_s", brick, sface, splane, sa - 3.11, sa + 3.11, 0.0, TH, sops))
        for (a, zb, w, h, sh) in sops:
            win_unit(parts, sface, splane, a, zb, w, h, sh, surround=None, cross=False)
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
    parts.append(sphere("ts_dome", 3.5, (x, front - 1.0, 27.6), M("copper", 0.5), seg=24, rings=14, zscale=0.95))
    parts.append(cyl("ts_lantern", 1.0, 2.6, (x, front - 1.0, 30.6), stone, verts=10, bevel=0.03, seg=1))
    parts.append(cyl("ts_lantop", 1.3, 1.8, (x, front - 1.0, 33.2), M("copper", 0.5), verts=10, r2=0.05, bevel=0.02, seg=1))
    parts.append(cyl("ts_clock", 1.3, 0.25, (x, front - 4.2, 20.0), M("plaster_white"), verts=24, rot=(math.pi / 2, 0, 0), center=True, bevel=0.02, seg=1))
    parts.append(torus("ts_clockrim", 1.3, 0.1, (x, front - 4.3, 20.0), M("gold", 0.4), rot=(math.pi / 2, 0, 0), seg=24, mseg=6))
    parts.append(arch("portal", 4.4, 8.0, 0.7, (0, front - 0.35, 0), stone, bevel=0.05, seg=1))
    parts.append(arch("portal2", 3.6, 7.4, 0.5, (0, front - 0.45, 0), M("stone_dark"), bevel=0.04, seg=1))
    parts.append(arch("door", 2.9, 6.8, 0.3, (0, front - 0.55, 0), M("wood_dark"), bevel=0.02, seg=1))
    for zz in (1.2, 3.0, 4.8):
        parts.append(box("dstrap", (2.6, 0.04, 0.1), (0, front - 0.72, zz), M("iron")))
    parts.append(box("dsplit", (0.06, 0.04, 5.3), (0, front - 0.72, 0), M("iron")))
    parts.append(roof("gable", 1.2, NW + 0.8, 9.5, (0, front + 0.6, NH), bdark, sag=0.0, flare=0.12, cuts=2, along_x=False))
    parts.append(box("snow", (NW + 0.8, NL, 0.1), (0, 2, NH + 0.02), M("snow"), bevel=0.03, seg=1))
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
    tower.append(sphere("onion", 3.7, (0, 0, 28.6), M("copper", 0.5), seg=24, rings=14, zscale=1.15))
    tower.append(cyl("onion_neck", 1.4, 2.2, (0, 0, 31.9), stone, verts=10, bevel=0.03, seg=1))
    tower.append(sphere("onion2", 1.7, (0, 0, 34.7), M("copper", 0.5), seg=20, rings=12, zscale=1.2))
    tower.append(cyl("spike", 0.18, 3.0, (0, 0, 36.3), M("gold", 0.4), verts=8, r2=0.02, bevel=0))
    tower.append(sphere("ball", 0.5, (0, 0, 37.8), M("gold", 0.4), seg=12, rings=8))
    tower.append(box("snow", (7.4, 7.4, 0.1), (0, 0, 24.0), M("snow"), bevel=0.03, seg=1))
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
    parts.append(sphere("dome", 3.8, (0, 0, 7.4), M("copper", 0.5), seg=24, rings=14, zscale=0.85))
    parts.append(cyl("lantern", 0.9, 1.6, (0, 0, 10.4), white, verts=10, bevel=0.03, seg=1))
    parts.append(cyl("lantop", 1.2, 1.3, (0, 0, 12.0), M("copper", 0.5), verts=10, r2=0.03, bevel=0.02, seg=1))
    parts.append(box("snow", (7.3, 7.3, 0.1), (0, 0, 5.3), M("snow"), bevel=0.03, seg=1))
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


def well():
    reset()
    stone = M("stone_dark")
    parts = []
    for k in range(8):
        a = math.tau * k / 8
        parts.append(cbox("stone", (0.95, 0.55, 0.5), (1.15 * math.cos(a), 1.15 * math.sin(a), 0.25), stone, rot=(0, 0, a + math.pi / 2), bevel=0.04, seg=1, wonk=0.03))
        parts.append(cbox("stone", (0.95, 0.55, 0.5), (1.15 * math.cos(a + math.pi / 8), 1.15 * math.sin(a + math.pi / 8), 0.75), stone, rot=(0, 0, a + math.pi / 8 + math.pi / 2), bevel=0.04, seg=1, wonk=0.03))
    parts.append(cyl("hole", 1.0, 0.05, (0, 0, 0.9), M("void"), verts=16, bevel=0))
    for sx in (-1, 1):
        parts.append(cyl("post", 0.09, 2.4, (sx * 1.1, 0, 1.0), M("wood_dark"), verts=8, bevel=0.01, seg=1))
    parts.append(cyl("beam", 0.08, 2.6, (0, 0, 3.35), M("wood_dark"), verts=8, rot=(0, math.pi / 2, 0), center=True, bevel=0.01, seg=1))
    parts.append(roof("wroof", 3.2, 1.8, 0.9, (0, 0, 3.45), M("tile_dark"), sag=0.05, flare=0.12, cuts=3, courses=2))
    parts.append(roof("wroof_snow", 3.2, 1.7, 0.95, (0, 0, 3.48), M("snow"), sag=0.05, flare=0.12, cuts=3, top_w=0.3))
    parts.append(cyl("windlass", 0.14, 2.0, (0, 0, 2.9), M("wood"), verts=10, rot=(0, math.pi / 2, 0), center=True, bevel=0.01, seg=1))
    parts.append(cyl("rope", 0.015, 1.2, (0, 0, 1.78), M("canvas"), verts=6))
    parts.append(cyl("bucket", 0.16, 0.3, (0, 0, 1.5), M("wood"), verts=10, r2=0.14, bevel=0.01, seg=1))
    export("well", join(parts, "well"), cyl("c", 1.4, 1.0, (0, 0, 0), None, verts=8))


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
    parts.append(roof("lowroof", W - 0.4, D - 0.6, 1.8, (0, 0, A0 + 0.5), M("tile_dark"), along_x=False, sag=0.03, flare=0.03, courses=2))
    parts.append(box("snow", (W + 0.5, D + 0.5, 0.06), (0, 0, A0 + 2.58), M("snow")))
    # women's annex against the west side
    ax = -W / 2 - 3.2
    parts.append(box("annex", (4.0, 10.0, 5.0), (ax, 2.0, 0), M("plaster_grey"), bevel=0.05, seg=1, wonk=0.04))
    col.append(box("c", (4.0, 10.0, 5.0), (ax, 2.0, 0)))
    parts.append(facade("annex_f", M("plaster_grey"), "-Y", 2.0 - 5.0 - 0.001, ax - 2.01, ax + 2.01, 0, 5.0, [(ax, 1.8, 0.8, 1.4, "round")]))
    win_unit(parts, "-Y", 2.0 - 5.0 - 0.001, ax, 1.8, 0.8, 1.4, "round", surround=None)
    parts.append(roof("annex_roof", 10.4, 4.6, 1.5, (ax, 2.0, 5.0), M("tile"), along_x=False, sag=0.03, flare=0.03, courses=2))
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
TEX_OF.update({"bolt_red": "cloth", "bolt_blue": "cloth", "bolt_green": "cloth", "linen": "cloth",
               "sacking": "cloth", "snow_dirty": "snow", "coach_green": "oak", "coach_red": "oak"})
TINT.update({"bark": (0.52, 0.47, 0.42), "snow_dirty": (0.68, 0.66, 0.64), "sacking": (0.80, 0.70, 0.52),
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
    ring = cyl("snow_ring", trunk_r * 3.2, 0.04, (0, 0, -0.02), M("snow_dirty"), verts=12, bevel=0)
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


def shrub_tub():
    """Clipped yew in an oak tub, snow on its shoulders: flanks a door."""
    reset()
    parts = []
    _tub(parts, 0.55, 0.5)
    parts.append(cyl("stem", 0.04, 0.3, (0, 0, 0.55), M("bark"), verts=6))
    parts.append(_lumpy("yew", 0.34, (0, 0, 1.05), M("yew"), zscale=1.7, amp=0.12, seed=3, seg=14, rings=10))
    parts.append(_lumpy("yew_top", 0.16, (0.02, 0.0, 1.62), M("yew"), zscale=1.3, amp=0.15, seed=4, seg=10, rings=6))
    parts.append(_lumpy("snow", 0.22, (0.02, 0.0, 1.66), M("snow"), zscale=0.55, amp=0.14, seed=5, seg=10, rings=6))
    parts.append(_lumpy("snow2", 0.25, (-0.05, 0.03, 1.36), M("snow"), zscale=0.28, amp=0.18, seed=6, seg=10, rings=6))
    export("shrub_tub", join(parts, "shrub_tub"), box("c", (0.65, 0.65, 1.2), (0, 0, 0)))


def shrub_juniper():
    """Upright juniper in a round tub: a darker, narrower evergreen."""
    reset()
    parts = [cyl("tub", 0.28, 0.45, (0, 0, 0), M("wood"), verts=14, r2=0.33, bevel=0.01, seg=1)]
    for zz in (0.08, 0.37):
        parts.append(cyl("hoop", 0.3 + zz * 0.1, 0.04, (0, 0, zz), M("iron", 0.5), verts=14, bevel=0))
    parts.append(cyl("soil", 0.31, 0.02, (0, 0, 0.43), M("soil"), verts=14, bevel=0))
    parts.append(_lumpy("jun", 0.24, (0, 0, 1.1), M("juniper"), zscale=2.8, amp=0.14, seed=8, seg=12, rings=12))
    parts.append(_lumpy("snow", 0.14, (0.03, -0.02, 1.62), M("snow"), zscale=0.7, amp=0.2, seed=9, seg=8, rings=6))
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
    parts.append(_bm_obj("rosemary", bm, M("rosemary")))
    parts.append(_lumpy("rosemary_body", 0.13, (-0.28, 0, 0.42), M("rosemary"), zscale=0.9, amp=0.25, seed=32, seg=10, rings=6))
    parts.append(_lumpy("rsnow", 0.1, (-0.28, 0, 0.52), M("snow"), zscale=0.4, amp=0.25, seed=33, seg=8, rings=5))
    _pot(parts, 0.17, 0.4, (0.22, 0.02, 0))
    parts.append(cyl("bay_stem", 0.018, 0.75, (0.22, 0.02, 0.38), M("bark"), verts=6))
    parts.append(_lumpy("bay", 0.22, (0.22, 0.02, 1.22), M("bay_leaf"), amp=0.12, seed=34, seg=12, rings=8))
    parts.append(_lumpy("bsnow", 0.15, (0.22, 0.02, 1.38), M("snow"), zscale=0.45, amp=0.2, seed=35, seg=8, rings=5))
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


def awning_striped():
    """Striped canvas awning on iron arms with a scalloped valance and snow along the top.
    Origin = top edge on the wall; 2.0 m wide, projects 1.15 m and drops 0.5 m."""
    reset()
    W, D, drop = 2.0, 1.15, 0.5
    ang = math.atan2(drop, D)
    L = math.hypot(D, drop)
    parts = []
    n = 8
    for k in range(n):
        x = -W / 2 + W / n * (k + 0.5)
        mat = M("canvas_stripe") if k % 2 else M("canvas")
        parts.append(cbox("stripe", (W / n + 0.002, L, 0.02), (x, -D / 2, -drop / 2), mat, rot=(ang, 0, 0)))
        parts.append(box("valance", (W / n, 0.02, 0.2), (x, -D, -drop - 0.2), mat))
        parts.append(cyl("scallop", W / n / 2, 0.02, (x, -D, -drop - 0.2), mat, verts=10, rot=(math.pi / 2, 0, 0), center=True))
    parts.append(box("roller", (W + 0.1, 0.1, 0.1), (0, -0.05, -0.05), M("wood_dark"), bevel=0.01, seg=1))
    for sx in (-1, 1):
        bm = bmesh.new()
        _tube(bm, (sx * W / 2, 0, -0.9), (sx * W / 2, -D, -drop), 0.015, 0.015, 5)
        _tube(bm, (sx * W / 2, 0, 0), (sx * W / 2, -D, -drop), 0.012, 0.012, 5)
        parts.append(_bm_obj("arm", bm, M("iron")))
    parts.append(cbox("snow", (W - 0.05, L * 0.7, 0.05), (0, -D * 0.4, -drop * 0.4 + 0.035), M("snow"), rot=(ang, 0, 0), bevel=0.02, seg=1))
    export("awning_striped", join(parts, "awning_striped"))


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
    """Old snow shovelled to the wall foot and packed by boots: an irregular slush apron with footprints, lying
    just proud of the setts. Origin = on the wall at the pavement; 3 m along the wall, up to 1.5 m out."""
    reset()
    rng = random.Random(191)
    bm = bmesh.new()
    n = 24
    ring = []
    for k in range(n):
        t = k / (n - 1)
        x = -1.5 + 3.0 * t
        y = -(0.5 + 0.9 * math.sin(math.pi * t) * rng.uniform(0.7, 1.1))
        ring.append((x, y))
    outline_pts = [(-1.5, 0.0)] + ring + [(1.5, 0.0)]
    c = bm.verts.new((0, -0.3, 0.012))
    vs = [bm.verts.new((x, y, 0.006 if y < -0.05 else 0.03)) for x, y in outline_pts]
    for a, b in zip(vs, vs[1:]):
        bm.faces.new((c, a, b))
    bm.faces.new((c, vs[-1], vs[0]))
    parts = [_bm_obj("slush", bm, M("snow_dirty"))]
    parts.append(_lumpy("drift", 0.5, (0.0, -0.12, 0.0), M("snow"), zscale=0.3, amp=0.2, seed=192, seg=14, rings=6, zmin=-0.01))
    edit_verts(parts[-1], lambda co: setattr(co, "x", co.x * 2.4))
    fp = bmesh.new()
    for k in range(14):
        x = rng.uniform(-1.3, 1.3)
        y = -rng.uniform(0.25, 1.1)
        a = rng.uniform(0, math.tau)
        ux, uy = math.cos(a), math.sin(a)
        pts = [(-0.05, -0.12), (0.05, -0.12), (0.055, 0.1), (-0.055, 0.1)]
        _quad(fp, [(x + px * ux - py * uy, y + px * uy + py * ux, 0.016) for px, py in pts])
    parts.append(_bm_obj("prints", fp, M("mud")))
    export("trampled_snow", join(parts, "trampled_snow"))


def laundry_line():
    """Washing frozen stiff on a line from a wall hook out to a forked pole: two sheets, a shirt and a petticoat.
    Origin = under the wall hook at the pavement; the line runs 6 m out from the wall (-Y) at 3.2 m and sags."""
    reset()
    Ly, H = 6.0, 3.2

    def zline(d):
        return H - 0.45 * math.sin(math.pi * d / Ly)
    parts = [box("wall_hook", (0.06, 0.1, 0.06), (0, -0.05, H - 0.03), M("iron"))]
    bm = bmesh.new()
    pts = [Vector((0, -Ly * k / 12, zline(Ly * k / 12))) for k in range(13)]
    for a, b in zip(pts, pts[1:]):
        _tube(bm, a, b, 0.008, 0.008, 4)
    parts.append(_bm_obj("line", bm, M("sacking")))
    bm = bmesh.new()
    _tube(bm, (0, -Ly, 0), (0, -Ly, H + 0.2), 0.05, 0.04, 6)
    _tube(bm, (0, -Ly, H), (0, -Ly + 0.12, H + 0.3), 0.03, 0.02, 5)
    parts.append(_bm_obj("pole", bm, M("wood_dark")))
    rng = random.Random(201)
    items = [(0.6, 1.1, 1.3, "linen"), (1.9, 1.1, 1.2, "linen"), (3.2, 0.7, 0.8, "plaster_white"), (4.2, 0.8, 1.0, "sacking")]
    for (d0, w, h, mat) in items:
        sheet = bmesh.new()
        nx, nz = 5, 4
        grid = []
        for i in range(nx + 1):
            col = []
            for j in range(nz + 1):
                d = d0 + w * i / nx
                z = zline(d) - h * j / nz
                x = 0.05 * math.sin(i * 1.7 + j * 0.9) + rng.uniform(-0.015, 0.015) + 0.04 * j / nz
                col.append(sheet.verts.new((x, -d, z)))
            grid.append(col)
        for i in range(nx):
            for j in range(nz):
                sheet.faces.new((grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]))
        parts.append(_bm_obj("sheet", sheet, M(mat)))
        for pd in (d0 + 0.05, d0 + w - 0.05):
            parts.append(box("peg", (0.03, 0.02, 0.08), (0, -pd, zline(pd) - 0.05), M("wood")))
    parts.append(cyl("pole_foot", 0.2, 0.05, (0, -Ly, -0.01), M("snow_dirty"), verts=8))
    export("laundry_line", join(parts, "laundry_line"), box("c", (0.2, 0.2, H), (0, -Ly, 0)))


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
    """3 m of clipped box hedge, knee to waist high, with snow lying on its flat top."""
    reset()
    h = _lumpy("hedge", 0.5, (0, 0, 0.42), M("yew"), amp=0.06, seed=211, seg=16, rings=8, zmin=0.0)
    edit_verts(h, lambda co: (setattr(co, "x", co.x * 3.0), setattr(co, "y", co.y * 0.75), setattr(co, "z", min(co.z * 1.0, 0.85))))
    snow = _lumpy("snow", 0.5, (0, 0, 0.84), M("snow"), zscale=0.12, amp=0.1, seed=212, seg=16, rings=6)
    edit_verts(snow, lambda co: (setattr(co, "x", co.x * 2.95), setattr(co, "y", co.y * 0.7)))
    export("hedge", join([h, snow], "hedge"), box("c", (3.0, 0.75, 0.9), (0, 0, 0)))


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
    ("trampled_snow", trampled_snow), ("laundry_line", laundry_line), ("park_railing", park_railing), ("hedge", hedge),
    ("lawn_snow", lawn_snow), ("gravel_path", gravel_path),
]


BUILDS = [
    ("tenement_a", lambda: tenement("tenement_a", 10.0, 3, "gable", "plaster_ochre", bays=3, shutters=True)),
    ("tenement_b", lambda: tenement("tenement_b", 8.0, 3, "attyka", "plaster_rose", bays=2)),
    ("tenement_c", lambda: tenement("tenement_c", 12.0, 4, "mansard", "plaster_cream", bays=3, pilasters=True, arched_windows=True)),
    ("tenement_d", lambda: tenement("tenement_d", 10.0, 3, "attyka", "plaster_sage", bays=3, arched_windows=True, shutters=True)),
    ("tenement_e", lambda: tenement("tenement_e", 8.0, 4, "gable", "plaster_blue", bays=2, shutters=True)),
    ("sukiennice", sukiennice), ("st_marys", st_marys), ("town_hall", town_hall), ("st_adalbert", st_adalbert),
    ("market_stall", market_stall), ("barrel", barrel), ("crate_stack", crate_stack), ("cart", cart), ("well", well),
    ("lantern_post", lantern_post), ("brazier", brazier), ("ground_cobbles", ground_cobbles),
] + globals().get("DISTRICT_BUILDS", []) + globals().get("FARM_BUILDS", []) + globals().get("DRESSING_BUILDS", [])


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
        for name, fn in BUILDS:
            if only and name not in only:
                continue
            fn()
        print("[assets] tris", " ".join("%s=%d" % kv for kv in TRI_LOG.items()))
    print("[assets] done in %.1fs" % (time.time() - t0))
