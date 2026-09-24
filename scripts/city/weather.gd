class_name Weather
extends Node3D
## Weather and time of day for the night district (added by greybox_district.gd after _environment()).
## Presets live in data/weather.json (clear_frost, light_snow, blizzard, sleet, rain_thaw, fog, overcast, clear_day,
## snow_day). One node per district; the static API reaches whichever one is live:
##   Weather.set_conditions("rain_thaw")                         a preset by name (a fresh start: its start cover / wetness)
##   Weather.set_conditions({kind, intensity, wind, temperature, snow_cover, wetness, time_of_day, preset})
##                                                              tweaks: a kind picks its preset's look, keys override
##   Weather.current() -> Dictionary                             preset, kind, intensity, wind, wind_speed, temperature,
##                                                              snow_cover, wetness, time_of_day, daylight, visibility...
##   signal changed(state)                                       on every set_conditions
## Called before a district exists (the campaign picking tonight's weather), the conditions wait for the next one.
## `--weather=<preset>` on the command line picks the first night's preset.
##
## What it drives:
##  - global shader parameters `snow_cover`, `wetness`, `wind`, `precipitation` (project.godot [shader_globals]):
##    the baked roof snow melts (assets/shaders/snow_cover.gdshader) and the cobbles get snow / puddles
##    (assets/shaders/wet_surface.gdshader); Assets.apply_wetness darkens and glosses plaster, wood, tile, cobble.
##    snow_cover and wetness drift toward the preset's targets per game hour (rain_thaw: 1.0 -> 0.3 over ~6 h).
##  - sky, ambient, fog, exposure and the directional light: the moon at night, a low winter sun after 06:00 (or at the
##    preset's fixed time_of_day); flame lights fade toward off in daylight (FlickerLight's base energy is scaled,
##    the original kept in meta "weather_base").
##  - precipitation: GPUParticles3D around the camera (a near box and a far ring for flakes and streaks, splash rings
##    within 12 m). Off indoors (below y = -50) and the near volume off while the player has a roof overhead.
##  - stealth: perception.gd reads current() (rain / wind shrink hearing, blizzard / fog shorten sight).
## Smoke: `--smoke` prints `[smoke] weather preset=...` for six presets (60 frames each);
## `--weather-shot=<dir>` saves <preset>_door.png / <preset>_overhead.png for every preset plus a rain_thaw pair.

signal changed(state: Dictionary)

const DATA := "res://data/weather.json"
const INTERIOR_Y := -50.0
const SMOKE_PRESETS := ["clear_frost", "light_snow", "blizzard", "rain_thaw", "fog", "clear_day"]
const KIND_PRESET := {"clear": "clear_frost", "snow": "light_snow", "blizzard": "blizzard", "sleet": "sleet",
		"rain": "rain_thaw", "fog": "fog", "overcast": "overcast"}
const MOON_ROT := Vector3(-34, 40, 0)
const Perception := preload("res://scripts/stealth/perception.gd")

static var _data: Dictionary = {}
static var _active: Weather = null
static var _pending: Variant = null
static var _state: Dictionary = {}
static var _runner_started := false

var preset_name := ""
var preset: Dictionary = {}
var kind := "clear"
var intensity := 0.0
var wind := Vector2.ZERO
var temperature := 0.0
var snow_cover := 1.0
var wetness := 0.0
var snow_target := 1.0
var snow_rate := 0.0
var wet_target := 0.0
var wet_rate := 0.1
var time_override := -1.0
var daylight := 0.0
var visibility := 1.0
var precip_scale := 1.0

var _env: Environment
var _sky: ProceduralSkyMaterial
var _moon: DirectionalLight3D
var _probe: ReflectionProbe
var _probe_daylight := -1.0
var _probe_reset := 0
var _sys: Dictionary = {}          ## name -> GPUParticles3D
var _counts: Dictionary = {}       ## name -> wanted amount
var _light_scale := 1.0
var _under_cover := false
var _indoors := false
var _t_cover := 0.0
var _t_sky := 0.0
var _t_guards := 0.0
var _sent_cover := -1.0
var _last_follow := Vector3(0, -1000, 0)


# ------------------------------------------------------------------ static API

static func data() -> Dictionary:
	if _data.is_empty():
		var f := FileAccess.open(DATA, FileAccess.READ)
		var parsed: Variant = JSON.parse_string(f.get_as_text()) if f else null
		_data = parsed if parsed is Dictionary else {"presets": {}}
	return _data


static func presets() -> Dictionary:
	return data().get("presets", {})


static func instance() -> Weather:
	return _active if _active != null and is_instance_valid(_active) and _active.is_inside_tree() else null


## A preset name or a Dictionary of conditions (see the header). Applies now, or to the next district.
static func set_conditions(c: Variant) -> void:
	var w := instance()
	if w:
		w.apply(c)
	else:
		_pending = c


## The live conditions (an empty Dictionary when no district is up). Cheap: a cached Dictionary, do not modify.
static func current() -> Dictionary:
	return _state if instance() else {}


# ------------------------------------------------------------------ setup

func _ready() -> void:
	name = "Weather"
	_active = self
	_find_refs()
	_build_particles()
	var start: Variant = _pending
	_pending = null
	if start == null:
		for a in OS.get_cmdline_user_args():
			if a.begins_with("--weather="):
				start = a.trim_prefix("--weather=")
	if start == null:
		start = str(data().get("default", "clear_frost"))
	apply(start)
	_late_init.call_deferred()
	var args := OS.get_cmdline_user_args()
	if "--smoke" in args and not _runner_started:
		_runner_started = true
		var r := _Runner.new()
		r.shot_dir = ""
		for a in args:
			if a.begins_with("--weather-shot="):
				r.shot_dir = a.trim_prefix("--weather-shot=")
		get_tree().root.add_child.call_deferred(r)


## The district builds the ground after this node: its (duplicated, parallax) cobble material joins the wet /
## snow overlay pass.
func _late_init() -> void:
	var cob := get_parent().get_node_or_null("Cobbles") as MultiMeshInstance3D
	if cob and cob.multimesh and cob.multimesh.mesh:
		var m := cob.multimesh.mesh.surface_get_material(0) as BaseMaterial3D
		if m:
			Assets.register_ground(m)
	_push_globals()


func _exit_tree() -> void:
	if _active == self:
		_active = null


func _find_refs() -> void:
	var world := get_world_3d()
	for n in get_tree().get_nodes_in_group("world_env"):
		if n is WorldEnvironment and (_env == null or n.get_parent() == get_parent()):
			_env = (n as WorldEnvironment).environment
	if _env == null:
		for n in get_parent().get_children():
			if n is WorldEnvironment:
				_env = n.environment
	if _env and _env.sky and _env.sky.sky_material is ProceduralSkyMaterial:
		_sky = _env.sky.sky_material
	for n in get_tree().get_nodes_in_group("moon_light"):
		if n is DirectionalLight3D and (n as Node3D).get_world_3d() == world:
			_moon = n
			break
	for n in get_parent().get_children():
		if n is ReflectionProbe:
			_probe = n
			break


# ------------------------------------------------------------------ conditions

func apply(c: Variant) -> void:
	var ps := presets()
	var over: Dictionary = {}
	var pname := ""
	var fresh := false
	if c is String or c is StringName:
		pname = str(c)
		fresh = true
	elif c is Dictionary:
		over = c
		if over.has("preset"):
			pname = str(over["preset"])
			fresh = true
		elif over.has("kind"):
			pname = str(KIND_PRESET.get(str(over["kind"]), preset_name))
			if str(over["kind"]) == "clear" and float(over.get("time_of_day", -1.0)) >= 7.0 and float(over.get("time_of_day", -1.0)) <= 17.0:
				pname = "clear_day"
		else:
			pname = preset_name
	if not ps.has(pname):
		if pname != "":
			push_warning("Weather: unknown preset '%s'" % pname)
		pname = str(data().get("default", "clear_frost"))
	preset_name = pname
	preset = ps.get(pname, {})
	kind = str(over.get("kind", preset.get("kind", "clear")))
	var base_int := float(preset.get("intensity", 0.0))
	intensity = float(over.get("intensity", base_int))
	precip_scale = clampf(intensity / base_int, 0.0, 2.0) if base_int > 0.0 else 1.0
	wind = _vec2(over.get("wind", preset.get("wind", [0, 0])))
	temperature = float(over.get("temperature", preset.get("temperature", 0.0)))
	time_override = float(over.get("time_of_day", preset.get("time_of_day", -1.0)))
	visibility = float(over.get("visibility", preset.get("visibility", 1.0)))
	snow_target = float(over.get("snow_target", preset.get("snow_target", 1.0)))
	snow_rate = float(over.get("snow_rate", preset.get("snow_rate", 0.0)))
	wet_target = float(over.get("wet_target", preset.get("wet_target", 0.0)))
	wet_rate = float(over.get("wet_rate", preset.get("wet_rate", 0.1)))
	if fresh:
		snow_cover = float(preset.get("start_snow_cover", snow_cover))
		wetness = float(preset.get("start_wetness", wetness))
	if over.has("snow_cover"):
		snow_cover = clampf(float(over["snow_cover"]), 0.0, 1.0)
	if over.has("wetness"):
		wetness = clampf(float(over["wetness"]), 0.0, 1.0)
	_sent_cover = -1.0
	_push_globals()
	_apply_sky()
	_configure_particles()
	_apply_guards()
	_update_state()
	changed.emit(_state)


func _vec2(v: Variant) -> Vector2:
	if v is Vector2:
		return v
	if v is Vector3:
		return Vector2(v.x, v.z)
	if v is Array and (v as Array).size() >= 2:
		return Vector2(float(v[0]), float(v[1]))
	if v is float or v is int:
		return Vector2(float(v), 0.0)
	return Vector2.ZERO


func _update_state() -> void:
	_state = {
		"preset": preset_name, "kind": kind, "intensity": intensity, "wind": wind, "wind_speed": wind.length(),
		"temperature": temperature, "snow_cover": snow_cover, "wetness": wetness, "time_of_day": _time_of_day(),
		"daylight": daylight, "visibility": visibility, "precipitation": _precip_amount(),
		"particles": particle_count(), "sounds": preset.get("sounds", []), "under_cover": _under_cover,
	}


func _precip_amount() -> float:
	return intensity if kind in ["snow", "blizzard", "sleet", "rain"] else 0.0


func _push_globals() -> void:
	RenderingServer.global_shader_parameter_set("snow_cover", snow_cover)
	RenderingServer.global_shader_parameter_set("wetness", wetness)
	RenderingServer.global_shader_parameter_set("wind", wind)
	RenderingServer.global_shader_parameter_set("precipitation", _precip_amount())
	Assets.apply_wetness(wetness, snow_cover > 0.02 or wetness > 0.02)
	_sent_cover = snow_cover


func _process(delta: float) -> void:
	var hours := delta * GameState.clock_scale / 60.0
	snow_cover = move_toward(snow_cover, snow_target, snow_rate * hours)
	wetness = move_toward(wetness, wet_target, wet_rate * hours)
	if absf(snow_cover - _sent_cover) > 0.001 or absf(wetness - float(_state.get("wetness", 0.0))) > 0.002:
		_push_globals()
		_state["snow_cover"] = snow_cover
		_state["wetness"] = wetness
	_follow()
	_t_cover -= delta
	if _t_cover <= 0.0:
		_t_cover = 0.2
		_check_cover()
	_t_sky -= delta
	if _t_sky <= 0.0:
		_t_sky = 0.5
		_apply_sky()
		_state["daylight"] = daylight
		_state["time_of_day"] = _time_of_day()
	_t_guards -= delta
	if _t_guards <= 0.0:
		_t_guards = 2.0
		_apply_guards()
	if _probe_reset > 0:
		_probe_reset -= 1
		if _probe_reset == 0 and _probe:
			_probe.update_mode = ReflectionProbe.UPDATE_ONCE


func _apply_guards() -> void:
	for g in get_tree().get_nodes_in_group("guards"):
		Perception.weather_apply(g)


# ------------------------------------------------------------------ sky, sun, lights

func _time_of_day() -> float:
	return time_override if time_override >= 0.0 else fmod(GameState.clock_minutes / 60.0, 24.0)


func _c(key: String, fallback: Color) -> Color:
	var v: Variant = preset.get(key)
	if v is Array and (v as Array).size() >= 3:
		return Color(float(v[0]), float(v[1]), float(v[2]), float(v[3]) if (v as Array).size() > 3 else 1.0)
	return fallback


func _apply_sky() -> void:
	var tod := _time_of_day()
	# December in Kraków: the sun clears the roofs only a little (about 18-20 degrees at noon).
	var elev := 20.0 * sin(PI * (tod - 6.0) / 12.0)
	daylight = smoothstep(-5.0, 8.0, elev)
	var ov := float(preset.get("overcast", 0.0))
	var moon_k := 1.0 - smoothstep(-8.0, -3.0, elev)
	var sun_k := smoothstep(-3.0, 6.0, elev)
	var night_top := _c("sky_top", Color(0.02, 0.025, 0.06))
	var night_hor := _c("sky_horizon", Color(0.10, 0.09, 0.14))
	var day_top := _c("day_top", Color(0.2, 0.38, 0.72))
	var day_hor := _c("day_horizon", Color(0.62, 0.70, 0.80))
	var top := night_top.lerp(day_top, daylight)
	var hor := night_hor.lerp(day_hor, daylight)
	# dawn / dusk: a warm band on the horizon while the sun is low
	var low := smoothstep(-4.0, 2.0, elev) * (1.0 - smoothstep(4.0, 12.0, elev)) * (1.0 - ov * 0.8)
	hor = hor.lerp(Color(0.95, 0.62, 0.42), low * 0.45)
	if _sky:
		_sky.sky_top_color = top
		_sky.sky_horizon_color = hor
		var snow_ground := lerpf(0.3, 0.8, snow_cover) * daylight
		_sky.ground_horizon_color = hor.darkened(0.25).lerp(Color(0.75, 0.77, 0.82), snow_ground * 0.4)
		_sky.ground_bottom_color = top.darkened(0.6).lerp(Color(0.5, 0.52, 0.56), snow_ground * 0.5)
		_sky.sun_angle_max = lerpf(1.6, 8.0, sun_k)
		_sky.sun_curve = lerpf(0.12, 0.08, sun_k)
	if _moon:
		if elev > -3.0:
			var az := -(tod - 12.0) * 14.0
			_moon.rotation_degrees = Vector3(-maxf(elev, 3.0), az, 0)
			var warm := Color(1.0, 0.70, 0.48).lerp(Color(1.0, 0.93, 0.84), smoothstep(3.0, 18.0, elev))
			_moon.light_color = warm.lerp(Color(0.86, 0.9, 0.97), ov)
			_moon.light_energy = float(preset.get("sun_energy", 1.2)) * sun_k
			_moon.light_angular_distance = lerpf(0.6, 4.0, ov)
			_moon.light_volumetric_fog_energy = lerpf(0.6, 0.25, ov)
		else:
			_moon.rotation_degrees = MOON_ROT
			_moon.light_color = Color(0.62, 0.72, 1.0).lerp(Color(0.72, 0.76, 0.86), ov)
			_moon.light_energy = float(preset.get("moon_energy", 0.45)) * moon_k
			_moon.light_angular_distance = lerpf(0.5, 3.0, ov)
			_moon.light_volumetric_fog_energy = 0.4
		_moon.sky_mode = DirectionalLight3D.SKY_MODE_LIGHT_ONLY if ov > 0.5 else DirectionalLight3D.SKY_MODE_LIGHT_AND_SKY
	if _env:
		var amb_night := Color(0.18, 0.21, 0.34)
		# daylight ambient stays near neutral: the blue sky already comes in through GI and reflections
		var amb_day := Color(0.60, 0.63, 0.68).lerp(day_hor, 0.25).lerp(Color(0.82, 0.84, 0.88), snow_cover * 0.2)
		_env.ambient_light_color = amb_night.lerp(amb_day, daylight)
		_env.ambient_light_energy = lerpf(float(preset.get("ambient_energy", 0.6)), lerpf(0.55, 0.95, ov), daylight)
		_env.tonemap_exposure = lerpf(float(preset.get("exposure", 1.1)), float(preset.get("day_exposure", 0.85)), daylight)
		_env.fog_light_color = _c("fog_color", Color(0.07, 0.08, 0.13)).lerp(day_hor * 0.95, daylight)
		_env.fog_density = float(preset.get("fog_density", 0.004))
		_env.fog_sky_affect = lerpf(1.0, 0.6, daylight)
		_env.volumetric_fog_density = float(preset.get("volumetric_density", 0.018))
		_env.volumetric_fog_albedo = Color(0.75, 0.78, 0.85).lerp(Color(0.95, 0.9, 0.82), daylight * (1.0 - ov * 0.6))
		# snow haze and fog glow a little on their own at night (the town's light scattered in them)
		_env.volumetric_fog_emission = _c("fog_emission", Color(0.02, 0.025, 0.04)).lerp(day_hor * 0.12, daylight * ov)
		_env.glow_hdr_threshold = lerpf(1.3, 2.2, daylight)
		_env.adjustment_saturation = lerpf(1.15, 1.0, daylight)
		# the procedural sky is bright next to a 20-degree sun: less of it bounced into the shade by day
		_env.sdfgi_energy = lerpf(1.2, 0.55, daylight)
		_env.ssil_intensity = lerpf(1.5, 0.8, daylight)
		# day: the sky's own light for ambient and reflections reads truer than a flat colour
		_env.ambient_light_sky_contribution = lerpf(0.0, 0.6, daylight)
	_scale_flames(lerpf(1.0, 0.04, daylight))
	for nm in _sys:
		var pm := ((_sys[nm] as GPUParticles3D).draw_pass_1 as QuadMesh).material as StandardMaterial3D
		pm.emission_energy_multiplier = lerpf(0.45 if nm != "splash" else 0.25, 0.0, daylight)
	if _probe and absf(daylight - _probe_daylight) > 0.15:
		_probe_daylight = daylight
		_probe.update_mode = ReflectionProbe.UPDATE_ALWAYS
		_probe_reset = 3


## Daylight dims the flame lights (street lanterns, candles, braziers). Interiors are left alone.
func _scale_flames(k: float) -> void:
	if absf(k - _light_scale) < 0.005 and k == 1.0:
		return
	var changed_scale := absf(k - _light_scale) >= 0.005
	_light_scale = k
	var world := get_world_3d()
	for l in get_tree().get_nodes_in_group("flame_lights"):
		var ol := l as OmniLight3D
		if ol == null or not ol.is_inside_tree() or ol.get_world_3d() != world or ol.global_position.y < INTERIOR_Y:
			continue
		var flicker := "amount" in ol and "_base" in ol
		if not ol.has_meta("weather_base"):
			if k == 1.0:
				continue
			ol.set_meta("weather_base", float(ol.get("_base")) if flicker else ol.light_energy)
		elif not changed_scale:
			continue
		var base := float(ol.get_meta("weather_base"))
		if flicker:
			ol.set("_base", base * k)
		elif ol.visible:
			ol.light_energy = base * k


# ------------------------------------------------------------------ precipitation

func _soft_dot(ring := false) -> GradientTexture2D:
	var g := Gradient.new()
	if ring:
		g.offsets = PackedFloat32Array([0.0, 0.55, 0.78, 1.0])
		g.colors = PackedColorArray([Color(1, 1, 1, 0), Color(1, 1, 1, 0.0), Color(1, 1, 1, 0.9), Color(1, 1, 1, 0)])
	else:
		g.offsets = PackedFloat32Array([0.0, 0.35, 1.0])
		g.colors = PackedColorArray([Color(1, 1, 1, 1), Color(1, 1, 1, 0.75), Color(1, 1, 1, 0)])
	var t := GradientTexture2D.new()
	t.gradient = g
	t.width = 32
	t.height = 32
	t.fill = GradientTexture2D.FILL_RADIAL
	t.fill_from = Vector2(0.5, 0.5)
	t.fill_to = Vector2(1.0, 0.5)
	return t


func _streak_tex() -> GradientTexture2D:
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.3, 0.8, 1.0])
	g.colors = PackedColorArray([Color(1, 1, 1, 0), Color(1, 1, 1, 1), Color(1, 1, 1, 0.8), Color(1, 1, 1, 0)])
	var t := GradientTexture2D.new()
	t.gradient = g
	t.width = 8
	t.height = 64
	t.fill_from = Vector2(0.5, 0.0)
	t.fill_to = Vector2(0.5, 1.0)
	return t


func _fade_ramp(peak := 1.0) -> GradientTexture1D:
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.1, 0.85, 1.0])
	g.colors = PackedColorArray([Color(1, 1, 1, 0), Color(1, 1, 1, peak), Color(1, 1, 1, peak), Color(1, 1, 1, 0)])
	var t := GradientTexture1D.new()
	t.gradient = g
	return t


func _particle_mat(tex: Texture2D, billboard: bool) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.shading_mode = BaseMaterial3D.SHADING_MODE_PER_VERTEX
	m.vertex_color_use_as_albedo = true
	m.albedo_texture = tex
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES if billboard else BaseMaterial3D.BILLBOARD_DISABLED
	m.distance_fade_mode = BaseMaterial3D.DISTANCE_FADE_PIXEL_ALPHA
	m.distance_fade_min_distance = 0.15
	m.distance_fade_max_distance = 1.2
	m.disable_receive_shadows = true
	# a little self-light: at night the flakes and drops pick up the town's glow even away from a lantern
	m.emission_enabled = true
	m.emission = Color(0.62, 0.66, 0.76)
	m.emission_energy_multiplier = 0.4
	return m


func _build_particles() -> void:
	for nm in ["flakes_near", "flakes_far", "streaks_near", "streaks_far", "splash"]:
		var p := GPUParticles3D.new()
		p.name = "Precip_" + nm
		p.local_coords = false
		p.emitting = false
		p.visible = false
		p.amount = 16
		p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		p.visibility_aabb = AABB(Vector3(-45, -30, -45), Vector3(90, 50, 90))
		p.process_material = ParticleProcessMaterial.new()
		var q := QuadMesh.new()
		if nm.begins_with("flakes"):
			q.material = _particle_mat(_soft_dot(), true)
		elif nm.begins_with("streaks"):
			q.material = _particle_mat(_streak_tex(), false)
			p.transform_align = GPUParticles3D.TRANSFORM_ALIGN_Z_BILLBOARD_Y_TO_VELOCITY
		else:
			q.orientation = PlaneMesh.FACE_Y
			q.material = _particle_mat(_soft_dot(true), false)
		p.draw_pass_1 = q
		add_child(p)
		_sys[nm] = p


func _configure_particles() -> void:
	var pr: Dictionary = preset.get("precip", {})
	var k := precip_scale
	var fall := float(pr.get("fall", 1.0))
	var sfall := float(pr.get("streak_fall", 6.0))
	var turb := float(pr.get("turbulence", 0.5))
	var w3 := Vector3(wind.x, 0.0, wind.y)
	_counts = {
		"flakes_near": int(float(pr.get("flakes", 0)) * k), "flakes_far": int(float(pr.get("far_flakes", 0)) * k),
		"streaks_near": int(float(pr.get("streaks", 0)) * k), "streaks_far": int(float(pr.get("far_streaks", 0)) * k),
		"splash": int(float(pr.get("splash", 0)) * k),
	}
	for nm in _sys:
		var p: GPUParticles3D = _sys[nm]
		var n: int = _counts[nm]
		var pm := p.process_material as ParticleProcessMaterial
		var q := p.draw_pass_1 as QuadMesh
		var mat := q.material as StandardMaterial3D
		var far: bool = nm.ends_with("_far")
		var height := 16.0 if far else 9.0
		if nm.begins_with("flakes"):
			var sz := float(pr.get("flake_size", 0.04))
			q.size = Vector2(sz, sz) * (1.4 if far else 1.0)
			var v := Vector3(0, -fall, 0) + w3
			pm.direction = v.normalized()
			pm.spread = 12.0
			pm.initial_velocity_min = v.length() * 0.8
			pm.initial_velocity_max = v.length() * 1.2
			pm.gravity = Vector3.ZERO
			pm.turbulence_enabled = turb > 0.0
			pm.turbulence_noise_strength = turb
			pm.turbulence_noise_scale = 4.0
			pm.turbulence_influence_min = 0.05
			pm.turbulence_influence_max = 0.14
			pm.scale_min = 0.6
			pm.scale_max = 1.5
			pm.color = Color(0.95, 0.96, 1.0, 1.0)
			pm.color_ramp = _fade_ramp(0.95)
			p.lifetime = height / maxf(fall, 0.2)
		elif nm.begins_with("streaks"):
			var ln := float(pr.get("streak_len", 0.5))
			q.size = Vector2(0.01 if ln > 0.45 else 0.02, ln) * (1.3 if far else 1.0)
			var v := Vector3(0, -sfall, 0) + w3
			pm.direction = v.normalized()
			pm.spread = 3.0
			pm.initial_velocity_min = v.length() * 0.9
			pm.initial_velocity_max = v.length() * 1.1
			pm.gravity = Vector3.ZERO
			pm.turbulence_enabled = false
			pm.scale_min = 0.8
			pm.scale_max = 1.2
			pm.color = _col(pr.get("streak_color", [0.75, 0.8, 0.9, 0.35]))
			pm.color_ramp = _fade_ramp(1.0)
			p.lifetime = height / maxf(v.length(), 0.5)
		else:
			q.size = Vector2(0.28, 0.28)
			pm.direction = Vector3.UP
			pm.spread = 0.0
			pm.initial_velocity_min = 0.0
			pm.initial_velocity_max = 0.0
			pm.gravity = Vector3.ZERO
			pm.scale_min = 0.5
			pm.scale_max = 1.2
			var sc := Curve.new()
			sc.add_point(Vector2(0, 0.25))
			sc.add_point(Vector2(1, 1.0))
			var ct := CurveTexture.new()
			ct.curve = sc
			pm.scale_curve = ct
			pm.color = Color(0.8, 0.84, 0.92, 0.5)
			pm.color_ramp = _fade_ramp(1.0)
			p.lifetime = 0.35
			height = 0.0
		pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_RING if far else ParticleProcessMaterial.EMISSION_SHAPE_BOX
		if far:
			pm.emission_ring_axis = Vector3.UP
			pm.emission_ring_radius = 30.0
			pm.emission_ring_inner_radius = 7.0
			pm.emission_ring_height = height
		elif nm == "splash":
			pm.emission_box_extents = Vector3(12, 0.01, 12)
		else:
			pm.emission_box_extents = Vector3(7, height * 0.5, 7)
		mat.distance_fade_max_distance = 3.0 if far else (2.5 if nm.begins_with("streaks") else 1.2)
		if n > 0:
			p.preprocess = minf(p.lifetime, 8.0)
			if p.amount != n:
				p.amount = n
			p.restart()
		p.set_meta("height", height)
	_update_emitters()
	_follow()


func _col(v: Variant) -> Color:
	if v is Array and (v as Array).size() >= 3:
		return Color(float(v[0]), float(v[1]), float(v[2]), float(v[3]) if (v as Array).size() > 3 else 1.0)
	return Color.WHITE


func _update_emitters() -> void:
	for nm in _sys:
		var p: GPUParticles3D = _sys[nm]
		var on: bool = int(_counts.get(nm, 0)) > 0 and not _indoors
		if on and _under_cover and (nm.ends_with("_near") or nm == "splash"):
			on = false
		p.emitting = on
		p.visible = on


func particle_count() -> int:
	var n := 0
	for nm in _sys:
		var p: GPUParticles3D = _sys[nm]
		if p.emitting:
			n += p.amount
	return n


func _player() -> Node3D:
	return get_tree().get_first_node_in_group("player") as Node3D


## The camera, or for a high camera (overhead) the point it looks at a little above the ground.
func _follow_point() -> Vector3:
	var cam := get_viewport().get_camera_3d()
	var pl := _player()
	var ground := pl.global_position.y if pl else 0.0
	if cam == null:
		return pl.global_position + Vector3(0, 1.7, 0) if pl else Vector3.ZERO
	var p := cam.global_position
	if p.y - ground > 20.0:
		var d := -cam.global_transform.basis.z
		var t := (p.y - (ground + 6.0)) / maxf(-d.y, 0.25)
		p += d * t
	return p


func _follow() -> void:
	if _sys.is_empty():
		return
	var c := _follow_point()
	# a jump (door, teleport, camera cut): refill the volume where the camera now is instead of waiting for it
	var jumped := c.distance_to(_last_follow) > 15.0
	_last_follow = c
	var pl := _player()
	var ground := pl.global_position.y if pl and absf(pl.global_position.y - c.y) < 20.0 else c.y - 1.7
	var w3 := Vector3(wind.x, 0.0, wind.y)
	for nm in _sys:
		var p: GPUParticles3D = _sys[nm]
		if not p.emitting:
			continue
		if nm == "splash":
			p.global_position = Vector3(c.x, ground + 0.03, c.z)
			continue
		var h := float(p.get_meta("height", 12.0))
		# emit upwind so the drifting volume is centred on the camera halfway through its fall
		var lead := w3 * p.lifetime * 0.5
		p.global_position = Vector3(c.x, ground + h * 0.5 + 0.5, c.z) - lead
		if jumped:
			p.restart()


func _check_cover() -> void:
	var cam := get_viewport().get_camera_3d()
	var pl := _player()
	var probe: Vector3
	var exclude: Array[RID] = []
	if pl and (cam == null or pl.is_ancestor_of(cam)):
		probe = pl.global_position + Vector3(0, 1.7, 0)
		if pl is CollisionObject3D:
			exclude.append((pl as CollisionObject3D).get_rid())
	elif cam:
		probe = cam.global_position
	else:
		return
	var indoors := probe.y < INTERIOR_Y
	var covered := false
	if not indoors and kind in ["snow", "blizzard", "sleet", "rain"]:
		var q := PhysicsRayQueryParameters3D.create(probe, probe + Vector3(0, 14, 0))
		q.exclude = exclude
		covered = not get_world_3d().direct_space_state.intersect_ray(q).is_empty()
	if indoors != _indoors or covered != _under_cover:
		_indoors = indoors
		_under_cover = covered
		_state["under_cover"] = covered
		_update_emitters()
		_state["particles"] = particle_count()


# ------------------------------------------------------------------ smoke and captures

class _Runner extends Node3D:
	var shot_dir := ""

	func _ready() -> void:
		process_mode = Node.PROCESS_MODE_ALWAYS
		if shot_dir != "":
			await _shots()
		else:
			await _smoke()
		queue_free()

	func _frames(n: int) -> void:
		for i in n:
			await get_tree().process_frame

	func _line() -> void:
		var s := Weather.current()
		print("[smoke] weather preset=%s snow_cover=%.2f wetness=%.2f particles=%d daylight=%.2f" % [
			s.get("preset", "-"), float(s.get("snow_cover", 0.0)), float(s.get("wetness", 0.0)),
			int(s.get("particles", 0)), float(s.get("daylight", 0.0))])

	## Applies `c` and holds it for `n` frames on one district. When the smoke swaps nights mid-way (a new district
	## comes up with its own default), the conditions are re-applied on the new one and the count restarts.
	func _hold(c: Variant, n: int) -> void:
		for attempt in 5:
			var w := Weather.instance()
			var waited := 0
			while w == null and waited < 600:
				await get_tree().process_frame
				waited += 1
				w = Weather.instance()
			if w == null:
				return
			Weather.set_conditions(c)
			var ok := true
			for i in n:
				await get_tree().process_frame
				if Weather.instance() != w:
					ok = false
					break
			if ok:
				return

	func _smoke() -> void:
		await _frames(20)
		var c := Assets.weather_counts()
		print("[smoke] weather materials snow_swapped=%d wet=%d ground_overlay=%d" % [c["snow"], c["wet"], c["ground"]])
		for p in Weather.SMOKE_PRESETS:
			await _hold(p, 60)
			_line()
		Weather.set_conditions(str(Weather.data().get("default", "clear_frost")))

	func _shots() -> void:
		DirAccess.make_dir_recursive_absolute(shot_dir)
		await _frames(120)
		var cam := Camera3D.new()
		cam.far = 400.0
		add_child(cam)
		var views := [["door", Vector3(30, 2.2, -8), Vector3(31, 1.4, -15)], ["overhead", Vector3(0, 70, 45), Vector3.ZERO]]
		var runs: Array = []
		for p in ["clear_frost", "light_snow", "blizzard", "sleet", "rain_thaw", "fog", "overcast", "clear_day", "snow_day"]:
			runs.append([p, p, views])
		var roofs := ["roofs", Vector3(-6, 16, 10), Vector3(-6, 9, -32)]
		runs.append(["rain_thaw_cover100", {"preset": "rain_thaw", "snow_cover": 1.0, "snow_rate": 0.0, "wetness": 0.6},
				views + [roofs]])
		runs.append(["rain_thaw_cover30", {"preset": "rain_thaw", "snow_cover": 0.3, "snow_rate": 0.0, "wetness": 1.0},
				views + [roofs]])
		runs.append(["clear_frost_cover50", {"preset": "clear_frost", "snow_cover": 0.5, "wetness": 0.3}, views + [roofs]])
		for r in runs:
			for v in r[2]:
				cam.look_at_from_position(v[1], v[2])
				cam.current = true
				await _hold(r[1], 24)
				if not cam.current:          # a new night's player camera took over during the hold
					cam.current = true
					await _frames(4)
				var path: String = shot_dir.path_join("%s_%s.png" % [r[0], v[0]])
				get_viewport().get_texture().get_image().save_png(path)
			_line()
		print("[smoke] weather shots in ", shot_dir)
		cam.current = false
		Weather.set_conditions(str(Weather.data().get("default", "clear_frost")))
