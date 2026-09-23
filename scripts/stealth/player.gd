extends CharacterBody3D
class_name Player
## Third-person stealth controller. Builds its own body, camera rig and light probe at runtime
## so the scene file stays trivial until Blender assets arrive.
##
## Mission hooks: `interact` uses the nearest available node in group "interactable" within reach and in front
## (Mission.interact); `carrying` (a bundle: slower, no sprint) and `disguised` (guards read you as a townsman,
## see guard.gd) are set by the mission; `attack` is a rear takedown on an unaware guard or the informer, or
## a cudgel swing in a fair fight. Health 3; at 0 the watch has beaten you.
##
## Stances: crouch (hold C / Ctrl), prone (toggle Z: capsule 0.7 m, 0.35x speed, half the crouch noise). Crouched,
## still and within 0.5 m of a wall the figure huddles against it (crouch_hide). Animation comes from the shared
## library (Assets.play / play_move / play_action, see docs/ANIMATION.md).

const WALK_SPEED := 3.0
const SPRINT_SPEED := 6.0
const CROUCH_SPEED := 1.6
const CARRY_FACTOR := 0.7         ## walking speed multiplier while carrying
const ACCEL := 12.0
const MOUSE_SENS := 0.0025
const GRAVITY := 18.0
const INTERACT_REACH := 2.5
const MAX_HEALTH := 3
const ATTACK_COOLDOWN := 0.6
const ATTACK_REACH := 1.6
const TAKEDOWN_REACH := 1.5
const TAKEDOWN_SECS := 60.0
const PRONE_FACTOR := 0.35        ## prone crawl speed as a fraction of WALK_SPEED
const HIDE_WALL_DIST := 0.5       ## crouch_hide when a wall is this close to the body (m)

var is_crouching := false
var is_sprinting := false
var is_prone := false     ## toggled with "prone" (Z); guards treat it like crouching
var is_hiding := false    ## crouched, still, back to a wall
var noise := 0.0          ## 0..1, read by guards
var visibility := 1.0     ## 0..1, multiplier on guard detection (crouch, shadow)

var carrying := false:
	set(v):
		carrying = v
		_update_props()
var disguised := false:
	set(v):
		disguised = v
		_update_props()
var health := MAX_HEALTH
var interact_target: Node3D = null    ## the interactable the prompt refers to, or null
var prompt_text := ""                 ## "E  talk to ..." while a target is in reach

var _yaw := 0.0
var _pitch := -0.25
var _pivot: Node3D
var _arm: SpringArm3D
var _camera: Camera3D
var _figure: Node3D
var _shape: CollisionShape3D
var _carry_prop: Node3D
var _cloak: MeshInstance3D
var _attack_cd := 0.0
var _last_swing_ms := -100000
var _lock := 0.0                      ## seconds of no control (takedown, being struck)
var _was_crouching := false
var _wall_check := 0.0
var _wall_normal := Vector3.ZERO
var _shot_walk := false               ## smoke screenshots: walk in place so the close-up shows the walk cycle


func _ready() -> void:
	add_to_group("player")
	_build_body()
	_build_camera()
	var args := OS.get_cmdline_user_args()
	for a in args:
		if a.begins_with("--shot=") and "--smoke" in args:
			_shot_walk = true
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _build_body() -> void:
	_shape = CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.35
	cap.height = 1.8
	_shape.shape = cap
	_shape.position.y = 0.9
	add_child(_shape)

	_figure = Assets.character(GameState.figure_name())
	if _figure == null:
		_figure = Node3D.new()
		var mi := MeshInstance3D.new()
		var m := CapsuleMesh.new()
		m.radius = 0.35
		m.height = 1.8
		mi.mesh = m
		mi.position.y = 0.9
		_figure.add_child(mi)
	_figure.set_meta("anim_role", "player")
	add_child(_figure)


func _build_camera() -> void:
	_pivot = Node3D.new()
	_pivot.position.y = 1.5
	add_child(_pivot)
	_arm = SpringArm3D.new()
	_arm.spring_length = 4.0
	_arm.margin = 0.2
	_arm.add_excluded_object(get_rid())
	_pivot.add_child(_arm)
	_camera = Camera3D.new()
	_camera.fov = 70
	_camera.current = true
	_arm.add_child(_camera)


func _mouse_sens() -> float:
	var s: Variant = GameState.get("settings")
	if s is Dictionary and (s as Dictionary).has("mouse_sens"):
		return MOUSE_SENS * float(s["mouse_sens"])
	return MOUSE_SENS


func _invert_y() -> bool:
	var s: Variant = GameState.get("settings")
	return s is Dictionary and bool((s as Dictionary).get("invert_y", false))


func _unhandled_input(event: InputEvent) -> void:
	var talking := Mission.dialogue_blocking()
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED and not talking:
		var sens := _mouse_sens()
		_yaw -= event.relative.x * sens
		_pitch = clampf(_pitch - event.relative.y * sens * (-1.0 if _invert_y() else 1.0), -1.2, 0.6)
	if event.is_action_pressed("toggle_mouse"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED else Input.MOUSE_MODE_CAPTURED
	if talking:
		return
	if event.is_action_pressed("interact") and not event.is_echo():
		if try_interact():
			get_viewport().set_input_as_handled()
	elif event.is_action_pressed("attack") and not event.is_echo():
		attack()
	elif event.is_action_pressed("prone") and not event.is_echo():
		set_prone(not is_prone)


func _physics_process(delta: float) -> void:
	_pivot.rotation = Vector3(_pitch, _yaw, 0)
	# In conversation the camera slides over the right shoulder so the other speaker is in view.
	var talk := Mission.dialogue_open()
	var shoulder := Vector3(cos(_yaw), 0.0, -sin(_yaw))
	var want_pivot := Vector3(0, 1.5, 0) + (shoulder * 0.75 if talk else Vector3.ZERO)
	_pivot.position = _pivot.position.lerp(want_pivot, clampf(6.0 * delta, 0.0, 1.0))
	_arm.spring_length = lerpf(_arm.spring_length, 2.3 if talk else 4.0, clampf(6.0 * delta, 0.0, 1.0))
	_attack_cd = maxf(0.0, _attack_cd - delta)
	_lock = maxf(0.0, _lock - delta)
	var frozen := _lock > 0.0 or Mission.dialogue_blocking()

	if is_prone and Input.is_action_just_pressed("crouch") and not frozen:
		set_prone(false)
	is_crouching = (Input.is_action_pressed("crouch") or is_prone) and not frozen
	is_sprinting = Input.is_action_pressed("sprint") and not is_crouching and not carrying and not frozen

	var input := Vector2.ZERO if frozen else Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var forward := -_pivot.global_transform.basis.z
	forward.y = 0
	forward = forward.normalized()
	var right := _pivot.global_transform.basis.x
	right.y = 0
	right = right.normalized()
	var wish := (forward * -input.y + right * input.x)

	var speed := WALK_SPEED
	if is_prone:
		speed = WALK_SPEED * PRONE_FACTOR
	elif is_crouching:
		speed = CROUCH_SPEED
	elif is_sprinting:
		speed = SPRINT_SPEED
	if carrying:
		speed *= CARRY_FACTOR

	var target := wish * speed
	velocity.x = move_toward(velocity.x, target.x, ACCEL * delta)
	velocity.z = move_toward(velocity.z, target.z, ACCEL * delta)
	if not is_on_floor():
		velocity.y -= GRAVITY * delta
	else:
		velocity.y = 0
	move_and_slide()

	var moving := wish.length() > 0.1
	if moving:
		_figure.rotation.y = lerp_angle(_figure.rotation.y, atan2(-wish.x, -wish.z), 10 * delta)
	var planar := Vector2(velocity.x, velocity.z).length()
	_animate(planar, moving, delta)

	# Crouch / prone: shrink the collision height so guards' rays are more likely blocked by low cover.
	var h := 0.7 if is_prone else (1.0 if is_crouching else 1.8)
	_shape.shape.height = h
	_shape.position.y = h * 0.5

	# Noise & visibility feed guard perception. Prone halves the crouch noise.
	if not moving:
		noise = 0.0
	elif is_prone:
		noise = 0.075
	elif is_crouching:
		noise = 0.15
	elif is_sprinting:
		noise = 1.0
	else:
		noise = 0.45
	visibility = 0.35 if is_prone else (0.5 if is_crouching else 1.0)

	_update_interact_target()


func head_position() -> Vector3:
	return global_position + Vector3(0, 0.3 if is_prone else (0.6 if is_crouching else 1.5), 0)


func set_prone(on: bool) -> void:
	if on == is_prone or health <= 0:
		return
	is_prone = on
	is_hiding = false
	if Vector2(velocity.x, velocity.z).length() < 0.3:
		Assets.play_action(_figure, "crouch_to_prone" if on else "prone_to_crouch")


# ------------------------------------------------------------------ animation

const _TRANSITIONS := ["stand_to_crouch", "crouch_to_stand", "crouch_to_prone", "prone_to_crouch"]


## Picks the stance / locomotion clip. One-shot actions (attack, hit, fall) are handled by Assets.play_action and
## win until they end; stance transitions are dropped as soon as the player moves.
func _animate(planar: float, moving: bool, delta: float) -> void:
	if health <= 0:
		return
	if moving and Assets.action_clip(_figure) in _TRANSITIONS:
		Assets.clear_action(_figure)
	# stand <-> crouch transitions while standing still
	var crouch_only := is_crouching and not is_prone
	if crouch_only != _was_crouching and not is_prone and planar < 0.3 and _lock <= 0.0 and not Assets.is_action(_figure):
		Assets.play_action(_figure, "stand_to_crouch" if crouch_only else "crouch_to_stand")
	_was_crouching = crouch_only
	is_hiding = false
	if planar > 0.3 and _lock <= 0.0:
		if is_prone:
			Assets.play_move(_figure, "prone_crawl", planar)
		elif is_crouching:
			Assets.play_move(_figure, "sneak", planar)
		elif carrying:
			Assets.play_move(_figure, "walk_carry", planar)
		elif is_sprinting:
			Assets.play_move(_figure, "run", planar)
		elif planar < 1.6:
			Assets.play_move(_figure, "walk", planar)
		else:
			Assets.play_move(_figure, "walk_fast", planar)
		return
	if is_prone:
		Assets.play(_figure, "prone_idle")
	elif is_crouching:
		_wall_check -= delta
		if _wall_check <= 0.0:
			_wall_check = 0.2
			_wall_normal = _near_wall()
		if _wall_normal != Vector3.ZERO:
			is_hiding = true
			_figure.rotation.y = lerp_angle(_figure.rotation.y, atan2(-_wall_normal.x, -_wall_normal.z), 8.0 * delta)
			Assets.play(_figure, "crouch_hide")
		else:
			Assets.play(_figure, "crouch_idle")
	elif _shot_walk and not Mission.dialogue_blocking():
		Assets.play_move(_figure, "walk_fast", 2.2)
	else:
		Assets.play(_figure, "idle")


## Normal of the nearest wall within HIDE_WALL_DIST of the capsule (8 rays at knee height), or ZERO.
func _near_wall() -> Vector3:
	var space := get_world_3d().direct_space_state
	var from := global_position + Vector3(0, 0.5, 0)
	var reach := 0.35 + HIDE_WALL_DIST
	var best := INF
	var normal := Vector3.ZERO
	for i in 8:
		var a := TAU * i / 8.0
		var q := PhysicsRayQueryParameters3D.create(from, from + Vector3(sin(a), 0, cos(a)) * reach)
		q.exclude = [get_rid()]
		var hit := space.intersect_ray(q)
		if hit.is_empty() or hit.get("collider") is CharacterBody3D:
			continue
		var n: Vector3 = hit["normal"]
		if absf(n.y) > 0.5:
			continue
		var d := from.distance_to(hit["position"])
		if d < best:
			best = d
			normal = Vector3(n.x, 0, n.z).normalized()
	return normal


func rotate_camera(euler: Vector3) -> void:
	_pitch = euler.x
	_yaw = euler.y
	_pivot.rotation = Vector3(_pitch, _yaw, 0)


## Turn camera and body toward a point (mission scripting, smoke tests).
func face_point(p: Vector3) -> void:
	var d := p - global_position
	var yaw := atan2(-d.x, -d.z)
	rotate_camera(Vector3(-0.22, yaw, 0))
	_figure.rotation.y = yaw


# ------------------------------------------------------------------ interaction

## Horizontal facing used for "in front": the camera's look direction (third person).
func _look_dir() -> Vector3:
	var f := -_pivot.global_transform.basis.z
	f.y = 0.0
	return f.normalized()


func _body_dir() -> Vector3:
	var f := -_figure.global_transform.basis.z
	f.y = 0.0
	return f.normalized()


func _in_front(p: Vector3, near_ok: float) -> bool:
	var to := p - global_position
	to.y = 0.0
	if to.length() < near_ok:
		return true
	to = to.normalized()
	return to.dot(_look_dir()) > 0.3 or to.dot(_body_dir()) > 0.3


func _update_interact_target() -> void:
	var best: Node3D = null
	var best_d := INF
	if not Mission.dialogue_blocking():
		for n in get_tree().get_nodes_in_group("interactable"):
			var ia := n as Node3D
			if ia == null or not ia.has_method("is_available") or not ia.is_available():
				continue
			var to := ia.global_position - global_position
			if absf(to.y) > 2.0:
				continue
			var d := Vector2(to.x, to.z).length()
			if d > INTERACT_REACH or d >= best_d or not _in_front(ia.global_position, 0.8):
				continue
			best = ia
			best_d = d
	if best != interact_target:
		if interact_target and is_instance_valid(interact_target):
			interact_target.set_highlight(false)
		interact_target = best
		if best:
			best.set_highlight(true)
	prompt_text = "E   " + str(best.get_prompt()) if best else ""


## Use the current target. Returns true if something happened.
func try_interact() -> bool:
	_update_interact_target()
	if interact_target == null:
		return false
	return Mission.interact(self, interact_target)


# ------------------------------------------------------------------ combat (non-lethal)

func is_fighting() -> bool:
	return Time.get_ticks_msec() - _last_swing_ms < 1500


func attack() -> String:
	if _attack_cd > 0.0 or _lock > 0.0 or Mission.dialogue_blocking():
		return ""
	_attack_cd = ATTACK_COOLDOWN
	_last_swing_ms = Time.get_ticks_msec()
	var target := _attack_target()
	if target == null:
		Assets.play_action(_figure, "attack_swing")
		return "miss"
	var to := target.global_position - global_position
	_figure.rotation.y = atan2(-to.x, -to.z)
	var unaware: bool = target.has_method("is_unaware_of") and target.is_unaware_of(self, TAKEDOWN_REACH)
	if not target.has_method("is_unaware_of"):
		unaware = _behind(target) and Vector2(to.x, to.z).length() <= TAKEDOWN_REACH
	if unaware:
		_lock = 1.4
		velocity = Vector3.ZERO
		Assets.play_action(_figure, "takedown")
		if target is Guard:
			target.knock_down(TAKEDOWN_SECS, false)
		else:
			target.knock_down(TAKEDOWN_SECS)
			if Mission.is_active():
				Mission.on_takedown(target, false)
		return "takedown"
	if target is Guard:
		Assets.play_action(_figure, "attack_swing" if randf() < 0.7 else "attack_thrust")
		target.take_hit(self)
		return "hit"
	Mission.message.emit("He would shout for the watch. Come at him from behind.", 3.0)
	return "refused"


func _attack_target() -> Node3D:
	var best: Node3D = null
	var best_d := INF
	var pool: Array = get_tree().get_nodes_in_group("guards") + get_tree().get_nodes_in_group("takedown")
	for n in pool:
		var t := n as Node3D
		if t == null or not t.is_visible_in_tree() or (t.has_method("is_downed") and t.is_downed()):
			continue
		var to := t.global_position - global_position
		var d := Vector2(to.x, to.z).length()
		if d > ATTACK_REACH or absf(to.y) > 1.5 or d >= best_d or not _in_front(t.global_position, 0.6):
			continue
		best = t
		best_d = d
	return best


func _behind(t: Node3D) -> bool:
	var to := global_position - t.global_position
	to.y = 0.0
	var fwd := -t.global_transform.basis.z
	fwd.y = 0.0
	return rad_to_deg(fwd.angle_to(to)) > 110.0


## Struck by the watch (musket butt).
func take_hit(from: Node3D) -> void:
	if health <= 0:
		return
	health -= 1
	_lock = 0.35
	if from:
		var push := global_position - from.global_position
		push.y = 0.0
		velocity += push.normalized() * 3.0
		var from_behind := _body_dir().dot(-push.normalized()) < -0.2
		Assets.play_action(_figure, "hit_react_back" if from_behind else "hit_react")
	if health <= 0:
		is_prone = false
		Assets.play_action(_figure, "knocked_down", 1.0, true)
	Mission.message.emit("Struck by a musket butt! (%d of %d)" % [health, MAX_HEALTH], 1.5)
	if health <= 0:
		if Mission.is_active():
			Mission.fail("Beaten by the watch")
		else:
			GameState.end_night(false)


# ------------------------------------------------------------------ carried bundle and cloak

func _update_props() -> void:
	if _figure == null:
		return
	if carrying and _carry_prop == null:
		_carry_prop = preload("res://scripts/mission/props.gd").bundle()
		_carry_prop.position = Vector3(0, 1.02, 0.2)      # slung on the back, where the camera sees it
		_carry_prop.rotation.x = -0.25
		_carry_prop.scale = Vector3.ONE * 0.85
		_figure.add_child(_carry_prop)
	elif not carrying and _carry_prop:
		_carry_prop.queue_free()
		_carry_prop = null
	if disguised and _cloak == null:
		_cloak = MeshInstance3D.new()
		var cm := CylinderMesh.new()
		cm.top_radius = 0.2
		cm.bottom_radius = 0.44
		cm.height = 1.2
		cm.radial_segments = 20
		_cloak.mesh = cm
		var mat := StandardMaterial3D.new()
		mat.albedo_color = Color(0.1, 0.09, 0.12)
		mat.roughness = 0.95
		_cloak.material_override = mat
		_cloak.position.y = 0.88
		_figure.add_child(_cloak)
	elif not disguised and _cloak:
		_cloak.queue_free()
		_cloak = null
