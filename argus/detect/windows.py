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


class EpisodeHold:
    """Epizodni 'ushlab turish': tur faol ro'yxatdan chiqsa ham, `hold` s
    davomida epizod OCHIQ hisoblanadi. Shu oynada tur qaytsa — o'sha epizod
    davom etadi (bitta ID, yangi rasm/video yo'q).

    Nega kerak (2026-09-28 08:35-08:39): yuz bir lahzaga topilib yana
    yo'qolganda 4 daqiqada 8 ta alohida "yuz" epizodi ochildi — har biriga
    rasm + video (16 ta media). Matn 120 s cheklovda edi, media esa yo'q."""

    def __init__(self, hold):
        self.hold = float(hold)
        self.last_seen = {}          # tur -> oxirgi faol vaqt
        self.ended = {}              # tur -> yopilgan epizodning oxirgi faol vaqti

    def update(self, active, now):
        """active — hozir faol turlar. Qaytadi: ushlab turilgan turlar to'plami."""
        for t in active:
            self.last_seen[t] = now
        held = set()
        for t, ts in list(self.last_seen.items()):
            if now - ts <= self.hold:
                held.add(t)
            else:
                self.ended[t] = ts       # yopilish kadrida davomiylik uchun
                del self.last_seen[t]
        return held

    def seen(self, tag, default=None):
        """Oxirgi faol vaqt — ochiq epizod bo'lsa undan, yopilgan bo'lsa
        yopilish paytidagi qiymatdan (ushlab turish oynasi hisobga kirmaydi)."""
        if tag in self.last_seen:
            return self.last_seen[tag]
        return self.ended.get(tag, default)
