extends Control
## HUD minimap (bottom right, ~190 px circle, north up; M toggles it on and off, J / Tab still opens the full map in
## the journal). Parchment inside a thin brass ring, drawn with scripts/ui/city_map.gd like the journal's Map tab:
## building footprints, the zone tint under the player (red rim when the clothes do not pass there), lanterns seen,
## hiding spots used, vendors and the brothel once found, recorded patrol loops, the current objective marker
## (missions.json `stealth.map_marks`: "actor:<id>" or [x, z]), guards the player can see now (red dots with a facing
## tick), the watch's last-known ghost, and the player arrow. No text but a compass N. Redrawn at 10 Hz.
## `player` / `watch` / `world` may be set by a test (intel_smoke.gd); otherwise found from the "player" group.

const CityMap := preload("res://scripts/ui/city_map.gd")
const Intel := preload("res://scripts/stealth/intel.gd")
const Perception := preload("res://scripts/stealth/perception.gd")

const DIAMETER := 190.0
const RADIUS_M := 30.0          ## metres from the centre to the rim
const SEE_DIST := 32.0
const HZ := 10.0

static var shown := true        ## M toggles; remembered across nights

var player: Node3D
var watch: Node
var world: Node3D
var intel_override: Dictionary = {}
var origin := Vector3.ZERO      ## test sandbox offset (its world is far from the district)
var data: Dictionary = {}       ## last gathered options (the smoke reads it)

var _mask: Control
var _map: Control
var _ring: Control
var _t := 0.0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	anchor_left = 1.0
	anchor_right = 1.0
	anchor_top = 1.0
	anchor_bottom = 1.0
	offset_left = -DIAMETER - 26
	offset_right = -26
	offset_top = -DIAMETER - 30
	offset_bottom = -30
	_mask = Control.new()
	_mask.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_mask.clip_children = CanvasItem.CLIP_CHILDREN_ONLY
	_mask.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_mask.draw.connect(func() -> void: _mask.draw_circle(_mask.size * 0.5, DIAMETER * 0.5 - 1.0, Color.WHITE))
	add_child(_mask)
	_map = Control.new()
	_map.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_map.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_map.draw.connect(_draw_map)
	_mask.add_child(_map)
	_ring = Control.new()
	_ring.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_ring.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_ring.draw.connect(_draw_ring)
	add_child(_ring)
	visible = shown


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and (event as InputEventKey).physical_keycode == KEY_M:
		shown = not shown
		visible = shown
		get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
	if not visible:
		return
	_t += delta
	if _t < 1.0 / HZ:
		return
	_t = 0.0
	refresh()


## Gathers what to show and redraws (10 Hz from _process; a test may call it directly).
func refresh() -> void:
	var p := _player()
	if p == null:
		data = {}
		_map.queue_redraw()
		return
	if watch == null or not is_instance_valid(watch):
		watch = Perception.watch_of(p)
	var intel: Dictionary = intel_override if not intel_override.is_empty() else Intel.journal_store()
	var zone := "street"
	var tres := false
	var z: Node = watch.get("zones") if watch else null
	if z:
		zone = z.current(p.global_position)
		tres = z.trespassing(p)
	var guards: Array = []
	var ghost: Variant = null
	if watch:
		var head: Vector3 = p.head_position() if p.has_method("head_position") else p.global_position + Vector3(0, 1.6, 0)
		var space := p.get_world_3d().direct_space_state
		for g in watch.guards():
			if g.is_downed() or not g.visible:
				continue
			var chest: Vector3 = g.global_position + Vector3(0, 1.3, 0)
			if chest.distance_to(head) > SEE_DIST:
				continue
			if Perception.clear_line(space, head, chest, [p.get_rid(), g.get_rid()], null, true):
				var f: Vector3 = -g.global_transform.basis.z
				guards.append([g.global_position, f.rotated(Vector3.UP, g.head_yaw)])
		if watch.has_method("ghost_visible") and watch.ghost_visible():
			ghost = watch.ghost_target()
	if world == null or not is_instance_valid(world):
		world = watch.get_parent() as Node3D if watch else null
	data = {"intel": intel, "world": world, "labels": false, "zones": "under", "zone": zone, "trespass": tres, "player": p,
			"guards": guards, "ghost": ghost, "objective": _objective(), "corporal": true, "icon": 0.62, "origin": origin}
	_map.queue_redraw()


func _player() -> Node3D:
	if player and is_instance_valid(player):
		return player
	return get_tree().get_first_node_in_group("player") as Node3D


## The first open, non-optional objective with a map mark (missions.json `stealth.map_marks`), as (x, z).
func _objective() -> Variant:
	if not Mission.is_active():
		return null
	var marks: Dictionary = Mission.data.get("stealth", {}).get("map_marks", {})
	for o in Mission.objectives:
		if o.get("done", false) or o.get("optional", false):
			continue
		var m: Variant = marks.get(str(o.get("id", "")))
		if m is Array and (m as Array).size() >= 2:
			return Vector2(float(m[0]), float(m[1]))
		if m is String and str(m).begins_with("actor:") and Mission.runner and is_instance_valid(Mission.runner):
			var a: Node3D = Mission.runner.call("actor", str(m).trim_prefix("actor:"))
			if a and a.global_position.y > -50.0:
				return Vector2(a.global_position.x, a.global_position.z)
	return null


func _draw_map() -> void:
	var r := Rect2(Vector2.ZERO, _map.size)
	_map.draw_rect(r, CityMap.PAPER)
	var p: Node3D = data.get("player")
	if p == null or not is_instance_valid(p):
		return
	var centre := Vector2(p.global_position.x - origin.x, p.global_position.z - origin.z)
	if p.global_position.y < -50.0:
		centre = Vector2(-16, 17.4)      # indoors: the map rests on the Town Hall door
	CityMap.draw_map(_map, r, centre, DIAMETER * 0.5 / RADIUS_M, data)
	# vignette toward the rim
	for i in 6:
		_map.draw_arc(r.get_center(), DIAMETER * 0.5 - 2.0 - i * 2.0, 0, TAU, 48, Color(0.35, 0.22, 0.1, 0.07), 2.0)


func _draw_ring() -> void:
	var c := _ring.size * 0.5
	var rad := DIAMETER * 0.5
	_ring.draw_arc(c, rad, 0, TAU, 64, Color(0, 0, 0, 0.45), 4.0)
	_ring.draw_arc(c, rad - 0.5, 0, TAU, 64, UiTheme.BRASS, 2.0)
	_ring.draw_arc(c, rad - 3.0, 0, TAU, 64, Color(UiTheme.BRASS_DARK, 0.8), 1.0)
	# compass N at the top of the ring
	var n := c + Vector2(0, -rad)
	_ring.draw_colored_polygon(PackedVector2Array([n + Vector2(0, -7), n + Vector2(6, 4), n + Vector2(-6, 4)]), UiTheme.BRASS_BRIGHT)
	var f := UiTheme.font("display")
	_ring.draw_string(f, n + Vector2(-5, 17), "N", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, CityMap.INK)
