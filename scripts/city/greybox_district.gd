extends Node3D
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
	sm.sun_angle_max = 5.0
	sky.sky_material = sm
	e.background_mode = Environment.BG_SKY
	e.sky = sky
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.16, 0.19, 0.32)
	e.ambient_light_energy = 0.5
	e.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	e.tonemap_exposure = 1.15
	e.ssao_enabled = true
	e.ssao_radius = 1.5
	e.ssao_intensity = 2.5
	e.glow_enabled = true
	e.glow_intensity = 0.55
	e.glow_bloom = 0.15
	e.glow_hdr_threshold = 1.0
	e.fog_enabled = true
	e.fog_light_color = Color(0.07, 0.08, 0.13)
	e.fog_density = 0.008
	e.adjustment_enabled = true
	e.adjustment_saturation = 1.15
	e.adjustment_contrast = 1.08
	env.environment = e
	add_child(env)

	# Low winter moon: cool, long shadows.
	var moon := DirectionalLight3D.new()
	moon.light_color = Color(0.55, 0.66, 1.0)
	moon.light_energy = 0.22
	moon.rotation_degrees = Vector3(-38, 40, 0)
	moon.shadow_enabled = true
	moon.directional_shadow_max_distance = 120
	add_child(moon)
	var fill := DirectionalLight3D.new()
	fill.light_color = Color(0.45, 0.5, 0.7)
	fill.light_energy = 0.12
	fill.rotation_degrees = Vector3(-30, -140, 0)
	add_child(fill)

	# Oil lanterns. Kraków had public street lighting from the 1770s, sparse: warm pools between dark stretches.
	for p in [Vector3(-22, 0, -22), Vector3(22, 0, -22), Vector3(-22, 0, 22), Vector3(16, 0, 24),
			Vector3(0, 0, -24), Vector3(-6, 0, 24), Vector3(-24, 0, 0), Vector3(24, 0, 4), Vector3(5, 0, 9), Vector3(-5, 0, -9)]:
		var l := OmniLight3D.new()
		l.position = p + Vector3(0.9, 2.9, 0)
		l.light_color = Color(1.0, 0.68, 0.36)
		l.light_energy = 10
		l.omni_range = 22
		l.omni_attenuation = 1.3
		l.shadow_enabled = true
		l.light_specular = 0.3
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
	for p in [Vector3(-14, 6, -27), Vector3(8, 6, -27), Vector3(-27, 6, 6), Vector3(6, 6, 27), Vector3(-12, 6, 27)]:
		var w := OmniLight3D.new()
		w.position = p
		w.light_color = Color(1.0, 0.75, 0.45)
		w.light_energy = 2.5
		w.omni_range = 9
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
	var gm := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = gb.size
	bm.material = _ground_mat
	gm.mesh = bm
	g.add_child(gm)
	add_child(g)
	# Snow patches and a few paving strips to break the plane.
	var snow := StandardMaterial3D.new()
	snow.albedo_color = Color(0.80, 0.83, 0.90)
	snow.roughness = 0.95
	var rng := RandomNumberGenerator.new()
	rng.seed = 1795
	for i in 24:
		var s := CSGBox3D.new()
		s.size = Vector3(rng.randf_range(2, 7), 0.06, rng.randf_range(2, 6))
		s.position = Vector3(rng.randf_range(-26, 26), 0.03, rng.randf_range(-26, 26))
		s.rotation.y = rng.randf() * TAU
		s.material = snow
		add_child(s)


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


func _guards() -> void:
	var routes := [
		{"name": "Rynek patrol A", "wps": [Vector3(-20, 0, -20), Vector3(18, 0, -20), Vector3(18, 0, -13), Vector3(-20, 0, -12)]},
		{"name": "Rynek patrol B", "wps": [Vector3(14, 0, 20), Vector3(-10, 0, 20), Vector3(-10, 0, 14), Vector3(14, 0, 17)]},
		{"name": "Cloth Hall sentry", "wps": [Vector3(0, 0, -7), Vector3(0, 0, -7)]},
		{"name": "St Mary's post", "wps": [Vector3(24, 0, -14), Vector3(24, 0, 4), Vector3(24, 0, -8)]},
	]
	for r in routes:
		var g := CharacterBody3D.new()
		g.set_script(GuardScript)
		g.guard_name = r["name"]
		var wps: Array[Vector3] = []
		for w in r["wps"]:
			wps.append(w)
		g.waypoints = wps
		g.position = wps[0]
		add_child(g)
		g.add_child(avoidance_obstacle(0.45))


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
