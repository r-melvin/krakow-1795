extends RefCounted
## First-person close actions (player.gd `start_fp` / `end_fp`, camera mode FIRST): the game stays third person and
## drops into the eyes only for close, focused work.
##   keyhole   E on a door with meta `keyhole` / `peephole` (a Spot is attached), or crouched E on a knockable door
##             (distraction.gd KnockDoor): the eye goes to the keyhole (meta `keyhole_eye`, local Vector3, else just
##             through the door), a keyhole-shaped mask, a +-25 degree look arc; hold E to keep looking, any movement
##             key (or Esc) returns
##   listen    E on a `listen` spot (meta `listen`, group "listen_spot"): eyes on the wall, soft vignette, muffled
##             audio through the audio agent's `Sfx.set_muffle(true)` when that autoload exists; the lines in meta
##             `lines` ([[text, gloss], ...] or strings) are heard one by one and written to the journal
##   lockpick  E on a door / chest with meta `locked` (true, or the pin count 2-4): hold the aim button (RMB) for
##             tension, tap strike (LMB / F) when the pin glows (the tension sits in its band); a tap outside the band
##             or too much tension for too long makes noise (watch.emit_sound -> sound_event) and counts a fail;
##             three fails and the pick slips. Success: meta `locked` false and `unlock(player)` if the node has it
##   pocket    crouched behind a townsperson (a Spot on every NPC without its own interactable): the same QTE,
##             2 pins, faster; success = 1-3 coins, failure = a shout and the watch told
## `Session` (a CanvasLayer on the player) runs one of these; `Qte` is the pin game (stepped, testable).

const Perception := preload("res://scripts/stealth/perception.gd")
const Interactable := preload("res://scripts/mission/interactable.gd")
const Walker := preload("res://scripts/npc/walker.gd")

# ------------------------------------------------------------------ the pin game

class Qte extends RefCounted:
	var pins := 3
	var index := 0                ## pins set so far
	var tension := 0.0            ## 0..1
	var band := Vector2(0.45, 0.7)
	var fails := 0
	var max_fails := 3
	var rate := 0.55              ## tension per second while held
	var over_t := 0.0             ## seconds above the band
	var noise_events := 0
	var state := ""               ## "" running, "ok", "fail"
	var rng := RandomNumberGenerator.new()

	func setup(n: int, fast := false, seed_ := 0) -> void:
		pins = clampi(n, 1, 4)
		rng.seed = seed_ if seed_ != 0 else Time.get_ticks_usec()
		rate = 0.8 if fast else 0.55
		_new_band()

	func _new_band() -> void:
		var lo := rng.randf_range(0.3, 0.7)
		band = Vector2(lo, lo + rng.randf_range(0.12, 0.18))

	func catching() -> bool:
		return tension >= band.x and tension <= band.y

	## One step. `held` = tension button, `tap` = strike this frame. Returns "" | "pin" | "miss" | "ok" | "fail".
	func step(delta: float, held: bool, tap: bool) -> String:
		if state != "":
			return state
		tension = clampf(tension + (rate if held else -rate * 1.6) * delta, 0.0, 1.0)
		if tension > band.y + 0.12:
			over_t += delta
			if over_t > 0.6:
				over_t = 0.0
				return _fail()
		else:
			over_t = maxf(0.0, over_t - delta)
		if tap:
			if catching():
				index += 1
				tension *= 0.4
				if index >= pins:
					state = "ok"
					return "ok"
				_new_band()
				return "pin"
			return _fail()
		return ""

	func _fail() -> String:
		fails += 1
		noise_events += 1
		tension = 0.0
		if fails >= max_fails:
			state = "fail"
			return "fail"
		return "miss"


## Draws the QTE: pins in a row (set ones brass, the current one glowing while it catches), a tension bar.
class QteView extends Control:
	var qte: Qte

	func _ready() -> void:
		set_anchors_preset(Control.PRESET_FULL_RECT)
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _process(_d: float) -> void:
		queue_redraw()

	func _draw() -> void:
		if qte == null:
			return
		var c := size * 0.5 + Vector2(0, size.y * 0.18)
		var w := 60.0 * qte.pins
		draw_rect(Rect2(c - Vector2(w * 0.5 + 20, 70), Vector2(w + 40, 110)), Color(0.05, 0.04, 0.03, 0.7))
		for i in qte.pins:
			var x := c.x - w * 0.5 + 30.0 + i * 60.0
			var set_ := i < qte.index
			var cur := i == qte.index
			var h := 34.0 if set_ else 22.0 + (qte.tension * 16.0 if cur else 0.0)
			var col := Color(0.8, 0.62, 0.3) if set_ else (Color(1.0, 0.9, 0.5) if cur and qte.catching() else Color(0.55, 0.55, 0.58))
			draw_rect(Rect2(Vector2(x - 8, c.y - 20 - h), Vector2(16, h)), col)
			draw_rect(Rect2(Vector2(x - 10, c.y - 20), Vector2(20, 6)), Color(0.3, 0.28, 0.26))
		var bar := Rect2(c + Vector2(-w * 0.5, 10), Vector2(w, 10))
		draw_rect(bar, Color(0.15, 0.13, 0.11))
		draw_rect(Rect2(bar.position, Vector2(w * qte.tension, 10)), Color(0.85, 0.55, 0.25))
		draw_rect(Rect2(bar.position + Vector2(w * qte.band.x, -3), Vector2(w * (qte.band.y - qte.band.x), 16)), Color(1, 0.9, 0.5, 0.35))
		for f in qte.fails:
			draw_circle(c + Vector2(-w * 0.5 + 8 + f * 16, 36), 5, Color(0.8, 0.2, 0.15))


# ------------------------------------------------------------------ a first-person session

class Session extends CanvasLayer:
	var kind := "keyhole"
	var player: Node3D
	var target: Node3D
	var eye := Vector3.ZERO          ## world position of the camera
	var look := Vector3.FORWARD      ## centre of the look arc
	var arc := deg_to_rad(25.0)
	var pitch_arc := 0.3
	var qte: Qte
	var heard: Array = []            ## listen: lines heard
	var result := ""                 ## ok | fail | done
	var muffled := false
	var t := 0.0
	var _next_line := 1.5
	var _lines: Array = []
	var _mask: TextureRect

	func _ready() -> void:
		layer = 5
		# the mask is a small CPU-drawn alpha texture stretched over the screen (no custom shader to fail)
		var vs := get_viewport().get_visible_rect().size if get_viewport() else Vector2(16, 9)
		_mask = TextureRect.new()
		_mask.set_anchors_preset(Control.PRESET_FULL_RECT)
		_mask.mouse_filter = Control.MOUSE_FILTER_IGNORE
		_mask.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		_mask.stretch_mode = TextureRect.STRETCH_SCALE
		_mask.texture = mask_texture(kind == "keyhole", vs.x / maxf(vs.y, 1.0))
		_mask.modulate.a = 0.0 if kind == "keyhole" else 1.0
		add_child(_mask)
		match kind:
			"listen":
				_lines = target.get_meta("lines", []) if target else []
				var sfx := player.get_tree().root.get_node_or_null("Sfx")
				if sfx and sfx.has_method("set_muffle"):
					sfx.set_muffle(true)
					muffled = true
			"lockpick", "pocket":
				qte = Qte.new()
				var n := 2
				if kind == "lockpick":
					var m: Variant = target.get_meta("locked", 3) if target else 3
					n = int(m) if (m is int or m is float) and int(m) >= 2 else 3
				qte.setup(n, kind == "pocket")
				var v := QteView.new()
				v.qte = qte
				add_child(v)

	## Keyhole (a round head over a flared slot) or a soft vignette, as an RGBA texture 320 x 180-ish.
	static func mask_texture(keyhole: bool, aspect: float) -> Texture2D:
		var h := 180
		var w := int(h * aspect)
		var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
		for y in h:
			for x in w:
				var u := (float(x) / w - 0.5) * aspect
				var v := 0.5 - float(y) / h
				var a := 0.0
				var col := Color(0, 0, 0)
				if keyhole:
					var circle := Vector2(u, v - 0.07).length() - 0.16
					var qy := v + 0.13
					var slot := maxf(absf(u) - (0.05 + 0.07 * clampf(-qy / 0.2, 0.0, 1.0)), absf(qy) - 0.17)
					var d := minf(circle, slot)
					a = clampf((d + 0.004) / 0.022, 0.0, 1.0)
					col = Color(0.10, 0.07, 0.04) * (1.0 - clampf(d / 0.09, 0.0, 1.0))
				else:
					var dd := Vector2(u, v).length()
					a = clampf((dd - 0.35) / 0.6, 0.0, 1.0) * 0.85
				img.set_pixel(x, y, Color(col.r, col.g, col.b, a))
		return ImageTexture.create_from_image(img)

	func mask_visible() -> bool:
		return _mask != null and _mask.visible

	## One frame. Returns false when the session is over.
	func tick(delta: float, hold: bool, tension: bool, tap: bool, cancel: bool) -> bool:
		t += delta
		if cancel:
			result = "done" if result == "" else result
			return false
		match kind:
			"keyhole":
				_mask.modulate.a = clampf(t / 0.25, 0.0, 1.0)
				if not hold and t > 0.3:
					result = "done"
					return false
			"listen":
				_next_line -= delta
				if _next_line <= 0.0 and heard.size() < _lines.size():
					_next_line = 3.0
					_hear(_lines[heard.size()])
				if not hold and t > 0.3:
					result = "done"
					return false
			"lockpick", "pocket":
				var r := qte.step(delta, tension, tap)
				if r == "miss" or r == "fail":
					_noise(0.35 if kind == "lockpick" else 0.2)
				if r == "ok" or r == "fail":
					result = r
					_finish_qte(r)
					return false
		return true

	func _hear(line: Variant) -> void:
		var text := str(line[0]) if line is Array else str(line)
		var gloss := str(line[1]) if line is Array and (line as Array).size() > 1 else ""
		heard.append(text)
		if player.get("sandbox"):
			return
		Mission.message.emit(text + ("  (%s)" % gloss if gloss != "" else ""), 3.0)
		Mission.journal_log("Overheard through the wall: \"%s\"%s" % [text, (" - " + gloss) if gloss != "" else ""], "note")

	func _noise(loud: float) -> void:
		var w := Perception.watch_of(player)
		if w:
			w.emit_sound(player.global_position, loud, kind, false, true, true)

	func _finish_qte(r: String) -> void:
		if kind == "lockpick":
			if r == "ok" and target:
				target.set_meta("locked", false)
				if target.has_method("unlock"):
					target.unlock(player)
			elif r == "fail":
				_noise(0.55)
				var kit: Node = player.get("kit")
				if kit:
					kit.take("lockpick")        # the pick snaps
		else:
			if r == "ok":
				var kit: Node = player.get("kit")
				if kit:
					kit.add("coin", 1 + randi() % 3)
			elif target:
				Walker.speech(target, ["Złodziej!", "Hands off, you!"].pick_random(), 2.0, 2.1)
				var w := Perception.watch_of(player)
				if w:
					w.report(player.global_position, target)

	func end() -> void:
		if muffled:
			var sfx := player.get_tree().root.get_node_or_null("Sfx")
			if sfx and sfx.has_method("set_muffle"):
				sfx.set_muffle(false)
		queue_free()


# ------------------------------------------------------------------ interact hosts

## An interactable for a keyhole / listen / lockpick / pocket target (the target is the parent, or `target`).
class Spot extends Node3D:
	var kind := "keyhole"
	var target: Node3D
	var _ia: Area3D

	func _ready() -> void:
		if target == null:
			target = get_parent() as Node3D
		_ia = Interactable.new()
		_ia.display_name = ""
		_ia.prompt_func = _prompt
		_ia.handler = _use
		_ia.marker_height = 1.6
		if kind != "pocket":
			_ia.set_meta("low_priority", true)
		add_child(_ia)

	func _player() -> Node3D:
		var w := Perception.watch_of(self)
		return (w.get_player() if w else get_tree().get_first_node_in_group("player")) as Node3D

	func _prompt() -> String:
		match kind:
			"keyhole":
				return "peer through the keyhole"
			"listen":
				return "listen at the wall"
			"lockpick":
				var pl := _player()
				var kit: Node = pl.get("kit") if pl else null
				if kit and not kit.has("lockpick"):
					return ""
				return "pick the lock" if target and target.get_meta("locked", false) else ""
			"pocket":
				var p := _player()
				if p == null or not p.get("is_crouching") or target == null or not target.visible:
					return ""
				var to := p.global_position - target.global_position
				to.y = 0.0
				var fwd := -target.global_transform.basis.z
				if to.length() > 1.4 or rad_to_deg(fwd.angle_to(to)) < 110.0:
					return ""
				return "pick his pocket"
		return ""

	func _use(actor: Node) -> bool:
		if actor == null or not actor.has_method("start_fp"):
			return false
		return actor.start_fp(kind, target if target else self)


## Attaches Spots to everything tagged in `world`: meta keyhole / peephole / listen / locked, groups "keyhole",
## "listen_spot", "locked"; and pocket Spots on townsfolk (group "npcs") that carry no interactable of their own.
static func attach_all(world: Node) -> int:
	var n := 0
	var seen := {}
	for g in ["keyhole", "listen_spot", "locked"]:
		for node in world.get_tree().get_nodes_in_group(g):
			if node is Node3D and world.is_ancestor_of(node):
				seen[node] = true
	for node in world.find_children("*", "Node3D", true, false):
		if node.has_meta("keyhole") or node.has_meta("peephole") or node.has_meta("listen") or node.has_meta("locked"):
			seen[node] = true
	for node in seen:
		if node.has_meta("fp_spot"):
			continue
		node.set_meta("fp_spot", true)
		var s := Spot.new()
		s.kind = "listen" if (node.has_meta("listen") or node.is_in_group("listen_spot")) else \
				("lockpick" if (node.has_meta("locked") or node.is_in_group("locked")) else "keyhole")
		node.add_child(s)
		n += 1
	for npc in world.get_tree().get_nodes_in_group("npcs"):
		if not (npc is Node3D) or not world.is_ancestor_of(npc) or npc.has_meta("fp_spot"):
			continue
		var has_ia := false
		for c in npc.get_children():
			if c is Area3D and c.is_in_group("interactable"):
				has_ia = true
				break
		if has_ia:
			continue
		npc.set_meta("fp_spot", true)
		var s := Spot.new()
		s.kind = "pocket"
		npc.add_child(s)
		n += 1
	return n
