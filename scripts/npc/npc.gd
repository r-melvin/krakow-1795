extends "res://scripts/npc/walker.gd"
## Ambient townsperson. Loads the first existing model from a candidate list, then either
##  - follows a schedule of posts (data/npcs.json "schedule"), walking between them on the navmesh and
##    playing an activity at each, or
##  - with no schedule, stands (idle, occasional slow turn) or wanders within a radius of its post.
## A storyline (storyline.gd) can take control with claim() / release() and drive it with the script_* calls.
## Phase F (docs/STEALTH.md 3.7): `enforcer` (data/npcs.json `enforcer: true`, or the mission's `stealth.enforcers`)
## knows the player's face: if he sees the disguised player within recognise_dist for recognise_secs
## (data/zones.json `enforcer`), he barks and calls the nearest guard (watch.report). `zone_permit` (data) lists the
## zones this townsperson belongs in (the journal map notes it). Enforcers join group "enforcer_npc".

enum Mode { AMBIENT, GOING, DOING, SCRIPTED, DOWNED }

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
var enforcer := false             ## knows the player's face through any disguise (phase F)
var zone_permit: Array = []       ## zones (data/zones.json) this townsperson belongs in
var recognise_target: Node3D      ## test sandbox: the player to recognise (else group "player")
var recognised := 0               ## times this enforcer called the watch

static var _roster: Dictionary = {}   ## npc id -> data/npcs.json entry (enforcer / zone_permit lookup)
var _recognise_t := 0.0
var _recognise_cd := 0.0
var _recognise_poll := 0.0

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

# Knocked down (player takedown): lies still for `_down_left` seconds, then gets up and resumes.
var _down_left := 0.0
var _mode_before_down: Mode = Mode.AMBIENT
var _rising := false              ## the get_up clip is playing (still DOWNED until it ends)


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
	_read_phase_f()
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
	Assets.play(_figure, clip if clip != "" and clip != "idle" else _idle_clip())


## Standing-about clip from the data: sitting (behaviour/activity "sit"), gossips talk, stallholders and traders
## haggle, lookouts stand alert; everyone else idles.
func _idle_clip(activity: String = "") -> String:
	if activity == "sit" or behaviour == "sit":
		return "sit_idle"
	var r := role.to_lower()
	if "rumour" in r or "gossip" in r or "neighbour" in r:
		return "talk_gesture_a" if hash(npc_id) % 2 == 0 else "talk_gesture_b"
	if "merchant" in r or "stall" in r or "loaves" in r:
		return "haggle"
	if "lookout" in r or "watching" in r or "informer" in r or "loitering" in r:
		return "idle_alert"
	return "idle"


func _physics_process(delta: float) -> void:
	if enforcer:
		_recognise(delta)
	var clock := GameState.clock_minutes
	var game_dt := maxf(clock - _last_clock, 0.0)
	_last_clock = clock
	match mode:
		Mode.DOWNED:
			halt(delta)
			_down_left -= delta
			if _down_left <= 0.0:
				if not _rising and Assets.has_clip(_figure, "get_up"):
					_rising = true
					Assets.clear_action(_figure)
					_down_left = Assets.play_action(_figure, "get_up")
				else:
					_get_up()
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


# --- Phase F: enforcers --------------------------------------------------------------------------

func _read_phase_f() -> void:
	if _roster.is_empty():
		var f := FileAccess.open("res://data/npcs.json", FileAccess.READ)
		var d: Variant = JSON.parse_string(f.get_as_text()) if f else null
		if d is Dictionary:
			for e in d.get("npcs", []):
				_roster[str(e.get("id", ""))] = e
	var e: Dictionary = _roster.get(npc_id, {})
	enforcer = bool(e.get("enforcer", false))
	zone_permit = e.get("zone_permit", [])
	if Mission.is_active() and (Mission.data.get("stealth", {}).get("enforcers", []) as Array).has(npc_id):
		enforcer = true
	if enforcer:
		add_to_group("enforcer_npc")


## An enforcer who sees the disguised player close by for long enough calls the watch (a bark, watch.report).
func _recognise(delta: float) -> void:
	_recognise_cd = maxf(0.0, _recognise_cd - delta)
	_recognise_poll -= delta
	if _recognise_poll > 0.0:
		return
	var step := 0.2
	_recognise_poll = step
	var p := recognise_target if recognise_target else get_tree().get_first_node_in_group("player") as Node3D
	if p == null or _recognise_cd > 0.0 or mode == Mode.DOWNED or _hidden or not visible or not p.get("disguised"):
		_recognise_t = 0.0
		return
	var cfg: Dictionary = preload("res://scripts/stealth/zones.gd").db().get("enforcer", {})
	var to := p.global_position - global_position
	to.y = 0.0
	var fwd := -global_transform.basis.z
	fwd.y = 0.0
	var sees := to.length() < float(cfg.get("recognise_dist", 6.0)) and absf(p.global_position.y - global_position.y) < 2.0 \
			and rad_to_deg(fwd.angle_to(to)) < float(cfg.get("cone_deg", 130.0)) * 0.5 \
			and p.get("hidden_spot") == null
	if sees:
		var q := PhysicsRayQueryParameters3D.create(global_position + Vector3(0, 1.6, 0), p.global_position + Vector3(0, 1.4, 0))
		q.exclude = [get_rid(), (p as CollisionObject3D).get_rid()]
		sees = get_world_3d().direct_space_state.intersect_ray(q).is_empty()
	_recognise_t = _recognise_t + step if sees else maxf(0.0, _recognise_t - step)
	if _recognise_t < float(cfg.get("recognise_secs", 2.0)):
		return
	_recognise_t = 0.0
	recognised += 1
	_recognise_cd = float(cfg.get("cooldown_secs", 30.0))
	var Zones := preload("res://scripts/stealth/zones.gd")
	var line := Zones.bark_text("recognise_f" if GameState.gender == "f" else "recognise")
	speech(self, line, 3.0)
	var w := preload("res://scripts/stealth/perception.gd").watch_of(self)
	if w and w.has_method("report"):
		w.report(p.global_position, self)
	else:
		var best: Node = null
		var best_d := INF
		for g in get_tree().get_nodes_in_group("guards"):
			var d := (g as Node3D).global_position.distance_to(global_position)
			if d < best_d and g.has_method("witness"):
				best_d = d
				best = g
		if best:
			best.witness(p.global_position)
	print("[npc] %s recognised the player at %s" % [npc_id, GameState.time_string()])


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
				Assets.play(_figure, _idle_clip())
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
			Assets.play(_figure, _idle_clip(act))
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
		var c := "walk"
		if sp > 2.0:
			c = "jog"
		elif "carrier" in role.to_lower():
			c = "carry_basket"
		Assets.play_move(_figure, c, sp)
	else:
		Assets.play(_figure, _idle_clip())


# --- Storyline control ------------------------------------------------------------------------

func claim() -> void:
	if mode == Mode.DOWNED:
		_mode_before_down = Mode.SCRIPTED
		return
	mode = Mode.SCRIPTED
	_set_hidden(false)
	_script_target = null
	_script_face = null
	_script_clip = "idle"
	script_arrived = true


## Hand back to the schedule (walk back to the current post) or, unscheduled, walk back home.
func release() -> void:
	if mode == Mode.DOWNED:
		_mode_before_down = Mode.AMBIENT
		return
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


# --- Mission hooks ----------------------------------------------------------------------------

## Knocked senseless (non-lethal): lie on the cobbles for `secs`, then get up and carry on.
func knock_down(secs: float) -> void:
	if mode == Mode.DOWNED:
		_down_left = maxf(_down_left, secs)
		return
	_mode_before_down = mode
	mode = Mode.DOWNED
	_down_left = secs
	_script_target = null
	_rising = false
	_shape.disabled = true
	if Assets.has_clip(_figure, "takedown_victim"):
		Assets.play_action(_figure, "takedown_victim", 1.0, true)
	else:
		_figure.rotation.x = -PI * 0.5
		_figure.position.y = 0.18
		Assets.play(_figure, "idle", 0.0)


func is_downed() -> bool:
	return mode == Mode.DOWNED


func _get_up() -> void:
	_rising = false
	_figure.rotation.x = 0.0
	_figure.position.y = 0.0
	Assets.clear_action(_figure)
	_shape.disabled = _hidden
	if _mode_before_down == Mode.SCRIPTED:
		mode = Mode.SCRIPTED
		script_arrived = true
	else:
		mode = Mode.AMBIENT
		release()


## Move instantly (e.g. into an interior set) and stay there as an unscheduled stander facing `yaw`.
func relocate(pos: Vector3, yaw: float) -> void:
	schedule = []
	mode = Mode.AMBIENT
	behaviour = "stand"
	_return_home = false
	_script_target = null
	global_position = pos
	_home = pos
	facing = yaw
	_want_yaw = yaw
	rotation.y = yaw
	velocity = Vector3.ZERO
	_set_hidden(false)
	reset_physics_interpolation()


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
