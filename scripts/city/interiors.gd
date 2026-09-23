extends Node3D
## Interior sets and the doors that lead to them.
## Each set (assets/blender/build_interiors.py) is instanced once, far below the map, and shared by every door
## mapped to it. A set's origin is the outside of its front door; the room extends toward -Z (Blender +Y).
## Doors are Area3D triggers in front of building portals. Overlap + `interact`, or walking into the door, fades
## out, stores the return point and drops the player just inside the set; the exit trigger in the doorway inside
## sends them back.
##
## The district hands over `portals` = [[asset, centre, rot_y], ...] collected in its `_row()` for the tenements;
## the landmarks' doors are fixed below (they match the Blender models and `_landmarks()` placement).

const DEPTH := -200.0
const SPACING := 40.0
const SETS := ["int_tavern", "int_shop", "int_workshop", "int_flat", "int_salon", "int_church"]
const TENEMENT_CYCLE := ["int_tavern", "int_shop", "int_workshop", "int_flat", "int_salon"]
const SET_TITLE := {"int_tavern": "tavern", "int_shop": "shop", "int_workshop": "workshop", "int_flat": "lodgings",
		"int_salon": "salon", "int_church": "church"}
## Door offset along the facade where the tenement's door is not centred (build_assets.py: 2 bays -> first bay).
const TENEMENT_DOOR_X := {"tenement_b": -2.0, "tenement_e": -2.0}
const TENEMENT_FRONT := 4.0          ## half the tenement depth: facade plane in module space
const SPAWN_IN := 1.8                ## metres inside the door where the player lands
const LAMPS := {                     ## kind -> [colour, energy, range, shadow]
	"lantern": [Color(1.0, 0.68, 0.36), 2.6, 7.5, true],
	"fire": [Color(1.0, 0.52, 0.22), 3.2, 8.0, true],
	"candle": [Color(1.0, 0.72, 0.42), 0.9, 4.0, false],
	"chandelier": [Color(1.0, 0.74, 0.46), 4.0, 12.0, true],
	"window": [Color(1.0, 0.70, 0.45), 1.0, 3.5, false],
}

var portals: Array = []

static var _smoked := false

var _sets := {}                      ## set name -> origin (Vector3, outside of its front door)
var _doors: Array[Area3D] = []
var _exits: Array[Area3D] = []
var _near: Array[Area3D] = []        ## triggers the player overlaps right now
var _return := {}                    ## {"pos": Vector3, "yaw": float} for the door we came through
var _busy := false
var _cooldown := 0.0
var _fade: ColorRect
var _prompt: Label


func _ready() -> void:
	name = "Interiors"
	for i in SETS.size():
		var origin := Vector3((i - SETS.size() * 0.5) * SPACING, DEPTH, 0.0)
		var inst := Assets.place(self, SETS[i], origin, 0.0)
		if inst == null:
			continue
		inst.name = SETS[i]
		_light(inst)
		_sets[SETS[i]] = origin
		_exits.append(_trigger("exit_" + SETS[i], origin + Vector3(0, 1.1, -0.5), Vector3(2.6, 2.2, 0.9), 0.0,
				{"set": SETS[i], "exit": true, "auto": true}))
	_build_doors()
	_build_ui()
	if "--smoke" in OS.get_cmdline_user_args() and not _smoked:
		_smoked = true       # only the first night's world: later nights belong to the mission smoke
		print("[smoke] interiors=%d doors=%d" % [_sets.size(), _doors.size()])
		_smoke.call_deferred()


# ------------------------------------------------------------------ doors
func _build_doors() -> void:
	var k := 0
	for p in portals:
		var asset: String = p[0]
		var centre: Vector3 = p[1]
		var rot_y: float = p[2]
		var b := Basis(Vector3.UP, rot_y)
		var pos := centre + b * Vector3(TENEMENT_DOOR_X.get(asset, 0.0), 0, TENEMENT_FRONT + 0.8)
		_door("door_%s_%d" % [asset, k], pos, rot_y, TENEMENT_CYCLE[k % TENEMENT_CYCLE.size()], true)
		k += 1
	# St Mary's west door (towers face the square), the Town Hall tower door, both ends of the Cloth Hall passage.
	_door("door_st_marys", Vector3(34, 0, -34) + Vector3(0, 0, 13.7), 0.0, "int_church", true, Vector3(3.0, 2.6, 1.2))
	_door("door_town_hall", Vector3(-16, 0, 12) + Vector3(0, 0, 4.2), 0.0, "int_salon", true)
	_door("door_cloth_hall_n", Vector3(0, 0, -3.9), PI, "int_shop", false, Vector3(2.6, 2.4, 1.0))
	_door("door_cloth_hall_s", Vector3(0, 0, 3.9), 0.0, "int_shop", false, Vector3(2.6, 2.4, 1.0))


## rot_y is the facade's facing (0 = the door looks toward +Z). auto: walking into it enters without `interact`.
func _door(id: String, pos: Vector3, rot_y: float, set_name: String, auto: bool, size := Vector3(1.8, 2.4, 1.2)) -> void:
	if not _sets.has(set_name):
		return
	_doors.append(_trigger(id, pos + Vector3(0, size.y * 0.5, 0), size, rot_y, {"set": set_name, "exit": false, "auto": auto}))


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
	_prompt.text = "E  leave" if exiting else "E  enter the %s" % SET_TITLE.get(a.get_meta("set"), "building")
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
			_go_out(player)
		else:
			_go_in(player, a)


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
	var out := door.global_transform.basis.z
	_return = {"pos": Vector3(door.global_position.x, 0.1, door.global_position.z) + out * 0.9, "yaw": atan2(-out.x, -out.z)}
	var origin: Vector3 = _sets[door.get_meta("set")]
	_teleport(player, origin + Vector3(0, 0.05, -SPAWN_IN), 0.0)


func _go_out(player: CharacterBody3D) -> void:
	if _return.is_empty():
		_return = {"pos": get_parent().call("player_spawn") if get_parent().has_method("player_spawn") else Vector3(0, 0.2, 0), "yaw": 0.0}
	_teleport(player, _return["pos"], _return["yaw"])
	_return = {}


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


# ------------------------------------------------------------------ set dressing
## Hang an OmniLight3D on every `lamp_<kind>_<nn>` empty exported by build_interiors.py.
func _light(n: Node) -> void:
	for c in n.get_children():
		_light(c)
	if n is Node3D and n.name.begins_with("lamp_"):
		var kind := String(n.name).get_slice("_", 1)
		var cfg: Array = LAMPS.get(kind, LAMPS["candle"])
		var l := OmniLight3D.new()
		l.light_color = cfg[0]
		l.light_energy = cfg[1]
		l.omni_range = cfg[2]
		l.omni_attenuation = 1.2
		l.shadow_enabled = cfg[3]
		l.light_specular = 0.4
		n.add_child(l)


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


# ------------------------------------------------------------------ smoke test and screenshot
func _smoke() -> void:
	for i in 3:
		await get_tree().physics_frame
	var shot_dir := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			shot_dir = a.trim_prefix("--shot=")
	if shot_dir != "" and _sets.has("int_tavern"):
		await _shot_tavern(shot_dir)
	# Every set has a floor under its spawn point.
	var space := get_world_3d().direct_space_state
	var floors := 0
	for s in _sets:
		var from: Vector3 = _sets[s] + Vector3(0, 1.5, -SPAWN_IN)
		var hit := space.intersect_ray(PhysicsRayQueryParameters3D.create(from, from + Vector3.DOWN * 3.0))
		if not hit.is_empty() and absf(hit["position"].y - DEPTH) < 0.2:
			floors += 1
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
	# Go through the first door without the fade, stand inside for a moment, come back out.
	var player := get_tree().get_first_node_in_group("player") as CharacterBody3D
	var result := "skipped"
	if player and not _doors.is_empty():
		var before := player.global_position
		var door := _doors[0]
		_go_in_now(player, door)
		for i in 20:
			await get_tree().physics_frame
		var inside := player.global_position
		var origin: Vector3 = _sets[door.get_meta("set")]
		var ok := absf(inside.y - DEPTH) < 0.3 and inside.distance_to(origin) < 4.0
		_go_out_now(player)
		var back := player.global_position
		player.global_position = before
		result = "%s in=%s back=%s" % ["ok" if ok else "FAIL", inside.snapped(Vector3.ONE * 0.01), back.snapped(Vector3.ONE * 0.01)]
	print("[smoke] interiors floors=%d/%d teleport=%s" % [floors, _sets.size(), result])


## Origin (outside of the front door) of an interior set, or Vector3.INF if it was not built.
func interior_origin(set_name: String) -> Vector3:
	return _sets.get(set_name, Vector3.INF)


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
	var out := door.global_transform.basis.z
	_return = {"pos": Vector3(door.global_position.x, 0.1, door.global_position.z) + out * 0.9, "yaw": atan2(-out.x, -out.z)}
	player.global_position = _sets[door.get_meta("set")] + Vector3(0, 0.05, -SPAWN_IN)
	player.velocity = Vector3.ZERO


func _go_out_now(player: CharacterBody3D) -> void:
	player.global_position = _return["pos"]
	player.velocity = Vector3.ZERO
	_return = {}


func _shot_tavern(dir: String) -> void:
	var prev := get_viewport().get_camera_3d()
	var o: Vector3 = _sets["int_tavern"]
	var cam := Camera3D.new()
	cam.fov = 75
	add_child(cam)
	# Blender (0.3, 0.7, 1.8) looking at (-0.6, 6.0, 1.6)  ->  Godot (x, z, -y)
	cam.look_at_from_position(o + Vector3(0.3, 1.8, -0.7), o + Vector3(-0.6, 1.6, -6.0))
	cam.make_current()
	for i in 12:
		await get_tree().process_frame
	get_viewport().get_texture().get_image().save_png(dir + "/shot_interior_tavern.png")
	print("[smoke] interior screenshot ", dir + "/shot_interior_tavern.png")
	cam.queue_free()
	if prev:
		prev.make_current()
