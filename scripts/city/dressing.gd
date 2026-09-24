extends Node3D
## The lived-in pass: flavour props that make the Rynek look used on a winter night (assets from the DRESSING
## section of assets/blender/build_assets.py). Instanced by greybox_district.gd after the market furniture, so the
## -colonly boxes of the benches, coach, trees, railings etc. are baked into the navmesh with everything else.
##
## Wall pieces are placed on the tenement facades from the district's `portals` ([asset, centre, rot_y] per module,
## in _row() order: north 0-4, south 5-9, west 10-13, east 14-15). The module geometry below mirrors tenement() in
## build_assets.py: facade plane 4 m in front of the module centre, ground floor 4.2 m, upper storeys 3.3 m, each
## jettied 0.22 m further out; the door is in the middle bay (first bay for the two-bay modules).
## Everything except the trees, the cafe tables and the churchyard green stays within ~1.5 m of a facade, clear of
## the patrol routes and the street corridors.
##
## `-- --dress-shot=/dir` (needs a window) saves close-ups of the dressing, night and lit, for checking placement.

const FRONT := 4.0
const GF := 4.2
const FL := 3.3
const JETTY := 0.22
const SIGN_Y := 3.45            ## guild bracket arm height on the ground floor
const BOARD_Y := 4.36           ## fascia board bottom: on the first-floor face, above the string course
const MODS := {
	"tenement_a": {"px": 0.0, "xs": [-3.333, 0.0, 3.333], "storeys": 3},
	"tenement_b": {"px": -2.0, "xs": [-2.0, 2.0], "storeys": 3},
	"tenement_c": {"px": 0.0, "xs": [-4.0, 0.0, 4.0], "storeys": 4},
	"tenement_d": {"px": 0.0, "xs": [-3.333, 0.0, 3.333], "storeys": 3},
	"tenement_e": {"px": -2.0, "xs": [-2.0, 2.0], "storeys": 4},
}
## Market stalls as _furniture() places them: straw is trodden in round their fronts.
const STALLS := [[Vector3(-14, 0, -14), 0.0], [Vector3(-10, 0, -14), 0.0], [Vector3(-6, 0, -16), 0.3],
		[Vector3(10, 0, 13), PI], [Vector3(14, 0, 13), PI], [Vector3(6, 0, 15), PI - 0.3],
		[Vector3(-20, 0, -4), PI * 0.5], [Vector3(20, 0, -10), -PI * 0.5], [Vector3(20, 0, -6), -PI * 0.5]]

var portals: Array = []
var _rng := RandomNumberGenerator.new()
var _boards := {}               ## portal -> lx of its fascia board (no window box over it)

static var _shot_done := false


func _ready() -> void:
	name = "Dressing"
	_rng.seed = 1795
	if portals.size() >= 16:
		_shops()
		_cafe()
		_inn()
		_homes()
	_churchyard()
	_benches()
	_plants()
	_clutter()
	_weeds()
	_feather_slush(self)
	add_child(preload("res://scripts/city/vendors.gd").new())     # street sellers and hawkers (data/vendors.json)
	add_child(preload("res://scripts/city/window_life.gd").create(portals, _boards))   # windows, chimneys (data/window_life.json)
	add_child(preload("res://scripts/city/street_life.gd").new())   # night life and crime (data/street_life.json)
	var dir := _shot_dir()
	if dir != "" and not _shot_done:
		_shot_done = true
		_shots.call_deferred(dir)


# ------------------------------------------------------------------ helpers
## Point on tenement `i`'s facade: `lx` along it (module space, +x to the right looking at the front), `y` up,
## `out` metres in front of the ground-floor face.
func _wp(i: int, lx: float, y: float, out: float) -> Vector3:
	var p: Array = portals[i]
	var pos: Vector3 = (p[1] as Vector3) + Basis(Vector3.UP, float(p[2])) * Vector3(lx, 0.0, FRONT + out)
	pos.y = y
	return pos


func _wall(i: int, asset: String, lx: float, y: float = 0.0, out: float = 0.0, rot_off: float = 0.0) -> Node3D:
	return Assets.place(self, asset, _wp(i, lx, y, out), float(portals[i][2]) + rot_off)


func _mod(i: int) -> Dictionary:
	return MODS.get(portals[i][0], MODS["tenement_a"])


## Window boxes under the upper windows of tenement i (every `step`th window, from storey 1 up to `top`).
func _window_boxes(i: int, top: int = 2, skip_lx: Array = []) -> void:
	var m := _mod(i)
	for s in range(1, mini(top, int(m["storeys"]) - 1) + 1):
		for x in m["xs"]:
			if skip_lx.has(x) or _rng.randf() < 0.3:
				continue
			if s == 1 and _boards.has(i) and absf(float(_boards[i]) - float(x)) < 1.5:
				continue
			_wall(i, "window_box", float(x), GF + FL * (s - 1) + 0.8 - 0.12, JETTY * s)


func _lamp(pos: Vector3, energy: float = 2.4, rng: float = 7.0, colour: Color = Color(1.0, 0.70, 0.40)) -> void:
	var l := OmniLight3D.new()
	l.position = pos
	l.light_color = colour
	l.light_energy = energy
	l.omni_range = rng
	l.omni_attenuation = 1.5
	l.light_specular = 0.5
	l.light_volumetric_fog_energy = 0.8
	add_child(l)


## A painted fascia board on the first-floor face over bay `lx`.
func _board(i: int, asset: String, lx: float, dy: float = 0.0) -> void:
	_boards[i] = lx
	_wall(i, asset, lx, BOARD_Y + dy, JETTY)


## A wall lantern over a door, with its light.
func _wall_lantern(i: int, lx: float, y: float = 3.0) -> void:
	_wall(i, "wall_lantern", lx, y, 0.0)
	_lamp(_wp(i, lx, y - 0.45, 0.62), 2.2, 7.0)


# ------------------------------------------------------------------ shop fronts and guild signs
func _shops() -> void:
	# 0  north, tenement_a: the wine cellar. Grapes, a board, the cellar hatch under the right-hand window, a cask.
	_board(0, "sign_winiarnia", -3.333)
	_wall(0, "guild_grapes", -2.05, SIGN_Y)
	_wall(0, "cellar_hatch", 3.333, 0.0, 0.08)
	_wall(0, "barrel", 4.55, 0.0, 0.6, _rng.randf() * TAU)
	_wall(0, "trampled_snow", 0.0, 0.0, 0.08)
	# 1  north, tenement_b: the baker. Pretzel, board, loaves on the ledge, flour sacks at the door.
	_board(1, "sign_piekarnia", 2.0)
	_wall(1, "guild_pretzel", 3.4, SIGN_Y)
	_wall(1, "shopfront_bakery", 2.0)
	_wall(1, "sacks_crates", 3.6, 0.0, 0.5, 0.1)
	_wall(1, "doormat_scraper", -2.0, 0.0, 0.95)
	# 2  north, tenement_c: the shoemaker. Boot on its bracket, an awning, a porter's handcart.
	_wall(2, "guild_boot", -2.05, SIGN_Y)
	_wall(2, "awning_striped", 4.0, 3.8, 0.0)
	_wall(2, "handcart", -4.3, 0.0, 0.95, PI * 0.5 + 0.1)
	_wall(2, "shovel_broom", 5.5, 0.0, 0.08)
	_wall(2, "trampled_snow", 0.0, 0.0, 0.08)
	# 4  north, tenement_e: the goldsmith. Ring, board, a lantern by the door, a juniper.
	_board(4, "sign_goldschmied", 2.0)
	_wall(4, "guild_ring", 3.4, SIGN_Y)
	_wall_lantern(4, -0.45)
	_wall(4, "shrub_juniper", -3.25, 0.0, 0.6)
	_wall(4, "doormat_scraper", -2.0, 0.0, 0.95)
	# 6  south, tenement_d: the apothecary. Mortar, board, bottles and jars in the window.
	_board(6, "sign_apotheke", 3.333)
	_wall(6, "guild_mortar", -2.05, SIGN_Y)
	_wall(6, "shopfront_bottles", 3.333)
	_wall(6, "doormat_scraper", 0.0, 0.0, 0.95)
	# 7  south, tenement_a: the locksmith. Key; his sledge of charcoal by the wall.
	_wall(7, "guild_key", -2.05, SIGN_Y)
	_wall(7, "sledge", 3.9, 0.0, 0.5, PI * 0.5)
	_wall(7, "door_wreath", 0.5, 1.8, -0.065)
	_wall(7, "trampled_snow", 0.0, 0.0, 0.08)
	# 9  south, tenement_c: the tailor and draper. Scissors, bolts of cloth, an awning.
	_wall(9, "guild_scissors", -2.05, SIGN_Y)
	_wall(9, "shopfront_cloth", -4.0)
	_wall(9, "awning_striped", -4.0, 3.8, 0.0)
	# 10 west, tenement_d: the beer hall. Tankard, a bench under the window, casks.
	_wall(10, "guild_tankard", -2.05, SIGN_Y)
	_wall(10, "bench_wood", 3.333, 0.0, 0.4)
	_wall(10, "barrel", 4.5, 0.0, 0.6, _rng.randf() * TAU)
	_wall(10, "barrel", -4.3, 0.0, 0.75, _rng.randf() * TAU)
	_wall(10, "trampled_snow", 0.0, 0.0, 0.08)
	# 11 west, tenement_e: a cloth merchant. Bolts in the window, an awning, deliveries.
	_wall(11, "shopfront_cloth", 2.0)
	_wall(11, "awning_striped", 2.0, 3.8, 0.0)
	_wall(11, "sacks_crates", 3.6, 0.0, 0.5, -0.1)
	# 12 west, tenement_a: a cooper's yard. Firewood under a lean-to, a sledge, a broom.
	_wall(12, "woodpile_leanto", 3.4, 0.0, 0.08)
	_wall(12, "sledge", -3.6, 0.0, 0.5, PI * 0.5)
	_wall(12, "shovel_broom", -1.9, 0.0, 0.08, 0.0)
	# 15 east, tenement_a: a chandler. Crates at the door, a broom.
	_wall(15, "sacks_crates", 3.6, 0.0, 0.5, 0.15)
	_wall(15, "shovel_broom", -3.0, 0.0, 0.08)
	_wall(15, "trampled_snow", 0.0, 0.0, 0.08)


# ------------------------------------------------------------------ the kawiarnia (south row, west end, by the Town Hall)
func _cafe() -> void:
	var i := 5
	_board(i, "sign_kawiarnia", 2.0)
	_wall(i, "oriel_cafe", -2.0, 5.0, JETTY)
	_wall(i, "awning_striped", 2.0, 3.8, 0.0)
	_wall(i, "guild_coffee", 3.45, SIGN_Y)
	_wall(i, "bench_wood", 2.0, 0.0, 0.4)
	_wall(i, "shrub_tub", -3.2, 0.0, 0.62)
	_wall(i, "cafe_table_set", 2.3, 0.0, 2.2, 0.4)
	_wall(i, "cafe_table_set", 4.4, 0.0, 1.9, -0.9)
	_wall(i, "chairs_stacked", 5.4, 0.0, 0.8, 0.2)
	_wall(i, "trampled_snow", -2.0, 0.0, 0.08)
	_wall_lantern(i, -0.45, 2.95)
	# a brazier for the smokers at the corner, and the glow of the oriel on the street
	var bz := _wp(i, 5.7, 0.0, 2.7)
	Assets.place(self, "brazier", bz, 0.0)
	_lamp(bz + Vector3(0, 1.2, 0), 3.0, 9.0, Color(1.0, 0.55, 0.22))
	_lamp(_wp(i, -2.0, 6.0, JETTY + 1.2), 1.4, 6.0, Color(1.0, 0.74, 0.46))
	# Pani Zofia's door at the Town Hall tower: a pot of Christmas roses either side.
	Assets.place(self, "pot_hellebore", Vector3(-17.55, 0, 16.0), 0.3)
	Assets.place(self, "pot_hellebore", Vector3(-14.45, 0, 16.0), 2.0)


# ------------------------------------------------------------------ the zajazd (east row, by the churchyard exit)
func _inn() -> void:
	var i := 14
	_board(i, "sign_zajazd", 2.0, -0.02)
	_wall(i, "guild_tankard", 3.45, SIGN_Y)
	_wall_lantern(i, -0.45)
	_wall(i, "pot_herbs", -3.2, 0.0, 0.55)
	_wall(i, "pot_herbs", 0.35, 0.0, 0.4, PI)
	_wall(i, "bench_wood", 2.0, 0.0, 0.4)
	_wall(i, "doormat_scraper", -2.0, 0.0, 0.95)
	_wall(i, "trampled_snow", -2.0, 0.0, 0.08)
	_wall(i, "door_wreath", -1.5, 1.8, -0.065)
	# the inn yard, in the street between the tenement's north gable (z=-4) and St Mary's towers
	Assets.place(self, "notice_board", Vector3(29.4, 0, -4.25), PI)
	Assets.place(self, "hitching_post", Vector3(28.3, 0, -5.4), 0.4)
	Assets.place(self, "woodpile_leanto", Vector3(34.6, 0, -4.0), PI)
	Assets.place(self, "coach", Vector3(32.6, 0, -7.5), 0.0)
	Assets.place(self, "straw_scatter", Vector3(37.4, 0, -7.4), 0.3)
	Assets.place(self, "horse", Vector3(37.2, 0, -7.5), PI * 0.5)
	Assets.place(self, "water_trough", Vector3(39.9, 0, -8.7), 0.0)
	Assets.place(self, "muck_heap", Vector3(37.6, 0, -4.9), 0.7)
	Assets.place(self, "trampled_snow", Vector3(33.0, 0, -4.02), PI)


# ------------------------------------------------------------------ houses: window boxes, wreaths, mats
func _homes() -> void:
	for i in [0, 1, 3, 5, 6, 8, 10, 11, 14, 15]:
		var skip: Array = [-2.0] if i == 5 else []           # the cafe oriel covers that window
		_window_boxes(i, 2, skip)
	# 3  north, tenement_d: lodgings. A wreath, a bench under the window, a mat.
	_wall(3, "door_wreath", 0.5, 1.8, -0.065)
	_wall(3, "doormat_scraper", 0.0, 0.0, 0.95)
	_wall(3, "bench_wood", -3.333, 0.0, 0.4)
	_wall(3, "trampled_snow", 0.0, 0.0, 0.08)
	# 8  south, tenement_b: lodgings. Wreath, mat, the shovelled step.
	_wall(8, "door_wreath", -1.5, 1.8, -0.065)
	_wall(8, "doormat_scraper", -2.0, 0.0, 0.95)
	_wall(8, "shovel_broom", 3.6, 0.0, 0.08)
	_wall(8, "trampled_snow", -2.0, 0.0, 0.08)
	# frozen washing strung across the two corner alleys, from the gable end of the row to a pole
	_laundry(Assets.place(self, "laundry_line", Vector3(-24.0, 0, -31.5), -PI * 0.5))
	_laundry(Assets.place(self, "laundry_line_b", Vector3(-24.0, 0, 31.0), -PI * 0.5))
	Assets.place(self, "sledge", Vector3(-25.2, 0, -34.0), 0.4)


# ------------------------------------------------------------------ St Mary's churchyard: trees and a railed green
func _churchyard() -> void:
	# The old parish cemetery in front of the church was still there in 1795 (cleared in 1796): limes and chestnuts.
	Assets.place(self, "tree_linden", Vector3(27.2, 0, -12.8), 0.4)
	Assets.place(self, "tree_chestnut", Vector3(26.9, 0, -8.8), 2.1)
	Assets.place(self, "tree_linden", Vector3(-29.0, 0, 22.5), 1.3)     # a lone lime in the south-west corner
	# the green: railings on a kerb, a hedge along the tower side, lawn under snow, a gravel walk, benches
	var x0 := 38.0
	var x1 := 44.0
	var z0 := -16.2
	var z1 := -10.2
	for x in [x0 + 1.5, x0 + 4.5]:
		Assets.place(self, "park_railing", Vector3(x, 0, z1), 0.0)
		Assets.place(self, "park_railing", Vector3(x, 0, z0), 0.0)
	for z in [z0 + 1.5, z0 + 4.5]:
		Assets.place(self, "park_railing", Vector3(x1 + 0.1, 0, z), PI * 0.5)
	Assets.place(self, "park_railing", Vector3(x0 - 0.1, 0, z0 + 1.5), PI * 0.5)    # gate gap on the west side
	Assets.place(self, "hedge", Vector3(39.6, 0, -15.55), 0.0)
	Assets.place(self, "hedge", Vector3(42.5, 0, -15.55), 0.02)
	Assets.place(self, "lawn_snow", Vector3(41.0, 0, -14.0), 0.0, 0.5)
	Assets.place(self, "lawn_snow", Vector3(41.2, 0, -10.9), PI, 0.35)
	Assets.place(self, "gravel_path", Vector3(40.4, 0, -12.4), PI * 0.5)
	Assets.place(self, "bench_wood", Vector3(39.9, 0, -13.75), 0.0)
	Assets.place(self, "bench_wood", Vector3(42.6, 0, -10.75), PI)
	Assets.place(self, "tree_linden", Vector3(38.9, 0, -14.9), 2.7)
	Assets.place(self, "tree_chestnut", Vector3(43.2, 0, -12.9), 0.9)
	Assets.place(self, "shrub_juniper", Vector3(43.6, 0, -15.4), 0.0)


# ------------------------------------------------------------------ benches by the wells and the church walls
func _benches() -> void:
	Assets.place(self, "bench_wood", Vector3(-12.0, 0, 11.4), PI)           # facing the west well
	Assets.place(self, "bench_wood", Vector3(11.6, 0, -9.0), PI * 0.5)      # facing the east well
	Assets.place(self, "bench_stone", Vector3(26.9, 0, -16.55), 0.0)        # against St Mary's west tower
	Assets.place(self, "bench_stone", Vector3(17.2, 0, 17.6), -PI * 0.5)    # St Adalbert's west wall


# ------------------------------------------------------------------ plants
func _plants() -> void:
	Assets.place(self, "ivy_patch", Vector3(17.15, 0, 20.4), -PI * 0.5)     # St Adalbert's, round the bench
	if portals.size() >= 16:
		_wall(3, "ivy_patch", -4.5, 0.0, 0.08)
		_wall(0, "shrub_tub", -1.95, 0.0, 0.5)
		_wall(0, "shrub_tub", 1.95, 0.0, 0.5)
	# straw trodden into the slush round the stall fronts
	for k in STALLS.size():
		if k % 3 == 2:
			continue
		var s: Array = STALLS[k]
		var r: float = s[1]
		Assets.place(self, "straw_scatter", (s[0] as Vector3) + Basis(Vector3.UP, r) * Vector3(0.2, 0, 1.3), r + _rng.randf_range(-0.4, 0.4))


# ------------------------------------------------------------------ clutter in the square
func _clutter() -> void:
	Assets.place(self, "sacks_crates", Vector3(-17.6, 0, -3.3), PI * 0.5 + 0.2)   # behind the west stall
	Assets.place(self, "handcart", Vector3(17.9, 0, -7.9), 0.3)                    # between the east stalls
	Assets.place(self, "sledge", Vector3(-7.5, 0, 13.6), -0.5)


# ------------------------------------------------------------------ washing that sways (assets/shaders/cloth_sway.gdshader)
const CLOTH_SWAY := "res://assets/shaders/cloth_sway.gdshader"
static var _sway_mats := {}          ## imported cloth_laundry* material -> ShaderMaterial (shared by both lines)

## Swap every cloth_laundry* surface under `root` for the sway shader, carrying the imported textures over.
## The wind amplitude comes from the global `wind` parameter that Weather drives; frozen pieces are stiff.
func _laundry(root: Node) -> void:
	if root == null:
		return
	for c in root.find_children("*", "MeshInstance3D", true, false):
		var mesh := (c as MeshInstance3D).mesh
		if mesh == null:
			continue
		for i in mesh.get_surface_count():
			var m := mesh.surface_get_material(i) as BaseMaterial3D
			if m == null or not m.resource_name.begins_with("cloth_laundry"):
				continue
			if not _sway_mats.has(m):
				_sway_mats[m] = _sway_material(m)
			mesh.surface_set_material(i, _sway_mats[m])


func _sway_material(src: BaseMaterial3D) -> ShaderMaterial:
	var sm := ShaderMaterial.new()
	sm.resource_name = src.resource_name + "_sway"
	sm.shader = load(CLOTH_SWAY)
	sm.set_shader_parameter("albedo", src.albedo_color)
	if src.albedo_texture:
		sm.set_shader_parameter("albedo_tex", src.albedo_texture)
	if src.normal_enabled and src.normal_texture:
		sm.set_shader_parameter("use_normal", true)
		sm.set_shader_parameter("normal_tex", src.normal_texture)
		sm.set_shader_parameter("normal_scale", src.normal_scale)
	if src.roughness_texture:
		sm.set_shader_parameter("rough_tex", src.roughness_texture)
	sm.set_shader_parameter("roughness", src.roughness)
	sm.set_shader_parameter("uv1_scale", src.uv1_scale)
	sm.set_shader_parameter("uv1_offset", src.uv1_offset)
	var frozen := src.resource_name.ends_with("frozen")
	sm.set_shader_parameter("stiffness", 0.9 if frozen else 0.0)
	sm.set_shader_parameter("translucency", 0.15 if frozen else 0.4)
	return sm


# ------------------------------------------------------------------ feathered slush edges
static var _feathered := {}          ## source mesh -> rebuilt mesh with rim alpha (shared by every instance)

## The packed-slush patches (trampled snow at doors, rings under trees) are exported with alpha blending but the
## glTF exporter drops their rim alpha, so rebuild it here: vertices at the 6 mm lip get alpha 0, those 8 mm higher
## (the inner ring and the crown) alpha 1, and the material takes alpha from vertex colour.
func _feather_slush(root: Node) -> void:
	for c in root.find_children("*", "MeshInstance3D", true, false):
		var mi := c as MeshInstance3D
		if mi.mesh == null or not (mi.mesh is ArrayMesh):
			continue
		var src := mi.mesh as ArrayMesh
		if not _feathered.has(src):
			_feathered[src] = _feathered_copy(src)
		if _feathered[src] != null:
			mi.mesh = _feathered[src]


func _feathered_copy(src: ArrayMesh) -> ArrayMesh:
	var hit := false
	var out := ArrayMesh.new()
	for i in src.get_surface_count():
		var mat := src.surface_get_material(i)
		var arrays := src.surface_get_arrays(i)
		if mat != null and mat.resource_name == "slush_trod" and mat is BaseMaterial3D \
				and (mat as BaseMaterial3D).transparency != BaseMaterial3D.TRANSPARENCY_DISABLED:
			hit = true
			var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var cols := PackedColorArray()
			cols.resize(verts.size())
			for k in verts.size():
				cols[k] = Color(1, 1, 1, clampf((verts[k].y - 0.0065) / 0.0075, 0.0, 1.0))
			arrays[Mesh.ARRAY_COLOR] = cols
			var m := (mat as BaseMaterial3D).duplicate() as BaseMaterial3D
			m.vertex_color_use_as_albedo = true
			m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			m.roughness = 0.85
			mat = m
		out.add_surface_from_arrays(src.surface_get_primitive_type(i), arrays)
		out.surface_set_material(out.get_surface_count() - 1, mat)
	return out if hit else null


# ------------------------------------------------------------------ dead grass between the setts (MultiMesh)
func _weeds() -> void:
	var mesh := _mesh_of("weed_tuft")
	if mesh == null:
		return
	var xf: Array[Transform3D] = []
	# along every facade foot, skipping the doorways
	for i in portals.size():
		var m := _mod(i)
		var px: float = m["px"]
		for k in 26:
			var lx := _rng.randf_range(-4.8, 4.8)
			if absf(lx - px) < 1.7:
				continue
			xf.append(_tuft(_wp(i, lx, 0.0, _rng.randf_range(0.1, 0.45))))
	# round the Cloth Hall (34 x 9, passage in the middle), the Town Hall front and the church towers
	for k in 90:
		var x := _rng.randf_range(-17.0, 17.0)
		if absf(x) < 2.2:
			continue
		var side := 1.0 if _rng.randf() < 0.5 else -1.0
		xf.append(_tuft(Vector3(x, 0, side * _rng.randf_range(4.6, 4.95))))
	for k in 30:
		xf.append(_tuft(Vector3(_rng.randf_range(-33.0, -12.5), 0, _rng.randf_range(16.05, 16.4))))
	for k in 30:
		xf.append(_tuft(Vector3(_rng.randf_range(24.0, 44.0), 0, _rng.randf_range(-16.8, -16.4))))
	# and in the corners of the square where carts never go, the churchyard green's edges, the lamp and well feet
	for c in [Vector2(-27, -27), Vector2(27, -27), Vector2(-27, 27), Vector2(27, 27), Vector2(-27, 21), Vector2(37, -6)]:
		for k in 18:
			var a := _rng.randf() * TAU
			var r := sqrt(_rng.randf()) * 2.6
			xf.append(_tuft(Vector3(c.x + cos(a) * r, 0, c.y + sin(a) * r)))
	for k in 50:
		var t := _rng.randf()
		var e := _rng.randi() % 4
		var p: Vector3 = [Vector3(38 + 6 * t, 0, -10.0), Vector3(38 + 6 * t, 0, -16.4), Vector3(44.3, 0, -16 + 6 * t), Vector3(37.8, 0, -16 + 3 * t)][e]
		xf.append(_tuft(p + Vector3(_rng.randf_range(-0.2, 0.2), 0, _rng.randf_range(-0.2, 0.2))))
	for c in [Vector2(-22, -22), Vector2(22, -22), Vector2(-22, 22), Vector2(16, 24), Vector2(0, -24), Vector2(-6, 24),
			Vector2(-24, 0), Vector2(24, 4), Vector2(5, 9), Vector2(-5, -9), Vector2(-12, 9), Vector2(14, -9)]:
		for k in 5:
			var a := _rng.randf() * TAU
			var r := 0.25 if c.x != -12 and c.x != 14 else 1.5
			xf.append(_tuft(Vector3(c.x + cos(a) * r, 0, c.y + sin(a) * r)))
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = xf.size()
	for k in xf.size():
		mm.set_instance_transform(k, xf[k])
	var mmi := MultiMeshInstance3D.new()
	mmi.name = "Weeds"
	mmi.multimesh = mm
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mmi)


func _tuft(p: Vector3) -> Transform3D:
	var s := _rng.randf_range(0.6, 1.4)
	var b := Basis(Vector3.UP, _rng.randf() * TAU).scaled(Vector3(s, s * _rng.randf_range(0.8, 1.3), s))
	return Transform3D(b, Vector3(p.x, 0.0, p.z))


## The first visual mesh in an asset's glTF (the collision bodies are skipped).
func _mesh_of(asset: String) -> Mesh:
	var n := Assets.instance(asset)
	if n == null:
		return null
	var found: Mesh = null
	var stack: Array = [n]
	while stack.size() > 0 and found == null:
		var c: Node = stack.pop_back()
		if c is MeshInstance3D and not (c.get_parent() is StaticBody3D):
			found = (c as MeshInstance3D).mesh
		for ch in c.get_children():
			stack.append(ch)
	n.free()
	return found


# ------------------------------------------------------------------ inspection shots (`-- --dress-shot=/dir`)
func _shot_dir() -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--dress-shot="):
			return a.trim_prefix("--dress-shot=")
	return ""


func _shots(dir: String) -> void:
	await get_tree().create_timer(2.0).timeout
	if not is_inside_tree():
		return
	for c in get_tree().root.find_children("*", "CanvasLayer", true, false):
		(c as CanvasLayer).visible = false
	var cam := Camera3D.new()
	cam.fov = 62
	add_child(cam)
	cam.current = true
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50, 30, 0)
	sun.light_energy = 2.2
	sun.visible = false
	add_child(sun)
	var shots := [
		["cafe", Vector3(-17.5, 2.4, 21.0), Vector3(-21.5, 2.2, 28.0)],
		["cafe_close", Vector3(-23.8, 1.7, 23.6), Vector3(-19.5, 1.6, 28.0)],
		["townhall_door", Vector3(-16.0, 1.9, 20.5), Vector3(-16.0, 1.2, 16.0)],
		["north_west_shops", Vector3(-13.0, 2.6, -20.5), Vector3(-13.0, 3.0, -28.0)],
		["north_east_shops", Vector3(12.0, 2.6, -20.5), Vector3(14.0, 3.0, -28.0)],
		["south_shops", Vector3(4.0, 2.6, 20.5), Vector3(4.0, 3.0, 28.0)],
		["west_shops", Vector3(-20.5, 2.6, -2.0), Vector3(-28.0, 2.8, -2.0)],
		["inn", Vector3(23.5, 2.6, 2.5), Vector3(28.0, 2.4, -1.0)],
		["inn_yard", Vector3(26.5, 3.2, -14.5), Vector3(33.0, 1.2, -6.0)],
		["churchyard", Vector3(34.0, 4.5, -6.5), Vector3(41.0, 0.5, -13.0)],
		["laundry", Vector3(-21.0, 2.2, -23.5), Vector3(-28.0, 2.8, -31.0)],
		["laundry_close", Vector3(-26.0, 2.0, -27.5), Vector3(-28.2, 2.3, -31.0)],
		["laundry_south", Vector3(-26.0, 2.0, 27.0), Vector3(-28.2, 2.3, 30.6)],
		["cafe_awning", Vector3(-20.2, 2.4, 22.6), Vector3(-22.0, 3.4, 28.0)],
		["adalbert", Vector3(12.5, 2.0, 21.0), Vector3(17.5, 1.5, 19.0)],
		["hedge_close", Vector3(39.4, 1.5, -12.2), Vector3(41.2, 0.45, -15.6)],
		["slush_cafe_door", Vector3(-16.6, 1.6, 25.2), Vector3(-18.0, 0.0, 27.8)],
		["slush_goldsmith_door", Vector3(18.2, 1.6, -24.6), Vector3(18.0, 0.0, -27.6)],
		["tree_ring", Vector3(25.0, 1.7, -10.6), Vector3(27.2, 0.0, -12.8)],
		["overhead_ne", Vector3(20.0, 38.0, 10.0), Vector3(22.0, 0.0, -10.0)],
		["overhead_sw", Vector3(-20.0, 38.0, 0.0), Vector3(-18.0, 0.0, 20.0)],
	]
	for s in shots:
		cam.look_at_from_position(s[1], s[2])
		for lit in [false, true]:
			sun.visible = lit
			for f in 4:
				await get_tree().process_frame
			get_viewport().get_texture().get_image().save_png("%s/dress_%s%s.png" % [dir, s[0], "_lit" if lit else ""])
	sun.queue_free()
	cam.queue_free()
	for c in get_tree().root.find_children("*", "CanvasLayer", true, false):
		(c as CanvasLayer).visible = true
	print("[smoke] dressing shots in ", dir)
