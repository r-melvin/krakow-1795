extends "res://scripts/npc/walker.gd"
## Ambient animals and horse-drawn vehicles (models from assets/blender/build_animals.py; see docs/ANIMALS.md).
## Behaviours:
##   "stand"   stays put, playing "idle" (with `tether`, a hitching rail is set in front of its head)
##   "wander"  potters around its post within `radius`
##   "follow"  trots at the heel of a person (`follow: "<npc id>"` in data/npcs.json)
##   "circle"  flies a circle of `radius` round its post at the post's height (hawk), playing "fly"
##   "drive"   a vehicle (carriage / horse_cart glb): harnessed horses in the glb's horse_slot_N empties pull
##             it round `route` (a loop of points) at `speed`; the vehicle trails the team on its pole like a
##             real trailer. Stops for the player, townsfolk, guards and other vehicles in its way.
## Rigged models play "idle" / "walk" (or "fly") from their AnimationPlayer ("sit" instead of "idle" for a
## standing animal that has one); older static models just stand.

## Ground speed (m/s) each gait clip covers at playback speed 1 (stride / cycle), from assets/blender/build_animals.py
## (HORSE_WALK / HORSE_TROT / DOG_WALKS / PIGEON_WALK). Playback speed = actual speed / this, so hooves and
## paws stay planted instead of sliding.
const GAIT_REF := {
	"horse": {"walk": 1.5, "trot": 3.0}, "horse_harnessed": {"walk": 1.5, "trot": 3.0},
	"dog_hound": {"walk": 1.125}, "dog_spitz": {"walk": 0.98}, "cat": {"walk": 0.55},
	"pigeon": {"walk": 0.225}, "crow": {"walk": 0.25},
}
const TROT_ABOVE := 1.8          ## horses trot above this ground speed (the dorozka's 2 m/s is a slow trot)
const LIFT := {"pigeon": 0.035, "crow": 0.035}   ## small birds would vanish into the parallax-mapped setts
const DRIVERS := ["town_coachman", "npc_m_03", "npc_m_01", "figure_townsman"]
const TURN_RATE := 0.75        ## rad/s at full speed: ~2.7 m turning radius at 2 m/s
const WAYPOINT_REACH := 4.0

var npc_id := "animal"
var candidates: PackedStringArray = []
var behaviour := "stand"
var radius := 3.0
var facing := 0.0
var speed := 0.7
var role := ""
var model_name := ""
var follow := ""                  ## npc_id of the person this animal trots after, "" = none
var tether := false               ## stand at a hitching rail
var route: Array = []             ## Vector3 loop for "drive"
var route_start := 0

var _leader: Node3D
var _home: Vector3
var _target: Vector3
var _pause := 0.0
var _rng := RandomNumberGenerator.new()
var _anims: Array[AnimationPlayer] = []
var _walk_ref := 1.0
var _rest_clip := "idle"          ## "sit" for a standing animal whose model has a sit clip (the cat)

# vehicle state
var _trailer: CharacterBody3D     ## the carriage body, dragged behind the team (top-level)
var _trail_len := 3.5             ## team centre -> vehicle origin
var _wheels: Array = []           ## [Node3D, radius]
var _wp := 0
var _drive_speed := 0.0
var _blocked_t := 0.0
var _ignore_npcs_t := 0.0
var _angle := 0.0


func _ready() -> void:
	add_to_group("animals")
	Footsteps.attach(self, "auto")    # hoof beats on the walk cycle, wheels, harness, calls (scripts/audio/footsteps.gd)
	_rng.seed = hash(npc_id)
	_home = global_position
	_target = _home
	rotation.y = facing
	_pause = _rng.randf_range(0.5, 2.5)
	if behaviour == "drive":
		add_to_group("vehicles")
		_build_vehicle.call_deferred()
		return
	_build()
	if behaviour == "circle":
		_angle = _rng.randf() * TAU
		for c in get_children():
			if c is CollisionShape3D:
				(c as CollisionShape3D).disabled = true
		_play("fly", 0.7)
		return
	setup_navigation(0.3 if _box_size().x < 0.5 else 0.6, 0.6, 4.0)
	nav_agent.avoidance_priority = 0.3   # animals give way to people
	if follow != "":
		behaviour = "follow"
	if behaviour == "stand":
		for ap in _anims:
			if ap.has_animation("sit"):
				_rest_clip = "sit"
	_play(_rest_clip)
	_desync()


# ------------------------------------------------------------------ building
func _pick_model() -> String:
	for n in candidates:
		if ResourceLoader.exists("res://assets/models/%s.glb" % n):
			return n
	return ""


func _build() -> void:
	model_name = _pick_model()
	_walk_ref = GAIT_REF.get(model_name, {}).get("walk", 1.0)
	var mesh: Node3D = Assets.instance(model_name) if model_name != "" else null
	var box := AABB(Vector3(-0.2, 0, -0.3), Vector3(0.4, 0.4, 0.6))
	if mesh:
		_strip_collision(mesh)
		mesh.rotation.y = PI       # Blender front -Y lands on +Z; turn to face -Z like other Node3Ds.
		mesh.position.y = LIFT.get(model_name, 0.0)
		add_child(mesh)
		_collect_anims(mesh)
		var b := _merged_aabb(mesh, mesh.transform)
		if b.size != Vector3.ZERO:
			box = b
	else:
		push_warning("Animal %s: no model among %s" % [npc_id, candidates])
	if tether:
		var rail := Assets.instance("hitch_rail")
		if rail:
			_strip_collision(rail)
			rail.position = Vector3(0, 0, box.position.z - 0.45)
			add_child(rail)
			box = box.merge(AABB(rail.position - Vector3(1.3, 0, 0.1), Vector3(2.6, 1.2, 0.2)))
	_add_box(self, box)


func _add_box(body: Node, box: AABB) -> void:
	var shape := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(maxf(box.size.x, 0.1), maxf(box.size.y, 0.1), maxf(box.size.z, 0.1))
	shape.shape = bs
	shape.position = box.get_center()
	body.add_child(shape)


func _box_size() -> Vector3:
	for c in get_children():
		if c is CollisionShape3D and (c as CollisionShape3D).shape is BoxShape3D:
			return ((c as CollisionShape3D).shape as BoxShape3D).size
	return Vector3.ONE


## The glbs carry a collision proxy that imports as a StaticBody3D. Drop it: a static body would collide with this moving body (and be baked into the navmesh);
## the body's own box shape replaces it.
func _strip_collision(n: Node) -> void:
	for c in n.get_children():
		if c is StaticBody3D:
			# "-col" (legacy) imports as a visible mesh holding the body: drop both. "-colonly" imports as a bare
			# StaticBody3D under the visual it was parented to: drop only the body, keep the visual.
			var owner_mesh := n if (n is MeshInstance3D and String(n.name).ends_with("-col")) else c
			owner_mesh.get_parent().remove_child(owner_mesh)
			owner_mesh.queue_free()
			return
		_strip_collision(c)


func _merged_aabb(n: Node, xf: Transform3D) -> AABB:
	var out := AABB()
	var first := true
	if n is MeshInstance3D and (n as MeshInstance3D).mesh:
		out = xf * (n as MeshInstance3D).mesh.get_aabb()
		first = false
	for c in n.get_children():
		if c is Node3D:
			var b := _merged_aabb(c, xf * (c as Node3D).transform)
			if b.size == Vector3.ZERO:
				continue
			out = b if first else out.merge(b)
			first = false
	return out


func _collect_anims(n: Node) -> void:
	if n is AnimationPlayer:
		var ap := n as AnimationPlayer
		for a in ap.get_animation_list():
			ap.get_animation(a).loop_mode = Animation.LOOP_LINEAR
		_anims.append(ap)
	for c in n.get_children():
		_collect_anims(c)


func _play(clip: String, spd: float = 1.0) -> void:
	for ap in _anims:
		var name := clip if ap.has_animation(clip) else ("idle" if ap.has_animation("idle") else "")
		if name == "":
			continue
		if ap.current_animation != name:
			ap.play(name, 0.25)
		ap.speed_scale = spd if name == clip else 1.0


func _desync() -> void:
	for ap in _anims:
		if ap.current_animation != "":
			ap.seek(_rng.randf() * ap.current_animation_length, true)


func _find(n: Node, prefix: String, out: Array) -> Array:
	if n.name.begins_with(prefix):
		out.append(n)
	for c in n.get_children():
		_find(c, prefix, out)
	return out


# ------------------------------------------------------------------ vehicles
## Team (this body) at the front: the harnessed horses. The vehicle glb rides on a top-level CharacterBody3D
## (not a StaticBody3D, which the runtime navmesh bake would carve out) dragged behind on its pole.
func _build_vehicle() -> void:
	model_name = _pick_model()
	var veh: Node3D = Assets.instance(model_name) if model_name != "" else null
	if veh == null:
		push_warning("Vehicle %s: no model among %s" % [npc_id, candidates])
		return
	_strip_collision(veh)
	var slots := _find(veh, "horse_slot", [])
	var slot_z := 3.45
	var team_box := AABB()
	var team_first := true
	for i in slots.size():
		var s: Node3D = slots[i]
		var horse := Assets.instance("horse_harnessed")
		if horse == null:
			continue
		_strip_collision(horse)
		horse.rotation.y = PI
		# slot position is in the vehicle's glb space (front +Z): mirror into this body's space (front -Z)
		horse.position = Vector3(-s.position.x, 0.0, 0.0)
		slot_z = s.position.z
		add_child(horse)
		_collect_anims(horse)
		var b := _merged_aabb(horse, horse.transform)
		team_box = b if team_first else team_box.merge(b)
		team_first = false
	_trail_len = absf(slot_z)
	if team_first:
		team_box = AABB(Vector3(-0.8, 0, -1.4), Vector3(1.6, 1.8, 2.8))
	_add_box(self, team_box)
	var obst := NavigationObstacle3D.new()
	obst.radius = maxf(team_box.size.x, team_box.size.z) * 0.5
	obst.avoidance_enabled = true
	add_child(obst)
	# the vehicle body, trailing
	_trailer = CharacterBody3D.new()
	_trailer.name = npc_id + "_vehicle"
	_trailer.top_level = true
	add_child(_trailer)
	veh.rotation.y = PI
	_trailer.add_child(veh)
	var vb := _merged_aabb(veh, veh.transform)
	if vb.size != Vector3.ZERO:
		# shape covers the body only (from just behind the horses to the tail), not the pole between them
		var back := AABB(vb.position, vb.size)
		var front_z := -_trail_len * 0.45
		back = AABB(Vector3(back.position.x, back.position.y, front_z), Vector3(back.size.x, back.size.y, back.end.z - front_z))
		_add_box(_trailer, back)
	var o2 := NavigationObstacle3D.new()
	o2.radius = 1.4
	o2.avoidance_enabled = true
	_trailer.add_child(o2)
	for w in _find(veh, "wheel_", []):
		var wb := _merged_aabb(w, Transform3D.IDENTITY)
		_wheels.append([w, maxf(wb.size.y * 0.5, 0.2)])
	for l in _find(veh, "lamp_", []):          # both carriage lamps: small, unshadowed pools
		var light := OmniLight3D.new()
		light.light_color = Color(1.0, 0.72, 0.4)
		light.light_energy = 0.9
		light.omni_range = 5.0
		light.shadow_enabled = false
		(l as Node3D).add_child(light)
	var seats := _find(veh, "driver_seat", [])
	if seats.size() > 0:
		_seat_driver(seats[0])
	# start on the route
	if route.size() > 1:
		_wp = (route_start + 1) % route.size()
		var p0: Vector3 = route[route_start % route.size()]
		var p1: Vector3 = route[_wp]
		global_position = p0
		var d := p1 - p0
		rotation.y = atan2(-d.x, -d.z)
	_place_trailer(true)
	_play("idle")
	_desync()


## A coachman on the box, posed sitting (thighs forward, knees bent, forearms out holding the reins).
func _seat_driver(seat: Node3D) -> void:
	var fig: Node3D = null
	for n in DRIVERS:
		if ResourceLoader.exists("res://assets/models/%s.glb" % n):
			fig = Assets.instance(n)
			break
	if fig == null:
		return
	seat.add_child(fig)
	fig.position = Vector3(0, -0.93, 0.05)
	var ap := Assets._find_anim_player(fig)
	if ap:
		ap.stop()
	var sk := _skeleton(fig)
	if sk == null:
		return
	var bends := {"thigh_l": -1.45, "thigh_r": -1.45, "calf_l": 1.5, "calf_r": 1.5,
			"upperarm_l": -0.5, "upperarm_r": -0.5, "lowerarm_l": -0.9, "lowerarm_r": -0.9}
	for b in bends:
		var i := sk.find_bone(b)
		if i >= 0:
			var rest := sk.get_bone_rest(i).basis.get_rotation_quaternion()
			sk.set_bone_pose_rotation(i, rest * Quaternion(Vector3.RIGHT, bends[b]))


func _skeleton(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n
	for c in n.get_children():
		var r := _skeleton(c)
		if r:
			return r
	return null


func _place_trailer(snap: bool) -> void:
	if _trailer == null:
		return
	var fwd := -global_transform.basis.z
	var hitch := global_position
	var q: Vector3
	if snap:
		q = hitch - fwd * _trail_len
	else:
		q = _trailer.global_position
		var d := hitch - q
		d.y = 0.0
		if d.length() < 0.01:
			d = fwd
		q = hitch - d.normalized() * _trail_len
	q.y = global_position.y
	var dir := hitch - q
	var yaw := atan2(-dir.x, -dir.z)
	var moved := Vector2(q.x - _trailer.global_position.x, q.z - _trailer.global_position.z).length()
	_trailer.global_transform = Transform3D(Basis(Vector3.UP, yaw), q)
	if not snap:
		for w in _wheels:
			(w[0] as Node3D).rotation.x += moved / float(w[1])


func _drive(delta: float) -> void:
	if route.size() < 2:
		return
	var target: Vector3 = route[_wp]
	var to := Vector3(target.x - global_position.x, 0.0, target.z - global_position.z)
	if to.length() < WAYPOINT_REACH:
		_wp = (_wp + 1) % route.size()
		target = route[_wp]
		to = Vector3(target.x - global_position.x, 0.0, target.z - global_position.z)
	var blocked := _blocked_ahead()
	if blocked:
		_blocked_t += delta
		if _blocked_t > 12.0:                   # a townsman planted in the road: edge past him
			_ignore_npcs_t = 5.0
			_blocked_t = 0.0
	else:
		_blocked_t = 0.0
	_ignore_npcs_t = maxf(_ignore_npcs_t - delta, 0.0)
	_drive_speed = move_toward(_drive_speed, 0.0 if blocked else speed, (4.0 if blocked else 0.7) * delta)
	var want := atan2(-to.x, -to.z)
	var k := clampf(_drive_speed / maxf(speed, 0.1), 0.25, 1.0)
	rotation.y = rotate_toward(rotation.y, want, TURN_RATE * k * delta)
	global_position += -global_transform.basis.z * _drive_speed * delta
	_place_trailer(false)
	if _drive_speed > 0.15:
		var g: Dictionary = GAIT_REF["horse_harnessed"]
		if _drive_speed > TROT_ABOVE:
			_play("trot", clampf(_drive_speed / g["trot"], 0.4, 1.6))
		else:
			_play("walk", clampf(_drive_speed / g["walk"], 0.3, 1.6))
	else:
		_play("idle")


## Anyone (or any vehicle) standing in the road just ahead of the horses.
func _blocked_ahead() -> bool:
	var fwd := -global_transform.basis.z
	var side := global_transform.basis.x
	var groups := ["player", "guards", "vehicles"] if _ignore_npcs_t > 0.0 else ["player", "guards", "npcs", "vehicles"]
	for g in groups:
		for n in get_tree().get_nodes_in_group(g):
			if n == self or not (n is Node3D) or not (n as Node3D).is_visible_in_tree():
				continue
			var pts: Array = [(n as Node3D).global_position]
			if g == "vehicles" and n.get("_trailer") != null:
				pts.append((n.get("_trailer") as Node3D).global_position)
			for p in pts:
				var d: Vector3 = p - global_position
				var f := d.dot(fwd)
				if f > 0.8 and f < 4.2 and absf(d.dot(side)) < 1.5 and absf(d.y) < 2.0:
					return true
	return false


func vehicle_position() -> Vector3:
	return _trailer.global_position if _trailer else global_position


# ------------------------------------------------------------------ per-frame
func _physics_process(delta: float) -> void:
	match behaviour:
		"drive":
			_drive(delta)
			return
		"circle":
			_circle(delta)
			return
		"follow":
			_follow(delta)
		"wander":
			_wander(delta)
	if is_moving():
		_play("walk", clampf(Vector2(velocity.x, velocity.z).length() / _walk_ref, 0.3, 2.5))
	else:
		_play(_rest_clip)


func _circle(delta: float) -> void:
	_angle += speed / maxf(radius, 1.0) * delta
	var p := _home + Vector3(cos(_angle) * radius, sin(_angle * 0.37) * 1.5, sin(_angle) * radius)
	var tangent := Vector3(-sin(_angle), 0.0, cos(_angle))
	global_position = p
	rotation.y = atan2(-tangent.x, -tangent.z)
	rotation.z = 0.25          # banked into the turn


func _follow(delta: float) -> void:
	if _leader == null or not is_instance_valid(_leader):
		_leader = null
		for n in get_tree().get_nodes_in_group("npcs"):
			if n.get("npc_id") == follow:
				_leader = n
				break
		if _leader == null:
			halt(delta)
			return
	# Heel: a little behind and to the left of the leader (leader forward is -Z).
	var b := _leader.global_transform.basis
	var heel := _leader.global_position + b.z * 1.1 - b.x * 0.7
	var gap := Vector2(heel.x - global_position.x, heel.z - global_position.z).length()
	if gap < 0.6 or not _leader.visible:
		halt(delta)
		turn_toward_yaw(_leader.rotation.y, delta)
		return
	walk_to(heel, clampf(gap * 1.3, 0.8, 4.0), delta)


func _wander(delta: float) -> void:
	if _pause > 0.0:
		_pause -= delta
		halt(delta)
		if _pause <= 0.0:
			_pick_target()
	elif walk_to(_target, speed, delta):
		_pause = _rng.randf_range(1.5, 5.0)


func _pick_target() -> void:
	var a := _rng.randf() * TAU
	var r := sqrt(_rng.randf()) * radius
	_target = _home + Vector3(cos(a) * r, 0.0, sin(a) * r)
