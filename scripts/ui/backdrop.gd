extends Control
## Painted night backdrop for the title and menu: sky gradient, moon, the Wawel hill and the Rynek skyline
## (St Mary's unequal towers, the Cloth Hall parapet, the Town Hall tower) as silhouettes, lit windows and
## falling snow. Drawn in code every frame; costs next to nothing compared with a 3D camera over the district.

@export var drift := 1.0          ## parallax sway strength
@export var snow_count := 220
@export var darken := 0.0         ## 0..1 extra dim, for screens that sit panels on top

var _t := 0.0
var _snow: Array = []             ## [Vector3(x 0..1, y 0..1, depth 0.3..1)]
var _windows: Array = []          ## [Rect2 in skyline units, flicker phase]
var _rng := RandomNumberGenerator.new()
var _halo: GradientTexture2D
var _haze: GradientTexture2D
var _vignette: GradientTexture2D

## Near skyline, x and width in fractions of the screen width, height in fractions of the height.
## kinds: gable, attyka, mansard, spire, tower_tall, dome, flat
const NEAR := [
	[-0.02, 0.07, 0.22, "gable"], [0.05, 0.05, 0.26, "mansard"], [0.10, 0.06, 0.24, "attyka"],
	[0.16, 0.035, 0.44, "tower_tall"],   # Town Hall tower
	[0.195, 0.05, 0.23, "gable"], [0.245, 0.30, 0.20, "attyka_long"],   # Sukiennice
	[0.545, 0.045, 0.27, "gable"], [0.59, 0.035, 0.62, "spire_crown"],   # St Mary's north tower (Hejnalica)
	[0.625, 0.07, 0.34, "nave"], [0.695, 0.032, 0.50, "spire"],          # nave, south tower
	[0.727, 0.05, 0.25, "mansard"], [0.777, 0.04, 0.30, "dome"],         # St Adalbert's is small; a dome house
	[0.817, 0.06, 0.24, "attyka"], [0.877, 0.05, 0.28, "gable"], [0.927, 0.08, 0.22, "mansard"],
]


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_rng.seed = 1795
	_halo = _radial(Color(0.85, 0.82, 0.7, 0.22), Color(0.85, 0.82, 0.7, 0.0))
	_vignette = _radial(Color(0, 0, 0, 0.0), Color(0, 0, 0, 0.55), 0.55)
	_haze = GradientTexture2D.new()
	_haze.fill_from = Vector2(0, 0)
	_haze.fill_to = Vector2(0, 1)
	var hg := Gradient.new()
	hg.set_color(0, Color(0.3, 0.36, 0.46, 0.0))
	hg.set_color(1, Color(0.3, 0.36, 0.46, 0.22))
	_haze.gradient = hg
	for i in snow_count:
		_snow.append(Vector3(_rng.randf(), _rng.randf(), _rng.randf_range(0.3, 1.0)))
	for b in NEAR:
		var n := int(b[1] * 90.0)
		for i in n:
			if _rng.randf() < 0.35:
				_windows.append([b[0] + b[1] * _rng.randf_range(0.15, 0.8), _rng.randf_range(0.03, b[2] * 0.7), _rng.randf() * TAU])


func _process(delta: float) -> void:
	_t += delta
	for i in _snow.size():
		var s: Vector3 = _snow[i]
		s.y += delta * 0.035 * s.z
		s.x += delta * (0.006 + 0.004 * sin(_t * 0.5 + s.z * 9.0)) * s.z
		if s.y > 1.02:
			s.y = -0.02
			s.x = _rng.randf()
		if s.x > 1.02:
			s.x -= 1.04
		_snow[i] = s
	queue_redraw()


func _draw() -> void:
	var w := size.x
	var h := size.y
	# Sky: deep blue at the top to a cold haze at the horizon.
	var top := Color("05070d")
	var mid := Color("0e1626")
	var low := Color("26303f")
	var steps := 48
	for i in steps:
		var f := float(i) / steps
		var c := top.lerp(mid, f * 1.6) if f < 0.62 else mid.lerp(low, (f - 0.62) / 0.38)
		draw_rect(Rect2(0, h * f, w, h / steps + 1), c)
	# Moon with a soft halo.
	var moon := Vector2(w * 0.78 + sin(_t * 0.03) * 6.0 * drift, h * 0.2)
	draw_texture_rect(_halo, Rect2(moon - Vector2(210, 210), Vector2(420, 420)), false)
	draw_circle(moon, 34.0, Color("e8e0c8"))

	var sway := sin(_t * 0.07) * 14.0 * drift
	_draw_wawel(w, h, sway * 0.4)
	draw_texture_rect(_haze, Rect2(0, h * 0.5, w, h * 0.4), false)
	_draw_near(w, h, sway)

	for s in _snow:
		var p := Vector2(s.x * w + sway * s.z, s.y * h)
		draw_circle(p, 0.8 + 2.0 * s.z, Color(0.92, 0.94, 1.0, 0.25 + 0.45 * s.z))
	if darken > 0.0:
		draw_rect(Rect2(Vector2.ZERO, size), Color(0.02, 0.03, 0.05, darken))
	draw_texture_rect(_vignette, Rect2(-w * 0.1, -h * 0.25, w * 1.2, h * 1.5), false)


static func _radial(inner: Color, outer: Color, start: float = 0.0) -> GradientTexture2D:
	var t := GradientTexture2D.new()
	t.fill = GradientTexture2D.FILL_RADIAL
	t.fill_from = Vector2(0.5, 0.5)
	t.fill_to = Vector2(0.5, 0.0)
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([start, 1.0])
	g.colors = PackedColorArray([inner, outer])
	t.gradient = g
	t.width = 256
	t.height = 256
	return t


func _draw_wawel(w: float, h: float, dx: float) -> void:
	var col := Color("141c2a")
	var base := h * 0.80
	var pts := PackedVector2Array()
	pts.append(Vector2(w * 0.0, h))
	pts.append(Vector2(w * 0.0, base - h * 0.02))
	# Hill rising to the right with the castle on it.
	var hill := [[0.30, 0.03], [0.38, 0.10], [0.44, 0.13], [0.5, 0.14]]
	for p in hill:
		pts.append(Vector2(w * p[0] + dx, base - h * p[1]))
	var ground := base - h * 0.14
	# Castle walls, towers and the cathedral's Zygmunt tower and dome.
	var blocks := [[0.50, 0.04, 0.10], [0.54, 0.012, 0.16], [0.552, 0.05, 0.09], [0.60, 0.02, 0.14],
			[0.62, 0.03, 0.19], [0.65, 0.015, 0.23], [0.665, 0.04, 0.12], [0.705, 0.012, 0.15], [0.717, 0.06, 0.08]]
	for b in blocks:
		var x0: float = w * b[0] + dx
		var x1: float = w * (b[0] + b[1]) + dx
		var top: float = ground - h * b[2]
		pts.append(Vector2(x0, top + 2))
		if b[1] < 0.02:
			pts.append(Vector2((x0 + x1) * 0.5, top - h * 0.04))   # spire
		else:
			pts.append(Vector2(x0, top))
			pts.append(Vector2(x1, top))
		pts.append(Vector2(x1, top + 2))
	pts.append(Vector2(w * 0.78 + dx, ground))
	pts.append(Vector2(w * 0.86 + dx, base - h * 0.06))
	pts.append(Vector2(w * 1.0, base - h * 0.02))
	pts.append(Vector2(w, h))
	draw_colored_polygon(pts, col)
	# The cathedral dome.
	draw_circle(Vector2(w * 0.645 + dx, ground - h * 0.19), h * 0.022, col)


func _draw_near(w: float, h: float, dx: float) -> void:
	var col := Color("05070b")
	var base := h * 0.92
	var pts := PackedVector2Array()
	pts.append(Vector2(-40, h))
	for b in NEAR:
		var x0: float = w * b[0] + dx
		var bw: float = w * b[1]
		var x1: float = x0 + bw
		var top: float = base - h * b[2]
		match b[3]:
			"gable":
				pts.append_array([Vector2(x0, top), Vector2(x0 + bw * 0.5, top - bw * 0.55), Vector2(x1, top)])
			"mansard":
				pts.append_array([Vector2(x0, top), Vector2(x0 + bw * 0.15, top - bw * 0.3), Vector2(x1 - bw * 0.15, top - bw * 0.3), Vector2(x1, top)])
			"attyka", "attyka_long":
				var n := int(bw / 18.0)
				var step := bw / maxf(n, 1)
				pts.append(Vector2(x0, top))
				for i in n:
					var xa := x0 + i * step
					pts.append_array([Vector2(xa, top - 12), Vector2(xa + step * 0.5, top - 12), Vector2(xa + step * 0.5, top), Vector2(xa + step, top)])
			"tower_tall":
				pts.append_array([Vector2(x0, top), Vector2(x0 + bw * 0.1, top - h * 0.03), Vector2(x0 + bw * 0.5, top - h * 0.1), Vector2(x1 - bw * 0.1, top - h * 0.03), Vector2(x1, top)])
			"spire":
				pts.append_array([Vector2(x0, top), Vector2(x0 + bw * 0.2, top - h * 0.02), Vector2(x0 + bw * 0.5, top - h * 0.1), Vector2(x1 - bw * 0.2, top - h * 0.02), Vector2(x1, top)])
			"spire_crown":
				# The Hejnalica: a tall spire ringed by eight turrets and a crown.
				pts.append_array([Vector2(x0, top), Vector2(x0, top - h * 0.025), Vector2(x0 + bw * 0.2, top - h * 0.02),
					Vector2(x0 + bw * 0.35, top - h * 0.06), Vector2(x0 + bw * 0.42, top - h * 0.075), Vector2(x0 + bw * 0.5, top - h * 0.16),
					Vector2(x1 - bw * 0.42, top - h * 0.075), Vector2(x1 - bw * 0.35, top - h * 0.06), Vector2(x1 - bw * 0.2, top - h * 0.02),
					Vector2(x1, top - h * 0.025), Vector2(x1, top)])
			"nave":
				pts.append_array([Vector2(x0, top), Vector2(x0 + bw * 0.5, top - bw * 0.35), Vector2(x1, top)])
			"dome":
				pts.append(Vector2(x0, top))
				for i in 9:
					var a := PI + PI * i / 8.0
					pts.append(Vector2(x0 + bw * 0.5 + cos(a) * bw * 0.4, top + sin(a) * bw * 0.4))
				pts.append(Vector2(x1, top))
			_:
				pts.append_array([Vector2(x0, top), Vector2(x1, top)])
	pts.append(Vector2(w + 40, base - h * 0.2))
	pts.append(Vector2(w + 40, h))
	draw_colored_polygon(pts, col)
	# Warm windows that flicker like candles.
	for win in _windows:
		var x: float = w * win[0] + dx
		var y: float = base - h * win[1]
		var a := 0.55 + 0.35 * sin(_t * 1.3 + win[2]) * sin(_t * 0.37 + win[2] * 2.0)
		draw_rect(Rect2(x, y - 9, 5, 9), Color(0.95, 0.72, 0.35, a * 0.8))
		draw_circle(Vector2(x + 2.5, y - 4.5), 9.0, Color(0.95, 0.65, 0.3, a * 0.05))
