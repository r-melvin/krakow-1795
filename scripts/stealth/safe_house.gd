extends Area3D
## Night objective. Reaching it ends the mission successfully.

func _ready() -> void:
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(2.5, 3, 2.5)
	shape.shape = box
	shape.position.y = 1.5
	add_child(shape)
	var marker := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 1.2
	cyl.bottom_radius = 1.2
	cyl.height = 0.1
	marker.mesh = cyl
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.9, 0.7, 0.2)
	mat.emission_enabled = true
	mat.emission = Color(0.9, 0.6, 0.1)
	mat.emission_energy_multiplier = 2.0
	marker.material_override = mat
	add_child(marker)
	var light := OmniLight3D.new()
	light.light_color = Color(1.0, 0.75, 0.4)
	light.omni_range = 6
	light.light_energy = 2
	light.position.y = 2.5
	add_child(light)
	body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node3D) -> void:
	if body is Player and not GameState.night_objective_done:
		GameState.night_objective_done = true
		GameState.end_night(true)
