extends "res://scripts/mission/interactable.gd"
## A hiding spot (docs/STEALTH.md 3.4): hay cart, barrels, doorway niche, under a coach, cellar hatch, lean-to, and
## benches (kind "bench": sitting, not hidden: the crowd factor applies when a townsman sits or stands close by).
## `E` enters and leaves (player.enter_spot / leave_spot). Inside, `hides_player` spots drop visibility to 0 and the
## camera goes to `peek_point`. A guard who saw the player go in (perceived within hiding.enter_seen_window) comes
## to search it and finds them; during Evasion guards prod nearby spots (hiding.evasion_find_chance).
## A downed guard dragged here is stashed (`stash_body`) and cannot be found by patrols until he wakes.
## Local points (in this node's space): peek_point, exit_point, inner_point.

const Perception := preload("res://scripts/stealth/perception.gd")

var kind := "hay"
var peek_point := Vector3(0, 1.1, 0.6)
var exit_point := Vector3(0, 0, 1.3)
var inner_point := Vector3.ZERO
var hides_player := true
var shows_figure := false        ## niche / lean-to: the figure stays, huddled (crouch_hide)
var takes_body := true
var occupant: Node3D = null
var body: Node3D = null
var witnessed: Dictionary = {}   ## guard -> true: saw the player go in
var last_searched := -100.0

const LABELS := {"hay": "Hay cart", "barrel": "Barrels", "niche": "Doorway niche", "coach": "Under the coach",
		"hatch": "Cellar hatch", "leanto": "Woodpile lean-to", "straw": "Straw heap", "bench": "Bench"}


func _ready() -> void:
	if display_name == "":
		display_name = LABELS.get(kind, "Hiding place")
	if kind == "bench":
		hides_player = false
		shows_figure = true
		takes_body = false
	marker_height = 1.6
	if highlight_root == null:
		highlight_root = self          # never tint the parent (the whole district); a placed prop may be passed in
	set_meta("low_priority", true)
	prompt_func = _prompt
	handler = _use
	super()
	add_to_group("hiding_spot")


func _prompt() -> String:
	var p := _player_near()
	if occupant != null:
		return "leave" if occupant == p else ""
	if p and p.get("dragging") != null:
		return "hide the body" if takes_body and body == null else ""
	if p and p.get("hidden_spot") != null:
		return ""
	return "sit" if kind == "bench" else "hide"


func _player_near() -> Node3D:
	var w := Perception.watch_of(self)
	return w.get_player() if w else get_tree().get_first_node_in_group("player") as Node3D


func _use(actor: Node) -> bool:
	if actor.get("dragging") != null:
		return takes_body and body == null and actor.end_drag(self)
	if occupant == actor:
		actor.leave_spot()
		return true
	if occupant == null and actor.has_method("enter_spot"):
		return actor.enter_spot(self)
	return false


func point(local: Vector3) -> Vector3:
	return global_transform * local


## Where a guard stands to search it: a step beyond the exit point, so the player pulled out lands in front of him.
func search_point() -> Vector3:
	var e := point(exit_point)
	var out := e - global_position
	out.y = 0.0
	return e + (out.normalized() * 0.8 if out.length() > 0.05 else Vector3.ZERO)


## The player got in: every guard who had him in view a moment ago saw it and comes to look.
func on_entered(p: Node3D) -> void:
	occupant = p
	witnessed.clear()
	var w := Perception.watch_of(self)
	if w == null:
		return
	if hides_player:
		var window := float(w.tv("hiding.enter_seen_window", 1.5))
		for g in w.awake_guards():
			if not g.is_runner and g.saw_player_within(window) and g.suspicion >= float(w.tv("suspicion.curious", 20.0)) * 0.5:
				witnessed[g] = true
				g.search_spot(self)
	w.hiding_changed.emit(self, true)


func on_left(_p: Node3D) -> void:
	occupant = null
	witnessed.clear()
	var w := Perception.watch_of(self)
	if w:
		w.hiding_changed.emit(self, false)


## A guard searches the spot. Returns "player" if he pulls the player out, "body" if he finds a stashed body.
func search(g: Node, deliberate: bool) -> String:
	var w := Perception.watch_of(self)
	last_searched = w.clock if w else 0.0
	if occupant != null and hides_player:
		var chance := float(w.tv("hiding.evasion_find_chance", 0.2)) if w else 0.2
		if witnessed.has(g) or (not deliberate and randf() < chance):
			var p := occupant
			p.leave_spot(true)
			if w:
				w.bark(g, "alarm")
			return "player"
	if body != null and is_instance_valid(body) and not body.body_found:
		var b := body
		release_body(b)
		g.find_body(b)
		return "body"
	return ""


func stash_body(g: Node3D) -> bool:
	if not takes_body or body != null:
		return false
	body = g
	g.hidden_in = self
	g.visible = false
	g.global_position = point(inner_point)
	return true


func release_body(g: Node3D) -> void:
	if body == g:
		body = null
	g.hidden_in = null
	g.visible = true
	g.global_position = point(exit_point)
