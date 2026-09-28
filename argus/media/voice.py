# -*- coding: utf-8 -*-
"""O'zbekcha ovozli ogohlantirish.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import os
import wave
from config import *
try:
    import winsound
except ImportError:
    winsound = None



class Voice:
    """O'zbekcha ovozli ogohlantirish — NAVBAT bilan (bittasi tugamaguncha
    keyingisi boshlanmaydi → ovoz uzilib qolmaydi). Bir vaqtda bir nechta xavf
    bo'lsa, VOICE_PRIORITY bo'yicha eng muhimi aytiladi."""
    def __init__(self, cooldown=4.0):
        self.cooldown = cooldown
        self._last = {}              # tag → oxirgi aytilgan vaqt (cooldown)
        self._busy_until = 0.0       # kanal shu vaqtgacha band (joriy ovoz tugaydi)
        self._dur = {}               # tag → wav davomiyligi (s)

    def _duration(self, wav):
        if wav in self._dur:
            return self._dur[wav]
        d = 1.5
        try:
            with wave.open(wav, "rb") as w:
                d = w.getnframes() / float(w.getframerate() or 44100)
        except Exception:
            pass
        self._dur[wav] = d
        return d

    def play(self, active_tags, now):
        """active_tags — hozir faol xavflar to'plami. Kanal bo'sh bo'lsa,
        ulardan eng ustuvorini (cooldown o'tgan) bir marta aytadi."""
        if now < self._busy_until:
            return None
        for tag in VOICE_PRIORITY:
            if tag not in active_tags:
                continue
            if now - self._last.get(tag, -1e9) < self.cooldown:
                continue
            wav = os.path.join(AUDIO_DIR, tag + ".wav")
            if winsound and os.path.exists(wav):
                winsound.PlaySound(wav, winsound.SND_FILENAME | winsound.SND_ASYNC)
                self._busy_until = now + self._duration(wav) + 0.15
            elif winsound:
                winsound.Beep(1100, 400)
                self._busy_until = now + 0.55
            self._last[tag] = now
            return tag
        return None
