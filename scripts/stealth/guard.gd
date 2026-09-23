extends CharacterBody3D
class_name Guard

const Walker := preload("res://scripts/npc/walker.gd")
const Perception := preload("res://scripts/stealth/perception.gd")
const Interactable := preload("res://scripts/mission/interactable.gd")
## Austrian watch patrol. Waypoint patrol with a head sweep at each stop, two-zone vision (docs/STEALTH.md 3.3):
##   near  0..near_dist,   near_angle:  sees any posture (scaled by the player's visibility)
##   far   ..view_distance, far_angle:  sees standing; crouching only in full light; never prone
##   peripheral            , peripheral_angle (60% range): catches sprinting
## Cover is two rays (head, chest): head only 0.5, chest only 0.7. Hearing: player.noise (surface-dependent) with
## walls halving the radius, masked by the church bell. Suspicion 0..100 drives CALM / CURIOUS / SEARCHING / ALARM;
## the district's watch coordinator (watch.gd) layers the alert phases, runners, search points, bodies and lures on
## top through `task` (investigate, look, relight, door, search, search_spot, body, follow).
## Non-lethal fighting: 2 health; in ALARM within reach it swings the musket butt at the player every 1.2 s.
## At 0 health, or taken from behind, it is `downed` (senseless) for a while, then wakes up searching; a downed
## guard can be dragged by the player (its child interactable) and hidden in a hiding spot.
## A disguised player (player.disguised) reads as a townsman: sight/hearing count a quarter, unless they
## sprint, crouch or linger within 3 m for more than 4 s. `enforcer` guards ignore the disguise (phase F hook).
## Phase F (scripts/stealth/zones.gd): in a zone the player's outfit does not permit (trespass), the disguise factor
## is void, zones.gd's sight modifier makes him x1.6 sharper, and on sight he goes Curious, Searching after 6 s.
## Enforcers (the Corporal) draw a red edge round their cone. `notoriety_view_mult` (intel.gd: +10 % at notoriety
## >= 30) scales the view like the curfew bell. Errand task "errand" (intel.gd's watch routines: the Corporal's
## glass at the Winiarnia, the midnight relief): walk to `pos`, stand `secs`, no suspicion, then back to the round.
## Kit hooks (scripts/stealth/kit.gd): `stagger(secs, clip)` / `is_staggered()` (a knife parry: block_stagger; flash
## powder: stagger) stand him reeling with no perception and no swing; `dead` (a lethal knife thrust, a pistol ball)
## keeps a downed guard from ever waking. Smoke clouds blind him through kit.gd's entry in `sight_modifiers`.

enum State { CALM, CURIOUS, SEARCHING, ALARM }

@export var waypoints: Array[Vector3] = []
@export var patrol_speed := 1.8
@export var chase_speed := 4.2
@export var view_distance := 14.0
@export var view_angle_deg := 70.0        ## legacy: the far cone uses cone.far_angle from data/stealth.json
@export var hearing_distance := 8.0
@export var wait_at_waypoint := 1.5
@export var guard_name := "Watchman"

var sandbox := false                      ## test world: no GameState / Mission side effects
var target_player: Node3D = null          ## explicit player (sandbox); otherwise group "player"
var enforcer := false                     ## phase F hook: sees through the disguise
var notoriety_view_mult := 1.0            ## intel.gd: base view x1.1 once the player is wanted
var sight_modifiers: Array[Callable] = [] ## phase F hook: (guard, player) -> float, multiplies a sighting

var state: State = State.CALM
var suspicion := 0.0             ## 0..100
var last_known: Vector3
var task: Dictionary = {}        ## current errand from the watch (see header); {} = none
var is_runner := false
var hidden_in: Node = null       ## hiding spot holding this (downed) body
var body_found := false          ## a comrade already found this body
var head_yaw := 0.0              ## radians, the look direction relative to the body
var sees_player := false         ## the player was in sight this frame
var last_seen_t := -100.0        ## watch clock when the player was last perceived
var last_score := 0.0
var caught := false              ## sandbox: _catch() ran

var _wp_index := 0
var _wait := 0.0
var _search_timer := 0.0
var _player: Node3D
var _watch: Node
var _cone: Node3D
var _cone_near: MeshInstance3D
var _cone_far: MeshInstance3D
var _label: Label3D
var _figure: Node3D
var _drag_ia: Area3D

var health := MAX_HEALTH
var downed_left := 0.0            ## seconds left senseless on the cobbles (0 = up)
var _base_view := 0.0
var _base_speed := 0.0
var _ext_view_mult := 1.0         ## curfew bell etc. (set_view_mult)
var _speed_mult := 1.0
var _cone_built_for := Vector2.ZERO
var _linger := 0.0                ## seconds the disguised player has stood within LINGER_DIST
var _near_time := 0.0             ## seconds the player has been within CATCH_DISTANCE while alarmed
var _swing_cd := SWING_WINDUP
var _shape: CollisionShape3D
var _rising := 0.0                ## seconds left of the get_up clip after waking (stands still meanwhile)
var _swings := 0
var _seize_played := false
var _t := 0.0
var _sweep_t := 0.0
var _scan_cd := 0.0
var _runner_post := Vector3.ZERO
var _path: PackedVector3Array = []
var _path_target := Vector3(INF, INF, INF)
var _path_age := 0.0
var _stuck := 0.0
var _task_prio := 0
var _bark_cd := 0.0
var _trespass_now := false        ## the player stands in a zone his outfit does not permit (zones.gd)
var _trespass_t := 0.0            ## seconds this guard has watched the player trespass
var _trespass_gap := 0.0          ## seconds since he last saw the trespasser
var _trespass_stage := 0          ## 0 none, 1 curious barked, 2 searching barked
var _cone_edge: MeshInstance3D    ## enforcers: red rim round the near wedge
var _cone_edge_far: MeshInstance3D
var dead := false                  ## kit.gd: killed (knife thrust with `lethal`, pistol ball): never wakes
var stagger_left := 0.0            ## kit.gd: parried or blinded by flash powder: reels on the spot, perceives nothing

const CATCH_DISTANCE := 1.3
const CATCH_TIME := 2.0           ## seconds held within CATCH_DISTANCE (while the player is not fighting back)
const MAX_HEALTH := 2
const REACH := 1.6
const SWING_EVERY := 1.2
const SWING_WINDUP := 0.6
const DISGUISE_FACTOR := 0.25
const LINGER_DIST := 3.0
const LINGER_TIME := 4.0
const TASK_PRIO := {"errand": 1, "look": 1, "follow": 2, "investigate": 2, "door": 2, "relight": 2, "search": 3, "search_spot": 4, "body": 4}


func _ready() -> void:
	if not sandbox:
		add_to_group("guards")
	_base_view = view_distance
	_base_speed = patrol_speed
	_build_visuals()
	if waypoints.is_empty():
		waypoints = [global_position]
	last_known = global_position
	_player = target_player if target_player else get_tree().get_first_node_in_group("player") as Node3D
	_sweep_t = randf() * 10.0


func T(path: String, fallback: Variant = 0.0) -> Variant:
	if _watch and is_instance_valid(_watch):
		return _watch.tv(path, fallback)
	return Perception.tg(path, fallback)


func _now() -> float:
	return _watch.clock if _watch and is_instance_valid(_watch) else _t


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
	elif not sandbox:
		fig.set_meta("anim_role", "guard")
	add_child(fig)

	# Vision cone: two flat wedges on the ground (near zone always; the far zone fades in with suspicion).
	_cone = Node3D.new()
	_cone.position.y = 0.05
	add_child(_cone)
	_cone_near = _wedge_instance()
	_cone_far = _wedge_instance()
	_cone.add_child(_cone_near)
	_cone.add_child(_cone_far)
	_rebuild_cone()

	_label = Label3D.new()
	_label.position.y = 2.2
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_label.font_size = 40
	_label.pixel_size = 0.005
	add_child(_label)

	# A downed guard can be dragged (hold E).
	_drag_ia = Interactable.new()
	_drag_ia.name = "DragBody"
	_drag_ia.display_name = guard_name
	_drag_ia.marker_height = 0.9
	_drag_ia.prompt_func = func() -> String:
		if downed_left <= 0.0 or hidden_in != null or visible == false:
			return ""
		if _player and _player.get("dragging") == self:
			return ""
		return "drag the body (hold)"
	_drag_ia.handler = func(actor: Node) -> bool:
		return actor.has_method("start_drag") and actor.start_drag(self)
	add_child(_drag_ia)


func _wedge_instance() -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = ImmediateMesh.new()
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var cmat := StandardMaterial3D.new()
	# Additive and dim: a faint tint on the cobbles that can never turn into a solid slab, whatever the exposure.
	cmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	cmat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	cmat.albedo_color = Color(0.035, 0.06, 0.02, 1.0)
	cmat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	cmat.cull_mode = BaseMaterial3D.CULL_DISABLED
	cmat.disable_receive_shadows = true
	mi.material_override = cmat
	return mi


func _rebuild_cone() -> void:
	var near_d := float(T("cone.near_dist", 5.0))
	_wedge(_cone_near.mesh as ImmediateMesh, 0.0, near_d, float(T("cone.near_angle", 90.0)))
	_wedge(_cone_far.mesh as ImmediateMesh, near_d, view_distance, float(T("cone.far_angle", 60.0)))
	_cone_built_for = Vector2(view_distance, near_d)
	if _cone_edge:
		_edge(_cone_edge.mesh as ImmediateMesh, 0.0, near_d, float(T("cone.near_angle", 90.0)), true)
		_edge(_cone_edge_far.mesh as ImmediateMesh, near_d, view_distance, float(T("cone.far_angle", 60.0)), false)


## A thin rim along a wedge (outer arc, plus the two sides when `sides`): the enforcer's red edge.
static func _edge(im: ImmediateMesh, r0: float, r1: float, angle_deg: float, sides: bool, w: float = 0.14) -> void:
	im.clear_surfaces()
	im.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	var half := deg_to_rad(angle_deg * 0.5)
	var steps := 20
	for i in steps:
		var a0 := -half + (2 * half) * float(i) / steps
		var a1 := -half + (2 * half) * float(i + 1) / steps
		var d0 := Vector3(sin(a0), 0, -cos(a0))
		var d1 := Vector3(sin(a1), 0, -cos(a1))
		for v in [d0 * (r1 - w), d0 * r1, d1 * r1, d0 * (r1 - w), d1 * r1, d1 * (r1 - w)]:
			im.surface_add_vertex(v)
	if sides:
		for sgn in [-1.0, 1.0]:
			var d := Vector3(sin(half * sgn), 0, -cos(half * sgn))
			var n := Vector3(-d.z, 0, d.x) * w * (1.0 if sgn < 0 else -1.0)
			for v in [d * maxf(r0, 0.4), d * r1, d * r1 + n, d * maxf(r0, 0.4), d * r1 + n, d * maxf(r0, 0.4) + n]:
				im.surface_add_vertex(v)
	im.surface_end()


func _build_edges() -> void:
	_cone_edge = _wedge_instance()
	_cone_edge_far = _wedge_instance()
	for e in [_cone_edge, _cone_edge_far]:
		var m := (e as MeshInstance3D).material_override as StandardMaterial3D
		m.albedo_color = Color(0.55, 0.04, 0.03, 1.0)
		(e as MeshInstance3D).position.y = 0.005
		_cone.add_child(e)
	_cone_built_for = Vector2.ZERO
	_rebuild_cone()


static func _wedge(im: ImmediateMesh, r0: float, r1: float, angle_deg: float) -> void:
	im.clear_surfaces()
	im.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	var half := deg_to_rad(angle_deg * 0.5)
	var steps := 16
	for i in steps:
		var a0 := -half + (2 * half) * float(i) / steps
		var a1 := -half + (2 * half) * float(i + 1) / steps
		var d0 := Vector3(sin(a0), 0, -cos(a0))
		var d1 := Vector3(sin(a1), 0, -cos(a1))
		im.surface_add_vertex(d0 * r0)
		im.surface_add_vertex(d0 * r1)
		im.surface_add_vertex(d1 * r1)
		if r0 > 0.0:
			im.surface_add_vertex(d0 * r0)
			im.surface_add_vertex(d1 * r1)
			im.surface_add_vertex(d1 * r0)
	im.surface_end()


func _physics_process(delta: float) -> void:
	_t += delta
	if _watch == null or not is_instance_valid(_watch):
		_watch = Perception.watch_of(self)
		if _watch:
			_watch.register_guard(self)
			refresh_mults()
	if _player == null or not is_instance_valid(_player):
		_player = target_player if target_player else get_tree().get_first_node_in_group("player") as Node3D
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
	if stagger_left > 0.0:
		stagger_left -= delta
		sees_player = false
		last_score = 0.0
		velocity = Vector3.ZERO
		_swing_cd = SWING_WINDUP
		_near_time = 0.0
		return
	_bark_cd = maxf(0.0, _bark_cd - delta)
	if is_runner:
		sees_player = false
		_run(delta)
		_update_head(delta, false)
		_update_visuals()
		_animate(Vector2(velocity.x, velocity.z).length())
		return
	var vis := _perceive()
	_update_suspicion(vis, delta)
	_scan_cd -= delta
	if _scan_cd <= 0.0:
		_scan_cd = 0.4
		_scan_world()
	var sweeping := false
	match state:
		State.CALM:
			if not _do_task(delta):
				sweeping = _patrol(delta)
			else:
				sweeping = task.get("sweep", false)
		State.CURIOUS:
			if not _do_task(delta):
				_halt(delta)
				_face(last_known, delta)
				sweeping = true
			else:
				sweeping = task.get("sweep", false)
		State.SEARCHING:
			if not _do_task(delta):
				sweeping = _search(delta)
			else:
				sweeping = task.get("sweep", false)
		State.ALARM:
			_fight(delta)
	_update_head(delta, sweeping)
	_update_visuals()
	_animate(Vector2(velocity.x, velocity.z).length())


## State machine -> clip: shoulder arms on patrol and at post, port arms scanning when curious or searching,
## running at the charge, bayonet guard in reach (swings and seizures are one-shots from _fight).
func _animate(planar: float) -> void:
	if is_runner:
		if planar > 0.3:
			Assets.play_move(_figure, "run", planar)
		else:
			Assets.play(_figure, "idle_alert")
		return
	match state:
		State.CALM:
			if planar > 2.6:
				Assets.play_move(_figure, "jog", planar)
			elif planar > 0.3:
				Assets.play_move(_figure, "guard_march", planar)
			elif task.get("kind", "") == "relight" and task.get("arrived", false):
				Assets.play(_figure, "sweep")
			else:
				Assets.play(_figure, "guard_sentry")
		State.CURIOUS:
			if planar > 0.3:
				Assets.play_move(_figure, "guard_march", planar)
			else:
				Assets.play(_figure, "guard_alert_look")
		State.SEARCHING:
			if planar > 2.6:
				Assets.play_move(_figure, "jog", planar)
			elif planar > 0.3:
				Assets.play_move(_figure, "guard_march", planar)
			else:
				Assets.play(_figure, "guard_alert_look")
		State.ALARM:
			if planar > 0.3:
				Assets.play_move(_figure, "run", planar)
			else:
				Assets.play(_figure, "musket_ready")


# ------------------------------------------------------------------ perception

func _look_dir() -> Vector3:
	var f := -global_transform.basis.z
	f.y = 0.0
	return f.normalized().rotated(Vector3.UP, head_yaw)


func _eye() -> Vector3:
	return global_position + Vector3(0, 1.5, 0)


## Returns 0..1 how well this guard currently perceives the player.
func _perceive() -> float:
	sees_player = false
	last_score = 0.0
	if _player == null or _player.get("health") != null and int(_player.get("health")) <= 0:
		return 0.0
	var eye := _eye()
	var head: Vector3 = _player.head_position()
	var chest: Vector3 = _player.chest_position() if _player.has_method("chest_position") else _player.global_position + Vector3(0, 1.0, 0)
	var to_player := head - eye
	var dist := to_player.length()
	var score := 0.0
	var space := get_world_3d().direct_space_state
	var hidden: bool = _player.get("hidden_spot") != null and _player.hidden_spot.get("hides_player")
	var zones: Node = _watch.get("zones") if _watch and is_instance_valid(_watch) else null
	_trespass_now = zones != null and zones.trespassing(_player)

	# Hearing: radius from the player's noise (surface-dependent), halved through walls, masked by the bell.
	var noise: float = float(_player.get("noise")) if _player.get("noise") != null else 0.0
	if noise > 0.0 and not hidden and not (_watch and _watch.masked()):
		var r := hearing_distance * noise * 1.5
		if dist < r and not Perception.clear_line(space, eye, chest, [get_rid()], _player, true):
			r *= float(T("noise.wall_factor", 0.5))
		if dist < r:
			score = maxf(score, 0.35 * minf(noise, 1.0))

	# Sight: two-zone cone plus peripheral vision for sprinting.
	var vis: float = float(_player.get("visibility")) if _player.get("visibility") != null else 1.0
	if not hidden and vis > 0.0 and dist < view_distance:
		var flat := Vector3(to_player.x, 0.0, to_player.z)
		var ang := rad_to_deg(_look_dir().angle_to(flat.normalized())) if flat.length() > 0.01 else 0.0
		var posture: int = _player.posture() if _player.has_method("posture") else 0
		var light: float = float(_player.get("light_level")) if _player.get("light_level") != null else 1.0
		var zone := ""
		if dist <= float(T("cone.near_dist", 5.0)) and ang <= float(T("cone.near_angle", 90.0)) * 0.5:
			zone = "near"
		elif ang <= float(T("cone.far_angle", 60.0)) * 0.5:
			if posture == 0 or posture == 3 or (posture == 1 and light >= float(T("light.full_light", 0.75))):
				zone = "far"
		if zone == "" and ang <= float(T("cone.peripheral_angle", 110.0)) * 0.5 and dist <= view_distance * 0.6 \
				and bool(_player.get("is_sprinting")):
			zone = "peripheral"
		if zone != "":
			var cover := _cover(space, eye, head, chest)
			if cover > 0.0:
				var falloff := 1.0 - (dist / view_distance)
				var s := (0.3 + 0.7 * falloff) * vis * cover
				if zone == "peripheral":
					s *= 0.6
				for m in sight_modifiers:
					if m.is_valid():
						s *= float(m.call(self, _player))
				if s > 0.0:
					sees_player = true
					score = maxf(score, s)
	if score > 0 and _player.get("disguised") and not enforcer and not _trespass_now \
			and not (_player.is_sprinting or _player.is_crouching or _linger > LINGER_TIME):
		score *= DISGUISE_FACTOR
	if score > 0:
		last_known = _player.global_position
		last_seen_t = _now()
		if _watch:
			_watch.report_sighting(self, last_known)
	last_score = score
	return score


## 1 = fully in view, 0.5 = only the head (leaning out, low wall), 0.7 = only the chest, 0 = hidden.
func _cover(space: PhysicsDirectSpaceState3D, eye: Vector3, head: Vector3, chest: Vector3) -> float:
	var h := Perception.clear_line(space, eye, head, [get_rid()], _player)
	var c := Perception.clear_line(space, eye, chest, [get_rid()], _player)
	if h and c:
		return 1.0
	if h:
		return float(T("cover.head_only", 0.5))
	if c:
		return float(T("cover.chest_only", 0.7))
	return 0.0


func saw_player_within(secs: float) -> bool:
	return _now() - last_seen_t <= secs


func _update_suspicion(vis: float, delta: float) -> void:
	if global_position.distance_to(_player.global_position) < LINGER_DIST:
		_linger += delta
	else:
		_linger = 0.0
	var cur := float(T("suspicion.curious", 20.0))
	var srch := float(T("suspicion.searching", 60.0))
	if vis > 0:
		suspicion += float(T("suspicion.gain", 45.0)) * vis * delta
	else:
		var floor_s := 0.0
		if not task.is_empty() and task.get("kind", "") != "look" and task.get("kind", "") != "errand":
			floor_s = cur + 5.0
		if _watch and _watch.phase == _watch.Phase.EVASION and state >= State.SEARCHING:
			floor_s = srch + 1.0
		if suspicion > floor_s:
			suspicion = maxf(floor_s, suspicion - float(T("suspicion.decay", 12.0)) * delta)
	_trespass_react(delta, cur, srch)
	suspicion = clampf(suspicion, 0, 100)

	var new_state := state
	if suspicion >= float(T("suspicion.alarm", 100.0)):
		new_state = State.ALARM
	elif suspicion >= srch:
		new_state = State.SEARCHING
	elif suspicion >= cur:
		new_state = State.CURIOUS
	elif state != State.ALARM or suspicion <= 0:
		new_state = State.CALM
	if state == State.ALARM and new_state != State.ALARM:
		# alarm sticks while the watch is in its ALARM phase (without a watch: until suspicion fully decays)
		if (_watch and _watch.phase == _watch.Phase.ALARM) or (_watch == null and suspicion > 0):
			new_state = State.ALARM
	if new_state != state:
		var old := state
		state = new_state
		match new_state:
			State.CURIOUS:
				if old == State.CALM and task.is_empty():
					_bark("curious")
			State.SEARCHING:
				_search_timer = 6.0
				if old < State.SEARCHING and task.is_empty():
					_bark("searching")
			State.ALARM:
				task = {}
				_task_prio = 0
				_bark("alarm")
				if _watch:
					_watch.on_guard_alarm(self)
				elif not sandbox:
					GameState.raise_alarm(guard_name)
			State.CALM:
				if old != State.ALARM and task.is_empty():
					_bark("calm")


## Trespass (zones.gd): Curious the moment he sees the player where the outfit is not allowed, Searching once he
## has watched them stay trespass.searching_secs; a short gap (grace_secs) out of sight does not reset the count.
func _trespass_react(delta: float, cur: float, srch: float) -> void:
	var zones: Node = _watch.get("zones") if _watch and is_instance_valid(_watch) else null
	if zones == null or state == State.ALARM:
		return
	if sees_player and _trespass_now:
		_trespass_gap = 0.0
		_trespass_t += delta
		if suspicion < cur + 1.0:
			suspicion = cur + 1.0
			last_known = _player.global_position
		if _trespass_stage == 0:
			_trespass_stage = 1
			_bark_line("trespass")
		if _trespass_t >= zones.tset("searching_secs", 6.0):
			if suspicion < srch + 1.0:
				suspicion = srch + 1.0
				last_known = _player.global_position
			if _trespass_stage == 1:
				_trespass_stage = 2
				_bark_line("trespass_search", true)
	else:
		_trespass_gap += delta
		if _trespass_gap > zones.tset("grace_secs", 1.5) and (not _trespass_now or not sees_player):
			_trespass_t = 0.0
			if _trespass_gap > 8.0:
				_trespass_stage = 0


## A glossed line from zones.json barks (trespass, trespass_search): "text\n(gloss)" over his head.
func _bark_line(kind: String, force := false) -> void:
	if _bark_cd > 0.0 and not force:
		return
	var Zones := preload("res://scripts/stealth/zones.gd")
	var text := Zones.bark_text(kind)
	if text == "":
		return
	_bark_cd = 2.5
	Walker.speech(self, text, 2.6, 2.3)
	if _watch:
		_watch.barked.emit(self, kind, text)


func is_trespass_seen() -> bool:
	return _trespass_now and sees_player


func _bark(kind: String) -> void:
	if _bark_cd > 0.0 and kind != "alarm":
		return
	_bark_cd = 2.5
	if _watch:
		_watch.bark(self, kind)
	else:
		Walker.speech(self, Perception.pick(Perception.tg("barks." + kind, [])), 2.0, 2.3)


## Every 0.4 s: bodies of comrades and doused lamps in view.
func _scan_world() -> void:
	if _watch == null or state == State.ALARM:
		return
	var space := get_world_3d().direct_space_state
	var eye := _eye()
	var look := _look_dir()
	var spot_d := float(T("bodies.spot_distance", 12.0))
	for g in _watch.guards():
		if g == self or not g.is_downed() or g.body_found or g.hidden_in != null or not g.visible:
			continue
		var bp: Vector3 = g.global_position + Vector3(0, 0.3, 0)
		var to := bp - eye
		if to.length() > spot_d:
			continue
		var flat := Vector3(to.x, 0, to.z)
		if rad_to_deg(look.angle_to(flat.normalized())) > 55.0 and flat.length() > 2.5:
			continue
		if not Perception.clear_line(space, eye, bp, [get_rid(), g.get_rid()], null, true):
			continue
		find_body(g)
		return
	if state == State.CALM or state == State.CURIOUS:
		for l in _watch.lamps():
			if not l.is_doused() or (l.claimed_by != null and is_instance_valid(l.claimed_by)):
				continue
			var lp: Vector3 = l.head_position()
			var to2 := lp - eye
			if to2.length() > view_distance:
				continue
			var flat2 := Vector3(to2.x, 0, to2.z)
			if rad_to_deg(look.angle_to(flat2.normalized())) > float(T("cone.far_angle", 60.0)) * 0.5 + 10.0:
				continue
			if not Perception.clear_line(space, eye, lp, [get_rid()], null, true):
				continue
			if set_task({"kind": "relight", "lamp": l, "pos": l.stand_position()}):
				l.claimed_by = self
				suspicion = maxf(suspicion, float(T("suspicion.curious", 20.0)) + 5.0)
				_bark("lamp")
			return


func find_body(g: Node) -> void:
	g.body_found = true
	suspicion = maxf(suspicion, float(T("suspicion.searching", 60.0)) + 5.0)
	last_known = g.global_position
	set_task({"kind": "body", "body": g, "pos": g.global_position}, true)
	_bark("body")
	if _watch:
		_watch.on_body_found(g, self)


# ------------------------------------------------------------------ tasks (the watch's errands)

func can_investigate() -> bool:
	return downed_left <= 0.0 and not is_runner and state != State.ALARM and _task_prio <= TASK_PRIO["investigate"]


## Replaces the current task if `t` has at least its priority (or `force`). Returns true if taken.
func set_task(t: Dictionary, force := false) -> bool:
	if is_runner or downed_left > 0.0 or state == State.ALARM:
		return false
	var prio: int = TASK_PRIO.get(t.get("kind", ""), 1)
	if not force and not task.is_empty() and prio < _task_prio:
		return false
	_release_task()
	task = t
	task["t"] = 0.0
	_task_prio = prio
	_path_target = Vector3(INF, INF, INF)
	return true


func _release_task() -> void:
	if task.is_empty():
		return
	var l: Variant = task.get("lamp")
	if l != null and is_instance_valid(l) and l.claimed_by == self:
		l.claimed_by = null
	task = {}
	_task_prio = 0


## A lure (coin, knock, barrel, horse): walk there and look around for `secs`.
func investigate(pos: Vector3, secs: float, kind: String = "noise") -> void:
	var t := {"kind": "investigate", "pos": pos, "secs": secs, "source": kind, "run": kind == "barrel"}
	if kind == "door" or kind == "knock":
		t["kind"] = "door"
	if set_task(t):
		last_known = pos
		suspicion = maxf(suspicion, float(T("suspicion.curious", 20.0)) + 5.0)
		_bark("noise")


## Turn and look at a point or node for `secs`. `force` (the church bell) interrupts errands up to lure priority.
func look_toward(target: Variant, secs: float, force := false) -> void:
	set_task({"kind": "look", "target": target, "secs": secs}, force and _task_prio <= TASK_PRIO["investigate"])


func follow_node(n: Node3D, secs: float) -> void:
	if set_task({"kind": "follow", "target": n, "secs": secs}):
		suspicion = maxf(suspicion, float(T("suspicion.curious", 20.0)) + 5.0)


## A non-lure noise in earshot (dropped crate, sprinting feet heard via the watch).
func hear_noise(pos: Vector3, loudness: float) -> void:
	suspicion = minf(99.0, suspicion + 12.0 * loudness)
	last_known = pos
	if state == State.CALM or state == State.CURIOUS:
		look_toward(pos, 1.5)


## Seen the player slip into `spot`: go and search it (finds them).
func search_spot(spot: Node) -> void:
	if set_task({"kind": "search_spot", "spot": spot, "pos": spot.search_point()}, true):
		suspicion = maxf(suspicion, float(T("suspicion.searching", 60.0)) + 2.0)
		last_known = spot.global_position


func _do_task(delta: float) -> bool:
	if task.is_empty():
		return false
	task["t"] = float(task["t"]) + delta
	task["sweep"] = false
	var done := false
	var kind: String = task.get("kind", "")
	var spd := patrol_speed * _speed_mult
	if float(task["t"]) > float(task.get("max_t", 40.0)):
		done = true
	match kind:
		"look":
			_halt(delta)
			var tg: Variant = task.get("target")
			if tg is Node3D:
				if is_instance_valid(tg):
					_face((tg as Node3D).global_position, delta)
			elif tg is Vector3:
				_face(tg, delta)
			done = done or float(task["t"]) >= float(task.get("secs", 2.0))
		"investigate", "search", "search_spot":
			var pos: Vector3 = task["pos"]
			var arrive := 1.1
			if not task.get("arrived", false):
				var run: bool = task.get("run", false)
				if _nav_go(pos, (chase_speed * 0.8 if run else spd * 1.3), delta, arrive):
					task["arrived"] = true
					task["at"] = float(task["t"])
			else:
				_halt(delta)
				task["sweep"] = true
				var look_secs := float(task.get("secs", T("phases.search_look_secs", 2.5)))
				if kind == "search_spot" or task.get("spot") != null:
					look_secs = float(T("hiding.search_secs", 2.5))
					var sp: Node = task.get("spot")
					if sp and is_instance_valid(sp):
						_face(sp.global_position, delta)
						task["sweep"] = false
				if float(task["t"]) - float(task["at"]) >= look_secs:
					done = true
					var sp2: Node = task.get("spot")
					if sp2 and is_instance_valid(sp2):
						var res: String = sp2.search(self, kind == "search_spot")
						if res == "player":
							task = {}
							_task_prio = 0
							last_known = _player.global_position
							suspicion = 100.0
							_update_suspicion(0.0, 0.0)
							return true
					if kind == "investigate" and state <= State.CURIOUS:
						_bark("calm")
					if kind != "investigate" and _watch:
						_watch._claims.erase(self)
		"door":
			var door: Node = task.get("door")
			var pos2: Vector3 = task["pos"]
			if door == null:
				for d in get_tree().get_nodes_in_group("knock_door"):
					if Perception.same_world(d, self) and (d as Node3D).global_position.distance_to(pos2) < 2.5:
						door = d
						task["door"] = d
			var stand: Vector3 = door.stand_position() if door and is_instance_valid(door) else pos2
			if not task.get("arrived", false):
				if _nav_go(stand, spd * 1.3, delta, 0.8):
					task["arrived"] = true
					task["at"] = float(task["t"])
					if door and is_instance_valid(door):
						door.guard_arrived(self)
			else:
				_halt(delta)
				_face(door.global_position if door and is_instance_valid(door) else pos2, delta)
				var hold := float(T("distractions.knock_hold_secs", 10.0)) if door and is_instance_valid(door) and door.is_open() \
						else float(T("phases.search_look_secs", 2.5))
				done = done or float(task["t"]) - float(task["at"]) >= hold
		"relight":
			var lamp: Node = task.get("lamp")
			if lamp == null or not is_instance_valid(lamp) or not lamp.is_doused():
				done = true
			elif not task.get("arrived", false):
				if _nav_go(task["pos"], spd * 1.2, delta, 0.6):
					task["arrived"] = true
					task["at"] = float(task["t"])
			else:
				_halt(delta)
				_face(lamp.global_position, delta)      # back to the square while he fiddles with the wick
				if float(task["t"]) - float(task["at"]) >= float(T("distractions.relight_secs", 5.0)):
					lamp.relight(self)
					done = true
		"body":
			var body: Node = task.get("body")
			if body == null or not is_instance_valid(body):
				done = true
			elif not task.get("arrived", false):
				if _nav_go(body.global_position, chase_speed * 0.7, delta, 1.2):
					task["arrived"] = true
					task["at"] = float(task["t"])
			else:
				_halt(delta)
				_face(body.global_position, delta)
				task["sweep"] = float(task["t"]) - float(task["at"]) > 1.5
				if float(task["t"]) - float(task["at"]) >= float(T("bodies.revive_after", 4.0)):
					if body.is_downed() and body.hidden_in == null:
						body.downed_left = minf(body.downed_left, 0.5)
					done = true
					last_known = global_position
					_search_timer = 6.0
		"errand":
			# a watch routine: walk there at a steady pace, stand a while (game minutes), then back to the round
			if not task.get("arrived", false):
				if _nav_go(task["pos"], spd, delta, 0.9):
					task["arrived"] = true
					task["at"] = float(task["t"])
			else:
				_halt(delta)
				if task.has("face"):
					_face(task["face"], delta)
				var rate := GameState.clock_scale if not sandbox else 1.0
				done = done or (float(task["t"]) - float(task["at"])) * rate >= float(task.get("minutes", 5.0))
		"follow":
			var n: Variant = task.get("target")
			if n == null or not is_instance_valid(n):
				done = true
			else:
				var np: Vector3 = (n as Node3D).global_position
				if global_position.distance_to(np) > 3.0:
					_nav_go(np, spd * 1.4, delta, 2.8)
				else:
					_halt(delta)
					_face(np, delta)
				done = done or float(task["t"]) >= float(task.get("secs", 8.0))
		_:
			done = true
	if done:
		_release_task()
	return true


# ------------------------------------------------------------------ movement

## Patrol; returns true while standing at a waypoint (head sweep).
func _patrol(delta: float) -> bool:
	var target := waypoints[_wp_index]
	var sentry := waypoints.size() <= 2 and waypoints[0].distance_to(waypoints[-1]) < 0.3
	if global_position.distance_to(target) < 0.4 or sentry and global_position.distance_to(target) < 0.8:
		_wait += delta
		_halt(delta)
		if not sentry and _wait >= wait_at_waypoint + float(T("sweep.wait_bonus", 1.5)):
			_wait = 0
			_wp_index = (_wp_index + 1) % waypoints.size()
		return true
	_go_to(target, patrol_speed * _speed_mult, delta)
	return false


## SEARCHING without an errand: during EVASION ask the watch for cover points near the ghost; otherwise go to the
## last-known position and look about for a few seconds, then drop back to Curious.
func _search(delta: float) -> bool:
	if _watch and _watch.phase == _watch.Phase.EVASION:
		var pt: Dictionary = _watch.next_search_point(self)
		var t := {"kind": "search", "pos": pt["pos"]}
		if pt.has("spot"):
			t["spot"] = pt["spot"]
		set_task(t)
		return false
	var arrived := _nav_go(last_known, patrol_speed * 1.3 * _speed_mult, delta, 1.0)
	_search_timer -= delta
	if _search_timer <= 0 and arrived:
		suspicion = float(T("suspicion.curious", 20.0))
	return arrived


func _halt(delta: float) -> void:
	velocity.x = 0.0
	velocity.z = 0.0
	if not is_on_floor():
		velocity.y -= 18.0 * delta
	move_and_slide()


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


## Walks toward `target` along the district navmesh when one exists (straight line otherwise). True on arrival.
func _nav_go(target: Vector3, speed: float, delta: float, arrive := 0.5) -> bool:
	var flat := Vector2(target.x - global_position.x, target.z - global_position.z)
	if flat.length() < arrive:
		_halt(delta)
		return true
	_path_age += delta
	if target.distance_to(_path_target) > 1.0 or _path_age > 2.5:
		_path_target = target
		_path_age = 0.0
		var map := get_world_3d().navigation_map
		_path = NavigationServer3D.map_get_path(map, global_position, target, true) if NavigationServer3D.map_get_iteration_id(map) > 0 else PackedVector3Array()
	var next := target
	while _path.size() > 0:
		var p := _path[0]
		if Vector2(p.x - global_position.x, p.z - global_position.z).length() < 0.5:
			_path.remove_at(0)
		else:
			next = p
			break
	var before := global_position
	_go_to(Vector3(next.x, global_position.y, next.z), speed, delta)
	if global_position.distance_to(before) < speed * delta * 0.2:
		_stuck += delta
		if _stuck > 2.0:
			_stuck = 0.0
			_path_age = 99.0
			if not task.is_empty():
				return true         # give up: count as arrived so the errand ends
	else:
		_stuck = 0.0
	return false


func _face(target: Vector3, delta: float) -> void:
	var d := target - global_position
	d.y = 0
	if d.length() < 0.01:
		return
	var want := atan2(-d.x, -d.z)
	rotation.y = lerp_angle(rotation.y, want, 6 * delta)


func _update_head(delta: float, sweeping: bool) -> void:
	var want := 0.0
	if sweeping:
		_sweep_t += delta
		var sentry := waypoints.size() <= 2 and waypoints[0].distance_to(waypoints[-1]) < 0.3
		var amp := deg_to_rad(float(T("sweep.sentry_amplitude_deg" if sentry and state == State.CALM else "sweep.amplitude_deg", 50.0)))
		var period := float(T("sweep.period", 4.0)) * (1.6 if sentry and state == State.CALM else 1.0)
		want = sin(_sweep_t * TAU / period) * amp
	head_yaw = lerpf(head_yaw, want, clampf(delta * 3.0, 0.0, 1.0))
	_cone.rotation.y = head_yaw
	if _figure:
		_figure.rotation.y = head_yaw * 0.6


## Watch view / speed multipliers (caution) times the mission's (curfew bell). Redraws the cone when it changes.
func refresh_mults() -> void:
	var vm := _ext_view_mult * notoriety_view_mult
	var sm := 1.0
	if _watch and is_instance_valid(_watch):
		vm *= _watch.view_mult()
		sm = _watch.speed_mult()
	_speed_mult = sm
	view_distance = _base_view * vm
	if absf(_cone_built_for.x - view_distance) > 0.01:
		_rebuild_cone()


# ------------------------------------------------------------------ alert phases (called by the watch)

func converge(pos: Vector3) -> void:
	if downed_left > 0.0 or is_runner or state == State.ALARM:
		return
	_release_task()
	last_known = pos
	suspicion = maxf(suspicion, float(T("suspicion.searching", 60.0)) + 5.0)


func start_evasion(ghost_pos: Vector3) -> void:
	if downed_left > 0.0 or is_runner:
		return
	_release_task()
	last_known = ghost_pos
	suspicion = float(T("suspicion.searching", 60.0)) + 8.0
	state = State.SEARCHING
	_search_timer = 6.0


func end_search() -> void:
	if downed_left > 0.0 or is_runner:
		return
	var k: String = task.get("kind", "")
	if k != "relight" and k != "body":
		_release_task()
	suspicion = 0.0
	if state != State.CALM:
		state = State.CALM
		_bark("calm")


func become_runner(post: Vector3, _reason: String) -> void:
	_release_task()
	is_runner = true
	_runner_post = post
	_path_target = Vector3(INF, INF, INF)
	state = State.SEARCHING
	suspicion = maxf(suspicion, float(T("suspicion.searching", 60.0)) + 1.0)


func _run(delta: float) -> void:
	if _nav_go(_runner_post, float(T("runner.speed", 4.0)), delta, 1.2) and global_position.distance_to(_runner_post) < 2.5:
		is_runner = false
		state = State.CALM
		suspicion = 0.0
		if _watch:
			_watch.on_runner_arrived(self)


# ------------------------------------------------------------------ fighting

## ALARM: close in on the player (or the last place he was seen); within reach, swing every SWING_EVERY s. Held
## close for CATCH_TIME s while the player is not fighting back, they are seized.
func _fight(delta: float) -> void:
	var d := global_position.distance_to(_player.global_position)
	var hidden: bool = _player.get("hidden_spot") != null and _player.hidden_spot.get("hides_player")
	if hidden or (not sees_player and d > REACH * 2.0):
		_nav_go(last_known, chase_speed, delta, 0.8)
		_swing_cd = SWING_WINDUP
		_near_time = maxf(0.0, _near_time - delta)
		return
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
	is_runner = false
	suspicion = 100.0
	_update_suspicion(0.0, 0.0)
	Assets.play_action(_figure, "hit_react")


## True if a player standing behind (and within `dist`) would be unseen: rear takedown allowed. A runner has eyes
## only for the road ahead.
func is_unaware_of(p: Node3D, dist: float = 1.5) -> bool:
	if downed_left > 0.0 or (not is_runner and (state == State.SEARCHING or state == State.ALARM)):
		return false
	var to_p := p.global_position - global_position
	to_p.y = 0.0
	if to_p.length() > dist:
		return false
	var fwd := -global_transform.basis.z
	fwd.y = 0.0
	return rad_to_deg(fwd.angle_to(to_p)) > (90.0 if is_runner else 110.0)


## Senseless for `secs`. `in_fight`: downed in open combat (witnesses raise the alarm); otherwise a quiet rear
## takedown. Crackdown now rises only through a runner reaching the Corporal (watch.gd).
func knock_down(secs: float, in_fight: bool) -> void:
	var was_runner := is_runner
	downed_left = secs
	health = 0
	state = State.CALM
	suspicion = 0.0
	_near_time = 0.0
	velocity = Vector3.ZERO
	is_runner = false
	body_found = false
	_release_task()
	head_yaw = 0.0
	if _figure:
		_figure.rotation.y = 0.0
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
	if was_runner and _watch:
		_watch.on_runner_stopped(self)
	var seen_by: Node = null
	var gs: Array = _watch.guards() if _watch else get_tree().get_nodes_in_group("guards")
	for g in gs:
		if g != self and g.has_method("can_see_point") and g.can_see_point(global_position + Vector3(0, 0.8, 0), -1.0, [get_rid()]):
			seen_by = g
			break
	if in_fight:
		for g in gs:
			if g != self and g.has_method("witness"):
				g.witness(global_position)
	if _watch and _watch.has_method("on_guard_downed"):
		_watch.on_guard_downed(self, in_fight, seen_by)
	if Mission.is_active() and not sandbox:
		Mission.on_takedown(self, in_fight)


func is_downed() -> bool:
	return downed_left > 0.0


## kit.gd: parried (block_stagger) or flash-blinded (stagger): stands reeling `secs`, no perception, no swing.
func stagger(secs: float, clip: String = "stagger") -> void:
	if downed_left > 0.0:
		return
	stagger_left = maxf(stagger_left, secs)
	sees_player = false
	if _figure:
		Assets.play_action(_figure, clip if Assets.has_clip(_figure, clip) else "stagger")


func is_staggered() -> bool:
	return stagger_left > 0.0 and downed_left <= 0.0


func _wake() -> void:
	if dead:
		downed_left = 1.0e9
		return
	downed_left = 0.0
	health = MAX_HEALTH
	if hidden_in and is_instance_valid(hidden_in):
		hidden_in.release_body(self)
	hidden_in = null
	visible = true
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
	if _watch and _watch.phase == _watch.Phase.CALM:
		_watch._set_phase(_watch.Phase.CAUTION)


## Another guard went down in a fight at `pos`: if this one can see the spot, full alarm.
func witness(pos: Vector3) -> void:
	if downed_left > 0.0:
		return
	var eye := _eye()
	var to := pos + Vector3(0, 1.0, 0) - eye
	if to.length() > view_distance:
		return
	if rad_to_deg(_look_dir().angle_to(Vector3(to.x, 0, to.z).normalized())) > float(T("cone.peripheral_angle", 110.0)) * 0.5 and to.length() > 4.0:
		return
	var q := PhysicsRayQueryParameters3D.create(eye, pos + Vector3(0, 1.0, 0))
	q.exclude = [get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	if not hit.is_empty() and not (hit.get("collider") is Guard) and not (hit.get("collider") == _player):
		return
	last_known = _player.global_position if _player else pos
	is_runner = false
	suspicion = 100.0
	_update_suspicion(0.0, 0.0)


## True if this guard, awake and on his feet, would see the point `pos` now (in his wide cone, nothing in between).
## Witnessed takedowns and torn bills (intel.gd) ask this; it has no side effects.
func can_see_point(pos: Vector3, max_dist: float = -1.0, exclude: Array = []) -> bool:
	if downed_left > 0.0 or is_runner or not is_inside_tree():
		return false
	var eye := _eye()
	var to := pos - eye
	if to.length() > (max_dist if max_dist > 0.0 else view_distance):
		return false
	var flat := Vector3(to.x, 0, to.z)
	if flat.length() > 1.5 and rad_to_deg(_look_dir().angle_to(flat.normalized())) > float(T("cone.peripheral_angle", 110.0)) * 0.5:
		return false
	return Perception.clear_line(get_world_3d().direct_space_state, eye, pos, [get_rid()] + exclude, _player, true)


## Curfew bell and the like: scale the view distance (1.0 restores it) and redraw the cone.
func set_view_mult(m: float) -> void:
	_ext_view_mult = m
	refresh_mults()


func _catch() -> void:
	caught = true
	set_physics_process(false)
	if sandbox:
		return
	if Mission.is_active():
		Mission.fail("Caught by the watch: " + guard_name)
	else:
		GameState.end_night(false)


## Cone: the near zone is always drawn; the far zone fades in as suspicion rises (hidden when calm).
func _update_visuals() -> void:
	if downed_left > 0.0:
		return
	var near_mat := _cone_near.material_override as StandardMaterial3D
	var far_mat := _cone_far.material_override as StandardMaterial3D
	var col := Color(0.035, 0.06, 0.02, 1.0)
	match state:
		State.CALM:
			_label.text = ""
		State.CURIOUS:
			col = Color(0.16, 0.12, 0.03, 1.0)
			_label.text = "?"
		State.SEARCHING:
			col = Color(0.24, 0.11, 0.03, 1.0)
			_label.text = "!?"
		State.ALARM:
			col = Color(0.30, 0.05, 0.03, 1.0)
			_label.text = "!!"
	if is_runner:
		col = Color(0.22, 0.07, 0.03, 1.0)
		_label.text = "»"
	if enforcer:
		col = col.lerp(Color(0.3, 0.02, 0.02), 0.4)
		if _cone_edge == null:
			_build_edges()
	if _cone_edge:
		_cone_edge.visible = enforcer and not is_runner
	near_mat.albedo_color = col
	var far_k := clampf((suspicion - 3.0) / 45.0, 0.0, 1.0)
	if state >= State.SEARCHING:
		far_k = 1.0
	_cone_far.visible = far_k > 0.01 and not is_runner
	if _cone_edge_far:
		_cone_edge_far.visible = enforcer and _cone_far.visible
	far_mat.albedo_color = Color(col.r * far_k * 0.8, col.g * far_k * 0.8, col.b * far_k * 0.8, 1.0)
