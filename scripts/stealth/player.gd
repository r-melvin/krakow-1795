extends CharacterBody3D
class_name Player
## Third-person stealth controller. Builds its own body, camera rig and light probe at runtime
## so the scene file stays trivial until Blender assets arrive.

const WALK_SPEED := 3.0
const SPRINT_SPEED := 6.0
const CROUCH_SPEED := 1.6
const ACCEL := 12.0
const MOUSE_SENS := 0.0025
const GRAVITY := 18.0

var is_crouching := false
var is_sprinting := false
var noise := 0.0          ## 0..1, read by guards
var visibility := 1.0     ## 0..1, multiplier on guard detection (crouch, shadow)

var _yaw := 0.0
var _pitch := -0.25
var _pivot: Node3D
var _arm: SpringArm3D
var _camera: Camera3D
var _figure: Node3D
var _shape: CollisionShape3D


func _ready() -> void:
	add_to_group("player")
	_build_body()
	_build_camera()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


func _build_body() -> void:
	_shape = CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.35
	cap.height = 1.8
	_shape.shape = cap
	_shape.position.y = 0.9
	add_child(_shape)

	_figure = Assets.instance("player_figure")
	if _figure == null:
		_figure = Node3D.new()
		var mi := MeshInstance3D.new()
		var m := CapsuleMesh.new()
		m.radius = 0.35
		m.height = 1.8
		mi.mesh = m
		mi.position.y = 0.9
		_figure.add_child(mi)
	add_child(_figure)


func _build_camera() -> void:
	_pivot = Node3D.new()
	_pivot.position.y = 1.5
	add_child(_pivot)
	_arm = SpringArm3D.new()
	_arm.spring_length = 4.0
	_arm.margin = 0.2
	_arm.add_excluded_object(get_rid())
	_pivot.add_child(_arm)
	_camera = Camera3D.new()
	_camera.fov = 70
	_camera.current = true
	_arm.add_child(_camera)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		_yaw -= event.relative.x * MOUSE_SENS
		_pitch = clampf(_pitch - event.relative.y * MOUSE_SENS, -1.2, 0.6)
	if event.is_action_pressed("toggle_mouse"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE if Input.mouse_mode == Input.MOUSE_MODE_CAPTURED else Input.MOUSE_MODE_CAPTURED


func _physics_process(delta: float) -> void:
	_pivot.rotation = Vector3(_pitch, _yaw, 0)

	is_crouching = Input.is_action_pressed("crouch")
	is_sprinting = Input.is_action_pressed("sprint") and not is_crouching

	var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var forward := -_pivot.global_transform.basis.z
	forward.y = 0
	forward = forward.normalized()
	var right := _pivot.global_transform.basis.x
	right.y = 0
	right = right.normalized()
	var wish := (forward * -input.y + right * input.x)

	var speed := WALK_SPEED
	if is_crouching:
		speed = CROUCH_SPEED
	elif is_sprinting:
		speed = SPRINT_SPEED

	var target := wish * speed
	velocity.x = move_toward(velocity.x, target.x, ACCEL * delta)
	velocity.z = move_toward(velocity.z, target.z, ACCEL * delta)
	if not is_on_floor():
		velocity.y -= GRAVITY * delta
	else:
		velocity.y = 0
	move_and_slide()

	var moving := wish.length() > 0.1
	if moving:
		_figure.rotation.y = lerp_angle(_figure.rotation.y, atan2(-wish.x, -wish.z), 10 * delta)

	# Crouch: shrink the visual and collision height so guards' rays are more likely blocked by low cover.
	var h := 1.0 if is_crouching else 1.8
	_shape.shape.height = h
	_shape.position.y = h * 0.5
	_figure.scale.y = h / 1.8

	# Noise & visibility feed guard perception.
	if not moving:
		noise = 0.0
	elif is_crouching:
		noise = 0.15
	elif is_sprinting:
		noise = 1.0
	else:
		noise = 0.45
	visibility = 0.5 if is_crouching else 1.0


func head_position() -> Vector3:
	return global_position + Vector3(0, 0.6 if is_crouching else 1.5, 0)


func rotate_camera(euler: Vector3) -> void:
	_pitch = euler.x
	_yaw = euler.y
	_pivot.rotation = Vector3(_pitch, _yaw, 0)
