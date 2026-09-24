extends Node3D
## Fire on the Rynek. One per district (group "fire"), made by street_life.gd. Anything with meta `flammable`
## (tagged at start-up: straw, the hay cart, awnings, woodpiles, the washing, stalls, handcarts, crates and sacks,
## stacked chairs) can burn. `Fire.ignite(pos)` (static: a knocked-over brazier or lamp, a thrown torch, a riot)
## lights the flammable thing nearest `pos` within 2.5 m, or a small ground fire there.
##
## A burning thing: small GPU particle flames and smoke, a warm flickering light (flicker.gd), an avoidance obstacle
## so walkers steer round it, a sound event (0.8) that draws the watch. Every few seconds it may catch neighbours
## within 2 m (spreading over ~20-40 s; snow and rain, Weather.current().wetness, slow it). It burns 60-120 s, less
## for each bucket: a bucket line of townsfolk walks between the nearest well and the fire. Anyone standing in it is
## hurt (the player: one health at a time, never the last). Afterwards the thing is charred (dark material).
## Signals: ignited(node), spread(node), burnt_out(node). Mission.flags "fire_started", "fire_out".

signal ignited(node: Node3D)
signal spread(node: Node3D)
signal burnt_out(node: Node3D)

const FlickerLight := preload("res://scripts/city/flicker.gd")
const Walker := preload("res://scripts/npc/walker.gd")
const NpcScript := preload("res://scripts/npc/npc.gd")
const WEATHER := "res://scripts/city/weather.gd"

## Assets that catch, and how big a fire they make (radius, m).
const FLAMMABLE := {"straw_scatter": 1.0, "woodpile_leanto": 1.6, "awning_striped": 1.4, "laundry_line": 1.2,
		"market_stall": 1.6, "handcart": 1.0, "sacks_crates": 1.0, "chairs_stacked": 0.8, "crate_stack": 1.2,
		"cart": 1.4, "hay": 1.4, "coach": 1.6, "notice_board": 0.8}
const POISONABLE := ["barrel", "cafe_table_set"]
const WELLS := [Vector3(-12, 0, 9), Vector3(14, 0, -9)]

var burning: Dictionary = {}       ## node -> {left: s, fx: Node3D, spread_t: s, r: m}
var spread_count := 0
var out_count := 0
var _rng := RandomNumberGenerator.new()
var _bucket_line: Array = []
var _hurt_cd := 0.0
var _registry: Array = []          ## flammable nodes
var rate := 1.0                    ## burn and spread speed multiplier (smoke runs use 10)


static func ignite(pos: Vector3, tree: SceneTree = null) -> Node3D:
	var t: SceneTree = tree if tree else (Engine.get_main_loop() as SceneTree)
	var f: Node = t.get_first_node_in_group("fire") if t else null
	return f.call("ignite_at", pos) as Node3D if f else null


func _ready() -> void:
	name = "Fire"
	add_to_group("fire")
	_rng.randomize()
	_tag.call_deferred()


## Mark what can burn among the district's props (dressing, furniture, hiding spots, outer city near set).
func _tag() -> void:
	var root := get_parent()
	while root and not root.is_in_group("nav_source") and root.get_parent() and root.get_parent() != get_tree().root:
		root = root.get_parent()
	if root == null:
		return
	for n in root.find_children("*", "Node3D", true, false):
		var base := n.scene_file_path.get_file().get_basename()
		if FLAMMABLE.has(base) and not n.has_meta("flammable"):
			n.set_meta("flammable", true)
			n.set_meta("fire_radius", FLAMMABLE[base])
		elif n.get("kind") != null and str(n.get("kind")) in ["hay", "leanto", "coach"] and n.is_in_group("hiding_spot"):
			n.set_meta("flammable", true)
			n.set_meta("fire_radius", 1.4)
		if base in POISONABLE and not n.has_meta("poisonable"):
			n.set_meta("poisonable", true)       # the intel/kit pass reads it; fire just tags it while it walks the props
		if n.has_meta("flammable"):
			_registry.append(n)


func flammables() -> Array:
	_registry = _registry.filter(func(n): return is_instance_valid(n))
	return _registry


func ignite_at(pos: Vector3) -> Node3D:
	var best: Node3D = null
	var bd := 2.5
	for n in flammables():
		var d := Vector2(n.global_position.x - pos.x, n.global_position.z - pos.z).length()
		if d < bd and not burning.has(n) and not n.has_meta("charred"):
			bd = d
			best = n
	if best == null:
		best = Node3D.new()           # a ground fire: spilt oil and straw, small and short
		best.name = "GroundFire"
		best.position = Vector3(pos.x, 0.0, pos.z)
		best.set_meta("flammable", true)
		best.set_meta("fire_radius", 0.7)
		best.set_meta("ground", true)
		add_child(best)
	_start(best)
	return best


func _start(n: Node3D) -> void:
	if burning.has(n):
		return
	var r := float(n.get_meta("fire_radius", 1.0))
	var fx := _flames(r)
	add_child(fx)
	fx.global_position = Vector3(n.global_position.x, 0.0, n.global_position.z)
	var life := _rng.randf_range(60.0, 120.0) * (0.35 if n.has_meta("ground") else 1.0)
	burning[n] = {"left": life, "fx": fx, "spread_t": _rng.randf_range(4.0, 8.0), "r": r}
	Mission.set_flag("fire_started", true)
	ignited.emit(n)
	var w := get_tree().get_first_node_in_group("watch")
	if w and w.has_method("emit_sound"):
		w.emit_sound(fx.global_position, 0.8, "fire", false, true, true)
	for g in get_tree().get_nodes_in_group("guards"):
		if (g as Node3D).global_position.distance_to(fx.global_position) < 22.0 and g.has_method("investigate"):
			if not g.has_method("can_investigate") or g.can_investigate():
				g.investigate(fx.global_position, 10.0, "fire")
	if _bucket_line.is_empty():
		_start_bucket_line(fx.global_position)


func _flames(r: float) -> Node3D:
	var root := Node3D.new()
	root.name = "Flames"
	var p := GPUParticles3D.new()
	p.amount = int(clampf(16.0 * r, 10.0, 32.0))
	p.lifetime = 0.9
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = Vector3(r * 0.6, 0.2, r * 0.6)
	pm.direction = Vector3(0, 1, 0)
	pm.spread = 12.0
	pm.initial_velocity_min = 1.2
	pm.initial_velocity_max = 2.4
	pm.gravity = Vector3(0, 0.6, 0)
	pm.scale_min = 0.5
	pm.scale_max = 1.1
	pm.color = Color(1.0, 0.55, 0.15)
	p.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(0.45, 0.6)
	var fm := StandardMaterial3D.new()
	fm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	fm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	fm.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	fm.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	fm.vertex_color_use_as_albedo = true
	fm.albedo_color = Color(1.0, 0.6, 0.2, 0.8)
	q.material = fm
	p.draw_pass_1 = q
	p.position.y = 0.3
	root.add_child(p)
	var s := GPUParticles3D.new()
	s.amount = 12
	s.lifetime = 3.0
	var sm := ParticleProcessMaterial.new()
	sm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	sm.emission_box_extents = Vector3(r * 0.5, 0.2, r * 0.5)
	sm.direction = Vector3(0, 1, 0)
	sm.spread = 20.0
	sm.initial_velocity_min = 0.8
	sm.initial_velocity_max = 1.4
	sm.gravity = Vector3(0.3, 0.2, 0)
	sm.scale_min = 1.0
	sm.scale_max = 2.2
	sm.color = Color(0.12, 0.11, 0.1, 0.5)
	s.process_material = sm
	var sq := QuadMesh.new()
	sq.size = Vector2(0.9, 0.9)
	var smat := StandardMaterial3D.new()
	smat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	smat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	smat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	smat.vertex_color_use_as_albedo = true
	sq.material = smat
	s.draw_pass_1 = sq
	s.position.y = 1.4
	root.add_child(s)
	var l := FlickerLight.new()
	l.amount = 0.35
	l.speed = 11.0
	l.light_color = Color(1.0, 0.5, 0.18)
	l.light_energy = 3.0 + r * 2.0
	l.omni_range = 6.0 + r * 3.0
	l.omni_attenuation = 1.3
	l.position.y = 1.0
	l.light_volumetric_fog_energy = 1.4
	root.add_child(l)
	l.add_to_group("flame_lights")
	var ob := NavigationObstacle3D.new()
	ob.radius = r + 0.3
	ob.avoidance_enabled = true
	root.add_child(ob)
	return root


func _wetness() -> float:
	if not ResourceLoader.exists(WEATHER):
		return 0.0
	var W: Script = load(WEATHER)
	var c: Variant = W.call("current") if W and W.has_method("current") else {}
	return clampf(float((c as Dictionary).get("wetness", 0.0)) if c is Dictionary else 0.0, 0.0, 1.0)


func _physics_process(delta: float) -> void:
	if burning.is_empty():
		return
	var wet := _wetness()
	var p := get_tree().get_first_node_in_group("player") as Node3D
	_hurt_cd = maxf(0.0, _hurt_cd - delta)
	for n in burning.keys():
		var b: Dictionary = burning[n]
		if not is_instance_valid(n):
			_finish(n)
			continue
		b["left"] = float(b["left"]) - delta * (1.0 + wet) * rate
		b["spread_t"] = float(b["spread_t"]) - delta * rate
		if float(b["spread_t"]) <= 0.0:
			b["spread_t"] = _rng.randf_range(4.0, 8.0)
			for m in flammables():
				if burning.has(m) or m.has_meta("charred") or m == n:
					continue
				var d := Vector2(m.global_position.x - n.global_position.x, m.global_position.z - n.global_position.z).length()
				if d < 2.0 + float(b["r"]) * 0.5 and _rng.randf() < 0.3 * (1.0 - 0.75 * wet):
					spread_count += 1
					_start(m)
					spread.emit(m)
		# anyone standing in it
		var fx: Node3D = b["fx"]
		if p and _hurt_cd <= 0.0 and Vector2(p.global_position.x - fx.global_position.x, p.global_position.z - fx.global_position.z).length() < float(b["r"]) * 0.8:
			_hurt_cd = 1.5
			var h := int(p.get("health"))
			if h > 1:
				p.set("health", h - 1)
				Mission.message.emit("The flames lick at you. (%d left)" % (h - 1), 1.5)
		if float(b["left"]) <= 0.0:
			_finish(n)


func _finish(n) -> void:
	var b: Dictionary = burning.get(n, {})
	burning.erase(n)
	if b.has("fx") and is_instance_valid(b["fx"]):
		(b["fx"] as Node3D).queue_free()
	out_count += 1
	if is_instance_valid(n):
		n.set_meta("charred", true)
		if n.has_meta("ground"):
			n.queue_free()
		else:
			_char(n)
		burnt_out.emit(n)
	if burning.is_empty():
		Mission.set_flag("fire_out", true)
		for w in _bucket_line:
			if is_instance_valid(w):
				_end_bucket(w)
		_bucket_line.clear()


func _char(n: Node) -> void:
	var dark := StandardMaterial3D.new()
	dark.albedo_color = Color(0.07, 0.06, 0.055)
	dark.roughness = 1.0
	for c in n.find_children("*", "MeshInstance3D", true, false):
		(c as MeshInstance3D).material_override = dark
	if n is MeshInstance3D:
		(n as MeshInstance3D).material_override = dark


# ------------------------------------------------------------------ the bucket line

func _start_bucket_line(at: Vector3) -> void:
	var pop := get_tree().get_first_node_in_group("population")
	if pop == null:
		return
	var well: Vector3 = WELLS[0] if at.distance_to(WELLS[0]) < at.distance_to(WELLS[1]) else WELLS[1]
	var cands: Array = []
	for c in pop.get_children():
		if c.get_script() == NpcScript and c.visible and not c.is_inside() and not c.is_downed() and int(c.mode) != 3 \
				and not c.has_meta("sl_busy") and not c.is_in_group("street_life") and c.global_position.distance_to(at) < 30.0:
			cands.append(c)
	cands.sort_custom(func(a, b): return a.global_position.distance_to(at) < b.global_position.distance_to(at))
	for w in cands.slice(0, 4):
		w.set_meta("sl_busy", true)
		w.set_meta("fire_role", w.role)
		w.claim()
		w.role = "bucket carrier"          # npc.gd walks carriers with carry_basket
		var bucket := Assets.instance("bucket")
		if bucket:
			for cb in bucket.find_children("*", "CollisionObject3D", true, false):
				cb.queue_free()
			bucket.name = "FireBucket"
			bucket.position = Vector3(0.25, 0.55, -0.2)
			bucket.scale = Vector3.ONE * 0.8
			w.add_child(bucket)
		_bucket_line.append(w)
		_carry(w, well, at)
	if not _bucket_line.is_empty():
		Walker.speech(_bucket_line[0], "Pali się! Wody!\n(Fire! Water!)", 3.0)


func _carry(w, well: Vector3, at: Vector3) -> void:
	var to_fire := true
	while is_instance_valid(w) and _bucket_line.has(w) and not burning.is_empty():
		var target: Vector3 = at if to_fire else well
		w.script_goto(target, 2.2 if to_fire else 1.4, false)
		var t := 0.0
		while is_instance_valid(w) and not w.script_arrived and t < 25.0:
			await get_tree().physics_frame
			t += get_physics_process_delta_time()
		if to_fire:
			for n in burning:        # each bucket shortens the nearest fire
				if (burning[n]["fx"] as Node3D).global_position.distance_to(at) < 4.0:
					burning[n]["left"] = float(burning[n]["left"]) - 8.0
			if is_instance_valid(w):
				Assets.play_action(w.get("_figure"), "window_pour" if Assets.has_clip(w.get("_figure"), "window_pour") else "shoved")
			await get_tree().create_timer(1.2, false).timeout
		to_fire = not to_fire


func _end_bucket(w) -> void:
	var b: Node = w.get_node_or_null("FireBucket")
	if b:
		b.queue_free()
	w.role = str(w.get_meta("fire_role", ""))
	w.remove_meta("fire_role")
	w.remove_meta("sl_busy")
	w.release()
