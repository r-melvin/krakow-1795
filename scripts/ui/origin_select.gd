extends Control
## Choose who you are. Shows starting influence per faction so the trade-offs are visible.

signal chosen(origin_id: String)

var _detail: RichTextLabel
var _selected := ""
var _start: Button


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	var bg := ColorRect.new()
	bg.color = Color(0.08, 0.06, 0.05)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)

	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["margin_left", "margin_right", "margin_top", "margin_bottom"]:
		margin.add_theme_constant_override(side, 40)
	add_child(margin)

	var v := VBoxContainer.new()
	margin.add_child(v)

	var title := Label.new()
	title.text = "KRAKÓW, WINTER 1795. The Commonwealth is gone. Who are you?"
	title.add_theme_font_size_override("font_size", 28)
	v.add_child(title)

	var h := HBoxContainer.new()
	h.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(h)

	var list := VBoxContainer.new()
	list.custom_minimum_size.x = 260
	h.add_child(list)
	for id in GameState.origins:
		var b := Button.new()
		b.text = GameState.origins[id]["name"]
		b.pressed.connect(_select.bind(id))
		list.add_child(b)

	_detail = RichTextLabel.new()
	_detail.bbcode_enabled = true
	_detail.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_detail.size_flags_vertical = Control.SIZE_EXPAND_FILL
	h.add_child(_detail)

	_start = Button.new()
	_start.text = "Begin"
	_start.disabled = true
	_start.pressed.connect(func(): chosen.emit(_selected))
	v.add_child(_start)


func _select(id: String) -> void:
	_selected = id
	_start.disabled = false
	var o: Dictionary = GameState.origins[id]
	var t := "[b]%s[/b]\n\n%s\n\n[b]Goal:[/b] %s\n[b]Weakness:[/b] %s\n\n[b]Starting influence[/b]\n" % [o["name"], o["blurb"], o["goal"], o["weakness"]]
	for fid in o["influence"]:
		var val := int(o["influence"][fid])
		var bar := "█".repeat(int(val / 5)) + "░".repeat(20 - int(val / 5))
		t += "%-22s %s %d\n" % [GameState.factions[fid]["name"], bar, val]
	t += "\n[b]Skills[/b]  "
	for s in o["skills"]:
		t += "%s %d   " % [s, o["skills"][s]]
	_detail.text = t
