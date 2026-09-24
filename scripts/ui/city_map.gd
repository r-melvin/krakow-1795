extends RefCounted
## Shared drawing of the Rynek plan for the journal's Map tab (journal.gd MapView) and the HUD minimap (minimap.gd).
## `draw_map(canvas, rect, centre, scale, options)`: draws onto any CanvasItem inside `rect`, world point `centre`
## (x, z) at the middle of `rect`, `scale` pixels per metre, north (-Z) up. Ink on paper; the caller draws the sheet.
## options:
##   intel: Dictionary      Mission.journal["intel"] (intel.gd): patrols, lamps, spots, places, enforcers, zone
##   world: Node3D          the district, for building footprints (measured once per district from its models)
##   labels: bool           landmark / patrol / place names (the journal; the minimap has none)
##   zones: "all" | "under" | "none"   tint every disguise zone, only the one under the player, or none
##   zone: String, trespass: bool      the player's zone and whether his clothes pass there
##   player: Node3D         draws the arrow (camera facing)
##   guards: [[Vector3 pos, Vector3 forward], ...]   guards seen now: red dots with a facing tick
##   ghost: Vector3 | null  the watch's last-known position of the player
##   objective: Vector2 | null        the current objective (x, z)
##   corporal: bool         the Corporal's flag at St Mary's post
##   icon: float            icon size multiplier (1 journal, ~0.7 minimap)
##   font, font_b: Font
##   clip: bool           cut building footprints at `rect` (the journal sheet)
##   origin: Vector3        subtracted from node positions (player, guards, ghost): a test sandbox's offset

const Zones := preload("res://scripts/stealth/zones.gd")
const LANDMARKS := {"sukiennice": "Cloth Hall", "town_hall": "Town Hall", "st_marys": "St Mary's", "st_adalbert": "St Adalbert's"}
## Outer-town buildings the map draws, with the labels the full sheet shows (blank: drawn, unlabelled).
const OUTER_NAMES := {"florian_gate": "Florian Gate", "barbican": "Barbican", "city_tower": "", "castle_gate": "Castle gate",
	"collegium_maius": "Collegium", "campanile": "", "synagogue": "Old Synagogue", "synagogue_wooden": "Synagogue",
	"uniate_church": "Uniate church", "prayer_house": "", "monastery_wall": "", "monastery_gate": "Monastery",
	"kingpin_house": "", "kingpin_warehouse": "Warehouse", "bathhouse": "Bathhouse", "windmill": "Mill", "watermill": "Water mill",
	"brewery": "Brewery", "forge": "Forge", "bell_foundry": "Foundry", "cooper_yard": "", "carpenter_yard": "", "wawel_far": "Wawel",
	"old_synagogue": "Old Synagogue", "sien_passage": ""}
const PAPER := Color(0.82, 0.74, 0.57)
const INK := Color(0.2, 0.13, 0.08)
const INK_SOFT := Color(0.2, 0.13, 0.08, 0.55)
const BLOCK := Color(0.62, 0.5, 0.36)
const RED := Color(0.62, 0.08, 0.05)
const BLUE := Color(0.12, 0.2, 0.42)
const GOLD := Color(0.95, 0.72, 0.25)
const CORPORAL_POST := Vector2(24, -10)

static var _foot_for := 0
static var _foot: Array = []                     ## [[Rect2 (x, z), label]]

var ci: CanvasItem
var rect: Rect2
var centre := Vector2.ZERO
var scale := 1.0
var opt: Dictionary = {}
var k := 1.0                                     ## icon size


static func draw_map(canvas: CanvasItem, r: Rect2, c: Vector2, s: float, options: Dictionary) -> void:
	var m := new()
	m.ci = canvas
	m.rect = r
	m.centre = c
	m.scale = s
	m.opt = options
	m.k = float(options.get("icon", 1.0))
	m._draw_all()


func P(x: float, z: float) -> Vector2:
	return rect.get_center() + (Vector2(x, z) - centre) * scale


func PV(v: Variant) -> Vector2:
	if v is Array:
		return P(float(v[0]), float(v[1]))
	if v is Vector2:
		return P(v.x, v.y)
	var o: Vector3 = opt.get("origin", Vector3.ZERO)
	return P((v as Vector3).x - o.x, (v as Vector3).z - o.z)


## True if `at` is near enough the drawn rect to be worth drawing (the minimap skips the rest of the city).
func near(at: Vector2, pad: float = 30.0) -> bool:
	return rect.grow(pad).has_point(at)


# ------------------------------------------------------------------ footprints

static func footprints(world: Node3D) -> Array:
	if world == null or not is_instance_valid(world):
		return fallback()
	if _foot_for == world.get_instance_id() and not _foot.is_empty():
		return _foot
	var out: Array = []
	var pool: Array = world.get_children()
	for c in world.get_children():          # the outer town keeps its buildings under its own node
		if c.get_script() and str(c.get_script().resource_path).ends_with("outer_city.gd"):
			pool += c.get_children()
	for c in pool:
		var n3 := c as Node3D
		if n3 == null:
			continue
		var base := n3.scene_file_path.get_file().get_basename()
		var named: Variant = OUTER_NAMES.get(base, null)
		if not (LANDMARKS.has(base) or base.begins_with("tenement_") or base.begins_with("ten_") or named != null
				or base.begins_with("kaz_") or base.begins_with("garb_") or base.begins_with("dock_") or base.begins_with("klep_")):
			continue
		var r := _aabb_xz(n3)
		if r.size.x > 0.5 and r.size.y > 0.5:
			out.append([r, LANDMARKS.get(base, str(named) if named != null else "")])
	if out.size() < 5:
		return fallback()
	_foot_for = world.get_instance_id()
	_foot = out
	return out


static func _aabb_xz(n: Node3D) -> Rect2:
	var have := false
	var box := AABB()
	for m in n.find_children("*", "MeshInstance3D", true, false):
		var mi := m as MeshInstance3D
		if mi.mesh == null or not mi.is_visible_in_tree():
			continue
		var a: AABB = mi.global_transform * mi.get_aabb()
		if a.size.y < 0.6 and a.position.y < 0.3:
			continue            # ground plates, steps, snow
		box = a if not have else box.merge(a)
		have = true
	if not have:
		return Rect2()
	return Rect2(box.position.x, box.position.z, box.size.x, box.size.z)


## greybox_district.gd's layout: 60 m square, tenement rows at +-32 (8 m deep), the landmarks.
static func fallback() -> Array:
	return [[Rect2(-24, -36, 48, 8), ""], [Rect2(-24, 28, 48, 8), ""], [Rect2(-36, -18, 8, 36), ""], [Rect2(28, -4, 8, 18), ""],
			[Rect2(-6, -16, 12, 32), "Cloth Hall"], [Rect2(-30, 6, 18, 12), "Town Hall"], [Rect2(28, -44, 12, 22), "St Mary's"],
			[Rect2(17, 14, 9, 8), "St Adalbert's"]]


# ------------------------------------------------------------------ drawing

func _draw_all() -> void:
	var intel: Dictionary = opt.get("intel", {})
	_draw_zones(intel)
	ci.draw_rect(Rect2(P(-30, -30), Vector2(60, 60) * scale), Color(INK, 0.35), false, 1.0)
	var feet := footprints(opt.get("world"))
	for f in feet:
		var r: Rect2 = f[0]
		var rr := Rect2(P(r.position.x, r.position.y), r.size * scale)
		if not rr.intersects(rect.grow(4.0)):
			continue
		if opt.get("clip", false):
			rr = rr.intersection(rect)
		var lm: bool = str(f[1]) != ""
		ci.draw_rect(rr, BLOCK.darkened(0.12) if lm else BLOCK)
		ci.draw_rect(rr, INK, false, 1.4 if lm else 1.0)
		if not lm and scale > 4.0:
			var hatch := PackedVector2Array()        # hatching on the tenements, one call
			var y := rr.position.y + 3.0
			while y < rr.end.y:
				hatch.append(Vector2(rr.position.x + 1, y))
				hatch.append(Vector2(rr.end.x - 1, y))
				y += 4.0
			ci.draw_multiline(hatch, Color(INK, 0.12), 1.0)
	if opt.get("labels", false):
		for f in feet:
			if str(f[1]) != "":
				var r: Rect2 = f[0]
				label(P(r.get_center().x, r.get_center().y), str(f[1]), 15, INK, true)
	_draw_places(intel)
	_draw_lamps_spots(intel)
	_draw_patrols(intel)
	if opt.get("corporal", true):
		_draw_corporal(intel)
	_draw_enforcers(intel)
	_draw_objective()
	_draw_ghost()
	_draw_guards()
	_draw_player()


func label(at: Vector2, text: String, fs: int, col: Color, centred := false, bold := false) -> void:
	var f: Font = opt.get("font_b" if bold else "font", null)
	if f == null:
		f = UiTheme.font("display" if bold else "italic")
	var w := f.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
	var pos := at - Vector2(w * 0.5, -fs * 0.35) if centred else at
	ci.draw_string(f, pos + Vector2(1, 1), text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(PAPER, 0.7))
	ci.draw_string(f, pos, text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, col)


func _draw_zones(intel: Dictionary) -> void:
	var mode := str(opt.get("zones", "all"))
	if mode == "none":
		return
	var zd: Dictionary = Zones.db().get("zones", {})
	var cur := str(opt.get("zone", intel.get("zone", "street")))
	var tres := bool(opt.get("trespass", false))
	for id in zd:
		if id == "street" or (mode == "under" and id != cur):
			continue
		var c: Array = zd[id].get("color", [0.7, 0.7, 0.7])
		var col := Color(float(c[0]), float(c[1]), float(c[2]))
		var first := true
		for poly in zd[id].get("polygons", []):
			var pts := PackedVector2Array()
			for pt in poly:
				pts.append(PV(pt))
			var bb := Rect2(pts[0], Vector2.ZERO)
			for q in pts:
				bb = bb.expand(q)
			if not bb.intersects(rect.grow(10.0)):
				continue
			ci.draw_colored_polygon(pts, Color(col.darkened(0.25), 0.28 if mode == "all" else 0.4))
			var closed := pts.duplicate()
			closed.append(pts[0])
			var edge := RED if id == cur and tres else Color(col.darkened(0.55), 0.8)
			dashed(closed, edge, 2.4 if id == cur else 1.2, 6.0, 4.0)
			if first and opt.get("labels", false):
				first = false
				label(pts[0] + Vector2(4, 13), str(zd[id].get("name", id)).get_slice(":", 0), 12, col.darkened(0.6))


## Dashed polyline in one draw call (the minimap redraws at 10 Hz: no per-dash primitives).
func dashed(pts: PackedVector2Array, col: Color, w: float, dash: float, gap: float) -> void:
	var segs := PackedVector2Array()
	for i in pts.size() - 1:
		var a := pts[i]
		var b := pts[i + 1]
		var L := a.distance_to(b)
		if L < 0.5:
			continue
		var d := (b - a) / L
		var t := 0.0
		while t < L:
			var q0 := a + d * t
			if near(q0):
				segs.append(q0)
				segs.append(a + d * minf(t + dash, L))
			t += dash + gap
	if segs.size() >= 2:
		ci.draw_multiline(segs, col, w)


func _draw_places(intel: Dictionary) -> void:
	var places: Dictionary = intel.get("places", {})
	for key in places:
		var e: Array = places[key]
		var at := P(float(e[0]), float(e[1]))
		if not near(at):
			continue
		if str(key) == "brothel":
			ci.draw_circle(at, 5.0 * k, RED)
			ci.draw_arc(at, 5.0 * k, 0, TAU, 16, INK, 1.0)
			if opt.get("labels", false):
				label(at + Vector2(7, -4), str(e[2]), 12, RED)
		else:
			var h := 3.0 * k
			ci.draw_rect(Rect2(at - Vector2(h, h), Vector2(h, h) * 2.0), Color(0.25, 0.4, 0.2))
			ci.draw_rect(Rect2(at - Vector2(h, h), Vector2(h, h) * 2.0), INK, false, 1.0)


func _draw_lamps_spots(intel: Dictionary) -> void:
	for key in intel.get("lamps", {}):
		var at := PV(intel["lamps"][key])
		if not near(at):
			continue
		ci.draw_circle(at, 4.5 * k, GOLD)
		ci.draw_arc(at, 4.5 * k, 0, TAU, 14, INK, 1.2 * k)
		if k >= 0.9:
			ci.draw_arc(at, 8.0, 0, TAU, 18, Color(0.85, 0.55, 0.15, 0.45), 1.0)
	for key in intel.get("spots", {}):
		var e: Array = intel["spots"][key]
		var at := P(float(e[0]), float(e[1]))
		var h := 4.0 * k
		ci.draw_line(at + Vector2(-h, -h), at + Vector2(h, h), INK, 2.0 * k)
		ci.draw_line(at + Vector2(-h, h), at + Vector2(h, -h), INK, 2.0 * k)


func _draw_patrols(intel: Dictionary) -> void:
	var pats: Dictionary = intel.get("patrols", {})
	for gname in pats:
		var pr: Dictionary = pats[gname]
		var wps: Array = pr.get("wps", [])
		if wps.is_empty():
			continue
		var col := RED if pr.get("enforcer", false) else BLUE
		if pr.get("sentry", false):
			var at := PV(wps[0])
			if not near(at):
				continue
			ci.draw_colored_polygon(PackedVector2Array([at + Vector2(0, -7) * k, at + Vector2(6, 5) * k, at + Vector2(-6, 5) * k]), col)
			if opt.get("labels", false):
				label(at + Vector2(8, 4), str(gname), 12, col)
			continue
		var pts := PackedVector2Array()
		for w in wps:
			pts.append(PV(w))
		pts.append(pts[0])
		dotted(pts, col)
		for i in wps.size():
			if near(PV(wps[i])):
				ci.draw_circle(PV(wps[i]), 2.6 * k, col)
		if opt.get("labels", false):
			label(PV(wps[0]) + Vector2(6, -6), str(gname), 12, col)


## A dotted loop (short ink dabs, one draw call) with an arrowhead mid-leg showing the way he walks.
func dotted(pts: PackedVector2Array, col: Color) -> void:
	var segs := PackedVector2Array()
	var step := 7.0 * k
	var dab := 2.4 * k
	for i in pts.size() - 1:
		var a := pts[i]
		var b := pts[i + 1]
		var L := a.distance_to(b)
		if L < 0.5:
			continue
		var d := (b - a) / L
		var t := 0.0
		while t <= L:
			var q := a + d * t
			if near(q):
				segs.append(q - d * dab * 0.5)
				segs.append(q + d * dab * 0.5)
			t += step
		var m := a.lerp(b, 0.5)
		if L > 20.0 and near(m):
			var n := Vector2(-d.y, d.x)
			ci.draw_colored_polygon(PackedVector2Array([m + d * 6.0 * k, m - d * 3.0 * k + n * 4.0 * k, m - d * 3.0 * k - n * 4.0 * k]), col)
	if segs.size() >= 2:
		ci.draw_multiline(segs, col, 2.6 * k)


func _draw_corporal(intel: Dictionary) -> void:
	var at := P(CORPORAL_POST.x, CORPORAL_POST.y)
	if not near(at):
		return
	var enf: bool = intel.get("enforcers", {}).has("guard:St Mary's post")
	ci.draw_line(at, at + Vector2(0, -16) * k, INK, 1.6)
	ci.draw_colored_polygon(PackedVector2Array([at + Vector2(0, -16) * k, at + Vector2(11, -12) * k, at + Vector2(0, -8) * k]), RED if enf else INK)
	if opt.get("labels", false):
		label(at + Vector2(-58, 14), "the Corporal", 12, RED if enf else INK)


func _draw_enforcers(intel: Dictionary) -> void:
	var enf: Dictionary = intel.get("enforcers", {})
	for id in enf:
		var e: Dictionary = enf[id]
		if not e.has("pos") or str(id).begins_with("guard:"):
			continue
		var at := PV(e["pos"])
		if not near(at):
			continue
		ci.draw_circle(at, 6.0 * k, Color(RED, 0.85))
		ci.draw_arc(at, 9.0 * k, 0, TAU, 18, RED, 1.5)
		if opt.get("labels", false):
			label(at + Vector2(10, 4), str(e.get("name", id)), 12, RED)


func _draw_objective() -> void:
	var o: Variant = opt.get("objective")
	if o == null:
		return
	var at := PV(o)
	if not near(at):
		return
	var r := 7.0 * k
	ci.draw_arc(at, r, 0, TAU, 20, Color(0.1, 0.35, 0.15), 2.2)
	ci.draw_colored_polygon(PackedVector2Array([at + Vector2(0, -r * 0.55), at + Vector2(r * 0.55, 0), at + Vector2(0, r * 0.55), at + Vector2(-r * 0.55, 0)]),
			Color(0.15, 0.5, 0.22))


func _draw_ghost() -> void:
	var g: Variant = opt.get("ghost")
	if g == null:
		return
	var at := PV(g)
	ci.draw_arc(at, 6.0 * k, 0, TAU, 16, Color(0.75, 0.35, 0.15, 0.9), 1.6)
	ci.draw_circle(at, 2.2 * k, Color(0.75, 0.35, 0.15, 0.7))


func _draw_guards() -> void:
	for gd in opt.get("guards", []):
		var at := PV(gd[0])
		var f: Vector3 = gd[1]
		var d := Vector2(f.x, f.z)
		d = d.normalized() if d.length() > 0.01 else Vector2(0, -1)
		ci.draw_line(at, at + d * 9.0 * k, RED, 2.0)
		ci.draw_circle(at, 3.8 * k, RED)
		ci.draw_arc(at, 3.8 * k, 0, TAU, 12, INK, 1.0)


func _draw_player() -> void:
	var p: Node3D = opt.get("player")
	if p == null or not is_instance_valid(p) or p.global_position.y < -50.0:
		return
	var at := PV(p.global_position)
	var fwd := Vector3(0, 0, -1)
	var cam: Camera3D = p.call("camera") if p.has_method("camera") else null
	if cam:
		fwd = -cam.global_basis.z
	var d := Vector2(fwd.x, fwd.z)
	d = d.normalized() if d.length() > 0.01 else Vector2(0, -1)
	var n := Vector2(-d.y, d.x)
	var s := 11.0 * k
	ci.draw_circle(at, s, Color(1.0, 0.95, 0.8, 0.5))
	ci.draw_colored_polygon(PackedVector2Array([at + d * s, at - d * s * 0.55 + n * s * 0.6, at - d * s * 0.23, at - d * s * 0.55 - n * s * 0.6]), Color(0.12, 0.07, 0.04))
	if opt.get("labels", false):
		label(at + Vector2(13, 16), "you", 13, INK)
