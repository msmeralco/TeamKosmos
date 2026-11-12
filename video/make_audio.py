"""Synthesises the music and sound design for the two Sol reels (120 BPM, seeded, so the files are reproducible).

Usage:  ../.venv/bin/python make_audio.py      (writes sol-reel/assets/intro.wav and outro.wav)
"""
import math
import wave
from pathlib import Path

import numpy as np

SR = 44100
OUT = Path(__file__).resolve().parent / "sol-reel" / "assets"
BEAT = 0.5  # 120 BPM


class Mix:
    def __init__(self, seconds):
        self.n = int(seconds * SR)
        self.buf = np.zeros((self.n, 2), dtype=np.float64)
        self.rng = np.random.default_rng(2026)

    def add(self, t, sig, gain=1.0, pan=0.0):
        i = int(t * SR)
        if i >= self.n or i < 0:
            return
        sig = sig[: self.n - i]
        l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
        self.buf[i : i + len(sig), 0] += sig * gain * l * 1.414
        self.buf[i : i + len(sig), 1] += sig * gain * r * 1.414

    def noise(self, dur):
        return self.rng.uniform(-1, 1, int(dur * SR))

    def save(self, path, fade_out=0.6, peak=0.89):
        b = self.buf.copy()
        b = np.tanh(b * 0.9)  # gentle glue so stacked hits never clip
        fo = int(fade_out * SR)
        b[-fo:] *= np.linspace(1, 0, fo)[:, None]
        b *= peak / max(1e-9, np.abs(b).max())
        data = (b * 32767).astype("<i2")
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(data.tobytes())


def env(n, attack=0.002, decay=0.2):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(attack, 1e-5)) * np.exp(-t / decay)


def kick(dur=0.38, f0=130, f1=44, decay=0.12):
    n = int(dur * SR); t = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * env(n, 0.001, decay) * 1.0


def hat(m, dur=0.07, open_=False):
    n = int(dur * (4 if open_ else 1) * SR); x = m.noise(n / SR)
    x = np.diff(x, prepend=0)  # crude high-pass
    return x * env(n, 0.001, 0.025 if not open_ else 0.09) * 0.5


def clap(m):
    n = int(0.2 * SR); x = m.noise(0.2); x = np.diff(x, prepend=0) * 0.7 + x * 0.3
    e = env(n, 0.001, 0.06) + 0.7 * np.roll(env(n, 0.001, 0.05), int(0.012 * SR))
    return x * e * 0.8


def boom(dur=0.9, f=52):
    n = int(dur * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * (1 + 0.4 * np.exp(-t / 0.06)) * t) * env(n, 0.002, 0.28)) * 1.0


def blip(freq, dur=0.12, vol=0.6):
    n = int(dur * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * freq * 2 * t)) * env(n, 0.002, dur / 3.2) * vol


def riser(m, dur, f0=300, f1=5000):
    n = int(dur * SR); x = m.noise(dur); t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (t / dur)
    y = x * np.sin(2 * np.pi * np.cumsum(f) / SR)
    return y * (t / dur) ** 2.2 * 0.5


def whoosh(m, dur=0.5, up=True):
    n = int(dur * SR); x = m.noise(dur); t = np.arange(n) / SR
    c = np.sin(np.pi * (t / dur if up else 1 - t / dur)) ** 1.5
    return np.diff(x, prepend=0) * c * 0.5


def chord(freqs, dur, attack=0.5, vol=0.35):
    n = int(dur * SR); t = np.arange(n) / SR; y = np.zeros(n)
    for i, f in enumerate(freqs):
        y += np.sin(2 * np.pi * f * t + i) + 0.3 * np.sin(2 * np.pi * f * 2.003 * t) + 0.12 * np.sin(2 * np.pi * f * 3 * t)
    e = np.minimum(1, t / attack) * np.exp(-np.maximum(0, t - dur * 0.55) / (dur * 0.3))
    return y / len(freqs) * e * vol


def chime(freq, dur=1.4, vol=0.4):
    n = int(dur * SR); t = np.arange(n) / SR
    return (np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * freq * 2.76 * t) + 0.25 * np.sin(2 * np.pi * freq * 5.4 * t)) * env(n, 0.002, dur / 5) * vol


def bass(freq, dur, vol=0.5):
    n = int(dur * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * freq * t) * env(n, 0.01, dur * 0.6) * vol


PENTA = [523.25, 587.33, 659.25, 783.99, 880.0, 987.77, 1046.5]


def arp(m, t0, t1, step=0.125, vol=0.16, seed=3):
    r = np.random.default_rng(seed); k = 0
    t = t0
    while t < t1 - 1e-6:
        m.add(t, blip(PENTA[int(r.integers(0, len(PENTA)))], 0.18, 1.0), vol, pan=float(r.uniform(-0.6, 0.6)))
        t += step; k += 1


def intro():
    """6 s: the sun bounces in (a tick and a soft thump per landing), crouches, hops up (whoosh), and the title lands (chime and chord)."""
    m = Mix(6.0)
    g, H, e = 5200.0, 500.0, 0.62
    tf = math.sqrt(2 * H / g)
    t, v, f = 0.12 + tf, g * tf * e, 760.0
    m.add(t, blip(f, 0.14), 0.5); m.add(t, kick(0.3, 100, 48, 0.09), 0.55)
    n = 0
    while True:
        f *= 0.86
        air = 2 * v / g
        if air < 0.06: break
        t += air; v *= e; n += 1
        m.add(t, blip(f, 0.12), 0.42)
        if n < 3: m.add(t, kick(0.25, 90, 48, 0.07), 0.4 - 0.1 * n)
    m.add(0.12, whoosh(m, 0.35, up=False), 0.12)        # the drop
    m.add(2.05, riser(m, 0.3, 300, 1800), 0.3)         # the crouch
    m.add(2.2, whoosh(m, 0.7), 0.55)                    # the hop
    m.add(2.9, boom(0.9, 55), 0.6)                      # arrival
    m.add(2.9, chime(1318.5, 1.7), 0.5); m.add(3.05, chime(987.77, 1.5), 0.3)
    m.add(2.9, chord([261.63, 329.63, 392.0, 493.88, 659.25], 3.0, 0.3), 0.9)
    for k, fr in enumerate((523.25, 659.25, 783.99, 987.77)):
        m.add(3.5 + k * 0.125, blip(fr, 0.2, 1.0), 0.14, pan=0.4 - 0.25 * k)
    m.save(OUT / "intro.wav", fade_out=1.0)


def outro():
    m = Mix(10.0)
    for k in range(0, 18):
        t0 = k * BEAT
        m.add(t0, kick(), 0.7)
    for k in range(2, 36):
        t0 = k * 0.25
        if k % 2 == 1: m.add(t0, hat(m), 0.2, pan=0.3)
    for t0 in np.arange(1.5, 7.0, 1.0): m.add(float(t0), clap(m), 0.4)
    for k, t0 in enumerate(np.arange(0.0, 7.5, 0.5)): m.add(float(t0), bass([65.41, 65.41, 73.42, 49.0][k % 4], 0.45), 0.45)
    # five words slam on the first five beats
    for k in range(5):
        m.add(k * BEAT, boom(0.4, 90 - k * 8), 0.55); m.add(k * BEAT, blip(520 + 130 * k, 0.1, 1.0), 0.3, pan=-0.6 + k * 0.3)
    m.add(2.0, riser(m, 0.5, 400, 3500), 0.5)
    # passport: the cover opens, the seal stamps, four vouchers are stamped one by one
    m.add(2.55, whoosh(m, 0.7), 0.7)
    m.add(3.5, boom(0.9, 56), 1.0); m.add(3.5, clap(m), 0.7); m.add(3.52, chime(1174.7, 1.5), 0.45)
    for k, t0 in enumerate((3.75, 4.25, 4.75, 5.25)):
        m.add(t0, boom(0.35, 100 - 6 * k), 0.7); m.add(t0, blip(900 + 150 * k, 0.12, 1.0), 0.3)
    arp(m, 3.75, 5.5, 0.125, 0.1, seed=4)
    # the plan: click, then the page slides out
    m.add(5.9, blip(1400, 0.05, 1.0), 0.5); m.add(6.0, blip(900, 0.06, 1.0), 0.5)
    m.add(6.1, whoosh(m, 0.5), 0.8)
    for k in range(4): m.add(6.5 + k * 0.125, blip(780 + 120 * k, 0.07, 1.0), 0.2)
    # resolve
    m.add(7.35, riser(m, 0.15, 800, 6000), 0.4)
    m.add(7.5, boom(1.3, 46), 1.0)
    m.add(7.5, chord([261.63, 329.63, 392.0, 493.88, 659.25], 2.5, 0.2), 1.0)
    m.add(7.6, chime(1318.5, 1.8), 0.55); m.add(8.0, chime(987.77, 1.5), 0.3)
    m.save(OUT / "outro.wav", fade_out=0.9)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    intro(); outro()
    print("wrote", OUT / "intro.wav", OUT / "outro.wav")
