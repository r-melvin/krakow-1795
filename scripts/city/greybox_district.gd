extends Node3D

const FlickerLight := preload("res://scripts/city/flicker.gd")
## Rynek Glowny, compressed to ~1/3 scale for play. Built from Blender glTF placed by script.
## Layout (Godot axes, metres): square is 60x60 centred on the origin. +X east, +Z south.
##   Sukiennice in the middle, Town Hall + tower SW, St Mary's NE, St Adalbert's SE.
##   Tenement rows on all four sides with arcaded/portalled ground floors facing the square.
## Blender front (-Y) lands on Godot +Z, so rot_y = 0 faces south, PI north, PI/2 east, -PI/2 west.

const GuardScript := preload("res://scripts/stealth/guard.gd")
const SafeHouseScript := preload("res://scripts/stealth/safe_house.gd")
const PopulationScript := preload("res://scripts/city/population.gd")

const NAV_GROUP := "nav_source"

signal navmesh_ready(polygons: int)

var _ground_mat: StandardMaterial3D
var nav_region: NavigationRegion3D
var _baked := false
var _bake_iteration := 0
var portals: Array = []          ## [asset, centre, rot_y] per tenement module, for door triggers


func _ready() -> void:
	_ground_mat = StandardMaterial3D.new()
	_ground_mat.albedo_color = Color(0.30, 0.28, 0.27)
	_ground_mat.roughness = 0.9
	_environment()
	_ground()
	_landmarks()
	_tenements()
	_furniture()
	_dressing()
	_guards()
	_population()
	_safe_house()
	_navigation()
	_interiors()


func _environment() -> void:
	var env := WorldEnvironment.new()
	var e := Environment.new()
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_top_color = Color(0.02, 0.025, 0.06)
	sm.sky_horizon_color = Color(0.10, 0.09, 0.14)
	sm.ground_bottom_color = Color(0.02, 0.02, 0.03)
	sm.ground_horizon_color = Color(0.08, 0.07, 0.10)
	sm.sun_angle_max = 1.6              # the moon's disc, drawn by the sky from the directional light
	sm.sun_curve = 0.12
	sky.sky_material = sm
	e.background_mode = Environment.BG_SKY
	e.sky = sky
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.18, 0.21, 0.34)
	e.ambient_light_energy = 0.6
	e.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	# ACES rolls lantern hot-spots off instead of clipping them to flat orange.
	e.tonemap_mode = Environment.TONE_MAPPER_ACES
	e.tonemap_exposure = 1.1
	e.tonemap_white = 6.0
	e.ssao_enabled = true
	e.ssao_radius = 1.2
	e.ssao_intensity = 2.0
	# Bounced light (Godot's signed-distance-field GI): lantern light bleeds onto the far side of the street and
	# under awnings instead of dying at the shadow edge. GPU cost, not CPU; toggled by the "gi" setting.
	var gi: bool = GameState.settings.get("gi", true)
	e.sdfgi_enabled = gi
	e.sdfgi_cascades = 4
	e.sdfgi_min_cell_size = 0.35
	e.sdfgi_bounce_feedback = 0.6
	e.sdfgi_read_sky_light = true
	e.sdfgi_energy = 1.2
	e.ssil_enabled = gi
	e.ssil_intensity = 1.5
	# Screen-space reflections: the wet cobbles and lantern glass pick up the windows and lanterns.
	e.ssr_enabled = true
	e.ssr_max_steps = 64
	e.ssr_fade_in = 0.15
	e.ssr_fade_out = 2.0
	e.glow_enabled = true
	e.glow_intensity = 0.45
	e.glow_bloom = 0.10
	e.glow_hdr_threshold = 1.3
	# Thin winter mist: volumetric so the lanterns and windows throw visible cones, plus a faint distance haze.
	e.fog_enabled = true
	e.fog_light_color = Color(0.07, 0.08, 0.13)
	e.fog_density = 0.004
	e.volumetric_fog_enabled = gi
	e.volumetric_fog_density = 0.018
	e.volumetric_fog_albedo = Color(0.75, 0.78, 0.85)
	e.volumetric_fog_emission = Color(0.02, 0.025, 0.04)
	e.volumetric_fog_emission_energy = 0.4
	e.volumetric_fog_anisotropy = 0.55
	e.volumetric_fog_length = 80.0
	e.volumetric_fog_sky_affect = 0.3
	e.adjustment_enabled = true
	e.adjustment_saturation = 1.15
	e.adjustment_contrast = 1.08
	env.environment = e
	add_child(env)

	# Low winter moon: cool, long shadows.
	var moon := DirectionalLight3D.new()
	moon.light_color = Color(0.62, 0.72, 1.0)
	moon.light_energy = 0.45
	moon.rotation_degrees = Vector3(-34, 40, 0)
	moon.shadow_enabled = true
	moon.directional_shadow_max_distance = 120
	moon.light_angular_distance = 0.5
	moon.light_volumetric_fog_energy = 0.4
	add_child(moon)
	# One probe over the square so glossy surfaces reflect the lit façades, not just the black sky.
	var probe := ReflectionProbe.new()
	probe.position = Vector3(0, 6, 0)
	probe.size = Vector3(64, 20, 64)
	probe.update_mode = ReflectionProbe.UPDATE_ONCE
	probe.intensity = 0.8
	probe.max_distance = 60
	add_child(probe)
	var fill := DirectionalLight3D.new()
	fill.light_color = Color(0.45, 0.5, 0.7)
	fill.light_energy = 0.12
	fill.rotation_degrees = Vector3(-30, -140, 0)
	add_child(fill)

	# Oil lanterns. Kraków had public street lighting from the 1770s, sparse: warm pools between dark stretches.
	for p in [Vector3(-22, 0, -22), Vector3(22, 0, -22), Vector3(-22, 0, 22), Vector3(16, 0, 24),
			Vector3(0, 0, -24), Vector3(-6, 0, 24), Vector3(-24, 0, 0), Vector3(24, 0, 4), Vector3(5, 0, 9), Vector3(-5, 0, -9)]:
		var l := FlickerLight.new()
		l.amount = 0.10
		l.speed = 7.0
		l.position = p + Vector3(0.9, 2.9, 0)
		l.light_color = Color(1.0, 0.70, 0.40)
		l.light_energy = 9
		l.omni_range = 24
		l.omni_attenuation = 1.5
		l.shadow_enabled = true
		l.light_size = 0.12
		l.light_specular = 0.7
		l.light_volumetric_fog_energy = 1.6
		add_child(l)
		Assets.place(self, "lantern_post", p, 0.0)

	# The dragon's cave, south-west beyond the Town Hall: a sulphurous glow (easter egg).
	var cave := OmniLight3D.new()
	cave.position = Vector3(-36, 2.5, 33)
	cave.light_color = Color(0.55, 0.95, 0.45)
	cave.light_energy = 5
	cave.omni_range = 16
	cave.shadow_enabled = true
	add_child(cave)

	# Lit windows spill a little warm light onto the square's edges.
	# Candle-lit windows: one or two flickering candle pools per house, just outside the façade, at the ground-floor
	# shop window and a first-floor room. Dimmer and yellower than the lanterns, no shadows (cheap). Placed after
	# the tenement rows are up so they follow the modules (see _candles()).
	call_deferred("_candles")
	# Watch braziers by the guard posts: the light the player has to skirt.
	for p in [Vector3(-3, 1.2, -18), Vector3(19, 1.2, 12)]:
		var b := FlickerLight.new()
		b.amount = 0.22
		b.speed = 9.0
		b.position = p
		b.light_color = Color(1.0, 0.55, 0.22)
		b.light_energy = 4
		b.omni_range = 12
		b.omni_attenuation = 1.5
		b.shadow_enabled = true
		b.light_volumetric_fog_energy = 1.2
		add_child(b)
		Assets.place(self, "brazier", p - Vector3(0, 1.2, 0), 0.0)


func _candles() -> void:
	var i := 0
	for por in portals:
		var centre: Vector3 = por[1]
		var rot: float = por[2]
		var out := Vector3(sin(rot), 0, cos(rot))     # façade normal, toward the street
		var face := centre + out * 4.0
		var along := Vector3(out.z, 0, -out.x)
		# houses alternate: a shop window low, a candle-lit room above, sometimes both
		var spots: Array = []
		if i % 3 != 1:
			spots.append(face + out * 1.0 + along * 1.5 + Vector3(0, 2.0, 0))
		if i % 3 != 2:
			spots.append(face + out * 0.8 + along * -2.0 + Vector3(0, 5.2, 0))
		for p in spots:
			var w := FlickerLight.new()
			w.amount = 0.18
			w.speed = 4.0
			w.position = p
			w.light_color = Color(1.0, 0.76, 0.42)
			w.light_energy = 3.0
			w.omni_range = 11
			w.omni_attenuation = 1.3
			w.light_specular = 0.5
			w.light_volumetric_fog_energy = 0.8
			add_child(w)
		i += 1
	# lit windows in the landmark blocks: Cloth Hall arcade, Town Hall, St Mary's porch
	for p in [Vector3(-9, 3, -6), Vector3(9, 3, 6), Vector3(-22, 4, 14), Vector3(26, 3, -14)]:
		var w := FlickerLight.new()
		w.amount = 0.12
		w.position = p
		w.light_color = Color(1.0, 0.74, 0.40)
		w.light_energy = 3.5
		w.omni_range = 12
		w.omni_attenuation = 1.3
		w.light_volumetric_fog_energy = 0.8
		add_child(w)


func _ground() -> void:
	# Plain static body (not CSG) so the navmesh baker reads its box shape directly.
	var g := StaticBody3D.new()
	g.name = "Ground"
	g.position.y = -0.5
	var gs := CollisionShape3D.new()
	var gb := BoxShape3D.new()
	gb.size = Vector3(90, 1, 90)
	gs.shape = gb
	g.add_child(gs)
	add_child(g)
	# Granite setts: one 4 m slab mesh instanced over the square (top at y=0), the box above stays as collision.
	var slab := Assets.instance("ground_cobbles")
	var slab_mesh: Mesh = null
	if slab:
		var stack: Array = [slab]
		while stack.size() > 0 and slab_mesh == null:
			var n: Node = stack.pop_back()
			if n is MeshInstance3D and not (n.get_parent() is StaticBody3D):
				slab_mesh = (n as MeshInstance3D).mesh
			for c in n.get_children():
				stack.append(c)
		slab.queue_free()
	if slab_mesh and ResourceLoader.exists("res://assets/ground/cobbles_height.png"):
		var base := slab_mesh.surface_get_material(0)
		if base is BaseMaterial3D:
			var pm := (base as BaseMaterial3D).duplicate() as BaseMaterial3D
			pm.heightmap_enabled = true
			pm.heightmap_texture = load("res://assets/ground/cobbles_height.png")
			pm.heightmap_scale = 2.0
			pm.heightmap_deep_parallax = true
			pm.heightmap_min_layers = 8
			pm.heightmap_max_layers = 24
			slab_mesh = slab_mesh.duplicate()
			slab_mesh.surface_set_material(0, pm)
	if slab_mesh:
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = slab_mesh
		var n_side := 23
		mm.instance_count = n_side * n_side
		var i := 0
		for ix in n_side:
			for iz in n_side:
				var x := (ix - (n_side - 1) * 0.5) * 4.0
				var z := (iz - (n_side - 1) * 0.5) * 4.0
				mm.set_instance_transform(i, Transform3D(Basis.IDENTITY, Vector3(x, 0.0, z)))
				i += 1
		var mmi := MultiMeshInstance3D.new()
		mmi.name = "Cobbles"
		mmi.multimesh = mm
		add_child(mmi)
	else:
		var gm := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = gb.size
		bm.material = _ground_mat
		gm.mesh = bm
		g.add_child(gm)


func _landmarks() -> void:
	Assets.place(self, "sukiennice", Vector3(0, 0, 0), 0.0)
	Assets.place(self, "town_hall", Vector3(-16, 0, 12), 0.0)        # tower at (-16,12), hall stretching west
	Assets.place(self, "st_marys", Vector3(34, 0, -34), 0.0)          # front (towers) faces south onto the square
	Assets.place(self, "st_adalbert", Vector3(21, 0, 19), 0.0)


func _tenements() -> void:
	# Rows of varied modules. Each entry: asset, width. Widths must sum to the row length.
	var north := [["tenement_a", 10.0], ["tenement_b", 8.0], ["tenement_c", 12.0], ["tenement_d", 10.0], ["tenement_e", 8.0]]
	var south := [["tenement_e", 8.0], ["tenement_d", 10.0], ["tenement_a", 10.0], ["tenement_b", 8.0], ["tenement_c", 12.0]]
	var west := [["tenement_d", 10.0], ["tenement_e", 8.0], ["tenement_a", 10.0], ["tenement_b", 8.0]]
	var east := [["tenement_b", 8.0], ["tenement_a", 10.0]]
	_row(north, Vector3(-24, 0, -32), Vector3(1, 0, 0), 0.0)        # z=-32, faces south (+Z)
	_row(south, Vector3(-24, 0, 32), Vector3(1, 0, 0), PI)          # faces north
	_row(west, Vector3(-32, 0, -18), Vector3(0, 0, 1), PI * 0.5)    # faces east
	_row(east, Vector3(32, 0, -4), Vector3(0, 0, 1), -PI * 0.5)     # faces west, south of St Mary's


func _row(mods: Array, start: Vector3, dir: Vector3, rot_y: float) -> void:
	var cursor := start
	for m in mods:
		var w: float = m[1]
		var centre := cursor + dir * (w * 0.5)
		portals.append([m[0], centre, rot_y])
		if Assets.place(self, m[0], centre, rot_y) == null:
			var b := CSGBox3D.new()
			b.size = Vector3(w, 12, 8) if dir.x != 0 else Vector3(8, 12, w)
			b.position = centre + Vector3(0, 6, 0)
			b.use_collision = true
			add_child(b)
		cursor += dir * w


func _furniture() -> void:
	# Stalls cluster on the square's east and west halves, as the weekly market left them.
	for s in [[Vector3(-14, 0, -14), 0.0], [Vector3(-10, 0, -14), 0.0], [Vector3(-6, 0, -16), 0.3],
			[Vector3(10, 0, 13), PI], [Vector3(14, 0, 13), PI], [Vector3(6, 0, 15), PI - 0.3],
			[Vector3(-20, 0, -4), PI * 0.5], [Vector3(20, 0, -10), -PI * 0.5], [Vector3(20, 0, -6), -PI * 0.5]]:
		Assets.place(self, "market_stall", s[0], s[1])
	for p in [Vector3(-11, 0, 15), Vector3(-10.2, 0, 15.7), Vector3(15, 0, -15), Vector3(-19, 0, -12), Vector3(19, 0, 10), Vector3(19.9, 0, 10.5)]:
		Assets.place(self, "barrel", p, randf() * TAU)
	for c in [[Vector3(12, 0, -19), 0.4], [Vector3(-16, 0, 20), -0.6], [Vector3(24, 0, 12), PI * 0.5]]:
		Assets.place(self, "cart", c[0], c[1])
	for c in [[Vector3(-8, 0, 12), 0.2], [Vector3(8, 0, -13), -0.5]]:
		Assets.place(self, "crate_stack", c[0], c[1])
	Assets.place(self, "well", Vector3(-12, 0, 9), 0.0)
	Assets.place(self, "well", Vector3(14, 0, -9), PI * 0.5)



## Lived-in flavour props: signs, shop fronts, the cafe and inn, benches, trees, clutter (scripts/city/dressing.gd).
func _dressing() -> void:
	var d := Node3D.new()
	d.set_script(load("res://scripts/city/dressing.gd"))
	d.set("portals", portals)
	add_child(d)


func _guards() -> void:
	var routes := [
		{"name": "Rynek patrol A", "wps": [Vector3(-20, 0, -20), Vector3(18, 0, -20), Vector3(18, 0, -13), Vector3(-20, 0, -12)]},
		{"name": "Rynek patrol B", "wps": [Vector3(14, 0, 20), Vector3(-10, 0, 20), Vector3(-10, 0, 14), Vector3(14, 0, 17)]},
		{"name": "Cloth Hall sentry", "wps": [Vector3(0, 0, -7), Vector3(0, 0, -7)]},
		{"name": "St Mary's post", "wps": [Vector3(24, 0, -14), Vector3(24, 0, 4), Vector3(24, 0, -8)]},
	]
	for r in routes:
		spawn_guard(r["name"], r["wps"])


## One watch patrol (or a sentry: a single waypoint, or two equal ones) facing `facing` at the start.
func spawn_guard(guard_name: String, points: Array, facing: float = 0.0) -> CharacterBody3D:
	var g := CharacterBody3D.new()
	g.set_script(GuardScript)
	g.guard_name = guard_name
	var wps: Array[Vector3] = []
	for w in points:
		wps.append(w if w is Vector3 else Vector3(float(w[0]), float(w[1]), float(w[2])))
	if wps.size() == 1:
		wps.append(wps[0])
	g.waypoints = wps
	g.position = wps[0]
	g.rotation.y = facing
	add_child(g)
	g.add_child(avoidance_obstacle(0.45))
	return g


func _population() -> void:
	# Night townsfolk and animals from data/npcs.json.
	var pop := Node.new()
	pop.set_script(PopulationScript)
	pop.name = "Population"
	add_child(pop)


func _safe_house() -> void:
	# Boatmen's contact: a cellar door at the south-east corner between St Adalbert's and the tenements.
	var sh := Area3D.new()
	sh.set_script(SafeHouseScript)
	sh.name = "SafeHouse"
	sh.position = Vector3(26, 0, 25)
	add_child(sh)


## Walkable surface for townsfolk, baked at runtime from the static collision (ground CSG and the -col
## shapes in the building and prop glTFs). Characters are CharacterBody3D, so they are not baked in.
func _navigation() -> void:
	add_to_group(NAV_GROUP)
	var nm := NavigationMesh.new()
	nm.geometry_parsed_geometry_type = NavigationMesh.PARSED_GEOMETRY_STATIC_COLLIDERS
	nm.geometry_source_geometry_mode = NavigationMesh.SOURCE_GEOMETRY_GROUPS_WITH_CHILDREN
	nm.geometry_source_group_name = NAV_GROUP
	nm.agent_radius = 0.4
	nm.agent_height = 1.75
	nm.agent_max_climb = 0.25
	nm.agent_max_slope = 30.0
	nm.cell_size = 0.2            # 0.4 m radius = 2 cells exactly
	nm.cell_height = 0.25
	# Only the street level matters: clip geometry above 4 m so roofs and towers are not voxelised.
	nm.filter_baking_aabb = AABB(Vector3(-45, -1, -45), Vector3(90, 5, 90))
	nav_region = NavigationRegion3D.new()
	nav_region.name = "NavRegion"
	nav_region.navigation_mesh = nm
	NavigationServer3D.map_set_cell_size(get_world_3d().navigation_map, nm.cell_size)
	NavigationServer3D.map_set_cell_height(get_world_3d().navigation_map, nm.cell_height)
	add_child(nav_region)
	nav_region.bake_finished.connect(_on_bake_finished)
	# The glTF instances and CSG collision register with physics during this frame: bake on the next one.
	await get_tree().physics_frame
	if is_inside_tree():
		nav_region.bake_navigation_mesh(true)


func _on_bake_finished() -> void:
	_bake_iteration = NavigationServer3D.map_get_iteration_id(get_world_3d().navigation_map)
	_baked = navmesh_polygons() > 0
	navmesh_ready.emit(navmesh_polygons())


## True once the baked navmesh has been synced into the world's navigation map (map sync is async,
## so the map iteration must move past the one current when the bake finished).
func nav_ready() -> bool:
	return _baked and NavigationServer3D.map_get_iteration_id(get_world_3d().navigation_map) > _bake_iteration


func navmesh_polygons() -> int:
	if nav_region == null or nav_region.navigation_mesh == null:
		return 0
	return nav_region.navigation_mesh.get_polygon_count()


## Guards and the player are not NavigationAgents; this lets townsfolk steer around them.
static func avoidance_obstacle(r: float) -> NavigationObstacle3D:
	var o := NavigationObstacle3D.new()
	o.name = "AvoidanceObstacle"
	o.radius = r
	o.avoidance_enabled = true
	return o


## Interior sets below the map and door triggers at the portals (scripts/city/interiors.gd).
func _interiors() -> void:
	var n := Node3D.new()
	n.set_script(load("res://scripts/city/interiors.gd"))
	n.set("portals", portals)
	add_child(n)


func player_spawn() -> Vector3:
	# Player enters from the NW alley between the tenement rows.
	return Vector3(-27, 0.2, -27)
