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

uniform float ink = 0.95;
uniform float hatch_scale = 3.0;
void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 px = 1.0 / vec2(textureSize(screen_tex, 0));
	vec3 src = texture(screen_tex, uv).rgb;
	float l = luma(src);
	vec3 paper = vec3(0.86, 0.80, 0.66);
	vec3 sepia = vec3(0.36, 0.26, 0.17);
	vec3 night = vec3(0.10, 0.12, 0.20);
	vec3 col = mix(night, sepia, smoothstep(0.05, 0.35, l));
	col = mix(col, paper, smoothstep(0.35, 0.85, l));
	float warm = clamp((src.r - src.b) * 2.0, 0.0, 1.0) * smoothstep(0.3, 0.7, l);
	col = mix(col, vec3(0.95, 0.72, 0.38), warm * 0.6);
	vec2 sp = uv / px / hatch_scale;
	float h1 = step(0.5, fract((sp.x + sp.y) * 0.25));
	float h2 = step(0.5, fract((sp.x - sp.y) * 0.25));
	float dark = 1.0 - smoothstep(0.08, 0.45, l);
	col = mix(col, col * 0.45, dark * h1 * 0.7);
	col = mix(col, col * 0.45, smoothstep(0.6, 1.0, dark) * h2 * 0.7);
	float e = edges_c(uv, px * 1.2, 3.0);
	col = mix(col, vec3(0.06, 0.05, 0.05), e * ink);
	col += (hash21(floor(uv / px * 0.7)) - 0.5) * 0.05;
	COLOR = vec4(col, 1.0);
}
