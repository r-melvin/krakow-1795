extends Node3D
## Interior rooms and the doors that lead to them.
## A room is a set (shell family: shop, workshop, tavern, cellar, flat, salon, church, chapel, guard, house, bath,
## store) dressed as a variant (the trade), built by assets/blender/build_interiors.py as `<set>_<variant>.glb`
## (or `<set>.glb` for an undressed variant ""). data/interiors.json says which door gets which room:
##   portals   - the tenement doors round the Rynek by portal index (the district's `portals` order),
##   landmarks - fixed doors on the square (St Mary's, the Town Hall tower, the Cloth Hall passage, St Adalbert's),
##   buildings - doors on the outer city's buildings, by asset name in data/city_layout.json and a module-space
##               offset (Godot metres, before the placement's scale and turn),
##   rooms     - per room: title, floor surface, prop metas, extra exits, notes on the Post_<n> markers.
## Each room used by a door has a slot far below the map on a grid, shared by every door mapped to it. The room is
## instanced the first time it is needed (the player goes in, or a script asks for its node or posts) and then stays;
## `always` rooms (the mission's salon) are instanced up front. Every room carries its own copies of the baked
## textures, so loading all of them at once costs gigabytes of VRAM. A room's origin is the outside of its front
## door; the room extends toward -Z. Rooms stay hidden (meshes and lights) until the player is inside one.
## Doors are Area3D triggers in front of the portals. Overlap + `interact`, or walking into the door, fades out,
## stores the return point and drops the player just inside; the exit trigger in the doorway inside (or an
## `Exit_<id>` marker: the kingpin's boat, the bathhouse back door) sends them back out.
##
## `-- --interior-shot=DIR[:room,room]` (needs a window) saves a view of every room (or the listed ones).

const FlickerLight := preload("res://scripts/city/flicker.gd")
const DATA := "res://data/interiors.json"
const LAYOUT := "res://data/city_layout.json"
const DEPTH := -200.0
const SPACING := 45.0
const COLS := 6
const TENEMENT_DOOR_X := {"tenement_b": -2.0, "tenement_e": -2.0}   ## door offset where it is not centred
const TENEMENT_FRONT := 4.0          ## half the tenement depth: facade plane in module space
const SPAWN_IN := 1.8                ## metres inside the door where the player lands
const LAMPS := {                     ## kind -> [colour, energy, range, shadow, flicker amount]
	"lantern": [Color(1.0, 0.68, 0.36), 2.6, 7.5, true, 0.08],
	"fire": [Color(1.0, 0.52, 0.22), 3.2, 8.0, true, 0.22],
	"candle": [Color(1.0, 0.72, 0.42), 0.9, 4.0, false, 0.12],
	"chandelier": [Color(1.0, 0.74, 0.46), 4.0, 12.0, true, 0.06],
	"window": [Color(1.0, 0.70, 0.45), 1.0, 3.5, false, 0.0],
	"stove": [Color(1.0, 0.50, 0.22), 1.4, 4.5, false, 0.18],
	"oven": [Color(1.0, 0.46, 0.18), 3.0, 7.0, true, 0.2],
	"forge": [Color(1.0, 0.42, 0.14), 3.8, 9.0, true, 0.25],
	"moon": [Color(0.55, 0.66, 1.0), 0.6, 4.5, false, 0.0],
}

var portals: Array = []

static var _smoked := false

var data: Dictionary = {}
var _rooms := {}                     ## room key -> {"origin": Vector3, "node": Node3D or null, "set", "variant", "pinned"}
var _doors: Array[Area3D] = []
var _exits: Array[Area3D] = []
var _near: Array[Area3D] = []        ## triggers the player overlaps right now
var _return := {}                    ## {"pos": Vector3, "yaw": float} for the door we came through
var _frame: Variant = null           ## Transform3D of the building whose door we came through (exits `at`)
var _inside := ""                    ## room key the player is in, "" outside
var _busy := false
var _cooldown := 0.0
var _fade: ColorRect
var _prompt: Label


func _ready() -> void:
	name = "Interiors"
	data = _read_json(DATA)
	var doors := _door_specs()
	# one instance per room that some door leads to (plus any the mission names), laid out on a grid below the map
	var keys: Array = []
	for d in doors:
		if not keys.has(d["room"]):
			keys.append(d["room"])
	for k in data.get("always", []):
		if not keys.has(k):
			keys.append(k)
	for i in keys.size():
		_add_room(keys[i], i)
	for k in data.get("always", []):
		_load(str(k), true)
	for d in doors:
		_door(d["id"], d["pos"], d["rot"], d["room"], d["auto"], d["size"])
		if d.has("frame") and not _doors.is_empty() and String(_doors.back().name) == d["id"]:
			_doors.back().set_meta("frame", d["frame"])
	_build_ui()
	var shot := _arg("--interior-shot=")
	if shot != "":
		_interior_shots.call_deferred(shot)
	if "--smoke" in OS.get_cmdline_user_args() and not _smoked:
		_smoked = true       # only the first night's world: later nights belong to the mission smoke
		var sets := {}
		var variants := {}
		for k in _rooms:
			sets[_rooms[k]["set"]] = true
			variants[k] = true
		print("[smoke] interiors=%d doors=%d" % [_rooms.size(), _doors.size()])
		print("[smoke] interiors sets=%d doors=%d variants=%d" % [sets.size(), _doors.size(), variants.size()])
		_smoke.call_deferred()


static func _read_json(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_warning("Interiors: cannot read %s" % path)
		return {}
	var d: Variant = JSON.parse_string(f.get_as_text())
	return d if d is Dictionary else {}


static func room_key(set_name: String, variant: String) -> String:
	return set_name if variant == "" else "%s_%s" % [set_name, variant]


# ------------------------------------------------------------------ rooms
func _add_room(key: String, i: int) -> void:
	if not ResourceLoader.exists("res://assets/models/%s.glb" % key):
		push_warning("Interiors: no model for room %s" % key)
		return
	var origin := Vector3((i % COLS - COLS * 0.5) * SPACING, DEPTH, float(i / COLS) * SPACING)
	var set_name: String = key
	var variant := ""
	for s in data.get("sets", []):
		if key == s or key.begins_with(str(s) + "_"):
			set_name = s
			variant = key.trim_prefix(str(s)).trim_prefix("_")
	_rooms[key] = {"origin": origin, "node": null, "set": set_name, "variant": variant, "pinned": false}
	_exits.append(_trigger("exit_" + key, origin + Vector3(0, 1.1, -0.5), Vector3(2.6, 2.2, 0.9), 0.0,
			{"room": key, "exit": true, "auto": true, "dest": ""}))


## Instance a room if it is not yet (pinned: a script holds on to it, never unloaded by the screenshot pass).
func _load(key: String, pin := false) -> Node3D:
	if not _rooms.has(key):
		return null
	var r: Dictionary = _rooms[key]
	r["pinned"] = r["pinned"] or pin
	if r["node"] != null:
		return r["node"]
	var inst := Assets.place(self, key, r["origin"], 0.0)
	if inst == null:
		return null
	inst.name = key
	var info: Dictionary = data.get("rooms", {}).get(key, {})
	inst.set_meta("set", r["set"])
	inst.set_meta("variant", r["variant"])
	inst.set_meta("surface", str(info.get("floor", "planks")))
	_rigs(inst, info)
	inst.visible = key == _inside
	r["node"] = inst
	return inst


func _unload(key: String) -> void:
	var r: Dictionary = _rooms.get(key, {})
	if r.is_empty() or r["node"] == null or r["pinned"] or key == _inside:
		return
	for a in _exits.duplicate():
		if a.get_meta("room") == key and str(a.get_meta("dest")) != "":
			_exits.erase(a)
			a.queue_free()
	(r["node"] as Node3D).queue_free()
	r["node"] = null


## Lights on the lamp_ empties, surface metas on the floors, metas on named props, particles, extra exits.
func _rigs(inst: Node3D, info: Dictionary) -> void:
	var floor_kind: String = str(info.get("floor", "planks"))
	var props: Dictionary = info.get("props", {})
	for n in inst.find_children("*", "", true, false):
		var nm := String(n.name)
		if n is StaticBody3D:
			n.set_meta("surface", nm.trim_prefix("surf_").get_slice("-", 0) if nm.begins_with("surf_") else floor_kind)
			if info.get("wet", false):
				n.set_meta("wet", true)
		elif nm.begins_with("lamp_") and n is Node3D:
			_lamp(n, nm.get_slice("_", 1))
		elif nm.begins_with("fx_") and n is Node3D:
			n.add_child(_particles(nm.get_slice("_", 1)))
		elif nm.begins_with("Exit_") and n is Node3D:
			var id := nm.trim_prefix("Exit_")
			var a := _trigger("exit_%s_%s" % [inst.name, id], (n as Node3D).global_position + Vector3(0, 1.1, 0),
					Vector3(1.6, 2.2, 1.2), (n as Node3D).global_rotation.y, {"room": String(inst.name), "exit": true, "auto": false, "dest": id})
			_exits.append(a)
		for key in props:
			if nm.begins_with(key):
				var m: Dictionary = props[key]
				for mk in m:
					n.set_meta(mk, m[mk])
				n.add_to_group("interior_props")


func _lamp(n: Node3D, kind: String) -> void:
	var cfg: Array = LAMPS.get(kind, LAMPS["candle"])
	var l := OmniLight3D.new()
	if float(cfg[4]) > 0.0:
		l.set_script(FlickerLight)
		l.set("amount", cfg[4])
		l.set("speed", 4.0 if kind == "candle" else 7.0)
	l.light_color = cfg[0]
	l.light_energy = cfg[1]
	l.omni_range = cfg[2]
	l.omni_attenuation = 1.2
	l.shadow_enabled = cfg[3]
	l.light_specular = 0.4
	n.add_child(l)


## Tobacco haze over the card table, steam off the bathhouse stones, drips in the kingpin's tunnel.
func _particles(kind: String) -> CPUParticles3D:
	var p := CPUParticles3D.new()
	p.name = "fx_" + kind
	var q := QuadMesh.new()
	var mat := StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	mat.vertex_color_use_as_albedo = true
	p.emission_shape = CPUParticles3D.EMISSION_SHAPE_BOX
	match kind:
		"drip":
			var s := SphereMesh.new()
			s.radius = 0.012
			s.height = 0.03
			var dm := StandardMaterial3D.new()
			dm.albedo_color = Color(0.5, 0.6, 0.7)
			dm.roughness = 0.05
			s.material = dm
			p.mesh = s
			p.amount = 3
			p.lifetime = 1.4
			p.emission_box_extents = Vector3(0.3, 0.02, 0.6)
			p.gravity = Vector3(0, -9.8, 0)
			p.initial_velocity_min = 0.0
			p.initial_velocity_max = 0.0
			return p
		"steam":
			q.size = Vector2(0.9, 0.9)
			p.amount = 28
			p.lifetime = 4.0
			p.emission_box_extents = Vector3(0.5, 0.1, 0.4)
			p.gravity = Vector3(0, 0.25, 0)
			p.initial_velocity_min = 0.15
			p.initial_velocity_max = 0.4
			p.color = Color(0.92, 0.92, 0.95, 0.10)
		_:
			q.size = Vector2(1.2, 0.7)
			p.amount = 16
			p.lifetime = 9.0
			p.emission_box_extents = Vector3(0.8, 0.15, 0.6)
			p.gravity = Vector3(0, 0.02, 0)
			p.initial_velocity_min = 0.02
			p.initial_velocity_max = 0.08
			p.color = Color(0.72, 0.70, 0.66, 0.06)
	q.material = mat
	p.mesh = q
	p.direction = Vector3.UP
	p.spread = 35.0
	p.scale_amount_min = 0.8
	p.scale_amount_max = 2.0
	var ramp := Gradient.new()
	ramp.set_color(0, Color(1, 1, 1, 0))
	ramp.add_point(0.25, Color(1, 1, 1, 1))
	ramp.set_color(ramp.get_point_count() - 1, Color(1, 1, 1, 0))
	p.color_ramp = ramp
	return p


func _show(key: String) -> void:
	if _inside != "" and _rooms.has(_inside) and _rooms[_inside]["node"] != null:
		(_rooms[_inside]["node"] as Node3D).visible = false
	_inside = key
	if key != "" and _rooms.has(key):
		var n := _load(key)
		if n:
			n.visible = true


# ------------------------------------------------------------------ doors
## Every door in data/interiors.json resolved to {id, pos, rot, room, auto, size}.
func _door_specs() -> Array:
	var out: Array = []
	var by_portal := {}
	for e in data.get("portals", []):
		by_portal[int(e["portal"])] = e
	var cycle: Array = data.get("cycle", [])
	for k in portals.size():
		var p: Array = portals[k]
		var asset: String = p[0]
		var b := Basis(Vector3.UP, float(p[2]))
		var e: Dictionary = by_portal.get(k, {})
		var room := ""
		if not e.is_empty():
			room = room_key(str(e["set"]), str(e.get("variant", "")))
		elif not cycle.is_empty():
			room = str(cycle[k % cycle.size()])
		if room == "":
			continue
		var pos: Vector3 = (p[1] as Vector3) + b * Vector3(TENEMENT_DOOR_X.get(asset, 0.0), 0, TENEMENT_FRONT + 0.8)
		out.append({"id": "door_%s_%d" % [asset, k], "pos": pos, "rot": float(p[2]), "room": room, "auto": true,
				"size": Vector3(1.8, 2.4, 1.2)})
	for e in data.get("landmarks", []):
		var at: Array = e["pos"]
		out.append({"id": str(e["id"]), "pos": Vector3(float(at[0]), 0, float(at[1])), "rot": float(e.get("rot", 0.0)),
				"room": room_key(str(e["set"]), str(e.get("variant", ""))), "auto": bool(e.get("auto", true)),
				"size": _v3(e.get("size", [1.8, 2.4, 1.2]))})
	var placed := {}
	for pl in _read_json(LAYOUT).get("place", []):
		var a := str(pl.get("a", ""))
		if not placed.has(a):
			placed[a] = []
		placed[a].append(pl)
	for e in data.get("buildings", []):
		var list: Array = placed.get(str(e["asset"]), [])
		for i in list.size():
			var pl: Dictionary = list[i]
			var pp: Array = pl["p"]
			var r := float(pl.get("r", 0.0))
			var s := float(pl.get("s", 1.0))
			var at: Array = e["at"]
			var pos := Vector3(float(pp[0]), 0, float(pp[1])) + Basis(Vector3.UP, r) * (Vector3(float(at[0]), 0, float(at[1])) * s)
			out.append({"id": str(e["id"]) + ("" if i == 0 else "_%d" % i), "pos": pos, "rot": r + float(e.get("facing", 0.0)),
					"room": room_key(str(e["set"]), str(e.get("variant", ""))), "auto": bool(e.get("auto", true)),
					"size": _v3(e.get("size", [1.8, 2.4, 1.2])),
					"frame": Transform3D(Basis(Vector3.UP, r).scaled(Vector3.ONE * s), Vector3(float(pp[0]), 0, float(pp[1])))})
	return out


static func _v3(a: Array) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2]))


## rot_y is the facade's facing (0 = the door looks toward +Z). auto: walking into it enters without `interact`.
func _door(id: String, pos: Vector3, rot_y: float, room: String, auto: bool, size := Vector3(1.8, 2.4, 1.2)) -> void:
	if not _rooms.has(room):
		return
	_doors.append(_trigger(id, pos + Vector3(0, size.y * 0.5, 0), size, rot_y, {"room": room, "exit": false, "auto": auto, "dest": ""}))


func _trigger(id: String, pos: Vector3, size: Vector3, rot_y: float, meta: Dictionary) -> Area3D:
	var a := Area3D.new()
	a.name = id
	a.position = pos
	a.rotation.y = rot_y
	a.monitorable = false
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = size
	cs.shape = bs
	a.add_child(cs)
	for key in meta:
		a.set_meta(key, meta[key])
	a.set_meta("set", meta["room"])            # older callers read "set"
	a.body_entered.connect(_on_trigger_entered.bind(a))
	a.body_exited.connect(_on_trigger_exited.bind(a))
	add_child(a)
	return a


func _on_trigger_entered(body: Node3D, a: Area3D) -> void:
	if body.is_in_group("player") and not _near.has(a):
		_near.append(a)


func _on_trigger_exited(body: Node3D, a: Area3D) -> void:
	if body.is_in_group("player"):
		_near.erase(a)


func _physics_process(delta: float) -> void:
	_cooldown = maxf(0.0, _cooldown - delta)
	var player := get_tree().get_first_node_in_group("player") as CharacterBody3D
	# A mission interactable in reach, or a conversation, takes the `interact` key and the prompt.
	var busy_elsewhere: bool = Mission.dialogue_blocking() or (player != null and player.get("interact_target") != null)
	if player == null or _near.is_empty() or busy_elsewhere:
		if _prompt:
			_prompt.visible = false
		return
	var a: Area3D = _near.back()
	var exiting: bool = a.get_meta("exit")
	if exiting:
		_prompt.text = "E  leave" if str(a.get_meta("dest")) == "" else "E  %s" % _exit_title(a)
	else:
		_prompt.text = "E  enter the %s" % title(str(a.get_meta("room")))
	_prompt.visible = not _busy
	if _busy or _cooldown > 0.0:
		return
	# Walking into the door counts: movement input pointing through the door (toward -Z of the trigger, i.e. into
	# the facade; for exits toward +Z, out through the front door). Input, not velocity: sliding against the
	# facade cancels the velocity component into it.
	var into := a.global_transform.basis.z * (1.0 if exiting else -1.0)
	var pushing: bool = a.get_meta("auto") and _wish().dot(Vector2(into.x, into.z)) > 0.5
	if Input.is_action_just_pressed("interact") or pushing:
		if exiting:
			_go_out(player, a)
		else:
			_go_in(player, a)


func title(room: String) -> String:
	return str(data.get("rooms", {}).get(room, {}).get("title", "building"))


func _exit_title(a: Area3D) -> String:
	var ex: Dictionary = data.get("rooms", {}).get(str(a.get_meta("room")), {}).get("exits", {}).get(str(a.get_meta("dest")), {})
	return str(ex.get("prompt", "leave"))


## Movement input on the ground plane, relative to the active camera (same mapping as player.gd).
func _wish() -> Vector2:
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return Vector2.ZERO
	var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var f := -cam.global_transform.basis.z
	var r := cam.global_transform.basis.x
	var w := Vector2(f.x, f.z).normalized() * -input.y + Vector2(r.x, r.z).normalized() * input.x
	return w


func _go_in(player: CharacterBody3D, door: Area3D) -> void:
	_frame = door.get_meta("frame") if door.has_meta("frame") else null
	var out := door.global_transform.basis.z
	_return = {"pos": Vector3(door.global_position.x, 0.1, door.global_position.z) + out * 0.9, "yaw": atan2(-out.x, -out.z)}
	var key := str(door.get_meta("room"))
	_show(key)
	_teleport(player, (_rooms[key]["origin"] as Vector3) + Vector3(0, 0.05, -SPAWN_IN), 0.0)


func _go_out(player: CharacterBody3D, a: Area3D = null) -> void:
	var dest := _destination(a)
	if dest.is_empty():
		if _return.is_empty():
			_return = {"pos": get_parent().call("player_spawn") if get_parent().has_method("player_spawn") else Vector3(0, 0.2, 0), "yaw": 0.0}
		dest = _return
	_teleport(player, dest["pos"], dest["yaw"])
	_return = {}
	_show("")


## A named exit's world destination from data/interiors.json (rooms.<key>.exits.<id>.pos), or {} for the way in.
func _destination(a: Area3D) -> Dictionary:
	if a == null or str(a.get_meta("dest", "")) == "":
		return {}
	var ex: Dictionary = data.get("rooms", {}).get(str(a.get_meta("room")), {}).get("exits", {}).get(str(a.get_meta("dest")), {})
	var pos: Variant = ex.get("pos", null)
	if pos is Array and (pos as Array).size() >= 2:
		return {"pos": Vector3(float(pos[0]), 0.2, float(pos[1])), "yaw": float(ex.get("yaw", 0.0))}
	var at: Variant = ex.get("at", null)
	if at is Array and (at as Array).size() >= 2 and _frame is Transform3D:
		var f: Transform3D = _frame
		var w := f * Vector3(float(at[0]), 0.0, float(at[1]))
		var fwd := f.basis.z.normalized()
		return {"pos": Vector3(w.x, 0.2, w.z), "yaw": atan2(fwd.x, fwd.z) + float(ex.get("yaw", 0.0))}
	return {}


func _teleport(player: CharacterBody3D, pos: Vector3, yaw: float, fade := true) -> void:
	_busy = true
	_near.clear()
	if fade:
		var tw := create_tween()
		tw.tween_property(_fade, "color:a", 1.0, 0.22)
		await tw.finished
	player.global_position = pos
	player.velocity = Vector3.ZERO
	if player.has_method("rotate_camera"):
		player.call("rotate_camera", Vector3(-0.2, yaw, 0))
	player.reset_physics_interpolation()
	if fade:
		await get_tree().physics_frame
		var tw2 := create_tween()
		tw2.tween_property(_fade, "color:a", 0.0, 0.35)
	_cooldown = 0.8
	_busy = false


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 50
	add_child(layer)
	_fade = ColorRect.new()
	_fade.color = Color(0, 0, 0, 0)
	_fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_fade.set_anchors_preset(Control.PRESET_FULL_RECT)
	layer.add_child(_fade)
	_prompt = Label.new()
	_prompt.visible = false
	_prompt.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_prompt.position += Vector2(-80, -90)
	_prompt.add_theme_font_size_override("font_size", 20)
	_prompt.add_theme_color_override("font_outline_color", Color.BLACK)
	_prompt.add_theme_constant_override("outline_size", 6)
	layer.add_child(_prompt)


# ------------------------------------------------------------------ API for the mission, population and campaign
## Origin (outside of the front door) of a room, by key ("int_shop_baker") or by set ("int_salon": the first room
## of that set), or Vector3.INF if it was not built.
func interior_origin(name_or_set: String) -> Vector3:
	var k := _resolve(name_or_set)
	return _rooms[k]["origin"] if k != "" else Vector3.INF


func _resolve(name_or_set: String) -> String:
	if _rooms.has(name_or_set):
		return name_or_set
	for k in _rooms:
		if _rooms[k]["set"] == name_or_set:
			return k
	return ""


## The room's node (its Post_<n> markers, `ledger`, `decanter` etc. are under it), instanced on demand and kept, or
## null.
func room_node(name_or_set: String) -> Node3D:
	var k := _resolve(name_or_set)
	return _load(k, true) if k != "" else null


## Every room key that some door leads to.
func room_keys() -> Array:
	return _rooms.keys()


## The Post_<n> markers of a room, in order: where NPCs should stand or sit (their -Z is the facing).
func post_markers(name_or_set: String) -> Array[Node3D]:
	var out: Array[Node3D] = []
	var n := room_node(name_or_set)
	if n == null:
		return out
	for c in n.find_children("Post_*", "", true, false):
		out.append(c as Node3D)
	out.sort_custom(func(a: Node3D, b: Node3D) -> bool: return String(a.name).naturalnocasecmp_to(String(b.name)) < 0)
	return out


## Room key a door leads to ("" if no such door).
func door_room(door_name: String) -> String:
	var d := find_door(door_name)
	return str(d.get_meta("room")) if d else ""


## Room key the player is in, "" outside.
func inside() -> String:
	return _inside


## Named door trigger (e.g. "door_town_hall"), or null.
func find_door(door_name: String) -> Area3D:
	for d in _doors:
		if String(d.name) == door_name:
			return d
	return null


## Go through a door at once, no fade (mission scripting and smoke tests).
func enter_now(player: CharacterBody3D, door_name: String) -> bool:
	var d := find_door(door_name)
	if d == null:
		return false
	_go_in_now(player, d)
	player.reset_physics_interpolation()
	return true


func _go_in_now(player: CharacterBody3D, door: Area3D) -> void:
	_frame = door.get_meta("frame") if door.has_meta("frame") else null
	var out := door.global_transform.basis.z
	_return = {"pos": Vector3(door.global_position.x, 0.1, door.global_position.z) + out * 0.9, "yaw": atan2(-out.x, -out.z)}
	var key := str(door.get_meta("room"))
	_show(key)
	player.global_position = (_rooms[key]["origin"] as Vector3) + Vector3(0, 0.05, -SPAWN_IN)
	player.velocity = Vector3.ZERO


func _go_out_now(player: CharacterBody3D) -> void:
	player.global_position = _return["pos"]
	player.velocity = Vector3.ZERO
	_return = {}
	_show("")


# ------------------------------------------------------------------ smoke test and screenshots
func _arg(prefix: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with(prefix):
			return a.trim_prefix(prefix)
	return ""


func _smoke() -> void:
	for k in _rooms:
		_load(k)
	for i in 3:
		await get_tree().physics_frame
	var shot_dir := _arg("--shot=")
	if shot_dir != "" and _rooms.has("int_tavern"):
		await _shot_room("int_tavern", shot_dir + "/shot_interior_tavern.png")
	# Every room has a floor under its spawn point.
	var space := get_world_3d().direct_space_state
	var floors := 0
	var no_floor: Array[String] = []
	for k in _rooms:
		var from: Vector3 = _rooms[k]["origin"] + Vector3(0, 1.5, -SPAWN_IN)
		var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(from, from + Vector3.DOWN * 3.0))
		if not hit.is_empty() and absf(hit["position"].y - DEPTH) < 0.2:
			floors += 1
		else:
			no_floor.append(k)
	# Every walk-in door has its facade within reach of the trigger (the capsule can stand in it against the wall).
	var reach := 0
	var auto_doors := 0
	var bad: Array[String] = []
	for d in _doors:
		if not d.get_meta("auto"):
			continue
		auto_doors += 1
		var out := d.global_transform.basis.z
		var half: float = (d.get_child(0) as CollisionShape3D).shape.size.z * 0.5
		var p := Vector3(d.global_position.x, 1.0, d.global_position.z)
		var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(p + out * 2.0, p - out * 2.0))
		if not hit.is_empty() and (hit["position"] - p).dot(out) < half + 0.3 and (hit["position"] - p).dot(out) > -half - 0.3:
			reach += 1
		else:
			bad.append(String(d.name))
	print("[smoke] interiors doors_at_facade=%d/%d %s" % [reach, auto_doors, bad if bad else ""])
	# Markers and tagged props the other systems look for.
	var posts := 0
	for k in _rooms:
		if _rooms[k]["node"] != null:
			posts += (_rooms[k]["node"] as Node3D).find_children("Post_*", "", true, false).size()
	var tagged := get_tree().get_nodes_in_group("interior_props").size()
	var gp: Node3D = _rooms.get("int_guard_post", {}).get("node", null)
	var ledger := gp != null and gp.find_child("ledger", true, false) != null
	print("[smoke] interiors posts=%d props=%d ledger=%s" % [posts, tagged, ledger])
	# Go through the first door without the fade, stand inside for a moment, come back out.
	var player := get_tree().get_first_node_in_group("player") as CharacterBody3D
	var result := "skipped"
	if player and not _doors.is_empty():
		var before := player.global_position
		var door := _doors[0]
		_go_in_now(player, door)
		for i in 20:
			await get_tree().physics_frame
		var inside_at := player.global_position
		var origin: Vector3 = _rooms[door.get_meta("room")]["origin"]
		var ok := absf(inside_at.y - DEPTH) < 0.3 and inside_at.distance_to(origin) < 4.0
		_go_out_now(player)
		var back := player.global_position
		player.global_position = before
		result = "%s in=%s back=%s" % ["ok" if ok else "FAIL", inside_at.snapped(Vector3.ONE * 0.01), back.snapped(Vector3.ONE * 0.01)]
	print("[smoke] interiors floors=%d/%d %s teleport=%s" % [floors, _rooms.size(), no_floor if no_floor else "", result])


## Camera placement for a room shot: data/interiors.json rooms.<key>.view = [[x, y, z], [tx, ty, tz]] in room
## space (Godot axes, origin at the front door), else just inside the door looking down the room.
func _view(key: String) -> Array:
	var v: Variant = data.get("rooms", {}).get(key, {}).get("view", null)
	if v is Array and (v as Array).size() == 2:
		return [_v3(v[0]), _v3(v[1])]
	return [Vector3(0.4, 1.7, -0.6), Vector3(-0.3, 1.2, -6.0)]


func _shot_room(key: String, path: String, v: Array = []) -> void:
	var prev := get_viewport().get_camera_3d()
	var was := _inside
	_show(key)
	var o: Vector3 = _rooms[key]["origin"]
	if v.is_empty():
		v = _view(key)
	var cam := Camera3D.new()
	cam.fov = 75
	add_child(cam)
	cam.look_at_from_position(o + v[0], o + v[1])
	cam.make_current()
	for i in 12:
		await get_tree().process_frame
	get_viewport().get_texture().get_image().save_png(path)
	print("[smoke] interior screenshot ", path)
	cam.queue_free()
	_show(was)
	if prev:
		prev.make_current()


func _interior_shots(spec: String) -> void:
	var dir := spec.get_slice(":", 0)
	var only: PackedStringArray = spec.get_slice(":", 1).split(",", false) if ":" in spec else PackedStringArray()
	for i in 30:
		await get_tree().process_frame
	for k in _rooms.keys():
		if only.is_empty() or only.has(k):
			var was_loaded: bool = _rooms[k]["node"] != null
			await _shot_room(k, "%s/shot_%s.png" % [dir, k])
			var extra: Array = data.get("rooms", {}).get(k, {}).get("views", [])
			for i in extra.size():
				await _shot_room(k, "%s/shot_%s_%d.png" % [dir, k, i + 1], [_v3(extra[i][0]), _v3(extra[i][1])])
			if not was_loaded:
				_unload(k)
				await get_tree().process_frame
