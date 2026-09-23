"""Procedural placeholder assets for Krakow 1795.

Run:  blender -b --python assets/blender/build_assets.py
Writes one .glb per asset into assets/models/ and saves assets/blender/placeholders.blend.
Each asset is a proper mesh (not CSG) so it can be hand-edited in Blender later.
Collision meshes carry the -col suffix; Godot turns them into StaticBody3D colliders on import.
"""
import bpy
import bmesh
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "models")
os.makedirs(OUT, exist_ok=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, rgb, rough=0.9):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return m


def box(name, size, loc=(0, 0, 0), material=None, parent=None):
    """Axis-aligned box. size=(x,y,z) in metres, loc is the base-centre (sits on z=loc.z)."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(loc[0], loc[1], loc[2] + size[2] / 2))
    o = bpy.context.object
    o.name = name
    o.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(scale=True)
    if material:
        o.data.materials.append(material)
    if parent:
        o.parent = parent
    return o


def cylinder(name, r, h, loc=(0, 0, 0), material=None, parent=None, verts=16):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=h, location=(loc[0], loc[1], loc[2] + h / 2))
    o = bpy.context.object
    o.name = name
    if material:
        o.data.materials.append(material)
    if parent:
        o.parent = parent
    return o


def empty(name):
    o = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(o)
    return o


def join(objs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    j = bpy.context.object
    j.name = name
    return j


def export(name):
    path = os.path.join(OUT, name + ".glb")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True,
                              export_apply=True, export_yup=True)
    print("[assets] wrote", path)


# ---------------------------------------------------------------- assets

def tenement():
    """3-storey Rynek tenement module. 12 m wide, 8 m deep, 11.5 m to eaves plus attic roof.
    Ground floor arcade of 3 arches (approximated as square openings), windows above, steep roof."""
    reset()
    plaster = mat("plaster", (0.78, 0.70, 0.58))
    stone = mat("stone", (0.45, 0.42, 0.38))
    roof = mat("roof_tile", (0.42, 0.20, 0.14))
    wood = mat("wood_dark", (0.22, 0.14, 0.08))

    W, D, FLOOR = 12.0, 8.0, 3.5
    parts = []
    # Ground floor: three piers + back wall + lintel (arcade you can walk under, 2.4 m deep)
    for i, x in enumerate((-5.5, -1.5, 2.5)):
        parts.append(box(f"pier{i}", (1.0, 2.4, FLOOR), (x + 0.5 - 0.5, -D / 2 + 1.2, 0), stone))
    parts.append(box("pier3", (1.0, 2.4, FLOOR), (5.5, -D / 2 + 1.2, 0), stone))
    parts.append(box("gf_back", (W, D - 2.4, FLOOR), (0, 1.2, 0), plaster))
    parts.append(box("gf_lintel", (W, 2.4, 0.6), (0, -D / 2 + 1.2, FLOOR - 0.6), stone))
    # Upper floors as one mass with window recesses cut by simple inset boxes (dark)
    parts.append(box("upper", (W, D, FLOOR * 2), (0, 0, FLOOR), plaster))
    for f in range(2):
        for x in (-4.0, -1.3, 1.3, 4.0):
            parts.append(box(f"win_{f}_{x}", (1.2, 0.15, 1.8), (x, -D / 2 - 0.05, FLOOR * (1 + f) + 1.0), wood))
    # Attic + gabled roof (a wedge)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, FLOOR * 3 + 2.0))
    r = bpy.context.object
    r.name = "roof"
    r.scale = (W + 0.6, D + 0.6, 4.0)
    bpy.ops.object.transform_apply(scale=True)
    bm = bmesh.new()
    bm.from_mesh(r.data)
    for v in bm.verts:
        if v.co.z > 0:
            v.co.y = 0.0
    bm.to_mesh(r.data)
    bm.free()
    r.data.materials.append(roof)
    parts.append(r)
    # Cornice
    parts.append(box("cornice", (W + 0.4, D + 0.4, 0.3), (0, 0, FLOOR * 3 - 0.3), stone))

    visual = join(parts, "tenement")
    # Collision: coarse shell (arcade open) so the player can walk under the arches.
    col = [box("tenement-col_a", (1.0, 2.4, FLOOR), (-5.5, -D / 2 + 1.2, 0)),
           box("tenement-col_b", (1.0, 2.4, FLOOR), (-1.5, -D / 2 + 1.2, 0)),
           box("tenement-col_c", (1.0, 2.4, FLOOR), (2.5, -D / 2 + 1.2, 0)),
           box("tenement-col_d", (1.0, 2.4, FLOOR), (5.5, -D / 2 + 1.2, 0)),
           box("tenement-col_e", (W, D - 2.4, FLOOR), (0, 1.2, 0)),
           box("tenement-col_f", (W, D, FLOOR * 2 + 4), (0, 0, FLOOR - 0.6))]
    c = join(col, "tenement-col")
    c.parent = visual
    c.display_type = "WIRE"
    export("tenement")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "assets", "blender", "tenement.blend"))


def arcade_segment():
    """Sukiennice arcade: 4 m tileable segment. Column + arch + parapet. Walk-through."""
    reset()
    stone = mat("stone_pale", (0.62, 0.58, 0.50))
    parts = [box("col", (0.8, 0.8, 5.0), (0, 0, 0), stone),
             box("arch_beam", (4.0, 0.8, 0.8), (2.0, 0, 5.0), stone),
             box("parapet", (4.0, 0.3, 1.0), (2.0, 0, 5.8), stone)]
    v = join(parts, "arcade_segment")
    c = join([box("arcade_segment-col_a", (0.8, 0.8, 5.0), (0, 0, 0)),
              box("arcade_segment-col_b", (4.0, 0.8, 1.8), (2.0, 0, 5.0))], "arcade_segment-col")
    c.parent = v
    export("arcade_segment")


def market_stall():
    """Market stall with canvas roof. Crouch cover 1.1 m at the counter."""
    reset()
    wood = mat("wood", (0.45, 0.32, 0.20))
    canvas = mat("canvas", (0.70, 0.62, 0.48), 1.0)
    parts = [box("counter", (2.4, 1.2, 1.1), (0, 0, 0), wood)]
    for x in (-1.1, 1.1):
        for y in (-0.5, 0.5):
            parts.append(box(f"post{x}{y}", (0.1, 0.1, 2.3), (x, y, 0), wood))
    parts.append(box("awning", (2.8, 1.6, 0.06), (0, 0, 2.3), canvas))
    v = join(parts, "market_stall")
    c = box("market_stall-col", (2.4, 1.2, 1.1), (0, 0, 0))
    c.parent = v
    export("market_stall")


def barrel():
    reset()
    wood = mat("barrel_wood", (0.40, 0.28, 0.16))
    iron = mat("iron", (0.15, 0.15, 0.16), 0.5)
    body = cylinder("body", 0.45, 1.0, material=wood, verts=14)
    # Bulge middle
    bm = bmesh.new()
    bm.from_mesh(body.data)
    for vtx in bm.verts:
        if abs(vtx.co.z) < 0.01:
            pass
    bm.free()
    hoops = [cylinder(f"hoop{i}", 0.47, 0.06, (0, 0, z), iron, verts=14) for i, z in enumerate((0.15, 0.8))]
    v = join([body] + hoops, "barrel")
    c = cylinder("barrel-col", 0.47, 1.0, verts=8)
    c.parent = v
    export("barrel")


def lantern_post():
    reset()
    iron = mat("iron_black", (0.08, 0.08, 0.09), 0.6)
    glass = mat("lantern_glass", (1.0, 0.8, 0.5), 0.2)
    glass.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1.0, 0.7, 0.35, 1)
    glass.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 4.0
    parts = [cylinder("post", 0.06, 3.0, material=iron, verts=8),
             box("arm", (0.6, 0.06, 0.06), (0.3, 0, 2.9), iron),
             box("lamp", (0.3, 0.3, 0.4), (0.6, 0, 2.5), glass),
             box("cap", (0.4, 0.4, 0.08), (0.6, 0, 2.9), iron)]
    v = join(parts, "lantern_post")
    c = cylinder("lantern_post-col", 0.08, 3.0, verts=6)
    c.parent = v
    export("lantern_post")


def figure(name, coat_rgb, hat=True):
    """Simple humanoid placeholder, 1.8 m, origin at feet, faces -Y in Blender (= -Z in Godot)."""
    reset()
    coat = mat(name + "_coat", coat_rgb)
    skin = mat("skin", (0.80, 0.62, 0.50))
    dark = mat("dark", (0.12, 0.10, 0.08))
    parts = [box("legs", (0.4, 0.25, 0.85), (0, 0, 0), dark),
             box("torso", (0.5, 0.3, 0.65), (0, 0, 0.85), coat),
             box("arm_l", (0.12, 0.12, 0.6), (-0.32, 0, 0.9), coat),
             box("arm_r", (0.12, 0.12, 0.6), (0.32, 0, 0.9), coat),
             box("head", (0.22, 0.22, 0.25), (0, 0, 1.52), skin)]
    if hat:
        parts.append(box("hat", (0.36, 0.36, 0.06), (0, 0, 1.76), dark))
        parts.append(box("crown", (0.2, 0.2, 0.12), (0, 0, 1.80), dark))
    v = join(parts, name)
    export(name)


def church_mass():
    """St Mary's stand-in: nave plus two unequal towers. Silhouette only."""
    reset()
    brick = mat("brick", (0.50, 0.28, 0.20))
    roof = mat("roof_green", (0.20, 0.35, 0.28))
    parts = [box("nave", (12, 28, 20), (0, 0, 0), brick),
             box("tower_n", (5, 5, 62), (-4.5, -16, 0), brick),
             box("tower_s", (5, 5, 48), (4.5, -16, 0), brick),
             box("spire_base", (4, 4, 6), (-4.5, -16, 62), roof),
             box("nave_roof", (13, 29, 8), (0, 0, 20), roof)]
    bpy.ops.object.select_all(action="DESELECT")
    v = join(parts, "church_mass")
    c = join([box("church_mass-col_a", (12, 28, 28), (0, 0, 0)),
              box("church_mass-col_b", (5, 5, 62), (-4.5, -16, 0)),
              box("church_mass-col_c", (5, 5, 48), (4.5, -16, 0))], "church_mass-col")
    c.parent = v
    export("church_mass")


if __name__ == "__main__":
    tenement()
    arcade_segment()
    market_stall()
    barrel()
    lantern_post()
    figure("watchman", (0.88, 0.88, 0.92))
    figure("player_figure", (0.25, 0.30, 0.55), hat=False)
    church_mass()
    print("[assets] done")
