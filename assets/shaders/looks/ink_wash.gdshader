shader_type spatial;
render_mode unshaded, cull_disabled, depth_test_disabled, depth_draw_never;
#include "common.gdshaderinc"
// Ink and wash: strong contours from depth and normals, cross-hatching in the shadows, a restricted palette
// (paper, sepia, indigo night, lantern amber), snow as bare paper.
uniform float ink = 0.9;
uniform float hatch_scale = 3.0;

void vertex() { POSITION = vec4(VERTEX.xy * 2.0, 1.0, 1.0); }

void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 px = 1.0 / VIEWPORT_SIZE;
	vec3 src = texture(screen_tex, uv).rgb;
	float l = luma(src);
	// wash: three tones
	vec3 paper = vec3(0.86, 0.80, 0.66);
	vec3 sepia = vec3(0.36, 0.26, 0.17);
	vec3 night = vec3(0.10, 0.12, 0.20);
	vec3 col = mix(night, sepia, smoothstep(0.05, 0.35, l));
	col = mix(col, paper, smoothstep(0.35, 0.85, l));
	// keep the lantern warmth
	float warm = clamp((src.r - src.b) * 2.0, 0.0, 1.0) * smoothstep(0.3, 0.7, l);
	col = mix(col, vec3(0.95, 0.72, 0.38), warm * 0.6);
	// hatching in the darks
	vec2 sp = uv * VIEWPORT_SIZE / hatch_scale;
	float h1 = step(0.5, fract((sp.x + sp.y) * 0.25));
	float h2 = step(0.5, fract((sp.x - sp.y) * 0.25));
	float dark = 1.0 - smoothstep(0.08, 0.45, l);
	col = mix(col, col * 0.45, dark * h1 * 0.7);
	col = mix(col, col * 0.45, smoothstep(0.6, 1.0, dark) * h2 * 0.7);
	// contours
	float e = edges(uv, px * 1.2, INV_PROJECTION_MATRIX, 60.0, 0.6);
	col = mix(col, vec3(0.06, 0.05, 0.05), e * ink);
	// paper grain
	col += (hash21(floor(uv * VIEWPORT_SIZE * 0.7)) - 0.5) * 0.05;
	ALBEDO = col;
}
