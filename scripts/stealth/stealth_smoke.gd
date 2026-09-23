extends Node
## `-- --smoke` stealth checks (started by the first district watch, watch.gd). They run beside the mission smoke,
## each in its own sandbox world (a SubViewport with its own World3D and physics space, offset far from the
## district so no group-based lookup can cross over): sandbox guards / player / watch have no GameState or
## Mission side effects and are not in the "guards" / "player" groups. Prints `[smoke] stealth ...` lines:
## light sampling, surface noise, crowd blending, a hide (a patrol walks past; a guard who saw you go in finds
## you), a lean, a thrown stone pulling a guard, a doused lamp relit, alarm -> evasion -> caution -> calm timing
## with a runner reaching the Corporal, a runner intercepted, a body dragged and hidden.
## `--stealth-shot=/dir` (windowed): a rendered sandbox with the HUD cues saves stealth_*.png.

const WatchScript := preload("res://scripts/stealth/watch.gd")
const GuardScript := preload("res://scripts/stealth/guard.gd")
const PlayerScript := preload("res://scripts/stealth/player.gd")
const HidingSpotScript := preload("res://scripts/stealth/hiding_spot.gd")
const Distraction := preload("res://scripts/stealth/distraction.gd")
const FlickerScript := preload("res://scripts/city/flicker.gd")
const Hud := preload("res://scripts/ui/hud.gd")

const OFFSET := Vector3(700, 0, 700)

var shot_dir := ""
var _pending := 0
var _t0 := 0


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--stealth-shot="):
			shot_dir = a.trim_prefix("--stealth-shot=")
	if DisplayServer.get_name() == "headless":
		shot_dir = ""
	_run()


func _run() -> void:
	await get_tree().process_frame
	_t0 = Engine.get_process_frames()
	print("[smoke] stealth sandbox tests start at frame %d" % _t0)
	var tests: Array[Callable] = [t_light_noise, t_hide, t_lean, t_coin, t_lamp, t_phases, t_runner, t_drag, t_misc]
	if shot_dir != "":
		DirAccess.make_dir_recursive_absolute(shot_dir)
		tests.append(t_shots)
	_pending = tests.size()
	for i in tests.size():
		_launch(tests[i], i)
	while _pending > 0:
		await get_tree().process_frame
	print("[smoke] stealth done at frame %d" % Engine.get_process_frames())


func _launch(c: Callable, i: int) -> void:
	var line: String = await c.call(i)
	print(line)
	_pending -= 1


# ------------------------------------------------------------------ sandbox helpers

func make_world(idx: int, overrides: Dictionary = {}, render := false) -> Dictionary:
	var vp := SubViewport.new()
	vp.own_world_3d = true
	vp.size = Vector2i(1600, 900) if render else Vector2i(16, 16)
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS if render else SubViewport.UPDATE_DISABLED
	vp.name = "Sandbox%d" % idx
	add_child(vp)
	var root := Node3D.new()
	root.position = OFFSET + Vector3(idx * 300.0, 0, 0)
	vp.add_child(root)
	var g := StaticBody3D.new()
	g.set_meta("surface", "cobbles")
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(90, 1, 90)
	cs.shape = bs
	g.add_child(cs)
	g.position.y = -0.5
	root.add_child(g)
	var moon := DirectionalLight3D.new()
	moon.rotation_degrees = Vector3(-34, 40, 0)
	moon.light_color = Color(0.62, 0.72, 1.0)
	moon.light_energy = 0.45
	moon.shadow_enabled = render
	root.add_child(moon)
	moon.add_to_group("moon_light")
	var w := WatchScript.new()
	w.sandbox = true
	w.overrides = overrides
	w.name = "SandboxWatch%d" % idx
	root.add_child(w)
	var p: CharacterBody3D = PlayerScript.new()
	p.sandbox = true
	p.scripted = true
	p.position = Vector3(0, 0.05, 30)
	root.add_child(p)
	w.player = p
	return {"vp": vp, "root": root, "watch": w, "player": p}


func L(w: Dictionary, v: Vector3) -> Vector3:
	return (w["root"] as Node3D).to_global(v)


func wall(w: Dictionary, centre: Vector3, size: Vector3, visual := false) -> StaticBody3D:
	var b := StaticBody3D.new()
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = size
	cs.shape = bs
	b.add_child(cs)
	if visual:
		var mi := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = size
		var mat := StandardMaterial3D.new()
		mat.albedo_color = Color(0.32, 0.29, 0.27)
		mat.roughness = 0.95
		bm.material = mat
		mi.mesh = bm
		b.add_child(mi)
	b.position = centre
	(w["root"] as Node3D).add_child(b)
	return b


func lantern(w: Dictionary, post: Vector3, with_lamp := true, visual := false) -> Node3D:
	var l := FlickerScript.new()
	l.amount = 0.10
	l.speed = 7.0
	l.position = post + Vector3(0.9, 2.9, 0)
	l.light_color = Color(1.0, 0.70, 0.40)
	l.light_energy = 9
	l.omni_range = 24
	l.omni_attenuation = 1.5
	l.shadow_enabled = false
	(w["root"] as Node3D).add_child(l)
	l.add_to_group("flame_lights")
	if visual:
		Assets.place(w["root"], "lantern_post", post, 0.0)
	if with_lamp:
		var lp := Distraction.LampPost.new()
		lp.light = l
		lp.position = post
		(w["root"] as Node3D).add_child(lp)
		return lp
	return l


func guard(w: Dictionary, gname: String, pts: Array, facing: float) -> Guard:
	var g: Guard = GuardScript.new()
	g.sandbox = true
	g.target_player = w["player"]
	g.guard_name = gname
	var wps: Array[Vector3] = []
	for pt in pts:
		wps.append(L(w, pt))
	if wps.size() == 1:
		wps.append(wps[0])
	g.waypoints = wps
	g.position = (w["root"] as Node3D).to_local(wps[0])
	g.rotation.y = facing
	(w["root"] as Node3D).add_child(g)
	return g


func spot(w: Dictionary, kind: String, pos: Vector3, rot: float, asset := "") -> Node3D:
	if asset != "":
		Assets.place(w["root"], asset, pos, rot)
	var hs := HidingSpotScript.new()
	hs.kind = kind
	hs.position = pos
	hs.rotation.y = rot
	hs.exit_point = Vector3(0, 0, 1.4)
	hs.peek_point = Vector3(0, 0.95, 0.75)
	(w["root"] as Node3D).add_child(hs)
	return hs


func tp(w: Dictionary, pos: Vector3, look: Vector3 = Vector3.INF) -> void:
	var p: CharacterBody3D = w["player"]
	p.global_position = L(w, pos)
	p.velocity = Vector3.ZERO
	if look != Vector3.INF:
		p.face_point(L(w, look))
	p.reset_physics_interpolation()


func step() -> float:
	await get_tree().physics_frame
	return get_physics_process_delta_time()


func wait_s(secs: float) -> void:
	var t := 0.0
	while t < secs:
		t += await step()


## Waits until `cond` is true or `timeout` sim-seconds pass; returns the time taken (or -1 on timeout).
func wait_until(cond: Callable, timeout: float) -> float:
	var t := 0.0
	while t < timeout:
		if cond.call():
			return t
		t += await step()
	return -1.0


func flat_dist(a: Vector3, b: Vector3) -> float:
	return Vector2(a.x - b.x, a.z - b.z).length()


# ------------------------------------------------------------------ tests

func t_light_noise(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	lantern(w, Vector3(-0.9, 0, 0), false)
	# a covered passage (sien) behind a wall, out of the lantern and the moon
	wall(w, Vector3(12, 2.5, 0), Vector3(0.4, 5, 14))
	wall(w, Vector3(18, 4.2, 0), Vector3(12, 0.3, 22))
	# a straw patch and a gravel patch
	for sp in [["straw", Vector3(-10, 0, 10), 2.0], ["gravel", Vector3(-10, 0, 18), 2.0]]:
		var n := Node3D.new()
		n.position = sp[1]
		n.set_meta("surface", sp[0])
		n.set_meta("surface_radius", sp[2])
		(w["root"] as Node3D).add_child(n)
		n.add_to_group("surface_patch")
	await wait_s(0.1)
	tp(w, Vector3(1.5, 0, 1.0))
	await wait_s(0.35)
	var pool := p.light_level
	var vis_pool := p.visibility
	tp(w, Vector3(16, 0, 0))
	await wait_s(0.35)
	var alley := p.light_level
	var vis_alley := p.visibility
	p.ai_crouch = true
	await wait_s(0.35)
	var crouch_alley := p.visibility
	p.ai_crouch = false
	tp(w, Vector3(-30, 0, -30))
	await wait_s(0.35)
	var moonlit := p.light_level
	# footsteps
	var noise := {}
	for s in [["cobbles", Vector3(-20, 0, -8), false], ["straw", Vector3(-11.2, 0, 10), false],
			["gravel", Vector3(-11.2, 0, 18), false], ["cobbles_sprint", Vector3(-20, 0, 0), true]]:
		tp(w, s[1])
		p.ai_sprint = s[2]
		p.ai_move = Vector3(1, 0, 0)
		await wait_s(0.3)
		noise[s[0]] = [p.noise, p.surface]
		p.ai_move = Vector3.ZERO
		p.ai_sprint = false
	# crowd blending: three townsfolk standing round the player (a stub population with the same query)
	var pop := CrowdStub.new()
	pop.name = "Population"
	(w["root"] as Node3D).add_child(pop)
	for k in 3:
		var npc := Node3D.new()
		pop.add_child(npc)
		npc.global_position = L(w, Vector3(-30 + cos(k * 2.1) * 1.4, 0, -30 + sin(k * 2.1) * 1.4))
	tp(w, Vector3(-30, 0, -30))
	await wait_s(0.4)
	var crowd := p.crowd_factor
	var vis_crowd := p.visibility
	p.ai_crouch = true
	await wait_s(0.4)
	var crowd_crouch := p.crowd_factor
	p.ai_crouch = false
	var ok: bool = pool > alley + 0.3 and vis_pool > vis_alley and noise["straw"][0] < noise["cobbles"][0] and noise["gravel"][0] > noise["cobbles"][0]
	return ("[smoke] stealth light pool=%.2f alley=%.2f moonlit=%.2f vis pool=%.2f alley=%.2f crouch_alley=%.2f\n" % [pool, alley,
			moonlit, vis_pool, vis_alley, crouch_alley]) + \
			("[smoke] stealth noise walk cobbles=%.2f straw=%.2f(%s) gravel=%.2f(%s) sprint=%.2f | crowd=%.2f vis=%.2f crouched_in_crowd=%.2f %s" % [
			noise["cobbles"][0], noise["straw"][0], noise["straw"][1], noise["gravel"][0], noise["gravel"][1], noise["cobbles_sprint"][0],
			crowd, vis_crowd, crowd_crouch, "OK" if ok and crowd < 0.5 and crowd_crouch == 1.0 else "FAIL"])


class CrowdStub extends Node:
	func _ready() -> void:
		add_to_group("population")

	func crowd_count(point: Vector3, _dir: Vector3 = Vector3.ZERO, radius: float = 2.5) -> int:
		var n := 0
		for c in get_children():
			if Vector2(c.global_position.x - point.x, c.global_position.z - point.z).length() <= radius:
				n += 1
		return n


func t_hide(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	lantern(w, Vector3(1.5, 0, -1.2), false)
	var hs := spot(w, "hay", Vector3.ZERO, 0.0)
	var a := guard(w, "Patrol", [Vector3(-12, 0, 2.2), Vector3(12, 0, 2.2)], -PI * 0.5)
	a.patrol_speed = 2.4
	await wait_s(0.05)
	var entered: bool = p.enter_spot(hs)
	var max_s := 0.0
	var min_d := INF
	var t := 0.0
	while t < 14.0:
		t += await step()
		max_s = maxf(max_s, a.suspicion)
		min_d = minf(min_d, flat_dist(a.global_position, hs.global_position))
		if a.global_position.x > L(w, Vector3(8, 0, 0)).x:
			break
	var passby_ok := entered and p.hidden_spot == hs and max_s < 1.0 and min_d < 3.0
	var passby := "passby entered=%s guard_min_dist=%.1f max_suspicion=%.1f still_hidden=%s" % [entered, min_d, max_s, p.hidden_spot == hs]
	# a sentry who watches the player go in
	p.leave_spot()
	a.queue_free()
	var b := guard(w, "Sentry", [Vector3(0, 0, 9.5)], 0.0)
	w["watch"].overrides["sweep.sentry_amplitude_deg"] = 0.0
	var seen := await wait_until(func() -> bool: return b.suspicion >= 20.0, 6.0)
	var entered2: bool = p.enter_spot(hs)
	var tasked: bool = b.task.get("kind", "") == "search_spot"
	var found_t := await wait_until(func() -> bool: return p.hidden_spot == null, 14.0)
	var found := found_t >= 0.0
	await wait_s(0.1)
	return "[smoke] stealth hide %s | seen_enter curious_after=%.1fs entered=%s searched=%s found=%s after %.1fs guard=%s %s" % [passby,
			seen, entered2, tasked, found, found_t, Guard.State.keys()[b.state], "OK" if passby_ok and found else "FAIL"]


func t_lean(idx: int) -> String:
	var w := make_world(idx, {"sweep.sentry_amplitude_deg": 0.0, "sweep.amplitude_deg": 0.0})
	var p: Player = w["player"]
	wall(w, Vector3(-2, 1.5, 0), Vector3(4, 3, 0.4))
	lantern(w, Vector3(-2.4, 0, 2.2), false)
	var g := guard(w, "Sentry", [Vector3(0.5, 0, -7)], PI)
	tp(w, Vector3(-0.42, 0, 0.75), Vector3(0.5, 1.5, -7))
	await wait_s(0.4)
	var hidden: float = g._perceive()
	p.ai_lean = 1.0
	await wait_s(0.4)
	var leaning: float = g._perceive()
	var head_off: float = flat_dist(p.head_position(), p.global_position)
	p.ai_lean = 0.0
	tp(w, Vector3(1.2, 0, 0.75), Vector3(0.5, 1.5, -7))
	await wait_s(0.4)
	var open: float = g._perceive()
	var ratio := leaning / open if open > 0 else 0.0
	return "[smoke] stealth lean hidden=%.2f leaning=%.2f open=%.2f ratio=%.2f head_offset=%.2fm %s" % [hidden, leaning, open, ratio,
			head_off, "OK" if hidden == 0.0 and leaning > 0.0 and absf(ratio - 0.5) < 0.12 else "FAIL"]


func t_coin(idx: int) -> String:
	var w := make_world(idx, {"distractions.investigate_secs": 3.0})
	var p: Player = w["player"]
	var g := guard(w, "Sentry", [Vector3(0, 0, 0)], 0.0)
	tp(w, Vector3(0, 0, 11), Vector3(0, 0, 0))
	await wait_s(0.3)
	var start := g.global_position
	var st: Node3D = p.throw_at(L(w, Vector3(5, 0, -4)))
	var landed_t := await wait_until(func() -> bool: return st.landed, 4.0)
	var land: Vector3 = st.land_pos
	var inv: bool = st.investigator == g
	var reach_t := await wait_until(func() -> bool: return flat_dist(g.global_position, land) < 1.6, 8.0)
	var moved := flat_dist(g.global_position, start)
	var state_there: String = Guard.State.keys()[g.state]
	var back_t := await wait_until(func() -> bool: return g.task.is_empty(), 8.0)
	return "[smoke] stealth coin landed=%s after %.1fs off_target=%.1fm investigator=%s reached=%s in %.1fs moved=%.1fm state=%s done_looking=%s rings=%d %s" % [
			landed_t >= 0.0, landed_t, flat_dist(land, L(w, Vector3(5, 0, -4))), inv, reach_t >= 0.0, reach_t, moved, state_there,
			back_t >= 0.0, w["watch"].ring_count(), "OK" if inv and reach_t >= 0.0 else "FAIL"]


func t_lamp(idx: int) -> String:
	var w := make_world(idx, {"distractions.relight_secs": 2.0, "sweep.sentry_amplitude_deg": 0.0})
	var p: Player = w["player"]
	var lamp: Node3D = lantern(w, Vector3(-0.9, 0, 0), true)
	var g := guard(w, "Sentry", [Vector3(0, 0, 10)], 0.0)
	tp(w, Vector3(0.6, 0, 0.8), Vector3(-0.9, 1, 0))
	await wait_s(0.35)
	var before := p.light_level
	var doused: bool = lamp.douse(p)
	await wait_s(0.35)
	var after := p.light_level
	tp(w, Vector3(-30, 0, -30))
	var relit_t := await wait_until(func() -> bool: return not lamp.is_doused(), 15.0)
	return "[smoke] stealth lamp light %.2f -> %.2f doused=%s relit_by=%s after %.1fs guard_at_post=%.1fm %s" % [before, after, doused,
			lamp.relit_by, relit_t, flat_dist(g.global_position, lamp.global_position),
			"OK" if doused and after < before - 0.3 and lamp.relit_by == "guard" else "FAIL"]


func t_phases(idx: int) -> String:
	var w := make_world(idx, {"phases.lost_secs": 0.5, "phases.evasion_secs": 2.5, "phases.caution_minutes": 2.0,
			"sweep.sentry_amplitude_deg": 0.0})
	var p: Player = w["player"]
	var wt: Node = w["watch"]
	lantern(w, Vector3(-0.9, 0, -4), false)
	var a := guard(w, "Sentry", [Vector3(0, 0, 0)], 0.0)
	var b := guard(w, "Patrol", [Vector3(20, 0, 0)], 0.0)
	wt.overrides["runner.corporal_post"] = [L(w, Vector3(20, 0, 7)).x, 0.0, L(w, Vector3(20, 0, 7)).z]
	wall(w, Vector3(-30, 2, 0), Vector3(0.4, 4, 20))
	tp(w, Vector3(0, 0, -3.5), Vector3(0, 1, 0))
	var alarm_t := await wait_until(func() -> bool: return wt.phase == wt.Phase.ALARM, 8.0)
	var t0: float = wt.clock
	tp(w, Vector3(-38, 0, 0))
	await wait_until(func() -> bool: return wt.phase == wt.Phase.CAUTION, 10.0)
	await wait_s(0.1)
	var caution_view := a.view_distance
	var calm_t := await wait_until(func() -> bool: return wt.phase == wt.Phase.CALM, 10.0)
	var times := {}
	for e in wt.phase_log:
		if not times.has(e[0]) or e[0] == "CALM":
			times[e[0]] = float(e[1]) - t0
	await wait_s(0.1)
	var runner_ok: bool = wt.runners_arrived == 1
	var got := "[smoke] stealth phases ALARM after %.1fs exposure; then EVASION@%.1fs CAUTION@%.1fs CALM@%.1fs (lost 0.5 s, evasion 2.5 s, caution 2 game-min) runner=%s arrived=%d log=%s" % [
			alarm_t, times.get("EVASION", -1.0), times.get("CAUTION", -1.0), times.get("CALM", -1.0), b.guard_name if runner_ok else "-",
			wt.runners_arrived, ",".join(wt.phase_log.map(func(e: Array) -> String: return str(e[0])))]
	var ok: bool = alarm_t >= 0.0 and calm_t >= 0.0 and times.get("EVASION", 99.0) < 1.5 and absf(float(times.get("CAUTION", 0.0)) - float(times.get("EVASION", 0.0)) - 2.5) < 0.3 \
			and absf(float(times.get("CALM", 0.0)) - float(times.get("CAUTION", 0.0)) - 2.0) < 0.3 and runner_ok
	return got + " caution_view=%.0fm calm_view=%.0fm %s" % [caution_view, a.view_distance, "OK" if ok and caution_view > a.view_distance else "FAIL"]


func t_runner(idx: int) -> String:
	var w := make_world(idx, {"sweep.sentry_amplitude_deg": 0.0})
	var p: Player = w["player"]
	var wt: Node = w["watch"]
	wt.overrides["runner.corporal_post"] = [L(w, Vector3(40, 0, 0)).x, 0.0, L(w, Vector3(40, 0, 0)).z]
	var a := guard(w, "Sentry", [Vector3(0, 0, 0)], 0.0)
	var b := guard(w, "Patrol", [Vector3(3, 0, 3)], -PI * 0.5)
	tp(w, Vector3(-30, 0, 30))
	await wait_s(0.2)
	a.last_known = L(w, Vector3(0, 0, -6))
	a.suspicion = 100.0
	a._update_suspicion(0.0, 0.0)
	var sent_t := await wait_until(func() -> bool: return b.is_runner, 3.0)
	await wait_s(1.0)
	var fwd := -b.global_transform.basis.z
	fwd.y = 0
	p.global_position = b.global_position - fwd.normalized() * 1.0
	p.face_point(b.global_position)
	var r: String = p.attack()
	await wait_s(0.2)
	var ok: bool = sent_t >= 0.0 and r == "takedown" and b.is_downed() and wt.runners_stopped == 1 and wt.runners_arrived == 0
	return "[smoke] stealth runner sent=%s after %.1fs attack=%s intercepted=%s arrived=%d stopped=%d %s" % [b.guard_name if sent_t >= 0.0 else "-",
			sent_t, r, b.is_downed(), wt.runners_arrived, wt.runners_stopped, "OK" if ok else "FAIL"]


func t_drag(idx: int) -> String:
	var w := make_world(idx, {"sweep.sentry_amplitude_deg": 0.0})
	var p: Player = w["player"]
	var wt: Node = w["watch"]
	var hs := spot(w, "hay", Vector3(6, 0, 0), 0.0)
	var a := guard(w, "Sentry", [Vector3(0, 0, 0)], 0.0)
	tp(w, Vector3(0, 0, 1.1), Vector3(0, 1, 0))
	await wait_s(0.3)
	var r: String = p.attack()
	await wait_s(1.6)
	var drag_ok: bool = a._drag_ia.on_interact(p)
	p.ai_drag_hold = true
	var start := p.global_position
	var t := 0.0
	var dist := 0.0
	while t < 6.0:
		p.ai_move = (hs.global_position - p.global_position) * Vector3(1, 0, 1)
		t += await step()
		if flat_dist(a.global_position, hs.global_position) < 1.2:
			break
	dist = flat_dist(p.global_position, start)
	var speed := dist / maxf(t, 0.01)
	p.ai_move = Vector3.ZERO
	p.ai_drag_hold = false
	await wait_s(0.1)
	var stashed: bool = a.hidden_in == hs and not a.visible
	# a patrol walks past the spot where he fell and past the cart
	var c := guard(w, "Patrol", [Vector3(-10, 0, 2.5), Vector3(12, 0, 2.5)], -PI * 0.5)
	c.patrol_speed = 2.6
	tp(w, Vector3(-30, 0, -30))
	await wait_until(func() -> bool: return c.global_position.x > L(w, Vector3(9, 0, 0)).x, 12.0)
	var found: bool = wt.bodies_found > 0
	return "[smoke] stealth drag takedown=%s drag=%s moved=%.1fm speed=%.2f m/s stashed=%s patrol_found=%s %s" % [r, drag_ok, dist, speed,
			stashed, found, "OK" if r == "takedown" and drag_ok and stashed and not found and speed < 1.8 else "FAIL"]


## Door knock, rolling barrel, loose horse, church bell.
func t_misc(idx: int) -> String:
	var w := make_world(idx, {"distractions.knock_hold_secs": 2.0, "sweep.sentry_amplitude_deg": 0.0})
	var wt: Node = w["watch"]
	var root: Node3D = w["root"]
	var a := guard(w, "Sentry A", [Vector3(0, 0, 0)], 0.0)
	var b := guard(w, "Sentry B", [Vector3(-20, 0, 0)], 0.0)
	tp(w, Vector3(0, 0, 40))
	await wait_s(0.2)
	# a knock: A walks to the door, the townsman who opens keeps him there
	var door := Distraction.KnockDoor.new()
	door.position = Vector3(5, 0, -5)
	root.add_child(door)
	door.knock()
	var held_t := await wait_until(func() -> bool: return door.holding == a, 10.0)
	var released_t := await wait_until(func() -> bool: return a.task.is_empty(), 8.0)
	# a kicked barrel rolls, rumbles, and B runs after it
	var bar := Distraction.RollingBarrel.new()
	bar.position = Vector3(-17, 0, 6)
	root.add_child(bar)
	await wait_s(0.1)
	bar.kick(Vector3(0, 0, -1))
	var stop_t := await wait_until(func() -> bool: return not bar.rolling, 8.0)
	var chased: bool = bar.chaser == b
	var reach_t := await wait_until(func() -> bool: return flat_dist(b.global_position, bar.global_position) < 2.0, 8.0)
	# a loose horse (stub): the nearest guard follows it
	var horse := Node3D.new()
	root.add_child(horse)
	horse.global_position = L(w, Vector3(4, 0, 4))
	var ht := Distraction.HorseTether.new()
	ht.horse = horse
	root.add_child(ht)
	await wait_s(0.1)
	ht.untie()
	var follow: bool = a.task.get("kind", "") == "follow" or b.task.get("kind", "") == "follow"
	# the church bell masks sound and turns heads
	wt.ring_bell(L(w, Vector3(0, 18, -30)))
	var masked: bool = wt.masked()
	var heard: Node = wt.emit_sound(L(w, Vector3(1, 0, -1)), 1.0, "stone", true)
	var looking: bool = a.task.get("kind", "") == "look"
	var ok := held_t >= 0.0 and released_t >= 0.0 and chased and reach_t >= 0.0 and follow and masked and heard == null and looking
	return "[smoke] stealth misc knock_held=%s(%.1fs) released=%s barrel rolled=%.1fm chased=%s reached=%s horse_followed=%s bell masked=%s heard_under_bell=%s heads_turned=%s %s" % [
			held_t >= 0.0, held_t, released_t >= 0.0, bar.rolled, chased, reach_t >= 0.0, follow, masked, heard != null, looking,
			"OK" if ok else "FAIL"]


# ------------------------------------------------------------------ screenshots (--stealth-shot=/dir)

func t_shots(idx: int) -> String:
	var w := make_world(idx, {"sweep.sentry_amplitude_deg": 0.0, "sweep.amplitude_deg": 0.0}, true)
	var p: Player = w["player"]
	var wt: Node = w["watch"]
	var root: Node3D = w["root"]
	_shot_env(root)
	# a slice of the square: cobbles, a tenement row, a lantern, a hay cart, a guard
	var slab := Assets.instance("ground_cobbles")
	if slab:
		slab.queue_free()
		for ix in range(-4, 5):
			for iz in range(-4, 5):
				var s := Assets.instance("ground_cobbles")
				s.position = Vector3(ix * 4.0, 0, iz * 4.0)
				root.add_child(s)
	Assets.place(root, "tenement_a", Vector3(-5, 0, -14), 0.0)
	Assets.place(root, "tenement_c", Vector3(6, 0, -14), 0.0)
	Assets.place(root, "tenement_d", Vector3(17, 0, -14), 0.0)
	lantern(w, Vector3(-3.5, 0, -4), true, true)
	var hs := spot(w, "hay", Vector3(4.5, 0, -6.5), 0.3, "handcart")
	Assets.place(root, "straw_scatter", Vector3(4.5, 0, -6.5), 0.3)
	Assets.place(root, "barrel", Vector3(8.0, 0, -8.0), 0.4)
	var g := guard(w, "Watchman", [Vector3(2, 0, 4)], PI * 0.8)
	var layer := CanvasLayer.new()
	(w["vp"] as SubViewport).add_child(layer)
	var cues := Hud.StealthCues.new()
	cues.player = p
	cues.watch = wt
	layer.add_child(cues)
	var out := PackedStringArray()
	# 1. visibility arc in the lantern pool, walking on cobbles
	tp(w, Vector3(-2.4, 0, -2.5))
	p.rotate_camera(Vector3(-0.25, 0.9, 0))
	p.ai_move = Vector3(0.3, 0, 0.0)
	await wait_s(0.8)
	out.append(await _shot(w, "stealth_arc_light", "vis=%.2f noise=%.2f" % [p.visibility, p.noise]))
	# 2. in the dark, crouched and still
	p.ai_move = Vector3.ZERO
	tp(w, Vector3(14, 0, -8.5))
	p.rotate_camera(Vector3(-0.2, 0.6, 0))
	p.ai_crouch = true
	await wait_s(0.8)
	out.append(await _shot(w, "stealth_arc_dark", "vis=%.2f" % p.visibility))
	p.ai_crouch = false
	# 3. hiding in the hay cart, peeking out at the guard
	tp(w, Vector3(4.5, 0, -5.0))
	p.enter_spot(hs)
	p.rotate_camera(Vector3(-0.12, PI * 0.9, 0))
	await wait_s(0.8)
	out.append(await _shot(w, "stealth_hiding", "hidden=%s vis=%.2f" % [p.hidden_spot != null, p.visibility]))
	p.leave_spot()
	# 4. the guard's cone at Curious (near + far zone), from above behind the player
	tp(w, Vector3(-3, 0, 9))
	g.suspicion = 38.0
	g.last_known = L(w, Vector3(-3, 0, 9))
	p.rotate_camera(Vector3(-0.75, -0.3, 0))
	await wait_s(0.5)
	out.append(await _shot(w, "stealth_cone_curious", "state=%s" % Guard.State.keys()[g.state]))
	# 5. a stone lands: the sound ring (and the guard turns)
	tp(w, Vector3(-4, 0, 10))
	p.rotate_camera(Vector3(-0.55, -0.1, 0))
	var st: Node3D = p.throw_at(L(w, Vector3(-1.0, 0, 2.5)))
	await wait_until(func() -> bool: return st.landed, 3.0)
	await wait_s(0.35)
	out.append(await _shot(w, "stealth_ring", "rings=%d" % wt.ring_count()))
	# 6. searching: the last-known ghost; the player has slipped away behind the cart
	g.suspicion = 70.0
	g.last_known = L(w, Vector3(-1.5, 0, -1.0))
	g.task = {}
	tp(w, Vector3(8, 0, 3))
	p.rotate_camera(Vector3(-0.35, 0.95, 0))
	await wait_s(0.6)
	out.append(await _shot(w, "stealth_ghost", "ghost=%s" % wt.ghost_visible()))
	# 7. the chevron: the reacting guard is behind the camera
	p.rotate_camera(Vector3(-0.2, -PI * 0.5 + 0.9, 0))
	await wait_s(0.3)
	out.append(await _shot(w, "stealth_chevron", "state=%s" % Guard.State.keys()[g.state]))
	return "[smoke] stealth screenshots " + " ".join(out)


func _shot_env(root: Node3D) -> void:
	var env := WorldEnvironment.new()
	var e := Environment.new()
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_top_color = Color(0.02, 0.025, 0.06)
	sm.sky_horizon_color = Color(0.10, 0.09, 0.14)
	sm.ground_bottom_color = Color(0.02, 0.02, 0.03)
	sm.ground_horizon_color = Color(0.08, 0.07, 0.10)
	sky.sky_material = sm
	e.background_mode = Environment.BG_SKY
	e.sky = sky
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.18, 0.21, 0.34)
	e.ambient_light_energy = 0.6
	e.tonemap_mode = Environment.TONE_MAPPER_ACES
	e.tonemap_exposure = 1.1
	e.tonemap_white = 6.0
	e.glow_enabled = true
	e.glow_intensity = 0.45
	e.glow_hdr_threshold = 1.3
	e.fog_enabled = true
	e.fog_light_color = Color(0.07, 0.08, 0.13)
	e.fog_density = 0.004
	env.environment = e
	root.add_child(env)


func _shot(w: Dictionary, name: String, note: String) -> String:
	var vp: SubViewport = w["vp"]
	for i in 3:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var path := shot_dir.path_join(name + ".png")
	vp.get_texture().get_image().save_png(path)
	return "%s(%s)" % [name, note]
