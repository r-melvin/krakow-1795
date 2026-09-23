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
    "steel": (0.55, 0.56, 0.60), "wood": (0.30, 0.18, 0.09),
}
_mats = {}


def M(key, rough=0.85):
    if key in _mats:
        return _mats[key]
    m = bpy.data.materials.new("cloth_" + key)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*COL[key], 1.0)
    b.inputs["Roughness"].default_value = rough
    _mats[key] = m
    return m


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
    for tname, w in spec.get("targets", {}).items():
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


def garment(h, rig, me, info, name, keep_fn, mat, thickness=0.012, smooth=True):
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
    sol = obj.modifiers.new("solid", "SOLIDIFY")
    sol.thickness = thickness + 0.014
    sol.offset = 0.0          # both sides of the helper surface: robust to any inward-facing helper normals
    sol.use_even_offset = False
    sol.thickness_clamp = 1.0
    sol.use_rim = True
    bpy.ops.object.modifier_apply(modifier="solid")
    if smooth:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(60))
    am = obj.modifiers.new("arm", "ARMATURE")
    am.object = rig
    obj.parent = rig
    return obj


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
        if dom in LEGS_UP and coat_len != "short":
            return co.z > hem
        return False
    out.append(garment(h, rig, me, info, "coat", coat_fn, M(coat), 0.014))

    # cuffs
    if spec.get("cuffs"):
        out.append(garment(h, rig, me, info, "cuffs", lambda i, co, g, dom: helper(g, "helper-tights") and dom in ARMS and near_hand(co), M(spec["cuffs"]), 0.016))
    else:
        out.append(garment(h, rig, me, info, "cuffs", lambda i, co, g, dom: helper(g, "helper-tights") and dom in ARMS and near_hand(co), M(coat), 0.014))

    # skirt for long coats (kontusz, sukmana, cassock, bekishe)
    if coat_len == "long":
        out.append(garment(h, rig, me, info, "skirt", lambda i, co, g, dom: helper(g, "helper-skirt"), M(coat), 0.012))

    # sash / belt
    if spec.get("sash"):
        out.append(garment(h, rig, me, info, "sash", lambda i, co, g, dom: helper(g, "helper-tights") and dom in TORSO | LEGS_UP and abs(co.z - waist_z + 0.02) < 0.07, M(spec["sash"]), 0.05))

    # collar
    if spec.get("collar"):
        out.append(garment(h, rig, me, info, "collar", lambda i, co, g, dom: helper(g, "helper-tights") and dom == "neck_01", M(spec["collar"]), 0.012))

    # breeches (hip to knee) and stockings (knee to ankle)
    breech_top = 9.0 if coat_len == "short" else (knee_z + 0.12 if coat_len == "long" else hem)
    out.append(garment(h, rig, me, info, "breeches", lambda i, co, g, dom: helper(g, "helper-tights") and (dom in LEGS_UP or (dom == "pelvis" and co.z < waist_z)) and knee_z - 0.03 < co.z <= breech_top, M(spec.get("breeches", "black")), 0.012))
    # the tights helper is open at the crotch: a fitted patch over the skin closes it
    if coat_len != "long":
        out.append(garment(h, rig, me, info, "breeches_in", lambda i, co, g, dom: skin_face(g) and dom in LEGS_UP | {"pelvis"} and knee_z + 0.05 < co.z <= min(breech_top, waist_z - 0.06), M(spec.get("breeches", "black")), 0.006))
    out.append(garment(h, rig, me, info, "stockings", lambda i, co, g, dom: helper(g, "helper-tights") and (dom in CALF or (dom in LEGS_UP and co.z <= knee_z - 0.03)) and co.z > ankle_z + spec.get("boot_height", 0.12), M(spec.get("stockings", "stocking")), 0.008))

    # boots: lower calf band of the tights + the body's own foot surface
    bh = ankle_z + spec.get("boot_height", 0.12)
    out.append(garment(h, rig, me, info, "boot_leg", lambda i, co, g, dom: helper(g, "helper-tights") and dom in CALF | FEET and co.z <= bh + 0.005, M(spec.get("boots", "leather"), 0.5), 0.022))
    out.append(garment(h, rig, me, info, "boot_foot", lambda i, co, g, dom: skin_face(g) and dom in FEET | CALF and co.z < bh, M(spec.get("boots", "leather"), 0.5), 0.014))

    # hats built on the body's own scalp faces (always fitted)
    hat = spec.get("hat")
    if hat in ("konfederatka", "krakuska", "biretta", "fur", "bonnet", "cap"):
        colour = {"konfederatka": "crimson", "krakuska": "red_cap", "biretta": "black", "fur": "fur", "bonnet": "cream", "cap": "brown_coat"}[hat]
        band_z = top_z - 0.075
        def scalp_face(g):
            return skin_face(g) and g.get("scalp", 0) > 0.5
        thick = {"fur": 0.10, "bonnet": 0.03, "cap": 0.035}.get(hat, 0.045)
        out.append(garment(h, rig, me, info, "hat", lambda i, co, g, dom: scalp_face(g) and co.z > band_z, M(colour), thick))
        if hat in ("konfederatka", "krakuska", "fur"):
            out.append(garment(h, rig, me, info, "hat_band", lambda i, co, g, dom: scalp_face(g) and band_z - 0.04 < co.z <= band_z + 0.005, M("fur" if hat != "krakuska" else "black"), 0.045))
        if hat == "bonnet":
            out.append(garment(h, rig, me, info, "hat_band", lambda i, co, g, dom: scalp_face(g) and band_z - 0.03 < co.z <= band_z + 0.005, M("cream"), 0.03))
        if hat in ("konfederatka", "krakuska", "biretta"):
            size = {"konfederatka": (0.25, 0.25, 0.10), "krakuska": (0.23, 0.23, 0.08), "biretta": (0.21, 0.21, 0.07)}[hat]
            bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.01, top_z - 0.02 + size[2] / 2))
            box = bpy.context.object
            box.scale = size
            bpy.ops.object.transform_apply(scale=True)
            bev = box.modifiers.new("b", "BEVEL"); bev.width = 0.025; bev.segments = 3
            bpy.ops.object.modifier_apply(modifier="b")
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
            box.data.materials.append(M(colour))
            box.name = "hat_top"
            _weight_to_bone(box, rig, "head")
            out.append(box)
        if hat == "krakuska":
            bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.01, radius2=0.002, depth=0.28, location=(0.10, -0.05, top_z + 0.07), rotation=(0.3, 0.7, 0))
            f = bpy.context.object
            f.data.materials.append(M("feather"))
            f.name = "feather"
            _weight_to_bone(f, rig, "head")
            out.append(f)
    return [o for o in out if o]


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
        aim_bone(rig, rig.pose.bones["upperarm_" + side], (sx * 0.16, 0.04, -1.0))
        aim_bone(rig, rig.pose.bones["lowerarm_" + side], (sx * 0.10, -0.22, -1.0))
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
def simplify_textured_materials():
    """MPFB wires textures through node groups the glTF exporter cannot follow (eyes come out white).
    Rebuild each textured material as image -> Principled BSDF, keeping the alpha link for strands."""
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        imgs = [n for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
        if not imgs:
            continue
        bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        direct = bsdf and bsdf.inputs["Base Color"].links and bsdf.inputs["Base Color"].links[0].from_node.type == "TEX_IMAGE"
        if direct:
            continue
        diffuse = sorted(imgs, key=lambda n: (("normal" in n.image.name.lower()) or ("bump" in n.image.name.lower()), -n.image.size[0]))[0]
        normal = next((n for n in imgs if "normal" in n.image.name.lower()), None)
        nt = m.node_tree
        for n in list(nt.nodes):
            if n not in (diffuse, normal):
                nt.nodes.remove(n)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        b.inputs["Roughness"].default_value = 0.6
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
        eyes = "high-poly" in low or "low-poly" in low
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


def shrink_images(max_size=2048):
    for img in bpy.data.images:
        if img.size[0] > max_size or img.size[1] > max_size:
            img.scale(min(img.size[0], max_size), min(img.size[1], max_size))


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
    shrink_images()
    simplify_textured_materials()
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


def build(name, spec):
    log("=== building", name)
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
    if spec.get("hat") == "tricorne":
        o = add(h, "clothes", "fedora_cocked", "Clothes")
        log("asset Hat ->", o.name if o else None)
    clothes = build_clothes(h, rig, spec)
    log("garments", [c.name for c in clothes])
    rest_arms_down(rig)
    if spec.get("musket"):
        _musket(rig)
    make_animations(rig)
    export(rig, name)


def _musket(rig):
    """Shouldered musket: vertical beside the right upper arm, welded to the right hand bone."""
    bpy.context.view_layer.update()
    hand = (rig.matrix_world @ rig.pose.bones["hand_r"].matrix).to_translation()
    x, y, z = hand.x - 0.05, hand.y + 0.13, hand.z
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.011, depth=1.15, location=(x, y, z + 0.62))
    barrel = bpy.context.object
    barrel.data.materials.append(M("steel", 0.4))
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y + 0.01, z + 0.20))
    stock = bpy.context.object
    stock.scale = (0.045, 0.075, 0.75)
    bpy.ops.object.transform_apply(scale=True)
    bev = stock.modifiers.new("b", "BEVEL"); bev.width = 0.012; bev.segments = 2
    bpy.ops.object.modifier_apply(modifier="b")
    stock.data.materials.append(M("wood"))
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y - 0.02, z - 0.12))
    butt = bpy.context.object
    butt.scale = (0.05, 0.12, 0.18)
    bpy.ops.object.transform_apply(scale=True)
    butt.data.materials.append(M("wood"))
    for o in (barrel, stock, butt):
        o.name = "musket"
        _weight_to_bone(o, rig, "hand_r")


CHARACTERS = {
    "watchman": {"macro": {"gender": 0.95, "age": 0.42, "muscle": 0.62, "weight": 0.5, "height": 0.6},
                 "targets": {"chin-prominent-incr": 0.3, "nose-hump-incr": 0.3}, "skin": "young_caucasian_male", "hair": "short02", "brows": "eyebrow003",
                 "coat": "white_coat", "coat_len": "mid", "cuffs": "facing_red", "collar": "facing_red", "breeches": "white_coat", "stockings": "stocking",
                 "boots": "black", "boot_height": 0.30, "hat": "tricorne", "musket": True},
    "figure_noble": {"macro": {"gender": 0.9, "age": 0.5, "muscle": 0.5, "weight": 0.55, "height": 0.55},
                     "targets": {"head-square": 0.3, "nose-scale-vert-incr": 0.2, "chin-width-incr": 0.2}, "skin": "middleage_caucasian_male", "hair": "short01", "brows": "eyebrow005",
                     "coat": "crimson", "coat_len": "long", "sash": "zupan_gold", "collar": "zupan_gold", "breeches": "zupan_gold", "stockings": "zupan_gold",
                     "boots": "tan_boot", "boot_height": 0.35, "hat": "konfederatka"},
    "figure_artist": {"macro": {"gender": 0.85, "age": 0.35, "muscle": 0.4, "weight": 0.4, "height": 0.5},
                      "targets": {"head-oval": 0.4, "nose-point-width-decr": 0.2}, "skin": "young_caucasian_male2", "hair": "long01", "brows": "eyebrow002",
                      "coat": "green_coat", "coat_len": "mid", "cuffs": "brown_coat", "collar": "cream", "breeches": "buff", "stockings": "stocking",
                      "boots": "black", "boot_height": 0.12, "hat": "tricorne"},
    "figure_veteran": {"macro": {"gender": 1.0, "age": 0.5, "muscle": 0.75, "weight": 0.55, "height": 0.6},
                       "targets": {"chin-prominent-incr": 0.4, "nose-hump-incr": 0.5, "head-rectangular": 0.3}, "skin": "middleage_caucasian_male", "hair": "short01", "brows": "eyebrow007",
                       "coat": "sukmana", "coat_len": "long", "sash": "facing_red", "cuffs": "facing_red", "breeches": "brown_coat", "stockings": "brown_coat",
                       "boots": "leather", "boot_height": 0.30, "hat": "krakuska"},
    "figure_merchant": {"macro": {"gender": 0.9, "age": 0.55, "muscle": 0.45, "weight": 0.7, "height": 0.5},
                        "targets": {"head-round": 0.4, "chin-jaw-drop-incr": 0.2}, "skin": "middleage_caucasian_male", "hair": "short01", "brows": "eyebrow004",
                        "coat": "brown_coat", "coat_len": "mid", "cuffs": "zupan_gold", "collar": "cream", "breeches": "black", "stockings": "stocking",
                        "boots": "black", "boot_height": 0.12, "hat": "tricorne"},
    "figure_priest": {"macro": {"gender": 0.9, "age": 0.6, "muscle": 0.4, "weight": 0.45, "height": 0.5},
                      "targets": {"head-oval": 0.3, "nose-scale-vert-incr": 0.3}, "skin": "old_caucasian_male", "hair": "short01", "brows": "eyebrow006",
                      "coat": "black", "coat_len": "long", "collar": "cream", "breeches": "black", "stockings": "black",
                      "boots": "black", "boot_height": 0.12, "hat": "biretta"},
    "figure_kazimierz": {"macro": {"gender": 0.9, "age": 0.5, "muscle": 0.45, "weight": 0.5, "height": 0.5},
                         "targets": {"nose-hump-incr": 0.2, "chin-prominent-incr": 0.2}, "skin": "middleage_caucasian_male", "hair": "short01", "brows": "eyebrow008",
                         "coat": "navy", "coat_len": "long", "collar": "black", "breeches": "black", "stockings": "black",
                         "boots": "black", "boot_height": 0.12, "hat": "fur"},
    "figure_townsman": {"macro": {"gender": 0.9, "age": 0.45, "muscle": 0.5, "weight": 0.5, "height": 0.5},
                        "skin": "young_caucasian_male", "hair": "short01", "brows": "eyebrow001",
                        "coat": "brown_coat", "coat_len": "mid", "breeches": "grey", "stockings": "stocking", "boots": "leather", "boot_height": 0.12, "hat": "cap"},
    "figure_townswoman": {"macro": {"gender": 0.05, "age": 0.4, "muscle": 0.45, "weight": 0.5, "height": 0.45, "cupsize": 0.5},
                          "skin": "young_caucasian_female", "hair": "braid01", "brows": "eyebrow009",
                          "coat": "sage", "coat_len": "long", "sash": "cream", "collar": "cream", "breeches": "sage", "stockings": "sage", "boots": "black", "boot_height": 0.10, "hat": "bonnet"},
}

if __name__ == "__main__":
    only = None
    if "--" in sys.argv:
        only = sys.argv[sys.argv.index("--") + 1:]
    for name, spec in CHARACTERS.items():
        if only and name not in only:
            continue
        build(name, spec)
    log("done")
