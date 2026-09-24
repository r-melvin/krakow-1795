// Cloth swaying in the wind (applied by scripts/city/dressing.gd): washing on a line (materials cloth_laundry*) and
// the hanging valances of awnings and market stalls (cloth_awning*: line_sag 0 and line_h at the eave, so only the
// cloth below the eave moves, along sway_dir, with the phase running along phase_axis).
// The line runs along the model's +Z from the wall hook (z = 0) to the pole (z = line_len) and sags as
// line_h - line_sag * sin(pi z / line_len), matching _laundry() in assets/blender/build_assets.py. Each vertex
// swings out along X by a sine of time scaled by how far it hangs below the line, so the pegged top edge stays put
// and the hems move most. Amplitude = a calm-air stir plus the global `wind` (scripts/city/weather.gd sets it;
// zero when there is no weather node). Frozen pieces pass a high stiffness and barely move.
// The fragment keeps the imported cloth look (albedo / normal / roughness) and lets lantern light through thin
// linen (backlight).
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_burley, specular_schlick_ggx;

global uniform vec2 wind;

uniform vec4 albedo : source_color = vec4(1.0);
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform bool use_normal = false;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float normal_scale = 1.0;
uniform sampler2D rough_tex : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform float roughness : hint_range(0.0, 1.0) = 0.95;
uniform vec3 uv1_scale = vec3(1.0);
uniform vec3 uv1_offset = vec3(0.0);

uniform float line_h = 3.2;
uniform float line_sag = 0.45;
uniform float line_len = 6.0;
uniform float calm_amp = 0.05;        // radians-ish of swing per metre of hang in still air
uniform float wind_gain = 0.035;      // extra per m/s of wind
uniform float stiffness : hint_range(0.0, 1.0) = 0.0;
uniform float translucency : hint_range(0.0, 1.0) = 0.35;
uniform vec3 sway_dir = vec3(1.0, 0.0, 0.0);     // model-space direction the cloth swings in
uniform vec3 phase_axis = vec3(0.0, 0.0, 1.0);   // model-space axis along the line / eave

void vertex() {
	float zl = line_h - line_sag * sin(PI * clamp(dot(VERTEX, phase_axis) / line_len, 0.0, 1.0));
	float hang = max(zl - VERTEX.y, 0.0);
	float ws = length(wind);
	float amp = (calm_amp + wind_gain * ws) * (1.0 - 0.85 * stiffness);
	float along = dot(VERTEX, phase_axis);
	float ph = TIME * (1.3 + 0.12 * ws) + along * 1.1 + NODE_POSITION_WORLD.x * 0.37 + NODE_POSITION_WORLD.z * 0.21;
	float swing = sin(ph) + 0.35 * sin(ph * 2.3 + hang * 3.0);
	VERTEX += sway_dir * (amp * hang * swing);
	VERTEX += phase_axis * (0.3 * amp * hang * sin(ph * 0.8 + 1.0));
	VERTEX.y += 0.15 * amp * hang * hang * abs(swing);
	UV = UV * uv1_scale.xy + uv1_offset.xy;
}

void fragment() {
	vec4 c = texture(albedo_tex, UV) * albedo;
	ALBEDO = c.rgb;
	ROUGHNESS = texture(rough_tex, UV).g * roughness;
	SPECULAR = 0.25;
	if (use_normal) {
		NORMAL_MAP = texture(normal_tex, UV).rgb;
		NORMAL_MAP_DEPTH = normal_scale;
	}
	BACKLIGHT = c.rgb * translucency;
}
