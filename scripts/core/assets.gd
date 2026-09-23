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
	return ps.instantiate() as Node3D


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
	"idle": true, "idle_alert": true, "walk": true, "walk_fast": true, "jog": true, "run": true, "walk_carry": true,
	"carry_basket": true, "sneak": true, "crouch_idle": true, "crouch_hide": true, "prone_idle": true, "prone_crawl": true,
	"prone_crawl_side": true, "crouch_crawl": true, "guard_sentry": true, "guard_march": true, "guard_alert_look": true,
	"musket_aim": true, "musket_ready": true, "pistol_aim": true, "block": false, "talk_gesture_a": true, "talk_gesture_b": true,
	"haggle": true, "sit_idle": true, "sweep": true,
}

## Ground speed (m/s) each in-place locomotion clip was authored at (stride / stance time in build_animations.py).
const CLIP_SPEED := {
	"walk": 1.08, "walk_fast": 1.90, "jog": 2.57, "run": 4.84, "walk_carry": 0.85, "carry_basket": 0.94,
	"sneak": 1.39, "guard_march": 1.78, "prone_crawl": 0.70, "prone_crawl_side": 0.35, "crouch_crawl": 0.31,
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
