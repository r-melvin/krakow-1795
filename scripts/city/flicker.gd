extends OmniLight3D
## Flame light: energy wanders around its base value (candle: slow and small; lantern: faster; brazier: bigger).
## Stealth: `douse(secs)` puts it out (the pool goes; group "flame_lights" samplers skip it) until `relight()` or
## the time runs out (the lamplighter's round).

@export var amount := 0.12
@export var speed := 6.0
@export var wander := 0.025      ## metres the flame moves about its socket (candle 2-3 cm; lantern 1 cm; brazier 6 cm)
@export var gusts := true        ## occasional draughts: a sharper dip and a lurch of the flame
var _home := Vector3.ZERO
var _gust := 0.0
var _gust_next := 0.0
var doused_left := 0.0
var _base := 1.0
var _t := 0.0
var _seed := 0.0


func _ready() -> void:
	_base = light_energy
	_seed = randf() * 100.0
	_home = position
	_gust_next = randf_range(3.0, 12.0)


func _process(delta: float) -> void:
	if doused_left > 0.0:
		doused_left -= delta
		if doused_left <= 0.0:
			relight()
		return
	_t += delta * speed
	var n := sin(_t + _seed) * 0.5 + sin(_t * 2.3 + _seed * 1.7) * 0.3 + sin(_t * 5.1 + _seed * 0.4) * 0.2
	# draughts: every few seconds the flame lies over and the light dips, then recovers
	if gusts:
		_gust_next -= delta
		if _gust_next <= 0.0:
			_gust = randf_range(0.6, 1.0)
			_gust_next = randf_range(3.0, 14.0)
		_gust = maxf(_gust - delta * 1.8, 0.0)
	light_energy = _base * (1.0 + amount * n) * (1.0 - 0.35 * _gust)
	if wander > 0.0:
		var w := Vector3(sin(_t * 0.9 + _seed) + 0.5 * sin(_t * 3.7 + _seed * 2.1),
				0.4 * sin(_t * 1.3 + _seed * 0.7) - 0.6 * _gust,
				cos(_t * 1.1 + _seed * 1.3) + 0.5 * sin(_t * 4.3 + _seed))
		position = _home + w * wander * (1.0 + 1.5 * _gust)


func douse(secs: float) -> void:
	doused_left = maxf(secs, 0.01)
	light_energy = 0.0
	visible = false


func relight() -> void:
	doused_left = 0.0
	light_energy = _base
	visible = true


func is_doused() -> bool:
	return doused_left > 0.0
