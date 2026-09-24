extends Node
class_name Footsteps
## Footsteps and body sounds for anything that walks (docs/AUDIO.md). `Footsteps.attach(body, kind)` adds one child
## node named "Footsteps" (idempotent; a later explicit kind replaces "auto"). Tables in data/audio.json "footsteps",
## "animals", "vehicles".
## Kinds:
##   shoe / boot / heel / bare / player   people: a step every stride of distance travelled (walk / run stride from
##       the kind), the sample set from the `surface` under the body (Perception.surface_at: cobbles, flags, snow, mud,
##       gravel, planks, straw); boots (guards), heels (women) and bare feet (beggars, urchins) swap in their own set on
##       hard ground; a scuff when the walking direction swings sharply. The player is quieter crouched or prone,
##       louder sprinting.
##   horse     hoof beats matched to the walk cycle: each AnimationPlayer of the body (one per horse) beats at fixed
##             phases of its "walk" (4 beats) / "trot" (2 beats) clip, so hooves follow the clip speed; soft ground
##             swaps to dull thuds. Standing horses snort, stamp and whinny now and then.
##   vehicle   (animal.gd behaviour "drive") the team's hooves as above, plus a wheel loop on the carriage body
##             pitched and levelled by speed (cobbles clatter or mud rumble by the surface under it), a wheel clack
##             over the setts, harness jingle, axle creaks, and the coachman's "Hooo!" when something blocks the road.
##   dog / cat / bird / hawk   calls on random timers (a dog growls at a close player, a cat purrs by a still player,
##             pigeons clap away from a running one).
##   auto      resolved on the first physics frame from the body (group, animal model, npc model name).
##   none      nothing (the dragon, goats and other silent props).

const Perception := preload("res://scripts/stealth/perception.gd")

var body: Node3D
var kind := "auto"

var _resolved := false
var _last_pos := Vector3.INF
var _last_dir := Vector2.ZERO
var _dist := 0.0
var _surface := "cobbles"
var _surf_t := 0.0
var _near := false
var _near_t := 0.0
var _scuff_cd := 0.0
var _foot_ph := -1.0                  ## last phase of the locomotion clip (-1 = none)
var _moving := false
var _rng := RandomNumberGenerator.new()
var _timers: Dictionary = {}          ## call event -> seconds left
var _phases: Dictionary = {}          ## AnimationPlayer -> last phase (0..1)
var _crow := false
# vehicle
var _wheel: AudioStreamPlayer3D
var _wheel_mud: AudioStreamPlayer3D
var _mud_mix := 0.0
var _clack_t := 3.0
var _jingle_t := 2.0
var _creak_t := 6.0
var _hoo_cd := 0.0
var _was_blocked := false
# cat
var _purr: AudioStreamPlayer3D
var _flap_cd := 0.0
var _growl_cd := 0.0


static func attach(b: Node3D, k: String = "auto") -> Node:
	if b == null or not is_instance_valid(b):
		return null
	var ex := b.get_node_or_null("Footsteps")
	if ex:
		if k != "auto" and ex.get("kind") != k:
			ex.set("kind", k)
			ex.set("_resolved", false)
		return ex
	var f := Footsteps.new()
	f.name = "Footsteps"
	f.body = b
	f.kind = k
	b.add_child(f)
	return f


static func cfg(section: String) -> Dictionary:
	return Sfx.data().get(section, {})


func _ready() -> void:
	_rng.seed = hash(str(body.name) if body else "fs")
	_near_t = _rng.randf() * 0.5


func _resolve() -> void:
	_resolved = true
	if kind != "auto":
		return
	kind = "shoe"
	if body.is_in_group("player"):
		kind = "player"
	elif body.is_in_group("guards"):
		kind = "boot"
	elif str(body.get("behaviour")) == "drive":
		kind = "vehicle"
	elif body.has_method("vehicle_position"):      # animal.gd
		var m := str(body.get("model_name"))
		if m.begins_with("horse"):
			kind = "horse"
		elif m.begins_with("dog"):
			kind = "dog"
		elif m == "cat":
			kind = "cat"
		elif m in ["pigeon", "crow"]:
			kind = "bird"
			_crow = m == "crow"
		elif m == "hawk":
			kind = "hawk"
		else:
			kind = "none"
	else:
		var m := (str(body.get("model_name")) + " " + str(body.get("role")) + " " + str(body.name)).to_lower()
		if _has_any(m, ["soldier", "guard", "corporal", "sergeant", "hussar", "drummer", "officer", "watchman"]):
			kind = "boot"
		elif _has_any(m, ["beggar", "urchin", "child", "scaveng", "orphan"]):
			kind = "bare"
		elif _has_any(m, ["_f_", "_f ", "woman", "girl", "madam", "hostess", "wife", "widow", "maid", "nun"]):
			kind = "heel"
	var calls: Array = (cfg("animals").get(kind, {}) as Dictionary).get("crow_calls" if _crow else "calls", [])
	for c in calls:
		_timers[str(c[0])] = _rng.randf_range(float(c[1]) * 0.3, float(c[2]))


static func _has_any(s: String, keys: Array) -> bool:
	for k in keys:
		if s.contains(k):
			return true
	return false


func _physics_process(delta: float) -> void:
	if body == null or not is_instance_valid(body):
		queue_free()
		return
	if not _resolved:
		_resolve()
	if kind == "none":
		set_physics_process(false)
		return
	_near_t -= delta
	if _near_t <= 0.0:
		_near_t = 0.5
		var lp: Variant = Sfx.listener_pos()
		var reach := float(cfg("footsteps").get("cull", 28.0))
		if kind in ["horse", "vehicle"]:
			reach = float(cfg("vehicles").get("radius", 45.0))
		elif kind in ["dog", "cat", "bird", "hawk"]:
			reach = 80.0
		_near = lp == null or body.global_position.distance_to(lp) < reach
	_scuff_cd -= delta
	match kind:
		"horse":
			_hooves()
			_calls(delta)
		"vehicle":
			_vehicle(delta)
		"dog", "cat", "bird", "hawk":
			_critter(delta)
		_:
			_person(delta)


# ------------------------------------------------------------------ people

func _person(delta: float) -> void:
	_surf_t -= delta
	var p := body.global_position
	if _last_pos == Vector3.INF:
		_last_pos = p
	var step := Vector2(p.x - _last_pos.x, p.z - _last_pos.z)
	_last_pos = p
	var moved := step.length()
	if moved > 2.5 or not _near or not body.is_visible_in_tree():   # teleported, far, or hidden
		_dist = 0.0
		_foot_ph = -1.0
		return
	var grounded: bool = body.is_on_floor() if body is CharacterBody3D else true
	var speed := moved / maxf(delta, 0.0001)
	var fc := cfg("footsteps")
	var kc: Dictionary = (fc.get("kinds", {}) as Dictionary).get(kind, {})
	var was_moving := _moving
	_moving = speed >= 0.3 and grounded
	if not _moving:
		_dist = minf(_dist, float(kc.get("walk", 0.72)) * 0.5)
		_foot_ph = -1.0
		return
	if kind == "player" and not was_moving and _rng.randf() < 0.6:
		_extra("cloth_rustle", -4.0)
	var dir := step / moved
	if _last_dir != Vector2.ZERO and _scuff_cd <= 0.0:
		var turn := absf(_last_dir.angle_to(dir)) / maxf(delta, 0.0001)
		if turn > float(fc.get("scuff_turn", 3.0)) and speed < 3.0:
			_scuff_cd = 1.0
			_scuff(0.0)
	_last_dir = dir
	var run := speed > 2.3
	var prone := kind == "player" and bool(body.get("is_prone"))
	# cadence: a step on each heel strike of the locomotion clip (build_animations.py gait: left heel at phase 0,
	# right at 0.5); a crawl drags once a cycle; no usable clip -> one step per stride of distance
	var ap := _anim()
	if ap != null and ap.current_animation_length > 0.0:
		var clip := ap.current_animation.to_lower()
		var crawl := _clip_is(clip, fc.get("crawl_clips", ["crawl"]))
		if crawl or _clip_is(clip, fc.get("loco_clips", ["walk", "run", "jog", "sneak", "march", "carry"])):
			var ph := ap.current_animation_position / ap.current_animation_length
			var last := _foot_ph if _foot_ph >= 0.0 else ph
			_foot_ph = ph
			for b in ([0.1] if crawl else fc.get("heel_phases", [0.0, 0.5])):
				if _crossed(last, ph, float(b)):
					if crawl or prone:
						_drag()
					else:
						_step(kc, run)
			_dist = 0.0
			return
	_foot_ph = -1.0
	var stride := float(kc.get("run" if run else "walk", 0.72))
	if prone:
		stride = 0.9
	_dist += moved
	if _dist >= stride:
		_dist -= stride
		if prone:
			_drag()
		else:
			_step(kc, run)


func _anim() -> AnimationPlayer:
	var fig: Variant = body.get("_figure")
	if fig is Node3D and is_instance_valid(fig) and (fig as Node3D).has_meta("anim"):
		var ap: Variant = (fig as Node3D).get_meta("anim")
		if ap is AnimationPlayer and is_instance_valid(ap):
			return ap
	return null


static func _clip_is(clip: String, keys: Array) -> bool:
	for k in keys:
		if clip.contains(str(k)):
			return true
	return false


func _sample_surface() -> void:
	if _surf_t > 0.0:
		return
	_surf_t = 0.6
	var ex: Array = []
	if body is CollisionObject3D:
		ex.append((body as CollisionObject3D).get_rid())
	_surface = Perception.surface_at(body, body.global_position, ex)


## One step: "step_<surface>_<shoe>" (10 variants), level +-vary_db, pitch +-pitch_var. The player is quieter
## sneaking (with a scuff of the sole now and then), louder sprinting (with a coat swish), and rustles.
func _step(kc: Dictionary, run: bool) -> void:
	_sample_surface()
	var fc := cfg("footsteps")
	var surfs: Dictionary = fc.get("surfaces", {})
	var surf := _surface if surfs.has(_surface) else "cobbles"
	var sc: Dictionary = surfs.get(surf, {})
	var set_name := "step_%s_%s" % [surf, str(kc.get("shoe", "shoe"))]
	var vary := float(fc.get("vary_db", 3.0))
	var vol := float(sc.get("volume_db", 0.0)) + float(kc.get("volume_db", -14.0)) + (float(kc.get("run_db", 2.0)) if run else 0.0) \
			+ _rng.randf_range(-vary, vary)
	if kind == "player":
		if bool(body.get("is_crouching")):
			vol += float(kc.get("sneak_db", -9.0))
			if _rng.randf() < float(kc.get("sneak_scuff", 0.5)):
				_scuff(float(kc.get("sneak_scuff_db", 2.0)))
		elif bool(body.get("is_sprinting")):
			vol += float(kc.get("sprint_db", 3.0))
			if _rng.randf() < float(kc.get("swish_chance", 0.3)):
				_extra("coat_swish", 0.0)
		if _rng.randf() < float(kc.get("rustle_chance", 0.12)):
			_extra("cloth_rustle", -6.0)
	Sfx.play(set_name, body.global_position, vol, float(fc.get("pitch_var", 0.06)), float(kc.get("pitch", 1.0)))


func _scuff(extra_db: float) -> void:
	_sample_surface()
	var sc: Dictionary = (cfg("footsteps").get("surfaces", {}) as Dictionary).get(_surface, {})
	Sfx.play(str(sc.get("scuff", "scuff")), body.global_position, float(cfg("footsteps").get("scuff_volume_db", -16.0)) + extra_db, 0.1)


func _drag() -> void:
	Sfx.play("drag", body.global_position, float(cfg("footsteps").get("drag_volume_db", -14.0)) + _rng.randf_range(-2.0, 2.0), 0.08)


func _extra(ev: String, db: float) -> void:
	Sfx.play(ev, body.global_position + Vector3(0, 1.0, 0), db, 0.08)


# ------------------------------------------------------------------ horses

## One horse per AnimationPlayer: beats when its walk / trot clip crosses the footfall phases.
func _hooves() -> void:
	if not _near:
		_phases.clear()
		return
	var aps: Variant = body.get("_anims")
	if not (aps is Array) or (aps as Array).is_empty():
		return
	var beats: Dictionary = cfg("animals").get("hoof_beats", {"walk": [0.0, 0.25, 0.5, 0.75], "trot": [0.0, 0.5]})
	_surf_t -= get_physics_process_delta_time()
	for ap in aps:
		if not is_instance_valid(ap):
			continue
		var a := ap as AnimationPlayer
		var clip := a.current_animation
		if not beats.has(clip) or a.current_animation_length <= 0.0:
			_phases.erase(a)
			continue
		var ph := a.current_animation_position / a.current_animation_length
		var last := float(_phases.get(a, ph))
		_phases[a] = ph
		for b in beats[clip]:
			if _crossed(last, ph, float(b)):
				_hoof(a, clip)


static func _crossed(a: float, b: float, x: float) -> bool:
	if a == b:
		return false
	if b > a:
		return x > a and x <= b
	return x > a or x <= b          # wrapped round the loop


func _hoof(a: AnimationPlayer, clip: String) -> void:
	_sample_surface()
	var soft := _surface in (cfg("vehicles").get("soft", ["mud", "snow", "straw"]) as Array)
	var ev := "hoof_soft" if soft else ("hoof_trot" if clip == "trot" else "hoof_walk")
	var at: Vector3 = (a.get_parent() as Node3D).global_position if a.get_parent() is Node3D else body.global_position
	Sfx.play(ev, at, 0.0, -1.0, 1.0 + _rng.randf_range(-0.04, 0.04))


func _calls(delta: float) -> void:
	if not _near or _timers.is_empty():
		return
	var moving: bool = body.has_method("is_moving") and body.is_moving()
	var calls: Array = (cfg("animals").get(kind, {}) as Dictionary).get("crow_calls" if _crow else "calls", [])
	for c in calls:
		var ev := str(c[0])
		if kind == "horse" and moving and ev != "horse_snort":
			continue                        # a walking horse does not stamp at a rail
		_timers[ev] = float(_timers.get(ev, 10.0)) - delta
		if _timers[ev] <= 0.0:
			_timers[ev] = _rng.randf_range(float(c[1]), float(c[2]))
			Sfx.play(ev, body.global_position + Vector3(0, 1.0 if kind == "horse" else 0.3, 0))


# ------------------------------------------------------------------ vehicles

func _vehicle(delta: float) -> void:
	var trailer: Variant = body.get("_trailer")
	if trailer == null or not is_instance_valid(trailer):
		return
	var vc := cfg("vehicles")
	var tr := trailer as Node3D
	if _wheel == null:
		_wheel = Sfx.attach_loop(tr, "wheel_loop", float(vc.get("wheel_volume_db", -6.0)), float(vc.get("radius", 45.0)))
		_wheel_mud = Sfx.attach_loop(tr, "wheel_mud_loop", -80.0, float(vc.get("radius", 45.0)))
		if _wheel == null:
			return
	var speed := float(body.get("_drive_speed"))
	var ref := float(vc.get("ref_speed", 2.0))
	var k := clampf(speed / ref, 0.0, 1.3)
	_surf_t -= delta
	if _surf_t <= 0.0:
		_surf_t = 0.8
		var ex: Array = [(body as CollisionObject3D).get_rid(), (tr as CollisionObject3D).get_rid()] if tr is CollisionObject3D else []
		_surface = Perception.surface_at(body, tr.global_position, ex)
	var soft := _surface in (vc.get("soft", ["mud", "snow", "straw"]) as Array)
	_mud_mix = move_toward(_mud_mix, 1.0 if soft else 0.0, delta)
	var base := float(vc.get("wheel_volume_db", -6.0))
	var gain := linear_to_db(maxf(k, 0.001))
	for pair in [[_wheel, 1.0 - _mud_mix], [_wheel_mud, _mud_mix]]:
		var p := pair[0] as AudioStreamPlayer3D
		if p == null:
			continue
		var w: float = pair[1]
		p.pitch_scale = clampf(0.55 + 0.45 * k, 0.55, 1.2)
		p.stream_paused = speed < 0.08 or w < 0.02 or not _near
		Sfx.set_loop_db(p, base + gain + linear_to_db(maxf(w, 0.001)))
	_hooves()
	if not _near:
		return
	var moving := speed > 0.2
	if moving:
		_clack_t -= delta * k
		if _clack_t <= 0.0:
			_clack_t = _rng.randf_range(float(vc["clack_every"][0]), float(vc["clack_every"][1]))
			if not soft:
				Sfx.play("wheel_clack", tr.global_position, linear_to_db(maxf(k, 0.2)))
		_jingle_t -= delta
		if _jingle_t <= 0.0:
			_jingle_t = _rng.randf_range(float(vc["jingle_every"][0]), float(vc["jingle_every"][1])) / maxf(k, 0.5)
			Sfx.play("harness_jingle", body.global_position + Vector3(0, 1.3, 0))
		_creak_t -= delta
		if _creak_t <= 0.0:
			_creak_t = _rng.randf_range(float(vc["creak_every"][0]), float(vc["creak_every"][1]))
			Sfx.play("cart_creak", tr.global_position + Vector3(0, 0.8, 0))
	_hoo_cd -= delta
	var blocked := float(body.get("_blocked_t")) > 0.5
	if blocked and not _was_blocked and _hoo_cd <= 0.0:
		_hoo_cd = float(vc.get("hoo_cooldown", 12.0))
		Sfx.play("coachman_hoo", tr.global_position + Vector3(0, 2.0, 0))
		if _rng.randf() < 0.5:
			Sfx.play("horse_snort", body.global_position + Vector3(0, 1.4, 0))
	_was_blocked = blocked


# ------------------------------------------------------------------ small animals

func _critter(delta: float) -> void:
	_calls(delta)
	if not _near:
		if _purr:
			_purr.stream_paused = true
		return
	var player := get_tree().get_first_node_in_group("player") as Node3D
	if player == null:
		return
	var d := player.global_position.distance_to(body.global_position)
	var pv := Vector2(player.get("velocity").x, player.get("velocity").z).length() if player is CharacterBody3D else 0.0
	var ac: Dictionary = cfg("animals").get(kind, {})
	match kind:
		"dog":
			_growl_cd -= delta
			if d < float(ac.get("growl_dist", 4.0)) and _growl_cd <= 0.0 and str(body.get("follow")) == "":
				_growl_cd = 18.0
				Sfx.play("dog_growl", body.global_position + Vector3(0, 0.4, 0))
			var sp := Vector2(body.get("velocity").x, body.get("velocity").z).length() if body is CharacterBody3D else 0.0
			if sp > float(ac.get("pant_speed", 2.0)) and _rng.randf() < delta * 0.25:
				Sfx.play("dog_pant", body.global_position + Vector3(0, 0.4, 0))
		"cat":
			var want := d < float(ac.get("purr_dist", 1.8)) and pv < 0.5
			if want and _purr == null:
				_purr = Sfx.attach_loop(body, "cat_purr", -14.0, 6.0, Vector3(0, 0.25, 0))
			if _purr:
				_purr.stream_paused = not want
		"bird":
			_flap_cd -= delta
			if not _crow and d < float(ac.get("flap_dist", 3.0)) and pv > 2.2 and _flap_cd <= 0.0:
				_flap_cd = 8.0
				Sfx.play("pigeon_flap", body.global_position + Vector3(0, 0.3, 0))
