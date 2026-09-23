extends Node
## Intel and notoriety (docs/STEALTH.md 3.6-3.7, phases E and F). One per watch (watch.gd creates it as `intel`).
##
## Overhearing: hints in data/storylines.json `hints` (NPC pairs, guards muttering, storyline lines) and in
##   data/npcs.json (`hints` on an NPC). Stand within LISTEN_DIST of a speaker for LISTEN_SECS (a pair hint needs
##   a second townsperson beside the speaker; a guard must be calm) and he says it aloud ("text\n(gloss)"); a
##   storyline `say` step with `hint` counts within EARSHOT (storyline.gd `storyline_hint`). The hint goes into the
##   journal: Log ("heard at <place>, <time>"), the People page of whoever it is about, the Storylines page.
## Bills: data/bills.json paper quads on the notice board and on walls (a ray finds the facade). E reads one (full
##   text into the Log, a one-line message); E on a wanted bill already read tears it down: notoriety -5, crackdown
##   +1 if a guard sees it. Wanted bills appear at notoriety >= 30, written from the player's origin, sex and coat.
## Patrol recording: crouched and still (or sitting on a bench, twice as fast) with a guard in view for RECORD_SECS:
##   his waypoints go to the journal map as a dotted loop. The map also gets lanterns seen, hiding spots used,
##   vendors and the brothel once found, enforcers once seen, the player's zone.
## Notoriety 0..100: +15 per runner reaching the Corporal, +25 per guard downed in open fight, +5 per takedown a
##   comrade saw; -10 per night; halved when Mission.flags "changed_coat" is set (once per setting). At >= 30:
##   wanted bills and guards' view x1.1; at >= 60 each patrol route gets a second patrol at night start.
## Enforcers: guards named in missions.json `stealth.enforcers` ("guard:<name>") get guard.enforcer; enforcer NPCs
##   (npc.gd) do their own recognising. Watch routines (data/zones.json `watch_routines`): the Corporal's glass at the
##   Winiarnia at 22:30, the Cloth Hall sentry's midnight relief (guard "errand" tasks) make the hints true.
## State lives in Mission.journal["intel"] (survives nights; reset with the journal by a new game). `sandbox`: a
## private store, no Mission / GameState side effects (scripts/stealth/intel_smoke.gd).

const Perception := preload("res://scripts/stealth/perception.gd")
const Walker := preload("res://scripts/npc/walker.gd")
const Interactable := preload("res://scripts/mission/interactable.gd")
const Zones := preload("res://scripts/stealth/zones.gd")
const BILLS := "res://data/bills.json"

const LISTEN_DIST := 4.0
const LISTEN_SECS := 5.0
const EARSHOT := 14.0
const PAIR_DIST := 3.5
const RECORD_SECS := 10.0
const RECORD_DIST := 26.0
const SEE_DIST := 20.0
const NOTORIETY := {"runner": 15.0, "fight": 25.0, "witnessed": 5.0, "tear": -5.0, "night": -10.0}
const WANTED_AT := 30.0
const DOUBLE_AT := 60.0

var sandbox := false
var watch: Node
var speakers_override: Dictionary = {}   ## sandbox: speaker id -> Node3D
var board_override: Node3D               ## sandbox: the notice board to post on
var flags_override: Dictionary = {}      ## sandbox: stand-in for Mission.flags
var shots_mode := false                  ## intel_smoke shots: keep the bills lit

var hints: Dictionary = {}               ## hint id -> hint (data)
var speaker_hints: Dictionary = {}       ## speaker id -> [hint ids]
var bills: Array = []                    ## [{id, def, node, ia, wanted, read, torn}]
var enforcer_ids: Array = []             ## "guard:<name>" / npc ids (mission data)

var _local: Dictionary = {}              ## sandbox store
var _listen: Dictionary = {}             ## hint id -> seconds listened
var _record: Dictionary = {}             ## guard -> seconds watched
var _tick := 0.0
var _slow := 0.0
var _hooked: Array = []
var _routines_done: Dictionary = {}
var _ready_t := 0.0
var _posted := false
var _coat_seen := false
var _view_applied := -1.0
var _bills_db: Dictionary = {}
var _street_life: Node
static var _smoke_seeded := false


# ------------------------------------------------------------------ store

static func default_store() -> Dictionary:
	return {"hints": {}, "bills": {}, "patrols": {}, "lamps": {}, "spots": {}, "enforcers": {}, "places": {},
			"notoriety": 0.0, "last_day": 0, "alarms": 0, "overheard": 0, "recorded": 0, "zone": "street",
			"outfit": "none", "last_seen": "", "doubled_day": 0, "torn": 0}


## The campaign's intel (Mission.journal["intel"]), created on first use. The journal map reads it.
static func journal_store() -> Dictionary:
	var j: Dictionary = Mission.journal
	if not j.has("intel") or not (j["intel"] is Dictionary):
		j["intel"] = default_store()
	var st: Dictionary = j["intel"]
	for k in default_store():
		if not st.has(k):
			st[k] = default_store()[k]
	return st


func store() -> Dictionary:
	if sandbox:
		if _local.is_empty():
			_local = default_store()
		return _local
	return journal_store()


func notoriety() -> float:
	return float(store()["notoriety"])


func wanted() -> bool:
	return notoriety() >= WANTED_AT


func _flags() -> Dictionary:
	return flags_override if sandbox else Mission.flags


# ------------------------------------------------------------------ setup

func _ready() -> void:
	add_to_group("stealth_intel")
	_load_hints()
	_bills_db = _read_json(BILLS)
	if not sandbox:
		var st := store()
		var last := int(st["last_day"])
		if last > 0 and GameState.day > last:
			var nights := GameState.day - last
			add_notoriety(NOTORIETY["night"] * nights, "nights")
		st["last_day"] = GameState.day
		if Mission.is_active():
			enforcer_ids = Mission.data.get("stealth", {}).get("enforcers", [])
		_coat_seen = bool(Mission.flags.get("changed_coat", false))
	if watch:
		watch.runner_arrived.connect(_on_runner_arrived)
		watch.guard_downed.connect(_on_guard_downed)
		watch.hiding_changed.connect(_on_hiding_changed)


static func _read_json(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	var d: Variant = JSON.parse_string(f.get_as_text()) if f else null
	return d if d is Dictionary else {}


func _load_hints() -> void:
	var sd := _read_json("res://data/storylines.json")
	for h in sd.get("hints", []):
		_add_hint(h, h.get("speakers", []))
	var nd := _read_json("res://data/npcs.json")
	for n in nd.get("npcs", []):
		for h in n.get("hints", []):
			_add_hint(h, [str(n.get("id", ""))])


func _add_hint(h: Dictionary, speakers: Array) -> void:
	var id := str(h.get("id", ""))
	if id == "":
		return
	var hh := h.duplicate()
	hh["speakers"] = speakers
	hints[id] = hh
	if h.has("story"):
		return
	for s in speakers:
		if not speaker_hints.has(s):
			speaker_hints[s] = []
		speaker_hints[s].append(id)


func player() -> Node3D:
	return watch.get_player() if watch else null


func _origin() -> Vector3:
	var z: Node = watch.get("zones") if watch else null
	return z.origin if z else Vector3.ZERO


func _xz(p: Vector3) -> Array:
	var o := _origin()
	return [snappedf(p.x - o.x, 0.01), snappedf(p.z - o.z, 0.01)]


func _place_of(p: Vector3) -> String:
	if sandbox:
		return "the practice yard"
	return Journal.place_of(p)


func _time() -> String:
	return "night" if sandbox else GameState.time_string()


func _journal() -> Node:
	if sandbox:
		return null
	return get_tree().get_first_node_in_group("journal")


func _log(text: String, kind: String) -> void:
	if not sandbox:
		Mission.journal_log(text, kind)


func _note(text: String) -> void:
	var j := _journal()
	if j and j.has_signal("noted"):
		j.noted.emit(text)


# ------------------------------------------------------------------ per frame

func _physics_process(delta: float) -> void:
	_ready_t += delta
	var p := player()
	if p == null or not is_instance_valid(p):
		return
	if not _posted and _ready_t > 0.6:
		_posted = true
		_post_bills()
		_apply_night_start()
	_patrol_recording(p, delta)
	_tick += delta
	if _tick >= 0.25:
		_listen_tick(p, _tick)
		_tick = 0.0
	_slow += delta
	if _slow >= 1.0:
		_slow = 0.0
		_slow_tick(p)
	if not sandbox and "--smoke" in OS.get_cmdline_user_args() and not _smoke_seeded and _ready_t > 1.5:
		_smoke_seeded = true
		_smoke_seed()


func _slow_tick(p: Node3D) -> void:
	var st := store()
	var z: Node = watch.get("zones")
	if z:
		st["zone"] = z.current(p.global_position)
		st["outfit"] = z.outfit(p)
	# enforcer guards (mission data) and the notoriety view
	var vm := 1.1 if wanted() else 1.0
	for g in watch.guards():
		if enforcer_ids.has("guard:" + str(g.guard_name)) and not g.enforcer:
			g.enforcer = true
		if absf(g.notoriety_view_mult - vm) > 0.001:
			g.notoriety_view_mult = vm
			g.refresh_mults()
	_discover(p)
	_hook_storylines()
	_routines()
	# anyone may set changed_coat (a future outfit system): it halves notoriety once per setting
	var coat := bool(_flags().get("changed_coat", false))
	if coat and not _coat_seen:
		add_notoriety(-notoriety() * 0.5, "changed coat")
		if not sandbox:
			Mission.message.emit("A different coat: the description on the bills no longer fits so well.", 3.0)
	_coat_seen = coat


# ------------------------------------------------------------------ overhearing

func _speaker_node(id: String) -> Node3D:
	if speakers_override.has(id):
		return speakers_override[id]
	if sandbox:
		return null
	if id.begins_with("guard:"):
		var gname := id.trim_prefix("guard:")
		for g in watch.guards():
			if str(g.guard_name) == gname:
				return g
		return null
	var pop := _population()
	return pop.actor(id) if pop else null


func _population() -> Node:
	for n in get_tree().get_nodes_in_group("population"):
		if not (n is Node3D) or Perception.same_world(n, watch):
			return n
	return null


func _listen_tick(p: Node3D, dt: float) -> void:
	var st := store()
	var active: Dictionary = {}
	for sid in speaker_hints:
		var pending := ""
		for hid in speaker_hints[sid]:
			if not st["hints"].has(hid):
				pending = hid
				break
		if pending == "" or active.has(pending):
			continue
		var n := _speaker_node(str(sid))
		if n == null or not is_instance_valid(n) or not n.is_visible_in_tree():
			continue
		if n.has_method("is_downed") and n.is_downed():
			continue
		if n is Guard and (n.state >= n.State.SEARCHING or n.is_runner):
			continue
		var to := n.global_position - p.global_position
		if absf(to.y) > 2.5 or Vector2(to.x, to.z).length() > LISTEN_DIST:
			continue
		var h: Dictionary = hints[pending]
		if not bool(h.get("solo", false)) and not _has_partner(n, h):
			continue
		active[pending] = n
	for hid in _listen.keys():
		if not active.has(hid):
			_listen.erase(hid)
	for hid in active:
		_listen[hid] = float(_listen.get(hid, 0.0)) + dt
		if _listen[hid] >= LISTEN_SECS:
			_listen.erase(hid)
			var h: Dictionary = hints[hid]
			var n: Node3D = active[hid]
			Walker.speech(n, "%s\n(%s)" % [h.get("text", ""), h.get("gloss", "")], 5.0, 2.3 if n is Guard else 2.15)
			record_hint(hid, n)


func _has_partner(n: Node3D, h: Dictionary) -> bool:
	var pool: Array = []
	for s in h.get("speakers", []):
		var o := _speaker_node(str(s))
		if o and o != n:
			pool.append(o)
	if not sandbox:
		pool += get_tree().get_nodes_in_group("npcs")
	for o in pool:
		if o != n and is_instance_valid(o) and (o as Node3D).is_visible_in_tree() \
				and (o as Node3D).global_position.distance_to(n.global_position) < PAIR_DIST:
			return true
	return false


## Writes hint `hid` (heard from `speaker`) to the journal. Returns false if it was already known.
func record_hint(hid: String, speaker: Node3D) -> bool:
	var st := store()
	if st["hints"].has(hid) or not hints.has(hid):
		return false
	var h: Dictionary = hints[hid]
	var where := _place_of(speaker.global_position) if speaker else "?"
	var entry := {"note": str(h.get("note", "")), "text": str(h.get("text", "")), "gloss": str(h.get("gloss", "")),
			"about": str(h.get("about", "")), "tab": str(h.get("tab", "log")), "where": where, "t": _time(),
			"night": 0 if sandbox else GameState.day, "story": str(h.get("story", ""))}
	st["hints"][hid] = entry
	st["overheard"] = int(st["overheard"]) + 1
	_log("Overheard: %s  (heard at %s, %s)" % [entry["note"], where, entry["t"]], "intel")
	var j := _journal()
	if j:
		var about: String = entry["about"]
		if about != "" and not about.begins_with("guard:") and j.has_method("meet"):
			j.meet(about, _speaker_node(about))
		if entry["story"] != "" and j.has_method("discover"):
			j.discover(entry["story"], "overheard")
	_note("Overheard: " + str(entry["note"]).get_slice(".", 0))
	return true


func _hook_storylines() -> void:
	var pop := _population()
	if pop == null or sandbox:
		return
	for s in pop.get("storylines"):
		if not is_instance_valid(s) or _hooked.has(s) or not s.has_signal("storyline_hint"):
			continue
		_hooked.append(s)
		s.storyline_hint.connect(_on_story_hint)


func _on_story_hint(_story: String, hid: String, actor: Node3D) -> void:
	var p := player()
	if p == null or actor == null or actor.global_position.distance_to(p.global_position) > EARSHOT:
		return
	record_hint(hid, actor)


# ------------------------------------------------------------------ patrol recording

func _still_watching(p: Node3D) -> float:
	var hs: Variant = p.get("hidden_spot")
	if hs != null and is_instance_valid(hs) and str(hs.get("kind")) == "bench":
		return 2.0
	if hs != null:
		return 0.0
	if p.is_crouching and Vector2(p.velocity.x, p.velocity.z).length() < 0.25:
		return 1.0
	return 0.0


func guard_in_view(p: Node3D, g: Node3D) -> bool:
	var head: Vector3 = p.head_position() if p.has_method("head_position") else p.global_position + Vector3(0, 1.6, 0)
	var chest := g.global_position + Vector3(0, 1.3, 0)
	if head.distance_to(chest) > RECORD_DIST:
		return false
	var cam: Camera3D = p.camera() if p.has_method("camera") else null
	if cam and cam.is_inside_tree() and not cam.is_position_in_frustum(chest):
		return false
	return Perception.clear_line(g.get_world_3d().direct_space_state, head, chest, [p.get_rid(), g.get_rid()], null, true)


func _patrol_recording(p: Node3D, delta: float) -> void:
	var rate := _still_watching(p)
	if rate <= 0.0:
		_record.clear()
		return
	var st := store()
	for g in watch.guards():
		if g.is_downed() or st["patrols"].has(str(g.guard_name)):
			continue
		if not guard_in_view(p, g):
			continue
		_record[g] = float(_record.get(g, 0.0)) + delta * rate
		if _record[g] >= RECORD_SECS:
			_record.erase(g)
			record_patrol(g)


func record_progress(g: Node) -> float:
	return float(_record.get(g, 0.0))


## His route (waypoints) goes onto the journal map.
func record_patrol(g: Node) -> void:
	var st := store()
	var wps: Array = []
	for w in g.waypoints:
		wps.append(_xz(w))
	var sentry: bool = g.waypoints.size() <= 2 and g.waypoints[0].distance_to(g.waypoints[-1]) < 0.3
	st["patrols"][str(g.guard_name)] = {"wps": wps, "sentry": sentry, "t": _time(), "night": 0 if sandbox else GameState.day,
			"enforcer": bool(g.enforcer)}
	st["recorded"] = int(st["recorded"]) + 1
	var what := "his post" if sentry else "his round"
	_log("You watched the %s long enough to learn %s: it is marked on the journal map." % [g.guard_name, what], "intel")
	_note("Marked on the map: the %s's %s" % [g.guard_name, "post" if sentry else "round"])


# ------------------------------------------------------------------ map discoveries

func _on_hiding_changed(spot: Node, occupied: bool) -> void:
	var p := player()
	if occupied and p and p.get("hidden_spot") == spot:
		var st := store()
		var k := "%d,%d" % [roundi(spot.global_position.x), roundi(spot.global_position.z)]
		st["spots"][k] = _xz(spot.global_position) + [str(spot.get("kind"))]


func _discover(p: Node3D) -> void:
	var st := store()
	var head: Vector3 = p.head_position() if p.has_method("head_position") else p.global_position + Vector3(0, 1.6, 0)
	var space := p.get_world_3d().direct_space_state
	for l in watch.lamps():
		var lp: Vector3 = l.global_position + Vector3(0, 2.6, 0)
		var k := "%d,%d" % [roundi(l.global_position.x), roundi(l.global_position.z)]
		if st["lamps"].has(k) or lp.distance_to(head) > SEE_DIST:
			continue
		if Perception.clear_line(space, head, lp, [p.get_rid()], null, true):
			st["lamps"][k] = _xz(l.global_position)
	if sandbox:
		return
	# enforcers seen: guards flagged enforcer, NPCs flagged enforcer (npc.gd)
	for g in watch.guards():
		if g.enforcer and not st["enforcers"].has("guard:" + str(g.guard_name)) and guard_in_view(p, g) \
				and g.global_position.distance_to(p.global_position) < 14.0:
			_mark_enforcer("guard:" + str(g.guard_name), str(g.guard_name), "guard", g)
	for n in get_tree().get_nodes_in_group("enforcer_npc"):
		var nn := n as Node3D
		var id := str(n.get("npc_id"))
		if nn and not st["enforcers"].has(id) and nn.is_visible_in_tree() and nn.global_position.distance_to(p.global_position) < 10.0 \
				and guard_in_view(p, nn):
			_mark_enforcer(id, Journal.person_name(id), "npc", nn)
	# vendors and the brothel, once near
	for vm in get_tree().get_nodes_in_group("vendors"):
		for v in vm.get("vendors"):
			var b: Node3D = v.body
			if b == null or not is_instance_valid(b) or st["places"].has("vendor:" + str(v.id)):
				continue
			if b.global_position.distance_to(p.global_position) < 12.0:
				st["places"]["vendor:" + str(v.id)] = _xz(b.global_position) + [str(v.d.get("name", str(v.id).capitalize()))]
	if not st["places"].has("brothel"):
		if _street_life == null and watch.get_parent() and int(_ready_t) % 5 == 1:
			_street_life = watch.get_parent().find_child("StreetLife", true, false)
		var sl: Node = _street_life if is_instance_valid(_street_life) else null
		if sl and sl.get("brothel_door") is Vector3 and sl.brothel_door != Vector3.ZERO \
				and (sl.brothel_door as Vector3).distance_to(p.global_position) < 14.0:
			st["places"]["brothel"] = _xz(sl.brothel_door) + ["The red lantern"]


func _mark_enforcer(id: String, pname: String, kind: String, node: Node3D) -> void:
	var st := store()
	st["enforcers"][id] = {"name": pname, "kind": kind, "night": 0 if sandbox else GameState.day,
			"where": _place_of(node.global_position), "pos": _xz(node.global_position)}
	var j := _journal()
	if j and kind == "npc" and j.has_method("meet"):
		j.meet(id, node)
	_log("%s knows your face: no cloak will fool %s." % [pname, "him"], "intel")


# ------------------------------------------------------------------ notoriety

func add_notoriety(delta: float, why: String) -> void:
	var st := store()
	var before := float(st["notoriety"])
	st["notoriety"] = clampf(before + delta, 0.0, 100.0)
	var after := float(st["notoriety"])
	if not sandbox and "--smoke" in OS.get_cmdline_user_args() and absf(after - before) > 0.01:
		print("[smoke]   intel notoriety %.0f -> %.0f (%s)" % [before, after, why])
	if before < WANTED_AT and after >= WANTED_AT:
		_log("Your description is being posted on the walls of the Rynek.", "intel")
		if not sandbox:
			Mission.message.emit("Wanted bills with your description are going up on the walls.", 3.0)
	if _posted:
		refresh_wanted()


func _on_runner_arrived(_g: Node) -> void:
	var st := store()
	st["alarms"] = int(st["alarms"]) + 1
	st["last_seen"] = _place_of(watch.ghost)
	add_notoriety(NOTORIETY["runner"], "alarm reached the Corporal")


func _on_guard_downed(g: Node, in_fight: bool, witness: Node) -> void:
	if in_fight:
		store()["last_seen"] = _place_of(g.global_position)
		add_notoriety(NOTORIETY["fight"], "guard downed in the open")
	elif witness != null:
		add_notoriety(NOTORIETY["witnessed"], "takedown witnessed")


func _apply_night_start() -> void:
	if sandbox:
		return
	var st := store()
	if notoriety() >= DOUBLE_AT and int(st["doubled_day"]) != GameState.day:
		st["doubled_day"] = GameState.day
		double_patrols()


## A second patrol on every patrol route (not sentries), walking it the other way round.
func double_patrols() -> int:
	var district: Node = watch.get_parent()
	if district == null or not district.has_method("spawn_guard"):
		return 0
	var n := 0
	for g in watch.guards():
		if g.waypoints.size() < 3 or str(g.guard_name).ends_with(" II"):
			continue
		var wps: Array = []
		for w in g.waypoints:
			wps.push_front(w)
		var ng: Node = district.spawn_guard(str(g.guard_name) + " II", wps, g.rotation.y + PI)
		if ng:
			n += 1
	if n > 0:
		_log("The Austrians have doubled the patrols tonight: your face is known.", "intel")
	return n


# ------------------------------------------------------------------ watch routines

func _routines() -> void:
	if sandbox:
		return
	for r in Zones.db().get("watch_routines", []):
		var id := str(r.get("id", ""))
		if _routines_done.has(id):
			continue
		var at := GameState.parse_clock(str(r.get("at", "23:00")))
		if GameState.clock_minutes < at:
			continue
		if GameState.clock_minutes > at + 20.0:
			_routines_done[id] = true
			continue
		for g in watch.guards():
			if str(g.guard_name) == str(r.get("guard", "")) and not g.is_downed() and g.state == g.State.CALM:
				var pos := Perception.vec(r.get("pos"))
				if g.set_task({"kind": "errand", "pos": pos, "minutes": float(r.get("minutes", 5.0)),
						"max_t": float(r.get("minutes", 5.0)) / maxf(GameState.clock_scale, 0.01) + 120.0, "label": str(r.get("label", ""))}):
					_routines_done[id] = true
					print("[intel] %s leaves for %s at %s" % [g.guard_name, r.get("label", "?"), GameState.time_string()])


# ------------------------------------------------------------------ bills

func _find_board() -> Node3D:
	if board_override:
		return board_override
	var district: Node = watch.get_parent()
	if district == null:
		return null
	for n in district.find_children("*", "Node3D", true, false):
		if (n as Node).scene_file_path.get_file().get_basename() == "notice_board":
			return n
	return null


func _post_bills() -> void:
	var places: Dictionary = _bills_db.get("places", {})
	var board := _find_board()
	for b in _bills_db.get("bills", []):
		if str(b.get("kind", "")) == "wanted":
			continue
		_post(b, places, board)
	refresh_wanted()


## Posts (or re-writes) the wanted bills notoriety calls for; takes them down when it falls below.
func refresh_wanted() -> void:
	var places: Dictionary = _bills_db.get("places", {})
	var board := _find_board()
	var wd: Dictionary = _bills_db.get("wanted", {})
	for b in _bills_db.get("bills", []):
		if str(b.get("kind", "")) != "wanted":
			continue
		var need := maxf(float(wd.get("min_notoriety", WANTED_AT)), float(b.get("min_notoriety", 0.0)))
		var existing: Dictionary = {}
		for e in bills:
			if e["id"] == b["id"]:
				existing = e
		if notoriety() >= need:
			if existing.is_empty():
				_post(b, places, board)
			elif not existing["torn"]:
				_write_bill(existing)
		elif not existing.is_empty() and is_instance_valid(existing["node"]):
			existing["node"].visible = false


func _post(b: Dictionary, places: Dictionary, board: Node3D) -> void:
	var pl: Dictionary = places.get(str(b.get("place", "")), {})
	if pl.is_empty():
		return
	var parent: Node3D = null
	var xf := Transform3D.IDENTITY
	if str(pl.get("on", "")) == "notice_board":
		if board == null:
			return
		parent = board
		var loc: Array = pl.get("local", [0, 1.2, 0.05])
		var z := float(loc[2]) + (0.006 if b.has("over") else 0.0)
		xf.origin = Vector3(float(loc[0]), float(loc[1]), z)
	else:
		var root: Node3D = watch.get_parent() as Node3D
		if root == null:
			return
		var o := _origin()
		var from := Perception.vec(pl.get("from")) + o + Vector3(0, float(pl.get("y", 1.7)), 0)
		var dir := Perception.vec(pl.get("dir"), Vector3(0, 0, -1)).normalized()
		var q := PhysicsRayQueryParameters3D.create(from, from + dir * 12.0)
		var hit := root.get_world_3d().direct_space_state.intersect_ray(q)
		if hit.is_empty() or hit.get("collider") is CharacterBody3D:
			return
		var nrm: Vector3 = hit["normal"]
		nrm.y = 0.0
		if nrm.length() < 0.5:
			return
		nrm = nrm.normalized()
		parent = root
		xf.basis = Basis.looking_at(-nrm, Vector3.UP)
		xf.origin = root.to_local(Vector3(hit["position"]) + nrm * 0.035)
	var sz: Array = pl.get("size", [0.45, 0.6])
	var node := Node3D.new()
	node.name = "Bill_" + str(b.get("id", ""))
	node.transform = xf
	parent.add_child(node)
	var e := {"id": str(b.get("id", "")), "def": b, "node": node, "ia": null, "wanted": str(b.get("kind", "")) == "wanted",
			"read": false, "torn": false, "size": Vector2(float(sz[0]), float(sz[1]))}
	bills.append(e)
	if b.has("over"):
		for u in bills:
			if u["id"] == str(b["over"]) and is_instance_valid(u["node"]):
				u["node"].visible = false
				if u["ia"]:
					u["ia"].enabled = false
	_write_bill(e)
	# the interactable stands at the foot of the wall, in front of the paper
	var ia := Interactable.new()
	ia.name = "ReadBill"
	ia.display_name = str(b.get("title", "A bill"))
	ia.set_meta("low_priority", true)
	ia.highlight_root = node
	ia.prompt_func = func() -> String:
		if e["torn"] or not node.visible:
			return ""
		if not e["read"]:
			return "read the bill"
		return "tear the bill down" if e["wanted"] else ""
	ia.handler = func(_actor: Node) -> bool:
		return use_bill(e)
	node.add_child(ia)
	var world_pos := node.global_position
	ia.global_position = Vector3(world_pos.x, world_pos.y - 1.1, world_pos.z) + node.global_basis.z * 0.25
	ia.marker_height = 1.1 + e["size"].y * 0.5 + 0.12
	e["ia"] = ia


## The paper: a quad with the heading (text + gloss) in ink, a few ruled lines, a sketch and description if wanted.
func _write_bill(e: Dictionary) -> void:
	var node: Node3D = e["node"]
	for c in node.get_children():
		if c.name != "ReadBill":
			c.queue_free()
	var sz: Vector2 = e["size"]
	var b: Dictionary = e["def"]
	var paper := MeshInstance3D.new()
	paper.name = "Paper"
	var qm := QuadMesh.new()
	qm.size = sz
	paper.mesh = qm
	var mat := StandardMaterial3D.new()
	var old := str(b.get("kind", "")) == "theatre"
	mat.albedo_color = Color(0.80, 0.72, 0.55) if old else (Color(0.88, 0.84, 0.72) if e["wanted"] else Color(0.84, 0.79, 0.66))
	mat.roughness = 0.95
	mat.emission_enabled = true
	mat.emission = mat.albedo_color
	mat.emission_energy_multiplier = 0.08
	paper.material_override = mat
	paper.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.add_child(paper)
	var heading: Array = b.get("heading", [])
	var desc: Array = []
	if e["wanted"]:
		var w := wanted_text()
		heading = w["heading"]
		desc = w["paper"]
	# ink scales with the paper: a wanted bill needs its whole height for heading, face and description
	var f := clampf(sz.y / (0.8 if e["wanted"] else 0.62), 0.55, 1.2)
	var y := sz.y * 0.5 - 0.03 * f
	for i in heading.size():
		var hl: Array = heading[i]
		var big := i == 0
		y -= _ink_line(node, str(hl[0]), y, sz.x, (0.072 if big else 0.05) * f, Color(0.08, 0.05, 0.03) if not (e["wanted"] and big) else Color(0.42, 0.04, 0.03), "bold" if big else "regular")
		y -= _ink_line(node, "(%s)" % hl[1], y, sz.x, 0.03 * f, Color(0.3, 0.22, 0.14), "italic")
		y -= 0.008 * f
	if e["wanted"]:
		# a rough sketch of a face in a frame
		var face := MeshInstance3D.new()
		var fm := QuadMesh.new()
		fm.size = Vector2(0.15, 0.175) * f
		face.mesh = fm
		var fmat := StandardMaterial3D.new()
		fmat.albedo_texture = _sketch_tex()
		fmat.albedo_color = Color(1, 1, 1)
		fmat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		fmat.roughness = 1.0
		face.material_override = fmat
		face.position = Vector3(0, y - fm.size.y * 0.5 - 0.008 * f, 0.002)
		node.add_child(face)
		y -= fm.size.y + 0.02 * f
		for dl in desc:
			y -= _ink_line(node, str(dl[0]), y, sz.x, 0.028 * f, Color(0.08, 0.05, 0.03), "regular", true)
			y -= _ink_line(node, "(%s)" % dl[1], y, sz.x, 0.022 * f, Color(0.3, 0.22, 0.14), "italic", true)
			y -= 0.006 * f
	# ruled "print" lines below
	var k := 0
	while y > -sz.y * 0.5 + 0.05 and k < 6:
		var ln := MeshInstance3D.new()
		var lm := QuadMesh.new()
		lm.size = Vector2(sz.x * (0.72 if k % 2 == 0 else 0.6), 0.008)
		ln.mesh = lm
		var lmat := StandardMaterial3D.new()
		lmat.albedo_color = Color(0.18, 0.13, 0.09)
		lmat.roughness = 1.0
		ln.material_override = lmat
		ln.position = Vector3(0, y - 0.02, 0.0015)
		node.add_child(ln)
		y -= 0.034
		k += 1


## One line of ink on the paper, fitted to its width (wrapped over at most two lines when `wrap`, then shrunk).
## Returns the height used.
func _ink_line(node: Node3D, text: String, top: float, width: float, height: float, col: Color, face: String, wrap := false) -> float:
	var l := Label3D.new()
	l.text = text
	var font := UiTheme.font(face)
	l.font = font
	l.font_size = 64
	l.outline_size = 0
	l.modulate = col
	l.shaded = true
	l.double_sided = false
	l.alpha_cut = Label3D.ALPHA_CUT_OPAQUE_PREPASS
	l.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	var avail := width * 0.86
	var px := height / 64.0
	var w_text := (font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 64).x if font else text.length() * 40.0) * px
	var lines := 1
	if wrap and w_text > avail:
		lines = 2
		if w_text * 1.15 > avail * 2.0:
			px *= avail * 2.0 / (w_text * 1.15)
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.width = avail / px
	elif w_text > avail:
		px *= avail / w_text
	l.pixel_size = px
	l.position = Vector3(0, top, 0.003)
	node.add_child(l)
	return 64.0 * px * 1.18 * lines


static var _sketch: Texture2D
static func _sketch_tex() -> Texture2D:
	if _sketch:
		return _sketch
	var img := Image.create(48, 56, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	var ink := Color(0.12, 0.08, 0.05, 0.9)
	for a in 64:
		var t := a / 64.0 * TAU
		var p := Vector2(24 + cos(t) * 13, 25 + sin(t) * 17)
		img.set_pixelv(Vector2i(p), ink)
		img.set_pixelv(Vector2i(p) + Vector2i(1, 0), ink)
	for x in range(0, 48):         # frame
		img.set_pixel(x, 0, ink)
		img.set_pixel(x, 55, ink)
	for yy in range(0, 56):
		img.set_pixel(0, yy, ink)
		img.set_pixel(47, yy, ink)
	for x in range(8, 40):        # hat brim
		img.set_pixel(x, 10, ink)
		img.set_pixel(x, 11, ink)
	for x in range(14, 34):       # hat crown
		for yy in range(3, 10):
			img.set_pixel(x, yy, Color(ink, 0.7))
	for d in [Vector2i(18, 22), Vector2i(29, 22)]:   # eyes
		for dx in 3:
			img.set_pixelv(d + Vector2i(dx, 0), ink)
	for yy in range(24, 32):      # nose
		img.set_pixel(24, yy, ink)
	for x in range(19, 30):       # mouth
		img.set_pixel(x, 35, ink)
	for x in range(10, 38):       # shoulders
		img.set_pixel(x, 48 - absi(x - 24) / 3, ink)
	_sketch = ImageTexture.create_from_image(img)
	return _sketch


## The wanted text from bills.json and the player: {heading: [[de/pl, gloss]], desc: [[de, gloss]]}.
func wanted_text() -> Dictionary:
	var wd: Dictionary = _bills_db.get("wanted", {})
	var sex := "m" if sandbox else GameState.gender
	var oid := "veteran" if sandbox else GameState.origin_id
	var od: Dictionary = wd.get("origins", {}).get(oid, wd.get("origins", {}).get("_default", {}))
	var n := notoriety()
	var desc: Array = []
	var sx: Array = wd.get("sex", {}).get(sex, ["jemand", "someone"])
	var coat: Array = od.get("coat", ["", ""])
	desc.append(["%s, %s" % [sx[0], coat[0]], "%s, %s" % [sx[1], coat[1]]])
	if n >= 45.0:
		desc.append(od.get("trait", ["", ""]))
	var st := store()
	if n >= float(wd.get("reward_at", 60)):
		if str(st["last_seen"]) != "":
			var ls: Array = wd.get("last_seen", ["%s", "%s"])
			desc.append([str(ls[0]) % st["last_seen"], str(ls[1]) % st["last_seen"]])
		desc.append(wd.get("reward", ["", ""]))
	var paper: Array = [desc[0]]
	if n >= float(wd.get("reward_at", 60)):
		paper.append(wd.get("reward", ["", ""]))
	return {"heading": wd.get("heading_f" if sex == "f" else "heading", [["GESUCHT", "Wanted"]]), "desc": desc,
			"paper": paper, "intro": wd.get("intro", ["", ""])}


## E on a bill: read it (full text to the journal, one line on screen), or tear down a wanted bill already read.
func use_bill(e: Dictionary) -> bool:
	var st := store()
	var b: Dictionary = e["def"]
	if not e["read"]:
		e["read"] = true
		var lines: Array = []
		var title := str(b.get("title", "A bill"))
		if e["wanted"]:
			var w := wanted_text()
			lines.append(w["intro"])
			lines += w["desc"]
		else:
			lines = b.get("lines", [])
		var text := PackedStringArray()
		for l in lines:
			text.append("%s (%s)" % [l[0], l[1]])
		var where := _place_of((e["node"] as Node3D).global_position)
		st["bills"][e["id"]] = {"title": title, "text": " ".join(text), "note": str(b.get("note", "")), "where": where,
				"t": _time(), "night": 0 if sandbox else GameState.day, "wanted": e["wanted"]}
		_log("%s, read at %s: %s" % [title, where, " ".join(text)], "bill")
		if not sandbox:
			Mission.message.emit("You read %s. The full text is in your journal." % title.to_lower(), 2.5)
		return true
	if e["wanted"] and not e["torn"]:
		e["torn"] = true
		var node: Node3D = e["node"]
		var seen := false
		for g in watch.guards():
			if g.can_see_point(node.global_position):
				seen = true
				break
		node.visible = false
		st["torn"] = int(st["torn"]) + 1
		add_notoriety(NOTORIETY["tear"], "bill torn down")
		if seen and not sandbox:
			GameState.crackdown = clampi(GameState.crackdown + 1, 0, 100)
		if not sandbox:
			Mission.message.emit("You tear the bill from the wall." + (" A soldier saw you do it." if seen else ""), 2.5)
		e["seen_tearing"] = seen
		return true
	return false


func bill_count(visible_only := true) -> int:
	var n := 0
	for e in bills:
		if is_instance_valid(e["node"]) and (not visible_only or (e["node"] as Node3D).visible):
			n += 1
	return n


func wanted_count() -> int:
	var n := 0
	for e in bills:
		if e["wanted"] and not e["torn"] and is_instance_valid(e["node"]) and (e["node"] as Node3D).visible:
			n += 1
	return n


# ------------------------------------------------------------------ smoke

## `--smoke`, first night only: exercise the district side (a patrol recorded, lanterns marked) so the journal map
## shot has something on it, and print what was posted.
func _smoke_seed() -> void:
	var p := player()
	for g in watch.guards():
		if str(g.guard_name) == "Rynek patrol A" or str(g.guard_name) == "St Mary's post":
			if str(g.guard_name) == "St Mary's post":
				g.enforcer = true
				_mark_enforcer("guard:St Mary's post", "St Mary's post", "guard", g)
				record_hint("corporal_himself", g)
			record_patrol(g)
	if not bills.is_empty():
		use_bill(bills[0])
	for l in watch.lamps().slice(0, 5):
		store()["lamps"]["%d,%d" % [roundi(l.global_position.x), roundi(l.global_position.z)]] = _xz(l.global_position)
	var z: Node = watch.get("zones")
	var names := PackedStringArray()
	for e in bills:
		names.append(str(e["id"]))
	print("[smoke] intel district bills=%d (%s) hints=%d zone_townhall_door=%s zone_post=%s zone_player=%s outfit=%s" % [
			bill_count(), ",".join(names), hints.size(), z.current(Vector3(-16, 0, 17.5)) if z else "-",
			z.current(Vector3(24, 0, -10)) if z else "-", z.current(p.global_position) if z and p else "-", z.outfit(p) if z else "-"])
