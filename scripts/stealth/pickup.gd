extends Node3D
## A world item the player can take with E (a tiny prompt: "pick up a stone"): loose stones, an empty bottle, a
## dropped knife, a downed guard's musket, and wares from a stall (vendor != null). Adds to the player's kit
## (scripts/stealth/kit.gd). Group "kit_pickup".
##
## Stall wares: standing, the prompt buys one (1 coin from the purse, no risk); crouched it steals one. A seller who
## sees the theft (within kit.vendor_see_dist, facing you, clear line) shouts, the watch is told (watch.report: the
## nearest free guard comes looking) and notoriety rises by kit.theft_notoriety. Wares come back after `respawn` s.
##
## Static helpers: `populate(world, centre)` scatters stone piles and bottles on the street near the player
## (street points on the navmesh); `attach_vendors(world)` puts a ware pickup on every food stall of vendors.gd;
## `drop(parent, item, pos)` leaves an item on the ground (disarmed knife, the musket).

const Perception := preload("res://scripts/stealth/perception.gd")
const Interactable := preload("res://scripts/mission/interactable.gd")
const Walker := preload("res://scripts/npc/walker.gd")

const LABELS := {"stone": "a stone", "bottle": "an empty bottle", "coin": "a coin", "food": "something to eat",
		"knife": "your knife", "musket": "the musket", "pistol": "a pistol", "smoke": "a smoke charge", "flash": "a flash charge"}

var item := "stone"
var count := 1
var label := ""                     ## "" = LABELS[item]; for stall wares the vendor's item name
var respawn := 0.0                  ## 0: gone once taken; else back after this many seconds
var vendor: Node3D = null           ## the seller's body (stall wares)
var price := 1
var taken := 0                      ## times taken
var stolen := 0
var _ia: Area3D
var _prop: Node3D
var _away := 0.0


func _ready() -> void:
	add_to_group("kit_pickup")
	if label == "":
		label = str(LABELS.get(item, item))
	if vendor == null:
		_prop = _visual(item, count)
		add_child(_prop)
	_ia = Interactable.new()
	_ia.display_name = ""
	_ia.prompt_func = _prompt
	_ia.handler = _use
	_ia.marker_height = 0.45
	if vendor == null:
		_ia.set_meta("low_priority", true)
	add_child(_ia)
	(_ia.get_child(0) as CollisionShape3D).position.y = 0.2 if vendor == null else 0.0


static func _visual(kind: String, n: int) -> Node3D:
	var root := Node3D.new()
	var path := "res://assets/models/kit_%s.glb" % kind
	if ResourceLoader.exists(path):
		for i in clampi(n, 1, 3):
			var m := Assets.instance("kit_" + kind)
			if m:
				m.position = Vector3(0.09 * i, 0, 0.05 * (i % 2))
				m.rotation.y = i * 1.7
				if kind in ["knife", "musket", "pistol", "bottle"]:
					m.rotation = Vector3(PI * 0.5, i * 1.7, 0)
					m.position.y = 0.04
				root.add_child(m)
		return root
	var mi := MeshInstance3D.new()
	var mat := StandardMaterial3D.new()
	match kind:
		"bottle":
			var cm := CylinderMesh.new()
			cm.top_radius = 0.02
			cm.bottom_radius = 0.04
			cm.height = 0.24
			mi.mesh = cm
			mi.rotation.z = PI * 0.5
			mi.position.y = 0.04
			mat.albedo_color = Color(0.16, 0.3, 0.18)
		"knife", "musket":
			var bm := BoxMesh.new()
			bm.size = Vector3(0.03, 0.02, 0.28 if kind == "knife" else 1.5)
			mi.mesh = bm
			mi.position.y = 0.02
			mat.albedo_color = Color(0.6, 0.6, 0.62) if kind == "knife" else Color(0.4, 0.26, 0.14)
		_:
			var sm := SphereMesh.new()
			sm.radius = 0.06
			sm.height = 0.09
			mi.mesh = sm
			mi.position.y = 0.04
			mat.albedo_color = Color(0.5, 0.48, 0.45)
	mi.material_override = mat
	root.add_child(mi)
	return root


func _process(delta: float) -> void:
	if _away > 0.0:
		_away -= delta
		if _away <= 0.0 and _prop:
			_prop.visible = true


func _player_crouched(actor: Node) -> bool:
	return actor != null and bool(actor.get("is_crouching"))


func _prompt() -> String:
	if _away > 0.0:
		return ""
	if vendor:
		if not is_instance_valid(vendor) or not vendor.visible:
			return ""
		var p := _player()
		if _player_crouched(p):
			return "steal " + label
		if int(GameState.coins) >= price:
			return "buy %s to throw (%d coin)" % [label, price]
		return "steal " + label
	return "pick up " + label


func _player() -> Node3D:
	var w := Perception.watch_of(self)
	return (w.get_player() if w else get_tree().get_first_node_in_group("player")) as Node3D


func _use(actor: Node) -> bool:
	var kit: Node = actor.get("kit") if actor else null
	if kit == null or _away > 0.0:
		return false
	var fig: Node3D = actor.get("_figure")
	if vendor:
		var pay: bool = not _player_crouched(actor) and int(kit.count("coin")) >= price
		if pay:
			kit.take("coin", price)
		else:
			stolen += 1
			_seen_stealing(actor as Node3D)
	kit.add(item, count)
	if kit.is_throwable(item) and not kit.is_throwable(kit.current):
		kit.last_throwable = item
	taken += 1
	if fig:
		Assets.play_action(fig, "stand_to_crouch" if not actor.get("is_crouching") else "crouch_idle", 1.6)
	if Kit_smoke():
		print("[smoke]   kit pickup %s x%d%s" % [item, count, " (stolen)" if vendor and stolen > 0 else ""])
	if respawn > 0.0:
		_away = respawn
		if _prop:
			_prop.visible = false
	else:
		queue_free()
	return true


static func Kit_smoke() -> bool:
	return "--smoke" in OS.get_cmdline_user_args()


## The seller sees the hand in his wares: a shout, the watch told, a little notoriety.
func _seen_stealing(p: Node3D) -> bool:
	if vendor == null or p == null:
		return false
	var eye := vendor.global_position + Vector3(0, 1.55, 0)
	var to := p.global_position + Vector3(0, 1.0, 0) - eye
	var fwd := -vendor.global_transform.basis.z
	var flat := Vector3(to.x, 0, to.z)
	var near := to.length() < float(Perception.tg("kit.vendor_see_dist", 6.0))
	var facing := flat.length() < 1.0 or rad_to_deg(fwd.angle_to(flat.normalized())) < 70.0
	if not (near and facing):
		return false
	Walker.speech(vendor, ["Złodziej! Łapać złodzieja!", "Thief! Stop, thief!"].pick_random(), 2.5, 2.2)
	var w := Perception.watch_of(self)
	if w:
		w.report(p.global_position, vendor)
		var intel: Node = w.get("intel")
		if intel and intel.has_method("add_notoriety"):
			intel.add_notoriety(float(Perception.tg("kit.theft_notoriety", 3.0)), "theft from a stall")
	return true


## Leaves `item` on the ground at `pos`.
static func drop(parent: Node, kind: String, pos: Vector3, n: int = 1) -> Node3D:
	var pk: Node3D = load("res://scripts/stealth/pickup.gd").new()
	pk.item = kind
	pk.count = n
	parent.add_child(pk)
	pk.global_position = pos
	return pk


## Scatters stone piles (3 stones) and bottles on the street round `centre`: points on the navmesh, on the ground.
static func populate(world: Node3D, centre: Vector3, piles: int = 10, bottles: int = 5, radius: float = 45.0) -> int:
	var space := world.get_world_3d().direct_space_state
	var nav := world.get_world_3d().navigation_map
	var rng := RandomNumberGenerator.new()
	rng.seed = 1795
	var made := 0
	var tries := 0
	while made < piles + bottles and tries < 200:
		tries += 1
		var a := rng.randf() * TAU
		var r := sqrt(rng.randf()) * radius
		var pt := centre + Vector3(cos(a) * r, 0, sin(a) * r)
		var snapped := NavigationServer3D.map_get_closest_point(nav, pt)
		if snapped.distance_to(pt) > 1.5 and snapped != Vector3.ZERO:
			pt = snapped
		var q := PhysicsRayQueryParameters3D.create(Vector3(pt.x, centre.y + 12.0, pt.z), Vector3(pt.x, centre.y - 5.0, pt.z))
		var hit := space.intersect_ray(q)
		if hit.is_empty() or (hit["normal"] as Vector3).y < 0.8 or absf((hit["position"] as Vector3).y - centre.y) > 0.8:
			continue
		# near a wall is where a stone would lie: prefer spots with a wall within 3 m
		var wall := false
		for k in 4:
			var d := Vector3(cos(k * PI * 0.5), 0, sin(k * PI * 0.5)) * 3.0
			var hq := PhysicsRayQueryParameters3D.create(hit["position"] + Vector3(0, 0.5, 0), hit["position"] + Vector3(0, 0.5, 0) + d)
			if not space.intersect_ray(hq).is_empty():
				wall = true
				break
		if not wall and tries < 150:
			continue
		var kind := "stone" if made < piles else "bottle"
		drop(world, kind, hit["position"], 3 if kind == "stone" else 1)
		made += 1
	return made


## A ware pickup beside every stationary food / drink stall of vendors.gd (the seller has `heal`, or sells fish).
static func attach_vendors(world: Node3D) -> int:
	var n := 0
	for vs in world.get_tree().get_nodes_in_group("vendors"):
		if not (vs is Node3D) or not Perception.same_world(vs, world):
			continue
		for v in vs.get("vendors"):
			if v.roaming or v.body == null or v.prop == null or v.prop.get_parent() == null:
				continue
			var d: Dictionary = v.d
			if int(d.get("heal", 0)) <= 0 and str(d.get("id", "")) != "ryby":
				continue
			if v.body.has_meta("kit_ware"):
				continue
			v.body.set_meta("kit_ware", true)
			var pk: Node3D = load("res://scripts/stealth/pickup.gd").new()
			pk.item = "food"
			pk.label = str(d.get("item", "some food"))
			pk.vendor = v.body
			pk.respawn = 30.0
			pk.price = 1
			vs.add_child(pk)
			pk.global_position = v.prop.global_position + Vector3(0, 0.3, 0)
			n += 1
	return n
