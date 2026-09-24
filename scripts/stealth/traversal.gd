extends RefCounted
## Parkour for the player (player.gd owns one: `trav`). Space (action "jump") in front of an edge:
##   vault   an obstacle <= kit.traversal vault_max (1.2 m) that is thin (the ground drops again behind it): over it,
##           landing on the far side (vault_low); a sprinting vault keeps its speed, so vaults chain
##   mantle  a ledge <= mantle_max (2.4 m), or a low wide top: up onto it (vault_high)
##   hang    an edge <= hang_max (3.5 m): jump and hang by the hands (ledge_hang); A / D shimmy along the edge
##           (ledge_shimmy) while the edge goes on; Space / W climb up (ledge_climb) if there is room; Ctrl drops
##           (drop_hang)
##   pipe    something tagged climbable (group "climbable" with meta `climb_kind`, as outer_city.gd tags the climb_*
##           colliders of build_assets.py, or meta `climbable`: "pipe", "ivy", "crates", "ledge", "vault", "mantle";
##           optional meta `climb_top` (world y) and `handholds` (Array of local Vector3)): a drainpipe or ivy is
##           climbed straight up (W / S, climb_pipe) and topped out onto the roof; handholds snap a hang
##   slide   sprinting + Ctrl: a slide (slide_under) with the body at 0.7 m, under a cart or a table
##   in the air, Space near an edge at hand height catches it (hang)
## Falls are measured from the highest point: <= roll_max (4 m) above roll_from (1.8 m) = fall_land_roll with the
## momentum kept; higher = stumble and a hit point. Edges are found geometrically (rays against any static
## collider), so it works on any StaticBody wall, cart, parapet or roof edge before the level agents tag anything.
## Guards who see a climb look up at it (guard.look_toward) and keep it as the last known place.

const Perception := preload("res://scripts/stealth/perception.gd")

enum { NONE, VAULT, MANTLE, HANG, CLIMB_UP, PIPE, SLIDE }
const NAMES := ["none", "vault", "mantle", "hang", "climb", "pipe", "slide"]

var p: CharacterBody3D
var state := NONE
var t := 0.0
var dur := 0.0
var p0 := Vector3.ZERO
var p1 := Vector3.ZERO
var p2 := Vector3.ZERO
var wall_n := Vector3.ZERO        ## horizontal normal of the wall being climbed (points to the player)
var ledge_y := 0.0                ## world y of the edge while hanging
var climbable: Node3D = null
var carry_speed := 0.0            ## planar speed restored after a vault
var carry_dir := Vector3.ZERO
var last_action := ""             ## vault | mantle | hang | climb | pipe | slide | drop
var last_landing := ""            ## roll | stumble | land
var last_fall := 0.0
var counts := {}                  ## action -> times (smoke)
var _peak_y := NAN
var _last_y := 0.0
var _air := false
var _shimmy_anim := 0.0


func _init(player: CharacterBody3D) -> void:
	p = player


func tvv(key: String, fb: float) -> float:
	return float(Perception.tg("traversal." + key, fb))


func active() -> bool:
	return state != NONE


func state_name() -> String:
	return NAMES[state]


func _space() -> PhysicsDirectSpaceState3D:
	return p.get_world_3d().direct_space_state


func _ray(a: Vector3, b: Vector3, inside := false) -> Dictionary:
	var q := PhysicsRayQueryParameters3D.create(a, b)
	q.exclude = [p.get_rid()]
	q.hit_from_inside = inside
	var hit := _space().intersect_ray(q)
	if not hit.is_empty() and hit.get("collider") is CharacterBody3D:
		return {}
	return hit


## Is there room for the standing capsule with its feet at `feet`?
func room_at(feet: Vector3, height := 1.7) -> bool:
	var sh := CapsuleShape3D.new()
	sh.radius = 0.3
	sh.height = height
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = sh
	q.transform = Transform3D(Basis.IDENTITY, feet + Vector3(0, height * 0.5 + 0.06, 0))
	q.exclude = [p.get_rid()]
	for r in _space().intersect_shape(q, 4):
		if not (r.get("collider") is CharacterBody3D):
			return false
	return true


## Looks for an edge ahead along `dir` within `reach`. Returns {} or {h, top, face, n, thin, land, stand, node}.
func probe(dir: Vector3, reach: float, min_h := 0.3, max_h := -1.0) -> Dictionary:
	if max_h < 0.0:
		max_h = tvv("hang_max", 3.5)
	dir.y = 0.0
	if dir.length() < 0.01:
		return {}
	dir = dir.normalized()
	var feet := p.global_position
	var hit := {}
	for hgt in [0.35, 0.8, 1.3, 1.9, 2.5, 3.1]:
		if hgt > max_h + 0.3:
			break
		var h := _ray(feet + Vector3(0, hgt, 0), feet + Vector3(0, hgt, 0) + dir * reach)
		if not h.is_empty() and absf((h["normal"] as Vector3).y) < 0.5:
			hit = h
			break
	if hit.is_empty():
		return {}
	var n: Vector3 = hit["normal"]
	n.y = 0.0
	n = n.normalized()
	var into := -n
	var face: Vector3 = hit["position"]
	# the top: a ray down from above the highest edge we could reach, just inside the face
	var col := face + into * 0.1
	var from := Vector3(col.x, feet.y + max_h + 0.45, col.z)
	var top_hit := _ray(from, Vector3(col.x, feet.y - 0.2, col.z), true)
	if top_hit.is_empty() or (top_hit["normal"] as Vector3) == Vector3.ZERO or (top_hit["normal"] as Vector3).y < 0.65:
		return {}
	var top_y: float = (top_hit["position"] as Vector3).y
	var h_rel := top_y - feet.y
	if h_rel < min_h or h_rel > max_h:
		return {}
	# nothing just above the top edge (not a slot under a balcony)
	if not _ray(Vector3(col.x, top_y + 0.05, col.z), Vector3(col.x, top_y + 0.9, col.z)).is_empty():
		return {}
	# thin? the ground falls away again within 0.9 m behind the face
	var thin := false
	var land := Vector3.ZERO
	for depth in [0.55, 0.85, 1.15]:
		var c: Vector3 = face + into * float(depth)
		var dh := _ray(Vector3(c.x, top_y + 0.3, c.z), Vector3(c.x, feet.y - 1.5, c.z))
		if not dh.is_empty() and (dh["position"] as Vector3).y < top_y - 0.35:
			thin = true
			land = face + into * (depth + 0.45)
			var lh := _ray(Vector3(land.x, top_y + 0.3, land.z), Vector3(land.x, feet.y - 2.5, land.z))
			land.y = (lh["position"] as Vector3).y if not lh.is_empty() else feet.y
			break
	var stand := face + into * 0.5
	stand.y = top_y
	return {"h": h_rel, "top": top_y, "face": face, "n": n, "thin": thin, "land": land, "stand": stand, "node": hit.get("collider")}


## Space pressed on the ground. Returns the action started, or "".
func try_start(dir: Vector3, sprinting: bool) -> String:
	if state != NONE:
		return ""
	var c := _climbable_ahead(dir)
	if c and str(_climb_kind(c)) in ["pipe", "ivy"]:
		return _start_pipe(c, dir)
	var r := probe(dir, 1.35 if sprinting else 1.0)
	if r.is_empty():
		return ""
	var h: float = r["h"]
	var into: Vector3 = -(r["n"] as Vector3)
	if h <= tvv("vault_max", 1.2) and r["thin"] and room_at(r["land"]):
		carry_speed = Vector2(p.velocity.x, p.velocity.z).length() if sprinting else 0.0
		carry_dir = into
		# a quadratic arc whose middle clears the top by 0.3 m (the control point sits twice as high)
		var land: Vector3 = r["land"]
		var apex: Vector3 = (r["face"] as Vector3) + into * 0.15
		apex.y = 2.0 * (float(r["top"]) + 0.3) - 0.5 * (p.global_position.y + land.y)
		_begin(VAULT, p.global_position, apex, land, 0.42 if sprinting else 0.55, "vault_low", into)
		return "vault"
	if h <= tvv("mantle_max", 2.4):
		if not room_at(r["stand"]):
			return ""
		var lip: Vector3 = (r["face"] as Vector3) - into * 0.1
		lip.y = float(r["top"]) + 0.15
		_begin(MANTLE, p.global_position, lip, r["stand"], 0.45 + h * 0.25, "vault_high", into)
		_witness(r["stand"])
		return "mantle"
	return _start_hang(r)


## Space pressed in the air (falling past an edge): catch it if it is at hand height.
func try_air_grab(dir: Vector3) -> String:
	if state != NONE or p.velocity.y > 1.0:
		return ""
	var r := probe(dir, 0.8, 1.3, 2.3)
	if r.is_empty():
		return ""
	return _start_hang(r)


func _start_hang(r: Dictionary) -> String:
	var into: Vector3 = -(r["n"] as Vector3)
	var hang := _hang_pos(r["face"], r["n"], r["top"])
	var c := r.get("node") as Node
	if c and c is Node3D and _handholds(c as Node3D).size() > 0:
		hang = _snap_hold(c as Node3D, hang, r["n"], r["top"])
	wall_n = r["n"]
	ledge_y = r["top"]
	_begin(HANG, p.global_position, p.global_position.lerp(hang, 0.5) + Vector3(0, 0.3, 0), hang, 0.35, "ledge_hang", into)
	_witness(hang + Vector3(0, 1.5, 0))
	return "hang"


func _hang_pos(face: Vector3, n: Vector3, top: float) -> Vector3:
	var h := face + n * 0.32
	h.y = top - tvv("hang_drop", 2.05)
	return h


func _begin(s: int, a: Vector3, b: Vector3, c: Vector3, d: float, clip: String, face_dir: Vector3) -> void:
	state = s
	t = 0.0
	dur = d
	p0 = a
	p1 = b
	p2 = c
	last_action = NAMES[s]
	counts[last_action] = int(counts.get(last_action, 0)) + 1
	p.velocity = Vector3.ZERO
	p.set_trav_collision(false)
	var fig: Node3D = p.get("_figure")
	if fig:
		fig.rotation.y = atan2(-face_dir.x, -face_dir.z)
		Assets.play_action(fig, clip, 1.0, s == HANG)
	if Perception.tg("traversal.log", false) or "--smoke" in OS.get_cmdline_user_args():
		if p.get("sandbox"):
			print("[smoke]   traversal %s from %s to %s" % [last_action, _v(a), _v(c)])


static func _v(v: Vector3) -> String:
	return "(%.1f, %.1f, %.1f)" % [v.x, v.y, v.z]


## Guards who see the climb look up at it and remember the spot.
func _witness(at: Vector3) -> void:
	var w := Perception.watch_of(p)
	if w == null:
		return
	for g in w.awake_guards():
		if g.can_see_point(p.global_position + Vector3(0, 1.2, 0), -1.0, [p.get_rid()]):
			g.look_toward(at, 4.0, true)
			g.last_known = at


## Called from player._physics_process while active. `mv` = (right, forward) input; returns true while it owns
## the body.
func tick(delta: float, mv: Vector2, jump: bool, drop: bool) -> bool:
	t += delta
	var fig: Node3D = p.get("_figure")
	match state:
		VAULT, MANTLE, CLIMB_UP:
			var u := clampf(t / dur, 0.0, 1.0)
			var e := u * u * (3.0 - 2.0 * u) if state != VAULT else u
			var a := p0.lerp(p1, e)
			var b := p1.lerp(p2, e)
			p.global_position = a.lerp(b, e)
			if u >= 1.0:
				_end()
				if carry_speed > 0.1:
					p.velocity = carry_dir * carry_speed
		HANG:
			if t < dur:
				var u := t / dur
				p.global_position = p0.lerp(p1, u).lerp(p1.lerp(p2, u), u)
				return true
			p.global_position = p2
			if drop or (jump and mv.y < -0.5):
				_drop_from_hang()
			elif jump or mv.y > 0.5:
				var stand := p2 - wall_n * 0.82
				stand.y = ledge_y
				if room_at(stand):
					var lip := p2 - wall_n * 0.1
					lip.y = ledge_y + 0.25
					_begin(CLIMB_UP, p2, lip, stand, 1.0, "ledge_climb", -wall_n)
			elif absf(mv.x) > 0.3:
				_shimmy(signf(mv.x), delta)
			elif fig and Assets.action_clip(fig) != "ledge_hang":
				Assets.play_action(fig, "ledge_hang", 1.0, true)
		PIPE:
			_pipe(delta, mv, jump, drop)
		SLIDE:
			var sp := lerpf(7.0, 2.5, clampf(t / dur, 0.0, 1.0))
			p.velocity.x = carry_dir.x * sp
			p.velocity.z = carry_dir.z * sp
			p.velocity.y -= 18.0 * delta
			p.move_and_slide()
			var clear := _ray(p.global_position + Vector3(0, 0.5, 0), p.global_position + Vector3(0, 1.85, 0)).is_empty()
			if (t >= dur and clear) or t > dur * 2.2:
				_end()
	return state != NONE


func _end() -> void:
	state = NONE
	p.set_trav_collision(true)
	var fig: Node3D = p.get("_figure")
	if fig and Assets.action_clip(fig) in ["ledge_hang", "ledge_shimmy", "climb_pipe"]:
		Assets.clear_action(fig)
	_air = false
	_peak_y = p.global_position.y


func _drop_from_hang() -> void:
	var at := p.global_position + wall_n * 0.3
	state = NONE
	last_action = "drop"
	counts["drop"] = int(counts.get("drop", 0)) + 1
	p.set_trav_collision(true)
	p.global_position = at
	p.velocity = Vector3.ZERO
	var fig: Node3D = p.get("_figure")
	if fig:
		Assets.play_action(fig, "drop_hang")
	_air = true
	_peak_y = at.y


func _shimmy(side: float, delta: float) -> void:
	var tangent := wall_n.cross(Vector3.UP).normalized() * side
	# the camera's right may be the wall's left: A / D follow the screen
	var cam_r: Vector3 = p.call("_cam_right")
	if cam_r.dot(wall_n.cross(Vector3.UP)) < 0.0:
		tangent = -tangent
	var step := tangent * tvv("shimmy_speed", 0.9) * delta
	var next := p.global_position + step
	# still an edge there: wall under the hands, top at the same height, nothing in the way sideways
	var hands := next + Vector3(0, tvv("hang_drop", 2.05) - 0.15, 0)
	var wall := _ray(hands, hands - wall_n * 0.8)
	var col := next - wall_n * 0.55
	var top := _ray(Vector3(col.x, ledge_y + 0.4, col.z), Vector3(col.x, ledge_y - 0.4, col.z))
	var side_block := _ray(p.global_position + Vector3(0, 1.4, 0), p.global_position + Vector3(0, 1.4, 0) + tangent * 0.45)
	if wall.is_empty() or top.is_empty() or absf((top["position"] as Vector3).y - ledge_y) > 0.25 or not side_block.is_empty():
		return
	p.global_position = next
	p2 = next
	counts["shimmy"] = int(counts.get("shimmy", 0)) + 1
	var fig: Node3D = p.get("_figure")
	_shimmy_anim -= delta
	if fig and _shimmy_anim <= 0.0:
		_shimmy_anim = Assets.play_action(fig, "ledge_shimmy", 1.0, false) * 0.95
		if _shimmy_anim <= 0.0:
			_shimmy_anim = 0.5


# ------------------------------------------------------------------ authored climbables (drainpipes, ivy, crates)

func _climb_kind(n: Node) -> String:
	var k: Variant = n.get_meta("climbable", n.get_meta("climb_kind", ""))
	if k is bool:
		return "ledge" if k else ""
	if str(k) == "" and n.is_in_group("climbable"):
		return "ledge"
	return str(k)


## The tagged climbable in front: a collider hit by a ray ahead (or an ancestor) with meta `climbable` /
## `climb_kind` or in group "climbable"; or a marker node (no collision) with meta `climbable` within 0.9 m.
func _climbable_ahead(dir: Vector3) -> Node3D:
	dir = Vector3(dir.x, 0, dir.z).normalized()
	for hgt in [1.0, 0.5, 1.6]:
		var from := p.global_position + Vector3(0, hgt, 0)
		var h := _ray(from, from + dir * 0.9)
		if h.is_empty():
			continue
		var col := h.get("collider") as Node
		for i in 4:
			if col == null or col == p.get_parent():
				break
			if col.has_meta("climbable") or col.has_meta("climb_kind") or col.is_in_group("climbable"):
				return col as Node3D
			col = col.get_parent()
	for n in p.get_tree().get_nodes_in_group("climbable"):
		var c := n as Node3D
		if c == null or c is CollisionObject3D or not Perception.same_world(c, p):
			continue
		var to := c.global_position - p.global_position
		to.y = 0.0
		if to.length() < 0.9 and (to.length() < 0.3 or to.normalized().dot(dir) > 0.5):
			return c
	return null


func _handholds(c: Node3D) -> Array:
	var hh: Variant = c.get_meta("handholds", [])
	return hh if hh is Array else []


func _snap_hold(c: Node3D, hang: Vector3, n: Vector3, top: float) -> Vector3:
	var best := hang
	var best_d := INF
	for lp in _handholds(c):
		var wp := c.to_global(lp)
		var hp := wp + n * 0.32
		hp.y = wp.y - tvv("hang_drop", 2.05)
		var d := hp.distance_to(hang)
		if d < best_d:
			best_d = d
			best = hp
			ledge_y = wp.y
	return best


## Where a straight climb tops out: meta `climb_top` (world y), else the height at which the wall in front ends.
func _climb_top(c: Node3D) -> float:
	if c.has_meta("climb_top"):
		return float(c.get_meta("climb_top"))
	var base := p.global_position
	var dir := -wall_n
	var y := 0.5
	while y < 24.0:
		var from := base + Vector3(0, y, 0)
		if _ray(from, from + dir * 1.2).is_empty():
			return base.y + y - 0.1
		y += 0.25
	return base.y + 3.0


func _start_pipe(c: Node3D, dir: Vector3) -> String:
	climbable = c
	dir = Vector3(dir.x, 0, dir.z).normalized()
	var from := p.global_position + Vector3(0, 1.0, 0)
	var h := _ray(from, from + dir * 1.2)
	var at := p.global_position
	if not h.is_empty():
		var n: Vector3 = h["normal"]
		wall_n = Vector3(n.x, 0, n.z).normalized()
		at = (h["position"] as Vector3) + wall_n * 0.35
	else:
		var to := c.global_position - p.global_position
		to.y = 0.0
		wall_n = -to.normalized() if to.length() > 0.05 else -dir
		at = c.global_position + wall_n * 0.35
	at.y = p.global_position.y + 0.2
	ledge_y = _climb_top(c)
	_begin(PIPE, p.global_position, at, at, 0.2, "climb_pipe", -wall_n)
	_witness(at + Vector3(0, 2.0, 0))
	return "pipe"


func _pipe(delta: float, mv: Vector2, jump: bool, drop: bool) -> void:
	if t < dur:
		p.global_position = p0.lerp(p2, t / dur)
		return
	if drop:
		_drop_from_hang()
		return
	var fig: Node3D = p.get("_figure")
	var v := mv.y if absf(mv.y) > 0.3 else (1.0 if jump else 0.0)
	if absf(v) > 0.0:
		var pos := p.global_position + Vector3(0, v * tvv("pipe_speed", 1.2) * delta, 0)
		if v < 0.0 and not _ray(pos + Vector3(0, 0.3, 0), pos - Vector3(0, 0.05, 0)).is_empty():
			_end()
			return
		p.global_position = pos
		if fig and not Assets.is_action(fig):
			Assets.play_action(fig, "climb_pipe", 1.0)
	var hands := p.global_position.y + tvv("hang_drop", 2.05)
	if hands >= ledge_y - 0.05:
		var stand := p.global_position - wall_n * 0.9
		stand.y = ledge_y
		if room_at(stand):
			var lip := p.global_position - wall_n * 0.2
			lip.y = ledge_y + 0.25
			_begin(CLIMB_UP, p.global_position, lip, stand, 1.0, "ledge_climb", -wall_n)
		else:
			p.global_position.y = ledge_y - tvv("hang_drop", 2.05)
			p2 = p.global_position
			state = HANG


# ------------------------------------------------------------------ slide, falls

func try_slide(dir: Vector3) -> String:
	if state != NONE or dir.length() < 0.1:
		return ""
	carry_dir = Vector3(dir.x, 0, dir.z).normalized()
	state = SLIDE
	t = 0.0
	dur = 0.75
	last_action = "slide"
	counts["slide"] = int(counts.get("slide", 0)) + 1
	var fig: Node3D = p.get("_figure")
	if fig:
		fig.rotation.y = atan2(-carry_dir.x, -carry_dir.z)
		Assets.play_action(fig, "slide_under")
	return "slide"


## Called every physics frame while not traversing (after move_and_slide). Returns "roll" / "stumble" / "land" on
## the landing frame, else "".
func track_fall(on_floor: bool) -> String:
	var y := p.global_position.y
	if absf(y - _last_y) > 1.2:
		_peak_y = y              # a teleport (missions, tests, leaving a hiding spot), not a fall
	_last_y = y
	if not on_floor:
		if not _air:
			_air = true
			_peak_y = y
		_peak_y = maxf(_peak_y, y)
		return ""
	if not _air:
		return ""
	_air = false
	var fall := _peak_y - y
	last_fall = fall
	if fall > tvv("roll_max", 4.0):
		last_landing = "stumble"
	elif fall > tvv("roll_from", 1.8):
		last_landing = "roll"
	elif fall > 0.8:
		last_landing = "land"
	else:
		return ""
	counts[last_landing] = int(counts.get(last_landing, 0)) + 1
	return last_landing
