shader_type sky;
render_mode use_half_res_pass;
// Kraków 1795 sky (scripts/city/sky.gd drives every uniform; docs/SKY.md).
//   full-res pass : atmosphere (5-step single scattering + an art gradient from data/weather.json), twilight, winter
//                   haze, sun disc and glare, moon (phase, maria, earthshine, halos), stars, planets, Milky Way,
//                   comet, meteors, lightning bolt; the cloud layer comes in from the half-res pass.
//   half-res pass : two cloud decks (low cumulus / stratus / nimbostratus / storm, and high cirrus) from two seamless
//                   noise textures, lit by the sun or moon (silver rims, dark bases), drifting with the wind.
//   cubemap pass  : the same without the point features (stars, meteors, bolt): SDFGI and reflections read it.
// Units: linear RGB; night zenith ~0.02 so lantern-lit scenes keep their ambient.

// ---- lights (direction TO the body, world space)
uniform vec3 sun_dir = vec3(0.0, -0.5, 0.86);
uniform vec3 moon_dir = vec3(0.0, 0.5, 0.86);
uniform vec3 sun_color : source_color = vec3(1.0, 0.95, 0.88);
uniform float sun_up = 0.0;           // 0..1: the directional light is the sun (weather.gd: sun elevation > -3 deg)
uniform float sun_elev = -30.0;       // degrees (from the weather clock)
uniform float moon_energy = 0.45;     // the moon light's energy (weather preset x night factor)
uniform float moon_phase = 0.68;      // 0 new, 0.25 first quarter, 0.5 full, 0.75 last quarter
uniform float moon_size = 0.5;        // angular radius, degrees (real 0.26; drawn larger to read at a 70 deg fov)
uniform float daylight = 0.0;         // Weather.current().daylight

// ---- colours (night ones = the weather preset's sky_top / sky_horizon: SDFGI ambient stays where it was)
uniform vec3 night_zenith : source_color = vec3(0.02, 0.025, 0.06);
uniform vec3 night_horizon : source_color = vec3(0.10, 0.09, 0.14);
uniform vec3 day_zenith : source_color = vec3(0.30, 0.42, 0.60);
uniform vec3 day_horizon : source_color = vec3(0.68, 0.72, 0.78);
uniform vec3 ground_color : source_color = vec3(0.03, 0.03, 0.04);
uniform vec3 haze_color : source_color = vec3(0.07, 0.08, 0.13);
uniform float haze = 0.3;             // winter haze band on the horizon (1 = fog whiteout)
uniform float haze_height = 0.12;     // how far up it reaches (sin of elevation)
uniform float sun_intensity = 16.0;   // physical-term scale
uniform float art_mix = 0.6;          // weight of the preset's day gradient against the physical term
uniform float town_glow = 0.35;       // the town's candle light on the low sky at night (very faint, warm)

// ---- clouds (see data/sky.json presets)
uniform sampler2D noise_a : hint_default_black, repeat_enable, filter_linear_mipmap;
uniform sampler2D noise_b : hint_default_black, repeat_enable, filter_linear_mipmap;
uniform float cloud_coverage = 0.3;
uniform float cloud_softness = 0.22;
uniform float cloud_scale = 1.0;
uniform float cloud_altitude = 0.9;   // low deck height (relative); lower = closer, more perspective
uniform float cloud_density = 1.0;
uniform float cloud_base_dark = 0.45; // how dark the thick undersides go
uniform float cloud_detail = 0.5;     // edge erosion by the second noise
uniform float cloud_sheet = 0.0;      // 1 = a featureless stratus sheet (flattens the lighting)
uniform float cloud_ragged = 0.0;     // nimbostratus scud: low torn fragments under the deck
uniform float cloud_tower = 0.0;      // storm: taller shading contrast, brighter rims, darker bases
uniform float cirrus = 0.0;           // high thin streaks
uniform float cirrus_streak = 3.0;    // stretch along the wind
uniform vec2 cloud_offset = vec2(0.0);   // accumulated wind drift (script, every frame)
uniform vec2 cirrus_offset = vec2(0.0);
uniform vec2 wind_dir = vec2(1.0, 0.0);

// ---- night sky
uniform mat3 star_basis = mat3(1.0); // world -> equatorial frame (script, from the sidereal time)
uniform float star_strength = 1.0;
uniform float milky_way = 0.6;
uniform float twinkle = 0.6;
uniform float planets = 1.0;
uniform float comet = 0.0;
uniform vec3 comet_dir = vec3(0.0, 0.0, 1.0);      // equatorial frame
uniform vec3 comet_tail = vec3(0.0, 1.0, 0.0);     // equatorial frame, away from the sun
uniform float moon_halo = 0.3;       // corona through thin cloud
uniform float halo22 = 0.0;          // ice-crystal 22 deg ring

// ---- events
uniform float flash = 0.0;           // lightning sky flash 0..1
uniform vec3 flash_dir = vec3(0.0, 0.3, 1.0);
uniform float flash_bolt = 0.0;      // 0 = sheet lightning behind cloud, >0 = a visible bolt of this brightness
uniform float flash_seed = 0.0;
uniform vec3 meteor_a = vec3(0.0, 1.0, 0.0);
uniform vec3 meteor_b = vec3(0.0, 1.0, 0.0);
uniform float meteor_t = -1.0;       // progress 0..1 (negative = none)
uniform float meteor_bright = 0.0;
uniform float meteor_fire = 0.0;     // fireball: fat green-white head, lingering train

const float R_E = 6371e3;
const float H_R = 8000.0;
const float H_M = 1200.0;
const vec3 BETA_R = vec3(5.5e-6, 13.0e-6, 22.4e-6);
const vec3 BETA_M = vec3(21e-6);

// ------------------------------------------------------------------ helpers

float hash1(vec3 p) {
	p = fract(p * vec3(443.897, 441.423, 437.195));
	p += dot(p, p.yzx + 19.19);
	return fract((p.x + p.y) * p.z);
}

vec3 hash3(vec3 p) {
	return vec3(hash1(p), hash1(p + 17.31), hash1(p + 91.7));
}

float chapman(float X, float cz) {
	float c = sqrt(X * 1.5707963);
	return c / ((c - 1.0) * cz + 1.0);
}

// optical depth (density x length) from height h toward cos-zenith cz, exponential atmosphere of scale height H
float od_sun(float h, float cz, float H) {
	float r0 = R_E + h;
	if (cz >= 0.0) {
		return exp(-h / H) * H * chapman(r0 / H, cz);
	}
	float sinz = sqrt(max(1.0 - cz * cz, 0.0));
	float rmin = r0 * sinz;
	if (rmin < R_E) {
		return 1e9;
	}
	return 2.0 * exp(-(rmin - R_E) / H) * H * chapman(rmin / H, 0.0) - exp(-h / H) * H * chapman(r0 / H, -cz);
}

vec3 sun_transmittance(float cz) {
	return exp(-(BETA_R * od_sun(0.0, cz, H_R) + BETA_M * od_sun(0.0, cz, H_M)));
}

// single scattering, five samples along the view ray, analytic sun depth per sample
vec3 scatter(vec3 v, vec3 s) {
	float cz = max(v.y, 0.0);
	float htop = 60e3;
	float ttop = -R_E * cz + sqrt(R_E * R_E * cz * cz + 2.0 * R_E * htop + htop * htop);
	float sy = s.y;
	float odR = 0.0;
	float odM = 0.0;
	vec3 sR = vec3(0.0);
	vec3 sM = vec3(0.0);
	float tprev = 0.0;
	for (int i = 0; i < 5; i++) {
		float f = float(i + 1) * 0.2;
		float t = ttop * f * f;
		float dt = t - tprev;
		float tm = 0.5 * (t + tprev);
		tprev = t;
		float h = sqrt(R_E * R_E + tm * tm + 2.0 * R_E * tm * cz) - R_E;
		float rR = exp(-h / H_R);
		float rM = exp(-h / H_M);
		odR += rR * dt * 0.5;
		odM += rM * dt * 0.5;
		vec3 tv = exp(-(BETA_R * odR + BETA_M * odM));
		vec3 ts = exp(-(BETA_R * od_sun(h, sy, H_R) + BETA_M * od_sun(h, sy, H_M)));
		sR += rR * tv * ts * dt;
		sM += rM * tv * ts * dt;
		odR += rR * dt * 0.5;
		odM += rM * dt * 0.5;
	}
	float ct = dot(v, s);
	float g = 0.7;
	float phR = 3.0 / (16.0 * PI) * (1.0 + ct * ct);
	float phM = 3.0 / (8.0 * PI) * ((1.0 - g * g) * (1.0 + ct * ct)) / ((2.0 + g * g) * pow(1.0 + g * g - 2.0 * g * ct, 1.5));
	return sun_intensity * (BETA_R * phR * sR + BETA_M * phM * sM);
}

// ------------------------------------------------------------------ clouds (half-res and cubemap passes)

// premultiplied colour + alpha of the cloud layers along `d`
vec4 clouds(vec3 d, vec3 amb_here, vec3 light_dir, vec3 light_col, float light_k) {
	float y = d.y;
	float up = smoothstep(-0.02, 0.10, y);
	if (up <= 0.0) {
		return vec4(0.0);
	}
	// ---- low deck: a plane at cloud_altitude with a curved horizon
	float t = cloud_altitude / (max(y, 0.0) + 0.06);
	vec2 uv = d.xz * t * 0.30 / max(cloud_scale, 0.05) + cloud_offset;
	float n1 = texture(noise_a, uv).r;
	float n2 = texture(noise_b, uv * 2.7 + cloud_offset * 0.6).r;
	float shape = n1 + (n2 - 0.5) * cloud_detail * 0.55;
	// scud: torn low fragments (a third, denser threshold on the detail noise)
	float scud = 0.0;
	if (cloud_ragged > 0.0) {
		float ts = cloud_altitude * 0.45 / (max(y, 0.0) + 0.08);
		vec2 uvs = d.xz * ts * 0.55 / max(cloud_scale, 0.05) + cloud_offset * 1.7;
		float n3 = texture(noise_b, uvs).r;
		scud = smoothstep(0.52, 0.72, n3 + (n1 - 0.5) * 0.4) * cloud_ragged;
	}
	float cov = clamp(cloud_coverage, 0.0, 1.0);
	float soft = max(cloud_softness, 0.02);
	float dens = smoothstep(1.0 - cov - soft, 1.0 - cov + soft, shape) * cloud_density;
	dens = max(dens, scud * 0.8);
	dens = min(dens, 1.0);
	// lighting: a second sample toward the light gives rims facing it; interior thickness darkens
	vec2 toward = light_dir.xz / max(abs(light_dir.y), 0.18) * 0.02 * (1.0 + cloud_tower * 0.8);
	float nl = texture(noise_a, uv + toward).r + (n2 - 0.5) * cloud_detail * 0.55;
	float dl = smoothstep(1.0 - cov - soft, 1.0 - cov + soft, nl) * cloud_density;
	float rim = exp(-dl * (2.6 + cloud_tower * 2.0)) * (1.0 - cloud_sheet * 0.85);
	// forward scatter: thin parts glow when the light is behind them
	float ct = max(dot(d, light_dir), 0.0);
	float fwd = pow(ct, 6.0) * (1.0 - dens) * 0.6 + pow(ct, 2.0) * 0.12;
	float thick = smoothstep(0.15, 0.95, dens);
	float base = cloud_base_dark * (0.6 + 0.4 * cloud_tower) * thick;
	vec3 lit = amb_here * (0.9 + 0.35 * rim) + light_col * light_k * (0.55 * rim + fwd) * (1.0 - cloud_sheet * 0.5);
	vec3 col = lit * (1.0 - base);
	// sheet lightning lights the deck from inside, brightest toward the flash
	if (flash > 0.001) {
		float fl = pow(max(dot(normalize(vec3(d.x, d.y * 0.6, d.z)), normalize(vec3(flash_dir.x, flash_dir.y * 0.6, flash_dir.z))), 0.0), 3.0);
		col += vec3(0.85, 0.9, 1.0) * flash * (0.03 + 0.35 * fl) * (0.4 + 0.6 * dens);
	}
	float a = dens * up;
	// ---- high cirrus: a stretched sheet, mostly forward-lit
	float ac = 0.0;
	vec3 cc = vec3(0.0);
	if (cirrus > 0.001) {
		float th = 6.0 / (max(y, 0.0) + 0.12);
		vec2 w = normalize(wind_dir + vec2(1e-3, 0.0));
		vec2 p = d.xz * th * 0.12 + cirrus_offset;
		vec2 pr = vec2(dot(p, w), dot(p, vec2(-w.y, w.x)));
		pr.x /= max(cirrus_streak, 1.0);
		float c1 = texture(noise_b, pr).r;
		vec2 pr2 = vec2(dot(p, vec2(w.x * 0.94 - w.y * 0.34, w.x * 0.34 + w.y * 0.94)), dot(p, vec2(-w.y, w.x))) * vec2(1.0 / max(cirrus_streak * 0.7, 1.0), 1.0);
		float c2 = texture(noise_a, pr2 * 1.9 + vec2(0.37, 0.11)).r;
		float cs = smoothstep(0.62 - cirrus * 0.22, 0.86, c1 * 0.7 + c2 * 0.3);
		ac = cs * cirrus * 0.42 * smoothstep(0.0, 0.18, y);
		float cf = pow(ct, 8.0) * 1.4 + pow(ct, 2.0) * 0.25 + 0.35;
		cc = amb_here * 1.0 + light_col * light_k * cf * mix(0.3, 1.0, daylight);
	}
	// composite cirrus behind the low deck, premultiplied
	vec3 rgb = cc * ac * (1.0 - a) + col * a;
	float alpha = a + ac * (1.0 - a);
	// distance fade into the horizon haze
	float far_k = 1.0 - exp(-t * 0.028);
	rgb = mix(rgb, amb_here * alpha, far_k * 0.85);
	return vec4(rgb, alpha);
}

// ------------------------------------------------------------------ night features

vec3 cube_dir(int face, vec2 uv) {  // uv in -1..1 on the face
	if (face == 0) return normalize(vec3(1.0, uv.y, -uv.x));
	if (face == 1) return normalize(vec3(-1.0, uv.y, uv.x));
	if (face == 2) return normalize(vec3(uv.x, 1.0, -uv.y));
	if (face == 3) return normalize(vec3(uv.x, -1.0, uv.y));
	if (face == 4) return normalize(vec3(uv.x, uv.y, 1.0));
	return normalize(vec3(-uv.x, uv.y, -1.0));
}

void face_uv(vec3 d, out int face, out vec2 uv) {
	vec3 a = abs(d);
	if (a.x >= a.y && a.x >= a.z) {
		face = d.x > 0.0 ? 0 : 1;
		uv = (d.x > 0.0 ? vec2(-d.z, d.y) : vec2(d.z, d.y)) / a.x;
	} else if (a.y >= a.z) {
		face = d.y > 0.0 ? 2 : 3;
		uv = (d.y > 0.0 ? vec2(d.x, -d.z) : vec2(d.x, d.z)) / a.y;
	} else {
		face = d.z > 0.0 ? 4 : 5;
		uv = (d.z > 0.0 ? vec2(d.x, d.y) : vec2(-d.x, d.y)) / a.z;
	}
}

// one star per grid cell; brightness follows the magnitude count law N(>B) ~ B^-1.25
float star_layer(vec3 dc, float n, float density, float bright, float seed, float horizon_k, float pix) {
	int face;
	vec2 uv;
	face_uv(dc, face, uv);
	vec2 g = (uv * 0.5 + 0.5) * n;
	vec2 cell = floor(g);
	vec3 h = hash3(vec3(cell, float(face) * 7.0 + seed));
	if (h.z > density) {
		return 0.0;
	}
	vec2 spos = (cell + 0.2 + 0.6 * h.xy) / n * 2.0 - 1.0;
	vec3 sd = cube_dir(face, spos);
	float ang = length(cross(dc, sd));
	float u = max(hash1(vec3(cell, seed + 3.3 + float(face))), 0.02);
	float b = min(pow(u, -0.8) - 0.9, 14.0) * bright;
	float sigma = max(0.0009 + 0.00035 * log(1.0 + b), pix * 0.7);
	float core = exp(-ang * ang / (2.0 * sigma * sigma));
	float tw = 1.0 + twinkle * (0.25 + 0.5 * horizon_k) * sin(TIME * (2.5 + 4.0 * h.x) + h.y * 40.0);
	return b * core * tw;
}

vec3 star_color(vec3 dc, float seed) {
	float t = hash1(dc * 13.1 + seed);   // blue-white to orange
	return mix(vec3(0.75, 0.82, 1.0), vec3(1.0, 0.85, 0.65), smoothstep(0.55, 0.95, t));
}

float point_glow(vec3 d, vec3 p, float sigma) {
	float ang = length(cross(d, p));
	return exp(-ang * ang / (2.0 * sigma * sigma)) * step(0.0, dot(d, p));
}

// ------------------------------------------------------------------ sky

void sky() {
	vec3 d = EYEDIR;
	// gradient-space pixel size (radians) for antialiasing the point features
	float pix = length(vec2(dFdx(d.x), dFdy(d.y))) + 1e-5;
	vec3 sd = normalize(sun_dir);
	vec3 md = normalize(moon_dir);
	float dl = clamp(daylight, 0.0, 1.0);
	float sunf = smoothstep(-8.0, 4.0, sun_elev);         // sun contributes light
	float night = 1.0 - smoothstep(-9.0, -1.0, sun_elev); // stars, moon glow

	// ---- base colour: the preset's night gradient + physical day scattering + an art gradient
	float yk = 1.0 - pow(1.0 - clamp(d.y, 0.0, 1.0), 6.0);
	vec3 night_col = mix(night_horizon, night_zenith, yk);
	night_col += night_horizon * town_glow * 0.25 * exp(-max(d.y, 0.0) * 10.0) * vec3(1.05, 0.95, 0.85);
	vec3 sun_t = sun_transmittance(sd.y);
	vec3 light_col = sun_color * sun_t;
	float mk = moon_energy * night;
	if (AT_HALF_RES_PASS) {
		vec3 ld = sunf > 0.5 ? sd : md;
		vec3 lc = mix(vec3(0.6, 0.7, 1.0) * mk * 1.0, light_col, sunf);
		vec3 amb = mix(night_col, mix(day_horizon, day_zenith, yk * 0.6), sunf);
		vec4 c = clouds(d, amb, ld, lc, 1.0);
		COLOR = c.rgb;
		ALPHA = c.a;
	} else {
		vec3 col = night_col * (1.0 - 0.85 * sunf);
		if (sun_elev > -14.0) {
			vec3 phys = scatter(d, sd);
			vec3 art = mix(day_horizon, day_zenith, yk) * sunf;
			col += phys + art * art_mix;
			// twilight: warm band toward the sun, violet toward the zenith, lasting to -10 deg
			float tw = smoothstep(-11.0, -3.0, sun_elev) * (1.0 - smoothstep(0.0, 8.0, sun_elev));
			vec2 hd = normalize(d.xz + vec2(1e-4, 0.0));
			vec2 hs = normalize(sd.xz + vec2(1e-4, 0.0));
			float az = max(dot(hd, hs), 0.0);
			float band = exp(-max(d.y, 0.0) * 6.5) * (0.25 + 0.75 * pow(az, 3.0));
			vec3 twc = mix(vec3(0.28, 0.14, 0.24), vec3(1.0, 0.50, 0.22), pow(az, 2.0) * exp(-max(d.y, 0.0) * 9.0));
			col += twc * tw * band * 0.55;
		}

		// ---- sun disc and glare
		if (sun_up > 0.0 && sd.y > -0.05) {
			float ang = acos(clamp(dot(d, sd), -1.0, 1.0));
			float r = radians(0.30);
			float disc = 1.0 - smoothstep(r - pix, r + pix, ang);
			float limb = 1.0 - 0.35 * pow(clamp(ang / r, 0.0, 1.0), 4.0);
			vec3 sunc = light_col * sun_up;
			col += sunc * (disc * limb * 18.0 + 0.012 / (ang * ang + 0.0008) + 0.35 * exp(-ang * 12.0));
		}

		// ---- clouds (half res); lit by the sun or the moon
		vec4 cl = HALF_RES_COLOR;
		if (AT_CUBEMAP_PASS) {
			vec3 ld = sunf > 0.5 ? sd : md;
			vec3 lc = mix(vec3(0.6, 0.7, 1.0) * mk * 1.0, light_col, sunf);
			cl = clouds(d, mix(night_col, mix(day_horizon, day_zenith, yk * 0.6), sunf), ld, lc, 1.0);
		}

		// ---- moon: disc with phase and maria, earthshine, halos
		if (night > 0.001 || sun_elev < 6.0) {
			float cm = dot(d, md);
			float ang = acos(clamp(cm, -1.0, 1.0));
			float r = radians(moon_size);
			vec3 mcol = vec3(0.0);
			if (ang < r + pix * 2.0) {
				vec3 right = normalize(cross(vec3(0.0, 1.0, 0.0), md));
				vec3 upm = cross(md, right);
				vec2 p = vec2(dot(d, right), dot(d, upm)) / sin(r);
				float rr = dot(p, p);
				float inside = 1.0 - smoothstep(1.0 - pix / r * 1.5, 1.0 + pix / r * 0.5, sqrt(rr));
				vec3 nrm = vec3(p, sqrt(max(1.0 - rr, 0.0)));
				float ph = moon_phase * 2.0 * PI;
				vec3 L = vec3(sin(ph), 0.0, -cos(ph));
				float tilt = radians(-22.0);
				L.xy = vec2(L.x * cos(tilt) - L.y * sin(tilt), L.x * sin(tilt) + L.y * cos(tilt));
				float lam = max(dot(nrm, L), 0.0);
				// maria: a fixed pattern on the disc from the cloud noise
				vec2 tuv = p * 0.23 + vec2(0.31, 0.62);
				float m1 = texture(noise_a, tuv).r;
				float m2 = texture(noise_b, tuv * 2.3 + 0.2).r;
				float maria = smoothstep(0.47, 0.60, m1 * 0.75 + m2 * 0.25);
				float craters = smoothstep(0.78, 0.9, m2) * 0.25;
				float albedo = mix(0.95, 0.36, maria) + craters;
				float limb = 1.0 - 0.25 * pow(rr, 2.0);
				float earthshine = 0.035 * (1.0 - smoothstep(0.35, 0.65, moon_phase)) + 0.012;
				mcol = vec3(0.98, 0.97, 0.92) * albedo * limb * (lam * 2.4 + earthshine) * inside * (0.55 + mk * 1.0);
			}
			// soft glow, corona through thin cloud, the 22 degree ice halo
			float glow = 0.05 * exp(-ang * 55.0) + 0.006 * exp(-ang * 9.0);
			float corona = moon_halo * cl.a * (0.12 * exp(-ang * 14.0) + 0.03 * exp(-ang * 4.0));
			float adeg = degrees(ang);
			float ring = halo22 * exp(-pow((adeg - 22.0) / 1.1, 2.0)) * 0.03;
			vec3 ringc = mix(vec3(1.0, 0.75, 0.6), vec3(0.8, 0.88, 1.0), smoothstep(21.5, 23.0, adeg));
			vec3 mglow = vec3(0.85, 0.9, 1.0) * (glow + corona) * max(mk, 0.05) * 2.0 + ringc * ring * max(mk, 0.05) * 2.0;
			col += mcol * (1.0 - cl.a * 0.92) + mglow;
		}

		// ---- stars, planets, the Milky Way, the comet, a meteor (screen only)
		if (!AT_CUBEMAP_PASS && night > 0.001 && d.y > -0.05) {
			vec3 dc = star_basis * d;
			float hk = 1.0 - smoothstep(0.0, 0.5, d.y);
			float vis = night * star_strength * (1.0 - cl.a) * (1.0 - dl);
			vis *= 1.0 - 0.45 * smoothstep(0.0, 0.6, mk);          // moonlight washes the faint ones
			vis *= smoothstep(-0.03, 0.12, d.y);                   // extinction at the horizon
			// Milky Way band (galactic pole RA 192.85 dec 27.13)
			vec3 gp = vec3(-0.8676, -0.1979, 0.4560);
			float gz = dot(dc, gp);
			float mw = exp(-gz * gz / 0.045) * milky_way;
			float mwn = texture(noise_a, dc.xy * 0.9 + dc.z * 0.4).r * 0.6 + texture(noise_b, dc.zx * 1.7).r * 0.4;
			mw *= 0.45 + 0.9 * mwn;
			vec3 stars = vec3(0.0);
			stars += star_color(dc, 1.0) * star_layer(dc, 46.0, 0.55, 0.45, 1.0, hk, pix);
			stars += star_color(dc, 2.0) * star_layer(dc, 110.0, 0.55 + 0.4 * mw, 0.06, 2.0, hk, pix);
			stars += vec3(0.7, 0.75, 0.9) * star_layer(dc, 210.0, 0.35 + 0.6 * mw, 0.014, 3.0, hk, pix);
			col += stars * vis * 0.08;
			col += vec3(0.16, 0.18, 0.24) * mw * 0.022 * vis;
			// planets: Jupiter (Gemini), Saturn (Taurus), Venus low in the west after dusk
			if (planets > 0.0) {
				vec3 jup = vec3(-0.0033, 0.9192, 0.3936);
				vec3 sat = vec3(0.6830, 0.6830, 0.2588);
				vec3 ven = vec3(0.3830, -0.9002, -0.2079);
				vec3 pc = vec3(0.0);
				pc += vec3(1.0, 0.96, 0.88) * 0.9 * point_glow(dc, jup, max(0.0016, pix * 0.8));
				pc += vec3(1.0, 0.92, 0.75) * 0.32 * point_glow(dc, sat, max(0.0013, pix * 0.8));
				pc += vec3(1.0, 0.98, 0.94) * 1.6 * point_glow(dc, ven, max(0.0018, pix * 0.8));
				col += pc * planets * vis * 1.2;
			}
			// comet: fuzzy coma, a tail away from the sun (equatorial frame)
			if (comet > 0.001) {
				vec3 cdn = normalize(comet_dir);
				vec3 off = dc - cdn * dot(dc, cdn);
				vec3 tdir = normalize(comet_tail - cdn * dot(comet_tail, cdn));
				float along = dot(off, tdir);
				float across = length(off - tdir * along);
				float coma = exp(-length(off) * length(off) / (2.0 * 0.005 * 0.005)) * 0.9 + exp(-length(off) / 0.016) * 0.35;
				float tail = smoothstep(-0.005, 0.02, along) * exp(-along / 0.14) * exp(-across * across / (2.0 * pow(0.006 + along * 0.22, 2.0))) * 0.35;
				col += (vec3(0.82, 0.88, 1.0) * coma + vec3(0.95, 0.9, 0.78) * tail) * comet * vis * 0.55 * step(0.0, dot(dc, cdn));
			}
			// meteor: a streak from meteor_a toward meteor_b
			if (meteor_t >= 0.0 && meteor_bright > 0.0) {
				vec3 head = normalize(mix(meteor_a, meteor_b, meteor_t));
				float tl = mix(0.28, 0.6, meteor_fire);
				vec3 tail = normalize(mix(meteor_a, meteor_b, max(meteor_t - tl, 0.0)));
				vec3 seg = head - tail;
				float sl = max(length(seg), 1e-4);
				vec3 sn = seg / sl;
				float u = clamp(dot(d - tail, sn), 0.0, sl);
				vec3 cp = tail + sn * u;
				float dist = length(d - cp);
				float w = max(0.0009 + 0.0022 * meteor_fire, pix * 0.8);
				float along_k = u / sl;
				float streak = exp(-dist * dist / (2.0 * w * w)) * pow(along_k, 1.6);
				float hglow = exp(-length(d - head) / (0.006 + 0.02 * meteor_fire)) * (0.4 + 1.2 * meteor_fire);
				float fade = smoothstep(0.0, 0.08, meteor_t) * (1.0 - smoothstep(0.75, 1.0, meteor_t));
				vec3 mc = mix(vec3(0.85, 0.9, 1.0), vec3(0.75, 1.0, 0.8), meteor_fire * 0.7);
				col += mc * (streak * 0.9 + hglow) * meteor_bright * fade * (1.0 - cl.a) * 0.6;
			}
		}

		// ---- cloud composite
		col = col * (1.0 - cl.a) + cl.rgb;

		// ---- lightning bolt below the cloud base (the diffuse flash is in the clouds)
		if (flash > 0.001) {
			col += vec3(0.7, 0.78, 1.0) * flash * 0.04 * (0.5 + 0.5 * max(dot(d, normalize(flash_dir)), 0.0));
			if (flash_bolt > 0.0 && !AT_CUBEMAP_PASS) {
				vec3 fd = normalize(flash_dir);
				vec3 right = normalize(cross(vec3(0.0, 1.0, 0.0), fd));
				vec3 upb = cross(fd, right);
				vec2 p = vec2(dot(d, right), dot(d, upb));
				float best = 1e9;
				vec2 a = vec2(0.0, 0.16);
				float seedk = flash_seed;
				for (int i = 0; i < 7; i++) {
					float fi = float(i);
					vec2 hh = hash3(vec3(fi, seedk, 4.2)).xy - 0.5;
					vec2 b = vec2(a.x + hh.x * 0.06, a.y - 0.03 - abs(hh.y) * 0.02);
					vec2 pa = p - a;
					vec2 ba = b - a;
					float hseg = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
					best = min(best, length(pa - ba * hseg));
					// a short branch off every other joint
					if (i == 2 || i == 4) {
						vec2 c = b + vec2(sign(hh.x) * 0.05, -0.035);
						vec2 bc = c - b;
						vec2 pb = p - b;
						float hb = clamp(dot(pb, bc) / dot(bc, bc), 0.0, 1.0);
						best = min(best, length(pb - bc * hb) + 0.0015);
					}
					a = b;
				}
				float core = exp(-best / max(0.0012, pix * 1.2));
				float glow = exp(-best / 0.02);
				col += vec3(0.8, 0.85, 1.0) * flash_bolt * flash * (core * 18.0 + glow * 1.6) * step(0.0, dot(d, fd));
			}
		}


		// ---- winter haze on the horizon (the fog presets close it to a whiteout) and the ground below the horizon
		vec3 hz = mix(haze_color, mix(day_horizon, haze_color, 0.35), dl);
		float hb = haze * exp(-max(d.y, 0.0) / max(haze_height, 0.01));
		col = mix(col, hz, clamp(hb, 0.0, 1.0));
		if (d.y < 0.0) {
			float gk = smoothstep(0.0, -0.25, d.y);
			vec3 g = mix(mix(col, hz, 0.5), ground_color, gk);
			col = mix(col, g, smoothstep(0.0, -0.01, d.y));
		}

		COLOR = col;
	}
}
