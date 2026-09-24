extends Node
## Look preview for art-direction review, active only with `-- --look=<painterly|ink_wash|cel|puppet|grime>`:
## a full-screen canvas layer running assets/shaders/looks/canvas/<name>.gdshader over the finished 3D frame,
## under the UI. Changes nothing when the flag is absent.

static func look_name() -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--look="):
			return a.trim_prefix("--look=")
	return ""


func _ready() -> void:
	var name := look_name()
	if name == "":
		queue_free()
		return
	var path := "res://assets/shaders/looks/canvas/%s.gdshader" % name
	if not ResourceLoader.exists(path):
		push_warning("look preview: no shader " + path)
		queue_free()
		return
	var layer := CanvasLayer.new()
	layer.layer = 5            # above the 3D view, below the HUD (10+)
	add_child(layer)
	var rect := ColorRect.new()
	rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var m := ShaderMaterial.new()
	m.shader = load(path)
	rect.material = m
	layer.add_child(rect)
	print("[look] preview active: ", name)
