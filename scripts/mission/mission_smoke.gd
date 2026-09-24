extends Node
## `-- --smoke` driver for the mission (called from main.gd _smoke()). Plays "The Printer's Bundle" three times,
## each on a fresh night (GameState.begin_night rebuilds the world and restarts the mission):
## underworld (smuggler), street (urchins), salon (hostess and cloak), planting the decoy on the informer each
## time; then a combat check (rear takedown, fair fight) and a failure. With `--shot=/dir` (windowed) it saves
## shot_dialogue.png, shot_dialogue_choices.png and shot_objectives.png.

var main: Node
var shot_dir := ""
var _state := "active"


func run_all(host: Node) -> void:
	main = host
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			shot_dir = a.trim_prefix("--shot=")
	if DisplayServer.get_name() == "headless":
		shot_dir = ""
	Mission.completed.connect(func(_s: String) -> void: _state = "completed")
	Mission.failed.connect(func(_r: String) -> void: _state = "failed")
	var cs: Node = preload("res://scripts/mission/campaign_smoke.gd").new()
	add_child(cs)
	await cs.preview_shots(main, self)
	for approach in ["underworld", "street", "salon"]:
		GameState.begin_night()
		print(await run_approach(approach))
	print("[smoke] mission objectives=%d/%d state=%s summary=%s" % [Mission.done_count(), Mission.objectives.size(), _state,
			Mission.summary.replace("\n", " | ")])
	GameState.begin_night()
	print(await run_combat())
	print("[smoke]   mission smoke done at frame %d" % Engine.get_process_frames())
	# the campaign: seven nights, the day phases, events, the failure loop, succession (campaign_smoke.gd)
	await cs.run(main, self)
	print("[smoke]   campaign smoke done at frame %d" % Engine.get_process_frames())


# ------------------------------------------------------------------ helpers

func frames(n: int) -> void:
	for i in n:
		await get_tree().physics_frame


func world() -> Node3D:
	return main.get("_world")


func runner() -> Node:
	return Mission.runner


func player() -> Player:
	return runner().player() if runner() else null


func wait_nav() -> void:
	await frames(3)
	for i in 400:
		if world() and world().nav_ready():
			break
		await get_tree().physics_frame


func tp(pos: Vector3, look: Vector3, settle: int = 3) -> void:
	var p := player()
	p.global_position = Vector3(pos.x, pos.y + 0.1, pos.z)
	p.velocity = Vector3.ZERO
	p.face_point(look)
	p.reset_physics_interpolation()
	await frames(settle)


## Stand `dist` m in front of (or behind) an NPC, facing them, and press interact.
func talk(id: String, behind := false, dist := 1.3) -> bool:
	var npc: Node3D = runner().actor(id)
	if npc == null:
		return false
	for attempt in 6:
		if not is_instance_valid(npc) or not npc.is_inside_tree():
			return false                      # carried off or freed mid-approach (events: corpse_carried)
		var fwd: Vector3 = -npc.global_transform.basis.z
		fwd.y = 0.0
		fwd = fwd.normalized()
		await tp(npc.global_position + fwd * dist * (-1.0 if behind else 1.0), npc.global_position, 1)
		var p := player()
		if p.interact_target and p.interact_target.get_parent() == npc and p.try_interact():
			return true
	return false


## Advance through the open conversation, taking the first offered choice whose action or next node is listed.
func run_dialogue(picks: Array, shot_line := "", shot_choices := "") -> PackedStringArray:
	var d: CanvasLayer = runner().dialogue
	var seen := PackedStringArray()
	var shot_done := false
	var choice_shot_done := false
	for step in 80:
		if not is_instance_valid(d) or not d.is_open:
			break
		var node := str(d.get_meta("node", ""))
		if seen.is_empty() or seen[-1] != node:
			seen.append(node)
		if shot_line != "" and not shot_done:
			shot_done = true
			await frames(25)        # let the camera settle over the shoulder
			await shot(shot_line)
		if d.is_choosing():
			if shot_choices != "" and not choice_shot_done:
				choice_shot_done = true
				await shot(shot_choices)
			var idx := -1
			for pk in picks:
				idx = runner().choice_index(str(pk))
				if idx >= 0:
					break
			if idx < 0:
				idx = maxi(runner().choice_index("leave"), 0)
			d.choose(idx)
		else:
			d.advance()
		await frames(2)
	while Mission.dialogue_blocking():          # the closing key press is swallowed for a moment
		await get_tree().process_frame
	return seen


func shot(name: String) -> void:
	if shot_dir == "":
		return
	for i in 4:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var path := shot_dir.path_join(name + ".png")
	get_viewport().get_texture().get_image().save_png(path)
	print("[smoke] mission screenshot ", path)


func plant_decoy() -> bool:
	var ok := await talk("informer", true, 1.2)
	return ok and Mission.has_flag("decoy_planted")


func take_stash() -> bool:
	var s: Node3D = runner().stash
	await tp(s.global_position + Vector3(-0.7, 0, 1.2), s.global_position + Vector3(0, 0.3, 0))
	var p := player()
	var ok := p.try_interact() and p.carrying
	if not ok:
		print("[smoke]   stash: target=%s prompt=%s pos=%s frame=%d" % [p.interact_target, p.prompt_text, p.global_position, Engine.get_process_frames()])
	return ok


func deliver() -> bool:
	for i in 240:
		if runner().get("_hostess_inside") or not player().carrying:
			break
		await get_tree().physics_frame
	var ok := await talk("hostess", false, 1.3)
	if ok:
		await run_dialogue(["deliver"])
	await frames(3)
	return ok


func _line(approach: String, notes: PackedStringArray) -> String:
	var total := Mission.objectives.size()
	return "[smoke] approach=%s objectives=%d/%d state=%s phase=%s coins=%d %s\n[smoke]   summary=%s" % [approach,
			Mission.done_count(), total, _state, GameState.Phase.keys()[GameState.phase], GameState.coins, " ".join(notes),
			Mission.summary.replace("\n", " | ")]


# ------------------------------------------------------------------ approaches

func run_approach(approach: String) -> String:
	_state = "active"
	await wait_nav()
	var notes := PackedStringArray()
	if runner() == null or player() == null:
		return "[smoke] approach=%s FAILED: no mission runner" % approach
	GameState.clock_minutes = GameState.parse_clock("21:15")
	if shot_dir != "" and approach == "underworld":
		await get_tree().create_timer(1.5).timeout      # let the night's fade-in finish before the screenshots
	print("[smoke]   %s night starts at frame %d" % [approach, Engine.get_process_frames()])
	notes.append("decoy=%s" % await plant_decoy())
	match approach:
		"underworld":
			notes.append("talk=%s" % await talk("smuggler"))
			notes.append("nodes=%s" % ",".join(await run_dialogue(["meet_smuggler"], "shot_dialogue", "shot_dialogue_choices")))
			notes.append("stash=%s" % await take_stash())
			if shot_dir != "":
				await tp(Vector3(3.2, 0, 10.5), Vector3(0.5, 0, 2.0), 20)     # out on the square, bundle in arms
				await shot("shot_objectives")
		"street":
			notes.append("talk=%s" % await talk("urchin_a"))
			notes.append("nodes=%s" % ",".join(await run_dialogue(["pay"])))
			await tp(Vector3(-40, 0.4, -40), Vector3(-30, 0, -30))      # out of sight while the urchin runs
			# Fast-forward while the urchin runs (fewer main-loop iterations for --quit-after).
			var t0 := GameState.clock_minutes
			Engine.time_scale = 4.0
			var n := 0
			while not Mission.has_flag("bundle_at_well") and n < 900 and Mission.is_active():
				await get_tree().process_frame
				n += 1
			Engine.time_scale = 1.0
			notes.append("urchin_at_well=%s after %.0f game-min" % [Mission.has_flag("bundle_at_well"), GameState.clock_minutes - t0])
			notes.append("collect=%s" % await talk("urchin_a"))
			notes.append("nodes=%s" % ",".join(await run_dialogue(["collect_bundle"])))
			notes.append("carrying=%s" % player().carrying)
		"salon":
			notes.append("talk=%s" % await talk("hostess"))
			notes.append("nodes=%s" % ",".join(await run_dialogue(["persuade", "hostess_persuade"])))
			notes.append("disguised=%s" % player().disguised)
			notes.append("stash=%s" % await take_stash())
			# In by the front door, past the Town Hall sentry, who should see only a guest.
			var door := Vector3(-16.0, 0, 17.4)
			await tp(door, door + Vector3(0, 0, -2), 45)
			var sentry_s := 0.0
			for g in get_tree().get_nodes_in_group("guards"):
				if g.guard_name == "Town Hall sentry" and world().is_ancestor_of(g):
					sentry_s = g.suspicion
			notes.append("sentry_suspicion=%.1f" % sentry_s)
			var interiors := world().get_node_or_null("Interiors")
			notes.append("door=%s" % (interiors != null and interiors.enter_now(player(), "door_town_hall")))
			await frames(5)
	if Mission.is_active():
		notes.append("deliver=%s" % await deliver())
	return _line(approach, notes)


func run_combat() -> String:
	_state = "active"
	await wait_nav()
	var sentry: Guard = null
	var patrol: Guard = null
	for g in get_tree().get_nodes_in_group("guards"):
		if not world().is_ancestor_of(g):
			continue
		if g.guard_name == "Cloth Hall sentry":
			sentry = g
		elif g.guard_name == "Rynek patrol A":
			patrol = g
	var p := player()
	# Rear takedown: step up behind the sentry.
	var back := sentry.global_transform.basis.z
	back.y = 0.0
	await tp(sentry.global_position + back.normalized() * 1.1, sentry.global_position, 2)
	var r1 := p.attack()
	var takedown := "ok" if r1 == "takedown" and sentry.is_downed() and GameState.night_alarm_count == 0 else "FAIL(%s)" % r1
	await frames(70)
	# Fair fight: face patrol A at arm's length and swing whenever the cudgel is ready.
	var crack0 := GameState.crackdown
	var fwd := -patrol.global_transform.basis.z
	fwd.y = 0.0
	await tp(patrol.global_position + fwd.normalized() * 1.2, patrol.global_position + Vector3(0, 1, 0), 1)
	var melee := "undecided"
	var swings := 0
	for i in 600:
		if patrol.is_downed():
			melee = "guard downed"
			break
		if _state == "failed" or p.health <= 0:
			melee = "player beaten"
			break
		p.face_point(patrol.global_position)
		if p.attack() != "":
			swings += 1
		await get_tree().physics_frame
	var line := "[smoke] combat takedown=%s melee=%s swings=%d player_health=%d crackdown %d->%d alarms=%d" % [takedown, melee,
			swings, p.health, crack0, GameState.crackdown, GameState.night_alarm_count]
	if Mission.is_active():
		Mission.fail("Caught by the watch: Rynek patrol B")
	await frames(3)
	return line + "\n[smoke] failure state=%s phase=%s summary=%s" % [_state, GameState.Phase.keys()[GameState.phase],
			Mission.summary.replace("\n", " | ")]
