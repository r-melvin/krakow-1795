extends Node
## Autoload "Mission". Objective tracking shared by the mission runner, HUD, guards and interactables.
## Data: data/missions.json. `start(id, world)` loads a mission, sets title/briefing/objectives and hands the
## world-side work (actors, props, dialogue, curfew) to scripts/mission/mission_runner.gd, which lives under the
## night world and is freed with it. `prepare_for_day(id)` fills title/briefing/objectives for the day briefing
## without spawning anything. The HUD reads `objectives` and listens to the signals.
##
## Branching missions: an entry may list `approaches` {name: {label, objectives}}; `set_approach(name)` swaps
## the objective list to that branch (objectives with the same id keep their done state).

signal objectives_changed
signal completed(summary: String)
signal failed(reason: String)
signal message(text: String, seconds: float)      ## transient on-screen text (dialogue line, hint)
signal announcement(text: String, seconds: float) ## large centred banner (the curfew bell)
signal approach_changed(approach: String)

const DATA_PATH := "res://data/missions.json"
const RunnerScript := preload("res://scripts/mission/mission_runner.gd")

var active := false
var mission_id := ""
var title := ""
var briefing := ""
var objectives: Array = []       ## [{id, text, done, optional}]
var summary := ""
var approach := ""               ## "" until the player commits to a branch (e.g. underworld | street | salon)
var flags: Dictionary = {}       ## mission facts set by dialogue actions and storylines (see missions.json)
var data: Dictionary = {}        ## the running mission's entry from missions.json
var runner: Node = null          ## mission_runner.gd under the night world, null by day

## Campaign journal (scripts/ui/journal.gd reads and fills it; it survives nights and is reset by a new game):
##   storylines: {id: {discovered: bool, status: "available"|"in progress"|"resolved"|"set aside", at: "HH:MM"}}
##   log:        [{night, t: "HH:MM", text, kind: "message"|"announcement"|"story"|"note"}]   newest last
##   people:     {npc id: {name, role, faction, where, t, night}}
##   missions:   [{id, title, night, success, approach}]   finished nights
var journal: Dictionary = {"storylines": {}, "log": [], "people": {}, "missions": []}

var _db: Dictionary = {}


func _ready() -> void:
	_ensure_input_actions()
	message.connect(func(t: String, _s: float) -> void: journal_log(t, "message"))
	announcement.connect(func(t: String, _s: float) -> void: journal_log(t, "announcement"))
	GameState.mission_ended.connect(_journal_mission_ended)
	GameState.phase_changed.connect(func(p: int) -> void:
		if p == GameState.Phase.ORIGIN_SELECT:
			journal = {"storylines": {}, "log": [], "people": {}, "missions": []})
	var f := FileAccess.open(DATA_PATH, FileAccess.READ)
	if f:
		var parsed: Variant = JSON.parse_string(f.get_as_text())
		if parsed is Dictionary:
			_db = parsed
		else:
			push_error("Mission: bad JSON in %s" % DATA_PATH)


## `attack` is added here (left mouse, F) so project.godot's input map need not change.
func _ensure_input_actions() -> void:
	if not InputMap.has_action("attack"):
		InputMap.add_action("attack")
		var mb := InputEventMouseButton.new()
		mb.button_index = MOUSE_BUTTON_LEFT
		InputMap.action_add_event("attack", mb)
		var k := InputEventKey.new()
		k.physical_keycode = KEY_F
		InputMap.action_add_event("attack", k)


func default_id() -> String:
	return str(_db.get("default", ""))


func mission_data(id: String) -> Dictionary:
	return _db.get("missions", {}).get(id, {})


## Day briefing: title, briefing and the opening objectives, nothing spawned, not active.
func prepare_for_day(id: String = "") -> void:
	_reset()
	_configure(id if id != "" else default_id())
	objectives_changed.emit()


## Night: load `id` and, given the freshly built night world, spawn its actors. Safe to call again on restart.
func start(id: String, world: Node = null) -> void:
	_reset()
	_configure(id)
	active = true
	for sid in journal["storylines"]:        # a fresh night: the city's storylines have not happened yet
		var e: Dictionary = journal["storylines"][sid]
		if e.get("status", "") != "resolved" or not data.get("approaches", {}).has(sid):
			e["status"] = "available"
	if world and not data.is_empty():
		runner = RunnerScript.new()
		runner.name = "MissionRunner"
		runner.data = data
		runner.world = world
		world.add_child(runner)
	objectives_changed.emit()


func _reset() -> void:
	if runner and is_instance_valid(runner) and not runner.is_queued_for_deletion():
		runner.queue_free()
	runner = null
	active = false
	mission_id = ""
	title = ""
	briefing = ""
	objectives = []
	summary = ""
	approach = ""
	flags = {}
	data = {}


func _configure(id: String) -> void:
	mission_id = id
	data = mission_data(id)
	if data.is_empty():
		# Legacy night: reach the safe house.
		title = "Night %d" % GameState.day
		briefing = "Reach the safe house at the south-east corner of the Rynek before dawn. Unseen, if you can."
		objectives = [{"id": "safe_house", "text": "Reach the safe house (lit marker, SE corner)", "done": false, "optional": false}]
		return
	title = str(data.get("title", id))
	briefing = str(data.get("briefing", ""))
	objectives = _objective_list(data.get("objectives", []))


static func _objective_list(raw: Array) -> Array:
	var out: Array = []
	for o in raw:
		out.append({"id": str(o["id"]), "text": str(o.get("text", o["id"])), "done": false,
				"optional": bool(o.get("optional", false))})
	return out


func is_active() -> bool:
	return active


# ------------------------------------------------------------------ objectives, flags, approach

func has_objective(id: String) -> bool:
	for o in objectives:
		if o["id"] == id:
			return true
	return false


func is_done(id: String) -> bool:
	for o in objectives:
		if o["id"] == id:
			return o["done"]
	return false


func done_count() -> int:
	var n := 0
	for o in objectives:
		if o["done"]:
			n += 1
	return n


func set_flag(name: String, value: Variant = true) -> void:
	flags[name] = value


func has_flag(name: String) -> bool:
	return flags.has(name) and bool(flags[name])


## Commit to a branch: swap in its objectives, keeping the done state of objectives the branches share.
func set_approach(a: String) -> void:
	if approach == a:
		return
	var branch: Dictionary = data.get("approaches", {}).get(a, {})
	if branch.is_empty():
		return
	approach = a
	var was_done := {}
	for o in objectives:
		if o["done"]:
			was_done[o["id"]] = true
	objectives = _objective_list(branch.get("objectives", []))
	for o in objectives:
		if was_done.has(o["id"]):
			o["done"] = true
	approach_changed.emit(a)
	objectives_changed.emit()
	message.emit(str(branch.get("label", a)), 4.0)


func complete_objective(id: String) -> void:
	for o in objectives:
		if o["id"] == id and not o["done"]:
			o["done"] = true
			objectives_changed.emit()
			message.emit("Objective complete: " + o["text"], 3.0)
	_check_done()


func _check_done() -> void:
	if not active:
		return
	for o in objectives:
		if not o["done"] and not o.get("optional", false):
			return
	finish(true)


# ------------------------------------------------------------------ ending

func finish(success: bool) -> void:
	if not active:
		return
	active = false
	summary = _success_summary() if success else _failure_summary("")
	if success:
		completed.emit(summary)
	_end_night(success)


func fail(reason: String) -> void:
	if not active:
		return
	active = false
	summary = _failure_summary(reason)
	failed.emit(reason)
	_end_night(false)


## Missions with `rewards` settle the night here (influence, crackdown, day) and hand the summary to the dawn
## report; the legacy safe-house night keeps GameState.end_night's own bookkeeping.
func _end_night(success: bool) -> void:
	if runner and is_instance_valid(runner):
		runner.call("shutdown")
	if not data.has("rewards"):
		GameState.end_night(success)
		return
	var rw: Dictionary = data["rewards"]
	GameState.night_objective_done = success
	if success:
		var infl: Dictionary = rw.get("influence", {})
		for fid in infl:
			GameState.add_influence(fid, int(infl[fid]))
		if is_done("decoy_informer"):
			GameState.crackdown += int(rw.get("decoy_crackdown", 0))
	else:
		var fl: Dictionary = data.get("failure", {})
		GameState.crackdown += int(fl.get("crackdown", 15))
		var finfl: Dictionary = fl.get("influence", {})
		for fid in finfl:
			GameState.add_influence(fid, int(finfl[fid]))
	GameState.crackdown += int(rw.get("alarm_crackdown", 5)) * GameState.night_alarm_count
	GameState.crackdown = clampi(GameState.crackdown, 0, 100)
	GameState.day += 1
	# Summary first, so whatever builds the dawn screen on the phase change already has it.
	GameState.mission_ended.emit(success, summary)
	GameState.set_phase(GameState.Phase.DAWN)


func _text(key: String) -> String:
	return str(data.get("summary", {}).get(key, ""))


func _success_summary() -> String:
	if data.is_empty():
		return "You reached the safe house before dawn."
	var lines: PackedStringArray = []
	var t := _text(approach if approach != "" else "underworld")
	if t != "":
		lines.append(t)
	if is_done("decoy_informer"):
		lines.append(_text("decoy"))
	if has_flag("owe_urchins"):
		lines.append(_text("owe"))
	if has_flag("informer_downed"):
		lines.append(_text("informer_downed"))
	var n := GameState.night_alarm_count
	lines.append(_text("clean") if n == 0 else _text("alarms").replace("{n}", str(n)))
	lines.append(_text("close"))
	var rw: Dictionary = data.get("rewards", {})
	var parts: PackedStringArray = []
	var infl: Dictionary = rw.get("influence", {})
	for fid in infl:
		parts.append("%s %+d" % [GameState.factions.get(fid, {}).get("name", fid), int(infl[fid])])
	var ck := int(rw.get("alarm_crackdown", 5)) * n + (int(rw.get("decoy_crackdown", 0)) if is_done("decoy_informer") else 0)
	if ck != 0:
		parts.append("Crackdown %+d" % ck)
	if not parts.is_empty():
		lines.append("(" + ", ".join(parts) + ")")
	return "\n".join(lines)


func _failure_summary(reason: String) -> String:
	if data.is_empty():
		return "You were caught by the watch. A bribe and a night in the cells."
	var lines: PackedStringArray = []
	if reason.begins_with("Beaten"):
		lines.append(_text("fail_beaten"))
	elif reason.begins_with("Caught"):
		var who := reason.get_slice(":", 1).strip_edges() if ":" in reason else "the watch"
		lines.append(_text("fail_caught").replace("{guard}", who))
	else:
		lines.append(_text("fail_other").replace("{reason}", reason))
	var p := get_tree().get_first_node_in_group("player")
	if p and p.get("carrying"):
		lines.append(_text("fail_bundle"))
	var fl: Dictionary = data.get("failure", {})
	var parts: PackedStringArray = ["Crackdown %+d" % int(fl.get("crackdown", 15))]
	var finfl: Dictionary = fl.get("influence", {})
	for fid in finfl:
		parts.append("%s %+d" % [GameState.factions.get(fid, {}).get("name", fid), int(finfl[fid])])
	lines.append("(" + ", ".join(parts) + ")")
	return "\n".join(lines)


# ------------------------------------------------------------------ player-facing hooks

func interact(actor: Node, target: Node) -> bool:
	## Called by the player when pressing `interact` near a target in group "interactable". Return true if handled.
	if dialogue_blocking():
		return false
	if target and target.has_method("on_interact"):
		return target.on_interact(actor)
	return false


## True while a dialogue box is open, and for a moment after it closes (so the closing key press does not
## also open a door or restart the conversation).
func dialogue_blocking() -> bool:
	return runner != null and is_instance_valid(runner) and runner.call("dialogue_blocking")


func dialogue_open() -> bool:
	return runner != null and is_instance_valid(runner) and runner.call("dialogue_open")


## From storyline.gd `{"do": "event"}` steps.
func story_event(story_id: String, event: String, actor: Node) -> void:
	if runner and is_instance_valid(runner):
		runner.call("on_story_event", story_id, event, actor)


## From player.gd when a rear takedown or a fight downs someone.
func on_takedown(target: Node, in_fight: bool) -> void:
	if runner and is_instance_valid(runner):
		runner.call("on_takedown", target, in_fight)


# ------------------------------------------------------------------ journal data (read by scripts/ui/journal.gd)

## Appends a timestamped entry to the journal log (the long text that no longer stays on screen).
func journal_log(text: String, kind: String = "note") -> void:
	if text.strip_edges() == "" or GameState.phase != GameState.Phase.NIGHT:
		return
	var lines: Array = journal["log"]
	if not lines.is_empty() and lines[-1]["text"] == text and lines[-1]["t"] == GameState.time_string():
		return
	lines.append({"night": GameState.day, "t": GameState.time_string(), "text": text, "kind": kind})
	while lines.size() > 200:
		lines.pop_front()


## Marks storyline (or mission approach) `id` discovered. Returns true the first time.
func journal_discover(id: String) -> bool:
	var e: Dictionary = journal["storylines"].get(id, {})
	var first := not bool(e.get("discovered", false))
	e["discovered"] = true
	if not e.has("status"):
		e["status"] = "available"
	if first:
		e["at"] = GameState.time_string()
	journal["storylines"][id] = e
	return first


func journal_set_status(id: String, status: String) -> void:
	var e: Dictionary = journal["storylines"].get(id, {"discovered": false})
	e["status"] = status
	journal["storylines"][id] = e


func _journal_mission_ended(success: bool, _summary: String) -> void:
	if mission_id == "":
		return
	journal["missions"].append({"id": mission_id, "title": title, "night": GameState.day - 1,
			"success": success, "approach": approach})
	for a in data.get("approaches", {}):
		var st := str(journal["storylines"].get(a, {}).get("status", ""))
		if st == "" or st == "resolved":
			continue
		journal_set_status(a, ("resolved" if success else "available") if a == approach else "set aside")
