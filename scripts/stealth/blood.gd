extends RefCounted
## Blood (docs/STEALTH.md "Kit"): brutal, not cartoonish. `Blood.wound(victim, from_pos, strength)` is called for a
## knife slash or stab, a pistol or musket ball, a bayonet, a sabre cut, a lethal takedown (never for a cudgel, cosh
## or choke). It makes:
##   - a short spray (GPUParticles3D, one shot) from the wound, away from the blow
##   - splatter quads (flat, alpha-textured, glossy) on the ground under the victim and on a wall behind him (raycast along the blow, within 2.5 m):
##     dark red, glossy, random rotation and size; snow takes it harder (bigger, darker); they fade over
##     blood.fade_game_hours (3 game hours at phases.game_minutes_per_sec) and are in group "blood_splat"
##   - a stain on the victim's coat (a Decal on the chest bone that follows the body)
## `Blood.stain_weapon(prop)` reddens the player's knife (a material overlay that fades over blood.weapon_secs).
## A guard who sees a splat within blood.notice_dist goes Curious and walks over (guard.investigate, source "blood");
## the watch is told through watch.report_blood(pos) if a later watch has it. Numbers in data/stealth.json "blood".

const Perception := preload("res://scripts/stealth/perception.gd")

static var _tex: Array = []
static var _drop: Texture2D


static func tb(key: String, fb: float) -> float:
	return float(Perception.tg("blood." + key, fb))


## Irregular splatter textures (a few variants): a pooled core with a ragged, noisy edge, elongated satellite drops
## flung one way, a streak, a darker rim where it dries. Alpha carries the shape, RGB the blood.
static func splat_texture(i: int) -> Texture2D:
	if _tex.is_empty():
		for v in 4:
			var n := 128
			var img := Image.create(n, n, false, Image.FORMAT_RGBA8)
			img.fill(Color(0, 0, 0, 0))
			var rng := RandomNumberGenerator.new()
			rng.seed = 1795 + v * 31
			var noise := FastNoiseLite.new()
			noise.seed = v * 7 + 3
			noise.frequency = 0.09
			var fling := rng.randf() * TAU
			var fdir := Vector2(cos(fling), sin(fling))
			# [centre, radius, stretch along fling]
			var blobs: Array = [[Vector2(64, 64) - fdir * 6.0, rng.randf_range(15, 22), 1.3]]
			for k in rng.randi_range(4, 7):
				blobs.append([Vector2(64, 64) + fdir.rotated(rng.randf_range(-0.6, 0.6)) * rng.randf_range(14, 26), rng.randf_range(5, 9), 1.6])
			for k in rng.randi_range(12, 22):
				var a := fling + rng.randf_range(-1.0, 1.0) * (1.2 if rng.randf() < 0.7 else PI)
				var d := rng.randf_range(24, 58)
				blobs.append([Vector2(64, 64) + Vector2(cos(a), sin(a)) * d, rng.randf_range(1.2, 3.6) * (1.0 - d / 90.0) + 0.8, 2.2])
			for y in n:
				for x in n:
					var p := Vector2(x, y)
					var a := 0.0
					for b in blobs:
						var off: Vector2 = p - b[0]
						var along := off.dot(fdir) / float(b[2])
						var across := off.dot(fdir.orthogonal())
						var dd := Vector2(along, across).length() / float(b[1])
						dd += noise.get_noise_2d(x, y) * 0.35
						a = maxf(a, clampf((1.0 - dd) * 6.0, 0.0, 1.0))
					if a > 0.0:
						var shade := 0.75 + 0.25 * noise.get_noise_2d(x * 3.0, y * 3.0)
						var rim := 1.0 - clampf(a * 1.4 - 0.4, 0.0, 1.0) * 0.35
						img.set_pixel(x, y, Color(0.42 * shade * rim, 0.03 * shade, 0.025 * shade, a))
			img.generate_mipmaps()
			_tex.append(ImageTexture.create_from_image(img))
	return _tex[i % _tex.size()]


static func _drop_tex() -> Texture2D:
	if _drop == null:
		var img := Image.create(16, 16, false, Image.FORMAT_RGBA8)
		for y in 16:
			for x in 16:
				var d := Vector2(x - 7.5, y - 7.5).length() / 7.5
				img.set_pixel(x, y, Color(1, 1, 1, clampf(1.0 - d, 0.0, 1.0)))
		_drop = ImageTexture.create_from_image(img)
	return _drop


## A wound on `victim` from a blow struck at `from_pos`. `strength` 0.5 (slash) .. 1.5 (a ball at close range).
## Returns the splats made.
static func wound(victim: Node3D, from_pos: Vector3, strength: float = 1.0) -> Array:
	if victim == null or not victim.is_inside_tree():
		return []
	var parent := victim.get_parent()
	var chest := victim.global_position + Vector3(0, 1.2, 0)
	var dir := chest - from_pos
	dir.y = 0.0
	dir = dir.normalized() if dir.length() > 0.01 else -victim.global_transform.basis.z
	_spray(parent, chest, dir, strength)
	var out: Array = []
	var space := victim.get_world_3d().direct_space_state
	var ex: Array[RID] = []
	if victim is CollisionObject3D:
		ex.append((victim as CollisionObject3D).get_rid())
	# the ground: where he stood (a falling body lands beyond it)
	var g_at := victim.global_position + dir * randf_range(-0.35, 0.15)
	var q := PhysicsRayQueryParameters3D.create(g_at + Vector3(0, 1.0, 0), g_at - Vector3(0, 3.0, 0))
	q.exclude = ex
	var hit := space.intersect_ray(q)
	if not hit.is_empty():
		out.append(splat(parent, hit["position"], hit["normal"], 0.8 * strength + 0.45, _surface(victim, hit["position"])))
	# a wall behind him
	var qw := PhysicsRayQueryParameters3D.create(chest, chest + (dir + Vector3(0, randf_range(-0.25, 0.1), 0)).normalized() * 2.5)
	qw.exclude = ex
	var hw := space.intersect_ray(qw)
	if not hw.is_empty() and absf((hw["normal"] as Vector3).y) < 0.6 and not (hw.get("collider") is CharacterBody3D):
		out.append(splat(parent, hw["position"], hw["normal"], 0.6 * strength + 0.3, ""))
	_stain(victim)
	return out


static func _surface(n: Node3D, at: Vector3) -> String:
	return Perception.surface_at(n, at + Vector3(0, 0.1, 0), [])


static func _spray(parent: Node, at: Vector3, dir: Vector3, strength: float) -> void:
	var p := GPUParticles3D.new()
	p.one_shot = true
	p.amount = int(28 * strength) + 10
	p.lifetime = 0.7
	p.explosiveness = 0.92
	p.local_coords = false
	var pm := ParticleProcessMaterial.new()
	pm.direction = (dir + Vector3(0, 0.25, 0)).normalized()
	pm.spread = 22.0
	pm.initial_velocity_min = 1.8 * strength
	pm.initial_velocity_max = 4.2 * strength
	pm.gravity = Vector3(0, -9.8, 0)
	pm.scale_min = 0.5
	pm.scale_max = 1.3
	pm.color = Color(0.32, 0.015, 0.015)
	p.process_material = pm
	var qm := QuadMesh.new()
	qm.size = Vector2(0.035, 0.035)
	var mat := StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	mat.vertex_color_use_as_albedo = true
	mat.albedo_texture = _drop_tex()
	mat.roughness = 0.25
	qm.material = mat
	p.draw_pass_1 = qm
	parent.add_child(p)
	p.global_position = at
	p.emitting = true
	p.get_tree().create_timer(2.0, false).timeout.connect(p.queue_free)


## A splatter decal at `at` facing out along `normal`. `surface` "snow" soaks it bigger and darker.
static func splat(parent: Node, at: Vector3, normal: Vector3, size: float, surface: String = "") -> Node3D:
	var s := Splat.new()
	var snow := surface == "snow"
	s.size_m = size * (1.5 if snow else 1.0) * randf_range(0.8, 1.25)
	s.strong = snow
	parent.add_child(s)
	s.global_position = at
	# point the decal's -Y (its projection) into the surface
	var n := normal.normalized() if normal.length() > 0.1 else Vector3.UP
	var up := n
	var side := up.cross(Vector3.FORWARD if absf(up.dot(Vector3.FORWARD)) < 0.9 else Vector3.RIGHT).normalized()
	var fwd := side.cross(up).normalized()
	s.global_basis = Basis(side, up, fwd) * Basis(Vector3.UP, randf() * TAU)
	return s


## A dark stain on the coat: a small decal riding the chest bone.
static func _stain(victim: Node3D) -> void:
	var fig: Node3D = victim.get("_figure") as Node3D
	if fig == null or fig.has_meta("blood_stain"):
		return
	var sks := fig.find_children("*", "Skeleton3D", true, false)
	if sks.is_empty():
		return
	var sk: Skeleton3D = sks[0]
	var bone := "spine_03" if sk.find_bone("spine_03") >= 0 else ("spine_02" if sk.find_bone("spine_02") >= 0 else "")
	if bone == "":
		return
	var ba := BoneAttachment3D.new()
	ba.bone_name = bone
	sk.add_child(ba)
	var d := Decal.new()
	d.size = Vector3(0.34, 0.5, 0.34)
	d.texture_albedo = splat_texture(randi())
	d.modulate = Color(0.55, 0.05, 0.04, 0.95)
	d.cull_mask = 0xFFFFF
	d.rotation = Vector3(PI * 0.5, 0, randf() * TAU)
	ba.add_child(d)
	fig.set_meta("blood_stain", d)


## The player's blade takes the blood: a red overlay on the knife that fades.
static func stain_weapon(prop: Node3D) -> void:
	if prop == null or not is_instance_valid(prop):
		return
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.35, 0.02, 0.02, 0.85)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.roughness = 0.2
	for mi in prop.find_children("*", "MeshInstance3D", true, false):
		(mi as MeshInstance3D).material_overlay = mat
	prop.set_meta("blood", true)
	var tw := prop.create_tween()
	tw.tween_property(mat, "albedo_color:a", 0.0, tb("weapon_secs", 60.0))


## One splatter on the ground or a wall; fades out over a few game hours; a guard who sees it comes to look.
class Splat extends Node3D:
	var size_m := 0.8
	var strong := false
	var noticed := false
	var age := 0.0
	var life := 180.0
	var quad: MeshInstance3D
	var mat: StandardMaterial3D
	var _check := 0.0

	func _ready() -> void:
		add_to_group("blood_splat")
		# a flat quad just off the surface (renders the same in every viewport); a Decal would wrap corners better but
		# is not drawn in the sandbox SubViewports the smoke captures use
		quad = MeshInstance3D.new()
		var qm := QuadMesh.new()
		qm.size = Vector2(size_m, size_m)
		qm.orientation = PlaneMesh.FACE_Y
		quad.mesh = qm
		quad.position.y = 0.006
		quad.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mat = StandardMaterial3D.new()
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		mat.albedo_texture = Blood_tex()
		mat.albedo_color = Color(1, 1, 1, 1) if not strong else Color(0.8, 0.7, 0.7, 1)
		mat.roughness = 0.3
		mat.metallic_specular = 0.45
		mat.cull_mode = BaseMaterial3D.CULL_DISABLED
		quad.material_override = mat
		add_child(quad)
		var gmps := float(Perception.tg("phases.game_minutes_per_sec", 1.0))
		life = float(Perception.tg("blood.fade_game_hours", 3.0)) * 60.0 / maxf(gmps, 0.01)

	func Blood_tex() -> Texture2D:
		return load("res://scripts/stealth/blood.gd").splat_texture(randi())

	func _process(delta: float) -> void:
		age += delta
		var k := clampf(1.0 - (age - life * 0.6) / (life * 0.4), 0.0, 1.0)
		mat.albedo_color.a = k
		if age > life:
			queue_free()
			return
		if noticed:
			return
		_check -= delta
		if _check > 0.0:
			return
		_check = 0.5
		var w := Perception.watch_of(self)
		if w == null:
			return
		for g in w.awake_guards():
			if g.global_position.distance_to(global_position) < float(Perception.tg("blood.notice_dist", 8.0)) \
					and g.can_see_point(global_position + Vector3(0, 0.1, 0)):
				noticed = true
				if w.has_method("report_blood"):
					w.report_blood(global_position)
				elif g.has_method("investigate"):
					g.investigate(global_position, 6.0, "blood")
				return
