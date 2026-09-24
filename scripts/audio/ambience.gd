extends Node
class_name Ambience
## The night's soundscape (docs/AUDIO.md; tables in data/audio.json "ambience", "schedule", "places"). One instance
## lives under main.gd; it wakes whenever a night district exists (group "nav_source") and a camera is current.
## Layers:
##   wind       two 2D beds (calm, strong) crossfaded by the wind strength: GameState "weather" if the game has one
##              (clear / snow / wind / storm), else a slow swing round ambience.wind.base.
##   murmur     the distant city: a 2D bed that swells with the townsfolk walking within 40 m of the listener.
##   crowds     up to four 3D murmur loops parked on knots of people: group "crowd" members, and idle townsfolk
##              standing three or more together.
##   taverns    tavern noise leaking from every door that leads to the tavern set (interiors.gd) and from the
##              brothel door (street_life.gd); inside the tavern set the bed plays in full.
##   random     dogs far off, an owl, a baby crying and a cough from windows, crows, gusts in a strong wind.
##   reverb     Area3D zones on Sfx.ZONE_LAYER with a reverb bus: the Cloth Hall arcade and passage, alleys, and
##              every interior set (the church gets the big room).
##   the clock  St Mary's great bell strikes the hours and the hejnal follows, played four times, once to each
##              quarter (the call breaks off mid-phrase, after the legend of the watchman shot as he sounded it);
##              the Town Hall clock strikes the hours a little late and one stroke on the half hour; the curfew
##              tolls at 22:00 (through watch.ring_bell, so the watch looks to the tower); compline, matins and
##              lauds on the small bells; the Angelus at 06:00 (three sets of three strokes, then a peal); the
##              Uniate chapel's bell; the Wawel Sigismund bell far off on feast days (flag feast_day); before dawn
##              the Kazimierz schulklopfer knocking men up for prayer; a murmur of prayer from the synagogue door on
##              the Sabbath eve. While bells and the hejnal ring, the watch's hearing is masked (watch.mask_sound).

const Perception := preload("res://scripts/stealth/perception.gd")

var wind := 0.3
var walkers_near := 0
var crowd_groups := 0
var sequences: PackedStringArray = []   ## tower / clock sequences run this session (smoke report)

var _wind_calm: AudioStreamPlayer
var _wind_strong: AudioStreamPlayer
var _murmur: AudioStreamPlayer
var _inside_bed: AudioStreamPlayer
var _crowds: Array[AudioStreamPlayer3D] = []
var _world: Node
var _doors: Array[AudioStreamPlayer3D] = []
var _brothel_done := false
var _brothel_tries := 0
var _prayer: AudioStreamPlayer3D
var _zones := 0
var _t := 0.0
var _slow_t := 0.0
var _last_min := -1.0
var _queue: Array = []
var _running := false
var _rand_t: Dictionary = {}
var _schul_t := 0.0
var _rng := RandomNumberGenerator.new()
var _fade := 0.0                        ## 0 = beds silent, 1 = full (night fade in / out)


func _ready() -> void:
	name = "Ambience"
	_rng.seed = 1241
	_wind_calm = _bed("wind_calm_loop")
	_wind_strong = _bed("wind_strong_loop")
	_murmur = _bed("city_murmur_loop")
	_inside_bed = _bed("tavern_loop")


func _bed(set_name: String) -> AudioStreamPlayer:
	var p := AudioStreamPlayer.new()
	p.name = set_name
	p.bus = "Ambience"
	p.volume_db = -80.0
	var f := Sfx.pick(set_name)
	p.stream = Sfx.stream(f) if f != "" else null
	add_child(p)
	return p


static func cfg(section: String) -> Dictionary:
	return Sfx.data().get(section, {})


static func place(key: String) -> Vector3:
	var p: Variant = cfg("places").get(key)
	return Vector3(float(p[0]), float(p[1]), float(p[2])) if p is Array else Vector3.ZERO


func _process(delta: float) -> void:
	_t += delta
	var cam := get_viewport().get_camera_3d()
	var district := _district()
	var night := GameState.phase == GameState.Phase.NIGHT and cam != null and district != null
	_fade = move_toward(_fade, 1.0 if night else 0.0, delta / (2.0 if night else 0.6))
	if not night:
		_apply_beds(null)
		if _world != null:
			_world = null
			_doors.clear()
			_crowds.clear()
			_prayer = null
			_last_min = -1.0
		return
	if district != _world:
		_setup_world(district)
	var lp := cam.global_position
	_slow_t -= delta
	if _slow_t <= 0.0:
		_slow_t = 1.0
		_update_murmur(lp)
		_update_crowds(lp)
		_update_doors(lp)
		_update_prayer()
	_update_wind(delta)
	_apply_beds(lp)
	_clock_tick()
	_random_tick(delta, lp)


## The night district (greybox_district.gd: in group "nav_source", has player_spawn()).
func _district() -> Node:
	if _world != null and is_instance_valid(_world) and _world.is_inside_tree():
		return _world
	for n in get_tree().get_nodes_in_group("nav_source"):
		if n.has_method("player_spawn"):
			return n
	return null


# ------------------------------------------------------------------ beds

func _inside(lp: Variant) -> bool:
	return lp != null and (lp as Vector3).y < float(Perception.tg("light.interior_below_y", -50.0))


func _update_wind(delta: float) -> void:
	var wc: Dictionary = cfg("ambience").get("wind", {})
	var base := float(wc.get("base", 0.3))
	var weather: Variant = GameState.get("weather")
	if weather is String and (wc.get("weather", {}) as Dictionary).has(weather):
		base = float(wc["weather"][weather])
	var target := base + float(wc.get("swing", 0.2)) * sin(TAU * _t / float(wc.get("period", 110.0))) \
			+ 0.08 * sin(_t * 0.37) * sin(_t * 0.11)
	wind = move_toward(wind, clampf(target, 0.0, 1.0), delta * 0.1)


func _apply_beds(lp: Variant) -> void:
	var fade_db := linear_to_db(maxf(_fade, 0.0001))
	var wc: Dictionary = cfg("ambience").get("wind", {})
	var mc: Dictionary = cfg("ambience").get("murmur", {})
	var inside := _inside(lp)
	var in_db := float(wc.get("inside_db", -14.0)) if inside else 0.0
	var calm: Array = wc.get("calm_db", [-16.0, -26.0])
	var strong: Array = wc.get("strong_db", [-44.0, -12.0])
	_set_bed(_wind_calm, lerpf(float(calm[0]), float(calm[1]), wind) + in_db + fade_db)
	_set_bed(_wind_strong, lerpf(float(strong[0]), float(strong[1]), wind) + in_db + fade_db)
	var mdb: Array = mc.get("db", [-34.0, -15.0])
	var k := clampf(float(walkers_near) / float(mc.get("full_at", 16)), 0.0, 1.0)
	_set_bed(_murmur, lerpf(float(mdb[0]), float(mdb[1]), sqrt(k)) + (float(mc.get("inside_db", -12.0)) if inside else 0.0) + fade_db)
	var in_tavern := inside and _room_family(lp).contains("tavern")
	_set_bed(_inside_bed, (float(cfg("ambience").get("tavern", {}).get("inside_db", -3.0)) if in_tavern else -80.0) + fade_db)


func _set_bed(p: AudioStreamPlayer, db: float) -> void:
	if p == null or p.stream == null:
		return
	p.volume_db = move_toward(p.volume_db, maxf(db, -80.0), 1.5)
	var want := p.volume_db > -60.0
	if want and not p.playing:
		p.play(randf() * 5.0)
	elif not want and p.playing:
		p.stop()


func _update_murmur(lp: Vector3) -> void:
	var r := float(cfg("ambience").get("murmur", {}).get("radius", 40.0))
	var n := 0
	for w in get_tree().get_nodes_in_group("npcs"):
		if w is Node3D and (w as Node3D).is_visible_in_tree() and (w as Node3D).global_position.distance_to(lp) < r:
			if not (w.has_method("is_inside") and w.is_inside()):
				n += 1
	walkers_near = n


## Knots of people: "crowd" members (clustered within `cluster` m) and idle townsfolk three or more within
## `idle_cluster` m. The nearest groups get a murmur loop each, louder the bigger the group.
func _update_crowds(lp: Vector3) -> void:
	var cc: Dictionary = cfg("ambience").get("crowd", {})
	var r := float(cc.get("radius", 40.0))
	var pts: Array[Vector3] = []
	for n in get_tree().get_nodes_in_group("crowd"):
		if n is Node3D and (n as Node3D).is_visible_in_tree() and (n as Node3D).global_position.distance_to(lp) < r:
			pts.append((n as Node3D).global_position)
	var clusters := _cluster(pts, float(cc.get("cluster", 5.0)), 2)
	var idle: Array[Vector3] = []
	for n in get_tree().get_nodes_in_group("npcs"):
		if n is Node3D and (n as Node3D).is_visible_in_tree() and not n.is_in_group("crowd") \
				and (n as Node3D).global_position.distance_to(lp) < r and n.has_method("is_moving") and not n.is_moving():
			if not (n.has_method("is_inside") and n.is_inside()):
				idle.append((n as Node3D).global_position)
	clusters.append_array(_cluster(idle, float(cc.get("idle_cluster", 3.0)), int(cc.get("idle_min", 3))))
	clusters.sort_custom(func(a: Array, b: Array) -> bool: return (a[0] as Vector3).distance_to(lp) < (b[0] as Vector3).distance_to(lp))
	crowd_groups = clusters.size()
	var maxp := int(cc.get("max_players", 4))
	while _crowds.size() < maxp and _world != null:
		var p := Sfx.attach_loop(_world as Node3D, "crowd_talk_loop", -80.0, r)
		if p == null:
			break
		p.top_level = true
		_crowds.append(p)
	for i in _crowds.size():
		var p := _crowds[i]
		if not is_instance_valid(p):
			continue
		if i < clusters.size():
			var c: Vector3 = clusters[i][0]
			var cnt: int = clusters[i][1]
			if p.volume_db < -60.0:
				p.global_position = c + Vector3(0, 1.5, 0)
			else:
				p.global_position = p.global_position.lerp(c + Vector3(0, 1.5, 0), 0.5)
			Sfx.set_loop_db(p, (float(cc.get("volume_db", -12.0)) + float(cc.get("per_doubling_db", 3.0)) * log(float(cnt) / 2.0) / log(2.0)) * 1.0 + linear_to_db(maxf(_fade, 0.0001)))
			p.stream_paused = false
		else:
			Sfx.set_loop_db(p, -80.0)
			p.stream_paused = true


## Greedy clustering: [[centroid, count], ...] with at least `min_n` members.
static func _cluster(pts: Array[Vector3], rad: float, min_n: int) -> Array:
	var cs: Array = []      # [sum, count]
	for p in pts:
		var hit := false
		for c in cs:
			if ((c[0] as Vector3) / float(c[1])).distance_to(p) < rad:
				c[0] = (c[0] as Vector3) + p
				c[1] = int(c[1]) + 1
				hit = true
				break
		if not hit:
			cs.append([p, 1])
	var out: Array = []
	for c in cs:
		if int(c[1]) >= min_n:
			out.append([(c[0] as Vector3) / float(c[1]), int(c[1])])
	return out


# ------------------------------------------------------------------ world: zones and doors

func _interiors() -> Node:
	if _world == null:
		return null
	for c in _world.get_children():
		if c.get("_doors") != null and (c.get("_rooms") != null or c.get("_sets") != null):
			return c
	return null


## [[room key, origin, set family], ...] from interiors.gd (`_rooms`: key -> {origin, set, ...}; older builds
## had `_sets`: name -> origin).
func _rooms() -> Array:
	var it := _interiors()
	var out: Array = []
	if it == null:
		return out
	var rooms: Variant = it.get("_rooms")
	if rooms is Dictionary:
		for k in rooms:
			var r: Dictionary = rooms[k]
			out.append([str(k), r.get("origin", Vector3.ZERO), str(r.get("set", k))])
	else:
		var sets: Dictionary = it.get("_sets")
		for k in sets:
			out.append([str(k), sets[k], str(k)])
	return out


## The set family of the room the listener is in ("" outside): interiors.gd `_inside`, else the nearest origin.
func _room_family(lp: Variant) -> String:
	var it := _interiors()
	if it == null or lp == null:
		return ""
	var inside: Variant = it.get("_inside")
	for r in _rooms():
		if (inside is String and inside != "" and r[0] == inside) or (not (inside is String) and (r[1] as Vector3).distance_to(lp) < 30.0):
			return str(r[2])
	return ""


func _setup_world(district: Node) -> void:
	_world = district
	if district.has_meta("ambience_built"):
		return
	district.set_meta("ambience_built", true)
	_doors.clear()
	_crowds.clear()
	_brothel_done = false
	_brothel_tries = 0
	_prayer = null
	_last_min = -1.0
	_zones = 0
	var ac: Dictionary = cfg("ambience")
	for z in ac.get("reverb_zones", []):
		_zone(district as Node3D, str(z["name"]), _v(z["center"]), _v(z["size"]), str(z["bus"]), float(z.get("amount", 0.5)), int(z.get("priority", 1)))
	var it := _interiors()
	if it:
		var ic: Dictionary = ac.get("interior", {})
		var taverns := {}
		for r in _rooms():
			var fam := str(r[2])
			var big := fam.contains("church") or fam.contains("chapel")
			var bus := str(ic.get("church_bus", "Reverb_Church")) if big else str(ic.get("bus", "Reverb_Interior"))
			_zone(district as Node3D, "interior_" + str(r[0]), (r[1] as Vector3) + _v(ic.get("offset", [0, 3, -12])),
					_v(ic.get("size", [26, 9, 30])), bus, float(ic.get("amount", 0.7)), 3)
			if fam.contains("tavern"):
				taverns[r[0]] = true
		for d in it.get("_doors"):
			if d is Area3D and is_instance_valid(d) and not bool(d.get_meta("exit", false)):
				var key := str(d.get_meta("room", d.get_meta("set", "")))
				if taverns.has(key) and (d as Area3D).global_position.y > -50.0:
					_door_source((d as Area3D).global_position, 1.0)


func _door_source(at: Vector3, pitch: float) -> void:
	var tc: Dictionary = cfg("ambience").get("tavern", {})
	if _doors.size() >= int(tc.get("max_doors", 8)):
		return
	var p := Sfx.attach_loop(_world as Node3D, "tavern_loop", float(tc.get("volume_db", -4.0)), float(tc.get("radius", 24.0)))
	if p == null:
		return
	p.top_level = true
	p.global_position = at + Vector3(0, 1.6, 0)
	p.pitch_scale = pitch
	p.attenuation_filter_cutoff_hz = float(tc.get("cutoff_hz", 2200))
	_doors.append(p)


## The brothel door: street_life.gd builds its scenes once the population exists, so look for it for a while.
func _update_doors(_lp: Vector3) -> void:
	if _brothel_done or _brothel_tries > 60:
		return
	_brothel_tries += 1
	var sl := _find_street_life(_world, 3)
	if sl == null:
		return
	var d: Variant = sl.get("D")
	if not (d is Dictionary) or not (d as Dictionary).has("brothel"):
		return
	_brothel_done = true
	var at: Vector3 = sl.call("_door_of", int(d["brothel"].get("portal", 12)))
	_door_source(at, float(cfg("ambience").get("tavern", {}).get("brothel_pitch", 1.06)))


## street_life.gd's node (its actors, not the node, are in group "street_life"): a shallow search of the district.
static func _find_street_life(n: Node, depth: int) -> Node:
	if n == null:
		return null
	for c in n.get_children():
		if c.has_method("_door_of") and c.get("D") != null:
			return c
	if depth > 1:
		for c in n.get_children():
			var f := _find_street_life(c, depth - 1)
			if f:
				return f
	return null


func _zone(parent: Node3D, zname: String, center: Vector3, size: Vector3, bus: String, amount: float, prio: int) -> void:
	var a := Area3D.new()
	a.name = "Reverb_" + zname
	a.collision_layer = Sfx.ZONE_LAYER
	a.collision_mask = 0
	a.monitoring = false
	a.monitorable = true
	a.priority = prio
	a.reverb_bus_enabled = true
	a.reverb_bus_name = bus
	a.reverb_bus_amount = amount
	a.reverb_bus_uniformity = 0.3
	var cs := CollisionShape3D.new()
	var bs := BoxShape3D.new()
	bs.size = size
	cs.shape = bs
	a.add_child(cs)
	parent.add_child(a)
	a.global_position = center
	_zones += 1


static func _v(a: Variant) -> Vector3:
	return Vector3(float(a[0]), float(a[1]), float(a[2])) if a is Array else Vector3.ZERO


# ------------------------------------------------------------------ the clock

func _clock_tick() -> void:
	var m := GameState.clock_minutes
	if _last_min < 0.0 or m < _last_min or m - _last_min > 240.0:
		_last_min = m
		return
	var from := _last_min
	if m <= from:
		return
	_last_min = m
	var sc := cfg("schedule")
	var special := false
	# fixed-time events first (they replace the plain hour strikes at that hour)
	if _crossed(from, m, _at(sc.get("curfew", {}).get("at", "22:00"))):
		_enqueue("curfew", [])
		special = true
	for at in _ats(sc.get("angelus", {}).get("at", [])):
		if _crossed(from, m, at):
			_enqueue("angelus", [])
			special = true
	for c in sc.get("canonical", []):
		if _crossed(from, m, _at(c["at"])):
			_enqueue("canonical", [str(c.get("name", "hours")), int(c.get("strokes", 5))])
	var sig: Dictionary = sc.get("sigismund", {})
	for at in _ats(sig.get("at", [])):
		if _crossed(from, m, at) and _flag(str(sig.get("flag", "feast_day"))):
			_enqueue("sigismund", [])
	for at in _ats(sc.get("uniate", {}).get("at", [])):
		if _crossed(from, m, at):
			_enqueue("uniate", [])
	var h1 := int(floor(m / 60.0))
	if h1 > int(floor(from / 60.0)):
		var hour := h1 % 24
		if not special:
			_enqueue("hour", [hour])
		_enqueue("hejnal", [hour])
		var th: Dictionary = sc.get("town_hall_clock", {})
		if not th.is_empty():
			_delayed_townhall(hour, float(th.get("delay", 14.0)))
	elif int(floor((m - 30.0) / 60.0)) > int(floor((from - 30.0) / 60.0)) and bool(sc.get("town_hall_clock", {}).get("half_hour", true)):
		_strike_now("bell_townhall", place(str(sc["town_hall_clock"].get("place", "town_hall_tower"))), 1, 0.0,
				float(sc["town_hall_clock"].get("mask_secs", 0.0)))
	# the schulklopfer: before dawn, not on the Sabbath
	var sk: Dictionary = sc.get("schulklopfer", {})
	if not sk.is_empty():
		var mm := fposmod(m, 1440.0)
		var dm: Array = sk.get("not_day_mod", [7, 6])
		if mm >= _at(sk.get("from", "05:05")) and mm < _at(sk.get("to", "05:45")) and GameState.day % int(dm[0]) != int(dm[1]):
			_schul_t -= get_process_delta_time()
			if _schul_t <= 0.0:
				var ev: Array = sk.get("every", [7.0, 14.0])
				_schul_t = _rng.randf_range(float(ev[0]), float(ev[1]))
				var spread := float(sk.get("spread", 40.0))
				Sfx.play("schulklopfer", place(str(sk.get("place", "kazimierz"))) + Vector3(_rng.randf_range(-spread, spread), 0, _rng.randf_range(-spread, spread)))
				if not "schulklopfer" in sequences:
					sequences.append("schulklopfer")


static func _at(s: Variant) -> float:
	return GameState.parse_clock(str(s))


static func _ats(v: Variant) -> Array:
	var out: Array = []
	if v is Array:
		for s in v:
			out.append(_at(s))
	elif v is String:
		out.append(_at(v))
	return out


## True if clock minute `at` (0..1440) lies in (from, to] (the clock runs past midnight: 1440 + ...).
static func _crossed(from: float, to: float, at: float) -> bool:
	var d := fposmod(at - from, 1440.0)
	return d > 0.0 and d <= to - from


static func _flag(name: String) -> bool:
	if Mission.has_method("has_flag") and Mission.has_flag(name):
		return true
	var c: Variant = GameState.get("campaign")
	return c is Dictionary and bool((c as Dictionary).get(name, false))


func _delayed_townhall(hour: int, delay: float) -> void:
	var th: Dictionary = cfg("schedule").get("town_hall_clock", {})
	await get_tree().create_timer(delay, false).timeout
	if _world == null:
		return
	var n := hour % 12
	_strike_now(str(th.get("bell", "bell_townhall")), place(str(th.get("place", "town_hall_tower"))), 12 if n == 0 else n,
			float(th.get("gap", 1.8)), float(th.get("mask_secs", 0.0)))


## `count` strokes `gap` s apart; each masks the watch's hearing for `mask_secs` (0 = not at all).
func _strike_now(ev: String, at: Vector3, count: int, gap: float, mask_secs: float) -> void:
	for i in count:
		if _world == null:
			return
		Sfx.play(ev, at)
		if mask_secs > 0.0:
			_mask(mask_secs)
		if i < count - 1:
			await get_tree().create_timer(gap, false).timeout


func _mask(secs: float) -> void:
	for w in get_tree().get_nodes_in_group("watch"):
		if w.has_method("mask_sound") and not bool(w.get("sandbox")):
			w.mask_sound(secs)


func _watch() -> Node:
	for w in get_tree().get_nodes_in_group("watch"):
		if not bool(w.get("sandbox")):
			return w
	return null


func _enqueue(kind: String, args: Array) -> void:
	if _queue.size() >= 4 and kind != "curfew":
		return
	_queue.append([kind, args])
	if not _running:
		_run_queue()


func _run_queue() -> void:
	_running = true
	while not _queue.is_empty():
		var job: Array = _queue.pop_front()
		if _world == null:
			continue
		var kind := str(job[0])
		sequences.append(kind)
		match kind:
			"hour": await _seq_hour(int(job[1][0]))
			"hejnal": await _seq_hejnal(int(job[1][0]))
			"curfew": await _seq_curfew()
			"angelus": await _seq_angelus()
			"canonical": await _seq_canonical(int(job[1][1]))
			"sigismund": await _seq_sigismund()
			"uniate": await _seq_uniate()
		await get_tree().create_timer(1.5, false).timeout
	_running = false


func _wait(secs: float) -> void:
	await get_tree().create_timer(secs, false).timeout


func _seq_hour(hour: int) -> void:
	var c: Dictionary = cfg("schedule").get("hour_strikes", {})
	var n := hour % 12
	await _strike_now(str(c.get("bell", "bell_great")), place(str(c.get("place", "st_marys_belfry"))), 12 if n == 0 else n,
			float(c.get("gap", 2.8)), float(c.get("mask_secs", 1.2)))
	await _wait(2.5)


## The hejnal: with all_directions, to each quarter in turn (the real ceremony); by default one call an hour,
## the quarter turning with the hour (a game hour is a minute of real time). The call facing the listener is louder.
func _seq_hejnal(hour: int) -> void:
	var c: Dictionary = cfg("schedule").get("hejnal", {})
	var tower := place(str(c.get("place", "st_marys_trumpet")))
	await _wait(float(c.get("delay", 3.0)))
	var dur := 20.0
	var f := Sfx.pick("hejnal")
	if f != "":
		dur = float(Sfx._sounds[f]["dur"]) - 3.0
	var dirs: Array = c.get("directions", [[0, 1]])
	if not bool(c.get("all_directions", false)) and not dirs.is_empty():
		dirs = [dirs[hour % dirs.size()]]
	for d in dirs:
		if _world == null:
			return
		var dir := Vector3(float(d[0]), 0.0, float(d[1]))
		var lp: Variant = Sfx.listener_pos()
		var facing := 1.0
		if lp != null:
			var to := (lp as Vector3) - tower
			to.y = 0.0
			facing = dir.dot(to.normalized()) if to.length() > 0.1 else 1.0
		Sfx.play("hejnal", tower + dir * 2.5, lerpf(-9.0, 0.0, (facing + 1.0) * 0.5))
		_mask(minf(float(c.get("mask_secs", 6.0)), dur))
		await _wait(dur + float(c.get("pause", 4.0)))


func _seq_curfew() -> void:
	var c: Dictionary = cfg("schedule").get("curfew", {})
	var at := place(str(c.get("place", "st_marys_belfry")))
	var n := int(c.get("strokes", 12))
	var gap := float(c.get("gap", 5.0))
	var w := _watch()
	if w and w.has_method("ring_bell"):
		w.call("ring_bell", at)          # masks, turns the watch to the tower; Sfx voices its "bell" sound event
		n -= 1
		await _wait(gap)
	await _strike_now(str(c.get("bell", "bell_great")), at, n, gap, float(c.get("mask_secs", 2.5)))
	await _wait(4.0)


func _seq_angelus() -> void:
	var c: Dictionary = cfg("schedule").get("angelus", {})
	var at := place(str(c.get("place", "st_marys_belfry")))
	for s in int(c.get("sets", 3)):
		await _strike_now(str(c.get("bell", "bell_great")), at, int(c.get("strokes", 3)), float(c.get("gap", 3.5)), float(c.get("mask_secs", 2.0)))
		await _wait(float(c.get("set_gap", 7.0)))
	if bool(c.get("peal", true)):
		Sfx.play("bell_peal", at)
		_mask(float(c.get("peal_mask_secs", 8.0)))
		await _wait(15.0)


func _seq_canonical(strokes: int) -> void:
	var c: Dictionary = cfg("schedule").get("canonical_bell", {})
	await _strike_now(str(c.get("bell", "bell_small")), place(str(c.get("place", "st_marys_belfry"))), strokes, float(c.get("gap", 1.6)), float(c.get("mask_secs", 1.0)))
	await _wait(3.0)


func _seq_sigismund() -> void:
	var c: Dictionary = cfg("schedule").get("sigismund", {})
	await _strike_now("bell_sigismund", place(str(c.get("place", "wawel"))), int(c.get("strokes", 6)), float(c.get("gap", 7.0)), 0.0)
	await _wait(6.0)


func _seq_uniate() -> void:
	var c: Dictionary = cfg("schedule").get("uniate", {})
	await _strike_now("bell_uniate", place(str(c.get("place", "uniate_chapel"))), int(c.get("strokes", 7)), float(c.get("gap", 1.3)), 0.0)
	await _wait(2.0)


## A low murmur of prayer from the synagogue door on the Sabbath eve (game day % 7 == 5, or flag sabbath_eve),
## until 22:00.
func _update_prayer() -> void:
	var c: Dictionary = cfg("schedule").get("sabbath_prayer", {})
	if c.is_empty() or _world == null:
		return
	var dm: Array = c.get("day_mod", [7, 5])
	var on := (GameState.day % int(dm[0]) == int(dm[1]) or _flag(str(c.get("flag", "sabbath_eve")))) \
			and fposmod(GameState.clock_minutes, 1440.0) >= 12 * 60 and fposmod(GameState.clock_minutes, 1440.0) < _at(c.get("until", "22:00"))
	if on and _prayer == null:
		_prayer = Sfx.attach_loop(_world as Node3D, "prayer_murmur_loop", float(c.get("volume_db", -10.0)), float(c.get("radius", 400.0)))
		if _prayer:
			_prayer.top_level = true
			_prayer.global_position = place(str(c.get("place", "synagogue_door")))
			_prayer.unit_size = 20.0
			if not "sabbath_prayer" in sequences:
				sequences.append("sabbath_prayer")
	elif not on and _prayer != null:
		if is_instance_valid(_prayer):
			_prayer.queue_free()
		_prayer = null


# ------------------------------------------------------------------ random distant life

func _random_tick(delta: float, lp: Vector3) -> void:
	if _inside(lp):
		return
	for e in cfg("ambience").get("random", []):
		var ev := str(e["event"])
		var every: Array = e.get("every", [60, 120])
		if not _rand_t.has(ev):
			_rand_t[ev] = _rng.randf_range(float(every[0]) * 0.3, float(every[1]))
		_rand_t[ev] = float(_rand_t[ev]) - delta
		if _rand_t[ev] > 0.0:
			continue
		_rand_t[ev] = _rng.randf_range(float(every[0]), float(every[1]))
		if wind < float(e.get("min_wind", 0.0)):
			continue
		var a := _rng.randf() * TAU
		var dist := 0.0
		var y := 0.0
		match str(e.get("where", "far")):
			"far":
				dist = _rng.randf_range(60.0, 110.0)
				y = 6.0
			"roof":
				dist = _rng.randf_range(15.0, 40.0)
				y = 13.0
			"window":
				dist = _rng.randf_range(8.0, 22.0)
				y = _rng.randf_range(4.5, 9.0)
			_:
				dist = _rng.randf_range(4.0, 12.0)
				y = 2.0
		Sfx.play(ev, Vector3(lp.x + cos(a) * dist, y, lp.z + sin(a) * dist))


## One line for the smoke log.
func report() -> String:
	return "wind=%.2f walkers_near=%d crowd_groups=%d crowd_players=%d tavern_doors=%d reverb_zones=%d sequences=%s" % [
		wind, walkers_near, crowd_groups, _crowds.size(), _doors.size(), _zones, ",".join(sequences)]
