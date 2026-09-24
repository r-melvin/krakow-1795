extends Control
## Day briefing (docs/GDD.md "Campaign"). Three columns:
##  - Tonight: the arc night and the institution at stake, the mission briefing and objectives, go out.
##  - The whisper network: rumours in play (reach, truth as far as you know, planted by you), leads to follow
##    (one a day brings that person into tonight), people found and their levers, the heir ("If you fall").
##  - The day: hours left and the day actions (Campaign.day_actions), planting a rumour through a channel, the
##    passage urchins, relations between factions that hurt now, what the day has done, and the city (crackdown,
##    notoriety, influence and loyalty, districts, institutions taken).
## Before the briefing, a pending succession card, trial, coup or the ending takes the screen.
## Everything goes through Mission.campaign (scripts/mission/campaign.gd); the screen rebuilds on its `changed`.

signal go_out
signal to_menu

const Backdrop := preload("res://scripts/ui/backdrop.gd")
const DEFAULT_TITLE := "The Boatmen's Letter"
const DEFAULT_BRIEFING := "A message must reach the boatmen's safe house across the Rynek before dawn."

var _summary := ""
var _summary_label: Label
var _go: Button
var _more: Label
var _root: Control
var _camp: Node
var _plant_rumour: OptionButton
var _plant_channel: OptionButton
var _plant_note: Label
var _urchin_opt: OptionButton
var _pending_rebuild := false
var _tab := "rumours"
var _mid_scroll: ScrollContainer


func _ready() -> void:
	theme = UiTheme.get_theme()
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var mission: Node = get_node_or_null("/root/Mission")
	_camp = mission.get("campaign") if mission else null
	if _camp and _camp.has_method("prepare_day"):
		_camp.call("prepare_day")
		_camp.changed.connect(_queue_rebuild)
	elif mission and mission.has_method("prepare_for_day"):
		mission.call("prepare_for_day")
	var bg := ColorRect.new()
	bg.color = UiTheme.BG
	add_child(UiTheme.full_rect(bg))
	var back := Control.new()
	back.set_script(Backdrop)
	back.set("darken", 0.66)
	back.set("snow_count", 110)
	back.set("drift", 0.4)
	add_child(back)
	to_menu.connect(GameState.to_menu)
	_build()
	modulate.a = 0.0
	create_tween().tween_property(self, "modulate:a", 1.0, 0.45)


func _queue_rebuild() -> void:
	if _pending_rebuild:
		return
	_pending_rebuild = true
	(func() -> void:
		_pending_rebuild = false
		if is_inside_tree():
			_build()).call_deferred()


func _build() -> void:
	if _root:
		_root.queue_free()
	var m := MarginContainer.new()
	for side in ["left", "right"]:
		m.add_theme_constant_override("margin_" + side, 40)
	m.add_theme_constant_override("margin_top", 26)
	m.add_theme_constant_override("margin_bottom", 22)
	_root = UiTheme.full_rect(m)
	add_child(_root)
	if _camp and not (_camp.call("card") as Dictionary).is_empty():
		_card_screen(m)
		return
	if _camp and bool(_camp.call("ended")):
		_ending_screen(m)
		return
	if _camp and bool(_camp.call("trial_pending")):
		_choice_screen(m, "The magistrate's sentence", "Two arrests in a row. The magistrate of the Town Hall, in a wig older than the Partitions, reads the sentence: the whipping post, or a night's banishment from the Old Town.",
				[["Twenty-five strokes at the whipping post", "Notoriety cleared; you go out tonight with one breath of health.", func() -> void: _camp.call("do_trial", "flogging")],
				 ["Banishment for a night", "Tonight's work goes ahead without you, badly: a lost night for the arc.", func() -> void: _camp.call("do_trial", "exile")]])
		return
	if _camp and not (_camp.call("coup") as Dictionary).is_empty():
		var c: Dictionary = _camp.call("coup")
		var fname: String = _camp.call("fname", str(c["faction"]))
		_choice_screen(m, "The movement is losing faith", "The %s's people are in the boatmen's cellar at first light: %s. They want a change at the head of the movement, or a price." % [fname, c["why"]],
				[["Concede: give the %s what it wants" % fname, "Coins, and ground with its rivals. You keep the seat.", func() -> void: _camp.call("resolve_coup", "concede")],
				 ["Stand firm and talk them down", "Eloquence decides. Fail, and they impose their candidate.", func() -> void: _camp.call("resolve_coup", "firm")],
				 ["Step aside", "Their candidate takes the banner; you become a rumour.", func() -> void: _camp.call("resolve_coup", "yield")]])
		return
	var outer := VBoxContainer.new()
	outer.add_theme_constant_override("separation", 12)
	m.add_child(outer)
	outer.add_child(_header())
	var cols := HBoxContainer.new()
	cols.size_flags_vertical = Control.SIZE_EXPAND_FILL
	cols.add_theme_constant_override("separation", 20)
	outer.add_child(cols)
	cols.add_child(_tonight_col())
	cols.add_child(_whisper_col())
	cols.add_child(_day_col())
	if _go:
		_go.grab_focus.call_deferred()


func _header() -> Control:
	var head := HBoxContainer.new()
	var hv := VBoxContainer.new()
	hv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(hv)
	var n: int = int(_camp.call("night")) if _camp else GameState.day
	hv.add_child(UiTheme.kicker("Day %d  ·  Night %d of 7  ·  Kraków, winter 1795" % [GameState.day, mini(n, 7)]))
	var leader: String = str(_camp.call("st").get("leader", "")) if _camp else ""
	var who: String = GameState.origin.get("name", "Nobody")
	hv.add_child(UiTheme.label((leader + ", " if leader != "" and leader != who else "") + who + (" (woman)" if GameState.gender == "f" else ""), 30, UiTheme.TEXT, "display_light"))
	# institutions taken, as a row of seals
	var seals := HBoxContainer.new()
	seals.add_theme_constant_override("separation", 6)
	seals.alignment = BoxContainer.ALIGNMENT_END
	if _camp:
		for e in _camp.call("arc"):
			var r: Dictionary = _camp.call("result_of", str((e["options"] as Array)[0]["mission"]))
			var won := bool(r.get("success", false))
			var lost := not r.is_empty() and not won
			var l := UiTheme.label("◆" if won else ("◇" if not lost else "✕"), 22, UiTheme.BRASS_BRIGHT if won else (UiTheme.BAD if lost else UiTheme.TEXT_DIM), "bold")
			l.tooltip_text = "Night %d: %s%s" % [int(e["night"]), e.get("institution", ""), " (taken)" if won else (" (lost)" if lost else "")]
			l.mouse_filter = Control.MOUSE_FILTER_STOP
			seals.add_child(l)
	var sv := VBoxContainer.new()
	sv.add_child(UiTheme.label("Institutions taken", 13, UiTheme.BRASS, "bold"))
	sv.add_child(seals)
	head.add_child(sv)
	return head


# ------------------------------------------------------------------ tonight

func _tonight_col() -> Control:
	var mission: Node = get_node_or_null("/root/Mission")
	var lp := UiTheme.panel()
	lp.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lp.size_flags_stretch_ratio = 1.25
	var lv := VBoxContainer.new()
	lv.add_theme_constant_override("separation", 10)
	lp.add_child(lv)
	var inst := ""
	if _camp:
		inst = str((_camp.call("arc_entry", int(_camp.call("night"))) as Dictionary).get("institution", ""))
	lv.add_child(UiTheme.kicker("Tonight" + ("  ·  at stake: " + inst if inst != "" else "")))
	var m_title: String = str(mission.get("title")) if mission else ""
	lv.add_child(UiTheme.heading(m_title if m_title != "" else DEFAULT_TITLE, 28))
	lv.add_child(HSeparator.new())
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	lv.add_child(scroll)
	var sv := VBoxContainer.new()
	sv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sv.add_theme_constant_override("separation", 10)
	scroll.add_child(sv)
	var brief: String = str(mission.get("briefing")) if mission else ""
	sv.add_child(UiTheme.body(brief if brief != "" else DEFAULT_BRIEFING, 16))
	var objs: Array = mission.get("objectives") if mission and mission.get("objectives") is Array else []
	if not objs.is_empty():
		sv.add_child(UiTheme.kicker("Objectives"))
		for o in objs:
			var t: String = ("◇  " if not o.get("optional", false) else "◌  ") + str(o.get("text", "")) + ("  (optional)" if o.get("optional", false) else "")
			sv.add_child(UiTheme.body(t, 15, UiTheme.TEXT if not o.get("optional", false) else UiTheme.TEXT_DIM))
	var lead := _lead_line()
	if lead != "":
		sv.add_child(UiTheme.body("Lead tonight: " + lead, 15, UiTheme.BRASS_BRIGHT))
	sv.add_child(_where())
	_summary_label = UiTheme.body("", 15, UiTheme.TEXT_DIM)
	_summary_label.visible = false
	sv.add_child(_summary_label)
	_more = UiTheme.label("▾  more below: scroll", 13, UiTheme.BRASS, "italic")
	_more.visible = false
	lv.add_child(_more)
	scroll.get_v_scroll_bar().changed.connect(func() -> void:
		var vb := scroll.get_v_scroll_bar()
		_more.visible = vb.max_value > vb.page + 1.0 and vb.value + vb.page < vb.max_value - 1.0)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	lv.add_child(row)
	if _camp and bool(_camp.call("exiled_tonight")):
		_go = UiTheme.primary_button("Spend the night outside the walls", func() -> void: _leave(func() -> void: _camp.call("pass_exile")), 300)
	else:
		_go = UiTheme.primary_button("Go out tonight", func() -> void: _leave(go_out.emit), 240)
	row.add_child(_go)
	var menu := UiTheme.button("Menu", func() -> void: _leave(to_menu.emit), 120)
	menu.custom_minimum_size.y = 56
	row.add_child(menu)
	set_summary(_summary)
	return lp


func _lead_line() -> String:
	if _camp == null:
		return ""
	var lid := str(_camp.call("st").get("lead", ""))
	if lid == "":
		return ""
	if lid.begins_with("sq:"):
		return str((_camp.get("db").get("side_quests", {}) as Dictionary).get(lid.trim_prefix("sq:"), {}).get("title", lid)) + " (marked on your map)"
	var p: Dictionary = _camp.call("person", lid)
	return "%s, %s (marked on your map)" % [p.get("name", lid), p.get("where", "")]


func _where() -> Control:
	var g := GridContainer.new()
	g.columns = 2
	g.add_theme_constant_override("h_separation", 14)
	g.add_theme_constant_override("v_separation", 4)
	var mission: Node = get_node_or_null("/root/Mission")
	var did := str(mission.get("data").get("district", "rynek")) if mission and mission.get("data") is Dictionary else "rynek"
	if did == "old_town":
		did = "rynek"
	var d: Dictionary = GameState.districts.get(did, GameState.districts.get("rynek", {}))
	if not d.is_empty():
		var c := str(d["controller"])
		var held: String = "the movement" if c == "movement" else str(GameState.factions.get(c, {}).get("name", c))
		_fact(g, "District", "%s, held by %s" % [d["name"], held])
		_fact(g, "Watch", "%s   ·   unrest %d" % ["●".repeat(int(d["watch"])) + "○".repeat(maxi(5 - int(d["watch"]), 0)), int(d["unrest"])])
	_fact(g, "Your edge", "Stealth %d  ·  Streetwise %d  ·  Eloquence %d" % [GameState.skill("stealth"), GameState.skill("streetwise"), GameState.skill("eloquence")])
	return g


func _fact(g: GridContainer, k: String, v: String) -> void:
	var kl := UiTheme.label(k.to_upper(), 13, UiTheme.BRASS, "bold")
	kl.custom_minimum_size.x = 96
	g.add_child(kl)
	g.add_child(UiTheme.label(v, 15, UiTheme.TEXT))


# ------------------------------------------------------------------ the whisper network

func _whisper_col() -> Control:
	var p := UiTheme.panel()
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	p.size_flags_stretch_ratio = 1.0
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 8)
	p.add_child(v)
	v.add_child(UiTheme.kicker("The whisper network"))
	var tabs := HBoxContainer.new()
	tabs.add_theme_constant_override("separation", 6)
	v.add_child(tabs)
	for t in [["rumours", "Rumours"], ["leads", "Leads"], ["people", "People"]]:
		var b := UiTheme.button(t[1], show_tab.bind(t[0]), 0)
		b.toggle_mode = true
		b.button_pressed = _tab == t[0]
		b.custom_minimum_size.y = 34
		tabs.add_child(b)
	v.add_child(HSeparator.new())
	_mid_scroll = ScrollContainer.new()
	_mid_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_mid_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	v.add_child(_mid_scroll)
	var sv := VBoxContainer.new()
	sv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sv.add_theme_constant_override("separation", 8)
	_mid_scroll.add_child(sv)
	if _camp == null:
		sv.add_child(UiTheme.body("The city is quiet.", 15, UiTheme.TEXT_DIM))
		return p
	match _tab:
		"rumours":
			_fill_rumours(sv)
		"leads":
			_fill_leads(sv)
		"people":
			_fill_people(sv)
	var heir: String = _camp.call("nominee_name")
	if heir != "":
		v.add_child(UiTheme.label("If you fall: %s" % heir, 15, UiTheme.BRASS_BRIGHT, "italic"))
	elif not (_camp.call("heirs") as Array).is_empty():
		v.add_child(UiTheme.label("If you fall: no heir named. The strongest faction will choose.", 14, UiTheme.TEXT_DIM, "italic"))
	return p


func show_tab(t: String) -> void:
	_tab = t
	_build()


func _fill_rumours(sv: VBoxContainer) -> void:
	var r = _camp.get("rumours")
	var known: Array = r.known()
	if known.is_empty():
		sv.add_child(UiTheme.body("You have heard nothing worth repeating yet. Stand near people at night and listen; the urchins sell what they hear.", 15, UiTheme.TEXT_DIM))
		return
	for rid in known:
		var d: Dictionary = r.def(rid)
		var s: Dictionary = r.state_of(rid)
		var box := VBoxContainer.new()
		box.add_theme_constant_override("separation", 2)
		var top := HBoxContainer.new()
		top.add_theme_constant_override("separation", 8)
		var kind := str(d.get("kind", ""))
		var name := UiTheme.label(str(d.get("subject", rid)) + (" (%s)" % kind if kind != "" else ""), 17, UiTheme.BRASS_BRIGHT, "display")
		name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		top.add_child(name)
		var status := str(s.get("status", "whisper"))
		var truth: String = str(Mission.journal.get("rumours", {}).get(rid, {}).get("truth", "unknown"))
		var tag: String = {"true": "true", "false": "false", "unknown": "?"}.get(truth, "?")
		var tl := UiTheme.label(("planted  ·  " if bool(s.get("planted", false)) else "") + status + "  ·  " + tag, 13,
				UiTheme.BAD if status == "disproved" else (UiTheme.GOOD if truth == "true" else UiTheme.TEXT_DIM), "bold")
		top.add_child(tl)
		box.add_child(top)
		box.add_child(UiTheme.body(str(d.get("text", "")), 14, UiTheme.TEXT))
		var bar := UiTheme.bar(float(r.reach(rid)), 100.0, UiTheme.BRASS if status != "disproved" else UiTheme.BAD, 6.0)
		bar.tooltip_text = "Reach: %d%% of the people who talk. At %d%% it takes hold." % [r.reach(rid), r.threshold()]
		box.add_child(bar)
		sv.add_child(box)


func _fill_leads(sv: VBoxContainer) -> void:
	var leads: Array = _camp.call("leads")
	if leads.is_empty():
		sv.add_child(UiTheme.body("No leads. A rumour about a person is a lead: follow it and they will be where the rumour says tonight.", 15, UiTheme.TEXT_DIM))
		return
	sv.add_child(UiTheme.body("Choose one to follow tonight. The person will be on your map.", 14, UiTheme.TEXT_DIM))
	for l in leads:
		var b := UiTheme.button(("●  " if l["chosen"] else "○  ") + str(l["label"]), func() -> void: _camp.call("choose_lead", str(l["id"])), 0)
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.custom_minimum_size.y = 38
		b.clip_text = true
		b.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		b.tooltip_text = str(l["desc"])
		b.disabled = bool(l.get("mission_only", false))
		sv.add_child(b)
		sv.add_child(UiTheme.body(str(l["desc"]), 13, UiTheme.TEXT_DIM))


func _fill_people(sv: VBoxContainer) -> void:
	var any := false
	var jp: Dictionary = Mission.journal.get("people", {})
	for pid in (_camp.call("st")["people"] as Dictionary):
		if not bool(_camp.call("found", pid)):
			continue
		any = true
		var p: Dictionary = _camp.call("person", pid)
		var e: Dictionary = jp.get(pid, {})
		var line := str(p.get("name", pid)) + ("  (historical)" if bool(p.get("historical", false)) else "") + ("  ·  your heir" if str(_camp.call("nominee")) == pid else "")
		sv.add_child(UiTheme.label(line, 16, UiTheme.BRASS_BRIGHT, "display"))
		sv.add_child(UiTheme.body(str(e.get("lever", p.get("role", ""))), 13, UiTheme.TEXT))
	if not any:
		sv.add_child(UiTheme.body("Nobody found yet. Follow a lead.", 15, UiTheme.TEXT_DIM))
	var lv: Dictionary = _camp.call("st")["levers"]
	if not lv.is_empty():
		sv.add_child(UiTheme.kicker("Levers"))
		for k in lv:
			sv.add_child(UiTheme.body("◆  %s" % lv[k].get("name", k), 14, UiTheme.TEXT))


# ------------------------------------------------------------------ the day

func _day_col() -> Control:
	var p := UiTheme.panel()
	p.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	p.size_flags_stretch_ratio = 1.1
	p.custom_minimum_size.x = 0
	p.clip_contents = true
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	p.add_child(scroll)
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_theme_constant_override("separation", 6)
	scroll.add_child(v)
	if _camp == null:
		_city(v)
		return p
	var ds: Dictionary = _camp.call("day_state")
	v.add_child(UiTheme.kicker("The day  ·  %d of %d hours  ·  %d zł" % [int(ds.get("left", 0)), int(ds.get("max", 0)), GameState.coins]))
	for a in _camp.call("day_actions"):
		var b := UiTheme.button(str(a["label"]), func() -> void: _camp.call("do_action", str(a["id"])), 0)
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.custom_minimum_size.y = 34
		b.disabled = not bool(a["enabled"])
		b.tooltip_text = str(a["desc"]) + ("\n" + str(a["why"]) if str(a["why"]) != "" else "")
		b.add_theme_font_size_override("font_size", 15)
		b.clip_text = true
		b.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		b.custom_minimum_size.x = 0
		v.add_child(b)
	v.add_child(_plant_box())
	v.add_child(_urchin_box())
	var rel: Array = _camp.call("relation_lines")
	if not rel.is_empty():
		v.add_child(UiTheme.kicker("Between the factions"))
		for l in rel:
			v.add_child(UiTheme.body(str(l["text"]), 13, UiTheme.BAD if bool(l["bad"]) else UiTheme.TEXT_DIM))
	var feed: Array = ds.get("feed", [])
	if not feed.is_empty():
		v.add_child(UiTheme.kicker("Today"))
		for f in feed:
			v.add_child(UiTheme.body("—  " + str(f), 13, UiTheme.TEXT))
	v.add_child(HSeparator.new())
	_city(v)
	return p


func _plant_box() -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 4)
	box.add_child(UiTheme.kicker("Plant a rumour"))
	var r = _camp.get("rumours")
	_plant_rumour = OptionButton.new()
	_plant_channel = OptionButton.new()
	for rid in r.plantable():
		_plant_rumour.add_item(str(r.def(rid).get("subject", rid)))
		_plant_rumour.set_item_metadata(_plant_rumour.item_count - 1, rid)
	for c in _camp.call("channels"):
		_plant_channel.add_item("%s (%d zł)" % [c["name"], int(c["cost"])])
		var i := _plant_channel.item_count - 1
		_plant_channel.set_item_metadata(i, c["id"])
		_plant_channel.set_item_disabled(i, not bool(c["enabled"]))
		_plant_channel.set_item_tooltip(i, str(c["desc"]) + ("\n" + str(c["why"]) if str(c["why"]) != "" else ""))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	for ob in [_plant_rumour, _plant_channel]:
		ob.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		ob.clip_text = true
		ob.fit_to_longest_item = false
		ob.custom_minimum_size.x = 60
	row.add_child(_plant_rumour)
	row.add_child(_plant_channel)
	box.add_child(row)
	_plant_note = UiTheme.body("", 13, UiTheme.TEXT_DIM)
	box.add_child(_plant_note)
	var go := UiTheme.button("Plant it", func() -> void:
		if _plant_rumour.selected < 0 or _plant_channel.selected < 0:
			return
		_camp.call("plant", str(_plant_rumour.get_item_metadata(_plant_rumour.selected)), str(_plant_channel.get_item_metadata(_plant_channel.selected))), 0)
	go.custom_minimum_size.y = 32
	go.disabled = int(_camp.call("actions_left")) <= 0 or _plant_rumour.item_count == 0
	box.add_child(go)
	var upd := func(_i: int = 0) -> void:
		if _plant_rumour.selected < 0:
			_plant_note.text = "Nothing left to plant."
			return
		var rid := str(_plant_rumour.get_item_metadata(_plant_rumour.selected))
		var d: Dictionary = r.def(rid)
		var truth: Variant = d.get("truth", true)
		var tt := "true" if (truth is bool and truth) else ("false" if truth is bool else ("true" if r.truth_of(rid) else "false, for now"))
		_plant_note.text = "\"%s\" (%s). %s" % [d.get("text", ""), tt, d.get("plant_note", "")]
	_plant_rumour.item_selected.connect(upd)
	for i in _plant_channel.item_count:
		if not _plant_channel.is_item_disabled(i):
			_plant_channel.select(i)
			break
	upd.call()
	return box


func _urchin_box() -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 4)
	box.add_child(UiTheme.kicker("The passage urchins"))
	box.add_child(UiTheme.body("1 zł, no hour spent. Honest about %d%% of the time." % int(round(float(_camp.call("urchin_truth_chance")) * 100.0)), 13, UiTheme.TEXT_DIM))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	_urchin_opt = OptionButton.new()
	_urchin_opt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_urchin_opt.clip_text = true
	_urchin_opt.fit_to_longest_item = false
	_urchin_opt.custom_minimum_size.x = 60
	var enabled := false
	for o in _camp.call("urchin_offers"):
		_urchin_opt.add_item(str(o["label"]))
		var i := _urchin_opt.item_count - 1
		_urchin_opt.set_item_metadata(i, o["id"])
		_urchin_opt.set_item_tooltip(i, str(o["desc"]))
		enabled = enabled or bool(o["enabled"])
	row.add_child(_urchin_opt)
	var b := UiTheme.button("Ask Staś", func() -> void:
		if _urchin_opt.selected >= 0:
			_camp.call("urchin_buy", str(_urchin_opt.get_item_metadata(_urchin_opt.selected))), 0)
	b.disabled = not enabled
	b.custom_minimum_size.y = 32
	row.add_child(b)
	box.add_child(row)
	return box


func _city(v: VBoxContainer) -> void:
	v.add_child(UiTheme.kicker("The city"))
	var ch := HBoxContainer.new()
	ch.add_theme_constant_override("separation", 10)
	var cl := UiTheme.label("Crackdown", 15)
	cl.custom_minimum_size.x = 120
	ch.add_child(cl)
	var cb := UiTheme.bar(GameState.crackdown, 100, UiTheme.BAD, 10.0)
	cb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ch.add_child(cb)
	ch.add_child(UiTheme.label(str(GameState.crackdown), 15, UiTheme.BAD, "bold"))
	v.add_child(ch)
	var nh := HBoxContainer.new()
	nh.add_theme_constant_override("separation", 10)
	var nl := UiTheme.label("Notoriety", 15)
	nl.custom_minimum_size.x = 120
	nh.add_child(nl)
	var nb := UiTheme.bar(GameState.notoriety(), 100, Color(0.75, 0.45, 0.3), 10.0)
	nb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	nh.add_child(nb)
	nh.add_child(UiTheme.label(str(int(GameState.notoriety())), 15, Color(0.85, 0.55, 0.4), "bold"))
	v.add_child(nh)
	var held := 0
	for d in GameState.districts.values():
		if str(d["controller"]) == "movement":
			held += 1
	v.add_child(UiTheme.label("Districts held by the movement: %d of %d" % [held, GameState.districts.size()], 14, UiTheme.TEXT_DIM))
	for fid in GameState.factions:
		var f: Dictionary = GameState.factions[fid]
		if f["external"]:
			continue
		var r := UiTheme.stat_row(f["name"], int(f["influence"]), UiTheme.BRASS, 150)
		var gr: int = int(_camp.call("grievance", fid)) if _camp else 0
		r.tooltip_text = "%s\nInfluence %d · loyalty %d · fear %d%s" % [f["agenda"], int(f["influence"]), GameState.get_loyalty(fid), int(f.get("fear", 0)),
				(" · grievance %d" % gr) if gr > 0 else ""]
		v.add_child(r)


func _strength_word(v: int) -> String:
	if v >= 80:
		return "Overwhelming."
	if v >= 60:
		return "Strong."
	if v >= 40:
		return "Contested."
	return "Thin on the ground."


# ------------------------------------------------------------------ full-screen cards

func _card_screen(m: MarginContainer) -> void:
	var c: Dictionary = _camp.call("card")
	var center := CenterContainer.new()
	m.add_child(center)
	var p := UiTheme.panel()
	p.custom_minimum_size = Vector2(900, 0)
	center.add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	p.add_child(v)
	var how: String = {"dead": "has died", "taken": "is in the Wawel cells for good", "coup": "has been pushed aside"}.get(str(c.get("how", "")), "has fallen")
	v.add_child(UiTheme.kicker("Succession"))
	v.add_child(UiTheme.label("%s %s." % [c.get("fallen", "The figurehead"), how], 20, UiTheme.TEXT_DIM, "italic"))
	v.add_child(UiTheme.label(str(c.get("name", "")), 48, UiTheme.BRASS_BRIGHT, "display_light"))
	v.add_child(UiTheme.body(str(c.get("role", "")), 18, UiTheme.TEXT))
	var backed := "Your nominee takes up the banner." if str(c.get("kind", "")) == "nominated" else "Forced on the movement by the %s." % c.get("backer", "strongest faction")
	v.add_child(UiTheme.body(backed, 18, UiTheme.BRASS))
	v.add_child(HSeparator.new())
	for l in c.get("changes", []):
		v.add_child(UiTheme.body("—  " + str(l), 17, UiTheme.TEXT))
	v.add_child(UiTheme.body("The journal, the people found, the rumours and the levers pass to the new figurehead.", 15, UiTheme.TEXT_DIM))
	var b := UiTheme.primary_button("Carry the banner", func() -> void: _camp.call("dismiss_card"), 280)
	v.add_child(b)
	b.grab_focus.call_deferred()


func _ending_screen(m: MarginContainer) -> void:
	var e: Dictionary = _camp.call("ending")
	var center := CenterContainer.new()
	m.add_child(center)
	var p := UiTheme.panel()
	p.custom_minimum_size = Vector2(960, 0)
	center.add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 14)
	p.add_child(v)
	v.add_child(UiTheme.kicker("The end of the winter  ·  %d nights" % (_camp.call("st")["results"] as Array).size()))
	v.add_child(UiTheme.label(str(e.get("title", "")), 46, UiTheme.BRASS_BRIGHT, "display_light"))
	v.add_child(UiTheme.body(str(e.get("text", "")), 19, UiTheme.TEXT))
	var fallen: Array = _camp.call("st")["fallen"]
	for f in fallen:
		v.add_child(UiTheme.body("In memory: %s, %s." % [f.get("name", "?"), f.get("cause", "")], 15, UiTheme.TEXT_DIM))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 12)
	v.add_child(row)
	var b := UiTheme.primary_button("Begin again", func() -> void: _leave(GameState.new_game), 240)
	row.add_child(b)
	row.add_child(UiTheme.button("Menu", func() -> void: _leave(to_menu.emit), 140))
	b.grab_focus.call_deferred()


func _choice_screen(m: MarginContainer, title: String, text: String, options: Array) -> void:
	var center := CenterContainer.new()
	m.add_child(center)
	var p := UiTheme.panel()
	p.custom_minimum_size = Vector2(900, 0)
	center.add_child(p)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 12)
	p.add_child(v)
	v.add_child(UiTheme.heading(title, 34))
	v.add_child(UiTheme.body(text, 18, UiTheme.TEXT))
	v.add_child(HSeparator.new())
	for o in options:
		var b := UiTheme.button(str(o[0]), o[2], 0)
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.custom_minimum_size.y = 44
		v.add_child(b)
		v.add_child(UiTheme.body(str(o[1]), 14, UiTheme.TEXT_DIM))


## Kept for callers that pass a line to show under the briefing.
func set_summary(s: String) -> void:
	_summary = s
	if _summary_label:
		_summary_label.text = s
		_summary_label.visible = s != ""


func _leave(then: Callable) -> void:
	if _go:
		_go.disabled = true
	var tw := create_tween()
	tw.tween_property(self, "modulate:a", 0.0, 0.3)
	tw.tween_callback(then)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		_leave(to_menu.emit)
