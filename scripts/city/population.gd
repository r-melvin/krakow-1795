extends Node
## Spawns the night population of the square from data/npcs.json: townsfolk (npc.gd) and animals (animal.gd),
## then the scripted storylines from data/storylines.json (storyline.gd).
## File: {"posts": {name: {pos: [x,y,z], facing}}, "npcs": [entry, ...]} (a bare array of entries also works).
## Entry: {id, model: "name" | ["candidate", ...], pos: [x,y,z], facing, behaviour, radius?, clip?, role?, kind?,
##         schedule?: [{at?: "HH:MM", post: name, activity: idle|sentry|walk|sit|inside, for: game minutes,
##                      run?: bool, flee_watch?: metres}], follow?: npc id (animals), tether?: bool (animals),
##         route?: [post name | [x,y,z], ...], route_start?: index (vehicles)}
## kind "animal" (or an animal model name, see ANIMAL_MODELS) spawns an animal (scripts/npc/animal.gd);
## kind "vehicle" (behaviour "drive") spawns a horse-drawn carriage or cart that drives its route loop.

const NpcScript := preload("res://scripts/npc/npc.gd")
const AnimalScript := preload("res://scripts/npc/animal.gd")
const StorylineScript := preload("res://scripts/npc/storyline.gd")
const ROSTER := "res://data/npcs.json"
const STORYLINES := "res://data/storylines.json"
const ANIMAL_MODELS := ["dog_", "cat", "dragon", "horse", "pigeon", "crow", "hawk", "goat", "goose", "pig", "carriage"]

var posts: Dictionary = {}        ## name -> {pos: Vector3, facing: float}
var _spawned: Array[Node] = []
var _by_id: Dictionary = {}
var storylines: Array[Node] = []
var _smoke := false
var _smoke_t := 0.0
static var _shots_done := false


func _ready() -> void:
	add_to_group("population")
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
	_smoke = "--smoke" in OS.get_cmdline_user_args()
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--shot=") and not _shots_done:
			_shots_done = true          # first night only: later nights belong to the mission smoke
			_vehicle_shots.call_deferred(arg.trim_prefix("--shot="))


func _load_storylines() -> void:
	var f := FileAccess.open(STORYLINES, FileAccess.READ)
	if f == null:
		return
	var data: Variant = JSON.parse_string(f.get_as_text())
	if not (data is Dictionary and (data as Dictionary).has("storylines")):
		push_warning("Population: %s has no storylines" % STORYLINES)
		return
	for sd in data["storylines"]:
		add_storyline(sd)


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
	var kind := str(e.get("kind", ""))
	var animal: bool = kind == "animal" or kind == "vehicle"
	if not animal and names.size() > 0:
		for prefix in ANIMAL_MODELS:
			if names[0].begins_with(prefix):
				animal = true

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
	else:
		if e.has("follow"):
			body.follow = str(e["follow"])
		body.tether = bool(e.get("tether", false))
		if e.has("route"):
			body.route = _resolve_route(body.npc_id, e["route"])
			body.route_start = int(e.get("route_start", 0))
	body.position = pos
	add_child(body)
	_spawned.append(body)
	_by_id[body.npc_id] = body


func _resolve_route(id: String, raw: Array) -> Array:
	var out: Array = []
	for r in raw:
		if r is Array:
			out.append(_vec(r))
		elif posts.has(str(r)):
			out.append(posts[str(r)]["pos"])
		else:
			push_warning("Population: %s route names unknown post '%s'" % [id, r])
	return out


## Smoke runs: report where the vehicles are every 2 s, so the log shows them moving.
func _physics_process(delta: float) -> void:
	if not _smoke:
		return
	_smoke_t += delta
	if _smoke_t < 2.0:
		return
	_smoke_t = 0.0
	for v in get_tree().get_nodes_in_group("vehicles"):
		if v.get_parent() == self:
			var p: Vector3 = v.vehicle_position()
			print("[smoke] %s at (%.1f, %.1f) speed=%.2f" % [v.npc_id, p.x, p.z, v._drive_speed])


## Shot mode (`-- --smoke --shot=/dir`): two close-ups of the carriage two seconds apart (to show it moving),
## and one of the tethered horse, taken early in the first night before main.gd's own screenshots.
func _vehicle_shots(dir: String) -> void:
	for i in 60:
		await get_tree().physics_frame
	var cam := Camera3D.new()
	add_child(cam)
	var prev := get_viewport().get_camera_3d()
	for k in 2:
		var v := actor("dorozka")
		if v:
			var p: Vector3 = v.global_position
			var fwd := -v.global_transform.basis.z
			var side := v.global_transform.basis.x
			cam.look_at_from_position(p + fwd * 5.0 - side * 5.5 + Vector3(0, 2.4, 0), p - fwd * 2.0 + Vector3(0, 1.0, 0))
			cam.current = true
			for i in 3:
				await get_tree().process_frame
			get_viewport().get_texture().get_image().save_png(dir + "/shot_carriage_%d.png" % k)
			print("[smoke] carriage shot %d at %s" % [k, v.vehicle_position()])
		if prev:
			prev.current = true
		for i in 120:
			await get_tree().physics_frame
	var h := actor("inn_horse")
	if h:
		cam.look_at_from_position(h.global_position + Vector3(3.5, 1.9, 3.5), h.global_position + Vector3(0, 0.9, 0))
		cam.current = true
		for i in 3:
			await get_tree().process_frame
		get_viewport().get_texture().get_image().save_png(dir + "/shot_inn_horse.png")
	for n in [["pigeon_a", Vector3(1.8, 1.0, 1.8)], ["vizsla", Vector3(2.0, 1.2, 2.0)]]:
		var a := actor(n[0])
		if a:
			cam.look_at_from_position(a.global_position + n[1], a.global_position + Vector3(0, 0.25, 0))
			cam.current = true
			for i in 3:
				await get_tree().process_frame
			get_viewport().get_texture().get_image().save_png(dir + "/shot_%s.png" % n[0])
	if prev and is_instance_valid(prev):
		prev.current = true
	cam.queue_free()


func count() -> int:
	return _spawned.size()


## Stealth crowd query (player.gd crowd blending): townsfolk within `radius` m of `point` who are out in the street,
## awake, and standing still or walking the same way as `dir` (dot > 0.5). `dir` ZERO counts every one near.
func crowd_count(point: Vector3, dir: Vector3 = Vector3.ZERO, radius: float = 2.5) -> int:
	var n := 0
	var d2 := Vector2(dir.x, dir.z)
	for b in _spawned:
		if not is_instance_valid(b) or b.get_script() != NpcScript:
			continue
		var npc := b as CharacterBody3D
		if npc.is_inside() or npc.is_downed() or not npc.visible:
			continue
		var off := Vector2(npc.global_position.x - point.x, npc.global_position.z - point.z)
		if off.length() > radius or absf(npc.global_position.y - point.y) > 2.0:
			continue
		var v := Vector2(npc.velocity.x, npc.velocity.z)
		if d2.length() > 0.1 and v.length() > 0.3 and v.normalized().dot(d2.normalized()) < 0.5:
			continue
		n += 1
	return n


## Mission hook: spawn one roster entry (same format as data/npcs.json). An entry whose id already exists
## replaces that NPC (the old one is freed); returns the new body.
func spawn_entry(e: Dictionary) -> Node3D:
	var id := str(e.get("id", "npc"))
	var old: Node = _by_id.get(id)
	if old and is_instance_valid(old):
		_spawned.erase(old)
		old.name = id + "_old"
		old.queue_free()
	_spawn(e)
	return _by_id.get(id) as Node3D


## Mission hook: run one more storyline (same format as data/storylines.json entries).
func add_storyline(sd: Dictionary) -> Node:
	var s := Node.new()
	s.set_script(StorylineScript)
	s.population = self
	s.data = sd
	s.name = "Story_" + str(sd.get("id", "story"))
	add_child(s)
	storylines.append(s)
	return s


func storyline(id: String) -> Node:
	for s in storylines:
		if is_instance_valid(s) and s.story_id == id:
			return s
	return null
