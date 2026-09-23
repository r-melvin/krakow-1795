extends CanvasLayer
## Night HUD: max guard suspicion, alarm count, objective hint.

var _bar: ProgressBar
var _state: Label
var _obj: Label
var _alarms: Label
var _clock: Label


func _ready() -> void:
	var root := MarginContainer.new()
	root.set_anchors_preset(Control.PRESET_TOP_LEFT)
	root.add_theme_constant_override("margin_left", 16)
	root.add_theme_constant_override("margin_top", 16)
	add_child(root)
	var v := VBoxContainer.new()
	root.add_child(v)

	_clock = Label.new()
	_clock.text = GameState.time_string()
	v.add_child(_clock)

	_obj = Label.new()
	_obj.text = "Night %d. Reach the safe house (lit marker, SE corner). Unseen if you can." % GameState.day
	v.add_child(_obj)

	_state = Label.new()
	_state.text = "Watch: calm"
	v.add_child(_state)

	_bar = ProgressBar.new()
	_bar.custom_minimum_size = Vector2(260, 18)
	_bar.max_value = 100
	_bar.show_percentage = false
	v.add_child(_bar)

	_alarms = Label.new()
	v.add_child(_alarms)

	var help := Label.new()
	help.text = "WASD move   Shift sprint   Ctrl/C crouch   Mouse look   Esc release mouse"
	help.modulate = Color(1, 1, 1, 0.6)
	v.add_child(help)


func _process(_d: float) -> void:
	var max_s := 0.0
	var worst := Guard.State.CALM
	for g in get_tree().get_nodes_in_group("guards"):
		max_s = maxf(max_s, g.suspicion)
		if g.state > worst:
			worst = g.state
	_bar.value = max_s
	_state.text = "Watch: " + ["calm", "curious", "searching", "ALARM"][worst]
	_clock.text = "Kraków, %s" % GameState.time_string()
	_alarms.text = "Alarms raised: %d    Crackdown: %d" % [GameState.night_alarm_count, GameState.crackdown]
