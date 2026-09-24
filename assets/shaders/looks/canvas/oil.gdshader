shader_type canvas_item;
// "Oil" look: cel / painterly / ink-wash hybrid. Muted oil-painting tones, brush-smoothed surfaces (generalised
// Kuwahara in two radii), a soft luminance banding for the cel read, thin broken ink at strong edges, and a canvas
// weave. Preview only: --look=oil (scripts/core/look_preview.gd).

uniform sampler2D screen_tex : hint_screen_texture, filter_linear, repeat_disable;
uniform float brush_px = 4.0;        // coarse brush radius (px)
uniform float detail_px = 1.6;       // fine brush radius kept where the image is busy (faces, hands)
uniform float bands = 5.0;           // cel bands on luminance
uniform float band_mix = 0.32;       // how hard the banding reads (0 = painterly only)
uniform float ink = 0.55;            // edge darkening
uniform float ink_width = 1.2;       // sobel step in px
uniform float saturation = 0.62;     // muted tones
uniform float lift = 0.035;          // lifted blacks (oil ground showing through)
uniform float weave = 0.045;         // canvas texture
uniform float grain = 0.03;

float luma(vec3 c) { return dot(c, vec3(0.299, 0.587, 0.114)); }
float hash21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

vec3 kuwahara(vec2 uv, vec2 px, float radius) {
	vec3 best = vec3(0.0); float bestv = 1e9;
	for (int q = 0; q < 4; q++) {
		vec2 dir = vec2(q < 2 ? 1.0 : -1.0, (q == 0 || q == 2) ? 1.0 : -1.0);
		vec3 m = vec3(0.0); vec3 s = vec3(0.0);
		for (int i = 0; i <= 2; i++) for (int j = 0; j <= 2; j++) {
			vec3 c = texture(screen_tex, uv + dir * vec2(float(i), float(j)) * px * radius * 0.5).rgb;
			m += c; s += c * c;
		}
		m /= 9.0; s = s / 9.0 - m * m;
		float v = s.r + s.g + s.b;
		if (v < bestv) { bestv = v; best = m; }
	}
	return best;
}

float sobel(vec2 uv, vec2 px) {
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
	return sqrt(gx * gx + gy * gy);
}

void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 px = 1.0 / vec2(textureSize(screen_tex, 0));
	// Brush: coarse strokes on flat areas, finer strokes where there is local detail (keeps faces readable).
	vec3 coarse = kuwahara(uv, px, brush_px);
	vec3 fine = kuwahara(uv, px, detail_px);
	float busy = clamp(sobel(uv, px * 2.0) * 1.6, 0.0, 1.0);
	vec3 col = mix(coarse, fine, busy);
	// Muted oil palette: desaturate, warm the lights and cool the shadows a touch, lift the blacks.
	float l = luma(col);
	col = mix(vec3(l), col, saturation);
	vec3 warm = vec3(1.06, 0.98, 0.90);
	vec3 cool = vec3(0.92, 0.96, 1.06);
	col *= mix(cool, warm, smoothstep(0.15, 0.7, l));
	col = col * (1.0 - lift) + vec3(lift * 1.1, lift * 1.0, lift * 0.9);
	// Soft cel: quantise luminance in a few bands, but only partially, so it reads as painted planes not flat cel.
	float lq = (floor(l * bands) + 0.5) / bands;
	float k = mix(1.0, lq / max(l, 0.02), band_mix);
	col *= clamp(k, 0.6, 1.4);
	// Ink: thin, broken along the stroke by a little noise so it feels drawn not traced.
	float e = clamp(sobel(uv, px * ink_width) * 2.0, 0.0, 1.0);
	e *= 0.75 + 0.25 * hash21(floor(uv / px / 3.0));
	col *= 1.0 - e * ink;
	// Canvas weave and grain.
	vec2 c = uv / px;
	float w = (sin(c.x * 1.9) * sin(c.y * 1.9)) * 0.5 + 0.5;
	col *= 1.0 - weave * (w - 0.5);
	col += (hash21(floor(c * 0.5)) - 0.5) * grain;
	float vig = smoothstep(1.3, 0.5, length(uv - 0.5) * 1.4);
	col *= mix(0.78, 1.0, vig);
	COLOR = vec4(col, 1.0);
}
