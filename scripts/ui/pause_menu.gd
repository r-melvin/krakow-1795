extends Control
## Night pause overlay. Esc (action "pause") toggles it: pauses the tree, releases the mouse, and offers
## Resume, Journal, Restart night, Options, Quit to menu. Runs with PROCESS_MODE_ALWAYS so it works while paused.

const OptionsPanel := preload("res://scripts/ui/options_panel.gd")

var _menu: Control
var _options: Control
var _first: Button


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	add_to_group("pause_menu")
	theme = UiTheme.get_theme()
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	visible = false
	var shade := ColorRect.new()
	shade.color = Color(0.02, 0.03, 0.05, 0.72)
	add_child(UiTheme.full_rect(shade))

	var center := CenterContainer.new()
	add_child(UiTheme.full_rect(center))
	var p := UiTheme.panel(true)
	p.custom_minimum_size = Vector2(460, 0)
	_menu = p
	center.add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 10)
	p.add_child(v)
	v.add_child(UiTheme.kicker("Night %d  ·  %s" % [GameState.day, GameState.time_string()]))
	v.add_child(UiTheme.heading("Paused", 48))
	v.add_child(HSeparator.new())
	_first = _item(v, "Resume", resume)
	_item(v, "Journal", _open_journal)
	_item(v, "Restart night", _restart)
	_item(v, "Options", _show_options)
	_item(v, "Quit to menu", _quit)
	v.add_child(UiTheme.spacer(6))
	v.add_child(UiTheme.label("Esc to resume", 15, UiTheme.TEXT_DIM, "italic"))

	_options = PanelContainer.new()
	_options.set_script(OptionsPanel)
	_options.visible = false
	_options.closed.connect(_hide_options)
	center.add_child(_options)


func _item(parent: Control, text: String, cb: Callable) -> Button:
	var b := UiTheme.menu_button(text, cb)
	b.add_theme_font_size_override("font_size", 28)
	parent.add_child(b)
	return b


func _input(event: InputEvent) -> void:
	if GameState.phase != GameState.Phase.NIGHT:
		return
	if event.is_action_pressed("pause"):
		if not visible and _journal() and _journal().is_open():
			return  # the journal closes itself on Esc
		if not visible and Mission.dialogue_open():
			return  # the dialogue box owns Esc and the mouse while a conversation is up
		get_viewport().set_input_as_handled()
		if not visible:
			open()
		elif _options.visible:
			_hide_options()
		else:
			resume()
	elif visible and event.is_action_pressed("ui_cancel") and _options.visible:
		get_viewport().set_input_as_handled()
		_hide_options()


func open() -> void:
	visible = true
	_menu.visible = true
	_options.visible = false
	get_tree().paused = true
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	(_menu.get_child(0).get_child(0) as Label).text = "Night %d  ·  %s" % [GameState.day, GameState.time_string()]
	_first.grab_focus.call_deferred()


func resume() -> void:
	visible = false
	get_tree().paused = false
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func is_open() -> bool:
	return visible


func _journal() -> Node:
	return get_tree().get_first_node_in_group("journal")


## The journal opens over the paused game; closing it comes back to this menu.
func _open_journal() -> void:
	var j := _journal()
	if j == null:
		return
	visible = false
	j.call("open", open)


func _restart() -> void:
	get_tree().paused = false
	GameState.begin_night()


func _quit() -> void:
	get_tree().paused = false
	GameState.to_menu()


func _show_options() -> void:
	_menu.visible = false
	_options.visible = true


func _hide_options() -> void:
	_options.visible = false
	_menu.visible = true
	_first.grab_focus.call_deferred()
