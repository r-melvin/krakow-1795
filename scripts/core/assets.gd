class_name Assets
## Thin loader for Blender-exported glTF. Returns an instanced scene or null if the file is missing.
## glTF export maps Blender (x, y, z) to Godot (x, z, -y): Blender -Y (front) becomes Godot +Z.
## So rot_y=0 faces +Z, PI faces -Z, PI/2 faces +X, -PI/2 faces -X.

static var _cache: Dictionary = {}


static func instance(name: String) -> Node3D:
	var path := "res://assets/models/%s.glb" % name
	if not _cache.has(path):
		_cache[path] = load(path) if ResourceLoader.exists(path) else null
	var ps: PackedScene = _cache[path]
	if ps == null:
		push_warning("Missing asset %s" % path)
		return null
	return ps.instantiate() as Node3D


static func place(parent: Node, name: String, pos: Vector3, rot_y: float = 0.0, scale: float = 1.0) -> Node3D:
	var n := instance(name)
	if n == null:
		return null
	n.position = pos
	n.rotation.y = rot_y
	n.scale = Vector3.ONE * scale
	parent.add_child(n)
	return n
