// Shared helpers for the look previews: a full-screen quad in front of the camera reading the screen, depth and
// normal-roughness buffers. Used only when the game is started with `--look=<name>`.
uniform sampler2D screen_tex : hint_screen_texture, filter_linear, repeat_disable;
uniform sampler2D depth_tex : hint_depth_texture, filter_nearest, repeat_disable;
uniform sampler2D normal_tex : hint_normal_roughness_texture, filter_nearest, repeat_disable;

float lin_depth(vec2 uv, mat4 inv_proj) {
	float d = texture(depth_tex, uv).r;
	vec3 ndc = vec3(uv * 2.0 - 1.0, d);
	vec4 v = inv_proj * vec4(ndc, 1.0);
	return -v.z / v.w;
}

// Edge strength from depth and normal discontinuities (silhouettes and creases), 0..1.
float edges(vec2 uv, vec2 px, mat4 inv_proj, float depth_scale, float normal_scale) {
	float d0 = lin_depth(uv, inv_proj);
	vec3 n0 = texture(normal_tex, uv).rgb * 2.0 - 1.0;
	float e = 0.0;
	vec2 offs[4] = vec2[](vec2(px.x, 0.0), vec2(-px.x, 0.0), vec2(0.0, px.y), vec2(0.0, -px.y));
	for (int i = 0; i < 4; i++) {
		float d1 = lin_depth(uv + offs[i], inv_proj);
		vec3 n1 = texture(normal_tex, uv + offs[i]).rgb * 2.0 - 1.0;
		e += clamp(abs(d1 - d0) / max(d0, 0.5) * depth_scale, 0.0, 1.0);
		e += clamp((1.0 - dot(n0, n1)) * normal_scale, 0.0, 1.0);
	}
	return clamp(e, 0.0, 1.0);
}

float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }

float hash21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
