shader_type spatial;
render_mode unshaded, cull_disabled, depth_test_disabled, depth_draw_never;
#include "common.gdshaderinc"
// Realism plus grime and grain: desaturated, contrasty, film grain, soft bloom lift in the lanterns, heavy vignette.
uniform float grain = 0.09;

void vertex() { POSITION = vec4(VERTEX.xy * 2.0, 1.0, 1.0); }

void fragment() {
	vec2 uv = SCREEN_UV;
	vec3 src = texture(screen_tex, uv).rgb;
	float l = luma(src);
	vec3 col = mix(vec3(l), src, 0.7);
	col = (col - 0.5) * 1.18 + 0.5;
	col = mix(col, col * vec3(0.96, 0.98, 1.06), 0.5);          // cold cast
	float g = hash21(floor(uv * VIEWPORT_SIZE) + fract(TIME) * 13.0) - 0.5;
	col += g * grain * (1.0 - l * 0.6);
	float vig = smoothstep(1.2, 0.35, length(uv - 0.5) * 1.4);
	col *= mix(0.55, 1.0, vig);
	ALBEDO = clamp(col, 0.0, 1.0);
}
