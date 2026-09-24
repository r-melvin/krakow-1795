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

uniform float grain = 0.09;
void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 px = 1.0 / vec2(textureSize(screen_tex, 0));
	vec3 src = texture(screen_tex, uv).rgb;
	float l = luma(src);
	vec3 col = mix(vec3(l), src, 0.7);
	col = (col - 0.5) * 1.18 + 0.5;
	col = mix(col, col * vec3(0.96, 0.98, 1.06), 0.5);
	float g = hash21(floor(uv / px) + fract(TIME) * 13.0) - 0.5;
	col += g * grain * (1.0 - l * 0.6);
	float vig = smoothstep(1.2, 0.35, length(uv - 0.5) * 1.4);
	col *= mix(0.55, 1.0, vig);
	COLOR = vec4(clamp(col, 0.0, 1.0), 1.0);
}
