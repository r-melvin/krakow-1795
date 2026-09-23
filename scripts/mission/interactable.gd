extends Area3D
## Something the player can use with `interact`: a prop, or a person (attach as a child of the NPC so it moves
## with them). The player picks the nearest available one within reach and in front, shows `get_prompt()` on
## the HUD, highlights it, and on the key press calls Mission.interact(player, self) -> on_interact(player).
##
## Set before adding to the tree: display_name, prompt (or prompt_func), handler, highlight_root.

var display_name := ""
var prompt := "use"
var prompt_func: Callable        ## () -> String. Overrides `prompt`; "" means nothing to do right now.
var handler: Callable            ## (actor: Node) -> bool
var enabled := true
var highlight_root: Node3D       ## meshes below it are tinted while targeted (default: the parent)
var marker_height := 2.35

var _marker: Label3D
var _overlay: StandardMaterial3D
var _highlighted := false
var _player: Node3D


func _ready() -> void:
	add_to_group("interactable")
	collision_layer = 0
	collision_mask = 0
	monitoring = false
	monitorable = false
	var cs := CollisionShape3D.new()
	var sp := SphereShape3D.new()
	sp.radius = 0.6
	cs.shape = sp
	cs.position.y = 0.6
	add_child(cs)
	_marker = Label3D.new()
	_marker.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	_marker.no_depth_test = true
	_marker.render_priority = 4
	_marker.font_size = 30
	_marker.outline_size = 8
	_marker.outline_modulate = Color(0.04, 0.03, 0.02, 0.85)
	_marker.pixel_size = 0.004
	_marker.position.y = marker_height
	_marker.visible = false
	add_child(_marker)
	_overlay = StandardMaterial3D.new()
	_overlay.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_overlay.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_overlay.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	_overlay.albedo_color = Color(0.9, 0.62, 0.25, 0.22)


func get_prompt() -> String:
	if prompt_func.is_valid():
		return str(prompt_func.call())
	return prompt


func is_available() -> bool:
	return enabled and is_inside_tree() and is_visible_in_tree() and get_prompt() != ""


func on_interact(actor: Node) -> bool:
	if not is_available() or not handler.is_valid():
		return false
	return bool(handler.call(actor))


func set_highlight(on: bool) -> void:
	if on == _highlighted:
		return
	_highlighted = on
	_tint(highlight_root if highlight_root else get_parent(), on)


func _tint(n: Node, on: bool) -> void:
	if n is MeshInstance3D:
		(n as MeshInstance3D).material_overlay = _overlay if on else null
	for c in n.get_children():
		if c is Node3D and not (c is Label3D) and c.get_script() != get_script():
			_tint(c, on)


## A small marker floats over anything usable within a few metres; it names the thing when targeted.
func _process(_d: float) -> void:
	if _player == null or not is_instance_valid(_player):
		_player = get_tree().get_first_node_in_group("player") as Node3D
		if _player == null:
			return
	var d := _player.global_position.distance_to(global_position)
	var avail := is_available()
	_marker.visible = avail and d < 7.0
	if not _marker.visible:
		return
	if _highlighted:
		_marker.text = display_name if display_name != "" else "◆"
		_marker.modulate = Color(1.0, 0.86, 0.55, 1.0)
	else:
		_marker.text = "◆"
		_marker.modulate = Color(1.0, 0.8, 0.45, clampf(1.2 - d / 7.0, 0.25, 0.8))
