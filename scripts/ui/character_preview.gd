extends SubViewportContainer
## Live 3D turntable of a character model in its own World3D: key, fill and rim light, a plinth, a slow turn
## and the "idle" clip. glTF figures are ~10 MB, so they load on a thread (ResourceLoader.load_threaded_request)
## while a spinner shows; loaded scenes go into Assets' cache and instanced figures are kept for reuse.

signal loaded(figure_name: String)

const SPIN_SPEED := 0.35   ## rad/s

static var _pending: Dictionary = {}     ## path -> true while a threaded load is in flight

var _viewport: SubViewport
var _turntable: Node3D
var _figures: Dictionary = {}            ## name -> Node3D pivot (instanced, cached)
var _wanted := ""
var _current: Node3D
var _spinner: Label
var _spin_t := 0.0


func _ready() -> void:
	stretch = true
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_viewport = SubViewport.new()
	_viewport.own_world_3d = true
	_viewport.transparent_bg = true
	_viewport.msaa_3d = Viewport.MSAA_4X
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(_viewport)

	var env := Environment.new()
	env.background_mode = Environment.BG_CLEAR_COLOR
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.45, 0.5, 0.62)
	env.ambient_light_energy = 0.35
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 1.05
	var we := WorldEnvironment.new()
	we.environment = env
	_viewport.add_child(we)

	var cam := Camera3D.new()
	cam.fov = 26
	_viewport.add_child(cam)
	cam.look_at_from_position(Vector3(0, 1.25, 6.8), Vector3(0, 0.88, 0))
	cam.current = true

	var key := DirectionalLight3D.new()     # warm lantern key from the front left
	key.light_color = Color(1.0, 0.86, 0.66)
	key.light_energy = 1.25
	key.shadow_enabled = true
	key.rotation = Vector3(deg_to_rad(-30), deg_to_rad(-35), 0)
	_viewport.add_child(key)
	var fill := OmniLight3D.new()           # cold moonlight fill from the right
	fill.light_color = Color(0.55, 0.65, 0.9)
	fill.light_energy = 1.2
	fill.omni_range = 9
	fill.position = Vector3(2.6, 1.6, 2.2)
	_viewport.add_child(fill)
	var rim := SpotLight3D.new()            # brass rim from behind
	rim.light_color = Color(1.0, 0.8, 0.5)
	rim.light_energy = 5.0
	rim.spot_range = 8
	rim.spot_angle = 35
	rim.position = Vector3(-1.2, 2.6, -2.4)
	_viewport.add_child(rim)
	rim.look_at(Vector3(0, 1.1, 0))

	var plinth := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = 0.62
	cyl.bottom_radius = 0.66
	cyl.height = 0.08
	plinth.mesh = cyl
	plinth.position.y = -0.04
	var pm := StandardMaterial3D.new()
	pm.albedo_color = Color(0.035, 0.04, 0.055)
	pm.roughness = 0.35
	plinth.material_override = pm
	_viewport.add_child(plinth)

	_turntable = Node3D.new()
	_viewport.add_child(_turntable)
	_turntable.rotation.y = PI - 0.4    # figures face -Z; turn them toward the camera

	_spinner = UiTheme.label("", 20, UiTheme.BRASS_BRIGHT, "italic")
	_spinner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_spinner.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_spinner.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_spinner)


## Show figure `name` (e.g. "figure_veteran_f"). Starts a threaded load if it is not cached yet.
func show_figure(name: String) -> void:
	_wanted = name
	if _figures.has(name):
		_display(name)
		return
	var path := _path(name)
	if not ResourceLoader.exists(path):
		_spinner.text = "No model for %s" % name
		return
	if not Assets._cache.has(path) and not _pending.has(path):
		if ResourceLoader.load_threaded_request(path, "", true) == OK:
			_pending[path] = true
	if _current:
		_current.visible = false
		_current = null


func is_ready() -> bool:
	return _current != null and _current.name == _wanted


func _path(name: String) -> String:
	return "res://assets/models/%s.glb" % name


func _process(delta: float) -> void:
	_turntable.rotation.y += delta * SPIN_SPEED
	if _wanted == "" or is_ready():
		_spinner.text = ""
		return
	# Poll every in-flight load so a figure the player skipped past still lands in the cache.
	for path in _pending.keys():
		var st := ResourceLoader.load_threaded_get_status(path)
		if st == ResourceLoader.THREAD_LOAD_LOADED:
			Assets._cache[path] = ResourceLoader.load_threaded_get(path)
			_pending.erase(path)
		elif st == ResourceLoader.THREAD_LOAD_FAILED or st == ResourceLoader.THREAD_LOAD_INVALID_RESOURCE:
			_pending.erase(path)
			Assets._cache[path] = null
	var wp := _path(_wanted)
	if Assets._cache.has(wp):
		if Assets._cache[wp] == null:
			_spinner.text = "Model failed to load"
			return
		var pivot := Assets.character(_wanted)
		if pivot:
			_figures[_wanted] = pivot
			_turntable.add_child(pivot)
			_display(_wanted)
		return
	_spin_t += delta
	var frames := ["◐", "◓", "◑", "◒"]
	_spinner.text = "%s   Loading figure…" % frames[int(_spin_t * 6.0) % 4]


func _display(name: String) -> void:
	for n in _figures:
		(_figures[n] as Node3D).visible = n == name
	_current = _figures[name]
	_current.name = name
	Assets.play(_current, "idle")
	_spinner.text = ""
	_turntable.rotation.y = PI - 0.4
	_current.scale = Vector3.ONE * 0.97
	create_tween().tween_property(_current, "scale", Vector3.ONE, 0.3).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	loaded.emit(name)
