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
## Kit (scripts/stealth/kit.gd, child `kit`): one current item ([ / ] or the wheel); F / LMB strikes with the
## current weapon (knife slash, cudgel, a picked-up musket, the pistol fires), RMB is the item's second use (knife:
## parry, pistol: aim, a throwable: aim and throw), G always aims the current / last throwable, X toggles lethal
## knife takedowns. Throwables (stones, coins, bottles, food, smoke and flash charges) fly distraction.gd's Stone.
## Traversal (scripts/stealth/traversal.gd, `trav`): Space vaults, mantles, hangs, climbs; Ctrl drops; sprint + Ctrl
## slides; falls roll or stumble. Camera modes THIRD / SHOULDER (aiming) / FIRST (V while aiming, and the close
## actions of scripts/stealth/fp_view.gd: keyhole, listening, lock-picking, pocket-picking) blend in 0.25 s.
## `sandbox` + `scripted`: a test player (scripts/stealth/stealth_smoke.gd) driven by the ai_* fields instead of
## the keyboard, outside the "player" group and free of Mission / GameState side effects.

const Perception := preload("res://scripts/stealth/perception.gd")
const Distraction := preload("res://scripts/stealth/distraction.gd")
const KitScript := preload("res://scripts/stealth/kit.gd")
const Traversal := preload("res://scripts/stealth/traversal.gd")
const Pickup := preload("res://scripts/stealth/pickup.gd")
const FpView := preload("res://scripts/stealth/fp_view.gd")
const Verbs := preload("res://scripts/stealth/verbs.gd")

enum CamMode { THIRD, SHOULDER, FIRST }
const CAM_BLEND := 0.25            ## seconds for a camera mode change
const HEAD_WORDS := ["head", "hat", "hair", "eye", "brow", "lash", "teeth", "tongue", "beard", "wig", "tricorn"]

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
var throw_kind := "stone"        ## what the current aim throws
var pistol_aim := false          ## RMB with the pistol: shoulder (or first-person) aim
var parrying := false            ## RMB held with the knife
var parries := 0
var fp_aim := false              ## V: aim in first person
var cam_mode: int = CamMode.THIRD
var kit: Node                    ## scripts/stealth/kit.gd
var trav                         ## scripts/stealth/traversal.gd
var fp: CanvasLayer = null       ## the running first-person session (fp_view.gd Session), or null
var last_fp_result := ""         ## how the last one ended: ok | fail | done
var ai_jump := false             ## scripted: Space this frame (consumed)
var ai_drop := false             ## scripted: drop from a hang this frame (consumed)
var ai_interact_hold := false    ## scripted: E held (keyhole / listen)
var ai_tension := false          ## scripted: lock-pick tension held
var ai_tap := false              ## scripted: lock-pick strike this frame (consumed)

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
var _parry_ms := -100000
var _hand_prop: Node3D
var _hand_item := ""
var _seized_by: Node = null
var _scan_cd := 0.0
var _head_meshes: Array = []
var _head_hidden := false
var _slide_prev_sprint := false
static var _kit_smoke_started := false


func _ready() -> void:
	if not sandbox:
		add_to_group("player")
	_build_body()
	_build_camera()
	kit = KitScript.new()
	kit.player = self
	kit.sandbox = sandbox
	add_child(kit)
	kit.night_start()
	kit.changed.connect(_update_hand_prop)
	trav = Traversal.new(self)
	_update_hand_prop.call_deferred()
	var args := OS.get_cmdline_user_args()
	for a in args:
		if a.begins_with("--shot=") and "--smoke" in args and not sandbox:
			_shot_walk = true
		if a.begins_with("--fight-shot=") and not sandbox and not _fight_started:
			_fight_started = true
			Player._fight_shots(a.trim_prefix("--fight-shot="))
		if a.begins_with("--walk-shot=") and not sandbox and not _fight_started:
			_fight_started = true
			Player._walk_shots(a.trim_prefix("--walk-shot="))
	if not sandbox:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		get_tree().create_timer(2.0, false).timeout.connect(_dress_world)
		if "--smoke" in args and not _kit_smoke_started:
			_kit_smoke_started = true
			var ks: Node = load("res://scripts/stealth/kit_smoke.gd").new()
			ks.name = "KitSmoke"
			get_tree().root.add_child.call_deferred(ks)


## Once the district is up: loose stones and bottles on the street, wares on the food stalls, keyhole / listen /
## lock / pocket spots (fp_view.gd).
func _dress_world() -> void:
	if not is_inside_tree():
		return
	var world := get_parent() as Node3D
	var piles := Pickup.populate(world, global_position)
	var wares := Pickup.attach_vendors(world)
	var spots := FpView.attach_all(world)
	var verbs := Verbs.attach_all(world)
	if "--smoke" in OS.get_cmdline_user_args():
		print("[smoke] kit world pickups=%d wares=%d fp_spots=%d verbs=%d" % [piles, wares, spots, verbs])


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
	if fp:
		return
	if event.is_action_pressed("interact") and not event.is_echo():
		if dragging == null and try_interact():
			get_viewport().set_input_as_handled()
	elif event.is_action_pressed("hide") and not event.is_echo():
		_toggle_hide()
	elif event.is_action_pressed("kit_next") and not event.is_echo():
		kit.cycle(1)
	elif event.is_action_pressed("kit_prev") and not event.is_echo():
		kit.cycle(-1)
	elif event.is_action_pressed("toggle_lethal") and not event.is_echo():
		kit.lethal = not kit.lethal
		kit.changed.emit()
		if not sandbox:
			Mission.message.emit("The blade will kill." if kit.lethal else "Choke, don't kill.", 1.5)
	elif event.is_action_pressed("cam_toggle") and not event.is_echo():
		fp_aim = not fp_aim
	elif event.is_action_pressed("aim") and not event.is_echo():
		begin_aim()
	elif event.is_action_released("aim"):
		end_aim(true)
	elif event.is_action_pressed("throw") and not event.is_echo():
		begin_throw_aim(kit.throwable())
	elif event.is_action_released("throw"):
		if aiming:
			end_aim(true)
	elif event.is_action_pressed("attack") and not event.is_echo():
		if hidden_spot == null:
			if pistol_aim or kit.current == "pistol":
				fire_pistol()
			else:
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
	var mode: int = CamMode.THIRD
	if fp:
		mode = CamMode.FIRST
	elif (aiming or pistol_aim) and hidden_spot == null:
		mode = CamMode.FIRST if fp_aim else CamMode.SHOULDER
	_set_cam_mode(mode)
	if mode == CamMode.FIRST:
		var eye_w: Vector3 = fp.eye if fp else eye_position()
		want_pivot = to_local(eye_w)
		want_arm = 0.0
	elif mode == CamMode.SHOULDER:
		want_pivot = Vector3(0, 1.62, 0) + shoulder * 0.62
		want_arm = 1.9
	if hidden_spot and hidden_spot.get("hides_player"):
		# peek out of the hiding place: the camera sits at the spot's peek point, nearly first person
		want_pivot = to_local(hidden_spot.point(hidden_spot.peek_point))
		want_arm = 0.35
	elif hidden_spot:
		want_arm = 3.2
	var k := 1.0 - exp(-delta * 3.0 / CAM_BLEND) if mode != CamMode.THIRD or _pivot.position.distance_to(want_pivot) > 0.3 else clampf(6.0 * delta, 0.0, 1.0)
	_pivot.position = _pivot.position.lerp(want_pivot, k)
	_arm.spring_length = lerpf(_arm.spring_length, want_arm, k)
	_attack_cd = maxf(0.0, _attack_cd - delta)
	_lock = maxf(0.0, _lock - delta)
	var frozen := _lock > 0.0 or (not sandbox and Mission.dialogue_blocking())

	if hidden_spot:
		_in_spot(delta)
		_update_interact_target()
		return
	if fp:
		_in_fp(delta)
		return
	if trav.active():
		if trav.state == Traversal.SLIDE:
			_shape.shape.height = 0.7
			_shape.position.y = 0.35
		trav.tick(delta, _move_input(), _take_jump(), _take_drop())
		_update_senses(delta, false)
		_update_interact_target()
		return
	_kit_tick(delta)

	var crouch_in: bool = ai_crouch if scripted else Input.is_action_pressed("crouch")
	var sprint_in: bool = ai_sprint if scripted else Input.is_action_pressed("sprint")
	if is_prone and not scripted and Input.is_action_just_pressed("crouch") and not frozen:
		set_prone(false)
	var crouch_tap: bool = (ai_drop if scripted else Input.is_action_just_pressed("crouch"))
	if crouch_tap and is_sprinting and not frozen and not is_prone and _move_dir != Vector3.ZERO and is_on_floor():
		ai_drop = false
		if trav.try_slide(_move_dir) != "":
			return
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
	var accel := ACCEL if is_on_floor() else ACCEL * 0.25
	if trav.carry_speed > 0.1 and is_sprinting:
		accel = ACCEL * 0.35          # a sprint vault keeps its speed into the next stride
		trav.carry_speed = maxf(0.0, trav.carry_speed - delta * 3.0)
	velocity.x = move_toward(velocity.x, target.x, accel * delta)
	velocity.z = move_toward(velocity.z, target.z, accel * delta)
	if not is_on_floor():
		velocity.y -= GRAVITY * delta
	else:
		velocity.y = 0
	# Space: vault / mantle / hang (traversal.gd), a hop when nothing is there; in the air, catch an edge.
	if _take_jump() and not frozen and not carrying and dragging == null:
		var dir := wish if wish.length() > 0.1 else _body_dir()
		if is_on_floor():
			var act: String = trav.try_start(dir, is_sprinting)
			if act != "":
				return
			if not is_crouching:
				velocity.y = float(_tv("traversal.hop_speed", 4.2))
		else:
			if trav.try_air_grab(dir) != "":
				return
	move_and_slide()
	_landing(trav.track_fall(is_on_floor()))

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
	elif in_smoke():
		visibility = minf(visibility, float(_tv("kit.smoke_visibility", 0.1)))
	elif kit and kit.current == "torch" and kit.torch_lit:
		visibility *= float(_tv("kit.torch_visibility", 1.4))
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
	if posture() != 0 or is_sprinting or is_fighting() or aiming or pistol_aim or parrying or dragging:
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
			Assets.play_move(_figure, "walk_player", planar)
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
	if kit and kit.current == "torch" and not kit.torch_lit and Verbs.light_torch(self):
		return true
	_update_interact_target()
	if interact_target == null:
		return false
	if sandbox:
		return interact_target.on_interact(self)
	return Mission.interact(self, interact_target)


# ------------------------------------------------------------------ combat (non-lethal)

func is_fighting() -> bool:
	return Time.get_ticks_msec() - _last_swing_ms < 1500


## Strike with the current weapon. Returns "takedown" | "hit" | "miss" | "refused" | "" (not ready), or the pistol's
## result. From behind an unaware target: a choke (or with the knife and `kit.lethal`, a killing thrust); a guard
## reeling from a parry takes the knife's thrust whatever he sees.
func attack() -> String:
	if _attack_cd > 0.0 or _lock > 0.0 or (not sandbox and Mission.dialogue_blocking()) or hidden_spot or dragging or trav.active():
		return ""
	var wpn: String = kit.weapon() if kit else "cudgel"
	if wpn == "pistol":
		return fire_pistol()
	if wpn == "torch" and not kit.torch_lit and Verbs.light_torch(self):
		return "lit"
	_attack_cd = float({"knife": _tv("kit.knife_cooldown", 0.35), "musket": _tv("kit.musket_cooldown", 1.1)}.get(wpn, ATTACK_COOLDOWN))
	_last_swing_ms = Time.get_ticks_msec()
	var target := _attack_target()
	var swing_clip: String = {"knife": "knife_slash", "musket": "attack_swing"}.get(wpn, "attack_swing")
	if target == null:
		Assets.play_action(_figure, swing_clip, 0.8 if wpn == "musket" else 1.0)
		return "miss"
	var to := target.global_position - global_position
	_figure.rotation.y = atan2(-to.x, -to.z)
	var staggered: bool = target.has_method("is_staggered") and target.is_staggered() and wpn == "knife"
	var unaware: bool = target.has_method("is_unaware_of") and target.is_unaware_of(self, TAKEDOWN_REACH)
	if not target.has_method("is_unaware_of"):
		unaware = _behind(target) and Vector2(to.x, to.z).length() <= TAKEDOWN_REACH
	if unaware and wpn == "cosh":
		# a sandbag to the back of the head: down longer than a choke, quicker, no blood, no notoriety of its own
		_lock = 0.7
		velocity = Vector3.ZERO
		Assets.play_action(_figure, "attack_swing", 1.4)
		kit.last_takedown = "cosh"
		if target is Guard:
			target.knock_down(float(_tv("kit.cosh_down_secs", 90.0)), false)
			Assets.play_action(target._figure, "knocked_down_forward", 1.0, true)
		else:
			target.knock_down(float(_tv("kit.cosh_down_secs", 90.0)))
			if Mission.is_active() and not sandbox:
				Mission.on_takedown(target, false)
		return "takedown"
	if unaware or staggered:
		var lethal: bool = wpn == "knife" and kit.lethal
		_lock = 0.8 if staggered else 1.4
		velocity = Vector3.ZERO
		Assets.play_action(_figure, "knife_stab" if (lethal or staggered) else "takedown")
		kit.last_takedown = "thrust" if staggered else ("lethal" if lethal else "choke")
		if target is Guard:
			if lethal:
				target.dead = true
			target.knock_down(1.0e9 if lethal else TAKEDOWN_SECS, staggered)
			if lethal:
				Assets.play_action(target._figure, "death_fall_forward", 1.0, true)
				_lethal_cost("killed a soldier")
		else:
			target.knock_down(TAKEDOWN_SECS)
			if Mission.is_active() and not sandbox:
				Mission.on_takedown(target, false)
		return "takedown"
	if target is Guard:
		match wpn:
			"knife":
				Assets.play_action(_figure, "knife_slash")
				target.take_hit(self)
			"musket":
				# a two-handed club: slow, heavy (two blows' worth), loud
				Assets.play_action(_figure, "attack_swing", 0.75)
				target.take_hit(self)
				if is_instance_valid(target) and not target.is_downed():
					target.take_hit(self)
				if _watch:
					_watch.emit_sound(global_position, float(_tv("kit.musket_loudness", 0.6)), "musket", false, true, true)
			_:
				Assets.play_action(_figure, "attack_swing" if randf() < 0.7 else "attack_thrust")
				target.take_hit(self)
		return "hit"
	if not sandbox:
		Mission.message.emit("He would shout for the watch. Come at him from behind.", 3.0)
	return "refused"


## A killing: notoriety and crackdown rise more than for a choke.
func _lethal_cost(why: String, notoriety_key := "kit.lethal_notoriety", crack_key := "kit.lethal_crackdown") -> void:
	var intel: Node = _watch.get("intel") if _watch and is_instance_valid(_watch) else null
	if intel and intel.has_method("add_notoriety"):
		intel.add_notoriety(float(_tv(notoriety_key, 10.0)), why)
	if not sandbox:
		GameState.crackdown = clampi(GameState.crackdown + int(_tv(crack_key, 2)), 0, 100)


# ------------------------------------------------------------------ pistol, parry, aiming

## The pistol: one ball, then kit.pistol_reload_secs of reloading (F again starts it). The shot is heard across the
## district: every guard converges, the watch is told, notoriety and crackdown rise. Returns "hit" | "miss" |
## "reload" | "".
func fire_pistol() -> String:
	if kit == null or not kit.has("pistol") or _lock > 0.0 or hidden_spot or trav.active():
		return ""
	if not kit.pistol_loaded:
		if kit.start_reload():
			Assets.play_action(_figure, "pistol_reload")
		return "reload"
	kit.pistol_loaded = false
	kit.changed.emit()
	_last_swing_ms = Time.get_ticks_msec()
	var from := _camera.global_position
	var dir := -_camera.global_transform.basis.z
	var target: Node3D = null
	var best := deg_to_rad(float(_tv("kit.pistol_cone_deg", 7.0)))
	var pool: Array = get_tree().get_nodes_in_group("guards") + get_tree().get_nodes_in_group("takedown")
	if _watch and is_instance_valid(_watch):
		for g in _watch.guards():
			if not g in pool:
				pool.append(g)
	for n in pool:
		var t := n as Node3D
		if t == null or not Perception.same_world(t, self) or (t.has_method("is_downed") and t.is_downed()):
			continue
		var chest := t.global_position + Vector3(0, 1.2, 0)
		var to := chest - from
		if to.length() > float(_tv("kit.pistol_range", 20.0)):
			continue
		var ang := dir.angle_to(to)
		if ang < best and Perception.clear_line(get_world_3d().direct_space_state, from, chest, [get_rid(), (t as CollisionObject3D).get_rid() if t is CollisionObject3D else get_rid()], null, true):
			best = ang
			target = t
	var face := dir
	face.y = 0.0
	if face.length() > 0.01:
		_figure.rotation.y = atan2(-face.x, -face.z)
	Assets.play_action(_figure, "pistol_fire")
	_muzzle_flash()
	var result := "miss"
	if target:
		result = "hit"
		if target is Guard:
			target.dead = true
			target.knock_down(1.0e9, true)
			Assets.play_action(target._figure, "death_fall", 1.0, true)
		elif target.has_method("knock_down"):
			target.knock_down(1.0e9)
	if _watch and is_instance_valid(_watch):
		_watch.emit_sound(global_position, float(_tv("kit.pistol_loudness", 1.0)), "pistol", false, true, true)
		_watch.report(global_position, self)
		for g in _watch.awake_guards():
			if g.is_runner or g.state == Guard.State.ALARM:
				continue
			g.converge(global_position)
			g.set_task({"kind": "search", "pos": global_position}, true)
	_lethal_cost("fired a pistol", "kit.pistol_notoriety", "kit.pistol_crackdown")
	if not sandbox:
		Mission.message.emit("The shot rings across the square.", 2.0)
	return result


func _muzzle_flash() -> void:
	var l := OmniLight3D.new()
	l.light_color = Color(1.0, 0.8, 0.5)
	l.light_energy = 6.0
	l.omni_range = 6.0
	get_parent().add_child(l)
	l.global_position = global_position + Vector3(0, 1.45, 0) + _body_dir() * 0.8
	get_tree().create_timer(0.09, false).timeout.connect(l.queue_free)


## RMB: the current item's second use.
func begin_aim() -> void:
	if hidden_spot or dragging or health <= 0 or trav.active():
		return
	match kit.current:
		"knife":
			start_parry()
		"pistol":
			pistol_aim = true
			Assets.play_action(_figure, "pistol_draw")
		"torch":
			if kit.torch_lit:
				begin_throw_aim("torch")
		_:
			begin_throw_aim(kit.throwable())


func end_aim(release_throw: bool) -> void:
	parrying = false
	pistol_aim = false
	if aiming:
		aiming = false
		if release_throw:
			throw_item(throw_kind, _aim_velocity())


func begin_throw_aim(k: String) -> void:
	if k == "" or hidden_spot or dragging or health <= 0 or trav.active():
		return
	throw_kind = k
	aiming = true


## Knife parry: a guard's blow landing within kit.parry_window s of the press is turned aside and he reels
## (block_stagger) for kit.parry_stagger_secs: an opening for the thrust.
func start_parry() -> void:
	parrying = true
	_parry_ms = Time.get_ticks_msec()
	_last_swing_ms = _parry_ms
	Assets.play_action(_figure, "knife_parry")


func _try_parry(from: Node3D) -> bool:
	if from == null or kit == null or kit.current != "knife" or not from.has_method("stagger"):
		return false
	if Time.get_ticks_msec() - _parry_ms > int(float(_tv("kit.parry_window", 0.5)) * 1000.0):
		return false
	_parry_ms = -100000
	from.stagger(float(_tv("kit.parry_stagger_secs", 1.8)), "block_stagger")
	Assets.play_action(_figure, "knife_parry")
	_last_swing_ms = Time.get_ticks_msec()
	parries += 1
	return true


## Per-frame kit work: pistol reload, being disarmed when seized, muskets beside downed guards.
func _kit_tick(delta: float) -> void:
	if kit.reload_left > 0.0:
		var working: bool = kit.current == "pistol" and not is_sprinting and _lock <= 0.0
		if working and not Assets.is_action(_figure):
			Assets.play_action(_figure, "pistol_reload")
		kit.tick(delta, working)
	_scan_cd -= delta
	if _scan_cd > 0.0 or _watch == null or not is_instance_valid(_watch):
		return
	_scan_cd = 0.2
	var seizing: Node = null
	for g in _watch.guards():
		if not is_instance_valid(g):
			continue
		if g.is_downed():
			if not g.has_meta("kit_musket") and g.get("hidden_in") == null:
				var right: Vector3 = g.global_transform.basis.x
				var pk := Pickup.drop(g.get_parent(), "musket", g.global_position + right * 0.9)
				g.set_meta("kit_musket", pk)
			continue
		if g.has_meta("kit_musket"):
			var pk: Variant = g.get_meta("kit_musket")
			if is_instance_valid(pk):
				(pk as Node).queue_free()
			g.remove_meta("kit_musket")
		if g.global_position.distance_to(global_position) < 1.6 and Assets.action_clip(g._figure) == "guard_seize":
			seizing = g
	if seizing and _seized_by != seizing:
		for item in kit.disarm():
			Pickup.drop(get_parent(), item, global_position + Vector3(randf_range(-0.6, 0.6), 0.02, randf_range(-0.6, 0.6)))
		if not sandbox:
			Mission.message.emit("He wrenches the weapon from your hand!", 2.0)
	_seized_by = seizing


## Leaves an item of the kit on the ground (the musket when you switch away from it).
func drop_item(item: String) -> void:
	Pickup.drop(get_parent(), item, global_position + _body_dir() * 0.6)


## The current weapon in the right hand (kit_<item>.glb on a BoneAttachment3D), or nothing.
func _update_hand_prop() -> void:
	var item: String = kit.current if kit and kit.current in ["knife", "cosh", "cudgel", "pistol", "musket", "torch"] else ""
	var key := item + ("_lit" if item == "torch" and kit.torch_lit else "")
	if key == _hand_item and (_hand_prop == null or is_instance_valid(_hand_prop)):
		return
	_hand_item = key
	if _hand_prop and is_instance_valid(_hand_prop):
		_hand_prop.queue_free()
	_hand_prop = null
	if item == "" or not ResourceLoader.exists("res://assets/models/kit_%s.glb" % item) or _figure == null or not is_inside_tree():
		return
	var sks := _figure.find_children("*", "Skeleton3D", true, false)
	if sks.is_empty():
		return
	var sk: Skeleton3D = sks[0]
	var bi := sk.find_bone("hand_r")
	if bi < 0:
		return
	var ba := BoneAttachment3D.new()
	ba.bone_name = "hand_r"
	sk.add_child(ba)
	var m := Assets.instance("kit_" + item)
	# kit props are modelled along +Y (Godot) from the grip; the hand bone runs wrist -> fingers along its +Y
	m.position = Vector3(0.0, 0.08, 0.03)
	m.rotation = Vector3(0, 0, -PI * 0.5)
	ba.add_child(m)
	_hand_prop = ba
	if key == "torch_lit":
		# the flame: a warm light that follows the hand (not a "flame_lights" member: the x1.4 is applied directly)
		var fl := OmniLight3D.new()
		fl.light_color = Color(1.0, 0.62, 0.3)
		fl.light_energy = 2.2
		fl.omni_range = 7.0
		fl.shadow_enabled = not sandbox
		fl.position = m.position + m.basis * Vector3(0, 0.45, 0)
		ba.add_child(fl)
		var flame := MeshInstance3D.new()
		var sm := SphereMesh.new()
		sm.radius = 0.06
		sm.height = 0.18
		var mat := StandardMaterial3D.new()
		mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		mat.albedo_color = Color(1.0, 0.7, 0.3)
		mat.emission_enabled = true
		mat.emission = Color(1.0, 0.55, 0.2)
		mat.emission_energy_multiplier = 4.0
		sm.material = mat
		flame.mesh = sm
		flame.position = fl.position
		ba.add_child(flame)


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
	if _try_parry(from):
		return
	if trav.active():
		if trav.state == Traversal.HANG:
			trav._drop_from_hang()
		else:
			trav._end()
	if fp:
		end_fp()
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


## Throw `kind` (a kit throwable) with velocity `vel`. `consume`: take it from the kit (the player's own throws);
## scripted throws (smoke tests, missions) pass false. Returns the Stone node, or null.
func throw_item(kind: String, vel: Vector3, consume := true) -> Node3D:
	if health <= 0 or hidden_spot or kind == "":
		return null
	if consume and not kit.take(kind):
		return null
	var st := Distraction.Stone.new()
	st.kind = kind
	st.velocity = vel
	st.loudness = float({"stone": _tv("distractions.throw_loudness", 0.9), "bottle": _tv("kit.bottle_loudness", 0.7),
			"coin": _tv("kit.coin_loudness", 0.35), "food": _tv("kit.food_loudness", 0.3)}.get(kind, 0.5))
	st.exclude = [get_rid()]
	get_parent().add_child(st)
	st.global_position = _hand()
	_figure.rotation.y = atan2(-vel.x, -vel.z)
	Assets.play_action(_figure, "throw_powder" if kind in ["smoke", "flash"] else "attack_swing", 1.0 if kind in ["smoke", "flash"] else 1.5)
	_arc.visible = false
	return st


## Throw a stone with velocity `vel` (does not use up the kit). Returns the stone.
func throw_stone(vel: Vector3) -> Node3D:
	return throw_item("stone", vel, false)


## Scripted throw at a point (smoke, missions).
func throw_at(point: Vector3, kind := "stone", consume := false) -> Node3D:
	return throw_item(kind, Distraction.launch_velocity(_hand(), point, float(_tv("distractions.throw_speed", 11.0))), consume)


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


# ------------------------------------------------------------------ traversal glue

## (right, forward) movement input, -1..1.
func _move_input() -> Vector2:
	if scripted:
		var f := _body_dir()
		var r := Vector3(-f.z, 0, f.x)
		return Vector2(ai_move.dot(r), ai_move.dot(f))
	var v := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	return Vector2(v.x, -v.y)


func _take_jump() -> bool:
	if scripted:
		var j := ai_jump
		ai_jump = false
		return j
	return Input.is_action_just_pressed("jump") and not Mission.dialogue_blocking()


func _take_drop() -> bool:
	if scripted:
		var d := ai_drop
		ai_drop = false
		return d
	return Input.is_action_just_pressed("crouch")


func set_trav_collision(on: bool) -> void:
	_shape.disabled = not on
	if on:
		_shape.shape.height = 1.8
		_shape.position.y = 0.9


## A landing after a fall: a roll keeps the momentum; a stumble from too high costs a hit point.
func _landing(kind: String) -> void:
	if kind == "":
		return
	match kind:
		"roll":
			Assets.play_action(_figure, "fall_land_roll")
			var f := _body_dir()
			velocity.x = f.x * maxf(3.0, Vector2(velocity.x, velocity.z).length())
			velocity.z = f.z * maxf(3.0, Vector2(velocity.x, velocity.z).length())
			if _watch:
				_watch.emit_sound(global_position, 0.45, "land", false, true, true)
		"stumble":
			Assets.play_action(_figure, "stumble")
			_lock = 0.9
			velocity = Vector3.ZERO
			if _watch:
				_watch.emit_sound(global_position, 0.7, "land", false, true, true)
			health -= 1
			if not sandbox:
				Mission.message.emit("A bad fall. (%d of %d)" % [health, MAX_HEALTH], 1.5)
				if health <= 0:
					if Mission.is_active():
						Mission.fail("Broke his neck in a fall")
					else:
						GameState.end_night(false)


## Inside a smoke cloud (distraction.gd SmokeCloud)?
func in_smoke() -> bool:
	for c in get_tree().get_nodes_in_group("smoke_cloud"):
		if Perception.same_world(c, self) and c.contains(chest_position()):
			return true
	return false


# ------------------------------------------------------------------ camera modes, first-person actions

## World position of the eyes (the head bone when there is one).
func eye_position() -> Vector3:
	var sks := _figure.find_children("*", "Skeleton3D", true, false) if _figure else []
	if not sks.is_empty():
		var sk: Skeleton3D = sks[0]
		var hi := sk.find_bone("head")
		if hi >= 0:
			return sk.global_transform * sk.get_bone_global_pose(hi).origin + Vector3(0, 0.09, 0) + _look_dir() * 0.12
	return head_position() + _look_dir() * 0.12


func _set_cam_mode(m: int) -> void:
	if m == cam_mode:
		return
	cam_mode = m
	_set_head_hidden(m == CamMode.FIRST)
	_camera.near = 0.03 if m == CamMode.FIRST else 0.05
	_arm.collision_mask = 0 if m == CamMode.FIRST else 1


## Hides the head, hat and hair meshes of the figure (first person).
func _set_head_hidden(on: bool) -> void:
	if _head_meshes.is_empty() and _figure:
		for mi in _figure.find_children("*", "MeshInstance3D", true, false):
			var nm := String(mi.name).to_lower()
			for w in HEAD_WORDS:
				if w in nm:
					_head_meshes.append(mi)
					break
	_head_hidden = on
	for mi in _head_meshes:
		if is_instance_valid(mi):
			(mi as MeshInstance3D).visible = not on
	if _hand_prop and is_instance_valid(_hand_prop) and _hand_item == "musket":
		_hand_prop.visible = not on


func head_hidden() -> bool:
	return _head_hidden


## Starts a first-person close action ("keyhole", "listen", "lockpick", "pocket") on `target`. Returns true.
func start_fp(kind: String, target: Node3D) -> bool:
	if fp or hidden_spot or dragging or health <= 0 or trav.active():
		return false
	aiming = false
	pistol_aim = false
	parrying = false
	var s := FpView.Session.new()
	s.kind = kind
	s.player = self
	s.target = target
	var to := target.global_position - global_position
	to.y = 0.0
	var inward := to.normalized() if to.length() > 0.05 else _body_dir()
	match kind:
		"keyhole":
			if target.has_meta("keyhole_eye"):
				s.eye = target.to_global(target.get_meta("keyhole_eye"))
			else:
				s.eye = target.global_position + inward * 0.35 + Vector3(0, 1.1, 0)
			s.look = inward
		"listen":
			s.eye = eye_position()
			s.look = inward
			s.arc = deg_to_rad(40.0)
		_:
			s.eye = eye_position()
			s.look = inward
			s.arc = deg_to_rad(30.0)
	_figure.rotation.y = atan2(-inward.x, -inward.z)
	if kind == "keyhole" or kind == "lockpick":
		Assets.play_action(_figure, "crouch_idle", 1.0, true)
	fp = s
	add_child(s)
	rotate_camera(Vector3(-0.05 if kind != "lockpick" else -0.35, atan2(-s.look.x, -s.look.z), 0))
	velocity = Vector3.ZERO
	return true


func end_fp() -> void:
	if fp == null:
		return
	var s := fp
	fp = null
	last_fp_result = str(s.get("result"))
	if is_instance_valid(s):
		s.end()
	Assets.clear_action(_figure)


func _in_fp(delta: float) -> void:
	velocity = Vector3.ZERO
	var s := fp
	# the look arc about the session's centre
	var yaw0 := atan2(-s.look.x, -s.look.z)
	_yaw = yaw0 + clampf(wrapf(_yaw - yaw0, -PI, PI), -s.arc, s.arc)
	_pitch = clampf(_pitch, -0.35 - s.pitch_arc, s.pitch_arc)
	var hold: bool = ai_interact_hold if scripted else Input.is_action_pressed("interact")
	var tension: bool = ai_tension if scripted else Input.is_action_pressed("aim")
	var tap: bool = ai_tap if scripted else Input.is_action_just_pressed("attack")
	ai_tap = false
	var cancel := false
	if scripted:
		cancel = ai_move.length() > 0.1
	else:
		cancel = Input.get_vector("move_left", "move_right", "move_forward", "move_back").length() > 0.2 \
				or Input.is_action_just_pressed("pause")
	if not s.tick(delta, hold, tension, tap, cancel):
		end_fp()
	_update_senses(delta, false)


# ------------------------------------------------------------------ fight capture (`-- --smoke --fight-shot=/dir`)

const FIGHT_SHOT_TAKEDOWN_OFFSET := 0.22   ## victim stands this far in front of the attacker (= build_animations.TAKEDOWN_OFFSET)


static var _fight_started := false


## Capture mode (`-- --smoke --fight-shot=/dir`): while the smoke run goes on, poses the current player next to a
## temporary guard for takedown, cudgel blow, hit and knockdown and saves a side and a front view of each from a
## temporary camera; the player's own camera, pose and physics are restored after every shot. Needs a window.
## Static so it survives the smoke run rebuilding the world; it looks the player up afresh for every shot.
static func _fight_shots(dir: String) -> void:
	var tree := Engine.get_main_loop() as SceneTree
	for i in 120:
		await tree.process_frame
	DirAccess.make_dir_recursive_absolute(dir)
	# [name, guard offset along the player's forward, guard faces the player?, player clip, time, guard clip, time]
	var setups := [
		["takedown_grab", FIGHT_SHOT_TAKEDOWN_OFFSET, false, "takedown", 0.5, "takedown_victim", 0.5],
		["takedown_lower", FIGHT_SHOT_TAKEDOWN_OFFSET, false, "takedown", 1.4, "takedown_victim", 1.4],
		["attack_swing", 1.5, true, "attack_swing", 0.44, "musket_ready", 0.3],
		["hit_react", 1.35, true, "hit_react", 0.08, "musket_butt", 0.44],
		["knocked_down", 1.5, true, "knocked_down", 1.4, "musket_ready", 0.3],
	]
	var saved := 0
	for s in setups:
		var p := tree.get_first_node_in_group("player") as Player
		while p == null or not p.is_inside_tree() or p._figure == null:
			await tree.process_frame
			p = tree.get_first_node_in_group("player") as Player
		var world := p.get_parent()
		var guard: Guard = Guard.new()
		guard.guard_name = "Fight shot guard"
		world.add_child(guard)
		guard.set_physics_process(false)
		p.set_physics_process(false)
		var cam := Camera3D.new()
		cam.fov = 40
		world.add_child(cam)
		var yaw := p._figure.rotation.y
		var fwd := Vector3(-sin(yaw), 0, -cos(yaw))
		var right := Vector3(cos(yaw), 0, -sin(yaw))
		var base := p.global_position
		guard.global_position = base + fwd * float(s[1])
		guard.rotation = Vector3(0, yaw + (PI if s[2] else 0.0), 0)
		await tree.process_frame
		p._freeze_clip(p._figure, s[3], s[4])
		p._freeze_clip(guard._figure, s[5], s[6])
		var mid := base + fwd * float(s[1]) * 0.5
		for view in [["side", mid + right * 4.2 + Vector3(0, 1.1, 0)], ["front", mid + fwd * 4.6 - right * 1.4 + Vector3(0, 1.3, 0)]]:
			cam.global_position = view[1]
			cam.look_at(mid + Vector3(0, 0.85, 0))
			cam.current = true
			for i in 3:
				await tree.process_frame
			tree.root.get_viewport().get_texture().get_image().save_png("%s/fight_%s_%s.png" % [dir, s[0], view[0]])
			saved += 1
		if is_instance_valid(p):
			p._camera.current = true
			Assets.clear_action(p._figure)
			var ap: AnimationPlayer = p._figure.get_meta("anim") if p._figure.has_meta("anim") else null
			if ap:
				ap.play()
			p.set_physics_process(true)
		cam.queue_free()
		guard.queue_free()
	print("[smoke] fight shots=%d in %s" % [saved, dir])


func _freeze_clip(pivot: Node3D, clip: String, t: float) -> void:
	if pivot == null or not pivot.has_meta("anim"):
		return
	Assets.play_action(pivot, clip, 1.0, true, 0.0)
	var ap: AnimationPlayer = pivot.get_meta("anim")
	ap.seek(t, true)
	ap.pause()


## Capture mode (`-- --smoke --walk-shot=/dir`): the player's figure and two townsfolk figures (the models of the two
## nearest NPCs) walk in place in a private SubViewport stage (own World3D, so the running smoke test cannot disturb
## it) with walk, walk_fast, run and sneak, frozen at two stride phases, shot from the side and from 3/4 front.
static func _walk_shots(dir: String) -> void:
	var tree := Engine.get_main_loop() as SceneTree
	for i in 150:
		await tree.process_frame
	DirAccess.make_dir_recursive_absolute(dir)
	var p := tree.get_first_node_in_group("player") as Player
	while p == null or not p.is_inside_tree():
		await tree.process_frame
		p = tree.get_first_node_in_group("player") as Player
	var models: Array = [GameState.figure_name()]
	var npcs: Array = []
	for n in tree.get_nodes_in_group("npcs"):
		var mn: Variant = n.get("model_name")
		if mn is String and mn != "" and not n.is_in_group("animals") and not (mn in models) and not "watch" in (mn as String) and not n.is_in_group("guards"):
			npcs.append(n)
	npcs.sort_custom(func(a: Node3D, b: Node3D) -> bool: return a.global_position.distance_to(p.global_position) < b.global_position.distance_to(p.global_position))
	for n in npcs.slice(0, 2):
		models.append(n.get("model_name"))
	var vp := SubViewport.new()
	vp.size = Vector2i(1280, 720)
	vp.own_world_3d = true
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	tree.root.add_child(vp)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = Color(0.62, 0.66, 0.72)
	env.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.environment.ambient_light_color = Color(0.55, 0.55, 0.58)
	vp.add_child(env)
	var sun := DirectionalLight3D.new()
	sun.rotation = Vector3(-0.9, 0.5, 0)
	sun.shadow_enabled = true
	vp.add_child(sun)
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(30, 30)
	ground.mesh = pm
	var gm := StandardMaterial3D.new()
	gm.albedo_color = Color(0.38, 0.38, 0.36)
	ground.material_override = gm
	vp.add_child(ground)
	var figs: Array = []
	for i in models.size():
		var f := Assets.character(models[i])
		if f == null:
			continue
		f.position = Vector3(1.8 * i, 0, 0)      # in a row, all facing -X, so the +Z camera sees profiles
		f.rotation.y = PI * 0.5
		vp.add_child(f)
		figs.append(f)
	var cam := Camera3D.new()
	cam.fov = 34
	vp.add_child(cam)
	cam.current = true
	var mid := Vector3(1.8 * (figs.size() - 1) * 0.5, 0.9, 0)
	var shots := 0
	for clip in ["walk", "walk_fast", "run", "sneak"]:
		for phase in [0.1, 0.35]:
			for i in figs.size():
				var c: String = "walk_player" if (i == 0 and clip == "walk") else clip
				var name := Assets.resolve(figs[i], c)
				if name == "":
					continue
				var ap: AnimationPlayer = figs[i].get_meta("anim")
				Assets.play_action(figs[i], c, 1.0, true, 0.0)
				ap.seek(ap.get_animation(name).length * phase, true)
				ap.pause()
			for view in [["side", mid + Vector3(0, 0.1, 8.0)], ["q34", mid + Vector3(-4.6, 0.9, 4.6)]]:
				cam.position = view[1]
				cam.look_at(mid)
				for k in 4:
					await tree.process_frame
				vp.get_texture().get_image().save_png("%s/walk_%s_%02d_%s.png" % [dir, clip, int(phase * 100), view[0]])
				shots += 1
	vp.queue_free()
	print("[smoke] walk shots=%d models=%s in %s" % [shots, models, dir])
