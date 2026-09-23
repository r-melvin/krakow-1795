extends Node3D
## Procedural greybox of a Rynek-adjacent block. Replace pieces with Blender glTF as they land.
## Layout (top view, metres): a 60x60 square with a market hall in the middle (Sukiennice stand-in),
## tenement blocks around the edges, alleys between them, a church mass in one corner.

const GuardScript := preload("res://scripts/stealth/guard.gd")
const SafeHouseScript := preload("res://scripts/stealth/safe_house.gd")

var _wall_mat: StandardMaterial3D
var _ground_mat: StandardMaterial3D


func _ready() -> void:
	_wall_mat = StandardMaterial3D.new()
	_wall_mat.albedo_color = Color(0.55, 0.5, 0.45)
	_ground_mat = StandardMaterial3D.new()
	_ground_mat.albedo_color = Color(0.3, 0.29, 0.28)

	_environment()
	_ground()
	_market_hall()
	_tenements()
	_church()
	_cover()
	_guards()
	_safe_house()


func _environment() -> void:
	var env := WorldEnvironment.new()
	var e := Environment.new()
	e.background_mode = Environment.BG_COLOR
	e.background_color = Color(0.03, 0.03, 0.06)
	e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	e.ambient_light_color = Color(0.25, 0.28, 0.4)
	e.ambient_light_energy = 0.35
	e.fog_enabled = true
	e.fog_light_color = Color(0.08, 0.09, 0.14)
	e.fog_density = 0.012
	env.environment = e
	add_child(env)

	var moon := DirectionalLight3D.new()
	moon.light_color = Color(0.6, 0.7, 0.95)
	moon.light_energy = 0.35
	moon.rotation_degrees = Vector3(-50, 30, 0)
	moon.shadow_enabled = true
	add_child(moon)

	# Street lanterns.
	for p in [Vector3(-20, 3, -20), Vector3(20, 3, -20), Vector3(-20, 3, 20), Vector3(20, 3, 20), Vector3(0, 3, -26), Vector3(0, 3, 26)]:
		var l := OmniLight3D.new()
		l.position = p
		l.light_color = Color(1.0, 0.75, 0.45)
		l.light_energy = 3
		l.omni_range = 12
		l.shadow_enabled = true
		add_child(l)
		var post := CSGCylinder3D.new()
		post.radius = 0.08
		post.height = 3
		post.position = Vector3(p.x, 1.5, p.z)
		add_child(post)


func _ground() -> void:
	var g := CSGBox3D.new()
	g.size = Vector3(70, 1, 70)
	g.position.y = -0.5
	g.use_collision = true
	g.material = _ground_mat
	add_child(g)


func _box(pos: Vector3, size: Vector3, mat: Material = null) -> CSGBox3D:
	var b := CSGBox3D.new()
	b.size = size
	b.position = pos + Vector3(0, size.y * 0.5, 0)
	b.use_collision = true
	b.material = mat if mat else _wall_mat
	add_child(b)
	return b


func _market_hall() -> void:
	# Long hall with arcades on both long sides (columns you can hide between).
	_box(Vector3(0, 0, 0), Vector3(30, 7, 8))
	for i in range(-14, 15, 4):
		_box(Vector3(i, 0, -5.5), Vector3(0.8, 5, 0.8))
		_box(Vector3(i, 0, 5.5), Vector3(0.8, 5, 0.8))
	_box(Vector3(0, 5, -5.5), Vector3(30, 0.5, 2.5))
	_box(Vector3(0, 5, 5.5), Vector3(30, 0.5, 2.5))


func _tenements() -> void:
	# Edge blocks with alley gaps.
	var h := 10.0
	# North row
	_box(Vector3(-22, 0, -30), Vector3(14, h, 8))
	_box(Vector3(-4, 0, -30), Vector3(12, h + 2, 8))
	_box(Vector3(14, 0, -30), Vector3(14, h, 8))
	# South row
	_box(Vector3(-22, 0, 30), Vector3(14, h, 8))
	_box(Vector3(-4, 0, 30), Vector3(12, h + 1, 8))
	_box(Vector3(14, 0, 30), Vector3(14, h, 8))
	# West column
	_box(Vector3(-30, 0, -14), Vector3(8, h, 12))
	_box(Vector3(-30, 0, 6), Vector3(8, h + 3, 12))
	# East column
	_box(Vector3(30, 0, -14), Vector3(8, h, 12))
	_box(Vector3(30, 0, 6), Vector3(8, h, 12))


func _church() -> void:
	# NE corner: nave + tower (St Mary's stand-in).
	_box(Vector3(26, 0, -26), Vector3(10, 16, 10))
	_box(Vector3(22, 0, -30), Vector3(3, 30, 3))


func _cover() -> void:
	# Market stalls, carts, barrels: low cover for crouching.
	var crate_mat := StandardMaterial3D.new()
	crate_mat.albedo_color = Color(0.45, 0.32, 0.2)
	for p in [Vector3(-8, 0, -12), Vector3(-4, 0, -12), Vector3(6, 0, 12), Vector3(10, 0, 12), Vector3(-16, 0, 2), Vector3(16, 0, -3), Vector3(-10, 0, 18), Vector3(12, 0, -18)]:
		_box(p, Vector3(2.2, 1.1, 1.4), crate_mat)
	for p in [Vector3(-12, 0, 14), Vector3(14, 0, 16), Vector3(-18, 0, -10), Vector3(18, 0, 10)]:
		var b := CSGCylinder3D.new()
		b.radius = 0.5
		b.height = 1.0
		b.position = p + Vector3(0, 0.5, 0)
		b.use_collision = true
		b.material = crate_mat
		add_child(b)


func _guards() -> void:
	var routes := [
		{"name": "Rynek patrol A", "wps": [Vector3(-18, 0, -14), Vector3(18, 0, -14), Vector3(18, 0, -22), Vector3(-18, 0, -22)]},
		{"name": "Rynek patrol B", "wps": [Vector3(18, 0, 14), Vector3(-18, 0, 14), Vector3(-18, 0, 22), Vector3(18, 0, 22)]},
		{"name": "Arcade sentry", "wps": [Vector3(-12, 0, 0), Vector3(-12, 0, 0)]},
		{"name": "East gate", "wps": [Vector3(22, 0, 0), Vector3(22, 0, 8), Vector3(22, 0, -8)]},
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
	var sh := Area3D.new()
	sh.set_script(SafeHouseScript)
	sh.position = Vector3(24, 0, 24)
	add_child(sh)


func player_spawn() -> Vector3:
	return Vector3(-24, 0.2, 24)
