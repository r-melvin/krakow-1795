extends Node
## Scene root. Swaps between origin select, day panel, and the night mission based on GameState.phase.

const OriginSelect := preload("res://scripts/ui/origin_select.gd")
const DayPanel := preload("res://scripts/ui/day_panel.gd")
const Hud := preload("res://scripts/ui/hud.gd")
const District := preload("res://scripts/city/greybox_district.gd")
const PlayerScript := preload("res://scripts/stealth/player.gd")

var _ui_layer: CanvasLayer
var _world: Node3D
var _pending_summary := ""


func _ready() -> void:
	_ui_layer = CanvasLayer.new()
	add_child(_ui_layer)
	GameState.phase_changed.connect(_on_phase)
	GameState.mission_ended.connect(_on_mission_ended)
	_on_phase(GameState.phase)
	if "--smoke" in OS.get_cmdline_user_args():
		_smoke()


func _clear() -> void:
	for c in _ui_layer.get_children():
		c.queue_free()
	if _world:
		_world.queue_free()
		_world = null
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE


func _on_phase(p: GameState.Phase) -> void:
	_clear()
	match p:
		GameState.Phase.ORIGIN_SELECT:
			var s := Control.new()
			s.set_script(OriginSelect)
			_ui_layer.add_child(s)
			s.chosen.connect(GameState.choose_origin)
		GameState.Phase.DAY, GameState.Phase.DAWN:
			var d := Control.new()
			d.set_script(DayPanel)
			_ui_layer.add_child(d)
			d.set_summary(_pending_summary)
			_pending_summary = ""
			d.go_out.connect(GameState.begin_night)
		GameState.Phase.NIGHT:
			_start_night()


func _start_night() -> void:
	_world = Node3D.new()
	_world.set_script(District)
	add_child(_world)
	var player := CharacterBody3D.new()
	player.set_script(PlayerScript)
	player.position = _world.player_spawn()
	_world.add_child(player)
	var hud := CanvasLayer.new()
	hud.set_script(Hud)
	_ui_layer.add_child(hud)


func _on_mission_ended(_success: bool, summary: String) -> void:
	_pending_summary = summary


## Headless smoke test: `godot --headless --path . --quit-after 600 -- --smoke`
func _smoke() -> void:
	await get_tree().process_frame
	print("[smoke] origins=%d factions=%d districts=%d" % [GameState.origins.size(), GameState.factions.size(), GameState.districts.size()])
	GameState.choose_origin("veteran")
	await get_tree().process_frame
	print("[smoke] phase=%s street=%d" % [GameState.Phase.keys()[GameState.phase], GameState.get_influence("street")])
	GameState.begin_night()
	for i in 90:
		await get_tree().physics_frame
	var guards := get_tree().get_nodes_in_group("guards")
	var player := get_tree().get_first_node_in_group("player") as Player
	print("[smoke] guards=%d player=%s" % [guards.size(), player.global_position if player else "none"])
	await _shots(player)
	for g in guards:
		print("[smoke]   %-16s state=%s suspicion=%.1f pos=%s" % [g.guard_name, Guard.State.keys()[g.state], g.suspicion, g.global_position])
	# Walk in front of a guard: expect suspicion to rise.
	player.global_position = guards[2].global_position + -guards[2].global_transform.basis.z * 4.0
	for i in 120:
		await get_tree().physics_frame
	print("[smoke] after exposure: sentry state=%s suspicion=%.1f alarms=%d" % [Guard.State.keys()[guards[2].state], guards[2].suspicion, GameState.night_alarm_count])
	if GameState.phase == GameState.Phase.NIGHT:
		player.global_position = Vector3(24, 0.5, 24)
		for i in 10:
			await get_tree().physics_frame
	print("[smoke] phase=%s day=%d crackdown=%d underworld=%d" % [GameState.Phase.keys()[GameState.phase], GameState.day, GameState.crackdown, GameState.get_influence("underworld")])
	get_tree().quit()


## With `-- --smoke --shot=/dir`, saves player-view and overhead PNGs (needs a real window, not --headless).
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
	cam.queue_free()
	print("[smoke] screenshots in ", dir)
