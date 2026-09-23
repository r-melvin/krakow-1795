extends "res://scripts/stealth/stealth_smoke.gd"
## `-- --smoke` checks for phases E and F (intel.gd, zones.gd, the enforcer bits of guard.gd / npc.gd), started by the
## first district watch beside stealth_smoke.gd, whose sandbox helpers it inherits: every check runs in its own
## SubViewport world with a sandbox watch, player, zones and intel (no GameState / Mission side effects).
## Prints detail lines and one summary:
##   [smoke] intel overheard=<n> bills=<n> patrols_recorded=<n> zone=<name> trespass=<ok|fail> enforcer=<ok|fail>
##           notoriety=<n> wanted=<bool>
## `--intel-shot=/dir` (windowed): intel_bill_wanted.png, intel_enforcer_cone.png, intel_trespass.png, intel_map.png.

const IntelScript := preload("res://scripts/stealth/intel.gd")

const JournalScript := preload("res://scripts/ui/journal.gd")
const MinimapScript := preload("res://scripts/ui/minimap.gd")

var R: Dictionary = {}


func _ready() -> void:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--intel-shot="):
			shot_dir = a.trim_prefix("--intel-shot=")
	if DisplayServer.get_name() == "headless":
		shot_dir = ""
	_run_intel()


func _run_intel() -> void:
	await get_tree().process_frame
	print("[smoke] intel sandbox tests start at frame %d" % Engine.get_process_frames())
	var tests: Array[Callable] = [t_overhear, t_bills, t_patrol, t_zones, t_trespass, t_enforcer, t_notoriety, t_minimap]
	if shot_dir != "":
		DirAccess.make_dir_recursive_absolute(shot_dir)
		tests.append(t_intel_shots)
	_pending = tests.size()
	for i in tests.size():
		_launch(tests[i], 20 + i)
	while _pending > 0:
		await get_tree().process_frame
	print("[smoke] intel overheard=%d bills=%d patrols_recorded=%d zone=%s trespass=%s enforcer=%s notoriety=%d wanted=%s minimap %s" % [
			int(R.get("overheard", 0)), int(R.get("bills", 0)), int(R.get("patrols", 0)), R.get("zone", "-"),
			"ok" if R.get("trespass", false) else "fail", "ok" if R.get("enforcer", false) else "fail",
			int(R.get("notoriety", 0)), R.get("wanted", false), "ok" if R.get("minimap", false) else "fail"])
	print("[smoke] minimap %s" % ("ok" if R.get("minimap", false) else "fail"))
	print("[smoke] intel done at frame %d" % Engine.get_process_frames())


func phase_f(w: Dictionary) -> Dictionary:
	var wt: Node = w["watch"]
	wt.add_phase_f((w["root"] as Node3D).global_position)
	w["zones"] = wt.zones
	w["intel"] = wt.intel
	return w


func stub(w: Dictionary, pos: Vector3, h := 1.7) -> Node3D:
	var n := Node3D.new()
	var mi := MeshInstance3D.new()
	var cm := CapsuleMesh.new()
	cm.radius = 0.28
	cm.height = h
	mi.mesh = cm
	mi.position.y = h * 0.5
	n.add_child(mi)
	(w["root"] as Node3D).add_child(n)
	n.global_position = L(w, pos)
	return n


# ------------------------------------------------------------------ E: overhearing

func t_overhear(idx: int) -> String:
	var w := phase_f(make_world(idx))
	var it: Node = w["intel"]
	var a := stub(w, Vector3(0, 0, 0))
	var b := stub(w, Vector3(1.8, 0, 0.3))
	var far := stub(w, Vector3(-12, 0, 0))
	it.speakers_override = {"well_gossip_a": a, "well_gossip_b": b, "guard:Cloth Hall sentry": far}
	tp(w, Vector3(0.8, 0, 3.0), Vector3(0.8, 0, 0))
	var t_pair := await wait_until(func() -> bool: return it.store()["hints"].has("corporal_tavern"), 8.0)
	# the solo guard stands 11 m off: out of earshot, nothing is heard
	await wait_s(1.0)
	var far_heard: bool = it.store()["hints"].has("watch_change")
	# walk up to him: now it is heard
	tp(w, Vector3(-10, 0, 2.0), Vector3(-12, 0, 0))
	var t_solo := await wait_until(func() -> bool: return it.store()["hints"].has("watch_change"), 8.0)
	# a storyline line with a hint, within earshot
	it._on_story_hint("delivery", "cellar_tonight", a)
	var story_ok: bool = it.store()["hints"].has("cellar_tonight")
	var n := int(it.store()["overheard"])
	R["overheard"] = n
	var ok := t_pair >= LISTEN_MIN() and t_solo >= LISTEN_MIN() and not far_heard and story_ok and n == 3
	var note: String = it.store()["hints"].get("corporal_tavern", {}).get("where", "?")
	return "[smoke] intel overhear pair=%.1fs solo=%.1fs far_heard=%s story=%s count=%d where=%s %s" % [t_pair, t_solo, far_heard,
			story_ok, n, note, "OK" if ok else "FAIL"]


func LISTEN_MIN() -> float:
	return IntelScript.LISTEN_SECS - 0.3


# ------------------------------------------------------------------ E: bills

func t_bills(idx: int) -> String:
	var w := phase_f(make_world(idx))
	var it: Node = w["intel"]
	var root: Node3D = w["root"]
	var board := Node3D.new()
	board.position = Vector3(6, 0, -6)
	root.add_child(board)
	it.board_override = board
	wall(w, Vector3(-7, 2.5, -28.2), Vector3(12, 5, 0.4))          # the north facade (bills.json wall_north)
	await wait_s(1.0)
	var posted: int = it.bill_count()
	var wanted0: int = it.wanted_count()
	var e: Dictionary = it.bills[0]
	var read: bool = it.use_bill(e) and it.store()["bills"].has(e["id"])
	it.add_notoriety(35.0, "test")
	await wait_s(0.1)
	var wanted1: int = it.wanted_count()
	var we: Dictionary = {}
	for b in it.bills:
		if b["wanted"] and (b["node"] as Node3D).visible:
			we = b
	var text: String = str(it.wanted_text()["desc"])
	var tore := false
	if not we.is_empty():
		it.use_bill(we)                # read it first
		tore = it.use_bill(we) and we["torn"]
	var after: float = it.notoriety()
	R["bills"] = posted
	var ok := posted >= 4 and wanted0 == 0 and read and wanted1 >= 1 and tore and absf(after - 30.0) < 0.01
	return "[smoke] intel bills posted=%d read=%s wanted_before=%d wanted_at_35=%d tore=%s notoriety_after=%.0f desc=%s %s" % [
			posted, read, wanted0, wanted1, tore, after, text.left(90), "OK" if ok else "FAIL"]


# ------------------------------------------------------------------ E: patrol recording

func t_patrol(idx: int) -> String:
	var w := phase_f(make_world(idx, {"sweep.amplitude_deg": 0.0}))
	var it: Node = w["intel"]
	var p: Player = w["player"]
	var g := guard(w, "Patrol A", [Vector3(-6, 0, -14), Vector3(6, 0, -14), Vector3(6, 0, -18), Vector3(-6, 0, -18)], PI * 0.5)
	g.patrol_speed = 1.2
	tp(w, Vector3(0, 0, 0), Vector3(0, 0, -14))
	p.ai_crouch = true
	var t_crouch := await wait_until(func() -> bool: return it.store()["patrols"].has("Patrol A"), 14.0)
	p.ai_crouch = false
	# a bench: twice as fast
	var g2 := guard(w, "Patrol B", [Vector3(-6, 0, 18), Vector3(6, 0, 18), Vector3(6, 0, 22)], -PI * 0.5)
	g2.patrol_speed = 1.2
	var bench := spot(w, "bench", Vector3(0, 0, 6), PI)
	tp(w, Vector3(0, 0, 7), Vector3(0, 0, 18))
	await wait_s(0.1)
	var sat: bool = p.enter_spot(bench)
	p.rotate_camera(Vector3(-0.2, 0.0, 0))
	p.face_point(L(w, Vector3(0, 0, 18)))
	var t_bench := await wait_until(func() -> bool: return it.store()["patrols"].has("Patrol B"), 10.0)
	p.leave_spot()
	var wps: int = (it.store()["patrols"].get("Patrol A", {}).get("wps", []) as Array).size()
	R["patrols"] = int(it.store()["recorded"])
	var ok := t_crouch >= 9.5 and t_crouch < 12.0 and wps == 4 and sat and t_bench >= 4.5 and t_bench < 7.0
	return "[smoke] intel patrol crouched=%.1fs wps=%d bench=%s %.1fs recorded=%d %s" % [t_crouch, wps, sat, t_bench,
			int(it.store()["recorded"]), "OK" if ok else "FAIL"]


# ------------------------------------------------------------------ F: zones

func t_zones(idx: int) -> String:
	var w := phase_f(make_world(idx))
	var z: Node = w["zones"]
	var p: Player = w["player"]
	var out := {}
	for pt in [["salon", Vector3(-15, 0, 18)], ["barracks", Vector3(24, 0, -10)], ["church", Vector3(33, 0, -19)],
			["church", Vector3(22, 0, 23.5)], ["street", Vector3(0, 0, 0)], ["kazimierz_gate", Vector3(-35, 0, 40)], ["street", Vector3(-38, 0, -5)]]:
		out[pt[1]] = [pt[0], z.current(L(w, pt[1]))]
	var all_ok := true
	for k in out:
		if out[k][0] != out[k][1]:
			all_ok = false
	tp(w, Vector3(-15, 0, 18))
	var none_permit: Array = z.permitted(p)
	var tres_none: bool = z.trespassing(p)
	z.flags["invited"] = true
	p.disguised = true
	var cloak: String = z.outfit(p)
	var tres_cloak: bool = z.trespassing(p)
	z.flags["disguise_austrian"] = true
	var coat: String = z.outfit(p)
	var tres_coat: bool = z.trespassing(p)
	R["zone"] = z.current(p.global_position)
	var ok := all_ok and none_permit == ["street"] and tres_none and cloak == "salon_cloak" and not tres_cloak and coat == "austrian_coat" and tres_coat
	return "[smoke] intel zones points=%s none=%s trespass(none/cloak/coat)=%s/%s/%s outfits=%s,%s %s" % [all_ok, none_permit, tres_none,
			tres_cloak, tres_coat, cloak, coat, "OK" if ok else "FAIL"]


## A sentry at the St Mary's post zone sees the player 8 m off in moonlight: in the barracks (trespass) he is Curious at
## once and Searching by 6 s; the same exposure on the open street leaves him merely Curious; in the salon zone with
## the cloak he stays calm (the disguise holds where it is permitted).
func t_trespass(idx: int) -> String:
	var res := {}
	var cases := [["barracks", Vector3(24, 0, -6), false], ["street", Vector3(0, 0, 4), false], ["salon", Vector3(-15, 0, 26), true]]
	var worlds: Array = []
	for i in cases.size():
		var c: Array = cases[i]
		var w := phase_f(make_world(idx + 100 * (i + 1), {"sweep.sentry_amplitude_deg": 0.0, "sweep.amplitude_deg": 0.0}))
		var gpos: Vector3 = c[1]
		var g := guard(w, "Sentry", [gpos], 0.0)
		w["guard"] = g
		tp(w, gpos + Vector3(0, 0, 40))
		if c[2]:
			(w["zones"] as Node).flags["invited"] = true
			(w["player"] as Player).disguised = true
		worlds.append(w)
	await wait_s(0.3)
	for i in cases.size():
		var w: Dictionary = worlds[i]
		(w["zones"] as Node).hook_guards()
		var gpos: Vector3 = cases[i][1]
		tp(w, gpos + Vector3(0, 0, -8), gpos)
	var first_curious := [-1.0, -1.0, -1.0]
	var searching_at := [-1.0, -1.0, -1.0]
	var t := 0.0
	while t < 6.6:
		t += await step()
		for i in cases.size():
			var g: Guard = worlds[i]["guard"]
			if first_curious[i] < 0.0 and g.state >= Guard.State.CURIOUS:
				first_curious[i] = t
			if searching_at[i] < 0.0 and g.state >= Guard.State.SEARCHING:
				searching_at[i] = t
	var states := PackedStringArray()
	for i in cases.size():
		var g: Guard = worlds[i]["guard"]
		states.append("%s:%s(%.0f) curious@%.1f search@%.1f" % [cases[i][0], Guard.State.keys()[g.state], g.suspicion, first_curious[i], searching_at[i]])
	var ok: bool = first_curious[0] >= 0.0 and first_curious[0] < 0.5 and searching_at[0] > 0.0 and searching_at[0] <= 6.5 \
			and (first_curious[1] < 0.0 or first_curious[1] > 1.0) and searching_at[1] < 0.0 \
			and worlds[2]["guard"].state == Guard.State.CALM
	R["trespass"] = ok
	return "[smoke] intel trespass %s %s" % [" | ".join(states), "OK" if ok else "FAIL"]


# ------------------------------------------------------------------ F: enforcers

func t_enforcer(idx: int) -> String:
	var w := phase_f(make_world(idx, {"sweep.sentry_amplitude_deg": 0.0, "sweep.amplitude_deg": 0.0}))
	var p: Player = w["player"]
	var z: Node = w["zones"]
	z.flags["invited"] = true
	p.disguised = true
	# two sentries side by side facing south, the player 5 m in front: one plain, one the Corporal (enforcer)
	var a := guard(w, "Plain sentry", [Vector3(-0.8, 0, 0)], PI)
	var b := guard(w, "Corporal", [Vector3(0.8, 0, 0)], PI)
	b.enforcer = true
	lantern(w, Vector3(-1.5, 0, 4.0), false)
	tp(w, Vector3(0, 0, 40))
	await wait_s(0.3)
	tp(w, Vector3(0, 0, 5.0), Vector3(0, 0, 0))
	await wait_s(2.0)
	var sa := a.suspicion
	var sb := b.suspicion
	var edge: bool = b._cone_edge != null and b._cone_edge.visible and (a._cone_edge == null or not a._cone_edge.visible)
	# an enforcer townsman (npcs.json "spy") recognises the disguised player and calls the nearest guard
	var w2 := phase_f(make_world(idx + 1000))
	var p2: Player = w2["player"]
	p2.disguised = true
	var far := guard(w2, "Far patrol", [Vector3(-16, 0, -6), Vector3(-16, 0, 6)], 0.0)
	var spy: CharacterBody3D = load("res://scripts/npc/npc.gd").new()
	spy.npc_id = "spy"
	spy.candidates = PackedStringArray(["npc_m_05", "figure_townsman"])
	spy.recognise_target = p2
	spy.position = Vector3(0, 0, 0)
	spy.facing = 0.0
	(w2["root"] as Node3D).add_child(spy)
	tp(w2, Vector3(0, 0, 40))
	await wait_s(0.2)
	tp(w2, Vector3(0, 0, -4.0), Vector3(0, 0, 0))
	var t_rec := await wait_until(func() -> bool: return spy.recognised > 0, 5.0)
	await wait_s(0.1)
	var called: bool = far.task.get("kind", "") == "search" or far.state >= Guard.State.SEARCHING
	spy.queue_free()
	var ok: bool = sb > 20.0 and sb > sa * 3.0 and edge and spy.enforcer and t_rec >= 1.8 and called
	R["enforcer"] = ok
	return "[smoke] intel enforcer disguised: plain=%.1f corporal=%.1f red_edge=%s | npc spy enforcer=%s recognised=%.1fs guard_called=%s %s" % [
			sa, sb, edge, spy.enforcer, t_rec, called, "OK" if ok else "FAIL"]


# ------------------------------------------------------------------ F: notoriety

func t_notoriety(idx: int) -> String:
	var w := phase_f(make_world(idx, {"sweep.sentry_amplitude_deg": 0.0}))
	var it: Node = w["intel"]
	var wt: Node = w["watch"]
	var g1 := guard(w, "Victim", [Vector3(0, 0, 0)], 0.0)
	var g2 := guard(w, "Witness", [Vector3(0, 0, -8)], PI)
	var g3 := guard(w, "Fighter", [Vector3(20, 0, 0)], 0.0)
	tp(w, Vector3(0, 0, 40))
	await wait_s(0.3)
	wt.on_runner_arrived(g3)                 # an alarm reaches the Corporal: +15
	var n1: float = it.notoriety()
	g1.knock_down(5.0, false)                # a takedown the Witness sees: +5
	var n2: float = it.notoriety()
	g3.knock_down(5.0, true)                 # a guard downed in open fight: +25
	var n3: float = it.notoriety()
	await wait_s(1.2)
	var wanted: bool = it.wanted()
	var vm: float = g2.notoriety_view_mult
	var view: float = g2.view_distance
	R["notoriety"] = n3
	R["wanted"] = wanted
	it.add_notoriety(IntelScript.NOTORIETY["night"], "a night passes")
	var n4: float = it.notoriety()
	it.flags_override["changed_coat"] = true
	await wait_s(1.2)
	var n5: float = it.notoriety()
	var ok := absf(n1 - 15) < 0.1 and absf(n2 - 20) < 0.1 and absf(n3 - 45) < 0.1 and wanted and absf(vm - 1.1) < 0.001 \
			and absf(n4 - 35) < 0.1 and absf(n5 - 17.5) < 0.1
	return "[smoke] intel notoriety runner=%.0f witnessed=%.0f fight=%.0f wanted=%s view_mult=%.2f view=%.1fm night=%.0f coat=%.1f %s" % [
			n1, n2, n3, wanted, vm, view, n4, n5, "OK" if ok else "FAIL"]


# ------------------------------------------------------------------ minimap

func sample_intel() -> Dictionary:
	var st: Dictionary = IntelScript.default_store()
	st["patrols"] = {"Rynek patrol A": {"wps": [[-20, -20], [18, -20], [18, -13], [-20, -12]], "sentry": false},
			"St Mary's post": {"wps": [[24, -14], [24, 4], [24, -8]], "sentry": false, "enforcer": true},
			"Cloth Hall sentry": {"wps": [[0, -7], [0, -7]], "sentry": true}}
	st["lamps"] = {"a": [-22, -22], "b": [22, -22], "c": [-5, -9], "d": [5, 9], "e": [24, 4]}
	st["spots"] = {"a": [-16, 20, "hay"], "b": [17.9, -7.9, "hay"]}
	st["enforcers"] = {"guard:St Mary's post": {"name": "St Mary's post", "kind": "guard"}, "spy": {"name": "The Man in the Brown Coat", "kind": "npc", "pos": [9.4, 11.6]}}
	st["places"] = {"brothel": [-27.9, 14.0, "The red lantern"], "vendor:chestnuts": [4, 7, "Chestnuts"]}
	st["zone"] = "barracks"
	return st


func add_minimap(w: Dictionary) -> Control:
	var layer := CanvasLayer.new()
	(w["vp"] as SubViewport).add_child(layer)
	var mm: Control = MinimapScript.new()
	mm.player = w["player"]
	mm.watch = w["watch"]
	mm.world = w["root"]
	mm.origin = (w["root"] as Node3D).global_position
	mm.intel_override = sample_intel()
	layer.add_child(mm)
	return mm


## The minimap gathers the player, the zone under him, a guard he can see (red dot) and nothing he cannot.
func t_minimap(idx: int) -> String:
	var w := phase_f(make_world(idx))
	var seen := guard(w, "Seen", [Vector3(0, 0, 18)], 0.0)
	var hidden := guard(w, "Behind a wall", [Vector3(12, 0, 18)], 0.0)
	wall(w, Vector3(6, 1.5, 24), Vector3(4, 3, 0.4))
	tp(w, Vector3(0, 0, 30), Vector3(0, 0, 18))
	var mm := add_minimap(w)
	await wait_s(0.3)
	mm.refresh()
	var gs: Array = mm.data.get("guards", [])
	var ok: bool = gs.size() == 1 and mm.data.get("player") == w["player"] and str(mm.data.get("zone", "")) == "street" and mm.visible
	R["minimap"] = ok
	return "[smoke] intel minimap guards_seen=%d (of 2) zone=%s player=%s %s" % [gs.size(), mm.data.get("zone", "-"),
			mm.data.get("player") != null, "OK" if ok else "FAIL"]


# ------------------------------------------------------------------ screenshots (--intel-shot=/dir)

func t_intel_shots(idx: int) -> String:
	var w := phase_f(make_world(idx, {"sweep.sentry_amplitude_deg": 0.0, "sweep.amplitude_deg": 0.0}, true))
	var it: Node = w["intel"]
	var root: Node3D = w["root"]
	var p: Player = w["player"]
	it.shots_mode = true
	_shot_env(root)
	for ix in range(-5, 6):
		for iz in range(-6, 6):
			var s := Assets.instance("ground_cobbles")
			if s:
				s.position = Vector3(ix * 4.0, 0, iz * 4.0)
				root.add_child(s)
	Assets.place(root, "tenement_a", Vector3(-5, 0, -14), 0.0)
	Assets.place(root, "tenement_c", Vector3(6, 0, -14), 0.0)
	lantern(w, Vector3(-4.8, 0, -7.6), false, true)
	var cam := Camera3D.new()
	cam.fov = 50
	root.add_child(cam)
	tp(w, Vector3(14, 0, 16))
	await wait_s(0.4)
	cam.current = true
	# 1. a wanted bill on the tenement wall
	it.add_notoriety(62.0, "shots")
	it.store()["last_seen"] = "the Cloth Hall passage"
	var places := {"shot_wall": {"from": [0.6, 0, -6.0], "dir": [0, 0, -1], "y": 1.75, "size": [0.52, 0.78]},
			"shot_wall2": {"from": [-1.3, 0, -6.0], "dir": [0, 0, -1], "y": 1.7, "size": [0.44, 0.56]}}
	it._post({"id": "shot_wanted", "kind": "wanted", "title": "A wanted bill", "place": "shot_wall"}, places, null)
	var db: Dictionary = it._bills_db
	it._post((db["bills"] as Array)[0].merged({"id": "shot_curfew", "place": "shot_wall2"}), places, null)
	await wait_s(0.2)
	var bill_pos := L(w, Vector3(0, 1.6, -9.9))
	for e in it.bills:
		if e["id"] == "shot_wanted":
			bill_pos = (e["node"] as Node3D).global_position
	cam.global_position = bill_pos + Vector3(-0.35, -0.1, 1.45)
	cam.look_at(bill_pos + Vector3(-0.3, -0.05, 0))
	var out := PackedStringArray()
	out.append(await _shot(w, "intel_bill_wanted", "bills=%d wanted=%d" % [it.bill_count(), it.wanted_count()]))
	# 2. an enforcer's red-edged cone, from above
	var g := guard(w, "Corporal", [Vector3(4, 0, 2)], PI * 0.85)
	g.enforcer = true
	g.suspicion = 30.0
	g.last_known = L(w, Vector3(6, 0, 8))
	tp(w, Vector3(14, 0, 16))
	await wait_s(0.6)
	cam.global_position = L(w, Vector3(4.5, 11, 13))
	cam.look_at(L(w, Vector3(4.5, 0, 5.5)))
	out.append(await _shot(w, "intel_enforcer_cone", "state=%s edge=%s" % [Guard.State.keys()[g.state], g._cone_edge != null]))
	g.queue_free()
	# 3. a trespass reaction: the player in the barracks zone, a sentry turns on him with a glossed bark
	var w2 := phase_f(make_world(idx + 1000, {"sweep.sentry_amplitude_deg": 0.0, "sweep.amplitude_deg": 0.0}, true))
	var r2: Node3D = w2["root"]
	_shot_env(r2)
	for ix in range(-4, 5):
		for iz in range(-4, 4):
			var s2 := Assets.instance("ground_cobbles")
			if s2:
				s2.position = Vector3(24 + ix * 4.0, 0, -10 + iz * 4.0)
				r2.add_child(s2)
	Assets.place(r2, "tenement_b", Vector3(24, 0, -24), 0.0)
	lantern(w2, Vector3(21.5, 0, -12.0), false, true)
	var sg := guard(w2, "Watchman", [Vector3(24, 0, -8)], 0.0)
	sg.add_to_group("mission")         # walker.gd culls bubbles far from the real player unless the speaker is a priority one
	tp(w2, Vector3(24, 0, 30))
	await wait_s(0.3)
	(w2["zones"] as Node).hook_guards()
	var mm2 := add_minimap(w2)
	var cam2 := Camera3D.new()
	cam2.fov = 55
	r2.add_child(cam2)
	cam2.current = true
	cam2.global_position = L(w2, Vector3(29.5, 3.2, -3.0))
	cam2.look_at(L(w2, Vector3(24, 1.3, -11.5)))
	tp(w2, Vector3(24.5, 0, -14.5), Vector3(24, 0, -8))
	await wait_until(func() -> bool: return sg.get_node_or_null("SpeechBubble") != null, 3.0)
	await wait_s(0.1)
	mm2.refresh()
	out.append(await _shot(w2, "intel_trespass", "zone=%s state=%s trespass=%s" % [(w2["zones"] as Node).current((w2["player"] as Node3D).global_position),
			Guard.State.keys()[sg.state], sg.is_trespass_seen()]) + " bubble=%s" % (sg.get_node_or_null("SpeechBubble") != null))
	await wait_s(0.3)
	mm2.refresh()
	out.append(await _shot(w2, "intel_minimap", "guards_seen=%d zone=%s" % [(mm2.data.get("guards", []) as Array).size(), mm2.data.get("zone", "-")]))
	# 4. the journal map, drawn in the sandbox's canvas from a sample of intel
	var layer := CanvasLayer.new()
	(w["vp"] as SubViewport).add_child(layer)
	var bg := ColorRect.new()
	bg.color = Color(0.075, 0.09, 0.12)
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	layer.add_child(bg)
	var mv := JournalScript.MapView.new()
	var st: Dictionary = sample_intel()
	mv.intel = st
	mv.world = root
	mv.position = Vector2(360, 40)
	mv.size = Vector2(880, 820)
	layer.add_child(mv)
	out.append(await _shot(w, "intel_map", "patrols=%d" % st["patrols"].size()))
	return "[smoke] intel screenshots " + " ".join(out)
