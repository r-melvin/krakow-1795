extends "res://scripts/npc/walker.gd"
## Ambient animal: a static (unrigged) mesh that stands, wanders near its post, or follows a person
## (`"follow": "<npc id>"` in data/npcs.json) a pace behind and to the side. No animation.

var npc_id := "animal"
var candidates: PackedStringArray = []
var behaviour := "stand"
var radius := 3.0
var facing := 0.0
var speed := 0.7
var role := ""
var model_name := ""
var follow := ""                  ## npc_id of the person this animal trots after, "" = none

var _leader: Node3D

var _home: Vector3
var _target: Vector3
var _pause := 0.0
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	add_to_group("animals")
	_rng.seed = hash(npc_id)
	_home = global_position
	_target = _home
	rotation.y = facing
	_pause = _rng.randf_range(0.5, 2.5)
	_build()
	setup_navigation(0.3, 0.6, 4.0)
	nav_agent.avoidance_priority = 0.3   # dogs give way to people
	if follow != "":
		behaviour = "follow"


func _build() -> void:
	for n in candidates:
		if ResourceLoader.exists("res://assets/models/%s.glb" % n):
			model_name = n
			break
	var mesh: Node3D = Assets.instance(model_name) if model_name != "" else null
	var box := AABB(Vector3(-0.2, 0, -0.3), Vector3(0.4, 0.4, 0.6))
	if mesh:
		_strip_collision(mesh)
		mesh.rotation.y = PI       # Blender front -Y lands on +Z; turn to face -Z like other Node3Ds.
		add_child(mesh)
		var b := _merged_aabb(mesh, mesh.transform)
		if b.size != Vector3.ZERO:
			box = b
	else:
		push_warning("Animal %s: no model among %s" % [npc_id, candidates])
	var shape := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = Vector3(maxf(box.size.x, 0.1), maxf(box.size.y, 0.1), maxf(box.size.z, 0.1))
	shape.shape = bs
	shape.position = box.get_center()
	add_child(shape)


## The animal glbs carry a "-col" proxy that imports as a visible box with a StaticBody3D child.
## Drop it: the static body would collide with this moving body, and the body's own box shape replaces it.
func _strip_collision(n: Node) -> void:
	for c in n.get_children():
		if c is StaticBody3D:
			var owner_mesh := n if n is MeshInstance3D else c
			owner_mesh.get_parent().remove_child(owner_mesh)
			owner_mesh.queue_free()
			return
		_strip_collision(c)


func _merged_aabb(n: Node, xf: Transform3D) -> AABB:
	var out := AABB()
	var first := true
	if n is MeshInstance3D and (n as MeshInstance3D).mesh:
		out = xf * (n as MeshInstance3D).mesh.get_aabb()
		first = false
	for c in n.get_children():
		if c is Node3D:
			var b := _merged_aabb(c, xf * (c as Node3D).transform)
			if b.size == Vector3.ZERO:
				continue
			out = b if first else out.merge(b)
			first = false
	return out


func _physics_process(delta: float) -> void:
	match behaviour:
		"follow":
			_follow(delta)
		"wander":
			_wander(delta)


func _follow(delta: float) -> void:
	if _leader == null or not is_instance_valid(_leader):
		_leader = null
		for n in get_tree().get_nodes_in_group("npcs"):
			if n.get("npc_id") == follow:
				_leader = n
				break
		if _leader == null:
			halt(delta)
			return
	# Heel: a little behind and to the left of the leader (leader forward is -Z).
	var b := _leader.global_transform.basis
	var heel := _leader.global_position + b.z * 1.1 - b.x * 0.7
	var gap := Vector2(heel.x - global_position.x, heel.z - global_position.z).length()
	if gap < 0.6 or not _leader.visible:
		halt(delta)
		turn_toward_yaw(_leader.rotation.y, delta)
		return
	walk_to(heel, clampf(gap * 1.3, 0.8, 4.0), delta)


func _wander(delta: float) -> void:
	if _pause > 0.0:
		_pause -= delta
		halt(delta)
		if _pause <= 0.0:
			_pick_target()
	elif walk_to(_target, speed, delta):
		_pause = _rng.randf_range(1.5, 5.0)


func _pick_target() -> void:
	var a := _rng.randf() * TAU
	var r := sqrt(_rng.randf()) * radius
	_target = _home + Vector3(cos(a) * r, 0.0, sin(a) * r)
