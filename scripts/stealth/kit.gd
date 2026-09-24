extends Node
## The player's kit (docs/STEALTH.md "Kit"): what is in the coat, one item current at a time, shown bottom-left as
## one icon and a count (Indicator below). A child of the player (player.gd `kit`). Numbers in data/stealth.json "kit".
##
##   weapons     knife (always; fast slash, silent takedown from behind: a choke, or a thrust when `lethal`; parry
##               with the aim button), cudgel (always; the old blow), pistol (one ball, kit.pistol_reload_secs to
##               reload, heard across the district: the last resort), musket (only picked up from a downed guard:
##               a slow two-handed club, dropped when you switch away unless Mission flag "musket_permitted")
##   throwables  stone, coin (from the purse: GameState.coins), bottle, food (vendor wares), smoke, flash
##   finale      cosh (a sandbag: a non-lethal knockout from behind, longer, and no blood: no notoriety of its own),
##               torch (lit at a flame light with E or F; carried one-handed it lights you, visibility x1.4; thrown it
##               sets fire through the fire system: verbs.gd; switching away drops it burning), tinderbox (sets a
##               `flammable` prop alight in 3 s), poison (a vial for a `poisonable` prop), lockpick (the pin game of
##               fp_view.gd; a failed pick breaks one)
##
## Hooks for the campaign / vendor agents: `kit.add(item, n)`, `kit.take(item, n)`, `kit.count(item)`,
## `kit.select(item)`; signal `changed`. Static helpers used by distraction.gd: the guards' smoke sight modifier,
## coin takers (walkers stop and pick it up: a crowd) and food takers (dogs, street urchins).

const Perception := preload("res://scripts/stealth/perception.gd")

signal changed

const ORDER := ["knife", "cosh", "cudgel", "pistol", "musket", "torch", "tinderbox", "stone", "coin", "bottle", "food", "smoke",
		"flash", "poison", "lockpick"]
const WEAPONS := ["knife", "cosh", "cudgel", "pistol", "musket", "torch"]
const THROWABLES := ["stone", "coin", "bottle", "food", "smoke", "flash", "torch"]
const TOOLS := ["tinderbox", "poison", "lockpick"]   ## used through props (verbs.gd, fp_view.gd), shown with a count
const ALWAYS := ["knife", "cudgel"]

var player: Node3D
var sandbox := false
var counts: Dictionary = {"knife": 1, "cudgel": 1}
var current := "knife"
var last_throwable := "stone"
var lethal := false                 ## knife takedowns kill (more crackdown / notoriety than a choke)
var pistol_loaded := true
var reload_left := 0.0              ## > 0 while reloading (seconds of work left)
var last_takedown := ""             ## "choke" | "lethal" | "thrust" (after a parry) | "cosh"
var torch_lit := false


func _ready() -> void:
	name = "Kit"


func tv(path: String, fallback: Variant) -> Variant:
	return Perception.tg("kit." + path, fallback)


## Night start: data/stealth.json kit.night_start (for now 1 smoke, 1 flash, 5 stones).
func night_start() -> void:
	var ns: Variant = tv("night_start", {"smoke": 1, "flash": 1, "stone": 5})
	if ns is Dictionary:
		for k in ns:
			if int(counts.get(k, 0)) < int(ns[k]):
				counts[k] = int(ns[k])
	changed.emit()


func count(item: String) -> int:
	if item == "coin" and not sandbox:
		return int(GameState.coins)
	if item in ALWAYS:
		return int(counts.get(item, 1))
	return int(counts.get(item, 0))


func has(item: String) -> bool:
	return count(item) > 0


## Campaign / vendor hook: gain `n` of `item`. Returns the new count.
func add(item: String, n: int = 1) -> int:
	if item == "coin" and not sandbox:
		GameState.coins += n
	else:
		counts[item] = int(counts.get(item, 0)) + n
	if item == "pistol":
		counts["pistol"] = 1
		pistol_loaded = true
	changed.emit()
	return count(item)


## Spend `n`. Returns false if there were not enough.
func take(item: String, n: int = 1) -> bool:
	if count(item) < n:
		return false
	if item == "coin" and not sandbox:
		GameState.coins -= n
	else:
		counts[item] = int(counts.get(item, 0)) - n
	if item == "torch" and count("torch") <= 0:
		torch_lit = false
	if not has(current):
		current = "knife" if has("knife") else "cudgel"
	changed.emit()
	return true


func is_weapon(item: String) -> bool:
	return item in WEAPONS


func is_throwable(item: String) -> bool:
	return item in THROWABLES


## What the aim / throw buttons throw: the current item if throwable, else the last throwable used, else any.
func throwable() -> String:
	if is_throwable(current) and has(current) and (current != "torch" or torch_lit):
		return current
	if has(last_throwable) and last_throwable != "torch":
		return last_throwable
	for t in THROWABLES:
		if t != "coin" and t != "torch" and has(t):
			return t
	return ""


func select(item: String) -> bool:
	if not has(item) or item == current:
		return false
	if current == "musket" and not musket_permitted():
		_drop_musket()
	if current == "torch" and torch_lit:
		# a burning torch is not stowed in a coat: it is left on the cobbles, still alight
		torch_lit = false
		counts["torch"] = int(counts.get("torch", 0)) - 1
		if player and player.has_method("drop_item"):
			player.drop_item("torch")
	current = item
	if is_throwable(item) and item != "torch":
		last_throwable = item
	changed.emit()
	return true


## [ and ] / the mouse wheel.
func cycle(dir: int) -> String:
	var i := ORDER.find(current)
	for k in ORDER.size():
		i = (i + dir + ORDER.size()) % ORDER.size()
		if has(ORDER[i]):
			select(ORDER[i])
			break
	return current


static func musket_permitted() -> bool:
	return bool(Mission.flags.get("musket_permitted", false))


func _drop_musket() -> void:
	counts["musket"] = 0
	if player and player.has_method("drop_item"):
		player.drop_item("musket")


func weapon() -> String:
	return current if is_weapon(current) else "knife" if has("knife") else "cudgel"


# ------------------------------------------------------------------ pistol

func start_reload() -> bool:
	if not has("pistol") or pistol_loaded or reload_left > 0.0:
		return false
	reload_left = float(tv("pistol_reload_secs", 20.0))
	changed.emit()
	return true


## Reload work goes on only with the pistol in hand and not sprinting; returns true the frame it completes.
func tick(delta: float, working: bool) -> bool:
	if reload_left <= 0.0 or not working:
		return false
	reload_left -= delta
	if reload_left <= 0.0:
		reload_left = 0.0
		pistol_loaded = true
		changed.emit()
		return true
	return false


func reload_progress() -> float:
	var full := float(tv("pistol_reload_secs", 20.0))
	return 1.0 - reload_left / full if reload_left > 0.0 else (1.0 if pistol_loaded else 0.0)


## Seized by the watch with a blade or pistol in hand: the pistol is taken, the knife knocked to the cobbles.
## Returns the items dropped on the ground (for pickup.gd to place).
func disarm() -> Array:
	var dropped: Array = []
	if current == "pistol" and has("pistol"):
		counts["pistol"] = 0
		pistol_loaded = false
		reload_left = 0.0
	elif current == "knife":
		counts["knife"] = 0
		dropped.append("knife")
	elif current == "musket":
		counts["musket"] = 0
		dropped.append("musket")
	else:
		return dropped
	current = "cudgel"
	changed.emit()
	return dropped


# ------------------------------------------------------------------ static helpers

static func smoke_on() -> bool:
	return "--smoke" in OS.get_cmdline_user_args()


static var _dot: Texture2D


## A soft round sprite for smoke puffs.
static func soft_dot() -> Texture2D:
	if _dot:
		return _dot
	var img := Image.create(64, 64, false, Image.FORMAT_RGBA8)
	for y in 64:
		for x in 64:
			var d := Vector2(x - 31.5, y - 31.5).length() / 31.5
			var a := clampf(1.0 - d, 0.0, 1.0)
			img.set_pixel(x, y, Color(1, 1, 1, a * a * (3.0 - 2.0 * a)))
	_dot = ImageTexture.create_from_image(img)
	return _dot


## Adds the smoke sight modifier to every guard of `node`'s watch (once per guard).
static func register_sight(node: Node) -> void:
	var w := Perception.watch_of(node)
	var pool: Array = w.guards() if w else node.get_tree().get_nodes_in_group("guards")
	var c := Callable(load("res://scripts/stealth/kit.gd"), "sight_modifier")
	for g in pool:
		if is_instance_valid(g) and not g.has_meta("kit_sight") and g.get("sight_modifiers") != null:
			g.set_meta("kit_sight", true)
			g.sight_modifiers.append(c)


## Guard sight modifier: 0 when a smoke cloud lies between the guard's eye and the player (or wraps the player).
static func sight_modifier(g: Node3D, p: Node3D) -> float:
	var eye := g.global_position + Vector3(0, 1.5, 0)
	var head: Vector3 = p.head_position() if p.has_method("head_position") else p.global_position + Vector3(0, 1.5, 0)
	for c in g.get_tree().get_nodes_in_group("smoke_cloud"):
		if Perception.same_world(c, g) and (c.blocks(eye, head) or c.contains(head)):
			return 0.0
	return 1.0


## Coin: up to kit.coin_takers walkers within kit.coin_radius stop what they do and come to pick it up (a small
## crowd round the spot: the player can blend there). Returns the takers.
static func call_walkers(coin: Node3D, pos: Vector3) -> Array:
	var cands: Array = []
	var r := float(Perception.tg("kit.coin_radius", 9.0))
	for n in coin.get_tree().get_nodes_in_group("npcs"):
		var npc := n as Node3D
		if npc == null or not Perception.same_world(npc, coin) or not npc.has_method("claim") or not npc.visible:
			continue
		var m: Variant = npc.get("mode")
		if m == null or int(m) >= 3:          # SCRIPTED (a storyline has him) or DOWNED
			continue
		var d := npc.global_position.distance_to(pos)
		if d < r:
			cands.append([d, npc])
	cands.sort_custom(func(a: Array, b: Array) -> bool: return a[0] < b[0])
	var takers: Array = []
	for i in mini(cands.size(), int(Perception.tg("kit.coin_takers", 3))):
		takers.append(cands[i][1])
	if not takers.is_empty():
		var t := Takers.new()
		t.spot = pos
		t.people = takers
		t.secs = float(Perception.tg("kit.coin_secs", 7.0))
		coin.get_parent().add_child(t)
	return takers


## Food: dogs (animals whose model or id says dog) come and nose it; street urchins run for it. Returns the takers.
static func call_animals(food: Node3D, pos: Vector3) -> Array:
	var takers: Array = []
	var r := float(Perception.tg("kit.food_radius", 14.0))
	for n in food.get_tree().get_nodes_in_group("animals"):
		var a := n as Node3D
		if a == null or not Perception.same_world(a, food) or a.global_position.distance_to(pos) > r:
			continue
		var tag := (str(a.get("model_name")) + " " + str(a.get("npc_id")) + " " + str(a.get("role"))).to_lower()
		if not ("dog" in tag or "hound" in tag or "spitz" in tag or "cat" in tag):
			continue
		if not a.has_meta("kit_food_restore"):
			a.set_meta("kit_food_restore", [a.get("behaviour"), a.get("_home"), a.get("radius")])
		a.set("behaviour", "wander")
		a.set("_home", pos)
		a.set("_target", pos)
		a.set("radius", 0.4)
		a.set("_pause", 0.0)
		takers.append(a)
		a.get_tree().create_timer(float(Perception.tg("kit.food_secs", 12.0)), false).timeout.connect(func() -> void:
			if is_instance_valid(a) and a.has_meta("kit_food_restore"):
				var rs: Array = a.get_meta("kit_food_restore")
				a.remove_meta("kit_food_restore")
				a.set("behaviour", rs[0])
				a.set("_home", rs[1])
				a.set("radius", rs[2]))
	var kids: Array = []
	for n in food.get_tree().get_nodes_in_group("npcs"):
		var npc := n as Node3D
		if npc and Perception.same_world(npc, food) and str(npc.get("npc_id")).begins_with("urchin") \
				and npc.global_position.distance_to(pos) < r and npc.get("mode") != null and int(npc.get("mode")) < 3:
			kids.append(npc)
	if not kids.is_empty():
		var t := Takers.new()
		t.spot = pos
		t.people = kids
		t.run = true
		t.secs = float(Perception.tg("kit.food_secs", 12.0)) * 0.5
		food.get_parent().add_child(t)
		takers.append_array(kids)
	return takers


## Walks claimed townsfolk to a spot, has them stoop there for `secs` (a knot of people: group "crowd"), then hands
## them back to their schedule.
class Takers extends Node:
	var spot := Vector3.ZERO
	var people: Array = []
	var secs := 7.0
	var run := false
	var _t := 0.0
	var _started := false

	func _physics_process(delta: float) -> void:
		if not _started:
			_started = true
			for i in people.size():
				var n: Node3D = people[i]
				if not is_instance_valid(n):
					continue
				n.claim()
				var a := TAU * i / maxf(people.size(), 1.0)
				n.script_goto(spot + Vector3(cos(a), 0, sin(a)) * 0.55, 0.0, run)
				n.script_face(spot)
		_t += delta
		for n in people:
			if is_instance_valid(n) and n.get("script_arrived") and not n.is_in_group("crowd"):
				n.add_to_group("crowd")
				n.script_play("crouch_idle")
		if _t > secs + 8.0:
			for n in people:
				if is_instance_valid(n):
					if n.is_in_group("crowd"):
						n.remove_from_group("crowd")
					n.script_play("idle")
					n.release()
			queue_free()


## Draws `item`'s icon centred on the canvas origin (callers set draw_set_transform for position and size, ~30 px
## radius at scale 1). `k` (the kit, or null) tints the lethal knife, the lit torch and the pistol's reload.
static func draw_icon(ci: CanvasItem, item: String, k: Node) -> void:
	var ink := Color(0.93, 0.88, 0.76)
	var c := Vector2.ZERO
	match item:
		"knife":
			var blade := Color(0.85, 0.2, 0.15) if (k != null and k.lethal) else Color(0.86, 0.87, 0.9)
			ci.draw_colored_polygon(PackedVector2Array([c + Vector2(-2, 4), c + Vector2(2, 4), c + Vector2(1, -16), c + Vector2(-1, -18)]), blade)
			ci.draw_line(c + Vector2(-7, 5), c + Vector2(7, 5), ink, 2.0)
			ci.draw_line(c + Vector2(0, 6), c + Vector2(0, 16), Color(0.45, 0.28, 0.15), 4.0)
		"cudgel":
			ci.draw_line(c + Vector2(-10, 13), c + Vector2(8, -11), Color(0.55, 0.36, 0.2), 5.0)
			ci.draw_circle(c + Vector2(9, -12), 5, Color(0.5, 0.32, 0.18))
		"pistol":
			var col := ink if (k == null or k.pistol_loaded) else Color(ink, 0.4)
			ci.draw_line(c + Vector2(-14, -5), c + Vector2(10, -5), col, 4.0)
			ci.draw_line(c + Vector2(6, -4), c + Vector2(12, 10), Color(0.5, 0.32, 0.18), 6.0)
			if k != null and not k.pistol_loaded and k.reload_left > 0.0:
				ci.draw_arc(c, 22, -PI * 0.5, -PI * 0.5 + TAU * k.reload_progress(), 32, Color(0.9, 0.7, 0.3), 3.0, true)
		"musket":
			ci.draw_line(c + Vector2(-17, 12), c + Vector2(17, -12), Color(0.5, 0.32, 0.18), 4.0)
			ci.draw_line(c + Vector2(0, 0), c + Vector2(19, -13), Color(0.6, 0.6, 0.64), 2.0)
		"cosh":
			ci.draw_line(c + Vector2(-9, 12), c + Vector2(2, -2), Color(0.45, 0.3, 0.18), 4.0)
			ci.draw_circle(c + Vector2(6, -7), 8, Color(0.62, 0.55, 0.42))
		"torch":
			ci.draw_line(c + Vector2(-6, 14), c + Vector2(3, -6), Color(0.45, 0.3, 0.18), 5.0)
			if (k != null and k.torch_lit):
				ci.draw_circle(c + Vector2(5, -11), 7, Color(1.0, 0.6, 0.2))
				ci.draw_circle(c + Vector2(5, -12), 4, Color(1.0, 0.9, 0.5))
			else:
				ci.draw_circle(c + Vector2(4, -9), 5, Color(0.2, 0.18, 0.16))
		"tinderbox":
			ci.draw_rect(Rect2(c + Vector2(-12, -6), Vector2(24, 14)), Color(0.55, 0.56, 0.6))
			ci.draw_line(c + Vector2(-10, -9), c + Vector2(10, -9), Color(0.9, 0.7, 0.3), 2.0)
		"poison":
			ci.draw_colored_polygon(PackedVector2Array([c + Vector2(-6, 14), c + Vector2(6, 14), c + Vector2(6, 0), c + Vector2(2, -4),
					c + Vector2(2, -12), c + Vector2(-2, -12), c + Vector2(-2, -4), c + Vector2(-6, 0)]), Color(0.35, 0.6, 0.35))
			ci.draw_circle(c + Vector2(0, 7), 3, Color(0.1, 0.12, 0.1))
		"lockpick":
			ci.draw_line(c + Vector2(-12, 8), c + Vector2(10, -6), ink, 2.0)
			ci.draw_line(c + Vector2(10, -6), c + Vector2(13, -2), ink, 2.0)
			ci.draw_circle(c + Vector2(-12, 8), 4, Color(0.6, 0.6, 0.64))
		"stone":
			ci.draw_circle(c + Vector2(-5, 3), 7, Color(0.6, 0.58, 0.55))
			ci.draw_circle(c + Vector2(6, 5), 5, Color(0.5, 0.48, 0.46))
		"coin":
			ci.draw_circle(c, 10, Color(0.85, 0.68, 0.3))
			ci.draw_arc(c, 7, 0, TAU, 20, Color(0.6, 0.45, 0.15), 1.5, true)
		"bottle":
			ci.draw_colored_polygon(PackedVector2Array([c + Vector2(-6, 15), c + Vector2(6, 15), c + Vector2(6, -2), c + Vector2(2, -7),
					c + Vector2(2, -15), c + Vector2(-2, -15), c + Vector2(-2, -7), c + Vector2(-6, -2)]), Color(0.25, 0.5, 0.3))
		"food":
			ci.draw_arc(c, 9, 0, TAU, 24, Color(0.78, 0.52, 0.24), 6.0, true)
		"smoke":
			for o in [Vector2(-7, 4), Vector2(5, 5), Vector2(-1, -5), Vector2(8, -4)]:
				ci.draw_circle(c + o, 7, Color(0.7, 0.7, 0.72, 0.85))
		"flash":
			var pts := PackedVector2Array()
			for i in 16:
				var r := 15.0 if i % 2 == 0 else 6.0
				var a := TAU * i / 16.0
				pts.append(c + Vector2(cos(a), sin(a)) * r)
			ci.draw_colored_polygon(pts, Color(1.0, 0.95, 0.7))


# ------------------------------------------------------------------ HUD indicator

## Bottom-left: the current item as a small drawn icon and its count (no words). Knife red when lethal; the pistol
## shows a reload arc. Added by hud.gd; `player` may be set by a test, otherwise group "player".
class Indicator extends Control:
	var player: Node3D
	var _last := ""

	func _ready() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE
		anchor_left = 0.0
		anchor_top = 1.0
		anchor_right = 0.0
		anchor_bottom = 1.0
		offset_left = 22
		offset_top = -118
		offset_right = 122
		offset_bottom = -58

	func _kit() -> Node:
		if player == null or not is_instance_valid(player):
			player = get_tree().get_first_node_in_group("player") as Node3D
		return player.get("kit") if player else null

	func _process(_d: float) -> void:
		var k := _kit()
		var key := ""
		if k:
			key = "%s|%d|%s|%s|%.2f" % [k.current, k.count(k.current), k.lethal, k.pistol_loaded, k.reload_progress()]
		if key != _last:
			_last = key
			queue_redraw()

	func _draw() -> void:
		var k := _kit()
		if k == null:
			return
		var c := Vector2(30, 30)
		draw_circle(c, 27, Color(0.05, 0.04, 0.03, 0.55))
		draw_arc(c, 27, 0, TAU, 40, Color(0.72, 0.58, 0.32, 0.8), 1.5, true)
		draw_set_transform(c)
		load("res://scripts/stealth/kit.gd").draw_icon(self, str(k.current), k)
		draw_set_transform(Vector2.ZERO)
		var ink := Color(0.93, 0.88, 0.76)
		if not (str(k.current) in ALWAYS):
			var n: int = 0 if k.current == "pistol" and not k.pistol_loaded else k.count(k.current)
			if k.current == "pistol":
				n = 1 if k.pistol_loaded else 0
			var font := ThemeDB.fallback_font
			draw_string_outline(font, Vector2(62, 44), str(n), HORIZONTAL_ALIGNMENT_LEFT, -1, 22, 5, Color(0, 0, 0, 0.8))
			draw_string(font, Vector2(62, 44), str(n), HORIZONTAL_ALIGNMENT_LEFT, -1, 22, ink)
