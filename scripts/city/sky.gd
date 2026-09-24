class_name CitySky
extends Node3D
## The sky: atmosphere, sun, moon, stars, clouds, storms and meteors (assets/shaders/sky.gdshader, docs/SKY.md).
## Added by greybox_district.gd right after Weather. It owns the WorldEnvironment's Sky resource (a ShaderMaterial in
## place of the old ProceduralSkyMaterial) and reads everything else from the weather:
##   - Weather.current() at 2 Hz and `changed`: preset, kind, time_of_day, daylight, wind, snow cover;
##   - the weather preset's sky_top / sky_horizon / day_top / day_horizon / fog_color (the night gradient stays what
##     the weather agent tuned, so the SDFGI ambient does not move);
##   - the `moon_light` DirectionalLight3D that weather.gd rotates (sun by day, moon by night): its direction is the
##     sun or moon in the sky, its colour and energy light the clouds.
## Cloud looks per preset live in data/sky.json; parameters cross-fade over transition_s.
## Static API (one instance per district):
##   CitySky.instance() -> CitySky
##   CitySky.set_look(type_or_params)     a cloud type name from sky.json ("storm") or a Dictionary of overrides;
##                                        cleared by the next weather change. Snap with CitySky.instance().snap()
##   signal lightning(strength, delay_s)  a strike: 0..1 strength, seconds until the thunder (distance / 343 m/s)
## `--sky-shot=<dir>` (with `--perf`) captures the sky set to <dir> and quits.

signal lightning(strength: float, delay_s: float)

const DATA := "res://data/sky.json"
const SHADER := preload("res://assets/shaders/sky.gdshader")
## json key -> shader uniform for the cross-faded floats
const UNIFORMS := {
	"coverage": "cloud_coverage", "softness": "cloud_softness", "scale": "cloud_scale", "altitude": "cloud_altitude",
	"density": "cloud_density", "base_dark": "cloud_base_dark", "detail": "cloud_detail", "sheet": "cloud_sheet",
	"ragged": "cloud_ragged", "tower": "cloud_tower", "cirrus": "cirrus", "cirrus_streak": "cirrus_streak",
	"haze": "haze", "haze_height": "haze_height", "halo22": "halo22", "moon_halo": "moon_halo",
	"star_strength": "star_strength",
}
const THUNDER_VARIANTS := 3

static var _data: Dictionary = {}
static var _active: CitySky = null
static var _pending_look: Variant = null

var mat: ShaderMaterial
var sky: Sky
var frozen := false                  ## shots: no scheduled meteors or strikes

var _env: Environment
var _light: DirectionalLight3D
var _cur: Dictionary = {}            ## smoothed look (json keys)
var _tgt: Dictionary = {}
var _look_override: Variant = null
var _preset := ""
var _tod := 21.0
var _daylight := 0.0
var _wind := Vector2.ZERO
var _moon_energy := 0.45
var _sun_elev := -30.0
var _cloud_offset := Vector2.ZERO
var _cirrus_offset := Vector2.ZERO
var _t_poll := 0.0
var _rng := RandomNumberGenerator.new()
# lightning
var _flash_light: DirectionalLight3D
var _flash_pulses: Array = []        ## [start_s, peak]
var _flash_t := 0.0
var _flash_on := false
var _flash_hold := -1.0
var _next_strike := 6.0
var _thunder: Array = []             ## AudioStreamWAV, built on first storm
var _thunder_building := false
var _thunder_player: AudioStreamPlayer
# meteors
var _meteor_t := -1.0
var _meteor_dur := 1.0
var _meteor_hold := false
var _next_meteor := 20.0
var _comet_force := false      ## shots


# ------------------------------------------------------------------ static API

static func data() -> Dictionary:
	if _data.is_empty():
		var f := FileAccess.open(DATA, FileAccess.READ)
		var parsed: Variant = JSON.parse_string(f.get_as_text()) if f else null
		_data = parsed if parsed is Dictionary else {"types": {}, "presets": {}}
	return _data


static func instance() -> CitySky:
	return _active if _active != null and is_instance_valid(_active) and _active.is_inside_tree() else null


## A cloud type name from data/sky.json or a Dictionary of parameter overrides; null clears. Applies to the next
## district when none is up.
static func set_look(look: Variant) -> void:
	var s := instance()
	if s:
		s.apply_look(look)
	else:
		_pending_look = look


# ------------------------------------------------------------------ setup

func _ready() -> void:
	name = "Sky"
	_active = self
	_rng.seed = 1795 + GameState.day
	_find_env()
	_build_sky()
	_find_light()
	_flash_light = DirectionalLight3D.new()
	_flash_light.name = "LightningLight"
	_flash_light.light_color = Color(0.82, 0.86, 1.0)
	_flash_light.light_energy = 0.0
	_flash_light.visible = false
	_flash_light.shadow_enabled = true
	_flash_light.directional_shadow_max_distance = 70.0
	_flash_light.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	_flash_light.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_ONLY
	_flash_light.light_volumetric_fog_energy = 0.6
	add_child(_flash_light)
	_thunder_player = AudioStreamPlayer.new()
	_thunder_player.bus = "SFX"
	add_child(_thunder_player)
	var w := Weather.instance()
	if w:
		w.changed.connect(_on_weather)
	var look: Variant = _pending_look
	_pending_look = null
	_on_weather(Weather.current())
	if look != null:
		apply_look(look)
	snap()
	_poll()
	_push_static()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--sky-shot="):
			var r := _Shots.new()
			r.shot_dir = a.trim_prefix("--sky-shot=")
			r.sky = self
			get_tree().root.add_child.call_deferred(r)


func _exit_tree() -> void:
	if _active == self:
		_active = null


func _find_env() -> void:
	for n in get_tree().get_nodes_in_group("world_env"):
		if n is WorldEnvironment and (_env == null or n.get_parent() == get_parent()):
			_env = (n as WorldEnvironment).environment
	if _env == null:
		for n in get_parent().get_children():
			if n is WorldEnvironment:
				_env = (n as WorldEnvironment).environment


func _find_light() -> void:
	var world := get_world_3d()
	for n in get_tree().get_nodes_in_group("moon_light"):
		if n is DirectionalLight3D and (n as Node3D).get_world_3d() == world:
			_light = n
			return


func _build_sky() -> void:
	mat = ShaderMaterial.new()
	mat.shader = SHADER
	if "--no-sky" in OS.get_cmdline_user_args():
		# perf A/B: the flat ProceduralSky the district had before this node
		var sm := ProceduralSkyMaterial.new()
		sm.sky_top_color = Color(0.02, 0.025, 0.06)
		sm.sky_horizon_color = Color(0.10, 0.09, 0.14)
		sm.ground_bottom_color = Color(0.02, 0.02, 0.03)
		sm.ground_horizon_color = Color(0.08, 0.07, 0.10)
		sm.sun_angle_max = 1.6
		sm.sun_curve = 0.12
		sky = Sky.new()
		sky.sky_material = sm
		if _env:
			_env.sky = sky
		set_process(false)
		return
	mat.set_shader_parameter("noise_a", _noise(512, 0.0075, 5, 11))
	mat.set_shader_parameter("noise_b", _noise(256, 0.02, 4, 71))
	sky = Sky.new()
	sky.sky_material = mat
	# incremental: the cubemap SDFGI and reflections read is re-rendered over a few frames whenever a uniform changes
	# (every frame while clouds drift), at 128 px a face; never a full sky per frame.
	sky.process_mode = Sky.PROCESS_MODE_INCREMENTAL
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	if _env:
		_env.background_mode = Environment.BG_SKY
		_env.sky = sky
		# The engine mixes the on-screen sky toward fog_light_color by fog_sky_affect with the fog amount fixed at 1,
		# and weather.gd sets fog_sky_affect 1.0 at night: the sky would be a flat fog colour. Aerial perspective
		# feeds the sky's own colour back into that mix (and lets distance fog take the sky's tint, which is what
		# real haze does); the presets' whiteouts come from the shader's haze term instead.
		_env.fog_aerial_perspective = 0.9


func _noise(size: int, freq: float, octaves: int, seed: int) -> NoiseTexture2D:
	var n := FastNoiseLite.new()
	n.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	n.seed = seed
	n.frequency = freq
	n.fractal_type = FastNoiseLite.FRACTAL_FBM
	n.fractal_octaves = octaves
	n.fractal_lacunarity = 2.1
	n.fractal_gain = 0.52
	var t := NoiseTexture2D.new()
	t.noise = n
	t.width = size
	t.height = size
	t.seamless = true
	t.seamless_blend_skirt = 0.2
	t.generate_mipmaps = true
	return t


# ------------------------------------------------------------------ looks

## The look for a weather state: the preset's entry, else the kind's type, else clear; then the override.
func _look_for(state: Dictionary) -> Dictionary:
	var d := data()
	var types: Dictionary = d.get("types", {})
	var presets: Dictionary = d.get("presets", {})
	var pname := str(state.get("preset", ""))
	var entry: Dictionary = presets.get(pname, {})
	var kinds: Dictionary = d.get("kinds", {})
	var tname := str(entry.get("type", kinds.get(str(state.get("kind", "clear")), "clear")))
	var look: Dictionary = (types.get(tname, types.get("clear", {})) as Dictionary).duplicate()
	for k in entry:
		if k != "type" and not str(k).begins_with("_"):
			look[k] = entry[k]
	if _look_override is String:
		var t: Dictionary = types.get(str(_look_override), {})
		for k in t:
			look[k] = t[k]
	elif _look_override is Dictionary:
		for k in _look_override:
			look[k] = _look_override[k]
	return look


func _on_weather(state: Dictionary) -> void:
	if state.is_empty():
		return
	var pname := str(state.get("preset", ""))
	if pname != _preset:
		_look_override = null
		_preset = pname
	_tgt = _look_for(state)
	if _cur.is_empty():
		_cur = _tgt.duplicate()
	# a storm arrives with its first strike soon
	if float(_tgt.get("storm", 0.0)) > 0.05:
		_next_strike = minf(_next_strike, 2.5)
		_ensure_thunder()


func apply_look(look: Variant) -> void:
	_look_override = look
	_tgt = _look_for(Weather.current())
	if float(_tgt.get("storm", 0.0)) > 0.05:
		_next_strike = minf(_next_strike, 1.5)
		_ensure_thunder()


## Skips the cross-fade.
func snap() -> void:
	_cur = _tgt.duplicate()
	_push_look()


func look() -> Dictionary:
	return _cur


func _push_look() -> void:
	for k in UNIFORMS:
		if _cur.has(k):
			mat.set_shader_parameter(UNIFORMS[k], float(_cur[k]))


# ------------------------------------------------------------------ per frame

func _process(delta: float) -> void:
	# cross-fade the look
	var tau := maxf(float(data().get("transition_s", 18.0)), 0.1)
	var k := 1.0 - exp(-delta / tau)
	var moved := false
	for key in _tgt:
		var t := float(_tgt[key])
		var c := float(_cur.get(key, t))
		if absf(t - c) > 0.0005:
			_cur[key] = c + (t - c) * k
			moved = true
		elif c != t:
			_cur[key] = t
			moved = true
	if moved:
		_push_look()
	# clouds drift with the wind (a little even in still air: the upper air moves)
	var w := _wind + Vector2(0.4, 0.15)
	_cloud_offset += w * delta * 0.0011
	_cirrus_offset += w * delta * 0.0005
	mat.set_shader_parameter("cloud_offset", _cloud_offset)
	mat.set_shader_parameter("cirrus_offset", _cirrus_offset)
	_t_poll -= delta
	if _t_poll <= 0.0:
		_t_poll = 0.5
		_poll()
	_lightning_step(delta)
	_meteor_step(delta)


## Reads the weather and the directional light; pushes the slow uniforms.
func _poll() -> void:
	var s := Weather.current()
	if not s.is_empty():
		if str(s.get("preset", "")) != _preset:
			_on_weather(s)
		_tod = float(s.get("time_of_day", _tod))
		_daylight = float(s.get("daylight", 0.0))
		var wv: Variant = s.get("wind", Vector2.ZERO)
		_wind = wv if wv is Vector2 else Vector2.ZERO
	# the sun's elevation as weather.gd computes it (the light is the sun while it is above -3 degrees); when the
	# weather state carries sun_elevation / sun_azimuth (degrees) those win over the mirrored formula
	_sun_elev = float(s.get("sun_elevation", 20.0 * sin(PI * (_tod - 6.0) / 12.0)))
	var sun_is_light := _sun_elev > -3.0
	var az := deg_to_rad(float(s.get("sun_azimuth", -(_tod - 12.0) * 14.0)))
	var sun_dir := Basis.from_euler(Vector3(deg_to_rad(-maxf(_sun_elev, -20.0)), az, 0.0)).z
	var moon_dir := Basis.from_euler(Vector3(deg_to_rad(Weather.MOON_ROT.x), deg_to_rad(Weather.MOON_ROT.y), 0.0)).z
	var sun_color := Color(1.0, 0.93, 0.84)
	var moon_energy := 0.0
	if _light:
		var ld := _light.global_transform.basis.z
		if sun_is_light:
			sun_dir = ld
			sun_color = _light.light_color
		else:
			moon_dir = ld
			moon_energy = _light.light_energy
	_moon_energy = moon_energy
	mat.set_shader_parameter("sun_dir", sun_dir)
	mat.set_shader_parameter("moon_dir", moon_dir)
	mat.set_shader_parameter("sun_color", sun_color)
	mat.set_shader_parameter("sun_up", 1.0 if sun_is_light else 0.0)
	mat.set_shader_parameter("sun_elev", _sun_elev)
	mat.set_shader_parameter("moon_energy", moon_energy)
	mat.set_shader_parameter("daylight", _daylight)
	mat.set_shader_parameter("wind_dir", _wind if _wind.length() > 0.05 else Vector2(1.0, 0.3))
	mat.set_shader_parameter("star_basis", _star_basis())
	# gradient colours from the weather preset (the same numbers the ProceduralSky used to get)
	var pr: Dictionary = Weather.presets().get(_preset, {})
	var night_top := _c(pr, "sky_top", Color(0.02, 0.025, 0.06))
	var night_hor := _c(pr, "sky_horizon", Color(0.10, 0.09, 0.14))
	var day_top := _c(pr, "day_top", Color(0.3, 0.42, 0.6))
	var day_hor := _c(pr, "day_horizon", Color(0.68, 0.72, 0.78))
	var fog_col := _c(pr, "fog_color", Color(0.07, 0.08, 0.13))
	mat.set_shader_parameter("night_zenith", night_top)
	mat.set_shader_parameter("night_horizon", night_hor)
	mat.set_shader_parameter("day_zenith", day_top)
	mat.set_shader_parameter("day_horizon", day_hor)
	mat.set_shader_parameter("haze_color", fog_col.lerp(day_hor * 0.95, _daylight))
	var snow := float(s.get("snow_cover", 1.0)) if not s.is_empty() else 1.0
	var ground := night_top.darkened(0.5).lerp(Color(0.5, 0.52, 0.56).lerp(Color(0.32, 0.30, 0.28), 1.0 - snow), _daylight)
	mat.set_shader_parameter("ground_color", ground)
	var md: Dictionary = data().get("moon", {})
	var phase := fposmod(float(md.get("phase_night1", 0.62)) + float(GameState.day - 1) * float(md.get("phase_per_night", 0.034)), 1.0)
	mat.set_shader_parameter("moon_phase", phase)
	# the comet: on from its night, only for looks that ask for it (clear skies)
	var cd: Dictionary = data().get("comet", {})
	var comet_on: bool = _comet_force or (bool(cd.get("enabled", true)) and GameState.day >= int(cd.get("from_night", 3)) and bool(_tgt.get("comet", false)))
	mat.set_shader_parameter("comet", float(cd.get("strength", 0.35)) if comet_on else 0.0)


func _push_static() -> void:
	var sd: Dictionary = data().get("stars", {})
	mat.set_shader_parameter("milky_way", float(sd.get("milky_way", 0.6)))
	mat.set_shader_parameter("twinkle", float(sd.get("twinkle", 0.6)))
	mat.set_shader_parameter("planets", float(sd.get("planets", 1.0)))
	var md: Dictionary = data().get("moon", {})
	mat.set_shader_parameter("moon_size", float(md.get("size_deg", 0.5)))
	var cd: Dictionary = data().get("comet", {})
	var head := _equatorial(float(cd.get("ra_hours", 22.9)), float(cd.get("dec_deg", 14.0)))
	var sun := _equatorial(float(cd.get("sun_ra_hours", 20.0)), float(cd.get("sun_dec_deg", -21.0)))
	mat.set_shader_parameter("comet_dir", head)
	mat.set_shader_parameter("comet_tail", (head - sun).normalized())


func _c(pr: Dictionary, key: String, fallback: Color) -> Color:
	var v: Variant = pr.get(key)
	if v is Array and (v as Array).size() >= 3:
		return Color(float(v[0]), float(v[1]), float(v[2]))
	return fallback


# ------------------------------------------------------------------ celestial frame

static func _equatorial(ra_hours: float, dec_deg: float) -> Vector3:
	var ra := deg_to_rad(ra_hours * 15.0)
	var dec := deg_to_rad(dec_deg)
	return Vector3(cos(dec) * cos(ra), cos(dec) * sin(ra), sin(dec))


## Local sidereal time in hours for the game clock (mid-January, Kraków).
func _lst_hours() -> float:
	var sd: Dictionary = data().get("stars", {})
	return fposmod(float(sd.get("lst_hours_at_21", 5.0)) + (_tod - 21.0) * 1.0027379, 24.0)


## world (x east, y up, z south) -> equatorial (x RA 0h, z north celestial pole)
func _star_basis() -> Basis:
	var sd: Dictionary = data().get("stars", {})
	var lat := deg_to_rad(float(sd.get("latitude_deg", 50.06)))
	var lst := deg_to_rad(_lst_hours() * 15.0)
	var cl := cos(lst)
	var sl := sin(lst)
	var cp := cos(lat)
	var sp := sin(lat)
	# local(e) for the equatorial basis vectors: east = -(ex sl - ey cl), up = ez sp + (ex cl + ey sl) cp,
	# south = -(ez cp - (ex cl + ey sl) sp)
	var ex := Vector3(-sl, cl * cp, cl * sp)
	var ey := Vector3(cl, sl * cp, sl * sp)
	var ez := Vector3(0.0, sp, -cp)
	var local_from_eq := Basis(ex, ey, ez)
	return local_from_eq.transposed()


func _local_from_equatorial(e: Vector3) -> Vector3:
	return _star_basis().transposed() * e


# ------------------------------------------------------------------ lightning

func _lightning_step(delta: float) -> void:
	var ld: Dictionary = data().get("lightning", {})
	var storm := float(_cur.get("storm", 0.0))
	if storm > 0.05 and not frozen and _flash_hold < 0.0:
		_next_strike -= delta * storm
		if _next_strike <= 0.0:
			_next_strike = _rng.randf_range(float(ld.get("min_gap_s", 3.5)), float(ld.get("max_gap_s", 13.0)))
			var km := _rng.randf_range(float(ld.get("min_km", 0.6)), float(ld.get("max_km", 9.0)))
			km = lerpf(km, float(ld.get("min_km", 0.6)), _rng.randf() * 0.3)   # a few close ones
			strike(km, km < float(ld.get("bolt_max_km", 4.5)) and _rng.randf() < 0.6)
	if _flash_hold >= 0.0:
		return
	if not _flash_on:
		return
	_flash_t += delta
	var f := 0.0
	var alive := false
	for p in _flash_pulses:
		var t0 := float(p[0])
		if _flash_t >= t0:
			var e := float(p[1]) * exp(-(_flash_t - t0) / 0.055)
			f += e
			if e > 0.01:
				alive = true
		else:
			alive = true
	f = minf(f, 1.0)
	mat.set_shader_parameter("flash", f)
	_flash_light.light_energy = f * float(ld.get("light_energy", 2.6))
	if not alive:
		_flash_on = false
		_flash_light.visible = false
		_flash_light.light_energy = 0.0
		mat.set_shader_parameter("flash", 0.0)


## A strike `km` away: sky flash and a light on the town now, thunder after the sound has travelled. Emits `lightning`.
func strike(km: float, bolt: bool, az_rad: float = NAN) -> float:
	var strength := clampf(1.8 / maxf(km, 0.4), 0.12, 1.0)
	if is_nan(az_rad):
		az_rad = _rng.randf_range(0.0, TAU)
	var el := _rng.randf_range(0.06, 0.28)
	var dir := Vector3(sin(az_rad) * cos(el), sin(el), cos(az_rad) * cos(el))
	mat.set_shader_parameter("flash_dir", dir)
	mat.set_shader_parameter("flash_bolt", (0.8 + 0.6 * strength) if bolt else 0.0)
	mat.set_shader_parameter("flash_seed", _rng.randf_range(0.0, 100.0))
	_flash_pulses.clear()
	var t := 0.0
	var n := _rng.randi_range(2, 4)
	for i in n:
		_flash_pulses.append([t, _rng.randf_range(0.45, 1.0) * strength * (1.0 if i == 0 else 0.7)])
		t += _rng.randf_range(0.04, 0.11)
	_flash_t = 0.0
	_flash_on = true
	_flash_light.visible = true
	_flash_light.shadow_enabled = km < 3.0
	_flash_light.look_at_from_position(Vector3.ZERO, -dir, Vector3.UP)
	var delay := km / 0.343
	lightning.emit(strength, delay)
	var ld: Dictionary = data().get("lightning", {})
	if bool(ld.get("thunder", true)):
		get_tree().create_timer(delay, false).timeout.connect(_thunder_play.bind(strength, km))
	return delay


## Shots: hold a flash frame (strength <= 0 releases).
func hold_flash(strength: float, bolt: bool, dir: Vector3) -> void:
	if strength <= 0.0:
		_flash_hold = -1.0
		_flash_on = false
		_flash_light.visible = false
		mat.set_shader_parameter("flash", 0.0)
		return
	_flash_hold = strength
	mat.set_shader_parameter("flash_dir", dir.normalized())
	mat.set_shader_parameter("flash_bolt", 1.3 if bolt else 0.0)
	mat.set_shader_parameter("flash_seed", 37.0)
	mat.set_shader_parameter("flash", strength)
	_flash_light.visible = true
	_flash_light.shadow_enabled = true
	_flash_light.look_at_from_position(Vector3.ZERO, -dir.normalized(), Vector3.UP)
	var ld: Dictionary = data().get("lightning", {})
	_flash_light.light_energy = strength * float(ld.get("light_energy", 2.6))


func _thunder_play(strength: float, km: float) -> void:
	if _thunder.is_empty() or not is_inside_tree():
		return
	var far := km > 3.0
	var idx := (THUNDER_VARIANTS - 1) if far else _rng.randi_range(0, THUNDER_VARIANTS - 2)
	_thunder_player.stream = _thunder[idx]
	var ld: Dictionary = data().get("lightning", {})
	_thunder_player.volume_db = float(ld.get("thunder_db", -8.0)) + linear_to_db(clampf(strength, 0.15, 1.0)) * 0.6
	_thunder_player.pitch_scale = _rng.randf_range(0.9, 1.05) * (0.85 if far else 1.0)
	_thunder_player.play()


## Synthesises the thunder variants once, off the main thread (no thunder sample in assets/audio yet).
func _ensure_thunder() -> void:
	if not _thunder.is_empty() or _thunder_building:
		return
	_thunder_building = true
	WorkerThreadPool.add_task(_build_thunder)


func _build_thunder() -> void:
	var out: Array = []
	for i in THUNDER_VARIANTS:
		out.append(_synth_thunder(41 + i * 7, i < THUNDER_VARIANTS - 1))
	_thunder_ready.call_deferred(out)


func _thunder_ready(pcm: Array) -> void:
	if "--smoke" in OS.get_cmdline_user_args() or "--sky-shot=" in " ".join(OS.get_cmdline_user_args()):
		print("[smoke] sky thunder variants=%d bytes=%d" % [pcm.size(), (pcm[0] as PackedByteArray).size() if not pcm.is_empty() else 0])
	for p in pcm:
		var w := AudioStreamWAV.new()
		w.format = AudioStreamWAV.FORMAT_16_BITS
		w.mix_rate = 22050
		w.stereo = false
		w.data = p
		_thunder.append(w)
	_thunder_building = false


## A thunder clap: an optional crack, then low rolling rumble (noise through wandering low-pass filters under a few
## overlapping bumps), a sub boom, soft clip, normalised near -18 dBFS RMS like the library.
static func _synth_thunder(seed: int, near: bool) -> PackedByteArray:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed
	var sr := 22050
	var dur := 6.5 if near else 7.5
	var n := int(dur * sr)
	var buf := PackedFloat32Array()
	buf.resize(n)
	# bumps of the roll
	var bumps: Array = []
	var nb := rng.randi_range(4, 7)
	for i in nb:
		bumps.append([rng.randf_range(0.05, 3.2), rng.randf_range(0.25, 1.1), rng.randf_range(0.4, 1.0)])
	var lp1 := 0.0
	var lp2 := 0.0
	var lp3 := 0.0
	var cut := 120.0
	var cut_target := 120.0
	var boom_phase := 0.0
	var sum_sq := 0.0
	for i in n:
		var t := float(i) / sr
		var white := rng.randf_range(-1.0, 1.0)
		if i % 512 == 0:
			cut_target = rng.randf_range(55.0, 260.0 if near else 140.0)
		cut += (cut_target - cut) * 0.002
		var a := 1.0 - exp(-TAU * cut / sr)
		lp1 += (white - lp1) * a
		lp2 += (lp1 - lp2) * a
		lp3 += (lp2 - lp3) * a
		var env := 0.0
		for b in bumps:
			var dt: float = (t - float(b[0])) / float(b[1])
			env += float(b[2]) * exp(-dt * dt * 2.0)
		env *= exp(-t / 2.4)
		var s := lp3 * env * 9.0
		if near:
			s += white * exp(-t / 0.045) * 0.9 * (1.0 - exp(-t / 0.002))
			s += lp1 * exp(-t / 0.35) * 1.5
		var bf := 55.0 * exp(-t / 1.4) + 28.0
		boom_phase += TAU * bf / sr
		s += sin(boom_phase) * exp(-t / 1.3) * (0.5 if near else 0.3)
		s = tanh(s * 1.4)
		buf[i] = s
		sum_sq += s * s
	var rms := sqrt(sum_sq / n)
	var gain := 0.125 / maxf(rms, 1e-4)     # ~ -18 dBFS
	var pcm := PackedByteArray()
	pcm.resize(n * 2)
	for i in n:
		var v := int(clampf(buf[i] * gain, -1.0, 1.0) * 32767.0)
		pcm.encode_s16(i * 2, v)
	return pcm


# ------------------------------------------------------------------ meteors

func _meteor_step(delta: float) -> void:
	if _meteor_hold:
		return
	if _meteor_t >= 0.0:
		_meteor_t += delta / _meteor_dur
		if _meteor_t >= 1.0:
			_meteor_t = -1.0
		mat.set_shader_parameter("meteor_t", _meteor_t)
		return
	if frozen:
		return
	var night := 1.0 - smoothstep(-9.0, -1.0, _sun_elev)
	var clear := (1.0 - float(_cur.get("coverage", 0.0)))
	var rate := night * clear * clear * (1.0 - float(_cur.get("haze", 0.3)) * 0.8) * float(_cur.get("meteors", 1.0))
	if rate <= 0.001:
		return
	_next_meteor -= delta * rate
	if _next_meteor <= 0.0:
		var md: Dictionary = data().get("meteors", {})
		_next_meteor = _rng.randf_range(0.35, 1.8) * float(md.get("mean_interval_s", 40.0))
		spawn_meteor(_rng.randf() < float(md.get("fireball_chance", 0.04)))


## A shooting star now (a fireball if `fire`). Direction from the radiant half the time.
func spawn_meteor(fire: bool) -> void:
	var md: Dictionary = data().get("meteors", {})
	var el := _rng.randf_range(deg_to_rad(22.0), deg_to_rad(78.0))
	var az := _rng.randf_range(0.0, TAU)
	var a := Vector3(sin(az) * cos(el), sin(el), cos(az) * cos(el))
	var travel: Vector3
	var radiant := _local_from_equatorial(_equatorial(float(md.get("radiant_ra_hours", 15.3)), float(md.get("radiant_dec_deg", 49.5))))
	if radiant.y > 0.05 and _rng.randf() < float(md.get("radiant_share", 0.5)):
		travel = a - radiant
	else:
		travel = Vector3(_rng.randf_range(-1, 1), _rng.randf_range(-1, -0.2), _rng.randf_range(-1, 1))
	travel = (travel - a * travel.dot(a)).normalized()
	var length := deg_to_rad(_rng.randf_range(6.0, 20.0) * (2.0 if fire else 1.0))
	var b := (a * cos(length) + travel * sin(length)).normalized()
	_meteor_dur = _rng.randf_range(0.35, 0.9) * (2.2 if fire else 1.0)
	_meteor_t = 0.0
	mat.set_shader_parameter("meteor_a", a)
	mat.set_shader_parameter("meteor_b", b)
	mat.set_shader_parameter("meteor_bright", (_rng.randf_range(4.0, 7.0)) if fire else (0.25 + 0.8 * pow(_rng.randf(), 2.0)))
	mat.set_shader_parameter("meteor_fire", 1.0 if fire else 0.0)
	mat.set_shader_parameter("meteor_t", 0.0)


## Shots: a meteor held at progress `t` from `a` toward `b` (t < 0 releases).
func hold_meteor(a: Vector3, b: Vector3, t: float, bright: float, fire: bool) -> void:
	if t < 0.0:
		_meteor_hold = false
		_meteor_t = -1.0
		mat.set_shader_parameter("meteor_t", -1.0)
		return
	_meteor_hold = true
	mat.set_shader_parameter("meteor_a", a.normalized())
	mat.set_shader_parameter("meteor_b", b.normalized())
	mat.set_shader_parameter("meteor_bright", bright)
	mat.set_shader_parameter("meteor_fire", 1.0 if fire else 0.0)
	mat.set_shader_parameter("meteor_t", t)


func sun_elevation() -> float:
	return _sun_elev


# ------------------------------------------------------------------ captures (`--perf --sky-shot=<dir>`)

class _Shots extends Node3D:
	var shot_dir := ""
	var sky: CitySky

	func _ready() -> void:
		process_mode = Node.PROCESS_MODE_ALWAYS
		await _run()
		queue_free()

	func _frames(n: int) -> void:
		for i in n:
			await get_tree().process_frame

	func _dir(az_deg: float, el_deg: float) -> Vector3:
		var az := deg_to_rad(az_deg)
		var el := deg_to_rad(el_deg)
		return Vector3(sin(az) * cos(el), sin(el), cos(az) * cos(el))

	func _az_of(v: Vector3) -> float:
		return rad_to_deg(atan2(v.x, v.z))

	func _run() -> void:
		DirAccess.make_dir_recursive_absolute(shot_dir)
		await _frames(240)
		var sub := SubViewport.new()
		sub.size = Vector2i(get_viewport().get_visible_rect().size)
		sub.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		sub.msaa_3d = get_viewport().msaa_3d
		sub.use_taa = get_viewport().use_taa
		add_child(sub)
		sub.world_3d = get_viewport().world_3d
		var cam := Camera3D.new()
		cam.far = 400.0
		cam.fov = 62.0
		sub.add_child(cam)
		cam.current = true
		Weather.shot_camera = cam
		sky.frozen = true
		var only := ""
		for a in OS.get_cmdline_user_args():
			if a.begins_with("--sky-shot-only="):
				only = a.trim_prefix("--sky-shot-only=")
		var eye_a := Vector3(-22.0, 4.0, -22.0)     # north-west corner of the square: south to east is open
		var eye_e := Vector3(12.0, 4.5, -22.0)      # along the north row: west is open
		var eye_c := Vector3(12.0, 5.0, 22.0)       # south-east: the low west-north-west sky over the Town Hall
		# [name, weather conditions, look override or "", aim: "moon" | "sun" | [az, el], extra, eye ("e" = eye_e)]
		var shots: Array = [
			["clear_night", {"preset": "clear_frost", "time_of_day": 23.6, "freeze": true}, "", "moon", "meteor"],
			["clear_night_comet", {"preset": "clear_frost", "time_of_day": 23.6, "freeze": true}, "", "comet", "comet", "c"],
			["moon_thin_cloud", {"preset": "clear_frost", "time_of_day": 23.0, "freeze": true}, "cirrus", "moon", ""],
			["fair_night", {"preset": "clear_frost", "time_of_day": 22.0, "freeze": true}, "fair", "moon_side", ""],
			["overcast_night", {"preset": "overcast", "time_of_day": 22.0, "freeze": true}, "", [20.0, 28.0], ""],
			["rain_night", {"preset": "rain_thaw", "time_of_day": 22.0, "freeze": true}, "", [60.0, 26.0], ""],
			["storm_night", {"preset": "rain_thaw", "time_of_day": 22.5, "freeze": true, "wind": [6.0, 2.5]}, "storm", [40.0, 26.0], "flash"],
			["fog_night", {"preset": "fog", "time_of_day": 23.0, "freeze": true}, "", [40.0, 22.0], ""],
			["dawn", {"preset": "clear_frost", "time_of_day": 6.7, "freeze": true}, "", "sun", ""],
			["dawn_cirrus", {"preset": "clear_frost", "time_of_day": 7.2, "freeze": true}, "cirrus", "sun_side", ""],
			["clear_day", {"preset": "clear_day"}, "", "sun_side", ""],
			["cumulus_day", {"preset": "clear_day"}, "fair", "sun_side", ""],
			["snow_day", {"preset": "snow_day"}, "", [300.0, 28.0], "", "e"],
			["overcast_day", {"preset": "overcast", "time_of_day": 11.0, "freeze": true}, "", [250.0, 28.0], "", "e"],
			["dusk", {"preset": "clear_frost", "time_of_day": 16.6, "freeze": true}, "", "sun", "", "e"],
		]
		for s in shots:
			var nm: String = s[0]
			if only != "" and not (nm in only.split(",")):
				continue
			Weather.set_conditions(s[1])
			await _frames(2)
			sky.apply_look(str(s[2]) if str(s[2]) != "" else null)
			sky.snap()
			sky._poll()
			await _frames(30)
			var aim: Variant = s[3]
			var dir: Vector3
			var light := sky._light
			var body := light.global_transform.basis.z if light else Vector3(0, 0.5, 0.86)
			if aim is String:
				var el := clampf(rad_to_deg(asin(body.y)), 4.0, 40.0)
				match str(aim):
					"moon", "sun":
						dir = _dir(_az_of(body), el * 0.55 + 6.0)
					"moon_side", "sun_side":
						dir = _dir(_az_of(body) + 55.0, 24.0)
					"comet":
						var cd: Dictionary = sky.data().get("comet", {})
						var c := sky._local_from_equatorial(sky._equatorial(float(cd.get("ra_hours", 1.5)), float(cd.get("dec_deg", 30.0))))
						dir = _dir(_az_of(c) + 14.0, clampf(rad_to_deg(asin(c.y)), 6.0, 40.0) - 4.0)   # the comet left of centre
			else:
				dir = _dir(float(aim[0]), float(aim[1]))
			var which: String = str(s[5]) if s.size() > 5 else ""
			var eye := eye_e if which == "e" else (eye_c if which == "c" else eye_a)
			cam.look_at_from_position(eye, eye + dir, Vector3.UP)
			var extra: String = str(s[4])
			if extra == "meteor":
				var right := dir.cross(Vector3.UP).normalized()
				var up := right.cross(dir).normalized()
				var a := (dir + up * 0.32 + right * 0.30).normalized()
				var b := (dir + up * 0.10 + right * 0.02).normalized()
				sky.hold_meteor(a, b, 0.62, 1.3, false)
			elif extra == "flash":
				var delay := sky.strike(2.0, true)     # the real path once (timer, thunder), then a held frame
				print("[smoke] sky strike delay_s=%.1f" % delay)
				await _frames(20)
				sky.hold_flash(0.7, true, _dir(float(aim[0]) - 12.0, 20.0))
			elif extra == "comet":
				sky._comet_force = true
				sky._poll()
			await _frames(8)
			sub.get_texture().get_image().save_png(shot_dir.path_join(nm + ".png"))
			print("[smoke] sky shot %s sun_elev=%.1f look=%s" % [nm, sky.sun_elevation(), str(s[2])])
			sky.hold_meteor(Vector3.UP, Vector3.UP, -1.0, 0.0, false)
			sky.hold_flash(0.0, false, Vector3.UP)
		print("[smoke] sky shots in ", shot_dir)
		Weather.shot_camera = null
		sky.frozen = false
		get_tree().quit()
