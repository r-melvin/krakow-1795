extends Node3D
## Rynek Glowny, compressed to ~1/3 scale for play. Built from Blender glTF placed by script.
## Layout (Godot axes, metres): square is 60x60 centred on the origin. +X east, +Z south.
##   Sukiennice in the middle, Town Hall + tower SW, St Mary's NE, St Adalbert's SE.
##   Tenement rows on all four sides with arcaded/portalled ground floors facing the square.
## Blender front (-Y) lands on Godot +Z, so rot_y = 0 faces south, PI north, PI/2 east, -PI/2 west.

const GuardScript := preload("res://scripts/stealth/guard.gd")
const SafeHouseScript := preload("res://scripts/stealth/safe_house.gd")

var _ground_mat: StandardMaterial3D


func _ready() -> void:
	_ground_mat = StandardMaterial3D.new()
	_ground_mat.albedo_color = Color(0.36, 0.35, 0.36)
	_environment()
	_ground()
	_landmarks()
	_tenements()
	_furniture()
	_guards()
	_safe_house()


func _environment() -> void:
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.04, 0.045, 0.08)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.3, 0.34, 0.5)
	e.ambient_light_energy = 0.4
	e.fog_enabled = true
	e.fog_light_color = Color(0.09, 0.10, 0.16)
	e.fog_density = 0.010
	e.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	e.glow_enabled = true
	e.glow_intensity = 0.4
	e.glow_bloom = 0.1
	env.environment = e
	add_child(env)

	var moon := DirectionalLight3D.new()
	moon.light_color = Color(0.62, 0.72, 1.0)
	moon.light_energy = 0.45
	moon.rotation_degrees = Vector3(-55, 35, 0)
	moon.shadow_enabled = true
	add_child(moon)

	# Oil lanterns. Kraków had public street lighting from the 1770s, sparse.
	for p in [Vector3(-22, 0, -22), Vector3(22, 0, -22), Vector3(-22, 0, 22), Vector3(16, 0, 24),
			Vector3(0, 0, -24), Vector3(-6, 0, 24), Vector3(-24, 0, 0), Vector3(24, 0, 4)]:
		var l := OmniLight3D.new()
		l.position = p + Vector3(0.8, 2.8, 0)
		l.light_color = Color(1.0, 0.72, 0.42)
		l.light_energy = 4
		l.omni_range = 14
		l.omni_attenuation = 1.4
		l.shadow_enabled = true
		add_child(l)
		Assets.place(self, "lantern_post", p, 0.0)


func _ground() -> void:
	var g := CSGBox3D.new()
	g.size = Vector3(90, 1, 90)
	g.position.y = -0.5
	g.use_collision = true
	g.material = _ground_mat
	add_child(g)
	# Snow patches and a few paving strips to break the plane.
	var snow := StandardMaterial3D.new()
	snow.albedo_color = Color(0.86, 0.88, 0.93)
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
	Assets.place(self, "well", Vector3(-12, 0, 2), 0.0)
	Assets.place(self, "well", Vector3(14, 0, 0), PI * 0.5)


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


func _safe_house() -> void:
	# Boatmen's contact: a cellar door at the south-east corner between St Adalbert's and the tenements.
	var sh := Area3D.new()
	sh.set_script(SafeHouseScript)
	sh.name = "SafeHouse"
	sh.position = Vector3(26, 0, 25)
	add_child(sh)


func player_spawn() -> Vector3:
	# Player enters from the NW alley between the tenement rows.
	return Vector3(-27, 0.2, -27)
