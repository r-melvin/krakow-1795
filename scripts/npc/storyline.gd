extends Node
## Runs one scripted sequence from data/storylines.json. Created by population.gd.
##
## {"id", "title",
##  "trigger": {"at": "HH:MM"} | {"radius": m, "actor": id}      (time on the world clock, or player within m of actor)
##  "spooked": {"radius": m, "actors": [ids], "goto": label, "until": label}   optional: player interference
##  "steps": [step, ...]}
## Step: {"do": op, "actor": id, "label"?: name, "next"?: label | "end", ...}
##   goto  pos: [x,y,z] | post: name | target: actor (+ keep: m); run?; wait? (default true);
##         secs?: with target+keep, tail the target that long (real seconds); lose?: m, on_lose?: label
##   wait  secs: s | until: "HH:MM" | arrive: [ids]
##   face  pos | target
##   say   text, secs (default 3), wait? (default true), alert?: {guard: name, suspicion: 0..100}
##   play  clip, secs? (blocks that long if given)
## Actor ids: an npc id from data/npcs.json, "player", or "guard:<guard_name>".
## Movement steps claim an NPC from its schedule; all claimed NPCs are released when the storyline ends.

enum Status { WAITING, RUNNING, DONE }

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
	if trig.has("radius"):
		var a := _actor(str(trig.get("actor", "")))
		var p := _player()
		if a and p and a.visible:
			return a.global_position.distance_to(p.global_position) < float(trig["radius"])
	return false


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
	_i = i
	_t = 0.0
	var s: Dictionary = _steps[i]
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
			if s.has("alert"):
				_alert(s["alert"])


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
	g.set("last_known", p.global_position)
	g.set("suspicion", maxf(float(g.get("suspicion")), float(al.get("suspicion", 50.0))))
