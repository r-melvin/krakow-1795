extends Node
## The campaign (data/campaign.json; docs/GDD.md "Campaign" and "Failure, capture and succession").
## A child of the Mission autoload (Mission.campaign). All state lives in GameState.campaign (saved at dawn):
##   night: next arc night (1..7) · results: [{night, mission, success, approach}] · flags: campaign facts ·
##   tonight: facts for the coming night only · levers: {id: {name, text, from}} · people: {id: {found, met}} ·
##   lead: person to bring into tonight · day: {day, left, done, feed, urchin} · dawn: consequence lines ·
##   events: [{night, id, outcome, text}] · grievance/contact/amends per faction · captures, trial, succession ·
##   leader: the current figurehead's name · ended/ending.
## The whisper network is scripts/mission/rumours.gd (`rumours`). The night side is mission_runner.gd, which asks
## `night_setup()` for tonight's modifiers and `night_people()` for the persons to place, and the day side is
## scripts/ui/day_panel.gd (actions, leads, planting, urchins, trial, heir) and dawn_panel.gd (`dawn` lines).

signal changed

const RumoursScript := preload("res://scripts/mission/rumours.gd")
const DATA := "res://data/campaign.json"
const LOCAL := ["church", "salon", "underworld", "street", "guilds", "magnates"]

var db: Dictionary = {}
var rumours: RefCounted
var _seen: Dictionary = {}        ## faction id -> last influence seen (rivalry deltas)
var _npc_pos: Dictionary = {}     ## npc id -> Vector2 (x, z), for the pacing estimate


func _ready() -> void:
	var f := FileAccess.open(DATA, FileAccess.READ)
	if f:
		var d: Variant = JSON.parse_string(f.get_as_text())
		if d is Dictionary:
			db = d
	rumours = RumoursScript.new(self)
	GameState.mission_ended.connect(_on_mission_ended)
	GameState.influence_changed.connect(_on_influence)
	GameState.phase_changed.connect(func(p: int) -> void:
		if p == GameState.Phase.ORIGIN_SELECT or p == GameState.Phase.MENU:
			_seen = {})


# ------------------------------------------------------------------ state

func st() -> Dictionary:
	var c: Dictionary = GameState.campaign
	for k in ["flags", "tonight", "levers", "people", "day", "grievance", "contact", "amends", "consumed"]:
		if not c.has(k) or not (c[k] is Dictionary):
			c[k] = {}
	for k in ["results", "dawn", "events", "fallen"]:
		if not c.has(k) or not (c[k] is Array):
			c[k] = []
	if not c.has("night"):
		c["night"] = 1
		c["captures"] = 0
		c["leader"] = GameState.origin.get("name", "You")
		_start_rumours()
	return c


func _start_rumours() -> void:
	for id in rumours.defs():
		if bool(rumours.def(id).get("start", false)):
			rumours.seed_rumour(id)


## Fresh campaign state for the current origin (a new game does this through GameState.new_game).
func new_campaign() -> void:
	GameState.campaign = {}
	GameState.tonight_mission = ""
	Mission.journal["rumours"] = {}
	_seen = {}
	st()


func night() -> int:
	return int(st()["night"])


func arc() -> Array:
	return db.get("arc", [])


func arc_entry(n: int) -> Dictionary:
	for e in arc():
		if int(e.get("night", 0)) == n:
			return e
	return {}


func mission_for_night(n: int) -> String:
	for o in arc_entry(n).get("options", []):
		if cond_all(o.get("if", [])):
			return str(o.get("mission", ""))
	return ""


func ended() -> bool:
	return str(st().get("ended", "")) != ""


func flag(name: String) -> bool:
	return bool(st()["flags"].get(name, false))


func set_flag(name: String, v := true) -> void:
	st()["flags"][name] = v


func lever(id: String) -> bool:
	return st()["levers"].has(id)


func found(pid: String) -> bool:
	return bool(st()["people"].get(pid, {}).get("found", false))


func person(pid: String) -> Dictionary:
	return db.get("people", {}).get(pid, {})


func result_of(mission: String) -> Dictionary:
	for r in st()["results"]:
		if str(r.get("mission", "")) == mission:
			return r
	return {}


# ------------------------------------------------------------------ conditions

func cond_all(conds: Array) -> bool:
	for c in conds:
		if not cond(str(c)):
			return false
	return true


## Campaign condition; "a|b|c" means any of them ("origin:artist|merchant|lever:x": parts without a key
## inherit the previous key). "!" negates the whole term.
func cond(c: String) -> bool:
	c = c.strip_edges()
	var neg := c.begins_with("!")
	if neg:
		c = c.substr(1)
	var ok := false
	var key := ""
	for part in c.split("|"):
		var t := str(part)
		if ":" in t or ">=" in t or t == "true":
			key = t.get_slice(":", 0) if ":" in t else ""
		elif key != "":
			t = key + ":" + t
		if _cond1(t):
			ok = true
			break
	return ok != neg


func _cond1(c: String) -> bool:
	if c == "true" or c == "":
		return true
	var key := c.get_slice(":", 0)
	var arg := c.substr(key.length() + 1) if ":" in c else ""
	match key:
		"flag":
			return Mission.has_flag(arg)
		"camp":
			return flag(arg)
		"tonight":
			return bool(st()["tonight"].get(arg, false))
		"lever":
			return lever(arg)
		"found":
			return found(arg)
		"heard":
			return rumours.heard(arg)
		"rumour":
			return rumours.active(arg)
		"night":
			return bool(result_of(arg).get("success", false))
		"lost":
			var r := result_of(arg)
			return not r.is_empty() and not bool(r.get("success", false))
		"played":
			return not result_of(arg).is_empty()
		"origin":
			return GameState.origin_id in arg.split(",")
		"gender":
			return GameState.gender == arg
		"inclination":
			return GameState.inclination != "unspoken" and (GameState.inclination == arg or GameState.inclination == "both" and arg in ["men", "women"])
		"loyalty":
			var p := arg.split(">=")
			return GameState.get_loyalty(p[0]) >= int(p[1])
		"influence":
			var p2 := arg.split(">=")
			return arms_length(p2[0]) == "" and GameState.get_influence(p2[0]) >= int(p2[1])
		"grievance":
			var p3 := arg.split(">=")
			return int(st()["grievance"].get(p3[0], 0)) >= int(p3[1])
		"top":
			return top_faction() == arg
	if c.begins_with("crackdown>="):
		return GameState.crackdown >= int(c.trim_prefix("crackdown>="))
	if c.begins_with("notoriety>="):
		return GameState.notoriety() >= float(c.trim_prefix("notoriety>="))
	if c.begins_with("coins>="):
		return GameState.coins >= int(c.trim_prefix("coins>="))
	if c.begins_with("loyal_count>="):
		return loyal_count(60) >= int(c.trim_prefix("loyal_count>="))
	if c.begins_with("night>="):
		return night() >= int(c.trim_prefix("night>="))
	push_warning("Campaign: unknown condition '%s'" % c)
	return false


func loyal_count(at: int) -> int:
	var n := 0
	for fid in LOCAL:
		if GameState.get_loyalty(fid) >= at:
			n += 1
	return n


func top_faction() -> String:
	var best := ""
	var bv := -1
	for fid in LOCAL:
		var v := GameState.get_loyalty(fid) + GameState.get_influence(fid) / 2
		if v > bv:
			bv = v
			best = fid
	return best


func fname(fid: String) -> String:
	return str(GameState.factions.get(fid, {}).get("name", fid.capitalize()))


# ------------------------------------------------------------------ effects

## Applies an effects dict (data/campaign.json, rumours.json, missions.json "campaign", events.json) and appends
## what happened to `lines` in words.
func apply_effects(eff: Dictionary, lines: Array = [], _why := "") -> void:
	if eff.is_empty():
		return
	var parts: PackedStringArray = []
	for fid in eff.get("influence", {}):
		var dv := int(eff["influence"][fid])
		GameState.add_influence(str(fid), dv)
		parts.append("%s influence %+d" % [fname(fid), dv])
	for fid in eff.get("loyalty", {}):
		var dv := int(eff["loyalty"][fid])
		if dv != 0:
			GameState.add_loyalty(str(fid), dv)
			parts.append("%s loyalty %+d" % [fname(fid), dv])
	for fid in eff.get("fear", {}):
		var dv := int(eff["fear"][fid])
		if dv != 0:
			GameState.add_fear(str(fid), dv)
			parts.append("%s fear %+d" % [fname(fid), dv])
	for fid in eff.get("strength", {}):
		var dv := int(eff["strength"][fid])
		if GameState.factions.has(fid):
			GameState.factions[fid]["strength"] = clampi(int(GameState.factions[fid]["strength"]) + dv, 0, 100)
			parts.append("%s strength %+d" % [fname(fid), dv])
	if eff.has("crackdown") and int(eff["crackdown"]) != 0:
		GameState.crackdown = clampi(GameState.crackdown + int(eff["crackdown"]), 0, 100)
		parts.append("Crackdown %+d" % int(eff["crackdown"]))
	if eff.has("coins") and int(eff["coins"]) != 0:
		GameState.coins = maxi(GameState.coins + int(eff["coins"]), 0)
		parts.append("%+d zł" % int(eff["coins"]))
	if eff.has("notoriety") and int(eff["notoriety"]) != 0:
		GameState.add_notoriety(float(eff["notoriety"]))
		parts.append("Notoriety %+d" % int(eff["notoriety"]))
	for fl in eff.get("camp", []):
		set_flag(str(fl))
	for fl in eff.get("tonight", []):
		st()["tonight"][str(fl)] = true
	for fid in eff.get("grievance", {}):
		add_grievance(str(fid), int(eff["grievance"][fid]))
	for lv in eff.get("levers", []):
		gain_lever(str(lv), "", lines)
	for pid in eff.get("found", []):
		find_person(str(pid), lines)
	for rid in eff.get("seed", []):
		rumours.seed_rumour(str(rid))
	for rid in eff.get("hear", []):
		rumours.seed_rumour(str(rid))
		rumours.hear(str(rid), "told")
	for pr in eff.get("plant", []):
		plant(str(pr[0]), str(pr[1]), true)
	if eff.has("hear_group"):
		for rid in rumours.loudest_unheard():
			var cs: Array = rumours.state_of(rid).get("carriers", [])
			if not rumours.group_members([eff["hear_group"]]).filter(func(a) -> bool: return a in cs).is_empty():
				rumours.hear(rid, "told")
				break
	for i in int(eff.get("hear_loudest", 0)):
		var lu: Array = rumours.loudest_unheard()
		if lu.is_empty():
			break
		rumours.hear(str(lu[0]), "told")
	for did in eff.get("district", {}):
		var dd: Dictionary = GameState.districts.get(did, {})
		var de: Dictionary = eff["district"][did]
		if dd.is_empty():
			continue
		for k in de:
			if k == "controller":
				dd["controller"] = str(de[k])
				parts.append("%s now answers to %s" % [dd.get("name", did), fname(str(de[k]))])
			else:
				dd[k] = clampi(int(dd.get(k, 0)) + int(de[k]), 0, 100 if k == "unrest" else 5)
	var text := str(eff.get("text", ""))
	if text != "":
		lines.append(text + ("  (" + ", ".join(parts) + ")" if not parts.is_empty() else ""))
	elif not parts.is_empty() and _why != "silent":
		lines.append(", ".join(parts))
	changed.emit()


func gain_lever(id: String, from: String = "", lines: Array = []) -> void:
	if id == "" or lever(id):
		return
	var name := id.replace("_", " ").capitalize()
	var text := ""
	for pid in db.get("people", {}):
		var lv: Dictionary = person(pid).get("lever", {})
		if str(lv.get("id", "")) == id:
			name = str(lv.get("name", name))
			text = str(lv.get("text", ""))
	st()["levers"][id] = {"name": name, "text": text, "from": from, "day": GameState.day}
	lines.append("Lever gained: %s. %s" % [name, text])


# ------------------------------------------------------------------ people

## Mark person `pid` found: journal People entry (found: true), lever, rumour proven.
func find_person(pid: String, lines: Array = [], node: Node3D = null) -> bool:
	var p := person(pid)
	if p.is_empty() or found(pid):
		return false
	var e: Dictionary = st()["people"].get(pid, {})
	e["found"] = true
	e["day"] = GameState.day
	st()["people"][pid] = e
	var lv: Dictionary = p.get("lever", {})
	var jp: Dictionary = Mission.journal["people"]
	jp[pid] = {"name": str(p.get("name", pid)), "role": str(p.get("role", "")), "faction": fname(str(p.get("faction", ""))),
			"where": str(p.get("where", "")), "t": GameState.time_string(), "night": GameState.day, "found": true,
			"lever": str(lv.get("name", "")) + (": " + str(lv.get("text", "")) if lv.has("text") else ""),
			"historical": bool(p.get("historical", false))}
	lines.append("Found: %s, %s." % [p.get("name", pid), p.get("where", "")])
	if not lv.is_empty():
		gain_lever(str(lv["id"]), pid, lines)
	for x in p.get("extra_levers", []):
		gain_lever(str(x), pid, lines)
	apply_effects(p.get("found_effects", {}), lines, "silent")
	for rid in rumours.defs():
		if str(rumours.def(rid).get("person", "")) == pid and rumours.in_play(rid):
			rumours.state_of(rid)["proven"] = true
			rumours.sync_journal(rid)
	if str(st().get("lead", "")) == pid:
		st()["lead"] = ""
	if Mission.is_active():
		Mission.message.emit("Found: %s. %s" % [p.get("name", pid), lv.get("name", "")], 4.0)
		Mission.journal_log("Found %s (%s). Lever: %s." % [p.get("name", pid), p.get("where", ""), lv.get("name", "none")], "story")
	changed.emit()
	return true


## Persons to place in tonight's world: the chosen lead, anyone drawn into the open by a rumour.
## [{id, def, pos: Array, open: bool}]
func night_people() -> Array:
	var out: Array = []
	var lead := str(st().get("lead", ""))
	for pid in db.get("people", {}):
		var p := person(pid)
		if found(pid) or p.has("mission_only") or bool(p.get("offstage", false)) or not p.has("pos"):
			continue
		var open_flag := str(p.get("open_flag", ""))
		if open_flag != "" and flag(open_flag) and p.has("open_pos"):
			out.append({"id": pid, "def": p, "pos": p["open_pos"], "open": true})
		elif pid == lead:
			out.append({"id": pid, "def": p, "pos": p["pos"], "open": false})
	return out


## Leads the day panel offers: persons not yet found whose rumour the player has heard.
func leads() -> Array:
	var out: Array = []
	for rid in rumours.known():
		var pid := str(rumours.def(rid).get("person", ""))
		if pid == "" or found(pid) or person(pid).is_empty():
			continue
		var p := person(pid)
		out.append({"id": pid, "rumour": rid, "label": "Follow the lead: %s" % p.get("role", pid),
				"desc": str(rumours.def(rid).get("text", "")), "chosen": str(st().get("lead", "")) == pid,
				"mission_only": p.has("mission_only")})
	return out


func choose_lead(pid: String) -> void:
	st()["lead"] = pid if str(st().get("lead", "")) != pid else ""
	changed.emit()


func heirs() -> Array:
	var out: Array = []
	for pid in db.get("people", {}):
		var p := person(pid)
		if not p.has("heir"):
			continue
		if p.has("heir_if"):
			if not cond_all(p["heir_if"]):
				continue
		elif not found(pid):
			continue
		out.append(pid)
	return out


# ------------------------------------------------------------------ rivalry, arm's length, grievance

func _rel() -> Dictionary:
	return db.get("relations", {})


func rivals(fid: String) -> Dictionary:
	var out := {}
	for k in _rel():
		if k.begins_with("_"):
			continue
		var ab: PackedStringArray = str(k).split("|")
		if ab.size() == 2 and (ab[0] == fid or ab[1] == fid):
			out[ab[1] if ab[0] == fid else ab[0]] = float(_rel()[k])
	return out


func _on_influence(fid: String, value: int) -> void:
	var before := int(_seen.get(fid, value))
	_seen[fid] = value
	var ph := GameState.phase
	if GameState.campaign.is_empty() or not (ph == GameState.Phase.DAY or ph == GameState.Phase.NIGHT or ph == GameState.Phase.DAWN):
		return
	var d := value - before
	if d <= 0:
		return
	var g: Dictionary = db.get("grievance", {})
	if d >= int(g.get("contact_min", 3)):
		st()["contact"][fid] = GameState.day
		add_grievance(fid, -int(g.get("contact_relief", 10)))
	var rv := rivals(fid)
	for b in rv:
		var loss := int(round(d * float(rv[b])))
		if loss > 0 and GameState.factions.has(b):
			GameState.add_loyalty(b, -loss)
			st()["contact"]["hurt:%s|%s" % [b, fid]] = GameState.day
			if d >= 5:
				add_grievance(b, int(g.get("rival_favour", 4)))


## The rival for whose sake `fid` keeps the player at arm's length, or "".
func arms_length(fid: String) -> String:
	if GameState.campaign.is_empty() or not fid in LOCAL:
		return ""
	if int(st()["amends"].get(fid, -99)) >= GameState.day - 2:
		return ""
	var gap := int(db.get("arms_length_gap", 30))
	var rv := rivals(fid)
	for a in rv:
		if float(rv[a]) >= 0.3 and GameState.get_influence(a) - GameState.get_influence(fid) > gap:
			return a
	return ""


func add_grievance(fid: String, dv: int) -> void:
	if not fid in LOCAL:
		return
	st()["grievance"][fid] = clampi(int(st()["grievance"].get(fid, 0)) + dv, 0, 100)


func grievance(fid: String) -> int:
	return int(st()["grievance"].get(fid, 0))


## Lines for the day briefing: rival pairs that hurt now, factions at arm's length, grievances.
func relation_lines() -> Array:
	var out: Array = []
	var texts: Dictionary = db.get("rivalry_text", {})
	for fid in LOCAL:
		var a := arms_length(fid)
		if a != "":
			out.append({"text": "%s keeps you at arm's length (too close to %s). Make amends to open its doors." % [fname(fid), fname(a)], "bad": true})
	for k in st()["contact"]:
		var ks := str(k)
		if ks.begins_with("hurt:") and int(st()["contact"][k]) >= GameState.day - 1:
			var pair := ks.trim_prefix("hurt:")
			if texts.has(pair) and out.size() < 4:
				out.append({"text": str(texts[pair]), "bad": false})
	var sab := int(db.get("grievance", {}).get("sabotage_at", 60))
	for fid in LOCAL:
		var gv := grievance(fid)
		if gv >= sab:
			out.append({"text": "%s is aggrieved (%d): unless appeased it will spoil tonight." % [fname(fid), gv], "bad": true})
		elif gv >= sab - 20:
			out.append({"text": "%s feels neglected (%d)." % [fname(fid), gv], "bad": false})
	return out


## Factions that will sabotage tonight: [{faction, kind, text}].
func sabotage_tonight() -> Array:
	var out: Array = []
	var g: Dictionary = db.get("grievance", {})
	for fid in LOCAL:
		if grievance(fid) >= int(g.get("sabotage_at", 60)):
			var s: Dictionary = g.get("sabotage", {}).get(fid, {})
			if not s.is_empty():
				out.append({"faction": fid, "kind": str(s.get("kind", "patrol")), "text": str(s.get("text", ""))})
	return out


func _dawn_grievance(lines: Array) -> void:
	var g: Dictionary = db.get("grievance", {})
	for fid in LOCAL:
		var last := int(st()["contact"].get(fid, 1))
		if GameState.day - last >= int(g.get("neglect_nights", 2)):
			add_grievance(fid, int(g.get("neglect", 12)))
	var promises: Dictionary = g.get("promises", {})
	for fl in promises:
		if Mission.has_flag(str(fl)) and not flag("promise_" + str(fl)):
			set_flag("promise_" + str(fl))
			add_grievance(str(promises[fl]), int(g.get("promise", 25)))
			lines.append("A promise is owed to the %s. It will be remembered if it is not kept." % fname(str(promises[fl])))


# ------------------------------------------------------------------ day

## Called by the day panel when it is built: a new day's action points, tonight's mission, the day briefing.
func prepare_day() -> void:
	var s := st()
	var dd: Dictionary = s["day"]
	if int(dd.get("day", -1)) != GameState.day:
		var ap := int(db.get("actions_per_day", 2))
		var res: Array = s["results"]
		if not res.is_empty() and bool(res[-1].get("success", false)) and int(res[-1].get("night", 0)) == GameState.day - 1:
			ap += int(db.get("bonus_action_after_win", 1))
		s["day"] = {"day": GameState.day, "left": ap, "max": ap, "done": [], "feed": [], "urchin": false}
		for fid in GameState.factions:
			_seen[fid] = GameState.get_influence(fid)
	if not ended():
		var m := mission_for_night(night())
		GameState.tonight_mission = m
		Mission.prepare_for_day(m)
	changed.emit()


func day_state() -> Dictionary:
	return st()["day"]


func actions_left() -> int:
	return int(day_state().get("left", 0))


func _feed(text: String) -> void:
	(day_state()["feed"] as Array).append(text)


## Day actions for the panel: [{id, label, desc, enabled, why, kind}]
func day_actions() -> Array:
	var out: Array = []
	var done: Array = day_state().get("done", [])
	for a in db.get("day_actions", []):
		var id := str(a["id"])
		var e := {"id": id, "label": str(a["label"]), "desc": str(a.get("desc", "")), "kind": "action"}
		var why := ""
		if id in done and not bool(a.get("repeat", false)):
			why = "Done today."
		elif not cond_all(a.get("need", [])):
			why = str(a.get("why", "Not open to you."))
		elif GameState.coins < int(a.get("cost", 0)):
			why = "Not enough coin."
		e["enabled"] = why == "" and actions_left() > 0
		e["why"] = why if why != "" else ("No time left today." if actions_left() <= 0 else "")
		out.append(e)
	for pid in db.get("people", {}):
		var p := person(pid)
		if not found(pid) or not p.has("meet") or bool(st()["people"][pid].get("met", false)):
			continue
		var m: Dictionary = p["meet"]
		var ok := GameState.coins >= int(m.get("cost", 0))
		out.append({"id": "meet:" + pid, "label": str(m.get("label", "Meet " + str(p.get("name", pid)))), "desc": str(m.get("desc", "")),
				"kind": "meet", "enabled": ok and actions_left() > 0, "why": "" if ok else "Not enough coin."})
	for rid in rumours.known():
		var ct: Dictionary = rumours.def(rid).get("counter", {})
		if not ct.is_empty() and rumours.in_play(rid) and not rumours.took_hold(rid):
			out.append({"id": "counter:" + rid, "label": str(ct.get("label", "Counter it")), "desc": str(ct.get("desc", "")),
					"kind": "counter", "enabled": actions_left() > 0, "why": ""})
	for pid in heirs():
		if pid == nominee():
			continue
		var hp := person(pid)
		out.append({"id": "nominate:" + pid, "label": "Name %s your heir" % hp.get("name", pid), "kind": "nominate",
				"desc": "If you fall, %s takes the banner. %s gains; its rivals notice.%s" % [hp.get("name", pid), fname(str(hp.get("faction", ""))),
				" Changing heirs costs trust." if nominee() != "" else ""], "enabled": actions_left() > 0, "why": ""})
	var g: Dictionary = db.get("grievance", {})
	for fid in LOCAL:
		if grievance(fid) >= 40:
			var cost := int(g.get("appease_cost", 3))
			out.append({"id": "appease:" + fid, "label": "Appease the %s (%d zł)" % [fname(fid), cost], "kind": "appease",
					"desc": "A favour, a purse, a word in the right ear. Grievance -%d." % int(g.get("appease", 40)),
					"enabled": GameState.coins >= cost and actions_left() > 0, "why": "" if GameState.coins >= cost else "Not enough coin."})
		var a := arms_length(fid)
		if a != "":
			out.append({"id": "amends:" + fid, "label": "Make amends with the %s" % fname(fid), "kind": "amends",
					"desc": "Distance yourself from the %s for a while (%s influence -3, 1 zł). Its doors open for three days." % [fname(a), fname(a)],
					"enabled": GameState.coins >= 1 and actions_left() > 0, "why": ""})
	return out


## Performs day action `id`. Returns the feedback line ("" if not allowed).
func do_action(id: String) -> String:
	if actions_left() <= 0:
		return ""
	var lines: Array = []
	var label := id
	if id.begins_with("nominate:"):
		return nominate(id.trim_prefix("nominate:"))
	if id.begins_with("counter:"):
		var rid := id.trim_prefix("counter:")
		var ct: Dictionary = rumours.def(rid).get("counter", {})
		rumours.state_of(rid)["status"] = "disproved"
		rumours.state_of(rid)["countered"] = true
		rumours.sync_journal(rid)
		apply_effects(ct.get("effects", {}), lines)
		label = str(ct.get("label", "Countered"))
		day_state()["left"] = actions_left() - 1
		(day_state()["done"] as Array).append(id)
		var tx := label + ": " + " ".join(lines)
		_feed(tx)
		changed.emit()
		return tx
	if id.begins_with("meet:"):
		var pid := id.trim_prefix("meet:")
		var m: Dictionary = person(pid).get("meet", {})
		if GameState.coins < int(m.get("cost", 0)):
			return ""
		GameState.coins -= int(m.get("cost", 0))
		st()["people"][pid]["met"] = true
		label = str(m.get("label", id))
		apply_effects(m.get("effects", {}), lines)
	elif id.begins_with("appease:"):
		var fid := id.trim_prefix("appease:")
		var g: Dictionary = db.get("grievance", {})
		if GameState.coins < int(g.get("appease_cost", 3)):
			return ""
		GameState.coins -= int(g.get("appease_cost", 3))
		add_grievance(fid, -int(g.get("appease", 40)))
		st()["contact"][fid] = GameState.day
		label = "Appeased the %s" % fname(fid)
		lines.append("Grievance now %d." % grievance(fid))
	elif id.begins_with("amends:"):
		var fid2 := id.trim_prefix("amends:")
		var a := arms_length(fid2)
		GameState.coins = maxi(GameState.coins - 1, 0)
		if a != "":
			GameState.add_influence(a, -3)
		st()["amends"][fid2] = GameState.day
		label = "Made amends with the %s" % fname(fid2)
	else:
		var a: Dictionary = {}
		for x in db.get("day_actions", []):
			if str(x["id"]) == id:
				a = x
		if a.is_empty() or not cond_all(a.get("need", [])) or GameState.coins < int(a.get("cost", 0)):
			return ""
		if id in day_state()["done"] and not bool(a.get("repeat", false)):
			return ""
		GameState.coins -= int(a.get("cost", 0))
		label = str(a["label"])
		apply_effects(a.get("effects", {}), lines)
	day_state()["left"] = actions_left() - 1
	(day_state()["done"] as Array).append(id)
	var text := label + ((": " + " ".join(lines)) if not lines.is_empty() else ".")
	_feed(text)
	changed.emit()
	return text


# --- planting

func channels() -> Array:
	var out: Array = []
	var chs: Dictionary = db.get("channels", {})
	for cid in chs:
		var c: Dictionary = chs[cid]
		var cost := channel_cost(cid)
		var why := ""
		if not cond_all(c.get("need", [])):
			why = str(c.get("why", "Not open to you."))
		elif GameState.coins < cost:
			why = "Not enough coin."
		out.append({"id": cid, "name": str(c.get("name", cid)), "desc": str(c.get("desc", "")), "cost": cost,
				"trace": float(c.get("trace", 0.1)), "enabled": why == "", "why": why})
	return out


func channel_cost(cid: String) -> int:
	var c: Dictionary = db.get("channels", {}).get(cid, {})
	var cost := int(c.get("cost", 1))
	var cw: Dictionary = c.get("cost_with", {})
	for k in cw:
		if cond(str(k)):
			cost = mini(cost, int(cw[k]))
	if cid == "press" and flag("free_press"):
		cost = 0
	return cost


## Plant rumour `rid` through channel `cid`. `free`: no coin, no day action (mission rewards). Returns the line.
func plant(rid: String, cid: String, free := false) -> String:
	var c: Dictionary = db.get("channels", {}).get(cid, {})
	var d: Dictionary = rumours.def(rid)
	if c.is_empty() or d.is_empty():
		return ""
	if not free:
		if actions_left() <= 0 or not cond_all(c.get("need", [])) or GameState.coins < channel_cost(cid):
			return ""
		GameState.coins -= channel_cost(cid)
		if cid == "press" and flag("free_press"):
			set_flag("free_press", false)
		day_state()["left"] = actions_left() - 1
		(day_state()["done"] as Array).append("plant:" + rid)
	if rumours.is_superstition(rid):
		GameState.add_influence("salon", -int(rumours.db.get("superstition_salon_cost", 2)))
	var groups: Array = rumours.db.get("channels_seed", {}).get(cid, [])
	rumours.seed_rumour(rid, groups, true, cid, int(c.get("extra", 0)))
	var text := "Planted \"%s\" through %s (reach %d%%). %s" % [d.get("text", rid), c.get("name", cid), rumours.reach(rid), d.get("plant_note", "")]
	if not free:
		_feed(text)
	changed.emit()
	return text


# --- the passage urchins

func urchin_truth_chance() -> float:
	var u: Dictionary = db.get("urchins", {})
	return minf(float(u.get("truth_base", 0.6)) + GameState.get_influence("street") * float(u.get("truth_per_street", 0.005)), float(u.get("truth_max", 0.95)))


func urchin_offers() -> Array:
	var out: Array = []
	var u: Dictionary = db.get("urchins", {})
	var bought := bool(day_state().get("urchin", false))
	for oid in u.get("offers", {}):
		var o: Dictionary = u["offers"][oid]
		var ok := not bought and GameState.coins >= int(u.get("cost", 1))
		out.append({"id": oid, "label": str(o["label"]), "desc": str(o.get("desc", "")), "enabled": ok,
				"why": "The urchins have gone to earn elsewhere today." if bought else ("Not enough coin." if not ok else "")})
	return out


## Buy from the urchins (by day, or at night through the mission runner). Returns what they said.
func urchin_buy(oid: String, at_night := false) -> String:
	var u: Dictionary = db.get("urchins", {})
	if GameState.coins < int(u.get("cost", 1)):
		return ""
	if not at_night:
		if bool(day_state().get("urchin", false)):
			return ""
		day_state()["urchin"] = true
	GameState.coins -= int(u.get("cost", 1))
	var rng := RandomNumberGenerator.new()
	rng.seed = hash("urchin|%d|%s|%d" % [GameState.day, oid, int(GameState.clock_minutes)])
	var honest := rng.randf() < urchin_truth_chance()
	var text := ""
	var lies: Array = u.get("lies", [])
	match oid:
		"sweep":
			st()["tonight"]["urchin_sweep" if honest else "urchin_sweep_lie"] = true
			text = "Staś swears patrol A will walk the north side only, and away from you." if honest else "Kasia says the watch will be thin tonight. She is grinning."
		"rumour":
			var lu: Array = rumours.loudest_unheard()
			if honest and not lu.is_empty():
				rumours.hear(str(lu[0]), "sold by the passage urchins")
				text = "Staś: \"%s\"" % rumours.def(lu[0]).get("text", "")
			else:
				var l: Array = lies[rng.randi() % lies.size()] if not lies.is_empty() else ["", "", "Nothing worth a grosz."]
				rumours._log("rumour (from the urchins, unproven): " + str(l[2]))
				text = "Kasia: \"%s\" (%s)" % [l[0], l[1]]
		"seen":
			var pick := ""
			for pid in db.get("people", {}):
				if found(pid) or person(pid).has("mission_only") or bool(person(pid).get("offstage", false)):
					continue
				for rid in rumours.defs():
					if str(rumours.def(rid).get("person", "")) == pid and not rumours.heard(rid):
						pick = rid
						break
				if pick != "":
					break
			if honest and pick != "":
				rumours.hear(pick, "the urchins saw them")
				text = "Staś saw someone: " + str(rumours.def(pick).get("text", ""))
			else:
				text = "They send you to a coal cellar in Stradom. There is nobody there but rats."
		"window":
			if honest:
				st()["tonight"]["extra_slip"] = true
				text = "Kasia knows a window by the apothecary that doesn't latch. If the watch takes you, you can slip away once more."
			else:
				text = "The window they promised was nailed shut last week. They knew."
		"shadow":
			var who := ""
			for pid in db.get("people", {}):
				if found(pid) and person(pid).has("meet") and not bool(st()["people"][pid].get("met", false)):
					who = pid
					break
			if honest and who != "":
				st()["people"][who]["met"] = true
				var ls: Array = []
				apply_effects(person(who)["meet"].get("effects", {}), ls)
				text = "The urchins shadowed %s all morning and brought you their news. %s" % [person(who).get("name", who), " ".join(ls)]
			else:
				text = "They followed the wrong man to the baths and back."
		"message":
			var worst := ""
			for fid in LOCAL:
				if worst == "" or grievance(fid) > grievance(worst):
					worst = fid
			add_grievance(worst, -20)
			text = "Kasia carried your message to the %s. Grievance -20." % fname(worst)
	if not at_night:
		_feed("The urchins (1 zł): " + text)
	changed.emit()
	return text


# --- trial and succession

func trial_pending() -> bool:
	return bool(st().get("trial", false))


## "flogging": notoriety cleared, 1 health next night. "exile": tonight is lost (the arc moves on).
func do_trial(choice: String) -> String:
	st()["trial"] = false
	st()["captures"] = 0
	var text := ""
	if choice == "flogging":
		GameState.add_notoriety(-100.0)
		set_flag("flogged")
		text = "Twenty-five strokes at the whipping post, counted in German. The crowd did not jeer. Notoriety cleared; you go out tonight with one breath of health."
	else:
		set_flag("exiled")
		text = "Banished from the Old Town for a night. Tonight's work is done by others, badly."
	_feed(text)
	changed.emit()
	return text


## True when the day panel must offer the exile's skipped night instead of going out.
func exiled_tonight() -> bool:
	return flag("exiled")


## The exiled night passes: counts as a lost night for the arc.
func pass_exile() -> void:
	set_flag("exiled", false)
	var m := mission_for_night(night())
	(st()["results"] as Array).append({"night": GameState.day, "mission": m, "success": false, "approach": "exile"})
	var lines: Array = ["You spent the night outside the walls. %s went ahead without you and failed." % Mission.mission_data(m).get("title", "Tonight's work")]
	apply_effects(Mission.mission_data(m).get("campaign", {}).get("failure", {}), lines, "silent")
	st()["night"] = night() + 1
	GameState.day += 1
	GameState.night_start_influence = {}
	st()["dawn"] = lines
	_check_end(false, m, lines)
	GameState.last_night_success = false
	GameState.last_night_summary = lines[0]
	GameState.set_phase(GameState.Phase.DAWN)


func succession_pending() -> bool:
	return not (st().get("card", {}) as Dictionary).is_empty() or not (st().get("coup", {}) as Dictionary).is_empty()


func _sc() -> Dictionary:
	return db.get("succession", {})


func nominee() -> String:
	return str(st().get("nominee", ""))


func nominee_name() -> String:
	var n := nominee()
	if n == "":
		return ""
	return str(person(n).get("name", n))


## Name `pid` (a found person with an heir entry) as the movement's heir. Costs a day action (unless `free`).
func nominate(pid: String, free := false) -> String:
	if not pid in heirs() or pid == nominee():
		return ""
	if not free:
		if actions_left() <= 0:
			return ""
		day_state()["left"] = actions_left() - 1
		(day_state()["done"] as Array).append("nominate:" + pid)
	var sc := _sc()
	var lines: Array = []
	var old := nominee()
	if old != "":
		var of := str(person(old).get("faction", ""))
		if GameState.factions.has(of):
			GameState.add_loyalty(of, -int(sc.get("drop_loyalty", 5)))
			lines.append("%s is dropped as heir; %s loyalty -%d." % [person(old).get("name", old), fname(of), int(sc.get("drop_loyalty", 5))])
	st()["nominee"] = pid
	st()["nominee_day"] = GameState.day
	var p := person(pid)
	var f := str(p.get("faction", ""))
	if f in LOCAL:
		GameState.add_influence(f, int(sc.get("nominee_influence", 4)))
	var sd: Dictionary = sc.get("scandals", {}).get(pid, {})
	if not sd.is_empty():
		lines.append(str(sd.get("text", "")))
		set_flag("heir_scandal")
	var jp: Dictionary = Mission.journal["people"]
	for k in jp:
		(jp[k] as Dictionary).erase("heir")
	if jp.has(pid):
		jp[pid]["heir"] = true
	var text := "You name %s your heir: if you fall, the banner passes to %s. %s" % [p.get("name", pid), "her" if str(p.get("heir", {}).get("gender", "m")) == "f" else "him", " ".join(lines)]
	if not free:
		_feed(text)
	changed.emit()
	return text


## The figurehead fell (`how`: "dead", "taken", "coup"; `cause` in words). The nominee takes over; with none
## the movement imposes the strongest faction's protégé. Either way a succession card waits for the day panel.
func fall(cause: String, lines: Array, how := "dead") -> void:
	(st()["fallen"] as Array).append({"name": str(st().get("leader", "You")), "cause": cause, "day": GameState.day, "how": how})
	lines.append("%s has fallen: %s." % [st().get("leader", "The figurehead"), cause])
	var n := nominee()
	if n != "" and n in heirs():
		install(n, str(person(n).get("faction", "")), "nominated", how, lines)
	else:
		force_succession(how, cause, lines)


## The movement imposes its own candidate: the protégé of its strongest faction.
func force_succession(how: String, cause: String, lines: Array) -> String:
	var backer := strongest_faction()
	var pr: Dictionary = _sc().get("proteges", {}).get(backer, {})
	if pr.is_empty():
		st()["ended"] = "fallen"
		st()["ending"] = {"title": "An Epitaph", "text": "No one was ready to take up the banner. The press was broken up for scrap, the salon closed its shutters, and the ballads changed their words. On a pillar of the Cloth Hall someone chalked a name, yours, and the rain took it by Easter."}
		lines.append("No one will take up the banner. The movement falls apart.")
		return ""
	install(str(pr["id"]), backer, "forced", how, lines, pr)
	lines.append("The %s forced its own candidate on the movement: %s. (%s)" % [fname(backer), pr.get("name", ""), cause])
	return str(pr["id"])


func strongest_faction() -> String:
	var best := ""
	for fid in LOCAL:
		if best == "" or GameState.get_influence(fid) > GameState.get_influence(best):
			best = fid
	return best


## Makes `pid` the figurehead. `pr`: a protégé entry (not a person found). Influence at 70% (100% for `backer`).
func install(pid: String, backer: String, kind: String, how: String, lines: Array, pr: Dictionary = {}) -> void:
	var p := person(pid) if pr.is_empty() else pr
	var h: Dictionary = p.get("heir", pr)
	if not GameState.origins.has(str(h.get("origin", ""))):
		return
	var sc := _sc()
	var fallen_name := str(st().get("leader", "the figurehead"))
	for fid in GameState.factions:
		if fid != backer:
			GameState.set_influence(fid, int(round(GameState.get_influence(fid) * 0.7)))
	if kind == "forced" and backer in LOCAL:
		GameState.add_influence(backer, int(sc.get("backer_influence", 10)))
		var rv := rivals(backer)
		for b in rv:
			GameState.add_influence(b, -int(sc.get("rival_loss", 6)))
		for rid in rumours.st():
			var rs: Dictionary = rumours.st()[rid]
			if bool(rs.get("planted", false)) and not bool(rs.get("took", false)):
				rs["status"] = "disproved"
				rs["lapsed"] = true
	GameState.origin_id = str(h["origin"])
	GameState.origin = GameState.origins[GameState.origin_id]
	GameState.gender = str(h.get("gender", "m"))
	GameState.inclination = str(h.get("inclination", "unspoken"))
	GameState.add_notoriety(-100.0)
	st()["leader"] = str(p.get("name", pid))
	st()["heir"] = pid
	st()["nominee"] = ""
	st()["failed_row"] = 0
	var fate: String = {"dead": "martyr", "taken": "prisoner", "coup": "exile"}.get(how, "martyr")
	var rtext: String = {"martyr": "%s died for the Third of May; %s carries the banner now.",
			"prisoner": "%s rots in the Wawel cells; %s carries the banner now.",
			"exile": "%s was pushed aside and has left the city; %s leads the movement now."}[fate] % [fallen_name, p.get("name", pid)]
	rumours.db["rumours"]["fallen_" + fate] = {"subject": "The %s" % fate, "truth": true, "spread": 0.5, "seed": ["passage", "church", "well"],
			"text": rtext, "line": ["Stary przywódca odszedł. Sztandar niesie kto inny.", "The old leader is gone. Someone else carries the banner."],
			"effects": {"loyalty": {"street": 6 if fate == "martyr" else 2, "church": (2 if GameState.get_loyalty("church") >= 50 else -3) if fate == "martyr" else 0},
					"text": "The fallen figurehead's name is chalked on the pillars of the Cloth Hall."}}
	rumours.seed_rumour("fallen_" + fate)
	rumours.hear("fallen_" + fate, "the whole city")
	var changes: Array = []
	changes.append("%s, %s." % [GameState.origin.get("name", ""), "a woman" if GameState.gender == "f" else "a man"])
	changes.append("Influence carried over at 70%%%s; notoriety forgotten." % ((" (100%% with the %s)" % fname(backer)) if kind == "forced" and backer in LOCAL else ""))
	if kind == "forced":
		changes.append("The %s gained ground; its rivals lost it. Rumours you planted that had not taken hold have lapsed." % fname(backer))
	st()["card"] = {"name": str(p.get("name", pid)), "role": str(p.get("role", "")), "kind": kind, "how": how, "fallen": fallen_name,
			"backer": fname(backer) if backer != "" else "", "changes": changes}
	var jp: Dictionary = Mission.journal["people"]
	jp[pid] = {"name": str(p.get("name", pid)), "role": str(p.get("role", "")) + " (now the figurehead)", "faction": fname(backer),
			"where": "at the head of the movement", "t": "day", "night": GameState.day, "found": true, "leader": true}
	lines.append("%s takes up the banner (%s)." % [p.get("name", pid), "your nominee" if kind == "nominated" else "forced by the %s" % fname(backer)])
	changed.emit()


func dismiss_card() -> void:
	st()["card"] = {}
	changed.emit()


func card() -> Dictionary:
	return st().get("card", {})


func coup() -> Dictionary:
	return st().get("coup", {})


## Does the movement lose faith in the figurehead? Sets st.coup for the day panel. Called at dawn.
func _faith_check(lines: Array) -> void:
	var sc := _sc()
	var why := ""
	var top := strongest_faction()
	if grievance(top) >= int(sc.get("faith_grievance", 80)):
		why = "the %s, the movement's strongest arm, is sick of being ignored" % fname(top)
	elif GameState.notoriety() >= float(sc.get("faith_notoriety", 90)):
		why = "every soldier in Kraków knows your face"
	elif int(st().get("failed_row", 0)) >= int(sc.get("faith_failures", 2)):
		why = "two nights lost in a row"
	if why != "" and not ended():
		st()["coup"] = {"faction": top, "why": why}
		lines.append("The movement is losing faith in you: %s. The %s will confront you this morning." % [why, fname(top)])


## Day-phase confrontation: "concede" (pay the backer's price), "firm" (eloquence test), "yield" (step aside).
func resolve_coup(choice: String) -> String:
	var c := coup()
	if c.is_empty():
		return ""
	st()["coup"] = {}
	var fid := str(c["faction"])
	var sc := _sc()
	var lines: Array = []
	var text := ""
	match choice:
		"concede":
			var con: Dictionary = sc.get("concession", {})
			GameState.coins = maxi(GameState.coins - int(con.get("coins", 3)), 0)
			for b in rivals(fid):
				GameState.add_influence(b, int(con.get("rival_influence", -4)))
			add_grievance(fid, int(con.get("grievance", -50)))
			st()["failed_row"] = 0
			text = "You give the %s what it wants. You keep the seat; its rivals notice what it cost." % fname(fid)
		"firm":
			var chance := 0.3 + 0.1 * GameState.skill("eloquence")
			var rng := RandomNumberGenerator.new()
			rng.seed = hash("coup|%d|%s" % [GameState.day, fid])
			if rng.randf() < chance:
				add_grievance(fid, -20)
				st()["failed_row"] = 0
				text = "You talk them down. The %s grumbles, and follows." % fname(fid)
			else:
				force_succession("coup", "the %s would not be talked down" % fname(fid), lines)
				text = "They will not be talked down. " + " ".join(lines)
		_:
			force_succession("coup", "you stepped aside for the %s's candidate" % fname(fid), lines)
			text = "You step aside. " + " ".join(lines)
	_feed(text)
	changed.emit()
	return text


# ------------------------------------------------------------------ night side

## Tonight's modifiers for mission_runner.gd: {remove_guards, add_guards: [{name, wps}], view_mult, health,
## hide_npcs, slips, messages, sabotage}. One-shot campaign flags are consumed here.
func night_setup() -> Dictionary:
	var s := st()
	var out := {"remove_guards": [], "add_guards": [], "view_mult": 1.0, "health": -1, "hide_npcs": [], "slips": 1,
			"messages": [], "sabotage": sabotage_tonight()}
	var tn: Dictionary = s["tonight"]
	if bool(tn.get("watch_bribed", false)):
		out["remove_guards"].append("Rynek patrol B")
		out["messages"].append("Rynek patrol B is drinking the sergeant's barrel tonight.")
	if _consume("watch_in_kazimierz"):
		out["remove_guards"].append("Rynek patrol A")
		out["messages"].append("Patrol A has gone to turn out the cellars of Kazimierz.")
	if bool(tn.get("urchin_sweep", false)):
		if not "Rynek patrol A" in out["remove_guards"]:
			out["remove_guards"].append("Rynek patrol A")
		out["messages"].append("The urchins were right: patrol A keeps to the north side, away from you.")
	if bool(tn.get("urchin_sweep_lie", false)):
		out["add_guards"].append({"name": "Rynek patrol C", "wps": [[-20, 0, -12], [18, 0, -13], [18, 0, -20], [-20, 0, -20]]})
		out["messages"].append("The urchins lied: there is an extra patrol on the north side.")
	if flag("corporal_disgraced"):
		out["remove_guards"].append("St Mary's post")
	if flag("informer_arrested"):
		out["hide_npcs"].append("informer")
	if _consume("watch_distrust"):
		out["view_mult"] = float(out["view_mult"]) * 0.9
	if lever("almanac"):
		out["view_mult"] = float(out["view_mult"]) * 0.9
	if _consume("flogged"):
		out["health"] = 1
		out["messages"].append("Your back is raw from the whipping post. One blow will finish you tonight.")
	if flag("rota_copied"):
		out["slips"] = int(out["slips"]) + 1
	if bool(tn.get("extra_slip", false)):
		out["slips"] = int(out["slips"]) + 1
	for sb in out["sabotage"]:
		if str(sb["kind"]) == "sanctuary":
			out["slips"] = 0
		add_grievance(str(sb["faction"]), -25)
	return out


func _consume(f: String) -> bool:
	if flag(f):
		set_flag(f, false)
		st()["consumed"][f] = GameState.day
		return true
	return false


## An event outcome at night (scripts/mission/events.gd).
func record_event(eid: String, outcome: String, text: String) -> void:
	(st()["events"] as Array).append({"night": GameState.day, "id": eid, "outcome": outcome, "text": text})


func note_heard(_rid: String) -> void:
	changed.emit()


# ------------------------------------------------------------------ dawn

func _on_mission_ended(success: bool, _summary: String) -> void:
	if GameState.campaign.is_empty() and GameState.origin_id == "":
		return
	var s := st()
	var lines: Array = []
	var mid := Mission.mission_id
	var n := night()
	var is_arc := not ended() and mid != "" and mid == mission_for_night(n)
	rumours.from_flags(Mission.flags)
	var md: Dictionary = Mission.data
	# capture and death bookkeeping (the mission runner sets these flags)
	if Mission.has_flag("captured"):
		s["captures"] = int(s.get("captures", 0)) + 1
		s["captures_total"] = int(s.get("captures_total", 0)) + 1
	elif success:
		s["captures"] = 0
	if is_arc:
		(s["results"] as Array).append({"night": GameState.day - 1, "mission": mid, "success": success, "approach": Mission.approach})
		var ce: Dictionary = md.get("campaign", {})
		apply_effects(ce.get("success" if success else "failure", {}), lines)
		if success:
			apply_effects(ce.get("approach", {}).get(Mission.approach, {}), lines)
			var inst := str(arc_entry(n).get("institution", ""))
			if inst != "":
				lines.push_front("Taken from the occupier: %s." % inst)
		for fl in ce.get("flags", {}):
			if Mission.has_flag(str(fl)):
				apply_effects(ce["flags"][fl], lines)
		for oid in ce.get("objectives", {}):
			if Mission.is_done(str(oid)):
				apply_effects(ce["objectives"][oid], lines)
		s["night"] = n + 1
	for e in s["events"]:
		if int(e.get("night", 0)) == GameState.day - 1 and str(e.get("text", "")) != "":
			lines.append("In the night: " + str(e["text"]))
	s["failed_row"] = 0 if success else int(s.get("failed_row", 0)) + 1
	var hanged := Mission.has_flag("captured") and int(s.get("captures", 0)) >= 3 and GameState.crackdown >= 60
	if Mission.has_flag("died") or hanged:
		fall("hanged at the Town Hall after a third arrest" if hanged else str(Mission.flags.get("death_cause", "killed in the night")), lines, "dead")
	elif Mission.has_flag("taken"):
		fall("taken to the Wawel cells for good", lines, "taken")
	elif int(s.get("captures", 0)) >= 2:
		s["trial"] = true
		lines.append("Two arrests in a row: the magistrate will pass sentence this morning.")
	_dawn_grievance(lines)
	rumours.night_step(lines)
	if not succession_pending():
		_faith_check(lines)
	s["tonight"] = {}
	s["lead"] = ""
	if is_arc:
		_check_end(success, mid, lines)
	s["dawn"] = lines
	changed.emit()


func _check_end(success: bool, mid: String, lines: Array) -> void:
	if not bool(arc_entry(night() - 1).get("finale", false)) or ended():
		return
	var _unused := [success, mid]
	for e in db.get("endings", []):
		if cond_all(e.get("if", [])):
			st()["ended"] = str(e["id"])
			st()["ending"] = {"title": str(e.get("title", "")), "text": str(e.get("text", ""))}
			lines.append("The end of the winter: %s." % e.get("title", ""))
			return


func ending() -> Dictionary:
	return st().get("ending", {})


func dawn_lines() -> Array:
	return st().get("dawn", [])


# ------------------------------------------------------------------ pacing estimate

func _npc_positions() -> void:
	if not _npc_pos.is_empty():
		return
	var f := FileAccess.open("res://data/npcs.json", FileAccess.READ)
	var d: Variant = JSON.parse_string(f.get_as_text()) if f else null
	if d is Dictionary:
		for e in d.get("npcs", []):
			var p: Array = e.get("pos", [0, 0, 0])
			_npc_pos[str(e.get("id", ""))] = Vector2(float(p[0]), float(p[2]))


func _mark_pos(md: Dictionary, mark: Variant) -> Variant:
	if mark is Array and (mark as Array).size() >= 2:
		return Vector2(float(mark[0]), float(mark[1]))
	var ms := str(mark)
	if ms.begins_with("actor:"):
		var id := ms.trim_prefix("actor:")
		for e in md.get("npcs", []):
			if str(e.get("id", "")) == id:
				var p: Array = e.get("pos", [0, 0, 0])
				return Vector2(float(p[0]), float(p[2]))
		if _npc_pos.has(id):
			return _npc_pos[id]
	return null


static func _words(t: String) -> int:
	return t.split(" ", false).size()


## Estimated minutes for mission `id` played by the route `route` (default: its smoke route). {total, parts}
func estimate_mission(id: String) -> Dictionary:
	_npc_positions()
	var md := Mission.mission_data(id)
	var es: Dictionary = db.get("estimate", {})
	var route := str(md.get("smoke", {}).get("approach", ""))
	var objs: Array = md.get("approaches", {}).get(route, {}).get("objectives", md.get("objectives", []))
	var marks: Dictionary = md.get("stealth", {}).get("map_marks", {})
	var sp: Array = md.get("estimate_spawn", es.get("spawn", [-27, -27]))
	var at := Vector2(float(sp[0]), float(sp[1]))
	var dist := 0.0
	var req := 0
	var opt := 0
	for o in objs:
		if bool(o.get("optional", false)):
			opt += 1
			continue
		req += 1
		var mp: Variant = _mark_pos(md, marks.get(str(o["id"]), null))
		if mp != null:
			dist += at.distance_to(mp)
			at = mp
	var travel := dist * float(es.get("detour", 1.6)) / float(es.get("walk_mps", 2.2)) / 60.0
	var words := 0
	var nodes: Dictionary = md.get("dialogue", {})
	for nid in md.get("smoke", {}).get("nodes", nodes.keys() if route == "" else []):
		var nd: Dictionary = nodes.get(nid, {})
		for l in nd.get("lines", []):
			words += _words(str(l[1]))
		for c in nd.get("choices", []):
			words += _words(str(c.get("text", "")))
	var dialogue := float(words) / float(es.get("read_wpm", 150))
	var brief := float(_words(str(md.get("briefing", "")))) / float(es.get("brief_wpm", 170))
	var wait := 0.0
	var need_clock := str(md.get("smoke", {}).get("clock", ""))
	if need_clock != "":
		wait = maxf(0.0, (GameState.parse_clock(need_clock) - GameState.NIGHT_START_MINUTES) / 60.0 - travel - dialogue)
	var stealth := req * float(es.get("stealth_per_objective", 1.4)) + opt * float(es.get("optional_minutes", 1.2))
	var total := travel + dialogue + brief + wait + stealth
	return {"total": total, "travel": travel, "dialogue": dialogue, "brief": brief, "wait": wait, "stealth": stealth, "metres": dist, "route": route}


## The whole arc: every night by its smoke route (the three-road first mission counted once), events, leads,
## the day phases. {nights, total, per_night: [[id, minutes]]}
func estimate_minutes() -> Dictionary:
	var es: Dictionary = db.get("estimate", {})
	var per: Array = []
	var total := 0.0
	var ap := int(db.get("actions_per_day", 2)) + 1
	for e in arc():
		var n := int(e.get("night", 0))
		var mid := str((e.get("options", [{}]) as Array)[0].get("mission", ""))
		var m: float = estimate_mission(mid)["total"]
		m += float(es.get("events_per_night", 2)) * float(es.get("event_minutes", 1.0))
		if n > 1:
			m += float(es.get("lead_minutes", 2.0))
		var day_words := _words(str(e.get("teaser", ""))) + 120        # rumours, leads and actions listed on the day panel
		m += float(day_words) / float(es.get("brief_wpm", 170)) + ap * float(es.get("day_choice_minutes", 0.6))
		per.append([mid, snappedf(m, 0.1)])
		total += m
	return {"nights": arc().size(), "total": total, "per_night": per}
