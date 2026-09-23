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
	player.add_child(District.avoidance_obstacle(0.45))
	var hud := CanvasLayer.new()
	hud.set_script(Hud)
	_ui_layer.add_child(hud)


func _on_mission_ended(_success: bool, summary: String) -> void:
	_pending_summary = summary


## Headless smoke test: `godot --headless --path . --quit-after 600 -- --smoke`
func _smoke() -> void:
	await get_tree().process_frame
	print("[smoke] origins=%d factions=%d districts=%d" % [GameState.origins.size(), GameState.factions.size(), GameState.districts.size()])
	GameState.choose_origin("veteran", "f" if "--woman" in OS.get_cmdline_user_args() else "m")
	await get_tree().process_frame
	print("[smoke] phase=%s street=%d" % [GameState.Phase.keys()[GameState.phase], GameState.get_influence("street")])
	GameState.begin_night()
	for i in 90:
		await get_tree().physics_frame
	var guards := get_tree().get_nodes_in_group("guards")
	var player := get_tree().get_first_node_in_group("player") as Player
	print("[smoke] guards=%d player=%s" % [guards.size(), player.global_position if player else "none"])
	print("[smoke] npcs=%d animals=%d" % [get_tree().get_nodes_in_group("npcs").size(), get_tree().get_nodes_in_group("animals").size()])
	await _smoke_schedules(player)
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
	if GameState.phase == GameState.Phase.NIGHT:
		var sh := _world.get_node_or_null("SafeHouse") as Node3D
		player.global_position = (sh.global_position if sh else Vector3(26, 0, 25)) + Vector3(0, 0.5, 0)
		for i in 10:
			await get_tree().physics_frame
	print("[smoke] phase=%s day=%d crackdown=%d underworld=%d" % [GameState.Phase.keys()[GameState.phase], GameState.day, GameState.crackdown, GameState.get_influence("underworld")])
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
