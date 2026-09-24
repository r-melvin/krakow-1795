extends Node
## The painted look: a full-screen canvas pass (assets/shaders/looks/canvas/oil.gdshader) over the finished 3D
## frame, under every UI layer. On by default (Options: "Painted look", setting `look`); `-- --look=<name>` swaps
## in another shader from assets/shaders/looks/canvas/ for review, `--look=off` disables it for a run.
## docs/GDD.md "Look".

const DEFAULT := "oil"
const LAYER := -1            # canvases draw after the 3D world in order; the UI layers start at 1

var _rect: ColorRect
var _name := DEFAULT


static func look_arg() -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--look="):
			return a.trim_prefix("--look=")
	return ""


func _ready() -> void:
	add_to_group("look")
	var arg := look_arg()
	if arg != "":
		_name = arg
	var layer := CanvasLayer.new()
	layer.layer = LAYER
	add_child(layer)
	_rect = ColorRect.new()
	_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_rect.color = Color(0, 0, 0, 0)     # if the shader ever fails to compile the frame shows through instead of a white rect
	layer.add_child(_rect)
	apply()
	if arg != "":
		print("[look] preview active: ", arg)


## Reads the setting (and the command-line override) and shows or hides the pass.
func apply() -> void:
	var on: bool = bool(GameState.settings.get("look", true)) if look_arg() == "" else look_arg() != "off"
	var path := "res://assets/shaders/looks/canvas/%s.gdshader" % _name
	if on and _name != "off" and ResourceLoader.exists(path):
		if _rect.material == null or (_rect.material as ShaderMaterial).shader.resource_path != path:
			var m := ShaderMaterial.new()
			m.shader = load(path)
			_rect.material = m
		_rect.visible = true
	else:
		if on and _name != "off":
			push_warning("look: no shader " + path)
		_rect.visible = false
