extends Node
## `-- --smoke` driver for the campaign (called at the end of mission_smoke.gd run_all). Starts a fresh campaign,
## spends each day (an action, a plant, a lead, the urchins, a nomination), plays each of the seven nights by the
## shortest route in its missions.json `smoke` block, stages one random event a night, tests the failure loop
## (slip away, the cells, breaking out), save/continue mid-campaign, succession (nominated, forced, a coup) and
## three kingpin methods (poison in the arc; knife and riot as replays), and proves that walking straight up to the
## kingpin fails. Prints:
##   [smoke] campaign nights=7 est_minutes=<n>          [smoke] night <n> <id> state=completed
##   [smoke] event <id> outcome=<o>                       [smoke] capture out=<..> checkpoint=<ok> succession heir=<id>
##   [smoke] night 7 kingpin approach=<x> killed=<bool> district=docks claimed=<bool>
##   [smoke] kingpin approach_blocked=<bool> disguise_bodyguard=<ok> isolate=<method>
##   [smoke] succession nominated=<id> forced=<id|none> coup=<bool>
##   [smoke] dialogue tones=<n> personalities=<n> branches_hit=<n>      [smoke] campaign end=<ending>
## With --shot-ui=<dir> (windowed) it saves ui_campaign_*.png of the day panel, the dawn, the nomination and the
## succession card.

const RunnerScript := preload("res://scripts/mission/mission_runner.gd")
const EVENTS_ORDER := ["runaway_cart", "lost_child", "procession", "brawl", "pamphlet_drop", "lamplighter", "duel"]

var ms: Node           ## mission_smoke.gd (its helpers: talk, run_dialogue, tp, frames, wait_nav)
var main: Node
var camp: Node
var shot_dir := ""
var _tones := 0
var _pers := {}
var _branches := 0
var _capture_line := ""
var _results: Array = []


func _ui_dir() -> String:
	if DisplayServer.get_name() == "headless":
		return ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot-ui="):
			return a.trim_prefix("--shot-ui=")
	return ""


func shot(name: String, wait := 0.9) -> void:
	if shot_dir == "":
		return
	await get_tree().create_timer(wait, true, false, true).timeout
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(shot_dir.path_join("ui_campaign_%s.png" % name))
	print("[smoke] ui shot campaign_", name)


func runner() -> Node:
	return Mission.runner


func frames(n: int) -> void:
	for i in n:
		await get_tree().physics_frame


# ------------------------------------------------------------------ preview shots (early, --shot-ui only)

## A campaign in progress for the screenshots: rumours, leads, people, a dawn report, a nomination and a
## succession card. Restores the state afterwards so the mission smoke that follows is unaffected.
func preview_shots(host: Node, smoke: Node) -> void:
	main = host
	ms = smoke
	camp = Mission.campaign
	shot_dir = _ui_dir()
	if shot_dir == "":
		return
	var saved := {"campaign": GameState.campaign.duplicate(true), "journal": Mission.journal.duplicate(true), "day": GameState.day,
			"crackdown": GameState.crackdown, "coins": GameState.coins, "factions": GameState.factions.duplicate(true), "tonight": GameState.tonight_mission}
	camp.new_campaign()
	GameState.day = 3
	var r = camp.rumours
	for id in ["corporal_laundress", "russian_coffee", "deserter_tannery", "black_dog", "hejnal_sign", "kosciuszko_escaped"]:
		r.hear(id, "overheard at the west well")
	camp.plant("raid_kazimierz", "ballad", true)
	camp.find_person("apprentice")
	camp.find_person("marianna")
	(camp.st()["results"] as Array).append({"night": 1, "mission": "printers_bundle", "success": true, "approach": "salon"})
	(camp.st()["results"] as Array).append({"night": 2, "mission": "corporals_ledger", "success": true, "approach": "bribe"})
	camp.st()["night"] = 3
	camp.add_grievance("guilds", 50)
	GameState.add_influence("underworld", 36)
	var lines: Array = ["Taken from the occupier: The watch's book.", "The rota was copied: the Austrians do not know you know their hours."]
	r.night_step(lines)
	lines.append("In the night: You caught a bolting cart-horse by the bridle; the carter Wojtek owes you.")
	camp.st()["dawn"] = lines
	GameState.last_night_success = true
	GameState.last_night_summary = "Private Novak's memory proved short and cheap. Four złoty: the price of a winter's watch.\nBy dawn the boatmen knew every hour the watch would walk until the thaw."
	GameState.night_start_influence = {}
	GameState.set_phase(GameState.Phase.DAWN)
	await shot("dawn", 1.4)
	GameState.set_phase(GameState.Phase.DAY)
	await shot("day", 1.4)
	var sc: Node = main.get("_screen")
	if sc and sc.has_method("show_tab"):
		sc.call("show_tab", "people")
		await shot("nominate", 0.8)
	camp.nominate("apprentice", true)
	camp.fall("shot on the Florian road (a preview)", [], "dead")
	GameState.set_phase(GameState.Phase.DAY)
	await shot("succession", 1.4)
	GameState.campaign = saved["campaign"]
	Mission.journal = saved["journal"]
	GameState.day = saved["day"]
	GameState.crackdown = saved["crackdown"]
	GameState.coins = saved["coins"]
	GameState.factions = saved["factions"]
	GameState.origin_id = "veteran"
	GameState.origin = GameState.origins["veteran"]
	GameState.gender = "m"
	GameState.tonight_mission = saved["tonight"]


# ------------------------------------------------------------------ the arc

func run(host: Node, smoke: Node) -> void:
	main = host
	ms = smoke
	camp = Mission.campaign
	shot_dir = _ui_dir()
	var est: Dictionary = camp.estimate_minutes()
	var parts := PackedStringArray()
	for pn in est["per_night"]:
		parts.append("%s=%.1f" % [pn[0], float(pn[1])])
	print("[smoke] campaign nights=%d est_minutes=%.0f (%s)" % [int(est["nights"]), float(est["total"]), ", ".join(parts)])
	# a fresh campaign for a veteran
	GameState.day = 1
	GameState.crackdown = 10
	GameState.coins = 12
	GameState.origin_id = "veteran"
	GameState.origin = GameState.origins["veteran"]
	GameState.gender = "m"
	GameState.inclination = "unspoken"
	for fid in GameState.factions:
		GameState.factions[fid]["influence"] = int(GameState.origin["influence"].get(fid, 0))
		GameState.factions[fid]["loyalty"] = 50
	Mission.journal = {"storylines": {}, "log": [], "people": {}, "missions": [], "rumours": {}}
	camp.new_campaign()
	for n in range(1, 8):
		GameState.set_phase(GameState.Phase.DAY)
		await frames(2)
		await _day(n)
		var mid: String = GameState.tonight_mission
		var f0 := Engine.get_process_frames()
		GameState.begin_night()
		await frames(3)
		var st := await _night(n, mid)
		print("[smoke] night %d %s state=%s dawn_lines=%d crackdown=%d coins=%d frames=%d" % [n, mid, st, camp.dawn_lines().size(), GameState.crackdown, GameState.coins, Engine.get_process_frames() - f0])
		for l in camp.dawn_lines().slice(0, 4):
			print("[smoke]   dawn: %s" % str(l).left(150))
		if n == 3:
			await _save_continue()
	print("[smoke] campaign end=%s (%s) loyal=%d top=%s district_docks=%s" % [camp.st().get("ended", "none"), camp.ending().get("title", ""),
			camp.loyal_count(60), camp.top_faction(), GameState.districts.get("docks", {}).get("controller", "?")])
	await _kingpin_replays()
	await _succession()
	print(_capture_line)
	var ts: Dictionary = RunnerScript.tone_stats
	print("[smoke] dialogue tones=%d personalities=%d branches_hit=%d" % [int(ts["tones"]), (ts["personalities"] as Dictionary).size(), int(ts["branches"])])
	print("[smoke] whisper rumours_known=%d in_play=%d people_found=%d levers=%d" % [camp.rumours.known().size(), camp.rumours.st().size(),
			(camp.st()["people"] as Dictionary).keys().filter(func(k) -> bool: return camp.found(k)).size(), (camp.st()["levers"] as Dictionary).size()])


func _day(n: int) -> void:
	var notes := PackedStringArray()
	if n >= 4:
		GameState.coins = maxi(GameState.coins, 10)
	match n:
		2:
			camp.rumours.seed_rumour("apprentice_press")
			camp.rumours.hear("apprentice_press", "smoke")
			camp.choose_lead("apprentice")
			notes.append(camp.do_action("tavern").left(60))
			notes.append(camp.plant("raid_kazimierz", "ballad").left(60))
		3:
			notes.append(camp.urchin_buy("rumour").left(60))
			notes.append(camp.do_action("nominate:apprentice").left(60))
			camp.choose_lead("deserter")
		4:
			notes.append(camp.do_action("stage_miracle").left(60))
			notes.append(camp.do_action("rest").left(60))
		5:
			camp.rumours.seed_rumour("banker_little_market")
			camp.rumours.hear("banker_little_market", "smoke")
			camp.choose_lead("banker")
			notes.append(camp.do_action("alms").left(60))
		6:
			notes.append(camp.plant("raid_warehouse", "madam").left(60))
		7:
			notes.append(camp.do_action("sell_favours").left(60))
	if camp.trial_pending():
		notes.append(camp.do_trial("flogging").left(50))
	if not camp.coup().is_empty():
		notes.append(camp.resolve_coup("concede").left(50))
	if not camp.card().is_empty():
		camp.dismiss_card()
	var dn: String = str(camp.night())
	print("[smoke] day %d (arc night %s) tonight=%s actions_left=%d rumours_known=%d leads=%d relations=%d | %s" % [GameState.day, dn, GameState.tonight_mission,
			camp.actions_left(), camp.rumours.known().size(), camp.leads().size(), camp.relation_lines().size(), " / ".join(notes)])


func _collect_stats() -> void:
	var r := runner()
	if r == null:
		return
	_tones += int(r.stats["tones"])
	_branches += int(r.stats["branches"])
	for k in r.stats["personalities"]:
		_pers[k] = true


func _night(n: int, mid: String) -> String:
	var box := {"s": "active"}
	var done := func(_s: String) -> void: box["s"] = "completed"
	var failed := func(_r: String) -> void: box["s"] = "failed"
	Mission.completed.connect(done)
	Mission.failed.connect(failed)
	GameState.clock_minutes = GameState.parse_clock("21:15")
	var r := runner()
	if r == null or ms.player() == null:
		Mission.completed.disconnect(done)
		Mission.failed.disconnect(failed)
		return "no-runner"
	# the whisper network: one injected rumour overheard through intel.gd's pipeline
	var intel: Node = r._intel()
	if intel:
		for hid in intel.hints:
			if str(hid).begins_with("rumour_"):
				var sp: Node3D = null
				for s in intel.hints[hid].get("speakers", []):
					if r.actor(str(s)):
						sp = r.actor(str(s))
						break
				if sp and intel.record_hint(hid, sp):
					await frames(30)
					print("[smoke]   whisper overheard=%s heard=%s" % [hid, camp.rumours.heard(str(hid).trim_prefix("rumour_"))])
					break
	await _event(n)
	if n == 2 and r.actor("apprentice"):
		await ms.talk("apprentice")
		await ms.run_dialogue([])
		print("[smoke]   lead found apprentice=%s levers=%s" % [camp.found("apprentice"), (camp.st()["levers"] as Dictionary).keys()])
	for who in ["deserter", "banker"]:
		if r.actor(who) and not camp.found(who):
			await ms.talk(who)
			await ms.run_dialogue([])
			print("[smoke]   lead found %s=%s" % [who, camp.found(who)])
	if n == 3:
		await _capture_test()
	if mid == "printers_bundle":
		print(await ms.run_approach("underworld"))
	else:
		await _steps(Mission.data.get("smoke", {}).get("steps", []), n)
	for i in 60:
		if box["s"] != "active":
			break
		await get_tree().physics_frame
	var state: String = box["s"]
	_collect_stats()
	if n == 7:
		print("[smoke] night 7 kingpin approach=%s killed=%s district=docks claimed=%s" % [Mission.approach, Mission.has_flag("killed"),
				GameState.districts.get("docks", {}).get("controller", "") == "movement"])
	if state == "active":
		print("[smoke]   night %d stuck: objectives=%s" % [n, Mission.objectives.map(func(o) -> String: return "%s:%s" % [o["id"], o["done"]])])
		Mission.fail("smoke: unfinished")
		state = "failed"
	Mission.completed.disconnect(done)
	Mission.failed.disconnect(failed)
	if n == 3 and shot_dir != "":
		await shot("dawn_n3", 1.4)
	return state


func _steps(steps: Array, _n: int) -> void:
	var r := runner()
	for s in steps:
		if not Mission.is_active():
			break
		if s.has("coins"):
			GameState.coins = maxi(GameState.coins, int(s["coins"]))
		elif s.has("loyalty"):
			for f in s["loyalty"]:
				GameState.factions[f]["loyalty"] = maxi(GameState.get_loyalty(f), int(s["loyalty"][f]))
		elif s.has("talk"):
			var ok: bool = await ms.talk(str(s["talk"]))
			var seen: PackedStringArray = await ms.run_dialogue(s.get("picks", []))
			print("[smoke]   talk %s=%s nodes=%s" % [s["talk"], ok, ",".join(seen)])
		elif s.has("use"):
			await _use(str(s["use"]), s.get("picks", []))
		elif s.has("enter"):
			var ok2: bool = r.interiors != null and r.interiors.enter_now(ms.player(), str(s["enter"]))
			await frames(6)
			print("[smoke]   enter %s=%s" % [s["enter"], ok2])
		elif s.has("out"):
			if r.interiors and r.interiors.has_method("_go_out_now"):
				r.interiors.call("_go_out_now", ms.player())
			await frames(6)
		elif s.has("reach"):
			var p: Array = s["reach"]
			await ms.tp(Vector3(float(p[0]), float(p[1]), float(p[2])), Vector3(float(p[0]), 0, float(p[2]) - 2.0), 12)
		elif s.has("kingpin_at"):
			var k: Node3D = r.kingpin()
			var stn: Array = Mission.data.get("kingpin", {}).get("stations", {}).get(str(s["kingpin_at"]), [0, 0])
			if k:
				k.relocate(Vector3(float(stn[0]), 0.05, float(stn[1])), 0.0)
				r.on_story_event("wilk_round", "at_" + str(s["kingpin_at"]), k)
			await frames(4)


func _use(id: String, picks: Array) -> void:
	var r := runner()
	var it: Dictionary = r.items.get(id, {})
	if it.is_empty():
		print("[smoke]   use %s: no such item" % id)
		return
	var at: Vector3 = (it["node"] as Node3D).global_position
	var p: Player = ms.player()
	var ok := false
	for off in [Vector3(0, 0, 1.1), Vector3(1.1, 0, 0), Vector3(0, 0, -1.1), Vector3(-1.1, 0, 0)]:
		await ms.tp(at + off, at + Vector3(0, 0.6, 0), 2)
		if p.interact_target and p.interact_target.get_parent() == it["node"] and p.try_interact():
			ok = true
			break
	await frames(2)
	if r.dialogue_open():
		await ms.run_dialogue(picks)
	r.finish_work()
	await frames(4)
	print("[smoke]   use %s=%s" % [id, ok])


func _event(n: int) -> void:
	var r := runner()
	if r == null or r.events == null:
		return
	var eid: String = EVENTS_ORDER[(n - 1) % EVENTS_ORDER.size()]
	var p: Player = ms.player()
	var anchor := p.global_position + Vector3(14, 0, 0)
	anchor.y = 0.0
	if not r.events.stage(eid, anchor):
		print("[smoke] event %s outcome=unstaged" % eid)
		return
	var key := str(r.events.active.get("key", ""))
	await frames(4)
	await ms.talk(key)
	await ms.run_dialogue([])
	var first := ""
	# take the first offered choice (run_dialogue falls back to leave); report what resolved
	print("[smoke] event %s outcome=%s%s" % [eid, r.events.last_outcome if Mission.has_flag("ev_%s_done" % eid) else "none", first])
	r.events.clear()


func _capture_test() -> void:
	var r := runner()
	RunnerScript.capture_in_smoke = true
	var p: Player = ms.player()
	var start := p.global_position
	await ms.tp(start + Vector3(3, 0, 3), start, 2)
	r.save_checkpoint("smoke checkpoint")
	await ms.tp(start + Vector3(-20, 0, 10), start, 2)
	Mission.fail("Caught by the watch: smoke")
	await frames(3)
	await ms.run_dialogue(["slip"])
	var cp_ok: bool = Mission.is_active() and p.global_position.distance_to(start + Vector3(3, 0, 3)) < 1.5
	await frames(3)
	Mission.fail("Caught by the watch: smoke again")
	await frames(3)
	var slip_greyed: bool = r.choice_index("slip") >= 0
	await ms.run_dialogue(["cells", "cell:wait"])
	await frames(4)
	await ms.run_dialogue(["cell:wait"])
	# the turnkey dozes and turns away every 5 s: try the window when he faces the wall
	var out := "none"
	for i in 12:
		r._turn_t = 5.5
		await frames(2)
		await _use("cell_window", [])
		if Mission.has_flag("capture_out_breakout"):
			out = "breakout"
			break
	RunnerScript.capture_in_smoke = false
	var heir: String = camp.nominee()
	_capture_line = "[smoke] capture out=%s checkpoint=%s slip_greyed_second=%s active=%s succession heir=%s" % [out, "ok" if cp_ok else "FAIL",
			slip_greyed, Mission.is_active(), heir if heir != "" else "none"]
	print(_capture_line)
	GameState.clock_minutes = GameState.parse_clock("21:30")


func _save_continue() -> void:
	var n: int = camp.night()
	var known: int = camp.rumours.known().size()
	var found := (camp.st()["people"] as Dictionary).size()
	GameState.save_game()
	camp.st()["night"] = 1
	Mission.journal["rumours"] = {}
	var ok := GameState.continue_game()
	await frames(3)
	var sd: Variant = JSON.parse_string(FileAccess.get_file_as_string(GameState.SAVE_PATH))
	print("[smoke] save roundtrip journal=%d flags=%d notoriety=%d version=%d" % [(Mission.journal as Dictionary).size(), (Mission.flags as Dictionary).size(),
			int(GameState.notoriety()), int(sd.get("version", 0)) if sd is Dictionary else -1])
	print("[smoke] save/continue ok=%s night=%d/%d rumours=%d/%d people=%d/%d" % [ok, camp.night(), n, camp.rumours.known().size(), known,
			(camp.st()["people"] as Dictionary).size(), found])


# ------------------------------------------------------------------ kingpin replays

func _kingpin_replays() -> void:
	# knife, through a bodyguard's coat taken at the privy
	GameState.begin_night()
	await frames(3)
	var r := runner()
	GameState.clock_minutes = GameState.parse_clock("22:16")
	await frames(20)
	var bg: Node3D = null
	print("[smoke]   kingpin replay bodyguards=%d wilk=%s mission=%s" % [r.bodyguards().size(), r.kingpin() != null, Mission.mission_id])
	for g in r.bodyguards():
		if g.guard_name == "Wilk's bodyguard 2":
			bg = g
	var p: Player = ms.player()
	var coat := false
	if bg:
		var back: Vector3 = bg.global_transform.basis.z
		back.y = 0.0
		await ms.tp(bg.global_position + back.normalized() * 1.1, bg.global_position, 2)
		var res: String = p.attack()
		await frames(5)
		coat = Mission.has_flag("disguise_bodyguard")
		print("[smoke]   kingpin privy takedown=%s coat=%s" % [res, coat])
	var k: Node3D = r.kingpin()
	if k:
		var kb: Vector3 = k.global_transform.basis.z
		kb.y = 0.0
		for tries in 4:
			await frames(50)
			if not is_instance_valid(k) or not k.is_inside_tree():
				break          # the night can end (or the kingpin die) while we wait
			kb = k.global_transform.basis.z
			kb.y = 0.0
			await ms.tp(k.global_position + kb.normalized() * 1.0, k.global_position, 2)
			var res2: String = p.attack()
			await frames(6)
			if Mission.has_flag("killed_knife"):
				break
			print("[smoke]   kingpin knife try %d: %s" % [tries, res2])
	print("[smoke] kingpin method=knife killed=%s blocked=%s" % [Mission.has_flag("killed_knife"), Mission.has_flag("approach_blocked")])
	var knife_coat := coat
	if Mission.is_active():
		Mission.fail("smoke: replay over")
	await frames(3)
	# riot: the raftsmen rise and the mob drags him out
	GameState.begin_night()
	await frames(3)
	r = runner()
	GameState.factions["street"]["loyalty"] = maxi(GameState.get_loyalty("street"), 50)
	await ms.talk("bartek7")
	await ms.run_dialogue(["incite"])
	r._mob_t = 100.0
	await frames(4)
	await ms.talk("bartek7")
	await ms.run_dialogue(["ice"])
	print("[smoke] kingpin method=riot killed=%s mob=%s" % [Mission.has_flag("killed_riot"), Mission.has_flag("mob_has_target")])
	if Mission.is_active():
		Mission.fail("smoke: replay over")
	await frames(3)
	# walking straight up to him fails
	GameState.begin_night()
	await frames(3)
	r = runner()
	await frames(10)
	k = r.kingpin()
	var blocked := false
	if k:
		var kf: Vector3 = -k.global_transform.basis.z
		kf.y = 0.0
		await ms.tp(k.global_position + kf.normalized() * 1.6, k.global_position, 3)
		await frames(40)
		blocked = Mission.has_flag("approach_blocked")
	print("[smoke] kingpin approach_blocked=%s disguise_bodyguard=%s isolate=privy" % [blocked, "ok" if knife_coat else "FAIL"])
	if Mission.is_active():
		Mission.fail("smoke: replay over")
	await frames(3)


func _succession() -> void:
	var nominated: String = camp.nominee()
	if nominated == "" and not camp.heirs().is_empty():
		camp.nominate(camp.heirs()[0], true)
		nominated = camp.nominee()
	var lines: Array = []
	camp.fall("a smoke test", lines, "dead")
	var heir: String = str(camp.st().get("heir", ""))
	camp.dismiss_card()
	camp.st()["nominee"] = ""
	lines = []
	camp.fall("a second smoke test", lines, "taken")
	var forced: String = str(camp.st().get("heir", ""))
	camp.dismiss_card()
	camp.st()["coup"] = {"faction": camp.strongest_faction(), "why": "smoke"}
	var cr: String = camp.resolve_coup("yield")
	print("[smoke] succession nominated=%s heir=%s forced=%s coup=%s leader=%s | %s" % [nominated if nominated != "" else "none", heir, forced if forced != heir else "none",
			cr != "", camp.st().get("leader", "?"), cr.left(90)])
