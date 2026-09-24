shader_type canvas_item;

uniform sampler2D screen_tex : hint_screen_texture, filter_linear, repeat_disable;
float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }
float hash21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float edges_c(vec2 uv, vec2 px, float scale) {
	float tl = luma(texture(screen_tex, uv + vec2(-px.x, -px.y)).rgb);
	float t  = luma(texture(screen_tex, uv + vec2(0.0, -px.y)).rgb);
	float tr = luma(texture(screen_tex, uv + vec2(px.x, -px.y)).rgb);
	float l  = luma(texture(screen_tex, uv + vec2(-px.x, 0.0)).rgb);
	float r  = luma(texture(screen_tex, uv + vec2(px.x, 0.0)).rgb);
	float bl = luma(texture(screen_tex, uv + vec2(-px.x, px.y)).rgb);
	float b  = luma(texture(screen_tex, uv + vec2(0.0, px.y)).rgb);
	float br = luma(texture(screen_tex, uv + vec2(px.x, px.y)).rgb);
	float gx = -tl - 2.0 * l - bl + tr + 2.0 * r + br;
	float gy = -tl - 2.0 * t - tr + bl + 2.0 * b + br;
	return clamp(sqrt(gx * gx + gy * gy) * scale, 0.0, 1.0);
}

uniform float ink = 0.9;
void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 px = 1.0 / vec2(textureSize(screen_tex, 0));
	vec3 src = texture(screen_tex, uv).rgb;
	float l = luma(src);
	float band = l < 0.12 ? 0.07 : (l < 0.35 ? 0.28 : (l < 0.7 ? 0.6 : 0.95));
	vec3 col = src * (band / max(l, 0.02));
	float g = luma(col);
	col = mix(vec3(g), col, 1.35);
	float e = edges_c(uv, px * 1.3, 2.6);
	col = mix(col, vec3(0.03, 0.03, 0.04), e * ink);
	COLOR = vec4(clamp(col, 0.0, 1.0), 1.0);
}
