class_name UiTheme
## Shared look for every front-end screen: blue-black panels, parchment text, brass accents.
## `UiTheme.get_theme()` builds the Theme once; the helpers make the recurring widgets.

const BG := Color("0a0e16")
const PANEL := Color(0.075, 0.098, 0.14, 0.94)
const PANEL_LIGHT := Color(0.11, 0.14, 0.195, 0.96)
const TEXT := Color("e9dec4")
const TEXT_DIM := Color("a39a86")
const BRASS := Color("c29a55")
const BRASS_BRIGHT := Color("e6c47f")
const BRASS_DARK := Color("6e5630")
const TROUGH := Color("1b2230")
const GOOD := Color("8fb37a")
const BAD := Color("c8604c")

const FONT_DIR := "res://assets/ui/fonts/"

static var _theme: Theme
static var _fonts: Dictionary = {}


## Display face for titles (light, regular, italic) and the text face (regular, italic, bold).
static func font(name: String) -> Font:
	if _fonts.has(name):
		return _fonts[name]
	var path: String = FONT_DIR + {
		"display_light": "NotoSerifDisplay-Light.ttf", "display": "NotoSerifDisplay-Regular.ttf",
		"display_italic": "NotoSerifDisplay-Italic.ttf", "regular": "NotoSerif-Regular.ttf",
		"italic": "NotoSerif-Italic.ttf", "bold": "NotoSerif-Bold.ttf"}.get(name, "NotoSerif-Regular.ttf")
	var f: Font = load(path) if ResourceLoader.exists(path) else ThemeDB.fallback_font
	_fonts[name] = f
	return f


static func get_theme() -> Theme:
	if _theme:
		return _theme
	var t := Theme.new()
	t.default_font = font("regular")
	t.default_font_size = 20

	t.set_color("font_color", "Label", TEXT)
	t.set_color("font_color", "RichTextLabel", TEXT)
	t.set_color("default_color", "RichTextLabel", TEXT)
	t.set_font("normal_font", "RichTextLabel", font("regular"))
	t.set_font("italics_font", "RichTextLabel", font("italic"))
	t.set_font("bold_font", "RichTextLabel", font("bold"))
	t.set_font_size("normal_font_size", "RichTextLabel", 20)
	t.set_font_size("italics_font_size", "RichTextLabel", 20)
	t.set_font_size("bold_font_size", "RichTextLabel", 20)
	t.set_constant("line_separation", "RichTextLabel", 4)

	t.set_stylebox("panel", "PanelContainer", panel_box())
	t.set_stylebox("panel", "Panel", panel_box())

	# Buttons: quiet by default, a brass rule on the left and warmer text when hovered or focused.
	var normal := _box(Color(0.1, 0.13, 0.18, 0.7), BRASS_DARK, 1, 3)
	var hover := _box(Color(0.16, 0.18, 0.21, 0.95), BRASS, 1, 3)
	hover.border_width_left = 4
	var pressed := _box(Color(0.2, 0.17, 0.12, 0.95), BRASS_BRIGHT, 1, 3)
	pressed.border_width_left = 4
	var disabled := _box(Color(0.08, 0.1, 0.13, 0.5), Color(0.25, 0.25, 0.25, 0.5), 1, 3)
	for b in [normal, hover, pressed, disabled]:
		b.content_margin_left = 18
		b.content_margin_right = 18
		b.content_margin_top = 8
		b.content_margin_bottom = 8
	t.set_stylebox("normal", "Button", normal)
	t.set_stylebox("hover", "Button", hover)
	t.set_stylebox("pressed", "Button", pressed)
	t.set_stylebox("hover_pressed", "Button", pressed)
	t.set_stylebox("focus", "Button", _focus_box())
	t.set_stylebox("disabled", "Button", disabled)
	t.set_color("font_color", "Button", TEXT)
	t.set_color("font_hover_color", "Button", BRASS_BRIGHT)
	t.set_color("font_focus_color", "Button", BRASS_BRIGHT)
	t.set_color("font_pressed_color", "Button", BRASS_BRIGHT)
	t.set_color("font_hover_pressed_color", "Button", BRASS_BRIGHT)
	t.set_color("font_disabled_color", "Button", Color(TEXT_DIM, 0.45))
	t.set_font_size("font_size", "Button", 21)

	# Menu buttons: no box at all until hovered.
	t.set_type_variation("MenuButtonFlat", "Button")
	var flat := StyleBoxEmpty.new()
	flat.content_margin_left = 22
	flat.content_margin_top = 6
	flat.content_margin_bottom = 6
	var flat_hover := StyleBoxFlat.new()
	flat_hover.bg_color = Color(BRASS, 0.10)
	flat_hover.border_color = BRASS
	flat_hover.border_width_left = 3
	flat_hover.content_margin_left = 22
	flat_hover.content_margin_top = 6
	flat_hover.content_margin_bottom = 6
	t.set_stylebox("normal", "MenuButtonFlat", flat)
	t.set_stylebox("disabled", "MenuButtonFlat", flat)
	t.set_stylebox("hover", "MenuButtonFlat", flat_hover)
	t.set_stylebox("pressed", "MenuButtonFlat", flat_hover)
	t.set_stylebox("hover_pressed", "MenuButtonFlat", flat_hover)
	t.set_stylebox("focus", "MenuButtonFlat", flat_hover)
	t.set_font("font", "MenuButtonFlat", font("display"))
	t.set_font_size("font_size", "MenuButtonFlat", 32)

	# Primary action: filled brass with dark ink.
	t.set_type_variation("PrimaryButton", "Button")
	var pn := _box(BRASS, BRASS_BRIGHT, 1, 3)
	var ph := _box(BRASS_BRIGHT, Color.WHITE, 1, 3)
	var pp := _box(BRASS_DARK, BRASS_BRIGHT, 1, 3)
	var pd := _box(Color(BRASS_DARK, 0.5), Color(BRASS_DARK, 0.5), 1, 3)
	for b in [pn, ph, pp, pd]:
		b.content_margin_left = 28
		b.content_margin_right = 28
		b.content_margin_top = 8
		b.content_margin_bottom = 10
	t.set_stylebox("normal", "PrimaryButton", pn)
	t.set_stylebox("hover", "PrimaryButton", ph)
	t.set_stylebox("pressed", "PrimaryButton", pp)
	t.set_stylebox("hover_pressed", "PrimaryButton", pp)
	t.set_stylebox("disabled", "PrimaryButton", pd)
	var pf := _focus_box()
	pf.border_color = Color.WHITE
	pf.set_border_width_all(2)
	pf.set_expand_margin_all(3)
	t.set_stylebox("focus", "PrimaryButton", pf)
	var ink := Color("141820")
	for k in ["font_color", "font_hover_color", "font_focus_color", "font_hover_pressed_color"]:
		t.set_color(k, "PrimaryButton", ink)
	t.set_color("font_pressed_color", "PrimaryButton", TEXT)
	t.set_font("font", "PrimaryButton", font("display"))
	t.set_font_size("font_size", "PrimaryButton", 28)

	for cls in ["CheckButton", "CheckBox"]:
		t.set_color("font_color", cls, TEXT)
		t.set_color("font_hover_color", cls, BRASS_BRIGHT)
		t.set_color("font_focus_color", cls, BRASS_BRIGHT)
		t.set_color("font_pressed_color", cls, TEXT)
		t.set_color("font_hover_pressed_color", cls, BRASS_BRIGHT)
		var e := StyleBoxEmpty.new()
		e.content_margin_left = 4
		t.set_stylebox("normal", cls, e)
		t.set_stylebox("hover", cls, e)
		t.set_stylebox("pressed", cls, e)
		t.set_stylebox("hover_pressed", cls, e)
		t.set_stylebox("focus", cls, _focus_box())

	t.set_icon("checked", "CheckButton", _switch(true))
	t.set_icon("unchecked", "CheckButton", _switch(false))
	t.set_icon("checked_disabled", "CheckButton", _switch(true))
	t.set_icon("unchecked_disabled", "CheckButton", _switch(false))
	t.set_constant("h_separation", "CheckButton", 16)

	var trough := _box(TROUGH, Color(BRASS_DARK, 0.6), 1, 2)
	var fill := _box(BRASS, BRASS, 0, 2)
	t.set_stylebox("background", "ProgressBar", trough)
	t.set_stylebox("fill", "ProgressBar", fill)
	t.set_color("font_color", "ProgressBar", TEXT)

	var slider := _box(TROUGH, Color(BRASS_DARK, 0.8), 1, 2)
	slider.content_margin_top = 4
	slider.content_margin_bottom = 4
	var area := _box(BRASS, BRASS, 0, 2)
	area.content_margin_top = 4
	area.content_margin_bottom = 4
	t.set_stylebox("slider", "HSlider", slider)
	t.set_stylebox("grabber_area", "HSlider", area)
	t.set_stylebox("grabber_area_highlight", "HSlider", _box(BRASS_BRIGHT, BRASS_BRIGHT, 0, 2))
	t.set_stylebox("focus", "HSlider", _focus_box())
	t.set_icon("grabber", "HSlider", _dot(18, BRASS_BRIGHT))
	t.set_icon("grabber_highlight", "HSlider", _dot(20, Color.WHITE))

	var sep := StyleBoxLine.new()
	sep.color = Color(BRASS, 0.45)
	sep.thickness = 1
	t.set_stylebox("separator", "HSeparator", sep)
	t.set_constant("separation", "HSeparator", 18)

	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(BRASS, 0.35)
	sb.set_corner_radius_all(3)
	t.set_stylebox("grabber", "VScrollBar", sb)
	t.set_stylebox("scroll", "VScrollBar", StyleBoxEmpty.new())
	t.set_stylebox("panel", "ScrollContainer", StyleBoxEmpty.new())
	_theme = t
	return t


static func panel_box(light: bool = false) -> StyleBoxFlat:
	var b := _box(PANEL_LIGHT if light else PANEL, Color(BRASS, 0.55), 1, 4)
	b.content_margin_left = 32
	b.content_margin_right = 32
	b.content_margin_top = 26
	b.content_margin_bottom = 26
	b.shadow_color = Color(0, 0, 0, 0.45)
	b.shadow_size = 18
	return b


static func _box(bg: Color, border: Color, width: int, radius: int) -> StyleBoxFlat:
	var b := StyleBoxFlat.new()
	b.bg_color = bg
	b.border_color = border
	b.set_border_width_all(width)
	b.set_corner_radius_all(radius)
	b.anti_aliasing = true
	return b


static func _focus_box() -> StyleBoxFlat:
	var b := StyleBoxFlat.new()
	b.draw_center = false
	b.border_color = Color(BRASS_BRIGHT, 0.7)
	b.set_border_width_all(1)
	b.set_corner_radius_all(3)
	return b


static func _dot(size: int, col: Color) -> ImageTexture:
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var r := size * 0.5
	for y in size:
		for x in size:
			var d := Vector2(x + 0.5 - r, y + 0.5 - r).length()
			img.set_pixel(x, y, Color(col, clampf(r - d, 0.0, 1.0)))
	return ImageTexture.create_from_image(img)


## A pill switch: brass with the knob right when on, dark with the knob left when off.
static func _switch(on: bool) -> ImageTexture:
	var w := 56
	var h := 28
	var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
	var r := h * 0.5
	var track := BRASS if on else TROUGH
	var edge := BRASS_BRIGHT if on else BRASS_DARK
	var knob_x := w - r if on else r
	for y in h:
		for x in w:
			var p := Vector2(x + 0.5, y + 0.5)
			var cx := clampf(p.x, r, w - r)
			var d := p.distance_to(Vector2(cx, r))
			var a := clampf(r - d, 0.0, 1.0)
			var col := track.lerp(edge, clampf(1.5 - (r - d), 0.0, 1.0))
			var kd := p.distance_to(Vector2(knob_x, r))
			var ka := clampf(r - 4.0 - kd, 0.0, 1.0)
			col = col.lerp(TEXT if on else TEXT_DIM, ka)
			img.set_pixel(x, y, Color(col, a))
	return ImageTexture.create_from_image(img)


# ---------------------------------------------------------------- widget helpers

static func label(text: String, size: int = 20, col: Color = TEXT, face: String = "regular") -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", col)
	if face != "regular":
		l.add_theme_font_override("font", font(face))
	return l


static func heading(text: String, size: int = 40) -> Label:
	return label(text, size, BRASS_BRIGHT, "display")


## Small caps-style overline above a heading.
static func kicker(text: String) -> Label:
	var l := label(text.to_upper(), 15, BRASS, "bold")
	l.add_theme_constant_override("line_spacing", 0)
	return l


static func body(text: String, size: int = 20, col: Color = TEXT) -> Label:
	var l := label(text, size, col)
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	return l


static func panel(light: bool = false) -> PanelContainer:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", panel_box(light))
	return p


static func button(text: String, cb: Callable, min_w: float = 0.0) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size.x = min_w
	b.pressed.connect(cb)
	return b


static func primary_button(text: String, cb: Callable, min_w: float = 0.0) -> Button:
	var b := button(text, cb, min_w)
	b.theme_type_variation = "PrimaryButton"
	b.custom_minimum_size.y = 60
	return b


static func menu_button(text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.theme_type_variation = "MenuButtonFlat"
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.pressed.connect(cb)
	return b


static func bar(value: float, max_value: float = 100.0, col: Color = BRASS, height: float = 14.0) -> ProgressBar:
	var p := ProgressBar.new()
	p.max_value = max_value
	p.value = value
	p.show_percentage = false
	p.custom_minimum_size = Vector2(120, height)
	p.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	if col != BRASS:
		p.add_theme_stylebox_override("fill", _box(col, col, 0, 2))
	return p


## A labelled faction row: name, bar, number.
static func stat_row(name: String, value: int, col: Color = BRASS, name_w: float = 190.0) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 14)
	var n := label(name, 18, TEXT)
	n.custom_minimum_size.x = name_w
	h.add_child(n)
	var b := bar(value, 100, col)
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h.add_child(b)
	var v := label(str(value), 18, BRASS_BRIGHT, "bold")
	v.custom_minimum_size.x = 36
	v.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	h.add_child(v)
	return h


static func margin(c: Control, px: int) -> MarginContainer:
	var m := MarginContainer.new()
	for side in ["margin_left", "margin_right", "margin_top", "margin_bottom"]:
		m.add_theme_constant_override(side, px)
	m.add_child(c)
	return m


static func spacer(h: float) -> Control:
	var c := Control.new()
	c.custom_minimum_size.y = h
	return c


static func full_rect(c: Control) -> Control:
	c.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	return c
