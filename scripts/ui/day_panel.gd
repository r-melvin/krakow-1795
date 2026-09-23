extends Control
## Day briefing: tonight's mission (Mission.title / Mission.briefing once the mission runner has prepared it),
## the state of the city (crackdown, faction influence, districts) and the choice to go out or return to menu.

signal go_out
signal to_menu

const Backdrop := preload("res://scripts/ui/backdrop.gd")
const DEFAULT_TITLE := "The Boatmen's Letter"
const DEFAULT_BRIEFING := "A message must reach the boatmen's safe house across the Rynek before dawn. The Austrian watch patrols the square; lanterns burn at the Cloth Hall and the Town Hall tower. Go unseen if you can."

var _summary := ""
var _summary_label: Label
var _go: Button


func _ready() -> void:
	theme = UiTheme.get_theme()
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	# The Mission autoload is looked up by path so this screen still works while the mission runner is absent.
	var mission: Node = get_node_or_null("/root/Mission")
	if mission and mission.has_method("prepare_for_day"):
		mission.call("prepare_for_day")
	var m_title: String = str(mission.get("title")) if mission and mission.get("title") != null else ""
	var m_brief: String = str(mission.get("briefing")) if mission and mission.get("briefing") != null else ""
	var m_objs: Array = mission.get("objectives") if mission and mission.get("objectives") is Array else []
	var bg := ColorRect.new()
	bg.color = UiTheme.BG
	add_child(UiTheme.full_rect(bg))
	var back := Control.new()
	back.set_script(Backdrop)
	back.set("darken", 0.62)
	back.set("snow_count", 120)
	back.set("drift", 0.4)
	add_child(back)

	var outer := VBoxContainer.new()
	outer.add_theme_constant_override("separation", 26)
	var m := UiTheme.margin(outer, 0)
	m.add_theme_constant_override("margin_left", 72)
	m.add_theme_constant_override("margin_right", 72)
	m.add_theme_constant_override("margin_top", 56)
	m.add_theme_constant_override("margin_bottom", 48)
	add_child(UiTheme.full_rect(m))

	# Header
	var head := HBoxContainer.new()
	outer.add_child(head)
	var hv := VBoxContainer.new()
	hv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(hv)
	hv.add_child(UiTheme.kicker("Day %d  ·  Kraków, winter 1795" % GameState.day))
	var who: String = GameState.origin.get("name", "Nobody")
	hv.add_child(UiTheme.label(who + (" (woman)" if GameState.gender == "f" else ""), 44, UiTheme.TEXT, "display_light"))
	hv.add_child(UiTheme.label(GameState.origin.get("goal", ""), 18, UiTheme.TEXT_DIM, "italic"))

	var cols := HBoxContainer.new()
	cols.size_flags_vertical = Control.SIZE_EXPAND_FILL
	cols.add_theme_constant_override("separation", 32)
	outer.add_child(cols)

	# Left: tonight's mission
	var lp := UiTheme.panel()
	lp.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lp.size_flags_stretch_ratio = 1.15
	cols.add_child(lp)
	var lv := VBoxContainer.new()
	lv.add_theme_constant_override("separation", 14)
	lp.add_child(lv)
	lv.add_child(UiTheme.kicker("Tonight"))
	var title: String = m_title if m_title != "" else DEFAULT_TITLE
	lv.add_child(UiTheme.heading(title, 42))
	lv.add_child(HSeparator.new())
	var brief: String = m_brief if m_brief != "" else DEFAULT_BRIEFING
	lv.add_child(UiTheme.body(brief, 20))
	if not m_objs.is_empty():
		lv.add_child(UiTheme.spacer(6))
		lv.add_child(UiTheme.kicker("Objectives"))
		for o in m_objs:
			var t: String = ("◇  " if not o.get("optional", false) else "◌  ") + str(o.get("text", ""))
			if o.get("optional", false):
				t += "  (optional)"
			lv.add_child(UiTheme.body(t, 18, UiTheme.TEXT if not o.get("optional", false) else UiTheme.TEXT_DIM))
	lv.add_child(UiTheme.spacer(6))
	lv.add_child(_where())
	_summary_label = UiTheme.body("", 17, UiTheme.TEXT_DIM)
	_summary_label.visible = false
	lv.add_child(_summary_label)
	var lspace := Control.new()
	lspace.size_flags_vertical = Control.SIZE_EXPAND_FILL
	lv.add_child(lspace)
	lv.add_child(UiTheme.label("Night falls at 21:00. The watch changes at midnight.", 16, UiTheme.TEXT_DIM, "italic"))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 14)
	lv.add_child(row)
	_go = UiTheme.primary_button("Go out tonight", func() -> void: _leave(go_out), 280)
	row.add_child(_go)
	var menu := UiTheme.button("Return to menu", func() -> void: _leave(to_menu), 200)
	menu.custom_minimum_size.y = 60
	row.add_child(menu)
	to_menu.connect(GameState.to_menu)

	# Right: the city
	var rp := UiTheme.panel()
	rp.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cols.add_child(rp)
	var rv := VBoxContainer.new()
	rv.add_theme_constant_override("separation", 8)
	rp.add_child(rv)
	rv.add_child(UiTheme.kicker("The city"))
	var ch := HBoxContainer.new()
	ch.add_theme_constant_override("separation", 14)
	var cl := UiTheme.label("Austrian crackdown", 18)
	cl.custom_minimum_size.x = 200
	ch.add_child(cl)
	var cb := UiTheme.bar(GameState.crackdown, 100, UiTheme.BAD)
	cb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ch.add_child(cb)
	var cv := UiTheme.label(str(GameState.crackdown), 18, UiTheme.BAD, "bold")
	cv.custom_minimum_size.x = 36
	cv.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	ch.add_child(cv)
	rv.add_child(ch)
	rv.add_child(UiTheme.label("Districts held: %d of %d" % [GameState.controlled_district_count(), GameState.districts.size()], 17, UiTheme.TEXT_DIM))
	rv.add_child(HSeparator.new())
	rv.add_child(UiTheme.kicker("Your influence"))
	for fid in GameState.factions:
		var f: Dictionary = GameState.factions[fid]
		if f["external"]:
			continue
		var r := UiTheme.stat_row(f["name"], int(f["influence"]), UiTheme.BRASS, 200)
		r.tooltip_text = f["agenda"]
		rv.add_child(r)
	rv.add_child(HSeparator.new())
	rv.add_child(UiTheme.kicker("Occupiers"))
	var occ := GridContainer.new()
	occ.columns = 2
	occ.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	occ.add_theme_constant_override("h_separation", 14)
	occ.add_theme_constant_override("v_separation", 8)
	for fid in ["austria", "russia", "prussia"]:
		if not GameState.factions.has(fid):
			continue
		var f: Dictionary = GameState.factions[fid]
		var n := UiTheme.label(f["name"], 17, UiTheme.TEXT)
		n.custom_minimum_size.x = 200
		n.tooltip_text = f["agenda"]
		occ.add_child(n)
		# Strength: how much force the power can bring to bear on Kraków (garrison, money, agents). A bar in the
		# occupier's dull red, with the meaning in the tooltip rather than a bare number on the page.
		var b := UiTheme.bar(float(f["strength"]), 100.0, Color(0.62, 0.26, 0.20), 10.0)
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.tooltip_text = "Strength: the force %s can bring to bear on the city (garrison, money, agents). %s" % [f["name"], _strength_word(int(f["strength"]))]
		occ.add_child(b)
	rv.add_child(occ)

	_go.grab_focus.call_deferred()
	modulate.a = 0.0
	create_tween().tween_property(self, "modulate:a", 1.0, 0.45)
	set_summary(_summary)


## Where tonight happens and what the player brings to it.
func _where() -> Control:
	var g := GridContainer.new()
	g.columns = 2
	g.add_theme_constant_override("h_separation", 18)
	g.add_theme_constant_override("v_separation", 6)
	var d: Dictionary = GameState.districts.get("rynek", {})
	if not d.is_empty():
		var held: String = GameState.factions.get(d["controller"], {}).get("name", "?")
		_fact(g, "District", "%s, held by %s" % [d["name"], held])
		_fact(g, "Watch", "%s   ·   unrest %d" % ["●".repeat(int(d["watch"])) + "○".repeat(maxi(5 - int(d["watch"]), 0)), int(d["unrest"])])
	_fact(g, "Your edge", "Stealth %d   ·   Streetwise %d   ·   Eloquence %d" % [GameState.skill("stealth"), GameState.skill("streetwise"), GameState.skill("eloquence")])
	return g


func _strength_word(v: int) -> String:
	if v >= 80:
		return "Overwhelming."
	if v >= 60:
		return "Strong."
	if v >= 40:
		return "Contested."
	return "Thin on the ground."


func _fact(g: GridContainer, k: String, v: String) -> void:
	var kl := UiTheme.label(k.to_upper(), 14, UiTheme.BRASS, "bold")
	kl.custom_minimum_size.x = 110
	g.add_child(kl)
	g.add_child(UiTheme.label(v, 18, UiTheme.TEXT))


## Kept for callers that pass a line to show under the briefing.
func set_summary(s: String) -> void:
	_summary = s
	if _summary_label:
		_summary_label.text = s
		_summary_label.visible = s != ""


func _leave(sig: Signal) -> void:
	_go.disabled = true
	var tw := create_tween()
	tw.tween_property(self, "modulate:a", 0.0, 0.3)
	tw.tween_callback(func() -> void: sig.emit())


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		_leave(to_menu)
