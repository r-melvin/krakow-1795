extends "res://scripts/stealth/stealth_smoke.gd"
## `-- --smoke` checks for the kit, close combat, throwables, pickups, traversal and the first-person close actions
## (kit.gd, player.gd, distraction.gd, pickup.gd, traversal.gd, fp_view.gd). Started by the player (player.gd) beside
## the stealth and intel smoke; every check runs in its own sandbox world (stealth_smoke.gd's helpers). Prints a line
## per check and
##   [smoke] kit knife=ok parry=ok pistol=ok smoke=ok flash=ok throw_coin=ok pickup=ok vault=ok mantle=ok hang=ok
##           climb=ok drop_roll=ok
##   [smoke] kit poison=ok torch=ok rig_drop=ok cosh=ok
##   [smoke] kit held=<items> inventory=ok wheel=ok blood splats=<n>
##   [smoke] camera keyhole=ok listen=ok lockpick=<ok|fail> qte=ok
## `--kit-shot=/dir` (windowed): kit_parry_side, kit_smoke_cloud, kit_flash, kit_vault_midair, kit_hang_sill,
## kit_roof_view, kit_keyhole.

const NpcScript := preload("res://scripts/npc/npc.gd")
const PickupScript := preload("res://scripts/stealth/pickup.gd")
const FpViewScript := preload("res://scripts/stealth/fp_view.gd")
const TraversalScript := preload("res://scripts/stealth/traversal.gd")
const VerbsScript := preload("res://scripts/stealth/verbs.gd")
const InventoryScript := preload("res://scripts/ui/inventory.gd")
const WheelScript := preload("res://scripts/ui/weapon_wheel.gd")
const BloodScript := preload("res://scripts/stealth/blood.gd")

var K: Dictionary = {}


func _ready() -> void:
	shot_dir = ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--kit-shot="):
			shot_dir = a.trim_prefix("--kit-shot=")
	if DisplayServer.get_name() == "headless":
		shot_dir = ""
	_run_kit()


func _ok(key: String) -> String:
	return "ok" if K.get(key, false) else "fail"


func _run_kit() -> void:
	await get_tree().process_frame
	print("[smoke] kit sandbox tests start at frame %d" % Engine.get_process_frames())
	if "--grip-shot" in OS.get_cmdline_user_args() and shot_dir != "":
		DirAccess.make_dir_recursive_absolute(shot_dir)
		print(await t_grip_shots(60))
		get_tree().quit()
		return
	var tests: Array[Callable] = [t_knife, t_parry, t_pistol, t_smoke, t_flash, t_coin, t_pickup, t_traversal, t_camera, t_finale, t_hold_ui]
	if shot_dir != "":
		DirAccess.make_dir_recursive_absolute(shot_dir)
		tests.append(t_kit_shots)
	_pending = tests.size()
	for i in tests.size():
		_launch(tests[i], 40 + i)
	while _pending > 0:
		await get_tree().process_frame
	var keys := ["knife", "parry", "pistol", "smoke", "flash", "throw_coin", "pickup", "vault", "mantle", "hang", "climb", "drop_roll"]
	var parts := PackedStringArray()
	for k in keys:
		parts.append("%s=%s" % [k, _ok(k)])
	print("[smoke] kit " + " ".join(parts))
	print("[smoke] kit held=%s inventory=%s wheel=%s blood splats=%d" % [K.get("held", "-"), _ok("inventory"), _ok("wheel"), int(K.get("splats", 0))])
	print("[smoke] kit poison=%s torch=%s rig_drop=%s cosh=%s" % [_ok("poison"), _ok("torch"), _ok("rig_drop"), _ok("cosh")])
	print("[smoke] camera keyhole=%s listen=%s lockpick=%s qte=%s" % [_ok("keyhole"), _ok("listen"), _ok("lockpick"), _ok("qte")])
	print("[smoke] kit done at frame %d" % Engine.get_process_frames())
	if "--kit-only" in OS.get_cmdline_user_args():
		get_tree().quit()


func _free(w: Dictionary) -> void:
	(w["vp"] as Node).queue_free()


# ------------------------------------------------------------------ combat

func t_knife(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	var g := guard(w, "Knife victim", [Vector3(0, 0, 0)], 0.0)      # faces -Z
	var g2 := guard(w, "Knife foe", [Vector3(10, 0, 0)], 0.0)
	await wait_s(0.2)
	p.kit.select("knife")
	p.kit.lethal = true
	tp(w, Vector3(0, 0, 1.0), Vector3(0, 1, 0))
	await wait_s(0.05)
	var r1 := p.attack()
	var clip1 := Assets.action_clip(p._figure)
	var kill: bool = r1 == "takedown" and g.dead and g.is_downed() and p.kit.last_takedown == "lethal"
	await wait_s(1.6)
	# fair fight: a slash at a guard who faces you (1 damage, 0.35 s)
	p.kit.lethal = false
	tp(w, Vector3(10, 0, -1.1), Vector3(10, 1, 0))
	await wait_s(0.05)
	var h0: int = g2.health
	var r2 := p.attack()
	await wait_s(0.4)
	var r3 := p.attack()
	var slash: bool = r2 == "hit" and h0 - g2.health >= 1 and (r3 == "hit" or r3 == "takedown" or g2.is_downed())
	K["knife"] = kill and slash
	_free(w)
	return "[smoke] kit knife lethal_takedown=%s clip=%s dead=%s slash=%s,%s guard_health %d->%d %s" % [r1, clip1, g.dead, r2, r3,
			h0, g2.health, "OK" if K["knife"] else "FAIL"]


func t_parry(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	var g := guard(w, "Parry foe", [Vector3(0, 0, 0)], PI)            # faces +Z, toward the player
	await wait_s(0.2)
	p.kit.select("knife")
	tp(w, Vector3(0, 0, 1.45), Vector3(0, 1, 0))
	g.suspicion = 100.0
	g.state = Guard.State.ALARM
	g.last_known = p.global_position
	var parried := false
	var t := 0.0
	while t < 8.0:
		t += await step()
		p.face_point(g.global_position)
		if g._swing_cd < 0.12 and g.stagger_left <= 0.0 and g.state == Guard.State.ALARM:
			p.start_parry()
		if p.parries > 0:
			parried = true
			break
	var staggered: bool = g.is_staggered()
	var hp: int = p.health
	await wait_s(0.1)
	var r := p.attack()
	K["parry"] = parried and staggered and hp == 3 and r == "takedown" and p.kit.last_takedown == "thrust"
	_free(w)
	return "[smoke] combat parry parried=%s after %.1fs staggered=%s player_health=%d thrust=%s(%s) %s" % [parried, t, staggered, hp, r,
			p.kit.last_takedown, "OK" if K["parry"] else "FAIL"]


func t_pistol(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	var wt: Node = w["watch"]
	var a := guard(w, "Pistol target", [Vector3(0, 0, 22)], 0.0)
	var b := guard(w, "Far patrol", [Vector3(-30, 0, -20)], 0.0)
	var heard := []
	wt.sound_event.connect(func(_pos: Vector3, loud: float, kind: String) -> void: heard.append([kind, loud]))
	await wait_s(0.2)
	p.kit.add("pistol")
	p.kit.select("pistol")
	tp(w, Vector3(0, 0, 30))
	var d := a.global_position - p.global_position
	p.rotate_camera(Vector3(-0.04, atan2(-d.x, -d.z), 0))
	await wait_s(0.1)
	var r1 := p.fire_pistol()
	var r2 := p.fire_pistol()
	await wait_s(0.5)
	var loud := false
	for h in heard:
		if h[0] == "pistol" and float(h[1]) >= 1.0:
			loud = true
	var converged: bool = b.state >= Guard.State.SEARCHING or b.task.get("kind", "") == "search"
	K["pistol"] = r1 == "hit" and a.dead and loud and converged and r2 == "reload" and absf(p.kit.reload_left - 20.0) < 1.0
	_free(w)
	return "[smoke] kit pistol shot=%s dead=%s loud=%s far_guard=%s(%.0f) again=%s reload_left=%.1f %s" % [r1, a.dead, loud,
			Guard.State.keys()[b.state], b.suspicion, r2, p.kit.reload_left, "OK" if K["pistol"] else "FAIL"]


func t_smoke(idx: int) -> String:
	var w := make_world(idx, {"sweep.sentry_amplitude_deg": 0.0, "sweep.amplitude_deg": 0.0})
	var p: Player = w["player"]
	lantern(w, Vector3(-1.5, 0, 0), false)
	var g := guard(w, "Smoke watcher", [Vector3(0, 0, -7)], 0.0)
	g.rotation.y = PI
	tp(w, Vector3(0, 0, 0), Vector3(0, 1, -7))
	await wait_s(0.5)
	var saw_before: bool = g.sees_player
	var n0: int = p.kit.count("smoke")
	var st: Node3D = p.throw_at(L(w, Vector3(0, 0, -0.5)), "smoke", true)
	await wait_until(func() -> bool: return st.landed, 3.0)
	await wait_s(0.4)
	var blind_frames := 0
	var frames := 0
	var vis_max := 0.0
	var t := 0.0
	while t < 1.0:
		t += await step()
		frames += 1
		if not g.sees_player:
			blind_frames += 1
		vis_max = maxf(vis_max, p.visibility)
	K["smoke"] = saw_before and st.effect != null and blind_frames == frames and vis_max <= 0.1001 and p.kit.count("smoke") == n0 - 1
	_free(w)
	return "[smoke] kit smoke saw_before=%s cloud=%s guard_blind=%d/%d player_vis<=%.2f charges %d->%d %s" % [saw_before, st.effect != null,
			blind_frames, frames, vis_max, n0, p.kit.count("smoke"), "OK" if K["smoke"] else "FAIL"]


func t_flash(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	var g := guard(w, "Flash victim", [Vector3(0, 0, -3)], PI)       # faces the landing point
	var g2 := guard(w, "Behind", [Vector3(0, 0, -9)], 0.0)            # 6 m off, facing away
	await wait_s(0.2)
	tp(w, Vector3(0, 0, 6), Vector3(0, 1, 0))
	var st: Node3D = p.throw_at(L(w, Vector3(0, 0, 0)), "flash", true)
	await wait_until(func() -> bool: return st.landed, 3.0)
	await wait_s(0.5)
	var blind: bool = g.is_staggered() and g.last_score == 0.0 and not g.sees_player
	var spared: bool = not g2.is_staggered()
	await wait_s(4.0)
	var recovered: bool = not g.is_staggered()
	K["flash"] = blind and spared and recovered
	_free(w)
	return "[smoke] kit flash blinded=%s other_spared=%s recovered_after_4s=%s %s" % [blind, spared, recovered, "OK" if K["flash"] else "FAIL"]


func t_coin(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	var root: Node3D = w["root"]
	var npc := NpcScript.new()
	npc.npc_id = "kit_smoke_walker"
	npc.candidates = PackedStringArray(["npc_m_03", "npc_m_01"])
	npc.behaviour = "stand"
	npc.position = Vector3(3, 0, 0)
	root.add_child(npc)
	var wt: Node = w["watch"]
	var heard := []
	wt.sound_event.connect(func(_pos: Vector3, _l: float, kind: String) -> void: heard.append(kind))
	await wait_s(0.3)
	tp(w, Vector3(0, 0, 6), Vector3(0, 1, 0))
	var coins0: int = p.kit.count("coin")
	p.kit.add("coin", 2)
	var st: Node3D = p.throw_at(L(w, Vector3(1.0, 0, 0.5)), "coin", true)
	await wait_until(func() -> bool: return st.landed, 3.0)
	await wait_s(2.5)
	var took: bool = npc in st.takers
	var crowd: bool = npc.is_in_group("crowd") or int(npc.mode) == 3
	K["throw_coin"] = took and crowd and "coin" in heard and p.kit.count("coin") == coins0 + 1
	var line: String = "[smoke] kit throw_coin takers=%d walker_claimed=%s crowd=%s ring=%s purse %d->%d %s" % [st.takers.size(), took, crowd,
			"coin" in heard, coins0 + 2, p.kit.count("coin"), "OK" if K["throw_coin"] else "FAIL"]
	npc.queue_free()
	_free(w)
	return line


func t_pickup(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	var root: Node3D = w["root"]
	var pk: Node3D = PickupScript.new()
	pk.item = "stone"
	pk.count = 3
	root.add_child(pk)
	pk.position = Vector3(0, 0, -0.9)
	var bt: Node3D = PickupScript.new()
	bt.item = "bottle"
	root.add_child(bt)
	bt.position = Vector3(5, 0, -0.9)
	await wait_s(0.1)
	tp(w, Vector3(0, 0, 0), Vector3(0, 0, -2))
	await wait_s(0.1)
	var s0: int = p.kit.count("stone")
	var prompt: String = p.prompt_text
	var ok1: bool = p.try_interact()
	tp(w, Vector3(5, 0, 0), Vector3(5, 0, -2))
	await wait_s(0.1)
	var ok2: bool = p.try_interact()
	K["pickup"] = ok1 and ok2 and p.kit.count("stone") == s0 + 3 and p.kit.count("bottle") == 1
	_free(w)
	return "[smoke] kit pickup prompt='%s' stones %d->%d bottle=%d %s" % [prompt, s0, p.kit.count("stone"), p.kit.count("bottle"),
			"OK" if K["pickup"] else "FAIL"]


# ------------------------------------------------------------------ traversal

## Builds the parkour yard: a 1 m wall, a 2 m ledge, a 3.2 m wall (the roof), all facing +Z.
func yard(w: Dictionary, visual := false) -> void:
	wall(w, Vector3(0, 0.5, -1.2), Vector3(3, 1.0, 0.3), visual)             # vault
	wall(w, Vector3(8, 1.0, -2.6), Vector3(3, 2.0, 3.0), visual)             # mantle (face at z -1.1)
	wall(w, Vector3(16, 1.6, -3.6), Vector3(6, 3.2, 5.0), visual)            # hang / climb (face at z -1.1)


func t_traversal(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	yard(w)
	await wait_s(0.2)
	var notes := PackedStringArray()
	# vault
	tp(w, Vector3(0, 0, -0.4), Vector3(0, 0.5, -3))
	await wait_s(0.1)
	p.ai_jump = true
	await wait_s(1.0)
	var lp := (w["root"] as Node3D).to_local(p.global_position)
	K["vault"] = p.trav.counts.get("vault", 0) == 1 and lp.z < -1.6 and absf(lp.y) < 0.2
	notes.append("vault z=%.2f y=%.2f" % [lp.z, lp.y])
	# mantle
	tp(w, Vector3(8, 0, -0.4), Vector3(8, 1, -3))
	await wait_s(0.1)
	p.ai_jump = true
	await wait_s(1.6)
	lp = (w["root"] as Node3D).to_local(p.global_position)
	K["mantle"] = p.trav.counts.get("mantle", 0) == 1 and absf(lp.y - 2.0) < 0.2 and lp.z < -1.2
	notes.append("mantle y=%.2f" % lp.y)
	# hang
	tp(w, Vector3(16, 0, -0.4), Vector3(16, 1, -3))
	await wait_s(0.1)
	p.ai_jump = true
	await wait_s(0.7)
	lp = (w["root"] as Node3D).to_local(p.global_position)
	var hang_y: float = lp.y
	K["hang"] = p.trav.state == TraversalScript.HANG and absf(lp.y - (3.2 - 2.05)) < 0.15
	# shimmy along the edge
	var x0: float = lp.x
	p.ai_move = (w["root"] as Node3D).global_transform.basis.x
	await wait_s(0.8)
	p.ai_move = Vector3.ZERO
	var shimmied: bool = absf((w["root"] as Node3D).to_local(p.global_position).x - x0) > 0.2
	notes.append("hang y=%.2f shimmy=%s" % [hang_y, shimmied])
	# climb up
	p.ai_jump = true
	await wait_s(1.4)
	lp = (w["root"] as Node3D).to_local(p.global_position)
	K["climb"] = p.trav.counts.get("climb", 0) == 1 and absf(lp.y - 3.2) < 0.2 and p.trav.state == TraversalScript.NONE
	notes.append("climb y=%.2f" % lp.y)
	# drop off the roof edge (3.2 m): a roll
	p.ai_move = (w["root"] as Node3D).global_transform.basis.z
	var landed: float = await wait_until(func() -> bool: return p.trav.last_landing != "", 4.0)
	p.ai_move = Vector3.ZERO
	await wait_s(0.2)
	K["drop_roll"] = p.trav.last_landing == "roll" and p.health == 3
	notes.append("drop fall=%.1fm landing=%s health=%d" % [p.trav.last_fall, p.trav.last_landing, p.health])
	# slide
	tp(w, Vector3(-8, 0, 4), Vector3(-8, 0, -3))
	p.ai_sprint = true
	p.ai_move = -(w["root"] as Node3D).global_transform.basis.z
	await wait_s(0.6)
	p.ai_drop = true
	await wait_s(0.2)
	var slid: bool = p.trav.counts.get("slide", 0) >= 1
	p.ai_sprint = false
	p.ai_move = Vector3.ZERO
	notes.append("slide=%s" % slid)
	var ok: bool = K["vault"] and K["mantle"] and K["hang"] and K["climb"] and K["drop_roll"]
	_free(w)
	return "[smoke] kit traversal %s %s" % [" ".join(notes), "OK" if ok else "FAIL"]


# ------------------------------------------------------------------ first-person close actions

func t_camera(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	var root: Node3D = w["root"]
	var wt: Node = w["watch"]
	# a tenement wall with a knockable door
	wall(w, Vector3(0, 2.0, -1.4), Vector3(6, 4, 0.4))
	var door := Distraction.KnockDoor.new()
	root.add_child(door)
	door.position = Vector3(0, 0, -1.15)
	# a listening spot and two locks further along
	var ls := Node3D.new()
	ls.position = Vector3(8, 0, -1.2)
	ls.set_meta("listen", true)
	ls.set_meta("lines", [["Jutro o północy, przy Sukiennicach.", "Tomorrow at midnight, by the Cloth Hall."]])
	root.add_child(ls)
	var lock1 := Node3D.new()
	lock1.position = Vector3(16, 0, -1.2)
	lock1.set_meta("locked", 3)
	root.add_child(lock1)
	var lock2 := Node3D.new()
	lock2.position = Vector3(24, 0, -1.2)
	lock2.set_meta("locked", 2)
	root.add_child(lock2)
	var n_spots := FpViewScript.attach_all(root)
	await wait_s(0.2)
	var notes := PackedStringArray()
	# keyhole
	p.ai_crouch = true
	tp(w, Vector3(0, 0, -0.2), Vector3(0, 1, -2))
	await wait_s(0.3)
	var started: bool = p.try_interact()
	p.ai_interact_hold = true
	await wait_s(0.5)
	var first: bool = p.cam_mode == Player.CamMode.FIRST and p.fp != null and p.fp.kind == "keyhole" and p.fp.mask_visible()
	var head: bool = p.head_hidden()
	p.ai_interact_hold = false
	await wait_s(0.5)
	var back: bool = p.fp == null and p.cam_mode == Player.CamMode.THIRD
	K["keyhole"] = started and first and back
	notes.append("keyhole started=%s first=%s head_hidden=%s back=%s" % [started, first, head, back])
	p.ai_crouch = false
	await wait_s(0.2)
	# listen
	tp(w, Vector3(8, 0, -0.3), Vector3(8, 1, -2))
	await wait_s(0.2)
	var l_started: bool = p.try_interact()
	p.ai_interact_hold = true
	var s: Node = p.fp
	await wait_s(2.2)
	var heard: int = s.heard.size() if is_instance_valid(s) else 0
	var muffled: bool = s.muffled if is_instance_valid(s) else false
	p.ai_interact_hold = false
	await wait_s(0.3)
	K["listen"] = l_started and heard >= 1 and p.fp == null
	notes.append("listen heard=%d muffle_hook=%s" % [heard, muffled])
	# lockpick, played well
	tp(w, Vector3(16, 0, -0.3), Vector3(16, 1, -2))
	await wait_s(0.2)
	var k_started: bool = p.try_interact()
	var sess: Node = p.fp
	var t := 0.0
	while is_instance_valid(sess) and p.fp == sess and t < 20.0:
		var q = sess.qte
		p.ai_tension = q.tension < (q.band.x + q.band.y) * 0.5
		p.ai_tap = q.catching() and q.tension >= q.band.x + 0.02
		t += await step()
	p.ai_tension = false
	var res: String = p.last_fp_result
	K["lockpick"] = k_started and not bool(lock1.get_meta("locked", true))
	notes.append("lockpick result=%s in %.1fs unlocked=%s" % [res, t, not bool(lock1.get_meta("locked", true))])
	# the QTE failing: three bad taps, noise each time
	var rings0: int = wt.ring_count()
	var heard_k := []
	wt.sound_event.connect(func(_pos: Vector3, _l: float, kind: String) -> void: heard_k.append(kind))
	tp(w, Vector3(24, 0, -0.3), Vector3(24, 1, -2))
	await wait_s(0.2)
	var f_started: bool = p.try_interact()
	var fs: Node = p.fp
	t = 0.0
	while is_instance_valid(fs) and p.fp == fs and t < 6.0:
		p.ai_tension = false
		p.ai_tap = true
		t += await step()
	var fres: String = p.last_fp_result
	K["qte"] = f_started and fres == "fail" and heard_k.count("lockpick") >= 3 and bool(lock2.get_meta("locked", false))
	notes.append("qte fail=%s noises=%d rings %d->%d" % [fres, heard_k.count("lockpick"), rings0, wt.ring_count()])
	_free(w)
	return "[smoke] kit camera spots=%d %s" % [n_spots, " ".join(notes)]


# ------------------------------------------------------------------ finale kit: poison, torch, rigging, cosh

class FireStub extends Node:
	var lit: Array = []

	func _ready() -> void:
		add_to_group("fire")

	func ignite(pos: Vector3) -> void:
		lit.append(pos)


func t_finale(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	var root: Node3D = w["root"]
	var notes := PackedStringArray()
	# poison: a tankard on a table
	var tank := Node3D.new()
	tank.name = "Tankard"
	tank.position = Vector3(0, 0.9, -0.9)
	tank.set_meta("poisonable", true)
	root.add_child(tank)
	# rigging: a cargo hook's load 3.2 m up over the lane
	var load_ := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(0.8, 0.6, 0.8)
	load_.mesh = bm
	load_.name = "CargoLoad"
	load_.position = Vector3(10, 3.2, 0)
	load_.set_meta("rig", true)
	load_.set_meta("rig_kind", "drop")
	root.add_child(load_)
	var n := VerbsScript.attach_all(root)
	await wait_s(0.2)
	p.kit.add("poison", 1)
	tp(w, Vector3(0, 0, 0.2), Vector3(0, 0.9, -2))
	await wait_s(0.2)
	var poured: bool = p.try_interact()
	K["poison"] = poured and bool(tank.get_meta("poisoned", false)) and p.kit.count("poison") == 0
	notes.append("poison poured=%s meta=%s" % [poured, tank.get_meta("poisoned", false)])
	await wait_s(1.0)
	# torch: lit at a lantern, carried (visibility x1.4), thrown into the fire system
	var fire := FireStub.new()
	root.add_child(fire)
	lantern(w, Vector3(-10.9, 0, 0), false)
	p.kit.add("torch", 1)
	p.kit.select("torch")
	tp(w, Vector3(-10, 0, 0.8), Vector3(-10, 1, -2))
	await wait_s(0.3)
	var vis0: float = p.visibility
	var lit: bool = p.try_interact() and p.kit.torch_lit
	await wait_s(0.3)
	var vis1: float = p.visibility
	var st: Node3D = p.throw_at(L(w, Vector3(-10, 0, -4)), "torch", true)
	await wait_until(func() -> bool: return st.landed, 3.0)
	await wait_s(0.1)
	K["torch"] = lit and vis1 > vis0 * 1.3 and fire.lit.size() >= 1 and p.kit.count("torch") == 0
	notes.append("torch lit=%s vis %.2f->%.2f fire_calls=%d" % [lit, vis0, vis1, fire.lit.size()])
	# rig: arm the load, a patrol walks under it
	tp(w, Vector3(10, 0, 1.0), Vector3(10, 3.2, 0))
	await wait_s(0.2)
	var armed_use: bool = p.try_interact()
	await wait_s(2.3)
	var armed: bool = bool(load_.get_meta("armed", false))
	var g := guard(w, "Rig victim", [Vector3(10, 0, -6), Vector3(10, 0, 6)], PI)
	g.patrol_speed = 2.0
	tp(w, Vector3(15, 0, -12), Vector3(10, 1, -12))      # out of his sight: he walks his round under the load
	var downed: float = await wait_until(func() -> bool: return g.is_downed(), 10.0)
	K["rig_drop"] = armed_use and armed and downed >= 0.0
	notes.append("rig armed=%s guard_downed=%s after %.1fs" % [armed, g.is_downed(), downed])
	# cosh: from behind, a knockout, not a death
	var g2 := guard(w, "Cosh victim", [Vector3(20, 0, 0)], 0.0)
	await wait_s(0.2)
	p.kit.select("cosh")
	tp(w, Vector3(20, 0, 1.0), Vector3(20, 1, 0))
	await wait_s(0.05)
	var r := p.attack()
	K["cosh"] = r == "takedown" and g2.is_downed() and not g2.dead and p.kit.last_takedown == "cosh"
	notes.append("cosh=%s downed=%s dead=%s" % [r, g2.is_downed(), g2.dead])
	fire.queue_free()
	_free(w)
	return "[smoke] kit finale verbs=%d %s" % [n, " ".join(notes)]


# ------------------------------------------------------------------ held props, inventory, wheel, blood

func _splats(w: Dictionary) -> int:
	var n := 0
	for sp in get_tree().get_nodes_in_group("blood_splat"):
		if (w["root"] as Node3D).is_ancestor_of(sp):
			n += 1
	return n


func t_hold_ui(idx: int) -> String:
	var w := make_world(idx)
	var p: Player = w["player"]
	var root: Node3D = w["root"]
	wall(w, Vector3(0, 1.5, -2.6), Vector3(6, 3, 0.3))
	await wait_s(0.2)
	# every kit item in the hand in turn
	var held := PackedStringArray()
	for it in ["knife", "cosh", "cudgel", "pistol", "torch", "stone", "bottle", "coin", "smoke", "flash"]:
		if not p.kit.has(it):
			p.kit.add(it, 1)
		p.kit.select(it)
		await get_tree().process_frame
		await get_tree().process_frame
		if p.held_item() == it and p.held_prop() != null:
			held.append(it)
	K["held"] = ",".join(held)
	# inventory: equip, drop
	var inv := InventoryScript.new()
	inv.player = p
	inv.pause = false
	(w["vp"] as Node).add_child(inv)
	await get_tree().process_frame
	inv.open()
	inv.select_item("pistol")
	inv.equip()
	var equipped: bool = p.kit.current == "pistol"
	var stones0: int = p.kit.count("stone")
	inv.select_item("stone")
	inv.drop()
	await get_tree().process_frame
	var dropped := false
	for pk in get_tree().get_nodes_in_group("kit_pickup"):
		if root.is_ancestor_of(pk) and pk.item == "stone":
			dropped = true
	K["inventory"] = inv.is_open() and inv.items().size() >= 8 and equipped and p.kit.count("stone") == stones0 - 1 and dropped
	inv.close()
	# wheel: a hold opens it (time x0.25), release equips the highlighted item; a tap does not
	var wh := WheelScript.new()
	wh.player = p
	wh.sandbox = true
	(w["vp"] as Node).add_child(wh)
	await get_tree().process_frame
	wh.press()
	await wait_s(0.1)
	var early: bool = wh.is_wheel_open
	await wait_s(0.3)
	var opened: bool = wh.is_wheel_open and wh.time_scale_applied == 0.25
	wh.highlight("smoke")
	wh.release()
	K["wheel"] = not early and opened and p.kit.current == "smoke" and not wh.is_wheel_open and wh.time_scale_applied == 1.0
	# blood: a knife slash and a pistol ball on a guard by the wall
	var g := guard(w, "Blood guard", [Vector3(0, 0, -1.4)], PI)
	await wait_s(0.2)
	p.kit.select("knife")
	tp(w, Vector3(0, 0, -0.3), Vector3(0, 1, -1.4))
	await wait_s(0.1)
	var r := p.attack()
	await wait_s(0.3)
	var blade: bool = p.held_prop() != null and p.held_prop().has_meta("blood")
	var cosh_before := _splats(w)
	# a cosh gives none
	var g2 := guard(w, "Cosh guard", [Vector3(8, 0, 0)], 0.0)
	await wait_s(0.2)
	p.kit.select("cosh")
	tp(w, Vector3(8, 0, 1.0), Vector3(8, 1, 0))
	await wait_s(0.05)
	p.attack()
	await wait_s(0.3)
	K["splats"] = cosh_before
	var clean: bool = _splats(w) == cosh_before
	var stain: bool = g._figure.has_meta("blood_stain")
	_free(w)
	return "[smoke] kit hold_ui held=%s inventory equip=%s drop=%s wheel early=%s opened=%s picked=%s blood slash=%s splats=%d blade=%s coat=%s cosh_clean=%s" % [
			",".join(held), equipped, dropped, early, opened, p.kit.current, r, cosh_before, blade, stain, clean]


## `--kit-shot=dir --grip-shot`: each held item in turn with the grips of data/stealth.json and, per item, the
## variants in GRIP_TRIALS (kit_grip_<item>_<n>.png), to tune kit.grips by eye.
const GRIP_TRIALS := {}   ## item -> [grip, ...] to try beside the data one


func t_grip_shots(idx: int) -> String:
	var w := make_world(idx, {}, true)
	var p: Player = w["player"]
	var root: Node3D = w["root"]
	_shot_env(root)
	lantern(w, Vector3(1.5, 0, 1.5), false, true)
	var cam := _cam(w)
	tp(w, Vector3(0, 0, 0), Vector3(0, 1, -4))
	await wait_s(0.4)
	var out := PackedStringArray()
	var poses := {"knife": ["knife_parry", 0.0], "pistol": ["pistol_aim", 0.5], "torch": ["idle", 1.0], "cudgel": ["idle", 1.0],
			"cosh": ["idle", 1.0], "bottle": ["idle", 1.0], "stone": ["idle", 1.0], "musket": ["idle", 1.0]}
	var base: Dictionary = Perception_tg("kit.grips", {})
	for it in poses:
		var trials: Array = [base.get(it, base.get("default", {}))] + GRIP_TRIALS.get(it, [])
		for n in trials.size():
			var grips := base.duplicate(true)
			grips[it] = trials[n]
			(w["watch"] as Node).overrides["kit.grips"] = grips
			if not p.kit.has(it):
				p.kit.add(it, 1)
			p.kit.select(it)
			if it == "torch":
				p.kit.torch_lit = true
			p._hand_item = "?"
			p._update_hand_prop()
			p.set_physics_process(false)
			p._freeze_clip(p._figure, poses[it][0], poses[it][1])
			await get_tree().process_frame
			var fwd := -p._figure.global_transform.basis.z
			var right := p._figure.global_transform.basis.x
			var hand := p.global_position + Vector3(0, 1.1, 0) + right * 0.25 + fwd * 0.2
			if it == "pistol":
				hand = p.global_position + Vector3(0, 1.45, 0) + fwd * 0.55 + right * 0.05
			_look(cam, hand + fwd * 0.9 + right * 0.8 + Vector3(0, 0.15, 0), hand)
			out.append(await _shot(w, "kit_grip_%s_%d" % [it, n], str(trials[n])))
			_look(cam, hand + right * 1.1 + Vector3(0, 0.1, 0), hand)
			out.append(await _shot(w, "kit_grip_%s_%d_side" % [it, n], ""))
			p.set_physics_process(true)
			Assets.clear_action(p._figure)
	_free(w)
	return "[smoke] kit grip shots " + " ".join(out)


static func Perception_tg(path: String, fb: Variant) -> Variant:
	return load("res://scripts/stealth/perception.gd").tg(path, fb)


# ------------------------------------------------------------------ screenshots

func _cam(w: Dictionary) -> Camera3D:
	var c := Camera3D.new()
	c.fov = 45
	(w["root"] as Node3D).add_child(c)
	return c


func _look(c: Camera3D, from: Vector3, at: Vector3) -> void:
	c.global_position = from
	c.look_at(at)
	c.current = true


func t_kit_shots(idx: int) -> String:
	var w := make_world(idx, {"sweep.sentry_amplitude_deg": 0.0, "sweep.amplitude_deg": 0.0}, true)
	var p: Player = w["player"]
	var root: Node3D = w["root"]
	_shot_env(root)
	var slab := Assets.instance("ground_cobbles")
	if slab:
		slab.queue_free()
		for ix in range(-5, 7):
			for iz in range(-4, 4):
				var sl := Assets.instance("ground_cobbles")
				sl.position = Vector3(ix * 4.0, 0, iz * 4.0)
				root.add_child(sl)
	lantern(w, Vector3(-3.5, 0, 2), false, true)
	lantern(w, Vector3(12, 0, 2), false, true)
	yard(w, true)
	Assets.place(root, "tenement_a", Vector3(-6, 0, -14), 0.0)
	Assets.place(root, "tenement_c", Vector3(6, 0, -14), 0.0)
	var out := PackedStringArray()
	var cam := _cam(w)
	# 1. a knife parry from the side
	var g := guard(w, "Shot guard", [Vector3(-4, 0, 4)], PI)
	g.set_physics_process(false)
	p.kit.select("knife")
	tp(w, Vector3(-4, 0, 5.4), Vector3(-4, 1, 4))
	await wait_s(0.3)
	p.set_physics_process(false)
	p._freeze_clip(p._figure, "knife_parry", 0.18)
	p._freeze_clip(g._figure, "musket_butt", 0.44)
	_look(cam, L(w, Vector3(-0.2, 1.2, 4.7)), L(w, Vector3(-4, 1.0, 4.7)))
	out.append(await _shot(w, "kit_parry_side", "knife"))
	p.set_physics_process(true)
	Assets.clear_action(p._figure)
	g.queue_free()
	# 2. a smoke cloud in the lantern light
	p._camera.current = true
	tp(w, Vector3(2, 0, 8), Vector3(2, 0, 3))
	p.rotate_camera(Vector3(-0.15, 0.2, 0))
	var st: Node3D = p.throw_at(L(w, Vector3(0, 0, 3)), "smoke", false)
	await wait_until(func() -> bool: return st.landed, 3.0)
	await wait_s(1.8)
	out.append(await _shot(w, "kit_smoke_cloud", "cloud=%s" % (st.effect != null)))
	await wait_s(8.0)
	# 3. a flash in a guard's face
	var g2 := guard(w, "Flash guard", [Vector3(4, 0, 3)], PI)
	await wait_s(0.2)
	tp(w, Vector3(4.5, 0, 11), Vector3(4, 1, 3))
	var fl: Node3D = p.throw_at(L(w, Vector3(4, 0, 5)), "flash", false)
	_look(cam, L(w, Vector3(9.5, 1.6, 6.5)), L(w, Vector3(4, 1.0, 4)))
	await wait_until(func() -> bool: return fl.landed, 3.0)
	out.append(await _shot(w, "kit_flash", "staggered=%s" % g2.is_staggered()))
	p._camera.current = true
	await wait_s(0.3)
	g2.queue_free()
	# 4. a vault, mid-air, from the side
	tp(w, Vector3(0, 0, -0.4), Vector3(0, 0.5, -3))
	await wait_s(0.2)
	p.ai_jump = true
	await wait_s(0.24)
	_look(cam, L(w, Vector3(4.5, 1.3, -1.2)), L(w, Vector3(0, 0.9, -1.2)))
	p.set_physics_process(false)
	out.append(await _shot(w, "kit_vault_midair", "state=%s" % p.trav.state_name()))
	p.set_physics_process(true)
	await wait_s(0.8)
	# 5. hanging from the sill of the 3.2 m wall
	tp(w, Vector3(15, 0, -0.4), Vector3(15, 1, -3))
	await wait_s(0.2)
	p.ai_jump = true
	await wait_s(0.8)
	_look(cam, L(w, Vector3(19.5, 2.2, 2.8)), L(w, Vector3(15, 2.0, -1.1)))
	out.append(await _shot(w, "kit_hang_sill", "state=%s" % p.trav.state_name()))
	# 6. up on the roof, looking down at the street and a guard
	p.ai_jump = true
	await wait_s(1.5)
	var g3 := guard(w, "Street guard", [Vector3(12, 0, 6), Vector3(20, 0, 6)], PI * 0.5)
	p._camera.current = true
	p.rotate_camera(Vector3(-0.55, PI, 0))
	await wait_s(0.6)
	out.append(await _shot(w, "kit_roof_view", "y=%.1f" % root.to_local(p.global_position).y))
	g3.queue_free()
	# 7. through a keyhole into a lit room with a guard at the table
	wall(w, Vector3(-10, 2.0, -1.4), Vector3(4, 4, 0.3), true)
	wall(w, Vector3(-12, 2.0, -4.0), Vector3(0.3, 4, 5), true)
	wall(w, Vector3(-8, 2.0, -4.0), Vector3(0.3, 4, 5), true)
	wall(w, Vector3(-10, 2.0, -6.5), Vector3(4, 4, 0.3), true)
	wall(w, Vector3(-10, 4.1, -4.0), Vector3(4.3, 0.2, 5.3), true)
	var room_light := OmniLight3D.new()
	room_light.light_color = Color(1.0, 0.72, 0.42)
	room_light.light_energy = 3.0
	room_light.omni_range = 6.0
	root.add_child(room_light)
	room_light.position = Vector3(-9.5, 2.6, -4.5)
	Assets.place(root, "barrel", Vector3(-11, 0, -5.5), 0.3)
	var g4 := guard(w, "Room guard", [Vector3(-9.6, 0, -4.8)], 0.4)
	g4.set_physics_process(false)
	Assets.play(g4._figure, "idle")
	var door := Distraction.KnockDoor.new()
	root.add_child(door)
	door.position = Vector3(-10, 0, -1.25)
	door.rotation.y = 0.0
	p.ai_crouch = true
	tp(w, Vector3(-10, 0, -0.5), Vector3(-10, 1, -3))
	await wait_s(0.4)
	p._camera.current = true
	p.start_fp("keyhole", door)
	p.ai_interact_hold = true
	await wait_s(0.6)
	out.append(await _shot(w, "kit_keyhole", "mode=%d" % p.cam_mode))
	p.ai_interact_hold = false
	p.ai_crouch = false
	await wait_s(0.4)
	# 8. held props: knife (knife guard pose), pistol (aimed), torch (lit, upright), close from the front-right
	tp(w, Vector3(-3.0, 0, 1.0), Vector3(-3.0, 1, -3))
	await wait_s(0.3)
	for hold in [["knife", "knife_parry", 0.0], ["pistol", "pistol_aim", 0.5], ["torch", "idle", 1.0]]:
		if not p.kit.has(hold[0]):
			p.kit.add(hold[0], 1)
		p.kit.select(hold[0])
		if hold[0] == "torch":
			p.kit.torch_lit = true
			p.kit.changed.emit()
		await wait_s(0.2)
		p.set_physics_process(false)
		p._freeze_clip(p._figure, hold[1], hold[2])
		var fwd := -p._figure.global_transform.basis.z
		var right := p._figure.global_transform.basis.x
		var hand := p.global_position + Vector3(0, 1.15, 0) + right * 0.2 + fwd * 0.25
		_look(cam, hand + fwd * 1.3 + right * 0.9 + Vector3(0, 0.25, 0), hand)
		out.append(await _shot(w, "kit_held_" + str(hold[0]), "held=%s" % p.held_item()))
		p.set_physics_process(true)
		Assets.clear_action(p._figure)
	# 9. a splatter: a knife thrust into a guard facing the 3.2 m wall of the yard
	p.kit.select("knife")
	lantern(w, Vector3(19.5, 0, 1.5), false, true)
	var gb := guard(w, "Splatter guard", [Vector3(17, 0, -0.5)], 0.0)
	await wait_s(0.2)
	p.kit.lethal = true
	tp(w, Vector3(17, 0, 0.5), Vector3(17, 1, -0.5))
	await wait_s(0.05)
	p.attack()
	await wait_s(1.6)
	tp(w, Vector3(23, 0, 3))
	_look(cam, L(w, Vector3(18.6, 1.6, 2.4)), L(w, Vector3(17, 0.6, -0.9)))
	out.append(await _shot(w, "kit_blood_splatter", "splats=%d" % _splats(w)))
	p.kit.lethal = false
	# 10. the weapon wheel and 11. the inventory, over the player's view
	p._camera.current = true
	tp(w, Vector3(2, 0, 8), Vector3(2, 1, 0))
	var wh := WheelScript.new()
	wh.player = p
	wh.sandbox = true
	(w["vp"] as Node).add_child(wh)
	await get_tree().process_frame
	wh.open_wheel()
	wh.highlight("smoke")
	await wait_s(0.2)
	out.append(await _shot(w, "kit_wheel", "items=%d" % wh.items().size()))
	wh.close_wheel()
	var inv := InventoryScript.new()
	inv.player = p
	inv.pause = false
	(w["vp"] as Node).add_child(inv)
	await get_tree().process_frame
	inv.open()
	inv.select_item("pistol")
	await wait_s(0.2)
	out.append(await _shot(w, "kit_inventory", "items=%d" % inv.items().size()))
	inv.close()
	_free(w)
	return "[smoke] kit screenshots " + " ".join(out)
