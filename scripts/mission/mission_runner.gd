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
	print("[mission] %s: %d people to talk to, stash at %s" % [data.get("title", "?"), _talk.size(),
			stash.global_position if stash else "none"])


func shutdown() -> void:
	_shut = true
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
			return GameState.get_influence(parts[0]) >= int(parts[1])
		"coins>=cost":
			return GameState.coins >= urchin_cost()
	if c.begins_with("coins>="):
		return GameState.coins >= int(c.trim_prefix("coins>="))
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
	for l in node.get("lines", []):
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
				return "You are not known enough here."
			"coins>=cost":
				return "Not enough coin."
	return ""


func _on_choice(i: int) -> void:
	if i < 0 or i >= _choices.size():
		return
	var c: Dictionary = _choices[i]
	var nxt := str(c.get("next", ""))
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
		if str(c.get("action", "")) == action_or_next or str(c.get("next", "")) == action_or_next:
			return k
	return -1


# ------------------------------------------------------------------ actions

## Dialogue and talk-rule actions. Returns a dialogue node to jump to, or "".
func _act(action: String, id: String) -> String:
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


func on_takedown(target: Node, in_fight: bool) -> void:
	if target == actor("informer"):
		Mission.set_flag("informer_downed")
		_abort_story("informer")
		Mission.message.emit("The informer sleeps in the snow. He will wake with a sore head and no story.", 4.0)
	elif target is Guard:
		if in_fight:
			Mission.message.emit("%s is down. The Austrians will make the city pay for that." % target.guard_name, 4.0)
		else:
			Mission.message.emit("%s slumps without a sound." % target.guard_name, 3.0)
