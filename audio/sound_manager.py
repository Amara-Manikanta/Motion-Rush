"""Procedurally synthesised sound effects.

The game ships with no audio assets, so every effect is generated as a numpy
waveform at start-up. That keeps the repo asset-free and means audio works on
a fresh clone with nothing to download.
"""

import math

import numpy as np
import pygame

SAMPLE_RATE = 44100


def _to_sound(wave: np.ndarray, volume: float) -> pygame.mixer.Sound:
    wave = np.clip(wave, -1.0, 1.0) * volume
    audio = (wave * 32767).astype(np.int16)
    stereo = np.repeat(audio.reshape(-1, 1), 2, axis=1)
    return pygame.sndarray.make_sound(np.ascontiguousarray(stereo))


def _env(n: int, attack=0.01, release=0.6) -> np.ndarray:
    a = max(1, int(n * attack))
    r = max(1, int(n * release))
    env = np.ones(n)
    env[:a] = np.linspace(0.0, 1.0, a)
    env[n - r:] = np.linspace(1.0, 0.0, r) ** 1.7
    return env


def _tone(freq_start, freq_end, dur, volume=0.4, harmonics=(1.0, 0.35, 0.15),
          square=False):
    n = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    freq = np.linspace(freq_start, freq_end, n)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    wave = np.zeros(n)
    for i, amp in enumerate(harmonics, start=1):
        w = np.sin(phase * i)
        if square:
            w = np.sign(w)
        wave += amp * w
    wave /= sum(harmonics)
    return _to_sound(wave * _env(n), volume)


def _noise(dur, volume=0.4, lowpass=0.25):
    n = int(SAMPLE_RATE * dur)
    rng = np.random.default_rng(4)
    wave = rng.uniform(-1, 1, n)
    # Cheap one-pole low-pass so it reads as a thud rather than a hiss.
    out = np.zeros(n)
    acc = 0.0
    for i in range(n):
        acc += (wave[i] - acc) * lowpass
        out[i] = acc
    return _to_sound(out * _env(n, attack=0.005, release=0.8), volume)


class SoundManager:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.sounds = {}
        self._music_channel = None
        if not enabled:
            return
        try:
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2,
                              buffer=512)
        except pygame.error:
            self.enabled = False
            return
        self._build()

    def _build(self):
        try:
            self.sounds = {
                "jump":   _tone(430, 880, 0.16, 0.30),
                "duck":   _tone(360, 170, 0.14, 0.26),
                "orb":    _tone(980, 1580, 0.10, 0.22, harmonics=(1.0, 0.3)),
                "lane":   _tone(600, 720, 0.06, 0.14, harmonics=(1.0,)),
                "hit":    _noise(0.45, 0.55, lowpass=0.06),
                "over":   _tone(340, 90, 0.85, 0.38, square=True),
                "start":  _tone(300, 900, 0.30, 0.32),
                "milestone": _tone(700, 1400, 0.22, 0.26),
            }
        except Exception:
            # Audio is a nicety -- never let it take the game down.
            self.enabled = False
            self.sounds = {}

    def play(self, name: str):
        if not self.enabled:
            return
        snd = self.sounds.get(name)
        if snd is not None:
            snd.play()

    def close(self):
        if self.enabled:
            pygame.mixer.quit()
