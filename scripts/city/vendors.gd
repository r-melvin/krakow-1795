extends Node3D
## Street trade: the hawkers and pitch-sellers of the Rynek on a winter night (data/vendors.json). Instanced by
## dressing.gd, so the carts' collision boxes are baked into the navmesh with the rest of the dressing.
##
## Two kinds of seller, each a walker.gd body carrying a figure from Assets.character and a prop from
## assets/blender/build_vendor_props.py (on a bone, or standing beside them):
##  - stationary pitches (by the Cloth Hall, the church doors, the inn, the lanterns): idle, then calling their wares
##    (talk_gesture_a and a speech bubble: the original cry with its English gloss beneath). Now and then a passing
##    townsperson (npc.gd, taken with claim()) walks over; both haggle, and the buyer walks on carrying (role +
##    " carrier" makes npc.gd play carry_basket) for carry_secs. Two customers at once make a crowd: the seller and
##    the customers join group "crowd" (a stealth crowd query can find them there).
##  - roaming hawkers walk a short loop of 2-3 stops carrying their goods (walk_carry), calling every 12-20 s.
## Everyone packs up at their `closing` clock time and walks off through the nearest door; the chestnut roaster,
## the hot-beer seller and the fish barrow stay all night. The ballad seller runs when the watch is Alarmed and
## comes back once it has been calm for a while.
## The player: E on a seller opens a small dialogue (the mission runner's dialogue box): buy (1 coin; food restores
## 1 health; the ballad sheet sets Mission flag "ballad_sheet"), ask for gossip (a mission hint), leave.
##
## `-- --smoke`: forces one player purchase and one NPC sale and prints
##   [smoke] vendors n=<count> sales=<n> cries=<n> bought=<item>
## `-- --vendor-shot=/dir` (needs a window): close-ups of every seller, a haggle and the buy dialogue.

const WalkerScript := preload("res://scripts/npc/walker.gd")
const NpcScript := preload("res://scripts/npc/npc.gd")
const InteractableScript := preload("res://scripts/mission/interactable.gd")
const DialogueScript := preload("res://scripts/mission/dialogue.gd")
const FlickerLight := preload("res://scripts/city/flicker.gd")
const DATA := "res://data/vendors.json"
const BUBBLE_H := 2.2

enum St { OPEN, WALKING, CLOSING, LEAVING, GONE, FLEEING, HIDDEN, RETURNING, PUSH, TURN, LOWER, STEP_BACK, STEP_IN, LIFT }
const PUSH_SPEED := 0.75
const STEP_BACK := 0.35         ## metres the seller steps back from the shafts to sell
const MAX_TILT := 0.5           ## radians a barrow may tip up on its axle

## One seller.
class V:
	var d: Dictionary
	var id := ""
	var roaming := false
	var body                        ## CharacterBody3D with walker.gd
	var fig: Node3D
	var shape: CollisionShape3D
	var prop: Node3D
	var prop_body: StaticBody3D
	var lamp: OmniLight3D
	var fx: GPUParticles3D
	var ia: Area3D
	var state := 0                  ## St
	var home := Vector3.ZERO
	var yaw := 0.0
	var loop: Array = []            ## [[Vector3, yaw], ...]
	var loop_i := 0
	var loop_dir := 1
	var target := Vector3.ZERO
	var wait := 0.0                 ## roaming: seconds left at the current stop; closing: pause before leaving
	var cry_t := 0.0                ## seconds to the next cry
	var cry_anim := 0.0             ## seconds of talk_gesture_a left
	var sale_t := 0.0               ## seconds to the next attempt at drawing a customer
	var work_t := 0.0               ## grinder: seconds of sparks left
	var customers: Array = []       ## [{npc, slot, phase (0 going, 1 haggling), t, said}]
	var closing := -1.0             ## clock minutes, -1 = all night
	var calm := 0.0
	var gossip_i := 0
	var crowd := false
	# pushed barrows ("cart" in vendors.json): the prop is posed from the seller's hands every frame while moving
	var cart := false
	var axle := Vector3.ZERO        ## cart-local pivot (the axle the barrow tips on)
	var du := 0.6                   ## axle -> grip, along the shafts (horizontal, at rest)
	var dv := 0.3                   ## axle -> grip, up (at rest)
	var wheel_r := 0.28
	var wheels: Array = []
	var wheel_ang := 0.0
	var last_axle := Vector3.INF
	var lift := 1.0                 ## 0 resting on its legs .. 1 shafts in the hands
	var grip_f := 0.32              ## hand midpoint, metres in front of the body
	var grip_h := 0.9               ## hand midpoint height
	var prop_rot := PI
	var pitches: Array = []         ## [[Vector3 selling spot, yaw], ...]
	var pitch_i := 0
	var leaving := false
	var obstacle: NavigationObstacle3D
	var sk: Skeleton3D
	var sk_in_body := Transform3D.IDENTITY
	var hands := Vector2i(-1, -1)


var cfg: Dictionary = {}
var vendors: Array = []
var sales := 0
var cries := 0
var bought := "-"

var _rng := RandomNumberGenerator.new()
var _exits: Array = []
var _population: Node
var _excluded: Dictionary = {}
var _excluded_ready := false
var _cooldown: Dictionary = {}      ## npc -> ticks (s) until it may buy again
var _busy: Dictionary = {}          ## npc -> V
var _dlg: CanvasLayer
var _own_dlg: CanvasLayer
var _talking: V
var _dlg_actions: Array = []
var _check_t := 0.0
var _smoke := false
var _no_close := false
var _grey_tex: Texture2D

static var _smoke_done := false
static var _shots_done := false


func _ready() -> void:
	name = "Vendors"
	add_to_group("vendors")
	_rng.seed = 1800
	var f := FileAccess.open(DATA, FileAccess.READ)
	if f == null:
		push_warning("Vendors: cannot open %s" % DATA)
		return
	var parsed: Variant = JSON.parse_string(f.get_as_text())
	if not parsed is Dictionary:
		push_warning("Vendors: %s is not an object" % DATA)
		return
	cfg = parsed
	for e in cfg.get("exits", []):
		_exits.append(Vector3(float(e[0]), 0.0, float(e[1])))
	for vd in cfg.get("vendors", []):
		if vd is Dictionary:
			_spawn(vd)
	var args := OS.get_cmdline_user_args()
	_smoke = "--smoke" in args
	var shot_dir := ""
	for a in args:
		if a.begins_with("--vendor-shot="):
			shot_dir = a.trim_prefix("--vendor-shot=")
	if shot_dir != "" and not _shots_done:
		_shots_done = true
		_no_close = true
		_shots.call_deferred(shot_dir)
	elif _smoke and not _smoke_done:
		_smoke_done = true
		_smoke_run.call_deferred()


# ------------------------------------------------------------------ spawning
func _spawn(vd: Dictionary) -> void:
	var v := V.new()
	v.d = vd
	v.id = str(vd.get("id", "vendor"))
	v.roaming = str(vd.get("kind", "stationary")) == "roaming"
	if v.roaming:
		for p in vd.get("loop", []):
			v.loop.append([Vector3(float(p[0]), 0.0, float(p[1])), float(p[2]) if p.size() > 2 else 0.0])
		if v.loop.is_empty():
			return
		v.loop_i = _rng.randi() % v.loop.size()
		v.home = v.loop[v.loop_i][0]
		v.yaw = v.loop[v.loop_i][1]
		v.wait = _rng.randf_range(5.0, 25.0)
	else:
		var p: Array = vd.get("pos", [0, 0, 0])
		v.home = Vector3(float(p[0]), 0.0, float(p[2]))
		v.yaw = float(vd.get("facing", 0.0))
	var closing := str(vd.get("closing", ""))
	v.closing = GameState.parse_clock(closing) if closing != "" else -1.0

	var b := CharacterBody3D.new()
	b.set_script(WalkerScript)
	b.name = "Vendor_" + v.id
	b.position = v.home
	b.rotation.y = v.yaw
	v.shape = CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.22
	cap.height = 1.75
	v.shape.shape = cap
	v.shape.position.y = 0.875
	b.add_child(v.shape)
	var names := PackedStringArray()
	for n in vd.get("model", []):
		names.append(str(n))
	var model := NpcScript.first_existing(names)
	v.fig = Assets.character(model) if model != "" else null
	if v.fig == null:
		v.fig = Node3D.new()
		var mi := MeshInstance3D.new()
		var cm := CapsuleMesh.new()
		cm.radius = 0.3
		cm.height = 1.75
		mi.mesh = cm
		mi.position.y = 0.875
		v.fig.add_child(mi)
	b.add_child(v.fig)
	add_child(b)
	v.body = b
	b.setup_navigation(0.4, 1.75, 3.0)
	b.set_meta("vendor_id", v.id)
	Assets.play(v.fig, _rest_clip(v))
	if v.fig.has_meta("anim"):
		var ap: AnimationPlayer = v.fig.get_meta("anim")
		if ap.current_animation != "":
			ap.seek(_rng.randf() * ap.current_animation_length, true)
	_make_prop(v)
	_make_lamp(v)
	_make_fx(v)
	_make_sound(v)
	var ia := InteractableScript.new()
	ia.name = "Interact"
	ia.display_name = str(vd.get("name", "seller")).capitalize()
	ia.marker_height = 2.05
	ia.highlight_root = v.fig
	ia.prompt_func = _prompt.bind(v)
	ia.handler = _on_interact.bind(v)
	b.add_child(ia)
	v.ia = ia
	v.cry_t = _rng.randf_range(1.0, 9.0)
	v.sale_t = _rng.randf_range(8.0, 30.0)
	if v.cart:
		_start_cart(v)
	vendors.append(v)


func _rest_clip(v: V) -> String:
	return str(v.d.get("idle_clip", "idle"))


func _vec(a: Variant, def: Vector3 = Vector3.ZERO) -> Vector3:
	if a is Array and (a as Array).size() >= 3:
		return Vector3(float(a[0]), float(a[1]), float(a[2]))
	return def


## Props on a bone follow it (baskets, yokes, trays, packs); the rest stand beside the seller, in body space.
func _make_prop(v: V) -> void:
	var asset := str(v.d.get("prop", ""))
	if asset == "":
		return
	var p := Assets.instance(asset)
	if p == null:
		return
	v.prop = p
	var at := _vec(v.d.get("prop_at"))
	var rot := float(v.d.get("prop_rot", 0.0))
	if v.d.has("prop_bone"):
		_attach_to_bone.call_deferred(v, str(v.d["prop_bone"]), at, rot)
		return
	p.position = v.body.transform * at
	p.rotation.y = v.yaw + rot
	add_child(p)
	if v.d.has("cart"):
		_setup_cart(v, p, rot)
	if v.d.has("prop_col"):
		var size := _vec(v.d["prop_col"], Vector3.ONE)
		var sb := StaticBody3D.new()
		var cs := CollisionShape3D.new()
		var bx := BoxShape3D.new()
		bx.size = size
		cs.shape = bx
		cs.position.y = size.y * 0.5
		sb.add_child(cs)
		p.add_child(sb)
		v.prop_body = sb


## Waits for the rest clip to pose the skeleton, then parents the prop under a BoneAttachment3D so that, in the
## current pose, it sits `at` (body axes) from the bone's origin, upright and turned `rot` about Y.
func _attach_to_bone(v: V, bone: String, at: Vector3, rot: float) -> void:
	for i in 3:
		await get_tree().process_frame
	if not is_instance_valid(v.body):
		return
	var sks := v.fig.find_children("*", "Skeleton3D", true, false)
	var sk: Skeleton3D = sks[0] if sks.size() > 0 else null
	var bi := sk.find_bone(bone) if sk else -1
	if bi < 0:
		v.prop.position = v.body.transform * (at + Vector3(0, 1.2, 0))
		v.prop.rotation.y = v.yaw + rot
		add_child(v.prop)
		return
	var sk_in_body := Transform3D.IDENTITY
	var n: Node = sk
	while n != null and n != v.body:
		if n is Node3D:
			sk_in_body = (n as Node3D).transform * sk_in_body
		n = n.get_parent()
	var pose := sk_in_body * sk.get_bone_global_pose(bi)
	var want := Transform3D(Basis(Vector3.UP, rot), pose.origin + at)
	var ba := BoneAttachment3D.new()
	ba.bone_name = bone
	sk.add_child(ba)
	v.prop.transform = pose.affine_inverse() * want
	ba.add_child(v.prop)


func _make_lamp(v: V) -> void:
	var ld: Dictionary = v.d.get("lamp", {})
	if ld.is_empty():
		return
	var l: OmniLight3D = FlickerLight.new()
	l.amount = 0.16
	l.speed = 8.0
	var c: Array = ld.get("color", [1.0, 0.7, 0.4])
	l.light_color = Color(float(c[0]), float(c[1]), float(c[2]))
	l.light_energy = float(ld.get("energy", 1.5))
	l.omni_range = float(ld.get("range", 6.0))
	l.omni_attenuation = 1.5
	l.light_specular = 0.4
	l.light_volumetric_fog_energy = 0.7
	var at := _vec(ld.get("at"))
	if bool(ld.get("on_body", false)):
		l.position = at
		v.body.add_child(l)
	elif v.cart and v.prop:
		l.position = v.prop.transform.affine_inverse() * (v.body.transform * at)     # rides on the barrow
		v.prop.add_child(l)
	else:
		l.position = v.body.transform * at
		add_child(l)
	v.lamp = l


## Chestnut smoke, beer steam (soft billboard puffs) or grindstone sparks (bright streaks, only while working).
func _make_fx(v: V) -> void:
	var kind := str(v.d.get("fx", ""))
	if kind == "":
		return
	var ps := GPUParticles3D.new()
	var m := ParticleProcessMaterial.new()
	var quad := QuadMesh.new()
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	mat.vertex_color_use_as_albedo = true
	mat.albedo_texture = _soft_dot()
	var ramp := Gradient.new()
	if kind == "sparks":
		ps.amount = 56
		ps.lifetime = 0.5
		ps.emitting = false
		m.direction = Vector3(0, 0.6, -1)
		m.spread = 28.0
		m.initial_velocity_min = 2.0
		m.initial_velocity_max = 3.6
		m.gravity = Vector3(0, -9.8, 0)
		m.scale_min = 0.5
		m.scale_max = 1.0
		quad.size = Vector2(0.04, 0.04)
		mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		ramp.set_color(0, Color(1.0, 0.85, 0.4, 1.0))
		mat.albedo_color = Color(2.0, 1.4, 0.6)
		ramp.set_color(1, Color(1.0, 0.35, 0.05, 0.0))
	else:
		var steam := kind == "steam"
		ps.amount = 10 if steam else 22
		ps.lifetime = 2.2 if steam else 4.0
		m.direction = Vector3(0, 1, 0)
		m.spread = 12.0
		m.initial_velocity_min = 0.25
		m.initial_velocity_max = 0.5
		m.gravity = Vector3(0.05, 0.12, 0.0)
		m.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
		m.emission_sphere_radius = 0.08 if steam else 0.18
		var grow := Curve.new()
		grow.add_point(Vector2(0, 0.35))
		grow.add_point(Vector2(1, 1.0))
		var ct := CurveTexture.new()
		ct.curve = grow
		m.scale_curve = ct
		quad.size = Vector2(0.28, 0.28) if steam else Vector2(0.5, 0.5)
		var a := 0.22 if steam else 0.18
		var col := Color(0.92, 0.92, 0.95) if steam else Color(0.62, 0.6, 0.58)
		ramp.set_color(0, Color(col, 0.0))
		ramp.set_color(1, Color(col, 0.0))
		ramp.add_point(0.18, Color(col, a))
	var gt := GradientTexture1D.new()
	gt.gradient = ramp
	m.color_ramp = gt
	quad.material = mat
	ps.process_material = m
	ps.draw_pass_1 = quad
	ps.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	ps.position = v.body.transform * _vec(v.d.get("fx_at"))
	ps.rotation.y = v.yaw                # emission directions are in the seller's frame (forward -Z)
	ps.visibility_aabb = AABB(Vector3(-2, -1, -2), Vector3(4, 5, 4))
	if v.cart and v.prop:
		ps.transform = v.prop.transform.affine_inverse() * ps.transform      # rides on the barrow
		v.prop.add_child(ps)
	else:
		add_child(ps)
	v.fx = ps


func _soft_dot() -> Texture2D:
	if _grey_tex:
		return _grey_tex
	var g := Gradient.new()
	g.set_color(0, Color(1, 1, 1, 1))
	g.set_color(1, Color(1, 1, 1, 0))
	var t := GradientTexture2D.new()
	t.gradient = g
	t.fill = GradientTexture2D.FILL_RADIAL
	t.fill_from = Vector2(0.5, 0.5)
	t.fill_to = Vector2(1.0, 0.5)
	t.width = 32
	t.height = 32
	_grey_tex = t
	return t


# ------------------------------------------------------------------ pushed barrows
## vendors.json "cart": {axle: [y, z], grip: [y, z], wheel_r, arrive: [x, z]} in the model's Blender coordinates
## (y toward the handles, z up; see build_vendor_props.py). The barrow tips on its axle: resting on its legs when
## set down, shafts lifted into the seller's hands to push. Its wheels (child nodes wheel_*) turn with ground speed.
func _setup_cart(v: V, p: Node3D, rot: float) -> void:
	var cd: Dictionary = v.d["cart"]
	var ax: Array = cd.get("axle", [0.0, 0.3])
	var gr: Array = cd.get("grip", [0.65, 0.65])
	v.cart = true
	v.prop_rot = rot
	v.axle = Vector3(0.0, float(ax[1]), -float(ax[0]))
	v.du = float(gr[0]) - float(ax[0])
	v.dv = float(gr[1]) - float(ax[1])
	v.wheel_r = float(cd.get("wheel_r", 0.28))
	for w in p.find_children("wheel_*", "Node3D", true, false):
		v.wheels.append(w)
	v.obstacle = NavigationObstacle3D.new()
	v.obstacle.radius = 0.75
	v.obstacle.avoidance_enabled = false
	p.add_child(v.obstacle)
	for pt in v.d.get("pitches", []):
		v.pitches.append([Vector3(float(pt[0]), 0.0, float(pt[1])), float(pt[2]) if pt.size() > 2 else v.yaw])
	if v.pitches.is_empty():
		v.pitches.append([v.home, v.yaw])


## Where the seller stands at the shafts for the selling spot `pos` facing `yaw` (a step in front of it).
func _push_stand(pos: Vector3, yaw: float) -> Vector3:
	return pos + Vector3(-sin(yaw), 0.0, -cos(yaw)) * STEP_BACK


## Spawned at the "arrive" point with the barrow in hand, pushing to the first pitch.
func _start_cart(v: V) -> void:
	var cd: Dictionary = v.d["cart"]
	v.home = v.pitches[0][0]
	v.yaw = v.pitches[0][1]
	var stand := _push_stand(v.home, v.yaw)
	if cd.has("arrive"):
		var a: Array = cd["arrive"]
		var from := Vector3(float(a[0]), 0.0, float(a[1]))
		v.body.position = from
		var dir := stand - from
		v.body.rotation.y = atan2(-dir.x, -dir.z)
		v.state = St.PUSH
		v.target = stand
		v.lift = 1.0
	else:
		v.body.position = v.home
		v.lift = 0.0
		v.state = St.OPEN
	_cart_down(v, v.state == St.OPEN)
	_pose_cart(v, 0.0)


## Leave the pitch: back to the shafts, pick the barrow up, push it to `to` (a new pitch's stand, or a door).
func _move_on(v: V, to: Vector3) -> void:
	v.target = to
	v.state = St.STEP_IN


func _cart_down(v: V, down: bool) -> void:
	if v.prop_body:
		v.prop_body.process_mode = Node.PROCESS_MODE_INHERIT if down else Node.PROCESS_MODE_DISABLED
	if v.obstacle:
		v.obstacle.avoidance_enabled = down
	v.last_axle = Vector3.INF


## Cart states. Returns true when it handled the frame.
func _cart_tick(v: V, delta: float) -> bool:
	var b = v.body
	match v.state:
		St.PUSH:
			_read_hands(v)
			if b.walk_to(v.target, PUSH_SPEED, delta):
				if v.leaving:
					_set_hidden(v, true)
					v.state = St.GONE
					return true
				v.home = v.pitches[v.pitch_i][0]
				v.yaw = v.pitches[v.pitch_i][1]
				v.state = St.TURN
			else:
				Assets.play_move(v.fig, _push_clip(v), PUSH_SPEED)
			_pose_cart(v, delta)
			return true
		St.TURN:
			b.halt(delta)
			b.turn_toward_yaw(v.yaw, delta, 2.5)
			Assets.play(v.fig, _push_clip(v), 0.5)
			_pose_cart(v, delta)
			if absf(angle_difference(b.rotation.y, v.yaw)) < 0.06:
				v.state = St.LOWER
			return true
		St.LOWER, St.LIFT:
			b.halt(delta)
			Assets.play(v.fig, "idle")
			v.lift = clampf(v.lift + (delta / 0.7 if v.state == St.LIFT else -delta / 0.8), 0.0, 1.0)
			_pose_cart(v, delta)
			if v.state == St.LOWER and v.lift <= 0.0:
				_cart_down(v, true)
				v.state = St.STEP_BACK
			elif v.state == St.LIFT and v.lift >= 1.0:
				v.state = St.PUSH
			return true
		St.STEP_BACK, St.STEP_IN:
			# a small step straight back from the shafts (or in to them), keeping the facing
			var goal: Vector3 = v.home if v.state == St.STEP_BACK else _push_stand(v.home, v.yaw)
			var p: Vector3 = b.global_position
			var flat := Vector3(goal.x - p.x, 0.0, goal.z - p.z)
			b.turn_toward_yaw(v.yaw, delta, 3.0)
			Assets.play(v.fig, "idle")
			if flat.length() < 0.03:
				if v.state == St.STEP_BACK:
					v.state = St.OPEN
					var sd: Array = v.d.get("stop_secs", [60, 100])
					v.wait = _rng.randf_range(float(sd[0]), float(sd[1]))
				else:
					_cart_down(v, false)
					v.state = St.LIFT
			else:
				b.global_position = p + flat.normalized() * minf(flat.length(), 0.6 * delta)
			return true
	return false


func _push_clip(v: V) -> String:
	return "push_cart" if Assets.has_clip(v.fig, "push_cart") else "walk_carry"


## Hand midpoint of the seller in body space (forward, height), smoothed; the barrow's grips follow it.
func _read_hands(v: V) -> void:
	if v.sk == null:
		var sks := v.fig.find_children("*", "Skeleton3D", true, false)
		if sks.is_empty():
			return
		v.sk = sks[0]
		v.hands = Vector2i(v.sk.find_bone("hand_l"), v.sk.find_bone("hand_r"))
		var n: Node = v.sk
		while n != null and n != v.body:
			if n is Node3D:
				v.sk_in_body = (n as Node3D).transform * v.sk_in_body
			n = n.get_parent()
	if v.hands.x < 0 or v.hands.y < 0:
		return
	var m: Vector3 = v.sk_in_body * ((v.sk.get_bone_global_pose(v.hands.x).origin + v.sk.get_bone_global_pose(v.hands.y).origin) * 0.5)
	var k := 0.15
	v.grip_f = lerpf(v.grip_f, clampf(-m.z + 0.05, 0.12, 0.55), k)
	v.grip_h = lerpf(v.grip_h, clampf(m.y - 0.03, 0.6, 1.25), k)


## Places the barrow: tipped on its axle by `lift` x the tilt that brings the grips to the hands, shafts ending in
## the seller's hands, wheels on the ground; while it is resting (lift 0 after LOWER) it stays where it was put.
func _pose_cart(v: V, _delta: float) -> void:
	if v.prop == null or not is_instance_valid(v.body):
		return
	var b: Node3D = v.body
	var r := sqrt(v.du * v.du + v.dv * v.dv)
	var phi := atan2(v.dv, v.du)
	var full := clampf(asin(clampf((v.grip_h - v.axle.y) / r, -1.0, 1.0)) - phi, 0.0, MAX_TILT)
	var th := full * smoothstep(0.0, 1.0, v.lift)
	var yaw: float = b.rotation.y
	var fwd := Vector3(-sin(yaw), 0.0, -cos(yaw))
	var reach := v.du * cos(th) - v.dv * sin(th)
	var axle_w: Vector3 = b.global_position + fwd * (v.grip_f + reach)
	axle_w.y = b.global_position.y + v.axle.y
	var basis := Basis(Vector3.UP, yaw + v.prop_rot) * Basis(Vector3.RIGHT, th)
	v.prop.global_transform = Transform3D(basis, axle_w - basis * v.axle)
	if v.last_axle != Vector3.INF:
		var dist := (axle_w - v.last_axle).dot(fwd)
		v.wheel_ang += dist / maxf(v.wheel_r, 0.05)
		for w in v.wheels:
			(w as Node3D).rotation.x = v.wheel_ang
	v.last_axle = axle_w


# ------------------------------------------------------------------ per frame
func _physics_process(delta: float) -> void:
	_check_t -= delta
	var check := _check_t <= 0.0
	if check:
		_check_t = 0.5
	var alarm := _watch_alarmed() if check else false
	for v in vendors:
		_tick(v, delta, check, alarm)
		_sound_tick(v)


func _tick(v: V, delta: float, check: bool, alarm: bool) -> void:
	var b = v.body
	if not is_instance_valid(b):
		return
	if check:
		_check_state(v, alarm)
	if v.cart and _cart_tick(v, delta):
		return
	match v.state:
		St.GONE, St.HIDDEN:
			return
		St.LEAVING, St.FLEEING, St.RETURNING:
			var run := v.state == St.FLEEING
			var sp := 2.6 if run else 0.95
			if b.walk_to(v.target, sp, delta):
				_arrived(v)
			else:
				Assets.play_move(v.fig, "run" if run else str(v.d.get("walk_clip", "walk_carry")), sp)
			return
		St.CLOSING:
			b.halt(delta)
			Assets.play(v.fig, "bow" if v.wait > 1.2 else "idle")
			v.wait -= delta
			if v.wait <= 0.0:
				v.state = St.LEAVING
				v.target = _nearest_exit(b.global_position)
			return
	# open for business (standing at a pitch or walking a round)
	if _talking == v:
		b.halt(delta)
		var p := _player()
		if p:
			b.turn_toward_point(p.global_position, delta)
		Assets.play(v.fig, "talk_gesture_b")
		return
	v.cry_t -= delta
	v.cry_anim = maxf(v.cry_anim - delta, 0.0)
	if v.cry_t <= 0.0:
		var ci: Array = cfg.get("cry_interval", [12, 20])
		v.cry_t = _rng.randf_range(float(ci[0]), float(ci[1]))
		_cry(v)
	if v.state == St.WALKING:
		var sp := 0.9
		if b.walk_to(v.target, sp, delta):
			v.state = St.OPEN
			var sd: Array = v.d.get("stop_secs", [30, 50])
			v.wait = _rng.randf_range(float(sd[0]), float(sd[1]))
		else:
			Assets.play_move(v.fig, str(v.d.get("walk_clip", "walk_carry")), sp)
		return
	b.halt(delta)
	_serve(v, delta)
	if v.roaming and v.customers.is_empty():
		v.wait -= delta
		if v.wait <= 0.0:
			_next_stop(v)
			return
	if v.cart and v.pitches.size() > 1 and v.customers.is_empty():
		v.wait -= delta
		if v.wait <= 0.0:                  # on to the next pitch: back to the shafts, lift, push
			v.pitch_i = (v.pitch_i + 1) % v.pitches.size()
			_move_on(v, _push_stand(v.pitches[v.pitch_i][0], v.pitches[v.pitch_i][1]))
			return
	# pose
	var haggling: Node3D = null
	for c in v.customers:
		if int(c["phase"]) == 1:
			haggling = c["npc"]
			break
	if haggling:
		b.turn_toward_point(haggling.global_position, delta)
		Assets.play(v.fig, str(v.d.get("work_clip", "haggle")))
		if v.fx and str(v.d.get("fx", "")) == "sparks":
			v.fx.emitting = true
	else:
		b.turn_toward_yaw(v.yaw if not v.roaming else float(v.loop[v.loop_i][1]), delta, 2.0)
		Assets.play(v.fig, "talk_gesture_a" if v.cry_anim > 0.0 else _rest_clip(v))
		if v.fx and str(v.d.get("fx", "")) == "sparks":
			v.work_t -= delta
			v.fx.emitting = v.work_t > 0.0
			if v.work_t < -_rng.randf_range(10.0, 25.0):
				v.work_t = _rng.randf_range(2.0, 4.0)      # grinding his own stock between customers


func _next_stop(v: V) -> void:
	var n := v.loop.size()
	if n < 2:
		v.wait = 30.0
		return
	var nxt := v.loop_i + v.loop_dir
	if nxt < 0 or nxt >= n:
		v.loop_dir = -v.loop_dir
		nxt = v.loop_i + v.loop_dir
	v.loop_i = nxt
	v.target = v.loop[nxt][0]
	v.state = St.WALKING


## Closing time, the watch's alarm, and coming back when it has calmed down.
func _check_state(v: V, alarm: bool) -> void:
	var open := v.state == St.OPEN or v.state == St.WALKING
	if bool(v.d.get("flees_alarm", false)):
		if alarm and (open or v.state == St.CLOSING or v.state == St.RETURNING):
			_drop_customers(v)
			_end_talk_with(v)
			_bubble(v.body, _pick("flee_lines"), 2.5)
			v.state = St.FLEEING
			v.target = _nearest_exit(v.body.global_position)
			return
		if v.state == St.HIDDEN:
			v.calm = v.calm + 0.5 if not alarm and _watch_calm() else 0.0
			if v.calm >= float(cfg.get("return_after_calm", 90.0)) and not _past_closing(v):
				v.calm = 0.0
				_set_hidden(v, false)
				v.state = St.RETURNING
				v.target = v.home if not v.roaming else v.loop[v.loop_i][0]
			return
	if open and _past_closing(v) and v.cart:
		_drop_customers(v)
		_end_talk_with(v)
		_bubble(v.body, _pick("closing_lines"), 3.0)
		v.leaving = true
		if v.fx:
			v.fx.emitting = false
		_move_on(v, _nearest_exit(v.body.global_position))
		return
	if open and _past_closing(v):
		_drop_customers(v)
		_end_talk_with(v)
		_bubble(v.body, _pick("closing_lines"), 3.0)
		v.state = St.CLOSING
		v.wait = 2.6
		if v.prop and not v.d.has("prop_bone"):
			v.prop.visible = false
			if v.prop_body:
				v.prop_body.process_mode = Node.PROCESS_MODE_DISABLED
		if v.fx:
			v.fx.emitting = false
		if v.lamp and not bool(v.d.get("lamp", {}).get("on_body", false)):
			v.lamp.visible = false


func _past_closing(v: V) -> bool:
	return not _no_close and v.closing >= 0.0 and GameState.phase == GameState.Phase.NIGHT \
			and GameState.clock_minutes >= v.closing


func _arrived(v: V) -> void:
	match v.state:
		St.LEAVING:
			_set_hidden(v, true)
			v.state = St.GONE
		St.FLEEING:
			_set_hidden(v, true)
			v.state = St.HIDDEN
			v.calm = 0.0
		St.RETURNING:
			v.state = St.OPEN
			v.wait = 20.0


func _set_hidden(v: V, h: bool) -> void:
	v.body.visible = not h
	if v.cart and v.prop:
		v.prop.visible = not h
	v.shape.disabled = h
	if v.body.nav_agent:
		v.body.nav_agent.avoidance_enabled = not h
	if v.lamp and bool(v.d.get("lamp", {}).get("on_body", false)):
		v.lamp.visible = not h
	_set_crowd(v, false)


func _nearest_exit(p: Vector3) -> Vector3:
	var best := p
	var bd := INF
	for e in _exits:
		var d := Vector2(e.x - p.x, e.z - p.z).length()
		if d < bd:
			bd = d
			best = e
	return best


func _watch() -> Node:
	for w in get_tree().get_nodes_in_group("watch"):
		if "phase" in w:
			return w
	return null


func _watch_alarmed() -> bool:
	var w := _watch()
	return w != null and int(w.get("phase")) == 1     # watch.gd Phase.ALARM


func _watch_calm() -> bool:
	var w := _watch()
	return w == null or int(w.get("phase")) == 0      # Phase.CALM


# ------------------------------------------------------------------ cries and bubbles
func _cry(v: V) -> void:
	var cl: Array = v.d.get("cries", [])
	if cl.is_empty():
		return
	_bubble(v.body, cl[_rng.randi() % cl.size()], 3.4)
	v.cry_anim = 3.2 if not v.roaming or v.state == St.OPEN else 0.0
	cries += 1


func _pick(key: String) -> Variant:
	var a: Array = cfg.get(key, [])
	return a[_rng.randi() % a.size()] if not a.is_empty() else ""


## Speech bubble with the original words and, beneath in smaller italics, the English gloss.
func _bubble(node: Node3D, line: Variant, secs: float) -> void:
	if node == null or not is_instance_valid(node):
		return
	var text := str(line.get("text", "")) if line is Dictionary else str(line)
	var gloss := str(line.get("gloss", "")) if line is Dictionary else ""
	if text == "":
		return
	var old := node.get_node_or_null("SpeechBubble")
	if old:
		old.name = "SpeechBubbleOld"
		old.queue_free()
	var l := _label(text, 34, UiTheme.font("regular"), VERTICAL_ALIGNMENT_BOTTOM)
	l.name = "SpeechBubble"
	l.position.y = BUBBLE_H + (0.2 if gloss != "" else 0.0)
	if gloss != "":
		var g := _label("(%s)" % gloss, 26, UiTheme.font("italic"), VERTICAL_ALIGNMENT_TOP)
		g.modulate = Color(0.86, 0.82, 0.70)
		g.position.y = -0.03
		l.add_child(g)
	node.add_child(l)
	var tw := l.create_tween()
	tw.tween_interval(secs)
	tw.tween_callback(l.queue_free)


func _label(text: String, size: int, font: Font, valign: VerticalAlignment) -> Label3D:
	var l := Label3D.new()
	l.text = text
	l.font = font
	l.font_size = size
	l.outline_size = 10
	l.outline_modulate = Color(0.05, 0.04, 0.03, 0.9)
	l.modulate = Color(1.0, 0.95, 0.82)
	l.pixel_size = 0.0045
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.width = 560
	l.vertical_alignment = valign
	l.no_depth_test = true
	l.render_priority = 5
	return l


# ------------------------------------------------------------------ customers (townsfolk from population.gd)
func _pop() -> Node:
	if _population == null or not is_instance_valid(_population):
		_population = get_tree().get_first_node_in_group("population")
	return _population


## NPC ids a storyline or the mission may claim (anything they mention by id) stay out of the queue.
func _build_exclusions() -> void:
	_excluded_ready = true
	var text := JSON.stringify(Mission.data) if Mission.data else ""
	var pop := _pop()
	if pop and "storylines" in pop:
		for s in pop.storylines:
			if is_instance_valid(s) and "data" in s:
				text += JSON.stringify(s.data)
	for n in get_tree().get_nodes_in_group("npcs"):
		if n.get_script() == NpcScript and ("\"%s\"" % n.npc_id) in text:
			_excluded[n.npc_id] = true


func _eligible(n: Node) -> bool:
	if not is_instance_valid(n) or n.get_script() != NpcScript or _busy.has(n) or _excluded.has(n.npc_id):
		return false
	var npc = n
	if not npc.visible or npc.is_inside() or npc.is_downed():
		return false
	if npc.mode == NpcScript.Mode.SCRIPTED or npc.mode == NpcScript.Mode.DOWNED:
		return false
	if float(_cooldown.get(npc, 0.0)) > _now():
		return false
	var r := str(npc.role).to_lower()
	for bad in ["informer", "smuggler", "lookout", "beggar", "stall", "merchant", "priest", "bishop", "guard", "carrier"]:
		if bad in r or bad in str(npc.npc_id):
			return false
	return true


func _now() -> float:
	return Time.get_ticks_msec() / 1000.0


func _serve(v: V, delta: float) -> void:
	# customers in progress
	for c in v.customers.duplicate():
		var npc = c["npc"]
		if not is_instance_valid(npc) or npc.is_downed() or npc.mode != NpcScript.Mode.SCRIPTED:
			_forget(v, c)
			continue
		c["t"] = float(c["t"]) - delta
		if int(c["phase"]) == 0:
			if npc.script_arrived:
				c["phase"] = 1
				var hs: Array = cfg.get("haggle_secs", [5.0, 8.0])
				c["t"] = float(c.get("haggle", _rng.randf_range(float(hs[0]), float(hs[1]))))
				npc.script_face(v.body)
				npc.script_play("haggle")
				_bubble(v.body, _pick("haggle_seller"), 2.4)
			elif float(c["t"]) <= 0.0:
				_release(v, c, false)
		else:
			if not bool(c.get("said", false)) and float(c["t"]) < float(c.get("haggle", 6.0)) * 0.6:
				c["said"] = true
				_bubble(npc, _pick("haggle_buyer"), 2.2)
			if float(c["t"]) <= 0.0:
				_release(v, c, true)
	_set_crowd(v, not v.roaming and v.customers.size() >= 2)
	# draw a new customer now and then
	if v.roaming:
		return
	v.sale_t -= delta
	if v.sale_t > 0.0:
		return
	var si: Array = cfg.get("sale_interval", [22, 50])
	v.sale_t = _rng.randf_range(float(si[0]), float(si[1]))
	if v.customers.size() >= 2:
		return
	var npc := _nearest_customer(v.body.global_position, float(cfg.get("customer_radius", 16.0)))
	if npc:
		start_sale(v, npc)
		if v.customers.size() == 1 and _rng.randf() < float(cfg.get("second_customer_chance", 0.4)):
			var n2 := _nearest_customer(v.body.global_position, float(cfg.get("customer_radius", 16.0)))
			if n2:
				start_sale(v, n2)


func _nearest_customer(p: Vector3, radius: float) -> Node3D:
	if not _excluded_ready:
		_build_exclusions()
	var best: Node3D = null
	var bd := radius
	for n in get_tree().get_nodes_in_group("npcs"):
		if not _eligible(n):
			continue
		var d := (n as Node3D).global_position.distance_to(p)
		if d < bd:
			bd = d
			best = n
	return best


## Sends `npc` to a slot in front of the seller (the second customer stands a little to the side).
func start_sale(v: V, npc: Node3D, haggle: float = -1.0) -> void:
	var slot := 0 if v.customers.is_empty() or int(v.customers[0]["slot"]) == 1 else 1
	var serve := float(v.d.get("serve", 1.2))
	var off := Vector3(0.0, 0.0, -serve) if slot == 0 else Vector3(0.75, 0.0, -serve + 0.25)
	npc.claim()
	npc.script_goto(v.body.global_transform * off)
	var c := {"npc": npc, "slot": slot, "phase": 0, "t": 30.0}
	if haggle > 0.0:
		c["haggle"] = haggle
	v.customers.append(c)
	_busy[npc] = v


func _release(v: V, c: Dictionary, sold: bool) -> void:
	var npc = c["npc"]
	_forget(v, c)
	if not is_instance_valid(npc):
		return
	_cooldown[npc] = _now() + float(cfg.get("customer_cooldown", 90.0))
	npc.release()
	if sold:
		sales += 1
		if v.fx and str(v.d.get("fx", "")) == "sparks":
			v.fx.emitting = false
		# walk on with the purchase: npc.gd plays carry_basket for anyone whose role says "carrier"
		var was := str(npc.role)
		npc.role = was + " carrier"
		get_tree().create_timer(float(cfg.get("carry_secs", 20.0)), false).timeout.connect(_uncarry.bind(npc, was))


func _uncarry(npc: Object, was: String) -> void:
	if is_instance_valid(npc):
		npc.set("role", was)


func _forget(v: V, c: Dictionary) -> void:
	v.customers.erase(c)
	var npc: Object = c["npc"]
	_busy.erase(npc)
	if is_instance_valid(npc) and (npc as Node).is_in_group("crowd"):
		(npc as Node).remove_from_group("crowd")


func _drop_customers(v: V) -> void:
	for c in v.customers.duplicate():
		_release(v, c, false)
	_set_crowd(v, false)


## Stealth hook: a stationary seller with 2+ customers is a crowd (seller and customers in group "crowd").
func _set_crowd(v: V, on: bool) -> void:
	if on == v.crowd:
		return
	v.crowd = on
	var members: Array = [v.body]
	for c in v.customers:
		members.append(c["npc"])
	for m in members:
		if not is_instance_valid(m):
			continue
		if on:
			(m as Node).add_to_group("crowd")
		elif (m as Node).is_in_group("crowd"):
			(m as Node).remove_from_group("crowd")


# ------------------------------------------------------------------ the player: buy, gossip, leave
func _player() -> Node3D:
	return get_tree().get_first_node_in_group("player") as Node3D


func _prompt(v: V) -> String:
	if v.state != St.OPEN and v.state != St.WALKING:
		return ""
	return "buy from the %s" % str(v.d.get("name", "seller"))


func _on_interact(_actor: Node, v: V) -> bool:
	return open_dialogue(v)


## The mission runner's dialogue box when there is one (so the player is held still while talking), else our own.
func _dialogue() -> CanvasLayer:
	var r: Node = Mission.runner
	if r != null and is_instance_valid(r) and r.get("dialogue") != null:
		return r.get("dialogue")
	if _own_dlg == null:
		_own_dlg = DialogueScript.new()
		_own_dlg.name = "VendorDialogue"
		add_child(_own_dlg)
	return _own_dlg


func open_dialogue(v: V) -> bool:
	var dl := _dialogue()
	if dl == null or dl.is_open or _talking != null:
		return false
	_dlg = dl
	_talking = v
	if v.state == St.WALKING:
		v.state = St.OPEN
		v.wait = maxf(v.wait, 8.0)
	var r: Node = Mission.runner
	if r != null and is_instance_valid(r) and dl == r.get("dialogue"):
		r.set("_choices", [])            # its choice handler ignores indices it did not offer
	dl.set_meta("node", "__vendor")      # ...and its finished handler finds no such node
	if not dl.choice_made.is_connected(_on_choice):
		dl.choice_made.connect(_on_choice)
	if not dl.finished.is_connected(_on_finished):
		dl.finished.connect(_on_finished)
	var price := int(cfg.get("price", 1))
	var who := str(v.d.get("name", "seller")).capitalize()
	var choices := [
		{"text": "Buy %s  (%d coin)" % [v.d.get("ware", "something"), price], "enabled": GameState.coins >= price,
				"why": "your purse is empty"},
		{"text": "Anything worth hearing tonight?"},
		{"text": "Leave"},
	]
	_dlg_actions = ["buy", "gossip", "leave"]
	dl.show_node([[who, str(v.d.get("pitch", "..."))]], choices)
	return true


func _on_choice(i: int) -> void:
	var v := _talking
	if v == null or i < 0 or i >= _dlg_actions.size():
		return
	var who := str(v.d.get("name", "seller")).capitalize()
	match _dlg_actions[i]:
		"buy":
			var lines: Array = [[who, str(v.d.get("thanks", "There you are."))]]
			var extra := _buy(v)
			if extra != "":
				lines.append(["", extra])
			_dlg.show_node(lines, [])
		"gossip":
			var g: Array = v.d.get("gossip", [])
			var text := "Nothing you'd pay for." if g.is_empty() else str(g[v.gossip_i % g.size()])
			v.gossip_i += 1
			if not g.is_empty():
				Mission.journal_log("Street talk, the %s: %s" % [v.d.get("name", "seller"), text], "note")
			_dlg.show_node([[who, text]], [])
		_:
			_dlg.close()
			_end_talk()


## Pays and applies the purchase. Returns a line of narration for the dialogue, or "".
func _buy(v: V) -> String:
	var price := int(cfg.get("price", 1))
	GameState.coins -= price
	var item := str(v.d.get("item", "something"))
	bought = item
	var note := ""
	var heal := int(v.d.get("heal", 0))
	var p := _player()
	if heal > 0 and p != null and "health" in p:
		var mx: int = Player.MAX_HEALTH if p is Player else 3
		var before := int(p.get("health"))
		p.set("health", mini(before + heal, mx))
		note = "Warm food. You feel steadier." if int(p.get("health")) > before else "Warm food in a cold hand."
	elif str(v.d.get("effect", "")) == "warmth":
		note = "Heat spreads from your belly to your frozen fingers."
	if v.d.has("flag"):
		Mission.set_flag(str(v.d["flag"]), true)
		note = "You fold the sheet into your coat. The words would hang a man in Vienna."
	Mission.message.emit("Bought %s (-%d coin)" % [item, price], 3.0)
	Mission.journal_log("Bought %s from the %s for %d coin." % [item, v.d.get("name", "seller"), price], "note")
	return note


func _on_finished() -> void:
	_end_talk()


func _end_talk() -> void:
	if _dlg:
		if _dlg.choice_made.is_connected(_on_choice):
			_dlg.choice_made.disconnect(_on_choice)
		if _dlg.finished.is_connected(_on_finished):
			_dlg.finished.disconnect(_on_finished)
	_talking = null


func _end_talk_with(v: V) -> void:
	if _talking == v:
		if _dlg:
			_dlg.close()
		_end_talk()


func _exit_tree() -> void:
	if _talking != null:
		_end_talk()


func vendor(id: String) -> V:
	for v in vendors:
		if v.id == id:
			return v
	return null


func count() -> int:
	return vendors.size()


# ------------------------------------------------------------------ smoke
## One player purchase (through the dialogue) and one NPC sale at the all-night chestnut cart, then the report.
func _smoke_run() -> void:
	await get_tree().create_timer(1.0, false).timeout
	if not is_inside_tree():
		return
	var ob := vendor("obwarzanki")
	if ob and open_dialogue(ob):
		for i in 4:
			if _dlg.is_choosing():
				break
			_dlg.advance()
		_dlg.choose(0)
		for i in 6:
			if not _dlg.is_open:
				break
			_dlg.advance()
		_end_talk()
	await get_tree().create_timer(0.5, false).timeout
	if not is_inside_tree():
		return
	var kv := vendor("grzaniec")
	if kv:
		var npc := _nearest_customer(kv.body.global_position, 999.0)
		if npc:
			# bring a passer-by close so the sale finishes before the smoke run moves on
			npc.global_position = kv.body.global_transform * Vector3(0.6, 0.0, -4.0)
			npc.reset_physics_interpolation()
			start_sale(kv, npc, 2.5)
	var t := 0.0
	while t < 20.0 and sales < 1 and is_inside_tree():
		await get_tree().create_timer(0.25, false).timeout
		t += 0.25
	if is_inside_tree():
		print("[smoke] vendors n=%d sales=%d cries=%d bought=%s" % [count(), sales, cries, bought.replace(" ", "_")])


# ------------------------------------------------------------------ inspection shots (`-- --vendor-shot=/dir`)
## The barrow sellers arrive pushing their carts at the start of the night: side and three-quarter views of each.
func _push_shots(dir: String) -> void:
	var hidden: Array = []
	for c in get_tree().root.find_children("*", "CanvasLayer", true, false):
		if (c as CanvasLayer).visible:
			hidden.append(c)
			(c as CanvasLayer).visible = false
	var cam := Camera3D.new()
	cam.fov = 50
	add_child(cam)
	cam.current = true
	for id in ["kasztany", "szlifierz", "ryby"]:
		var v := vendor(id)
		if v == null or v.state != St.PUSH:
			continue
		for view in [["side", Vector3(3.0, 1.2, -0.7), Vector3(0, 0.75, -0.75)], ["34", Vector3(2.3, 1.7, -3.2), Vector3(0, 0.8, -0.7)], ["rear34", Vector3(2.0, 1.7, 2.0), Vector3(0, 0.8, -0.6)]]:
			var bt: Transform3D = v.body.global_transform
			var eye := view[1] as Vector3
			if (bt * Vector3(-eye.x, eye.y, eye.z)).length() < (bt * eye).length():
				eye.x = -eye.x                # shoot from the square's side, not from inside a facade
			cam.look_at_from_position(bt * eye, bt * (view[2] as Vector3))
			for f in 3:
				await get_tree().process_frame
			get_viewport().get_texture().get_image().save_png("%s/vendor_push_%s_%s.png" % [dir, id, view[0]])
		print("[smoke] vendor push %s state=%s lift=%.2f grip_f=%.2f grip_h=%.2f clip=%s wheel=%.2f" % [id, St.keys()[v.state], v.lift, v.grip_f, v.grip_h, _push_clip(v), v.wheel_ang])
	cam.queue_free()
	for c in hidden:
		if is_instance_valid(c):
			(c as CanvasLayer).visible = true


## The smoke run replaces this night after ~10 s, so everything is staged at once: two customers put straight
## into their places at the ring-bread woman, the grinder at his stone.
func _shots(dir: String) -> void:
	await get_tree().create_timer(1.5, false).timeout
	if not is_inside_tree():
		return
	await _push_shots(dir)
	if not is_inside_tree():
		return
	var ob := vendor("obwarzanki")
	if ob:
		for k in 2:
			var npc := _nearest_customer(ob.body.global_position, 999.0)
			if npc:
				start_sale(ob, npc, 30.0)
				var slot: Vector3 = npc._script_target
				npc.global_position = slot
				npc.reset_physics_interpolation()
	var gr := vendor("szlifierz")
	if gr:
		gr.work_t = 60.0
	var t := 0.0
	while t < 5.0 and is_inside_tree():
		var ok := ob == null or ob.customers.is_empty() or int(ob.customers[0]["phase"]) == 1
		if ok and t > 1.5:
			break
		await get_tree().create_timer(0.25, false).timeout
		t += 0.25
	if not is_inside_tree():
		return
	print("[smoke] vendor shots: crowd=%d customers=%d" % [get_tree().get_nodes_in_group("crowd").size(), ob.customers.size() if ob else 0])
	var cam := Camera3D.new()
	cam.fov = 55
	add_child(cam)
	cam.current = true
	# the buy dialogue first (HUD visible), over the player's shoulder
	var kv := vendor("grzaniec")
	if kv:
		cam.look_at_from_position(kv.body.global_transform * Vector3(0.7, 1.75, -3.2), kv.body.global_transform * Vector3(0, 1.2, 0))
		var opened := open_dialogue(kv)
		print("[smoke] vendor dialogue opened=%s talking=%s" % [opened, _talking != null])
		if opened:
			for i in 3:
				if _dlg.is_choosing():
					break
				_dlg.advance()
			for f in 6:
				await get_tree().process_frame
			get_viewport().get_texture().get_image().save_png("%s/vendor_dialogue.png" % dir)
			_dlg.close()
			_end_talk()
	var layers: Array = []
	for c in get_tree().root.find_children("*", "CanvasLayer", true, false):
		if (c as CanvasLayer).visible:
			layers.append(c)
			(c as CanvasLayer).visible = false
	var close := {"kasztany": [Vector3(1.9, 1.7, -3.8), Vector3(0, 0.9, -0.7)],
			"obwarzanki": [Vector3(2.7, 1.6, -0.9), Vector3(0.0, 1.1, -0.7)],
			"ryby": [Vector3(-1.2, 2.3, -2.7), Vector3(0, 0.7, -0.9)],
			"szlifierz": [Vector3(2.0, 1.5, -2.9), Vector3(0, 0.9, -0.6)]}
	for v in vendors:
		if not v.body.visible:
			continue
		var c: Array = close.get(v.id, [Vector3(1.3, 1.6, -2.6), Vector3(0, 1.1, -0.2)])
		cam.look_at_from_position(v.body.global_transform * (c[0] as Vector3), v.body.global_transform * (c[1] as Vector3))
		for f in 4:
			await get_tree().process_frame
		get_viewport().get_texture().get_image().save_png("%s/vendor_%s.png" % [dir, v.id])
	# the chestnut roaster set down at his pitch, stepped back from the shafts
	var kc := vendor("kasztany")
	var w := 0.0
	while kc and kc.state != St.OPEN and w < 10.0 and is_inside_tree():
		await get_tree().create_timer(0.25, false).timeout
		w += 0.25
	if kc and is_inside_tree():
		for view in [["side", Vector3(3.0, 1.2, -0.7), Vector3(0, 0.75, -0.9)], ["34", Vector3(2.3, 1.7, -3.2), Vector3(0, 0.8, -0.8)]]:
			cam.look_at_from_position(kc.body.global_transform * (view[1] as Vector3), kc.body.global_transform * (view[2] as Vector3))
			for f in 3:
				await get_tree().process_frame
			get_viewport().get_texture().get_image().save_png("%s/vendor_setdown_kasztany_%s.png" % [dir, view[0]])
		print("[smoke] vendor setdown kasztany state=%s lift=%.2f after %.1fs" % [St.keys()[kc.state], kc.lift, w])
	for c in layers:
		if is_instance_valid(c):
			(c as CanvasLayer).visible = true
	cam.queue_free()
	print("[smoke] vendor shots in ", dir)


# ------------------------------------------------------------------ sound (scripts/audio/sfx.gd, docs/AUDIO.md)
## The chestnut brazier and the beer pot crackle; the knife grinder's stone whines while his sparks fly.
func _make_sound(v: V) -> void:
	var fx := str(v.d.get("fx", ""))
	var set_name: String = {"smoke": "brazier_loop", "steam": "brazier_loop", "sparks": "grinder_loop"}.get(fx, "")
	if set_name == "" or not is_instance_valid(v.body):
		return
	var at: Variant = v.d.get("fx_at", [0.0, 1.0, -0.8])
	var p := Sfx.attach_loop(v.body, set_name, 0.0 if fx == "smoke" else (-4.0 if fx == "steam" else 0.0), -1.0,
			Vector3(float(at[0]), float(at[1]), float(at[2])))
	if p:
		p.stream_paused = fx == "sparks"
		v.body.set_meta("sfx_loop", p)


func _sound_tick(v: V) -> void:
	if not is_instance_valid(v.body) or not v.body.has_meta("sfx_loop"):
		return
	var p := v.body.get_meta("sfx_loop") as AudioStreamPlayer3D
	if p == null or not is_instance_valid(p):
		return
	var gone: bool = v.state == St.GONE or v.state == St.HIDDEN or not v.body.visible
	if str(v.d.get("fx", "")) == "sparks":
		p.stream_paused = gone or v.fx == null or not v.fx.emitting
	else:
		p.stream_paused = gone or v.state == St.LEAVING or v.state == St.FLEEING

