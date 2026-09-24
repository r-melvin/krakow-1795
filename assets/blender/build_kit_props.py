"""The player's kit for Krakow 1795 (scripts/stealth/kit.gd, pickup.gd, distraction.gd): what a townsman conspirator
carries in a coat in 1795. Each prop well under 1k triangles.

Run:  blender -b --python assets/blender/build_kit_props.py [-- --only kit_knife,kit_pistol]
Writes assets/models/kit_*.glb. Reuses the helpers, palette and baked texture cache of build_assets.py (loaded with
importlib; that file is not modified).

Conventions (as build_assets.py): metres, Blender Z up, glTF maps Blender (x, y, z) -> Godot (x, z, -y).
- Held things (knife, cudgel, pistol, musket): origin at the middle of the grip, the business end along Blender +Z
  (Godot +Y), the edge / trigger guard toward Blender -Y (Godot +Z). player.gd puts them on a BoneAttachment3D.
- Loose things (stone, bottle, coin, ring-bread, charges, pouch): origin at the bottom centre, resting on the ground.
"""
import importlib.util
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("build_assets", os.path.join(HERE, "build_assets.py"))
ba = importlib.util.module_from_spec(_spec)
sys.modules["build_assets"] = ba
_spec.loader.exec_module(ba)

box, cbox, cyl, sphere, torus, blob, join, export, M = ba.box, ba.cbox, ba.cyl, ba.sphere, ba.torus, ba.blob, ba.join, ba.export, ba.M
reset, edit_verts = ba.reset, ba.edit_verts
PI = math.pi

ba.PAL.update({
    "steel": (0.62, 0.63, 0.66), "horn": (0.22, 0.16, 0.10), "brass_kit": (0.72, 0.56, 0.26), "leather_kit": (0.30, 0.19, 0.10),
    "bottle_glass": (0.14, 0.28, 0.16), "cork": (0.62, 0.48, 0.30), "paper_charge": (0.86, 0.80, 0.66), "twine": (0.55, 0.45, 0.30),
    "ring_bread": (0.70, 0.46, 0.20), "flint_stone": (0.46, 0.44, 0.41), "coin_silver": (0.78, 0.76, 0.70), "ash_wood": (0.52, 0.38, 0.22),
})
ba.TEX_OF.update({"steel": "metal", "brass_kit": "metal", "coin_silver": "metal", "leather_kit": "cloth", "ash_wood": "oak",
                  "flint_stone": "sandstone"})
ba.TINT.update({"steel": (0.85, 0.86, 0.9), "brass_kit": (0.95, 0.8, 0.5), "coin_silver": (0.95, 0.95, 0.95)})


def kit_knife():
    """A clasp-less working knife: horn grip with brass bolster, a 13 cm clip-point blade."""
    reset()
    parts = [cyl("grip", 0.013, 0.11, (0, 0, -0.055), M("horn", 0.6), verts=8),
             cyl("bolster", 0.015, 0.012, (0, 0, 0.055), M("brass_kit", 0.35), verts=8)]
    blade = box("blade", (0.004, 0.026, 0.13), (0, 0.0, 0.067), M("steel", 0.25))

    def taper(co):
        t = max(0.0, (co.z - 0.067) / 0.13)
        co.y = co.y * (1.0 - 0.85 * t) - 0.004 * t
    edit_verts(blade, taper)
    parts.append(blade)
    export("kit_knife", join(parts, "kit_knife"))


def kit_cudgel():
    """A blackthorn cudgel: 60 cm, a knob at the head, a wrist thong."""
    reset()
    parts = [cyl("shaft", 0.016, 0.62, (0, 0, -0.12), M("ash_wood", 0.8), verts=8, r2=0.022),
             sphere("knob", 0.038, (0, 0, 0.50), M("ash_wood", 0.8), seg=8, rings=6),
             torus("thong", 0.03, 0.004, (0, 0, -0.13), M("leather_kit", 0.9), rot=(PI / 2, 0, 0), seg=10, mseg=3)]
    export("kit_cudgel", join(parts, "kit_cudgel"))


def kit_pistol():
    """A flintlock holster pistol: walnut stock with a curved butt, iron barrel, brass furniture, the lock."""
    reset()
    wood = M("wood_dark", 0.6)
    parts = [cyl("barrel", 0.011, 0.26, (0, -0.01, 0.06), M("iron", 0.4), verts=10),
             box("fore", (0.022, 0.024, 0.20), (0, -0.01 + 0.008, 0.04), wood),
             cbox("butt", (0.028, 0.04, 0.13), (0, 0.04, -0.03), wood, rot=(-0.9, 0, 0)),
             sphere("pommel", 0.022, (0, 0.085, -0.075), M("brass_kit", 0.35), seg=8, rings=5),
             box("lock", (0.03, 0.02, 0.05), (0.012, 0.0, 0.03), M("iron", 0.45)),
             cbox("cock", (0.006, 0.02, 0.012), (0.014, 0.02, 0.08), M("iron", 0.45), rot=(0.5, 0, 0)),
             torus("guard", 0.014, 0.0025, (0, -0.03, 0.0), M("brass_kit", 0.35), rot=(0, PI / 2, 0), seg=10, mseg=3)]
    export("kit_pistol", join(parts, "kit_pistol"))


def kit_musket():
    """A guard's musket taken off him (the club): a plain stand-in, 1.5 m."""
    reset()
    parts = [box("stock", (0.04, 0.05, 1.15), (0, 0, -0.35), M("wood", 0.7)),
             cbox("butt", (0.045, 0.12, 0.28), (0, 0.03, -0.42), M("wood", 0.7)),
             cyl("barrel", 0.012, 1.05, (0, -0.02, -0.05), M("iron", 0.4), verts=8),
             box("lock", (0.03, 0.02, 0.06), (0.02, 0, -0.14), M("iron", 0.45))]
    export("kit_musket", join(parts, "kit_musket"))


def kit_stone():
    """A loose cobble chip, fist-sized."""
    reset()
    o = sphere("stone", 0.045, (0, 0, 0.035), M("flint_stone", 0.9), seg=7, rings=5)
    rng = random.Random(3)

    def lump(co):
        co.x *= 1.0 + rng.uniform(-0.15, 0.2)
        co.y *= 1.0 + rng.uniform(-0.2, 0.1)
        co.z = 0.035 + (co.z - 0.035) * 0.75
    edit_verts(o, lump)
    export("kit_stone", o)


def kit_bottle():
    """An empty green-glass wine bottle with its cork."""
    reset()
    g = M("bottle_glass", 0.12)
    parts = [cyl("body", 0.038, 0.17, (0, 0, 0), g, verts=12),
             cyl("shoulder", 0.038, 0.04, (0, 0, 0.17), g, verts=12, r2=0.015),
             cyl("neck", 0.014, 0.07, (0, 0, 0.21), g, verts=10),
             cyl("cork", 0.012, 0.018, (0, 0, 0.275), M("cork", 0.9), verts=8)]
    export("kit_bottle", join(parts, "kit_bottle"))


def kit_coin():
    """A silver złoty."""
    reset()
    export("kit_coin", cyl("coin", 0.013, 0.0025, (0, 0, 0), M("coin_silver", 0.3), verts=14))


def kit_food():
    """An obwarzanek: a poppy-seed ring-bread (the vendors' wares, thrown to dogs and urchins)."""
    reset()
    export("kit_food", torus("ring", 0.055, 0.02, (0, 0, 0.02), M("ring_bread", 0.8), seg=14, mseg=6))


def _charge(name, tint):
    """A twist of paper round a charge of powder, tied with twine; a coloured wax seal says which."""
    reset()
    parts = [sphere("twist", 0.04, (0, 0, 0.035), M("paper_charge", 0.85), seg=8, rings=6, zscale=0.8),
             cyl("neck", 0.012, 0.03, (0, 0, 0.06), M("paper_charge", 0.85), verts=6, r2=0.02),
             torus("tie", 0.013, 0.003, (0, 0, 0.065), M("twine", 0.9), seg=8, mseg=3),
             sphere("seal", 0.012, (0.0, -0.035, 0.035), M(tint, 0.4), seg=6, rings=4)]
    export(name, join(parts, name))


def kit_smoke():
    ba.PAL.setdefault("wax_grey", (0.35, 0.35, 0.38))
    _charge("kit_smoke", "wax_grey")


def kit_flash():
    ba.PAL.setdefault("wax_red", (0.62, 0.10, 0.08))
    _charge("kit_flash", "wax_red")


def kit_pouch():
    """The powder pouch worn at the hip: a leather bag with a flap and a brass stud."""
    reset()
    parts = [blob("bag", (0.12, 0.05, 0.13), (0, 0, 0), M("leather_kit", 0.9)),
             box("flap", (0.125, 0.012, 0.06), (0, -0.026, 0.08), M("leather_kit", 0.85)),
             sphere("stud", 0.008, (0, -0.034, 0.085), M("brass_kit", 0.35), seg=6, rings=4)]
    export("kit_pouch", join(parts, "kit_pouch"))


def kit_cosh():
    """A sandbag cosh: a leather sausage of sand on a short wrist loop."""
    reset()
    parts = [cyl("grip", 0.014, 0.12, (0, 0, -0.06), M("leather_kit", 0.9), verts=8),
             blob("bag", (0.06, 0.06, 0.2), (0, 0, 0.06), M("leather_kit", 0.85)),
             torus("loop", 0.028, 0.004, (0, 0, -0.07), M("leather_kit", 0.9), rot=(PI / 2, 0, 0), seg=10, mseg=3)]
    export("kit_cosh", join(parts, "kit_cosh"))


def kit_torch():
    """A pitch torch: an ash stave with a tow-and-pitch head (the flame is a light and a mesh in the game)."""
    reset()
    parts = [cyl("stave", 0.017, 0.62, (0, 0, -0.18), M("ash_wood", 0.8), verts=8),
             cyl("head", 0.035, 0.14, (0, 0, 0.40), M("soot", 0.95), verts=8, r2=0.03),
             torus("band", 0.03, 0.005, (0, 0, 0.40), M("iron", 0.5), seg=10, mseg=3)]
    export("kit_torch", join(parts, "kit_torch"))


def kit_tinderbox():
    """A tin tinderbox with a steel striker and a flint on the lid."""
    reset()
    parts = [cyl("box", 0.035, 0.025, (0, 0, 0), M("steel", 0.35), verts=12),
             box("striker", (0.05, 0.012, 0.006), (0, 0, 0.025), M("iron", 0.4)),
             sphere("flint", 0.01, (0.018, 0.01, 0.03), M("flint_stone", 0.5), seg=5, rings=3)]
    export("kit_tinderbox", join(parts, "kit_tinderbox"))


def kit_poison():
    """A small apothecary vial, dark green glass, wax-sealed."""
    reset()
    g = M("bottle_glass", 0.12)
    ba.PAL.setdefault("wax_red", (0.62, 0.10, 0.08))
    parts = [cyl("vial", 0.012, 0.05, (0, 0, 0), g, verts=8),
             cyl("neck", 0.006, 0.015, (0, 0, 0.05), g, verts=6),
             cyl("seal", 0.008, 0.008, (0, 0, 0.064), M("wax_red", 0.4), verts=6)]
    export("kit_poison", join(parts, "kit_poison"))


def kit_lockpick():
    """A ring of picks and a tension wrench."""
    reset()
    parts = [torus("ring", 0.02, 0.0025, (0, 0, 0.003), M("iron", 0.45), seg=10, mseg=3),
             box("pick", (0.004, 0.08, 0.002), (0.0, 0.05, 0.002), M("steel", 0.3)),
             box("wrench", (0.004, 0.06, 0.002), (0.01, 0.04, 0.004), M("steel", 0.3), rot=(0, 0, 0.3))]
    export("kit_lockpick", join(parts, "kit_lockpick"))


BUILDS = [("kit_knife", kit_knife), ("kit_cudgel", kit_cudgel), ("kit_pistol", kit_pistol), ("kit_musket", kit_musket),
          ("kit_stone", kit_stone), ("kit_bottle", kit_bottle), ("kit_coin", kit_coin), ("kit_food", kit_food),
          ("kit_smoke", kit_smoke), ("kit_flash", kit_flash), ("kit_pouch", kit_pouch),
          ("kit_cosh", kit_cosh), ("kit_torch", kit_torch), ("kit_tinderbox", kit_tinderbox), ("kit_poison", kit_poison),
          ("kit_lockpick", kit_lockpick)]

if __name__ == "__main__":
    only = ba._cli_list("--only")
    for name, fn in BUILDS:
        if only and name not in only:
            continue
        fn()
    print("[kit_props] tris", " ".join("%s=%d" % kv for kv in ba.TRI_LOG.items()))
