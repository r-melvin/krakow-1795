extends CanvasLayer
## Bottom-of-screen conversation box: speaker name, one line at a time (advance with `interact`), then an
## optional list of 2-4 choices (keys 1-4 or click). The mission runner drives it node by node:
##   show_node(lines, choices)   lines: [[speaker, text], ...]; choices: [{text, enabled, why?}, ...]
## emits choice_made(index) or, after the last line of a node without choices, finished.
## While open the player cannot move or act (player.gd asks Mission.dialogue_blocking()).

signal choice_made(index: int)
signal finished

const CLOSE_GRACE_MS := 250

var is_open := false
var _lines: Array = []
var _i := 0
var _choices: Array = []
var _choosing := false
var _closed_at := -100000
var _mouse_before := Input.MOUSE_MODE_CAPTURED

var _root: Control
var _speaker: Label
var _text: Label
var _hint: Label
var _choice_box: VBoxContainer


func _ready() -> void:
	layer = 40
	_build()
	visible = false


func blocking() -> bool:
	return is_open or Time.get_ticks_msec() - _closed_at < CLOSE_GRACE_MS


func show_node(lines: Array, choices: Array) -> void:
	if not is_open:
		_mouse_before = Input.mouse_mode
	is_open = true
	visible = true
	_lines = lines
	_choices = choices
	_i = 0
	_show_current()


func advance() -> void:
	if not is_open or _choosing:
		return
	_i += 1
	_show_current()


func choose(index: int) -> void:
	if not is_open or not _choosing or index < 0 or index >= _choices.size():
		return
	if not bool(_choices[index].get("enabled", true)):
		return
	_choosing = false
	_clear_choices()
	choice_made.emit(index)


func close() -> void:
	if not is_open:
		return
	is_open = false
	_choosing = false
	visible = false
	_closed_at = Time.get_ticks_msec()
	if _mouse_before == Input.MOUSE_MODE_CAPTURED and DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func current_speaker() -> String:
	return _speaker.text


func is_choosing() -> bool:
	return _choosing


func _show_current() -> void:
	_clear_choices()
	if _i < _lines.size():
		var l: Array = _lines[_i]
		_speaker.text = str(l[0]).to_upper()
		_text.text = str(l[1])
		_hint.text = "E  continue"
		_hint.visible = true
		return
	if not _choices.is_empty():
		_choosing = true
		_hint.text = "1-%d  or click" % _choices.size()
		for k in _choices.size():
			var c: Dictionary = _choices[k]
			var b := Button.new()
			var en := bool(c.get("enabled", true))
			b.text = "%d.  %s%s" % [k + 1, c.get("text", "..."), "" if en else "   (%s)" % c.get("why", "not possible")]
			b.alignment = HORIZONTAL_ALIGNMENT_LEFT
			b.disabled = not en
			b.focus_mode = Control.FOCUS_NONE
			b.add_theme_font_override("font", UiTheme.font("regular"))
			b.add_theme_font_size_override("font_size", 17)
			b.add_theme_color_override("font_color", UiTheme.TEXT)
			b.add_theme_color_override("font_hover_color", UiTheme.BRASS_BRIGHT)
			b.add_theme_color_override("font_disabled_color", UiTheme.TEXT_DIM * Color(1, 1, 1, 0.7))
			var flat := StyleBoxFlat.new()
			flat.bg_color = Color(0, 0, 0, 0)
			flat.content_margin_left = 10
			flat.content_margin_top = 3
			flat.content_margin_bottom = 3
			var hov := flat.duplicate() as StyleBoxFlat
			hov.bg_color = Color(UiTheme.BRASS, 0.14)
			hov.border_color = UiTheme.BRASS
			hov.border_width_left = 3
			b.add_theme_stylebox_override("normal", flat)
			b.add_theme_stylebox_override("disabled", flat)
			b.add_theme_stylebox_override("hover", hov)
			b.add_theme_stylebox_override("pressed", hov)
			b.pressed.connect(choose.bind(k))
			_choice_box.add_child(b)
		_choice_box.visible = true
		if DisplayServer.get_name() != "headless":
			Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		return
	close()
	finished.emit()


func _clear_choices() -> void:
	for c in _choice_box.get_children():
		c.queue_free()
	_choice_box.visible = false


func _input(event: InputEvent) -> void:
	if not is_open:
		return
	if event.is_action_pressed("interact") and not event.is_echo():
		get_viewport().set_input_as_handled()
		advance()
	elif event is InputEventKey and event.pressed and not event.echo and _choosing:
		var k: int = (event as InputEventKey).physical_keycode
		if k >= KEY_1 and k <= KEY_4:
			get_viewport().set_input_as_handled()
			choose(k - KEY_1)


func _build() -> void:
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	var panel := PanelContainer.new()
	var box := StyleBoxFlat.new()
	box.bg_color = Color(0.05, 0.06, 0.09, 0.9)
	box.border_color = Color(UiTheme.BRASS, 0.6)
	box.border_width_top = 2
	box.set_corner_radius_all(3)
	box.content_margin_left = 28
	box.content_margin_right = 28
	box.content_margin_top = 14
	box.content_margin_bottom = 12
	box.shadow_color = Color(0, 0, 0, 0.5)
	box.shadow_size = 16
	panel.add_theme_stylebox_override("panel", box)
	panel.anchor_left = 0.24
	panel.anchor_right = 0.76
	panel.anchor_top = 1.0
	panel.anchor_bottom = 1.0
	panel.offset_top = -40
	panel.offset_bottom = -36
	panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_root.add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 6)
	panel.add_child(v)
	var top := HBoxContainer.new()
	v.add_child(top)
	_speaker = Label.new()
	_speaker.add_theme_font_override("font", UiTheme.font("bold"))
	_speaker.add_theme_font_size_override("font_size", 14)
	_speaker.add_theme_color_override("font_color", UiTheme.BRASS_BRIGHT)
	_speaker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(_speaker)
	_hint = Label.new()
	_hint.add_theme_font_override("font", UiTheme.font("italic"))
	_hint.add_theme_font_size_override("font_size", 13)
	_hint.add_theme_color_override("font_color", UiTheme.TEXT_DIM)
	top.add_child(_hint)
	_text = Label.new()
	_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_text.custom_minimum_size = Vector2(0, 48)
	_text.add_theme_font_override("font", UiTheme.font("regular"))
	_text.add_theme_font_size_override("font_size", 19)
	_text.add_theme_color_override("font_color", UiTheme.TEXT)
	v.add_child(_text)
	_choice_box = VBoxContainer.new()
	_choice_box.add_theme_constant_override("separation", 2)
	_choice_box.visible = false
	v.add_child(_choice_box)
