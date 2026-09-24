// Baked roof / sill / coping snow that melts with the global `snow_cover` (scripts/city/weather.gd).
// Replaces the glTF "snow" StandardMaterial3D (scripts/core/assets.gd copies its textures in), so at
// snow_cover = 1 it renders the same as before. As cover drops, a world-space noise field decides which
// parts go first (lower-facing and thin bits a little earlier); the blanket sinks into the tiles near the
// melt line and the rim turns grey, dark and glossy (melt water) before the fragment is cut away with a
// crumbly, grainy edge instead of a clean contour.
// Accumulation (weather.gd): `fresh_snow` lays a bright, soft, slightly thicker powder cap over it; `crust` greys it
// with a sleet grain; icicles (is_ice) follow the global `icicles` instead of the cover, the tips going first.
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_burley, specular_schlick_ggx;

global uniform float snow_cover;
global uniform float wetness;
global uniform float fresh_snow;
global uniform float crust;
global uniform float icicles;
uniform bool is_ice = false;

uniform vec4 albedo : source_color = vec4(1.0);
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform bool use_normal = false;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform float normal_scale = 1.0;
uniform sampler2D rough_tex : filter_linear_mipmap_anisotropic, repeat_enable, hint_default_white;
uniform vec4 rough_channel = vec4(0.0, 1.0, 0.0, 0.0);
uniform float roughness : hint_range(0.0, 1.0) = 1.0;
uniform float specular : hint_range(0.0, 1.0) = 0.5;
uniform vec3 uv1_scale = vec3(1.0);
uniform vec3 uv1_offset = vec3(0.0);
uniform float melt_bias = 0.0;      // > 0 melts this material earlier (icicles, dust on cloth)
uniform float sink = 0.06;          // metres the blanket settles by at the melt line

varying vec3 w_pos;
varying float w_up;

float hash3(vec3 p) {
	p = fract(p * 0.3183099 + vec3(0.1, 0.17, 0.13));
	p *= 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float vnoise(vec3 x) {
	vec3 i = floor(x);
	vec3 f = fract(x);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(hash3(i + vec3(0, 0, 0)), hash3(i + vec3(1, 0, 0)), f.x),
				mix(hash3(i + vec3(0, 1, 0)), hash3(i + vec3(1, 1, 0)), f.x), f.y),
			mix(mix(hash3(i + vec3(0, 0, 1)), hash3(i + vec3(1, 0, 1)), f.x),
				mix(hash3(i + vec3(0, 1, 1)), hash3(i + vec3(1, 1, 1)), f.x), f.y), f.z);
}

float fbm(vec3 p) {
	float a = 0.5;
	float s = 0.0;
	for (int i = 0; i < 4; i++) {
		s += a * vnoise(p);
		p = p * 2.03 + vec3(1.7, 9.2, 3.1);
		a *= 0.5;
	}
	return s / 0.9375;
}

// 0 = melts last, 1 = melts first
float melt_order(vec3 p, float up) {
	float broad = fbm(p * vec3(0.35, 0.6, 0.35));
	float detail = fbm(p * 2.4 + vec3(5.0));
	float n = broad * 0.72 + detail * 0.28;
	n = (n - 0.5) * 1.35 + 0.5;
	return clamp(n + (1.0 - clamp(up, 0.0, 1.0)) * 0.12 + melt_bias, 0.0, 1.0);
}

float threshold() {
	float c = is_ice ? icicles : snow_cover;
	// full cover renders the baked look untouched (the melt terms below never reach it)
	return c >= 0.999 ? 4.0 : c * 1.3 - 0.15;
}

void vertex() {
	w_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec3 wn = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
	w_up = wn.y;
	if (!is_ice && wn.y > 0.3) {
		// fresh powder sits a little proud of the old blanket
		VERTEX += inverse(mat3(MODEL_MATRIX)) * vec3(0.0, fresh_snow * 0.025 * snow_cover, 0.0);
	}
	float edge = threshold() - melt_order(w_pos, w_up);
	float thin = clamp(edge / 0.4, 0.0, 1.0);
	if (thin < 1.0) {
		vec3 down = inverse(mat3(MODEL_MATRIX)) * vec3(0.0, -sink * (1.0 - thin), 0.0);
		VERTEX += down;
	}
}

void fragment() {
	vec2 uv = UV * uv1_scale.xy + uv1_offset.xy;
	float edge = threshold() - melt_order(w_pos, w_up);
	// near the melt line the blanket goes rotten: fine noise eats holes into it and a grain of crystals
	// crumbles the contour, so it reads as thawing snow rather than a cut-out shape
	float near_line = 1.0 - smoothstep(0.0, 0.3, edge);
	float holes = fbm(w_pos * 7.0 + vec3(11.0)) - 0.5;
	float grain = hash3(floor(w_pos * 40.0)) - 0.5;
	edge += (holes * 0.22 + grain * 0.05) * near_line;
	if (edge < 0.0) {
		discard;
	}
	vec4 base = texture(albedo_tex, uv) * albedo;
	float r = dot(texture(rough_tex, uv), rough_channel) * roughness;
	// slush: a wide grey, glossy band that darkens toward the line (melt water soaking the rim)
	float rim = 1.0 - smoothstep(0.0, 0.32, edge);
	rim = rim * rim * (3.0 - 2.0 * rim);
	float slush = clamp(max(rim, wetness * 0.4 + (1.0 - snow_cover) * 0.18), 0.0, 1.0);
	vec3 slush_col = base.rgb * mix(vec3(0.62, 0.65, 0.70), vec3(0.34, 0.36, 0.40), rim);
	vec3 col = mix(base.rgb, slush_col, slush);
	float rr = mix(r, 0.12, slush);
	if (!is_ice) {
		// sleet crust: a grey, granular skin; fresh powder: bright, soft and matte over everything
		float cr = crust * (0.75 + grain * 0.5) * (1.0 - fresh_snow);
		col = mix(col, base.rgb * vec3(0.66, 0.67, 0.70), clamp(cr, 0.0, 1.0));
		rr = mix(rr, 0.55, cr);
		float fr = fresh_snow * smoothstep(0.2, 0.6, w_up) * (1.0 - rim);
		col = mix(col, vec3(0.97, 0.98, 1.0), fr * 0.8);
		rr = mix(rr, 0.95, fr);
		slush *= 1.0 - fr * 0.7;
	}
	ALBEDO = col;
	ROUGHNESS = rr;
	SPECULAR = mix(specular, 0.7, slush);
	if (use_normal) {
		NORMAL_MAP = texture(normal_tex, uv).rgb;
		NORMAL_MAP_DEPTH = normal_scale * (1.0 - slush * 0.6) * (1.0 - fresh_snow * 0.5);
	}
}
