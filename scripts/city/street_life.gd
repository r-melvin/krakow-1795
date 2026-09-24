extends Node3D
## Night life and crime on the Rynek (docs/GDD.md "Night life and crime"; tables in data/street_life.json).
## Instanced by dressing.gd after the dressing, so its few props (the brothel's red lantern and bench, the pillory,
## stocks, whipping post and gallows when those models exist) are baked into the navmesh with the rest.
##
## Persistent scenes (spawned once the population exists):
##   brothel      a door on the west row (portal 12) with a red lantern, two women calling out, a madam who sells
##                rooms and gossip (dialogue), a doorman on a bench, a pimp, a stream of customers (soldiers openly)
##   punishment   a prisoner in the pillory (and one in the stocks) by the Town Hall with placards, jeers and
##                charity, a soldier on guard; the gallows outside the rows; a flogging once a night
##   poverty      veteran beggars, a beggar woman freezing in a doorway (collected by a cart before dawn),
##                children scavenging behind the stalls, a soup line at St Adalbert's
##   drunks       3-5 after 22:00: stagger, sing, relieve themselves, fall asleep, accost people, get moved on
## Transient events (never more than `max_events` at once, rolled by clock hour and crackdown): fights, cutpurses,
## muggings, a burglar, a fence at a cellar door, arrests, a press gang, soldiers harassing a pedlar or a Uniate
## priest, a firewood requisition, posters burned, the curfew beating of a drunk, a brawl over a brothel bill,
## the Visitation (a raid on the brothel at crackdown >= 40, once a night).
##
## Actors: crowd-type extras are spawned through population.spawn_entry (so they count for the player's crowd
## blending) and driven with the npc.gd storyline API (claim / script_goto / script_play); people the player can
## fight (thugs, cutpurses, drunks) are `Tough`s (npc.gd + is_unaware_of / knock_down hooks, group "takedown"):
## player.gd's attack treats an `is_unaware_of() == true` non-guard as a takedown, which is how one swing fells a
## thug. Parked actors are pooled (hidden, processing off) and reused.
##
## Talk: people carry a `personality` and the player's choices a `tone`; a toned choice is answered from the speaker's
## own responses, else data responses[personality][tone] (lines, effect, next). The bard at the kawiarnia, the
## madam, doorman, pimp, drunks, the man in the pillory, the thugs and a riot's ringleader all talk this way.
## Riot: riot(centre, intensity, cause) (signals riot_started / riot_peak / riot_ended). Fire: fire.gd, Fire.ignite(pos).
##
## Hooks: Mission.flags "brothel_room" (true while the paid room hides the player, 20 s), "brothel_room_used",
## "gossip_officer" / "gossip_rota" / "gossip_informer", "saw_burglar", "posters_burned", "flogging_seen";
## group "crowd" (onlookers of fights and punishments, the soup line: stealth blending); Mission.message lines go
## to the journal log. Guards are drawn to fights with guard.investigate(pos) and the watch's emit_sound(); we do
## not call guard.witness(), which pins the *player's* position and raises the alarm on them.
##
## `-- --smoke` forces every event once on the first night and prints `[smoke] street_life ...`;
## `-- --street-shot=/dir` (windowed) stages the scenes and saves close-ups.

const NpcScript := preload("res://scripts/npc/npc.gd")
const Walker := preload("res://scripts/npc/walker.gd")
const FlickerLight := preload("res://scripts/city/flicker.gd")
const DialogueScript := preload("res://scripts/mission/dialogue.gd")
const InteractableScript := preload("res://scripts/mission/interactable.gd")
const Perception := preload("res://scripts/stealth/perception.gd")
const Props := preload("res://scripts/mission/props.gd")
const FireScript := preload("res://scripts/city/fire.gd")
const DATA_PATH := "res://data/street_life.json"

signal riot_started(centre: Vector3, intensity: float, cause: String)
signal riot_peak(mob: int)
signal riot_ended(outcome: String)
const FRONT := 4.0


## Someone the player can knock down with an ordinary swing while `fair` (a fight they are in), or from behind.
## `soft`: the swing only shoves (drunks). `on_felled(self)` runs either way.
class Tough extends "res://scripts/npc/npc.gd":
	var fair := false
	var soft := false
	var on_felled: Callable

	func is_unaware_of(p: Node3D, dist: float = 1.5) -> bool:
		if p == null or not visible:
			return false
		var to := p.global_position - global_position
		to.y = 0.0
		if fair or soft:
			return to.length() <= dist + 0.35
		var fwd := -global_transform.basis.z
		fwd.y = 0.0
		return to.length() <= dist and rad_to_deg(fwd.angle_to(to)) > 110.0

	func knock_down(secs: float) -> void:
		if soft:
			if on_felled.is_valid():
				on_felled.call(self)
			return
		super(secs)
		if on_felled.is_valid():
			on_felled.call(self)


var D: Dictionary = {}
var portals: Array = []
var district: Node
var pop: Node
var watch: Node
var interiors: Node
var _rng := RandomNumberGenerator.new()
var _lanes: Array = []            ## [a: Vector3, b: Vector3] carriage lane segments
var _lanterns: Array = []         ## street lantern positions
var _pool: Dictionary = {}        ## model key -> parked actors
var _serial := 0
var _running: Array = []          ## transient events in progress
var _next: Dictionary = {}        ## event kind -> clock minute of its next roll
var _smoke := false
var _shot_dir := ""
var _ts := 1.0                    ## scripted pauses x this (smoke compresses them)
var _instant := false             ## approaches teleport (smoke / shots)
var _stat: Dictionary = {"drunks": 0, "fights": 0, "cutpurse": "none", "mugging": "none", "raid": false}
var _anchors: Dictionary = {}     ## shot name -> [target (Node3D | Vector3), camera offset, look height]

# brothel
var brothel_door := Vector3.ZERO
var _b_out := Vector3.ZERO        ## facade normal at the brothel
var _b_rot := 0.0
var _women: Array = []            ## static figures
var _madam: Node3D
var _doorman: Node3D
var _pimp
var _customers: Array = []
var _raid_on := false
var _raid_done := false
var _raid_at := -1.0
var _gossip_told: Array = []
var _room_left := 0.0
var _room_spot: Node3D

# drunks
var _drunks: Array = []
var _sleep_spots: Dictionary = {} ## bench index -> drunk
var _benches: Array = []          ## [pos, rot] of benches along the square (dressing.gd)

# punishment / poverty
var _prisoners: Array = []
var _flog_done := false
var _flog_at := -1.0
var _beggars: Array = []
var _freezer: Node3D
var _frozen := false
var _collected := false
var _poster: Node3D

# dialogue
var _dlg: CanvasLayer
var _dlg_graph: Dictionary = {}
var _dlg_vars: Dictionary = {}
var _dlg_names: Dictionary = {}
var _dlg_choices: Array = []
var _dlg_node := ""
var _dlg_handler: Callable
var _dlg_personality := ""        ## the speaker's personality (responses[personality][tone])
var _dlg_who: Node3D              ## the speaker's node (effects: slap, knife, leave)
var _dlg_resp: Dictionary = {}    ## the speaker's own responses by tone, before the personality table
var _dlg_after := ""              ## node to go to once a toned response has been read
var _gossip_free := false
var _mug_state: Dictionary = {}
var _bard: Node3D
var fire: Node3D                  ## scripts/city/fire.gd (Fire.ignite)
var riot_state: Dictionary = {}   ## {on, centre, intensity, cause, t, mob, rioters, leader, peak, outcome}
var _player_mug_next := 0.0
var _beg_cd := 0.0
var _saw_burglar := false
var _sim_boost := 1.0
var _shot_only: PackedStringArray = []     ## `--street-shot-only=a,b`: just these shots

static var _smoked := false
static var _shot_done := false
static var _static_shots := false


# ================================================================== setup

func _ready() -> void:
	name = "StreetLife"
	_rng.randomize()
	var f := FileAccess.open(DATA_PATH, FileAccess.READ)
	if f:
		var parsed: Variant = JSON.parse_string(f.get_as_text())
		if parsed is Dictionary:
			D = parsed
	if D.is_empty():
		push_warning("StreetLife: cannot read %s" % DATA_PATH)
		return
	var par := get_parent()
	if par and "portals" in par:
		portals = par.get("portals")
	district = par.get_parent() if par else null
	var args := OS.get_cmdline_user_args()
	_smoke = "--smoke" in args
	for a in args:
		if a.begins_with("--street-shot="):
			_shot_dir = a.trim_prefix("--street-shot=")
		if a.begins_with("--street-shot-only="):
			_shot_only = a.trim_prefix("--street-shot-only=").split(",")
	_read_lanes()
	_build_static()
	_setup.call_deferred()


func _read_lanes() -> void:
	var f := FileAccess.open("res://data/npcs.json", FileAccess.READ)
	if f == null:
		return
	var data: Variant = JSON.parse_string(f.get_as_text())
	if not data is Dictionary:
		return
	var posts: Dictionary = data.get("posts", {})
	for e in data.get("npcs", []):
		if not (e is Dictionary and e.has("route")):
			continue
		var pts: Array = []
		for r in e["route"]:
			if posts.has(str(r)):
				pts.append(_v(posts[str(r)]["pos"]))
		for i in pts.size():
			_lanes.append([pts[i], pts[(i + 1) % pts.size()]])
		break


func _setup() -> void:
	if not is_inside_tree() or district == null:
		return
	pop = district.get_node_or_null("Population")
	watch = district.get("watch")
	interiors = district.get_node_or_null("Interiors")
	_lanterns.clear()
	var lp: Variant = district.get("_lanterns")
	if lp is Array:
		for e in lp:
			_lanterns.append(e[1])
	if _lanterns.is_empty():
		for p in [[-22, 0, -22], [22, 0, -22], [-22, 0, 22], [16, 0, 24], [0, 0, -24], [-6, 0, 24], [-24, 0, 0], [24, 0, 4], [5, 0, 9], [-5, 0, -9]]:
			_lanterns.append(_v(p))
	fire = FireScript.new()
	add_child(fire)
	_dlg = DialogueScript.new()
	_dlg.name = "StreetDialogue"
	add_child(_dlg)
	_dlg.choice_made.connect(_on_dlg_choice)
	_dlg.finished.connect(_on_dlg_finished)
	_setup_brothel_people()
	_setup_punishment_people()
	_setup_poverty()
	_setup_bard()
	if _smoke:
		print("[smoke] street_life night set up: women=%d prisoners=%d beggars=%d gallows=%s" % [_women.size(), _prisoners.size(), _beggars.size(), _prop_state("gallows")])
	var raid: Dictionary = D["brothel"]["raid"]
	_raid_at = _rand_clock(raid["at"])
	_flog_at = GameState.parse_clock(str(D["punishment"]["flogging"]["at"]))
	_brothel_loop()
	_customer_loop()
	_pimp_loop()
	_jeer_loop()
	_scavenger_loop()
	_soup_loop()
	if (_smoke or _shot_dir != "") and not _smoked:
		_smoked = true
		_smoke_main.call_deferred()
	elif _shot_dir != "" and not _static_shots and DisplayServer.get_name() != "headless":
		_static_shots = true          # a later night: the standing scenes again, before anything happens to them
		_later_shots.call_deferred()


# ------------------------------------------------------------------ static props (before the navmesh bake)

func _build_static() -> void:
	if portals.size() > int(D["brothel"]["portal"]):
		var b: Dictionary = D["brothel"]
		var i := int(b["portal"])
		_b_rot = float(portals[i][2])
		_b_out = Vector3(sin(_b_rot), 0, cos(_b_rot))
		brothel_door = _wp(i, float(b["door_lx"]), 0.0, 0.0)
		# the red lantern over the door, and its flickering light
		var lan := Assets.place(self, "wall_lantern", _wp(i, float(b["lantern_lx"]), float(b["lantern_y"]), 0.0), _b_rot)
		var l := FlickerLight.new()
		l.amount = 0.2
		l.speed = 5.0
		l.position = _wp(i, float(b["lantern_lx"]), float(b["lantern_y"]) - 0.45, 0.62)
		l.light_color = Color(1.0, 0.1, 0.06)
		l.light_energy = 4.5
		l.omni_range = 5.5
		l.omni_attenuation = 0.9
		l.light_volumetric_fog_energy = 1.4
		add_child(l)
		l.add_to_group("flame_lights")
		if lan:
			_red_glass(lan)
			# and a red pane of our own in the cage, so it reads even under the street lantern
			var pane := _prim_box(Vector3(0.215, 0.3, 0.215), Color(0.8, 0.05, 0.03))
			var pm := pane.material_override as StandardMaterial3D
			pm.emission_enabled = true
			pm.emission = Color(1.0, 0.08, 0.04)
			pm.emission_energy_multiplier = 6.0
			pane.position = lan.position + Basis(Vector3.UP, _b_rot) * Vector3(0, -0.42, 0.55)
			pane.rotation.y = _b_rot
			add_child(pane)
		var bench_pos := _wp(i, float(b["bench_lx"]), 0.0, float(b["bench_out"]))
		if _clear_of_lanes(bench_pos):
			Assets.place(self, "bench_wood", bench_pos, _b_rot)
	var pu: Dictionary = D["punishment"]
	# the pillory is placed in _setup: the outer-city pass may already have put one before the Town Hall
	_place_opt("stocks", pu["stocks"], "")
	_place_opt("whipping_post", pu["flogging"], "hitching_post", "post")
	_place_opt("gallows", pu["gallows"], "")
	# a bowl for each beggar, a barrel for the soup
	for bg in D["poverty"]["beggars"]:
		var p := _v(bg["pos"])
		var bowl := _prim_cyl(0.11, 0.07, Color(0.32, 0.24, 0.16))
		bowl.position = p + Vector3(sin(float(bg["rot"]) + PI), 0.035, cos(float(bg["rot"]) + PI)) * Vector3(0.55, 1, 0.55)
		add_child(bowl)
	var s: Dictionary = D["poverty"]["soup"]
	var sp := _v(s["server"]) + Vector3(0.0, 0, -0.9)
	if _clear_of_lanes(sp):
		Assets.place(self, "barrel", sp, 0.4)


## Place a punishment model if the buildings pass has made it (else `fallback`, or nothing). Remembers the node.
func _place_opt(asset: String, e: Dictionary, fallback: String, key := "pos") -> void:
	var p := _v(e[key])
	if not _clear_of_lanes(p):
		return
	var use := asset if ResourceLoader.exists("res://assets/models/%s.glb" % asset) else fallback
	if use == "":
		return
	var n := Assets.place(self, use, p, float(e.get("rot", 0.0)))
	if n:
		n.set_meta("sl_asset", asset)
		n.set_meta("sl_real", use == asset)
		e["_node"] = n


# ================================================================== helpers

static func _v(a: Variant) -> Vector3:
	if a is Vector3:
		return a
	return Vector3(float(a[0]), float(a[1]), float(a[2]))


func _wp(i: int, lx: float, y: float, out: float) -> Vector3:
	var p: Array = portals[i]
	var pos: Vector3 = (p[1] as Vector3) + Basis(Vector3.UP, float(p[2])) * Vector3(lx, 0.0, FRONT + out)
	pos.y = y
	return pos


func _door_of(i: int, out := 0.9) -> Vector3:
	var asset: String = portals[i][0]
	var lx := -2.0 if asset in ["tenement_b", "tenement_e"] else 0.0
	return _wp(i, lx, 0.0, out)


func _clear_of_lanes(p: Vector3) -> bool:
	var clear := float(D.get("lane_clearance", 3.0))
	for s in _lanes:
		var a: Vector3 = s[0]
		var b: Vector3 = s[1]
		var ab := Vector2(b.x - a.x, b.z - a.z)
		var ap := Vector2(p.x - a.x, p.z - a.z)
		var t := clampf(ap.dot(ab) / maxf(ab.length_squared(), 0.001), 0.0, 1.0)
		if (ap - ab * t).length() < clear:
			return false
	return true


func _dark(p: Vector3) -> bool:
	var d := float(D.get("lantern_dark_dist", 12.0))
	for l in _lanterns:
		if Vector2(p.x - l.x, p.z - l.z).length() < d:
			return false
	return true


func _clock() -> float:
	return GameState.clock_minutes


func _hour() -> int:
	return (int(_clock()) / 60) % 24


func _between(from: String, until: String) -> bool:
	var c := _clock()
	return c >= GameState.parse_clock(from) and c < GameState.parse_clock(until)


func _rand_clock(r: Variant) -> float:
	if r is Array:
		return randf_range(GameState.parse_clock(str(r[0])), GameState.parse_clock(str(r[1])))
	return GameState.parse_clock(str(r))


func _table(rows: Variant, fallback := 1.0) -> float:
	var v := fallback
	if rows is Array:
		for r in rows:
			if GameState.crackdown >= float(r[0]):
				v = float(r[1])
	return v


func _prob(kind: String) -> float:
	var e: Dictionary = D["events"].get(kind, {})
	var hours: Dictionary = e.get("hours", {})
	var p := float(hours.get(str(_hour()), hours.get("*", 0.0)))
	return p * _table(e.get("crackdown", [])) * _sim_boost


func _range(r: Variant) -> float:
	return _rng.randf_range(float(r[0]), float(r[1])) if r is Array else float(r)


func _pick(key: String) -> Dictionary:
	var l: Array = D["lines"].get(key, [])
	return l[_rng.randi() % l.size()] if not l.is_empty() else {}


func _pickf(list: Array) -> Variant:
	return list[_rng.randi() % list.size()] if not list.is_empty() else null


func _player() -> Node3D:
	return get_tree().get_first_node_in_group("player") as Node3D


func _sleep(secs: float) -> void:
	await get_tree().create_timer(maxf(secs * _ts, 0.02), false).timeout


func _frames(n: int) -> void:
	for i in n:
		await get_tree().physics_frame


func _ok(a) -> bool:
	return a != null and is_instance_valid(a) and a.is_inside_tree()


func _flat(a: Vector3, b: Vector3) -> float:
	return Vector2(a.x - b.x, a.z - b.z).length()


static func _yaw_to(from: Vector3, to: Vector3) -> float:
	var d := to - from
	return atan2(-d.x, -d.z)


func _msg(key: String, subs: Dictionary = {}, secs := 4.0) -> void:
	var t := str(D.get("messages", {}).get(key, key))
	for k in subs:
		t = t.replace("{%s}" % k, str(subs[k]))
	Mission.message.emit(t, secs)


## The long journal line for a scene only when the player is close to it (within `r` m), once per key.
func _msg_near(key: String, at: Vector3, r := 6.0, subs: Dictionary = {}, secs := 4.0) -> bool:
	var p := _player()
	if p == null or _stat.has("told_" + key) or _flat(p.global_position, at) > r:
		return false
	_stat["told_" + key] = true
	_msg(key, subs, secs)
	return true


func _flag(name: String, v: Variant = true) -> void:
	Mission.set_flag(name, v)


# ------------------------------------------------------------------ speech: the original, the gloss beneath (Walker.speech)

func bubble(node, line: Variant, secs := 3.0) -> void:
	if node == null or not is_instance_valid(node) or not (node is Node3D) or line == null:
		return
	var text := ""
	var gloss := ""
	if line is Dictionary:
		text = str(line.get("text", ""))
		gloss = str(line.get("gloss", ""))
	else:
		text = str(line)
	if text == "":
		return
	if gloss != "":
		text += "\n" + (gloss if gloss.begins_with("(") else "(" + gloss + ")")
	Walker.speech(node, text, secs)     # the shared budget: range, count, gloss distance, walls


func say(node, key: String, secs := 3.4) -> void:
	bubble(node, _pick(key), secs)
	Sfx.say_hook(node, key)      # the snore, the drum, the cry under the bubble (data/audio.json "say")


## A placard (board + painted text with its gloss) hung in front of a figure or on a post.
func _placard(parent: Node3D, line: Dictionary, local: Vector3, yaw := 0.0) -> Node3D:
	var root := Node3D.new()
	root.name = "Placard"
	root.position = local
	root.rotation.y = yaw
	var board := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = Vector3(0.62, 0.3, 0.025)
	board.mesh = bm
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.72, 0.62, 0.45)
	mat.roughness = 0.9
	board.material_override = mat
	root.add_child(board)
	var t := Label3D.new()
	t.text = str(line.get("text", "")) + "\n(" + str(line.get("gloss", "")) + ")"
	t.font_size = 26
	t.pixel_size = 0.0028
	t.modulate = Color(0.12, 0.07, 0.04)
	t.outline_size = 0
	t.position = Vector3(0, 0, -0.016)
	t.rotation.y = PI
	t.width = 210
	t.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	root.add_child(t)
	parent.add_child(root)
	return root


func _prim_cyl(r: float, h: float, col: Color) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var cm := CylinderMesh.new()
	cm.top_radius = r
	cm.bottom_radius = r * 0.8
	cm.height = h
	mi.mesh = cm
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	m.roughness = 0.85
	mi.material_override = m
	return mi


func _prim_box(size: Vector3, col: Color) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	m.roughness = 0.95
	mi.material_override = m
	return mi


## The lantern's glass (material "gold", emissive) turned red.
func _red_glass(n: Node) -> void:
	var red := StandardMaterial3D.new()
	red.albedo_color = Color(0.85, 0.08, 0.05)
	red.emission_enabled = true
	red.emission = Color(1.0, 0.1, 0.05)
	red.emission_energy_multiplier = 7.0
	for c in n.find_children("*", "MeshInstance3D", true, false):
		var mi := c as MeshInstance3D
		if mi.mesh == null:
			continue
		for i in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(i)
			if m and m.resource_name == "gold":
				mi.set_surface_override_material(i, red)


func _strip_collision(n: Node) -> void:
	for c in n.find_children("*", "CollisionObject3D", true, false):
		c.queue_free()


# ------------------------------------------------------------------ static figures (no physics)

func _fig(models: Array, pos: Vector3, yaw: float, clip := "idle") -> Node3D:
	var name := NpcScript.first_existing(PackedStringArray(models))
	var f: Node3D = Assets.character(name) if name != "" else null
	if f == null:
		return null
	f.position = pos
	f.rotation.y = yaw
	add_child(f)
	Assets.play(f, clip)
	if f.has_meta("anim"):
		var ap: AnimationPlayer = f.get_meta("anim")
		if ap.current_animation != "":
			ap.seek(_rng.randf() * ap.current_animation_length, true)
	return f


# ------------------------------------------------------------------ actors (npc.gd bodies, pooled)

func _actor(models: Array, pos: Vector3, yaw: float, tough := false):
	var key := ("T" if tough else "E") + ":" + ",".join(PackedStringArray(models))
	var list: Array = _pool.get(key, [])
	var a = null
	while not list.is_empty() and a == null:
		var c = list.pop_back()
		if _ok(c):
			a = c
	if a != null:
		a.process_mode = Node.PROCESS_MODE_INHERIT
		a.set_physics_process(true)
		a.global_position = pos
		a.rotation = Vector3(0, yaw, 0)
		a.velocity = Vector3.ZERO
		a.reset_physics_interpolation()
		a.claim()
	else:
		_serial += 1
		var id := "sl_%d" % _serial
		if tough or pop == null:
			a = Tough.new() if tough else NpcScript.new()
			a.npc_id = id
			a.candidates = PackedStringArray(models)
			a.behaviour = "stand"
			a.facing = yaw
			a.position = pos
			a.role = "street life"
			add_child(a)
		else:
			a = pop.spawn_entry({"id": id, "model": models, "pos": [pos.x, pos.y, pos.z], "facing": yaw,
					"behaviour": "stand", "role": "street life"})
		if a == null:
			return null
		a.claim()
	a.set_meta("sl_key", key)
	a.speed = 1.1
	a.add_to_group("street_life")
	if a is Tough:
		a.fair = false
		a.soft = false
		a.on_felled = Callable()
	var fig: Node3D = a.get("_figure")
	if fig:
		Assets.clear_action(fig)
		fig.rotation = Vector3.ZERO      # the pivot; the glTF inside is already turned
		fig.position = Vector3.ZERO
	a.script_play("idle")
	return a


func _park(a) -> void:
	if not _ok(a):
		return
	if a.is_downed():
		a._get_up()
	a.claim()
	var fig: Node3D = a.get("_figure")
	if fig:
		Assets.clear_action(fig)
		fig.rotation = Vector3.ZERO      # the pivot; the glTF inside is already turned
		fig.position = Vector3.ZERO
		for c in fig.get_children():
			if c.has_meta("sl_prop"):
				c.queue_free()
	for c in a.get_children():
		if c.has_meta("sl_prop") or String(c.name).begins_with("SpeechBubble"):
			c.queue_free()
	for g in ["crowd", "takedown", "street_life"]:
		if a.is_in_group(g):
			a.remove_from_group(g)
	a.rotation = Vector3.ZERO
	a._set_hidden(true)
	a.global_position = Vector3(-44, 0, -44)
	a.process_mode = Node.PROCESS_MODE_DISABLED
	var key := str(a.get_meta("sl_key", ""))
	if not _pool.has(key):
		_pool[key] = []
	_pool[key].append(a)


## Walk (or run) to `p`; returns when there (true) or after `timeout` s. `_instant` teleports unless `walk`.
func _goto(a, p: Vector3, run := false, timeout := 30.0, walk := false) -> bool:
	if not _ok(a):
		return false
	if _instant and not walk:
		a.global_position = p
		a.reset_physics_interpolation()
		a.script_goto(null)
		a.script_arrived = true
		await get_tree().physics_frame
		return _ok(a)
	a.script_goto(p, 0.0, run)
	var t := 0.0
	while _ok(a) and not a.script_arrived and t < timeout:
		await get_tree().physics_frame
		t += get_physics_process_delta_time()
	return _ok(a) and a.script_arrived


func _halt(a, clip := "idle", face: Variant = null) -> void:
	if not _ok(a):
		return
	a.script_goto(null)
	a.script_arrived = true
	a.script_play(clip)
	if face != null:
		a.script_face(face)


func _fig_of(n) -> Node3D:
	if n is CharacterBody3D:
		return n.get("_figure")
	return n as Node3D


func _act(n, clip: String, hold := false) -> float:
	if not _ok(n):
		return 0.0
	Sfx.act_hook(n, clip)        # blows landing, falls, stumbles (data/audio.json "acts")
	return Assets.play_action(_fig_of(n), clip, 1.0, hold)


func _face_now(n, p: Vector3) -> void:
	if not _ok(n):
		return
	(n as Node3D).rotation.y = _yaw_to((n as Node3D).global_position, p)
	if n is CharacterBody3D:
		n.script_face(p)


## Doors, alley mouths and exits people come from and go to.
func _entries() -> Array:
	var out: Array = []
	for i in portals.size():
		out.append(_door_of(i, 1.0))
	for e in D["crime"]["exits"]:
		out.append(_v(e))
	return out


func _nearest(list: Array, p: Vector3, min_d := 0.0) -> Vector3:
	var best := p
	var bd := INF
	for q in list:
		var d := _flat(q, p)
		if d >= min_d and d < bd:
			bd = d
			best = q
	return best


func _exit_near(p: Vector3) -> Vector3:
	var ex: Array = []
	for e in D["crime"]["exits"]:
		ex.append(_v(e))
	return _nearest(ex, p)


## Where a newcomer for an event at `p` comes from: a door or exit not too close, the nearest such.
func _spawn_near(p: Vector3, min_d := 6.0) -> Vector3:
	if _instant:
		var a := _rng.randf() * TAU
		return _nav_point(p + Vector3(cos(a), 0, sin(a)) * 2.0)
	return _nearest(_entries(), p, min_d)


func _nav_point(p: Vector3) -> Vector3:
	var map := get_world_3d().navigation_map
	if NavigationServer3D.map_get_iteration_id(map) == 0:
		return p
	var q := NavigationServer3D.map_get_closest_point(map, p)
	return Vector3(q.x, 0.0, q.z)


func _reachable(p: Vector3, from := Vector3(0, 0, -20)) -> bool:
	var map := get_world_3d().navigation_map
	if NavigationServer3D.map_get_iteration_id(map) == 0:
		return true
	var path := NavigationServer3D.map_get_path(map, from, p, true)
	return path.size() > 0 and _flat(path[-1], p) < 1.5


func _leave(a, run := false) -> void:
	if not _ok(a):
		return
	var home := _nearest(_entries(), (a as Node3D).global_position, 4.0)
	await _goto(a, home, run, 40.0, true)
	_park(a)


# ------------------------------------------------------------------ townsfolk already on the square

func _excluded_ids() -> Dictionary:
	var ex := {}
	if Mission.data is Dictionary:
		for id in Mission.data.get("talk", {}):
			ex[str(id)] = true
		for e in Mission.data.get("npcs", []):
			ex[str(e.get("id", ""))] = true
		for id in Mission.data.get("takedown", []):
			ex[str(id)] = true
	if pop:
		for s in pop.storylines:
			if is_instance_valid(s) and s.has_method("actor_ids"):
				for id in s.actor_ids():
					ex[str(id)] = true
	return ex


func _walkers_near(p: Vector3, r: float, n: int = 99) -> Array:
	var out: Array = []
	if pop == null:
		return out
	var ex := _excluded_ids()
	for c in pop.get_children():
		if c.get_script() != NpcScript or not c.visible or c.is_inside() or c.is_downed():
			continue
		if c.has_meta("sl_busy") or c.is_in_group("street_life") or c.is_in_group("mission") or ex.has(str(c.npc_id)):
			continue
		if int(c.mode) == 3:   # SCRIPTED by a storyline
			continue
		if _flat(c.global_position, p) <= r:
			out.append(c)
	out.sort_custom(func(a, b): return _flat(a.global_position, p) < _flat(b.global_position, p))
	return out.slice(0, n)


func _borrow(w) -> void:
	w.set_meta("sl_busy", true)
	w.set_meta("sl_speed", w.speed)
	w.claim()


func _give_back(w) -> void:
	if not _ok(w):
		return
	w.remove_meta("sl_busy")
	if w.has_meta("sl_speed"):
		w.speed = float(w.get_meta("sl_speed"))
	if w.is_in_group("crowd"):
		w.remove_from_group("crowd")
	var torch: Node = w.get_node_or_null("Torch")
	if torch:
		torch.queue_free()
		w.remove_meta("torch")
	var fig: Node3D = w.get("_figure")
	if fig:
		Assets.clear_action(fig)
	w.release()


# ------------------------------------------------------------------ the watch

func _guards() -> Array:
	var out: Array = []
	for g in get_tree().get_nodes_in_group("guards"):
		if g is Node3D and g.is_visible_in_tree() and not (g.has_method("is_downed") and g.is_downed()) and Perception.same_world(g, self):
			out.append(g)
	return out


func _guard_sees(g: Node3D, p: Vector3, max_d := -1.0) -> bool:
	var eye := g.global_position + Vector3(0, 1.5, 0)
	var to := p + Vector3(0, 1.0, 0) - eye
	var vd: float = max_d if max_d > 0.0 else float(g.get("view_distance") if g.get("view_distance") != null else 14.0)
	if to.length() > vd:
		return false
	var look := -g.global_transform.basis.z
	look.y = 0.0
	look = look.normalized().rotated(Vector3.UP, float(g.get("head_yaw") if g.get("head_yaw") != null else 0.0))
	if to.length() > 4.0 and rad_to_deg(look.angle_to(Vector3(to.x, 0, to.z).normalized())) > 60.0:
		return false
	return Perception.clear_line(get_world_3d().direct_space_state, eye, p + Vector3(0, 1.0, 0), [g.get_rid()], null, true)


## A disturbance at `p`: the watch hears it (rings, hear_noise) and guards who can see it, or are close, come over.
func _disturb(p: Vector3, loudness := 0.8, kind := "fight") -> int:
	var w := watch if watch and is_instance_valid(watch) else get_tree().get_first_node_in_group("watch")
	if w:
		if w.has_method("emit_sound"):
			w.emit_sound(p, loudness, kind, false, true, true)
		elif w.has_method("sound_event"):
			w.call("sound_event", p, loudness)
	var n := 0
	for g in _guards():
		if (_guard_sees(g, p) or _flat(g.global_position, p) < 12.0) and g.has_method("investigate"):
			if not g.has_method("can_investigate") or g.can_investigate():
				g.investigate(p, 8.0, kind)
				n += 1
	return n


# ================================================================== the scheduler

func _physics_process(delta: float) -> void:
	if D.is_empty() or pop == null:
		return
	var p := _player()
	if _dlg and _dlg.is_open and p:
		p.set("_lock", maxf(float(p.get("_lock")), 0.12))
	if _room_left > 0.0:
		_room_left -= delta
		if _room_left <= 0.0:
			_flag("brothel_room", false)
			if _room_spot and is_instance_valid(_room_spot) and p and p.get("hidden_spot") == _room_spot:
				p.leave_spot()
	_tick_events()
	_tick_drunks(delta)
	_tick_clock_scenes()
	_tick_player(delta, p)


func _tick_events() -> void:
	var c := _clock()
	var mx := int(D.get("max_events", 2))
	for kind in D["events"]:
		if not _next.has(kind):
			_next[kind] = c + _range(D["events"][kind]["every"])
			continue
		if c < float(_next[kind]):
			continue
		_next[kind] = c + _range(D["events"][kind]["every"])
		if _smoke or _running.size() >= mx:
			continue
		if _rng.randf() < _prob(kind):
			start_event(kind)


## Starts a transient event. `forced` ignores the cap (smoke, scheduled punishments).
func start_event(kind: String, forced := false, opts: Dictionary = {}) -> void:
	if not forced and _running.size() >= int(D.get("max_events", 2)):
		return
	_running.append(kind)
	_stat["peak_events"] = maxi(int(_stat.get("peak_events", 0)), _running.size() if not forced else 0)
	_stat["started"] = str(_stat.get("started", "")) + kind + " "
	match kind:
		"fight": await _ev_fight(opts)
		"cutpurse": await _ev_cutpurse(opts)
		"mugging": await _ev_mugging(opts)
		"mug_player": await _ev_mug_player(opts)
		"burglar": await _ev_burglar(opts)
		"fence": await _ev_fence(opts)
		"arrest": await _ev_arrest(opts)
		"pressgang": await _ev_pressgang(opts)
		"harass": await _ev_harass(opts)
		"requisition": await _ev_requisition(opts)
		"poster": await _ev_poster(opts)
		"bill_fight": await _ev_bill_fight(opts)
		"raid": await _ev_raid(opts)
		"flogging": await _ev_flogging(opts)
		"curfew": await _ev_curfew(opts)
		"collect": await _ev_collect(opts)
		_: push_warning("StreetLife: unknown event " + kind)
	_running.erase(kind)


func _tick_clock_scenes() -> void:
	var c := _clock()
	var room := _running.size() < int(D.get("max_events", 2))
	if room and not _raid_done and _raid_at > 0.0 and c >= _raid_at and GameState.crackdown >= int(D["brothel"]["raid"]["crackdown_min"]):
		_raid_done = true
		room = false
		start_event("raid")
	if room and not _flog_done and _flog_at > 0.0 and c >= _flog_at and c < _flog_at + 90.0:
		_flog_done = true
		room = false
		start_event("flogging")
	var fz: Dictionary = D["poverty"]["freezing"]
	if not _frozen and c >= GameState.parse_clock(str(fz["freeze_at"])):
		_freeze()
	if room and _frozen and not _collected and c >= GameState.parse_clock(str(fz["collect_at"])):
		_collected = true
		start_event("collect")
	# after the curfew bell, a drunk who did not move on
	if c >= GameState.parse_clock("22:05") and not _stat.has("curfew_rolled") and not _smoke:
		_stat["curfew_rolled"] = true
		if _rng.randf() < 0.6 + GameState.crackdown / 100.0:
			get_tree().create_timer(_rng.randf_range(20.0, 90.0), false).timeout.connect(func() -> void: start_event("curfew"))


func _tick_player(delta: float, p: Node3D) -> void:
	if p == null or _smoke or _dlg.is_open or Mission.dialogue_blocking():
		return
	# a beggar asks as the player passes
	_beg_cd -= delta
	if _beg_cd <= 0.0:
		for b in _beggars:
			if _ok(b) and _flat(b.global_position, p.global_position) < 3.2:
				say(b, "beggar", 3.2)
				_beg_cd = 14.0
				break
	if _frozen and _freezer and _ok(_freezer):
		_msg_near("frozen", _freezer.global_position)
	var c := _clock()
	var cr: Dictionary = D["crime"]
	if c >= _player_mug_next and c >= GameState.parse_clock(str(cr["player_mug_after"])):
		_player_mug_next = c + float(cr["player_mug_check"])
		if _running.size() < int(D["max_events"]) and _alone_in_dark(p) and _rng.randf() < _prob("mugging") + 0.2:
			_player_mug_next = c + float(cr["player_mug_cooldown"])
			start_event("mug_player", false, {})


func _alone_in_dark(p: Node3D) -> bool:
	if p.global_position.y < -50.0 or p.get("hidden_spot") != null or not _dark(p.global_position):
		return false
	for n in get_tree().get_nodes_in_group("npcs"):
		if n.visible and not n.is_inside() and _flat(n.global_position, p.global_position) < 10.0:
			return false
	for g in _guards():
		if _flat(g.global_position, p.global_position) < 15.0:
			return false
	return true


func _player_in_crowd(p: Node3D) -> bool:
	if p == null:
		return false
	for n in get_tree().get_nodes_in_group("crowd"):
		if n is Node3D and n.visible and _flat(n.global_position, p.global_position) < 2.0:
			return true
	return pop != null and pop.crowd_count(p.global_position, Vector3.ZERO, 2.0) >= 2


# ================================================================== the brothel

func _setup_brothel_people() -> void:
	if brothel_door == Vector3.ZERO:
		return
	var b: Dictionary = D["brothel"]
	var i := int(b["portal"])
	var face := _b_rot + PI
	for w in b["women"]:
		var f := _fig(w["models"], _wp(i, float(w["lx"]), 0.0, float(w["out"])), face + _rng.randf_range(-0.35, 0.35), str(w["clip"]))
		if f:
			f.set_meta("home", f.position)
			f.set_meta("clip", "talk_gesture_a" if str(w["clip"]) == "wave" else str(w["clip"]))
			f.set_meta("pox", bool(w.get("pox", false)))
			Assets.play(f, str(f.get_meta("clip")))
			_women.append(f)
	var md: Dictionary = b["madam"]
	_madam = _fig(md["models"], _wp(i, float(md["lx"]), 0.0, float(md["out"])), face, "idle")
	if _madam:
		var ia := InteractableScript.new()
		ia.display_name = str(md["name"])
		ia.prompt_func = func() -> String: return "talk to %s" % md["name"] if not _dlg.is_open else ""
		ia.handler = _on_madam
		ia.marker_height = 2.2
		_madam.add_child(ia)
	var seat := _wp(i, float(b["bench_lx"]), 0.0, float(b["bench_out"]) + 0.05)
	_doorman = _fig(b["doorman"]["models"], seat, face, "sit_idle")
	_talker(_doorman, "doorman")
	_anchors["brothel"] = [brothel_door, _b_out * 6.5 + Basis(Vector3.UP, _b_rot) * Vector3(2.2, 0, 0) + Vector3(0, 1.9, 0), 1.4]


func _brothel_loop() -> void:
	var cry_t := 2.0
	var cough_t := 6.0
	while is_inside_tree():
		await get_tree().create_timer(1.0, false).timeout
		if _women.is_empty() or _raid_on:
			continue
		cry_t -= 1.0 * GameState.clock_scale
		cough_t -= 1.0 * GameState.clock_scale
		if cry_t <= 0.0:
			cry_t = _range(D["brothel"]["cry_every"])
			var w: Node3D = _pickf(_women)
			if w and w.visible:
				var soldier := _soldier_near(brothel_door, 12.0)
				say(w, "cry_soldier" if soldier else "cry", 3.6)
				Assets.play_action(w, "wave")
		if cough_t <= 0.0:
			cough_t = _range(D["brothel"]["cough_every"])
			for w in _women:
				if w.visible and bool(w.get_meta("pox", false)):
					say(w, "cough", 2.6)
					Assets.play_action(w, "hit_react")


func _soldier_near(p: Vector3, r: float) -> bool:
	for g in _guards():
		if _flat(g.global_position, p) < r:
			return true
	for c in _customers:
		if _ok(c) and c.visible and c.has_meta("soldier") and _flat(c.global_position, p) < r:
			return true
	return false


func _customer_loop() -> void:
	var bd: Dictionary = D["brothel"]["customers"]
	while is_inside_tree():
		await get_tree().create_timer(maxf(_range(bd["every"]) / maxf(GameState.clock_scale, 0.1), 1.0), false).timeout
		if _raid_on or brothel_door == Vector3.ZERO or _smoke:
			continue
		_customers = _customers.filter(func(c): return _ok(c) and c.process_mode != Node.PROCESS_MODE_DISABLED)
		if _customers.size() >= int(bd["max"]):
			continue
		_customer()


func _customer(soldier := -1) -> void:
	var bd: Dictionary = D["brothel"]["customers"]
	var is_soldier: bool = (_rng.randf() < float(bd["soldier_share"])) if soldier < 0 else soldier == 1
	var models: Array = _pickf(bd["soldier_models"] if is_soldier else bd["models"])
	var start := _nearest(_entries(), brothel_door, 14.0)
	var a = _actor(models, start, 0.0)
	if a == null:
		return
	_customers.append(a)
	if is_soldier:
		a.set_meta("soldier", true)
	var drunk: bool = _rng.randf() < float(bd["drunk_share"])
	a.speed = 0.8 if drunk else 1.1
	var lat := Basis(Vector3.UP, _b_rot) * Vector3(_rng.randf_range(-1.6, 1.6), 0, 0)
	await _goto(a, brothel_door + _b_out * 2.1 + lat, false, 45.0, true)
	if not _ok(a):
		return
	var w: Node3D = _pickf(_women)
	if w:
		_halt(a, "haggle", w.global_position)
		if _rng.randf() < 0.5:
			say(a, "customer_soldier" if is_soldier else "customer", 3.0)
		await _sleep(3.8)
	if _raid_on or not _ok(a):
		await _leave(a)
		return
	if _doorman and _rng.randf() < 0.15:
		say(_doorman, "doorman", 2.4)
	await _goto(a, brothel_door + _b_out * 1.15, false, 12.0, true)
	if not _ok(a):
		return
	a._set_hidden(true)
	a.set_meta("inside", true)
	await get_tree().create_timer(maxf(_range(D["brothel"]["customers"]["inside"]) / maxf(GameState.clock_scale, 0.1), 2.0) * (0.3 if _smoke else 1.0), false).timeout
	while _raid_on:
		await get_tree().create_timer(2.0, false).timeout
	if not _ok(a):
		return
	a.remove_meta("inside")
	a.global_position = brothel_door + _b_out * 1.25
	a.reset_physics_interpolation()
	a._set_hidden(false)
	a.speed = 0.75 if drunk or _rng.randf() < 0.3 else 1.1
	await _leave(a)
	_customers.erase(a)


func _pimp_loop() -> void:
	if brothel_door == Vector3.ZERO:
		return
	var b: Dictionary = D["brothel"]["pimp"]
	var home := _wp(int(D["brothel"]["portal"]), float(b["lx"]), 0.0, float(b["out"]))
	_pimp = _actor(b["models"], home, _b_rot + PI + 0.6)
	if _pimp == null:
		return
	_talker(_pimp, "pimp", func() -> bool: return not _raid_on)
	_halt(_pimp, "idle", brothel_door + _b_out * 3.0)
	while is_inside_tree():
		await get_tree().create_timer(maxf(_range(b["every"]) / maxf(GameState.clock_scale, 0.1), 3.0), false).timeout
		if not _raid_on:
			await pimp_collect()


func pimp_collect() -> bool:
	if not _ok(_pimp) or _women.is_empty():
		return false
	var w: Node3D = _pickf(_women)
	var home: Vector3 = _pimp.global_position
	await _goto(_pimp, w.global_position + (_pimp.global_position - w.global_position).normalized() * 0.9, false, 15.0)
	_halt(_pimp, "haggle", w.global_position)
	say(_pimp, "pimp_demand", 2.8)
	await _sleep(2.4)
	say(w, "pimp_reply", 2.8)
	Assets.play_action(w, "haggle")
	await _sleep(2.4)
	if _rng.randf() < 0.35:
		_act(_pimp, "shoved")
		Assets.play_action(w, "hit_react")
		await _sleep(1.0)
	_stat["pimp"] = true
	await _goto(_pimp, home, false, 15.0)
	_halt(_pimp, "idle", brothel_door + _b_out * 3.0)
	return true


# ------------------------------------------------------------------ the madam

func _on_madam(_actor_node: Node) -> bool:
	if _dlg.is_open or Mission.dialogue_blocking():
		return false
	var md: Dictionary = D["brothel"]
	_dlg_names = {"$madam": str(md["madam"]["name"]), "$them": str(md["madam"]["name"]), "$you": "You"}
	_dlg_vars = {"room": int(md["room_cost"]), "gossip": 0 if _gossip_free else int(md["gossip_cost"])}
	_dlg_handler = _madam_action
	_dlg_graph = D["madam"]
	_dlg_personality = str(D["people"]["madam"]["personality"])
	_dlg_who = _madam
	_dlg_resp = {}
	if _madam:
		_madam.rotation.y = _yaw_to(_madam.global_position, _player().global_position) if _player() else _madam.rotation.y
		Assets.play(_madam, "talk_gesture_b")
	if _raid_on:
		_dlg_play("raid_closed")
	elif _room_left > 0.0:
		_dlg_play("room_taken")
	else:
		_dlg_play("greet")
	return true


func _madam_action(action: String) -> String:
	var md: Dictionary = D["brothel"]
	match action:
		"room":
			var n := int(md["room_cost"])
			if GameState.coins < n:
				return ""
			GameState.coins -= n
			_take_room()
			_msg("room", {"n": n})
			return "room"
		"gossip":
			var n := 0 if _gossip_free else int(md["gossip_cost"])
			var left := ["officer", "rota", "informer"].filter(func(k): return not _gossip_told.has(k))
			if left.is_empty():
				return "gossip_done"
			if GameState.coins < n:
				return ""
			GameState.coins -= n
			_gossip_free = false
			_dlg_vars["gossip"] = int(md["gossip_cost"])
			var k: String = left[0]
			_tell_gossip(k)
			return "gossip_" + k
		"leave":
			return ""
	return ""


func _tell_gossip(k: String) -> void:
	if not _gossip_told.has(k):
		_gossip_told.append(k)
	_flag("gossip_" + k)
	var what: String = {"officer": "an Austrian officer is upstairs at the red lantern; his men wait at the corner.",
			"rota": "the patrols change at the bell and look up little for a quarter of an hour after it.",
			"informer": "the informer reports to the Corporal before midnight, and drinks with his clerk at the wine cellar."}.get(k, k)
	_msg("gossip", {"what": what}, 5.0)


## A paid room: through the lodging house's door into the interior set if there is one, else the doorway hides the
## player like a hiding spot. Visibility 0 for `room_secs`, guard suspicion cleared, Mission.flags "brothel_room".
func _take_room() -> void:
	var p := _player()
	if p == null:
		return
	_flag("brothel_room", true)
	_flag("brothel_room_used", true)
	_room_left = float(D["brothel"]["room_secs"])
	for g in _guards():
		if g.get("state") != 3:   # not ALARM: they lose the thread
			g.set("suspicion", 0.0)
	var went := false
	if interiors and interiors.has_method("enter_now"):
		var door := "door_%s_%d" % [portals[13][0], 13] if portals.size() > 13 else ""
		if door != "" and interiors.find_door(door):
			went = interiors.enter_now(p, door)
			if went:
				interiors.set("_return", {"pos": brothel_door + _b_out * 1.5 + Vector3(0, 0.1, 0), "yaw": _b_rot + PI})
	if not went:
		var hs := preload("res://scripts/stealth/hiding_spot.gd").new()
		hs.kind = "niche"
		hs.display_name = "The red lantern's back room"
		hs.position = brothel_door + _b_out * 0.2
		hs.rotation.y = _b_rot
		hs.inner_point = Vector3(0, 0, -0.1)
		hs.exit_point = Vector3(0, 0, 1.4)
		hs.peek_point = Vector3(0, 1.0, 0.6)
		add_child(hs)
		_room_spot = hs
		p.enter_spot(hs)


# ------------------------------------------------------------------ dialogue runner (own box: the mission's runner owns its own)

func _dlg_play(node_name: String) -> void:
	var node: Dictionary = _dlg_graph.get(node_name, {})
	if node.is_empty():
		_dlg.close()
		return
	_dlg_node = node_name
	var lines: Array = []
	for l in node.get("lines", []):
		lines.append([_dlg_fmt(str(_dlg_names.get(str(l[0]), l[0]))), _dlg_fmt(str(l[1]))])
	_dlg_choices = []
	var shown: Array = []
	for c in node.get("choices", []):
		_dlg_choices.append(c)
		shown.append({"text": _dlg_fmt(str(c.get("text", "..."))), "enabled": _dlg_need(str(c.get("need", ""))), "why": str(c.get("why", "not possible"))})
	_dlg.show_node(lines, shown)


func _dlg_fmt(t: String) -> String:
	for k in _dlg_vars:
		t = t.replace("{%s}" % k, str(_dlg_vars[k]))
	return t.replace("{coins}", str(GameState.coins))


func _dlg_need(c: String) -> bool:
	if c == "" or not ">=" in c:
		return true
	var rhs := c.get_slice(">=", 1).strip_edges()
	var n := int(_dlg_vars.get(rhs, int(rhs)))
	return GameState.coins >= n


func _on_dlg_choice(i: int) -> void:
	if i < 0 or i >= _dlg_choices.size():
		return
	var c: Dictionary = _dlg_choices[i]
	var nxt := str(c.get("next", ""))
	if c.has("cost") and GameState.coins >= int(c["cost"]):
		GameState.coins -= int(c["cost"])
	if c.has("action") and _dlg_handler.is_valid():
		var r := str(_dlg_handler.call(str(c["action"])))
		if r != "":
			nxt = r
	elif c.has("tone"):
		# answered by who is speaking: their own line for this tone, else their personality's
		var resp := _response(str(c["tone"]))
		if not resp.is_empty():
			var eff := str(resp.get("effect", ""))
			var redirect := _effect(eff) if eff != "" else ""
			_dlg_after = str(resp.get("next", redirect if redirect != "" else nxt))
			_stat["tone_" + str(c["tone"])] = _dlg_personality
			var lines: Array = []
			for l in resp.get("lines", []):
				lines.append([_dlg_fmt(str(_dlg_names.get(str(l[0]), l[0]))), _dlg_fmt(str(l[1]))])
			_dlg_node = "__response"
			_dlg_choices = []
			if _dlg.is_open:
				_dlg.show_node(lines, [])
			return
	if nxt != "" and _dlg_graph.has(nxt):
		_dlg_play(nxt)
	else:
		_dlg.close()
		_dlg_ended()


func _on_dlg_finished() -> void:
	if _dlg_node == "__response":
		if _dlg_after != "" and _dlg_graph.has(_dlg_after):
			_dlg_play(_dlg_after)
		else:
			_dlg_ended()
		return
	var node: Dictionary = _dlg_graph.get(_dlg_node, {})
	if _dlg_graph == D["madam"] and _dlg_node.begins_with("gossip_") and _dlg_node != "gossip_done":
		_dlg_play("greet")
		return
	if node.has("next"):
		_dlg_play(str(node["next"]))
		return
	_dlg_ended()


func _dlg_ended() -> void:
	if _madam:
		Assets.play(_madam, "idle")
	if has_meta("dlg_done"):
		var cb: Callable = get_meta("dlg_done")
		remove_meta("dlg_done")
		if cb.is_valid():
			cb.call()


func _response(tone: String) -> Dictionary:
	if _dlg_resp.has(tone):
		return _dlg_resp[tone]
	var table: Dictionary = D.get("responses", {}).get(_dlg_personality, {})
	return table.get(tone, table.get("*", {}))


## What a toned answer does. Returns a dialogue node to go to next, or "".
func _effect(eff: String) -> String:
	var p := _player()
	match eff:
		"gossip_free":
			_gossip_free = true
			_dlg_vars["gossip"] = 0
		"gossip_officer", "gossip_rota", "gossip_informer":
			_tell_gossip(eff.trim_prefix("gossip_"))
		"free_room":
			_msg("free_room", {}, 3.5)
			_take_room()
		"warm", "drink", "kind":
			_msg(eff, {}, 3.5)
			_flag("street_" + eff, true)
		"slap", "knife":
			if p and _dlg_who:
				if eff == "knife":
					_act(_dlg_who, "knife_stab" if Assets.has_clip(_fig_of(_dlg_who), "knife_stab") else "attack_thrust")
				else:
					_act(_dlg_who, "attack_swing")
				_cudgel(p, _dlg_who, eff)
		"leave":
			if _dlg_who is CharacterBody3D:
				_leave(_dlg_who)
		"cost_up":
			_mug_state["cost"] = int(_mug_state.get("cost", 3)) + 1
			_dlg_vars["cost"] = _mug_state["cost"]
		"cowed_if_strong":
			if GameState.get_influence("street") >= 40 or GameState.get_influence("underworld") >= 20:
				_mug_state["result"] = "cowed"
				_msg("cowed", {}, 3.5)
		"fight":
			_mug_state["result"] = "fight"
		"calm", "rile", "appeal":
			if riot_state.get("on", false):
				var d := -0.25 if eff == "calm" else 0.2
				if eff == "appeal":
					d = -0.35 if GameState.get_influence("street") >= int(D["riot"]["calm_street"]) else 0.1
				riot_state["intensity"] = clampf(float(riot_state["intensity"]) + d, 0.0, 1.0)
				_msg("riot_calm" if d < 0.0 else "riot_rile", {}, 3.5)
	return ""


## Somebody to talk to: `who` keys data "people" and "dialogues". `ok` (optional) decides when they will talk.
func _talker(node: Node3D, who: String, ok: Callable = Callable()) -> void:
	if node == null:
		return
	var ia := InteractableScript.new()
	var pd: Dictionary = D["people"].get(who, {})
	ia.display_name = str(pd.get("name", who))
	ia.marker_height = 2.2
	ia.prompt_func = func() -> String:
		if _dlg.is_open or (ok.is_valid() and not bool(ok.call())):
			return ""
		return "talk to " + str(pd.get("name", who)).to_lower() if str(pd.get("name", who)).begins_with("A ") or str(pd.get("name", who)).begins_with("The ") else "talk to " + str(pd.get("name", who))
	ia.handler = func(_a: Node) -> bool: return _talk_to(who, node)
	node.add_child(ia)


func _talk_to(who: String, node: Node3D) -> bool:
	if _dlg.is_open or Mission.dialogue_blocking():
		return false
	var g: Dictionary = D.get("dialogues", {}).get(who, {})
	if g.is_empty():
		return false
	var pd: Dictionary = D["people"].get(who, {})
	_dlg_graph = g
	_dlg_names = {"$them": str(pd.get("name", who)), "$you": "You"}
	_dlg_vars = {}
	_dlg_personality = str(pd.get("personality", ""))
	_dlg_resp = g.get("responses", {})
	_dlg_who = node
	_dlg_handler = func(_action: String) -> String: return ""
	var p := _player()
	if p and not (node is CharacterBody3D):
		node.rotation.y = _yaw_to(node.global_position, p.global_position)
	elif p and node is CharacterBody3D:
		_halt(node, "idle", p)
	_dlg_play("start")
	return true


## Smoke/test helper: answer the open conversation with the choice whose action is `action`.
func answer(action: String) -> bool:
	if _dlg == null or not _dlg.is_open:
		return false
	for guard_i in 12:
		if _dlg.is_choosing():
			break
		_dlg.advance()
	for k in _dlg_choices.size():
		if str(_dlg_choices[k].get("action", "")) == action or str(_dlg_choices[k].get("tone", "")) == action \
				or str(_dlg_choices[k].get("next", "")) == action:
			_dlg.choose(k)
			return true
	return false


# ================================================================== drunks

func _tick_drunks(_delta: float) -> void:
	_drunks = _drunks.filter(func(d): return _ok(d) and d.visible)
	var target := _drunk_target()
	if _drunks.size() < target and not has_meta("drunk_spawning"):
		set_meta("drunk_spawning", true)
		_spawn_drunk()
		get_tree().create_timer(3.0, false).timeout.connect(func() -> void: remove_meta("drunk_spawning"))


func _drunk_target() -> int:
	var dk: Dictionary = D["drunks"]
	if not _between(str(dk["from"]), str(dk["until"])) and not has_meta("force_drunks"):
		return int(get_meta("force_drunks", 0))
	var t: Dictionary = dk["count_by_hour"]
	var n := int(t.get(str(_hour()), t.get("*", 0)))
	return maxi(n, int(get_meta("force_drunks", 0)))


func _spawn_drunk(at: Variant = null):
	var dk: Dictionary = D["drunks"]
	var alley: bool = _rng.randf() < _table(dk["alley_share"], 0.2)
	var start: Vector3
	if at != null:
		start = at
	else:
		# out of a tavern door: the beer hall (10), the inn (14), the cafe (5), or an alley mouth
		var doors: Array = []
		for i in [10, 14, 5]:
			if i < portals.size():
				doors.append(_door_of(i, 1.1))
		start = _pickf(doors) if not alley or doors.is_empty() else _v(_pickf(dk["alley_points"]))
	var a = _actor(_pickf(dk["models"]), _nav_point(start), _rng.randf() * TAU, true)
	if a == null:
		return null
	a.soft = true
	a.speed = 0.72
	a.set_meta("drunk", true)
	a.set_meta("alley", alley)
	a.add_to_group("takedown")
	a.on_felled = _drunk_shoved
	if not a.has_meta("talker"):
		a.set_meta("talker", true)
		_talker(a, "drunk", func() -> bool: return not a.has_meta("asleep") and not a.has_meta("held"))
	_drunks.append(a)
	_stat["drunks"] = maxi(int(_stat["drunks"]), _drunks.size())
	_drunk_life(a)
	return a


func _drunk_shoved(a) -> void:
	if not _ok(a) or a.has_meta("shoved_cd"):
		return
	a.set_meta("shoved_cd", true)
	a.set_meta("interrupt", true)
	_halt(a)
	_act(a, "shoved")
	say(a, "shoved", 2.6)
	_stat["drunk_shoved"] = true
	get_tree().create_timer(2.0, false).timeout.connect(func() -> void:
		if _ok(a):
			a.remove_meta("shoved_cd")
			if _rng.randf() < 0.5:
				_act(a, "stumble"))


func _drunk_life(a) -> void:
	var dk: Dictionary = D["drunks"]
	await get_tree().physics_frame
	while _ok(a) and a.visible:
		if a.has_meta("held"):
			await get_tree().create_timer(0.5, false).timeout
			continue
		if not a.has_meta("asleep") and randf() < 0.3:
			Sfx.play("hiccup", (a as Node3D).global_position + Vector3(0, 1.5, 0))
		if a.has_meta("asleep"):
			if _rng.randf() < 0.3:
				say(a, "snore", 2.5)
			await get_tree().create_timer(_rng.randf_range(15.0, 25.0), false).timeout
			if _clock() >= GameState.parse_clock(str(dk["until"])) and not _smoke:
				_wake_drunk(a)
				await _leave(a)
				return
			continue
		if _drunks.size() > _drunk_target() + 1 or _clock() >= GameState.parse_clock(str(dk["until"])):
			a.speed = 0.72
			await _leave(a)
			return
		var r := _rng.randf()
		var sleep_ok := _clock() >= GameState.parse_clock("23:30")
		if r < 0.45:
			var pts: Array = dk["alley_points"] if bool(a.get_meta("alley", false)) else dk["square_points"]
			await _stagger_to(a, _nav_point(_v(_pickf(pts)) + Vector3(_rng.randf_range(-2, 2), 0, _rng.randf_range(-2, 2))), 25.0)
		elif r < 0.65:
			_halt(a, "idle")
			var now := Time.get_ticks_msec() / 1000.0
			if now - float(a.get_meta("sang", -100.0)) >= 20.0:
				a.set_meta("sang", now)
				say(a, "song", 3.0)
			_act(a, "talk_gesture_b")
			await get_tree().create_timer(4.0, false).timeout
		elif r < 0.78:
			await drunk_relieve(a)
		elif r < 0.9 and sleep_ok:
			await drunk_sleep(a)
		else:
			_halt(a, "idle")
			_act(a, "stumble")
			await get_tree().create_timer(2.5, false).timeout


## Staggering walk: a sinusoidal weave across the line, a stumble every few seconds. Checks for the watch (moved on)
## and for someone to accost on the way.
func _stagger_to(a, target: Vector3, max_secs: float) -> void:
	var t := 0.0
	var ph := _rng.randf() * TAU
	var next_stumble := _rng.randf_range(3.0, 6.0)
	var dk: Dictionary = D["drunks"]
	while _ok(a) and t < max_secs and not a.has_meta("held"):
		if a.has_meta("interrupt"):
			a.remove_meta("interrupt")
			await get_tree().create_timer(2.0, false).timeout
		var to: Vector3 = target - a.global_position
		to.y = 0.0
		if to.length() < 1.0:
			break
		var dir := to.normalized()
		var side := Vector3(-dir.z, 0, dir.x)
		a.script_goto(a.global_position + dir * 1.6 + side * sin(t * 1.7 + ph) * 1.0, 0.0, false)
		if t > next_stumble:
			next_stumble = t + _rng.randf_range(3.0, 7.0)
			_halt(a)
			_act(a, "stumble")
			await get_tree().create_timer(1.2, false).timeout
			t += 1.2
			continue
		# the watch moves him on
		for g in _guards():
			if _flat(g.global_position, a.global_position) < float(dk["guard_move_on_dist"]) and not a.has_meta("moved_cd"):
				var gf: Vector3 = -g.global_transform.basis.z
				var tog: Vector3 = a.global_position - g.global_position
				tog.y = 0.0
				if gf.dot(tog.normalized()) > 0.5:
					await _moved_on(a, g)
					return
		# accost the player or a townsman
		var p := _player()
		if p and not _smoke and not a.has_meta("accost_cd") and _flat(p.global_position, a.global_position) < float(dk["accost_dist"]) \
				and p.get("hidden_spot") == null and not _dlg.is_open:
			await drunk_accost(a, p)
			return
		if not a.has_meta("accost_cd") and _rng.randf() < 0.003:
			var ws := _walkers_near(a.global_position, 3.0, 1)
			if not ws.is_empty():
				await drunk_accost(a, ws[0])
				return
		await get_tree().physics_frame
		t += get_physics_process_delta_time()
	_halt(a)


func _moved_on(a, g: Node3D) -> void:
	a.set_meta("moved_cd", true)
	get_tree().create_timer(25.0, false).timeout.connect(func() -> void:
		if _ok(a):
			a.remove_meta("moved_cd"))
	_halt(a, "idle", g.global_position)
	bubble(g, _pick("guard_move_on"), 2.6)
	await get_tree().create_timer(1.4, false).timeout
	say(a, "drunk_reply", 2.6)
	var away: Vector3 = a.global_position - g.global_position
	away.y = 0.0
	_stat["moved_on"] = true
	await _goto(a, _nav_point(a.global_position + away.normalized() * 9.0), false, 14.0, true)


## Block someone's path with an offered bottle, then wander off. The player's swing only shoves him (Tough.soft).
func drunk_accost(a, who: Node3D) -> void:
	a.set_meta("accost_cd", true)
	get_tree().create_timer(float(D["drunks"]["accost_cooldown"]), false).timeout.connect(func() -> void:
		if _ok(a):
			a.remove_meta("accost_cd"))
	var fwd := -who.global_transform.basis.z
	if who.has_method("_look_dir"):
		fwd = who.call("_look_dir")
	fwd.y = 0.0
	await _goto(a, who.global_position + fwd.normalized() * 1.05, false, 5.0, true)
	if not _ok(a):
		return
	_halt(a, "idle", who)
	say(a, "accost", 3.2)
	_act(a, "talk_gesture_a")
	_stat["accost"] = true
	await get_tree().create_timer(4.0, false).timeout
	if not _ok(a):
		return
	say(a, "accost_leave", 2.6)
	await get_tree().create_timer(0.6, false).timeout
	var away: Vector3 = a.global_position - who.global_position
	away.y = 0.0
	await _goto(a, _nav_point(a.global_position + away.normalized().rotated(Vector3.UP, _rng.randf_range(-1, 1)) * 7.0), false, 10.0, true)


func drunk_relieve(a) -> void:
	# the nearest bit of wall between two doors
	var best := Vector3.ZERO
	var best_yaw := 0.0
	var bd := INF
	for i in portals.size():
		if i == int(D["brothel"]["portal"]):
			continue
		for lx in [-4.3, 4.3]:
			var q := _wp(i, lx, 0.0, 0.55)
			var d := _flat(q, a.global_position)
			if d < bd:
				bd = d
				best = q
				best_yaw = float(portals[i][2])
	if bd > 22.0:
		return
	await _stagger_to(a, best + Vector3(sin(best_yaw), 0, cos(best_yaw)) * 1.5, 18.0)
	await _goto(a, best, false, 8.0)
	if not _ok(a):
		return
	_halt(a, "idle", best - Vector3(sin(best_yaw), 0, cos(best_yaw)) * 2.0)
	await get_tree().create_timer(1.0, false).timeout
	say(a, "relieve", 3.0)
	_stat["relieve"] = true
	await get_tree().create_timer(5.0 * (0.3 if _smoke else 1.0), false).timeout


## Onto a free bench (sit, then slump and snore), else into a doorway (huddled).
func drunk_sleep(a, instant := false) -> void:
	var best := -1
	var bd := INF
	for k in _benches.size():
		if _sleep_spots.has(k) and _ok(_sleep_spots[k]):
			continue
		var d := _flat(_benches[k][0], a.global_position)
		if d < bd:
			bd = d
			best = k
	a.set_meta("asleep", true)
	a.remove_from_group("takedown")
	if best >= 0 and bd < 30.0:
		_sleep_spots[best] = a
		var pos: Vector3 = _benches[best][0]
		var rot: float = _benches[best][1]
		var out := Vector3(sin(rot), 0, cos(rot))
		if not instant:
			await _stagger_to(a, pos + out * 1.4, 25.0)
			await _goto(a, pos + out * 0.8, false, 6.0)
		if not _ok(a):
			return
		a._shape.disabled = true
		a.set_physics_process(false)      # no gravity while wedged onto the seat
		a.global_position = pos + out * 0.08
		a.rotation.y = rot + PI
		a.reset_physics_interpolation()
		_halt(a, "sit_idle")
		Assets.play(a._figure, "sit_idle")       # its physics (and so its own clip calls) is off while asleep
		a.set_meta("sleep_spot", best)
		if not instant:
			await get_tree().create_timer(12.0 * (0.2 if _smoke else 1.0), false).timeout
		if _ok(a):
			a.rotation.x = -0.12
			a.rotation.z = 0.12
			var fig: Node3D = a.get("_figure")
			if fig and fig.has_meta("anim"):
				(fig.get_meta("anim") as AnimationPlayer).speed_scale = 0.25
			say(a, "snore", 3.0)
	else:
		_halt(a, "crouch_hide")
	_stat["asleep"] = true


func _wake_drunk(a) -> void:
	if not _ok(a):
		return
	a.remove_meta("asleep")
	a.rotation.x = 0.0
	a.rotation.z = 0.0
	a._shape.disabled = false
	a.set_physics_process(true)
	if a.has_meta("sleep_spot"):
		_sleep_spots.erase(int(a.get_meta("sleep_spot")))
		a.remove_meta("sleep_spot")
	var fig: Node3D = a.get("_figure")
	if fig and fig.has_meta("anim"):
		(fig.get_meta("anim") as AnimationPlayer).speed_scale = 1.0


# ================================================================== riot

## A riot at `centre` (campaign finale hook): townsfolk within data riot.radius become a mob with a ringleader (talk to
## him: joke / threat / appeal moves the intensity), they smash stalls and barrels (torches set them alight at high
## intensity), drag out anything in group "riot_target" (killed() / take_hit() / knock_down()), and at low Street
## influence turn on the player's allies (group "movement"). The player close to the ringleader calms it with Street
## influence >= calm_street, else feeds it. After volley_after seconds the watch forms a line and fires: the mob
## scatters and two or three rioters die. Crackdown +crackdown_per_min per game minute. Outcomes: crushed, dispersed,
## spent. Signals riot_started / riot_peak / riot_ended, mirrored to Mission.flags riot_on / riot_peak / riot_outcome.
func riot(centre: Vector3, intensity: float = 0.5, cause: String = "bread") -> void:
	if riot_state.get("on", false) or D.is_empty():
		return
	var rd: Dictionary = D["riot"]
	riot_state = {"on": true, "centre": centre, "intensity": clampf(intensity, 0.0, 1.0), "cause": cause, "t": 0.0,
			"mob": [], "rioters": [], "leader": null, "peak": false, "outcome": "", "smashed": 0, "dead": 0, "min": _clock()}
	var mob: Array = riot_state["mob"]
	for w in _walkers_near(centre, float(rd["radius"]), 8):
		_borrow(w)
		w.add_to_group("crowd")
		w.set_meta("rioter", true)
		mob.append(w)
	for k in int(rd["rioters"]):
		var r = _actor(_pickf(rd["rioter_models"]), _nav_point(centre + Vector3(_rng.randf_range(-4, 4), 0, _rng.randf_range(-4, 4))), 0.0)
		if r:
			r.add_to_group("crowd")
			r.set_meta("rioter", true)
			mob.append(r)
			riot_state["rioters"].append(r)
	var leader = _actor(rd["ringleader_models"], _nav_point(centre), 0.0)
	if leader:
		riot_state["leader"] = leader
		mob.append(leader)
		riot_state["rioters"].append(leader)
		if not leader.has_meta("talker"):
			leader.set_meta("talker", true)
			_talker(leader, "ringleader", func() -> bool: return riot_state.get("on", false))
	for k in mini(int(rd["torches"]), mob.size()):
		_torch(mob[k])
	_msg("riot", {"cause": cause}, 4.0)
	_flag("riot_on", true)
	riot_started.emit(centre, intensity, cause)
	_anchors["riot"] = [centre, Vector3(6.0, 2.6, 5.0), 1.2]
	_riot_loop()


func _torch(a) -> void:
	var t := Node3D.new()
	t.name = "Torch"
	t.set_meta("sl_prop", true)
	var stick := _prim_box(Vector3(0.04, 0.6, 0.04), Color(0.3, 0.2, 0.1))
	stick.position = Vector3(0, 0.3, 0)
	t.add_child(stick)
	var flame := _prim_box(Vector3(0.12, 0.18, 0.12), Color(1.0, 0.55, 0.15))
	var fm := flame.material_override as StandardMaterial3D
	fm.emission_enabled = true
	fm.emission = Color(1.0, 0.5, 0.12)
	fm.emission_energy_multiplier = 5.0
	flame.position = Vector3(0, 0.66, 0)
	t.add_child(flame)
	var l := FlickerLight.new()
	l.amount = 0.3
	l.speed = 10.0
	l.light_color = Color(1.0, 0.55, 0.2)
	l.light_energy = 2.0
	l.omni_range = 6.0
	l.position = Vector3(0, 0.8, 0)
	t.add_child(l)
	t.position = Vector3(0.28, 1.2, -0.15)
	t.rotation.z = -0.25
	a.add_child(t)
	a.set_meta("torch", true)


func _riot_loop() -> void:
	var rd: Dictionary = D["riot"]
	var volley_at := float(rd["volley_after"]) * (0.12 if _smoke else 1.0)
	var max_t := float(rd["max_secs"]) * (0.2 if _smoke else 1.0)
	var chant_t := 1.0
	var smash_t := 3.0 * _ts
	var target_t := 2.0 * _ts
	var lined := false
	while is_inside_tree() and riot_state.get("on", false):
		await get_tree().create_timer(0.5, false).timeout
		var dt := 0.5
		riot_state["t"] = float(riot_state["t"]) + dt
		var t := float(riot_state["t"])
		var c: Vector3 = riot_state["centre"]
		var mob: Array = (riot_state["mob"] as Array).filter(func(m): return _ok(m) and not m.has_meta("dead"))
		riot_state["mob"] = mob
		var inten := float(riot_state["intensity"])
		# drift, and the player's presence by the ringleader
		inten += 0.012 * dt
		var p := _player()
		var leader = riot_state.get("leader")
		if p and _ok(leader) and _flat(p.global_position, leader.global_position) < 6.0:
			inten += (-0.03 if GameState.get_influence("street") >= int(rd["calm_street"]) else 0.015) * dt
		inten = clampf(inten, 0.0, 1.0)
		riot_state["intensity"] = inten
		# crackdown by the game minute
		if _clock() - float(riot_state["min"]) >= 1.0:
			riot_state["min"] = _clock()
			GameState.crackdown = clampi(GameState.crackdown + int(rd["crackdown_per_min"]), 0, 100)
		if inten >= 0.9 and not riot_state["peak"]:
			riot_state["peak"] = true
			_flag("riot_peak", true)
			riot_peak.emit(mob.size())
			_stat["riot_peak_n"] = mob.size()
		# the mob mills, shakes fists, chants now and then
		for m in mob:
			if m.has_meta("busy_riot"):
				continue
			if _rng.randf() < 0.25:
				m.script_goto(_nav_point(c + Vector3(_rng.randf_range(-4.5, 4.5), 0, _rng.randf_range(-4.5, 4.5))), 0.0, inten > 0.7)
			elif _rng.randf() < 0.3 * inten:
				_act(m, "attack_swing" if _rng.randf() < 0.6 else "shoved")
		chant_t -= dt
		if chant_t <= 0.0 and not mob.is_empty():
			chant_t = _rng.randf_range(6.0, 9.0)
			say(_pickf(mob), "chant", 2.6)
		# smash a stall or a barrel, and at high pitch set it alight
		smash_t -= dt
		if smash_t <= 0.0 and inten > 0.4 and not mob.is_empty():
			smash_t = _rng.randf_range(5.0, 8.0) * _ts
			_riot_smash(c, _pickf(mob), inten)
		# targets, and the player's allies when the street does not know them
		target_t -= dt
		if target_t <= 0.0 and not mob.is_empty():
			target_t = 4.0 * _ts
			_riot_targets(c, mob, inten)
		if t >= volley_at - 6.0 * _ts and not lined:
			lined = true
			for g in _guards():
				if _flat(g.global_position, c) < 40.0 and g.has_method("investigate"):
					g.investigate(c + (g.global_position - c).normalized() * 9.0, 12.0, "riot")
		if t >= volley_at:
			await _riot_volley(c, mob)
			_riot_end("crushed")
			return
		if inten <= 0.05:
			_riot_end("dispersed")
			return
		if t >= max_t:
			_riot_end("spent")
			return


func _riot_smash(c: Vector3, m, inten: float) -> void:
	var best: Node3D = null
	var bd := 14.0
	if not riot_state.has("smashables"):
		var list: Array = []
		for n in district.find_children("*", "Node3D", true, false):
			if n.scene_file_path.get_file().get_basename() in ["market_stall", "barrel", "crate_stack", "sacks_crates", "handcart", "chairs_stacked", "cart"]:
				list.append(n)
		riot_state["smashables"] = list
	for n in riot_state["smashables"]:
		if not is_instance_valid(n) or n.has_meta("smashed"):
			continue
		var d := _flat(n.global_position, c)
		if d < bd:
			bd = d
			best = n
	if best == null or not _ok(m):
		return
	best.set_meta("smashed", true)
	m.set_meta("busy_riot", true)
	await _goto(m, _nav_point(best.global_position + (c - best.global_position).normalized() * 1.2), true, 10.0, true)
	if not _ok(m):
		return
	_halt(m, "idle", best.global_position)
	_act(m, "attack_swing")
	await _sleep(0.5)
	if is_instance_valid(best):
		var tw := best.create_tween()          # knocked over
		tw.tween_property(best, "rotation", best.rotation + Vector3(0.5 if _rng.randf() < 0.5 else -0.5, _rng.randf_range(-0.4, 0.4), 0.2), 0.6)
		riot_state["smashed"] = int(riot_state.get("smashed", 0)) + 1
		if inten > 0.7 and m.has_meta("torch"):
			FireScript.ignite(best.global_position, get_tree())
			riot_state["fires"] = int(riot_state.get("fires", 0)) + 1
	if _ok(m):
		m.remove_meta("busy_riot")


func _riot_targets(c: Vector3, mob: Array, inten: float) -> void:
	var r := float(D["riot"]["radius"])
	var pool: Array = get_tree().get_nodes_in_group("riot_target")
	if GameState.get_influence("street") < int(D["riot"]["turn_on_allies_below"]):
		pool += get_tree().get_nodes_in_group("movement")
	for tgt in pool:
		if not (tgt is Node3D) or not (tgt as Node3D).is_visible_in_tree() or _flat((tgt as Node3D).global_position, c) > r:
			continue
		if tgt.has_meta("riot_done"):
			continue
		var m = _pickf(mob)
		if m == null or m.has_meta("busy_riot"):
			return
		m.set_meta("busy_riot", true)
		m.script_goto(tgt, 0.9, true)
		await _sleep(2.5)
		if _ok(m) and is_instance_valid(tgt):
			_act(m, "attack_swing")
			tgt.set_meta("riot_done", true)
			if inten > 0.85 and tgt.has_method("killed"):
				tgt.call("killed")
			elif tgt.has_method("take_hit"):
				tgt.call("take_hit", m)
			elif tgt.has_method("knock_down"):
				tgt.call("knock_down", 30.0)
			riot_state["dragged"] = int(riot_state.get("dragged", 0)) + 1
		if _ok(m):
			m.remove_meta("busy_riot")
		return


## The watch's line: take aim, fire; the mob runs; two or three rioters (never the borrowed townsfolk) fall.
func _riot_volley(c: Vector3, mob: Array) -> void:
	var line: Array = []
	for g in _guards():
		if _flat(g.global_position, c) < 45.0:
			line.append(g)
		if line.size() >= 4:
			break
	if not line.is_empty():
		bubble(line[0], D["lines"]["volley"][0], 2.0)
	await _sleep(2.0)
	for g in line:
		var fig: Node3D = g.get("_figure")
		if fig:
			g.look_at(Vector3(c.x, g.global_position.y, c.z), Vector3.UP)
			Assets.play_action(fig, "musket_fire" if Assets.has_clip(fig, "musket_fire") else "attack_thrust")
	if not line.is_empty():
		bubble(line[0], D["lines"]["volley"][1], 1.6)
	var w := watch if watch and is_instance_valid(watch) else get_tree().get_first_node_in_group("watch")
	if w and w.has_method("emit_sound"):
		w.emit_sound(c, 1.0, "volley", false, true, true)
	var dead_n := _rng.randi_range(int(D["riot"]["deaths"][0]), int(D["riot"]["deaths"][1]))
	var rioters: Array = (riot_state["rioters"] as Array).filter(func(r): return _ok(r) and r != riot_state.get("leader"))
	for r in rioters.slice(0, dead_n):
		r.set_meta("dead", true)
		_halt(r)
		_act(r, "death_fall" if _rng.randf() < 0.6 else "death_fall_forward", true)
		r.remove_from_group("crowd")
		riot_state["dead"] = int(riot_state["dead"]) + 1
	var scattered := false
	for m in mob:
		if _ok(m) and not m.has_meta("dead"):
			if not scattered:
				scattered = true
				say(m, "scatter", 2.0)
			var away: Vector3 = m.global_position - c
			away.y = 0.0
			m.script_goto(_nav_point(m.global_position + away.normalized() * 14.0), 0.0, true)
	_msg_near("riot_crushed", c, 30.0, {}, 5.0)
	await _sleep(4.0)


func _riot_end(outcome: String) -> void:
	riot_state["on"] = false
	riot_state["outcome"] = outcome
	_flag("riot_on", false)
	_flag("riot_outcome", outcome)
	if outcome == "dispersed":
		_msg_near("riot_dispersed", riot_state["centre"], 30.0)
	for m in riot_state.get("mob", []):
		if not _ok(m) or m.has_meta("dead"):
			continue
		m.remove_meta("rioter")
		if m.has_meta("sl_busy"):
			_give_back(m)
		else:
			_leave(m, true)
	riot_ended.emit(outcome)
	_stat["riot"] = "%s peak=%s smashed=%d dead=%d" % [outcome, riot_state.get("peak", false), int(riot_state.get("smashed", 0)), int(riot_state.get("dead", 0))]


# ================================================================== the bard at the kawiarnia

## A lute-player by the cafe brazier: verses now and then, and a verse for a rumour (data "bard", dialogues.bard).
func _setup_bard() -> void:
	var bd: Dictionary = D.get("bard", {})
	if bd.is_empty() or portals.size() <= int(bd["portal"]):
		return
	var i := int(bd["portal"])
	var pos := _wp(i, float(bd["lx"]), 0.0, float(bd["out"]))
	if not _clear_of_lanes(pos):
		return
	_bard = _fig(bd["models"], pos, float(portals[i][2]) + PI + 0.35, str(bd.get("clip", "talk_gesture_b")))
	if _bard == null:
		return
	# no lute among the models: a plain one, pear body and neck, slung across the chest
	var lute := Node3D.new()
	lute.name = "Lute"
	lute.position = Vector3(0.08, 1.02, -0.24)
	lute.rotation = Vector3(0.15, 0.0, -0.75)
	var body := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 0.17
	sm.height = 0.3
	body.mesh = sm
	body.scale = Vector3(1.0, 1.25, 0.45)
	var wood := StandardMaterial3D.new()
	wood.albedo_color = Color(0.45, 0.28, 0.14)
	wood.roughness = 0.6
	body.material_override = wood
	lute.add_child(body)
	var neck := _prim_box(Vector3(0.05, 0.42, 0.03), Color(0.25, 0.16, 0.09))
	neck.position = Vector3(0, 0.36, 0.0)
	lute.add_child(neck)
	var head := _prim_box(Vector3(0.06, 0.12, 0.03), Color(0.22, 0.14, 0.08))
	head.position = Vector3(0, 0.6, -0.04)
	head.rotation.x = 0.9
	lute.add_child(head)
	_bard.add_child(lute)
	_talker(_bard, "bard", func() -> bool: return _between(str(bd["from"]), str(bd["until"])))
	_anchors["bard"] = [pos, Vector3(2.2, 1.6, -2.4), 1.2]
	_bard_loop(bd)


func _bard_loop(bd: Dictionary) -> void:
	while is_inside_tree() and _bard:
		await get_tree().create_timer(maxf(_range(bd["verse_every"]) / maxf(GameState.clock_scale, 0.1), 6.0), false).timeout
		var on := _between(str(bd["from"]), str(bd["until"]))
		_bard.visible = on
		if on and not _dlg.is_open:
			say(_bard, "verse", 3.0)
			_stat["bard"] = true


# ================================================================== punishment

func _setup_punishment_people() -> void:
	var pu: Dictionary = D["punishment"]
	var found: Node3D = null
	for n in district.find_children("*", "Node3D", true, false):
		if n.scene_file_path.get_file() == "pillory.glb" and not is_ancestor_of(n):
			found = n
			break
	if found:
		found.set_meta("sl_real", true)
		pu["pillory"]["_node"] = found
		pu["pillory"]["pos"] = [found.global_position.x, 0.0, found.global_position.z]
		pu["pillory"]["rot"] = found.global_rotation.y
		# the stocks and the soldier stand with it (they were placed before we knew): move them alongside
		var st: Node3D = pu["stocks"].get("_node")
		var r := found.global_rotation.y
		var side := Vector3(cos(r), 0, -sin(r))
		var out := Vector3(sin(r), 0, cos(r))
		if st:
			st.global_position = found.global_position + side * 3.4 + out * 0.9
			st.global_rotation.y = r
			pu["stocks"]["pos"] = [st.global_position.x, 0.0, st.global_position.z]
			pu["stocks"]["rot"] = r
		var gp: Vector3 = found.global_position - side * 2.2 + out * 1.6
		pu["guard"]["pos"] = [gp.x, 0.0, gp.z]
		pu["guard"]["rot"] = r + PI - 0.5
	else:
		_place_opt("pillory", pu["pillory"], "hitching_post")
	for key in ["pillory", "stocks"]:
		var e: Dictionary = pu[key]
		var node: Node3D = e.get("_node")
		if node == null:
			continue
		var real: bool = node.get_meta("sl_real", false)
		if key == "stocks" and not real:
			continue
		var p := _v(e["pos"])
		var rot := float(e.get("rot", 0.0))
		var out := Vector3(sin(rot), 0, cos(rot))
		var side := Vector3(out.z, 0, -out.x)
		# pillory.glb: stone steps 0.7 m high, the neck-and-wrist board at 2.13 m just in front of the post;
		# stocks.glb: the bench 0.6 m behind the leg board. Fallback: tied beside a hitching post.
		var fp := p + side * 0.55 + out * 0.15
		if real:
			fp = p + out * 0.3 + Vector3(0, 0.7, 0) if key == "pillory" else p - out * 0.6
		var f := _fig(e["models"], fp, rot + PI, "sit_idle" if key == "stocks" else "idle")
		if f == null:
			continue
		if key == "pillory":
			f.rotation.x = -0.1 if real else -0.12
		_placard(f, e["placard"], Vector3(0, 1.22 if key == "pillory" else 0.95, -0.24), 0.0)
		f.set_meta("placard", e["placard"])
		if key == "pillory":
			_talker(f, "prisoner")
		_prisoners.append(f)
	var gd: Dictionary = pu["guard"]
	if not _prisoners.is_empty():
		var g := _fig(gd["models"], _v(gd["pos"]), float(gd["rot"]), "guard_sentry")
		if g:
			g.set_meta("soldier", true)
	_anchors["pillory"] = [_v(pu["pillory"]["pos"]), Vector3(3.6, 1.8, 3.4), 1.2]
	# the gallows, outside the rows: a hanged pamphleteer turning slowly in the wind
	var ge: Dictionary = pu["gallows"]
	var gn: Node3D = ge.get("_node")
	if gn and bool(gn.get_meta("sl_real", false)):
		# gallows.glb: the noose hangs at (0.3, 2.86, 0) in the model's space, under the beam
		var hang: Vector3 = gn.global_transform * Vector3(0.3, 2.86, 0.0)
		var swing := Node3D.new()
		swing.name = "Hanged"
		swing.position = hang
		add_child(swing)
		var f := _fig(ge["models"], Vector3.ZERO, float(ge["rot"]) + PI, "idle")
		if f:
			remove_child(f)
			swing.add_child(f)
			f.position = Vector3(0, -1.58, 0)
			Assets.play(f, "idle", 0.0)
			_placard(f, ge["placard"], Vector3(0, 1.2, -0.22))
			var tw := swing.create_tween().set_loops()
			tw.tween_property(swing, "rotation", Vector3(0.02, 0.25, 0.035), 3.6).set_trans(Tween.TRANS_SINE)
			tw.tween_property(swing, "rotation", Vector3(-0.02, -0.25, -0.035), 3.6).set_trans(Tween.TRANS_SINE)
			_stat["gallows"] = true
		_anchors["gallows"] = [hang - Vector3(0, 1.6, 0), Vector3(5.5, 0.4, 2.5), 0.4]


func _jeer_loop() -> void:
	var pu: Dictionary = D["punishment"]
	while is_inside_tree():
		await get_tree().create_timer(maxf(_range(pu["jeer_every"]) / maxf(GameState.clock_scale, 0.1), 4.0), false).timeout
		if _prisoners.is_empty() or _smoke:
			continue
		await jeer()


func jeer() -> bool:
	if _prisoners.is_empty():
		return false
	var pr: Node3D = _pickf(_prisoners)
	var kind: bool = _rng.randf() < float(D["punishment"]["kind_share"])
	var a = null
	var borrowed := false
	var ws := _walkers_near(pr.global_position, 14.0, 1)
	if not ws.is_empty() and not _instant:
		a = ws[0]
		_borrow(a)
		borrowed = true
	else:
		a = _actor(_pickf(D["punishment"]["flogging"]["models"]["crowd"]), _spawn_near(pr.global_position, 8.0), 0.0)
	if a == null:
		return false
	var fwd := Vector3(sin(pr.rotation.y + PI), 0, cos(pr.rotation.y + PI))
	await _goto(a, pr.global_position - fwd * 1.8 + Vector3(_rng.randf_range(-0.8, 0.8), 0, 0), false, 25.0)
	if not _ok(a):
		return false
	a.add_to_group("crowd")
	_halt(a, "idle", pr.global_position)
	if kind:
		say(a, "kind", 3.0)
		_act(a, "bow")
		var loaf := _prim_box(Vector3(0.2, 0.08, 0.11), Color(0.55, 0.38, 0.2))
		loaf.position = pr.global_position - fwd * 0.5 + Vector3(0, 0.04, 0)
		add_child(loaf)
		get_tree().create_timer(120.0, false).timeout.connect(loaf.queue_free)
	else:
		say(a, "jeer", 3.0)
		_act(a, "attack_thrust" if _rng.randf() < 0.3 else "talk_gesture_a")
	await _sleep(2.5)
	if _rng.randf() < 0.5:
		say(pr, "prisoner", 3.0)
	_stat["jeer"] = "kind" if kind else "jeer"
	await _sleep(1.5)
	if borrowed:
		_give_back(a)
	else:
		await _leave(a)
	return true


func _ev_flogging(_o: Dictionary) -> void:
	var fl: Dictionary = D["punishment"]["flogging"]
	var post := _v(fl["post"])
	var rot := float(fl.get("rot", 0.0))
	var out := Vector3(sin(rot), 0, cos(rot))      # the post's face, toward the square
	var ms: Dictionary = fl["models"]
	var town_door := _nav_point(Vector3(-16, 0, 17.0))
	var start := town_door if not _instant else post + out * 2.0
	var victim = _actor(ms["victim"], start, 0.0)
	var s1 = _actor(ms["soldier"], start + Vector3(0.8, 0, 0.4), 0.0)
	var s2 = _actor(ms["soldier"], start + Vector3(-0.8, 0, 0.4), 0.0)
	var sgt = _actor(ms["sergeant"], start + Vector3(0, 0, 0.9), 0.0)
	var drum = _actor(ms["drummer"], start + Vector3(1.2, 0, 1.0), 0.0)
	if victim == null or s1 == null:
		return
	for s in [s1, s2, sgt, drum]:
		if s:
			s.set_meta("soldier", true)
	var side := Vector3(out.z, 0, -out.x)
	await _goto(victim, post + out * 0.78, false, 25.0)
	_goto(s1, post + out * 1.7 + side * 0.4, false, 25.0)
	_goto(sgt, post + out * 1.2 - side * 2.2, false, 25.0)
	_goto(drum, post + out * 0.9 + side * 2.4, false, 25.0)
	await _goto(s2, post - side * 1.2 + out * 0.4, false, 25.0)
	_anchors["flogging"] = [post, out * 5.0 - side * 3.5 + Vector3(0, 2.0, 0), 1.2]
	# the crowd: a few townsfolk from the doors, and whoever is passing
	var crowd: Array = []
	var borrowed: Array = []
	for k in int(fl["crowd"]):
		var ang := lerpf(-1.1, 1.1, float(k) / maxf(float(fl["crowd"]) - 1.0, 1.0)) + _rng.randf_range(-0.12, 0.12)
		var at := post + out.rotated(Vector3.UP, ang) * _rng.randf_range(3.4, 4.4)
		var c = _actor(_pickf(ms["crowd"]), _spawn_near(at, 6.0), 0.0)
		if c:
			crowd.append(c)
			c.add_to_group("crowd")
			_goto(c, _nav_point(at), false, 30.0)
	for w in _walkers_near(post, 16.0, 3):
		_borrow(w)
		borrowed.append(w)
		w.add_to_group("crowd")
		var ang := _rng.randf_range(-1.3, 1.3)
		w.script_goto(_nav_point(post + out.rotated(Vector3.UP, ang) * _rng.randf_range(4.2, 5.2)))
	await _sleep(3.0)
	for c in crowd + borrowed:
		if _ok(c):
			c.script_face(post)
	_halt(victim, "idle", post)
	_halt(s1, "idle", post)
	_halt(s2, "guard_sentry", post + out * 4.0)
	_halt(sgt, "idle", post + out * 3.0)
	_halt(drum, "guard_sentry", post + out * 4.0)
	say(drum, "drum", 2.4)
	await _sleep(2.4)
	for l in D["lines"]["sentence"]:
		bubble(sgt, l, 3.8)
		await _sleep(3.8)
	var n := int(fl["strokes"]) if not _smoke else 6
	var counts: Array = D["lines"]["count"]
	for k in n:
		if not _ok(victim) or not _ok(s1):
			break
		_act(s1, "attack_swing")
		await _sleep(0.35)
		if _ok(victim):
			Sfx.play("lash", (victim as Node3D).global_position + Vector3(0, 1.3, 0))
		_act(victim, "hit_react_back" if k % 2 == 0 else "hit_react")
		if k % 5 == 4 or k == n - 1:
			bubble(sgt, counts[mini(k, counts.size() - 1)], 1.2)      # the count, every fifth stroke
		elif k % 7 == 2:
			say(victim, "flog_cry", 1.4)
		if _msg_near("flogging", post, 7.0, {}, 5.0):
			_flag("flogging_seen", true)
		if k == n / 2:
			var c: Variant = _pickf(crowd + borrowed)
			if c:
				say(c, "flog_crowd", 2.4)
		await _sleep(float(fl["stroke_secs"]) - 0.35)
	_stat["flogging"] = n
	if _ok(victim):
		_act(victim, "knocked_down", true)
	await _sleep(3.0)
	for c in crowd:
		_leave(c)
	for w in borrowed:
		_give_back(w)
	if _ok(victim):
		Assets.clear_action(victim._figure)
		_act(victim, "get_up")
		await _sleep(2.2)
		victim.speed = 0.55
	# the escort takes him back into the Town Hall
	s1.script_goto(victim, 0.9)
	s2.script_goto(victim, 0.9)
	_goto(sgt, town_door, false, 30.0, true)
	_goto(drum, town_door, false, 30.0, true)
	await _goto(victim, town_door, false, 40.0, true)
	for a in [victim, s1, s2, sgt, drum]:
		_park(a)


# ================================================================== poverty

func _setup_poverty() -> void:
	var pv: Dictionary = D["poverty"]
	for b in pv["beggars"]:
		var f := _fig(b["models"], _v(b["pos"]), float(b["rot"]), "crouch_idle")
		if f:
			_beggars.append(f)
	if not _beggars.is_empty():
		var b0: Node3D = _beggars[0]
		_anchors["beggar"] = [b0.global_position, Vector3(1.6, 1.3, 2.8), 0.6]
	var fz: Dictionary = pv["freezing"]
	if portals.size() > int(fz["portal"]):
		var i := int(fz["portal"])
		var p := _wp(i, float(fz["lx"]), 0.0, float(fz["out"]))
		_freezer = _fig(fz["models"], p, float(portals[i][2]) + PI, "crouch_hide")
		if _freezer:
			_anchors["freezing"] = [p, Vector3(1.8, 1.5, 3.0), 0.5]
			_freezer_talk()
	# benches the drunks sleep on (dressing.gd _benches / _churchyard)
	_benches = [[Vector3(-12.0, 0, 11.4), PI], [Vector3(11.6, 0, -9.0), PI * 0.5], [Vector3(26.9, 0, -16.55), 0.0],
			[Vector3(17.2, 0, 17.6), -PI * 0.5], [Vector3(39.9, 0, -13.75), 0.0], [Vector3(42.6, 0, -10.75), PI]]


func _freezer_talk() -> void:
	while is_inside_tree() and not _frozen:
		await get_tree().create_timer(_rng.randf_range(40.0, 70.0), false).timeout
		if not _frozen and _ok(_freezer):
			say(_freezer, "freezing", 3.0)


func _freeze() -> void:
	_frozen = true
	if _ok(_freezer):
		Assets.play(_freezer, "crouch_hide", 0.0)
		_freezer.rotation.z = 0.18
		_freezer.rotation.x = -0.1
	_stat["frozen"] = true


func _ev_collect(_o: Dictionary) -> void:
	if not _ok(_freezer):
		return
	var fz: Dictionary = D["poverty"]["freezing"]
	var p: Vector3 = _freezer.global_position
	var out := Vector3(sin(_freezer.rotation.y + PI), 0, cos(_freezer.rotation.y + PI))    # toward the street
	var start := _spawn_near(p, 10.0)
	var m1 = _actor(fz["collectors"][0], start, 0.0)
	var m2 = _actor(fz["collectors"][1], start + Vector3(0.9, 0, 0), 0.0)
	_anchors["collect"] = [m1, Vector3(3.0, 1.8, 3.0), 0.8]
	if m1 == null or m2 == null:
		return
	var cart := Assets.instance("handcart")
	if cart:
		_strip_collision(cart)
		cart.set_meta("sl_prop", true)
		cart.position = Vector3(0, 0, -1.1)
		m1.add_child(cart)
	m2.script_goto(m1, 1.3)
	await _goto(m1, p + out * 2.2, false, 40.0)
	await _sleep(1.0)
	_halt(m1, "idle", p)
	await _goto(m2, p + out * 0.9, false, 10.0)
	_halt(m2, "idle", p)
	say(m2, "collectors", 3.2)
	await _sleep(3.2)
	_act(m2, "stand_to_crouch")
	say(m1, "collectors", 2.6)
	await _sleep(2.0)
	# lifted onto the cart under a sack
	_freezer.visible = false
	if cart:
		var body := _prim_box(Vector3(0.55, 0.28, 1.5), Color(0.22, 0.2, 0.17))
		body.position = Vector3(0, 0.68, 0)
		cart.add_child(body)
	_stat["collected"] = true
	m2.script_goto(m1, 1.2)
	await _leave(m1)
	_park(m2)


func _scavenger_loop() -> void:
	var sc: Dictionary = D["poverty"]["scavengers"]
	await _frames(40)
	var kids: Array = []
	while is_inside_tree():
		var on := _between(str(sc["from"]), str(sc["until"]))
		if on and kids.is_empty():
			for m in sc["models"]:
				var k = _actor(m, _nav_point(_v(_pickf(sc["points"]))), 0.0)
				if k:
					k.speed = 1.4
					kids.append(k)
			if not kids.is_empty():
				_anchors["scavengers"] = [kids[0], Vector3(2.5, 1.6, -2.8), 0.5]
				_stat["scavengers"] = kids.size()
		elif not on and not kids.is_empty():
			for k in kids:
				_leave(k, true)
			kids.clear()
		for k in kids:
			if not _ok(k) or k.has_meta("busy"):
				continue
			_scavenge_step(k)
		await get_tree().create_timer(2.0, false).timeout


func _scavenge_step(k) -> void:
	var sc: Dictionary = D["poverty"]["scavengers"]
	k.set_meta("busy", true)
	for g in _guards():
		if _flat(g.global_position, k.global_position) < float(sc["flee_guard"]):
			if _rng.randf() < 0.5:
				say(k, "scavenge", 2.0)
			var away: Vector3 = k.global_position - g.global_position
			away.y = 0.0
			await _goto(k, _nav_point(k.global_position + away.normalized() * 9.0), true, 8.0, true)
			await get_tree().create_timer(5.0, false).timeout
			if _ok(k):
				k.remove_meta("busy")
			return
	await _goto(k, _nav_point(_v(_pickf(sc["points"])) + Vector3(_rng.randf_range(-0.8, 0.8), 0, 0)), false, 15.0, true)
	if not _ok(k):
		return
	_halt(k, "crouch_idle")
	if _rng.randf() < 0.35:
		say(k, "scavenge", 2.4)
	await get_tree().create_timer(_rng.randf_range(4.0, 8.0), false).timeout
	if _ok(k):
		k.remove_meta("busy")


func _soup_loop() -> void:
	var s: Dictionary = D["poverty"]["soup"]
	await _frames(50)
	var server: Node3D = null
	var line: Array = []
	var S := _v(s["server"])
	var dir := _v(s["line_dir"]).normalized()
	var serve_t := 0.0
	while is_inside_tree():
		var on := _between(str(s["from"]), str(s["until"]))
		if on and server == null:
			server = _fig(s["models"]["server"], S, float(s["server_rot"]), "idle")
			_anchors["soup"] = [S + dir * 1.8, Vector3(-1.5, 1.7, 4.2), 1.0]
		if not on and server != null:
			server.queue_free()
			server = null
			for a in line:
				_leave(a)
			line.clear()
		if server:
			line = line.filter(func(a): return _ok(a))
			while line.size() < int(s["size"]):
				var slot := S + dir * float(s["gap"]) * (line.size() + 1)
				var a = _actor(_pickf(s["models"]["poor"]), _spawn_near(slot, 6.0) if not line.is_empty() else slot, 0.0)
				if a == null:
					break
				a.add_to_group("crowd")
				line.append(a)
			for k in line.size():
				var slot := S + dir * float(s["gap"]) * (k + 1)
				var a = line[k]
				if _flat(a.global_position, slot) > 0.4 and not a.has_meta("walking"):
					a.script_goto(slot)
				elif a.script_arrived:
					_halt(a, "idle", S)
			serve_t -= 1.0 * GameState.clock_scale
			if serve_t <= 0.0 and not line.is_empty():
				serve_t = float(s["serve_secs"])
				var front = line.pop_front()
				_serve(server, front)
		await get_tree().create_timer(1.0, false).timeout


func _serve(server: Node3D, a) -> void:
	if not _ok(a):
		return
	a.set_meta("walking", true)
	Assets.play_action(server, "haggle")
	if _rng.randf() < 0.5:
		say(server, "soup_server", 3.0)
	await _sleep(1.6)
	_act(a, "bow")
	say(a, "soup_poor", 2.6)
	_stat["soup"] = int(_stat.get("soup", 0)) + 1
	await _sleep(2.0)
	a.remove_meta("walking")
	await _leave(a)


# ================================================================== fights

func _ev_fight(o: Dictionary) -> void:
	var p := _player()
	var centre: Vector3 = o.get("at", p.global_position if p else Vector3.ZERO)
	var ev: Dictionary = D["events"]["fight"]
	var a = null
	var b = null
	var borrowed := false
	var alley: bool = o.get("alley", _rng.randf() < _table(ev["alley_share"], 0.1))
	if not alley and not o.has("extras"):
		# two townsfolk within near_player of the player, preferably by a tavern door
		var cands := _walkers_near(centre, float(D["near_player"]))
		var best := -INF
		for i in cands.size():
			for j in range(i + 1, cands.size()):
				var d := _flat(cands[i].global_position, cands[j].global_position)
				if d > 9.0:
					continue
				var mid: Vector3 = (cands[i].global_position + cands[j].global_position) * 0.5
				var score := -d + _rng.randf() * 3.0
				for ti in [10, 14, 5]:
					if ti < portals.size() and _flat(_door_of(ti), mid) < 10.0:
						score += float(ev["tavern_weight"]) * 3.0
				if score > best:
					best = score
					a = cands[i]
					b = cands[j]
		if a:
			_borrow(a)
			_borrow(b)
			borrowed = true
	var M: Vector3
	if a == null:
		# two drinkers out of a tavern door, or in a dark alley
		var spot: Vector3 = o.get("at", Vector3.ZERO)
		if not o.has("at"):
			var near: Array = []          # within near_player of the player: an alley, or a tavern door
			if alley:
				for q in D["drunks"]["alley_points"]:
					near.append(_v(q))
			else:
				for ti in [10, 14, 5]:
					if ti < portals.size():
						near.append(_door_of(ti, 3.0))
			near = near.filter(func(q): return _flat(q, centre) <= float(D["near_player"]))
			spot = _pickf(near) if not near.is_empty() else centre
		spot = _nav_point(spot)
		a = _actor(_pickf(D["drunks"]["models"]), _spawn_near(spot, 5.0), 0.0)
		b = _actor(_pickf(D["drunks"]["models"]), _spawn_near(spot, 5.0), 0.0)
		if a == null or b == null:
			return
		M = spot
	else:
		M = (a.global_position + b.global_position) * 0.5
	var ax: Vector3 = (a.global_position - M)
	ax.y = 0.0
	ax = ax.normalized() if ax.length() > 0.1 else Vector3.RIGHT
	_goto(a, _nav_point(M + ax * 0.75), false, 12.0)
	await _goto(b, _nav_point(M - ax * 0.75), false, 12.0)
	if not (_ok(a) and _ok(b)):
		return
	_halt(a, "idle", b)
	_halt(b, "idle", a)
	_anchors["fight"] = [M, Vector3(4.0, 2.0, 4.2), 1.1]
	# words first
	for w_i in 2:                     # one exchange of words, then fists
		var s = a if w_i % 2 == 0 else b
		say(s, "insult", 2.2)
		_act(s, "talk_gesture_a" if w_i % 2 == 0 else "talk_gesture_b")
		await _sleep(1.6)
	var seen := _disturb(M, 0.8, "fight")
	# onlookers gather in a ring: a crowd to blend into
	var crowd: Array = []
	for w in _walkers_near(M, 16.0, 4):
		_borrow(w)
		w.add_to_group("crowd")
		crowd.append(w)
		var ang := _rng.randf() * TAU
		w.script_goto(_nav_point(M + Vector3(cos(ang), 0, sin(ang)) * _rng.randf_range(2.6, 3.6)))
	if crowd.size() < 2 and (o.has("extras") or _instant):
		for c_i in 3:
			var ang := TAU * c_i / 3.0 + 0.4
			var c = _actor(_pickf(D["punishment"]["flogging"]["models"]["crowd"]), _nav_point(M + Vector3(cos(ang), 0, sin(ang)) * 3.0), 0.0)
			if c:
				c.add_to_group("crowd")
				c.set_meta("sl_extra", true)
				crowd.append(c)
	var dur := _rng.randf_range(8.0, 15.0)
	var t := 0.0
	var broken := false
	var rnd := 0
	while t < dur and _ok(a) and _ok(b):
		var att = a if rnd % 3 != 2 else b
		var def = b if att == a else a
		_act(att, "attack_swing" if _rng.randf() < 0.75 else "attack_thrust")
		await _sleep(0.35)
		_act(def, _pickf(["hit_react", "hit_react", "stagger", "hit_react_back"]))
		if rnd == 1:
			var c: Variant = _pickf(crowd)
			if c:
				say(c, "cheer", 2.0)
		await _sleep(_rng.randf_range(1.0, 1.6))
		t += 1.6
		rnd += 1
		for g in _guards():
			if _flat(g.global_position, M) < 3.5:
				broken = true
		if broken:
			break
	var loser = b if _rng.randf() < 0.5 else a
	var winner = a if loser == b else b
	if broken:
		bubble(a, _pick("cheer"), 1.6)
		_goto(a, _nav_point(a.global_position + ax * 8.0), true, 8.0, true)
		await _goto(b, _nav_point(b.global_position - ax * 8.0), true, 8.0, true)
	else:
		_act(loser, "knocked_down" if _rng.randf() < 0.6 else "knocked_down_forward", true)
		await _sleep(2.4)
		if _ok(loser):
			Assets.clear_action(loser._figure)
			_act(loser, "get_up")
			say(loser, "fight_down", 2.4)
		await _sleep(2.0)
		_halt(loser, "crouch_idle")
		await _sleep(3.0)
	_stat["fights"] = int(_stat["fights"]) + 1
	for c in crowd:
		if c.has_meta("sl_extra"):
			c.remove_meta("sl_extra")
			_leave(c)
		else:
			_give_back(c)
	if _ok(loser):
		loser.speed = 0.55      # limps off
	if borrowed:
		await _sleep(4.0)
		_give_back(winner)
		await _sleep(3.0)
		_give_back(loser)
	else:
		_leave(winner)
		await _leave(loser)
	if seen >= 0:
		_stat["fight_guards"] = seen


# ================================================================== crime

## Cutpurse: shadows someone in a crowd, brushes past, runs for an alley. The player can be the mark when standing
## in a crowd; one swing at him (he is `fair` while running) drops the coins as a purse to pick up with E.
func _ev_cutpurse(o: Dictionary) -> void:
	var p := _player()
	var cr: Dictionary = D["crime"]
	var on_player: bool = o.get("player", p != null and _player_in_crowd(p) and _rng.randf() < float(D["events"]["cutpurse"]["player_chance"]))
	var mark: Node3D = p if on_player else null
	if mark == null:
		var ws := _walkers_near(p.global_position if p else Vector3.ZERO, float(D["near_player"]))
		ws = ws.filter(func(w): return pop.crowd_count(w.global_position, Vector3.ZERO, 3.0) >= 2) if ws.size() > 3 else ws
		if ws.is_empty():
			return
		mark = _pickf(ws)
	var thief = _actor(cr["thief"], _spawn_near(mark.global_position, 7.0), 0.0, true)
	if thief == null:
		return
	thief.speed = 1.25
	# shadow the mark
	if not _instant:
		thief.script_goto(mark, 2.4)
		var t := 0.0
		while _ok(thief) and t < _rng.randf_range(6.0, 11.0):
			await get_tree().physics_frame
			t += get_physics_process_delta_time()
	# the brush: a quick sneak step in, a hand in the coat
	thief.script_goto(mark, 0.55)
	_act(thief, "sneak")
	var tt := 0.0
	while _ok(thief) and _flat(thief.global_position, mark.global_position) > 0.95 and tt < 5.0:
		await get_tree().physics_frame
		tt += get_physics_process_delta_time()
		if _instant and tt > 0.1:
			thief.global_position = mark.global_position + (thief.global_position - mark.global_position).normalized() * 0.8
	var stolen := 0
	if on_player:
		var take: Array = cr["cutpurse_take"]
		stolen = mini(_rng.randi_range(int(take[0]), int(take[1])), GameState.coins)
		GameState.coins -= stolen
		_msg("cutpurse_player", {"n": stolen}, 4.5)
	_stat["cutpurse"] = "hit" if (stolen > 0 or not on_player) else "miss"
	_stat["cutpurse_mark"] = "player" if on_player else "walker"
	# run
	thief.fair = true
	thief.add_to_group("takedown")
	thief.set_meta("stolen", stolen)
	thief.on_felled = _thief_felled
	thief.speed = 2.0
	var exit := _exit_near(thief.global_position)
	thief.script_goto(exit, 0.0, true)
	_anchors["cutpurse"] = [thief, Vector3(2.5, 1.7, 3.5), 1.0]
	if not on_player:
		get_tree().create_timer(2.0, false).timeout.connect(func() -> void:
			if _ok(mark) and not mark.has_meta("sl_busy"):
				say(mark, "thief_cry", 3.0)
				_disturb(mark.global_position, 0.6, "shout"))
	var run_t := 0.0
	var chased := false
	while _ok(thief) and not thief.is_downed() and not thief.script_arrived and run_t < 30.0:
		for g in _guards():
			if _guard_sees(g, thief.global_position, 16.0):
				if not chased:
					chased = true
					bubble(g, _pick("guard_chase"), 2.4)
					_stat["cutpurse_chased"] = true
				if g.has_method("follow_node") and g.get("task") is Dictionary and (g.get("task") as Dictionary).is_empty():
					g.follow_node(thief, 6.0)
				if _flat(g.global_position, thief.global_position) < 1.6:
					bubble(g, D["lines"]["guard_chase"][1], 2.4)
					thief.knock_down(20.0)
					_stat["cutpurse_caught"] = "guard"
		await get_tree().physics_frame
		run_t += get_physics_process_delta_time()
	if _ok(thief) and thief.is_downed():
		await get_tree().create_timer(6.0, false).timeout
	_park(thief)


func _thief_felled(thief) -> void:
	var n := int(thief.get_meta("stolen", 0))
	thief.fair = false
	if thief.is_in_group("takedown"):
		thief.remove_from_group("takedown")
	say(thief, "thief_caught", 2.8)
	_stat["cutpurse_caught"] = _stat.get("cutpurse_caught", "player")
	if n <= 0:
		return
	thief.set_meta("stolen", 0)
	_drop_purse(thief.global_position + Vector3(0.4, 0, 0.3), n)
	_msg("cutpurse_dropped", {}, 3.0)


func _drop_purse(at: Vector3, n: int) -> void:
	var purse := Node3D.new()
	purse.name = "DroppedPurse"
	purse.position = at
	add_child(purse)
	var m := MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 0.09
	sm.height = 0.13
	m.mesh = sm
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.38, 0.24, 0.12)
	m.material_override = mat
	m.position.y = 0.06
	purse.add_child(m)
	var ia := InteractableScript.new()
	ia.display_name = "Your purse"
	ia.prompt = "pick up your purse"
	ia.marker_height = 0.6
	ia.handler = func(_a: Node) -> bool:
		GameState.coins += n
		_msg("cutpurse_recovered", {"n": n}, 3.0)
		_stat["cutpurse_recovered"] = n
		purse.queue_free()
		return true
	purse.add_child(ia)


func _mug_spot(min_player := 15.0) -> Vector3:
	var p := _player()
	var ok: Array = []
	for s in D["crime"]["mug_spots"]:
		var v := _v(s)
		if _dark(v) and _clear_of_lanes(v) and _reachable(v) and (p == null or _flat(v, p.global_position) > min_player or _instant):
			ok.append(v)
	return _pickf(ok) if not ok.is_empty() else Vector3.INF


## Two thugs corner a lone walker in a dark alley: grabbed, shoved, purse taken, left sitting stunned.
func _ev_mugging(o: Dictionary) -> void:
	var cr: Dictionary = D["crime"]
	var spot: Vector3 = o.get("at", _mug_spot())
	if spot == Vector3.INF:
		return
	var victim = _actor(_pickf(cr["mug_victim"]), _spawn_near(spot, 10.0), 0.0)
	_anchors["mugging"] = [spot, Vector3(3.0, 1.8, 2.8), 1.0]
	var t1 = _actor(cr["thugs"][0], _nav_point(spot + Vector3(3.5, 0, 2.5)), 0.0, true)
	var t2 = _actor(cr["thugs"][1], _nav_point(spot + Vector3(-3.0, 0, -2.5)), 0.0, true)
	if victim == null or t1 == null or t2 == null:
		return
	_halt(t1, "idle", spot)
	_halt(t2, "idle", spot)
	await _goto(victim, spot, false, 40.0)
	if not _ok(victim):
		return
	t1.script_goto(victim, 0.85, true)
	t2.script_goto(victim, 0.85, true)
	if _instant:
		t1.global_position = victim.global_position + Vector3(0.8, 0, 0.3)
		t2.global_position = victim.global_position + Vector3(-0.8, 0, -0.3)
	await _sleep(2.0)
	_halt(victim, "idle", t1)
	say(t1, "mug_thug", 2.6)
	_act(victim, "grabbed")
	await _sleep(1.6)
	say(victim, "mug_victim", 2.6)
	_act(t2, "attack_swing")
	await _sleep(0.4)
	_act(victim, "shoved")
	await _sleep(1.4)
	_act(victim, "knocked_down", true)
	_disturb(spot, 0.5, "shout")
	await _sleep(1.2)
	_stat["mugging_walker"] = "robbed"
	_leave(t1)
	_leave(t2)
	await _sleep(3.0)
	if _ok(victim):
		Assets.clear_action(victim._figure)
		_act(victim, "get_up")
		await _sleep(2.0)
		_halt(victim, "crouch_idle")
		await _sleep(8.0)
		victim.speed = 0.7
		await _leave(victim)


## The player alone in a dark alley after 23:00: two thugs close in. Pay, fight (one swing fells each), or run;
## underworld influence >= underworld_pass and they nod you through.
func _ev_mug_player(o: Dictionary) -> void:
	var p := _player()
	if p == null:
		return
	var cr: Dictionary = D["crime"]
	var pp := p.global_position
	var fwd := -p.global_transform.basis.z
	fwd.y = 0.0
	fwd = fwd.normalized() if fwd.length() > 0.1 else Vector3.FORWARD
	var t1 = _actor(cr["thugs"][0], _nav_point(pp + fwd * (1.3 if _instant else 7.0)), 0.0, true)
	var t2 = _actor(cr["thugs"][1], _nav_point(pp - fwd * (1.3 if _instant else 6.0) + Vector3(0.5, 0, 0)), 0.0, true)
	if t1 == null or t2 == null:
		return
	if not _instant:
		t1.script_goto(p, 1.4, true)
		t2.script_goto(p, 1.4, true)
		var t := 0.0
		while t < 8.0 and _ok(t1) and _flat(t1.global_position, p.global_position) > 1.8:
			await get_tree().physics_frame
			t += get_physics_process_delta_time()
	_halt(t1, "idle", p)
	_halt(t2, "idle", p)
	_anchors["mug_player"] = [t1, Vector3(1.6, 1.7, 2.6), 1.3]
	if GameState.get_influence("underworld") >= int(cr["underworld_pass"]) and not o.get("force_dialogue", false):
		_act(t1, "bow")
		say(t1, "mug_pass", 3.2)
		_msg("mug_passed", {}, 3.5)
		_stat["mugging"] = "passed"
		await _sleep(3.0)
		_leave(t1)
		_leave(t2)
		return
	say(t1, "mug_thug", 3.0)
	_mug_state = {"result": "", "cost": int(cr["mug_cost"])}
	var pers: Variant = D["people"]["thug"]["personality"]
	_dlg_personality = str(_pickf(pers) if pers is Array else pers)
	if o.has("personality"):
		_dlg_personality = str(o["personality"])
	_dlg_names = {"$thug": "Thug", "$thug2": "The other thug", "$them": "Thug", "$you": "You"}
	_dlg_vars = {"cost": _mug_state["cost"]}
	_dlg_graph = cr["mugging_dialogue"]
	_dlg_resp = {}
	_dlg_who = t1
	_dlg_handler = func(action: String) -> String:
		_mug_state["result"] = action
		if action == "pay":
			GameState.coins -= mini(int(_mug_state["cost"]), GameState.coins)
			return "paid"
		return action
	_dlg_play("demand")
	var wait := 0.0
	var answers: Array = o.get("answers", [o["answer"]] if o.has("answer") else [])
	while str(_mug_state["result"]) == "" and _dlg.is_open and wait < 60.0:
		await get_tree().physics_frame
		wait += get_physics_process_delta_time()
		if _smoke and wait > 0.2 and not answers.is_empty() and _dlg.is_open:
			if answer(str(answers[0])):
				answers.pop_front()
			elif _dlg_node == "__response":
				_dlg.advance()
	var result := [str(_mug_state["result"])]
	var cost := int(_mug_state["cost"])
	if result[0] == "":
		result[0] = "run"
	var linger := 0.0
	while _dlg.is_open and linger < 2.5 and not _smoke:      # let the last line be read
		await get_tree().physics_frame
		linger += get_physics_process_delta_time()
	_dlg.close()
	match result[0]:
		"cowed":
			_stat["mugging"] = "cowed"
			_act(t1, "bow")
			await _sleep(1.5)
			_leave(t1)
			_leave(t2)
		"pay":
			_msg("mug_paid", {"n": cost}, 3.5)
			_stat["mugging"] = "paid"
			await _sleep(1.5)
			_leave(t1)
			_leave(t2)
		"fight":
			_stat["mugging"] = await _mug_fight(p, t1, t2)
		_:
			say(t1, "mug_fled", 2.4)
			_stat["mugging"] = "ran"
			t1.script_goto(p, 1.0, true)
			t2.script_goto(p, 1.0, true)
			await _sleep(5.0)
			_msg("mug_ran", {}, 3.0)
			_leave(t1)
			_leave(t2)


## A thug's blow: one health, never the last one (the watch beats you senseless, thugs just rob you).
func _cudgel(p: Node3D, from: Node3D, key := "cudgel") -> void:
	var h := int(p.get("health"))
	if h <= 1:
		return
	p.set("health", h - 1)
	p.set("_lock", 0.35)
	var push := p.global_position - from.global_position
	push.y = 0.0
	p.set("velocity", p.get("velocity") + push.normalized() * 2.5)
	var fig: Node3D = p.get("_figure")
	if fig:
		Assets.play_action(fig, "hit_react")
	if key == "cudgel":
		Mission.message.emit("A cudgel across the shoulders! (%d of %d)" % [h - 1, int(Player.MAX_HEALTH)], 1.5)
	else:
		_msg(key, {"h": h - 1, "max": int(Player.MAX_HEALTH)}, 2.0)


func _mug_fight(p: Node3D, t1, t2) -> String:
	var down := [0]
	for t in [t1, t2]:
		t.fair = true
		t.add_to_group("takedown")
		t.on_felled = func(_x) -> void: down[0] += 1
	var cd := [0.8, 1.5]
	var t := 0.0
	while down[0] < 2 and t < 30.0 and is_instance_valid(p):
		for k in 2:
			var th = [t1, t2][k]
			if not _ok(th) or th.is_downed():
				continue
			th.script_goto(p, 1.05, true)
			cd[k] -= get_physics_process_delta_time()
			if cd[k] <= 0.0 and _flat(th.global_position, p.global_position) < 1.6:
				cd[k] = _rng.randf_range(1.4, 2.2)
				_act(th, "attack_swing")
				_cudgel(p, th)
		await get_tree().physics_frame
		t += get_physics_process_delta_time()
	if down[0] >= 2:
		_msg("mug_fought", {}, 4.0)
		await get_tree().create_timer(8.0, false).timeout
		_park(t1)
		_park(t2)
		return "fought"
	var n := mini(int(D["crime"]["mug_cost"]), GameState.coins)
	GameState.coins -= n
	Mission.message.emit("Beaten in the snow, you feel them take %d złoty." % n, 3.5)
	_leave(t1)
	_leave(t2)
	return "beaten"


## A burglar prising a shutter behind the row; flees when the player comes near. Seeing him: Mission flag "saw_burglar".
func _ev_burglar(o: Dictionary) -> void:
	var sp: Dictionary = o.get("spot", _pickf(D["crime"]["burglar_spots"]))
	var pos := _v(sp["pos"])
	var rot := float(sp["rot"])
	var b = _actor(D["crime"]["burglar"], _nav_point(pos), rot, true)
	if b == null:
		return
	b.global_position = pos
	b.rotation.y = rot
	_halt(b, "haggle", pos + Vector3(-sin(rot), 0, -cos(rot)) * 2.0)      # at the shutter, back to the alley
	if Assets.has_clip(b._figure, "climb_short") and _rng.randf() < 0.5:
		_act(b, "climb_short")
	_anchors["burglar"] = [pos, Vector3(2.5, 1.6, 2.5).rotated(Vector3.UP, rot), 1.2]
	var t := 0.0
	var fled := false
	var dur := 40.0 * (0.12 if _smoke else 1.0)
	_stat["burglar"] = "prying"
	while _ok(b) and t < dur:
		var p := _player()
		if p:
			var d := _flat(p.global_position, pos)
			if d < 15.0 and not _saw_burglar and Perception.clear_line(get_world_3d().direct_space_state, p.global_position + Vector3(0, 1.5, 0), pos + Vector3(0, 1.2, 0), [p.get_rid(), b.get_rid()], null, true):
				_saw_burglar = true
				_flag("saw_burglar", true)
				_msg("saw_burglar", {}, 5.0)
			if d < 9.0:
				fled = true
				break
		if _rng.randf() < 0.004:
			say(b, "burglar", 2.0)
		await get_tree().create_timer(0.25, false).timeout
		t += 0.25
	_stat["burglar"] = "fled" if fled else ("seen" if _saw_burglar else "in")
	if not _ok(b):
		return
	if fled:
		bubble(b, D["lines"]["burglar"][1], 2.2)
		b.speed = 2.0
		b.fair = true
		b.add_to_group("takedown")
		await _goto(b, _exit_near(pos), true, 20.0, true)
	else:
		b._set_hidden(true)          # in through the shutter
		await get_tree().create_timer(4.0, false).timeout
	_park(b)


## After midnight a fence at the wine cellar hatch buys a bundle from a thief; whispers, coins, down the hatch.
func _ev_fence(_o: Dictionary) -> void:
	var cr: Dictionary = D["crime"]
	var spot := _v(cr["fence_spot"])
	var fence = _actor(cr["fence"], spot, PI, false)
	var seller = _actor(cr["thief"], _spawn_near(spot, 12.0), 0.0, true)
	_anchors["fence"] = [spot, Vector3(2.4, 1.6, 2.6), 1.1]
	if fence == null or seller == null:
		return
	fence.global_position = spot
	var bundle := Props.bundle()
	bundle.set_meta("sl_prop", true)
	bundle.scale = Vector3.ONE * 0.7
	bundle.position = Vector3(0, 0.8, -0.28)
	seller.add_child(bundle)
	await _goto(seller, spot + Vector3(0, 0, 1.0), false, 40.0)
	if not _ok(seller):
		return
	_halt(seller, "idle", fence)
	_halt(fence, "idle", seller)
	for k in 4:
		var who = fence if k % 2 == 0 else seller
		bubble(who, D["lines"]["fence"][k], 2.4)
		_act(who, "haggle")
		await _sleep(2.3)
	if is_instance_valid(bundle):
		bundle.get_parent().remove_child(bundle)
		fence.add_child(bundle)
	_stat["fence"] = true
	_leave(seller)
	await _sleep(2.0)
	if _ok(fence):
		fence._set_hidden(true)
		await get_tree().create_timer(1.0, false).timeout
		_park(fence)


# ================================================================== occupation

func _soldiers(n: int, at: Vector3, corporal := false) -> Array:
	var oc: Dictionary = D["occupation"]
	var out: Array = []
	for k in n:
		var m: Array = oc["corporal"] if corporal and k == 0 else oc["soldier"]
		var s = _actor(m, _nav_point(at + Vector3(0.9 * k, 0, 0.5 * k)), 0.0)
		if s:
			s.set_meta("soldier", true)
			out.append(s)
	return out


## Someone crossing the square: an extra from a door walking toward another door (or the given point).
func _passerby(models: Array, near: Vector3) -> Array:
	var from := _spawn_near(near, 8.0)
	var to := _nav_point(near)
	var a = _actor(models, from, _yaw_to(from, to))
	return [a, to]


func _ev_arrest(o: Dictionary) -> void:
	var oc: Dictionary = D["occupation"]
	var p := _player()
	var near: Vector3 = o.get("at", _nav_point((p.global_position if p else Vector3.ZERO) + Vector3(_rng.randf_range(-14, 14), 0, _rng.randf_range(-14, 14))))
	var pb := _passerby(_pickf(oc["victim"]), near)
	var v = pb[0]
	if v == null:
		return
	var sol := _soldiers(2, _spawn_near(near, 8.0))
	if sol.size() < 2:
		return
	await _goto(v, pb[1], false, 30.0)
	for s in sol:
		s.script_goto(v, 1.0, true)
	if _instant:
		sol[0].global_position = v.global_position + Vector3(1.0, 0, 0.2)
		sol[1].global_position = v.global_position + Vector3(-1.0, 0, 0.2)
	_anchors["arrest"] = [v, Vector3(3.0, 1.8, 3.0), 1.1]
	await _sleep(3.0)
	_halt(v, "idle", sol[0])
	for s in sol:
		_halt(s, "idle", v)
	say(sol[0], "arrest_soldier", 2.6)
	_act(v, "haggle")
	await _sleep(2.4)
	say(v, "arrest_victim", 2.6)
	await _sleep(1.2)
	bubble(sol[1], D["lines"]["arrest_soldier"][1], 2.6)
	_act(v, "grabbed")
	_act(sol[1], "guard_seize")
	await _sleep(2.0)
	_stat["arrest"] = true
	# marched off to the barracks
	var exit := _v(oc["barracks_exit"])
	for s in sol:
		s.script_goto(v, 0.9)
	await _goto(v, exit, false, 60.0, true)
	_park(v)
	for s in sol:
		_park(s)


func _ev_pressgang(o: Dictionary) -> void:
	var oc: Dictionary = D["occupation"]
	var p := _player()
	var near: Vector3 = o.get("at", _nav_point((p.global_position if p else Vector3.ZERO) + Vector3(_rng.randf_range(-12, 12), 0, _rng.randf_range(-12, 12))))
	var pb := _passerby(oc["youth"], near)
	var y = pb[0]
	_anchors["pressgang"] = [y, Vector3(3.0, 1.8, -3.0), 1.1]
	var m = _actor(oc["mother"], (y.global_position if y else near) + Vector3(0.7, 0, 0.3), 0.0)
	if y == null or m == null:
		return
	m.script_goto(y, 1.0)
	var sol := _soldiers(3, _spawn_near(near, 8.0), true)
	if sol.size() < 2:
		return
	await _goto(y, pb[1], false, 30.0)
	for s in sol:
		s.script_goto(y, 1.1, true)
	if _instant:
		for k in sol.size():
			sol[k].global_position = y.global_position + Vector3(cos(k * 2.1), 0, sin(k * 2.1)) * 1.1
		m.global_position = y.global_position + Vector3(0.6, 0, 1.0)
	await _sleep(3.0)
	for s in sol:
		_halt(s, "idle", y)
	_halt(y, "idle", sol[0])
	say(sol[0], "press_corporal", 3.0)
	await _sleep(2.6)
	_act(y, "grabbed")
	_act(sol[1], "guard_seize")
	say(y, "press_youth", 2.0)
	await _sleep(1.2)
	_halt(m, "idle", y)
	say(m, "press_mother", 3.0)
	_act(m, "talk_gesture_b")
	await _sleep(2.8)
	bubble(sol[0], D["lines"]["press_corporal"][1], 2.8)
	_stat["pressgang"] = true
	var exit := _v(oc["barracks_exit"])
	for s in sol:
		s.script_goto(y, 1.0)
	m.script_goto(y, 1.6)
	_goto(y, exit, false, 60.0, true)
	await _sleep(8.0)
	if _ok(m):
		_halt(m, "crouch_idle")
		bubble(m, D["lines"]["press_mother"][1], 3.0)
		await _sleep(5.0)
		_leave(m)
	await _sleep(20.0)
	_park(y)
	for s in sol:
		_park(s)


func _ev_harass(o: Dictionary) -> void:
	var oc: Dictionary = D["occupation"]
	var p := _player()
	var priest: bool = o.get("priest", _rng.randf() < 0.4)
	var near: Vector3 = o.get("at", _nav_point((p.global_position if p else Vector3.ZERO) + Vector3(_rng.randf_range(-12, 12), 0, _rng.randf_range(-12, 12))))
	var pb := _passerby(oc["uniate_priest"] if priest else oc["pedlar"], near)
	var v = pb[0]
	_anchors["harass"] = [v, Vector3(2.8, 1.8, 3.0), 1.1]
	if v == null:
		return
	var sol := _soldiers(2, _spawn_near(near, 8.0))
	if sol.size() < 2:
		return
	await _goto(v, pb[1], false, 30.0)
	for s in sol:
		s.script_goto(v, 1.0, true)
	if _instant:
		sol[0].global_position = v.global_position + Vector3(0.9, 0, 0.5)
		sol[1].global_position = v.global_position + Vector3(-0.9, 0, 0.5)
	await _sleep(3.0)
	_halt(v, "idle", sol[0])
	for s in sol:
		_halt(s, "idle", v)
	var sk := "harass_soldier_priest" if priest else "harass_soldier"
	var vk := "harass_priest" if priest else "harass_pedlar"
	bubble(sol[0], D["lines"][sk][0], 2.6)
	await _sleep(2.2)
	bubble(v, D["lines"][vk][0], 2.8)
	_act(v, "haggle")
	await _sleep(2.4)
	_act(sol[1], "musket_butt" if Assets.has_clip(sol[1]._figure, "musket_butt") else "attack_thrust")
	await _sleep(0.3)
	_act(v, "shoved")
	bubble(sol[1], D["lines"][sk][1], 2.6)
	await _sleep(2.4)
	bubble(v, D["lines"][vk][1], 2.8)
	_act(v, "bow")
	await _sleep(2.0)
	if not priest:
		bubble(sol[0], D["lines"]["harass_soldier"][2], 2.4)
	_stat["harass"] = "priest" if priest else "pedlar"
	await _sleep(1.5)
	for s in sol:
		_leave(s)
	v.speed = 1.3
	await _leave(v)


func _ev_requisition(o: Dictionary) -> void:
	var oc: Dictionary = D["occupation"]
	var p := _player()
	var near: Vector3 = o.get("at", _nav_point((p.global_position if p else Vector3.ZERO) + Vector3(_rng.randf_range(-12, 12), 0, _rng.randf_range(-12, 12))))
	var pb := _passerby(oc["peasant"], near)
	var v = pb[0]
	_anchors["requisition"] = [v, Vector3(3.2, 1.8, 2.6), 1.0]
	if v == null:
		return
	v.speed = 0.8
	var cart := Assets.instance("handcart")
	if cart:
		_strip_collision(cart)
		cart.set_meta("sl_prop", true)
		cart.position = Vector3(0, 0, -1.05)
		v.add_child(cart)
		for k in 5:
			var lg := _prim_cyl(0.07, 0.8, Color(0.36, 0.26, 0.17))
			lg.rotation.x = PI * 0.5
			lg.position = Vector3(-0.28 + 0.14 * k, 0.66 + 0.05 * (k % 2), 0)
			cart.add_child(lg)
	var sol := _soldiers(2, _spawn_near(near, 8.0))
	if sol.size() < 2:
		return
	await _goto(v, pb[1], false, 30.0)
	for s in sol:
		s.script_goto(v, 1.2, true)
	if _instant:
		sol[0].global_position = v.global_position + Vector3(1.4, 0, 0.3)
		sol[1].global_position = v.global_position + Vector3(-1.4, 0, 0.6)
	await _sleep(3.0)
	_halt(v, "idle", sol[0])
	for s in sol:
		_halt(s, "idle", v)
	say(sol[0], "requisition_soldier", 3.0)
	await _sleep(2.6)
	say(v, "requisition_peasant", 3.0)
	_act(v, "talk_gesture_b")
	await _sleep(2.6)
	_act(sol[1], "shoved")
	_act(v, "shoved")
	bubble(sol[0], D["lines"]["requisition_soldier"][1], 2.6)
	if cart and is_instance_valid(cart):
		v.remove_child(cart)
		sol[1].add_child(cart)
	_stat["requisition"] = true
	await _sleep(2.0)
	_halt(v, "crouch_idle")
	_goto(sol[0], _v(oc["barracks_exit"]), false, 60.0, true)
	sol[1].script_goto(sol[0], 1.6)
	await _sleep(8.0)
	if _ok(v):
		bubble(v, D["lines"]["requisition_peasant"][0], 3.0)
		await _sleep(4.0)
		_leave(v)
	await _sleep(25.0)
	for s in sol:
		_park(s)


## A corporal tears the printed leaf off the inn yard's notice board and burns a sheaf at the watch brazier.
func _ev_poster(_o: Dictionary) -> void:
	var oc: Dictionary = D["occupation"]
	var board := _v(oc["notice_board"])
	_anchors["poster"] = [board, Vector3(-2.6, 1.8, -3.2), 1.2]
	if _poster == null or not is_instance_valid(_poster):
		_poster = Node3D.new()
		_poster.name = "Poster"
		_poster.position = board + Vector3(0, 1.05, -0.05)
		add_child(_poster)
		var q := _prim_box(Vector3(0.42, 0.56, 0.005), Color(0.86, 0.82, 0.7))
		_poster.add_child(q)
		var t := Label3D.new()
		t.text = "KONSTYTUCJA\n3 MAJA\n(The Constitution\nof the Third of May)"
		t.font_size = 22
		t.pixel_size = 0.0024
		t.modulate = Color(0.1, 0.06, 0.04)
		t.outline_size = 0
		t.position = Vector3(0, 0, -0.006)
		t.rotation.y = PI
		_poster.add_child(t)
	_poster.visible = true
	var c = _soldiers(1, _spawn_near(board, 8.0), true)
	if c.is_empty():
		return
	var cp = c[0]
	await _goto(cp, board + Vector3(0, 0, -0.95), false, 40.0)
	_halt(cp, "idle", board)
	await _sleep(1.0)
	_act(cp, "attack_swing")
	await _sleep(0.5)
	_poster.visible = false
	say(cp, "poster_corporal", 3.0)
	await _sleep(2.4)
	var br := _v(oc["brazier"])
	await _goto(cp, br + Vector3(-1.0, 0, -0.6), false, 40.0)
	_halt(cp, "idle", br)
	_act(cp, "window_throw" if Assets.has_clip(cp._figure, "window_throw") else "attack_thrust")
	var flare := FlickerLight.new()
	flare.amount = 0.4
	flare.speed = 12.0
	flare.position = br + Vector3(0, 1.3, 0)
	flare.light_color = Color(1.0, 0.6, 0.25)
	flare.light_energy = 6.0
	flare.omni_range = 9.0
	add_child(flare)
	get_tree().create_timer(5.0, false).timeout.connect(flare.queue_free)
	bubble(cp, D["lines"]["poster_corporal"][1], 3.0)
	_anchors["poster_burn"] = [br, Vector3(2.8, 1.8, -2.6), 1.0]
	var ws := _walkers_near(br, 14.0, 1)
	if not ws.is_empty():
		say(ws[0], "poster_onlooker", 3.0)
	_flag("posters_burned", true)
	_msg_near("posters", br, 8.0, {}, 4.5)
	_stat["poster"] = true
	await _sleep(3.0)
	await _leave(cp)
	get_tree().create_timer(30.0 / maxf(GameState.clock_scale, 0.1), false).timeout.connect(func() -> void:
		if _poster and is_instance_valid(_poster):
			_poster.visible = true)


## After the curfew bell: two soldiers beat a drunk who did not go home.
func _ev_curfew(o: Dictionary) -> void:
	var d = o.get("drunk", null)
	if d == null:
		for x in _drunks:
			if _ok(x) and not x.has_meta("asleep") and not x.has_meta("held"):
				d = x
				break
	if d == null:
		return
	d.set_meta("held", true)
	_anchors["curfew"] = [d, Vector3(3.0, 1.8, 2.8), 0.9]
	_halt(d, "idle")
	var sol := _soldiers(2, _spawn_near(d.global_position, 8.0))
	if sol.size() < 2:
		d.remove_meta("held")
		return
	for s in sol:
		s.script_goto(d, 1.0, true)
	if _instant:
		sol[0].global_position = d.global_position + Vector3(1.0, 0, 0.3)
		sol[1].global_position = d.global_position + Vector3(-1.0, 0, 0.3)
	await _sleep(3.0)
	for s in sol:
		_halt(s, "idle", d)
	_face_now(d, sol[0].global_position)
	say(sol[0], "curfew_soldier", 2.8)
	await _sleep(2.2)
	say(d, "curfew_drunk", 2.4)
	for k in 4:
		var s = sol[k % 2]
		_act(s, "musket_butt" if Assets.has_clip(s._figure, "musket_butt") else "attack_swing")
		await _sleep(0.35)
		_act(d, "hit_react" if k < 3 else "knocked_down", k == 3)
		await _sleep(0.9)
	_stat["curfew_beating"] = true
	for s in sol:
		_leave(s)
	await _sleep(12.0)
	if _ok(d):
		Assets.clear_action(d._figure)
		_act(d, "get_up")
		await _sleep(2.0)
		d.remove_meta("held")


## A customer who will not pay: the doorman throws him into the street and the brawl spills over.
func _ev_bill_fight(_o: Dictionary) -> void:
	if brothel_door == Vector3.ZERO or _doorman == null:
		return
	var c = _actor(_pickf(D["brothel"]["customers"]["models"]), brothel_door + _b_out * 1.2, _b_rot + PI)
	_anchors["bill_fight"] = [c, Vector3(3.0, 1.8, 3.0), 1.0]
	if c == null:
		return
	var seat: Vector3 = _doorman.position
	_doorman.position = brothel_door + _b_out * 1.3 + Basis(Vector3.UP, _b_rot) * Vector3(-0.8, 0, 0)
	_doorman.rotation.y = _yaw_to(_doorman.position, c.global_position)
	Assets.play(_doorman, "idle")
	_halt(c, "idle", _doorman.global_position)
	say(_doorman, "bill_doorman", 2.6)
	await _sleep(2.0)
	say(c, "bill_customer", 2.6)
	_act(c, "talk_gesture_b")
	await _sleep(2.2)
	Assets.play_action(_doorman, "attack_thrust")
	await _sleep(0.3)
	_act(c, "shoved")
	await _goto(c, brothel_door + _b_out * 3.4, false, 4.0)
	_doorman.position = brothel_door + _b_out * 2.6
	_doorman.rotation.y = _yaw_to(_doorman.position, c.global_position)
	_halt(c, "idle", _doorman.global_position)
	var crowd: Array = []
	for w in _walkers_near(brothel_door, 14.0, 2):
		_borrow(w)
		w.add_to_group("crowd")
		crowd.append(w)
		w.script_goto(_nav_point(brothel_door + _b_out * 5.0 + Vector3(_rng.randf_range(-2, 2), 0, _rng.randf_range(-2, 2))))
	_disturb(brothel_door + _b_out * 3.0, 0.7, "fight")
	for k in 3:
		Assets.play_action(_doorman, "attack_swing")
		await _sleep(0.35)
		_act(c, "hit_react" if k < 2 else "knocked_down", k == 2)
		if k == 1 and not crowd.is_empty():
			say(crowd[0], "cheer", 2.0)
		await _sleep(1.2)
	_stat["bill_fight"] = true
	await _sleep(2.5)
	_doorman.position = seat
	_doorman.rotation.y = _b_rot + PI
	Assets.play(_doorman, "sit_idle")
	for w in crowd:
		_give_back(w)
	if _ok(c):
		Assets.clear_action(c._figure)
		_act(c, "get_up")
		await _sleep(1.8)
		bubble(c, D["lines"]["bill_customer"][1], 2.6)
		c.speed = 0.7
		await _leave(c)


## The Visitation: a patrol at the door; the women go in; the madam argues and pays; the patrol moves on.
func _ev_raid(_o: Dictionary) -> void:
	if brothel_door == Vector3.ZERO:
		return
	_raid_on = true
	_anchors["raid"] = [brothel_door, _b_out * 6.0 + Vector3(0, 2.0, 0) + Basis(Vector3.UP, _b_rot) * Vector3(-2.5, 0, 0), 1.2]
	_stat["raid"] = true
	var start := _nearest(_entries(), brothel_door, 12.0) if not _instant else brothel_door + _b_out * 4.0
	var sol := _soldiers(3, start, true)
	for w in _women:
		say(w, "raid_women", 2.0)
	await _sleep(1.5)
	for w in _women:
		w.visible = false
	for c in _customers:
		if _ok(c) and not c.has_meta("inside"):
			_leave(c, true)
	_msg_near("raid", brothel_door, 8.0)
	for k in sol.size():
		_goto(sol[k], brothel_door + _b_out * 1.8 + Basis(Vector3.UP, _b_rot) * Vector3((k - 1) * 0.9, 0, 0), false, 50.0)
	await _sleep(2.0 if _instant else 18.0)
	for s in sol:
		_halt(s, "idle", brothel_door)
	if not sol.is_empty():
		say(sol[0], "raid_soldier", 3.0)
	await _sleep(2.6)
	if _madam:
		say(_madam, "raid_madam", 3.4)
		Assets.play_action(_madam, "haggle")
	await _sleep(float(D["brothel"]["raid"]["secs"]) * 0.5)
	if _madam:
		bubble(_madam, D["lines"]["raid_madam"][1], 3.0)
		Assets.play_action(_madam, "bow")
	await _sleep(float(D["brothel"]["raid"]["secs"]) * 0.5)
	for s in sol:
		_leave(s)
	await _sleep(3.0 if _instant else 25.0)
	for w in _women:
		w.visible = true
		Assets.play(w, str(w.get_meta("clip", "idle")))
	_raid_on = false


# ================================================================== smoke and shots

func _smoke_main() -> void:
	# wait for the navmesh
	for i in 600:
		if district and district.has_method("nav_ready") and district.nav_ready():
			break
		await get_tree().physics_frame
	await _frames(10)
	if not is_inside_tree():
		return
	if "--street-sim" in OS.get_cmdline_user_args():
		await _sim()
		return
	var shots := _shot_dir != "" and DisplayServer.get_name() != "headless" and not _shot_done
	_instant = true
	_ts = 0.25 if shots else 0.15
	var coins0 := GameState.coins
	var infl0 := GameState.get_influence("underworld")
	GameState.set_influence("underworld", 0)          # so the thugs do not wave the player through
	_flog_done = true
	_raid_done = true
	_collected = true
	set_meta("force_drunks", 4)
	for k in 4:
		var d = _spawn_drunk(_v(D["drunks"]["square_points"][k]))
		if k == 0 and d:
			drunk_sleep(d, true)
			var bi := int(d.get_meta("sleep_spot", 0))
			var bo := Vector3(sin(float(_benches[bi][1])), 0, cos(float(_benches[bi][1])))
			_anchors["drunk_bench"] = [d, bo * 2.4 + Vector3(bo.z, 0, -bo.x) * 1.2 + Vector3(0, 1.3, 0), 0.7]
	if shots:
		_shot_done = true
	var jobs := {
		"fight": {"at": _nav_point(_door_of(10, 3.2) if portals.size() > 10 else Vector3(-24.0, 0, -12.0)), "extras": true},
		"cutpurse": {"player": true},
		"mug_player": {"answers": ["talk", "joke", "pay"], "personality": "vengeful", "force_dialogue": true},
		"raid": {},
		"flogging": {},
		"arrest": {"at": _nav_point(Vector3(8.0, 0, -16.0))},
		"pressgang": {"at": _nav_point(Vector3(-4.0, 0, 13.0))},
		"harass": {"at": _nav_point(Vector3(10.0, 0, 18.0)), "priest": false},
		"requisition": {"at": _nav_point(Vector3(-18.0, 0, -18.0))},
		"poster": {},
		"curfew": {},
		"bill_fight": {},
		"burglar": {},
		"fence": {},
		"mugging": {"at": _mug_spot(0.0)},
	}
	# shots: start the short scenes late so they are mid-action when the camera comes round
	var delay := {"cutpurse": 2.2, "mugging": 1.0, "burglar": 1.6, "fence": 0.8, "bill_fight": 1.0, "curfew": 1.0, "raid": 1.0} if shots else {}
	if shots:
		jobs.erase("mug_player")      # staged on its own for the dialogue shot
	for k in jobs:
		if k == "mugging" and jobs[k]["at"] == Vector3.INF:
			continue
		if delay.has(k):
			get_tree().create_timer(float(delay[k]), false).timeout.connect(start_event.bind(k, true, jobs[k]))
		else:
			start_event(k, true, jobs[k])
	pimp_collect()
	jeer()
	var ck0 := GameState.crackdown
	riot(_nav_point(Vector3(12.0, 0, 6.0)), 0.95, "bread and the new tax")
	fire.rate = 10.0 if not shots else 1.0
	FireScript.ignite(Vector3(14.0, 0, 13.0), get_tree())
	_anchors["fire"] = [Vector3(14.0, 0, 13.0), Vector3(-3.5, 2.2, -4.0), 1.0]
	_freeze()
	start_event("collect", true)
	_customer(1)
	if shots:
		await get_tree().create_timer(2.8, false).timeout
		await _shoot_all(["drunk_bench", "fight", "cutpurse", "flogging", "raid", "riot", "fire", "bard", "arrest", "pressgang", "harass",
				"requisition", "curfew", "bill_fight", "poster", "poster_burn", "collect", "mugging", "burglar", "fence"])
		await _shoot_mug_dialogue()
	var t := 0.0
	while t < 14.0 and is_inside_tree():
		await get_tree().physics_frame
		t += get_physics_process_delta_time()
		if _stat.has("fence") and _stat.has("poster") and str(_stat["mugging"]) != "none" and int(_stat["fights"]) > 0 and _stat.has("flogging") \
				and _stat.has("bill_fight") and _stat.has("curfew_beating") and _stat.has("collected") and _stat.has("arrest"):
			break
	# the madam: buy the gossip, then the room (into the lodging-house interior), then put the player back
	var madam := "none"
	var tones: Array = []
	var p := _player()
	if p and _madam and not shots:
		var back := p.global_position
		var wt := 0.0
		while _raid_on and wt < 10.0:          # the Visitation first has to leave
			await get_tree().physics_frame
			wt += get_physics_process_delta_time()
		var told := PackedStringArray()
		for k in 2:
			if _on_madam(p) and answer("gossip"):
				told.append(_dlg_node)
				await _frames(2)
				_dlg.close()
		if _on_madam(p) and answer("room"):
			await _frames(3)
			madam = "%s,room(%s,flag=%s)" % [",".join(told), "interior" if p.global_position.y < -50.0 else "doorway", Mission.has_flag("brothel_room")]
			_dlg.close()
		# the others, each answered in one tone: personality x tone decides what comes back
		var hp := int(p.get("health"))
		for spec in [["doorman", _doorman, "threat"], ["prisoner", _prisoners[0] if not _prisoners.is_empty() else null, "joke"],
				["bard", _bard, "bribe"], ["pimp", _pimp, "joke"]]:
			if spec[1] != null and _talk_to(spec[0], spec[1]) and answer(spec[2]):
				await _frames(2)
				tones.append("%s(%s):%s->%s" % [spec[0], _dlg_personality, spec[2], str(_response(spec[2]).get("effect", "line"))])
				_dlg.close()
			else:
				tones.append("%s:none" % spec[0])
		p.set("health", hp)
		if interiors:
			interiors.set("_return", {})
		if p.get("hidden_spot") != null:
			p.leave_spot()
		p.global_position = back
		p.reset_physics_interpolation()
		_room_left = 0.0
		_flag("brothel_room", false)
	var rt := 0.0
	while (riot_state.get("on", false) or not fire.burning.is_empty()) and rt < 10.0:
		await get_tree().physics_frame
		rt += get_physics_process_delta_time()
	GameState.crackdown = ck0
	GameState.coins = coins0
	GameState.set_influence("underworld", infl0)
	remove_meta("force_drunks")
	print("[smoke] street_life brothel=(%.1f, %.1f) drunks=%d fights=%d cutpurse=%s mugging=%s raid=%s" % [brothel_door.x, brothel_door.z,
			int(_stat["drunks"]), int(_stat["fights"]), _stat["cutpurse"], _stat["mugging"], _stat["raid"]])
	print("[smoke] riot peak=%d outcome=%s smashed=%d dead=%d fires=%d" % [int(_stat.get("riot_peak_n", 0)), riot_state.get("outcome", "running"),
			int(riot_state.get("smashed", 0)), int(riot_state.get("dead", 0)), int(riot_state.get("fires", 0))])
	print("[smoke] fire spread=%d extinguished=%s burning=%d out=%d" % [fire.spread_count, fire.burning.is_empty(), fire.burning.size(), fire.out_count])
	print("[smoke] street_life madam=%s gossip_flags=%s talk=%s mug_tone=%s bard=%s" % [madam, ",".join(_gossip_told), " ".join(tones),
			_stat.get("tone_joke", "none"), _bard != null])
	print("[smoke] street_life extra prisoners=%d pillory=%s stocks=%s whipping_post=%s gallows=%s flogging=%s jeer=%s beggars=%d frozen=%s collected=%s scavengers=%s soup=%s asleep=%s" % [
			_prisoners.size(), _prop_state("pillory"), _prop_state("stocks"), _prop_state("flogging"), _prop_state("gallows"), _stat.get("flogging", "none"),
			_stat.get("jeer", "none"), _beggars.size(), _stat.get("frozen", false), _stat.get("collected", false), _stat.get("scavengers", false),
			_stat.get("soup", 0), _stat.get("asleep", false)])
	print("[smoke] street_life occupation arrest=%s pressgang=%s harass=%s requisition=%s poster=%s curfew_beating=%s | brothel pox=%s pimp=%s bill_fight=%s customers=%d | crime burglar=%s fence=%s mugging_walker=%s cutpurse_mark=%s | max_events=%d" % [
			_stat.get("arrest", false), _stat.get("pressgang", false), _stat.get("harass", "none"), _stat.get("requisition", false),
			_stat.get("poster", false), _stat.get("curfew_beating", false), _women.any(func(w): return bool(w.get_meta("pox", false))),
			_stat.get("pimp", false), _stat.get("bill_fight", false), _customers.size(), _stat.get("burglar", "none"), _stat.get("fence", false),
			_stat.get("mugging_walker", "none"), _stat.get("cutpurse_mark", "none"), int(D.get("max_events", 2))])
	_ts = 1.0
	_instant = false


## `-- --smoke --street-sim`: after the forced pass, let the ordinary scheduler run (probabilities x4) for 25 s of
## real time, the player free to be robbed, accosted or mugged, and report what happened (replaces the forced pass).
func _sim() -> void:
	_stat["started"] = ""
	_stat["peak_events"] = 0
	_smoke = false
	_sim_boost = 4.0
	var p := _player()
	_player_mug_next = 0.0
	var t := 0.0
	while t < 9.0 and is_inside_tree():
		await get_tree().physics_frame
		t += get_physics_process_delta_time()
		if p and t > 2.0 and not has_meta("sim_moved"):
			set_meta("sim_moved", true)      # a dark alley behind the west row, after the interiors' own smoke
			p.global_position = _nav_point(Vector3(-38.5, 0, -6.0)) + Vector3(0, 0.1, 0)
			p.reset_physics_interpolation()
		if _dlg.is_open and _dlg_graph == D["crime"]["mugging_dialogue"] and t > 1.0:
			answer("fight" if _rng.randf() < 0.5 else "pay")
	_sim_report()


func _sim_report() -> void:
	if _sim_boost <= 1.0:
		return
	_smoke = true
	_sim_boost = 1.0
	print("[smoke] street_life sim clock=%s peak_events=%d (cap %d) started=%s mugging=%s cutpurse=%s drunks=%d moved_on=%s accost=%s relieve=%s asleep=%s" % [
			GameState.time_string(), int(_stat["peak_events"]), int(D.get("max_events", 2)), str(_stat["started"]).strip_edges(),
			_stat["mugging"], _stat["cutpurse"], _drunks.size(), _stat.get("moved_on", false), _stat.get("accost", false),
			_stat.get("relieve", false), _stat.get("asleep", false)])


func _exit_tree() -> void:
	_sim_report()      # the smoke night may end before the simulation does


func _later_shots() -> void:
	await _frames(30)
	await _shoot_all(["brothel", "pillory", "gallows", "beggar", "freezing"])
	for i in 240:                  # the soup line and the children take a moment to gather
		if _anchors.has("soup") and _anchors.has("scavengers"):
			break
		await get_tree().physics_frame
	await _frames(20)
	await _shoot_all(["soup", "scavengers"])


## A camera spot with a clear view of `look`: the preferred offset, else the same distance swung round.
func _clear_cam(look: Vector3, pref: Vector3) -> Vector3:
	var space := get_world_3d().direct_space_state
	var flat := Vector3(pref.x, 0, pref.z)
	for k in 16:
		var ang := (k / 2) * 0.4 * (1.0 if k % 2 == 0 else -1.0)
		var off := flat.rotated(Vector3.UP, ang)
		var cp := Vector3(look.x + off.x, pref.y, look.z + off.z)
		var pq := PhysicsPointQueryParameters3D.new()      # not inside a building's collision box
		pq.position = cp
		if not space.intersect_point(pq, 1).is_empty():
			continue
		if Perception.clear_line(space, look, cp, [], null, true) and Perception.clear_line(space, cp, look, [], null, true) \
				and Perception.clear_line(space, cp, cp + off.normalized() * 0.4, [], null, true):
			return cp
	return Vector3(look.x + pref.x, pref.y, look.z + pref.z)


func _prop_state(key: String) -> String:
	var e: Dictionary = D["punishment"].get(key, {})
	var n: Node3D = e.get("_node")
	if n == null:
		return "absent"
	return "model" if bool(n.get_meta("sl_real", false)) else "fallback"


## Windowed: close-ups of the staged scenes (`-- --street-shot=/dir`), night as it is.
func _shoot_all(names: Array, suffix := "") -> void:
	if not is_inside_tree():
		return
	var cam := Camera3D.new()
	cam.fov = 58
	add_child(cam)
	var prev := get_viewport().get_camera_3d()
	var layers: Array = []
	for c in get_tree().root.find_children("*", "CanvasLayer", true, false):
		if c != _dlg and (c as CanvasLayer).visible:
			(c as CanvasLayer).visible = false
			layers.append(c)
	for name in names:
		if not _shot_only.is_empty() and not _shot_only.has(name):
			continue
		if not _anchors.has(name):
			print("[smoke] street shot %s: not staged" % name)
			continue
		await _shoot(cam, name, _shot_dir, false, suffix)
	for c in layers:
		if is_instance_valid(c):
			(c as CanvasLayer).visible = true
	if prev and is_instance_valid(prev):
		prev.current = true
	cam.queue_free()


## The mugging dialogue: the player stood in a dark alley, the thugs close in, the box open on screen.
func _shoot_mug_dialogue() -> void:
	if not _shot_only.is_empty() and not _shot_only.has("mug_player"):
		return
	var spot := _mug_spot(0.0)
	var p := _player()
	if spot == Vector3.INF or p == null:
		return
	p.global_position = spot + Vector3(0, 0.1, 0)
	p.reset_physics_interpolation()
	start_event("mug_player", true, {"force_dialogue": true})
	await get_tree().process_frame
	var cam := Camera3D.new()
	cam.fov = 58
	add_child(cam)
	var layers: Array = []
	for c in get_tree().root.find_children("*", "CanvasLayer", true, false):
		if c != _dlg and (c as CanvasLayer).visible:
			(c as CanvasLayer).visible = false
			layers.append(c)
	await _shoot(cam, "mug_player", _shot_dir, true)
	for c in layers:
		if is_instance_valid(c):
			(c as CanvasLayer).visible = true
	cam.queue_free()
	answer("pay")
	print("[smoke] street shots in ", _shot_dir)


func _shoot(cam: Camera3D, name: String, dir: String, with_ui := false, suffix := "") -> void:
	var an: Array = _anchors[name]
	if an[0] is Object and not is_instance_valid(an[0]):
		return
	var tgt: Vector3 = (an[0] as Node3D).global_position if an[0] is Node3D else an[0]
	var look := tgt + Vector3(0, float(an[2]), 0)
	cam.look_at_from_position(_clear_cam(look, an[1]), look)
	cam.current = true
	_dlg.visible = with_ui and _dlg.is_open
	await RenderingServer.frame_post_draw      # one frame per shot: the smoke night is short on a loaded GPU
	get_viewport().get_texture().get_image().save_png("%s/street_%s%s.png" % [dir, name, suffix])
	_dlg.visible = _dlg.is_open
	print("[smoke] street shot %s%s at %s (frame %d, %.1fs)" % [name, suffix, tgt, Engine.get_process_frames(), Time.get_ticks_msec() / 1000.0])
