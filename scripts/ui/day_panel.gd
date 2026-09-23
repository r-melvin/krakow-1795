extends Control
## Day phase: status of factions and districts, then go out for the night.
## Dawn phase reuses this with a mission summary at the top.

signal go_out

var _text: RichTextLabel
var _button: Button
var _summary := ""


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	var bg := ColorRect.new()
	bg.color = Color(0.1, 0.09, 0.07)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)
	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["margin_left", "margin_right", "margin_top", "margin_bottom"]:
		margin.add_theme_constant_override(side, 40)
	add_child(margin)
	var v := VBoxContainer.new()
	margin.add_child(v)
	_text = RichTextLabel.new()
	_text.bbcode_enabled = true
	_text.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(_text)
	_button = Button.new()
	_button.text = "Go out tonight"
	_button.pressed.connect(func(): go_out.emit())
	v.add_child(_button)
	refresh()


func set_summary(s: String) -> void:
	_summary = s
	refresh()


func refresh() -> void:
	var t := ""
	if _summary != "":
		t += "[b]Dawn report[/b]\n%s\n\n" % _summary
	t += "[b]Day %d[/b]   %s, %s\nCrackdown: %d / 100    Districts held: %d / %d\n\n" % [
		GameState.day, GameState.origin.get("name", "?"), GameState.origin.get("goal", ""),
		GameState.crackdown, GameState.controlled_district_count(), GameState.districts.size()]
	t += "[b]Factions[/b]\n"
	for fid in GameState.factions:
		var f: Dictionary = GameState.factions[fid]
		if f["external"]:
			continue
		var val := int(f["influence"])
		var bar := "█".repeat(int(val / 5)) + "░".repeat(20 - int(val / 5))
		t += "%-22s %s %3d   [i]%s[/i]\n" % [f["name"], bar, val, f["agenda"]]
	t += "\n[b]Occupiers[/b]\n"
	for fid in ["austria", "russia", "prussia"]:
		var f: Dictionary = GameState.factions[fid]
		t += "%-10s strength %d   [i]%s[/i]\n" % [f["name"], f["strength"], f["agenda"]]
	t += "\n[b]Districts[/b]\n"
	for did in GameState.districts:
		var d: Dictionary = GameState.districts[did]
		t += "%-20s held by %-22s unrest %2d   watch %d\n" % [d["name"], GameState.factions[d["controller"]]["name"], d["unrest"], d["watch"]]
	t += "\n[i]Tonight: a message must reach the boatmen's safe house across the Rynek. The Austrian watch patrols the square.[/i]"
	_text.text = t
