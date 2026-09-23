class_name Journal
extends CanvasLayer
## The night journal: a full-screen book (J or Tab, or Journal in the pause menu; Esc, J or Tab closes it).
## Opening pauses the game and shows the mouse; closing restores both. Added by scripts/ui/hud.gd each night;
## the entries themselves live in Mission.journal (scripts/core/mission.gd), so they survive nights.
##
## Tabs (1-5, or the arrow keys, or click):
##   Missions    the current mission: title, briefing, approach, objectives (done / optional), rewards hint;
##               finished missions below.
##   Storylines  every mission approach (missions.json `approaches` + `journal.storylines`), mission storyline
##               and city storyline (data/storylines.json) the player has discovered, with a blurb, status and
##               the people involved; undiscovered ones show as "???" rows.
##   People      NPCs spoken with or overheard: name, role, faction, where and when last seen.
##   Log         timestamped Mission.message / announcement text and overheard storyline lines.
##   Controls    the key list.
##
## Discovery: a dialogue node with `"discover": [ids]` (missions.json) marks those storylines; a mission
## approach is discovered (and "in progress") when chosen; a storyline.gd sequence is discovered when it begins
## within sight of the player (flag and proximity triggers always), or when one of its lines is overheard.
## The journal polls the mission's dialogue box for the node on screen and listens to storyline.gd's
## storyline_started / storyline_step / storyline_ended signals.
##
## Screenshots: `-- --smoke --shot-journal[=dir]` (windowed; dir defaults to --shot= or --shot-ui=) saves
## journal_<tab>.png on the third night of the smoke run (after the first mission pass) and
## journal_first_<tab>.png ten seconds into the first night.

const TABS := ["Missions", "Storylines", "People", "Log", "Controls"]
const EARSHOT := 14.0          ## m: an NPC's storyline line is overheard within this distance
const SIGHT := 22.0            ## m: a storyline that begins this close to the player is seen
const STATUS_COL := {"available": UiTheme.BRASS, "in progress": UiTheme.BRASS_BRIGHT, "resolved": UiTheme.GOOD,
		"set aside": UiTheme.TEXT_DIM}
const CONTROLS := [["W A S D", "Walk"], ["Mouse", "Look about"], ["Shift", "Run (the watch hears it)"],
		["Ctrl  /  C", "Crouch and creep"], ["E", "Talk, take, use"], ["F  /  Left mouse", "Strike; from behind, a silent takedown"],
		["1 - 4", "Choose a reply"], ["J  /  Tab", "Journal"], ["Esc  /  P", "Pause"]]
const TIPS := ["Lanterns show you to the watch; the curfew bell makes them look twice as far.",
		"Walk when carrying the bundle or wearing a borrowed cloak. A hurry is noticed before a face.",
		"Come at a man from behind and he never sees you.",
		"Every alarm raised tightens the Austrian crackdown tomorrow."]
## Where an NPC was last seen: the nearest of these (x, z on the Rynek).
const PLACES := [["the Cloth Hall passage", Vector2(0, 3)], ["the Cloth Hall arcades", Vector2(0, -8)],
		["St Mary's", Vector2(31, -17)], ["the Town Hall door", Vector2(-16, 17.5)], ["St Adalbert's steps", Vector2(22, 23)],
		["the west well", Vector2(-12.5, 6.3)], ["the east well", Vector2(15, -6.6)], ["the north-west alley", Vector2(-24, -24)],
		["the docks-side alley", Vector2(24, 14)], ["the north row", Vector2(2, -26)], ["the south row", Vector2(-2, 26)],
		["the market stalls", Vector2(-10, -12)], ["the east stalls", Vector2(11, 11)], ["the west side", Vector2(-26, -4)],
		["the safe-house cellar", Vector2(27, 8)]]

signal noted(text: String)

static var _nights := 0
static var _npcs_db: Dictionary = {}     ## npc id -> roster entry (data/npcs.json)
static var _story_db: Dictionary = {}    ## data/storylines.json

var _root: Control
var _kicker: Label
var _heading: Label
var _tab_buttons: Array[Button] = []
var _left: VBoxContainer
var _right: VBoxContainer
var _left_scroll: ScrollContainer
var _right_scroll: ScrollContainer
var _tab := 0
var _was_paused := false
var _mouse_before := Input.MOUSE_MODE_CAPTURED
var _on_close := Callable()
var _last_node := ""
var _hooked: Array = []


func _ready() -> void:
	layer = 30
	process_mode = Node.PROCESS_MODE_ALWAYS
	add_to_group("journal")
	_nights += 1
	_load_dbs()
	_build()
	visible = false
	Mission.approach_changed.connect(_on_approach)
	noted.connect(_forward_note)
	_hook_storylines()
	var t := Timer.new()
	t.wait_time = 1.0
	t.autostart = true
	t.timeout.connect(_hook_storylines)
	add_child(t)
	_setup_shots()


# ------------------------------------------------------------------ data

static func _load_dbs() -> void:
	if _npcs_db.is_empty():
		var f := FileAccess.open("res://data/npcs.json", FileAccess.READ)
		var d: Variant = JSON.parse_string(f.get_as_text()) if f else null
		if d is Dictionary:
			for e in d.get("npcs", []):
				_npcs_db[str(e.get("id", ""))] = e
	if _story_db.is_empty():
		var f := FileAccess.open("res://data/storylines.json", FileAccess.READ)
		var d: Variant = JSON.parse_string(f.get_as_text()) if f else null
		if d is Dictionary:
			_story_db = d


static func _mission_data() -> Dictionary:
	var id := Mission.mission_id if Mission.mission_id != "" else Mission.default_id()
	return Mission.mission_data(id)


## Every storyline the journal knows of, in book order: the mission's approaches, its own storylines, then the
## city's. [{id, title, blurb, npcs: [ids], kind: "approach"|"mission"|"city"}]
static func catalogue() -> Array:
	_load_dbs()
	var md := _mission_data()
	var jd: Dictionary = md.get("journal", {}).get("storylines", {})
	var out: Array = []
	var approaches: Dictionary = md.get("approaches", {})
	for a in approaches:
		var j: Dictionary = jd.get(a, {})
		out.append({"id": a, "title": str(j.get("title", str(a).capitalize())),
				"blurb": str(j.get("blurb", approaches[a].get("label", ""))), "npcs": j.get("npcs", []), "kind": "approach"})
	for sd in md.get("storylines", []):
		out.append(_story_entry(sd, jd.get(str(sd.get("id", "")), {}), "mission"))
	for sd in _story_db.get("storylines", []):
		out.append(_story_entry(sd, sd.get("journal", {}), "city"))
	return out


static func _story_entry(sd: Dictionary, j: Dictionary, kind: String) -> Dictionary:
	var npcs: Array = []
	for st in sd.get("steps", []):
		var a := str(st.get("actor", ""))
		if a != "" and a != "player" and not npcs.has(a):
			npcs.append(a)
	var blurb := str(j.get("blurb", ""))
	if blurb == "":
		blurb = str(sd.get("note", "")).get_slice(". ", 0)
	return {"id": str(sd.get("id", "")), "title": str(j.get("title", sd.get("title", sd.get("id", "")))), "blurb": blurb,
			"npcs": npcs, "kind": kind}


static func _people_data(id: String) -> Dictionary:
	var md := _mission_data()
	var p: Dictionary = md.get("journal", {}).get("people", {}).get(id, {})
	if p.is_empty():
		p = _story_db.get("journal", {}).get("people", {}).get(id, {})
	return p


static func person_name(id: String) -> String:
	if id.begins_with("guard:"):
		return id.trim_prefix("guard:").capitalize()
	var p := _people_data(id)
	if p.has("name"):
		return str(p["name"])
	var talk: Dictionary = _mission_data().get("talk", {}).get(id, {})
	if talk.has("name"):
		return str(talk["name"])
	return id.replace("_", " ").capitalize()


static func person_role(id: String) -> String:
	for e in _mission_data().get("npcs", []):
		if str(e.get("id", "")) == id and e.has("role"):
			return str(e["role"])
	return str(_npcs_db.get(id, {}).get("role", ""))


static func person_faction(id: String) -> String:
	var f := str(_people_data(id).get("faction", ""))
	if f == "":
		return ""
	return str(GameState.factions.get(f, {}).get("name", f.capitalize()))


static func place_of(pos: Vector3) -> String:
	if pos.y < -50.0:
		return "indoors, in the salon"
	var best := ""
	var best_d := INF
	for pl in PLACES:
		var d: float = (pl[1] as Vector2).distance_to(Vector2(pos.x, pos.z))
		if d < best_d:
			best_d = d
			best = pl[0]
	return best


func _title_of(id: String) -> String:
	for e in catalogue():
		if e["id"] == id:
			return e["title"]
	return id.capitalize()


## Record meeting (or overhearing) NPC `id` standing at `where`.
func meet(id: String, node: Node3D) -> void:
	if id == "" or id == "player" or id.begins_with("guard:"):
		return
	var people: Dictionary = Mission.journal["people"]
	var first := not people.has(id)
	people[id] = {"name": person_name(id), "role": person_role(id), "faction": person_faction(id),
			"where": place_of(node.global_position) if node else str(people.get(id, {}).get("where", "")),
			"t": GameState.time_string(), "night": GameState.day}
	if first and visible:
		_refresh()


func discover(id: String, how: String) -> void:
	if Mission.journal_discover(id):
		var t := _title_of(id)
		Mission.journal_log("New storyline: %s (%s)." % [t, how], "story")
		noted.emit("New storyline: " + t)
		if visible:
			_refresh()


func _forward_note(text: String) -> void:
	var panel: Node = null
	if get_parent():
		for c in get_parent().get_children():
			if c.has_method("note"):
				panel = c
	if panel:
		panel.call("note", text)


# ------------------------------------------------------------------ discovery hooks

func _process(_d: float) -> void:
	var r: Node = Mission.runner
	if r == null or not is_instance_valid(r):
		return
	var dlg: Node = r.get("dialogue")
	if dlg and is_instance_valid(dlg) and dlg.get("is_open"):
		var node := str(dlg.get_meta("node", ""))
		var who := str(r.get("_speaking"))
		var key := who + "/" + node
		if key != _last_node:
			_last_node = key
			_on_dialogue_node(who, node)
	else:
		_last_node = ""


func _on_dialogue_node(who: String, node_name: String) -> void:
	var r: Node = Mission.runner
	meet(who, r.call("actor", who) if r else null)
	var nd: Dictionary = Mission.data.get("dialogue", {}).get(node_name, {})
	for id in nd.get("discover", []):
		discover(str(id), "told by " + person_name(who))


func _on_approach(a: String) -> void:
	discover(a, "chosen")
	Mission.journal_set_status(a, "in progress")
	for other in Mission.data.get("approaches", {}):
		var e: Dictionary = Mission.journal["storylines"].get(other, {})
		if other != a and not e.is_empty() and e.get("status", "") != "resolved":
			Mission.journal_set_status(other, "set aside")


func _population() -> Node:
	var r: Node = Mission.runner
	if r and is_instance_valid(r):
		return r.get("population")
	return null


func _hook_storylines() -> void:
	var pop := _population()
	if pop == null:
		return
	for s in pop.get("storylines"):
		if not is_instance_valid(s) or _hooked.has(s) or not s.has_signal("storyline_started"):
			continue
		_hooked.append(s)
		s.storyline_started.connect(_on_story_started.bind(s))
		s.storyline_step.connect(_on_story_step.bind(s))
		s.storyline_ended.connect(_on_story_ended)


func _player() -> Node3D:
	return get_tree().get_first_node_in_group("player") as Node3D


func _on_story_started(id: String, s: Node) -> void:
	Mission.journal_set_status(id, "in progress")
	var trig: Dictionary = s.get("data").get("trigger", {})
	var seen := trig.has("flag") or trig.has("radius")
	var p := _player()
	var pop := _population()
	if not seen and p and pop:
		for aid in s.actor_ids():
			var a: Node3D = pop.actor(aid) if not aid.begins_with("guard:") else null
			if a and a.global_position.distance_to(p.global_position) < SIGHT:
				seen = true
				break
	if seen:
		discover(id, "seen")


func _on_story_step(id: String, text: String, s: Node) -> void:
	var a: Node3D = s.current_actor()
	var p := _player()
	if a == null or p == null or a.global_position.distance_to(p.global_position) > EARSHOT:
		return
	discover(id, "overheard")
	var pop := _population()
	var aid := ""
	if pop:
		for x in s.actor_ids():
			if pop.actor(x) == a:
				aid = x
	meet(aid, a)
	Mission.journal_log("%s: “%s”" % [person_name(aid) if aid != "" else "A voice", text], "story")


func _on_story_ended(id: String) -> void:
	Mission.journal_set_status(id, "resolved")


# ------------------------------------------------------------------ open / close

func is_open() -> bool:
	return visible


## Opens the book. `on_close` runs after it closes (the pause menu reopens itself); `pause` false only for shots.
func open(on_close: Callable = Callable(), pause: bool = true) -> void:
	if visible or Mission.dialogue_open():
		return
	_on_close = on_close
	_was_paused = get_tree().paused
	_mouse_before = Input.mouse_mode
	visible = true
	if pause:
		get_tree().paused = true
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	_refresh()


func close() -> void:
	if not visible:
		return
	visible = false
	get_tree().paused = _was_paused
	if DisplayServer.get_name() != "headless":
		Input.mouse_mode = _mouse_before
	var cb := _on_close
	_on_close = Callable()
	if cb.is_valid():
		cb.call()


func _pause_menu_open() -> bool:
	for n in get_tree().get_nodes_in_group("pause_menu"):
		if n.visible:
			return true
	return false


func _input(event: InputEvent) -> void:
	if GameState.phase != GameState.Phase.NIGHT:
		return
	if event.is_action_pressed("journal") and not event.is_echo():
		if visible:
			get_viewport().set_input_as_handled()
			close()
		elif not _pause_menu_open() and not Mission.dialogue_open() and Mission.is_active():
			get_viewport().set_input_as_handled()
			open()
		return
	if not visible:
		return
	if event.is_action_pressed("pause") or event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		close()
	elif event is InputEventKey and event.pressed and not event.echo:
		var k: int = (event as InputEventKey).physical_keycode
		if k >= KEY_1 and k <= KEY_5:
			_set_tab(k - KEY_1)
		elif k == KEY_RIGHT or k == KEY_D:
			_set_tab((_tab + 1) % TABS.size())
		elif k == KEY_LEFT or k == KEY_A:
			_set_tab((_tab + TABS.size() - 1) % TABS.size())
		else:
			return
		get_viewport().set_input_as_handled()


# ------------------------------------------------------------------ the book

func _build() -> void:
	_root = Control.new()
	_root.theme = UiTheme.get_theme()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_root)
	var shade := ColorRect.new()
	shade.color = Color(0.01, 0.015, 0.025, 0.82)
	_root.add_child(UiTheme.full_rect(shade))

	var book := PanelContainer.new()
	var cover := StyleBoxFlat.new()
	cover.bg_color = Color(0.2, 0.13, 0.08, 1.0)          # leather binding
	cover.border_color = UiTheme.BRASS_DARK
	cover.set_border_width_all(2)
	cover.set_corner_radius_all(8)
	cover.set_content_margin_all(12)
	cover.shadow_color = Color(0, 0, 0, 0.6)
	cover.shadow_size = 28
	book.add_theme_stylebox_override("panel", cover)
	book.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	book.offset_left = 70
	book.offset_right = -70
	book.offset_top = 40
	book.offset_bottom = -40
	_root.add_child(book)

	var pages := PanelContainer.new()
	var pg := StyleBoxFlat.new()
	pg.bg_color = Color(0.075, 0.09, 0.12, 0.99)
	pg.border_color = Color(UiTheme.BRASS, 0.5)
	pg.set_border_width_all(1)
	pg.set_corner_radius_all(3)
	pg.content_margin_left = 44
	pg.content_margin_right = 44
	pg.content_margin_top = 24
	pg.content_margin_bottom = 18
	pages.add_theme_stylebox_override("panel", pg)
	book.add_child(pages)

	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 10)
	pages.add_child(v)

	# Header: kicker + tab heading on the left, the tabs as ribbon bookmarks on the right.
	var head := HBoxContainer.new()
	v.add_child(head)
	var hv := VBoxContainer.new()
	hv.add_theme_constant_override("separation", -4)
	hv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(hv)
	_kicker = UiTheme.kicker("Journal")
	hv.add_child(_kicker)
	_heading = UiTheme.heading("Missions", 40)
	hv.add_child(_heading)
	var tabs := HBoxContainer.new()
	tabs.add_theme_constant_override("separation", 4)
	tabs.size_flags_vertical = Control.SIZE_SHRINK_END
	head.add_child(tabs)
	for i in TABS.size():
		var b := Button.new()
		b.text = "%d  %s" % [i + 1, TABS[i]]
		b.focus_mode = Control.FOCUS_NONE
		b.toggle_mode = true
		b.add_theme_font_override("font", UiTheme.font("display"))
		b.add_theme_font_size_override("font_size", 19)
		b.add_theme_color_override("font_color", UiTheme.TEXT_DIM)
		b.add_theme_color_override("font_hover_color", UiTheme.BRASS_BRIGHT)
		b.add_theme_color_override("font_pressed_color", UiTheme.BRASS_BRIGHT)
		b.add_theme_color_override("font_hover_pressed_color", UiTheme.BRASS_BRIGHT)
		var off := StyleBoxFlat.new()
		off.bg_color = Color(0, 0, 0, 0)
		off.border_color = Color(UiTheme.BRASS, 0.18)
		off.border_width_bottom = 2
		off.content_margin_left = 12
		off.content_margin_right = 12
		off.content_margin_top = 4
		off.content_margin_bottom = 6
		var on := off.duplicate() as StyleBoxFlat
		on.bg_color = Color(UiTheme.BRASS, 0.12)
		on.border_color = UiTheme.BRASS_BRIGHT
		on.set_corner_radius_all(2)
		var hov := off.duplicate() as StyleBoxFlat
		hov.border_color = Color(UiTheme.BRASS, 0.6)
		b.add_theme_stylebox_override("normal", off)
		b.add_theme_stylebox_override("hover", hov)
		b.add_theme_stylebox_override("pressed", on)
		b.add_theme_stylebox_override("hover_pressed", on)
		b.pressed.connect(_set_tab.bind(i))
		tabs.add_child(b)
		_tab_buttons.append(b)

	var rule := ColorRect.new()
	rule.color = Color(UiTheme.BRASS, 0.4)
	rule.custom_minimum_size.y = 1
	v.add_child(rule)

	# The spread: left page | spine | right page.
	var spread := HBoxContainer.new()
	spread.size_flags_vertical = Control.SIZE_EXPAND_FILL
	spread.add_theme_constant_override("separation", 0)
	v.add_child(spread)
	_left_scroll = _page()
	spread.add_child(_left_scroll)
	_left = _left_scroll.get_child(0).get_child(0)
	var spine := Spine.new()
	spine.custom_minimum_size.x = 64
	spread.add_child(spine)
	_right_scroll = _page()
	spread.add_child(_right_scroll)
	_right = _right_scroll.get_child(0).get_child(0)

	var foot := UiTheme.label("J  /  Tab  close        1 - 5  or  ← →  turn the page        Esc  back to the night", 14,
			Color(UiTheme.TEXT_DIM, 0.8), "italic")
	foot.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	v.add_child(foot)


func _page() -> ScrollContainer:
	var sc := ScrollContainer.new()
	sc.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sc.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sc.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	var m := MarginContainer.new()
	m.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	m.add_theme_constant_override("margin_top", 10)
	m.add_theme_constant_override("margin_right", 10)
	sc.add_child(m)
	var v := VBoxContainer.new()
	v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	v.add_theme_constant_override("separation", 10)
	m.add_child(v)
	return sc


func _set_tab(i: int) -> void:
	_tab = clampi(i, 0, TABS.size() - 1)
	_refresh()


func _refresh() -> void:
	for i in _tab_buttons.size():
		_tab_buttons[i].set_pressed_no_signal(i == _tab)
	_kicker.text = ("Journal  ·  Night %d  ·  %s" % [GameState.day, GameState.time_string()]).to_upper()
	_heading.text = TABS[_tab]
	for c in _left.get_children() + _right.get_children():
		c.get_parent().remove_child(c)
		c.queue_free()
	_left_scroll.scroll_vertical = 0
	_right_scroll.scroll_vertical = 0
	match _tab:
		0: _fill_missions()
		1: _fill_storylines()
		2: _fill_people()
		3: _fill_log()
		4: _fill_controls()


# --- text helpers

func _t(text: String, size: int = 18, col: Color = UiTheme.TEXT, face: String = "regular") -> Label:
	var l := UiTheme.label(text, size, col, face)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return l


func _section(parent: Control, text: String) -> void:
	parent.add_child(UiTheme.spacer(4))
	parent.add_child(UiTheme.kicker(text))


func _hair(parent: Control) -> void:
	var r := ColorRect.new()
	r.color = Color(UiTheme.BRASS, 0.16)
	r.custom_minimum_size.y = 1
	parent.add_child(r)


func _fleuron(parent: Control) -> void:
	var l := _t("❧", 20, Color(UiTheme.BRASS, 0.55))
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	parent.add_child(l)


# --- Missions

func _fill_missions() -> void:
	var md: Dictionary = Mission.data if not Mission.data.is_empty() else _mission_data()
	var L := _left
	L.add_child(UiTheme.label(Mission.title if Mission.title != "" else str(md.get("title", "Tonight")), 34,
			UiTheme.BRASS_BRIGHT, "display"))
	var appr := "No road chosen yet"
	if Mission.approach != "":
		appr = str(md.get("approaches", {}).get(Mission.approach, {}).get("label", Mission.approach))
	L.add_child(_t(appr, 18, UiTheme.BRASS, "italic"))
	_hair(L)
	for para in Mission.briefing.split("\n\n"):
		if para.strip_edges() != "":
			L.add_child(_t(para.strip_edges(), 17, Color(UiTheme.TEXT, 0.92)))

	var R := _right
	R.add_child(UiTheme.kicker("Objectives"))
	for o in Mission.objectives:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 10)
		var opt := bool(o.get("optional", false))
		var mark := UiTheme.label("✓" if o["done"] else ("◇" if opt else "○"), 19,
				UiTheme.GOOD if o["done"] else UiTheme.BRASS, "bold")
		mark.custom_minimum_size.x = 20
		mark.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
		row.add_child(mark)
		var tx := _t(str(o["text"]) + ("  (optional)" if opt else ""), 18,
				UiTheme.TEXT_DIM if o["done"] else UiTheme.TEXT, "italic" if opt else "regular")
		row.add_child(tx)
		R.add_child(row)
	var hint := str(md.get("journal", {}).get("reward_hint", ""))
	var infl: Dictionary = md.get("rewards", {}).get("influence", {})
	if hint != "" or not infl.is_empty():
		_section(R, "Rewards")
		if hint != "":
			R.add_child(_t(hint, 17, UiTheme.TEXT_DIM, "italic"))
		var parts: PackedStringArray = []
		for fid in infl:
			parts.append("%s +%d" % [GameState.factions.get(fid, {}).get("name", fid), int(infl[fid])])
		if not parts.is_empty():
			R.add_child(_t("   ·   ".join(parts), 16, UiTheme.BRASS))
	_section(R, "Completed")
	var done: Array = Mission.journal["missions"]
	if done.is_empty():
		R.add_child(_t("Nothing yet. This is the first night.", 17, UiTheme.TEXT_DIM, "italic"))
	for i in range(done.size() - 1, -1, -1):
		var m: Dictionary = done[i]
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 12)
		var n := UiTheme.label("Night %d" % int(m.get("night", 0)), 16, UiTheme.BRASS, "bold")
		n.custom_minimum_size.x = 76
		row.add_child(n)
		var road := _title_of(str(m.get("approach", ""))) if str(m.get("approach", "")) != "" else ""
		row.add_child(_t("%s%s" % [m.get("title", "?"), ("  —  " + road) if road != "" else ""], 17))
		row.add_child(UiTheme.label("delivered" if m.get("success", false) else "failed", 15,
				UiTheme.GOOD if m.get("success", false) else UiTheme.BAD, "italic"))
		R.add_child(row)


# --- Storylines

func _fill_storylines() -> void:
	var all := catalogue()
	var known: Dictionary = Mission.journal["storylines"]
	var found := 0
	for e in all:
		if bool(known.get(e["id"], {}).get("discovered", false)):
			found += 1
	var half := int(ceil(all.size() / 2.0))
	for i in all.size():
		var e: Dictionary = all[i]
		var parent := _left if i < half else _right
		if i == 0:
			parent.add_child(_t("%d of %d threads found. The city keeps its own secrets; listen at corners." % [found, all.size()],
					16, UiTheme.TEXT_DIM, "italic"))
		elif i == half:
			parent.add_child(_t(" ", 16))
		var k: Dictionary = known.get(e["id"], {})
		if bool(k.get("discovered", false)):
			_story_row(parent, e, str(k.get("status", "available")))
		else:
			_unknown_row(parent, e)
		_hair(parent)


func _story_row(parent: Control, e: Dictionary, status: String) -> void:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	var top := HBoxContainer.new()
	var tl := UiTheme.label(e["title"], 24, UiTheme.BRASS_BRIGHT, "display")
	tl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(tl)
	top.add_child(UiTheme.label(status, 15, STATUS_COL.get(status, UiTheme.BRASS), "italic"))
	box.add_child(top)
	var kind: String = {"approach": "A road to the bundle", "mission": "Tonight's errand", "city": "The city by night"}.get(e["kind"], "")
	box.add_child(UiTheme.label(str(kind).to_upper(), 12, Color(UiTheme.BRASS, 0.8), "bold"))
	if str(e["blurb"]) != "":
		box.add_child(_t(e["blurb"], 17, UiTheme.TEXT))
	var who: PackedStringArray = []
	for id in e["npcs"]:
		who.append(person_name(str(id)))
	if not who.is_empty():
		box.add_child(_t("Involves: " + ", ".join(who), 15, UiTheme.TEXT_DIM, "italic"))
	parent.add_child(box)


func _unknown_row(parent: Control, e: Dictionary) -> void:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 2)
	box.add_child(UiTheme.label("? ? ?", 24, Color(UiTheme.TEXT_DIM, 0.6), "display"))
	var hint: String = {"approach": "Someone could show you another road.", "mission": "Something may yet happen tonight.",
			"city": "Something is afoot in the city."}.get(e["kind"], "")
	box.add_child(_t(str(hint), 16, Color(UiTheme.TEXT_DIM, 0.7), "italic"))
	parent.add_child(box)


# --- People

func _fill_people() -> void:
	var people: Dictionary = Mission.journal["people"]
	if people.is_empty():
		_left.add_child(_t("You have spoken to no one yet. Faces and names you learn in the night are kept here.",
				17, UiTheme.TEXT_DIM, "italic"))
		_right.add_child(_t(" ", 16))
		return
	var ids := people.keys()
	var half := int(ceil(ids.size() / 2.0))
	for i in ids.size():
		var p: Dictionary = people[ids[i]]
		var parent := _left if i < half else _right
		var box := VBoxContainer.new()
		box.add_theme_constant_override("separation", 1)
		var top := HBoxContainer.new()
		var n := UiTheme.label(str(p.get("name", ids[i])), 22, UiTheme.BRASS_BRIGHT, "display")
		n.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		top.add_child(n)
		if str(p.get("faction", "")) != "":
			top.add_child(UiTheme.label(str(p["faction"]), 14, UiTheme.BRASS, "bold"))
		box.add_child(top)
		if str(p.get("role", "")) != "":
			box.add_child(_t(str(p["role"]), 16, UiTheme.TEXT))
		box.add_child(_t("Last seen at %s, %s, night %d." % [p.get("where", "?"), p.get("t", "?"), int(p.get("night", 1))],
				14, UiTheme.TEXT_DIM, "italic"))
		parent.add_child(box)
		_hair(parent)


# --- Log

func _fill_log() -> void:
	var lines: Array = Mission.journal["log"]
	if lines.is_empty():
		_left.add_child(_t("The page is blank. What you hear and learn tonight is written here.", 17, UiTheme.TEXT_DIM, "italic"))
		return
	var entries: Array = lines.slice(maxi(lines.size() - 40, 0))
	entries.reverse()
	var half := int(ceil(entries.size() / 2.0))
	var last_night := -1
	for i in entries.size():
		var e: Dictionary = entries[i]
		var parent := _left if i < half else _right
		if int(e.get("night", 0)) != last_night or i == half:
			last_night = int(e.get("night", 0))
			parent.add_child(UiTheme.kicker("Night %d" % last_night))
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 14)
		var t := UiTheme.label(str(e.get("t", "")), 15, UiTheme.BRASS, "bold")
		t.custom_minimum_size.x = 48
		t.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
		row.add_child(t)
		var kind := str(e.get("kind", ""))
		var col := UiTheme.BRASS_BRIGHT if kind == "announcement" else UiTheme.TEXT
		row.add_child(_t(str(e.get("text", "")).replace("\n", " "), 16, col, "italic" if kind == "story" else "regular"))
		parent.add_child(row)


# --- Controls

func _fill_controls() -> void:
	for c in CONTROLS:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 18)
		var k := UiTheme.label(c[0], 18, UiTheme.BRASS_BRIGHT, "bold")
		k.custom_minimum_size.x = 190
		k.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		row.add_child(k)
		row.add_child(_t(c[1], 18))
		_left.add_child(row)
		_hair(_left)
	_right.add_child(UiTheme.kicker("Notes on the watch"))
	for tip in TIPS:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 10)
		var m := UiTheme.label("❧", 16, UiTheme.BRASS)
		m.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
		row.add_child(m)
		row.add_child(_t(tip, 17, UiTheme.TEXT, "italic"))
		_right.add_child(row)
	_right.add_child(UiTheme.spacer(10))
	_fleuron(_right)


# ------------------------------------------------------------------ screenshots (--shot-journal)

static func _shot_dir() -> String:
	var args := OS.get_cmdline_user_args()
	var want := false
	var dir := ""
	var fallback := ""
	for a in args:
		if a == "--shot-journal":
			want = true
		elif a.begins_with("--shot-journal="):
			want = true
			dir = a.trim_prefix("--shot-journal=")
		elif a.begins_with("--shot=") and fallback == "":
			fallback = a.trim_prefix("--shot=")
		elif a.begins_with("--shot-ui=") and fallback == "":
			fallback = a.trim_prefix("--shot-ui=")
	if not want or DisplayServer.get_name() == "headless":
		return ""
	return dir if dir != "" else fallback


func _setup_shots() -> void:
	if _shot_dir() == "":
		return
	var prefix := ""
	var wait := 0.0
	if _nights == 1:
		prefix = "journal_first"
		wait = 10.0
	elif _nights == 3:
		prefix = "journal"
		wait = 2.0
	if prefix == "":
		return
	var t := Timer.new()
	t.one_shot = true
	t.wait_time = wait
	t.process_mode = Node.PROCESS_MODE_ALWAYS
	t.ignore_time_scale = true
	t.timeout.connect(_capture.bind(prefix))
	add_child(t)
	t.start()


func _capture(prefix: String) -> void:
	var dir := _shot_dir()
	if Mission.dialogue_open() or visible:
		return
	open(Callable(), false)
	for i in TABS.size():
		_set_tab(i)
		for f in 3:
			await get_tree().process_frame
		await RenderingServer.frame_post_draw
		if not is_inside_tree():
			return
		var path := dir.path_join("%s_%s.png" % [prefix, TABS[i].to_lower()])
		get_viewport().get_texture().get_image().save_png(path)
		print("[smoke] journal shot ", path)
	close()


## The gutter between the pages: a shaded fold with a brass stitch line.
class Spine extends Control:
	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		var cx := size.x * 0.5
		for i in 12:
			var w := 12.0 - i
			draw_rect(Rect2(cx - w * 2.0, 0, w * 4.0, size.y), Color(0, 0, 0, 0.035))
		draw_line(Vector2(cx, 6), Vector2(cx, size.y - 6), Color(UiTheme.BRASS, 0.35), 1.0)
		var y := 14.0
		while y < size.y - 10:
			draw_line(Vector2(cx - 3, y), Vector2(cx + 3, y + 4), Color(UiTheme.BRASS, 0.25), 1.0)
			y += 18.0
