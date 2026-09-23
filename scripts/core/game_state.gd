extends Node
## Autoload. Holds all persistent campaign state: origin, factions, districts, day counter, crackdown.

signal phase_changed(phase: Phase)
signal influence_changed(faction_id: String, value: int)
signal alarm_raised(source: String)
signal mission_ended(success: bool, summary: String)
signal hour_changed(hour: int)

const NIGHT_START_MINUTES := 21 * 60   ## night missions begin at 21:00

enum Phase { ORIGIN_SELECT, DAY, NIGHT, DAWN }

var phase: Phase = Phase.ORIGIN_SELECT
var day: int = 1
var crackdown: int = 10          ## 0..100. Austrian pressure on the city.
var origin_id: String = ""
var gender: String = "m"      ## "m" or "f": picks figure_<origin> or figure_<origin>_f
var origin: Dictionary = {}

var factions: Dictionary = {}    ## id -> {name, strength, fear, agenda, external, influence, loyalty}
var origins: Dictionary = {}
var districts: Dictionary = {}

var night_alarm_count: int = 0
var night_objective_done: bool = false

## World clock, in game minutes since midnight of the mission's first day (so 01:30 after midnight is 1530).
## Advances only during the night phase: `clock_scale` game minutes per real second (default 1 s = 1 min).
var clock_minutes: float = NIGHT_START_MINUTES
var clock_scale: float = 1.0


func _ready() -> void:
	factions = _load_json("res://data/factions.json")
	origins = _load_json("res://data/origins.json")
	districts = _load_json("res://data/districts.json")
	for id in factions:
		factions[id]["influence"] = 0
		factions[id]["loyalty"] = 50


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


func choose_origin(id: String, sex: String = "m") -> void:
	origin_id = id
	gender = sex
	origin = origins[id]
	for fid in origin["influence"]:
		set_influence(fid, int(origin["influence"][fid]))
	set_phase(Phase.DAY)


func set_phase(p: Phase) -> void:
	phase = p
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
	return "figure_%s%s" % [origin_id, "_f" if gender == "f" else ""]


func skill(name: String) -> int:
	return int(origin.get("skills", {}).get(name, 0))


## Called by guards when they go to full alarm.
func raise_alarm(source: String) -> void:
	night_alarm_count += 1
	alarm_raised.emit(source)


func begin_night() -> void:
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
