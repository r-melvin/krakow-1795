shader_type spatial;
render_mode unshaded, cull_disabled, depth_test_disabled, depth_draw_never;
#include "common.gdshaderinc"
// Painterly period print: soft edge-preserving smoothing, gentle tonal posterisation, warm desaturated palette,
// thin contour only on silhouettes, paper grain and a vignette. Like a hand-tinted aquatint.
uniform float smooth_px = 2.5;
uniform float bands = 9.0;
uniform float ink = 0.55;
uniform float grain = 0.06;

void vertex() { POSITION = vec4(VERTEX.xy * 2.0, 1.0, 1.0); }

void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 px = 1.0 / VIEWPORT_SIZE;
	// Kuwahara-lite: average of the least-variance quadrant of a small window
	vec3 best = vec3(0.0); float bestv = 1e9;
	for (int q = 0; q < 4; q++) {
		vec2 dir = vec2(q < 2 ? 1.0 : -1.0, (q == 0 || q == 2) ? 1.0 : -1.0);
		vec3 m = vec3(0.0); vec3 s = vec3(0.0);
		for (int i = 0; i <= 2; i++) for (int j = 0; j <= 2; j++) {
			vec3 c = texture(screen_tex, uv + dir * vec2(float(i), float(j)) * px * smooth_px).rgb;
			m += c; s += c * c;
		}
		m /= 9.0; s = s / 9.0 - m * m;
		float v = s.r + s.g + s.b;
		if (v < bestv) { bestv = v; best = m; }
	}
	vec3 col = best;
	// palette: warm shadows, cool highlights kept, slight desaturation
	float l = luma(col);
	col = mix(vec3(l), col, 0.78);
	col = mix(col, col * vec3(1.06, 0.98, 0.90), 0.5);
	// tonal bands with soft steps
	float lb = floor(l * bands) / bands;
	col *= mix(1.0, (lb + 0.5 / bands) / max(l, 0.02), 0.35);
	// silhouette contour
	float e = edges(uv, px * 1.5, INV_PROJECTION_MATRIX, 40.0, 0.35);
	col *= 1.0 - e * ink;
	// paper grain and vignette
	float g = hash21(floor(uv * VIEWPORT_SIZE * 0.5)) - 0.5;
	col += g * grain;
	float vig = smoothstep(1.25, 0.45, length(uv - 0.5) * 1.4);
	col *= mix(0.72, 1.0, vig);
	ALBEDO = col;
}
