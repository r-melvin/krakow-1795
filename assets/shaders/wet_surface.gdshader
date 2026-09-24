// Overlay pass (next_pass) for the paved ground: snow and rain puddles on top of the base StandardMaterial3D,
// which keeps its own parallax, textures and tuning. Driven by the globals `ground_snow` (weather.gd: the snow
// cover, capped per preset) and `wetness`.
// The overlay runs the same parallax occlusion walk as the base material (its height map, scale and layer counts
// are copied in by assets.gd register_ground), so the snow sits *in* the relief:
//  - a fill level rises through the height range: the joints and hollows fill first, the setts stay stone;
//  - the stone tops get only a thin, broken cap of dust;
//  - low-frequency drifts lift the fill in lumps, and a fixed trampled mask along the walking lines of the square
//    packs the snow into grey slush with footprint pits;
//  - the snow surface gets its own normal from the filled height (rounded edges against the stones, contact shade).
// Rain fills the joints and hollows with dark, glossy water: the puddle mask comes from the height map's low areas
// and widens with the accumulated `puddles`; falling drops ring it (`rain`) and it skins over with ice in frost.
// Accumulation (weather.gd): `fresh_snow` raises and brightens the fill into soft powder; `crust` lays a grey
// granular sleet skin over snow and stone alike; `track_map` (weather_fx.gd) holds walkers' footprints stamped with
// the snowfall total at the time, so tracks fill in again while it snows (`snowfall_total`).
shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_back, diffuse_burley, specular_schlick_ggx;

global uniform float ground_snow;
global uniform float wetness;
global uniform float puddles;
global uniform float rain;
global uniform float frost;
global uniform float crust;
global uniform float fresh_snow;
global uniform float snowfall_total;
global uniform sampler2D track_map : filter_linear;
global uniform vec4 track_rect;

uniform bool has_height = false;
uniform sampler2D height_tex : filter_linear_mipmap, repeat_enable, hint_default_white;
uniform bool use_parallax = false;
uniform float heightmap_scale = 2.0;
uniform int heightmap_min_layers = 8;
uniform int heightmap_max_layers = 24;
uniform vec2 heightmap_flip = vec2(1.0);
uniform vec3 uv1_scale = vec3(1.0);
uniform vec3 uv1_offset = vec3(0.0);
uniform float fill_amount = 0.62;   // how far up the height range the joints fill at full cover
uniform vec3 snow_color : source_color = vec3(0.88, 0.9, 0.95);
uniform float texel_uv = 0.0012;    // finite-difference step for the snow normal (UV units)

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

float height_at(vec2 uv) {
	return has_height ? texture(height_tex, uv).r : 0.5;
}

float seg_dist(vec2 p, vec2 a, vec2 b) {
	vec2 pa = p - a;
	vec2 ba = b - a;
	float t = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
	return length(pa - ba * t);
}

// Worn lines across the Rynek (world xz): the patrol loops, the Cloth Hall passage, the way to St Mary's.
float trampled(vec2 p) {
	float d = 1e3;
	d = min(d, seg_dist(p, vec2(-24.0, -20.0), vec2(22.0, -20.0)));
	d = min(d, seg_dist(p, vec2(-12.0, 18.0), vec2(22.0, 18.0)));
	d = min(d, seg_dist(p, vec2(0.0, -30.0), vec2(0.0, 30.0)));
	d = min(d, seg_dist(p, vec2(-30.0, 0.0), vec2(-10.0, 0.0)));
	d = min(d, seg_dist(p, vec2(10.0, 0.0), vec2(30.0, -6.0)));
	d = min(d, seg_dist(p, vec2(24.0, -18.0), vec2(30.0, -8.0)));
	d = min(d, seg_dist(p, vec2(-27.0, -27.0), vec2(-12.0, -14.0)));
	d = min(d, seg_dist(p, vec2(24.0, -14.0), vec2(24.0, 6.0)));
	float wobble = (vnoise(p * 0.35) - 0.5) * 1.2;
	return 1.0 - smoothstep(0.5, 1.9, d + wobble);
}

// Footprint pits: staggered ovals in 0.7 m cells, only inside the trampled band.
float footprints(vec2 p) {
	vec2 cell = floor(p / 0.7);
	vec2 f = fract(p / 0.7) - 0.5;
	float h = hash2(cell);
	vec2 o = vec2(hash2(cell + 3.1), hash2(cell + 7.7)) - 0.5;
	vec2 q = (f - o * 0.4);
	q = mat2(vec2(cos(h * 6.28), sin(h * 6.28)), vec2(-sin(h * 6.28), cos(h * 6.28))) * q;
	float e = length(q * vec2(1.0, 2.2));
	return (1.0 - smoothstep(0.13, 0.19, e)) * step(0.35, h);
}

// Rain rings on standing water: one drop per 0.3 m cell, each on its own cycle; returns a tangent-space tilt.
vec2 ripples(vec2 p, float t) {
	vec2 cell = floor(p / 0.3);
	vec2 acc = vec2(0.0);
	for (int j = -1; j <= 1; j++) {
		for (int i = -1; i <= 1; i++) {
			vec2 c = cell + vec2(float(i), float(j));
			float h = hash2(c);
			vec2 centre = (c + vec2(hash2(c + 1.3), hash2(c + 5.1))) * 0.3;
			float ph = fract(t * 0.9 + h);
			vec2 d = p - centre;
			float r = length(d);
			float ring = sin((r - ph * 0.35) * 60.0) * (1.0 - ph) * (1.0 - smoothstep(0.0, 0.05, abs(r - ph * 0.35)));
			acc += normalize(d + 1e-4) * ring;
		}
	}
	return acc;
}

void vertex() {
	w_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	VERTEX += NORMAL * 0.002;
}

void fragment() {
	if (w_pos.y < -50.0) {
		discard;
	}
	vec2 uv = UV * uv1_scale.xy + uv1_offset.xy;
	// the same parallax occlusion walk as BaseMaterial3D's deep parallax, so the overlay lands on the same texel
	if (use_parallax && has_height) {
		vec3 view_dir = normalize(normalize(-VERTEX) * mat3(TANGENT * heightmap_flip.x, -BINORMAL * heightmap_flip.y, NORMAL));
		float num_layers = mix(float(heightmap_max_layers), float(heightmap_min_layers), abs(view_dir.z));
		float layer_depth = 1.0 / num_layers;
		vec2 P = view_dir.xy * heightmap_scale * 0.01;
		vec2 delta = P / num_layers;
		vec2 ofs = uv;
		float depth = 1.0 - height_at(ofs);
		float current_depth = 0.0;
		for (int i = 0; i < 32; i++) {
			if (current_depth >= depth) {
				break;
			}
			ofs -= delta;
			depth = 1.0 - height_at(ofs);
			current_depth += layer_depth;
		}
		vec2 prev_ofs = ofs + delta;
		float after_depth = depth - current_depth;
		float before_depth = (1.0 - height_at(prev_ofs)) - current_depth + layer_depth;
		float weight = after_depth / (after_depth - before_depth);
		uv = mix(ofs, prev_ofs, weight);
	}
	float cover = clamp(ground_snow, 0.0, 1.0);
	float h = height_at(uv);
	vec2 wp = w_pos.xz;
	float drift = fbm(wp * 0.22);                    // lumps a few metres across
	float fine = fbm(wp * 3.1 + vec2(4.0));
	float tr = trampled(wp) * smoothstep(0.05, 0.35, cover) * (1.0 - fresh_snow * 0.7);   // fresh powder covers the old lines
	// walkers' tracks: stamped with the snowfall total, they fill in with each new snow-hour
	vec2 tuv = (wp - track_rect.xy) / track_rect.zw;
	float stamp = (tuv.x > 0.0 && tuv.y > 0.0 && tuv.x < 1.0 && tuv.y < 1.0) ? texture(track_map, tuv).r : 0.0;
	float track = stamp > 0.0 ? clamp(1.0 - (snowfall_total - (stamp - 1.0)) * 3.0, 0.0, 1.0) * clamp(stamp * 4.0, 0.0, 1.0) : 0.0;
	track *= smoothstep(0.1, 0.4, cover);
	float fp = footprints(wp) * max(tr, track);
	// fill level: rises with cover and fresh powder, lifted by drifts, lowered where feet pack it down
	float level = cover * fill_amount - 0.08 + (drift - 0.5) * 0.34 * cover + fresh_snow * 0.15 * cover
			- tr * 0.22 * cover - track * 0.38 * cover - fp * 0.5;
	float fill = smoothstep(h - 0.035, h + 0.035, level);
	// thin broken caps on the stone tops (wind-scoured, patchy; thicker in fresh powder), none on the trampled line
	float cap = smoothstep(0.45, 0.8, fine + cover * 0.4 - 0.25 + fresh_snow * 0.25) * smoothstep(0.3, 0.9, cover) * (1.0 - tr);
	cap *= mix(0.75, 0.95, fresh_snow) * smoothstep(level, level + 0.35, h) * (1.0 - fp);
	float snow = clamp(max(fill, cap) * smoothstep(0.02, 0.1, cover), 0.0, 1.0);

	// the snow's own surface: stones where uncovered, the flat fill level where covered; its gradient gives a normal
	vec2 e = vec2(texel_uv, 0.0);
	float sx0 = max(height_at(uv - e.xy), level);
	float sx1 = max(height_at(uv + e.xy), level);
	float sy0 = max(height_at(uv - e.yx), level);
	float sy1 = max(height_at(uv + e.yx), level);
	vec3 nm = normalize(vec3((sx0 - sx1) * 6.0, (sy0 - sy1) * 6.0, 1.0));
	// contact shade where the snow meets the stone (the fill is shallow against a sett's flank)
	float contact = smoothstep(0.0, 0.12, level - h);

	// standing water: the low joints and hollows first, widening with the accumulated puddles
	float pw = max(puddles, wetness * 0.5);
	float puddle = smoothstep(pw * 0.62 + 0.02, pw * 0.62 - 0.1, h + (drift - 0.5) * 0.35) * smoothstep(0.03, 0.2, pw);
	float film = wetness * 0.3;
	float water = clamp(max(puddle * 0.85, film), 0.0, 1.0) * (1.0 - snow);
	// sleet crust: a grey granular skin over snow and stone tops alike
	float grain = hash2(floor(wp * 90.0));
	float cr = crust * (0.55 + grain * 0.45) * (1.0 - water) * smoothstep(0.35, 0.6, h + snow);
	float a = clamp(snow * mix(0.97, 0.8, tr) + water + cr * 0.8 * (1.0 - snow), 0.0, 1.0);
	if (a < 0.004) {
		discard;
	}
	float k = snow / max(snow + water + cr * (1.0 - snow), 0.001);
	float kc = cr * (1.0 - snow) / max(snow + water + cr * (1.0 - snow), 0.001);
	vec3 packed_col = vec3(0.42, 0.41, 0.40);          // trodden, dirty slush
	vec3 s_col = mix(snow_color, packed_col, clamp(tr * 0.75 + fp * 0.5 + track * 0.25, 0.0, 1.0));
	s_col = mix(s_col, vec3(0.96, 0.97, 1.0), fresh_snow * (1.0 - tr) * 0.6);
	s_col *= mix(0.72, 1.0, contact) * mix(0.9, 1.04, fine);
	s_col *= mix(1.0, 0.6, max(track, fp * 0.7) * (1.0 - tr * 0.5));   // prints read as blue-grey hollows
	s_col = mix(s_col, s_col * vec3(0.72, 0.73, 0.76), crust * (0.5 + grain * 0.5));
	s_col *= mix(1.0, 0.62, wetness);
	vec3 w_col = mix(vec3(0.015, 0.016, 0.018), vec3(0.55, 0.6, 0.66), frost * 0.5);   // frozen puddles skin over
	vec3 c_col = vec3(0.6, 0.61, 0.64) * (0.8 + grain * 0.35);
	ALBEDO = w_col * (1.0 - k - kc) + s_col * k + c_col * kc;
	float wr = mix(0.03, 0.12, frost);
	ROUGHNESS = wr * (1.0 - k - kc) + mix(mix(mix(0.82, 0.5, tr), 0.3, wetness), 0.95, fresh_snow) * k + 0.6 * kc;
	SPECULAR = 0.5;
	vec3 n_out = mix(vec3(0.5, 0.5, 1.0), nm * 0.5 + 0.5, k);
	if (rain > 0.01 && frost < 0.5) {
		vec2 rp = ripples(wp, TIME) * rain * (1.0 - k) * puddle;
		n_out = normalize(n_out * 2.0 - 1.0 + vec3(rp * 0.6, 0.0)) * 0.5 + 0.5;
	}
	NORMAL_MAP = n_out;
	ALPHA = a;
}
