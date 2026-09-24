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

uniform float smooth_px = 3.5;
uniform float bands = 7.0;
uniform float ink = 0.7;
uniform float grain = 0.07;
void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 px = 1.0 / vec2(textureSize(screen_tex, 0));
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
	float l = luma(col);
	col = mix(vec3(l), col, 0.72);
	col = mix(col, col * vec3(1.08, 0.97, 0.88), 0.6);
	float lb = floor(l * bands) / bands;
	col *= mix(1.0, (lb + 0.5 / bands) / max(l, 0.02), 0.45);
	float e = edges_c(uv, px * 1.5, 2.2);
	col *= 1.0 - e * ink;
	col += (hash21(floor(uv / px * 0.5)) - 0.5) * grain;
	float vig = smoothstep(1.25, 0.45, length(uv - 0.5) * 1.4);
	col *= mix(0.7, 1.0, vig);
	COLOR = vec4(col, 1.0);
}
