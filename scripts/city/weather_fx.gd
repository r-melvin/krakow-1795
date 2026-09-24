extends Node3D
## Weather detail around the accumulated state of scripts/city/weather.gd (a child of the Weather node):
##  - mist: FogVolume boxes on assets/shaders/mist_volume.gdshader over the square (ground mist), the moat, the
##    Vistula and Old Vistula, the yards and St Mary's churchyard, drifting with the wind and scaled by the global
##    `mist` (thicker toward dawn, in the fog preset); brazier smoke volumes that pool downwind of the fire.
##  - lantern haloes: flame lights' volumetric-fog energy rises with the mist (base kept in meta "weather_fog_base").
##  - breath: a few one-shot puffs bound to the nearest characters (player, townsfolk, watch) in frost.
##  - eaves: melt-water drips under the nearest eaves while the roofs melt or it rains; snow sliding off in a burst
##    when the roof cover drops fast (Weather.event "roof_slide" for the audio owner).
##  - tracks: walkers stamp a 256x256 R-float map over the square (global `track_map`) with the snowfall total at the
##    time, so the ground shader fills old tracks in again while it snows.
## `--no-weather-fx` skips all of this (perf comparison).

const MIST_SHADER := "res://assets/shaders/mist_volume.gdshader"
const TRACK_RES := 256
const TRACK_RECT := Rect2(-48, -48, 96, 96)
const BREATH_POOL := 8
const DRIP_POOL := 6

var weather: Node3D
var _noise: NoiseTexture3D
var _mist_shader: Shader
var _volumes: Array = []
var _eaves: Array = []               ## [position (eave line centre), along (unit), out (unit), width]
var _drips: Array = []
var _shed: GPUParticles3D
var _breath: Array = []              ## [GPUParticles3D, bound character, next time]
var _track_img: Image
var _track_tex: ImageTexture
var _track_dirty := false
var _t := 0.0
var _t_breath := 0.0
var _t_track := 0.0
var _t_track_up := 0.0
var _t_eaves := 0.0
var _t_halo := 0.0
var _next_shed := 0.0
var _last_cover := -1.0
var _step_side := 1.0


func _ready() -> void:
	name = "WeatherFX"
	_mist_shader = load(MIST_SHADER)
	_noise = NoiseTexture3D.new()
	_noise.width = 64
	_noise.height = 64
	_noise.depth = 64
	_noise.seamless = true
	var fn := FastNoiseLite.new()
	fn.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	fn.frequency = 0.045
	fn.fractal_octaves = 3
	_noise.noise = fn
	_build_mist()
	_build_breath()
	_build_eave_fx()
	_build_tracks()
	get_tree().create_timer(3.0, false).timeout.connect(_late)


func _late() -> void:
	if not is_inside_tree():
		return
	_find_eaves()
	_build_smoke()


# ------------------------------------------------------------------ mist and smoke

func _volume(nm: String, centre: Vector3, size: Vector3, dens: float, params: Dictionary = {}) -> FogVolume:
	var v := FogVolume.new()
	v.name = "Mist_" + nm
	v.shape = RenderingServer.FOG_VOLUME_SHAPE_BOX
	v.size = size
	v.position = centre
	var m := ShaderMaterial.new()
	m.shader = _mist_shader
	m.set_shader_parameter("noise_tex", _noise)
	m.set_shader_parameter("density", dens)
	for k in params:
		m.set_shader_parameter(k, params[k])
	v.material = m
	add_child(v)
	_volumes.append(v)
	return v


func _build_mist() -> void:
	# the square: a knee-high ground mist
	_volume("square", Vector3(0, 0.9, 0), Vector3(96, 2.2, 96), 0.12, {"scale": 0.07})
	# the frozen moat round the walls
	var moat := {"albedo": Color(0.78, 0.82, 0.88), "scale": 0.05, "height_power": 1.3}
	_volume("moat_n", Vector3(0, 1.0, -109), Vector3(226, 4.0, 10), 0.35, moat)
	_volume("moat_s", Vector3(0, 1.0, 105), Vector3(226, 4.0, 10), 0.35, moat)
	_volume("moat_w", Vector3(-109, 1.0, -2), Vector3(10, 4.0, 206), 0.35, moat)
	_volume("moat_e", Vector3(109, 1.0, -2), Vector3(10, 4.0, 206), 0.35, moat)
	# the Vistula bend and the Old Vistula: river mist, taller and denser
	var river := {"albedo": Color(0.8, 0.84, 0.9), "scale": 0.035, "height_power": 1.2, "drift": 0.8}
	_volume("vistula", Vector3(-145, 1.5, 168), Vector3(176, 6.0, 50), 0.5, river)
	_volume("old_vistula", Vector3(40, 1.5, 134), Vector3(206, 5.0, 18), 0.5, river)
	# yards (data/city_layout.json points.yards) and St Mary's churchyard
	var layout := {}
	var f := FileAccess.open("res://data/city_layout.json", FileAccess.READ)
	if f:
		var parsed: Variant = JSON.parse_string(f.get_as_text())
		if parsed is Dictionary:
			layout = parsed
	var i := 0
	for y in (layout.get("points", {}) as Dictionary).get("yards", []):
		_volume("yard_%d" % i, Vector3(float(y[0]), 1.0, float(y[1])), Vector3(13, 3.0, 13), 0.25, {"scale": 0.1})
		i += 1
	_volume("churchyard", Vector3(38, 1.0, -10), Vector3(15, 3.0, 12), 0.25, {"scale": 0.1})


## Brazier smoke: a low, dense pool leaning downwind of each fire (the Rynek watch braziers, stall fires).
func _build_smoke() -> void:
	var w: Vector2 = weather.get("wind") if weather else Vector2.ZERO
	var lean := Vector3(w.x, 0, w.y).limit_length(1.0) * 2.0
	var n := 0
	for node in get_parent().get_parent().find_children("*", "Node3D", true, false):
		var n3 := node as Node3D
		if not n3.scene_file_path.ends_with("brazier.glb") or n3.global_position.y < -50.0:
			continue
		_volume("smoke_%d" % n, n3.global_position + Vector3(0, 2.4, 0) + lean, Vector3(7, 4.0, 7), 0.5,
				{"base": 0.35, "mist_gain": 0.3, "albedo": Color(0.36, 0.34, 0.32), "scale": 0.18, "height_power": 0.8,
				"drift": 1.0, "emission": Color(0.03, 0.012, 0.0)})
		n += 1
		if n >= 12:
			break


## Flame lights throw stronger haloes in mist.
func _haloes() -> void:
	var m := float(weather.call("_mist_now")) if weather else 0.3
	var k := 1.0 + clampf(m - 0.3, -0.3, 1.2) * 1.1
	for l in get_tree().get_nodes_in_group("flame_lights"):
		var ol := l as Light3D
		if ol == null or not ol.is_inside_tree() or ol.global_position.y < -50.0:
			continue
		if not ol.has_meta("weather_fog_base"):
			ol.set_meta("weather_fog_base", ol.light_volumetric_fog_energy)
		ol.light_volumetric_fog_energy = float(ol.get_meta("weather_fog_base")) * k


# ------------------------------------------------------------------ particles: shared look

func _dot_tex() -> GradientTexture2D:
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.4, 1.0])
	g.colors = PackedColorArray([Color(1, 1, 1, 1), Color(1, 1, 1, 0.6), Color(1, 1, 1, 0)])
	var t := GradientTexture2D.new()
	t.gradient = g
	t.width = 32
	t.height = 32
	t.fill = GradientTexture2D.FILL_RADIAL
	t.fill_from = Vector2(0.5, 0.5)
	t.fill_to = Vector2(1.0, 0.5)
	return t


func _mat(tex: Texture2D, billboard: bool, glow: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
	m.vertex_color_use_as_albedo = true
	m.albedo_texture = tex
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES if billboard else BaseMaterial3D.BILLBOARD_DISABLED
	m.disable_receive_shadows = true
	m.emission_enabled = glow > 0.0
	m.emission = Color(0.62, 0.66, 0.76)
	m.emission_energy_multiplier = glow
	return m


func _ramp(peak: float) -> GradientTexture1D:
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.15, 0.6, 1.0])
	g.colors = PackedColorArray([Color(1, 1, 1, 0), Color(1, 1, 1, peak), Color(1, 1, 1, peak * 0.6), Color(1, 1, 1, 0)])
	var t := GradientTexture1D.new()
	t.gradient = g
	return t


func _curve(a: float, b: float) -> CurveTexture:
	var c := Curve.new()
	c.add_point(Vector2(0, a))
	c.add_point(Vector2(1, b))
	var t := CurveTexture.new()
	t.curve = c
	return t


# ------------------------------------------------------------------ breath

func _build_breath() -> void:
	for i in BREATH_POOL:
		var p := GPUParticles3D.new()
		p.name = "Breath_%d" % i
		p.one_shot = true
		p.emitting = false
		p.amount = 4
		p.lifetime = 1.5
		p.explosiveness = 0.5
		p.local_coords = false
		p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		p.visibility_aabb = AABB(Vector3(-2, -1, -2), Vector3(4, 3, 4))
		var pm := ParticleProcessMaterial.new()
		pm.direction = Vector3(0, 0.15, -1)
		pm.spread = 14.0
		pm.initial_velocity_min = 0.35
		pm.initial_velocity_max = 0.55
		pm.gravity = Vector3(0, 0.08, 0)
		pm.damping_min = 0.3
		pm.damping_max = 0.5
		pm.scale_min = 0.8
		pm.scale_max = 1.2
		pm.scale_curve = _curve(0.35, 2.4)
		pm.color = Color(0.95, 0.96, 1.0, 1.0)
		pm.color_ramp = _ramp(0.22)
		pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
		pm.emission_sphere_radius = 0.03
		p.process_material = pm
		var q := QuadMesh.new()
		q.size = Vector2(0.28, 0.28)
		q.material = _mat(_dot_tex(), true, 0.45)
		p.draw_pass_1 = q
		add_child(p)
		_breath.append([p, null, randf() * 3.0])


func _breath_tick(now: float) -> void:
	var cam: Camera3D = weather.call("view_camera") if weather else get_viewport().get_camera_3d()
	var t := float(weather.get("temperature")) if weather else 0.0
	if cam == null or t > 2.0 or cam.global_position.y < -50.0:
		return
	# the nearest characters within 18 m of the camera, rebound every tick
	var cands: Array = []
	for grp in ["player", "npcs", "guards"]:
		for c in get_tree().get_nodes_in_group(grp):
			var c3 := c as Node3D
			if c3 == null or not c3.is_visible_in_tree():
				continue
			var d := c3.global_position.distance_to(cam.global_position)
			if d < 18.0 and c3.global_position.y > -50.0:
				cands.append([d, c3])
	cands.sort_custom(func(a, b): return a[0] < b[0])
	var bound: Array = []
	for i in mini(cands.size(), BREATH_POOL):
		bound.append(cands[i][1])
	for i in BREATH_POOL:
		var e: Array = _breath[i]
		e[1] = bound[i] if i < bound.size() else null
		if e[1] == null or now < float(e[2]):
			continue
		var ch := e[1] as Node3D
		var head: Vector3 = ch.call("head_position") if ch.has_method("head_position") else ch.global_position + Vector3(0, 1.6, 0)
		var fwd := -ch.global_transform.basis.z
		fwd.y = 0.0
		fwd = fwd.normalized() if fwd.length() > 0.01 else Vector3.FORWARD
		var p := e[0] as GPUParticles3D
		p.global_transform = Transform3D(Basis.looking_at(fwd, Vector3.UP), head + fwd * 0.14 - Vector3(0, 0.07, 0))
		p.restart()
		# faster when running (they pant), colder air shows it longer
		var run := 1.0
		if "velocity" in ch and (ch.get("velocity") as Vector3).length() > 3.0:
			run = 0.5
		e[2] = now + (2.6 + randf() * 1.4) * run


# ------------------------------------------------------------------ eaves: drips and slides

func _build_eave_fx() -> void:
	var streak := GradientTexture2D.new()
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.5, 1.0])
	g.colors = PackedColorArray([Color(1, 1, 1, 0), Color(1, 1, 1, 1), Color(1, 1, 1, 0)])
	streak.gradient = g
	streak.width = 4
	streak.height = 32
	streak.fill_from = Vector2(0.5, 0)
	streak.fill_to = Vector2(0.5, 1)
	for i in DRIP_POOL:
		var p := GPUParticles3D.new()
		p.name = "Drip_%d" % i
		p.amount = 40
		p.lifetime = 1.4
		p.local_coords = false
		p.emitting = false
		p.visible = false
		p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		p.transform_align = GPUParticles3D.TRANSFORM_ALIGN_Z_BILLBOARD_Y_TO_VELOCITY
		p.visibility_aabb = AABB(Vector3(-6, -16, -2), Vector3(12, 18, 4))
		var pm := ParticleProcessMaterial.new()
		pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
		pm.emission_box_extents = Vector3(4, 0.02, 0.05)
		pm.direction = Vector3.DOWN
		pm.spread = 2.0
		pm.initial_velocity_min = 0.2
		pm.initial_velocity_max = 0.6
		pm.gravity = Vector3(0, -9.8, 0)
		pm.color = Color(0.8, 0.86, 0.95, 0.6)
		pm.color_ramp = _ramp(1.0)
		pm.collision_mode = ParticleProcessMaterial.COLLISION_DISABLED
		p.process_material = pm
		var q := QuadMesh.new()
		q.size = Vector2(0.025, 0.22)
		q.material = _mat(streak, false, 0.5)
		p.draw_pass_1 = q
		add_child(p)
		_drips.append(p)
	_shed = GPUParticles3D.new()
	_shed.name = "RoofSlide"
	_shed.one_shot = true
	_shed.emitting = false
	_shed.amount = 180
	_shed.lifetime = 2.2
	_shed.explosiveness = 0.8
	_shed.local_coords = false
	_shed.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_shed.visibility_aabb = AABB(Vector3(-8, -16, -6), Vector3(16, 20, 12))
	var sm := ParticleProcessMaterial.new()
	sm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	sm.emission_box_extents = Vector3(2.5, 0.15, 0.3)
	sm.direction = Vector3(0, -0.3, 1)
	sm.spread = 25.0
	sm.initial_velocity_min = 1.0
	sm.initial_velocity_max = 2.4
	sm.gravity = Vector3(0, -9.8, 0)
	sm.scale_min = 0.3
	sm.scale_max = 1.6
	sm.color = Color(0.95, 0.96, 1.0)
	sm.color_ramp = _ramp(1.0)
	sm.angular_velocity_min = -180
	sm.angular_velocity_max = 180
	_shed.process_material = sm
	var sq := QuadMesh.new()
	sq.size = Vector2(0.24, 0.24)
	sq.material = _mat(_dot_tex(), true, 0.35)
	_shed.draw_pass_1 = sq
	add_child(_shed)


## Eave lines of the square's tenement rows, read from the baked roof snow: in each module's glTF the snow
## vertices right at the front (local +Z beyond the façade) are the roof blanket's lower edge and the cornice cap, so
## their highest point is the eave line (cached per asset).
static var _eave_cache: Dictionary = {}     ## scene path -> Vector3(eave y, front z, half width) or null


func _find_eaves() -> void:
	var district := get_parent().get_parent()
	var portals: Variant = district.get("portals")
	if not (portals is Array):
		return
	var mods: Array = []
	for c in district.get_children():
		var c3 := c as Node3D
		if c3 and c3.scene_file_path.get_file().begins_with("tenement"):
			mods.append(c3)
	for por in portals:
		var centre: Vector3 = por[1]
		var node: Node3D = null
		for c3 in mods:
			if (c3 as Node3D).position.distance_to(centre) < 0.5 and c3.scene_file_path.get_file().get_basename() == str(por[0]):
				node = c3
				break
		if node == null:
			continue
		var e: Variant = _eave_of(node)
		if e == null:
			continue
		var ev: Vector3 = e
		var xf := node.global_transform
		var out := (xf.basis.z).normalized()
		var along := (xf.basis.x).normalized()
		_eaves.append([xf * Vector3(0, ev.x, ev.y) + out * 0.1, along, out, ev.z * 2.0])


func _eave_of(node: Node3D) -> Variant:
	var key := node.scene_file_path
	if _eave_cache.has(key):
		return _eave_cache[key]
	var best_y := -1.0
	var front := -1e9
	var half := 0.0
	var inv := node.global_transform.affine_inverse()
	for mi in node.find_children("*", "MeshInstance3D", true, false):
		var m := (mi as MeshInstance3D).mesh
		if m == null:
			continue
		var to_node: Transform3D = inv * (mi as MeshInstance3D).global_transform
		for si in m.get_surface_count():
			var mat := m.surface_get_material(si)
			if mat == null or not ("snow" in mat.resource_name.to_lower()):
				continue
			var verts: PackedVector3Array = m.surface_get_arrays(si)[Mesh.ARRAY_VERTEX]
			for v in verts:
				var p: Vector3 = to_node * (v as Vector3)
				front = maxf(front, p.z)
				half = maxf(half, absf(p.x))
	if front > -1e8:
		for mi in node.find_children("*", "MeshInstance3D", true, false):
			var m := (mi as MeshInstance3D).mesh
			if m == null:
				continue
			var to_node: Transform3D = inv * (mi as MeshInstance3D).global_transform
			for si in m.get_surface_count():
				var mat := m.surface_get_material(si)
				if mat == null or not ("snow" in mat.resource_name.to_lower()):
					continue
				for v in m.surface_get_arrays(si)[Mesh.ARRAY_VERTEX]:
					var p: Vector3 = to_node * (v as Vector3)
					# the roof slopes back from the eave: any roof snow within 0.8 m of the façade plane (z = 4) is
					# at the eave; balconies and sills sit lower, so the highest of them is the eave line
					if p.z > 3.2 and p.z < 5.0 and p.y > 4.0:
						best_y = maxf(best_y, p.y)
	var r: Variant = Vector3(best_y, 4.35, clampf(half - 0.5, 1.5, 6.0)) if best_y > 0.0 else null
	_eave_cache[key] = r
	return r


func _eave_debug() -> String:
	return str(_eaves.slice(0, 3).map(func(e): return (e[0] as Vector3).snapped(Vector3.ONE * 0.1)))


func _eave_tick(cam_pos: Vector3) -> void:
	if weather == null:
		return
	var roof := float(weather.get("snow_cover"))
	var rate := float(weather.get("roof_rate"))
	var kind := str(weather.get("kind"))
	var inten := float(weather.get("intensity"))
	var a: Dictionary = weather.call("data").get("accumulation", {})
	var drip := clampf(-rate / float(a.get("drip_rate", 0.02)), 0.0, 1.0) * (1.0 if roof > 0.03 else 0.0)
	if kind == "rain" or kind == "sleet":
		drip = maxf(drip, inten * (0.6 if kind == "rain" else 0.3))
	drip = maxf(drip, float(weather.get("wetness")) * 0.25 if float(weather.get("temperature")) > 0.0 else 0.0)
	var near: Array = []
	if drip > 0.02 and cam_pos.y > -50.0:
		for e in _eaves:
			var d := (e[0] as Vector3).distance_to(cam_pos)
			if d < 32.0:
				near.append([d, e])
		near.sort_custom(func(x, y): return x[0] < y[0])
	for i in DRIP_POOL:
		var p: GPUParticles3D = _drips[i]
		if i < near.size():
			var e: Array = near[i][1]
			var al: Vector3 = e[1]
			var ou: Vector3 = e[2]
			p.global_transform = Transform3D(Basis(al, Vector3.UP, ou), e[0])
			(p.process_material as ParticleProcessMaterial).emission_box_extents = Vector3(float(e[3]) * 0.5, 0.02, 0.05)
			p.amount_ratio = clampf(drip, 0.05, 1.0)
			if not p.emitting:
				p.emitting = true
			p.visible = true
		else:
			p.emitting = false
			p.visible = false
	# roofs shed their snow in sheets when the cover drops fast (a thaw, a set_conditions jump)
	var jump := _last_cover - roof if _last_cover >= 0.0 else 0.0
	_last_cover = roof
	var fast := -rate > float(a.get("shed_rate", 0.06))
	if (jump > 0.08 or (fast and _t > _next_shed)) and roof > 0.05:
		shed(cam_pos)
		_next_shed = _t + randf_range(5.0, 12.0) / clampf(-rate / 0.06, 1.0, 4.0)


## A sheet of snow sliding off the nearest suitable eave (in view distance). Returns false when there is none.
func shed(near: Vector3) -> bool:
	var best: Array = []
	var best_d := 40.0
	for e in _eaves:
		var d := (e[0] as Vector3).distance_to(near) + randf() * 8.0
		if d < best_d and d > 4.0:
			best_d = d
			best = e
	if best.is_empty():
		return false
	var al: Vector3 = best[1]
	var ou: Vector3 = best[2]
	var pos: Vector3 = best[0] + al * randf_range(-2.5, 2.5)
	_shed.global_transform = Transform3D(Basis(al, Vector3.UP, ou), pos)
	_shed.restart()
	if weather and weather.has_signal("event"):
		weather.emit_signal("event", "roof_slide", pos)
	return true


# ------------------------------------------------------------------ tracks

func _build_tracks() -> void:
	_track_img = Image.create(TRACK_RES, TRACK_RES, false, Image.FORMAT_RF)
	_track_img.fill(Color(0, 0, 0, 0))
	_track_tex = ImageTexture.create_from_image(_track_img)
	RenderingServer.global_shader_parameter_set("track_map", _track_tex.get_rid())
	RenderingServer.global_shader_parameter_set("track_rect",
			Vector4(TRACK_RECT.position.x, TRACK_RECT.position.y, TRACK_RECT.size.x, TRACK_RECT.size.y))


## Stamps one footprint at a world position (value = snowfall total + 1, so 0 stays "no track").
func stamp(pos: Vector3) -> void:
	var uv := (Vector2(pos.x, pos.z) - TRACK_RECT.position) / TRACK_RECT.size
	if uv.x <= 0.0 or uv.y <= 0.0 or uv.x >= 1.0 or uv.y >= 1.0:
		return
	var total := float(weather.get("snowfall_total")) if weather else 0.0
	_track_img.set_pixel(int(uv.x * TRACK_RES), int(uv.y * TRACK_RES), Color(total + 1.0, 0, 0))
	_track_dirty = true


## A test track (shots): footprints every 0.35 m from a to b.
func stamp_line(a: Vector3, b: Vector3) -> void:
	var n := int(a.distance_to(b) / 0.35)
	for i in n + 1:
		stamp(a.lerp(b, float(i) / maxf(n, 1)))


func _track_tick() -> void:
	if weather == null or float(weather.get("ground_cover")) < 0.08:
		return
	for grp in ["player", "npcs", "guards"]:
		for c in get_tree().get_nodes_in_group(grp):
			var c3 := c as Node3D
			if c3 == null or absf(c3.global_position.y) > 1.2:
				continue
			var p := c3.global_position
			var last: Vector3 = c3.get_meta("trk_last", Vector3(1e6, 0, 0))
			if p.distance_to(last) < 0.35:
				continue
			c3.set_meta("trk_last", p)
			var dir := (p - last)
			var side := Vector3(-dir.z, 0, dir.x).normalized() * 0.14 * _step_side if dir.length() < 5.0 else Vector3.ZERO
			_step_side = -_step_side
			stamp(p + side)


# ------------------------------------------------------------------ tick

func _process(delta: float) -> void:
	_t += delta
	var cam: Camera3D = weather.call("view_camera") if weather else get_viewport().get_camera_3d()
	var cam_pos := cam.global_position if cam else Vector3.ZERO
	_t_breath -= delta
	if _t_breath <= 0.0:
		_t_breath = 0.25
		_breath_tick(_t)
	_t_track -= delta
	if _t_track <= 0.0:
		_t_track = 0.2
		_track_tick()
	_t_track_up -= delta
	if _t_track_up <= 0.0 and _track_dirty:
		_t_track_up = 0.5
		_track_dirty = false
		_track_tex.update(_track_img)
	_t_eaves -= delta
	if _t_eaves <= 0.0:
		_t_eaves = 0.5
		_eave_tick(cam_pos)
	_t_halo -= delta
	if _t_halo <= 0.0:
		_t_halo = 1.0
		_haloes()


## Shots: every bound character breathes out now.
func puff_now() -> void:
	for e in _breath:
		e[2] = 0.0
	_breath_tick(_t)


func counts() -> Dictionary:
	var drips := 0
	for p in _drips:
		if (p as GPUParticles3D).emitting:
			drips += 1
	return {"volumes": _volumes.size(), "eaves": _eaves.size(), "drips": drips, "breath": BREATH_POOL, "eave_sample": _eave_debug()}
