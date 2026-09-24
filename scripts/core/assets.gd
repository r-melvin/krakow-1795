class_name Assets
## Thin loader for Blender-exported glTF. Returns an instanced scene or null if the file is missing.
## glTF export maps Blender (x, y, z) to Godot (x, z, -y): Blender -Y (front) becomes Godot +Z.
## So rot_y=0 faces +Z, PI faces -Z, PI/2 faces +X, -PI/2 faces -X.

static var _cache: Dictionary = {}


static func instance(name: String) -> Node3D:
	var path := "res://assets/models/%s.glb" % name
	if not _cache.has(path):
		_cache[path] = load(path) if ResourceLoader.exists(path) else null
	var ps: PackedScene = _cache[path]
	if ps == null:
		push_warning("Missing asset %s" % path)
		return null
	var inst := ps.instantiate() as Node3D
	if inst and not name.begins_with("int_"):
		_weather_pass(inst)
		_cull_pass(inst, name)
	return inst


## Distance culling by size: small things (props, dressing, vendor wares, weeds) vanish beyond 90 m with a fade,
## people beyond 150 m, mid-size pieces (carts, stalls, gutters, trees) beyond 220 m; buildings, landmarks and
## the ground are never culled. Cuts the primitives and draw calls the far town costs every frame.
const CULL_SMALL := 90.0
const CULL_FIGURE := 150.0
const CULL_MID := 220.0
static func _cull_pass(root: Node3D, name: String) -> void:
	var is_figure := name.begins_with("figure_") or name.begins_with("hist_") or name.begins_with("cast_") \
			or name.begins_with("npc_") or name.begins_with("town_") or name.begins_with("dist_") or name == "watchman"
	var aabb := AABB()
	var meshes: Array = []
	_collect_meshes(root, meshes)
	if meshes.is_empty():
		return
	for m in meshes:
		var mi := m as MeshInstance3D
		var b := mi.get_aabb()
		aabb = b if aabb.size == Vector3.ZERO else aabb.merge(b)
	var size := aabb.get_longest_axis_size()
	var rng := 0.0
	if is_figure:
		rng = CULL_FIGURE
	elif size < 3.0:
		rng = CULL_SMALL
	elif size < 9.0:
		rng = CULL_MID
	else:
		return
	for m in meshes:
		var mi := m as MeshInstance3D
		mi.visibility_range_end = rng
		mi.visibility_range_end_margin = rng * 0.12
		mi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF


static func _collect_meshes(n: Node, out: Array) -> void:
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		_collect_meshes(c, out)


static func place(parent: Node, name: String, pos: Vector3, rot_y: float = 0.0, scale: float = 1.0) -> Node3D:
	var n := instance(name)
	if n == null:
		return null
	n.position = pos
	n.rotation.y = rot_y
	n.scale = Vector3.ONE * scale
	parent.add_child(n)
	return n


## Characters come from the MakeHuman pipeline facing +Z, with an AnimationPlayer holding "idle", "walk", "sentry".
## Returns a pivot whose forward is -Z like every other Node3D, with the figure turned inside it.
## The shared clip set of anim_library.glb is attached as the AnimationLibrary "lib"; clips are retargeted onto
## this model's skeleton the first time they are played (see _retarget) and cached per model.
static func character(name: String) -> Node3D:
	var pivot := Node3D.new()
	pivot.name = name
	var fig := instance(name)
	if fig == null:
		return null
	fig.rotation.y = PI
	pivot.add_child(fig)
	_tune_materials(fig)
	var ap := _find_anim_player(fig)
	if ap:
		for anim_name in ap.get_animation_list():
			ap.get_animation(anim_name).loop_mode = Animation.LOOP_LINEAR
		pivot.set_meta("anim", ap)
		_attach_library(pivot, ap, name)
	return pivot


## Skin gets subsurface scattering and a softer specular; cloth goes fully rough; strands stay alpha-scissor.
static func _tune_materials(n: Node) -> void:
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		for i in mi.get_surface_override_material_count():
			var mat := mi.get_active_material(i)
			if mat is BaseMaterial3D:
				var bm := mat as BaseMaterial3D
				var nm := bm.resource_name.to_lower()
				if "body" in nm:
					bm.subsurf_scatter_enabled = true
					bm.subsurf_scatter_strength = 0.6
					bm.subsurf_scatter_skin_mode = true
					bm.roughness = 0.62
					bm.metallic_specular = 0.45
				elif nm.begins_with("cloth_"):
					bm.roughness = 0.95
					bm.metallic_specular = 0.2
				elif "high-poly" in nm or "low-poly" in nm:
					bm.roughness = 0.05
					bm.metallic_specular = 1.0
					bm.clearcoat_enabled = true
					bm.clearcoat = 1.0
					bm.clearcoat_roughness = 0.04
				elif "eye_shadow" in nm:
					bm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
					bm.cull_mode = BaseMaterial3D.CULL_BACK
	for c in n.get_children():
		_tune_materials(c)


static func _find_anim_player(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var r := _find_anim_player(c)
		if r:
			return r
	return null


# ------------------------------------------------------------------ shared animation library

const LIB_PATH := "res://assets/models/anim_library.glb"
const LIB := "lib"
const BLEND := 0.2

## Clips that loop. Everything else plays once and holds its last frame (falls, deaths, transitions).
const LOOPING := {
	"idle": true, "idle_alert": true, "walk": true, "walk_player": true, "walk_fast": true, "jog": true, "run": true, "walk_carry": true,
	"carry_basket": true, "sneak": true, "crouch_idle": true, "crouch_hide": true, "prone_idle": true, "prone_crawl": true,
	"prone_crawl_side": true, "crouch_crawl": true, "guard_sentry": true, "guard_march": true, "guard_alert_look": true,
	"musket_aim": true, "musket_ready": true, "pistol_aim": true, "block": false, "talk_gesture_a": true, "talk_gesture_b": true,
	"haggle": true, "sit_idle": true, "sweep": true,
}

## Ground speed (m/s) each in-place locomotion clip was authored at (stride / stance time in build_animations.py).
const CLIP_SPEED := {
	"walk": 0.93, "walk_player": 1.27, "walk_fast": 2.18, "jog": 2.57, "run": 4.84, "walk_carry": 0.85, "carry_basket": 0.94,
	"sneak": 1.28, "guard_march": 1.78, "prone_crawl": 0.70, "prone_crawl_side": 0.35, "crouch_crawl": 0.31,
}

## Gameplay state -> clip. Scripts ask Assets.clip_for("prone") instead of hard-coding clip names.
const STATE_CLIP := {
	"idle": "idle", "alert": "idle_alert", "walk": "walk", "walk_fast": "walk_fast", "jog": "jog", "run": "run", "sprint": "run",
	"carry": "walk_carry", "sneak": "sneak", "crouch": "crouch_idle", "hide": "crouch_hide", "prone": "prone_idle",
	"crawl": "prone_crawl", "attack": "attack_swing", "thrust": "attack_thrust", "takedown": "takedown", "hit": "hit_react",
	"hit_back": "hit_react_back", "down": "knocked_down", "dead": "death_fall", "get_up": "get_up", "sentry": "guard_sentry",
	"march": "guard_march", "search": "guard_alert_look", "fight": "musket_ready", "strike": "musket_butt",
	"seize": "guard_seize", "sit": "sit_idle", "talk": "talk_gesture_a", "haggle": "haggle", "sweep": "sweep",
}

## When a model lacks a library clip (no anim_library.glb), fall back to its own baked clips.
const FALLBACK := {
	"walk": "walk", "walk_fast": "walk", "jog": "walk", "run": "walk", "sneak": "walk", "walk_carry": "walk", "carry_basket": "walk",
	"guard_march": "walk", "guard_sentry": "sentry", "prone_crawl": "walk", "crouch_crawl": "walk",
}

static var _lib_loaded := false
static var _lib_anims: Dictionary = {}       ## clip -> Animation in the library skeleton's space
static var _lib_rest: Dictionary = {}        ## bone -> global rest rotation (Quaternion) of the library skeleton
static var _lib_rest_pos: Dictionary = {}    ## bone -> local rest position of the library skeleton
static var _lib_pelvis_h := 1.0
static var _libs: Dictionary = {}            ## model name -> AnimationLibrary (retargeted clips, filled lazily)
static var _smoke := -1
static var _smoke_last := {"player": "-", "guard": "-"}
static var _smoke_seen: Dictionary = {}


static func _load_lib() -> void:
	if _lib_loaded:
		return
	_lib_loaded = true
	if not ResourceLoader.exists(LIB_PATH):
		push_warning("Missing %s: characters keep their own idle/walk clips" % LIB_PATH)
		return
	var ps: PackedScene = load(LIB_PATH)
	var root := ps.instantiate()
	var sks := root.find_children("*", "Skeleton3D", true, false)
	var ap := _find_anim_player(root)
	if sks.is_empty() or ap == null:
		root.free()
		return
	var sk: Skeleton3D = sks[0]
	for i in sk.get_bone_count():
		var bn := sk.get_bone_name(i)
		_lib_rest[bn] = sk.get_bone_global_rest(i).basis.get_rotation_quaternion()
		_lib_rest_pos[bn] = sk.get_bone_rest(i).origin
	var pi := sk.find_bone("pelvis")
	if pi >= 0:
		_lib_pelvis_h = maxf(0.1, sk.get_bone_global_rest(pi).origin.y)
	for n in ap.get_animation_list():
		_lib_anims[n] = ap.get_animation(n)
	root.free()


static func _attach_library(pivot: Node3D, ap: AnimationPlayer, model: String) -> void:
	_load_lib()
	if _lib_anims.is_empty():
		return
	var root := ap.get_node_or_null(ap.root_node)
	var sks := pivot.find_children("*", "Skeleton3D", true, false)
	if root == null or sks.is_empty():
		return
	var sk: Skeleton3D = sks[0]
	if not _libs.has(model):
		_libs[model] = AnimationLibrary.new()
	if not ap.has_animation_library(LIB):
		ap.add_animation_library(LIB, _libs[model])
	pivot.set_meta("anim_skel", sk)
	pivot.set_meta("anim_skel_path", str(root.get_path_to(sk)))


## Library clip -> this skeleton. Each bone keeps the library's rotation as a world-space delta from rest:
## q_target = A * q_lib * B with A = Gt(parent)^-1 * Glib(parent) and B = Glib(bone)^-1 * Gt(bone) (global rests),
## so arms, feet and spines with different rest orientations (female pelvis/thigh angles, MPFB bone rolls) still
## land in the same world pose. Only the pelvis keeps a translation track, scaled by pelvis height.
static func _retarget(clip: String, src: Animation, sk: Skeleton3D, sk_path: String) -> Animation:
	var dst := Animation.new()
	dst.length = src.length
	dst.loop_mode = Animation.LOOP_LINEAR if LOOPING.get(clip, false) else Animation.LOOP_NONE
	var pi := sk.find_bone("pelvis")
	var scale := (sk.get_bone_global_rest(pi).origin.y / _lib_pelvis_h) if pi >= 0 else 1.0
	for t in src.get_track_count():
		var type := src.track_get_type(t)
		if type != Animation.TYPE_ROTATION_3D and type != Animation.TYPE_POSITION_3D:
			continue
		var bone := String(src.track_get_path(t).get_concatenated_subnames())
		var bi := sk.find_bone(bone)
		if bi < 0 or not _lib_rest.has(bone):
			continue
		if type == Animation.TYPE_POSITION_3D and bone != "pelvis":
			continue
		var par := sk.get_bone_parent(bi)
		var a := Quaternion.IDENTITY
		if par >= 0 and _lib_rest.has(sk.get_bone_name(par)):
			a = sk.get_bone_global_rest(par).basis.get_rotation_quaternion().inverse() * (_lib_rest[sk.get_bone_name(par)] as Quaternion)
		var nt := dst.add_track(type)
		dst.track_set_path(nt, NodePath(sk_path + ":" + bone))
		dst.track_set_interpolation_type(nt, src.track_get_interpolation_type(t))
		if type == Animation.TYPE_ROTATION_3D:
			var b: Quaternion = (_lib_rest[bone] as Quaternion).inverse() * sk.get_bone_global_rest(bi).basis.get_rotation_quaternion()
			for k in src.track_get_key_count(t):
				var q: Quaternion = src.track_get_key_value(t, k)
				dst.rotation_track_insert_key(nt, src.track_get_key_time(t, k), (a * q * b).normalized())
		else:
			var rest_t := sk.get_bone_rest(bi).origin
			var rest_l: Vector3 = _lib_rest_pos[bone]
			for k in src.track_get_key_count(t):
				var p: Vector3 = src.track_get_key_value(t, k)
				dst.position_track_insert_key(nt, src.track_get_key_time(t, k), rest_t + a * ((p - rest_l) * scale))
	return dst


## The AnimationPlayer name to play for `clip` on this character ("lib/<clip>", its own clip, a fallback), or "".
static func resolve(pivot: Node3D, clip: String) -> String:
	if pivot == null or not pivot.has_meta("anim"):
		return ""
	var ap: AnimationPlayer = pivot.get_meta("anim")
	var full := LIB + "/" + clip
	if ap.has_animation(full):
		return full
	if _lib_anims.has(clip) and ap.has_animation_library(LIB) and pivot.has_meta("anim_skel"):
		var lib := ap.get_animation_library(LIB)
		if not lib.has_animation(clip):
			lib.add_animation(clip, _retarget(clip, _lib_anims[clip], pivot.get_meta("anim_skel"), pivot.get_meta("anim_skel_path")))
		return full
	if ap.has_animation(clip):
		return clip
	var fb: String = FALLBACK.get(clip, "idle")
	return fb if ap.has_animation(fb) else ""


static func has_clip(pivot: Node3D, clip: String) -> bool:
	return pivot != null and pivot.has_meta("anim") and resolve(pivot, clip).begins_with(LIB + "/")


static func clip_for(state: String) -> String:
	return STATE_CLIP.get(state, state)


## Locomotion / state clip with a cross-fade. Ignored while a one-shot action (play_action) is running.
static func play(pivot: Node3D, clip: String, speed: float = 1.0, blend: float = BLEND) -> void:
	if pivot == null or not pivot.has_meta("anim") or is_action(pivot):
		return
	_play(pivot, clip, speed, blend)


## In-place locomotion clip whose playback rate follows the ground speed, so feet do not skate.
static func play_move(pivot: Node3D, clip: String, ground_speed: float, blend: float = BLEND) -> void:
	var base: float = CLIP_SPEED.get(clip, 1.0)
	play(pivot, clip, clampf(ground_speed / base, 0.55, 1.7), blend)


## One-shot clip (attack, hit, fall...). Locomotion calls are ignored until it ends; `hold` keeps its last frame
## until clear_action() or another action (knocked down, dead). Returns its duration in seconds.
static func play_action(pivot: Node3D, clip: String, speed: float = 1.0, hold: bool = false, blend: float = 0.12) -> float:
	if pivot == null or not pivot.has_meta("anim"):
		return 0.0
	var name := _play(pivot, clip, speed, blend, true)
	if name == "":
		return 0.0
	var ap: AnimationPlayer = pivot.get_meta("anim")
	var dur := ap.get_animation(name).length / maxf(speed, 0.01)
	pivot.set_meta("action_until", INF if hold else Time.get_ticks_msec() / 1000.0 + dur)
	pivot.set_meta("action_clip", clip)
	return dur


static func is_action(pivot: Node3D) -> bool:
	return pivot != null and pivot.has_meta("action_until") and Time.get_ticks_msec() / 1000.0 < float(pivot.get_meta("action_until"))


static func action_clip(pivot: Node3D) -> String:
	return str(pivot.get_meta("action_clip", "")) if is_action(pivot) else ""


static func clear_action(pivot: Node3D) -> void:
	if pivot and pivot.has_meta("action_until"):
		pivot.remove_meta("action_until")


static func _play(pivot: Node3D, clip: String, speed: float, blend: float, restart: bool = false) -> String:
	var ap: AnimationPlayer = pivot.get_meta("anim")
	var name := resolve(pivot, clip)
	if name == "":
		return ""
	if ap.current_animation != name:
		ap.play(name, blend)
	elif restart:
		ap.seek(0.0, true)
	ap.speed_scale = speed
	_smoke_note(pivot, clip)
	return name


## `[smoke] anim player=<clip> guard=<clip>` whenever a new combination shows up in a --smoke run.
static func _smoke_note(pivot: Node3D, clip: String) -> void:
	if _smoke < 0:
		_smoke = 1 if "--smoke" in OS.get_cmdline_user_args() else 0
	if _smoke == 0 or not pivot.has_meta("anim_role"):
		return
	var role := str(pivot.get_meta("anim_role"))
	if _smoke_last.get(role, "") == clip:
		return
	_smoke_last[role] = clip
	var key := "%s|%s" % [_smoke_last["player"], _smoke_last["guard"]]
	if not _smoke_seen.has(key):
		_smoke_seen[key] = true
		print("[smoke] anim player=%s guard=%s" % [_smoke_last["player"], _smoke_last["guard"]])


# ------------------------------------------------------------------ weather material pass (scripts/city/weather.gd)
## Additive, once per imported mesh (the PackedScene cache shares meshes and materials between instances):
##  - any material named "*snow*" (and the icicle "ice") becomes a ShaderMaterial on snow_cover.gdshader that reads
##    the global `snow_cover` and melts away with a noisy, wet rim; textures are copied so cover 1.0 looks as before.
##  - cobble / plaster / wood / tile / stone materials are registered for wetness: darker albedo, lower roughness
##    (a parameter pass on the shared material, so parallax and the imported tuning stay).
##  - the cobble material also gets the wet_surface.gdshader overlay (snow in the joints, puddles) as its next_pass
##    while there is snow or water to show (apply_wetness toggles it).
const SNOW_SHADER := "res://assets/shaders/snow_cover.gdshader"
const WET_SHADER := "res://assets/shaders/wet_surface.gdshader"
const WET_PREFIXES := ["cobble", "plaster", "wood", "oak", "timber", "plank", "tile", "shingle", "stone", "brick", "sandstone", "log", "gravel"]

static var _weather_meshes: Dictionary = {}     ## mesh instance id -> true (already processed)
static var _snow_mats: Dictionary = {}          ## source material -> ShaderMaterial
static var _wet_mats: Dictionary = {}           ## BaseMaterial3D -> [albedo_color, roughness]
static var _ground_mats: Dictionary = {}        ## BaseMaterial3D -> overlay ShaderMaterial
static var _snow_shader: Shader
static var _wet_shader: Shader
static var _wetness := 0.0
static var _overlay_on := false
static var weather_swapped := 0                 ## snow materials swapped (smoke / report)


static func _weather_pass(root: Node) -> void:
	var stack: Array = [root]
	while not stack.is_empty():
		var n: Node = stack.pop_back()
		for c in n.get_children():
			stack.append(c)
		var mi := n as MeshInstance3D
		if mi == null or mi.mesh == null:
			continue
		var mesh := mi.mesh
		for i in mi.get_surface_override_material_count():
			var ov := mi.get_surface_override_material(i)
			if ov:
				var sw := _weather_material(ov)
				if sw != ov:
					mi.set_surface_override_material(i, sw)
		var id := mesh.get_instance_id()
		if _weather_meshes.has(id):
			continue
		_weather_meshes[id] = true
		for i in mesh.get_surface_count():
			var m := mesh.surface_get_material(i)
			if m == null:
				continue
			var sw := _weather_material(m)
			if sw != m:
				mesh.surface_set_material(i, sw)


static func _weather_material(m: Material) -> Material:
	var bm := m as BaseMaterial3D
	if bm == null:
		return m
	var nm := bm.resource_name.to_lower()
	if "snow" in nm or nm == "ice":
		if not _snow_mats.has(bm):
			_snow_mats[bm] = snow_material(bm, 0.12 if nm == "ice" else (0.08 if "~snow" in nm else 0.0))
			weather_swapped += 1
		return _snow_mats[bm]
	for p in WET_PREFIXES:
		if nm.begins_with(p):
			register_wet(bm)
			if p == "cobble":
				register_ground(bm)
			break
	return m


## A snow_cover.gdshader material that renders like `src` at full cover.
static func snow_material(src: BaseMaterial3D, melt_bias := 0.0) -> ShaderMaterial:
	if _snow_shader == null:
		_snow_shader = load(SNOW_SHADER)
	var sm := ShaderMaterial.new()
	sm.resource_name = src.resource_name + "_melt"
	sm.shader = _snow_shader
	sm.set_shader_parameter("albedo", src.albedo_color)
	if src.albedo_texture:
		sm.set_shader_parameter("albedo_tex", src.albedo_texture)
	if src.normal_enabled and src.normal_texture:
		sm.set_shader_parameter("use_normal", true)
		sm.set_shader_parameter("normal_tex", src.normal_texture)
		sm.set_shader_parameter("normal_scale", src.normal_scale)
	if src.roughness_texture:
		sm.set_shader_parameter("rough_tex", src.roughness_texture)
		var ch := [Vector4(1, 0, 0, 0), Vector4(0, 1, 0, 0), Vector4(0, 0, 1, 0), Vector4(0, 0, 0, 1), Vector4(0.33, 0.33, 0.33, 0)]
		sm.set_shader_parameter("rough_channel", ch[clampi(src.roughness_texture_channel, 0, 4)])
	sm.set_shader_parameter("roughness", src.roughness)
	sm.set_shader_parameter("specular", src.metallic_specular)
	sm.set_shader_parameter("uv1_scale", src.uv1_scale)
	sm.set_shader_parameter("uv1_offset", src.uv1_offset)
	sm.set_shader_parameter("melt_bias", melt_bias)
	return sm


## Wetness darkens and glosses `mat` (its imported albedo colour and roughness are kept as the dry values).
static func register_wet(mat: BaseMaterial3D) -> void:
	if mat == null or _wet_mats.has(mat):
		return
	var dry := [mat.albedo_color, mat.roughness]
	for other in _wet_mats:      # a duplicate of a registered (maybe already wet) material keeps the dry values
		if is_instance_valid(other) and other.resource_name == mat.resource_name and other.albedo_texture == mat.albedo_texture:
			dry = (_wet_mats[other] as Array).duplicate()
			break
	_wet_mats[mat] = dry
	if _wetness > 0.0:
		_wet_one(mat, _wetness)


## The cobble overlay (snow in the joints, puddles). Reads the material's own height map if it has one.
static func register_ground(mat: BaseMaterial3D) -> void:
	if mat == null or _ground_mats.has(mat):
		return
	if _wet_shader == null:
		_wet_shader = load(WET_SHADER)
	var sm := ShaderMaterial.new()
	sm.shader = _wet_shader
	sm.render_priority = 1
	var hp := "res://assets/ground/cobbles_height.png"
	var ht: Texture2D = mat.heightmap_texture if mat.heightmap_texture else (load(hp) as Texture2D if ResourceLoader.exists(hp) else null)
	if ht:
		sm.set_shader_parameter("has_height", true)
		sm.set_shader_parameter("height_tex", ht)
	# the base's parallax walk, repeated in the overlay so the snow sits in the relief
	if mat.heightmap_enabled and mat.heightmap_texture:
		sm.set_shader_parameter("use_parallax", true)
		sm.set_shader_parameter("heightmap_scale", mat.heightmap_scale)
		sm.set_shader_parameter("heightmap_min_layers", mat.heightmap_min_layers if mat.heightmap_deep_parallax else 1)
		sm.set_shader_parameter("heightmap_max_layers", mat.heightmap_max_layers if mat.heightmap_deep_parallax else 1)
		sm.set_shader_parameter("heightmap_flip", Vector2(-1.0 if mat.heightmap_flip_tangent else 1.0, -1.0 if mat.heightmap_flip_binormal else 1.0))
	sm.set_shader_parameter("uv1_scale", mat.uv1_scale)
	sm.set_shader_parameter("uv1_offset", mat.uv1_offset)
	_ground_mats[mat] = sm
	register_wet(mat)
	mat.next_pass = sm if _overlay_on else null


static func _wet_one(mat: BaseMaterial3D, w: float) -> void:
	var dry: Array = _wet_mats[mat]
	var c: Color = dry[0]
	var k := lerpf(1.0, 0.7, w)
	mat.albedo_color = Color(c.r * k, c.g * k, c.b * k, c.a)
	mat.roughness = float(dry[1]) * lerpf(1.0, 0.4, w)


## Called by weather.gd when wetness or snow cover change. `overlay`: the cobble overlay is worth drawing.
static func apply_wetness(w: float, overlay: bool) -> void:
	w = clampf(w, 0.0, 1.0)
	for dead in _wet_mats.keys().filter(func(m): return not is_instance_valid(m)):
		_wet_mats.erase(dead)
		_ground_mats.erase(dead)
	if absf(w - _wetness) > 0.004 or (w == 0.0 and _wetness != 0.0):
		_wetness = w
		for mat in _wet_mats:
			if is_instance_valid(mat):
				_wet_one(mat, w)
	if overlay != _overlay_on:
		_overlay_on = overlay
		for mat in _ground_mats:
			if is_instance_valid(mat):
				(mat as BaseMaterial3D).next_pass = _ground_mats[mat] if overlay else null


static func weather_counts() -> Dictionary:
	return {"snow": _snow_mats.size(), "wet": _wet_mats.size(), "ground": _ground_mats.size()}
