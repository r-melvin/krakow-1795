#!/usr/bin/env python3
"""Procedural sound library for Krakow 1795.

Every sound in assets/audio/ is synthesised here from noise, oscillators, damped modes, formant filters and a
convolution reverb (numpy only; ffmpeg's libvorbis for the Ogg files). Deterministic: each sound is seeded from its
name, so a re-run writes the same samples. Short point sounds are 22.05 kHz mono 16-bit WAV; beds, bells, the
hejnal and other long sounds are 22.05 kHz mono Ogg Vorbis. assets/audio/manifest.json lists every file with its
set, duration, loop flag, peak and RMS; scripts/audio/sfx.gd reads it at run time.

Usage:
  python3 tools/gen_sfx.py                   # synthesise everything + manifest.json
  python3 tools/gen_sfx.py --only step_,hoof # just the names starting with these prefixes (manifest merged)
  python3 tools/gen_sfx.py --list            # the sound list with descriptions
  python3 tools/gen_sfx.py --demo            # also render assets/audio/demo_mix.ogg (20 s walk through the
                                             # square) and print its RMS/peak stats and timeline

Code: MIT. Generated audio: CC BY 4.0 (see README, Attribution).
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import wave
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "audio"
SR = 22050
NYQ = SR / 2
TAU = 2 * math.pi


# ====================================================================== primitives

def secs(d):
    return max(1, int(round(d * SR)))


def tt(n):
    return np.arange(n) / SR


def seeded(name):
    return np.random.default_rng(zlib.crc32(name.encode()))


def nextpow2(n):
    return 1 << int(n - 1).bit_length()


def fit(x, n):
    if len(x) >= n:
        return x[:n]
    return np.concatenate([x, np.zeros(n - len(x))])


def mix(dst, src, at, gain=1.0):
    """Adds src into dst starting at `at` seconds (clipped to dst)."""
    i = int(round(at * SR))
    if i >= len(dst) or i + len(src) <= 0:
        return dst
    s0 = max(0, -i)
    i = max(0, i)
    m = min(len(dst) - i, len(src) - s0)
    dst[i:i + m] += src[s0:s0 + m] * gain
    return dst


def conv(a, b):
    n = len(a) + len(b) - 1
    N = nextpow2(n)
    return np.fft.irfft(np.fft.rfft(a, N) * np.fft.rfft(b, N), N)[:n]


def rms(x):
    return float(np.sqrt(np.mean(x * x) + 1e-20))


def db(v):
    return 20 * math.log10(max(v, 1e-9))


# ---------------------------------------------------------------- filters (zero-phase, frequency domain)

def g_lp(fc, order=2):
    return lambda f: 1.0 / np.sqrt(1.0 + (f / fc) ** (2 * order))


def g_hp(fc, order=2):
    return lambda f: 1.0 / np.sqrt(1.0 + (fc / np.maximum(f, 1e-3)) ** (2 * order))


def g_bp(fc, q):
    return lambda f: 1.0 / np.sqrt(1.0 + q * q * (f / fc - fc / np.maximum(f, 1e-3)) ** 2)


def g_peak(fc, q, gain_db):
    k = 10 ** (gain_db / 20) - 1
    return lambda f: 1.0 + k * g_bp(fc, q)(f) ** 2


def g_mul(*gs):
    def g(f):
        out = np.ones_like(f)
        for gg in gs:
            out = out * gg(f)
        return out
    return g


def filt(x, gain, circular=False, pad=0.2):
    """Applies a magnitude response gain(f) (zero phase). Padded on both sides unless circular (loops)."""
    if circular:
        X = np.fft.rfft(x)
        return np.fft.irfft(X * gain(np.fft.rfftfreq(len(x), 1 / SR)), len(x))
    p = secs(pad)
    xp = np.concatenate([np.zeros(p), x, np.zeros(p)])
    X = np.fft.rfft(xp)
    y = np.fft.irfft(X * gain(np.fft.rfftfreq(len(xp), 1 / SR)), len(xp))
    return y[p:p + len(x)]


def lp(x, fc, order=2, circular=False):
    return filt(x, g_lp(fc, order), circular)


def hp(x, fc, order=2, circular=False):
    return filt(x, g_hp(fc, order), circular)


def bp(x, fc, q=1.0, circular=False):
    return filt(x, g_bp(fc, q), circular)


def stft_filter(x, gain_fn, nfft=1024, hop=256):
    """Time-varying zero-phase filter: gain_fn(times (F,1), freqs (1,B)) -> (F,B) gains. Hann overlap-add."""
    n = len(x)
    xp = np.concatenate([np.zeros(nfft), x, np.zeros(nfft)])
    win = 0.5 - 0.5 * np.cos(TAU * np.arange(nfft) / nfft)
    nfr = 1 + (len(xp) - nfft) // hop
    idx = np.arange(nfft)[None, :] + hop * np.arange(nfr)[:, None]
    X = np.fft.rfft(xp[idx] * win, axis=1)
    freqs = np.fft.rfftfreq(nfft, 1 / SR)[None, :]
    tc = ((hop * np.arange(nfr) + nfft / 2 - nfft) / SR)[:, None]
    Y = np.fft.irfft(X * gain_fn(tc, freqs), nfft, axis=1) * win
    out = np.zeros(len(xp))
    for i in range(nfr):
        out[i * hop:i * hop + nfft] += Y[i]
    return out[nfft:nfft + n] / 1.5


# ---------------------------------------------------------------- sources

def noise(r, n, slope_db=0.0):
    """Gaussian noise with a spectral slope in dB/octave (0 white, -3 pink, -6 brown). Unit std."""
    w = r.standard_normal(n)
    if slope_db == 0.0:
        return w
    X = np.fft.rfft(w)
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = f[1]
    X *= (f / 1000.0) ** (slope_db / 6.0206)
    y = np.fft.irfft(X, n)
    return y / (np.std(y) + 1e-12)


def ctrl(r, n, rate, lo=-1.0, hi=1.0):
    """Smooth random control signal (cosine-interpolated random points at `rate` per second)."""
    k = max(2, int(n / SR * rate) + 2)
    pts = r.uniform(lo, hi, k)
    pos = np.arange(n) / max(n - 1, 1) * (k - 1)
    i0 = np.minimum(pos.astype(int), k - 2)
    fr = pos - i0
    w = (1 - np.cos(math.pi * fr)) * 0.5
    return pts[i0] * (1 - w) + pts[i0 + 1] * w


def env(n, a=0.002, tau=0.1, hold=0.0):
    """Linear attack `a`, optional hold, then exponential decay with time constant `tau`."""
    t = tt(n)
    e = np.exp(-np.maximum(t - a - hold, 0.0) / tau)
    na = min(max(1, secs(a)), n)
    e[:na] *= np.linspace(0, 1, na)
    return e


def env_pts(n, pts):
    """Piecewise-linear envelope from [(t, v), ...]."""
    ts = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    return np.interp(tt(n), ts, vs)


def modes(r, n, freqs, amps, taus, attack=0.0004):
    """Sum of exponentially damped sinusoids (resonant body). Random phases, tiny attack ramp."""
    t = tt(n)
    out = np.zeros(n)
    for f, a, tau in zip(freqs, amps, taus):
        if f <= 0 or f >= NYQ * 0.95:
            continue
        out += a * np.exp(-t / tau) * np.sin(TAU * f * t + r.uniform(0, TAU))
    na = secs(attack)
    out[:na] *= np.linspace(0, 1, na)
    return out


def burst(r, n, tau, a=0.0003):
    return noise(r, n) * env(n, a, tau)


def thud(n, f=90.0, tau=0.03, sweep=0.4, a=0.0015):
    """Low body thump: a sine that drops from f*(1+sweep) to f."""
    t = tt(n)
    fr = f * (1 + sweep * np.exp(-t / 0.012))
    return np.sin(TAU * np.cumsum(fr) / SR) * env(n, a, tau)


def chirp(n, f0, f1, tau, curve=1.0):
    t = tt(n)
    x = (t / max(t[-1], 1e-6)) ** curve
    fr = f0 + (f1 - f0) * x
    return np.sin(TAU * np.cumsum(fr) / SR) * env(n, 0.001, tau)


def grains(r, n, count, t0, spread, f_lo, f_hi, tau_lo=0.0008, tau_hi=0.003, skew=3.0, amp_pow=2.0):
    """Micro-clicks (tiny damped sines): crunch, grit, gravel, crackle. Times beta-skewed towards t0."""
    out = np.zeros(n)
    for _ in range(int(count)):
        at = t0 + spread * r.beta(1.2, skew)
        tau = r.uniform(tau_lo, tau_hi)
        L = secs(tau * 6)
        f = math.exp(r.uniform(math.log(f_lo), math.log(f_hi)))
        tg = tt(L)
        g = (r.uniform() ** amp_pow) * np.exp(-tg / tau) * np.sin(TAU * f * tg + r.uniform(0, TAU))
        mix(out, g, at)
    return out


def saw(f0, jitter=None):
    """Naive sawtooth following a per-sample frequency array (aliasing tamed by the formant filters after it)."""
    f = f0 if jitter is None else f0 * (1 + jitter)
    ph = np.cumsum(f / SR)
    return 2 * (ph % 1.0) - 1


def pulse_train(r, n, rate, width=0.004, jitter=0.1):
    out = np.zeros(n)
    t = 0.0
    k = secs(width * 5)
    shape = np.exp(-tt(k) / width)
    while t < n / SR:
        mix(out, shape * r.uniform(0.6, 1.0), t)
        t += (1.0 / rate) * (1 + r.uniform(-jitter, jitter))
    return out


def reverb(x, rt60=1.8, wet=0.3, pre=0.015, bright=5000.0, seed=7, early=()):
    """Convolution with synthetic decaying noise (HF darkening over time) + optional early echoes [(s, gain)]."""
    r = np.random.default_rng(seed)
    L = secs(rt60 * 1.15)
    t = tt(L)
    base = r.standard_normal(L) * 10 ** (-3 * t / rt60)
    bright_ir = lp(base, bright, 1)
    dark_ir = lp(base, bright / 5, 1)
    w = np.clip(t / (rt60 * 0.6), 0, 1)
    ir = bright_ir * (1 - w) + dark_ir * w
    ir = np.concatenate([np.zeros(secs(pre)), ir])
    ir /= math.sqrt(np.sum(ir * ir)) + 1e-12
    for d, g in early:
        e = np.zeros(len(ir))
        i = secs(d)
        if i < len(ir):
            e[i] = g
            ir = ir + lp(e, bright * 0.6, 1) * 3.0
    wet_sig = conv(x, ir)
    wet_sig *= rms(x) / (rms(wet_sig) + 1e-12) * 0.7
    dry = fit(x, len(wet_sig))
    return dry * (1 - wet * 0.35) + wet_sig * wet


def soft_limit(x, drive=1.5):
    p = np.max(np.abs(x)) + 1e-12
    return np.tanh(drive * x / p) / math.tanh(drive) * p


def loopify(x, n_loop, xf):
    """Equal-power crossfade of the tail (x[n_loop:n_loop+xf]) into the head: a seamless loop of n_loop samples."""
    x = fit(x, n_loop + xf)
    y = x[:n_loop].copy()
    a = np.linspace(0, 1, xf)
    y[:xf] = x[:xf] * np.sqrt(a) + x[n_loop:n_loop + xf] * np.sqrt(1 - a)
    return y


def finalize(x, loop=False, peak_db=-1.0, drive=1.3, fade_out=0.004):
    x = np.asarray(x, dtype=np.float64)
    x = x - np.mean(x)
    x = hp(x, 28, 2, circular=loop)
    if drive > 0:
        x = soft_limit(x, drive)
    p = np.max(np.abs(x)) + 1e-12
    x = x / p * 10 ** (peak_db / 20)
    if not loop:
        na = min(secs(0.0008), len(x))
        x[:na] *= np.linspace(0, 1, na)
        nf = min(secs(fade_out), len(x))
        x[-nf:] *= np.linspace(1, 0, nf)
    return x


# ---------------------------------------------------------------- voices (formants)

VOWELS = {   # (F, bandwidth, gain dB) for an adult man
    "a": [(730, 110, 0), (1090, 120, -5), (2440, 170, -18), (3400, 250, -26)],
    "e": [(530, 90, 0), (1840, 120, -12), (2480, 170, -18), (3500, 250, -26)],
    "i": [(290, 70, 0), (2250, 120, -16), (2900, 170, -16), (3600, 250, -26)],
    "o": [(570, 90, 0), (840, 100, -6), (2410, 170, -24), (3300, 250, -30)],
    "u": [(330, 70, 0), (720, 90, -12), (2240, 170, -30), (3300, 250, -34)],
    "y": [(470, 90, 0), (1500, 110, -10), (2500, 170, -20), (3500, 250, -28)],   # Polish y / schwa
}
VKEYS = list(VOWELS)


def vowel(v, scale=1.0):
    return np.array([(F * scale, B * scale, g) for F, B, g in VOWELS[v]], dtype=np.float64)


def formant_gain(f, fm):
    """f: (...,B) freqs; fm: (...,M,3) per-row formants -> (...,B) linear gain."""
    g = np.zeros(np.broadcast_shapes(f.shape, fm.shape[:-2] + (1,)))
    for m in range(fm.shape[-2]):
        F = fm[..., m, 0][..., None]
        B = fm[..., m, 1][..., None]
        a = 10 ** (fm[..., m, 2][..., None] / 20)
        g = g + a / (1 + ((f - F) / (B * 0.5)) ** 2)
    return g + 0.003


def vowel_track(keys, scale=1.0):
    """keys [(t, vowel), ...] -> fn(times) -> (T, M, 3) interpolated formants."""
    ts = np.array([k[0] for k in keys])
    arr = np.stack([vowel(k[1], scale) for k in keys])

    def fn(times):
        times = np.asarray(times).reshape(-1)
        out = np.empty((len(times),) + arr.shape[1:])
        for m in range(arr.shape[1]):
            for c in range(3):
                out[:, m, c] = np.interp(times, ts, arr[:, m, c])
        return out
    return fn


def additive_voice(f0, track, rolloff=-10.0, fmax=None, step=64, chunk=8192):
    """Harmonic voice: sum of partials of the per-sample f0, weighted by the formant track and a spectral tilt."""
    n = len(f0)
    fmax = min(fmax or NYQ * 0.92, NYQ * 0.92)
    K = max(1, int(fmax / max(np.min(f0), 20.0)))
    nc = n // step + 2
    cpos = np.arange(nc) * step
    f0c = np.interp(cpos, np.arange(n), f0)
    fm = track(cpos / SR)                              # (nc, M, 3)
    k = np.arange(1, K + 1)[:, None]
    hf = k * f0c[None, :]                              # (K, nc)
    amp = np.zeros((K, nc))
    for m in range(fm.shape[1]):
        F = fm[:, m, 0][None, :]
        B = fm[:, m, 1][None, :]
        a = 10 ** (fm[:, m, 2][None, :] / 20)
        amp += a / (1 + ((hf - F) / (B * 0.5)) ** 2)
    amp = (amp + 0.002) * k ** (rolloff / 6.0206)
    amp[hf > fmax] = 0.0
    ph = TAU * np.cumsum(f0) / SR
    out = np.zeros(n)
    for s in range(0, n, chunk):
        e = min(n, s + chunk)
        pos = np.arange(s, e) / step
        i0 = np.minimum(pos.astype(int), nc - 2)
        fr = pos - i0
        A = amp[:, i0] * (1 - fr) + amp[:, i0 + 1] * fr
        out[s:e] = np.sum(A * np.sin(k * ph[None, s:e]), axis=0)
    return out


def curve(n, pts):
    """Per-sample control from [(t, v), ...] (linear)."""
    return env_pts(n, pts)


def vibrato(n, rate, depth, delay=0.0, r=None):
    t = tt(n)
    ramp = np.clip((t - delay) / 0.25, 0, 1)
    ph = r.uniform(0, TAU) if r is not None else 0.0
    return 1 + depth * ramp * np.sin(TAU * rate * t + ph)


def noisy_formant(r, n, track):
    """Noise shaped by a time-varying formant track (breath, hoarseness, whisper)."""
    def g(tc, f):
        return formant_gain(f, track(tc[:, 0]))
    return stft_filter(noise(r, n), g)


def babble(r, n, voices, fmax=3200.0, men=0.6, rate=5.5, gap=(0.3, 1.6), phrase=(0.8, 2.8), level_spread=9.0,
           f0_scale=1.0, monotone=False, breath=1.0):
    """Granular crowd talk: each voice speaks phrases of vowel syllables (formant-filtered glottal saw), with
    consonant dips and the odd fricative. Returns the sum of `voices` voices at spread levels."""
    out = np.zeros(n)
    hop = 256
    for v in range(voices):
        man = r.uniform() < men
        base = (r.uniform(95, 140) if man else r.uniform(180, 245)) * f0_scale
        scale = 1.0 if man else 1.16
        f0 = np.full(n, base)
        amp = np.zeros(n)
        vow = np.zeros(n, dtype=int)
        fric = np.zeros(n)
        t = r.uniform(0, 1.5)
        while t < n / SR:
            pd = r.uniform(*phrase)
            pe = min(t + pd, n / SR)
            st = t
            while st < pe:
                sd = r.uniform(0.7, 1.4) / rate
                i0, i1 = secs(st), min(n, secs(st + sd))
                if i1 <= i0:
                    break
                L = i1 - i0
                decl = 1.0 - 0.12 * (st - t) / max(pd, 0.1)
                wob = r.uniform(-0.04, 0.04) if monotone else r.uniform(-0.2, 0.22)
                f0[i0:i1] = base * decl * (1 + wob + np.linspace(r.uniform(-0.05, 0.05), r.uniform(-0.15, 0.15), L))
                e = np.sin(np.linspace(0, math.pi, L)) ** 0.6
                amp[i0:i1] = np.maximum(amp[i0:i1], e * r.uniform(0.6, 1.0))
                vow[i0:i1] = r.integers(0, len(VKEYS))
                if r.uniform() < 0.18:
                    fl = min(secs(0.05), L)
                    fric[i0:i0 + fl] += np.hanning(fl) * r.uniform(0.2, 0.5)
                st += sd
            t = pe + r.uniform(*gap)
        amp = lp(amp, 30, 1)
        amp = np.maximum(amp, 0)
        src = saw(lp(f0, 20, 1), jitter=0.03 * ctrl(r, n, 60) + 0.015 * noise(r, n))
        src = src * 0.55 + noise(r, n) * 0.35 * breath          # breath: speech heard across a square is mostly noise
        # per-frame formants from the vowel index at the frame centre (smoothed by the frame overlap)
        tbl = np.stack([vowel(k, scale) for k in VKEYS])

        def g(tc, f, vow=vow, tbl=tbl):
            idx = np.clip((tc[:, 0] * SR).astype(int), 0, n - 1)
            return formant_gain(f, tbl[vow[idx]]) * g_lp(fmax, 2)(f)
        voiced = stft_filter(src, g, hop=hop) * amp
        fr = hp(noise(r, n), 3500) * lp(fric, 40, 1) * 0.25
        out += (voiced + fr) * 10 ** (-r.uniform(0, level_spread) / 20)
    return out


# ====================================================================== registry

SOUNDS = {}


def snd(name, n=1, loop=False, fmt="wav", cat="sfx", desc="", peak=-1.0, drive=1.3):
    def deco(fn):
        SOUNDS[name] = dict(fn=fn, n=n, loop=loop, fmt=fmt, cat=cat, desc=desc, peak=peak, drive=drive)
        return fn
    return deco


# ====================================================================== footsteps

def _impact(r, surface, weight=1.0):
    n = secs(0.3)
    if surface == "cobbles":
        x = hp(burst(r, n, 0.0015), 1800) * 0.5
        x += modes(r, n, [r.uniform(1800, 3200), r.uniform(900, 1500), r.uniform(3500, 5200)], [0.5, 0.35, 0.22],
                   [0.012, 0.02, 0.006])
        x += thud(n, r.uniform(85, 120), 0.025) * 0.55 * weight
        x += grains(r, n, 8, 0.004, 0.05, 2000, 6000) * 0.25
    elif surface == "flags":
        x = hp(burst(r, n, 0.002), 1200) * 0.35
        x += modes(r, n, [r.uniform(700, 1100), r.uniform(1300, 2000), r.uniform(2500, 3200)], [0.5, 0.3, 0.15],
                   [0.035, 0.02, 0.01])
        x += thud(n, r.uniform(80, 105), 0.03) * 0.7 * weight
    elif surface == "snow":
        x = grains(r, n, r.integers(160, 240), 0.0, r.uniform(0.11, 0.16), 1500, 6500, 0.0005, 0.0016, skew=2.2,
                   amp_pow=1.5) * 1.3
        x += bp(noise(r, n), 3000, 0.8) * env(n, 0.012, 0.05) * 0.18
        x += lp(thud(n, r.uniform(65, 80), 0.04), 400) * 0.6 * weight
    elif surface == "mud":
        centre0, centre1 = r.uniform(220, 300), r.uniform(650, 900)

        def g(tc, f):
            c = centre0 + (centre1 - centre0) * np.clip(tc / 0.12, 0, 1)
            return g_bp(1.0, 3.0)(f / c) * g_lp(1400, 2)(f)
        x = stft_filter(noise(r, n), g) * env(n, 0.01, 0.06) * 1.2
        x += thud(n, r.uniform(55, 70), 0.05) * 0.8 * weight
        pop = chirp(secs(0.03), 300, r.uniform(800, 1100), 0.012) * 0.25
        mix(x, pop, r.uniform(0.1, 0.15))
    elif surface == "gravel":
        x = grains(r, n, r.integers(60, 110), 0.0, r.uniform(0.08, 0.12), 1500, 7000, 0.0008, 0.003, skew=2.0,
                   amp_pow=2.5) * 2.0
        x += bp(noise(r, n), 3000, 1.0) * env(n, 0.003, 0.03) * 0.15
        x += thud(n, r.uniform(80, 100), 0.03) * 0.5 * weight
    elif surface == "planks":
        f0 = r.uniform(160, 200)
        x = modes(r, n, [f0, f0 * 2.3, f0 * 3.9, f0 * 5.6], [1.0, 0.5, 0.3, 0.15], [0.07, 0.04, 0.02, 0.012])
        x += hp(burst(r, n, 0.002), 800) * 0.18
        x += thud(n, r.uniform(95, 110), 0.03) * 0.6 * weight
    elif surface == "straw":
        am = np.clip(ctrl(r, n, 90, -0.4, 1.0), 0, None) ** 2
        x = bp(noise(r, n), 3200, 0.5) * env(n, 0.012, 0.07) * am * 0.9
        x += lp(thud(n, 90, 0.025), 300) * 0.25 * weight
    elif surface == "heel":
        x = hp(burst(r, n, 0.0008), 3000) * 0.6
        x += modes(r, n, [r.uniform(2800, 3800), r.uniform(1100, 1400)], [0.45, 0.6], [0.008, 0.015])
        x += thud(n, 150, 0.015) * 0.2
    elif surface == "boot":
        x = thud(n, r.uniform(70, 85), 0.045, 0.5) * 1.0 * weight
        x += modes(r, n, [r.uniform(1300, 1900), r.uniform(2400, 3000)], [0.45, 0.25], [0.018, 0.01])
        x += hp(burst(r, n, 0.0015), 1500) * 0.35
        x += grains(r, n, 5, 0.002, 0.02, 3000, 6000, 0.002, 0.006) * 0.4    # hobnails
    elif surface == "bare":
        x = bp(burst(r, n, 0.003), 1500, 0.7) * 0.5
        x += lp(thud(n, 110, 0.02), 300) * 0.8
    else:
        raise ValueError(surface)
    return x


SURFACES = ["cobbles", "flags", "snow", "mud", "gravel", "planks", "straw"]
SHOES = ["shoe", "boot", "bare"]
STEP_VARIANTS = 10
# toe / roll layer: band centre (Hz), q, level, decay (s) per surface
ROLL = {"cobbles": (2600, 1.1, 0.40, 0.030), "flags": (1800, 1.0, 0.35, 0.028), "snow": (3000, 0.8, 0.30, 0.060),
        "mud": (900, 1.2, 0.45, 0.050), "gravel": (3400, 0.9, 0.30, 0.045), "planks": (1500, 1.0, 0.30, 0.030),
        "straw": (3200, 0.7, 0.55, 0.070)}
# heel thud per shoe: (f lo, f hi, decay s, level)
HEEL = {"boot": (62, 82, 0.024, 1.0), "shoe": (80, 105, 0.018, 0.8), "bare": (95, 120, 0.014, 0.6)}


def _heel_layer(r, n, surface, shoe):
    """Heel strike: a short low thud (60-120 Hz, fast decay) plus the surface's own contact sound."""
    f_lo, f_hi, tau, lvl = HEEL[shoe]
    soft = surface in ("snow", "mud", "straw")
    th = thud(n, r.uniform(f_lo, f_hi), tau * (1.6 if soft else 1.0), 0.35, 0.002 if soft else 0.0008) * lvl
    th += lp(burst(r, n, 0.006), 350) * 0.35 * lvl
    hard_k = {"boot": 1.0, "shoe": 0.7, "bare": 0.25}[shoe]
    x = np.zeros(n)
    if surface == "cobbles":
        x += hp(burst(r, n, 0.0009), 2200) * 0.8 * hard_k
        x += modes(r, n, [r.uniform(1800, 3200), r.uniform(3300, 4600), r.uniform(1100, 1500)], [0.5, 0.25, 0.25],
                   [0.016, 0.009, 0.02]) * hard_k
        x += grains(r, n, r.integers(8, 15), 0.03, 0.05, 2000, 6000, 0.0008, 0.0025) * 0.5        # grit tail
    elif surface == "flags":
        x += bp(burst(r, n, 0.004), 1400, 0.6) * 1.1 * max(hard_k, 0.75)                         # clean slap
        x += modes(r, n, [r.uniform(900, 1300)], [0.15], [0.022]) * hard_k
    elif surface == "snow":
        x += grains(r, n, r.integers(130, 200), 0.004, r.uniform(0.10, 0.14), 1500, 6000, 0.0005, 0.0015,
                    skew=2.6, amp_pow=1.5) * 0.7
        th = lp(th, 300) * 0.7            # snow swallows the heel
    elif surface == "mud":
        c0, c1 = r.uniform(230, 300), r.uniform(650, 850)

        def g(tc, f):
            return g_bp(1.0, 3.0)(f / (c0 + (c1 - c0) * np.clip(tc / 0.1, 0, 1))) * g_lp(1500, 2)(f)
        x += stft_filter(noise(r, n), g) * env(n, 0.008, 0.05) * 1.0
        mix(x, chirp(secs(0.03), 380, r.uniform(900, 1200), 0.01) * 0.3, r.uniform(0.15, 0.2))      # suction pop
    elif surface == "gravel":
        x += grains(r, n, r.integers(50, 90), 0.0, r.uniform(0.08, 0.11), 1800, 7000, 0.0006, 0.0025, skew=2.8,
                    amp_pow=2.2) * (0.6 if shoe == "bare" else 0.9)
    elif surface == "planks":
        f0 = r.uniform(150, 250)
        x += modes(r, n, [f0, f0 * 2.4, f0 * 3.9], [0.7, 0.3, 0.12], [0.07, 0.035, 0.018]) * max(hard_k, 0.4)
        x += hp(burst(r, n, 0.0015), 1000) * 0.3 * hard_k
    elif surface == "straw":
        am = np.clip(ctrl(r, n, 90, -0.3, 1.0), 0, None) ** 2
        x += bp(noise(r, n), 3200, 0.5) * env(n, 0.01, 0.07) * am * 0.8
    if shoe == "boot" and surface in ("cobbles", "flags", "gravel"):
        x += grains(r, n, 4, 0.001, 0.015, 3000, 6000, 0.002, 0.006) * 0.35                     # hobnails
    if shoe == "bare" and surface in ("cobbles", "flags", "planks"):
        x += bp(burst(r, n, 0.003), 1500, 0.8) * 0.7                                             # skin slap
    return th + x


def _roll_layer(r, n, surface, shoe):
    """Toe / roll: a brighter scuff (1-4 kHz) shaped by the surface."""
    c, q, lvl, tau = ROLL[surface]
    c *= r.uniform(0.85, 1.15) * (0.8 if shoe == "bare" else 1.0)
    x = bp(noise(r, n), c, q) * env(n, 0.006, tau) * lvl
    if surface == "snow" and r.uniform() < 0.5:                  # dry-cold squeak
        m = secs(0.045)
        f = curve(m, [(0, r.uniform(1500, 1800)), (0.045, r.uniform(2000, 2400))])
        sq = np.sin(TAU * np.cumsum(f) / SR) + 0.4 * np.sin(2 * TAU * np.cumsum(f) / SR)
        mix(x, sq * np.hanning(m) * 0.12, 0.01)
    if surface == "gravel":
        x += grains(r, n, 25, 0.0, 0.05, 2000, 6000) * 0.3
    if surface == "planks" and r.uniform() < 0.25:
        mix(x, _creak(r, 0.18, (140, 200)) * 0.12, 0.02)
    return x * {"bare": 0.6, "shoe": 1.0, "boot": 1.1}[shoe]


def footstep(r, surface, shoe):
    soft = surface in ("snow", "mud", "straw")
    n = secs(0.42 if soft else 0.3)
    out = _heel_layer(r, n, surface, shoe)
    roll_at = r.uniform(0.045, 0.08) * (1.15 if shoe == "boot" else 1.0)
    mix(out, _roll_layer(r, secs(0.2), surface, shoe), roll_at)
    return out


for _s in SURFACES:
    for _sh in SHOES:
        snd("step_%s_%s" % (_s, _sh), n=STEP_VARIANTS, cat="step",
            desc="%s on %s: heel thud + %s roll" % (_sh, _s, _s))(lambda r, i, s=_s, sh=_sh: footstep(r, s, sh))


@snd("scuff", n=6, desc="shoe scuffing on stone when turning or sneaking")
def _scuff(r, i):
    n = secs(0.26)
    c0, c1 = r.uniform(1800, 2600), r.uniform(700, 1100)

    def g(tc, f):
        c = c0 + (c1 - c0) * np.clip(tc / 0.2, 0, 1)
        return g_bp(1.0, 1.5)(f / c)
    x = stft_filter(noise(r, n), g) * env_pts(n, [(0, 0), (0.04, 1), (0.12, 0.6), (0.25, 0)])
    return x + grains(r, n, 25, 0.02, 0.2, 2000, 6000) * 0.4


@snd("scuff_snow", n=4, desc="foot sliding in snow, mud or straw")
def _scuff_snow(r, i):
    n = secs(0.3)
    x = grains(r, n, 220, 0.0, 0.26, 1500, 6000, 0.0005, 0.0015, skew=1.3, amp_pow=1.5)
    return x + bp(noise(r, n), 2500, 0.7) * env_pts(n, [(0, 0), (0.05, 0.25), (0.28, 0)])


@snd("drag", n=4, desc="body dragging over the ground (prone crawl): long cloth-on-stone scrape")
def _drag(r, i):
    n = secs(0.7)
    c = curve(n, [(0, 700), (0.35, 1200), (0.7, 800)])

    def g(tc, f):
        idx = np.clip((tc[:, 0] * SR).astype(int), 0, n - 1)
        return g_bp(1.0, 0.9)(f / c[idx][:, None])
    x = stft_filter(noise(r, n), g) * env_pts(n, [(0, 0), (0.12, 1), (0.5, 0.7), (0.7, 0)])
    x *= 0.7 + 0.3 * np.abs(ctrl(r, n, 25))
    return x + grains(r, n, 30, 0.05, 0.6, 1500, 5000, skew=1.0) * 0.3


@snd("cloth_rustle", n=6, desc="coat and cloth rustle on the player's movement")
def _rustle(r, i):
    n = secs(r.uniform(0.25, 0.4))
    am = np.clip(ctrl(r, n, 60, -0.2, 1.0), 0, None) ** 1.5
    x = bp(noise(r, n), r.uniform(1800, 3000), 0.6) * am
    return x * env_pts(n, [(0, 0), (0.05, 1), (n / SR * 0.7, 0.6), (n / SR, 0)])


@snd("coat_swish", n=4, desc="coat tails swishing on a sprint")
def _swish(r, i):
    n = secs(0.3)
    c = curve(n, [(0, 600), (0.15, 1600), (0.3, 900)])

    def g(tc, f):
        idx = np.clip((tc[:, 0] * SR).astype(int), 0, n - 1)
        return g_bp(1.0, 1.3)(f / c[idx][:, None])
    return stft_filter(noise(r, n), g) * np.hanning(n)


# ====================================================================== horses and vehicles

def _hoof(r, weight=1.0, soft=False, click=1.0):
    n = secs(0.25)
    x = modes(r, n, [r.uniform(600, 720), r.uniform(780, 900), r.uniform(1150, 1400)], [1.0, 0.7, 0.35],
              [0.035, 0.028, 0.015])
    x += bp(burst(r, n, 0.004), r.uniform(650, 850), 2.5) * 0.9          # the hollow of the hoof wall
    x += thud(n, r.uniform(90, 110), 0.05) * 0.8 * weight
    if soft:
        x = lp(x, 500)
        def g(tc, f):
            return g_bp(1.0, 2.5)(f / (250 + 500 * np.clip(tc / 0.1, 0, 1)))
        x += stft_filter(noise(r, n), g) * env(n, 0.01, 0.05) * 0.8
    else:
        x += hp(burst(r, n, 0.001), 1800) * 0.25 * click
        x += modes(r, n, [r.uniform(2700, 3300)], [0.08 * click], [0.018])
    return x


@snd("hoof_walk", n=8, desc="walking hoof on cobbles: impact + hollow horn resonance, two-part clop")
def _hoof_walk(r, i):
    out = np.zeros(secs(0.32))
    mix(out, _hoof(r), 0.0)
    mix(out, _hoof(r, 0.7), r.uniform(0.05, 0.08), r.uniform(0.45, 0.65))    # hind hoof follows the fore
    return out


@snd("hoof_trot", n=8, desc="trotting hoof: single sharp clop with a flam")
def _hoof_trot(r, i):
    out = np.zeros(secs(0.28))
    mix(out, _hoof(r, 1.1, click=1.3), 0.0)
    mix(out, _hoof(r, 0.9, click=1.1), r.uniform(0.02, 0.035), 0.6)     # the diagonal pair, a hair apart
    return out


@snd("hoof_soft", n=3, desc="hoof in mud or snow: dull thud and squelch")
def _hoof_soft(r, i):
    out = np.zeros(secs(0.3))
    mix(out, _hoof(r, soft=True), 0.0)
    mix(out, _hoof(r, 0.7, soft=True), r.uniform(0.03, 0.05), 0.5)
    return out


@snd("horse_stamp", n=2, desc="tethered horse stamping and scraping a hoof")
def _stamp(r, i):
    out = np.zeros(secs(0.6))
    mix(out, _hoof(r, 1.8, click=1.4), 0.0)
    mix(out, _scuff(r, 0) * 0.5, 0.12)
    return out


def _clack(r, big=1.0):
    n = secs(0.2)
    x = hp(burst(r, n, 0.002), 700) * 0.5
    x += modes(r, n, [r.uniform(350, 500), r.uniform(900, 1300), r.uniform(2000, 2600)], [0.6, 0.4, 0.2],
               [0.02, 0.012, 0.006])
    x += thud(n, r.uniform(60, 75), 0.03 + 0.03 * big) * 0.7 * big
    return x


def _creak(r, dur=0.4, f=(90, 140)):
    n = secs(dur)
    rate = curve(n, [(0, f[0]), (dur * 0.5, f[1]), (dur, f[0] * 1.1)]) * (1 + 0.1 * ctrl(r, n, 20))
    src = saw(rate)
    x = bp(src, r.uniform(450, 600), 3) + bp(src, r.uniform(1100, 1400), 4) * 0.6
    return x * np.sin(np.linspace(0, math.pi, n)) ** 1.5


@snd("wheel_loop", loop=True, fmt="ogg", desc="iron-tyred wheels on cobbles at 2 m/s: rumble, felloe-joint clacks locked to each wheel's rotation (front 3 turns, rear 2 turns per loop), sett bumps, rattle, creak (4.71 s loop)")
def _wheel_loop(r, i):
    speed = 2.0
    front_c, rear_c = TAU * 0.5, TAU * 0.75            # tyre circumferences (m)
    L, xf = 3 * front_c / speed, 0.25                   # = 2 * rear_c / speed: both wheels come round together
    n = secs(L + xf)
    x = lp(noise(r, n, -6), 150) * 0.45 * (0.8 + 0.2 * ctrl(r, n, 6))
    bumps = np.zeros(n)
    for circ, joints, lvl, pan_off in [(front_c, 6, 0.8, 0.0), (rear_c, 7, 1.0, 0.11)]:
        per = circ / speed
        # each felloe joint / tyre weld strikes at the same point of every turn, with its own weight and timbre
        spots = [(k / joints + r.uniform(-0.03, 0.03), r.uniform(0.35, 1.0), int(r.integers(0, 1 << 30))) for k in range(joints)]
        turn = 0
        while turn * per < L + xf:
            for ph, g, seed in spots:
                t = pan_off + (turn + ph) * per
                if 0 <= t < L + xf:
                    rr = np.random.default_rng(seed)
                    mix(x, _clack(rr, 0.5) * g * lvl * 0.8, t)
                    mix(bumps, np.exp(-tt(secs(0.08)) / 0.03) * g, t)
            turn += 1
    for _ in range(r.poisson(2 * L)):
        t = r.uniform(0, L + xf)
        mix(x, _clack(r, 1.5) * r.uniform(0.5, 1.0), t)
        mix(bumps, np.exp(-tt(secs(0.2)) / 0.06) * 1.3, t)
    rattle = bp(noise(r, n), 1600, 1.0) * lp(bumps + 0.3 * np.abs(ctrl(r, n, 12)), 25, 1)
    x += rattle * 0.3
    for _ in range(2):
        mix(x, _creak(r, 0.35) * 0.1, r.uniform(0, L))
    return loopify(x, secs(L), secs(xf))


@snd("wheel_mud_loop", loop=True, fmt="ogg", desc="wheels in mud and slush: low rumble, squelch and splash (4 s loop)")
def _wheel_mud(r, i):
    L, xf = 4.0, 0.25
    n = secs(L + xf)
    x = lp(noise(r, n, -6), 120) * 0.7 * (0.75 + 0.25 * ctrl(r, n, 3))
    wet = np.zeros(n)
    for _ in range(int(9 * L)):
        t = r.uniform(0, L + xf)
        m = secs(0.15)
        c0 = r.uniform(200, 400)

        def g(tc, f, c0=c0):
            return g_bp(1.0, 3.0)(f / (c0 * (1 + 1.5 * np.clip(tc / 0.1, 0, 1))))
        mix(wet, stft_filter(noise(r, m), g) * env(m, 0.01, 0.04), t, r.uniform(0.2, 0.6))
    x += wet + grains(r, n, 60 * L, 0, L, 600, 2500, 0.002, 0.006, skew=1.0) * 0.3
    return loopify(x, secs(L), secs(xf))


@snd("wheel_clack", n=4, desc="a wheel dropping off a raised sett: clack, thump and body rattle")
def _wheel_clack(r, i):
    n = secs(0.5)
    x = np.zeros(n)
    mix(x, _clack(r, 2.0), 0)
    mix(x, _clack(r, 1.0) * 0.6, r.uniform(0.06, 0.1))
    x += bp(noise(r, n), 1500, 1) * env(n, 0.004, 0.08) * 0.4
    return x


@snd("cart_creak", n=2, desc="axle and body creak of a cart")
def _cart_creak(r, i):
    return _creak(r, r.uniform(0.6, 0.9), (r.uniform(70, 90), r.uniform(130, 170)))


def _bell_hit(r, n, f, amp=1.0, taus=(0.25, 0.12, 0.06)):
    return modes(r, n, [f, f * 2.76, f * 5.40, f * 8.93], [amp, amp * 0.4, amp * 0.2, amp * 0.08],
                 [taus[0], taus[1], taus[2], taus[2] * 0.6])


@snd("harness_jingle", n=4, desc="harness bells and buckles jostling: small inharmonic bells")
def _jingle(r, i):
    n = secs(0.9)
    x = np.zeros(n)
    fs = r.uniform(2300, 3600, 4)
    for _ in range(r.integers(6, 11)):
        mix(x, _bell_hit(r, secs(0.6), fs[r.integers(0, 4)], r.uniform(0.3, 1.0)), 0.3 * r.beta(1.2, 2.5))
    x += grains(r, n, 12, 0.0, 0.3, 1500, 4000, 0.002, 0.005) * 0.4
    return x


# ---------------------------------------------------------------- horse voice

@snd("horse_whinny", n=2, desc="whinny: rising then falling squeal with a fast tremolo")
def _whinny(r, i):
    d = 1.7
    n = secs(d)
    pk = r.uniform(1000, 1250)
    f0 = curve(n, [(0, 520), (0.1, pk), (0.5, pk * 0.8), (1.2, 480), (1.45, 300), (d, 240)])
    f0 *= 1 + 0.06 * np.sin(TAU * r.uniform(10, 13) * tt(n))
    trk = lambda ts: np.repeat(np.array([[(1000, 350, 0), (2200, 450, -8), (3500, 600, -16)]], float), len(ts), 0)
    v = additive_voice(f0, trk, -8, 8000)
    am = 0.75 + 0.25 * np.sin(TAU * 11 * tt(n))
    e = env_pts(n, [(0, 0), (0.05, 1), (1.1, 0.8), (1.5, 0.35), (d, 0)])
    breath = noisy_formant(r, n, trk) * 0.25
    return (v * am + breath) * e


@snd("horse_snort", n=3, desc="snort: noisy blow with a lip flutter")
def _snort(r, i):
    d = r.uniform(0.5, 0.75)
    n = secs(d)
    fl = r.uniform(28, 40)
    am = (0.5 + 0.5 * np.sin(TAU * fl * tt(n))) ** 2
    x = lp(noise(r, n), 1300) * (0.4 + 0.6 * am)
    x += lp(pulse_train(r, n, fl, 0.006), 300) * 0.8
    return x * env(n, 0.02, d * 0.35)


@snd("coachman_hoo", n=2, desc='coachman calling "Hooo!" to the horses (non-verbal)')
def _hoo(r, i):
    d = 1.1 if i == 0 else 1.2
    n = secs(d)
    if i == 0:
        f0 = curve(n, [(0, 125), (0.12, 150), (0.7, 128), (d, 105)])
        trk = vowel_track([(0, "u"), (0.25, "o"), (d, "o")])
        e = env_pts(n, [(0, 0), (0.06, 1), (0.8, 0.8), (d, 0)])
    else:
        f0 = curve(n, [(0, 140), (0.1, 160), (0.35, 150), (0.45, 120), (0.55, 165), (d, 120)])
        trk = vowel_track([(0, "u"), (0.3, "o"), (0.45, "u"), (0.6, "o"), (d, "o")])
        e = env_pts(n, [(0, 0), (0.05, 1), (0.36, 0.9), (0.45, 0.25), (0.52, 1), (1.0, 0.7), (d, 0)])
    f0 *= vibrato(n, 5.0, 0.015, 0.2, r)
    v = additive_voice(f0, trk, -8, 5000)
    h = noisy_formant(r, n, trk) * env_pts(n, [(0, 1), (0.08, 0.1), (d, 0.05)]) * 0.4
    return (v + h) * e


# ====================================================================== dogs, cats, birds

def _bark(r, size=1.0):
    d = r.uniform(0.16, 0.22)
    n = secs(d + 0.05)
    p = r.uniform(0.9, 1.1) / size
    f0 = curve(n, [(0, 330 * p), (0.03, 600 * p), (d * 0.6, 420 * p), (d, 250 * p)])
    f0 *= 1 + 0.03 * ctrl(r, n, 150)
    fs = 0.9 / size ** 0.5
    trk = lambda ts: np.repeat(np.array([[(900 * fs, 250, 0), (1800 * fs, 350, -5), (3200 * fs, 500, -14)]]), len(ts), 0)
    v = additive_voice(f0, trk, -7, 7000)
    x = v + noisy_formant(r, n, trk) * 0.6
    return x * env_pts(n, [(0, 0), (0.006, 1), (d * 0.5, 0.7), (d, 0), (d + 0.05, 0)])


@snd("dog_bark", n=4, desc="bark: pitched noise burst with formants (1-3 woofs)")
def _dog_bark(r, i):
    size = [1.0, 0.8, 1.25, 1.0][i]
    out = np.zeros(secs(1.1))
    t = 0.0
    for _ in range([1, 2, 2, 3][i]):
        mix(out, _bark(r, size), t)
        t += r.uniform(0.22, 0.34)
    return out


@snd("dog_bark_far", n=2, fmt="ogg", desc="dogs barking far off across the city (lowpassed, reverberant)")
def _bark_far(r, i):
    out = np.zeros(secs(3.2))
    t = 0.1
    for _ in range(r.integers(3, 6)):
        mix(out, _bark(r, r.uniform(0.8, 1.2)), t, r.uniform(0.5, 1.0))
        t += r.uniform(0.3, 0.7)
    out = lp(out, 1100)
    return fit(reverb(out, 2.5, 0.6, 0.05, 2500), secs(3.2))


@snd("dog_growl", n=2, desc="low growl: jittery pulses through a nasal formant")
def _growl(r, i):
    d = 1.3
    n = secs(d)
    f0 = r.uniform(85, 100) * (1 + 0.08 * ctrl(r, n, 30))
    src = saw(f0, 0.05 * ctrl(r, n, 200))
    x = bp(src, 500, 2.5) + bp(src, 1300, 3) * 0.4
    am = 0.6 + 0.4 * np.abs(ctrl(r, n, 25))
    return x * am * env_pts(n, [(0, 0), (0.2, 1), (1.0, 0.9), (d, 0)])


@snd("dog_pant", n=1, desc="panting: breathy in-out bursts")
def _pant(r, i):
    d = 1.6
    n = secs(d)
    cyc = np.sin(math.pi * ((tt(n) * 3.4) % 1.0)) ** 2
    x = noisy_formant(r, n, lambda ts: np.repeat(np.array([[(1000, 400, 0), (2200, 600, -6)]]), len(ts), 0))
    return x * cyc * env_pts(n, [(0, 0), (0.1, 1), (1.4, 1), (d, 0)])


@snd("cat_meow", n=3, desc='meow: "mi-a-ow" pitch and vowel sweep')
def _meow(r, i):
    d = r.uniform(0.7, 0.95)
    n = secs(d)
    p = r.uniform(0.9, 1.15)
    f0 = curve(n, [(0, 480 * p), (0.15, 760 * p), (0.45 * d / 0.8, 690 * p), (d, 420 * p)])
    f0 *= vibrato(n, 7, 0.02, 0.1, r)
    trk = vowel_track([(0, "i"), (0.2, "a"), (0.55 * d, "a"), (d, "u")], 1.65)
    v = additive_voice(f0, trk, -9, 8000)
    return (v + noisy_formant(r, n, trk) * 0.12) * env_pts(n, [(0, 0), (0.04, 0.8), (0.2, 1), (d * 0.8, 0.8), (d, 0)])


@snd("cat_purr", loop=True, desc="purr: low pulses at ~26 Hz, inhale and exhale (1.6 s loop)")
def _purr(r, i):
    L, xf = 1.6, 0.1
    n = secs(L + xf)
    x = np.zeros(n)
    t = 0.0
    while t < L + xf:
        ph = (t % 0.8) / 0.8
        rate = 25 if t % 1.6 < 0.8 else 27
        mix(x, lp(burst(r, secs(0.03), 0.008), 700) * (0.5 + 0.5 * math.sin(math.pi * ph)), t)
        t += 1 / rate
    return loopify(x, secs(L), secs(xf))


@snd("pigeon_coo", n=3, desc='pigeon "croo-croo-coo": soft low hum with bumps')
def _coo(r, i):
    d = 1.2
    n = secs(d)
    b = r.uniform(230, 280)
    f0 = curve(n, [(0, b), (0.2, b * 1.05), (0.3, b * 0.95), (0.45, b * 1.18), (0.6, b), (0.9, b * 1.08), (d, b * 0.9)])
    trk = lambda ts: np.repeat(np.array([[(420, 220, 0), (900, 350, -20)]]), len(ts), 0)
    v = additive_voice(f0, trk, -16, 3000) * (1 + 0.15 * np.sin(TAU * 30 * tt(n)))
    e = env_pts(n, [(0, 0), (0.05, 0.7), (0.22, 0.6), (0.27, 0.1), (0.33, 0.8), (0.52, 0.7), (0.58, 0.1),
                    (0.66, 1.0), (1.05, 0.7), (d, 0)])
    return v * e


@snd("pigeon_flap", n=2, desc="wing flaps of a pigeon taking off, with a wing clap")
def _flap(r, i):
    d = 0.9
    n = secs(d)
    x = np.zeros(n)
    t = 0.0
    k = 0
    rate = r.uniform(9, 11)
    while t < d - 0.1:
        m = secs(0.08)
        f = bp(noise(r, m), r.uniform(700, 1500), 0.8) * env(m, 0.01, 0.03) * (1.0 - 0.6 * t / d)
        mix(x, f, t)
        if k == 0:
            mix(x, hp(burst(r, secs(0.04), 0.003), 1000) * 0.8, t)
        t += 1 / rate
        k += 1
    return x


def _caw(r, d=0.32):
    n = secs(d)
    b = r.uniform(520, 680)
    f0 = curve(n, [(0, b * 0.9), (0.05, b), (d, b * 0.8)]) * (1 + 0.08 * ctrl(r, n, 120))
    trk = lambda ts: np.repeat(np.array([[(1300, 450, 0), (2400, 600, -4), (3600, 700, -12)]]), len(ts), 0)
    v = additive_voice(f0, trk, -6, 7000) + additive_voice(f0 * 0.5, trk, -6, 4000) * 0.35
    return (v + noisy_formant(r, n, trk) * 0.9) * env_pts(n, [(0, 0), (0.02, 1), (d * 0.7, 0.8), (d, 0)])


@snd("crow_caw", n=3, desc="crow: harsh noisy caws with subharmonics")
def _crow(r, i):
    out = np.zeros(secs(1.6))
    t = 0.0
    for _ in range(r.integers(2, 4)):
        mix(out, _caw(r), t)
        t += r.uniform(0.4, 0.5)
    return out


@snd("hawk_cry", n=2, fmt="ogg", desc='hawk: descending "kee-eeer"')
def _hawk(r, i):
    d = 1.0
    n = secs(d + 0.6)
    out = np.zeros(n)
    for k, (at, dd) in enumerate([(0.0, d), (d + 0.1, 0.4)]):
        m = secs(dd)
        f0 = curve(m, [(0, 2500), (0.12 * dd, 3000), (dd, 1800)]) * (1 + 0.02 * ctrl(r, m, 60))
        trk = lambda ts: np.repeat(np.array([[(3000, 1500, 0)]]), len(ts), 0)
        v = additive_voice(f0, trk, -6, 10000) + noisy_formant(r, m, trk) * 0.3
        mix(out, v * env_pts(m, [(0, 0), (0.03, 1), (dd * 0.7, 0.7), (dd, 0)]), at, 1.0 if k == 0 else 0.6)
    return fit(reverb(out, 1.6, 0.3, 0.03), n)


@snd("owl_hoot", n=2, fmt="ogg", desc='tawny owl: "hoo ... hu, hu-hoooo"')
def _owl(r, i):
    d = 3.6
    n = secs(d)
    out = np.zeros(n)
    b = r.uniform(380, 440)
    trk = lambda ts: np.repeat(np.array([[(420, 160, 0), (900, 300, -26)]]), len(ts), 0)
    for at, dd, qv in [(0.0, 0.45, 0), (1.6, 0.12, 0), (1.9, 0.9, 1)]:
        m = secs(dd)
        f0 = curve(m, [(0, b * 0.95), (0.05, b), (dd, b * 0.9)])
        v = additive_voice(f0, trk, -24, 2500)
        if qv:
            v *= 0.7 + 0.3 * np.sin(TAU * 18 * tt(m))
        mix(out, v * env_pts(m, [(0, 0), (min(0.05, dd / 3), 1), (dd * 0.8, 0.8), (dd, 0)]), at)
    return fit(reverb(out, 2.0, 0.35, 0.03, 3000), n)


# ====================================================================== people

@snd("laugh", n=2, desc='laughter: breathy "ha-ha-ha" (a man, a woman)')
def _laugh(r, i):
    b = 210 if i == 0 else 320
    out = np.zeros(secs(1.5))
    t = 0.0
    k = r.integers(5, 8)
    for j in range(k):
        m = secs(0.13)
        f0 = np.full(m, b * (1 - 0.04 * j)) * (1 + np.linspace(0.05, -0.08, m))
        trk = vowel_track([(0, "a"), (0.13, "a")], 1.0 if i == 0 else 1.16)
        v = additive_voice(f0, trk, -10, 5000) * env_pts(m, [(0, 0), (0.03, 1), (0.13, 0)])
        h = noisy_formant(r, m, trk) * env_pts(m, [(0, 0.8), (0.035, 0.1), (0.13, 0)]) * 0.6
        mix(out, v + h, t, 1 - 0.07 * j)
        t += r.uniform(0.15, 0.19)
    return out


@snd("cough", n=3, desc="a cough from a window or a doorway")
def _cough(r, i):
    out = np.zeros(secs(0.8))
    for k, at in enumerate([0.0, r.uniform(0.22, 0.3)]):
        m = secs(0.25)
        x = bp(noise(r, m), r.uniform(700, 1100), 0.5) * env(m, 0.004, 0.06)
        f0 = curve(m, [(0, 170), (0.08, 120)])
        v = additive_voice(f0, vowel_track([(0, "y"), (0.25, "y")]), -10, 4000) * env(m, 0.003, 0.04)
        mix(out, x + v * 0.5, at, 1.0 if k == 0 else 0.6)
    return out


@snd("baby_cry", n=2, fmt="ogg", desc="a baby crying in a tenement: waah with in-breaths")
def _baby(r, i):
    d = 3.2
    out = np.zeros(secs(d))
    t = 0.05
    while t < d - 0.6:
        cd = r.uniform(0.6, 0.9)
        m = secs(cd)
        b = r.uniform(400, 470)
        f0 = curve(m, [(0, b * 0.9), (0.1, b * 1.1), (cd * 0.7, b), (cd, b * 0.8)]) * vibrato(m, 6, 0.03, 0.1, r)
        trk = vowel_track([(0, "e"), (0.12, "a"), (cd, "e")], 1.6)
        v = additive_voice(f0, trk, -8, 9000) + noisy_formant(r, m, trk) * 0.3
        mix(out, v * env_pts(m, [(0, 0), (0.05, 1), (cd * 0.8, 0.8), (cd, 0)]), t)
        t += cd + 0.08
        m2 = secs(0.14)
        mix(out, hp(noise(r, m2), 1500) * np.hanning(m2) * 0.15, t)
        t += r.uniform(0.2, 0.3)
    return out


@snd("hiccup", n=3, desc='drunk\'s "hic"')
def _hiccup(r, i):
    n = secs(0.22)
    m = secs(0.07)
    f0 = curve(m, [(0, 280 * r.uniform(0.85, 1.15)), (0.07, 220)])
    v = additive_voice(f0, vowel_track([(0, "i"), (0.07, "i")]), -8, 5000) * env(m, 0.002, 0.03)
    out = np.zeros(n)
    mix(out, hp(burst(r, secs(0.02), 0.003), 800) * 0.5, 0.0)
    mix(out, v, 0.004)
    return out


@snd("snore", n=2, desc="snoring drunk: fluttering inhale, breathy exhale")
def _snore(r, i):
    d = 2.6
    n = secs(d)
    out = np.zeros(n)
    m = secs(1.1)
    fl = r.uniform(26, 34)
    src = lp(pulse_train(r, m, fl, 0.008), 900) + lp(noise(r, m), 600) * 0.3
    trk = lambda ts: np.repeat(np.array([[(320, 160, 0), (900, 300, -8)]]), len(ts), 0)
    ins = stft_filter(src, lambda tc, f: formant_gain(f, trk(tc[:, 0])))
    mix(out, ins * env_pts(m, [(0, 0), (0.3, 1), (0.9, 1), (1.1, 0)]), 0.0)
    m2 = secs(1.0)
    mix(out, bp(noise(r, m2), 900, 0.7) * env_pts(m2, [(0, 0), (0.15, 0.35), (1.0, 0)]), 1.35)
    return out


@snd("grunt", n=4, desc="grunts and cries of pain in a fight")
def _grunt(r, i):
    d = r.uniform(0.15, 0.3)
    n = secs(d)
    b = r.uniform(100, 130) * (1.6 if i == 3 else 1.0)
    f0 = curve(n, [(0, b * 1.1), (d, b * 0.85)]) * (1 + 0.04 * ctrl(r, n, 90))
    trk = vowel_track([(0, "y" if i % 2 else "a"), (d, "y")])
    v = additive_voice(f0, trk, -8, 5000) + noisy_formant(r, n, trk) * 0.35
    return v * env_pts(n, [(0, 0), (0.015, 1), (d * 0.6, 0.7), (d, 0)])


@snd("punch", n=4, desc="blow landing: low thud, cloth slap")
def _punch(r, i):
    n = secs(0.25)
    x = thud(n, r.uniform(70, 95), 0.05, 0.6) * 1.0
    x += bp(burst(r, n, 0.006), r.uniform(900, 1600), 0.8) * 0.3
    x += bp(noise(r, n), 3000, 0.5) * env(n, 0.01, 0.04) * 0.06
    return x


@snd("body_fall", n=2, desc="a body hitting the cobbles")
def _fall(r, i):
    n = secs(0.8)
    x = np.zeros(n)
    mix(x, thud(secs(0.4), r.uniform(55, 65), 0.09, 0.5) * 1.0 + bp(burst(r, secs(0.4), 0.02), 900, 0.7) * 0.5, 0)
    mix(x, thud(secs(0.3), 75, 0.05) * 0.5 + _impact(r, "cobbles")[:secs(0.3)] * 0.3, r.uniform(0.12, 0.2))
    x += bp(noise(r, n), 2500, 0.6) * env_pts(n, [(0, 0), (0.05, 0.2), (0.6, 0)])
    return x


@snd("lash", n=3, desc="the flogging: whoosh, whip crack, smack")
def _lash(r, i):
    n = secs(0.6)
    x = np.zeros(n)
    m = secs(0.28)

    def g(tc, f):
        return g_bp(1.0, 1.4)(f / (500 + 2500 * np.clip(tc / 0.25, 0, 1) ** 2))
    mix(x, stft_filter(noise(r, m), g) * env_pts(m, [(0, 0), (0.24, 0.5), (0.28, 0)]), 0)
    mix(x, hp(burst(r, secs(0.05), 0.0015), 2000) * 1.3, 0.27)
    mix(x, thud(secs(0.12), 180, 0.02) * 0.4 + bp(burst(r, secs(0.12), 0.008), 1500, 0.7) * 0.5, 0.275)
    return x


def _snare(r, amp=1.0):
    n = secs(0.2)
    x = bp(noise(r, n), 4500, 0.7) * env(n, 0.001, 0.07) * 0.8
    x += modes(r, n, [r.uniform(190, 210), 330], [0.8, 0.3], [0.05, 0.03])
    return x * amp


@snd("drum_roll", n=1, fmt="ogg", desc="side drum: a roll (crescendo) for the sentence")
def _drum_roll(r, i):
    d = 2.6
    out = np.zeros(secs(d + 0.3))
    t = 0.0
    while t < d:
        mix(out, _snare(r, 0.35 + 0.65 * t / d) * r.uniform(0.8, 1.0), t)
        t += 1 / 17 * (1 + r.uniform(-0.1, 0.1))
    mix(out, _snare(r, 1.5), d)
    return out


@snd("drum_beat", n=2, desc="side drum: measured march beats")
def _drum_beat(r, i):
    out = np.zeros(secs(2.2))
    pat = [0, 0.5, 1.0, 1.25, 1.5] if i == 0 else [0, 0.25, 0.5, 1.0, 1.5, 1.75]
    for k, at in enumerate(pat):
        mix(out, _snare(r, 1.0 if k == 0 else 0.7), at * 1.1)
    return out


@snd("drunk_song", n=2, fmt="ogg", desc='drunk singing "la-la-la", off key')
def _song(r, i):
    d = 3.2
    out = np.zeros(secs(d))
    base = r.uniform(130, 160)
    scale = [0, 2, 4, 5, 7, 9, 7, 4]
    t = 0.0
    k = 0
    while t < d - 0.3:
        nd = r.choice([0.25, 0.35, 0.5, 0.7])
        m = secs(nd)
        semi = scale[(k * 3 + r.integers(0, 3)) % len(scale)] + r.uniform(-0.4, 0.4)
        f0 = np.full(m, base * 2 ** (semi / 12)) * vibrato(m, 5.5, 0.02, 0.1, r)
        trk = vowel_track([(0, "y"), (0.04, "a"), (nd, "o" if k % 3 == 2 else "a")])
        v = additive_voice(f0, trk, -9, 5000)
        mix(out, v * env_pts(m, [(0, 0), (0.03, 0.4), (0.06, 1), (nd * 0.8, 0.8), (nd, 0)]), t)
        t += nd + 0.02
        k += 1
    return out


@snd("crowd_jeer", n=2, fmt="ogg", desc="crowd jeering and oohing at the pillory / the flogging")
def _jeer(r, i):
    d = 2.8
    n = secs(d)
    x = babble(r, n, 8, 3500, 0.7, 7.0, (0.1, 0.3), (0.6, 1.5), 6, f0_scale=1.25)
    for _ in range(3):
        m = secs(r.uniform(0.5, 0.9))
        f0 = curve(m, [(0, 180), (m / SR, 140)]) * r.uniform(0.8, 1.3)
        mix(x, additive_voice(f0, vowel_track([(0, "o"), (1, "u")]), -9, 4000) * np.hanning(m) * 0.6, r.uniform(0, d - 1))
    return x * env_pts(n, [(0, 0), (0.3, 1), (2.2, 1), (d, 0)])


# ---------------------------------------------------------------- beds

@snd("city_murmur_loop", loop=True, fmt="ogg", cat="bed", desc="distant city murmur: many far voices, a low hum (16 s loop)")
def _murmur(r, i):
    L, xf = 16.0, 1.0
    n = secs(L + xf)
    x = babble(r, n, 22, 1100, 0.6, 5.0, (0.2, 1.2), (1.0, 3.0), 12)
    x = lp(x, 900) + lp(noise(r, n, -6), 180) * 0.25 * rms(x)
    return loopify(x, secs(L), secs(xf))


@snd("crowd_talk_loop", loop=True, fmt="ogg", cat="bed", desc="a knot of people talking: close granular murmur (10 s loop)")
def _crowd(r, i):
    L, xf = 10.0, 0.6
    n = secs(L + xf)
    x = babble(r, n, 6, 3400, 0.6, 5.5, (0.3, 1.4), (0.8, 2.6), 7)
    return loopify(x, secs(L), secs(xf))


def _glass(r, amp=1.0):
    n = secs(0.5)
    f = r.uniform(2400, 3600)
    return modes(r, n, [f, f * 2.32, f * 4.25], [1.0, 0.4, 0.15], [0.12, 0.05, 0.02]) * amp


@snd("tavern_loop", loop=True, fmt="ogg", cat="bed", desc="tavern / beer hall: loud talk, laughter, clinking mugs, a fiddle scrap (12 s loop)")
def _tavern(r, i):
    L, xf = 12.0, 0.8
    n = secs(L + xf)
    x = babble(r, n, 10, 3000, 0.75, 6.0, (0.1, 0.8), (1.0, 3.0), 8, f0_scale=1.08)
    lvl = rms(x)
    for _ in range(int(L * 1.2)):
        mix(x, _glass(r) * lvl * r.uniform(0.6, 1.4), r.uniform(0, L + xf))
    for _ in range(3):
        mix(x, _laugh(r, int(r.integers(0, 2))) * lvl * 3.0, r.uniform(0, L))
    for _ in range(2):
        mix(x, _impact(r, "planks") * lvl * 3.0, r.uniform(0, L))
    # a fiddle phrase from the corner: a sawtooth with vibrato through a body resonance
    fl = secs(3.0)
    notes = [0, 4, 7, 5, 4, 2, 0]
    f0 = np.concatenate([np.full(fl // len(notes), 392 * 2 ** (s / 12)) for s in notes])
    f0 = fit(f0, fl)
    fid = saw(lp(f0, 30, 1) * vibrato(fl, 6, 0.008, 0, r))
    fid = bp(fid, 700, 1.2) + bp(fid, 2500, 1.5) * 0.4
    mix(x, fid * env_pts(fl, [(0, 0), (0.2, 1), (2.7, 1), (3.0, 0)]) * lvl * 0.6, r.uniform(1, L - 4))
    return loopify(x, secs(L), secs(xf))


@snd("prayer_murmur_loop", loop=True, fmt="ogg", cat="bed", desc="low murmur of men at prayer heard from a synagogue door (12 s loop)")
def _prayer(r, i):
    L, xf = 12.0, 0.8
    n = secs(L + xf)
    x = babble(r, n, 7, 1500, 1.0, 4.5, (0.2, 0.8), (2.0, 4.0), 6, f0_scale=0.92, monotone=True)
    return loopify(lp(x, 1400), secs(L), secs(xf))


def _wind(r, n, strength):
    base = noise(r, n, -3)
    lfo1 = ctrl(r, n, 0.12, 0, 1)
    lfo2 = ctrl(r, n, 0.35, 0, 1)
    howl_c = 500 + 700 * lfo1

    def g(tc, f, howl_c=howl_c, lfo1=lfo1):
        idx = np.clip((tc[:, 0] * SR).astype(int), 0, n - 1)
        c = (300 + 600 * lfo1[idx])[:, None]
        body = g_bp(1.0, 0.8)(f / c)
        howl = g_bp(1.0, 7.0)(f / howl_c[idx][:, None]) * (0.6 * strength)
        return (body + howl) * g_lp(2500 + 2000 * strength, 2)(f)
    x = stft_filter(base, g)
    x *= 0.35 + 0.65 * lfo2 ** (1.5 - strength * 0.5)
    x += lp(noise(r, n, -6), 90) * 0.4
    return x


@snd("wind_calm_loop", loop=True, fmt="ogg", cat="bed", desc="light winter wind over the roofs (16 s loop)")
def _wind_calm(r, i):
    L, xf = 16.0, 1.0
    return loopify(_wind(r, secs(L + xf), 0.25), secs(L), secs(xf))


@snd("wind_strong_loop", loop=True, fmt="ogg", cat="bed", desc="strong wind: gusts and a howl in the chimneys (16 s loop)")
def _wind_strong(r, i):
    L, xf = 16.0, 1.0
    return loopify(_wind(r, secs(L + xf), 1.0), secs(L), secs(xf))


@snd("wind_gust", n=2, fmt="ogg", desc="a single gust whistling through a passage")
def _gust(r, i):
    n = secs(3.0)
    return _wind(r, n, 1.0) * env_pts(n, [(0, 0), (1.0, 1), (1.6, 0.8), (3.0, 0)])


@snd("brazier_loop", loop=True, fmt="ogg", desc="brazier / chestnut fire: soft roar and crackle (8 s loop)")
def _brazier(r, i):
    L, xf = 8.0, 0.5
    n = secs(L + xf)
    x = lp(noise(r, n, -4), 450) * 0.25 * (0.7 + 0.3 * ctrl(r, n, 2))
    x += grains(r, n, 90 * L, 0, L + xf, 800, 5000, 0.0005, 0.003, skew=1.0, amp_pow=3.0) * 1.2
    for _ in range(int(L * 1.5)):
        m = secs(0.05)
        mix(x, modes(r, m, [r.uniform(1500, 3500)], [1], [0.006]) + hp(burst(r, m, 0.002), 1000), r.uniform(0, L + xf),
            r.uniform(0.3, 0.9))
    return loopify(x, secs(L), secs(xf))


@snd("grinder_loop", loop=True, fmt="ogg", desc="knife grinder: treadle-driven stone, blade whine and sparks (4 s loop)")
def _grinder(r, i):
    L, xf = 4.0, 0.3
    n = secs(L + xf)
    pedal = 0.5 + 0.5 * np.sin(TAU * 1.25 * tt(n))
    wheel = lp(noise(r, n, -6), 250) * 0.3 * (0.8 + 0.2 * pedal)
    f = 3800 * (1 + 0.06 * pedal + 0.03 * ctrl(r, n, 8))

    def g(tc, fr):
        idx = np.clip((tc[:, 0] * SR).astype(int), 0, n - 1)
        return g_bp(1.0, 14.0)(fr / f[idx][:, None]) + g_bp(1.0, 10.0)(fr / (f[idx][:, None] * 1.52)) * 0.4
    whine = stft_filter(noise(r, n), g) * (0.4 + 0.6 * np.clip(ctrl(r, n, 1.5, 0.2, 1.0), 0, 1)) * 1.5
    spark = grains(r, n, 150 * L, 0, L + xf, 3000, 8000, 0.0005, 0.0015, skew=1.0) * 0.5
    creak = np.zeros(n)
    for k in range(6):
        mix(creak, _creak(r, 0.25, (60, 80)) * 0.15, k / 1.25 + 0.3)
    return loopify(wheel + whine + spark + creak, secs(L), secs(xf))


# ====================================================================== stealth, props, doors

@snd("stone_land", n=3, desc="a thrown stone landing and bouncing on cobbles")
def _stone(r, i):
    n = secs(0.6)
    x = np.zeros(n)
    t = 0.0
    g = 1.0
    for _ in range(r.integers(2, 4)):
        m = secs(0.1)
        hit = hp(burst(r, m, 0.001), 2000) * 0.6 + modes(r, m, [r.uniform(2500, 4500), r.uniform(5000, 7000)],
                                                            [0.6, 0.3], [0.01, 0.005])
        mix(x, hit, t, g)
        t += r.uniform(0.08, 0.16) * g
        g *= r.uniform(0.35, 0.55)
    return x


@snd("bottle_smash", n=2, desc="glass bottle shattering: crack, pings and tinkling shards")
def _bottle(r, i):
    n = secs(1.0)
    x = hp(burst(r, n, 0.004), 1500) * 1.0
    x += thud(n, 140, 0.02) * 0.3
    for _ in range(r.integers(25, 40)):
        m = secs(0.2)
        f = r.uniform(3000, 9000)
        mix(x, modes(r, m, [f, f * 1.7], [1, 0.4], [r.uniform(0.01, 0.05), 0.01]), 0.5 * r.beta(1.0, 3.0),
            r.uniform(0.1, 0.5))
    return x


@snd("coin_chink", n=2, desc="a coin dropping on stone and rolling to rest")
def _coin(r, i):
    n = secs(0.8)
    x = np.zeros(n)
    t = 0.0
    g = 1.0
    f = r.uniform(4200, 5600)
    for _ in range(r.integers(4, 7)):
        mix(x, modes(r, secs(0.3), [f, f * 1.48, f * 2.1], [1, 0.5, 0.3], [0.06, 0.03, 0.02]), t, g)
        t += r.uniform(0.05, 0.12) * (0.4 + g)
        g *= 0.6
    return x


@snd("cabbage_thud", n=2, desc="a cabbage (or bone, or rag) thumping onto the street")
def _cabbage(r, i):
    n = secs(0.35)
    x = thud(n, r.uniform(110, 140), 0.04, 0.3) * 0.8
    x += lp(burst(r, n, 0.02), 1800) * 0.6
    return x


@snd("barrel_roll_loop", loop=True, desc="barrel rolling over cobbles: rumble, hoop bumps, wooden resonance (3 s loop)")
def _barrel_roll(r, i):
    L, xf = 3.0, 0.2
    n = secs(L + xf)
    x = lp(noise(r, n, -6), 300) * 0.4 * (0.8 + 0.2 * ctrl(r, n, 9))
    t = 0.0
    while t < L + xf:
        m = secs(0.2)
        k = modes(r, m, [r.uniform(110, 130), r.uniform(250, 280), r.uniform(520, 600)], [1, 0.5, 0.2],
                  [0.06, 0.04, 0.02])
        mix(x, k * r.uniform(0.4, 0.9) + _clack(r, 0.3) * 0.3, t)
        t += 1 / 2.2 * (1 + r.uniform(-0.1, 0.1))
    x += grains(r, n, 40 * L, 0, L, 1500, 5000, 0.001, 0.003, skew=1.0) * 0.4
    return loopify(x, secs(L), secs(xf))


@snd("barrel_clonk", n=1, desc="barrel coming to rest: hollow wooden clonk")
def _barrel_clonk(r, i):
    n = secs(0.6)
    return modes(r, n, [118, 262, 575, 900], [1, 0.6, 0.3, 0.1], [0.12, 0.08, 0.04, 0.02]) + fit(_clack(r, 1.0), n) * 0.4


def _knock(r, amp=1.0, f=None):
    n = secs(0.2)
    f = f or r.uniform(140, 170)
    x = modes(r, n, [f, f * 2.2, f * 4.1, r.uniform(1100, 1500)], [1, 0.6, 0.35, 0.2], [0.07, 0.04, 0.02, 0.01])
    return (x + hp(burst(r, n, 0.001), 1500) * 0.35) * amp


@snd("door_knock", n=2, desc="three knocks on a wooden door")
def _door_knock(r, i):
    out = np.zeros(secs(1.0))
    t = 0.0
    f = r.uniform(140, 170)
    for k in range(3):
        mix(out, _knock(r, [1.0, 0.85, 1.0][k], f * r.uniform(0.97, 1.03)), t)
        t += [0.22, 0.22, 0.3][k] * r.uniform(0.9, 1.1)
    return out


@snd("door_open", n=1, desc="door creaking open")
def _door_open(r, i):
    n = secs(1.3)
    x = _creak(r, 1.2, (70, 190))
    return fit(x, n) + fit(_knock(r, 0.3, 300), n)


@snd("door_close", n=1, desc="door shutting: thud and latch")
def _door_close(r, i):
    n = secs(0.6)
    x = thud(n, 75, 0.06) * 0.9 + fit(_knock(r, 0.6, 120), n)
    mix(x, modes(r, secs(0.1), [2500, 3800], [0.5, 0.3], [0.01, 0.006]) + hp(burst(r, secs(0.1), 0.001), 2000) * 0.3, 0.09)
    return x


@snd("shutter_open", n=2, desc="window shutters creaking open and banging back")
def _shutter(r, i):
    n = secs(0.9)
    x = fit(_creak(r, 0.45, (120, 240)) * 0.6, n)
    mix(x, _knock(r, 0.8, r.uniform(220, 280)), r.uniform(0.45, 0.55))
    return x


@snd("schulklopfer_knock", n=3, desc="the shammes' mallet on a shutter calling men to morning prayer: knock-knock ... knock")
def _schul(r, i):
    out = np.zeros(secs(1.8))
    f = r.uniform(200, 260)
    for k, at in enumerate([0.0, 0.32, 1.05]):
        mix(out, _knock(r, 1.0 if k != 1 else 0.8, f * r.uniform(0.98, 1.02)), at)
        mix(out, grains(r, secs(0.15), 6, 0.01, 0.08, 800, 2500, 0.004, 0.01) * 0.4, at)   # shutter rattle
    return out


@snd("lamp_douse", n=1, desc="lantern doused: a puff and a short sizzle")
def _douse(r, i):
    n = secs(0.8)
    x = bp(noise(r, n), 900, 0.6) * env(n, 0.02, 0.06) * 0.8
    x += hp(noise(r, n), 3500) * env(n, 0.03, 0.2) * 0.35
    return x + grains(r, n, 20, 0.05, 0.5, 2000, 6000) * 0.3


@snd("lamp_relight", n=1, desc="lantern relit: flint strike, sparks, soft whoomp")
def _relight(r, i):
    n = secs(1.1)
    x = np.zeros(n)
    for at in (0.0, 0.25):
        mix(x, hp(noise(r, secs(0.08)), 2500) * env(secs(0.08), 0.005, 0.02) + grains(r, secs(0.08), 12, 0, 0.06, 3000, 8000), at)
    m = secs(0.7)
    mix(x, lp(noise(r, m), 700) * env_pts(m, [(0, 0), (0.08, 1), (0.7, 0)]) * 0.7, 0.3)
    return x


@snd("musket_shot", n=1, fmt="ogg", desc="flintlock musket: flint snap, pan fizz, loud low boom with crack and a long echoing tail", drive=3.0)
def _musket(r, i):
    n = secs(3.5)
    x = np.zeros(n)
    mix(x, modes(r, secs(0.05), [2800, 4100], [0.3, 0.2], [0.006, 0.004]), 0.0)
    mix(x, hp(noise(r, secs(0.05)), 2500) * env(secs(0.05), 0.003, 0.015) * 0.25, 0.004)
    m = secs(1.0)
    shot = hp(burst(r, m, 0.0015), 1000) * 1.2
    shot += lp(noise(r, m), 180) * env(m, 0.002, 0.12) * 1.8
    shot += thud(m, 40, 0.15, 1.0) * 1.2
    shot += bp(noise(r, m), 600, 0.7) * env(m, 0.002, 0.05) * 0.8
    shot = soft_limit(shot, 3.0)
    mix(x, shot, 0.05)
    return fit(reverb(x, 2.8, 0.5, 0.02, 3500, early=[(0.09, 0.5), (0.21, 0.35), (0.37, 0.25), (0.6, 0.15)]), n)


@snd("pistol_shot", n=1, fmt="ogg", desc="flintlock pistol: sharper crack, shorter boom, echo", drive=2.5)
def _pistol(r, i):
    n = secs(2.2)
    x = np.zeros(n)
    mix(x, modes(r, secs(0.04), [3200, 4600], [0.3, 0.2], [0.005, 0.003]), 0.0)
    m = secs(0.6)
    shot = hp(burst(r, m, 0.0012), 1500) * 1.5 + lp(noise(r, m), 300) * env(m, 0.001, 0.06) * 1.2
    shot += thud(m, 60, 0.07, 1.0) * 0.8
    mix(x, soft_limit(shot, 2.5), 0.03)
    return fit(reverb(x, 2.0, 0.42, 0.02, 4000, early=[(0.08, 0.4), (0.19, 0.25), (0.34, 0.15)]), n)


@snd("smoke_charge", n=1, fmt="ogg", desc="smoke powder: fuse fizz, whump, long hissing billow")
def _smoke(r, i):
    n = secs(2.2)
    x = np.zeros(n)
    mix(x, hp(noise(r, secs(0.2)), 3000) * 0.3, 0.0)
    m = secs(0.6)
    mix(x, lp(noise(r, m), 150) * env(m, 0.005, 0.15) * 1.3 + thud(m, 55, 0.12) * 0.8, 0.2)
    m2 = secs(1.9)
    fizz = hp(noise(r, m2), 2000) * env_pts(m2, [(0, 0), (0.1, 0.5), (1.9, 0)])
    mix(x, fizz + grains(r, m2, 80, 0, 1.6, 2000, 7000, skew=1.5) * 0.6, 0.25)
    return x


@snd("flash_crack", n=1, fmt="ogg", desc="flash powder: sharp crack, fwoomp and sparkle")
def _flash(r, i):
    n = secs(1.2)
    x = hp(burst(r, n, 0.001), 1500) * 1.4
    x += lp(noise(r, n), 800) * env(n, 0.01, 0.1) * 0.8
    x += grains(r, n, 60, 0.02, 0.6, 3000, 9000, skew=1.5) * 0.6
    return reverb(x, 1.5, 0.3)[:n]


@snd("knife_slash", n=2, desc="knife drawn and slashed: whoosh and a metallic shing")
def _knife(r, i):
    n = secs(0.5)
    x = np.zeros(n)
    m = secs(0.25)

    def g(tc, f):
        return g_bp(1.0, 2.0)(f / (800 + 2500 * np.clip(tc / 0.2, 0, 1)))
    mix(x, stft_filter(noise(r, m), g) * np.hanning(m) * 0.6, 0.0)
    m2 = secs(0.35)
    shing = modes(r, m2, [r.uniform(3000, 3600), r.uniform(4700, 5300), r.uniform(6800, 7600)], [0.4, 0.3, 0.2],
                  [0.08, 0.05, 0.03]) + hp(noise(r, m2), 4000) * env(m2, 0.005, 0.05) * 0.3
    mix(x, shing, 0.1)
    return x


@snd("splash_slops", n=2, desc="slops thrown from a window splashing on the street")
def _splash(r, i):
    n = secs(1.0)
    x = lp(burst(r, n, 0.08), 3000) * 0.8
    for _ in range(r.integers(20, 35)):
        m = secs(0.05)
        mix(x, chirp(m, r.uniform(400, 900), r.uniform(1000, 2500), 0.012), 0.5 * r.beta(1.2, 3.0), r.uniform(0.1, 0.4))
    x += grains(r, n, 60, 0.03, 0.5, 1000, 5000, 0.001, 0.004, skew=2.5) * 0.4
    return x


@snd("glass_clink", n=2, desc="mugs and glasses clinking")
def _clink(r, i):
    out = np.zeros(secs(0.6))
    mix(out, _glass(r), 0)
    mix(out, _glass(r, 0.6), r.uniform(0.01, 0.03))
    return out


# ====================================================================== bells and the hejnal

BELL_PARTIALS = [   # ratio to the prime, amplitude, relative decay
    (0.5, 0.6, 1.0), (1.0, 0.5, 0.7), (1.2, 0.7, 0.55), (1.5, 0.25, 0.35), (2.0, 1.0, 0.45), (2.5, 0.35, 0.22),
    (2.67, 0.3, 0.18), (3.0, 0.3, 0.14), (4.0, 0.25, 0.1), (5.33, 0.15, 0.06), (6.1, 0.1, 0.045), (7.2, 0.08, 0.035),
]


def bell(r, prime, dur, decay, strike=1.0, detune=0.6, inharm=0.0, bright=1.0):
    n = secs(dur)
    t = tt(n)
    x = np.zeros(n)
    for ratio, a, dk in BELL_PARTIALS:
        f = prime * ratio * (1 + inharm * r.uniform(-1, 1))
        if f >= NYQ * 0.9:
            continue
        tau = decay * dk * 6.0
        a = a * (bright if ratio > 2.1 else 1.0)
        for s in (-0.5, 0.5):     # a close pair: the slow beating of a real bell
            ff = f + s * detune * r.uniform(0.5, 1.5) * (ratio ** 0.5)
            x += a * 0.5 * np.exp(-t / tau) * np.sin(TAU * ff * t + r.uniform(0, TAU))
    na = secs(0.006)                                   # a clapper on bronze: a quick but not clicky onset
    x[:na] *= np.linspace(0, 1, na) ** 0.7
    m = min(n, secs(0.4))
    clap = lp(hp(burst(r, m, 0.004), 500), 3500) * 0.25
    for _ in range(6):
        clap += modes(r, m, [r.uniform(1500, 5000)], [r.uniform(0.03, 0.1)], [r.uniform(0.015, 0.05)])
    x[:m] += clap * strike * 0.6
    return x


@snd("bell_great", n=1, fmt="ogg", cat="bell", desc="St Mary's great bell: one stroke (hum, prime, tierce, quint, nominal; long tail)")
def _bell_great(r, i):
    d = 16.0
    x = bell(r, 98.0, d, 1.5, 1.0, 0.6, 0.0, 0.8)
    return fit(reverb(x, 4.0, 0.35, 0.03, 3500), secs(d))


@snd("bell_sigismund", n=1, fmt="ogg", cat="bell", desc="the Wawel Sigismund bell far off: very deep, distant (feast days)")
def _bell_sig(r, i):
    d = 18.0
    x = bell(r, 46.25, d, 2.0, 0.5, 0.35)
    x = lp(x, 1500)
    return fit(reverb(x, 4.0, 0.55, 0.08, 2000), secs(d))


@snd("bell_townhall", n=1, fmt="ogg", cat="bell", desc="the Town Hall clock bell: a hammer stroke, higher and shorter")
def _bell_th(r, i):
    d = 7.0
    x = bell(r, 330.0, d, 0.5, 1.4, 1.0, 0.0, 1.0)
    return fit(reverb(x, 2.4, 0.3, 0.02), secs(d))


@snd("bell_small", n=3, fmt="ogg", cat="bell", desc="St Mary's smaller bells (three pitches) for the canonical hours")
def _bell_small(r, i):
    d = 9.0
    x = bell(r, [196.0, 220.0, 261.6][i], d, 0.65, 0.9, 0.6, 0.0, 0.85)
    return fit(reverb(x, 2.8, 0.3, 0.03), secs(d))


@snd("bell_uniate", n=1, fmt="ogg", cat="bell", desc="the Uniate chapel's small bell: tinny, a little out of tune")
def _bell_uniate(r, i):
    d = 5.0
    x = bell(r, 494.0, d, 0.3, 1.0, 1.5, 0.03, 1.1)
    return fit(reverb(x, 1.8, 0.25, 0.02), secs(d))


@snd("bell_peal", n=1, fmt="ogg", cat="bell", desc="a peal: four bells rung in rounds (after the Angelus strokes)")
def _peal(r, i):
    d = 15.0
    n = secs(d)
    out = np.zeros(n)
    primes = [261.6, 220.0, 196.0, 164.8]
    t = 0.3
    rnd = 0
    while t < d - 4.0:
        for k, p in enumerate(primes):
            g = min(1.0, 0.4 + 0.2 * rnd) * (1.0 if t < d - 6 else 0.7)
            mix(out, bell(r, p, 4.5, 0.4, 0.9), t, g)
            t += 0.42 * r.uniform(0.94, 1.06)
        t += 0.42      # the handstroke gap
        rnd += 1
    return fit(reverb(out, 3.0, 0.3, 0.03), n)


NOTE = {"F4": 349.23, "G4": 392.0, "A4": 440.0, "Bb4": 466.16, "C5": 523.25, "D5": 587.33, "F5": 698.46}
# An approximation of the Hejnal mariacki: the rising F-major triad, the held C, the turn and the fall, then the call
# again, broken off mid-note (the legend of the watchman shot through the throat as he sounded the alarm).
HEJNAL = [("F4", 1.0), ("A4", 1.0), ("C5", 2.6), ("C5", 0.5), ("D5", 0.5), ("C5", 0.5), ("Bb4", 0.5), ("A4", 2.2),
          ("A4", 0.5), ("Bb4", 0.5), ("C5", 1.0), ("A4", 1.0), ("F4", 2.6),
          ("F4", 1.0), ("A4", 1.0), ("C5", 2.6), ("C5", 0.5), ("D5", 0.5), ("C5", 0.5), ("Bb4", 0.5), ("A4", 1.2),
          ("Bb4", 0.5), ("C5", -0.38)]   # negative: cut off without release after that many beats
BEAT = 0.55


def trumpet_note(r, f, dur, cut=False, loud=1.0):
    n = secs(dur + (0.0 if cut else 0.12))
    t = tt(n)
    scoop = 1 - 0.03 * np.exp(-t / 0.03)
    f0 = f * scoop * vibrato(n, 5.3, 0.004, 0.35, r) * (1 + 0.0015 * ctrl(r, n, 6))
    rel = 0.008 if cut else 0.1
    e = env_pts(n, [(0, 0), (0.04, 1.0), (0.12, 0.85), (max(dur - 0.05, 0.13), 0.9), (dur, 0.9 if cut else 0.7),
                    (dur + rel, 0.0), (n / SR + 1, 0.0)]) * loud
    K = int(NYQ * 0.9 / f)
    ph = TAU * np.cumsum(f0) / SR
    x = np.zeros(n)
    for k in range(1, K + 1):
        hf = k * f
        bump = 1 + 1.8 * math.exp(-((hf - 1300) / 700) ** 2)
        p = 1.9 - 1.1 * e                       # brighter when louder
        x += bump * k ** (-p) * np.sin(k * ph)
    x *= e
    x += bp(noise(r, n), 1500, 0.8) * env(n, 0.005, 0.03) * 0.25 * loud
    return x


@snd("hejnal", n=1, fmt="ogg", cat="bell", desc="the hejnal mariacki: synthesised trumpet phrase from St Mary's tower, broken off mid-phrase")
def _hejnal(r, i):
    total = sum(abs(b) for _, b in HEJNAL) * BEAT
    n = secs(total + 4.0)
    out = np.zeros(n)
    t = 0.2
    for k, (name, beats) in enumerate(HEJNAL):
        cut = beats < 0
        d = abs(beats) * BEAT
        hold = 1.25 if beats >= 2.0 else 1.0      # fermatas on the long notes
        mix(out, trumpet_note(r, NOTE[name], d * hold - 0.03, cut, 0.8 + 0.2 * (beats >= 1.0)), t)
        t += d * hold
    out = fit(out, n)
    return fit(reverb(out, 2.4, 0.4, 0.03, 4500, early=[(0.21, 0.35), (0.38, 0.2), (0.55, 0.1)]), n)


# ====================================================================== UI

@snd("ui_click", n=1, cat="ui", desc="UI click: a soft, muted wooden tick", peak=-8.0)
def _ui_click(r, i):
    n = secs(0.06)
    x = modes(r, n, [720, 1450], [1, 0.3], [0.009, 0.005]) + lp(burst(r, n, 0.0015), 2500) * 0.12
    return lp(x, 3000) * 0.5


@snd("ui_hover", n=1, cat="ui", desc="UI hover: a faint soft tick", peak=-14.0)
def _ui_hover(r, i):
    n = secs(0.035)
    return lp(modes(r, n, [1900], [1], [0.004]), 3000) * 0.3


@snd("ui_page", n=2, cat="ui", desc="journal page turn: paper swish and flutter")
def _ui_page(r, i):
    n = secs(0.45)
    c = curve(n, [(0, 1500), (0.2, 3500), (0.45, 2000)])

    def g(tc, f):
        idx = np.clip((tc[:, 0] * SR).astype(int), 0, n - 1)
        return g_bp(1.0, 1.2)(f / c[idx][:, None])
    x = stft_filter(noise(r, n), g) * env_pts(n, [(0, 0), (0.12, 1), (0.3, 0.5), (0.45, 0)])
    return x + grains(r, n, 20, 0.05, 0.3, 1500, 5000, 0.001, 0.004) * 0.5


# ====================================================================== output

def write_wav(path, x, channels=1):
    pcm = np.clip(np.round(x * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def write_ogg(path, x, channels=1, q=3):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "t.wav"
        write_wav(tmp, x, channels)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp), "-map_metadata", "-1", "-c:a", "libvorbis",
                        "-q:a", str(q), "-fflags", "+bitexact", "-flags", "+bitexact", str(path)], check=True)


def render(name, spec, idx):
    fname = name if spec["n"] == 1 else "%s_%d" % (name, idx + 1)
    r = seeded(fname)
    x = spec["fn"](r, idx)
    fade = 1.5 if spec["cat"] == "bell" else (0.15 if spec["fmt"] == "ogg" else 0.004)
    x = finalize(x, spec["loop"], spec["peak"], spec["drive"], fade)
    return fname, x


def generate(only):
    OUT.mkdir(parents=True, exist_ok=True)
    man_path = OUT / "manifest.json"
    manifest = {"sample_rate": SR, "generator": "tools/gen_sfx.py", "licence": "CC BY 4.0", "sounds": {}, "sets": {}}
    if only and man_path.exists():
        manifest = json.loads(man_path.read_text())
    total = 0
    for name, spec in SOUNDS.items():
        if only and not any(name.startswith(p) for p in only):
            continue
        files = []
        for i in range(spec["n"]):
            fname, x = render(name, spec, i)
            ext = spec["fmt"]
            path = OUT / (fname + "." + ext)
            for old in (OUT / (fname + ".wav"), OUT / (fname + ".ogg")):
                if old != path and old.exists():
                    old.unlink()
            (write_wav if ext == "wav" else write_ogg)(path, x)
            manifest["sounds"][fname] = {"file": "res://assets/audio/%s.%s" % (fname, ext), "set": name,
                                         "dur": round(len(x) / SR, 3), "loop": spec["loop"], "cat": spec["cat"],
                                         "peak_db": round(db(np.max(np.abs(x))), 1), "rms_db": round(db(rms(x)), 1)}
            files.append(fname)
            total += 1
        manifest["sets"][name] = {"files": files, "desc": spec["desc"], "loop": spec["loop"], "cat": spec["cat"]}
        print("  %-22s x%d  %s" % (name, spec["n"], spec["desc"][:70]))
    man_path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    if not only:        # drop files of sets that no longer exist (and their Godot import sidecars)
        keep = {Path(v["file"]).name for v in manifest["sounds"].values()} | {"demo_mix.ogg"}
        for pth in list(OUT.iterdir()):
            base = pth.name[:-len(".import")] if pth.name.endswith(".import") else pth.name
            if Path(base).suffix in (".wav", ".ogg") and base not in keep:
                pth.unlink()
    size = sum(p.stat().st_size for p in OUT.iterdir() if p.suffix in (".wav", ".ogg"))
    print("wrote %d files (%d in manifest), %.2f MB in %s" % (total, len(manifest["sounds"]), size / 1048576, OUT))


# ====================================================================== demo mix

def load_set(name, k=0):
    spec = SOUNDS[name]
    return render(name, spec, k % spec["n"])[1]


def demo():
    """20 s: walking north-east across the square past a crowd, a dorozka trots by, St Mary's strikes, a dog barks."""
    D = 20.0
    n = secs(D)
    L = np.zeros(n)
    R = np.zeros(n)
    timeline = []

    def place(x, at, gain_db, pan=0.0, label=None):
        g = 10 ** (gain_db / 20)
        a = (pan + 1) * math.pi / 4
        mix(L, x, at, g * math.cos(a))
        mix(R, x, at, g * math.sin(a))
        if label:
            timeline.append((at, label))

    def bed(name, gain_db, pan, gain_curve=None, label=None):
        x = load_set(name)
        reps = int(math.ceil(n / len(x))) + 1
        y = np.tile(x, reps)[:n]
        if gain_curve is not None:
            y = y * gain_curve
        place(y, 0.0, gain_db, pan, label)

    bed("wind_calm_loop", -20, 0.0, label="wind bed (calm)")
    bed("city_murmur_loop", -22, -0.2, label="distant city murmur")
    crowd_g = env_pts(n, [(0, 0.15), (5, 0.6), (8, 1.0), (11, 0.6), (16, 0.15), (D, 0.1)])
    bed("crowd_talk_loop", -14, -0.5, crowd_g, "crowd talk near the Cloth Hall stalls (swells 5-11 s)")
    # footsteps on cobbles, then flagstones in the arcade 9-12 s
    t = 0.3
    k = 0
    vr = np.random.default_rng(1795)
    while t < D - 0.5:
        surf = "step_flags_shoe" if 9.0 <= t < 12.0 else "step_cobbles_shoe"
        x = load_set(surf, int(vr.integers(0, STEP_VARIANTS)))
        x = np.interp(np.arange(0, len(x), vr.uniform(0.94, 1.06)), np.arange(len(x)), x)    # pitch +-6 %
        place(x, t, -19 + vr.uniform(-3, 3), 0.1 if k % 2 else -0.1)                          # level +-3 dB
        t += 0.55 * vr.uniform(0.97, 1.03)       # heel strikes at the walk clip's cadence (~1.8 steps/s)
        k += 1
    timeline.append((0.3, "player footsteps (shoe) on cobbles, flagstones in the arcade 9-12 s, under the murmur"))
    # a guard's boots crossing 25 -> 8 m away: quieter and duller with distance (the in-game distance low-pass)
    t = 1.0
    while t < 8.0:
        dist = 25.0 - (t - 1.0) * 2.4
        cut = float(np.interp(dist, [3.0, 25.0], [12000.0, 1800.0]))
        x = lp(load_set("step_cobbles_boot", int(vr.integers(0, STEP_VARIANTS))), cut)
        place(x, t, -16 - 20 * math.log10(dist / 3.0) + vr.uniform(-3, 3), 0.7)
        t += 0.62
    timeline.append((1.0, "a guard's boots approaching from 25 m (distance low-pass)"))
    # the dorozka: approaches from the left, passes at 9 s, recedes right
    t0, t1 = 3.0, 15.5
    for tt_ in np.arange(t0, t1, 0.25):
        dist = 2.5 + abs(tt_ - 9.0) * 2.0
        pan = float(np.clip((tt_ - 9.0) / 4.0, -1, 1))
        g = -6 - 20 * math.log10(dist / 2.5)
        place(load_set("hoof_trot", int(tt_ * 4)), tt_, g, pan)
        place(load_set("hoof_trot", int(tt_ * 4) + 1), tt_ + 0.11, g - 1, pan)
    wl = load_set("wheel_loop")
    seg = np.tile(wl, 4)[:secs(t1 - t0)]
    tl = tt(len(seg)) + t0
    dist = 2.5 + np.abs(tl - 9.3) * 2.0
    seg = seg * (2.5 / dist) * env_pts(len(seg), [(0, 0), (1, 1), (t1 - t0 - 1, 1), (t1 - t0, 0)])
    pan_c = np.clip((tl - 9.3) / 4.0, -1, 1)
    a = (pan_c + 1) * math.pi / 4
    g = 10 ** (-9 / 20)
    mix(L, seg * np.cos(a), t0, g)
    mix(R, seg * np.sin(a), t0, g)
    timeline.append((t0, "dorozka approaching: trotting hooves (2 horses), iron tyres on cobbles"))
    place(load_set("harness_jingle", 1), 8.4, -12, -0.1, "harness jingle as it passes")
    place(load_set("wheel_clack", 2), 9.6, -10, 0.1, "wheel clack over a raised sett")
    place(load_set("coachman_hoo"), 10.2, -12, 0.3, 'coachman: "Hooo!"')
    place(load_set("bell_great"), 12.0, -9, 0.6, "St Mary's great bell (stroke 1)")
    place(load_set("bell_great"), 15.0, -9, 0.6, "St Mary's great bell (stroke 2)")
    place(load_set("dog_bark", 1), 6.0, -16, -0.8, "dog barks behind the Town Hall")
    place(load_set("dog_bark_far"), 16.5, -18, 0.9, "dogs far off")
    place(load_set("laugh", 1), 7.3, -17, -0.5, "a woman laughs in the crowd")
    place(load_set("pigeon_flap"), 4.2, -15, 0.4, "pigeons take off")
    place(load_set("cough", 1), 17.8, -20, -0.3, "cough from a window")
    st = np.stack([L, R], axis=1)
    st = soft_limit(st, 1.2)
    st = st / (np.max(np.abs(st)) + 1e-12) * 10 ** (-1.0 / 20)
    path = OUT / "demo_mix.ogg"
    write_ogg(path, st.reshape(-1), channels=2, q=4)
    mono = st.mean(axis=1)
    print("demo: %s  %.1f s stereo  peak %.1f dBFS  RMS %.1f dBFS  crest %.1f dB" % (
        path.relative_to(ROOT), D, db(np.max(np.abs(st))), db(rms(mono)), db(np.max(np.abs(st))) - db(rms(mono))))
    print("  per 2 s RMS (dBFS): " + " ".join("%.0f" % db(rms(mono[secs(s):secs(s + 2)])) for s in range(0, int(D), 2)))
    print("  timeline:")
    for at, label in sorted(timeline):
        print("   %5.1f s  %s" % (at, label))


# ====================================================================== footstep stats

# Power-weighted spectral centroid ranges (the heel thud carries most of a step's energy, so a hard-soled step on
# stone centres around 1-2.5 kHz, a hollow board or wet mud well under 1 kHz, crunchy snow / gravel / straw above
# 1.5 kHz), and the longest acceptable onset-to-peak time (hard ground: the heel is the peak; crunchy ground: the
# peak may land in the crunch just after). All sets: crest (peak/RMS) 10-24 dB, RMS -30..-12 dBFS at -1 dBFS peak.
STEP_TARGETS = {
    "cobbles": ((900, 2600), 6.0), "flags": ((500, 1800), 6.0), "snow": ((1500, 4200), 40.0),
    "mud": ((200, 1000), 40.0), "gravel": ((1500, 4500), 25.0), "planks": ((200, 900), 8.0),
    "straw": ((1200, 4200), 40.0),
}


def analyse(x):
    """(spectral centroid Hz, attack ms = start to 90 % of the 1 ms-smoothed peak envelope, RMS dBFS, crest dB)."""
    P = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1 / SR)
    cent = float((P * f).sum() / (P.sum() + 1e-20))
    e = np.convolve(np.abs(x), np.ones(secs(0.001)) / secs(0.001), "same")
    on = np.argmax(e > 0.1 * e.max())
    att = (np.argmax(e > 0.9 * e.max()) - on) / SR * 1000.0
    pk = float(np.max(np.abs(x)))
    return cent, att, db(rms(x)), db(pk) - db(rms(x))


def step_stats():
    man = json.loads((OUT / "manifest.json").read_text())
    fails = 0
    print("footstep sets: centroid Hz (min/mean/max) | attack ms (max) | RMS dBFS (mean) | crest dB (min/max) | target")
    for surf in SURFACES:
        (c_lo, c_hi), a_max = STEP_TARGETS[surf]
        for shoe in SHOES:
            name = "step_%s_%s" % (surf, shoe)
            st = []
            for fname in man["sets"][name]["files"]:
                pth = OUT / Path(man["sounds"][fname]["file"]).name
                with wave.open(str(pth)) as w:
                    x = np.frombuffer(w.readframes(w.getnframes()), "<i2") / 32768.0
                st.append(analyse(x))
            a = np.array(st)
            ok = (a[:, 0].min() >= c_lo and a[:, 0].max() <= c_hi and a[:, 1].max() <= a_max
                  and a[:, 3].min() >= 10 and a[:, 3].max() <= 24 and a[:, 2].min() >= -30 and a[:, 2].max() <= -12)
            fails += 0 if ok else 1
            print("  %-22s %5.0f/%5.0f/%5.0f | %5.1f | %6.1f | %4.1f/%4.1f | %d-%d Hz, <=%.0f ms  %s" % (
                name, a[:, 0].min(), a[:, 0].mean(), a[:, 0].max(), a[:, 1].max(), a[:, 2].mean(), a[:, 3].min(),
                a[:, 3].max(), c_lo, c_hi, a_max, "ok" if ok else "OUT OF RANGE"))
    print("footstep sets out of range: %d / %d" % (fails, len(SURFACES) * len(SHOES)))
    return fails


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", default="", help="comma-separated name prefixes")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--demo", action="store_true", help="also render assets/audio/demo_mix.ogg and print its stats")
    ap.add_argument("--demo-only", action="store_true", help="render only the demo mix")
    ap.add_argument("--stats", action="store_true", help="print footstep analysis against the target ranges")
    a = ap.parse_args()
    if a.list:
        for name, s in SOUNDS.items():
            print("%-22s x%d %-4s %s%s" % (name, s["n"], s["fmt"], "loop " if s["loop"] else "", s["desc"]))
        return
    if shutil.which("ffmpeg") is None:
        sys.exit("gen_sfx: ffmpeg (with libvorbis) is needed for the Ogg files")
    if not a.demo_only:
        generate([p for p in a.only.split(",") if p])
    if a.stats or a.demo:
        step_stats()
    if a.demo or a.demo_only:
        demo()


if __name__ == "__main__":
    main()
