extends RefCounted
## The Whisper Network (data/rumours.json; docs/GDD.md "Campaign"). Owned by scripts/mission/campaign.gd.
##
## A rumour is carried by named townsfolk of data/npcs.json. Its state lives in GameState.campaign["rumours"]
## (saved with the game):
##   {id: {carriers: [npc ids], planted: bool, channel, heard: bool, status: "whisper"|"talk"|"common"|"disproved",
##         took: bool (effects applied), traced: bool, day: first day in play, truth: bool (resolved at seeding)}}
## Dawn (`night_step`): every carrier passes the rumour to each neighbour on the `network` with probability
##   spread x (1 + channel boost) x (1 - crackdown/200); reach = carriers / roster. At reach >= threshold the
##   rumour takes hold and its `effects` apply once. False rumours that took hold can be disproved; planted ones
##   can be traced back to the player.
## Night (`night_hints`): each rumour in play but unheard becomes an intel.gd hint spoken by its carriers present
##   in the square (overheard like any other hint); `poll_heard` moves overheard ones into the journal.
## The player's view is Mission.journal["rumours"] (truth "unknown" until proven) plus "rumour: ..." Log lines.

const DATA := "res://data/rumours.json"
const HINT_PREFIX := "rumour_"

var db: Dictionary = {}
var campaign: Node                ## campaign.gd (conditions and effects)
var _roster: Array = []
var _links: Dictionary = {}       ## npc id -> [npc ids]


func _init(c: Node = null) -> void:
	campaign = c
	var f := FileAccess.open(DATA, FileAccess.READ)
	if f:
		var d: Variant = JSON.parse_string(f.get_as_text())
		if d is Dictionary:
			db = d
	var net: Dictionary = db.get("network", {})
	for g in net:
		for a in net[g]:
			if not a in _roster:
				_roster.append(a)
			if not _links.has(a):
				_links[a] = []
			for b in net[g]:
				if b != a and not b in _links[a]:
					_links[a].append(b)


func defs() -> Dictionary:
	return db.get("rumours", {})


func def(id: String) -> Dictionary:
	return defs().get(id, {})


func st() -> Dictionary:
	if not GameState.campaign.has("rumours") or not (GameState.campaign["rumours"] is Dictionary):
		GameState.campaign["rumours"] = {}
	return GameState.campaign["rumours"]


func state_of(id: String) -> Dictionary:
	return st().get(id, {})


func roster_size() -> int:
	return maxi(_roster.size(), 1)


func threshold() -> int:
	return int(db.get("threshold", 35))


func in_play(id: String) -> bool:
	var s := state_of(id)
	return not s.is_empty() and str(s.get("status", "")) != "disproved"


func reach(id: String) -> int:
	return int(round(100.0 * (state_of(id).get("carriers", []) as Array).size() / roster_size()))


func took_hold(id: String) -> bool:
	return bool(state_of(id).get("took", false))


func heard(id: String) -> bool:
	return bool(state_of(id).get("heard", false))


## Taken hold, or planted by the player and still alive.
func active(id: String) -> bool:
	return in_play(id) and (took_hold(id) or bool(state_of(id).get("planted", false)))


func truth_of(id: String) -> bool:
	var t: Variant = def(id).get("truth", true)
	if t is bool:
		return t
	return campaign != null and campaign.cond(str(t))


func group_members(groups: Array) -> Array:
	var out: Array = []
	var net: Dictionary = db.get("network", {})
	for g in groups:
		for a in net.get(str(g), []):
			if not a in out:
				out.append(a)
	return out


## Put rumour `id` into circulation, carried by the members of `groups` (network group names) plus `extra`
## random carriers. Returns true if it was new.
func seed_rumour(id: String, groups: Array = [], planted := false, channel := "", extra := 0) -> bool:
	if def(id).is_empty():
		return false
	var s: Dictionary = st().get(id, {})
	var fresh := s.is_empty()
	if fresh:
		s = {"carriers": [], "planted": planted, "channel": channel, "heard": planted, "status": "whisper",
				"took": false, "traced": false, "day": GameState.day, "truth": truth_of(id)}
	elif planted:
		s["planted"] = true
		s["channel"] = channel
		s["truth"] = truth_of(id)
		if str(s.get("status", "")) == "disproved":
			s["status"] = "whisper"
	var gs: Array = groups if not groups.is_empty() else def(id).get("seed", [])
	var cs: Array = s["carriers"]
	for a in group_members(gs):
		if not a in cs:
			cs.append(a)
	var rng := _rng(id, 7)
	for i in extra:
		var a: String = _roster[rng.randi() % _roster.size()]
		if not a in cs:
			cs.append(a)
	s["carriers"] = cs
	st()[id] = s
	_status(id)
	if planted:
		hear(id, "planted by you")
	return fresh


func _status(id: String) -> void:
	var s: Dictionary = st()[id]
	if str(s.get("status", "")) == "disproved":
		return
	var r := reach(id)
	s["status"] = "common" if r >= 60 else ("talk" if r >= threshold() else "whisper")


func _rng(id: String, salt: int) -> RandomNumberGenerator:
	var rng := RandomNumberGenerator.new()
	rng.seed = hash("%s|%d|%d|%s" % [id, GameState.day, salt, GameState.origin_id])
	return rng


## The player learns rumour `id` (overheard, told, planted). Journal entry and a Log line. True the first time.
func hear(id: String, where: String = "") -> bool:
	var d := def(id)
	if d.is_empty():
		return false
	if not st().has(id):
		seed_rumour(id)
	var s: Dictionary = st()[id]
	var first := not bool(s.get("journal", false))
	s["heard"] = true
	s["journal"] = true
	sync_journal(id, where)
	if first:
		_log("rumour: " + str(d.get("text", id)) + ("  (%s)" % where if where != "" else ""))
		if campaign:
			campaign.note_heard(id)
	return first


func sync_journal(id: String, where: String = "") -> void:
	var s := state_of(id)
	if not bool(s.get("journal", false)):
		return
	var d := def(id)
	var jr: Dictionary = Mission.journal.get("rumours", {})
	var e: Dictionary = jr.get(id, {})
	var truth := "unknown"
	if str(s.get("status", "")) == "disproved":
		truth = "false"
	elif bool(s.get("proven", false)) or bool(s.get("planted", false)):
		truth = "true" if bool(s.get("truth", true)) else "false"
	e["subject"] = str(d.get("subject", id))
	e["text"] = str(d.get("text", ""))
	e["gloss"] = str((d.get("line", ["", ""]) as Array)[1]) if (d.get("line", []) as Array).size() > 1 else ""
	e["line"] = str((d.get("line", [""]) as Array)[0]) if (d.get("line", []) as Array).size() > 0 else ""
	e["truth"] = truth
	e["reach"] = reach(id)
	e["status"] = str(s.get("status", "whisper"))
	e["planted"] = bool(s.get("planted", false))
	e["person"] = str(d.get("person", ""))
	if not e.has("night"):
		e["night"] = GameState.day
		e["where"] = where
	if d.has("historical"):
		e["historical"] = str(d["historical"])
	jr[id] = e
	Mission.journal["rumours"] = jr


func _log(text: String) -> void:
	var lines: Array = Mission.journal["log"]
	var t := GameState.time_string() if GameState.phase == GameState.Phase.NIGHT else "day"
	lines.append({"night": GameState.day, "t": t, "text": text, "kind": "intel"})
	while lines.size() > 200:
		lines.pop_front()


## The rumours the player has heard or planted, loudest first.
func known() -> Array:
	var out: Array = []
	for id in st():
		if bool(st()[id].get("journal", false)):
			out.append(id)
	out.sort_custom(func(a, b) -> bool: return reach(a) > reach(b))
	return out


## Unheard rumours in play, loudest first.
func loudest_unheard() -> Array:
	var out: Array = []
	for id in st():
		if not heard(id) and in_play(id):
			out.append(id)
	out.sort_custom(func(a, b) -> bool: return reach(a) > reach(b))
	return out


func plantable() -> Array:
	var out: Array = []
	for id in defs():
		if bool(defs()[id].get("plantable", false)) and not active(id):
			out.append(id)
	return out


# ------------------------------------------------------------------ dawn

## One night of spreading, taking hold, disproof and tracing. Appends dawn report lines to `lines`.
func night_step(lines: Array) -> void:
	var ck := float(GameState.crackdown)
	var channels: Dictionary = campaign.db.get("channels", {}) if campaign else {}
	for id in st().keys():
		var s: Dictionary = st()[id]
		if str(s.get("status", "")) == "disproved":
			continue
		var d := def(id)
		var ch: Dictionary = channels.get(str(s.get("channel", "")), {})
		var p := float(d.get("spread", 0.3)) * (1.0 + float(ch.get("boost", 0.0))) * (1.0 - ck / 200.0)
		var rng := _rng(id, 1)
		var before := reach(id)
		var cs: Array = s["carriers"]
		var add: Array = []
		var ks: Dictionary = db.get("kind_spread", {}).get(str(d.get("kind", "")), {})
		for a in cs:
			for b in _links.get(a, []):
				if not b in cs and not b in add and rng.randf() < p * _kind_mult(ks, str(b)):
					add.append(b)
		cs.append_array(add)
		s["carriers"] = cs
		_status(id)
		var r := reach(id)
		if bool(s.get("journal", false)) and r >= threshold() and before < threshold():
			lines.append("Whispers: \"%s\" is now in every mouth (reach %d%%)." % [d.get("subject", id), r])
		# taking hold
		if not bool(s.get("took", false)) and r >= threshold():
			s["took"] = true
			var eff: Dictionary = d.get("effects", {})
			if not eff.is_empty() and campaign:
				campaign.apply_effects(eff, lines, "rumour")
		# disproof of a false rumour that took hold
		if bool(s.get("took", false)) and not bool(s.get("truth", true)):
			var mult := float(ch.get("disprove_mult", 1.0))
			if rng.randf() < float(d.get("disprove", 0.3)) * mult * float(r) / 100.0:
				s["status"] = "disproved"
				if campaign:
					campaign.apply_effects(d.get("disproved", {"text": "\"%s\" was proved false." % d.get("subject", id)}), lines, "rumour")
					if bool(s.get("planted", false)) and ch.has("faction"):
						GameState.add_influence(str(ch["faction"]), -5)
						lines.append("Your %s lied, and it is known: %s influence -5." % [ch.get("name", "rumour"), GameState.factions.get(ch["faction"], {}).get("name", ch["faction"])])
		# tracing a planted rumour back to the player
		if bool(s.get("planted", false)) and not bool(s.get("traced", false)):
			var tp := float(ch.get("trace", 0.15)) * (1.0 + ck / 100.0) * float(r) / 100.0
			if str(s.get("status", "")) == "disproved":
				tp *= 2.0
			if rng.randf() < tp:
				s["traced"] = true
				if str(d.get("kind", "")) == "miracle" and campaign:
					campaign.apply_effects(db.get("blasphemy", {}), lines, "rumour")
				GameState.add_notoriety(12.0)
				GameState.crackdown = clampi(GameState.crackdown + 3, 0, 100)
				lines.append("The Polizei traced \"%s\" to %s, and from there to you. Notoriety +12, crackdown +3." % [d.get("subject", id), ch.get("name", "its source")])
		sync_journal(id)


## Spread multiplier of a superstition kind for carrier `b` (the best of the groups b belongs to).
func _kind_mult(ks: Dictionary, b: String) -> float:
	if ks.is_empty():
		return 1.0
	var best := 0.0
	var net: Dictionary = db.get("network", {})
	for g in net:
		if b in net[g]:
			best = maxf(best, float(ks.get(g, 1.0)))
	return best if best > 0.0 else 1.0


func is_superstition(id: String) -> bool:
	return str(def(id).get("kind", "")) != ""


## Flags set tonight by other systems (the madam's gossip, the ballad sheet) that mean a rumour was heard.
func from_flags(flags: Dictionary) -> void:
	var fs: Dictionary = db.get("flag_sources", {})
	for f in fs:
		if flags.has(f) and bool(flags[f]):
			hear(str(fs[f]), "street talk")


# ------------------------------------------------------------------ night

## intel.gd hints for tonight: every unheard rumour in play, spoken by its carriers (solo: no partner needed).
func night_hints() -> Array:
	var out: Array = []
	for id in st():
		var s: Dictionary = st()[id]
		if heard(id) or not in_play(id):
			continue
		var d := def(id)
		var line: Array = d.get("line", [str(d.get("text", "")), ""])
		out.append({"id": HINT_PREFIX + id, "speakers": (s.get("carriers", []) as Array).duplicate(), "solo": true,
				"text": str(line[0]), "gloss": str(line[1]) if line.size() > 1 else "",
				"note": "Rumour: " + str(d.get("text", "")), "about": "", "tab": "log"})
	return out


## Rumour hints the intel store says were overheard; marks them heard. Returns the ids newly heard.
func poll_heard(intel_hints: Dictionary) -> Array:
	var out: Array = []
	for hid in intel_hints:
		var h := str(hid)
		if not h.begins_with(HINT_PREFIX):
			continue
		var id := h.trim_prefix(HINT_PREFIX)
		if not heard(id) and def(id).size() > 0:
			hear(id, "overheard at %s" % str(intel_hints[hid].get("where", "?")))
			out.append(id)
	return out
