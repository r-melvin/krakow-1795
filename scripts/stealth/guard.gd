extends CharacterBody3D
class_name Guard

const Walker := preload("res://scripts/npc/walker.gd")
## Austrian watch patrol. Waypoint patrol, vision cone with line-of-sight, hearing, suspicion state machine.
## Non-lethal fighting: 2 health; in ALARM within reach it swings the musket butt at the player every 1.2 s.
## At 0 health, or taken from behind, it is `downed` (senseless) for a while, then wakes up searching.
## A disguised player (player.disguised) reads as a townsman: sight/hearing count a quarter, unless they
## sprint, crouch or linger within 3 m for more than 4 s.

enum State { CALM, CURIOUS, SEARCHING, ALARM }

@export var waypoints: Array[Vector3] = []
@export var patrol_speed := 1.8
@export var chase_speed := 4.2
@export var view_distance := 14.0
@export var view_angle_deg := 70.0
@export var hearing_distance := 8.0
@export var wait_at_waypoint := 1.5
@export var guard_name := "Watchman"

var state: State = State.CALM
var suspicion := 0.0             ## 0..100
var last_known: Vector3
var _wp_index := 0
var _wait := 0.0
var _search_timer := 0.0
var _player: Player
var _cone: MeshInstance3D
var _label: Label3D
var _figure: Node3D
var _alarm_reported := false

var health := MAX_HEALTH
var downed_left := 0.0            ## seconds left senseless on the cobbles (0 = up)
var _base_view := 0.0
var _linger := 0.0                ## seconds the disguised player has stood within LINGER_DIST
var _near_time := 0.0             ## seconds the player has been within CATCH_DISTANCE while alarmed
var _swing_cd := SWING_WINDUP
var _shape: CollisionShape3D
var _rising := 0.0                ## seconds left of the get_up clip after waking (stands still meanwhile)
var _swings := 0
var _seize_played := false

const SUSPICION_GAIN := 45.0     ## per second at full visibility, point blank
const SUSPICION_DECAY := 12.0
const CATCH_DISTANCE := 1.3
const CATCH_TIME := 2.0           ## seconds held within CATCH_DISTANCE (while the player is not fighting back)
const MAX_HEALTH := 2
const REACH := 1.6
const SWING_EVERY := 1.2
const SWING_WINDUP := 0.6
const DISGUISE_FACTOR := 0.25
const LINGER_DIST := 3.0
const LINGER_TIME := 4.0


func _ready() -> void:
	add_to_group("guards")
	_base_view = view_distance
	_build_visuals()
	if waypoints.is_empty():
		waypoints = [global_position]
	last_known = global_position
	_player = get_tree().get_first_node_in_group("player") as Player


func _build_visuals() -> void:
	var shape := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.35
	cap.height = 1.8
	shape.shape = cap
	shape.position.y = 0.9
	add_child(shape)
	_shape = shape

	_figure = Assets.character("watchman")
	var fig: Node3D = _figure
	if fig == null:
		fig = Node3D.new()
		var mi := MeshInstance3D.new()
		var m := CapsuleMesh.new()
		m.radius = 0.35
		m.height = 1.8
		mi.mesh = m
		mi.position.y = 0.9
		fig.add_child(mi)
	else:
		fig.set_meta("anim_role", "guard")
	add_child(fig)

	# Vision cone: a flat wedge on the ground, colour shows state.
	_cone = MeshInstance3D.new()
	var cone_mesh := ImmediateMesh.new()
	_cone.mesh = cone_mesh
	var cmat := StandardMaterial3D.new()
	# Additive and dim: a faint tint on the cobbles that can never turn into a solid slab, whatever the exposure.
	cmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	cmat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	cmat.albedo_color = Color(0.035, 0.06, 0.02, 1.0)
	cmat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	cmat.cull_mode = BaseMaterial3D.CULL_DISABLED
	cmat.no_depth_test = false
	cmat.disable_receive_shadows = true
	_cone.material_override = cmat
	_cone.position.y = 0.05
	add_child(_cone)
	_rebuild_cone()

	_label = Label3D.new()
	_label.position.y = 2.2
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_label.font_size = 40
	_label.pixel_size = 0.005
	add_child(_label)


func _rebuild_cone() -> void:
	var im := _cone.mesh as ImmediateMesh
	im.clear_surfaces()
	im.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	var half := deg_to_rad(view_angle_deg * 0.5)
	var steps := 16
	for i in steps:
		var a0 := -half + (2 * half) * float(i) / steps
		var a1 := -half + (2 * half) * float(i + 1) / steps
		im.surface_add_vertex(Vector3.ZERO)
		im.surface_add_vertex(Vector3(sin(a0), 0, -cos(a0)) * view_distance)
		im.surface_add_vertex(Vector3(sin(a1), 0, -cos(a1)) * view_distance)
	im.surface_end()


func _physics_process(delta: float) -> void:
	if _player == null:
		_player = get_tree().get_first_node_in_group("player") as Player
		if _player == null:
			return
	if downed_left > 0.0:
		downed_left -= delta
		velocity = Vector3.ZERO
		if downed_left <= 0.0:
			_wake()
		return
	if _rising > 0.0:
		_rising -= delta
		velocity = Vector3.ZERO
		return
	var vis := _perceive()
	_update_suspicion(vis, delta)
	match state:
		State.CALM:
			_patrol(delta)
		State.CURIOUS:
			_face(last_known, delta)
		State.SEARCHING:
			_go_to(last_known, patrol_speed * 1.3, delta)
			_search_timer -= delta
			if _search_timer <= 0 and global_position.distance_to(last_known) < 1.0:
				suspicion = 20
		State.ALARM:
			_fight(delta)
	_update_visuals()
	_animate(Vector2(velocity.x, velocity.z).length())


## State machine -> clip: shoulder arms on patrol and at post, port arms scanning when curious or searching,
## running at the charge, bayonet guard in reach (swings and seizures are one-shots from _fight).
func _animate(planar: float) -> void:
	match state:
		State.CALM:
			if planar > 0.3:
				Assets.play_move(_figure, "guard_march", planar)
			else:
				Assets.play(_figure, "guard_sentry")
		State.CURIOUS:
			Assets.play(_figure, "guard_alert_look")
		State.SEARCHING:
			if planar > 0.3:
				Assets.play_move(_figure, "guard_march", planar)
			else:
				Assets.play(_figure, "guard_alert_look")
		State.ALARM:
			if planar > 0.3:
				Assets.play_move(_figure, "run", planar)
			else:
				Assets.play(_figure, "musket_ready")


## Returns 0..1 how well this guard currently perceives the player.
func _perceive() -> float:
	var to_player := _player.head_position() - (global_position + Vector3(0, 1.5, 0))
	var dist := to_player.length()
	var score := 0.0

	# Hearing (ignores walls for now, halved through them later).
	if _player.noise > 0 and dist < hearing_distance * _player.noise * 1.5:
		score = maxf(score, 0.35 * _player.noise)

	# Sight.
	if dist < view_distance:
		var fwd := -global_transform.basis.z
		var ang := rad_to_deg(fwd.angle_to(to_player.normalized()))
		if ang < view_angle_deg * 0.5:
			var space := get_world_3d().direct_space_state
			var q := PhysicsRayQueryParameters3D.create(global_position + Vector3(0, 1.5, 0), _player.head_position())
			q.exclude = [get_rid()]
			var hit := space.intersect_ray(q)
			if hit.is_empty() or hit.get("collider") == _player:
				var falloff := 1.0 - (dist / view_distance)
				score = maxf(score, (0.3 + 0.7 * falloff) * _player.visibility)
	if score > 0 and _player.get("disguised") and not (_player.is_sprinting or _player.is_crouching or _linger > LINGER_TIME):
		score *= DISGUISE_FACTOR
	if score > 0:
		last_known = _player.global_position
	return score


func _update_suspicion(vis: float, delta: float) -> void:
	if global_position.distance_to(_player.global_position) < LINGER_DIST:
		_linger += delta
	else:
		_linger = 0.0
	if vis > 0:
		suspicion += SUSPICION_GAIN * vis * delta
	else:
		suspicion -= SUSPICION_DECAY * delta
	suspicion = clampf(suspicion, 0, 100)

	var new_state := state
	if suspicion >= 100:
		new_state = State.ALARM
	elif suspicion >= 60:
		new_state = State.SEARCHING
	elif suspicion >= 20:
		new_state = State.CURIOUS
	elif state != State.ALARM or suspicion <= 0:
		new_state = State.CALM
	if state == State.ALARM and suspicion > 0:
		new_state = State.ALARM   # alarm sticks until suspicion fully decays

	if new_state != state:
		if new_state == State.SEARCHING:
			_search_timer = 6.0
		if new_state == State.ALARM and not _alarm_reported:
			_alarm_reported = true
			GameState.raise_alarm(guard_name)
		if new_state == State.CALM:
			_alarm_reported = false
		state = new_state


func _patrol(delta: float) -> void:
	var target := waypoints[_wp_index]
	if global_position.distance_to(target) < 0.4:
		_wait += delta
		velocity = Vector3.ZERO
		if _wait >= wait_at_waypoint:
			_wait = 0
			_wp_index = (_wp_index + 1) % waypoints.size()
		return
	_go_to(target, patrol_speed, delta)


func _go_to(target: Vector3, speed: float, delta: float) -> void:
	var dir := target - global_position
	dir.y = 0
	if dir.length() < 0.2:
		velocity.x = 0
		velocity.z = 0
	else:
		dir = dir.normalized()
		velocity.x = dir.x * speed
		velocity.z = dir.z * speed
		_face(target, delta)
	if not is_on_floor():
		velocity.y -= 18.0 * delta
	move_and_slide()


func _face(target: Vector3, delta: float) -> void:
	var d := target - global_position
	d.y = 0
	if d.length() < 0.01:
		return
	var want := atan2(-d.x, -d.z)
	rotation.y = lerp_angle(rotation.y, want, 6 * delta)


## ALARM: close in; within reach, swing every SWING_EVERY s. Held close for CATCH_TIME s while the player is not
## fighting back, they are seized.
func _fight(delta: float) -> void:
	var d := global_position.distance_to(_player.global_position)
	if d > REACH:
		_go_to(_player.global_position, chase_speed, delta)
		_swing_cd = SWING_WINDUP
	else:
		velocity.x = 0.0
		velocity.z = 0.0
		_face(_player.global_position, delta)
		if not is_on_floor():
			velocity.y -= 18.0 * delta
		move_and_slide()
		_swing_cd -= delta
		if _swing_cd <= 0.0:
			_swing_cd = SWING_EVERY
			Walker.speech(self, "Halt!", 0.8, 2.3)
			_swings += 1
			Assets.play_action(_figure, "musket_butt" if _swings % 3 != 0 else "bayonet_thrust", 1.3)
			if _player.has_method("take_hit"):
				_player.take_hit(self)
	if d < CATCH_DISTANCE and not (_player.has_method("is_fighting") and _player.is_fighting()):
		_near_time += delta
		if _near_time > CATCH_TIME * 0.5 and not _seize_played:
			_seize_played = true
			Assets.play_action(_figure, "guard_seize")
		if _near_time > CATCH_TIME:
			_catch()
	else:
		_near_time = maxf(0.0, _near_time - delta)
		if _near_time <= 0.0:
			_seize_played = false


## Struck by the player in a fight. Goes to ALARM at once; at 0 health it is downed.
func take_hit(_from: Node3D) -> void:
	if downed_left > 0.0:
		return
	health -= 1
	if health <= 0:
		knock_down(60.0, true)
		return
	last_known = _player.global_position if _player else global_position
	suspicion = 100.0
	_update_suspicion(0.0, 0.0)
	Assets.play_action(_figure, "hit_react")


## True if a player standing behind (and within `dist`) would be unseen: rear takedown allowed.
func is_unaware_of(p: Node3D, dist: float = 1.5) -> bool:
	if downed_left > 0.0 or state == State.SEARCHING or state == State.ALARM:
		return false
	var to_p := p.global_position - global_position
	to_p.y = 0.0
	if to_p.length() > dist:
		return false
	var fwd := -global_transform.basis.z
	fwd.y = 0.0
	return rad_to_deg(fwd.angle_to(to_p)) > 110.0


## Senseless for `secs`. `in_fight`: downed in open combat (crackdown +5, witnesses raise the alarm);
## otherwise a quiet rear takedown.
func knock_down(secs: float, in_fight: bool) -> void:
	downed_left = secs
	health = 0
	state = State.CALM
	suspicion = 0.0
	_near_time = 0.0
	velocity = Vector3.ZERO
	if _figure and Assets.has_clip(_figure, "knocked_down"):
		# fair fight: thrown on his back; rear takedown: choked and lowered to the cobbles
		Assets.play_action(_figure, "knocked_down" if in_fight else "takedown_victim", 1.0, true)
	elif _figure:
		_figure.rotation.x = -PI * 0.5
		_figure.position.y = 0.18
		Assets.play(_figure, "idle", 0.0)
	_shape.disabled = true
	_cone.visible = false
	_label.text = "zz"
	if in_fight:
		GameState.crackdown = clampi(GameState.crackdown + 5, 0, 100)
		for g in get_tree().get_nodes_in_group("guards"):
			if g != self and g.has_method("witness"):
				g.witness(global_position)
	if Mission.is_active():
		Mission.on_takedown(self, in_fight)


func is_downed() -> bool:
	return downed_left > 0.0


func _wake() -> void:
	downed_left = 0.0
	health = MAX_HEALTH
	if _figure:
		_figure.rotation.x = 0.0
		_figure.position.y = 0.0
		Assets.clear_action(_figure)
		_rising = Assets.play_action(_figure, "get_up")
	_shape.disabled = false
	_cone.visible = true
	last_known = global_position
	suspicion = 65.0
	_search_timer = 6.0
	state = State.SEARCHING


## Another guard went down in a fight at `pos`: if this one can see the spot, full alarm.
func witness(pos: Vector3) -> void:
	if downed_left > 0.0:
		return
	var eye := global_position + Vector3(0, 1.5, 0)
	var to := pos + Vector3(0, 1.0, 0) - eye
	if to.length() > view_distance:
		return
	if rad_to_deg((-global_transform.basis.z).angle_to(to.normalized())) > view_angle_deg * 0.5 and to.length() > 4.0:
		return
	var q := PhysicsRayQueryParameters3D.create(eye, pos + Vector3(0, 1.0, 0))
	q.exclude = [get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if not hit.is_empty() and not (hit.get("collider") is Guard) and not (hit.get("collider") is Player):
		return
	last_known = _player.global_position if _player else pos
	suspicion = 100.0
	_update_suspicion(0.0, 0.0)


## Curfew bell and the like: scale the view distance (1.0 restores it) and redraw the cone.
func set_view_mult(m: float) -> void:
	view_distance = _base_view * m
	_rebuild_cone()


func _catch() -> void:
	set_physics_process(false)
	if Mission.is_active():
		Mission.fail("Caught by the watch: " + guard_name)
	else:
		GameState.end_night(false)


func _update_visuals() -> void:
	if downed_left > 0.0:
		return
	var mat := _cone.material_override as StandardMaterial3D
	match state:
		State.CALM:
			mat.albedo_color = Color(0.035, 0.06, 0.02, 1.0)
			_label.text = ""
		State.CURIOUS:
			mat.albedo_color = Color(0.16, 0.12, 0.03, 1.0)
			_label.text = "?"
		State.SEARCHING:
			mat.albedo_color = Color(0.24, 0.11, 0.03, 1.0)
			_label.text = "!?"
		State.ALARM:
			mat.albedo_color = Color(0.30, 0.05, 0.03, 1.0)
			_label.text = "!!"
