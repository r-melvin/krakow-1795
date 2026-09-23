extends Node
## Runs one scripted sequence from data/storylines.json. Created by population.gd.
##
## {"id", "title",
##  "trigger": {"at": "HH:MM"} | {"radius": m, "actor": id, "cone"?: deg} | {"flag": name}
##             (time on the world clock; player within m of actor, optionally inside the actor's field of view;
##              or a Mission flag being set)
##  "spooked": {"radius": m, "actors": [ids], "goto": label, "until": label}   optional: player interference
##  "steps": [step, ...]}
## Step: {"do": op, "actor": id, "label"?: name, "next"?: label | "end", "when"?: flag, "unless"?: flag, ...}
##   (a step whose Mission flag condition fails is skipped, its "next" ignored)
##   goto  pos: [x,y,z] | post: name | target: actor (+ keep: m); run?; wait? (default true);
##         secs?: with target+keep, tail the target that long (real seconds); lose?: m, on_lose?: label
##   wait  secs: s | until: "HH:MM" | arrive: [ids] | flag: name (a Mission flag)
##   face  pos | target
##   say   text, secs (default 3), wait? (default true), hint?: id (intel.gd overhearing), alert?: {guard: name, suspicion: 0..100, pos?: [x,y,z]}
##         (alert sends the guard to pos, or by default to where the player stands)
##   event name: calls Mission.story_event(story id, name, actor) for mission logic
##   play  clip, secs? (blocks that long if given)
## Actor ids: an npc id from data/npcs.json, "player", or "guard:<guard_name>".
## Movement steps claim an NPC from its schedule; all claimed NPCs are released when the storyline ends.

enum Status { WAITING, RUNNING, DONE }

## For the journal (scripts/ui/journal.gd): the sequence began, an actor spoke a line, the sequence ended.
signal storyline_started(id: String)
signal storyline_step(id: String, text: String)
signal storyline_ended(id: String)
## For intel.gd (phase E): a `say` step carrying `"hint": id` (a hint in data/storylines.json `hints`) was spoken by
## `actor`; intel writes the hint to the journal if the player stood within earshot.
signal storyline_hint(id: String, hint_id: String, actor: Node3D)

var population: Node              ## population.gd, for actor and post lookup
var data: Dictionary = {}
var status: Status = Status.WAITING
var story_id := ""

var _steps: Array = []
var _labels: Dictionary = {}
var _i := -1
var _t := 0.0
var _claimed: Array[Node] = []
var _spooked := false
var _trigger_at := -1.0


func _ready() -> void:
	story_id = str(data.get("id", name))
	_steps = data.get("steps", [])
	for i in _steps.size():
		var s: Dictionary = _steps[i]
		if s.has("label"):
			_labels[str(s["label"])] = i
	var trig: Dictionary = data.get("trigger", {})
	if trig.has("at"):
		_trigger_at = GameState.parse_clock(str(trig["at"]))


func _physics_process(delta: float) -> void:
	match status:
		Status.WAITING:
			if _triggered():
				status = Status.RUNNING
				print("[story] %s begins at %s" % [story_id, GameState.time_string()])
				storyline_started.emit(story_id)
				_enter(0)
		Status.RUNNING:
			_check_spooked()
			if status != Status.RUNNING:
				return
			_t += delta
			var jump := _tick(_steps[_i], delta)
			if jump != "":
				_goto_label(jump)
			elif _done(_steps[_i]):
				var nxt := str((_steps[_i] as Dictionary).get("next", ""))
				if nxt != "":
					_goto_label(nxt)
				else:
					_enter(_i + 1)


func _triggered() -> bool:
	var trig: Dictionary = data.get("trigger", {})
	if _trigger_at >= 0.0:
		return GameState.clock_minutes >= _trigger_at
	if trig.has("flag"):
		return Mission.has_flag(str(trig["flag"]))
	if trig.has("radius"):
		var a := _actor(str(trig.get("actor", "")))
		var p := _player()
		if a and p and a.visible and not (a.has_method("is_downed") and a.is_downed()):
			if a.global_position.distance_to(p.global_position) >= float(trig["radius"]):
				return false
			if trig.has("cone"):
				var to_p := p.global_position - a.global_position
				to_p.y = 0.0
				var fwd := -a.global_transform.basis.z
				fwd.y = 0.0
				return rad_to_deg(fwd.angle_to(to_p)) < float(trig["cone"]) * 0.5
			return true
	return false


## Start (or jump) straight to a labelled step, whatever the trigger (mission logic: a planted decoy sends the
## informer off to report at once).
func start_at(label: String) -> void:
	if status == Status.DONE or not _labels.has(label):
		return
	if status == Status.WAITING:
		status = Status.RUNNING
		print("[story] %s begins at %s (at %s)" % [story_id, GameState.time_string(), label])
		storyline_started.emit(story_id)
	_goto_label(label)


## Stop now (mission logic: the actor was bribed, fooled or knocked down). Claimed NPCs are released.
func abort() -> void:
	if status == Status.RUNNING:
		print("[story] %s aborted at %s" % [story_id, GameState.time_string()])
		_finish()
	else:
		status = Status.DONE
		storyline_ended.emit(story_id)


func _check_spooked() -> void:
	var sp: Dictionary = data.get("spooked", {})
	if _spooked or sp.is_empty():
		return
	var until := str(sp.get("until", ""))
	if until != "" and _labels.has(until) and _i >= int(_labels[until]):
		return
	var p := _player()
	if p == null:
		return
	for id in sp.get("actors", []):
		var a := _actor(str(id))
		if a and a.global_position.distance_to(p.global_position) < float(sp.get("radius", 3.0)):
			_spooked = true
			print("[story] %s interrupted by the player at %s" % [story_id, GameState.time_string()])
			_goto_label(str(sp.get("goto", "end")))
			return


func _goto_label(label: String) -> void:
	if label == "end" or not _labels.has(label):
		_finish()
	else:
		_enter(int(_labels[label]))


func _enter(i: int) -> void:
	if i >= _steps.size():
		_finish()
		return
	var s: Dictionary = _steps[i]
	if (s.has("when") and not Mission.has_flag(str(s["when"]))) or (s.has("unless") and Mission.has_flag(str(s["unless"]))):
		_enter(i + 1)
		return
	_i = i
	_t = 0.0
	var a := _actor(str(s.get("actor", "")))
	match str(s.get("do", "")):
		"goto":
			var npc := _claim(a)
			if npc:
				var target: Variant = _target_of(s)
				npc.script_goto(target, float(s.get("keep", 0.0)), bool(s.get("run", false)))
		"face":
			var npc := _claim(a)
			if npc:
				npc.script_face(_target_of(s))
		"play":
			var npc := _claim(a)
			if npc:
				npc.script_play(str(s.get("clip", "idle")))
		"say":
			if a:
				var Walker := preload("res://scripts/npc/walker.gd")
				Walker.speech(a, str(s.get("text", "...")), float(s.get("secs", 3.0)))
				storyline_step.emit(story_id, str(s.get("text", "...")))
				if s.has("hint"):
					storyline_hint.emit(story_id, str(s["hint"]), a)
			if s.has("alert"):
				_alert(s["alert"])
		"event":
			Mission.story_event(story_id, str(s.get("name", "")), a)


## Per-frame work for the running step. Returns a label to jump to, or "".
func _tick(s: Dictionary, _delta: float) -> String:
	if str(s.get("do", "")) == "goto" and s.has("lose"):
		var a := _actor(str(s.get("actor", "")))
		var tgt := _actor(str(s.get("target", "")))
		if a and tgt and a.global_position.distance_to(tgt.global_position) > float(s["lose"]):
			return str(s.get("on_lose", "end"))
	return ""


func _done(s: Dictionary) -> bool:
	match str(s.get("do", "")):
		"goto":
			if not bool(s.get("wait", true)):
				return true
			if s.has("secs"):
				return _t >= float(s["secs"])
			var npc := _actor(str(s.get("actor", "")))
			return npc == null or not ("script_arrived" in npc) or npc.script_arrived or _t > 90.0
		"wait":
			if s.has("until"):
				return GameState.clock_minutes >= GameState.parse_clock(str(s["until"]))
			if s.has("flag"):
				return Mission.has_flag(str(s["flag"]))
			if s.has("arrive"):
				for id in s["arrive"]:
					var n := _actor(str(id))
					if n and "script_arrived" in n and not n.script_arrived and _t < 90.0:
						return false
				return true
			return _t >= float(s.get("secs", 1.0))
		"say":
			return not bool(s.get("wait", true)) or _t >= float(s.get("secs", 3.0))
		"play":
			return _t >= float(s.get("secs", 0.0))
		"face":
			return _t >= 0.4
	return true


func _finish() -> void:
	status = Status.DONE
	for n in _claimed:
		if is_instance_valid(n):
			n.release()
	_claimed.clear()
	print("[story] %s ends at %s" % [story_id, GameState.time_string()])
	storyline_ended.emit(story_id)


## The actor of the running step (the speaker, during a `say`), or null. For the journal.
func current_actor() -> Node3D:
	if status != Status.RUNNING or _i < 0 or _i >= _steps.size():
		return null
	return _actor(str((_steps[_i] as Dictionary).get("actor", "")))


## Every actor id the sequence uses (npc ids, "guard:<name>"; not "player"). For the journal.
func actor_ids() -> PackedStringArray:
	var out := PackedStringArray()
	for st in _steps:
		var id := str((st as Dictionary).get("actor", ""))
		if id != "" and id != "player" and not out.has(id):
			out.append(id)
	return out


func _claim(a: Node3D) -> Node3D:
	if a == null or not a.has_method("claim"):
		return null
	if not _claimed.has(a):
		a.claim()
		_claimed.append(a)
	return a


func _target_of(s: Dictionary) -> Variant:
	if s.has("pos"):
		var p: Array = s["pos"]
		return Vector3(float(p[0]), float(p[1]), float(p[2]))
	if s.has("post"):
		return population.post_pos(str(s["post"]))
	return _actor(str(s.get("target", "")))


func _actor(id: String) -> Node3D:
	if id == "":
		return null
	if id == "player":
		return _player()
	if id.begins_with("guard:"):
		var gname := id.trim_prefix("guard:")
		for g in get_tree().get_nodes_in_group("guards"):
			if g.get("guard_name") == gname:
				return g
		return null
	return population.actor(id) if population else null


func _player() -> Node3D:
	return get_tree().get_first_node_in_group("player") as Node3D


## An informer's report: the named guard grows suspicious and heads for where the player was last seen.
func _alert(al: Dictionary) -> void:
	var g := _actor("guard:" + str(al.get("guard", "")))
	var p := _player()
	if g == null or p == null:
		return
	var where: Vector3 = p.global_position
	if al.has("pos"):
		var ap: Array = al["pos"]
		where = Vector3(float(ap[0]), float(ap[1]), float(ap[2]))
	g.set("last_known", where)
	g.set("suspicion", maxf(float(g.get("suspicion")), float(al.get("suspicion", 50.0))))
