shader_type spatial;
render_mode unshaded, cull_disabled, depth_test_disabled, depth_draw_never;
#include "common.gdshaderinc"
// Cel-shaded realism: luminance quantised to three bands, boosted saturation, dark outlines.
uniform float ink = 0.85;

void vertex() { POSITION = vec4(VERTEX.xy * 2.0, 1.0, 1.0); }

void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 px = 1.0 / VIEWPORT_SIZE;
	vec3 src = texture(screen_tex, uv).rgb;
	float l = luma(src);
	float band = l < 0.12 ? 0.07 : (l < 0.35 ? 0.28 : (l < 0.7 ? 0.6 : 0.95));
	vec3 col = src * (band / max(l, 0.02));
	float g = luma(col);
	col = mix(vec3(g), col, 1.35);
	float e = edges(uv, px * 1.3, INV_PROJECTION_MATRIX, 50.0, 0.5);
	col = mix(col, vec3(0.03, 0.03, 0.04), e * ink);
	ALBEDO = clamp(col, 0.0, 1.0);
}
