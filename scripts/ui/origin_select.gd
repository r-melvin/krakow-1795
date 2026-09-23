extends Control
## Choose who you are. Left: origins and Man / Woman. Centre: the figure on a turntable. Right: blurb, goal,
## weakness, starting influence per faction and skills, so the trade-offs are visible. Emits `chosen`.

signal chosen(origin_id: String, sex: String, inclination: String)

const Preview := preload("res://scripts/ui/character_preview.gd")
const SKILL_MAX := 3

var _selected := ""
var _sex := "m"
var _incl := "unspoken"
var _incl_buttons: Dictionary = {}
var _start: Button
var _preview: SubViewportContainer
var _origin_buttons: Dictionary = {}
var _sex_buttons: Dictionary = {}
var _info: VBoxContainer
var _name: Label
var _blurb: Label
var _goal: Label
var _weak: Label
var _bars: VBoxContainer
var _skills: GridContainer
var _caption: Label


func _ready() -> void:
	theme = UiTheme.get_theme()
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var bg := ColorRect.new()
	bg.color = UiTheme.BG
	add_child(UiTheme.full_rect(bg))
	# A soft pool of light behind the figure.
	var glow := TextureRect.new()
	var gt := GradientTexture2D.new()
	gt.fill = GradientTexture2D.FILL_RADIAL
	gt.fill_from = Vector2(0.5, 0.55)
	gt.fill_to = Vector2(0.5, 0.0)
	var g := Gradient.new()
	g.set_color(0, Color(0.2, 0.22, 0.3, 0.9))
	g.set_color(1, Color(0.04, 0.05, 0.08, 0.0))
	gt.gradient = g
	gt.width = 512
	gt.height = 512
	glow.texture = gt
	glow.stretch_mode = TextureRect.STRETCH_SCALE
	glow.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	glow.offset_left = 380
	glow.offset_right = -560
	glow.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(glow)

	var root := HBoxContainer.new()
	root.add_theme_constant_override("separation", 0)
	add_child(UiTheme.full_rect(root))

	# ---- left: origins
	var left := UiTheme.panel()
	left.custom_minimum_size.x = 380
	var lsb := UiTheme.panel_box()
	lsb.set_corner_radius_all(0)
	lsb.border_width_left = 0
	lsb.border_width_top = 0
	lsb.border_width_bottom = 0
	lsb.content_margin_left = 48
	lsb.content_margin_top = 56
	left.add_theme_stylebox_override("panel", lsb)
	root.add_child(left)
	var lv := VBoxContainer.new()
	lv.add_theme_constant_override("separation", 8)
	left.add_child(lv)
	lv.add_child(UiTheme.kicker("Kraków, winter 1795"))
	lv.add_child(UiTheme.heading("Who are you?", 42))
	lv.add_child(UiTheme.spacer(18))
	var group := ButtonGroup.new()
	for id in GameState.origins:
		var b := Button.new()
		b.text = GameState.origins[id]["name"]
		b.toggle_mode = true
		b.button_group = group
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.theme_type_variation = "MenuButtonFlat"
		b.add_theme_font_size_override("font_size", 25)
		b.pressed.connect(_select.bind(id))
		b.focus_entered.connect(_select.bind(id))
		lv.add_child(b)
		_origin_buttons[id] = b
	lv.add_child(UiTheme.spacer(22))
	lv.add_child(UiTheme.kicker("Play as"))
	var sexrow := HBoxContainer.new()
	sexrow.add_theme_constant_override("separation", 10)
	var sg := ButtonGroup.new()
	for opt in [["m", "Man"], ["f", "Woman"]]:
		var b := Button.new()
		b.text = opt[1]
		b.toggle_mode = true
		b.button_group = sg
		b.button_pressed = opt[0] == _sex
		b.custom_minimum_size.x = 130
		b.pressed.connect(_set_sex.bind(opt[0]))
		sexrow.add_child(b)
		_sex_buttons[opt[0]] = b
	lv.add_child(sexrow)
	lv.add_child(UiTheme.spacer(6))
	lv.add_child(UiTheme.kicker("Drawn to"))
	var inclrow := HBoxContainer.new()
	inclrow.add_theme_constant_override("separation", 6)
	for opt in [["unspoken", "Unspoken"], ["women", "Women"], ["men", "Men"], ["both", "Both"]]:
		var ib := Button.new()
		ib.text = opt[1]
		ib.toggle_mode = true
		ib.button_pressed = opt[0] == _incl
		ib.custom_minimum_size = Vector2(0, 34)
		ib.pressed.connect(_set_incl.bind(opt[0]))
		inclrow.add_child(ib)
		_incl_buttons[opt[0]] = ib
	lv.add_child(inclrow)
	var incl_note := UiTheme.label("A private matter with public consequences in 1795. It opens some doors and closes others; the watch and the blackmailers care.", 13, UiTheme.TEXT_DIM, "italic")
	incl_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lv.add_child(incl_note)
	lv.add_child(UiTheme.spacer(18))
	lv.add_child(UiTheme.body("Where you were born decides who will listen to you, and who would see you hang.", 16, UiTheme.TEXT_DIM))
	var lspace := Control.new()
	lspace.size_flags_vertical = Control.SIZE_EXPAND_FILL
	lv.add_child(lspace)
	lv.add_child(UiTheme.button("Back to menu", GameState.to_menu, 0))
	lv.add_child(UiTheme.spacer(24))

	# ---- centre: turntable
	var centre := VBoxContainer.new()
	centre.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.add_child(centre)
	_preview = SubViewportContainer.new()
	_preview.set_script(Preview)
	_preview.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_preview.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	centre.add_child(_preview)
	_caption = UiTheme.label("", 18, UiTheme.TEXT_DIM, "display_italic")
	_caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	centre.add_child(_caption)
	centre.add_child(UiTheme.spacer(30))

	# ---- right: details
	var right := UiTheme.panel()
	right.custom_minimum_size.x = 560
	var rsb := UiTheme.panel_box()
	rsb.set_corner_radius_all(0)
	rsb.border_width_right = 0
	rsb.border_width_top = 0
	rsb.border_width_bottom = 0
	rsb.content_margin_left = 44
	rsb.content_margin_right = 52
	rsb.content_margin_top = 56
	rsb.content_margin_bottom = 40
	right.add_theme_stylebox_override("panel", rsb)
	root.add_child(right)
	_info = VBoxContainer.new()
	_info.add_theme_constant_override("separation", 10)
	right.add_child(_info)
	_info.add_child(UiTheme.kicker("Origin"))
	_name = UiTheme.heading("", 40)
	_info.add_child(_name)
	_blurb = UiTheme.body("", 18, UiTheme.TEXT)
	_info.add_child(_blurb)
	_info.add_child(HSeparator.new())
	_goal = _labelled(_info, "Goal")
	_weak = _labelled(_info, "Weakness")
	_info.add_child(HSeparator.new())
	_info.add_child(UiTheme.kicker("Starting influence"))
	_bars = VBoxContainer.new()
	_bars.add_theme_constant_override("separation", 5)
	_info.add_child(_bars)
	_info.add_child(UiTheme.spacer(4))
	_info.add_child(UiTheme.kicker("Skills"))
	_skills = GridContainer.new()
	_skills.columns = 2
	_skills.add_theme_constant_override("h_separation", 30)
	_skills.add_theme_constant_override("v_separation", 2)
	_info.add_child(_skills)
	var rspace := Control.new()
	rspace.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_info.add_child(rspace)
	_start = UiTheme.primary_button("Begin", _begin)
	_start.custom_minimum_size.y = 64
	_info.add_child(_start)

	var first: String = GameState.origin_id if GameState.origins.has(GameState.origin_id) else GameState.origins.keys()[0]
	_sex = GameState.gender if GameState.origin_id != "" else "m"
	_sex_buttons[_sex].button_pressed = true
	_origin_buttons[first].button_pressed = true
	_select(first)
	_origin_buttons[first].grab_focus.call_deferred()
	modulate.a = 0.0
	create_tween().tween_property(self, "modulate:a", 1.0, 0.4)


func _labelled(parent: Control, title: String) -> Label:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 14)
	var t := UiTheme.label(title, 16, UiTheme.BRASS, "bold")
	t.custom_minimum_size.x = 100
	h.add_child(t)
	var l := UiTheme.body("", 18, UiTheme.TEXT)
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(l)
	parent.add_child(h)
	return l


func _select(id: String) -> void:
	if id == _selected:
		return
	_selected = id
	if not _origin_buttons[id].button_pressed:
		_origin_buttons[id].set_pressed_no_signal(true)
	var o: Dictionary = GameState.origins[id]
	_name.text = o["name"] + ("  ·  " + str(o["gloss"]) if o.has("gloss") else "")
	_blurb.text = o["blurb"]
	_goal.text = o["goal"]
	_weak.text = o["weakness"]
	for c in _bars.get_children():
		c.queue_free()
	for fid in o["influence"]:
		var val := int(o["influence"][fid])
		_bars.add_child(UiTheme.stat_row(GameState.factions[fid]["name"], val, UiTheme.BRASS, 200))
	for c in _skills.get_children():
		c.queue_free()
	for s in o["skills"]:
		var n := int(o["skills"][s])
		var h := HBoxContainer.new()
		h.add_theme_constant_override("separation", 10)
		var l := UiTheme.label(String(s).capitalize(), 17, UiTheme.TEXT)
		l.custom_minimum_size.x = 118
		h.add_child(l)
		h.add_child(UiTheme.label("◆".repeat(n) + "◇".repeat(maxi(SKILL_MAX - n, 0)), 17, UiTheme.BRASS_BRIGHT if n > 0 else UiTheme.TEXT_DIM))
		_skills.add_child(h)
	_refresh_preview()


func _set_incl(i: String) -> void:
	_incl = i
	for k in _incl_buttons:
		_incl_buttons[k].set_pressed_no_signal(k == i)


func _set_sex(s: String) -> void:
	_sex = s
	if not _sex_buttons[s].button_pressed:
		_sex_buttons[s].set_pressed_no_signal(true)
	_refresh_preview()


func _refresh_preview() -> void:
	if _selected == "":
		return
	_preview.show_figure(GameState.figure_name_for(_selected, _sex))
	_caption.text = "%s, %s" % [GameState.origins[_selected]["name"], "a woman" if _sex == "f" else "a man"]


func preview_ready() -> bool:
	return _preview.is_ready()


func _begin() -> void:
	if _selected == "":
		return
	var tw := create_tween()
	tw.tween_property(self, "modulate:a", 0.0, 0.3)
	tw.tween_callback(func() -> void: chosen.emit(_selected, _sex, _incl))


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		GameState.to_menu()
