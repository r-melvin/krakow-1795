// Overlay pass (next_pass) for the cobble ground: a snow layer and rain puddles on top of the base
// StandardMaterial3D, so the base keeps its parallax, textures and tuning. Driven by the globals
// `snow_cover` and `wetness` (scripts/city/weather.gd). Snow settles in the joints between the setts
// first (the cobble height map), then drifts over them in noise-masked patches; at snow_cover = 1 the
// square is dusted, not buried. Rain fills the joints and hollows with dark, glossy water.
// Building plaster / wood / tile wetness is a parameter pass on their own materials (assets.gd).
shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_back, diffuse_burley, specular_schlick_ggx;

global uniform float snow_cover;
global uniform float wetness;

uniform bool has_height = false;
uniform sampler2D height_tex : filter_linear_mipmap, repeat_enable, hint_default_white;
uniform vec3 uv1_scale = vec3(1.0);
uniform vec3 uv1_offset = vec3(0.0);
uniform float snow_amount = 0.42;   // how much of the height range fills at snow_cover = 1
uniform vec3 snow_color : source_color = vec3(0.86, 0.88, 0.93);

varying vec3 w_pos;

float hash2(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float vnoise(vec2 x) {
	vec2 i = floor(x);
	vec2 f = fract(x);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash2(i), hash2(i + vec2(1, 0)), f.x), mix(hash2(i + vec2(0, 1)), hash2(i + vec2(1, 1)), f.x), f.y);
}

float fbm(vec2 p) {
	float a = 0.5;
	float s = 0.0;
	for (int i = 0; i < 4; i++) {
		s += a * vnoise(p);
		p = p * 2.07 + vec2(3.1, 7.7);
		a *= 0.5;
	}
	return s / 0.9375;
}

void vertex() {
	w_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	VERTEX += NORMAL * 0.004;
}

void fragment() {
	if (w_pos.y < -50.0) {
		discard;
	}
	vec2 uv = UV * uv1_scale.xy + uv1_offset.xy;
	float h = has_height ? texture(height_tex, uv).r : 0.5;
	float n = fbm(w_pos.xz * 0.3) * 0.7 + fbm(w_pos.xz * 1.9) * 0.3;
	// snow: a fill level rising through the height range, pushed up and down by drifts
	float level = snow_cover * snow_amount - 0.1 + (n - 0.5) * 0.55;
	float snow = smoothstep(h - 0.06, h + 0.04, level) * smoothstep(0.02, 0.12, snow_cover);
	// water: joints and hollows first, a thin film over the rest when it really rains
	float puddle = smoothstep(0.42, 0.2, h + (n - 0.5) * 0.45) * wetness;
	float film = wetness * 0.35;
	float water = clamp(max(puddle * 0.75, film), 0.0, 1.0) * (1.0 - snow);
	float a = clamp(snow * 0.95 + water, 0.0, 1.0);
	if (a < 0.004) {
		discard;
	}
	float k = snow * 0.95 / max(a, 0.001);
	vec3 slush = snow_color * mix(1.0, 0.62, wetness);
	ALBEDO = mix(vec3(0.015, 0.016, 0.018), slush, k);
	ROUGHNESS = mix(0.06, mix(0.78, 0.3, wetness), k);
	SPECULAR = 0.5;
	ALPHA = a;
}
