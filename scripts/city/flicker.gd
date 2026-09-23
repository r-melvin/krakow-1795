extends OmniLight3D
## Flame light: energy wanders around its base value (candle: slow and small; lantern: faster; brazier: bigger).
## Stealth: `douse(secs)` puts it out (the pool goes; group "flame_lights" samplers skip it) until `relight()` or
## the time runs out (the lamplighter's round).

@export var amount := 0.12
@export var speed := 6.0
var doused_left := 0.0
var _base := 1.0
var _t := 0.0
var _seed := 0.0


func _ready() -> void:
	_base = light_energy
	_seed = randf() * 100.0


func _process(delta: float) -> void:
	if doused_left > 0.0:
		doused_left -= delta
		if doused_left <= 0.0:
			relight()
		return
	_t += delta * speed
	var n := sin(_t + _seed) * 0.5 + sin(_t * 2.3 + _seed * 1.7) * 0.3 + sin(_t * 5.1 + _seed * 0.4) * 0.2
	light_energy = _base * (1.0 + amount * n)


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
