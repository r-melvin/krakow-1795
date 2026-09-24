extends CanvasLayer
## Inventory (I): what the player carries, in the journal's theme (UiTheme). A grid of kit items (kit.gd icons and
## counts); the selected one shows its name and blurb (data/stealth.json kit.blurbs) and an Equip / Use / Drop row.
##   Equip  makes it the current item (the hand prop follows, player.gd)
##   Use    throwables: equip and start aiming; food: eaten (1 health); a lit-able torch: lit at a lantern if one is
##          near; tools used on props (poison, lockpick, tinderbox): says so
##   Drop   leaves one on the cobbles as a pickup (pickup.gd); coins drop one coin
## The world pauses while it is open. `player` may be set by a test (else group "player"); `pause` false for tests.

const KitScript := preload("res://scripts/stealth/kit.gd")
const Pickup := preload("res://scripts/stealth/pickup.gd")
const Verbs := preload("res://scripts/stealth/verbs.gd")
const NAMES := {"knife": "Knife", "cosh": "Cosh", "cudgel": "Cudgel", "pistol": "Pistol", "musket": "Musket", "torch": "Torch",
		"tinderbox": "Tinderbox", "stone": "Stones", "coin": "Purse", "bottle": "Bottle", "food": "Bread", "smoke": "Smoke powder",
		"flash": "Flash powder", "poison": "Poison", "lockpick": "Lockpicks"}

var player: Node3D
var pause := true
var selected := ""
var last_action := ""
var _root: Control
var _grid: GridContainer
var _name: Label
var _blurb: Label
var _count: Label
var _was_paused := false
var _mouse_before := Input.MOUSE_MODE_CAPTURED


func _ready() -> void:
	layer = 20
	process_mode = Node.PROCESS_MODE_ALWAYS
	add_to_group("inventory")
	_root = Control.new()
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(_root)
	var dim := ColorRect.new()
	dim.color = Color(0, 0, 0, 0.45)
	UiTheme.full_rect(dim)
	_root.add_child(dim)
	var centre := CenterContainer.new()
	UiTheme.full_rect(centre)
	_root.add_child(centre)
	var pan := UiTheme.panel()
	pan.custom_minimum_size = Vector2(820, 480)
	centre.add_child(pan)
	var m := UiTheme.margin(VBoxContainer.new(), 26)
	pan.add_child(m)
	var v: VBoxContainer = m.get_child(0)
	v.add_theme_constant_override("separation", 14)
	v.add_child(UiTheme.kicker("WHAT YOU CARRY"))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 26)
	row.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(row)
	_grid = GridContainer.new()
	_grid.columns = 5
	_grid.add_theme_constant_override("h_separation", 10)
	_grid.add_theme_constant_override("v_separation", 10)
	row.add_child(_grid)
	var side := VBoxContainer.new()
	side.custom_minimum_size = Vector2(300, 0)
	side.add_theme_constant_override("separation", 10)
	row.add_child(side)
	_name = UiTheme.heading("", 30)
	side.add_child(_name)
	_count = UiTheme.label("", 18, UiTheme.BRASS)
	side.add_child(_count)
	_blurb = UiTheme.body("", 18, UiTheme.TEXT_DIM)
	_blurb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_blurb.custom_minimum_size = Vector2(300, 120)
	side.add_child(_blurb)
	var buttons := HBoxContainer.new()
	buttons.add_theme_constant_override("separation", 10)
	buttons.add_child(UiTheme.primary_button("Equip", equip, 90))
	buttons.add_child(UiTheme.button("Use", use, 80))
	buttons.add_child(UiTheme.button("Drop", drop, 80))
	side.add_child(buttons)
	v.add_child(UiTheme.label("I or Esc closes   ·   hold Tab for the wheel", 15, UiTheme.TEXT_DIM, "italic"))
	visible = false


func _player() -> Node3D:
	if player == null or not is_instance_valid(player):
		player = get_tree().get_first_node_in_group("player") as Node3D
	return player


func _kit() -> Node:
	var p := _player()
	return p.get("kit") if p else null


func is_open() -> bool:
	return visible


func open() -> void:
	if visible or _kit() == null:
		return
	visible = true
	_was_paused = get_tree().paused
	if pause:
		get_tree().paused = true
	_mouse_before = Input.mouse_mode
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	var k := _kit()
	if selected == "" or not k.has(selected):
		selected = k.current
	_refresh()


func close() -> void:
	if not visible:
		return
	visible = false
	if pause:
		get_tree().paused = _was_paused
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = _mouse_before


func _input(event: InputEvent) -> void:
	if GameState.phase != GameState.Phase.NIGHT and not visible:
		return
	if event.is_action_pressed("inventory") and not event.is_echo():
		get_viewport().set_input_as_handled()
		if visible:
			close()
		elif not Mission.dialogue_open() and not _other_open():
			open()
	elif visible and (event.is_action_pressed("pause") or event.is_action_pressed("ui_cancel")):
		get_viewport().set_input_as_handled()
		close()


func _other_open() -> bool:
	for g in ["journal", "pause_menu"]:
		for n in get_tree().get_nodes_in_group(g):
			if n.get("visible"):
				return true
	return false


## The items carried, in kit order.
func items() -> Array:
	var k := _kit()
	var out: Array = []
	if k:
		for it in KitScript.ORDER:
			if k.has(it):
				out.append(it)
	return out


func select_item(item: String) -> void:
	selected = item
	_refresh()


func _refresh() -> void:
	var k := _kit()
	if k == null:
		return
	for c in _grid.get_children():
		c.queue_free()
	for it in items():
		var cell := Cell.new()
		cell.item = it
		cell.kit = k
		cell.selected = it == selected
		cell.equipped = it == k.current
		cell.pressed_cb = select_item
		_grid.add_child(cell)
	_name.text = str(NAMES.get(selected, selected.capitalize()))
	_count.text = "" if selected in KitScript.ALWAYS else ("× %d" % k.count(selected)) + ("   (in hand)" if selected == k.current else "")
	var blurbs: Variant = Perception_tg("kit.blurbs", {})
	_blurb.text = str((blurbs as Dictionary).get(selected, "")) if blurbs is Dictionary else ""


static func Perception_tg(path: String, fb: Variant) -> Variant:
	return load("res://scripts/stealth/perception.gd").tg(path, fb)


func equip() -> void:
	var k := _kit()
	if k and selected != "" and (k.is_weapon(selected) or k.is_throwable(selected) or selected == "tinderbox"):
		k.select(selected)
		last_action = "equip"
	_refresh()


func use() -> void:
	var k := _kit()
	var p := _player()
	if k == null or selected == "":
		return
	last_action = "use"
	match selected:
		"food":
			if k.take("food"):
				var mx := int(p.get("MAX_HEALTH")) if p.get("MAX_HEALTH") != null else 3
				p.set("health", mini(int(p.get("health")) + 1, mx))
				_msg("Bread, cold and good. You feel steadier.")
		"torch":
			k.select("torch")
			if not Verbs.light_torch(p):
				_msg("Light it at a lantern or a brazier.")
		"poison", "lockpick", "tinderbox":
			_msg({"poison": "Tip it into a cup no one is watching.", "lockpick": "Kneel at a locked door.",
					"tinderbox": "Kneel by something that will burn."}[selected])
		_:
			if k.is_throwable(selected):
				k.select(selected)
				close()
				if p.has_method("begin_throw_aim"):
					p.begin_throw_aim(selected)
				return
			k.select(selected)
	_refresh()


func drop() -> void:
	var k := _kit()
	var p := _player()
	if k == null or selected == "" or not k.has(selected):
		return
	if selected == "torch" and k.torch_lit and k.current == "torch":
		k.select("knife" if k.has("knife") else "cudgel")      # a burning torch drops itself, lit
	elif k.take(selected):
		Pickup.drop(p.get_parent(), selected, p.global_position + (-p.global_transform.basis.z) * 0.6 + Vector3(0, 0.02, 0))
	last_action = "drop"
	if not k.has(selected):
		selected = k.current
	_refresh()


func _msg(t: String) -> void:
	var p := _player()
	if p and not p.get("sandbox"):
		Mission.message.emit(t, 2.5)


## One square of the grid: the icon, the count, a brass frame when selected, a dot when in hand.
class Cell extends Control:
	var item := ""
	var kit: Node
	var selected := false
	var equipped := false
	var pressed_cb: Callable

	func _init() -> void:
		custom_minimum_size = Vector2(84, 84)
		mouse_filter = Control.MOUSE_FILTER_STOP

	func _gui_input(e: InputEvent) -> void:
		if e is InputEventMouseButton and e.pressed and e.button_index == MOUSE_BUTTON_LEFT and pressed_cb.is_valid():
			pressed_cb.call(item)

	func _draw() -> void:
		var r := Rect2(Vector2.ZERO, size)
		draw_rect(r, UiTheme.PANEL_LIGHT)
		draw_rect(r, UiTheme.BRASS_BRIGHT if selected else UiTheme.BRASS_DARK, false, 2.0 if selected else 1.0)
		draw_set_transform(size * 0.5 - Vector2(0, 4), 0.0, Vector2(1.25, 1.25))
		load("res://scripts/stealth/kit.gd").draw_icon(self, item, kit)
		draw_set_transform(Vector2.ZERO)
		if equipped:
			draw_circle(Vector2(10, 10), 4, UiTheme.BRASS_BRIGHT)
		if kit and not (item in ["knife", "cudgel"]):
			var n: int = kit.count(item)
			var f := UiTheme.font("bold")
			draw_string(f, Vector2(size.x - 30, size.y - 8), str(n), HORIZONTAL_ALIGNMENT_RIGHT, 24, 17, UiTheme.TEXT)
