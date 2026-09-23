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
##
## Stealth (docs/STEALTH.md, tunables in data/stealth.json): `visibility` = posture x light x crowd (0 inside a
## hiding spot); `light_level` is sampled from the district's flame lights and the moon; `noise` = gait x the
## surface underfoot. Lean (Q / R, while still) moves the head, and the camera, out past a corner: guards then see
## only the head (cover 0.5). Hiding spots and benches (enter_spot / leave_spot), dragging a downed guard (hold E:
## start_drag / end_drag, half speed), throwing a stone (hold G to aim, release to throw).
## `sandbox` + `scripted`: a test player (scripts/stealth/stealth_smoke.gd) driven by the ai_* fields instead of
## the keyboard, outside the "player" group and free of Mission / GameState side effects.

const Perception := preload("res://scripts/stealth/perception.gd")
const Distraction := preload("res://scripts/stealth/distraction.gd")

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
var noise := 0.0          ## 0..~1.3, read by guards (gait x surface)
var visibility := 1.0     ## 0..1, multiplier on guard detection (posture x light x crowd; 0 hidden)
var light_level := 1.0    ## 0.15..1 light at the chest (flame lights + moon)
var surface := "cobbles"  ## ground underfoot (surface patches / collider meta)
var crowd_factor := 1.0   ## 0.35 walking in a crowd, 0.25 on a bench beside a townsman, else 1
var lean := 0.0           ## -1 left .. 1 right (smoothed)
var hidden_spot: Node3D = null   ## the hiding spot / bench the player is in, or null
var dragging: Node3D = null      ## the downed guard being dragged, or null
var aiming := false              ## "throw" held: arc preview

var sandbox := false      ## test world: not in group "player", no Mission / GameState side effects
var scripted := false     ## inputs from the ai_* fields
var ai_move := Vector3.ZERO      ## world-space wish direction (scripted)
var ai_crouch := false
var ai_sprint := false
var ai_lean := 0.0
var ai_drag_hold := false

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
var _watch: Node
var _sense_cd := 0.0
var _surface_cd := 0.0
var _crowd_cd := 0.0
var _ring_cd := 0.0
var _arc: MeshInstance3D
var _move_dir := Vector3.ZERO


func _ready() -> void:
	if not sandbox:
		add_to_group("player")
	_build_body()
	_build_camera()
	var args := OS.get_cmdline_user_args()
	for a in args:
		if a.begins_with("--shot=") and "--smoke" in args and not sandbox:
			_shot_walk = true
	if not sandbox:
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
	# Throw arc preview (only while aiming).
	_arc = MeshInstance3D.new()
	_arc.mesh = ImmediateMesh.new()
	_arc.top_level = true
	_arc.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var am := StandardMaterial3D.new()
	am.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	am.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	am.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	am.albedo_color = Color(0.9, 0.7, 0.4, 0.55)
	am.no_depth_test = true
	_arc.material_override = am
	_arc.visible = false
	add_child(_arc)


func camera() -> Camera3D:
	return _camera


func _mouse_sens() -> float:
	var s: Variant = GameState.get("settings")
	if s is Dictionary and (s as Dictionary).has("mouse_sens"):
		return MOUSE_SENS * float(s["mouse_sens"])
	return MOUSE_SENS


func _invert_y() -> bool:
	var s: Variant = GameState.get("settings")
	return s is Dictionary and bool((s as Dictionary).get("invert_y", false))


func _unhandled_input(event: InputEvent) -> void:
	if scripted:
		return
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
		if dragging == null and try_interact():
			get_viewport().set_input_as_handled()
	elif event.is_action_pressed("hide") and not event.is_echo():
		_toggle_hide()
	elif event.is_action_pressed("throw") and not event.is_echo():
		aiming = hidden_spot == null and dragging == null and health > 0
	elif event.is_action_released("throw"):
		if aiming:
			aiming = false
			throw_stone(_aim_velocity())
	elif event.is_action_pressed("attack") and not event.is_echo():
		if hidden_spot == null:
			attack()
	elif event.is_action_pressed("prone") and not event.is_echo():
		if hidden_spot == null:
			set_prone(not is_prone)


func _physics_process(delta: float) -> void:
	if _watch == null or not is_instance_valid(_watch):
		_watch = Perception.watch_of(self)
	_pivot.rotation = Vector3(_pitch, _yaw, 0)
	# In conversation the camera slides over the right shoulder so the other speaker is in view.
	var talk := Mission.dialogue_open() and not sandbox
	var shoulder := Vector3(cos(_yaw), 0.0, -sin(_yaw))
	var want_pivot := Vector3(0, 1.5, 0) + (shoulder * 0.75 if talk else Vector3.ZERO) + shoulder * lean * 0.55
	var want_arm := 2.3 if talk else 4.0
	if hidden_spot and hidden_spot.get("hides_player"):
		# peek out of the hiding place: the camera sits at the spot's peek point, nearly first person
		want_pivot = to_local(hidden_spot.point(hidden_spot.peek_point))
		want_arm = 0.35
	elif hidden_spot:
		want_arm = 3.2
	_pivot.position = _pivot.position.lerp(want_pivot, clampf(6.0 * delta, 0.0, 1.0))
	_arm.spring_length = lerpf(_arm.spring_length, want_arm, clampf(6.0 * delta, 0.0, 1.0))
	_attack_cd = maxf(0.0, _attack_cd - delta)
	_lock = maxf(0.0, _lock - delta)
	var frozen := _lock > 0.0 or (not sandbox and Mission.dialogue_blocking())

	if hidden_spot:
		_in_spot(delta)
		_update_interact_target()
		return

	var crouch_in: bool = ai_crouch if scripted else Input.is_action_pressed("crouch")
	var sprint_in: bool = ai_sprint if scripted else Input.is_action_pressed("sprint")
	if is_prone and not scripted and Input.is_action_just_pressed("crouch") and not frozen:
		set_prone(false)
	is_crouching = (crouch_in or is_prone) and not frozen
	is_sprinting = sprint_in and not is_crouching and not carrying and dragging == null and not frozen

	var wish := Vector3.ZERO
	if not frozen:
		if scripted:
			wish = Vector3(ai_move.x, 0, ai_move.z)
			if wish.length() > 1.0:
				wish = wish.normalized()
		else:
			var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
			var forward := -_pivot.global_transform.basis.z
			forward.y = 0
			forward = forward.normalized()
			var right := _pivot.global_transform.basis.x
			right.y = 0
			right = right.normalized()
			wish = (forward * -input.y + right * input.x)

	var speed := WALK_SPEED
	if is_prone:
		speed = WALK_SPEED * PRONE_FACTOR
	elif is_crouching:
		speed = CROUCH_SPEED
	elif is_sprinting:
		speed = SPRINT_SPEED
	if carrying:
		speed *= CARRY_FACTOR
	if dragging:
		speed *= float(_tv("drag.speed_factor", 0.5))

	var target := wish * speed
	velocity.x = move_toward(velocity.x, target.x, ACCEL * delta)
	velocity.z = move_toward(velocity.z, target.z, ACCEL * delta)
	if not is_on_floor():
		velocity.y -= GRAVITY * delta
	else:
		velocity.y = 0
	move_and_slide()

	var moving := wish.length() > 0.1
	_move_dir = wish.normalized() if moving else Vector3.ZERO
	if moving:
		_figure.rotation.y = lerp_angle(_figure.rotation.y, atan2(-wish.x, -wish.z), 10 * delta)
	var planar := Vector2(velocity.x, velocity.z).length()
	_animate(planar, moving, delta)

	# Lean out past a corner (only standing still, not prone): the head and camera shift sideways.
	var lean_in: float = ai_lean if scripted else (Input.get_action_strength("lean_right") - Input.get_action_strength("lean_left"))
	if moving or is_prone or frozen or dragging:
		lean_in = 0.0
	lean = move_toward(lean, clampf(lean_in, -1.0, 1.0), delta * 6.0)
	var fig_right := _figure.global_transform.basis.x
	var side := signf(_cam_right().dot(fig_right)) if absf(_cam_right().dot(fig_right)) > 0.2 else 1.0
	_figure.rotation.z = -lean * 0.28 * side

	# Crouch / prone: shrink the collision height so guards' rays are more likely blocked by low cover.
	var h := 0.7 if is_prone else (1.0 if is_crouching else 1.8)
	_shape.shape.height = h
	_shape.position.y = h * 0.5

	if dragging:
		_update_drag(delta)
	_update_senses(delta, moving)
	_update_aim()
	_update_interact_target()


## Inside a hiding spot or on a bench: no movement; visibility 0 (bench: sitting x light x crowd).
func _in_spot(delta: float) -> void:
	velocity = Vector3.ZERO
	global_position = hidden_spot.point(hidden_spot.inner_point)
	is_sprinting = false
	lean = 0.0
	_figure.rotation.z = 0.0
	if hidden_spot.get("shows_figure"):
		_figure.visible = true
		var yaw: float = hidden_spot.global_rotation.y
		_figure.global_rotation.y = lerp_angle(_figure.global_rotation.y, yaw, 8.0 * delta)
		Assets.play(_figure, "sit_idle" if hidden_spot.kind == "bench" else "crouch_hide")
	else:
		_figure.visible = false
	_update_senses(delta, false)
	noise = 0.0


func _cam_right() -> Vector3:
	var r := _pivot.global_transform.basis.x
	r.y = 0.0
	return r.normalized()


func _tv(path: String, fallback: Variant) -> Variant:
	return _watch.tv(path, fallback) if _watch and is_instance_valid(_watch) else Perception.tg(path, fallback)


## 0 standing, 1 crouching, 2 prone, 3 sitting (bench).
func posture() -> int:
	if hidden_spot and hidden_spot.get("kind") == "bench":
		return 3
	if is_prone:
		return 2
	if is_crouching:
		return 1
	return 0


func _update_senses(delta: float, moving: bool) -> void:
	_sense_cd -= delta
	if _sense_cd <= 0.0:
		_sense_cd = 1.0 / maxf(float(_tv("light.sample_hz", 10.0)), 1.0)
		light_level = Perception.light_at(self, chest_position(), [get_rid()])
	_surface_cd -= delta
	if _surface_cd <= 0.0:
		_surface_cd = 0.2
		surface = Perception.surface_at(self, global_position, [get_rid()])
	_crowd_cd -= delta
	if _crowd_cd <= 0.0:
		_crowd_cd = 0.25
		crowd_factor = _crowd()
	# Noise: the gait, times the surface underfoot. Prone halves the crouch noise.
	var gait := 0.0
	if moving:
		if is_prone:
			gait = float(_tv("noise.prone", 0.075))
		elif is_crouching:
			gait = float(_tv("noise.crouch", 0.15))
		elif is_sprinting:
			gait = float(_tv("noise.sprint", 1.0))
		else:
			gait = float(_tv("noise.walk", 0.45))
	noise = gait * Perception.surface_noise(surface)
	if dragging and moving:
		noise = maxf(noise, 0.3 * Perception.surface_noise(surface))
	# Visibility: posture x light x crowd; nothing at all inside a hiding place.
	var pk: String = ["stand", "crouch", "prone", "sit"][posture()]
	visibility = float(_tv("posture." + pk, 1.0)) * light_level * crowd_factor
	if hidden_spot and hidden_spot.get("hides_player"):
		visibility = 0.0
	# Loud footsteps show a ring on the ground (feedback only; guards hear `noise` directly).
	_ring_cd -= delta
	if noise >= 0.9 and _ring_cd <= 0.0 and _watch:
		_ring_cd = float(_tv("rings.sprint_every", 0.55))
		_watch.emit_sound(global_position, noise * 0.6, "step", false, true, false)


## Crowd blending: inside a group of townsfolk (standing, or walking the same way), not crouched, sprinting or
## armed; or on a bench beside a townsman.
func _crowd() -> float:
	var pop: Node = null
	for p in get_tree().get_nodes_in_group("population"):
		if p.get_parent() is Node3D and Perception.same_world(p.get_parent(), self):
			pop = p
			break
	if pop == null or not pop.has_method("crowd_count"):
		return 1.0
	if posture() == 3:
		var n: int = pop.crowd_count(global_position, Vector3.ZERO, float(_tv("crowd.bench_npc_radius", 1.8)))
		return float(_tv("crowd.bench_factor", 0.25)) if n >= 1 else 1.0
	if posture() != 0 or is_sprinting or is_fighting() or aiming or dragging:
		return 1.0
	var c: int = pop.crowd_count(global_position, _move_dir, float(_tv("crowd.radius", 2.5)))
	return float(_tv("crowd.factor", 0.35)) if c >= int(_tv("crowd.min_count", 3)) else 1.0


func head_position() -> Vector3:
	var h := 0.3 if is_prone else (0.75 if is_crouching else 1.55)
	if posture() == 3:
		h = 1.15
	return global_position + Vector3(0, h, 0) + _cam_right() * lean * float(_tv("lean.offset", 0.45))


## The torso point guards test for cover (does not lean).
func chest_position() -> Vector3:
	return global_position + Vector3(0, 0.25 if is_prone else (0.5 if is_crouching else 1.05), 0)


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
		elif dragging:
			Assets.play_move(_figure, "walk_carry", planar)
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
	if hidden_spot:
		best = hidden_spot
		best_d = 0.0
	elif sandbox or not Mission.dialogue_blocking():
		# stealth props (hiding spots, lamps, barrels, doors: meta "low_priority") only win when no mission person or
		# prop is in reach, so they never steal a conversation or a pickup
		var lo: Node3D = null
		var lo_d := INF
		for n in get_tree().get_nodes_in_group("interactable"):
			var ia := n as Node3D
			if ia == null or not ia.has_method("is_available") or not ia.is_available():
				continue
			if dragging and ia.get_parent() == dragging:
				continue
			var to := ia.global_position - global_position
			if absf(to.y) > 2.0:
				continue
			var d := Vector2(to.x, to.z).length()
			if d > INTERACT_REACH or not _in_front(ia.global_position, 0.8):
				continue
			if ia.has_meta("low_priority"):
				if d < lo_d:
					lo = ia
					lo_d = d
			elif d < best_d:
				best = ia
				best_d = d
		if best == null:
			best = lo
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
	if sandbox:
		return interact_target.on_interact(self)
	return Mission.interact(self, interact_target)


# ------------------------------------------------------------------ combat (non-lethal)

func is_fighting() -> bool:
	return Time.get_ticks_msec() - _last_swing_ms < 1500


func attack() -> String:
	if _attack_cd > 0.0 or _lock > 0.0 or (not sandbox and Mission.dialogue_blocking()) or hidden_spot or dragging:
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
			if Mission.is_active() and not sandbox:
				Mission.on_takedown(target, false)
		return "takedown"
	if target is Guard:
		Assets.play_action(_figure, "attack_swing" if randf() < 0.7 else "attack_thrust")
		target.take_hit(self)
		return "hit"
	if not sandbox:
		Mission.message.emit("He would shout for the watch. Come at him from behind.", 3.0)
	return "refused"


func _attack_target() -> Node3D:
	var best: Node3D = null
	var best_d := INF
	var pool: Array = get_tree().get_nodes_in_group("guards") + get_tree().get_nodes_in_group("takedown")
	if _watch and is_instance_valid(_watch):
		for g in _watch.guards():
			if not g in pool:
				pool.append(g)
	for n in pool:
		var t := n as Node3D
		if t == null or not t.is_visible_in_tree() or (t.has_method("is_downed") and t.is_downed()) or not Perception.same_world(t, self):
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
	if hidden_spot:
		leave_spot(true)
	if dragging:
		end_drag(null)
	if sandbox:
		return
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


# ------------------------------------------------------------------ hiding spots and benches

## Get into a hiding spot (or sit on a bench). Returns true if it worked.
func enter_spot(spot: Node3D) -> bool:
	if hidden_spot or dragging or health <= 0 or carrying and spot.get("hides_player"):
		return false
	set_prone(false)
	is_prone = false
	hidden_spot = spot
	aiming = false
	velocity = Vector3.ZERO
	_shape.disabled = true
	global_position = spot.point(spot.inner_point)
	reset_physics_interpolation()
	spot.on_entered(self)
	return true


## Out again, at the spot's exit point. `pulled`: a guard dragged the player out.
func leave_spot(pulled := false) -> void:
	if hidden_spot == null:
		return
	var spot := hidden_spot
	hidden_spot = null
	_shape.disabled = false
	_figure.visible = true
	global_position = spot.point(spot.exit_point)
	var out: Vector3 = spot.point(spot.exit_point) - spot.global_position
	if out.length() > 0.1:
		_figure.rotation.y = atan2(-out.x, -out.z)
	reset_physics_interpolation()
	spot.on_left(self)
	if pulled:
		_lock = 0.8
		Assets.play_action(_figure, "grabbed")


func _toggle_hide() -> void:
	if hidden_spot:
		leave_spot()
		return
	var best: Node3D = null
	var best_d := INTERACT_REACH
	for s in get_tree().get_nodes_in_group("hiding_spot"):
		var sp := s as Node3D
		if sp == null or not Perception.same_world(sp, self) or sp.get("occupant") != null:
			continue
		var d := sp.global_position.distance_to(global_position)
		if d < best_d:
			best_d = d
			best = sp
	if best:
		enter_spot(best)


# ------------------------------------------------------------------ dragging a downed guard

func start_drag(g: Node3D) -> bool:
	if dragging or hidden_spot or carrying or not g.has_method("is_downed") or not g.is_downed() or g.get("hidden_in") != null:
		return false
	dragging = g
	set_prone(false)
	is_prone = false
	return true


func _drag_held() -> bool:
	return ai_drag_hold if scripted else Input.is_action_pressed("interact")


func _update_drag(_delta: float) -> void:
	if not is_instance_valid(dragging) or not dragging.is_downed():
		dragging = null
		return
	var back := -_body_dir()
	var want := global_position + back * 0.95
	dragging.global_position = Vector3(want.x, global_position.y, want.z)
	dragging.global_rotation.y = _figure.global_rotation.y + PI
	if not _drag_held():
		end_drag(null)


## Let go of the body: into `spot` (or the nearest free hiding spot within drag.hide_radius), else on the ground.
func end_drag(spot: Node3D = null) -> bool:
	if dragging == null:
		return false
	var g := dragging
	dragging = null
	if spot == null:
		var best_d := float(_tv("drag.hide_radius", 2.2))
		for s in get_tree().get_nodes_in_group("hiding_spot"):
			var sp := s as Node3D
			if sp == null or not Perception.same_world(sp, self) or not sp.get("takes_body") or sp.get("body") != null:
				continue
			var d := sp.global_position.distance_to(g.global_position)
			if d < best_d:
				best_d = d
				spot = sp
	if spot and is_instance_valid(g):
		return spot.stash_body(g)
	return false


# ------------------------------------------------------------------ throwing

func _hand() -> Vector3:
	return global_position + Vector3(0, 1.55, 0) + _look_dir() * 0.35


func _aim_velocity() -> Vector3:
	var f := -_camera.global_transform.basis.z
	var dir := (f + Vector3(0, 0.35, 0)).normalized()
	return dir * float(_tv("distractions.throw_speed", 11.0))


## Throw a stone with velocity `vel`. Returns the stone.
func throw_stone(vel: Vector3) -> Node3D:
	if health <= 0 or hidden_spot:
		return null
	var st := Distraction.Stone.new()
	st.velocity = vel
	st.loudness = float(_tv("distractions.throw_loudness", 0.9))
	st.exclude = [get_rid()]
	get_parent().add_child(st)
	st.global_position = _hand()
	_figure.rotation.y = atan2(-vel.x, -vel.z)
	Assets.play_action(_figure, "attack_swing", 1.5)
	_arc.visible = false
	return st


## Scripted throw at a point (smoke, missions).
func throw_at(point: Vector3) -> Node3D:
	return throw_stone(Distraction.launch_velocity(_hand(), point, float(_tv("distractions.throw_speed", 11.0))))


func _update_aim() -> void:
	if not aiming:
		_arc.visible = false
		return
	var im := _arc.mesh as ImmediateMesh
	im.clear_surfaces()
	var p := _hand()
	var v := _aim_velocity()
	var space := get_world_3d().direct_space_state
	var pts := PackedVector3Array([p])
	for i in 60:
		var nv := v + Vector3(0, -Distraction.Stone.GRAVITY, 0) * 0.04
		var np := p + (v + nv) * 0.5 * 0.04
		var q := PhysicsRayQueryParameters3D.create(p, np)
		q.exclude = [get_rid()]
		var hit := space.intersect_ray(q)
		if not hit.is_empty():
			pts.append(hit["position"])
			break
		pts.append(np)
		p = np
		v = nv
	if pts.size() < 2:
		return
	im.surface_begin(Mesh.PRIMITIVE_LINES)
	for i in range(0, pts.size() - 1, 2):
		im.surface_add_vertex(pts[i])
		im.surface_add_vertex(pts[i + 1])
	var end := pts[-1] + Vector3(0, 0.03, 0)
	for k in 16:
		var a0 := TAU * k / 16.0
		var a1 := TAU * (k + 1) / 16.0
		im.surface_add_vertex(end + Vector3(cos(a0), 0, sin(a0)) * 0.35)
		im.surface_add_vertex(end + Vector3(cos(a1), 0, sin(a1)) * 0.35)
	im.surface_end()
	_arc.global_transform = Transform3D.IDENTITY
	_arc.visible = true
