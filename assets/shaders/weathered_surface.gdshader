// Building and prop surfaces that catch the weather (scripts/core/assets.gd converts the plain glTF
// StandardMaterial3D: albedo, normal and ORM roughness/metal maps, UV scale, cull mode are copied in, so with no
// snow and a dry night it renders as before).
//  - snow: every upward-facing bit (sills, lintels, door hoods, ledges, cornices, balcony rails, steps, cart tops,
//    barrel heads, sign boards, hats) catches a world-space layer: global `snow_cover` x a smoothstep on the
//    world normal's up component, broken up by noise, with a bright soft rim for thickness; `fresh_snow` makes it
//    brighter and wider, `crust` greys it. `catch_amount` scales it per material (cloth only dusts, tile sheds).
//    Surfaces at street level (floors, arcade paving) are left to the ground overlay.
//  - wet: `wetness` darkens the albedo and lowers roughness on all faces (more on upward ones), with streaks
//    running down the verticals (a vertically stretched noise) below the ledges.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, diffuse_burley, specular_schlick_ggx;

global uniform float snow_cover;
global uniform float wetness;
global uniform float fresh_snow;
global uniform float crust;

uniform vec4 albedo : source_color = vec4(1.0);
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform bool use_vertex_color = false;
uniform bool use_normal = false;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float normal_scale = 1.0;
uniform sampler2D rough_tex : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform vec4 rough_channel = vec4(0.0, 1.0, 0.0, 0.0);
uniform float roughness : hint_range(0.0, 1.0) = 1.0;
uniform sampler2D metal_tex : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform vec4 metal_channel = vec4(0.0, 0.0, 1.0, 0.0);
uniform float metallic : hint_range(0.0, 1.0) = 0.0;
uniform float specular : hint_range(0.0, 1.0) = 0.5;
uniform vec3 uv1_scale = vec3(1.0);
uniform vec3 uv1_offset = vec3(0.0);
uniform float catch_amount = 1.0;   // snow catch (cloth 0.35: a dusting; tile 0.6: roofs shed it)
uniform float wet_amount = 1.0;     // how much this surface darkens when wet (iron / glass-like less)

varying vec3 w_pos;
varying vec3 w_nrm;

float hash3(vec3 p) {
	p = fract(p * 0.3183099 + vec3(0.1, 0.17, 0.13));
	p *= 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float vnoise(vec3 x) {
	vec3 i = floor(x);
	vec3 f = fract(x);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(hash3(i), hash3(i + vec3(1, 0, 0)), f.x), mix(hash3(i + vec3(0, 1, 0)), hash3(i + vec3(1, 1, 0)), f.x), f.y),
			mix(mix(hash3(i + vec3(0, 0, 1)), hash3(i + vec3(1, 0, 1)), f.x), mix(hash3(i + vec3(0, 1, 1)), hash3(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

void vertex() {
	w_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	w_nrm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

void fragment() {
	vec2 uv = UV * uv1_scale.xy + uv1_offset.xy;
	vec4 base = texture(albedo_tex, uv) * albedo;
	if (use_vertex_color) {
		base *= COLOR;
	}
	float r = dot(texture(rough_tex, uv), rough_channel) * roughness;
	float m = dot(texture(metal_tex, uv), metal_channel) * metallic;
	vec3 col = base.rgb;
	float up = w_nrm.y;
	bool outdoors = w_pos.y > -50.0;

	// ---- snow on whatever faces up
	float snow = 0.0;
	float rim = 0.0;
	if (outdoors && snow_cover > 0.01 && up > 0.35) {
		float n = vnoise(w_pos * 1.7) * 0.65 + vnoise(w_pos * 6.3 + vec3(3.1)) * 0.35;
		float cover = snow_cover * catch_amount * (1.0 + fresh_snow * 0.3);
		float need = 1.0 - 0.5 * clamp(cover, 0.0, 1.2);            // cover 1: faces above ~60 degrees up
		float t = up - need + (n - 0.5) * 0.3 + cover * 0.08;
		snow = smoothstep(0.0, 0.1, t) * smoothstep(0.1, 0.7, w_pos.y) * clamp(cover * 1.5, 0.0, 1.0);
		rim = smoothstep(0.0, 0.05, t) * (1.0 - smoothstep(0.05, 0.14, t));
	}
	// ---- wet: everywhere, more on top faces, streaks down the verticals
	float wet = 0.0;
	if (outdoors && wetness > 0.01) {
		float streak = vnoise(vec3(w_pos.x * 4.0, w_pos.y * 0.35, w_pos.z * 4.0) + vec3(w_nrm.x, 0.0, w_nrm.z) * 3.0);
		float vertical = 1.0 - abs(up);
		wet = wetness * wet_amount * (0.45 + 0.35 * max(up, 0.0) + vertical * smoothstep(0.45, 0.75, streak) * 0.5);
		wet = clamp(wet, 0.0, 1.0) * (1.0 - snow);
	}
	col *= mix(1.0, 0.58, wet);
	r = mix(r, r * 0.3, wet);

	vec3 s_col = vec3(0.95, 0.97, 1.02);
	s_col = mix(s_col, vec3(0.62, 0.64, 0.68), crust * 0.7);
	s_col = mix(s_col, vec3(0.97, 0.98, 1.0), fresh_snow * 0.7);
	s_col *= mix(1.0, 0.72, wetness);                          // slushy when it rains on it
	s_col += vec3(0.1) * rim;                                 // the soft rounded edge of a cap
	col = mix(col, s_col, snow);
	ALBEDO = col;
	ROUGHNESS = mix(r, mix(0.85, 0.35, wetness), snow);
	METALLIC = m * (1.0 - snow);
	SPECULAR = mix(specular, 0.6, max(wet, snow * 0.5));
	if (use_normal) {
		NORMAL_MAP = texture(normal_tex, uv).rgb;
		NORMAL_MAP_DEPTH = normal_scale * (1.0 - snow * 0.8);
	}
}
