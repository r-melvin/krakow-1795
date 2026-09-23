extends Node3D
## The watch coordinator: one per district world (group "watch"; find it with Perception.watch_of(node)).
##  - Alert phases (MGS): CALM -> ALARM (a guard at full alarm: others within converge_radius close in, a runner
##    is sent to the Corporal) -> EVASION (no sighting for lost_secs: evasion_secs of searching cover points near
##    the last-known ghost) -> CAUTION (caution_minutes game-minutes of faster patrols and longer sight) -> CALM.
##  - Crackdown rises only when a runner reaches the Corporal's post (GameState.raise_alarm + crackdown there).
##  - Sound events with rings (`emit_sound`), sound masking (`mask_sound`, the church bell `ring_bell`).
##  - Bodies (downed guards) found by patrols, doused lamps, hiding spots, the ghost outline.
## Hooks for later phases (E: intel, F: disguise zones / enforcers): the signals below, `guard.enforcer`,
## `guard.sight_modifiers` (Callables (guard, player) -> float), `flags` (free-form facts, also mirrored into
## Mission.flags as "stealth_<name>" outside the sandbox).
## `sandbox`: a test world (scripts/stealth/stealth_smoke.gd): no GameState/Mission side effects.

const Perception := preload("res://scripts/stealth/perception.gd")
const Walker := preload("res://scripts/npc/walker.gd")

enum Phase { CALM, ALARM, EVASION, CAUTION }
const PHASE_NAMES := ["CALM", "ALARM", "EVASION", "CAUTION"]

signal phase_changed(phase: int)
signal sound_event(pos: Vector3, loudness: float, kind: String)
signal player_spotted(guard: Node, pos: Vector3)
signal body_found(body: Node, finder: Node)
signal runner_sent(runner: Node)
signal runner_arrived(runner: Node)
signal runner_stopped(runner: Node)
signal hiding_changed(spot: Node, occupied: bool)
signal lamp_changed(lamp: Node, lit: bool)
signal barked(guard: Node, kind: String, text: String)

var sandbox := false
var overrides: Dictionary = {}       ## "section.key" -> value (sandbox tests speed the timers up)
var player: Node3D                   ## explicit player (sandbox); otherwise the group "player" in this world
var phase: Phase = Phase.CALM
var phase_left := 0.0                ## EVASION: seconds; CAUTION: game minutes
var ghost := Vector3.ZERO            ## where the watch last saw the player
var runner: Node = null
var runners_arrived := 0
var runners_stopped := 0
var bodies_found := 0
var flags: Dictionary = {}
var clock := 0.0                     ## seconds since this watch started (guards time their memories with it)
var phase_log: Array = []            ## [[phase name, clock]] for the smoke

var _mask_left := 0.0
var _last_sighting := -100.0
var _guards: Array = []
var _episode_logged := false
var _calm_for := 0.0
var _runner_this_episode := false
var _runner_pending: Variant = null  ## Vector3: a runner is owed once a guard is free (the only one was fighting)
var _claims: Dictionary = {}         ## guard -> Vector3 search point
var _ghost_node: Node3D
var _ghost_mat: ShaderMaterial
var _rings: Array = []               ## [MeshInstance3D, age, dur]
var _ring_shader: Shader
static var _smoke_reported := false
static var _smoke_started := false

const RING_SHADER := """
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled;
uniform float t = 0.0;
uniform vec4 col : source_color = vec4(1.0, 0.8, 0.5, 1.0);
void fragment() {
	vec2 p = UV * 2.0 - 1.0;
	float r = length(p);
	float edge = 0.15 + 0.85 * t;
	float w = 0.03 + 0.02 * t;
	float a = smoothstep(w, 0.0, abs(r - edge)) + 0.35 * smoothstep(w * 3.0, 0.0, abs(r - edge * 0.72)) * (1.0 - t);
	ALBEDO = col.rgb * a * (1.0 - t) * col.a;
}
"""

const GHOST_SHADER := """
shader_type spatial;
render_mode unshaded, blend_add, depth_draw_never, cull_back, shadows_disabled;
uniform vec4 col : source_color = vec4(0.9, 0.55, 0.3, 1.0);
uniform float strength = 1.0;
void fragment() {
	float rim = pow(1.0 - clamp(abs(dot(NORMAL, VIEW)), 0.0, 1.0), 1.8);
	float scan = 0.8 + 0.2 * sin(TIME * 3.0);
	ALBEDO = col.rgb * (rim * 1.4 + 0.07) * strength * scan;
}
"""


func _ready() -> void:
	add_to_group("watch")
	name = "Watch" if not sandbox else name
	_build_ghost()
	_ring_shader = Shader.new()
	_ring_shader.code = RING_SHADER
	phase_log.append([PHASE_NAMES[phase], 0.0])
	if not sandbox and "--smoke" in OS.get_cmdline_user_args() and not _smoke_started:
		_smoke_started = true
		var s: Node = load("res://scripts/stealth/stealth_smoke.gd").new()
		s.name = "StealthSmoke"
		get_tree().root.add_child.call_deferred(s)


func tv(path: String, fallback: Variant = 0.0) -> Variant:
	if overrides.has(path):
		return overrides[path]
	return Perception.tg(path, fallback)


func get_player() -> Node3D:
	if player and is_instance_valid(player):
		return player
	for p in get_tree().get_nodes_in_group("player"):
		if Perception.same_world(p, self):
			player = p
			return p
	return null


func register_guard(g: Node) -> void:
	if not g in _guards:
		_guards.append(g)


func guards() -> Array:
	var out: Array = []
	for g in _guards:
		if is_instance_valid(g) and g.is_inside_tree():
			out.append(g)
	_guards = out
	return out.duplicate()


func awake_guards() -> Array:
	return guards().filter(func(g: Node) -> bool: return not g.is_downed())


func spots() -> Array:
	return get_tree().get_nodes_in_group("hiding_spot").filter(func(s: Node) -> bool: return Perception.same_world(s, self))


func lamps() -> Array:
	return get_tree().get_nodes_in_group("stealth_lamp").filter(func(s: Node) -> bool: return Perception.same_world(s, self))


func masked() -> bool:
	return _mask_left > 0.0


func view_mult() -> float:
	return float(tv("phases.caution_view_mult", 2.0)) if phase == Phase.CAUTION else 1.0


func speed_mult() -> float:
	return float(tv("phases.caution_speed_mult", 2.0)) if phase == Phase.CAUTION else 1.0


func phase_name() -> String:
	return PHASE_NAMES[phase]


func set_flag(key: String, value: Variant = true) -> void:
	flags[key] = value
	if not sandbox and Mission.is_active():
		Mission.set_flag("stealth_" + key, value)


# ------------------------------------------------------------------ phases

func _physics_process(delta: float) -> void:
	clock += delta
	_mask_left = maxf(0.0, _mask_left - delta)
	var gs := guards()
	var any_alarm := false
	var all_calm := true
	for g in gs:
		if g.is_downed():
			continue
		if g.state == g.State.ALARM:
			any_alarm = true
		if g.state != g.State.CALM or g.is_runner:
			all_calm = false
	match phase:
		Phase.CALM, Phase.EVASION, Phase.CAUTION:
			if any_alarm:
				_set_phase(Phase.ALARM)
		Phase.ALARM:
			if not any_alarm or clock - _last_sighting > float(tv("phases.lost_secs", 3.0)):
				_set_phase(Phase.EVASION)
	if phase == Phase.EVASION:
		phase_left -= delta
		if phase_left <= 0.0:
			_set_phase(Phase.CAUTION)
	elif phase == Phase.CAUTION:
		var rate := float(tv("phases.game_minutes_per_sec", 1.0)) * (1.0 if sandbox else GameState.clock_scale)
		phase_left -= delta * rate
		if phase_left <= 0.0:
			_set_phase(Phase.CALM)
	if _runner_pending != null and phase != Phase.ALARM:
		var from: Vector3 = _runner_pending
		_runner_pending = null
		request_runner(from, "alarm")
	if phase == Phase.CALM and all_calm:
		_calm_for += delta
		if _calm_for > 5.0:
			_episode_logged = false
			_runner_this_episode = false
	else:
		_calm_for = 0.0
	if not sandbox and not _smoke_reported and clock > 3.0 and "--smoke" in OS.get_cmdline_user_args():
		_smoke_reported = true
		var lights := get_tree().get_nodes_in_group("flame_lights").filter(func(l: Node) -> bool: return Perception.same_world(l, self))
		var patches := get_tree().get_nodes_in_group("surface_patch").filter(func(l: Node) -> bool: return Perception.same_world(l, self))
		var doors := get_tree().get_nodes_in_group("knock_door").filter(func(l: Node) -> bool: return Perception.same_world(l, self))
		print("[smoke] stealth district lights=%d spots=%d lamps=%d doors=%d surfaces=%d guards=%d phase=%s" % [lights.size(),
				spots().size(), lamps().size(), doors.size(), patches.size(), gs.size(), phase_name()])


func _set_phase(p: Phase) -> void:
	if p == phase:
		return
	var old := phase
	phase = p
	phase_log.append([PHASE_NAMES[p], snappedf(clock, 0.01)])
	match p:
		Phase.ALARM:
			_last_sighting = clock
			var conv := float(tv("phases.converge_radius", 30.0))
			for g in awake_guards():
				if g.state != g.State.ALARM and not g.is_runner and g.global_position.distance_to(ghost) < conv:
					g.converge(ghost)
			if not _runner_this_episode:
				var alarmed: Node = null
				for g in awake_guards():
					if g.state == g.State.ALARM:
						alarmed = g
						break
				request_runner(ghost, "alarm", alarmed)
		Phase.EVASION:
			phase_left = float(tv("phases.evasion_secs", 60.0))
			_claims.clear()
			var first := true
			for g in awake_guards():
				if g.is_runner:
					continue
				if g.state == g.State.ALARM or g.state == g.State.SEARCHING or g.global_position.distance_to(ghost) < float(tv("phases.converge_radius", 30.0)):
					g.start_evasion(ghost)
					if first:
						first = false
						bark(g, "evasion")
		Phase.CAUTION:
			phase_left = float(tv("phases.caution_minutes", 3.0))
			for g in awake_guards():
				if not g.is_runner:
					g.end_search()
		Phase.CALM:
			pass
	if old == Phase.CAUTION or p == Phase.CAUTION:
		for g in guards():
			g.refresh_mults()
	set_flag("phase", PHASE_NAMES[p])
	phase_changed.emit(p)


## A guard perceives the player at `pos` (any state). Alarm sightings keep the ALARM phase alive.
func report_sighting(g: Node, pos: Vector3) -> void:
	if g.state == g.State.ALARM or phase == Phase.ALARM or g.state == g.State.SEARCHING:
		ghost = pos
		if g.state == g.State.ALARM:
			_last_sighting = clock
	player_spotted.emit(g, pos)


## Called by a guard entering ALARM.
func on_guard_alarm(g: Node) -> void:
	ghost = g.last_known
	_last_sighting = clock
	if phase != Phase.ALARM:
		_set_phase(Phase.ALARM)


## Search point for a guard during EVASION (hiding spots near the ghost first, then open points around it).
func next_search_point(g: Node) -> Dictionary:
	var radius := float(tv("phases.search_radius", 9.0))
	var best: Dictionary = {}
	var best_d := INF
	for s in spots():
		if s.kind == "bench":
			continue
		var d: float = s.global_position.distance_to(ghost)
		if d > radius or clock - float(s.last_searched) < 12.0 or _claimed(s.global_position, g):
			continue
		d += g.global_position.distance_to(s.global_position) * 0.3
		if d < best_d:
			best_d = d
			best = {"pos": s.search_point(), "spot": s}
	if not best.is_empty():
		_claims[g] = best["pos"]
		return best
	var space := get_world_3d().direct_space_state
	for attempt in 10:
		var a := randf() * TAU
		var r := randf_range(1.5, radius)
		var p := ghost + Vector3(cos(a) * r, 0.0, sin(a) * r)
		if _claimed(p, g):
			continue
		if not Perception.clear_line(space, ghost + Vector3(0, 1.0, 0), p + Vector3(0, 1.0, 0), [], null, true):
			continue
		_claims[g] = p
		return {"pos": p}
	return {"pos": ghost + Vector3(randf_range(-2, 2), 0, randf_range(-2, 2))}


func _claimed(p: Vector3, g: Node) -> bool:
	for k in _claims:
		if k != g and is_instance_valid(k) and (_claims[k] as Vector3).distance_to(p) < 2.0:
			return true
	return false


# ------------------------------------------------------------------ runner, bodies

## Sends the guard nearest `from_pos` (preferring anyone but `busy`) running to the Corporal's post.
func request_runner(from_pos: Vector3, reason: String, busy: Node = null) -> Node:
	if runner and is_instance_valid(runner) and runner.is_runner:
		return runner
	var best: Node = null
	var best_d := INF
	for g in awake_guards():
		if g == busy or g.is_runner:
			continue
		var d: float = g.global_position.distance_to(from_pos)
		if d < best_d:
			best_d = d
			best = g
	if best == null and busy != null and busy.state != busy.State.ALARM:
		best = busy
	if best == null or best.is_downed():
		# the only guard about is busy fighting: he goes to report once he has lost the player
		_runner_pending = from_pos if busy != null else null
		_runner_this_episode = _runner_pending != null
		return null
	_runner_pending = null
	runner = best
	_runner_this_episode = true
	best.become_runner(Perception.vec(tv("runner.corporal_post", [24.0, 0.0, -10.0])), reason)
	bark(best, "runner")
	runner_sent.emit(best)
	return best


func on_runner_arrived(g: Node) -> void:
	runner = null
	runners_arrived += 1
	if not sandbox:
		GameState.crackdown = clampi(GameState.crackdown + int(tv("runner.crackdown", 5)), 0, 100)
		GameState.raise_alarm(str(g.guard_name))
	set_flag("runner_arrived", runners_arrived)
	runner_arrived.emit(g)


func on_runner_stopped(g: Node) -> void:
	if runner == g:
		runner = null
	runners_stopped += 1
	runner_stopped.emit(g)


func on_body_found(body: Node, finder: Node) -> void:
	bodies_found += 1
	body_found.emit(body, finder)
	if phase == Phase.CALM:
		_set_phase(Phase.CAUTION)
	elif phase == Phase.CAUTION:
		phase_left = float(tv("phases.caution_minutes", 3.0))
	request_runner(body.global_position, "body", finder)


# ------------------------------------------------------------------ sound

## A sound at `pos`. `lure`: the nearest guard in earshot investigates (others glance at it); otherwise guards in
## earshot grow a little suspicious. Returns the investigating guard, if any. Rings show for loud events.
func emit_sound(pos: Vector3, loudness: float, kind: String, lure := false, show_ring := true, notify := true) -> Node:
	if show_ring:
		spawn_ring(pos, loudness, kind)
	sound_event.emit(pos, loudness, kind)
	if not notify or (masked() and kind != "bell"):
		return null
	var space := get_world_3d().direct_space_state
	var hear := float(tv("noise.hearing_distance", 8.0))
	var best: Node = null
	var best_d := INF
	var heard: Array = []
	for g in awake_guards():
		if g.is_runner:
			continue
		var ear: Vector3 = g.global_position + Vector3(0, 1.6, 0)
		var rng := minf(hear * loudness * 2.0, float(tv("distractions.lure_radius", 16.0)) if lure else INF)
		if not Perception.clear_line(space, ear, pos + Vector3(0, 0.4, 0), [g.get_rid()], null, true):
			rng *= float(tv("noise.wall_factor", 0.5))
		var d: float = g.global_position.distance_to(pos)
		if d > rng:
			continue
		heard.append(g)
		if lure and g.can_investigate() and d < best_d:
			best_d = d
			best = g
	for g in heard:
		if g == best:
			g.investigate(pos, float(tv("distractions.investigate_secs", 8.0)), kind)
		elif lure:
			g.look_toward(pos, 2.5)
		else:
			g.hear_noise(pos, loudness)
	return best


func mask_sound(secs: float) -> void:
	_mask_left = maxf(_mask_left, secs)


## Mission hook: the church bell. Masks all sound for bell_mask_secs and turns the watch's eyes to the tower.
func ring_bell(tower: Variant = null) -> void:
	var t := Perception.vec(tower, Perception.vec(tv("distractions.bell_tower", [34.0, 18.0, -38.0])))
	var secs := float(tv("distractions.bell_mask_secs", 4.0))
	mask_sound(secs)
	for g in awake_guards():
		if not g.is_runner and g.state != g.State.ALARM:
			g.look_toward(t, secs, true)
	spawn_ring(Vector3(t.x, 0.05, t.z), 3.0, "bell")
	sound_event.emit(t, 3.0, "bell")


func spawn_ring(pos: Vector3, loudness: float, kind: String) -> void:
	var mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	var r := 1.2 + clampf(loudness, 0.0, 3.0) * 4.0
	pm.size = Vector2(r * 2.0, r * 2.0)
	mi.mesh = pm
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var mat := ShaderMaterial.new()
	mat.shader = _ring_shader
	var col := Color(1.0, 0.82, 0.55, 0.9)
	match kind:
		"step":
			col = Color(0.85, 0.85, 0.9, 0.55)
		"bell":
			col = Color(0.75, 0.8, 1.0, 0.8)
		"body", "alarm":
			col = Color(1.0, 0.35, 0.25, 0.9)
	mat.set_shader_parameter("col", col)
	mi.material_override = mat
	add_child(mi)
	mi.global_position = Vector3(pos.x, pos.y + 0.06, pos.z)
	_rings.append([mi, 0.0, float(tv("rings.secs", 2.0))])


func ring_count() -> int:
	return _rings.size()


# ------------------------------------------------------------------ barks

## Speech bubble over the guard; the first bark of an alert episode also goes to the message line (and journal).
func bark(g: Node, kind: String) -> String:
	var text := Perception.pick(tv("barks." + kind, []))
	if text == "":
		return ""
	Walker.speech(g, text, 2.2, 2.3)
	if not _episode_logged and kind != "calm":
		_episode_logged = true
		if not sandbox:
			Mission.message.emit("%s: “%s”" % [g.guard_name, text], 2.5)
	barked.emit(g, kind, text)
	return text


# ------------------------------------------------------------------ ghost + rings

func _build_ghost() -> void:
	_ghost_node = Node3D.new()
	_ghost_node.name = "Ghost"
	_ghost_mat = ShaderMaterial.new()
	var sh := Shader.new()
	sh.code = GHOST_SHADER
	_ghost_mat.shader = sh
	var body := MeshInstance3D.new()
	var cap := CapsuleMesh.new()
	cap.radius = 0.28
	cap.height = 1.4
	body.mesh = cap
	body.position.y = 0.72
	body.scale = Vector3(1.0, 1.0, 0.7)
	var head := MeshInstance3D.new()
	var sp := SphereMesh.new()
	sp.radius = 0.13
	sp.height = 0.28
	head.mesh = sp
	head.position.y = 1.56
	for m in [body, head]:
		(m as MeshInstance3D).material_override = _ghost_mat
		(m as MeshInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		_ghost_node.add_child(m)
	_ghost_node.visible = false
	add_child(_ghost_node)


## Where the ghost should stand now (EVASION: the watch's ghost; a lone searching guard: his last-known), or null.
func ghost_target() -> Variant:
	if phase == Phase.EVASION:
		return ghost
	var best: Node = null
	for g in guards():
		if g.is_downed() or g.is_runner or g.state != g.State.SEARCHING or not g.task.is_empty():
			continue
		if best == null or g.suspicion > best.suspicion:
			best = g
	return best.last_known if best else null


func _process(delta: float) -> void:
	var gt: Variant = ghost_target()
	var p := get_player()
	var show: bool = gt != null and (p == null or p.global_position.distance_to(gt) > 1.2)
	if show:
		_ghost_node.global_position = _ghost_node.global_position.lerp(gt, clampf(delta * 6.0, 0.0, 1.0)) if _ghost_node.visible else gt
		_ghost_mat.set_shader_parameter("strength", 1.0 if phase == Phase.EVASION else 0.8)
	_ghost_node.visible = show
	for i in range(_rings.size() - 1, -1, -1):
		var r: Array = _rings[i]
		r[1] += delta
		var mi: MeshInstance3D = r[0]
		if r[1] >= r[2] or not is_instance_valid(mi):
			if is_instance_valid(mi):
				mi.queue_free()
			_rings.remove_at(i)
			continue
		(mi.material_override as ShaderMaterial).set_shader_parameter("t", r[1] / r[2])


func ghost_visible() -> bool:
	return _ghost_node.visible
