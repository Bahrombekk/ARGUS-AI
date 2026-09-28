# -*- coding: utf-8 -*-
"""Debounce yordamchilari: sirpanuvchi oyna va uzluksiz-vaqt.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import collections



class PresenceWindow:
    """Sirpanuvchi oyna + minimal aniqlash soni (kam kadrли oynaда 1-2 yolg'on
    aniqlash ratio'дан oshib ketmaydi)."""
    def __init__(self, window, ratio, min_hits):
        self.window, self.ratio, self.min_hits = window, ratio, min_hits
        self.buf = collections.deque(); self.latched = False
    def update(self, det, now):
        self.buf.append((now, bool(det)))
        while self.buf and now - self.buf[0][0] > self.window:
            self.buf.popleft()
        n = len(self.buf); hits = sum(1 for _, d in self.buf if d)
        r = hits / n if n else 0.0
        span = (self.buf[-1][0]-self.buf[0][0]) if n > 1 else 0.0
        if span >= self.window*0.5 and r >= self.ratio and hits >= self.min_hits:
            self.latched = True
        elif r < self.ratio*0.5:
            self.latched = False
        return self.latched


class Sustain:
    """Uzluksiz-vaqt: shart shuncha s UZLUKSIZ rost bo'lса → latched."""
    def __init__(self, sec):
        self.sec = sec; self.since = None; self.latched = False
    def update(self, cond, now):
        if cond:
            if self.since is None: self.since = now
            self.latched = (now - self.since) >= self.sec
        else:
            self.since = None; self.latched = False
        return self.latched
