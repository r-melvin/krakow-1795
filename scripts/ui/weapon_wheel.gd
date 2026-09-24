extends CanvasLayer
## Weapon wheel (action "wheel", Tab). A tap (< 0.25 s) opens or closes the journal as Tab always did; held, a ring
## of everything carried (kit.gd icons, counts) opens round the screen centre and the world slows to 0.25. The mouse
## (or [ / ]) moves the highlight; letting go of Tab equips the highlighted item. The journal's own J key is unchanged.
## `player` may be set by a test (else group "player"); `sandbox` records the slow-down instead of applying it.

const KitScript := preload("res://scripts/stealth/kit.gd")
const HOLD_SECS := 0.25
const SLOW := 0.25

var player: Node3D
var sandbox := false
var is_wheel_open := false
var highlighted := ""
var time_scale_applied := 1.0
var _pressing := false
var _held := 0.0
var _aim := Vector2.ZERO
var _ring: Ring


func _ready() -> void:
	layer = 18
	process_mode = Node.PROCESS_MODE_ALWAYS
	add_to_group("weapon_wheel")
	_ring = Ring.new()
	_ring.wheel = self
	add_child(_ring)
	_ring.visible = false


func _player() -> Node3D:
	if player == null or not is_instance_valid(player):
		player = get_tree().get_first_node_in_group("player") as Node3D
	return player


func _kit() -> Node:
	var p := _player()
	return p.get("kit") if p else null


func items() -> Array:
	var k := _kit()
	var out: Array = []
	if k:
		for it in KitScript.ORDER:
			if k.has(it):
				out.append(it)
	return out


func _input(event: InputEvent) -> void:
	if sandbox:
		return
	if event.is_action_pressed("wheel") and not event.is_echo():
		get_viewport().set_input_as_handled()
		press()
	elif event.is_action_released("wheel"):
		get_viewport().set_input_as_handled()
		release()
	elif is_wheel_open:
		if event is InputEventMouseMotion:
			_aim += (event as InputEventMouseMotion).relative
			if _aim.length() > 120.0:
				_aim = _aim.normalized() * 120.0
			_pick_from_aim()
			get_viewport().set_input_as_handled()
		elif event.is_action_pressed("kit_next") or event.is_action_pressed("kit_prev"):
			step(1 if event.is_action_pressed("kit_next") else -1)
			get_viewport().set_input_as_handled()


func _journal() -> Node:
	return get_tree().get_first_node_in_group("journal")


## Tab down.
func press() -> void:
	var j := _journal()
	if j and j.get("visible"):
		j.close()               # Tab closes an open journal at once
		return
	_pressing = true
	_held = 0.0


## Tab up: a tap opens the journal, a hold picks the highlighted item.
func release() -> void:
	if not _pressing:
		return
	_pressing = false
	if is_wheel_open:
		var k := _kit()
		if k and highlighted != "":
			k.select(highlighted)
		close_wheel()
	elif not sandbox:
		var j := _journal()
		if j and not j.get("visible") and GameState.phase == GameState.Phase.NIGHT and Mission.is_active() \
				and not Mission.dialogue_open():
			j.open()


func _process(delta: float) -> void:
	if not _pressing or is_wheel_open:
		return
	# real time, whatever Engine.time_scale is
	_held += delta / maxf(Engine.time_scale, 0.01)
	if _held >= HOLD_SECS:
		open_wheel()


func open_wheel() -> void:
	var k := _kit()
	if k == null or Mission.dialogue_open() and not sandbox:
		return
	is_wheel_open = true
	highlighted = k.current
	_aim = Vector2.ZERO
	time_scale_applied = SLOW
	if not sandbox:
		Engine.time_scale = SLOW
	_ring.visible = true
	_ring.queue_redraw()


func close_wheel() -> void:
	is_wheel_open = false
	_ring.visible = false
	time_scale_applied = 1.0
	if not sandbox:
		Engine.time_scale = 1.0


func highlight(item: String) -> void:
	if item in items():
		highlighted = item
		_ring.queue_redraw()


func step(dir: int) -> void:
	var its := items()
	if its.is_empty():
		return
	var i := its.find(highlighted)
	highlight(its[(i + dir + its.size()) % its.size()])


func _pick_from_aim() -> void:
	if _aim.length() < 25.0:
		return
	var its := items()
	if its.is_empty():
		return
	var a := fposmod(atan2(_aim.y, _aim.x) + PI * 0.5, TAU)       # 0 at the top, clockwise
	var i := int(round(a / (TAU / its.size()))) % its.size()
	highlight(its[i])


## The ring: slots round the centre, the highlighted one larger with a brass rim, its name in the middle.
class Ring extends Control:
	var wheel: Node

	func _ready() -> void:
		set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		var its: Array = wheel.items()
		var k: Node = wheel._kit()
		var c := size * 0.5
		var R := minf(size.x, size.y) * 0.26
		draw_circle(c, R + 62, Color(0.03, 0.035, 0.05, 0.72))
		draw_arc(c, R + 62, 0, TAU, 96, UiTheme.BRASS_DARK, 2.0, true)
		draw_arc(c, R - 50, 0, TAU, 64, UiTheme.BRASS_DARK, 1.5, true)
		var n: int = maxi(its.size(), 1)
		for i in its.size():
			var a := -PI * 0.5 + TAU * i / n
			var p := c + Vector2(cos(a), sin(a)) * R
			var hi: bool = its[i] == wheel.highlighted
			draw_circle(p, 44 if hi else 36, UiTheme.PANEL_LIGHT if hi else Color(0.06, 0.07, 0.1, 0.9))
			draw_arc(p, 44 if hi else 36, 0, TAU, 40, UiTheme.BRASS_BRIGHT if hi else UiTheme.BRASS_DARK, 2.5 if hi else 1.2, true)
			draw_set_transform(p, 0.0, Vector2.ONE * (1.45 if hi else 1.15))
			load("res://scripts/stealth/kit.gd").draw_icon(self, its[i], k)
			draw_set_transform(Vector2.ZERO)
			if k and not (its[i] in ["knife", "cudgel"]):
				draw_string(UiTheme.font("bold"), p + Vector2(14, 30), str(k.count(its[i])), HORIZONTAL_ALIGNMENT_LEFT, -1, 16, UiTheme.TEXT)
		var nm: String = load("res://scripts/ui/inventory.gd").NAMES.get(wheel.highlighted, str(wheel.highlighted).capitalize())
		var f := UiTheme.font("display")
		var w := f.get_string_size(nm, HORIZONTAL_ALIGNMENT_CENTER, -1, 30).x
		draw_string(f, c + Vector2(-w * 0.5, 10), nm, HORIZONTAL_ALIGNMENT_LEFT, -1, 30, UiTheme.BRASS_BRIGHT)
