extends CharacterBody3D
class_name Guard
## Austrian watch patrol. Waypoint patrol, vision cone with line-of-sight, hearing, suspicion state machine.

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
var _alarm_reported := false

const SUSPICION_GAIN := 45.0     ## per second at full visibility, point blank
const SUSPICION_DECAY := 12.0
const CATCH_DISTANCE := 1.3


func _ready() -> void:
	add_to_group("guards")
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

	var fig := Assets.instance("watchman")
	if fig == null:
		fig = Node3D.new()
		var mi := MeshInstance3D.new()
		var m := CapsuleMesh.new()
		m.radius = 0.35
		m.height = 1.8
		mi.mesh = m
		mi.position.y = 0.9
		fig.add_child(mi)
	add_child(fig)

	# Vision cone: a flat wedge on the ground, colour shows state.
	_cone = MeshInstance3D.new()
	var cone_mesh := ImmediateMesh.new()
	_cone.mesh = cone_mesh
	var cmat := StandardMaterial3D.new()
	cmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	cmat.albedo_color = Color(0.55, 0.75, 0.35, 0.10)
	cmat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	cmat.cull_mode = BaseMaterial3D.CULL_DISABLED
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
			_go_to(_player.global_position, chase_speed, delta)
			if global_position.distance_to(_player.global_position) < CATCH_DISTANCE:
				_catch()
	_update_visuals()


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
	if score > 0:
		last_known = _player.global_position
	return score


func _update_suspicion(vis: float, delta: float) -> void:
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


func _catch() -> void:
	set_physics_process(false)
	GameState.end_night(false)


func _update_visuals() -> void:
	var mat := _cone.material_override as StandardMaterial3D
	match state:
		State.CALM:
			mat.albedo_color = Color(0.55, 0.75, 0.35, 0.10)
			_label.text = ""
		State.CURIOUS:
			mat.albedo_color = Color(0.95, 0.8, 0.25, 0.18)
			_label.text = "?"
		State.SEARCHING:
			mat.albedo_color = Color(0.95, 0.5, 0.15, 0.22)
			_label.text = "!?"
		State.ALARM:
			mat.albedo_color = Color(0.9, 0.15, 0.1, 0.28)
			_label.text = "!!"
