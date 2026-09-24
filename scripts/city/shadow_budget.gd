extends Node
## Shadow budget: only the few flame lights nearest the camera cast shadows. Every omni shadow renders the scene
## again, so a dozen shadowed lanterns cost more than the whole town; four near ones look the same from the street.

@export var budget := 4
@export var period := 0.4
var _t := 0.0


func _process(delta: float) -> void:
	_t += delta
	if _t < period:
		return
	_t = 0.0
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return
	var lights := get_tree().get_nodes_in_group("shadow_capable")
	var cp := cam.global_position
	lights.sort_custom(func(a, b) -> bool:
		return a.global_position.distance_squared_to(cp) < b.global_position.distance_squared_to(cp))
	for i in lights.size():
		var l := lights[i] as Light3D
		if l == null:
			continue
		var want := i < budget and l.visible and l.light_energy > 0.05
		if l.shadow_enabled != want:
			l.shadow_enabled = want
