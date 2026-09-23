extends CharacterBody3D
## Shared locomotion for townsfolk and animals: NavigationAgent3D path following with RVO avoidance
## once the district navmesh is baked, straight-line steering (with stuck detection) before that or
## if no navmesh exists. Subclasses call `walk_to()` each physics frame and `halt()` when idle.

const GRAVITY := 18.0
const ARRIVE_DIST := 0.45

var agent_radius := 0.4
var nav_agent: NavigationAgent3D

var _safe_velocity := Vector3.ZERO
var _desired := Vector3.ZERO
var _last_target := Vector3(INF, INF, INF)
var _stuck := 0.0
var _detour := Vector3.ZERO
var _detour_left := 0.0
var _detours := 0
var _district: Node


func setup_navigation(avoid_radius: float, height: float, max_speed: float) -> void:
	agent_radius = avoid_radius
	nav_agent = NavigationAgent3D.new()
	nav_agent.name = "NavAgent"
	nav_agent.radius = avoid_radius
	nav_agent.height = height
	nav_agent.max_speed = max_speed
	nav_agent.path_desired_distance = 0.35
	nav_agent.target_desired_distance = ARRIVE_DIST
	# The baked surface sits ~0.5 m above the ground plane (voxel rounding); report path points at foot level.
	nav_agent.path_height_offset = 0.5
	nav_agent.avoidance_enabled = true
	nav_agent.neighbor_distance = 6.0
	nav_agent.max_neighbors = 8
	nav_agent.time_horizon_agents = 1.2
	nav_agent.time_horizon_obstacles = 0.5
	add_child(nav_agent)
	nav_agent.velocity_computed.connect(func(v: Vector3) -> void: _safe_velocity = v)


## True once the district's runtime navmesh is baked and synced into the navigation map.
func nav_ready() -> bool:
	if nav_agent == null:
		return false
	if _district == null or not is_instance_valid(_district):
		_district = get_tree().get_first_node_in_group("nav_source")
		if _district == null:
			return false
	return _district.has_method("nav_ready") and _district.nav_ready()


## Steers toward `target` at `speed` for one physics frame. Returns true on arrival (or if the target is
## unreachable and the path is exhausted, or it stays blocked through three sidestep attempts).
## Stationary townsfolk are avoidance agents but do not carve the navmesh, so a knot of people can
## block a corridor: after 1.5 s without progress the walker sidesteps for a moment, then re-paths.
func walk_to(target: Vector3, speed: float, delta: float) -> bool:
	var flat_to := Vector2(target.x - global_position.x, target.z - global_position.z)
	if flat_to.length() < ARRIVE_DIST:
		halt(delta)
		return true
	var next := target
	var use_nav := nav_ready()
	if _detour_left > 0.0:
		_detour_left -= delta
		next = _detour
		if _detour_left <= 0.0:
			_last_target = Vector3(INF, INF, INF)   # force a fresh path
	elif use_nav:
		if target.distance_to(_last_target) > 0.25:
			_last_target = target
			nav_agent.target_position = target
		if nav_agent.is_navigation_finished():
			halt(delta)
			return true
		next = nav_agent.get_next_path_position()
	var dir := Vector3(next.x - global_position.x, 0.0, next.z - global_position.z)
	if dir.length() < 0.01:
		dir = Vector3(flat_to.x, 0.0, flat_to.y)
	dir = dir.normalized()
	_desired = dir * speed
	var v := _desired
	if use_nav:
		nav_agent.velocity = _desired
		if _detour_left <= 0.0:   # sidesteps ignore avoidance, which is what deadlocked us
			v = _safe_velocity
	velocity.x = v.x
	velocity.z = v.z
	var face := v if Vector2(v.x, v.z).length() > 0.1 else _desired
	rotation.y = lerp_angle(rotation.y, atan2(-face.x, -face.z), 6.0 * delta)
	var before := global_position
	_apply_motion(delta)
	var moved := Vector2(global_position.x - before.x, global_position.z - before.z).length()
	if moved < speed * delta * 0.25:
		_stuck += delta
	else:
		_stuck = maxf(_stuck - delta, 0.0)
		if _stuck == 0.0 and _detour_left <= 0.0:
			_detours = 0
	if _stuck > 1.5:
		_stuck = 0.0
		_detours += 1
		if _detours > 3:
			_detours = 0
			return true
		var side := Vector3(-dir.z, 0.0, dir.x) * (1.0 if randf() < 0.5 else -1.0)
		_detour = global_position + side * 1.3 - dir * 0.4
		_detour_left = 1.0
	return false


## Standing still: zero planar velocity, tell avoidance we are stationary, keep gravity.
func halt(delta: float) -> void:
	_desired = Vector3.ZERO
	velocity.x = 0.0
	velocity.z = 0.0
	if nav_agent and nav_agent.avoidance_enabled and nav_ready():
		nav_agent.velocity = Vector3.ZERO
	_apply_motion(delta)


func turn_toward_yaw(yaw: float, delta: float, rate: float = 3.0) -> void:
	rotation.y = lerp_angle(rotation.y, yaw, rate * delta)


func turn_toward_point(p: Vector3, delta: float, rate: float = 4.0) -> void:
	var d := p - global_position
	if Vector2(d.x, d.z).length() > 0.05:
		turn_toward_yaw(atan2(-d.x, -d.z), delta, rate)


func is_moving() -> bool:
	return Vector2(velocity.x, velocity.z).length() > 0.1


func _apply_motion(delta: float) -> void:
	if not is_on_floor():
		velocity.y -= GRAVITY * delta
	else:
		velocity.y = 0.0
	move_and_slide()


## Speech bubble above any Node3D (townsfolk, guards). Replaces a previous bubble on the same node.
## Kept sparse on purpose: nothing is shown beyond SPEECH_RANGE from the player, at most SPEECH_MAX bubbles
## are up at once (guards always get through; the farthest civilian bubble makes room), the English gloss
## under a foreign line only appears within SPEECH_GLOSS_RANGE, and civilian bubbles fade after ~3 s.
const SPEECH_RANGE := 14.0
const SPEECH_GLOSS_RANGE := 7.0
const SPEECH_MAX := 3
static var _bubbles: Array = []

static func speech(node: Node3D, text: String, secs: float, height: float = 2.15) -> void:
	if node == null or not is_instance_valid(node) or not node.is_inside_tree():
		return
	var priority := node.is_in_group("guards") or node.is_in_group("mission")
	var player := node.get_tree().get_first_node_in_group("player") as Node3D
	var dist := 0.0
	if player:
		dist = player.global_position.distance_to(node.global_position)
		if dist > SPEECH_RANGE and not priority:
			return
		if dist > SPEECH_GLOSS_RANGE and "\n(" in text:
			text = text.substr(0, text.find("\n("))
	_bubbles = _bubbles.filter(func(b) -> bool: return is_instance_valid(b) and b.is_inside_tree())
	var old := node.get_node_or_null("SpeechBubble")
	if old:
		old.name = "SpeechBubbleOld"
		_bubbles.erase(old)
		old.queue_free()
	if _bubbles.size() >= SPEECH_MAX:
		if priority and player:
			var far: Node = null
			var far_d := -1.0
			for b in _bubbles:
				var bp := (b.get_parent() as Node3D)
				var d := player.global_position.distance_to(bp.global_position) if bp else 999.0
				if bp and not bp.is_in_group("guards") and d > far_d:
					far = b
					far_d = d
			if far:
				_bubbles.erase(far)
				far.queue_free()
			else:
				return
		else:
			return
	var l := Label3D.new()
	l.name = "SpeechBubble"
	l.text = text
	l.position.y = height
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.font_size = 30 if priority else 26
	l.outline_size = 9
	l.outline_modulate = Color(0.05, 0.04, 0.03, 0.9)
	l.modulate = Color(1.0, 0.95, 0.82) if priority else Color(0.9, 0.86, 0.76, 0.92)
	l.pixel_size = 0.0045
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.width = 460
	l.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
	l.no_depth_test = priority          # civilians' words do not show through walls
	l.render_priority = 5
	node.add_child(l)
	_bubbles.append(l)
	var hold := secs if priority else minf(secs, 3.2)
	var tw := l.create_tween()     # dies with the label, so a freed world leaves no dangling timer
	tw.tween_interval(hold)
	tw.tween_property(l, "modulate:a", 0.0, 0.4)
	tw.tween_callback(l.queue_free)
