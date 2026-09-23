extends Control
## Dawn result: success or failure headline, the dawn report, influence and crackdown changes since the night
## began (GameState.night_start_influence), then Continue to the next day or back to the menu.
## Built on entering DAWN; GameState.mission_ended arrives right after and fills in the report.

const Backdrop := preload("res://scripts/ui/backdrop.gd")

var _headline: Label
var _kick: Label
var _report: VBoxContainer
var _deltas: VBoxContainer
var _continue: Button


func _ready() -> void:
	theme = UiTheme.get_theme()
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var bg := ColorRect.new()
	bg.color = UiTheme.BG
	add_child(UiTheme.full_rect(bg))
	var back := Control.new()
	back.set_script(Backdrop)
	back.set("darken", 0.55)
	back.set("drift", 0.3)
	add_child(back)
	# Dawn: a faint warm wash from the bottom of the screen.
	var wash := TextureRect.new()
	var gt := GradientTexture2D.new()
	gt.fill_from = Vector2(0.5, 1.0)
	gt.fill_to = Vector2(0.5, 0.3)
	var g := Gradient.new()
	g.set_color(0, Color(0.75, 0.45, 0.25, 0.28))
	g.set_color(1, Color(0.75, 0.45, 0.25, 0.0))
	gt.gradient = g
	wash.texture = gt
	wash.stretch_mode = TextureRect.STRETCH_SCALE
	wash.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(UiTheme.full_rect(wash))

	var center := CenterContainer.new()
	add_child(UiTheme.full_rect(center))
	var p := UiTheme.panel()
	p.custom_minimum_size = Vector2(1040, 0)
	center.add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 14)
	p.add_child(v)
	_kick = UiTheme.kicker("Dawn  ·  Day %d" % (GameState.day - 1))
	v.add_child(_kick)
	_headline = UiTheme.label("", 52, UiTheme.TEXT, "display_light")
	v.add_child(_headline)
	v.add_child(HSeparator.new())

	var cols := HBoxContainer.new()
	cols.add_theme_constant_override("separation", 40)
	v.add_child(cols)
	var lv := VBoxContainer.new()
	lv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lv.size_flags_stretch_ratio = 1.2
	lv.add_theme_constant_override("separation", 10)
	cols.add_child(lv)
	lv.add_child(UiTheme.kicker("Report"))
	_report = VBoxContainer.new()
	_report.add_theme_constant_override("separation", 8)
	lv.add_child(_report)
	var rv := VBoxContainer.new()
	rv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rv.add_theme_constant_override("separation", 6)
	cols.add_child(rv)
	rv.add_child(UiTheme.kicker("What changed"))
	_deltas = VBoxContainer.new()
	_deltas.add_theme_constant_override("separation", 6)
	rv.add_child(_deltas)

	v.add_child(UiTheme.spacer(8))
	v.add_child(HSeparator.new())
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_END
	row.add_theme_constant_override("separation", 14)
	v.add_child(row)
	row.add_child(UiTheme.label("Progress saved.", 16, UiTheme.TEXT_DIM, "italic"))
	var sp := Control.new()
	sp.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(sp)
	var menu := UiTheme.button("Menu", func() -> void: _leave(GameState.to_menu), 150)
	menu.custom_minimum_size.y = 60
	row.add_child(menu)
	_continue = UiTheme.primary_button("Continue", func() -> void: _leave(GameState.set_phase.bind(GameState.Phase.DAY)), 220)
	row.add_child(_continue)

	GameState.mission_ended.connect(_on_result)
	# If the result is already known (built late), show it now.
	show_result(GameState.last_night_success, GameState.last_night_summary)
	_continue.grab_focus.call_deferred()
	modulate.a = 0.0
	create_tween().tween_property(self, "modulate:a", 1.0, 0.6)


func _on_result(success: bool, summary: String) -> void:
	show_result(success, summary)


func show_result(success: bool, summary: String) -> void:
	_headline.text = "You came through the night." if success else "The watch had you."
	_headline.add_theme_color_override("font_color", UiTheme.BRASS_BRIGHT if success else Color("e29a86"))
	for c in _report.get_children():
		c.queue_free()
	var lines := PackedStringArray()
	for l in summary.split("\n", false):
		lines.append(l)
	var mission: Node = get_node_or_null("/root/Mission")
	var extra: String = str(mission.get("summary")) if mission and mission.get("summary") != null else ""
	if extra != "" and not extra in summary:
		for l in extra.split("\n", false):
			lines.append(l)
	if lines.is_empty():
		lines.append("The night passed without report.")
	for l in lines:
		_report.add_child(UiTheme.body("—  " + l, 19))
	_build_deltas()


func _build_deltas() -> void:
	for c in _deltas.get_children():
		c.queue_free()
	var any := false
	var start: Dictionary = GameState.night_start_influence
	for fid in GameState.factions:
		var f: Dictionary = GameState.factions[fid]
		if f["external"]:
			continue
		var now := GameState.get_influence(fid)
		var before := int(start.get(fid, now))
		var d := now - before
		if d == 0:
			continue
		any = true
		_deltas.add_child(_delta_row(f["name"], now, d, true))
	var dc := GameState.crackdown - GameState.night_start_crackdown
	if dc != 0 and not start.is_empty():
		any = true
		_deltas.add_child(_delta_row("Austrian crackdown", GameState.crackdown, dc, false))
	if not any:
		_deltas.add_child(UiTheme.body("Nothing moved. The city holds its breath.", 18, UiTheme.TEXT_DIM))


## `up_is_good`: influence gains are good news, crackdown gains are bad.
func _delta_row(name: String, value: int, delta: int, up_is_good: bool) -> HBoxContainer:
	var good := (delta > 0) == up_is_good
	var col := UiTheme.GOOD if good else UiTheme.BAD
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 12)
	var n := UiTheme.label(name, 18)
	n.custom_minimum_size.x = 190
	h.add_child(n)
	var b := UiTheme.bar(value, 100, UiTheme.BAD if not up_is_good else UiTheme.BRASS)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(b)
	var d := UiTheme.label("%+d" % delta, 18, col, "bold")
	d.custom_minimum_size.x = 44
	d.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	h.add_child(d)
	return h


func _leave(then: Callable) -> void:
	_continue.disabled = true
	var tw := create_tween()
	tw.tween_property(self, "modulate:a", 0.0, 0.3)
	tw.tween_callback(then)
