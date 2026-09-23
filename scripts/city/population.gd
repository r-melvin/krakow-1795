extends Node
## Spawns the night population of the square from data/npcs.json: townsfolk (npc.gd) and animals (animal.gd),
## then the scripted storylines from data/storylines.json (storyline.gd).
## File: {"posts": {name: {pos: [x,y,z], facing}}, "npcs": [entry, ...]} (a bare array of entries also works).
## Entry: {id, model: "name" | ["candidate", ...], pos: [x,y,z], facing, behaviour, radius?, clip?, role?, kind?,
##         schedule?: [{at?: "HH:MM", post: name, activity: idle|sentry|walk|sit|inside, for: game minutes,
##                      run?: bool, flee_watch?: metres}], follow?: npc id (animals)}
## kind "animal" (or a model name starting dog_/cat/dragon) spawns a static-mesh animal.

const NpcScript := preload("res://scripts/npc/npc.gd")
const AnimalScript := preload("res://scripts/npc/animal.gd")
const StorylineScript := preload("res://scripts/npc/storyline.gd")
const ROSTER := "res://data/npcs.json"
const STORYLINES := "res://data/storylines.json"

var posts: Dictionary = {}        ## name -> {pos: Vector3, facing: float}
var _spawned: Array[Node] = []
var _by_id: Dictionary = {}
var storylines: Array[Node] = []


func _ready() -> void:
	var f := FileAccess.open(ROSTER, FileAccess.READ)
	if f == null:
		push_warning("Population: cannot open %s" % ROSTER)
		return
	var data: Variant = JSON.parse_string(f.get_as_text())
	var entries: Array = []
	if data is Array:
		entries = data
	elif data is Dictionary and (data as Dictionary).has("npcs"):
		entries = data["npcs"]
		var raw_posts: Dictionary = data.get("posts", {})
		for k in raw_posts:
			var pd: Dictionary = raw_posts[k]
			posts[k] = {"pos": _vec(pd.get("pos", [0, 0, 0])), "facing": float(pd.get("facing", 0.0))}
	else:
		push_warning("Population: %s is not a roster" % ROSTER)
		return
	for e in entries:
		if e is Dictionary:
			_spawn(e)
	_load_storylines()


func _load_storylines() -> void:
	var f := FileAccess.open(STORYLINES, FileAccess.READ)
	if f == null:
		return
	var data: Variant = JSON.parse_string(f.get_as_text())
	if not (data is Dictionary and (data as Dictionary).has("storylines")):
		push_warning("Population: %s has no storylines" % STORYLINES)
		return
	for sd in data["storylines"]:
		var s := Node.new()
		s.set_script(StorylineScript)
		s.population = self
		s.data = sd
		s.name = "Story_" + str(sd.get("id", "story"))
		add_child(s)
		storylines.append(s)


static func _vec(p: Array) -> Vector3:
	return Vector3(float(p[0]), float(p[1]), float(p[2]))


func actor(id: String) -> Node3D:
	return _by_id.get(id) as Node3D


func post_pos(name: String) -> Vector3:
	return posts[name]["pos"] if posts.has(name) else Vector3.ZERO


func scheduled_count() -> int:
	var n := 0
	for b in _spawned:
		if "schedule" in b and not (b.schedule as Array).is_empty():
			n += 1
	return n


## Posts that cannot be reached from the open square (the path from `from` ends more than `tol` metres
## short of the post, ignoring height). Needs the navmesh to be baked and synced.
func unreachable_posts(from: Vector3 = Vector3(0, 0, -20), tol: float = 1.5) -> PackedStringArray:
	var out := PackedStringArray()
	var map := get_viewport().world_3d.navigation_map
	for k in posts:
		var p: Vector3 = posts[k]["pos"]
		var path := NavigationServer3D.map_get_path(map, from, p, true)
		var end: Vector3 = path[-1] if path.size() > 0 else from
		if Vector2(end.x - p.x, end.z - p.z).length() > tol:
			out.append("%s(%.1f)" % [k, Vector2(end.x - p.x, end.z - p.z).length()])
	return out


func _resolve_schedule(id: String, raw: Array) -> Array:
	var out: Array = []
	for r in raw:
		if not r is Dictionary:
			continue
		var post := str(r.get("post", ""))
		var pos: Vector3
		var fac := 0.0
		if r.has("pos"):
			pos = _vec(r["pos"])
			fac = float(r.get("facing", 0.0))
		elif posts.has(post):
			pos = posts[post]["pos"]
			fac = float(r.get("facing", posts[post]["facing"]))
		else:
			push_warning("Population: %s schedule names unknown post '%s'" % [id, post])
			continue
		out.append({
			"at": GameState.parse_clock(str(r["at"])) if r.has("at") else -1.0,
			"post": post if post != "" else "%s@%s" % [id, pos],
			"pos": pos,
			"facing": fac,
			"activity": str(r.get("activity", "idle")),
			"for": float(r.get("for", 10.0)),
			"run": bool(r.get("run", false)),
			"flee_watch": float(r.get("flee_watch", 0.0)),
		})
	return out


func _spawn(e: Dictionary) -> void:
	var names := PackedStringArray()
	var m: Variant = e.get("model", "")
	if m is Array:
		for s in m:
			names.append(str(s))
	else:
		names.append(str(m))
	var pos := _vec(e.get("pos", [0, 0, 0]))
	var animal: bool = e.get("kind", "") == "animal"
	if not animal and names.size() > 0:
		var n0 := names[0]
		animal = n0.begins_with("dog_") or n0 == "cat" or n0 == "dragon"

	var body := CharacterBody3D.new()
	body.set_script(AnimalScript if animal else NpcScript)
	body.name = str(e.get("id", "npc"))
	body.npc_id = str(e.get("id", "npc"))
	body.candidates = names
	body.behaviour = str(e.get("behaviour", "stand"))
	body.radius = float(e.get("radius", 3.0 if animal else 4.0))
	body.facing = float(e.get("facing", 0.0))
	body.role = str(e.get("role", ""))
	if e.has("speed"):
		body.speed = float(e["speed"])
	if not animal:
		body.clip = str(e.get("clip", "idle"))
		if e.has("schedule"):
			body.schedule = _resolve_schedule(body.npc_id, e["schedule"])
	elif e.has("follow"):
		body.follow = str(e["follow"])
	body.position = pos
	add_child(body)
	_spawned.append(body)
	_by_id[body.npc_id] = body


func count() -> int:
	return _spawned.size()
