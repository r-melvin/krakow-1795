extends RefCounted
## Prop verbs for the kit (docs/STEALTH.md "Kit"), attached by `attach_all(world)` to anything that declares them:
##   poison   meta `poisonable` (a tankard, the hot-beer can, a cauldron, the tasting-table cask, a snuffbox): E with a
##            vial in the kit (kit "poison") tips it in (pour_small): meta `poisoned` = true, `poisoned_by` = "player"
##            on the prop and Mission flags `poisoned_by` = <prop name>, `poisoned_<prop name>` = true. The campaign's
##            target scripts read the meta when they drink. Sound hook: Sfx.play("pour") if the audio agent's Sfx has it.
##   ignite   meta `flammable`: E with a tinderbox (kit "tinderbox") kneels 3 s and sets it alight: meta `burning`,
##            node.ignite() if it has one, and Fire.ignite(pos) on the street-life fire system (a node in group
##            "fire" with ignite()). A lit torch does it at once.
##   rig      meta `rig` with `rig_kind` = "drop" (a cargo hook's load, a hanging sign: falls straight down), "roll" (a
##            barrel stack's chock: rolls along meta `rig_dir`, local, default -Z), "release" (the bell rope, a
##            counterweight: swings free with a loud sound). E: a 2 s action arms it (meta `armed` = true); when a
##            body of group "riot_target" or "guards" passes under it (drop / release: within rig_radius of the spot
##            below, roll: in its path within 7 m) the prop becomes a RigidBody3D and falls; anyone it strikes at speed
##            is knocked down (guard.knock_down / npc.knock_down), with a sound event. `trigger()` fires it at once.
##            The rope is worked from meta `rig_at` (local Vector3) or the ground straight below the prop.
## The torch (kit "torch") is lit at any flame light (group "flame_lights") within reach: `Verbs.light_torch(player)`.

const Perception := preload("res://scripts/stealth/perception.gd")
const Interactable := preload("res://scripts/mission/interactable.gd")


static func smoke_on() -> bool:
	return "--smoke" in OS.get_cmdline_user_args()


## Ignites `pos` through the fire system (group "fire" nodes with ignite(pos)) and any `flammable` node given.
static func ignite_at(from: Node, pos: Vector3, target: Node = null) -> bool:
	var any := false
	if target:
		target.set_meta("burning", true)
		if target.has_method("ignite"):
			target.ignite()
		any = true
	for f in from.get_tree().get_nodes_in_group("fire"):
		if f.has_method("ignite") and (not (f is Node3D) or not (from is Node3D) or Perception.same_world(f, from)):
			f.ignite(pos)
			any = true
	return any


## Lights the player's torch from the nearest flame light within 2.2 m. Returns true if lit.
static func light_torch(p: Node3D) -> bool:
	var kit: Node = p.get("kit")
	if kit == null or not kit.has("torch") or kit.torch_lit:
		return false
	for l in p.get_tree().get_nodes_in_group("flame_lights"):
		var ol := l as Node3D
		if ol == null or not Perception.same_world(ol, p) or not ol.visible:
			continue
		if ol.has_method("is_doused") and ol.is_doused():
			continue
		var d := ol.global_position - (p.global_position + Vector3(0, 1.4, 0))
		if Vector2(d.x, d.z).length() < 2.2 and absf(d.y) < 2.2:
			kit.torch_lit = true
			kit.changed.emit()
			return true
	return false


static func _sfx(from: Node, what: String) -> void:
	var sfx := from.get_tree().root.get_node_or_null("Sfx")
	if sfx and sfx.has_method("play"):
		sfx.play(what)


## An interactable for one verb on its parent prop.
class VerbSpot extends Node3D:
	var verb := "poison"            ## poison | ignite | rig
	var target: Node3D
	var busy := 0.0                 ## seconds left of the arming / kindling action
	var actor: Node3D
	var fell: RigidBody3D = null
	var struck: Array = []
	var _ia: Area3D
	var _check := 0.0
	var _fall_t := 0.0
	var _vel := Vector3.ZERO
	var _rest := false

	func _ready() -> void:
		if target == null:
			target = get_parent() as Node3D
		if verb == "rig":
			# the rope is tied off where a hand can reach it: meta `rig_at` (local), else on the ground below the prop
			top_level = true
			var at := target.global_position
			if target.has_meta("rig_at"):
				at = target.to_global(target.get_meta("rig_at"))
			else:
				var q := PhysicsRayQueryParameters3D.create(at, at - Vector3(0, 30, 0))
				var hit := target.get_world_3d().direct_space_state.intersect_ray(q)
				if not hit.is_empty():
					at = hit["position"]
			global_position = at
		_ia = Interactable.new()
		_ia.display_name = ""
		_ia.prompt_func = _prompt
		_ia.handler = _use
		_ia.marker_height = 0.8
		_ia.set_meta("low_priority", true)
		add_child(_ia)

	func _kit() -> Node:
		var w := Perception.watch_of(self)
		var p: Node = w.get_player() if w else get_tree().get_first_node_in_group("player")
		return p.get("kit") if p else null

	func _prompt() -> String:
		if busy > 0.0 or target == null:
			return ""
		var k := _kit()
		match verb:
			"poison":
				if target.get_meta("poisoned", false):
					return ""
				return "tip the vial in" if k == null or k.has("poison") else ""
			"ignite":
				if target.get_meta("burning", false):
					return ""
				if k and (k.has("tinderbox") or (k.current == "torch" and k.torch_lit)):
					return "set it alight"
				return ""
			"rig":
				return "" if target.get_meta("armed", false) or fell else "rig it to fall"
		return ""

	func _use(a: Node) -> bool:
		var kit: Node = a.get("kit") if a else null
		if kit == null or busy > 0.0:
			return false
		actor = a as Node3D
		var fig: Node3D = a.get("_figure")
		match verb:
			"poison":
				if not kit.take("poison"):
					return false
				target.set_meta("poisoned", true)
				target.set_meta("poisoned_by", "player")
				if fig:
					Assets.play_action(fig, "pour_small" if Assets.has_clip(fig, "pour_small") else "talk_gesture_b", 1.0)
				Verbs_sfx(self, "pour")
				if not a.get("sandbox"):
					Mission.set_flag("poisoned_by", str(target.name))
					Mission.set_flag("poisoned_" + str(target.name), true)
				return true
			"ignite":
				if kit.current == "torch" and kit.torch_lit:
					return _light()
				busy = float(Perception.tg("kit.tinder_secs", 3.0))
				a.set("_lock", busy)
				if fig:
					Assets.play_action(fig, "crouch_idle", 1.0, true)
				return true
			"rig":
				busy = float(Perception.tg("kit.rig_secs", 2.0))
				a.set("_lock", busy)
				if fig:
					Assets.play_action(fig, "sweep", 1.0, true)
				return true
		return false

	static func Verbs_sfx(n: Node, what: String) -> void:
		var sfx := n.get_tree().root.get_node_or_null("Sfx")
		if sfx and sfx.has_method("play"):
			sfx.play(what)

	func _light() -> bool:
		var any := false
		target.set_meta("burning", true)
		if target.has_method("ignite"):
			target.ignite()
		for f in get_tree().get_nodes_in_group("fire"):
			if f.has_method("ignite"):
				f.ignite(target.global_position)
				any = true
		var w := Perception.watch_of(self)
		if w:
			w.emit_sound(target.global_position, 0.4, "fire", false, true, true)
		return true

	func _physics_process(delta: float) -> void:
		if busy > 0.0:
			busy -= delta
			if busy <= 0.0:
				busy = 0.0
				if actor and actor.get("_figure"):
					Assets.clear_action(actor.get("_figure"))
				if verb == "ignite":
					_light()
				elif verb == "rig":
					target.set_meta("armed", true)
					if smoke():
						print("[smoke]   kit rig armed %s (%s)" % [target.name, target.get_meta("rig_kind", "drop")])
			return
		if verb != "rig":
			return
		if fell:
			_fall_t += delta
			_move_fell(delta)
			_strike()
			if _fall_t > 6.0:
				set_physics_process(false)
			return
		if not target.get_meta("armed", false):
			return
		_check -= delta
		if _check > 0.0:
			return
		_check = 0.1
		for grp in ["riot_target", "guards"]:
			for n in get_tree().get_nodes_in_group(grp):
				if n is Node3D and Perception.same_world(n, target) and _in_zone(n as Node3D):
					trigger(n)
					return
		# sandbox guards are outside the "guards" group: ask the watch
		var w := Perception.watch_of(self)
		if w:
			for g in w.awake_guards():
				if _in_zone(g):
					trigger(g)
					return

	func smoke() -> bool:
		return "--smoke" in OS.get_cmdline_user_args()

	func _kind() -> String:
		return str(target.get_meta("rig_kind", "drop"))

	func _dir() -> Vector3:
		var d: Variant = target.get_meta("rig_dir", Vector3(0, 0, -1))
		var v: Vector3 = target.global_transform.basis * (d as Vector3)
		v.y = 0.0
		return v.normalized()

	func _in_zone(b: Node3D) -> bool:
		if b.has_method("is_downed") and b.is_downed():
			return false
		var to := b.global_position - target.global_position
		if _kind() == "roll":
			var along := Vector3(to.x, 0, to.z).dot(_dir())
			var off := (Vector3(to.x, 0, to.z) - _dir() * along).length()
			return along > 0.0 and along < 7.0 and off < 0.9 and absf(to.y) < 1.5
		return Vector2(to.x, to.z).length() < float(Perception.tg("kit.rig_radius", 0.8)) and to.y < 0.5

	## Lets the rigged prop go.
	func trigger(by: Node = null) -> void:
		if fell:
			return
		target.set_meta("armed", false)
		var body := RigidBody3D.new()
		body.mass = 60.0
		var cs := CollisionShape3D.new()
		var bs := BoxShape3D.new()
		var ab := _aabb(target)
		bs.size = ab.size.clamp(Vector3(0.2, 0.2, 0.2), Vector3(3, 3, 3))
		cs.shape = bs
		cs.position = ab.get_center() - target.global_position
		body.add_child(cs)
		var parent := target.get_parent()
		var xf := target.global_transform
		parent.add_child(body)
		body.global_transform = Transform3D(Basis.IDENTITY, xf.origin)
		target.reparent(body, true)
		for c in target.find_children("*", "CollisionObject3D", true, false):
			(c as CollisionObject3D).collision_layer = 0
		if target is CollisionObject3D:
			(target as CollisionObject3D).collision_layer = 0
		# a kinematic RigidBody3D driven here (deterministic in any physics space): gravity for drop / release,
		# a decaying roll for roll; it comes to rest on whatever is below or ahead
		body.freeze_mode = RigidBody3D.FREEZE_MODE_KINEMATIC
		body.freeze = true
		match _kind():
			"roll":
				_vel = _dir() * 4.5
			"release":
				_vel = Vector3(randf_range(-1, 1), -1.0, randf_range(-1, 1))
			_:
				_vel = Vector3(0, -1.0, 0)
		fell = body
		_fall_t = 0.0
		if smoke():
			print("[smoke]   kit rig %s fell (%s) under %s" % [target.name, _kind(), by.name if by else "-"])

	func _move_fell(delta: float) -> void:
		if _rest or fell == null or not is_instance_valid(fell):
			return
		var half := 0.3
		for c in fell.get_children():
			if c is CollisionShape3D and (c as CollisionShape3D).shape is BoxShape3D:
				half = ((c as CollisionShape3D).shape as BoxShape3D).size.y * 0.5
		if _kind() == "roll":
			_vel = _vel.move_toward(Vector3.ZERO, 0.8 * delta)
			fell.rotate(_dir().cross(Vector3.UP).normalized(), -_vel.length() * delta / maxf(half, 0.1))
		else:
			_vel.y -= 9.8 * delta
		var from := fell.global_position
		var to := from + _vel * delta
		var q := PhysicsRayQueryParameters3D.create(from, to + _vel.normalized() * half)
		q.exclude = [fell.get_rid()]
		var hit := fell.get_world_3d().direct_space_state.intersect_ray(q)
		if not hit.is_empty() and not (hit.get("collider") is CharacterBody3D):
			fell.global_position = (hit["position"] as Vector3) - _vel.normalized() * half
			_rest = true
			_vel = Vector3.ZERO
			_crash()
			return
		fell.global_position = to
		if _vel.length() < 0.2 and _kind() == "roll":
			_rest = true
			_crash()

	## The crash is what the watch hears (no creak before it, or the victim would stop short).
	func _crash() -> void:
		var w := Perception.watch_of(self)
		if w:
			w.emit_sound(fell.global_position, 0.9 if _kind() == "release" else 0.7, "rig_" + _kind(), false, true, true)

	func _strike() -> void:
		if fell == null or not is_instance_valid(fell) or _rest:
			return
		var pool: Array = []
		var w := Perception.watch_of(self)
		if w:
			pool.append_array(w.awake_guards())
		for grp in ["riot_target", "guards"]:
			for n in get_tree().get_nodes_in_group(grp):
				if not n in pool:
					pool.append(n)
		for b in pool:
			if not (b is Node3D) or b in struck or not Perception.same_world(b, fell):
				continue
			# anywhere along the body (feet to head) within reach of the falling load's centre
			var bp: Vector3 = (b as Node3D).global_position
			var c := fell.global_position
			var along := Vector3(bp.x, clampf(c.y, bp.y, bp.y + 1.8), bp.z)
			if along.distance_to(c) < float(Perception.tg("kit.rig_strike_radius", 1.1)):
				struck.append(b)
				if smoke():
					print("[smoke]   kit rig struck %s" % b.name)
				if b.has_method("knock_down"):
					if b is Guard:
						b.knock_down(float(Perception.tg("kit.rig_down_secs", 90.0)), false)
					else:
						b.knock_down(float(Perception.tg("kit.rig_down_secs", 90.0)))

	static func _aabb(n: Node3D) -> AABB:
		var out := AABB(n.global_position - Vector3(0.3, 0.3, 0.3), Vector3(0.6, 0.6, 0.6))
		var first := true
		for vi in n.find_children("*", "VisualInstance3D", true, false):
			var v := vi as VisualInstance3D
			var ab := v.global_transform * v.get_aabb()
			out = ab if first else out.merge(ab)
			first = false
		if n is VisualInstance3D:
			out = (n as VisualInstance3D).global_transform * (n as VisualInstance3D).get_aabb() if first else out
		return out


## Attaches VerbSpots to everything in `world` with meta poisonable / flammable / rig (or groups "poisonable",
## "flammable", "rig"). Returns how many.
static func attach_all(world: Node) -> int:
	var n := 0
	var found: Array = []
	for g in ["poisonable", "flammable", "rig"]:
		for node in world.get_tree().get_nodes_in_group(g):
			if node is Node3D and world.is_ancestor_of(node):
				found.append([node, g])
	for node in world.find_children("*", "Node3D", true, false):
		for m in ["poisonable", "flammable", "rig"]:
			if node.has_meta(m) and node.get_meta(m):
				found.append([node, m])
	for f in found:
		var node: Node3D = f[0]
		var key := "verb_" + str(f[1])
		if node.has_meta(key):
			continue
		node.set_meta(key, true)
		var s := VerbSpot.new()
		s.verb = {"poisonable": "poison", "flammable": "ignite", "rig": "rig"}[f[1]]
		node.add_child(s)
		n += 1
	return n
