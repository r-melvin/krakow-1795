"""Shared animation library for every Krakow 1795 human.

Run:  blender -b --python assets/blender/build_animations.py [-- --rebuild] [-- clip1 clip2 ...]
Out:  assets/models/anim_library.glb (game_engine armature, a tiny proxy skin, one glTF animation per clip)

Builds ONE reference human exactly the way build_characters.py does (MPFB body with the watchman's macro
sliders, MPFB "game_engine" rig, rest_arms_down() as the rest pose) and authors every clip procedurally.
All clips are in place (no root motion); only the pelvis carries a translation track.

Pose model. A pose is a flat dict of anatomical parameters (degrees / metres). Each bone gets a rotation R
expressed in world-aligned axes carried by its parent (X = character's left, Y = character's back, Z = up;
MakeHuman faces -Y). A bone's world delta is D = D_parent @ R and its pose basis is Qrest^-1 @ R @ Qrest,
so every bone rotates about intuitive body axes regardless of MPFB's bone rolls. Legs and arms can be
driven by analytic two-bone IK (planted feet, hands on a musket), the head can be gaze-stabilised.
Keyed clips interpolate parameters with monotone cubic (PCHIP) splines, so extremes ease in and out.

The same "world delta" rule is what scripts/core/assets.gd uses to retarget these clips onto each
character's own rest pose (q_target = A @ q_lib @ B, see docs/ANIMATION.md).

Licence: authored here, CC0 like the rest of the project's generated assets. No mocap, no Mixamo.
"""
import bpy
import math
import os
import sys
from mathutils import Matrix, Quaternion, Vector, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "assets", "models", "anim_library.glb")
CACHE = os.path.join(os.environ.get("ANIM_CACHE", "/tmp"), "krakow_anim_reference.blend")
FPS = 30
REF_NAME = "watchman"


def log(*a):
    print("[anim]", *a)


# ------------------------------------------------------------------ reference human
def build_reference():
    """Body + game_engine rig + arms-down rest, the same calls build_characters.build() makes."""
    import build_characters as bc
    from bl_ext.user_default.mpfb.services.humanservice import HumanService
    spec = dict(bc.ALL[REF_NAME])
    h = bc.make_body(spec)
    rig = HumanService.add_builtin_rig(h, "game_engine")
    bc.rest_arms_down(rig)
    rig.name = "Human_rig"
    # musket geometry in the rest pose (build_characters._musket): butt, axis +Z, belly +Y
    hand = (rig.matrix_world @ rig.data.bones["hand_r"].matrix_local).to_translation()
    rig["musket_butt"] = (hand.x - 0.11, hand.y + 0.02, hand.z - 0.30)
    for o in list(bpy.data.objects):
        if o.type == "MESH":
            bpy.data.objects.remove(o)
    proxy_mesh(rig)
    bpy.ops.wm.save_as_mainfile(filepath=CACHE)
    return rig


def proxy_mesh(rig):
    """A tiny skinned mesh (one small tetrahedron per bone) so glTF writes a skin and Godot builds a Skeleton3D."""
    verts, faces, owners = [], [], []
    for b in rig.data.bones:
        c = b.head_local
        s = 0.004
        base = len(verts)
        verts += [c + Vector((s, 0, 0)), c + Vector((-s, s, 0)), c + Vector((-s, -s, 0)), c + Vector((0, 0, s))]
        faces += [(base, base + 1, base + 2), (base, base + 1, base + 3), (base + 1, base + 2, base + 3), (base, base + 2, base + 3)]
        owners.append(b.name)
    me = bpy.data.meshes.new("anim_proxy")
    me.from_pydata([tuple(v) for v in verts], [], faces)
    o = bpy.data.objects.new("anim_proxy", me)
    bpy.context.scene.collection.objects.link(o)
    for i, name in enumerate(owners):
        vg = o.vertex_groups.new(name=name)
        vg.add([4 * i, 4 * i + 1, 4 * i + 2, 4 * i + 3], 1.0, "REPLACE")
    o.parent = rig
    am = o.modifiers.new("arm", "ARMATURE")
    am.object = rig
    return o


def load_reference(rebuild=False):
    if not rebuild and os.path.exists(CACHE):
        bpy.ops.wm.open_mainfile(filepath=CACHE)
        rig = bpy.data.objects["Human_rig"]
        log("reference from cache", CACHE)
        return rig
    return build_reference()


# ------------------------------------------------------------------ math helpers
def rx(d):
    return Quaternion((1, 0, 0), math.radians(d))


def ry(d):
    return Quaternion((0, 1, 0), math.radians(d))


def rz(d):
    return Quaternion((0, 0, 1), math.radians(d))


def body(x, y, z):
    """Body frame (x = left, y = forward, z = up) to Blender world (MakeHuman faces -Y)."""
    return Vector((x, -y, z))


def frame_quat(direction, pole):
    d = direction.normalized()
    p = (pole - d * pole.dot(d))
    if p.length < 1e-6:
        p = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((0, 1, 0))
        p = p - d * p.dot(d)
    p.normalize()
    z = d.cross(p)
    m = Matrix((d, p, z)).transposed()
    return m.to_quaternion()


def align(rest_dir, rest_pole, dir_, pole):
    return frame_quat(dir_, pole) @ frame_quat(rest_dir, rest_pole).inverted()


def ss(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def lerp(a, b, t):
    return a + (b - a) * t


SIDES = (("L", "l", 1.0), ("R", "r", -1.0))


# ------------------------------------------------------------------ rig model
class RigModel:
    def __init__(self, rig):
        self.rig = rig
        self.order = []
        self.parent = {}
        self.head = {}
        self.q = {}
        self.children = {}

        def walk(b):
            self.order.append(b.name)
            for c in b.children:
                walk(c)
        for b in rig.data.bones:
            if b.parent is None:
                walk(b)
        for b in rig.data.bones:
            self.parent[b.name] = b.parent.name if b.parent else None
            self.head[b.name] = b.head_local.copy()
            self.q[b.name] = b.matrix_local.to_quaternion()
        H = self.head
        self.leg = {}
        for S, s, _ in SIDES:
            self.leg[S] = ((H["calf_" + s] - H["thigh_" + s]).length, (H["foot_" + s] - H["calf_" + s]).length)
        self.arm = {}
        for S, s, _ in SIDES:
            self.arm[S] = ((H["lowerarm_" + s] - H["upperarm_" + s]).length, (H["hand_" + s] - H["lowerarm_" + s]).length)
        self.musket_butt = Vector(rig.get("musket_butt", (H["hand_r"].x - 0.11, H["hand_r"].y + 0.02, H["hand_r"].z - 0.30)))
        log("rig: %d bones, pelvis z %.3f, leg %.3f+%.3f, arm %.3f+%.3f, ankle z %.3f" % (
            len(self.order), H["pelvis"].z, self.leg["L"][0], self.leg["L"][1], self.arm["L"][0], self.arm["L"][1], H["foot_l"].z))


# ------------------------------------------------------------------ pose parameters -> bone rotations
def local_rotations(P):
    """Anatomical params -> {bone: R} in parent-carried world-aligned axes."""
    g = P.get
    R = {}
    R["pelvis"] = rz(g("pt", 0)) @ ry(g("pl", 0)) @ rx(g("pp", 0))
    sp, sl, st = g("sp", 0), g("sl", 0), g("st", 0)
    for b, w in (("spine_01", 0.25), ("spine_02", 0.35), ("spine_03", 0.40)):
        R[b] = rz(st * w) @ ry(sl * w) @ rx(sp * w)
    R["neck_01"] = rz(g("nt", 0)) @ ry(g("nl", 0)) @ rx(g("np", 0))
    R["head"] = rz(g("ht", 0)) @ ry(g("hl", 0)) @ rx(g("hp", 0))
    for S, s, sg in SIDES:
        R["thigh_" + s] = rz(sg * g("tz" + S, 0)) @ ry(-sg * g("ta" + S, 0)) @ rx(-g("tf" + S, 0)) @ rz(sg * g("tt" + S, 0))
        R["calf_" + s] = rx(g("k" + S, 0))
        R["foot_" + s] = rz(sg * g("fo" + S, 0)) @ rx(-g("a" + S, 0))
        R["ball_" + s] = rx(-g("to" + S, 0))
        R["clavicle_" + s] = rz(-sg * g("cp" + S, 0)) @ ry(-sg * g("cs" + S, 0))
        R["upperarm_" + s] = rz(sg * g("ah" + S, 0)) @ ry(-sg * g("aa" + S, 0)) @ rx(-g("af" + S, 0)) @ rz(sg * g("at" + S, 0))
        R["lowerarm_" + s] = rx(-g("e" + S, 0)) @ rz(-sg * g("pr" + S, 0))
        R["hand_" + s] = ry(sg * g("wf" + S, 0)) @ rx(-g("wd" + S, 0))
        curl = g("f" + S, 12)
        for fi, fb in enumerate(("index", "middle", "ring", "pinky")):
            spread = (fi - 1.5) * g("fs" + S, 0)
            R["%s_01_%s" % (fb, s)] = ry(sg * curl * 0.9) @ rx(spread)
            R["%s_02_%s" % (fb, s)] = ry(sg * curl * 1.1)
            R["%s_03_%s" % (fb, s)] = ry(sg * curl * 0.8)
        th = g("th" + S, 8)
        R["thumb_01_" + s] = rx(-th * 0.4)
        R["thumb_02_" + s] = ry(sg * th * 0.6)
        R["thumb_03_" + s] = ry(sg * th * 0.8)
    return R


class Solver:
    def __init__(self, model):
        self.m = model

    def solve(self, P):
        """Returns ({bone: basis quaternion}, pelvis basis location)."""
        m = self.m
        g = P.get
        R = local_rotations(P)
        D, Pos = {}, {}
        forced = {}
        hip = body(g("hx", 0), g("hy", 0), g("hz", 0))
        for n in m.order:
            p = m.parent[n]
            if p is None:
                D[n] = Quaternion()
                Pos[n] = m.head[n].copy()
                continue
            Dp = D[p]
            if n == "pelvis":
                Pos[n] = m.head[n] + hip
            else:
                Pos[n] = Pos[p] + Dp @ (m.head[n] - m.head[p])
            D[n] = forced.pop(n) if n in forced else Dp @ R.get(n, Quaternion())
            # ---- leg IK once the thigh head is known
            for S, s, sg in SIDES:
                if n == "thigh_" + s and g("ik" + S, 0) > 0.001:
                    w = min(1.0, g("ik" + S, 0))
                    Dt, Dc, Df = self.leg_ik(S, s, sg, Pos[n], D, P)
                    D[n] = D[n].slerp(Dt, w) if w < 1 else Dt
                    fk_c = D[n] @ R["calf_" + s]
                    forced["calf_" + s] = fk_c.slerp(Dc, w) if w < 1 else Dc
                    if Df is not None:
                        forced["foot_" + s] = Df   # blended later (depends on calf)
                        forced["_fw_" + s] = w
            if n.startswith("foot_") and ("_fw_" + n[-1]) in forced:
                w = forced.pop("_fw_" + n[-1])
                fk = D[p] @ R[n]
                D[n] = fk.slerp(D[n], w)
            # ---- arm IK (and musket-driven right hand) once the upper arm head is known
            for S, s, sg in SIDES:
                if n == "upperarm_" + s:
                    tgt = self.hand_target(S, s, sg, D, Pos, P)
                    if tgt is not None:
                        wpos, w, hand_rot = tgt
                        Du, Dl = self.arm_ik(S, s, sg, Pos[n], wpos, D, P)
                        D[n] = D[n].slerp(Du, w) if w < 1 else Du
                        forced["lowerarm_" + s] = (D[n] @ R["lowerarm_" + s]).slerp(Dl, w)
                        if hand_rot is not None:
                            forced["hand_" + s] = hand_rot
            # ---- gaze stabilisation on the head
            if n == "head" and g("gz", 0) > 0.001:
                want = rz(g("gt", 0)) @ ry(g("gl", 0)) @ rx(g("gp", 0))
                D[n] = D[n].slerp(want, min(1.0, g("gz", 0)))
            if n == "neck_01" and g("gz", 0) > 0.001:
                want = rz(g("gt", 0) * 0.5) @ rx(g("gp", 0) * 0.5)
                D[n] = D[n].slerp(want.slerp(D[n], 0.5), min(1.0, g("gz", 0)) * 0.5)
        self.D, self.Pos = D, Pos
        basis = {}
        for n in m.order:
            p = m.parent[n]
            if p is None:
                continue
            Rl = D[p].inverted() @ D[n]
            basis[n] = m.q[n].inverted() @ Rl @ m.q[n]
        loc = m.q["pelvis"].inverted() @ hip
        return basis, loc

    # two-bone IK -------------------------------------------------------------------------------
    @staticmethod
    def _knee(Hp, T, L1, L2, pole):
        d = T - Hp
        dist = max(0.05, min(d.length, (L1 + L2) * 0.9995))
        u = d.normalized()
        a = (L1 * L1 - L2 * L2 + dist * dist) / (2 * dist)
        hgt = math.sqrt(max(0.0, L1 * L1 - a * a))
        w = pole - u * pole.dot(u)
        if w.length < 1e-6:
            w = Vector((0, -1, 0))
        w.normalize()
        K = Hp + u * a + w * hgt
        return K, Hp + u * dist

    def leg_ik(self, S, s, sg, hip_pos, D, P):
        m, g = self.m, P.get
        L1, L2 = m.leg[S]
        T = body(g("fx" + S, sg * 0.1), g("fy" + S, 0), g("fz" + S, m.head["foot_" + s].z))
        # knee points along the pelvis' forward, a little outward (plus optional swing "kp")
        pole = D["pelvis"] @ (rz(sg * g("kp" + S, 8)) @ Vector((0, -1, 0)))
        K, T2 = self._knee(hip_pos, T, L1, L2, pole)
        rest_t = m.head["calf_" + s] - m.head["thigh_" + s]
        rest_c = m.head["foot_" + s] - m.head["calf_" + s]
        rp = Vector((0, -1, 0))
        Dt = align(rest_t, rp, K - hip_pos, pole)
        Dc = align(rest_c, rp, T2 - K, pole)
        Df = None
        if g("fa" + S, 1) > 0:   # foot orientation is world-absolute under IK: pitch (toes up +), toe-out, roll
            Df = rz(sg * g("fo" + S, 0) + g("fyaw", 0)) @ ry(-sg * g("fr" + S, 0)) @ rx(-g("a" + S, 0))
        return Dt, Dc, Df

    def hand_target(self, S, s, sg, D, Pos, P):
        m, g = self.m, P.get
        if S == "R" and g("mk", 0) > 0.001:
            Dh, wrist = self.musket_hand(P)
            return wrist, min(1.0, g("mk", 0)), Dh
        w = g("ikh" + S, 0)
        if w <= 0.001:
            if S == "L" and g("mk", 0) > 0.001 and g("mlh", -1) >= 0 and g("mlw", 1.0) > 0.001:
                Dh, wrist = self.musket_hand(P)
                ax, belly = self.musket_dir(P)
                side = ax.cross(belly)                 # the musket's left when aiming belly-down
                grip = self.musket_butt_world(P) + ax * g("mlh", 0.7) + belly * 0.035
                d = (-side * 0.8 + belly * 0.2 + ax * 0.15).normalized()   # fingers wrap across the far side
                wr = grip - d * 0.075 + belly * 0.03
                d0 = (m.head["middle_01_l"] - m.head["hand_l"]).normalized()
                hand_rot = frame_quat(d, -belly) @ frame_quat(d0, Vector((-1, 0, 0))).inverted()
                return wr, min(1.0, g("mlw", 1.0) * g("mk", 0)), hand_rot
            return None
        T = body(g("hx" + S, sg * 0.25), g("hy" + S, 0.1), g("hz" + S, 1.0))
        hr = None
        if g("hra" + S, 0) > 0.5:
            d0 = (m.head["middle_01_" + s] - m.head["hand_" + s]).normalized()
            base = frame_quat(Vector((0, -1, 0)), Vector((0, 0, -1))) @ frame_quat(d0, Vector((-sg, 0, 0))).inverted()
            hr = rz(sg * g("hyw" + S, 0)) @ ry(-sg * g("hrl" + S, 0)) @ rx(g("hpt" + S, 0)) @ base
        return T, min(1.0, w), hr

    def arm_ik(self, S, s, sg, sh, T, D, P):
        m, g = self.m, P.get
        L1, L2 = m.arm[S]
        # elbow points back, down and out; "ep" swings it outward (+) about the shoulder->wrist axis
        base_pole = D["spine_03"] @ Vector((sg * 0.35, 1.0, -0.4))
        axis = (T - sh).normalized()
        if g("pw" + S, 0) > 0.5:
            base_pole = body(g("px" + S, 0), g("py" + S, 0), g("pz" + S, -1))
        pole = Quaternion(axis, math.radians(-sg * g("ep" + S, 0))) @ base_pole
        E, T2 = self._knee(sh, T, L1, L2, pole)
        rest_u = m.head["lowerarm_" + s] - m.head["upperarm_" + s]
        rest_l = m.head["hand_" + s] - m.head["lowerarm_" + s]
        rp = Vector((sg * 0.35, 1.0, -0.4))
        Du = align(rest_u, rp, E - sh, pole)
        Dl = align(rest_l, rp, T2 - E, pole)
        return Du, Dl

    # musket (welded to hand_r in build_characters._musket) --------------------------------------
    def musket_dir(self, P):
        """Axis (butt -> muzzle) and belly (trigger-guard side). pitch 90 = upright with the belly to the back,
        pitch 0 = pointing forward with the belly up (mroll 180 turns it belly-down for aiming)."""
        g = P.get
        th = math.radians(g("mpitch", 90))
        rot = rz(g("myaw", 0)) @ ry(g("mside", 0))
        a = rot @ Vector((0, -math.cos(th), math.sin(th)))
        b = rot @ Vector((0, math.sin(th), math.cos(th)))
        b = Quaternion(a, math.radians(g("mroll", 0))) @ b
        return a, b

    def musket_butt_world(self, P):
        g = P.get
        return body(g("mbx", -0.25), g("mby", 0.1), g("mbz", 0.6))

    def musket_hand(self, P):
        m = self.m
        a, belly = self.musket_dir(P)
        Dh = frame_quat(a, belly) @ frame_quat(Vector((0, 0, 1)), Vector((0, 1, 0))).inverted()
        butt = self.musket_butt_world(P)
        wrist = butt + Dh @ (m.head["hand_r"] - m.musket_butt)
        return Dh, wrist


# ------------------------------------------------------------------ clip containers
CLIPS = {}      # name -> (frames, fn(t_seconds) -> params, loop)


def clip(name, length, loop=False):
    def deco(fn):
        CLIPS[name] = (length, fn, loop)
        return fn
    return deco


def pchip(ts, vs, t, loop, length):
    n = len(ts)
    if n == 1:
        return vs[0]
    if loop:
        t = t % length
    if t <= ts[0]:
        return vs[0]
    if t >= ts[-1]:
        return vs[-1]
    i = 0
    while ts[i + 1] < t:
        i += 1

    def slope(k):
        if k <= 0 or k >= n - 1:
            if loop and (k == 0 or k == n - 1):
                # wrap: neighbours across the seam (last key duplicates the first)
                h0 = ts[-1] - ts[-2]
                h1 = ts[1] - ts[0]
                d0 = (vs[-1] - vs[-2]) / h0
                d1 = (vs[1] - vs[0]) / h1
            else:
                return 0.0
        else:
            h0 = ts[k] - ts[k - 1]
            h1 = ts[k + 1] - ts[k]
            d0 = (vs[k] - vs[k - 1]) / h0
            d1 = (vs[k + 1] - vs[k]) / h1
        if d0 * d1 <= 0:
            return 0.0
        w1 = 2 * h1 + h0
        w2 = h1 + 2 * h0
        return (w1 + w2) / (w1 / d0 + w2 / d1)
    h = ts[i + 1] - ts[i]
    u = (t - ts[i]) / h
    m0, m1 = slope(i) * h, slope(i + 1) * h
    h00 = 2 * u ** 3 - 3 * u ** 2 + 1
    h10 = u ** 3 - 2 * u ** 2 + u
    h01 = -2 * u ** 3 + 3 * u ** 2
    h11 = u ** 3 - u ** 2
    return h00 * vs[i] + h10 * m0 + h01 * vs[i + 1] + h11 * m1


def keyed(base, keys, loop=False, length=None):
    """keys: [(t, {param: value})], each key inherits the previous one. Returns fn(t) -> params."""
    acc = dict(base)
    full = []
    for t, d in keys:
        acc = dict(acc)
        acc.update(d)
        full.append((t, acc))
    if loop:
        full.append((length, dict(full[0][1])))
    names = set()
    for _, d in full:
        names |= set(d)
    ts = [t for t, _ in full]
    series = {nm: [d.get(nm, base.get(nm, 0.0)) for _, d in full] for nm in names}

    def fn(t):
        return {nm: pchip(ts, vs, t, loop, length or ts[-1]) for nm, vs in series.items()}
    return fn


def add(p, q, w=1.0):
    out = dict(p)
    for k, v in q.items():
        out[k] = out.get(k, 0.0) + v * w
    return out


def breath(t, amt=1.0, rate=0.27):
    b = math.sin(t * math.tau * rate)
    return {"sp": -0.8 * b * amt, "csL": 0.8 * b * amt, "csR": 0.8 * b * amt, "hp": 0.5 * b * amt}


# ------------------------------------------------------------------ poses
M = None   # RigModel, set in main()


def ankle_z():
    return M.head["foot_l"].z


GLOBAL_PARAMS = "hx hy hz pp pl pt sp sl st np nl nt hp hl ht gz gp gt gl fyaw mk mbx mby mbz mpitch myaw mside mroll mlh mlw".split()
SIDE_PARAMS = ("ik fx fy fz a to fo fr fa kp tf ta tt tz k cs cp af aa ah at e pr wf wd f fs th "
               "ikh hx hy hz hra hyw hrl hpt pw px py pz ep").split()


def defaults():
    """Every parameter at its neutral value, so a named pose fully overrides whatever a sequence held before."""
    d = {k: 0.0 for k in GLOBAL_PARAMS}
    for S, _, sg in SIDES:
        for k in SIDE_PARAMS:
            d[k + S] = 0.0
        d.update({"fa" + S: 1.0, "f" + S: 12.0, "th" + S: 8.0, "fz" + S: ankle_z(), "kp" + S: 8.0, "fx" + S: sg * 0.11, "pz" + S: -1.0})
    d.update({"mpitch": 90.0, "mlh": -1.0, "mlw": 1.0})
    return d


def complete(p):
    q = defaults()
    q.update(p)
    return q


def stand(**kw):
    """Relaxed standing: planted IK feet, soft knees, arms hanging with a slight bend, loose fingers."""
    p = {"ikL": 1, "ikR": 1, "fxL": 0.11, "fxR": -0.11, "fyL": 0.0, "fyR": -0.02, "fzL": ankle_z(), "fzR": ankle_z(),
         "hz": -0.012, "foL": 6, "foR": 6, "eL": 12, "eR": 12, "afL": 2, "afR": 2, "fL": 18, "fR": 18, "thL": 10, "thR": 10,
         "gz": 0.0, "prL": 8, "prR": 8}
    p.update(kw)
    return complete(p)



# ------------------------------------------------------------------ clips
def define_clips():
    """All clip definitions. Called once M (the reference RigModel) exists."""
    AZ = ankle_z()
    LF = (M.head["ball_l"] - M.head["foot_l"]).length * 0.95      # ankle -> ball, the heel-rise lever

    def K(t, **kw):
        return (t, kw)

    # ---------------------------------------------------------------- locomotion
    def gait(t, T, af, ab, duty, lift, hz0, bob, sway=0.02, twist=5.0, roll=3.0, arm=18.0, elbow=14.0,
             lean=3.0, width=0.095, run=False, lag=0.05, toe_off=24.0, strike=12.0, arm_abd=6.0, knee_out=6.0,
             gaze=4.0, arms=True, feet_y=0.0):
        ph = (t / T) % 1.0
        v_rel = (af + ab) / (duty * T)
        P = {"gz": 0.9, "gp": gaze, "hz": hz0}
        for S, s, sg in SIDES:
            f = (ph + (0.0 if S == "L" else 0.5)) % 1.0
            if f < duty:
                u = f / duty
                y = af - (af + ab) * u
                if u < 0.15:
                    pitch = strike * (1 - ss(u / 0.15))
                elif u < 0.55:
                    pitch = 0.0
                else:
                    pitch = -toe_off * ss((u - 0.55) / 0.45)
                heel = math.radians(max(0.0, -pitch))
                y += LF * (1 - math.cos(heel))
                z = AZ + LF * math.sin(heel)
                toe = max(0.0, -pitch)
            else:
                u = (f - duty) / (1 - duty)
                tsw = (1 - duty) * T
                th = math.radians(toe_off)
                y0 = -ab + LF * (1 - math.cos(th))
                z0 = AZ + LF * math.sin(th)
                m0 = -v_rel * tsw * (0.35 if not run else 0.2)
                m1 = -v_rel * tsw * 0.25
                if run:   # heel kicks up behind before the knee drives forward
                    uu = ss(max(0.0, (u - 0.12) / 0.88))
                    y = y0 + (af - y0) * uu
                    z = AZ + (z0 - AZ) * (1 - u) ** 2 + lift * math.sin(math.pi * min(1.0, u ** 0.75))
                else:
                    h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
                    y = h00 * y0 + h10 * m0 + h01 * af + h11 * m1
                    z = AZ + (z0 - AZ) * (1 - u) ** 2 + lift * math.sin(math.pi * u) ** 1.3 * (1.0 - 0.25 * u)
                pitch = pchip([0, 0.3, 0.7, 1.0], [-toe_off, -8 if not run else -30, 10, strike], u, False, 1.0)
                toe = toe_off * (1 - ss(u / 0.3))
            P["ik" + S] = 1
            P["fx" + S] = sg * width
            P["fy" + S] = y + feet_y
            P["fz" + S] = z
            P["a" + S] = pitch
            P["to" + S] = toe
            P["fo" + S] = 5
            P["kp" + S] = knee_out
        c2 = math.cos(2 * math.pi * ph)
        s2 = math.sin(2 * math.pi * ph)
        if run:
            P["hz"] = hz0 - bob * math.cos(4 * math.pi * (ph - duty / 2))
        else:
            P["hz"] = hz0 - bob * math.cos(4 * math.pi * ph)
        P["hx"] = sway * s2
        P["pt"] = -twist * c2
        P["pl"] = -roll * s2
        P["st"] = twist * 1.4 * math.cos(2 * math.pi * (ph - 0.03))
        P["sl"] = roll * 0.8 * s2
        P["sp"] = lean + (0.8 if not run else 2.0) * math.cos(4 * math.pi * ph)
        if arms:
            ca = math.cos(2 * math.pi * (ph - lag))
            for S, sg2 in (("L", -1.0), ("R", 1.0)):
                afv = sg2 * arm * ca
                P["af" + S] = afv + (arm * 0.2)
                P["e" + S] = elbow + max(0.0, afv) * (0.7 if not run else 0.9)
                P["aa" + S] = arm_abd
                P["at" + S] = -4
                P["pr" + S] = 12
                P["wf" + S] = 4 + 0.15 * afv
                P["cp" + S] = 0.12 * afv
                P["f" + S] = 22 if not run else 60
                P["th" + S] = 12 if not run else 40
        return P

    @clip("walk", 1.0, loop=True)
    def _walk(t):
        return gait(t, 1.0, 0.27, 0.40, 0.62, 0.075, -0.035, 0.016)

    @clip("walk_fast", 0.74, loop=True)
    def _walk_fast(t):
        return gait(t, 0.74, 0.33, 0.47, 0.57, 0.085, -0.075, 0.02, twist=7, roll=3.5, arm=26, elbow=20, lean=6, toe_off=32, strike=14)

    @clip("jog", 0.70, loop=True)
    def _jog(t):
        return gait(t, 0.70, 0.30, 0.42, 0.40, 0.16, -0.075, 0.03, sway=0.012, twist=8, roll=3, arm=30, elbow=70, lean=8,
                    run=True, toe_off=34, strike=8, gaze=2)

    @clip("run", 0.62, loop=True)
    def _run(t):
        return gait(t, 0.62, 0.38, 0.55, 0.31, 0.26, -0.085, 0.04, sway=0.01, twist=10, roll=3, arm=45, elbow=78, lean=13,
                    run=True, toe_off=40, strike=6, gaze=0, knee_out=4)

    @clip("walk_carry", 1.1, loop=True)
    def _walk_carry(t):
        P = gait(t, 1.1, 0.24, 0.36, 0.64, 0.065, -0.05, 0.018, twist=3, roll=4, lean=14, arms=False, gaze=-4)
        # both hands hold the bundle's straps at the chest, elbows in; the load makes the steps heavier
        ph = (t / 1.1) % 1
        for S, sg in (("L", 1), ("R", -1)):
            P.update({"af" + S: 28, "aa" + S: 4, "ah" + S: -30, "e" + S: 115, "pr" + S: -10, "f" + S: 80, "th" + S: 50,
                      "wf" + S: 10, "cs" + S: 6 + 2 * math.cos(4 * math.pi * ph)})
        return P

    @clip("carry_basket", 1.05, loop=True)
    def _carry_basket(t):
        P = gait(t, 1.05, 0.25, 0.37, 0.63, 0.07, -0.04, 0.016, lean=2, gaze=3)
        # basket on the left forearm, body counter-leans to the right, left arm still
        P.update({"afL": 18, "aaL": 12, "ahL": -8, "eL": 95, "prL": -60, "fL": 35, "wfL": -5, "csL": 5,
                  "sl": P["sl"] - 4, "pl": P["pl"] - 1})
        return P

    @clip("sneak", 0.9, loop=True)
    def _sneak(t):
        P = gait(t, 0.9, 0.36, 0.44, 0.64, 0.09, -0.33, 0.02, sway=0.035, twist=6, roll=2, arm=10, elbow=55, lean=30,
                 toe_off=26, strike=6, width=0.12, gaze=-18, knee_out=12)
        for S in "LR":
            P["af" + S] += 18
            P["aa" + S] = 14
            P["f" + S] = 35
        P["hy"] = -0.06
        return P

    @clip("guard_march", 0.72, loop=True)
    def _guard_march(t):
        P = gait(t, 0.72, 0.32, 0.45, 0.60, 0.08, -0.06, 0.018, twist=4, roll=2.5, arm=30, elbow=12, lean=0, toe_off=28, strike=16, gaze=0)
        # musket at shoulder arms on the right: the right hand rides with the hip bob, the left arm swings
        P.update(musket_shoulder())
        P["mbz"] += P["hz"] + 0.06
        P["mbx"] += P["hx"]
        return P

    # ---------------------------------------------------------------- standing idles
    @clip("idle", 6.0, loop=True)
    def _idle(t):
        w = math.sin(t * math.tau / 6.0)                 # slow weight shift from foot to foot
        P = stand()
        P["hx"] = 0.022 * w
        P["pl"] = -2.0 * w
        P["sl"] = 1.6 * w
        P["hz"] = -0.012 - 0.006 * abs(w)
        P["kL"] = 0
        P["gz"] = 0.6
        P["gt"] = 10 * math.sin(t * math.tau / 6.0 * 2 + 0.7) * ss(0.5 + 0.5 * math.sin(t * math.tau / 6.0 + 2.0))
        P["gp"] = 2
        return add(P, breath(t, 1.0, 0.25 + 0 * t))

    def musket_shoulder():
        return {"mk": 1, "mbx": -0.30, "mby": 0.06, "mbz": 0.64, "mpitch": 97, "mside": 6, "mroll": -10, "mlh": -1,
                "fR": 75, "thR": 45}

    @clip("idle_alert", 2.4, loop=True)
    def _idle_alert(t):
        base = stand(hz=-0.07, fxL=0.15, fxR=-0.15, fyL=0.08, fyR=-0.08, sp=9, afL=16, afR=16, eL=48, eR=48, aaL=10, aaR=10,
                     fL=40, fR=40, gz=0.85, gp=-2, foR=18)
        f = keyed(base, [K(0, gt=0), K(0.5, gt=28, st=10, pt=4), K(1.1, gt=28, st=10), K(1.6, gt=-30, st=-10, pt=-4), K(2.1, gt=-30, st=-10)],
                  loop=True, length=2.4)
        return lambda tt: add(f(tt), breath(tt, 1.6, 0.5))

    CLIPS["idle_alert"] = (2.4, _idle_alert(0), True)

    @clip("guard_sentry", 5.0, loop=True)
    def _guard_sentry(t):
        P = stand(fxL=0.12, fxR=-0.12, foL=14, foR=14, hz=-0.01, eL=6, afL=0, fL=30)
        P.update(musket_shoulder())
        sway = math.sin(t * math.tau / 5.0)
        P["hx"] = 0.012 * sway
        P["pl"] = -1.2 * sway
        P["sl"] = 1.0 * sway
        P["ht"] = 6 * math.sin(t * math.tau / 5.0 * 2 + 1.0) * ss((math.sin(t * math.tau / 5.0) + 1) / 2)
        P["mbx"] += P["hx"]
        return add(P, breath(t))

    @clip("guard_alert_look", 3.2, loop=True)
    def _guard_alert_look(t):
        # musket at the port (diagonal across the chest), scanning left and right with the torso and head
        base = stand(hz=-0.06, fxL=0.15, fxR=-0.15, fyL=0.10, fyR=-0.08, sp=6, foR=16,
                     mk=1, mbx=-0.16, mby=0.12, mbz=0.84, mpitch=75, myaw=0, mside=35, mroll=-40, mlh=0.50, mlw=1.0,
                     fL=70, fR=75, thL=40, thR=45, gz=0.7, gp=-2)
        f = keyed(base, [K(0, gt=0, st=0), K(0.6, gt=38, st=16, pt=6, myaw=10), K(1.3, gt=40, st=16, pt=6, myaw=10),
                         K(2.0, gt=-36, st=-14, pt=-6, myaw=-10), K(2.7, gt=-38, st=-14, pt=-6, myaw=-10)], loop=True, length=3.2)
        return f(t)

    # ---------------------------------------------------------------- crouch / hide
    def crouch(**kw):
        p = stand(hz=-0.40, hy=-0.07, fxL=0.16, fxR=-0.16, fyL=0.10, fyR=-0.14, fzR=AZ + 0.035, aR=-24, toR=24, foL=10, foR=14,
                  sp=30, afL=26, afR=22, eL=60, eR=55, aaL=14, aaR=14, fL=30, fR=30, gz=0.85, gp=-6, kpL=14, kpR=10)
        p.update(kw)
        return p

    @clip("crouch_idle", 3.0, loop=True)
    def _crouch_idle(t):
        s1 = math.sin(t * math.tau / 3.0)
        P = crouch()
        P["hx"] = 0.015 * s1
        P["gt"] = 14 * math.sin(t * math.tau / 3.0 + 0.6)
        P["st"] = 4 * math.sin(t * math.tau / 3.0 + 0.3)
        return add(P, breath(t, 1.3, 0.33))

    @clip("crouch_hide", 3.6, loop=True)
    def _crouch_hide(t):
        # huddled low with the back to a wall: knees up, arms hugging them, head sunk, peeking to either side
        base = stand(hz=-0.58, hy=-0.05, fxL=0.14, fxR=-0.14, fyL=0.20, fyR=0.16, aL=-10, aR=-12, toL=10, toR=12, fzL=AZ + 0.02, fzR=AZ + 0.025,
                     sp=26, pp=-8, afL=62, afR=60, ahL=-30, ahR=-30, eL=62, eR=58, prL=40, prR=40, fL=55, fR=55, csL=10, csR=10, cpL=10, cpR=10,
                     gz=0.6, gp=10, kpL=4, kpR=4)
        f = keyed(base, [K(0, gt=0), K(0.8, gt=34, sl=4, gp=4), K(1.6, gt=34, sl=4, gp=4), K(2.2, gt=-10, sl=0, gp=10),
                         K(2.8, gt=-26, sl=-3, gp=6)], loop=True, length=3.6)
        return add(f(t), breath(t, 1.6, 0.4))

    # ---------------------------------------------------------------- prone
    def prone(**kw):
        p = {"pp": 88, "hz": -0.79, "hy": 0.0, "sp": -24, "np": -18, "hp": -26,
             "tfL": 5, "tfR": 5, "taL": 8, "taR": 6, "ttL": 20, "ttR": 24, "kL": 3, "kR": 6, "aL": -40, "aR": -44,
             "ikhL": 1, "ikhR": 1, "hxL": 0.20, "hxR": -0.20, "hyL": 0.62, "hyR": 0.58, "hzL": 0.05, "hzR": 0.05,
             "hraL": 1, "hraR": 1, "hywL": -25, "hywR": -25,
             "pwL": 1, "pwR": 1, "pxL": 0.5, "pxR": -0.5, "pyL": -0.4, "pyR": -0.4, "pzL": -1, "pzR": -1,
             "fL": 20, "fR": 20, "csL": 10, "csR": 10}
        p.update(kw)
        return complete(p)

    @clip("prone_idle", 4.0, loop=True)
    def _prone_idle(t):
        s1 = math.sin(t * math.tau / 4.0)
        P = prone()
        P["ht"] = 10 * math.sin(t * math.tau / 4.0 + 0.5)
        P["sp"] += 1.5 * math.sin(t * math.tau * 0.3)
        P["hx"] = 0.01 * s1
        return P

    @clip("prone_crawl", 1.3, loop=True)
    def _prone_crawl(t):
        T = 1.3
        ph = (t / T) % 1
        P = prone(sp=-12, np=-12, hp=-20)
        for S, sg in (("L", 1.0), ("R", -1.0)):
            f = (ph + (0.0 if S == "L" else 0.5)) % 1
            duty = 0.6
            if f < duty:                      # elbow/hand planted, pulling the body forward (slides back in place)
                u = f / duty
                y = 0.78 - 0.55 * u
                z = 0.05
            else:
                u = (f - duty) / (1 - duty)
                y = 0.23 + 0.55 * ss(u)
                z = 0.05 + 0.10 * math.sin(math.pi * u)
            P["hy" + S] = y
            P["hz" + S] = z
            P["hx" + S] = sg * 0.24
            # same-side knee draws up along the ground while that arm reaches, then pushes
            k = 0.5 + 0.5 * math.cos(2 * math.pi * (f - 0.85))
            P["ta" + S] = 10 + 40 * k
            P["tt" + S] = 25 + 60 * k
            P["tf" + S] = 5 + 10 * k
            P["k" + S] = 4 + 75 * k
            P["a" + S] = -40 + 10 * k
        P["pl"] = 5 * math.sin(2 * math.pi * ph)
        P["sl"] = -8 * math.cos(2 * math.pi * ph)
        P["st"] = 4 * math.sin(2 * math.pi * ph)
        P["hx"] = 0.03 * math.cos(2 * math.pi * ph)
        P["ht"] = 4 * math.cos(2 * math.pi * ph)
        return P

    @clip("prone_crawl_side", 1.6, loop=True)
    def _prone_crawl_side(t):
        # sideways shuffle to the character's left: hands and knees step apart then together
        T = 1.6
        ph = (t / T) % 1
        P = prone()
        a = math.sin(2 * math.pi * ph)
        b = math.sin(2 * math.pi * (ph - 0.25))
        P["hxL"] = 0.24 + 0.10 * max(0.0, a) - 0.06 * max(0.0, -a)
        P["hxR"] = -0.20 + 0.06 * max(0.0, a) - 0.08 * max(0.0, -a)
        P["hzL"] = 0.05 + 0.06 * max(0.0, math.sin(2 * math.pi * (ph + 0.1)))
        P["hzR"] = 0.05 + 0.06 * max(0.0, math.sin(2 * math.pi * (ph + 0.6)))
        P["taL"] = 12 + 14 * max(0.0, b)
        P["taR"] = 6 - 4 * max(0.0, b) + 10 * max(0.0, -b)
        P["kL"] = 12 + 30 * max(0.0, b)
        P["hx"] = 0.05 * a
        P["pl"] = 3 * a
        P["sl"] = -6 * a
        return P

    def all_fours(**kw):
        p = {"pp": 72, "hz": -0.40, "hy": -0.05, "sp": -12, "np": -10, "hp": -34,
             "ikL": 1, "ikR": 1, "fxL": 0.12, "fxR": -0.12, "fyL": -0.52, "fyR": -0.52, "fzL": 0.05, "fzR": 0.05, "aL": -155, "aR": -155,
             "faL": 1, "faR": 1, "kpL": 0, "kpR": 0,
             "ikhL": 1, "ikhR": 1, "hxL": 0.20, "hxR": -0.20, "hyL": 0.50, "hyR": 0.50, "hzL": 0.06, "hzR": 0.06, "hraL": 1, "hraR": 1,
             "hywL": -12, "hywR": -12, "epL": 20, "epR": 20, "fL": 10, "fR": 10}
        p.update(kw)
        return complete(p)

    @clip("crouch_crawl", 1.2, loop=True)
    def _crouch_crawl(t):
        # hands and knees under a low obstacle: diagonal pairs move together
        T = 1.2
        ph = (t / T) % 1
        P = all_fours()
        for S, sg, off_h, off_k in (("L", 1.0, 0.0, 0.5), ("R", -1.0, 0.5, 0.0)):
            fh = (ph + off_h) % 1
            fk = (ph + off_k) % 1
            duty = 0.7
            if fh < duty:
                u = fh / duty
                P["hy" + S] = 0.62 - 0.26 * u
                P["hz" + S] = 0.06
            else:
                u = (fh - duty) / (1 - duty)
                P["hy" + S] = 0.36 + 0.26 * ss(u)
                P["hz" + S] = 0.06 + 0.07 * math.sin(math.pi * u)
            if fk < duty:
                u = fk / duty
                P["fy" + S] = -0.40 - 0.26 * u
                P["fz" + S] = 0.06
            else:
                u = (fk - duty) / (1 - duty)
                P["fy" + S] = -0.66 + 0.26 * ss(u)
                P["fz" + S] = 0.06 + 0.06 * math.sin(math.pi * u)
        P["hx"] = 0.02 * math.sin(2 * math.pi * ph)
        P["pl"] = 3 * math.sin(2 * math.pi * ph)
        P["st"] = -4 * math.sin(2 * math.pi * ph)
        P["hz"] += 0.01 * math.cos(4 * math.pi * ph)
        return P

    # ---------------------------------------------------------------- transitions
    STAND = stand()
    CROUCH = crouch()
    PRONE = prone()

    def seq(name, length, keys, base=None):
        b = complete(base or {})
        CLIPS[name] = (length, keyed(b, keys), False)

    seq("stand_to_crouch", 0.5, [K(0, **STAND), K(0.18, hz=-0.20, sp=12, hy=-0.03), K(0.5, **CROUCH)])
    seq("crouch_to_stand", 0.6, [K(0, **CROUCH), K(0.3, hz=-0.12, sp=10, hy=-0.02, eL=30, eR=30, afL=10, afR=10), K(0.6, **STAND)])
    kneel_hands = dict(CROUCH, hz=-0.46, hy=0.05, sp=55, gp=-30, ikhL=1, ikhR=1, hxL=0.2, hxR=-0.2, hyL=0.45, hyR=0.45, hzL=0.06, hzR=0.06,
                       hraL=1, hraR=1, hywL=-15, hywR=-15)
    seq("crouch_to_prone", 1.0, [K(0, **CROUCH), K(0.35, **kneel_hands),
                                 K(0.65, pp=45, hz=-0.62, hy=0.05, sp=-5, ikL=0.5, ikR=0.5, fyL=-0.45, fyR=-0.5, fzL=0.05, fzR=0.05, aL=-155, aR=-155,
                                   tfL=10, tfR=20, kL=40, kR=60,
                                   hyL=0.55, hyR=0.55, gz=0.3),
                                 K(1.0, **dict(PRONE, ikL=0, ikR=0, gz=0))])
    seq("prone_to_crouch", 1.1, [K(0, **dict(PRONE, ikL=0, ikR=0, gz=0)),
                                 K(0.35, pp=60, hz=-0.66, sp=-8, hyL=0.45, hyR=0.45, hzL=0.05, hzR=0.05, tfL=30, tfR=10, kL=70, kR=40),
                                 K(0.7, **dict(kneel_hands, ikL=1, ikR=1)), K(1.1, **dict(CROUCH, ikhL=0, ikhR=0))])

    # ---------------------------------------------------------------- climb a 1 m ledge in front
    top = 1.0 + AZ
    seq("climb_short", 1.8, [
        K(0.0, **STAND),
        K(0.25, hz=-0.16, sp=10, ikhL=1, ikhR=1, hxL=0.24, hxR=-0.24, hyL=0.36, hyR=0.36, hzL=1.12, hzR=1.12, hraL=1, hraR=1, gp=10, gz=0.8),
        K(0.45, hz=-0.20, hyL=0.46, hyR=0.46, hzL=1.04, hzR=1.04),
        K(0.75, hz=0.30, hy=0.18, sp=35, fyL=0.05, fzL=0.40, fyR=0.10, fzR=0.30, aL=-20, aR=-10, ikL=1, ikR=1),
        K(1.05, hz=0.52, hy=0.34, sp=45, fyR=0.50, fzR=top, aR=0, fyL=0.10, fzL=0.62, aL=-40, gp=20),
        K(1.40, hz=0.86, hy=0.52, sp=22, fyL=0.62, fzL=top, aL=0, fyR=0.58, ikhL=0.3, ikhR=0.3),
        K(1.80, **dict(STAND, hz=1.0, hy=0.62, fyL=0.62, fyR=0.60, fzL=top, fzR=top, ikhL=0, ikhR=0, gz=0)),
    ])

    # ---------------------------------------------------------------- lying poses, falls, deaths
    def lie_back(**kw):
        p = complete({"pp": -88, "hz": -0.83, "hy": -0.50, "sp": 4, "np": 8, "hp": 4, "ht": 22,
                      "ikL": 0, "ikR": 0, "tfL": 4, "tfR": 10, "kL": 6, "kR": 16, "aL": -38, "aR": -34, "ttL": 26, "ttR": 30, "taL": 8, "taR": 6,
                      "aaL": 34, "aaR": 42, "eL": 24, "eR": 14, "afL": 4, "afR": 6, "prL": -30, "prR": -40, "fL": 30, "fR": 26})
        p.update(kw)
        return p

    def lie_front(**kw):
        p = complete({"pp": 88, "hz": -0.78, "hy": 0.55, "sp": -6, "np": -10, "hp": -8, "ht": 70, "hl": 6,
                      "ikL": 0, "ikR": 0, "tfL": 6, "tfR": 8, "kL": 4, "kR": 14, "aL": -60, "aR": -55, "ttL": 30, "ttR": 20, "taL": 8, "taR": 10,
                      "aaL": 95, "aaR": 18, "atL": 80, "eL": 70, "afL": 0, "afR": -8, "prL": 10, "prR": -30, "fL": 30, "fR": 26})
        p.update(kw)
        return p

    seq("knocked_down", 1.3, [
        K(0.0, **STAND),
        K(0.12, hz=-0.02, hy=-0.05, pp=-6, sp=-14, hp=-18, afL=40, afR=50, aaL=30, aaR=35, eL=40, eR=50, gz=0),
        K(0.35, hz=-0.28, hy=-0.22, pp=-24, sp=-10, fyL=0.18, fzL=AZ + 0.12, aL=20, kL=30, afL=60, afR=70, aaL=45, aaR=50),
        K(0.62, hz=-0.62, hy=-0.40, pp=-62, sp=6, ikL=0.6, ikR=0.6, tfL=40, tfR=25, kL=40, kR=30, aL=10, aR=0, np=18, hp=10),
        K(0.80, **lie_back(sp=8, np=14, hp=10, tfL=18, tfR=14, kL=20, kR=24, afL=20, afR=10)),
        K(1.3, **lie_back()),
    ])
    seq("knocked_down_forward", 1.2, [
        K(0.0, **STAND),
        K(0.12, hy=0.06, pp=8, sp=16, hp=14, afL=-20, afR=-24, gz=0),
        K(0.35, hz=-0.25, hy=0.22, pp=28, sp=10, fyR=-0.25, fzR=AZ + 0.15, aR=-30, kR=50, afL=40, afR=45, eL=20, eR=20),
        K(0.60, hz=-0.62, hy=0.45, pp=66, sp=-10, ikL=0, ikR=0, tfL=30, tfR=10, kL=50, kR=40, afL=85, afR=85, eL=40, eR=40, np=-20, hp=-20),
        K(0.78, **lie_front(afL=70, afR=60, eL=80, eR=70, sp=-6)),
        K(1.2, **lie_front()),
    ])
    seq("get_up", 2.4, [
        K(0.0, **lie_back()),
        K(0.55, **complete({"pp": -32, "hz": -0.82, "hy": -0.50, "sp": 44, "np": 6, "hp": 0, "gz": 0.3, "gp": 10,
                            "ikL": 1, "ikR": 1, "fxL": 0.14, "fxR": -0.12, "fyL": -0.06, "fyR": -0.12, "fzL": AZ, "fzR": AZ, "aL": 10, "aR": 6,
                            "ikhR": 1, "hxR": -0.30, "hyR": -0.72, "hzR": 0.05, "hraR": 1, "hywR": 150,
                            "afL": 30, "eL": 60, "fL": 30})),
        K(1.05, pp=6, hz=-0.60, hy=-0.28, sp=40, hxR=-0.32, hyR=-0.36, aL=0, aR=0, afL=40, eL=70, gp=16),
        K(1.55, **dict(CROUCH, hy=-0.14, fyL=-0.06, fyR=-0.12, hz=-0.42)),
        K(2.4, **dict(STAND, hy=-0.06, fyL=-0.04, fyR=-0.10)),
    ])
    seq("get_up_prone", 1.9, [
        K(0.0, **lie_front()),
        K(0.35, **dict(PRONE, hy=0.4, ikL=0, ikR=0, hyL=0.72, hyR=0.70, sp=-10, ht=0, hl=0)),
        K(0.75, pp=45, hz=-0.55, hy=0.35, sp=-4, tfL=45, tfR=20, kL=100, kR=90, hyL=0.72, hyR=0.70, hp=-20, np=-10),
        K(1.15, **dict(kneel_hands, hy=0.30, hyL=0.72, hyR=0.70, fyL=0.20, fyR=-0.20)),
        K(1.55, hz=-0.22, hy=0.12, sp=20, ikhL=0, ikhR=0, afL=20, afR=20, eL=40, eR=40, fyL=0.14, fyR=-0.02, gz=0.5, gp=0),
        K(1.9, **dict(STAND, hy=0.08, fyL=0.08, fyR=0.02)),
    ])
    seq("death_fall", 1.7, [
        K(0.0, **STAND),
        K(0.15, pp=-4, sp=-10, hp=-16, afL=24, afR=20, aaL=20, aaR=22, eL=50, eR=60, gz=0),
        K(0.45, hz=-0.22, hy=-0.10, pp=-10, sp=6, hp=10, kL=40, kR=30, afL=10, afR=16, eL=30, eR=40, aaL=18, aaR=20),
        K(0.80, hz=-0.60, hy=-0.34, pp=-48, sp=14, ikL=0.8, ikR=0.8, tfL=60, tfR=50, kL=90, kR=80, aL=0, aR=0, np=20, hp=16, afL=40, afR=50),
        K(1.05, **lie_back(sp=10, np=16, hp=12, tfL=26, kL=40, afL=30, afR=20)),
        K(1.25, **lie_back(sp=2, np=4, tfL=16, kL=26, ht=34)),
        K(1.7, **lie_back(tfL=14, kL=24, ht=34)),
    ])
    seq("death_fall_forward", 1.6, [
        K(0.0, **STAND),
        K(0.18, sp=22, hp=14, afL=-14, afR=-8, eL=40, eR=50, prL=30, gz=0),
        K(0.50, hz=-0.34, hy=0.06, pp=10, sp=30, kL=60, kR=70, fyL=0.02, afL=10, afR=14, eL=30, eR=40),
        K(0.72, hz=-0.46, hy=0.10, pp=16, sp=34, ikL=0.6, ikR=0.6, fyL=-0.30, fyR=-0.34, fzL=0.08, fzR=0.08, aL=-60, aR=-60, tfL=10, tfR=10, kL=90, kR=90),
        K(1.05, **lie_front(afL=30, afR=10, eL=50)),
        K(1.6, **lie_front()),
    ])
    kneel = dict(STAND, hz=-0.41, hy=0.02, fyL=-0.42, fyR=-0.44, fzL=0.05, fzR=0.05, aL=-155, aR=-155, kpL=0, kpR=0, sp=8)
    seq("death_kneel", 2.6, [
        K(0.0, **STAND),
        K(0.25, sp=18, hp=16, afL=40, afR=36, ahL=-40, ahR=-40, eL=110, eR=110, prL=-40, prR=-40, gz=0),
        K(0.70, **dict(kneel, sp=24, hp=20, afL=36, afR=34, ahL=-40, ahR=-40, eL=110, eR=110, gz=0)),
        K(1.30, **dict(kneel, sp=10, sl=8, hp=6, hl=12, afL=10, afR=20, ahL=-10, ahR=-20, eL=60, eR=80, hz=-0.43, gz=0)),
        K(1.75, pp=40, pl=20, hz=-0.62, hy=0.25, sp=10, ikL=0.4, ikR=0.4, tfL=40, tfR=40, kL=110, kR=110, afL=40, afR=40, eL=40),
        K(2.1, **lie_front(pl=6, hy=0.45, kL=40, kR=60, tfL=20, tfR=30)),
        K(2.6, **lie_front(hy=0.45, kL=40, kR=60, tfL=20, tfR=30)),
    ])
    seq("death_musket", 1.8, [
        K(0.0, **STAND),
        K(0.08, hy=-0.06, pp=-10, sp=-22, hp=-20, afL=34, afR=30, aaL=30, aaR=34, eL=30, eR=20, gz=0, fyL=0.02),
        K(0.35, hy=-0.12, pp=-4, pt=18, sp=16, st=14, hp=12, afL=22, ahL=-55, eL=115, prL=-30, afR=20, aaR=30, eR=40, fyR=-0.22, fzR=AZ + 0.08, kR=30),
        K(0.75, hz=-0.36, hy=-0.14, pt=30, pp=-6, sp=22, st=18, kL=60, kR=70, fyR=-0.10, fzR=AZ, afL=22, eL=115, afR=10, aaR=20, eR=30),
        K(1.10, hz=-0.64, hy=-0.30, pt=40, pp=-40, pl=-20, sp=20, ikL=0.7, ikR=0.7, tfL=60, tfR=50, kL=90, kR=100, aL=0, aR=0, np=20),
        K(1.35, **lie_back(pt=35, pl=-14, sp=8, np=10, afL=40, ahL=-40, eL=110, prL=-10, tfL=30, kL=40)),
        K(1.8, **lie_back(pt=35, pl=-14, afL=40, ahL=-40, eL=110, prL=-10, tfL=24, kL=34)),
    ])
    seq("fall_land_roll", 1.5, [
        K(0.0, **dict(STAND, hz=0.9, ikL=0, ikR=0, tfL=20, tfR=10, kL=40, kR=30, aL=-20, aR=-20, afL=70, afR=70, aaL=40, aaR=40, eL=30, eR=30, sp=-5, gz=0.3)),
        K(0.30, **dict(STAND, hz=0.15, ikL=0, ikR=0, tfL=16, tfR=12, kL=20, kR=16, aL=-10, aR=-10, afL=40, afR=40, aaL=35, aaR=35, eL=20, eR=20, sp=5)),
        K(0.42, **dict(CROUCH, hz=-0.45, hy=0.0, sp=40, ikL=1, ikR=1, afL=40, afR=40, eL=40, eR=40)),
        K(0.62, pp=70, hz=-0.62, hy=0.35, sp=60, np=40, hp=20, ikL=0.3, ikR=0.3, tfL=80, tfR=80, kL=120, kR=120, afL=60, afR=60, eL=60, eR=60),
        K(0.85, pp=200, hz=-0.60, hy=0.75, sp=60, np=40, ikL=0, ikR=0, tfL=110, tfR=110, kL=130, kR=130, aL=-20, aR=-20, afL=40, afR=40, eL=90, eR=90, gz=0),
        K(1.08, pp=330, hz=-0.45, hy=1.05, sp=40, np=20, hp=10, tfL=100, tfR=90, kL=120, kR=120, afL=40, afR=40),
        K(1.5, **dict(CROUCH, pp=360, hy=1.2, fyL=1.3, fyR=1.06, ikL=1, ikR=1)),
    ])
    seq("stumble", 1.1, [
        K(0.0, **STAND),
        K(0.15, fyR=-0.18, fzR=AZ + 0.06, aR=-20, sp=6, gz=0.6),
        K(0.35, hy=0.12, pp=12, sp=18, hz=-0.08, fyR=0.20, fzR=AZ + 0.10, aR=-30, kR=40, afL=50, afR=-30, aaL=40, aaR=30, eL=30, eR=20, hp=-10),
        K(0.55, hy=0.28, pp=16, sp=20, hz=-0.20, fyR=0.45, fzR=AZ, aR=0, fyL=0.02, afL=60, afR=40, aaL=50, aaR=40),
        K(0.80, hy=0.40, pp=8, sp=10, hz=-0.12, fyL=0.62, fzL=AZ, aL=0, afL=30, afR=30, aaL=20, aaR=20),
        K(1.1, **dict(STAND, hy=0.46, fyL=0.52, fyR=0.44)),
    ])

    # ---------------------------------------------------------------- being hit
    seq("hit_react", 0.55, [K(0, **STAND), K(0.08, hy=-0.03, pp=-3, sp=-14, hp=-22, np=-6, afL=24, afR=28, eL=60, eR=70, aaL=10, aaR=12, hz=-0.03, gz=0),
                            K(0.22, hy=-0.07, sp=-6, hp=-6, fyL=-0.12, fzL=AZ, hz=-0.06), K(0.55, **dict(STAND, hy=-0.07, fyL=-0.10, fyR=-0.06))])
    seq("hit_react_back", 0.55, [K(0, **STAND), K(0.08, hy=0.04, pp=6, sp=18, hp=18, afL=-18, afR=-18, aaL=16, aaR=18, eL=30, eR=30, hz=-0.04, gz=0),
                                 K(0.24, hy=0.10, sp=8, fyR=0.16, fzR=AZ, hz=-0.06), K(0.55, **dict(STAND, hy=0.10, fyL=0.08, fyR=0.12))])
    seq("stagger", 1.3, [
        K(0, **STAND),
        K(0.10, hy=-0.05, sp=-16, hp=-20, afL=40, afR=46, aaL=30, aaR=40, eL=40, eR=50, gz=0),
        K(0.35, hy=-0.20, hz=-0.08, pl=6, sl=-8, fyR=-0.36, fzR=AZ + 0.06, aR=-10, sp=-8),
        K(0.55, hy=-0.32, hz=-0.10, pl=-6, sl=8, fyR=-0.40, fzR=AZ, aR=0, fyL=-0.20, fzL=AZ + 0.08),
        K(0.80, hy=-0.44, hz=-0.12, pl=4, sl=-4, fyL=-0.56, fzL=AZ, sp=10, hp=6, afL=30, afR=30),
        K(1.3, **dict(STAND, hy=-0.44, fyL=-0.50, fyR=-0.40, hz=-0.04, sp=6)),
    ])
    seq("shoved", 0.9, [K(0, **STAND), K(0.10, hy=-0.06, sp=-10, cpL=-10, cpR=-10, afL=30, afR=30, aaL=20, aaR=20, eL=40, eR=40, gz=0),
                        K(0.30, hy=-0.20, hz=-0.07, fyR=-0.34, fzR=AZ + 0.06, sp=-6),
                        K(0.50, hy=-0.28, fyR=-0.34, fzR=AZ, sp=4), K(0.9, **dict(STAND, hy=-0.28, fyL=-0.18, fyR=-0.34, sp=4))])
    guard_up = dict(STAND, hz=-0.07, fyL=0.12, fyR=-0.10, fxL=0.15, fxR=-0.15, foR=20, sp=8, pt=-10, st=-6,
                    afL=62, afR=70, ahL=-30, ahR=-26, eL=120, eR=110, prL=-40, prR=-30, fL=80, fR=80, thL=50, thR=50, csL=10, csR=10,
                    gz=0.8, gp=6, hp=10)
    seq("block", 0.9, [K(0, **STAND), K(0.18, **guard_up), K(0.30, **dict(guard_up, hy=-0.04, sp=4, hp=14)), K(0.9, **guard_up)])
    seq("grabbed", 1.5, [
        K(0, **STAND),
        K(0.10, hy=0.05, sp=12, csL=16, csR=16, cpL=10, cpR=10, gz=0.5),
        K(0.35, hy=0.04, pt=18, st=16, sp=8, afL=50, afR=40, ahL=-40, ahR=-30, eL=90, eR=100, fL=80, fR=80, fyL=0.10),
        K(0.70, pt=-20, st=-18, sp=6, afL=60, afR=55, eL=70, eR=80, fyR=-0.12),
        K(1.05, pt=14, st=12, sp=14, hp=10, afL=50, afR=60, eL=90, eR=90),
        K(1.5, pt=-6, st=-6, sp=10, afL=45, afR=45, eL=95, eR=95),
    ])

    # ---------------------------------------------------------------- player weapons
    fight = dict(STAND, hz=-0.06, fyL=0.14, fyR=-0.12, fxL=0.14, fxR=-0.15, foR=22, sp=6, pt=-8, st=-6,
                 afL=30, eL=60, aaL=12, fL=45, afR=20, eR=50, aaR=12, fR=85, thR=55, gz=0.8, gp=4)
    seq("attack_swing", 0.85, [
        K(0.0, **fight),
        K(0.25, pt=-22, st=-26, sp=0, sl=6, afR=110, aaR=40, ahR=10, eR=100, atR=30, wfR=-30, afL=40, eL=80, hz=-0.05, fyL=0.14),
        K(0.40, pt=10, st=18, sp=16, sl=-6, afR=60, aaR=20, ahR=-40, eR=20, atR=0, wfR=20, fyL=0.30, hz=-0.10, hy=0.06),
        K(0.52, pt=16, st=28, sp=22, afR=10, aaR=10, ahR=-60, eR=30, wfR=30, afL=10, eL=40),
        K(0.85, **dict(fight, hy=0.06, fyL=0.28)),
    ])
    seq("attack_thrust", 0.6, [
        K(0.0, **fight),
        K(0.18, pt=-16, st=-10, afR=30, eR=110, ahR=-10, wfR=-10, hy=-0.03),
        K(0.30, pt=12, st=10, sp=14, afR=85, eR=8, ahR=-10, hz=-0.10, hy=0.10, fyL=0.36, afL=10, eL=40),
        K(0.6, **dict(fight, hy=0.08, fyL=0.30)),
    ])
    sabre_guard = dict(fight, afR=45, eR=60, aaR=10, ahR=-12, prR=-20, wfR=-10, fR=90)
    seq("sabre_draw", 0.9, [
        K(0.0, **STAND),
        K(0.25, **dict(STAND, st=12, afR=35, ahR=-70, eR=80, aaR=10, prR=30, fR=40, afL=5, gz=0.6, gp=10)),
        K(0.40, **dict(STAND, st=14, afR=38, ahR=-74, eR=90, fR=90, thR=50, gz=0.6)),
        K(0.62, **dict(fight, afR=120, aaR=30, ahR=-10, eR=40, prR=0, fR=90, thR=50)),
        K(0.9, **sabre_guard),
    ])
    seq("sabre_slash", 0.7, [
        K(0.0, **sabre_guard),
        K(0.18, pt=-18, st=-22, afR=130, aaR=40, ahR=10, eR=70, atR=30, wfR=-20),
        K(0.32, pt=14, st=22, sp=18, afR=50, aaR=10, ahR=-60, eR=10, wfR=20, fyL=0.30, hy=0.06, hz=-0.10),
        K(0.42, pt=18, st=26, sp=20, afR=20, ahR=-70, eR=15),
        K(0.7, **dict(sabre_guard, hy=0.05, fyL=0.26)),
    ])
    seq("sabre_parry", 0.55, [
        K(0.0, **sabre_guard),
        K(0.16, afR=150, aaR=20, ahR=-30, eR=60, prR=-60, wfR=-30, st=-4, hy=-0.03, hp=-6),
        K(0.30, afR=150, aaR=20, ahR=-30, eR=64, hy=-0.05, sp=2),
        K(0.55, **sabre_guard),
    ])
    seq("knife_stab", 0.55, [
        K(0.0, **dict(fight, afR=15, eR=70, prR=40, afL=40, eL=70)),
        K(0.14, pt=-14, st=-10, afR=-10, eR=90, aaR=10, afL=60, eL=40, ahL=-10),
        K(0.26, pt=14, st=14, sp=16, afR=55, eR=35, ahR=-15, wfR=-20, afL=40, eL=90, hy=0.10, hz=-0.10, fyL=0.32),
        K(0.55, **dict(fight, hy=0.08, fyL=0.28, afR=15, eR=70)),
    ])
    aim_pistol = dict(STAND, fxL=0.14, fxR=-0.12, fyL=0.04, fyR=-0.04, foL=20, pt=-25, st=-15,
                      afR=88, ahR=18, eR=4, aaR=0, fR=80, thR=40, wfR=0, afL=0, eL=20, aaL=8,
                      gz=1.0, gt=0, gp=0, ht=28, hl=-8, csR=4)
    seq("pistol_draw", 0.8, [
        K(0.0, **STAND),
        K(0.25, **dict(STAND, afR=20, ahR=-50, eR=90, prR=20, fR=30, st=6, gz=0.6, gp=12)),
        K(0.38, **dict(STAND, afR=24, ahR=-54, eR=95, fR=85, st=6)),
        K(0.8, **aim_pistol),
    ])
    CLIPS["pistol_aim"] = (2.0, lambda t: add(aim_pistol, {"afR": 1.2 * math.sin(t * math.tau * 0.5), "ahR": 0.8 * math.sin(t * math.tau * 0.37),
                                                           "sp": 0.8 * math.sin(t * math.tau * 0.5)}), True)
    seq("pistol_fire", 0.6, [K(0.0, **aim_pistol), K(0.05, **dict(aim_pistol, afR=110, eR=24, wfR=20, sp=-3, hy=-0.02, hp=-6)),
                             K(0.22, **dict(aim_pistol, afR=100, eR=14, wfR=8, hy=-0.02)), K(0.6, **aim_pistol)])

    # ---------------------------------------------------------------- musket (guards)
    aim_musket = dict(STAND, hz=-0.04, fxL=0.10, fxR=-0.14, fyL=0.20, fyR=-0.12, foL=10, foR=40, pt=-28, st=-12, sp=4,
                      mk=1, mbx=-0.12, mby=0.12, mbz=1.40, mpitch=2, myaw=0, mroll=240, mlh=0.66, mlw=1.0,
                      fL=60, fR=75, thL=30, thR=40, gz=1.0, gp=4, gt=6, gl=-14, csR=6)
    CLIPS["musket_aim"] = (2.0, lambda t: add(aim_musket, {"mpitch": 0.6 * math.sin(t * math.tau * 0.5), "myaw": 0.5 * math.sin(t * math.tau * 0.31),
                                                          "sp": 0.6 * math.sin(t * math.tau * 0.5)}), True)
    seq("musket_fire", 0.9, [K(0.0, **aim_musket),
                             K(0.05, **dict(aim_musket, mpitch=12, mby=0.06, mbz=1.42, hy=-0.04, sp=-3, pt=-32, gp=-2)),
                             K(0.30, **dict(aim_musket, mpitch=6, mby=0.09, hy=-0.03)), K(0.9, **aim_musket)])
    port = dict(STAND, hz=-0.03, fxL=0.13, fxR=-0.13, foR=16, mk=1, mbx=-0.16, mby=0.12, mbz=0.84, mpitch=75, myaw=0, mside=35, mroll=-40,
                mlh=0.50, mlw=1.0, fL=70, fR=75, gz=0.8, gp=4)
    # the musket is welded 0.30 m above the butt, so ramming happens with the butt at the thigh and the rod hand
    # working along the upper barrel
    load = dict(port, mbx=-0.20, mby=0.16, mbz=0.50, mpitch=72, myaw=0, mside=18, mroll=-10, mlw=0.0, gp=24, sp=8)
    ram_hi = dict(load, ikhL=1, hxL=0.02, hyL=0.46, hzL=1.50, hp=-6, gp=-6)
    ram_lo = dict(ram_hi, hzL=1.30, hyL=0.42)
    seq("musket_reload", 4.2, [
        K(0.0, **aim_musket), K(0.45, **port), K(0.85, **load),
        K(1.15, **dict(load, ikhL=1, hxL=0.02, hyL=0.18, hzL=1.52, gp=10, hp=6)),      # bite the cartridge
        K(1.45, **dict(load, ikhL=1, hxL=0.02, hyL=0.18, hzL=1.52, gp=10, hp=6)),
        K(1.75, **dict(load, ikhL=1, hxL=0.0, hyL=0.46, hzL=1.52, gp=-10)),            # pour into the barrel
        K(2.05, **ram_hi), K(2.35, **ram_lo), K(2.6, **ram_hi), K(2.85, **ram_lo), K(3.1, **ram_hi),
        K(3.5, **port), K(4.2, **aim_musket),
    ])
    bay_guard = dict(STAND, hz=-0.10, fxL=0.13, fxR=-0.14, fyL=0.22, fyR=-0.18, foR=30, pt=-20, st=-8, sp=8,
                     mk=1, mbx=-0.20, mby=-0.02, mbz=0.92, mpitch=10, myaw=4, mroll=240, mlh=0.62, mlw=1.0, fL=70, fR=75, gz=1.0, gp=2)
    CLIPS["musket_ready"] = (2.4, lambda t: add(bay_guard, add(breath(t, 1.5, 0.42), {"hx": 0.012 * math.sin(t * math.tau / 2.4),
                                                                                    "mby": 0.02 * math.sin(t * math.tau / 2.4 + 0.5)})), True)
    seq("bayonet_thrust", 1.0, [
        K(0.0, **bay_guard),
        K(0.25, **dict(bay_guard, mby=-0.12, mbz=0.94, hy=-0.05, pt=-26)),
        K(0.45, **dict(bay_guard, mby=0.40, mbz=1.02, mpitch=6, hy=0.14, hz=-0.16, fyL=0.44, pt=-8, st=0, sp=16)),
        K(0.60, **dict(bay_guard, mby=0.42, mbz=1.02, mpitch=6, hy=0.14, hz=-0.16, fyL=0.44, pt=-8, sp=16)),
        K(1.0, **dict(bay_guard, hy=0.10, fyL=0.38)),
    ])
    shoulder = dict(STAND, **musket_shoulder())
    seq("musket_butt", 0.9, [
        K(0.0, **port),
        K(0.25, **dict(port, mbx=-0.28, mby=-0.10, mbz=0.95, mpitch=110, myaw=10, mside=20, pt=-24, st=-18, hy=-0.03)),
        K(0.42, **dict(port, mbx=-0.06, mby=0.38, mbz=1.25, mpitch=120, myaw=-20, mside=-10, pt=18, st=16, sp=14, hy=0.10, hz=-0.10, fyL=0.34)),
        K(0.55, **dict(port, mbx=0.0, mby=0.40, mbz=1.22, mpitch=125, myaw=-26, mside=-14, pt=22, st=18, sp=16, hy=0.12, hz=-0.10, fyL=0.34)),
        K(0.9, **dict(port, hy=0.10, fyL=0.30)),
    ])
    seq("guard_seize", 1.2, [
        K(0.0, **shoulder),
        K(0.25, **dict(shoulder, mbx=-0.32, mby=0.02, mbz=0.48, mpitch=70, mside=10, hy=0.04, sp=8, afL=60, eL=40, fL=20)),
        K(0.50, **dict(shoulder, mbx=-0.34, mby=0.10, mbz=0.46, mpitch=62, mside=10, hy=0.22, hz=-0.10, sp=20, fyL=0.42, pt=-10,
                       ikhL=1, hxL=0.05, hyL=0.72, hzL=1.28, fL=40, thL=20)),
        K(0.70, **dict(shoulder, mbx=-0.34, mby=0.10, mbz=0.46, mpitch=62, mside=10, hy=0.18, hz=-0.10, sp=14, fyL=0.42, pt=-4,
                       ikhL=1, hxL=0.04, hyL=0.56, hzL=1.24, fL=85, thL=50)),
        K(1.2, **dict(shoulder, mbx=-0.32, mby=0.08, mbz=0.50, mpitch=70, mside=10, hy=0.14, hz=-0.06, sp=8, fyL=0.34,
                      ikhL=1, hxL=0.03, hyL=0.48, hzL=1.22, fL=85, thL=50)),
    ])

    # ---------------------------------------------------------------- takedown (rear choke) and its victim
    seq("takedown", 2.0, [
        K(0.0, **fight),
        K(0.25, **dict(fight, hy=0.12, fyL=0.34, fyR=-0.02, sp=10, afR=70, afL=70, eR=90, eL=90)),
        K(0.45, **dict(fight, hy=0.18, fyL=0.34, fyR=-0.02, sp=6, pt=0, st=0, ikhR=1, hxR=0.10, hyR=0.46, hzR=1.40,
                       ikhL=1, hxL=0.16, hyL=0.40, hzL=1.48, fR=80, fL=70, csL=12, csR=12)),
        K(0.9, **dict(fight, hy=0.08, fyL=0.34, fyR=-0.10, sp=-6, pp=-6, ikhR=1, hxR=0.06, hyR=0.34, hzR=1.36,
                      ikhL=1, hxL=0.14, hyL=0.30, hzL=1.44, hp=-8, csL=14, csR=14, cpL=-8, cpR=-8)),
        K(1.3, **dict(fight, hy=0.04, fyL=0.34, fyR=-0.10, sp=-4, pp=-4, pt=8, ikhR=1, hxR=0.08, hyR=0.34, hzR=1.30,
                      ikhL=1, hxL=0.16, hyL=0.30, hzL=1.38)),
        K(1.7, **dict(CROUCH, hz=-0.32, hy=0.06, sp=24, ikhR=1, hxR=0.10, hyR=0.46, hzR=0.80, ikhL=1, hxL=0.18, hyL=0.44, hzL=0.86)),
        K(2.0, **dict(CROUCH, hy=0.06)),
    ])
    seq("takedown_victim", 2.0, [
        K(0.0, **STAND),
        K(0.35, **dict(STAND, hp=-24, np=-10, sp=-8, csL=14, csR=14, gz=0)),
        K(0.55, **dict(STAND, hp=-26, np=-12, sp=-10, hy=-0.05, ikhL=1, ikhR=1, hxL=0.06, hxR=-0.06, hyL=0.02, hyR=0.02, hzL=1.42, hzR=1.42, fL=80, fR=80)),
        K(0.95, **dict(STAND, hp=-20, np=-10, sp=-14, pp=-8, hy=-0.10, hz=-0.06, ikhL=1, ikhR=1, hxL=0.08, hxR=-0.04, hyL=0.04, hyR=0.00, hzL=1.36, hzR=1.40,
                       fyL=0.06, fzL=AZ + 0.05, aL=20)),
        K(1.35, **dict(STAND, hp=-6, np=0, sp=6, pp=-10, hy=-0.14, hz=-0.24, kL=40, afL=10, afR=16, eL=30, eR=40, ikhL=0.4, ikhR=0.4, hzL=1.1, hzR=1.1)),
        K(1.7, **dict(kneel, hy=-0.14, sp=-10, pp=-20, hp=10, afL=0, afR=10, eL=20, eR=20)),
        K(2.0, **lie_back(hy=-0.55)),
    ])

    # ---------------------------------------------------------------- townsfolk life
    talk = stand(fxL=0.12, fxR=-0.10, fyL=0.04, fyR=-0.04, foL=12, hz=-0.015, gz=0.4)
    seq("talk_gesture_a", 3.2, [
        K(0.0, **talk),
        K(0.5, afR=30, eR=80, ahR=-10, prR=-60, wfR=-10, fR=10, thR=0, st=6, hp=4, ht=-4, sl=2),
        K(0.9, afR=26, eR=70, ahR=10, prR=-80, fR=8, hp=-2),
        K(1.4, afR=34, eR=85, ahR=-5, prR=-70, afL=18, eL=60, prL=-50, fL=10, hp=6),
        K(2.0, afR=20, eR=60, prR=-40, afL=26, eL=75, prL=-80, ahL=12, st=-4, ht=6),
        K(2.6, afR=8, eR=30, prR=0, afL=10, eL=40, prL=-20, fR=18, fL=18, st=0, ht=0),
        K(3.2, **talk)], base=talk)
    CLIPS["talk_gesture_a"] = (3.2, CLIPS["talk_gesture_a"][1], True)
    seq("talk_gesture_b", 3.0, [
        K(0.0, **talk),
        K(0.45, afL=34, eL=90, ahL=-20, prL=-75, fL=8, wfL=-15, sl=-3, hl=-6, hp=6),
        K(0.8, afL=40, eL=70, ahL=10, prL=-85, hp=-4),                      # open-palm offer
        K(1.25, csL=10, csR=10, afR=20, eR=70, prR=-80, fR=6, hp=4, hl=8),   # shrug
        K(1.6, csL=0, csR=0, afL=20, eL=60, afR=22, eR=60),
        K(2.2, afR=40, eR=40, ahR=-20, prR=-10, fR=70, thR=50, st=8),        # pointing
        K(3.0, **talk)], base=talk)
    CLIPS["talk_gesture_b"] = (3.0, CLIPS["talk_gesture_b"][1], True)
    haggle = dict(talk, sp=8, gz=0.5, gp=6)
    seq("haggle", 3.4, [
        K(0.0, **haggle),
        K(0.35, afL=30, eL=100, prL=-60, fL=40, afR=34, eR=95, prR=-70, fR=10, hp=10),    # counting on the fingers
        K(0.7, fL=20, fR=40, hp=12),
        K(1.05, fL=40, fR=10),
        K(1.45, afR=40, eR=40, ahR=-30, prR=-10, wfR=20, fR=0, thR=0, st=10, ht=-10),     # a chop of the hand: no!
        K(1.65, afR=30, eR=55, ahR=-10),
        K(2.1, ht=-14, gt=0), K(2.35, ht=12), K(2.6, ht=-8),                              # head shake
        K(3.0, afL=10, eL=40, afR=10, eR=40, ht=0, st=0, csL=8, csR=8),
        K(3.4, **haggle)], base=haggle)
    CLIPS["haggle"] = (3.4, CLIPS["haggle"][1], True)
    seq("wave", 1.8, [
        K(0.0, **talk),
        K(0.35, afR=150, aaR=20, eR=40, prR=-80, wfR=0, fR=4, thR=0, sl=3),
        K(0.60, ahR=12, wdR=10), K(0.85, ahR=-14, wdR=-10), K(1.10, ahR=12, wdR=10), K(1.35, ahR=-10, wdR=-6),
        K(1.8, **talk)], base=talk)
    seq("bow", 2.6, [
        K(0.0, **STAND),
        K(0.45, **dict(STAND, fyR=-0.28, fxR=-0.08, foR=45, fyL=0.08, hy=-0.06, afR=40, ahR=-60, eR=100, prR=-70, fR=10,
                       afL=10, aaL=40, eL=10, prL=-60, fL=6, gz=0.3)),
        K(1.05, **dict(STAND, fyR=-0.28, fxR=-0.08, foR=45, fyL=0.08, hy=-0.14, hz=-0.08, pp=20, sp=30, np=10, hp=10,
                       afR=40, ahR=-70, eR=110, prR=-70, fR=10, afL=30, aaL=50, eL=6, prL=-80, fL=4, gz=0)),
        K(1.6, **dict(STAND, fyR=-0.28, fxR=-0.08, foR=45, fyL=0.08, hy=-0.14, hz=-0.08, pp=22, sp=32, np=12, hp=12,
                      afR=40, ahR=-70, eR=110, prR=-70, fR=10, afL=30, aaL=50, eL=6, prL=-80, fL=4, gz=0)),
        K(2.2, **dict(STAND, fyR=-0.20, fxR=-0.10, foR=30, hy=-0.06, afR=10, eR=40, gz=0.2)),
        K(2.6, **STAND)])
    sit = complete({"hz": -0.47, "hy": 0.08, "sp": 16, "np": 4, "hp": 4, "ikL": 1, "ikR": 1, "fxL": 0.14, "fxR": -0.12,
                    "fyL": 0.46, "fyR": 0.40, "fzL": AZ, "fzR": AZ, "aL": 4, "aR": 0, "foL": 12, "foR": 16, "kpL": 14, "kpR": 18,
                    "afL": 32, "afR": 28, "eL": 40, "eR": 46, "aaL": 6, "aaR": 6, "prL": 30, "prR": 30, "fL": 30, "fR": 30, "gz": 0.4, "gp": 4})
    CLIPS["sit_idle"] = (5.0, lambda t: add(sit, add(breath(t, 1.2), {"ht": 12 * math.sin(t * math.tau / 5.0), "st": 3 * math.sin(t * math.tau / 5.0 + 0.4),
                                                                     "sp": 2 * math.sin(t * math.tau / 2.5)})), True)
    def _sweep(t):
        ph = (t / 1.6) % 1
        c = math.cos(2 * math.pi * ph)          # +1 = broom to the character's right, -1 = to the left
        P = dict(talk, sp=20, hz=-0.07, fxL=0.16, fxR=-0.16, fyL=0.14, fyR=-0.10, foR=20, gz=0.6, gp=30, fL=85, fR=85, thL=50, thR=50)
        tw = -16 * c
        P.update({"st": tw, "pt": tw * 0.35, "hx": 0.02 * c})
        ang = math.radians(tw * 1.4 - 10)
        # upper hand (left) near the belly, lower hand (right) further down the handle
        for S, r, zz in (("L", 0.26, 0.98), ("R", 0.46, 0.74)):
            x = -math.sin(ang) * r - 0.05
            y = math.cos(ang) * r
            P.update({"ikh" + S: 1, "hx" + S: x, "hy" + S: y, "hz" + S: zz + 0.03 * math.sin(2 * math.pi * ph)})
        return P
    CLIPS["sweep"] = (1.6, _sweep, True)


# ------------------------------------------------------------------ baking & export
def bake(rig, solver, name, length, fn, loop):
    frames = max(2, int(round(length * FPS)))
    act = bpy.data.actions.new(name)
    rig.animation_data.action = act
    pbs = rig.pose.bones
    for pb in pbs:
        pb.rotation_mode = "QUATERNION"
    for f in range(0, frames + 1):          # a loop's last frame equals its first
        t = f / FPS
        P = fn(t % length if loop else min(t, length))
        basis, loc = solver.solve(P)
        for n, q in basis.items():
            pb = pbs[n]
            pb.rotation_quaternion = q
            pb.keyframe_insert("rotation_quaternion", frame=f + 1)
        pbs["pelvis"].location = loc
        pbs["pelvis"].keyframe_insert("location", frame=f + 1)
    act.use_fake_user = True
    rig.animation_data.action = None
    track = rig.animation_data.nla_tracks.new()
    track.name = name
    strip = track.strips.new(name, 1, act)
    strip.name = name
    return act


def export(rig):
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.context.scene.render.fps = FPS
    bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
                              export_animations=True, export_animation_mode="NLA_TRACKS", export_rest_position_armature=True,
                              export_skins=True, export_morph=False, export_def_bones=True, export_materials="NONE",
                              export_optimize_animation_size=True, export_force_sampling=True, export_frame_step=1)
    log("wrote", os.path.relpath(OUT, ROOT), "%.2f MB" % (os.path.getsize(OUT) / 1e6))


def main():
    global M
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    rebuild = "--rebuild" in argv
    only = [a for a in argv if not a.startswith("--")]
    rig = load_reference(rebuild)
    bpy.context.scene.render.fps = FPS
    M = RigModel(rig)
    define_clips()
    solver = Solver(M)
    rig.animation_data_create()
    for tr in list(rig.animation_data.nla_tracks):
        rig.animation_data.nla_tracks.remove(tr)
    for a in list(bpy.data.actions):
        bpy.data.actions.remove(a)
    names = [n for n in CLIPS if not only or n in only]
    for n in names:
        length, fn, loop = CLIPS[n]
        bake(rig, solver, n, length, fn, loop)
    log("baked %d clips: %s" % (len(names), " ".join(names)))
    for pb in rig.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    export(rig)


if __name__ == "__main__":
    main()
