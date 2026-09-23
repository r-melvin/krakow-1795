extends OmniLight3D
## Flame light: energy wanders around its base value (candle: slow and small; lantern: faster; brazier: bigger).

@export var amount := 0.12
@export var speed := 6.0
var _base := 1.0
var _t := 0.0
var _seed := 0.0


func _ready() -> void:
	_base = light_energy
	_seed = randf() * 100.0


func _process(delta: float) -> void:
	_t += delta * speed
	var n := sin(_t + _seed) * 0.5 + sin(_t * 2.3 + _seed * 1.7) * 0.3 + sin(_t * 5.1 + _seed * 0.4) * 0.2
	light_energy = _base * (1.0 + amount * n)
