extends Control

## Title card: painted night skyline, the title in a display serif, then any key or click goes to the main menu.

const Backdrop := preload("res://scripts/ui/backdrop.gd")
const ContentNotice := preload("res://scripts/ui/content_notice.gd")
static var notice_shown := false   # once per launch

var _content: VBoxContainer
var _prompt: Label
var _leaving := false
var _ready_for_input := false


func _ready() -> void:
	theme = UiTheme.get_theme()
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var bg := ColorRect.new()
	bg.color = UiTheme.BG
	add_child(UiTheme.full_rect(bg))
	var back := Control.new()
	back.set_script(Backdrop)
	add_child(back)

	_content = VBoxContainer.new()
	_content.alignment = BoxContainer.ALIGNMENT_CENTER
	_content.add_theme_constant_override("separation", 6)
	add_child(UiTheme.full_rect(_content))
	_content.offset_bottom = -170

	var kick := UiTheme.label("A  TALE  OF  THE  THIRD  PARTITION", 17, UiTheme.BRASS, "bold")
	kick.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_content.add_child(kick)
	var title := UiTheme.label("KRAKÓW 1795", 132, UiTheme.TEXT, "display_light")
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.7))
	title.add_theme_constant_override("shadow_offset_y", 4)
	title.add_theme_constant_override("shadow_outline_size", 10)
	_content.add_child(title)
	var rule := HBoxContainer.new()
	rule.alignment = BoxContainer.ALIGNMENT_CENTER
	var line := ColorRect.new()
	line.color = UiTheme.BRASS
	line.custom_minimum_size = Vector2(420, 1)
	rule.add_child(line)
	_content.add_child(rule)
	_content.add_child(UiTheme.spacer(10))
	var sub := UiTheme.label("The Commonwealth is gone. The city is not.", 30, UiTheme.TEXT, "display_italic")
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_content.add_child(sub)

	_prompt = UiTheme.label("Press any key", 20, UiTheme.BRASS_BRIGHT, "regular")
	_prompt.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_prompt.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	_prompt.offset_top = -150
	_prompt.offset_bottom = -110
	_prompt.offset_left = -300
	_prompt.offset_right = 300
	add_child(_prompt)

	modulate.a = 0.0
	_content.modulate.a = 0.0
	_prompt.modulate.a = 0.0
	var tw := create_tween()
	tw.tween_property(self, "modulate:a", 1.0, 0.8)
	tw.tween_property(_content, "modulate:a", 1.0, 1.4).set_trans(Tween.TRANS_SINE)
	tw.tween_callback(func() -> void: _ready_for_input = true)
	tw.tween_property(_prompt, "modulate:a", 1.0, 0.6)
	tw.tween_callback(_pulse)
	# Let an impatient player skip the fade after a short beat.
	create_tween().tween_callback(func() -> void: _ready_for_input = true).set_delay(0.5)


func _pulse() -> void:
	if _leaving:
		return
	var tw := create_tween().set_loops()
	tw.tween_property(_prompt, "modulate:a", 0.35, 1.2).set_trans(Tween.TRANS_SINE)
	tw.tween_property(_prompt, "modulate:a", 1.0, 1.2).set_trans(Tween.TRANS_SINE)


func _input(event: InputEvent) -> void:
	if _leaving or not _ready_for_input:
		return
	var go: bool = (event is InputEventKey and event.pressed and not event.echo) \
			or (event is InputEventMouseButton and event.pressed) \
			or (event is InputEventJoypadButton and event.pressed)
	if go:
		get_viewport().set_input_as_handled()
		leave()


func leave() -> void:
	if _leaving:
		return
	_leaving = true
	var tw := create_tween()
	tw.tween_property(self, "modulate:a", 0.0, 0.6).set_trans(Tween.TRANS_SINE)
	tw.tween_callback(func() -> void:
		if GameState.phase != GameState.Phase.SPLASH:
			return
		if notice_shown or "--smoke" in OS.get_cmdline_user_args() and "--shot-ui" not in " ".join(OS.get_cmdline_user_args()):
			GameState.to_menu()
			return
		notice_shown = true
		var n := Control.new()
		n.set_script(ContentNotice)
		get_parent().add_child(n)
		n.accepted.connect(func() -> void:
			n.queue_free()
			if GameState.phase == GameState.Phase.SPLASH:
				GameState.to_menu()))
