"""Animals, harnessed horses and horse-drawn vehicles for Krakow 1795, from third-party CC0 / CC-BY models.

Run:  bash tools/fetch_animals.sh                      (downloads the sources into assets/third_party/)
      blender -b --python assets/blender/build_animals.py [-- --only horse,cat]
Writes assets/models/<name>.glb for: horse, horse_harnessed, dog_hound, dog_spitz, cat, pigeon, crow, hawk,
carriage, horse_cart, coach (replaces build_assets.py's inn-yard coach), hitch_rail. Sources and licences:
docs/ANIMALS.md.

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


# ------------------------------------------------------------------ refined quadrupeds (dogs and cat from the Quaternius rigs)
# The Quaternius meshes are ~1.9k flat-shaded triangles in flat colours. Keeping their rigs and clips, each is
# refined here: vertices welded, silhouette reshaped per breed by bone-weighted displacement (drop ears, deep chest,
# ruff, curled tail...), tail / ear postures baked into a new rest pose, two levels of subdivision then a decimate
# back to a game budget, smooth shading, UVs, the flat colours (or a procedural tabby) baked to a 1024 albedo and
# multiplied by a generated fur texture, with matching fur normal and roughness maps.
TEX_TMP = os.path.join(ROOT, "assets", "textures", "animals")


def _np():
    import numpy
    return numpy


def _box_blur(a, n, axis):
    """Cyclic box blur of length n along axis (keeps the tile seamless)."""
    np = _np()
    out = np.zeros_like(a)
    for k in range(-(n // 2), n - n // 2):
        out += np.roll(a, k, axis=axis)
    return out / n


def fur_maps(name, size=1024, streak=9, seed=1, contrast=0.3):
    """Tileable fur: fine per-hair noise smeared into short strands (direction +u), two octaves. Returns
    (albedo multiplier HxW, normal HxWx3 in 0..1, roughness HxW)."""
    np = _np()
    rng = np.random.default_rng(seed)
    h = np.zeros((size, size), np.float32)
    for amp, s, st in ((1.0, 1, streak), (0.6, 2, streak * 2), (0.35, 8, 3)):
        n = rng.random((size // s, size // s)).astype(np.float32)
        if s > 1:
            n = np.kron(n, np.ones((s, s), np.float32))
        n = _box_blur(n, st, 1)          # strands along u
        n = _box_blur(n, 2, 0)
        h += amp * (n - n.mean()) / (n.std() + 1e-6)
    h = (h - h.min()) / (h.max() - h.min())
    alb = (1.0 - contrast) + contrast * h
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 3.0
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 3.0
    nrm = np.stack([-dx, -dy, np.ones_like(h)], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    rough = 0.55 + 0.35 * (1.0 - h)
    return alb, nrm * 0.5 + 0.5, rough


def np_image(name, arr, non_color=False):
    """Float array (H, W[, 3]) -> packed Blender image (saved as PNG under assets/textures/animals, a cache)."""
    np = _np()
    os.makedirs(TEX_TMP, exist_ok=True)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, -1)
    hgt, wid = arr.shape[:2]
    rgba = np.concatenate([arr, np.ones((hgt, wid, 1), np.float32)], -1).astype(np.float32)
    img = bpy.data.images.new(name, wid, hgt, alpha=False, float_buffer=False)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    img.pixels.foreach_set(rgba.ravel())
    path = os.path.join(TEX_TMP, name + ".png")
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    img.pack()
    return img


def vgroup_weights(mesh, names):
    """Per-vertex summed weight of the vertex groups whose name starts with any of `names`."""
    idx = {g.index for g in mesh.vertex_groups if any(g.name.startswith(n) for n in names)}
    out = [0.0] * len(mesh.data.vertices)
    for v in mesh.data.vertices:
        out[v.index] = min(1.0, sum(g.weight for g in v.groups if g.group in idx))
    return out


def bone_head(rig, name):
    return rig.matrix_world @ rig.data.bones[name].head_local


def bone_tail(rig, name):
    return rig.matrix_world @ rig.data.bones[name].tail_local


def weld(mesh):
    bm = bmesh.new()
    bm.from_mesh(mesh.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.to_mesh(mesh.data)
    bm.free()


def bake_pose_into_rest(rig, mesh, pose):
    """pose: {bone: (Matrix3 armature-space rotation, (sx, sy, sz) bone-local scale)}. Deforms the mesh by the
    pose and makes it the rest pose, so the clips (rest-relative) keep the new posture."""
    ad = rig.animation_data
    muted = []
    if ad:
        ad.action = None
        for t in ad.nla_tracks:
            muted.append((t, t.mute))
            t.mute = True
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
        if pb.name in pose:
            R, sc = pose[pb.name]
            M = pb.bone.matrix_local.to_3x3()
            pb.rotation_quaternion = (M.inverted() @ R @ M).to_quaternion()
            pb.scale = sc
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg)
    co = [v.co.copy() for v in ev.data.vertices]
    for v, c in zip(mesh.data.vertices, co):
        v.co = c
    select([rig], rig)
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.pose.armature_apply(selected=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    for t, m in muted:
        t.mute = m
    bpy.context.view_layer.update()


def reshape(mesh, fn):
    """fn(index, Vector) -> Vector, applied to every vertex (world == local: everything is applied)."""
    for v in mesh.data.vertices:
        v.co = fn(v.index, v.co.copy())


def radial(p, a, b, k):
    """Scale point p away from segment a-b by k (inflate / slim around a bone axis)."""
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-9)))
    c = a + ab * t
    return c + (p - c) * k


def rot_about(p, pivot, axis, ang):
    return pivot + Matrix.Rotation(ang, 3, axis) @ (p - pivot)


def smooth_and_budget(mesh, tris_target, levels=2):
    select([mesh], mesh)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.tris_convert_to_quads()
    bpy.ops.object.mode_set(mode="OBJECT")
    arm = [m for m in mesh.modifiers if m.type == "ARMATURE"]
    for m in arm:
        mesh.modifiers.remove(m)
    sub = mesh.modifiers.new("Subdivision", "SUBSURF")
    sub.levels = sub.render_levels = levels
    sub.uv_smooth = "PRESERVE_BOUNDARIES"
    bpy.ops.object.modifier_apply(modifier=sub.name)
    ntri = sum(len(p.vertices) - 2 for p in mesh.data.polygons)
    if ntri > tris_target:
        dec = mesh.modifiers.new("Decimate", "DECIMATE")
        dec.ratio = tris_target / ntri
        bpy.ops.object.modifier_apply(modifier=dec.name)
    for p in mesh.data.polygons:
        p.use_smooth = True
    return mesh


def attach_armature(mesh, rig):
    for m in list(mesh.modifiers):
        if m.type == "ARMATURE":
            mesh.modifiers.remove(m)
    m = mesh.modifiers.new("Armature", "ARMATURE")
    m.object = rig
    mesh.parent = rig


def bake_fur_material(name, mesh, seed, colour_fn=None, streak=9, contrast=0.3):
    """UV-unwrap, bake the current materials' base colour to 1024, multiply by fur, one Principled material."""
    np = _np()
    select([mesh], mesh)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.01)
    bpy.ops.object.mode_set(mode="OBJECT")
    target = bpy.data.images.new(name + "_bake", 1024, 1024, alpha=False)
    for mat in mesh.data.materials:
        nt = mat.node_tree
        if colour_fn:
            colour_fn(mat)
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = target
        nt.nodes.active = t
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 1
    sc.render.bake.use_pass_direct = False
    sc.render.bake.use_pass_indirect = False
    sc.render.bake.use_pass_color = True
    sc.render.bake.margin = 8
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, use_clear=True, margin=8)
    base = np.array(target.pixels[:], np.float32).reshape(1024, 1024, 4)[..., :3]
    alb, nrm, rough = fur_maps(name, 1024, streak, seed, contrast)
    # byte images hold sRGB values: multiply the fur in linear space, then store as sRGB again
    lin = np.where(base <= 0.04045, base / 12.92, np.power((base + 0.055) / 1.055, 2.4)) * alb[..., None]
    srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.power(np.clip(lin, 0, None), 1 / 2.4) - 0.055)
    a_img = np_image(name + "_albedo", np.clip(srgb, 0, 1))
    n_img = np_image(name + "_normal", nrm, non_color=True)
    r_img = np_image(name + "_rough", rough, non_color=True)
    bpy.data.images.remove(target)
    m = principled(name + "_fur", (1, 1, 1), 0.8, a_img, n_img, spec=0.3)
    bs = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    rt = m.node_tree.nodes.new("ShaderNodeTexImage")
    rt.image = r_img
    m.node_tree.links.new(rt.outputs["Color"], bs.inputs["Roughness"])
    nmap = next(n for n in m.node_tree.nodes if n.type == "NORMAL_MAP")
    nmap.inputs["Strength"].default_value = 0.8
    eyes = [i for i, mt in enumerate(mesh.data.materials) if mt.get("eye")]
    mesh.data.materials.clear()
    mesh.data.materials.append(m)
    for p in mesh.data.polygons:
        p.material_index = 0
    return m


def reground(rig, meshes):
    mn, mx = world_bbox(meshes)
    off = Vector((-(mn.x + mx.x) / 2, -(mn.y + mx.y) / 2, -mn.z))
    for o in [rig] + meshes:
        if o.parent is None:
            o.location += off
    bpy.context.view_layer.update()
    select([rig] + meshes, rig)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)


def load_quaternius(src, clips):
    reset()
    objs = import_gltf(src)
    rig = next(o for o in objs if o.type == "ARMATURE")
    mesh = next(o for o in objs if o.type == "MESH" and o.parent == rig)
    for o in objs:
        if o.type == "MESH" and o is not mesh:
            bpy.data.objects.remove(o)
    rename_clips(rig, clips)
    return rig, mesh


def flat_colours(mesh, recolour):
    """Replace each flat material by a Principled of the recoloured tone (the bake reads these)."""
    for i, mat in enumerate(mesh.data.materials):
        bs = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        c = tuple(bs.inputs["Base Color"].default_value[:3]) if bs else (0.5, 0.5, 0.5)
        mesh.data.materials[i] = principled("src_%d_%s" % (i, mat.name), recolour(mat.name, c), 0.8)


DOG_CLIPS = {"idle": ["AnimalArmature|Idle", "Idle"], "walk": ["AnimalArmature|Walk", "Walk"],
             "run": ["AnimalArmature|Gallop", "Gallop"]}


def _ears_drop(rig, mesh, length=1.9, angle=2.5):
    """Prick ears -> long hound leathers: lengthen, thin, then swing each ear down beside the cheek."""
    for side, sgn in ((".L", 1), (".R", -1)):
        w = vgroup_weights(mesh, ["Ear1" + side, "Ear2" + side, "Ear3" + side, "Ear4" + side])
        piv = bone_head(rig, "Ear1" + side)
        tip = bone_tail(rig, "Ear4" + side)
        up = (tip - piv).normalized()

        def f(i, p, w=w, piv=piv, up=up, sgn=sgn):
            k = min(1.0, max(0.0, (w[i] - 0.1) / 0.4))      # full swing for the leather, none for the skull
            if k <= 0.0:
                return p
            d = p - piv
            along = d.dot(up)
            q = piv + d + up * along * (length - 1.0) * k            # longer
            q.x = piv.x + (q.x - piv.x) * (1.0 - 0.45 * k)           # thinner leather
            q.y = piv.y + (q.y - piv.y) * (1.0 + 0.5 * k)            # broader
            q = rot_about(q, piv, "Y", sgn * angle * k)               # hang down outside the head
            q = rot_about(q, piv, "Z", -sgn * 0.35 * k)               # leather set forward, along the cheek
            return q + Vector((sgn * 0.012 * k, 0, 0))
        reshape(mesh, f)


def _deepen_chest(rig, mesh, k=1.3):
    w = vgroup_weights(mesh, ["Torso"])
    a, b = bone_head(rig, "Torso"), bone_tail(rig, "Torso2")
    fy = bone_head(rig, "FrontUpperLeg.L").y

    def f(i, p):
        if w[i] <= 0.0:
            return p
        c = a.lerp(b, max(0.0, min(1.0, (p.y - a.y) / (b.y - a.y))))
        if p.z >= c.z:
            return p
        # deepest behind the elbows, tucked up towards the loin
        front = max(0.0, min(1.0, 1.0 - abs(p.y - fy) / (abs(a.y - fy) + 1e-6)))
        return Vector((p.x, p.y, c.z + (p.z - c.z) * (1.0 + (k - 1.0) * w[i] * (0.4 + 0.6 * front))))
    reshape(mesh, f)


def _round_skull(rig, mesh, k=1.1, muzzle=1.0):
    w = vgroup_weights(mesh, ["Head"])
    h0, h1 = bone_head(rig, "Head"), bone_tail(rig, "Head")

    def f(i, p):
        if w[i] <= 0.0:
            return p
        fwd = (h1 - h0).normalized()
        d = p - h0
        along = d.dot(fwd)
        if along > (h1 - h0).length * 0.5:     # muzzle: shorten / lengthen along the head axis
            return p + fwd * (along - (h1 - h0).length * 0.5) * (muzzle - 1.0) * w[i]
        return h0 + d * (1.0 + (k - 1.0) * w[i])     # cranium: rounder
    reshape(mesh, f)


def _tail_radius(rig, mesh, k):
    names = [b.name for b in rig.data.bones if b.name.startswith("Tail")]
    w = vgroup_weights(mesh, ["Tail"])
    a, b = bone_head(rig, names[0]), bone_tail(rig, names[-1])
    reshape(mesh, lambda i, p: p.lerp(radial(p, a, b, k), w[i]) if w[i] > 0 else p)


def dog_hound():
    """Ogar polski: black saddle and tan points, long drop ears, deep chest, sabre tail, longer muzzle."""
    rig, mesh = load_quaternius(Q_WOLF, DOG_CLIPS)
    normalise(rig, [mesh], 0.62, "withers", shoulder_bone="FrontUpperLeg.L", head_bone="Head")
    weld(mesh)
    tails = [b.name for b in rig.data.bones if b.name.startswith("Tail")]
    # sabre tail carried low: bake a droop into the rest pose
    bake_pose_into_rest(rig, mesh, {tails[0]: (rx(-1.0), (1, 1, 1)), tails[2]: (rx(0.3), (1, 1, 1))})
    _tail_radius(rig, mesh, 0.55)
    _ears_drop(rig, mesh)
    _deepen_chest(rig, mesh, 1.3)
    _round_skull(rig, mesh, 1.06, muzzle=1.15)
    flat_colours(mesh, hound_colours)
    # the leathers are black on an ogar (the wolf's pale inner ear would bake tan)
    black = next(i for i, m in enumerate(mesh.data.materials) if 0.0 < sum(m.diffuse_color[:3]) < 0.15)
    we = vgroup_weights(mesh, ["Ear"])
    for p in mesh.data.polygons:
        if sum(we[v] for v in p.vertices) / len(p.vertices) > 0.4:
            p.material_index = black
    smooth_and_budget(mesh, 12000)
    bake_fur_material("dog_hound", mesh, seed=11, streak=7, contrast=0.28)
    attach_armature(mesh, rig)
    reground(rig, [mesh])
    rig.name = "dog_hound_rig"
    rig_export("dog_hound", rig, [mesh])


def dog_spitz():
    """Wolfspitz: cream coat, thick ruff and breeches, small prick ears, tail curled over the back."""
    rig, mesh = load_quaternius(Q_HUSKY, DOG_CLIPS)
    normalise(rig, [mesh], 0.50, "withers", shoulder_bone="FrontUpperLeg.L", head_bone="Head")
    weld(mesh)
    tails = [b.name for b in rig.data.bones if b.name.startswith("Tail")]
    bake_pose_into_rest(rig, mesh, {t: (rx(0.6), (1, 1, 1)) for t in tails[1:]})
    _tail_radius(rig, mesh, 1.5)                                    # plume
    wn = vgroup_weights(mesh, ["Neck", "Torso3"])
    wh = vgroup_weights(mesh, ["Head"])
    n0, n1 = bone_head(rig, "Torso3"), bone_tail(rig, "Neck3")
    reshape(mesh, lambda i, p: p.lerp(radial(p, n0, n1, 1.45), wn[i] * (1.0 - wh[i])) if wn[i] > 0 else p)   # ruff
    wt = vgroup_weights(mesh, ["Torso", "Back"])
    t0, t1 = bone_head(rig, "Back"), bone_tail(rig, "Torso2")
    reshape(mesh, lambda i, p: p.lerp(radial(p, t0, t1, 1.12), wt[i]) if wt[i] > 0 else p)                    # coat
    for side in (".L", ".R"):                                        # smaller ears
        we = vgroup_weights(mesh, ["Ear1" + side, "Ear2" + side, "Ear3" + side, "Ear4" + side])
        piv = bone_head(rig, "Ear1" + side)
        reshape(mesh, lambda i, p, we=we, piv=piv: p.lerp(piv + (p - piv) * 0.8, we[i]) if we[i] > 0 else p)
    _round_skull(rig, mesh, 1.08, muzzle=0.85)
    flat_colours(mesh, spitz_colours)
    smooth_and_budget(mesh, 12000)
    bake_fur_material("dog_spitz", mesh, seed=12, streak=12, contrast=0.35)
    attach_armature(mesh, rig)
    reground(rig, [mesh])
    rig.name = "dog_spitz_rig"
    rig_export("dog_spitz", rig, [mesh])


def _tabby(mat):
    """Brown mackerel tabby from object-space position: stripes round the body, pale belly and muzzle."""
    nt = mat.node_tree
    bs = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bs is None:
        return
    base = bs.inputs["Base Color"].default_value[:3]
    if sum(base) / 3 < 0.03:        # eyes and nose stay dark
        return
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Y"
    wave.inputs["Scale"].default_value = 7.0
    wave.inputs["Distortion"].default_value = 7.0
    wave.inputs["Detail Scale"].default_value = 2.5
    wave.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = (0.06, 0.045, 0.03, 1)
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color = (0.34, 0.25, 0.15, 1)
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    # belly and chin pale: blend towards cream below 45% of the height
    belly = nt.nodes.new("ShaderNodeMapRange")
    belly.inputs["From Min"].default_value = mat.get("belly_z", 0.12)
    belly.inputs["From Max"].default_value = mat.get("belly_z", 0.12) + 0.03
    belly.inputs["To Min"].default_value = 1.0
    belly.inputs["To Max"].default_value = 0.0
    nt.links.new(sep.outputs["Z"], belly.inputs["Value"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["B"].default_value = (0.50, 0.42, 0.32, 1)
    nt.links.new(belly.outputs["Result"], mix.inputs["Factor"])
    nt.links.new(ramp.outputs["Color"], mix.inputs["A"])
    nt.links.new(mix.outputs["Result"], bs.inputs["Base Color"])


def cat():
    """House cat reshaped from the Quaternius Husky rig (so it keeps idle / walk and gains a keyed sit): short
    flat face, rounded skull, small wide ears, slim body, shorter legs, long thin tail, tabby fur, whiskers."""
    rig, mesh = load_quaternius(Q_HUSKY, {"idle": ["AnimalArmature|Idle", "Idle"], "walk": ["AnimalArmature|Walk", "Walk"]})
    normalise(rig, [mesh], 0.25, "withers", shoulder_bone="FrontUpperLeg.L", head_bone="Head")
    weld(mesh)
    tails = [b.name for b in rig.data.bones if b.name.startswith("Tail")]
    # tail carried low then curving up (rotations only: scaling bones into the rest pose breaks the clips'
    # translation keys, so the proportions are changed on the mesh instead)
    pose = {t: (rx(0.22), (1, 1, 1)) for t in tails}
    pose[tails[0]] = (rx(-1.0), (1, 1, 1))
    bake_pose_into_rest(rig, mesh, pose)
    _tail_radius(rig, mesh, 0.42)
    _round_skull(rig, mesh, 1.18, muzzle=0.45)
    wh = vgroup_weights(mesh, ["Head", "Ear"])
    hp = bone_head(rig, "Head")
    reshape(mesh, lambda i, p: p.lerp(hp + (p - hp) * 1.3, wh[i]) if wh[i] > 0 else p)     # bigger head
    for side in (".L", ".R"):
        we = vgroup_weights(mesh, ["Ear1" + side, "Ear2" + side, "Ear3" + side, "Ear4" + side])
        piv = bone_head(rig, "Ear1" + side)
        reshape(mesh, lambda i, p, we=we, piv=piv: p.lerp(piv + Vector(((p - piv).x * 1.15, (p - piv).y * 1.3, (p - piv).z * 0.75)), we[i]) if we[i] > 0 else p)
    wt = vgroup_weights(mesh, ["Torso", "Back"])
    t0, t1 = bone_head(rig, "Back"), bone_tail(rig, "Torso2")
    reshape(mesh, lambda i, p: p.lerp(Vector((t0.x + (p.x - t0.x) * 0.82, p.y, p.z)), wt[i]) if wt[i] > 0 else p)
    # softer, thicker limbs: a cat's legs are short and plump next to a husky's
    for b in ("FrontUpperLeg", "FrontLowerLeg", "BackUpperLeg", "BackLowerLeg"):
        for sd in (".L", ".R"):
            wl = vgroup_weights(mesh, [b + sd])
            a0, a1 = bone_head(rig, b + sd), bone_tail(rig, b + sd)
            reshape(mesh, lambda i, p, wl=wl, a0=a0, a1=a1: p.lerp(radial(p, a0, a1, 1.3), wl[i]) if wl[i] > 0 else p)
    flat_colours(mesh, lambda n, c: c)
    for m in mesh.data.materials:
        m["belly_z"] = bone_head(rig, "Back").z * 0.55
    smooth_and_budget(mesh, 9000)
    bake_fur_material("cat", mesh, seed=13, colour_fn=_tabby, streak=6, contrast=0.3)
    attach_armature(mesh, rig)
    # whiskers: thin tapered strands fanning from the muzzle, skinned to the head
    h0, h1 = bone_head(rig, "Head"), bone_tail(rig, "Head")
    fwd = (h1 - h0).normalized()
    vs = world_verts(mesh)
    wh = vgroup_weights(mesh, ["Head"])
    front = [v for i, v in enumerate(vs) if wh[i] > 0.5]
    tip_y = min(v.y for v in front)
    snout = [v for v in front if v.y < tip_y + 0.012]
    sz = sum(v.z for v in snout) / len(snout)
    bm = bmesh.new()
    for sgn in (-1, 1):
        for k in range(5):
            a = Vector((sgn * 0.006, tip_y + 0.008, sz - 0.004 + k * 0.0015))
            d = Vector((sgn * 1.0, 0.35 + 0.1 * k, -0.25 + 0.14 * k)).normalized()
            bm_cyl(bm, a, a + d * (0.055 + 0.006 * k), 0.00035, 0.0001, seg=3, caps=False)
    wk = new_obj("whiskers", bm, principled("cat_whisker", (0.85, 0.83, 0.78), 0.4, spec=0.5))
    weight_all(wk, "Head")
    select([mesh, wk], mesh)
    bpy.ops.object.join()
    attach_armature(mesh, rig)
    reground(rig, [mesh])
    cat_sit(rig)
    rig.name = "cat_rig"
    rig_export("cat", rig, [mesh])


def cat_sit(rig):
    """Sitting: haunches down, forelegs straight, head up, tail wrapped round (keyed on the Quaternius rig)."""
    hip = bone_head(rig, "Back")
    frames = list(range(1, 62, 6))
    tails = [b.name for b in rig.data.bones if b.name.startswith("Tail")]

    def sit(f):
        t = (f - 1) / 60
        breathe = 0.02 * math.sin(t * math.tau)
        r = {"Back": rx(-0.75), "Torso": rx(0.05 + breathe), "Neck1": rx(0.45), "Head": rx(0.25 + 0.03 * math.sin(t * math.tau * 0.5)),
             "FrontUpperLeg.L": rx(0.7), "FrontUpperLeg.R": rx(0.7),
             "BackLeg.L": rx(0.9), "BackLeg.R": rx(0.9),
             "BackUpperLeg.L": rx(-1.6), "BackUpperLeg.R": rx(-1.6),
             "BackLowerLeg.L": rx(2.1), "BackLowerLeg.R": rx(2.1),
             tails[0]: rx(1.6), tails[1]: rz(0.5), tails[2]: rz(0.5), tails[3]: rz(0.5)}
        return r, {"Body": Vector((0, 0, -hip.z * 0.55))}
    act = keyed_action(rig, "sit", frames, sit, with_loc=True)
    for fc in action_fcurves(act):
        for k in fc.keyframe_points:
            k.interpolation = "BEZIER"
    push_nla(rig, act, "sit")


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


# ------------------------------------------------------------------ vehicles (procedural, textured like the buildings)
# Materials come from build_assets.py (imported, not edited): its baked oak / iron / glass / cloth / snow textures,
# tinted per key, with auto_uv() projecting UVs at the same texel density as the buildings.
_BA = None
VEH_KEYS = {   # extra palette keys: (texture kind, tint)
    "veh_lacquer": ("oak", (0.10, 0.10, 0.11)),      # black-lacquered panels, grain just visible
    "veh_coach_green": ("oak", (0.20, 0.36, 0.27)),
    "veh_wheel_red": ("oak", (0.62, 0.20, 0.14)),
    "veh_wheel_yellow": ("oak", (0.80, 0.58, 0.22)),
    "veh_hood": ("cloth", (0.13, 0.11, 0.10)),        # oiled leather hood
    "veh_leather": ("cloth", (0.36, 0.22, 0.13)),
    "veh_cushion": ("cloth", (0.52, 0.12, 0.12)),
    "veh_blind": ("cloth", (0.78, 0.64, 0.42)),
    "veh_hammercloth": ("cloth", (0.55, 0.10, 0.10)),
    "veh_sacking": ("cloth", (0.80, 0.70, 0.52)),
    "veh_hay": ("thatch", (1.0, 0.92, 0.72)),
}


def ba():
    """build_assets.py as a module (materials, texture bakes, auto_uv). Its caches point at datablocks that
    reset() deletes, so they are cleared on every call."""
    global _BA
    if _BA is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("krakow_build_assets", os.path.join(ROOT, "assets", "blender", "build_assets.py"))
        _BA = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_BA)
        for k, (kind, tint) in VEH_KEYS.items():
            _BA.PAL[k] = tint
            _BA.TEX_OF[k] = kind
            _BA.TINT[k] = tint
    return _BA


def VM(key, rough=0.85, emit=None, emit_strength=0.0):
    return ba().M(key, rough, emit, emit_strength)


def veh_reset():
    reset()
    ba()._mats.clear()


def bm_tube(bm, pts, r, seg=6):
    for a, b in zip(pts[:-1], pts[1:]):
        bm_cyl(bm, a, b, r, seg=seg, caps=False)


def part(name, mat, build, parent=None, loc=None):
    bm = bmesh.new()
    build(bm)
    o = new_obj(name, bm, mat)
    if loc is not None:
        for v in o.data.vertices:
            v.co -= Vector(loc)
        o.location = loc
    if parent:
        o.parent = parent
    return o


def wheel(name, radius, width, spokes, paint, loc, parent, hub_r=0.075):
    """Artillery-style wheel about the X axis, origin on the hub: painted felloe and spokes, iron tyre with
    nail heads, turned hub with iron bands and axle cap."""
    def felloe(bm):
        vs = bm_ring(bm, (0, 0, 0), (1, 0, 0), radius - 0.045, radius - 0.045, 0.035, seg=28, tseg=4)
        for v in vs:
            v.co.x *= width / 0.05
        bm_cyl(bm, (-width * 0.8, 0, 0), (width * 0.8, 0, 0), hub_r, hub_r * 0.85, seg=10)          # hub
        for k in range(spokes):
            a = math.tau * (k + 0.5) / spokes
            d = Vector((0, math.cos(a), math.sin(a)))
            bm_cyl(bm, d * hub_r * 0.9 + Vector((0.008 * (-1) ** k, 0, 0)), d * (radius - 0.07), 0.017, 0.013, seg=5, caps=False)

    def iron(bm):
        vs = bm_ring(bm, (0, 0, 0), (1, 0, 0), radius - 0.008, radius - 0.008, 0.012, seg=28, tseg=4)
        for v in vs:
            v.co.x *= (width * 1.1) / 0.024
        for x in (-width * 0.8, width * 0.8):
            bm_ring(bm, (x, 0, 0), (1, 0, 0), hub_r * 0.95, hub_r * 0.95, 0.01, seg=10, tseg=4)
        bm_cyl(bm, (width * 0.8, 0, 0), (width * 1.6, 0, 0), hub_r * 0.55, hub_r * 0.4, seg=8)      # axle cap
        bm_cyl(bm, (-width * 0.8, 0, 0), (-width * 1.3, 0, 0), hub_r * 0.5, seg=8)
    w = part(name, VM(paint), felloe)
    t = part(name + "_iron", VM("iron"), iron)
    select([w, t], w)
    bpy.ops.object.join()
    w.location = loc
    w.parent = parent
    return w


def leaf_spring(bm, centre, half_len, rise=0.08, leaves=3, along="Y"):
    """Stacked elliptic leaf spring: each leaf a flattened arc, longest on top."""
    cx, cy, cz = centre
    for k in range(leaves):
        L = half_len * (1.0 - 0.22 * k)
        pts = []
        for i in range(9):
            t = -1 + 2 * i / 8
            u = t * L
            z = cz + rise * (1 - t * t) * (1 if k == 0 else 0.9) - k * 0.014
            pts.append(Vector((cx, cy + u, z)) if along == "Y" else Vector((cx + u, cy, z)))
        for a, b in zip(pts[:-1], pts[1:]):
            bm_box(bm, ((0.05, (b - a).length, 0.01) if along == "Y" else ((b - a).length, 0.05, 0.01)), (a + b) / 2,
                   Vector((0, 1, 0) if along == "Y" else (1, 0, 0)).rotation_difference((b - a).normalized()).to_matrix())
        # the lower half of the ellipse
        pts2 = [Vector((p.x, p.y, 2 * cz - p.z - 0.02)) for p in pts] if k == 0 else []
        for a, b in zip(pts2[:-1], pts2[1:]):
            bm_box(bm, ((0.05, (b - a).length, 0.01) if along == "Y" else ((b - a).length, 0.05, 0.01)), (a + b) / 2,
                   Vector((0, 1, 0) if along == "Y" else (1, 0, 0)).rotation_difference((b - a).normalized()).to_matrix())


def c_spring(bm, base, up=0.55, depth=0.28, back=1, seg=7):
    """C-spring standing on the perch end: rises from `base`, curls over towards the body (direction `back`)."""
    pts = []
    for i in range(seg + 1):
        a = math.pi * 1.25 * i / seg - math.pi * 0.5
        pts.append(Vector(base) + Vector((0, back * (depth * (1 - math.cos(a + math.pi * 0.5)) * 0.5) * -1, up * 0.5 * (1 + math.sin(a)))))
    for a, b in zip(pts[:-1], pts[1:]):
        bm_box(bm, (0.06, 0.035, (b - a).length + 0.01), (a + b) / 2, Vector((0, 0, 1)).rotation_difference((b - a).normalized()).to_matrix())
    return pts[-1]


def lamp(bm_frame, bm_glass, c, s=1.0):
    """Carriage lamp: iron box frame with a chimney cap, glass faces (separate emissive mesh)."""
    x, y, z = c
    bm_box(bm_frame, (0.12 * s, 0.12 * s, 0.02), (x, y, z - 0.09 * s))
    bm_box(bm_frame, (0.13 * s, 0.13 * s, 0.025), (x, y, z + 0.09 * s))
    bm_cyl(bm_frame, (x, y, z + 0.1 * s), (x, y, z + 0.17 * s), 0.035 * s, 0.012 * s, seg=6)
    for sx in (-1, 1):
        for sy in (-1, 1):
            bm_box(bm_frame, (0.012, 0.012, 0.18 * s), (x + sx * 0.055 * s, y + sy * 0.055 * s, z))
    bm_box(bm_glass, (0.1 * s, 0.1 * s, 0.16 * s), (x, y, z))


def finish_uvs(objs):
    for o in objs:
        if o.type == "MESH" and not o.name.endswith("-colonly"):
            ba().auto_uv(o)


def carriage(trace_back=1.95):
    """Dorozka: Krakow's hired open cab. Black-lacquered body with a red coach line, crimson cushions, a folding
    leather hood on iron hoops and landau irons, raised driver's box with cushion and footboard, elliptic leaf
    springs on both axles, iron-tyred red wheels, pole, splinter bar and swingletrees for the pair, steps, two
    lamps, whip. Front at -Y; horses in the horse_slot empties."""
    veh_reset()
    lac, red, iron, wood = VM("veh_lacquer"), VM("veh_wheel_red"), VM("iron"), VM("wood_dark")
    hood, cush, leather = VM("veh_hood"), VM("veh_cushion"), VM("veh_leather")
    glass = VM("veh_lampglass", 0.2, emit=(1.0, 0.72, 0.36), emit_strength=4.0) if "veh_lampglass" in ba().PAL else None
    if glass is None:
        ba().PAL["veh_lampglass"] = (1.0, 0.85, 0.6)
        glass = VM("veh_lampglass", 0.2, emit=(1.0, 0.72, 0.36), emit_strength=4.0)
    RW, FW, TRACK = 0.66, 0.46, 0.78
    YR, YF = 0.95, -1.05
    root = part("carriage", iron, lambda bm: (
        bm_cyl(bm, (-TRACK, YR, RW), (TRACK, YR, RW), 0.032, seg=8),
        bm_cyl(bm, (-TRACK, YF, FW), (TRACK, YF, FW), 0.032, seg=8),
        [leaf_spring(bm, (sx * 0.5, YR, RW + 0.12), 0.34) for sx in (-1, 1)],
        [leaf_spring(bm, (sx * 0.45, YF, FW + 0.12), 0.28) for sx in (-1, 1)],
        [bm_box(bm, (0.2, 0.08, 0.02), (sx * 0.62, 0.0, 0.52)) for sx in (-1, 1)],          # step treads
        [bm_cyl(bm, (sx * 0.56, 0.0, 0.92), (sx * 0.62, 0.0, 0.53), 0.012, seg=5) for sx in (-1, 1)],
        [bm_cyl(bm, (sx * 0.62, -0.62, 1.52), (sx * 0.62, -0.95, 1.2), 0.012, seg=5) for sx in (-1, 1)],   # box irons
        [bm_cyl(bm, (sx * 0.66, 0.55, 1.35), (sx * 0.66, 1.0, 1.62), 0.012, seg=5) for sx in (-1, 1)],    # landau irons
        bm_cyl(bm, (0.62, -0.62, 1.55), (0.95, -0.2, 2.9), 0.007, 0.003, seg=4),                        # whip
        bm_cyl(bm, (0.6, -0.64, 1.45), (0.64, -0.6, 1.65), 0.015, seg=6),                                # whip socket
    ))
    parts = [root]
    parts.append(part("perch", wood, lambda bm: (
        bm_box(bm, (0.1, abs(YR - YF) + 0.2, 0.08), (0, (YR + YF) / 2, 0.55)),
        bm_cyl(bm, (0, YF, 0.56), (0, -4.35, 0.96), 0.04, 0.03, seg=8),                         # pole to the horses' chests
        bm_box(bm, (1.7, 0.07, 0.07), (0, -1.5, 0.80)),                                          # splinter bar
        [bm_box(bm, (0.78, 0.05, 0.05), (sx * 0.62, -1.56, 0.92)) for sx in (-1, 1)],            # swingletrees
        [bm_cyl(bm, (sx * 0.62, -1.5, 0.8), (sx * 0.62, -1.56, 0.92), 0.015, seg=5) for sx in (-1, 1)],
        bm_cyl(bm, (0, -1.5, 0.8), (0, YF, FW + 0.05), 0.03, seg=6),
    ), root))
    def body(bm):
        bm_box(bm, (1.26, 1.5, 0.05), (0, 0.35, 0.95))                                          # floor
        for sx in (-1, 1):
            # side panel: lower edge swept up at the front, the classic cab line
            vs = bm_box(bm, (0.04, 1.3, 0.44), (sx * 0.63, 0.45, 1.18))
            for v in vs:
                if v.co.z < 1.1 and v.co.y < 0.0:
                    v.co.z += 0.12
            bm_box(bm, (0.04, 0.5, 0.24), (sx * 0.63, -0.45, 1.08))                              # footwell sides
            # mudguard over the front wheel
            pts = [Vector((sx * 0.7, YF + FW * math.cos(a), FW + 0.08 + FW * math.sin(a))) for a in [math.radians(d) for d in range(20, 181, 32)]]
            for a, b in zip(pts[:-1], pts[1:]):
                bm_box(bm, (0.16, (b - a).length + 0.01, 0.012), (a + b) / 2, Vector((0, 1, 0)).rotation_difference((b - a).normalized()).to_matrix())
        bm_box(bm, (1.3, 0.05, 0.62), (0, 1.12, 1.28))                                          # back
        bm_box(bm, (1.26, 0.04, 0.34), (0, -0.7, 1.1))                                          # dash
        bm_box(bm, (0.9, 0.42, 0.32), (0, -0.55, 1.38))                                         # driver's box
        vs = bm_box(bm, (0.9, 0.5, 0.035), (0, -1.02, 1.03), Matrix.Rotation(math.radians(-18), 3, "X"))   # footboard
    parts.append(part("body", lac, body, root))
    parts.append(part("coachline", red, lambda bm: [
        (bm_box(bm, (0.046, 1.28, 0.02), (sx * 0.632, 0.46, 1.33)),
         bm_box(bm, (0.046, 1.1, 0.012), (sx * 0.632, 0.52, 1.06)),
         bm_box(bm, (0.046, 0.02, 0.26), (sx * 0.632, 1.08, 1.2))) for sx in (-1, 1)] + [bm_box(bm, (0.92, 0.02, 0.02), (0, -0.765, 1.5))], root))
    parts.append(part("cushions", cush, lambda bm: (
        bm_box(bm, (1.18, 0.55, 0.14), (0, 0.78, 1.12)), bm_box(bm, (1.18, 0.12, 0.45), (0, 1.05, 1.40)),
        bm_box(bm, (0.94, 0.46, 0.1), (0, -0.55, 1.58)), bm_box(bm, (0.94, 0.06, 0.22), (0, -0.32, 1.72))), root))
    def hood_shell(bm):
        hc, hr, seg = Vector((0, 0.95, 1.30)), 0.68, 12
        cols = []
        for i in range(seg + 1):
            a = math.radians(-8 + 104 * i / seg)
            d = Vector((0, math.sin(a), math.cos(a)))
            # leather sags a little between the hoops
            sag = 0.025 * abs(math.sin(i / seg * math.pi * 3))
            cols.append([bm.verts.new(hc + Vector((x, 0, 0)) + d * (hr - sag)) for x in (-0.66, 0, 0.66)])
        for i in range(seg):
            for j in range(2):
                bm.faces.new((cols[i][j], cols[i][j + 1], cols[i + 1][j + 1], cols[i + 1][j]))
        for side, xi in ((-0.66, 0), (0.66, 2)):
            ctr = bm.verts.new(hc + Vector((side, 0, 0)))
            ring = [c[xi] for c in cols]
            for i in range(seg):
                bm.faces.new((ctr, ring[i], ring[i + 1]) if side > 0 else (ctr, ring[i + 1], ring[i]))
        bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.018)
    parts.append(part("hood", hood, hood_shell, root))
    def hoops(bm):
        hc, hr = Vector((0, 0.95, 1.30)), 0.69
        for k in range(4):
            a = math.radians(-8 + 104 * k / 3)
            pts = [hc + Vector((x, 0, 0)) + Vector((0, math.sin(a), math.cos(a))) * hr for x in (-0.68, 0.68)]
            bm_tube(bm, [pts[0], pts[1]], 0.012)
            for p in pts:
                bm_tube(bm, [hc + Vector((p.x, 0, 0)), p], 0.01, seg=4)                    # bows down to the joint
        for sx in (-1, 1):
            bm.verts.ensure_lookup_table()
            r = bmesh.ops.create_uvsphere(bm, u_segments=6, v_segments=4, radius=0.03)
            bmesh.ops.translate(bm, verts=r["verts"], vec=hc + Vector((sx * 0.69, 0, 0)))
    parts.append(part("hood_irons", iron, hoops, root))
    fr, gl = bmesh.new(), bmesh.new()
    for sx in (-1, 1):
        lamp(fr, gl, (sx * 0.5, -0.78, 1.79))
        bm_cyl(fr, (sx * 0.5, -0.78, 1.45), (sx * 0.5, -0.78, 1.7), 0.012, seg=5)
    lf = new_obj("lamp_frames", fr, iron)
    lf.parent = root
    lg = new_obj("lamp_glass", gl, glass)
    lg.parent = root
    parts += [lf, lg]
    for tag, y, r in (("wheel_rl", YR, RW), ("wheel_rr", YR, RW), ("wheel_fl", YF, FW), ("wheel_fr", YF, FW)):
        parts.append(wheel(tag, r, 0.034, 14 if r > 0.5 else 12, "veh_wheel_red", (-TRACK if tag.endswith("l") else TRACK, y, r), root))
    finish_uvs(parts)
    extras = [empty("horse_slot_0", (-0.62, -1.5 - trace_back, 0), root), empty("horse_slot_1", (0.62, -1.5 - trace_back, 0), root),
              empty("driver_seat", (0, -0.55, 1.63), root), empty("lamp_L", (-0.5, -0.78, 1.8), root), empty("lamp_R", (0.5, -0.78, 1.8), root)]
    col = col_box("carriage", (-0.95, -1.6, 0), (0.95, 1.3, 2.1), root)
    export("carriage", parts + extras + [col], anim=False)


def horse_cart(trace_back=1.95):
    """Peasant ladder cart (woz drabiniasty): plank bed on two beams, raked ladder sides, iron-shod wheels,
    shafts reaching the horse's shoulders, a driver's plank, a load of grain sacks and loose hay. Front at -Y."""
    veh_reset()
    wood, dark, iron = VM("wood"), VM("wood_dark"), VM("iron")
    R, TRACK, YA = 0.62, 0.72, 0.3
    root = part("horse_cart", dark, lambda bm: [
        (bm_box(bm, (0.09, 2.5, 0.09), (sx * 0.46, 0.25, 0.72)),                                 # bed beams
         bm_cyl(bm, (sx * 0.46, -1.0, 0.72), (sx * 0.5, -3.95, 1.05), 0.035, 0.028, seg=6),      # shafts
         bm_box(bm, (0.08, 0.1, R - 0.72 + 0.14), (sx * 0.46, YA, (R + 0.72) / 2 - 0.02))) for sx in (-1, 1)])
    parts = [root]
    def bed(bm):
        for k in range(7):                                  # loose planks with gaps
            x = -0.42 + k * 0.14
            bm_box(bm, (0.125, 2.4, 0.035), (x, 0.25, 0.785))
        for sx in (-1, 1):
            bm_cyl(bm, (sx * 0.62, -0.95, 0.8), (sx * 0.66, 1.42, 1.32), 0.028, seg=6)           # ladder rails
            bm_cyl(bm, (sx * 0.55, -0.95, 0.8), (sx * 0.58, 1.42, 0.92), 0.028, seg=6)
            for k in range(10):
                y = -0.88 + k * 0.25
                zt = 0.8 + (y + 0.95) / 2.37 * 0.52
                bm_cyl(bm, (sx * 0.55, y, 0.8), (sx * 0.63, y, zt + 0.02), 0.013, seg=5)         # rungs
            bm_cyl(bm, (sx * 0.5, -0.6, 0.75), (sx * 0.62, -0.6, 1.02), 0.02, seg=5)             # stake (lushnia)
        bm_box(bm, (1.05, 0.05, 0.32), (0, -0.92, 0.94))                                         # front board
        bm_box(bm, (1.05, 0.05, 0.26), (0, 1.4, 0.92))                                           # tailboard
        bm_box(bm, (0.95, 0.26, 0.05), (0, -0.7, 1.12))                                          # driver's plank
    parts.append(part("bed", wood, bed, root))
    parts.append(part("axle", iron, lambda bm: (bm_cyl(bm, (-TRACK, YA, R), (TRACK, YA, R), 0.04, seg=8),
                                                [bm_box(bm, (0.1, 0.12, 0.02), (sx * 0.5, -3.5, 1.0)) for sx in (-1, 1)]), root))
    sacking = VM("veh_sacking")
    def sacks(bm):
        for (x, y, z, rz_, sc) in [(-0.22, 0.05, 0.99, 0.0, 1.0), (0.21, 0.2, 0.99, 0.25, 1.0), (0.0, 0.5, 1.05, -0.1, 0.95),
                                   (-0.18, 0.95, 0.98, 0.35, 1.0), (0.22, 1.05, 0.98, 0.0, 0.9), (0.02, 0.7, 1.28, 1.4, 0.85)]:
            r = bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.5)
            bmesh.ops.transform(bm, matrix=Matrix.Translation((x, y, z)) @ Matrix.Rotation(rz_, 4, "Z") @ Matrix.Diagonal((0.2 * sc, 0.3 * sc, 0.15 * sc, 1)), verts=r["verts"])
            bm_cyl(bm, (x + 0.29 * sc * math.sin(-rz_) * 0, y - 0.3 * sc, z + 0.02), (x, y - 0.36 * sc, z + 0.05), 0.04, 0.015, seg=5)   # tied neck
    parts.append(part("sacks", sacking, sacks, root))
    def hay(bm):
        r = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.5)
        rng = __import__("random").Random(7)
        for v in r["verts"]:
            v.co.x *= 1.05
            v.co.y *= 1.35
            v.co.z *= 0.55
            v.co += v.co.normalized() * rng.uniform(-0.04, 0.05)
        bmesh.ops.translate(bm, verts=r["verts"], vec=(0, 0.55, 1.15))
    parts.append(part("hay", VM("veh_hay"), hay, root))
    for tag, x in (("wheel_l", -TRACK), ("wheel_r", TRACK)):
        parts.append(wheel(tag, R, 0.045, 12, "wood_dark", (x, YA, R), root, hub_r=0.09))
    finish_uvs(parts)
    extras = [empty("horse_slot_0", (0, -0.95 - trace_back, 0), root), empty("driver_seat", (0, -0.7, 1.17), root)]
    col = col_box("horse_cart", (-0.85, -1.0, 0), (0.85, 1.45, 1.5), root)
    export("horse_cart", parts + extras + [col], anim=False)


def coach():
    """Travelling coach (kareta) standing in the inn yard (placed by scripts/city/dressing.gd, replaces the
    build_assets.py version of the same name). Closed green body with a swelled lower panel, glazed doors with
    half-drawn blinds and a coat-of-arms roundel, quarter lights, black roof with a luggage rail, strapped trunks
    under snow, four C-springs with leather braces over a perch, red iron-tyred wheels, coachman's box with a
    hammercloth, lamps, steps, pole. Built front -Y, then turned so the pole points +X like the old one."""
    veh_reset()
    green, lac, red, iron, wood = VM("veh_coach_green"), VM("veh_lacquer"), VM("veh_wheel_red"), VM("iron"), VM("wood_dark")
    leather, blind, hc = VM("veh_leather"), VM("veh_blind"), VM("veh_hammercloth")
    gold = VM("gold", 0.35)
    ba().PAL.setdefault("veh_lampglass", (1.0, 0.85, 0.6))
    lampg = VM("veh_lampglass", 0.2, emit=(1.0, 0.72, 0.36), emit_strength=4.0)
    glass = VM("glass")
    RW, FW, TR = 0.72, 0.52, 0.86
    YR, YF = 1.05, -1.15
    Z0, Z1, BL, BW = 0.78, 2.02, 1.8, 1.36     # body bottom, top, length, width
    root = part("coach", wood, lambda bm: (
        bm_box(bm, (0.12, abs(YR - YF) + 0.5, 0.1), (0, (YR + YF) / 2, 0.52)),                    # perch
        bm_box(bm, (1.3, 0.14, 0.12), (0, YF, FW + 0.12)),                                         # fore carriage bed
        bm_box(bm, (1.3, 0.14, 0.12), (0, YR, RW + 0.02)),
        bm_cyl(bm, (0, YF - 0.1, 0.56), (0, -3.2, 0.45), 0.045, 0.034, seg=8),                     # pole
        bm_box(bm, (0.95, 0.06, 0.06), (0, -1.75, 0.58)),                                          # swingletree bar
    ))
    parts = [root]
    parts.append(part("running_gear", iron, lambda bm: (
        bm_cyl(bm, (-TR, YR, RW), (TR, YR, RW), 0.04, seg=8), bm_cyl(bm, (-TR, YF, FW), (TR, YF, FW), 0.04, seg=8),
        [c_spring(bm, (sx * 0.55, y, 0.62 if y > 0 else FW + 0.18), up=0.5, depth=0.3, back=(1 if y > 0 else -1)) for sx in (-1, 1) for y in (YR + 0.2, YF - 0.15)],
        [bm_box(bm, (0.26, 0.12, 0.02), (sx * 0.78, 0.0, 0.55)) for sx in (-1, 1)],                # steps
        [bm_cyl(bm, (sx * 0.66, 0.0, Z0 + 0.02), (sx * 0.78, 0.0, 0.56), 0.012, seg=5) for sx in (-1, 1)],
        [bm_cyl(bm, (sx * 0.5, YF - 0.35, 1.5), (sx * 0.5, YF - 0.62, 1.12), 0.014, seg=5) for sx in (-1, 1)],   # box irons
    ), root))
    parts.append(part("braces", leather, lambda bm: [
        bm_cyl(bm, (sx * 0.55, y + (0.15 if y > 0 else -0.15) * -1 * (1 if y > 0 else -1) * 0, 1.08 if y > 0 else FW + 0.66), (sx * 0.5, y * 0.82, Z0 + 0.06), 0.022, seg=5)
        for sx in (-1, 1) for y in (YR + 0.2, YF - 0.15)] + [bm_box(bm, (0.05, abs(YR - YF), 0.02), (sx * 0.5, 0, Z0 - 0.05)) for sx in (-1, 1)], root))
    def shell(bm):
        r = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.transform(bm, matrix=Matrix.Translation((0, 0, (Z0 + Z1) / 2)) @ Matrix.Diagonal((BW, BL, Z1 - Z0, 1)), verts=r["verts"])
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=3, use_grid_fill=True)
        for v in bm.verts:
            t = max(0.0, min(1.0, (v.co.z - Z0) / (Z1 - Z0)))
            # swelled lower panel (bombe): narrower and shorter at the sill, full at the waist
            f = 0.78 + 0.22 * min(1.0, t / 0.45) ** 0.6
            v.co.y *= f
            v.co.x *= 0.94 + 0.06 * min(1.0, t / 0.45)
    parts.append(part("body", green, shell, root))
    def trim(bm):
        for sx in (-1, 1):
            x = sx * (BW / 2 + 0.006)
            bm_box(bm, (0.014, 0.66, 0.025), (x, 0.0, Z1 - 0.02))                                  # door frame
            bm_box(bm, (0.014, 0.025, Z1 - Z0 - 0.1), (x, -0.33, (Z0 + Z1) / 2))
            bm_box(bm, (0.014, 0.025, Z1 - Z0 - 0.1), (x, 0.33, (Z0 + Z1) / 2))
            bm_box(bm, (0.014, BL, 0.02), (x, 0, Z0 + (Z1 - Z0) * 0.47))                           # waist moulding
            bm_ring(bm, (x * 1.004, 0.0, Z0 + 0.36), (1, 0, 0), 0.1, 0.1, 0.012, seg=16, tseg=4)   # roundel ring
            bm_box(bm, (0.02, 0.08, 0.02), (x * 1.01, 0.22, Z0 + 0.62))                             # door handle
    parts.append(part("gilt", gold, trim, root))
    parts.append(part("arms", VM("veh_hammercloth"), lambda bm: [
        bm_cyl(bm, (sx * (BW / 2 + 0.002), 0, Z0 + 0.36), (sx * (BW / 2 + 0.012), 0, Z0 + 0.36), 0.09, seg=14) for sx in (-1, 1)], root))
    parts.append(part("arms_eagle", VM("snow"), lambda bm: [
        bm_box(bm, (0.01, 0.07, 0.09), (sx * (BW / 2 + 0.015), 0, Z0 + 0.36), Matrix.Rotation(math.radians(45), 3, "X")) for sx in (-1, 1)], root))
    def windows(bm):
        for sx in (-1, 1):
            x = sx * (BW / 2 + 0.004)
            bm_box(bm, (0.01, 0.5, 0.46), (x, 0.0, Z1 - 0.32))                                     # door light
            for y in (-0.62, 0.62):
                bm_box(bm, (0.01, 0.34, 0.42), (x * 0.985, y * 0.95, Z1 - 0.32))                   # quarter lights
        bm_box(bm, (1.0, 0.01, 0.4), (0, -BL / 2 - 0.004, Z1 - 0.32))                              # front light
    parts.append(part("glass", glass, windows, root))
    def blinds(bm):
        for sx in (-1, 1):
            x = sx * (BW / 2 + 0.008)
            bm_box(bm, (0.008, 0.48, 0.2), (x, 0.0, Z1 - 0.2))                                     # half drawn
            bm_cyl(bm, (x, -0.25, Z1 - 0.09), (x, 0.25, Z1 - 0.09), 0.018, seg=6)
            for y in (-0.62, 0.62):
                bm_box(bm, (0.008, 0.32, 0.12), (x * 0.99, y * 0.95, Z1 - 0.17))
    parts.append(part("blinds", blind, blinds, root))
    def roof(bm):
        r = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.transform(bm, matrix=Matrix.Translation((0, 0, Z1 + 0.05)) @ Matrix.Diagonal((BW + 0.1, BL + 0.1, 0.1, 1)), verts=r["verts"])
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=2, use_grid_fill=True)
        for v in bm.verts:
            if v.co.z > Z1 + 0.06:
                v.co.z += 0.06 * (1 - (2 * v.co.x / (BW + 0.1)) ** 2)                              # domed
        bm_box(bm, (0.95, 0.46, 0.34), (0, YF - 0.38, 1.36))                                       # coachman's box
    parts.append(part("roof", lac, roof, root))
    parts.append(part("hammercloth", hc, lambda bm: (bm_box(bm, (1.0, 0.52, 0.34), (0, YF - 0.38, 1.2)),
                                                    bm_box(bm, (1.02, 0.02, 0.06), (0, YF - 0.12, 1.02))), root))
    parts.append(part("box_cushion", VM("veh_cushion"), lambda bm: (bm_box(bm, (0.96, 0.44, 0.1), (0, YF - 0.38, 1.58)),
                                                                   bm_box(bm, (0.96, 0.07, 0.28), (0, YF - 0.14, 1.72))), root))
    parts.append(part("footboard", wood, lambda bm: bm_box(bm, (0.9, 0.46, 0.035), (0, YF - 0.82, 1.2), Matrix.Rotation(math.radians(-20), 3, "X")), root))
    def rail(bm):
        zt = Z1 + 0.14
        hx, hy = BW / 2, BL / 2 - 0.05
        for sx in (-1, 1):
            for sy in (-1, 1):
                bm_cyl(bm, (sx * hx, sy * hy, zt - 0.04), (sx * hx, sy * hy, zt + 0.16), 0.012, seg=5)
            bm_cyl(bm, (sx * hx, -hy, zt + 0.16), (sx * hx, hy, zt + 0.16), 0.01, seg=5)
            bm_cyl(bm, (-hx, sx * hy, zt + 0.16), (hx, sx * hy, zt + 0.16), 0.01, seg=5)
        for y in (-0.3, 0.45):                                                                      # trunk straps
            bm_box(bm, (0.92, 0.04, 0.012), (0, y, zt + 0.42))
    parts.append(part("roof_rail", iron, rail, root))
    parts.append(part("trunks", leather, lambda bm: (bm_box(bm, (0.9, 0.62, 0.38), (0, -0.3, Z1 + 0.33)),
                                                    bm_box(bm, (0.7, 0.5, 0.3), (0.05, 0.45, Z1 + 0.29))), root))
    def snowcap(bm):
        r = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=6, radius=0.5)
        bmesh.ops.transform(bm, matrix=Matrix.Translation((0, -0.3, Z1 + 0.53)) @ Matrix.Diagonal((0.92, 0.64, 0.07, 1)), verts=r["verts"])
        r = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=6, radius=0.5)
        bmesh.ops.transform(bm, matrix=Matrix.Translation((0, 0.8, Z1 + 0.16)) @ Matrix.Diagonal((1.3, 0.3, 0.05, 1)), verts=r["verts"])
    parts.append(part("snow", VM("snow"), snowcap, root))
    fr, gl = bmesh.new(), bmesh.new()
    for sx in (-1, 1):
        lamp(fr, gl, (sx * 0.56, YF - 0.12, 1.78), 1.1)
        bm_cyl(fr, (sx * 0.52, YF - 0.12, 1.45), (sx * 0.56, YF - 0.12, 1.68), 0.012, seg=5)
    lf = new_obj("lamp_frames", fr, iron)
    lg = new_obj("lamp_glass", gl, lampg)
    lf.parent = lg.parent = root
    parts += [lf, lg]
    for tag, y, r in (("wheel_rl", YR, RW), ("wheel_rr", YR, RW), ("wheel_fl", YF, FW), ("wheel_fr", YF, FW)):
        parts.append(wheel(tag, r, 0.04, 14 if r > 0.6 else 12, "veh_wheel_red", (-TR if tag.endswith("l") else TR, y, r), root, hub_r=0.085))
    finish_uvs(parts)
    col = col_box("coach", (-0.95, -1.5, 0), (0.95, 1.55, 2.4), root)
    root.rotation_euler.z = math.pi / 2          # front -Y -> +X, as build_assets placed it
    export("coach", parts + [col], anim=False)


def M(name, color, rough=0.6, **kw):
    return principled("veh_" + name, color, rough, **kw)


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
    ("dog_hound", dog_hound),
    ("dog_spitz", dog_spitz),
    ("cat", cat),
    ("pigeon", pigeon),
    ("crow", crow),
    ("hawk", hawk),
    ("carriage", carriage),
    ("horse_cart", horse_cart),
    ("coach", coach),
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
