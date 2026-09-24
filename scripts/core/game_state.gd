extends Node
## Autoload. Holds all persistent campaign state: origin, factions, districts, day counter, crackdown.

signal phase_changed(phase: Phase)
signal influence_changed(faction_id: String, value: int)
signal alarm_raised(source: String)
signal mission_ended(success: bool, summary: String)
signal hour_changed(hour: int)
signal settings_changed

const NIGHT_START_MINUTES := 21 * 60   ## night missions begin at 21:00
const SETTINGS_PATH := "user://settings.json"
const SAVE_PATH := "user://save.json"
const DEFAULT_SETTINGS := {"master_volume": 1.0, "mouse_sens": 1.0, "invert_y": false, "fullscreen": false, "vsync": true, "gi": true, "msaa": true, "taa": true, "ambience": false, "bells": true}

enum Phase { SPLASH, MENU, ORIGIN_SELECT, DAY, NIGHT, DAWN }

var phase: Phase = Phase.SPLASH
var day: int = 1
var crackdown: int = 10          ## 0..100. Austrian pressure on the city.
var origin_id: String = ""
var gender: String = "m"      ## "m" or "f": picks figure_<origin> or figure_<origin>_f
## Whom the character is drawn to: "women", "men", "both" or "unspoken". In 1795 this is a private fact with
## public consequences (a crime under Austrian law, a blackmail lever, a door into some circles and out of others).
var inclination: String = "unspoken"
var origin: Dictionary = {}

var factions: Dictionary = {}    ## id -> {name, strength, fear, agenda, external, influence, loyalty}
var origins: Dictionary = {}
var districts: Dictionary = {}

var coins: int = 12            ## purse in złoty, spent in missions (urchins, bribes). Reset by new_game().
var night_alarm_count: int = 0
var night_objective_done: bool = false

## World clock, in game minutes since midnight of the mission's first day (so 01:30 after midnight is 1530).
## Advances only during the night phase: `clock_scale` game minutes per real second (default 1 s = 1 min).
var clock_minutes: float = NIGHT_START_MINUTES
var clock_scale: float = 1.0

## Player options, persisted in user://settings.json. Keys: master_volume (0..1 linear), mouse_sens (multiplier,
## default 1.0, read by the player controller), invert_y (bool), fullscreen (bool), vsync (bool),
## gi (bool: bounced light, volumetric mist and screen-space GI; costs GPU, applied when a night is built).
var settings: Dictionary = DEFAULT_SETTINGS.duplicate()

## Influence and crackdown at the start of the current night, for the dawn report's deltas.
var night_start_influence: Dictionary = {}
var night_start_crackdown: int = 0
## Campaign (scripts/mission/campaign.gd, data/campaign.json): the arc, the whisper network (rumours), people found,
## levers, day actions and the dawn consequences. Plain JSON-able data so it saves as-is. Reset by new_game().
var campaign: Dictionary = {}
## Mission id the campaign chose for tonight ("" = the default). Mission.start() uses it in place of the default id.
var tonight_mission: String = ""
var night_start_loyalty: Dictionary = {}
var night_start_notoriety: float = 0.0
var last_night_success := false
var last_night_summary := ""


func _ready() -> void:
	factions = _load_json("res://data/factions.json")
	origins = _load_json("res://data/origins.json")
	districts = _load_json("res://data/districts.json")
	for id in factions:
		factions[id]["influence"] = 0
		factions[id]["loyalty"] = 50
	load_settings()
	apply_settings()
	mission_ended.connect(func(ok: bool, text: String) -> void:
		last_night_success = ok
		last_night_summary = text)


func _process(delta: float) -> void:
	if phase != Phase.NIGHT:
		return
	var before := int(clock_minutes) / 60
	clock_minutes += delta * clock_scale
	var after := int(clock_minutes) / 60
	if after != before:
		hour_changed.emit(after % 24)


## "HH:MM" of the world clock (wraps past midnight).
func time_string() -> String:
	return minutes_to_string(clock_minutes)


static func minutes_to_string(m: float) -> String:
	var total := int(m)
	return "%02d:%02d" % [(total / 60) % 24, total % 60]


## Parses "HH:MM" into clock minutes on the night timeline: hours before noon count as after midnight (+24 h).
static func parse_clock(s: String) -> float:
	var parts := s.split(":")
	var h := int(parts[0])
	var m := int(parts[1]) if parts.size() > 1 else 0
	if h < 12:
		h += 24
	return float(h * 60 + m)


func _load_json(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_error("Cannot open %s" % path)
		return {}
	var parsed = JSON.parse_string(f.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("Bad JSON in %s" % path)
		return {}
	return parsed


func new_game() -> void:
	## Reset campaign state and go to origin selection.
	day = 1
	crackdown = 10
	coins = 12
	origin_id = ""
	origin = {}
	campaign = {}
	tonight_mission = ""
	for id in factions:
		factions[id]["influence"] = 0
		factions[id]["loyalty"] = 50
	set_phase(Phase.ORIGIN_SELECT)


func to_menu() -> void:
	set_phase(Phase.MENU)


func choose_origin(id: String, sex: String = "m", incl: String = "unspoken") -> void:
	origin_id = id
	gender = sex
	inclination = incl
	origin = origins[id]
	for fid in origin["influence"]:
		set_influence(fid, int(origin["influence"][fid]))
	set_phase(Phase.DAY)


func set_phase(p: Phase) -> void:
	phase = p
	if p == Phase.DAWN:
		save_game()
	phase_changed.emit(p)


func get_influence(fid: String) -> int:
	return int(factions.get(fid, {}).get("influence", 0))


func set_influence(fid: String, value: int) -> void:
	if not factions.has(fid):
		return
	factions[fid]["influence"] = clampi(value, 0, 100)
	influence_changed.emit(fid, factions[fid]["influence"])


func add_influence(fid: String, delta: int) -> void:
	set_influence(fid, get_influence(fid) + delta)


## Loyalty (0..100): how far a faction leans to the movement rather than to the occupiers (50 = on the fence).
func get_loyalty(fid: String) -> int:
	return int(factions.get(fid, {}).get("loyalty", 50))


func add_loyalty(fid: String, delta: int) -> void:
	if factions.has(fid):
		factions[fid]["loyalty"] = clampi(get_loyalty(fid) + delta, 0, 100)


## Fear (0..100): how much a faction fears Austria (data/factions.json seeds it).
func add_fear(fid: String, delta: int) -> void:
	if factions.has(fid):
		factions[fid]["fear"] = clampi(int(factions[fid].get("fear", 0)) + delta, 0, 100)


## Notoriety lives in the intel store (scripts/stealth/intel.gd, Mission.journal["intel"]); read/write it by day too.
func notoriety() -> float:
	var j: Dictionary = get_node("/root/Mission").journal if has_node("/root/Mission") else {}
	return float(j.get("intel", {}).get("notoriety", 0.0))


func add_notoriety(delta: float) -> void:
	if not has_node("/root/Mission"):
		return
	var j: Dictionary = get_node("/root/Mission").journal
	if not j.has("intel") or not (j["intel"] is Dictionary):
		j["intel"] = load("res://scripts/stealth/intel.gd").default_store()
	j["intel"]["notoriety"] = clampf(float(j["intel"].get("notoriety", 0.0)) + delta, 0.0, 100.0)


func figure_name() -> String:
	return figure_name_for(origin_id, gender)


## Model name for any origin and sex, e.g. ("veteran", "f") -> "figure_veteran_f". Used by the origin preview.
func figure_name_for(id: String, sex: String) -> String:
	return "figure_%s%s" % [id, "_f" if sex == "f" else ""]


func skill(name: String) -> int:
	return int(origin.get("skills", {}).get(name, 0))


## Called by guards when they go to full alarm.
func raise_alarm(source: String) -> void:
	night_alarm_count += 1
	alarm_raised.emit(source)


func begin_night() -> void:
	night_start_influence = {}
	for fid in factions:
		night_start_influence[fid] = get_influence(fid)
	night_start_crackdown = crackdown
	night_start_loyalty = {}
	for fid in factions:
		night_start_loyalty[fid] = get_loyalty(fid)
	night_start_notoriety = notoriety()
	night_alarm_count = 0
	night_objective_done = false
	clock_minutes = NIGHT_START_MINUTES
	set_phase(Phase.NIGHT)


## Called by mission logic (objective reached, or player caught).
func end_night(success: bool) -> void:
	var lines: PackedStringArray = []
	if success:
		lines.append("You reached the safe house before dawn.")
		add_influence("underworld", 5)
		add_influence("street", 3)
		if night_alarm_count == 0:
			lines.append("No alarm was raised. The boatmen are impressed.")
			add_influence("underworld", 5)
		else:
			lines.append("%d alarms were raised. Austrian patrols doubled in the district." % night_alarm_count)
			crackdown += 5 * night_alarm_count
	else:
		lines.append("You were caught by the watch. A bribe and a night in the cells.")
		crackdown += 15
		add_influence("guilds", -5)
		add_influence("magnates", -5)
	crackdown = clampi(crackdown, 0, 100)
	day += 1
	set_phase(Phase.DAWN)
	mission_ended.emit(success, "\n".join(lines))


func controlled_district_count() -> int:
	var n := 0
	for d in districts.values():
		var c: String = d["controller"]
		if factions.has(c) and not factions[c]["external"] and get_influence(c) >= 50:
			n += 1
	return n


# ------------------------------------------------------------------ settings and save

func load_settings() -> void:
	settings = DEFAULT_SETTINGS.duplicate()
	if not FileAccess.file_exists(SETTINGS_PATH):
		return
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(SETTINGS_PATH))
	if typeof(parsed) == TYPE_DICTIONARY:
		for k in DEFAULT_SETTINGS:
			if parsed.has(k):
				settings[k] = type_convert(parsed[k], typeof(DEFAULT_SETTINGS[k]))


func save_settings() -> void:
	var f := FileAccess.open(SETTINGS_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(settings, "  "))


## Set one option, apply it and persist. Emits settings_changed.
func set_setting(key: String, value: Variant) -> void:
	settings[key] = value
	apply_settings()
	save_settings()


func apply_settings() -> void:
	var bus := AudioServer.get_bus_index("Master")
	var vol := clampf(float(settings["master_volume"]), 0.0, 1.0)
	AudioServer.set_bus_volume_db(bus, linear_to_db(maxf(vol, 0.0001)))
	AudioServer.set_bus_mute(bus, vol <= 0.001)
	# Ambient beds (wind, city murmur, tavern and crowd loops) are off by default: they read as a music track.
	# Point sounds stay on the SFX bus. Bells and the hejnał have their own switch (read by ambience.gd).
	var amb := AudioServer.get_bus_index("Ambience")
	if amb >= 0:
		AudioServer.set_bus_mute(amb, not bool(settings.get("ambience", false)))
	if DisplayServer.get_name() != "headless":
		var want_full: bool = settings["fullscreen"]
		var mode := DisplayServer.window_get_mode()
		var is_full := mode == DisplayServer.WINDOW_MODE_FULLSCREEN or mode == DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN
		if want_full != is_full:
			DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if want_full else DisplayServer.WINDOW_MODE_WINDOWED)
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if settings["vsync"] else DisplayServer.VSYNC_DISABLED)
	# Edge quality: 4x multisampling for geometry edges, temporal AA for the specular shimmer on wet cobbles,
	# lantern glass and hair. Both on by default; either can be turned off in Options for weaker GPUs.
	var vp := get_viewport()
	if vp:
		vp.msaa_3d = Viewport.MSAA_4X if bool(settings.get("msaa", true)) else Viewport.MSAA_DISABLED
		vp.use_taa = bool(settings.get("taa", true))
		vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_DISABLED if bool(settings.get("msaa", true)) else Viewport.SCREEN_SPACE_AA_FXAA
		vp.use_debanding = true
		vp.anisotropic_filtering_level = Viewport.ANISOTROPY_16X
	settings_changed.emit()


func has_save() -> bool:
	return FileAccess.file_exists(SAVE_PATH)


## Written at every dawn: enough to resume the campaign at the next day.
func save_game() -> void:
	var infl := {}
	for fid in factions:
		infl[fid] = get_influence(fid)
	var data := {"day": day, "origin": origin_id, "gender": gender, "influence": infl, "crackdown": crackdown, "coins": coins, "inclination": inclination}
	# Campaign (additive): loyalty/fear per faction, district state, the arc and the journal (rumours, people, intel).
	var loy := {}
	var fear := {}
	for fid in factions:
		loy[fid] = get_loyalty(fid)
		fear[fid] = int(factions[fid].get("fear", 0))
	data["loyalty"] = loy
	data["fear"] = fear
	data["districts"] = districts
	data["campaign"] = campaign
	data["tonight"] = tonight_mission
	data["version"] = 2
	if has_node("/root/Mission"):
		data["journal"] = get_node("/root/Mission").journal
		data["flags"] = get_node("/root/Mission").flags
	var f := FileAccess.open(SAVE_PATH, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(data, "  "))


## Loads user://save.json and goes to the day briefing. Returns false if there is no usable save.
func continue_game() -> bool:
	if not has_save():
		return false
	var d = JSON.parse_string(FileAccess.get_file_as_string(SAVE_PATH))
	if typeof(d) != TYPE_DICTIONARY or not origins.has(str(d.get("origin", ""))):
		return false
	day = int(d.get("day", 1))
	crackdown = int(d.get("crackdown", 10))
	coins = int(d.get("coins", 12))
	origin_id = str(d["origin"])
	gender = str(d.get("gender", "m"))
	inclination = str(d.get("inclination", "unspoken"))
	origin = origins[origin_id]
	for fid in factions:
		factions[fid]["influence"] = 0
		factions[fid]["loyalty"] = 50
	var infl: Dictionary = d.get("influence", {})
	for fid in infl:
		set_influence(fid, int(infl[fid]))
	var loy: Dictionary = d.get("loyalty", {})
	for fid in loy:
		if factions.has(fid):
			factions[fid]["loyalty"] = int(loy[fid])
	var fear: Dictionary = d.get("fear", {})
	for fid in fear:
		if factions.has(fid):
			factions[fid]["fear"] = int(fear[fid])
	if d.get("districts") is Dictionary and not (d["districts"] as Dictionary).is_empty():
		districts = d["districts"]
	campaign = d.get("campaign", {}) if d.get("campaign") is Dictionary else {}
	tonight_mission = str(d.get("tonight", ""))
	if has_node("/root/Mission") and d.get("journal") is Dictionary:
		var mj: Dictionary = get_node("/root/Mission").journal
		var sj: Dictionary = d["journal"]
		for k in sj:
			mj[k] = sj[k]
	if has_node("/root/Mission") and int(d.get("version", 1)) >= 2 and d.get("flags") is Dictionary:
		get_node("/root/Mission").flags = d["flags"]
	set_phase(Phase.DAY)
	return true


## Period gating. `req` may hold: gender ("m"/"f"), not_gender, inclination (a String or Array of allowed values;
## "unspoken" never satisfies an explicit requirement), origin / not_origin (ids or Arrays), min_influence
## ({faction: value}), min_coins. Returns true when every present key is satisfied. Content authors use it on
## dialogue choices, doors and roles: a woman is not let into the guild hall, a man is not taken for a nun, a
## man who wants men can be blackmailed and can also enter certain rooms a straight man cannot.
func option_allowed(req: Dictionary) -> bool:
	if req.is_empty():
		return true
	if req.has("gender") and gender != str(req["gender"]):
		return false
	if req.has("not_gender") and gender == str(req["not_gender"]):
		return false
	if req.has("inclination"):
		var want = req["inclination"]
		var ok := false
		if want is Array:
			ok = inclination in want or ("both" in want and inclination == "both")
		else:
			ok = inclination == str(want)
		if inclination == "both" and (want is Array and ("women" in want or "men" in want) or str(want) in ["women", "men"]):
			ok = true
		if not ok:
			return false
	if req.has("origin"):
		var o = req["origin"]
		if (o is Array and origin_id not in o) or (not (o is Array) and origin_id != str(o)):
			return false
	if req.has("not_origin"):
		var no = req["not_origin"]
		if (no is Array and origin_id in no) or (not (no is Array) and origin_id == str(no)):
			return false
	if req.has("min_influence"):
		for fid in req["min_influence"]:
			if get_influence(str(fid)) < int(req["min_influence"][fid]):
				return false
	if req.has("min_coins") and coins < int(req["min_coins"]):
		return false
	return true


## Why an option is closed, for a greyed choice: short period phrasing.
func option_reason(req: Dictionary) -> String:
	if req.has("gender") and gender != str(req["gender"]):
		return "Not for a woman here." if gender == "f" else "Not for a man here."
	if req.has("not_gender") and gender == str(req["not_gender"]):
		return "Not for a woman here." if gender == "f" else "Not for a man here."
	if req.has("inclination"):
		return "Not your inclination."
	if req.has("origin") or req.has("not_origin"):
		return "Not for someone of your station."
	if req.has("min_influence"):
		return "You are not known enough here."
	if req.has("min_coins"):
		return "Not enough coin."
	return ""
