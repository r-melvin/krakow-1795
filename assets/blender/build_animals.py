"""Animals, harnessed horses and horse-drawn vehicles for Krakow 1795, from third-party CC0 / CC-BY models.

Run:  bash tools/fetch_animals.sh                      (downloads the sources into assets/third_party/)
      blender -b --python assets/blender/build_animals.py [-- --only horse,cat]
Writes assets/models/<name>.glb for: horse, horse_harnessed, dog_hound, dog_spitz, cat, pigeon, crow, hawk,
carriage, horse_cart, hitch_rail. Sources and licences: docs/ANIMALS.md.

Conventions (same as build_assets.py)
- Metres, Blender Z up, glTF export_yup: Blender (x, y, z) -> Godot (x, z, -y).
- Animals and vehicles face Blender -Y (Godot +Z); origin on the ground under the body centre.
  scripts/npc/animal.gd turns the instance by PI so it faces a Node3D's -Z forward.
- Animations are NLA tracks named like the humans' clips: "idle", "walk" (plus "fly", "run" where the source has
  them). The source horse has a rig but no animation: its walk (4-beat, 32 frames at 30 fps, ~1.5 m/s at scale
  1) and idle are keyed procedurally here.
- Every glb carries a "<name>-colonly" box, which Godot turns into a StaticBody3D (animal.gd strips it from
  moving animals and uses its own shape).
- Vehicles contain empties that the runtime reads: "horse_slot_N" (where a horse_harnessed stands, facing the
  same way), "driver_seat", "lamp_L"/"lamp_R", and wheel objects "wheel_*" with their origin on the hub (the
  runtime spins them about local X).
- Blender 5.x: transform_apply bakes location too, and bone-local location keys do not scale with the rig, so
  normalise() multiplies them by the applied scale.
"""
import bpy
import bmesh
import math
import os
import sys
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "assets", "models")
TP = os.path.join(ROOT, "assets", "third_party")
FPS = 30
MAX_TEX = 1024
TRI_LOG = {}


def log(*a):
    print("[animals]", *a, flush=True)


# ------------------------------------------------------------------ scene helpers
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = FPS


def select(objs, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)


def append_blend(path, types=("MESH", "ARMATURE")):
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = list(src.objects)
        dst.images = list(src.images)      # old files keep textures outside the node trees: bring them all
    out = []
    for o in dst.objects:
        if o is None:
            continue
        if o.type in types:
            bpy.context.scene.collection.objects.link(o)
            out.append(o)
    return out


def import_gltf(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def tris(objs):
    n = 0
    for o in objs:
        if o.type == "MESH" and not o.name.endswith("-colonly"):
            dg = bpy.context.evaluated_depsgraph_get()
            me = o.evaluated_get(dg).to_mesh()
            n += sum(len(p.vertices) - 2 for p in me.polygons)
            o.evaluated_get(dg).to_mesh_clear()
    return n


def world_bbox(objs):
    pts = []
    for o in objs:
        if o.type == "MESH" and not o.name.endswith("-colonly"):
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def world_verts(o):
    m = o.matrix_world
    return [m @ v.co for v in o.data.vertices]


def action_fcurves(act):
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for cb in strip.channelbags:
                out += list(cb.fcurves)
    if not out and hasattr(act, "fcurves"):
        out = list(act.fcurves)
    return out


# ------------------------------------------------------------------ materials
def principled(name, color=(0.8, 0.8, 0.8), rough=0.8, image=None, normal=None, alpha=False, emit=None, vcol=None, spec=0.35):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bs.outputs["BSDF"], out.inputs["Surface"])
    bs.inputs["Base Color"].default_value = (*color[:3], 1.0)
    bs.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in bs.inputs:
        bs.inputs["Specular IOR Level"].default_value = spec
    if image is not None:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = image
        nt.links.new(t.outputs["Color"], bs.inputs["Base Color"])
        if alpha:
            nt.links.new(t.outputs["Alpha"], bs.inputs["Alpha"])
            m.blend_method = "CLIP" if hasattr(m, "blend_method") else None
            if hasattr(m, "surface_render_method"):
                m.surface_render_method = "DITHERED"
    elif vcol:
        c = nt.nodes.new("ShaderNodeVertexColor")
        c.layer_name = vcol
        nt.links.new(c.outputs["Color"], bs.inputs["Base Color"])
    if normal is not None:
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = normal
        normal.colorspace_settings.name = "Non-Color"
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(t.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bs.inputs["Normal"])
    if emit is not None:
        bs.inputs["Emission Color"].default_value = (*emit[:3], 1.0)
        bs.inputs["Emission Strength"].default_value = emit[3] if len(emit) > 3 else 2.0
    m.diffuse_color = (*color[:3], 1.0)
    return m


def image_tex(m):
    """First image texture feeding a material (any node), or None."""
    if m and m.node_tree:
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                return n.image
    return None


def shrink_images(limit=MAX_TEX):
    """Cap texture size (the glb embeds them as lossy WebP, which Godot 4 imports and which keeps alpha)."""
    for img in bpy.data.images:
        limit = min(limit, img.get("max_size", limit))
        if img.size[0] > limit or img.size[1] > limit:
            f = limit / max(img.size[0], img.size[1])
            img.scale(max(1, int(img.size[0] * f)), max(1, int(img.size[1] * f)))


# ------------------------------------------------------------------ normalise: scale, face -Y, feet at origin
def normalise(rig, meshes, target, measure="withers", shoulder_bone=None, head_bone=None, yaw=None, drop_z=True, measure_verts=None):
    """measure: 'withers' (height of the back above the front legs), 'height' (overall), 'length' (along Y).
    yaw (radians) overrides the automatic facing (head bone ahead of the body centre -> -Y)."""
    objs = ([rig] if rig else []) + meshes
    for o in objs:     # glTF importers wrap things in empties with the unit/axis conversion; bake it in
        if o.parent and o.parent not in objs:
            mw = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = mw
    bpy.context.view_layer.update()
    mn, mx = world_bbox(meshes)
    centre = (mn + mx) / 2
    if yaw is None:
        yaw = 0.0
        if rig and head_bone and head_bone in rig.data.bones:
            h = rig.matrix_world @ rig.data.bones[head_bone].head_local
            d = Vector((h.x - centre.x, h.y - centre.y))
            if d.length > 1e-6:
                yaw = math.atan2(d.x, -d.y)      # rotate so the head points to -Y
                yaw = round(yaw / (math.pi / 2)) * (math.pi / 2)    # sources are axis-aligned: snap
    R = Matrix.Rotation(yaw, 4, "Z")
    for o in objs:
        if o.parent is None:
            o.matrix_world = R @ Matrix.Translation(-Vector((centre.x, centre.y, 0))) @ o.matrix_world
    bpy.context.view_layer.update()
    mn, mx = world_bbox(meshes)
    if measure == "height":
        cur = mx.z - mn.z
    elif measure == "length":
        cur = mx.y - mn.y
    else:
        yb = (rig.matrix_world @ rig.data.bones[shoulder_bone].head_local).y
        band = (mx.y - mn.y) * 0.05
        top = mn.z
        for o in meshes:
            ws = world_verts(o)
            for i, v in enumerate(ws):
                if abs(v.y - yb) < band and v.z > top and (measure_verts is None or i in measure_verts):
                    top = v.z
        cur = top - mn.z
    s = target / cur
    S = Matrix.Scale(s, 4)
    off = Vector((0, 0, -mn.z * s if drop_z else 0))
    for o in objs:
        if o.parent is None:
            o.matrix_world = Matrix.Translation(off) @ S @ o.matrix_world
    bpy.context.view_layer.update()
    # re-centre on the bbox after scaling (x, y), feet on z=0
    mn, mx = world_bbox(meshes)
    c = (mn + mx) / 2
    for o in objs:
        if o.parent is None:
            o.matrix_world = Matrix.Translation(Vector((-c.x, -c.y, -mn.z))) @ o.matrix_world
    bpy.context.view_layer.update()
    # apply, scaling bone-local translation keys by the total object scale of the rig
    if rig:
        rs = rig.matrix_world.to_scale()[0]
        for act in bpy.data.actions:
            for fc in action_fcurves(act):
                if fc.data_path.startswith("pose.bones") and fc.data_path.endswith(".location"):
                    for k in fc.keyframe_points:
                        k.co.y *= rs
                        k.handle_left.y *= rs
                        k.handle_right.y *= rs
    select(objs, rig or meshes[0])
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    log("  normalised: measured %.3f -> %.2f m (scale %.4f, yaw %.0f deg), bbox %s" % (cur, target, s, math.degrees(yaw), tuple(round(v, 2) for v in (world_bbox(meshes)[1] - world_bbox(meshes)[0]))))
    return s


# ------------------------------------------------------------------ animation helpers
def clear_anim(obj):
    if obj.animation_data:
        obj.animation_data.action = None
        for t in list(obj.animation_data.nla_tracks):
            obj.animation_data.nla_tracks.remove(t)


def push_nla(obj, act, name):
    """One NLA track + strip named `name` playing `act` (glTF NLA_TRACKS mode exports one clip per track)."""
    obj.animation_data_create()
    act.name = name
    act.use_fake_user = True
    track = obj.animation_data.nla_tracks.new()
    track.name = name
    start = int(act.frame_range[0])
    strip = track.strips.new(name, start, act)
    strip.name = name
    if hasattr(strip, "action_slot") and getattr(act, "slots", None):
        for sl in act.slots:
            if sl.target_id_type == ("KEY" if isinstance(obj, bpy.types.Key) else "OBJECT"):
                strip.action_slot = sl
                break
    track.mute = False
    return track


def rename_clips(rig, mapping):
    """mapping: {new clip name: [candidate source action names]}. Keeps only mapped actions."""
    clear_anim(rig)
    keep = []
    found = {new: next((bpy.data.actions.get(c) for c in cands if bpy.data.actions.get(c)), None) for new, cands in mapping.items()}
    for new, cands in mapping.items():
        act = found[new]
        if act is None:
            log("  no action among", cands, "have", [x.name for x in bpy.data.actions])
            continue
        if act in keep:          # the same source reused under a second name
            act = act.copy()
        push_nla(rig, act, new)
        keep.append(act)
    for a in list(bpy.data.actions):
        if a not in keep:
            bpy.data.actions.remove(a)
    # object-level transform keys would fight the runtime's placement: drop them
    for a in keep:
        for fc in action_fcurves(a):
            if not fc.data_path.startswith("pose.bones") and not fc.data_path.startswith("key_blocks"):
                try:
                    fc.id_data  # noqa
                    for layer in a.layers:
                        for strip in layer.strips:
                            for cb in strip.channelbags:
                                if fc in list(cb.fcurves):
                                    cb.fcurves.remove(fc)
                except Exception:
                    pass
    return keep


def key_pose(rig, frame, rots, locs=None):
    """rots: {bone: Matrix(3x3) rotation in armature space applied to that bone (about its head)}."""
    for pb in rig.pose.bones:
        R = rots.get(pb.name)
        M = pb.bone.matrix_local.to_3x3()
        q = (M.inverted() @ (R if R is not None else Matrix.Identity(3)) @ M).to_quaternion()
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = q
        pb.keyframe_insert("rotation_quaternion", frame=frame)
        if locs is not None:
            loc = locs.get(pb.name, Vector())
            pb.location = M.inverted() @ loc
            pb.keyframe_insert("location", frame=frame)


def keyed_action(rig, name, frames, pose_fn, with_loc=False):
    rig.animation_data_create()
    act = bpy.data.actions.new(name)
    rig.animation_data.action = act
    for f in frames:
        r, l = pose_fn(f)
        key_pose(rig, f, r, l if with_loc else None)
    rig.animation_data.action = None
    for fc in action_fcurves(act):
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
    return act


def rx(a):
    return Matrix.Rotation(a, 3, "X")


def rz(a):
    return Matrix.Rotation(a, 3, "Z")


# ------------------------------------------------------------------ procedural primitives (origin = given pivot)
def new_obj(name, bm, mat, pivot=Vector()):
    me = bpy.data.meshes.new(name)
    for v in bm.verts:
        v.co -= pivot
    bm.to_mesh(me)
    bm.free()
    if mat:
        me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    o.location = pivot
    bpy.context.scene.collection.objects.link(o)
    return o


def bm_box(bm, size, centre, rot=None):
    r = bmesh.ops.create_cube(bm, size=1.0)
    M = Matrix.Translation(Vector(centre)) @ (rot.to_4x4() if rot else Matrix.Identity(4)) @ Matrix.Diagonal((*size, 1))
    bmesh.ops.transform(bm, matrix=M, verts=r["verts"])
    return r["verts"]


def bm_cyl(bm, p1, p2, r1, r2=None, seg=8, caps=True):
    p1, p2 = Vector(p1), Vector(p2)
    d = p2 - p1
    L = d.length
    res = bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=seg, radius1=r1, radius2=r1 if r2 is None else r2, depth=L)
    q = Vector((0, 0, 1)).rotation_difference(d.normalized())
    M = Matrix.Translation((p1 + p2) / 2) @ q.to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=M, verts=res["verts"])
    return res["verts"]


def bm_ring(bm, centre, axis, rx_, rz_, tube, seg=20, tseg=6, up=None):
    """Elliptic torus around `axis` (ring radii rx_, rz_ in the plane perpendicular to axis)."""
    axis = Vector(axis).normalized()
    up = Vector(up) if up else (Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((0, 1, 0)))
    u = axis.cross(up).normalized()
    w = u.cross(axis).normalized()
    rings = []
    for i in range(seg):
        a = math.tau * i / seg
        c = Vector(centre) + u * (rx_ * math.cos(a)) + w * (rz_ * math.sin(a))
        radial = (u * (rx_ * math.cos(a)) + w * (rz_ * math.sin(a))).normalized()
        ring = []
        for j in range(tseg):
            b = math.tau * j / tseg
            ring.append(bm.verts.new(c + radial * (tube * math.cos(b)) + axis * (tube * math.sin(b))))
        rings.append(ring)
    for i in range(seg):
        r0, r1 = rings[i], rings[(i + 1) % seg]
        for j in range(tseg):
            bm.faces.new((r0[j], r1[j], r1[(j + 1) % tseg], r0[(j + 1) % tseg]))
    return [v for r in rings for v in r]


def bm_wheel(bm, radius, width, spokes=12, hub_r=0.07, rim=0.035, tyre=0.012):
    """Wheel around the X axis at the origin: iron-tyred felloe, turned hub, flat spokes."""
    vs = bm_ring(bm, (0, 0, 0), (1, 0, 0), radius - rim * 0.5, radius - rim * 0.5, rim * 0.6, seg=28, tseg=6)
    for v in vs:     # flatten the felloe along the axle
        v.co.x *= width / (rim * 1.2)
    vs += bm_cyl(bm, (-width * 0.9, 0, 0), (width * 0.9, 0, 0), hub_r, hub_r * 0.8, seg=10)
    vs += bm_cyl(bm, (-width * 1.6, 0, 0), (width * 1.6, 0, 0), hub_r * 0.55, seg=8)
    for k in range(spokes):
        a = math.tau * k / spokes
        d = Vector((0, math.cos(a), math.sin(a)))
        vs += bm_cyl(bm, d * hub_r * 0.9, d * (radius - rim), 0.016, 0.012, seg=5, caps=False)
    return vs


def weight_all(obj, group):
    vg = obj.vertex_groups.get(group) or obj.vertex_groups.new(name=group)
    vg.add([v.index for v in obj.data.vertices], 1.0, "REPLACE")


def col_box(name, mn, mx, parent=None):
    bm = bmesh.new()
    c = (Vector(mn) + Vector(mx)) / 2
    bm_box(bm, Vector(mx) - Vector(mn), (0, 0, 0))
    o = new_obj(name + "-colonly", bm, None, Vector())
    for v in o.data.vertices:
        v.co += c
    o.display_type = "WIRE"
    if parent:
        o.parent = parent
    return o


def empty(name, loc, parent=None):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    e.empty_display_size = 0.2
    bpy.context.scene.collection.objects.link(e)
    if parent:
        e.parent = parent
    return e


# ------------------------------------------------------------------ export
def export(name, objs, anim=True):
    path = os.path.join(OUT, name + ".glb")
    shrink_images()
    select(objs)
    kw = dict(filepath=path, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
              export_image_format="WEBP", export_image_quality=80, export_animations=anim)
    if anim:
        kw.update(export_animation_mode="NLA_TRACKS", export_skins=True, export_def_bones=True,
                  export_rest_position_armature=True, export_morph=True, export_morph_animation=True)
    bpy.ops.export_scene.gltf(**kw)
    TRI_LOG[name] = tris(objs)
    log("wrote", os.path.relpath(path, ROOT), "tris", TRI_LOG[name], "MB %.2f" % (os.path.getsize(path) / 1e6))


def rig_export(name, rig, meshes, extra=()):
    mn, mx = world_bbox(meshes)
    c = col_box(name, (mn.x, mn.y, 0), (mx.x, mx.y, mx.z))
    for m in meshes:
        if m.parent is None:
            mw = m.matrix_world.copy()
            m.parent = rig
            m.matrix_world = mw
    export(name, [rig] + meshes + [c] + list(extra))


# ------------------------------------------------------------------ horse (Lyndon Daniels / ChadM, CC0)
HORSE = os.path.join(TP, "oga_rigged_horse", "riggedHorse.blend")
# rig: Bone (hip->withers, root), Bone.001 neck, Bone.002 head, Bone.001_L/R ears, Bone.003/.004 tail,
# front legs Bone_L/R (+.001 forearm, .002 cannon), hind legs Bone_L/R.003 (+.004 gaskin, .005 cannon)
FRONT = (("Bone_L", "Bone_L.001", "Bone_L.002"), ("Bone_R", "Bone_R.001", "Bone_R.002"))
HIND = (("Bone_L.003", "Bone_L.004", "Bone_L.005"), ("Bone_R.003", "Bone_R.004", "Bone_R.005"))


def load_horse():
    reset()
    objs = append_blend(HORSE)
    rig = next(o for o in objs if o.type == "ARMATURE")
    body = bpy.data.objects["Plane"]
    mane, tail = bpy.data.objects["BezierCurve"], bpy.data.objects["BezierCurve.005"]
    eyes = [bpy.data.objects["Sphere"], bpy.data.objects["Sphere.002"]]
    imgs = bpy.data.images
    diff, nrm = imgs["HorseMain4k00.png"], imgs["HorseMain4k00Norm00.p"]
    hair = imgs["Hair12Main2k.png"]
    hair["max_size"] = 512
    body.data.materials[0] = principled("horse_coat", (0.8, 0.8, 0.8), 0.72, diff, nrm, spec=0.3)
    hm = principled("horse_hair", (0.8, 0.8, 0.8), 0.6, hair, alpha=True, spec=0.4)
    for o in (mane, tail):
        o.data.materials[0] = hm
    em = principled("horse_eye", (0.05, 0.03, 0.02), 0.08, spec=0.9)
    for e in eyes:
        e.data.materials[0] = em
    for img in list(imgs):
        if img.users == 0 or not img.has_data and not img.packed_file:
            imgs.remove(img)
    # skin the loose parts: eyes to the head, mane to the neck, tail along its two bones
    for e in eyes:
        weight_all(e, "Bone.002")
    weight_all(mane, "Bone.001")
    t0 = rig.matrix_world @ rig.data.bones["Bone.004"].head_local
    tv = tail.vertex_groups.new(name="Bone.003")
    tv2 = tail.vertex_groups.new(name="Bone.004")
    for v, co in zip(tail.data.vertices, world_verts(tail)):
        w = min(1.0, max(0.0, (t0.z - co.z) / 2.0 + 0.5))
        tv.add([v.index], 1.0 - w, "REPLACE")
        tv2.add([v.index], w, "REPLACE")
    for o in eyes + [mane, tail]:
        o.parent = None
    bpy.context.view_layer.update()
    for o in eyes + [mane, tail]:     # world-space verts, then parent to the rig with an armature modifier
        mw = o.matrix_world.copy()
        o.data.transform(mw)
        o.matrix_world = Matrix.Identity(4)
    body_mw = body.matrix_world.copy()
    body.parent = None
    body.data.transform(body_mw)
    body.matrix_world = Matrix.Identity(4)
    n_coat = len(body.data.vertices)       # the joined mesh keeps the coat's vertices first
    select([body] + eyes + [mane, tail], body)
    bpy.ops.object.join()
    for m in list(body.modifiers):
        body.modifiers.remove(m)
    mod = body.modifiers.new("Armature", "ARMATURE")
    mod.object = rig
    body.name = "horse_body"
    for o in list(bpy.data.objects):
        if o not in (rig, body):
            bpy.data.objects.remove(o)
    rig.name = "horse_rig"
    normalise(rig, [body], 1.60, "withers", shoulder_bone="Bone_L", yaw=0.0, measure_verts=set(range(n_coat)))
    body.parent = rig
    return rig, body


def horse_anims(rig):
    clear_anim(rig)

    def leg_angles(p, front):
        """p: gait phase 0..1 for this leg. Stance 0..0.62 sweeps the leg back, swing lifts and brings it forward.
        Returns (upper, middle, lower) rotations about X (positive swings the part backwards)."""
        A = 0.30 if front else 0.26
        duty = 0.62
        if p < duty:
            t = p / duty
            up = -A + 2 * A * t
            lift = 0.0
        else:
            t = (p - duty) / (1 - duty)
            up = A - 2 * A * (0.5 - 0.5 * math.cos(math.pi * t))
            lift = math.sin(math.pi * t)
        if front:   # knee (carpus) folds back during swing, fetlock follows
            return up, -0.10 * lift, 1.25 * lift
        return up, -0.55 * lift, 0.95 * lift        # stifle forward, hock flexes back

    frames = list(range(1, 34))       # 32-frame loop (frame 33 == frame 1)
    phase = {"LH": 0.0, "LF": 0.25, "RH": 0.5, "RF": 0.75}

    def walk(f):
        t = (f - 1) / 32
        r = {}
        for (chain, key) in ((FRONT[0], "LF"), (FRONT[1], "RF"), (HIND[0], "LH"), (HIND[1], "RH")):
            a, b, c = leg_angles((t - phase[key]) % 1.0, key.endswith("F"))
            # rotations compose down the chain: each bone's armature-space delta is relative to its parent
            r[chain[0]] = rx(a)
            r[chain[1]] = rx(b)
            r[chain[2]] = rx(c)
        r["Bone.001"] = rx(0.05 * math.sin(t * math.tau * 2))           # head nods twice a stride
        r["Bone.002"] = rx(-0.04 * math.sin(t * math.tau * 2))
        r["Bone.003"] = rz(0.08 * math.sin(t * math.tau))
        r["Bone.004"] = rz(0.12 * math.sin(t * math.tau - 0.8))
        return r, None

    walk_act = keyed_action(rig, "walk", frames, walk)

    def idle(f):
        t = (f - 1) / 120
        s = math.sin(t * math.tau)
        r = {"Bone.001": rx(0.035 * s), "Bone.002": rx(0.03 * math.sin(t * math.tau * 2)),
             "Bone.003": rz(0.18 * max(0.0, math.sin(t * math.tau * 3)) ** 3),
             "Bone.004": rz(0.30 * max(0.0, math.sin(t * math.tau * 3 - 0.5)) ** 3),
             "Bone.001_L": rx(0.25 * max(0.0, math.sin(t * math.tau * 2 + 1.0)) ** 8),
             "Bone.001_R": rx(0.25 * max(0.0, math.sin(t * math.tau * 1 + 2.5)) ** 8),
             "Bone_R.004": rx(-0.06), "Bone_R.005": rx(0.12)}      # rests a hind leg
        return r, None

    idle_act = keyed_action(rig, "idle", list(range(1, 122, 4)), idle)
    for a in (idle_act, walk_act):
        for fc in action_fcurves(a):
            for k in fc.keyframe_points:
                k.interpolation = "BEZIER" if a is idle_act else "LINEAR"
    push_nla(rig, idle_act, "idle")
    push_nla(rig, walk_act, "walk")


def horse():
    rig, body = load_horse()
    horse_anims(rig)
    rig_export("horse", rig, [body])


def _bone_pt(rig, name, t=0.0):
    b = rig.data.bones[name]
    return rig.matrix_world @ (b.head_local.lerp(b.tail_local, t))


def _section(verts, centre, axis, slab, reach=0.5):
    """Body section through `centre` perpendicular to `axis`: (half width, half height, section centre, up)."""
    axis = axis.normalized()
    u = axis.cross(Vector((0, 0, 1))).normalized()
    w = u.cross(axis).normalized()
    if w.z < 0:
        w = -w
    xs, zs = [], []
    for v in verts:
        d = v - centre
        if abs(d.dot(axis)) < slab and (d - axis * d.dot(axis)).length < reach:
            xs.append(d.dot(u))
            zs.append(d.dot(w))
    if not xs:
        return 0.2, 0.2, centre, w
    c = centre + u * ((max(xs) + min(xs)) / 2) + w * ((max(zs) + min(zs)) / 2)
    return (max(xs) - min(xs)) / 2, (max(zs) - min(zs)) / 2, c, w


def horse_harnessed():
    """Horse in a pair/cart harness: breast collar, back pad with terrets and belly band, traces running back
    to the vehicle (ending TRACE_BACK metres behind the horse's centre), bridle with blinkers, reins to the driver."""
    rig, body = load_horse()
    horse_anims(rig)
    verts = world_verts(body)
    leather = principled("harness_leather", (0.07, 0.045, 0.03), 0.45, spec=0.5)
    brass = principled("harness_brass", (0.72, 0.55, 0.22), 0.3, spec=0.8)
    parts = []

    def part(name, build, group, mat=leather):
        bm = bmesh.new()
        build(bm)
        o = new_obj(name, bm, mat)
        weight_all(o, group)
        parts.append(o)
        return o

    # collar round the base of the neck
    n0, n1 = _bone_pt(rig, "Bone.001", 0.0), _bone_pt(rig, "Bone.001", 1.0)
    axis = (n1 - n0).normalized()
    cpt = n0.lerp(n1, 0.22)
    hx, hz, cc, cup = _section(verts, cpt, axis, 0.04, 0.45)
    part("collar", lambda bm: bm_ring(bm, cc, axis, hx + 0.03, hz + 0.03, 0.045, seg=22, tseg=8, up=cup), "Bone")
    part("hames", lambda bm: bm_ring(bm, cc - axis * 0.02, axis, hx + 0.07, hz + 0.05, 0.014, seg=22, tseg=5, up=cup), "Bone", brass)
    # back pad and belly band behind the withers
    wy = _bone_pt(rig, "Bone_L", 0.0).y
    s0, s1 = _bone_pt(rig, "Bone", 0.0), _bone_pt(rig, "Bone", 1.0)      # spine bone: hip -> withers
    tb = (wy + 0.32 - s0.y) / (s1.y - s0.y)
    bp = s0.lerp(s1, tb)
    bp.x = 0.0
    bx, bz, bcen, _ = _section(verts, bp, Vector((0, 1, 0)), 0.04, 0.75)
    part("girth", lambda bm: bm_ring(bm, bcen, (0, 1, 0), bx + 0.012, bz + 0.012, 0.03, seg=26, tseg=4), "Bone")
    top = bcen + Vector((0, 0, bz + 0.03))
    part("pad", lambda bm: bm_box(bm, (bx * 1.3, 0.22, 0.05), top), "Bone")
    for sx in (-1, 1):
        part("terret", lambda bm, sx=sx: bm_ring(bm, top + Vector((sx * 0.1, 0, 0.07)), (0, 1, 0), 0.04, 0.04, 0.009, seg=10, tseg=4), "Bone", brass)
    # traces: from the collar sides back along the flanks
    TRACE_BACK = 1.95
    ty = TRACE_BACK
    for sx in (-1, 1):
        a = cc + Vector((sx * (hx + 0.05), 0, -hz * 0.35))
        b = Vector((sx * (bx + 0.06), bp.y, a.z - 0.05))
        c = Vector((sx * (bx + 0.02), ty, 0.92))
        part("trace", lambda bm, a=a, b=b: bm_cyl(bm, a, b, 0.018, seg=6), "Bone")
        part("trace", lambda bm, b=b, c=c: bm_cyl(bm, b, c, 0.018, seg=6), "Bone")
    # bridle: crown piece behind the ears, noseband, cheek straps, blinkers, bit
    h0, h1 = _bone_pt(rig, "Bone.002", 0.0), _bone_pt(rig, "Bone.002", 1.0)
    hax = (h1 - h0).normalized()
    crown = h0.lerp(h1, 0.12)
    nose = h0.lerp(h1, 0.72)
    cx, cz, crown_c, upv = _section(verts, crown, hax, 0.025, 0.22)
    nx, nz, nose_c, _ = _section(verts, nose, hax, 0.025, 0.16)
    part("crownpiece", lambda bm: bm_ring(bm, crown_c, hax, cx + 0.01, cz + 0.01, 0.014, seg=18, tseg=4, up=upv), "Bone.002")
    part("noseband", lambda bm: bm_ring(bm, nose_c, hax, nx + 0.012, nz + 0.012, 0.014, seg=18, tseg=4, up=upv), "Bone.002")
    side = Vector((1, 0, 0))
    for sx in (-1, 1):
        a = crown_c + side * sx * (cx + 0.01)
        b = nose_c + side * sx * (nx + 0.012)
        part("cheek", lambda bm, a=a, b=b: bm_cyl(bm, a, b, 0.012, seg=5), "Bone.002")
        eye = crown_c.lerp(nose_c, 0.35) + side * sx * (cx * 0.95 + 0.03) + upv * (cz * 0.35)
        part("blinker", lambda bm, eye=eye: bm_box(bm, (0.012, 0.11, 0.08), eye), "Bone.002")
    bit_c = nose_c + hax * 0.08 - upv * (nz * 0.55)
    part("bit", lambda bm: bm_cyl(bm, bit_c - side * (nx + 0.05), bit_c + side * (nx + 0.05), 0.01, seg=6), "Bone.002", brass)
    # reins: bit -> terret (head end weighted to the head, so they follow its nod) -> driver behind
    drv = Vector((0, ty + 0.9, 1.55))
    mx_, mz, mid_c, mid_up = _section(verts, n0.lerp(n1, 0.55), axis, 0.03, 0.4)
    for sx in (-1, 1):
        a = bit_c + side * sx * (nx + 0.05)
        b = top + Vector((sx * 0.1, 0, 0.07))
        m = mid_c + mid_up * (mz + 0.015) + side * sx * 0.07      # over the crest of the neck, not through it
        for p0, p1, gA, gB in ((a, m, "Bone.002", "Bone.001"), (m, b, "Bone.001", "Bone")):
            bm = bmesh.new()
            bm_cyl(bm, p0, p1, 0.008, seg=5)
            o = new_obj("rein", bm, leather)
            g1, g2 = o.vertex_groups.new(name=gA), o.vertex_groups.new(name=gB)
            for v in o.data.vertices:
                w = min(1.0, max(0.0, (v.co - p0).length / max((p1 - p0).length, 1e-6)))
                g1.add([v.index], 1.0 - w, "REPLACE")
                g2.add([v.index], w, "REPLACE")
            parts.append(o)
        part("rein", lambda bm, b=b, sx=sx: bm_cyl(bm, b, drv + Vector((sx * 0.12, 0, 0)), 0.008, seg=5), "Bone")
    select(parts)
    bpy.ops.object.join()
    harness = bpy.context.object
    harness.name = "harness"
    m = harness.modifiers.new("Armature", "ARMATURE")
    m.object = rig
    harness.parent = rig
    trace_end = empty("trace_end", (0, ty, 0.92))
    rig_export("horse_harnessed", rig, [body, harness], extra=[trace_end])
    return TRACE_BACK


# ------------------------------------------------------------------ Quaternius dogs (CC0)
Q = os.path.join(TP, "quaternius_animals")
Q_WOLF = os.path.join(Q, "f1d12388-e39b-4157-b32a-646a1d089fc4.glb")
Q_HUSKY = os.path.join(Q, "611d25c7-430f-4bb5-ab2c-d8f5f3cb9712.glb")


def quaternius_dog(name, src, height, recolour):
    reset()
    objs = import_gltf(src)
    rig = next(o for o in objs if o.type == "ARMATURE")
    meshes = [o for o in objs if o.type == "MESH" and o.parent == rig]
    for o in objs:
        if o.type == "MESH" and o not in meshes or o.type == "EMPTY" and o.name != "RootNode" and o.parent == rig:
            bpy.data.objects.remove(o)
    rename_clips(rig, {"idle": ["AnimalArmature|Idle", "Idle"], "walk": ["AnimalArmature|Walk", "Walk"],
                       "run": ["AnimalArmature|Gallop", "Gallop"]})
    normalise(rig, meshes, height, "withers", shoulder_bone="FrontUpperLeg.L", head_bone="Head")
    for o in list(bpy.data.objects):
        if o.type == "EMPTY":
            bpy.data.objects.remove(o)
    for m in meshes:
        for i, mat in enumerate(m.data.materials):
            bs = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            c = tuple(bs.inputs["Base Color"].default_value[:3]) if bs else (0.5, 0.5, 0.5)
            new = recolour(mat.name, c)
            m.data.materials[i] = principled("%s_%s" % (name, mat.name), new, 0.85 if max(new) > 0.05 else 0.35, spec=0.3)
    rig.name = name + "_rig"
    rig_export(name, rig, meshes)


def hound_colours(mname, c):
    """Polish hound (ogar polski): black saddle, tan legs and head, darker muzzle."""
    lum = sum(c) / 3
    if lum < 0.03:
        return c                                    # eyes, nose
    if lum < 0.2:
        return (0.035, 0.028, 0.024)                # saddle: black
    return (0.42, 0.22, 0.09)                       # tan points


def spitz_colours(mname, c):
    """Wolfspitz / Pomeranian ancestor: cream coat, pale buff belly, black points."""
    lum = sum(c) / 3
    if lum < 0.03:
        return c
    if lum < 0.1:
        return (0.62, 0.48, 0.30)                   # husky mask dark -> buff
    if lum < 0.5:
        return (0.80, 0.70, 0.52)                   # grey -> cream
    return (0.90, 0.86, 0.76)


# ------------------------------------------------------------------ cat (Drummyfish, CC0)
def cat():
    reset()
    objs = append_blend(os.path.join(TP, "oga_simple_cat", "cat_2-80.blend"))
    # Cube.001 is the walking cat with two shape keys (legs forward / back); Cube is a mirrored sitting variant
    for o in objs:
        if o.name != "Cube.001":
            bpy.data.objects.remove(o)
    body = bpy.data.objects["Cube.001"]
    img = bpy.data.images.load(os.path.join(TP, "oga_simple_cat", "cat.png"))
    img.pack()
    body.data.materials[0] = principled("cat_fur", (0.8, 0.8, 0.8), 0.9, img, spec=0.2)
    for m in list(body.modifiers):
        body.modifiers.remove(m)      # "Auto Smooth" node group: shading only, and it would block shape-key export
    for p in body.data.polygons:
        p.use_smooth = False
    normalise(None, [body], 0.25 * 1.28, "height", yaw=None)
    # face -Y: the head end is the taller end
    vs = world_verts(body)
    mn, mx = world_bbox([body])
    front = [v for v in vs if v.z > mn.z + (mx.z - mn.z) * 0.8]
    fy = sum(v.y for v in front) / max(1, len(front))
    if fy > 0:
        body.data.transform(Matrix.Rotation(math.pi, 4, "Z"))
    key = body.data.shape_keys
    act = bpy.data.actions.get("KeyAction")
    if key and act:
        key.animation_data_create()
        key.animation_data.action = None
        push_nla(key, act, "walk")
        idle = bpy.data.actions.new("idle")
        key.animation_data.action = idle
        for kb in key.key_blocks[1:]:
            kb.value = 0.0
            kb.keyframe_insert("value", frame=1)
            kb.keyframe_insert("value", frame=30)
        key.animation_data.action = None
        push_nla(key, idle, "idle")
    mn, mx = world_bbox([body])
    c = col_box("cat", (mn.x, mn.y, 0), (mx.x, mx.y, mx.z))
    body.name = "cat"
    export("cat", [body, c])


# ------------------------------------------------------------------ birds
def pigeon():
    """mujtaba-io's rigged pigeon (CC0). It is modelled in flight (wings spread, its "idle" is a glide), so the
    ground clips are keyed here: wings rolled and swept back along the flanks, head-bobbing walk. Untextured:
    painted with the feral rock-dove pattern per face from the dominant bone of each face."""
    reset()
    objs = append_blend(os.path.join(TP, "oga_pigeon", "genuinely-my-pigeon-extended-furthur.blend"))
    rig = bpy.data.objects["pigeon-armature"]
    body = bpy.data.objects["pigeon-model"]
    for o in objs:
        if o not in (rig, body):
            bpy.data.objects.remove(o)
    rename_clips(rig, {"fly": ["flap-wings-animation"]})
    normalise(rig, [body], 0.30, "length", head_bone="face-bone")
    fly = bpy.data.actions.get("fly")
    clear_anim(rig)
    ry = lambda a: Matrix.Rotation(a, 3, "Y")

    def folded(extra=None):
        r = {"left-wing-1": rx(math.radians(-28)) @ rz(math.radians(80)) @ ry(math.radians(-12)) @ rx(math.radians(-90)),
             "right-wing-1": rx(math.radians(-28)) @ rz(math.radians(-80)) @ ry(math.radians(12)) @ rx(math.radians(-90)),
             "left-wing-2": rx(math.radians(-10)) @ rz(math.radians(8)), "right-wing-2": rx(math.radians(-10)) @ rz(math.radians(-8)),
             "tail-bone-1": rx(math.radians(-8))}
        r.update(extra or {})
        return r

    def idle(f):
        t = (f - 1) / 60
        look = 0.35 * math.sin(t * math.tau) * (1 if (t % 1) < 0.5 else 0.4)
        return folded({"neck-bone": rz(look), "face-bone": rx(0.15 * max(0.0, math.sin(t * math.tau * 2)) ** 4)}), None

    def walk(f):
        t = (f - 1) / 12
        bob = math.sin(t * math.tau)
        return folded({"thorax-bone": rx(0.05 * bob), "neck-bone": rx(0.35 * max(0.0, bob)),
                       "left-upper-leg-bone": rx(0.5 * bob), "right-upper-leg-bone": rx(-0.5 * bob)}), None

    idle_act = keyed_action(rig, "idle", list(range(1, 62, 3)), idle)
    walk_act = keyed_action(rig, "walk", list(range(1, 14)), walk)
    push_nla(rig, idle_act, "idle")
    push_nla(rig, walk_act, "walk")
    if fly:
        push_nla(rig, fly, "fly")
    grey = principled("pigeon_grey", (0.46, 0.48, 0.54), 0.8, spec=0.3)
    dark = principled("pigeon_neck", (0.16, 0.22, 0.21), 0.4, spec=0.7)
    prim = principled("pigeon_primaries", (0.18, 0.18, 0.21), 0.8, spec=0.3)
    leg = principled("pigeon_leg", (0.62, 0.16, 0.16), 0.6, spec=0.3)
    me = body.data
    me.materials.clear()
    for m in (grey, dark, prim, leg):
        me.materials.append(m)
    gname = {g.index: g.name for g in body.vertex_groups}
    for p in me.polygons:
        acc = {}
        for vi in p.vertices:
            for g in me.vertices[vi].groups:
                acc[gname[g.group]] = acc.get(gname[g.group], 0.0) + g.weight
        top = max(acc, key=acc.get) if acc else ""
        idx = 0
        if top in ("neck-bone", "face-bone"):
            idx = 1
        elif top in ("left-wing-2", "right-wing-2", "tail-bone-2"):
            idx = 2
        elif "leg" in top and max(me.vertices[vi].co.z for vi in p.vertices) < 0.035:
            idx = 3
        p.material_index = idx
    rig_export("pigeon", rig, [body])


def crow():
    """Teh_Bucket's raven (CC0), scaled to a hooded crow (~0.45 m)."""
    reset()
    objs = append_blend(os.path.join(TP, "oga_raven", "raven_0.blend"))
    rig = bpy.data.objects["raven_armature"]
    body = bpy.data.objects["raven_mesh"]
    img = bpy.data.images.get("raven")
    body.data.materials[0] = principled("crow_feathers", (0.8, 0.8, 0.8), 0.55, img, spec=0.5)
    rename_clips(rig, {"idle": ["stand"], "fly": ["fly"]})
    normalise(rig, [body], 0.45, "length", head_bone="beak")
    rig_export("crow", rig, [body])


def hawk():
    """Sherkiz's hawk (CC-BY 3.0), wings spread in its rest pose; clip "fly" (and "idle" = the same glide)."""
    reset()
    objs = import_gltf(os.path.join(TP, "polypizza_hawk", "2a7aca61-a8f6-45f6-950e-003d4bfcab45.glb"))
    rig = next(o for o in objs if o.type == "ARMATURE")
    body = next(o for o in objs if o.type == "MESH" and o.parent == rig)
    for o in objs:
        if o.type == "MESH" and o is not body:
            bpy.data.objects.remove(o)
    img = image_tex(body.data.materials[0])
    body.data.materials[0] = principled("hawk_feathers", (0.8, 0.8, 0.8), 0.7, img, spec=0.3)
    rename_clips(rig, {"fly": ["metarig|Fly", "Fly"], "idle": ["metarig|Fly", "Fly"]})
    normalise(rig, [body], 0.55, "length", head_bone="head")
    for o in list(bpy.data.objects):
        if o.type == "EMPTY":
            bpy.data.objects.remove(o)
    rig_export("hawk", rig, [body])


# ------------------------------------------------------------------ vehicles (procedural)
def M(name, color, rough=0.6, **kw):
    return principled("veh_" + name, color, rough, **kw)


def carriage(trace_back=1.95):
    """Dorozka / fiacre: a two-horse hire cab. Sprung open body with a folding leather hood over the rear seat,
    raised driver's box, small front and tall rear wheels on elliptic springs, a centre pole and splinter bar.
    Front at -Y. The horses stand in slots ahead of the splinter bar."""
    reset()
    body_c = M("lacquer", (0.03, 0.035, 0.04), 0.35)
    trim = M("trim", (0.45, 0.07, 0.06), 0.5)
    wheel_c = M("wheel", (0.30, 0.05, 0.04), 0.55)
    iron = M("iron", (0.08, 0.08, 0.09), 0.45)
    hood_c = M("hood", (0.05, 0.045, 0.04), 0.55)
    seat_c = M("cushion", (0.18, 0.05, 0.06), 0.9)
    wood = M("wood", (0.22, 0.13, 0.07), 0.8)
    lamp_glass = M("lamp_glass", (0.9, 0.75, 0.4), 0.2, emit=(1.0, 0.72, 0.35, 3.0))
    objs = []
    RW, FW, TRACK = 0.66, 0.46, 0.78          # rear / front wheel radius, half track
    YR, YF = 0.95, -1.05                      # axle positions
    # chassis: perch pole and axles
    bm = bmesh.new()
    bm_cyl(bm, (0, YF, 0.50), (0, YR, 0.58), 0.035, seg=8)
    bm_cyl(bm, (-TRACK, YR, RW), (TRACK, YR, RW), 0.035, seg=8)
    bm_cyl(bm, (-TRACK, YF, FW), (TRACK, YF, FW), 0.035, seg=8)
    for y, z0, half in ((YR, RW, 0.62), (YF, FW, 0.5)):      # elliptic leaf springs (a flattened ring each side)
        for sx in (-1, 1):
            vs = bm_ring(bm, (sx * 0.52, y, z0 + 0.10), (1, 0, 0), half * 0.5, 0.07, 0.018, seg=16, tseg=4)
    bm_cyl(bm, (0, YF, 0.52), (0, -3.55, 0.78), 0.04, 0.03, seg=8)          # pole
    bm_cyl(bm, (-0.85, -1.5, 0.80), (0.85, -1.5, 0.80), 0.035, seg=8)       # splinter bar
    bm_cyl(bm, (0, -1.5, 0.80), (0, YF, FW), 0.03, seg=6)
    objs.append(new_obj("chassis", bm, iron))
    # body: floor, sides with a swept lower edge, seat and back
    bm = bmesh.new()
    bm_box(bm, (1.26, 1.5, 0.05), (0, 0.35, 0.95))                           # floor
    for sx in (-1, 1):
        bm_box(bm, (0.04, 1.3, 0.42), (sx * 0.63, 0.45, 1.18))              # side panels
        bm_box(bm, (0.04, 0.5, 0.22), (sx * 0.63, -0.45, 1.06))             # footwell sides, lower
    bm_box(bm, (1.3, 0.05, 0.62), (0, 1.12, 1.28))                          # back panel
    bm_box(bm, (1.26, 0.04, 0.3), (0, -0.7, 1.08))                          # dash front of the footwell
    objs.append(new_obj("body", bm, body_c))
    bm = bmesh.new()
    for sx in (-1, 1):
        bm_box(bm, (0.05, 1.32, 0.04), (sx * 0.645, 0.45, 1.40))            # red coachline on the rail
    bm_box(bm, (1.32, 0.06, 0.04), (0, 1.13, 1.60))
    objs.append(new_obj("trim", bm, trim))
    bm = bmesh.new()
    bm_box(bm, (1.18, 0.55, 0.14), (0, 0.78, 1.12))                         # rear seat cushion
    bm_box(bm, (1.18, 0.12, 0.45), (0, 1.05, 1.40))                         # squab
    objs.append(new_obj("seat", bm, seat_c))
    # folding hood: a leather shell over hoops, lowered halfway (quarter circle behind the seat)
    bm = bmesh.new()
    hc, hr = Vector((0, 0.95, 1.30)), 0.68
    seg, cols = 14, []
    for i in range(seg + 1):
        a = math.radians(-8 + 110 * i / seg)        # from just forward of vertical to down behind
        d = Vector((0, math.sin(a), math.cos(a)))
        cols.append([bm.verts.new(hc + Vector((x, 0, 0)) + d * hr) for x in (-0.66, 0.66)])
    for i in range(seg):
        bm.faces.new((cols[i][0], cols[i][1], cols[i + 1][1], cols[i + 1][0]))
    for x in (-0.66, 0.66):                         # side quarters (fan-shaped)
        ctr = bm.verts.new(hc + Vector((x, 0, 0)))
        ring = [c[0 if x < 0 else 1] for c in cols]
        for i in range(seg):
            bm.faces.new((ctr, ring[i], ring[i + 1]) if x > 0 else (ctr, ring[i + 1], ring[i]))
    bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.02)
    for k in range(4):                              # hood hoops
        a = math.radians(-8 + 110 * k / 3)
        d = Vector((0, math.sin(a), math.cos(a)))
        bm_cyl(bm, hc + Vector((-0.69, 0, 0)) + d * hr, hc + Vector((0.69, 0, 0)) + d * hr, 0.014, seg=6)
    objs.append(new_obj("hood", bm, hood_c))
    # driver's box: raised seat on an iron frame, footboard sloping forward
    bm = bmesh.new()
    bm_box(bm, (0.9, 0.42, 0.3), (0, -0.55, 1.38))                          # box
    bm_box(bm, (0.9, 0.5, 0.04), (0, -1.05, 1.02), Matrix.Rotation(math.radians(-18), 3, "X"))   # footboard
    objs.append(new_obj("driver_box", bm, body_c))
    bm = bmesh.new()
    bm_box(bm, (0.94, 0.46, 0.1), (0, -0.55, 1.58))
    objs.append(new_obj("driver_cushion", bm, seat_c))
    bm = bmesh.new()
    for sx in (-1, 1):
        bm_cyl(bm, (sx * 0.4, -0.35, 1.0), (sx * 0.4, -0.35, 1.34), 0.02, seg=6)
        bm_cyl(bm, (sx * 0.4, -0.75, 1.0), (sx * 0.4, -0.75, 1.34), 0.02, seg=6)
        bm_cyl(bm, (sx * 0.5, -0.78, 1.45), (sx * 0.5, -0.78, 1.72), 0.012, seg=6)     # lamp brackets
        bm_box(bm, (0.1, 0.1, 0.03), (sx * 0.5, -0.78, 1.70))
        bm_box(bm, (0.1, 0.1, 0.03), (sx * 0.5, -0.78, 1.88))
        bm_cyl(bm, (sx * 0.5, -0.78, 1.89), (sx * 0.5, -0.78, 1.96), 0.03, 0.005, seg=6)
    bm_cyl(bm, (0.62, -0.62, 1.55), (0.95, -0.2, 2.9), 0.008, 0.004, seg=5)            # whip in its socket
    objs.append(new_obj("fittings", bm, iron))
    bm = bmesh.new()
    for sx in (-1, 1):
        bm_box(bm, (0.085, 0.085, 0.15), (sx * 0.5, -0.78, 1.79))
    objs.append(new_obj("lamps", bm, lamp_glass))
    bm = bmesh.new()
    bm_box(bm, (0.4, 0.08, 0.3), (0.0, 1.2, 0.95))                          # luggage boot at the back
    objs.append(new_obj("boot", bm, wood))
    root = objs[0]
    for o in objs[1:]:
        o.parent = root
    # wheels, origin on the hub
    for tag, y, r in (("wheel_rl", YR, RW), ("wheel_rr", YR, RW), ("wheel_fl", YF, FW), ("wheel_fr", YF, FW)):
        bm = bmesh.new()
        bm_wheel(bm, r, 0.035, spokes=14 if r > 0.5 else 12)
        x = -TRACK if tag.endswith("l") else TRACK
        w = new_obj(tag, bm, wheel_c, Vector())
        w.location = (x, y, r)
        w.parent = root
        objs.append(w)
    # horse slots: horse_harnessed's traces end trace_back behind its centre, at the splinter bar (y=-1.5)
    extras = [empty("horse_slot_0", (-0.62, -1.5 - trace_back, 0), root), empty("horse_slot_1", (0.62, -1.5 - trace_back, 0), root),
              empty("driver_seat", (0, -0.55, 1.63), root), empty("lamp_L", (-0.5, -0.78, 1.8), root), empty("lamp_R", (0.5, -0.78, 1.8), root)]
    col = col_box("carriage", (-0.95, -1.6, 0), (0.95, 1.3, 2.1), root)
    root.name = "carriage"
    export("carriage", objs + extras + [col], anim=False)


def horse_cart(trace_back=1.95):
    """Peasant ladder-sided cart (woz drabiniasty), two tall wheels, shafts for one horse, a load of sacks and hay.
    Front at -Y."""
    reset()
    wood = M("cart_wood", (0.30, 0.20, 0.11), 0.85)
    wood_d = M("cart_wood_dark", (0.17, 0.11, 0.06), 0.85)
    iron = M("cart_iron", (0.08, 0.08, 0.09), 0.5)
    sack = M("sack", (0.55, 0.47, 0.34), 0.95)
    hay = M("hay", (0.62, 0.52, 0.28), 0.95)
    objs = []
    R, TRACK, YA = 0.62, 0.72, 0.3
    bm = bmesh.new()
    bm_box(bm, (0.95, 2.3, 0.06), (0, 0.25, 0.78))                           # bed
    for sx in (-1, 1):
        bm_box(bm, (0.08, 2.5, 0.08), (sx * 0.5, 0.25, 0.72))                # side beams, continue as shafts
        bm_cyl(bm, (sx * 0.5, -1.0, 0.72), (sx * 0.52, -3.55, 0.95), 0.035, 0.028, seg=6)  # shafts
        bm_cyl(bm, (sx * 0.62, -0.95, 0.78), (sx * 0.62, 1.4, 1.35), 0.03, seg=6)   # ladder side top rail (sloped)
        bm_cyl(bm, (sx * 0.56, -0.95, 0.80), (sx * 0.6, 1.4, 0.95), 0.03, seg=6)    # lower rail
        for k in range(9):
            y = -0.9 + k * 0.28
            zt = 0.78 + (y + 0.95) / 2.35 * 0.57
            bm_cyl(bm, (sx * 0.57, y, 0.78), (sx * 0.62, y, zt + 0.02), 0.014, seg=5)  # rungs
    bm_box(bm, (1.0, 0.05, 0.3), (0, -0.9, 0.93))                           # front board
    bm_box(bm, (1.0, 0.05, 0.25), (0, 1.38, 0.92))                          # tailboard
    bm_box(bm, (0.8, 0.28, 0.06), (0, -0.7, 1.12))                          # driver's plank across the sides
    objs.append(new_obj("cart_body", bm, wood))
    bm = bmesh.new()
    bm_cyl(bm, (-TRACK, YA, R), (TRACK, YA, R), 0.04, seg=8)
    for sx in (-1, 1):
        bm_box(bm, (0.06, 0.06, R - 0.72 + 0.1), (sx * 0.5, YA, (R + 0.72) / 2))    # axle block
    objs.append(new_obj("cart_axle", bm, iron))
    bm = bmesh.new()
    for i, (x, y, z, rx_) in enumerate([(-0.22, 0.1, 0.98, 0.0), (0.2, 0.25, 0.98, 0.2), (0.0, 0.5, 1.02, -0.1), (-0.15, 0.95, 0.98, 0.3), (0.22, 1.0, 0.98, 0.0)]):
        vs = bm_box(bm, (0.36, 0.55, 0.3), (x, y, z), Matrix.Rotation(rx_, 3, "Z"))
    objs.append(new_obj("sacks", bm, sack))
    bm = bmesh.new()
    r = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.5)
    bmesh.ops.transform(bm, matrix=Matrix.Translation((0, 0.9, 1.1)) @ Matrix.Diagonal((1.0, 1.1, 0.5, 1)), verts=r["verts"])
    objs.append(new_obj("hay", bm, hay))
    for o in objs[1:]:
        o.parent = objs[0]
    for tag, x in (("wheel_l", -TRACK), ("wheel_r", TRACK)):
        bm = bmesh.new()
        bm_wheel(bm, R, 0.045, spokes=12, hub_r=0.09)
        w = new_obj(tag, bm, wood_d, Vector())
        w.location = (x, YA, R)
        w.parent = objs[0]
        objs.append(w)
    extras = [empty("horse_slot_0", (0, -0.95 - trace_back, 0), objs[0]), empty("driver_seat", (0, -0.7, 1.17), objs[0])]
    col = col_box("horse_cart", (-0.85, -1.0, 0), (0.85, 1.45, 1.5), objs[0])
    objs[0].name = "horse_cart"
    export("horse_cart", objs + extras + [col], anim=False)


def hitch_rail():
    """Tethering rail outside an inn: two oak posts and a rail with iron rings."""
    reset()
    oak = M("rail_oak", (0.25, 0.16, 0.09), 0.85)
    iron = M("rail_iron", (0.08, 0.08, 0.09), 0.5)
    bm = bmesh.new()
    for x in (-1.2, 1.2):
        bm_box(bm, (0.14, 0.14, 1.15), (x, 0, 0.575))
    bm_box(bm, (2.7, 0.1, 0.1), (0, 0, 1.05))
    root = new_obj("hitch_rail", bm, oak)
    bm = bmesh.new()
    for x in (-0.6, 0.6):
        bm_ring(bm, (x, -0.07, 0.98), (0, 1, 0), 0.05, 0.05, 0.008, seg=10, tseg=4)
    rings = new_obj("rings", bm, iron)
    rings.parent = root
    col = col_box("hitch_rail", (-1.3, -0.1, 0), (1.3, 0.1, 1.15), root)
    export("hitch_rail", [root, rings, col], anim=False)


# ------------------------------------------------------------------ main
BUILDS = [
    ("horse", horse),
    ("horse_harnessed", horse_harnessed),
    ("dog_hound", lambda: quaternius_dog("dog_hound", Q_WOLF, 0.62, hound_colours)),
    ("dog_spitz", lambda: quaternius_dog("dog_spitz", Q_HUSKY, 0.50, spitz_colours)),
    ("cat", cat),
    ("pigeon", pigeon),
    ("crow", crow),
    ("hawk", hawk),
    ("carriage", carriage),
    ("horse_cart", horse_cart),
    ("hitch_rail", hitch_rail),
]


def _only():
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1].split(",")
    return None


if __name__ == "__main__":
    if not os.path.exists(HORSE):
        raise SystemExit("[animals] sources missing: run  bash tools/fetch_animals.sh  first")
    only = _only()
    for name, fn in BUILDS:
        if only and name not in only:
            continue
        log("building", name)
        fn()
    log("tris", " ".join("%s=%d" % kv for kv in TRI_LOG.items()))
    log("done")
