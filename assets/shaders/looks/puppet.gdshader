shader_type spatial;
render_mode unshaded, cull_disabled, depth_test_disabled, depth_draw_never;
#include "common.gdshaderinc"
// Stop-motion puppetry (camera side only): miniature tilt-shift depth of field, felted softness on surfaces,
// warm stage-light saturation, soft vignette. The held-frame animation and puppet proportions would come from
// the character pipeline, not this pass.
uniform float focus_m = 7.0;
uniform float blur_px = 3.0;

void vertex() { POSITION = vec4(VERTEX.xy * 2.0, 1.0, 1.0); }

void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 px = 1.0 / VIEWPORT_SIZE;
	float d = lin_depth(uv, INV_PROJECTION_MATRIX);
	float coc = clamp(abs(d - focus_m) / focus_m, 0.0, 1.0);
	coc = max(coc, abs(uv.y - 0.52) * 1.6 - 0.25);   // tilt-shift band
	coc = clamp(coc, 0.0, 1.0);
	vec3 col = vec3(0.0);
	float wsum = 0.0;
	for (int i = -2; i <= 2; i++) for (int j = -2; j <= 2; j++) {
		vec2 o = vec2(float(i), float(j)) * px * blur_px * coc;
		float w = 1.0 / (1.0 + float(i * i + j * j));
		col += texture(screen_tex, uv + o).rgb * w; wsum += w;
	}
	col /= wsum;
	float l = luma(col);
	col = mix(vec3(l), col, 1.25);
	col *= vec3(1.05, 0.98, 0.92);
	float vig = smoothstep(1.3, 0.4, length(uv - 0.5) * 1.4);
	col *= mix(0.6, 1.0, vig);
	ALBEDO = col;
}
