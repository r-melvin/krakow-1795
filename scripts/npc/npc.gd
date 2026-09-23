extends "res://scripts/npc/walker.gd"
## Ambient townsperson. Loads the first existing model from a candidate list, then either
##  - follows a schedule of posts (data/npcs.json "schedule"), walking between them on the navmesh and
##    playing an activity at each, or
##  - with no schedule, stands (idle, occasional slow turn) or wanders within a radius of its post.
## A storyline (storyline.gd) can take control with claim() / release() and drive it with the script_* calls.

enum Mode { AMBIENT, GOING, DOING, SCRIPTED }

var npc_id := "npc"
var candidates: PackedStringArray = []
var behaviour := "stand"          ## "stand" | "wander" | "sit" (sit behaves as stand for now)
var radius := 4.0
var clip := "idle"
var role := ""
var facing := 0.0
var speed := 1.1
var model_name := ""              ## the candidate actually used, "" if none existed

## Resolved schedule: [{at: float (clock minutes, -1 = none), post: String, pos: Vector3, facing: float,
##   activity: String, for: float (game minutes), run: bool, flee_watch: float (m, 0 = off)}]
var schedule: Array = []
var step := -1                    ## current schedule index
var post_name := ""               ## post currently heading to / occupying
var post_changes := 0             ## how many times the schedule moved this NPC to a different post
var mode: Mode = Mode.AMBIENT

var _figure: Node3D
var _shape: CollisionShape3D
var _home: Vector3
var _target: Vector3
var _pause := 0.0
var _turn_timer := 0.0
var _want_yaw := 0.0
var _rng := RandomNumberGenerator.new()
var _triggered: Dictionary = {}   ## schedule index -> true once its "at" time has fired
var _doing_left := 0.0            ## game minutes left at the current post
var _last_clock := 0.0
var _hidden := false

# Storyline control
var _script_target: Variant = null   ## Vector3, Node3D, or null
var _script_keep := 0.0
var _script_run := false
var _script_clip := "idle"
var _script_face: Variant = null     ## Vector3 point or Node3D
var script_arrived := true
var _return_home := false


func _ready() -> void:
	add_to_group("npcs")
	_rng.seed = hash(npc_id)
	_home = global_position
	rotation.y = facing
	_want_yaw = facing
	_turn_timer = _rng.randf_range(3.0, 9.0)
	_pause = _rng.randf_range(0.5, 3.0)
	_target = _home
	_last_clock = GameState.clock_minutes
	_build()
	setup_navigation(0.4, 1.75, 3.2)
	if not schedule.is_empty():
		add_to_group("scheduled")
		_start_schedule()


static func first_existing(names: PackedStringArray) -> String:
	for n in names:
		if ResourceLoader.exists("res://assets/models/%s.glb" % n):
			return n
	return ""


func _build() -> void:
	_shape = CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	# Narrower than the 0.4 m navmesh erosion, which voxel rounding can shave to ~0.3 m at corners.
	cap.radius = 0.22
	cap.height = 1.75
	_shape.shape = cap
	_shape.position.y = 0.875
	add_child(_shape)

	model_name = first_existing(candidates)
	if model_name != "":
		_figure = Assets.character(model_name)
	if _figure == null:
		push_warning("NPC %s: no model among %s, using capsule" % [npc_id, candidates])
		_figure = Node3D.new()
		var mi := MeshInstance3D.new()
		var m := CapsuleMesh.new()
		m.radius = 0.3
		m.height = 1.75
		mi.mesh = m
		mi.position.y = 0.875
		_figure.add_child(mi)
	add_child(_figure)
	_play_rest()
	# Desynchronise identical clips so a crowd does not breathe in unison.
	if _figure.has_meta("anim"):
		var ap: AnimationPlayer = _figure.get_meta("anim")
		if ap.current_animation != "":
			ap.seek(_rng.randf() * ap.current_animation_length, true)


func _play_rest() -> void:
	Assets.play(_figure, clip if clip != "" else "idle")


func _physics_process(delta: float) -> void:
	var clock := GameState.clock_minutes
	var game_dt := maxf(clock - _last_clock, 0.0)
	_last_clock = clock
	match mode:
		Mode.SCRIPTED:
			_scripted(delta)
		Mode.GOING, Mode.DOING:
			_check_time_triggers(clock)
			if mode == Mode.GOING:
				_going(delta)
			else:
				_doing(delta, game_dt)
		_:
			if _return_home:
				if walk_to(_home, speed, delta):
					_return_home = false
				_walk_anim(speed)
			elif behaviour == "wander":
				_wander(delta)
			else:
				_stand(delta)
				halt(delta)


# --- Schedule ---------------------------------------------------------------------------------

func _start_schedule() -> void:
	# Begin at the latest step whose time has already come (all earlier timed steps count as fired).
	var clock := GameState.clock_minutes
	var best := 0
	for i in schedule.size():
		var at: float = schedule[i]["at"]
		if at >= 0.0 and at <= clock:
			_triggered[i] = true
			best = i
	_begin_step(best)


func _check_time_triggers(clock: float) -> void:
	var best := -1
	for i in schedule.size():
		var at: float = schedule[i]["at"]
		if at >= 0.0 and at <= clock and not _triggered.has(i):
			_triggered[i] = true
			best = maxi(best, i)
	if best >= 0 and best != step:
		_begin_step(best)


func _begin_step(i: int) -> void:
	step = i
	var e: Dictionary = schedule[i]
	var p: String = e["post"]
	if p != post_name:
		if post_name != "":
			post_changes += 1
		post_name = p
	_set_hidden(false)
	mode = Mode.GOING


func _advance() -> void:
	var nxt := (step + 1) % schedule.size()
	var at: float = schedule[nxt]["at"]
	if at >= 0.0 and not _triggered.has(nxt) and at > GameState.clock_minutes:
		return   # wait here at the current post until the next step's time has come
	_triggered[nxt] = true
	_begin_step(nxt)


func _going(delta: float) -> void:
	var e: Dictionary = schedule[step]
	var sp := speed * (2.4 if e["run"] else 1.0)
	if walk_to(e["pos"], sp, delta):
		mode = Mode.DOING
		_doing_left = e["for"]
		_want_yaw = e["facing"]
		_pick_target_around(e["pos"], 2.5)
		if e["activity"] == "inside":
			_set_hidden(true)
	_walk_anim(sp)


func _doing(delta: float, game_dt: float) -> void:
	var e: Dictionary = schedule[step]
	var act: String = e["activity"]
	match act:
		"walk":
			# Stroll about the post.
			if _pause > 0.0:
				_pause -= delta
				halt(delta)
				Assets.play(_figure, "idle")
				if _pause <= 0.0:
					_pick_target_around(e["pos"], 2.5)
			elif walk_to(_target, speed * 0.8, delta):
				_pause = _rng.randf_range(2.0, 5.0)
			else:
				_walk_anim(speed * 0.8)
		"inside":
			velocity = Vector3.ZERO
		"sentry":
			halt(delta)
			turn_toward_yaw(e["facing"], delta)
			Assets.play(_figure, "sentry")
		_:   # idle, sit
			halt(delta)
			_turn_timer -= delta
			if _turn_timer <= 0.0:
				_turn_timer = _rng.randf_range(5.0, 12.0)
				_want_yaw = float(e["facing"]) + _rng.randf_range(-0.8, 0.8)
			turn_toward_yaw(_want_yaw, delta, 1.5)
			Assets.play(_figure, "idle")
	_doing_left -= game_dt
	var flee: float = e["flee_watch"]
	if flee > 0.0 and _watch_near(flee):
		_doing_left = 0.0
		_triggered[(step + 1) % schedule.size()] = true   # leave now, whatever the next step's time
	if _doing_left <= 0.0:
		_advance()


func _watch_near(dist: float) -> bool:
	for g in get_tree().get_nodes_in_group("guards"):
		if (g as Node3D).global_position.distance_to(global_position) < dist:
			return true
	return false


## "inside" activity: the NPC has gone in through a door. Hide it and take it out of collision/avoidance.
func _set_hidden(h: bool) -> void:
	if h == _hidden:
		return
	_hidden = h
	visible = not h
	_shape.disabled = h
	if nav_agent:
		nav_agent.avoidance_enabled = not h


func is_inside() -> bool:
	return _hidden


# --- Ambient (no schedule) --------------------------------------------------------------------

func _stand(delta: float) -> void:
	_turn_timer -= delta
	if _turn_timer <= 0.0:
		_turn_timer = _rng.randf_range(5.0, 12.0)
		_want_yaw = facing + _rng.randf_range(-0.9, 0.9)
	rotation.y = lerp_angle(rotation.y, _want_yaw, 0.8 * delta)
	_play_rest()


func _wander(delta: float) -> void:
	if _pause > 0.0:
		_pause -= delta
		halt(delta)
		_play_rest()
		if _pause <= 0.0:
			_pick_target_around(_home, radius)
	elif walk_to(_target, speed, delta):
		_pause = _rng.randf_range(2.0, 6.0)
	else:
		_walk_anim(speed)


func _pick_target_around(centre: Vector3, r: float) -> void:
	var a := _rng.randf() * TAU
	var d := sqrt(_rng.randf()) * r
	_target = centre + Vector3(cos(a) * d, 0.0, sin(a) * d)


func _walk_anim(sp: float) -> void:
	if is_moving():
		Assets.play(_figure, "walk", clampf(sp / 1.3, 0.6, 2.2))
	else:
		Assets.play(_figure, "idle")


# --- Storyline control ------------------------------------------------------------------------

func claim() -> void:
	mode = Mode.SCRIPTED
	_set_hidden(false)
	_script_target = null
	_script_face = null
	_script_clip = "idle"
	script_arrived = true


## Hand back to the schedule (walk back to the current post) or, unscheduled, walk back home.
func release() -> void:
	_script_target = null
	_script_face = null
	if schedule.is_empty():
		mode = Mode.AMBIENT
		_return_home = true
	else:
		_begin_step(step)


## Walk to a point, or keep within `keep` metres of a node (re-targeting as it moves).
func script_goto(target: Variant, keep: float = 0.0, run: bool = false) -> void:
	_script_target = target
	_script_keep = keep
	_script_run = run
	_script_face = null
	script_arrived = false


func script_face(target: Variant) -> void:
	_script_face = target


func script_play(clip_name: String) -> void:
	_script_clip = clip_name


func say(text: String, secs: float) -> void:
	speech(self, text, secs)


func _scripted(delta: float) -> void:
	if _script_target != null:
		var goal: Vector3
		if typeof(_script_target) == TYPE_OBJECT:
			if not is_instance_valid(_script_target):
				_script_target = null
				return
			goal = (_script_target as Node3D).global_position
		else:
			goal = _script_target
		var sp := speed * (2.4 if _script_run else 1.0)
		var dist := Vector2(goal.x - global_position.x, goal.z - global_position.z).length()
		if _script_keep > 0.0:
			# Hold station `keep` metres short of the target.
			if dist <= _script_keep:
				script_arrived = true
				halt(delta)
				turn_toward_point(goal, delta)
				Assets.play(_figure, _script_clip)
				return
			var stand := goal + (global_position - goal).normalized() * _script_keep * 0.9
			walk_to(stand, sp, delta)
		elif walk_to(goal, sp, delta):
			script_arrived = true
			_script_target = null
		_walk_anim(sp)
		return
	halt(delta)
	if _script_face != null:
		var fp: Vector3 = (_script_face as Node3D).global_position if _script_face is Node3D else _script_face
		turn_toward_point(fp, delta)
	Assets.play(_figure, _script_clip)
