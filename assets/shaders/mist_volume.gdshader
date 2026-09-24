// Local mist / smoke for FogVolume boxes (scripts/city/weather_fx.gd): a drifting 3D noise density, soft at the
// box edges and thinning with height, scaled by the global `mist` (weather.gd: the preset's ground mist, thicker
// toward dawn and in the fog preset). Smoke volumes set mist_gain 0 and keep their own density.
shader_type fog;

global uniform vec2 wind;
global uniform float mist;

uniform sampler3D noise_tex : repeat_enable, filter_linear;
uniform float density = 0.1;
uniform float base = 0.0;           // density share that ignores the mist global (smoke)
uniform float mist_gain = 1.0;
uniform vec3 albedo : source_color = vec3(0.8, 0.82, 0.86);
uniform vec3 emission : source_color = vec3(0.0);
uniform float scale = 0.08;          // noise cycles per metre
uniform float height_power = 1.6;    // > 1: pooled low, fading upward
uniform float drift = 0.6;           // share of the wind speed the pattern drifts at
uniform float glow = 0.05;           // a little self-light: mist reads against the dark even away from lamps

void fog() {
	vec3 p = WORLD_POSITION * scale;
	p -= vec3(wind.x, 0.0, wind.y) * TIME * drift * scale;
	p.y += TIME * 0.01;
	float n = texture(noise_tex, p).r * 0.65 + texture(noise_tex, p * 2.3 + vec3(0.37)).r * 0.35;
	n = smoothstep(0.3, 0.75, n);
	float ex = min(UVW.x, 1.0 - UVW.x);
	float ez = min(UVW.z, 1.0 - UVW.z);
	float edge = smoothstep(0.0, 0.22, min(ex, ez));
	float vert = pow(clamp(1.0 - UVW.y, 0.0, 1.0), height_power);
	float amount = base + mist * mist_gain;
	DENSITY = density * amount * n * edge * vert;
	ALBEDO = albedo;
	EMISSION = emission + albedo * glow * clamp(amount, 0.0, 1.0);
}
