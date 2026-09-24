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

uniform float blur_px = 3.0;
void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 px = 1.0 / vec2(textureSize(screen_tex, 0));
	float coc = clamp(abs(uv.y - 0.52) * 2.2 - 0.25, 0.0, 1.0);   // tilt-shift band
	vec3 col = vec3(0.0); float wsum = 0.0;
	for (int i = -2; i <= 2; i++) for (int j = -2; j <= 2; j++) {
		vec2 o = vec2(float(i), float(j)) * px * blur_px * coc;
		float w = 1.0 / (1.0 + float(i * i + j * j));
		col += texture(screen_tex, uv + o).rgb * w; wsum += w;
	}
	col /= wsum;
	float l = luma(col);
	col = mix(vec3(l), col, 1.3);
	col *= vec3(1.06, 0.98, 0.9);
	float vig = smoothstep(1.3, 0.4, length(uv - 0.5) * 1.4);
	col *= mix(0.55, 1.0, vig);
	COLOR = vec4(col, 1.0);
}
