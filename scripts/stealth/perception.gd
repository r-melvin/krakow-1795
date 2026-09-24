extends RefCounted
## Stealth helpers shared by the player, guards, the watch coordinator, hiding spots and distractions.
##  - Tunables from data/stealth.json: `tv(node, "section.key", fallback)` (a sandbox watch in the node's world may
##    override any key, see watch.gd `overrides`).
##  - Light: `light_at(node, pos)` sums the OmniLights in group "flame_lights" with Godot's omni attenuation,
##    ray-tested for occlusion, plus the moon (group "moon_light") when a ray toward it is clear. Clamped.
##  - Surface: `surface_at(node, pos)`: nearest patch in group "surface_patch" (meta surface, surface_radius),
##    else the `surface` meta on the collider under the point (or an ancestor), else "cobbles".
##  - `watch_of(node)`: the watch coordinator in the same World3D (group "watch").

const DATA := "res://data/stealth.json"

static var _data: Dictionary = {}


static func data() -> Dictionary:
	if _data.is_empty():
		var f := FileAccess.open(DATA, FileAccess.READ)
		if f:
			var parsed: Variant = JSON.parse_string(f.get_as_text())
			if parsed is Dictionary:
				_data = parsed
		if _data.is_empty():
			push_warning("Perception: cannot read %s" % DATA)
			_data = {"_missing": true}
	return _data


## Global tunable "section.key" (no overrides).
static func tg(path: String, fallback: Variant = 0.0) -> Variant:
	var parts := path.split(".")
	var d: Variant = data()
	for p in parts:
		if d is Dictionary and (d as Dictionary).has(p):
			d = d[p]
		else:
			return fallback
	if path == "noise.hearing_distance" and (d is float or d is int):
		return float(d) * weather_hearing_mult()        # rain / wind mask distraction sounds too (weather.gd)
	return d


## Tunable for `node`'s world: the watch's overrides first, then data/stealth.json.
static func tv(node: Node, path: String, fallback: Variant = 0.0) -> Variant:
	var w := watch_of(node) if node else null
	if w and (w.overrides as Dictionary).has(path):
		return w.overrides[path]
	return tg(path, fallback)


static func vec(v: Variant, fallback := Vector3.ZERO) -> Vector3:
	if v is Vector3:
		return v
	if v is Array and (v as Array).size() >= 3:
		return Vector3(float(v[0]), float(v[1]), float(v[2]))
	return fallback


static func pick(list: Variant) -> String:
	if list is Array and not (list as Array).is_empty():
		return str(list[randi() % (list as Array).size()])
	return ""


## The watch coordinator living in the same World3D as `node`, or null.
static func watch_of(node: Node) -> Node:
	if node == null or not node.is_inside_tree():
		return null
	var n3 := node as Node3D
	var world: World3D = n3.get_world_3d() if n3 else node.get_viewport().world_3d
	for w in node.get_tree().get_nodes_in_group("watch"):
		if (w as Node3D).get_world_3d() == world:
			return w
	return null


static func same_world(a: Node3D, b: Node3D) -> bool:
	return a != null and b != null and a.get_world_3d() == b.get_world_3d()


## True if nothing (or only `target`) blocks the segment. Character bodies other than `target` are skipped when
## `skip_chars` (hearing, lights), so townsfolk do not muffle a sound.
static func clear_line(space: PhysicsDirectSpaceState3D, from: Vector3, to: Vector3, exclude: Array = [],
		target: Object = null, skip_chars := false) -> bool:
	var ex: Array[RID] = []
	for e in exclude:
		if e is RID:
			ex.append(e)
	for i in 4:
		var q := PhysicsRayQueryParameters3D.create(from, to)
		q.exclude = ex
		var hit := space.intersect_ray(q)
		if hit.is_empty():
			return true
		var c: Object = hit.get("collider")
		if target != null and c == target:
			return true
		if skip_chars and c is CharacterBody3D:
			ex.append(hit["rid"])
			continue
		return false
	return true


## Light level 0..1 at `pos` for stealth (lanterns, candles, braziers, the moon).
static func light_at(node: Node3D, pos: Vector3, exclude: Array = []) -> float:
	var world := node.get_world_3d()
	var space := world.direct_space_state
	var sum := 0.0
	for l in node.get_tree().get_nodes_in_group("flame_lights"):
		var ol := l as OmniLight3D
		if ol == null or not ol.is_inside_tree() or not ol.is_visible_in_tree() or ol.light_energy <= 0.01:
			continue
		var lp := ol.global_position
		var d := lp.distance_to(pos)
		if d >= ol.omni_range or ol.get_world_3d() != world:
			continue
		var c := ol.light_energy * omni_attenuation(d, ol.omni_range, ol.omni_attenuation)
		if c < 0.03:
			continue
		if not clear_line(space, lp, pos, exclude, null, true):
			continue
		sum += c
	var level := sum * float(tg("light.gain", 0.45))
	for m in node.get_tree().get_nodes_in_group("moon_light"):
		var dl := m as DirectionalLight3D
		if dl == null or dl.get_world_3d() != world or not dl.is_visible_in_tree():
			continue
		var to_moon := dl.global_transform.basis.z.normalized()      # the light shines along -Z
		if clear_line(space, pos, pos + to_moon * 60.0, exclude, null, true):
			level += float(tg("light.moon", 0.25))
			level += float(weather_state().get("daylight", 0.0)) * float(tg("light.sun", 0.6))   # the same light is the sun by day
		break
	return clampf(level, float(tg("light.min", 0.15)), float(tg("light.max", 1.0)))


## Godot 4's omni falloff: distance^-decay, windowed smoothly to zero at the range.
static func omni_attenuation(d: float, rng: float, decay: float) -> float:
	var win := clampf(1.0 - pow(d / maxf(rng, 0.001), 4.0), 0.0, 1.0)
	return pow(maxf(d, 0.5), -decay) * win * win


static func surface_at(node: Node3D, pos: Vector3, exclude: Array = []) -> String:
	var indoors := pos.y < float(tg("light.interior_below_y", -50.0))
	var world := node.get_world_3d()
	var best := ""
	var best_r := INF
	for p in node.get_tree().get_nodes_in_group("surface_patch"):
		var pn := p as Node3D
		if pn == null or pn.get_world_3d() != world:
			continue
		var r := float(pn.get_meta("surface_radius", 1.0))
		var d := Vector2(pn.global_position.x - pos.x, pn.global_position.z - pos.z).length()
		if d <= r and r < best_r and absf(pn.global_position.y - pos.y) < 1.5:
			best_r = r
			best = str(pn.get_meta("surface", ""))
	if best != "":
		return weather_surface(best, pos)
	var q := PhysicsRayQueryParameters3D.create(pos + Vector3(0, 0.3, 0), pos - Vector3(0, 1.2, 0))
	var ex: Array[RID] = []
	for e in exclude:
		if e is RID:
			ex.append(e)
	q.exclude = ex
	var hit := world.direct_space_state.intersect_ray(q)
	if not hit.is_empty():
		var n: Node = hit.get("collider") as Node
		while n != null and n != node.get_tree().root:
			if n.has_meta("surface"):
				return weather_surface(str(n.get_meta("surface")), pos)
			n = n.get_parent()
	return "planks" if indoors else weather_surface("cobbles", pos)


static func surface_noise(s: String) -> float:
	if s == "sleet":
		return float(tg("surfaces.sleet", 1.3))     # a crunching crust (weather.gd); stealth.json may tune it
	return float(tg("surfaces." + s, 1.0))


## Outdoor ground under accumulated weather: a sleet crust crunches ("sleet"); deep fresh powder muffles ("snow").
static func weather_surface(s: String, pos: Vector3) -> String:
	if pos.y < float(tg("light.interior_below_y", -50.0)) or s in ["planks", "straw", "mud"]:
		return s
	var w := weather_state()
	if w.is_empty():
		return s
	if float(w.get("crust", 0.0)) > 0.35:
		return "sleet"
	if s != "snow" and float(w.get("fresh", 0.0)) > 0.5 and float(w.get("ground_cover", 0.0)) > 0.6:
		return "snow"
	return s


# ------------------------------------------------------------------ weather (scripts/city/weather.gd)
## Rain and wind mask footsteps (hearing x0.6 in rain / sleet, x0.8 in a blizzard or wind of 5 m/s and up);
## blizzard and fog shorten the far cone (weather_state().visibility, data/weather.json). Clear weather: 1.0.

static var _weather_script: Script


## Weather.current() without a hard dependency (sandboxes and smoke scenes have no weather node: {}).
static func weather_state() -> Dictionary:
	if _weather_script == null:
		_weather_script = load("res://scripts/city/weather.gd")
	return _weather_script.call("current") if _weather_script else {}


static func weather_hearing_mult() -> float:
	var w := weather_state()
	if w.is_empty():
		return 1.0
	var m := 1.0
	var k := str(w.get("kind", ""))
	if k == "rain" or k == "sleet":
		m *= 0.6
	if k == "blizzard" or float(w.get("wind_speed", 0.0)) >= 5.0:
		m *= 0.8
	return m


static func weather_sight_mult() -> float:
	var w := weather_state()
	return clampf(float(w.get("visibility", 1.0)), 0.2, 1.0) if not w.is_empty() else 1.0


## Scales a guard's hearing radius and hooks the sight limit into guard.sight_modifiers (once per guard).
static func weather_apply(g: Node) -> void:
	if g == null or not ("hearing_distance" in g):
		return
	if not g.has_meta("weather_hearing_base"):
		g.set_meta("weather_hearing_base", float(g.get("hearing_distance")))
	g.set("hearing_distance", float(g.get_meta("weather_hearing_base")) * weather_hearing_mult())
	if not g.has_meta("weather_sight_hooked") and "sight_modifiers" in g:
		g.set_meta("weather_sight_hooked", true)
		(g.get("sight_modifiers") as Array).append(weather_sight_modifier)


## guard.sight_modifiers entry: nothing past the weather's far-cone range, a softer falloff inside it; the near
## cone (cone.near_dist) is never cut.
static func weather_sight_modifier(g: Node3D, player: Node3D) -> float:
	var m := weather_sight_mult()
	if m >= 0.999 or g == null or player == null:
		return 1.0
	var d := g.global_position.distance_to(player.global_position)
	if d <= float(tg("cone.near_dist", 5.0)):
		return 1.0
	var far := float(g.get("view_distance")) * m
	if d >= far:
		return 0.0
	return 1.0 - 0.4 * (d / far) * (d / far)
