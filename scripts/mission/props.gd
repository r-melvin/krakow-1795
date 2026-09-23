extends RefCounted
## Small mission props built in Godot until Blender versions exist. `bundle()` prefers assets/models/bundle.glb.

static var _burlap: StandardMaterial3D
static var _twine: StandardMaterial3D
static var _paper: StandardMaterial3D


## A bundle of pamphlets: burlap-wrapped block, crossed twine, a loose printed sheet tucked under the cord.
## About 0.5 x 0.28 x 0.36 m, origin at the bottom centre.
static func bundle() -> Node3D:
	if ResourceLoader.exists("res://assets/models/bundle.glb"):
		var n := Assets.instance("bundle")
		if n:
			return n
	_materials()
	var root := Node3D.new()
	root.name = "Bundle"
	var size := Vector3(0.5, 0.28, 0.36)
	_box(root, size, Vector3(0, size.y * 0.5, 0), _burlap)
	# twine, both ways round
	_box(root, Vector3(size.x + 0.012, size.y + 0.012, 0.022), Vector3(0, size.y * 0.5, 0), _twine)
	_box(root, Vector3(0.022, size.y + 0.012, size.z + 0.012), Vector3(0.06, size.y * 0.5, 0), _twine)
	# a sheet slipped under the cord on top
	var sheet := _box(root, Vector3(0.21, 0.004, 0.28), Vector3(-0.1, size.y + 0.008, 0.01), _paper)
	sheet.rotation.y = 0.18
	return root


static func _box(parent: Node3D, size: Vector3, pos: Vector3, mat: Material) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	mi.material_override = mat
	mi.position = pos
	parent.add_child(mi)
	return mi


static func _materials() -> void:
	if _burlap:
		return
	_burlap = StandardMaterial3D.new()
	var tex := NoiseTexture2D.new()
	tex.width = 128
	tex.height = 128
	tex.seamless = true
	var noise := FastNoiseLite.new()
	noise.noise_type = FastNoiseLite.TYPE_CELLULAR
	noise.frequency = 0.25
	tex.noise = noise
	var grad := Gradient.new()
	grad.set_color(0, Color(0.33, 0.25, 0.15))
	grad.set_color(1, Color(0.62, 0.5, 0.33))
	tex.color_ramp = grad
	_burlap.albedo_texture = tex
	_burlap.uv1_scale = Vector3(3, 3, 3)
	_burlap.roughness = 1.0
	var nt := NoiseTexture2D.new()
	nt.width = 128
	nt.height = 128
	nt.seamless = true
	nt.as_normal_map = true
	nt.bump_strength = 4.0
	nt.noise = noise
	_burlap.normal_enabled = true
	_burlap.normal_texture = nt
	_twine = StandardMaterial3D.new()
	_twine.albedo_color = Color(0.72, 0.62, 0.42)
	_twine.roughness = 0.95
	_paper = StandardMaterial3D.new()
	_paper.albedo_color = Color(0.86, 0.82, 0.7)
	_paper.roughness = 0.9
