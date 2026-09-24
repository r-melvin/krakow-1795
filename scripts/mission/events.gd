extends Node
## Random events with player participation (data/events.json; docs/GDD.md "Campaign"). Created by
## mission_runner.gd under the night world, freed with it. At most `max_per_night` events a night, each at most
## once, staged at an anchor 12-40 m from the player so they can be seen and joined: actors are ordinary
## townsfolk spawned through population.spawn_entry (claimed, group "mission", so vendors and street life leave
## them alone), one of them carries a talk interactable with the event's dialogue (the runner's dialogue box and
## verbs); a choice's `ev:<id>:<outcome>` resolves the event: campaign effects now, a line in the dawn report.
## Specials: fire (flickering light, the watch drawn to it), procession (walk with it: disguised while it lasts),
## lamps (lights near the lamplighter go dark), flogging (street_life.gd's flogging scene if it has start_event).
## `--smoke`: nothing fires by itself unless `auto` is set (the campaign smoke forces events with `force`).

const DATA := "res://data/events.json"

static var auto_in_smoke := false

var runner: Node
var db: Dictionary = {}
var fired: Array = []             ## event ids staged tonight
var active: Dictionary = {}       ## {id, actors: [Node3D], key, anchor: Vector3, t0, done_at, light}
var last_outcome := ""
var _next_at := 0.0
var _tick := 0.0
var _bark_t := 0.0
var _serial := 0
var _rng := RandomNumberGenerator.new()
var _disguise_left := 0.0
var _smoke := false


func _ready() -> void:
	var f := FileAccess.open(DATA, FileAccess.READ)
	if f:
		var d: Variant = JSON.parse_string(f.get_as_text())
		if d is Dictionary:
			db = d
	_rng.seed = hash("events|%d|%s" % [GameState.day, GameState.origin_id])
	_smoke = "--smoke" in OS.get_cmdline_user_args()
	_next_at = GameState.parse_clock(str(db.get("first_at", "21:06")))


func _player() -> Node3D:
	return runner.player() if runner else null


func _physics_process(delta: float) -> void:
	if runner == null or not Mission.is_active():
		return
	if _disguise_left > 0.0:
		_disguise_left -= delta
		if _disguise_left <= 0.0:
			var p0 := _player()
			if p0 and not _outfit_flag():
				p0.disguised = false
				Mission.message.emit("The procession disperses. You are yourself again.", 3.0)
	_tick += delta
	if not active.is_empty():
		_manage(delta)
		return
	if _tick < 0.5:
		return
	_tick = 0.0
	if _smoke and not auto_in_smoke:
		return
	if GameState.clock_minutes < _next_at or fired.size() >= int(db.get("max_per_night", 3)):
		return
	var ev: Array = db.get("every", [5, 9])
	_next_at = GameState.clock_minutes + _rng.randf_range(float(ev[0]), float(ev[1]))
	var p := _player()
	if p == null or runner.dialogue_open():
		return
	var ids: Array = eligible()
	if ids.is_empty():
		return
	ids.shuffle()
	for eid in ids:
		if stage(str(eid)):
			return


func _outfit_flag() -> bool:
	for f in ["disguise_austrian", "disguise_clergy", "invited", "masked", "laundress", "drunk_act"]:
		if Mission.has_flag(f):
			return true
	return false


func eligible() -> Array:
	var out: Array = []
	var c := GameState.clock_minutes
	for eid in db.get("events", {}):
		if eid in fired:
			continue
		var e: Dictionary = db["events"][eid]
		var hr: Array = e.get("hours", ["21:00", "04:00"])
		if c < GameState.parse_clock(str(hr[0])) or c > GameState.parse_clock(str(hr[1])):
			continue
		if Mission.campaign and Mission.campaign.night() < int(e.get("min_night", 1)):
			continue
		if not runner.cond_list(e.get("if", [])):
			continue
		out.append(eid)
	return out


func _anchor(e: Dictionary, p: Vector3) -> Variant:
	if e.has("interior"):
		var it: Node = runner.interiors
		if it == null or not it.has_method("inside"):
			return null
		var room := str(it.inside())
		var want := str(e["interior"])
		if room == "" or not room.begins_with(want):
			return null
		var o: Vector3 = it.interior_origin(room)
		var loc: Array = e.get("local", [[0, -4]])
		var l: Array = loc[_rng.randi() % loc.size()]
		return o + Vector3(float(l[0]), 0.05, float(l[1]))
	if p.y < -50.0:
		return null
	if e.has("at"):
		var a := Vector3(float(e["at"][0]), 0, float(e["at"][1]))
		return a if Vector2(a.x - p.x, a.z - p.z).length() < 45.0 else null
	var best: Variant = null
	var bd := INF
	for a in db.get("anchors", []):
		var v := Vector3(float(a[0]), 0, float(a[1]))
		var d := Vector2(v.x - p.x, v.z - p.z).length()
		if d >= 12.0 and d <= 40.0 and d < bd:
			bd = d
			best = v
	return best


## Stage event `eid` near the player (or at `at`). Returns false if there is no room for it.
func stage(eid: String, at: Variant = null) -> bool:
	var e: Dictionary = db.get("events", {}).get(eid, {})
	var p := _player()
	var pop: Node = runner.population
	if e.is_empty() or p == null or pop == null:
		return false
	var anchor: Variant = at if at != null else _anchor(e, p.global_position)
	if anchor == null:
		return false
	var av: Vector3 = anchor
	fired.append(eid)
	active = {"id": eid, "actors": [], "key": "", "anchor": av, "t0": Time.get_ticks_msec() / 1000.0, "done_at": -1.0, "light": null}
	var k := 0
	for ad in e.get("actors", []):
		_serial += 1
		var aid := "ev_%s_%d_%d" % [eid, k, _serial]
		var off: Array = ad.get("at", [0, 0])
		var pos := av + Vector3(float(off[0]), 0, float(off[1]))
		var body: Node3D = pop.spawn_entry({"id": aid, "model": ad.get("model", ["figure_townsman"]), "pos": [pos.x, 0.0, pos.z],
				"facing": float(ad.get("facing", 0.0)), "behaviour": "stand", "clip": str(ad.get("clip", "idle")), "role": "event"})
		if body:
			body.add_to_group("mission")
			body.set_meta("event_barks", ad.get("barks", []))
			if body.has_method("claim"):
				body.claim()
			if ad.has("walk") and body.has_method("script_goto"):
				var w: Array = ad["walk"]
				body.script_goto(av + Vector3(float(w[0]), 0, float(w[1])), 0.0, bool(ad.get("run", false)))
			active["actors"].append(body)
			if bool(ad.get("key", false)):
				active["key"] = aid
		k += 1
	if str(active["key"]) != "":
		var rules := [{"if": ["!flag:ev_%s_done" % eid], "node": eid + "_start", "prompt": str(e.get("talk", "talk"))}, {"prompt": ""}]
		runner.add_talk(str(active["key"]), {"name": _key_name(e), "rules": rules}, e.get("dialogue", {}))
	match str(e.get("special", "")):
		"fire":
			var l := OmniLight3D.new()
			l.light_color = Color(1.0, 0.5, 0.18)
			l.light_energy = 4.0
			l.omni_range = 9.0
			l.position = av + Vector3(0, 1.4, 0)
			runner.world.add_child(l)
			active["light"] = l
			_lure(av, 45.0, 25.0, "fire")
		"flogging":
			var sl: Node = runner.world.find_child("StreetLife", true, false)
			if sl and sl.has_method("start_event"):
				sl.call("start_event", "flogging", true)
	Mission.message.emit(str(e.get("notice", "Something is happening nearby.")), 4.5)
	print("[events] %s staged at (%.0f, %.0f), %s" % [eid, av.x, av.z, GameState.time_string()])
	return true


func _key_name(e: Dictionary) -> String:
	var t := str(e.get("talk", ""))
	return t.get_slice(" ", t.get_slice_count(" ") - 1).capitalize() if t != "" else "Stranger"


func _lure(pos: Vector3, radius: float, secs: float, kind: String) -> void:
	for g in get_tree().get_nodes_in_group("guards"):
		if runner.world.is_ancestor_of(g) and (g as Node3D).global_position.distance_to(pos) < radius and g.has_method("investigate"):
			g.investigate(pos, secs, kind)


func _manage(delta: float) -> void:
	var now := Time.get_ticks_msec() / 1000.0
	var p := _player()
	_bark_t -= delta
	if _bark_t <= 0.0:
		_bark_t = _rng.randf_range(4.0, 6.5)
		var who: Array = (active["actors"] as Array).filter(func(a) -> bool: return is_instance_valid(a) and not (a.get_meta("event_barks", []) as Array).is_empty())
		if not who.is_empty() and float(active["done_at"]) < 0.0:
			var a: Node3D = who[_rng.randi() % who.size()]
			var bs: Array = a.get_meta("event_barks")
			var b: Array = bs[_rng.randi() % bs.size()]
			if a.has_method("say"):
				a.say("%s\n(%s)" % [b[0], b[1]] if b.size() > 1 else str(b[0]), 3.2)
	var light: Variant = active.get("light")
	if light != null and is_instance_valid(light):
		(light as OmniLight3D).light_energy = 3.2 + 1.4 * sin(now * 13.0) * sin(now * 5.3)
	var gone := p != null and p.global_position.distance_to(active["anchor"]) > 75.0
	var late := now - float(active["t0"]) > float(db.get("timeout", 110))
	var over := float(active["done_at"]) > 0.0 and now - float(active["done_at"]) > 10.0
	if (gone or late or over) and not runner.dialogue_open():
		clear()


## The event's actors leave (freed), its light goes out.
func clear() -> void:
	if active.is_empty():
		return
	for a in active["actors"]:
		if is_instance_valid(a):
			a.queue_free()
	var light: Variant = active.get("light")
	if light != null and is_instance_valid(light):
		(light as Node).queue_free()
	if str(active.get("key", "")) != "":
		runner.remove_talk(str(active["key"]))
	active = {}


## `ev:<id>:<outcome>` from a dialogue choice.
func resolve(eid: String, outcome: String) -> void:
	var e: Dictionary = db.get("events", {}).get(eid, {})
	var o: Dictionary = e.get("outcomes", {}).get(outcome, {})
	Mission.set_flag("ev_%s_done" % eid)
	Mission.set_flag("ev_%s_%s" % [eid, outcome])
	last_outcome = outcome
	if not active.is_empty() and str(active["id"]) == eid:
		active["done_at"] = Time.get_ticks_msec() / 1000.0
	var lines: Array = []
	if Mission.campaign:
		var eff := o.duplicate()
		var text := str(eff.get("text", ""))
		eff.erase("text")
		Mission.campaign.apply_effects(eff, lines, "silent")
		if text != "":
			Mission.campaign.record_event(eid, outcome, text + ("  (" + ", ".join(lines) + ")" if not lines.is_empty() else ""))
	var p := _player()
	var av: Vector3 = active.get("anchor", p.global_position if p else Vector3.ZERO)
	match str(e.get("special", "")) + ":" + outcome:
		"fire:slip":
			_lure(av, 60.0, 35.0, "fire")
		"procession:join":
			if p:
				p.disguised = true
				_disguise_left = 45.0
		"lamps:dark":
			var n := 0
			for l in runner.world.find_children("*", "OmniLight3D", true, false):
				var ln := l as OmniLight3D
				if ln.visible and ln.global_position.y > -50.0 and ln.global_position.distance_to(av) < 14.0:
					ln.visible = false
					n += 1
			Mission.message.emit("%d lanterns stay dark on this corner tonight." % n, 3.0)
		"snowball_urchins:hire":
			_lure(av, 40.0, 20.0, "noise")
	if eid == "runaway_cart" or eid == "brawl" or eid == "flogging_crowd":
		if runner.world.get("watch") and runner.world.watch.has_method("emit_sound"):
			runner.world.watch.emit_sound(av, 0.6, "crowd", false, false)
	print("[events] %s resolved: %s" % [eid, outcome])
