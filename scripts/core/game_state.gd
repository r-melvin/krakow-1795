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
const DEFAULT_SETTINGS := {"master_volume": 1.0, "mouse_sens": 1.0, "invert_y": false, "fullscreen": false, "vsync": true, "gi": true}

enum Phase { SPLASH, MENU, ORIGIN_SELECT, DAY, NIGHT, DAWN }

var phase: Phase = Phase.SPLASH
var day: int = 1
var crackdown: int = 10          ## 0..100. Austrian pressure on the city.
var origin_id: String = ""
var gender: String = "m"      ## "m" or "f": picks figure_<origin> or figure_<origin>_f
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
	for id in factions:
		factions[id]["influence"] = 0
		factions[id]["loyalty"] = 50
	set_phase(Phase.ORIGIN_SELECT)


func to_menu() -> void:
	set_phase(Phase.MENU)


func choose_origin(id: String, sex: String = "m") -> void:
	origin_id = id
	gender = sex
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
	if DisplayServer.get_name() != "headless":
		var want_full: bool = settings["fullscreen"]
		var mode := DisplayServer.window_get_mode()
		var is_full := mode == DisplayServer.WINDOW_MODE_FULLSCREEN or mode == DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN
		if want_full != is_full:
			DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN if want_full else DisplayServer.WINDOW_MODE_WINDOWED)
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if settings["vsync"] else DisplayServer.VSYNC_DISABLED)
	settings_changed.emit()


func has_save() -> bool:
	return FileAccess.file_exists(SAVE_PATH)


## Written at every dawn: enough to resume the campaign at the next day.
func save_game() -> void:
	var infl := {}
	for fid in factions:
		infl[fid] = get_influence(fid)
	var data := {"day": day, "origin": origin_id, "gender": gender, "influence": infl, "crackdown": crackdown, "coins": coins}
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
	origin = origins[origin_id]
	for fid in factions:
		factions[fid]["influence"] = 0
		factions[fid]["loyalty"] = 50
	var infl: Dictionary = d.get("influence", {})
	for fid in infl:
		set_influence(fid, int(infl[fid]))
	set_phase(Phase.DAY)
	return true
