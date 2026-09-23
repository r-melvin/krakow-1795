extends PanelContainer
## Options: master volume, mouse sensitivity, invert Y, fullscreen, VSync. Every change is applied and saved
## at once through GameState.set_setting(). Shared by the main menu and the pause overlay.

signal closed

var _first: Control


func _ready() -> void:
	add_theme_stylebox_override("panel", UiTheme.panel_box(true))
	custom_minimum_size = Vector2(640, 0)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 16)
	add_child(v)
	v.add_child(UiTheme.kicker("Settings"))
	v.add_child(UiTheme.heading("Options", 44))
	v.add_child(HSeparator.new())

	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 24)
	grid.add_theme_constant_override("v_separation", 18)
	v.add_child(grid)

	var s: Dictionary = GameState.settings
	_first = _slider_row(grid, "Master volume", "master_volume", 0.0, 1.0, 0.05, func(x: float) -> String: return "%d%%" % roundi(x * 100))
	_slider_row(grid, "Mouse sensitivity", "mouse_sens", 0.2, 3.0, 0.05, func(x: float) -> String: return "%.2f×" % x)
	_toggle_row(grid, "Invert vertical look", "invert_y")
	_toggle_row(grid, "Fullscreen", "fullscreen")
	_toggle_row(grid, "Vertical sync", "vsync")
	_toggle_row(grid, "Bounced light and mist (GPU)", "gi")
	_toggle_row(grid, "Multisample anti-aliasing (4x)", "msaa")
	_toggle_row(grid, "Temporal anti-aliasing", "taa")

	v.add_child(UiTheme.spacer(4))
	v.add_child(HSeparator.new())
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_END
	var reset := UiTheme.button("Defaults", _defaults, 150)
	row.add_child(reset)
	row.add_child(UiTheme.button("Back", func() -> void: closed.emit(), 150))
	row.add_theme_constant_override("separation", 12)
	v.add_child(row)
	var hint := UiTheme.label("Changes apply immediately.   Esc: back", 15, UiTheme.TEXT_DIM, "italic")
	v.add_child(hint)
	visibility_changed.connect(func() -> void:
		if is_visible_in_tree():
			focus_first())


func focus_first() -> void:
	if _first:
		_first.grab_focus.call_deferred()


func _slider_row(grid: GridContainer, text: String, key: String, lo: float, hi: float, step: float, fmt: Callable) -> Control:
	grid.add_child(_name_label(text))
	var sl := HSlider.new()
	sl.min_value = lo
	sl.max_value = hi
	sl.step = step
	sl.value = float(GameState.settings[key])
	sl.custom_minimum_size = Vector2(280, 24)
	sl.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	sl.focus_mode = Control.FOCUS_ALL
	grid.add_child(sl)
	var val := UiTheme.label(fmt.call(sl.value), 18, UiTheme.BRASS_BRIGHT, "bold")
	val.custom_minimum_size.x = 70
	grid.add_child(val)
	sl.value_changed.connect(func(x: float) -> void:
		val.text = fmt.call(x)
		GameState.set_setting(key, x))
	sl.set_meta("key", key)
	return sl


func _toggle_row(grid: GridContainer, text: String, key: String) -> void:
	grid.add_child(_name_label(text))
	var cb := CheckButton.new()
	cb.button_pressed = bool(GameState.settings[key])
	cb.text = "On" if cb.button_pressed else "Off"
	cb.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	cb.custom_minimum_size.x = 120
	cb.toggled.connect(func(on: bool) -> void:
		cb.text = "On" if on else "Off"
		GameState.set_setting(key, on))
	cb.set_meta("key", key)
	grid.add_child(cb)
	grid.add_child(Control.new())


func _name_label(text: String) -> Label:
	var l := UiTheme.label(text, 20)
	l.custom_minimum_size.x = 220
	return l


func _defaults() -> void:
	for k in GameState.DEFAULT_SETTINGS:
		GameState.settings[k] = GameState.DEFAULT_SETTINGS[k]
	GameState.apply_settings()
	GameState.save_settings()
	_sync(self)


func _sync(n: Node) -> void:
	for c in n.get_children():
		if c.has_meta("key"):
			var v = GameState.settings[c.get_meta("key")]
			if c is HSlider:
				c.set_value_no_signal(float(v))
				c.value_changed.emit(float(v))
			elif c is CheckButton:
				c.button_pressed = bool(v)
		_sync(c)
