extends Node
## Disguise zones (docs/STEALTH.md 3.7, phase F). One per watch (watch.gd creates it as its child `zones`).
## data/zones.json: named polygons on the Rynek (XZ) plus interior sets, and outfits = disguise permits. The outfit
## worn is the first whose Mission flag is set (the mission can add its own: missions.json `stealth.outfits`); a
## disguised player with no flagged outfit wears the salon cloak; otherwise "none" (street only).
## Trespass: standing in a zone the outfit does not permit. Every guard of the watch gets `sight_factor` in its
## `sight_modifiers` (x trespass.sight there); guard.gd drops the 0.25 disguise factor while the player trespasses,
## goes Curious on sight and Searching after trespass.searching_secs (guard._trespass_react).
## API: current(pos) -> zone id, permitted(player) -> [zone ids], outfit(player) -> id, trespassing(player),
## zone_name(id), polygons(id) (the journal map draws them). A flagged outfit marked "disguised" sets
## player.disguised (e.g. a future `disguise_austrian` flag), so any system can hand out a coat.
## `sandbox`: a test world; `origin` is the sandbox root (polygons are relative to it), `flags` stand in for
## Mission.flags.

const DATA := "res://data/zones.json"

var sandbox := false
var origin := Vector3.ZERO
var flags: Dictionary = {}           ## sandbox stand-in for Mission.flags
var watch: Node
var data: Dictionary = {}
var zones: Dictionary = {}           ## id -> {name, polys: [PackedVector2Array], interiors: [set names], color}
var order: Array = []
var outfits: Dictionary = {}

var _interior_boxes: Dictionary = {} ## zone id -> [Rect2 (XZ)] resolved from the district's interiors
var _interiors_resolved := false
var _cache_frame := -1
var _cache_pos := Vector3.INF
var _cache_zone := "street"
var _hook_cd := 0.0

static var _db: Dictionary = {}


static func db() -> Dictionary:
	if _db.is_empty():
		var f := FileAccess.open(DATA, FileAccess.READ)
		var d: Variant = JSON.parse_string(f.get_as_text()) if f else null
		if d is Dictionary:
			_db = d
	return _db


func _ready() -> void:
	add_to_group("stealth_zones")
	data = db()
	order = data.get("order", ["street"])
	for id in data.get("zones", {}):
		var z: Dictionary = data["zones"][id]
		var polys: Array = []
		for poly in z.get("polygons", []):
			var pv := PackedVector2Array()
			for pt in poly:
				pv.append(Vector2(float(pt[0]), float(pt[1])))
			polys.append(pv)
		var c: Array = z.get("color", [0.7, 0.7, 0.7])
		zones[id] = {"name": str(z.get("name", id)), "polys": polys, "interiors": z.get("interiors", []),
				"color": Color(float(c[0]), float(c[1]), float(c[2]))}
	outfits = (data.get("outfits", {}) as Dictionary).duplicate(true)
	if not sandbox and Mission.is_active():
		var mo: Dictionary = Mission.data.get("stealth", {}).get("outfits", {})
		for id in mo:
			outfits[id] = mo[id]


func _flags() -> Dictionary:
	return flags if sandbox else Mission.flags


func _physics_process(delta: float) -> void:
	_hook_cd -= delta
	if _hook_cd > 0.0:
		return
	_hook_cd = 0.5
	hook_guards()
	if sandbox:
		return
	# a flagged outfit that disguises (an Austrian coat, a cassock) puts the player in it, whoever set the flag
	var p: Node3D = watch.get_player() if watch else null
	if p and not p.disguised:
		var o := outfit(p)
		if o != "none" and bool(outfits.get(o, {}).get("disguised", false)) and _flags().has(str(outfits[o].get("flag", ""))):
			p.disguised = true


## Adds the trespass sight modifier to every guard of the watch (once each).
func hook_guards() -> void:
	if watch == null:
		return
	for g in watch.guards():
		if not g.has_meta("zones_hooked"):
			g.set_meta("zones_hooked", true)
			g.sight_modifiers.append(sight_factor)


# ------------------------------------------------------------------ queries

## The zone id at `pos` (world space): the first zone in `order` containing it, else "street".
func current(pos: Vector3) -> String:
	var f := Engine.get_physics_frames()
	if f == _cache_frame and pos.distance_squared_to(_cache_pos) < 0.0001:
		return _cache_zone
	var p := pos - origin
	var out := "street"
	for id in order:
		if id == "street":
			continue
		if contains(str(id), p):
			out = str(id)
			break
	_cache_frame = f
	_cache_pos = pos
	_cache_zone = out
	return out


## True if the local point `p` (relative to `origin`) lies in zone `id`.
func contains(id: String, p: Vector3) -> bool:
	var z: Dictionary = zones.get(id, {})
	if z.is_empty():
		return false
	if p.y < -50.0:
		_resolve_interiors()
		for r in _interior_boxes.get(id, []):
			if (r as Rect2).has_point(Vector2(p.x, p.z)):
				return true
		return false
	var v := Vector2(p.x, p.z)
	for poly in z["polys"]:
		if Geometry2D.is_point_in_polygon(v, poly):
			return true
	return false


func _resolve_interiors() -> void:
	if _interiors_resolved or watch == null or not watch.is_inside_tree():
		return
	var district: Node = watch.get_parent()
	var ints: Node = district.get_node_or_null("Interiors") if district else null
	if ints == null or not ints.has_method("interior_origin"):
		return
	_interiors_resolved = true
	for id in zones:
		var boxes: Array = []
		for s in zones[id]["interiors"]:
			var o: Vector3 = ints.interior_origin(str(s))
			if o != Vector3.INF:
				boxes.append(Rect2(o.x - 13.0, o.z - 26.0, 26.0, 28.0))
		_interior_boxes[id] = boxes


## The outfit the player wears now (outfits key).
func outfit(player: Node = null) -> String:
	var fl := _flags()
	var cloak := ""
	for id in outfits:
		if id == "none":
			continue
		var f := str(outfits[id].get("flag", ""))
		if f != "" and fl.has(f) and fl[f]:
			return str(id)
		if cloak == "" and bool(outfits[id].get("disguised", false)) and id == "salon_cloak":
			cloak = str(id)
	if player and player.get("disguised"):
		return cloak if cloak != "" else "salon_cloak"
	return "none"


func outfit_name(id: String) -> String:
	return str(outfits.get(id, {}).get("name", id))


## Zones the player's outfit lets them stand in.
func permitted(player: Node = null) -> Array:
	if player == null and watch:
		player = watch.get_player()
	return outfits.get(outfit(player), {}).get("permit", ["street"])


func trespassing(player: Node3D) -> bool:
	if player == null:
		return false
	return not permitted(player).has(current(player.global_position))


## Sight modifier for guard.sight_modifiers: x trespass.sight while the player trespasses.
func sight_factor(_guard: Node, player: Node) -> float:
	var p := player as Node3D
	return float(data.get("trespass", {}).get("sight", 1.6)) if trespassing(p) else 1.0


func tset(key: String, fallback: float) -> float:
	return float(data.get("trespass", {}).get(key, fallback))


func zone_name(id: String) -> String:
	return str(zones.get(id, {}).get("name", id.capitalize()))


func zone_color(id: String) -> Color:
	return zones.get(id, {}).get("color", Color(0.7, 0.7, 0.7))


## [PackedVector2Array] of zone `id` (district coordinates), for the journal map.
func polygons(id: String) -> Array:
	return zones.get(id, {}).get("polys", [])


## A bark line from zones.json `barks.<kind>`: "text\n(gloss)".
static func bark_text(kind: String) -> String:
	var list: Array = db().get("barks", {}).get(kind, [])
	if list.is_empty():
		return ""
	var e: Variant = list[randi() % list.size()]
	if e is Array and (e as Array).size() >= 2:
		return "%s\n(%s)" % [e[0], e[1]]
	return str(e)
