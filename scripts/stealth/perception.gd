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
		break
	return clampf(level, float(tg("light.min", 0.15)), float(tg("light.max", 1.0)))


## Godot 4's omni falloff: distance^-decay, windowed smoothly to zero at the range.
static func omni_attenuation(d: float, rng: float, decay: float) -> float:
	var win := clampf(1.0 - pow(d / maxf(rng, 0.001), 4.0), 0.0, 1.0)
	return pow(maxf(d, 0.5), -decay) * win * win


static func surface_at(node: Node3D, pos: Vector3, exclude: Array = []) -> String:
	if pos.y < float(tg("light.interior_below_y", -50.0)):
		return "planks"
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
		return best
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
				return str(n.get_meta("surface"))
			n = n.get_parent()
	return "cobbles"


static func surface_noise(s: String) -> float:
	return float(tg("surfaces." + s, 1.0))
