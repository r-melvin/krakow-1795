extends CanvasLayer
## Night HUD, kept sparse: top left only the clock and a small watch eye (its colour follows the worst guard's
## suspicion) with the watch state in one word, and an alarm count once the watch has been roused. The controls
## line shows for the first 8 s of the first night only (after that they live in the pause menu's Journal,
## "Controls" tab). The mission block (objectives_panel.gd) and the journal (journal.gd) are added here.
## Stealth cues (StealthCues below, no text): a thin arc under the screen centre whose length is the player's
## visibility and whose colour is their noise (white quiet -> amber loud), and a chevron at the screen edge
## pointing at the most alarmed guard when he is off-screen. Sound rings, the last-known ghost and the guard cones
## are drawn in the world (watch.gd, guard.gd). A minimap (minimap.gd, bottom right, M toggles) shares the journal
## map's drawing (city_map.gd).

const HELP_SECONDS := 8.0
const STATE_WORDS := ["calm", "curious", "searching", "alarm"]

static var _help_shown := false  ## once per session: restarts and later nights do not repeat it

var _clock: Label
var _state: Label
var _alarms: Label
var _eye: WatchEye
var _help: Label


func _ready() -> void:
	var root := MarginContainer.new()
	root.set_anchors_preset(Control.PRESET_TOP_LEFT)
	root.add_theme_constant_override("margin_left", 22)
	root.add_theme_constant_override("margin_top", 14)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 0)
	root.add_child(v)

	_clock = _lbl(26, UiTheme.TEXT, "display")
	_clock.text = GameState.time_string()
	v.add_child(_clock)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 7)
	v.add_child(row)
	_eye = WatchEye.new()
	_eye.custom_minimum_size = Vector2(22, 14)
	_eye.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(_eye)
	_state = _lbl(15, UiTheme.TEXT_DIM, "italic")
	row.add_child(_state)
	_alarms = _lbl(14, UiTheme.BAD, "bold")
	row.add_child(_alarms)

	if not _help_shown and GameState.day == 1:
		_help_shown = true
		_help = _lbl(15, Color(UiTheme.TEXT, 0.75))
		_help.text = "WASD move    Shift sprint    Ctrl crouch    Z prone    Q/R lean    G throw    E use    F strike    J journal    Esc pause"
		_help.anchor_left = 0.0
		_help.anchor_top = 1.0
		_help.anchor_bottom = 1.0
		_help.offset_left = 22
		_help.offset_top = -40
		_help.offset_bottom = -16
		add_child(_help)
		var tw := _help.create_tween()
		tw.tween_interval(HELP_SECONDS)
		tw.tween_property(_help, "modulate:a", 0.0, 1.0)
		tw.tween_callback(_help.queue_free)

	add_child(StealthCues.new())
	# Kit indicator bottom left: the current item's icon and count (scripts/stealth/kit.gd Indicator).
	add_child(preload("res://scripts/stealth/kit.gd").Indicator.new())
	# Minimap bottom right (scripts/ui/minimap.gd, M toggles it); the full map is the journal's Map tab.
	add_child(preload("res://scripts/ui/minimap.gd").new())
	# Mission block: current objective top right, purse, interact prompt, one-line messages, curfew banner.
	add_child(preload("res://scripts/mission/objectives_panel.gd").new())
	# The journal (J / Tab, or from the pause menu): its own layer above the HUD, works while paused.
	add_child(preload("res://scripts/ui/journal.gd").new())


func _lbl(size: int, col: Color, face: String = "regular") -> Label:
	var l := Label.new()
	l.add_theme_font_override("font", UiTheme.font(face))
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", col)
	l.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.75))
	l.add_theme_constant_override("outline_size", 5)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


func _process(_d: float) -> void:
	var max_s := 0.0
	var worst := Guard.State.CALM
	for g in get_tree().get_nodes_in_group("guards"):
		if g.is_downed():
			continue
		max_s = maxf(max_s, g.suspicion)
		if g.state > worst:
			worst = g.state
	_eye.suspicion = max_s
	_eye.alarm = worst == Guard.State.ALARM
	_state.text = STATE_WORDS[worst]
	_state.add_theme_color_override("font_color", UiTheme.BAD if worst == Guard.State.ALARM else
			(UiTheme.BRASS_BRIGHT if worst > Guard.State.CALM else UiTheme.TEXT_DIM))
	_clock.text = GameState.time_string()
	var n := GameState.night_alarm_count
	_alarms.text = ("·  %d alarm%s" % [n, "" if n == 1 else "s"]) if n > 0 else ""


## A small drawn eye: dim when the watch is calm, warming to brass and then red as suspicion rises.
class WatchEye extends Control:
	var suspicion := 0.0:
		set(v):
			if absf(v - suspicion) > 0.5:
				suspicion = v
				queue_redraw()
	var alarm := false:
		set(v):
			if v != alarm:
				alarm = v
				queue_redraw()

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _draw() -> void:
		var t := clampf(suspicion / 100.0, 0.0, 1.0)
		var col := Color(UiTheme.TEXT_DIM, 0.8).lerp(UiTheme.BRASS_BRIGHT, clampf(t * 2.0, 0.0, 1.0))
		if t > 0.5 or alarm:
			col = UiTheme.BRASS_BRIGHT.lerp(UiTheme.BAD, 1.0 if alarm else (t - 0.5) * 2.0)
		var c := size * 0.5
		var w := size.x * 0.5
		var h := size.y * 0.5
		var pts := PackedVector2Array()
		for i in 25:
			var a := TAU * i / 24.0
			pts.append(c + Vector2(cos(a) * w, sin(a) * h * (0.35 + 0.65 * absf(sin(a)))))
		draw_colored_polygon(pts, Color(0, 0, 0, 0.45))
		draw_polyline(pts, col, 1.5, true)
		draw_circle(c, h * (0.5 + 0.25 * t), col)
		draw_circle(c, h * 0.2, Color(0, 0, 0, 0.8))



## Stealth cues, drawn without text. `player` / `watch` may be set explicitly (the stealth smoke's sandbox);
## otherwise the "player" group and that player's watch are used.
class StealthCues extends Control:
	const Perception := preload("res://scripts/stealth/perception.gd")
	const ARC_RADIUS := 30.0
	const ARC_SPAN := deg_to_rad(130.0)
	var player: Node3D
	var watch: Node
	var _vis := 0.0
	var _noise := 0.0

	func _init() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE
		set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

	func _process(delta: float) -> void:
		if player == null or not is_instance_valid(player):
			player = get_tree().get_first_node_in_group("player") as Node3D
			watch = null
		if player and (watch == null or not is_instance_valid(watch)):
			watch = Perception.watch_of(player)
		if player:
			_vis = lerpf(_vis, float(player.get("visibility")), clampf(delta * 8.0, 0.0, 1.0))
			_noise = lerpf(_noise, clampf(float(player.get("noise")), 0.0, 1.0), clampf(delta * 6.0, 0.0, 1.0))
		queue_redraw()

	func _draw() -> void:
		if player == null or not is_instance_valid(player) or not player.is_inside_tree():
			return
		var vp := get_viewport_rect().size
		# The visibility meter moved onto the watchers (a ring over each guard's head fills as he takes the player
		# in). Here only the hidden dot and the off-screen chevron remain.
		var c := Vector2(vp.x * 0.5, vp.y * 0.775)
		if player.get("hidden_spot") != null and player.hidden_spot.get("hides_player"):
			draw_circle(c, 3.0, Color(0.6, 0.75, 0.95, 0.8))
		_draw_chevron(vp)

	func _draw_chevron(vp: Vector2) -> void:
		var cam := get_viewport().get_camera_3d()
		if cam == null or watch == null or not is_instance_valid(watch):
			return
		var best: Node3D = null
		var best_s := 19.0
		for g in watch.guards():
			if g.is_downed():
				continue
			var s: float = g.suspicion + (100.0 if g.is_runner else 0.0)
			if (g.state > 0 or g.is_runner) and s > best_s:
				best_s = s
				best = g
		if best == null:
			return
		var wp: Vector3 = best.global_position + Vector3(0, 1.6, 0)
		var behind := cam.is_position_behind(wp)
		var sp := cam.unproject_position(wp)
		var margin := 40.0
		var rect := Rect2(Vector2(margin, margin), vp - Vector2(margin, margin) * 2.0)
		if not behind and rect.has_point(sp):
			return
		var centre := vp * 0.5
		var dir := (sp - centre)
		if behind:
			dir = -dir
		if dir.length() < 1.0:
			dir = Vector2(0, 1)
		dir = dir.normalized()
		var sx := (rect.size.x * 0.5) / maxf(absf(dir.x), 0.001)
		var sy := (rect.size.y * 0.5) / maxf(absf(dir.y), 0.001)
		var p := centre + dir * minf(sx, sy)
		var col := Color(1.0, 0.78, 0.3, 0.85)
		if best.state >= 2:
			col = Color(1.0, 0.5, 0.2, 0.9)
		if best.state >= 3 or best.is_runner:
			col = Color(1.0, 0.25, 0.18, 0.95)
		var perp := Vector2(-dir.y, dir.x)
		var tip := p + dir * 13.0
		var pts := PackedVector2Array([tip, p - dir * 7.0 + perp * 13.0, p - dir * 1.0, p - dir * 7.0 - perp * 13.0])
		draw_colored_polygon(pts, col)
		draw_polyline(PackedVector2Array([pts[0], pts[1], pts[2], pts[3], pts[0]]), Color(0, 0, 0, 0.5), 1.0, true)
