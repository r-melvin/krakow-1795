extends Node
## World side of the running mission. Created by Mission.start(id, world) under the night world and freed with
## it, so a restart (GameState.begin_night) rebuilds everything from scratch.
##
## From the mission's entry in data/missions.json it:
##  - adds or overrides NPCs (`npcs`, roster format of data/npcs.json) and extra guards (`guards`),
##  - places props (`props`: the stash) and attaches interactables to them and to every person in `talk`,
##  - plays dialogue graphs (`dialogue` nodes) chosen by `talk` rules and applies their string actions,
##  - adds mission storylines (`storylines`, storyline.gd format) and answers their `event` steps,
##  - rings the curfew bell (`curfew`).
##
## Talk rules: {npc id: {"name", "rules": [{"if": [cond...], "node": dialogue node | "action": name,
##   "prompt": text}]}} - the first rule whose conditions all hold decides the prompt and what `interact` does.
## Conditions (prefix "!" negates): approach:<name|none>, flag:<f>, before:HH:MM, after:HH:MM, carrying,
##   disguised, behind (player behind the NPC, within reach), inside (NPC is in an interior set), downed,
##   influence:<faction>>=N, coins>=N | coins>=cost, origin:<a|b>, done:<objective>.
## Dialogue node: {"lines": [[speaker, text], ...], "enter"?: action, "next"?: node,
##   "choices"?: [{"text", "action"?, "next"?, "if"?: [cond], "need"?: [cond], "why"?: text}]}
##   Speaker "$npc" is the talk name, "$you" the player. Text may use {cost}, {coins}.
##   A choice's action runs first and may redirect to another node (e.g. threaten -> success or failure).

## Campaign additions (docs/GDD.md "Campaign"):
##  - conditions also take camp:, tonight:, lever:, found:, heard:, rumour:, night:, lost:, crackdown>=, notoriety>=,
##    loyalty:<f>>=N, grievance:<f>>=N, top:<f>, skill:<name>>=N, count:<name>>=N, charmed:<npc>, grudge:<npc>
##    (scripts/mission/campaign.gd); influence: fails while that faction keeps you at arm's length.
##  - actions may be verb strings, several joined by ";": flag:x unflag:x obj:x approach:x coins:+n infl:f:n
##    loyal:f:n fear:f:n crack:n notor:n disguise:on|off carry:on|off msg:<key or text> lever:id hear:rumour
##    plant:rumour:channel found:person go:node test:<cond>|<node ok>|<node fail> story:id[:label] abort:id
##    lure:<guard name> hide:npc walk:npc:x,z follow:npc down:npc fail:<key> camp:flag count:name ev:id:outcome
##    hideitem:id showitem:id clock:+n urchin:offer enter:<door> out cp nominate:person effects:<key>
##  - `items` (props with rules like talk rules: prompt, action | node, secs), `zones` (reach a spot), `timers`
##    (clock), `on_takedown` {npc | guard:<name>: action}, `on_event` {storyline event: action}, `variants`
##    [{if, remove_guards, add_guards, flags, message}], npc `interior` (placed inside that set).
##  - the campaign's night modifiers (Campaign.night_setup), lead persons, the passage urchins as night contacts,
##    random events (scripts/mission/events.gd), the whisper network's rumours as overheard hints.
##  - failure loop: checkpoints (objective done, 20 s in a hiding spot), and on Mission.fail from the watch the
##    choice to slip away to the checkpoint, go to the cells (bribe, ransom or break out) or restart the night.
##  - tone x personality: choices with `tone` against the talk entry's `personality`/`temper` (campaign.json tones).

const EventsScript := preload("res://scripts/mission/events.gd")
const InteractableScript := preload("res://scripts/mission/interactable.gd")
const DialogueScript := preload("res://scripts/mission/dialogue.gd")
const Props := preload("res://scripts/mission/props.gd")

var data: Dictionary = {}
var world: Node3D

var population: Node
var interiors: Node
var dialogue: CanvasLayer
var stash: Node3D
var stash_ia: Area3D

var _talk: Dictionary = {}
var _nodes: Dictionary = {}
var _speaking := ""               ## npc id of the current conversation
var _choices: Array = []          ## the data dicts of the choices currently offered
var _curfew := 0                  ## 0 waiting, 1 ringing, 2 over
var _hostess_inside := false
var _hostess_in_at := -1.0        ## ticks (s) when the hostess should go in, -1 = not scheduled
var _carried_prop: Node3D
var _shut := false

var camp: Node                    ## Mission.campaign
var events: Node                  ## scripts/mission/events.gd
var setup: Dictionary = {}        ## Campaign.night_setup()
var items: Dictionary = {}        ## id -> {def, node, ia}
var _zones: Array = []
var _timers: Array = []
var _work: Dictionary = {}        ## timed item interaction {id, action, secs, t}
var _slow := 0.0
var _hints_done := false
var _checkpoint: Dictionary = {}
var _done_n := 0
var _hide_t := 0.0
var slips_left := 1
var captured := false             ## in (or out of) the cells tonight
var _cell: Node3D
var _turnkey: Node3D
var _turn_t := 0.0
var _window_warned := false
var _riot_at := -1.0
var _decoded_lead := ""
static var capture_in_smoke := false   ## the campaign smoke tests the capture loop
var stats := {"tones": 0, "personalities": {}, "branches": 0}
## Tonight's conduct for the dawn score card (Campaign.score_night): times seen, runners that reached the
## Corporal, guards downed (in the open), kills, noise, collateral, bodies found, methods and allies used.
var score := {"spotted": 0, "runners": 0, "knockouts": 0, "fights": 0, "kills": 0, "noise": 0, "collateral": 0, "bodies": 0,
		"methods": {}, "allies": {}, "coins0": 0, "clock0": 0.0, "slips": 0, "captured": false}
var _last_spot := -10.0
static var tone_stats := {"tones": 0, "personalities": {}, "branches": 0}   ## all nights (smoke)


func _ready() -> void:
	population = world.get_node_or_null("Population")
	interiors = world.get_node_or_null("Interiors")
	_talk = data.get("talk", {})
	_nodes = data.get("dialogue", {})
	dialogue = DialogueScript.new()
	dialogue.name = "Dialogue"
	add_child(dialogue)
	dialogue.choice_made.connect(_on_choice)
	dialogue.finished.connect(_on_node_finished)
	_spawn_npcs()
	_spawn_guards()
	_spawn_props()
	_attach_talk()
	for sd in data.get("storylines", []):
		if population:
			population.add_storyline(sd)
	if not bool(data.get("uses_safe_house", true)):
		var sh := world.get_node_or_null("SafeHouse") as Node3D
		if sh:
			sh.visible = false          # the cellar is only a landmark tonight: no glowing objective marker
	for id in data.get("takedown", []):
		var a := actor(str(id))
		if a:
			a.add_to_group("takedown")
	_campaign_ready()
	print("[mission] %s: %d people to talk to, stash at %s" % [data.get("title", "?"), _talk.size(),
			stash.global_position if stash else "none"])


func shutdown() -> void:
	_shut = true
	if events:
		events.clear()
	if dialogue:
		dialogue.close()


func dialogue_blocking() -> bool:
	return dialogue != null and dialogue.blocking()


func dialogue_open() -> bool:
	return dialogue != null and dialogue.is_open


func actor(id: String) -> Node3D:
	return population.actor(id) if population else null


func player() -> Player:
	for p in get_tree().get_nodes_in_group("player"):
		if world.is_ancestor_of(p):
			return p as Player
	return null


static func _vec(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))


func point(name: String) -> Vector3:
	var p: Array = data.get("points", {}).get(name, [0, 0, 0])
	return _vec(p)


# ------------------------------------------------------------------ building

func _spawn_npcs() -> void:
	if population == null:
		return
	for e in data.get("npcs", []):
		if e.has("interior") and interiors:
			var o: Vector3 = interiors.interior_origin(str(e["interior"]))
			if o == Vector3.INF:
				push_warning("Mission: no room '%s' for %s" % [e["interior"], e.get("id", "?")])
				continue
			if o != Vector3.INF:
				var e2: Dictionary = e.duplicate()
				var pp: Array = e["pos"]
				e2["pos"] = [o.x + float(pp[0]), o.y + float(pp[1]) + 0.05, o.z + float(pp[2])]
				var b: Node3D = population.spawn_entry(e2)
				if b and b.has_method("relocate"):
					b.relocate(Vector3(e2["pos"][0], e2["pos"][1], e2["pos"][2]), float(e.get("facing", 0.0)))
				continue
		population.spawn_entry(e)


func _spawn_guards() -> void:
	if not world.has_method("spawn_guard"):
		return
	for g in data.get("guards", []):
		world.spawn_guard(str(g["name"]), g["wps"], float(g.get("facing", 0.0)))


func _spawn_props() -> void:
	var sd: Dictionary = data.get("props", {}).get("stash", {})
	if sd.is_empty():
		return
	stash = Node3D.new()
	stash.name = "Stash"
	stash.position = _vec(sd["pos"])
	stash.rotation.y = float(sd.get("facing", 0.0))
	world.add_child(stash)
	var b := Props.bundle()
	b.name = "BundleMesh"
	stash.add_child(b)
	# sacking thrown over half of it, and a broken barrel beside
	var sack := MeshInstance3D.new()
	var sm := BoxMesh.new()
	sm.size = Vector3(0.62, 0.05, 0.5)
	sack.mesh = sm
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.3, 0.25, 0.18)
	mat.roughness = 1.0
	sack.material_override = mat
	sack.position = Vector3(0.12, 0.3, 0.02)
	sack.rotation = Vector3(0.05, 0.3, -0.12)
	stash.add_child(sack)
	Assets.place(stash, "barrel", Vector3(0.1, 0, -0.75), 0.4)
	stash_ia = InteractableScript.new()
	stash_ia.name = "StashInteract"
	stash_ia.display_name = str(sd.get("name", "Sacking"))
	stash_ia.marker_height = 0.9
	stash_ia.highlight_root = b
	stash_ia.prompt_func = _stash_prompt
	stash_ia.handler = _take_stash
	stash.add_child(stash_ia)


func _attach_talk() -> void:
	for id in _talk:
		var npc := actor(id)
		if npc == null:
			push_warning("Mission: no NPC '%s' to talk to" % id)
			continue
		var ia := InteractableScript.new()
		ia.name = "Talk"
		ia.display_name = str(_talk[id].get("name", id))
		ia.marker_height = 2.02
		ia.highlight_root = npc
		ia.prompt_func = _talk_prompt.bind(id)
		ia.handler = _on_talk.bind(id)
		npc.add_child(ia)


# ------------------------------------------------------------------ per frame

func _physics_process(_delta: float) -> void:
	if _shut or not Mission.is_active():
		return
	_curfew_tick()
	_campaign_tick(_delta)
	var p := player()
	# The hostess waits at the Town Hall door until the bundle is on its way, then goes in to her guests.
	if not _hostess_inside and p:
		var h := actor("hostess")
		var now := Time.get_ticks_msec() / 1000.0
		if h and _hostess_in_at >= 0.0 and now >= _hostess_in_at and not dialogue.blocking():
			_hostess_go_in()
		elif h and p.carrying and _hostess_in_at < 0.0 and h.global_position.distance_to(p.global_position) > 8.0:
			_hostess_go_in()


func _curfew_tick() -> void:
	var cf: Dictionary = data.get("curfew", {})
	if cf.is_empty() or _curfew >= 2:
		return
	var at := GameState.parse_clock(str(cf.get("at", "22:00")))
	var clock := GameState.clock_minutes
	if _curfew == 0 and clock >= at:
		_curfew = 1
		for g in get_tree().get_nodes_in_group("guards"):
			if world.is_ancestor_of(g):
				g.set_view_mult(float(cf.get("view_mult", 2.0)))
		Mission.announcement.emit(str(cf.get("text", "The curfew bell.")), 6.0)
		print("[mission] curfew bell at %s" % GameState.time_string())
	elif _curfew == 1 and clock >= at + float(cf.get("minutes", 3.0)):
		_curfew = 2
		for g in get_tree().get_nodes_in_group("guards"):
			if world.is_ancestor_of(g):
				g.set_view_mult(1.0)
		Mission.message.emit(str(cf.get("end_text", "The bell falls silent.")), 4.0)


# ------------------------------------------------------------------ conditions

func _cond_all(conds: Array, id: String) -> bool:
	for c in conds:
		if not _cond(str(c), id):
			return false
	return true


func _cond(c: String, id: String) -> bool:
	var neg := c.begins_with("!")
	if neg:
		c = c.substr(1)
	return _cond_raw(c, id) != neg


func _cond_raw(c: String, id: String) -> bool:
	if "|" in c and camp != null and not c.begins_with("approach:"):
		return camp.cond(c)
	var key := c.get_slice(":", 0)
	var arg := c.substr(key.length() + 1) if ":" in c else ""
	var p := player()
	var npc := actor(id)
	match key:
		"approach":
			return Mission.approach == ("" if arg == "none" else arg)
		"flag":
			return Mission.has_flag(arg)
		"done":
			return Mission.is_done(arg)
		"before":
			return GameState.clock_minutes < GameState.parse_clock(arg)
		"after":
			return GameState.clock_minutes >= GameState.parse_clock(arg)
		"carrying":
			return p != null and p.carrying
		"disguised":
			return p != null and p.disguised
		"inside":
			return npc != null and npc.global_position.y < -100.0
		"downed":
			return npc != null and npc.has_method("is_downed") and npc.is_downed()
		"behind":
			return p != null and npc != null and _behind(npc, p)
		"origin":
			return GameState.origin_id in arg.split("|")
		"gender":                        # gender:f  gender:m
			return GameState.gender in arg.split("|")
		"inclination":                   # inclination:men|both  ("unspoken" never satisfies)
			return GameState.inclination != "unspoken" and GameState.inclination in arg.split("|")
		"influence":
			var parts := arg.split(">=")
			if camp and camp.arms_length(parts[0]) != "":
				return false
			return GameState.get_influence(parts[0]) >= int(parts[1])
		"skill":
			var sp := arg.split(">=")
			return GameState.skill(sp[0]) >= int(sp[1])
		"count":
			var cp := arg.split(">=")
			return int(Mission.flags.get("count_" + cp[0], 0)) >= int(cp[1])
		"charmed", "grudge":
			return camp != null and camp.flag("%s_%s" % [key, arg])
		"camp", "tonight", "lever", "found", "heard", "rumour", "night", "lost", "played", "loyalty", "grievance", "top":
			return camp != null and camp.cond(c)
		"coins>=cost":
			return GameState.coins >= urchin_cost()
	if c.begins_with("coins>="):
		return GameState.coins >= int(c.trim_prefix("coins>="))
	if camp and (c.begins_with("crackdown>=") or c.begins_with("notoriety>=") or c.begins_with("loyal_count>=") or c.begins_with("night>=") or "|" in c):
		return camp.cond(c)
	push_warning("Mission: unknown condition '%s'" % c)
	return false


## Player behind the NPC (outside a 140 degree front arc) and within interact reach: he does not see them.
func _behind(npc: Node3D, p: Node3D) -> bool:
	var to := p.global_position - npc.global_position
	to.y = 0.0
	if to.length() > 2.6:
		return false
	var fwd := -npc.global_transform.basis.z
	fwd.y = 0.0
	return rad_to_deg(fwd.angle_to(to)) > 110.0


func urchin_cost() -> int:
	var c: Dictionary = data.get("urchin_cost", {"normal": 5, "street": 2, "street_min": 30})
	return int(c["street"]) if GameState.get_influence("street") >= int(c["street_min"]) else int(c["normal"])


func _fmt(t: String) -> String:
	return t.replace("{cost}", str(urchin_cost())).replace("{coins}", str(GameState.coins))


# ------------------------------------------------------------------ talking

func _rule(id: String) -> Dictionary:
	for r in _talk.get(id, {}).get("rules", []):
		if _cond_all(r.get("if", []), id):
			return r
	return {}


func _talk_prompt(id: String) -> String:
	var r := _rule(id)
	if r.is_empty():
		return ""
	return _fmt(str(r.get("prompt", "talk to %s" % _talk[id].get("name", id))))


func _on_talk(_actor: Node, id: String) -> bool:
	var r := _rule(id)
	if r.is_empty():
		return false
	if r.has("action"):
		var nxt := _act(str(r["action"]), id)
		if nxt != "":
			play(id, nxt)
		return true
	play(id, str(r.get("node", "")))
	return true


## Open (or continue) the conversation with `id` at dialogue node `node_name`.
func play(id: String, node_name: String) -> void:
	var node: Dictionary = _nodes.get(node_name, {})
	if node.is_empty():
		push_warning("Mission: no dialogue node '%s'" % node_name)
		dialogue.close()
		return
	_speaking = id
	if node.has("enter"):
		var redirect := _act(str(node["enter"]), id)
		if redirect != "":
			play(id, redirect)
			return
	if _shut:
		return
	var who := str(_talk.get(id, {}).get("name", id))
	var lines: Array = []
	var pers := str(_talk.get(id, {}).get("personality", ""))
	var src: Array = node.get("lines", [])
	if node.has("lines_by") and (node["lines_by"] as Dictionary).has(pers):
		src = node["lines_by"][pers]
	var pre: Array = get_meta("pre_lines", []) if has_meta("pre_lines") else []
	if not pre.is_empty():
		remove_meta("pre_lines")
		src = pre + src
	for l in src:
		var sp := str(l[0]).replace("$npc", who).replace("$you", "You")
		lines.append([sp, _fmt(str(l[1]))])
	_choices = []
	var shown: Array = []
	for c in node.get("choices", []):
		if not _cond_all(c.get("if", []), id):
			continue
		var ok := _cond_all(c.get("need", []), id)
		_choices.append(c)
		var why := str(c.get("why", ""))
		if not ok and why == "":
			why = _period_why(c.get("need", []), id)
		shown.append({"text": _fmt(str(c.get("text", "..."))), "enabled": ok, "why": why if why != "" else "not possible"})
	dialogue.set_meta("node", node_name)
	dialogue.show_node(lines, shown)


## Period phrasing for a greyed choice whose `need` failed on who the player is.
func _period_why(needs: Array, id: String) -> String:
	for n in needs:
		var c := str(n)
		if _cond(c, id):
			continue
		var key := c.trim_prefix("!").get_slice(":", 0)
		match key:
			"gender":
				return "Not for a woman here." if GameState.gender == "f" else "Not for a man here."
			"inclination":
				return "Not your inclination."
			"origin":
				return "Not for someone of your station."
			"influence":
				var fid := c.trim_prefix("!").get_slice(":", 1).get_slice(">=", 0)
				if camp and camp.arms_length(fid) != "":
					return "They keep you at arm's length: you are too close to the %s." % camp.fname(camp.arms_length(fid))
				return "You are not known enough here."
			"lever", "found":
				return "You would need something you do not have."
			"loyalty":
				return "They do not trust you enough."
			"skill":
				return "Beyond your skill."
			"coins>=cost":
				return "Not enough coin."
	return ""


func _on_choice(i: int) -> void:
	if i < 0 or i >= _choices.size():
		return
	var c: Dictionary = _choices[i]
	var nxt := str(c.get("next", ""))
	if c.has("tone"):
		var r := _tone_reaction(str(c["tone"]), _speaking)
		if r == "good" and c.has("on_good"):
			nxt = str(c["on_good"])
		elif r == "bad":
			if c.has("on_bad"):
				nxt = str(c["on_bad"])
			elif float(_talk.get(_speaking, {}).get("temper", 0.3)) >= 0.6:
				_thrown_out(_speaking)
				return
	if c.has("action"):
		var redirect := _act(str(c["action"]), _speaking)
		if redirect != "":
			nxt = redirect
	if nxt != "" and not _shut:
		play(_speaking, nxt)
	else:
		dialogue.close()


func _on_node_finished() -> void:
	var node: Dictionary = _nodes.get(str(dialogue.get_meta("node", "")), {})
	if node.has("next") and not _shut:
		play(_speaking, str(node["next"]))


## Smoke/test helper: the index of the offered choice with this action or next node, or -1.
func choice_index(action_or_next: String) -> int:
	for k in _choices.size():
		var c: Dictionary = _choices[k]
		if str(c.get("id", "")) == action_or_next or str(c.get("action", "")) == action_or_next or str(c.get("next", "")) == action_or_next:
			return k
	return -1


# ------------------------------------------------------------------ actions

## Dialogue and talk-rule actions. Returns a dialogue node to jump to, or "".
func _act(action: String, id: String) -> String:
	if ":" in action or ";" in action or action in ["out", "cp", "slip", "cells", "restart", "mob", "frisk_ok"]:
		return _verbs(action, id)
	var p := player()
	match action:
		"leave":
			return ""
		"meet_smuggler":
			Mission.set_flag("know_stash")
			Mission.set_approach("underworld")
			Mission.complete_objective("meet_smuggler")
		"pay":
			GameState.coins -= urchin_cost()
			Mission.set_flag("paid_urchins")
			_hire_urchins()
		"promise":
			Mission.set_flag("owe_urchins")
			_hire_urchins()
		"threaten":
			if GameState.get_influence("street") >= int(data.get("threaten_street_min", 30)):
				Mission.set_flag("threatened_urchins")
				_hire_urchins()
				return "urchins_threat_ok"
			Mission.set_flag("urchins_scattered")
			_scatter_urchins()
			_tip_informer()
			return "urchins_threat_fail"
		"persuade":
			_win_hostess()
		"refused":
			Mission.set_flag("hostess_refused")
		"hostess_in":
			_hostess_in_at = Time.get_ticks_msec() / 1000.0 + 0.6
		"collect_bundle":
			if _carried_prop:
				_carried_prop.queue_free()
				_carried_prop = null
			if p:
				p.carrying = true
			Mission.set_flag("bundle_collected")
			Mission.complete_objective("collect_bundle")
		"deliver":
			if p:
				p.carrying = false
			Mission.set_flag("delivered")
			dialogue.close()
			Mission.complete_objective("deliver")
		"plant_decoy":
			Mission.set_flag("decoy_planted")
			Mission.message.emit(str(data.get("decoy_text", "You slip a false pamphlet into his pocket.")), 4.0)
			Mission.complete_objective("decoy_informer")
			# He finds it soon enough and runs to the corporal with it.
			var s: Node = population.storyline("informer") if population else null
			if s and s.status == 0:
				s.start_at("report")
		"bribe_informer":
			GameState.coins -= int(data.get("informer_bribe", 3))
			Mission.set_flag("informer_bribed")
			_abort_story("informer")
		"lie_informer":
			if p and p.carrying:
				_tip_informer()
				return "informer_lie_fail"
			Mission.set_flag("informer_fooled")
			_abort_story("informer")
		_:
			push_warning("Mission: unknown action '%s'" % action)
	return ""


func _hire_urchins() -> void:
	Mission.set_approach("street")
	Mission.set_flag("urchins_hired")    # starts the urchin_run storyline
	Mission.complete_objective("hire_urchins")


func _scatter_urchins() -> void:
	var dests := [point("scatter_a"), point("scatter_b")]
	var k := 0
	for id in ["urchin_a", "urchin_b"]:
		var u := actor(id)
		if u and u.has_method("claim"):
			u.claim()
			u.script_goto(dests[k], 0.0, true)
			u.say(["Run!", "Scarper!"][k], 2.0)
		k += 1


## The informer hears of you: his storyline fires at once, wherever you are.
func _tip_informer() -> void:
	if population == null:
		return
	var s: Node = population.storyline("informer")
	if s and s.status == 0:
		var trig: Dictionary = s.data.get("trigger", {})
		trig["radius"] = 60.0
		trig.erase("cone")
	Mission.message.emit("Word of you will reach the informer.", 3.0)


func _abort_story(sid: String) -> void:
	if population:
		var s: Node = population.storyline(sid)
		if s:
			s.abort()


func _win_hostess() -> void:
	Mission.set_approach("salon")
	Mission.set_flag("know_stash")
	Mission.set_flag("invited")
	var p := player()
	if p:
		p.disguised = true
	Mission.complete_objective("win_hostess")
	_hostess_in_at = Time.get_ticks_msec() / 1000.0 + 1.5


func _hostess_go_in() -> void:
	var h := actor("hostess")
	_hostess_inside = true
	_hostess_in_at = -1.0
	if h == null or interiors == null or not h.has_method("relocate"):
		return
	var origin: Vector3 = interiors.interior_origin(str(data.get("salon_set", "int_salon")))
	if origin == Vector3.INF:
		return
	h.relocate(origin + point("hostess_inside") + Vector3(0, 0.05, 0), float(data.get("hostess_inside_facing", PI)))
	print("[mission] the hostess goes in to her guests at %s" % GameState.time_string())


func _stash_prompt() -> String:
	if stash == null or not stash.visible:
		return ""
	return "take the printer's bundle" if Mission.has_flag("know_stash") else "search the sacking"


func _take_stash(_actor: Node) -> bool:
	if not Mission.has_flag("know_stash"):
		Mission.message.emit(str(data.get("stash_unknown_text", "Old sacking. Nothing here for you.")), 3.5)
		return true
	stash.visible = false
	stash_ia.enabled = false
	var p := player()
	if p:
		p.carrying = true
	Mission.set_flag("bundle_taken")
	Mission.message.emit(str(data.get("stash_taken_text", "You shoulder the bundle.")), 4.0)
	Mission.complete_objective("take_bundle")
	return true


# ------------------------------------------------------------------ storylines and takedowns

func on_story_event(_story: String, ev: String, who: Node) -> void:
	match ev:
		"urchin_took_bundle":
			if stash:
				stash.visible = false
				stash_ia.enabled = false
			if who is Node3D:
				_carried_prop = Props.bundle()
				_carried_prop.position = Vector3(0, 0.8, -0.28)
				_carried_prop.scale = Vector3.ONE * 0.75
				(who as Node3D).add_child(_carried_prop)
			Mission.set_flag("urchin_has_bundle")
		"bundle_at_well":
			Mission.set_flag("bundle_at_well")
			Mission.message.emit(str(data.get("handoff_text", "The bundle waits for you at the well.")), 4.0)
		_:
			var oe: Dictionary = data.get("on_event", {})
			if ev.begins_with("at_"):
				for k in Mission.flags.keys():
					if str(k).begins_with("at_"):
						Mission.flags.erase(k)
				Mission.set_flag(ev)
			if oe.has(ev):
				var h: Variant = oe[ev]
				if h is Array:
					for e in h:
						if _cond_all(e.get("if", []), ""):
							_act(str(e.get("action", "")), "")
							break
				else:
					_act(str(h), "")


func on_takedown(target: Node, in_fight: bool) -> void:
	var ot: Dictionary = data.get("on_takedown", {})
	for k in ot:
		var ks := str(k)
		if (ks.begins_with("guard:") and target is Guard and target.guard_name == ks.trim_prefix("guard:")) or target == actor(ks):
			_act(str(ot[k]), ks)
	if target == actor("informer"):
		Mission.set_flag("informer_downed")
		_abort_story("informer")
		Mission.message.emit("The informer sleeps in the snow. He will wake with a sore head and no story.", 4.0)
	elif target is Guard:
		if in_fight:
			Mission.message.emit("%s is down. The Austrians will make the city pay for that." % target.guard_name, 4.0)
		else:
			Mission.message.emit("%s slumps without a sound." % target.guard_name, 3.0)


# ================================================================== campaign (docs/GDD.md "Campaign")

func cond_list(conds: Array) -> bool:
	return _cond_all(conds, _speaking)


func _campaign_ready() -> void:
	camp = Mission.campaign
	var p := player()
	setup = camp.night_setup() if camp and not GameState.campaign.is_empty() else {}
	var msgs: Array = setup.get("messages", []).duplicate()
	# variants of this mission chosen by the campaign's state
	var remove: Array = setup.get("remove_guards", []).duplicate()
	var add: Array = setup.get("add_guards", []).duplicate()
	for v in data.get("variants", []):
		if not _cond_all(v.get("if", []), ""):
			continue
		remove.append_array(v.get("remove_guards", []))
		add.append_array(v.get("add_guards", []))
		for f in v.get("flags", []):
			Mission.set_flag(str(f))
		if str(v.get("message", "")) != "":
			msgs.append(str(v["message"]))
	for g in get_tree().get_nodes_in_group("guards"):
		if world.is_ancestor_of(g) and g.guard_name in remove:
			g.remove_from_group("guards")
			g.queue_free()
	for gd in add:
		if world.has_method("spawn_guard"):
			world.spawn_guard(str(gd["name"]), gd["wps"], float(gd.get("facing", 0.0)))
	var vm := float(setup.get("view_mult", 1.0))
	if not is_equal_approx(vm, 1.0):
		for g in get_tree().get_nodes_in_group("guards"):
			if world.is_ancestor_of(g):
				g.sight_modifiers.append(func(_g: Node, _p: Node) -> float: return vm)
	if p and int(setup.get("health", -1)) > 0:
		p.health = int(setup["health"])
	for id in setup.get("hide_npcs", []):
		var a := actor(str(id))
		if a and a.has_method("relocate"):
			a.relocate(Vector3(0, -300, 0), 0.0)
			a.visible = false
	slips_left = int(setup.get("slips", 1))
	for sb in setup.get("sabotage", []):
		msgs.append(str(sb["text"]))
		Mission.set_flag("betrayed_" + str(sb["faction"]))
		match str(sb["kind"]):
			"patrol":
				var at := _first_mark()
				add_guard_near(at, "Tipped-off patrol")
			"riot":
				_riot_at = GameState.clock_minutes + 12.0
			"toll":
				GameState.coins = maxi(GameState.coins - 3, 0)
			"tongue":
				GameState.add_notoriety(15.0)
	_merge_side_quest()
	_spawn_items()
	_zones = data.get("zones", []).duplicate(true)
	_timers = data.get("timers", []).duplicate(true)
	_spawn_people()
	_urchin_contacts()
	score["coins0"] = GameState.coins
	score["clock0"] = GameState.clock_minutes
	var wt: Variant = world.get("watch")
	if wt:
		if wt.has_signal("player_spotted"):
			wt.player_spotted.connect(func(_g: Node, _p: Vector3) -> void:
				var now := Time.get_ticks_msec() / 1000.0
				if now - _last_spot > 4.0:
					score["spotted"] = int(score["spotted"]) + 1
				_last_spot = now)
		if wt.has_signal("runner_arrived"):
			wt.runner_arrived.connect(func(_g: Node) -> void: score["runners"] = int(score["runners"]) + 1)
		if wt.has_signal("guard_downed"):
			wt.guard_downed.connect(func(_g: Node, in_fight: bool, _w: Node) -> void:
				score["knockouts"] = int(score["knockouts"]) + 1
				if in_fight:
					score["fights"] = int(score["fights"]) + 1)
		if wt.has_signal("body_found"):
			wt.body_found.connect(func(_b: Node, _f: Node) -> void: score["bodies"] = int(score["bodies"]) + 1)
	_kingpin_setup()
	events = EventsScript.new()
	events.name = "Events"
	events.runner = self
	add_child(events)
	Mission.objectives_changed.connect(_on_objectives_changed)
	Mission.approach_changed.connect(func(_a: String) -> void: _readd_lead_objectives())
	if world.get("watch") and world.watch.has_signal("hiding_changed"):
		world.watch.hiding_changed.connect(func(_s: Node, occ: bool) -> void: _hide_t = 0.0 if occ else -1.0)
	_hide_t = -1.0
	if p:
		save_checkpoint("the start of the night")
	if not msgs.is_empty():
		get_tree().create_timer(2.5, false).timeout.connect(func() -> void:
			if not _shut:
				Mission.message.emit("\n".join(msgs), 6.0))


func _first_mark() -> Vector3:
	var marks: Dictionary = data.get("stealth", {}).get("map_marks", {})
	for o in Mission.objectives:
		if o.get("optional", false) or o["done"]:
			continue
		var m: Variant = marks.get(o["id"], null)
		if m is Array:
			return Vector3(float(m[0]), 0, float(m[1]))
		if m is String and str(m).begins_with("actor:"):
			var a := actor(str(m).trim_prefix("actor:"))
			if a:
				return a.global_position
	return Vector3.ZERO


func add_guard_near(at: Vector3, gname: String) -> void:
	if not world.has_method("spawn_guard") or at.y < -50.0:
		return
	var wps := [[at.x - 6.0, 0, at.z - 4.0], [at.x + 6.0, 0, at.z - 4.0], [at.x + 6.0, 0, at.z + 4.0], [at.x - 6.0, 0, at.z + 4.0]]
	world.spawn_guard(gname, wps, 0.0)


func _campaign_tick(delta: float) -> void:
	if _work.size() > 0:
		_work_tick(delta)
	if _hide_t >= 0.0:
		var p0 := player()
		if p0 and p0.get("hidden_spot"):
			_hide_t += delta
			if _hide_t >= 20.0:
				_hide_t = -1.0
				save_checkpoint("a hiding place")
	if _cell and is_instance_valid(_turnkey):
		_turnkey_tick(delta)
	_kingpin_tick(delta)
	_slow += delta
	if _slow < 0.25:
		return
	_slow = 0.0
	var p := player()
	if p == null:
		return
	if not _hints_done:
		_inject_hints()
	elif camp:
		var intel := _intel()
		if intel:
			camp.rumours.poll_heard(intel.store().get("hints", {}))
	var pos := p.global_position
	for z in _zones:
		if bool(z.get("_fired", false)):
			continue
		var zp := _vec(z["pos"])
		if z.has("interior") and interiors:
			zp += interiors.interior_origin(str(z["interior"]))
		if pos.distance_to(zp) <= float(z.get("radius", 2.5)) and _cond_all(z.get("if", []), ""):
			if bool(z.get("once", true)):
				z["_fired"] = true
			_act(str(z.get("action", "")), "")
	for t in _timers:
		if bool(t.get("_fired", false)):
			continue
		if GameState.clock_minutes >= GameState.parse_clock(str(t["at"])) and _cond_all(t.get("if", []), ""):
			t["_fired"] = true
			_act(str(t.get("action", "")), "")
	if _riot_at > 0.0 and GameState.clock_minutes >= _riot_at:
		_riot_at = -1.0
		Mission.announcement.emit("A mob you did not call is shouting in the square. The watch is running towards you.", 5.0)
		for g in get_tree().get_nodes_in_group("guards"):
			if world.is_ancestor_of(g) and (g as Node3D).global_position.distance_to(pos) < 45.0 and g.has_method("investigate"):
				g.investigate(pos, 20.0, "noise")


# ------------------------------------------------------------------ verbs

func _verbs(action: String, id: String) -> String:
	var redirect := ""
	for v in action.split(";", false):
		var r := _verb(str(v).strip_edges(), id)
		if r != "":
			redirect = r
		if _shut:
			break
	return redirect


func _num(s: String) -> int:
	return int(s.trim_prefix("+"))


func _verb(v: String, id: String) -> String:
	var key := v.get_slice(":", 0)
	var arg := v.substr(key.length() + 1) if ":" in v else ""
	_score_verb(key, arg)
	var p := player()
	var lines: Array = []
	match key:
		"leave":
			pass
		"flag":
			Mission.set_flag(arg)
		"unflag":
			Mission.flags.erase(arg)
		"obj":
			Mission.complete_objective(arg)
		"approach":
			Mission.set_approach(arg)
		"coins":
			GameState.coins = maxi(GameState.coins + _num(arg), 0)
		"infl":
			GameState.add_influence(arg.get_slice(":", 0), _num(arg.get_slice(":", 1)))
		"loyal":
			GameState.add_loyalty(arg.get_slice(":", 0), _num(arg.get_slice(":", 1)))
		"fear":
			GameState.add_fear(arg.get_slice(":", 0), _num(arg.get_slice(":", 1)))
		"crack":
			GameState.crackdown = clampi(GameState.crackdown + _num(arg), 0, 100)
		"notor":
			GameState.add_notoriety(float(_num(arg)))
		"disguise":
			if p:
				p.disguised = arg == "on"
		"carry":
			if p:
				p.carrying = arg == "on"
		"msg":
			Mission.message.emit(_fmt(str(data.get("texts", {}).get(arg, arg))), 4.0)
		"lever":
			if camp:
				camp.gain_lever(arg, str(data.get("title", "")), lines)
		"hear":
			if camp:
				camp.rumours.seed_rumour(arg)
				camp.rumours.hear(arg, "told by %s" % _talk.get(id, {}).get("name", "someone"))
				Mission.message.emit("Rumour noted: " + str(camp.rumours.def(arg).get("subject", arg)), 3.0)
		"plant":
			if camp:
				camp.plant(arg.get_slice(":", 0), arg.get_slice(":", 1), true)
		"found":
			if camp:
				camp.find_person(arg, lines, actor(arg))
		"go":
			return arg
		"test":
			var parts := arg.split("|")
			if parts.size() >= 3:
				return parts[1] if _cond(parts[0], id) else parts[2]
		"story":
			var s: Node = population.storyline(arg.get_slice(":", 0)) if population else null
			if s:
				s.start_at(arg.get_slice(":", 1) if ":" in arg else "")
		"abort":
			_abort_story(arg)
		"lure":
			var src := actor(id)
			var at: Vector3 = src.global_position if src else (p.global_position if p else Vector3.ZERO)
			for g in get_tree().get_nodes_in_group("guards"):
				if world.is_ancestor_of(g) and g.guard_name == arg and g.has_method("investigate"):
					g.investigate(at, 25.0, "noise")
		"hide":
			var a := actor(arg)
			if a and a.has_method("relocate"):
				a.relocate(Vector3(0, -300, 0), 0.0)
				a.visible = false
		"walk":
			var a2 := actor(arg.get_slice(":", 0))
			var xz := arg.get_slice(":", 1).split(",")
			if a2 and a2.has_method("script_goto") and xz.size() >= 2:
				a2.claim()
				a2.script_goto(Vector3(float(xz[0]), 0, float(xz[1])), 0.0, false)
		"follow":
			var a3 := actor(arg)
			if a3 and a3.has_method("script_goto") and p:
				a3.claim()
				a3.script_goto(p, 1.6, false)
		"down":
			var a4 := actor(arg)
			if a4 and a4.has_method("knock_down"):
				a4.knock_down(60.0)
		"fail":
			captured = true
			Mission.fail(str(data.get("texts", {}).get(arg, arg)))
		"camp":
			if camp:
				camp.set_flag(arg)
		"count":
			Mission.flags["count_" + arg] = int(Mission.flags.get("count_" + arg, 0)) + 1
		"ev":
			if events:
				events.resolve(arg.get_slice(":", 0), arg.get_slice(":", 1))
		"hideitem":
			_item_visible(arg, false)
		"showitem":
			_item_visible(arg, true)
		"clock":
			GameState.clock_minutes += float(_num(arg))
		"urchin":
			if camp:
				var said: String = camp.urchin_buy(arg, true)
				if said == "":
					return "urchin_broke"
				if arg == "window":
					slips_left += 1
				set_meta("pre_lines", [["$npc", said]])
				return "urchin_told"
		"enter":
			if interiors and p:
				interiors.enter_now(p, arg)
		"out":
			if interiors and p and interiors.has_method("_go_out_now"):
				interiors.call("_go_out_now", p)
		"cp":
			save_checkpoint("a safe moment")
		"nominate":
			if camp:
				camp.nominate(arg, true)
		"effects":
			if camp:
				camp.apply_effects(data.get("effects", {}).get(arg, {}), lines)
		"send":
			var gn := arg.get_slice(":", 0)
			var sxz := arg.get_slice(":", 1).split(",")
			for g in get_tree().get_nodes_in_group("guards"):
				if world.is_ancestor_of(g) and g.guard_name == gn and g.has_method("investigate") and sxz.size() >= 2:
					g.investigate(Vector3(float(sxz[0]), 0, float(sxz[1])), 90.0, "noise")
		"dismiss":
			for g in get_tree().get_nodes_in_group("guards"):
				if world.is_ancestor_of(g) and g.guard_name == arg:
					g.remove_from_group("guards")
					g.queue_free()
		"kill":
			return _kill(arg)
		"fire":
			var fxz := arg.split(",")
			if fxz.size() >= 2:
				var fp := Vector3(float(fxz[0]), 0, float(fxz[1]))
				var l := OmniLight3D.new()
				l.light_color = Color(1.0, 0.45, 0.15)
				l.light_energy = 6.0
				l.omni_range = 14.0
				world.add_child(l)
				l.global_position = fp + Vector3(0, 2.0, 0)
				for g in get_tree().get_nodes_in_group("guards"):
					if world.is_ancestor_of(g) and (g as Node3D).global_position.distance_to(fp) < 50.0 and g.has_method("investigate"):
						g.investigate(fp, 40.0, "fire")
				Mission.announcement.emit("Fire! Straw, sacks, then the doors: the warehouse is burning.", 4.0)
		"mob":
			_mob_start()
		"frisk_ok":
			Mission.set_flag("frisk_ok")
		"below":
			var ents: Dictionary = camp.db.get("undercroft", {}).get("entrances", {}) if camp else {}
			var door := str(ents.get(arg, arg))
			if interiors == null or p == null or not interiors.enter_now(p, door):
				Mission.message.emit(str(data.get("texts", {}).get("below_missing", "The grate will not budge.")), 3.5)
			else:
				Mission.set_flag("below")
				score["methods"]["the drains"] = true
		"slip":
			_slip_away()
		"cells":
			_to_cells()
		"restart":
			dialogue.close()
			GameState.begin_night.call_deferred()
		"cell":
			return _cell_out(arg)
		_:
			push_warning("Mission: unknown verb '%s'" % v)
	if not lines.is_empty() and Mission.is_active():
		Mission.message.emit(" ".join(lines), 4.0)
	return ""


# ------------------------------------------------------------------ talk added at night (people, urchins, events)

## Attach a talk entry (runner talk format) to population actor `id`, with extra dialogue nodes.
func add_talk(id: String, def: Dictionary, nodes: Dictionary = {}) -> void:
	for k in nodes:
		_nodes[k] = nodes[k]
	_talk[id] = def
	var npc := actor(id)
	if npc == null or npc.get_node_or_null("Talk"):
		return
	var ia := InteractableScript.new()
	ia.name = "Talk"
	ia.display_name = str(def.get("name", id))
	ia.marker_height = 2.02
	ia.highlight_root = npc
	ia.prompt_func = _talk_prompt.bind(id)
	ia.handler = _on_talk.bind(id)
	npc.add_child(ia)


func remove_talk(id: String) -> void:
	_talk.erase(id)


func _spawn_people() -> void:
	if camp == null or population == null or GameState.campaign.is_empty():
		return
	for e in camp.night_people():
		var pid := str(e["id"])
		if actor(pid) != null or _talk.has(pid):
			continue
		var pd: Dictionary = e["def"]
		var pos: Array = e["pos"]
		var body: Node3D = population.spawn_entry({"id": pid, "model": pd.get("model", ["figure_townsman"]), "pos": pos,
				"facing": float(pd.get("facing", 0.0)), "behaviour": "stand", "clip": "idle", "role": str(pd.get("role", ""))})
		if body == null:
			continue
		body.add_to_group("mission")
		if body.has_method("claim"):
			body.claim()
		var node := {"lines": pd.get("lines", []), "enter": "found:%s;obj:find_%s" % [pid, pid]}
		add_talk(pid, {"name": str(pd.get("name", pid)), "personality": str(pd.get("personality", "")),
				"temper": float(pd.get("temper", 0.3)), "rules": [{"node": "person_" + pid, "prompt": "talk to %s" % pd.get("name", pid)}]},
				{"person_" + pid: node})
		var marks: Dictionary = data.get("stealth", {}).get("map_marks", {})
		marks["find_" + pid] = "actor:" + pid
		if not data.has("stealth"):
			data["stealth"] = {"map_marks": marks}
		else:
			data["stealth"]["map_marks"] = marks
		var lo := {"id": "find_" + pid, "text": "Find %s (%s)" % [pd.get("name", pid), pd.get("where", "")], "done": false, "optional": true}
		set_meta("lead_" + pid, lo)
		Mission.objectives.append(lo.duplicate())
		print("[mission] lead: %s at %s" % [pid, pos])
	Mission.objectives_changed.emit()


func _readd_lead_objectives() -> void:
	for m in get_meta_list():
		if str(m).begins_with("lead_"):
			var lo: Dictionary = get_meta(m)
			if not Mission.has_objective(lo["id"]):
				var o := lo.duplicate()
				o["done"] = camp != null and camp.found(str(m).trim_prefix("lead_"))
				Mission.objectives.append(o)
	Mission.objectives_changed.emit()


## Staś and Kasia sell news at night on the nights their own mission does not need them.
func _urchin_contacts() -> void:
	if camp == null or GameState.campaign.is_empty():
		return
	var nodes := {
		"urchin_news": {"lines": [["$npc", "A grosz for news, mister? We know everything. Some of it's even true."]],
			"choices": [
				{"text": "What's the talk in the passage? (1 zł)", "action": "urchin:rumour", "need": ["coins>=1"], "tone": "bribe"},
				{"text": "Any window unlatched tonight? (1 zł)", "action": "urchin:window", "need": ["coins>=1"]},
				{"text": "You'll make a fine informer one day.", "tone": "joke", "next": "urchin_joke", "on_bad": "urchin_sulk"},
				{"text": "Not tonight.", "action": "leave"}]},
		"urchin_told": {"lines": [["$npc", "Pleasure doing business."]]},
		"urchin_broke": {"lines": [["$npc", "No coin, no news. We're not the Church."]]},
		"urchin_joke": {"lines": [["$npc", "Informer! We'd starve. The Austrians pay in promises and the Corporal keeps the promises."]]},
		"urchin_sulk": {"lines": [["$npc", "Charming. Go and ask the informer yourself, then."]]}}
	for id in ["urchin_a", "urchin_b"]:
		if _talk.has(id) or actor(id) == null:
			continue
		add_talk(id, {"name": "Staś" if id == "urchin_a" else "Kasia", "personality": "wry", "temper": 0.2,
				"rules": [{"node": "urchin_news", "prompt": "buy news from the urchin"}]}, nodes)


# ------------------------------------------------------------------ rumours as overheard hints

func _intel() -> Node:
	for n in get_tree().get_nodes_in_group("stealth_intel"):
		if world.is_ancestor_of(n):
			return n
	return null


func _inject_hints() -> void:
	_hints_done = true
	var intel := _intel()
	if intel == null or camp == null or GameState.campaign.is_empty():
		return
	var n := 0
	for h in camp.rumours.night_hints():
		var hid := str(h["id"])
		if intel.hints.has(hid):
			continue
		intel.hints[hid] = h
		for s in h["speakers"]:
			if actor(str(s)) == null:
				continue
			if not intel.speaker_hints.has(s):
				intel.speaker_hints[s] = []
			if not hid in intel.speaker_hints[s]:
				intel.speaker_hints[s].append(hid)
				n += 1
	print("[mission] whisper network: %d rumour lines placed on the townsfolk" % n)


# ------------------------------------------------------------------ items, zones, timed work

func _spawn_items() -> void:
	for d in data.get("items", []):
		var id := str(d["id"])
		var pos := _vec(d["pos"])
		if d.has("interior") and interiors:
			var o: Vector3 = interiors.interior_origin(str(d["interior"]))
			if o != Vector3.INF:
				pos += o
		var root := Node3D.new()
		root.name = "Item_" + id
		world.add_child(root)
		root.global_position = pos
		root.rotation.y = float(d.get("facing", 0.0))
		var model := str(d.get("model", "bundle"))
		var mesh: Node3D
		match model:
			"bundle":
				mesh = Props.bundle()
				root.add_child(mesh)
			"book", "letter", "paper", "lock", "winch", "box":
				mesh = _small_prop(model)
				root.add_child(mesh)
			_:
				mesh = Assets.place(root, model, Vector3.ZERO, 0.0, float(d.get("scale", 1.0)))
				if mesh == null:
					mesh = _small_prop("box")
					root.add_child(mesh)
		var ia := InteractableScript.new()
		ia.name = "ItemInteract"
		ia.display_name = str(d.get("name", id))
		ia.marker_height = float(d.get("marker_height", 1.1))
		ia.highlight_root = mesh
		ia.prompt_func = _item_prompt.bind(id)
		ia.handler = _item_use.bind(id)
		root.add_child(ia)
		items[id] = {"def": d, "node": root, "ia": ia}
		_talk[id] = {"name": str(d.get("name", id)), "rules": []}
		if bool(d.get("hidden", false)):
			_item_visible(id, false)


func _small_prop(kind: String) -> Node3D:
	var root := Node3D.new()
	var col: Color = {"book": Color(0.35, 0.12, 0.1), "letter": Color(0.88, 0.84, 0.72), "paper": Color(0.9, 0.86, 0.74),
			"lock": Color(0.25, 0.24, 0.22), "winch": Color(0.3, 0.22, 0.14), "box": Color(0.4, 0.3, 0.2)}.get(kind, Color.GRAY)
	var size: Vector3 = {"book": Vector3(0.3, 0.07, 0.22), "letter": Vector3(0.24, 0.02, 0.17), "paper": Vector3(0.3, 0.02, 0.22),
			"lock": Vector3(0.2, 0.25, 0.1), "winch": Vector3(0.9, 0.9, 0.6), "box": Vector3(0.6, 0.5, 0.45)}.get(kind, Vector3.ONE * 0.3)
	# a small crate or post to stand it on, so it sits at hand height
	if kind in ["book", "letter", "paper"]:
		var stand := MeshInstance3D.new()
		var sm := BoxMesh.new()
		sm.size = Vector3(0.6, 0.85, 0.45)
		stand.mesh = sm
		var smat := StandardMaterial3D.new()
		smat.albedo_color = Color(0.32, 0.23, 0.15)
		stand.material_override = smat
		stand.position.y = 0.425
		root.add_child(stand)
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	var mat := StandardMaterial3D.new()
	mat.albedo_color = col
	mat.roughness = 0.8
	mi.material_override = mat
	mi.position.y = (0.85 + size.y * 0.5) if kind in ["book", "letter", "paper"] else size.y * 0.5
	root.add_child(mi)
	return root


func _item_visible(id: String, on: bool) -> void:
	var it: Dictionary = items.get(id, {})
	if it.is_empty():
		return
	(it["node"] as Node3D).visible = on
	(it["ia"] as Area3D).enabled = on


func _item_rule(id: String) -> Dictionary:
	var it: Dictionary = items.get(id, {})
	if it.is_empty() or not (it["node"] as Node3D).visible:
		return {}
	for r in it["def"].get("rules", []):
		if _cond_all(r.get("if", []), id):
			return r
	return {}


func _item_prompt(id: String) -> String:
	if not _work.is_empty():
		return ""
	return _fmt(str(_item_rule(id).get("prompt", "")))


func _item_use(_actor: Node, id: String) -> bool:
	var r := _item_rule(id)
	if r.is_empty() or str(r.get("prompt", "")) == "":
		return false
	if r.has("secs"):
		_work = {"id": id, "action": str(r.get("action", "")), "secs": float(r["secs"]), "t": 0.0}
		Mission.message.emit(str(r.get("work_text", "Working... stay close (%d s)." % int(r["secs"]))), 3.0)
		return true
	if r.has("node"):
		play(id, str(r["node"]))
		return true
	var nxt := _act(str(r.get("action", "")), id)
	if nxt != "":
		play(id, nxt)
	return true


func _work_tick(delta: float) -> void:
	var it: Dictionary = items.get(str(_work["id"]), {})
	var p := player()
	if it.is_empty() or p == null:
		_work = {}
		return
	if p.global_position.distance_to((it["node"] as Node3D).global_position) > 2.6:
		Mission.message.emit("You stepped away. The work is undone.", 2.5)
		_work = {}
		return
	_work["t"] = float(_work["t"]) + delta
	if float(_work["t"]) >= float(_work["secs"]):
		var a := str(_work["action"])
		var id := str(_work["id"])
		_work = {}
		var nxt := _act(a, id)
		if nxt != "":
			play(id, nxt)


## Smoke helper: finish any timed work at once.
func finish_work() -> void:
	if not _work.is_empty():
		_work["t"] = float(_work["secs"])


# ------------------------------------------------------------------ tone x personality

func _tone_reaction(tone: String, id: String) -> String:
	var pers := str(_talk.get(id, {}).get("personality", ""))
	stats["tones"] = int(stats["tones"]) + 1
	tone_stats["tones"] = int(tone_stats["tones"]) + 1
	if pers != "":
		stats["personalities"][pers] = true
		tone_stats["personalities"][pers] = true
	var table: Dictionary = camp.db.get("tones", {}).get("table", {}) if camp else {}
	var r := str(table.get(tone, {}).get(pers, "neutral"))
	if r != "neutral":
		stats["branches"] = int(stats["branches"]) + 1
		tone_stats["branches"] = int(tone_stats["branches"]) + 1
	if camp and pers != "":
		if r == "good":
			camp.set_flag("charmed_" + id)
			var cl: Dictionary = camp.db.get("tones", {}).get("charmed_line", {})
			var lu: Array = camp.rumours.loudest_unheard()
			if not lu.is_empty() and not camp.flag("charm_paid_" + id):
				camp.set_flag("charm_paid_" + id)
				camp.rumours.hear(str(lu[0]), "a charmed %s" % _talk.get(id, {}).get("name", id))
				set_meta("pre_lines", [["$npc", "%s \"%s\"" % [cl.get(pers, cl.get("default", "")), camp.rumours.def(lu[0]).get("text", "")]]])
		elif r == "bad":
			camp.set_flag("grudge_" + id)
	return r


func _thrown_out(id: String) -> void:
	var pers := str(_talk.get(id, {}).get("personality", ""))
	var t: Dictionary = camp.db.get("tones", {}).get("thrown_out", {}) if camp else {}
	var who := str(_talk.get(id, {}).get("name", id))
	_choices = []
	dialogue.set_meta("node", "")
	dialogue.show_node([[who, str(t.get(pers, t.get("default", "We are done.")))]], [])


# ------------------------------------------------------------------ checkpoints, capture, the cells

func _on_objectives_changed() -> void:
	var n := Mission.done_count()
	if n > _done_n and Mission.is_active():
		_done_n = n
		save_checkpoint("an objective done")


func save_checkpoint(why: String) -> void:
	var p := player()
	if p == null or p.global_position.y < -50.0 or captured:
		return
	_checkpoint = {"pos": p.global_position, "objectives": Mission.objectives.duplicate(true), "flags": Mission.flags.duplicate(true),
			"approach": Mission.approach, "carrying": p.carrying, "disguised": p.disguised, "why": why}


func has_checkpoint() -> bool:
	return not _checkpoint.is_empty()


## From Mission.fail: the watch has the player. Returns true if the runner takes over (the choice below).
func intercept_fail(reason: String) -> bool:
	if captured or _shut:
		return false
	if "--smoke" in OS.get_cmdline_user_args() and not capture_in_smoke:
		return false
	if not (reason.begins_with("Caught") or reason.begins_with("Beaten")):
		return false
	var can_slip := slips_left > 0 and has_checkpoint()
	var why := "one chance a night; notoriety +5, ten minutes pass" if can_slip else ("no quiet corner will hide you tonight" if slips_left <= 0 else "nowhere to slip back to")
	_nodes["__caught"] = {"lines": [["The watch", "Halt! Im Namen des Kaisers!\\n(Stop! In the Emperor's name!)"], ["$you", "Hands on your collar. A moment to decide."]],
		"choices": [
			{"text": "Slip away to the last safe moment (%s)" % _checkpoint.get("why", "?"), "action": "slip", "need": ["true"] if can_slip else ["!true"], "why": why},
			{"text": "Go quietly: a night in the cells", "action": "cells"},
			{"text": "Restart the night", "action": "restart"}]}
	_talk["__watch"] = {"name": "The watch"}
	_nodes["__caught"]["choices"][0]["need"] = [] if can_slip else ["coins>=100000"]
	play("__watch", "__caught")
	return true


func _calm_guards() -> void:
	for g in get_tree().get_nodes_in_group("guards"):
		if not world.is_ancestor_of(g):
			continue
		if g.get("caught"):
			g.caught = false
			g.set_physics_process(true)
		if g.has_method("end_search"):
			g.end_search()
		g.suspicion = 0.0
		g.state = 0


func _slip_away() -> void:
	var p := player()
	if p == null or _checkpoint.is_empty():
		return
	score["slips"] = int(score["slips"]) + 1
	slips_left -= 1
	Mission.objectives = (_checkpoint["objectives"] as Array).duplicate(true)
	Mission.flags = (_checkpoint["flags"] as Dictionary).duplicate(true)
	Mission.approach = str(_checkpoint["approach"])
	p.global_position = _checkpoint["pos"]
	p.velocity = Vector3.ZERO
	p.health = maxi(p.health, 2)
	p.carrying = bool(_checkpoint["carrying"])
	p.disguised = bool(_checkpoint["disguised"])
	p.reset_physics_interpolation()
	GameState.clock_minutes += 10.0
	GameState.add_notoriety(5.0)
	_calm_guards()
	Mission.objectives_changed.emit()
	Mission.message.emit("You twist free and are gone into the snow. Ten minutes later you are back at %s." % _checkpoint.get("why", "a safe place"), 4.5)
	Mission.set_flag("slipped")
	print("[mission] slipped away to the checkpoint (%s)" % _checkpoint.get("why", ""))


## A cell far below the map: a turnkey, a barred window, three ways out.
func _to_cells() -> void:
	var p := player()
	captured = true
	score["captured"] = true
	Mission.set_flag("captured")
	if p == null:
		return
	var at := Vector3(0, -400, 0)
	_cell = Node3D.new()
	_cell.name = "Cell"
	world.add_child(_cell)
	_cell.global_position = at
	var stone := StandardMaterial3D.new()
	stone.albedo_color = Color(0.28, 0.27, 0.25)
	stone.roughness = 1.0
	for b in [[Vector3(0, -0.1, 0), Vector3(8, 0.2, 6)], [Vector3(0, 3.1, 0), Vector3(8, 0.2, 6)], [Vector3(-4, 1.5, 0), Vector3(0.2, 3, 6)],
			[Vector3(4, 1.5, 0), Vector3(0.2, 3, 6)], [Vector3(0, 1.5, -3), Vector3(8, 3, 0.2)], [Vector3(0, 1.5, 3), Vector3(8, 3, 0.2)]]:
		var body := StaticBody3D.new()
		var cs := CollisionShape3D.new()
		var sh := BoxShape3D.new()
		sh.size = b[1]
		cs.shape = sh
		body.add_child(cs)
		var mi := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = b[1]
		mi.mesh = bm
		mi.material_override = stone
		body.add_child(mi)
		body.position = b[0]
		_cell.add_child(body)
	var lamp := OmniLight3D.new()
	lamp.light_color = Color(1.0, 0.62, 0.3)
	lamp.light_energy = 1.4
	lamp.omni_range = 7.0
	lamp.position = Vector3(2.5, 2.2, 1.5)
	_cell.add_child(lamp)
	items["cell_window"] = {}
	var win := {"id": "cell_window", "pos": [at.x - 2.8, at.y + 0.0, at.z - 2.6], "model": "box", "name": "The barred window",
		"rules": [{"if": ["flag:cell_breakout"], "prompt": "work the loose bar and climb out", "action": "cell:window"}]}
	data["items"] = [win]
	items.erase("cell_window")
	_spawn_items()
	_turnkey = population.spawn_entry({"id": "turnkey", "model": ["town_night_watchman", "watchman", "npc_m_06"],
			"pos": [at.x + 2.2, at.y, at.z + 1.4], "facing": 2.4, "behaviour": "stand", "role": "The turnkey"}) if population else null
	if _turnkey:
		_turnkey.add_to_group("mission")
		if _turnkey.has_method("relocate"):
			_turnkey.relocate(at + Vector3(2.2, 0.05, 1.4), 2.4)
	var bribe := 6 - (3 if GameState.get_influence("underworld") >= 30 or GameState.get_influence("guilds") >= 30 else 0)
	var ch: Array = [{"text": "Pay the turnkey (%d zł)" % bribe, "action": "cell:bribe", "need": ["coins>=%d" % bribe]}]
	var n := 0
	for fid in ["salon", "guilds", "church", "magnates", "underworld", "street"]:
		if GameState.get_influence(fid) >= 15 and n < 2:
			ch.append({"text": "Send word to the %s to ransom you (%s influence -10)" % [camp.fname(fid) if camp else fid, camp.fname(fid) if camp else fid], "action": "cell:ransom_" + fid})
			n += 1
	ch.append({"text": "Wait for him to doze, and try the window", "action": "cell:wait"})
	_nodes["__cell"] = {"lines": [["The turnkey", "Sit. The Commandant sees prisoners at nine, the magistrate at ten, and the hangman whenever he likes."],
			["The turnkey", "Of course, a man in my position has expenses."]], "choices": ch}
	_talk["turnkey"] = {"name": "The turnkey", "personality": "cynical-merchant", "temper": 0.4, "rules": [{"node": "__cell", "prompt": "talk to the turnkey"}]}
	add_talk("turnkey", _talk["turnkey"])
	p.global_position = at + Vector3(-1.0, 0.2, 0.0)
	p.velocity = Vector3.ZERO
	p.health = maxi(p.health, 1)
	p.carrying = false
	p.disguised = false
	p.reset_physics_interpolation()
	_calm_guards()
	Mission.announcement.emit("The cells under the watch post.", 4.0)
	print("[mission] captured: in the cells at %s" % GameState.time_string())
	play.call_deferred("turnkey", "__cell")


func _cell_out(how: String) -> String:
	var p := player()
	if how == "bribe":
		var bribe := 6 - (3 if GameState.get_influence("underworld") >= 30 or GameState.get_influence("guilds") >= 30 else 0)
		GameState.coins = maxi(GameState.coins - bribe, 0)
		Mission.set_flag("capture_out_bribe")
		dialogue.close()
		Mission.fail.call_deferred("Released from the cells for a bribe")
	elif how.begins_with("ransom_"):
		var fid := how.trim_prefix("ransom_")
		GameState.add_influence(fid, -10)
		if camp:
			for b in camp.rivals(fid):
				camp.add_grievance(b, 15)
		Mission.set_flag("capture_out_ransom")
		dialogue.close()
		Mission.fail.call_deferred("Ransomed from the cells by the " + (camp.fname(fid) if camp else fid))
	elif how == "wait":
		GameState.clock_minutes = maxf(GameState.clock_minutes, GameState.parse_clock("03:00"))
		Mission.set_flag("cell_breakout")
		Mission.message.emit("Three o'clock. The turnkey's chin sinks to his chest, then jerks up. Try the window while he looks away.", 5.0)
	elif how == "window":
		if _turnkey and is_instance_valid(_turnkey) and p and _faces(_turnkey, p):
			if _window_warned:
				Mission.set_flag("capture_out_failed")
				dialogue.close()
				Mission.fail.call_deferred("Caught at the cell window")
				return ""
			_window_warned = true
			Mission.message.emit("The turnkey grunts and looks your way. Not now.", 3.0)
			return ""
		_break_out()
	return ""


func _faces(n: Node3D, p: Node3D) -> bool:
	var to := p.global_position - n.global_position
	to.y = 0.0
	var fwd := -n.global_transform.basis.z
	fwd.y = 0.0
	return rad_to_deg(fwd.angle_to(to)) < 70.0


func _turnkey_tick(delta: float) -> void:
	if not Mission.has_flag("cell_breakout"):
		return
	_turn_t += delta
	var away := int(_turn_t / 5.0) % 2 == 1
	_turnkey.rotation.y = (2.4 + PI) if away else 2.4


func _break_out() -> void:
	var p := player()
	Mission.set_flag("capture_out_breakout")
	Mission.set_flag("broke_out")
	Mission.flags.erase("cell_breakout")
	if _cell:
		_cell.queue_free()
		_cell = null
	if _turnkey and is_instance_valid(_turnkey):
		_turnkey.queue_free()
	_turnkey = null
	_item_visible("cell_window", false)
	if p:
		p.global_position = Vector3(-24.0, 0.3, -29.0)
		p.velocity = Vector3.ZERO
		p.reset_physics_interpolation()
	GameState.add_notoriety(10.0)
	for g in get_tree().get_nodes_in_group("guards"):
		if world.is_ancestor_of(g):
			g.sight_modifiers.append(func(_g: Node, _p: Node) -> float: return 1.2)
	Mission.announcement.emit("Out through the window, down the old well shaft into the drains, and up through the laundry grate. 3 a.m., and every soldier is looking for you.", 5.0)
	print("[mission] broke out of the cells at %s" % GameState.time_string())


# ================================================================== the kingpin (missions.json `kingpin`)
## A target with a routine (a mission storyline emitting at_<station> events), an escort of enforcer bodyguards
## (Guards whose waypoints the runner keeps on a ring round him: one ahead, one behind looking back), a frisk
## when anyone without a permit comes within arm's reach (the approach fails: the guards go to Alarm and he
## holes up), and `kill:<method>` for the systemic kills (poison, accident, fire, riot, guillotine, knife, pistol).

var _kp_t := 0.0
var _kp_holed := false
var _mob: Array = []
var _mob_t := -1.0
var kill_method := ""


func kingpin() -> Node3D:
	var kd: Dictionary = data.get("kingpin", {})
	return actor(str(kd.get("id", ""))) if not kd.is_empty() else null


func bodyguards() -> Array:
	var names: Array = data.get("kingpin", {}).get("guards", [])
	var out: Array = []
	for g in get_tree().get_nodes_in_group("guards"):
		if world.is_ancestor_of(g) and g.guard_name in names and not g.is_downed():
			out.append(g)
	return out


func _kingpin_setup() -> void:
	var kd: Dictionary = data.get("kingpin", {})
	if kd.is_empty():
		return
	for g in bodyguards():
		g.enforcer = true
		var gg: Node3D = g
		g.sight_modifiers.append(func(_g: Node, p: Node) -> float:
			return 3.0 if p and is_instance_valid(gg) and (p as Node3D).global_position.distance_to(gg.global_position) < 8.0 else 1.0)
	if camp and camp.flag("warehouse_raid_feared"):
		var bg := bodyguards()
		if bg.size() > 1:
			var wh: Array = kd.get("stations", {}).get("warehouse", [0, 0])
			bg[-1].waypoints = [Vector3(float(wh[0]) + 2.0, 0, float(wh[1])), Vector3(float(wh[0]) - 2.0, 0, float(wh[1]))] as Array[Vector3]
			bg[-1].set_meta("kp_detached", true)
			Mission.set_flag("isolated_raid")


func _kingpin_tick(delta: float) -> void:
	var kd: Dictionary = data.get("kingpin", {})
	if kd.is_empty() or kill_method != "":
		return
	var k := kingpin()
	var p := player()
	if k == null or p == null:
		return
	_kp_t += delta
	if _mob_t >= 0.0:
		_mob_t += delta
		if _mob_t > float(kd.get("mob_secs", 8.0)) and not Mission.has_flag("mob_has_target"):
			Mission.set_flag("mob_has_target")
			for g in bodyguards():
				g.remove_from_group("guards")
				g.queue_free()
			k.relocate(_mob_spot(), 0.0)
			Mission.announcement.emit("The mob has dragged Wilk out into the snow. They are waiting for you to say what happens to him.", 5.0)
	if _kp_t < 0.4:
		return
	_kp_t = 0.0
	# escort ring: one ahead, one behind (looking back), unless busy
	var fwd := -k.global_transform.basis.z
	fwd.y = 0.0
	fwd = fwd.normalized() if fwd.length() > 0.1 else Vector3.FORWARD
	var ring := float(kd.get("ring", 2.4))
	var i := 0
	for g in bodyguards():
		if g.has_meta("kp_detached") or g.state >= 2 or g.get("is_runner"):
			continue
		var off := fwd * ring if i % 2 == 0 else -fwd * ring
		var at := k.global_position + off + fwd.cross(Vector3.UP) * (0.6 if i > 1 else 0.0)
		g.waypoints = [at, at] as Array[Vector3]
		i += 1
	# the frisk
	var d := p.global_position.distance_to(k.global_position)
	if d < float(kd.get("frisk_dist", 2.6)) and not _kp_holed and not _permitted():
		var near := false
		for g in bodyguards():
			if (g as Node3D).global_position.distance_to(k.global_position) < 8.0:
				near = true
		if near:
			_blocked()


func _permitted() -> bool:
	for c in data.get("kingpin", {}).get("permits", []):
		if _cond_all(c, ""):
			return true
	return false


func _blocked() -> void:
	Mission.set_flag("approach_blocked")
	_kp_holed = true
	for g in bodyguards():
		g.suspicion = 100.0
		if g.has_method("look_toward"):
			g.look_toward(player(), 4.0, true)
	var k := kingpin()
	var hide: Array = data.get("kingpin", {}).get("stations", {}).get(str(data.get("kingpin", {}).get("hole", "warehouse")), [])
	var s: Node = population.storyline(str(data.get("kingpin", {}).get("story", ""))) if population else null
	if s:
		s.abort()
	if k and hide.size() >= 2:
		k.claim()
		k.script_goto(Vector3(float(hide[0]), 0, float(hide[1])), 0.0, true)
	Mission.message.emit("A bodyguard's hand hits your chest: \"Arms up.\" The other has a pistol out, and Wilk is already walking away fast.", 4.5)
	print("[mission] kingpin approach blocked (frisked) at %s" % GameState.time_string())


func _mob_spot() -> Vector3:
	var ms: Array = data.get("kingpin", {}).get("mob_spot", [0, 0])
	return Vector3(float(ms[0]), 0, float(ms[1]))


func _mob_start() -> void:
	if _mob_t >= 0.0 or population == null:
		return
	_mob_t = 0.0
	Mission.set_flag("riot_on")
	var at := _mob_spot()
	for i in 6:
		var b: Node3D = population.spawn_entry({"id": "mob_%d" % i, "model": [["dist_raftsman", "npc_m_04"], ["dist_porter", "npc_m_01"], ["npc_m_00", "figure_townsman"],
				["dist_peasant", "npc_m_03"], ["npc_f_03", "figure_townswoman"], ["dist_tanner", "npc_m_05"]][i],
				"pos": [at.x + cos(i) * 3.0, 0, at.z + sin(i) * 3.0], "facing": 0.0, "behaviour": "stand", "role": "rioter"})
		if b:
			b.add_to_group("mission")
			b.add_to_group("crowd")
			if b.has_method("claim"):
				b.claim()
			b.say(["Na Wilka!\n(At the Wolf!)", "Dość królów!\n(No more kings!)", "Pochodnie!\n(Torches!)"][i % 3], 3.0)
			_mob.append(b)
	for g in bodyguards():
		g.investigate(at, 30.0, "noise")
	GameState.crackdown = clampi(GameState.crackdown + 4, 0, 100)
	Mission.announcement.emit("The quay rises: torches, boathooks, a roar of \"No more kings!\"", 4.5)


func _kill(method: String) -> String:
	var k := kingpin()
	if kill_method != "" or k == null:
		return ""
	score["kills"] = int(score["kills"]) + 1
	score["methods"][method] = true
	if method in ["pistol", "riot", "guillotine", "fire"]:
		score["noise"] = int(score["noise"]) + 1
	kill_method = method
	Mission.set_flag("killed")
	Mission.set_flag("killed_" + method)
	if k.has_method("knock_down"):
		k.knock_down(99999.0)
	var s: Node = population.storyline(str(data.get("kingpin", {}).get("story", ""))) if population else null
	if s:
		s.abort()
	var t: Dictionary = data.get("kill_texts", {})
	Mission.announcement.emit(str(t.get(method, "Wilk is dead.")), 5.0)
	if Mission.data.get("approaches", {}).has(method):
		Mission.set_approach(method)
	Mission.complete_objective("kill_target")
	if method == "pistol":
		GameState.add_notoriety(30.0)
		for g in bodyguards():
			g.suspicion = 100.0
	print("[mission] kingpin killed: %s at %s" % [method, GameState.time_string()])
	return ""


# ------------------------------------------------------------------ score card data

func _score_verb(key: String, arg: String) -> void:
	match key:
		"disguise":
			if arg == "on":
				score["methods"]["disguise"] = true
		"flag":
			if arg.begins_with("disguise_") or arg in ["masked", "laundress", "drunk_act", "invited"]:
				score["methods"]["disguise"] = true
			elif arg.begins_with("poisoned") or arg == "hauer_poisoned":
				score["methods"]["poison"] = true
			elif arg in ["riot_on"]:
				score["noise"] = int(score["noise"]) + 1
				score["collateral"] = int(score["collateral"]) + 1
				score["allies"]["the crowd"] = true
			elif arg in ["batman_bribed", "informer_bribed"]:
				score["methods"]["bribe"] = true
			elif arg == "omen_told" or arg == "canon_away":
				score["methods"]["superstition"] = true
		"fire":
			score["noise"] = int(score["noise"]) + 1
			score["collateral"] = int(score["collateral"]) + 2
			score["methods"]["fire"] = true
		"mob":
			score["noise"] = int(score["noise"]) + 1
			score["collateral"] = int(score["collateral"]) + 1
			score["allies"]["the raftsmen"] = true
		"plant":
			score["methods"]["rumour"] = true
		"lure", "send":
			score["methods"]["distraction"] = true
		"urchin":
			score["allies"]["the urchins"] = true
		"camp":
			if arg == "miracle_staged":
				score["methods"]["miracle"] = true


## Tonight's score inputs, read by Campaign.score_night at dawn.
func score_card() -> Dictionary:
	var sc := score.duplicate(true)
	if Mission.has_flag("urchins_hired"):
		sc["allies"]["the urchins"] = true
	if Mission.has_flag("brothel_room") or Mission.has_flag("brothel_room_used") or Mission.has_flag("gossip_rota"):
		sc["allies"]["Mother Weronika"] = true
	if Mission.has_flag("decoy_planted"):
		sc["methods"]["false leaf"] = true
	if Mission.has_flag("slipped"):
		sc["methods"]["slipping away"] = true
	if events and events.fired.size() > 0:
		sc["events"] = events.fired.size()
	sc["alarms"] = GameState.night_alarm_count
	sc["minutes"] = int(GameState.clock_minutes - float(sc["clock0"]))
	sc["spent"] = maxi(int(sc["coins0"]) - GameState.coins, 0)
	sc["approach"] = Mission.approach
	return sc


# ------------------------------------------------------------------ side quests (campaign.json side_quests)

## Tonight's lead may be a side quest: merge its people, items, talk, texts and optional objectives.
func _merge_side_quest() -> void:
	if camp == null or GameState.campaign.is_empty():
		return
	var sq: Dictionary = camp.side_quest_tonight()
	if sq.is_empty():
		return
	var n := 0
	for e in sq.get("npcs", []):
		var o: Vector3 = interiors.interior_origin(str(e.get("interior", ""))) if interiors and e.has("interior") else Vector3.ZERO
		if o == Vector3.INF or population == null:
			continue
		var pp: Array = e["pos"]
		var at := o + Vector3(float(pp[0]), float(pp[1]) + 0.05, float(pp[2]))
		var e2: Dictionary = e.duplicate()
		e2["pos"] = [at.x, at.y, at.z]
		var b: Node3D = population.spawn_entry(e2)
		if b:
			b.add_to_group("mission")
			if b.has_method("relocate"):
				b.relocate(at, float(e.get("facing", 0.0)))
			n += 1
	if not data.has("items"):
		data["items"] = []
	for it in sq.get("items", []):
		(data["items"] as Array).append(it)
	var tx: Dictionary = data.get("texts", {})
	for k in sq.get("texts", {}):
		tx[k] = sq["texts"][k]
	data["texts"] = tx
	var ot: Dictionary = data.get("on_takedown", {})
	for k in sq.get("on_takedown", {}):
		ot[k] = sq["on_takedown"][k]
	data["on_takedown"] = ot
	for id in sq.get("takedown", []):
		var a := actor(str(id))
		if a:
			a.add_to_group("takedown")
	for id in sq.get("talk", {}):
		add_talk(str(id), sq["talk"][id], sq.get("dialogue", {}))
	var marks: Dictionary = data.get("stealth", {}).get("map_marks", {})
	for k in sq.get("map_marks", {}):
		marks[k] = sq["map_marks"][k]
	if data.has("stealth"):
		data["stealth"]["map_marks"] = marks
	for o2 in sq.get("objectives", []):
		var lo := {"id": str(o2["id"]), "text": str(o2["text"]), "done": false, "optional": true}
		set_meta("lead_" + str(o2["id"]), lo)
		Mission.objectives.append(lo.duplicate())
	Mission.objectives_changed.emit()
	print("[mission] side quest: %s (%d people placed below)" % [sq.get("title", "?"), n])
