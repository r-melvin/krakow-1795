shader_type spatial;
render_mode unshaded, cull_disabled, depth_test_disabled, blend_mix, shadows_disabled;
// A billboard ring over a watcher's head that fills clockwise from the top with his suspicion of the player.
// Drawn only while he is taking the player in, so the "stealth meter" lives on the man who is looking.
uniform float fill : hint_range(0.0, 1.0) = 0.0;
uniform vec4 color : source_color = vec4(0.9, 0.75, 0.3, 1.0);
uniform float alpha : hint_range(0.0, 1.0) = 1.0;

void vertex() {
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
}

void fragment() {
	vec2 p = UV * 2.0 - 1.0;
	float r = length(p);
	float ring = smoothstep(0.62, 0.66, r) * (1.0 - smoothstep(0.90, 0.94, r));
	float ang = atan(p.x, -p.y);            // 0 at the top, clockwise
	float t = (ang + 3.14159265) / 6.2831853;
	t = fract(t + 0.5);
	float on = step(t, fill);
	vec3 track = vec3(0.05, 0.04, 0.03);
	ALBEDO = mix(track, color.rgb, on);
	ALPHA = ring * alpha * mix(0.45, 1.0, on);
	// a dot in the middle so an empty ring still reads as an eye
	float dot_ = 1.0 - smoothstep(0.10, 0.14, r);
	ALBEDO = mix(ALBEDO, color.rgb, dot_);
	ALPHA = max(ALPHA, dot_ * alpha * 0.9);
}
