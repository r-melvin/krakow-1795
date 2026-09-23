extends Control
## Mission block of the night HUD (added by scripts/ui/hud.gd), deliberately small:
##  - top right: the current objective on one line and the purse (coin + number, hearts only when hurt, a word
##    when carrying or cloaked). Shown for 6 s at the start of the night and for 4 s whenever the objectives,
##    purse or carried state change, then it fades out; the full list is in the journal (J).
##  - bottom centre: the interact prompt as a key cap and a verb ("E  Talk"), and above it one Mission.message
##    line at a time (first clause only, 3 s). The whole text goes to the journal log (Mission.journal_log).
##  - the Mission.announcement banner (curfew bell): its first line only, 2.5 s.
##  - bottom right: a quiet "Journal" note when the journal learns something (Journal.noted).

const SHOW_FIRST := 6.0
const SHOW_CHANGE := 4.0
const MESSAGE_SECONDS := 3.0
const BANNER_SECONDS := 2.5
const FADE := 0.6

## Prompt verbs: the first word of an interactable's prompt -> what the key cap says.
const VERBS := {"talk": "Talk", "take": "Take", "search": "Search", "slip": "Plant", "give": "Give",
		"enter": "Enter", "open": "Open", "use": "Use", "read": "Read", "knock": "Knock", "leave": "Leave"}

var _top: VBoxContainer
var _obj_row: HBoxContainer
var _obj: Label
var _status_row: HBoxContainer
var _coins: Label
var _tags: Label
var _pips: Label
var _prompt_row: HBoxContainer
var _prompt_verb: Label
var _msg: Label
var _msg_tween: Tween
var _banner: Label
var _banner_tween: Tween
var _note: Label
var _note_tween: Tween

var _show_left := SHOW_FIRST
var _status_key := ""
var _objective_key := ""
var _hurt := false
var _alpha := 0.0


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_build()
	Mission.objectives_changed.connect(_rebuild)
	Mission.message.connect(_on_message)
	Mission.announcement.connect(_on_announcement)
	_rebuild()
	_show_left = SHOW_FIRST


func _build() -> void:
	# --- top right: objective + purse
	_top = VBoxContainer.new()
	_top.anchor_left = 1.0
	_top.anchor_right = 1.0
	_top.offset_left = -560
	_top.offset_right = -22
	_top.offset_top = 16
	_top.alignment = BoxContainer.ALIGNMENT_BEGIN
	_top.add_theme_constant_override("separation", 2)
	_top.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_top)
	_obj_row = HBoxContainer.new()
	_obj_row.alignment = BoxContainer.ALIGNMENT_END
	_obj_row.add_theme_constant_override("separation", 8)
	_top.add_child(_obj_row)
	var mark := _lbl(15, UiTheme.BRASS, "bold")
	mark.text = "◇"
	_obj_row.add_child(mark)
	_obj = _lbl(18, UiTheme.TEXT, "italic")
	_obj.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_obj_row.add_child(_obj)

	_status_row = HBoxContainer.new()
	_status_row.alignment = BoxContainer.ALIGNMENT_END
	_status_row.add_theme_constant_override("separation", 6)
	_top.add_child(_status_row)
	_pips = _lbl(14, UiTheme.BAD, "bold")
	_status_row.add_child(_pips)
	_tags = _lbl(14, UiTheme.TEXT_DIM, "italic")
	_status_row.add_child(_tags)
	var coin := Coin.new()
	coin.custom_minimum_size = Vector2(13, 13)
	coin.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	_status_row.add_child(coin)
	_coins = _lbl(15, UiTheme.BRASS_BRIGHT, "bold")
	_status_row.add_child(_coins)

	# --- bottom centre: message line above the prompt
	_msg = _lbl(17, UiTheme.TEXT, "italic")
	_msg.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_msg.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_msg.clip_text = true
	_msg.anchor_left = 0.22
	_msg.anchor_right = 0.78
	_msg.anchor_top = 1.0
	_msg.anchor_bottom = 1.0
	_msg.offset_top = -196
	_msg.offset_bottom = -170
	_msg.modulate.a = 0.0
	add_child(_msg)

	_prompt_row = HBoxContainer.new()
	_prompt_row.alignment = BoxContainer.ALIGNMENT_CENTER
	_prompt_row.add_theme_constant_override("separation", 9)
	_prompt_row.anchor_left = 0.3
	_prompt_row.anchor_right = 0.7
	_prompt_row.anchor_top = 1.0
	_prompt_row.anchor_bottom = 1.0
	_prompt_row.offset_top = -158
	_prompt_row.offset_bottom = -128
	_prompt_row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_prompt_row)
	var cap := PanelContainer.new()
	var cb := StyleBoxFlat.new()
	cb.bg_color = Color(0.05, 0.06, 0.09, 0.75)
	cb.border_color = Color(UiTheme.BRASS, 0.8)
	cb.set_border_width_all(1)
	cb.set_corner_radius_all(3)
	cb.content_margin_left = 8
	cb.content_margin_right = 8
	cb.content_margin_top = 0
	cb.content_margin_bottom = 1
	cap.add_theme_stylebox_override("panel", cb)
	cap.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var key := _lbl(15, UiTheme.BRASS_BRIGHT, "bold")
	key.text = "E"
	cap.add_child(key)
	_prompt_row.add_child(cap)
	_prompt_verb = _lbl(19, UiTheme.TEXT, "regular")
	_prompt_row.add_child(_prompt_verb)
	_prompt_row.visible = false

	# --- banner (curfew bell)
	_banner = _lbl(28, UiTheme.BRASS_BRIGHT, "display")
	_banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_banner.add_theme_constant_override("outline_size", 9)
	_banner.anchor_left = 0.1
	_banner.anchor_right = 0.9
	_banner.anchor_top = 0.22
	_banner.anchor_bottom = 0.22
	_banner.modulate.a = 0.0
	add_child(_banner)

	# --- journal note, bottom right
	_note = _lbl(14, UiTheme.BRASS, "italic")
	_note.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	_note.anchor_left = 1.0
	_note.anchor_right = 1.0
	_note.anchor_top = 1.0
	_note.anchor_bottom = 1.0
	_note.offset_left = -520
	_note.offset_right = -22
	_note.offset_top = -42
	_note.offset_bottom = -18
	_note.modulate.a = 0.0
	add_child(_note)


func _lbl(size: int, col: Color, face: String = "regular") -> Label:
	var l := Label.new()
	l.add_theme_font_override("font", UiTheme.font(face))
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", col)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	l.add_theme_constant_override("outline_size", 6)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


## The first objective still to do (optional ones last), shortened to its first clause.
static func current_objective() -> String:
	for want_optional in [false, true]:
		for o in Mission.objectives:
			if not o["done"] and bool(o.get("optional", false)) == want_optional:
				return short_text(str(o["text"]))
	return ""


## First clause of a sentence: up to the first ':' or ' (' (the journal keeps the whole text).
static func short_text(t: String) -> String:
	for cut in [": ", " ("]:
		var i := t.find(cut)
		if i > 8:
			t = t.substr(0, i)
	return t.strip_edges()


## One line for the screen: the first line, then the first sentence or clause.
static func one_line(t: String) -> String:
	t = t.strip_edges().get_slice("\n", 0)
	var best := t.length()
	for cut in [". ", "! ", "? ", ": ", "; "]:
		var i := t.find(cut)
		if i > 10 and i < best:
			best = i + (1 if cut[0] in ".!?" else 0)
	return t.substr(0, best).strip_edges()


static func clip_words(t: String, n: int) -> String:
	if t.length() <= n:
		return t
	var cut := t.substr(0, n)
	var sp := cut.rfind(" ")
	return (cut.substr(0, sp) if sp > n / 2 else cut).rstrip(",;: ") + "…"


func _rebuild() -> void:
	var cur := current_objective()
	_obj.text = clip_words(cur, 56) if cur != "" else "Done. Get clear before dawn."
	if cur != _objective_key:
		_objective_key = cur
		_show(SHOW_CHANGE)


func _show(secs: float) -> void:
	_show_left = maxf(_show_left, secs)


func _process(delta: float) -> void:
	_show_left = maxf(_show_left - delta, 0.0)
	var target := 1.0 if _show_left > 0.0 else 0.0
	_alpha = move_toward(_alpha, target, delta / FADE)
	_obj_row.modulate.a = _alpha
	var p := get_tree().get_first_node_in_group("player")
	if p == null or not is_instance_valid(p):
		_prompt_row.visible = false
		return
	# Hearts show only once hurt, and then stay (with the purse row) while the objective line fades.
	var hp: int = p.get("health")
	_hurt = hp < 3
	_pips.text = ("●".repeat(maxi(hp, 0)) + "○".repeat(maxi(3 - hp, 0))) if _hurt else ""
	var tags: PackedStringArray = []
	if p.get("carrying"):
		tags.append("bundle")
	if p.get("disguised"):
		tags.append("cloaked")
	_tags.text = "   ".join(tags) + ("   ·" if not tags.is_empty() else "")
	_coins.text = str(GameState.coins)
	var key := "%d|%d|%s" % [GameState.coins, hp, _tags.text]
	if key != _status_key:
		if _status_key != "":
			_show(SHOW_CHANGE)
		_status_key = key
	_status_row.modulate.a = 1.0 if _hurt else _alpha
	# Prompt: key cap + verb.
	var raw := "" if Mission.dialogue_open() else str(p.get("prompt_text"))
	var verb := prompt_verb(raw)
	_prompt_row.visible = verb != ""
	_prompt_verb.text = verb


## "E   talk to the printer" -> "Talk"; "E   slip a false pamphlet into his pocket" -> "Plant".
static func prompt_verb(raw: String) -> String:
	var t := raw.strip_edges()
	if t.begins_with("E "):
		t = t.substr(2).strip_edges()
	if t == "":
		return ""
	var w := t.get_slice(" ", 0).to_lower()
	return VERBS.get(w, w.capitalize())


func _on_message(text: String, _seconds: float) -> void:
	var t := text
	if t.begins_with("Objective complete: "):
		t = "✓  " + short_text(t.trim_prefix("Objective complete: "))
	else:
		t = one_line(t)
	_msg.text = clip_words(t, 90)
	if _msg_tween:
		_msg_tween.kill()
	_msg_tween = create_tween()
	_msg_tween.tween_property(_msg, "modulate:a", 1.0, 0.2)
	_msg_tween.tween_interval(MESSAGE_SECONDS)
	_msg_tween.tween_property(_msg, "modulate:a", 0.0, 0.5)


func _on_announcement(text: String, _seconds: float) -> void:
	_banner.text = one_line(text)
	if _banner_tween:
		_banner_tween.kill()
	_banner_tween = create_tween()
	_banner_tween.tween_property(_banner, "modulate:a", 1.0, 0.4)
	_banner_tween.tween_interval(BANNER_SECONDS)
	_banner_tween.tween_property(_banner, "modulate:a", 0.0, 0.8)


## From journal.gd: a quiet "Journal · New storyline: ..." at the bottom right.
func note(text: String) -> void:
	_note.text = "✎  " + text + "    J"
	if _note_tween:
		_note_tween.kill()
	_note_tween = create_tween()
	_note_tween.tween_property(_note, "modulate:a", 1.0, 0.3)
	_note_tween.tween_interval(3.0)
	_note_tween.tween_property(_note, "modulate:a", 0.0, 0.8)


## A small brass coin for the purse.
class Coin extends Control:
	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		var c := size * 0.5
		var r := minf(size.x, size.y) * 0.5
		draw_circle(c, r, UiTheme.BRASS_DARK)
		draw_circle(c, r - 1.5, UiTheme.BRASS_BRIGHT)
		draw_arc(c, r - 3.5, 0.0, TAU, 20, UiTheme.BRASS_DARK, 1.0, true)
