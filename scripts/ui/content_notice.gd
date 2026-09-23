extends Control
## Shown once per launch between the title card and the main menu: what the player is walking into.
## The game depicts the partition years as they were, including the prejudices of the time, and some
## choices are closed to a character because of who they are. Continue with any confirm key or the button.

signal accepted

const Backdrop := preload("res://scripts/ui/backdrop.gd")

const HEADING := "Before you go out"
const BODY := (
	"Kraków, 1795. This game does not soften the years it is set in.\n\n"
	+ "The city is occupied. There is violence in the streets, public punishment on the square, poverty, "
	+ "drink, prostitution, disease and cold that kills. The watch beats people. The powers that rule here "
	+ "and many of the people who live here hold the bigotries of their age: against Jews, against the "
	+ "peasantry, against foreigners, against women who act outside their station, against anyone whose "
	+ "desires were then a crime. Characters will voice those views. The game presents them as the world "
	+ "the player has to move through, not as views it shares.\n\n"
	+ "Who you are matters. Some doors, roles and conversations will be closed to your character because "
	+ "of their sex, their origin, their faith or their inclinations, exactly as they would have been. "
	+ "Other doors open for the same reasons. Finding the way round is part of the game."
)

var _ok: Button
var _leaving := false


func _ready() -> void:
	theme = UiTheme.get_theme()
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var bg := ColorRect.new()
	bg.color = UiTheme.BG
	add_child(UiTheme.full_rect(bg))
	var back := Control.new()
	back.set_script(Backdrop)
	back.set("darken", 0.7)
	back.set("snow_count", 90)
	add_child(back)

	var panel := UiTheme.panel()
	panel.set_anchors_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(860, 0)
	panel.anchor_left = 0.5
	panel.anchor_right = 0.5
	panel.anchor_top = 0.5
	panel.anchor_bottom = 0.5
	panel.offset_left = -430
	panel.offset_right = 430
	panel.offset_top = -270
	panel.offset_bottom = 270
	add_child(panel)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 14)
	panel.add_child(v)
	v.add_child(UiTheme.kicker("A word before the game"))
	v.add_child(UiTheme.heading(HEADING, 40))
	v.add_child(HSeparator.new())
	var body := UiTheme.body(BODY, 19)
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	v.add_child(body)
	v.add_child(UiTheme.spacer(4))
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_END
	row.add_theme_constant_override("separation", 12)
	v.add_child(row)
	row.add_child(UiTheme.label("Enter or click to continue", 15, UiTheme.TEXT_DIM, "italic"))
	_ok = UiTheme.primary_button("I understand", _accept, 240)
	row.add_child(_ok)
	_ok.grab_focus.call_deferred()

	modulate.a = 0.0
	create_tween().tween_property(self, "modulate:a", 1.0, 0.6).set_trans(Tween.TRANS_SINE)


func _input(event: InputEvent) -> void:
	if _leaving:
		return
	if event.is_action_pressed("ui_accept") or (event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT and not _ok.get_global_rect().has_point(get_global_mouse_position())):
		get_viewport().set_input_as_handled()
		_accept()


func _accept() -> void:
	if _leaving:
		return
	_leaving = true
	var tw := create_tween()
	tw.tween_property(self, "modulate:a", 0.0, 0.45).set_trans(Tween.TRANS_SINE)
	tw.tween_callback(func() -> void: accepted.emit())
