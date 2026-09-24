extends Node
## Scene root. Swaps between splash, main menu, origin select, day briefing, the night mission and the dawn
## result based on GameState.phase. UI screens live on `_ui_layer`; the pause overlay and the phase fade sit
## on layers above it.

const Splash := preload("res://scripts/ui/splash.gd")
const MainMenu := preload("res://scripts/ui/main_menu.gd")
const OriginSelect := preload("res://scripts/ui/origin_select.gd")
const DayPanel := preload("res://scripts/ui/day_panel.gd")
const DawnPanel := preload("res://scripts/ui/dawn_panel.gd")
const PauseMenu := preload("res://scripts/ui/pause_menu.gd")
const Hud := preload("res://scripts/ui/hud.gd")
const District := preload("res://scripts/city/greybox_district.gd")
const PlayerScript := preload("res://scripts/stealth/player.gd")

var _ui_layer: CanvasLayer
var _top_layer: CanvasLayer      ## pause overlay
var _fade: ColorRect             ## black veil faded out on every phase change
var _world: Node3D
var _screen: Control             ## current full-screen UI, if any
var _pause: Control


func _ready() -> void:
	get_tree().root.theme = UiTheme.get_theme()
	add_child(Sfx.new())          # sound library + voice pool (scripts/audio, docs/AUDIO.md)
	add_child(Ambience.new())     # wind, murmur, crowds, taverns, bells and the hejnal
	_ui_layer = CanvasLayer.new()
	add_child(_ui_layer)
	_top_layer = CanvasLayer.new()
	_top_layer.layer = 20
	_top_layer.process_mode = Node.PROCESS_MODE_ALWAYS
	add_child(_top_layer)
	var fade_layer := CanvasLayer.new()
	fade_layer.layer = 50
	add_child(fade_layer)
	_fade = ColorRect.new()
	_fade.color = Color.BLACK
	_fade.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_fade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	fade_layer.add_child(_fade)
	GameState.phase_changed.connect(_on_phase)
	_on_phase(GameState.phase)
	if "--smoke" in OS.get_cmdline_user_args():
		_smoke()


func _clear() -> void:
	get_tree().paused = false
	for c in _ui_layer.get_children():
		c.queue_free()
	for c in _top_layer.get_children():
		c.queue_free()
	_screen = null
	_pause = null
	if _world:
		_world.queue_free()
		_world = null
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _on_phase(p: GameState.Phase) -> void:
	_clear()
	match p:
		GameState.Phase.SPLASH:
			_screen = _add_screen(Splash)
		GameState.Phase.MENU:
			_screen = _add_screen(MainMenu)
		GameState.Phase.ORIGIN_SELECT:
			_screen = _add_screen(OriginSelect)
			_screen.chosen.connect(GameState.choose_origin)
		GameState.Phase.DAY:
			_screen = _add_screen(DayPanel)
			_screen.go_out.connect(GameState.begin_night)
		GameState.Phase.DAWN:
			_screen = _add_screen(DawnPanel)
		GameState.Phase.NIGHT:
			_start_night()
	_fade.color.a = 1.0
	var tw := create_tween()
	tw.tween_property(_fade, "color:a", 0.0, 0.8 if p == GameState.Phase.NIGHT else 0.35)


func _add_screen(script: GDScript) -> Control:
	var c := Control.new()
	c.set_script(script)
	_ui_layer.add_child(c)
	return c


func _start_night() -> void:
	_world = Node3D.new()
	_world.set_script(District)
	add_child(_world)
	var player := CharacterBody3D.new()
	player.set_script(PlayerScript)
	player.position = _world.player_spawn()
	_world.add_child(player)
	player.add_child(District.avoidance_obstacle(0.45))
	Mission.start("printers_bundle", _world)     # mission actors, props, dialogue; objectives for the HUD
	var hud := CanvasLayer.new()
	hud.set_script(Hud)
	_ui_layer.add_child(hud)
	for c in hud.get_children():     # CanvasLayer breaks theme inheritance; give the HUD's roots the theme
		if c is Control:
			c.theme = UiTheme.get_theme()
	_pause = Control.new()
	_pause.set_script(PauseMenu)
	_top_layer.add_child(_pause)


## Headless smoke test: `godot --headless --path . --quit-after 600 -- --smoke`
func _smoke() -> void:
	await get_tree().process_frame
	print("[smoke] origins=%d factions=%d districts=%d" % [GameState.origins.size(), GameState.factions.size(), GameState.districts.size()])
	await _ui_shot("splash", 3.0)
	if _ui_shot_dir() != "":
		var notice := _add_screen(preload("res://scripts/ui/content_notice.gd"))
		await _ui_shot("notice", 1.0)
		notice.queue_free()
	GameState.to_menu()
	await get_tree().process_frame
	await _ui_shots_menu()
	GameState.new_game()
	await get_tree().process_frame
	await _ui_shots_origin()
	GameState.choose_origin("veteran", "f" if "--woman" in OS.get_cmdline_user_args() else "m")
	await get_tree().process_frame
	await _ui_shot("day", 1.0)
	print("[smoke] phase=%s street=%d" % [GameState.Phase.keys()[GameState.phase], GameState.get_influence("street")])
	GameState.begin_night()
	for i in 90:
		await get_tree().physics_frame
	await _ui_shots_pause()
	var guards := get_tree().get_nodes_in_group("guards")
	var player := get_tree().get_first_node_in_group("player") as Player
	print("[smoke] guards=%d player=%s" % [guards.size(), player.global_position if player else "none"])
	print("[smoke] npcs=%d animals=%d" % [get_tree().get_nodes_in_group("npcs").size(), get_tree().get_nodes_in_group("animals").size()])
	await _smoke_schedules(player)
	await _perf_report()
	print("[smoke] audio ", Sfx.smoke(), "\n[smoke] audio ambience ", (get_node("Ambience") as Ambience).report())
	await _shots(player)
	for g in guards:
		print("[smoke]   %-16s state=%s suspicion=%.1f pos=%s" % [g.guard_name, Guard.State.keys()[g.state], g.suspicion, g.global_position])
	# Walk in front of a guard: expect suspicion to rise.
	player.global_position = guards[2].global_position + -guards[2].global_transform.basis.z * 4.0
	for i in 120:
		await get_tree().physics_frame
	var g2: Guard = guards[2]
	var to_p := player.head_position() - (g2.global_position + Vector3(0, 1.5, 0))
	var space := g2.get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.create(g2.global_position + Vector3(0, 1.5, 0), player.head_position())
	q.exclude = [g2.get_rid()]
	var hit := space.intersect_ray(q)
	print("[smoke] sentry dist=%.2f angle=%.1f fwd=%s hit=%s perceive=%.2f visibility=%.2f" % [to_p.length(), rad_to_deg((-g2.global_transform.basis.z).angle_to(to_p.normalized())), -g2.global_transform.basis.z, (str(hit.get("collider").get_path()) if not hit.is_empty() else "none"), g2._perceive(), player.visibility])
	print("[smoke] after exposure: sentry state=%s suspicion=%.1f alarms=%d" % [Guard.State.keys()[guards[2].state], guards[2].suspicion, GameState.night_alarm_count])
	# The mission, three times (underworld, street, salon; each a fresh night), then a combat check and a failure.
	var mission_smoke: Node = preload("res://scripts/mission/mission_smoke.gd").new()
	add_child(mission_smoke)
	await mission_smoke.run_all(self)
	mission_smoke.queue_free()
	if GameState.phase == GameState.Phase.NIGHT:
		var sh := _world.get_node_or_null("SafeHouse") as Node3D
		player.global_position = (sh.global_position if sh else Vector3(26, 0, 25)) + Vector3(0, 0.5, 0)
		for i in 10:
			await get_tree().physics_frame
	print("[smoke] phase=%s day=%d crackdown=%d underworld=%d" % [GameState.Phase.keys()[GameState.phase], GameState.day, GameState.crackdown, GameState.get_influence("underworld")])
	if _ui_shot_dir() != "" and GameState.phase == GameState.Phase.NIGHT:
		GameState.end_night(true)    # shot mode only: force a dawn so the result screen can be captured
	await _ui_shot("dawn", 1.2)
	get_tree().quit()


## Waits for the runtime navmesh, reports the clock, schedules and storylines, then runs the clock at
## 60 game minutes per second for 200 physics frames and counts the NPCs whose schedule moved them.
func _smoke_schedules(player: Player) -> void:
	for i in 300:
		if _world.nav_ready():
			break
		await get_tree().physics_frame
	var pop := _world.get_node_or_null("Population")
	var bad: PackedStringArray = pop.unreachable_posts() if pop else PackedStringArray()
	print("[smoke] clock=%s navmesh_polys=%d scheduled=%d storylines=%d unreachable_posts=%s" % [GameState.time_string(),
			_world.navmesh_polygons(), pop.scheduled_count() if pop else 0, pop.storylines.size() if pop else 0, bad])
	var before := {}
	for n in get_tree().get_nodes_in_group("scheduled"):
		before[n] = n.post_changes
	# Park the player out of sight behind the north row so the fast-forward cannot end the night.
	var spawn := player.global_position
	player.global_position = Vector3(-40, 0.5, -40)
	GameState.clock_scale = 60.0
	var t0 := GameState.time_string()
	for i in 200:
		await get_tree().physics_frame
	GameState.clock_scale = 1.0
	var changed := 0
	var moves := 0
	for n in before:
		if n.post_changes > before[n]:
			changed += 1
			moves += n.post_changes - before[n]
	var inside := 0
	var walking := 0
	for n in get_tree().get_nodes_in_group("npcs"):
		if n.is_inside():
			inside += 1
		elif n.is_moving():
			walking += 1
	var stories := PackedStringArray()
	for s in pop.storylines:
		stories.append("%s=%s" % [s.story_id, s.Status.keys()[s.status]])
	print("[smoke] clock %s -> %s: npcs_changed_post=%d/%d moves=%d walking=%d inside=%d stories=%s" % [t0, GameState.time_string(),
			changed, before.size(), moves, walking, inside, ", ".join(stories)])
	player.global_position = spawn
	for i in 5:
		await get_tree().physics_frame


## With `-- --smoke --shot=/dir`, saves player-view and overhead PNGs (needs a real window, not --headless).
## Frame-time and scene-size figures for the optimisation pass: averaged over 120 frames of the player's view.
## Headless runs report the scene counts only (no frames are rendered there).
func _perf_report() -> void:
	var t0 := Time.get_ticks_usec()
	var frames := 120
	for i in frames:
		await get_tree().process_frame
	var ms := (Time.get_ticks_usec() - t0) / 1000.0 / frames
	var objs := Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME)
	var prims := Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)
	var draws := Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)
	var vram := Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0
	var tex := Performance.get_monitor(Performance.RENDER_TEXTURE_MEM_USED) / 1048576.0
	var nodes := Performance.get_monitor(Performance.OBJECT_NODE_COUNT)
	var lights := get_tree().get_nodes_in_group("flame_lights").size()
	var mem := Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0
	print("[smoke] perf frame_ms=%.2f fps=%.0f objects=%d primitives=%d draw_calls=%d vram_mb=%.0f tex_mb=%.0f nodes=%d lights=%d ram_mb=%.0f load_s=%.1f" % [
		ms, 1000.0 / maxf(ms, 0.01), objs, prims, draws, vram, tex, nodes, lights, mem, Time.get_ticks_msec() / 1000.0])


func _shots(player: Player) -> void:
	var dir := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			dir = a.trim_prefix("--shot=")
	if dir == "":
		return
	player.rotate_camera(Vector3(-0.15, -PI * 0.75, 0))
	for i in 5:
		await get_tree().process_frame
	get_viewport().get_texture().get_image().save_png(dir + "/player_view.png")
	var cam := Camera3D.new()
	cam.position = Vector3(0, 70, 45)
	cam.look_at_from_position(cam.position, Vector3(0, 0, 0))
	_world.add_child(cam)
	cam.current = true
	for i in 5:
		await get_tree().process_frame
	get_viewport().get_texture().get_image().save_png(dir + "/overhead.png")
	# close-ups of the populated square
	for shot in [["stmarys_door", Vector3(30, 2.2, -8), Vector3(31, 1.4, -15)], ["stalls", Vector3(-6, 2.0, -8), Vector3(-11, 1.2, -13)],
			["townhall_corner", Vector3(-8, 2.0, 22), Vector3(-14, 1.2, 17)], ["cloth_hall_passage", Vector3(0, 1.8, 12), Vector3(0, 1.2, 6)],
			["dragon", Vector3(-30, 2.5, 30), Vector3(-38, 1.5, 36)], ["delivery_alley", Vector3(19, 2.4, 9), Vector3(25, 1.3, 16)],
			["player_closeup", player.global_position + Vector3(0.6, 1.7, -2.2), player.global_position + Vector3(0, 1.45, 0)]]:
		cam.position = shot[1]
		cam.look_at_from_position(shot[1], shot[2])
		for i in 4:
			await get_tree().process_frame
		get_viewport().get_texture().get_image().save_png(dir + "/shot_" + shot[0] + ".png")
	cam.queue_free()
	print("[smoke] screenshots in ", dir)


# ------------------------------------------------------------------ UI screenshots (`-- --smoke --shot-ui=/dir`)

func _ui_shot_dir() -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot-ui="):
			return a.trim_prefix("--shot-ui=")
	return ""


## Waits `wait` seconds of real time (so fades finish), then saves ui_<name>.png. No-op without --shot-ui.
func _ui_shot(name: String, wait: float = 0.8) -> void:
	var dir := _ui_shot_dir()
	if dir == "" or DisplayServer.get_name() == "headless":
		return
	await get_tree().create_timer(wait, true, false, true).timeout
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(dir.path_join("ui_%s.png" % name))
	print("[smoke] ui shot ", name)


func _ui_shots_menu() -> void:
	if _ui_shot_dir() == "":
		return
	await _ui_shot("menu", 1.0)
	if _screen and _screen.has_method("_show_options"):
		_screen.call("_show_options")
		await _ui_shot("menu_options", 0.6)
		_screen.call("_show_credits")
		await _ui_shot("menu_credits", 0.6)
		_screen.call("_back")


## Waits (up to 30 s) for the threaded figure load, then shoots the man and the woman.
func _ui_shots_origin() -> void:
	if _ui_shot_dir() == "" or _screen == null or not _screen.has_method("preview_ready"):
		return
	for sex in ["m", "f"]:
		if sex == "f":
			_screen.call("_set_sex", "f")
		var t := 0.0
		while not _screen.preview_ready() and t < 30.0:
			await get_tree().process_frame
			t += get_process_delta_time()
		print("[smoke] origin preview %s ready=%s after %.1fs" % [sex, _screen.preview_ready(), t])
		await _ui_shot("origin_select" if sex == "m" else "origin_select_f", 1.2)
	_screen.call("_set_sex", "m")


func _ui_shots_pause() -> void:
	if _ui_shot_dir() == "" or _pause == null:
		return
	await _ui_shot("night_hud", 0.5)
	_pause.call("open")
	await _ui_shot("pause", 0.5)
	_pause.call("_show_options")
	await _ui_shot("pause_options", 0.4)
	_pause.call("resume")
	await get_tree().process_frame
