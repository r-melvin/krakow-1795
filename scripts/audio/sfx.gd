extends Node
class_name Sfx
## Sound library (docs/AUDIO.md). One instance lives under main.gd; everything else uses the static API:
##   Sfx.play(name, pos, volume_db := 0.0, pitch_var := -1.0, pitch := 1.0) -> AudioStreamPlayer3D (null if culled)
##   Sfx.play2d(name, volume_db := 0.0, bus := "")     non-positional one-shot (ambience layers)
##   Sfx.ui(name)                                     UI bus, keeps playing while the game is paused
##   Sfx.attach_loop(node, name, volume_db, radius)   a looping 3D source that rides on `node` (caller owns it)
##   Sfx.watch_hooks(watch), Sfx.say_hook(node, key), Sfx.act_hook(node, clip)   glue (data/audio.json tables)
## `name` is an event of data/audio.json "events" (set, volume, radius, unit, pitch variance, priority, extra layers,
## max seconds, bus), else a set of assets/audio/manifest.json (a random variant, never the same one twice running),
## else a single file name.
## Voices: a pool of AudioStreamPlayer3D (voices.max). When all are busy the oldest voice of lower or equal priority
## is stolen, else the new sound is dropped. A sound farther than its radius from the listener is never started.
## Occlusion: a ray from the listener (the current Camera3D) to the source when it starts, refreshed every
## occlusion.update_secs for long voices and loops: blocked -> lowpass + volume drop.
## Buses SFX, Ambience, UI and the reverb buses of the Area3D zones (ambience.gd) are created under Master (whose
## volume GameState.apply_settings() sets); a hard limiter guards Master.
## Also attaches footsteps (scripts/audio/footsteps.gd) to guards and the player once a second, and wires UI sounds
## (UiTheme.wire_sound) into every node added to the tree.

const MANIFEST := "res://assets/audio/manifest.json"
const DATA := "res://data/audio.json"
const ZONE_LAYER := 1 << 19          ## physics layer of the reverb-zone Area3Ds; every 3D player's area_mask

static var _inst: Sfx
static var _sounds: Dictionary = {}  ## file name -> manifest entry
static var _sets: Dictionary = {}    ## set name -> manifest set
static var _data: Dictionary = {}
static var _streams: Dictionary = {}
static var _last_pick: Dictionary = {}
static var _bad: Dictionary = {}     ## file names that failed to load

var voices_peak := 0
var played: Dictionary = {}          ## event / set name -> times started
var dropped := 0
var culled := 0
var _pool: Array[AudioStreamPlayer3D] = []
var _ui_pool: Array[AudioStreamPlayer] = []
var _flat_pool: Array[AudioStreamPlayer] = []
var _loops: Array[AudioStreamPlayer3D] = []
var _occ_t := 0.0
var _scan_t := 0.0
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	name = "Sfx"
	_inst = self
	process_mode = Node.PROCESS_MODE_ALWAYS
	_rng.seed = 1795
	_load()
	_make_buses()
	var v: Dictionary = _data.get("voices", {})
	for i in int(v.get("max", 32)):
		var p := AudioStreamPlayer3D.new()
		p.process_mode = Node.PROCESS_MODE_PAUSABLE
		p.area_mask = ZONE_LAYER
		p.doppler_tracking = AudioStreamPlayer3D.DOPPLER_TRACKING_DISABLED
		p.attenuation_filter_db = float(_data.get("occlusion", {}).get("air_filter_db", -10.0))
		add_child(p)
		_pool.append(p)
	for i in int(v.get("ui", 6)):
		var u := AudioStreamPlayer.new()
		u.bus = "UI"
		u.process_mode = Node.PROCESS_MODE_ALWAYS
		add_child(u)
		_ui_pool.append(u)
	for i in int(v.get("flat", 6)):
		var f := AudioStreamPlayer.new()
		f.bus = "Ambience"
		f.process_mode = Node.PROCESS_MODE_PAUSABLE
		add_child(f)
		_flat_pool.append(f)
	get_tree().node_added.connect(_on_node_added)


func _exit_tree() -> void:
	if _inst == self:
		_inst = null


# ------------------------------------------------------------------ data

static func _read_json(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_warning("Sfx: cannot open %s (run python3 tools/gen_sfx.py)" % path)
		return {}
	var d: Variant = JSON.parse_string(f.get_as_text())
	return d if d is Dictionary else {}


static func _load() -> void:
	if not _sounds.is_empty():
		return
	var m := _read_json(MANIFEST)
	_sounds = m.get("sounds", {})
	_sets = m.get("sets", {})
	_data = _read_json(DATA)


static func data() -> Dictionary:
	_load()
	return _data


static func file_count() -> int:
	_load()
	return _sounds.size()


## Resolved event parameters for `name` (event table over defaults; a bare set or file name gets the defaults).
static func event(name: String) -> Dictionary:
	_load()
	var ev: Dictionary = (_data.get("defaults", {}) as Dictionary).duplicate()
	for k in ["volume_db", "radius", "unit", "pitch_var", "priority", "bus"]:
		if not ev.has(k):
			ev[k] = {"volume_db": 0.0, "radius": 25.0, "unit": 0.1, "pitch_var": 0.05, "priority": 1, "bus": "SFX"}[k]
	ev["set"] = name
	ev["pitch"] = 1.0
	ev["secs"] = 0.0
	ev["also"] = []
	var evs: Dictionary = _data.get("events", {})
	if evs.has(name):
		ev.merge(evs[name], true)
	return ev


## A file of the set (random, not the last one picked), or the name itself if it is a file; "" if unknown.
static func pick(set_name: String) -> String:
	_load()
	if _sets.has(set_name):
		var files: Array = _sets[set_name]["files"]
		if files.is_empty():
			return ""
		if files.size() == 1:
			return files[0]
		var last: String = _last_pick.get(set_name, "")
		var f: String = files[randi() % files.size()]
		if f == last:
			f = files[(files.find(f) + 1) % files.size()]
		_last_pick[set_name] = f
		return f
	return set_name if _sounds.has(set_name) else ""


static func stream(fname: String) -> AudioStream:
	if _streams.has(fname):
		return _streams[fname]
	if _bad.has(fname) or not _sounds.has(fname):
		return null
	var e: Dictionary = _sounds[fname]
	var path := str(e["file"])
	var s: AudioStream = null
	if ResourceLoader.exists(path):
		s = load(path) as AudioStream
	if s == null and FileAccess.file_exists(path):       # not imported yet: read the raw file
		if path.ends_with(".ogg"):
			s = AudioStreamOggVorbis.load_from_file(path)
		else:
			s = AudioStreamWAV.load_from_file(path)
	if s == null:
		_bad[fname] = true
		push_warning("Sfx: cannot load %s" % path)
		return null
	if bool(e.get("loop", false)):
		if s is AudioStreamWAV:
			var w := s as AudioStreamWAV
			w.loop_mode = AudioStreamWAV.LOOP_FORWARD
			w.loop_begin = 0
			w.loop_end = int(float(e["dur"]) * w.mix_rate) - 1
		elif s is AudioStreamOggVorbis:
			(s as AudioStreamOggVorbis).loop = true
	_streams[fname] = s
	return s


# ------------------------------------------------------------------ buses

func _make_buses() -> void:
	var levels: Dictionary = _data.get("buses", {"SFX": 0.0, "Ambience": 0.0, "UI": 0.0})
	for b in ["SFX", "Ambience", "UI"]:
		var i := _bus(b)
		AudioServer.set_bus_volume_db(i, float(levels.get(b, 0.0)))
	var rbs: Dictionary = _data.get("reverb_buses", {})
	for rb in rbs:
		var i := _bus(rb)
		if AudioServer.get_bus_effect_count(i) == 0:
			var c: Dictionary = rbs[rb]
			var fx := AudioEffectReverb.new()
			fx.room_size = float(c.get("room_size", 0.5))
			fx.damping = float(c.get("damping", 0.5))
			fx.spread = float(c.get("spread", 1.0))
			fx.wet = float(c.get("wet", 0.5))
			fx.dry = 0.0
			fx.predelay_msec = float(c.get("predelay_ms", 20))
			fx.hipass = float(c.get("hipass", 0.0))
			AudioServer.add_bus_effect(i, fx)
	var master := AudioServer.get_bus_index("Master")
	var has_limiter := false
	for k in AudioServer.get_bus_effect_count(master):
		if AudioServer.get_bus_effect(master, k) is AudioEffectHardLimiter:
			has_limiter = true
	if not has_limiter:
		var lim := AudioEffectHardLimiter.new()
		lim.ceiling_db = -0.5
		AudioServer.add_bus_effect(master, lim)


static func _bus(bus_name: String) -> int:
	var i := AudioServer.get_bus_index(bus_name)
	if i < 0:
		AudioServer.add_bus()
		i = AudioServer.bus_count - 1
		AudioServer.set_bus_name(i, bus_name)
		AudioServer.set_bus_send(i, "Master")
	return i


# ------------------------------------------------------------------ static API

static func play(name: String, pos: Vector3, volume_db: float = 0.0, pitch_var: float = -1.0, pitch: float = 1.0) -> AudioStreamPlayer3D:
	if _inst == null or not is_instance_valid(_inst) or not _inst.is_inside_tree():
		return null
	return _inst._play3d(name, pos, volume_db, pitch_var, pitch, false)


static func play2d(name: String, volume_db: float = 0.0, bus: String = "") -> AudioStreamPlayer:
	if _inst == null or not is_instance_valid(_inst):
		return null
	return _inst._play_flat(name, volume_db, bus, false)


static func ui(name: String) -> void:
	if _inst == null or not is_instance_valid(_inst):
		return
	_inst._play_flat(name, 0.0, "UI", true)


## A looping source parented to `node` (freed with it). The caller may change volume_db / pitch_scale / stream_paused.
static func attach_loop(node: Node3D, name: String, volume_db: float = 0.0, radius: float = -1.0, offset := Vector3.ZERO) -> AudioStreamPlayer3D:
	if _inst == null or node == null or not is_instance_valid(node):
		return null
	var ev := event(name)
	var fname := pick(str(ev["set"]))
	var s := stream(fname) if fname != "" else null
	if s == null:
		return null
	var p := AudioStreamPlayer3D.new()
	p.name = "Loop_" + name
	p.stream = s
	p.bus = str(ev["bus"])
	p.area_mask = ZONE_LAYER
	p.max_distance = radius if radius > 0.0 else float(ev["radius"])
	p.unit_size = maxf(0.5, p.max_distance * float(ev["unit"]))
	p.volume_db = float(ev["volume_db"]) + volume_db
	p.attenuation_filter_db = float(_data.get("occlusion", {}).get("air_filter_db", -10.0))
	p.doppler_tracking = AudioStreamPlayer3D.DOPPLER_TRACKING_DISABLED
	p.position = offset
	p.set_meta("base_db", p.volume_db)
	node.add_child(p)
	p.play(randf() * float(_sounds[fname]["dur"]) * 0.9)    # desynchronise identical loops
	_inst._loops.append(p)
	_inst.played[name] = int(_inst.played.get(name, 0)) + 1
	return p


## Sets a loop's level while keeping occlusion (use instead of writing volume_db directly).
static func set_loop_db(p: AudioStreamPlayer3D, db: float) -> void:
	if p and is_instance_valid(p):
		p.set_meta("base_db", db)
		p.volume_db = db + float(p.get_meta("occ_db", 0.0))


static func listener_pos() -> Variant:
	if _inst == null or not is_instance_valid(_inst) or not _inst.is_inside_tree():
		return null
	var cam := _inst.get_viewport().get_camera_3d()
	return cam.global_position if cam else null


# ------------------------------------------------------------------ glue for the game systems

## watch.gd `_ready`: voice every sound event (distractions, fights, the bell) and the lanterns.
static func watch_hooks(w: Node) -> void:
	if _inst == null or w == null:
		return
	if w.has_signal("sound_event") and not w.is_connected("sound_event", _inst._on_watch_sound):
		w.connect("sound_event", _inst._on_watch_sound)
	if w.has_signal("lamp_changed") and not w.is_connected("lamp_changed", _inst._on_lamp):
		w.connect("lamp_changed", _inst._on_lamp)


## street_life.gd say(): the non-verbal sound under a speech bubble (a snore, the drum, a cry).
static func say_hook(node: Variant, key: String) -> void:
	var ev: Variant = (data().get("say", {}) as Dictionary).get(key)
	if ev is String and node is Node3D and is_instance_valid(node):
		play(ev, (node as Node3D).global_position + Vector3(0, 1.5, 0))


## street_life.gd _act(): blows landing, falls, stumbles.
static func act_hook(node: Variant, clip: String) -> void:
	var a: Variant = (data().get("acts", {}) as Dictionary).get(clip)
	if not (a is Array) or not (node is Node3D) or not is_instance_valid(node) or _inst == null:
		return
	var n := node as Node3D
	var ev := str(a[0])
	var delay := float(a[1])
	if delay <= 0.0:
		play(ev, n.global_position + Vector3(0, 1.2, 0))
	else:
		var later := func() -> void:
			if is_instance_valid(n) and n.is_inside_tree():
				play(ev, n.global_position + Vector3(0, 1.2, 0))
		_inst.get_tree().create_timer(delay, false).timeout.connect(later)


func _on_watch_sound(pos: Vector3, loudness: float, kind: String) -> void:
	var map: Dictionary = _data.get("watch_kinds", {})
	if not map.has(kind):
		return
	var m: Variant = map[kind]
	if m == null:
		return
	var ev := ""
	if m is String:
		ev = m
	elif m is Array:
		for pair in m:
			if loudness >= float(pair[1]):
				ev = str(pair[0])
				break
	if ev != "":
		play(ev, pos + Vector3(0, 0.2, 0), clampf(linear_to_db(maxf(loudness, 0.05)) * 0.5, -10.0, 4.0))


func _on_lamp(lamp: Node, lit: bool) -> void:
	if lamp is Node3D and is_instance_valid(lamp):
		var at: Vector3 = lamp.call("head_position") if lamp.has_method("head_position") else (lamp as Node3D).global_position
		play("lamp_relight" if lit else "lamp_douse", at)


func _on_node_added(n: Node) -> void:
	if n is Control:
		UiTheme.wire_sound(n)


# ------------------------------------------------------------------ voices

func _now() -> float:
	return Time.get_ticks_msec() / 1000.0


func _play3d(name: String, pos: Vector3, vol: float, pv: float, pitch: float, force: bool) -> AudioStreamPlayer3D:
	var ev := event(name)
	if str(ev["bus"]) == "UI":
		_play_flat(name, vol, "UI", true)
		return null
	var fname := pick(str(ev["set"]))
	if fname == "":
		return null
	var radius := float(ev["radius"])
	var lpos: Variant = listener_pos()
	if not force and lpos != null and pos.distance_to(lpos) > radius:
		culled += 1
		return null
	var s := stream(fname)
	if s == null:
		return null
	var prio := 9 if force else int(ev["priority"])
	var p := _voice(prio)
	if p == null:
		dropped += 1
		return null
	p.stream = s
	p.bus = str(ev["bus"])
	p.global_position = pos
	p.max_distance = radius
	p.unit_size = maxf(0.5, radius * float(ev["unit"]))
	var pvv := float(ev["pitch_var"]) if pv < 0.0 else pv
	p.pitch_scale = clampf(float(ev["pitch"]) * pitch * (1.0 + _rng.randf_range(-pvv, pvv)), 0.3, 3.0)
	p.set_meta("base_db", float(ev["volume_db"]) + vol)
	_occlude(p, lpos)
	p.play()
	var dur := float(_sounds[fname]["dur"]) / p.pitch_scale
	var secs := float(ev["secs"])
	if secs > 0.0 and secs < dur:
		var tw := p.create_tween()
		tw.tween_interval(secs)
		tw.tween_property(p, "volume_db", -60.0, 0.15)
		tw.tween_callback(p.stop)
		p.set_meta("tween", tw)
		dur = secs + 0.15
	var now := _now()
	p.set_meta("until", now + dur)
	p.set_meta("start", now)
	p.set_meta("prio", prio)
	p.set_meta("long", dur > 1.5)
	played[name] = int(played.get(name, 0)) + 1
	voices_peak = maxi(voices_peak, active_voices())
	for layer in ev["also"]:
		var lname := str(layer[0])
		var delay := float(layer[1]) if layer.size() > 1 else 0.0
		if delay <= 0.0:
			_play3d(lname, pos, vol, -1.0, 1.0, force)
		else:
			get_tree().create_timer(delay, false).timeout.connect(func() -> void: _play3d(lname, pos, vol, -1.0, 1.0, force))
	return p


func _voice(prio: int) -> AudioStreamPlayer3D:
	var now := _now()
	var steal: AudioStreamPlayer3D = null
	var oldest := INF
	for p in _pool:
		if float(p.get_meta("until", 0.0)) <= now:
			_reset(p)
			return p
		var st := float(p.get_meta("start", 0.0))
		if int(p.get_meta("prio", 0)) <= prio and st < oldest:
			oldest = st
			steal = p
	if steal:
		_reset(steal)
	return steal


func _reset(p: AudioStreamPlayer3D) -> void:
	if p.has_meta("tween"):
		var tw: Variant = p.get_meta("tween")
		if tw is Tween and (tw as Tween).is_valid():
			(tw as Tween).kill()
		p.remove_meta("tween")
	p.stop()


func active_voices() -> int:
	var now := _now()
	var n := 0
	for p in _pool:
		if float(p.get_meta("until", 0.0)) > now:
			n += 1
	return n


func _play_flat(name: String, vol: float, bus: String, ui_pool: bool) -> AudioStreamPlayer:
	var ev := event(name)
	var fname := pick(str(ev["set"]))
	var s := stream(fname) if fname != "" else null
	if s == null:
		return null
	var pool := _ui_pool if ui_pool else _flat_pool
	var now := _now()
	var p: AudioStreamPlayer = null
	var oldest := INF
	for q in pool:
		if float(q.get_meta("until", 0.0)) <= now:
			p = q
			break
		if float(q.get_meta("start", 0.0)) < oldest:
			oldest = float(q.get_meta("start", 0.0))
			p = q
	if p == null:
		return null
	p.stop()
	p.stream = s
	p.bus = bus if bus != "" else str(ev["bus"])
	p.volume_db = float(ev["volume_db"]) + vol
	var pvv := float(ev["pitch_var"])
	p.pitch_scale = 1.0 + _rng.randf_range(-pvv, pvv)
	p.play()
	p.set_meta("start", now)
	p.set_meta("until", now + float(_sounds[fname]["dur"]) / p.pitch_scale)
	played[name] = int(played.get(name, 0)) + 1
	return p


## Ray from the listener to the source: a wall in between (hit farther than 1.2 m from the source) muffles it.
func _occlude(p: AudioStreamPlayer3D, lpos: Variant) -> void:
	var oc: Dictionary = _data.get("occlusion", {})
	var blocked := false
	if lpos != null and p.is_inside_tree():
		var src := p.global_position + Vector3(0, 0.3, 0)
		var lp: Vector3 = lpos
		if lp.distance_to(src) > 1.5:
			var q := PhysicsRayQueryParameters3D.create(lp, src)
			q.collision_mask = 1
			var hit := p.get_world_3d().direct_space_state.intersect_ray(q)
			blocked = not hit.is_empty() and (hit["position"] as Vector3).distance_to(src) > 1.2
	var occ_db := float(oc.get("volume_db", -8.0)) if blocked else 0.0
	p.set_meta("occ_db", occ_db)
	p.attenuation_filter_cutoff_hz = float(oc.get("cutoff_hz", 900)) if blocked else float(oc.get("clear_cutoff_hz", 14000))
	p.volume_db = float(p.get_meta("base_db", 0.0)) + occ_db


func _process(delta: float) -> void:
	_occ_t -= delta
	if _occ_t <= 0.0:
		_occ_t = float(_data.get("occlusion", {}).get("update_secs", 0.25))
		var lpos: Variant = listener_pos()
		var now := _now()
		for p in _pool:
			if bool(p.get_meta("long", false)) and float(p.get_meta("until", 0.0)) > now:
				_occlude(p, lpos)
		var keep: Array[AudioStreamPlayer3D] = []
		for p in _loops:
			if is_instance_valid(p) and p.is_inside_tree():
				keep.append(p)
				if p.playing and not p.stream_paused:
					_occlude(p, lpos)
		_loops = keep
	_scan_t -= delta
	if _scan_t <= 0.0:
		_scan_t = 1.0
		for g in ["guards", "player"]:
			for n in get_tree().get_nodes_in_group(g):
				if n is Node3D and not n.has_node("Footsteps"):
					Footsteps.attach(n, "auto")


# ------------------------------------------------------------------ smoke

## Headless smoke: loads every file, forces one of each event (ignoring distance and priority) in front of the
## listener and returns "files=<loaded>/<total> voices_peak=<n> events=<started,...>" (failures listed after).
static func smoke() -> String:
	_load()
	if _inst == null:
		return "files=0 voices_peak=0 events=none (no Sfx node)"
	var ok := 0
	for f in _sounds:
		if stream(f) != null:
			ok += 1
	var lpos: Variant = listener_pos()
	var at: Vector3 = (lpos as Vector3) + Vector3(0, -1.0, -3.0) if lpos != null else Vector3.ZERO
	var started := PackedStringArray()
	var failed := PackedStringArray()
	var names: Array = (_data.get("events", {}) as Dictionary).keys()
	names.sort()
	for n in names:
		var ev := event(n)
		if str(ev["bus"]) == "UI":
			var before := int(_inst.played.get(n, 0))
			ui(n)
			if int(_inst.played.get(n, 0)) > before:
				started.append(n)
			else:
				failed.append(n)
		elif _inst._play3d(n, at, -12.0, 0.0, 1.0, true) != null:
			started.append(n)
		else:
			failed.append(n)
	var s := "files=%d/%d voices_peak=%d events=%s" % [ok, _sounds.size(), _inst.voices_peak, ",".join(started)]
	if not failed.is_empty():
		s += " FAILED=%s" % ",".join(failed)
	return s
