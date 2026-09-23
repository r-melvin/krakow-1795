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


## Characters come from the MakeHuman pipeline facing +Z, with an AnimationPlayer holding "idle", "walk", "sentry".
## Returns a pivot whose forward is -Z like every other Node3D, with the figure turned inside it.
static func character(name: String) -> Node3D:
	var pivot := Node3D.new()
	pivot.name = name
	var fig := instance(name)
	if fig == null:
		return null
	fig.rotation.y = PI
	pivot.add_child(fig)
	_tune_materials(fig)
	var ap := _find_anim_player(fig)
	if ap:
		for anim_name in ap.get_animation_list():
			ap.get_animation(anim_name).loop_mode = Animation.LOOP_LINEAR
		pivot.set_meta("anim", ap)
	return pivot


## Skin gets subsurface scattering and a softer specular; cloth goes fully rough; strands stay alpha-scissor.
static func _tune_materials(n: Node) -> void:
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		for i in mi.get_surface_override_material_count():
			var mat := mi.get_active_material(i)
			if mat is BaseMaterial3D:
				var bm := mat as BaseMaterial3D
				var nm := bm.resource_name.to_lower()
				if "body" in nm:
					bm.subsurf_scatter_enabled = true
					bm.subsurf_scatter_strength = 0.6
					bm.subsurf_scatter_skin_mode = true
					bm.roughness = 0.62
					bm.metallic_specular = 0.45
				elif nm.begins_with("cloth_"):
					bm.roughness = 0.95
					bm.metallic_specular = 0.2
				elif "eye_shadow" in nm:
					bm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
					bm.cull_mode = BaseMaterial3D.CULL_BACK
	for c in n.get_children():
		_tune_materials(c)


static func _find_anim_player(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var r := _find_anim_player(c)
		if r:
			return r
	return null


## Play a clip on a character pivot if it has one and it is not already playing.
static func play(pivot: Node3D, clip: String, speed: float = 1.0) -> void:
	if pivot == null or not pivot.has_meta("anim"):
		return
	var ap: AnimationPlayer = pivot.get_meta("anim")
	if not ap.has_animation(clip):
		return
	if ap.current_animation != clip:
		ap.play(clip, 0.15)
	ap.speed_scale = speed
