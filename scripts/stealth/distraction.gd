extends RefCounted
## Distractions (docs/STEALTH.md 3.5). Each is a small Node3D with an interactable child (the interact contract of
## scripts/mission/interactable.gd) and talks to the watch coordinator of its world:
##   Stone        thrown by the player (action "throw"): flies a ballistic arc, lands with a sound ring; the nearest
##                guard in earshot walks over and looks about for investigate_secs.
##   LampPost     "douse" a lantern (FlickerLight.douse): the pool goes dark for douse_secs; a guard who notices
##                comes and relights it with his back to the square.
##   RollingBarrel "kick": rolls along the kick direction, rumbling, and stops with a clonk; a guard runs after it.
##   KnockDoor    "knock": a sound; a townsman opens and keeps the guard who comes talking for knock_hold_secs.
##   HorseTether  "untie" the tethered horse: it wanders off, the watch looks, the nearest guard follows it.
## The church bell is a watch call (watch.ring_bell / mask_sound), for missions.

const Perception := preload("res://scripts/stealth/perception.gd")
const Interactable := preload("res://scripts/mission/interactable.gd")
const Walker := preload("res://scripts/npc/walker.gd")


## Base: builds the interactable child.
class Lure extends Node3D:
	func make_ia(display: String, prompt_fn: Callable, handler_fn: Callable, height := 1.9) -> Area3D:
		var ia := Interactable.new()
		ia.display_name = display
		ia.prompt_func = prompt_fn
		ia.handler = handler_fn
		ia.marker_height = height
		ia.set_meta("low_priority", true)   # mission people and props win the interact target (player.gd)
		add_child(ia)
		return ia


## Ballistic launch velocity to land on `target` from `from` (flight time scales with distance).
static func launch_velocity(from: Vector3, target: Vector3, speed: float) -> Vector3:
	var d := target - from
	var flat := Vector2(d.x, d.z).length()
	var t := clampf(flat / maxf(speed * 0.85, 0.1), 0.35, 1.8)
	var g := Stone.GRAVITY
	return Vector3(d.x / t, (d.y + 0.5 * g * t * t) / t, d.z / t)


# ------------------------------------------------------------------ thrown stone

class Stone extends Node3D:
	const GRAVITY := 14.0
	var velocity := Vector3.ZERO
	var loudness := 0.9
	var exclude: Array = []
	var landed := false
	var land_pos := Vector3.ZERO
	var investigator: Node = null
	var _age := 0.0
	var _mesh: MeshInstance3D

	func _ready() -> void:
		_mesh = MeshInstance3D.new()
		var sm := SphereMesh.new()
		sm.radius = 0.05
		sm.height = 0.08
		_mesh.mesh = sm
		var mat := StandardMaterial3D.new()
		mat.albedo_color = Color(0.45, 0.43, 0.4)
		_mesh.material_override = mat
		add_child(_mesh)

	func _physics_process(delta: float) -> void:
		if landed:
			_age += delta
			if _age > 12.0:
				queue_free()
			return
		_age += delta
		var from := global_position
		velocity.y -= GRAVITY * delta
		var to := from + velocity * delta
		var q := PhysicsRayQueryParameters3D.create(from, to)
		var ex: Array[RID] = []
		for e in exclude:
			ex.append(e)
		q.exclude = ex
		var hit := get_world_3d().direct_space_state.intersect_ray(q)
		if not hit.is_empty() or _age > 4.0:
			var p: Vector3 = hit.get("position", to)
			var n: Vector3 = hit.get("normal", Vector3.UP)
			global_position = p + n * 0.04
			_land()
			return
		global_position = to

	func _land() -> void:
		landed = true
		_age = 0.0
		land_pos = global_position
		var ground := land_pos
		var q := PhysicsRayQueryParameters3D.create(land_pos + Vector3(0, 0.2, 0), land_pos - Vector3(0, 20, 0))
		var hit := get_world_3d().direct_space_state.intersect_ray(q)
		if not hit.is_empty():
			ground = hit["position"]
		global_position = ground + Vector3(0, 0.04, 0)
		var w := Perception.watch_of(self)
		if w:
			investigator = w.emit_sound(ground, loudness, "stone", true)


# ------------------------------------------------------------------ lantern dousing

class LampPost extends Lure:
	var light: OmniLight3D          ## a FlickerLight (scripts/city/flicker.gd)
	var claimed_by: Node = null     ## the guard coming to relight it
	var relit_by := ""              ## "guard" | "lamplighter" | "" (smoke)
	var _ia: Area3D

	func _ready() -> void:
		add_to_group("stealth_lamp")
		_ia = make_ia("Lantern", _prompt, _use, 2.0)

	func _prompt() -> String:
		return "douse the lantern" if light and not is_doused() else ""

	func _use(actor: Node) -> bool:
		return douse(actor)

	func douse(actor: Node = null) -> bool:
		if light == null or is_doused():
			return false
		var w := Perception.watch_of(self)
		var secs := float(w.tv("distractions.douse_secs", 30.0)) if w else 30.0
		light.douse(secs)
		claimed_by = null
		relit_by = ""
		if actor != null and actor.get("_figure") != null:
			Assets.play_action(actor.get("_figure"), "wave", 1.3)
		if w:
			w.lamp_changed.emit(self, false)
		return true

	func relight(by: Node = null) -> void:
		if light and is_doused():
			light.relight()
		relit_by = "guard" if by != null else "lamplighter"
		claimed_by = null
		var w := Perception.watch_of(self)
		if w:
			w.lamp_changed.emit(self, true)

	func is_doused() -> bool:
		return light != null and light.has_method("is_doused") and light.is_doused()

	func head_position() -> Vector3:
		return light.global_position if light else global_position + Vector3(0, 2.8, 0)

	## Where a guard stands to reach the wick (between the post and the square: his back to the square).
	func stand_position() -> Vector3:
		var lp := head_position()
		var off := Vector3(lp.x - global_position.x, 0, lp.z - global_position.z)
		if off.length() < 0.1:
			off = Vector3(0.8, 0, 0)
		return global_position + off.normalized() * 0.2 - off.normalized().rotated(Vector3.UP, PI * 0.5) * 0.7


# ------------------------------------------------------------------ rolling barrel

class RollingBarrel extends Lure:
	var prop: Node3D
	var rolling := false
	var roll_dir := Vector3.ZERO
	var speed := 0.0
	var chaser: Node = null
	var rolled := 0.0
	var _rumble := 0.0
	var _ia: Area3D

	func _ready() -> void:
		add_to_group("stealth_barrel")
		prop = Assets.instance("barrel")
		if prop == null:
			prop = MeshInstance3D.new()
			var cm := CylinderMesh.new()
			cm.top_radius = 0.3
			cm.bottom_radius = 0.3
			cm.height = 0.9
			(prop as MeshInstance3D).mesh = cm
			prop.position.y = 0.45
		add_child(prop)
		_ia = make_ia("Barrel", _prompt, _use, 1.4)

	func _prompt() -> String:
		return "" if rolling else "kick the barrel"

	func _use(actor: Node) -> bool:
		var dir := Vector3.ZERO
		if actor is Node3D:
			dir = global_position - (actor as Node3D).global_position
		kick(dir)
		if actor.get("_figure") != null:
			Assets.play_action(actor.get("_figure"), "attack_thrust", 1.4)
		return true

	func kick(dir: Vector3) -> void:
		dir.y = 0.0
		if dir.length() < 0.05:
			dir = -global_transform.basis.z
		roll_dir = dir.normalized()
		var w := Perception.watch_of(self)
		speed = float(w.tv("distractions.barrel_speed", 3.8)) if w else 3.8
		rolling = true
		rolled = 0.0
		_rumble = 0.0
		# on its side: the barrel's own axis (Y) lies across the roll direction
		var axis := roll_dir.cross(Vector3.UP).normalized()
		prop.basis = Basis(roll_dir, axis, roll_dir.cross(axis)).orthonormalized()
		prop.position = Vector3(0, 0.3, 0) - axis * 0.45

	func _physics_process(delta: float) -> void:
		if not rolling:
			return
		var step := roll_dir * speed * delta
		var from := global_position + Vector3(0, 0.3, 0)
		var q := PhysicsRayQueryParameters3D.create(from, from + roll_dir * (0.45 + step.length()))
		var ex: Array[RID] = []
		for c in prop.find_children("*", "CollisionObject3D", true, false):
			ex.append((c as CollisionObject3D).get_rid())
		q.exclude = ex
		var hit := get_world_3d().direct_space_state.intersect_ray(q)
		if not hit.is_empty():
			if hit.get("collider") is CharacterBody3D:
				speed *= 0.5
			else:
				var n: Vector3 = hit["normal"]
				n.y = 0.0
				roll_dir = roll_dir.bounce(n.normalized()).normalized() if n.length() > 0.1 else -roll_dir
				speed *= 0.55
				step = Vector3.ZERO
		global_position += step
		rolled += step.length()
		var ax := prop.basis.y.normalized()
		var centre := prop.position + ax * 0.45
		var sgn := signf(roll_dir.cross(Vector3.UP).dot(ax))
		if step.length() > 0.0001:
			prop.basis = (Basis(ax, -sgn * step.length() / 0.3) * prop.basis).orthonormalized()
		prop.position = centre - prop.basis.y.normalized() * 0.45
		speed = maxf(0.0, speed - 0.55 * delta - speed * 0.12 * delta)
		_rumble -= delta
		var w := Perception.watch_of(self)
		if _rumble <= 0.0 and w:
			_rumble = 0.6
			w.emit_sound(global_position, 0.45, "barrel", false, true, false)
		if speed < 0.25:
			rolling = false
			if w:
				chaser = w.emit_sound(global_position, float(w.tv("distractions.barrel_loudness", 0.9)), "barrel", true)


# ------------------------------------------------------------------ knocking on a door

class KnockDoor extends Lure:
	var model := "npc_m_03"         ## who answers
	var lines: Array = ["Kto tam? ...Panie żołnierzu?", "Was wollen Sie? Es ist Nacht!", "Nikogo nie widziałem."]
	var knocked := false
	var opener: Node3D = null
	var holding: Node = null
	var _open_left := 0.0
	var _ia: Area3D

	func _ready() -> void:
		add_to_group("knock_door")
		_ia = make_ia("Door", _prompt, _use, 2.1)

	func _prompt() -> String:
		return "" if knocked else "knock on the door"

	func _use(_actor: Node) -> bool:
		return knock()

	func knock() -> bool:
		if knocked:
			return false
		knocked = true
		var w := Perception.watch_of(self)
		if w:
			var g: Node = w.emit_sound(global_position, float(w.tv("distractions.knock_loudness", 0.8)), "knock", true)
			if g:
				g.task["door"] = self
		get_tree().create_timer(1.6, false).timeout.connect(_open)
		return true

	func _open() -> void:
		if not is_inside_tree():
			return
		opener = Assets.character(model)
		if opener == null:
			opener = Node3D.new()
		add_child(opener)
		opener.position = Vector3(0, 0, -0.1)
		Assets.play(opener, "idle")
		Walker.speech(self, str(lines[0]), 2.5, 2.1)
		_open_left = 6.0         # nobody comes: he grumbles and shuts it again

	func is_open() -> bool:
		return opener != null and is_instance_valid(opener)

	func stand_position() -> Vector3:
		return global_transform * Vector3(0, 0, 1.4)

	func guard_arrived(g: Node) -> void:
		holding = g
		var w := Perception.watch_of(self)
		_open_left = float(w.tv("distractions.knock_hold_secs", 10.0)) if w else 10.0
		if not is_open():
			_open()
			_open_left = float(w.tv("distractions.knock_hold_secs", 10.0)) if w else 10.0
		Walker.speech(self, str(lines[1 + randi() % 2]), 3.0, 2.1)

	func _process(delta: float) -> void:
		if not is_open():
			return
		if opener.has_meta("anim"):
			Assets.play(opener, "talk_gesture_a" if holding else "idle")
		_open_left -= delta
		if _open_left <= 0.0:
			opener.queue_free()
			opener = null
			holding = null
			get_tree().create_timer(20.0, false).timeout.connect(func() -> void: knocked = false)


# ------------------------------------------------------------------ the tethered horse

class HorseTether extends Lure:
	var horse: Node3D               ## an animal.gd body (behaviour "stand", tether)
	var loose := false
	var _ia: Area3D

	func _ready() -> void:
		add_to_group("stealth_horse")
		_ia = make_ia("Horse", _prompt, _use, 2.2)

	func _prompt() -> String:
		return "" if loose or horse == null or not is_instance_valid(horse) else "untie the horse"

	func _use(_actor: Node) -> bool:
		return untie()

	func untie() -> bool:
		if loose or horse == null or not is_instance_valid(horse):
			return false
		loose = true
		var w := Perception.watch_of(self)
		horse.set("behaviour", "wander")
		horse.set("tether", false)
		horse.set("radius", float(w.tv("distractions.horse_wander_radius", 9.0)) if w else 9.0)
		horse.set("speed", 1.3)
		horse.set("_pause", 0.1)
		if w:
			var g: Node = w.emit_sound(horse.global_position, float(w.tv("distractions.horse_loudness", 1.2)), "horse", true)
			if g:
				g.follow_node(horse, float(w.tv("distractions.investigate_secs", 8.0)))
			for o in w.awake_guards():
				if o != g and o.global_position.distance_to(horse.global_position) < 20.0:
					o.look_toward(horse, 3.0)
		return true

	func _process(_d: float) -> void:
		if horse and is_instance_valid(horse) and not loose:
			global_position = horse.global_position
