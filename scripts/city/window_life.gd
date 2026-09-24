extends Node3D
## Life at the windows and chimneys of the square (tunables and event tables in data/window_life.json):
##   * chimney smoke: a pool of GPUParticles3D (<= smoke.max_emitters x smoke.particles) handed to the nearest lit
##     chimneys within smoke.cull_distance of the camera; denser at the cooking hours, thin late at night, drifting
##     with `wind`; a few chimneys stay cold.
##   * window events, one every scheduler.interval s at a window within scheduler.radius m of the player (never the
##     same window twice running): a figure leaning on the sill, pouring a bucket into the street (stream, splash,
##     a wet patch fading over a minute, a bark, a watch sound event), throwing a cabbage / bone / bottle / rag that
##     bounces and stays, shaking out a duster (dust), cooking (warm flicker, a pot on the sill, a wisp from the
##     window head, the cook stirring behind the frame), or a cat sitting on the sill.
##   * street cooking: a cauldron over the cafe brazier and a pot over a fire in the inn yard, steaming, with a cook
##     stirring on a schedule; ember sparks at any Furnace_* empty; thin steady wisps from the tavern windows.
##
## Anchors: named empties in the building glbs win when present: Chimney_<n> (flue top), Window_<n> (sill centre,
## +Z into the street), Furnace_<n>. Until the buildings carry them, each placed building is resolved by
## fallback: tenements mirror tenement() in assets/blender/build_assets.py (the same trick dressing.gd uses:
## chimney per roof kind, a window per bay and upper storey, shutters on tenement_a/d/e); any other house-like glb
## gets chimneys estimated from its mesh AABB (top edge, two per module, 1 m in from the ends) and windows from the
## candle lights (greybox_district.gd _candles(): FlickerLights ~1 m outside a window, pushed back to the facade).
## Candle lights also mark tenement windows as "lit" (cooking prefers them).
##
## Windows: the figure stands in the room behind the sill (the building's solid storey box hides everything behind
## the glass plane). An "open window" card covers the glass (in front of the frame for leans, behind it for the
## cook, so the cook is seen through the casement), and only the head, shoulders and arms cross it.
##
## `-- --smoke` fires every event type once within a few seconds and prints
## `[smoke] window_life chimneys=<n> events=<types>`. `-- --smoke --window-shot=/dir` (windowed) saves close-ups:
## chimney smoke against the moon, a pour with its splash, a thrown cabbage, a cooking window, the brazier steam,
## with and without GI.

const FlickerLight := preload("res://scripts/city/flicker.gd")
const Walker := preload("res://scripts/npc/walker.gd")
const DATA_PATH := "res://data/window_life.json"

## tenement() geometry (build_assets.py): ground floor, storey height, jetty per storey, facade 4 m before centre.
const GF := 4.2
const FL := 3.3
const JETTY := 0.22
const FRONT := 4.0
const REV := 0.15
const TENEMENTS := {
	"tenement_a": {"width": 10.0, "storeys": 3, "bays": 3, "roof": "gable", "shutters": true, "arched": false},
	"tenement_b": {"width": 8.0, "storeys": 3, "bays": 2, "roof": "attyka", "shutters": false, "arched": false},
	"tenement_c": {"width": 12.0, "storeys": 4, "bays": 3, "roof": "mansard", "shutters": false, "arched": true},
	"tenement_d": {"width": 10.0, "storeys": 3, "bays": 3, "roof": "attyka", "shutters": true, "arched": true},
	"tenement_e": {"width": 8.0, "storeys": 4, "bays": 2, "roof": "gable", "shutters": true, "arched": false},
}
## chimney(parts, x, y, z, h) per roof kind: x as a fraction of the width, Blender y, base above `top`, height.
const CHIMNEY := {"gable": [0.3, 1.2, 2.0, 2.6], "attyka": [-0.25, 1.5, 1.5, 2.2], "mansard": [-0.3, 1.0, 2.6, 2.4]}
const HOUSE_WORDS := ["house", "cottage", "manor", "granary", "workshop", "stable"]
const EVENT_TYPES := ["lean", "pour", "throw", "shake", "cook", "cat", "street_cook"]
const THROW_RELEASE := 0.78          ## window_throw: the hand opens here (build_animations.py)
const LOOP_CLIPS := ["window_lean", "window_shake_cloth", "cook_stir", "cook_chop"]

var portals: Array = []              ## the district's [asset, centre, rot_y] per tenement (from dressing.gd)
var boards: Dictionary = {}          ## portal -> lx of its fascia board (no figures at that first-floor window)

var cfg: Dictionary = {}
var chimneys: Array = []             ## {pos, lit, emitter}
var windows: Array = []              ## {pos, basis, w, h, shutters, lit, portal, lx, storey, busy}
var furnaces: Array = []
var fired: Array = []                ## event types fired in this world

var _rng := RandomNumberGenerator.new()
var _district: Node3D
var _pool: Array = []                ## smoke GPUParticles3D
var _events: Array = []              ## active window events (state dictionaries, advanced in _process)
var _street: Array = []              ## street cooks
var _wisps: Array = []               ## [GPUParticles3D, pos]
var _litter: Array = []              ## [node, secs left, kind] puddles and thrown props
var _next_event := 0.0
var _last_window := -1
var _smoke := false
var _smoke_frames := 0
var _smoke_cycle := 0
var _pool_timer := 0.0
var _ready_done := false
var _mat_cache := {}

var _smoke_tex: ImageTexture
var _blot_tex: ImageTexture
static var _smoke_printed := false
static var _smoke_seen: Dictionary = {}
static var _shot_index := 0
static var _shot_restarts := 0


## One call from dressing.gd once the dressing is placed.
static func create(p_portals: Array, p_boards: Dictionary) -> Node3D:
	var n := Node3D.new()
	n.set_script(load("res://scripts/city/window_life.gd"))
	n.set("portals", p_portals)
	n.set("boards", p_boards)
	return n


func _ready() -> void:
	name = "WindowLife"
	_rng.seed = 1795
	_smoke = "--smoke" in OS.get_cmdline_user_args()
	cfg = _load_json(DATA_PATH)
	_setup.call_deferred()


func _load_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		push_warning("window_life: missing %s" % path)
		return {}
	var d: Variant = JSON.parse_string(FileAccess.get_file_as_string(path))
	return d if d is Dictionary else {}


func c(path: String, fallback: Variant) -> Variant:
	var cur: Variant = cfg
	for k in path.split("."):
		if cur is Dictionary and (cur as Dictionary).has(k):
			cur = cur[k]
		else:
			return fallback
	return cur


func _v3(a: Variant, fallback := Vector3.ZERO) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2])) if a is Array and a.size() >= 3 else fallback


func _col(a: Variant, fallback := Color.WHITE) -> Color:
	if a is Array and a.size() >= 3:
		return Color(float(a[0]), float(a[1]), float(a[2]), float(a[3]) if a.size() > 3 else 1.0)
	return fallback


func _range(path: String, fallback: Vector2) -> Vector2:
	var a: Variant = c(path, null)
	return Vector2(float(a[0]), float(a[1])) if a is Array and a.size() >= 2 else fallback


# ------------------------------------------------------------------ setup
func _setup() -> void:
	if not is_inside_tree():
		return
	_district = _find_district()
	_collect_anchors()
	_build_smoke_pool()
	_build_wisps()
	_build_street_cooks()
	_build_furnaces()
	_next_event = _rng.randf_range(_range("scheduler.interval", Vector2(20, 60)).x * 0.5, _range("scheduler.interval", Vector2(20, 60)).x)
	_ready_done = true


func _find_district() -> Node3D:
	var n: Node = get_parent()
	while n != null:
		if n.is_in_group("nav_source") or n.get("portals") != null and n.has_method("player_spawn"):
			return n as Node3D
		n = n.get_parent()
	return get_parent().get_parent() as Node3D if get_parent() and get_parent().get_parent() is Node3D else get_parent() as Node3D


## Placed building instances: children of the district instanced from a glb.
func _buildings() -> Array:
	var out: Array = []
	if _district == null:
		return out
	for ch in _district.get_children():
		if ch is Node3D and ch.scene_file_path.begins_with("res://assets/models/"):
			out.append(ch)
	return out


func _collect_anchors() -> void:
	var lights: Array = []
	for l in get_tree().get_nodes_in_group("flame_lights"):
		if l is Node3D and _district and _district.is_ancestor_of(l):
			lights.append((l as Node3D).global_position)
	var boxes: Array = []
	var dressing := get_parent()
	if dressing:
		for ch in dressing.get_children():
			if ch is Node3D and ch.scene_file_path.get_file().get_basename() == "window_box":
				boxes.append((ch as Node3D).global_position)
	for b: Node3D in _buildings():
		var base: String = b.scene_file_path.get_file().get_basename()
		var ch_nodes := b.find_children("Chimney_*", "Node3D", true, false)
		var win_nodes := b.find_children("Window_*", "Node3D", true, false)
		for f in b.find_children("Furnace_*", "Node3D", true, false):
			furnaces.append((f as Node3D).global_position)
		var portal := _portal_of(b)
		var info: Dictionary = TENEMENTS.get(base, {})
		# chimneys
		if not ch_nodes.is_empty():
			for n in ch_nodes:
				_add_chimney((n as Node3D).global_position)
		elif not info.is_empty():
			var ck: Array = CHIMNEY[info["roof"]]
			var body_h: float = GF + FL * (int(info["storeys"]) - 1)
			var top := body_h + 0.4
			var local := Vector3(float(ck[0]) * float(info["width"]), top + float(ck[2]) + float(ck[3]) + 0.5, -float(ck[1]))
			_add_chimney(b.global_transform * local)
		elif _house_like(base):
			var bb := _local_aabb(b)
			if bb.size != Vector3.ZERO:
				var along_x := bb.size.x >= bb.size.z
				var length := bb.size.x if along_x else bb.size.z
				var modules := maxi(1, int(round(length / 10.0)))
				for m in modules:
					for e in [0, 1]:
						var t0: float = (float(m) + float(e)) / modules
						var d: float = lerpf(-length * 0.5, length * 0.5, t0) + (1.0 if e == 0 else -1.0)
						var cc := bb.get_center()
						var lp := Vector3(cc.x + d, bb.end.y, cc.z) if along_x else Vector3(cc.x, bb.end.y, cc.z + d)
						_add_chimney(b.global_transform * lp)
		# windows
		if not win_nodes.is_empty():
			# Window_<n>: sill centre, 2 cm proud of the wall, +Z out. Ground-floor shop windows (barred) only take
			# cooks and cats; first-floor ones everything. Same skips as the fallback (fascia boards, boxes, oriel).
			for n in win_nodes:
				var wn := n as Node3D
				var bas := wn.global_transform.basis.orthonormalized()
				var wp := wn.global_position - bas.z * 0.02
				var loc: Vector3 = b.global_transform.affine_inverse() * wp
				var ground := loc.y < GF - 0.5
				var s := 0 if ground else int(round((loc.y - GF - 0.8) / FL)) + 1
				var arched: bool = ground or (not info.is_empty() and bool(info["arched"]) and s == 1)
				if not ground:
					if s == 1 and boards.has(portal) and absf(float(boards[portal]) - loc.x) < 1.5:
						continue
					if portal == 5 and s == 1 and absf(loc.x + 2.0) < 0.5:
						continue
					if _box_near(boxes, wp):
						continue
				_add_window(wp, bas, 1.3 if ground else 1.1, 2.2 if ground else (2.1 if arched else 1.85),
						info.get("shutters", false) and not arched, portal, loc.x, s, lights, arched, base)
		elif not info.is_empty():
			var storeys: int = info["storeys"]
			var bays: int = info["bays"]
			var width: float = info["width"]
			var bay_w := width / bays
			for s in range(1, storeys):
				for k in bays:
					var lx := -width / 2 + bay_w * (k + 0.5)
					var arched: bool = info["arched"] and s == 1
					if s == 1 and boards.has(portal) and absf(float(boards[portal]) - lx) < 1.5:
						continue
					if portal == 5 and s == 1 and absf(lx + 2.0) < 0.5:
						continue            # the cafe oriel covers that window
					var zb := GF + FL * (s - 1) + 0.8
					var local := Vector3(lx, zb, FRONT + JETTY * s)
					var wp: Vector3 = b.global_transform * local
					if _box_near(boxes, wp):
						continue
					_add_window(wp, b.global_transform.basis.orthonormalized(), 1.1, 2.1 if arched else 1.85,
							info["shutters"] and not arched, portal, lx, s, lights, arched, base)
		elif _house_like(base):
			var bb := _local_aabb(b)
			for lp in lights:
				var loc: Vector3 = b.global_transform.affine_inverse() * lp
				if loc.y < 3.0 or loc.x < bb.position.x - 0.5 or loc.x > bb.end.x + 0.5:
					continue
				if absf(loc.z - bb.end.z) < 2.0:          # a candle outside the front (+Z) face: push it back
					var sill := Vector3(loc.x, loc.y - 0.9, bb.end.z)
					_add_window(b.global_transform * sill, b.global_transform.basis.orthonormalized(), 1.0, 1.6, false, -1, loc.x, 1, lights)
	# chimneys that stay cold tonight
	var unlit := float(c("smoke.unlit_fraction", 0.2))
	var r := RandomNumberGenerator.new()
	r.seed = 96
	for ch in chimneys:
		ch["lit"] = r.randf() >= unlit


func _house_like(base: String) -> bool:
	for w in HOUSE_WORDS:
		if w in base:
			return true
	return false


func _portal_of(b: Node3D) -> int:
	for i in portals.size():
		var p: Array = portals[i]
		if (p[1] as Vector3).distance_to(b.global_position) < 0.5 and str(p[0]) == b.scene_file_path.get_file().get_basename():
			return i
	return -1


func _box_near(boxes: Array, wp: Vector3) -> bool:
	for bp in boxes:
		var d: Vector3 = bp - wp
		if Vector2(d.x, d.z).length() < 0.8 and absf(d.y + 0.12) < 0.4:
			return true
	return false


## Merged AABB of an instance's meshes in its own space.
func _local_aabb(root: Node3D) -> AABB:
	var out := AABB()
	var first := true
	for mi in root.find_children("*", "MeshInstance3D", true, false):
		var m := mi as MeshInstance3D
		if m.mesh == null:
			continue
		var xf := root.global_transform.affine_inverse() * m.global_transform
		var bb := xf * m.mesh.get_aabb()
		out = bb if first else out.merge(bb)
		first = false
	return out


func _add_chimney(p: Vector3) -> void:
	chimneys.append({"pos": p, "lit": true, "emitter": null})


func _add_window(p: Vector3, b: Basis, w: float, h: float, shutters: bool, portal: int, lx: float, storey: int, lights: Array, arched := false,
		asset := "") -> void:
	var out := b.z
	var lit := false
	for lp in lights:
		if (lp as Vector3).distance_to(p + out * 0.9 + Vector3.UP * 0.5) < 1.8:
			lit = true
	windows.append({"pos": p, "basis": b, "w": w, "h": h, "shutters": shutters, "lit": lit, "portal": portal, "lx": lx,
			"storey": storey, "busy": false, "arched": arched, "idx": windows.size(), "ground": storey == 0, "asset": asset})


# ------------------------------------------------------------------ textures and materials
func smoke_texture() -> ImageTexture:
	if _smoke_tex:
		return _smoke_tex
	var n := 128
	var img := Image.create(n, n, false, Image.FORMAT_RGBA8)
	var noise := FastNoiseLite.new()
	noise.seed = 7
	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise.fractal_type = FastNoiseLite.FRACTAL_FBM
	noise.fractal_octaves = 4
	noise.frequency = 0.035
	for y in n:
		for x in n:
			var dx := (x + 0.5) / n * 2.0 - 1.0
			var dy := (y + 0.5) / n * 2.0 - 1.0
			var r := sqrt(dx * dx + dy * dy)
			var fall := clampf(1.0 - r, 0.0, 1.0)
			fall = fall * fall * (3.0 - 2.0 * fall)
			var v := noise.get_noise_2d(x, y) * 0.5 + 0.5
			var a := clampf(pow(fall, 1.3) * (0.7 + 0.6 * v), 0.0, 1.0)
			var shade := 0.82 + 0.18 * v
			img.set_pixel(x, y, Color(shade, shade, shade, a))
	img.generate_mipmaps()
	_smoke_tex = ImageTexture.create_from_image(img)
	return _smoke_tex


## A wet patch: dark, blotchy, alpha-feathered.
func blot_texture() -> ImageTexture:
	if _blot_tex:
		return _blot_tex
	var n := 128
	var img := Image.create(n, n, false, Image.FORMAT_RGBA8)
	var noise := FastNoiseLite.new()
	noise.seed = 21
	noise.fractal_octaves = 3
	noise.frequency = 0.05
	for y in n:
		for x in n:
			var dx := (x + 0.5) / n * 2.0 - 1.0
			var dy := (y + 0.5) / n * 2.0 - 1.0
			var r := sqrt(dx * dx + dy * dy) + noise.get_noise_2d(x, y) * 0.45
			var a := clampf((0.85 - r) * 3.0, 0.0, 1.0)
			img.set_pixel(x, y, Color(0.05, 0.045, 0.04, a * 0.85))
	img.generate_mipmaps()
	_blot_tex = ImageTexture.create_from_image(img)
	return _blot_tex


## Soft billboard smoke / steam / dust material: alpha-blended (not additive), lit by the moon and lanterns, with
## a little emission so it reads in the dark and backlight so lanterns behind it glow through.
func _puff_material(col: Color, emission: float, backlight: Color) -> StandardMaterial3D:
	var key := "%s|%.3f|%s" % [col, emission, backlight]
	if _mat_cache.has(key):
		return _mat_cache[key]
	var m := StandardMaterial3D.new()
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.billboard_keep_scale = true          # otherwise the billboard drops the particle's scale (and its growth)
	m.vertex_color_use_as_albedo = true
	m.albedo_texture = smoke_texture()
	m.albedo_color = col
	m.roughness = 1.0
	m.metallic_specular = 0.0
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.emission_enabled = emission > 0.0
	m.emission = Color(0.55, 0.60, 0.72)
	m.emission_energy_multiplier = emission
	m.backlight_enabled = true
	m.backlight = backlight
	m.proximity_fade_enabled = true
	m.proximity_fade_distance = 0.5
	m.disable_receive_shadows = false
	_mat_cache[key] = m
	return m


func _drop_material(col: Color, emission: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	m.billboard_keep_scale = true
	m.vertex_color_use_as_albedo = true
	m.albedo_color = col
	m.albedo_texture = _streak_texture()
	m.roughness = 0.1
	m.metallic_specular = 0.8
	m.emission_enabled = true
	m.emission = Color(col.r, col.g, col.b)
	m.emission_energy_multiplier = emission
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	return m


func _ramp(stops: Array) -> GradientTexture1D:
	var g := Gradient.new()
	var offs := PackedFloat32Array()
	var cols := PackedColorArray()
	for st in stops:
		offs.append(float(st[0]))
		cols.append(st[1])
	g.offsets = offs
	g.colors = cols
	var t := GradientTexture1D.new()
	t.gradient = g
	return t


func _curve(pts: Array) -> CurveTexture:
	var cv := Curve.new()
	for p in pts:
		cv.add_point(Vector2(float(p[0]), float(p[1])))
	var t := CurveTexture.new()
	t.curve = cv
	return t


## Generic rising puff emitter (chimney smoke, wisps, steam). `local` = direction/velocities in its own space.
func _puff_emitter(amount: int, lifetime: float, vel: Vector2, scale: Vector2, grow: float, col: Color, emission: float,
		dir := Vector3.UP, spread := 10.0, radius := 0.15, wind_k := 0.25, buoy := 0.1) -> GPUParticles3D:
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	pm.emission_sphere_radius = radius
	pm.direction = dir
	pm.spread = spread
	pm.initial_velocity_min = vel.x
	pm.initial_velocity_max = vel.y
	var wind := _v3(c("wind", [0.55, 0.0, 0.25]))
	pm.gravity = Vector3(wind.x * wind_k, buoy, wind.z * wind_k)
	pm.damping_min = 0.02
	pm.damping_max = 0.06
	pm.scale_min = scale.x
	pm.scale_max = scale.y
	pm.scale_curve = _curve([[0.0, 1.0 / grow], [0.3, 0.55], [1.0, 1.0]])
	pm.scale_curve.curve.bake()
	pm.angle_min = -180.0
	pm.angle_max = 180.0
	pm.angular_velocity_min = -14.0
	pm.angular_velocity_max = 14.0
	# no turbulence: in Godot it steers the velocity toward the noise field and the plume churns in place instead
	# of rising; the curl comes from the spread, the spin and the wind acceleration
	pm.color_ramp = _ramp([[0.0, Color(0.8, 0.8, 0.82, 0.0)], [0.12, Color(0.85, 0.85, 0.87, 1.0)], [0.55, Color(0.95, 0.95, 0.97, 0.55)],
			[1.0, Color(1, 1, 1, 0.0)]])
	var p := GPUParticles3D.new()
	p.amount = amount
	p.lifetime = lifetime
	p.preprocess = lifetime
	p.local_coords = false
	p.fixed_fps = 30
	p.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2.ONE
	q.material = _puff_material(col, emission, _col(c("smoke.backlight", [0.55, 0.45, 0.38])))
	p.draw_pass_1 = q
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	var reach := lifetime * (vel.y + 0.5 * absf(buoy) * lifetime) + 2.0
	var drift := 0.5 * wind.length() * wind_k * lifetime * lifetime + 2.0
	p.visibility_aabb = AABB(Vector3(-drift, -1.0, -drift), Vector3(drift * 2.0, reach + 1.0, drift * 2.0))
	return p


# ------------------------------------------------------------------ chimney smoke
func _build_smoke_pool() -> void:
	var lit := chimneys.filter(func(ch: Dictionary) -> bool: return ch["lit"])
	var n := mini(int(c("smoke.max_emitters", 40)), lit.size())
	var parts := mini(int(c("smoke.particles", 24)), 24)
	for i in n:
		var e := _puff_emitter(parts, float(c("smoke.lifetime", 9.0)), _range("smoke.rise_speed", Vector2(0.35, 0.6)),
				_range("smoke.scale", Vector2(0.55, 1.1)), float(c("smoke.grow", 3.2)), _col(c("smoke.colour", [0.72, 0.72, 0.74, 0.38])),
				float(c("smoke.emission", 0.05)), Vector3.UP, 12.0, 0.18, 0.25, float(c("smoke.buoyancy", 0.1)))
		e.name = "ChimneySmoke%d" % i
		e.emitting = false
		e.visible = false
		add_child(e)
		_pool.append({"node": e, "chimney": -1})
	_assign_pool(true)


func smoke_ratio() -> float:
	var h := fposmod(GameState.clock_minutes / 60.0, 24.0)
	var ck := _range("smoke.cooking_hours", Vector2(18, 22))
	var late := _range("smoke.late_hours", Vector2(0, 5))
	var cook_r := float(c("smoke.cooking_ratio", 1.0))
	var eve_r := float(c("smoke.evening_ratio", 0.75))
	var late_r := float(c("smoke.late_ratio", 0.3))
	if h >= ck.x and h < ck.y:
		return cook_r
	if h >= ck.y:
		return lerpf(eve_r, late_r, clampf((h - ck.y) / maxf(24.0 - ck.y, 0.01), 0.0, 1.0))
	if h >= late.x and h < late.y:
		return late_r
	return lerpf(late_r, eve_r, clampf((h - late.y) / maxf(ck.x - late.y, 0.01), 0.0, 1.0))


func _view_pos() -> Vector3:
	var cam := get_viewport().get_camera_3d() if is_inside_tree() else null
	if cam:
		return cam.global_position
	var p := _player()
	return p.global_position if p else Vector3.ZERO


func _player() -> Node3D:
	for p in get_tree().get_nodes_in_group("player"):
		if p is Node3D and (_district == null or _district.is_ancestor_of(p)):
			return p
	return null


## The pool follows the viewer: nearest lit chimneys within the cull distance get an emitter.
func _assign_pool(snap := false) -> void:
	var vp := _view_pos()
	var cull := float(c("smoke.cull_distance", 60.0))
	var cand: Array = []
	for i in chimneys.size():
		var ch: Dictionary = chimneys[i]
		if not ch["lit"]:
			continue
		var d := vp.distance_to(ch["pos"])
		if d <= cull:
			cand.append([d, i])
	cand.sort_custom(func(a: Array, b: Array) -> bool: return a[0] < b[0])
	var want := {}
	for k in mini(cand.size(), _pool.size()):
		want[cand[k][1]] = true
	var free: Array = []
	for slot in _pool:
		if slot["chimney"] >= 0 and want.has(slot["chimney"]):
			want.erase(slot["chimney"])
		else:
			free.append(slot)
	var ratio := smoke_ratio()
	for slot in free:
		var e: GPUParticles3D = slot["node"]
		if want.is_empty():
			slot["chimney"] = -1
			e.emitting = false
			e.visible = false
			continue
		var ci: int = want.keys()[0]
		want.erase(ci)
		slot["chimney"] = ci
		e.global_position = chimneys[ci]["pos"]
		e.visible = true
		e.emitting = true
		e.restart()            # a fresh chimney: preprocess so the plume is already standing
	for slot in _pool:
		(slot["node"] as GPUParticles3D).amount_ratio = ratio


# ------------------------------------------------------------------ steady wisps (tavern windows)
func _build_wisps() -> void:
	for wdef in c("wisp_windows", []):
		var w := _window_at(int(wdef[0]), float(wdef[1]), int(wdef[2]))
		if w.is_empty():
			continue
		var b: Basis = w["basis"]
		var e := _wisp_emitter()
		e.global_transform = Transform3D(b, (w["pos"] as Vector3) + b.y * (float(w["h"]) - 0.12) + b.z * 0.02)
		add_child(e)
		_wisps.append([e, e.global_position])


func _wisp_emitter() -> GPUParticles3D:
	return _puff_emitter(int(c("wisp.particles", 10)), float(c("wisp.lifetime", 4.5)), Vector2(0.18, 0.3),
			_range("wisp.scale", Vector2(0.18, 0.4)), 2.5, _col(c("wisp.colour", [0.78, 0.76, 0.74, 0.2])), 0.06,
			Vector3(0, 0.55, 0.85), 14.0, 0.08, 0.3, 0.14)


## The window of tenement portal `i` at bay `lx`, storey `s` (any window of it if that one was skipped).
func _window_at(i: int, lx: float, s: int) -> Dictionary:
	var best: Dictionary = {}
	var bd := INF
	for w in windows:
		if w["portal"] != i:
			continue
		var d: float = absf(float(w["lx"]) - lx) + absf(int(w["storey"]) - s) * 3.0
		if d < bd:
			bd = d
			best = w
	if best.is_empty() and i >= 0 and i < portals.size():
		# every window of that house was skipped (boxes, boards): synthesise the requested one for the wisp
		var p: Array = portals[i]
		var b := Basis(Vector3.UP, float(p[2]))
		var pos: Vector3 = (p[1] as Vector3) + b * Vector3(lx, 0, FRONT + JETTY * s)
		pos.y = GF + FL * (s - 1) + 0.8
		best = {"pos": pos, "basis": b, "w": 1.1, "h": 1.85}
	return best


# ------------------------------------------------------------------ street cooking and furnaces
func _build_street_cooks() -> void:
	for sc in c("street_cooks", []):
		var pos: Vector3
		var rot := 0.0
		if sc.has("portal"):
			var i := int(sc["portal"])
			if i >= portals.size():
				continue
			var p: Array = portals[i]
			rot = float(p[2])
			pos = (p[1] as Vector3) + Basis(Vector3.UP, rot) * Vector3(float(sc["lx"]), 0.0, FRONT + float(sc["out"]))
			pos.y = 0.0
		else:
			pos = _v3(sc["pos"])
		var prop := Assets.place(self, str(sc["prop"]), pos, rot)
		var steam := _puff_emitter(int(c("steam.particles", 18)), float(c("steam.lifetime", 3.5)), Vector2(0.45, 0.75),
				_range("steam.scale", Vector2(0.25, 0.55)), 3.0, _col(c("steam.colour", [0.9, 0.9, 0.92, 0.28])), 0.08,
				Vector3.UP, 16.0, 0.12, 0.35, 0.18)
		steam.position = pos + Vector3(0, float(sc.get("steam_y", 1.5)), 0)
		steam.emitting = false
		add_child(steam)
		var light: OmniLight3D = null
		if sc.get("light", false):
			light = FlickerLight.new()
			light.amount = 0.25
			light.speed = 8.0
			light.light_color = Color(1.0, 0.52, 0.2)
			light.light_energy = 2.5
			light.omni_range = 6.0
			light.omni_attenuation = 1.4
			light.position = pos + Vector3(0, 0.45, 0)
			light.light_volumetric_fog_energy = 0.6
			add_child(light)
			light.add_to_group("flame_lights")
		var off := Basis(Vector3.UP, rot) * _v3(sc.get("cook_offset", [0, 0, 0.9]))
		_street.append({"def": sc, "pos": pos, "rot": rot, "prop": prop, "steam": steam, "light": light, "cook": null,
				"spoon": null, "cook_pos": pos + off, "t": 0.0, "on": false,
				"pot_y": float(sc.get("steam_y", 1.5)) - 0.12})


func _build_furnaces() -> void:
	for fp in furnaces:
		var pm := ParticleProcessMaterial.new()
		pm.direction = Vector3.UP
		pm.spread = 25.0
		pm.initial_velocity_min = 1.2
		pm.initial_velocity_max = 2.8
		var wind := _v3(c("wind", [0.55, 0.0, 0.25]))
		pm.gravity = Vector3(wind.x, -1.2, wind.z)
		pm.scale_min = 0.02
		pm.scale_max = 0.05
		pm.turbulence_enabled = true
		pm.turbulence_noise_strength = 2.0
		pm.color_ramp = _ramp([[0.0, Color(1.0, 0.8, 0.4, 1)], [0.6, Color(1.0, 0.4, 0.1, 0.9)], [1.0, Color(0.6, 0.1, 0.0, 0.0)]])
		var p := GPUParticles3D.new()
		p.amount = int(c("sparks.particles", 30))
		p.lifetime = float(c("sparks.lifetime", 1.6))
		p.local_coords = false
		p.process_material = pm
		var q := QuadMesh.new()
		q.size = Vector2.ONE
		var m := StandardMaterial3D.new()
		m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
		m.billboard_keep_scale = true
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m.vertex_color_use_as_albedo = true
		m.albedo_texture = smoke_texture()
		m.albedo_color = Color(4.0, 2.2, 1.0)
		q.material = m
		p.draw_pass_1 = q
		p.position = fp
		add_child(p)


func _street_update(delta: float) -> void:
	var h := fposmod(GameState.clock_minutes / 60.0, 24.0)
	var h24 := h if h >= 12.0 else h + 24.0
	var vp := _view_pos()
	for s in _street:
		var d: Dictionary = s["def"]
		var hrs: Array = d.get("hours", [17, 26])
		var active := h24 >= float(hrs[0]) and h24 < float(hrs[1])
		var near := _smoke or vp.distance_to(s["pos"]) < float(c("smoke.cull_distance", 60.0))
		(s["steam"] as GPUParticles3D).emitting = active and near
		(s["steam"] as GPUParticles3D).visible = near
		if s["light"]:
			(s["light"] as OmniLight3D).visible = active
		s["t"] = float(s["t"]) - delta
		var want_on: bool = active and near
		if want_on and float(s["t"]) <= 0.0:
			s["on"] = not s["on"]
			s["t"] = float(d.get("on_secs", 45.0)) if s["on"] else float(d.get("off_secs", 25.0))
		if not want_on:
			s["on"] = false
		if s["on"] and s["cook"] == null:
			_street_cook_in(s)
		elif not s["on"] and s["cook"] != null:
			_street_cook_out(s)
		if s["cook"] != null and s["spoon"] != null:
			var hand := _bone_pos(s["cook"], "hand_r", (s["cook_pos"] as Vector3) + Vector3(0, 1.15, 0))
			var t := Time.get_ticks_msec() / 1000.0
			var pot: Vector3 = (s["pos"] as Vector3) + Vector3(0.06 * cos(t * 2.6), float(s["pot_y"]) - 0.1, 0.06 * sin(t * 2.6))
			_stick(s["spoon"], hand, pot)


func _street_cook_in(s: Dictionary) -> void:
	var d: Dictionary = s["def"]
	var fig := _figure(d.get("models", []))
	if fig == null:
		return
	add_child(fig)
	fig.global_position = s["cook_pos"]
	var to: Vector3 = (s["pos"] as Vector3) - (s["cook_pos"] as Vector3)
	fig.rotation.y = atan2(-to.x, -to.z)
	_play_loop(fig, "cook_stir")
	s["cook"] = fig
	s["spoon"] = _spoon()
	add_child(s["spoon"])
	if s["t"] <= 0.0:
		s["t"] = float(d.get("on_secs", 45.0))
	_note("street_cook")


func _street_cook_out(s: Dictionary) -> void:
	if is_instance_valid(s["cook"]):
		(s["cook"] as Node).queue_free()
	if is_instance_valid(s["spoon"]):
		(s["spoon"] as Node).queue_free()
	s["cook"] = null
	s["spoon"] = null


func _spoon() -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = 0.012
	cm.bottom_radius = 0.016
	cm.height = 1.0
	cm.radial_segments = 6
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.32, 0.22, 0.13)
	m.roughness = 0.8
	cm.material = m
	mi.mesh = cm
	return mi


## Stretch a unit cylinder between two points.
func _stick(mi: MeshInstance3D, a: Vector3, b: Vector3) -> void:
	var d := b - a
	var L := maxf(d.length(), 0.01)
	var y := d / L
	var x := y.cross(Vector3.FORWARD if absf(y.dot(Vector3.FORWARD)) < 0.9 else Vector3.RIGHT).normalized()
	var z := x.cross(y)
	mi.global_transform = Transform3D(Basis(x, y * L, z), (a + b) * 0.5)


# ------------------------------------------------------------------ figures
func _figure(prefer: Array = []) -> Node3D:
	var names: Array = []
	for n in prefer:
		if ResourceLoader.exists("res://assets/models/%s.glb" % n):
			names.append(n)
			break
	if names.is_empty():
		# prefer townsfolk already loaded by the population (no hitch); else load one
		for path in Assets._cache.keys():
			var base := str(path).get_file().get_basename()
			if Assets._cache[path] != null and (base.begins_with("npc_") or base.begins_with("town_")):
				names.append(base)
		if names.is_empty():
			for n in ["npc_f_01", "npc_m_01", "npc_f_03", "npc_m_05"]:
				if ResourceLoader.exists("res://assets/models/%s.glb" % n):
					names.append(n)
					break
	if names.is_empty():
		return null
	# grown-ups at the windows: skip figures much shorter than the reference (children), a few tries
	var fig: Node3D = null
	for k in 4:
		if fig:
			fig.free()
		fig = Assets.character(names[_rng.randi() % names.size()])
		if fig == null or _fig_scale(fig) >= 0.9 or not prefer.is_empty():
			break
	return fig


## Pelvis height relative to the animation library's reference (0.944 m): clips authored for a 1.02 m sill scale.
func _fig_scale(fig: Node3D) -> float:
	if fig == null or not fig.has_meta("anim_skel"):
		return 1.0
	var sk: Skeleton3D = fig.get_meta("anim_skel")
	var pi := sk.find_bone("pelvis")
	if pi < 0:
		return 1.0
	var local := _rel_xf(fig, sk) * sk.get_bone_global_rest(pi).origin
	return clampf(local.y / 0.944, 0.6, 1.3)


## Transform of `n` in the space of its ancestor `root`, valid before either is in the tree.
func _rel_xf(root: Node3D, n: Node3D) -> Transform3D:
	var xf := Transform3D.IDENTITY
	var cur: Node = n
	while cur != null and cur != root:
		if cur is Node3D:
			xf = (cur as Node3D).transform * xf
		cur = cur.get_parent()
	return xf


func _play_loop(fig: Node3D, clip: String) -> void:
	var nm := Assets.resolve(fig, clip)
	if nm == "":
		return
	var ap: AnimationPlayer = fig.get_meta("anim")
	if clip in LOOP_CLIPS:
		ap.get_animation(nm).loop_mode = Animation.LOOP_LINEAR
	Assets.clear_action(fig)
	Assets.play(fig, clip)
	if ap.current_animation != "" and clip == "window_lean":
		ap.seek(_rng.randf() * ap.current_animation_length, true)


func _bone_pos(fig: Node3D, bone: String, fallback: Vector3) -> Vector3:
	if fig == null or not is_instance_valid(fig) or not fig.has_meta("anim_skel"):
		return fallback
	var sk: Skeleton3D = fig.get_meta("anim_skel")
	var bi := sk.find_bone(bone)
	if bi < 0:
		return fallback
	return sk.global_transform * sk.get_bone_global_pose(bi).origin


# ------------------------------------------------------------------ scheduler
func _process(delta: float) -> void:
	if not _ready_done:
		return
	_pool_timer -= delta
	if _pool_timer <= 0.0:
		_pool_timer = 0.5
		_assign_pool()
		var vp := _view_pos()
		var cull := float(c("smoke.cull_distance", 60.0))
		for w in _wisps:
			var near := vp.distance_to(w[1]) < cull
			(w[0] as GPUParticles3D).emitting = near
			(w[0] as GPUParticles3D).visible = near
	_street_update(delta)
	_litter_update(delta)
	for e in _events.duplicate():
		_event_update(e, delta)
	if _shot_dir() != "":
		_shots_update(delta)
		return
	if _smoke:
		_smoke_frames += 1
		if _smoke_frames % int(c("scheduler.smoke_interval_frames", 25)) == 0 and _smoke_cycle < EVENT_TYPES.size() - 1:
			var kind: String = EVENT_TYPES[_smoke_cycle]
			_smoke_cycle += 1
			var w := _pick_window(kind, true)
			if not w.is_empty():
				start_event(kind, w)
		return
	_next_event -= delta
	if _next_event <= 0.0:
		var iv := _range("scheduler.interval", Vector2(20, 60))
		_next_event = _rng.randf_range(iv.x, iv.y)
		var kind := _pick_kind()
		var w := _pick_window(kind)
		if not w.is_empty():
			start_event(kind, w)


func _pick_kind() -> String:
	var weights: Dictionary = c("scheduler.weights", {"lean": 1})
	var total := 0.0
	for k in weights:
		if k == "cat" and not ResourceLoader.exists("res://assets/models/cat.glb"):
			continue
		total += float(weights[k])
	var r := _rng.randf() * total
	for k in weights:
		if k == "cat" and not ResourceLoader.exists("res://assets/models/cat.glb"):
			continue
		r -= float(weights[k])
		if r <= 0.0:
			return k
	return "lean"


## A free window within the radius of the player (never the last one used); cooking prefers lit rooms.
func _pick_window(kind: String, any := false) -> Dictionary:
	var p := _player()
	var pp := p.global_position if p else _view_pos()
	var radius := float(c("scheduler.radius", 40.0))
	var min_d := float(c("scheduler.min_distance", 6.0))
	var cand: Array = []
	for w in windows:
		if w["busy"] or int(w["idx"]) == _last_window:
			continue
		if w["ground"] and not (kind in ["cook", "cat"]):
			continue
		var d := pp.distance_to(w["pos"])
		if not any and (d > radius or d < min_d):
			continue
		var score := _rng.randf() + (1.0 if kind == "cook" and w["lit"] else 0.0) - (d / 200.0 if any else 0.0)
		cand.append([score, w])
	if cand.is_empty():
		return {}
	cand.sort_custom(func(a: Array, b: Array) -> bool: return a[0] > b[0])
	return cand[0][1]


func _note(kind: String) -> void:
	if not fired.has(kind):
		fired.append(kind)
	if not _smoke:
		return
	_smoke_seen[kind] = true
	if not _smoke_printed and _smoke_seen.size() >= EVENT_TYPES.size() - (0 if ResourceLoader.exists("res://assets/models/cat.glb") else 1):
		_smoke_printed = true
		var names := PackedStringArray()
		for k in EVENT_TYPES:
			if _smoke_seen.has(k):
				names.append(k)
		print("[smoke] window_life chimneys=%d lit=%d emitters=%d windows=%d events=%s" % [chimneys.size(),
				chimneys.filter(func(ch: Dictionary) -> bool: return ch["lit"]).size(), _pool.size(), windows.size(), ",".join(names)])


# ------------------------------------------------------------------ window events
## Starts a window event of `kind` ("lean", "pour", "throw", "shake", "cook", "cat") at window `w`.
func start_event(kind: String, w: Dictionary, opts: Dictionary = {}) -> Dictionary:
	w["busy"] = true
	_last_window = int(w["idx"])
	Sfx.play("cat_meow" if kind == "cat" else "shutter_open", w["pos"])      # scripts/audio/sfx.gd
	var e := {"kind": kind, "win": w, "t": 0.0, "nodes": [], "fig": null, "stage": 0, "opts": opts}
	var dur: Vector2
	match kind:
		"lean": dur = _range("lean.secs", Vector2(6, 12))
		"pour": dur = Vector2(6.5, 7.5)
		"throw": dur = Vector2(5.0, 6.0)
		"shake": dur = _range("shake.secs", Vector2(5, 8))
		"cook": dur = _range("cook.secs", Vector2(20, 40))
		"cat": dur = _range("cat.secs", Vector2(25, 50))
		_: dur = Vector2(6, 8)
	e["dur"] = _rng.randf_range(dur.x, dur.y)
	if opts.has("dur"):
		e["dur"] = float(opts["dur"])
	var b: Basis = w["basis"]
	var sill: Vector3 = w["pos"]
	if kind == "cat":
		_event_cat(e, b, sill)
	else:
		_event_open(e, b, sill)
	_events.append(e)
	_note(kind)
	return e


## Card over the glass, shutters (closed, about to swing open), the figure stepping up to the sill.
func _event_open(e: Dictionary, b: Basis, sill: Vector3) -> void:
	var w: Dictionary = e["win"]
	var kind: String = e["kind"]
	var ww: float = w["w"]
	var hh: float = w["h"]
	if w.get("arched", false):
		hh -= ww * 0.5
	var cook := kind == "cook"
	# the "open window": a dark room card. Leans: in front of the frame (casement open, no mullion); the cook is
	# seen through the frame, so the card sits just in front of the glass, behind the mullions.
	var card := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(ww - 0.02, hh - 0.03)
	card.mesh = q
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.035, 0.028, 0.022)
	m.roughness = 1.0
	m.emission_enabled = true
	m.emission = Color(1.0, 0.55, 0.25) if cook or w["lit"] else Color(0.5, 0.35, 0.2)
	m.emission_energy_multiplier = 0.2 if cook else (0.12 if w["lit"] else 0.04)
	m.albedo_texture = _room_texture()
	m.emission_texture = _room_texture()
	card.material_override = m
	var card_out := -REV + 0.03 if cook else -0.035
	card.global_transform = Transform3D(b, sill + b.z * card_out + b.y * (0.03 + (hh - 0.03) * 0.5))
	add_child(card)
	card.global_transform = Transform3D(b, sill + b.z * card_out + b.y * (0.03 + (hh - 0.03) * 0.5))
	e["nodes"].append(card)
	# shutters: a pair of leaves closed over the window, hinged at the reveal edges, swung open in the first 0.8 s
	# casements: two glazed leaves closed over the opening, swinging out on the jamb hinges in the first 0.8 s (the
	# painted shutters are baked open on the facades). The cook's window stays shut: he is seen through the glass.
	if not cook:
		var hinges: Array = []
		for sx in [-1.0, 1.0]:
			var hinge := Node3D.new()
			add_child(hinge)
			hinge.global_transform = Transform3D(b, sill + b.x * (sx * (ww * 0.5 - 0.01)) + b.z * -0.03 + b.y * 0.03)
			hinge.add_child(_casement(ww * 0.5 - 0.01, hh - 0.04, -sx, w.get("asset", "")))
			hinges.append([hinge, sx])
			e["nodes"].append(hinge)
		e["hinges"] = hinges
	# the figure, stepping forward from deep in the room
	var fig := _figure()
	if fig == null:
		return
	add_child(fig)
	var back := {"lean": 0.22, "pour": 0.26, "throw": 0.26, "shake": 0.26, "cook": 0.30}.get(kind, 0.25) as float
	var lateral := 0.0
	if cook:
		lateral = (ww * 0.25) * (1.0 if _rng.randf() < 0.5 else -1.0)
	var fs := _fig_scale(fig)
	e["fig_base"] = sill + b.x * lateral + b.y * (0.03 - 1.02 * fs + (0.03 if cook else 0.07))
	e["fig_back"] = back
	e["fig_t"] = 0.0
	# pivot forward is -Z: turn it to face out of the window (+Z of the window basis)
	fig.global_transform = Transform3D(b * Basis(Vector3.UP, PI), (e["fig_base"] as Vector3) - b.z * (back + 0.6))
	e["fig"] = fig
	match kind:
		"lean":
			_play_loop(fig, "window_lean")
		"pour":
			_play_loop(fig, "window_lean")
			var vessels: Array = c("pour.vessels", ["bucket"])
			var v := Assets.instance(str(vessels[_rng.randi() % vessels.size()]))
			if v:
				add_child(v)
				e["vessel"] = v
				v.visible = false
		"throw":
			_play_loop(fig, "window_lean")
			var props: Array = c("throw.props", ["cabbage"])
			var pick := str(e["opts"].get("prop", props[_rng.randi() % props.size()]))
			var item := Assets.instance(pick)
			if item:
				add_child(item)
				item.visible = false
				e["item"] = item
				e["item_name"] = pick
		"shake":
			_play_loop(fig, "window_shake_cloth")
			var rag := Assets.instance("rag")
			if rag:
				add_child(rag)
				e["rag"] = rag
			var dust := _dust_emitter()
			add_child(dust)
			dust.emitting = false
			e["dust"] = dust
			e["nodes"].append(dust)
		"cook":
			_play_loop(fig, "cook_stir" if _rng.randf() < 0.75 else "cook_chop")
			var pot := Assets.instance("pot_on_hook")
			var pot_pos := sill + b.x * lateral + b.z * 0.02 + b.y * 0.03
			if pot:
				add_child(pot)
				pot.global_transform = Transform3D(b, pot_pos)
				e["nodes"].append(pot)
			e["pot"] = pot_pos + b.z * 0.08 + b.y * 0.1
			var spoon := _spoon()
			add_child(spoon)
			e["spoon"] = spoon
			e["nodes"].append(spoon)
			var light := FlickerLight.new()
			light.amount = 0.28
			light.speed = 6.0
			light.light_color = _col(c("cook.light_colour", [1.0, 0.52, 0.22]))
			light.light_energy = float(c("cook.light_energy", 1.6))
			light.omni_range = float(c("cook.light_range", 3.2))
			light.omni_attenuation = 1.3
			light.light_specular = 0.3
			light.light_volumetric_fog_energy = 0.5
			add_child(light)
			light.global_position = sill + b.z * 0.12 + b.y * 0.9
			light.add_to_group("flame_lights")
			e["nodes"].append(light)
			var wisp := _wisp_emitter()
			add_child(wisp)
			wisp.global_transform = Transform3D(b, sill + b.y * (hh - 0.1) + b.z * 0.0)
			e["nodes"].append(wisp)
			var steam := _puff_emitter(8, 2.2, Vector2(0.3, 0.5), Vector2(0.12, 0.26), 2.5, _col(c("steam.colour", [0.9, 0.9, 0.92, 0.28])),
					0.1, Vector3.UP, 12.0, 0.05, 0.3, 0.12)
			add_child(steam)
			steam.global_position = e["pot"]
			e["nodes"].append(steam)


## One glazed casement leaf (frame, transom, dark crown glass), extending `dir` (+1 / -1 along x) from its hinge.
func _casement(width: float, height: float, dir: float, asset: String) -> Node3D:
	var leaf := Node3D.new()
	var wood := StandardMaterial3D.new()
	wood.albedo_color = {"tenement_d": Color(0.30, 0.12, 0.09), "tenement_e": Color(0.34, 0.26, 0.14)}.get(asset, Color(0.22, 0.15, 0.09))
	wood.roughness = 0.8
	var glass := StandardMaterial3D.new()
	glass.albedo_color = Color(0.08, 0.10, 0.13, 0.55)
	glass.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glass.roughness = 0.05
	glass.metallic_specular = 0.9
	var t := 0.055
	var bars := [[width * 0.5, t * 0.5, width, t], [width * 0.5, height - t * 0.5, width, t], [t * 0.5, height * 0.5, t, height],
			[width - t * 0.5, height * 0.5, t, height], [width * 0.5, height * 0.66, width, t * 0.8]]
	for bar in bars:
		var mi := MeshInstance3D.new()
		var bm := BoxMesh.new()
		bm.size = Vector3(float(bar[2]), float(bar[3]), 0.045)
		mi.mesh = bm
		mi.material_override = wood
		mi.position = Vector3(dir * float(bar[0]), float(bar[1]), 0.0)
		leaf.add_child(mi)
	var pane := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(width - t * 2.0, height - t * 2.0)
	pane.mesh = q
	pane.material_override = glass
	pane.position = Vector3(dir * width * 0.5, height * 0.5, 0.0)
	leaf.add_child(pane)
	return leaf


var _room_tex: ImageTexture
func _room_texture() -> ImageTexture:
	if _room_tex:
		return _room_tex
	var img := Image.create(16, 32, false, Image.FORMAT_RGBA8)
	for y in 32:
		for x in 16:
			var v := 0.55 + 0.45 * (1.0 - float(y) / 31.0)            # warmer, brighter toward the lamp above
			var edge := minf(minf(x, 15 - x) / 4.0, 1.0)
			img.set_pixel(x, y, Color(v * (0.6 + 0.4 * edge), v * (0.6 + 0.4 * edge), v * (0.6 + 0.4 * edge)))
	_room_tex = ImageTexture.create_from_image(img)
	return _room_tex


func _event_cat(e: Dictionary, b: Basis, sill: Vector3) -> void:
	if not ResourceLoader.exists("res://assets/models/cat.glb"):
		e["dur"] = 0.0
		return
	var cat := Assets.instance("cat")
	add_child(cat)
	for sb in cat.find_children("*", "StaticBody3D", true, false):
		sb.queue_free()
	var side := 1.0 if _rng.randf() < 0.5 else -1.0
	# along the sill, head turned a little toward the street
	cat.global_transform = Transform3D(b * Basis(Vector3.UP, side * (PI * 0.5 - 0.35)),
			sill + b.x * (side * -0.15) + b.z * 0.0 + b.y * 0.03)
	for ap in cat.find_children("*", "AnimationPlayer", true, false):
		var a := ap as AnimationPlayer
		var clip := "sit" if a.has_animation("sit") else ("idle" if a.has_animation("idle") else "")
		if clip != "":
			a.get_animation(clip).loop_mode = Animation.LOOP_NONE if clip == "sit" else Animation.LOOP_LINEAR
			a.play(clip)
	e["nodes"].append(cat)


func _event_update(e: Dictionary, delta: float) -> void:
	e["t"] = float(e["t"]) + delta
	var t: float = e["t"]
	var dur: float = e["dur"]
	var w: Dictionary = e["win"]
	var b: Basis = w["basis"]
	var sill: Vector3 = w["pos"]
	var kind: String = e["kind"]
	# shutters: open over 0.8 s, close over the last 0.8 s
	if e.has("hinges"):
		var open := clampf(t / 0.8, 0.0, 1.0) * clampf((dur - t) / 0.8, 0.0, 1.0)
		open = open * open * (3.0 - 2.0 * open)
		for hp in e["hinges"]:
			var hinge: Node3D = hp[0]
			if is_instance_valid(hinge):
				hinge.global_transform = Transform3D(b * Basis(Vector3.UP, float(hp[1]) * open * deg_to_rad(100.0)), hinge.global_position)
	# the figure steps up to the sill after the shutters, and back before they close
	var fig: Node3D = e["fig"]
	if fig and is_instance_valid(fig):
		var step := clampf((t - 0.5) / 0.7, 0.0, 1.0) * clampf((dur - 0.9 - t) / 0.7, 0.0, 1.0)
		step = step * step * (3.0 - 2.0 * step)
		var back: float = e["fig_back"]
		fig.global_position = (e["fig_base"] as Vector3) - b.z * (back + 0.6 * (1.0 - step))
	match kind:
		"pour": _pour_update(e, t, b, sill)
		"throw": _throw_update(e, t, b, sill)
		"shake":
			var rag: Node3D = e.get("rag")
			var mid := _hands_mid(fig, sill + b.z * 0.25 + b.y * 0.3)
			if rag and is_instance_valid(rag):
				rag.global_transform = Transform3D(b * Basis(Vector3.RIGHT, -1.2 + 0.4 * sin(t * TAU * 2.0)), mid + b.z * 0.08 - b.y * 0.12)
			var dust: GPUParticles3D = e["dust"]
			dust.global_position = mid + b.z * 0.12 - b.y * 0.1
			dust.emitting = t > 1.3 and t < dur - 1.2
		"cook":
			if e.has("spoon"):
				var hand := _bone_pos(fig, "hand_r", (e["pot"] as Vector3) + b.y * 0.3)
				var pot: Vector3 = (e["pot"] as Vector3) + b.x * 0.03 * cos(t * 2.6) + b.z * 0.03 * sin(t * 2.6)
				_stick(e["spoon"], hand, pot)
	if t >= dur:
		_event_end(e)


func _hands_mid(fig: Node3D, fallback: Vector3) -> Vector3:
	if fig == null or not is_instance_valid(fig):
		return fallback
	return (_bone_pos(fig, "hand_l", fallback) + _bone_pos(fig, "hand_r", fallback)) * 0.5


## Pour: at 1.4 s the figure plays window_pour; the vessel rides between its hands and tips (clip 0.8-1.3 s),
## water streams 1.25-2.45 s into the clip, splashes where it lands, leaves a wet patch and makes a noise.
func _pour_update(e: Dictionary, t: float, b: Basis, sill: Vector3) -> void:
	var fig: Node3D = e["fig"]
	var start := 1.4
	var ct := t - start
	if e["stage"] == 0 and t >= start and fig:
		e["stage"] = 1
		Assets.play_action(fig, "window_pour")
		# one short bark per pour, on the window figure itself (Walker.speech applies the crowd-text budget)
		var barks: Array = c("pour.barks", ["Uwaga! Woda!"])
		Walker.speech(fig, str(barks[_rng.randi() % barks.size()]), 2.6, 1.95)
	var v: Node3D = e.get("vessel")
	if v and is_instance_valid(v):
		v.visible = e["stage"] >= 1 and ct < 3.2
		var tilt := 0.0
		if ct > 0.8:
			tilt = clampf((ct - 0.8) / 0.5, 0.0, 1.0) * clampf((2.8 - ct) / 0.4, 0.0, 1.0)
		var mid := _hands_mid(fig, sill + b.z * 0.2 + b.y * 0.2)
		# base between the hands, tipping over its front lip toward the street
		v.global_transform = Transform3D(b * Basis(Vector3.RIGHT, tilt * deg_to_rad(115.0)), mid - b.y * 0.12)
	if e["stage"] == 1 and ct >= 1.25:
		e["stage"] = 2
		var lip := (_hands_mid(fig, sill) if fig else sill) + b.z * 0.2
		var stream := _stream_emitter()
		add_child(stream)
		stream.global_transform = Transform3D(b, lip)
		stream.emitting = true
		e["stream"] = stream
		e["nodes"].append(stream)
		var fall := sqrt(2.0 * maxf(lip.y, 0.5) / 9.8)
		e["splash_at"] = t + fall
		e["splash_pos"] = Vector3(lip.x, 0.0, lip.z) + b.z * (0.9 * fall)
	if e["stage"] >= 1 and ct > 3.3 and not e.has("relaxed") and fig and not Assets.is_action(fig):
		e["relaxed"] = true
		_play_loop(fig, "window_lean")
	if e["stage"] == 2:
		if ct >= 2.45 and e.has("stream"):
			(e["stream"] as GPUParticles3D).emitting = false
		if t >= float(e["splash_at"]):
			e["stage"] = 3
			_splash(e["splash_pos"])


func _stream_emitter() -> GPUParticles3D:
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = Vector3(0.05, 0.02, 0.03)
	pm.direction = Vector3(0, -0.2, 1)
	pm.spread = 5.0
	pm.initial_velocity_min = 0.7
	pm.initial_velocity_max = 1.1
	pm.gravity = Vector3(0, -9.8, 0)
	pm.scale_min = 0.6
	pm.scale_max = 1.2
	pm.color_ramp = _ramp([[0.0, Color(1, 1, 1, 0.9)], [0.8, Color(1, 1, 1, 0.7)], [1.0, Color(1, 1, 1, 0.0)]])
	var p := GPUParticles3D.new()
	p.amount = 160
	p.lifetime = 1.8
	p.local_coords = false
	p.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(0.11, 0.5)
	q.material = _drop_material(Color(0.66, 0.70, 0.74, 0.8), 0.45)
	p.draw_pass_1 = q
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	p.visibility_aabb = AABB(Vector3(-2, -14, -2), Vector3(4, 16, 6))
	return p


func _splash(pos: Vector3) -> void:
	var pm := ParticleProcessMaterial.new()
	pm.direction = Vector3.UP
	pm.spread = 55.0
	pm.initial_velocity_min = 1.2
	pm.initial_velocity_max = 2.6
	pm.gravity = Vector3(0, -9.8, 0)
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
	pm.emission_sphere_radius = 0.25
	pm.scale_min = 0.5
	pm.scale_max = 1.0
	pm.color_ramp = _ramp([[0.0, Color(1, 1, 1, 0.9)], [1.0, Color(1, 1, 1, 0.0)]])
	var p := GPUParticles3D.new()
	p.amount = 40
	p.lifetime = 0.8
	p.explosiveness = 0.35
	p.local_coords = false
	p.process_material = pm
	var q := QuadMesh.new()
	q.size = Vector2(0.05, 0.1)
	q.material = _drop_material(Color(0.7, 0.72, 0.75, 0.6), 0.25)
	p.draw_pass_1 = q
	add_child(p)
	p.global_position = pos + Vector3(0, 0.05, 0)
	p.emitting = true
	_litter.append([p, 2.2, "fx"])
	# the wet patch: a dark, glossy decal on the setts, fading out over pour.puddle_secs
	var d := Decal.new()
	d.size = Vector3(2.2, 1.2, 1.8)
	d.texture_albedo = blot_texture()
	d.texture_orm = _wet_orm()
	d.albedo_mix = 1.0
	d.upper_fade = 0.3
	d.lower_fade = 0.3
	add_child(d)
	d.global_position = pos + Vector3(0, 0.1, 0)
	d.rotation.y = _rng.randf() * TAU
	var secs := float(c("pour.puddle_secs", 60.0))
	_litter.append([d, secs, "puddle", secs])
	_sound(pos, float(c("pour.loudness", 0.6)), "splash")
	_startle(pos)


var _streak_tex: ImageTexture
func _streak_texture() -> ImageTexture:
	if _streak_tex:
		return _streak_tex
	var img := Image.create(16, 64, false, Image.FORMAT_RGBA8)
	for y in 64:
		for x in 16:
			var ax := absf((x + 0.5) / 8.0 - 1.0)
			var ay := absf((y + 0.5) / 32.0 - 1.0)
			var a := clampf(1.0 - ax, 0.0, 1.0) * clampf(1.2 - ay * ay, 0.0, 1.0)
			img.set_pixel(x, y, Color(1, 1, 1, a))
	img.generate_mipmaps()
	_streak_tex = ImageTexture.create_from_image(img)
	return _streak_tex


var _orm_tex: ImageTexture
func _wet_orm() -> ImageTexture:
	if _orm_tex:
		return _orm_tex
	var img := Image.create(4, 4, false, Image.FORMAT_RGBA8)
	img.fill(Color(1.0, 0.06, 0.0, 1.0))
	_orm_tex = ImageTexture.create_from_image(img)
	return _orm_tex


## Throw: the item rides in the right hand from 1.2 s, window_throw starts at 1.4 s, the hand lets go at 0.78 s.
func _throw_update(e: Dictionary, t: float, b: Basis, sill: Vector3) -> void:
	var fig: Node3D = e["fig"]
	var start := 1.4
	var item: Node3D = e.get("item")
	if e["stage"] == 0 and t >= 1.2:
		e["stage"] = 1
		if item:
			item.visible = true
	if e["stage"] == 1 and t >= start and fig:
		e["stage"] = 2
		Assets.play_action(fig, "window_throw")
	if e["stage"] in [1, 2] and item and is_instance_valid(item):
		item.global_position = _bone_pos(fig, "hand_r", sill + b.z * 0.2 + b.y * 0.3) - b.y * 0.05
	if e["stage"] == 2 and t >= start + THROW_RELEASE:
		e["stage"] = 3
		if item and is_instance_valid(item):
			var at := item.global_position
			item.get_parent().remove_child(item)
			_launch(item, str(e.get("item_name", "cabbage")), at, b)
			e.erase("item")
	if e["stage"] == 3 and fig and not Assets.is_action(fig):
		e["stage"] = 4
		_play_loop(fig, "window_lean")


func _launch(item: Node3D, pick: String, at: Vector3, b: Basis) -> void:
	var body := RigidBody3D.new()
	body.name = "Thrown_" + pick
	body.collision_layer = 0          # nothing collides with it (walkers step over it); it lands on the world
	body.collision_mask = 1
	body.mass = 0.8
	body.continuous_cd = true
	var pmat := PhysicsMaterial.new()
	pmat.bounce = 0.45 if pick in ["cabbage", "bone"] else 0.3
	pmat.friction = 0.9
	body.physics_material_override = pmat
	body.angular_damp = 1.5
	var shape := CollisionShape3D.new()
	match pick:
		"cabbage":
			var s := SphereShape3D.new()
			s.radius = 0.1
			shape.shape = s
			shape.position.y = 0.09
		"bottle":
			var cs := CylinderShape3D.new()
			cs.radius = 0.045
			cs.height = 0.3
			shape.shape = cs
			shape.position.y = 0.15
		_:
			var bs := BoxShape3D.new()
			bs.size = Vector3(0.26, 0.06, 0.2)
			shape.shape = bs
			shape.position.y = 0.03
	body.add_child(shape)
	item.position = Vector3.ZERO
	body.add_child(item)
	add_child(body)
	body.global_position = at
	var sp := _range("throw.speed", Vector2(2.2, 3.4))
	body.linear_velocity = b.z * _rng.randf_range(sp.x, sp.y) + Vector3.UP * 1.4 + b.x * _rng.randf_range(-0.6, 0.6)
	body.angular_velocity = Vector3(_rng.randf_range(-6, 6), _rng.randf_range(-3, 3), _rng.randf_range(-6, 6))
	var stay := float(c("throw.stay_secs", 90.0))
	_litter.append([body, stay, "thrown", stay, false])
	body.contact_monitor = true          # the thud when it lands (scripts/audio/sfx.gd)
	body.max_contacts_reported = 1
	body.body_entered.connect(func(_b: Node) -> void: Sfx.play("stone" if pick == "bottle" else "cabbage", body.global_position), CONNECT_ONE_SHOT)


func _dust_emitter() -> GPUParticles3D:
	var p := _puff_emitter(30, 2.6, Vector2(0.2, 0.6), Vector2(0.1, 0.3), 3.0, Color(0.72, 0.66, 0.58, 0.35), 0.04,
			Vector3(0, -0.4, 1.0), 40.0, 0.12, 0.8, -0.3)
	p.preprocess = 0.0
	return p


func _event_end(e: Dictionary) -> void:
	_events.erase(e)
	(e["win"] as Dictionary)["busy"] = false
	for n in e["nodes"]:
		if is_instance_valid(n):
			(n as Node).queue_free()
	for k in ["fig", "vessel", "item", "rag"]:
		if e.get(k) != null and is_instance_valid(e[k]):
			(e[k] as Node).queue_free()


func _litter_update(delta: float) -> void:
	for l in _litter.duplicate():
		var n: Node3D = l[0]
		if not is_instance_valid(n):
			_litter.erase(l)
			continue
		l[1] = float(l[1]) - delta
		match l[2]:
			"puddle":
				(n as Decal).modulate.a = clampf(float(l[1]) / float(l[3]), 0.0, 1.0)
			"thrown":
				if not l[4] and n.global_position.y < 0.4 and (n as RigidBody3D).linear_velocity.y <= 0.5:
					l[4] = true
					_sound(n.global_position, float(c("throw.loudness", 0.4)), "thud")
				if float(l[1]) < 2.0:
					n.scale = Vector3.ONE * maxf(float(l[1]) / 2.0, 0.01)
		if float(l[1]) <= 0.0:
			n.queue_free()
			_litter.erase(l)


# ------------------------------------------------------------------ stealth hooks
func _sound(pos: Vector3, loudness: float, kind: String) -> void:
	for wn in get_tree().get_nodes_in_group("watch"):
		if _district and not _district.is_ancestor_of(wn):
			continue
		if wn.has_method("sound_event"):
			wn.call("sound_event", pos, loudness)
		elif wn.has_method("emit_sound"):
			wn.call("emit_sound", pos, loudness, kind)
		return


func _startle(pos: Vector3) -> void:
	var r := float(c("pour.startle_radius", 2.0))
	for n in get_tree().get_nodes_in_group("npcs"):
		if n is Node3D and (n as Node3D).global_position.distance_to(pos) < r and n.has_method("startle"):
			n.call("startle", pos)


# ------------------------------------------------------------------ inspection shots (`-- --window-shot=/dir`)
var _shot_t := 0.0
var _shot_cam: Camera3D
var _shot_state: Dictionary = {}

func _shot_dir() -> String:
	if DisplayServer.get_name() == "headless":
		return ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--window-shot="):
			return a.trim_prefix("--window-shot=")
	return ""


const SHOTS := ["smoke_moon", "smoke_moon_nogi", "smoke_roofs", "pour", "pour_close", "pour_ground", "throw", "cook", "cook_close", "lean",
		"lean_side", "shake", "cat", "brazier", "brazier_nogi", "inn_yard"]


func _shot_list() -> Array:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--window-shot-only="):
			return Array(a.trim_prefix("--window-shot-only=").split(","))
	return SHOTS


func _shots_update(delta: float) -> void:
	var shots := _shot_list()
	if _shot_index >= shots.size():
		return
	var name_: String = shots[_shot_index]
	for cl in get_tree().root.find_children("*", "CanvasLayer", true, false):
		(cl as CanvasLayer).visible = false
	if _district:
		for lb in _district.find_children("SpeechBubble*", "Label3D", true, false):
			if not is_ancestor_of(lb):
				(lb as Label3D).visible = false
	if _shot_cam == null:
		_shot_cam = Camera3D.new()
		_shot_cam.fov = 60
		add_child(_shot_cam)
		_shot_state = {}
		_shot_t = 0.0
		_shot_setup(name_)
	_shot_cam.current = true
	_shot_t += delta
	var wait: float = _shot_state.get("wait", 2.0)
	if _shot_state.has("follow"):
		_shot_follow(name_)
	if _shot_t >= wait:
		var dir := _shot_dir()
		DirAccess.make_dir_recursive_absolute(dir)
		get_viewport().get_texture().get_image().save_png(dir.path_join("window_%s.png" % name_))
		print("[smoke] window shot ", name_)
		_set_gi(true)
		_shot_index += 1
		_shot_cam.queue_free()
		_shot_cam = null
		if _shot_index >= shots.size():
			for cl in get_tree().root.find_children("*", "CanvasLayer", true, false):
				(cl as CanvasLayer).visible = true
			print("[smoke] window shots in ", dir)


func _shot_window(storey: int, idx_hint: int, need_shutters := false) -> Dictionary:
	var list := windows.filter(func(w: Dictionary) -> bool: return int(w["storey"]) == storey and not w["busy"] and (not need_shutters or w["shutters"]))
	if list.is_empty() and need_shutters:
		list = windows.filter(func(w: Dictionary) -> bool: return int(w["storey"]) == storey and not w["busy"])
	if list.is_empty():
		list = windows.filter(func(w: Dictionary) -> bool: return not w["busy"])
	if list.is_empty():
		return {}
	return list[idx_hint % list.size()]


func _look_at_window(w: Dictionary, dist: float, side: float, height: float, target_dy := 0.8) -> void:
	var b: Basis = w["basis"]
	var sill: Vector3 = w["pos"]
	var cam := sill + b.z * dist + b.x * side
	cam.y = height
	_shot_cam.look_at_from_position(cam, sill + b.y * target_dy)


func _set_gi(on: bool) -> void:
	var env: WorldEnvironment = null
	for n in get_tree().root.find_children("*", "WorldEnvironment", true, false):
		env = n
	if env == null or env.environment == null:
		return
	var e := env.environment
	var want: bool = on and GameState.settings.get("gi", true)
	e.sdfgi_enabled = want
	e.ssil_enabled = want
	e.volumetric_fog_enabled = want


func _shot_setup(name_: String) -> void:
	_set_gi(not name_.ends_with("_nogi"))
	match name_:
		"smoke_moon", "smoke_moon_nogi":
			var cam := Vector3(-4.0, 1.7, 7.6)
			var md := Vector3(0.533, 0.559, 0.635)
			for l in get_tree().get_nodes_in_group("moon_light"):
				if l is Node3D and _district and _district.is_ancestor_of(l):
					md = (l as Node3D).global_transform.basis.z.normalized()
			_shot_cam.look_at_from_position(cam, cam + (md - Vector3(0, 0.12, 0)).normalized() * 30.0)
			_shot_state["wait"] = 4.0
		"smoke_roofs":
			var cam := Vector3(-12.0, 1.7, -11.0)
			_shot_cam.look_at_from_position(cam, Vector3(-2.0, 15.0, -34.0))
			_shot_state["wait"] = 2.0
		"pour", "pour_ground", "pour_close":
			var w := _shot_window(1, 3)
			if w.is_empty():
				return
			start_event("pour", w, {"dur": 12.0})
			_look_at_window(w, 7.5, 3.5, 1.7, 0.0 if name_ == "pour" else -3.0)
			if name_ == "pour_ground":
				_look_at_window(w, 4.5, 2.2, 1.5, -4.2)
			if name_ == "pour_close":
				_look_at_window(w, 3.2, 2.6, 1.6, -1.2)
			_shot_state["wait"] = 1.4 + 2.35 if name_ == "pour" else (1.4 + 2.1 if name_ == "pour_close" else 1.4 + 4.5)
		"throw":
			var w := _shot_window(1, 5)
			if w.is_empty():
				return
			var e := start_event("throw", w, {"dur": 8.0, "prop": "cabbage"})
			_look_at_window(w, 6.0, 2.5, 1.7, 0.0)
			_shot_state["wait"] = 4.5
			_shot_state["follow"] = e
		"cook", "cook_close":
			var w := _shot_window(1, 7)
			if w.is_empty():
				return
			start_event("cook", w, {"dur": 20.0})
			if name_ == "cook":
				_look_at_window(w, 8.0, -2.5, 1.7, 1.0)
			else:
				_look_at_window(w, 3.5, -1.0, float((w["pos"] as Vector3).y) + 0.4, 0.9)
			_shot_state["wait"] = 3.0
		"lean", "lean_side":
			var w := _shot_window(1, 2, true)
			if w.is_empty():
				return
			start_event("lean", w, {"dur": 12.0})
			if name_ == "lean":
				_look_at_window(w, 6.0, 1.5, 1.7, 1.0)
			else:
				_look_at_window(w, 2.2, 2.2, float((w["pos"] as Vector3).y) + 0.3, 0.6)
			_shot_state["wait"] = 3.0
		"shake":
			var w := _shot_window(2, 1)
			if w.is_empty():
				return
			start_event("shake", w, {"dur": 10.0})
			_look_at_window(w, 7.0, -2.0, 1.7, 0.8)
			_shot_state["wait"] = 3.2
		"cat":
			var w := _shot_window(1, 4)
			if w.is_empty():
				return
			start_event("cat", w, {"dur": 10.0})
			_look_at_window(w, 3.0, 1.0, float((w["pos"] as Vector3).y) + 0.2, 0.2)
			_shot_state["wait"] = 1.5
		"brazier", "brazier_nogi":
			for s in _street:
				if str(s["def"]["id"]) == "cafe_brazier":
					s["on"] = true
					s["t"] = 60.0
					var p: Vector3 = s["pos"]
					var rot: float = s["rot"]
					var fwd := Vector3(sin(rot), 0, cos(rot))
					var side := Vector3(fwd.z, 0, -fwd.x)
					_shot_cam.look_at_from_position(p + fwd * 3.6 + side * 1.6 + Vector3(0, 1.6, 0), p + Vector3(0, 1.4, 0))
			_shot_state["wait"] = 3.0
		"inn_yard":
			for s in _street:
				if str(s["def"]["id"]) == "inn_yard":
					s["on"] = true
					s["t"] = 60.0
					var p: Vector3 = s["pos"]
					_shot_cam.look_at_from_position(p + Vector3(-3.2, 1.6, -2.0), p + Vector3(0, 0.8, 0))
			_shot_state["wait"] = 3.0


func _shot_follow(name_: String) -> void:
	if name_ != "throw" or _shot_t < 3.6:
		return
	for l in _litter:
		if l[2] == "thrown" and is_instance_valid(l[0]):
			var p: Vector3 = (l[0] as Node3D).global_position
			var e: Dictionary = _shot_state["follow"]
			var b: Basis = e["win"]["basis"]
			_shot_cam.look_at_from_position(p + b.z * 1.6 + b.x * 0.9 + Vector3(0, 0.9, 0), p + Vector3(0, 0.08, 0))
